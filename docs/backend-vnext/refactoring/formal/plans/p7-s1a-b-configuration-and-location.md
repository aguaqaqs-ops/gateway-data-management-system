# P7-S1a B 配置与位置协议交接

日期：2026-11-10。状态：实施候选，未独审、未在CT验证；无B_GO/C–G通过声明。

隔离分支`p7-s1a-b`、worktree`/home/dev/gdds-p7-s1a-b`，准确起点`00ca325c2ed6d705abfa39e9528ef148e6029cfc`。A_GO原件`/home/dev/gdds-p7-s1a-reviews/a/355c54a0-a-go.md`，SHA256=`3d22ae5e4b11143e505bfb7de3cc4b06c7f226a2cee6009639580f7a2f9ddfbb`；A静态原件在06 `/home/dev/gdds-test-tmp/p7-s1a-a-static-355c54a0/logs/verification.log`。本包不改A/P6原件、FE树、main并行工作、共享AGENTS/testing-conventions，不push/tag。候选精确SHA由提交后外置回执绑定，避免文档自指。

实现依据为[A消费者/摘要表](p7-s1a-a-entry-and-contract.md)、[详细设计](p7-s1a-storage-resource-design.md)和[执行方案§3–6](p7-s1a-execution-plan.md)。本轮用户AGENTS/提示词节点及失败规则优先；不借本地DC91/DC68扩大权限。

## 配置

BE与RS各有窄`deployment_config.py` adapter，格式相同，不新增共享领域包；共享输入位于`vnext/fixtures/runtime-config/v1/`，两侧读取同一组正/负向量。`StorageLayoutConfig`/`ResourceProfile`加载至不可变typed结构，`DeploymentConfig`核公共environment/group一致。输入各限256KiB，filesystem限定1–10项，十个slot必须精确齐全；只接受bind。所有结构闭集、拒重复key、未知版本、bool冒整数、小数整数、非有限CPU/比例。path要求规范POSIX绝对路径、非root目录、source与容器path各自不相等/不嵌套；filesystem mountpoint允许`/`。source必须落在声明mountpoint下，storage ID为互异32位lower hex；每filesystem必须被使用，相同source policy冲突拒绝。min_free_bytes为正safe integer、fraction在(0,1]；未按旧隐式root推断filesystem。

资源含W/K/N/M/E/reserve、worker/backend/RS CPU/memory/swap、宿主共享预算及两个temporary cap；W=K=1、N1–256、M≤40GiB、8GiB≤reserve<E≤48GiB、M≤E−reserve、N≤floor(workerCPU)，组内规划内存/CPU合计不得超host_budget。M不是RSS。两配置摘要沿现有JCS+SHA256，不进入artifact或业务摘要。role_roots只暴露backend/worker六slot或RS四slot。已填开发profile只是结构样例（N1/M24/E32/reserve8、48GiB/8CPU宿主声明），**没有现场可运行/容量证据**，F须按实际节点修订source/CPU/宿主预算并预检。

本包不接settings旧环境入口、不打开实际root、不写marker、不核挂载/cgroup；这些是C/E/F责任，不能把纯格式向量记作部署通过。

## 逐消费者

| A消费者 | B处理 | 剩余owner |
| --- | --- | --- |
| artifacts/types/digest/validate/serialize、InMemory | 唯一location enum/parse/build；四字段不变，严格a1四位置64lowerhex；bare lookup也拒旧格式；同ID不同ref既有冲突保持 | C resolver/读者 |
| SourcePackage/HTTP stream | source bytes/doc和stream显式durable，nonce128；SourcePackage业务ID另保原形态，不套artifact codec | D scratch/接收cap |
| projection publish | durable固定kind，nonce128；不把位置加到projection/business digest | D链路 |
| canonical key/store、snapshot artifact/client Parquet | 完整repo/projection/schema/count/table/mapping输入；IPC/canonical wrapper=canonical，raw wrapper/rows/client Parquet=export，client key保完整原身份 | C store、D file/scratch |
| comparison/risk persistence、records、ChangeSet、pair pipeline | comparison显式位置，固定kind；移除records caller自定义prefix；ChangeSet保完整64hex身份，不再截16hex；cache key仍包含原scope/raw绑定 | D消费者 |
| checkpoints、preview、submit、history | checkpoint/READY/state与canonical-table-set、request/terminal evidence=durable；删除checkpoint自定义ID绕口，state kind仅四个现有producer；Submit payload bare refs严格校验 | C保护、D恢复 |
| bundle assembler/transport | 新manifest/closure/rewrite/surface-source=export；transport复用同helper重算closure；既有成员ref保留，bundle业务ID不套codec | C borrow、D下载 |
| domain Workspace/Preview/Attempt/Submission、ConfigurationSideFacts、PrepareCheckpoint/finalize facts | backend nominal与bare refs严格codec，RS nominal/Submission repository artifact独立canonical UUID；INITIAL_EMPTY null保留 | C UoW |
| archive candidate/frozen plan/audit subject | candidate函数检查manifest/source IDs；冻结JSON与subject嵌套bare bindings递归检查；digest保原preimage绑定 | C/D事务链 |
| SQLite operations/workspace/submission/archive/cache/canonical/export、HTTP | 既有decoder经ArtifactRef/nominal/domain构造继承严格codec；新增HTTP响应field validator及history bundle bare解码；DB TEXT/JSON列可存目标形态，无schema改变/双读 | C锁序/布局 |
| Local/Bounded store | bare ID已有集中校验继承严格codec；stream端口/调用者显式location。仍是原单root磁盘实现，不宣称唯一root选择完成 | C全替换 |
| active benchmark bundle fixture及测试support | 活跃producer和所有触及ref夹具改新协议；RS假ref用UUID，不更改历史P6报告 | G最终回归 |

没有新增locator表、location冗余字段、旧格式fallback、迁移/回填路径。Ref协议切换不改变权限scope、Head/T1/READY成功事实或exact-commit恢复资格。

## 摘要与golden

`configuration-facts/v1/frozen-full.json`仅替换两source IDs，并按原`SHA256(JCS(asdict(facts)))`重算facts_digest。`archive/v2/identities.json`仅candidate的manifest/source refs及原candidate digest改变；fixture中其他独立facts/subject digest输入未被伪称为同一次事实的后代。其余archive向量载荷未变。原绑定未删除。

Snapshot artifact_content_digest排除row artifact_id，固定bytes/descriptor/profile时保持；含row refs的wrapper JSON/raw SHA改变。records不含ref的manifest/content、canonical state/table/projection、规则、cell encoding和replay SQL算法不变。comparison/risk closure/cache envelopes和含这些raw SHA的surface/bundle摘要可按原完整性公式传递变化。`comparison/s1b/semantic-results.json`、`risk/s1b/structural-risk.json`、`bundle/s1b/snapshot-table-bindings.json`、`surface/s1b/table-presentation.json`及mutation renderer golden均未重录：这些既有向量核业务投影/内容或直接raw成员绑定，不要求变成新的位置输入。实际保持/roundtrip与新raw闭合由固定focused稿验证，当前未写PASS。

## 验证与交接

当前按main `e0bde022a0cfdfefc33d48a8c20b19899fa1bd20`最新Owner规则完成host focused：五包ruff/mypy、既定74项backend unit串/并行、RS共享配置JCS与独立distribution owner，必要数据使用真实Arrow/Parquet/SQLite与固定业务golden。开发机只编辑、只读分析及独立fixture计算，不执行产品测试/静态/编译。Rust/backend五依赖输入不变，RS仅新增精确rfc8785的新锁b47；依赖缓存来源仍如实记录。旧固定完整脚本及其逐次构建审批限制是历史；当前不调用其末尾History Compose。

Current HEAD由外置回执绑定；Container rebuild required：yes，执行点G最终候选（实际Compose harness及RS依赖闭包变更）。`test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart`和`test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`的observer、zero-write/restart、完整同/分盘容器结果明确deferred→G；B current container gate未执行，carried none，不由格式/unit通过冒充。完整t1旅程及OpenAPI/bundle集合对照仍留G。

C接位置resolver、typed本地root、原子对象目录、no-replace/copy/读者与保护锁序；D接file/scratch/download/全部消费者和bounded维护；E接RS真实布局；F接settings唯一配置入口/实际mount+cgroup/render；G接确认范围真实链与最终证据。Owner给协调者确认的G范围不在B执行。本包不开始C、不宣称S1a完成。

## R1 修订与待复审

原审固定`df0116245fdb15d074d12eddf959972a0240ffb6`，报告`/home/dev/gdds-p7-s1a-reviews/b/df011624-r1.md`，SHA256=`835d13c4cc4a429ac61f8e16e3e1ac1635ba4461ab6b9f0fc549da0ad2bf7370`，结论B_NO_GO/SCRIPT_NO_GO。首候选未执行，以下是同包准备的修复，不把静态finding记作测试失败或自行关闭。

| Finding | 修订 | 验证owner |
| --- | --- | --- |
| F1 Preview缩进/未绑定bundle | 两个分支共用strict ready/bundle解码，保持CheckpointDecodeError；ready ID/ref一致、bundle在READY closure内 | Preview fresh/replay既有focused，新增非法bare/closure绑定向量 |
| F2 risk截24hex | 三类producer共用完整digest身份helper，删除截断 | risk contracts的仅后40位不同区分向量 |
| F3 History/typed遗漏 | History assemble恢复、publish及公用job-state解码均校验bare/ref与bundle closure；SnapshotTableBinding使用codec | History既有focused及bare/ref/closure负向、nominal boundary |
| F4 夹具/golden | Ready按完整新ID字典序重建正向raw和SHA、负向确实逆序；大集合按真实ID序断言。Submit canonical基础ref全部合法。RS SQLseed恢复UUID，metadata两处隐藏hex source及SQL closure IDs改为目标形态 | checkpoints/submit payload、real-dump工具unit、commit metadata |
| F5 stream先写后拒 | ID构造前移至消费stream/建staging前，后续ArtifactRef构造也在本人staging收尾try内 | 输入一旦被迭代即失败的负向stream，且无staging残留 |
| F6 依赖身份与daemon | 固定06本机两个tag/四项offline env；在sync/测试前按官方--print-input核候选backend完整输入/tag/label及RS lock/tag/label；无代理且本机Unix Docker endpoint；失配/缺base立即停止 | 修订执行稿及唯一测试者实际预检原件，待原审核收 |
| F7 golden owner遗漏 | 纳入archive_queries实际冻结向量owner及real_dump_journey工具unit（不是真实旅程）；所有阶段非0即停 | 修订固定选择器 |

READY wire SHA按新raw更新为`sha256:3a30adbe13c24e6363028b4474ab78735b97c22bf9b0ce00d2d8201016a26a00`，仅ID载荷/排序的原公式重算；不改变生产排序或去掉raw断言。resource/config/业务规则golden未额外重录。stream问题在实施者提交后只读自查先报告，原审独立复核；其余问题按R1原件保留。本次未在开发机运行语法/产品测试/lint/编译；新候选仍需原审复审SCRIPT_GO、CT实际证据与最终B核收。


### F6 来源与选中tag修订

R1修订候选849cf6f799中的d054是旧Cargo.lock输入，原审尚未准许正文，未发生产品执行。选中base改为当前完整输入578；可信source commit53746c7236a79c96bd41587165e80683da283400、input/image identity/归档/06 LAN预填原件及SHA全部在[验证稿F6来源](p7-s1a-b-verification.md#f6-固定预填来源补充)。正式稿先核来源SHA及候选tag_inputs，再对当前06两个dependency-base导出config原bytes与全部有序DiffID逐项匹配；RS仅取精确6dc base条目。现成verifier原字节纳入候选，SHA保持。没有新建/覆盖/重tag base，没有将未保原件的内联计算冒作证据；旧P6只提供依赖来源，不提供B产品通过。当前正文/导出均待原审SCRIPT_GO及唯一测试者执行。


### 正式执行 backend ruff 失败与修订

06固定候选bba9的第一次正文在backend ruff F841退出1；原日志及SHA、实际触及/未运行范围见[验证稿首次正式失败](p7-s1a-b-verification.md#首次正式执行失败与范围内修订)。此次不覆盖失败原件：删除因fixed ID kind替换而失去唯一用途的restore context/prefix残余，静态追踪唯一caller并加入既有native Arrow restore owner单例；其他publication的控制/取消回调保持。尚待同原审与CT新候选完整稿复验，不由实施者自签finding关闭。

### Owner补充：S1a最终交接要求

Owner要求G实证规范化OpenAPI与S1a基准不变，bundle tar的logical_path成员集合及manifest字段集合不变，并逐项列出ID/摘要**取值**变化；当前B没有完成这些最终对照，不预填PASS或将字段集合不变替代取值分析。BE-b第二步设计须在S1a本地exit并合main后由后端设计会话开始，随后实施，前端设计会话参与审核；旧“现在开始”作废，B不提前开展BE-b。DC74未生效并随P6退出关闭，不能作为本轮额外门禁或冻结资源约束。此补充保留交接，由协调者main记录和G收口。


### d97 backend mypy 失败与修订

06 d97的backend ruff已通过，mypy因两处负向测试的动态`replace(**dict[str, str])`出现19条类型不匹配而退出1；[原日志和修订依据](p7-s1a-b-verification.md#d97-backend-mypy-失败与测试类型修订)保持。改用带具体record类型的共享mutator表和固定keyword，保四个Attempt/两个Preview非法ID场景与错误断言，不使用type-ignore/cast掩盖。没有产品算法或配置/ID/golden改动、没有删测试；等待同原审与CT新候选复验。

## 2bacea RS distribution failure修订

06候选2bacea日志`/home/dev/gdds-test-tmp/p7-s1a-b-2bacea83/logs-r1/verification.log`，SHA256 `627608c5b62a318c36ce6242f426704625cc71232271e25479d090b6c8ab3cf0`，原exit1且本人资源已释放。五包离线同步及shared/contracts/client/backend静态已通过，RS ruff通过；RS mypy因配置adapter非法跨包import报两条missing-import而停止，pytest/Compose均未运行。本事实不是B_GO。

既有`test_distribution_boundaries.py::test_repository_sources_do_not_import_non_repository_packages`明确禁止RS import shared kernel；`repository-workspace.toml`表达三个独立distribution及仅contracts的repository依赖边，其RS forbidden_imports数组没有逐字列shared kernel，不能误引。修订RS使用精确锁定的`rfc8785==0.1.4`及stdlib SHA256，并在窄adapter保留与BE相同的I-JSON整数/有限数/Unicode scalar与noncharacter拒绝。BE仍用现有shared-kernel实现，配置边界将其CanonicalEncodingError转为ValueError；两侧共享完整冻结JCS preimage/SHA、Unicode/数字有效及拒绝向量。新增既有包边界owner selector，不改独立distribution约束、不加type-ignore或MYPYPATH补丁。

RS新lock SHA `b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f`，仅增加该版本rfc8785及root要求；production Docker ARG同步。backend五输入及578不变。RS新base必须经[独立依赖准备稿](p7-s1a-b-rs-dependency-preparation.md)原审后生成完整原件，经LAN预填06，再将实际identity SHA固定入新正文调用wrapper后复审EXEC_GO。旧6dc仅为备料输入，不再作为当前RS依赖base；全部旧候选/失败原件保留。当前没有运行新构建、预填、语法、测试或编译。


## f3d首次host focused产品失败及六组修订

06候选f3d日志`/home/dev/gdds-test-tmp/p7-s1a-b-f3d12825/logs-focused-r1/verification.log` SHA `0c2f392f5dbd4d7edfa940e130f665c5c4f31781f0cbc6aad74ae8e0819302aa`，JUnit backend-unit.xml SHA `fb286fe6f6d96e03d4f470efe29ac054e7557712d08c08e15186156ad630ce13`。五包offline sync/ruff/mypy均通过；backend非serial为24failed/1853passed/4warnings，原exit1、logger0/SSH1，source clean、本人资源释放。后续backend serial及RS配置pytest未运行。原件经LAN只读复制至实施者外置目录并逐SHA相同，不改写原失败或把局部通过拼作整次exit0。此为产品finding，不适用构建环境快修掩盖。

- 19个canonical metadata用例共同被遗留`ipc-t_000`前置fixture拒绝。row_ref改合法canonical test identity，保312表/不读IPC/不写状态及18个故障注入断言，不删向量。
- job corrupt-digest helper旧payload-ref前置失败：helper用durable固定kind/seed生成合法ref后仍实际改坏bytes，继续期待raw_sha256 mismatch。
- SubmitAttempt空manifest：恢复字段nonempty检查先于a1校验，保持既有非空错误；非空旧ID仍拒绝。Submission同字段检查顺序一致。
- 空canonical closure：期望按真实新ID字典序排序，不改生产排序或fixture ID来凑旧先后。
- BLANK closure：原case在失败前已通过core/comparison/table及ordered/blank summary，后续Risk/Parquet断言尚未到达。本轮保P6 `comparison/s3-e/old-python-expected.json`内容和provenance不变；独立新建`comparison/s1a/blank-location-closure.json`，用标准库从既有冻结字段重构完整旧JCS preimage，精确复现7b589a48…；仅替换两个ref ID后推导88b8424f…，与原实际失配值相同。记录旧/新closure、完整ID、未变manifest preimage和SHA；consumer核发布的确切refs/manifest/closure bytes，并继续全部原业务/Risk/Parquet断言，未盲录新golden或宣称未经复验通过。
- Surface旧cache-local负例被fixture hash成合法export ref，故不是实际无效输入。Surface/Bundle两个validator与两份Contract helper统一用中心strict a1 codec，删除不可达旧prefix表；合法opaque ref不按hash前种子猜cache/flow授权，scope/完整closure/READY owner保持。共享负向表在有效request构造后定点污染ref，仍期待assemble FAILED/无surface；另直接核constructor、Surface/Bundle ref及Contract边界拒绝。bundle logical_path禁令不动，未将失败改成READY。

本次修订不改Rust/依赖锁/镜像recipe或image labels；新产品候选继续使用真实source_commit=f3d的b47依赖缓存（完整依赖输入不变），不为新产品提交重建/retag或虚构来源。原审只核实际代码/Contract/fixture差异一次，唯一测试者在新clean候选按受影响范围复验，74项host集合/RS owner仍保，完整Compose/harness deferred→G。不在开发机测试，不改预算/预期来制造通过。
