# 归档业务核验补充：时间、来源链与审核收口

状态：**修订设计已独审 GO，待 Owner 实施 kickoff 确认**。2026-11-07 Owner 已确认业务方向与 §2 的选择；本页技术形态已在候选 `16472197b4` 经报告 `a5d87540e6` 独审 GO，不是已实现接口。与 BE-a／BE-d 一起收口，不重新实施 S1–S2b，不启动 S3。引用源码核查 main `a8de5e5346d2421e1237d52e8ff3f5025dc84aea`；此后纯基准文档提交不代表核验功能已落地。

关联：[Owner 决议 DC89/DC90](p6-s0-owner-decisions.md)、[BE-a](p6-be-a-design.md)、[BE-d](p6-be-d-design.md)、[联合 kickoff](p6-be-a-d-kickoff.md)、[Business Lifecycle](../contracts/business-lifecycle-and-state.md)、[P5 Archive](p5-5d-archive-design.md)。本页暂称“归档核验补充”，不占用已有 BE-b／BE-c 编号。

## 1. 现状、业务损失与边界

legacy `backend_vnext/api/formal_state_store.py::_batch_graph_payload` 有生成时间倒退、必要时间缺失与 initial 来源无法解释的阻塞；人工处置允许有理由接受对应异常。旧 `_extract_configuration_generated_at` 从 `version_manager.saved_time` 取最后一个可解析值，无时区按 UTC。legacy 仅作行为参考，不恢复其 batch aggregate、持久 candidate、ArchiveExecution 或 Python 计算双路径。

当前 vnext 的 FULL Preview 有 baseline→initial、initial→modified；Archive 有选择确认、排除 approved sibling 与工程身份例外，但**没有上述时间／来源门禁**。基线 ID 绑定不证明上传的 initial 内容来自已知现场版本。此缺口在 S2 之前已存在，不能当作 S2b 删除 Python 引入的回归，也不能用旧阶段通过证据声明已覆盖。

损失：把来源不明、可能漏传的现场改动，或生成时间倒退的数据，不经明确处置推进为业务基线。权威对象为 Submission、归档审计和 BaselineHead（A 类）；Preview 诊断及图为派生结果（C 类）。最小措施是在现有输入处理时取得小型事实，随既有业务记录冻结；归档短事务仅比较这些事实并使用现有确认机制。无新 service、独立 UID、图数据库、后台扫描、持久诊断状态机或通用规则平台。

## 2. 已确认的业务决策

1. 同 scope、当前 baseline 下存在未关闭的 PENDING Submission，阻塞归档；仅有上传／Preview 的草稿不阻塞。现有 active SubmitAttempt 门禁保留。
2. 新 APPROVE 拒绝过期基线；WITHDRAW／REJECT 保留释放出口；合法历史幂等回放不重判为新动作。BE-a 拥有这部分实现。
3. initial 可匹配当前基线、同轮次已通过提交的 initial 或 modified；允许同一起点分叉和多步链。不要求只匹配“上一份 modified”。
4. 共同未知的 initial 不因相互匹配就变成来源已知；报共享来源根因并列出受影响提交。
5. 自动解释范围限当前基线＋同基线、未关闭且已通过的提交。更旧归档历史不自动放行；本轮不建设全历史扫描，已有历史页面可供人工查阅。
6. 时间倒退、来源不明、必要生成时间缺失可由持有 `archive_submission` 的人逐项填写原因后接受；数据损坏、越权、事务冲突不可豁免。人工接受不改写诊断为“来源已证明”。
7. 时间使用 UTC；无时区值按 UTC，有 offset 的值归一为 UTC。选用 **源数据中最后一个可解析值**。最后有效值小于最大有效值时另报异常，不能自动换成最大值。
8. 已APPROVED但存在不可接受的业务问题时，增加“有理由关闭、不归档”处置；保留APPROVED历史、释放工作区以重新上传，不恢复RETURN_FOR_REVISION、不伪装为WITHDRAW（Owner随后确认，见§10）。

以下实现细化由本稿提出，仍需独审；不得把下文新字段／错误码当作现有 API。

## 3. 内容身份与可解释来源

### 3.1 一样的数据

建议直接复用同一 storage projection／ruleset／scalar mapping 下的 canonical business state digest：规范表集合、schema、行数、内容摘要共同决定相等。复用当前 `canonical_state_digest_of` 与 Rust 规范摘要，不另写一种 Python 行哈希。技术 commit ID、snapshot ID、raw SQL 字节摘要、文件时间、bundle digest 均不能替代业务内容身份。

不忽略当前规范存储保留的 `version_manager` 或其他 BROWSE_ONLY/SNAPSHOT_ONLY 表；不擅自去掉 saved_time 来促成匹配。只有现有规则明确排除的技术列／表沿原规则排除。规则或投影版本不同视为不可直接匹配，显式诊断，不能碰巧摘要字符串相同就相连。若业务要求“忽略某些额外字段仍视为相同”，须先具体列字段并修订 owning Contract，不能由实施者放宽。

### 3.2 集合与算法

输入是一个 control DB 一致快照：exact scope、当前 Head node/commit/version、当前基线内容身份，以及全部当前轮次 eligible approved Submission 的 initial/modified 内容身份。PENDING 是独立硬阻塞，不作为来源锚；REJECTED、WITHDRAWN、已关闭和跨 scope 提交均不参与。

以内容身份合并相同状态节点；每份提交是一条 initial→modified 有向边，保留独立 submission ID，不合并业务提交。以当前基线为已解释起点，重复扩展可达边直至固定点；输入排序仅决定稳定输出，不决定可达性。匹配已解释 initial 与匹配已解释 modified 都有效。相同 initial 共享来源解释；**不能使用本提交自己的 initial、同组未知 initial 或一个无已知起点的环自证合法**。

| 输入（当前基线 X） | 来源结论 |
| --- | --- |
| A:X→Y；B:Y→Z | 两者已解释，允许链 |
| A:X→Y；B:X→Z | 两者已解释，允许从共同 initial 分叉 |
| C:X→Q；A:Q→Y；B:Q→Z（任意输入顺序） | 三者已解释，A/B 共享已解释 initial Q |
| A:Q→Y；B:Q→Z，无 X 到 Q 的路径 | 共同未知来源；相同 initial 不自动放行 |
| A:Q→R；B:R→Q，无 X 到 Q/R 的路径 | 未解释环，不能循环自证 |
| A:Q→Y；B:Y→Z，无 X 到 Q 的路径 | B 有 peer 匹配，但仍受未知根 Q 影响，不能只报告 A 后声称 B 正常 |
| Q 仅存在于旧归档历史或跨项目数据 | 本轮不能自动解释 |

诊断对尚不可达子图按弱连通分量分组，每组保存稳定排序的状态身份及受影响提交；共享根／环只产生一个来源 issue，仍列出全部关联项。人工接受绑定整个组，不让调用方任意删去受影响项。分量、边或候选改变后 subject 变化，旧接受不再适用。已可达部分不进入未知组；同一组有多个未知入口时一并列出，不谎称唯一根因。

“匹配来源”与时间校验独立：内容链可解释但时间倒退时仍有时间 issue。人工接受来源异常只解除对应 issue 的门禁，不伪造来源边或抹掉原始 UNKNOWN 结论。

### 3.3 模式与第一批

- FULL：initial 取实际上传的一侧，modified 取实际上传的一侧。
- MODIFIED_ONLY：initial 明确标为 `BASELINE_REUSED`，内容身份及生成时间引用绑定基线；不能表述为用户上传 initial 已验证，也无法发现未提供的现场 initial 漏传。
- 显式 INITIAL 空基线：建议沿旧业务例外，首次来源核验和需要 baseline 时间的比较为 NOT_APPLICABLE，不能把不存在的 baseline 时间记为 0 或“通过”。FULL 若提供两侧时间，仍检查 modified 对 initial；modified 自身时间质量仍检查。首次归档后立即采用正常规则。
- 工程身份 replacement/UNVERIFIABLE 不自动豁免来源或时间问题；既有身份异常接受仍单独存在，不拿身份确认顶替来源确认。

## 4. 生成时间事实

### 4.1 提取位置与顺序

来源为 SQL 中 `version_manager.saved_time`。在 S2b 唯一 Rust 上传数据路径解析／物化时、**规范排序之前**，按 SQL 源中该表 INSERT 行的实际出现顺序扫描全部批次；最后值不是 PK 最大项、不是最后一个 Arrow 输出 batch、不是最后一个规范表行。目录 mtime、上传时间、Operation 时间、BaselineNode.created_at 不可代替。

从同一次流式扫描产出小型事实，暂定字段：`selected_time_utc`、`max_valid_time_utc`、有效／空／非法计数、last/max 源行序号、源摘要与提取规则标识、质量状态。不保存整列到 Python，不把全部时间值写日志，不重新读取整包。若当前 native 输出 seam 不足，显式修订 Rust adapter/metadata Contract；不增加 Python SQL 回退。

提取规则身份固定为 `gateway-vnext/configuration-generated-time/v1`；它是本字段的业务提取规则，不是修改Shared Kernel table scalar的语法。规则与事实摘要一起冻结；实现不得继承宿主`fromisoformat`的隐式扩展。

语法作用于SQL unquote/unescape后的单元格逻辑文本（typed DATETIME/TIMESTAMP仍先满足原table scalar边界）；仅去掉两端ASCII空格、TAB、CR、LF，即U+0020/U+0009/U+000D/U+000A。null或trim后空串为EMPTY；其他类型不能靠宿主自动转字符串成为时间。DATE-only、数字epoch、Unicode空白／数字等不在允许集。语法为：

```text
digit     = ASCII "0".."9"
date      = digit{4} "-" digit{2} "-" digit{2}
clock     = digit{2} ":" digit{2} ":" digit{2}
fraction  = "." digit{1..6}
zone      = "Z" | ("+" | "-") digit{2} ":" digit{2}
timestamp = date ("T" | U+0020) clock [fraction] [zone]
```

闭合数值范围：proleptic Gregorian年0001–9999，月01–12、日按闰年/实际月份验证；时00–23、分/秒00–59，不接受leap second、24:00或零/不完整日期。offset为00:00–14:00（14时只准00分），正负均允许，+00:00/-00:00均按零偏移；不接受无冒号offset、offset秒、命名时区、小写t/z。无zone按UTC；有offset以`UTC=local-offset`精确归一，结果越出0001–9999即INVALID，不截断、不回绕、不夹紧。fraction超过6位即INVALID，即使多余位为零也不舍入。

成功输出固定为`YYYY-MM-DDTHH:MM:SS[.fraction]Z`，fraction去尾零，全零则省略；比较使用精确微秒instant，不使用字符串顺序、float、宿主timezone/tzdb。可复用Shared Kernel日期/clock/fraction数值校验；其TIMESTAMP仍只接受既有UTC编码、DATETIME仍是civil值，本规则的空格/offset扩展只属于本字段提取。

物理顺序为version_manager表源行序，序号从1开始跨INSERT/batch连续计数（空/非法行也占序号）；selected取最后有效行，max相同时保留第一次达到max的源行序号，避免并行归并改变诊断身份。表/列缺失分别记录`TABLE_ABSENT`/`COLUMN_ABSENT`；表存在零行、全EMPTY、存在INVALID但无有效值分别记录`NO_ROWS`/`NO_VALUE`/`NO_VALID_VALUE`。没有有效值时selected/max及对应序号均null，不制造时间0；有有效值也保存EMPTY/INVALID计数。未被保存的facts对象/必需字段是完整性损坏，不是上述业务缺失。

对每一行，非EMPTY且不满足本语法/数值范围为INVALID；即使其后有有效行，也不擦除非法计数。因SQL已有非法typed scalar而解析失败的输入仍按原边界硬拒绝，人工接受不得绕过解析器；合法TEXT单元格里的非法时间文本才进入本质量诊断。

固定向量（技术定稿，后续V1在专用节点实际验证）：

| 单值或源序输入 | 预期 |
| --- | --- |
| `2026-11-07 12:00:00`、`2026-11-07T12:00:00Z` | 同为`2026-11-07T12:00:00Z` |
| 两端ASCII空格/TAB/CR/LF，中心为合法值 | trim后有效；内部TAB、两个空格分隔、NBSP均INVALID |
| `2026-11-07T00:30:00+01:00` | `2026-11-06T23:30:00Z`，允许跨日 |
| `2026-11-07T12:00:00.120000-00:00` | `2026-11-07T12:00:00.12Z` |
| `2026-11-07T00:00:00+14:00` | `2026-11-06T10:00:00Z`；+14:01/+15:00 INVALID |
| `2024-02-29T00:00:00` / `2026-02-29T00:00:00` | 前者有效，后者INVALID |
| `2026-11-07`、`2026-11-07t12:00:00z`、`.1234567`或`.0000000` fraction、秒60、24:00:00 | INVALID，不补零/舍入/扩大语法 |
| `0001-01-01T00:00:00Z` / `9999-12-31T23:59:59.999999Z` | 两端边界有效 |
| `0001-01-01T00:00:00+00:01` / `9999-12-31T23:59:59-00:01` | UTC结果越界，INVALID |
| 有效12:00、非法date-only、有效11:00（同日），分布于不同INSERT/batch | selected=11:00@3，max=12:00@1，valid2/invalid1，质量与LAST_NOT_MAX两项均存在 |
| 12:00Z、13:00+01:00（同日） | 相等instant，selected@2/max@1，不报LAST_NOT_MAX |

向量另包含null、空串、全空、全非法、无表/列/行及合法值后的七位fraction；最后一项INVALID不能抢占前一有效selected。线程数、Arrow切块及规范排序改变不得改变提取结果。

| 条件 | 目标结果 |
| --- | --- |
| 至少一个有效值 | selected = 源序最后有效值，max = 全部有效值最大值 |
| selected < max | `GENERATION_TIME_LAST_NOT_MAX`，保留 selected；不得改成 max |
| 全部有效值相等 | 正常，相等不算倒退 |
| 表／列缺失、无有效值 | 显式 missing 状态，归档产生必要时间缺失 issue |
| 存在非空不可解析值，但仍有有效值 | 保留最后有效值及非法计数；产生 `GENERATION_TIME_INVALID_VALUES`质量issue，可逐项人工接受 |

本轮不额外要求每相邻两行时间都单调；Owner 确认的是“最后有效值不是最大值”必须可见。各类质量问题合成每侧一个诊断事实，不能无限按行生成 issue。

### 4.2 时间比较

仅在两个被比较值均有效时计算严格 `<`，相等允许。缺值时显示对应缺失 issue，不能把无法比较记为时间顺序通过。

- modified < initial：`TIME_ABNORMAL_MODIFIED`，relation=`MODIFIED_BEFORE_INITIAL`。
- modified < baseline：`TIME_ABNORMAL_MODIFIED`，relation=`MODIFIED_BEFORE_BASELINE`。
- initial < baseline：`TIME_ABNORMAL_INITIAL`，relation=`INITIAL_BEFORE_BASELINE`。

同一提交的 modified 两个倒退关系可合并为一个 issue，但受影响 relations 必须全部绑定、展示。时间质量、来源不明与倒退分别诊断，不因一个接受而自动覆盖另一类。

baseline来自已归档Submission时，其原有INVALID/LAST_NOT_MAX与接受记录只显示历史来源，不逐轮重开相同旧issue。若本轮需要baseline时间但它确实无有效值，则产生一项新的`BASELINE_TIME_UNAVAILABLE`，绑定当前Head和受影响候选集合，解释“本轮无法完成baseline时间比较”；该问题可有理由接受，但比较结果仍为NOT_COMPARABLE。INITIAL空基线按§3.3不适用，不产生此项。MODIFIED_ONLY复用baseline侧时同一缺失只归此全局项，不为每个initial重复生成质量issue。

## 5. 数据生命周期与权威绑定

| 环节 | 目标行为及 owner |
| --- | --- |
| Rust SQL 解析／上传物化 | 同次扫描提取源序时间事实，复用规范摘要；遵守取消、deadline、N/M 和 typed error |
| Preview materialize checkpoint | 冻结 initial/modified 小型事实、规则身份、source artifact 绑定；FULL 初始内容 digest 补进既有 canonical metadata。重启从 checkpoint 恢复，不按当前 SQL 或新时间策略重算旧事实 |
| Preview READY | 与现有 LeaseSession/事务发布完整结果；HTTP 查询可展示本提交时间诊断，尚不能宣称同轮次来源检查最终通过 |
| AcceptSubmit T1 | 由服务器从绑定 Preview 复制 facts 到 immutable Attempt；caller 不提供“事实已通过”的布尔值。校验 source/Preview/baseline 与 facts digest，不需要读取全部 peer 或阻塞纯提交 |
| Submit finalize | Attempt→Submission 同事务复制并校验，保留唯一权威来源；重启、重放不丢失也不二次修改 |
| Archive preview／审计 append／Start | 从 durable Submission 与 baseline 来源读取 facts，派生图与问题；不依赖临时 Preview artifact 仍存在、不执行 SQL/Dolt/全表扫描 |
| Archive commit | existing Plan/Result 冻结核验输入身份、规则身份、问题及接受引用；新 baseline 由 selected Submission 取得 modified 内容/时间事实，和 Head/CAS 原子绑定 |
| 后续轮次 | 当前 baseline 是已成立的业务锚；上轮人工接受事实留在 ArchiveResult 供审计，不伪称上轮数据自然可达，也不要求每轮重新接受相同历史事实 |

小型事实优先嵌入现有 Preview/Attempt/Submission 序列化字段与 Plan frozen input；不为它创建独立资源、receipt 状态机或重复的 Baseline 时间权威字段。基线可通过 `source_submission_id` 取得事实，INITIAL 空节点为显式无来源；引用缺失／不一致是完整性错误。schema 直接更新唯一基线，不迁移、双读或回填旧 DB。

时间事实不改变既有业务内容哈希算法。其源绑定与核验版本进入新的 facts digest，并纳入 candidate／selection／anomaly 接受身份，不能把不同时间事实当成同一已确认候选。需要修订的 checkpoint、DTO、candidate digest 及 golden 逐项列入实施清单；不以“无兼容负担”绕过冻结产物校验。

## 6. 归档受理、审计与 HTTP

### 6.1 硬阻塞

权限／scope、active Attempt、当前基线与候选变化、PENDING、引用损坏、facts 缺字段或绑定错误、资源上限、CAS 都不可人工豁免。区分“输入明确没有时间”的业务事实与“程序漏保存时间事实”的损坏：前者可接受缺失，后者完整性错误。

### 6.2 可接受异常与现有机制复用

保留选择确认、逐 sibling 排除、选中项工程身份例外。新增 issue 覆盖本轮全部 approved 候选的来源与时间，不只检查选中项；归档同时关闭其余项，不能通过换选中项隐藏同轮问题。若不愿接受，可按§10先显式关闭有问题的提交，再重新预览余下集合；这不是静默忽略。

建议在现有 Archive AnomalyResolution 增加明确 subject/action：来源异常、时间倒退／记录顺序异常、时间质量缺失／非法值三类接受。不做 caller 自由输入 issue 或通用“忽略所有”。每项要求 `archive_submission`、非空 reason、当前 expected sequence；可撤销，启动时只认最新肯定事件。无新增双人制、TTL 或通用审批引擎。

subject 绑定 scope、当前 Head/version、完整 candidate-set、核验规则版本、issue code、relations／group、受影响 submission/facts identities；新增候选、不同选择相关的处置、事实或规则变化均按对应 subject 重新确认。Start 引用集合必须精确覆盖当前需要的全部确认，不允许缺失、多余、重复、过期。合法同键 Start replay 在当前鉴权之后仍返回旧成功结果，不重跑新门禁。

来源 issue 的 `detected_status=UNEXPLAINED` 与 `resolution_status=ACCEPTED` 分开；UI 可以说“来源未解释，已由某人说明并接受”，不能改成“来源匹配”。时间 issue 同理，原因不修改上传时间事实。

### 6.3 API 与前端消费者

复用 archive candidates／preview／audit／start 路由。预览新增结构化 `pending_review` 阻塞摘要和业务诊断：code、受影响 submission IDs、side/relation、时间值或缺失状态、匹配来源引用、subject、最新接受状态；不返回 SQL 行、私有路径或跨 scope 数据。仅当前归档权限能读整个轮次；self-only 权限不能借此读他人提交。

新硬阻塞建议 `ARCHIVE_PENDING_REVIEW`（409）；过期基线 APPROVE 沿用／明确 `BASELINE_VERSION_CONFLICT`（409）；可接受问题未解决继续 `ARCHIVE_ANOMALY_UNRESOLVED`（409）；facts 损坏沿现有 `ARCHIVE_INTEGRITY_FAILURE`（503）。错误映射、OpenAPI 和固定 DTO 必须在本节实施 kickoff 前与实际 adapter 对齐。

FE3 需接收的说明：旧“已通过且基线过期，找管理员”不再是正常出口；待审核在归档前阻塞。增加三类业务异常展示、原因输入、撤销与过期刷新。当前 FE3 不是这些新增界面的实现授权；前端设计由其 owner 更新，后端不直接改前端文档或源码。BE-d 仅传输既有 bundle，不在 tar 内临时注入归档图；归档动态诊断从上述 API 读取。

## 7. 事务、容量与资源

- 在同一个 `BEGIN IMMEDIATE` 内重查 Head、active attempts、PENDING、candidate-set、facts、诊断和接受引用，再做既有 Plan/Result/Head/Workspace 原子提交。不把只读预览结果当权威，不在事务内物化／网络读取。
- Approve/归档任一先完成：前者改变候选，旧预览需刷新；后者使旧 baseline 的新 approve 被拒绝。Submit 先受理则 active gate 阻塞；归档先完成则旧 Preview 的新 Submit 被既有 baseline gate 拒绝。Finalize 与门禁不得有释放 attempt 后尚未出现 PENDING 的可见空隙。
- 图规模至多当前候选 200 项，状态节点至多 401；按字典集合与固定点处理，无全历史搜索。PENDING 只做有界计数／列表，超限返回范围错误，不分页冻结部分轮次。
- 候选上限保持200、Start body保持256KiB；**选择确认上限1，异常引用上限1601**，替换旧两个字段共用200的限制。精确issue合并/数量与静态请求预算见§7.1，不留给实施者猜测、不合并不同issue来塞入旧限制。
- 时间扫描增量内存有界，不以候选数保持所有 Parquet FD／mmap。沿 S2b32/8/M24、N1；无需因本设计重跑完整性能基准，实际新增路径计数和资源边界必须验证。

### 7.1 异常上界与请求预算（B2技术定稿）

N为本轮eligible approved候选数，1≤N≤200。固定issue owner与分组如下；诊断flags不是额外的独立接受，确定后的issue必须分别接受：

| issue类别 | 分组与去重 | 上界 |
| --- | --- | --- |
| 源时间质量 | 每候选每个实际上传侧最多一项：无有效值为必要时间缺失（附MISSING原因及非法计数），否则有非法值为INVALID_VALUES；两者互斥，EMPTY伴随有效值只计数 | 2N |
| 源时间顺序 | 每候选每个实际上传侧selected<max单独一项，不并入质量接受；同一冻结产物被多候选引用也按候选绑定 | 2N |
| 跨侧时间倒退 | 每候选modified一项，relations集合含对initial/baseline的所有已成立关系；initial对baseline另项。不是两种不同issue共享一个接受 | 2N |
| initial来源未解释 | 尚不可达子图的每个非空分量一项，至少含一份候选；整组成员/边及全部影响绑定 | N |
| approved sibling排除 | 每未选中候选一项 | N−1 |
| 选中项工程身份例外 | 既有聚合的身份异常一项 | 1 |
| 本轮baseline时间不可比较 | §4.2的BASELINE_TIME_UNAVAILABLE全局项，不重复旧历史质量接受 | 1 |
| **合计** | 保守结构上界，不要求所有类别同时可达 | **8N+1≤1601** |

投影/ruleset身份矛盾、事实损坏、scope/版本等不可豁免项不计入anomaly接受，直接hard blocker；不额外派生不在表中的自由issue。超过1601或算法产生重复/未知类别应失败，不能截断、分页接受或静默扩容；未来新增issue类别须重算此界并修订Contract。

目标常量拆为`ARCHIVE_MAX_CONFIRMATION_REFS=1`、`ARCHIVE_MAX_ANOMALY_REFS=8*ARCHIVE_MAX_CANDIDATES+1`；同步domain/application校验、HTTP schema/OpenAPI、fingerprint/replay校验与所有consumer，删除两字段共用`ARCHIVE_MAX_AUDIT_REFS`的旧路径。Start在形状校验后仍要求exact issue集合与最新sequence；数组预算不是允许填充无关接受。候选N<200时也必须匹配当次实际集合，不按1601配额填充。

Start每引用仅有`subject_digest`（固定71字节ASCII）和`sequence`（I-JSON非负safe整数，最多16位）；reason、target IDs、relations、诊断正文只在独立append和服务端派生/保存的subject中，不重复塞进Start。来源组append请求只传group subject_digest及Head/candidate-set/selected等已有绑定、action/reason/expected_sequence；服务端同事务重算并冻结完整成员，不允许caller传可删减的affected列表，更不能要求200个最大长度ID的转义数组占满请求。

上述sequence/Head version的0..9007199254740991范围同时约束HTTP与application入口；接受append递增超界时明确拒绝，不创建日后无法通过HTTP引用的事件、不回绕。已有成功结果的合法replay仍按原事实返回。引用数字不允许指数或字符串变体突破预算。

静态JSON预算：1601 anomaly refs＋1 confirmation，每项紧凑对象120字节（再计数组逗号）；2个255 UTF-8 bytes ID按最保守ASCII控制字符`\u0001`转义计各1530字节，两个digest固定71字节、Head version取`9007199254740991`，含全部现有Start字段名/括号后共**197,265 bytes**，距离262,144 bytes尚余**64,879 bytes**。该计算使用标准JSON序列化的协议形状，无产品调用/测试。前端发送紧凑UTF-8 JSON；任意增加的whitespace仍受实际body字节上限，不承诺无限排版的请求可接受。后续若新增Start字段必须更新预算，不能侵占余量而不记录。

这明确支持审核B2的正常来源场景：200个FULL、initial有时间、每个modified缺时间，199排除＋200质量＝399 anomaly refs可接受并Start，无需为了旧200限制关闭有效提交。实施阶段小型边界向量验证399、1601形状上限/1602拒绝、exact集合、256KiB字节门禁及200候选规则推导上界；不生成大规模真实数据、不做性能测量。1601是保守协议预算，不要求构造所有类别同时成立的伪业务样本。

## 8. 分步实施与验证建议（尚未启动）

| 小节 | 改动／出口 | 定向验证 owner |
| --- | --- | --- |
| A1 BE-a | 原权限/DTO/旧动作删除＋pending归档门禁＋过期approve拒绝 | review HTTP owner 权限/回放；archive queries/transactions/concurrency 门禁、finalize竞争和回滚；不重复全矩阵 Compose |
| V1 时间与内容事实 | Rust 源序提取、Preview/checkpoint、T1/Submission冻结 | native固定向量：跨INSERT/Arrow批次、规范排序不同、UTC/offset、空/非法、最后非最大；既有Preview/Submit owner验证恢复、绑定、失败无部分写 |
| V2 来源和时间规则 | 纯派生诊断、复用audit、Start事务、有理由关闭出口 | 一个纯规则 owner 参数化图/时间表；audit owner接受/撤销/过期；archive transaction owner新门禁、关闭及原子效果 |
| D BE-d | 最终closure一对一tar | 见BE-d设计；可在V设计收口时独立准备，实际产品顺序在联合kickoff确认 |
| 联合最终候选 | 前后端消费接口固定、必要runner/容器/真实数据 | 04实际受影响包及当前候选Compose，按闭包规则沿用未变包；05 fresh t1含FULL/MODIFIED_ONLY与归档、完整tar；异常用小型合成真实wiring补足 |

日常 native/focused/Contract 在06或05（按用途与现有占用）；真实旅程默认05，不把S2b E的06一次性授权延长到本任务。04最终候选才跑权威门禁；已运行的Compose不单独重复。frontend07调试、04其独立门禁由前端owner安排。

真实 t1 不一定包含倒退、未知来源或足够同轮提交；不能以自然数据未触发异常声称覆盖。固定向量至少包括：上述六个图例及输入排列不变；最后非最大；跨侧三关系／相等；空基线；缺失与损坏区别；MODIFIED_ONLY限制；replacement不豁免；无权限与scope隔离；人工接受不伪造PASS；新增peer后旧接受失效；合法历史replay；检查失败无Head/释放副作用；容量超限不截断。

不重做S1a/S1b，不恢复参照解析器，不全量生成合成基准，不改原冻结测量worktree/镜像/输入/卷。最终真实数据范围和角色仍需在修订kickoff明确；新实施/独审角色不能沿用S2b已结束角色授权。

## 9. 实施前收口清单

Owner来源范围、共同未知根、人工接受、时间口径及后续发现的关闭出口均已答复，没有继续阻塞本文编写的问题。以下技术细化由设计/独审解决，超出已确认语义才再交Owner：

- 源时间语法/范围/版本/非法值细则已在§4.1定稿，native输出seam及固定向量按此实施；不把SQL源序替换为规范行序。
- canonical身份复用的全表/规则绑定固定向量；不静默排除额外字段。
- 初始空基线NOT_APPLICABLE、时间事实在baseline来源中的持久读取与TTL隔离。
- 新fields/schema/checkpoint/digest/OpenAPI的精确清单按实施小节固定；审计引用及Start最坏形状已在§7.1定稿，不再是Owner待决容量项。
- 更新Business Lifecycle、P5-5C/5D、Snapshot Materialization、Canonical/Preview/Submit Contract的目标修订；实现同步正文，历史决议与审核报告不改写。
- 独审本轮修订设计；旧BE-a kickoff审核不覆盖新增门禁和本业务链路。仅文档编辑不宣称产品验证或GO，不以旧S2b退出冒新功能完成。

## 10. 有理由关闭、不归档（Owner已确认方向，技术草案）

### 10.1 业务出口

新核验可能在APPROVED后阻塞归档；没有此出口时，操作者只能接受不愿接受的异常或永久占用工作区。新增显式`CLOSE_NOT_ARCHIVED`命令，作用于scope内仍占用工作区、未终局处置的APPROVED Submission。无需伪造一个异常才能关闭；必须填写非空原因并确认“保留历史、释放工作区、内容未成为基线”。PENDING继续走REJECT/WITHDRAW，不提供绕过审核的关闭。

关闭不修改Review projection/status/事件序列，不撤销历史APPROVE，不新建BaselineNode、不移动Head/Repository main、不删除Submission/Upload/Repository commit。关闭不可撤销；重提必须新上传、新Preview、新Submission，不能恢复旧工作区generation的指针。已经选为基线或被归档关闭的对象拒绝新的关闭动作。

建议权限复用`archive_submission`，不让reviewer-only或self-only自动获得；reason与actor/time被冻结。UI要明确区分“审核通过”与“已关闭、未归档”，不能只显示APPROVED导致误认为仍可归档。已有过期baseline的APPROVED若仍有合法占用也允许此出口，不要求它重新获得普通归档候选资格。

关闭单个提交后，从余下候选重新派生来源图；它的initial/modified不再充当本轮自动解释来源。可能使下游重新变为UNKNOWN，必须展示、重新接受或分别关闭，不自动级联关闭。原candidate-set与依赖它的确认随之过期。

### 10.2 一个终局处置事实，不伪造ArchiveResult

当前`archive_disposition_records`以submission_id为唯一键，所有行强制引用ArchiveResult。不能为单独关闭伪造ArchiveResult或基线。

建议将该表及领域类型直接推广/更名为`submission_disposition_records`／`SubmissionDisposition`（无兼容包袱，旧类型/字段不双轨保留），继续以submission_id保证只能终局处置一次：

- `disposition`仍区分`ARCHIVED_BASELINE`与`CLOSED_NOT_ARCHIVED`。
- `source_kind=ARCHIVE`时必须引用真实result_id，actor/time沿既有Result/Plan权威来源；一个result只准一个ARCHIVED_BASELINE。
- `source_kind=MANUAL_CLOSE`时只允许CLOSED_NOT_ARCHIVED、result_id必须null，记录当前scope、actor、UTC时间、reason、idempotency key/fingerprint、被关闭Submission/review版本和工作区绑定；该行本身即不可变成功审计事实，不另建同义关闭记录表。
- CHECK/FK约束来源二选一，不能出现既无来源又算closed、同时属于两种来源或manual行冒充基线。

MANUAL_CLOSE幂等键按exact scope与CLOSE命令命名空间唯一，不与START/CONFIRMATION/RESOLUTION混用；原归档来源行的manual字段必须为空。表名调整不是新增一份并行closedness权威，旧表/旧读路径同步移除。

Candidate查询、review closedness、History查询/DTO、ArchiveResult装配等所有消费者统一改读新处置事实；不保留“只查ArchiveResult所以看不见manual关闭”的旁路。Review历史状态不变；History/Review facts提供处置来源与关闭摘要，self-only只读自己的既有允许范围，不能借新DTO扩权。

### 10.3 命令、事务与回放

建议公开`POST /v1/submissions/{submission_id}/closure`，命令固定为CLOSE_NOT_ARCHIVED，不接受自由action。输入为idempotency key、expected_review_version、expected当前baseline node/head_version和非空reason；Submission本身不可变，服务器读取并冻结其facts和Workspace精确占用绑定。具体路由/schema名在独审收口，不当作现有API。

同步短写事务：当前认证/permission/scope→同键成功结果校验与回放→fresh Head/version→APPROVED/未处置/精确Workspace generation/upload/preview/occupancy→插入唯一终局处置并CAS释放Workspace、清当前输入与Preview、version+1→提交。保持OPEN及generation，沿现有释放语义；不在此事务查Dolt或读产物。

无需当前candidate-set PASS、无需先接受异常、也不要求无其他Workspace active Attempt：否则可能无法解除正在处理的阻塞。只要求被关闭Workspace确实由该Submission占用；不误释放后继Attempt。命令只读目标及当前Head，不必须加载全图，所以候选/异常数量超限也不会堵死关闭出口。调用前可查看有界归档预览的影响提示，执行后必须刷新。

same key/same fingerprint在当前鉴权后返回原成功；不同内容冲突。新key重复关闭409，不执行第二次释放；已归档对象返回已终局冲突。响应丢失后可安全重放，旧预期Head不阻塞原成功回放。reason、actor、时间不可通过重放改写。

**2026-11-07 实施前技术澄清：MANUAL_CLOSE 为 actor-independent 的终局业务命令。** 幂等命名空间为 exact repository/device/project scope＋CLOSE＋key，actor 不进入命名空间或 request fingerprint。fingerprint 绑定命令、exact scope、目标 submission、请求中的 expected_review_version、expected baseline node/head_version 及 reason；不把当前 caller、执行时间或重放时的最新 Head/Workspace 状态加入请求身份。同 scope 的另一位当前具有 `archive_submission` 权限且通过目标授权的 actor，以同 key/payload 请求时回放原成功，返回并保留首次关闭者、时间和原因，不记为第二位 actor 又关闭或签署了一次；不同目标或 payload 返回幂等冲突，不返回原结果内容。当前鉴权、scope 与目标授权仍在幂等查找/回放之前，原成功不能绕过权限撤销或跨 scope 边界。

该选择沿用 [Archive Start §5.2](p5-5d-archive-design.md#52-idempotency-details-and-errors-after-commit) 的业务命令语义，亦与 [BE-a §4](p6-be-a-design.md) 的成功命令回放方向一致；不改变 confirmation/resolution 审计 append 的 actor-bound fingerprint，因为后者记录个人接受声明。恢复后仍校验所存关闭事实与原请求的绑定及完整性，不以当前状态重算旧请求、不覆盖原 actor，也不将持久记录损坏伪装成普通冲突。此项是对 §10.2/§10.3 已定命名空间和不可变关闭审计的技术细化，不新增 Owner 业务决议；由 V2 独审核对实现与证据。

Start与close：close先完成则Start旧集合拒绝；Start先完成则close见已处置拒绝。两个close只能一条处置/一次释放。late失败回滚处置和Workspace全部写入。目标可属于旧baseline，但请求对当前Head的预期仍要匹配，防止与刚发生的归档交错被静默接受。

### 10.4 验收和范围影响

增加公开权限/404隔离/原成功replay测试；事务owner验证保留APPROVED与历史、Head/Repository不变、唯一终局处置和精确释放、crash后重放及与Start竞争；History owner验证两种处置来源和旧archive查询正常；来源纯规则owner验证移除桥接提交后下游UNKNOWN。一个真实wiring异常拒绝→有理由关闭→新上传重提→归档路径，不把所有内部故障点搬进Compose。

上述公开权限/replay owner 同时覆盖两位当前授权 actor 的同 key/payload 回放、首次 actor/time/reason 保持、权限撤销后拒绝，以及同 key 不同目标/reason/expected version 的冲突；复用事务 owner 的唯一处置/精确释放断言，不另复制完整 Compose 矩阵。

本节影响control DB基线schema、Submission/Archive closedness、History和Review DTO及前端动作，明显超出原BE-a审核；联合kickoff和前端交接必须列明。它属于归档核验的闭环依赖，V2不能在没有该出口时声明完成。
