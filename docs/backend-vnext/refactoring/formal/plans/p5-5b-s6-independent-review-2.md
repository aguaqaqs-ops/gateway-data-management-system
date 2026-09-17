# P5-5B-S6 Independent Review Round 2 (remediation 1bbc125d)

状态：**FAIL — R1/R2(MODIFIED_ONLY)/R3 已由独立探针实测关闭；FULL completeness 路径新增 blocker**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target and decision

```yaml
stage: P5-5B-S6-remediation-round-1
implementation_candidate: 1bbc125d99f7b4dd24fe97d0ff39b0cec10a1a25
parent_candidate: ff9ea77cfe0dcf1b7f807fec2374c7b3bb8c170a
round_1_review: docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-independent-review.md
decision: fail
verified_closed: [S6-R1, S6-R2-MODIFIED_ONLY, S6-R3, S6-R4, S6-R5, S6-R6, S6-R8]
findings_open:
  - S6-RR1 [Blocker] FULL completeness 下 base digest 计算确定性失败（accept 全量 503）
  - S6-RR2 [Medium] closure owner 测试用源码文本断言，非行为证据
  - S6-RR3 [Medium] read-only factory 类型洞仍在（本轮真实故障即由此漏过）
  - S6-RR4 [Low] ruleset_version 被接收后丢弃，与 design 文本不一致
  - S6-RR5 [Low] port 双重 except + 全量映射掩盖编程错误
  - S6-RR6 [Low] 生产 composition 无 202 成功路径测试（T1 路径仍未覆盖）
container_gate_for_current_head: deferred（沿用 handoff）
s7_entry: blocked
```

方法：只读审阅 `1bbc125d` 全部 diff；另跑 4 个 throwaway probe（构造后已删除，见 §4）实测
port 行为、preview↔port digest 等式与 FULL/MODIFIED_ONLY 分支。未重跑 handoff 已报告的 focused gate。

## 2. Verified closures（本轮实测）

**S6-R1 关闭（实测）**：`del baseline_head.*` 已删除，`HttpBaselineCanonicalDigestPort` 委托
`preview_jobs.compute_baseline_canonical_bundle_digest`。用真实 port + mock repository transport 调用
（`InputCompleteness.MODIFIED_ONLY`）返回 `sha256:3e84c25d…`，无 `FrozenInstanceError`。

**S6-R2 关闭（MODIFIED_ONLY，实测端到端）**：把 preview harness 的上传包内容置为与 baseline 相同
（canonical no-op），跑真实 materialize + assemble 得到 `bundle_digest`，再对同一 baseline 调用 port 侧
`compute_baseline_canonical_bundle_digest`：

```text
preview bundle digest (canonical no-op): sha256:e96d345b437b0237dfb1deb00603f72b3766c05cbf0b61f08a4b013d086de118
port base digest                      : sha256:e96d345b437b0237dfb1deb00603f72b3766c05cbf0b61f08a4b013d086de118
NO_CANONICAL_CHANGE would fire        : True
```

两侧现在共用 `_run_pair_pipeline` + `surface_artifact_closure` + `assemble_bundle`，pair specs / inputs /
indexes 与 `_assemble_preview` 逐字段一致（reviewer monkeypatch `assemble_bundle` 捕获两侧
`BundleAssemblyInput`，两种 completeness 均 `TOPOLOGY MATCH: True`，见 §4 probe 4），
比较语义因此成立。round-1 R2 的「不同构造」问题已消除（FULL 的失败是内容重复而非拓扑差异，见 S6-RR1）。

**S6-R3 关闭**：`surface_artifact_closure` 由 `preview_jobs` 导出，`runtime.py` 中约 300 行重复
pipeline/closure 已删除（782 → 413 行）；port 直接调用 owner。

**S6-R4 关闭（部分证据仍弱，见 S6-RR2）**：`test_production_lifespan_shutdown_marks_not_ready` 现在断言
lifespan 退出后 `/readyz == 503` 且 `/healthz == 200`；新增 `assert_submit_registry_decoders`
（registry 对照冻结常量，具有实际判别力）并纳入 `assert_workspace_registry_ready`，worker/HTTP 启动路径
同时受检。

**S6-R5/R6/R7/R8 关闭**：compose e2e fallback 显式 `pytest.skip` 并打印实际 image；`backend.stop_grace_period: 180s`
写入 compose 且被 contract test 断言；wire 断言的 `or` 兜底已删除（`request.url.path == path` 精确断言），
worker barrier 用例的非判别 lease 断言已删除，settings 断言改回契约字面值；`build_submit_recovery_capability_mapping`
统一 route/composition 两份 lookup，`FailClosedSession/Scope` 与 `__all__` 私有名清理完成。

**附加修复已核实**：`unit_of_work_factory(*, read_only=False)`。该缺陷真实存在——`submit_acceptance.py:123/194/282`
都以 `read_only=True` 调用该 factory，round-1 candidate 在这一步就会 `TypeError`。**更正 round-1
review 的因果顺序**：修复前新 key 的首次失败是这里的 `TypeError`（replay 路径同样经过），digest port 的
`FrozenInstanceError` 在其后；两者都导致 500，verdict 不变。

## 3. Findings

### S6-RR1 [Blocker] FULL completeness 下 base digest 永远失败，accept 全量 503

`compute_baseline_canonical_bundle_digest` 在 `InputCompleteness.FULL` 分支把 baseline 快照同时作为
baseline/initial/modified 三侧（`preview_jobs.py:1235-1249`），两个 pair 因此产出**内容完全相同**
的比较产物。bundle 组装只对 `SNAPSHOT_TABLE` 做跨 pair 共享提升，其他 kind 的重复 source ref 直接
失败（`capabilities/bundle_assembly/_assembly.py:461-475`，`DUPLICATE_SOURCE_ARTIFACT_REF`）。
artifact ID 由「前缀 + kind + 内容 digest」确定（`capabilities/comparison/artifacts.py:991-999`，
前缀固定 `comparison`，不含 pair id），所以重复是**确定性**的，与仓库内容无关。

实测（真实 port + 可用 mock repository transport）：

```text
MODIFIED_ONLY: OK sha256:3e84c25d2bfe768d3...
FULL: ApiError 503 DEPENDENCY_UNAVAILABLE - baseline canonical digest is unavailable
```

底层失败原因（直接调用 owner 函数，捕获 assemble 结果）：

```text
FULL
  profile: MULTI_PAIR pairs: ['baseline_to_initial', 'initial_to_modified']
  status: FAILED diagnostics: ['DUPLICATE_SOURCE_ARTIFACT_REF']
  RAISED: PreviewJobError baseline bundle assembly failed
```

影响：FULL 是契约定义的一等上传模式（`business-lifecycle-and-state.md:50`：FULL 要求 INITIAL+MODIFIED；
`multipart_upload.py:100-115` 明确支持），因此**FULL workspace 的每个新 AcceptSubmit 都返回
503**（replay 不调用该 port，不受影响）。design §6.1 新增段落描述的是「preview job 在字节相同上传下
可能 DUPLICATE_SOURCE_ARTIFACT_REF」，但没有意识到 base digest 的**定义本身**（三侧同为 baseline）
必然是同一个失败场景。

要求（需要 design/契约 owner 决策，不能由实现自行选择）：

1. 二选一确定可实现的语义：
   - (a) 扩展 bundle 组装规则，使内容相同的非 snapshot artifact 也能跨 pair 提升为 `shared/…`
     绑定（preview 与 base 两侧同规则 ⇒ 仍同构）；这会改变 bundle 布局/`bundle_digest`，属
     bundle capability owner 的契约变更，需相应 design/ADR 记录；
   - (b) 修改 design：FULL 下 base canonical digest 改用其他可比对定义（例如仅以
     `initial_to_modified` 单 pair 语义重定义两侧），并同步 preview 侧 canonical digest 语义。
2. 修复后必须补 FULL 分支的 owner test：真实 port 返回 digest，且**真实 preview no-op 的
   `bundle_digest` 与之相等**（本轮用 MODIFIED_ONLY 完成了同类证明，见 §2；FULL 需要同一强度的证据）。

### S6-RR2 [Medium] closure owner 测试是源码文本断言

`tests/test_production_wiring.py:374-383` 用 `inspect.getsource(preview_jobs.surface_artifact_closure)` 断言
字符串包含 `ordered_extension` / `surface.projections`，并断言 `runtime` 源码里不再出现 `_surface_artifact_closure`。

问题：这不是行为证据——重命名、导出别名、把逻辑移到 capability 内部（正是推荐的清理方向）都会让断言
失效，而真正的回归（例如再次引入第二份 closure、或丢失 ordered/projection 绑定）不会被它拦住。

要求：改为行为断言——构造含 ordered extension ref 与 projection 的 surface（可直接使用
`surface_assembly` 的 fixtures 或最小手工 `ComparisonSurface`），断言 `surface_artifact_closure`
产出 `pairs/<id>/ordered/...`、`pairs/<id>/projections/...` 绑定且覆盖 `collect_surface_refs`；
「runtime 不再复制」这一点应放到 `tests/test_architecture.py` 的边界规则里，或用「port 委托 owner」
的 monkeypatch 断言替代。

### S6-RR3 [Medium] 使 read-only factory 缺陷漏过的类型洞仍在

`http/orchestration/submit_acceptance.py:54-57` 把 `Callable[[], ControlDbUnitOfWork]` 用 `cast`
转成 `SubmitControlUnitOfWorkFactory`（要求 `read_only: bool = False`），而
`http/dependencies.py:215` 等处把该 factory 声明为 `Callable[[], ControlDbUnitOfWork]`。
正因如此，round-1 candidate 的 `unit_of_work_factory()`（无 `read_only` 参数）能通过 `strict` mypy，
在生产路径上才炸。

要求：把 `WorkspaceHttpDependencies.unit_of_work_factory` 与 orchestration 的对应参数改为
`SubmitControlUnitOfWorkFactory`（或等价的 `ControlUnitOfWorkFactory` protocol，含
`read_only: bool = False`），删除 `_submit_uow_factory` 的 `cast`；让同类缺陷变成 mypy error，
测试 harness 的 fake factory 也随之受同一契约约束。

### S6-RR4 [Low] `ruleset_version` 被接收后丢弃，与 design 文本不符

`compute_baseline_canonical_bundle_digest` 校验 `ruleset_version` 后 `del ruleset_version`
（`preview_jobs.py:1225-1228`）；design §6.1 新增段落写的是「按 bound … `PreviewResult.ruleset_version` …
重跑 comparison+bundle assembly」。实际两侧都不使用该字段（preview 的 `_materialize_baseline_side`
同样写死 `TABLE_RULESET_VERSION`），所以当前行为自洽，但语义与文本不一致：未来 preview 改用其它
ruleset version 时，base 侧会静默按 v1 计算并给出错误的相等/不等结论。

要求：二选一——(a) 让该参数真正参与（至少 fail-closed 校验 bound 值等于本进程实现的 ruleset version）；
(b) 修正 design 措辞，明确 `ruleset_version` 只是绑定事实、不参与 digest 计算，并在 port docstring 说明。
建议 (a)，与仓库其它「未知版本 fail closed」的既有模式一致。

### S6-RR5 [Low] port 的双重 except 与全量映射

`runtime.py:231-253` 的 `except (PreviewJobError, ValueError)` 与紧随其后的 `except Exception`
产生完全相同的 `ApiError(503)`，前者实际冗余；同时全量兜底会把编程错误（如 round-1 的
`FrozenInstanceError`、签名不匹配的 `TypeError`）统一伪装成 503，降低可诊断性——本轮 `unit_of_work_factory`
缺陷若发生在本 port 内就会被掩盖。

要求：合并为单一 handler；只对预期异常族（`PreviewJobError` / `ValueError` / repository provider
错误）映射 503，其余保持 500 以便测试与告警暴露真实缺陷。

### S6-RR6 [Low] 生产 composition 仍无 202 成功路径测试

本轮新增的 `test_accept_submit_rejects_no_canonical_change_with_production_port` 用真实 runtime
composition + 真实 port 走到 `409`，但**没有任何测试让生产 composition 走完 T1 并返回 202**。
`read_only` factory 缺陷恰好位于该区间（`load_accept_submit_preflight` / T1 写事务 / artifact
verification / main resolve），说明该区间的接线风险是实测过的。

要求：在 S6 或 S7 增加一个生产 composition 的 202 用例（seed 非 no-op preview，使
`bundle_digest != base digest`，断言 202 + attempt/operation row 落库 + protection 迁移），
并把 nodeid 写入 handoff/S7 计划。

## 4. Probe evidence (throwaway, removed)

1. `probe_r2b.py`：直接调用 `compute_baseline_canonical_bundle_digest`，捕获 `assemble_bundle` 结果——
   MODIFIED_ONLY `READY` + digest；FULL `FAILED` + `DUPLICATE_SOURCE_ARTIFACT_REF` + `PreviewJobError`。
2. `probe_full_port.py`：真实 `HttpBaselineCanonicalDigestPort`（mock transport 可用）——
   MODIFIED_ONLY 返回 digest；FULL 返回 `ApiError 503 DEPENDENCY_UNAVAILABLE`。
3. `probe_modonly_equality.py`：真实 preview job（canonical no-op）`bundle_digest` 与 port base digest
   逐字节相等（`sha256:e96d345b…`）⇒ MODIFIED_ONLY 的 `NO_CANONICAL_CHANGE` 可触发。
4. `probe_r2c.py`：monkeypatch `assemble_bundle` 捕获 preview 侧与 port 侧的 `BundleAssemblyInput`——
   MODIFIED_ONLY `SINGLE_PAIR`、FULL `MULTI_PAIR`，两者的 inputs/pairs/indexes 完全相同
   （`TOPOLOGY MATCH: True`）；FULL 的 port 调用在此拓扑下仍 `RAISED PreviewJobError`。

①②③④ 均已删除，worktree 无残留（仅新增本 review 文档）。

## 5. Not verified / deferred

```yaml
s6_focused_gates: 未重跑（采信 remediation handoff：unit 32 passed、worker serial 3 passed、ruff/mypy pass）
compose_e2e: 未重跑；本轮为显式 skip（repository-service conjunction build 不可用）
container_conjunction_gate: 未执行（沿 handoff defer 至 S8）
five_package_static: 未执行（defer 至 S8）
```

## 6. Required remediation

```yaml
blocking_findings: [S6-RR1]
remediation_allowed_paths:
  - vnext/backend/src/gateway_backend/application/preview_jobs.py          # S6-RR1 (a)/(b), S6-RR4
  - vnext/backend/src/gateway_backend/capabilities/bundle_assembly/**      # S6-RR1 (a)（需 owner 授权）
  - vnext/backend/src/gateway_backend/http/runtime.py                      # S6-RR5
  - vnext/backend/src/gateway_backend/http/dependencies.py                 # S6-RR3
  - vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py # S6-RR3
  - vnext/backend/tests/test_production_wiring.py                          # S6-RR1, S6-RR2, S6-RR6
  - vnext/backend/tests/test_backend_readiness.py                          # S6-RR1（如需 registry/ports 断言）
  - vnext/backend/tests/support/*                                          # S6-RR3 fake factory 契约
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md # S6-RR1, S6-RR4
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-*.md
re_review_entry: S6-RR1 修复（含 FULL 分支行为证据）后重跑 S6 focused gate 并做 round 3 复审
```
