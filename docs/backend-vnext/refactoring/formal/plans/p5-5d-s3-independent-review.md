# P5-5D-S3 Independent Review（合并版）

日期：2026-09-22。结论：**REQUEST CHANGES；不支持维持 `p5_5d_s3_stage_exit: pass`；S4 不得启动。**

本文件是两轮独立评审的**合并版**，作为本阶段 closure 的唯一评审依据；两轮原始编号映射见附录 A，
两轮均不再单独引用。合并方法：并集去重、以"能否失败/能否复现"复核每一条、按统一 P1/P2/P3 定级
（定级分歧在条目内显式记录）。

评审绑定：

- `git HEAD = 6a27565b55342cdab9e3c137664fb7ca330f9a89`（parent `a6720238d6`）。
- 工作区：仅两份未跟踪评审文档（本文件与 `p5-5e-s0-independent-docs-review.md`），无 `vnext/**` 差异；
  评审窗口内曾出现的临时探针已由对应评审者删除，当前 `ruff check .` 与 `mypy`（421 source files）通过。
- 输入：[S3 handoff](p5-5d-s3-handoff.md)、[accepted design](p5-5d-archive-design.md)、
  [execution plan](p5-5d-archive-execution-plan.md)、testing conventions、proportional assurance policy。
- 本报告不修改 handoff 签署状态，不修复实现，不执行 commit、deployment 或 Repository effect。

## 0. 已复核通过的证据

| 声明 | 复核方式 | 结果 |
| --- | --- | --- |
| focused gate 107 passed | 受控 wrapper 单进程重跑六文件 | ✅ `107 passed`（~5.4s） |
| 五包 ruff + mypy | backend 本轮实跑；其余四包由另一轮实跑通过 + 本轮核对自 S1 起零源码改动 | ✅ `ruff` All checks passed；`mypy` 421 files 无错 |
| 五锁 SHA + compose.yaml SHA | `sha256sum` 对比 handoff | ✅ 六项全部一致 |
| 三个 image ID | `docker images` | ✅ `a05b5de49b67` / `313302c977a8` / `70c25d76bb1a` 均存在 |
| 镜像内容 == HEAD 源树 | 镜像内 `/app/backend/src` 与本地逐文件 SHA-256 列表摘要 | ✅ 两侧 245 文件、摘要相同（recipe 见 B.3） |
| 7 条路由 + 生产 OpenAPI 路径集 | 读 `wiring.py`/`routes/archives.py` + `test_http_openapi.py` | ✅ 注册与冻结集合一致（+7） |
| write 路由 `acquire_new_work`、Preview 纯读、独立 permission、409/404 映射骨架 | 逐文件审读 | ✅ 结构正确 |
| O-1 修复（`_authoritative_baseline_head`） | diff 审读 | ✅ 对齐权威 Head，断言未削弱；`test_production_wiring.py` 实测 **19 passed**（handoff 记 18） |
| `session.json` / `deploy/README.md` | 审读 | ✅ 权限显式、initial-only seed、升级步骤、secret 路径齐全（该示例无测试读取，见 P3-8） |
| 交付的容器 conjunction（6 passed, ~277s） | **两轮均未重跑**；仅核对 image ID 存在与内容等价 | ⚠️ 仍属 delivery 自报证据；本轮另跑的双 actor 旅程（见 P1-2）在**同一源内容**上重建镜像并通过 |
| 跨 scope / 跨 actor 拒绝 | 读用例与 harness | ❌ 现有用例空转（P1-3） |

## 1. P1（阻断）

### P1-1 生产错误契约：5 类可修复输入返回 500 而非 422

位置：`http/routes/archives.py:188-193`（query 参数无界）、
`http/orchestration/archive.py:236-270`（只把 `subject_kind` 的 `ValueError` 映射为 422）、
`http/schemas/archive.py:105`（`reason` 允许 `null`，无 action 相关必填性校验）、
`http/schemas/archive.py:131-132`（两个 ref 数组无长度/唯一性约束）、
`application/archive/queries.py:202-206`、`application/archive/audit.py:92`、
`application/archive/contracts.py:349-352`（全部抛裸 `ValueError`）。

进程内 HTTP 探针实测（合法 session + `archive_submission`）：

| 输入 | 实际 | Design §8.2 / 路由自身 `responses` 要求 |
| --- | --- | --- |
| `GET /v1/archive-audit-events?subject_digest=not-a-digest` | **500** | 422 `REQUEST_VALIDATION_FAILED` |
| 同路由 `limit=0` / `101` / `-1` | **500** | 422（100 为设计硬上限） |
| 同路由 `after_sequence=-1` | **500** | 422 |
| `POST /v1/archive-confirmations` `action=REVOKE` + `reason: null`（或缺失） | **500** | 422（需 reason 的动作不允许 null/空串） |
| `POST /v1/archives` 带 201 个 `confirmation_refs` | **500** | 422（audit refs 上限 200） |

根因：边界校验散落在 Application `contracts.py`，抛裸 `ValueError`；`http/errors.py` 无
`ValueError → 422` 映射（`@app.exception_handler(Exception)` 兜底为 500），
`orchestration/archive.py:248-256` 只 catch 了 `subject_kind`。结果是"客户端可修复输入"与
"服务端故障"不可区分，且路由 `responses={422:…}` 声明与实际不符。

修改意见（两层）：

1. DTO 层收口：`subject_digest` 查询参数改用 schema 内已有的 `ArchiveDigest` Annotated；
   `after_sequence` 加 `Query(ge=0)`；`limit` 加 `Query(ge=1, le=ARCHIVE_AUDIT_EVENTS_MAX_LIMIT)`；
   两个 ref 数组加 `Field(max_length=ARCHIVE_MAX_AUDIT_REFS)` + 唯一性 validator；
   `AppendArchiveConfirmationRequest` 加 `model_validator`，接上目前**是死代码**的
   `schemas/archive.py:407 validate_confirmation_reason_field`（按 action 判 null 合法性）。
2. Application 层兜底：`application/archive/errors.py` 新增
   `ArchiveRequestValidation(ArchiveApplicationError)`，`stable_code="REQUEST_VALIDATION_FAILED"`，
   让 `contracts.py` 的 validator 抛它——`map_domain_exception` 的 `SubmitApplicationError` 兜底分支
   （`http/errors.py:299-311`）天然映射 422，无需新增映射表项。

测试 owner：`test_archive_http.py`（Design §9 已把 "DTO/error、body 限额" 分给该文件）。新增共享
参数表覆盖上表五类，按 §8.2 语义命名，不复制 Application owner 的 sequence/幂等矩阵。

### P1-2 Compose 旅程未达 Plan §4 S3 最低屏障，且 handoff 的豁免理由不成立

位置：`tests/test_archive_compose_e2e.py`（仅单 submission 旅程）；
[p5-5d-s3-handoff.md](p5-5d-s3-handoff.md) 的 "Compose journey scope note"。

Plan §4 逐字要求："Archive journey 至少两位 actor 两份同 base 成功 Submission：技术 main 在后
提交者，选择先提交者归档，验证业务 Head 指向其 commit、后提交者 CLOSED_NOT_ARCHIVED、全部相关
Workspace release。"handoff 以"同 device/project 第二次 Submit 触发 `SUBMIT_OCCUPANCY_CONFLICT`"
缩减为单 submission。

该理由只对"同 actor 重提"成立，屏障本身可达——两轮证据互补：

- 静态追溯：`finalize_transaction.py:119` 在 finalize 删除 repository occupancy；
  workspace OPEN 唯一索引是 actor 级（`migrations.py:425-428`
  `CREATE UNIQUE INDEX workspace_records_open_exact_scope ON workspace_records(owner_actor_id,
  gateway_device_external_key, business_project_id) WHERE state='OPEN'`）→ 第二位 actor 拿自己的
  workspace；`review.py:39-45` 的 `_RELEASE_ACTIONS` 只有 REJECT/RETURN_FOR_REVISION/WITHDRAW，
  APPROVE 不释放；workspace 由 Archive 统一释放（`archive/start.py:401-432` 遍历
  `snapshot.candidates`）——业务设计预期多 workspace 同存到归档。
- 真实运行（本轮新跑，重建镜像 + 真实 repository-service，两次上传/preview/submit、两次 approve）：

```text
first:  ws-53f493cb-…（actor compose-actor-1）
second: ws-09a867e4-…（actor compose-actor-2，同 device/project scope）
candidates: [sub-7b894875-…, sub-c677413b-…]                     # 两份同 base 候选
anomalies:  [APPROVED_SIBLING_EXCLUDED → sub-c677413b-…]  can_start=False
can_start after resolution: True []
dispositions: A=ARCHIVED_BASELINE, B=CLOSED_NOT_ARCHIVED         # 选择先提交者
released workspaces: [ws-53f493cb-…, ws-09a867e4-…]              # 两份都 release
result: baseline_head_version=1, baseline_commit_id=<A 的 commit>
main before == main after                                        # Archive 零 Repository effect
```

修改意见：给 `test_submit_compose_e2e.py:_run_accept_to_submission_read_journey` 增加
session/token 参数（与已接受的 `journey_key_prefix` 同类最小 seam），用第二位 actor 跑第二次
上传/preview/submit，并断言：两份同 base 候选 → `APPROVED_SIBLING_EXCLUDED` 指向后提交者 →
resolution 后 `can_start=True` → dispositions = `ARCHIVED_BASELINE` + `CLOSED_NOT_ARCHIVED` →
`released_workspace_ids` 覆盖两个 workspace → 业务 Head == 先提交者 commit 且 main 不变 →
restart 后可读 Result/audit。handoff 的 scope note 删除，或改写为"同 actor 未归档重提被占用阻塞"。

同时补齐现有单 submission 旅程缺失的断言：`dispositions`、`released_workspace_ids`、归档后
新 base 的下一轮 Preview、scope 内 audit 读取。

### P1-3 跨 scope 拒绝用例是空转的（证据无效）

位置：`tests/test_archive_http.py:327-347`。

`tests/support/http_workspace_harness.py:864-865` 每次调用都 `initialize_control_db(tmp_path /
"control.db")`，`other_env` 用的是**另一份 DB**；`tests/support/workspace_fixtures.py:31-32` 的
`FixedScopeResolutionPort.resolve` 直接 `del context`。因此该用例的 404 只证明"该 id 在另一个库里
不存在"——即使删掉生产代码的全部 scope 过滤，测试仍会通过。Plan §4 明文把
"cross-actor/project/Repository 拒绝" 列为 S3 屏障，目前没有有效证据。

生产代码路径本身正确（`application/archive/queries.py:257-273` 按 repository_id + device + project
三级过滤），因此本条是**证据无效**而非已复现缺陷（第一轮评审定 P2，合并定为 P1：屏障未满足）。

修改意见：同一 control DB + `extra_sessions` 挂第二 scope session（`test_review_http.py` 的
`OTHER_SCOPE_BEARER` 模式是现成范例），把**已存在**的 archive result 暴露给错误 scope，断言
404/403；再补一条同 scope 不同 actor 的读取用例。

### P1-4 流程：delivery 自签 `p5_5d_s3_stage_exit: pass`

Plan §1（第 51 行）明文："delivery 只给建议，不自行代签阶段通过或 slice acceptance"。S2 先例：
handoff 首版（`12441a5402`）为 `p5_5d_s2_stage_exit: not_evaluated` + `review: pending`，直到独立
closure review 通过（`a6720238d6`）才变成 `pass` + `review: accepted`。S3 handoff 在
`review: pending` 的同时写 `pass`，并同步把 Plan 的 authority 块改为 "S3 pass / next_step:
P5-5D-S4"，自相矛盾。

修改意见：handoff 与 Plan 回退为 `p5_5d_s3_stage_exit: not_evaluated`、
`next_step: P5-5D-S3-remediation`；本文 findings 闭环 + 独立 re-review 通过后再签。

## 2. P2

### P2-1 413 上限形同虚设

位置：`http/orchestration/archive.py:59-70`、`http/routes/archives.py:82,116,160,234`。

实测：同一合法 body 带 `Content-Length > 256 KiB` → 413；同 body 以 chunked（无 `Content-Length`）
→ **201 成功**。且 `ensure_request_body_within_limit` 在 handler 体内执行，此时 FastAPI 已完整读入并
解析 body；`int()` 对负数静默通过，非法头直接放行。Design §3.3 的 256 KiB 是资源预算，目前既不覆盖
chunked，也不是"读前"拦截。

修改意见：ASGI 中间件/依赖层按实际读取字节计数后 413；或由 design owner 显式接受 declared-only
语义、拒绝缺失/非法头，并修订 §3.3/§8.2 措辞——二选一，留决策记录。

### P2-2 重复 JSON key 静默覆盖

位置：`http/schemas/archive.py`（沿用 FastAPI 默认 JSON 解析，无重复 key 检测）。

实测两例：`{"reason":"first","reason":"second"}` → 201（取最后值）；
`{"action":"CONFIRM",…,"action":"REVOKE"}` → **按 REVOKE 进入业务分支**（`409
ARCHIVE_AUDIT_VERSION_CONFLICT`）。Design §8.1 明文"duplicate JSON keys 不得悄悄覆盖"，第二例说明
重复 key 能改变动作语义，不只是文本取值。

修改意见：Archive 写路由前用 `object_pairs_hook` 严格解析拒绝重复 key；或由 design owner 显式修订
该句（平台现有严格解析只在 multipart 侧）。

### P2-3 同一条件在 append 与 Start 返回不同稳定码

位置：`application/archive/audit.py:132,134,141,243,245,263,265`（一律 `BaselineVersionConflict`
→ `BASELINE_VERSION_CONFLICT`）对
`application/archive/start.py:147,153,181`（`CandidateSetConflict` / `CandidateBindingConflict`）。

Design §8.2 只列全局 409 集合、未按命令分配，故**不是设计违背**，而是可观测性不一致：append 侧
无法区分 Head 漂移与候选集合/选择漂移。定级分歧：第一轮评 P3、第二轮评 P2；合并定 P2，因为无论是否
统一码，都必须在测试中固定，否则映射分支无人负责（见 P3-1）。

修改意见：由 design owner 决定"统一 append 路径稳定码"或"保留并写明语义"；随后在
`test_archive_http.py` 用按 §8.2 语义命名的 409 断言固定（含 details 的 expected/actual）。

### P2-4 边界参数表缺 Plan 逐字点名的行

位置：`tests/test_archive_http.py:42,51`（`ARCHIVE_HTTP_ID_BOUNDARY_CASES` /
`ARCHIVE_HTTP_REASON_BOUNDARY_CASES`），`:474`（null reason）、`:487`（surrogate）。

Plan §4 S3 要求 "缺失/null/非 string/非法 surrogate 按 action/strict shape 拒绝"。现表只有 null 与
surrogate，缺 "reason 缺键" 与 "reason / `expected_sequence` 非 string" 两行。P1-1 修复后
"REVOKE 缺 reason 键"会由 500 变 422，正好一并补表。

### P2-5 append 路由无 429 用例

屏障写的是 "append/Start 受 shutdown admission"，现只有
`test_archive_start_returns_429_when_admission_closed`（`test_archive_http.py:312-325`）。把
closed-gate 用例参数化到三条写路由。

### P2-6 Provenance 不符 Plan §6.3

1. `implementation_candidate_head: a6720238d6` 是**父提交**；镜像 `Created =
   2026-09-22T05:45:43Z`（14:45:43 +0900），而 S3 内容在 `15:47:47 +0900` 才提交为 `6a27565b55`。
   即镜像来自未提交工作树（内容已核对一致，见 B.3，但记录绑定了错误对象）。
2. 缺 §6.3 明确要求的 source-tree digest、`clean/dirty` 标记、**运行中 container ID 与 `.Image`**
   （handoff 自述 "running container IDs not retained"；§6.2 明确"仅有 tag 或预构建 inspect 不能证明
   实际被运行"）。两轮均未复算同一 recipe 的 source-tree digest（见 B.3 的数值差异）。
3. backend/worker 镜像无 revision 标签（`docker inspect` 的 `org.opencontainers.image.revision` 为空）。
4. `repository-service` 复用 33 小时前的 `gateway-repository-service:local`（label revision
   `d19b3efcab`）。已核对 `823661134e..HEAD` 对 `vnext/repository_service|repository_client|
   repository_contracts|shared_kernel` **零改动**，复用实质成立，但 §6.2 要求显式跑
   `build-repository-service-image.sh` 并记录等价性论证，handoff 只有一句 "build script skipped when
   tag present"。

修改意见：修复候选重跑时按四项逐一重采（含统一 recipe 的 source-tree digest 与运行中 container ID），
并给 backend/worker 镜像加 revision 标签。

### P2-7 handoff 数字与表述错误

1. `test_production_wiring.py` 实为 **19 passed**（本机 collected=19、passed=19），handoff 写 18。
2. "Archive Start produces zero Repository effect (main commit unchanged in HTTP and compose tests)"：
   `test_archive_http.py` 是进程内 fake Repository，全文只有 `assert "repository_id" not in body`，
   没有 main 可比——该句仅在 compose 侧成立。
3. 零写观察窗口只比较了 main 两次；§6.2 还要求 Repository **commit 集合**与"窗口内 Backend
   Operation 集合无新增 Archive operation"，需补齐或降级表述。

### P2-8 单 submission 旅程断言不完整

见 P1-2 末段（`dispositions`、`released_workspace_ids`、新 base Preview、audit 读取四项缺失）。

### P2-9 跨 actor replay 语义未在 HTTP 层固定

Design §9 把 "cross-actor replay 与读取" 分给 `test_archive_http.py`，该文件未覆盖。需补两条：
另一位有权限 actor 用他人 confirmation key + 完全相同 body → 409 `IDEMPOTENCY_CONFLICT`
（fingerprint 含 `actor_id`）；同一 Start key 由另一位授权 actor 重放 → 成功 replay 且 `archived_by`
保持原 `accepted_by`（Design §5.2 的**刻意非对称**，必须被固定而不是被后续"顺手统一"改掉）。

## 3. P3（修复轮顺手处理）

1. **错误映射分支无测试固定**：`ARCHIVE_AUDIT_VERSION_CONFLICT`、`CANDIDATE_SET_CONFLICT`、
   `ARCHIVE_SCOPE_LIMIT_EXCEEDED`、`IDEMPOTENCY_CONFLICT` 在测试目录零出现。本轮探针确认其行为
   **正确**（stale `expected_sequence` → 409 + `details{expected:0,actual:1}`；同 key 不同 body →
   409 `IDEMPOTENCY_CONFLICT`；201 candidates → 409 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`；缺
   `Idempotency-Key` → 422），但一次分支顺序调整（例如 `ArchiveAuditVersionConflict` 落到
   `SubmitApplicationError` 兜底）就会静默变 422。
2. **死代码**：`schemas/archive.py:68 ArchiveCandidateRefRequest`（仅定义无引用）、
   `schemas/archive.py:401 validate_utf8_reason_field`（无引用，删）、
   `test_archive_http.py:40 OTHER_SCOPE_BEARER`（仅定义无引用）。`validate_confirmation_reason_field`
   不要删，按 P1-1 接进 DTO。
3. **死参数**：`journey_key_prefix` 三个 caller 全用默认值，handoff 宣称的 "idempotency isolation"
   实际未生效；P1-2 的双 actor 旅程正好启用它。
4. **类型抑制**：`schemas/archive.py:433` 的 `# type: ignore[arg-type]` 源于
   `application/archive/queries.py:68` 把 `disposition` 声明为裸 `str`；收敛为闭合枚举/Literal 后移除。
5. **参数表复用与无效表达式**：`test_archive_http.py:399-400` 复用 ID 表前两行做 idempotency-key
   用例；`:411` 的 `validate_utf8_id(...) if … else None` 是无效表达式语句。
6. **Preview 只读证明过窄**：`_archive_table_counts` 只数 3 张表（漏 `archive_disposition_records`），
   建议复用 `tests/support/archive_fixtures.py:71 assert_archive_durable_state_unchanged`。
7. **泄漏扫描覆盖 2/7 响应**：建议对七个响应统一做 forbidden 字段/子串扫描（现仅 candidates 与
   Start）。
8. **屏障只靠文字背书**：`vnext/deploy/config/session.json` 无任何测试读取，"权限示例不自动授予
   真实用户"目前只有 README 文字；`extra=forbid` 只在 schema 层断言，缺 HTTP 层多余字段 → 422 用例。
9. **OpenAPI 基线**：`test_http_openapi.py` 的精确路径断言取自同一 commit 的源常量，无独立字面量
   基线；`test_production_wiring.py` 的路由子集断言（3/7）与 OpenAPI owner 重复。
10. **job registry 精确集合**：`test_production_wiring.py:80-84` 只遍历
    `preview_job_definitions() + submit_job_definitions()`，多注册一个 Archive job 不会 fail；
    registry 由 `http/runtime.py:188-191` 从两个命名列表构造，属性近乎结构性，但断言 key 集合相等的
    成本是一行，建议加上。
11. **Plan §3 允许的 helper 迁入未做**：`tests/test_archive_compose_e2e.py:14-24` 跨模块 import
    两个 test 私有 helper（第三个 consumer 已出现）。要么按 Plan 迁入
    `tests/support/compose_gate_harness.py`，要么在 handoff 记录不迁理由。

## 4. 非阻断观察

- `http/schemas/archive.py:369` 用 `old_baseline_head_version + 1` 与
  `plan.selected_repository_commit_id` 重建 Result 的 baseline 字段。与 `start.py:125,288-290` 的 CAS
  语义一致，双 actor 运行实测 `result.baseline_head_version == head`；因 `BaselineNode` 不存 version，
  这是唯一可行来源。建议在该公式处写明不变量来源，避免第三处静默复制。
- `GET /v1/archive-audit-events` 的 `next_after_sequence` 在"恰好取满一页"时也会返回游标（含最后一
  页），属游标约定；建议在 DTO 注释说明，避免被当作"还有下一页"的强保证。
- `application/archive/queries.py:257-273` 先按 result id 全局读行、再用 plan 的 scope 过滤，属可接受
  的 404 不披露实现；该行为目前**没有**有效证据覆盖（见 P1-3）。

## 5. 关闭条件与复验命令

1. **P1-1**：DTO 收口 + `ArchiveRequestValidation`；`test_archive_http.py` 新增共享参数表覆盖五类
   输入与 409 稳定码（含 details）。
2. **P1-2**：`test_archive_compose_e2e.py` 改为双 actor 旅程 + 全部命名断言；删除 handoff 的 scope
   note。
3. **P1-3**：跨 scope 用例改为同一 control DB + 第二 scope session，暴露**已存在**的 result。
4. **P1-4**：handoff 与 Plan 回退 `p5_5d_s3_stage_exit: not_evaluated`、
   `next_step: P5-5D-S3-remediation`。
5. **P2-1/P2-2**：给出实现或 design owner 的显式修订记录；**P2-3**：design owner 裁决 + 测试固定；
   **P2-4/P2-5/P2-8/P2-9**：补断言；**P2-6**：provenance 四项重采；**P2-7**：数字与表述更正。
6. 修复改变 `vnext/**` 后必须重算 source-tree/锁/Compose digest、fresh build、重跑 focused gate +
   §6 全量 conjunction（0 skipped，含新双 actor 旅程）+ 五包 static；不得沿用 `a6720238d6` /
   `a05b5de49b67` 续签；S4 不得绑定当前候选，且须在独立 re-review 之后启动。

复验命令（与本次评审一致）：

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
GATEWAY_COMPOSE_GATE_PROJECT_NAME=<proj> \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

## 附录 A：两轮原始编号映射

| 合并编号 | 第一轮（A） | 第二轮（B） | 说明 |
| --- | --- | --- | --- |
| P1-1 | F2 | P1-1 | 两轮独立复现同一缺陷与同一修复方案 |
| P1-2 | F1 | P1-2 | A 提供真实双 actor 运行；B 提供占用/唯一索引静态追溯 |
| P1-3 | — | P1-3 | B 提出；A 复核成立并采纳（定级 P2 → P1） |
| P1-4 | — | P1-4 | B 提出；A 复核 S2 先例与 Plan §1 后采纳 |
| P2-1 | F3 | P2-1 | 一致 |
| P2-2 | F4 | P2-2 | 一致；B 的 `action` 变体更强 |
| P2-3 | — | P2-3a | B 提出；A 复核后定为决策项 + 测试固定（P3 → P2） |
| P2-4 | — | P2-4 | B 提出，A 复核成立 |
| P2-5 | — | P2-5 | B 提出，A 复核成立 |
| P2-6 | F5 | P2-7 | 一致 |
| P2-7 | F7 + F6(部分) | P2-8 | 一致 |
| P2-8 | — | P2-9 | B 提出，A 复核成立 |
| P2-9 | F10 后半 | — | A 提出（Design §9 owner 缺口 + §5.2 非对称） |
| P3-1 | F10 前半 | P2-3b | 一致 |
| P3-2/3/4 | F9 | P3 对应项 | 一致 |
| P3-5…P3-8 | 部分 | P3 对应项 | 以 B 的枚举为主 |
| P3-9…P3-11 | F8 / 观察 | P3 对应项 | 一致 |
| 观察 | 观察 | — | A 提出（`old+1`、游标约定） |

## 附录 B：原始证据

### B.1 进程内 HTTP 探针（`TestClient` + `tests/support/archive_fixtures.py`）

```text
bad digest                     → 500 INTERNAL_ERROR
limit=0 / 101 / -1             → 500
after_sequence=-1              → 500
REVOKE + reason=null           → 500
201 confirmation_refs          → 500
declared Content-Length 300KiB → 413 REQUEST_TOO_LARGE
chunked 300KiB（无 CL）        → 201（接受）
duplicate "reason" key         → 201
duplicate "action" key         → 409 ARCHIVE_AUDIT_VERSION_CONFLICT（按 REVOKE 处理）
stale expected_sequence        → 409 + details{expected:0,actual:1}
same key + different body      → 409 IDEMPOTENCY_CONFLICT
201 candidates                 → 409 ARCHIVE_SCOPE_LIMIT_EXCEEDED
missing Idempotency-Key        → 422 REQUEST_VALIDATION_FAILED
duplicate confirmation refs    → 409 ARCHIVE_CONFIRMATION_REQUIRED（design §8.2 将重复引用列在 422）
```

### B.2 双 actor Compose 旅程（本轮实跑）

镜像：`gateway-p5-5d-review-dual-backend` = `sha256:704b5a29b51b…`（重新 build），
project `gateway-p5-5d-review-dual`，`GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local`；
运行时长 ~140s，1 passed；`compose down -v` 已清理。完整输出见 P1-2 引用块。

### B.3 源树摘要与 recipe（§6.3 要求"路径数量、算法与输出"）

- recipe（本轮）：`cd <src> && find . -name '*.py' -type f | LC_ALL=C sort | xargs sha256sum |
  sha256sum`。
- 结果：镜像 `/app/backend/src` 与 HEAD `vnext/backend/src` 均为
  `a25bab581a1958d320bd7a7a5c2110bb5a80fcf7287a589ecb6d587a08024843`（245 文件）。
- 另一轮评审给出的 `c824ecf8…`（同为 245 文件）与本值不可比——差异来自路径前缀是否参与外层摘要。
  closure 前必须固定一条 recipe 并把"文件数 + 算法 + 输出"写入 handoff。
- 另一轮评审另算了 tracked `vnext/**` 级 digest（905 文件，`1a740d76be2575abfd7bb52e9216a91b6c01c7042c0f625801aad2752b9e945e`）；
  该值本轮未复算，修复轮须用统一 recipe 重算后写入 handoff。

### B.4 代码事实索引（用于复核各条 finding）

- workspace scope 含 actor：`domain/workspace/policies.py:27-32`；OPEN 唯一索引
  `infrastructure/control_db/migrations.py:425-428`；`sqlite_workspace.py:65-83`。
- 占用释放：`application/submission/review.py:39-45`；`application/archive/start.py:401-432`；
  repository occupancy 在 `application/submission/finalize_transaction.py:119` 删除。
- 错误码不一致：`application/archive/audit.py:132,134,141` 对 `application/archive/start.py:147,153`。
- job registry：`http/runtime.py:188-191`。
- harness：`tests/support/http_workspace_harness.py:864-865`（每次新建 DB）、
  `tests/support/workspace_fixtures.py:31-32`（`del context`）。

本次仅新增/合并本报告，不代签 handoff，不修复实现，不执行 commit、部署或 Repository effect。
