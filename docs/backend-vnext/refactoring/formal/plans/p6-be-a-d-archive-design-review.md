# BE-a / BE-d 与归档业务核验：独立设计审核

日期：2026-11-07。审核对象为已提交候选 **`6995fe46a893f21d3dcb68ed6e1f17ebc74e6dd9`**，父提交 **`a8de5e5346d2421e1237d52e8ff3f5025dc84aea`**。本报告只评价设计，不是产品实施或功能验收。

结论：**需修订后复审**。DC89/DC90 已确认的业务方向没有发现新的业务冲突；事务、权威绑定及最小机制总体可行。B1/B2 是实施前须在设计中定下的两项技术选择；N1 是已存在的前端 consumer 差异，须写清交接依赖。不能把原 BE-a kickoff 审核或 S2b exit 当成本轮新增能力的 GO。

## 1. 审核范围与方法

只读 detached worktree：`/home/dev/gdds-reviews/p6-be-a-d-archive-6995fe46`，固定候选，按 AGENTS 链接主仓库 `legacy/`，审核期间不修改设计、产品或测试。范围为父提交到候选的七份设计文档：

- [BE-a](p6-be-a-design.md)、[BE-d](p6-be-d-design.md)、[归档业务核验](p6-archive-business-validation-design.md)、[联合 kickoff](p6-be-a-d-kickoff.md)；
- [Owner 决议](p6-s0-owner-decisions.md)新增 DC89/DC90、[执行计划](p6-execution-plan.md)、[总体设计](p6-design.md)。

对照了实际 Rust parser/materialization、Preview/checkpoint、Submit T1/finalize、Review/Archive 事务、control DB schema/查询、History 两种读取路径、生产 bundle reader/HTTP、bundle assembler、前端 tar consumer 与 legacy 参考。遵守 AGENTS、testing-conventions、比例化保障政策；本轮不运行测试、编译、容器或真实数据，不占测试节点、不接管原基准、不创建子 agent、不推送、不改 tag。

以下行号均指候选 `6995fe46`。代码定位以仓库根为基准。

## 2. 阻塞项

### B1：生成时间的有效语法仍未闭合，会改变“最后有效值”及归档事实

设计定位：[业务设计 §4.1](p6-archive-business-validation-design.md#41-提取位置与顺序)，L69–79；§9 L162。

稿件正确要求源序、UTC、最后有效值、保留 max 和规则标识，但“复用 Shared Kernel 允许的时间值范围／有时区 ISO 值”还不是确定的提取语法。当前 [Shared Canonical Encoding §3](../contracts/shared-canonical-encoding.md#3-typed-scalar-frame) L73 区分 civil DATETIME 与已解析 UTC TIMESTAMP；`vnext/rust/gateway-shared-kernel/src/scalar.rs` L645–670 的 TIMESTAMP 只接受 `T…Z`，不解析 offset。legacy `capabilities/snapshot_materialization/materializer.py` L1764–1783 则 trim 后调用 `fromisoformat`，可接受的集合更宽，不能作为目标语法。

例如一个有效时间后跟 `2026-11-07 12:00:00`、date-only 或七位 fraction：后项算有效还是 INVALID，直接改变 selected、last/max 序号和倒退结论。offset 归一跨日期／合法年份边界的结果也须确定。这不是宿主语言实现细节，而是要进入 immutable Submission 和 Baseline 的业务事实。

最小修订：在设计中给一个闭合提取 grammar、精度/日期/offset 范围、空白与 `T`/空格分隔及 date-only 处理，明确合法文本归一后的 UTC 表示、缺失原因/非法状态和提取规则身份；列小型固定向量。可复用 Shared Kernel 日期/秒/最多六位 fraction 的数值校验，但不改变其现有 table scalar 语义，不继承 `fromisoformat` 的隐式扩展。typed scalar 原边界失败继续硬拒绝；合法 TEXT 单元格中不满足时间 grammar 的值才按新质量规则处理。

### B2：新增逐项异常后的引用容量尚未作出可执行选择

设计定位：[业务设计 §6.2](p6-archive-business-validation-design.md#62-可接受异常与现有机制复用)，L118–122；§7 L138–139；[联合 kickoff §5](p6-be-a-d-kickoff.md#5-确认记录与当前缺口)，L87。

稿件已识别此风险，但不是仅在“最坏全异常”时才可能发生。一个完全正常的来源图即可证明：200 个 FULL approved 提交，initial 均等当前有有效时间的 baseline，每个 modified 明确缺时间；选择其中一个时，必须有 **199 份 sibling 排除 + 200 份必要时间缺失接受 = 399 anomaly refs**。现有 `application/archive/contracts.py` L22–24、L380–383 和 `http/schemas/archive.py` L150–153 只允许该字段 200 项，因此这些可接受异常全部处理后仍不能 Start。

L139 的 fail-closed 范围错误和 §10 的关闭退路可以防止漏验，却尚未回答最终支持多少候选／多少 issue、哪种有界形状可以归档。若沿用 200 refs，这是一次明确的可接受异常容量限制，应在 kickoff 前定稿；若目标仍为 200 候选可逐项接受，就需同步确定更大的有界引用预算。不能靠合并不同异常的接受、丢引用或分页冻结解决。

最小修订：先定每侧质量 issue 与时间关系 issue 的合并规则，给出至多 200 候选时来源分量、时间质量/倒退、原排除/身份异常的数量上界；在设计中选择 refs 上限并静态核对 256 KiB Start body。reason 在各自 append 请求中，不应重复塞进 Start。若选择保留较小容量，明确精确的范围错误与有理由关闭后的恢复路径及对外容量说明。只需静态预算和后续小型边界向量，不要求生成大规模真实数据或跑性能基准。

## 3. 非阻塞交接项

### N1：现有前端 PAX parser 按字符数解释 UTF-8 字节长度

设计定位：[BE-d §2–§3](p6-be-d-design.md#2-成员对应owner已确认)，L23、L31；§5 L49。

`frontend/src/features/bundle/posix-tar.ts` L199–215 先把整个 PAX body 解码为 JS string，再用 `text.length`、`slice` 和字符 offset 处理 PAX record length；POSIX PAX length 是 UTF-8 字节数。合法 `12 path=中\n` 是 12 bytes、10 个 JS code units，L209 的界限判断即会拒绝。该结论来自静态读取，未运行前端测试。Shared canonical identifier 允许 Unicode，Preview 使用表名形成逻辑路径（`application/preview_jobs.py` L1651、L1663–1669），所以多字节长路径属于真实可达形状。现有 `posix-tar.test.ts` L16–21 的长路径检查没有覆盖此差异。

后端仍须编码标准 PAX byte length，保持合法表名和成员完整性。建议 BE-d 明列 ASCII、中文及非 BMP 的长路径向量，并将前端 owner 修正 consumer、用同一实际 tar 对接列为 FE3 解除依赖的条件；后端设计/实施不直接修改前端源码。此项不要求现在启动前端实现，但不宜把“现有 FE parser 已支持长路径”扩称为 UTF-8 PAX 互通已成立。

## 4. 已核对的设计边界

| 边界 | 审核结果与后续唯一验证落点 |
| --- | --- |
| 内容身份 | `canonical_state_digest_of`（snapshot_materialization/contracts.py L599–622）对传入的全部规范表按名称稳定排序，包含 business schema、row count、raw content digest；没有在此丢掉 BROWSE_ONLY/SNAPSHOT_ONLY。业务设计 L32–34 要求复用完整规范表并另绑定 projection/ruleset/scalar，方向正确。FULL initial 的新 digest 必须从同样的规范描述符计算；不能拿 comparison digest、raw SQL 或 commit 代替。规范 composite 表同样属于该集合。 |
| 源序提取 | Rust `table_access/mod.rs` L6–17 已保留源序合并语义，源序提取应落在业务规范排序前；不能从 IPC/PK 排序回推。L67–71 的小型事实与预算方向可行；B1 收口后由 native 向量覆盖跨 INSERT/批次、线程/分块不变及 LAST_NOT_MAX。 |
| 冻结、恢复、取消 | 设计 L98–108 覆盖 materialize checkpoint→READY→T1→Submission→Plan/Result/基线来源，区分输入缺时间与漏保存 facts。现有 Preview 通过 LeaseSession 和 `_atomic_publish_preview` 发布，旧 generation/基线漂移进入 SUPERSEDED；新增 facts 须作为既有发布的一部分，不另开写路径。新载荷必需字段、digest/job contract 和 golden 在 V1 同步；取消/失租不得发布部分事实。 |
| 来源图 | L38–54 从当前 baseline 做可达固定点，不依赖输入序；分叉、链、共同未知 Q、无锚环和未知根向下游传播均有正确示例。未知子图分组绑定完整影响集合，人工接受不插入来源边、不改变 detected status。纯规则 owner 参数化输入排列即可，不增加持久图系统。 |
| MODIFIED_ONLY / INITIAL / replacement | L58–61 明示 BASELINE_REUSED 的可证明边界，只有明确 INITIAL 空基线才允许相应 NOT_APPLICABLE；FULL 两侧和 modified 自身质量仍检查。replacement/UNVERIFIABLE 不覆盖来源/时间。基线事实从 source_submission_id 读取、引用损坏硬拒绝，避免把 Preview TTL 当归档事实生命周期。 |
| PENDING / APPROVE / replay | BE-a §9 让同 scope/current baseline 的 PENDING 成为硬阻塞，同时保留 active Attempt。fresh APPROVE 在写事务检查 node/commit，REJECT/WITHDRAW 保留出口；当前授权后的成功 replay 在 fresh 门禁之前返回，方向正确。现有 finalize 同事务 seed Review、切 occupancy 并移除 Repository occupancy（finalize_transaction.py L100–125），新增 pending gate 不应制造中间可见空隙。 |
| 人工接受与 Start | 设计 L114–137 区分硬阻塞与可接受异常，全部 approved 候选参与；subject 绑定 Head、集合、rules/facts、relations/group，最新肯定事件及 exact refs 在 BEGIN IMMEDIATE 内复核。需把当前单 target 的 audit/DTO 改成能表达整个来源组的目标形态；这是既有审计 owner 的扩展，不建立平行接受系统。B2 定稿后由 audit/transaction owner 覆盖撤销、集合变化、冲突与失败无副作用。 |
| 有理由关闭 | §10 的单一 submission disposition PK、ARCHIVE/MANUAL_CLOSE 二选一、独立 CLOSE 幂等命名空间和精确 occupancy CAS 可实现一份终局事实。保留 APPROVED，当前 Head 预期与合法旧 baseline 目标可并存，Start/close 同写事务串行。成功 replay 不要求占用仍在，新 key 已关闭冲突；不要求其他 Workspace 无 Attempt，也不让集合超限堵住关闭。 |
| 关闭 consumers | 当前 candidate SQL（sqlite_submission.py L195）、Review closedness（database.py L290–293）、Archive result assembly（sqlite_archive.py L442–461）、History 分页 SQL（sqlite_history.py L283–284）及完整 snapshot SQL（L371–372）均读取旧 disposition。§10.2 明确要求统一替换，不能只改 mutation。HistoryNode/Page、ReviewFactsResponse 当前没有来源/关闭摘要，V2 要同步所声明的新 DTO；self-only 仍仅能读本人。移除桥接提交后其他项回 UNKNOWN 的规则已覆盖。 |
| tar closure / 完整性 | 最终 closure 每 entry 一个普通文件、metadata 在前、无下载层去重，与 assembler 最终路径去重和前端 closure 顺序一致。preflight 必须实际发生于 StreamingResponse 之前，准备结果带 bundle digest/准确 length；metadata 16 MiB 的现有上限与前端一致。逻辑摘要与 raw artifact SHA 按各自 Contract 校验，不能把 tar 容器字节哈希当业务 digest。 |
| tar 生命周期 | L27–33 要求预检与发送有界、少量活动 handle、沿既有保护协调 cleanup，断连/取消/失败释放且流中异常中断，比例适当。现有 store.locate 是整文件 bytes，不能直接用于产物流；可最小扩展公开读取 port，不复制私有 store 状态机。具体保护持有期、close ownership、最大 chunk/FD 及正常/失败/断连 smoke 由 D 交付。 |
| HTTP / 前端边界 | Preview/History 现有错误路径不同，设计保留分类并对完整性失败新增 typed 503，方向合理。两路由 OpenAPI 改 tar、ETag/length，现有 JSON/octet-stream 删除。归档动态诊断仍从归档 API 读，不注入离线 bundle；新异常/关闭页面由前端 owner 更新。N1 单独交接。 |
| 验证比例 | A1/V1/V2/D 各有不变量 owner；04 最终受影响包与必要 Compose，05 一次 fresh t1 合并 FULL/MODIFIED_ONLY/归档/两类 tar，合成 wiring 补异常和关闭重提。自然 t1 不证明异常已覆盖。未受影响包依法按闭包复用；不重做 S1–S2b、全量性能矩阵、t4 或原冻结基准。新增摘要载荷要更新其 owning golden，既有业务 hash 不变则不能借故重录全部计算 golden。 |

本轮不要求恢复旧 Python 路径、batch aggregate、Archive Operation、迁移兼容或全历史搜索；也没有依据增设权限服务、图数据库、独立持久诊断状态机或 syscall 时序证明。B1/B2 可由设计者技术收口，未发现必须再次向 Owner 询问的业务选择。

## 5. 静态证据与容器决策

候选和合格 S2b 实际来源 `a6876d560050285321fd9f62942d590a03f35d64` 的 `vnext` Git tree 均为 **`92c1d6403d7cf3cbc4cf2746100699ed8d028ba7`**，本轮独立用 Git 核对。按联合 kickoff §7，复用 [E 独审已核的五包静态记录](p6-s2b-e-review.md)：06 `profile-focused-and-five-static.log` SHA256 `8af309bc680872fb21d0e6981fde0109881b744199f65d2661265ec90e075d97`。本次没有再次访问测试节点或读取原日志，不把同源码静态证据当作新规则、权限、schema 或传输通过。

```text
Current reviewed HEAD: 6995fe46a893f21d3dcb68ed6e1f17ebc74e6dd9
Container rebuild required: no
Reason: 候选只修改七份设计/计划文档；本轮只读设计审核
Last verified image revision: a6876d560050285321fd9f62942d590a03f35d64（引用 E 独审）
Last verified RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Last verified backend image: sha256:34130ae839ba946d07bee991f2a7e44b01f1f1f33b9416aba6b13c8c14644e3e
Last verified worker image: sha256:692cc893fdbbc4e5c5b336679334b3561c6e0ed1a0b36cf20e42e3d661334298
Container gate for current HEAD: not-applicable（没有作本候选产品门禁声明）
Carried from: none（本轮未计算运行闭包或镜像 carried）
Deferred gates/nodeids: 新产品尚未实施，精确范围在实施 kickoff 固定
Required execution point: 联合产品最终候选按实际影响验证，不为本报告重跑门禁
```

本报告及设计修订只做文档 diff/链接检查，不冒称产品静态检查或功能验证。审核 worktree 与报告保留；等待设计者提交新候选后，按实际 diff 复审 B1/B2/N1 及相应交叉文档，不预先宣布修复通过。
