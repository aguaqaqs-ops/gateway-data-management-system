# AGENTS 结构整理定向复核（2026-11-08）

结论：**通过，可接受固定治理候选 `f08f596c0f792c1fa25c5ed7985585465023147c`。** 初审 F1、N1 均关闭；有限去重未发现丢失原约束、引入新要求或失效引用。本轮无新增阻塞或非阻塞 finding。此结论只覆盖本次六份治理文档，不覆盖期间并行产品提交，不授权推送或节点 main 同步。

## 1. 对象与方法

- 固定区间：`f08f596c0f^..f08f596c0f`。只读 detached worktree：`/home/dev/gdds-agents-rereview-20261108`，已核 HEAD 与 clean 状态。
- 本人核对本提交确实只有 A、T、第二轮交接、初审报告入库副本、首轮整理交接、references.tsv 六份文档。候选父提交的 A/T 与初审 `ea3b17307d067163c576a4f90b640366f98ef151` 逐字相同；FE3 kickoff 在首审与本候选之间也未变化。
- 按初审 finding 关闭标准与初审 §6 的保留项逐项阅读实际 diff、新位置及其前后条文；初审的 115 项原文语义核对继续有效，本轮定向重核实际受影响项，未把交接自检结果当作独立结论。
- 只运行本地 Git 与文本/标题/链接检查；未写被审 worktree，未运行产品测试、编译、lint、容器或节点命令，未创建子 agent。初审原件与初审 worktree 均未修改。

以下 A/T 行号均绑定本候选；A 为 `AGENTS.md`，T 为 `docs/backend-vnext/testing-conventions.md`，K 为 `docs/frontend-vnext/fe3-kickoff.md`。

## 2. Finding 关闭

| 项 | 候选位置与独立核对 | 结论 |
| --- | --- | --- |
| F1：每次运行镜像取证范围扩大 | T:468 明确工具链沿 FD7；依赖镜像 tag/dependency-input label/本机 ID/全部 Layers、RS tag/ID/三个 labels、backend/worker 本机 ID及 Docker/Compose 版本按 K §4.3；config digest/全部 DiffID 仅跨节点传输比较并写 handoff，不要求每次 save 依赖镜像。与 K:271–277、470及原 kickoff 审核 N5 一致 | **关闭**；恢复原义，没有新脚本或取证要求 |
| F1 关联记录 | references.tsv 仅 R443 的核对结论改变，记录初版冲突和修正去向；首轮交接 §4 同步标出 F1，状态开头明确其为初版历史记录并链接第二轮 | **关闭**；没有以修改原引用来掩盖冲突 |
| N1：“三处澄清”计数不符 | T:7 改为“相关措辞按 owner 确认澄清” | **关闭** |

## 3. 有限去重的规则保留核对

| 改动组 | 候选落点 | 实核结果 |
| --- | --- | --- |
| A 节点规格移出 | A:34–41；T:25、27 | SSH 别名、节点用途、共享宿主边界及 06/07 worker 设置仍在 A；IP、CPU/RAM/thin 容量、扩容日期仍在 T。自主并行/本节点占用/端口/计时独占/实际冲突协调未变 |
| S2b E 一次性用途转历史 | A:41；T:646–650 | 授权原段逐字保留，新增历史限定不扩大用途；A 链接已指向新标题。06 fresh t1–t3、04 并行、t4 沿独审及职责不转移、clean/占用/离线要求均在 |
| mypy 历史耗时移出 | A:226–240；T:644 | 1.5 秒观测附原 A 提交归入历史；五包 Ruff/mypy、RS strict/tests、禁止省略、wrapper 命令与 Rust 的 05/06/占用/外置 target 要求保持。Q6 未变成常设豁免 |
| uv 实际环境与派生缓存排除 | T:129–145 | 实际 uv 环境目录内容与三种排除 `__pycache__`/`.pyc`/`.pyo` 先完整移入闭包主段。只对锁定源码与对应 Python 解释器派生项排除，没有扩大排除范围 |
| Hypothesis 生命周期 | T:119–127、163–168 | Python 包专属固定路径、TMPDIR 空值 /tmp fallback、worktree 外绝对 TMPDIR、manifest 前打印/删除残留、退出含失败与可捕获中断、仅清理专属目录、同包两遍共用、focused 区别、carried 同路径且不存在均保留 |
| 完整闭包与变化处理 | T:133–159、161–174 | Git/legacy/uv/缓存路径内容权限、工具与 daemon、build 指纹、基础/服务/依赖/client image ID、prebuilt inventory、Rust 工具链/解释器/cargo config/指纹、tracked 0o7777/祖先/context 根、非 Git 类型权限内容与 ignore 拒绝均在；依赖镜像名称/ID/开关变化重跑、凭据仅摘要及合格来源条件未变 |
| 镜像等价段去除重复输入清单 | T:333–357；A:182–188 | 三条资格仍完整。RS 两 labels 在最终 HEAD 重算、backend 在来源同 WT 检出最终 HEAD并与来源起始 manifest compare、同节点限制、禁止另一 WT 判等价或不等价、exit 合入后清理 WT 均保留。删除内容由闭包主段精确链接承接 |
| 包沿用与 V..H 分判 | T:161–174、356–362 | 来源须实际包通过/整次 exit 0/clean/起止 HEAD，沿用链直指初次实跑；backend Compose 随包沿用，但 V..H 镜像等价独立且阶段最终 HEAD须满足全部条件。同提交已通过 Compose 不单独重跑规则保持 |
| wrapper/no-sync 合并 | T:178–203 | run/sync locked 与环境隔离、no-sync 先只读 lock check 再 locked no-sync、不得自动 sync 替换待验证 wheel、五锁前后比较/漂移非零/不 restore、改锁授权与重新同步、canonical owner及示例均保留 |
| 两遍批次集中 | T:205–232 | 完整并行 marker 与 serial -n 0 命令、三小包单进程、Rust 首包/自行并行、不受测试 workers 影响、默认 auto/节点并行度、parallel_safe 逐项隔离条件及四项清单均在 |
| G11 历史基线迁移 | T:635–642 | 原提交、测试数/marker 数、可重叠说明、精确耗时、墙钟、91.7% 及 handoff 链接均保留；未改数值或把历史耗时作当前承诺 |
| P2 历史限定 | T:247–283 | 原标题、命令、inventory、精确排除范围、最终候选条件及触发重建边界保持；只将“当前延期”明确为当时历史安排 |
| FD7/M1 与其他硬约束 | A:78–103、T:431–475及本提交 diff | 除 F1 镜像字段外未改：mock 不占用、真实脚本自行取/释放占用、session/预取锁 exit 3、secret/输入来源/清理顺序、M1 重置后 VmHWM 基线与 VmRSS 记录、renderer 判定等均保持；未收入 FE3a 临时全占用或旧统一 05 规则 |

本轮没有修改测试机制、Docker/Compose 触发条件、DC68、依赖授权、主线/阶段边界、比例化或 artifact cleanup 保障。初审列出的裸 uv 示例等既有文字问题未在本轮重开，亦未因去重扩大影响。

## 4. 标题、引用、原件与文档检查

- A 的 12 个二/三级标题逐字、按原序保留；T 初审已有 30 个二/三级标题全部按原序保留，只新增“测试批次与 focused 运行”“G11 与静态检查历史观测”“历史阶段说明”三节。
- A 的权威运行前提、镜像身份等价及其第 3 条、镜像身份、backend/worker、DC67/DC68 文字入口仍在。原 115 项映射只发生上表覆盖的落点迁移；第二轮对照提供后续去向，没有伪改首轮行号。
- references.tsv 仍有 451 条；逐条比较 id、原文件/行与完整引用文字，全部未变。核对结果只有 R443 更新。
- 对本提交五份 Markdown 文件检查全部 48 个本地链接/锚点，目标均存在且锚点可定位；历史初审的绝对 worktree 链接仍有效。`git diff --check HEAD^ HEAD` 通过。
- 入库初审副本与 worktree 外原件逐字一致，SHA256 均为 `3c5036c95e71ebceed60edc5ddb09386d1343c27b9fdc405ced2419512c885a9`。初审“暂不接受”结论保留为其固定对象结论，本复核单独关闭 findings，没有改写原报告。
- 资源前提与基线静态检查失败只按原交接保留，没有新节点执行。Q6 仍仅是本次纯文档提交例外；没有宣称当前或并行产品代码五包通过。

## 5. 容器决策及接受边界

- Current HEAD：`f08f596c0f792c1fa25c5ed7985585465023147c`。
- Container rebuild required：**no**；本提交六份文档不触碰产品、依赖、deployment、harness 或 container-only runtime boundary。
- Last verified image revision/source-tree：**本轮未读取、未验证**。
- Container gate for current HEAD：**not-applicable（本次治理文档复核）**；Carried from：**none**；本轮无新增延期门禁。

本轮治理整理审核通过，可以由主会话提交本复核报告并更新交接状态，交 owner 接受。后续若仅添加报告与状态，不必重开产品验证；如再改规则正文，应按实际 diff 定向核对。本结论不覆盖 `ea3b17307d..f08f596c0f` 期间的并行产品改动，也不把本候选称作产品门禁通过。推送和节点 main 同步仍按用户后续明确授权办理。
