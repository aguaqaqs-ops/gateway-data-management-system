# BE-b 实施与验收执行计划

日期：2026-11-10；2026-11-11 补齐 FE-BEB-11–13 与正式实施授权。状态：**设计开工条件已满足；授权新实施会话连续完成 B0–B5，产品验证与 exit 尚待执行**。

设计依据：[BE-b 第二步设计](be-b-second-step-design.md)，业务依据[第一步](../../../../frontend-vnext/be-b-navigation-and-presentation-draft.md)、[FE4 kickoff §4](../../../../frontend-vnext/fe4-kickoff.md)。产品起点 B=`42780a12303c8040526bf5dc8f9c6f0acb12dbb1`，`p7-s1a-exit` 已完成。BE-b 不等待 S1b；FE4b 等 BE-b exit 与自己的 FE4a exit。

## 1. 开工条件与本轮交付

前端 `b61cc37d5f` 窄复核为 GO_WITH_NONBLOCKING，FE-BEB-01–10 全 CLOSED；报告 `/home/dev/gdds-stage-exchange/be-b/reviews/frontend-targeted-rereview-b61cc37d5f.md`，SHA256 `45fff18109b2594ca494b060379e869b893c246e3ee79769da23e9914cdb8845`。FE-BEB-11–13 已补入第二步 §4.1/4.2/§8 与第一步；前端原审明确无需再轮核对。后端 `b61cc37d5f` 原审 GO 原件同目录 `b61cc37d5f-backend-final.md`，后续文字补足的后端窄核记录在阶段日志。

Owner 2026-11-11 最新指令：“我将在新会话中按照约定的分工角色/模型进行代码实现，授权直接推进完成整个 BE-b，除非遇到阻塞问题等待我确认。”此授权覆盖完整 B0–B5、下述 §5 既定最小真实范围、必要专用节点 focused/静态/容器/门禁、修复与原审复审、最终交付及满足 §6 后的本地 `be-b-exit`。不再逐包、逐次正常验证或退出前重复申请；不包含 push/上线、FE4b 产品实现、S1b/BE-c 或扩大性能目标。

开工条件已满足：后端设计无未关闭阻塞；前端消费形状与摘要责任已确认；Owner 已给完整实施授权。当前设计会话只完成文档和新会话 prompt，不提前修改产品；新会话从 B0 开始直接执行。节点现场、缓存、t4 确切输入/已建节点清单须在相应执行前核实并登记，不把静态设计审核称为这些运行前提已通过。

只有无法在既定方案内解决的业务/Contract 冲突、需改变资源/验收范围、缺失且无法取得的权威输入、不可逆操作或指定模型不可用等实质阻塞才交 Owner。常规命名、实现路径、池内合格节点选择、可逆修复/获准缓存准备由协调者推进。过程原件放 `/home/dev/gdds-stage-exchange/be-b/`；设计/Contract/正式决定与最终一页总结入库。

## 2. 工作包与风险

一个持续协调者安排提交、风险和最终门禁；每包新实施上下文，内聚小包可合并。A/B 类逐包独审，C/D 由实施者与门禁，阶段末新上下文全范围独审。独审与实施者不同模型家族；按 P7-D26/D27 及 S1a C 起实际安排沿用下表，不恢复 A/B 旧三角色。取消专职测试者，focused 由实施者在合格节点运行。

| 角色 | 模型/强度 | 边界 |
| --- | --- | --- |
| 持续协调者 | `gpt-6.1-terra` / high | 主会话由 Owner 选模型；核基线/授权、分包/风险、触发门禁、维护日志、交付/退出，不冒充独审 |
| 每包实施者 | `gpt-6.1-sol` / high | 新上下文，产品/Contract/测试源码、focused、普通修复和本人资源收尾 |
| A/B 包独审与阶段全范围独审 | `gpt-6-astra` / xhigh（复杂判断可 max） | 新上下文、只读 clean detached 候选；同 finding 原审持续复审；阶段全范围另开新审核上下文 |

来源：P7-D26/D27、S1a 执行方案 §4.1 的协调/实施模型，以及 `/home/dev/gdds-stage-exchange/p7-s1a/log.md` C 起 Sol 实施/Astra 独审的新流程；本阶段沿用当前已启用组合。子 agent 显式模型/强度并 `fork_turns="none"`，任务单绑定候选、路径、依赖和允许写入范围。模型不可用不静默替换。内聚包可合并，但不得由实施者自审；最多四个活跃角色含协调者，不递归扩队。不启动专职 Luna 测试角色。

| 包 | 改动与产物 | 风险/审核 | 完成判据 |
| --- | --- | --- | --- |
| B0 基线/Contract 落地 | 核 B..实际 main 增量；消费者与版本矩阵；同步正式目标 Contract 与第一步修订；确认前端反馈 | A 边界设计独审 | 字段、摘要、payload、测试 owner 无待猜决策；不单独提前发布空 Contract 版本 |
| B1 注释与历史绑定 | Rust COMMENT、adapter、测试 Python oracle；presentation 与 manifest；Preview/PrepareImport/Submission/History frozen 链 | A，逐包独审 | 注释不影响业务身份/no-op；历史精确 ref、raw 完整性、重启可读；不污染 canonical/export cache |
| B2 导航与列展示 | 业务规则 registry、双侧过滤、分组认领、replacement、计数/风险归属、导航诊断 | C；若改 comparison 内聚合公共边界按实际升 B | 第一步全部规则有参数化覆盖；table_scope 与局部事实分离，空表结构/风险可达；线性扫描、有界状态；未发布 records 不被当成无变化 |
| B3 最终表/定位/surface | 双侧浏览表、native shared row encoder、最终 Parquet locator、Surface v4 内容绑定与 ref 重写 | A/B：surface 摘要与 READY 引用，逐包独审 | 有快照侧定位完整；行序测试；closure/integrity 和保护不遗漏；后端 surface golden 与前端 loader/ref/closure 一致性；缺快照侧筛选可达 |
| B4 flow/诊断/互通 | pair/view ID、稳定 code、Preview/History 全部接线、真实 fixture 入口、文档替换与错误路径 | B，逐包独审；可与 B3 合并 | 无旧 ID/自由文本 emit；完整七项前端交付草稿；没有 native 重复调用伪差分 |
| B5 集中验收/退出 | 固定 V、受影响权威包+容器、最小真实范围、全范围独审、交付与一页总结 | 阶段全范围新独审 | 当前 H 的证据闭合，无未决阻塞；前端设计核对完成；按本次授权满足 §6 后本地 exit |

建议 B1→B2→B3→B4 顺序实施，必要可合并 B3/B4；不为早交付把业务范围拆成多个对外 Contract/golden 版本。中间提交可有明确 deferred 集成项，但已发现正确性问题不得以延期关闭。每包 handoff 写交接区追加日志，不新建入库审核墙。

## 3. 源码边界与阶段检查

预期改动 `vnext/rust/gateway-compute-core`/Python extension、backend capabilities/application/infrastructure、相关 tests/fixtures、`vnext/scripts` fixture 入口和 owning docs。shared_kernel 算法保持；repository_service 不增加 COMMENT 或导航逻辑。若实际修改共享契约/消费者，纳入相应包，不能因“预期只后端”漏测。

`frontend/` 产品接入、占位 fixture 删除、浏览器 row identity 删除与截图属于 FE4b，不由 BE-b 静默修改。BE-b 提供后端 surface golden、既有 bundle/closure 跨语言向量与生成输出，不要求浏览器重算 surface_digest，前端设计 owner 确认怎样刷新既有 fixture 路径。

B0 必须将 FE-BEB-11–13 的导航必有/退役清单、无记录行的完整性及 suppressed 计数前提、同侧整数 UTF8 typed decode 与逐侧诊断落入 Contract；B2 对 registry/实际比较资格做断言，B4 给反例 fixture。不能将本轮文字关闭当作产品测试已覆盖。

B1 验证重点：native 与独立 oracle；manifest raw/semantic 分离；no-op 无副作用；PrepareImport 冻结/恢复。B2 以纯 contract 单元测试为主，不建 Dolt。B3 覆盖实际 Parquet、export cache、shared、mixed root 下载/保护；B4 最小 Preview/History/replacement 接线。测试同构输入用共享参数表，timing 测试 serial，每个不变量仅一个 owner。

代码提交执行现行 AGENTS 要求的 Python ruff/mypy、受影响 focused 与 Rust fmt/clippy；均在专用节点，不在 CT201。Rust 修改后 backend focused 强制重装扩展并校验 build input。不要在每个包跑完整 runner/Compose/完整真实旅程；集中在 B5。

## 4. 节点、门禁和镜像

当前流程以 main AGENTS 的 DC91/DC97/P7-D25–D27 为准，不照搬旧节点用途：focused/真实数据在五节点池合格空闲节点原子占用，初始 pytest/Cargo jobs=4。自动阶段门禁固定 04 的既有 worktree，命中/不命中由脚本判定；04 忙等待，不把旧 carried 迁往别节点。

代码、缓存/依赖镜像经获准 LAN；UV_OFFLINE=1、CARGO_NET_OFFLINE=true、预置 dependency-base、本机 Compose 离线构建；依赖输入不变不重建 dependency-base。无公网/转发代理取证。默认产品 N1/M24/E32/reserve8、单 worker；测试 worker 数与产品 N 分开。

最终 V 使用 `scripts/run-stage-gate.py <完整SHA> --packages <实际受影响包> --purpose stage`；准确 flags/现场配置以 `scripts/README.md` 与工具为准。预期 rust、backend 必跑；repository_service 等根据实际闭包判定。阶段不是项目最终/发布，不预设每次六包 fresh。最后 H 若只加文档，仍让脚本按同节点同树的实际闭包决定；prepared manifest 不冒充 actual runner manifest，整次失败不收录部分通过。

本阶段增加 bundle/decoder/产物与 native 行路径，B5 重建当前候选并跑受影响 backend 容器旅程。同次 runner 已含的 Compose 不额外再跑。中间容器项只要不阻断后续正确接线可 deferred。每轮记录当前 HEAD、重建触发/延期理由、最后 image revision/source-tree 和最终来源，不把 B/S1a 的镜像称为 BE-b 通过。

runner 失败停止该次及依赖验收；保留原件。明确命令/缓存/环境错误按当前快速修复规则，无盲重试/次数触发的无谓审批；产品失败回实现/原审/必要复验，不能归为环境故障。

## 5. 真实数据与成本边界（本轮完整实施授权内的既定范围）

BE-b 变化集中 Preview/History 及提交保存展示元数据；本次完整实施授权按现有计划执行一次集中最小链：

| 数据 | 目的与范围 | 不作何种宣称 |
| --- | --- | --- |
| 标准 t1 v1/v2 | 一次上传/Preview→Submit/Review/Archive 建立两个真实版本；覆盖 MODIFIED_ONLY、一次 FULL 的两个 pair、History 两/三节点，校验真实分组/列/定位/闭包；复用同一建立过程，不重复全旅程 | 不重做 P6 全性能矩阵，不与新 FE4b t1 截图混为同一次后端运行 |
| t4 已有标准输入 | 一次有界 Preview + History 代表性大表导航/定位/完整 bundle 校验；若 History 缺节点，只建立这次验证所需最少节点，准备成本计入；报告扫描量、产物体积、内存及时间 | 不自动运行 t4 完整 Submit/Archive/所有 W/H 多次采样，不重跑正式性能基准 |
| 小型确定性输入 | gid/地址变化、重复/孤儿、replacement、仅注释变化、改前公式（t1 composite_changed=0）、keyless duplicate | 由 focused/contract/fixture 覆盖，不扩成新的真实数据档位 |

t4 具体版本/两侧和节点库存须实施 kickoff 核清并列清单；不能写“沿用旧 t4 导航正确性”（旧版本未实现导航）。若资源/时间无法覆盖，向 Owner 提交实际影响与替代范围，未确认不自行删减、也不无限扩大。性能只报告；正确性、资源硬界、输入/提交来源仍是门槛。前端 FE4b 按自己的计划在 t1 做两种宽度正式截图，不重复 t4 导航后端验证。

## 6. FE4b 交付与退出条件

- [ ] 第一阶段已确认范围全部实现，包括双侧公式、行定位、ID、稳定诊断；第一步修订与前端定向反馈关闭。
- [ ] 新 Contract/selector、全部 decoder/producer、ref traverse/rewrite、保护/恢复/清理同步；无旧格式兼容路径。
- [ ] 注释不改变规范业务身份、no-op 无历史覆盖；DDL 标识符和 canonical/export 缓存不被展示字段污染。
- [ ] 表内容 binding 与物理 ref 分离的后端 v4 golden、locator 重排不变性、前端 ref/closure 校验与新形状协议已固定。
- [ ] 新 candidate 的受影响权威包/容器和已确认真实范围有证据，无产品失败未处理；模型独立的阶段全范围审核通过。
- [ ] 交付正式 Contract、五类 golden、fixture 入口/固定输入与输出、生产 OpenAPI、稳定码全集、main/vnext tree/镜像身份；按 FE4 §4 分开解释 S1a 与 BE-b 的全部变化。
- [ ] 阶段日志引用原始日志/机器 result/SHA、失败与限制，不把未知填为通过；本人临时资源收尾，保留仍被消费者引用的 evidence/carried 工作区。

满足后在 main 可达最终 H 依本次授权创建附注 `be-b-exit`，绑定 V/H/全范围独审/证据与限制，无需再次申请本地退出；设计准备会话不预打 tag。提交一页阶段总结；FE4b 另行接入、取证与退出，不能把 BE-b exit 写成整个 FE4 已完成。不 push、不部署。

## 7. 前端核对闭环与实施交接

原提示词 `prompts/frontend-targeted-review.md` 与 `prompts/frontend-targeted-rereview.md`、两轮前端报告和后端原审报告均在阶段交接目录保留。前端原审已确认双侧筛选、表级/局部事实、replacement、列并集、五列 locator、摘要责任与 fixture 可消费；无需再转交一轮相同设计。

下表为设计关闭与实施责任映射，B0/B4 同步 owning Contract/交付时逐项落实。新的实质消费者形状变化才回到设计/前端针对性核对，不为文字或命令修正重复流程。

| Finding | 目标落点与实施责任 |
| --- | --- |
| FE-BEB-01 | 设计 §4.1/4.2：table_scope、空表变化/风险保留、无装置时整表入口；Owner 已同意 sg_cfg 补充，B2 覆盖 |
| FE-BEB-02 | §4.4：columns 并集/present_in，before-only 展示字段；B3 与前端列渲染 |
| FE-BEB-03 | §4.1：不增加公开账本；前端取消有导航时自动补其他表，按侧集合覆盖；FE4 owner 同步 kickoff §5.3 |
| FE-BEB-04 | §6/8 与 B3：不要求浏览器 surface_digest；后端 golden + 前端 ref/closure 一致性 |
| FE-BEB-05 | §4.4：补两个稳定码；两个 pair 失败/取消原文不进 surface，B4 给完整 emit 表 |
| FE-BEB-06 | §4.2：每表一条事实不可用诊断，首版统一该表 fallback；B2 |
| FE-BEB-07 | §5.1：有逻辑 before 的双侧浏览表必须绑定；未变别名 current，新增侧 null；B3 |
| FE-BEB-08 | §4.2/5.2：安全整数/typed 比较、整表降级、locator 两个上下文字段；不修改 records；前端已确认新形状，B2/B3 实施 |
| FE-BEB-09 | §4.1/4.3：projection 单一、五组/分侧不变量、side 键空间与诊断；B2/B4 |
| FE-BEB-10 | §8：后端输入与 SHA 清单、完整调用及输出映射；B4，前端 wrapper 删除私有导入/手写占位 |
| FE-BEB-11 | §1/4.1/8 与第一步：导航缺失/重复拒绝、退役 B9/fallbackNavigation/preview-no-navigation，目标目录及根 manifest/closure 清单；B0/B4 关闭产品落点，FE4b 删除旧前端路径 |
| FE-BEB-12 | §4.2：无记录行双侧身份复用须实际比较资格、完整 records/locator、无 suppressed 增删；未知时不造 before；B0/B2/B4，增加 gid变化+未改cfg 和抑制新增反例 |
| FE-BEB-13 | §4.2：规范类型→JSON→真实 Parquet 物理映射；同侧 metadata 严格 typed decode，不改整数UTF8导出；逐受影响侧诊断；B0/B2/B4 |

FE4 kickoff §3.1 B1/B4/B6/B7/B9、§5.3 判据/fixture/截图分工及 §2.3/§4 来源记录由前端设计 owner 在 FE4b 正常设计中同步，包括 B9 退役及无 display_order 旧分支删除；不另阻塞 BE-b 后端开工。BE-b 交付列明这些消费者改动，不静默修改前端产品或代签 FE4b 验收。

新会话入口：`/home/dev/gdds-stage-exchange/be-b/prompts/be-b-implementation.md`，绑定准备提交/文件摘要、授权、角色和退出清单。协调者开工先核该提交在 main 可达、实际 HEAD 增量及工作区归属，保护他人未提交修改；不从任意旧 FE 工作区直接继续。
