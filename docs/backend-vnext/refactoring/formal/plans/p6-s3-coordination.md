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
| A | `/root/s3_a_impl`，GPT-6-Sol xhigh | `/root/s3_a_review`，GPT-6-Sol xhigh | `/root/s3_a_test`，GPT-6-Luna max | GO，报告 `f28c89eff5ac`；本节三角色已正常结束 |
| B | `/root/s3_b_impl`，GPT-6-Sol xhigh | `/root/s3_b_review`，GPT-6-Sol max | `/root/s3_b_test`，GPT-6-Luna max | A 核收后已直接启动，待实施候选 |
| C–E | 各节新建 | 各节新建 | 按需、错峰 | 依赖上一节实际核收 |

A 实施者拥有 `p6-s3-a-contract-handoff.md` 与独立固定向量测试；审核者只维护 `p6-s3-a-review.md`；协调者维护本记录。各角色只显式 stage 本人路径，在 main 追加本地提交，不改写已引用提交。测试运行仅一个执行责任人，被测 detached worktree 全程不写入。

## 3. 节点与验证边界

首次现场检查 2026-11-07 17:16:47Z，04/05/06 的 BatchMode SSH 均 OK，无占用标记，Docker 无运行容器。首次进程/端口检索因节点无 `rg` 未形成完整空闲判断，交测试者以可用工具补核；不能将这次查询称作完整执行前检查。

CT108 有原基准的有效 `p6-baseline-measure` 标记（16:01:55Z 开始）及 W4-STRESS 三容器栈，8000 已占用。本任务未取得或移除其标记、未接管资源。06 仅先做只读环境预检，不占用节点等待候选。执行时重新核现场并原子取得本人标记，完成运行与收尾后释放。

A 只跑 06 Contract/focused 及适用静态检查；不跑完整 runner、全旅程或正式性能。后续 B/C 差分、D 接线与诊断、E 集中取证按已审 kickoff 收敛。所有测试、编译、lint、容器均只在专用节点，源码通过 LAN 同步，clean 已提交 worktree，日志在外并记录 hostname/UTC/起止 HEAD/原 exit/SHA。离线缓存、扩展强制重装和 build-input、工具链及镜像身份按 AGENTS 执行。

## 4. 仍待实际交付的事项

A 已完成接口与独立预期准备并获独立 GO；B–E 尚未完成，当前没有 S3 最终产品 V、最终 H 或 S3 门禁结果。三视图完整摘要实现、风险上限重放、Arrow schema/raw golden、实际消费者迁移、预算 owner 与 FULL 驻留、操作内完整 key、安全 miss、唯一生产路径及旧代码删除均须后续逐节交付，不能用设计复审或 A 准备结果替代。

最终预计 rust/backend 受影响；其他包须实际闭包判定，不能口头 carried。阶段最终容器结果需实际绑定；runner 已执行的 Compose 不重复。最终真实范围拟按 kickoff：替换期 t1–t4 逐表差分，05 fresh t1–t3 功能旅程，t4 功能/容量及 W3/W4 根据 CT108 现场安排；退出前向 Owner 提交具体证据、沿用条件与待补项作 DC33 确认。S2b 的 06 全旅程用途例外不继承。

W3/W4 的 MO、FULL、W4 约 10% 混合变化和每表 100% 压力档、1 预热+3 正式测量、分项耗时及资源均未实测。无 CT108 窗口时可先 06 诊断，但不称正式统计或达标；W2 无行比较，不计作 S3 比较收益。未知、失败与待办持续分列。

## 5. A 固定候选与核收进展

初稿 `34f68dc0c0016aeadbba53cd8e0c11b8b5869bcd` 由独审 `2a5e2bf3d4` 指出 A-F1（比较/三族 records 的独立 expected、具体 nodeid/fixture 与执行映射不足）、A-F2（风险批接口未固定）。同一实施者在 `29e4c442305222e5e5b47b9023e3f6aa66f0d422` 补 C1–C6 映射、必要纯向量与最小风险 batch 签名；同一审核者静态确认接口缺口关闭、向量内容可核，执行证据仍待补。

执行前发现 shared_kernel 未安装 xdist，故 `4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec` 仅移除该包 focused 命令的 `-n 0`（backend 保留）。错误命令没有执行，不产生失败重跑或 DC68 证据。最终执行候选为 4d5a，包含新增 shared_kernel 测试；产品、golden、锁和 Rust 源均未改变。

06 测试者在 17:36:52Z 现场复核空闲后原子取得 `session=p6-s3-a-test-4d5a4b0d98ee` 标记，经 LAN bundle 同步候选并建立新 detached worktree，按 [A 交接 §4](p6-s3-a-contract-handoff.md#4-验证与边界) 执行 focused、三份 Rust 既有 Parquet 向量和五包 Ruff/mypy。当前没有结果，不能将预检或静态审核记成测试 PASS。测试期 main 的其他文档提交不改变被测 worktree。

A 容器决策为 rebuild=no：仅 Contract/交接与纯测试，未触容器边界；本节容器状态 deferred，不宣称当前候选通过或 carried，最近 BE-a/d image/product 来源只作历史引用。B/C/D 的生产接入及最终容器验证仍按规则进行。

### A 最终核收与 B 启动

A 实测 V=`4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec`，交接 H=`b8c0697df2be6629fb62ef75abc68396e36206bc`（仅文档，`vnext` tree 同 V）；原审核者最终报告 **`f28c89eff5ac1e653facb21229c3b5a7d281f971`，A GO**。A-F1/F2 均关闭，无本节剩余 finding。具体接口、消费者、断言移交与原件见 [A handoff §5](p6-s3-a-contract-handoff.md#5-a-轮验证与交接记录) 和 [A 独审末节](p6-s3-a-review.md)。

06 focused Shared Kernel 132 / backend 40 / Rust 固定 Parquet 3 项、五包 Ruff/mypy 十项全部原 exit0，由原审从节点原件独核。最终索引为 `evidence-index.tsv` SHA256=`86974f17672252e85377d92f3ef41474e7ac149faa9ef66cbc3c87f447130093`；原失败、更正及事后完整 argv 补录均保留，不把补录称为事前脚本。两次无副作用自身命令错误不是产品测试失败：backend sync 前误用旧 Rust tree 的断言，及命令补录生成的 heredoc delimiter 碰撞。候选实际 Rust tree 与已安装扩展 build input 均为 `e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`；无 cache miss。

06 本人标记于 **17:56:56Z** 释放，release log SHA256=`ab398f9a814e915d288d55c867c9c529885af8985580b1b0f1714f339e39f905`。原审现场另核无标记/测试进程/容器/8000；候选 WT 与证据保留，A 三角色正常结束，无后台或节点占用。A 没有运行真实数据或性能，也没有切生产路由。

协调依本轮连续授权直接新建 B 实施/独审/测试三角色，加协调者仍为四槽。B 仅共用比较内核、单侧 ordered 摘要和对应差分/资源边界；先由实施者明确文件归属与内部 API，再固定候选并由唯一测试者在 06 执行。原审为复杂语义/摘要/资源边界使用 Owner 已允许的 Sol max。C/D/E 与 DC33 最终确认仍按原次序，不因 A GO 自动完成。

## 6. B 接口与后续测量准备

B 文件归属为 Rust `comparison/{kernel,standard,mod,ordered}.rs` 及必要测试/临时差分 adapter 与 B handoff；不修改 C 的 records writer/reader 或 D 风险生产接线。结果持有 cloned RecordBatch 的 Arc backing，records 使用 batch/row locator，C 接 Arrow builders。预算约定：context 的 remaining bytes 已扣 caller 预约的唯一 pinned/backing；B 仅预约自有编码帧、索引、排序和 locator 峰值，不能重复扣 shared backing。caller 在输出最后消费者释放前不得退 pinned charge；实际生命周期由 B 独审核收，D 再核 operation 接线。S2b canonical IPC 的 SET 是 Utf8 加声明 metadata，必须按声明序恢复 sequence framing，不能只在旧原型 List 布局上差分。

B 真实差分执行前核 06 实际八份 t1–t4 package 的 size/SHA，对照 datasets.json 与 P5 S4 handoff §8 已接受身份；已有目录或 S2b 的 INPUTS_VALID 不代替本次核验。B 只跑逐表差分，不是全旅程。

后续 D/E W3/W4 工具接线另需注意：当前 main 有 real_dump_journey 与旧 V1 consumer，但完整合成负载/测量工具留在原基准分支（只读核 `p6-baseline@b6070468f6dbf967bc763e9fe7f2d9a23b8bda50`）。该分支 generator 引用旧 parser grammar/storage-projection Python helpers，不能不经适配就当作当前唯一 Rust 路径已能执行。优先复用已核身份的现有输入或职责内最小工具适配，不合入整套旧算法或 evidence 框架；原冻结 worktree、镜像、输入和卷保持不动。此为测量准备提醒，不是已运行或新增核心方案，也不豁免 W3/W4 起测。

### B 首个 Rust 检查点

实施检查点 `3577df182d6481a9c6e49554e445c81071924c09` 仅四个 Rust comparison 文件，不是完整 B 候选。06 在独立 scratch 执行机械格式准备，格式 patch SHA256=`a89f43a7512a808a603eb2d998f17a66d4ed0ebaf28d2c59b1e1f1cd800170a4`，由原实施者在 main 应用为 `9b34be7356a92228ef07ee0c4f01bf215e2bf653`。准备期间相对 Git exclude 路径错误在未格式化/测试前退出，原日志 SHA256=`40f8c23f5af833b10b9c8b2256cda028a277a5fc8f853750b218451a07e2b479`；按 DC68 仅纠正为绝对路径后续行，原件保留。

06 对固定 clean 9b34 的 `cargo fmt --all --check` exit0；`cargo clippy -p gateway-compute-core --locked --offline --all-targets -- -D warnings` **exit101**，因 `ordered.rs` 未用 `ListArray` 与 `batches` 需可变借用。首次失败即停，`cargo test` **未运行**。这是实际编译反馈，不能按 DC68 重跑旧候选或记测试通过；原实施者已将两项普通修正并入后续未提交工作。

原日志 `/home/dev/gdds-test-tmp/p6-s3-b-test-9b34be7356a9/logs/rust-focused.log` SHA256=`c0eecef9412e267f98cef536d91025af4c5209db77ace24f790de27349fc8d6f`；运行前完整脚本 SHA256=`ac6809c5d528e567dfef2c5eaf345bfdee21607181f78c52daa9a47c2e6b3d48`。起止 9b34、WT clean、六锁不变。06 本人标记于 18:36:04Z 释放，release SHA256=`2df6ead5b7dfe9f21805f9d8a4662c01a99fb80086da50558c5ac4dbe0848708`；无本任务进程/容器/8000。保留本节自有 WT、Cargo target 和证据供后续 focused，非权威 carried 来源。

B 原审已对固定检查点提前指出并交原实施者：ordered 仍全值 Vec、0/N batch/空表 schema 不足、记录预约晚于分配与 scratch 退账不足、读完后的索引/LIS/排序/摘要阶段缺控制检查。完整 B 必须本节补齐；C 只接 Arrow builders，不承接这些未完成比较职责。当前不记 B GO。旧 Python 参照拟用 S3 自有固定 A 4d5 的独立只读 WT/venv 进程，E 删除临时 harness，不复制改名永久 oracle。

为流式摘要，B 可将已在 workspace 精确钉版且由 shared-kernel 正式消费的 sha2 从 core dev-dependency 提升为 regular；不改变 preimage、Contract、锁定版本。需实核 Cargo.lock/规定 dependency-base 输入保持及离线命中，E 因 Rust/生产 manifest 改动重建当前候选镜像，不称旧镜像当前 PASS。

### B 第二检查点与停止阈值

新结构检查点 `a4ff75362737ec4a6e15a2cb6f1ace836ea26657`（5 路径，含 sha2 提升，Cargo.lock 未变）经 06 scratch 格式 patch SHA256=`9db25424367720a7370701457c69f99033d0ea4441026396cf3b250505e22241`，成为 `b91767f5d794701cfebb49b83b64cf5a7130c09a`，待 06 fmt/core clippy/standard 8 case 反馈，仍非完整 B。原审在固定 a4ff 确认 locator、显式 schema 0/N batch、部分 scratch 退账及重循环控制已有代码；同时指出 I-JSON 数字 guard、normal/degraded 记录双源、实际编码 metadata 冲突及预算簇仍待修订。实施者正集中修复，不混入 b917 测试 WT。

预算簇按实质轮次而非候选命名计：**3577 原始问题 → a4ff 第一轮修订（b917 只格式）→ 下一固定预算修订为第二轮**。当前待修包括共享 slice 重复按整 backing 估算、retained metadata 已分配后 grow、scratch/retained 阶段计费。若第二轮原审后同一 M 不变量仍实质未解或持续引入相邻回归，按 Owner 两轮停止条件暂停受影响依赖并提交具体阻塞报告；不能因称“检查点”而免计。JCS 数字等不同根因单列。本轮仍授权完成集中修订和适用验证。
