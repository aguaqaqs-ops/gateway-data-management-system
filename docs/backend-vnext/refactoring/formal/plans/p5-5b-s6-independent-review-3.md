# P5-5B-S6 Independent Review Round 3 (remediation round 2, c55726ca)

状态：**FAIL — RR1 阻断已由独立探针实测关闭；RR5 收窄引入 1 个新的阻断（仓库不可用映射为 500）**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target and decision

```yaml
stage: P5-5B-S6-remediation-round-2
implementation_candidate: c55726cac6e4f41d3b5808ccd48815df10a9557d
parent_candidate: 1bbc125d99f7b4dd24fe97d0ff39b0cec10a1a25
previous_reviews:
  - p5-5b-s6-independent-review.md
  - p5-5b-s6-independent-review-2.md
decision: fail
verified_closed: [S6-RR1, S6-RR2, S6-RR3, S6-RR4-behavior, S6-RR6]
findings_open:
  - S6-RR9 [High/blocking] Repository/transport 故障在 digest port 上退化为 500（与 design 错误族、
    HttpRepositoryMainResolvePort 行为不一致）
  - S6-RR10 [Low] preview/submit 两处 ruleset_version 词表分裂；升级前已存 PreviewResult 会在 accept 上
    以「依赖不可用」形式 503
  - S6-RR11 [Low] bundle 跨 pair 共享新规则只写在 5B plan，未更新 owning capability/contract 文档
container_gate_for_current_head: deferred（沿 handoff；round 2 未触碰 container boundary）
s7_entry: blocked
```

方法：只读审阅 `c55726ca` 全部 diff；另跑 3 个 throwaway probe 实测 FULL/MODIFIED_ONLY digest、
preview↔port 等式、legit preview 的共享分支命中情况与仓库故障映射（构造后已删除，见 §4）。
未重跑 handoff 已报告的 focused gate。

## 2. Verified closures（本轮实测）

**S6-RR1 关闭（实测，三向证据）**

```text
port base digest (FULL)          : sha256:09719cf6887380c764c07
legit FULL preview digest        : sha256:78f04ab8b57e64c7fa94d
  promotion kinds (legit preview): []           # 合法 bundle 不触发新共享分支 ⇒ digest 无回归
  guard fires for legit preview  : False        # 有真实变更时不误报
canonical-noop FULL preview      : sha256:09719cf6887380c764c07
  promotion kinds (noop preview) : ['RECORDS_CLOSURE']
  guard fires for noop preview   : True         # FULL identity/no-change 路径 guard 正确触发
```

- FULL 下 port 不再抛 `PreviewJobError`，`bundle_digest` 可得；
- canonical no-op 的 preview `bundle_digest` 与 port base digest **逐字节相等** ⇒ `NO_CANONICAL_CHANGE`
  在 FULL 上真实可达；
- 正常 preview 对新共享分支命中为 **0** ⇒ `shared/<kind>/...` 提升只在「原本会失败」的重复 ref 场景
  生效，既有合法 bundle 的 `bundle_digest` 不变（`by_source` 排序与路径规则未动；`SNAPSHOT_TABLE` 仍走
  `shared/snapshot-tables/{digest}.parquet`，保持原路径）。`verify_bundle` 从 manifest 内容重算 digest，
  不重跑收集逻辑，故已发布 manifest 的校验不受影响。

**S6-RR2 关闭**：`tests/test_production_wiring.py:424-475` 用真实 `surface_assembly` 构造含
ordered extension 与 projection 的 surface，断言 closure 产出 `pairs/pair-1/ordered/…`、
`pairs/pair-1/projections/…` 且覆盖 `collect_surface_refs(surface)` 全部 ref（行为断言）；
「runtime 不再复制」移到 `tests/test_architecture.py` 的边界规则，位置正确。

**S6-RR3 关闭**：`WorkspaceHttpDependencies.unit_of_work_factory` 与 submit/preview/multipart
orchestration 参数改为 `SubmitControlUnitOfWorkFactory`，`_submit_uow_factory` 与三处 `cast` 已删除；
harness 内的单个 `cast` 属测试支撑、可接受。

**S6-RR4（行为）关闭**：`compute_baseline_canonical_bundle_digest` 对
`ruleset_version != RULESET_VERSION` fail-closed；`build_preview_job_payload` 改为发 `RULESET_VERSION`。
余留问题见 S6-RR10。

**S6-RR5（意图）关闭**：port 只映射 `PreviewJobError`/`ValueError`，`TypeError` 等直接抛出
（`test_http_baseline_canonical_digest_port_does_not_mask_programming_errors` 有判别力）。
但收窄过度，见 S6-RR9。

**S6-RR6 关闭**：`test_accept_submit_returns_202_with_production_runtime` 用真实 `prepare_backend_runtime`
composition + 真实 port（FULL）+ mock repository transport（含 main resolve），断言 `202`、
`state=PREPARED`、Attempt/Operation 落库；并断言 `baseline_digest != preview digest`，即 T1 路径真实走通。

**S6-RR7/RR8（round 2 review 的 Low 项）**：compose e2e 仍为显式 skip（本轮未重跑，已在 handoff 声明）；
`container_rebuild_required: no` 应理解为「本轮相对上一轮的增量」，S6 lineage 的 current-HEAD
container gate 仍在 defer（handoff 已写 `container_gate_for_current_head: deferred`）。

## 3. Findings

### S6-RR9 [High/blocking] Repository 故障在 digest port 上退化为 500

`runtime.py:241` 现在只捕获 `(PreviewJobError, ValueError)`。但仓库侧故障**都不是 ValueError**：

| 故障 | 抛出类型 | 结果 |
|---|---|---|
| repository 连接失败/重启 | `httpx.ConnectError` | 逃逸 → 500 |
| 行流超时 | `httpx.ReadTimeout` | 逃逸 → 500 |
| 仓库返回带合法 error body 的 4xx/5xx | `RepositoryClientError(RuntimeError)` | 逃逸 → 500 |
| 协议违规 | `RepositoryProtocolError(RuntimeError)` | 逃逸 → 500 |

实测（真实 port + `httpx.MockTransport`）：

```text
conn-refused: RAW httpx.ConnectError: refused
timeout     : RAW httpx.ReadTimeout: slow
```

只有被 capability 内部转成诊断的 `RepositoryProviderError`（表缺失/ref 不匹配/会话关闭）才会变成
`ValueError` → 503。也就是说**最常见的依赖故障路径全部返回 500 INTERNAL_ERROR**，与：

- design §5.3 的 AcceptSubmit 错误族（repository evidence 不可验证 ⇒ `503 DEPENDENCY_UNAVAILABLE`）；
- 同一请求路径上的 `HttpRepositoryMainResolvePort`（`runtime.py:277` 仍 `except Exception` → 503）

都不一致。round 2 的 `test_http_baseline_canonical_digest_port_maps_failures_to_503` 把原来的
repository-failure 用例换成了「不支持的 ruleset_version」，因此这条最现实的失败路径**失去了覆盖**，
gate 全绿并不代表它可用。

要求：

1. 明确捕获依赖故障族（`gateway_repository_client.errors.RepositoryClientError /
   RepositoryProtocolError / RepositoryStreamError / RepositoryClientTimeoutError`、`httpx.HTTPError`
   以及 `RepositoryProviderError`）映射为 503 `DEPENDENCY_UNAVAILABLE`，编程错误（`TypeError` /
   `AttributeError` / `KeyError` 等）继续抛出让测试与告警暴露；
2. 恢复/新增 repository-failure 测试，且必须给出**合法** wire 失败响应（含 `X-Request-ID` 与 client
   期望的 error body 字段），使映射真实生效——round 1 的旧用例其实是被 `RepositoryProtocolError`
   顺带命中的，不能作为证据；
3. 把「ruleset_version 不受支持」与「依赖不可用」分开：版本偏斜更接近 design §5.3 的
   `503 SERVICE_NOT_READY`（composition/版本不匹配），当前的 `DEPENDENCY_UNAVAILABLE` +
   "baseline canonical digest is unavailable" 会把运维引向错误的排查方向（见 S6-RR10）。

### S6-RR10 [Low] ruleset_version 词表分裂与升级前 PreviewResult 的行为

RR4 把 preview payload 的 `ruleset_version` 从 `"v1"` 改为 `RULESET_VERSION`（`"v2"`，
`preview_acceptance.py:99`），但 submit payload 仍写死 `"v1"` 且 decoder 强校验
（`application/submission/job_payload.py:41`、`application/submit_jobs.py:2434`）。两者同名不同义、
现在取值相反；`PreviewResult.ruleset_version` 是持久化字段，因此：

- 升级前已生成的 PreviewResult（`"v1"`）在其 workspace 上执行新 accept 时，port 直接 fail-closed →
  用户看到 `503 DEPENDENCY_UNAVAILABLE / baseline canonical digest is unavailable`，而真实原因是
  **需要重新 preview**；这是可诊断性问题，不是依赖故障；
- 该字段不在任何 HTTP response DTO 中（内部字段），因此无客户端可见破坏，但内部语义已分裂。

要求：在 design/handoff 明确 (a) 两个 payload 的 `ruleset_version` 词表各自的 owner 与取值来源，
(b) 升级兼容规则（旧 preview 需重新 preview，或提供兼容判定），(c) 该偏斜使用独立/更准确的错误码与
诊断，避免伪装成依赖故障。若 owner 认为 preview payload 应继续用 `"v1"`，则 RR4 的 fail-closed 判定
必须改为与 preview 实际使用的版本常量对齐。

### S6-RR11 [Low] bundle 跨 pair 共享规则的 owner 文档未更新

新规则（相同 `source_ref` 且 kind 相同的跨 pair 产物提升为 `shared/{kind}/{digest}/artifact`）只写进了
5B plan（`p5-5b-submit-finalize-design.md` §6.1）。bundle 布局的 owning 文档
`docs/backend-vnext/contracts/comparison-bundle.md`（§215-216 只描述 `shared/snapshot-tables/...`；
§365 规定 records/risk/projection 为 pair-scoped 且不得共享 `tables/...`、`comparison/records/...`、
`risk/...` 路径）与 `docs/backend-vnext/capabilities/bundle-assembly.md` 均未更新，
`BUNDLE_CONTRACT_VERSION`（`backend-vnext/comparison-bundle/v2`）也没有关于新命名空间/是否需要升级的说明。

另外两点需要在 owner 文档里定死（当前实现的行为）：

- 提升后的 binding 保留**第一个** binding 的 `table_name` 并置 `pair_id=None`；对 table-scoped kind
  （如两表产生相同 records 字节）会丢失第二个表的关联。若该情形不应被共享，应把提升限制在
  pair-scoped 非表级 kind；
- `_collect_bindings` 在提升时不清理 `by_path` 中的旧 pair 路径条目（当前无害：最终 manifest 走
  `by_source`），但属于易误读状态，建议一并整理。

要求：由 bundle capability owner 更新 owning 文档（或按上一条收窄规则），并明确新命名空间与
contract version 的关系；5B plan 只能引用，不应成为该布局的唯一记录。

## 4. Probe evidence (throwaway, removed)

1. `probe_sharing_hits.py`：spy `_assembly._promote_binding_to_shared` + 真实 preview harness——
   legit FULL preview 命中 0 次、digest 与 base 不同；canonical-noop FULL preview 命中
   `RECORDS_CLOSURE`、digest 与 base 相等（输出见 §2）。
2. `probe_repo_failure2.py`：真实 `HttpBaselineCanonicalDigestPort` + `httpx.MockTransport` 注入
   `ConnectError` / `ReadTimeout` ⇒ 原始异常逃逸（500），未映射为 `ApiError 503`。
3. 上一轮遗留探针（`probe_r2b/full_port/modonly_equality`）的结论在本轮由 `probe_sharing_hits` 复核。

三个文件均已删除，worktree 无残留。

## 5. Not verified / deferred

```yaml
s6_focused_gates: 未重跑（采信 handoff：unit 50 passed、FULL equality 1 passed、worker serial 3 passed、ruff/mypy pass）
compose_e2e: 本轮未重跑（handoff 声明沿用 round 1 skip 策略）
container_conjunction_gate: 未执行（沿 S6 lineage defer 至 S8；round 2 未新增 container boundary 改动）
five_package_static: 未执行（defer 至 S8）
```

## 6. Required remediation

```yaml
blocking_findings: [S6-RR9]
non_blocking_findings: [S6-RR10, S6-RR11]
remediation_allowed_paths:
  - vnext/backend/src/gateway_backend/http/runtime.py                  # S6-RR9（依赖故障族映射）
  - vnext/backend/tests/test_production_wiring.py                      # S6-RR9（合法 wire 失败用例）
  - vnext/backend/src/gateway_backend/application/preview_jobs.py      # S6-RR10（如需版本兼容判定）
  - vnext/backend/src/gateway_backend/http/orchestration/preview_acceptance.py # S6-RR10
  - vnext/backend/src/gateway_backend/capabilities/bundle_assembly/**  # S6-RR11（若收窄提升范围）
  - docs/backend-vnext/contracts/comparison-bundle.md                  # S6-RR11（owner 文档）
  - docs/backend-vnext/capabilities/bundle-assembly.md                 # S6-RR11（owner 文档）
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md # S6-RR10
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-*.md
re_review_entry: S6-RR9 修复 + 恢复 repository-failure 覆盖后重跑 S6 focused gate（含 compose e2e 至少一次
  可 build 的 conjunction 尝试）并做 round 4 复审
```
