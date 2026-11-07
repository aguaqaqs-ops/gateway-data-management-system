# BE-d：完整 Bundle tar 传输设计

状态：2026-11-07 设计草案，Owner 已确认成员对应方向，待独审及实施 kickoff；未实现。引用当前生产 reader 为 `bootstrap/composition.py::LocalArtifactBundleReader`，仍只读 manifest；FE3 `posix-tar.ts` 已按严格闭包消费。关联 [联合 kickoff](p6-be-a-d-kickoff.md)、[Comparison Bundle](../../../contracts/comparison-bundle.md)、[归档业务核验](p6-archive-business-validation-design.md)。

## 1. 范围与消费者

Preview `/bundle` 与 History `/bundle` 一次请求返回完整、不压缩 POSIX tar，媒体类型 `application/x-tar`。下载后前端离线浏览，不加按artifact下载接口；不保留JSON/tar双格式。BE-b导航和归档动态来源图不进入本任务；归档事实通过其业务API读取。

共享在既有bundle assembler中表达，传输层不能另做内容去重或改写digest。业务内容与既有manifest/closure保值；发现producer缺口时明确报告、定向修订，不能为使下载成功悄悄更改golden。

## 2. 成员对应（Owner已确认）

按普通文件成员计数，顺序严格为：

1. `manifest.json`，既有发布manifest字节；
2. `artifact-closure.json`，同一发布的closure字节；
3. 最终closure的每一个entry，按既定顺序各发送一次，成员名恰为其`logical_path`。

每entry一个普通文件；每成员一个entry，不缺、多、乱序或重复路径。PAX长路径扩展头是编码，不是业务entry；禁止symlink/hardlink成员，不能用链接省掉被声明的路径。保留路径、绝对路径、`..`及跨root异常拒绝。

多个业务引用可通过同一closure entry及其`table_bindings`共享一个文件；相同source_ref/hash如果最终仍声明为两个不同logical_path，则两个成员都必须发送。只发一次是指已由assembler合并成一个entry的共享产物，不是下载时按字节内容去重。

固定向量包括：两个pair/side引用一个shared entry；相同源对应两个合法不同entry；相同内容但不同schema不可误合并；重复/冲突路径拒绝；pax长路径与空文件。与前端fixture逐项核对，发现差异交设计，不强迫前端放宽完整性校验。

## 3. 传输生命周期与预算

- 调用既有Preview/History鉴权、exact scope与readiness/TTL检查后，解析并交叉验证manifest/closure、引用身份、每个成员的大小和摘要；响应头前完成预检。参数中的artifact ID不得变成caller可选host路径。
- Reader返回明确的准备结果：业务bundle digest、准确总长度、下载名、受控stream及close责任；不能保持原`tuple[name, iterator]`却在route重复读manifest拼头。metadata预检必须在返回StreamingResponse之前执行，不能放在尚未迭代的generator中造成“200之后才报预检错误”。
- 使用现有artifact保护／handle生命周期协调cleanup。不能一次把全部产物读成bytes或为所有成员永久打开FD；与S2b已修复的FD生命周期保持一致。若现有公开保护port不足，最小扩展owner接口，不复制私有store状态机。
- 预检与发送分别用有界chunk；建议单stream工作buffer不超过1 MiB、同时活动产物handle不超过2（metadata除外也须有界）。metadata使用现有manifest限制，正式handoff给最大chunk/FD/内存计数；不拿M24作为下载可以攒包的理由。
- 响应长度包括tar512字节头、每成员padding、pax头与内容及padding、结束零块。固定mtime/uid/gid/mode等非业务头字段，文件名UTF-8与pax规则确定；长度计算与实际编码共享规则并有独立固定向量。
- `Content-Length`必须等于实际响应字节数；`ETag`为HTTP引号包裹的bundle digest；文件名安全且以tar标识。当前无Range/压缩/分段下载consumer，本轮不新增。
- 头后I/O错误立即中断，不能吞异常或补齐假成功；断连、取消、正常结束、异常都释放保护与句柄。前端只在全部成员、摘要和总长度验证后提交OPFS事务，失败丢弃未完成副本。

## 4. 错误与OpenAPI

保持两路由现有的认证/授权、资源不存在、结果未就绪及过期分类，不统一改成空tar或200。Preview现有缺bundle为404 `RESOURCE_NOT_FOUND`，History现有artifact不可用路径为404 `ARTIFACT_UNAVAILABLE`；实现前把各实际异常路径映射列成参数表并同步OpenAPI。

建议新增typed bundle完整性错误映射503 `BUNDLE_INTEGRITY_FAILURE`用于manifest/closure矛盾、摘要或大小损坏；缺失/不可用依现有资源分类处理，不能把完整性失败隐藏为可正常下载。此码为待审设计，非现有API。服务器私有路径、原始业务行不进入错误响应。

OpenAPI明确200 `application/x-tar`及Content-Length/ETag；删去旧JSON/octet-stream声明。旅程工具解析全部成员并校验closure，不能只取manifest就PASS；GET开始到读完的时间、实际响应字节数单列只报告，不改READY/operation完成锚点。

## 5. 验证与交接

纯编码/长度/closure匹配用固定小向量；公开HTTP两个路由参数化鉴权/状态/缺失/损坏；生产wiring覆盖Preview FULL/MODIFIED_ONLY/replacement、History两/三节点、共享/长路径/空表。一个代表性stream失败、断连和cleanup并发测试证明资源释放，不穷举内部时序。

06/05定向开发，04最终候选runner包含必要Compose；05一次fresh t1包含Preview与History整包下载，默认不新增t4或完整基准。无真实长路径/共享形态时由合成wiring覆盖，不能要求全量数据重生成。若与归档核验在同一最终候选验收，复用同次旅程/Compose，不为两个任务重复启动。

按包闭包和容器身份等价分别判定沿用；当前路由/harness变更须最终HEAD镜像验证。原基准冻结工具/镜像不改，main旅程tar消费修订只用于新产品候选。前端快照/fixture与实际tar对接由FE3 owner更新，后端提供确切提交、OpenAPI、固定向量和证据。

设计交付不代表新接口已可用；BE-d独审及最终验收完成后才能向FE3报依赖解除。
