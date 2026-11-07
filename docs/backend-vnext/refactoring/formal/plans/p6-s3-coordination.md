# Phase 6 S3 实施协调记录

2026-11-07；本轮 Owner 已明确采用固定设计并授权 A→B→C→D→E 实施、修复、逐节独审及验收推进。正式退出、tag、push 另办；DC33 最终真实数据范围仍须退出前确认。本记录不代替实施交接或独立审核结论。

## 1. 起点与并行边界

- 首次核对 main=`d70230783683a5f82d5a14206708cdc8bc7153df`；`vnext` tree=`56720104af34a1eb677336f57bdbc07444a56615`，与设计代码起点 `5dde965a65` 相同。设计依据为 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，独立复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` 的最新 §5 为 READY_FOR_OWNER；历史 CHANGES_REQUIRED 不重开。
- 初始 tracked diff 只有他人的 `docs/frontend-vnext/fe3-kickoff.md`，staged/untracked 为空；随后前端会话提交为 `771cc083b002`，不计入 S3 实施。设计起点以来的其他基准、前端及证据文档亦不混为 S3 产品增量。未 reset/restore 或 stage 他人文件。
- 已核 `p6-s2b-exit` 附注：指独审 `9220f3cdec`，产品实际来源 `a6876d5600`、H=`3580e6649f`；S2b 功能退出完成。生产保持 N1、单 active、32 GiB worker envelope / 8 GiB reserve / 显式 M24 GiB。
- 已核 BE-a/d 联合退出最新 §15 与 tag：`p6-be-a-d-exit` 指 `77b9aeea74b08b527ef1c78637e0cbe000b60d2f`；实际产品 `49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`。FE3b/FE3c 与原基准独立，不因后端已退出标为完成。
- 现存基准与审核 worktree 全部保留，不修改其源码、镜像、卷、输入或证据。S3 不进入 S4/S5、前端功能、恢复状态机或部署旋钮。

## 2. 角色、写入与状态

工具提供四个并发槽（包含协调者）。不递归扩建角色；同节审核者连续负责初审、修复复审和证据核收；完成收尾后结束该节职责。

| 节 | 实施者 | 独立审核者 | 测试执行者 | 状态 |
| --- | --- | --- | --- | --- |
| A | `/root/s3_a_impl`，GPT-6-Sol xhigh | `/root/s3_a_review`，GPT-6-Sol xhigh | `/root/s3_a_test`，GPT-6-Luna max | 候选 `4d5a4b0d98ee` 在 06 验证中，待原审核证，不预记 GO |
| B–E | 各节新建 | 各节新建 | 按需、错峰 | 依赖上一节实际核收 |

A 实施者拥有 `p6-s3-a-contract-handoff.md` 与独立固定向量测试；审核者只维护 `p6-s3-a-review.md`；协调者维护本记录。各角色只显式 stage 本人路径，在 main 追加本地提交，不改写已引用提交。测试运行仅一个执行责任人，被测 detached worktree 全程不写入。

## 3. 节点与验证边界

首次现场检查 2026-11-07 17:16:47Z，04/05/06 的 BatchMode SSH 均 OK，无占用标记，Docker 无运行容器。首次进程/端口检索因节点无 `rg` 未形成完整空闲判断，交测试者以可用工具补核；不能将这次查询称作完整执行前检查。

CT108 有原基准的有效 `p6-baseline-measure` 标记（16:01:55Z 开始）及 W4-STRESS 三容器栈，8000 已占用。本任务未取得或移除其标记、未接管资源。06 仅先做只读环境预检，不占用节点等待候选。执行时重新核现场并原子取得本人标记，完成运行与收尾后释放。

A 只跑 06 Contract/focused 及适用静态检查；不跑完整 runner、全旅程或正式性能。后续 B/C 差分、D 接线与诊断、E 集中取证按已审 kickoff 收敛。所有测试、编译、lint、容器均只在专用节点，源码通过 LAN 同步，clean 已提交 worktree，日志在外并记录 hostname/UTC/起止 HEAD/原 exit/SHA。离线缓存、扩展强制重装和 build-input、工具链及镜像身份按 AGENTS 执行。

## 4. 仍待实际交付的事项

当前尚无 A–E 实施 GO、S3 产品 V、最终 H 或 S3 门禁结果。三视图完整摘要、风险上限重放、Arrow schema/raw golden、实际消费者迁移、预算 owner 与 FULL 驻留、操作内完整 key、安全 miss、唯一生产路径及旧代码删除均须逐节交付，不能用设计复审替代。

最终预计 rust/backend 受影响；其他包须实际闭包判定，不能口头 carried。阶段最终容器结果需实际绑定；runner 已执行的 Compose 不重复。最终真实范围拟按 kickoff：替换期 t1–t4 逐表差分，05 fresh t1–t3 功能旅程，t4 功能/容量及 W3/W4 根据 CT108 现场安排；退出前向 Owner 提交具体证据、沿用条件与待补项作 DC33 确认。S2b 的 06 全旅程用途例外不继承。

W3/W4 的 MO、FULL、W4 约 10% 混合变化和每表 100% 压力档、1 预热+3 正式测量、分项耗时及资源均未实测。无 CT108 窗口时可先 06 诊断，但不称正式统计或达标；W2 无行比较，不计作 S3 比较收益。未知、失败与待办持续分列。

## 5. A 固定候选与核收进展

初稿 `34f68dc0c0016aeadbba53cd8e0c11b8b5869bcd` 由独审 `2a5e2bf3d4` 指出 A-F1（比较/三族 records 的独立 expected、具体 nodeid/fixture 与执行映射不足）、A-F2（风险批接口未固定）。同一实施者在 `29e4c442305222e5e5b47b9023e3f6aa66f0d422` 补 C1–C6 映射、必要纯向量与最小风险 batch 签名；同一审核者静态确认接口缺口关闭、向量内容可核，执行证据仍待补。

执行前发现 shared_kernel 未安装 xdist，故 `4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec` 仅移除该包 focused 命令的 `-n 0`（backend 保留）。错误命令没有执行，不产生失败重跑或 DC68 证据。最终执行候选为 4d5a，包含新增 shared_kernel 测试；产品、golden、锁和 Rust 源均未改变。

06 测试者在 17:36:52Z 现场复核空闲后原子取得 `session=p6-s3-a-test-4d5a4b0d98ee` 标记，经 LAN bundle 同步候选并建立新 detached worktree，按 [A 交接 §4](p6-s3-a-contract-handoff.md#4-验证与边界) 执行 focused、三份 Rust 既有 Parquet 向量和五包 Ruff/mypy。当前没有结果，不能将预检或静态审核记成测试 PASS。测试期 main 的其他文档提交不改变被测 worktree。

A 容器决策为 rebuild=no：仅 Contract/交接与纯测试，未触容器边界；本节容器状态 deferred，不宣称当前候选通过或 carried，最近 BE-a/d image/product 来源只作历史引用。B/C/D 的生产接入及最终容器验证仍按规则进行。
