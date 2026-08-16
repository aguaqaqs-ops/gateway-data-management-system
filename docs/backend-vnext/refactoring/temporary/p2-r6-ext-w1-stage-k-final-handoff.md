# P2-R6-EXT-W1 Stage K — Final handoff

状态：`pass`

日期：2026-08-16

本记录是 Stage K 要求的独立只读收口。审核对象是 Stage F-J 已提交的 evidence；本阶段
不修改 production code、Contract、测试、Dockerfile、Compose 或已验证镜像输入。`phase_2_complete`
仍按 P2 testing conventions 保持 `no`，因为 S7/S10 的 versioned-read Compose、restored
snapshot lifecycle 和 v8 formal gate 尚未完成。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
Stage J：[P2-R6-EXT-W1 Stage J Final Image and Lifecycle](p2-r6-ext-w1-stage-j-final-image-lifecycle.md)
脱敏 descriptor：[P2-R6-EXT-W1 external descriptor](p2-r6-ext-w1-external-descriptor.yaml)
入口 readiness：[P2-R6-S6 Entry Readiness](p2-r6-s6-entry-readiness.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_documentation_head_sha: 352d9097ddf26fb3e68397430f45d2e479473e51
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
worktree_clean_at_review: yes
production_source_changed_after_container_build: no
package_version: v1
canonicalization_version: v1
external_descriptor_sha256: sha256:416eb412d7e9ec389bb0dffae5511b016937ae1e29790cc3e26b549eb772205f
external_descriptor_bytes: 2682
```

`352d9097` 与 Stage J 镜像验证的 `656a66bf` 之间只有 plan/readiness/Stage J 文档差异；
没有 production source、Contract、test、dependency、Dockerfile 或 Compose 输入差异。因此
镜像事实绑定 `container_validated_code_sha`，本 handoff 的文档 SHA 不冒充镜像 candidate SHA。
历史 S5 evidence 文件自其 provenance commit `b5b4cca3310959f45cc527ab3e7d4eb1754d12d3`
以来未被修改，且其中绑定的 S5 candidate `e7a6e42d` 仍为祖先；`e7a6e42d` 本身早于该
文档记录提交，因此不作为该文件的 diff 起点。

## Closure review

| area | result | evidence |
| --- | --- | --- |
| Five fixtures and v1 packages | pass | Stage F/H; five package SHA and manifest digest match |
| Production validator | pass | Stage G/H; five `FULL_SCAN` + `REJECT`, unknown=0, lossy=0 |
| Failure/no-effect probes | pass | Stage G/H; reopen, truncation, digest, metadata and row-count probes |
| S6 capacity | pass | Stage I capacity; all five positive HTTP imports accepted |
| W2 boundary | pass | Stage I W2; 201681690-byte replay below 200 MiB cap |
| Concurrency | pass | Stage I matrix; 1/4/8 pass, ninth stream 503, import peak 4 |
| Current production image | pass | Stage J; image `sha256:57e2ec06...281296`, restart/replay and container FULL_SCAN |
| Cleanup | pass | Stage F-J temporary roots and Compose resources cleared |

The five fixtures remain positive accepted cases. No SQL type rewrite, column filtering, lossy
stringification, or fabricated digest was used. The medium catalog count of 327 ENUM columns is
the authoritative Stage F/G scan; the earlier readiness estimate of 328 is not a mismatch.

## State decision

```yaml
stage_k_exit: pass
R6-EXT-W1: yes
P2-R6-S6_ready: yes
s6_capacity: pass
w2: pass
concurrency_matrix: pass
validator_gate: pass
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
phase_2_complete: no
production_retest_required: yes
new_blocker_count: 0
deferred_retest_count: 3
```

The deferred items are declared Phase 2 S7/S10 scope, not hidden blockers for R6-EXT-W1:

- versioned-read Compose e2e inside the network and from the gate host;
- fresh/restart/restored snapshot Compose lifecycle;
- Candidate A v8 formal 66-record gate (`--runs 5`).

Those gates must remain open in the P2-R6 operational-closure plan. This handoff does not promote
the image to `gateway-repository-service:p2-r6-final` and does not claim Phase 2 completion.

## Docker / Compose decision

```text
Current HEAD: 352d9097ddf26fb3e68397430f45d2e479473e51
Container rebuild required: no
Reason: Stage K changes are documentation and a sanitized descriptor only; production/build inputs are unchanged
Last verified image revision: 656a66bf04714cce987c85649246c3767b2586e2
Last verified source-tree/image id: sha256:f6dc57cb635482b5c5287746ba5da956db7d56fcd9bc461ff942e04d514a785e / sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
Container gate for validated production code: passed
Container gate for documentation HEAD: stale-by-documentation-only-delta
Deferred gates/nodeids: P2-R6-S7/S10 versioned-read Compose e2e (absent), restored snapshot Compose, v8 formal 66-record
Required execution point: rebuild only if a later change touches production/build/deployment boundary
```

The stale label applies only to the literal documentation HEAD versus the image label. It does not
invalidate the Stage J gate for `container_validated_code_sha`; any production or build-input change
must create a new candidate and repeat the required image/container gates.

## Verdict

```yaml
review_status: pass
blocker_count: 0
evidence_closed_for: R6-EXT-W1
history_s5_unchanged: yes
readiness_descriptor_consistent: yes
phase_2_complete: no
next_owner: P2-R6-S7/S10 operational closure
```
