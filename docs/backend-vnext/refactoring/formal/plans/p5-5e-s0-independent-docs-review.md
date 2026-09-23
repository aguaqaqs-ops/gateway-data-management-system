# P5-5E-S0 Independent Docs Review

日期：2026-09-21。审核对象：History Compare 三份 candidate 设计及执行计划。

## 1. 总结论

**定向修订。当前版本不通过文档审核。**

核心模型成立：History 从 Backend 权威业务事实派生，覆盖全部成功 Submission，业务父边与技术 parent 分离；Compare 绑定授权业务节点的 exact commit，使用既有 HISTORY pair 语义、只读 Repository 数据面和 durable Operation。三节点映射相邻双 pair、同 commit 多业务身份、短事务外物化均有可用公共接口支持。不因 5D/5E 尚未实现而否决 docs-only 设计。

阻塞项集中于比较 policy 的实际输入、CommitId 类型、HTTP 公共面接线、确定性身份编码、integrity Contract 对齐及实施门禁。可在既有 Application/adapter 分工和 S1–S4 主路径内修正，无须重建业务树或替换 Operation 架构，故不建议整体返工。

本文仅给独立审核结论，不修改 candidate 状态，不接受或升级上游 Contract，不授权实现、提交、推送、部署，不签署 5E/P5 exit。

## 2. 固定版本、范围及隔离

入场与报告写入前分别检查了 HEAD/status：

| 工作区 | 分支 | HEAD | 入场状态及用途 |
| --- | --- | --- | --- |
| `/home/dev/gateway-data-management-system` | `phase1/gate-ownership-repair` | `d19b3efcab42d54523b94146d7a4d687823b5b86` | clean；只在这里新增本报告 |
| `/home/dev/gdds-5e-history-compare-docs` | `p5-5e-history-compare-docs` | `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c` | 仅下列三份 untracked candidate；全部源码/测试/Contract 审核在此固定基线进行 |

主目录没有完整 candidate，故定位独立 worktree，未把主目录旧文档或并行实现当作本轮输入。作者声明的起点与实际 worktree HEAD 一致，无需改回其他提交。只读查看两 HEAD 的 diff stat 确认并行变更涉及 5D baseline/migration/initial-empty；没有用这些新源码证明 candidate 的 E 声明或 5D 已验收。

三份文件作为整体审核；该 worktree 无其他 tracked diff、无其他作者新增文件。审核开始及结束前摘要相同：

| 文件（均位于 candidate worktree 的 `docs/backend-vnext/refactoring/formal/plans/`） | 行数 | SHA-256 |
| --- | ---: | --- |
| `p5-5e-s0-entry-brief.md` | 138 | `b1b02044bf4cb120772dd8db4d03343aeda6e99354e8138e46a2b5ce8512f604` |
| `p5-5e-history-compare-design.md` | 402 | `e6f5a86d456dfddf16c285a9b158b83212aebde72b3579912ebd762b6906469d` |
| `p5-5e-history-compare-execution-plan.md` | 236 | `d2f876b9789d64ce14875dd039625b5631d612abd422a78e11f54dcfa97753bd` |

下文 **Design / Plan / Entry** 指此摘要固定的文件；**B**=`vnext/backend/src/gateway_backend/`，**T**=`vnext/backend/tests/`；所有源码行号以 `6f6a780415` 为准。主目录新增报告不会把其 HEAD 变成被审代码基线。

已阅读用户指定的 AGENTS、testing-conventions、P5 总纲、implementation-stages、四份 Contract、比例化 policy、5D accepted review/design/execution plan；补读 Repository Service Contract 与 ADR 0012。按真实调用链检查 Comparison/Risk/Surface/Bundle 公共输入与实现、RepositoryRef/HTTP Arrow、Submission/Workspace 身份、control DB、HTTP、preview/checkpoint/worker 注册模式及相关测试。作者临时 `/tmp/verify_history_pair.py` 和“已核查”陈述不作为独立通过证据。

## 3. 实质 findings（按严重程度）

### F1 — P1：宣称 ordered/blank 业务比较，但执行输入没有对应 policy 来源与绑定

**位置：** Design:205–215（§5.3），Design:355（测试 owner）；Plan:78–91、145–151（执行与路径预算）。

**证据：** `B/capabilities/comparison/pair_planning.py:57` 的 `bind_pair_input` 接受 `table_policies`，默认空；`:301–323` 为未提供 policy 的表建立默认 `ComparisonTablePolicy`。`contracts.py:668–675` 默认 `ignored_columns=()`、`ordered_policy=None`。`standard.py:210–220` 只有非空 ordered policy 才调用 ordered 比较；`:697` 默认把共同列（包括 `no`）纳入普通 value 比较。文档引用的 `B/application/preview_jobs.py:1320–1364` 也没有提供 table policies，因此照搬这条链不会自动得到 ordered/blank facts。

Canonical Storage Contract §3 明确 `no` 不进入普通 row-content modified 判定。现有 `T/test_comparison_ordered.py:134` 的 move-only 场景要求零 content update、产生 ROW_MOVED；这些用例显式配置 ordered policy，不能证明 History 默认调用已满足该语义。

**触发与影响：** 两个合法 canonical commit 中 real gid 和业务值不变、只交换 `no`。按文档所举现有装配先例直接调用，走普通 keyed 比较，将位置变化计入内容修改，缺少承诺的 ordered/blank extension，随后 Risk/Surface/Bundle 继承错误解释。仅同 commit、加表或 schema-degraded 的样本发现不了此问题。“同一函数”不能替代“正确的 policy 与 canonical 输入解释”。

**最小修正方向：** 明确 History 从哪个已存在的公共事实/规则入口得到每表 comparison policy、canonical ordered/pseudo provenance，以及如何冻结/恢复；不能在 History 猜测 gid 或复制私有规则算法。若需要原 owner 的最小公开适配，列精确条件预算，不能一面承诺语义一面笼统禁止必要路径。仅修本 consumer 必需的边界，不要求重做 Preview/Submit。

**关闭标准：** 修订 §5 输入矩阵/绑定与恢复说明、§8 owner、Plan 预算；列出 canonical move-only、pseudo/blank、普通 keyed 的少量代表场景，并指定真实 Repository 读取对本地同 policy oracle 的语义对照。可复用既有 capability owner 测试，不复制其矩阵。docs 复审检查完整可执行路径，运行证明留实现阶段。

### F2 — P1：HistoryNode 的 40-hex CommitId 限制违反 Repository 公共类型

**位置：** Design:112（§3.2 `commit_id: ... (40 hex)`），连带 §4.2、§7.1 的 DTO 映射。

**证据：** `contracts/repository-service.md:116` 定义 CommitId 为 Repository-scoped opaque string，1..1024 code points；`vnext/repository_contracts/src/gateway_repository_contracts/types.py:30` 的 `CommitIdString = BoundedOpaqueString`，不是 Git SHA。`B/domain/submission/models.py:181,206` 保存 Repository 返回值，不生成 40-hex 身份。Canonical Storage §1 也明确 commit hash 与各种 digest 不是可互换域。

**触发与影响：** 合法 initial/Submission commit 不满足该人为形状时，History 输出校验或冻结输入被拒绝，真实 Repository journey 无法按冻结 DTO 交付；即使 fixture 使用 40-hex 假值通过，也不能证明兼容。

**最小修正方向：** 保持 exact opaque CommitId，声明其 owner 与实际界限；不转码成另一 identity、不 trim/normalize、不套用业务 ID 或 SHA-256 规则。HTTP path 传输编码继续由 Repository adapter 拥有。

**关闭标准：** 三份文档消除 40-hex 假设；节点、payload、result 和 replay 原样保留非 40-hex 合法 commit；测试预算包含真实返回值及一个合法 opaque 值的 round trip。

### F3 — P1：HTTP 接受响应与 generic Operation 授权接线不能按现有预算完成

**位置：** Design:250、302、308、334；Plan:78、147。

**证据：** `B/http/schemas/preview.py:25–33` 的既有 `OperationAcceptedResponse` 必填 `workspace_id / upload_revision_id / generation`，status 仅 QUEUED，并非文档声称的 `{operation_id,status}`。另外 `B/http/routes/operations.py:37` 在调用 `authorize_operation_read` 前无条件检查 `workspace_read`，`:45` 传入 `permission_checked=True`；后续 helper 当前也按 Workspace 返回。Plan 仅列 `orchestration/operation_scope.py`，没有 `routes/operations.py`。

**触发与影响：** 无 Workspace 的 History accept 无法按既有 DTO 构造合法响应。仅具 `read_project_history` 的合法审计 actor 虽可 accept/result/bundle，却在 generic operation route 先收到 403；新增 helper 分支根本不能到达。授予额外 Workspace 权限不是设计所承诺的独立授权修复。

**最小修正方向：** 在已有新增 `schemas/history.py` 预算内定义精确接受响应；明确 replay status 是接受时状态还是当前状态。补齐 generic route 的按 job/business reference 授权分派和窄依赖接线预算，保留原 Preview/Submit 授权，不造 Workspace 字段。

**关闭标准：** HTTP 图从实际 route 起可走通；History-only actor 可以读取自己的授权 scope 的 generic operation，workspace-only actor 不能读取 History operation；撤权、改绑、跨 scope 同样受限；accept/replay DTO 可直接构造。分别归 `test_history_http.py` 与 `test_operation_http.py`，production factory 冒烟而非仅 mock router。

### F4 — P2：确定性 operation/acceptance ID 的分隔符拼接存在确定碰撞

**位置：** Design:247–249。

**证据与触发：** ID preimage 是 `history-compare:{device}:{project}:{key}`。合法两组 `(device, project, key)`：`('dev:a','p','k')` 和 `('dev','a:p','k')` 得到完全相同 preimage `history-compare:dev:a:p:k`，从而相同 op/hca ID；这不是 SHA 截断概率问题。`B/domain/workspace/models.py:33–47` 的 identity 未禁止冒号，文档也只规定 opaque byte 限额。Business Lifecycle §1A 要求 exact tuple 区分 scope。

**影响：** 不同授权 scope 的独立请求撞到全局 PK/operation UNIQUE，第二个无法正常接受；若实现借 ID 查 replay 还可能误关联。这里只确认身份碰撞及可用性问题，不将未实现的泄漏路径当作已发生漏洞。

**最小修正方向：** 使用带 domain separator 的 canonical tuple/object 编码再 hash，沿用已有 JCS 即可；不用新增身份平台，不缩窄已允许的业务标识来掩盖碰撞。

**关闭标准：** 上述两组生成不同 ID；同 exact scope/key 可确定重放；异 key 独立；acceptance/operation 同事务闭包保持。唯一 owner 为 `test_history_compare_transactions.py`。

### F5 — P2：§6.6 自行豁免 accepted integrity 要求，且“已有 Repository-side owner”没有落点

**位置：** Design:290–291、389。

**证据：** Operation Lifecycle and Integrity §3–4 对 authoritative repository content/readback mismatch 要求 durable incident 或等价 control record，并规定保留及可读性。Design 却把 commit 缺失/回读不一致归为“无 delete/rewrite 所以 V1 无触发源”，仅 FAILED+metric，并把持久责任交给未指明的“既有机制”。检索基线 `vnext/**` 未找到该生产 incident 实现；唯一同名测试 `T/test_artifact_staging_conformance.py:134–146` 是手工创建 JSON 后确认 staging 删除不碰它，并非生产 incident 服务。

**触发与影响：** 历史事实引用的 commit 实际不可读取，或已经确认的权威内容回读不一致。普通 I/O、数据损坏、恢复不一致不以产品提供 delete API 为前提。当前文档既承诺处理该场景，又静默改写其 Contract 后果，后续实施无法判断按哪个门禁交付。

**最小修正方向：** 区分暂时依赖不可用、可重算 artifact 缺失与确认的权威事实异常；明确现有 durable Operation/diagnostic 能承担哪些等价记录要求、哪些尚未满足。若拟减小 Contract 要求，列为 owning Contract 待决定项，不能声称无冲突或凭空依赖现有服务。本审核不要求 5E 建通用 incident 平台、broker/sidecar，也不授权修改上游。

**关闭标准：** 文档提供具体责任落点与最小持久诊断/读取/保留策略，或引用另行接受的 Contract 决定；消除未证实的 E 依赖与无触发源推论。普通 artifact 缺失不被升级为 Repository 权威损坏，测试只证明一个代表性屏障。

### F6 — P2：执行门禁有互相冲突的放行条件与不可运行的五包命令

**位置：** Plan:55–57、70、130–137、166–169、200–203、230；Design:378、381、384–385。

**证据与触发：**

- 5E kickoff 要求完整 5D exit，却另称 initial-empty 未 pass 不阻碍 S1、S3 可 deferred。已接受 5D Plan §4 S1 明确未通过该 gate 不能给 S1 pass，5D 最终 conjunction 也要求真实零表 journey。合法 5D exit 不应与缺失这项必要证据并存；“先写 T 测试”的例外还与禁止 5D exit 前开始 5E 实现冲突。
- S1 是带 production wiring 的独立交付阶段，Plan:200 无条件允许延期到 S2；testing-conventions 的 Docker 规则要求阶段最终候选 fresh build。Plan:203 又只在 final fix 涉及容器边界时重跑，与 S4 最终候选 fresh 要求不一致。阶段内普通逻辑迭代可延期，阶段通过不能借旧镜像证明。
- 五包命令列 `shared_kernel common common_infra repository_service backend`，基线没有 `vnext/common`、`vnext/common_infra`；实际另外两包是 `repository_client`、`repository_contracts`。命令到不存在的目录就退出，无法完成声称的五包门禁。

**影响：** 同一缺证据候选可被不同章节解释成继续/延期/通过；照抄命令无法验收。不是要求本轮 docs-only 跑实现测试，而是要求后续执行条件唯一且可运行。

**最小修正方向：** 明确 5D accepted design 允许 5E docs review，verified slice exit 才允许实现；缺少必要 5D 证据时停止 kickoff，不设置绕过分支。统一阶段内延期与阶段最终候选的区别；替换成真实五包。所需测试可以先写进设计，不应把创建实现测试说成仍在 docs-only 范围。

**关闭标准：** S1/S3/S4 和 final handoff 对 initial-empty、fresh image、0 skipped 的判定一致；静态核对命令路径完整；每项延期都有明确最终关闭节点，不再允许最终 exit 遗留必需零表腿。

## 4. 完整场景推演与非阻塞观察

| 场景 | 审核结果 |
| --- | --- |
| initial + 全部成功 Submission + 五种 Review + 两种 Archive disposition | 权威来源/保留方向正确；不只取 approved/archived。baseline 与 submission 分别保留身份和 promotion link；失败 import/private candidate/marker 无权进入树。CommitId 限制须按 F2 修正。 |
| 两/三节点 resolve → accept → worker → 恢复/发布 → result/bundle | HISTORY/FULL/NOT_APPLICABLE 与相邻双 pair 可表达。`test_comparison_planning.py:356` 与 `test_bundle_assembly.py:159,207` 分别支持 binding 和共享 artifact 拓扑；不是 History 实现通过证据。F1/F3/F4 未闭合前不能宣称正式链路可交付。 |
| 并发 Review/Archive | 单请求 readonly DB snapshot + immutable commit freeze 能保持页内一致；Review/disposition 改变不改变已接受比较输入。无必要让长 Repository I/O 进入事务。跨页明确不承诺全集快照，不把 head_version 当作 Review 变化检测器。 |
| 跨 actor、撤权、mapping 改绑 | 同 scope 审计权限覆盖多 actor 与 Contract 相符；每次读校验 current Repository，worker 不重授权可以成立。generic route 实际入口缺口见 F3；403/404 表的重复冲突仍须统一，见下文。 |
| 空 initial、相同 commit、多身份 | 公共 pair/bundle 可以承载；节点不可按 commit 合并，仅物化去重。空 initial 依赖 5D 完整验证，不能用零行表冒充零表。重复 node ref 按设计合法；需避免计划中的“duplicates”测试文字被实现为统一拒绝。 |
| 缺失 artifact | 既有 Bundle assembly 在 missing/tampered closure 下拒绝 READY（`test_bundle_assembly.py:301,313,418`），不需要新安全框架。但已成功结果缺 bytes、重启后 checkpoint 缺 bytes的用例处置需在实现前具体化，不能仅以 PURE_RECOMPUTE 自动保证恢复。 |
| 5D 未实现 / 已实现 | 允许依赖 accepted design 完成 docs-only 评审；实现前重核实际 schema/port/seed/权限及独立 exit。此次未吸收主目录 5D-S1，也不据此认定 5D pass。 |

**待验证假设，不计作已证实实现缺陷：**

1. §5.2 把 request fingerprint 与含 resolved commits/version 的 binding 合一，§6.2 又要求先 replay 后 resolve。实现前应明确：用 incoming ordered refs 对照 durable refs、如何从旧记录重建冻结 preimage、版本升级后是否仍能 replay、改绑后如何拒绝旧 Repository 结果。已有冻结数据可以支持合理方案，目前不能仅凭这处省略断言一定绕过授权。
2. SUCCEEDED 结果与 operation 共存、FAILED/CANCELLED 中间物清理的主张，需要具体 pin/release 与缺失结果错误处理。检查了既有 protection/checkpoint 模式，未发现必须新增 GC 状态机的依据；但本轮没有运行 History 恢复/取消测试。Operation durable record 与 artifact cache 的保留语义不可互相替代。
3. V1 单版本是假设，不是已验证跨版本兼容。HTTP Arrow 当前从 canonical catalog/rows 重建 summary，不能把它当作读取历史 manifest 的完整规则版本证明。真实跨版本输入出现时按既定 reopen 处理，不以同一函数名或 digest 字符串推出业务等价。

**非阻塞文档整理：** Design:315 和 :316 同时给跨 scope 引用规定 403/404，应统一到 §4.2 的不披露语义；“1 个 JobDefinition（3 步）”宜改为一个 job kind、三个按 step 注册的定义（基线 `preview_jobs.py:304–343`）；`baseline_node_records` 的字段命名、submission scope 经 Workspace/固定归属解析的实际 join，应在 5D 对齐门明确，不能把 D 表字段简称当作已存在列。

未要求新增 comparison_projection/business_projection 占位能力，没有证据表明必须把 P5 既有私有 import、nominal ref 或 manifest 归属历史债全部塞入 5E。新增消费者仍必须遵守 P5 §2A；F1 如需公开适配，仅处理实际依赖。远程读取与本地 oracle 等价是 implementation-stages:622 的 5E exit 要求，应归入 F1 的具体验证，不使用作者临时脚本替代。

## 5. 5D 依赖与文档接受边界

5D 文档已接受（`p5-5d-s0-independent-docs-acceptance.md`），可以作为 5E 文档设计输入；不能作为 baseline/Archive/readiness/initial-empty 已实现的证明。三份 candidate 对 E/D/P 的总体区分是合理的，少量具体错误由上述 findings 处理。

后续实现的硬前置仍是：独立 5D slice exit、实际 Node/Head/disposition 与 Review closure、seed 不回退和固定 scope、真实 initial-empty 完整链路、Archive HTTP 权限及 fresh Compose 证据。kickoff 应按最终 5D source tree 核对 schema 邻接版本及 ports，偏离时先修订 5E 对应设计。5E 自身退出只签其链路；P5 §2A 全局收口与代表性性能输入仍单独验收。

## 6. 检查与未运行验证

本轮执行：只读 Git/worktree/status/diff-stat、候选 SHA-256 与路径/符号检索、上述 Contract/源码/测试的静态调用链和场景核查；创建本报告并检查格式。没有修改 candidate、源码、测试、依赖、部署或 accepted Contract，没有覆盖并行工作，没有提交。

本轮未执行：pytest（focused/unit/integration/全量）、五包 ruff/mypy、Dolt 实验、作者临时脚本、镜像构建、Compose、部署。结论是文档审核，不宣称任何 5E 实现门禁通过；现有测试只读核查不等于重跑通过。

```text
Current HEAD (report checkout): d19b3efcab42d54523b94146d7a4d687823b5b86
Reviewed code HEAD: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
Container rebuild required this review: no
Reason: read-only design review + independent report only; no runtime/deployment changes
Container gate for current HEAD: not-applicable to this docs-only review; not verified here
Last historical verified image revision: 04317788c259b172e3b8580cfe42bac8d16735f0
Last historical source-tree: sha256:9b7f863c4d24596fdddb3bbd82a4e5b25a85fcf1af26dd8af2124dbb06c885d9
Image IDs: not independently inspected in this review; historical 5C acceptance owns them
Required execution point: authorized implementation stage final candidates and final 5E conjunction
```

历史 image/source-tree 数值来自固定基线中的 5D 接受记录，仅作 provenance 指针，不是本轮验证。F6 关闭后按明确的阶段规则运行对应门禁；本报告不调用旧镜像替代当前候选证明。

---

## 7. v2 复审 — 2026-09-21

### 7.1 本轮结论与固定输入

**结论仍为定向修订；v2 尚不通过。F2、F3、F4、F6 的实质问题关闭；F1、F5 未关闭。**

v2 已修正多处真实接口错误，不需要整体返工。剩余问题不是“尚未写实现”，而是设计自身的冻结时序无法同时满足，以及 accepted integrity Contract 的处置尚未确定。不能把新增 pending 项视为 finding 已关闭。

首轮 §1–6 原文保留；本节结论仅对应以下 v2 文件。追加前报告 SHA-256 为 `f606010820de9201dcb7f6c688236c88f532a2005fecae92f3eedfe75667bbaa`。不使用作者给出的缩略 `88ee0542…76b675ea` 代替本报告实际记录的三文件身份。

| 对象 | 本轮实际值 |
| --- | --- |
| 报告 checkout | `/home/dev/gateway-data-management-system`；`phase1/gate-ownership-repair`；HEAD `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` |
| 报告 checkout 入场 status | 仅本独立报告 untracked；无其他未提交修改 |
| candidate checkout | `/home/dev/gdds-5e-history-compare-docs`；`p5-5e-history-compare-docs`；HEAD `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c` |
| candidate status | 仅三份 candidate untracked；无 tracked diff；未吸收主分支推进 |
| Entry，138 行 | `1af51512adfd0ef7967f4bd3ea8475950c24e565374a5ff0f2c8b3114980d8fd` |
| Design，421 行 | `ae22a1c252f1aa7b0b53082738c4291ec2991ee397f96b26b4b30bf622dfab76` |
| Plan，240 行 | `a802911c10da3529a399f97c2373ad91964338f634328f373a6d98d66624ad78` |

三个摘要在本轮读取开始和报告追加前一致。本节 Design/Plan 行号均指 v2；源码、Contract、测试仍固定在 `6f6a780415`。沿用首轮已读权威依据，并针对修订重读相关源码与 Contract；不把主目录最新 5D 实现作为本轮 E 证据。

### 7.2 Finding 关闭表

| Finding | v2 结论 | 依据 |
| --- | --- | --- |
| F1 比较 policy | **未关闭，P1** | 已识别默认 policy 缺口、提供公共 resolver 和代表场景，但具体 per-table policy 同时要求在 accept 和后续 assemble 才构造，缺少可执行冻结链；见 §7.3 |
| F2 CommitId | **关闭（文档层）** | Design:116、126 改为 exact opaque 1..1024 code points，禁止与 ID/digest 约束混用；符合 Repository 公共 Contract |
| F3 HTTP DTO/授权 | **关闭（文档层）** | Design:257、316 明确新的 History DTO 与当前状态 replay；:322、349 明确 generic route 分派；Plan:79 已明确授权修改实际 route。路径总表漏同步属下文整理项，不再解释为禁止该文件 |
| F4 ID 分隔符碰撞 | **关闭（文档层）** | Design:255–256 的 named-key JCS 区分 exact scope/key，:368 明确反碰撞用例；不再存在首轮确定碰撞 |
| F5 integrity | **未关闭，P2** | 已撤回虚构既有机制及“无触发源”，但等价载体仍 pending，且具体字段/后续处置未覆盖 Contract；见 §7.4 |
| F6 实施门禁 | **关闭（实质规则）** | Plan S1 kickoff 明确 5D 完整证据；S1 末候选 fresh、S4 最终 fresh/0 skipped；五包实际路径已纠正；无测试先行实现的绕过分支。Entry 末尾摘要仍漏列 S1，须随正文同步 |

这里的关闭不表示实现、容器或 slice gate 已通过，也不接受作者自签“全部 findings 已落实关闭”的表述。

### 7.3 F1 持续阻塞：具体 table policy 的冻结点与数据可得时点冲突

**位置：** Design:73、203–207、212–213、253–254、272–285；Plan:78、89–90。

**已证实的设计矛盾：**

1. §5.2 的 accept fingerprint 等于 compare binding，包含实际 `table_policies` 列表；§6.2 第 4 步要求在短 DB 事务内构造并冻结它。
2. §5.3 第 1 步才读取 exact commit 的 Snapshot/Summary/TableSet；第 2 步才按每张表调用 resolver 构造该列表，又要求与 acceptance preimage 字面相同，resume 不重派生。
3. 实际 `B/capabilities/table_rules/resolver.py:36–51` 需要 `table_name`，RAW_PRIMARY_KEY 分支还使用 `primary_key_columns`（同文件 `_decision_from_record`）。`registry.py:194–205,318–325` 包含 regex selector 和 fallback，不是可在不知道 Repository 表清单时枚举全部具体表名的目录。节点解析所得 scope/ref/commit 不提供这些表描述符；`B/domain/submission/models.py:171` 只有 manifest 引用等冻结字段，并无内联表清单。文档未指定额外的可用事实读口，也明令 accept 事务仅 control DB、无 Repository I/O。

**具体失败场景：** 新 accept 比较 initial 与含任意新增匹配 regex 的 ordered 表的 Submission。服务在 accept 时知道两个 commit，却不知道实际匹配的表名和 schema，不能产生完整 per-table policy preimage。若写空列表后在 worker 填充，违反冻结 fingerprint；若在 accept 内读取 Repository，违反短事务/零外部 I/O；若复用当前 ruleset 后每次重算，违反所声明的冻结及恢复语义。三节点表集合不同同样触发。

此外，v2 接入了 per-table 列表后，Design:285 仍称 payload “只有 scope/node refs/commits/binding digest/ruleset 与 contract version，远低于 64 KiB”；acceptance DDL 也没有 policy 内容字段。即使可经 job_payload 保存，仍须说明真实承载位置和预算，而不能只把 digest 当作可恢复内容。

**已确认可保留的部分：** `migrated_table_ruleset_snapshot`、`resolve_table_rule` 是已公开入口；ordered 比较类型及算法存在。Repository materializer 在 `repository_ref.py:223–225` 赋予 `CANONICAL_PSEUDO_GID` provenance，`snapshot_materialization/artifact.py:474–516` 能编解码该 metadata，故不将“canonical provenance 不存在”列为 finding。F1 的问题是本用例冻结/恢复编排未闭合，不是要求新建 capability 或伪造已有能力。

**最小修正方向：** 选定一个明确可实现的冻结点，区分请求 replay identity、接受时固定的规则身份与 worker 解析后的执行 binding；或者提供有证据、事务外且有界的输入描述符预读方案。无需新增状态平台，也不要求只有某一种实现。明确实际 policy 内容的存放、版本/顺序、恢复来源和大小预算；不得改写已经成立的 request fingerprint。

**关闭标准：** 修订 §5.2/§5.3/§6.2/§6.4 与 Plan，使任意合法表名、两/三输入不同表集合、响应丢失原 key replay、materialize 后重启均只有一条一致的数据流；每个冻结字段在冻结点确实可得，accept 仍是短事务。比较语义沿既有 owner，用已加入的 ordered/pseudo/普通表代表场景验证；无需扩充全故障矩阵。docs 复审只要求这条设计链闭合，不要求提前实现。

### 7.4 F5 持续阻塞：pending 不替代等价记录设计或已接受的 Contract 决定

**位置：** Design:297–305、404–405；Plan:78、S2/S3 阶段交付与验收。

**证据：** Operation Lifecycle §4 已明确等价 control record 的最低语义：expected/observed digest、affected tables、recommended action、first/last seen、acknowledgement status、resolution reference，以及 admin readback 和保留至 acknowledge/resolution/operator archive。该要求不以存储表是否命名 incident 为准。

`B/operations/contracts.py:170–179` 的 `OperationDiagnostic` 仅有 `code/message`（message 4 KiB）；它当然可以承载 bounded 文本，但基线不因此自动获得后续确认/处置接口。`B/operations/state.py:118–121,151–154` 的 final terminal record 只允许完全相同的幂等重复，不能在 FAILED operation/step 上原地更新后续 acknowledgement/resolution。v2 没有定义其他处置记录落点，却把这两个终态对象称为等价载体。

**触发与影响：** Compare 确认同一 exact commit 回读不一致并 FAILED 后，管理员需要确认和记录 resolution。按现设计没有可执行的记录与读取闭环；仅延长 operation 保留并不能表达这些事实。§10 又一面说 pending “实现前必须关闭”，一面称不阻塞 S1–S3 主体，而 Plan S2 要交付 §6 全部语义、S3 要跑正式生产链路，阶段完成条件不唯一。

**最小修正方向：** 不要求独立 incident 表或 Repository-side 新服务。若采用现有记录作最小等价机制，就逐项说明必需事实、确认/处置的实际接口和保留落点；若拟豁免部分要求，须先取得相应 owning Contract 的明确接受决定，本审核无权替代该决定。区分普通瞬时读失败与确认的权威异常即可，不要求为每次 compare 无条件双读或增加探针平台。明确受影响的 Compare 阶段不可在未决时通过；S1 纯读投影是否可独立推进可单列，但不等于整份设计已无 blocker。

**关闭标准：** pending 有明确已接受结论，或文档给出符合现行 Contract 的具体最小方案及对应有限路径预算；F5 不能仅通过改名为 pending 关闭。S2/S3 的交付与停止条件须引用同一前置，不可留下“类 c 到时再补”同时宣称完整 Compare 可用。

### 7.5 其余推演、待验证项与整理项

重新沿完整路径核对后，首轮对业务树、成功 Submission 全覆盖、业务父边、同 commit 多身份、跨 actor/current permission、只读 effect 闭包及 5D 依赖的总体判断保持。新增 policy 映射没有理由改变这些模型；空 initial 的 5D 证据现在是单一硬前置。三节点相邻 pair、真实 Repository 与同 policy oracle 的验收已写入 Design:376，不能用同 commit 小样本代替。

**待验证假设（非新增 blocker）：** v2 replay 明确先做 immutable node 引用/当前授权解析，再决定 replay，可与 Review/Archive 状态变化不影响重放相容。政策版本漂移保守 409 是明确选定的 V1 限制；F1 重构冻结点时须同步其比较依据。artifact 缺失已有稳定错误/不伪 READY 的决定；仍需实现阶段证明 checkpoint 恢复、终态保护释放及已成功 bundle 缺失的 HTTP 行为，不能从 PURE_RECOMPUTE 词汇直接推得通过。

**随下一版同步的非阻塞整理：**

- Plan §3 总表遗漏 `http/routes/operations.py`，与明确列入的 Plan:79 同步即可；本轮按具体阶段交付解释其已在预算内。
- Entry 最后镜像执行点摘要遗漏 S1；以已修正 Plan S1/§6.1 为准同步。
- Design:316 把新增 `schemas/history.py` 标成 E，应为 P；`:218` 的 trusted-table-rules docstring 属 `OrderedTablePolicy`，不是 `ComparisonTablePolicy`。不影响公共接口实际存在的结论。
- `ARTIFACT_UNAVAILABLE` 已在 §6.6 定义，但 §7.2 尚未给 HTTP status；补齐映射。不要把终态成功状态改写为失败来掩盖 bytes 缺失。
- Design:367、369 与 :370、371 对 policy 语义和 generic read 存在 owner 表重叠；Application 保留绑定集成代表点，原 capability/operation HTTP 文件保持对应语义矩阵唯一 owner。

5D accepted design 仍允许此轮 docs-only 复审；verified 5D exit 及实际 schema/port 对齐仍是未来实现前置。本次没有验证主 checkout 的新 5D 提交，不据其推进降低或提高本轮结论。P5 整体架构/性能收口没有被纳入 F1/F5 的最小修订范围。

### 7.6 本轮检查、隔离与镜像记录

已执行只读 HEAD/branch/status、候选摘要、三份 v2 全文与修订依赖源码/测试/Contract 核查；仅在原报告末尾追加复审，首轮记录保留。未修改 candidate、源码、测试、依赖、部署、accepted Contract，未提交或推送。

未运行 pytest、五包 ruff/mypy、作者临时脚本、Dolt、镜像或 Compose；没有实现门禁通过声明。文档层 F2/F3/F4/F6 关闭不代替这些运行证据。

```text
Current HEAD (report checkout): 8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523
Reviewed code HEAD: 6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c
Container rebuild required: no
Reason: read-only docs re-review + report append only
Container gate for current HEAD: not-applicable to this review; not run
Last image/source-tree: historical pointer unchanged from §6; not inspected this round
Required execution point: authorized stage final candidates and final 5E conjunction per revised Plan
```


## 8. v3.4 独立复审（2026-09-21，本轮最新结论）

### 8.1 结论与版本固定

**定向修订。F1 文档层关闭；F2/F3/F4/F6 保持关闭；F5 部分修复，仍有一项阻塞：integrity 的 expected/observed 内容事实被替换为首次/复读诊断指纹，尚不能认定符合 accepted Contract。** 不要求整体返工，也不因尚未实现而否决设计。History 权威事实模型、授权边界、相邻 pair 编排及主要实施路径仍成立。

本节只针对实际读取的 **v3.4**，不是用户较早列出的 v2。前文是历史审核，不回写；追加前报告 SHA-256 为 `b5a9b5f3259da96373d775bac9f3b22d4edb3efbd7fe57b054fe6a122b7a0d2c`。

| 对象 | 本轮固定值 |
| --- | --- |
| Candidate worktree / branch | `/home/dev/gdds-5e-history-compare-docs` / `p5-5e-history-compare-docs` |
| Candidate HEAD / 声明的代码基线 | `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c`，两者一致 |
| Candidate status / 作者范围 | 三份文件均为 ` A`（intent-to-add）；无其他工作区改动 |
| Entry，158 行 | `3a065ba6d92dd79baa1ba10b4207bd67c04d5f8e2f36984c753ac6f8aa63a716` |
| Design，481 行 | `b6a55fef8ee91096b6c4503e30d01358507fded51cfbd82370fb5139c9ea9c7e` |
| Plan，247 行 | `0b7f0278257a41cc62aa0083d25fa90a49aa3228997ad814f2bb482d0add963f` |
| 报告 checkout HEAD / branch | `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` / `phase1/gate-ownership-repair` |

报告 checkout 有并行 5D-S2 未提交工作：5D execution plan/handoff、archive application/domain/control DB 及相关测试修改，另有未跟踪的 5D review、`application/archive/closure.py` 和本报告。全部保留，不将其当作本轮实现依据。所有以下源码结论均在固定 candidate worktree 复核；主 checkout 不作为 5E 代码基线。

审核范围沿用 §2/§7 的强制输入：AGENTS、testing-conventions、P5 总纲、implementation-stages、Business Lifecycle、Canonical Storage、Operation Lifecycle、Contract Taxonomy、比例化 policy、5D accepted acceptance/design/execution；继续核对 Comparison/Table Rules、Repository materialization、Operation 发布与 HTTP DTO/route/mapper，补核 ADR 0016。作者自检编号及临时脚本不作为独立验收证据。

### 8.2 Finding 关闭状态

| Finding | 本轮判定及证据 |
| --- | --- |
| F1 | **关闭（设计层）**。Design:201–217 将 accept-binding 与 compare-binding 分开；前者只依赖 DB 可得节点/commit/规则身份，后者在 materialize 后按公开 resolver 构造 policy，与 sides 一起进入 checkpoint。assemble 从 checkpoint 恢复；Design:308–309 明确 policy 不进入 inline payload。不同输入表集合、三节点中间输入复用、ordered/blank 绑定与真实远端 oracle 已有执行及测试落点。 |
| F2 | 保持关闭；Design:118、127 的 opaque CommitId / code-point 约束未退回 Git SHA 形状。 |
| F3 | 保持关闭原问题；Design:261、365、371 与 Plan:156 已明确新 accept DTO、generic route 的授权分派和生产路径预算。新增 incident 响应的 DTO 整理见 §8.5，不据此重开原授权 finding。 |
| F4 | 保持关闭；Design:257–258 使用 named-key JCS object，不再拼冒号元组。 |
| F5 | **部分修复，未关闭**。独立 control row、终态不变、internal-bearer ack、resolution、保留及 S2 必交付均已明确；不再沿用上一轮“没有确认/处置落点”的理由。剩余问题见 §8.3。 |
| F6 | 保持关闭；Design:450–459 的 5D kickoff 硬前置与 Plan §6 的 fresh-image/最终门禁一致，未恢复 deferred 零表腿。 |

### 8.3 F5 — P2，持续阻塞：诊断复现指纹不能自行替代权威内容的 expected/observed digest

**位置：** Design:295–296（存储字段）、340–349（取值与等价声明）、463–464（“已关闭”及“待 S0 接受确认”）；Plan:156（指纹 helper 与零 capability 改动预算）、160（预算外停止）。

**已证实的缺口及权威证据：**

- Operation Lifecycle and Integrity:57–78（§4）要求权威事实 incident 保存 `expected_digest / observed_digest`，并将 digest 与诊断引用分别列为保留信息；ADR 0016 的对象是 Repository/content readback mismatch 等权威事实。Contract Taxonomy:44–59 规定语义由 owner 定义，消费方不能为本地便利改变 owner contract。
- 固定基线 `B/capabilities/snapshot_materialization/repository_ref.py:331–349` 实际将读取 rows 算出的 `raw_digest` 与 `hidden_table.raw_content_digest` 比较；不等时返回固定消息 `raw_content_digest does not match hidden summary`。`MaterializationDiagnostic` 的公共字段不携带这两个值（`contracts.py:170` 起）。因此文档指出当前公开面拿不到两个内容值，这一源码事实正确。
- Design:344 却规定第一次失败的诊断哈希为 expected，第二次失败的诊断哈希为 observed。两者都来自失败观测；第一次失败并不是预期内容的权威来源。域分离、JCS、候选诊断选择及有界重读都不能补出缺失的内容事实。Design:464 本身仍将该语义列作待接受，不能同时据此宣称 §4 已逐项等价满足。本轮未发现对应 owning Contract 的已接受决定。

**具体触发场景：** 同一 exact commit 的表 T，其 summary 期望内容摘要 A，读回 rows 算得 B，且 A≠B。首次和复读均返回相同 code/table/message。按本设计，记录必为 `expected_digest=F(d)=observed_digest`。即便实际读回内容从 B 变成另一不匹配内容 C，只要错误消息相同，仍得到相同 F。这里没有 SHA 碰撞：哈希输入根本没有 A/B/C。记录可以证明“同一诊断再次出现”，不能表达哪一份内容被期待、哪一份内容被观测。

**影响：** durable incident 与 ack 闭环虽可实现，但对外使用 accepted 字段名承载了不同语义；管理员或后续 consumer 不能从该记录判断内容 mismatch 的两侧。执行计划又以 capability 零改动为固定前提，实施者被迫在“按此填满字段”与“停止回设计”之间选择。失败点局限于异常诊断公共边界，不影响业务树或正常 compare 主路径，不支持整体返工。

**最小修正方向（任选其一，须形成一个明确决定）：**

1. 保留现行 Contract 含义，由原 materialization/Repository 语义 owner 定义有界的公开 mismatch 诊断事实及可得性；在必要范围调整接口/路径预算，History 只投影公开事实，不复制私有 digest 算法。并非要求每个 CORRUPT 场景强造两份摘要；不可取得时的表达也应明确，不以第一次错误冒充 expected。
2. 若要采用诊断指纹作为本窄场景的最小等价信息，先取得 Operation Runtime and Repository Integrity owner 对该信息降级及字段含义的明确接受依据。将其与内容摘要区分，说明缺失内容证据的处理和诊断可追溯性，再同步设计与验收。本次独立审核不代签这一语义变更，也不授权修改上游。

保留已有小表、ack、保留与事务闭包即可；无需通用 incident 平台、broker/sidecar、额外信任域或全 P5 故障治理。

**关闭标准：** Design §6.4/§6.6/§10 与 Plan 对同一方案一致，不再“已关闭”与“待确认”并存；从公开事实到持久字段的映射有真实含义和可执行预算。唯一 integrity owner 用一个 A≠B 的 mismatch 代表场景验证记录语义，外加已有 ack/保留闭环；无需穷举内部 digest 步骤。docs 复审检查设计及 owner 决定，不要求此时提前实现或跑门禁。

### 8.4 完整场景复核与 5D 边界

- **History 读取：** 权威源仍是 baseline/submission/review/disposition 事实；全部成功 Submission 保留，包含待审、驳回、撤回及不同 archive disposition。同 commit 多业务身份不合并；业务 parent、排序、分页和页内 readonly 快照分离清楚。无 Dolt log/private candidate/失败 import/Operation marker 混入。
- **两/三节点执行：** 当前 scope 内解析 exact commit，accept 短事务冻结请求；worker 物化 distinct commits、公开 ruleset 投影 policy、冻结执行 binding、相邻 pair、Risk/Surface/Bundle、恢复及发布链在现有公共模型下可成立。未冒用 native diff 或声称三侧原生比较；F1 闭合不等于运行验收通过。
- **并发与读取边界：** 并发 Review/Archive 不改已冻结 commit；权限撤回、mapping 改绑和跨 scope 在每次 Operation/result/bundle 读取重新判定。同 commit 合法 UNCHANGED；成功后的 artifact 缺失有稳定错误，不篡改终态。异常内容仍受 F5 限制。
- **5D：** accepted 设计足以支持 docs-only 设计评审，不等于 verified implementation。实际 schema/port/version 对齐、initial-empty 和零表真实旅程、5D 独立 slice exit 仍是实现启动前置；不据主 checkout 的提交或未提交实现推定其通过。5E slice exit 与 P5 整体退出继续分别验收。

### 8.5 待验证假设与非阻塞整理

**待验证假设，非已证实缺陷：** V1 单 ruleset 的确切版本兼容、5D 最终表形与读口、checkpoint 容量及恢复、事务发布/取消时的保护释放、真实 Repository 与本地同 policy oracle 等价，仍须授权后的实现证据。现有 `LeaseSession.publish_operation` 和 preview 的 transaction-bound publication 模式支持窄 control row 与终态原子发布的方向；本轮不因没有 History 实现而新增 blocker。

**非阻塞建议：**

- Design:371 新承诺 generic Operation 回读携带 `integrity_incident`。基线 `http/routes/operations.py:21–24` 固定 `response_model=OperationResponse`；`http/schemas/operation.py:17–28` 及 `http/mappers.py:75–92` 没有该字段。预算已有 route 和新 history schema，可明确选定新增专用响应/union，或列入现有 DTO/mapper 修改；不要只改授权就认为 incident 能通过响应校验。该缝可在已有职责内解决，不认定必须改被禁止模块。
- Design §8 对 generic-read 授权、incident accept 门禁分别在多行 owner 出现。落实时保留一个权威参数矩阵，其他文件仅集成冒烟，避免重复证明；不增加测试数量要求。

### 8.6 检查与隔离记录

执行了只读 HEAD/branch/worktree/status、候选全文与相关公开接口核对、摘要复核、candidate `git diff --check`（通过）。只追加本报告，历史字节保留；不修改三份 candidate、源码、测试、依赖、部署或 accepted Contract，不提交/推送。

未运行 pytest、五包 ruff/mypy、作者临时脚本、Dolt、全量 runner、镜像构建或 Compose。**没有实现门禁通过声明。** 本次只读复审与报告追加不触发镜像重建；当前 HEAD 容器门禁未运行。最后镜像 provenance 仅沿用 §6 的历史指针（source tree `04317788c2aa4c62fedf08b61037cd9ac973cd81`，本轮未验证 image ID）；正式验证仍须按 Plan 在授权后的阶段候选与最终候选执行，旧镜像不证明当前 HEAD。

本结论不改变设计状态、Contract 版本、实现权限或 5E/P5 exit 状态。


## 9. v3.5 独立复审（2026-09-21，本轮最新结论）

### 9.1 总结论与隔离

**定向修订。公开 mismatch digest pair 的语义与窄路径预算可接受；剩余阻塞是 §6.6 新增的异常分类条件，不是要求在 S0 提前实现公开接口。** F1–F4/F6 保持文档层关闭；F5 的诊断指纹替代方案已经撤回，其旧阻塞理由关闭，但新方案仍会将已知的权威内容矛盾排除出 incident。问题限于一处分类/记录规则及对应验收，无须整体返工。

版本固定如下；追加前报告 SHA-256 为 `4fa051f0245a5f1125e8061efe82ad3364a2d2e1651c1c019247a0cfd150d99f`，§1–§8 的全部历史字节原样保留，不回写旧结论。

| 对象 | 固定值 |
| --- | --- |
| Candidate worktree / branch | `/home/dev/gdds-5e-history-compare-docs` / `p5-5e-history-compare-docs` |
| HEAD / 声明代码基线 | `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c`，一致 |
| 范围与 status | 三份 candidate，均 ` A`；无其他作者修改 |
| Entry，154 行 | `fbd6704176d8f05f41e2460c91ca5e164a50f7f5d4da5190a0427a617076849e` |
| Design，484 行 | `77929896db4438decd11913f716c88a4d8c82c478b601e9c8876d39227032daf` |
| Plan，247 行 | `a661ddd89a374fd7bd27aa1ec2241e2901f3e96da2d8cb3a656f18a338929e15` |
| 报告 checkout | `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` / `phase1/gate-ownership-repair` |

主 checkout 的并行 5D-S2 docs/application/domain/control DB/tests 修改及未跟踪 review/closure.py 与 §8.1 所列一致，全部保留。源码依据只取固定 candidate worktree；主 checkout 的 5D 实现不混入结论。强制权威输入沿用同一固定基线已读的 AGENTS、testing-conventions、P5 总纲/阶段计划、四份 Contract、比例化 policy、5D acceptance/design/execution，以及 ADR 0016；本轮重点重核 Operation Lifecycle §3–4、materialization 的实际失败分支与公共类型、修订后的三份文档及执行预算。

### 9.2 已成立的修复与 S0/S2 分界

Design:341–346 明确 expected 来自 summary/声明侧、observed 来自读回/重算侧，History 只投影公开 `DigestRef`，不复制私有算法。基线 `repository_ref.py:166–179,331–349` 确实存在计算或比较两侧内容摘要的路径。Plan:157、161 为 `snapshot_materialization/{contracts.py,repository_ref.py}` 列出窄例外；`_Halt`、失败转换与诊断构造也在该文件内，未发现必须改被禁止模块才能传递这两个字段的证据。

因此，**接口实现及 A≠B 持久映射的运行证明留到 S2 合理**。这属于明确的新提案交付，不是虚构既有能力；本轮不以“字段现在还不存在”否决 docs-only 设计，也不再要求对已废止的诊断指纹方案取得 Contract 例外。独立行、ack、resolution、保留和终态不变的骨架保持可用。

### 9.3 F5 — P2：把 digest pair 一致性/可得性当成权威异常的必要条件，会漏掉已确认 mismatch

**位置：** Design:335–339、345–350（尤其 :349 的 A/B/C 示例）；Plan:94（验收只列固定 A≠B）；Entry:140–141（前置与关闭声明）。

**已证实的设计缺陷：** 新规则要求两次候选失败不仅同码，而且 pair 完全相同；若 observed 改变，明确归 (a)，不建 incident。又规定任何候选码没有完整 pair 都归 (a)。两条规则把“证据载体是否完整/两次是否完全一样”误用为“是否存在权威内容矛盾”的判断。

**决定性场景：** 同一 exact commit、同一表 T，声明摘要一直为 A。第一次完整读回为 B≠A，第二次完整读回为 C≠A，B≠C；两次均是 `HIDDEN_SUMMARY_DIGEST_MISMATCH`，没有 timeout/I/O 未完成。Design:349 明确要求此时落 (a)。而基线 `B/capabilities/snapshot_materialization/repository_ref.py:331–343` 正是在完成 row digest 计算并与 summary 比较后产生该失败：两次观测各自已经证明内容 mismatch。错误内容变化不否定 mismatch，反而还表明 immutable commit 读回不稳定。

Operation Lifecycle and Integrity:53、57–78 要求 repository content/readback mismatch 先处理 durable incident；ADR 0016 Decision 同样覆盖这类权威事实。按当前规则仅落 FAILED/metric，用户可换 key 再 accept，PENDING incident 门禁无记录可查，确认/处置与保留闭环被跳过。

**同一分类问题的另一实际分支：** `repository_ref.py:413–417` 在 summary 声明表 T、同一 commit catalog 缺失 T 时返回候选 mismatch；这个检查本身没有一对内容摘要。对重复确认的这类结构矛盾，仅因公共 pair 缺失就归瞬时不可用，同样不能证明符合 §4。并非要求为 timeout、普通 artifact 丢失或未知故障一律建 incident，也不要求用伪造摘要填满字段。

**最小修正方向：** 将权威异常判断与 digest 证据的具体承载分开。对于两次都已确认的同一 commit 内容 mismatch，不以错误值变化为降级理由；明确保存哪一次完整 expected/observed pair及其语义即可，不必新增多观测状态机。对于已确认却无 pair 的结构矛盾，由 materialization owner 给出最小公开事实及可得性表达，明确符合 Contract 的记录方式；不能默认当作瞬时故障，也不能退回诊断哈希冒充内容摘要。若要豁免该类，则需要对应 owner 接受依据，而不是 consumer 自行排除。

**关闭标准：** §6.6 分类、§10 前置与 Plan S2 验收一致；固定 A/变化 B→C 的两次真实 mismatch 不再绕过 incident；已确认无 pair 的结构矛盾有明确处置，不以字段缺失抹去事实。继续由 `test_history_compare_integrity.py` 维护一个共享参数表，覆盖原 A≠B、变化读回与一个无 pair 的代表点；不复制低层全矩阵，不扩大同 euid 威胁模型。S0 只审上述设计闭合，公开字段实现和运行证明仍在 S2。

### 9.4 其余场景、假设与非阻塞说明

四类完整场景结论沿用 §8.4：权威业务树与所有成功 Submission 覆盖、同 commit 多身份、两/三节点相邻 pair、accept/worker/checkpoint/result/bundle、每次读取授权、Review/Archive 并发、mapping 改绑、权限撤回与 artifact 缺失的核心设计未因本轮修订改变。新增接口位于原 materialization owner，不构成公共 contract 承载 History 编排或 owner 倒挂；未提出 native diff 能力或 Repository 写入。

**待实现验证而非新增 blocker：** public pair 从 `_Halt` 经失败转换到 diagnostic 不丢失、兼容现有调用方、事务发布/恢复/取消、真实 Repository oracle 和生产 wiring，均留实施验收。S2 前置应理解为该阶段内先交付 owner 公共面、再接 History consumer；若文档的“启动时未提供就停 S2”被解释为禁止 S2 内先交付其预算内接口，会形成排程歧义，建议同步措辞。

**非阻塞整理：** §6.6 标题仍有“F5 v3 闭合，非 pending”，宜限定为骨架，以 §10 的公开面待交付状态为准；§8.5 的 generic response-model 与唯一测试 owner 整理建议继续适用。以上不另列 blocker。

5D accepted design 继续允许 docs-only 评审；5D verified slice exit、initial-empty/零表真实旅程及实际 schema/port/version 对齐仍是实现 kickoff 硬前置。没有复审或接受主 checkout 的 5D 实现，也没有授予 5E 实现权限或签署 5E/P5 exit。

### 9.5 检查与未运行验证

已只读记录 HEAD/branch/status、候选 SHA-256、相关源码分支/公开类型/Contract，candidate `git diff --check` 通过；只追加本报告，保留历史和所有并行工作。

未运行 pytest、五包 ruff/mypy、作者临时脚本、Dolt、权威 runner、镜像构建或 Compose，不宣称实现门禁通过。本轮只读复审加报告不触发重建；当前 HEAD 容器门禁未运行。最后 image/source-tree 仍仅为 §8.6 的历史指针，未核实运行 image；正式 fresh-image 验证仍按 Plan 在授权后的阶段候选及最终候选执行。


## 10. v3.6 独立复审（2026-09-22，本轮最新结论）

### 10.1 总结论

**通过（docs-only 设计及具体执行计划）。本轮未发现阻塞性设计问题，F1–F6 均在文档层关闭。** F5 的公开诊断接口、结构事实编码、持久映射及运行证明仍须在 S2 交付；设计通过不宣称这些实现已经存在或已验收。

v3.6 将确认异常与记录观测分开：声明 A、读回 B→C 且均不等于 A，不再因此降级；缺少 content pair 的结构矛盾有原 materialization owner 的公开结构事实路径。两者都有明确 consumer、窄生产路径预算、阶段内先后顺序和代表性验收。无需为通过 S0 先实现它们，也无需扩大为通用 incident 平台。

本节为最新结论；§1–§9 原样保留，记录旧候选的审核历史。本结论不自动改写 candidate 状态、提升 Contract、授权实现/提交/推送或签署 5E/P5 slice exit。

### 10.2 固定版本、范围与隔离

| 对象 | 固定值 |
| --- | --- |
| Candidate worktree / branch | `/home/dev/gdds-5e-history-compare-docs` / `p5-5e-history-compare-docs` |
| 实际 HEAD / 文档代码基线 | `6f6a780415b3e85ec2d1e9074b1f34c4093a9c7c`，一致 |
| 作者修改范围与 status | 仅 Entry、Design、Plan 三份 candidate，均为 ` A`；实际标题版本 v3.6 |
| Entry，158 行，SHA-256 | `2bfa84bb3fba2388aa5e28b41801f9da9dcf41916ab5487acf12f759c10e4b50` |
| Design，491 行，SHA-256 | `7a675a96d7954094d1fe43daede9e39488239511b0157c069d85403c4b4de80c` |
| Plan，247 行，SHA-256 | `481ead5a829e4ddbdc3d5190e8e4ff71e3034f32e4949f648e5de3ee70e957a7` |
| 报告 checkout HEAD / branch | `8af7fb44eb5ab4a5c66ebe77dcc0d1a43352c523` / `phase1/gate-ownership-repair` |
| 追加前报告 SHA-256 | `ca5af83c05b1f3c85b9c91e1fdde6a809ded357a7f8c1ae440f7065c27ca8a04` |

主 checkout 仍有并行 5D-S2 的 execution plan/handoff、archive application/domain/control DB 与相关测试修改，未跟踪 closure.py、5D review/rereview 及本报告；本轮不覆盖、不纳入代码证据。与上一轮相比新增的 5D rereview 也不作为本轮 verified implementation 的替代。

审核沿用固定基线已读的全部强制输入：AGENTS、testing-conventions、P5 总纲、implementation-stages、Business Lifecycle、Canonical Storage、Operation Lifecycle、Contract Taxonomy、比例化 policy、5D independent acceptance/design/execution；既有 Comparison/Risk/Surface/Bundle、Repository read/native diff 与相关测试核查仍适用。本轮复核 v3.6 三份文档的变更和一致性，重读 Operation Lifecycle §3–4、materialization 失败路径/公开类型、Shared Kernel DigestRef 及现有 materialization 测试。未将作者 grep、自检或临时脚本作为独立运行通过证据。

### 10.3 实质 findings 与关闭依据

**无新增实质 finding。** 本轮关闭的是设计缺口，不是实现测试。

| 项目 | 判定与证据 |
| --- | --- |
| F1–F4/F6 | 保持 §8、§9 文档层关闭结论。双层 binding、opaque CommitId、accept DTO/generic 授权入口、JCS 身份与 5D/fresh-image 门禁均未因本轮变更被推翻。 |
| F5：诊断指纹替代内容事实 | 保持关闭。Design §6.6 使用声明侧/读回侧公开事实，明确禁止旧诊断哈希方案；History 不重算或复制私有算法。 |
| F5：B→C 被降级 | **关闭。** Design:338–343 明确两次 observed 可不同；:353–355 明确 incident 保存首次 pair，时间覆盖两次观测。基线 `repository_ref.py:331–343` 的声明摘要与读回摘要比较提供可执行来源。两次失败不再因错误值不同绕过 incident。 |
| F5：结构矛盾无 content pair 被降级 | **关闭。** Design:345–349 明确独立结构事实路径及 owner 公开面；:356 明确 catalog 缺表代表场景。基线 `repository_ref.py:389–417` 确实在同一物化过程持有 hidden table 声明与 indexed catalog，并可判定“声明存在/观测缺失”，不是依赖未提供的 Repository 新能力。 |
| F5：路径预算和阶段顺序 | **关闭（设计层）。** Plan:157、161 同时允许原 materialization owner 修改 contracts/repository_ref 两文件，覆盖 content 与结构公开事实；Design §10 将顺序明确为 S2 阶段内先交付公共面再接 consumer，无法实现才回设计。Plan:94 与 Design §8 共用三场景参数表和 integrity owner，不再要求 S2 启动前已有实现。 |

结构事实摘要与旧诊断指纹的区别在于前者对应声明/观测两侧的实际结构事实，由其语义 owner 定义；后者仅对应两次错误消息。本轮接受前者作为最小设计方向，不将其冒称已有 canonical row digest。Shared Kernel `types.py:232–253` 的 DigestRef 只规定摘要引用形状，不使不同摘要域自动等价。

### 10.4 四类完整场景复核

1. **History 读取：** 权威输入仍是 baseline/submission/review/disposition，覆盖所有成功 Submission；initial、待审/驳回/撤回和不同 Archive disposition 可读。业务 parent 与技术 parent、同 commit 多身份、排序分页和单页快照一致性维持既有设计；不读 Dolt log 构造业务树，不纳入 private candidate/失败 import/Operation marker。
2. **两/三节点 Compare：** 当前授权 scope 内解析 exact commit，accept 短事务冻结节点/规则身份；worker 按 distinct commit 物化，再冻结每表 policy，执行相邻一/两 pair、Risk/Surface/Bundle 和恢复发布。使用真实公共语义，不虚构 native 三侧 diff。只读限制业务及 Repository effect，允许 Operation/control record/artifact 持久化。
3. **并发和失败：** Review/Archive 并发不改变冻结 commit；权限撤回、mapping 改绑及跨 scope 在每次 Operation/result/bundle 读取重新判定。空 initial、同 commit、同 commit 多业务身份和缺失 artifact 的既有决定保持。v3.6 补齐已确认内容漂移及结构矛盾的 durable incident 路径，ack 不修改 Operation 终态。
4. **依赖与验收：** 5D accepted design 可支持此轮文档接受；verified 5D slice exit、initial-empty 与零表真实旅程、实际 schema/port/version 对齐仍是 5E kickoff 前置。HTTP/worker/production wiring、真实 Repository oracle、fresh image 和最终退出分别有阶段预算及门禁，不能用 mock router 或旧镜像替代。

未发现需要重建核心模型、变更主要职责或重做实施计划的问题；没有要求 5E 清偿整个 P5 历史技术债。

### 10.5 待验证事项与非阻塞建议

以下是授权后的实施验收事项，不是尚未解决的 S0 blocker：

- Materialization owner 落实 content/结构公开事实的类型、两侧含义、确定性编码和传播；结构摘要必须代表实际声明/观测，不能退回 hash(error message)。History 仅消费公开结果，不把结构摘要误解为 canonical row/snapshot/manifest digest。
- `test_history_compare_integrity.py` 按共享参数表验证 `content_stable`、`content_drifting`、`structural_no_content_pair` 及持久映射/ack；provider harness 应使生产 materialization 产生公开事实，不能只手填两个假摘要来证明 producer 已接通。复用既有 materialization 测试事实，不复制完整矩阵。
- 验证事务发布、恢复/取消、结果保护与读授权、真实 Repository 对同 policy 本地 oracle 的等价性，以及生产 factory/worker/容器旅程。5D 最终表形和 V1 ruleset 兼容仍须按 kickoff/停止条件核实。

非阻塞整理沿用 §8.5：generic Operation 的 incident 字段需在实际 response-model 中接通，可利用已有 route/history schema 预算；唯一测试 owner 表的交叉描述在实施时以一个权威矩阵落实。Entry 历史说明的“capability 零改动”应按新版 Plan 的 materialization 窄例外理解，不扩张为全 capability 修改许可。

### 10.6 检查结果与权限边界

本轮执行只读 HEAD/branch/status、摘要、公开类型/失败分支/相关测试文本与 Contract 核查；candidate `git diff --check` 通过。仅追加本报告，历史字节保留，三份候选及并行工作不变。

未运行 pytest、五包 ruff/mypy、作者临时脚本、Dolt、权威 runner、镜像构建或 Compose。**未宣称任何实现门禁通过。** 当前报告 checkout HEAD 如 §10.2；纯文档复审和报告追加不触发镜像重建。最后 image/source-tree 仍仅引用 §8.6 的历史记录（`04317788c2aa4c62fedf08b61037cd9ac973cd81`），本轮未验证 image ID；正式 fresh-image 证据必须在授权后的阶段最终候选及最终并合取得。

本轮通过仅是指定摘要版本的独立文档审核结论。没有修改 accepted Contract、candidate 状态、提交或部署，也没有自行授权下一阶段。
