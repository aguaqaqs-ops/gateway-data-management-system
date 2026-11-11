# P7 S2b 详细执行计划

日期：2026-11-11。状态：**待 GPT-6-Astra 独立审核；尚未具备已审代码实施条件。** 基线 `p7-s2a-exit=f720ef571df72682d56732876f03c79f076eca45`；配套[设计](p7-s2b-design.md)为行为和算法依据。Owner授权本轮形成文档并独审/修复至可实施，不含产品实现、测试运行、push或部署。审核报告、修订和交接放 `/home/dev/gdds-stage-exchange/p7-s2b/`，不把过程文档入库。

## 1. 范围、依赖和执行规则

S2a已退出。本阶段只增加同机静态独立组、统一业务入口、在线新增设备、部署隔离和整机预算；组程序/资源/root变更仅组级维护。新增设备全过程不能重启/暂停旧设备、worker或其他组。已有设备转组/删除/禁用/重绑不走新增，S3调度及S4b复制/转交不提前实现。

未来获得产品实施授权后按A→B→C→D→E→F推进，可在B完成后将无依赖的D配置工作并行准备，但同一文件/主线合入由协调者串行处理。各包不跑全量门禁；必要focused和容器接线后，F对最终候选集中验收。A/B风险包独审使用新上下文、不同模型家族，原finding由原审复审；阶段末完整独审。可沿用S2a协调Terra/high、实施Sol6.1/high、独审Astra/xhigh的角色方案，但需在未来实施授权入口明确，不把本轮文档授权扩大成产品执行。

全部测试、lint、编译、容器在专用节点clean已提交worktree执行。自动门禁固定04及既有工具；focused/真实节点按有效规则与现场占用选取，优先06/05，不回退CT201测试。历史文档有06 96GiB和当前main五节点64GiB两种记录，预算以执行现场核实为准；本计划先按64GiB保守设计，不修改硬件、生产默认或其他人的资源。新阶段不继承S2a具体真实输入与测试profile授权。

## 2. 已核源码接点与变更责任

下表路径相对仓库根；`BE`=`vnext/backend/src/gateway_backend`、`RS`=`vnext/repository_service/src/gateway_repository_service`、`RC`=`vnext/repository_client/src/gateway_repository_client`、`Contracts`=`vnext/repository_contracts/src/gateway_repository_contracts`。

| 接点 | 具体改动与禁止事项 | 包 |
| --- | --- | --- |
| `BE/infrastructure/control_db/sqlite_mapping.py`、`sqlite_provisioned_scope.py`、`baseline_head_sql.py` | 提取insert-or-exact-replay事务；复用固定scope/INITIAL核验；启动不覆盖repo/enabled/推进Head；允许空seed | B |
| `BE/bootstrap/composition.py`、`operation_worker.py` | 注入目录/在线注册依赖、RS身份检查；worker读取DB新行，不能新增设备缓存 | B/D |
| `BE/http/auth.py`、`dependencies.py`、`wiring.py`、`routes/maintenance.py` | 普通API统一route-key核验；注册同AdmissionGate；现有内部鉴权；热session挂载与快照 | B/C |
| `BE/http/routes/device_registration.py`、`http/schemas/device_registration.py`（新） | 内部注册/query、普通device-context DTO及有界错误；管理API不公开 | B/C |
| `BE/application/provisioning/`（新窄模块） | 组身份/目录预留检查、同key RS create、事务前后重读；不新建job/恢复状态表 | B |
| `RS/http/routes/repositories.py`、`create_repository/command.py`、`mutation_store.py` | 复用原create，不改原幂等/UNKNOWN、不创建通用查询服务 | B（只依赖） |
| `RS/http/routes/deployment_identity.py`（新）、`runtime_preflight.py`、`RC/client.py`、Contracts DTO | 增加认证组身份读方法；与ready分别判断，不令RS认识设备scope | A/D |
| `vnext/scripts/render-runtime-config.py`、`host_runtime_config.py`、`worker_deployment.py` | 单组渲染复用；完整组清单汇总、跨组路径/端口/镜像/预算核验 | D |
| `vnext/scripts/manage-worker-group.py` | 显式组管理锁、身份核验；入口独立project，原expected服务集合不吞入口 | B/D |
| `vnext/scripts/processing_group_config.py`、`manage-processing-groups.py`（新） | 文件schema/追加校验、发布锁、reserve/register/session/route发布及status；无常驻服务 | A/C |
| `vnext/deploy/compose.yaml`、`compose.dev.yaml`、新`compose.entry.yaml`/Nginx模板 | 参数化backend loopback端口；明确组镜像；动态session/目录父目录ro挂载；入口host网络/独立project | C/D |
| `vnext/backend/tests`、RS/RC/Contracts tests、`vnext/backend/tests/support/compose_gate_harness.py` | 注册/身份/代理接线，复用已有Compose启动与业务旅程，扩展多project清理 | B–F |
| `frontend/src/features/api/{authenticated-fetch,client,session}.ts`、session/handoff调用方 | 一次身份快照携带route-key；统一JSON/上传/流式/轮询；不按页面复制实现 | E |
| frontend请求层tests、mock handlers、`frontend/e2e-real/`与调用fixtures | 更新新必需header与device-context；保持现有401/404/幂等行为 | E/F |
| `vnext/backend/benchmarks/real_dump_journey.py`及受控新增组旅程driver | 支持选择group/设备与统一入口，不伪造源设备身份、不直接改seed后重启代替热新增 | F |

A先用rg复核实际HTTP入口、harness路径和OpenAPI生成入口；表中标“新”者尚不存在，不冒称已实现。main前进仅核实际增量和影响，不能重写已审来源。

## 3. 配置、协议与算法实现清单

### A. 配置schema和Contract（风险B）

1. 按设计§3实现纯parser/renderer模型：directory≤8MiB/10000 devices、groups≤1MiB/32 groups；严格字段、重复key、bool/int、原始UTF8设备ID≤255bytes，禁path/URL注入。目录device唯一性含false预留；生成key为UTF8 SHA256小写hex，固定向量。
2. 配置清单固定 `host.memory_bytes/cpu_count/shared_memory_reserve_bytes/shared_cpu_reserve`、`entry`和`groups[]`；entry包含监听/管理端口、镜像、memory/cpu预算；group包含group_id、project、backend loopback port、storage/resource路径、session目录、RS/internal token文件与明确镜像组合。全字段由typed model序列化，不接受任意Compose/shell片段。
3. 不把全局directory digest写进每组部署锁存身份；后台任务只依赖本组固定部署与DB事实。新增设备不触发 `compare_configuration` mismatch。必要字段加入现有版本的基线模型，不引入旧/新配置兼容双读。
4. Contract同步表见§6。确定route-key、registration/device-context/RS身份DTO及错误的OpenAPI；新增body≤8KiB、未知字段拒绝，GET query同有界身份。不为生成协议先实现业务。
5. 写配置/向量/错误表及schema focused（无Dolt）；独审核输入边界和权威归属。交付包括对当前组统计语义的决定：仍是当前设备所属组、需statistics_read_group；运维可用各组受控session访问，无新增全局统计授权模型。

### B. 组内在线注册与维护（风险A）

1. 新内部register与query路由通过internal bearer，body环境/组必须等于本进程；目录必须已有device→本组预留。目录只在受理管理请求时读取，坏目录不使所有已运行组退出。
2. acquire_new_work覆盖完整注册；先短read UoW，已有exact active scope返回固定INITIAL，冲突含disabled拒绝；缺项在事务外RS create，deterministic key按设计§5，返回后短write UoW fresh-read并原子插入mapping/INITIAL/Head。
3. UUID5 namespace固定为`uuid.NAMESPACE_URL`，name为UTF8 JCS字符串数组`["gateway-device-initial-v1",environment_id,group_id,device_external_key]`；共享向量记录完整输出。RS key使用同设计中的独立domain，不复用业务digest。
4. 整个register每次最多一个existing client调用（client本身有界原key重试）；不在HTTP层外套无限重试。RS PENDING/409不能冒称未创建，不换key；既有RS启动恢复责任保留。DB不完整时不能凭可变main补INITIAL。DB失败后保留RS结果供同key重做，不删除正式repo。
5. 启动seed的批量固定归属校验仍执行；只允许缺项初始化与exact已有mapping，删除upsert覆盖；空mappings合法。组生产启动seed与directory核归属，旧本地fixture同步新前提；不把seed作为动态DB的全量清单，也不清未出现在seed中的在线记录。
6. 管理锁位于宿主配置目录，group ID经白名单编码后构造固定文件名；顺序统一先全局发布锁、后目标组锁，维护只取目标组锁，不反向取得全局锁。drain在后台HTTP仍依赖原gate，无RPC租约。既有停止/恢复不用全机容器扫描结果随意停别组。
7. focused最低：首次/同请求重放、project/禁用/固定归属冲突、并发同device同/异scope、RS响应丢失key不变、DB提交前故障后重放、Head推进后不回退、空seed与重启不覆盖在线映射、drain先关/注册先受理两种顺序。真实RS create自身crash矩阵复用原owner，新增测试不重复内部每个syscall。

### C. 统一入口与热发布（风险B，配置唯一性/不误路由按A边界审核）

1. 新入口独立Compose project，仅Nginx固定镜像；公共监听只开放`/v1/`及无敏感入口health；管理loopback port返回已加载config摘要/指定key选定组，非公共路由。日志不输出session/凭据/device配置全文。
2. 生成严格key map及固定upstream，body预算≥backend合法上限，显式关闭request/response缓存与upstream retry；连接/idle预算按设计。流式不在代理落完整上传/下载临时文件，backend原bounded输入控制保留。无外部请求拼接上游地址。
3. 所有普通BE API经require_identity核route-key和本地scope；基础授权/对象权限保持。普通device-context只读DB、返回 `{environment_id,group_id,gateway_device_external_key,business_project_id,repository_id}`；必须已就绪可受理才在新增final probe判成功，普通读状态不以gate关闭推断业务对象消失。
4. CLI `validate`/`render-entry`/`add-device`/`status-device`/`check-groups`：宿主受控路径、无shell、固定子进程timeout；前置检查失败exit2、锁忙exit3、后置未完成exit1、实际可用exit0，JSON输出不能含token。`status-device`不重放任何写入。
5. add-device持锁按reserve(false)→register→原子追加session→scope probe→directory(true)→candidate nginx-t→publish/HUP→actual probe执行。session文档输入只含目标device/project授权项，包含至少一个可用device read权限probe身份；同token不同内容冲突，不覆盖既有撤销/到期项。
6. 将已验证配置以独立版本文件保存，原子切换Nginx固定入口文件；保留上一有效版本。HUP未确认时旧运行配置继续，控制器不报成功、不清旧文件；若已确认reload失败，恢复磁盘指向上一有效版本。进程在切换/确认间退出后，重试读取实际probe与文件核定，`nginx -t`不通过不得重启有效入口。最多一旧代未退出时拒绝继续reload，不强杀长流。
7. focused：目录预留防重复分配、配置错误保留旧文件、false/true与actual不混淆、exact重放/部分失败恢复、同/异组锁、missing/duplicate/Unicode/大小写header、身份与错组拒绝。最小容器接线合并验证Nginx真实header行为、host原子替换容器可见、长upload/download跨HUP、新连接路由生效、旧设备业务继续。

### D. 完整组隔离与整机预算（风险B）

1. backend宿主端口参数化为loopback；RS仅组网络。每组显式独立project/mount/session/token，入口独立，禁止共享默认named volumes/可变镜像tag。实际`docker compose config`及inspect核服务继承、worker编号/镜像、端口/卷/CPU/内存。
2. 新认证RS `GET /internal/v1/deployment-identity` → `{environment_id,group_id,storage_digest}`，读取现有preflight事实、不扫描root。Contracts DTO、client窄方法、RS路由、BE/worker startup核验同时交付。新组接口暂不可用/返回其他组不得ready；注册前也核。错误端点不凭readyz放行。
3. 复用host_runtime_config已有filesystem/root校验，再按实际host filesystem合并跨组路径与容量。拒绝overlap/nesting、不同组secret复用、port/project重复、资源总和越界；不让多组各自将整个host剩余容量当独享。调用检查禁止写用户业务root，初始化只创建明确新目录。
4. manage-worker-group核目标组身份与实际project，drain/stop-group保持S2a真实进程退出及UNKNOWN规则。新组启动/单组版本切换不重新创建其他组或入口；组版本组合写入清单，真实跨版本兼容不在本轮验收。
5. focused +必要Compose：错误RS凭据/端点/组返回拒绝、相同物理盘不重复承诺、ports/mount冲突、A维护B继续、empty新组启动并热加首设备。不能只看renderer JSON，必须inspect实际运行容器。

### E. 消费者与文档接线（API边界风险B；纯文案C）

1. 修改任何`frontend/`文件前通知前端设计会话目的/范围，按AGENTS由其纳入当前或下一阶段审核/调试；通知与来源放阶段区。此处是实施协作前置，不要求本轮提前改前端/发送外部消息。
2. 公共fetch从一次捕获的session提供Bearer+device-key；原调用构造器同步参数，所有API/mocks/测试client统一新header。并发切换session不产生混合token/key；旧设备operation的轮询按原scope终止或保持，不能静默切组。
3. OpenAPI/generated类型、dev bootstrap、后端Compose客户端、benchmark及外部接入说明同步，不保留无header的隐式默认组。公开错误体沿原ApiError；流式失败不转成空成功body。
4. 前端focused覆盖JSON/上传/bundle/轮询/分页、missing device、切会话、401失效处理；真实backend最小e2e至少两个组上下文和热新增后入口访问，不另建前端全局设备管理UI。
5. 文档更新部署/runbook：新增、查询未完成、维护单组、错误配置保留旧路由、禁止手改既有归属、配置与session父目录挂载、版本组合和预算。risk/Contract audit与前端实际改动均进入F完整核收。

### F. 最终独审、门禁与真实旅程（风险A核收）

1. 固定最终产品候选clean提交，对`p7-s2a-exit..V`全范围独审，包含A–E所有边界和前端协作结果。finding修复→原审复审→必要增量验证，不以设计GO代替代码独审。
2. 受影响backend、repository_service、repository_client、repository_contracts及实际依赖闭包由自动门禁选择/查表；默认选择六包使来源清楚，不要求每个工作包六包。S5/发布fresh六包规则仍有效。
3. 新Nginx镜像是backend Compose输入，必须纳入`test_input_closure.py`与gate容器清单/配置允许项，记录所选tag、同节点image ID及跨节点config/DiffID；不能因入口在新Compose文件而漏入闭包。修改这些工具属于B风险，独审并在专用节点做窄工具验证，不重复开发完整gate系统。
4. 最终candidate构建必要镜像并运行集中双组/热新增Compose；同一runner已跑的旅程不另重跑。前端仍使用独立权威入口和真实backend e2e入口，不能用后端包通过代替前端。
5. 真实旅程按§7清单获确认后运行一次，不以合成或S2a旧数据冒称新的真实设备。结果来源固定SHA、输入hash、组/设备、worker资源，旧失败保留；修复触及旅程逻辑按实际范围复验。
6. 满足退出条件后提交一页总结；总结HEAD由gate闭包绑定，必要包重跑；独审核来源和限制，再由获实施授权的协调者创建本地附注`p7-s2b-exit`。本轮文档不创建该tag。正常收尾仅释放本人占用与无消费者资源。

## 4. 最小测试owner与失败证据

| 不变量 | 现有owner/新增测试位置 | 不重复项 |
| --- | --- | --- |
| 固定scope、INITIAL、Head不回退 | `test_provisioned_scope_seed.py` + 新`test_device_registration.py` | 不复制Archive/Submit全矩阵 |
| RS create幂等/恢复 | RS create/mutation tests；backend adapter窄测试 | 不新增第二create ledger测试体系 |
| 热新增与drain | `test_worker_group_maintenance.py` + register服务测试 | 不穷举所有线程调度 |
| route-key/鉴权/对象边界 | backend HTTP auth/route tests参数表 | 不为每个同构404复制测试函数 |
| 双组实际隔离及热发布 | 新`test_processing_groups_compose_e2e.py`；扩展既有harness | 集中一个场景矩阵，不每包重建完整镜像 |
| consumer请求一致性 | authenticated-fetch/client tests、最小真实e2e | 无全局管理UI/重复后端业务证明 |
| 闭包包含入口镜像 | `test_input_closure.py`既有脚本tests | 不改runner按包通过含义 |

热新增Compose具体顺序：A/a1和B/b1完成初始化→以既有harness可观察屏障保持A一个操作在途、B持续发有效请求→add A/a2（可用合成身份作为边界）→核原容器代际/任务未重启、a2经统一入口完整业务→释放原任务并核结果→A维护时B继续→A恢复。另以合法流式请求跨HUP证明不中断；不用长sleep推断在途。屏障仅测试夹具，不引入production探针/故障注入API。真实旅程不靠这些合成ID冒称不同真实设备。

权威失败停止当前及依赖验收，保留exit/log/SHA。构建/环境错误按当前快速修复规则，有依据修正后重跑失败步骤，不将产品问题归类成环境。所有实际测试在节点且在clean提交运行；本轮只读源码/文档核验不构成产品测试。

## 5. 资源档与缓存准备

生产默认N1、单worker E32/reserve8/M24不变。以下是**待执行前确认的小输入测试建议**，不是已获具体资源授权或已测容量：

| 档位 | 每worker | BE/RS每组 | 入口/整机共享余量 | 内存总预算 |
| --- | --- | --- | --- | --- |
| 两组各W1 | E12/reserve8/M4 GiB、CPU2、swap0、N1 | BE2GiB/CPU1；RS4GiB/CPU2 | entry0.5GiB/CPU1；shared8GiB/CPU2 | 44.5GiB，CPU13 |
| A W2、B W1 | 同上，共3worker | 同上 | 同上 | 56.5GiB，CPU15 |

仅小输入功能；每组worker同规格且W=K。现行S2a W2/E16不能直接沿用到三worker加两套服务：48+12+8+0.5=68.5GiB，超64GiB；禁止删reserve或临时超配凑通过。若真实输入M4不足，停止该档并调整有依据方案交Owner，不把OOM视正常、不提高期限逃避功能要求。该确认只影响运行，不阻塞协议/代码编写与独审。

入口镜像在CT201取得固定版本、记录来源/平台/digest，docker save到获准LAN、目标load并比config digest/全部DiffID；测试CT不联网拉取。backend依赖输入未变时复用原dependency-base；若修改依赖按现行脚本预构建并记录。Nginx身份、构建/传输时间、缓存endpoint类别（无凭据）、npm cache按锁来源写阶段区。未命中停止补齐，不在CT201测试。

## 6. Contract与交付文档

| owning文档 | 实施要落的规则 |
| --- | --- |
| 新窄`formal/contracts/processing-groups-and-routing.md`及taxonomy | 单环境唯一设备组、目录预留/开放、route-key、热新增顺序/失败语义、组级维护、部署与整机资源；由部署/接入边界owner负责 |
| `business-lifecycle-and-state.md` | 引用组归属边界；在线登记与INITIAL同事务、固定scope不变、新增不重绑；启动seed收窄 |
| `operation-lifecycle-and-integrity.md` | 注册受理与drain共用gate，业务队列/claim/recovery保持S2a；无新job类型 |
| `repository-service.md`及RC/Contracts/OpenAPI | 认证部署身份只读接口；原create及其409/UNKNOWN边界不变 |
| `canonical-storage-and-repository-boundary.md` | 组间独立可写root、已有保护/发布/cleanup语义不变 |
| `statistics-and-query.md` | group/environment观测归属、只读单组查询及现有权限；无聚合承诺 |
| `vnext/deploy/README.md`、backend API文档、前端接入说明 | 启动空组、在线新增/查询/失败重试、单组维护、HTTP header和消费者接线 |

正式Contract在产品实施A中按实际协议修订，标明目标/生效状态，不在本轮文档中假称已实现。运行报告和提示词不入库；设计/计划/S0决议保留正式来源。

## 7. 真实输入、验收边界与执行前条件

Owner已同意“小输入、两个设备、两组功能验证，不做容量/性能矩阵”及新增设备无停机。实际可用第二真实设备及其身份/输入尚未核实；S2a已有来源仅`rd-t1-a-v1`（107115 bytes，SHA256 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`）和原`compose-device/compose-project`scope，来源见阶段区S2a真实handoff。不得改名复制为第二真实设备、改XML身份或借合成多组测试宣称真实两设备通过。

实施准备阶段先只读盘点获准真实输入与原始身份来源，形成一次DC33清单：每设备external key/project来源、输入路径/模式/字节/SHA、预期业务链/异常处置、组、节点、profile、是否新增设备、不得改变的源事实。基本旅程按有效输入执行Upload→Preview→Submit→Review/Archive或真实无变化/异常分支；保持源异常，不造审批成功。新增设备并发屏障在合成Compose强制验证；真实旅程按实际输入支持的重叠运行保存观测，不伪造时序。

若只存在一个合格真实设备，不悄悄降低已定范围：继续不依赖它的实现/边界验证，退出前将“一个真实链+合成多组边界”替代建议及来源缺口交Owner明确决定。具体profile/节点/输入清单执行前集中确认，不能把本轮设计授权当真实运行许可。这不是未定核心算法，代码实施准备可完成；但未确认/未取得真实来源不能宣称阶段exit-ready。

其他运行前条件：获得产品实施授权；前端修改前通知前端设计；目标节点有效占用和离线缓存就绪；新镜像平台身份固定并进入闭包；测试资源档确认。它们与“详细设计具备编码条件”分别记录。默认N1，N>1开放前D24同输入N2/N1结果/digest与t4 D23参考仍最迟S5，本阶段不代替。

## 8. 本轮设计审核收口

正式审核固定本地提交，在clean detached worktree只读核源码、设计/计划及S0和总入口一致性。GPT-6-Astra审核范围包括：业务需求完整、最小机制、scope/INITIAL幂等、热新增不中断、代理语义/错误/流式、凭据/端点/roots边界、维护竞争、预算、测试owner/闭包、消费者接线和真实来源限制。

本轮不运行产品测试；文档检查采用路径/引用、diff和算法追踪，不将其称为测试通过。报告写阶段区并绑定完整SHA及文档摘要。若有阻塞finding，由设计者修订并提交，原审对增量及关联全文复审；直到明确GO、未关闭阻塞0。之后只更新状态/审核入口并让原审核最终差异，保留最终受审内容摘要。最终答复清楚区分设计GO、执行前条件及尚未进行的产品实施/验证。
