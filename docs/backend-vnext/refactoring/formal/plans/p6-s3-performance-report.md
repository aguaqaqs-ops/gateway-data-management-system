# S3 W3/W4 诊断与容量补测记录

2026-11-09最新：**新V4b0的W3 MO一预热三测量、W3 FULL预热及r1已独核；Owner已确认取消其余18项。一次现有证据聚合原exit0，W3 MO实际统计见§13，待原E核收；随后只余最终H绑定及原E总核收。** 本文把实测、重构及未运行分开；不将准备、失败或未知计为通过。早期各节按其当时事实保留，最新范围见§12。源码与门禁见[累计交接](p6-s3-candidate-handoff.md)、[协调§39](p6-s3-coordination.md#39-full-r1及一次现有证据聚合)及原E[独审](p6-s3-e-review.md)。

**Owner最新口径（2026-11-08，DC97）：性能指标是否达标不再作为退出依据，只要求可靠测量。** 本文60／180／600秒等值保留参考，“未达／未知”不改成达标；未达本身不阻塞退出。剩余退出取证关注已确认范围、真实统计／来源与限制、业务／资源安全、独审和最终H绑定，不要求把慢样本优化到目标内。

## 1. 固定条件与计时范围

已失败新档来源产品 V=`1e669c053f2486c50a8413c58de11d923d7f3cad`；局部排序预算修复候选为V4b0，见§7，尚无成功warm。两者Rust tree均=`9d4f84ce0897099402226c77c548c487c4912008`，与 main 后续 S4 B/C 算法隔离。CT108／`gw-dms-test`，32 vCPU／64GiB guest；本次唯一增预算档为 **48GiB worker hard envelope、8GiB reserve、M40GiB、N1、单 active**。生产默认仍32/8/M24。实际容器及端点资源守卫须逐次取证，授权与静态配置不证明生效。

性能范围为现役 `--scope t4-identity`：fresh v1 Preview→Submit→Archive 建立基线，再测 v2 Preview；省略重复 Preview、v2 Submit 和 History。完整功能由另组默认 N1/32−8/M24 的 fresh t1–t4 证明，两种范围不相互替代。READY 观察是接受响应到首次可见结果／终端的 host 端计时，保留实际 polling 粒度；不冒充服务器内部精确 READY 瞬间。每组需1次成功预热和3次成功测量，预热不进入中位数／范围，失败不补位。

accepted 输入13文件清单 SHA256=`cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3`，原字节归档 SHA=`4008b3f876d554b96aca5c59e09c0a906e51d032dbb533397a87543f1eaa949f`。W3为2×t4；W4普通档每表约10%混合变化，另100%压力档；MO与FULL分组。数据、规则、冻结golden及schema不因资源支持改变。同组固定节点、资源和输入，硬件／资源档变化后的结果另组报告，不与原基准混算提速。

## 2. 原M24失败和只读重构

原产品 V774 的 W3 MO warm 已进入基线 v1 Submit，因 `operation memory reservation exceeded` actual exit1，未到 v2 Preview。首拒 stage、表号、requested/live仍未知；不是已证物理OOM。v1 Preview114.783s、631新增表、0 native compare属于另一前置操作，**不是 W3 v2 READY 或比较提速样本**。原始失败、私有三卷归档及完整 SHA 见[容量停止报告](p6-s3-e-capacity-stop.md)。

CT108 对原归档只读重构631表、683,508行：实际 Arrow nbytes152,303,216B；按现行行预约、reader/replay生命周期复算总29,677,814,302B（27.640GiB）。M24模型出现交叉，M40模型未出现；没有同时打开全部reader、未覆盖全部pre-adapter预约，也未构造v2 canonical，不能倒填原首次拒绝点或证明M40/FULL容量。报告 SHA=`89fb32ffe03c87852fa4a0a9a688ca687b29066efb0e2ebc434bdbfecb5a5fc6`，原 E §66–67核收；据此固定新档设计，而非修改算法或降低预约式。

## 3. 当前首轮新档实际失败

04 当前 V1e 全六包及同次 Compose／镜像绑定 actual0，原 E §71已独核；CT108源码、13输入及镜像准备也已核收0。首个 M40 W3 MO warm 于18:19:35–18:23:09Z运行，**node／outer exit1，成功预热数0**。

旅程在 `wait_repository_service_ready` 失败，唯一RS容器 exit3、`OOMKilled=false`，日志为无法导入 `gateway_repository_service.app`。三服务ready、开始端点guard、worker及首业务动作均未到；result `start_resource_guard_count=0`、`worker_count=0`、`resource_verdict=INCOMPLETE_OR_FAILED`、`acceptance_complete=false`。这次失败没有测到M40预约或v2比较，不能写成容量失败或通过。

控制端原件：`/home/dev/gdds-test-tmp/p6-s3-resource-performance-e76342ef0b/warm-control/`，实际源为V1e；outer SHA=`4143fc2f389a3e1e62905d3332686838a446b594c6a1f72cc8d28e352f7082fa`、result=`02201f9dfcaea5e18fa6a3a2e78a8659bb0ac18f9830866706a018b67d9ac478`、journey=`231076e7bbe21434f3eddb117cb519af9f3f6de14833b35d3afd11cbf4e8c624`、RS log=`165fcc9811c5e757beca09b54bddd4f7c205cda781555684adb42ed8f242c8e8`，控制捕获与节点原件SHA一致。原 E §73／`e236037ef7`核收。原停容器、镜像／tar、卷和本人marker保留待修复；没有改写原result或无修改重试。

只读stat显示：CT108和05新worktree的源码目录0700、文件0600，04过门禁worktree对应0755／0644；RS Dockerfile COPY保留源权限，entrypoint由root降为gateway。此链支持准备环境权限根因，容器内底层ImportError未单独重演。原实施者正固定只处理公开tracked源码权限的新准备稿及新镜像／fresh warm；secret、venv、输入和原失败资产不放宽或覆盖。此为同根工具错误的第1轮修复准备，实际复验尚未执行；05 t1尚未开始并因同根前提暂停。

## 4. 样本矩阵与目标

| 组 | 当前实际执行 | 有效warm／测量 | v2 READY／完成、中位数／范围 |
| --- | --- | --- | --- |
| W3 MO | 原M24基线Submit失败；M40首轮RS启动失败；修订M40 warm在v2 Preview失败 | 0／0 | v2失败尝试221.885s；无成功READY／完成统计 |
| W3 FULL | 未运行 | 0／0 | UNKNOWN |
| W4约10% MO | 未运行 | 0／0 | UNKNOWN |
| W4约10% FULL | 未运行 | 0／0 | UNKNOWN |
| W4 100% MO | 未运行 | 0／0 | UNKNOWN，压力业务成功也须独立确认 |
| W4 100% FULL | 未运行 | 0／0 | UNKNOWN，压力业务成功也须独立确认 |

S3诊断起测与S6正式取证分开。保留S6 W3 READY≤60s、W4 READY≤180s、完成≤600s目标；100%压力档无性能门槛，失败仍报告失败。未形成1warm+3，不给正式统计或达标结论。剩余23项外置稿待首warm成功及原E复审，当前没有启动；磁盘须按首warm实际归档大小、现存原件和现场余量核准，不能自动删除保护证据腾空间。

## 5. 分项与结论边界

修订M40 warm已到完整负载v2，但在assemble步骤失败，未形成完整pair／bundle分段。该次已观察的MODIFIED上传投影为5.8700875s；比较、records/JCS、Parquet、Risk必要列转换、surface/bundle、native调用／输入读取／去重计数及v2 M40账本高水仍 **UNKNOWN**。D阶段两表六场景已核诊断只说明其明确有限范围，不能顶替本矩阵。W2没有行比较，不计入S3比较提速；真实0去重命中合法，不承诺跨表或FULL命中率。

后续只按实际v2操作／step窗口归属服务日志：compare-read/build包含native records builder及其中未独测artifact JCS；随后table/facts-core JCS另计；Parquet写属于records publication内部。Risk必要Arrow转换属于lazy view遍历时rules evaluation内部，digest/report JCS及artifact publication属于Risk publication内部，不能将嵌套值再次加总或用残差声称纯规则CPU。pair局部未观测的投影／bundle `null`不当0。cgroup各容器生命周期峰、进程RSS峰、操作M预约高水和host可用内存分列，各自峰不代表同一时刻总峰。

后续实际结果、修复复验和独审结论追加到本文；当前没有性能豁免、S3 E GO、最终新H绑定或阶段退出，tag／push／发布均未办理。

## 6. 首轮工具修复准备核收与进行中状态

原 E §74／`70bc1d5dfc`已独核CT108第一轮修复的**准备范围**：从同V1e和bundle新建umask022的运行WT，910 tracked公开文件／95源码目录分别核644／755，旧WT和坏镜像不动；强制native input9d4f、六锁0漂、clean、三镜像真实config／全DiffID及原marker释放0。18:39:08–18:40:29Z outer/node/capture0，直接原件`/home/dev/gdds-test-tmp/p6-s3-resource-repair-r1-1e669c053f/prepare-control/`：outer SHA=`e0dbed5c93495953023603cfbdf9a5b16ab782406eeb2281870c6495f658c0cc`、node=`380a26b8dce86e9cae23150c3573257472496854e6bf7810e4160b76abc97e86`、prepared-images=`0affc906dade8840daf419ed93bc23463dcbc317c1590b5aa16919bd646da1d9`。这是PREP_PASS，不是RS运行或M40容量结论。

未执行的旧r1warm稿因在释放标记后重hash大型tar被撤回；修订稿先在占用内封node核心result、tar SHA及manifest，最后删owner／rmdir，真实释放事件绑定封口SHA经stdout返回，控制端核原exit／远近原件／postflight后另封最终acceptance receipt。node pending快照不预填释放成功；postflight失败仍先捕获原件，再判失败。业务、输入和48/8/M40不改。固定driver SHA=`5bc3a65c1776e66808364a73d621be4981ef33b8a90458fa0606c3d521c20e54`、controller=`cd3d857f36766b03955b80ded88547567bff2e1e731f9222aac81b048fbdb956`，原E静审CLEAR后由同一Luna仅执行一次。

截至本节提交，修订warm已在CT108实际运行，监控观察到三服务ready、首业务前资源guard通过、v1 Preview成功，随后进入v1 Submit；**尚无封口完成结果、v2样本或本轮成功warm**。该监控状态不代替最终原件与独审。第4节仍为0有效样本／UNKNOWN，剩余23未启动。05默认32/8/M24完整功能证据另在累计交接逐档列出，不混入此性能矩阵。

## 7. M40修订warm终局、局部排序限额与新修复候选

§6修订warm现已封口：node18:48:18–19:24:07Z、outer截至19:24:12Z，原exit1，成功warm数0。v1 Preview119.097s、v1 Submit1658.57s及真实read／approve／Archive成功；v2 Preview从19:20:11.233Z到19:23:52.809Z失败，step尝试耗时221.885s，原诊断`RESOURCE_LIMIT_EXCEEDED`。**失败尝试耗时不是成功READY／完成样本**，没有启动后续23项。

直接原件`/home/dev/gdds-test-tmp/p6-s3-resource-repair-r1-1e669c053f/warm-r1-control/`：outer SHA=`026decbb0a245bc76cb303bf3675fa63030c40781305b1de3ed225b6f7eaccf8`，node stdout=`93bd357797d38f304993545d18b61b4b0e0410c0aa07b511d2967a62adc4b50b`，result=`06c0ad41e0aae2a0e1739b6b8534ab9d419228f73b57f138f658559d51431a72`，journey=`7e3201eaa15fe162777b4c8bab47d0f792ace8960c4346a72679622bd42dad33`，manifest=`8ffa2908b930d2513cee4cffad3de7631d88c26d1b17fbb4bdb463436b24cfb5`。原E §78／`1cba6b0331`已逐项对节点原SHA独核。

资源守卫与业务结论分列：同一worker的48/8/M40/N1配置、三服务开始／结束guard、全部OOM三键0、正常SIGTERM、当前镜像绑定、clean／六锁均合格，worker生命周期cgroup峰16,869,629,952B，host MemAvailable起67,335,496,704B／尾64,861,898,752B；这些峰不是原生排序charge或M账本。业务仍exit1、node sealed success=false、acceptance=false、warm=0，失败停资源与原marker保留；`resource_verdict=PASS`不能作为整轮PASS。

只读control DB副本诊断actual0，原E §79／`df50b0058d`核收：materialize_inputs attempt1成功，assemble_preview attempt1失败；持久message长度28、SHA=`0544e9a68fbb93babbd3c2708859535a3e67180a58f6d2393c78f6aa449677b7`，没有原requested／live细节。该SHA精确等于固定Rust源码`records sort budget exceeded`，出自`records/source.rs::build_family`六个局部排序guard；Python比较生产入口每表固定传`max_sort_bytes=2 GiB`，与M40独立。原E §80核收此源码归因。**不能将本次失败称为已证明的M40总预约拒绝，也不能靠单纯增M解除该固定guard。** 具体表、记录族、哪一guard及首次被拒字节数仍UNKNOWN。

可选checkpoint引用盘点首次执行被受控uv wrapper拒绝外部脚本路径，node／outer exit2，尚未读取checkpoint；原E §81保留其原件、未重试。该工具失败不覆盖前述原M40业务失败，引用盘点并非修复必要前置，也不绕过wrapper限制。

原E对局部设计`a01149fc…`给DESIGN_CLEAR：仅把已在Python M账本预扣并交同一Rust KernelContext的`native_budget`透传为排序上限，保留FULL JCS排序、全部增长前租约、M40／N1及现役512MiB输出／reader、2m记录／1024行组界限，无新开关或Rust／FFI改动。第一代码候选acb417只因低cap测试释放断言不可达而修订为 **`4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb`**，原E §83静态CODE_CLEAR；06 focused于20:14:04–20:15:22Z actual0并在§85／`1207de61b6`独核，native9d4、backend Ruff／mypy0、134 nonserial＋1 serial通过。原expected／golden和业务断言未回填新Rust输出。

新候选尚待集中门禁、当前产品完整fresh及新的W3 MO warm。旧V1e在05的t1–t4已各档fresh且独立PASS，仅记旧源功能回归；不冒新V4b0或M40性能结果。第4节仍0有效warm／0测量，23项及聚合仍HOLD；后续只有新合格warm、独审和实际tar／磁盘准入满足后才推进。

20:40:43Z，旧M40失败标记已按原E静审的release-only稿实际释放，node／outer0且原E §88独核PASS。只新增外部收尾报告／receipt并移除本人marker，三停容器／三卷／一网络、旧WT、DB、输入、镜像和runtime tar均保留，原失败result／manifest逐SHA不变。sealed closeout report SHA=`238eb665f64b8d571299144fbd393abbab81f76f2e4897664148df43e67c873b`、control receipt=`59cceabba4d2c4bb451b509a0aa84b19f9f927e3f1de1a4d308305046b52e9cc`，见[协调§32](p6-s3-coordination.md#32-排序预算修复后的当前候选与集中验证)。释放不是warm成功；后续新准备／warm需重新现场准入，未预留CT108。

## 8. 新V4b0首暖前置核收

截至21:05Z，新V4b0的04权威两包实跑＋四包同WT直接原V1e沿用、当前Compose镜像出口均actual0，原E §92／`da66ded9b9`已核PASS；原runner SHA=`962a23b2f94b51668c5b8e2af098e1dd312b8590341311052ec590f814cb7a4d`，outer=`03aed7a69e2c3afd71a1feecf9790a790201fc598123e4c9d57a22b204baa4c0`。CT108新source／13输入／镜像准备actual0已在原E §89独核PREP_PASS，outer=`54ac09bc4d7e09aad6ef5e1e5283515d59431f00a2bfb7531338b3ea5bd70a9a`、prepare.log=`f0031eaecced560fd3cdaadc02f7dae9e996fc0fd14307e2383686d64bce46a0`。这些满足首暖稿固定实际来源的前提，**不是首暖或M40业务通过**。

原实施者已把上述真实SHA填入新V4b0 W3 MO稿，原E对字面终稿复审CLEAR，协调只交唯一tester单次执行。driver SHA=`312a9d394a5c9384ee67276b2c97265ddf56bdc794b90af7f3fcad9fc124d967`、controller=`36bcbd3afa49f2c666d8cfe4dd5a15cfc8d789546998fb45c2f55123d2865cd2`、WARM说明=`25b52cc2ae7bbab9821f87ac9a05658bbfe7a2707bee9d46d1036dae1f431514`。后续实际运行时另核48GiB envelope／8GiB reserve／M40／N1、同一worker、三OOM键、真实runtime镜像及全部资源／封口守卫；构建时传配置不代替其生效。当前矩阵仍0有效warm／0测量，剩余23和聚合未执行。main移植1ecb的代码及06 focused PASS另记[协调§33](p6-s3-coordination.md#33-v4b0权威核收与main最小移植实证)，不混入隔离Rust9d4性能源。

## 9. 首个合格W3 MO预热的实测与范围

新V4b0／Rust9d4在CT108以N1／单active／48GiB worker／8GiB reserve／M40运行首暖，21:07:35–21:50:41Z node／capture／postflight／outer全0，原E §98／`6e30955ff4`独核PASS；真实基线v1 Preview、Submit、read／approve／Archive以及v2 Preview／身份摘要均成功。直接control路径见协调§34，outer SHA=`cb3d4403df16b78272be052d46bc3163c41a0430048e1649e762ea964618162a`、journey=`87d7c55822ec64df83a887361e50722a141df2aac9dd776e38632540f0bba7b1`、最终receipt=`626ccab83ae5a235a5d4f2e979ee5db082e22671ff97e09582aae7e5d7408b73`。该receipt是1次成功warm、0次测量；节点sealed pending快照不回填释放事实。

v2 Preview操作从21:39:21.383Z到21:49:21.093Z，旅程记录`user_visible_seconds=599.71`、`completion_seconds=599.72`，可见观察方式`operation_terminal_result`、poll间隔2s；不是服务器内部精确READY瞬间。**该预热可见值超过W3 60s目标；完成值接近600s，不能据一次预热签正式达标。** 身份摘要核验在21:50:20.448Z完成；v2业务step整体窗口21:39:21.084–21:50:20.719Z、wall659.635s，包含这段后置核验，不与操作完成时间混称。该step原CPU累计backend17.489s／RS13.912s／worker561.726s，counter reset列表为空；这是完整step CPU，非仅599.72s操作窗口。另行请求的事后即时CPU／current memory因容器已正常清理而未采到，仍UNKNOWN；无需重启或补造。

同一v2 step内的唯一worker日志`3ccbc8c6d5e8-before-stop.log` SHA=`9ec066f2fa75949dd3e72d627f5656c9489b3b3820455ca7cd3df10c87a360f3`，含唯一v2 pair及bundle阶段事件。以下仅是这一预热的wall分段，不是1warm＋3统计，嵌套子段不能相加：

| 分段 | 本次秒数 | 包含关系／限制 |
| --- | ---: | --- |
| MODIFIED上传投影 | 5.795 | 独立stage观察 |
| comparison总计 | 310.394 | 含read/build268.373及随后table／facts-core JCS42.021 |
| native索引／比较 | 14.083 | read/build内部 |
| native records builder | 252.827 | read/build内部，包含其内部未单独量出的artifact JCS／排序，不能全称纯JCS |
| native输入桥计时／ordered当前侧摘要 | 0.003／0.378 | read/build内部，输入桥不覆盖全部上游I/O |
| records publication／其中Parquet写 | 3.199／1.168 | Parquet为publication子段 |
| Risk总计／rules | 110.255／12.293 | rules为Risk子段 |
| Risk必要Arrow转换 | 6.402 | rules内部，不另加到Risk总计 |
| Risk publication／其中artifact publication | 97.625／97.533 | 含digest／report JCS，后两者另记0.003／0.009s |
| surface／table export | 13.698 | 独立pair段 |
| bundle assembly | 104.783 | 独立stage；pair内null不当0 |

native dispatch631、实际calls182、input reads232、cache hits0，0命中是本次事实，不由人工重复key向量冒收益。上述分段并非端到端全部等待／解析／调度，不把残差称为纯Python；普通值／记录JCS及Risk转换的现有边界不隐去。比较账本high-water42,933,014,528B含native phase事先预约，不等于必要内存最小值；worker生命周期cgroup峰16,863,698,944B、VmHWM16,169,332KiB包括基线Submit及v2，不当作v2专属峰，也不与账本相加。Host MemAvailable开始67,315,010,560B／结束64,123,972,608B、三服务OOM三键全0、同worker／镜像／clean／六锁／正常stop／实际释放均合格。

| 组 | 当前合格warm／完成测量 | 当前可声明 |
| --- | --- | --- |
| W3 MO | 1／0 | warm业务／资源PASS；r1已开始，尚无正式统计 |
| W3 FULL | 0／0 | NOT_RUN |
| W4约10% MO／FULL | 各0／0 | NOT_RUN |
| W4 100% MO／FULL | 各0／0 | NOT_RUN；压力失败仍不能记成功 |

首暖tar747,672,064B／SHA=`17606ad458fc5138f0d4a97d3d24a33bbe322b5b8a676961ee8c15b280410177`及磁盘端点支持原E §100对后续固定稿的条件静态核收，实际每项仍核前序收据、输入／镜像／配置与空间。23项已获协调逐项条件授权，22:00:31Z首项r1开始；每组1warm＋3齐后交原E核收，最终再单独放行受控只读聚合。未完／失败不补位、不记通过，S6目标及旧两档失败均保留，最终H和S3整体核收仍待。

## 10. W3 MO首个测量执行结果（组统计待齐）

r1与§9预热保持同CT108、V4b0／Rust9d4、N1／单active／48GiB hard／8GiB reserve／M40、同13输入和t4-identity范围。22:00:31–22:44:16Z node／capture／postflight／outer0，最终控制收据PASS；原E完成单项SHA及前序链预核，**完整组资格与正式统计仍等三次齐全**。直接原件及完整SHA见[协调§35](p6-s3-coordination.md#35-累计代码核收与首个测量原结果)。

| 样本 | 可见观察s | 操作完成s | 当前结论 |
| --- | ---: | ---: | --- |
| warm | 599.710 | 599.720 | 已独核预热PASS，排除于测量统计 |
| r1 | 605.877 | 605.887 | 执行及控制收据PASS，组独核待齐；两时延均超对应目标 |
| r2 | — | — | 运行中，不记0 |
| r3 | — | — | NOT_RUN |

可见观察仍为host端首次operation终端结果，不是服务器内部精确READY时间；600s操作完成与包含后置校验的step wall分开。当前不计算median／range，不将r1的业务成功写成S6目标达成。其余W3 FULL、W4约10%及100%压力各组未运行；聚合仍只在最后实际范围确定后按受控入口执行一次。

DC97不缩减现有测量范围／1warm＋3，也不将失败、缺项或无效来源当可靠样本。r1超参考值仍如实保留；其数值未达不作为停止后续样本或拒绝退出的理由。实际测试／资源guard／身份或取证失败仍按既有停止、留证和独审规则处理。

## 11. W3 MO一暖三测资格核收

原E `296a46770e` §103对warm及三测的同源／同配置／原件SHA、真实前序链、业务／资源／镜像／实际释放逐件核收PASS。输入、资源与范围仍同§9；完整原件索引及外层／最终receipt SHA见[协调§37](p6-s3-coordination.md#37-w3-modified_only首组样本资格闭合2026-11-09)。

| 样本 | 可见观察s | 操作完成s | 资格／统计角色 |
| --- | ---: | ---: | --- |
| warm | 599.710 | 599.720 | 原E已核预热，排除于测量统计 |
| r1 | 605.877 | 605.887 | 已核measurement，保留目标未达原值 |
| r2 | 595.743 | 595.752 | 已核measurement |
| r3 | 595.870 | 595.879 | 已核measurement |

这里只列原始字段，不在开发机运行聚合或用目测结果冒充最终受控报告。W3 FULL下一组按固定稿推进；W4约10%及100%压力各模式尚未运行，不能由本组推性能或容量。DC97要求可靠测量而非数值达标；最终median／range、全组分段／资源／计数和实际未知仍由末次专用节点受控聚合及原E核收。

## 12. 已确认的测量收敛范围与FULL预热

Owner已直接确认原E静态CLEAR的[最小清单](p6-s3-e-scope-supplement.md)／`ffa1ee70bb`，取消18个尚未启动项：FULL r2/r3两项，加W4约10%及100%压力各MO/FULL四组各一暖三测16项，不自动顺延。原始矩阵仍列NOT_RUN，不能把范围取消写为通过；本文此前“全部六组／1warm＋3必须补齐”的待项口径由本次具体确认更新。

W3 FULL预热于CT108 00:20:34–01:04:52Z封口，原E `25bf0cdac6` §104核收：node／outer／capture／postflight0、同V4b0／13输入／N1／48−8／M40，实际同一Preview两pair、bundle pair_count2、631可见表／64变更／0失败降级，资源／镜像与最终真实释放合格。原字段可见670.932s／完成670.942s仅为预热观察；worker生命周期物理峰16,851,574,784B，不当作v2独占或两侧同时驻留量。完整SHA及原件见该独审段。

FULL r1已开始、尚无终局。待其自然封口及独核后，执行一次原固定受控聚合：W3 MO的完整组出三测median／range；FULL只有warm和r1则统计UNKNOWN，原始观察单列；W4四组全表输出／容量／性能NOT_RUN／UNKNOWN。`all_groups_complete=false`与聚合过程exit0可以同时存在，不能改表填数或丢慢样本。默认M24原W3基线Submit失败及首次拒绝点未知仍保留；新档结果不证明原档同条件通过。最终H及S3整体E仍待实际绑定和独核。

## 13. 本次已批准范围的受控报告

FULL r1已在原E `e88ece5c98` §106核收单次测量资格PASS；唯一Luna于CT108 01:54:35–01:54:39Z运行一次原已审聚合稿。原node／capture／postflight／outer exit0，固定V4b0 clean／六锁0漂，报告与最终控制收据完成；本节数值只转录节点报告，未在开发机运行统计。原件根、完整report／receipt／outer SHA见[协调§39](p6-s3-coordination.md#39-full-r1及一次现有证据聚合)，report SHA=`c37e3db3a699f891affee58f129d457e86c9105c9f5382c8d0b394448c70997e`。原E正在核收该报告，不以执行者通知代独审。

| 负载／模式 | 实际样本 | 可见观察秒 | 操作完成秒 | 统计限制 |
| --- | --- | --- | --- | --- |
| W3 MO | 1warm＋3measurement | median595.870；range595.743–605.877 | median595.879；range595.752–605.887 | 预热599.710／599.720不入统计 |
| W3 FULL | warm＋r1 | warm670.932；r1 669.540 | warm670.942；r1 669.550 | INCOMPLETE；三样本统计UNKNOWN；r2/r3取消 |
| W4约10% MO／FULL | 0 | UNKNOWN | UNKNOWN | 全组取消，原始NOT_RUN；全表输出与容量同样未测 |
| W4 100%压力MO／FULL | 0 | UNKNOWN | UNKNOWN | 全组取消，原始NOT_RUN；无成功压力结论 |

报告`all_groups_complete=false`、`s6_verdict=NOT_ASSESSED`保留；退出按已确认最小范围，不冒原计划六组完成。可见计时为2秒poll的operation terminal observation，不是服务器内部精确READY。W3输入为2×t4派生负载、资源N1/48−8/M40，不是原M24容量证明；数值超过参考目标不构成退出门槛。

报告还保留六次原样本逐pair的实测分段、native计数及预约高水，不生成跨组加总。以下只列MO r1与FULL r1中initial_to_modified的**原字段**，展示已测职责及包含关系，不是各段median：

| 字段 | MO r1秒 | FULL r1第二pair秒 | 包含关系 |
| --- | --- | --- | --- |
| comparison total | 309.9643607160542 | 309.98104098206386 | 含read/build与随后facts/records JCS |
| native records build | 252.80942216799997 | 252.17699095599997 | read/build内部，含native排序及内部产物JCS |
| 随后records JCS | 41.52512506581843 | 41.61196280200966 | 完整payload由Rust生成；Python只小metadata，不是逐行Python编码 |
| records publication | 3.062593827024102 | 3.0712150188628584 | 内含Parquet写1.1709966640919447／1.1596696821507066 |
| Risk total | 113.35153992590494 | 110.59572038683109 | 必要Arrow转换6.523780236253515／6.432785206940025属于rules内部 |
| surface／table export | 13.457606365904212 | 21.831863838015124 | pair范围；bundle assembly另属整operation |
| bundle assembly | 109.3270913651213 | 107.38398779486306 | 各operation一次，FULL不是第二pair专有耗时 |

Risk publication内部还含标注JSON生成／验证，不能全称纯I/O；嵌套子段不能重复加总到READY。FULL第一pair也实际执行，两个pair的native calls分别144／182、input reads144／232；MO r1为182／232，cache_hits均0，0命中合法，不据此声称去重提速。两侧同时驻留量未单列；M40预约高水含预留，不当作最小所需RAM；worker物理峰是生命周期峰，不当作v2独占。CPU累计的现有step窗口与清理后即时值限制沿§9，不补未知为0。W2无行比较，不计S3比较收益。
