# AGENTS 独审修正与有限去重（2026-11-08）

状态：固定候选 `f08f596c0f792c1fa25c5ed7985585465023147c` 经 GPT-6-Astra（high）独立定向复核通过，F1/N1 关闭，无新增 finding；待 owner 接受，未推送或同步节点。首轮固定候选 `ea3b17307d067163c576a4f90b640366f98ef151`；首轮 [115 项对照](agents-restructure-2026-11-08.md)与[451 条引用原文](agents-restructure-2026-11-08-references.tsv)继续保留。

## 1. 独立审核与修正

Owner 明确授权 GPT-6-Astra、high 子 agent 独审后再有限去重。审核 agent `/root/agents_independent_review` 在只读 detached worktree `/home/dev/gdds-agents-independent-review-20261108` 审固定 `ea3b17307d`，未改候选、未运行测试或节点操作；报告见 [独立审核](agents-restructure-2026-11-08-independent-review.md)。报告原件 SHA256 `3c5036c95e71ebceed60edc5ddb09386d1343c27b9fdc405ced2419512c885a9`，入库副本保持原字节。

初审结论为暂不接受：115 项原规则均保留，451 条引用原文一致，但新增前端条文有一项阻塞 F1，另有非阻塞 N1。

| Finding | 初版问题 | 本轮修正 |
| --- | --- | --- |
| F1（P2） | T 初版第 487 行把所有镜像 config digest/全部 DiffID 写成每次运行日志义务，违背 FE3 kickoff §4.3 和原审核 N5 的比例化限制 | 恢复工具链沿 FD7；依赖/RS/backend/worker 每次运行记本机 ID、相应 tag/labels、依赖全部 Layers、Docker/Compose 版本；config digest/全 DiffID 在跨节点传输时比较并写 handoff，不要求每次 save 依赖镜像；链接 kickoff §4.3 |
| F1 关联记录 | 首轮对照与 R443 笼统标记为保留，未发现冲突 | 首轮报告对应行、R443 核对结果注明 finding 和修正去向；451 条原引用文字不改 |
| N1（P3） | T 状态行称“三处澄清”，实际 Q1–Q5 五类 | 改为“相关措辞按 owner 确认澄清” |

这是恢复既有要求，不修改脚本、历史日志或测量数字，也不增加取证义务。

## 2. 有限去重逐项去向

A = [AGENTS](../../../../../AGENTS.md)；T = [testing-conventions](../../../testing-conventions.md)。原位置行号均绑定 `ea3b17307d`。以下补充首轮对照表，未列出的原规则保持。

| 原位置 | 整理内容 | 新位置与必须保留的约束 |
| --- | --- | --- |
| A 37–38 | 节点 IP、容量、扩容日期 | T“执行入口”原有节点说明；A 保留 SSH 别名/用途、共享宿主边界及 worker 设置 |
| A 41 / T 29 | S2b E 一次性 06 t1–t3 授权 | 原文移至 T“历史基线 → 历史阶段说明”；A 一次性用途链接同步指向该节，未扩大节点常设用途 |
| A 226–227 | mypy 增量缓存约 1.5 秒 | T“历史基线 → G11 与静态检查历史观测”标明原 A 提交来源；A 五包 Ruff/mypy、RS strict/tests、禁止省略、命令及 Rust 要求保留 |
| T 61–68 / 215–219 | 两遍批次定义与其历史基线混排、定义重复 | 完整批次定义集中 T“测试批次与 focused 运行”；G11 计数、时长、原提交与 handoff 原文移至历史基线 |
| T 215–239 | 三小包/并行例外/worker 说明 | 新批次小节保留两遍精确 marker、serial 固定 0、三小包单进程、Rust 首包且自行并行、默认 auto、06/07 设置、parallel_safe 隔离条件及既有四项清单 |
| T 367–376 | uv 实际环境摘要与 pycache 排除仅在重复段中 | 先完整移到 T“Hypothesis 隔离与按包闭包沿用”，再去除镜像等价重复段；实际 venv 内容与三种派生缓存排除均保留 |
| T 143–145 / 367–376 | Hypothesis 生命周期与包/Compose 输入重复 | 以 Hypothesis 小节为完整定义，保留固定路径、TMPDIR fallback、打印、前后/中断清理、同包两遍共用、focused 区别；carried 同来源路径且不存在，闭包变化重跑 |
| T 351–362 | 镜像等价第 3 条再次展开闭包输入 | 改为引用闭包主段，仍保留最终 HEAD、同节点同 worktree、RS labels、backend compare、containerd 重建 ID 说明、禁止换 WT 判等价或不等价、exit 合入后才清理 WT |
| T 367–376 / 179–183 | 包沿用与镜像等价关系重复 | 完整关系只在闭包主段；镜像等价节明确引用且要求阶段绑定仍满足本节全部条件。合格来源、包沿用包含同次 Compose、V..H 分别判定均保留 |
| T 187–214 | uv wrapper/no-sync/五锁说明重复 | 完整规则集中“内网构建环境变量”开头；保留 no-sync 先只读检查、不得自动 sync 替换待验证 wheel、前后五锁/漂移拒绝/不 restore、canonical owner 与命令示例 |
| T 258/270 | P2 阶段段落仍写“当前延期” | 保留原标题、命令、inventory 和退出条件，仅标明历史阶段及“当时延期”，不改历史规则 |

本轮不继续改五包静态适用范围、DC68、占用与审批规则，不重开 runner 行为或历史治理机制。原 A 全部二/三级标题、T 现有标题均保留；T 只新增批次与历史说明小节。有限去重重在让机制有一个完整定义，不以行数要求删除规则。

## 3. 检查与资源边界

- 在开始编辑前，2026-11-08 06:21:45–46Z 对 04/05/CT108/06/07 分别 BatchMode `echo OK` 后只读查询，五节点均无 `/home/dev/gdds-node-busy.d`；未启动测试、Compose 或计时任务，未获取/删除节点标记。
- 编辑前重新保存 `git grep -n AGENTS`，912 处（包括首轮引用清单与对照报告自身新增引用），文件在 CT201 `/home/dev/gdds-agents-restructure-20261108/references-before-round2.txt`。首轮 451 条原引用文字继续保持；现有标题/文字入口和新增链接按本轮候选核对。
- 只运行本地文档内容、链接、标题与 `git diff --check` 检查。上一轮基线代码静态失败及 owner 允许本次纯文档提交的 Q6 继续如实记录；未重跑产品检查，不报告当前代码五包通过。独审亦明确本次文字修正无需产品测试或镜像构建。
- 本轮改动不涉及产品、测试、依赖、部署或容器边界，不触发重建；未读取或验证 image revision/source-tree，不宣称 passed/carried，不新增延期门禁。并行产品会话的改动不属于本轮提交或结论。

## 4. 接受与后续

同一独审 agent 在新的只读 detached worktree `/home/dev/gdds-agents-rereview-20261108` 对固定候选 `f08f596c0f792c1fa25c5ed7985585465023147c` 完成定向复核：F1/N1 均关闭，上述各组迁移保留原约束，无新增 finding，接受本轮治理候选。报告见[独立定向复核](agents-restructure-2026-11-08-independent-rereview.md)，原件及入库副本 SHA256 均为 `00387fb690395441e9078b33714adc65a2e322c79f26c387767a93b425d0ae35`；既有初审报告保持原字节和当时结论。独审未运行产品测试或节点操作，结论仅覆盖本轮治理文件，不覆盖并行产品提交。

本次后续提交只归档复核报告并更新本交接状态，不修改规则正文。独审通过后交 owner 确认，推送和三个节点 main 的 fast-forward 仍须后续明确授权；不切换任何在用 worktree。

本轮文档自检：A 原 12 个标题、T 原 30 个标题按原序保留；48 个本地链接有效；451 条引用原文不变，核对结果仅更新 R443；uv 排除项/no-sync 限制/G11 数值/S2b E 原文均保留且完整定义去重；`git diff --check` 通过。记录：CT201 `/home/dev/gdds-agents-restructure-20261108/document-check-round2.log`，SHA256 `664c24817736270161fff7851bf2ef9dc8ef03c4736a759a6d2ef422fe7808f3`。A 12,813 → 12,733 字符（仍 240 行），T 33,849 → 33,394 字符（651 → 650 行）；迁移历史说明、增加精确链接与修正 F1 均计入净值，不以压行数替代结构改善。
