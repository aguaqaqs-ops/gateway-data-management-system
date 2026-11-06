# S2b B 恢复交付独立审核

状态：**审核进行中，B 未 GO**。本报告由恢复后的独立审核者 `/root/s2b_b_review_resume`（GPT-6-Astra/high）维护；原 [B 审核记录](p6-s2b-b-review.md)保留历史失败与停止事实，不改判通过。Owner 的恢复授权与边界见 [B 任务单](p6-s2b-b-kickoff.md)及 DC86 补充。

## 1. 固定审核起点

新只读 detached worktree 为 `/home/dev/gdds-test-tmp/s2b-b-delivery-review`，初始检出授权文档提交 `1e224e6d0bff2001597efc03bfbc4bbee6433a33`，已核 clean 和指向仓库本地 `legacy` 的链接。本报告在 main 按显式路径提交；审核工作区不修改产品/测试，不运行开发主机测试，也不派生角色。

产品起点 `5621bd48531b7af465e878f1bc7f87f707a772a3` 的实际差异已重新检查：`633e599cbc` 的 catalog 必填源行数及 binder 接线、`9225f78883` 的 projection 绑定源行数字段、`75f2ddac93` 的格式修正、`5621bd4853` 的既有 example 首行 policy 修正。未发现这些已完成小步的新增阻塞。业务版本/摘要没有因 catalog 字段变化而改变，binder 身份检查仍在原时点。

当前 Rust 仍只有公共 API 与初始 preflight，不能据此宣称完整 Arrow schema/name/type/binding、实际行数比对、三个业务 kernel 或 C Stream adapter 已实现。该结论不重做 A 或 S2a；A 的 workspace tests 不等同完整 architecture CLI，旧 B 两次 cargo 又缺少原子占用，均不能成为本次通过或 carried 来源。

## 2. 恢复执行前置

实施者统一占用和执行 06，审核者只读核证、不并跑。恢复占用记录 `/tmp/s2b-b-resume-acquire.log` 已读取并复算 SHA256 `fa76313434f56b10c537890147fcdd509bd13d71c89245e063b96a1c4d374d9e`。实施者报告实际原子 `mkdir` 成功；审核者另经 BatchMode SSH 独立确认 `gw-dms-06` 的 marker owner 为 `/root/s2b_b_impl_resume`、用途为 B focused Rust/native、开始时间 `2026-11-06T11:54:08Z`。当时工作区 `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` 与 `refs/codex/s2b-b-source` 均为 `75f2ddac93fc5b1b5cfb9f41dd7fb51dae421cbf`，porcelain 为空，legacy 链接正确。

既有 `/tmp/p6-s2b-b-source-main-5621bd4853.bundle` 已独立复算 SHA256 `92adc55e3b0c55082c64571e0be02cce43c6a060f351a6966283dcd97ba5b29a`。最小同步脚本 `/tmp/s2b-b-sync-resume.sh`（SHA256 `571034b5358db3687c8b0b6dbf826903ecf77aa69ca2eab856943ed5a95faa57`）已静态核：固定参数单源、dirty 拒绝、目标 SHA/verify/list-heads、fetch 后核新对象，再 checkout。定向脚本初稿 `/tmp/s2b-b-focused-resume.sh`（SHA256 `42bb2cf6f532b142793ac94f1933980e730e0f51bc886628f42cea6fbeb1c4f0`）已核，要求实际运行日志补打印离线/jobs/外置目录/build-input 设置，并记录同步 wrapper exit。原范围同步与 focused 可继续，不表示产品通过。

首轮实际同步日志 `/tmp/s2b-b-resume-sync.log` 已独立读取并复算 SHA256 `fffbe1458e3c1a49890ee8a75256ce09a5c4e89c0390293112ab4f1723233fe2`：06 `11:55:34Z–11:55:35Z`，前后 HEAD 明确为 clean 75f2 → clean 5621，目标 bundle SHA、verify/list-heads、fetch/checkout 均成功。该文件没有独立 exit 字段，不把工具调用结果伪称为日志字段。

首轮 06 `/home/dev/gdds-test-tmp/logs/s2b-b-resume-early-5621.log` 已独立读取并核 SHA256 `7e8018553e093dbc107ef9225bdec68a90ad7936a9bf45d07aebe76dc5c3948a`：`11:55:35Z–11:57:23Z`，busy owner 正确，UV/Cargo offline、jobs 4、外置 TMPDIR/target 与 build-input 明确；rustc/cargo/rustfmt/clippy-driver 实际解析到同一个 1.97 工具链。fmt、完整 architecture CLI、core 46 项、强制重装扩展、tree checker 与 29 项 composite/business 测试全部成功，最终 exit 0。实际 installed=expected=`b15994f769746faa7fad49a7d332587da0a58d85`，已另以 Git 核为 5621 的 Rust tree。

该 focused 日志开头未打印 HEAD；固定脚本在执行前断言 expected=5621/clean，紧邻同步日志和结尾 HEAD/clean 提供绑定，不能把它写成日志有起始 HEAD 字段。已要求以后脚本显式打印起始 HEAD，不为这项格式补跑整批。本轮是恢复后首份成功定向证据，只覆盖已有骨架/catalog与回归，不证明尚未实现的业务 kernel。后续执行继续核同机残留与缓存来源，不因首轮成功取消前置。

## 3. 语义与证据审核范围

沿用原审核 §3 的一次性完整矩阵及任务单，不逐轮扩矩阵。独立依据为 owning Contracts、原 Python 算法与现存 SQL Snapshot/Shared Kernel/ENUM-SET/composite golden；不会从 Rust actual 回填 expected。重点包括 SET sequence 直接进入 cell-frame、SQL 重复 warning 与 projection blocker 分层、PROVISIONAL 无摘要、完整诊断及 1024/omitted、keyed frame tuple 排序、keyless 重复/零列、ordered 与 canonicalized-input、actual row-count 绑定、catalog 过滤前校验及 binder 优先级、不同摘要域、复制前预算和同时驻留、取消/真实可选 deadline、caller-owned pool 与真实 C Stream。

Core 必须核实际 Arrow/schema/binding，Python 预计算诊断不能代替它；adapter 不直接依赖 Shared Kernel，不改 guard。仍有生产消费者的原 Python 路径保留到 D/E；C 的存储/恢复、D 的 M/control 与 E 的最终切换不提前纳入 B。

## 4. 首批业务实现审核（待修复）

已将 detached 审核工作区固定到 `4b546c46de`，读取 `business_kernel/cells.rs` 与 `operations.rs` 全部实现。现有 `encode_uleb128` 仅由 crate-private 升为 public 并在 lib re-export，算法与 module/decode 边界未变，符合本次真实 core consumer 的授权。三个操作已出现主体，但尚无该批业务测试或 adapter 交付。

以下问题已直接交实施者，修复后按固定差异和实际定向结果复审：

- **资源边界**：诊断先创建 String 再检查字节，且 diagnostics 与 workspace 的 live 额度分别比较，漏同时驻留；catalog 多表 metadata/表数等尚未整体限额；output 只计 arrays，遗漏返回 descriptor/facts。修正应沿现有局部预约，不建立全局 allocation 框架。
- **实际绑定与业务 schema**：descriptor 的 logical/declared/labels 一致性未完整验证，projection 只核 source/output 同名，空表可用错误计划把不支持的源声明伪成支持类型。ordered 输出 gid/no、规范 gid 类型/非空与 canonical key 约束，以及普通 key 输出非空属性尚未完整守住。catalog 的 `NamedKernelTableInput.table_name` 未消费，需绑定实际 descriptor。
- **已冻结语义**：空 SET key 被先当成空文本判 `KEY_EMPTY`，原 owner 应为 `UNSUPPORTED_TABLE`；SQL reserved gid 的文本检查使用 Rust `parse`，遗漏原 Python `int` 可接受的形式（例如 `4_000_000_000`）。ordered 数字字符串继续保持拒绝，不与 SQL 共用宽松转换。
- **输出构建**：始终使用 small String/Binary arrays，不能承接合法 Large 输入的整列 payload；自有 values/text 构建循环缺少运行中 checkpoint。应按既有 offset 口径选择布局，在自有循环及标准库大调用前后检查 control。

这些是原一次性验收清单内的具体缺口，不增加新业务范围。独立向量、差分、最终 native/容器等仍待实际交付，不把当前主体实现当成 PASS。

## 5. 当前验证与镜像决定

当前审核产品 HEAD：`4b546c46de`。恢复后 5621 骨架/catalog 的成功定向证据见 §2，不能冒充本批新业务实现已测；B 最终门禁未运行，carried 无。中间算法修改不逐次重建镜像，按任务单延期到收敛的 B 最终候选完成适用 Rust policy/完整 CLI、五 Python 静态、强制重装扩展及 Rust tree checker、相关 native focused 与当前镜像 health/clean-stop/native smoke。

最后已验证镜像仍是 A 产品 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`：06 backend 本机 image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`，Rust tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`，来源见 [A 审核 §7](p6-s2b-a-review.md#7-最终-db776-验证结论)。该结果不冒充 B 当前候选，dependency-base 以最终完整输入与 config/全部 DiffID 判定。S2b 最终 04 runner/container 与 t1–t4 正确性仍保留；W1/W2、真实 FULL 峰值和生产 M 未知保持未知。
