# Phase 6 S5 实施与验证计划

状态：**DESIGN_CLEAR；A/B/C实现与必要证据已独审GO，准备D**；A产品`eb64578925`、B产品`e1098b2a62`、C产品`fdb2a69a43`，实际证据与未测范围见各节handoff。设计独审绑定候选仍为`75267e9a72cfb9f428b1c1e5182c1fe55f6e697f`。设计见[p6-s5-design](p6-s5-design.md)，设计源码起点main `4c648965286ec751c4395cd6111f11838610299c`。当前授权及协调角色见[实施任务提示词](p6-s5-implementation-prompt.md)：直接完整推进A–E，仅实质阻塞需确认；从C起各节新建三类子agent。

## 1. 已确认输入与交付边界

S3/S4正式退出已核Git对象与handoff；S5基于当前main保留S4树。Owner本轮确认：

1. DC33采用标准t1 v1/v2，优先复用身份可核的合法已提交状态；真实路径只做必要History冷查、复查和真实records/bundle读取；FULL、三节点、损坏/恢复以focused/Contract证明。不做fresh t1–t4、2×t4或1暖3测。
2. 五节点按DC91/DC97统一空闲池，任何产品运行均取得本节点原子占用；04/06/07同宿主、各节点缓存与carried来源不混淆。
3. AGENTS及相关执行说明只保留现行要求，不保留失效指令；历史handoff、原审和证据不改写。

本计划使用N1/单active、32GiB worker/8GiB reserve/显式M24；不是引用S3/S4 M40专项授权。若本范围不能在M24完成，先独核输入/预约/生命周期及实际失败，交具体选择，不能改预算或预期绕过。性能时间顺带报告，无数值门槛。

S5完成目标：单表diff/risk跨operation复用、History按需读表、当前绑定语义保持、TTL与Submit引用正确、恢复与资源边界闭合。无HTTP新功能、无S4 SQL修改、无新多worker调度、无SDK、无容量原型。

## 2. 小节依赖和路径归属

顺序为A→B→C→D→E。每节先固定clean已提交候选，独立审核后再核必要验证；同轮finding由同一审核者连续复审，下一节消费已核接口。可以提前只读准备后节，不并行修改相同owner。下列B为backend源、T为backend tests。

### A 纯任务契约与内存恢复接口

输入：现ComparisonPlan/TableComparisonTask、S3 facts/core与三族records、risk候选控制顺序、S4共用context。输出：完整纯任务输入类型/稳定key、neutral比较codec及risk事件接口、独立小向量、owning Contract目标形态。

- Comparison owner：B`capabilities/comparison/{contracts,pair_planning,production,native,artifacts}.py`及必要新增`cache.py/cache_codec.py`；Rust `gateway-compute-core/src/records/`与`gateway-compute-python/src/comparison*`的粗粒度restore/export。
- Risk owner：B`capabilities/risk_evaluation/{contracts,_engine}.py`及neutral事件模块；缓存仅复用完整候选，emit与时间/上限仍一份。
- 文档：Comparison/Risk/Artifacts、Rust policy精确FFI、相关import guard；不追加架构违例基线。
- 交付顺序：先共同语义输入→neutral facts/record views→内存round-trip→风险事件。先完成codec可独立调用验证，再接DB。
- 最小验证：Rust固定facts/三族语义；backend真实adapter round-trip与当前绑定digest/Parquet；风险控制小向量（含cap与到期同时发生、被过滤候选、末条emit的原时间检查位置）；import guard允许/拒绝。不建Dolt仓库验证key或codec。
- 无持久缓存发布、无History切换。默认不触发Compose重建；若变更production依赖或container boundary则按触发规则重建受影响门禁。

### B TTL存储、引用和失败隔离

输入：A的完整格式/key/reader contract。输出：cache port、SQLite entry/uses索引、TTL/protection、原子登记与read lease、有界清理；cache可丢失不污染业务。

- Artifact/DB owner：B`artifacts/`端口、`infrastructure/control_db/{schema,database,sqlite_protection}.py`与专用cache adapter；B`infrastructure/artifact_store`只复用现read/cleanup session，必要小接线。
- 先直接改基线schema→store/lookup-and-pin/discard-if-same→TTL触达/有界prune→损坏与I/O失败分类。所有成员先被登记保护；无兼容migration。
- 验证owner：新增`T/test_computation_cache.py`，用临时真实文件系统和SQLite覆盖same-scope命中、跨scope拒绝、TTL续期/过期、完整原子登记、读pin与cleanup、替换后旧reader安全、条件discard不删新条目、可选写失败。一个共享fault参数表，不建syscall故障墙。
- 保护/cleanup若发生container-only边界改动，本节最终候选运行适用门禁；纯SQLite/文件协议已由focused证明时可推至E。失败日志与未决现场保留。

### C Preview与History接线及按需数据路径

输入：A/B通过接口。输出：真正跨operation缓存生产/消费、metadata先行与需求裁剪、完整bundle导出、checkpoint恢复。

- Application owner：B`application/{pair_pipeline,preview_jobs}.py`、`application/history/{compare_jobs,compare_bindings,ports}.py`、canonical metadata/table access；bootstrap依赖注入。
- Snapshot owner：B`capabilities/snapshot_materialization/{repository_ref,artifact,client_parquet,contracts}.py`及按需描述接口。精确row-layout含source columns、labels、ordered provenance与writer，不猜schema。
- 顺序：metadata-only精确commit描述→task/cache lookup→独立export lookup→合并行需求→miss行读取/比较及hit恢复→风险→surface/bundle→checkpoint/READY。恢复时重新检cache并补读，不持久化“上次命中所以没有reader”的假设。
- Preview当前上传/identity/T1流程不替换；只按实际pair形成条目。History H1/H3/冷读及FULL例外由同一pipeline实现，无生产开关或永久双算法。
- 验证owner：`T/test_history_compare_jobs.py`证明H1/H3、FULL未计算pair、冷读、三节点/反向/同commit、坏cache回填及坏authority稳定失败；`test_snapshot_export_cache.py`只拥有row-layout+writer与导出命中语义，不复制History矩阵；Preview现测试增加形成缓存→另一op读取的接线smoke。
- 此节checkpoint改动直接改目标载荷/版本，更新对应golden，不兼容旧checkpoint。这里不得改变comparison/risk业务golden，差异无法解释即停。

### D Submit触达、RS控制与旧路径清理

输入：B索引/uses，C生产者与consumer。输出：T3可选触达、取消/截止与有界503接线、资源生命周期和旧入口删除。

- Submission owner：B`application/submission/{finalize_transaction,ports,artifact_release}.py`；不改S4 planner、SQL、publisher、T1 PREPARED及Repository effect/CAS；恢复按DC94以prepare checkpoint是否持久化分界，PREPARED本身不证明已有导入包。
- Read owner：B`infrastructure/repository_read/http_arrow.py`、必要operation read scheduler；`vnext/repository_client/src/gateway_repository_client/{client,arrow_stream,retry}.py`只增通用控制参数/有限等待，不import backend。
- 上限：RS≤min(N,8)，N1为1；不创建每表计算池，所有read/restore/FFI/输出同M。原client重试总attempt上限保持，取消deadline到open/read/backoff。
- 删除被替换的repr identity、History全表预读假设、无consumer的map-only mock/probe；保真实generic facade、原artifact validator和独立golden。
- 验证owner：`test_submit_finalize.py`/既有事务测试拥有T3成功回滚/response-loss replay、cache缺失不阻业务、BaselineHead不动；既有prepare恢复测试保有checkpoint前冻结输入缺失稳定失败、checkpoint后固定包复用/缺包失败的唯一owner，不复制新矩阵；client原retry/arrow测试拥有有界重试及通用deadline；backend HTTP adapter测试只证operation控制传到实际client，单一并发/M与释放owner覆盖hit/miss/cancel/exception。
- 提交前五Python包ruff/mypy；Rust受影响则fmt/clippy，均在专用节点。修改container harness即在本节最终候选重建适用Compose；否则集中E。

### E 最终固定候选与独立核收

输入：A–D findings关闭、固定最终产品V、已有golden与独立t1预期、Owner已确认范围。输出：当前源码/镜像绑定的必要权威包、一次真实定向清单、逐包实际/沿用/未验证矩阵、最终H与独审回执。

1. 固定产品V，先审源码/删除矩阵/资源/事务与执行稿；执行稿必须使用真实现有CLI，`uv-consume`不接受业务`--project`参数，使用受支持名称。
2. 准备本人clean worktree与legacy link；预填充实际节点cache/依赖镜像，记录来源commit、SHA、prefill UTC、镜像config digest/全部DiffID。不开公网、不用代理证据、不借用或改写原S3/S4来源。
3. 执行必要权威包及同次Compose，不另重复已过同候选Compose；失败停止后续carried/验收。五包静态与Rust构建检查按实际变化完成。
4. 执行§5一次t1定向清单，记录正确性、资源和观察时间。执行者唯一，按事件等待异常/完成；协调者不重复巡视。无预配测试角色而提前运行。
5. 原审核者核原件、SHA、起止HEAD、资源释放及失败/未知项；只有未受影响闭包才按同源规则沿用。文档H在原来源同WT计算绑定，不能把新WT视为原来源。
6. 设计CLEAR/代码GO/证据GO/阶段退出分别记录。E全部条件与独立退出核收满足后完成本地附注exit tag；未经明确授权不push。

## 3. 唯一验证owner矩阵

| 不变量 | 权威owner/最小向量 | 上层只做 |
| --- | --- | --- |
| key完整、方向/scope、规则/存储/descriptor变化miss | 新comparison cache Contract test；共享逐字段变异表与显式移除字段审查 | History跨op smoke |
| neutral codec恢复facts/artifact两序、blank信息、当前digest、Parquet bytes | Comparison Rust codec向量＋backend adapter现records出版测试各管自身边界 | 一次真实open_records_closure |
| ordered gid/no、伪gid、keyless重复、共有列/schema演进 | 既有独立golden＋cache round-trip代表向量 | 不建多套差分矩阵 |
| 完整风险序列、CheckClosure顺序、cap/filter/编号/时间 | `test_risk_evaluation.py`或专属cache test一个owner，复用现S3语义向量 | History风险结果一致 |
| TTL/保护/并发/条件失效 | `test_computation_cache.py`真实SQLite/filesystem | Compose smoke |
| H1/H3/H2/FULL/三节点需求与恢复 | `test_history_compare_jobs.py`一组共享参数表 | t1冷/暖一组 |
| 权威绑定错误、ACL、ruleset冻结 | 现History accept/transaction/HTTP测试 | 不把坏binding模拟成cache缺失 |
| T3原子/回放/不改head，cache可选 | 现finalize事务测试 | 已有Submit Compose受影响回归 |
| 503次数、deadline/cancel及stream关闭 | repository_client retry/arrow owner；backend仅参数接线 | 1个真实adapter smoke |
| M和最后消费者释放、restore/export增长前预约 | 同一operation资源测试owner，hit/miss/异常参数表 | t1 worker实际M/cgroup报告 |
| 真实records读取与完整tar | `comparison.artifacts.open_records_closure`原测试；bundle下载现owner | t1实际取出成员并读 |

固定预期来自手算、现有golden、必要时固定旧源码受控捕获；不能用新codec actual生成expected。cache on/off测试控制的是cache port/seed，不引入永久生产feature flag。写入cache后与读回cache比较只能证round-trip，必须另有独立facts/records预期。

## 4. 运行与沿用矩阵

| 范围 | A–D | E计划 | 当前状态 |
| --- | --- | --- | --- |
| rust | codec/restore改变时focused、fmt/clippy，backend前强制native重装 | 实跑，因Rust树变化 | A fmt/clippy/core focused4通过，权威全包未跑 |
| backend | 按节focused/必要集成，serial -n0 | 实跑权威包，含现History/Submit/ordered等Compose | A focused278+1、B focused162、C focused420通过；B空serial工具续步已核，权威/Compose未跑 |
| repository_client | D通用控制变更focused | 实跑权威包 | 未运行 |
| shared_kernel / repository_contracts | 无语义改动时不新增测试矩阵 | 优先核原来源同WT闭包；不同即实跑 | 尚无carried判定 |
| repository_service | 产品未改，保原wire/容量 | Docker context等闭包很可能变化；按真实manifest决定，变化必实跑 | 尚无carried判定 |
| 五Python包ruff/mypy | 有代码提交按AGENTS执行 | 最终受影响修订复验 | A/B/C固定候选分别实际通过；后续改动仍需复验 |
| frontend | 无产品文件变更 | 无新增FE门禁；若发现breaking DTO则停止修设计/范围 | 不代表FE阶段验收 |
| t1真实History | 不在每节重复旅程 | §5一次 | 未运行 |

S4四包c9e、backend/RS 6786只是可审来源线索，不是预先批准S5 carry。carried必须同来源节点/WT/环境、包专属Hypothesis路径无残留、完整manifest和镜像等价实际通过；换节点可实跑，不能搬迁旧来源判等。E选包范围随实际闭包确定，不承诺只跑三包；项目最终/发布仍六包全量。

成本估计是排程上限参考而非性能承诺：A–D每轮focused预计分钟级到十余分钟（Rust重装与环境准备单列）；最终权威/Compose以S4两包约31分钟及完整六包约33分钟的历史观察作数量级参考，预留1小时窗口，失败另计；t1定向生产读取预留约20分钟执行窗口，不含首次制品准备或必要合法状态补建。只有一次冷查+一次暖查，不做预热统计组/细粒度profile。实际更慢如实报告，不为满足估计删断言。

## 5. 标准t1真实执行清单

### 5.1 状态、输入和独立预期

- 选合法t1 v1/v2已提交状态，核输入SHA、scope/repository、精确commit、canonical manifest、source product/镜像与生成路径。先只读确认可用性；不假定旧卷存在或可改。
- 若使用他人/冻结证据资源，只能经允许的只读方式取得快照，或先协调资源owner；不启动/改写原来源栈、cache、control DB。在本人隔离命名空间使用可核同字节副本，记录来源限制。
- 当前项目无migration要求；旧control DB schema不匹配不得“修库”迁移。若存量无法在新基线下合法使用，先报告具体缺失并选本人新栈以标准t1必要Preview/Submit/审批/Archive前置建立两个节点；这只补前置，不扩成t1–t4或所有cache状态全旅程。需动他人资源或超出已确认范围再协调Owner。
- expected从已有t1独立golden/旧源捕获与owning语义获得。SET按逻辑成员序列比较内部/Repository profile，保重复行multiset；不从新History结果反填。无可核独立预期时先补来源，不以self round-trip充正确性。

### 5.2 一次冷查与一次复查

1. 本人新cache namespace无派生diff/risk/导出/可重建canonical项，保留权威commit/metadata及冻结资料。请求既有History HTTP A→B；记录operation、commit/node绑定、耗时和分层计数，READY后核完整节点表集合与摘要。
2. 下载完整bundle tar，核HTTP长度/ETag/成员闭合；实际调用现records restore/open入口读取命中的记录族，核schema/count/content及独立代表记录、风险target/编号、所有表manifest；必要代表导出表按逻辑值与独立预期对比。没有现行独立records HTTP endpoint，不虚构接口。
3. 相同有向pair用新idempotency key产生**新operation**复查；不能把同key受理replay当缓存hit。核健康条目与scope/规则相同，实际比较/单侧facts/Dolt行读取为0，metadata及cache/records验证次数如实记录。
4. 暖结果与同请求确定语义一致；实例ID按定义分离，不能mask掉records/content或本应保值的摘要。核取消/资源等本轮无异常，记录N/M、cgroup实际峰值与预约高水位，二者不互相替代。
5. 关闭本人stream/handle/栈，记录节点、开始结束UTC/HEAD、入口exit、日志/结果SHA和占用释放。原失败保持原值。

真实t1不承担FULL/三节点/每种损坏回填/所有取消点/大负载容量；这些由§3对应focused证明。真实H1 Preview→History及T3引用以focused integration证明，此真实路径集中H2/H3与读者。两次请求的时间仅观察，不计算三样本median或宣称同条件提速。

## 6. 执行纪律、审核与exit

- 测试执行前先`ssh -o BatchMode=yes <alias> 'echo OK'`，现场核有效占用、Dolt/Compose/8000，原子`mkdir /home/dev/gdds-node-busy.d`并写会话/用途/UTC；仅释放本人标记。已有入口自管标记不重复取得。
- root PATH以`/home/dev/.cargo/bin`开头，不设RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME；TMPDIR为磁盘`/home/dev/gdds-test-tmp`；UV_OFFLINE=1、CARGO_NET_OFFLINE=true。Rust四工具与selector一致，Cargo target在worktree外；Rust改后强制重装扩展并核build input。
- 所有uv消费走`vnext/scripts/uv-consume.sh`，不改锁或引入依赖；若确需依赖变化先取得授权/CT201预填充。backend/worker保dependency-base及network=none、本机Compose build，不设prebuilt。
- 唯一后续测试/等待者按提示词Luna max，普通角色不能另启动一份长测。资源/规则由设计与实施owner决定，不交Luna自行改变。总活跃≤4，独审新角色；本次设计审核使用用户临时授权的GPT-6-Astra high，该授权不延伸后续阶段。
- 协调者保持连续；按A/B/C/D/E小节新建实施、独审、测试/等待子agent，不跨小节复用角色。阶段内finding仍由该节原审连续复核，固定交接和执行收尾完成后换新角色；新角色读取必要文件/原件，不默认继承旧子agent对话或临时授权。Owner于B进行中补充此规则，本轮从C起执行，A/B历史原文不改，切换不另申请许可。
- 每节交接记录HEAD、改动/Contract/golden、focused结果或未运行、重建触发理由、最后验证image revision/source-tree、延期节点/来源；文档设计不做虚假container carry。
- 同根工具故障按DC68最多三轮有修订复验，每轮停止原次、保原exit/log/SHA并收尾；产品语义/资源失败按所属规则，不借工具重试改变预期。
- exit需A–D独审关闭、E必要实跑/合法carry绑定最终H、Owner确认真实范围完成、当前源码与镜像明确、未知/取消项列清。需要改变冻结业务语义、M、SQL/算法golden、跨scope或威胁模型时先回Owner。

本计划与[实施任务提示词](p6-s5-implementation-prompt.md)共同作为本次已授权A–E实施入口；不在小节边界重复申请继续。
