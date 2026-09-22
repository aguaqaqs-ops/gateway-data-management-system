# P5-5D-S3 Re-Review（remediation `2233e80cc1`）

日期：2026-09-22。结论：**REQUEST CHANGES（仅剩 1 项阻断）**——修复轮把合并版评审的 P1-1…P1-4 与绝大多数
P2/P3 关闭了，但**新引入的 `ArchiveRequestBodyLimitMiddleware` 存在可被远程触发的死循环，会阻塞整个
uvicorn 事件循环**。该项修复 + 重新取证后，本阶段可以进入 stage exit 签署流程。

评审绑定：`git HEAD = 2233e80cc1b8e1288acf1ed9785c6b84093f67ce`（parent `6a27565b55`）。
工作区：仅 `docs/.../p5-5e-s0-independent-docs-review.md` 未跟踪；`vnext/**` 干净。
输入：[合并版评审](p5-5d-s3-independent-review.md)、[修复任务单](p5-5d-s3-remediation-work-order.md)、
[新 handoff](p5-5d-s3-handoff.md)、accepted design、execution plan。

本次为**只读复审**：未修改任何实现、handoff 或 authority 字段，未提交、未部署、未产生 Repository effect。
为取证运行过 E1/E3 全量、E2 的部分用例（会构建镜像并起停容器，`compose down -v` 已清理），并在 `/tmp`
下使用临时探针脚本（未落入仓库）。

## 0. 本次实际运行

| 运行 | 结果 |
| --- | --- |
| E1 focused gate（六文件） | ✅ **131 passed, 1 warning, 7.1s**（与报告一致；`--collect-only` 亦为 131） |
| E3 五包 ruff + mypy | ✅ 全通过（backend 421 / repository_service 198 / client 26 / contracts 15 / shared_kernel 34 files） |
| E2 conjunction 复跑 | ⚠️ **3 passed / 3 failed**：`test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect`、`test_review_compose_e2e.py::…`、`test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` 通过；其余 3 项因 `Bind for 0.0.0.0:8000 failed: port is already allocated` 失败——同一时刻 `gateway-p5-5d-s3-remediation-gate-backend-1` 栈正在占用宿主 8000（交付方自己的容器门禁在并行运行），属环境冲突而非缺陷 |
| 镜像内容 == HEAD 源树 | ✅ 本地与 `gateway-p5-5d-s3-remediation-gate-backend` 的 `/app/backend/src` 摘要均为 `1702492dd7a947f62d8a0e8515ba8fdeb98614c40fd39ca7fb9307cc66950a3b` |
| 锁/Compose digest | ✅ 五个 uv.lock 与 `compose.yaml`（`f1b8ca6f…`）与 handoff 记录一致 |
| 中间件断连行为 | ❌ **实测：真实 uvicorn 进程被单个中断请求挂死**（R-1） |
| Source-tree digest 复算 | ❌ 与 handoff 记录不符（R-2） |

## R-1（P1，新引入，阻断）`ArchiveRequestBodyLimitMiddleware` 在请求中断时死循环，阻塞整个事件循环

位置：`vnext/backend/src/gateway_backend/http/dependencies.py:326-366`，核心是

```python
body = b""
more_body = True
while more_body:
    message: Message = await receive()
    if message["type"] != "http.request":
        continue          # <-- http.disconnect 走这里，且 more_body 永远为 True
```

证据一（服务端语义）：uvicorn 0.51.0 两个协议实现都在断连时**同步**返回 `http.disconnect`，没有任何
await 让出点——`protocols/http/httptools_impl.py:563-575` 与 `protocols/http/h11_impl.py:527-545`：

```python
if self.disconnected or self.response_complete:
    return {"type": "http.disconnect"}
```

证据二（单元级）：用假 `receive` 先给一段不完整 `http.request`、再持续返回 `http.disconnect`，
中间件**永不返回**：1 秒内调用 `receive()` **4 697 855 次**，2 秒内 9 373 979 次；外层
`asyncio.wait_for(..., 1.0)` 的定时回调**根本无法执行**（事件循环被独占），线程永不退出。

证据三（端到端）：把一个只挂该中间件 + `/v1/archives` + `/healthz` 的最小 FastAPI 应用跑在真实
uvicorn 上，先确认 `/healthz` 3ms 内 200，然后用裸 socket 发
`POST /v1/archives`（`Content-Length: 5000`，只发 5 字节后关闭）：

```text
healthz before abort: ok=True (0.003s)
health probe failed: TimeoutError
healthz after aborted POST: ok=False (3.024s)
RESULT: SERVER STALLED
```

影响：生产入口 `bootstrap/http_server.py:59-66` 的 `uvicorn.Config(...)` **未设置 `workers`**，即单进程
单事件循环；中间件又在认证之前执行，且只按路径匹配四条 Archive POST。因此**未认证**的客户端只要对
`/v1/archives`（或其余三条写路径）发起一个中途中断的请求，就能让整个 backend HTTP 服务（含
`/healthz`、`/readyz`）永久无响应并占满一个 CPU 核，直到进程被外部重启。这不是"archive 局部降级"，
而是全服务 DoS。

最小修复：把任何非 `http.request` 消息（尤其 `http.disconnect`）当作终止条件立即返回/抛出，不要
`continue`；循环内每轮都必须有真实让出点。建议实现：

```python
while more_body:
    message = await receive()
    if message["type"] != "http.request":
        return  # 客户端断开或响应已完成：不再读 body，交给服务器收尾
    ...
```

测试要求（该缺陷正是"缺一个可失败的用例"）：在 `tests/test_archive_http.py` 增加中间件级用例——用
假 `receive` 构造"部分 body → `http.disconnect`"，断言在超时前正常返回（例如
`asyncio.wait_for(mw(scope, receive, send), 1.0)` 必须完成而不是挂起）；可选再加一条端到端断言：中断的
archive POST 之后 `/healthz` 仍能响应。注意 TestClient 会完整发送 body，**现有 HTTP 用例无法覆盖**该路径。

## R-2（P2）Provenance 两项仍不满足 §6.3

1. **Source-tree digest 不可复算**。handoff 记录 `a963b15a80059ed1dabbf982c8f65774beaf1e7d0f69ef5129dd386f067edd48`
   （905 文件，recipe 为 `git ls-files 'vnext/**' | LC_ALL=C sort | while read p; …`）。在
   `2233e80cc1` 上按同一 recipe（及其 `read -r`、变量顺序等变体）复算，稳定得到
   `9ed8121ae4eb0ace2f5b0f2a0195bc6d398a4e923b5c44f63ca1fa04f19fd6e0`（905 文件，数量一致）。
   另测：baseline `6a27565b55` 树为 `ee44d67a30f120348ad2775d643d37f594d6655f6f0f0f4dfa40e6396199302a`、
   hash-first 变体为 `fe6b54667b91ae645be13d747d7db416659ce206553f25c10b6188926feb073b`，均不等于记录值。
   即记录值与交付候选不对应（很可能是在修复过程中、提交前的工作树状态上计算的）。§6.3 要求 digest
   绑定被验证的候选，因此必须在最终候选上重算并写入 handoff（R-1 修复后必然要重算一次）。
2. **运行中容器证据不合规（且交付方产物不可检索）**。`capture_running_container_provenance`
   （`tests/support/compose_gate_harness.py:239-256`）用
   `docker compose ps --format '{{.Name}}\t{{.ID}}\t{{.Image}}'`：容器 ID 是运行中采集 ✅，但
   `{{.Image}}` 是镜像**引用/tag**，不是 §6.3 要求的 immutable `.Image` ID（需
   `docker inspect --format '{{.Image}}' <container>`）。本次复审自己运行该用例得到的产物为证：

   ```json
   {"gateway-p5-5d-s3-rereview-gate-backend-1": {"container_id": "b38c3615a4ad",
    "image": "gateway-p5-5d-s3-rereview-gate-backend"}, …}
   ```

   即 `image` 字段不含 `sha256:`。另：产物只写到 pytest `tmp_path`，复审时在
   `/tmp/pytest-of-dev/*/` 未找到交付方那次运行的该文件（可能已被 pytest 清理或 basetemp 不同），
   评审无法检索。修复：采集 immutable image ID（并断言其等于 fresh build ID），把结果落到可检索位置，
   或在 handoff 中直接列出三个服务的 container ID + `.Image`。
3. 次要：`Git HEAD | introduced_by_this_commit` 未记录字面 SHA（§6.3 要求完整 HEAD）。若采用
   "由引入提交自我指代"的写法，应在 handoff 或 acceptance 记录中同时给出字面 SHA。

已核对通过：backend `src` py digest 本地 == 镜像 ✅；三个 image ID 存在 ✅；五锁/Compose digest 不变 ✅；
backend/worker 无 OCI revision 标签已如实记录并以 py digest 对等补偿（可接受）。

## R-3（P2）Plan §4 S3 段仍保留修复前的自签文本，与 §1 自相矛盾

`p5-5d-archive-execution-plan.md` 的 status 行与 §1 authority 块已正确回退
（`p5_5d_s3_stage_exit: not_evaluated` ✅），但 §4 的 "### S3" 段落仍是旧文本：

> **S3 delivery complete**（2026-09-22）… focused gate **107 passed**；fresh-build conjunction
> **6 passed, 0 skipped**；五包 static 全通过；`p5_5d_s3_stage_exit: pass`；`next_step: P5-5D-S4`。

这与 §1 的 `not_evaluated` 直接冲突，并残留了被否定的自签记录。另：handoff countersign 与 plan §1 都写
`next_step: P5-5D-S4`，但 stage exit 尚未签署，下一步应是独立 re-review（例如
`P5-5D-S3-re-review`），S4 只能在签署后启动。

修复：把 §4 S3 段更新为修复后的事实（131 passed / conjunction / `not_evaluated` / 下一步 re-review），
并统一 `next_step`。

## R-4（P3）表述与覆盖的残余缺口

1. handoff 写 "HTTP responses 不泄漏 … （**七响应** forbidden 字段表）"，实际
   `test_archive_responses_do_not_leak_internal_fields` 只扫描 **3** 个响应
   （candidates、preview、confirm）。补齐其余四个（anomaly-resolutions、audit-events、archives start、
   archive result）或改写措辞。
2. "技术 main 在后提交者" 仅以 `main_after_both != initial_commit_id` 断言，未把 B 的提交确认为 main。
   建议直接断言 main == B 的 submission commit（可从 submission 读取或候选事实取）。
3. 边界参数表仍缺计划逐字点名的 "reason / `expected_sequence` 非 string" 行（Application 层已有
   `test_archive_audit.py` 覆盖非整数，HTTP 层缺）；建议补两行。
4. `P2-9` 只补了 confirmation key 的跨 actor 冲突；**Start key 由另一位授权 actor 重放应成功且保持原
   `accepted_by`**（Design §5.2 的刻意非对称）仍无用例固定。

## 关闭条目核对（我逐条验证的结论）

| 条目 | 结论 | 验证方式 |
| --- | --- | --- |
| P1-1 500→422 | ✅ 关闭 | 代码审读（`ArchiveRequestValidation` + DTO 收口 + `Query(ge/le)` + `model_validator` + refs 上限/唯一性）+ E1 131 passed（含 5 类 query、REVOKE null/缺键、201 refs、重复 refs、409 codes、429×3、跨 actor 冲突） |
| P1-2 双 actor Compose | ✅ 关闭 | 代码审读（两份同 base 候选、anomaly 指向 B、dispositions、releases、Head==A 的 commit、commit 集合与 operation 计数窗口、新 base preview、restart 后 Result/audit）+ 我复跑该 nodeid 通过 |
| P1-3 跨 scope 证据 | ✅ 关闭 | 代码审读：同 DB 第二条 mapping + `OTHER_SCOPE_BEARER` 得 404，同 scope 跨 actor 得 200；archive 读取走 `resolve_provisioned_scope`（读 DB mapping），故 404 由 scope 过滤产生；handoff 记录的可失败性实验（临时移除过滤 → 200）与机制一致 |
| P1-4 authority 回退 | ⚠️ 基本关闭 | handoff/plan §1 已回退；§4 残留见 R-3 |
| P2-1 256 KiB | ✅ 关闭（但引入 R-1） | 中间件按实际字节计数（declared + chunked 用例）；无 `Content-Length` 也生效 |
| P2-2 重复 JSON key | ✅ 关闭 | `object_pairs_hook` 拒绝重复键 → 422，用例存在 |
| P2-3 稳定码分工 | ✅ 关闭 | handoff 记录决策；`ARCHIVE_AUDIT_VERSION_CONFLICT`（含 details）/`CANDIDATE_SET_CONFLICT` 等已被测试固定 |
| P2-4 参数表 | ⚠️ 部分 | null/缺键/非法 surrogate ✅；非 string 行缺（R-4.3） |
| P2-5 append 429 | ✅ 关闭 | 三条写路由参数化 |
| P2-6 provenance | ❌ 未关闭 | 见 R-2 |
| P2-7 handoff 数字 | ✅ 关闭 | 19 passed 实测一致；HTTP main 表述已改为仅 compose 证明 |
| P2-8 单 submission 断言 | ✅ 关闭 | 观察窗口/新 base preview/audit 读取已补 |
| P2-9 跨 actor replay | ⚠️ 部分 | confirmation key 冲突 ✅；Start key 非对称缺（R-4.4） |
| P3-1…P3-11 | ✅ 基本关闭 | 死代码删除、`disposition` Literal 与 `# type: ignore` 移除、OpenAPI 字面量基线、job registry 精确 key 集合、session.json 断言、`extra=forbid` HTTP 用例、Preview 只读改用 `assert_archive_durable_state_unchanged`、helper 迁入 `compose_gate_harness.py`（无跨测试私有 import 残留）、`journey_key_prefix` 已实际启用；泄漏扫描 3/7 见 R-4.1 |

另核对：`tests/test_archive_audit.py` 的改动只是把断言异常类型从 `ValueError` 换成
`ArchiveRequestValidation`，未削弱语义 ✅。

## 关闭条件

1. 修 R-1（含中间件级断连用例），并确认修复后 E1 仍全绿。
2. R-2：在最终候选上重算 source-tree digest；容器证据改为 immutable `.Image` ID 且可检索；补字面 HEAD。
3. R-3：Plan §4 S3 段与 `next_step` 更正。
4. R-4：泄漏扫描补到七响应、技术 main 断言、非 string 行、Start key 跨 actor 重放。
5. 改变 `vnext/**` 后重跑 E1 + E3 + **完整 E2**（在宿主空闲、无并行栈占用 8000 时执行，0 skipped），
   并重采 provenance；随后由独立 acceptance authority 决定 `p5_5d_s3_stage_exit`，交付方继续只写
   `pass_recommended`。

环境提示（非缺陷）：E2 依赖 `compose.yaml` 固定发布宿主 8000 端口，多会话并行时会出现
`port is already allocated` 的假失败；建议 gate 期间串行化，或在 harness 中支持端口覆盖。

本次仅新增本报告，不代签 handoff，不修复实现，不执行 commit、部署或 Repository effect。
