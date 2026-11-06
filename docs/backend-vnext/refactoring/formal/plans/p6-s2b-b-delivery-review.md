# S2b B 恢复交付独立审核

状态：**审核进行中，B 未 GO**。本报告由恢复后的独立审核者 `/root/s2b_b_review_resume`（GPT-6-Astra/high）维护；原 [B 审核记录](p6-s2b-b-review.md)保留历史失败与停止事实，不改判通过。Owner 的恢复授权与边界见 [B 任务单](p6-s2b-b-kickoff.md)及 DC86 补充。

## 1. 固定审核起点

新只读 detached worktree 为 `/home/dev/gdds-test-tmp/s2b-b-delivery-review`，初始检出授权文档提交 `1e224e6d0bff2001597efc03bfbc4bbee6433a33`，已核 clean 和指向仓库本地 `legacy` 的链接。本报告在 main 按显式路径提交；审核工作区不修改产品/测试，不运行开发主机测试，也不派生角色。

产品起点 `5621bd48531b7af465e878f1bc7f87f707a772a3` 的实际差异已重新检查：`633e599cbc` 的 catalog 必填源行数及 binder 接线、`9225f78883` 的 projection 绑定源行数字段、`75f2ddac93` 的格式修正、`5621bd4853` 的既有 example 首行 policy 修正。未发现这些已完成小步的新增阻塞。业务版本/摘要没有因 catalog 字段变化而改变，binder 身份检查仍在原时点。

当前 Rust 仍只有公共 API 与初始 preflight，不能据此宣称完整 Arrow schema/name/type/binding、实际行数比对、三个业务 kernel 或 C Stream adapter 已实现。该结论不重做 A 或 S2a；A 的 workspace tests 不等同完整 architecture CLI，旧 B 两次 cargo 又缺少原子占用，均不能成为本次通过或 carried 来源。

## 2. 恢复执行前置

实施者统一占用和执行 06，审核者只读核证、不并跑。恢复占用记录 `/tmp/s2b-b-resume-acquire.log` 已读取并复算 SHA256 `fa76313434f56b10c537890147fcdd509bd13d71c89245e063b96a1c4d374d9e`。实施者报告实际原子 `mkdir` 成功；审核者另经 BatchMode SSH 独立确认 `gw-dms-06` 的 marker owner 为 `/root/s2b_b_impl_resume`、用途为 B focused Rust/native、开始时间 `2026-11-06T11:54:08Z`。当时工作区 `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` 与 `refs/codex/s2b-b-source` 均为 `75f2ddac93fc5b1b5cfb9f41dd7fb51dae421cbf`，porcelain 为空，legacy 链接正确。

既有 `/tmp/p6-s2b-b-source-main-5621bd4853.bundle` 已独立复算 SHA256 `92adc55e3b0c55082c64571e0be02cce43c6a060f351a6966283dcd97ba5b29a`。最小同步脚本 `/tmp/s2b-b-sync-resume.sh`（SHA256 `571034b5358db3687c8b0b6dbf826903ecf77aa69ca2eab856943ed5a95faa57`）已静态核：固定参数单源、dirty 拒绝、目标 SHA/verify/list-heads、fetch 后核新对象，再 checkout。定向脚本初稿 `/tmp/s2b-b-focused-resume.sh`（SHA256 `42bb2cf6f532b142793ac94f1933980e730e0f51bc886628f42cea6fbeb1c4f0`）已核，要求实际运行日志补打印离线/jobs/外置目录/build-input 设置，并记录同步 wrapper exit。原范围同步与 focused 可继续，不表示产品通过。

同机残留、缓存来源/离线配置、实际 selector、起止 HEAD/时间、退出码与最终日志 SHA 由后续真实执行记录闭合；此处不预写结果。

## 3. 语义与证据审核范围

沿用原审核 §3 的一次性完整矩阵及任务单，不逐轮扩矩阵。独立依据为 owning Contracts、原 Python 算法与现存 SQL Snapshot/Shared Kernel/ENUM-SET/composite golden；不会从 Rust actual 回填 expected。重点包括 SET sequence 直接进入 cell-frame、SQL 重复 warning 与 projection blocker 分层、PROVISIONAL 无摘要、完整诊断及 1024/omitted、keyed frame tuple 排序、keyless 重复/零列、ordered 与 canonicalized-input、actual row-count 绑定、catalog 过滤前校验及 binder 优先级、不同摘要域、复制前预算和同时驻留、取消/真实可选 deadline、caller-owned pool 与真实 C Stream。

Core 必须核实际 Arrow/schema/binding，Python 预计算诊断不能代替它；adapter 不直接依赖 Shared Kernel，不改 guard。仍有生产消费者的原 Python 路径保留到 D/E；C 的存储/恢复、D 的 M/control 与 E 的最终切换不提前纳入 B。

## 4. 当前验证与镜像决定

当前产品 HEAD：`5621bd48531b7af465e878f1bc7f87f707a772a3`。恢复后的合格业务测试证据尚待实际执行；B 最终门禁未运行，carried 无。中间骨架修改不逐次重建镜像，按任务单延期到收敛的 B 最终候选完成适用 Rust policy/完整 CLI、五 Python 静态、强制重装扩展及 Rust tree checker、相关 native focused 与当前镜像 health/clean-stop/native smoke。

最后已验证镜像仍是 A 产品 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`：06 backend 本机 image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`，Rust tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`，来源见 [A 审核 §7](p6-s2b-a-review.md#7-最终-db776-验证结论)。该结果不冒充 B 当前候选，dependency-base 以最终完整输入与 config/全部 DiffID 判定。S2b 最终 04 runner/container 与 t1–t4 正确性仍保留；W1/W2、真实 FULL 峰值和生产 M 未知保持未知。
