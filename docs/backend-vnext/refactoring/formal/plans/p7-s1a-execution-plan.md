# P7-S1a 实施执行方案

> **P7-D27 最新切换安排：**B 由原三角色完成必要验证、复审和收尾后暂停，不自动进入 C；门禁工具按规格完成独审与专用节点验证后，协调者从 C 恢复新流程。C–G 取消专职测试者，实施者负责 focused、协调者触发门禁；按风险安排不同模型家族独审，G 全范围独审仍覆盖 A–G。C–F 不逐包跑完整门禁，G 集中验收，产品与真实验收范围不变。C 起过程材料放仓库外，最终一页总结入库。下文旧“逐包三角色/自动推进/入库 handoff”仅保留为 A/B 的执行依据；C–G 以 [S0 决议 §7](p7-s0-owner-decisions.md#7-b-收尾后的流程切换owner-后续确认与安排) 为准。

> **2026-11-10 Owner 补充交接要求：**S1a exit 须向前端交付并以实际证据核对：规范化 OpenAPI 不变，bundle tar 的 `logical_path` 成员集合及 manifest 字段集合不变；ID 与摘要的取值可能变化，交接须逐项列明变化及影响。上述为验收要求，尚非已验证结论。BE-b 第二步设计在 S1a 本地 exit 并合入 main 之后由后端开始（owner 2026-11-10 更正，取代同日“现在开始”的记录），随后实施；DC74 标为“未生效，随 P6 退出关闭”。参见 [后端交接与 BE-b 第二步启动记录](p7-s1a-frontend-beb-handoff.md)。

日期：2026-11-10。状态：**实施文档已落成，可供编码会话按序执行；代码未实施，独审与产品验证未执行**。

设计依据：[S1a 详细设计](p7-s1a-storage-resource-design.md)、[处理组与设备测试副本](p7-processing-groups-and-test-extraction-design.md)、工作区实际 [S0 决议](p7-s0-owner-decisions.md)、[P7 总体设计](p7-design.md)及[总执行计划](p7-execution-plan.md)。本文把既定目标细化为实现输入、工作包、完成条件和验收责任；不重新询问已确认的单机、按类挂载、全状态测试复制和不回合并边界。

> **Owner 2026-11-10 验证节奏补充（适用于当前进行中的 S1a）：**A–F 工作包做针对性逻辑/Contract 与必要数据验证，G 在最终候选集中构建和验收。不因小节交接、角色更换或复审重复完整构建、全量 runner 和完整真实旅程。只能在容器内证明且影响后续接线的行为，相关修改收敛后做最小容器验证，可合并关联小节。具体执行见 §5.2；此补充不重写此前实施/测试事实。

Owner 于 2026-11-10 已授权**下一编码会话直接推进 S1a A–G，直到 S1a 本地 exit**，各工作包分别新建实施/独审/测试三角色，沿用最近 P6-S6 模型安排，详见 §4.1–4.3。本设计会话只补文档，不立即写产品代码或启动测试。下一会话无需逐节申请开工、正常修复/验证或符合条件后的本地退出；不授权上线、push 或 S1b 以后实现。

## 1. 分组和设备抽取放在哪一步

保持 P7 的 S0–S5 大阶段编号，按依赖细分 S2 与 S4；这是本轮文档的阶段安排，不表示这些能力已获产品验收。

| 阶段 | 交付边界 | 为什么放在这里 |
| --- | --- | --- |
| **S1a** | 单处理组内多 root、显式环境/组身份、配置/资源边界；默认一组一个 worker | 先让每组可以拥有完整独立存储；不提前实现设备路由或复制工具 |
| **S1b** | 单组统计与查询，记录环境/组/设备归属 | 从一开始区分来源与副本，避免以后把相同 ID 的两个物理副本少算 |
| **S2a** | 原 S2 的组内多 worker 租约、claim、K 与恢复正确性 | 原子 claim、unknown effect 和健康 worker 并存是后续所有组运行的基础 |
| **S2b** | 同机独立处理组、静态设备归属目录、组内写入范围检查、各组资源与故障隔离 | 验证两组可独立运行；目录只管设备归属，组内维护业务状态。首版用受控配置/管理入口，不以外部注册 API 为前置 |
| **S3** | 组内队列/准入/公平和整机资源总预算 | 在已明确的组作用域内调度；不建设在线跨组调度器或自动迁移 |
| **S4a** | 原 S4 的映射管理、外部历史回灌及组路由接线 | 确定最后一批任务关联/幂等记录，使抽取能覆盖实际最终 schema |
| **S4b** | 单设备全状态导出/加载、独立测试运行、排空后的受控生产换组说明及必要接线 | 在业务/队列/审核记录结构稳定后做闭包导出，避免每阶段重写抽取器；测试复制与生产写入转交分别验证 |
| **S5** | 统一容量配置、分组/回灌/测试副本的综合验收和操作手册 | 验证交付组合，而不是到 S5 才开始开发抽取工具 |

S4b 以“设备全状态单向测试副本”为首要交付；无历史选择器、无回合并。生产换组仅限停投递、排空/查明 effect 后的唯一写入责任转交，不能直接把测试副本接回生产。具体目录变更、工具接口和导出表清单在 S2b/S4b 各自实施前细化，不把其设计空白转嫁给 S1a。

上述安排已获 Owner 确认并同步总计划。原 S2 的多 worker 退出要求在 S2a 完成后仍保持，S2b 另验证组隔离；原 S4 回灌验收在 S4a 完成后仍保持，S4b 另验证抽取。S5 保留最终六包、容器及适用真实数据要求；P6 验收与已办退出不变。

三份原 S0 文档已按本次授权补入阶段/分组边界和 S1a 执行授权，原 S0 决议保留。编码会话以工作区实际七份 P7 文档为输入，按实际改动同步 owning Contract；“共享 DB/roots”明确指**组内共享**，不能实现成所有组共用一个全局 control DB。

## 2. S1a 的范围与入口

### 2.1 必须交付与不进入本步的工作

S1a 交付一组一 worker 的完整上传、Preview、Submit/Review/Archive、下载、恢复及维护链，支持同盘和按类别分盘。必须覆盖 backend 与 RS 两端，实际容器挂载、权限、资源限制和容量失败行为都要接线。

本步不实现设备→处理组目录、组间请求路由、生产设备换组工具、全状态导出/加载器、多 worker 启动协议、全局队列策略、统计数据库/查询 API。配置中保留明确的环境与组身份属于当前部署命名，不预建空 routing 表、通用迁移协议或抽取格式。

### 2.2 实际代码起点

- 已复核基线 B：`p6-exit` → `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`，`vnext` tree `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。
- 当前工作区是较早的 `fe3b-evidence-04`，HEAD `a300b16485bcad2f178aaccfe0c8adbb51b5ab83`，不能直接在此编写 P7 产品或覆盖后续 P6 改动。
- 实施会话先确认 main 当前实际提交，B 必须在其祖先中；记录 B..实际起点的产品差异并复核新增消费者。使用不干扰已有工作区的正确 checkout；不切走当前其他会话的分支、不携带其 dirty 文件、不重写已审核提交。
- 先将本轮七份 P7 文档按仓库流程纳入实现可引用的本地提交：S0 决议、总体设计、总执行计划、S1a 详细设计、分组补充、本方案、新会话提示词。确认文件自交接后无他人并行改动，再逐路径暂存；不得顺带提交 `fe3c-review.md`、architecture/implementation-stages 等其他会话文件，不用 `git add .`，不因输入未提交而忽略其内容。
- A已固定`5ddd73b962`并提交七份原件`bc184e5007`，详见[A入口与消费者/摘要表](p7-s1a-a-entry-and-contract.md)；A仍仅提交待实现Contract目标，未记产品通过。实施与复审/测试 worktree 分开，测试必须是 clean 已提交源码。

## 3. 编码输入定稿

本节定稿此前留给工程细化的接线；语义不变量仍由详细设计及 owning Contract 约束。文件名可在不改变职责时作常规调整，但不得改变配置来源或增加兼容路径。

### 3.1 配置文档与作用域

保留两个职责不同的权威配置文件：`storage-layout.json` 管位置与挂载，`resource-profile.json` 管资源。每个参数只在其 owning 文件出现一次；Compose 的 bind、environment、mem_limit/cpus/replicas 都由这两份输入渲染，不在 YAML 中另填第二份常量。secrets 文件不纳入上述 JSON。

| 配置 | 必需字段 / 约束 |
| --- | --- |
| 两份公共头 | `schema_version: 1`、`environment_id`、`group_id`；两个 ID 均为 1–64 位 `[a-z0-9][a-z0-9_-]*`，不作为用户设备身份；两文档必须一致 |
| storage `filesystems` | 以部署自定短名为 key；每项包含宿主 `mountpoint`、`expected_source`、`min_free_bytes`、`min_free_fraction`；production bind 必须显式核对 mount 来源，不以路径存在推断挂载成功 |
| storage `roots` | 精确包含 S1a 的十个 slot；每项 `source`（宿主绝对目录）、`path`（容器绝对目录）、`filesystem_id`、`storage_id`（32 位小写十六进制）、`mount_mode: "bind"`。本阶段标准模板使用 long syntax bind 且禁止自动建 source |
| storage marker | 每 root `.gateway-storage.json`：`schema_version/environment_id/group_id/slot/storage_id`。显式初始化时写，启动只核对；不含凭据，不作为业务状态 |
| resources `worker` | `count=W`、`active_limit=K`、`kernel_threads=N`、`kernel_memory_bytes=M`、`memory_envelope_bytes=E`、`memory_reserve_bytes`、`cpu_limit`、`swap_limit_bytes`；S1a W=K=1 |
| resources `backend` / `repository_service` | 各自 `memory_limit_bytes`、`cpu_limit`、`swap_limit_bytes`；RS/Dolt 子进程包含在 RS 容器预算内，不再次当作独立份额累加 |
| resources `host_budget` | `memory_bytes`、`cpu_count`、`shared_memory_reserve_bytes`、`shared_cpu_reserve`；部署规划值须在实际宿主/祖先 cgroup 的可用范围内，不把 declared 值当作现场实测 |
| resources `temporary` | `scratch_max_bytes_per_attempt`、`staging_max_bytes_per_object`；正整数 bytes，不允许 0 表示无限。HTTP 接收阶段以 request/upload context 作为 owner，没有 operation 时不伪造 operation |

`deployment_id` 在初稿中的含义收敛为显式 `(environment_id, group_id)`，不再增加第三个同义配置字段。大小均为 bytes、时间为 seconds；整数不得接受 bool/小数，浮点配置拒绝 NaN/Infinity，所有结构拒绝重复 JSON key、未知字段与不支持的 schema_version。CPU quota 以有限正数核数表示，N 不大于有效 quota 的整数部分及 cpuset 限制。

十个 slot 的 source/path 均不得相等或互相嵌套；允许它们映射同一 filesystem。source 的父目录、root、内部对象不得经 symlink 逃逸；runtime 不检查未挂进本服务的其他角色路径。每个服务结构校验配置后，只打开本角色授权的 roots。配置大小固定上限 256 KiB，十个 roots 与 filesystem 数量有明确界限，不从配置递归展开模板。

宿主渲染工具校验完整布局并生成 Compose override/env；`render` 只做结构验证和生成，不声称远端挂载已通过；显式 `check-host` 在实际执行主机核 source、filesystem 与规划资源后才能初始化/启动。backend 和 RS 在各自 bootstrap 的 typed adapter 中独立验证本角色配置与实际 roots/cgroup，不能只信渲染结果。两侧使用相同配置格式向量核对摘要/解析结果；不为共享几项配置新建 Python 包或改动 shared kernel 的领域职责。摘要采用现有 JCS＋SHA256（仅规范字段），运行日志只记录摘要、逻辑 slot 与脱敏原因。

后台进程的内存/CPU 与挂载核验在角色预检完成后才允许 readiness/claim。统一规范设置入口为 `GATEWAY_STORAGE_LAYOUT_FILE` 与 `GATEWAY_RESOURCE_PROFILE_FILE`；旧单 root 和重复 worker N/M/E 环境入口删除，运行值由 JSON 注入 settings。凭据、session、mapping 等未被替代的 settings 保留原 owner。control DB 的目标位置由 metadata slot 及固定相对文件名得出，不另接受一个可偏离该 slot 的绝对 DB 路径。

### 3.2 值的来源与开发验证样例

| 参数 | 选择 | 性质 |
| --- | --- | --- |
| N / M / E / reserve / W / K | 1 / 24 GiB / 32 GiB / 8 GiB / 1 / 1 | P6 最终单 worker 起始配置，不声称覆盖任意输入 |
| E/M 上限、reserve 下界 | E≤48 GiB、M≤40 GiB、reserve≥8 GiB，M≤E−reserve | 延续/收紧已复核预算边界，不自动调参 |
| scratch / 单对象 staging cap | 开发验证样例分别 8 GiB / 4 GiB | 有界工程样例，非 P6 测得峰值或 S5 生产默认；达到 cap 明确失败 |
| backend filesystem 水位 | 开发验证样例 5 GiB 与 10%，取较大者 | 与已有 RS 水位同量级的保守起点，不证明设备数容量 |
| RS 水位/import headroom | 5 GiB、10%、1 GiB | 沿既有值，改为检查实际写入 filesystem |
| CPU、backend/RS limits、宿主总预算 | 必填，根据实际节点可用资源填写 | 不设冒充生产容量的全机默认；实施者可选择符合公式的开发 profile，无需为普通数值反复问 Owner |

交付配置模板及一个填写完整的开发 profile。完整开发 profile 的 CPU/共享服务份额由实施时现场预检确定并写入 handoff；本轮不访问节点，不能把未观察数值伪装为可运行证据。小型 fault fixture 可以使用更小的测试 cap，明确它的输入范围。S5 最终默认值按目标硬件/真实数据另定，不阻塞 S1a 参数接线。

上传压缩/展开、单 Parquet、bundle metadata 等已有上限不因新增 cap 放宽。配置 cap 更小时，该负载可能得到资源拒绝；不得将拒绝当作处理成功。多 root 同盘对 available/headroom 按实际 filesystem 合并，预检之后仍保留 ENOSPC/EDQUOT 安全失败。

### 3.3 实现模块与接口落点

以下新增路径是实施目标，不表示文件现在已经存在。`BE`、`RS` 的展开同 S1a 设计。

| 边界 | 实施落点 |
| --- | --- |
| Artifact ID codec | `BE/artifacts/location.py` 新增枚举/parse/build；修改 `types/digest/validate/serialize`，四字段 ref 不新增 locator 字段；现有所有 producer 使用显式 location |
| typed roots 与本地 borrow | `BE/infrastructure/artifact_store/layout.py` 新增；`local_store.py` 统一路由；不让 capability 取得宿主 root 或自行组合路径 |
| 流式文件导入与 temporary owner | `BE/artifacts/store.py` / `bounded_store.py` 端口；`BE/infrastructure/artifact_store/` 实现；将 client Parquet、comparison Parquet spool、HTTP Arrow及multipart接收临时目录接到配置scratch。multipart由composition/dependencies/route在解析前注入request/upload owner、其余当前operation owner，共享累计cap并保原producer上限；覆盖取消/ENOSPC与close失败收尾 |
| backend 配置/生命周期 | `BE/settings.py`、`bootstrap/composition.py`、`bootstrap/operation_worker.py`；两个 production worker composition 入口一起改 |
| backend 维护 CLI | `BE/bootstrap/storage_admin.py` 新增 `init-layout`、`check-layout`、`cleanup`；只接受配置和 bounded 参数，不接受任意服务端文件路径删除 |
| RS 配置与 layout | `RS/deployment_config.py` 新增窄配置 adapter；`settings.py/layout.py/runtime.py/process.py` 修改；由具名字段访问 root，不留万能 `layout.root` 推断 |
| RS 管理/发布/清理 | `artifact_layout.py`、upload/create/import/recovery/cleanup、`snapshot_admin.py` 及 offline admin 同轮适配，不只改 settings |
| 部署渲染 | `vnext/scripts/render-runtime-config.py` 新增标准库 CLI，读取两配置并渲染已有 Compose 模板的 override/env；输出在 worktree 外，配置错误非零，不自动创建 mount source |
| 容器与说明 | `vnext/deploy/compose*.yaml`、deploy README、RS entrypoint、必要 Dockerfile 和现有 Compose harness；生成物不作为新的产品状态机 |

首次 `init-layout` 只在显式预检过的空目录中写 marker/必要子目录；已有 marker 匹配时幂等，不匹配时拒绝，不格式化/擦除目录。RS entrypoint 在实际挂载核验后仅准备本服务子目录，不递归修复整个宿主目录权限。host preflight 核源 filesystem、容器 preflight 核实际 mount+marker，两层缺一不可。

固定相对路径如下；只在 adapter 内组合，业务 ref 不包含这些路径：

| 字段/内容 | 目标位置 |
| --- | --- |
| backend control DB | `be-metadata/control.sqlite3`，WAL/SHM 同目录 |
| RS control/layout/service lock | `rs-metadata/control/` 下既有 layout.json/service.lock |
| RS service-state DB | `rs-metadata/service-state/repository-service.sqlite3`，WAL/SHM 同目录 |
| RS provider HOME/config | `rs-metadata/provider/`；`DoltRunner` 的 server_root 显式使用 rs-metadata，TMPDIR 显式使用 rs-scratch/provider |
| RS versioned | `rs-repository/versioned/<repository-key>` |
| RS staging_versioned | `rs-repository/.staging/versioned/`，与 versioned 的原子发布对同盘 |
| RS artifacts | `rs-artifacts/<repository-key>/{staging,ready}`，两者同盘 |
| RS staging_artifacts | `rs-scratch/import/` 下按 operation 划分的可重建临时目录；query/probe 另设本角色子目录 |

RS 不再提供能涵盖以上所有位置的单一 `layout.root/staging`。probe/whole-root 管理若需要列举集合，显式枚举对应 roots，不能造一个公共祖先后跨盘 rglob；历史测量报告不重算。`artifact_layout` 在配置 root 处允许已经核验的独立挂载，只有 root 以下的 server-owned 子目录继续要求同 mount、拒绝 symlink/额外子挂载；不能把原“artifacts 与 data_root 父目录同挂载”的检查原样留下。

现有测试使用 named volume 的 harness 可在 setup 中显式准备、初始化挂载后运行相同 adapter；若保留 named-volume 测试模式，必须明确其渲染器字段/验证分支，只用于实际已声明的 Docker volume，不能成为 production bind 缺失后的 fallback。标准交付 profile 先固定 bind，避免新增多种生产挂载后端。

### 3.4 关键实现顺序与失败语义

1. **位置协议**：只接受 `a1:<location>:<64-lower-hex>`。ID/hash 输入、类目和 token 规则按设计 §4.1；`RepositoryArtifactRef` 不套 backend codec。bare ID 查询、重算 bundle closure、canonical key、所有 SQLite/HTTP/JSON decoder 同步切换。
2. **单对象发布**：目标 root 内写 staging directory；copy/hash 分块且支持取消/限额；fsync payload/ref/目录；同盘 no-replace rename；fsync 两侧父目录后返回。Linux `renameat2(RENAME_NOREPLACE)` 采用窄平台 adapter，不增加依赖/通用 syscall 框架；缺能力明确拒绝，不以先检查再 replace 代替原子性。
3. **read/cleanup/pin 锁序**：root borrow 在 DB 事务之前。未知成员的 closure 先按固定顺序借四个 artifact roots；发布在 SH 下用 no-replace 仲裁，禁止升级 EX。保护新增/移交的 application UoW 入口借 root 后再开事务，不能在 `SQLiteArtifactProtectionStore` 已处于事务内时倒序加锁。
4. **删除临界区**：先取得所属 root 非阻塞 EX，再用明确的清理事务入口重核保护/TTL、执行一个对象的受控删除；此入口不能调用再次取得 SH 的普通 protection UoW wrapper。复制/hash/扫描不在 DB 事务内。读到“未保护”后关闭事务再删的旧流程必须替换。
5. **损坏对象**：普通 put 不覆盖既有损坏目录。只在 owning Contract 已允许的 exact-commit 回填路径进行受限修复；先关闭读者，重核恢复资格后独占修复，保留保护记录。不能为冻结 PREPARED 输入新增重建路径；若既有业务 recovery 要求稳定失败，继续稳定失败。
6. **READY/业务状态**：多个对象逐一完成后，由已有 checkpoint/READY/T1/CAS 屏障发表引用；不设计跨文件系统联合事务。发布前缀孤儿按原 owner/TTL 收尾，不能提前宣告成功。

清理 CLI 首版是显式一次性维护命令，无新增后台服务：`--max-candidates` 默认 32、允许 1–32，额外固定单次扫描访问项预算 1,024；最多处理预算内条目后返回可继续的遍历进度。目录使用增量迭代而非全量 sorted/rglob；单次会话跨类别 round-robin，root busy 时跳过，进度仅为派生游标，不建立 durable cleanup receipt。跨调用连续处理由既有运维调用者保留游标；拒绝用户借游标指定任意路径。

对象目录/sidecar/期限异常、未知形状、跨挂载边界均 manual review；staging/scratch 删除还要核非活跃 owner 与持有锁。CLI 硬上限既限制候选数也限制目录项扫描，不能在“最多删除 32 个”的名义下扫描整盘。metadata、Dolt、secrets 不属于它的枚举范围。

对外失败沿现有 owner：启动配置/挂载失败阻止 ready/claim；HTTP 新工作遇基础存储不可用或低水位以既有 `SERVICE_NOT_READY` 503 表达，内部 reason 区分 root unavailable/capacity rejected；已存在的 size 限制、artifact missing 与 integrity 错误保留原接口语义。接收后的文件 I/O 失败交回既有 operation 失败/恢复处理，effect 已发生或未知时保留查结果流程，不能一律重置成可重试任务。HTTP headers 发出后出现失败则中断流，不追加伪成功尾部。

## 4. 顺序工作包与可审提交

可按工作包切若干提交，不按每个文件或每个测试建阶段。相互依赖的 ID producer/decoder/golden 必须同一逻辑批次完成，不保兼容实现来凑中间 green。阶段调试仍只跑 focused；每个包完成不重复全量 runner。

| 工作包 | 文件与具体动作 | 完成条件 |
| --- | --- | --- |
| **S1a-A 入口与 Contract** | 固定实际 main 起点；核 B 后差异；更新本次触及的 Artifact/Storage、Snapshot、Operation、Business、Bundle owning 说明与旧 artifacts.md；标出改变的 ID/raw golden 和不应改变的业务 digest | 有明确入口 SHA、消费者增量清单、摘要影响表；不变更 P6 证据、不新增 migration/兼容别名；Contract 更改与对应实现同轮提交 |
| **S1a-B 配置与位置协议** | typed config、ID codec、完整 producer/decoder、in-memory store、config vectors；更新 canonical/bundle 重算 ID、nominal refs、DB 载荷校验 | 新 ID 四位置可 roundtrip；旧/未知格式稳定拒绝；相同内容在同盘/分盘下身份相等；scope 未丢失。配置 key/上限/必填项与 §3 一致 |
| **S1a-C backend 发布/读者/保护** | multi-root store、no-replace 原子目录、copy-from-scratch、全部读取端口、read/pin/cleanup 锁序、保护 UoW 接线 | bytes/stream/file 三入口完整；copy 中断无残缺可见对象；同 ID 并发与跨 root closure 可读；new pin 与删除不能竞态误删；无 SH→EX 死锁 |
| **S1a-D backend 消费链与维护** | SourcePackage、canonical metadata/IPC、diff/risk/cache、checkpoint/Submit、export/bundle/download、scratch、显式 cleanup CLI | 设计 §3.1/3.2 每行有改动或不变理由；READY/Attempt/Head 保护正确；可选 cache miss 与 frozen 丢失分开；无系统默认 temp 回退或单 root 私有路径绕行 |
| **S1a-E RS 分盘闭环** | 具名 roots、建库 staging→repository、upload staging→ready、SQLite/HOME、import scratch、capacity、reconciliation/admin/cleaner/entrypoint | 删全局同 filesystem 断言，仅保发布对/DB journal 约束；不同盘完整建库/upload/import/recovery/cleanup/admin 可用；backend 无 RS 卷；Dolt versioncheck 初始化仍关闭 |
| **S1a-F 部署与资源闭环** | 两配置渲染、同盘/分盘 profile、mem_limit/cpus/replicas 接线、角色实际 cgroup/mount/marker 核验、停服改挂载说明；补 S1b 必需的 bounded stat/config 关联 | 不一致配置拒启；旧 root/env 设置已删除；M 与 RSS 含义正确；W=K=1；可运行开发 profile 有现场条件记录；必要容器接线做最小验证，完整构建验收移交 G |
| **S1a-G 收敛、独审与阶段证据** | focused 问题收敛，最终候选受影响权威包/Compose、适用真实链、变更区间独审、handoff | §6 退出清单全部有结果；不以自查冒充独审、不口头 carried；未知容量保留限制，下一阶段可以接线 |

**不能延期到 S1b 的内容**：RS 分盘、实际 read/stream/download、保护/清理、scratch 接线与实际容器资源限制。**不能提前塞入 S1a 的内容**：遥测持久化、目录路由、任务分组调度、设备导出表映射或把普通文件故障改成新的恢复平台。

S1b 只需要 S1a 提供稳定的环境/组配置身份、ref/location/size、既有业务引用关系、owning adapter 的 bounded stat/page 及 RS 写入观测接点；这些不增加统计写入事务，不让统计成功成为业务 commit 的前提。

### 4.1 角色、模型与独立上下文

“沿用之前”采用最近 P6-S6 的完整三角色安排，来源为 `p6-exit:docs/backend-vnext/refactoring/formal/plans/p6-s6-implementation-prompt.md` §3 与同提交的 `p6-s6-coordination.md`。较早 S3 的 Sol 6.0 配置和临时 Astra 授权不延续；旧 FE 工作区可能没有 S6 文件，可用 `git show p6-exit:<路径>` 只读核对。

| 角色 | 模型与强度 | 写入和判定责任 |
| --- | --- | --- |
| 持续协调者 | `gpt-6.1-terra` / high | 维护授权、基线、依赖、协调/handoff、推进与最终本地退出，不代替独审 |
| 每包实施者 | `gpt-6.1-sol` / high | 本包产品/Contract/测试源码、执行稿、普通修复及实施交接 |
| 每包独立审核者 | `gpt-6.1-sol` / xhigh，复杂事务/证据冲突可 max | 在 clean readonly detached 候选核设计/代码/执行稿/证据，连续复审本包 finding，只写独审报告 |
| 每包唯一测试者 | `gpt-6-luna` / max | 执行固定已审稿、等待、收集原 exit/日志/资源状态和本人收尾；确认的构建/环境故障按全局快速流程直接纠正命令/环境并复跑，不修改产品、预期、预算/验收范围，不签 GO |

每进入 A、B、C、D、E、F、G，分别新建 `s1a_<字母>_impl/review/test` 三个 agent，显式模型/强度，支持时使用 `fork_turns="none"`。不一次创建 21 个活跃角色；上包原审核收、任务/资源收尾并落盘交接后，再创建下一包，最多四个活跃角色含协调者，不递归扩队。工具没有销毁能力时记录已结束职责，不声称删除会话。

每个角色只接收本包任务单、必读材料、固定候选/工作区、前包交接、原件索引、允许写入路径与未决 finding，不继承前包整段对话。模型不可用时报告具体角色/模型阻塞，不静默替换；协调模型由新会话选择，不假称工具已切换主模型。同包修复由原实施/原审继续，不能换人清空失败记录。

测试角色每包都建，但只执行该包有依据的验证。A 的设计/Contract 静态核对不自动触发产品全测；依赖 B–F 才能成立的实现断言明确移交，不把未实现项记 PASS。若 A 先提交 Contract 目标，必须标注待实现，不宣称已生效；耦合 producer/decoder/golden 在后续同一逻辑批次闭合。

### 4.2 持续推进与停止

每包按“实现/必要 focused 调试 → 固定可审候选 → 原审与所需验证 → 范围内修复复审 → handoff”闭合。上一包明确交接后自动继续下一包；不为命名、helper、正常提交、节点常规使用或逐包验收重复询问 Owner。协调者串行安排 main 写入；审核/测试读固定 SHA 的独立 worktree，测试期间无人修改被测树。确需并行实现才使用短期分支，尽快合回 main，不动其他会话分支。

普通实现缺陷在授权范围内修复并按实际变化复验；失败先停该次执行和依赖后续验收，保留原件，不用无修改重试或改预期制造通过。DC68 按适用的现行 AGENTS、Owner 最新指令与 testing-conventions 执行，不把旧阶段次数/临时恢复许可带入本轮。超过既有规则、原因/副作用不明、来源冲突或实质改变业务/资源边界时，给出证据、影响、选项和推荐，等待 Owner 明确回复；等待不是批准。

**Owner 2026-11-10 最新构建恢复授权：**确认属于非程序逻辑的构建/环境故障，按 [全局快速修复流程](../../../testing-conventions.md#构建故障快速修复owner-2026-11-10)定位、修正并重跑失败步骤，不设固定次数上限，不因旧“一次/三轮”规则停止。环境/命令修正由唯一执行者直接完成，不逐次交实施/独审；源码修订由实施者修复、原审对差异做一次针对性评审后复验。每次有具体修正或已核实环境变化，不盲重试；一个故障条目追加日志索引和结果，阶段 handoff 引用一次。真正的产品 finding 或授权/来源/副作用阻塞按正常流程。当前已仅因旧次数限制暂停的构建可在核分类、现场状态和前提后直接恢复，无需再申请开工。

节点暂时占用/缓存未准备时不回退开发主机测试，可继续无依赖的实现、文档或只读工作；不抢占他人标志或冻结资源。DC33 的具体真实输入/节点范围在准备时提前一次确认，期间继续实现和 focused 验证，不把它变成 A–G 反复开工审批。未确认前不跑完整真实旅程；不自动扩展 t2/t3/t4 或继承 P6 的 06 专项真实验证许可。

### 4.3 G 的本地 exit 收尾

G 新独审必须审整个 S1a 实际改动区间、全部遗留 finding、Contract/golden/消费者闭环和最终证据，不只审核 G 的文档。最终候选 V、绑定 H、实际运行来源、同 worktree carried 与镜像等价分别记录；未满足 §6 任何必需项不得签 `S1a EXIT_GO`。最终文档增量也按真实闭包处理，不把后来的 docs HEAD 冒充实际运行 V。

所有条件成立、独立 EXIT_GO 与资源收尾已核后，协调者按本次“直到 S1a exit”授权，在 main 可达的已验最终 H 上创建本地附注 **`p7-s1a-exit`**；附注绑定产品 V、H、独审/报告路径及摘要、验证范围与限制。已有同名 tag 先核对象/目标/注释：完全匹配则报告已存在，冲突则停止，不覆盖或移动。A–F 不各建退出 tag，S1a 不建立 `p7-exit`。

如为避免报告自身提交循环而将最终签署/回执放在 worktree 外，handoff 明确其路径/SHA256，再以纯文档提交归档且不移动原 H/tag。核 tag 为 annotated、目标正确、main 可达、相关工作区状态及本人资源释放；保留来源测试 worktree/环境/镜像和成功失败原件。交付退出回执后停止，不 push、不上线、不启动 S1b。

## 5. 验证执行方案

### 5.1 focused owner 与节点

以下测试文件在 B 中实际存在，实施时优先扩展其行为向量。新配置/布局/维护 CLI 的直接边界可新增少量测试，不复制整套业务测试。完整场景判据见详细设计 §13。

| 范围 | 权威测试入口（相对包 tests/） | 调试安排 |
| --- | --- | --- |
| ID/发布/读取 | backend `test_artifact_ref_conformance.py`、`test_artifact_staging_conformance.py`、`test_workspace_artifact_store.py`、`test_artifact_boundary.py` | 06 focused；纯类型/codec 不依赖 Dolt |
| IPC/cache/保护 | backend `test_canonical_table_store.py`、`test_canonical_table_cache.py`、`test_computation_cache.py`、`test_snapshot_export_cache.py`、`test_submit_artifact_protection.py` | 06；锁/进程/时间相关场景 serial |
| 配置/资源/接线 | backend `test_backend_settings.py`、`test_worker_kernel_resources.py`、`test_production_wiring.py`；RS `test_settings.py`、`test_capacity.py` | 06；基础数值校验不用启动真实库 |
| RS artifact/layout/admin | RS `test_artifact_layout.py`、`test_upload_artifact_publication.py`、`test_artifact_cleanup_integration.py`、`test_snapshot_admin.py` | 06 的隔离真实 filesystem 与必要 Dolt integration |
| 实际服务边界 | backend Submit/Review/Archive/History Compose 测试与既有 harness；RS import/versioned-read/Compose lifecycle 测试 | 06 focused 小型 Compose；正式候选 04 权威批次覆盖 |
| 真实业务输入 | 默认 05 调试最小受影响链；04/其他获准节点正式取证按 AGENTS 与 DC33 | 不在开发主机运行、不承袭 P6 的 06 专项完整旅程授权 |

需要实际两种 filesystem 的测试预先准备本任务隔离的本地卷/loopback filesystem，验证 device 不同；只模拟 `EXDEV` 不足以证明真实跨盘成功。空间耗尽在隔离小卷/配额中制造，不填满共享宿主。容器缺挂载/权限/运行期丢盘与真正 fsync/rename 失败分别验证，不能只用 mocked Path 作为最终证据。

### 5.2 运行前提与收敛方式

**A–F 是实施工作包，G 是 S1a 集中验收点。**各包完成受影响静态/类型、focused/unit/Contract、必要真实 filesystem/Dolt 与最小数据链后，按实际结果独审和交接，自动推进下一包；不执行各包完整镜像构建、全量 runner 或完整真实旅程。完成条件中的容器断言可明确标为待 G 验证，不预填 PASS，也不因该项集中验收阻塞无依赖实施。

挂载、权限、entrypoint、实际 cgroup 或 signal 等只能由容器证明且影响后续接线的行为，在关联实现收敛后安排最小必要 Compose 验证，E/F 等关联包可以合并一次执行。只覆盖相关行为，不展开所有业务矩阵；G 仍绑定最终候选，早期 smoke 不代替最终门禁。真实跨 filesystem、复制中断、ENOSPC、保护/恢复等必要语义继续按 owning 测试覆盖，不能因省构建退化为只测纯逻辑或只 mock。

handoff 记录本包已验证内容、`deferred` 容器项及具体执行点（默认 G）；独审区分本包实现结论与最终阶段容器结论，不为角色存在或工作包收尾追加完整构建，不以延期关闭已发现正确性问题。构建/缓存故障先停止受影响执行和依赖验收，按现行停止/DC68 规则处理，可以继续无依赖逻辑开发。

依赖基础镜像仅在其定义的依赖/锁/工具链输入变化时重建和传输，产品源码变化使用已有基础镜像与缓存；G 仍按要求在测试节点实际构建产品镜像。一次集中完整验收是正常通过目标，修复后按实际影响重建复验，不设“仅准运行一次”的限制。同次 runner 已覆盖的 Compose 旅程不另跑。

所有测试、编译、lint/mypy 均在专用测试节点，执行前按 AGENTS 核 BatchMode SSH、有效占用、服务/端口及所需缓存；有占用冲突才协调。源码经 LAN 到 clean 已提交 worktree，linked worktree 准备 legacy symlink。06 初始 pytest/Cargo jobs 4，产品 N/W/K 单独配置。

使用 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp` 与受控 uv wrapper。日志在 worktree 外，记录 hostname、起止 HEAD/时间、exit 与 SHA256。focused 测试按文件/marker 缩小；有 Rust 改动先强制重装扩展并核 build-input，但本步不计划修改 Rust kernel 算法。

提交前按 AGENTS 完成五个 Python 包 ruff/mypy；Rust 若实际变化，再补对应 rustfmt/clippy。依赖/锁/基础镜像无计划变更，不因配置工作任意升级。确有必要变更时明确记录原因，按 DC67 预填充实际节点、更新闭包，不从测试 CT 访问公网。

### 5.3 最终候选与真实范围

预期受影响权威包为 **backend、repository_service**；若实际修改 shared_kernel/repository_contracts/repository_client/Rust，则加入相应包。以最终差异与闭包判定，不能预先把未改包标为已通过或 carried。S1a 非 S5，不要求为了形式重复六包。

在 G 的最终 clean 候选由 `vnext/scripts/run-tests.sh` 运行选定包并保留同次 Compose provenance；实际节点按现行 AGENTS 五节点池规则选择和记录。mount/entrypoint/配置/容器 harness 变化在此集中触发最终候选必要镜像重建及门禁，不要求 A–F 各包重复完整构建；backend/worker 采用获准 dependency-base、本机离线 Compose build，不设置 prebuilt 绕过。RS/client e2e 按其预置依赖规则。测试期间不得写 worktree 或手工 retag/rmi。

同盘与分盘都必须在最终候选完成必要容器行为验证；只扩展相关 journey 的布局参数，不把所有无关业务矩阵乘二。已有同次 runner 覆盖的 Compose 旅程不另跑。改动到实际 harness 的输入必须进闭包；日志须标记每种布局的有效 config/root filesystem。阶段最终 H 如只多文档，carried 仍按同来源节点/同 worktree 规则实算，不口头沿用。

**S1a 的真实数据建议范围**：既有标准 t1 MODIFIED_ONLY 第一轮与重复输入，覆盖上传、Preview、Submit/Review/Archive、完整下载及保护后清理；真实旅程以分盘配置运行，同盘功能由相同候选的容器向量与业务 golden 对照。它验证实际消费者接线，不作 t4/FULL/多设备容量证明。若改动面暴露其他必需路径，再据实际差异补充。

真实清单与节点按 DC33 在执行准备时由 Owner 一次确认；这是尚未执行的验收范围确认，不是当前设计缺失，也不要求本轮提前预留节点。未取得范围确认时可以继续已授权的实现和 focused 验证，不能擅自启动完整真实旅程。runner 非零或必需缓存缺失按 AGENTS 停止，不继续后续验收。

## 6. S1a 退出清单

所有项目完成才可称 S1a 实现完成；设计文档落成不满足该清单。

- [ ] 实际实现起点与最终候选 SHA 已记录；B 后消费者差异已复核；未改其他会话工作。
- [ ] 所有 backend artifact producer、serializer、lookup/read/stream/mmap、download、cache/protection/cleanup 使用同一位置协议与 resolver；无旧格式 fallback。
- [ ] 单对象发布完整、跨盘复制中断不发表残缺结果、多 root READY 闭合；同盘/分盘业务语义及位置无关摘要一致。
- [ ] Head、Preview、T1 Attempt、Submission、READY、cache TTL/uses 与下载 borrow 保持各自责任；冻结丢失不被当普通 cache miss。
- [ ] RS 所有发布/恢复/admin/清理使用目标 layout；Dolt、RS DB、RS artifact 边界没有被 backend 绕过。
- [ ] 缺挂载/错卷/只读/权限/运行期身份变化明确失败；没有自动创建 root 或系统盘 temp fallback。
- [ ] 配置同源、参数约束有效，真实容器内存/CPU/挂载与声明相符；一组一 worker，整机预算不重复承诺。
- [ ] backend 有界维护入口可实际使用，未知目录只诊断，不越 root；scratch cap 与 low-space/ENOSPC 结果明确。
- [ ] 已删除替代实现/旧 aliases；owning Contract、相关 raw golden、文档/配置样例一致，业务 digest 变化有逐项理由。
- [ ] 受影响包、必要容器门禁、按已确认范围执行的真实链与独审都有实际结果；不以资源拒绝或缺项称容量通过。
- [ ] handoff、日志/镜像 provenance、限制与下一阶段接口齐全，完成后只释放本任务资源。

## 7. Handoff 与下一编码会话入口

handoff 固定记录：实际起止提交与区间、本文工作包进度、逐消费者处理、Contract/ID/raw golden 变化及不变的业务 digest、两配置摘要和实际 cgroup/mount、每包运行/沿用来源、容器 image revision/source-tree/config digest/RootFS、真实输入与节点/日志 SHA、失败/UNKNOWN/容量限制、独审结果和资源释放。

后续编码会话先读取 AGENTS、三份 S0 工作区文档、本方案、S1a 详细设计及分组补充，再从 S1a-A 开始。不要重新讨论已确认业务边界，也不要直接开始 S2b/S4b。发现新的业务取舍会改变边界时再提出；一般实现修正由实施者处理并同步文档。

**当前完成状态**：详细设计、分组边界和本执行方案均已落盘，足以开始有明确范围的 S1a 编码。没有尚待 Owner 决定的设计选项；开发环境具体预算可由执行时现场状态确定，正式真实范围按既有 DC33 在验收准备时确认。独审与测试尚未执行，不能预填为通过。

2026-11-10 本次文档交接已将确认的阶段、分组边界和下一会话授权同步到三份 S0 来源文档，并新增[完整实施提示词](p7-s1a-implementation-prompt.md)。未修改 Accepted Contract、其他会话文件或产品代码，未提交、部署、推送、建 tag、连接测试节点或运行产品测试。本轮不触发镜像重建；产品基准/最后已有镜像 provenance 仍为 S1a 设计 §14 所列 P6 B，未将它 carried 为 P7 结果。
