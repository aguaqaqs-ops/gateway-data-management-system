# S5 A 独立产品审核归档

固定产品候选 `eb64578925398a6402f6e7b21790226c5f4e78e6` **A CODE_GO / EVIDENCE_GO**，可进入B；历次实际失败原件保留。该结论限A，不是权威runner、Compose、t1或S5退出GO。以下为新独立Sol原审及连续复审逐字原文；设计CLEAR未用作产品GO。各原件的SHA与本归档文件整体SHA分别记录。

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


---

原件：`/home/dev/gdds-s5-logs/reviews/a-r7-types.md`；SHA256：`10c9fc61961005acc2312de715e05889f71fd380c45ccaa5237e071b710760c0`。

---

# P6 S5 A 连续产品复审 R7（测试类型修复）

结论：**CODE_GO，绑定 `ee234028e04578e923c10969b239c41c272e259e`**。20 项已知 mypy 错误的源码原因已逐项修订，测试输入及断言未降级；可沿已核执行稿正式重验。当前修订的 mypy/后续检查尚待实际原件，A 证据 GO 与 B 继续等待。

## 1. 固定对象与独立性

- Candidate：`ee234028e04578e923c10969b239c41c272e259e`；上轮被测候选：`c1a5332a8722d3736280d8b60059944e329b8697`。
- Rust tree仍为 `180d191566f9eb95729994ea9ef3284e7fa54b78`，精确不变，无须另做 Rust 格式准备；完整审核 base仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-ee234028e0`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。
- `c1a533..ee234` 唯一 vnext 路径为 `vnext/backend/tests/test_comparison_cache.py`，41 增 33 删；中间 `8925` 只归档文档。产品代码、Contract、锁、Rust 和依赖均未改。
- 本人未实现本次被审修订，未改产品、测试、Contract 或被审 worktree，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

## 2. 失败原件与实际运行边界

独核 `/home/dev/gdds-s5-logs/execution/a-focused/20261109T063945Z-c1a5332a8722d3736280d8b60059944e329b8697/remote-evidence/mypy-backend.log`，SHA256=`03ac3643943e472b10bb08ef201889d4b0d8efd437230c766afd2724f75cb90e`；同目录 steps.tsv SHA256=`bedb28c0d21e67f2eec2c8b570e79ceda5098e05ffde2853f6ec9e395aba78a3`，均与交接一致。

该次在 06 固定 c1a533/Rust tree运行：native sync、精确 extension build-input、五包环境同步、shared_kernel/repository_contracts/repository_client 的 ruff/mypy、backend ruff均 exit 0；backend mypy在 536 个 source files中报告本新测试文件20项错误，command exit 1、tee exit 0后停止。session记录工作区仍clean、失败状态保留、占用已释放。repository_service静态、Rust和backend focused未运行。该次不是完整 A GO，也不是 qualified runner 来源；部分实际成功不能冒称后续成功或当前 ee234 全部通过。

## 3. 单文件逐项修订核查

| 错误组 | 当前修订与对照结果 |
| --- | --- |
| descriptor动态字段字典 | row_count/content/schema/compare_key四分支改为显式replace，分别仍为原+1、different-content摘要、different-schema摘要及空key；仍只去掉current reader而保descriptor mutation。四种输入、参数表和identity差异断言不变。 |
| Optional policy | 先取局部policy并assert非None，再复用该局部替换policy/storage字段；没有移除原有效性assert，也没有将可空类型强行cast。 |
| 两侧storage动态替换 | before/current facts、descriptor和最终policy字段显式分支，`ComparisonStorageFacts | None`只表达原本允许的missing mutation。missing、source_schema、canonical_schema、content、projection、view、effective_key、partial_schema、partial_projection、partial_content十项均与原字典值和侧别逐项一致；其余参数表及NotCacheable/摘要改变断言原样保留。 |
| KEYLESS变量类型冲突 | SQL循环字符串改名insert_rows，解析facts列表改名fact_rows，所有使用点一致。2增1删0改、三occurrence identity、frozen a/b frame、family/count与restore digest断言不变。 |

完整差异没有新增ignore、cast或Any；既有Any未扩大。没有修改业务expected、frozen向量、错误类型、当前M/控制/释放向量，也没有跳过测试。20项已知类型错误的源码原因静态关闭，但是否通过mypy仍须实际执行。

R6及之前的产品源码结论原样保持，R6原件 `/home/dev/gdds-s5-logs/reviews/a-r6-format.md` SHA256=`a6f223d72da27015d99946a25e5f562024a61c550b0db2a21ac0ad902b29519b`，保留未改。未借本次测试修复重开设计或扩大测试矩阵。

## 4. 下一次输入与容器状态

沿已核 `/home/dev/gdds-s5-logs/execution/a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，正式参数绑定本 candidate及上述不变Rust tree；唯一测试角色核空闲/合格缓存后实际执行，保首失败停止规则。当前候选 **NATIVE/BUILD-INPUT / FIVE-PACKAGE STATIC / RUST / FOCUSED = NOT_RUN**（本报告核收状态）；既有c1a533部分成功只记录为其自身运行事实，不作为包闭包沿用或完整门禁来源。

Current HEAD：`ee234028e04578e923c10969b239c41c272e259e`。Container rebuild required：本 A 子节无独立触发，未改依赖/锁/部署/container harness/container-only 行为。Container gate for current HEAD：**deferred**，必要执行点仍为E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像或新增carried。


---

原件：`/home/dev/gdds-s5-logs/reviews/a-r8-clippy.md`；SHA256：`29d48f17d2238797b5f0a4cfdb2e4352b754e9e7dd10b4ac0440af11226bfbc9`。

---

# P6 S5 A 连续产品复审 R8（局部 clippy 收口）

结论：**CODE_GO，绑定 `0ddc7ec6485aa3b373934dea1a4daccec87b6490`**。局部 too_many_arguments 豁免有明确既有边界依据，未改执行语义；可交唯一测试角色按同稿重验，无须另做格式准备。实际 fmt/clippy/core/focused仍待当前候选原件，A 证据 GO 与 B 继续等待。

## 1. 固定对象与独立性

- Candidate：`0ddc7ec6485aa3b373934dea1a4daccec87b6490`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 上轮被测候选：`ee234028e04578e923c10969b239c41c272e259e`；完整审核 base仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读 detached worktree：`/home/dev/gdds-s5-review-a-0ddc7ec648`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy链接正确。
- `ee234..0ddc` 唯一差异为 `vnext/rust/gateway-compute-core/src/records/builders.rs` 新增三行，没有其他产品、测试、Contract、依赖或锁变化。
- 本人未实现本次修订，未改产品、测试、Contract或被审worktree，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。

## 2. 原失败与修订核查

独核 `/home/dev/gdds-s5-logs/execution/a-focused/20261109T064444Z-ee234028e04578e923c10969b239c41c272e259e/remote-evidence/rust-clippy.log`，SHA256=`c277a511c4feace32df88e9e9a65627372ceac2cbee6a4e100393a2ad46b1031`，与交接一致。原失败为恢复函数8参数超过clippy阈值7，command exit101、tee exit0；属于实际产品静态失败，原件保留。

同目录steps/session记录06固定ee234运行：native sync、精确extension build-input、五包ruff/mypy和Rust fmt均exit0，clippy首失败后停止。工作区仍clean、失败临时状态保留、占用已释放；core cache tests与backend focused未运行。该次不能作完整A GO或qualified runner来源。

本次只在 `restore_records_batches` 紧邻处增加两行说明及 `#[allow(clippy::too_many_arguments)]`。说明要求显式保留每次调用的limits、当前operation context和存活external owner；与同模块族 `source.rs::build_standard_records` / `build_standard_records_from_ordered` 已有同名局部豁免及owner说明一致。该豁免仅作用于本函数，未扩至module/workspace或其他lint。

逐字对照函数签名与函数体，无参数、分支、限额、校验、资源释放、输出/schema/batch边界或固定expected变化。保留显式family/detail/table/neutral/max_records/max_row_bytes/context/owner有助核对恢复边界；为满足参数数量新建包装类型没有当前需要。本次不扩大机制，也不修改业务算法。

已知clippy阻塞的源码原因关闭，无新代码finding；先前A1–A4、Risk R2、同M、DAG、FFI和R7测试类型结论保持。R7原件 `/home/dev/gdds-s5-logs/reviews/a-r7-types.md` SHA256=`10c9fc61961005acc2312de715e05889f71fd380c45ccaa5237e071b710760c0`，保留未改。

## 3. 实际重验与容器状态

继续使用已核 `/home/dev/gdds-s5-logs/execution/a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，参数固定本candidate及Rust tree，由唯一测试角色核空闲/缓存后运行。手工新增注释/attribute不需另产格式补丁；正式 `cargo fmt --all --check`仍执行，未以本代码审核代替fmt结果。当前候选必要native/build-input、五静态、Rust和focused执行核收状态均为 **NOT_RUN**，既有ee234成功只记为其实际部分事实。

Current HEAD：`0ddc7ec6485aa3b373934dea1a4daccec87b6490`。Container rebuild required：本A子节无独立触发，未改依赖/锁/部署/container harness/container-only行为。Container gate for current HEAD：**deferred**，必要执行点仍为E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像或新增carried。


---

原件：`/home/dev/gdds-s5-logs/reviews/a-r9-fixtures.md`；SHA256：`30c90acb5d137d85477e39eb7ca0a0942975dcb07237c1a46e3223c16a028699`。

---

# P6 S5 A 连续产品复审 R9（完整 fixture 与 owning writer schema）

结论：**CODE_GO，绑定 `18b79112fafa55cf4a318585328fefa079c6481a`**。两处测试修订对应已核失败原因，未削弱完整绑定或改变冻结业务预期；可交唯一测试角色同稿正式重验。当前focused成功及完整A证据仍待实际原件，B继续等待。

## 1. 固定对象与独立性

- Candidate：`18b79112fafa55cf4a318585328fefa079c6481a`；上轮被测候选：`0ddc7ec6485aa3b373934dea1a4daccec87b6490`。
- Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`，精确不变；完整审核base仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读detached worktree：`/home/dev/gdds-s5-review-a-18b79112fa`；创建后及报告前核exact HEAD、detached、index/tracked/untracked clean，legacy链接正确。
- `0ddc..18b` 唯一vnext差异为tests/support/comparison_cache_inputs.py与test_comparison_cache.py，共7增7删；中间仅并行前端文档合并，不属于本轮产品审核。产品guard/Contract/Rust/锁/依赖未改。
- 本人未实现本修订，未改产品、测试、Contract或被审worktree，未运行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。仅作源码、Git和既有原件核查；外置诊断脚本未作为执行证据。

## 2. 首次 focused 原件与根因

独核 `/home/dev/gdds-s5-logs/execution/a-focused/20261109T064827Z-0ddc7ec6485aa3b373934dea1a4daccec87b6490/remote-evidence/backend-focused-parallel.log`，SHA256=`be4d3bf38e6c64ef89ac84a6c4c77bff3533bc959c96a5a02ae6834e82006b06`。同目录steps.tsv实际SHA256=`342d63bc08b549db252094dbec1877bb72183a0e19d308d67c160ea9feb62afb`。

06固定0ddc运行中，native/build-input、五包ruff/mypy、Rust fmt/clippy及core cache focused均exit0；backend parallel focused为56失败、222通过，command exit1、tee exit0后停止，serial未启动。工作区仍clean、失败临时状态保留、占用已释放。失败并未被解释成工具故障，也不能把前面的局部成功视为完整A GO或qualified runner来源。

独核两项实际问题：

1. Snapshot Materialization的 `materialize_source_arrow` 对所有成功表都携带SOURCE_MISSING_STABLE_KEY的SnapshotTableOrderedMetadata；该metadata表达可用来源事实，并不是ORDERED角色声明。原helper以metadata非None推断ordered，从而对STD(id,note)虚造GID_NO_V1/structural(no)，被 `_complete_side` 的完整列集合守卫正确拒绝；S3D session同用此helper，无法得到声明key。该guard及真实canonical writer proof应保留。
2. ORDERED roundtrip失败已通过identity、restore和facts digest，在Parquet rawSHA比对失败，不属于上述binding拒绝。新测试把native reader.schema直接交 `_write_arrow_parquet`；真实 `publish_records_family_arrow` 及既有frozen S3C测试则采用owning `_schema_for`。native Arrow metadata来自Rust HashMap，语义相同schema不能替代既有writer schema的固定序列化。应接回原writer路径，不能修改golden或新增产品排序机制来适配测试。

## 3. 固定修订逐项核查

- helper新增keyword-only `ordered: bool=False`并删除由ordered_metadata推断角色的语句。现有storage_facts存在时仍优先保留原storage_rule_view；无原facts时才按调用方明确角色构造小fixture view，canonical writer、schema/content/version值保持。
- 核对所有调用点：`_planned(ordered)`的before/current两侧均传同一实际声明；S3D `_session_bound`、second-pair writer、SET和KEYLESS输入均为STANDARD，保持默认False。没有将列名或reader availability当作角色推断依据。
- roundtrip Parquet调用改用 `_schema_for(RecordsArtifactFamily(family), None, identity.task_input.detail_policy)`，与既有S3C/真实publisher同一owner schema；实际batch仍是恢复handle导出的batch，未改数据、batch边界、family、detail或预期来源。
- 冻结raw SHA/content digest、完整facts digest、KEYLESS净计数/occurrence/frame与所有negative/资源断言均原样保留。无新增ignore、cast、产品guard放松、expected更新或测试跳过。

两项根因在源码中关闭，没有新代码finding；R1–R8既有产品语义、同M/控制/owner、完整binding、DAG/FFI和风险冻结核查结论保持。R8原件 `/home/dev/gdds-s5-logs/reviews/a-r8-clippy.md` SHA256=`29d48f17d2238797b5f0a4cfdb2e4352b754e9e7dd10b4ac0440af11226bfbc9`，保留未改。

## 4. 实际重验与容器状态

沿已核 `/home/dev/gdds-s5-logs/execution/a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，参数固定本candidate及上述不变Rust tree；唯一测试角色核空闲/缓存后执行。当前候选必要native/build-input、五静态、Rust及focused核收状态仍为 **NOT_RUN**，实际通过后再核原件形成A证据结论，不提前B。

Current HEAD：`18b79112fafa55cf4a318585328fefa079c6481a`。Container rebuild required：本A子节无独立触发，未改依赖/锁/部署/container harness/container-only行为。Container gate for current HEAD：**deferred**，必要执行点仍为E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像或新增carried。


---

原件：`/home/dev/gdds-s5-logs/reviews/a-r10-semantics.md`；SHA256：`91a07eda1a5d32f83a9272b0d406b32484462d55400cf26a1b5cc796fdf157ed`。

---

# P6 S5 A 连续产品复审 R10（三项语义修订）

结论：**CODE_GO，绑定最终 `eb64578925398a6402f6e7b21790226c5f4e78e6`**。STANDARD 无关 provenance 导致的 key 差异已修，两个新增测试预期依据固定旧源修正而非按本次actual重录；可交唯一测试角色同稿正式重验。完整A证据与B继续等待。

## 1. 固定对象与原失败

- Candidate：`eb64578925398a6402f6e7b21790226c5f4e78e6`；上轮被测候选：`18b79112fafa55cf4a318585328fefa079c6481a`。中间单测试提交cc3b不单独作为本轮候选，未改写已引用提交。
- Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`；完整审核base仍为 `fd9e383d76642037e4b3246c847222ea9483e033`。
- 只读detached worktree：`/home/dev/gdds-s5-review-a-eb64578925`；创建后及报告前核exact HEAD、detached、index/tracked/untracked clean，legacy链接正确。
- `18b..eb` 仅task_input.py及test_comparison_cache.py，20增6删。未改golden、Contract、算法、锁、版本、Rust或依赖。
- 本人未实现被审修订，未改产品、测试、Contract或被审worktree，未运行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。

独核 `/home/dev/gdds-s5-logs/execution/a-focused/20261109T065929Z-18b79112fafa55cf4a318585328fefa079c6481a/remote-evidence/backend-focused-parallel.log`，SHA256=`1df0e5a7bb56111c1e8449188d6987fa5373c9aab4938477929b89affff67ead`。06固定18b运行，native/build-input、五包静态、Rust fmt/clippy/core cache focused均通过；parallel focused275通过、3失败，command exit1/tee exit0后停止，serial未启动。session记录HEAD仍18b且clean，失败状态保留、占用已释放。失败原件不覆盖、不当qualified runner来源，未跑项不写通过。

## 2. 旧源依据与逐项修订

### STANDARD reader载体与key

所有成功Snapshot Materialization表均可携带OrderedMetadata，STANDARD native请求不消费该metadata。原任务projection无条件纳入before/current ordered metadata，移除table资源时变None，导致相同STANDARD纯任务key变化。当前仅在 `native_kind == "ordered"` 时保留两项metadata；STANDARD两项投影为None，其他descriptor、完整storagefacts、resolved policy/rules、scope、方向、diagnostics、detail、版本和native request原样保留。

ORDERED仍由原ordered_policy读取两侧blank provenance，且继续把完整OrderedMetadata写入projection；没有通过全局删除provenance或未分类字段来缩小key。缺必要ORDERED输入仍走原拒绝/不可缓存路径。原table=None等key断言保留，并新增只清reader/artifact/batch_reader三项资源、保descriptor/provenance的等key断言，覆盖两种资源表达。

### KEYLESS values

固定 `vnext/fixtures/golden/comparison/s3-e/old-python-expected.json` 声明old_algorithm_source=`4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec`、source_commit=`a9da0c59277e3179f34d646eabcd9c185917ae05`。本人分别用Git只读核两份固定旧源：standard.py::_compare_keyless647–663仅构造kind与occurrence identity，不附before/current values；S5前base fd9e的Rust compare_keyless也明确before/current=None、value_columns为空。

因此本新增test改为明确断言三条记录的两侧values均空，有独立冻结来源依据。2增1删0改、ROW_ADDED/ROW_ADDED/ROW_DELETED序、三个不同occurrence identity、restore记录数/完整digest断言全部保留；未改业务实现以输出原不存在的values，也未改既有golden。

### SET与NULL frame

同固定旧源a9da standard.py528–555的keyed modified只输出changed列；fd9e Rust亦以changed作为value_columns。原新增输入note两侧NULL，note不该出现在modified values。当前改输入为NULL→`x`，使note确为changed列，保留测试的NULL覆盖目标。

独立逐字核预期：NULL scalar frame为`0000`，string `x` 为tag20/length01/payload78，即`200178`；非空SET仍为冻结sequence `020320016103200162`，空SET仍为`00`。before/current列序、fact/restore digest和资源finally保持。源注释指向的a9da行号/实现已核，不据新actual生成expected。

本轮三个原因在源码中关闭，无新代码finding；原A1–A4、Risk R2、同M/控制/owner、完整binding、DAG/FFI等结论保持。R9原件 `/home/dev/gdds-s5-logs/reviews/a-r9-fixtures.md` SHA256=`30c90acb5d137d85477e39eb7ca0a0942975dcb07237c1a46e3223c16a028699`，保留未改。

## 3. 待验与容器状态

沿已核 `/home/dev/gdds-s5-logs/execution/a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，参数固定本candidate及不变Rust tree；唯一测试角色核空闲/缓存后实际重验。当前必要native/build-input、五静态、Rust及focused核收状态仍为 **NOT_RUN**；源码GO不代替本轮执行，不提前B。

Current HEAD：`eb64578925398a6402f6e7b21790226c5f4e78e6`。Container rebuild required：本A子节无独立触发，未改依赖/锁/部署/container harness/container-only行为。Container gate for current HEAD：**deferred**，必要执行点仍为E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像或新增carried。


---

原件：`/home/dev/gdds-s5-logs/reviews/a-evidence-review.md`；SHA256：`59ad4241f82584c7eabb97d785519026d7ccd4a46021f876a1049ccec2c10e05`。

---

# P6 S5 A 独立执行证据核收

结论：**A EVIDENCE_GO，可进入 B**。此结论仅覆盖已审 A 纯任务身份、neutral codec、真实 facade 恢复与 Risk 候选/重放所需的 focused 和静态证据；不等于六包权威 runner、qualified runner 来源、Compose、真实 t1、S5 E 退出或性能测量通过，不作 carried 判定。

## 1. 精确输入与独立性

- 实际成功被测候选：`eb64578925398a6402f6e7b21790226c5f4e78e6`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`。CODE_GO 原件为R10，SHA256=`91a07eda1a5d32f83a9272b0d406b32484462d55400cf26a1b5cc796fdf157ed`。
- 核收时文档候选：`22a1168a5c23bc403971a312be67eb1a6b0f88b0`，只读detached worktree `/home/dev/gdds-s5-review-a-22a1168a5c`；exact HEAD、detached、index/tracked/untracked clean、正确legacy链接均已核。
- eb645与22a116的完整vnext tree同为 `82db2123363c543a02d745bbe03dea2e226c4305`。区间仅审核归档/handoff/coordinator及Comparison Contract两句说明；Contract精确表述R10已核STANDARD无consumer的metadata不入key、ORDERED保实际provenance，未新增业务或执行边界。
- R7、R8、R9、R10外置原件的全部字节分别在22a116审核归档中出现恰好一次，摘要与原件均一致；未将修订摘要替换为原审报告。
- 本人是原独立审核角色，未实现被审产品/测试/Contract，未在开发机或其他节点执行产品检查，未写被审worktree、未启动额外诊断/测试、未创建子agent、push/tag。本轮仅核Git、原件、摘要和执行稿，报告写worktree外。

## 2. 成功运行原件与身份

原件根：`/home/dev/gdds-s5-logs/execution/a-focused/20261109T070802Z-eb64578925398a6402f6e7b21790226c5f4e78e6`。

| 对象 | SHA256 |
| --- | --- |
| source.bundle | `cdc25cc8508a7e3c0d41113a7afe154ddc40f611c6305d9654fe02a61ab86e12` |
| remote-evidence/session.log | `42165529ec42ee26e805fb635bc2daa7cb52d89e8f77790cf2b3497cc629c04b` |
| remote-evidence/steps.tsv | `b42d2cbfdeb658d44b85aabce280c1ed7df90b1812af1336dc433496ebbdcd87` |
| local SHA256SUMS | `f8ceec080d1925f5e7f2f392355acf4f4072d5f06fd0c8aa9f13ac10dd2b7026` |
| remote-evidence/SHA256SUMS | `7ede28a093558196bf2b79ce67f86bfabbaa66ad62ccbd8f7ed2d8f62a8637dd` |
| backend-focused-parallel.log | `82c3fcef4fa64213d66afe838b03c4f8597af63db666bd32ffa7aa4fbd896d53` |
| backend-focused-serial.log | `0f5f3a4a5c582839880bbff3606cae6d7e891db88d03ac7e427d94a5f0e61c48` |

本人逐项重算最终local清单33项、remote清单24项的文件摘要，均匹配；清单自身的SHA256SUMS.sha256和orchestrator.log.sha256也分别匹配。remote清单按复制后的同名原件核对，未把原绝对测试节点路径不存在误当摘要差异。另逐行核steps的全部日志SHA、HEAD、command/tee exit；实际为 **21个执行步骤，22行含表头**，全为0。交接文字中候选/时间/步骤计数笔误已更正，以下均以固定原件为准。

现场与来源：BatchMode SSH接通，06原子获取本人标志前后均核空闲，admission记录Compose为空、8000未监听；固定bundle经LAN传输后摘要与remote verify相符。测试worktree为已提交clean detached输入。执行稿为已独核 `a-focused-next.sh`，SHA256=`fb7ad84fa7a4e7d9641dd2f802e2e51c314f063e8e28703f200d0d2d3c933d8e`，没有另跑诊断稿或无修改重跑旧失败候选。

## 3. 实际结果与工具/资源边界

运行节点 `gw-dms-06.lan`，session UTC为 **2026-11-09 07:08:05Z–07:10:14Z**；开始/结束及每步HEAD均为eb645，Rust tree精确一致。UV_OFFLINE=1、CARGO_NET_OFFLINE=true，使用本节点预填缓存；PATH以/home/dev/.cargo/bin开头，禁止设置RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME的入口守卫保持。selector、rustc/cargo/rustfmt/clippy-driver均为同一1.97.0工具链；uv为0.11.28。未新增依赖或修改lock，也未从开发机运行测试。

| 步骤组 | 实际结果 |
| --- | --- |
| 五包locked offline sync | 通过；backend显式 `--reinstall-package gateway-compute-python` 并带当前 `GATEWAY_RUST_BUILD_INPUT`，日志确认实际构建native。 |
| extension build-input | 通过；expected=installed=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。 |
| 五包ruff/mypy | shared_kernel、repository_contracts、repository_client、backend、repository_service各自通过；mypy实际分别检查34/15/26/536/201个source files。 |
| Rust fmt/clippy | `cargo fmt --all --check`及workspace/locked/offline/all-targets clippy -D warnings通过。 |
| Rust core cache focused | 4 passed、0 failed；覆盖独立三family facts、固定完整JCS replay、scalar/SET分立帧规则及非法blank/frame。其余过滤项未冒称运行。 |
| backend parallel focused | 278 passed；7个已审范围文件，4 workers，按非serial/parallel_safe表达式执行。 |
| backend serial focused | 1 passed、278 deselected；按serial且非parallel_safe、-n0执行，未将deselected误计为运行。 |

实际backend范围为新Comparison cache、现Comparison production/session、Arrow/frozen、小型Contract vectors、architecture/import guard、Risk candidate cache和Risk evaluation。独立冻结facts/Parquet向量、完整binding变更、异scope/同M控制与释放、empty schema、SET/NULL、KEYLESS multiset、Risk空编码/解码控制及资源向量由上述实际focused执行覆盖。没有重录业务golden或为了通过修改旧算法expected。

session最终记录worktree_clean_after_checks=yes、successful_run_temp_state_cleanup=attempted、cleanup_status=0、marker_released=yes、original_or_final_exit_code=0；受核执行稿只在dolt/pytest/cargo/uv/rustc/clippy进程、容器和8000均空时清本人runroot临时资源与释放标志。local兜底release随后记录标志已释放/非本人且exit0，没有移除他人占用；日志复制、SSH/tee及local orchestrator均exit0。失败旧runroot按原约束保留，未借本次成功清理他人或历史证据。生产N1/单active/M24与测试workers独立，未增加预算或扩大真实范围。

## 4. 五次原失败与闭合

五次失败原件均保留在a-focused目录。本人对各次local/remote原始清单、清单自身及orchestrator摘要重新核对，分别核20、46、54、58、58项，全部匹配；数字包含清单/日志重复绑定，不代表测试数。每次原首失败及后续未运行项目仍按原件记载，未将失败run变成PASS来源。

| 原候选 | 原首失败 | 连续修订及当前闭合 |
| --- | --- | --- |
| ad043 | native compile exit1，4个E0433 | R5/R6移回core facade、保预算/owner顺序；最终native构建及build-input实际通过。 |
| c1a533 | 新测试mypy20项，exit1 | R7显式字段/narrowing/变量名；最终五包静态通过。 |
| ee234 | restore函数参数数clippy，exit101 | R8仅局部allow与既有边界说明；最终workspace clippy通过。 |
| 0ddc | parallel56失败/222通过，exit1 | R9显式fixture角色与owning writer schema，保完整guard和golden；最终同范围focused通过。 |
| 18b | parallel3失败/275通过，exit1 | R10按native consumer分类provenance，并据固定旧源修新增KEYLESS/SET向量；最终同范围278+1通过。 |

Risk R1/R2、A1–A4和后续源码findings均已原审连续关闭；本轮实际原件补齐A所需执行证据。未留需Owner选择的新业务语义或本范围阻塞。**现在可以在实际最新main继续B**，B持久entries/uses/TTL、operation强pin事务/lease/root read_session及其focused仍须作为新范围独审，不能由A结果预签。

## 5. 容器与退出边界

Current reviewed docs HEAD：`22a1168a5c23bc403971a312be67eb1a6b0f88b0`；实际被测产品HEAD：eb645。Container rebuild required：本A子节无独立触发，未改依赖/锁/部署/container harness/container-only行为。Current container gate：**deferred**，必要执行点仍为E最终候选或后续实际触发边界；Carried from：none。Last verified image/source-tree仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`交接线索，本审核未重算镜像或新增carried。

本次不是run-tests.sh权威完整运行，没有qualified runner闭包manifest，也没有Compose、真实t1或性能测量结果。E仍须按最终实际闭包完成规定全六包/容器/最小真实旅程及独立退出核收，不能据本报告提前标记S5 exit。
