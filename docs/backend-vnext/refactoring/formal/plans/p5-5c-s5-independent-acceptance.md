# P5-5C-S5 Independent Slice Exit Acceptance

状态：**PASS — `p5_5c_slice_exit: pass`**

日期：2026-09-20

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[Execution Plan §8](p5-5c-review-execution-plan.md)、
[S5 Handoff](p5-5c-s5-handoff.md)、[S5 Remediation Handoff](p5-5c-s5-remediation-handoff.md)、
[S4 Independent Review](p5-5c-s4-independent-review.md)。

```yaml
acceptance_kind: p5_5c_s5_slice_exit
acceptance_authority: explicit_repository_owner_authorization
acceptance_target_tip: 4710a7a37727700c5466e83085ba5389d5816428
accepted_candidate_head: 04317788c259b172e3b8580cfe42bac8d16735f0
gate_tested_head: 04317788c259b172e3b8580cfe42bac8d16735f0
decision: pass
findings_closed: [P1, P2]
review_findings_open: []
p5_5c_slice_exit: pass
p5_5c_implementation_status: completed
p5_5c_implementation_authorized: no
p5_5d_design_readiness: ready
p5_5d_implementation_authorized: no
production_deployment_authorized: no
new_repository_effect_authorized: no
```

## Acceptance and evidence

独立复审确认 P1 readiness/clean-stop 缺口及 P2 conjunction 镜像绑定缺口均已关闭，未发现新增
阻塞问题。用户随后明确授权将 `p5_5c_slice_exit: pass` 落入文档。

- 本 context 独立复跑 PREBUILT conjunction：**5 passed, 0 skipped，174.92s**，包括 Review
  journey、Submit restart、Submit journey、Backend CMD、readiness/clean-stop。
- 运行中三个容器的实际 Image IDs 与 S5 handoff 一致：repository `sha256:d731197ec2e425defcaf582cc9cd2c516f9e43176f62bd4b0990336680e42b30`、
  backend `sha256:ee3e8b0983efdb84cbd56a25d090d050b4d527deca87f5f572dfc25ac0736b5b`、
  worker `sha256:f0ef349faea1f19d417e2db6dc447864971c111326e1f3992432127f9f15d261`。
- 独立重算 874 个 tracked `vnext/**` 文件摘要：
  `sha256:9b7f863c4d24596fdddb3bbd82a4e5b25a85fcf1af26dd8af2124dbb06c885d9`。
  算法为按路径排序，每行 `path\tsha256\n`，再对全部 UTF-8 记录计算 SHA-256。
- 五锁与 Compose SHA 均匹配 handoff；candidate 到 publication tip 无 `vnext/**` 差异。
- 本 context 独立复跑 Backend ruff/mypy：pass（391 source files）。五包 static、累计 focused
  278 passed、权威 runner exit 0 采用 candidate handoff 证据；未再次执行全量 runner。

复跑命令：

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5c-s5-gate \
GATEWAY_COMPOSE_GATE_PREBUILT=1 \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_review_compose_e2e.py tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py
```

## Container decision

- Current HEAD at review/publication start：`4710a7a37727700c5466e83085ba5389d5816428`；工作区干净。
- Container rebuild required this docs-only publication：no；本轮只记录已完成的独立验收。
- Last verified image revision：`04317788c259b172e3b8580cfe42bac8d16735f0`；source-tree/IDs 见上。
- Container gate for accepted candidate：passed；publication HEAD 不另宣称 fresh-build passed。
- Deferred gates/nodeids：none for accepted 5C candidate。后续触及容器边界或形成新阶段最终候选时，
  按 testing conventions 重新构建并验证。

## P5-5D design entry assessment

具备开始 P5-5D docs-only entry brief、Archive detailed design 和 execution plan 的条件。
依据是 5A/5B/5C exit pass，以及 [Business Lifecycle §5](../contracts/business-lifecycle-and-state.md)
和 [P5 Baseline §6.4](p5-business-vertical-slices-design.md) 已冻结 Archive 业务边界。
这不表示 5D 详细设计已 accepted，也不开放 source/test/dependency/deployment 改动。

5D 设计须落实 CandidateProjection、confirmation/anomaly resolution、纯读 PreviewArchivePlan、
StartArchive 单个 SQLite 事务、BaselineHead CAS、与 AcceptSubmit/Review return 的并发屏障、
幂等与 scope 权限。所选既有 Submission commit 成为新业务 Baseline；不得引入 Repository
写入、第二个 commit、Operation/ArchiveExecution 或无 consumer 的 outbox。

P5 §2A 尚存跨 Slice 架构收口项继续由原 owner 处理；5C exit 不宣称全部历史问题已解决。
下一步在新对话中明确授权 5D docs-only 工作；独立 docs review 与后续实现授权仍分别进行。
