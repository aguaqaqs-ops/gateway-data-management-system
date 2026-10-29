# Phase 6 S1b handoff

状态：**已通过（repository owner，2026-10-29，DC63）**，附注 tag `p6-s1b-exit`；审核链见[终审](p6-s1b-final-review.md)。当前候选与证据见下方“审核后修订”节；后续“初次候选记录”仅是 H=705b17c1 的历史 handoff。

## 审核后修订与复审证据

### 候选与提交

- 本轮最终代码候选 V/H：`020deda2fd59839c9ae6e31660f6fd23d14304d2`。F1–F4 前一候选为 `afbfaea8e2154326e25c29091f34ffb3c12cd8ab`；本轮 F5 修订在该已审核候选后追加，当前 runner 与 t1–t4 旅程均绑定到 `020deda2`。最终 handoff 提交只更新本文件，不改变代码候选或其证据绑定。
- 实施分支仍为 `p6-s1b-impl`；在已审核候选上追加提交，没有推送、打 tag、改写已审核提交，也没有修改 p6-design、执行计划或 owner 决议记录。
- 修订按主题提交：F1–F4 已审核提交为 `7e591debd4`、`e1146910dd`、`688888e721`、`383c829aaf`、`be64f6fcd4`、`b5acb3d797`、`91401f0146`、`e876986db8`、`bae1eb1944`、`afbfaea8e2`、`fb2b507588`；F5 追加提交为 `94001027c0` 修复全表导出绑定、`5c8d7beb2f` 补 History bundle 与缓存覆盖、`fccea4561e` 核对 Parquet 标量内容、`020deda2fd` 收窄共享绑定断言类型。

### F1–F4 修订与关闭证据（沿用前候选已关闭行为）

- **F1 上传取消生命周期**：取消时 shield 等待受理子 task 结束后再传播原始 asyncio cancellation；staging 清理位于该等待之后，route 的 `acquire_new_work` 名额也随请求生命周期保留到线程完成或异常结束。没有新增 durable 状态。权威测试 owner 为 backend upload streaming：使用 `threading.Event` 暂停真实同步受理工作，对外层 asyncio task 直接 `cancel()`；验证线程运行期间暂存文件可读、线程结束后才清理并释放准入名额，且成功/失败事务结果保持原语义。日志 `05-focused-F1-F4-afbfaea8.log`，其中该用例属于 serial。
- **F2 只增列的共有行关联**：keyed、keyless、ordered 都按共有列投影完整行 multiset 比较，忽略新增列及物理顺序，但不拆散排除列值与共有行的关系。关闭用例覆盖 t(id PK, aux 排除列) 的两行交换 aux 值并新增 note，结果为 `content_changed=True`、SUMMARY_ONLY；仅新增列或物理行重排不报告内容变化。keyless additive 专项也已收敛覆盖。权威 comparison/surface/risk 测试在同一 focused 日志中通过。
- **F3 ENUM/SET 标签大小写**：先解析类型关键字与原始标签，只规范化类型关键字，标签按精确字符串比较。模块级共享参数表覆盖 ENUM 与 SET：标签改大小写或改名（新增列和不新增列两种）均为 INCOMPATIBLE 并产生 schema 风险；只增标签/成员（含中间插入）仍为 COLUMNS_ADDED。权威 row-encoding/comparison/risk/surface 测试通过。
- **F4 导出缓存命中不读取 Dolt 行**：repository materialization 先用 canonical identity 的 raw_content_digest、目录 schema、精确源类型/ENUM/SET 标签、ordered metadata、scalar encoding 与 writer/artifact contract 生成 row-layout cache key 并 lookup；通过现有完整性规则校验的命中直接复用缓存 Parquet，不调用表 reader；未命中或缓存无效时回退读表并回填。ordered metadata 可由 ruleset 得出时不因 metadata 单独读表；行比较和单侧摘要继续按 S1a demand 规则读取。History 原本按比较需求选择变化侧/表；完整导出需求由 F5 单独传递，避免把未变化表从 bundle 排除。权威 bundle/export-cache 测试用调用计数证明 hit 不读、miss 回退并回填，并保留 schema、ENUM 标签、writer 版本变化不误命中用例。

### F5 复审修复与最终候选证据

- **根因与修复**：History 的比较读取选择只包含需比较的变化表；F4 又让 repository ref cache lookup 仅遍历该选择集，导致未变化表既不读行，也没有 SNAPSHOT_TABLE 文件或节点/侧绑定。现在 `RepositoryRefMaterializationRequest.export_tables` 单独承载完整导出需求；History 将比较选择与每个节点全部 canonical 表名分别传递。cache lookup/reader 使用比较表与导出表的并集，命中仍跳过表 reader，miss/失效才读取、校验并回填；最终 bundle closure 逐节点保留绑定，同内容文件继续按现有机制共享。没有新增 durable 状态或计时插桩。
- **行为测试**：扩展 `test_two_node_compare_job_succeeds` 与 `test_unchanged_ordered_history_bundles_both_sides_and_preserves_facts`，直接读取最终 History bundle 和 Parquet，核对未变化普通表与 ordered 表的 before/current 绑定及内容；`test_history_full_table_export_uses_cold_and_warm_cache_entries` 以 reader 调用数证明冷缓存读取/回填、暖缓存命中不读表；`test_history_bundle_preserves_changed_added_and_deleted_table_bindings` 覆盖变化、新增、删除表；`test_three_node_compare_job_uses_multi_pair_bundle` 覆盖三节点共享文件仍保留每侧绑定。focused 命令为 `tests/test_history_compare_jobs.py tests/test_snapshot_export_cache.py -m unit`，CT05 最终候选 `34 passed, 1 warning`，exit 0；日志 `/home/dev/gdds-p6-logs/s1b/05-focused-f5-final-020deda2.log`。测试按 bundle 行为验证引用、checksum、Parquet 可读性和规范标量值，不只检查 operation 状态或 digest。
- **静态检查**：CT05 `gw-dms-test-05` 上五包 Ruff 与 mypy 均通过，日志 `/home/dev/gdds-p6-logs/s1b/05-static-python-f5-final-020deda2.log`；Rust 未改动。F5 没有新的 comparison/risk/surface golden diff，也没有 Contract 文本 diff：现有 Comparison Bundle Contract 已覆盖完整 History 导出和精确缓存命中不读表的语义。
- **逐包闭包判定与权威 runner**：CT04 来源为 clean worktree 上实际通过的 runner V=`91401f014699cf99feba05675762cada2847e459`。以该 V 的 manifest 与当前候选 compare 后，rust、shared_kernel、repository_contracts、repository_client 沿用 V；backend 与 repository_service 在当前候选运行。runner 日志 `/home/dev/gdds-p6-logs/s1b/04-runner-f5-020deda2.log`，hostname `gw-dms-test-04`，2026-10-28 21:29:57–21:50:16Z，起止 HEAD 均为 `020deda2fd59839c9ae6e31660f6fd23d14304d2`，exit 0。manifest 比较与 runner 起始 manifest 日志：`04-compare-f5-020deda2-to-afbfaea8.log`、`04-compare-f5-runner-manifests.log`、`04-manifest-f5-020deda2-retry1.log`。

| 包 | 当前总摘要 | 判定与来源 |
| --- | --- | --- |
| rust | `290aabfc2a9f011aabcd539912331ccd2694c4a59546d91e1b7e85212564f590` | 沿用 V=`91401f014699cf99feba05675762cada2847e459` 的实际成功 runner |
| shared_kernel | `4e3980c00e6f8abbb6f652447f6f40fdec40078a1c4230f1267b3f66a8776bee` | 沿用同一 V |
| repository_contracts | `75784176323e50dd3d5484f48295f71a5c5841e781b7a3fa465df177338d7209` | 沿用同一 V |
| repository_client | `ecfecc332d51d649e0c1499bbbd2f6027be7d728762842df3626d422d675eed7` | 沿用同一 V |
| backend | `8c83a3bc74cd00196d005c061156851822daf6fa36dfdab95a5bdce9568d9e6b` | 当前候选运行；parallel 3062 passed，serial 41 passed |
| repository_service | `9a44edee7e195e74ff01c727a4495d5d128ad2f7b24ee5a2375640ed8b943b2f` | 当前候选运行；parallel 1741 passed、1 skipped，serial 207 passed |

- CT04 当前 runner 覆盖 backend Compose；Dockerfile/Compose/依赖未变。Repository Service 按 build-input/source-tree label 判定 carried：CT04 本机 image ID `sha256:b66c7fef0b8dd6c6b6d66e0463862e109f1d44cd8614e96fe93564bd8a2a4dd9` 的 build-input revision=`4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree=`sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`、lock SHA=`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`，标签输入与已验证镜像一致。CT108 真实旅程使用的 Repository Service image ID=`sha256:3007cb250a25aa95b597141200c0f3d8292084cc8e5e84d8c3c1aa062b4f97ba`，具有相同 build-input/source-tree/lock 标签；节点间 image ID 不作相等判定。缓存来源为本机预置和批准 LAN artifact cache endpoint `192.168.233.180:18080`，未记录凭据。

#### 最终候选 t1–t4 旅程

所有旅程均在 clean worktree、HEAD=`020deda2fd59839c9ae6e31660f6fd23d14304d2` 完成，exit 0，无 degraded/failed 表。t1–t3 在 CT05 `gw-dms-test-05`，t4 在 CT108 `gw-dms-test`。除表内日志外，节点上的所有日志位于 `/home/dev/gdds-p6-logs/s1b/`。下表 API 时间为秒，Preview 数量为 changed/table；History 行数是业务 History record 数。

| 档位 | 节点；UTC 起止；日志 | composite unchanged | Preview v1 / repeat / v2 | Submit v1 / v2 | History API / records |
| --- | --- | ---: | --- | --- | --- |
| t1 | CT05；2026-10-28 21:52:40–21:56:36Z；`05-t1-f5-020deda2.log` | 4 行 / 11.244s | `125/125`, `0/125`, `4/125`；`30.114/20.076/20.077` | `36.167/26.125` | `20.070s / 12` |
| t2 | CT05；2026-10-28 22:01:08–22:29:52Z；`05-t2-f5-020deda2.log` | 45 行 / 146.167s | `209/209`, `0/209`, `57/220`；`249.598/182.661/329.206` | `180.799/343.506` | `175.003s / 1147` |
| t3 | CT05；2026-10-28 22:30:26–23:27:34Z；`05-t3-f5-020deda2.log` | 201 行 / 447.846s | `192/192`, `0/192`, `23/193`；`540.434/441.568/702.480` | `339.493/550.415` | `296.867s / 711` |
| t4 | CT108；2026-10-28 23:28:35–2026-10-29 00:40:20Z；`ct108-t4-f5-020deda2.log` | 435 行 / 665.620s | `312/312`, `0/312`, `26/312`；`792.218/685.654/792.202` | `553.778/271.847` | `361.051s / 168` |

- t3 v2 的 193 张表中，33 张 COLUMNS_ADDED 仍为：32 张原始只增列 + 2 张 ENUM 只增标签 − `device_model_table`（属 `DEFAULT_SKIPPED_TABLE_NAMES`）；没有 SCHEMA_CHANGE 风险、degraded 或 failed 表。四档 Submit 均成功。F5 只改 History 的完整导出需求与绑定，不改 Preview 的显式键或 BROWSE_ONLY 语义；既有 surface/step audit 的 11 张显式键与 BROWSE_ONLY 结果保留为前一候选证据：`05-final-surface-step-audit-afbfaea8.log`、`ct108-final-surface-step-audit-afbfaea8.log`。

#### 最终 History bundle 全表核对

按每个 History pair 的最终 bundle manifest，逐侧把 `SNAPSHOT_TABLE.table_bindings` 与 Surface 的 before/current refs 对照，读取全部唯一 Parquet 文件并核对引用 raw checksum 与 Surface 行数。日志不输出真实行值。t1–t3 每份日志有四份 closure 文档（两种 pair bundle 各有重复文档）；每个 pair 的表名集合无 missing/extra，Parquet 全部可读。

| 档位 | 每个 pair 的 before/current 绑定 | ordered 表绑定 | 唯一 Parquet / 总绑定（共享复用数） | 结果 |
| --- | --- | --- | --- | --- |
| t1 | `125/125` 与 `121/125` | `9/9` 与 `8/9` | `106/250 (144)` 与 `102/246 (144)` | 每侧与 Surface 精确一致；所有 Parquet 可读、行数匹配 |
| t2 | `170/209` 与 `209/209` | `51/72` 与 `72/72` | `130/379 (249)` 与 `144/418 (274)` | 每侧与 Surface 精确一致；所有 Parquet 可读、行数匹配 |
| t3 | `192/193` 与 `139/193` | `54/54` 与 `48/54` | `169/385 (216)` 与 `121/332 (211)` | 新增/删除侧与 Surface 精确一致；所有 Parquet 可读、行数匹配 |
| t4 | `312/312`（两节点、一个 pair） | `144/144` | `166/624 (458)` | 286 张 unchanged 和 26 张 updated 表均具 before/current 绑定；checksum、Surface ref、Parquet 读取及行数全通过 |

- t1–t3 只读日志：`05-f5-t1-history-bundle-audit-final.log`、`05-f5-t2-history-bundle-audit.log`、`05-f5-t3-history-bundle-audit.log`。t4 日志 `/home/dev/gdds-p6-logs/s1b/ct108-t4-history-bundle-audit-f5-020deda2.log`；control DB 使用 `mode=ro&immutable=1`，无 `-shm` 接触。该文件保留早期只读诊断脚本的失败记录；最终从成功 History operation 的 Comparison Bundle manifest 执行的 `robust_script_retry` 段 exit 0，得出上表绑定覆盖。

#### t4 性能对照与 N1 处置

| t4 操作 | API 秒 | `materialize_inputs` 秒 | assemble 秒 | publish 秒 |
| --- | ---: | ---: | ---: | ---: |
| v1 Preview | 792.218 | 721.597 | 67.037 | 0.763 |
| repeat Preview | 685.654 | 608.509 | 74.420 | 0.308 |
| v2 Preview | 792.202 | 675.706 | 112.779 | 0.382 |
| History | 361.051 | 216.440 | 142.544 | 0.035 |

- t4 control DB step 明细只读日志：`/home/dev/gdds-p6-logs/s1b/ct108-t4-step-audit-f5-020deda2.log`。此前 `162.472s API / 78.822s materialize_inputs` 是 F5 输出遗漏候选的结果，不是满足完整 History Contract 的性能结论。当前 History 对比 H=705 的 `744.135s / 595.122s` 分别少 `383.084s / 378.682s`；对比 S1a API `312.889s` 当前多 `48.162s`。repeat Preview 为 `685.654s / 608.509s`，对比 H=705 的 `693.751s / 616.207s`。
- **N1-1 待 owner 处置**：当前 step 仍只有 `materialize_inputs` 与 assemble/publish 聚合，没有独立 checkpoint-read 和 bundle 子段时间戳；不增加产品计时插桩，也不伪造拆分值。继续明确标记待 owner 处置。
- **N1-2 已关闭**：保留原审核 b §3 的最终真实卷只读计数证据和 `/home/dev/gdds-p6-logs/s1b/05-N1-2-row-cache-counts-afbfaea8.log`、`/home/dev/gdds-p6-logs/s1b/ct108-N1-2-row-cache-counts-afbfaea8.log`；不重复触碰 control DB，也不清理旧证据或卷。

#### F5 保留与清理清单

- 不清理 worktree、bundle、volume、真实数据 scratch、Docker image、manifest 或日志。保留当前实施 worktree `/home/dev/gdds-p6-logs/s1b/impl-wt`、CT04 `/home/dev/gdds-p6-logs/s1b/04-wt`、CT05 `/home/dev/gdds-p6-logs/s1b/05-f5-020deda2-wt`、CT108 `/home/dev/gdds-p6-logs/s1b/ct108-f5-020deda2-wt`，以及早期 `ct108-wt`。F5 候选 bundle `/home/dev/gdds-p6-logs/s1b/impl-f5-020deda2.bundle`，SHA-256 `54c16bbbbeff1ad571565dadb2f1b1e6bd12e75f878698da3aa50de658bc1f8c`；此前 afb bundle 和所有报告中列出的旧候选 bundle 均保留。
- 保留 t1–t4 F5 project 的 backend-control、backend-artifacts、repository-data、repository-service-data volumes：`s1bf5t1-020deda2`、`s1bf5t2-020deda2`、`s1bf5t3-020deda2`、`s1bf5t4-020deda2`。CT108 t4 项目已停止并移除容器/网络，stop 日志 `/home/dev/gdds-p6-logs/s1b/ct108-t4-stop-f5-020deda2.log`，3 个 volumes 仍存在；CT05 项目亦已停栈，卷保留。CT04 runner 与历史 V=914、H=705、afb 候选卷/image 继续保留。
- 保留 `/home/dev/gdds-p6-logs/s1b/` 下所有 runner、manifest、focused/static、journey、bundle/step audit、stop、cache-count 日志和真实数据 scratch；保留 `/home/dev/gdds-p6-logs/s1b/dev-cache`、`dev-cache-http-f5.log`、`dev-cache-http-f5.pid` 与文件。批准 LAN HTTP cache 在 t4 及全部节点取缓存完成后于 2026-10-29 00:46:25 UTC 停止，未清理缓存目录或日志。所有后续清理留给 owner 在独立复审与阶段 exit 合入后执行。

### Golden 与 Contract diff

- 仅三个受影响的 S1b comparison/risk/surface golden 有 diff：`comparison/s1b/semantic-results.json` 对应 F2 交换排除值后共有行投影变化及 F3 标签大小写/改名由兼容改为不兼容；`risk/s1b/structural-risk.json` 对应不兼容 ENUM/SET 标签现在产生 schema 风险；`surface/s1b/table-presentation.json` 对应 additive 内容变化的 summary-only 与不兼容 schema 分类展示。没有其他 golden 变化。
- Contract 只修订实现原先未遵守的语义：`comparison.md` 明确 ENUM/SET 标签精确比较；`comparison-bundle.md` 和 `snapshot.md` 明确 row-layout cache hit 不读取 Dolt 表行。Contract 文本其余目标语义已覆盖，无额外扩展。

### F1–F4 前候选 `afbfaea8` 的 focused、runner 与镜像记录（历史）

- CT05 hostname `gw-dms-test-05` 上，F1–F4 前候选 focused 为 132 passed、1 warning，exit 0；日志 `/home/dev/gdds-p6-logs/s1b/05-focused-F1-F4-afbfaea8.log`。五个 Python 包 Ruff 与 mypy 全过；日志 `/home/dev/gdds-p6-logs/s1b/05-static-python-afbfaea8.log`。当前 F5 候选的 focused/static 证据见上文。
- 在 CT04 同一 worktree 对来源 runner V= `91401f014699cf99feba05675762cada2847e459` 做逐包 manifest compare。来源是 clean worktree 上实际成功的权威 runner `/home/dev/gdds-p6-logs/s1b/04-runner-final-91401f0146.log`。rust、shared_kernel、repository_contracts、repository_client 可沿用；backend 与 repository_service 因 package/backend 与完整 Docker context 变化而在新候选运行。比较日志 `/home/dev/gdds-p6-logs/s1b/04-compare-afbfaea8-to-914-final.log`。

| 包 | afb 前候选总摘要 | 判定与来源 |
| --- | --- | --- |
| rust | `290aabfc2a9f011aabcd539912331ccd2694c4a59546d91e1b7e85212564f590` | 沿用来源 V=914 runner |
| shared_kernel | `4e3980c00e6f8abbb6f652447f6f40fdec40078a1c4230f1267b3f66a8776bee` | 沿用来源 V=914 runner |
| repository_contracts | `75784176323e50dd3d5484f48295f71a5c5841e781b7a3fa465df177338d7209` | 沿用来源 V=914 runner |
| repository_client | `ecfecc332d51d649e0c1499bbbd2f6027be7d728762842df3626d422d675eed7` | 沿用来源 V=914 runner |
| backend | `cadf6f682d81de8694cbdee725ba219d448575f41328435a58877363a661bd91` | 在 V/H=afb runner；parallel 3061 passed，serial 41 passed |
| repository_service | `c831d1aa7de6a68595ca48cc74c5b5af76d46a38428cf8edb9bd2233eca9e22a` | 在 V/H=afb runner；parallel 1741 passed、1 skipped，serial 207 passed |

- afb 前候选的权威 runner `/home/dev/gdds-p6-logs/s1b/04-runner-final-afbfaea8.log`，hostname `gw-dms-test-04`，2026-10-28 18:16:11–18:36:27Z，起止 HEAD 均为 afb，exit 0。该记录和镜像信息仅保留作 F1–F4 历史证据；当前候选 runner 与镜像判定见 F5 节。

### F1–F4 前候选 `afbfaea8` 的 t1–t4 旅程（历史；History 全表输出由 F5 重新验收）

四档均在 clean worktree 的前一候选 afb 上完成，旅程 exit 0、无 degraded/failed 表；t1–t3 在 CT05，t4 在 `ct108-gw-dms`。这些 Preview/Submit 记录作为历史保留；F5 最终候选的旅程和完整 History bundle 覆盖见上文。afb 的 History bundle 漏掉未变化表，因此本节 History 输出与耗时不作为完整 History Contract 的证据。

| 档位 | 节点；UTC 起止；旅程日志 | offline composite；v1 Preview / repeat / v2；History |
| --- | --- | --- |
| t1 | CT05 `gw-dms-test-05`；18:22:21–18:26:02Z；`05-t1-final-afbfaea8.log` | 4 行 unchanged（11.304s）；125/125、0/125、4/125；12 records。 |
| t2 | CT05 `gw-dms-test-05`；18:26:29–18:52:41Z；`05-t2-final-afbfaea8.log` | 45 行 unchanged（146.537s）；209/209、0/209、57/220；1147 records。 |
| t3 | CT05 `gw-dms-test-05`；18:53:27–19:49:18Z；`05-t3-final-afbfaea8.log` | 201 行 unchanged（443.874s）；192/192、0/192、23/193；711 records。 |
| t4 | CT108 `gw-dms-test`；18:37:01–19:45:30Z；`ct108-t4-final-afbfaea8.log` | 435 行 unchanged（655.204s）；312/312、0/312、26/312；168 records。 |

四份日志中的 API 阶段耗时（秒）：t1 Preview v1/repeat/v2 `30.114/20.077/20.078`，Submit v1/v2 `34.160/28.131`，History `6.025`；t2 `210.749/174.618/281.004`，Submit `176.784/337.468`，History `128.383`；t3 `511.800/437.553/690.430`，Submit `335.481/549.448`，History `274.801`；t4 `796.214/687.653/800.258`，Submit `553.766/271.838`，History `162.472`。其中 t4 `162.472s / 78.822s` 为缺少完整表绑定的无效 History 性能值，F5 修正后的测量见上文。对应 stop 日志：`05-t1-stack-stop-afbfaea8.log`、`05-t2-stack-stop-afbfaea8.log`、`05-t3-stack-stop-final-afbfaea8.log`、`ct108-t4-stack-stop-final-afbfaea8.log`；服务已停止，volume 保留。

- 最终 v2 Preview 的只读 surface 核对：11 张显式键表的 key 列均无 mismatch；非空配置表按前后行数均符合原 Contract。BROWSE_ONLY 状态分别为 t1 `10 unchanged/7 absent`、t2 `11/6`、t3 `12/5`、t4 `15/2`，四档均无 compare key、无 annotation。t2 有 11 张整表新增（337 行）及 11 张整表删除（5563 行）；t3 有 1 张整表新增（comm_user_data，1 行）。step 间隔每档均为 6 个 operation、18 个成功 step、12 个间隔；最大 gap t1 `0.031s`、t2 `0.182s`、t3 `0.397s`、t4 `0.427s`，均无超过 1s 的 gap。证据日志：`05-final-surface-step-audit-afbfaea8.log`、`ct108-final-surface-step-audit-afbfaea8.log`。
- t3 v2 共 193 张表，其中 33 张 COLUMNS_ADDED：**33 张 COLUMNS_ADDED = 原始 32 张只增列 + 2 张 ENUM 只增标签 − device_model_table（属 DEFAULT_SKIPPED_TABLE_NAMES）**。无 SCHEMA_CHANGE 风险、degraded 或 failed 表；v1/v2 Submit 均有 repository commit。核对来自最终候选的 surface/step 日志和旅程输出。

### N1 前一候选证据与处置（当前 F5 性能值见上文）

- **N1-1 checkpoint-read 与 bundle 子段对照**：本段数值是 F5 前候选的历史记录；该候选漏掉 History 全表输出，不能作为当前完整 History 的性能结论。其 `162.472s API / 78.822s materialize_inputs` 已由上文 F5 的 `361.051s / 216.440s` 替代。当前 step 仍只有 `materialize_inputs` 与 assemble/publish 聚合，没有 checkpoint-read 或 bundle 子段的独立 timestamp；不加产品插桩、不伪造拆分值，继续待 owner 处置。
- **N1-2 重复导出 cache 复用**：按审核 b §3 方法，在最终真实数据 artifact volumes 扫描 table artifact manifests 的 row_file_refs；只输出 counts，不输出 artifact/row-file IDs 或 row data。control SQLite 使用 `mode=ro&immutable=1`，不触碰 `-shm`。按 miss 会 mint 新 sta-rows ID、相同 row-file ID 被多个 manifest 引用即表示跨导出复用计数：

| 卷 | table manifests | distinct row files | 被多个 manifest 引用的 row files | cache rows | 同时有 protection intent 与 manifest 引用 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t1 | 395 | 135 | 106 | 111 | 111 |
| t2 | 819 | 297 | 146 | 164 | 164 |
| t3 | 785 | 282 | 169 | 191 | 191 |
| t4 | 1149 | 415 | 166 | 185 | 185 |

  每档全部 cache rows 都有 protection intent 且被 table manifest 引用；四卷合计 cache rows `651/651`。只读计数日志：`05-N1-2-row-cache-counts-afbfaea8.log`、`ct108-N1-2-row-cache-counts-afbfaea8.log`。N1-2 计数证据已补；N1-1 的子段解释由 owner 最终处置。

### F1–F4 前候选保留与清理清单（历史记录）

- 尚未清理任何 worktree、bundle、volume、真实数据 scratch、Docker image、manifest 或日志。保留实施 worktree `/home/dev/gdds-p6-logs/s1b/impl-wt`、CT04 `/home/dev/gdds-p6-logs/s1b/04-wt`、CT05 `/home/dev/gdds-p6-logs/s1b/05-bae1eb1944-wt`、CT108 `/home/dev/gdds-p6-logs/s1b/ct108-wt`；候选 bundle `/home/dev/gdds-p6-logs/s1b/impl-final-afbfaea8.bundle`（SHA-256 `1d2681e3cfdfcb03341dae5d5e0291ed4196a7ca7c40215c1dd4f0b335a60ed7`）。
- 保留 t1–t4 final project 的 backend-control、backend-artifacts、repository-data、repository-service-data volumes，项目分别为 `s1bfinalt1afbfaea8`、`s1bfinalt2afbfaea8`、`s1bfinalt3afbfaea8`、`s1bfinalt4afbfaea8`；亦保留首次审核 H=705 与来源 V=914 的历史 volumes。最终旅程 stack 已停止。
- 保留 `/home/dev/gdds-p6-logs/s1b/` 下 runner、manifest、journey、stack-stop、cache-count、surface/step audit 日志及真实数据 scratch；保留批准 LAN cache 目录 `/home/dev/gdds-p6-logs/s1b/dev-cache` 与其日志。LAN HTTP cache service 已在旅程和构建完成后停止，目录和日志未删。所有清理留给 owner 在独立审核与阶段 exit 合入后执行。

## 初次候选记录（历史，已由审核后修订节覆盖）

- 基线：`ae3301d6d8`（`p6-s1a-exit` 为 `1d6a8d03fe`）。实施分支：`p6-s1b-impl`，未推送、未打 tag，未在主 checkout 工作或提交。
- 权威门禁候选 V：`80ce756619290d0ec95515ab73470241ce56a311`。
- 最终实现与真实数据候选 H：`705b17c1a137ede6b4339376527b30a4c58288f7`。V..H 只改 `vnext/backend/benchmarks/real_dump_journey.py` 与 `vnext/backend/tests/test_real_dump_journey.py`，按 P5 执行计划 §8.9 处理；其中 33 张 t3 只增列表不再贡献 schema-only History record，基线由 744 修正为 711。H 的这两处修订已在 H 上重跑 `test_real_dump_journey.py`、相关 synthetic-load 测试、五包 Ruff/mypy 与 t1–t4 旅程。

### 提交清单

下列提交均位于 `ae3301d6d8..705b17c1a137ede6b4339376527b30a4c58288f7`：

| 提交 | 内容 |
| --- | --- |
| `9283a16cbc81` | 实施 Phase 6 S1b 业务语义 Contract |
| `4158ea39d481` | FLOAT 单次舍入与 build snapshot 清理 |
| `24f265e06e28` | 冻结 S1b parser 与 table-rule goldens |
| `57363b1d2692` | 调整 scheduler failure 行为测试 |
| `6f879c63a606` | 修复 additive schema summary 比较 |
| `33653ea7bdb5` | 对齐 S1b fixtures 与 legacy rule 检查 |
| `7d9622be9a56` | 修正 binary32 golden 向量 |
| `bb63babe7fd0` | 修复 S1b diagnostics 与静态检查 |
| `b4cf7391bead` | 修复 backend S1b 类型检查 |
| `e148f478d086` | 删除冗余 cache adapter cast |
| `066dd8281a36` | 保留 JSON census 的 SQL statement 边界 |
| `8351b1e9d21d` | 给 synthetic SET mutation 定型 |
| `f94762933afa` | 标注 synthetic SET mutations |
| `64fffc3307ff` | 计入 SQL INSERT 中每个 JSON tuple |
| `d83a24aa8079` | 修复 worker、bundle 与 cache 边界检查 |
| `78d99e9828ff` | 修复 synthetic input table width 追踪 |
| `b455649d4f8e` | 删除过期 preview 测试 import |
| `0eec65a3bb62` | 更新 Rust canonical vector corpus count |
| `74da64c2ee95` | 调整 browse-only table addition History 断言 |
| `d4c75b004707` | 输出 row-count mismatch 诊断 |
| `f6d979f5a262` | 支持多行 INSERT benchmark 输入 |
| `86f1b3b6628c` | 复用 W4 key index |
| `3a3fd5dad33b` | 修正 key candidate union 类型 |
| `61865d3b90f5` | 复用 W4 fresh-key candidates |
| `80ce75661929` | 修正 expanded W4 输入行数 |
| `23ba083a10e3` | 冻结 S1b real-data baselines |
| `705b17c1a137` | 按 additive-column 规则修正 t3 History baseline |

## Contract 与 golden

- Comparison facts 新增稳定 schema evolution：`NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE`。共有列继续比较；只增列（含 ENUM 标签、SET 成员只增）不降级、不生成 SCHEMA_CHANGE 风险，Submit 仍创建版本。整表新增/删除表现为整表浏览并带表级行数风险。
- Preview 与 History bundle 保留全部表绑定；内容相同的表按内容地址共享。表数据文件为 Parquet。snapshot export cache 以 `row_layout_digest + Parquet writer contract version` 为精确键，并经 artifact protection/TTL 管理；schema 或 writer 版本不同不命中。
- Upload 使用 60 秒 idle timeout 与 `最大包 ÷ 1 Mbps` 总上限；两者返回 `UPLOAD_STREAM_TIMEOUT` / HTTP 408，原因 `IDLE | TOTAL`；413 仅用于大小或资源限制。受理中的同步解压、artifact 写入及 control DB 工作在线程池执行，保留预算、断连释放和完成/取消边界。P5-5A 上传设计的错误码表已同步。
- 参照 SQL parser 为 BIT 负数/超宽/非 ASCII `b'..'` 返回确定诊断；BIT 数字字面量按十进制；支持仅用于二进制列的 `_binary` 字符串与十六进制字面量；保留 `\%`、`\_` 反斜杠；忽略列类型中的注释；JSON 拒绝 NaN、Infinity 与孤立代理，最大嵌套深度 100 且检查不递归。Shared Kernel FLOAT 直接舍入到 binary32；零日期仍拒绝。
- DC56 显式键名单按精确选择器落实：`comm_user_data(data_key)`；`forwardtbl_lst_cs/dz/qt/yc/yk/ym/yt/yx(tbname)`（8 个精确名，`STANDARD_EXACT`）；`mms_rp_cdc_index(idx)`；`out_time_cfg(board, link_no)`。显式键重复或 NULL 时稳定失败，不回退 keyless。新增 17 张 `BROWSE_ONLY`：`iec61850c_cfg`、`jdxx_cfg`、`cnt_manage_cfg`、`dev104_cfg`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、`nbridge_cfg`、`nr103d_cfg`、`nr103ht_cfg`、`sc_cfg`、`scada_cfg`、`sg_manage_cfg`、`sntp_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg`。规则文档从 v3 升至 v4；storage-projection 版本仍为 3。
- Worker 在 executor 正常或异常结束、以及收到停止信号时置位 runtime 持有的 wake event；非 drain 等待该事件，超时取下一 heartbeat 或 drain 截止的剩余时间，不用短间隔轮询。heartbeat、lease、drain 与单 executor 语义不变。build-repository-service-image.sh 的 EXIT trap 覆盖全部退出路径并清理 lock snapshot。
- Contract 文档更新：`comparison.md`、`comparison-surface.md`、`risk.md`、`comparison-bundle.md`、`snapshot.md`、`snapshot-table-access.md`、`shared-canonical-encoding.md` 与相应 capability 文档；P5-5A 错误码表同步。没有修改 p6-design、p6-execution-plan 或 owner decision record。

S1b 更新并冻结的 golden：

- comparison：`vnext/fixtures/golden/comparison/s1b/semantic-results.json`；risk：`.../risk/s1b/structural-risk.json`；surface：`.../surface/s1b/table-presentation.json`；bundle：`.../bundle/s1b/snapshot-table-bindings.json`。
- storage-projection 例外行只更新一次：规则 v4 对应的 ruleset golden 与 `storage-projection/manifest/valid/s5-durable-roundtrip/document.json`。受影响文件为 `ruleset/valid/s1-net-cfg`、`ruleset/valid/s2-migrated-matrix` 与 `ruleset/malformed/s1-duplicate-selector`。
- table-access 的 S1b 合成语义向量：BIT negative/too-wide/non-ASCII、`_binary` 文本列拒绝、JSON depth 100/101、NaN/Infinity/孤立代理、零日期及 parser semantics 接受例。
- shared-kernel canonical FLOAT 向量同步更新；Rust vector corpus count 同步。
- S1a mutation 与导入包 goldens 未改变；真实数据没有进入 Git。所有 golden diff 均对应以上批准项。

## 权威 runner、carried 与镜像

### V 上六包 runner

- 节点 `ct108-gw-dms-04`（hostname `gw-dms-test-04`），V clean worktree，2026-10-28 08:05:22Z–08:26:09Z，runner exit 0。日志：`/home/dev/gdds-p6-logs/s1b/04-runner-80ce756619.log`。
- 环境：umask 022、HOME `/root`、LC_ALL `C.UTF-8`、TMPDIR `/home/dev/gdds-test-tmp`，PATH 以 `/home/dev/.cargo/bin` 开头。Rust fmt/clippy/test 三步通过；六包状态均 passed。backend parallel 3045 passed、serial 40 passed；repository_service parallel 1741 passed/1 skipped、serial 207 passed。runner 退出时 `TMP_SNAPSHOTS_AFTER=` 为空。
- V 起始 package manifest total digest：rust `7a85c5544d4c53794ea0fadd8db803e5f273ffd3d1f2069a34fdc4332cbe9867`；shared_kernel `54e51c2a078d5e47bce39cca8277a0c3541f73036fff871c058332cc5216e928`；repository_contracts `30a2c50c7c3bd2ef296cd1b43b2d0a6896e5373d23612fe0cbb86d7aba02d3f3`；repository_client `162d732710870e114456dce5b9df267c1560a8bab539a6a9c15ea376b2aa4c44`；backend `a14a0567b049dd918cd771f5c6a785b5587e85ad36af77893427793174568a13`；repository_service `1c054008a4b790f15a09bf0f8b960df2c956c59ac7a979bce7eea5e34d83ceca`。

### H 上逐包判定

- V 与 H 的逐包 compare 在 CT04 的同一 `04-wt` worktree 完成；比较日志为 `/home/dev/gdds-p6-logs/s1b/04-carried-manifest-compare-H2-705b17.log`。rust、shared_kernel、repository_contracts、repository_client 为“可沿用”，变化组件为空，来源直接指向 V runner。
- backend 与 repository_service 的 `docker:context:vnext` 摘要在 H 变化；backend 还变化 `package:backend`，与 V 后允许的 benchmark/test 修订相符。因此两包在 H 上另行运行，未把 compare 的“运行”绕成 carried。
- H 上 `GATEWAY_TEST_PACKAGES=backend,repository_service` runner 使用 CT04 同一 clean worktree；节点 hostname `gw-dms-test-04`，2026-10-28 13:42:31Z–14:03:49Z，起止 HEAD 均为 H，exit 0。日志 `/home/dev/gdds-p6-logs/s1b/04-runner-H2-backend-rs-705b17.log`。backend parallel 3045 passed、serial 40 passed；repository_service parallel 1741 passed/1 skipped、serial 207 passed。H 的 post-sync package manifest digest：backend `7f8de198031889f7ec43f42d3a1b0e180d0a8c6bf69d4ad06b839c3cbc70e305`，repository_service `9bebcf74fbaa02fa185fe2d620790d002caa8f6221a6bd59e2ed2323aa031fcb`。退出后复核 HEAD 仍为 H、worktree clean、cache HTTP 200、Hypothesis leftover 0、Cargo target 不存在、TMPDIR lock snapshot 0、active container 0、Dolt process 0；runner 与 postcheck 均 exit 0。postcheck `/home/dev/gdds-p6-logs/s1b/04-H2-runner-postcheck.log`。
- CT04 carried identity：V repository-service image ID `sha256:bd6cb6913f94d62d8dbc8cdc636e21852a30471c43dbeb04d53239a69d6fc312`，build-input revision `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，lock SHA `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。H 在同一 CT04 worktree 重算得到相同 build-input revision 与 source-tree digest；`gateway-repository-service:local` label 匹配。identity log：`/home/dev/gdds-p6-logs/s1b/04-carried-identity-H2-705b17.log`。V build log：`/home/dev/gdds-p6-logs/s1b/04-image-build-80ce756619.log`。

### 05 门禁前预检与 H focused/static

- V 的 05 预检均通过（不作为门禁证据）：`05-static-preflight-80ce756619.log`、`05-parallel-preflight-80ce756619.log`、`05-history-compose-preflight-80ce756619.log`，均在 CT05/HOST `gw-dms-test-05`，HEAD V，exit 0；V image build 记录 `05-image-build-80ce756619.log`。
- H 的 `test_real_dump_journey.py` 58 passed（2.90s）；五个 Python 包 Ruff 与 mypy 全通过。日志 `/home/dev/gdds-p6-logs/s1b/05-focused-static-H2-705b17c1a1.log`。
- H 的 synthetic load focused 测试 4 passed（0.62s），日志 `/home/dev/gdds-p6-logs/s1b/05-synthetic-load-H2-retry1-705b17c1a1.log`。第一次因远程命令使用错误 cwd，pytest 未启动即 exit 127；改为 worktree 绝对路径后通过，未改代码。

### 网络与缓存

- 开发节点只提供 LAN 静态缓存 `192.168.233.180:18080`，HTTP 200；没有配置公网转发或代理出口。缓存目录 `/home/dev/gdds-p6-logs/s1b/dev-cache` 在 Git 外，缓存清单注明只提供已批准制品。CT04/05/CT108 的运行日志仅记录缓存来源类别与 HTTP health status，不含凭据。
- CT04 选定包 runner 的 uv lock resolution 均命中本机环境/cache；Rust toolchain `1.97.0`、cargo/rustc/rustfmt/clippy-driver 在 `/home/dev/.cargo/bin` 可用，registry source/archive 各 166 项。Rust 权威门禁命令为 offline。H backend extension rebuild 使用 `CARGO_NET_OFFLINE=true`，build-input 校验通过。
- V 镜像构建依赖的 Docker base/service images 均从本机缓存取得。H 后的 candidate Git bundle 从批准的 LAN cache 到 CT04，用于同一 worktree carried 计算；bundle SHA-256 `8cdbaa7c335a5dace3d01d2a338b0cd3bb19a330216634c94faf8403e41862bf`。

## t1–t4 完整旅程

所有旅程在最终 H=`705b17c1a137ede6b4339376527b30a4c58288f7` clean worktree 运行，容器栈已停止、卷保留。

| 档位 | 节点/hostname；起止 UTC；exit；日志 | 结果摘要 |
| --- | --- | --- |
| t1 | 05 / `gw-dms-test-05`；11:33:53–11:37:54；0；`05-t1-final-H2-705b17c1a1.log` | offline composite 4 行 unchanged；v1 Preview 125/125 changed，重复 Preview 0/125；v2 4/125 changed；degraded/failed 0；History 12 records。 |
| t2 | 05 / `gw-dms-test-05`；11:38:57–12:07:48；0；`05-t2-final-H2-705b17c1a1.log` | offline composite 45 行 unchanged；v1 Preview 209/209，重复 0/209；v2 57/220；degraded/failed 0；History 1147 records。 |
| t3 | 05 / `gw-dms-test-05`；12:11:19–13:12:06；0；`05-t3-final-H2-705b17c1a1.log` | offline composite 201 行 unchanged；v1 Preview 192/192，重复 0/192；v2 23/193；degraded/failed 0；History 711 records。 |
| t4 | `ct108-gw-dms` / hostname `gw-dms-test`；11:30:44–12:49:50；0；`ct108-t4-journey-H2-705b17c1a1.log` | offline composite 435 行 unchanged；v1 Preview 312/312，重复 0/312；v2 26/312；degraded/failed 0；History 168 records。 |

对应 stack stop 日志：`05-t1-stack-stop-H2-705b17c1a1.log`、`05-t2-stack-stop-H2-705b17c1a1.log`、`05-t3-stack-stop-H2-705b17c1a1.log`、`ct108-t4-stack-stop-H2-705b17c1a1.log`。

### step 唤醒间隔

从各档只读 control DB `step_records.started_at_us/completed_at_us` 按每个 operation 计算前一步完成至下一步开始间隔；Preview、Submit、History 共 6 个 operation、18 个成功 step、12 个间隔/档。最大间隔：t1 0.039s、t2 0.207s、t3 0.416s、t4 0.696s；均没有超过 1s 的间隔，也没有接近 10s heartbeat 的等待，因此无逐项 >1s 需说明。证据：`05-step-gaps-verify-final-H2-705b17.log`、`ct108-step-gaps-final-H2-705b17.log`。

### 显式键与 BROWSE_ONLY 核对

- t1–t4 每档的 11 张显式键表都按 Contract 列配置，表级投影无失败/降级；重复键/NULL 停止项未触发。只列非空表的行数与比较结果：
  - t1：`comm_user_data` 1 行 unchanged；`forwardtbl_lst_yx` 1 行 unchanged。
  - t2：`comm_user_data` 1 行；`forwardtbl_lst_yc/yk/yt/yx` 各 1 行；均 unchanged。
  - t3：`comm_user_data` 是 1 行整表新增；`forwardtbl_lst_yc/yk/yt/yx` 各 1 行 unchanged。
  - t4：`comm_user_data` 1 行、`mms_rp_cdc_index` 42 行、`forwardtbl_lst_yc` 2 行、`forwardtbl_lst_yk/yt` 各 1 行、`forwardtbl_lst_yx` 2 行；均 unchanged；`forwardtbl_lst_cs/dz/qt/ym` 与 `out_time_cfg` 为空。
- 新增 17 张 BROWSE_ONLY 出现时均无 compare key、无 risk annotation：t1 10 unchanged/7 absent；t2 11/6；t3 12/5；t4 15/2。t4 absent 为 `iec101_cfg`、`iec104gw_cfg`。完整逐档名单和计数日志：CT05 `05-realdata-surface-audit-final-H2-705b17.log`，CT108 `ct108-realdata-surface-audit-final-H2-705b17.log`。
- 整表浏览与风险：t1、t4 无整表新增/删除。t2 有 11 个 `TABLE_ADDED`（共 337 行；`b1_n11_iec104_cfg` 337 行，其余 10 表为 0 行）和 11 个 `TABLE_DELETED`（共 5563 行；非空表为 `b1_n5_iec104_cfg` 337、`b1_n5_iec104_syk_list` 91、`b1_n5_iec104_syx_list` 4609、`b1_n5_iec104_yc_list` 525、`b1_n5_iec104_yt_list` 1 行）。每张表各一条 TABLE_ADDED/TABLE_DELETED 风险 annotation，表级 row count 可见。t3 `comm_user_data` 1 行整表新增，1 条 TABLE_ADDED annotation。没有将整表变化伪装成逐行 records。
- t3 v2 Preview 的 193 张表中，33 张为 `COLUMNS_ADDED`；没有 SCHEMA_CHANGE 风险、degraded 或 failed 表。v1/v2 Submit 都有 repository commit ID，继续生成版本。核对日志：`05-t3-schema-audit-final-H2-705b17.log`。

### parser 真实输入检查

- JSON count-only 扫描覆盖 t1–t4 的 v1/v2 共 8 份 SQL 输入；每份 `json_value_count=0`、最大深度 0、深度分布 `{}`，扫描 exit 0。因此远低于 100 层上限。日志：`05-json-depth-final-H2-705b17.log`、`ct108-json-depth-final-H2-705b17.log`。
- V6 parser report 与 DC62 既有 census 记载 t1–t4 无 DC62 §2 P 语义受影响值；S1b 全量旅程成功解析。没有发现受影响值或触发停止条件。新增接受写法由 synthetic round-trip 与 table-access/shared-kernel goldens 覆盖。

### Export cache 与 upload 行为

- backend 权威测试覆盖同 layout 重复导出读取受保护 Parquet row file；不同 row layout、ENUM/SET label、writer contract version 不误命中；TTL 到期解除保护。权威测试：`test_repeated_parquet_export_uses_the_protected_cached_row_file`、`test_export_cache_is_exact_by_repository_and_row_layout`、`test_row_layout_cache_identity_includes_enum_labels`、`test_export_cache_writer_version_is_part_of_the_exact_key`、`test_export_cache_expiry_releases_cache_protection`。V runner backend passed；H backend 两批均通过。真实旅程重复 v1 Preview 均为 0 changed rows。
- 上传合成测试覆盖低速流在大小推导总预算内成功、IDLE 超时映射 HTTP 408 与原因、TOTAL 超时原因；`UPLOAD_STREAM_TIMEOUT` 与 413 语义由 HTTP golden/Contract 覆盖。对应测试：`test_low_rate_stream_within_size_derived_total_budget_is_accepted`、`test_idle_stream_timeout_maps_to_http_408_with_reason`、`test_total_stream_timeout_has_total_reason`；H backend runner passed。

## S1b synthetic load

生成器与规则位于 `vnext/backend/benchmarks/p6_s1b_synthetic_load.py`、`p6_s1b_measurement_runbook.md`，输出只含表名、计数和耗时；真实数据与合成 SQL 均在 Git 外。

- 2× t4 SQL：153,875,448 bytes，临时路径 `/home/dev/gdds-p6-logs/s1b/ct108-synthetic-load-80ce756619/t4-2x.sql`。
- W4 10%：319 tables；baseline/current rows 436,714/436,869；insert/delete/update 14,674/14,519/14,722；737.931s。
- W4 100% stress：319 tables；同一 row totals；insert/delete/update 145,675/145,520/145,674；726.647s。仅作为压力档报告，不设验收门槛。

## t4 性能对照与限制

t4 H 的 API stage timings：v1 Preview 804.293s、v1 Submit 557.812s、repeat Preview 693.751s、v2 Preview 846.541s、v2 Submit 271.849s、History 744.135s。S1a handoff 对照为 1546.088、579.863、872.580、1007.306、289.942、312.889s；不设性能门槛。

H 的 control DB step 聚合：v1 `materialize_inputs` 734.016s / `assemble_preview` 67.750s / `publish_preview` 0.762s；repeat 616.207 / 74.403 / 0.305s；v2 730.656 / 112.944 / 0.382s；History 595.122 / 146.011 / 0.029s。S1a 的内部 checkpoint-read v1/v2 为 45.110/58.656s，bundle v1/v2 为 51.393/2.442s。

H 现有 worker step 只输出 `materialize_inputs` 与 assemble/publish 聚合，没有独立 checkpoint-read 与 bundle 子段计时；不能把上述 aggregate 当成那两个 S1a 子段的同口径新值。v1 assemble aggregate 明显短于 S1a 的 723.046s worker assembly aggregate；v2 为 112.944s，对照 S1a worker assembly 111.196s，差 1.748s。精确的 checkpoint/bundle 子段差额本阶段无法从现有信号隔离；依 DC62 不增加产品计时插桩，保留为 S2b/owner 可复核的测量限制。

## 偏差、停止条件与清理

- 操作性恢复：第一次读取候选 bundle 时在 Git repo 外运行 `git bundle verify`，因缺少 repository 参数退出 1；改在 CT04 `04-wt` 校验与 fetch 成功。第一次 Cargo 版本探针从 repo 根目录运行，rustup 未读取 `vnext/rust/rust-toolchain.toml`；在 `vnext/rust` 目录复核到预装 1.97.0、rustfmt/clippy 与 crate cache。没有运行失败的测试或代码修改。
- S1b golden 仅在 §4.6/DC56 批准项内变化；t1–t4 显式键、BROWSE_ONLY、schema evolution、HTTP 上传和 parser 项均未发现设计冲突；无 JSON 深度/受影响值停止项；最终 authority/package runner 无失败后停止。
- H 的 package runner 与 postcheck 均 exit 0；S1b 已要求的 runner 与真实数据验收均通过。未触发设计 §17 或执行计划 §7 停止条件。
- 未清理任何 ref、worktree、bundle、Docker image/volume 或真实数据 scratch。交 owner 在独立审核与 exit 合入后清理：实施 worktree `/home/dev/gdds-p6-logs/s1b/impl-wt`；CT04 `/home/dev/gdds-p6-logs/s1b/04-wt` 与 `04-cache`；CT05 `/home/dev/gdds-p6-logs/s1b/05-wt`；CT108 `/home/dev/gdds-p6-logs/s1b/ct108-wt`；候选 bundles 与 `/home/dev/gdds-p6-logs/s1b/` 阶段日志/manifest/cache；本机 cache `/home/dev/gdds-p6-logs/s1b/dev-cache` 及 HTTP service PID/log；CT05 Docker volumes `gateway-s1b-final-t1-705b17_*`、`gateway-s1b-final-t2-705b17_*`、`gateway-s1b-final-t3-705b17_*`；CT108 `gateway-s1b-t4-705b17_*`；t1–t4 真实数据 state/artifact volumes 与 2×t4/W4 scratch。旅程 stack 已停止，volume 均按要求保留。
