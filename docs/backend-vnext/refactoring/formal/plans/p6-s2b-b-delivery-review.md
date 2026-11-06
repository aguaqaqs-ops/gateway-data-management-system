# S2b B 恢复交付独立审核

状态：**审核进行中，B 未 GO**。本报告由恢复后的独立审核者 `/root/s2b_b_review_resume`（GPT-6-Astra/high）维护；原 [B 审核记录](p6-s2b-b-review.md)保留历史失败与停止事实，不改判通过。Owner 的恢复授权与边界见 [B 任务单](p6-s2b-b-kickoff.md)及 DC86 补充。

## 1. 固定审核起点

新只读 detached worktree 为 `/home/dev/gdds-test-tmp/s2b-b-delivery-review`，初始检出授权文档提交 `1e224e6d0bff2001597efc03bfbc4bbee6433a33`，已核 clean 和指向仓库本地 `legacy` 的链接。本报告在 main 按显式路径提交；审核工作区不修改产品/测试，不运行开发主机测试，也不派生角色。

产品起点 `5621bd48531b7af465e878f1bc7f87f707a772a3` 的实际差异已重新检查：`633e599cbc` 的 catalog 必填源行数及 binder 接线、`9225f78883` 的 projection 绑定源行数字段、`75f2ddac93` 的格式修正、`5621bd4853` 的既有 example 首行 policy 修正。未发现这些已完成小步的新增阻塞。业务版本/摘要没有因 catalog 字段变化而改变，binder 身份检查仍在原时点。

上述起点的 Rust 只有公共 API 与初始 preflight，不能据此宣称完整 Arrow schema/name/type/binding、实际行数比对、三个业务 kernel 或 C Stream adapter 已实现；后续实现见 §4–5。该结论不重做 A 或 S2a；A 的 workspace tests 不等同完整 architecture CLI，旧 B 两次 cargo 又缺少原子占用，均不能成为本次通过或 carried 来源。

## 2. 恢复执行前置

实施者统一占用和执行 06，审核者只读核证、不并跑。恢复占用记录 `/tmp/s2b-b-resume-acquire.log` 已读取并复算 SHA256 `fa76313434f56b10c537890147fcdd509bd13d71c89245e063b96a1c4d374d9e`。实施者报告实际原子 `mkdir` 成功；审核者另经 BatchMode SSH 独立确认 `gw-dms-06` 的 marker owner 为 `/root/s2b_b_impl_resume`、用途为 B focused Rust/native、开始时间 `2026-11-06T11:54:08Z`。当时工作区 `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` 与 `refs/codex/s2b-b-source` 均为 `75f2ddac93fc5b1b5cfb9f41dd7fb51dae421cbf`，porcelain 为空，legacy 链接正确。

既有 `/tmp/p6-s2b-b-source-main-5621bd4853.bundle` 已独立复算 SHA256 `92adc55e3b0c55082c64571e0be02cce43c6a060f351a6966283dcd97ba5b29a`。最小同步脚本 `/tmp/s2b-b-sync-resume.sh`（SHA256 `571034b5358db3687c8b0b6dbf826903ecf77aa69ca2eab856943ed5a95faa57`）已静态核：固定参数单源、dirty 拒绝、目标 SHA/verify/list-heads、fetch 后核新对象，再 checkout。定向脚本初稿 `/tmp/s2b-b-focused-resume.sh`（SHA256 `42bb2cf6f532b142793ac94f1933980e730e0f51bc886628f42cea6fbeb1c4f0`）已核，要求实际运行日志补打印离线/jobs/外置目录/build-input 设置，并记录同步 wrapper exit。原范围同步与 focused 可继续，不表示产品通过。

首轮实际同步日志 `/tmp/s2b-b-resume-sync.log` 已独立读取并复算 SHA256 `fffbe1458e3c1a49890ee8a75256ce09a5c4e89c0390293112ab4f1723233fe2`：06 `11:55:34Z–11:55:35Z`，前后 HEAD 明确为 clean 75f2 → clean 5621，目标 bundle SHA、verify/list-heads、fetch/checkout 均成功。该文件没有独立 exit 字段，不把工具调用结果伪称为日志字段。

首轮 06 `/home/dev/gdds-test-tmp/logs/s2b-b-resume-early-5621.log` 已独立读取并核 SHA256 `7e8018553e093dbc107ef9225bdec68a90ad7936a9bf45d07aebe76dc5c3948a`：`11:55:35Z–11:57:23Z`，busy owner 正确，UV/Cargo offline、jobs 4、外置 TMPDIR/target 与 build-input 明确；rustc/cargo/rustfmt/clippy-driver 实际解析到同一个 1.97 工具链。fmt、完整 architecture CLI、core 46 项、强制重装扩展、tree checker 与 29 项 composite/business 测试全部成功，最终 exit 0。实际 installed=expected=`b15994f769746faa7fad49a7d332587da0a58d85`，已另以 Git 核为 5621 的 Rust tree。

该 focused 日志开头未打印 HEAD；固定脚本在执行前断言 expected=5621/clean，紧邻同步日志和结尾 HEAD/clean 提供绑定，不能把它写成日志有起始 HEAD 字段。已要求以后脚本显式打印起始 HEAD，不为这项格式补跑整批。本轮是恢复后首份成功定向证据，只覆盖已有骨架/catalog与回归，不证明尚未实现的业务 kernel。后续执行继续核同机残留与缓存来源，不因首轮成功取消前置。

## 3. 语义与证据审核范围

沿用原审核 §3 的一次性完整矩阵及任务单，不逐轮扩矩阵。独立依据为 owning Contracts、原 Python 算法与现存 SQL Snapshot/Shared Kernel/ENUM-SET/composite golden；不会从 Rust actual 回填 expected。重点包括 SET sequence 直接进入 cell-frame、SQL 重复 warning 与 projection blocker 分层、PROVISIONAL 无摘要、完整诊断及 1024/omitted、keyed frame tuple 排序、keyless 重复/零列、ordered 与 canonicalized-input、actual row-count 绑定、catalog 过滤前校验及 binder 优先级、不同摘要域、复制前预算和同时驻留、取消/真实可选 deadline、caller-owned pool 与真实 C Stream。

Core 必须核实际 Arrow/schema/binding，Python 预计算诊断不能代替它；adapter 不直接依赖 Shared Kernel，不改 guard。仍有生产消费者的原 Python 路径保留到 D/E；C 的存储/恢复、D 的 M/control 与 E 的最终切换不提前纳入 B。

## 4. 首批业务实现审核与修正记录

已将 detached 审核工作区固定到 `4b546c46de`，读取 `business_kernel/cells.rs` 与 `operations.rs` 全部实现。现有 `encode_uleb128` 仅由 crate-private 升为 public 并在 lib re-export，算法与 module/decode 边界未变，符合本次真实 core consumer 的授权。三个操作已出现主体，但尚无该批业务测试或 adapter 交付。

以下问题已直接交实施者，修复后按固定差异和实际定向结果复审：

- **资源边界**：诊断先创建 String 再检查字节，且 diagnostics 与 workspace 的 live 额度分别比较，漏同时驻留；catalog 多表 metadata/表数等尚未整体限额；output 只计 arrays，遗漏返回 descriptor/facts。修正应沿现有局部预约，不建立全局 allocation 框架。
- **实际绑定与业务 schema**：descriptor 的 logical/declared/labels 一致性未完整验证，projection 只核 source/output 同名，空表可用错误计划把不支持的源声明伪成支持类型。ordered 输出 gid/no、规范 gid 类型/非空与 canonical key 约束，以及普通 key 输出非空属性尚未完整守住。catalog 的 `NamedKernelTableInput.table_name` 未消费，需绑定实际 descriptor。
- **已冻结语义**：空 SET key 被先当成空文本判 `KEY_EMPTY`，原 owner 应为 `UNSUPPORTED_TABLE`；SQL reserved gid 的文本检查使用 Rust `parse`，遗漏原 Python `int` 可接受的形式（例如 `4_000_000_000`）。ordered 数字字符串继续保持拒绝，不与 SQL 共用宽松转换。
- **输出构建**：始终使用 small String/Binary arrays，不能承接合法 Large 输入的整列 payload；自有 values/text 构建循环缺少运行中 checkpoint。应按既有 offset 口径选择布局，在自有循环及标准库大调用前后检查 control。

这些是原一次性验收清单内的具体缺口，不增加新业务范围。独立向量、差分、最终 native/容器等仍待实际交付，不把当前主体实现当成 PASS。

`573421b151119745b72749e37c65d7dabb3f7c99` 已在 detached worktree 复审：诊断单条构造前检查与局部固定 envelope 预约、catalog 聚合预算及名称绑定、输出 descriptor/facts 估计、large offsets 与逐行 builder checkpoint 均已补；类型核验复用既有 parser vocabulary，retained source/output 映射与 ordered/key schema 约束已补。被丢弃的合法源列不受 projection 白名单拒绝。reserved 文本 gid 的 Nd/下划线处理仍待 native Python oracle。SET 修正另发现 NULL 优先级问题：应先保留 `NullScalar → KEY_NULL`，只把非 NULL SET 判为 `UNSUPPORTED_TABLE`，已交实施者修正。

该批七项新 core 测试的独立预期已核：现有五 SQL Snapshot golden 的 READY 表摘要及 PROVISIONAL、固定 SET cell sequence、手工 keyed 物理顺序 `[2,10,-1]` 与 IPC 置换、keyless 零列三行、ordered 固定 gid/no 分配、非空零命中 catalog、初始取消与 output cap。尚未覆盖的完整诊断、部分/整体失败、运行中控制及 adapter 等仍按原矩阵待交付；不把测试数量当作完整覆盖。

以下 06 日志已独立读取并核 SHA；实际脚本 SHA 均为 `4062c80616f088590ae6163c0244c3559963301cfed1f5f74521576eef7785c3`，均有本任务 busy、offline/jobs/外置 target、起止 HEAD/clean 与 exit：

| 日志 | 固定 HEAD 与结果 | SHA256 |
| --- | --- | --- |
| `s2b-b-core-4b546.log` | 4b546；12:03:27–12:03:28 UTC；ULEB re-export 顺序导致 fmt exit 1，测试未开始 | `24869748e4207dcf1c8469134c25caafce1739ecd262b94745da5b8a0fa5bb2c` |
| `s2b-b-core-uleb-format.log` | df77938b8b；12:03:41–12:03:50 UTC；唯一格式修正已核；fmt、原 core 46、Shared Kernel 82+3+3、完整 CLI exit 0 | `ec39b2ae631dd636e0e67894bc73bbf100d66516646e732e90a27d2879bbd983` |
| `s2b-b-core-boundaries.log` | 573421b151；12:12:39–12:12:47 UTC；fmt、core 53、Shared Kernel 82+3+3、完整 CLI exit 0；unused import warning 尚待最终 clippy 收口 | `a1dbd7d3c66c105f852ab39fc058d63f3ac95bba44703116c2513c50ba500690` |

## 5. Native adapter 与当前修正

已依次在 detached worktree 读取固定 `7791718138`、`da760448b306d76a4208b0b50d85e4ddb42bbc18`、`25fe793d961e7471d981b5b7afceca5811c197d1`。三个窄 adapter 复用 A 的 C Stream consumer、caller pool、cancel watch、detach 与 panic boundary；core 没有 Python/IO，adapter 没有直接依赖 Shared Kernel。Python 新 producer 保留规则、SQL spelling normalizer 和小 metadata，只有既定 composite exception 将过滤后的事实转回 Python。旧生产 caller 尚未切换，未为 B 提前删除或复制其 snapshot/manifest 调度。

实际复审闭合：非 NULL SET key 与 NULL 优先级；retained source SQL spelling 绑定（空 TEXT 不能伪装成 VARCHAR）；投影 display_name；真实零 batch reader 的 schema 保留；零列 synthetic batch 的固定 header 前置额度；多 stream 累计 rows/batches/input 与 adapter metadata；probe 异常优先于取消错误映射；Python 输出 metadata/facts 的复制前额度和控制检查。SQL 返回共享 Arrow buffers，计入 output、不会再作为新 owned live 重复相加；其他局部预约仍保守，不宣称是精确 allocator 计量，C/M 校准必须按真实生命周期。

新增 native 测试的独立 expected 已读取：真实 parser→B→A IPC，SET/UINT/负零、key 诊断、SQL warning/projection blocker、PROVISIONAL、Python int oracle、零 batch schema、零列非零行穿过 C Stream/B/A、ordered/canonicalized input、catalog 全 payload 与过滤前验证、消费中 row cap、运行中取消/deadline/probe 异常。25fe 补齐既定的 1050 列完整诊断顺序及 1024+26、被丢弃 JSON 值不影响摘要、metadata/live/input/diagnostic 拒绝、真实 parser 与现有 Python owner 的 PARTIAL/FAILED 分类。**本段只记录代码和 expected 审核；截至本次报告，da760/25fe 的 native pytest 尚未执行，不能记 PASS。**

### 一次同步前置错误与最小恢复

实施者在 da760 格式提交后用共享 main 的 `HEAD~1` 推断 previous，误取并发文档提交 `5aa63e384dfea114375d3c875d8e713e6cdd7021`；06 实际仍为 clean `0a9d8bf27329729b3e2b7c44f8dea12d3b8eeb51`。审核者实际读日志并独立 SSH 核目标 HEAD/clean/原 busy。同步在 previous 断言处拒绝，未 fetch/checkout；失败 bundle 保留。外层调用没有检查该非零结果，又调用了旧 HEAD 的 fmt；fmt 失败后没有编译或业务测试。

| 失败证据 | SHA256 |
| --- | --- |
| 本机 `/tmp/s2b-b-resume-sync-transfer-format.log`，12:29:53 UTC；previous 断言失败 | `a359eff7a51a5fe06c90fadb92886722853fdf2007fb68896f7bb432be2d4e4c` |
| 06 `/home/dev/gdds-test-tmp/logs/s2b-b-consumers-compile.log`，同一时刻；旧 0a9 fmt 失败 | `fe2e7bd50bd113945fc756e959ef62a24d8fa8326eb599050f9858b4f0243ec0` |

root 判定为新组合首次该因果的前置错误，授权一次最小修正；再失败即停 Owner。审核者实际读取并复算 source `/tmp/s2b-b-publish-source.sh` SHA256 `4b71db8839171db6879b285fe1f2e4837faa6a33ba1f06426a861be763b34864`、target `/tmp/s2b-b-sync-resume.sh` SHA256 `189338eab32e31b748c758aea43a5fd0068667105c53fa0c3a62a91c3961fa03`。candidate 先绑定任务自有 `refs/codex/s2b-b-transfer/<fullsha>`，bundle/advertised ref/fetch 使用该固定引用，不依赖其他会话暂停 main 提交；previous 取实际 0a9 full SHA，新文件名保留失败 bundle。已给这一次恢复执行 GO，要求同步的实际 rc 0 单独确认后才另 call 验证，未把此 GO 当成产品通过。

恢复已成功，审核者已独立读取 `/tmp/s2b-b-resume-sync-authorized-recovery.log` 并复算 SHA256 `d729ef6e3b6b0d01fa609e76ecd09f74a8c50f57f64a4cba20de3817a480e91f`：06 `12:39:23–12:39:24 UTC`，clean 0a9 → clean 25fe；bundle SHA256 `2edaf39a77916960017479f27711822cfd590569139d8deccd400c73465c787b`、固定 ref、verify/fetch/checkout 全部闭合。同步文件没有单独 rc 字段；实际独立调用成功后才开始后续验证，不冒称其有该日志字段。

### Native 实际结果与代码收口

`5dd7e8efb1965fec3163631890f574ed774f37db` 仅格式化输出预算代码；`d84094c76f21d67330f3c1fb905852d9478444d0` 仅收窄 Python 类型及测试非空断言。首轮 d840 的三例失败已实读：两例 NULL 主键在原 parser/materializer 的 NOT NULL 检查先失败，未到 B；1050 列测试把 parser 预算对象误传 dict，`getattr` 路径沿用默认 512。`8c889dac6d022c43249eff873a0f4789be9b2db6` 改用真实 `comm_user_data/data_key` 规则，使合法 nullable SQL source 进入 canonical key 检查；宽列测试用既有 `RESOURCE_BUDGETS` 对象并断言 parser COMPLETE。没有放宽产品规则或改变 KEY_NULL、1024+omitted 的预期。API 注释同步实际 Python normalizer/core schema owner。

以下日志已独立读取并复算 SHA；前一失败整次仍为失败，不能作合格 PASS/carried 来源。两轮 native 都使用原 busy、offline、jobs 4、外置 target/logs 和 `pytest -n 0`：

| 实际证据 | 结果 | SHA256 |
| --- | --- | --- |
| 06 `s2b-b-native-compile-7791.log`，12:19:14–12:19:34 UTC，clean 779171813864b378bb2214d13487bf85941b81a4 | adapter check、fmt、core/Shared Kernel、完整 CLI exit 0；不等于 native pytest | `2410d4e759669361ebe0309b0eb80c3102bb3f77b8babb020973c0a0ef304b29` |
| 06 执行、本机捕获 `/tmp/s2b-b-core-5dd7-remote.log`，12:40:11–12:40:27 UTC，起止 clean 5dd7 | fmt、adapter check、core 53、Shared Kernel 82+3+3、完整 CLI exit 0 | `47c19997ca705c5324c15589a551f2b4b3001f9dba2aa524fad6608a91c7453b` |
| 06 `s2b-b-native-focused-d840.log`，12:42:11–12:42:47 UTC，起止 clean d840 | 强制重装/tree checker、backend Ruff/mypy 通过；pytest 177 PASS/3 FAIL，整次 exit 1 | `3a0dc18ce6c78c0b92434da30570c6127bb072d4ea6353d4544d7b6e81489ab8` |
| 06 `s2b-b-native-focused-8c889.log`，12:45:22–12:45:37 UTC，起止 clean 8c889 | 强制重装/tree checker、backend Ruff/mypy 493 source files、180 项 native/既有 owner focused 全部通过，exit 0 | `39bc6ce3faf14c049b44ddec7ed5cba8a3f50bda635f890fb1f28a4f7a5a72cd` |

8c889 的实际 expected=installed Rust tree 为 `d90bd09352ec068558d1fb0334764037818d649e`，已另以 Git 核对。focused 脚本 SHA256 `5675b53f27e57c9170dc90f26c3f99cb3750894a266067e006776241b3899654`；选择 native business、Rust parser adapter、SQL/business snapshot、composite contracts/bind、projection core/integrity/contracts 现有 owner。§5 所列 native 预期至此取得实际通过证据，包括零列三行 C Stream→B→A IPC。当前代码与原一次性 native 矩阵无未闭合阻塞；B 整体仍待最终 Rust policy、五包静态与当前候选容器证据。

## 6. 当前验证与镜像决定

当前审核产品 HEAD：`8c889dac6d022c43249eff873a0f4789be9b2db6`。成功定向证据与实际覆盖见 §2、§4–5；B 最终门禁未运行，carried 无。中间算法修改不逐次重建镜像，按任务单延期到收敛的 B 最终候选完成适用 Rust policy/完整 CLI、五 Python 静态、当前镜像 health/clean-stop/native smoke；本候选强制重装、Rust tree checker 和 native focused 已通过，不因报告推进重复整批。

最后已验证镜像仍是 A 产品 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`：06 backend 本机 image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`，Rust tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`，来源见 [A 审核 §7](p6-s2b-a-review.md#7-最终-db776-验证结论)。该结果不冒充 B 当前候选，dependency-base 以最终完整输入与 config/全部 DiffID 判定。S2b 最终 04 runner/container 与 t1–t4 正确性仍保留；W1/W2、真实 FULL 峰值和生产 M 未知保持未知。
