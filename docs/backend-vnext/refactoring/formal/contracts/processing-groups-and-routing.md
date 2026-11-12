# Processing Groups and Device Routing

状态：Accepted S2b target；A 已提供配置模型、标识向量及 wire DTO，HTTP/部署接线随 B–E 激活，阶段验证以 F 为准。

Owner：Backend Deployment / HTTP 接入边界。业务 scope / INITIAL 由 Business Lifecycle 拥有；Repository 创建与恢复由 Repository Service 拥有。

## 1. Authority

同一 environment 中每个 exact device 只有一个正式写入 group。宿主 `device-directory.json` 保存归属预留，组内 control DB 保存 project/repository/INITIAL/Head；session 文件保存授权。目录不保存业务对象/secret，也不参与组内任务的配置锁存摘要。目录损坏仅阻止新增/发布，已有服务继续使用最后加载的路由及 DB 事实；禁止遍历各组 DB 猜测重建。

设备与 project 为原始 UTF-8 exact 字符串：1..255 Unicode scalar、最多1020 bytes，拒 NUL/surrogate/noncharacter；不 trim、大小写折叠或归一化。设备不是 pathname、URL 或 shell 片段。Python/TS 共享向量在 `vnext/fixtures/processing-groups/v1/identity-vectors.json`；业务 digest 不变。

P7-S2B-D07（Owner 2026-11-12）规定 noncharacter 为 U+FDD0–U+FDEF 与平面 0..16 各自末尾两个码点，共 66 个。所有 device/project 身份入口（目录/组配置、HTTP DTO、session、seed、领域与业务写入）在摘要或注册副作用前拒绝；HTTP 沿输入校验错误，配置加载沿既有失败方式。保留中文、emoji、组合/预组合的 exact 区分；不放宽 [Shared Canonical Encoding](shared-canonical-encoding.md)。本增量尚待 A 实现、验证和原审复审，不表示已激活或 A 已 GO。

## 2. Host documents

JSON 均拒重复 key、未知字段、bool 充 int、非有限数。schema_version 固定整数1。

- directory：最多8MiB/10000 devices，字段 `schema_version, environment_id, devices`；每项仅 `gateway_device_external_key, group_id, enabled`。false 仍独占预留；重复设备/route-key碰撞/未知组拒绝。新增只允许追加、false→true、exact重放；禁止删除、改组、true→false。
- groups：最多1MiB/32组，字段 `schema_version, environment_id, host, entry, groups`。host 为 `memory_bytes, cpu_count, shared_memory_reserve_bytes, shared_cpu_reserve`。entry 为 `listen_address, listen_port, management_port, image, memory_limit_bytes, cpu_limit`；监听仅明确 IP literal，管理端固定 loopback。
- 每组为 `group_id, project, backend_port, storage_config, resource_config, session_directory, internal_token_file, repository_token_file, images`。backend 端点只能派生为 `http://127.0.0.1:<backend_port>`，不接受 caller URL。images 为 `backend, worker, repository_service, revision`（完整 Git SHA）；禁止无 tag / latest / shell 片段，引用由部署方固定，运行还须核实际镜像身份。
- 所有路径为绝对、规范 POSIX server-owned 路径；不接受任意 Compose/shell 配置。各组 project/端口/session/token 不共享。实际 mount/root、同盘容量、CPU/内存汇总由部署 preflight 核验，纯 parser 不声称已核文件系统。

父目录 ro bind；文件以同目录 temporary+fsync+replace+父目录fsync 热发布。全局发布锁后目标组锁；维护只取目标组锁，不反向取发布锁。退出释放 flock，不靠文件存在判断占用。

## 3. Public protocol

所有普通 `/v1/` 请求（含对象ID、分页、轮询、上传、下载）携带同一会话快照的 Bearer 和单值 `X-Gateway-Device-Key`，值为 `SHA256(UTF8(device))` 的64位小写hex，无前缀、无project。入口先严格校验再 map 至固定 upstream；未知 key 404，无默认组/跨组 fallback/写入重放。组端独立核Bearer、header及本组active scope/INITIAL，再走原对象权限。

未认证401；header/请求格式错误422 `REQUEST_VALIDATION_FAILED`；设备/对象/本组归属不符404 `RESOURCE_NOT_FOUND`，不泄露正确组。health、预检和 internal 管理不要求设备header。入口仅公开 `/v1/` 和无敏感health，拒 `/internal/`。

| API | Authorization | Request / Response |
| --- | --- | --- |
| `POST /internal/v1/devices/register` | 本组 internal bearer | 严格 body≤8192 bytes：environment_id/group_id/device/project四项（完整字段名同 directory/DTO）；200首次及exact重放均返回四项+repository_id+initial_node_id+initial_commit_id |
| `GET /internal/v1/devices/registration?device=...` | 本组 internal bearer | 同有界设备域，只读DB/固定INITIAL；200同上，缺项404；不以可变Head猜INITIAL |
| `GET /v1/device-context` | session+device header | 200四项+repository_id，只返回本scope最小上下文，不增权限名；final probe另核可受理 |
| `GET /internal/v1/deployment-identity`（RS） | 本组RS bearer | 200 `{environment_id,group_id,storage_digest}`，读取既有preflight，不扫描root；ready不能代替身份 |

注册配置/scope/禁用/固定归属冲突409；gate关闭503。响应沿原 ApiError（RS沿SimpleError），不含secret/private path。DTO和错误进入实际路由生成的OpenAPI；不注册占位路由。

## 4. Hot add and failures

新增顺序：预留false→组内原key注册→原子追加本设备授权→scope probe→目录true→同版本nginx -t→原子发布/HUP→loopback实际加载摘要/组probe+公共device-context。仅文件true或HUP exit0不能报告available。旧有效配置必须保留；坏候选不替换，未确认报告未完成并允许同身份重试。不建注册任务表、目录服务或第二恢复器。

注册原key、固定INITIAL及短事务由 Business Lifecycle 拥有，RS I/O 在事务外。注册完整受理区间持原 AdmissionGate，drain可见in_flight。空seed/合法空sessions可以启动，空sessions全部普通请求401，不注入默认token。旧设备及在途任务不中断；维护A不停止B/入口。已有设备迁移/删除/禁用/重绑由S4b另定，调度/背压由S3另定。

## 5. Isolation and budgets

每组完整BE/worker/RS和独立可写DB/Dolt/roots/凭据/生命周期；只读依赖镜像可共享。实际跨组root不等/不嵌套；相同filesystem合并容量水位，不能重复承诺空闲。

整机一次核 `sum(W*E + BE + RS) + entry + shared_reserve <= host`，CPU同式；各组局部预算仍核，W=K、N默认1、worker reserve≥8GiB不放宽。无目录generation强制其他组停机。两组同版本验证不代表跨版本兼容或硬件故障隔离。
