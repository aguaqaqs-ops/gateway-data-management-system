# P5-5B-S6 Independent Review Round 4 (remediation round 3, 5a2bd56d)

状态：**PASS — S6 wiring/unit/process 证据闭合；container conjunction 与五包 static 按 lineage 仍 defer 至 S8**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target and decision

```yaml
stage: P5-5B-S6-remediation-round-3
implementation_candidate: 5a2bd56dafe5ccb71f5ffe334a12e41c639ff215
parent_candidate: c55726cac6e4f41d3b5808ccd48815df10a9557d
previous_reviews:
  - p5-5b-s6-independent-review.md
  - p5-5b-s6-independent-review-2.md
  - p5-5b-s6-independent-review-3.md
decision: pass
findings_open: []
findings_closed_this_round: [S6-RR9, S6-RR10, S6-RR11]
non_blocking_nits:
  - 版本偏斜靠 PreviewJobError message 字符串相等分类（有真实路径测试保护）
  - port 使用 except BaseException 而非 except Exception
container_gate_for_current_head: deferred（S8；本轮未触碰 container boundary）
five_package_static: deferred（S8）
s7_entry: eligible（最终授权按 lineage 惯例由用户给出）
```

方法：只读审阅 `5a2bd56d` 全部 diff；另跑 1 个 throwaway probe 覆盖错误映射矩阵、异常类型归属与
digest 回归（构造后已删除，见 §4）。未重跑 handoff 已报告的 focused gate。

## 2. Verified closures（本轮实测）

```text
ruleset-mismatch   : ApiError 503 SERVICE_NOT_READY        # RR9/§6.1 版本偏斜使用独立错误码
wire-503 (legal)   : ApiError 503 DEPENDENCY_UNAVAILABLE
wire-503 (bad body): ApiError 503 DEPENDENCY_UNAVAILABLE
legal body raises  : RepositoryClientError -> classified as RepositoryClientError
programming err    : RAW builtins.TypeError                # 编程错误不被掩盖
FULL noop equality : True  sha256:09719cf6887380c764c     # 与 round 2 值逐字节一致
```

**S6-RR9 关闭**：`runtime.py` 新增 `_api_error_for_baseline_digest_failure`，映射表与 design
error family 一致：

- ruleset 不受支持 → `503 SERVICE_NOT_READY`（区别于依赖故障，消息为
  "preview ruleset version is not supported by this deployment"）；
- `ValueError` / `RepositoryProviderError` / `httpx.HTTPError` / repository client 四个错误类型
  → `503 DEPENDENCY_UNAVAILABLE`；
- 其余（含 `TypeError`）原样抛出，probe 确认未被吞掉。

新增四个用例中，`..._maps_repository_wire_error_to_503` 使用**合法** wire 失败响应
（`X-Request-ID` + body 内 `request_id`）；probe 独立确认该响应实际产生
`RepositoryClientError`（而非仅命中 `RepositoryProtocolError` 兜底），因此测试覆盖的是真实
client-error 路径，不是假阳性。`ConnectError` / `ReadTimeout` 用例与 sibling
`HttpRepositoryMainResolvePort` 的 503 行为一致。

**S6-RR10 关闭**：design §6.1 现明确 preview `ruleset_version` = table-rules `RULESET_VERSION`（`"v2"`，
由 `build_preview_job_payload` 发出）、submit job payload 的 `"v1"` 为独立契约字段（同名不同义），
并写明「升级后 bound preview `ruleset_version != RULESET_VERSION` 的 workspace 须重新 preview 后方可
accept」，漏洞语义与错误码（`SERVICE_NOT_READY`）在文本中一致。

**S6-RR11 关闭**：`contracts/comparison-bundle.md` 新增跨 pair 共享规则（触发条件、路径
`shared/{kind-segment}/{digest-suffix}/artifact`、`SNAPSHOT_TABLE` 例外、`pair_id=None`/`shared=true`、
`table_name` 取首个 binding、`bundle_contract_version` 不 bump），并改写原「不得共享 pair-scoped
路径」条目为「不同 `source_ref` 不得共享同一 pair-scoped logical path；相同 `source_ref` 的跨 pair
重复允许提升」；`capabilities/bundle-assembly.md` 同步。`_collect_bindings` 现于提升时
`by_path.pop(previous_source.logical_path, None)` 清理过期条目，probe 确认清理后**digest 与 round 2
逐字节一致**（`sha256:09719cf6…`，同时 canonical-noop FULL 的 preview↔port 等式仍成立）⇒ 该清理
不改变任何既有行为。

## 3. 非阻断 nit（不阻塞 S6 关闭，建议随下阶段处理）

1. **版本偏斜靠 message 字符串分类**：`_api_error_for_baseline_digest_failure` 用
   `str(exc) == _BASELINE_DIGEST_UNSUPPORTED_RULESET_MESSAGE` 区分 ruleset 偏斜，而该常量是
   `preview_jobs.py` 中消息的副本。真实路径测试（`..._maps_unsupported_ruleset_to_service_not_ready`）
   会在改词时失败，因此当前有保护；但更稳的做法是由 application 层抛出专用异常类型
   （如 `UnsupportedRulesetVersion(PreviewJobError)`）让分类只依赖类型，避免跨层字符串耦合。
2. **`except BaseException as exc:`**（`HttpBaselineCanonicalDigestPort.get_baseline_canonical_digest`）：
   mapper 对未匹配类型原样 `raise`，行为正确；但 `KeyboardInterrupt`/`SystemExit`/`CancelledError`
   也会经过 helper 帧再抛出，建议改为 `except Exception`，让这些控制流异常自然传播。

## 4. Probe evidence (throwaway, removed)

`probe_round4.py`：真实 `HttpBaselineCanonicalDigestPort` + `httpx.MockTransport` 注入
ruleset 不匹配 / 合法 503 wire body / 畸形 error body / `TypeError`；并用 provider 直接确认合法 body
产生 `RepositoryClientError`；另跑 FULL canonical-noop preview↔port digest 等式与值回归。
输出见 §2/§3，文件已删除，worktree 无残留。

## 5. Not verified / deferred（S6 通过的边界）

```yaml
s6_focused_gates: 未重跑（采信 handoff：unit 53 passed、worker serial 3 passed、ruff/mypy pass）
compose_e2e: 1 skipped（repository-service build 因 dolt checksum 失败；fallback 显式 skip）
container_conjunction_gate: 未执行；S6 lineage 记录 container_gate_for_current_head=deferred，S8 必须在
  最终 candidate HEAD 重建三镜像并记录 provenance（compose.yaml 自 round 1 起已含
   stop_grace_period/secrets 改动，仍未在任何镜像上验证）
five_package_static: 未执行（S8）
S7 functional acceptance: 未开始（本 review 只覆盖 wiring/unit/process 证据）
```

## 6. Round 4 结论与 reopen 条件

- S6-R1–R8（round 1 review）、S6-RR1–RR6（round 2 review）、S6-RR9–RR11（round 3 review）全部关闭；
  round 4 的独立 probe 未发现新的功能或契约偏差。
- S6 通过的是：production composition 接线、readiness/shutdown、settings、compose wiring、
  bundle 共享契约、digest port 错误映射，以及对应 unit/process 证据。
- 触发 reopen 的条件：S8 container conjunction 或五包 static 暴露与当前 wiring 契约不符的行为；
  S7 独立功能验收发现 accept/finalize journey 与 design §6/§13 不一致；或 ruleset/bundle 契约
  owner 否决本轮记录的共享规则与版本策略。
- 下阶段建议：进入 P5-5B-S7 独立功能验收（授权按既有惯例由用户显式给出），S8 负责 current-HEAD
  三镜像 conjunction、五包 static 与 container provenance 记录。
