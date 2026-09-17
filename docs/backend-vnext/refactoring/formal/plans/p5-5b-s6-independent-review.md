# P5-5B-S6 Independent Review (Round 1)

状态：**FAIL — S6 不可关闭；需 S6 remediation round 后再审**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target and decision

```yaml
stage: P5-5B-S6-readiness-shutdown-settings-deployment-wiring
implementation_candidate: ff9ea77cfe0dcf1b7f807fec2374c7b3bb8c170a
review_scope: wiring correctness + owner-test evidence + handoff claims
decision: fail
findings_open:
  - S6-R1 baseline canonical digest port 每次调用抛 FrozenInstanceError（blocker）
  - S6-R2 baseline canonical digest 与 preview canonical digest 不同一构造（guard 永久失效）
  - S6-R3 runtime 复制 preview 的 canonical bundle closure 且已漂移（潜伏 503）
  - S6-R4 handoff 三项 invariant 断言无对应证据
  - S6-R5 compose e2e 静默 fallback 到旧 repository image
  - S6-R6 backend 无 stop_grace_period / drain 预算
  - S6-R7 新增测试存在恒真断言与重复 owner
  - S6-R8 重复实现与死代码
container_gate_for_current_head: deferred（handoff 声明，reviewer 未重建镜像）
s7_entry: blocked
```

Review 方法：只读审阅 `ff9ea77c` 全部 production diff 与 owner tests；另行执行 3 个 throwaway probe
（构造后已删除，不入库，见 §4）。未重跑 handoff 已报告的 focused gate，未重建镜像。

## 2. Findings

### S6-R1 [Blocker] `HttpBaselineCanonicalDigestPort` 每次调用必抛 `FrozenInstanceError`

位置：`vnext/backend/src/gateway_backend/http/runtime.py:605`

```python
def get_baseline_canonical_digest(self, *, repository_id: str, baseline_head: BaselineHead) -> str:
    del baseline_head.business_baseline_node_id, baseline_head.baseline_head_version
```

`BaselineHead` 是 `@dataclass(frozen=True, slots=True)`
（`domain/workspace/models.py:65-77`），对 frozen dataclass 的属性 `del` 必然抛
`dataclasses.FrozenInstanceError`。该异常不是 `ValueError`，不被本方法内的
`except ValueError → ApiError(503)` 捕获，也不被 `submit_acceptance.py` 的 `try/except` 捕获，
最终落到 `http/errors.py` 的兜底 `Exception` handler（`INTERNAL_ERROR` / 500）。

影响：`submit_acceptance.py:237` 对**每个非 replay 的新 key**调用该 port（T1 之前），因此生产接线
下所有新 `POST /v1/workspaces/{id}/submit-attempts` 都返回 500；`NO_CANONICAL_CHANGE`、
T1 CAS、occupancy、worker submit 全部不可达。仅 same-key replay 分支不调用该 port。

为什么现有 gate 没发现：全仓库没有任何测试**调用**该 port。唯一引用是 type 断言
（`tests/test_backend_readiness.py:122`：`assert type(...baseline_canonical_digest) is HttpBaselineCanonicalDigestPort`）；
HTTP 用例走 `tests/support/http_workspace_harness.py` 的 fake port；compose smoke 只覆盖
startup/restart/workspace POST。

复现（throwaway probe，最小形态）：

```python
port = HttpBaselineCanonicalDigestPort(provider_factory=lambda rid, commit: provider)
port.get_baseline_canonical_digest(repository_id=REPO_ID, baseline_head=BASELINE_HEAD)
# FrozenInstanceError: cannot delete field 'business_baseline_node_id'
#   runtime.py:605 in get_baseline_canonical_digest
```

要求：

1. 删除该 `del` 行（若目的是说明 digest 不依赖 node id/head version，应改为显式注释或不使用参数）。
2. 补一个**调用真实 port** 的 owner test：成功路径（materialize + bundle 得到 digest）与失败路径
   （provider 抛错 → `503 DEPENDENCY_UNAVAILABLE`）。仅 type 断言不构成 owner。
3. remediation 后必须重跑并记录 `tests/test_backend_readiness.py`、`tests/test_production_wiring.py`
   与至少一个真实 accept 行为用例，证明新 key 的 accept 不再 500。

### S6-R2 [High] baseline digest 与 preview canonical digest 不在同一构造，`NO_CANONICAL_CHANGE` 永久失效

设计 §6.1 步骤 4 与契约 §5 要求：当 Preview-bound canonical business digest 与 current business
base 相同 ⇒ 在 Attempt 前返回 `409 NO_CANONICAL_CHANGE`，不构建 import artifact、不调用 Repository。
实现依赖 `preview_canonical_business_digest(preview_result) == port.get_baseline_canonical_digest(...)`
（`application/submission/accept.py:101-107`）。

实际两侧构造：

| | preview canonical digest | S6 port 产出 |
|---|---|---|
| 来源 | `preview_jobs.py:1186-1198`（assemble checkpoint `digests.bundle_digest`） | `runtime.py:531-588` |
| `bundle_profile` | `MULTI_PAIR`（FULL）或 `SINGLE_PAIR`（MODIFIED_ONLY），`preview_jobs.py:1109/1128` | `SINGLE_PAIR`（runtime.py:564） |
| `inputs` | baseline/initial/modified（FULL）或 baseline/modified | `("baseline","Baseline")`, `("current","Current")`（runtime.py:565-568） |
| `pairs` | `baseline_to_initial` + `initial_to_modified` / `initial_to_modified` | 单 pair `baseline-identity`（`_PAIR_IDENTITY`, runtime.py:159/457-530） |

`compute_bundle_digest` 的 preimage（`capabilities/bundle_assembly/_digest.py:44-101,104-125`）显式包含
`bundle_profile`、`inputs[].role/display_name/input_index`、`pairs[].pair_id/…`。因此两侧 preimage
在任何内容下都不同 ⇒ 该等式**任何输入都不成立**（SHA-256 碰撞除外），
`assert_no_canonical_change_after_baseline` 在生产中是死分支。

注意该 guard 的假阴性方向是「接受本应 409 的 no-op submit」：会继续构建 `RepositoryImportArtifact`、
提升 source artifact retention、调用 Repository（契约 §5 明确禁止）。S2 的 T1 matrix 用例只覆盖
fake port 注入 `baseline_port.digest = preview_canonical_business_digest(seed["preview_result"])`
（`tests/test_submit_http.py:279`），不覆盖生产构造。

这意味着 base-side canonical digest 的推导在 design 中未冻结（owner 未定义「current business base
canonical digest」如何由 baseline commit 重算）。**先改 design/契约，再改实现**，不得由 S6 自行选择
第三种构造。要求：

1. design/契约明确 base digest 与 preview canonical digest 必须同构（同一 bundle 构造：相同 profile/
   inputs/pairs 语义，或明确改为非 bundle 的 canonical content digest 并同步改 accept 比较两侧）。
2. 实现必须复用 preview 侧的唯一 owner，而不是第三份 compare→risk→surface→bundle 实现（见 S6-R3）。
3. 新增行为证据：no-op 输入 ⇒ `409 NO_CANONICAL_CHANGE` 且零写入；非 no-op ⇒ 正常进入 T1。
   该断言必须在真实 preview + 真实 port 上成立，而不是双方 fake。

附带事实（probe 记录，供 owner 判定是否属本阶段）：当上传内容与 baseline 完全相同时，
preview assemble 直接 `BundleAssemblyError("DUPLICATE_SOURCE_ARTIFACT_REF")`
（`capabilities/bundle_assembly/_assembly.py:473-474`），即用户拿到的是 preview operation 失败而不是
`409`。契约 §9 的 `DROP_FROM_STORAGE` no-op 场景（source 不同、canonical content 相同）不受此影响，
但该差异需要 owner 明确谁负责。

### S6-R3 [High] runtime 复制 preview 的 canonical bundle closure 并已漂移

`runtime.py:354-456` 的 `_surface_artifact_closure` 与 `application/preview_jobs.py:965-1094` 的同名函数
（bundle 布局 owner，130 行）是复制关系，且**在引入时就已漂移**：

- runtime 版缺少 `table.ordered_extension` 的 `{prefix}/ordered/{table}/{key}.json` 绑定；
- runtime 版缺少 `surface.projections` 的 `{prefix}/projections/...`（projection/risk-summary/diagnostics）绑定；
- runtime 版用 `collect_surface_refs(surface)` 做覆盖断言，而 `bundle_assembly/_refs.py:40-101`
  的 `_surface_refs` **包含**这两类 ref ⇒ 一旦 surface 出现这两类 ref，抛
  `ValueError("surface ref is not mapped for bundle closure")` → 被 port 转成
  `503 DEPENDENCY_UNAVAILABLE`，即新 accept 全量失败（fail-closed）。

可达性：`ordered_extension.records` 非空时 `surface_assembly/_assembly.py:457-494` 会写入
`ordered_records_ref`；该路径由 table rule 的 ordered policy 触发
（`capabilities/table_rules/registry.py:205` 存在 `GID_NO_V1`）。当前 v1 生产 ruleset 未传
`table_policies`（`comparison/pair_planning.py:321` 默认 policy），`projections` 目前恒为 `()`
（`surface_assembly/_assembly.py:161`），因此是潜伏缺陷而非现网故障——但它是 canonical 布局的第二份
实现，任何后续 ordered policy/ruleset 接线会立即变成 503。

要求：删除复制，复用唯一 owner（导出 `preview_jobs._surface_artifact_closure` 或把映射上移到
`capabilities/bundle_assembly`），并加一个覆盖「含 ordered/projection ref 的 surface」的用例，
证明两侧产出相同的 bindings。

### S6-R4 [Medium] handoff 三项 invariant 断言无证据支撑

| handoff 断言 | 实际 | 证据 |
|---|---|---|
| 「worker 与 HTTP 共用 `build_workspace_job_registry()`」 | worker 只对**一次性构造后丢弃**的 registry 做断言，执行仍走 `submit_composition_bundle` 的 `definition_registry` | `bootstrap/operation_worker.py:347-355` vs `:309-310` |
| 「HTTP T1 preflight 与 worker 共用 decoder identity 快照」 | `assert_submit_job_registered` 只做 `resolve_runnable`，**不比较** `decoder_identity`；只有 preview 侧 `assert_preview_registry_ready` 做 identity 比较 | `application/submission/accept_transaction.py:85-93` vs `application/preview_registry.py:28-36` |
| 「production shutdown `/readyz` 503 + `/healthz` 200」 | 没有任何用例断言 shutdown 后 `/readyz` 返回 503；`test_production_shutdown_closes_admission_gate`（`tests/test_http_admission_shutdown.py:69`）手工 `gate.close()` 后仍断言 `/readyz == 200`，`test_production_lifespan_shutdown_marks_not_ready`（`:91`）只断言 `app.state` | `tests/test_http_admission_shutdown.py:69-108` |

另有 `test_production_wiring.py:67-72` 的 “combined registry step identity” 是
`registry.get(...)` 与 `submit_job_definitions()[0]` 比较——同一函数的输出对自身，属 tautology，
不构成 HTTP↔worker 一致性证据。

要求：要么实现真正的跨 composition identity 检查（HTTP registry 与 worker composition 的
definitions/decoders 对比，并纳入 startup gate），要么把 handoff 断言降级为实际证据的描述；
`/readyz` 状态迁移必须由 HTTP 层用例直接断言（例如在 lifespan 内注入一个受控探针，或在
`ready=False` 状态上直接调用 app）。

### S6-R5 [Medium] compose e2e 静默 fallback 到旧 repository image

`tests/test_submit_compose_e2e.py:124-141`：`docker compose build backend worker repository-service`
失败时，改为只 build `backend worker` 并 `up --no-build`，此时 `repository-service` 使用
`GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local`（handoff 记录：
2026-09-15 `b44a67a7fe62`）。

问题：该分支通过时，测试输出与真实三镜像 conjunction **不可区分**；这个 “pass” 因此只能作为
wiring smoke 证据，不能作为 current HEAD 的 repository-service 证据（handoff §Container provenance
已披露，但测试本身没有留下机器可读信号）。

要求：fallback 分支改为显式 `pytest.skip`/打标记（或至少 `print` image id + digest 到输出），
并断言 `docker compose images --format json` 中实际运行的 repository image id，避免把
fallback 运行误记为 conjunction pass。

### S6-R6 [Medium] backend 缺少 `stop_grace_period`，drain 预算不对称

compose 只给 worker 加了 `stop_grace_period: 180s`（= `graceful_drain_timeout_seconds`，合理），
backend 仍是 Docker 默认 10s。设计 §13.2 要求 shutdown 后「允许既有 read」；而 S6 后 accept 路径
新增了 baseline 全量 materialize + 多次 Repository 往返（`GATEWAY_BACKEND_REPOSITORY_TIMEOUT_SECONDS=30`，
S6-R2 若按当前实现保留则单次请求可能达分钟级），10s SIGKILL 会在请求中途终止进程。

要求：为 backend 明确 drain 预算（`stop_grace_period` 与 uvicorn graceful timeout 对齐，并说明
最长可接受在途请求），或在 handoff 中写明该边界与理由（含 S7 需验证的 nodeid）。

### S6-R7 [Low] 新增测试的恒真/非判别断言与重复 owner

- `tests/test_production_wiring.py:213-216`：`assert path.endswith(f"/refs/{encoded}") or "/refs/main" in path`
  不接受任何被测输入（`path` 由测试自己拼出，`or` 兜底恒真）；handler 内 `request.url.path.endswith(...) or encoded in ...`
  同样带 `or`。有效断言只剩返回的 commit id。
- `tests/test_submit_worker_process.py:169-307`（checkpoint barrier 参数化用例）：子进程是
  `python -c` 直接调用 `LeaseSession`，**不经过** `gateway_backend.bootstrap.operation_worker`
  模块入口，与 S5 的 `test_submit_worker.py` / `test_submit_recovery.py` 的 lease/checkpoint
  不变量 owner 重复；断言 `persisted_step.lease_expires_at < now-1s` 在子进程用 `now-60s` 注入时钟下
  **恒真**（非判别性），真正判别的是 `optimistic_version ∈ {1,2}`。
- `tests/test_backend_dockerfile_contract.py:65`：`assert "backend-internal-bearer:" in compose`
  在 secret 已声明但未被任何 service 引用时同样为真，只证明字符串存在；compose 断言整体为文本块
  匹配，只能证明「文本存在」而非「接线生效」。

要求：按仓库测试约定收敛——保留判别性断言（wire 精确 path/header、image id、跨进程 registry identity），
删除恒真断言；checkpoint barrier 若确需进程级证据，应驱动模块入口或说明与 S5 owner 的分工。

### S6-R8 [Low] 重复实现与死代码

- `runtime.py:318-352` `_submit_recovery_capability_lookup` 与
  `http/routes/operator_recovery.py:29-53` `_capability_lookup` 是同一映射的两份实现（同一请求路径内
  两份 lookup 并存，漂移风险：route 版把 `JobDefinitionLookupError` 映射为 `503 SERVICE_NOT_READY`，
  runtime 版直接向上抛）。
- `runtime.py:163-179` `FailClosedSessionPort` / `FailClosedScopeResolution` 已无任何消费者
  （S6 之前即已如此，但既然本阶段重写 composition，顺手删除成本几乎为零）。
- `settings.py:211`（`__all__`）把私有名 `_WORKER_FIXED_BUDGETS`（定义于 `:21`）导出供测试 import；
  `test_backend_settings.py:85-90` 的期望值取自同一模块，属同源比较；建议测试直接断言契约字面值
  （180.0/1/1）并保留 env/kwarg override 被拒的断言。

## 3. Not verified / deferred

```yaml
s6_focused_gates: 未重跑（采信 S6 handoff 报告：unit 28 passed、worker serial 3 passed、ruff/mypy pass）
compose_e2e: 未重跑（采信 handoff 1 passed；执行环境 docker/网络限制由 handoff 记录）
container_conjunction_gate: 未执行；S6-R5 的静默 fallback 使其证据强度进一步下降
five_package_static: 未执行（S6 声明 defer 至 S8）
docker_rebuild: reviewer 未重建；S6 触及 deployment boundary，最终 gate 仍须在 S8 于 candidate HEAD 重建
```

## 4. Probe evidence (throwaway, removed)

1. **FrozenInstanceError**：构造 `HttpBaselineCanonicalDigestPort` + `tests/support/preview_job_harness`
   的 fake provider，调用 `get_baseline_canonical_digest` → traceback 指向 `runtime.py:605`。
2. **no-op preview 行为**：把 harness 的 `MODIFIED_SQL` 替换为 `BASELINE_SQL`（上传内容 == baseline），
   跑 materialize → assemble → publish：
   ```
   BUNDLE STATUS: FAILED
   DIAGNOSTICS: ['DUPLICATE_SOURCE_ARTIFACT_REF']
   PROFILE: MULTI_PAIR
   ```
   （对照组 `MODIFIED_SQL` 默认值 → `READY`）
3. **preview 侧 bundle 形状**：assemble 阶段 `BundleAssemblyInput` 实测 `MULTI_PAIR`
   （`preview_jobs.py:1109`），与 S6-R2 表格中 port 侧 `SINGLE_PAIR` 对照。

三个 probe 文件均已删除，`git status` 无残留。

## 5. Required remediation (逐 finding)

```yaml
remediation_allowed_paths:
  - vnext/backend/src/gateway_backend/http/runtime.py            # S6-R1, S6-R2, S6-R3, S6-R8
  - vnext/backend/src/gateway_backend/application/preview_jobs.py # S6-R3（导出/上移 closure owner）
  - vnext/backend/src/gateway_backend/http/routes/operator_recovery.py # S6-R8（合并 lookup）
  - vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py # S6-R2（若比较两侧变更）
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py # S6-R4（若实现真实 identity 检查）
  - vnext/backend/tests/test_backend_readiness.py                 # S6-R1
  - vnext/backend/tests/test_production_wiring.py                 # S6-R1, S6-R4, S6-R7
  - vnext/backend/tests/test_submit_worker_process.py             # S6-R7
  - vnext/backend/tests/test_submit_compose_e2e.py                # S6-R5
  - vnext/backend/tests/test_backend_dockerfile_contract.py       # S6-R5, S6-R7
  - vnext/deploy/compose.yaml                                     # S6-R6
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-*.md     # handoff 断言修正
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md # S6-R2 design gap（需 owner/用户授权）
blocking_findings: [S6-R1, S6-R2, S6-R3]
non_blocking_findings: [S6-R4, S6-R5, S6-R6, S6-R7, S6-R8]
re_review_entry: R1/R2/R3 修复 + 新增 owner test 后，重跑 S6 focused gate 并重做独立复审
```

S6-R2 触碰 design 未定义语义（base canonical digest 推导），按执行计划 §S6「contract drift / reopen」
规则，需要 design owner 或用户显式裁定后再进入实现 remediation。
