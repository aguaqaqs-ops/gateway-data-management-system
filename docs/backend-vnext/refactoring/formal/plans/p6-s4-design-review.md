# P6 S4 独立设计初审（静态）

**结论：CHANGES_REQUIRED。** 固定 base `572359d3a7719591eb21ce81d6f0b07cb18b237c`；初审候选 `ea4abd3ffdd28abd0957c5568a6ad74f18710b97`；协调者补充后的本报告最终对象 `59f523cf27c79a6e74a1990228b5e79788f613ca`（`ea4abd..59f523` 只改 S4 design/kickoff 两份文档）。审核 worktree `/home/dev/gdds-s4-design-review-ea4abd`，现为 detached `59f523`，`git status --porcelain` 空；`legacy` 链接由主仓库 `.git/info/exclude:22` 忽略。审核者未改候选或主工作区文件。下面是设计缺口，不是产品缺陷或运行 finding。

## 阻塞 finding

### F1（高）：保留的公开 renderer/schema facade 没有可执行的资源会话契约

- **设计位置：** `p6-s4-design.md:85-87,172-178`、`p6-s4-kickoff.md:22`。方案要求新 FFI 复用已初始化的进程池 N 和同一个 operation M，通用 renderer 以受限 Arrow 适配调用同一 Rust SQL 内核，并称调用方显式 operation context 计费；但保留 facade 的输入签名、启动/取消/截止/预算来源与迁移未固定。
- **源码事实：** `vnext/backend/src/gateway_backend/capabilities/mutation_planning/_repository_replay_renderer.py:95-121` 的 `render_change_set_replay(closure, *, expected_renderer_capability=None)` 可直接调用且返回 `ReplayRenderOutcome`；`storage_projection/import_replay.py:17-38` 的 schema facade 也无 context 参数。`test_dolt_renderer.py` 和 `test_storage_projection_import_replay.py` 直接消费。`comparison/native.py:53-75` 现有 native operation 则必须取得 `current_kernel_context()` 并预约 M；Rust policy §4 明确不能隐式初始化池或给宽松默认 M。
- **后果：** C 节无法同时满足保留 facade、原失败结果、单 operation M 及无预算旁路；若直接沿 comparison 的隐式 context，独立调用和测试会在无 context 下失败，若补默认 context 又绕过资源边界。DDL 从 `storage_projection` 经 `mutation_planning` 取 FFI 还会形成 capability 环；`59f523` 已明确将 DDL FFI 归已有 `storage_projection.native`，此子点已关闭。
- **最小修正/验收：** 在 A/C 固定两个公开 facade 的显式执行会话参数与错误映射（可直接要求现有 `KernelExecutionContext`），声明由 worker/测试支持层初始化既有池并提供同一 M、cancel/deadline；不自动建池/默认 M；列出旧直接调用的迁移。`ReplayRenderOutcome` 的 capability/resource 结果和 schema facade 的原错误边界保持，明确通用 ChangeSet→Arrow 适配的临时内存纳入同一 context。A 的签名/consumer矩阵及 C 的 focused 验证覆盖无会话拒绝、能力失败、资源/取消/截止。新增 DDL FFI 仍由 `storage_projection.native` 独占。

### F2（中）：未读取 parent 的 keyless 重建被误写成旧净计数，source-only NOOP 也写得过宽

- **设计位置：** `p6-s4-design.md:48-61,83` 称 changed keyless 直接重建且不读 parent，又称“强制重建的 summary 沿原 before+after 全表口径”；第 59 行称 source schema-only 候选最终仍 NOOP。`p6-design.md:531` 把 source-only NOOP 例外写为不区分表类。`p6-s4-kickoff.md:21,48` 要求计数与 NOOP 差分。
- **源码事实：** `import_publication.py:557-573` 的 `_patch_comparable` 排除 keyless；`:365-371` 只读取可比较 keyed parent；`:268-269,624-631` 对其他 parent 交给通用 planner 的是**真实 manifest + 空 rows**。`_planner.py:196-225,323-350` 的 `changed_row_count` 对完整 keyed/完整 keyless 输入是净 diff；keyless 用 digest 多重集，100 行仅改一行时完整输入净差为 2，并非 before+after=200。现 Submit 只在 `import_publication.py:279-286` 消费 `summary.operation`，没有消费该 changed count。source schema-only 的非空 keyless 因缺 before rows 不能证明 NOOP，现行为是重建；可比较 keyed 读到完整 before 后才可能 NOOP。
- **后果：** 方案会把未实际计算的数量标成旧净 diff，导致断言/报告虚假；若按文字强制 keyless NOOP，可改变现有 `replay.sql` 字节。为无消费方的旧摘要读全量 parent 又抵消逐表有界目标。
- **最小修正/验收：** Submit 小 summary 分开列 `before_count/after_count`、实际 `write_count`、decision/reason；仅真正做 storage diff 的表给精确 D/U/I 或 `net_counts`，未 diff 的强制重建记 `None/未计算`，不得称为旧净计数。通用 planner/ChangeSet 在完整输入下的原计数保持。将 source-only NOOP 缩窄到已读完整 parent 的可比较 keyed 场景（空表特例如有独立证据可另定）；keyless 非空仍按现重建。A 的独立 expected 与 B/D focused 同时核 `decision`、SQL 字节和计数字段的“未计算”语义。

### F3（中）：Storage Mutation owning Contract 的 source fallback 与已确认恢复分界冲突

- **位置与事实：** `p6-s4-design.md:186-191` 与 `canonical-storage-and-repository-boundary.md:156-175` 明确 T1 后 Attempt 已为 PREPARED，checkpoint 前冻结输入坏/缺稳定失败，checkpoint 后只能复用原包及 key。`storage-mutation-and-change-set.md:128-136` 仍写“artifact 在 Preview/Submit reuse…缺失、损坏或 digest 不匹配时，Submit 可从 durable source fallback 或要求新的 upload attempt”。后者未在本候选同步修订，读者会把 source fallback 用于已冻结 Attempt。
- **后果：** A/D 对缺 frozen 文件和缺 checkpoint 包的实现可从两个 accepted Contract 得出相反行为，影响恢复与幂等 key。
- **最小修正/验收：** 在 Storage Mutation §7 明示 Submit T1 后按 Canonical Storage 的 checkpoint 分界，禁止用 SourcePackage 或新 upload attempt 重建冻结输入/已固定包；T1 前的新 Preview、独立 external consumer 按各自 owning 规则，不借本条改变 Submit。A 的恢复矩阵和 D 的缺冻文件/坏包测试引用同一边界。

## 已核一致项与实现期验证

- DC94 的 storage key 独立判定已在 `storage-mutation-and-change-set.md:72-76` 与 S4 §3.1 写明；ordered `gid` 稳定、`no` 可更新，keyless 重复及 JCS 顺序与现 `_digest.py:39-49`、`import_replay.py:47-65` 一致。keyless mutation row digest 仍有排序消费者，区别于业务 raw-content。
- SQL 顺序和批次方案对应现 `storage_projection/import_replay.py:17-55`、`_repository_replay_renderer.py:147-268,289-421,424-527`；尤其 DELETE/UPDATE 的连续 256 窗口、UPDATE 所有非键列 CASE、`.15g`、完整 4MiB 语句、单行超限和最终 200MiB cap 都有明确设计与独立 expected 来源。数值/字节等价仍须由未来 A–E 的实际证据证明。
- 原 `import_publication.py:194-209` 预约 2528MiB 并一次打开全部 inputs，`:237-303` 又构造 Python rows/ChangeSet；S4 逐表打开/释放、DML bytes 汇集后 DDL 前置的方案与 `publish.py`/`package.py` 的 bytes API 相容。`canonical_store.py:119-215` 的 handle 持有 mapping/stream owner；实现须按 S4 §5 的先 native/stream、后 reader/mmap 顺序关闭。现阶段没有测得 2528MiB 与新 DML/native 的实际峰值，也没有证明 M24 可过；这属于 D/E 停止和验证条件，不应当作设计 PASS 或另建 spool/streaming tar 的理由。
- T1 PREPARED、checkpoint 后固定包、T2 EFFECT_PENDING、技术 main 与业务 BaselineHead 分离，以及非 INITIAL 缺/坏 parent 拒绝，除 F3 的旧 Contract 句子外，在 S4 与 Canonical Storage 叙述自洽。S3 来源 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2` 仍 BLOCKED_CAPACITY；Q18 静态 CLEAR 不解除 FE 前置。S4 的 S3-only/joint归因、W2无行比较、DC33 N1/32−8/M24 fresh t1–t4 完整旅程、冻结2×t4分组统计和100%压力单列均已写入 kickoff。

## 审核范围和证据边界

静态读取候选三份 S4 文档、`AGENTS.md`、testing-conventions 相关规则、P6设计/执行计划/DC45/55/57/78/91–94、S1a阈值/终审指向、S3累计交接/容量状态指向、Q18状态、Rust及比例化政策、Storage Mutation/Canonical Storage/Shared Encoding/Business Lifecycle/Operation Lifecycle/Repository Service/ADR0014 的相关段，以及上引现行源码与测试调用点；未运行测试、编译、lint、容器或真实数据取证。候选相对 base 仅文档变更，**本轮 container rebuild=no**；最后产品/镜像验证仍是既有 S3 来源，不能沿用为 S4 新产品证据。没有 S4 产品 V、runner exit、Compose 或性能/容量 PASS；没有实施授权、S3 exit 或 S5 放行。

原审核者可在修订固定提交上按 F1–F3 连续复审，逐项关闭；修订只需最小文本与调用契约，不因未来独立消费者或假设威胁新增机制。

---

## 连续复审：`de0eb3a8b2f9881737a183f0a4663dad9a75d67f`

**累计结论：DESIGN_CLEAR_FOR_OWNER（设计可交 Owner 判断实施授权）。** 原审核者在同一 detached 审核 WT 从 `59f523cf27c79a6e74a1990228b5e79788f613ca` 切到固定 `de0eb3a8b2f9881737a183f0a4663dad9a75d67f`，复核精确 `59f523..de0eb3`：仅 `storage-mutation-and-change-set.md`、`p6-design.md`、`p6-s4-design.md`、`p6-s4-kickoff.md` 四份文档，32 insertions/7 deletions；WT 仍 clean。原 `ea4abd` 初审与 `59f523` 增补结论保留在上文，本节逐项累计关闭，不倒改旧 finding。

| 原 finding | 复审核对与结论 |
| --- | --- |
| F1 公开facade会话/预算 | **关闭。** `p6-s4-design.md:94-111` 固定两个 facade 均必填 `KernelExecutionContext`，由 caller 管理 scope、共享已初始化 N/同 M，显式取消/截止；没有默认预算、首次调用初始化或兼容旧签名。通用 closure 的驻留/转换/结果预约到最后 consumer 有 owner，Submit package envelope 与 schema charge 的重叠需划分/保守额外预约；列出 worker 与所有现役测试调用迁移，以及无有效 context、真实扩展验证。现 `vnext/backend/tests/conftest.py:45-59` 确有 session pool fixture 和 autouse scope fixture，后者目前 `yield None`，文档要求 C 改成显式 yield context，路径可实施。`59f523` 已固定 DDL 仍归 `storage_projection.native`，不反向依赖 Mutation Planning；失败类型映射仍如 §3.3。 |
| F2 keyless/source-only 计数和 NOOP | **关闭。** `p6-s4-design.md:59,76-89` 明确 source-only NOOP 仅限实际读完整 before 的可比较 keyed；非空 keyless 的初筛仍 rebuild。新 Submit 小 summary 对未读 before/未做 diff 的强制重建记 `net_counts=None`，分列 before/after 与 INSERT 实写行数；已做 keyed diff 的 D/U/I 不截断。通用 planner/ChangeSet 的完整输入计数未更动；`p6-design.md:531-536` 和 kickoff §4 同步改断言与测试移交。此修订正确反映现 Submit 只消费 summary.operation、keyless parent 未读的源码事实。 |
| F3 T1后source fallback | **关闭。** `storage-mutation-and-change-set.md:134-141` 明确生产 Submit T1 后冻结输入坏/缺拒绝，checkpoint 后固定包/ref/raw SHA 且不得换 key；T1 前新 Preview、可选 external target 各由自身规则负责。与 Canonical Storage §5 和 S4 §7 一致。 |

复审未发现新的会改变核心方案的阻塞。原 2528MiB 包预约与 DML 字节汇集、通用 renderer 完整 SQL 字节、Arrow 最后 owner及父表校验仍是实施期按 A–E 固定 expected 和资源账本证明的项目；**本结论不表示这些未来测试已通过，也不预测 M24/目标时间 PASS**。S3 仍 BLOCKED_CAPACITY，Q18 节点核收独立，S5 不放行。候选相对 base 仍仅文档，container rebuild=no；无 S4 当前产品 image revision/source-tree、runner、Compose 或真实旅程。此次复审只读，没有测试、编译、lint、构建、容器或节点取证，也没有产品实现/实施授权。
