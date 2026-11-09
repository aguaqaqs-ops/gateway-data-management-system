# S5 C 独立产品审核归档

固定产品候选 `fdb2a69a437f669150f9c3c2eed15f220e77f7f3` 已 **C CODE_GO / EVIDENCE_GO，可进入D**；420 focused 与五包静态实际通过并由原审核收。下面同一新建 C 独立审核者原文逐字保留，原始失败不改记为成功；无 qualified runner、Compose、t1 或 carried 结论。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r1.md`；SHA256：`071949fab159dee726dc2bdac458a6576bf37037b7056976dd70fc075aff9aed`。

---

# P6 S5 C 独立产品审核 R1

结论：**CODE_CHANGES_REQUIRED**。固定候选的 metadata-first、独立 diff/export lookup、持久 payload 与当前 pair 出版主线符合已关闭设计；以下资源释放/可选保留回退和必要集成向量仍需收口。产品执行证据为 **NOT_RUN**，不签 C EVIDENCE_GO、carried 或 E。无需扩大 M、真实数据范围、威胁模型或增加依赖。

## 1. 固定对象与独立性

- Base：`c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`。
- 原提交：`e9ada96c7eb9bd1efe6c726d4055a659773a0a6b`；审核中协调者固定了后继 `984d339ffc4c5f0acfeb7f6621efe11bc8a52ad7`，本报告最终绑定后者。
- 最终 vnext tree：`f57fa8b73a3ecece6a774ee7ba55c2913a66d5ee`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`，与 B/A 相同。
- 只读 detached worktrees：`/home/dev/gdds-s5-review-c-e9ada96c7e` 与 `/home/dev/gdds-s5-review-c-984d339ffc`。各自创建后核 exact HEAD、detached、index/tracked/untracked clean；报告前最终 WT 仍 clean，legacy 正确指向 `/home/dev/gateway-data-management-system/legacy`。
- 已读完整 C 产品/Contract/测试增量，并追原 canonical schema/content binding、实际 Preview/History/Submit consumer、Comparison session/native/codec/records、Risk emit/closure、Parquet layout/cache、root borrow 与 operation M 生命周期。约束、设计及 A/B 原件的准备输入见此前准备交接；没有以设计 CLEAR 或 A/B GO 代 C 产品结论。
- 本人未参与实现，未编辑产品/测试/Contract或被审 WT，未创建子 agent，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未 push/tag。以下结论来自固定源码/Git/既有原件，只写本外置报告。

## 2. 必须修订的 findings

### C1 — P2：新增 reader 在两个准入/异常出口未完整释放，妨碍同 M 的一次回退

位置：`capabilities/snapshot_materialization/repository_ref.py:157`；`application/history/compare_jobs.py:1067`。

`ensure_committed_tables` 已调用 `_ensure_committed_tables` 成功取得新 reader 后，才执行 `retain_metadata(result, ...)`。该预约拒绝时没有关闭刚打开的 reader/batch reader；内层的异常清理已经不在调用栈。另 `_ensure_history_demands_once` 对前面已完成 commit 的异常清理仅关闭 `table.reader`，没有关闭 `table.batch_reader`。

`snapshot_table_from_arrow` 的 batch owner 是 `reader.reopen()`，有独立 Arrow reservation 和 `_ArrowLifetime` borrower。只关闭主 reader 不会关闭该借用，canonical handle/mapping 与其 M 预约要到 operation scope 最终清理才释放。因此上层捕获 MemoryError、释放可选缓存后立即重新准入时，仍带着本次失败加载留下的 backing，可能再次资源失败。这个结论已独立追到 `ArrowSourceTableReader.close`/`_ArrowLifetime.release`；协调者/实施者也主动标出了相同接缝。

最小修订：wrapper 在结果元数据准入失败时关闭本次新增的主/batch reader，保留调用者原已有 reader；History partial-load 异常同时关闭主/batch reader。关闭保持幂等，不增加全局 refcount、journal 或新恢复路径。

最小验证：一个实际 canonical reader 小向量在成功 load 后拒绝 result metadata 预约，核新增两 reader/mapping/预约释放且已有 reader可用；一个多 commit partial-load/导出失败向量核已加载 commit 的 batch 借用同步释放。无需全旅程或 syscall 故障矩阵。

### C2 — P2：持久身份保留没有进入必要计算的可选内存回退判定

位置：`capabilities/comparison/production.py:279`、`:295`、`:964`（尤其 `:975`）。

`prepare_persistent` 为首次、单次真实任务保留 `persistent_identity_charges`/完整 JCS，即使 cache miss 也保到 assembly 收尾；这部分是可选持久保留。`compare_plan_native` 的 MemoryError 分支仍只检查旧 session 的 `key_charges` 和 `cached`。单次任务没有这两项时直接抛出，不会释放上述可选持久身份后重做必要准入。即使旧 session 条件使重试发生，`evict_local()` 也不释放这些持久身份预约。

因此可以出现同一冷 miss 计划在无 cache 时可完成，却因开启可选持久保留而在 native/metadata 准入处失败的区间。后续 writer/surface 的可选驱逐入口同样只释放 cold views/risk retention，仍保留这部分身份。A 的旧局部去重回退不能证明新增持久保留不改变原业务接受范围。

最小修订：把可放弃的持久 identity/candidate retention 纳入必要准入之前的最小驱逐/一次重准入；当前确实供 restored Arrow 使用的 payload/backing 不得提前释放。若需要放弃尚未消费的命中，须先恢复它对应的 exact-commit 行需求，不能在 reader 缺席时继续冷算。保持真实 remaining uses，不伪造第二次使用，不新增调度平台或扩大 M。

最小验证：单次真实任务、真实 persistent port 的冷 miss，定向令可选身份驻留导致必要预约拒绝；断驱逐后同一计划可完成且两次拒绝/控制优先级、无残留预约符合原接口。既有 A foreign/cancel/Arrow owner 矩阵不复制，只补本次新增可选保留接缝。

### C3 — P2：当前新增集成向量未覆盖已分配给 C 的 H1 与 FULL 例外

位置：`tests/test_preview_job_assemble.py:846`；`tests/test_history_compare_jobs.py:1275`。

Preview 新向量是 Preview→Preview，History 新共享表是 History→History；二者没有跨 upload/committed authority 的实际 producer→consumer 连接。FULL 向量只断 Preview 声明两个相邻 pair，没有真的请求尚未计算的 baseline→modified，再验证首次允许计算、后续新 operation 才命中。此为 kickoff C/唯一 owner 矩阵明确要求，不能用 A 纯 key 相等/codec round-trip 或另一条 Preview replay 替代。

最小修订/验证：在现 History owner 下用一组小共享场景消费真实 Preview 形成的 computation cache，覆盖普通 H1 与 FULL baseline→modified 首次 miss/随后 H3；用新 logical operation/idempotency key，保持原 pair 集合，不提前多算。顺带核当前 facts/records/风险 target 与编号和完整 bundle 的实际结果，以及风险持久条目确被消费；独立 expected 继续取手算/现 golden。无需复制 A 风险 cap/filter/clock 或 codec 故障矩阵，不新增真实数据旅程。

## 3. 审核中已关闭的协调发现与观察

- e9 把完整 metadata 占位 table set 改成了通用 `materialize_repository_ref` 的返回形态，确会使 `infrastructure/repository_write/import_publication.py::_materialize_parent_table` 的单表 `len==1` 守卫失败，且 Preview 部分 ARTIFACTS_REQUIRED 会把无 reader 占位交给 `publish_canonical_tables`。协调者先发现后，我直接核实际 consumer。984d 的私有 `complete_table_set` 参数使新 `describe_repository_ref` 保完整占位，而原通用 materialize 继续只返回其实际行需求；summary 始终完整。该产品原因在 984d **静态关闭**，无兼容分支/proof flag；实际回归待唯一测试者。
- `_ensure_history_demands_once` 每 distinct commit 又执行一次真实 control metadata resolve，当前 `s5_history_demands` 未记录这部分，只有 `_materialize_distinct_commits` 的 metadata/catalog 计数。应按实际调用补 metadata 计数，不能增加 catalog 计数或将其写成零 I/O。协调者/实施者已主动说明该观察；它不要求新增 evidence 状态或更多测量。

## 4. 其余已核源码边界

- `describe_table` 抽取并复用原 `load_table` 的 `compute_schema_digest` + table/count/raw binding 核验；所有表先完整核 authority，才读任何行。新描述校验 repository、exact ref/pinned catalog、完整表集合与 INITIAL 空集；没有新 DAG/schema 算法或布尔凭证。
- History 恢复直接采用 v5 side/v2 document，重新解析 scope 内相同 exact commit metadata/catalog，并比较完整冻结描述；重新分别 diff/export lookup，再由 Comparison 的 `_task_arrow_inputs` 合并 actual demands。不会读 main，也没有旧 checkpoint 双读。
- canonical source descriptor 的同一 helper 同时用于 loaded reader 和 metadata-only export。layout 含源列声明/ENUM/SET labels/ordered provenance；export 在 root shared borrow 下续保护并核真实 ref/hash/footer/schema/count/layout/repository，坏文件 `discard_if_same` 不删新 writer。新的 SQLite错误没有被一般 catch 吞成 miss。
- Comparison-owned persistent envelope 保原 schema、batch rows 与空流；decode 经真实 facade/native 批量验证，坏版本精确 discard 后一次 miss。restore 在同 operation M 逐表建 phase、seal 后才准入 miss compute，Rust/core 未接 DB、路径或 I/O。
- 当前 facts/core、Parquet records/closure、risk、surface 和完整 bundle 仍走唯一出版链；没有返回旧 bundle。持久完整候选与真实 remaining uses 分开，必要 pair 输出成功后才 store/mark_used，组合信号在当前路径汇总。
- Risk 新持久 adapter 复用原完整事件 codec/emit/closure；cap（pair 优先）→候选→filter→预约/编号/append→原 clock 未改，filtered 不增加 clock。当前仅源码核查，不代表真实持久接线向量已经通过。
- restored payload 新借用计数绑定 native input owner，handle 关闭后外部实际 Arrow consumer仍可持 payload/lease/M；session 生命周期 finally 在 READY 前释放 cache intent，保 workflow/source/checkpoint owner。C1/C2 是这些局部失败准入的剩余缺口，不要求新资源框架。

## 5. 执行稿、证据与容器决定

独核外置 `/home/dev/gdds-s5-logs/execution/c-focused.sh`，SHA256=`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`。固定候选/祖先/vnext tree、clean、LAN bundle 摘要、节点原子占用、offline、selector 四工具、独立 TMPDIR/Cargo/uv 环境、native 强制重装/build-input、五包 ruff/mypy、15 backend focused、首失败停/原 numeric exit/SHA/本人资源释放均沿既有边界。15目标文件没有 serial 标记；未安排空 serial 步骤。本人只读脚本，未执行或做 bash/产品语法检查；修订加入的新目标文件或变化范围须同步最终执行稿。

所有当前 C native/build-input、五包静态及 focused 为 **NOT_RUN**。A/B focused 不是 qualified runner 来源；没有用它们作 C carried。C1–C3 修订后固定 clean 新候选，由本原审核者连续复核，再交新 C 唯一测试者在合格 CT 执行必要范围并保原件，实际结果另核。

Current HEAD：`984d339ffc4c5f0acfeb7f6621efe11bc8a52ad7`。Container rebuild required：本 C 迭代无独立触发；未改 Rust、锁/production 依赖、部署、entrypoint、容器 harness 或 container-only boundary。Last verified image revision：仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` 的交接来源，backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`，镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本审核未重算这些镜像。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选（或之后实际触发边界的必要节点）。没有当前源码镜像 GO、真实 t1 或 E 预签。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r2.md`；SHA256：`1c93a9bad0125e1e9289e64f334bc58423b920826221f845752a08e7dc66655a`。

---

# P6 S5 C 连续产品复审 R2

结论：**CODE_CHANGES_REQUIRED（仅 C3 的风险持久命中判据尚待收紧）**。C1/C2 的产品原因已静态关闭；H1/FULL 的真实 producer→consumer 向量已补入。当前候选尚未执行产品检查，不签 C EVIDENCE_GO、carried 或 E。

## 固定对象与方法

- Candidate：`372d32105af2e4c19c951ec69c64479336d32ba8`；R1 最终候选：`984d339ffc4c5f0acfeb7f6621efe11bc8a52ad7`；完整 base：`c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`。
- vnext tree：`e0e9fc8b2185adcf136faea6c8d450ceeaea3569`；Rust tree 仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-372d32105a`，创建后核 exact HEAD、detached、index/tracked/untracked clean、正确 legacy 链接；报告前再次核相同状态。
- 本人直接读取全部十路径增量，追 C1 canonical handle/Arrow borrower、C2 session/producer/retire/necessary-output 驱逐、C3 真实 Preview metadata 与 History consume、Risk facade/port 和架构规则；未实现修订、未改被审 WT/产品/测试/Contract，未运行测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。
- R1 原件 `/home/dev/gdds-s5-logs/reviews/c-r1.md` SHA256=`071949fab159dee726dc2bdac458a6576bf37037b7056976dd70fc075aff9aed` 保持未改。

## Finding 连续闭合

| Finding | 修订与独核 | 状态 |
| --- | --- | --- |
| C1 新 reader/batch 异常释放 | ensure 外层 try 覆盖 result metadata 预约及 merged kernel scope 返回时控制失败；仅对相对于输入新增的 SnapshotTable 关闭主/batch reader，主关闭异常时仍 finally 关 batch。内层加载失败原清理保留。History partial-load 分别按已有 reader/batch identity 排除原借用，关闭本次新主/batch。metadata 拒绝/return 取消共享向量核 mapping 回原集合、旧 reader/batch 仍可消费；History export 拒绝向量核新两 consumer 均已关闭。 | 产品原因静态 CLOSED；执行待验 |
| C2 可选持久身份挤占必要 M | full identity 与 map 预算内的轻量 task binding 分离；has_optional_retention 包含新 identity/pending/risk；冷 miss 失败关闭 session，原计划只再准入一次；有必要 restored handle 时只驱逐 full identity、cold views/局部保留，保 sealed backing 和轻量 binding，继续以同 operation 使用命中。retire/mark_used 使用轻量 keys，真实 remaining uses 未伪造。必要输出驱逐同时放弃 full optional identities。新增单次冷拒绝及 warm metadata 拒绝沿真实 cache port，并保 fixed golden/零输入读取/最后 Arrow consumer 的原断言。 | 产品原因静态 CLOSED；执行待验 |
| C3 H1/FULL 接线 | 一个新向量用真实 FULL Preview 三 handler 生成 B/C canonical manifests 和 cache，再把该 manifest 绑定到精确 History commits。实际请求 B→C 断 kernel0；A→C 首次断1、下一新 operation断0。实际读当前 records closure、完整节点 Parquet，手算两侧 id 和 records count，核风险当前表绑定/连续编号。 | H1/FULL 主缺口静态 CLOSED；下述风险命中判据仍 OPEN |

C1 顺带核当前完整 authority：ensure 在任何新行读取前复用原 `describe_table` 核全表和 ordered provenance；History 再 resolve 后比完整 storage facts，矛盾稳定失败。新增小向量将未需求表 raw identity 改变，要求任何新行前失败；没有新 proof bool/schema 算法/registry。

## C3 唯一剩余修订：直接观察风险 hit，不能以同 manifest 排除重算

位置：`tests/test_history_compare_jobs.py` 的 `test_full_preview_to_history_reuses_only_the_pairs_actually_computed`，当前 `current_uses & source_uses` 断言。

Comparison 的 kernel0 已证明其命中。Risk 的 `(kind, task_digest, manifest_artifact_id)` 与原 producer 相交则只证明使用/写入了同一派生值：risk encoder 是确定的内容寻址；若 Risk lookup 未接通、重算后 store 同 bytes，也会生成同 manifest id 并通过当前断言。因此这条断言尚不能满足 R1 C3 明确要求的“风险持久条目确被消费”。

最小修订是在同一向量用 test-only observer 委托真实 cache port 或 `PersistentRiskCandidates.lookup/store`，分别断 H1/H3 风险 lookup 返回 hit 且不重新 store，FULL 首次为 miss 并形成完整候选。保现实际 records/风险/bundle 内容断言；不加生产指标、功能开关或第二套风控矩阵。协调者已确认并安排该窄补丁，未把尚不存在的补丁计作关闭。

## 其他增量与执行边界

- app 的 Risk persistence 入口改为实际 Risk facade 导出；Risk persistence 的 context 类型改用已有 `RiskOperationPort`，不再 import 上游未获准的 table_access owner。沿现 DAG/精确 facade 规则核一致；没有 architecture baseline 豁免、依赖或 Contract 行为变化。
- `s5_history_demands.control_metadata_resolves` 记录本阶段每次实际 control resolve；没有伪加 catalog 计数，metadata 与实际行读继续分开。
- 原通用 materialize 形态回归在 984d 已静态关闭，本增量未重开；新完整占位只属于 describe/ensure。R1 其余 metadata authority、payload/native 当前绑定、风险控制、完整 bundle、精确条件失效与 cache pins 结论保持。
- 执行稿 `/home/dev/gdds-s5-logs/execution/c-focused.sh` SHA256 仍为 `c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`，15目标文件范围覆盖本轮新向量；未新增 serial marker，Rust 未改。当前 native/build-input、五包 ruff/mypy、focused 均 **NOT_RUN**。补丁固定并由本原审窄复核后，再交唯一 C 测试者执行，不提前跑或把源码关闭当实测。

Current HEAD：`372d32105af2e4c19c951ec69c64479336d32ba8`。Container rebuild required：本轮无独立触发；未改 Rust/锁/production 依赖/部署/entrypoint/容器 harness/container-only boundary。Last verified image revision/source 仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选或之后实际触发边界的必要节点。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r3.md`；SHA256：`cf3e2ed1e4bc8af54e1b8eb676c2c80bacd1ad17f1991079c1e81491b4d4270c`。

---

# P6 S5 C 连续产品复审 R3

结论：**CODE_GO，绑定 `3895b879b9fc6a70b7998bc00847e137dd41fbee`**。R1 的 C1–C3 全部静态关闭；本轮仅收紧风险实际命中的测试判据，没有新增代码阻塞。可交新 C 唯一测试者执行已核必要范围，实际证据仍 **NOT_RUN**；本结论不等于 C EVIDENCE_GO、qualified runner、Compose、真实 t1、carried 或 E。

## 固定对象与连续依据

- Candidate：`3895b879b9fc6a70b7998bc00847e137dd41fbee`；上一复审候选：`372d32105af2e4c19c951ec69c64479336d32ba8`；完整 base：`c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`。
- vnext tree：`1ea875f48707fc8e847ba1d04a514ae27cf3168a`；Rust tree 仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-3895b879b9`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。
- `372d..3895` 只有 `tests/test_history_compare_jobs.py` 的 22 增 1 删。产品、Contract、golden、依赖、锁、Rust 与部署不变。
- 本人未实现修订、未编辑产品/测试/Contract或被审 WT，未执行测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。
- R1 原件 `/home/dev/gdds-s5-logs/reviews/c-r1.md` SHA256=`071949fab159dee726dc2bdac458a6576bf37037b7056976dd70fc075aff9aed`；R2 原件 `/home/dev/gdds-s5-logs/reviews/c-r2.md` SHA256=`1c93a9bad0125e1e9289e64f334bc58423b920826221f845752a08e7dc66655a`，均保留未改。C1 新借用清理、C2 可选持久保留准入、完整 metadata/ordered authority 与 facade/DAG 等源码关闭依据沿 R2，不重复原审。

## C3 关闭

同一 H1/FULL 小向量现在通过 test-only observer 调用原 `PersistentRiskCandidates.lookup`，记录真实返回是否有候选；store observer 委托同一个真实 `ControlDbComputationCache.store`，只记录 RISK kind 的实际结果，没有伪造返回或换掉产品路径。每个 History 新 operation 前清空观察。

断言 H1 B→C 和后续 H3 A→C 各实际风险 hit 一次且没有风险 store，FULL 首次 A→C 实际 miss 一次并成功 store。该判据能够区分“读原值”和“重新计算后同内容地址写入”，关闭 R2 唯一剩余缺口。原实际 FULL Preview handlers/合法 canonical manifests、Comparison 0/1/0、当前 records closure/风险表绑定与编号、完整节点 Parquet 手算行和成功 producer uses 断言都保留；没有按 actual 修改业务 expected、增加生产计数或复制 A 风控矩阵。

## 必要执行与容器状态

执行稿 `/home/dev/gdds-s5-logs/execution/c-focused.sh` SHA256 仍为 `c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`。其 15 个 backend 目标已包含全部 C 修订/新增向量，仍无空 serial 步骤。下一执行参数应精确绑定本 candidate、上述 Rust tree 和实际合格空闲 CT；先核 clean/LAN 缓存与原子占用，再 offline 强制重装 native/build-input、五包 ruff/mypy 和必要 focused。首失败保原 numeric exit/log/SHA、停止后续验收并按现行修复规则处理。本人没有执行该脚本。

当前 native/build-input、五包静态、backend focused 均 **NOT_RUN**；A/B 已核 focused 不代替本次结果，也不构成 qualified runner/carried 来源。实际原件返回后由本原审核者另核 C 证据，未测 E 事项继续保留。

Current HEAD：`3895b879b9fc6a70b7998bc00847e137dd41fbee`。Container rebuild required：本 C 迭代无独立触发，未改锁/production 依赖、部署、entrypoint、容器 harness 或 container-only 行为。Last verified image revision/source 仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选或之后实际触发边界的必要节点。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r4.md`；SHA256：`32cb69442cc4e9330d271d47386c82838a0af532d59c7bbd215a675992516d9b`。

---

# P6 S5 C 连续产品复审 R4（首个静态失败修复）

结论：**CODE_GO，绑定 `07a1a380412117bb5077631648ff438ab1cc305b`**。3895 的两项 ruff 失败来自同一顶层冗余导入，当前单行删除已静态关闭该原因；C1–C3 已关闭结论保持。当前候选的实际检查仍待重新执行和原件核收，不能把本代码结论视为 C 证据 GO。

## 固定对象与独核

- Candidate：`07a1a380412117bb5077631648ff438ab1cc305b`；上次被测：`3895b879b9fc6a70b7998bc00847e137dd41fbee`。
- vnext tree：`590af901207433d901b8e8002a7a3bcb49f13131`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-07a1a38041`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。
- `3895..07a1` 仅从 `tests/test_history_compare_jobs.py` 顶层删除未使用的 `HistoryNodeRefKind`；1110 附近实际 consumer 的函数内导入和使用保留。未改产品、测试输入/断言、Contract、golden、Rust、依赖、锁或部署。
- 本人未实现修订、未编辑被审 WT/产品/测试/Contract，未运行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

## 原失败与当前边界

只读核原件目录 `/home/dev/gdds-s5-logs/execution/c-focused/20261109T090559Z-3895b879b9fc6a70b7998bc00847e137dd41fbee/remote-evidence/`：

| 原件 | SHA256 |
| --- | --- |
| ruff-backend.log | `2d537768161d3c16193b8e125a20cbb647235584dd93eb87a0226a526c5b8349` |
| session.log | `35a84a8b43158b4f1f7f0bcf7791c5fa7f1672b6a92e7f39e607fed642f5ab61` |
| steps.tsv | `733f7b8caa7b34737e21095275af1ca02e092a726de74a62234bf4a9a3cd3426` |

三项摘要均实核相符。06 3895 的前12步 command/tee0，含强制 native/build-input、五包环境同步和前三包静态；第13步 ruff-backend command1/tee0，明确报 F401 顶层无用导入及 F811 函数内重名，随后停止。backend mypy、RS 静态及15文件 focused未运行；session 记录结束 HEAD 相同且 clean、失败临时现场保留、cleanup0、本人标记释放、原入口1。该失败是源码静态 finding，非 DC68 工具重试；没有把原入口改为成功。

本单行修订不改变现有 C 语义/资源结论；可由唯一 C 测试者用原已核 `c-focused.sh`（SHA256=`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`）固定新 candidate/Rust tree参数，在合格空闲 CT 按原规则执行必要检查。当前 07a1 的 ruff/mypy/focused等仍 **NOT_RUN**；原失败原件与未跑范围保留，实际结果另行核收。

Current HEAD：`07a1a380412117bb5077631648ff438ab1cc305b`。Container rebuild required：本修复无独立触发；仅删除测试无用导入，未改依赖/部署/container harness/container-only行为。Last verified image revision/source 仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选或之后实际触发边界的必要节点。无 C EVIDENCE_GO、qualified runner/carried、Compose、t1 或 E 预签。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r5.md`；SHA256：`5f1b9a594e3d050eb5496e87596d506e7de54ec1500eb32a66de6af5489f1b94`。

---

# P6 S5 C 连续产品复审 R5（五项 mypy 失败修复）

结论：**CODE_GO，绑定 `addc576c31bb2d42c2c12cc52c56b9e58336f46d`**。五项已知 mypy 失败的源码原因已逐项修订；没有改变算法、业务预期、控制或资源条件。C1–C3 关闭结论保持。当前候选的实际静态/focused结果仍待原件，C EVIDENCE_GO 尚未给出。

## 固定对象与修订核查

- Candidate：`addc576c31bb2d42c2c12cc52c56b9e58336f46d`；上次被测：`07a1a380412117bb5077631648ff438ab1cc305b`。
- vnext tree：`930d6549e2735695ca2cae2a8eb9adaf31927dff`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-addc576c31`；创建后与报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。
- `07a1..addc` 仅四路径14增13删。pair_pipeline 将提前返回分支局部变量改名 `validated_artifacts`，保相同完整集合校验；Preview closure 用独立 `export_ref` 完成 Optional 缩窄，传入同一个必需 ref/同一个 index 路径；失败清理测试从公开 owning Snapshot facade 取 `ensure_committed_tables`，仍 monkeypatch 实际 application 调用点并委托原产品函数。
- 两处 row 预期改为显式 `SignedIntegerScalar("1"/"2"/"3")`。已追固定 owning `SourceCell` 与 `table_access.native.source_cell_from_arrow` 的 SIGNED_INTEGER 分支，以及 Shared Kernel `SignedIntegerScalar(decimal: str)`：`INT` reader 输出本来就是该 typed scalar；不是宿主 int。数值和序列保持手算输入，不从本次 actual 生成 expected，不改产品转换或业务 golden。
- 本人未实现修订、未编辑产品/测试/Contract或被审 WT，未运行测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

## 原失败与实际边界

只读核原件 `/home/dev/gdds-s5-logs/execution/c-focused/20261109T091105Z-07a1a380412117bb5077631648ff438ab1cc305b/remote-evidence/`：

| 原件 | SHA256 |
| --- | --- |
| mypy-backend.log | `4c6abf922484b41aec3864c3d675d7abe0b4e7f9f41c89932a2ec99d4929adbc` |
| session.log | `ee3d543f2c25e9eb38f16d8032cdef9dc571535351ed1b1179f6c625271a7ad5` |
| steps.tsv | `17ef3f93e7fa61a73c244c1a36081c77ba614b04ee2f5f7de22fa0f03de6c83e` |

三项 SHA均实核一致。mypy 原件明确是1项局部重定义、2项 typed row equality、1项 Optional 赋值与1项未显式导出属性，共五项四文件；command1/tee0。06 本次 session 09:11:08–09:12:31Z，前13步成功（含 backend ruff），pytest尚未启动；backend mypy失败后停止，RS静态/15文件focused未运行，原入口1。协调者和唯一执行者保留 clean/失败现场/本人标记释放事实；这些不把原失败改成成功。本轮按产品静态 finding 修订，非 DC68 工具重试。

可交唯一 C 测试者按原已核 `c-focused.sh`（SHA256=`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`）固定本 candidate/Rust tree参数在合格 CT 重验。当前 addc 的 ruff/mypy/focused等仍 **NOT_RUN**，不因代码原因关闭而签证据 GO。前两次原始失败、实际部分通过和未跑范围继续保留。

Current HEAD：`addc576c31bb2d42c2c12cc52c56b9e58336f46d`。Container rebuild required：本修复无独立触发；未改依赖/部署/container harness/container-only行为。Last verified image revision/source仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate for current HEAD：**deferred**；Carried from：none；Required execution point：E 最终候选或之后实际触发边界的必要节点。无 qualified runner/carried、Compose、t1 或 E 预签。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r6.md`；SHA256：`3e240164a9f79455de18bb1d9ea93d5db57ba0585ce71a9c529eed317ab4befa`。

---

# P6 S5 C 连续产品复审 R6（首轮 focused 失败修复）

结论：**CODE_CHANGES_REQUIRED**。七项失败对应的测试 consumer/fixture 与新输入错误映射原因已有实质修订；新增 assemble catch 范围仍会改变既有计算/出版错误分类，须按下述 C4 窄化。C1–C3 原关闭结论保持，但关键 H1/FULL 实测仍未通过，不给 C EVIDENCE_GO。

## 固定对象与原失败

- Candidate：`ad8f09120b10776b3b5919e9b85c6935e2bdeb08`；上次被测：`addc576c31bb2d42c2c12cc52c56b9e58336f46d`。
- vnext tree：`9a4faba2319c4d8da42f5908a0158fec724b2a36`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-ad8f09120b`，创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean，legacy 链接正确。完整核四路径130增62删及实际异常/fixture owner。
- 本人未实现修订、未改产品/测试/Contract或被审 WT，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。

已只读实核 addc 原件根 `/home/dev/gdds-s5-logs/execution/c-focused/20261109T091523Z-addc576c31bb2d42c2c12cc52c56b9e58336f46d/remote-evidence/`：focused log SHA256=`302146aa50a5a139b43b29b83c5ffe281239901e9b646bcebf8f35c9a06ccf04`；session=`6f4a2ffd1170ac5eb408c3e46ba7621740955e85673359dac9f3c22f9189d313`；steps=`019d8b5ab7de2aa25e8ae9d5a27aad0ae5a5f0a29a98f0bc8c3438e9002b4444`，均与报送一致。

06 09:15:25–09:17:24Z，前16步 native/build-input/五包ruff/mypy command/tee均0，第17步 focused command1/tee0，**410 passed / 7 failed / 27.64s**。原入口1、clean、失败现场保留和本人标记释放保持原件；410项通过不掩盖7项失败，尤其H1/FULL新链路尚未完整执行成功。当前 ad8f 检查仍 NOT_RUN。

## 七项修订的独核

- 两个 ORDERED 参数只导出无行 STANDARD 流，空 Arrow table不能持有该 payload backing。改借真实非空 ORDERED 族并断 num_rows>0，继续原最后 consumer 前 cleanup不可取/释放后可取断言，未弱化生命周期。
- two-node 相同规范内容的首次物理读取不属于指定 before 侧：checkpoint side map 经 JCS key序恢复，`commit-b`可先于`commit-base`。新断言按两commit全部session总计一次`t`，保完整两侧bundle值。addc 的 `_reader_names` 本来已聚合所有sessions；不能把此次失败记作其只看last session。
- 坏wire测试冻结合法两行authority后，令所有实际 runtime row stream只有一行；metadata opens不消耗按次fault。断言推进到真正ensure的assemble，仍要求原 `REPOSITORY_ROW_COUNT_MISMATCH` 和 operation/step FAILED。源码也确需处理新ensure直接抛出的deterministic provider错误，不只是改测试时点。
- Preview暖请求改用现 `build_preview_job_payload` 创建新 `idempotency_identity`；不向closed payload根添加非法 `idempotency_key`，未放宽parser/schema。
- 主reader关闭按owning `TableAccessError(READER_CLOSED)`检查，batch仍按原ValueError；不是接受未关闭reader。
- FULL共享Preview DB用既有 `seed_provisioned_mapping_with_head` 建合法父node/head/initial前置。已核schema外键是 `(repository_id,parent_node_id)`，不是source_submission；没有关外键、伪造提交旅程或改产品约束。
- materialize fresh/resume与assemble fresh authority/ensure的新增输入失败开始沿原 typed分类处理。新增两case向量在metadata step成功后注入open_timeout/catalog_error，分别要求原retryable HandlerExecutionFailure/code或稳定FAILED/code，并断零行读。checkpoint decode/pin/publication、controls与未知DB目前不在一般catch中。

## C4 — P2：assemble 对整个计算/出版块捕获通用 HistoryCompareJobError，扩大了输入错误分类

位置：`application/history/compare_jobs.py` 新 `build_assemble_comparison_handler` 的 try/`except HistoryCompareJobError`（约527–550行）。

try同时包住 fresh `_validate_described_sides` 和完整 `_assemble_comparison`。后者不仅含ensure输入读取，也经 `_run_pair_pipeline` 将原 `PairPipelineError` 包成 `HistoryCompareJobError`，并自行用同类异常报告 bundle assembly failed等。新的catch因此会把既有records/risk/surface/bundle计算或出版失败一并改报 `HISTORY_COMMIT_UNAVAILABLE`，而这些此前沿原runtime边界传播，不是本次新输入错误。

最小修订：只让 fresh authority及ensure的typed deterministic输入失败进入既有input publisher，retryable保原HandlerExecutionFailure；明确区分/局部转换新输入异常，勿按message识别。既有pipeline/bundle的HistoryCompareJobError继续原runtime边界，CheckpointDecodeError/control/unknownDB继续传播。一个最小caller回归即可核既有pipeline异常未被改分类，不新增故障平台或完整矩阵。

协调者已明确接受该窄收口并安排后继，当前报告不把尚未出现的补丁当关闭。materialize resume的fresh核验虽移入原typed try，但checkpoint解析/identity/pin/发布仍在外，范围正确；不要求重开其余C设计。

## 执行与容器边界

后继固定并由本原审连续核C4后，仍由唯一C测试者按同 `c-focused.sh` SHA256=`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`、15文件、无新增serial，在合格CT执行必要范围。当前 ad8f尚无实际ruff/mypy/focused原件。失败不归DC68工具重试，不改变expected、M24或已确认真实范围。

Current HEAD：`ad8f09120b10776b3b5919e9b85c6935e2bdeb08`。Container rebuild required：本轮无独立触发；无依赖/锁/部署/container harness/container-only改动。Last verified image revision/source仍仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件 SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate：**deferred**；Carried from：none；Required execution point：E 最终候选或之后实际触发边界的必要节点。没有qualified runner/carried、Compose、t1或E预签。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-r7.md`；SHA256：`e683dc3e3a1ceb9c85274ac7527856619c0e0022aca09dccbc7a39a2417fe80a`。

---

# P6 S5 C 连续产品复审 R7（输入错误分类收口）

结论：**CODE_GO，绑定 `fdb2a69a437f669150f9c3c2eed15f220e77f7f3`**。R6 的 C4 已静态关闭；C1–C3、七项 focused 失败对应修订的源码依据保持。当前候选尚未实际重验，C EVIDENCE_GO 继续等待原件；不把本结论反推关键 H1/FULL 或其他测试已通过。

## 固定对象与独立性

- Candidate：`fdb2a69a437f669150f9c3c2eed15f220e77f7f3`；R6 candidate：`ad8f09120b10776b3b5919e9b85c6935e2bdeb08`；完整 base仍为 `c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`。
- vnext tree：`e2bca77c31c3faccf277fdccf890ba50e0530c16`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-fdb2a69a43`；创建后及报告前核 exact HEAD、detached、index/tracked/untracked clean、正确 legacy 链接。
- `ad8f..fdb2` 仅 History handler 与其测试两路径51增14删；直接读取完整增量及所有相关catch/throw点。未改算法、Contract、业务golden、Rust、依赖、锁或部署。
- 本人未实现修订、未编辑产品/测试/Contract或被审 WT，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。
- R6 原件 `/home/dev/gdds-s5-logs/reviews/c-r6.md` SHA256=`3e240164a9f79455de18bb1d9ea93d5db57ba0585ce71a9c529eed317ab4befa` 保留未改。

## C4 关闭依据

fresh `_validate_described_sides` 现在单独处于原规则/输入typed处理范围，已知 HistoryCompareJobError 可映射原稳定输入失败。需要计算时，`_assemble_comparison` 使用另一局部try，只处理原已发布的 PairPipelineCancelled、RepositoryProviderError 与新增最小 `HistoryCompareInputError`；不再捕获通用 HistoryCompareJobError。

新 input subtype 只由二次 metadata resolve 的已知 CommitCanonicalMetadataError、冻结 storage facts不一致或table-set矛盾产生；无message识别、广义异常吞没或新重试。原 `_run_pair_pipeline`/records/risk/surface/bundle 的通用 HistoryCompareJobError 仍向原 runtime传播。materialize fresh/resume的原typed分类保持；checkpoint envelope/closed output解析、pin/发布在外，CheckpointDecodeError/control/unknownDB未捕。

单个新增真实harness caller回归在materialize成功后从assembly发出原通用pipeline错误，要求相同类型/消息向外抛出，持久operation仍RUNNING、未被误发布commit unavailable。该向量对应C4的具体边界，未建立第二套故障矩阵。C4 **静态 CLOSED**，实际执行待验。

## 重验与原证据边界

此前3895 ruff1、07a1 mypy1、addc focused7失败的原件/原exit继续保持；addc的410项通过及静态通过不等于修后候选已测。ad8f只作源码修订稿，未执行产品检查。当前 fdb2 的 native/build-input、五包静态、15文件focused均 **NOT_RUN**。

可交唯一C测试者按已核 `/home/dev/gdds-s5-logs/execution/c-focused.sh`（SHA256=`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`）固定本candidate及不变Rust tree，在合格空闲CT按原规则执行。范围含新增authority分类与pipeline caller回归，无新serial/空serial，首失败停、原numeric exit/SHA与资源收尾规则不变。本人未执行该稿；实际原件返回后再独核C证据。

Current HEAD：`fdb2a69a437f669150f9c3c2eed15f220e77f7f3`。Container rebuild required：本轮无独立触发；无依赖/部署/container harness/container-only行为改动。Last verified image revision/source仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算镜像。Container gate：**deferred**；Carried from：none；Required execution point：E最终候选或之后实际触发边界的必要节点。无qualified runner/carried、Compose、t1或E预签。


---

原件：`/home/dev/gdds-s5-logs/reviews/c-evidence-review.md`；SHA256：`5aee78c21953eeed134d50cd73dc074d1ebe01c88c16d77646bdab1d8e7c5fff`。

---

# P6 S5 C 独立证据核收

结论：**C EVIDENCE_GO，绑定产品 `fdb2a69a437f669150f9c3c2eed15f220e77f7f3`**。R7 的 CODE_GO 保持；C1–C4 的连续原审修订及本节必要 focused/静态检查已有同一固定候选的实际成功原件。C 产品与本节证据可关闭，后续 D 由新角色接手。本结论不签 qualified runner、carried、Compose、真实 t1、性能/容量或 E 最终门禁。

## 固定对象与审核独立性

- C base：`c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`；最终产品：`fdb2a69a437f669150f9c3c2eed15f220e77f7f3`。
- vnext tree：`e2bca77c31c3faccf277fdccf890ba50e0530c16`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`，与 B/A 相同。
- 只读 detached WT：`/home/dev/gdds-s5-review-c-fdb2a69a43`。本次再次核 exact HEAD、两棵 tree、tracked/untracked clean 与 `legacy -> /home/dev/gateway-data-management-system/legacy`。协调者新增交接文档没有修改该产品 WT 或被测候选。
- 原审链 R1–R7 保持，R7 原件 SHA256=`e683dc3e3a1ceb9c85274ac7527856619c0e0022aca09dccbc7a39a2417fe80a`。本次没有重开已关闭设计或用设计 CLEAR/A/B GO 代 C 结果。
- 本人未实施或编辑产品、测试、Contract、被审/被测 WT，未运行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子 agent、push/tag。只读源码、Git 和执行原件；本机 Python 仅解析现存 TSV/校验现存文件 SHA256，不消费产品代码或执行产品检查。只写本外置报告。

## 原件、身份与逐项完整性

成功原件根：`/home/dev/gdds-s5-logs/execution/c-focused/20261109T093318Z-fdb2a69a437f669150f9c3c2eed15f220e77f7f3/`。

| 原件 | 独立重算 SHA256 |
| --- | --- |
| 执行稿 `/home/dev/gdds-s5-logs/execution/c-focused.sh` | `c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a` |
| `remote-evidence/session.log` | `95ff94a694a790e48c6e4d255754a50b7e7803251bba5328636c82c03a4ad0ed` |
| `remote-evidence/steps.tsv` | `1b99944b61473bda45164a9399ff13c5d0cf681feafdb00609f6127c48b13778` |
| `remote-evidence/backend-focused-parallel.log` | `dbba5578a1e093399921f5f80f53ba77cede05b5133e783daf89e0274b0bf51b` |
| `remote-evidence/backend-native-sync.log` | `eb2b049d51c49bfdd8c1a19eaa40a3575af06ff0639596067f90c020c5b98ba9` |
| `remote-evidence/extension-build-input.log` | `9523ba40c8f7ce48385ef4eb7e66467a418f2f7f823369a68bbea1d7ffae78b0` |
| `source.bundle` | `ec128d850fed55f8349f239f60e6517a6bebd0c1009e43074ea908cd9d9c7292` |
| 本地 `SHA256SUMS` | `40b21183f56cbc69ac6169893357b9ceed83e6173ab019f2632aab5073151494` |

已重算成功批次本地 manifest 的29项与远端 manifest 的20项，全部相符；也核两份 manifest 自摘要及 orchestrator 自摘要。远端 manifest 中的原远端绝对路径按 basename 映射到原样复制的 `remote-evidence/` 后逐件校验，没有把远端路径误作本地文件。17行 step 的 candidate、每项日志摘要和 command/tee 数值均与实际日志相符。三次历史失败也分别完成同样的 manifest、自摘要、step HEAD/日志摘要核验，无不符项。

`bundle-build.log` 和远端 `bundle-verify.log` 保留 Git bundle 校验成功，bundle ref 指向 exact fdb2；本地 source main、远端 checkout、每步 HEAD、finish HEAD 均为 fdb2。bundle 大小5,648,069 bytes，摘要与 session 一致。脚本在新建 detached WT 后核 clean，添加正确 legacy 链接；结束再次核 clean。日志、环境、target、临时文件与证据均置于产品 WT 外。

## 实际成功范围

实际节点为 `ct107-gw-dms-06` / `gw-dms-06.lan`；本地开始2026-11-09 09:33:18Z，远端 session 09:33:20Z–09:35:24Z，runtime 开始09:33:21Z，最后产品步骤结束09:35:23Z。admission 原件记录整机相关资源检查、无运行 Compose 容器/8000监听与原子取得本人 busy marker。结束无遗留活动资源，cleanup_status=0，marker_released=yes；成功临时环境按稿清理。远端原入口、remote、outer tee、artifact copy、本地总入口均为0；不只以 tee 成功推定产品成功。

17步骤 command/tee 全为0，范围与已审执行稿一致：

1. backend 通过受控 `uv-consume.sh` offline 同步并显式 `--reinstall-package gateway-compute-python`。原日志实际出现 Building/Built 原生扩展，未仅复用旧安装；另四个 Python 包同步成功。
2. build-input 实核 `expected=installed=c0213e18a9645c5cfbd39f310f532273a03a10cb status=ok`。
3. shared_kernel、repository_contracts、repository_client、backend、repository_service 五包 `ruff check .`/mypy 共10步成功。mypy 分别报告34、15、26、542、201 source files 无问题。
4. 15个固定 backend 文件以 `-m '(not serial) or parallel_safe' -n 4` 实际执行，**420 passed，4 warnings，31.68s**。该目标集没有 serial 用例，无空 serial 调用或被隐去的 serial 失败。四条 warning 均是四个 worker 导入 TestClient 时的现存 Starlette/httpx 弃用提示，不是失败或跳过。

15文件为 computation_cache、comparison_cache、comparison_s3_d_production、risk_candidate_cache、risk_evaluation、history_compare_jobs、preview_job_assemble、history_metadata_materialization、repository_ref_materialization_protocol、repository_ref_materialization_digest、canonical_commit_access、canonical_table_store、snapshot_export_cache、operation_worker_contracts、architecture 的既定测试文件，未把 focused 结果写成全包 pytest 或六包权威 runner。

其中实际包含 C 的关键接缝：完整 authority 先行、分别 diff/export lookup 后合并按需行与 exact-commit checkpoint 恢复；真正 SQLite/FS 跨 operation 持久 diff/Risk；坏缓存精确条件失效/补算；同 operation/pool 的必要准入与可选保留回退；新增 reader/batch 的失败/取消释放及最后非空 Arrow consumer 生命周期；当前 records、风险 target/编号/closure、surface 与完整 bundle。C4 的两个 fresh authority 分类 case 和原 pipeline 错误不被误分类的真实 caller 回归也在这次420项中通过。

H1/FULL 向量使用真实 FULL Preview handlers 产生相邻 B/C manifest，不额外预计算 A→C。History B→C 的实际 Risk lookup 命中且无 store，kernel0；此前未计算 A→C 首次 kernel1、Risk miss/store成功；新 operation H3 再 kernel0、Risk lookup hit且无 store。风险消费由真实 lookup/store 委托 observer 证明，不以内容寻址 manifest 相同冒充实际命中。uses 对原 producer 的 kind/task/manifest 精确匹配，完整节点行与当前 records/风险预期仍来自手算或既有固定来源。该小向量没有扩大成完整真实数据旅程。

环境按受控 wrapper locked/offline 消费，session 明示 UV_OFFLINE=1、CARGO_NET_OFFLINE=true；缓存为节点本地既有预填 uv/Cargo，本次无依赖/锁变化、无公网取依赖或转发代理步骤。uv0.11.28、Python3.14.6；Rust selector下 rustc/cargo/rustfmt/clippy 均来自 `/home/dev/.cargo/bin` 的1.97.0工具链，未设置禁止的 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME。Cargo jobs4、pytest workers4是测试执行并行度，不改变产品 N1、单 active、32GiB−8GiB/M24。focused 专属小预算向量不构成额外生产 M 授权或实际 M24 容量/RSS 测量。Rust tree不变，本节实际强制 native/build-input，不宣称本次执行 Rust fmt/clippy/test。

## 历史失败原值及连续关闭

以下三批原件均仍在同一 `execution/c-focused/` 根下；其本地/远端 manifests、每步摘要及自摘要已逐件重核，失败退出未改为0，session均记录原 HEAD、clean、失败临时现场保留、cleanup0与本人 marker 释放。均是已触及产品的源码/测试 finding，不记 DC68 工具重试。

| 原件目录前缀 / candidate | 实际首失败与未执行范围 | 失败日志 SHA256 |
| --- | --- | --- |
| `20261109T090559Z-3895b879b9fc6a70b7998bc00847e137dd41fbee` | 06 session09:06:01–09:07:14Z；13步，前12步0，ruff-backend1/tee0；backend mypy、RS静态、pytest未跑；原入口1 | `2d537768161d3c16193b8e125a20cbb647235584dd93eb87a0226a526c5b8349` |
| `20261109T091105Z-07a1a380412117bb5077631648ff438ab1cc305b` | 06 session09:11:08–09:12:31Z；14步，前13步0，mypy-backend1/tee0；RS静态、pytest未跑；原入口1 | `4c6abf922484b41aec3864c3d675d7abe0b4e7f9f41c89932a2ec99d4929adbc` |
| `20261109T091523Z-addc576c31bb2d42c2c12cc52c56b9e58336f46d` | 06 session09:15:25–09:17:24Z；17步，前16步0，focused1/tee0；410 passed/7 failed/4 warnings/27.64s；原入口1 | `302146aa50a5a139b43b29b83c5ffe281239901e9b646bcebf8f35c9a06ccf04` |

addc实际收集结果合计417（410+7），不是420。最终420来自其后增加的两个 authority case和一个 pipeline caller回归；不存在把 addc 的失败改记成功。ad8f只审源码，未执行产品检查。

C1 资源清理、C2 可选身份保留回退、C3 实际 producer→consumer 与风险消费判据、C4 输入异常边界沿同一原审 R1–R7 连续关闭；首轮静态失败及 focused 七项具体原因和修订范围见各轮原文。本次实测完成代码审核时保留的执行条件，不以410旧通过或其他阶段结果补签。

## 交接与剩余边界

只读核当前未提交的 `p6-s5-c-handoff.md` 和 `p6-s5-c-review.md` 草稿：最终产品/tree、实际17步/420结果、三次失败原值与未运行范围、ad8f未执行、D新角色和E延期表述均与原件一致。R1–R7各外置原文在 review 归档中分别逐字出现一次，SHA header均与实核一致。草稿当前的 EVIDENCE_PENDING 是本报告前的真实状态；协调者可在逐字附入本报告及摘要后更新为 C EVIDENCE_GO，保留各轮原文中的历史 NOT_RUN/PENDING，不改写原件。

Current HEAD（本结论产品对象）：`fdb2a69a437f669150f9c3c2eed15f220e77f7f3`。Container rebuild required：本 C 内部 Python/Contract/测试改动未独立触发依赖、部署、entrypoint、容器 harness 或 container-only 边界；阶段最终门禁仍必须按规则绑定最终候选。Last verified image revision/source仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本节未重算其身份。Current HEAD container gate：**deferred 到 E 最终候选**；Carried from：none。

C 没有权威 runner、qualified 包来源、Compose、t1、正式性能/容量或carried结论。D 的 T3 finalize participant、RS/client控制与prepare checkpoint/DC94屏障仍由D完成；E保留全六包、适用Compose及已确认标准t1最小冷查/新operation复查与实际records/完整tar。C角色仅完成本节固定交接收尾后退场，不跨节复用；无S5 exit tag或push。
