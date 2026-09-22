# P5-5D-S3 Round-3 Fix Work Order（给实现者）

你是 P5-5D S3 的实现者。仓库 `/home/dev/gateway-data-management-system`，当前 HEAD
`2233e80cc1b8e1288acf1ed9785c6b84093f67ce`（parent `6a27565b55`）。依据：
[p5-5d-s3-re-review.md](p5-5d-s3-re-review.md)（本轮复审，**结论 REQUEST CHANGES**）与其逐条采纳的
第二份复审条目 R1–R9。上一轮工单见 [p5-5d-s3-remediation-work-order.md](p5-5d-s3-remediation-work-order.md)。

权威状态：`p5_5d_s3_stage_exit: not_evaluated`。本轮完成后**只能**写
`delivery_recommendation: pass_recommended` + `review: pending`，不得自签 stage exit / slice exit /
production_deployment_authorized。相关规则见仓库 `AGENTS.md` 与 execution plan §3 预算：
允许路径为 S3 行内的 `http/*`、`application/archive/*`、`domain/archive/*`、
`infrastructure/control_db/sqlite_archive.py`、`vnext/deploy/*`、`tests/test_archive_*.py`、
`tests/test_http_*.py`、`tests/test_production_wiring.py`、`tests/test_backend_readiness.py`、
`tests/test_architecture.py`、`tests/support/*`（fixture 改动须在 handoff 逐项列明）；**禁止**改其他四个包、
任何 `uv.lock`/`pyproject.toml`、Dockerfile/构建脚本、capability 私有实现，禁止新增 worker job、表、
outbox、broker/sidecar、Repository mount。

---

## T0（P1，阻断）修复 `ArchiveRequestBodyLimitMiddleware` 断连死循环

**位置**：`vnext/backend/src/gateway_backend/http/dependencies.py`，
`ArchiveRequestBodyLimitMiddleware.__call__` 的读取循环（约 347-364 行）：

```python
while more_body:
    message: Message = await receive()
    if message["type"] != "http.request":
        continue          # ← 缺陷：http.disconnect 走这里，more_body 恒为 True
    ...
```

**为什么是阻断级**：uvicorn 0.51.0 的两套协议实现在断连/响应完成后**同步**返回
`{"type": "http.disconnect"}`，没有让出点（`uvicorn/protocols/http/httptools_impl.py:563-575`、
`uvicorn/protocols/http/h11_impl.py:527-545`）。于是该循环变成没有 await 让出的紧循环：实测
`receive()` 每秒被调用 **4 697 855** 次，`asyncio.wait_for(..., 1.0)` 的定时回调**无法执行**，协程
永不返回。生产入口 `bootstrap/http_server.py:59-66` 未设 `workers`（单进程单事件循环），且中间件在
认证之前执行，因此**未认证客户端**对四条 Archive POST 路径中任意一条发起一个中途中断的请求，即可让
整个 backend（含 `/healthz`、`/readyz`）永久无响应并占满一核。端到端复现（真实 uvicorn + 裸 socket，
声明 `Content-Length: 5000` 只发 5 字节后关闭）：

```text
healthz before abort: ok=True (0.003s)
health probe failed: TimeoutError
healthz after aborted POST: ok=False (3.024s)
RESULT: SERVER STALLED
```

**要求改动**：

1. 任何非 `http.request` 消息（尤其 `http.disconnect`）都是**终止条件**，立即 `return`，不要
   `continue`；循环每轮都必须有真实让出点。语义：客户端已断开或响应已完成时不再继续读取 body，交给
   ASGI 服务器收尾（不返回任何响应）。
2. 保持既有行为不变：256 KiB 实际字节上限（含 chunked）→ 413；重复 JSON key → 422；四条 POST 路径
   生效、读路径不受影响；不引入新的模块或新机制。
3. **必须新增一个"修前失败、修后通过"的用例**（`tests/test_archive_http.py`，`pytest.mark.unit`，
   现有 pytestmark 即可）。注意 TestClient 永远发送完整 body，这条分支在现有 HTTP 用例下不可达，所以
   要直接驱动中间件。**必须在工作线程 + 截止时间**里运行，避免回归时测试自身挂起：

```python
def test_archive_body_middleware_returns_on_client_disconnect() -> None:
    """客户端中途断开时中间件必须立即返回，不得空转阻塞事件循环。

    TestClient 总是发送完整 body，无法覆盖该路径，因此直接驱动 ASGI 中间件。
    """
    calls = 0

    async def receive() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b'{"selected"', "more_body": True}
        return {"type": "http.disconnect"}

    async def inner_app(scope, receive, send):  # pragma: no cover - 不应到达
        raise AssertionError("inner app must not run on disconnect")

    async def send(message):  # pragma: no cover
        return None

    def run() -> None:
        asyncio.run(ArchiveRequestBodyLimitMiddleware(inner_app)(SCOPE, receive, send))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "middleware spun without yielding on http.disconnect"
    assert calls <= 3
```

   （`SCOPE` 为 `{"type": "http", "method": "POST", "path": "/v1/archives", "headers": []}`；
   请自行调整签名与 import，不要引入 pytest-asyncio。）
4. 保留证据：在 handoff 记一句"修复前该用例的表现"（可用 `git stash` 或临时还原循环手测一次），
   以证明用例确实能失败。

## T1（测试缺口）R1 / R2 / R3，全部落在 `tests/test_archive_http.py`

- **R1 跨 actor 的 Start key 重放**：另一位**同 scope 且有 `archive_submission`** 的 actor（复用现有
  `test_archive_cross_actor_idempotency_conflict_on_confirmation` 的 `extra_sessions` 写法）用
  actor-1 的 `Idempotency-Key` 与**完全相同**的 `/v1/archives` body 重放 → 断言 **200**、返回的
  `archive_plan_id`/`archive_result_id` 与首次一致、且 `archived_by == actor-1`
  （Design §5.2 的刻意非对称：Start fingerprint 不含 actor_id，审计 append 含 actor_id——对照那一条
  必须仍是 409 `IDEMPOTENCY_CONFLICT`）。用途：防止后续"顺手统一"破坏该语义。
- **R2 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 的 HTTP 断言**：用既有
  `tests/support/archive_fixtures.py::seed_bulk_approved_archive_candidates(db_path, count=201)`，
  `GET /v1/archive-candidates` → 断言 **409** 且 `code == "ARCHIVE_SCOPE_LIMIT_EXCEEDED"`，并断言响应体
  **不含**部分候选列表（设计：不返回可 Start 的部分集合）。全仓当前对该 code 零断言。
- **R3 非 string 边界行**：在既有共享参数表风格下补 `reason: 5`（或 `true`）与
  `expected_sequence: "0"` 两类，HTTP 断 422 `REQUEST_VALIDATION_FAILED`，同表内补 DTO 侧
  `pytest.raises(ValidationError)` 对照（现有表已覆盖 null/缺键/surrogate/多余字段）。
- 规范：模块级共享参数表；不新增 fixture；用例名描述业务行为（不要 `r1_*`/轮次命名）；不引入 Dolt
  fixture；不复制 S2 owner（`test_archive_audit.py`）的矩阵。

## T2（provenance）R4 / R5 —— 必须在 T0 完成后、于最终候选上执行

- **R4 source-tree digest 重算重记**：handoff 记的
  `a963b15a80059ed1dabbf982c8f65774beaf1e7d0f69ef5129dd386f067edd48` 在 `2233e80cc1` 上按其记录的
  recipe 复算稳定得到 `9ed8121ae4eb0ace2f5b0f2a0195bc6d398a4e923b5c44f63ca1fa04f19fd6e0`
  （905 文件；baseline 树 `ee44d67a…`、hash-first `fe6b5466…` 均不等），即该值算自提交前的中间态
  （镜像构建 19:44:50 +0900，提交 19:58）。本轮在**新 HEAD 干净树**上重算，并在 handoff 写全
  "命令 + 文件数 + 输出"。
- **统一 recipe（本轮起强制）**：`path\tsha256` + 相对路径，树级与文件级都用同一形式，不要再用
  `xargs sha256sum` 默认格式（后者正是 R8 的标签错因）：

```bash
cd <repo-root> && git ls-files 'vnext/**' | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum

cd vnext/backend/src && find . -name '*.py' -type f | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum
# 镜像侧同命令（cd /app/backend/src），两侧必须相等
```

  旧值不要保留为并列条目，标为 superseded 或直接删除。
- **R5 运行中容器证据改为 immutable ID**：`capture_running_container_provenance`
  （`tests/support/compose_gate_harness.py:239-256`）目前用 `docker compose ps --format {{.Image}}`，
  得到的是 tag（实测产物 `"image": "gateway-p5-5d-s3-rereview-gate-backend"`，无 `sha256:`），§6.2 明令
  禁止 tag-only。改为：对每个运行中的容器取 `docker inspect --format '{{.Image}}' <container_id>`
  （或 `compose ps -q | xargs docker inspect`），同时记录容器 ID 与 `sha256:` 镜像 ID，并（推荐）断言
  backend/worker 的值等于本轮 fresh build 的 image ID。产物落盘位置改为**可检索**（固定路径并打印，
  或在 handoff 直接列出三服务 container ID + `.Image`），不要只依赖 pytest `tmp_path`（只保留最近
  3 次运行）。该文件属 fixture 改动，按 Plan §3 在 handoff 逐项列明。

## T3（文档）R6 / R7 / R8 / R9 + Plan 残留

1. **R6**：handoff "Scope delivered" 写的 `vnext/backend/src/gateway_backend/http/app.py` 不存在，改为
   `vnext/backend/src/gateway_backend/app.py`（middleware 注册于 `create_app()`）。
2. **R7**：handoff 称泄漏扫描覆盖"七响应 forbidden 字段表"，实际 `test_archive_http.py` 只扫 3 个
   （candidates / preview / confirm）。二选一：把
   `test_archive_responses_do_not_leak_internal_fields` 扩到其余四个响应
   （anomaly-resolutions / audit-events / archives start / archive result，复用同一
   `ARCHIVE_FORBIDDEN_RESPONSE_SUBSTRINGS`，推荐），或把措辞改为"3 响应 + 表驱动扩展"。
3. **R8**：py digest 的 recipe 标签必须与实际算法一致；按 T2 的统一 recipe 重算后同时更新标签与数值
   （记录值 `1702492d…` 实为 `find|sort|xargs sha256sum|sha256sum` 默认格式；本轮若 `src` 未变可保留
   数值但必须改对标签）。
4. **R9**：把 `## Independent countersign` 块中交付方自己的结论改为
   `delivery_recommendation: pass_recommended` + `review: pending`，避免再次出现代签观感；继续保留
   `p5_5d_s3_stage_exit: not_evaluated`。
5. **Plan 残留（本轮复审 R-3）**：`p5-5d-archive-execution-plan.md` §4 的 "### S3" 段仍是修复前文本
   （"**S3 delivery complete** … focused gate **107 passed** … `p5_5d_s3_stage_exit: pass`；
   `next_step: P5-5D-S4`"），与 §1 的 `not_evaluated` 直接冲突。改为修复后事实（131 passed、conjunction、
   `not_evaluated`），并把 §1 与 handoff 的 `next_step` 一并改为 re-review 步骤
   （如 `P5-5D-S3-re-review`）；S4 只在 stage exit 签署后启动。
6. **（P3，可选）** 中间件短路的 413/422 响应不带既有 envelope 的 `details`，与 FastAPI 校验错误形状
   不一致——补 `details`（若成本极低）或在 handoff 记为已知差异。**不要**本轮实现请求体读取超时
   （slowloris），只在 handoff 登记为待 design 决策项。

## T4 复验与重采（由本轮改动性质决定）

本轮 T0 改 `src/`，因此 **必须 fresh build**：

```bash
# E1 focused gate
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py

# E3 五包 static
for pkg in backend repository_service repository_client repository_contracts shared_kernel; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done

# E2 fresh build + 全量 conjunction（宿主空闲！见下方注意）
GATEWAY_COMPOSE_GATE_PROJECT_NAME=<new-project> \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py

# 回归（第二份复审在 2233e80cc1 上记录 2350 passed，作为基线）
../scripts/uv-consume.sh -C . run pytest -q -m unit
```

注意：**E2 前确认宿主 8000 端口空闲**——`compose.yaml` 固定发布该端口，并发运行另一个 compose 栈会造成
`Bind for 0.0.0.0:8000 failed: port is already allocated` 的假失败（本轮复审实测 3 项因此失败）。若无法
串行，请在记录中说明并重跑。

重采要求：新 HEAD 的 source-tree digest、backend `src` py digest（本地 == 镜像）、三服务运行中 container
ID + `.Image`、镜像 ID 与构建时间、五锁与 `compose.yaml` SHA；`uv.lock` 不应出现在 diff 中。

## 完成定义（DoD）

1. T0 修复 + 断连用例；能给出该用例在修复前失败、修复后通过的证据。
2. T1 三条（R1/R2/R3）与 T3 R7（若选择补扫）的新用例，均按"修前失败"要求自检。
3. T2 在最终候选上重算/重记 provenance，recipe 统一且可复制。
4. T3 文档修订完成，handoff 与 Plan 内部一致，`next_step` 正确。
5. E1 / E2（0 skipped，宿主空闲）/ E3 全绿 + `-m unit` 无回归。
6. handoff 写 `delivery complete — pass_recommended`、`review: pending`、
   `p5_5d_s3_stage_exit: not_evaluated`；`git status` 中除已披露的
   `p5-5e-s0-independent-docs-review.md` 外无未跟踪残留，`vnext/**` 无未记录差异。
7. 提交后请求独立签署；S4 只能在 stage exit 签署后启动，且仍须按计划对最终候选做 fresh-build 全量
   conjunction。
