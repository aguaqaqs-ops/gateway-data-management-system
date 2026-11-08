# READY 容量修正：CT108 限定恢复终核

结论：**GO，无剩余恢复前阻塞项。** 允许原实施者按固定 runbook 的 DC80 命令，从 `p6bw4s4h120261105a` 的 `v2-preview` 前 checkpoint，在新 project `p6bw4s4h120261105b` 恢复 W4/S4/H1；启动预检、三卷复制后摘要校验及停止规则继续执行。2026-11-05 已先把结论直接发送实施会话 `01a193fa-ecf4-7782-b6e1-430856f414ea` 并抄设计会话 `01a1a628-e59a-7981-aad5-6bf31e919d38`，不再等待额外确认。本结论仅放行这次恢复，不代表恢复结果通过或基准阶段 exit。

## 1. 对象与方法

- 恢复候选 H：`e798ec87a37330250b0c051162e7962dba1daa60`；handoff：`5730ef68584cf99423cfb95a8fbb9b1f2d7c41e0`，`p6-baseline`。
- 接续依据：main `4307e49b9a00dfec937f7bc8cd8a0bdb16fe9e8e` 的 [kickoff §6](p6-ready-closure-capacity-kickoff.md#6-最终恢复核验的现有会话接续2026-11-05)。固定调用为候选中的 `vnext/backend/benchmarks/p6_s1b_measurement_runbook.md` §DC80。
- 候选在 `/home/dev/gdds-p6-capacity-resume-final-e798ec87` clean detached worktree 只读检查。经 BatchMode SSH 连接 04、CT108，直接读取节点原始日志及元数据、重算所列文件摘要、程序比较 manifest 与镜像身份记录；未执行测试、测量、镜像构建或全卷扫描，未修改既有证据或节点资源。
- 复用已通过的[容量设计审核](p6-ready-closure-capacity-kickoff-review.md)、[产品审核](p6-ready-closure-capacity-code-review.md)、[工具审核](p6-ready-capacity-resume-code-review.md)和 [04 停止及环境修复审核](p6-ready-capacity-ct04-gate-stop-review.md)。来源三卷实物核验按 kickoff §6 复用已有结论；运行时复制校验仍由已审入口执行。

## 2. 04 权威结果及最终 H 沿用

成功来源为 `a16439d7cf9a7d2d90ed7cb6da0330bd649e0fb8`，实际 runner worktree `/home/dev/gdds-p6-baseline-capacity-resume-a16439-04`。原始日志记录 hostname `gw-dms-test-04`、2026-11-05 17:03:56Z–17:13:52Z、起止 HEAD 相同且 clean，backend 并行 3,285 passed、串行 62 passed，runner/wrapper exit 均为 0。本次授权的 backend 包及其容器门禁通过；没有将它表述为六包全量 runner。

直接从成功 runner 日志解析 manifest，程序比较与保存的 source JSON 完全一致。再比较同一节点、同一 worktree 在 H 产生的 current JSON：两份 `components` 完全相等，均为 clean，`total_digest` 均为 `01165883e5a4b033996f27d8f60dec39168ffaa6ae37f3cf9731ff9a2b41148e`，比较结果为“可沿用”、`changed_components=[]`。操作日志记录相同运行环境、镜像选择和空 Hypothesis/pytest cache；postflight 记录 H clean、无项目资源及活动测试进程、8000 空闲，锁已释放。审核读取时 04 worktree 仍 clean。

`a16439..H` 只增加 handoff 文本和固定 approval JSON，未修改 `vnext/`、构建/部署边界或容器测试；H 本身单独提交的唯一文件是 approval JSON。已审工具候选 `cd9b75ce887d737327d0ee6611017b475040f856` 到 H 的 `vnext/` 无差异。按包闭包及镜像等价条件满足，可将上述 backend/container 结果绑定到 H，不因本报告重建或重测。首次 exit 1 的环境失败继续保留，不能替换为成功记录；其修正重跑已有明确授权。

## 3. approval、CT108 镜像与来源

04 在成功门禁之后，通过已审入口从目标 project tags 生成 approval，生成命令 exit 0。生成物、提交文件、CT108 文件 SHA256 均为 `09b0924196c4cbefa2fd64e3cb284f999771f69c5dba7c08e6de68345f052e95`。其产品提交为 `8132f1bfa6c657d2baa75ea5c51c1f86bc23c5ff`，project 为 `p6bw4s4h120261105b`，目标 `vnext` tree 为 `0ebce55391446c056d0cf1b259412d1ef5770d97`。

CT108 实际 worktree `/home/dev/gdds-p6-baseline-measure-e798ec87a37330250b0c051162e7962dba1daa60-ct108` 在审核读取时为 H 且 clean。程序比较 approval 的 `target_images` 与加载日志内 expected/observed 对象完全相等：backend、worker config digest 均为 `sha256:8f03a1fbcf8333ad752793d7ca1e8d9983c4b13a0956881be1c4f2e31749010b`，各自全部 15 个 RootFS DiffID 一致。CT201 归档 SHA `a4072b448219bd3b0b0a75d49d7e70681ba5e3fddf4aa0c8f01e695ebcd90561` 沿用前次独立审核并与此次加载记录衔接，没有以跨节点 inspect ID 作身份判断。

CT108 Repository Service 已用本机锁匹配 dependency-base 离线构建。构建日志的 expected/observed 与审核读取的实际 image labels 一致：revision 为 H，build-input revision 为 `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree 为 `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，uv-lock SHA 为 `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。此处确认部署目标身份，不宣称新增 RS 全包测试。

来源 V′ 独立身份日志核对两个源 tag 的 config digest `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1` 及各 15 层为 MATCH。V′ 与 H 是不同镜像，分别绑定原步骤和恢复步骤。

直接读取原 `run.json`、`state.json`、launch log 的 SHA 与固定预检记录相等，分别为 `7e7ff2debfb2ae290a52d642e10b7e9e52f0ffdf922df74a6cfba5d6c4f46ac3`、`5e91ebb6082edfd68fa06305ab720e6aaaa594291b71e388bbca50dcf65bc365`、`7aba50eea30d95af4c6c0920ae2f5ddd407279e93ad81132998d33c8f2dccfd5`。原运行 HEAD 为 `20cf0ec87e7e0c068aaa61c33ad49014cae36f52`，有结束时间、exit 1、失败步骤 `v2-preview`，之前 13 项检查全部 PASS。综合预检确认恢复 checkpoint 为 `completed_through=v2-upload`、绑定三卷；不用失败末态恢复。

源 compare-state 为 MATCH、issues 为空；绑定的 expected manifest SHA 为 `4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7`，census SHA 为 `04952cb5523b9b6d44530654994bcad2a692a132697cacc2f157a7e8c66eea67`。预检还记录固定产品转换、H 身份和目标 evidence 不存在；审核读取时 CT108 无运行容器。恢复命令继续使用相同输入、新 evidence、新项目及已审快照复制路径，保留 sampler、节点占用、离线/无代理环境与停止规则。

## 4. 本轮直接核对的主要原始证据

以下相对路径均位于对应节点 `/home/dev/gdds-p6-logs/baseline/scenarios/capacity-resume-h-20261105/`；SHA256 由本轮读取原文件重算。

| 节点 / 文件 | SHA256 |
| --- | --- |
| 04 `ct04-backend-container-gate-retry.log` | `cfb5c41161100506b76af8e52e0d0421b07baefa6bc8841b1335868a1f1e19b8` |
| 04 `backend-test-input-manifest.json` | `33ba83c5baaab7d0ff46aa495fe6913ba4f746f7f3508e0334522c7a6f84d275` |
| 04 `ct04-capacity-resume-approval-generation.log` | `dcfbde0fbb1a5fff73918a87fa53de5020fa5bf0ac4f2679ab8b7785f06d1ef2` |
| 04 `ct04-closure-compare/backend-test-input-manifest-e798.json` | `7e70e4c0a85adf6a249f8587b4645f583de13366f650d4466e91f23158cbe5c5` |
| 04 `ct04-closure-compare/backend-closure-compare-e798.log` | `175fec453531b74c044e4a17c302705e15ebd232e442aec3f8c8e984b569d746` |
| 04 `ct04-closure-compare/ct04-e798-closure-operation-retry.log` | `37d5bbe527400b1c9aaa4bc34ff3e415e1b9a4c17b7e138331c949c2b20f2b44` |
| 04 `ct04-closure-compare/ct04-closure-postflight.log` | `6b49f878fa34e7837c465702aaaa3dfa9388e5f132f9554b1e107e3fc2b691a6` |
| CT108 `ct108-load-and-verify-h-images.log` | `00fe0aa6fad45a2134ebc67eee7ae3afc28a3032a59b24727f9098a42ba50a2a` |
| CT108 `ct108-vprime-identity-final.log` | `a9a810940f506aa745ea078986c81541f84dcd903685bbf8be014f96730d892c` |
| CT108 `ct108-repository-service-image-build-and-identity.log` | `4faf2c492d1e853776b9943ff825769a9f63019d661124745270992c5838d6ca` |
| CT108 `ct108-final-source-preflight-retry.log` | `f7644e77a56e577338fbb815ce6a93ff110a9b30d7f977aa0416cbef020899a3` |
| CT108 `ct108-source-compare-state-retry.log` | `eae5b0b57ecf0e4fe978f7d87361ca0a87e67585596cef7b9557d327c13742fb` |

本轮只提交本报告，未改产品、设计正文、输入、源证据或既有审核；未推送、未打 tag。既有 H2/H3 等结论保持其原范围，剩余正式场景与最终 runner 仍由基准实施及退出审核处理。
