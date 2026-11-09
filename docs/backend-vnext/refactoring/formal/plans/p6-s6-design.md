# Phase 6 S6 详细设计

状态：**DESIGN_GO**；固定设计候选`9b466d788f00ea1edb9e98b88f1746f2a7bcfee7`经新S6原审连续复审，F1–F4关闭。仅授权设计、文档与设计独审，未授权产品执行。
日期：2026-11-09。范围决定来自本轮 Owner 三项明确答复，见 [协调记录](p6-s6-coordination.md)。
实施入口：[kickoff](p6-s6-kickoff.md)。独审：[review](p6-s6-design-review.md)。

## 1. 实际基线与结论边界

设计起点为 main `c391524061f0ffbabc4fc95f3ceb713b1b99526e`，实际工作区 `/home/dev/gdds-s5-design-main`，index/tracked/untracked 均 clean。前端工作区 `/home/dev/gateway-data-management-system` 不切分支、不覆盖。起点相对 S5 H 只有设计 prompt 与执行计划入口两份文档变化。

S5 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`；H=`e80f6ddbac88b47b6c41d8d2faa21e39c24dbd53`；附注 `p6-s5-exit` 对象 `5d169e6db68c2469d3ce010b469dc4b3034dd196`。当前 vnext tree=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust tree=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。

已读取并实算 `/home/dev/gdds-s5-logs/archives/p6-s5-exit-e80f6ddbac88/` 中 `e-exit-review.md`（SHA256 `2e92a3239016b5a523e2a6a3e364f02f8f3fc4cb214d9dd371af3011fe71f860`）与 `receipt.json`（`c73cced09622747470e0ef194798ad56a95ae53ef8bf175740029e75ee3f7974`）。它们确认原06六包/Compose、同来源 H 实际绑定及本人资源释放后 EXIT_GO，足以解除 S6 设计前置，不替代 S6 最终门禁。

S5真实证据为 t1 两个 History operation、四个完整 tar、独立旧源12 records/6风险 annotation。44.148/34.118秒仅观察；cold cgroup peak UNKNOWN；RS 原日志1 skip身份/原因未知；RS admission诊断及物理RiskReport专有字段未直接观察。暖 kernel/ordered单侧/RS rows为0，restore/校验/重绑/metadata非0。这些限制继续保留，不补造历史PASS。

## 2. 旧义务处置（当前执行范围）

| 原义务/依据 | 已有来源及适用边界 | 当前处置/剩余证明 | 重新开启条件 |
| --- | --- | --- | --- |
| W1/W2，DC83/DC84、总设计§16.1/16.3 | S2b a687 M24 t1–t3功能；旧t4 M16单次观察；均非S6测量 | Owner明确替换为本轮真实t4 v1、N1/M24一次首次Preview及一次原样重传，合法Submit/审批/Archive前置，末次无变更Submit；无预热重复、无median | 本范围出现业务/资源失败，或提出具体新容量承诺 |
| 2×t4全负载/§16.3全场景/一暖三测 | S3 V4b0 N1/M40 W3 MO三测；FULL只有warm+r1；18项取消、W4 UNKNOWN | 本轮Owner明确取消额外全矩阵执行；S3报告仅引用其原配置与输入，不作当前产品统计 | 明确规模/分布/consumer与专项预算 |
| t1–t4完整旅程 | S3已批准fresh功能来源；S4真实t4 M40定向Submit；S5 t1 M24定向History | 本轮取消重复全旅程；保本轮t4最小链及最终回归 | 具体修复改变未覆盖业务语义 |
| 定N 1/2/4/8/16/32曲线 | 早期parser原型不代表整链；默认N1已定 | 本轮Owner取消曲线，N1/单active不变 | 当前真实负载有线程瓶颈且另定专项 |
| DC74/BE-c完整包体积 | BE-d完整tar已交付；S5保存完整tar；前端kickoff BE-c低速下载consumer | Owner替换草案：复用可核完整tar字节，顺带本次真实GET；缺场景记缺项，不为覆盖补旅程 | 前端实际下载/浏览瓶颈或明确网络SLO |
| 存储报告、V8门禁剖析 | 原报告与本轮最终runner现成分项 | 仅整理已有来源，按对象/产品/输入/配置分列；不另跑容量普查/V8/profiling | 明确磁盘或门禁时长问题及决策用途 |
| DC78旧算法清理 | S2b/S3/S4/S5已分别完成生产替换 | §6逐项核消费者，当前无新增产品删除 | 确认无消费者且有替代者的具体对象 |
| 六包完整权威及最终容器 | S5合格来源只证明S5 | 保留：最终候选实跑全部六包、同HEAD本机重建适用容器并完整运行 | 不以阶段carried豁免 |
| 独立SDK/多worker/具名大表优化 | 总设计§1.5、DC37/DC98 | 不实施SDK/P7调度或合成大表优化；交接实际边界与owner | 首个独立consumer获准或真实规模热点成立 |

S3取消项、S4撤回28旅程/队列和原失败不搬为S6待办。M24大负载历史失败、S4 M24未测、W4未知仍独立存在；本轮t4成功也不证明2×t4、所有模式或未来规模容量。

## 3. 业务路径、不变量与风险等级

A类事实：审批、业务BaselineHead、Repository commit/main、权威绑定；B类：Attempt/operation/checkpoint；C类：可重算canonical/export/diff/risk缓存；D类：测试scope和报告字段。保原事务/CAS/幂等/认证与scope，不新增journal、sidecar、helper或evidence平台。

| 场景/当前入口 | 当前行为与失败状态 | 设计处置/唯一主要测试owner |
| --- | --- | --- |
| Preview→Submit：`application/submission/finalize_transaction.py` | T1冻结；Repository技术main独立CAS；T3核事实并原子提交Submission/ReviewSeed，cache触达可选，未知SQL错误不可吞 | 无需产品实现；`test_submit_finalize.py`，原prepare恢复测试 |
| APPROVE→Archive：`application/archive/start.py` | 当前轮PENDING阻归档，过期baseline新APPROVE拒绝；Head与正式引用在`save_archived_node_and_cas_head`同事务前移；Submit不提前移动 | 无需产品实现；现审核/Archive事务owner，真实t4在Submit后与Archive后分别断言head |
| History：`application/history/compare_jobs.py` | exact commit metadata先行、按需读行，cache失效可补需求；scope/ruleset/checkpoint权威矛盾稳定失败 | 无需产品实现；`test_history_compare_jobs.py`，沿S5已核真实来源 |
| FULL首次未算pair、三节点 | 相邻pair不能冒直接pair命中；按distinct commit合并需求；不提前多算以凑零调用 | 无需实现或重复真实矩阵；现History owner |
| 冷/暖records/risk/bundle | 同语义输出保值；源HTTP/checkpoint Surface与最终tar嵌套ref重写后Surface分别校验自身digest，跨层不强求相等 | 无需产品实现；`test_comparison_cache.py`、records owner、bundle owner各管本边界 |
| 缓存miss vs冻结损坏 | 已提交派生副本可从exact commit回填；T1后prepare checkpoint前冻结canonical坏则失败；checkpoint后只用原包/key，缺包不得重建 | 无需实现；Canonical Storage§5/现Submit恢复owner |
| 取消/截止/租约丢失/正常drain | 原context传播，释放流/lease/charge；cache不能吞控制失败，不能发布部分结果；正常生命周期日志operation_id=-不是业务操作 | 无需实现；原runtime/client控制与资源owner |
| Rust/Python边界 | core纯计算，facade负责Arrow/预算，Python保risk控制、编排/读写/发布，RS保持公共HTTP边界 | 无需新接口；精确FFI import guard、现adapter资源测试 |

以上“无需实现”基于已退出阶段的对应实现和证明，不是本轮新实测结论；发现可定位的实际缺陷时先补本页的影响、处置、唯一owner及最小验证，不恢复全矩阵。

## 4. 已确认的具体缺口与目标形态

### 4.1 Contract旧early-exit条款（独审F1）

`comparison.md` Summary Early Exit、ComparisonPlan与验收条款，以及`ordered-diff.md`的关系段仍允许所有unchanged零reader、ordered省extension；与后段S3语义和`comparison/production.py::_ordered_unchanged_native`冲突。

直接修正文档到当前唯一生产行为：完整判等包含descriptor业务schema、行数、非空raw digest，storage事实source/canonical schema、StorageRuleView、projection version及一致内容绑定；允许key transition时effective key相等，policy与表名绑定正确。普通metadata任务可以零reader；unchanged ordered cache miss需current单侧规范行按当前pair策略算ordered/occupancy摘要、填两侧extension，不读before、不跑LIS、不生成逐行records；健康同任务cache可恢复相同facts。导出/composite数据需求另算。无算法、DTO、schema或golden变更，不增兼容层。

### 4.2 最小真实scope（独审F2，留实施）

在`vnext/backend/benchmarks/real_dump_journey.py`新增明确scope `t4-w1-w2`，只允许`--tier t4`、fresh、MODIFIED_ONLY、无cross-project/派生s3 census/skip-repeat/from-step。不改变旧scope语义；参数不合法在起栈/写入前拒绝。

复用`_run_tier`现v1及repeat步骤，repeat结果完成即返回，不进入v2 workspace或History。scope结果包含实际输入SHA/规模、首次/重复Preview与Submit身份、审批Archive绑定、重复Repository mutation集合前后、timing及bundle_transfer。无变更Submit既核`NO_CANONICAL_CHANGE`，又核无新增Repository operation、main不动、业务head不动。首次Submit后业务head仍为空基线；Archive后指v1且版本递增，重复请求使用该合法head。不能直接改DB构造前置。

现 `_repository_mutation_ids` 与catalog/真实内容核对仅在特定模式启用；新scope显式复用这些真实校验，不以返回码替代。输入依标准datasets/census及冻结业务向量，不从本次输出反填expected；SET跨物理profile按owning逻辑值比对。真实catalog/schema/count与已有独立代表keyed/ordered/keyless/composite预期都保留。不因空records天然无差异新增全记录算法测试。

唯一新增测试owner `tests/test_real_dump_journey.py`：参数共享负例表；成功链在repeat结束且不调用v2/History；任何前置/重复校验失败停止；新scope必采无变更mutation校验。仅mock步骤调度/边界，业务正确性继续由既有owner及真实运行证明。

### 4.2.1 独立预期与计数采集的固定来源

输入固定为标准`/home/dev/gateway-real-dumps/datasets.json` SHA256 `78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f`及仓库census SHA256 `733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988`，t4 v1包的size/SHA从该metadata读取并逐件验证（不采用2×t4派生清单）。

真实表oracle直接引用[S4交接“真实业务核收”](p6-s4-handoff.md#真实业务核收与取消项)和[协调§18/19](p6-s4-coordination.md#18-set口径闭合与dc98短真实验证固定稿)：旧B `788ed36e7742a067bf01c16ad2e6aaed2fed91fb`，不运行旧算法重新捕获。采用其已保存的标准t4 v1完整312表schema/count及五代表表预期；SET `app_cfg`24行使用已独核mapped JSON，SHA256=`258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f`，从原B raw摘要`1ac38b4634a80eb8f1d42d13ce197a507781317869f554a1a8418d1d71427149`按声明映射，wire摘要`2c9c580537840e71b6d35f4704a9ade016adbc8521894e1483621d28da696a93`。源目录为原04 `/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-plan/appcfg-t4-b-mapped-r0-control/`，其他四表/全catalog预期循S4协调§18固定assets清单取同字节只读副本；不启动旧服务、不改旧expected。先核清单/摘要，无法定位则停止准备并报告缺失，不用当前结果替代。

| 本轮字段/断言 | 采集与核验方法 | 缺失处理 |
| --- | --- | --- |
| W2逻辑基线行需求=0 | 新scope由已核两侧完整canonical manifest按`preview_jobs._changed_canonical_tables`的owning完整身份规则独立列U/X/A/D；X/D为空，结合重复字节和现Preview owner断言，不从RS请求数倒推逻辑需求 | metadata缺失/矛盾为完整性失败 |
| kernel/ordered/restore/validation/rebind | 原worker `s3_pair_metrics`，由`application/pair_pipeline.py`输出；锁定本scope两个operation及各自pair，分别取`comparison_kernel_calls`、`ordered_single_side_calls`、`cache_restore_calls`、`cache_records_validation_calls`、`digest_rebinds` | 事件缺失记UNKNOWN，先修工具归属/日志捕获，不默认0 |
| 实际RS rows/catalog HTTP | 同RS容器完整带timestamp access日志按repository/exact commit及repeat Preview独占窗口计数；先用合法前置的Repository真实内容读取正校准rows通道，校准在W2窗口外。保原日志及前后边界，拒绝容器重启/截断/无正校准下推零 | UNKNOWN不满足本轮实际读取核验，停止证据核收；仅修捕获，若原件可只读补核不重跑业务 |
| native `input_reads` | 仅报告native Arrow输入读取，可能为current单侧，不能当Dolt/HTTP请求 | 与HTTP分列 |
| W2无Repository mutation | 现`_repository_mutation_ids`在repeat前后真实查询，另核technical main/head；本scope无条件开启，不依赖旧submit_measurements选项偶然启用 | 任一变化/缺失均失败 |

复用S5已核HTTP日志解析方法（原`e-t1-warm-resume-r3.py::access_counts`及S5交接），不复用其业务ID/时间窗。W2 current单侧摘要允许非0；真正比较kernel应为0，restore和重绑不是比较。SQL/read计数不得把验证器自己的前置读请求混入W2。若当前现成观察无法证明某必需断言，先形成具体工具修订并独审，不新增production计时/持久evidence机制。

### 4.3 计时与BE-c（独审F3）

本次采用现有计时，**不新增精确READY时钟机制**：Preview字段是POST受理响应后至首次可读观察，终态fallback按`visibility_observation`原值标明，轮询2秒；不包含upload/HTTP受理响应前时间，不称服务器精确READY。首次/重复分别记录，不能相减声称提速，也不计算median/range。Upload及合法前置有现step wall则单列，不将重叠区间相加。旧180/30秒只作历史2×t4目标背景，不拿t4观察判同条件达标。

BE-c每个引用包记source V、输入/模式/节点数、bundle identity、原tar SHA、已验证实收bytes及原完整性结果。理论低速下限=`8*bytes/1000000`秒，明确不含协议/浏览器开销、不是1Mbps实测。新scope已有`download_bundle_tar`全量消费两次Preview包，顺带保存transfer事实，不新增History GET。GET含预检/封装/发送，READY前组装/导出仍留原操作内。来源不齐记UNKNOWN，不重新启动旧栈补字段。

只读存档核对在设计阶段允许；任何新增计时、统计脚本/测试或真实消费须等实施授权并在专用CT。前端交接给出该口径，由前端owner更新其kickoff“打包”歧义，不代签FE3c。

## 5. 资源与验证范围

N1、单active、worker32GiB（34359738368）/reserve8GiB（8589934592）/显式M24（25769803776），预算不等RSS。M预约HWM、RSS、cgroup生命周期peak/events分别报告，未观测填UNKNOWN。S5 cold/warm预约分别25438132736/25438127616，不混同。

首次t4无本任务缓存；建立v1后保留正常业务生成的缓存，repeat用新workspace/key/operation，不能把幂等replay当W2。输入用真实t4 v1，不生成放大负载，不清别人缓存。M24拒绝或实际业务失败先留证、定位，交Owner具体选择；不据低RSS删预约或升M40。

新增scope focused是唯一新增验证；Contract文档纠偏引用现有unchanged ordered测试。最终六包/适用Compose包含既有H1/H2/H3/FULL/恢复/取消等owner，不在真实t4复制故障矩阵。最终gate遵守kickoff精确HEAD顺序，普通阶段carried不能替代。

## 6. 清理与能力交接

| 核查对象 | 替代者/真实consumer | 处置 |
| --- | --- | --- |
| 旧Python SQL生产parser/旧嵌入扩展 | Rust table_access + gateway-compute-python，S2b完成切换 | 不恢复旧路径；本轮无新增删除 |
| `comparison/standard.py`、`ordered.py` | metadata/degraded/envelope仍被production使用；行算法由Rust comparison/records拥有 | 保留，文件名不是旧算法证据 |
| `tests/support/table_access_sql.py` | `_parse_sql_native`测试适配与固定语义consumer | 保留，非第二parser |
| `mutation_planning/_planner.py`、`_changeset.py`、`_digest.py`等 | 通用planner/external target；`external_target_sync/_ledger_digest.py`仍消费digest | 保留，S4仅替换Submit热点 |
| `_repository_replay_renderer.py` | 已委托`render_change_set_native`，公开facade仍有consumer | 保留，非双renderer |
| Python XML parser、Risk `_engine`、artifact reader/publisher | XML语义、risk控制时序及I/O真实职责 | 保留，不为Rust覆盖率迁移 |
| 临时差分与旧缓存入口 | S2b/S3/S4/S5交接已记删除；当前没有证实需另删对象 | 零新增产品删除；若发现无consumer对象再逐项列替代者与测试移交 |

Backend Architecture负责独立能力交接：core已与Python/I/O分离，但当前私有native、backend context与初始化不是独立发行SDK。首个独立consumer获准时再收口公开session、版本/错误/close/取消/预算和打包，不启动backend/worker/Dolt即可调用的验收留该时点。P7多worker、队列吞吐及生产总容量不在S6。

## 7. 报告与完成定义

存储只按已有来源分列SourcePackage、Dolt、metadata、canonical/计算/导出派生副本、staging峰与cleanup后状态；估算与实测、logical bytes与物理占用分别列，未知不填0，不宣称全系统容量下降。门禁时长取最终runner现成包/批次分项，不重复V8。

设计完成需本轮三项范围决定落文、F1–F3有具体处置、新独审固定候选无阻塞，形成可执行kickoff。设计GO仅允许请求实施确认。S6实施完成需最小真实链、最终六包/容器、原始失败/未知交接及独立退出核收；本轮不创建exit tag、不推送、不执行产品。
