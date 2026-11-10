# P7-S1a：A–G 完整实施至本地 exit 提示词

新会话请选择 **GPT-6.1 Terra / high**，将下方正文作为任务指令。本文件记录 Owner 于 2026-11-10 已给出的下一会话授权；当前设计会话只准备文档，不启动实现或测试。

---

你是本项目 P7-S1a 的持续协调者，使用 `gpt-6.1-terra` / high。我已确认阶段安排，现在授权你按仓库实际设计与执行方案完整推进 **S1a A→B→C→D→E→F→G，直到 S1a 正式本地 exit**。不要停在计划、创建角色、某包完成或建议继续。正常实现、必要验证、普通修复复审和满足条件后的本地退出无需逐次确认；只有真实阻塞才暂停受影响工作，说明证据、影响、选项与推荐，等待我的明确回复。无回复不视为批准，可以继续不依赖该决定的工作。

## 1. 授权与范围

授权 S1a 范围内产品/工具/owning Contract/测试/文档更新、必要唯一基线 schema 修改、删除被替代路径、本地 main 提交、独立审核、必要 focused/静态/编译/集成/容器验证、离线依赖和镜像准备、按确认范围的真实输入验证、修复复审、报告/handoff，以及条件满足后的本地附注 `p7-s1a-exit`。没有兼容、迁移、双读/双写、旧字段别名或历史数据回填要求。

S1a 只完成单处理组单 worker 的多 root 存储、跨盘发布、实际消费者、保护/清理、挂载失败和资源配置闭环，提供 S1b 所需的环境/组归属与窄观测接点。**不实现 S1b 统计产品、S2 多 worker/多组、S3 调度或 S4 抽取工具，不 push、不上线、不改 P6 验收，不操作其他会话或冻结资源。** 测试节点上的必要临时 Compose 验证属于已授权测试；生产/试运行部署不在授权内。

已确认的后续安排为：S1b 统计；S2a 组内多 worker；S2b 同机独立组/静态目录；S3 组内公平与整机预算；S4a 外部映射/有序回灌；S4b 全设备状态抽取/独立测试加载及受控生产换组；S5 综合验收。抽取默认包含设备全部现存历史、审核、终态和未完成任务及必要依赖，无历史子集选择器、无回合并。不要重新询问这些边界，也不要提前实现它们。

## 2. 先核工作区与实际输入

先只读核 branch、HEAD、index/tracked/untracked、worktrees、相关 tags 和并行写入。设计交接时 `/home/dev/gateway-data-management-system` 在 FE 分支 `fe3b-evidence-04`，HEAD `a300b16485bcad2f178aaccfe0c8adbb51b5ab83`，早于 P6 exit，不能直接作为产品起点。实际 main 曾在 `/home/dev/gdds-s5-design-main`，这只是查找线索，不代替现场核对。

P6 已正式退出：附注 `p6-exit` 指向 **`b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`（B）**，`vnext` tree=`49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。实际实现起点须为 main 上 B 的后继，记录 B..起点的消费者变化，不回退后续提交、不在 FE 工作区切分支。正常使用 main；确需隔离并行工作才建短期分支/独立 checkout，尽快合回，不改写已审核或取证引用提交。

以下 **七份 P7 文件最初均在原工作区，尚未提交**。先读取那里实际全文，再核 main 是否已有后续同名版本；有并行编辑先比较归属/语义，不能盲目覆盖。新设计内记录的三份 S0 SHA 是首次读取时历史输入摘要，不是当前版本校验值。将本任务七份文档显式纳入可引用的本地提交；不得混入 `fe3c-review.md`、architecture/implementation-stages 或其他会话改动，不使用 `git add .`。

完整读取：

1. 实际工作区及实现 main 适用的 `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`；按当前 Owner 指令和适用现行规则执行，不复制旧阶段临时许可。
2. `docs/backend-vnext/refactoring/formal/plans/p7-s0-owner-decisions.md`。
3. 同目录 `p7-design.md`、`p7-execution-plan.md`。
4. 同目录 `p7-s1a-storage-resource-design.md`、`p7-s1a-execution-plan.md`。
5. 同目录 `p7-processing-groups-and-test-extraction-design.md`、本提示词。
6. 比例化保障政策、ADR 0012；按消费者追 owning Storage、Snapshot、Operation、Business、Comparison/Bundle 与 RS Contract 及实际源码。P6 最终证据入口见 S1a 设计 §1，只复核依赖，不重跑/重审整个 P6。

语义不变量由详细设计与 owning Contract 控制，实施细节由 S1a 执行方案控制，本提示词及 Owner 最新指令控制授权和角色。设计尚未独审，不能写 DESIGN_GO；A 的原审先核本轮设计/Contract 与实际 consumer，发现范围内工程缺口由本包修正，改变已确认业务边界才提交 Owner。

## 3. 每包新建三角色

沿用最近 P6-S6 的模型安排，来源为 `p6-exit:docs/backend-vnext/refactoring/formal/plans/p6-s6-implementation-prompt.md` §3；旧工作区缺该文件时用 Git 对象读取。

| 角色 | 模型 | 推理强度 |
| --- | --- | --- |
| 持续协调者 | `gpt-6.1-terra` | high |
| A–G 各包实施者 | `gpt-6.1-sol` | high |
| A–G 各包独立审核者 | `gpt-6.1-sol` | xhigh，复杂事务/证据冲突可 max |
| A–G 各包唯一测试/等待/日志角色 | `gpt-6-luna` | max |

每包分别创建 `s1a_a_impl/review/test` 等三角色，到 G 同理；显式模型/强度，支持时 `fork_turns="none"`，不跨包复用上下文，不一次创建全部 21 个活跃角色。前包核收/资源收尾/交接后再换下一组三角色；最多四个活跃角色含协调者，不递归扩队、不增加监控 agent。同包原审连续负责修复复审，不能换人重置失败次数。

任务输入必须自包含：固定候选/工作区、必读 Contract/设计小节、本包边界、允许写入路径、前包 handoff、未决 finding 和原件索引。协调者记录实际角色 ID/模型/强度和阶段状态，不假称已创建或销毁角色。模型不可用时说明具体阻塞，不静默替换；新会话主模型由会话选择，不假称已热切换。

Sol 实施者写代码/Contract/测试源码/执行稿并定位修复；Sol 原审在 clean readonly detached worktree 核代码/稿/证据，只写独审报告，不实施后代签；Luna 只执行固定已审稿和本人收尾，保原 exit/日志，不修改参数/预算/预期/产品、不擅自重试或换节点、不签 GO。协调者维护授权、依赖、主线串行写入和交接，不代替独审。每包测试角色都建，但 A 等文档包按实际影响做静态核查，不为了角色存在运行无关测试。

## 4. A–G 持续实施

以 S1a 执行方案 §3–6 的完整字段、文件落点、验证矩阵和退出条件为准：

- **A 入口/Contract：**核 B 后变更、全消费者和摘要边界，独核详细设计及 Contract 目标；清楚区分待实现目标与已生效行为。
- **B 配置/位置协议：**统一 typed 两配置、位置 codec、所有 producer/decoder、nominal refs、in-memory 与 golden；耦合变更同逻辑批次闭合，无旧格式 fallback。
- **C backend 发布/读者/保护：**多 root store、目标盘 staging、完整原子发布、跨盘有界 copy、锁序和 protection/cleanup 屏障。
- **D backend 消费者/维护：**上传、canonical、cache、checkpoint、Submit、export/download、scratch 全链与 bounded cleanup；不能只新增几个路径 settings。
- **E RS 分盘：**建库/upload/import/recovery/admin/cleanup、SQLite/HOME/entrypoint 全链；不让 backend 直接挂 RS 卷。
- **F 部署/资源：**配置渲染、实际宿主/container mount/cgroup 预检、同盘/分盘 profile、W=K=1、N/M/E/reserve 和 S1b 窄接点。
- **G 最终收敛/退出：**固定最终候选，受影响包权威/必要容器、按确认范围真实链、整个 S1a 区间独审、handoff、最终绑定及本地附注 tag。

每包完成实际实现、必要 focused、独审/验证、修复复审和 handoff 后自动继续。中间不得保兼容实现来凑 green，不把依赖后续包的断言记 PASS；仅清楚移交未完成项。最终 G 必须关闭全链，不将 RS 分盘、下载、保护/清理或实际容器预算延期至 S1b。所有已确认上限/默认值以设计为准；M 是 kernel 预算，不是 RSS，不能因为 RSS 低就降低 M。运行机具体可用 CPU/内存预算按现场合理配置，长期容量默认值仍由 S5 实证定稿。

## 5. 验证、失败与真实范围

全部测试、lint/mypy、编译、容器及取证只在专用 CT 的 clean 已提交 worktree；开发主机只做代码/文档编辑、只读核查和获准依赖准备。06 focused/Contract/小型 Compose，04 权威 runner/容器/carried，05 默认真实输入调试/适用旅程；不继承 P6 的 06 专项真实运行许可。现场核空闲后原子取得本人所需标志，不反复预约，不操作他人有效占用。

严格按 AGENTS 使用获准 LAN 传输/预填缓存、UV_OFFLINE=1、CARGO_NET_OFFLINE=true、受控 uv、linked worktree legacy link、必要 Rust build-input、离线 dependency-base/本机 Compose build。日志在 worktree 外，绑定 hostname、起止 HEAD/UTC、原 numeric exit 与 SHA256。测试期间不写被测树、不手工重建/retag 参与验证的镜像。跨节点镜像比 config digest 与全部 RootFS DiffID，不比 inspect ID。

调试只 focused，代码提交所需五包 ruff/mypy 与实际受影响 Rust 检查按 AGENTS 执行；各包不重复全量。G 预期 backend/repository_service 权威，实际改到其他包再纳入；不把 S5 六包最终门禁机械搬到 S1a。mount/权限/entrypoint/Compose 边界必须有当前候选相应容器门禁；同盘/真实跨 filesystem、复制中断和缺挂载必须覆盖，不能只 mock EXDEV。空间耗尽只用本人隔离小卷/配额，不填满共享主机。

真实范围提案为：标准 t1 MODIFIED_ONLY 首次及重复输入，上传→Preview→Submit/Review/Archive→完整下载→保护后清理，分盘运行；同盘由同候选容器向量和业务 golden 对照，不扩为 t4/FULL/多设备容量证明。按 DC33，在准备时一次提交具体输入标识、步骤与节点给 Owner 确认，继续其余无依赖工作；未确认前不启动完整真实旅程。该项是具体验收范围确认，不是再次请求 A–G 实施授权。

每次失败先停该次运行和依赖后续验收，保原始日志/SHA、实际触及范围和安全收尾，再由 Sol 分析，范围内修复、原审、按修订稿必要复验。DC68 遵守适用现行规则与 Owner 最新指令，不沿用旧阶段的特殊重试授权；不得无修改重试、换人掩盖次数、改预期或跳身份/缓存前提。原因/副作用不明、规则要求交 Owner、实质语义变更或确需他人资源时报告并等待明确答复。暂时等待时继续独立工作，不回退开发机测试。

## 6. 最终本地退出

1. S1a 执行方案 §6 全部满足；A–F 交接、整个区间独审、所有 finding 与限制有明确结果。设计者自查不替代独审，旧 P6 证据不当作 P7 已测。
2. 固定产品 V、最终绑定 H、每包实际来源及容器 provenance。H 的后续文档增量若沿用 V，必须在同来源节点/同 worktree 实算闭包和镜像等价，不口头 carried、不引用链式沿用。
3. 独审最终 H、必需测试/真实范围、资源释放与限制后，签 **S1a EXIT_GO**。需要避免报告自身提交循环时使用带 SHA256 的外置签署/回执，随后纯文档归档不移动已验 H/tag。
4. 所有条件成立后，按已有授权直接创建本地附注 **`p7-s1a-exit` → H**，记录产品 V、H、原审/证据路径与摘要、范围/限制；核 tag 类型/目标/main 可达。已有同名 tag 完全匹配则报告已有，冲突即停，不覆盖或移动。不建 A–F 或整个 P7 exit tag。
5. 只释放本任务应释放资源，保留被引用成功/失败原件和必要来源 worktree/env/images。交付最终提交/tag、实现/文档位置、实际验证与独审、未测/容量限制、资源释放及 S1b 接口交接。停止于 S1a exit，不 push、不上线、不自动开始 S1b。

现在核实际起点与七份文档，简报基线后创建 A 的全新三角色并开始；有已授权工作即可持续推进，不在包边界等待批准。
