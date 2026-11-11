# BE-b 实施与验收执行计划

日期：2026-11-10；2026-11-11 按 FE-BEB-01–10 修订。状态：**前端反馈修订已获后端原审 GO，待前端窄复核；本轮仅授权文档、后端独审与前端核对准备，尚未授权产品实施**。

设计依据：[BE-b 第二步设计](be-b-second-step-design.md)，业务依据[第一步](../../../../frontend-vnext/be-b-navigation-and-presentation-draft.md)、[FE4 kickoff §4](../../../../frontend-vnext/fe4-kickoff.md)。产品起点 B=`42780a12303c8040526bf5dc8f9c6f0acb12dbb1`，`p7-s1a-exit` 已完成。BE-b 不等待 S1b；FE4b 等 BE-b exit 与自己的 FE4a exit。

## 1. 开工条件与本轮交付

本轮落成设计与计划，由 GPT-6-Astra 在新上下文、clean detached 候选独立审核；同一 finding 原审复审。前端定向核对由 Owner 转交 prompt 后回传，不通过工具代发消息。

编码入口须同时满足：

1. 后端设计独审无未关闭阻塞项。
2. 前端确认双侧集合 row_filter、本侧孤儿判定、TABLE_FALLBACK/table_scope/new code、两侧列并集/present_in、缺快照筛选上下文、replacement_sides/同侧名称、surface v4 内容绑定/摘要及 fixture 可消费；差异同步设计和第一步，未返回不是同意。
3. Owner 明确产品实施范围和本节真实数据范围。当前授权不解释为自动进入编码或打产品 exit tag。

本轮只做文档差异、链接、源码依据核对；不运行产品测试、连接测试节点、构建镜像或修改 Accepted Contract。审核/prompt/log 放 `/home/dev/gdds-stage-exchange/be-b/`，只将设计、正式决定、计划入库。

## 2. 工作包与风险

一个持续协调者安排提交、风险和最终门禁；每包新实施上下文，内聚小包可合并。A/B 类逐包独审，C/D 由实施者与门禁，阶段末新上下文全范围独审。独审与实施者不同模型家族；本轮指定 Astra 仅指设计独审，不替未来实施团队预填模型或审核通过。取消专职测试者，focused 由实施者在合格节点运行。

| 包 | 改动与产物 | 风险/审核 | 完成判据 |
| --- | --- | --- | --- |
| B0 基线/Contract 落地 | 核 B..实际 main 增量；消费者与版本矩阵；同步正式目标 Contract 与第一步修订；确认前端反馈 | A 边界设计独审 | 字段、摘要、payload、测试 owner 无待猜决策；不单独提前发布空 Contract 版本 |
| B1 注释与历史绑定 | Rust COMMENT、adapter、测试 Python oracle；presentation 与 manifest；Preview/PrepareImport/Submission/History frozen 链 | A，逐包独审 | 注释不影响业务身份/no-op；历史精确 ref、raw 完整性、重启可读；不污染 canonical/export cache |
| B2 导航与列展示 | 业务规则 registry、双侧过滤、分组认领、replacement、计数/风险归属、导航诊断 | C；若改 comparison 内聚合公共边界按实际升 B | 第一步全部规则有参数化覆盖；table_scope 与局部事实分离，空表结构/风险可达；线性扫描、有界状态；未发布 records 不被当成无变化 |
| B3 最终表/定位/surface | 双侧浏览表、native shared row encoder、最终 Parquet locator、Surface v4 内容绑定与 ref 重写 | A/B：surface 摘要与 READY 引用，逐包独审 | 有快照侧定位完整；行序测试；closure/integrity 和保护不遗漏；后端 surface golden 与前端 loader/ref/closure 一致性；缺快照侧筛选可达 |
| B4 flow/诊断/互通 | pair/view ID、稳定 code、Preview/History 全部接线、真实 fixture 入口、文档替换与错误路径 | B，逐包独审；可与 B3 合并 | 无旧 ID/自由文本 emit；完整七项前端交付草稿；没有 native 重复调用伪差分 |
| B5 集中验收/退出 | 固定 V、受影响权威包+容器、最小真实范围、全范围独审、交付与一页总结 | 阶段全范围新独审 | 当前 H 的证据闭合，无未决阻塞；前端设计核对完成；Owner 按实施授权决定本地 exit |

建议 B1→B2→B3→B4 顺序实施，必要可合并 B3/B4；不为早交付把业务范围拆成多个对外 Contract/golden 版本。中间提交可有明确 deferred 集成项，但已发现正确性问题不得以延期关闭。每包 handoff 写交接区追加日志，不新建入库审核墙。

## 3. 源码边界与阶段检查

预期改动 `vnext/rust/gateway-compute-core`/Python extension、backend capabilities/application/infrastructure、相关 tests/fixtures、`vnext/scripts` fixture 入口和 owning docs。shared_kernel 算法保持；repository_service 不增加 COMMENT 或导航逻辑。若实际修改共享契约/消费者，纳入相应包，不能因“预期只后端”漏测。

`frontend/` 产品接入、占位 fixture 删除、浏览器 row identity 删除与截图属于 FE4b，不由 BE-b 静默修改。BE-b 提供后端 surface golden、既有 bundle/closure 跨语言向量与生成输出，不要求浏览器重算 surface_digest，前端设计 owner 确认怎样刷新既有 fixture 路径。

B1 验证重点：native 与独立 oracle；manifest raw/semantic 分离；no-op 无副作用；PrepareImport 冻结/恢复。B2 以纯 contract 单元测试为主，不建 Dolt。B3 覆盖实际 Parquet、export cache、shared、mixed root 下载/保护；B4 最小 Preview/History/replacement 接线。测试同构输入用共享参数表，timing 测试 serial，每个不变量仅一个 owner。

代码提交执行现行 AGENTS 要求的 Python ruff/mypy、受影响 focused 与 Rust fmt/clippy；均在专用节点，不在 CT201。Rust 修改后 backend focused 强制重装扩展并校验 build input。不要在每个包跑完整 runner/Compose/完整真实旅程；集中在 B5。

## 4. 节点、门禁和镜像

当前流程以 main AGENTS 的 DC91/DC97/P7-D25–D27 为准，不照搬旧节点用途：focused/真实数据在五节点池合格空闲节点原子占用，初始 pytest/Cargo jobs=4。自动阶段门禁固定 04 的既有 worktree，命中/不命中由脚本判定；04 忙等待，不把旧 carried 迁往别节点。

代码、缓存/依赖镜像经获准 LAN；UV_OFFLINE=1、CARGO_NET_OFFLINE=true、预置 dependency-base、本机 Compose 离线构建；依赖输入不变不重建 dependency-base。无公网/转发代理取证。默认产品 N1/M24/E32/reserve8、单 worker；测试 worker 数与产品 N 分开。

最终 V 使用 `scripts/run-stage-gate.py <完整SHA> --packages <实际受影响包> --purpose stage`；准确 flags/现场配置以 `scripts/README.md` 与工具为准。预期 rust、backend 必跑；repository_service 等根据实际闭包判定。阶段不是项目最终/发布，不预设每次六包 fresh。最后 H 若只加文档，仍让脚本按同节点同树的实际闭包决定；prepared manifest 不冒充 actual runner manifest，整次失败不收录部分通过。

本阶段增加 bundle/decoder/产物与 native 行路径，B5 重建当前候选并跑受影响 backend 容器旅程。同次 runner 已含的 Compose 不额外再跑。中间容器项只要不阻断后续正确接线可 deferred。每轮记录当前 HEAD、重建触发/延期理由、最后 image revision/source-tree 和最终来源，不把 B/S1a 的镜像称为 BE-b 通过。

runner 失败停止该次及依赖验收；保留原件。明确命令/缓存/环境错误按当前快速修复规则，无盲重试/次数触发的无谓审批；产品失败回实现/原审/必要复验，不能归为环境故障。

## 5. 真实数据与成本边界（建议范围，待 Owner 确认）

BE-b 变化集中 Preview/History 及提交保存展示元数据；建议一次集中最小链：

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

满足后在 main 可达最终 H 按 Owner 的产品实施/退出授权创建附注 `be-b-exit`，绑定 V/H/全范围独审/证据与限制；本轮不创建。提交一页阶段总结；FE4b 另行接入、取证与退出，不能把 BE-b exit 写成整个 FE4 已完成。不 push、不部署。

## 7. 前端定向核对请求

原提示词位于 `/home/dev/gdds-stage-exchange/be-b/prompts/frontend-targeted-review.md`，本次窄复核提示词位于同目录 `frontend-targeted-rereview.md`，审核时绑定不可变文档候选 SHA；后端独审在 `/home/dev/gdds-stage-exchange/be-b/reviews/`。反馈至少回答：双侧集合筛选可实现且不会把缺侧当全表/漏多 gid；本侧孤儿有入口；TABLE_FALLBACK 正确保留整表风险；replacement 分侧键/标题与诊断定位明确；后端 v4 golden 与前端 loader/closure 分工明确；原始 DDL 名与展示名分离满足浏览器需求；golden/fixture/七项交付足以刷新 FE4b。

返回 GO/GO_WITH_NONBLOCKING/CHANGES_REQUIRED，并列逐项文件段落、具体反例和建议；不要求前端现在实施/跑真实数据，也不让其代审后端存储/事务。前端意见回传后由后端设计者修订，实质后端变更交原 Astra 独审复核；再向 Owner报告可实施状态与剩余范围确认。

本次反馈修订映射（均为设计落点，关闭以原审/前端复核为准）：

| Finding | 目标落点与实施责任 |
| --- | --- |
| FE-BEB-01 | 设计 §4.1/4.2：table_scope、空表变化/风险保留、无装置时整表入口；Owner 已同意 sg_cfg 补充，B2 覆盖 |
| FE-BEB-02 | §4.4：columns 并集/present_in，before-only 展示字段；B3 与前端列渲染 |
| FE-BEB-03 | §4.1：不增加公开账本；前端取消有导航时自动补其他表，按侧集合覆盖；FE4 owner 同步 kickoff §5.3 |
| FE-BEB-04 | §6/8 与 B3：不要求浏览器 surface_digest；后端 golden + 前端 ref/closure 一致性 |
| FE-BEB-05 | §4.4：补两个稳定码；两个 pair 失败/取消原文不进 surface，B4 给完整 emit 表 |
| FE-BEB-06 | §4.2：每表一条事实不可用诊断，首版统一该表 fallback；B2 |
| FE-BEB-07 | §5.1：有逻辑 before 的双侧浏览表必须绑定；未变别名 current，新增侧 null；B3 |
| FE-BEB-08 | §4.2/5.2：安全整数/typed 比较、整表降级、locator 两个上下文字段；不修改 records；B2/B3，须前端核新形状 |
| FE-BEB-09 | §4.1/4.3：projection 单一、五组/分侧不变量、side 键空间与诊断；B2/B4 |
| FE-BEB-10 | §8：后端输入与 SHA 清单、完整调用及输出映射；B4，前端 wrapper 删除私有导入/手写占位 |

FE4 kickoff §3.1 B1/B4/B6/B7/B9、§5.3 判据/fixture/截图分工及 §2.3/§4 来源记录由前端设计 owner 在窄复核后同步；本轮不修改前端产品代码或代签前端结论。
