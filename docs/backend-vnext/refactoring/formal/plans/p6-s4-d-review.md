# P6 S4 D 独立审核原始记录

2026-11-08。状态：**D 产品 V `41d1944208` 阶段 GO（源码＋focused），H2 `9d91653ac9` 文档核收**。r4 首轮失败原件仍保留，不倒签。E 的完整门禁、镜像、真实数据和资源结论未运行。

## 固定准备对象

- 准备基线 `462981862b2d128c678c2941683046f82c807ca6`；只读 detached worktree `/home/dev/gdds-reviews/p6-s4-d-prep-462981862b`，`legacy` 已链接且忽略，status clean。
- 已读仓库 `AGENTS.md`、testing-conventions、S4 固定设计/kickoff/review prompt/coordination、A–C handoff 与原审、P6 设计/执行/DC96、Storage Mutation/Canonical Storage/Shared Encoding/Business Lifecycle/Operation Lifecycle/Repository Service/External Effect owning 文档、ADR 0014、Rust 与比例化政策，以及当前 Submit、parent access、native handle、publisher/checkpoint 源码。设计 `de0eb3a8b2` 的既有清除不重开。
- root 通知 S3 最小 port `1ecb17f6de4c71ddb001a6829d2222cd28bacb34`；仅四路径，D 候选将含 port。S3 原候选及 C `48053253f9` 的节点结果不能作为 D 当前候选通过证据。

## 候选源码核点

1. 完整 frozen manifest、closure、每张 after IPC 的 repository/descriptor/schema/count/content 绑定；NOOP 仍打开完整 after；异常逐表释放。删除旧全量 Python row/ChangeSet path 与无消费者 import wrapper/support，通用 planner、外部 ledger、publisher/package/readback/recovery 保留。
2. 非 INITIAL parent 先以精确 technical commit 验完整 catalog，按需每表取真实 before；cache miss 同 commit 回填且核 count/content。committed reader 的 trusted flag 只能由真实核验 owner 在成功后赋予，reopen 保实际 backing、同 M 和 close 语义；不造假 artifact/IPC。source-only keyed 零差 NOOP，keyless 不读 before 的 rebuild 不能填净差。
3. `summary → choose_table_mutation → apply_decision/render → close` 顺序；同 operation M/N/cancel/deadline。前表 native/index/input 释放后再开下表，输出 bytes 及 DML 汇集的最后 owner 和既有 2528 MiB package envelope 清楚，不用 RSS 缩约。
4. 删除表 DROP、所有 rebuild DROP+CREATE、再全表 DML；DDL 顺序和 DML UTF-8 顺序分开。`DDL + DML ≤ 200 MiB` 在发布前精确判定；保原 SQL/golden/独立 expected，错误分类不吞取消、截止、资源拒绝。
5. `publish_canonicalization` 的 full target manifest 与完整 structural import input、checkpoint/parent binding、expected-parent CAS、保护、unknown outcome/readback 及技术 main/业务 BaselineHead 边界保持。临时 `architecture_baseline.storage` 须真实接线后删除。
6. 测试按 owning Contract 语义移交，检查旧测试独有断言；精确脚本经本人静审后由唯一 Luna 在专用节点执行，实际 exit/HEAD/SHA/标记/离线/强制 extension 与五包静态等只凭原始节点证据核收。

本准备未执行测试、编译、lint、build、容器、节点取证；未改产品、主线或他人 worktree。最终审核将在固定 D SHA 的新 clean detached worktree 继续。

## D r1 / r2 源码初审

- D 直接基线 `fbb9cf6a488f903451a2905b81e403f21ada1e66`，含 root 已合的 S3 最小 port。r1 `180e08e6e8df7856f40b1c3182974cd397fe8d78`；r2 `edfe3bbc0a876a03ed0bcc428e1bdb942e5cf2ec`。分别在 `/home/dev/gdds-reviews/p6-s4-d-r1-180e08e6e8`、`/home/dev/gdds-reviews/p6-s4-d-r2-edfe3bbc0a` 的 clean detached worktree 只读审查，均链接并忽略 legacy。r2 Rust tree `e2a901417b19259ece669637a41545e774261445` 未变；`git diff --check fbb9..r2` 为 0。
- r1 测试 `test_prepare_rejects_invalid_frozen_parent_manifest` 的两个参数在进入 `pytest.raises` 前由 `PrepareImportBuildInput.__post_init__` 自行拒绝，且文件末尾多余空行触发 diff check。r2 改成可构造的 parent content tamper，删去空行，**两点已关闭**。
- **F-D1，阻塞：T1 后有行的 keyed parent 仍依赖运行期 ruleset。** `import_publication.py:213–223` 中，只要非 INITIAL 的变更表进入 `parent_read_names`，就调用 `migrated_table_ruleset_snapshot()` 并要求其 digest 与 parent manifest 相同；`_materialize_parent_table` 随后将该 runtime snapshot 传入 `RepositoryRefMaterializationRequest`。`repository_ref.py:343` 还会从 runtime ruleset 求 compare key。反例：A 下 T1 冻结，prepare checkpoint 前按规定 drain/restart 激活 B，parent exact commit、完整 manifest、冻结 after IPC 均未变，非 INITIAL keyed 表有 1 行修改；当前 D 在任何 parent read 前拒绝。`ruleset-activation-and-migration.md:20–25`、P5 closure S5 handoff:106 的 owner 决议均要求 T1 后 Submit 只使用冻结产物，不依赖 runtime ruleset。最小修复：parent materialization 的 storage-only 路径由冻结 parent manifest/binding 得键及列，保留现有 exact commit、full catalog、count/content、cache miss 核验；由 Submit preparation 语义 owner 加一个非 INITIAL keyed T1 跨激活回归。不得以仅删 digest guard、仍用 runtime compare key 冒充修复。**r2 判 CHANGES_REQUIRED**。已通知实施者和 root；实施者报告正在修，但未作为固定候选审查。
- **F-D2，待修订核：非 INITIAL parent 核验与 PATCH 缺少生产接线测试。** r2 新测试覆盖 INITIAL 多表 DDL、坏 parent manifest；既有 `test_submit_prepare_removed_tables.py` 只验删除，没有一条真实 `parent_access → materialize_repository_ref → CanonicalCommittedTableAccess → native PATCH` 旅程，也没有错 commit/count/content 的该接线反例。这是 D 新接线的主业务边界；建议在既有 Submit preparation owner 中用一条 keyed patch 与少量绑定失败参数测试，按 Contract 语义命名。已通知实施者/root；待新固定候选核。
- **F-D3，低风险清理：**删旧 row planner 后，Submit `PrepareImportBuildInput.repository_base_digest` 只剩构造/校验与旧测试，没有生产读取（`application/submission/contracts.py:101,114`、`submit_jobs.py:1660`、`test_submit_import_builder.py:1032`）。新项目规则要求删被替代路径的无消费者字段/专属测试；不涉及 external target 同名活字段。实施者报告拟随修订移除，待固定候选核。
- r2 其余静审：逐表打开完整 frozen after（含 unchanged 表）并校验 artifact ref、repository、raw manifest、descriptor、count/content、schema/key；更改表在同 active operation M 内打开 before/after lease，summary→共用 policy→render 后按 native handle、lease、reader 顺序关闭；按 UTF8 表序汇集 DML，单次 schema renderer 只对 rebuild 子集加 DROP/CREATE，删除表先 DROP，DDL 全在 DML 前；发布器拿完整 target import input，构包前按 DDL+DML 原始 bytes 判 200 MiB；原 checkpoint、publisher、package readback 保留。`architecture_baseline.storage` 临时豁免已删除且真实 Submit 调用 policy facade。以上仅源码审读，不能代替节点 focused、Dolt、Compose、容量和性能证据。

## D r3 修复复审与执行稿静审

- 固定 r3 `1ff24b7802892982577e0e151ee7ac947767ee51`（父 r2），clean detached `/home/dev/gdds-reviews/p6-s4-d-r3-1ff24b7802`，legacy 链接且忽略，`git diff --check r2..r3` 为 0；Rust tree 仍 `e2a901417b19259ece669637a41545e774261445`。
- **F-D1 产品路径已修，测试尚欠可检出旧错误的注入。** `RepositoryRefMaterializationRequest` 新 `frozen_storage_only` 仅在 `ruleset=None` 下允许；`repository_ref.py:338–349` 仅该模式从 complete canonical binding 的 storage key 建 descriptor，普通比较仍从注入 ruleset 求 compare key；`_ruleset_mismatch` 保版本核验。Submit parent 调用只传 frozen binding/`ruleset=None`，原 full catalog、精确 commit、count/content、committed reader 和同 M 路径未跳过。`ruleset-activation-and-migration.md` 与 Storage Mutation owning 文档同步窄记。源码层 F-D1 已关闭。
- r3 的非 INITIAL 100 行 1 变 PATCH 测试确实调用真实 canonical IPC、`build_committed_table_access` 与 native Submit，且有错 commit/count/content 三个参数反例；F-D2 接线范围足够。但 `test_submit_patch_uses_frozen_parent_after_runtime_ruleset_changes` 仅 monkeypatch `table_rules.registry`，r2 旧生产代码在 `import_publication.py` 直接绑定导入函数，故旧错误仍可通过该测试。**审核建议校正：**最初曾建议像现役 INITIAL 测试那样用 `raising=False` 给已删除的 `publication_module.migrated_table_ruleset_snapshot` 造回 alias；root 指出这是旧机制专属 mock/probe，与 AGENTS/比例化政策冲突，该建议撤销。应让 parent/T1 after 从真实不同于 runtime default B 的合法 ruleset A 冻结，保持 storage view 相同，令旧 digest guard 按业务输入必然失败；必要时在现役 RepositoryRef 协议 owner 验 frozen-storage 使用 binding key。现役 INITIAL dead-alias probe 一并收敛。r3 测试语义暂判 CHANGES_REQUIRED。
- F-D3 已关闭：Submit-only `repository_base_digest` 从构造类型、调用方与其无消费者专属测试移除；external target 活字段未动。新增 `RepositoryRef` 合同字段属于进程内 narrow read mode，不是持久证据、IPC、辅助服务或新信任域。
- root 固定的 r3 执行稿：`/home/dev/gdds-test-tmp/p6-s4-d-r1-06-1ff24b7802/` 下 `node.sh` SHA `39fa25fb34ba129569148a62332a3faed9ba7d8d847286fd9b09ffe3343b5479`、`run.sh` SHA `b5496b6a7826bab949000ec1336fa06de7d1ead9a985f2586f9124687e390c12`、bundle SHA `754984b8e704e833763ce8c10e66c840e060ab3b6f727ae2a36dbd656d922944`。静审：06 实时主机/进程/Docker/8000、原子标记和本人释放、bundle fixed clean detached WT、legacy、selector/六锁/offline、forced native reinstall/build-input、五包 Ruff/Mypy、16 个 focused 文件双 marker（serial `-n 0`）、exit/HEAD/status/log SHA 完整；Rust3 的 C r7 同机同 tree 仅标 debug-only，容器延期 E，均适用。**SCRIPT_STRUCTURE_CLEAR，SOURCE_NOT_RELEASED**：r3 测试修复会变更提交和 bundle，此三原件不可直接执行作下一候选证据，必须重新固定并复审 SHA。没有运行任何节点步骤。

## D r4 源码阶段结论

- r4 `ce1037e320c514c5ca18de43b02748265092df2c`（父 r3），clean detached `/home/dev/gdds-reviews/p6-s4-d-r4-ce1037e320`，legacy 链接且忽略；仅改 owning Ruleset Activation 文档与 `test_submit_import_builder.py`，`git diff --check r3..r4` 为 0，Rust tree 不变。
- 非 INITIAL keyed PATCH 的冻结 parent 和 after 现由合法 ruleset A 生成：只将 fallback 的 `compare_excluded_columns` 加入非键 `value`，实际 storage key 仍 `(id,)`；运行期真实 default B 与 A 的 ruleset digest 不同。旧 r2 `runtime.ruleset_digest == parent.manifest.ruleset_digest` 分支会拒绝；r4 新路径仍以真实 IPC、committed access 和 native PATCH 得到 UPDATE、无 DROP，且错 commit/count/content 反例保留。F-D1/F-D2 的生产语义及可检出旧错的业务测试均已关闭。
- 删除 INITIAL 场景给已删除函数造 `raising=False` alias 的 mock/probe。其 T1 恢复业务断言由现役 `test_submit_job_prepare.py:372` 所有，包原样重用和确定性由 builder 现役测试所有；未删独有断言。F-D3 仍关闭。
- **源码阶段 GO，限 D r4 实际范围。** D Python/Contract 改动进入 backend/worker Docker source closure；本阶段无当前镜像门禁，最近 image revision/source-tree 在 D 稿记 none，镜像重建/Compose 与全旅程留最终 E 固定候选。r3 的 node/run/bundle 仅为旧 SHA 的结构静审，不能移作 r4 实际运行。待 root 固定 r4 执行稿并由唯一 Luna 节点运行；本人只核原件，不在开发主机测试、编译、lint、build 或取证。

## D r4 精确执行稿静审

- root 固定 `/home/dev/gdds-test-tmp/p6-s4-d-r1-06-ce1037e320/`：`node.sh` SHA256 `ba69ebd697898eb78ae37739155c1798a0fb6380a0538fd583d3238732aebefd`，`run.sh` SHA256 `0bd670dc9b2544033520d711834b94d1c9d4e07334c2220bb874ecaed728ea7f`，`source.bundle` SHA256 `996effea19e8f1ab6ff03776c9f94390d5371f8c8c39c91dcc457485c017aa30`，bundle list-heads 唯一 `ce1037e320c514c5ca18de43b02748265092df2c HEAD`。
- 与已审 r3 执行稿逐行 diff，仅固定 source SHA、bundle/path、session/脚本 SHA 换；实际执行链与 16 focused 文件双 marker 相同。**SCRIPT_CLEAR**：可由 root 派唯一 Luna 在实时空闲、合格 06 节点运行此一次 focused 调试。此结论只签脚本静态适用，不能签节点实际 exit、HEAD、日志、Rust3 carried、容器、真实数据、容量或性能；执行原件到达后另核。

## D r4 节点首轮原件与 F-D4

- root/Luna 在 `ct107-gw-dms-06` 实际运行上述 fixed 脚本。原始抓回节点日志 `/home/dev/gdds-test-tmp/p6-s4-d-r1-06-ce1037e320/controller/captured/focused.log` SHA256 `f46ac480f7aaac9ebc1645933833eb83b83821a819de9c13883c728cb4eddcc0`，outer.log SHA256 `298a6e3b9e6bfe771ee139ff23191d5bdd74f6385c89ee753d45b650add1ea16`；抓回 log SHA 与节点自报 SHA 相同。06 `gw-dms-06` 32C/64GiB，起 `2026-11-08T21:26:30Z`、止 `21:27:30Z`，起止 HEAD `ce1037e320c514c5ca18de43b02748265092df2c` 且 status clean，六锁 SHA 前后一致，marker file/dir 释放 exit 0。强制扩展重装与 build-input checker 0、五包 Ruff/Mypy 全 0；nonserial 16 文件 **326 passed、1 failed**，唯一 `test_production_reachability_matches_frozen_baseline`，serial 依首败未跑；入口/final/outer exit 均 1。C r7 Rust3 同机同 tree 的日志只作 debug reference，不是本轮 formal carried。**此轮不能签 D focused GO**，不将 326 pass 冒充全通过；失败原件保留。
- **F-D4，architecture reachability：**实测新增不可达恰为 `mutation_planning._artifacts/_changeset/_digest/_planner/_repository_replay_renderer` 五项，stale 为空。Submit 真正改走 native table 后五模块不再由 app/http_server/operation_worker 导入；普通 facade re-export 不算生产接线。源码 consumer 核对：`_planner.plan_storage_mutation` 是固定设计保留的通用 standalone planner；`_changeset` 和 `_artifacts` 由它构建/可选发表 ChangeSet；`_digest` 供通用 planner/ChangeSet 的键/行摘要；`_repository_replay_renderer.render_change_set_replay` 是 owning Contract 固定保留的通用 Rust-backed renderer。测试仍覆盖这些 API，但**没有当前 app/worker 运行 consumer**；external target 目前只直接消费 mutation `contracts` DTO，自有 ledger digest，设计 §193 的“直接消费 `_digest`”与现源码不符。Owner 固定 S4 设计 §192–200 明确保留通用 API，不能为通过架构门禁假接生产 import，也不能删这些已授权保留能力。`architecture_baseline.py` 顶部虽要求基线通常只缩，但允许同 diff 经明确独审理由登记；在此已批准 standalone library surface 下，最小修复可精确登记这五个**永久** unreachable，逐项写真实 consumer/保留原因与 owner，不称生产已接线；B temporary `.native/.storage` 两项仍删除，不增加 import/cycle 例外、不改 root 图。新固定 V 后完整受影响 focused 双 marker 复验，不能改预期掩盖产品失败。

## D r5 F-D4 修复源码核收

- 固定 `41d1944208fe99911df0a15641ab651505d1274c`（父 r4），clean detached `/home/dev/gdds-reviews/p6-s4-d-r5-41d1944208`，legacy 已链接且忽略，Rust tree 不变，`git diff --check r4..r5` 为 0。唯一 diff 是 `architecture_baseline.py` 同处精确登记上列五项，注释明确实际无生产入口、external target 只用 DTO、保留依据与有真实 caller/Contract 退休时重新处理；B 临时 `.native/.storage` 项仍不在基线。未改 import/cycle baseline、reachability root/算法、生产源或测试预期。按原文件“explicit, reviewed justification in same diff”的窄例外，**F-D4 源码修复 CLEAR**；这不改变 r4 原件 exit1，也不使 326 pass 自动变整轮通过。等待 r5 新执行稿与节点完整 nonserial+serial 原件。

- r5 精确复验稿 `/home/dev/gdds-test-tmp/p6-s4-d-r2-06-41d1944208/`：`node.sh` SHA256 `486ac6e31d5d411e926f1646f41dcac8028fb06df2069b7d1b33a6df8cc2c8da`，`run.sh` SHA256 `63551a8f8d594aa7c7dc7f1b8952f14f5bf9ba66f6ba9c96399adefa9ba3f694`，`source.bundle` SHA256 `aee850c921e309e5bc45636efdcea3e3ba04cb75ab482f97f41fa71ebd058a42`，bundle 唯一 HEAD `41d1944208fe99911df0a15641ab651505d1274c`。与 Ce 已执行稿逐行 diff 仅 source pin、路径、session、摘要；完整强制扩展/build-input、五静态、16 文件双 marker、前后身份与清理均未减，**SCRIPT_CLEAR**。唯一 Luna 可在实时合格 06 重跑；本人仍只核后续原始节点结果。

## D r5 节点复验原件与阶段 GO

- 原始抓回节点日志 `/home/dev/gdds-test-tmp/p6-s4-d-r2-06-41d1944208/controller/captured/focused.log` SHA256 `746e81deb09450194960a823971c198f3f736a514f331677537a958824adc0df`，outer.log SHA256 `5c12eb21a7777cfcff473fe7a8685b11a16af097056efdbc3b1590197452b847`；节点自报 SHA 与抓回一致。`gw-dms-06` 32C/64GiB，起 `2026-11-08T21:32:59Z`、止 `21:34:21Z`，起止 HEAD 均 `41d1944208fe99911df0a15641ab651505d1274c` 且 clean；六锁 SHA 前后一致、marker file/dir 释放均 exit 0，外层 capture/entry/final/outer exit 全 0。forced native reinstall、build-input checker、五个 Python 包 Ruff/Mypy 均 exit 0；16 focused 文件 nonserial **327 passed**、serial **18 passed（327 deselected）**，两遍自身 exit 0。旧 r4 的 architecture failure 被 exact five baseline 同 diff 理由闭合，未修改生产验证预期或跳过该 test；本轮实际 architecture 通过。
- **F-D1–4 全部关闭，D V 阶段 GO**，只限已审 D 产品源码及上述 focused 结果。D 20 路径增量（相对直基线 `fbb9cf6a488f903451a2905b81e403f21ada1e66`）均在最终固定 V，`git diff --check` 0，Rust tree `e2a901417b19259ece669637a41545e774261445` 未变。S3 最小 port 已在基线，不用隔离旧 4b0/774 或 C480 节点证据倒签当前 main。Rust C r7 同 06/同 tree 的三步只作 debug reference，不是 D formal carried；D 本轮未实际跑 Rust 包。最新 D 镜像 revision/source-tree 仍 `none`，backend/worker source closure 改动的当前镜像重建、Compose、六包完整闭包、真实 t1–t4/2×t4、容量/性能/压力以及 S3 exit 判断均交 E 实际完成，不能从本报告推导。

## 保留/删除消费者核对

| 被替代部分 | D V 处置与现役语义 owner |
| --- | --- |
| Submit Python `ImportReplayTableSnapshot`、逐行 keyed/image graph、`mutation_planning/import_replay.py` wrappers 与其专属六测试 | 删除。DROP/CREATE/INSERT 和跨表 DDL 顺序在 Submit builder/schema tests；旧 258 行分批语义由 `test_dolt_renderer.py` 的 257 跨 256 窗口、独立 batch vectors 与复合键测试拥有；伪 gid、SET、冻结 IPC 在 Submit builder；scalar bytes 由 Shared Kernel/六 golden/native renderer 拥有。没有保留旧 Python 并跑 oracle。 |
| 通用 planner/ChangeSet/artifact/digest/replay renderer | 保留已批准 standalone API 与 `test_mutation_planning.py`、`test_dolt_renderer.py`、`test_sql_replay_controls.py`；五模块当前无 app/worker 运行入口，精确 architecture baseline 登记且说明退休条件。external target 当前只直接用 mutation contracts DTO、自有 ledger digest；不冒称直接消费通用执行模块。 |
| Storage Projection publisher/package、`read_back_package`/`verify_checkpoint_semantic_binding`、RepositoryRef committed access | 保留实际 Submit、包验证与恢复消费者；准备包 full target import input、只对 rebuild 子集渲染 DDL，checkpoint 后原包/ref/raw SHA 原样复用。 |
| B temporary `architecture_baseline` 的 `mutation_planning.native/.storage` | D 真实 `prepare_storage_table`/`choose_table_mutation` 生产接线后删除，未通过假 import/export 或扩大图规则保例外。 |

本审核者只读 detached 源码与节点原始日志；未在开发主机或测试节点运行测试、编译、lint、build、容器或取证，未改产品、golden、锁、主线或他人 worktree。

## 最终文档 H2 核收

- 产品 V `41d1944208fe99911df0a15641ab651505d1274c` 后有三笔纯文档提交：`ef7bceba946eaed6b79e6ea1168d53da68f3158e` 为 S3 独审文档 §96–97，`d332df5d30da1f3a4747fb564b4544fcc47cfeda` 新增 D handoff，`9d91653ac96908cc9cafe159fcb7b76a5a3525bd` 只澄清 D handoff 一行诊断口径。最终 H2 在 clean detached `/home/dev/gdds-reviews/p6-s4-d-h2-9d91653ac9` 审核，legacy 链接且忽略；`git diff --check V..H2` 为 0。`V..H2` 的实际路径恰为 `p6-s3-e-review.md` 与 `p6-s4-d-handoff.md`，没有产品、测试、锁、Docker、Compose 或 Rust 改动；S3 文档内容由其独审者负责，本 D 报告不签 S3 结果。
- D handoff 的 V、原失败 r4、r5 专用节点 327 nonserial＋18 serial、force extension/build-input/五包静态、focused/outer 日志 SHA 与本报告原件相符；该两份日志在控制端重算 SHA 分别为 `746e81deb09450194960a823971c198f3f736a514f331677537a958824adc0df`、`5c12eb21a7777cfcff473fe7a8685b11a16af097056efdbc3b1590197452b847`。handoff 正确保留 Rust 同树 C 结果仅 debug reference、D 无当前镜像/Compose/真实 M24/性能结论，E 仍须独立门禁。H2 的 `native_calls=2` 明确仅计 prepare/render 粗入口，不冒充全部 FFI/chunk/lifecycle 次数；`parent_read` 仅计 Repository parent materialize，完整 frozen after 逐表 opening 另行发生。源码日志字段与这两句一致。
- **最终 D 阶段 GO，证据绑定产品 V `41d1944208`；H2 仅作为文档 handoff 核收。** 这不把 V 的 focused 结果自动提升为 H2 当前 HEAD 全包或容器门禁，亦不代表 S4 exit、S3 exit、资源档、真实数据或性能达标。最新已验证 D image revision/source-tree 仍 `none`；E 最终 HEAD 的镜像重建、Compose、六包、真实旅程/容量与性能依既定独审及节点原件判定。
