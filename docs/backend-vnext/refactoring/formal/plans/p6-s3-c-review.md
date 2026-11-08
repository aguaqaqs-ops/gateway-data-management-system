# Phase 6 S3 C 独立审核

**当前结论：C 固定候选 `bca590261568e8adeec605ecc00afbb2715782ad` 的预算/offset finding 已在代码层静态闭合，仍无 C GO。** Owner 已允许按已审 [C 执行停止与恢复稿](p6-s3-c-execution-stop.md) `93589767aebfa889a5d1244afd34bb54642bc575` 恢复执行；这只恢复测试通道，不是产品通过。旧 `9f6c9ffb16c6980a51784186236b0cc9b8fb15b4` 的 06 Rust focused 首步 fmt 失败并停止，clippy/test 未运行；bca 的 Rust/backend/FFI/容器证据和依赖镜像 06 预填充仍待取得。

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
