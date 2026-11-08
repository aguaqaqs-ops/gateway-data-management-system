# Phase 6 S3 C 独立审核

**当前结论：C 固定候选 `20fbaa2decc1a934f7e1316be5e0810984cf6f2f` 仍无 C GO。** Owner 已允许按已审 [C 执行停止与恢复稿](p6-s3-c-execution-stop.md) `93589767aebfa889a5d1244afd34bb54642bc575` 恢复执行；这只恢复测试通道，不是产品通过。旧 9f 在 06 fmt 首败、bca 在 clippy E0609 首败、bd 在新增 lint 首败；20f 的 fmt 通过，clippy 又发现 PyO3 三处编译错，workspace test/native/backend/static 均未运行。先前读预算与 offset finding 在代码层静态闭合，新增导出 Arrow buffer 物理容量欠账 finding 待修。CT201→06 依赖镜像预填充按完整身份通过，当前候选镜像与真实 native smoke 仍待取证。

## 1. 固定对象、职责与方法

设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496` 与 kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` §5 已 READY，A 独审 `f28c89eff5ac1e653facb21229c3b5a7d281f971` GO，B 最终独审 `17fd6739b809f048ac7b2f45cb784c144e2d98ad` GO；不重开这些已关闭结论。C 的范围是从 B retained Arrow/locator 建三族记录 Arrow、完整未裁剪 facts/table/core 流式 JCS、真实 Parquet 读取校验、输入与导出 owner/预算交接；D 才接唯一生产 comparison route，E 才清理旧热点并做最终门禁。B 临时 JSON probe 不能充当 C/D 生产桥。

本人依据仓库 AGENTS、testing conventions、比例化与 Rust 安全性能政策、S3 设计/kickoff/A/B handoff 与独审，以及 Comparison、Ordered Diff、Risk、Shared Canonical、Storage、Operation Lifecycle、Performance owning Contract 审核。在 `/home/dev/gdds-s3-c-review-573d5824`、`/home/dev/gdds-s3-c-review-0194d145`、`/home/dev/gdds-s3-c-review-93589767`、`/home/dev/gdds-s3-c-review-1018d8f5`、`/home/dev/gdds-s3-c-review-9f6c9ffb`、`/home/dev/gdds-s3-c-review-c30fd820`、`/home/dev/gdds-s3-c-review-526dc498` 固定 detached worktree 只读核对象，均核 HEAD、tracked clean、`legacy/` symlink。审核工作树与开发主机均未运行编译、lint、测试、容器或性能测量；唯一测试者为 `/root/s3_c_test`。

依赖检查点 `573d58248f0dc90e27f1be79ac9f2802211ed738` 仅在 core Cargo.toml/Cargo.lock 各加一行已锁 workspace `arrow-data=59.1.0` direct dependency，未引入新 crate/version；这是 CT201 dependency-base 备料的静态准入，**不是 C 产品 GO**。最终候选仍须逐项比 backend/worker dependency-base 五输入摘要与该来源，并在 CT201 clean 来源构建、LAN 预填到实际测试节点，核 archive SHA、config digest 与全部 RootFS DiffID。

core 检查点 `0194d145bf7c77c34225298df7b099480b61809c` 仅含 core 接口与实现，PyO3/backend 尚未固定。静态看到三族 Arrow builder、B locator→facts/artifact 两序、完整 table/core JCS 重放、递归 Arrow data buffers/nulls/children 的 `Bytes::from_owner` charge 链以及逐 batch validator 的方向；尚无当前候选编译或行为证据，不能推论 C GO。`OutputCharge` 静态结构未见 charge→batch 回环，实际 PyO3 capsule、导出 batch outlive handle、最后 owner/GIL 仍待固定候选和 06 证据。C 的增长前预算、诊断读接口、writer raw golden 等早期具体缺口已交原实施者在同一职责内修订；不把 WIP 视为固定产品 finding 轮，也不把 B 已关闭的 scratch 根因机械并入 C。

## 2. DC68 原件与执行范围

已审 Rust-only 脚本在 CT201 路径 `/home/dev/gdds-test-tmp/p6-s3-c-rust-0194d145/run-rust-focused.sh`，最终 SHA256=`041507743d095694f6de1fd797fb3e8c6154e89db6289f7061630bcc3ebb54ff`。脚本检查 06/marker、固定 clean HEAD、legacy、六锁、离线/jobs4、仓库 Rust selector 与四工具，按 fmt→workspace clippy→workspace test 首失败停，记录起止 hostname/UTC/HEAD/exit。它只拟收 core 编译反馈，不含 backend、容器或 C 验收；**实际从未启动**。

CT201 原件目录 `/home/dev/gdds-test-tmp/p6-s3-c-rust-0194d145/logs/`：

| 原件 | 本人核到的范围 | SHA256 |
| --- | --- | --- |
| `bundle-create-prep-attempt-1.log` | 缺 `archives/` 使 `.bundle.lock` 无法创建；这是事后誊录，UTC 仅分钟，数值 exit 未捕获，不冒称实时完整 argv/exit。 | `c4c6f6197819d940b8dfb528be75658a7f8da2a1032a340b4769d36143393f22` |
| `bundle-create-attempt-2.log` | 补目录后唯一纠正重做；00:31:53Z、源 HEAD=0194 clean；裸 SHA 正向加 `^2c79…` 报 empty bundle，原 exit128。 | `327f03ef48593f8d95be30be7370eea6ff39ef9ee7be1b2014abcd7165500a6c` |
| `marker-release-after-setup-stop.log` | 06 本人标记 00:29:58Z 获取、00:33:29Z 释放，SSH exit0。 | `2a02ddef45ac8ec8d4de94f489e9ee2aba8845296f4a9bf7988f67c275016e56` |

本人又只读核源 WT HEAD=0194/clean、archives 无 bundle；以 BatchMode SSH 到 06，现场无该会话 marker、被测 WT 或 Rust 日志。两次均未触被测对象，未发生源码传输、编译、测试或 dependency-base 构建。`git rev-list --count 2c79…0194` 实际为 946，且 2c79 是祖先，empty bundle 不能归因为零增量。Git bundle 需要可广告的引用名；固定 WT 的字面 `HEAD` 是本次恢复命令应使用的正向参数，裸 SHA 不是。

## 3. 对恢复稿的独立裁定

固定 `93589767…` 的恢复稿精确列出：同一 CT201 clean fixed0194 源 WT，用新文件名及字面 `HEAD` 创建全历史 bundle，不选增量 base/负向修订；在 Git repository 上 verify/list-heads 并要求广告 HEAD 指向0194；经获准 LAN 按 SHA 传 06，在本任务 node repo verify/fetch，建新 clean detached0194 WT 与 legacy symlink；确认现场空闲后原子取得本人标记，字面运行原 SHA `041507…54ff` 脚本一次并首失败停，保留原失败和后续原件，不动 B WT 或他人资源。若新完整 C 候选先固定，须由同一 C 独审先核对象与相同机制执行稿，再显式替换 HEAD/WT/日志路径。该稿没有 push/tag/amend、覆盖原件或用 CT201 代测试的步骤，恢复路径**可供 Owner 决定**。

DC68 明确“重做再次失败……均停止交 owner”。第一次准备错误仅按其已知范围记录，第二次纠正仍失败；因此本人不批准、也未执行第三次 bundle、替代传输、测试或 CT201 dependency-base 构建。Owner 若放行，唯一测试者按已审稿恢复；否则维持受影响执行停止。后续 C 固定候选仍须独审、同角色复审与原件核收，包含三族 schema/nullable/1024 rowgroup/raw golden、完整 facts 原序、JCS/content/raw 分层、真实 open/read/restore native 边界、取消/截止/M、导出 owner 直到最后 consumer，以及当前 image/container boundary 的具体判定；06 focused 不等于 04 最终门禁。

### 3.1 固定恢复命令脚本静态核

协调者随后把同一恢复稿写成两份**未执行**外置脚本；本人逐字只读核 SHA、命令顺序与 06 现场，无测试/`bash -n`/bundle 创建：

| 脚本 | SHA256 | 静态核点 |
| --- | --- | --- |
| `/home/dev/gdds-test-tmp/p6-s3-c-rust-0194d145/resume-create-source.sh` | `ad3a282502366fbfeaaa2e91d25483e51b73bca9348b38f8980bb563b7a1ff07` | 仅在源 clean HEAD=0194 时，用字面 `HEAD` 创建新的全历史 bundle；在源 Git repo 内 verify/list-heads，并要求唯一广告 `0194… HEAD`，记录 archive SHA，拒覆盖原件。无负向基线、branch/tag/push。 |
| `/home/dev/gdds-test-tmp/p6-s3-c-rust-0194d145/resume-prepare-node.sh` | `5f1823074cc6e4ac28efc6902dc4cd6dc1dac66de42889448afd8eabfc5905f3` | 核 06 与本会话 marker、传入的 64 hex archive SHA，拒现存 repo/WT/log；在本任务新 bare Git repo 内 verify/fetch bundle 的 `HEAD`，核 FETCH_HEAD=0194，建 clean detached WT 和 legacy symlink/exclude。无其他节点或 B WT 修改。 |

本人以 BatchMode 只读核 06 的 Git 2.47.3，且上述 node repo/WT/log 均不存在；源码和脚本在 CT201 仍固定，archive 尚未生成。两份脚本对 `93589767…` 的命令收敛没有新增机制，**静态执行稿 CLEAR，可供 Owner 作恢复决定**。局域网传输的起止、双端 SHA、06 新 marker 与原脚本执行仍须由唯一测试者在获放行后逐项记录并交本人独核；此 CLEAR 不替代 Owner 放行。

## 4. C 固定候选初审与复审

`1018d8f54d15e28b3b8f0edbfd55e7e47b712c66` 是首个完整 C 代码与 handoff 固定候选。本人在 detached worktree 初审，确认新接口以 B retained Arrow/locator 输入、三族 Arrow 输出，facts 依 B 原序而 artifact 全局排序，FULL 排序后再投影 detail，完整未裁剪 table/core payload 流式 JCS，Python Arrow Parquet 直写以及 open/restore 经 Python Parquet→Arrow→真实 PyO3 validator 的路径。`Bytes::from_owner` 递归包装 ArrayData 的值、validity、offset 和 children buffer，charge owner 无明显 batch 回环；此为静态判断，实际 capsule/最后借用输出释放仍须 06 取证。旧 tuple route 在 C 尚未接唯一生产 route 时暂存，D 接线、E 删除义务仍在。

首候选的同一读写预算问题有两个具体表现：真实 open/restore 用诊断 reader 的 retained-batch 上界，给不会导出 batch 的流式校验额外扣一次容量；32×row-group 未压缩字节上界会使合法 400 MiB 单 UTF8 值在 M24 GiB 下假拒。writer 以 2 GiB 内存 spool 阈值写受 512 MiB artifact 限制的文件，在产物上限核验前可能超过 writer 预留。`9f6c9ffb16c6980a51784186236b0cc9b8fb15b4` 将真实读与诊断导出分别准入、无字典固定 schema 的预解码/JCS 系数收为有解释的 16×并逐行复核；writer spool 阈值改为 `min(spool, artifact)`，增长前预留 `2*max_artifact+2*max(batch.nbytes)+1 MiB`。对应边界测试已写入。**先前具体假拒与 spool 峰值静态修复，但读预准入同根仍有下述漏项，不能称整体关闭。** 此处是 1018 首候选→9f 一轮实质修订，不把未执行的编译、机械格式修复或先前 WIP 提醒机械算成同根第三轮。

`c30fd820223740f1f436d2f52af7c199700d3da8` 补了 C 自有输入 helper，避免 E 删除 B 差分桥后 C 测试断裂；加入三族 raw/content 对旧 Python、FULL 排序/裁剪后重复、预算拒绝退账、取消/截止、真实读内容/schema/I/O 故障等向量。当前旧 Python expected 来自冻结旧实现与 Contract，不以 B 新输出充当 expected；E 删旧路径前须将动态旧输出固定为独立 fixture/golden。该提交的 GIL 向量只用第二次 cancel poll，可能在 native 真正拉取 Arrow 前通过；本人指出后，`526dc4983731107148d3188a726559d90ca97207` 改为惰性 `RecordBatchReader`，构造后断未预取，首批由 native `read_stream` 拉取才唤醒后台 Python 线程，断线程进度、取消异常与收尾。此项静态修复已核，仍须在含 526 的固定候选上由 06 运行。

目前尚不能签 C GO：上述静态复审不替代 06 对 Rust/FFI、三族 raw golden、真实 native read、GIL、取消/截止、同 M phase seal、导出 Arrow 最后 owner 的 focused 原件，也不替代当前镜像 native consumer 的小容器门禁。D 生产接线与 E 清理/最终 04 门禁各按其职责办理。依赖基础镜像最终输入摘要及 CT201 构建、06 预填身份仍待核。

### 4.1 526 续审待修 finding

读侧 `_decoded_admission` 在 526 只用 `16*row_group.total_byte_size+group.num_rows*2048+1 MiB`。固定 schema 的 nullable List 可在 1 行放大量 null/空嵌套元素；Parquet definition/repetition levels 可 RLE 为很小的未压缩页，列 `num_values` 却为 N，Arrow child offset/validity/struct slots 在 validator 的 `batch.nbytes` 检查之前已分配 O(N)。原预留可能仅约 1 MiB，不能保住 M24 的预解码准入。这是 1018→9f 读预算根因的继续修订，不把新提交名或机械fmt算独立根因。

输出侧 `records/builders.rs::append_value` 在 526 对 Utf8/Binary/List 无每批累计 i32 offset 前置检查。锁定 Arrow 59.1.0 的 `GenericByteBuilder::append_value` 文档/源码明确超 2 GiB 在值 buffer 扩展后 panic；`GenericListBuilder::append` 超 child length 也 panic。`max_output_bytes` 与 artifact policy 可显式提高，N1/M24 GiB 下仍可到达，S3 设计 §4 要求过大 offset/单行不能容纳时报预算拒绝。此项与读预准入分别交原实施者在 C 职责内修，未请求新的核心方案。

`68a97378e1ff1fee164410baaecb7ee22dd83b92` 为两项集中固定修订。本人在 clean detached WT 静态复审：读侧遍历每 row group 的全部 Parquet leaf，拒 dictionary/负 `num_values`，以 `16*total_byte_size+512*Σleaf.num_values+2048*num_rows+1 MiB` 取最大组，在 Python decode 前预约/拒绝；固定三族 schema 最深四级 List/Struct/Scalar，512 B/leaf slot 覆盖 Arrow child/offset/validity 与 Value/JCS 结构暂额，16×字节覆盖 plain 可变值及 escape。新增真实 PyArrow 100k nullable `Scalar.items` 元素压缩向量：32 MiB 限先拒、M24 准入时解码 `nbytes` 低于预约；400 MiB plain 宽值仍保可准入。输出侧 Utf8/Binary 检查每批 `values_slice()` 累积字节，List 检查 child 数，递归子 builder；注入小 offset limit 测试覆盖刚好到界、下一 append 增长前拒绝和嵌套。1024 行新 batch 仍独立重置，无全表 2 GiB cap。**这两 finding 在固定代码层静态关闭，实际06运行/高水位仍未取得。** 对读预准入按 1018 初候选→9f 第一修订→68a 第二修订跟踪，尚无“同根两轮修而不解”的事实；后续以实际结果判断。

`bca590261568e8adeec605ecc00afbb2715782ad` 仅将 06 原 `cargo fmt --all` 机械 patch 应用到 8 个 Rust 路径；本人在 clean detached WT 核 HEAD 与 Rust tree=`c5cb5288a62497940bbf5905828f1942b70668ca`，对 `68a..bca` 的 Rust diff 用原 Git 九位 index 缩写生成 SHA256=`234259e6b829553968068880fcbc0e8865f8b65f0a9b776df3aa018f7515d22b`，与 06 原 patch 逐字相同。它不另算一轮预算修订，待新固定候选的06运行。

`bd384246bd50320feba1d1cb805a96034ab294c7` 是 bca clippy 首败后的单文件最小修复。本人在 `/home/dev/gdds-s3-c-review-bd384246` 固定 detached WT 核 HEAD、clean、legacy exclude；单提交只将 ordered 非 FULL 的 `small_row_upper` 调用中不存在的 `OrderedRecordRef.diagnostics` 换成 `&[]`，该行实际构造的 `diagnostics` 已是空数组，不改变语义。五个 backend/worker dependency-base 输入相对 bca 无 diff。此编译反馈不是读预算或 offset 同根的新轮；能否编译及行为仍以该提交的 06 原件为准。

## 5. Owner 恢复后的 9f 源端原件

Owner 明确回复“允许按已审恢复稿放行”，协调者记录于 `5036f77f04`；本人原先对 `93589767…` 的“可供 Owner 决定”判断不再是执行阻塞。唯一 tester 将已审脚本只改固定 HEAD、证据目录、会话和 bundle 名，三份 SHA 分别为源端 `b833aeae3953a00a58646972f9f28061e54fc779849b387788ddd593786e9018`、06 准备 `b17e8802e0f7ede620c20413e1de713d54c958e5453c2e2a7dd999db80cb66cb`、06 Rust focused `67bc649956b02142de83398440b07a0618c7987bfefa6f42cc18c2c6bd1d8291`。本人逐字对原模板比对，变化仅上述字段，Rust 顺序仍为 fmt→workspace clippy→workspace test，首败即停。

CT201 第一次源 WT 准备只因既有日志名拒覆盖，原件 `source-wt-create.log` SHA256=`6c75480fe9027bb81f191ddaec501d9c55d9df0f5898c282e44622030ee28dcd`、exit 2，未触源 WT；tester 保留该失败并从步骤开头重做，`source-wt-create-attempt-2.log` SHA256=`0dc7ada66340208cc29bc272245604ad6b00ffe3ae4958130bf9c796f36df555`，01:10:36–37Z、HEAD 精确 9f、clean detached、legacy exclude 命中、exit 0。源端 bundle 脚本原件 `resume-create-source.log` SHA256=`d92c3bd3193b3d5a5219696a88da06bd5f92971bdb5e151a2af84dc0ec98aca4`，01:11:26–27Z、起止 HEAD=9f、exit 0；repo 内 verify 明示完整历史，list-heads 唯一 `9f… HEAD`，归档 SHA256=`6529d9a26434191719d877f7a1542475c23ce737821eb09812ab57c2a5d4a127`。本人另读源 WT 的 HEAD/status/legacy exclude，仍精确且 clean。随后的 06 接收与 Rust focused 原件见 §5.1。

### 5.1 06 首轮 Rust focused 原件

首次 06 只读 preflight 的远端 Bash 嵌套引号在命令体前解析失败，`06-preflight-attempt-1.log` SHA256=`766fc5c744d6d5d65fc2a31bf709c94276ed60dd23ea8dd1b3fddd787702e38f` 是事后摘要，原 numeric exit 未捕获。本人逐字审 literal heredoc 修正版 SHA256=`d1bada0b5c2422ff6eaf9b61ed6835dd7fc246b3d065f545befdf53b7be0f1b6`，唯一 tester 执行后原始 `06-preflight-attempt-2.log` SHA256=`574fd350f96ce8b5cbeafffa1124661f48f92d253964e614156a656cca50f280`：01:16:28Z、gw-dms-06/root、无 marker/容器/相关进程，仅 22 监听，SSH exit 0。

本人逐字核外层 `transfer-prepare-run.sh` SHA256=`42ce4a49dddb5f966151e7cd9252ba6997d4608afa3a2ca303bbde7f9697c3f8` 后放行唯一执行。其原始日志 SHA256=`ea8f2270fc9d4241a8b84be6549784e90443328025882f5660f9bd12ea820456`，01:18:11–14Z：本地与 06 的 bundle/node/Rust 三 SHA 均一致，本人 marker 原子取得、LAN 拷贝完成；node prep 日志 SHA256=`3e42b5649c51a44ae8d930ac43b33d3d3714cc3381411f62e2744b7e4d713fec`，完整历史 bundle 在新 bare repo verify/fetch，06 HEAD=9f、clean detached+legacy、exit 0。Rust 日志 SHA256=`c0f7ee16768bc9292666696d2864fd642d729f6e72b795c5cfc7f95628e4ebb6`，01:18:13–14Z，选中 Rust 1.97.0、离线/jobs4、起止 HEAD=9f、工作树 clean、六锁未漂；**`cargo fmt --all --check` 首步 exit 1**，故 clippy/test 均未运行，外层 FINAL_EXIT=1。tester 的只读 postflight 原件 SHA256=`b72b9fc4bcb784c18e301f91a82c550fe15f7e77ff1e9d389d45cbba8f04802a` 核同一 marker、无相关进程、WT clean。其本人 marker 释放原件 `marker-release.log` SHA256=`b8a59b8ee7849659e21c0b9547f991a2284e2984633c8cd256deda121c1b7400` 是事后记录的 SSH stdout/exit：01:21:17Z，owner/进程/port/异己文件 guard PASS，仅删除本人 marker，tool exit 0；不冒称原始自动日志。format 是机械反馈，不计 C 预算同根产品修订轮；须在新固定候选由唯一 tester 重跑。

## 6. CT201 dependency-base 原件

本人逐字核 `/home/dev/gdds-test-tmp/p6-s3-c-dependency-base-573d5824/build-and-save.sh` SHA256=`fb05c816aeaebc9907037887ba6510354c46a2372ac6284dca6adaa003445cf1`，只按 clean `573d58248f0dc90e27f1be79ac9f2802211ed738` 用 authority builder `--print-input`→`--save`→`--print-input` 并比同一输入、检查归档 config/全 DiffID/label；不运行产品测试或把 CT201 结果当测试。唯一 tester 的原始 `build-and-save.log` SHA256=`7e1b02db9b823bd4be8c55a4888c2e40b99e83a9320a2919e17c7f18762094d3`，heavy-dev-01 01:22:02–01:24:09Z、起止 HEAD=573、clean、六锁无漂、exit 0。本人在固定 68a detached WT 逐项核五个 backend/worker dependency-base 输入 SHA 与 573 `input-before.json` 相同，573..68a 五路径 diff 为空；以后产品候选须再核这五输入。

输入前后 JSON SHA256 均 `835bb4758561a1c1be509d4778c7310619142d1b5006efd26d948f57aaf30520`，full input SHA256=`ca0ba0a24a5e96a435e14a6da80b26cc390d315722f0432be3affe9de3339085`，tag=`gateway-backend-deps:lock-ca0ba0a24a5e`。归档 `/home/dev/gdds-test-tmp/p6-s3-c-dependency-base-573d5824/archives/backend-dependency-base.tar` SHA256=`fb30d4666cf5466c66ca464c9db7103457cec92f4eb9003980f6c1a2e3dfc136`；`image-identity.json` SHA256=`3fc8843af9cc6212a25b69e0032813a7362c44ced5c80798676d8ad6f8df2b05`，其中 config digest=`sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c`、全部 19 个 RootFS DiffID，源 Rust base config=`sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1` 与 5 个 DiffID 均在原件。该归档在 CT201 build/save 通过；06 的 LAN 传输、`docker load` 后 config/全 DiffID 比对、当前候选离线 Compose 构建和容器 smoke 均待实证。

## 7. 68a 机械格式与 bca 固定候选

本人逐字核格式主体 `/home/dev/gdds-test-tmp/p6-s3-c-format-68a97378/prepare-and-format.sh` SHA256=`844ec577c48daeed3df06c77ad28e25a9a02cf06b8854f750e91e8f8bde996b1`，以及本人 dirty scratch 保护性收尾 `cleanup-format.sh` SHA256=`639eb9ca968e09417149b7451e3534ed01bab53c1ea6048307c83157a9942070`，放行唯一 tester：源 clean detached 68a 与字面 HEAD 完整 bundle，06 原子本人 marker/LAN SHA，独立 68a WT 仅 `cargo fmt --all`，patch/SHA 双端核后才在同 session 删除本人格式 WT、核旧 9f WT clean、释放本人 marker。格式主体原始日志 SHA256=`6dbc44520ad6499000ef82615da5395ee5890eeb325fa189cadc3bf8203deba0`，01:27:25–29Z exit0；06 `format.log` SHA256=`923ac6af1f0923c1db8bac6d2e2ad8e4715238e0d9381c980bd4c9d13457bc9a`，01:27:29–30Z，HEAD=68a、Rust1.97、六锁无漂、8 Rust 路径格式 patch SHA=`234259e6b829553968068880fcbc0e8865f8b65f0a9b776df3aa018f7515d22b`、exit0。收尾原始日志 SHA256=`16327dc30aba5ac7d06f2b7e06588c86ee4e2deeffb2c36ff756bbaf0f5e4adf`，01:28:00–01Z exit0；06 patch 与 live-before-cleanup patch SHA 同，实际仅本人格式 WT 移除、marker 不在、旧9f WT仍精确 HEAD9f且 clean。格式 patch 与 bca 源码一致见 §4.1；本步没有 clippy/test，也不是 bca 验收。

## 8. bca 06 focused 首败与只读取证

本人静态逐字核 bca 的源、节点、运行与外层四稿，SHA256 分别为 `a48182538d3cd850c77b4cfa7d587589ee985d3fe2529bb560e80de1dbc79567`、`59c67fb19b69fd43aacbdb48793020a165520d17cb3b064cd640ecd5f2ae248a`、`7221f17d916eeef800ab81733a43651eea34ea31cc84a9048cbd82a22b5cf4df`、`bac2d71d344168914f75c1495eb58567ee471e60af29d8feada7fe331c497aa7`。执行范围是 clean detached bca 源、字面 HEAD 全历史 bundle、06 本人原子 marker 与局域网双端 SHA、clean detached 测试 WT+legacy，Rust fmt→clippy→workspace test，再强制重装 native 并核 build-input、C focused unit、五 Python 包 ruff/mypy；任一步首败即停，不含 Compose。backend `pyproject.toml` 的 mypy `files=["src","tests"]` 已覆盖新的 C 测试与 support 文件。

唯一 tester 的源 bundle 日志 SHA256=`043eb7d52c51053b3340d6e08b8c182c0e1a9213761231806e5d2d58b0a82fec`，archive SHA256=`b02217139d58a439c09a0d4d4ec79675acd61c8ef4dc6bec6bc6f64ed64211d6`；外层原始日志 SHA256=`8558b4f5ddd29fff75c13217e1715851e46da5b37ed791ff4a7e6463f621068c`，01:32:48–56Z，`FINAL_EXIT=101`。06 节点准备原始日志 SHA256=`bc98f5eab88eca34580d6035b982ab16bb02e7dc2d2c7c9304f2e3807fb74749`：完整历史 bundle verify/fetch，HEAD=bca，clean detached，exit0。06 Rust 原始日志 SHA256=`4a647ef7e03dd9c579df0ce23eb3086e31fb3c3e9d3826d6642af651bd287338`：Rust selector/toolchain 1.97.0、HEAD=bca、Rust tree=`c5cb5288a62497940bbf5905828f1942b70668ca`、clean、六锁无漂；`cargo fmt --all --check` exit0，`cargo clippy --workspace --locked --offline --all-targets -- -D warnings` 在 `records/source.rs:158` 报 E0609：`OrderedRecordRef` 无 `diagnostics` 字段，exit101。workspace test、native 重装、backend focused 与五包静态均**未运行**；不能报通过或推断 C 行为。

只读 postflight 原件 SHA256=`936a175aeb8a458fb2a7d0206cd2128368eae99e59548394570eef7ab59691e7`：同一 `rg -n … "$f" | tail -n 100` 在节点上对 node 与 Rust 两个不同日志各报一次 `rg: command not found`，两条管道各自的 numeric exit 未捕获，不能写成查询成功。两条之间没有修正或重做；其后每个文件各用 `tail -n 100` 一次，完整取得原始日志末尾、SHA、clippy 诊断、HEAD、六锁与失败退出。故这是同批两个未成功只读查询，**不是** DC68 意义上的“纠正后再次失败”；postflight 最终 SSH exit0 不替代那两条失败。本人 marker 释放日志 SHA256=`f016d383bc692c56509485e3fc4851310442ec41e2242bcbbb291844988293ae`，明确标为事后誊录的 SSH stdout/exit：01:34:27Z，核精确 owner、无相关进程/容器/8000 listener，才移除本人 marker，工具 exit0。没有继续测试或把失败当 PASS。

## 9. 06 依赖预填充与 bd 重跑稿静态核

本人逐字核 CT201→06 预填充脚本 `/home/dev/gdds-test-tmp/p6-s3-c-dependency-base-573d5824/prefill-06.sh` SHA256=`48017e4e374725c8c7826359f0d46b2d98d6611f05edf1d3ccae7282e334f437`，及随附身份核验脚本 `verify-saved-image.py` SHA256=`bbf4a6ac956ec57cc88bdb496f334306bdfe9e92024a538526cc6b2136ca7d50`。它只在 06 空闲时取得本人原子 marker，经 LAN 校四件源/节点 SHA；以 `docker save` 的 config blob digest 与完整 RootFS DiffID 核 Rust base 5 层、dependency image 19 层并核锁输入 label。已有相同 derived tag 只核不覆盖，缺失才 `docker load`；精准释放本人 marker。Python runtime base 要求本机存在，当前 Compose 后续仍需当前候选镜像实证。此稿**静态 CLEAR，仅备料，不把 CT201 构建或预填充当 C 产品测试**；06 原始执行结果另核。

bd 的源、节点、运行与外层四稿 SHA256 分别为 `6cbc4a132fbdfb65405d9fcb93c12234dc515f20ed6b078120a53036da775b75`、`57a8d2ff0bef7689a6ae3f15d8df86f70b55ea9ce0392b8575cddc29f58c5127`、`c0ddde6d26ce48aad9b9d996919ac164c7640363f62275fca395512758457020`、`748f67ff2f553f021dc6e9872d01ebc5be3dfb45f4961e1fd6685df037141333`。本人逐字核：除了固定 HEAD、证据路径、会话、嵌入脚本 SHA 和 purpose 文字，命令与已审 bca 稿一致；两类 06 操作严格串行，bd 仍从 fmt 重新开始、首败停止。此为**执行稿静态 CLEAR**，不是 bd 编译、测试或 C GO。

### 9.1 06 依赖预填充原件

唯一 tester 在 bca 本人 marker 释放后执行预填充，原始 CT201 日志 `/home/dev/gdds-test-tmp/p6-s3-c-dependency-base-573d5824/logs/06-prefill.log` SHA256=`c84aaade82bb2d52618d579e9afa634586c7dae2e1924b4b3c0160ffff083d11`、`FINAL_EXIT=0`。日志记 heavy-dev-01 01:36:33Z 起、06 01:36:36Z 获取本人 marker、LAN 01:36:35–55Z、06 01:37:14–29Z `docker load`、01:37:49Z 释放本人 marker；两个节点四文件 SHA 均正确。06 本机 `docker save` 的 Rust base config=`sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1`、全 5 DiffID，与 CT201 源一致；导入 dependency tag 后 config=`sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c`、全 19 DiffID 与锁输入 label 均一致。06 本机 inspect ID 仅参考；本步没有编译、产品测试或 Compose，不能把 bca/bd 失败改记 PASS。

## 10. bd 06 focused 新首败

bd 的源 bundle 日志 SHA256=`7f74bd62e2deda04339b2f8d2af7373efd5663c4d5fe6ff5b2ce778797304456`；节点准备原始日志 SHA256=`7f1345ba8f860e56e90ff48d3f96d660e21a11ed52145fb49c70ec6ec0fe4bdf`，完整历史 bundle verify/fetch、HEAD=bd、clean detached、exit0。外层原始日志 SHA256=`4a948468e0aa82d29b04bf596470b75041985f27a754e29c251c897a1284029f`，01:38:18–26Z、`FINAL_EXIT=101`。06 Rust 原始日志 SHA256=`aa0d1677398b8bbd236411426083a95ac92c121f811f20b4c30118ff97716e5d`，01:38:22–26Z，HEAD=bd、Rust tree=`d2114c5bce35d03b0fedd7ae485890c637ab2e3f`、clean、六锁无漂；fmt exit0，clippy exit101。clippy 报 C 新 `comparison/policy.rs` enum large variant、`records/source.rs` 五个 builder 函数参数数目，以及 C 新 builders/source 单测 25 条 `expect`/`unwrap` lint。既有 E0609 已不再出现，但 workspace test、native 重装、backend focused 与五包静态仍**未运行**。这属于新编译/lint 反馈，未触及读预算或 offset 同根修订轮；交原实施者集中按 Rust policy 最小修，下一固定提交从 fmt 重新跑。

tester 的只读 postflight 原件 SHA256=`009696965544fae611d9efdd50e627a1856b855f8f0d548e8d4268ee86d33df2`，以 `awk`/`tail` 收齐原始日志与诊断、WT=bd clean、本人 marker、无相关进程/容器/8000 listener，SSH exit0。本人 marker 释放原件 SHA256=`5bf70247781662f3fb433a38fa853cd977e8e23f984db6c4972050e114885da3` 是事后誊录的 SSH stdout/exit：01:40:03Z 检查精确 owner/idle 后移除本人 marker，工具 exit0。没有重跑 clippy 或后续步骤。

## 11. 20f、policy/guard 与导出物理容量 finding

`20fbaa2decc1a934f7e1316be5e0810984cf6f2f` 仅改 C 的 `comparison/policy.rs`、`records/builders.rs`、`records/source.rs`。本人在 clean detached WT 复审：`large_enum_variant` 只对每 operation 一个 336B policy enum 局部放行，注释说明不新建 parse lease 退出后的未计费 Box；五个函数的 `too_many_arguments` 只在显式 budget/context/owner 接口局部放行；三个新测试改 `Result`、`?` 与 `.err().ok_or(...)`，仍断言正/负边界。没有 module/crate 级 lint 放宽，五个 dependency-base 输入无 diff。这是对 bd 的普通编译/lint 反馈修正，**静态 CLEAR 不等于编译通过**。

本人逐字核 20f 的源/节点/运行/外层四稿 SHA256=`b023aed84603534c669e3da84d4d457b29893e66ddd3d32ec1705823c07005ad`、`5f2caf2e81cf3d14ba44f886aba207b77612c8c3d9ec1c808de6f2cd97b2a232`、`3661e78b852e7751fdfaf9b92c66402514a64c3eb45e0610b94ff324c35cfbd3`、`b58d2fdaea364ac4e69bc67e17853799c0b3bf99bed0386d266d3469d3e5a886`；规范化 HEAD、证据路径、会话及嵌入 SHA 后与已审 bd 四稿逐字一致，故静态执行稿 CLEAR。唯一 tester 原始源 bundle 日志 SHA256=`4ff456d258bb5a4c3cd8ad614b73b7cfe3025624f0eb63a655aef0720b9bbb10`；节点准备日志 SHA256=`4530172c91b33fe22ea312e002bb3060ffc939f219e5882d991b93d22bee9c46`，exit0、clean detached20f；外层日志 SHA256=`bb68e7bf0b4efb8d401d3c8b0993413e2b687c37d70c23b274edd699343c78d5`，`FINAL_EXIT=101`。06 Rust 原始日志 SHA256=`eeadd8ef6adf56e21ec6db3d18e19f85f2bb344ba989aa9a12d415cba2e79639`：01:43:31–35Z、HEAD=20f、Rust tree=`b95be77383b1905985b15e9684a698c8566d9d42`、clean/六锁无漂，fmt exit0，clippy exit101。core 先前 lint 已不再报；新诊断在 PyO3 `comparison_records.rs`：`json_size` 要求 `&Value` 却收到 `&OrderedCompareResult`、`Bound` 无 `.downcast()`、`Python::try_attach` 闭包返回的 Bound 生命周期外逃。workspace test、native 重装、backend focused 与五包静态仍**未运行**。postflight SHA256=`5333e94cbbc11935d12d6989f6d4562e171a6863a1eaf32c3549d5b841c6cadf` 核 clean/idle/本人 marker；释放原件 SHA256=`66f3fb5eef62adc11199c3fbe96cdbe67a954eb3230423bf6da13d3330d5b302` 标为事后誊录，01:44:33Z 精确 owner/idle 后仅释放本人 marker，工具 exit0。此为新编译反馈，不计先前读预算两轮。

Rust Safety Policy 单独文档提交 `234ccc93d804aab0da7ba61d3b6d0bd56ec4de29` 在 clean detached WT 独核：v7 §4 只登记已审 S3 `comparison.native` 五个精确粗入口、Arrow bulk/小 metadata、同 M/seal/最后 buffer owner 与 `artifacts` 经 facade 调用的边界；无 wildcard、其他 owner 或代码放宽。`ce47551284d70a48d94cb39e2baf167a413411ef` 仅改 import guard 测试注释及形状表，五入口正例与三条同 owner 越权/wildcard、其他 owner 越权拒绝；guard 映射和 Rust tree 均不变。两提交静态 CLEAR，测试仍待当前候选运行。

**新增 C 导出 owner/M finding：** `records/builders.rs::retained_charge` 在每 1024 行及最终完成时以 `ArrayData::get_slice_memory_size()` 合计输出，再 `lease.shrink_to(retained)`。锁定 Arrow 59.1.0 的该方法只计切片**逻辑长度**；`MutableBuffer::into_buffer` 保留原 allocation capacity，`get_array_memory_size()` 才计递归 Buffer capacity/null/children。`ChargedBuffer.original` 使这些原 buffer 在 PyO3 导出后继续存活，故容量大于长度时当前 lease 已退到逻辑值，直到最后 Arrow consumer 释放前都可能少计 M。包装成 `Bytes::from_owner` 后外部 Buffer 的 `capacity()` 为零，因此应在包装前对原输出按物理容量计 retained、必要时增长前拒绝，并用 spare-capacity 输出与 reader/handle 先关闭、最后 batch 释放的向量核退账；无需新 allocator registry。此与读侧 Parquet 预准入的两轮是不同根因，已交 C 实施者同职责内修，未请求新核心方案。

## 12. 2e 物理容量与 schema 修订、1338 格式候选

本人发现 `records.rs::expected_fields` 五处 List child 使用 `element`，冻结 Python `artifacts._schema_for` 的 `pa.list_` 公共 Arrow schema 默认 child 为 `item`；`_schema_matches` 严格比较嵌套 Field，故新 Rust Arrow 输出、Python Parquet writer/真实 Python→native reader之间有 schema 风险。这是独立的 C 物理 schema finding，不通过改 Python 或更新 golden 掩差。已冻结的三份 Python Parquet `.b64` 原始物理 schema 明文有 `list/element`，而旧 Rust `read_records_parquet_v1` 三个测试曾通过这些向量；Parquet 物理命名不能推定 PyArrow `schema_arrow` 命名。旧 Rust 直接 reader 是原型/测试消费者，新生产消费者须按 Python 公共 schema；两种 reader 应在固定06候选上分别取证，如实迁移旧原型断言，不为它放宽真实 C schema。

`2e0c64226c0ad61aad6b66b36213086bdda4b876` 在 clean detached WT 独审：三处 20f PyO3 编译问题以泛型 `Serialize` counting writer（先计数后分配 metadata）、`Bound.cast`、`try_attach` 闭包内消费结果修正；五处 List child 仅改为 `item`，nullability 与 Python/golden 不变。输出在 `charged_batch` 包装前以递归 `ArrayData.get_array_memory_size()` 计物理 buffer capacity、null/children/header；最宽 STANDARD 固定 schema 48 builder 节点的初始容量设 512 KiB workspace 并在创建前 reserve；每组同时保留已完成 physical retained 与下一组 workspace，组边界及最终核 physical≤output policy 和已预充 lease，最后 drop builder 再缩到 retained。新 Rust 向量分别构造 capacity>logical、核固定三族初始预额，Python 导出向量在 seal 后断 native token > batch logical nbytes，handle/reader先关、最后 batch/table 释放才退。五个 dependency-base 输入无 diff。**物理 retained 和 List 命名在代码层静态收敛，双 reader、实际高水位/最后释放与完整行为仍待06。**

2e 机械格式主体/收尾两稿 SHA256=`993315b0a44365532ddb1098649eae6abce4faac2f3d69c623dca3ce44a9ac2f`/`33f8cb96646c88ff7e033d0fb272ddd1dd8f31637850312c8fafb6c753790f5c`，规范化后与已审 68a 两稿逐字一致；唯一 tester 的主体原件 SHA256=`5a67548179ab4d3d9162cd141a98a76ef9d9b6dcea31c2fe33d4f3bf37cbc21c`，01:54:19–23Z exit0；06 `format.log` SHA256=`0d3e42bc899a756c8a66730b8e1c0471bd78913dd4ea7c4f05c671904489b9db`、patch SHA256=`c080c213d855c306ee9ba89076082b181ecc0c4210e948ba39bcb4e192951a49`，只改 `builders.rs` 格式。收尾原件 SHA256=`effbe79bfb54acafdbfe1b9f777c6f7d19dd32f519e5bbdecef2b1da85bef330`，01:54:46–47Z exit0，只删本人格式 WT、释放本人 marker，旧 9f WT 保留。`1338aa36d6faf59ca2bb1d13853a837b2f94e7a3` 在 clean detached WT 的 `2e..1338` 源 diff 按九位 index 缩写 SHA256 正是 `c080c213…`，仅机械格式，不另算物理容量/读预算修订轮。正式 06 focused 执行稿四 SHA=`a9c8eb7f8ac428f67165abcf866acdced5db27b049ea74c16abd0658f4f92ccf`、`337195b18cb89be66c700f472ec888a6fc3abdbce7d592fd776e5bd5afd4e9b8`、`005703a3f5320cc4909643d86720da221ffbcc203a7272565745b185867fb0b4`、`6145d2f15af8200235e7ef450a7083f5c8c98228af44c0c21454e16851c73a0a`；对 20f 已审稿只增现有 architecture import-shape 测试节点，其余 retarget、首败停机制不变，静态 CLEAR。真实运行结果另核，不能由格式原件代替。
