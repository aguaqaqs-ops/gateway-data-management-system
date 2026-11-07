# Phase 6 S3 B 独立审核

**状态：完整 B 验证候选 `4f1bd419dc7d66da0cb1b8bd0c5de59c6df8587c` 审核中，尚无运行 GO。** 固定 Rust 检查点 `3577df182d6481a9c6e49554e445c81071924c09` 为原始问题来源，`a4ff75362737ec4a6e15a2cb6f1ace836ea26657` 为第一轮、`ac21ad4069abb08f162d9418a6426a63d7508974` 为第二轮实质预算修订；`9b34be7356a92228ef07ee0c4f01bf215e2bf653` 与 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 为机械格式检查点，不单独计预算修订轮。本轮仍待 06 的当前候选编译、fixed/property/差分与 t1–t4 按表原件，不把旧镜像结果写成当前通过。

## 1. 固定对象与方法

设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`、kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` §5 已 READY；A 独审 `f28c89eff5ac1e653facb21229c3b5a7d281f971` 最终 GO，A 无剩余 finding。依据 AGENTS、testing conventions、比例化/Rust 政策、S3 设计/kickoff、A handoff 与 Comparison/Ordered Diff/Risk、Shared Canonical Encoding、Canonical Storage、Snapshot Table Access owning Contract，并对照固定 A/旧 Python 生产实现。未重开已关闭的 kickoff 设计。

本人在 `/home/dev/gdds-s3-b-review-3577df18`、`/home/dev/gdds-s3-b-review-a4ff7536`、`/home/dev/gdds-s3-b-review-ac21ad40`、`/home/dev/gdds-s3-b-review-2e975888`、`/home/dev/gdds-s3-b-review-a665a3c0` 五个 detached worktree 只读审核，均固定 HEAD、tracked clean、链接 `legacy/`。a4ff 的 `vnext` tree 为 `de98b3fcedc713e88a0798a1357503e081560a5e`，ac21 为 `e6c464bd343eca865c1274247bfac7438e9942d9`，2e975 为 `97e1bb3e9da32eff5d0120e0cffb99c6817d2875`，a665 为 `5488e79d098c42d928a0e4f7ccfb4ae2aa38497f`。开发主机和审核 worktree 未运行编译、lint、测试、容器或性能测量。

## 2. 当前静态核点

3577 的 ordered 入口沿用全值 Vec、零 batch 缺 schema、索引/LIS/摘要缺控制检查、scratch charge 留至结果 Drop 且部分 record 在分配后才预约。a4ff 已实际改为三族 locator + Arrow Arc owner、显式 schema 的零/N batch、索引/LIS/gap/digest 控制检查、scratch `shrink_to` 与增长前 record 预约；单侧 compare 任务明确拒绝交 Python 表级 metadata owner。固定 Python 的整表新增/删除不产生逐行 records，不能拿旧 Rust 原型的单侧行为作预期。

a4ff 时仍待核以下具体边界；其后静态关闭状态见 §2.1，不把 a4ff 本身记为最终失败或通过：

- **预算同一根因：** a4ff 仍逐 batch 累加 `get_buffer_memory_size()` 再按倍数预约；Arrow 59.1.0 `arrow-data/src/data.rs` 明确共享底层 Buffer 的各 slice 均报告完整容量，随机切分同一 backing 可使同数据/同 M 虚假拒绝。`ordered_retained_bytes` 在结果构建后再 `serde_json::to_vec` 和 `shrink_to(retained)`，当 retained 超初始 lease 时事后 `grow`；零行宽 schema 是具体边界。下一预算实质修订为第二轮；若同一 M 不变量仍未解决，停止受影响 B 预算 GO 并报具体阻塞，不用格式检查点重置轮次。
- **流式 JCS 数字：** a4ff `ordered_digest` 直接写 `row.position.to_string()`；固定 Python 与旧 Rust JCS 均拒绝大于 `2^53-1` 的整数，`no=2^53` 在 Int64 中可表示。新流式路径必须保持原失败边界，并对数字写入作最小校验。
- **facts 消费：**正常 ordered 的三族记录在 locators、`facts.records` 为空；退化则 `facts.records` 有 `TABLE_DEGRADED`、locators 为空。C 的完整 table/core payload 必须合并这两支并从未裁剪值重放，不可直接序列化小型 `facts` 或拼 table hash。Blank 私有 `entity_key_kind` 仍属 facts，不进 Parquet。B/C handoff 需把双支消费规则说清并用旧生产退化结果差分。
- **编码依赖的 metadata：**a4ff 会核物理类型，但 Utf8 的 `sql_type=DECIMAL(10,0)` 与 `declared_type.kind=string` 冲突仍可通过并按 decimal 编码。真实 S2b owner 生成一致 metadata；B 只需对自身编码实际依赖的冲突作最小失败检查，不复制整套 IPC 校验矩阵。

已静态对照的正向语义包括 keyless occurrence 0/后续域与 minimal ULEB、SET Utf8 的声明序 sequence frame、ordered 绝对 `no`/LIS 并列/blank gap 锚与排序。它们仍待完整固定向量和差分原件核收。B 新入口不得成为生产 flag/fallback；旧 Vec 原型及临时 Python 差分仅替换期测试使用，E 按清单删除。C 的三族 Arrow builder/JCS writer-reader、D 的风险/去重/生产路由不提前要求 B 实现。

### 2.1 第二轮 ac21 的静态复核

预算同根因已在代码层针对性收口：standard、ordered 及 unchanged ordered 改用 Arrow `get_slice_memory_size()` 按实际 slice 范围估算本地编码，避免同 backing 被 N 个 batch 重报完整容量；ordered 在解析 schema/选项 metadata 前预约临时 lease，释放后主 lease 预留结果 metadata 上界；`KernelLease::shrink_to` 现只允许退账，禁止结果构建后再增长。record locator 在分配前预约。零批次宽 metadata 与共享 backing 切片已有新增边界测试代码。**这关闭了两轮阈值下的重大预算静态缺口，不等于运行 PASS**：ac21 的 12 项 standard tests 及新边界尚未编译或执行，06 仍按 §3 的 DC68 停止。C/D 要在实际 adapter/最后 consumer 路径证明已计费输入 owner 与 B 结果共同存活，并另计 Arrow builder/JCS/writer；B 接口本身不能宣称端到端完成。

其它独立根因也见到最小修订：normal/degraded 均走 `StandardRecordRef`，`OrderedKernelResult.facts_metadata` 明示只有小 metadata，完整 facts 仍需 C 从未裁剪 locator/Arrow 值重放；流式 ordered JCS 数字加入 I-JSON safe integer guard；`columns_added` 的 ordered `content_changed` 改用共有全行投影 multiset；编码依赖的 `sql_type`/`declared_type` 参数、kind 与物理类型冲突改为失败。上述均属**静态可见，未有 06 运行证据**。未变化 ordered 的少量摘要字符串输出计费由 C/D 小 facts owner 继续核，现无理由为此另建 allocator registry 或扩大 B 验证范围。

ac21 静态复核另发现两个与预算轮无关的 ordered 诊断差异，交实施者按固定 Python 行为作最小修订并纳入差分：

- `CanonicalPseudoGid` 下非法非空 gid（如 `-1`）在 Rust `read_side` 落入 `SOURCE_GID_INVALID`，固定 Python `_parse_stable` 对该 provenance 给 `CANONICAL_GID_INVALID`；退化诊断参与 facts 摘要。
- 合法 S2b string/Utf8 字段若被 ordered policy 用作 `gid`/`no`，固定 Python `_integer` 对非空 `StringScalar("1")` 给 `ORDERED_INTEGER_INVALID`，Rust `read_integer` 却解析为整数继续比较。空串在两边均按 missing。若保留旧原型测试宽容行为，新生产入口仍须保持冻结诊断。

### 2.2 完整静态候选 a665 的增量

在固定 `2e9758885a8179d0e8e90c9c90a7c244577b9ea2` 与 `a665a3c06304d2f9ac8d4befb27f7be6d2a4a3df` 上只读核到：`782d07` 将 standard/ordered 列数上限提至 2048、ordered 行数上限提至 10,000,000，和 S2b canonical IPC owner 当前上限一致；canonical 伪 GID 的非法非空值与非空 Utf8 `gid`/`no` 已在 Rust 新入口分配正确诊断，旧原型专属 numeric text 宽容仍待 E 删除。a665 把 b917 06 clippy 报的 `.any()` 枚举索引误解引用修为 `frames[index]`；这仅是静态修正，待当前候选重新编译。

临时 `comparison/probe.rs` + PyO3 Arrow C Stream 桥只供 B 差分，未被 Python 生产 `compare_plan` 路由调用，E 删除点已列交接；其 test-side 24 GiB 估算不能充当 D 的输入 charge 或 C builder 预算证据。测试先将旧 reader 转真实 S2b canonical IPC，再以固定旧 Python `standard.py`、`ordered.py`、`row_encoding.py` 源 SHA（依次 `3ff92146caac590ac989b3fa08ed1200ac410c2ccb9bd9c8a95f15f73422acf4`、`049ff089f20e8bbc1e72090d54d2ae88ea15ef84e324819241a07e2d68bd160f`、`41fae5ad009edbcc1c947c0266182b99c924cc728db21ad9942770236e7b397e`）锁住旧行为；本人对照固定 4d5 原件核过这三份 SHA。a665 的 synthetic/真实差分已比完整 ordered/blank summary、六个 blank interval 字段、三族行帧/身份及 digests；unchanged ordered 特意给 native 空 before stream，旧事实须为零 summary、无 records；真实 t1–t4 遇到旧 Python predegraded 现在明确失败，不能静默计数跳过。八包 `datasets.json` identity/size/tar SHA 常量与 P5 S4 §8 固定表一致；工具仅逐表调用冻结 Python 及 native probe，非完整旅程。

**N 与控制的后续补证：**a665 的单任务 pool 证据偏弱；固定 `39bfa7552ed480c625e139c6e7beacbb8e56c154` 增加同一 `KernelContext`、同一 Rayon pool 的 12 项 keyed/keyless/ordered `par_iter`，按输入序收集 N=1/4 的计数、locator、digest 签名，结果释放后核 16 MiB 余额恢复；另加已到期 `Instant` 的 deadline 错误向量。固定 `20e226206d` 增加当前 canonical 伪 GID=-1 与冻结 Python 的诊断差分。`cab0656d68dde02074bfe3ebef0393c19b082e0c` 相对 39b 仅为新测试 Rust 格式调整，vnext tree=`6be70a9dc215d27aa5fcd682e01bd50f43998857`；detached WT clean。静态证据设计缺口已关，仍待唯一 06 当前候选运行，不把 probe 当 C/D 生产接线。

### 2.3 真实数据 CLI 的当前 owner 接线

固定 cab 的 `benchmarks/s3_b_real_table_diff.py` 原复用旧 `p6_v1_ordered_diff._materialize_package`，该 helper 缺当前 `preview_jobs._materialize_uploaded_side` 的必需 `repository_id`、`export_cache` 两参数且只解包 3 项；CLI 也未建立 `current_kernel_context()`，直接运行会在测试内核前失败。此为替换期取证入口缺口，不是 Rust 产品预算第三轮。固定 `4efa4b3ec5457e83e48d9fbf2e18245e67afdc51` 在 B 自有工具内用当前五元返回首项和必需参数物化，进程初始化固定 N=1，每 tier 用新的 `KernelExecutionContext(OperationMemoryBudget(24 GiB), NeverCancel(), 1)` 包住 v1/v2 物化、逐表差分和 reader 关闭。本人对照 `preview_jobs.py` 当前签名/返回及 `real_dump_journey.py` scope 范式核过，静态前置缺口已关；Rust tree=`8c7e096e6b9bae5ca12e12c66e79bbec59371146` 与 cab 相同，vnext tree=`aa640aafe3c5e50d2d72239c18591200668e8963`。旧 p6_v1 工具未改，4efa 的 CLI 仍待 06 实际运行。

## 3. 06 执行稿的 DC68 停止复核

本人先用 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'` 确认连接，再只读核 `/home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/` 原件。`pre-run-command-errors.log` 现场 SHA256 为 `60e8fc6c95ef2d677cb70babc7a6e64e4545d5c917a358071b99b39dbc21d3b0`，记录第一次可选只读检查因节点无 `rg` 返回 127；第二次改用 `grep` 时 shell 引用错误，把 `WT`/`LOG`/`EXPECTED`/`run_step` 当命令并产生引号 EOF，再返 127。此汇总日志保存了两次错误的 stderr/exit 与作用范围，但没有独立逐字的两次原始 argv，不能据此复原完整命令行。

待执行 `run-rust-focused.sh` 现场和侧车 SHA256 均为 `841e85777ed758fe85e2de4ebf4225985ea81efa44e1b19c7db872515b68ca1b`；脚本本体含固定 HEAD/clean/六锁/离线/toolchain 前后检查、fmt → core clippy → focused tests 首错停。脚本引用的 worktree 路径虽含旧 `9b34` 目录名，现场 HEAD 为 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 且 clean，不能把目录名误判为错误 HEAD。该次证据目录没有 `rust-focused.log` 或测试输出；`marker-release.log` SHA256=`896fdef8270870edcf874ed51171a2c0a4d9906f1123c45c38a37a2d1a6e229d`，记录 06 主机 18:55:38Z 因连续自身命令错误在测试前释放占用。现场占用目录不存在。两次失败均在被测对象运行前，但已重复，按 DC68 停止；本人没有作第三次预检或启动任何测试。此节仅裁定执行停止，不评价 B 代码 GO，也不计作产品预算修复轮。

**最小恢复执行稿建议：**保留两次失败文件与 SHA；Owner 对 DC68 恢复作决定后，测试者重新原子取得 06 占用，核固定 b917 worktree clean/六锁/离线缓存；删去可选 `rg`/`grep` 源码检查与嵌套 shell 引用，按字面执行 `bash /home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/run-rust-focused.sh` 一次。首个被测步骤失败即停，记录 hostname、起止 HEAD/time、各步 exit、最终 exit 与日志 SHA。若候选源码已另修，则先固定新 SHA、使用对应 clean worktree 和新脚本，不把 b917 结果沿用到新树。此建议不授权在 Owner 决定前重试。

Owner 后已明确“允许放行”；同一 06 测试者按上述已审脚本实际恢复一次。本人只读核 `rust-focused.log` SHA256=`5ba79e1bf4c38850f9f35ba1f1ae77b30364e863987eb2a1fefafc167a20cf74`，脚本 SHA 仍为 `841e85777ed758fe85e2de4ebf4225985ea81efa44e1b19c7db872515b68ca1b`：hostname `gw-dms-06`、22:35:01–22:35:15Z、起止 HEAD=b917 且 clean、六锁未变、offline/jobs4/toolchain1.97；fmt exit 0，core clippy exit 101，`standard.rs:487` 两处 `usize` 错误解引用 E0614，按首失败停，focused test 未运行，整体 exit 101。保留该失败，后续只验证修正后的新固定候选，不重跑 b917；此编译错误与预算第二轮无关。

### 3.1 4efa 唯一执行首失败与下一最小修正

06 完整脚本先按原 SHA `5a4a46ed177f030611db3f785e4edf9150ae98f9bc2befee636345bd09b8ff54` 只读审；为符合仓库 Rust selector 前提，同一测试者在启动前把 `cd "$WT/vnext/rust"` 移至 rustup 检查前，最终脚本 SHA256=`90f436b460b5f3228713d2860d6ca64b6df7732fa093158e54ce090b2d2d4825`，输入 SHA helper SHA256=`dac92e185be66cba8178d1e4dbf779fb91fe9158a313b4b9ba27629d3b7555cd`。脚本逐步记录完整 argv/time/exit，核 clean HEAD、legacy、六锁、offline/jobs4、当前 Rust tree build-input，顺序为 workspace fmt/clippy/test → 原生扩展强制重装与 build-input 核验 → Python 6 差分 → 八包 SHA/按表对照 → 五 Python 包 ruff/mypy，首失败停。06 现场数据根目录与 manifest `package.tar.gz` 行形状已只读确认。

4efa 实际 `run-final.log` SHA256=`ee3a15b125830433289684a5ee46334f6ac20286d18a4c07c195b10860791b38`：hostname `gw-dms-06`，23:05:08–23:05:25Z，起止 HEAD 同为 4efa，仓库 `rust-toolchain.toml` 选择 1.97，四工具同 bin，六锁前后相同，`LOCK_DRIFT=0`；fmt exit 0，workspace clippy exit 101，`ordered.rs:561` 的 `option_strings.try_fold` 因绑定非 `mut` 报 E0596；workspace test、后续 Python 与真实按表全部未运行。固定 `4f1bd419dc7d66da0cb1b8bd0c5de59c6df8587c` 仅将该绑定改 `let mut option_strings`，detached clean、Rust tree=`edc408d4a9b96af2a1c851eef98e2df3863840ea`；本人静态核为精确语法修正，未重开已关闭预算根因，仍待其 06 新执行。

4efa 之前一次 bundle 传输准备调用在非仓库上下文执行裸 `git bundle verify` 而 exit 1，发生在 fetch/checkout/测试之前。开发侧保存的 `setup-attempt-1.log` SHA256=`b20e21701a211cd8bfa8378ee775eb05798e1ddaf14257b9b40a6b12d6562a61`，文件自述为事后从工具调用与返回誊录，不是原始独立 shell argv 日志；它能支持错误内容和已知作用范围，不能伪称实时原始日志。按 DC68 从 bundle verify 步骤修正仓库上下文一次并继续；该准备错误不计 B 产品失败或预算修订轮。

## 4. 容器与后续证据

本轮最新受审固定 HEAD=`4f1bd419dc7d66da0cb1b8bd0c5de59c6df8587c`（前轮 4efa，增量仅编译 iterator 绑定）；`gateway-compute-core/Cargo.toml` 已将已锁 `sha2` 从 dev 移至 regular dependency，且 Rust product tree 变化，**触发**当前产品镜像重建判定。workspace 版本仍精确 `=0.11.0`，Cargo.lock 未随 a4ff/ac21/4f1 变化；06 当前候选离线构建命中待实际日志核。B 不接生产路由，当前容器验证延期到 E 最终固定 HEAD 在 04 的集中门禁，不能称 a4ff/b917/ac21/4f1 已 PASS 或 carried。最近既有已验证 image revision=`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`、source tree=`56720104af34a1eb677336f57bdbc07444a56615`，仅为 BE-a/d 历史基准。

完整 B 候选还须有 06 clean 已提交 worktree 的 fixed/property/旧生产临时差分、随机 batch/允许 N 确定性、预算/取消/截止与 t1–t4 v1/v2 按表差分；八个输入 SHA 须逐包对照 `datasets.json` 与 P5 S4 handoff §8，旧 expected 来自 Contract/A/冻结 Python。B 不跑完整真实旅程、04 runner/carried、Compose 或 CT108 正式性能；这些留后续阶段对应节点。最终独审需核原始日志/脚本/摘要与手册边界后再给 GO 或明确 finding。
