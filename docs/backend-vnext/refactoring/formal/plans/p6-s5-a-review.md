# S5 A 独立产品审核归档

截至R6，修后固定候选 `c1a5332a8722d3736280d8b60059944e329b8697` 源码 **CODE_GO**；首次ad043编译失败原件保留，修后实际 focused、Rust 与五包静态证据尚待核收，A尚无证据GO，B未放行。以下为新独立Sol原审及连续复审逐字原文；设计CLEAR未用作产品GO。各原件的SHA与本归档文件整体SHA分别记录。

原件 Risk R1：`/home/dev/gdds-s5-logs/reviews/a-risk-r1.md`；SHA256：`b27a860fa7c725860f7754e030aa104e22f8f038739c083eba96cb13c857976b`。

---

# P6 S5 A / Risk 子候选独立产品审核 R1

结论：**CODE_CHANGES_REQUIRED**。发现一处 codec operation 控制缺口和一处确定的测试预期错误；均可按现有 A 节授权最小修复，不需 Owner 决策。原 emit 业务控制顺序未见回归。此结论只覆盖本 Risk 子候选，不代表 A 整体、持久缓存或 S5 已通过，也不以设计 CLEAR 代产品 GO。

## 1. 固定对象与独立性

- Candidate：`17255de2222df61e45206e96f51d39ea8dd788aa`。
- Base：`fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-risk-17255de222`；创建后及报告前均核 exact HEAD、detached、index/tracked/untracked clean；`legacy` 指向 `/home/dev/gateway-data-management-system/legacy`。
- 区间仅六个路径：Risk public facade、`_engine.py`、新 `candidates.py`、将原 `test_risk_s3_d_cache.py` 改名并增补为 `test_risk_candidate_cache.py`、`risk.md`、S5 coordination。Comparison 的未提交 WIP 不在审核对象中。
- 本人未参与该范围实现；没有修改被审 worktree、产品、测试或 owning Contract，没有递归分派，没有执行测试、编译、lint、镜像构建、真实旅程或 push/tag。
- 直接读取全部新增/修改 Risk 代码与测试、原版本差异，并追 `_facts.py`、Risk DTO/规则校验、Comparison session 的实际 risk lookup/store/commit/evict 接口、operation checkpoint 和 S3/S5 owning 语义。

## 2. 必须修订的 finding

### F1 — P2：codec 空序列绕过 operation 控制，批量 JSON 工作开始前未检查

位置：`vnext/backend/src/gateway_backend/capabilities/risk_evaluation/candidates.py:211`、`:289`。

`encode_risk_candidates` 的唯一 checkpoint 在事件写入循环的 `index % 1024 == 0` 分支；`decode_risk_candidates` 先 reserve、`json.loads(raw)` 并对整份 document 重新 canonicalize，然后才在事件恢复循环检查。合法空事件序列完全不进入这些循环，因此已经取消、已到 deadline 或已经关闭的 operation 仍可获得成功的 encoded/decoded owner。非空 decode 也会在首次观察 operation 控制前先做完整 JSON 分配与解析。这与 S5 设计 §8、risk.md 新增 codec 同 operation 控制/生命周期要求不符。

最小修订：入口先检查同一个 operation；有界预扫描/事件处理保持 operation checkpoint；整份 JSON 解码/规范化等 bulk 步骤前后以及成功返回前检查控制，确保空序列和最后一个事件也经过控制屏障。仅用现有 operation checkpoint，不调用或前移 Risk 的 table/pair clock，不增加状态机或第二套取消机制。异常路径继续关闭本次 reservation，InterruptedError/TimeoutError 等原控制结果直接传播，不当作普通 cache miss。

最小验证：在本文件的 codec owner 增加共享的小参数向量，覆盖 encode/decode 的空序列在预取消/截止下拒绝、bulk 后控制变化拒绝，以及已取得 reservation 后异常时余额恢复。每个边界只需一处权威断言，不扩为全 fault/调度矩阵；既有 replay 的 Risk clock 向量继续保持原计数。

### F2 — P2：过滤候选向量错误要求零标注风险表占位

位置：`vnext/backend/tests/test_risk_candidate_cache.py:503`。

`count=1, include_low=False` 参数写为 READY 且 `expected_counts=(0,)`。原 `_include_level` 过滤该 ROW_ADDED 的 MEDIUM_LOW 标注；随后 `_publish_result` 在 `_engine.py:688` 对空 annotations 直接跳过表，因而现行正确 `RiskReport.tables` 是空 tuple，计数投影应为 `()`。Risk Contract 亦规定无 annotation 的表不出现在 report，不产生占位 UNKNOWN/零标注行。该参数会让冷/暖正确结果同时失败，不能用它驱动产品变更。

最小修订：只将该参数的 expected_counts 改成 `()`，保留 READY、hit、cold/hot digest 与 clock 次数断言；不修改产品的无风险表语义。

## 3. 已核通过的代码边界与剩余依赖

- **完整纯风险输入：** `optional_candidate_input` 从当前 `RiskFacts` 移除 comparison/table/ref 外层绑定后，保留 table status、risk scope、schema evolution/effective keys、row stats、degraded/semantic facts/diagnostics，并补入 comparison_failed、ordered_unsupported、两侧 row count、suppressed counts、uncovered targets 及原 pair/table diagnostics。完整 ruleset document 包含 rule body、severity、params、model/contract/version；RiskOptions、artifact policy 和 policy semantic version 进入 JCS 域分隔 key。当前表/comparison digest 不再用作纯风险身份。
- **Comparison 依赖尚未验收：** `comparison_task_digest` 在此子候选仍由原 S3 session 提供，其完整 neutral records、FINAL 归一、repository/scope 和实际 native 输入同源性须待完整 A 的 Comparison 候选核收。这是明确的后续依赖，不能据本子候选声称跨 operation 风险缓存 key 已整体成立。
- **neutral 事件：** EMIT 保留 rule ID、所有现 RiskTarget 字段及有序 typed evidence，仅移除 table_name；恢复重新绑定当前表。CHECK_RECORDS_CLOSURE 保留事件位置、当前 closure/ref/digest 核验，未保存旧验证结论。格式、complete、连续 ordinal、封闭 envelope/event/target 字段与 key 均检查；decoded owner 关闭和异常路径释放 reservation。
- **原业务控制：** diff 中 cap（同时触界 pair 优先）→候选记录→rule/level→过滤→必要输出预约/编号/append→原 `_check_table` 顺序不变；被过滤候选仍直接 return；table-budget except 不加后续 total，而 diagnostics preflight 的正常 degraded 返回仍累加；pair cap 仍丢弃部分标注。composite 仍当前执行。缓存采用 neutral target 后当前编号/表名重新绑定。
- **完成与可选资源：** recorder 只在单表自然完成时 finish；真实 Comparison session 的 pending_risk 在 pair 成功后提交，失败清理；原 optional eviction 与必要 output 的一次重新准入路径保留。新 encoder admission failure 返回 None，decoder 对已取得的 charge 在异常时关闭。codec 的 16MiB 是 optional retention 上限，未改 Risk 产品接受范围。持久发布/TTL/protection 尚不在本候选。
- **独立预期：** `_PORTABLE_DOCUMENT` 是显式手写目标字段，新增 cap/时间同时触界、过滤与末条 emit 的状态/计数/诊断为独立小向量；旧 closure/cap/degraded/optional pressure 向量随文件改名保留，未从新结果录制 golden。除 F2 外未见需要改冻结预期的依据。
- **权限文档：** coordination 明确现授权、角色分离、统一节点池、M24、未运行/无 carried 与不 push；没有把原设计轮的未授权/Astra 叙述扩用为当前实施权限。

## 4. 必要验证与容器决定

两项修订固定为新 clean 已提交候选，由本原审核者连续复审后，再由唯一测试角色在合格专用节点执行：

1. `test_risk_candidate_cache.py` 与现 `test_risk_evaluation.py` 的受影响 Risk focused；包含 codec 控制/释放新小向量和原 replay 控制向量。无需 Dolt fixture、全量 runner或真实旅程。
2. 按 AGENTS 完成五个 Python 包 ruff/mypy。此子候选未改 Rust；不为它单独启动 Rust 编译。完整 A 接入 Comparison 后另按实际变化核 native 重装与 Rust/adapter 验证。

本报告未运行这些检查，当前证据状态为 **NOT_RUN**。不得先把 17255de222 写为 focused PASS 或 A GO。

Current HEAD：`17255de2222df61e45206e96f51d39ea8dd788aa`。

Container rebuild required：no；此差异只改纯 Python Risk 逻辑/codec、测试与文档，未触碰依赖、部署、容器 harness 或 container-only runtime boundary。

Last verified image revision/source-tree：仅沿用历史 S4 交接线索 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`；本审核没有重新核镜像或形成该候选的 carried 结果。

Container gate for current HEAD：**deferred**；集中 E 最终候选的必要权威/Compose，若后续触碰强制边界则按实际触发点执行。Carried from：none。不得把旧镜像证据称为当前 Risk 子候选 gate PASS。

没有需要 Owner 选择的新增业务取舍。F1/F2 关闭及必要 focused/静态证据核收后，可对该 Risk 子范围给限定 CODE_GO；A 整体与 B 开工仍等完整 A 候选核收。


---

原件 Risk R2：`/home/dev/gdds-s5-logs/reviews/a-risk-r2.md`；SHA256：`54113c388bfbfa02dd79163cb7ae6d3144dbf5800a77be7a93f4d0befb30b55b`。

---

# P6 S5 A / Risk 子候选独立产品复审 R2

结论：**CODE_GO（仅 A/Risk 子范围）；验证证据待核收**。R1 的 F1/F2 均已在固定修订稿关闭，本次增量未发现新的代码阻塞。此结论不代表完整 A、跨 operation 缓存接线或 S5 GO，不提前放行 B，也不代替专用节点 focused/五包静态结果。

## 1. 固定对象与方法

- Candidate：`1924249ec0787709695fdaae0d34dcb32df5756a`。
- 原审 Candidate：`17255de2222df61e45206e96f51d39ea8dd788aa`；完整实现 base：`fd9e383d76642037e4b3246c847222ea9483e033`。
- 新只读 detached worktree：`/home/dev/gdds-s5-review-a-risk-1924249ec0`；创建后及报告前均核 exact HEAD、detached、index/tracked/untracked clean。`legacy` 指向 `/home/dev/gateway-data-management-system/legacy`。
- 原审至本稿仅四路径：Risk `_engine.py`、`candidates.py`、`test_risk_candidate_cache.py` 与 coordination。Rust tree 仍为 `e2a901417b19259ece669637a41545e774261445`，Comparison WIP 不在此固定提交。
- 本人是 R1 原审核者，直接读完整增量及受影响函数和新小向量；沿用 R1 已完成的其余字段、规则、事件、session 完成边界核查。没有改产品/测试/Contract 或被审 worktree，没有运行测试、编译、lint、构建或真实旅程，没有创建子 agent、push/tag。

## 2. Finding 关闭

| R1 finding | 固定修订与独核 | 结论 |
| --- | --- | --- |
| F1 codec operation 控制 | encode/decode 入口先调用同 operation checkpoint；encode 预扫描及事件写入每 1024 事件检查，成功构造与返回前继续检查；decode 在 bulk JSON/规范化后、事件循环及最终返回前检查。空序列也经过入口和取得 charge 后的控制点。key builder 入口/完成及 engine key hashing 后接同 operation 检查。取得 reservation 后的异常仍经唯一 except 关闭 charge 并原样传播。没有调用 Risk table/pair clock，也未前移 emit 检查。 | CLOSED |
| F2 过滤向量预期 | `include_low=False` 的 READY 参数改为 `expected_counts=()`；保留 cold/hit 状态、digest、命中及 clock 次数比较。产品 `_publish_result` 无风险表缺席语义未改。 | CLOSED |

新增 `_CodecStop` 小向量以真实 OperationMemoryBudget 为账本，共享 encode/decode、首次 checkpoint/取得 charge 后 checkpoint、InterruptedError/TimeoutError 参数；断言原控制异常和预算余额恢复。这是 codec 的最小控制/释放 owner，没有增加治理机制或全故障矩阵。其源码足以表达 F1 关闭条件；本人没有运行它，不把静态核对记为执行 PASS。

本次删除 `optional_candidate_input` 的普通 ValueError/OverflowError 吞异常分支，所有已取得 charge 的异常均关闭后传播；entry/key 上的 operation 控制不会被改成 cache miss。当前 producer 给出的 RiskFacts/rules/options 沿 owning DTO 校验，尺寸/预约不足仍以原 None 路径安全放弃可选 key。没有发现本增量改变冻结业务预期的依据。

## 3. 继续验证与边界

唯一测试者可在本固定候选、合格专用节点上执行 R1 已列 Risk focused：`test_risk_candidate_cache.py` 与受影响 `test_risk_evaluation.py`，以及 AGENTS 要求的五包 ruff/mypy。原始日志须按现行节点占用、离线、clean/HEAD/exit/SHA 规则保留，完成后再由本审核者核收。此处不要求单独 Rust/Compose 或真实旅程。

Comparison task identity 仍是完整 A 的待核依赖：该 digest 必须确实对应实际 native 语义输入、完整 neutral facts/records、FINAL 归一及 repository/scope。本 Risk 子范围的代码 GO 不证明该前提已经完成。持久 entry/uses、TTL/protection、History 与 T3 接线也尚未在此候选核收。

Current HEAD：`1924249ec0787709695fdaae0d34dcb32df5756a`。Container rebuild required：no，纯 Python codec/control 与测试/文档增量，未触碰容器或部署边界。Last verified image/source-tree 仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 的来源线索，本次未复核镜像或重算 carried。Container gate for current HEAD：**deferred**，集中 E 最终候选；Carried from：none。产品执行状态：**NOT_RUN / 待唯一测试者原件**。

R1 外置原件 `/home/dev/gdds-s5-logs/reviews/a-risk-r1.md` 的 SHA256 为 `b27a860fa7c725860f7754e030aa104e22f8f038739c083eba96cb13c857976b`，本次未改其原文。没有剩余本子范围代码 finding 或需要 Owner 决定的业务取舍。


---

原件 A R1：`/home/dev/gdds-s5-logs/reviews/a-r1.md`；SHA256：`0cdf3396f7af6821118070123c8cbb9e6127eaf2a573ae7345ee143dae319b42`。

---

# P6 S5 A 完整候选独立产品审核 R1

结论：**CODE_CHANGES_REQUIRED**。固定 A 候选存在四项应在现有设计内修复的代码问题，分别涉及 SET facts frame、完整 canonical 任务准入、restore 的同 operation M/控制、以及 neutral 载荷闭合。无需改变冻结业务/digest、扩大 M 或真实范围；修复后由本审核者连续复审。Risk 子范围 R2 的限定代码 GO 保留，不能代替完整 A GO，B 尚不放行。

## 1. 固定对象、范围与独立性

- Candidate：`c32c9aabd96bfae36093aa805a2ee2eea1c04c7e`。
- Base：`fd9e383d76642037e4b3246c847222ea9483e033`；Comparison 增量父：Risk R2 `1924249ec0787709695fdaae0d34dcb32df5756a`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-c32c9aabd9`；创建后核 exact HEAD、detached、index/tracked/untracked clean，`legacy` 指向 `/home/dev/gateway-data-management-system/legacy`。报告前再次核同一身份与 clean。
- 直接读取完整 Comparison 16 路径增量：task input、Python codec/native/production、core cache/facts/builders、PyO3 handle/restore、Contract/Artifacts/Rust policy/import guard 与新测试；并追现 descriptor、storage facts、planner、canonical Arrow proof、records validator、三族 producer、当前 M/native phase 与 frozen oracle 来源。
- Risk 已由同一审核者连续原审/复审：R1 原件 SHA256=`b27a860fa7c725860f7754e030aa104e22f8f038739c083eba96cb13c857976b`；R2 原件 SHA256=`54113c388bfbfa02dd79163cb7ae6d3144dbf5800a77be7a93f4d0befb30b55b`。本次沿用其字段/控制核查，仅核完整 A 的新依赖接缝。
- 本人未参与实现，未改被审 worktree、产品/测试/Contract，没有创建子 agent，没有运行产品测试、编译、fmt、lint、镜像或真实数据，没有 push/tag。候选 Rust 尚未格式化/编译/测试，不能从源码审核推出这些检查通过。

## 2. 必须修订的问题

### A1 — P2：新 facts frame validator 拒绝现有合法 SET 编码

位置：`vnext/rust/gateway-compute-core/src/records/cache.rs:185`。

`frame` 要求 hex 至少四字符，并将第一字节无条件当 scalar tag，再解析 payload length。但 Canonical Storage/Shared Canonical Encoding §3.2 和现 `comparison::ordered::encode_cell` 的 SET 分支规定：非 NULL SET 单元格是 sequence frame 本身，不包 scalar tag。`comparison/standard.rs::canonical_set_uses_frozen_sequence_frame_and_rejects_bad_order` 已有独立断言：`SET('a','b')` 值 `a,b` 的 frame 为 `[2,3,32,1,97,3,32,1,98]`，空 SET 为 `[0]`。前者被当前 tag 白名单拒绝，后者 hex `00` 被最短长度拒绝。因此正常比较能生成的合法 SET facts 无法被新缓存 restore 验证，真实 SET 任务不能满足健康热命中。

这里的单字节 `[0]` 是**空 SET**，不是 NULL；普通 NULL scalar frame 仍为 `[0,0]`，不能错误改其业务期望。

最小修订：facts validator 按现 owning scalar/SET sequence 定义接受并验证相应 frame，复用已有 safe helper 或最小局部有界校验，不发明新 scalar tag、不修改业务编码/Shared Kernel v1、不新增公共通用 decoder。增加空 SET、声明序非空 SET、NULL 的固定 frame 向量及一个真实 adapter cache round-trip；expected 取上述冻结 owner，不从新 codec 生成。

### A2 — P1：仅 FINAL 标签与 raw digest 即可生成 key，缺完整 canonical/storage 准入

位置：`vnext/backend/src/gateway_backend/capabilities/comparison/task_input.py:232`；`production.py:116`。

`build_table_task_identity` 只检查 repository/scope/mode、可选尺寸和 descriptor 的 FINAL/raw digest，没有要求两侧 `ComparisonStorageFacts` 存在，亦未核其中 canonical schema/content/projection 与对应 descriptor 的绑定完整。`semantic_value(policy)` 能把现有 storage 字段序列化，但 `None` 也会成功成为持久身份；这与设计 §3 的“缺完整元数据/非 canonical 输入不进入持久缓存”不符。

这不是只缺一条字段变异测试：现新测试的 `_planned` 来自 `canonical_bound`，该 helper 经 `bound` 返回的 `BoundSnapshotInput.storage_facts=()`；planner 因而生成两侧 storage facts 均为 None，测试仍要求 `TableTaskIdentity`。所谓 `storage` mutation 只改 `policy_version`，没有实际证明任一侧 storage view、source/canonical schema、projection version 变化必须 miss。`_task_key` 又将新稳定身份直接用于现 operation session；原 reader/artifact 身份已经删除，session lookup 仅 reopen reader，不能用此替代首次 canonical/storage authority 核验。

最小修订：在唯一 identity owner 对两侧完整 storage/canonical 绑定作显式准入；缺失/部分字段或与 descriptor 不符时 NotCacheable，authority 矛盾仍留给原 owner 的稳定失败，不伪装 cache miss。metadata-only History 可以没有 row reader，但必须有已验证的完整 side facts；不要为 key 强迫读行。实际 native 请求继续来自同一 task projection，不能补第二份 cache 字段白名单。必要时将原 owner 的已验证 side binding 作为明确输入，而非凭 FINAL 枚举猜验证成功。

最小验证：使用真正完整的 side facts 固定向量，分别变异两侧 effective key/storage view/source schema/canonical schema/content/projection version，并断缺字段不产生持久 key；保留合法 Preview/Repository authority 归一后去除 commit/operation/display 的相等断言。无须 Dolt fixture。

### A3 — P1：restore 可把当前 Python 预算与另一 operation 的 native 预算/控制混用

位置：`vnext/backend/src/gateway_backend/capabilities/comparison/cache_codec.py:210`；`native.py:164`；`vnext/rust/gateway-compute-python/src/comparison_records.rs:850`。

Python restore 只对传入 `context.require_active()`，随后将任意 `ComparisonOperation` 传入 native。后者使用其创建时保存的 context、cancel watch、deadline 和 parent charge；没有与当前 Python operation 的 identity 比较。native 已保存 `operation_identity=id(origin.memory)`，但本入口不检查它。因而可在新 operation 的 active context 下，把 IPC/Python reservation 计入新 M，把 restored Arrow/header/native work 计入旧 M，并继续观察旧 cancel/deadline。现 facts-core 的 handle 同 phase/同 operation 检查只发生在后续摘要调用，不能弥补 restore 已经分配和执行的这段混用。

最小修订：沿现 operation identity，在 restore 开始文件/Arrow/FFI 分配前拒绝不属于当前 operation 的 native phase，并保持当前取消/截止前后检查；无需新 registry、scheduler 或资源框架。若 native facade 暴露必要的最小身份验证入口，继续保精确 FFI owner。

最小验证：创建 A 的 native phase，在 B 的 active context 下尝试 restore，断早期拒绝、B/A 两账本不留新增占用；同 operation 正常 restore、控制异常及最终 Arrow consumer 释放沿唯一资源 owner 验证。`high_water <= limit` 只是账本自限，不单独证明输入/输出都归同一个 M。

### A4 — P2：完整标记未闭合 task-kind、必需 metadata 与空族 schema/risk 值

位置：`cache_codec.py:227`；`comparison_records.rs:872`、`:891`、`:905`、`:924`；`records/builders.rs:247`。

存在四个同属新 neutral 格式准入的具体漏项：

1. Python restore 只要 `native_metadata_json is None` 且 views/families 为空，就直接返回 fact/None；没有限制为 ordered-current-summary 或 nonrecord metadata 任务。将合法 row-comparison payload 的这三项清空，仍会被当 complete 成功恢复，实际 records/facts 已丢失。
2. native metadata 仅要求是 object，`record_count` 用 `get(...).and_then(as_u64).is_some_and(...)` 检查；缺字段/错误类型完全跳过校验，且当前 table fact 的 counts/summary 与 native/family 数据没有完整的必要闭合。`metadata_json={}` 可以通过此处，不能作为协议声称的完整 native metadata。
3. artifact stream 的 schema 在 `let (_, batches)` 被丢弃；`restore_records_batches` 只在遍历 batch 时验证 schema。合法零行族没有 batch，因此错误的空族 schema 会被接受，而 facts/risk 空流则已有显式 schema 检查。
4. risk view 只核 Arrow schema、每 batch 行数与 STANDARD facts 总数，不核其枚举/必要值。未知 record_kind、非法 changed_columns 等会留到真正 Risk consumer 转换时才失败，而不是在 cache 格式验证时判 invalid/miss。

最小修订：按 task-kind 明确必需/可空成员；对现真实 native producer 的小 metadata 使用闭合字段/类型及必要 count/summary 校验；保留并检查空族 reader schema；对 risk 最小投影验证其实际 consumer 要求的 kind/identity/columns 形状。继续依赖可信 producer+scope/key/raw SHA 的关联，不要求额外跨 view 防篡改证明、重算比较或同 euid 攻击模型。损坏格式应在统一 codec 边界拒绝，由后续 B/C 按设计只 invalidate 精确条目并正常计算一次；控制错误仍直接传播。

最小验证：共享 fault 参数表覆盖 row task 缺整组成员、required metadata 缺失/类型/count、空族 schema、一个坏 risk kind/column；补一个完整正常零行族 round-trip。不要用更新业务 golden 接受丢记录。

## 3. 其余已核边界与保留事项

- 新任务的 native policy 从 `build_table_task_input(..., include_identity=False)` 生成，identity 分支调用相同 policy constructor；共有列、effective keys、keyless/ordered 参数与原 production policy 搬移内容一致。完整 projection 保留 schema 内表名、规则主体、options/detail/contracts、两侧 ordered provenance、plan/descriptor diagnostics，不以显示名删除业务 schema 身份。A2 是准入缺口，不要求推翻这个共同构造方向。
- 三族 facts 序由现 `fact_row_value` 输出，BLANK 保留 entity_key_kind；artifact 序通过去 table_name Arrow 视图恢复，未排序/rechunk；每批最多1024行，未虚构1024个 batch 的上限。STANDARD risk 独立视图继续 facts 序。table/core digest 对 restored neutral rows 走完整 JCS 重放，不是串联 table digest；records content digest 由真实 validator 重算。
- 新 cache prepare 在原 native phase seal 前执行，失败的可选 reservation 不改变必要比较结果；Python codec 与 native output/input parent 的 owners 显式存在，核心无 DB/filesystem/I/O，入口仅经 comparison.native，import guard/policy 精确登记，未追加架构豁免。A3 的 operation 绑定仍必须先修复。
- Python payload 为内存格式，持久 manifest/ArtifactRef/TTL 的完整发布尚归 B；本轮未声称 DB/cache hit、History 零读或 T3 已实现。后续 B/C 不能仅以这些内存 dataclass 替代持久 ref/raw/schema/count 核验。
- 新 adapter 测试使用已有 S3 pre-C frozen_case 的准确 standard/ordered 输入，且分别断 table facts digest、records content 与 Parquet raw SHA；这是合格的独立 oracle 方向。现新测试尚未覆盖 A1/A2/A3/A4 对应边界，也未执行，不以 self round-trip 或手写三行 facts 验证器测试代替完整 reader 正确性。
- 文档直接替换旧 pair-level/JSONL 条款符合无兼容要求；Comparison Records Closure 末尾仍残留“table-level comparison cache 后续再设计”一句，应随本节机械清理，避免与紧邻新 Contract 矛盾。无需因此新增协议或测试。

## 4. 必要验证、容器与证据状态

先固定有修改的修订稿、由本原审复核上述四项，再由唯一测试者执行必要 focused：Rust facts/cache/records 与 adapter cache tests、原 comparison/risk frozen owner、import guard 允许/拒绝；Rust 改后强制重装 gateway-compute-python 并核 build input，不能使用旧扩展。按 AGENTS 完成 Rust fmt/clippy 与五 Python 包 ruff/mypy。取消/异常/同 M 的新小向量归相应唯一 owner，使用必要参数表，不新建重复全矩阵。阶段内不因此提前跑六包或真实 t1。

本人本轮**未运行任何产品检查**；Rust fmt/编译/clippy/test、backend focused、五包静态当前均不能记为本候选 PASS。后续机械 formatter patch 仍须固定入 clean 候选，不能在被测/被审 worktree 写入后复用旧 SHA。

Current HEAD：`c32c9aabd96bfae36093aa805a2ee2eea1c04c7e`。Container rebuild required：本 A 子节无独立触发，代码未改锁/production 依赖、部署、container harness 或 container-only boundary；阶段 E 最终候选仍需适用当前 Compose 绑定。Last verified image revision/source-tree 仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 的交接线索，本审核未重算镜像或 carried。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选，或后续实际触发边界的必要节点。

没有需要 Owner 改变业务取舍的阻塞；四项均是已授权设计的局部实现收口。完成本轮修复复审和必要证据核收后才判断完整 A GO，不把 Risk 子结论或设计 CLEAR 作为替代。


---

原件 A R2：`/home/dev/gdds-s5-logs/reviews/a-r2.md`；SHA256：`dd5ef82ecff7976e856709409819c390932ab88c94f17a7ec48e1bf367b0090b`。

---

# P6 S5 A 连续产品复审 R2（preformat）

结论：**CODE_CHANGES_REQUIRED**。原审 A1–A4 的产品代码原因在本修订稿静态关闭；新增的两处测试代码错误仍阻塞固定候选验证。另待下一固定稿核 NativeComparison 的真实 codec owner 接口与机械格式化差异，尚不签完整 A GO 或 B 开工。Risk R2 限定结论保留，未把设计 CLEAR 或未运行检查当作通过。

## 1. 固定对象与方法

- Candidate：`58e1a7f927d1f0f7daa737b83910d9d49090d793`。
- 原审 Candidate：`c32c9aabd96bfae36093aa805a2ee2eea1c04c7e`；完整 base：`fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-58e1a7f927`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean。`legacy` 链接正确。
- Candidate Rust tree：`24fd29b7178bc74fcee1705368ceb6167730d629`。
- 直接读完整 18 路径增量与受影响函数：完整侧准入、native policy/key、codec/metadata、SET parser、risk projection、operation identity、原 session 适配、版本常量/FFI/DAG/Contract，以及全部新增小向量。未改变 Risk R2 所核代码边界。
- 本人未参与实现，未改被审 worktree、产品/测试/Contract，没有运行产品测试、Python parser 检查、编译、fmt、lint、构建或真实旅程，没有创建子 agent、push/tag。下述测试缺陷来自直接读取源码，不冒称已运行失败。

## 2. 原 finding 关闭依据

| 原 finding | 修订与独核 | 当前结论 |
| --- | --- | --- |
| A1 SET facts frame | `records/cache.rs::frame` 先验证 scalar，否则按 SET sequence 验证成员数、length framing、string scalar、非空/不重复及末尾闭合；保留空 SET `00` 与 NULL `0000` 的不同形态。固定向量包含两者及声明序非空 SET，adapter 向量直接断旧 owner 定义的 frame 文本。没有改 canonical 版本、业务编码或旧 golden。 | 产品原因静态 CLOSED；向量待执行 |
| A2 完整 canonical/storage 准入 | `_complete_side` 要求两侧完整 source/canonical schema/content/projection、table/columns/key 绑定；现存 reader 必须是原 canonical owner 已成功验证的 Arrow reader。缺失/部分 storage 不再产生持久身份；新 helper 用真实 canonical writer 建完整小输入，逐侧变异真实 storage 字段。metadata-only 无 reader仍允许完整 side facts，schema digest 的权威核验归原 owner，Comparison 不复制 StorageProjection 算法或新增 DAG。 | 产品原因静态 CLOSED；C 仍须在 lookup 前核精确 metadata authority |
| A3 同 operation M/控制 | Codec 入口在分配前核 native phase `require_operation(id(context.memory))`，facade 再核 active context/identity并传同 identity到native，native入口校验旧 phase 未关闭/未sealed且属于当前 operation；返回前检查当前控制。encode亦核 handle operation。foreign/cancel/deadline/budget与最后 Arrow consumer 向量已加入，deadline 参数当前有下述 R2-F2 缺陷。 | 产品原因静态 CLOSED；资源向量待修/执行 |
| A4 载荷闭合 | row task 必须带完整 native views，metadata-only仅限两种无记录kind；小 metadata 现按 standard/ordered精确字段/类型及必要 summary/count验证；Python重建当前native table fact并比较 neutral outcome；空 artifact流schema被保留并核对；risk projection核kind/identity/column/null值。fault参数表与正常零STANDARD族向量已加入。未引入跨view防篡改证明或新状态机。 | 产品原因静态 CLOSED；向量待执行 |

A2 的边界与当前 owning DAG 一致：完整字段/一致性准入由 Comparison 持有，canonical_schema_digest 的语义验证由原 authority owner承担。C 必须把原 `load_table` 中的 exact catalog/schema/count/commit 检查提前到 metadata describe/cache lookup前，不能靠此处 FINAL 枚举或等到 ensure_rows才核。无需 proof布尔、durable凭证或新registry；本次不把尚未实现的 C authority接线写成已验证。

## 3. 本轮必须修订的测试错误

### R2-F1 — P1：session 输入适配破坏 Python if/else 语法

位置：`vnext/backend/tests/test_comparison_s3_d_production.py:1295`。

`if fresh:` 分支末尾新增的 `before = complete_canonical_bound(before)` 与 `if` 同级，后面紧跟 `else:`。Python 的 else不能在中间插入同级语句，整个测试模块无法解析/收集；不是某个参数预期不符。

最小修订：将该语句放入对应 fresh 分支（或在完整if/else后统一处理），保留原fresh/artifact与普通输入两分支意图。不要为修测试改产品行为。修后固定新提交再做专用节点检查。

### R2-F2 — P2：deadline 向量直接写 frozen context，未进入 restore

位置：`vnext/backend/tests/test_comparison_cache.py:388`。

`KernelExecutionContext` 为 `@dataclass(frozen=True, slots=True)`，当前 deadline 参数执行 `context.deadline_monotonic = 0.0`，会在进入 `pytest.raises(TimeoutError)` 前抛 FrozenInstanceError。该向量没有验证 restore deadline，也可能在操作关闭 finally 建立之前提前退出，不能作为控制/释放证明。

最小修订：按现公开构造/控制机制建立会在 restore 前到期的有限 deadline或受控clock，不改 frozen产品类型、不靠修改被测对象绕过控制。保持 foreign/cancel/budget共用的最小参数表，以及两账本余额/最后consumer断言。

## 4. 其他增量核查与下一固定稿边界

- 版本投影补入 Pythoncomparison/standard/records/closure/projection/scalar常量，以及由Comparison facade读取的既有Rustordered format/version和canonical mapping版本。`_comparison_format_versions_native` 只返回现有常量，无新版本轴；policy/import guard精确登记，负例继续拒绝Risk直接restore FFI和任意入口/wildcard。未见新增DAG反向边。
- 冷/热 table fact构造共用 `native.table_fact`，避免codec与production各维护一份metadata解释；原session命中重绑当前descriptor。reader availability属于资源事实，不进入内容key，实际lookup保留reopen拒绝不可用reader；相关旧session测试改为真实完整canonical输入，未修改其业务oracle。
- 可选 cache prepare新增 `cache_created_risk`，失败discard只释放本次额外risk view，不误删原必要risk输出；codec异常关闭已创建handle与本次owner。当前小向量方向符合reservation/最后consumer边界，但尚未执行，不能用账本自限断言代替实际通过。
- 目前 `_complete_side` 保守拒绝任何 descriptor.degraded_reason；Repository metadata会对合法无compare key描述标 `KEYLESS`。该路径目前可能安全miss，C应如实计数并核其keyless适配，不能宣称已产生/命中健康条目；此处不据性能偏好新增安全机制或扩大测试矩阵。
- 新 `cache_codec.py` 当前仍只有测试直接消费。协调者已提出下一固定稿添加 `NativeComparison.encode_cache_candidate(...)` 的真实owner内存接口，由现native结果owner控制当前fact/handle/context，并让adapter向量通过它调用；这属于A的最小真实facade闭合，不是提前DB/History，也不能靠架构baseline豁免、只re-export或测试私有调用冒production reachability。本R2不预签尚未出现的接口实现。

下一 fixed clean候选包含 R2-F1/F2修复、上述最小owner接口及机械 formatter差异后，由本审核者窄复核这些增量；原A1–A4不因格式化重开完整原审。随后唯一测试者再按已审范围执行必要Rust/installed native adapter/Comparison与Risk focused、import guard、五Python包ruff/mypy；不能在开发机运行，不能用旧.so。当前所有执行证据仍 **NOT_RUN**。

## 5. 容器与归档

Current HEAD：`58e1a7f927d1f0f7daa737b83910d9d49090d793`。Container rebuild required：本子节无独立触发；未改锁/production依赖、部署、实际container harness或container-only runtime边界。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`来源线索；本次未重算镜像/新增carried。Container gate for current HEAD：**deferred**；Carried from：none；必要执行点仍E最终候选或后续实际触发边界的节点。

原A R1外置原件 `/home/dev/gdds-s5-logs/reviews/a-r1.md`，SHA256=`0cdf3396f7af6821118070123c8cbb9e6127eaf2a573ae7345ee143dae319b42`，未改原文。当前不需Owner选择新增业务取舍；完成上述局部修复/窄复核与必要证据后再判断完整A GO。


---

原件 A R3：`/home/dev/gdds-s5-logs/reviews/a-r3.md`；SHA256：`840ca7f87ca09162b94fb05aa271d39b79828d99ac52aee0d7a90961d3c384c6`。

---

# P6 S5 A 连续产品复审 R3（功能稿，待机械格式化）

结论：**CODE_GO（本固定功能源码范围）；格式化候选与执行证据待核**。R2-F1/F2 均关闭，新增真实 codec owner 接口和合法 KEYLESS 代表适配未发现代码阻塞。此结论不等于 A 已完成验证，不放行 B；格式化提交仍须机械比对，之后由唯一测试者执行必要 focused/静态/Rust并交原件核收。

## 1. 固定对象与独立性

- Candidate：`5a74dfd0684f45a826e485d48d73a6ea66dd7126`。
- 上轮 Candidate：`58e1a7f927d1f0f7daa737b83910d9d49090d793`；完整 base：`fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-5a74dfd068`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，`legacy` 链接正确。
- Rust tree：`569ed462e66908a67ada1cfcb91cad74788a6ab1`。
- 窄审五路径完整差异：Comparison production/task_input、两份 backend tests、Rust records/cache tests。沿用 R1/R2 已关闭的 A1–A4、Risk R2、版本/FFI/DAG核查，没有重审 S3/S4或重建测试矩阵。
- 本人未改被审 worktree、产品/测试/Contract，未执行测试、Python语法命令、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。以下关闭来自固定源码核对，不冒称运行成功。

## 2. 本轮关闭与新增接口核查

| 对象 | 实际修订与独核 | 结论 |
| --- | --- | --- |
| R2-F1 if/else 语法 | reader-cancel测试恢复完整fresh/else结构；该测试不使用session，因此保原canonical/artifact小输入，不人为为它增加cache预置。闭reader纯行为测试亦回到原非session helper，业务预期不变。 | CLOSED |
| R2-F2 frozen deadline | context在构造时得到有限deadline；native phase建立后仅在测试内控制monotonic clock越界，未写frozen字段。嵌套独立operation显式 `new_operation=True`，foreign/cancel/deadline/budget保持原错误及两账本释放断言。 | CLOSED |
| 真实 codec owner | `NativeComparison.encode_cache_candidate(table_name, identity, context)` 由已完成的真实result owner查当前table fact及所持handle，经唯一ComparisonCacheCodec导出；检查active context与table存在性，handle的same-operation检查仍在codec。实际adapter/fault/SET/keyless向量调用该owner方法。production模块产生真实codec依赖边，不是仅re-export、测试专用入口或baseline豁免。 | 静态通过 |
| KEYLESS 适配 | 完整侧准入接受合法 `DegradedReason.KEYLESS`，其余FINAL、完整storage/content/columns/key与reader proof条件保持。新增真实keyless multiset代表为before a×2/b×1、current a×1/b×3，独立净计数2增1删0改；facts序、三个occurrence身份、冻结string frame和restore计数/当前facts摘要均有明确断言。没有set去重或改原算法预期。 | 静态通过 |
| Rust test机械收口 | test module移到生产items之后，success tests改为workspace既有Result/`?`风格，固定facts/frame字符串、negative vectors及完整JCS预期未改；没有借lint修订业务断言。 | 静态通过，未运行lint/test |

owner接口文档把当前必需pair输出、可选retention失败和payload关闭责任留给调用方；它没有提前接DB/History，也不把内存encode自动登记为可命中持久条目。C后续必须通过该真实结果owner接线，并在pair成功后才暴露持久候选；metadata-only canonical authority仍按R2明确前置，由原owner在lookup前验证精确catalog/schema/count/commit。

原 A1–A4 仍静态关闭；本轮没有修改SET帧语义、风险控制顺序、digest定义、SQL、生产M24、scope/恢复屏障或独立golden。没有剩余需要Owner选择的新业务取舍。

## 3. 尚未核收的执行与下一步

当前 **FORMAT / COMPILE / FOCUSED / STATIC = NOT_RUN**，不能由本代码GO反推通过。独立测试角色在本人隔离worktree生成机械rustfmt patch后，固定入新clean候选；本原审只比对格式化差异与产品树身份。若超出机械格式，则核受影响语义，不以格式化名义接受功能变化。

随后唯一测试者按已审范围执行：Rust fmt/clippy及必要cache/facts/records tests；强制重装gateway-compute-python并核build input；backend新cache/Risk、既有Comparison/session/frozen owner与import guard focused；五Python包ruff/mypy。输入/节点/占用/离线/HEAD/exit/SHA/资源释放均沿现行规则，不在开发机执行、不用旧.so，不提前六包或真实t1。执行失败保原件并先处理，未运行或未知仍不得写PASS。

## 4. 容器与原件

Current HEAD：`5a74dfd0684f45a826e485d48d73a6ea66dd7126`。Container rebuild required：本子节无独立触发，未改锁/production依赖、部署、实际container harness或container-only行为。Container gate for current HEAD：**deferred**，必要执行点仍E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像/新增carried。

R2外置原件 `/home/dev/gdds-s5-logs/reviews/a-r2.md` SHA256=`dd5ef82ecff7976e856709409819c390932ab88c94f17a7ec48e1bf367b0090b`，未改原文。完整A的证据GO及交接仍待后续真实检查原件核收。


---

原件 A R4：`/home/dev/gdds-s5-logs/reviews/a-r4-format.md`；SHA256：`dc44e3d802004594b3c2aebcfbfb4921e94bd0746cfcd525ca4db610a399b150`。

---

# P6 S5 A 连续产品复审 R4（最终格式化候选）

结论：**CODE_GO，绑定最终候选 `ad043152b1604da1ff56ec67f1513e4fd9b66456`；产品执行证据仍 NOT_RUN**。R3 至本轮仅有四个 Rust 文件的机械格式差异，未发现语义、固定向量或资源归属变化。此候选可交唯一测试角色集中执行 A 必要验证；本结论不等于 A 证据 GO，不放行 B。

## 1. 固定对象、独立性与补丁身份

- Candidate：`ad043152b1604da1ff56ec67f1513e4fd9b66456`。
- 上轮功能 Candidate：`5a74dfd0684f45a826e485d48d73a6ea66dd7126`；完整审核 base：`fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-ad043152b1`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，`legacy` 链接为 `/home/dev/gateway-data-management-system/legacy`。
- 最终 Rust tree：`00fda965165d64ff8846d2205754f38d4cd4630c`。backend tree：`240d6ccd86ca0df0df053d752e592838e626d9a8`，与 R3 完全相同。
- 06 原格式补丁：`/home/dev/gdds-test-tmp/p6-s5-a-5a74df-prep/rustfmt.patch`，40,690 字节，SHA256=`727e7c2ff83b323e43fec0d18b41924db460039747d5113a5478df19cd801ec0`。本审核校验其摘要，并在最终候选上只读执行 `git apply --reverse --check`，exit 0；以原补丁的 `core.abbrev=9` 渲染 `git diff --no-ext-diff --binary 5a74dfd0684f45a826e485d48d73a6ea66dd7126 HEAD` 得到逐字相同摘要，故不是仅据提交说明信任格式化范围。默认不同 abbreviation 的 diff 字节差异已确认属于渲染差异。
- 本人未改被审产品、测试、Contract 或 worktree；未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。原补丁由唯一测试角色在 06 生成，本报告不以其存在代替最终候选的实际产品检查。

## 2. 四路径机械比对与既有结论绑定

逐段完整比对四路径差异，范围仅限以下内容：

| 路径 | 差异及核查 |
| --- | --- |
| `gateway-compute-core/src/comparison/mod.rs` | 同一 `pub use ordered` 集合的排序和换行；导出成员未增删。 |
| `gateway-compute-core/src/records.rs` | 同一 cache 导出集合的排序和换行；模块可达性与公开接口未变。 |
| `gateway-compute-core/src/records/cache.rs` | 行拆分、括号/大括号排版、尾逗号及 `?` 换行；SET/scalar 帧常量与合法条件、metadata 精确 keys/枚举/count 约束、错误字符串、固定 facts/JCS 预期和测试输入均未改。 |
| `gateway-compute-python/src/comparison_records.rs` | import 排序、行拆分、大括号及尾逗号；same-operation 守卫、控制检查次序、schema/count/family/risk 校验、M 预留/lease/owner 字段和 FFI 参数值均未改。 |

不存在额外 Python、Contract、SQL、依赖锁、部署或容器 harness 差异。R3 真实 `NativeComparison.encode_cache_candidate` owner 消费、合法 KEYLESS multiset 向量、frozen deadline/reader-session 两项测试修正保持原文；R1–R2 已核 A1–A4、版本常量/FFI/DAG、Risk R2 控制点与释放结论仍适用于本最终候选。没有新代码 finding 或待 Owner 选择的业务取舍。

R3 原件 `/home/dev/gdds-s5-logs/reviews/a-r3.md` SHA256=`840ca7f87ca09162b94fb05aa271d39b79828d99ac52aee0d7a90961d3c384c6`，保留未改；本轮不把设计 CLEAR、源码 CODE_GO 或机械格式比对当作执行 PASS。

## 3. 尚待唯一测试角色完成的证据

最终候选的 **FOCUSED / STATIC / RUST / NATIVE BUILD-INPUT = NOT_RUN**（本报告核收状态）。必要 focused、五 Python 包 ruff/mypy、Rust fmt/clippy/相关测试及强制重装 native extension/精确 build-input 核查，仍由唯一测试角色在获准测试节点的 clean、已提交 worktree 实际执行。执行输入须固定本 SHA，沿用有效占用、离线缓存、节点/起止 HEAD/exit/log SHA 和释放规则；失败保原件并先修复，不提前全量六包、真实 t1 或 B。

后续由原审核者核原件，才形成 A 的必要执行证据 GO；本报告仅完成从 R3 到最终格式化提交的代码结论绑定。

## 4. 容器状态

Current HEAD：`ad043152b1604da1ff56ec67f1513e4fd9b66456`。Container rebuild required：本 A 子节无独立触发，未改锁/production 依赖、部署、实际 container harness 或 container-only 行为。Container gate for current HEAD：**deferred**，必要执行点仍为 E 最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree 仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 交接线索，本审核未重算镜像或新增 carried。


---



---

原件：`/home/dev/gdds-s5-logs/reviews/a-r5-compile.md`；SHA256：`7eb2a42c1de2b15ff0e2a3550629cd61ece2aa8e74e6b0d1b8b6f9e3ce490055`。

---

# P6 S5 A 连续产品复审 R5（首次编译失败修复）

结论：**CODE_GO（固定功能源码范围，待最终格式化比对与实际重验）**。首次 native 编译暴露的四个 E0433 原因已在源码中关闭；本轮没有发现新代码阻塞。尚无当前修订的编译成功证据，A 证据 GO 与 B 放行继续等待。

## 1. 固定对象与原失败

- Candidate：`5351170224c6bbe4997074338292fb04b380e64f`；Rust tree：`aeae50698611cd2803e8c7ca466f7a999565aff8`。
- 原被测候选：`ad043152b1604da1ff56ec67f1513e4fd9b66456`；完整审核 base 仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-5351170224`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，已按规定建立正确 legacy 符号链接。
- `ad043..535117` 的 vnext 变化只有四个 Rust 路径；Cargo.toml、Cargo.lock、其他依赖锁与 backend Python 树未改。并行 FE3b 合并仅影响 frontend/docs/frontend，`6ec37dde9a` 仅归档 S5 审核文档；本轮不重审前端或代签前端结论。
- 本人未实现本轮被审代码，未改产品、测试、Contract 或被审 worktree，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

独核首次执行原件：`/home/dev/gdds-s5-logs/execution/a-focused/20261109T061526Z-ad043152b1604da1ff56ec67f1513e4fd9b66456/remote-evidence/backend-native-sync.log`，SHA256=`16905a439faa5a29a7f458dada14fd8f57739daf83a6e6ebd67382e2e3599067`。06 的 steps/session 记录 2026-11-09 06:15:29Z–06:16:28Z、精确 ad043 与 Rust tree `00fda965165d64ff8846d2205754f38d4cd4630c`，native sync command exit 1、tee exit 0；工作区检查后仍 clean，失败临时状态保留，占用标志已释放。

这是产品失败：`gateway-compute-python/src/comparison_records.rs` 中直接使用 `serde_json::json!`、`serde_json::Value`、`serde_json::from_str` 和 `gateway_shared_kernel::canonicalize_identifier`，而该 crate 无两者直接依赖，产生四个 E0433，maturin/cargo 编译退出失败。既有源码审核漏掉了该依赖解析错误；没有将它归类为工具故障、缓存缺失或无产品运行的脚本错误。原件保留，后续 focused/static/Rust 检查未运行，不能由 R4 CODE_GO 反推其通过。

## 2. 修复边界与关键逐字段核查

| 边界 | 当前修订及独核 | 结论 |
| --- | --- | --- |
| FFI 依赖解析 | FFI 不再引用 serde_json 或 gateway_shared_kernel，改消费已有 gateway-compute-core facade 的 `CacheMetadata`、`export_neutral_facts`、`validate_neutral_risk_column`。core 本来已有 JSON/shared-kernel 直接依赖；未新增依赖、锁变化或 re-export 第三方 JSON 类型。 | 四个已知 E0433 源码原因 CLOSED；实际编译待验 |
| opaque metadata | core 的 `CacheMetadata(Value)` 字段私有，`parse` 保原 JSON parse/object 拒绝条件及错误；`validate(kind, counts)` 调原精确 metadata validator，原 keys、枚举、版本、summary/count/family 规则未改，底层 Value validator改私有。FFI 中先 same-operation/active owner/control，随后 `context.reserve(json_metadata_upper(...))`，再 `CacheMetadata::parse`；facts 读取/validate 后才传三 family counts验证。没有把 parse 移到预算前，也没有绕过后续 family、risk 或 artifact/schema/count 闭合。 | 静态通过 |
| neutral facts 导出 | 原 FFI detach 内三个互斥 result 分支，改为相同 `standard/ordered/neutral` 三个 Option 借用，交 core helper。core 内仍构造相同 neutral table metadata 和 TableFactsSource，并按 STANDARD、ORDERED、BLANK 顺序调用原 exporter，前两次 clone owner，最后一次 move owner；context、max_row_bytes、原 lease/1024 batch/ordinal/frame 行为未变。公开的逐 family JSON源接口收为私有，真实 consumer 是新的整体 export helper。 | 静态通过 |
| 风险列校验 | core helper仍调用同一 canonicalize_identifier并比较原始列名；FFI仍先 null拒绝、同样逐列调用、再以同一 HashSet 拒绝重复；原错误类型/消息与循环控制点保留。没有降低 canonical/重复列约束或更改 Risk emit/业务clock。 | 静态通过 |
| M/control/资源寿命 | metadata lease仍先于解析，成功时仍转入恢复handle的 `_schema_lease`；失败时局部metadata/facts/lease/Arc owner按原栈释放。export结果仅整体成功后写入 `self.cache_facts/cache_metadata/_cache_metadata_lease`，部分失败不发布候选。same-operation identity、当前cancel/deadline、OperationUse、PythonChargeOwner和parent/last-consumer链未改。 | 静态通过，原资源向量仍待实跑 |

四路径为 core lib.rs、records.rs、records/cache.rs 和 Python adapter comparison_records.rs。完整差异已核，没有改既有 SET/scalar frame、summary/count 计算、facts digest、records family、Risk 控制顺序、M24、SQL、scope/恢复屏障或独立 golden。未引入额外治理、持久 proof 或新 DAG 边。

R1–R3 已关闭 A1–A4、Risk R2、版本常量/FFI/DAG和真实 codec owner/KEYLESS 向量的功能结论保持；本轮为编译失败做局部连续复审，不扩大原阶段范围。

## 3. 待核事项与执行状态

当前 **FINAL FORMAT / CURRENT NATIVE COMPILE / FOCUSED / STATIC / RUST = NOT_RUN**（本报告核收状态）。唯一测试角色将本固定修订在 06 的隔离 worktree 生成机械格式补丁；入最终 clean 提交后由原审核者再比对格式差异。随后以该最终提交重新开始必要 native sync/build-input、focused、五 Python 包 ruff/mypy 和 Rust 检查。首次 ad043 失败不作来源 PASS、不沿用未执行步骤；失败按原规则保原件并先修，不推进 B。

R4 原件 `/home/dev/gdds-s5-logs/reviews/a-r4-format.md` SHA256=`dc44e3d802004594b3c2aebcfbfb4921e94bd0746cfcd525ca4db610a399b150`，保留未改。本次源码 CODE_GO 仅授权继续验证输入，不代表当前编译或 A 必要执行证据已经通过。

## 4. 容器状态

Current HEAD：`5351170224c6bbe4997074338292fb04b380e64f`。Container rebuild required：本 A 子节未单独触发，依赖/锁/部署/container harness/container-only 行为均未改。Container gate for current HEAD：**deferred**，必要执行点仍为 E 最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 交接线索，本审核未重算镜像或新增 carried。


---

原件：`/home/dev/gdds-s5-logs/reviews/a-r6-format.md`；SHA256：`a6f223d72da27015d99946a25e5f562024a61c550b0db2a21ac0ad902b29519b`。

---

# P6 S5 A 连续产品复审 R6（编译修复的最终格式候选）

结论：**CODE_GO，绑定 `c1a5332a8722d3736280d8b60059944e329b8697`**。R5 至本轮仅三处 Rust 文件机械排版，原编译失败的源码修复结论保持。可交唯一测试角色正式开始 A 重验；实际编译、focused、静态及 Rust 证据仍待核，A 证据 GO 和 B 继续等待。

## 1. 固定对象与补丁身份

- Candidate：`c1a5332a8722d3736280d8b60059944e329b8697`。
- 上轮功能 Candidate：`5351170224c6bbe4997074338292fb04b380e64f`；中间 `3af4` 只写 handoff 文档。完整审核 base 仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-c1a5332a87`；创建后与报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。
- Rust tree：`180d191566f9eb95729994ea9ef3284e7fa54b78`；backend tree仍为 `240d6ccd86ca0df0df053d752e592838e626d9a8`，与 R5 完全相同。
- 07 原机械补丁：`/home/dev/gdds-s5-logs/execution/a-format-prep-07/continuation/20261109T063645Z-5351170224c6bbe4997074338292fb04b380e64f/format-continuation-1/cargo-fmt.patch`，2,980 字节，SHA256=`6c5d54755170626dd1d928a8339e0124fffd2237905e9fc991283fa59655dedf`。摘要已核；最终候选上 `git apply --reverse --check` exit 0；`core.abbrev=8` 的 `git diff --no-ext-diff --binary 5351170224c6bbe4997074338292fb04b380e64f HEAD -- vnext/rust` 与原补丁逐字同 SHA。
- 本人未改被审产品、测试、Contract 或 worktree；未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

## 2. 机械差异与结论绑定

完整核对三路径，只有 core lib.rs 的同集合导出换行、records/cache.rs 的 validator 函数签名合并为一行、comparison_records.rs 的 `metadata.validate(...).map_err(...)` 拆为多行。没有 import 成员、参数、分支、字符串、JSON/schema/family/count 条件、控制检查、预算/lease/owner 次序或固定向量变化。vnext 之外只有本轮 handoff 文档，不作为新的产品改动审核。

因此 R5 的 opaque core metadata、neutral facts 整体导出、canonical 风险列验证与 FFI 不再引用缺失直接依赖的结论，连同既有 A1–A4、Risk R2、同 M、DAG、版本/FFI 和 owner/KEYLESS 向量核查，绑定至本最终候选。没有新代码 finding。

R5 原件 `/home/dev/gdds-s5-logs/reviews/a-r5-compile.md` SHA256=`7eb2a42c1de2b15ff0e2a3550629cd61ece2aa8e74e6b0d1b8b6f9e3ce490055`，保留未改。首次 ad043 编译失败及其原件仍有效，不以本次格式比对改写为通过。

## 3. 执行稿与待验状态

只读窄核后续执行稿 `/home/dev/gdds-s5-logs/execution/a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，与首次执行稿相比未见真实阻塞：候选/Rust tree 的 40hex 校验、五节点枚举、clean main、候选 ancestor 与后续完整 vnext tree 相同均在 remote 调用前；派生路径/refs/session 只含固定字符；Cargo target 归本人 runroot，不再触碰共享 target；离线、Rust 环境约束、首失败停止、日志与 owned marker 释放均保留。此稿未由本人执行，不据此宣称检查通过。

正式参数应固定 `S5_A_CANDIDATE=c1a5332a8722d3736280d8b60059944e329b8697`、`S5_A_RUST_TREE=180d191566f9eb95729994ea9ef3284e7fa54b78`，节点由唯一测试角色只读核现场空闲与合格缓存后从授权池选择。当前 **NATIVE COMPILE / BUILD-INPUT / FOCUSED / STATIC / RUST = NOT_RUN**（本报告核收状态）。实际成功原件返回并经原审核者核收后，才能形成 A 必要证据 GO，不提前 B。

## 4. 容器状态

Current HEAD：`c1a5332a8722d3736280d8b60059944e329b8697`。Container rebuild required：本 A 子节无独立触发，未改依赖/锁/部署/container harness/container-only 行为。Container gate for current HEAD：**deferred**，必要执行点仍为 E 最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 交接线索，本审核未重算镜像或新增 carried。
