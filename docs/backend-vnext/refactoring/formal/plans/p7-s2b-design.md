# P7 S2b 静态独立处理组与设备热新增设计

日期：2026-11-11。状态：**业务边界已获 Owner 确认；详细设计待独立审核，产品未实施。** 源码基线 `p7-s2a-exit` / `f720ef571df72682d56732876f03c79f076eca45`。配套[详细执行计划](p7-s2b-execution-plan.md)给出接点、工作包和验证责任。本轮只授权文档及 GPT-6-Astra 独审、修复至具备代码实施条件，不含产品实现、push、部署或阶段 exit。

依据：[S0 §15](p7-s0-owner-decisions.md#15-s2b-业务收口与设计审核授权2026-11-11)、[S2 共用设计](p7-s2-design.md)、[分组与副本设计](p7-processing-groups-and-test-extraction-design.md)、[比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)。本稿明确替代早期“全部归属配置只能维护窗口更新”“S2b 不在线注册”的限制；原 S2a 退出与既有业务 Contract 不改写为本稿已实现。

## 1. 目标和边界

同机至少两个完整组，各有 backend、固定 worker 池、RS、独立 control/telemetry/RS DB、Dolt、所有可写 roots 和内部凭据。组内沿 S2a W=K、单 executor、固定实例恢复；组间不共享业务可写状态。一个设备在同一 environment 只有一个正式写入组，现有 exact device/project scope 和 repository 固定归属不变。

统一用户入口，用户不选组；新增设备在线注册并开放路由，已有设备和在途任务不暂停、不重启。组程序/资源/root 变化可以只维护该组。新增组部署就绪后在线加入入口。已有设备换组、删除/禁用、scope/repository 重绑不通过新增接口实现；生产转交留 S4b。没有自动分流、跨组均衡、任意版本混搭/降级、全局对象索引/队列/业务数据库或全局统计聚合。两组同版本验证不宣称跨版本灰度已可用。

公共入口是标准 Nginx 代理，无应用业务数据库、用户会话数据库或自定义代理实现；组业务授权由 backend 负责。同机受控运维属于既有信任域，部署脚本不是抵抗恶意同 UID 管理员的安全边界。公共入口/宿主/物理盘故障可能影响多组，不承诺高可用或硬件故障隔离。

## 2. 当前源码和最小增量

| 当前事实 | S2b 处理 |
| --- | --- |
| `http/auth.py` SessionPort 已解析设备、project 和权限；LiveFileSessionPort 每请求读文件 | 保留鉴权；增加设备路由校验。凭据文件热发布改父目录只读挂载，不能依靠单文件 bind/secret 看到替换后的 inode |
| `sqlite_mapping.py` 只在 composition/operation_worker 启动 seed；scope resolver 每次查 control DB | 增加 backend 内部在线注册；worker直接读新 DB 行，无广播或配置重载 |
| `_apply_seed_record` 会 upsert repository/enabled | 在线新增使用 insert-or-exact-replay，禁止拿原 upsert 作注册；启动 seed 同步收窄为补齐缺项/精确核对，不覆盖在线事实 |
| RS CreateRepository 已有原 key 幂等与初始空 commit，client 已支持 | 复用，不增加 create operation 或第二 effect ledger |
| ClosableAdmissionGate 已记录 in_flight，maintenance/drain 关闭新受理 | 注册在同一个 gate 内持有整个受理区间，RS 调用在 SQLite 事务外 |
| environment/group/root 标记和 BE-worker 配置比对已有；RS preflight 有组身份 | 复用并核 BE→RS 组身份；补部署总清单和整机聚合校验 |
| Compose backend 固定8000，renderer按单组生成，管理命令已按project筛选 | 参数化端口/镜像/配置路径，补多组部署清单；不得通过宿主全局名称停其他组 |
| 前端 authenticated-fetch 为上传/轮询/bundle共用入口 | 在此统一增加路由键，所有调用方保持同一设备上下文；前端改动遵循通知/审核规则 |

路径均相对 `vnext/backend/src/gateway_backend/`（另注明者除外）；详细文件表见执行计划。

## 3. 配置与权威

### 3.1 单机目录

新增宿主受控 `device-directory.json`：`schema_version=1`、`environment_id`、`devices[]`。每项仅 `gateway_device_external_key`、`group_id`、`enabled`。设备字符串按原始 UTF-8 exact 比较，不 trim/大小写折叠/Unicode归一化；1..255 bytes。最多10000项、8MiB；重复JSON键、未知字段、重复设备、未知组拒绝。`enabled=false`表示归属已预留但未要求入口开放；`true`表示组准备完成、期望开放。它不是当前 Nginx 已加载的证明。唯一性同时包括false项，失败预留不自动释放给别组。

目录只保存归属和必要有效状态；project/repository/INITIAL/Head、任务和授权不放入。组内业务 DB 保存固定scope和历史事实。目录丢失/损坏时禁止新增和配置发布，已有服务继续使用已加载路由与组内有效映射；不猜组、不依据遍历各组DB重建唯一权威。新部署入口无有效配置时拒启。受控重建须明确停止相关服务及核数据，不能由新增命令自动完成。

新增 `groups.json` 为宿主部署清单：schema/environment、整机CPU/内存和一次共享reserve、入口端口/资源/固定镜像、每组 `group_id`、Compose project、backend管理端点、storage/resource文件路径、session目录、内部/RS token文件路径、backend/worker/RS明确镜像引用和程序revision。路径绝对、服务端所有；文件不含secret值。组数1..32，文件1MiB；端点只允许本机/明确部署内网地址，无userinfo/fragment/任意caller URL，HTTP客户端禁止重定向。环境由入口部署确定，客户端不能通过header切环境。

目录与session采用父目录只读bind、普通文件同目录temporary+fsync+replace+父目录fsync发布。不给容器Docker socket或宿主写权限。每组仅挂本组session目录；公共目录只读挂到backend管理边界，普通业务/worker不在每次请求依赖目录读取。凭据轮换/撤销仍按原session语义，不因路由快照冻结授权。

### 3.2 串行配置操作

一台宿主仅一个配置发布命令，使用配置目录内普通flock。锁只串行化短控制面变更，不停业务，不占worker执行许可。每组管理锁覆盖 add-device 与 drain/stop-group 等运维命令的完整区间；不同组维护可独立，原有测试节点占用规则另行适用。进程退出释放锁，文件存在不是占用证据；不建分布式锁或恢复daemon。

新增路径只接受目录追加新设备、false→true或exact重放，既有true项不能删除/改组/改成false，scope冲突交人工处理；组改名/环境变化也不属于热新增。发布前逐项比较既有有效条目，任何不符拒绝整个候选。旧文件与当前服务保留，不通过全局generation变化令其他组拒启/停止任务。

## 4. 统一入口与外部协议

### 4.1 路由键

所有普通 `/v1/` 请求新增单值header `X-Gateway-Device-Key`：`hex_lower(SHA256(UTF8(gateway_device_external_key)))`，固定64个小写十六进制字符；不加前缀、不包含project。采用这个ASCII路由表示避免把任意Unicode设备标识放入HTTP header以及Nginx map字符串的不区分大小写匹配。它不是凭据或业务digest；原设备ID仍是业务权威。renderer发现不同设备产生相同路由键时拒绝，不合并。提供Python/TS共享向量（ASCII大小写、中文、组合字符），不改变已有业务ID/Contract digest。

客户端公共请求层从当前会话取得设备，和Bearer作为一次请求的同一身份快照；切换会话时不允许old token/new device组合。覆盖GET、POST、multipart、分页、轮询、bundle下载和外部脚本；不解析请求body找路由，不为operation/submission ID建立全局索引。单组调用同样使用该header，同步改调用方，无兼容双路径。每个页面持有操作的原设备上下文，不能因当前设备切换继续以新设备请求旧operation。

backend先解析现有Bearer，再验证header严格单值/格式及是否等于认证设备计算值，再用本地映射核设备active及scope/INITIAL一致；现有各对象权限检查继续执行。即使直接访问组backend或入口错误转发也不可越组写。group统计继续要求statistics_read_group，不自动提供跨组数据。未认证401；格式错误422 `REQUEST_VALIDATION_FAILED`；设备/对象/本组归属不匹配统一404 `RESOURCE_NOT_FOUND`，不泄漏正确组；内部管理的配置冲突另用409。预检/health与内部管理不使用普通设备header。

### 4.2 标准代理

采用固定版本官方 `nginx:1.28.0` 作为首个实现基线，实施缓存准备时固定实际平台manifest/config digest及全部DiffID；无浮动latest，升级另显式修订。标准map仅从已校验hex key选择由配置生成的固定upstream，每组只有一个backend；未知key拒绝404，无default组、通配设备匹配或由caller拼proxy_pass URL。先大小写敏感正则校验64位小写hex，重复header合并值（逗号等）不能通过；容器测试验证所选版本实际行为，backend仍独立拒绝重复值。

公开server仅代理普通`/v1/`，拒绝`/internal/`；不把RS或运维接口公布。组backend端口绑定loopback作为宿主管理/入口upstream，RS仅组内网络。入口容器用host网络访问固定loopback upstream（单机Linux）；绑定的公开地址/端口由部署清单指定，管理探针单独loopback监听。组Compose网络独立，入口不挂任何业务root或凭据。

显式 `proxy_http_version 1.1`、`proxy_request_buffering off`、`proxy_buffering off`、`proxy_cache off`、`proxy_next_upstream off`；保留原method、path/query、Bearer、幂等键及必要流式响应headers，不替换backend业务错误，不跟随上游redirect，不自动重试/跨组fallback。Host/forwarded headers由入口规范化，不信任caller提供的组/环境/内部身份header。

入口body上限与当前上传预算一致或更宽（backend负责每类精确上限），不能沿Nginx默认1MiB截断产品合法上传；连接5秒、read/send idle600秒作为有界初值，不把idle timeout当操作总期限。旧业务deadline/取消/UNKNOWN不变。正式设置须核最大合法请求/长流；日志禁止Bearer及body。连接数/入口内存/CPU预算显式配置，入口资源计入整机。

Nginx HUP平滑加载保留旧请求，不设置会为配置刷新强制中断在途流的shutdown timeout。控制器最多等待30秒确认新配置；超时仅报告配置状态未确认，禁止杀旧worker。前一代仍有长流时不连续累计更多reload，新的配置操作返回busy，现有业务继续；下一次操作在原代自然退出后重试。

依据：[Nginx map](https://nginx.org/en/docs/http/ngx_http_map_module.html)、[proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)、[HUP控制](https://nginx.org/en/docs/control.html)。这是方案依据，不是本项目实测通过。

## 5. 在线注册、幂等与发布算法

### 5.1 组内API

新增内部 `POST /internal/v1/devices/register`，仅本组internal bearer；body严格为 `environment_id, group_id, gateway_device_external_key, business_project_id`，各身份使用现有有界类型。返回200（首次及exact重放一致）含这四项、repository_id、initial_node_id、initial_commit_id。不接受caller指定repo/commit、enabled或任意路径。新增 `GET /internal/v1/devices/registration?device=...` 查询现有DB映射和INITIAL（未登记404），返回identity便于响应丢失后核对；不查可变Head来猜INITIAL。

POST持有 `acquire_new_work` 直到RS结果和DB事务结束；maintenance已关门返回503，drain可见当前注册in_flight。受理前核固定environment/group、受控目录设备预留确属本组及RS身份；目录坏只拒本次注册，不把整组readiness锁死。普通业务不依赖全局目录的每次读取。

算法：

1. 在短read UoW查该device全部mapping（含disabled）及固定INITIAL。已有exact active scope且身份完整则返回原结果；不同project、disabled、损坏或相互矛盾均409，不重新启用/重绑。已映射时不再向RS创建第二库。
2. 缺失时使用确定性RS create key：`p7-device-create-v1:` + SHA256(JCS `[environment_id,group_id,device_external_key]`)。同设备的冲突project也共用此key，避免竞争时生成两个库；scope冲突由下一事务唯一规则拒绝。key不含随机attempt、时间或调用者。
3. 事务外调用既有 `RepositoryServiceClient.create_repository`。响应丢失按相同key重放，沿RS原失败/UNKNOWN语义；409未能确定原结果时停止本次，查询/原RS恢复，不换key绕过、不新增自动RS重启。组不能接管/删除无法判定的库。
4. 短write UoW fresh-read映射及INITIAL，再次执行完整固定scope校验。若并发已有exact结果，必须与RS返回repo/initial一致；冲突原子拒绝。首次插入既有 `provisioned_scope_mappings`、`baseline_node_records(INITIAL)`、`baseline_head_records(version=0)`，一个事务。INITIAL node ID采用UUID5的`uuid.NAMESPACE_URL`与JCS `["gateway-device-initial-v1",environment,group,device]`字符串（加固定向量）；commit只取RS create返回的空commit，不能取当前main。已推进Head不得覆盖。
5. 不新增control DB注册状态表/任务类型。RS create成功而DB未提交是可恢复的暂存结果：下一次同key取得原库继续；不做补偿删除。已有DB成功而响应丢失直接exact重放。worker的scope resolver自然看到新行，不能遍历重启全部worker。

启动seed保留bootstrap用途，但改为只插缺失、对已有精确核对且不覆盖repo/enabled/INITIAL/Head；生产seed只能包含该组已预留设备。在线注册数据不要求回写seed文件；新节点可空seed启动并在线注册。移除“必须至少一个mapping”的启动限制。原允许mapping更新的Contract能力并未通过此入口实现，专门维护路径未来另定；删除被替代的启动upsert行为及其错误预期测试。

### 5.2 宿主新增命令

新增 `manage-processing-groups.py add-device --group <g> --device <d> --project <p> --session-document <受控文件>`；参数路径只指本机受控文件，secret不在argv/日志；命令不接受任意shell。调用方重复使用同device/group/scope即可，不另要求记忆随机幂等key。用 `status-device` 读目录期望、目标组DB和入口实际路由，区分reserved、registered、routing-pending、available；这些为现场推导结果，不保存第二状态机。

1. 取得发布锁和目标组管理锁，校验全清单、原目录及追加差异、目标组readiness与配置。已有别组预留立即冲突；先原子保存新设备`enabled=false`，确保命令在创建RS后崩溃也不能被另一组抢登记。
2. 调组内注册API；失败保留false预留，其他设备/组继续。凭据按当前session格式在目标组session父目录原子合并发布：先验证旧项不丢失/不改动，新token不能重复或属于其他scope，原到期/撤销规则保留。源凭据不放路由目录，不把创建设备等同授予所有用户权限。
3. 用新设备的授权会话执行一个不产生Workspace/任务的backend scope就绪查询（新增普通 `GET /v1/device-context`，返回当前scope/repository及组/环境，认证和设备header同其他业务口）；确认目标组尚可受理。无需为了验证授权先写业务。
4. 原子将目录该项改为true，从完整有效目录生成独立candidate Nginx配置，运行同版本`nginx -t`后原子发布固定配置并HUP。只发布候选，不覆盖/清理其他组配置。已有条目只能保持原路由。
5. 通过仅loopback管理探针验证加载的配置摘要和该key实际选择组（Nginx本地生成的静态响应，不查询业务DB）；每次用新连接，至多30秒。随后通过公开入口调用device-context核端到端身份。二者满足才报告新增成功。probe/token不写公开访问日志。

`t`失败/目录true后崩溃/信号结果丢失时，期望目录可能领先于实际入口；旧有效代理继续服务旧设备。命令报告未完成，保留候选、旧有效配置和错误，下一次从目录+DB+实际探针幂等核对并重试；不能仅凭文件true或HUP exit0报告成功。损坏候选不替换旧有效配置。进程整体重启先测试磁盘有效配置；不能因失败candidate覆盖最后有效配置而丢掉已有路由。无无限自动重试、定时reconciler或跨文件事务要求。

同组维护命令与新增命令使用同一个组管理锁，不能在register成功至路由开放间启动stop-group。HTTP drain仍是最后受理屏障，持锁不是鉴权替代；服务因独立故障失去ready时新增失败，不改其他组。成功只证明本次检查时可用，不承诺之后不发生故障。

## 6. 部署、资源和维护

每组清单固定所有可写root源路径，跨组所有路径两两不相等/不嵌套；同filesystem可不同目录。校验实际mount/dev身份，不只比较字符串；继承现有root/symlink保护。独立metadata/telemetry/RS ledger/缓存/临时路径，不能共享默认named volume、session文件、RS或internal token。容器只挂本组root。相同只读依赖镜像可以共享，不把物理带宽隔离写成承诺。

新增RS内部身份响应（受本组bearer保护，返回environment/group及现有storage digest）及client窄方法；backend启动和注册前核匹配，worker启动同样核。本轮不让RS理解设备业务scope。credential隔离+网络隔离+端点身份核验共同覆盖误连；不能把`/readyz=200`当正确组身份。

部署渲染必须产出每组明确backend/worker/RS镜像、端口、文件与Compose项目；固定worker服务继承同组源Compose/镜像，不能引用另一worktree的base。维护脚本目标必须同时符合environment/group/project及实际container labels、config挂载与进程代际；沿S2a实际进程/cgroup退出判据。只改变A组版本/资源时不重启入口/B组，不要求全局配置generation同步。各组允许明确经过验证的版本组合，不支持组内滚动混跑。

整机预算由部署清单校验一次：`sum(Wg*Eg + BEg + RSg) + entry + shared_reserve <= host`，CPU同式；各group现有host_budget必须与该host声明一致但不得各自计一次共享reserve。保留单组局部上限检查，新增host汇总拒绝超配。kernel M不等于RSS，默认N1、W=K、每worker reserve>=8GiB不放宽。现行生产E32/M24不自动改成测试值。

磁盘按宿主真实filesystem身份合并空闲/低水位，不把同盘空闲加两遍，不把各组水位当独享配额；若配置容量份额则总份额不能超过宿主预算。无总配额分配器，不保证并发写入永不ENOSPC，已有bounded scratch、预检、失败与protected artifact规则继续有效。thin guest空闲不能证明宿主pool空闲。

## 7. 验证和完成标准

退出证明至少两个同版本独立组；真实跨版本灰度、迁移/降级和性能容量均不在本阶段承诺。每个不变量一个owner：

| 行为 | 权威验证层 |
| --- | --- |
| 配置exact、追加差异、唯一性、hash向量、预算/路径冲突 | 纯单元，无Dolt |
| scope注册原子性、重复/冲突、推进Head后重放不回退、启动seed不覆盖 | backend Contract + SQLite；RS client用有界替身 |
| 原RS create响应丢失/同key恢复 | 复用RS owning tests；新增backend只验使用相同key及不换key |
| register与drain、响应丢失、配置发布失败和重试 | backend/脚本 focused，时序依赖标serial |
| 双组隔离/端点误连、实际资源、仅A维护、Nginx流式与reload、热文件inode | 一组集中Compose场景，绑定当前候选和镜像 |
| 请求层所有请求一致路由、切会话不串scope、未知设备/错误保持 | 前端请求层单元及最小真实backend e2e |
| A旧设备任务和B组继续，A在线加入新设备且完成业务 | 必须Compose验；保留实际在途屏障和配置/容器代际，不能只比较串行调用成功 |

最小矩阵：两组W1/N1为基础；A W2、B W1另做必要组合接线，复用S2a worker不变量，不复制全故障矩阵。合成设备用于明确边界，不冒称两个真实设备。真实输入与资源执行清单见执行计划§7；D24 N2/N1与t4参考仍最迟S5。

## 8. Contract 与后续边界

实施包A先将实际协议加入Business Lifecycle（设备归属/注册/INITIAL）、Operation Lifecycle（新增受理/drain、原恢复不变）、Repository Service（身份窄接口/原create）、Canonical Storage（组root边界）、Statistics（组作用域）、backend HTTP/OpenAPI及部署规格。必要时新增窄`processing-groups-and-routing.md` owning部署Contract并更新taxonomy，避免同一规则在多处各自成为权威；不得因本文增加第二恢复系统。

S4b消费者保持：环境/组身份清楚、唯一写入组、原ID可保留、所有业务记录仍组内可枚举。S2b不实现通用导出器、生产换组或跨版本备份恢复。S3调度/背压不提前进入本阶段。公共入口协议需同步前端/外部消费者，不以“后端已支持”代替产品接线完成。
