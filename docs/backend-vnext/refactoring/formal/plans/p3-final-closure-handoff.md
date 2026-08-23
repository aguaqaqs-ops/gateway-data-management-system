# P3 Final Closure and P4/P5 Entry Handoff

状态：**pass**（F0–F5 complete/pass；`p3_exit: pass`；不是 P4/P5 implementation authorization）

日期：2026-08-23

Owner：Backend vNext Architecture Acceptance

本文封存 P3-FINAL 的 sealed candidate、evidence record、deferred register 与 P4/P5 entry
boundary。F5 独立验收见
[p3-final-closure-f5-independent-acceptance.md](p3-final-closure-f5-independent-acceptance.md)。

上游身份：[P3-FINAL F5 Independent Acceptance Record](p3-final-closure-f5-independent-acceptance.md)
（F0–F1 process evidence archived；recover via tag `docs/p3-p4-cleanup-pre-20260823`，见
[p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml) `paths.archive_from_default`）

R7 上游：[P3-R7 Mutation and Target Closure Handoff](p3-r7-mutation-target-closure-handoff.md)

```yaml
handoff_kind: p3_final_closure
round: P3-FINAL-F5
tested_candidate_sha: 13ce18b8b2d689bc7a4087e0072d485891740c0c
prior_tested_candidate_sha: a28d88a85793017716029638155687ca17e4b5ed
prior_handoff_record_sha: c58498d7a517b7f954a7ee24284a58829bd81a40
handoff_record_sha: b0ac984507056fb10c17c07243330b20a315c2c8
f3_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
f4_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
p3_exit: pass
p4_ready: yes
p4_implementation_authorized: no_until_p4_entry_acceptance
p3_production_integration_authorized: no
p3_implementation_authorized: no
```

`13ce18b` 是 **F2/benchmark authority**；`a28d88a` 是 **F3 source/test** 与 **F4 container
authority**。二者之间只有 runner/applicability formal changes，production/test/build inputs
不变。`13ce18b` 相对 `a28d88a` 修正 benchmark runner 适用性/测量记录与 owning P3
design/execution applicability 裁定；F3/F4 未重跑，仍继承 `a28d88a` 上已通过的
source/container evidence。

## 1. Gate identity

| Gate | Result | Authority |
| --- | --- | --- |
| F0 entry/applicability | **pass** | F5 acceptance record；process plan archived（tag `docs/p3-p4-cleanup-pre-20260823`） |
| F1 evidence reconciliation | **pass** | same |
| F2 diagnostic benchmark | **pass** on `13ce18b` | [p3-final-closure-benchmark.json](p3-final-closure-benchmark.json) |
| F3 source/static | **pass** on `a28d88a`（未因 runner-only reconciliation 重跑） | `/tmp/p3-final-run-tests.log` |
| F4 backend container | **pass** on `a28d88a` image | remote `gateway-backend:p3-final-a28d88a85793` |
| F5 independent acceptance | **pass** | [p3-final-closure-f5-independent-acceptance.md](p3-final-closure-f5-independent-acceptance.md) |

## 2. Benchmark applicability reconciliation

F5 初审阻塞项为 benchmark 覆盖与上位 P3 三层 measurement 策略的 applicability 歧义。修复后
正式裁定：

- P3 exit 当前证据范围 = **component/multi-pair diagnostic only**；
- cross-capability artifact chain → deferred to **P5/P6/P7**；
- production/reference provider comparison → deferred to **P6/P7**；
- `staging_high_water` → **`not_applicable`**（in-memory Arrow workload，无 staging path）。

权威记录：

- [p3-capability-foundation-execution-plan.md §6](p3-capability-foundation-execution-plan.md#6-benchmark-policy)
- [p3-capability-foundation-design.md §5–6](p3-capability-foundation-design.md#5-phase-3-deliverables)
- runner `applicability_scope` / `measurement_record` in
  `vnext/backend/benchmarks/p3_capability_diagnostics.py`

## 3. Revision identity

```text
tested_candidate_sha: 13ce18b8b2d689bc7a4087e0072d485891740c0c
f3_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
f4_validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
handoff_record_sha: b0ac984507056fb10c17c07243330b20a315c2c8
f5_acceptance_record: p3-final-closure-f5-independent-acceptance.md
```

## 4. Container provenance

```text
execution_host: 10.10.60.4 (tmpuser)
gate_worktree: /home/tmpuser/gateway-gate-a28d88a85793
validated_source_sha: a28d88a85793017716029638155687ca17e4b5ed
image_tag: gateway-backend:p3-final-a28d88a85793
image_id: sha256:1e04d4e3e9603fd3c62ac857a77c0fb6fefeb8eb29b31dcf1ecc0da9b997d550
remote_smoke_log: /tmp/p3-final-container-smoke.log
remote_smoke_log_sha256: 62175b878acf49f4d2bf8eef682c125f684da9817701fe1b66ae7e23773e66dc
```

## 5. Deferred/reopen register

| Item | Disposition | Owner | Reopen condition |
| --- | --- | --- | --- |
| legacy oracle fixture | known external fixture / exact exclusion | R4 | parity matrix or migration/cutover change |
| cross-capability benchmark | deferred | P5/P6/P7 | confirmed consumer + production path |
| provider comparison | deferred | P6/P7 | production provider candidate exists |
| P4 durable runtime | not implemented | P4 | P4 entry handoff |
| P5 business jobs | not implemented | P5 application | P5 entry |
| external target adapter | in-memory reference only | future adapter | first consumer confirmed |

## 6. P4/P5 entry boundary

P3 不交付、不授权：

- durable Operation Store、worker、lease、heartbeat、takeover；
- Workspace/HTTP/PreviewResult、Submit/finalize、confirmation、occupancy、T1/T3；
- production external-target adapter 或 multi-target durable schema；
- Repository Service reconciliation 仍由其 control DB/marker/ref/CAS 拥有；P4 lease 不改变
  Repository operation authority。

P4 可进入 entry/design conversation；`p4_implementation_authorized: no_until_p4_entry_acceptance`。

## 7. F5 acceptance checklist

独立验收者应核对：

1. `13ce18b` tested candidate 与 evidence-only handoff diff；
2. benchmark applicability 裁定是否消除 P2 ambiguity；
3. F3/F4 继承 `a28d88a` 是否被 reconciliation scope 正当支持；
4. legacy oracle exact exclusion 未写成 gap closed；
5. P4/P5 owner seam 与 formal contracts 一致。
