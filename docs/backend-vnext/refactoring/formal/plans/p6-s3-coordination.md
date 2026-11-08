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
| B | `/root/s3_b_impl`，GPT-6-Sol xhigh | `/root/s3_b_review`，GPT-6-Sol max | `/root/s3_b_test`，GPT-6-Luna max | GO，报告 `17fd6739b809`；本节三角色已正常结束 |
| C | `/root/s3_c_impl`，GPT-6-Sol xhigh | `/root/s3_c_review`，GPT-6-Sol max | `/root/s3_c_test`，GPT-6-Luna max | GO，报告 `ce217c0ad777`；本节三角色已正常结束 |
| D | `/root/s3_d_impl`，GPT-6-Sol xhigh | `/root/s3_d_review`，GPT-6-Sol max | `/root/s3_d_test`，GPT-6-Luna max | Owner已确认恢复执行通道；集中修订与原审继续，未 GO |
| E | 下一节新建 | 下一节新建 | 按需、错峰 | 依赖 D 实际核收 |

A 实施者拥有 `p6-s3-a-contract-handoff.md` 与独立固定向量测试；审核者只维护 `p6-s3-a-review.md`；协调者维护本记录。各角色只显式 stage 本人路径，在 main 追加本地提交，不改写已引用提交。测试运行仅一个执行责任人，被测 detached worktree 全程不写入。

## 3. 节点与验证边界

首次现场检查 2026-11-07 17:16:47Z，04/05/06 的 BatchMode SSH 均 OK，无占用标记，Docker 无运行容器。首次进程/端口检索因节点无 `rg` 未形成完整空闲判断，交测试者以可用工具补核；不能将这次查询称作完整执行前检查。

CT108 有原基准的有效 `p6-baseline-measure` 标记（16:01:55Z 开始）及 W4-STRESS 三容器栈，8000 已占用。本任务未取得或移除其标记、未接管资源。06 仅先做只读环境预检，不占用节点等待候选。执行时重新核现场并原子取得本人标记，完成运行与收尾后释放。

A 只跑 06 Contract/focused 及适用静态检查；不跑完整 runner、全旅程或正式性能。后续 B/C 差分、D 接线与诊断、E 集中取证按已审 kickoff 收敛。所有测试、编译、lint、容器均只在专用节点，源码通过 LAN 同步，clean 已提交 worktree，日志在外并记录 hostname/UTC/起止 HEAD/原 exit/SHA。离线缓存、扩展强制重装和 build-input、工具链及镜像身份按 AGENTS 执行。

## 4. 仍待实际交付的事项

A 已完成接口与独立预期准备，B 共用内核和 C Arrow 记录/读写已获独立 GO；D 正在实施，E 尚未完成，当前没有 S3 最终产品 V、最终 H 或 S3 门禁结果。C 三视图/完整摘要/schema/raw golden 和 owner 的具体核收见 §9；风险重放、生产消费者迁移、FULL 驻留、操作内完整 key、安全 miss、唯一生产路径及旧代码删除仍须后续交付，不能用设计复审或 A–C GO 替代。

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

只读输入定位补充（2026-11-08，未传输、未重核节点文件、未运行）：上述固定分支 `p6-baseline-handoff.md` 的“输入准备结果”记载已接受 2×t4 包 v1 为 10,652,436 bytes / `74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c`，v2 为 10,649,536 bytes / `121dc3b0e0418a76e2563111970dd136cf00d0942c83f37b8cc19597995b6d20`。后续已验收 W4 输入根为 `/home/dev/gdds-p6-logs/baseline/input/w4-generator-correction-20261105b`，summary SHA256=`6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`；10% expected manifest SHA256=`4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7`。早期多个 W4 根已作废，不能凭同名目录或最初 1ed 根中旧 W4 冒输入有效；2×接受身份与后续 W4接受分开核。D/E 如采用，应从获准副本读取并向 S3 自有目录复制，重核实际包/manifest/summary身份及当前产品完整性，保原文件不动；这段源码定位不替代运行前核验或 DC33。

当前 main 的 `real_dump_journey._read_metadata` 固定读取仓库 P5 八数据集 census，因此仅换 synthetic data root 不能得到正确 W3/W4 验证。需要 S3 职责内最小测量入口/参数接线，直接复用当前 Preview/History/native 路径与已核的 synthetic census；不得改 P5 census/golden 或从旧分支整套搬回已删除算法。正式 1 预热+3 测量、中位数/范围、MO/FULL/压力和各段计时仍待 D/E 具体执行稿与独审核收。

2026-11-08 **00:14:57Z** 只读核 05（BatchMode OK）：上述 W4 summary 与 10% expected manifest 路径确实存在，分别 551,463 / 1,699 bytes；仅核文件存在/大小，未 hash、未传输或当作输入验证通过。05 当时由 `codex-p6-parallel-closeout-20261107a` 有效占用，00:02:48Z 开始做历史 baseline record/index。协调未取锁、未读大输入或操作其 worktree/资源；D/E 需要取用时重新按现场协调，当前 C 的 06 开发不受该占用影响。

### B 首个 Rust 检查点

实施检查点 `3577df182d6481a9c6e49554e445c81071924c09` 仅四个 Rust comparison 文件，不是完整 B 候选。06 在独立 scratch 执行机械格式准备，格式 patch SHA256=`a89f43a7512a808a603eb2d998f17a66d4ed0ebaf28d2c59b1e1f1cd800170a4`，由原实施者在 main 应用为 `9b34be7356a92228ef07ee0c4f01bf215e2bf653`。准备期间相对 Git exclude 路径错误在未格式化/测试前退出，原日志 SHA256=`40f8c23f5af833b10b9c8b2256cda028a277a5fc8f853750b218451a07e2b479`；按 DC68 仅纠正为绝对路径后续行，原件保留。

06 对固定 clean 9b34 的 `cargo fmt --all --check` exit0；`cargo clippy -p gateway-compute-core --locked --offline --all-targets -- -D warnings` **exit101**，因 `ordered.rs` 未用 `ListArray` 与 `batches` 需可变借用。首次失败即停，`cargo test` **未运行**。这是实际编译反馈，不能按 DC68 重跑旧候选或记测试通过；原实施者已将两项普通修正并入后续未提交工作。

原日志 `/home/dev/gdds-test-tmp/p6-s3-b-test-9b34be7356a9/logs/rust-focused.log` SHA256=`c0eecef9412e267f98cef536d91025af4c5209db77ace24f790de27349fc8d6f`；运行前完整脚本 SHA256=`ac6809c5d528e567dfef2c5eaf345bfdee21607181f78c52daa9a47c2e6b3d48`。起止 9b34、WT clean、六锁不变。06 本人标记于 18:36:04Z 释放，release SHA256=`2df6ead5b7dfe9f21805f9d8a4662c01a99fb80086da50558c5ac4dbe0848708`；无本任务进程/容器/8000。保留本节自有 WT、Cargo target 和证据供后续 focused，非权威 carried 来源。

B 原审已对固定检查点提前指出并交原实施者：ordered 仍全值 Vec、0/N batch/空表 schema 不足、记录预约晚于分配与 scratch 退账不足、读完后的索引/LIS/排序/摘要阶段缺控制检查。完整 B 必须本节补齐；C 只接 Arrow builders，不承接这些未完成比较职责。当前不记 B GO。旧 Python 参照拟用 S3 自有固定 A 4d5 的独立只读 WT/venv 进程，E 删除临时 harness，不复制改名永久 oracle。

为流式摘要，B 可将已在 workspace 精确钉版且由 shared-kernel 正式消费的 sha2 从 core dev-dependency 提升为 regular；不改变 preimage、Contract、锁定版本。需实核 Cargo.lock/规定 dependency-base 输入保持及离线命中，E 因 Rust/生产 manifest 改动重建当前候选镜像，不称旧镜像当前 PASS。

### B 第二检查点与停止阈值

新结构检查点 `a4ff75362737ec4a6e15a2cb6f1ace836ea26657`（5 路径，含 sha2 提升，Cargo.lock 未变）经 06 scratch 格式 patch SHA256=`9db25424367720a7370701457c69f99033d0ea4441026396cf3b250505e22241`，成为 `b91767f5d794701cfebb49b83b64cf5a7130c09a`，待 06 fmt/core clippy/standard 8 case 反馈，仍非完整 B。原审在固定 a4ff 确认 locator、显式 schema 0/N batch、部分 scratch 退账及重循环控制已有代码；同时指出 I-JSON 数字 guard、normal/degraded 记录双源、实际编码 metadata 冲突及预算簇仍待修订。实施者正集中修复，不混入 b917 测试 WT。

预算簇按实质轮次而非候选命名计：**3577 原始问题 → a4ff 第一轮修订（b917 只格式）→ 下一固定预算修订为第二轮**。当前待修包括共享 slice 重复按整 backing 估算、retained metadata 已分配后 grow、scratch/retained 阶段计费。若第二轮原审后同一 M 不变量仍实质未解或持续引入相邻回归，按 Owner 两轮停止条件暂停受影响依赖并提交具体阻塞报告；不能因称“检查点”而免计。JCS 数字等不同根因单列。本轮仍授权完成集中修订和适用验证。

### B 执行触发 DC68：等待 Owner 决定

06 在 b917 脚本已保存、实际 fmt/clippy/test **尚未启动**时，额外可选只读检查第一次因无 `rg` exit127；一次纠正尝试的 shell 引用又 exit127。按 AGENTS DC68 的“重做再次失败……停止交 owner”已停止，没有第三次执行、换角色或换模型绕过。06 本人标记于 **18:55:38Z** 释放，原 WT 保持 clean/b917，源 bundle、脚本和错误摘要保留。

可审工作单为 **`71e28c20eb`** [执行停止与恢复稿](p6-s3-b-execution-stop.md)，原审核者 **`063e94a727`** [停止复核](p6-s3-b-review.md)已核现场及工作单一致；后者仅执行停止审，**没有 B 产品 GO**。脚本 SHA256=`841e85777ed758fe85e2de4ebf4225985ea81efa44e1b19c7db872515b68ca1b`；错误综合摘要 SHA256=`60e8fc6c95ef2d677cb70babc7a6e64e4545d5c917a358071b99b39dbc21d3b0`（非完整原始 argv/输出）；release SHA256=`896fdef8270870edcf874ed51171a2c0a4d9906f1123c45c38a37a2d1a6e229d`。b917 没有测试结果，最近实际仍为 9b34 fmt0/clippy101/test未跑。

协调已向 Owner 发出异步具体问题：是否按原审已核最小稿恢复 06（移除可选 regex/嵌套引用检查，literal bash 已保存脚本，一次启动/首错停）。**尚未收到答复，未把预选或经过时间当授权。** 原测试角色结束本执行回合，无后台/本人标记；若获准恢复，唤醒同一 B 测试角色。B 静态修订及必要文档继续，依赖运行的核收与 C–E 不放行。

### B 静态修订继续

预算第二轮集中 core 候选 **`ac21ad4069abb08f162d9418a6426a63d7508974`** 已固定（仅四个 comparison 源）。实施者报告已补 slice 实际范围估算、metadata 构建前预约/临时退账、shrink 禁止事后 grow、normal/degraded 统一 record ref、仅小 metadata 的明确命名、流式 I-JSON 数字检查、实际编码 SQL/声明 kind 冲突及 columns-added 共有投影 multiset。standard 单测源码现 12 项；**尚未编译/执行，原审正在固定对象只读核第二轮，不能记修复已核收或 B GO**。

主线另有临时 probe/Python 差分与 B handoff 的实施者 WIP，不混入 ac21。临时 probe 只作替换期测试，旧 Python 参照用 S3 自有固定 4d5 WT/独立进程，E 删除 harness；不向 core/Python 新增未锁版本或永久 oracle。原审对双侧空表与整表缺侧、隐藏共有列/新增列、JCS 和完整 facts 重放的核点继续保留。

### Owner 放行恢复（2026-11-07）

Owner 对上述已审恢复稿明确回复 **“允许放行”**；DC68 本次恢复决定已取得，之前待决定的文字保留为历史。协调在 22:33Z 重新核 main=`1d5cc20884209df765c554631bc6ebdf26ead390`、worktree clean；`ee58afaf76ecf509384fb4e79c5cb1145ef40e1c..main` 的 `vnext` 差异为空，期间原基准/诊断的并行文档不混算 S3 产品变更。

暂停期间 B 已提交完整静态代码候选 `2e9758885a8179d0e8e90c9c90a7c244577b9ea2`、[handoff](p6-s3-b-handoff.md) `ee58afaf76ecf509384fb4e79c5cb1145ef40e1c`；仍未 fmt/编译/测试/真实按表验证，不是 B GO。原审报告最新 `ba818b0d8d` 的两项 ordered 诊断差异由后续语义增量处理，待同一原审核收。

协调已唤醒同一 B 实施/独审/测试三角色（合计仍四槽），先由原唯一测试者按已审 literal bash 稿重新核 06 现场并执行保留的 b917 脚本一次；原失败、摘要出处限制和资源释放记录全保留。然后对完整静态候选固定格式与执行稿，按影响完成 Rust/FFI/差分/逐表及静态检查。此放行恢复既有授权范围，不取消未来首错停止、缓存缺失与资源规则，不增加 tag/push 或 DC33 最终范围授权。后续每节核收后仍直接推进，不重复问日常开工许可。

### B 放行后的实际推进

原审 `6d924f719e` 已固定 ac21 第二预算轮静态复核：原重大 M 根因有针对性代码关闭，不触同根两轮阻塞；不能推导运行 PASS。后续 ordered 诊断/Utf8 gid-no 修复及临时 probe、合成/真实差分代码交接为 `2e9758885a81`/`ee58afaf76ec`，仍无运行证据。

22:35:01–22:35:15Z，原唯一测试者按已审脚本一次运行 b917：fmt0、clippy101（standard keyed `any` 闭包两处 usize 错误解引用）、test 未启动；起止 b917/clean、六锁不变、offline、无 cache miss。日志 SHA256=`5ba79e1bf4c38850f9f35ba1f1ae77b30364e863987eb2a1fefafc167a20cf74`，原审现场核符。22:35:56Z 本人释放，release SHA256=`e9b14dea0d77c0fee5442f9d12b6a06b84df32a69ab700d2558135f77786b41e`。详见[恢复单 §5](p6-s3-b-execution-stop.md#5-owner-放行及实际恢复结果)。这是普通编译反馈，已由实施者修正新候选，旧 b917 不重复跑。

完整候选 `a665a3c06304d2f9ac8d4befb27f7be6d2a4a3df` 包含两处机械编译修正及合成/真实差分的完整 ordered/blank summary、blank interval 六字段与 real degraded 明确失败；原审固定对象确认此前差分缺口代码层关闭。后续 Python 诊断向量 `20e226206d` 与 a665 Rust tree 相同。06 scratch 格式 patch SHA256=`efd2222e1b103154172a4b3cce94b4aa296115188253224a60fad1859cc25aa2` 已回原实施者；22:40:48Z 格式准备结束释放，release SHA256=`27c873168174f79cdd10ed18446f31fae3bf2557b075fe3f3886ca370d50b441`。新固定格式/多任务 N1-N4 最小向量候选随后统一验证；尚无 B GO。

### B 完整验证候选与执行稿

`39bfa7552ed4` 增加同一 context/pool 的 12 个并行表任务 N1/N4 确定性与释放、到期截止向量，06 scratch 机械格式应用后为 `cab0656d68dd`。启动前独审核出真实差分 CLI 缺 operation scope，且旧 benchmark helper 不符合当前 Preview API；实施者只在 B 自有临时工具修正，最终代码候选 **`4efa4b3ec5457e83e48d9fbf2e18245e67afdc51`**，handoff=`4921696b1235`，独审静态增量=`4241168e1c`。Rust tree=`8c7e096e6b9bae5ca12e12c66e79bbec59371146`，vnext tree=`aa640aafe3c5e50d2d72239c18591200668e8963`；本轮没有生产路由变更、golden/锁修改或 B GO。

06 同一测试者取得本人标记于 22:57:49Z，在原自有 detached WT 固定 4efa/clean。LAN bundle SHA256=`14dac6f836b15f69030a5e10dd5a695da692936fef52c9deba2bae333e4ddee3`。cab 准备时一次 `git bundle verify` 在非 Git 目录报错，未触被测对象；在仓库内纠正一次成功，原日志 SHA256=`b20e21701a211cd8bfa8378ee775eb05798e1ddaf14257b9b40a6b12d6562a61` 保留。

唯一执行稿 `/home/dev/gdds-test-tmp/p6-s3-b-4efa4b3/run-final.sh` 经协调与原审原件核对；在启动前将 toolchain 检查移至 `vnext/rust` 下读取仓库 selector，最终脚本 SHA256=`90f436b460b5f3228713d2860d6ca64b6df7732fa093158e54ce090b2d2d4825`，输入核验 helper SHA256=`dac92e185be66cba8178d1e4dbf779fb91fe9158a313b4b9ba27629d3b7555cd`。完整 argv、cwd、起止 HEAD/UTC、raw exit 和六锁均由脚本记录。顺序为一次 workspace fmt/clippy/test → 强制扩展重装与 build-input 核验 → 六项 Python 差分 → 八包 SHA 与 t1–t4 逐表差分 → 五包 Ruff/mypy；首失败停止，不自动重试。已授权同一测试者启动，实际结果待原件，不能把脚本审核记作 PASS。

本轮实际 4efa 在 23:05:08–23:05:25Z fmt0、workspace clippy101，`ordered.rs` 具名迭代器调用 `try_fold` 缺 `mut`，workspace test 与后续未执行；日志 SHA256=`ee3a15b125830433289684a5ee46334f6ac20286d18a4c07c195b10860791b38`，本人标记 23:06:17Z 释放。最小修正 `4f1bd419dc7d66da0cb1b8bd0c5de59c6df8587c` 经同一原审准入后，同一测试者复用本 B 外置 Cargo cache，以新脚本 SHA256=`deb6067775f1935b42c5746677d3254d59fc57996605b58ba95235637d0f636e` 唯一执行。23:08:53–23:08:56Z fmt0、clippy101，编译已越过该错误，现报 19 条 lint；workspace test、Python、真实差分与五包静态均未启动。日志 SHA256=`a42bdce9329c5d69aa532ba5c768d347bfc87a42fbc5a21b1784c04829251a29`；23:10:44Z 释放本人标记。两次起止 HEAD/clean、selector1.97、六锁不变均由原审从原件独核；普通编译/lint 修正不重开已关闭的预算根因，也不把未运行项记通过。

23:07:32Z 再次只读核 CT108：原基准 `p6-baseline-measure` 的 DC63/V5b 单次诊断有效标记于 22:33:24Z 开始，固定其自有 `d2ffe1ac...` WT，三服务运行、8000 占用。S3 未取标记或改动其资源；正式测量窗口仍未知，D/E 的 06 阶段诊断准备继续，不能冒正式结果。

## 7. B 最终独审核收与 C 启动

B 起点 `ecb96af0092999e54c5499f126ee1436e38ce7fd`，最终代码 V=`fbb7fca65d81ff61ecf0022e85da0bdf0f71ae9a`，handoff H=`4918cc5440d01d2a29224a164f1b56ab1ab1a4b2`。同一原审核者最终报告 **`17fd6739b809f048ac7b2f45cb784c144e2d98ad`，B GO，无剩余 B finding**。实际 11 个 `vnext` 路径及职责见 [B handoff](p6-s3-b-handoff.md)；区间并行基准/前端文档不混为 B。所有原失败、修正与预期来源均已列手册并由原审独核，未放宽 Contract/validator/golden。

06 的 2b 固定源 `2b629e4562166de706da984995fc2ebc14fb1252` 实际 workspace fmt/clippy/test、native 强制重装/input 校验通过；Rust tree=`cef7eaf099937a66ce33c160154936a5c086f0be`。该轮后续因临时逐表工具把 SNAPSHOT_ONLY 送入行核而 exit1，不能作为权威 runner/carried 来源；合格的 Rust focused 分项原件 SHA256=`28103b95e234a63dcc24eb1f36fcc641ac2aeb14de119f6def0d413413986f57`。503 修复分流后四档逐表通过，但显式工具 mypy 20 条错误首败；fbb 仅修两份临时 Python 工具/测试类型与关闭 helper 导入，Rust tree 相同。原审核收来源严格区分，不把整体失败稿写成整体通过。

fbb 最终受影响验证在 `gw-dms-06` **23:45:00–23:49:11Z**：build-input 与上述 tree 一致；Python 六例、八包 size/SHA、t1–t4 逐表差分、CLI 自身 mypy、五包 Ruff/mypy 全 exit0，起止 fbb/clean、六锁不变、整体 exit0。原日志 SHA256=`26826be79042550ee2e98f66f8e99b156b2696a27ad053b9e0f01992dd985b1e`；脚本 SHA256=`0c13f470981de362dc912db40315f9c4f7e7ac78db874b2ba18be5f11f99ce4e`。四档 planned=125/220/193/312，`row_kernel_checked`=9/72/76/145，predegraded 全0；行核字段含 unchanged ordered 单侧摘要，不能据此宣称双侧比较次数、读取数或性能收益。metadata/non-record/early-exit 分项见手册。真实逐表步骤 **23:45:01–23:48:49Z**，不是正式性能测量或完整旅程。

06 本人标记于 **23:50:26Z** 释放。释放来源为测试者原 SSH 返回，没有另造实时日志；原审核者随后独立核无 marker、无本任务进程，最终原件 SHA 未变。B source WT、任务 Cargo cache、全部日志与脚本保留；三角色正常结束。B 没有生产路由、HTTP/Contract/golden/锁/部署变更，没有 Compose 或当前镜像通过声明，最终 E 容器门禁仍待办。

B GO 后协调直接创建全新的 C 三角色，加协调者仍四槽，不递归扩建。C 实施者负责 records builders/完整 facts 与 JCS/实际 Arrow validator 与读写边界，原审仅维护 C 审核报告，唯一测试者执行 06 的固定已审 focused 稿。C 首先细化输入 charge、B result 与导出 Arrow 的生命周期和文件归属，随后直接实施；不以临时 JSON probe 充当生产 bridge，不加 tuple fallback/部署开关。C 实际新 FFI consumer 的容器边界另按 AGENTS 判定，不能机械继承 B 延期 E 的理由。

C/D 必须保住完整 facts payload、blank 私有字段和三逻辑视图；D/E 另明确迁移 non-record role `COLUMNS_ADDED` 的旧 Python `_read_rows`/Counter 热点，B handoff 已给可复用 keyless 接口与独立业务断言。最终唯一生产路径、风险/去重、W3/W4 起测、集中门禁、DC33 与退出交接仍为未完成事项。

## 8. C 检查点与执行停止

C 依赖快照 `573d58248f0dc90e27f1be79ac9f2802211ed738` 仅给 core manifest/lock 各加现有 workspace `arrow-data=59.1.0` 直接依赖边，同 C 原审核者在 fixed detached WT 已准入制品准备，非产品 GO。锁变化触发 CT201 clean 依赖基镜像构建与目标节点 LAN 预置；当前尚未构建/传输。core 编译反馈检查点为 `0194d145bf7c77c34225298df7b099480b61809c`，9 个 core 路径；PyO3/backend 仍在实施。

00:30Z 左右源码 bundle 准备首次缺 `archives/`，一次纠正后于 **00:31:53Z** 又 empty bundle exit128，触 AGENTS DC68。06 本人标记 00:29:58Z 取得、**00:33:29Z** 释放；source0194仍 clean，候选未传到06、06被测WT未建、Rust/容器/依赖base均未运行。原失败与来源限制、release SHA及具体恢复稿固定于 **`93589767ae`** [C 执行停止单](p6-s3-c-execution-stop.md)，待同原审核收后交 Owner 决定；不执行第三次 bundle 或用替代传输绕过。

只读图谱核定增量并非空（946个提交），Git本机手册明确裸提交 SHA 不满足 bundle 命名引用要求。恢复稿改固定 clean 源 WT 的字面 `HEAD` 全历史 bundle，不用裸SHA/负向基线，仍由原测试者唯一执行、原审核者核稿，后续首失败/缓存/身份规则保持。之前 B 的“允许放行”不自动豁免本次重复错误。

C 静态实现/独审继续：三族 builders、完整table/core JCS、真实 Arrow validator/写入/读取、budget与最后buffer owner均未完成核收；已知 JCS 分配前预约与读侧scope/生命周期问题在同原角色集中修订。D生产接线依赖C实际GO，暂不启动；其余不依赖运行的执行稿/交接准备继续。没有将未知记为通过。

### C 恢复获准（2026-11-08）

Owner 对固定恢复稿与原审 `08547dc6715645d7a615c49898ccf495ca8e3257` 明确回复 **“允许按已审恢复稿放行”**。同一 C 实施者、审核者和唯一测试者恢复执行通道，仍合计四槽；之前停止与原失败原件保留，不重复申请日常许可。

最新完整固定 C 候选为 **`9f6c9ffb16c6980a51784186236b0cc9b8fb15b4`**（首个完整候选1018之后的读写 admission 修订）。按已审恢复条件，测试者在新任务目录建立 clean detached 源/06 WT，三份脚本显式替换固定对象与路径并由原审快核，再以字面 `HEAD` 完整 bundle 传输，首轮只跑 Rust focused，不测试旧0194。共享 main 已有其他会话文档及 C 后续 WIP，均不触碰、不混入固定对象。CT201 dependency-base 五输入已由原审逐路径确认与573一致，实际构建、完整镜像身份和 LAN 预填仍待执行，不能记为证据通过。

原审核者继续核三族独立预期、native 取消/截止/GIL/M、真实读取逻辑损坏、最后 Arrow buffer owner 与 writer/JCS 分配前预约。普通缺口由原实施者补最小向量并另固定候选；C 暂无运行或容器通过结果，D生产接线、W3/W4与集中验收尚未完成。

### C 首轮实际反馈及当前修订

Owner放行后，字面HEAD完整bundle成功（SHA `6529d9a26434191719d877f7a1542475c23ce737821eb09812ab57c2a5d4a127`），06 node准备通过。固定9f在 **01:18:13–14Z** 实际 fmt exit1、clippy/test未启动，起止clean/六锁不变/selector1.97.0；原Rust日志SHA `c0f7ee16768bc9292666696d2864fd642d729f6e72b795c5cfc7f95628e4ebb6`。完整恢复与自身准备错误出处见 [C恢复单§5.1](p6-s3-c-execution-stop.md#51-实际恢复首轮fmt-首败非-c-go)，原件保留；没有新产品PASS。

`c30fd82022` 补C独立输入support及新入口排序/预算/损坏向量；`526dc49837` 修GIL向量为实际首批读取后后台线程推进/取消，均由原审静态核，需新完整候选实际运行。原审另发现读取的 nullable nested list 不能只用压缩后level/payload bytes推导Arrow解码内存，须用leaf `num_values`；这属于1018→9f读预准入第一轮修订尚有缺口，下一集中修订为第二轮，不能更名重计。builder每批Utf8/Binary/List的i32 offset须append前拒绝，是独立finding；整表不加2GiB假限。实施者集中修这两项后，再由唯一测试者在06独立scratch做机械fmt，原被测9f WT不写。

01:07:51Z CT108只读现场无marker/运行容器，尚未占用，不代表后续正式窗口已取得。01:14:24Z只读核已接受 `w4-generator-correction-20261105b` 根：summary SHA `6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`；2x两包SHA `74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c` / `121dc3b0e0418a76e2563111970dd136cf00d0942c83f37b8cc19597995b6d20`；W4-10%/100%包分别 `4cb82a16d7c7801a1d4ecf11828cf8e94a92ed95bd6f89293a75653164bbd27c` / `c6f7c5e74f48715d2e33e9efe32a5679e913caccd8f93398f3ad4d1322eb4ec6`，与既有独审来源一致。对应journey roots/census已定位；未复制、生成、测试或改原线。D仍须在自己的输入副本/当前工具上核实际manifest与census，不能直接沿用旧P5硬编码旅程预期。

## 9. C 最终核收与 D 启动

同一 C 独立审核者最终报告 **`ce217c0ad77783a4a3c0eba3f0033bce356aaa3c` §19：C GO，无剩余 C finding**。产品 V=`854d3888a9de49a666f209145756befec1dd2532`，handoff H=`c5bbc4544f97f7d1c2d7607a7b6d92265b92a67c`，详见 [C handoff](p6-s3-c-handoff.md) 与 [C review](p6-s3-c-review.md)。H仅文档；实际镜像来源仍V，不冒称H重建、权威runner或S3退出。C原实施者确认本人无WIP，main clean。

C累计关闭预算增长前预约、nullable nested `num_values`、每批i32 offset、实际buffer capacity/最后owner、PyO3边界、严格物理Parquet `element`→公共Arrow `item`无逐行转换重绑，以及完整facts/core重放。三原b64 golden的family/version/detail/count/content断言已移至实际Python Parquet→Rust reader；原字节与raw SHA未改，旧无生产consumer的直接Rust Parquet reader已删除。诊断原件 `71961e18b44a1ea5bdf798456c8ba24f393f274301ecbf2002cddc955a9fd2f9`证明canonical schema直写三族raw逐字同冻结输入；首差仅来自错误使用回读schema的测试输入，未批准格式变化。

Rust tree=`0866ac1223177d66cf13dc8b7389875c7bcb39b7`；实际workspace fmt/clippy/test来源为ab610e82日志 `1ba0d0f7da4a8d8e8127b6fa50d39fa7272daccd18e705fbe52524c0ba2f9f07` 的三个exit0分项。该整稿后来Python首败，**不是权威carried来源**。V854在06 **02:48:19–02:49:07Z** 实际强制native重装/input、C focused67、architecture50、五包Ruff/mypy全0，原log SHA=`12f07b3f5aa294cabb66d02e95c7de64c05e0882049369e2906aa994771e45d4`，起止V/clean/六锁稳定。原postflight/release SHA=`cec4684ab6ec752332783b90e018da6518d30258f77a3480c7e0b73698ff5657`，SSH0，02:51:27Z释放。

06当前镜像小门禁 **02:52:14–02:54:13Z** 实际0，vnext tree=`f2b1ca467434730482dbf0a85ba163b59eb2fb59`。offline Compose build backend/worker与镜像内真实Parquet→Rust smoke原log SHA=`97df5395210b420430519268a84c5daf0b74ab902d1f361bb3ed0ba6cbac9f3d`；两镜像config分别backend `sha256:15d83b25314b89a9625f39835970eae8ee24d22ada58ccc947a7d4deaab026ef`、worker `sha256:1ef7719fcbc443abffe52993709d9daefdc42afc8827b5b87e87a226798765a3`，各全13DiffID见identity JSON（SHA=`045ac22b1b2084c262f6cb78b6ea2fde761c370e9576e3aa26c4601b5b064696`），archive SHA=`1a5a447da032b35380ae332e74b591f31b5496ba09c1fced53b46f3f5c0a5d58`。六锁/HEAD稳定，02:54:13Z释放；最后资源只读核02:59:02Z无marker/本project容器，原log SHA=`af884dd793c33f7ae66fdfd6ba524144f5b7e04480d418731d9d23a7ee1325a4`。不是完整Compose旅程或04权威门禁。

新backend dependency base由CT201 clean573构建：tag `gateway-backend-deps:lock-ca0ba0a24a5e`，完整输入 `ca0ba0a24a5e96a435e14a6da80b26cc390d315722f0432be3affe9de3339085`，来源config `sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c`与全19DiffID及Rust base config/全5DiffID均独核；归档SHA=`fb30d4666cf5466c66ca464c9db7103457cec92f4eb9003980f6c1a2e3dfc136`。06 LAN/load核原件SHA=`c84aaade82bb2d52618d579e9afa634586c7dae2e1924b4b3c0160ffff083d11`，身份全同，非跨节点inspect ID比较。最终若E删未用Cargo依赖改变锁，须另按流程构建/预填，不冒沿用此tag。

全部原失败与修复、证据出处限制由handoff/review保留；ab原27失败实际为20 cast级联、3 raw测试输入、4错误DigestRef API，不能写成全是cast。C操作内API、producer/reader与独立向量现可供D依赖；**唯一生产compare路径、风险Arrow必要列、完整key操作内去重、FULL实际生命周期与W3/W4仍待D**。E仍须删除旧Python/probe与专属重复测试、冻结C动态旧expected、做04最终闭包/镜像门禁及DC33真实范围确认。S4/S5/FE/原基准职责不变。

C三角色完成收尾后结束；协调按Owner授权创建全新的D实施/原审/唯一测试者（最多四活跃含协调者），不等待日常再授权。D保持N1/单active/32GiB worker envelope/8GiB reserve/显式M24GiB；真实数据默认05、正式性能CT108现场核有效占用后取用，C的06小门禁不扩大完整旅程用途。

## 10. D 固定修订、取证停止与输入准备

D 首检查点 `f000e5b075408455a35e8ae3dededc28036c73c6` 仅在06实际运行 fmt，03:36:30Z exit1；clippy未启动，backend/native重装、测试、容器均未运行。起止f000/clean、六锁无漂移。run原件SHA=`6bd909e6ceeca3b168a078b0544c4a3e276be380de6c5895543ecc5a7a7a483c`。随后postflight及一次修正抓取两次同根 `FIELD=hash` 前缀解析错误均外层exit1；远端收尾SSH0，本人标记03:36:56Z已释放。新DC68停止依据、原件与缺少组合stdout原文件的限制、最小恢复方案固定于 **`7ca300def7`** [D执行停止单](p6-s3-d-execution-stop.md)。不追加f000比对或以C旧许可豁免。

原D角色继续静态实施/独审。第二固定产品检查点 **`5c47795062937a8db0315640a95ab763d2c2c8ab`** 包含17显式路径，锁/toolchain/base未改；原审在固定detached WT核f000 findings及跨节接口。5c无编译/测试/镜像结果，仍非D GO。首复审已发现去重会话首对误清声明导致不能命中，原实施者在后续WIP修订；人工重复key只证明机制，实际FULL和跨表0命中合法。

停止前，协调已从CT108已接受的 `w4-generator-correction-20261105b` 根只读复制2x、W4-10%、W4-100%的T4 v1/v2及metadata/census至CT201私有目录 `/home/dev/gdds-test-tmp/p6-s3-input-copy-20261108/source/`。源端本人短时标记03:25:00–03:25:02Z取得和释放，无测试/生成/原WT或镜像/卷修改。各root实际仅有 `packages/<T4-id>.tar.gz` 两包，虽然datasets.json列八个ID；不能把旧八包固定校验原样套用这些根。首次只读探路误假定 `<root>/<id>/package.tar.gz` 后按现代码查到正确路径，无产品或证据生成；不把探路错误写成输入缺失。

copy原日志SHA=`d5b7c112996317ae34a5305b34ae17c171c4ee53b9b942057db42885bf0eed60`，机器身份清单 `copied-inputs.json` SHA=`cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3`（13件：六包、七metadata，各size/SHA匹配）。CT201与源端时钟秒级差异不作性能计时。summary仍为§8的6b63，四个合成包SHA亦同§8；原输入绝未重生成或修改。本项仅输入缓存准备，**不是S3真实功能、性能或DC33通过**。执行通道恢复前不再做传输/缓存补验。

原D独审先以 `ffda001b01` 核恢复说明，随后对 `1719ca8f24` 固定的完整未执行捕获模板逐字核收，于 **`1bb081ea19`** [D review §4](p6-s3-d-review.md#4-dc68-取证停止与恢复稿独核)明确：最小恢复方案可交Owner决定，模板静态CLEAR并非D GO。协调已向Owner提交本次D恢复确认，未把此前C的许可或默认选项视作答复。等待决定期间仍只做静态工作；下一固定候选完整 source/node/run/调用字面稿需同原审核收后才能执行。

并行原基准文档 `1d4aa1dd63` 最新将Owner A分版本参考范围的测量交付关闭，仍保留九场景缺合法baseline、旧FAILED来源及其他限制，不宣单版本矩阵、性能目标或Phase6整体exit。S3仅记录此边界变化，既不继承其测量结果，也不据此推定CT108当前现场空闲或取得资源。

### D 恢复获准

Owner 明确回复 **“确认并继续”**，本单已审恢复范围的执行通道恢复。原D三角色连续负责，含协调者仍四槽；唯一测试者已收到恢复，待下一集中固定代码及原审完整字面执行稿核收再启动06。原失败和停止事实不改，不再为同一已授权恢复逐步索要许可。5c第一轮实修未闭的cache有效性/有限用途、旧错误优先级与诊断、Risk当前取消/截止等由原角色集中修订，下一固定候选复审；不能以称为checkpoint重计同根轮次。DC33最终真实范围和正式退出手续仍另按既定要求办理。

## 11. 集中验证与 DC33 待确认范围草案

本节范围草案已获Owner明确DC33确认（见下文），不是运行结果。最终候选固定、D/E独审及实际节点/缓存前提仍须满足。

- D先在06完成受影响Rust/backend focused、五包Ruff/mypy和当前镜像的小型真实Preview MO/FULL、History/Compose。W3/W4按已接受合成输入做Preview分段诊断，优先CT108现场可用时使用自己的WT、镜像tag、project和输入副本；不给06继承完整真实旅程例外。04/05/CT108于2026-11-08 04:09:07Z的只读探查无busy/running containers/8000监听，仅为当时现场，不作预约或最终前检。
- E删除后在06做受影响focused与静态检查，收敛后固定唯一产品V。最终04使用S3自己的clean WT；若没有合格来源在同节点同WT证明某包可沿用，就实际运行该包。不得为取得沿用去修改原基准冻结WT或凭源码相似口头carried。若六包均需运行，使用一次六包权威入口；其中Compose不重复运行。保留此S3 gate WT至最终H绑定及交接完成。
- 建议DC33最终真实范围为**05 fresh t1、t2、t3完整功能旅程，加CT108 fresh t4完整功能/容量旅程**，均在最终产品V，以既有八包输入的原size/SHA和census作独立业务预期。各旅程v1与重复Preview用MODIFIED_ONLY、v2用FULL（baseline→initial、initial→modified），随后Submit、真实读取/approve和History；`--scope full`表示完整步骤，只有`--v2-input-completeness FULL`表示Preview FULL。不把S2b t4旧算法结果沿用为S3验证，不继承06的S2b专项用途。必要的跨项目/replacement、小型错误及取消/恢复向量由实际受影响focused/Compose覆盖，不重复完整真实矩阵。
- W3、W4约10%混合变化分别补MO与FULL，W4每表100%变化补压力诊断；输入来自§10的已接受副本，实际统计与census须核当前工具支持的T4 pair。S3阶段诊断报告实际版本、分段、调用/读取/派发、内存和冷暖条件；只跑诊断时不宣正式READY目标或1预热+3测量已完成。若取得正式统计，严格保留1预热+3测量、中位数/范围、失败样本和CT108独占；S6正式取证职责与W3≤60秒/W4≤3分钟READY、完成≤10分钟目标不变，压力失败不记成功。完整旅程的Submit/History不为比较段统计无依据重复。

提出上述fresh范围的依据是本轮替换比较、records/JCS、risk和真实reader接线，S2b容量结果不能覆盖新算法。退出前会将具体范围、实际结果、沿用条件与待补项交Owner作DC33确认；此草案不提前豁免t4、W3/W4或最终门禁。最终H逐包闭包/镜像绑定必须在原合格V的同节点同S3 WT完成，直接引用最初实际通过来源和原日志。

Owner 对§11具体问题明确回复 **“确认 fresh t1–t4 范围”**。最终产品V在05 fresh t1–t3、CT108 fresh t4；各档v1/重复Preview为MODIFIED_ONLY、v2为FULL，包含Submit、真实读取/approve、History，N1/M24GiB不变。t4不沿用S2b旧算法结果；W3/W4的MO/FULL/压力阶段诊断另列实际结果与未知。DC33这项范围决定已经取得，不再等待或重复申请同一范围。此确认不代替实际运行、独审核证或正式退出/tag/push。

## 12. 1c25 固定候选与 CT108 缓存事实

D集中候选为 `1c25ea68e713fef8718ea499592628dc035a7e94`，Rust tree=`45acfe79a0b9bffdf701d5d42be590cba456f092`，交接初稿 `bd752e4c62`（随后doc补充 `5c066fbedd`）。原审固定报告 `bdaadf21f0` 保留reader ready→closed命中隔离、Risk可选key分配前准入和成功ORDERED+BLANK生产三族覆盖待修/待证；原实施者继续后续WIP，不能据此改写1c25。06首轮仅在独立scratch做格式patch准备，完整字面稿先由原审核收；截至本节记录还没有1c25编译/测试/镜像通过。

为与06准备并行，协调明确接管CT108独立cache-only准备，原测试者停止写该稿、仍唯一负责D产品测试。原审逐字CLEAR脚本SHA=`cfe4432e057f4ea56433bfda68f5539cc179d39aa58c9a749295eb62445a7b38`，保原rc的失败收尾只可释放精确本人session且无任务进程/服务的标记。协调实际运行于CT201控制端 **04:24:18–04:25:39Z**，CT108 `gw-dms-test` 本人标记 **04:24:22–04:25:39Z**，remote与overall exit0；无产品编译、测试、Compose或性能测量。

目标ca0依赖tag原本缺席（已审预填分支preflight42，非测试失败）；LAN传输 **04:24:22–04:24:42Z**，`docker load` **04:25:01–04:25:17Z**。源C clean构建提交573d5824、完整inputca0、tag `gateway-backend-deps:lock-ca0ba0a24a5e` 与源归档SHA `fb30d4666cf5466c66ca464c9db7103457cec92f4eb9003980f6c1a2e3dfc136` 均按原件绑定。目标核Rust base config `sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1`/全5DiffID、dependency config `sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c`/全19DiffID两个IDENTITY_MATCH；没有跨机inspect ID比较，也未覆盖现有tag。

完整控制端原log `/home/dev/gdds-test-tmp/p6-s3-d-ct108-cache-prefill/logs/prefill-ct108.log` SHA=`96c3f6db0b5cb0ac082b35860ddb109cef97d4c2e23933bf21699eb53b672ed8`，保全部DiffID、逐步原exit与释放时间；已交同原审独核。目标同名专用目录的Rust resave tar SHA=`0734b9e84dd0f73b6e6b9d3de9fd6b505f6bb98d849c125bcdac2b738a12941c`、dependency resave tar SHA=`839de70a848c40c1f7c3c8085f08b465f61b7a0e2603fa5403ae498376e54dc2`；重save raw字节不同不作为跨机镜像不等价。原基准WT/镜像/卷/输入未修改，新归档和日志保留，标记已释放。此事实仅为缓存准备，**不证明1c25或S3产品通过**。

## 13. Rust 组件实际通过与后端接线待验

1c25的06独立scratch fmt原件与非空patch经原审核收，patch SHA=`efacb52d13787fd7a5be809a1dd1c7ff7197f4cb2baaed53308637428395857f`，三Rust路径机械应用为 `0a7c9fe89278093c76aa245401428d47e5b28337`；这不是1c25 fmtcheck PASS。0a Rust tree=`439426056d3fce9fca6e9cb9e58de4aa4813fda8`。

06 `gw-dms-06` 固定clean0a于 **04:34:30–04:35:21Z** 实际运行 `cargo fmt --all --check`、workspace/all-target clippy `-D warnings`、workspace test，三步原exit均0，199 passed/0 failed，doc tests0；Rust1.97四工具同selector、offline/jobs4、六锁无漂。本人marker **04:34:28–04:35:21Z** 获取/guarded释放，remote/outer/capture0。同原审已逐项独核，这只核收该Rust组件，不替代后端、04权威入口或D GO。

原件在CT201 `/home/dev/gdds-test-tmp/p6-s3-d-0a7c9fe8-06/`：outer log SHA=`f3e8fefff8c4ef703a1b10dc6d047e5080c9f4004b06474165ce2be0a2d1b94e`，`captured-rust/rust-diagnostics.log` SHA=`3aeb269d6830b1cca6068b02de81a8c5f9621230804d3114c4d57dc732d81008`，标准manifest SHA=`25a68d9c3766e72342023164569453a8cc120981badae2ebd3593c057a1461ba`，capture收据SHA=`9562ee81cbf5665fa5e5410667bdf6ae904f16674b08e18590fa8e2274102575`，全部check0。

完整Python候选已继续固定为 `eaa508ce4f61c84e724c2c1c25afbcda3f07d4a8`，Rust tree仍4394，锁/base不变；ready→closed reader命中隔离、Risk key诊断准入与同池紧M safe retry、成功ORDERED+BLANK三族向量待当前06 native/backend focused实际核。原审撤回了4c Risk ruleset长身份误报：既有前置validator已冻结三身份字段；因此新增重复guard/专属重复测试已从eaa移除，保真正预算修复与向量。后续只对改变的Python接线和适用证据验证，不无故重复同树Rust三步。

## 14. D 实际接线反馈与最小整合授权

以下是后续固定候选的实际反馈，完整原件、逐步状态与修复出处由 [D handoff](p6-s3-d-handoff.md) 和原审核者的 [D review](p6-s3-d-review.md) 连续维护；不是 D GO 或合格权威 carried 来源。

- `7707042c44240b30ea4e33e7a56a8c7b7948bb62` 在06于05:06:49–05:09:04Z通过 Rust fmt/clippy/workspace test（199项）和强制 native/input；随后 focused 为10通过、1失败，原始 run SHA=`6e5a154001c623444958942e28416533bee37fe5fdecef8faa424df62bf665e5`。后续候选修订真实 artifact 绑定及诊断；原失败不改。
- `9ef4b0954a951a570d23320b9dbb8c86cf1ac9d9` 在06于05:29:13–05:30:40Z通过强制 native/input，受影响非串行 focused 为83通过、2失败，原始 run SHA=`887a8f65cb5461de0c0ee002fbb198fe0a57478fc9578936de7c93a3611a443f`。串行和静态未运行；不得将83分项通过写成整轮通过。
- `d67440b592bb583e15f91252b018d98e4ab3047d` 在06于05:39:28–05:40:52Z通过强制 native/input，两个 writer 向量暴露真实第一对比较已返回 `DEGRADED/ValueError/TABLE_DEGRADED`；原始 run SHA=`ed556507e89627e618b2a35df2f708de2b46c6956401c2ab93502485f382e70b`。日志未暴露底层 ValueError 文本。源码独核定位 fresh business Arrow 缺 canonical profile metadata；`CANONICAL_SCHEMA_REQUIRED` 是源码推断，不能冒称原始异常消息。
- 产品 `4b224865e42e4c3ea4a5d9d595a36ca34db0b874`（Rust tree=`bb3383ff30e538aa8f3f6beb3d1c879c524379ec`）补 fresh verified canonical backing 的 schema-only view：复用 canonical owner 的小型 FFI，普通数组共享，BIT 按列转换，持久化/已有或部分 profile 仍走严格 validator。不重新全表编码 IPC，不放松校验，不变 producer/public schema 与 raw golden。06于05:59:07Z首步 fmtcheck exit1，仅两 Rust 文件七个格式 hunk；后续 clippy/test/native/pytest/串行/静态均未运行。node raw SHA=`94b9b92f8e4c2e0453d7675697063ee003556f3c9654f888fbe0e854939a22a7`，outer SHA=`bcbdbc68d50f850a944b9b0c834fbb57d6b6526c9e5fe788bbd584c00ea9b548`，manifest SHA=`09d9a89f8365430b204425382084e3178f742089862add239d759aa76f4f9257`，capture receipt SHA=`b528c442de1b727a4fc56827bee4362b9fdefc8ca02edd0cca52fe3d4ad9920b`。原审已核；clean/六锁稳定、05:59:08Z释放本人占用。

原审另确认4b的必要BIT view预算存在独立高列数假拒绝：native portion先占用大部分M，随后每BIT列固定预约4MiB header，会使很小的宽表不能在M24运行。实施者集中修必要转换的真实有界计费及格式；不抬M，不通过少记native可用额绕过。普通独立finding不按“cache/M/reader”等大类合并为同根两轮；同一根因须依据具体修复与复审事实计数。

Owner 已明确回复 **“授权三项最小修复纳入”**：在D收敛后、E最终产品V冻结前整合下列已独审修复及必要验证。具体审稿为工作区外 `/home/dev/gdds-p6-logs/analysis-handoff-20261108/review/integration-review.md` 和 `implementation-plan.md`；它们不替代S3本轮独审和实际证据。

| 授权项 | 精确源提交与适配边界 | 本轮核收 |
| --- | --- | --- |
| GC claim间调度（P1） | `0c97cb9c09`、`eee60c165e`、`9704d0b286`：保初始GC状态，活跃claim/executor期间暂停，join确认后才收集，下一anchor前空闲收集；保现DC88 drain/续租/取消与attempt预算 | worker scheduler/integration focused及适用本机容器，最终代表性prepare仍用32/8/M24 |
| 冷catalog批COUNT与同key合并（P2） | `dae01d557e`、`4497ded8ff`：bounded batch16及ordinal校验、同key in-flight；保8项/16MiB和现timeout，错误清理，不缓存半成品，保独立import catalog路径 | focused及一次真实Dolt historical commit integration，最终RS门禁 |
| JCS bounded hash sink（P2） | `1f9731dfc3`：仅两处hash-only ChangeSet消费者改流式hash；原bytes API、错误、Unicode/数值/排序/digest保持 | shared_kernel JCS和MutationPlanning独立向量及最终受影响包门禁 |

不整条合并原基准分支，不重复移植已在main的READY32768修复，不搬诊断wrapper/旧资源设置/输入生成器。不改变N1、32GiB worker、8GiB reserve、M24GiB、冻结语义、golden或部署旋钮；不扩到S4/S5、FULL并行或ordered新快路。三项由E新实施/独审角色在同一整合候选中接收，逐项列来源、实际产品提交和证据；原基准冻结WT/镜像/输入/卷/证据保持独立。现四槽D角色继续本节，不另建第五角色。

## 15. D 新 Rust 通过、BIT 测试边界与阶段起测口径

`7378687f32ad68c7033df32da02cf3f2021b242a` 修必要view预算并按4b原件机械格式化。06于06:09:44–06:10:34Z实际fmt0/clippy0，workspace test101，core 73通过/1失败：新测试把IPC规范列序与decode恢复的descriptor列序直接比较。原件 node SHA=`29515003706993aa557ba46a063af343ec9b73b369a617db2edf352c3d91b55b`，outer SHA=`60883a8688f3d9ee278c37b65f026a9ca8fa7a3179eeaaa1bbe2c644b2164261`；后续native/backend均未跑，06:10:35Z释放。原审独核后，`2b3f80267238bd3a288c66313f3d830a4459b634` 只修测试构造：profile严格对照实际IPC文件schema，保独立indices断言，decode另断原descriptor列序；产品mapping/格式未改。

固定2b3（Rust tree=`b5f2439384d859bd32df3e3e24979f4f63f0f91b`）在06于 **06:16:49–06:19:08Z** 实际fmt/clippy/workspace test全0（合计200通过），强制扩展重装与build-input核验全0。受影响nonserial focused为 **88通过/3失败**；serial GIL和五包静态未跑。node原件SHA=`c34682da698f52965ccaa10761cc416dad32b0340f05539b7c0778d995b1c2ec`，outer SHA=`90c457b8e43f58b63a660d5eb7a0192ab9c8ba351d09e9dfff2aff12fb441faf`，manifest SHA=`f4c2f76d7f6197b745920c3c84e31f759600d956d62da43111340f67c6d27c03`（check0），capture receipt SHA=`d420fcddfbeb18ae1ae9387a37f3c55e5a4c4afb0fb06751b843c767041f214b`（exit0），bundle SHA=`f755a4f4049d2ebfad278bf03e7b1932b8f13e4e88a6566673e7b84a62a446d9`。本人标记06:19:09Z释放，起止clean/六锁稳定；同原审已核原件。整轮exit1，不能作权威carried来源。

两BIT失败均在测试的 `table_set.tables[0]` 处IndexError，尚未进入新view/native/M。源码独核确认当前business→storage projection显式不接纳BIT，故旧普通artifact helper的输出为空；本节不得为救测例扩S4投影。修订限BIT专例：READERS_REQUIRED的既有business Arrow经真实canonical publisher，再测试fresh view/持久读取；明确只证明C writer→D adapter对该类型的能力，不宣称当前Preview投影支持BIT。第三失败是pair_pipeline直接导入comparison.artifacts/production，改用comparison公共导出，不扩architecture frozen baseline或豁免。普通writer modified/added两条实际路径断言保留；修订仍需原审核和节点运行。

D的W3/W4起测可在06做明确标记的**选表组件诊断**：保完整输入binding，从完整计划选最大可用Standard/Ordered表，用派生单表task跑当前生产compare→Arrow records→Risk；不修改快照身份/summary/table_set，不输出完整pair/Preview/surface/READY结论。MO为v1→v2；FULL样本明确baseline=v1、initial=v1同对象假定，不能证明真实FULL峰值或收益。保输入/census、选表范围、实际调用/读取/分项、账本high-water及原失败；InMemoryArtifactStore的RSS不证明生产worker envelope。100%压力失败如实停报。完整负载、当前部署Preview、projection/bundle独立计时、DC33 fresh旅程与适用正式统计由E/CT108承接；D部分结果不得冒充完成这些未知项。现成 `real_dump_journey --scope t4-identity` 含v1 Submit/Archive准备，只能在CT108按职责使用自有资源，不借partial名称扩06完整旅程用途。

## 16. FE3c Q18 与生成时间预期：当前事实和建议交接

Owner 于2026-11-08转来前端两项问题，要求核是否修复、建议环节和回复。本节是源码核对与具体修复建议，不是归档API变更实施授权，不改变S3已授权的三项最小整合范围。核对代码起点 `af7f145ef931d1aa35e1ba6461ae331010774e9d`，相关归档/审核接口尚无后续产品变更。

**Q18仍未修复，是实际接口可用性缺口。** `CloseSubmissionRequest.expected_review_version`必填，manual_close将其与review projection的optimistic_version做CAS；review GET先经过 `assert_review_permission`，只有archive_submission不满足审核读取权限。`ArchiveCandidateResponse`只有submission_id/expected_candidate_digest，预检和History也未提供关闭用review_version。现测试的 `_archive_permissions()`含review_submission，关闭body写死1，不能证明archive-only调用者可以独立取得CAS值并完成关闭。不得要求前端猜1、放松CAS或给归档身份额外审核权限来绕过。

建议作为**独立BE-Q18接口补缺**，在FE3c关闭功能接线/验收前完成，不塞入S4/S5，也不无授权混入S3冻结HTTP接口。推荐在归档候选只读响应中逐候选增加 `review_version`，从现有同一读事务的权威review projection取值；前端以它填写expected_review_version。仅扩读模型/DTO，不改变candidate digest、归档选择/关闭fingerprint、CAS或审核读取权限。先固定owning Contract/OpenAPI的精确字段与scope，再由归档后端实施/独审，06跑archive-only读取候选→取得版本→关闭成功、stale版本409、scope拒绝；随后按接口影响完成静态/容器验证。前端收到固定后端候选/独审结果后刷新生成类型与mock，再定稿FE3 kickoff §16.6并跑05 R12。本文不把该建议标为已实现、已测或已解除FE3c前置。

**生成时间项是预期修正，当前不需要改后端语义。** `derive_archive_business_validation` 对每个实际上传侧调用 `_append_time_quality`，与baseline是否为None无关。MODIFIED_ONLY的INITIAL_EMPTY/BASELINE_REUSED侧不当作上传侧；MODIFIED仍检查，FULL则检查两个上传侧。空INITIAL只使相应来源/基线比较不适用，不免除上传侧时间质量。因此合成A没有saved_time时，预期为一项 `GENERATION_TIME_MISSING`、side=MODIFIED。FE3 kickoff §4.6已按源码修正表格并注明未经产品实测；05首轮对完整issue集合实测、不符即停交设计判断的安排正确。不要补造时间或改后端使错误的“零异常”预期通过；带有效saved_time的真实t1须按其输入事实另判。

给前端的建议口径：Q18确认存在、仍是FE3c前置，不影响FE3b；建议独立后端补缺并返回归档候选review_version，在固定修复交付前不假定可用。生成时间修正与当前源码一致，保留§4.6预期及05实测停止规则。S3既定实现/审核/验证继续推进。

## 17. D 功能与静态收敛，容器和组件诊断待运行

固定 `ce8c5d6fcd50b81edb219fd4d14a13d862107a77` 在06于06:35:58–06:37:36Z实际强制native/input0、受影响nonserial **91通过**、serial GIL **1通过**；前三Python包Ruff/mypy0，backend Ruff唯一公开导出F401使整轮exit1，后续未跑。原件node SHA=`6531473682243f9b39d7f682e9983749b6f55cc880c1830f093081e8b531fb4a`，outer SHA=`b19d5b4a1041c26f9ff31b53021292d0ec7cd61d0126110e0cb2f9ba8b7e1c63`，标准manifest SHA=`d244e04ad31fa1a570fd7d48d7d97f428fa9cf7c65419f8427367c574431b8e4`，capture receipt SHA=`f7a5e9d0881bcad66093656752aad968f7231102a7199c703221b9b4a9e2564f`。原审已核；不是合格authority carried来源。

`90cb4379d2` 只补公开导出后，在06于06:47:17–06:49:01Z实际静态首败揭示17项类型问题，含两个具体运行缺口：Preview去重预声明使用domain枚举而identity评估返回capability枚举，实际pair pipeline本已正确，但不同项目会被预声明为DETAILED、产生无用途key/task；metadata-only BLANK publication误取标准记录字段。实施者修正确身份与三族字段准入，并补两项验证；无handle的完整Standard/Ordered行不进入小metadata路径，BLANK能力保留，不建设Python算法fallback。

固定 `af7f145ef931d1aa35e1ba6461ae331010774e9d` 在06于07:03:38–07:05:24Z实际两项业务 **2通过**、architecture **1通过**、native/input0；前三包静态/backend Ruff0，backend mypy仅新增测试引用的显式export问题1项，RS静态未跑。node SHA=`b624635906c188dc2e35eae057afd0057aa4c130c2d1e2b6c52517dac0ea5dc5`、outer SHA=`5b698d1786bb79d305c621bcdf31293644659162a62fbd41de98befd1d9112f0`、manifest SHA=`0c9b1263a8002eb254ef2e600facdaa8f10812345a0294b4575da040b5995caf`、receipt SHA=`28c16d72c076a0dab638e59e37a36bcda84131c5b2a5c68fcd1e117a676cd7d3`，标准check/capture0、07:05:25Z释放，clean/六锁稳定。FULL向量同时核预声明mode、replacement实际native_calls=0和持久化identity_pairs；BLANK向量核无handle Arrow closure与旧writer逐字同字节。

当前产品 **`a9da0c59277e3179f34d646eabcd9c185917ae05`** 仅再改测试从定义owner取原函数，产品逻辑同af7f；Rust tree仍 **`b5f2439384d859bd32df3e3e24979f4f63f0f91b`**。06于 **07:10:17–07:12:04Z** actual fresh offline native/input及**全部五包Ruff/mypy均0**，整稿outer/remote/capture均0。node SHA=`93e0337318808eee63e6194d764b9dd718270ffac3d91e0edbe5a42540c50bec`，outer SHA=`03413c472dc9ffe47e970a260598655982b2cd5307511d411c9d554d6f3236a7`，manifest SHA=`38e14c37ed6b241f8d152ff38e87dcea84e5d2b01a475248ca5910da440c2495`（check0），receipt SHA=`f4329904a6c717b77300720686528f6a112c164988de03ca8588562881678976`，bundle SHA=`3532f8e60d3570fa285986a3c7fb36a199630241a75b9ba997ac011ebdbf6a7a`。起止clean/六锁稳定，07:12:05Z本人marker释放；同原审已独核。只跑静态的成功稿也不是权威runner来源。

下一D核收是a9当前镜像小Compose的既有普通Standard Submit例和ordered FULL/History例，及固定外置脚本SHA=`f5330d9e5f306719a0e3a87cd4265cf69a65198743eba006a1387e18466b0218`的W3/W4 selected-table起测。MO由focused实际native/application路径覆盖，容器分工不宣MO container已测；E最终fresh MO/FULL再补部署范围。外置脚本逻辑静审CLEAR，但完整节点外层/accepted13项输入身份须另核；当前两项均尚未运行。D仍不是GO，E尚未启动。镜像最后实际验证来源仍C的854d3888，不冒称a9已构建。

## 18. D 独审核收与 E 启动

§17保留当时状态；现由后续实际证据更新：D 产品固定为 `a9da0c59277e3179f34d646eabcd9c185917ae05`，Rust tree=`b5f2439384d859bd32df3e3e24979f4f63f0f91b`，handoff=`d1aad819be5e632a66f0f8cbbd3722a5ebafee36`；原独审在 `055707a98436128c7484c92877df3fc17d33035f` 的 [D review §35](p6-s3-d-review.md) 签署 **D GO**。该结论接收本节适用 focused、静态、两个小 Compose 选择器与 selected-table 起测，不代替 E 的删除审核、04权威门禁、DC33 fresh四档或完整性能取证。

06小Compose实际为两段独立原件：首次Submit **1 passed**，随后Ordered未启动而整体exit0，原稿不能记两例通过；保留该范围错误及原始SHA，并按Owner恢复执行已审Ordered-only修订稿，实际 **1 passed / 54.41s**、显式完成和原exit0。Submit原件SHA=`11b7b985f05dac434ecf579000a389569190f88bb6746af56a4c1755d99c6299`；Ordered原件SHA=`411fa24578db3b8be8285aef811e428f41e998a1d5af831c53d273b64da1c054`、外层SHA=`c4d263ff779ded4353ae45e11f05b26b6b0b9e7969dcff7e7fe8c89322530adf`。a9当前backend/worker与RS完整镜像身份、原始命令、收尾、失败闭环由D handoff/review直接绑定；这不是当前E镜像结果。

06 selected-table修订稿于 **08:11:01–08:19:55Z** 对2x、W4约10%、W4 100%各MO/FULL共六项实际exit0，完整计划631表中仅选Standard 92,428行与Ordered 9,822/9,828行两表。原始node SHA=`20271ee0fc5dff6c3c0560be00773ed365a32c02e0b4e1eba75176faa0abe8d9`，outer SHA=`11d33b96d59db5a743f11b64022a8e31021a5263250ec14e93c5d4a2821a3a7f`，标准manifest SHA=`60105fc5e5b322a77d32378658554f7469e947123a3313330fe0af285b77a26b`。初稿在uv wrapper拒绝外部脚本时尚未进入诊断Python，原失败保留，修订显式离线lock-check后使用同clean WT已安装解释器，不修改消费wrapper。六项仅证明组件起测；FULL的baseline=v1/initial=v1同对象假设、InMemory store及未归属cgroup历史峰值均保留限制。

2x变化对comparison **48.292s**；native records build **38.291s（含JCS 8.273s）**；publication **0.299s（含Parquet 0.256s）**；Risk **47.022s（含必要Arrow转换2.829s）**。这些包含关系不能相加成独立分项，0.299s也不是全部records成本。10%/100%的Risk约2.738s/26.948s。该局部2x结果对W3 READY目标构成性能预警，但没有完整Preview/READY边界，不能正式判定目标通过或失败。E在现役入口补最小rules/report-JCS/publication、projection/bundle分段，并据完整负载作DC47语言边界评估；不据此自动迁Rust或改N/M。账本high-water不是物理峰值，selected压力成功不是完整容量通过。

Owner最新“允许3次自行修复尝试”已在 `c47f2fccd014a7799fda613d611149b23a640407` 同步AGENTS、testing-conventions与DC68现行补充，并获原审核者静态CLEAR。首次工具/操作失败后，同一具体根因最多三轮修复、适用独审和受影响复验；仍首败停本次执行、保存原始exit/日志/SHA、确认安全收尾，不无修改重试，不重计同根，不放宽产品/frozen/身份/缓存边界。历史停止稿不再作为“一次即停”的现行依据。

E已按生命周期创建新实施者Sol xhigh、新独审Sol max与唯一测试者Luna max，连协调共四槽，D角色已结束。E独审初稿为 `6fae419575` 的 [E review](p6-s3-e-review.md)，尚无E GO。三项最小整合已分别固定为GC `028aff2da7`、catalog `c6a2792901`、JCS `968e8ec7ee`；独审首轮确认精确源包与范围，实际测试仍待执行。下一步先从06固定旧a9源冻结C/D的独立expected，再删除旧行算法、writer与替换期桥；不从新Rust结果反填预期。最终V、H、门禁、fresh t1–t4和完整W3/W4仍待集中取证；FE3c Q18仍按§16独立交接，未混入S3。

## 19. E 独立预期冻结与集中取证准备

原独审已在 `80d71e4983b97e366d9035fcf9ca99298fa6ee04` 的 [E review §5](p6-s3-e-review.md) 核收旧来源 **20例facts/records预期**。06 `gw-dms-06` 固定clean a9/Rust b5f于09:06:34–09:08:00Z实际强制native/input、pytest **20 passed / 2.25s**、六锁无漂及本人marker guarded释放0；outer与标准capture均0。每个expanded nodeid一次旧Python调用，原审逐项重算20 input_digest、21 table digest、18 records项，并核C三族raw b64及D ordered blank-only/旧Risk、C/D两对相同输入的一致性。来源是固定a9的旧Python及4d5算法血缘，不是新Rust输出。原始JSONL SHA=`7c629fdbe64bc4ffb016135accd86cc74edacd93cd7b32347d4ed2364e0027f9`、collection SHA=`ccbec5bde3ea187888ddd5ee065ca040cf259ce3f0810dadd6b485ffcf0812a3`、node SHA=`96fde94d2382461f22e1b5e2e1e9fe3b7704875178b99bcfefba6103230e5e59`、outer SHA=`b8fcd5e89418cfc4cc7ad69b506d69c1e93e4a116849db0007de8a6ded62153b`，标准manifest SHA=`85546cbc385fa612e30f8908dd69739feeac102eb5bb774414dad604c9eace9d`。原件保留在CT201 `/home/dev/gdds-test-tmp/p6-s3-e-old-freeze-outer-a9-20261108-r3/` 与06独立来源WT。

冻结仍有**明确补项**：D keyless COLUMNS_ADDED/UPDATE_ONLY单例原有旧Risk摘要断言未被r3插件捕获；其facts/records已核收，但Risk断言删除边界暂扣。实施者从同a9旧源仅补这一nodeid、绑定原input/core/table及rules/options/digest，原审核收后再固定该断言，不用删断言代替补证，也不重跑已合格20例。其余只允许先提取最小必要固定值并提交独审；20例取证不是E产品GO。

此前r0缺Node主仓库a9对象、r1默认clone不抓custom bundle ref而为空bare、r2私有库未忽略legacy导致dirty，均未进入native或pytest；原失败日志/独立postflight保留，标记均释放。原审按现行DC68代码传输/检出准备例外判0/3，不将这些记成产品失败或成功；最终通过稿显式full-history bundle、bare init+精确fetch、private exclude及clean链接，不再借Node主仓库对象或metadata前提。

E的现役consumer迁移按每项职责静审并待focused实测：census改真实native handle计数；replacement测试直接调用独立replacement owner；Preview取消测试挂现役Arrow writer；planning与non-record role保schema/key、存在性、共有列和变化计数断言。Rust direct Parquet/core dev base64已裁剪声明，shared-kernel实际base64消费者保留；06仅在独立scratch从旧lock离线最小裁剪、逐一核所有保留包身份，commit新lock后才在CT201构建新dependency-base。五包静态、受影响focused和Rust三步仍待当前整合候选实际运行，不能把静审当测试通过。

最终权威范围已由E原审确认：04本S3自有clean WT **六包全部实跑**，无合格D 06权威carried来源；同次Compose不重复。V→H再在该同04 WT逐包/镜像实测沿用。05 fresh t1–t3、CT108 fresh t4沿用Owner已确认DC33范围，v1/repeat MO、v2 FULL；分别保同worker生命周期、32/8/M24资源与真实业务结果。协调者准备相应外层，未固定V/base的草稿均拒执行；不会把准备文件存在或节点只读空闲写成门禁通过。
