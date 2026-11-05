# Phase 6 W4 READY 闭包容量停止复核

- **结论：停止成立，属于冻结产品的 READY 闭包容量失败；不得原样重试。指定 v2-preview 前 checkpoint 的基础证据核验通过，可保留为 DC80 限定恢复来源候选，但尚未放行正式恢复。**
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- handoff 候选：`ec6c0571729796c9ccf2455fd9ef884040a619f5`，末节 W4/S4/H1 停止记录。
- 运行工具 HEAD：`20cf0ec87e7e0c068aaa61c33ad49014cae36f52`；六个产品路径的 Git tree 与冻结 `p6-s1c-exit`（`9f288ad50475030ddb496ad00b3b79f4abdc0082`）经程序比较相等。backend/worker 为原 V′ 镜像。
- 方法：`/home/dev/gdds-p6-w4-preview-stop-ec6c0571` clean detached worktree 只读审核；CT108 只读日志、JSON、快照及 SQLite（`mode=ro&immutable=1`），未取占用标记、未启动产品/测试、未改原卷。真实数据只输出计数与摘要。

## 1. 失败归因与停止规则

场景 `p6bw4s4h120261105a` 从 `2026-11-05T10:58:44.830Z` 至 `13:33:49.002Z`，exit 1、FAILED、failure_step 为 `v2-preview`。失败操作诊断为 `operation.pure_recompute_failed`；日志堆栈依次经过 recovery、job definition、Preview assemble、prepare_ready_closure、ReadyClosureDocument.build，静态错误为 `output_refs exceeds bounded document size`。该步约 53 分钟，尚未达到 11,300 秒预算，不是超时。

冻结源码的 READY output refs 上限为 4,096；Preview 在 build 前通过 unique_artifact_refs 去重。失败发生在被测产品运行之后，不能归为 DC68 的启动前命令错误或 DC66 第 5 项工具缺陷。保留失败记录，不以同产品原命令再试来解决确定性容量限制。handoff 记录其后未启动 FULL/STRESS 等正式场景；原运行不能作为完整成功测量。

失败时 assemble_state 尚未写入持久 artifact/checkpoint，故无法从现存证据恢复精确失败引用数和完整组成，只能确认去重后大于 4,096。不为得到精确数重跑 Preview，也不将容量上界当作实际失败数量。

## 2. 已成功闭包的独立核对

从 v2-preview 前 checkpoint 的 control DB 读取成功 operation 的 ready_closure_ref，按 artifact store 的 SHA256 路径规则读取对象，独立重算 payload SHA、字节数并与 DB 引用比较；两份均一致，引用 ID 唯一且排序正确。只读前后 DB SHA 不变。

| 样本 | refs | 字节 | 正常组成 | payload SHA256 |
| --- | ---: | ---: | --- | --- |
| v1 Preview | 2,528 | 847,834 | bundle manifest、canonical table-set closure、canonicalization manifest、comparison closure 各 1；risk content、risk manifest、STA manifest、STA rows 各 631 | `2277bf70d1c7749e292f6c9c44af64f6565d34451bb267d4a971938bcb9cd2cb` |
| repeat Preview | 910 | 282,866 | 上述固定四项；project identity 1；STA manifest 631、STA rows 274 | `cb8a827b7804e46a469112227c0c325893d69566d6816d6236bff7935709731a` |

这些成功样本不存在重复膨胀，不能据此推断失败闭包的精确数。正常 refs 包含完整性所需 manifest 和数据引用，不能删引用以适配旧上限。

## 3. 来源 checkpoint 与身份

原 run/state 的结束时间、exit/failure 已写完，起点为 `completed_through=v2-upload`，即 upload 完成后、v2-preview 开始前。两文件前 13 项 step_checks 均为 PASS 且相等；checkpoint 的 completed_through、volume_snapshots、volume_digests 三项一致，state 额外含 steps 和 elapsed_seconds，不要求整个对象形状相同。快照内没有失败 Preview 的完成状态。

独立重算三份快照目录摘要，与记录相符：

| 卷 | 文件数 | 字节 | tree SHA256 |
| --- | ---: | ---: | --- |
| backend-artifacts | 8,924 | 404,429,541 | `2c4da65980c4c0ff88395f516c995f99eefe18e0620bedb1315f865ad44d7279` |
| backend-control | 1 | 2,154,496 | `4424684abf3a8c17293139bf7f1c15d929b3bf7782405c1429a114d54f913022` |
| repository-service-data | 20 | 75,222,091 | `bd88913c65a50e8cd10a215d1cb4443dadad0847dcd3f5692e44fa604184c05e` |

快照路径均在本次 evidence/checkpoints/v2-preview 内；摘要核对后原 run/state SHA 未变。源 run/state 的 backend/worker config digest 及全部 RootFS DiffID 与原 V′ identity 记录程序比较一致；节点现存对应镜像的全部 RootFS 层也与保存记录一致。该事实绑定旧来源，不意味着未来 H 镜像必须或能够与 V′ 相同。

输入绑定的新根为 `w4-generator-correction-20261105b`。expected manifest SHA 为 `4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7`，input-summary SHA 为 `6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`；manifest 及其 census、accepted document、dataset manifest 依赖摘要均重算匹配。sampler 输入 provenance SHA 为 `ade6de414ade0785654f2f8713d0e4eec475a4b403288b024d07e7015d279944`，记录 MATCH。容量补审又独立核对当前三份 census，结果见[定值补审 §4](p6-ready-closure-capacity-kickoff-review.md#4-容量定值补审2026-11-05)。

## 4. 日志摘要及诊断更正

以下原证据位于 `/home/dev/gdds-p6-logs/baseline/scenarios/p6bw4s4h120261105a/`，SHA256 已独立重算并与 handoff 比较：

| 相对路径 | SHA256 |
| --- | --- |
| launch-w4-s4-h1.sh | `b626d02f526a185df32c1c47830e4556603f6b7e0e9ed2dabb2fca88e5ebbd24` |
| launch.log | `7aba50eea30d95af4c6c0920ae2f5ddd407279e93ad81132998d33c8f2dccfd5` |
| launcher-wrapper.log | `771293f6bd216bb6b4cb355c56c4e5c8123b2c251add518bba824b2e556f6443` |
| evidence/run.json | `7e7ff2debfb2ae290a52d642e10b7e9e52f0ffdf922df74a6cfba5d6c4f46ac3` |
| evidence/state.json | `5e91ebb6082edfd68fa06305ab720e6aaaa594291b71e388bbca50dcf65bc365` |
| resources.json | `7be9bb68b4cccbf9cbdd937ef2a8c78b24534f4250c75e8879124c4bf90ac762` |
| image-identity.log | `c8f998a17c7ce9623aee6318d2f6ab418d4d3bed203d5b0049f00c7c22e0e91e` |
| compare-state.log | `2cf1d64fe0060976155525b234ecc5ad516a657bfc6734de6d086970c5300f97` |
| compose/real-dump-t4-20261105T133345359843Z.compose.log | `daeef9f0cdbd0d74111010ba2b432c8876f9722e5fedd8d684579a21ad215726` |

校正诊断日志 `baseline/monitor/w4-ready-closure-capacity-20261105c.log` 重算 SHA 为 `df571d860d8ac6220c37884bd228067c06fd3a031d06520b32dc124f3aed670c`。初稿 0/0 是误取 step_checks 字段，checkpoint False 是比较了不同形状的整个对象；实际读取 outcome 和公共字段后均通过。旧 W4-100% census 的 False 属于作废来源，不属于当前输入；本次直接核验新根，未采用旧文件。校正日志末句“before v2-upload completion”为笔误，真实状态为 upload 已完成；保留日志，由 handoff 订正说明。

## 5. 处置与恢复边界

Owning 边界是 [P4 runtime READY closure](p4-durable-operation-runtime-design.md) 和 [R4 §9](p4-r4-jobdefinition-checkpoint-execution-plan.md#9-p4-r4-s2a--artifact-checkpoint-and-ready-closure-contract)：完整、有序 exact refs、size/digest、版本与一次性 CAS publication。这里的 4,096 refs 与 inline JSON aggregate 4096 是不同限制。

没有 DC80 时，产品容量修正超出 DC66 第 5 项，且失败 checkpoint 的同产品镜像约束及 DC64 共享设施默认整档要求仍存在；不能把常量修改自动归为工具修正。DC80 已明确本次限定例外，因此不再等待重复 owner 授权，也不默认全基准重跑。仅提高有依据的有限容量、保持 schema/格式/排序/digest/输出集合不变，在技术上没有已知必须丢弃该快照的理由；仍须用最终代码和新镜像证明。

容量定值已单独补审通过，可实施 32,768。后续完成 05 focused/五包静态、产品和限定工具代码审核、04 backend/容器门禁及 H 镜像身份核验；以精确 V→H 双身份关系保留全部其他输入/快照校验。审核恢复条件后，在新项目、新证据目录和新卷副本，从 v2-preview 开头运行全部后续步骤，复制后再次核卷摘要；不得从失败末态或原卷直接续跑。此前成功步骤按未受影响映射沿用并保留原始来源；受影响计时在 H 实测。

本报告不触发现场镜像构建、不宣称 H 已有验证镜像；镜像验证属于修正候选后续门槛。基准终审、S2a exit 仍未办理，原证据及快照继续保留。未推送、未改产品或设计正文。
