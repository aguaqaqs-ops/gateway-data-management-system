# P2-R6-S10 Independent Audit Adapter Review — Attempt-3 Rerun

状态：`pass`

日期：2026-08-17

本记录是 S10-3 对 S10-2 attempt-3 adapter 的新独立只读复审。复审对象是 S10-6
因 named volume leftover fail-closed 后修复的 adapter；attempt-1、attempt-2、首次失败
审核、attempt-2 通过审核及 S10-6 失败记录均原样保留。本审核没有修改 adapter、candidate、
production、test、dependency、Dockerfile、Compose、image 或既有 evidence；没有读取或执行
批准的 W1 `medium` / W2 package，也没有启动 HTTP、Docker 或 Compose live path。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §5 / §8

attempt-3 修复记录：[P2-R6-S10 Step 2 — Production-image W1/W2 Audit Adapter](p2-r6-s10-step-2-audit-adapter.md)

S10-6 失败记录（保留）：[P2-R6-S10 Step 6 — W1 medium and W2 production repeat](p2-r6-s10-step-6-w1-w2-production-repeat.md)

attempt-2 通过审核（保留）：[Independent Audit Adapter Review — Rerun](p2-r6-s10-audit-adapter-review-rerun.md)

首次失败审核（保留）：[Independent Audit Adapter Review](p2-r6-s10-audit-adapter-review.md)

## Reviewed identity and isolation

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean_at_review: yes
adapter: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/adapter/s10_w1_w2_audit_adapter.py
adapter_schema: p2-r6-s10-audit-adapter-v3
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
command_contract_sha256: 81f231c8fca566e086650670e722adb7a84b44291624627f9b532a4b4ef338d4
attempt_2_adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
attempt_1_adapter_sha256: b758febdc9b1d97e732e17047d84d57cda45c16b5bba61f32768a04e7b3e9d1f
prior_s10_6_record_sha256: 6acc1f584d06939f93ba4b7f6c7cc53c2306c0b42fb9c8ea8645046b6993b1f2
review_kind: independent_read_only_adapter_review_attempt_3
approved_packages_read: no
w1_w2_consumed: no
production_code_changed_by_review: no
image_built_or_changed_by_review: no
phase_2_complete: no
```

当前 adapter 与 command contract 均通过 `adapter/SHA256SUMS`。attempt-1/attempt-2
文件的 SHA-256 与历史记录一致；S10-6 失败步骤记录 SHA-256 仍为
`6acc1f58…993b1f2`。candidate `HEAD` 是 literal sealed candidate，porcelain 为空。

## Review results

### 1. Attempt-3 change scope

**Pass.** attempt-2 到 attempt-3 的源码差异仅包含：schema/attempt 标识、固定的
`COMPOSE_DOWN_ARGS`、dry-validate cleanup 契约字段，以及 HTTP 完成后失败证据的统一构造。
未改变 public HTTP identity/readback、package provenance、candidate/image binding、资源采样、
data-root 或 redaction 行为。

### 2. S10-6 named-volume cleanup

**Pass.** `cleanup_compose` 通过 argv-only subprocess 执行 project-scoped：

```text
docker compose -f <compose-file> -p <scoped-project> --profile p2-r2 down -v --remove-orphans
```

`-p` 与运行中 container 的 `com.docker.compose.project` label 在进入 live HTTP 前严格比对；
`-v` 删除该 Compose project 声明的 named volume。cleanup 后再次按相同 project label 统计
containers/networks/volumes，任一非零都只能产生 `FAILED`、
`container_pass=not_claimed`。这关闭了 S10-6 attempt-1 中
`repository-service-data` volume 残留的 adapter 缺陷。

### 3. Cleanup failure evidence retention

**Pass.** adapter 只有在 import identity、`main`、catalog/503 fallback、row stream、
unknown/lossy、row count、disk after 与 query-temp 全部通过后，才设置
`http_completed=true`。随后 sampler/client/Compose cleanup/final inventory 均在外层
`try/finally` 中执行。若 HTTP 已完成而 sampler、`down -v` 或 final inventory 失败，
`fail_payload` 保留：

- `timings`
- `resource_peaks`
- `public_counts`
- `w2_band`
- `cleanup` 与 `http_completed=true`

同时强制 `status=FAILED`、`container_pass=not_claimed`、进程非零退出。HTTP 未完整通过时
只记录 `http_completed=false`，不会把部分公共事实误写为完成证据。

### 4. Prior S10-3 boundary remains closed

**Pass.** attempt-2 已关闭的五项 finding 在 attempt-3 中保持不变：

- candidate HEAD/clean/Service lock 与 running image ID、candidate/build-input/source-tree/lock labels 全部绑定；
- package-derived `canonicalization_manifest_digest` 与 expected/import result 绑定；
- upload、operation、`main`、catalog 与 row readback identity 完整校验，仅 catalog HTTP 503 使用 manifest fallback；
- sampler/client/cleanup 位于 fail-closed lifecycle 中，输出经过 secret/host-path redaction；
- `0B` resource parsing、sampler error、固定 server-owned data-root 与 argv-only `docker exec` 保持有效。

AST parse 通过，未发现 `shell=True` 或 `sh -c`。adapter 仍不导入 Service、Client、backend
或 `r6_s6_lib` 内部实现，不存在 host-runtime fallback 或 HTTP request retry。

## Verification performed

以下检查均为只读，未消耗批准 package：

- 当前/attempt-2/attempt-1 adapter、command contract、S10-6 失败记录 SHA-256 复核；
- 当前 `adapter/SHA256SUMS` 校验；
- attempt-2 到 attempt-3 源码逐行差异审核；
- Python AST parse、`shell=True` 与 forbidden import 静态检查；
- cleanup argv、project label binding、post-cleanup inventory 与 failure serialization 控制流审核；
- retained dry-validation evidence：success exit `0`，八个 fail-closed cases exit `1`，
  `compose_down_args=[down,-v,--remove-orphans]`，`container_pass=not_claimed`，
  `w1_w2_consumed=false`；
- candidate HEAD/clean porcelain 只读复核。

没有执行 live HTTP/Docker/Compose，因此本审核不证明 `down -v` 的远端实际执行结果，也不
授予 W1/W2 production pass。该结果必须由使用当前 exact adapter SHA 的新 S10-6 attempt
证明；任何 adapter 字节变化都会使本审核失效并重开 S10-3。

## Findings and verdict

```yaml
finding_count: 0
blocker_count: 0
high_count: 0
medium_count: 0
low_count: 0
prior_review_status: pass
prior_s10_6_status: fail
prior_s10_6_failure_preserved: yes
review_status: pass
allow_w1_w2_execution: yes
approved_packages_consumed: no
w1_w2_production_claim: no
candidate_or_image_changed_by_review: no
production_retest_required: yes
S10_exit: no
S11_ready: no
phase_2_complete: no
next: repeat S10-6 with adapter SHA af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150 and a new attempt ID
```

本次 pass 仅授权在 candidate、final image IDs、topology 与 baseline 均保持不变时，以新
attempt ID 重跑 S10-6。它不把历史 leftover 失败改写为 pass，不授予 W1/W2 production
结果、S10 exit、S10 seal、S11 handoff 或 Phase 2 completion。

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no for this read-only review; final images and Compose inputs are unchanged
Reason: external adapter-only cleanup fix; S10-4 final artifacts and S10-5 gate remain preserved
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current adapter SHA: deferred
Required execution point: new S10-6 attempt with exact adapter SHA af672fa0…b41150
```
