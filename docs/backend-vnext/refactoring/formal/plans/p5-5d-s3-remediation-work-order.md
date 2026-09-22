# P5-5D-S3 Remediation Work Order

日期：2026-09-22。依据：[S3 Independent Review（合并版）](p5-5d-s3-independent-review.md)。
对象：P5-5D-S3 交付方（Backend Archive HTTP / Deployment owner）。

执行前须知：

- 权威状态：`p5_5d_s3_stage_exit: pass` 已被评审否定，**不得**在修复轮内重新自签；完成本单后只提交
  `pass_recommended` 并请求独立 re-review。
- 允许路径：沿用 [execution plan](p5-5d-archive-execution-plan.md) §3 的 S3 行
  （`http/routes/archives.py`、`http/schemas/archive.py`、`http/orchestration/archive.py`、
  `http/dependencies.py`、`http/wiring.py`、`http/errors.py`、`application/archive/*`、
  `domain/archive/ports.py`、`infrastructure/control_db/sqlite_archive.py`、
  `vnext/deploy/config/session.json`、`vnext/deploy/README.md`、`tests/test_archive_http.py`、
  `tests/test_archive_compose_e2e.py`、`tests/test_http_*.py`、`tests/test_production_wiring.py`、
  `tests/test_backend_readiness.py`、`tests/test_architecture.py`、
  `tests/support/compose_gate_harness.py`）。fixture/harness 改动（`tests/support/*.py`）按 Plan §3
  须在 handoff **逐项列明**，不得按 `tests/**` 放行。新增文件或超出该行须在 handoff 显式记录预算
  扩展理由。
- 禁区：其他四个包、全部 `uv.lock`/`pyproject.toml`、Dockerfile/构建传输、capability 私有实现、
  History、Operations Runtime 业务扩展；不得新增 Archive worker/job、锁表、candidate 表、outbox、
  broker/sidecar、Repository mount 或 write adapter。
- 每个任务的"验收"都要求**可失败性**：新增/修改的测试必须在修复前失败（留证据），修复后通过。

## T1 — P1-1：HTTP 校验边界 500 → 422

**目标**：任何 caller 可修复的输入都返回 422 `REQUEST_VALIDATION_FAILED`（或已定义的 409），
不再出现 `INTERNAL_ERROR`；`GET /v1/archive-audit-events` 的 query 参数、confirmation 的 action 相关
reason 必填性、Start 的 ref 数组上限与重复引用全部在 DTO 层收口。

**位置**：`application/archive/errors.py`、`application/archive/contracts.py`、
`application/archive/queries.py:206`、`application/archive/audit.py:92`、
`http/schemas/archive.py:105,131-132,401-417`、`http/routes/archives.py:188-193`、
`http/orchestration/archive.py:236-270`。

**改动**：

1. `application/archive/errors.py` 新增：
   `class ArchiveRequestValidation(ArchiveApplicationError): stable_code = "REQUEST_VALIDATION_FAILED"`
   （带 `reason: str`）。现有 `map_domain_exception` 的 `SubmitApplicationError` 兜底分支
   （`http/errors.py:299-311`）会自动映射为 422，**不要**新增映射表项。
2. `contracts.py` 中面向 caller 值的 validator 改抛 `ArchiveRequestValidation`：
   `validate_utf8_id` / `validate_utf8_reason` / `validate_archive_digest` / `validate_non_negative_int` /
   `validate_archive_sequence` / `validate_archive_confirmation_reason`。
   内部不变量检查（`compute_*_digest`、`compute_start_request_fingerprint` 里的同一批调用）保持现状，
   由 DTO 先行拦截；不得把"由已存事实推导出的矛盾"改成 422。
3. `http/schemas/archive.py`：
   - `AppendArchiveConfirmationRequest` 加 `model_validator(mode="after")`，调用
     `validate_archive_confirmation_reason(self.action, self.reason)`（即接上现在的死代码
     `validate_confirmation_reason_field`；`REVOKE` + `null` 必须在 DTO 层被拒）。
   - `StartArchiveRequest.confirmation_refs` / `anomaly_resolution_refs` 加
     `Field(default_factory=list, max_length=ARCHIVE_MAX_AUDIT_REFS)`，并加唯一性校验
     （`subject_digest` 或 `(subject_digest, sequence)` 重复即 422，符合 Design §8.2 "重复引用"）。
   - 删除无引用的 `validate_utf8_reason_field`（`validate_confirmation_reason_field` 保留并被 2 调用）。
4. `http/routes/archives.py:188-193`：
   - `subject_kind: Annotated[ArchiveSubjectKindLiteral, Query()]`（FastAPI 原生 422）；
   - `subject_digest: Annotated[ArchiveDigest, Query()]`；
   - `after_sequence: Annotated[int, Query(ge=0)] = 0`；
   - `limit: Annotated[int, Query(ge=1, le=ARCHIVE_AUDIT_EVENTS_MAX_LIMIT)] = 100`
     （常量从 `application.archive.queries` 导入，避免复制 100）。
   相应简化 `list_audit_events_operation` 的 `subject_kind` 解析（保留一层防御性转换即可）。
5. `tests/test_archive_http.py` 新增共享参数表（HTTP DTO 与 Application validator 同表、以 §3.3 byte
   规则为唯一期望），至少覆盖：
   - `subject_digest` 非法、`limit` 0/101/-1、`after_sequence` -1、`REVOKE` + `reason: null` 与缺键、
     201 个 `confirmation_refs`、重复 refs、非 string 的 `reason` / `expected_sequence`、
     非法 surrogate、多余字段。
   - 409 稳定码断言：`ARCHIVE_AUDIT_VERSION_CONFLICT`（含 `details{expected,actual}`）、
     `CANDIDATE_SET_CONFLICT`、`ARCHIVE_SCOPE_LIMIT_EXCEEDED`、`IDEMPOTENCY_CONFLICT`。
   - 429 参数化到三条写路由（`confirmations` / `anomaly-resolutions` / `archives`）。
   - cross-actor replay：另一位 actor 用他人 confirmation key + 完全相同 body → 409
     `IDEMPOTENCY_CONFLICT`；同一 Start key 由另一位授权 actor 重放 → 成功 replay 且 `archived_by`
     保持原 `accepted_by`（Design §5.2 的刻意非对称）。

**验收**：评审 B.1 表中的 5 类 500 全部变 422；新增用例在修复前失败、修复后通过；无新增 500 路径。

**验证**：见 §复验 E1。

## T2 — P1-2：Compose 双 actor 旅程（Plan §4 屏障）

**目标**：`test_archive_compose_e2e.py` 覆盖"两位 actor、两份同 base 成功 Submission、归档先提交者、
后提交者 CLOSED_NOT_ARCHIVED、全部 Workspace release、下一轮 Preview 用新 base、restart 后 Head 不变
且 Result/audit 可读"。

**位置**：`tests/test_submit_compose_e2e.py:400-490`（journey helper）、
`tests/test_archive_compose_e2e.py` 全文。

**改动**：

1. `_run_accept_to_submission_read_journey` 增加 `token: str = SESSION_TOKEN` 参数（与已接受的
   `journey_key_prefix` 同类最小 seam），内部 `_auth_headers(token=token, idempotency_key=…)`；同时启用
   `journey_key_prefix`（现在三个 caller 全用默认值，属死参数）。
2. `test_archive_compose_e2e.py` 改造为（顺序不可颠倒，占用语义见评审 P1-2 追溯）：
   - 旅程 A：actor-1（`SESSION_TOKEN`）上传/preview/submit → 提交 A → 用 reviewer session approve A；
   - 旅程 B：actor-2（`REVIEWER_TOKEN`，已具备 `workspace_read`/`upload_submit_workspace`/
     `preview_workspace`）以 `journey_key_prefix="compose-b"` 再走一次 → 提交 B → approve B；
     B 会得到**自己的 workspace**（OPEN 唯一索引含 `owner_actor_id`），不得复用 A 的 workspace；
   - 断言 `GET /v1/archive-candidates` 恰有 A、B 两个同 base 候选；记录两次提交后的技术 main，
     断言 main == 后提交者（B）的 commit；
   - `POST /v1/archive-plan-preview`（selected=A）→ 恰一个 `APPROVED_SIBLING_EXCLUDED` 且
     `sibling_submission_id == B`、`can_start is False`、`workspace_releases` 含两个 workspace；
   - `POST /v1/archive-confirmations`（selection subject）+ `POST /v1/archive-anomaly-resolutions`
     （anomaly subject，`issue_code=APPROVED_SIBLING_EXCLUDED`）→ 再次 preview `can_start is True`；
   - `POST /v1/archives` → 断言 `dispositions` = A `ARCHIVED_BASELINE` + B `CLOSED_NOT_ARCHIVED`、
     `released_workspace_ids` 覆盖两个 workspace、`baseline_head_version == 原 + 1`、
     `baseline_commit_id == A 的 commit`；
   - 归档后 main 与窗口前相同；`GET /v1/archives/{id}` 200；
   - **观察窗口**（Plan §6.2）：窗口开始前等待无 active Attempt，记录 main 与 Repository commit 集合
     （用既有 repository read harness），窗口内只做 Archive/audit/只读 preview，再读一次必须完全相同；
     同时断言 control DB 的 Operation 集合无新增 Archive operation；
   - **新 base 下一轮**：用归档后的 Head 再跑一次 preview（或 submit 前置 stage），证明新 base 可用；
   - restart `backend`/`worker` 后（`_wait_http_ok`）断言 Head 不变、Result 与 audit 仍可读。
3. 删除 handoff 的 "Compose journey scope note"，或改写为"同 actor 未归档重提被占用阻塞"。
4. 迁移或记录：`test_archive_compose_e2e.py:14-24` 跨模块 import 两个 test 私有 helper，现已有第三个
   consumer；按 Plan §3 最小迁入 `tests/support/compose_gate_harness.py`，或在 handoff 记录不迁理由。

**验收**：新旅程通过且 0 skipped；把 `released_workspace_ids` / `dispositions` 断言临时删掉必须失败
（可失败性自检）。

**验证**：见 §复验 E2。

## T3 — P1-3：跨 scope 拒绝证据重写（同一 DB）

**目标**：让"跨 scope/跨 Repository 不披露"这条屏障的证据真的能失败。

**位置**：`tests/test_archive_http.py:327-347`、`tests/support/http_workspace_harness.py`
（`create_workspace_http_environment`，当前固定
`FixedScopeResolutionPort(repository_id="repo-1", …)`，且其 `resolve` 直接 `del context`）。

**改动（推荐 A）**：在同一 control DB 内使用**真实** `ProvisionedScopeResolution` +
两份 `seed_provisioned_mappings`（不同 device/project → 不同 repository），把已存在的 archive result
暴露给第二 scope 的 session，断言 404 `RESOURCE_NOT_FOUND`；再补一条同 scope 不同 actor 的读取用例
（应 200）。harness 需要新增可选参数以便注入 per-scope 解析（变更限于该 harness 文件；属 fixture 改动，
按 Plan §3 在 handoff 逐项列明）。
**改动（备选 B）**：给 harness 增加 scope-aware 解析端口（按 `(device, project)` 返回不同
`ResolvedScope`），同样必须指向同一 DB。

**可失败性证据（必做）**：临时注释 `application/archive/queries.py:263-268` 的 scope 过滤，确认用例
**失败**（返回 200），恢复后通过；在 handoff 记录该实验（不进入提交内容）。

**注意**：不要再新增"另一个全新 DB 的 env"作为跨 scope 证据；`OTHER_SCOPE_BEARER`
（`test_archive_http.py:40`）当前是死常量，接入本任务。

## T4 — P1-4：authority 回退

**位置**：`p5-5d-s3-handoff.md`（Authority gate snapshot、Independent countersign）、
`p5-5d-archive-execution-plan.md` §1 与 §4 S3 段。

**改动**：

- `p5_5d_s3_stage_exit: not_evaluated`；`next_step: P5-5D-S3-remediation`；
  countersign 写 `review: findings_open` 并链接本 work order 与合并版评审。
- Plan §1 status 行与 §4 S3 段删除 "S3 pass（delivery complete）"/`p5_5d_s3_stage_exit: pass`，
  改为 "S3 remediation in progress；P1-1…P1-4 未关闭"。
- 只有修复 + 独立 re-review 通过后，才由评审方（非交付方）把该字段改回 `pass`。

## T5 — P2-1 / P2-2：请求体上限与重复 JSON key

**目标**：Design §3.3 的 256 KiB 是**实际字节**上限（含 chunked/无 `Content-Length`），且"读前"生效；
重复 JSON key 不得静默覆盖（§8.1）。

**推荐实现（都在预算内）**：

1. 在 `http/dependencies.py` 增加一个只作用于四条 Archive POST 路径的 ASGI middleware：包装
   `receive` 累加字节，超过 `ARCHIVE_MAX_REQUEST_BYTES` 立即返回既有错误信封
   `{"code":"REQUEST_TOO_LARGE","message":…}`（413），不再继续读取；`http/wiring.py` 注册。
   该层不解析 body，因此不改变 OpenAPI schema。
2. 在 `http/orchestration/archive.py` 增加一个依赖：`data = await request.body()`（此时 ≤ 上限且被
   Starlette 缓存，FastAPI 随后复用同一份），用
   `json.loads(data, object_pairs_hook=<reject duplicates>)` 检测重复 key，命中返回
   `422 REQUEST_VALIDATION_FAILED`。四条 POST 路由统一挂载。
3. 删除或收敛现有 `ensure_request_body_within_limit`（`orchestration/archive.py:59-70`）：不再只看
   `Content-Length`，也不要静默接受负数/非法头。

**替代方案（需 design owner 接受）**：明确声明只约束 declared `Content-Length`，则必须拒绝缺失/非法
头，并同步修订 Design §3.3/§8.1 与路由 `responses`，测试按修订后的契约写。

**验收**：declared 300 KiB → 413；chunked 300 KiB（无 `Content-Length`）→ 413（当前是 201）；
重复 `reason`/`action` key → 422（当前 201/409）；四条 POST 路由全部覆盖；GET 路由不受影响。

## T6 — P2-6：Provenance 四项重采

在修复后的**同一次** fresh build + conjunction 运行中采集，写入新 handoff：

1. `git rev-parse HEAD` + `git status --porcelain`（`vnext/**` 必须干净）+ `clean/dirty` 标记。
2. **统一 recipe** 的 source-tree digest（§6.3 要求"路径数量 + 算法 + 输出"）：

   ```bash
   cd <repo-root> && git ls-files 'vnext/**' | LC_ALL=C sort | \
     while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum
   ```

   同时记录文件数。镜像侧等价性核对用：

   ```bash
   docker run --rm --entrypoint sh <backend-image> -c \
     'cd /app/backend/src && find . -name "*.py" -type f | LC_ALL=C sort | xargs sha256sum | sha256sum'
   cd vnext/backend/src && find . -name '*.py' -type f | LC_ALL=C sort | xargs sha256sum | sha256sum
   ```

   两者必须相等；把两侧数值与 recipe 一并记录（此前两轮评审得出不同数值即因 recipe 未统一）。
3. 五个 `uv.lock` SHA、`compose.yaml` SHA 与运行 project name；`PREBUILT` 使用前提。
4. **运行中**每个场景的 container ID + `.Image`（在栈仍在运行时采集，不得只 inspect tag）；建议在
   `tests/support/compose_gate_harness.py` 加一个 helper，在 journey 中直接落盘。
5. 每服务的不可变 image ID、revision/source-tree 标签（两个 backend/worker 镜像当前
   `org.opencontainers.image.revision` 为空，需补标签）、构建时间与退出码。
6. `repository-service` 复用理由：`823661134e..HEAD` 对
   `vnext/repository_service|repository_client|repository_contracts|shared_kernel` 零改动，
   镜像 label revision `d19b3efcab`；或按 §6.2 显式重跑 `build-repository-service-image.sh`。

## T7 — P2-7：handoff 数字与表述更正

- `test_production_wiring.py` 计 19 passed（handoff 写 18）。
- 删除/更正 "main commit unchanged in HTTP and compose tests"：HTTP 侧只有
  `assert "repository_id" not in body`，无 main 可比；零 Repository effect 仅由 compose 侧（含 T2 的
  观察窗口）证明。
- 零写观察窗口的表述按 T2 实际断言（main + commit 集合 + 无新增 Archive operation）更新。

## T8 — P3 清单（逐项处理或记录不处理理由）

1. 错误映射分支测试固定（并入 T1）。
2. 死代码：`schemas/archive.py:68 ArchiveCandidateRefRequest`（删）、
   `schemas/archive.py:401 validate_utf8_reason_field`（删）、
   `test_archive_http.py:40 OTHER_SCOPE_BEARER`（T3 接入）；`validate_confirmation_reason_field` 保留。
3. 死参数 `journey_key_prefix` 由 T2 启用。
4. `schemas/archive.py:433` 的 `# type: ignore[arg-type]`：把
   `application/archive/queries.py:68` 的 `disposition: str` 收敛为闭合枚举/Literal 后移除抑制。
5. `test_archive_http.py:399-400` 复用 ID 表前两行做 idempotency-key 用例可保留；
   `:411` 的 `validate_utf8_id(...) if … else None` 表达式语句删除。
6. Preview 只读证明改用 `tests/support/archive_fixtures.py:71 assert_archive_durable_state_unchanged`
   或补 `archive_disposition_records` 计数。
7. 泄漏扫描扩展到七个响应（forbidden 字段/子串统一表）。
8. `vnext/deploy/config/session.json` 加一条读取断言（权限示例不自动授予），并补 HTTP 层
   `extra=forbid` → 422 用例。
9. `test_http_openapi.py` 增加独立字面量基线（不取自源常量）；`test_production_wiring.py` 的路由子集
   断言可保留或移除（与 OpenAPI owner 去重）。
10. `test_production_wiring.py` 断言 job registry key 集合精确等于 `preview ∪ submit`。
11. helper 迁移按 T2 第 4 步处理。

## 复验（修复候选必须全绿）

```bash
# E1 focused gate
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py

# E2 fresh build + 全量 conjunction（0 skipped）
GATEWAY_COMPOSE_GATE_PROJECT_NAME=<new-project> \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py

# E3 五包 static（backend 必须含新增/修改测试）
for pkg in backend repository_service repository_client repository_contracts shared_kernel; do
  (cd vnext/$pkg && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

改变 `vnext/**` 后必须重算 source-tree/锁/Compose digest 与镜像 ID；不得沿用
`a6720238d6` / `a05b5de49b67` 续签。

## 完成定义（Definition of Done）

1. P1-1…P1-4 全部关闭，且每条附"修复前失败 / 修复后通过"的证据。
2. P2-1…P2-9 关闭，或对需要 design owner 决策的条目（P2-1、P2-2、P2-3）给出显式决策记录并同步测试。
3. P3-1…P3-11 处理或逐条记录不处理理由。
4. E1/E2/E3 全绿（E2 0 skipped），provenance 按 T6 重采并写入新 handoff。
5. 新 handoff 状态为 `delivery complete`（`pass_recommended`），**不**自签
   `p5_5d_s3_stage_exit`；T4 的 `not_evaluated` 保持到独立 re-review 通过。
6. 提交前 `git status` 中不得残留评审探针或未记录文件；`vnext/**` 无未记录差异。
