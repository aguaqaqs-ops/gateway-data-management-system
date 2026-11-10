# P7-S1a 存储布局与资源配置详细设计

日期：2026-11-10。状态：**详细设计稿；产品未实施、未测试、未独立审核**。

依据：[S0 决议及补充授权](p7-s0-owner-decisions.md)、[总体设计](p7-design.md)、[执行计划](p7-execution-plan.md)。本会话只完成设计交接；Owner 已授权下一编码会话按 [S1a 执行方案](p7-s1a-execution-plan.md)完成 A–G 至本地 exit。本文确定目标和验证责任，不把文档落成当成产品实现/独审/验收；不修改 P6 验收要求或其他会话文件，不授权上线或推送。

2026-11-10 讨论补充：[处理组边界与设备测试副本设计](p7-processing-groups-and-test-extraction-design.md)明确组内共享状态、组间隔离，以及默认包含设备全部现存历史/审核/未完成任务的单向测试副本。下文 roots 与 worker 的共享范围按处理组解释；S1a 仍先验证默认单组、单 worker，不把分组/抽取功能记为已经交付。

编码执行入口：[S1a 实施执行方案](p7-s1a-execution-plan.md)。其中已定稿配置接线、开发验证样例、S1a-A–G 工作包及完成条件；独立处理组落在 S2b，全状态测试抽取/加载落在 S4b，S5 综合验收。本设计负责语义不变量，执行方案负责实施细节与阶段安排。

## 1. 来源、入口与 P6 退出后的复核

### 1.1 两类来源分别固定

三份 P7 文档以工作区实际文件为准；读取时均未提交。以下 SHA256 固定的是**本会话最初读取时的历史输入**，不代表 2026-11-10 补入分组/阶段/执行授权后的现值；新会话必须读取现有全文，不用旧哈希或 Git 旧版覆盖它们：

| 文档 | SHA256 |
| --- | --- |
| `p7-s0-owner-decisions.md` | `75a97bca3cec0641595262066641e321f41f09dcd8991dca6aa6853281578674` |
| `p7-design.md` | `5f905181ff64ef6e5d274e77fd64b9bd3f6dca4b998719c8447a32d099c3a875` |
| `p7-execution-plan.md` | `8ad486b55a87f9c839872ccf45988d5108ee044e131109d40332323517e0119b` |

本工作区 HEAD 为 `a300b16485bcad2f178aaccfe0c8adbb51b5ab83`，分支 `fe3b-evidence-04`，是 P6 exit 的祖先，**不能作为最终产品代码基线**。本文源码盘点以本地附注 tag `p6-exit` 指向的 `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`（下称 B）为准，使用 Git 对象及临时源码快照只读核对，未切换当前分支。B 的 `vnext` tree 为 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。

P7 产品代码的已复核起点为 B；实际获准实施时在 main 上核对 B 的后继变更，记录实际起始 SHA，并补盘点新增消费者。不得从当前较早的 FE 工作区覆盖或撤回 P6 改动。实际A入口已固定main后继`5ddd73b962`，B..该起点只有两份FE文档、vnext tree不变；新增consumer/摘要/Contract目标见[A入口](p7-s1a-a-entry-and-contract.md)。下文原盘点相对源码路径均指 **B 上的文件**；其中 `computation_cache.py` 等在当前工作区尚不存在。

已读取 P6 最终外部报告与独审，目录为 `/home/dev/gdds-s6-logs/final/b0fc25e881cb4ce39b1cc847bad92b4ccb06b809/`：

| 文件 | SHA256 / 结论 |
| --- | --- |
| `report.md` | `6cb574a183fe61b7188d7120f97cfffd60de0d1d6697c051f783769fb9b483a7` |
| `receipt.json` | `dd4220407a432c177690ca54ad07cbaa1bff78ac49378c5de61c921419c67b03` |
| `reviews/iii-h8-p6-exit-review-r1.md` | `df7cd22fe87b8c5220fdd765c9b8a45a2c778602d084803ab917f0df9040a3ad`；P6 EXIT_GO，与附注 tag 相符 |

这些是已有证据的只读复核，未重新运行任何旅程。P6 最终曾获准在 06 执行，不因此把该专项授权扩展到 P7；P7 节点分工仍按执行计划与 AGENTS。

### 1.2 资源与容量结论

| 项目 | B 与最终证据 | S1a 决定 |
| --- | --- | --- |
| 单 worker 配置 | N=1，E=34,359,738,368 B，reserve=8,589,934,592 B，M=25,769,803,776 B；单 active executor | 同盘起始样例保留此配置，W=K=1 |
| 代码可配置范围 | N 1–256；E 上限 48 GiB；M 上限 40 GiB；reserve 固定 8 GiB；M 必填 | S1a 显式统一配置，保留 E/M 上限与 reserve 安全下界；不自动上调 |
| t4 W1/W2 预约高水位 | 25,645,861,504 / 25,714,930,944 B，接近 M24 | 不因 RSS 低而缩小 M；不能推出两个 executor 的容量 |
| 同 worker 生命周期观测 | cgroup peak 965,079,040 B，进程 RSS HWM 680,247,296 B；与预约口径不同 | 供 S1b 记录来源类型，不充当内存预算 |
| 存储 | 输入 5,597,503 B；两次 tar 7,193,088 / 5,263,360 B；Dolt、IPC、计算缓存、staging 全量逻辑/物理容量多为 UNKNOWN | 无依据给出生产盘容量、scratch 峰值或设备数容量默认值 |
| 更大历史样本 | S3/S4 的 M40 及原失败/取消/UNKNOWN 各有适用范围 | 不把 M24 或 M40 宣称为所有 FULL、2×t4 或多设备负载的容量保证 |

S1a 定参数含义、关系、接线、拒绝行为和起始样例；目标单机总预算、服务 CPU/内存份额、磁盘容量和 S5 最终默认值仍依实际硬件及本轮观测选择。此处信息不足不改变 S0 边界，无需重问业务决议。

## 2. 设计决定与边界

1. 存储类别是静态逻辑位置。backend 对象有 durable/canonical/comparison/export 四个位置；scratch 不承载 ArtifactRef。repository 和 RS 私有产物仍由 RS 管理。
2. 采用**在 backend opaque artifact ID 中编码显式逻辑位置**的定位格式；不查找所有 root，不从用途、媒体类型或旧 ID 名称猜位置，不增加一张必须先提交的定位目录表。
3. 同一 ArtifactRef 只有一个物理归属。增加用途、Head/Attempt/READY/TTL owner 只增加引用，不能移动或复制该对象。转换格式或真正新生成的交付产物使用新 ID。
4. 目标 root 内 staging 完成 bytes、ref 及持久化后，以一次目录 rename 发布。独立 scratch 到目标 staging 使用有界复制；文件系统之间没有联合原子事务。
5. 挂载必须在进程启动前明确准备。缺失、错卷、只读、权限不足或运行期身份变化使受影响服务拒绝新工作，不创建替代 root，不退回系统盘。
6. 同一处理组的 backend/worker 共用相同逻辑布局与 control DB；不同组使用独立可写状态。RS 不把仓库卷挂给 backend。统计从各 owning adapter 获取窄观测，不能跨越此边界。
7. S1a 仅单 worker 闭环，W=K=1。多 worker 启动/租约、全局槽位和队列公平分别属于 S2/S3；仅增加配置字段不宣称已支持这些能力。

遵守[比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)及 [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：使用既有进程/DB/文件锁；不新增 broker、UID、sidecar 服务、quarantine/tombstone 或持久清理证明协议。目录中的 ref 是现有内容身份元数据，不是第二套业务完成记录。

## 3. 实际消费者盘点与目标归属

以下 `BE/` 指 `vnext/backend/src/gateway_backend/`，`RS/` 指 `vnext/repository_service/src/gateway_repository_service/`。分类须在 producer 创建 ID 时确定，reader 和 cleaner 只解析位置协议，不复制本表的业务推断逻辑。

### 3.1 backend 产物与读写链

| 实际文件 / 消费者 | 当前行为 | S1a 物理位置及责任 |
| --- | --- | --- |
| `BE/http/orchestration/multipart_upload.py`；`capabilities/source_package_staging/staging.py` | `put_stream` 接收上传；SourcePackage bytes/provenance 文档发布，恢复读原输入 | durable；接收 staging 同目标盘，已受理输入不得留在 scratch |
| `BE/capabilities/storage_projection/publish.py` | 发布 CanonicalizationManifest、projection/structural 元数据 | durable；与 Submission 恢复/审计权威对应，不因 JSON 小而放统计盘 |
| `BE/capabilities/snapshot_materialization/canonical_store.py`；`artifacts/canonical_table_store.py` | scope 内确定性 canonical ID，IPC put/open；index register/bind commit | canonical；保持 IPC profile、业务 schema/table digest 与 scope key |
| `BE/capabilities/snapshot_materialization/artifact.py` | raw Parquet wrapper 与 canonical IPC wrapper、rows/ref/manifest | canonical wrapper 与 IPC 在 canonical；raw 客户端 wrapper/Parquet 在 export。分别显式传 location，不能按同一 `_opaque_id("sta-manifest")` 猜位置 |
| `BE/application/canonical_metadata/{manifest_reader,table_access}.py` | 通过 bare artifact ID `get_ref` 读 durable manifest，精确 commit 惰性物化及绑定 Head | durable/canonical 依原 ref 路由；未加载的历史表不为换 root 预先物化 |
| `BE/capabilities/snapshot_materialization/client_parquet.py` | 本地临时 Parquet、内容 ID、export cache | export；临时 writer 使用 scratch，最终从文件有界导入 export staging，不再整文件 `read_bytes` 后复制 |
| `BE/capabilities/comparison/{artifacts,persistence,cache_codec}.py`；`BE/artifacts/computation_cache.py` | records、manifest、closure、缓存复用/重绑定 | comparison；manifest/member 的位置随 ref；恢复为本次语义生成的新对象仍归 comparison |
| `BE/capabilities/risk_evaluation/{_artifacts,persistence}.py` | risk content/manifest/closure 与缓存 | comparison；风险用途不自动提升为 durable，需长期保存的业务事实仍由现有业务记录负责 |
| `BE/capabilities/mutation_planning/_artifacts.py`；`application/pair_pipeline.py` | ChangeSet closure、project identity assessment | comparison；作为冻结输入时加强保护，物理位置不变 |
| `BE/application/checkpoints.py`；`preview_jobs.py`、`submit_jobs.py`、`history/compare_jobs.py` | checkpoint envelope、READY closure、canonical table-set closure、请求快照 | durable；引用的 IPC/records/export 留在原类别，整个 closure 的发布状态仍由 operation/checkpoint/READY owner 决定 |
| `BE/application/submission/import_builder.py`；`infrastructure/repository_write/import_publication.py` | 构造固定 BackendArtifactRef package，再上传得到独立 RepositoryArtifactRef，unknown outcome 复用 package/key | backend package/request facts 在 durable；RS 接收副本在 rs-artifacts。属于两个服务的两个物理对象，不能用 raw SHA 合并统计或重建新 key |
| `BE/capabilities/bundle_assembly/{_assembly,transport}.py` | 引用已有成员、生成/重写交付成员、manifest 与 closure；transport 重算 closure ID | 新 bundle manifest/closure 和新交付成员在 export；未改变 bytes/身份且直接引用的成员继续使用原 ref，不能为 bundle 用途搬盘。两端 ID helper 必须同步 |
| `BE/application/bundle_download.py`；`BE/artifacts/{bundle_download,tar_stream}.py`；HTTP download 路由 | 按 artifact ID 定位，headers 前核完整 closure，再逐成员流式输出，持有 read session | 保留流式 tar，不新增持久 tar；支持一个下载跨多个 root。鉴权仍先从业务 scope/结果绑定判断，位置编码不是授权凭据 |
| `BE/http/routes/upload_revisions.py`；`http/dependencies.py`；`bootstrap/composition.py`；`http/orchestration/multipart_stream.py`；`multipart_upload.py` | `mkdtemp` 未指定 dir；解析异常关闭当前 handle/rmtree，成功由 acceptance finally 清理（取消等待线程真正结束） | composition经WorkspaceHttpDependencies/route在parse前注入be-scratch能力；request/upload owner，禁止ambient TMPDIR或系统temp回退。共享 cap累计全部parts且保留原单part上限；无operation时不伪造。构造/解析/验证/发布/取消及ENOSPC均关闭/释放本次临时资源，不能在线程读取时先删输入 |
| `BE/capabilities/comparison/artifacts.py` `_write_arrow_parquet` | `SpooledTemporaryFile` 未指定 dir，超过内存阈值或要求fileno时可rollover到系统temp；已有writer/spool finally | 显式本operation scratch，原records/spool与temporary共享cap取严格边界；最终bytes仍计同M。写入/close/ENOSPC/取消失败不发表READY，所有出口关闭；残留按非活跃owner有界清理 |
| `BE/infrastructure/repository_read/http_arrow.py` | `NamedTemporaryFile` 默认写系统临时目录，消费 Arrow HTTP | 转入 backend/worker scratch；结束/取消关闭并删除，不能把 spool 当恢复依据 |

`bundle_assembly` 当前存在交付成员重写；本轮不顺带删除必要转换或许诺按 raw SHA 全局去重。相同 bytes、不同 ID 是两个对象；只有同一个 ID 被多用途引用时必须维持唯一归属。

### 3.2 定位、持久化、保护与清理消费者

| 文件 / 边界 | 必须同步的变化 |
| --- | --- |
| `BE/artifacts/{types,digest,validate,serialize,store,bounded_store}.py` | 一个位置 codec/constructor；四字段 ref 的严格 ID 校验；InMemory 与 filesystem 语义一致；`put_stream` 显式 location，拒绝未知位置 |
| `BE/infrastructure/artifact_store/{local_store,bounded_store}.py` | 所有 put/put_from_path/get_ref/locate/read_exact/open_buffer/verify_readable、mtime、删除、read/cleanup session 改为同一个 resolver；删除 `_validated_paths` 单 root 私有绕行 |
| `BE/infrastructure/control_db/{sqlite_canonical_tables,sqlite_snapshot_export_cache,snapshot_export_cache,computation_cache,sqlite_protection}.py` | 保存完整新 ID；缓存行与 member refs 一致；TTL/uses/index miss 不覆盖强 owner。B 已有 computation cache，不能以当前 FE 工作区缺少该模块而漏改 |
| `BE/infrastructure/control_db/{sqlite_operations,sqlite_workspace,sqlite_submission}.py` 及 `schema.py` | operation artifact_refs、source bindings、bare closure/manifest ID 与 nominal ref 的序列化/反序列化全部验证新格式；不做旧 ID 双读 |
| `BE/application/submission/{artifact_refs,artifact_release,finalize_transaction}.py`；workspace/Preview、archive Head 事务 | BackendArtifactRef 与 RepositoryArtifactRef 保持名义类型区分；T1 移交、finalize/abort 释放、Head CAS 移交、READY closure 保护不能降级 |
| `BE/bootstrap/{composition,operation_worker}.py`；`settings.py` | HTTP、worker、恢复、下载和维护命令注入同一布局；两个 worker composition 入口均覆盖；不存在从某个旧 `artifact_root` 隐式创建新 store 的路径 |
| `BE/infrastructure/control_db/computation_cache.py` | 保留 root borrow → DB pin → 文件验证的锁序；`ControlDbComputationCache.store` 在 read_session 内写产物，禁止新增 SH→EX 升级死锁 |
| backend cleanup | B 有 `classify_cleanup/delete_eligible` 和 cleanup settings，源码未发现完整周期扫盘入口。S1a 要交付一个显式、有界维护入口，调用这些保护 owner；不能把已有字段误称为已有后台 GC |

### 3.3 Repository Service 与部署消费者

| 实际文件 / 消费者 | 当前耦合与 S1a 目标 |
| --- | --- |
| `RS/layout.py` `DurableLayout` | 单 `data_root` 派生 control/versioned/staging/artifacts/service-state/provider，全局同 filesystem 断言。改为显式多位置；只要求每一原子发布对的 staging/target 同 filesystem |
| `RS/settings.py`、`runtime.py`、`provider_lifecycle.py` | DB 路径、启动锁、provider HOME、磁盘 admission 均依赖 root。分别绑定 rs-metadata/repository/rs-scratch/rs-artifacts；保留单 RS 服务锁和原恢复语义 |
| `RS/create_repository/{command,adapters,visibility}.py`、`mutation_reconciliation.py` | 新库 staging、rename 与崩溃核对 | 建库 staging 留在 repository root，不能放通用 scratch 后跨盘 rename；核对只看此 root |
| `RS/upload_artifact/{command,admission_pin}.py`、`artifact_{layout,root,cleanup,cleaner,retention}.py` | artifact ready/staging、dirfd/pin、pending cleanup、孤儿扫描 | 整套 rs-artifacts 独立挂载；其 ready/staging 同盘，内部拒绝 symlink/额外子挂载；不复用 backend 的 ID 或清理器 |
| `RS/versioned_import/{submission,command,worker,provider,recovery,admin}.py` | 入队/导入 headroom、import staging、恢复 probe/digest 与受控管理 | 临时展开/probe 可归 rs-scratch；RepositoryArtifactRef 的唯一字节、事务/恢复权威仍在 rs-artifacts/rs-metadata/Dolt。逐项确认可重建后才移动 temporary 文件 |
| `RS/snapshot_admin.py`、`versioned_import/admin.py` | 离线 bind_existing、service lock、路径限制假定一个 root | 读取相同配置并显式枚举 owner roots；原管理动作保持可用。已有快照如涉及多 root，在服务停下且锁定后收集/恢复一致集合，不进行在线跨盘快照，不新增备份平台 |
| `RS/providers.py`、`process.py` 的 `DoltRunner` 及 `provider_lifecycle.py` | 查询临时目录、HOME/TMPDIR、子进程生命周期 | provider 配置/HOME 在 rs-metadata，纯临时文件在 rs-scratch；关闭 versioncheck 的既有初始化规则保留 |
| `RS/capacity.py`、`admission.py`、`versioned_import/submission.py`、`upload_artifact/command.py` | 原 `layout.root` free-space 检查与并发 admission | 各动作检查实际写入位置，同盘合并预算；不只检查 metadata 盘；既有并发数不因换 root 扩大 |
| `RS/storage.py`、`filesystem.py`、`workflow.py`、matrix/target-gate | 含 P2 测量专用布局及全树扫描 | 只适配真正调用的新布局接口；不修改 P6 历史证据口径。`storage_snapshot` 的全量 `rglob/sorted` 不直接用作 S1b 在线查询 |
| `vnext/repository_service/docker-entrypoint.sh`、两个 Dockerfile、`vnext/deploy/compose*.yaml`、deploy README、Compose harness | entrypoint 当前从 DATA_ROOT 拼 artifacts，初始化会建目录/chown；worker 当前固定 mem_limit 与环境值 | 先核挂载，再按明确 root 初始化各自子目录；禁止跨 root 递归 chown；Compose 同源配置、实际 cgroup/mount 验证与 container gate 同轮更新 |

## 4. 位置协议与目录布局

### 4.1 BackendArtifactRef 定稿

保留 `ArtifactRef = {artifact_id, media_type, size_bytes, raw_sha256}` 四字段形状。**改变 artifact_id 的合法格式及生成规则**，不是保留旧身份兼容：

```text
a1:<location>:<token>
location = durable | canonical | comparison | export
token = 64 个小写十六进制字符
```

`a1` 是位置编码版本，不是业务 digest 版本。最大 ID 78 字符，仍在现有 128 字符上限内。token 定义为 `hex(SHA256(JCS(["gateway-artifact-id-v1", location, kind, identity_payload])))`；确定性对象的 payload 使用现有完整身份输入，随机对象使用新生成的 128-bit nonce 十六进制串。kind 使用各 producer 的固定类型名，不接受调用方任意指定。codec 必须接收 `ArtifactLocation` 枚举和对象身份，业务模块不得自行拼路径。canonical payload 保留 repository + projection/schema/row-count/table-digest/mapping-version 的身份输入，不能因新 root 丢掉 scope。

`get_ref(artifact_id)` 解析固定位置段一次，选唯一注册 root，然后由完整 ID 的 SHA256 得到内部对象路径。未知位置、旧格式、路径字符、超长 ID、同 ID 不同 ref 都拒绝；不尝试其他 root。这个段是明确的逻辑定位协议，不是对 `canonical-table:`、`media_type` 或文件扩展名的启发式猜测。调用方把整个 ID 当作 opaque token，不解析它来决定权限或业务状态。

不添加 locator DB 的原因：已有 HTTP/result/checkpoint 大量只持有 artifact ID，显式 ID 已足够定位；无需让每次文件写入再与全局索引完成双重提交。不新增 `location` ref 字段的原因：该字段将与 ID 中的唯一位置重复，并迫使 bare ID 查询另找目录。若将来需要同 ID 在线迁移、多位置副本或远程存储，再重开协议，不预建本轮不用的间接层。

同一逻辑位置改变物理挂载路径时 ID 不变；同一对象不能改 location。`RepositoryArtifactRef` 是 RS 独立协议，保持原 ID/schema，不套 `a1`。名义类型适配器必须分别校验，不能用宽泛字符串验证器把两者混用。

影响 ref/ID 的 wrapper、checkpoint、bundle closure 和 transport digest/golden 同步更新。表业务 digest、comparison 规则、canonical cell encoding、Dolt commit 语义不因路径变化修改；新 ID 不能混进业务摘要新增输入。Comparison Bundle 原有“artifact ID 不进入 semantic digest”的规则保留；变化的 serialized bytes/raw SHA 与语义摘要分别核对，不能全量重录 golden 掩盖业务差异。引用 ID 已参与的摘要随目标载荷重新生成，不承诺与旧 golden 相等。同一新版本在同盘与分盘配置下必须得到相同身份/摘要。A已按实际源码补齐[摘要影响表](p7-s1a-a-entry-and-contract.md#4-摘要与-golden-边界)：SnapshotTableArtifact.artifact_content_digest排除row artifact_id，固定bytes/descriptor时保持；含ref的manifest/closure raw SHA及surface/bundle完整性可传递变化；ConfigurationFacts及Archive绑定摘要包含source ID，必须沿原公式重算，不能删绑定或全量重录golden。

### 4.2 部署位置表

下列 slot 在每个处理组内各有一份；不同组的容器内路径可以相同，宿主目录/volume 必须独立。`environment_id` 与 `group_id` 共同限定运行命名空间，root marker 记录其归属。测试复制保持业务 ArtifactRef 不变，为目标环境重新准备挂载 marker；不把源环境的 marker 当作目标卷身份，不向 ID 编入物理组位置。

| 配置 slot | 示例容器路径 | 内容 / 挂载进程 |
| --- | --- | --- |
| `be-durable` | `/var/lib/gateway/storage/durable` | backend/worker 的 SourcePackage、durable manifests、checkpoint/package；backend 与 worker RW |
| `be-canonical` | `/var/lib/gateway/storage/canonical` | IPC/wrapper；backend 与 worker RW |
| `be-comparison` | `/var/lib/gateway/storage/comparison` | diff/risk/ChangeSet/cache；backend 与 worker RW |
| `be-export` | `/var/lib/gateway/storage/export` | Parquet、bundle 元数据/交付成员；backend 与 worker RW |
| `be-scratch` | `/var/lib/gateway/storage/scratch` | 按服务实例/执行尝试的工作目录；backend 与 worker 可共享挂载但目录分别所有 |
| `be-metadata` | `/var/lib/gateway/storage/metadata` | control.sqlite3 及 WAL/SHM；S1b 独立可丢弃 telemetry DB 子目录；backend/worker RW |
| `rs-repository` | `/var/lib/gateway/rs/repository` | versioned Dolt 库、建库 publication staging；只给 RS |
| `rs-artifacts` | `/var/lib/gateway/rs/artifacts` | 各库 RepositoryImportArtifact 的 staging/ready；只给 RS |
| `rs-scratch` | `/var/lib/gateway/rs/scratch` | 可重建 import 展开、query/probe spool；只给 RS |
| `rs-metadata` | `/var/lib/gateway/rs/metadata` | RS SQLite/WAL/SHM、service lock/layout、provider HOME/config；只给 RS |

metadata/telemetry 逻辑上分开统计，不要求为首版再加一个挂载。control DB 的 journal/SHM 与主文件必须同一目录/介质；不能把 WAL 单独引到 scratch。业务配置、secrets 继续只读单独挂载，不属于 cleanup 管辖。

同盘样例使用同一宿主文件系统下的十个互不嵌套目录；分盘样例把类别目录分别 bind 到目标本地介质，backend 与 worker 容器路径一致。类别目录必须不同且不得彼此包含；“同盘”不等于两个类别共用同一个对象命名空间。RS 与 backend 的 durable 可以在同一物理盘，仍须不同目录、不同 owner。

Backend 每个 artifact root 的目标结构为：

```text
<root>/                         # 预先准备的挂载与身份
  .gateway-storage.json         # 仅初始化时写入的部署/slot 标识
  .staging/<nonce>/             # 尚未发布；临时持有 flock
      payload
      ref.jcs
  objects/<id-hash[0:2]>/<id-hash[2:4]>/<id-hash>/
      payload
      ref.jcs
```

ref 与 payload 同目录一次发布，替代现有“payload rename 后再写 `.ref.jcs`”两步可见路径。不存在旧布局 fallback。RS 继续自己的 ready/pin/cleanup 结构，只移动配置的根，不复刻 backend 格式。

### 4.3 Adapter 接口责任

`StorageLayout` 是只读的 slot→已验证 root 映射；`ArtifactLocation` 和 ID codec 位于 artifact 边界，Path 与 fd 只属于 infrastructure。保留现有 `put(bytes, ref)`、`get_ref(id)`、`locate(ref)`、`read_exact(ref)` 和 `open_buffer(ref)` 调用语义，内部统一走 resolver。`put_stream(location, kind, stream, declared_size, declared_raw_sha256, media_type)` 必须显式接收 location；不从 kind 映射位置。

为实际文件 producer 提供 `put_from_path(source, ref, checkpoint, byte_limit)` 的有界内部接口；source 只接受本服务 scratch handle 提供的普通文件，失败保持 source，成功是否删除由 producer 所有权决定。`open_scratch(owner_context, byte_limit)` 返回 context-managed handle，关闭时清理自身文件；不向 domain/HTTP 暴露 Path。`read_session()` 为需要多位置 closure 的旧调用者提供固定四 root borrow；单对象 reader 可借用单一 root。清理枚举与 S1b 文件描述仅在 infrastructure 提供 bounded page/stat 接口，不扩展业务 `ArtifactRef` 载荷。

## 5. 挂载、配置一致性与失败行为

### 5.1 一个配置来源

新增版本化部署配置 `storage-layout.json`（部署文件，不进入业务载荷）：包含 `schema_version=1`、`environment_id/group_id`、每个 slot 的绝对 `path`、预期 `storage_id`、挂载模式及容量策略。backend、worker、RS 只读挂载同一版本，各自只接入有权限的 slot；配置加载器拒绝重复/未知字段、缺项、相对路径、相等/嵌套 roots 与 symlink 祖先。宿主 source/filesystem 及两个配置文件的具体字段、加载入口和渲染职责按执行方案 §3.1。

Compose 渲染与启动预检读取同一配置；容器内对实际 mount、UID/GID、读写性重新核验。backend/worker 的四类 root 与 metadata 配置摘要必须一致，可在既有内部 readiness/preflight 边界比对；本机服务记录实际摘要及 slot 状态，公共 HTTP 不回显绝对路径。无独立配置服务器、热更新或外部写接口。

同组摘要比对使用 `be-metadata/.gateway-runtime-configuration.json` 这一可重建普通文件：仅 backend 显式启动在 root/marker/有效身份及小文件写探针通过后原子发布 environment/group 与两份 JCS 规范化摘要；worker 不创建。Compose 按 backend healthy 后启动 worker；缺失、损坏、组或摘要不符均在 worker startup/claim 前拒绝。运行期 backend/worker 仅有界、no-follow 读取并比对，拒绝 symlink、目录和子挂载，不从 readiness/请求自动修复。停服更换配置后 backend 启动可替换旧、缺失或损坏的普通记录。此记录不证明存活、租约或业务完成，不新增 epoch/DB/schema，也不阻断安全离线维护或低水位 cleanup。


旧 `GATEWAY_BACKEND_ARTIFACT_ROOT`、worker 对应字段及 RS 单 `DATA_ROOT` 隐式布局入口由目标配置替代，不保别名或优先级回退。测试 fixture 直接构造同一 typed layout，不绕过 root 校验；仅纯内存 store 不要求文件系统。

### 5.2 初始化与缺挂载检测

单看“目录存在/可写”不能发现宿主数据盘未挂载后落到系统盘。采用两层最小检测：

1. 部署预检核宿主挂载来源与预期本地 filesystem（分盘配置显式指定设备/UUID），再建立 bind；使用不自动创建 source 的 long syntax。禁止在启动服务时为缺失 source 执行 `mkdir -p`。同盘样例也明确它依赖哪个宿主 filesystem。
2. 一次显式初始化在已核对的空目录写 `.gateway-storage.json`，包含 environment_id、group_id、slot、随机 storage ID、布局版本；service 启动只读取，不自动补写。每个容器校验目标确为配置要求的 mount、marker 匹配、无 symlink、普通目录、有效 euid 可读写，并以小文件 create/fsync/unlink 验证实际写权限。标识是防错卷措施，不是秘密或业务 proof。

初始化由部署管理动作完成；既有 RS entrypoint 仍可准备已验证 root 内的必要目录/权限，但必须先验证挂载，不自动把空底层目录初始化为新库。不得随启动递归改他人目录权限。网络存储不在支持范围，metadata 需支持 SQLite locking/WAL，artifact root 需支持目录 flock、fsync 和本地 rename。

启动捕获各 root 的 fd、device/inode/mount identity；操作入口及 readiness 检查配置路径仍对应该 root。运行期卸载/换卷后不重新解析到新目录继续写；已打开 fd 也不能成为继续受理新工作的理由。恢复挂载后重新预检/重启，禁止在线换盘。此保证针对协作运维/I/O 故障，不建立恶意同 UID 换名的 syscall 证明。

### 5.3 失败结果

| 故障 | 行为 |
| --- | --- |
| 启动缺 root、marker 不符、布局不一致、权限或只读 | fail closed；readiness 不成立；worker 不 claim；不创建默认盘副本 |
| 运行期 root 不可用 | 受影响服务停止新接收/claim，readiness 表达 storage unavailable；已有只读请求只有在所需 roots 健康时继续；liveness 不因磁盘低水位伪称进程死亡 |
| 临时容量/低水位拒绝 | 拒绝新工作并不 ready；不锁存为身份失效。RS 保持有界 cleaner 可运行，容量恢复后重新准入；启动先做身份/权限预检、原有安全 reclaim，再核容量进入 ready |
| 单个可选 cache 条目缺失/损坏、root 本身健康 | 保持既有 cache miss/discard/recompute 路径；不能扩展为强保护输入丢失可忽略 |
| PREPARED Attempt 的冻结文件缺失 | 按 Canonical Storage §5 稳定失败；不回原输入/parent/新 ruleset 重建，不推进 main |
| ENOSPC、EDQUOT、EIO、fsync/rename 失败 | 当前写入失败，不发表成功引用/READY；清理本次 staging 或记录残留供有界清理；不降低校验、不自动加容量 |
| 下载前检查失败 | headers 前沿用现有错误契约；发送过程中失败则中止流、释放 read session，不发送伪造完整 tar 尾部 |
| Repository effect 后存储/响应失败 | 保持 UNKNOWN 查询与恢复；不能把 HTTP 失败解释为无提交，不能用新 package/key 盲重放 |

内部错误区分 invalid layout、root unavailable、capacity rejected、artifact unavailable、integrity mismatch。映射到现有错误体系；如需新增 HTTP code，实施时在 owning OpenAPI 定义稳定 code 与 retryable，磁盘路径只留受控诊断。S1a 不借此引入 S3 队列状态机。

## 6. 写入、跨盘发布与恢复屏障

### 6.1 Backend 单对象发布顺序

1. 校验 typed ref/目标 location、输入 owner 及 root 健康。保护需要的对象仍沿既有流程先登记保护；不能等发布完才补 Attempt/READY 的生命周期责任。
2. 在目标 root `.staging` 下创建独占随机目录，持有目录 fd 的 flock 直到完成或失败。stream/bytes 直接写目标 staging；scratch 来源只接受服务生成的普通文件，不接受 HTTP path。
3. 从 scratch 复制时以固定小块（沿用 64 KiB）读取，累计长度、计算 raw SHA；超 declared size 或当前输出预算立即失败，支持取消/deadline。源文件保留到发布成功；不调用跨 filesystem `replace`，不以 `shutil.move` 的隐式 copy/delete 充当原子操作。
4. 验证 size/raw SHA，写完整 `ref.jcs`，fsync payload/ref 和 staging 目录。复制本身做流式 hash，不再额外整文件分配；格式/业务验证由原 producer/reader owning Contract 承担。
5. 在已持有 root read borrow 的条件下，用同盘原子、不覆盖目标的目录 rename 将 staging 发布到唯一 `objects/.../<hash>`。Linux adapter 使用 `renameat2(RENAME_NOREPLACE)` 的明确语义，能力缺失在部署预检拒绝，不以“先 exists 再普通 replace”模拟。若并发已存在，核对完整 ref 与有效 bytes，相同则幂等返回，不同则冲突。发现不完整既有目录报告 integrity failure，修复走明确的 cache invalidation/cleanup 后重建，不直接覆盖强保护内容。
6. fsync 目标父目录及 staging 父目录，成功后返回 ref；再由原 control DB CAS/事务发布 checkpoint、cache index、READY 或业务引用。目录 fsync 失败不能返回成功。最后清除本次 source/scratch（按调用者所有权）与临时句柄。

不使用跨目录 DB+filesystem 两阶段提交。进程在 rename 后、DB 引用提交前崩溃，只会留下完整孤儿；在 rename 前崩溃，只留下不可见 staging。未知写入结果以同 ID 检查/重试，不分配新 ID 伪造新对象。业务提交成功不依赖 S1b 统计写入成功。

多对象 closure 不是跨 root 原子 rename：逐对象完成发布/验证，全部需要的引用受保护，最后提交现有 READY/checkpoint 屏障。失败前缀是未被 READY 引用的完整对象，按其 owner/TTL 收尾；任何不完整成员都不得获得 READY。提交/归档的 T1、fixed package/key、Head CAS 屏障不变。

已有完整 ref 的丢失/损坏与未完成首次发布分别处理。对 owning Contract 明确允许从精确 accepted commit 回填的 canonical 派生对象，保留专门修复入口：先在目标 staging 完整生成并校验，关闭本次 read handles/SH borrow，再取得所属 root 独占 borrow，重核身份与恢复资格、替换损坏目录，保留全部保护记录；中断后仍按同一 exact commit 回填。不在 read_session 内升级 EX；锁不可得则有界重试。它不能用于 T1 后尚未具备恢复资格的冻结输入，也不是 cleanup 删除 protected artifact 的例外。普通 `put` 不自行决定恢复资格或覆盖损坏内容。

### 6.2 锁序与读者

root borrow 统一按 `durable → canonical → comparison → export` 顺序取得，去重后释放；需要多 root 的下载/cache 可在读取 manifest 前借用全部四个 root（固定上限四个），避免动态发现成员时反向加锁。无需为优化四个锁引入持久租约表。

所有读取、发布、pin/保护建立在 root `LOCK_SH` 下；单对象删除在所属 root `LOCK_EX|LOCK_NB` 下进行。发布不升级 root EX：并发发布由不可覆盖的完整对象目录 rename 仲裁。这样 `ControlDbComputationCache.store` 的既有 read_session 内写入不会死锁。嵌套 read session 由组合层复用或有明确引用计数，不重复反向借用。

锁序固定为 root borrow → control DB 短事务；DB 中核强保护/TTL 后执行必要的单对象删除临界区，保护新增也遵守相同顺序，避免“检查未保护后同时新 pin”的竞态。不得在 DB 事务内复制、hash 大文件或扫描目录。跨 root 的保护列表先借齐有序 roots，再做原子 DB 移交；读者 lifetime、mapping、Arrow/Rust 借用关闭顺序沿用现有 Contract。

### 6.3 RS 发布与恢复

RS artifact staging 与 ready 放同一 rs-artifacts root，继续使用既有 upload admission pin/发布协议。建库 staging 与最终 versioned 目录放同一 rs-repository root。删除当前“所有 layout components 必须一个 filesystem”的断言，换成这两个发布对及 SQLite journal 的精确约束。

普通 import 展开文件可在 rs-scratch；其来源 package、操作记录、Dolt 真实提交结果不能在那里保存唯一副本。import recovery、mutation reconciliation、离线 admin 全部使用配置后的 layout；任何 recovery 路径需要重新获得源文件时沿已有 frozen package/ref 获取，不拿 scratch 存在与否断言 effect 已发生。Dolt 目录绝不作为一般 artifact 从 scratch copy 后替代在线库。

## 7. 清理与空间有界性

### 7.1 保护优先，类别不决定可删

| 对象 | 保护权威 / 可删条件 |
| --- | --- |
| durable 原输入、CanonicalizationManifest、Submit package/checkpoint | 原 Workspace/operation/Attempt/Submission owner 与保留策略；目录名 durable 不代替策略，也不允许统一 TTL 清空 |
| canonical IPC/wrapper | 有效 Preview、T1 Attempt、当前 BaselineHead 强引用；全部强引用释放后按既有 TTL；旧 commit 可派生数据仅在 Contract 允许时按精确 commit 回填 |
| comparison/cache | cache TTL/uses 与本次 operation 强 pin 分开；cache index 被 prune 不能释放 Attempt/READY 引用 |
| export/bundle | READY 完整 closure 与现有缓存 TTL 分开；下载持有 read session，cache miss 不能使 READY 静默失效 |
| RS artifacts | RS reservation/import operation/TTL/cleanup owner；backend 不删除或扫描 RS 路径 |
| scratch/目标 staging | 无唯一恢复事实；仅在 writer/consumer 无有效持有且超期后删除；进程仍活跃但目录较旧不能按时间删除 |
| metadata/Dolt | 不进入 artifact sweeper；control DB 无容量淘汰；Dolt GC 仅由 RS 已有管理边界执行 |

backend 显式维护入口按类别 round-robin，每批最多沿用 32 个候选；目录遍历增量推进且不跟 symlink/子挂载，不一次 materialize 全树，不因某 root busy 反复扫描它饿死其他位置。只识别本版本合法对象目录及 staging；未知形状/损坏 ref 列为 manual review，不能按文件名推断可删。单个 root 缺失时跳过并报告，不把“扫描不到”当作已删。

清理执行时重核当前保护和期限；持有 read/download 时返回 retryable，不删除。只清理符合条件的已发布对象/本系统 staging，目录删除不越出配置 root。幂等删除保留 DELETED/ABSENT/RETRYABLE_FAILURE 语义。cache 索引残留按现有 miss/prune 修复，不增加持久删除 receipt。

scratch/staging 目录以现有 operation/step/attempt 或上传接收上下文关联，并持有进程级 flock；orphan 清理必须先取得非阻塞独占锁、核实际 active owner，再按 grace/TTL 删除。进程退出自动释放锁；业务恢复仍只信 operation DB。初始孤儿宽限采用既有 24h TTL，手工排空后的显式清理可立即处理确认无 owner 的目录，不造新后台清理协议。

### 7.2 预算与低水位

每个实际 filesystem 一份容量观测/策略：以本机 filesystem identity（同宿主 `st_dev`，结合 mountinfo；bind mount 不重复算）分组，使用 `statvfs` 的可用块和 inode。共享盘的 free bytes 只记一次；slot 级展示可以引用同一 filesystem，不相加。thin pool、宿主快照/压缩与 guest allocated bytes 分开，guest free 不证明宿主 pool 有余量。

新写入的最低准入条件：`available ≥ max(min_free_bytes, total × min_free_fraction) + known_write_headroom`，并核可用 inode。known headroom 至少含目标完整 staging 大小、该 filesystem 尚需保留的源/工作副本及元数据余量；不同 filesystem 分别核算，同盘的同时需求相加，不能每个目录重复消费同一余量。已存在 source 已体现在 available 中，不再扣两次。无法精确预知的输出必须有显式上限，不能把估计当作保留成功。

S1a 给所有文件 writer/stream/spool 显式单对象与每执行尝试 temporary bytes 上限；优先复用现有 upload、展开、bundle、export 与 kernel 输出限制，通过同一执行上下文累计，溢出安全失败。原生子进程临时写入不能靠 Python 计数声称硬限制，需使用可用的 filesystem quota/受限临时卷或明确部署容量边界并监测；无法强制时如实标注“水位检查＋ENOSPC”，不能宣称有精确磁盘预留。

B 已有可直接沿用的单项上限：backend 上传压缩 256 MiB、展开 1 GiB、8,192 entries、path 1,024 bytes；client Parquet 单文件 1 GiB；bundle manifest/closure JSON 各 16 MiB；RS 上传 256 MiB、展开/tar stream 各 4 GiB。它们是不同阶段的界限，不能互相替代，S1a 不顺带放宽。新增 `scratch_max_bytes_per_attempt`、`staging_max_bytes_per_object` 及 backend filesystem 水位作为部署 profile 必填项，无隐式无限值；实际输出同时受 producer 原上限和配置 cap 限制，较小 cap 引起的资源拒绝不是处理成功。开发验证样例按执行方案 §3.2，未测的生产容量与最终默认值留给 S5，focused 小型 profile 只能证明自己的范围。

现有 RS 起始水位为 5 GiB、10%，import headroom 1 GiB；在分盘后应用到真正的写盘，作为保守配置样例，不是容量验收结论。backend 同类水位与 scratch/output cap 在部署 profile 显式填写，不能根据 t4 压缩文件大小推导。`min_free_fraction` 在 (0,1]，字节/条数上限正整数且有系统可表示上界；同 filesystem 配置冲突拒绝启动。低水位不通过删除保护数据来解除。

S1a 实现 root 检查和实际写入失败边界；上传、队列/executor/RS 的全局预约与选择性暂停归 S3，不能用本节预检查冒充并发容量预留。本节所有上限与拒绝结果均进入 S1b 配置关联，资源拒绝不计成功容量样本。

## 8. N/M/E/reserve/W/K 的统一配置

使用一份静态资源 profile 驱动 typed settings 与 Compose 环境、mem_limit/cpus/replicas；启动记录有效值和非敏感摘要。保留现有 worker 字段语义，去掉“环境声称一个 E，Compose 固定另一个 E”的双来源。租约、心跳、claim_limit/max_in_flight 和 drain 固定值不随资源 profile 任意开放。

| 参数 | 单位、校验与生效 |
| --- | --- |
| N / `kernel_threads` | int，1–256，不接受 bool/小数/NaN；启动时传入 kernel，一次执行中不变 |
| M / `kernel_memory_budget_bytes` | 显式 int bytes，0 < M ≤ 40 GiB 且 M ≤ E−reserve；缺值拒启；不是 RSS 或 cgroup hard limit |
| E / `memory_envelope_bytes` | int bytes，reserve < E ≤ 48 GiB；worker 容器 `memory.max` 等于 E；祖先 cgroup 更紧时拒绝该 profile |
| reserve / `memory_reserve_bytes` | int bytes，8 GiB ≤ reserve < E；S1a 可显式增大以留运行余量，不低于 P6 已确认下界，不按 RSS 自动调小 |
| W / worker_count | 正整数；S1a 必须为 1。S2 才允许受控 replicas>1 |
| K / active_executor_limit | 正整数且 K≤W；S1a 必须 K=W=1。S2 优先 W=K，W>K 需另有原子可恢复槽位 |
| worker CPU limit | 部署 profile 显式声明 quota/cpuset 或可用 CPU 上界；有 quota 时 N≤floor(有效 quota 核数)，有 cpuset 时 N≤有效集合大小；缺省无限 quota 不能假装已隔离 |
| 整机 usable memory / shared reserve | 部署预检核 `W×E + backend_limit + RS/Dolt_limit + OS/其他共享余量 ≤ 实际可用预算`；有祖先 cgroup 时也受其约束；SQLite/page cache 按所属进程/容器计入，不能在公式里重复计数 |

CPU 还包括 Arrow、Python、RS/Dolt、上传和后台工作；`K×N` 是 kernel 的规划量，不是整机总线程数。资源 profile 分开记录非 kernel 服务份额；总 CPU 不超配作为保守部署原则，但不据此承诺性能。S1a 不自动探测并增加 N/W，不照搬测试 workers=4/48。

上表 W/K/E 为组内参数。多个处理组并存时，整机预算将各组 `W×E` 与各组 backend/RS 份额相加，再加一次宿主共享余量；测试组同样计入。默认单组公式不能被每个组分别用来重复承诺整台机器容量。

容器部署启动预检比较渲染值与真实 cgroup v2 限制（memory.max、CPU quota/cpuset、swap 策略）。本地 host 运行没有 cgroup 时明确标识无硬 envelope，不作为容器资源隔离通过；正常部署不得把只验证环境值当作实际限制。swap 如被允许必须显式配置/记录，不计入 M 或宿主可用物理内存。

有效配置只在排空/重启生效，包含 storage layout/resource profile 的稳定摘要供 S1b 关联。预检不尝试修改宿主控制组或扩容；容量不足报告配置不可运行。保守起始样例 N1/M24/E32/reserve8/W1/K1 与后续 S5 经验证的默认值分别标记。

## 9. 为 S1b 提供的统计归属边界

S1a 提供可定位、可枚举、可关联的事实，不在发布热路径上创建完整统计数据库或 API。位置编码只表达物理类别，不编码 repository_id；否则多用途/共享对象会被误计成独占。

| 信息 | S1a 生产/保留位置 | S1b 消费要求 |
| --- | --- | --- |
| 物理对象 key | 组内 `(service_owner, artifact_id)`；跨组加 `(environment_id, group_id)`；RS 用自己的 repository/artifact identity | backend 同 ID 在一组内只计一次；相同 SHA 不合并两个真实副本；BE→RS、源→测试传输副本分别计 |
| 逻辑大小/格式/位置 | ref 的 size/media/raw SHA、解析出的 location、对象发布 mtime | object logical bytes 与 ref/目录元数据开销分列；mtime 不当业务创建/commit 时间 |
| 物理大小 | owning adapter 有界 `lstat/fstat`，可用时 `st_blocks×512`，采集窗口 | 跨 root 按 `(filesystem, inode)` 去重硬链接，区别 symlink/未知；reflink/thin pool 无法精确分摊，不假装 exclusive bytes |
| repository 归属 | canonical key/cache key、snapshot export cache、computation cache uses、Workspace/operation/Attempt/Submission/Head/READY 的既有关系 | 一个对象引用集合；区分单库独占、多个库共享、全局及未归属。保护 owner 不等于设备 owner，不能只统计当前 pins |
| 任务/尝试 | 既有 operation/step/attempt、upload/submission；scratch 上下文；发布事件可带关联 ID | 创建者与使用者分别记录；重试不把同物理对象重复累计；缺失关联为 unknown，不从文件名猜设备 |
| filesystem | slot→实际 filesystem 的运行期映射、free/inode 窗口 | 同盘 free 一次；跨服务容器的 bind 需要部署侧关联同宿主 filesystem，不将容器 mount ID 当全局 ID |
| metadata | BE/RS DB、WAL/SHM、provider config；telemetry 独立子目录 | 全局列出，不按设备数均分；telemetry 失败/满额不影响 control DB 事务 |
| RS 写入窗口 | import 在首次实际写库前/结果确定后提供观测接点，绑定 repository/operation/前后 commit；包含失败尝试 | 测量由 RS 负责，backend 不挂库；after−before 可负、可受后续写入/维护干扰；不可得则 null/unavailable |

S1b 建立 derived 对象/引用投影时，至少能表达 `object_key/location/repository_refs/purpose_refs/protection_status/observed_at/completeness`。可在现有事务后订阅内部发布/引用变化或从有界 SQL 页面重建；统计记录失败不得使既有业务事务回滚。无统计行不阻塞 get_ref；统计发现 orphan 不授权删除。失去业务关系后的对象可以转为“未归属”，不为补计费来源强加 durable lineage。

设备引用量允许一份对象被多个设备分别引用；设备独占量＋共享量＋未归属/全局量才与去重物理总量对齐，用途标签可以重叠而物理类别不重叠。IPC 同时是 Head 与 Preview 输入只计 canonical 一次；comparison records 同时进 cache/READY 只计 comparison 一次；转成 Parquet 是新增 export 对象，不能把导出大小当作 IPC 释放量。

只读查询 DTO、授权/分页/版本、采样周期、曲线预算/保留以及缺失/重置语义由 S1b 定稿；本文只要求配置关联与上述数据来源可用，不提前建设接口。任何 HTTP 查询不得同步递归扫描 root。逐任务内存峰值和共享 RS/cgroup 观测分别保留范围，沿用 P6 已确认的预约与 RSS 区别。

## 10. 调整挂载的运行操作

仅支持排空或停服后调整，不支持在线换盘、每设备选盘、自动冷热移动。

1. 停止新投递/受理，排空 worker 与 RS 写入，确认无 active upload/download、Attempt 执行和未定 effect。未定 effect 先沿既有恢复查明；不能以换盘清空问题。
2. 停 worker/backend/RS 及清理/统计任务，取得各服务既有独占锁；记录当前配置、版本和仍需保留的对象范围。全部相关进程停下后复制，不能 live copy SQLite/WAL 或 Dolt 正在写的目录。
3. 对要移动的位置复制完整目录集合到新本地介质，保留 IDs/ref、权限和必要元数据；DB 连同实际存在的 WAL/SHM 作为一致停服集合处理。采用标准复制工具核数量/字节/摘要；不建迁移状态机，不改物理类别编码。
4. 核对新挂载来源、空间/权限和 slot marker，统一更新同一份配置并替换所有服务 mount；移盘不改 artifact ID/digest，不写旧位置别名。旧目录保持只读保留到核验完成，绝不同时启动两组 writer。
5. 预检所有 roots，再先起 RS/控制面、执行必要恢复，后启 worker 和接收。验证受保护对象、Head、固定 package、跨 root 下载与清理范围；失败则保持停服并诊断。在新环境已接受写入后不能简单切回旧副本。

部署可重建不等于授权自动丢数据。若明确选择全环境重建，沿 S0/D07 的人工受控重建流程丢弃本轮状态并重新注册映射/导入；不把删除 control DB 或 cache root 当作正常换盘步骤。首次要求保留正式业务状态时另开 migration/备份恢复设计。

## 11. Contract、代码与文档改动面

以下为**未来实施清单**；本轮不修改 Accepted Contract 的版本或状态。

| owning 文档/代码 | 必改内容与回归边界 |
| --- | --- |
| [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §5 | ID 位置协议、唯一归属、多 root 发布/保护、PREPARED 与 exact-commit 恢复分界；不变更规范表语义 |
| [Snapshot Table Access](../../../contracts/snapshot-table-access.md) | canonical/raw/client wrapper 的分类，IPC 与 export 区分、read-handle/root 生命周期；内容 key 不丢 scope |
| [Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) | 资源字段和生效/拒启、checkpoint/READY 跨 root closure、scratch 非权威；S1a 不重写多 worker 恢复 |
| [Business Lifecycle](../contracts/business-lifecycle-and-state.md) | source/manifest/Attempt/Head 的保护移交与 nominal ref 新 ID 约束；不改 Submit/Archive 状态机 |
| [Comparison Bundle](../../../contracts/comparison-bundle.md)、comparison/risk/ChangeSet 相关 Contract | ref codec、bundle/records/cache closure 与 golden；保留 READY 之前物化/导出，GET 不临时造业务结果 |
| [早期 Artifact 说明](../../../artifacts.md) | 修订本次触及的单 root、旧 canonical Parquet 和发布描述，指向当前 owner；不重写全部历史设计 |
| RS owning layout/mutation/upload/cleanup 规范与 ADR 0012 | 替换全局同盘假定，精确发布对、配置/缺挂载边界、admin 对新布局的理解；不扩张安全主体 |
| `settings.py`、bootstrap、ports/adapters、schema/DTO/golden | 严格新 ID、配置同源，必要时直接改唯一 schema baseline；不引入 migration、旧字段双读/兼容 alias |
| Compose/entrypoint/依赖闭包与 test harness | 多 root mount/权限、实际 cgroup、离线本机构建、当前候选容器验证；改锁/基础镜像才触发相应预填充流程 |

须删除被替代的单 root resolver、默认系统临时目录接线、跨盘 rename 路径、旧 ID parser/generator 和对应旧探针。只删除本轮替代路径，不借机重构 RS 历史 probe 或修改 P6 测量/退出证据。

## 12. 实施顺序（下一编码会话已获授权）

以下为顺序概要；可执行的工作包、输入字段、文件落点及每步完成条件以 [S1a 实施执行方案](p7-s1a-execution-plan.md) §3–6 为准。

| 步骤 | 可审交付 | 前置与停止条件 |
| --- | --- | --- |
| A | 在 B 后继 main 固定实际实现入口；核本文消费者差异，修订 owning Contract/ID golden 目标 | 保留三份 S0 文档来源；不覆盖其他会话改动；设计独审按实际风险安排 |
| B | 位置 codec、typed layout、全部 ID producer/serializer 与 in-memory contract | 先统一身份；检查 canonical/transport 重算 ID、nominal refs、bare ID 查询；不保旧格式 |
| C | multi-root local store、单对象原子发布、跨盘 copy、read/cleanup 锁序与失败 | 对应 focused Contract 验证通过后接消费者；保持 READY/T1 原屏障 |
| D | scratch 显式接线、backend 全部读写/下载/cache/protection、bounded 维护入口 | 核 protected 缺失与 optional miss 的差别；未知目录只诊断 |
| E | RS 显式 layout 与发布对、admission/recovery/admin/entrypoint；Compose 同盘/分盘样例 | 不去掉子目录 root/symlink 检查；保持同库 writer/CAS/effect 核对 |
| F | N/M/E/reserve profile、W=K=1、实际 cgroup/挂载启动预检、S1b 窄观测接点和运行说明 | 缺硬件/容量值明确配置失败或待 S5，不制造测量默认值 |
| G | 在 clean 最终候选完成受影响权威包与必要容器门禁、独审/handoff | 调试只 focused；阶段真实输入范围按改动面及 DC33 确认；不重复同次 runner Compose |

每步记录实际改动、摘要影响和验证 owner。S1a 完成须能在单 worker 下从上传、Preview、Submit/Archive、恢复到下载/清理闭环；不能只交四个新路径 settings。S1b 可据接口约定提前设计，但不能把未实施统计说成已可查询。

## 13. 验证矩阵（本轮不执行）

每个不变量一个权威测试 owner；其他层只验证接线。以下优先扩展现有行为用例，同构场景参数化，不复制新全矩阵。

| 不变量 | 权威 owner / 已有测试入口 | 最低场景与判据 |
| --- | --- | --- |
| ID 唯一、准确定位 | backend artifact ref conformance / boundary | 四位置、旧/未知格式、路径注入、非法 token；get_ref/locate 不扫描其他 roots；同 ID 不同 ref 冲突；同盘/分盘 ID/digest 相等 |
| 单对象发布完整 | backend artifact staging/store | bytes/stream/path 三入口；同盘/真实 EXDEV 分盘；短流、超长、SHA 错、取消、copy 中断/ENOSPC、fsync/rename 错；失败无可读残缺 ref |
| 并发与崩溃 | backend store/保护 owner，serial | 同 ID 并发相同/冲突发布；rename 前/后与 DB 引用前后代表点中断；相同 ID 可核结果；不穷举内部每条 syscall |
| 所有读协议一致 | artifact store / snapshot table owner | locate/read_exact/open_buffer/get_ref/verify_readable 命中四位置；mmap 关闭与 Arrow/Rust lifetime、symlink/非普通文件/错 root 拒绝 |
| 多 root READY/download | backend bundle download Contract/HTTP 接线 | 混合位置 closure；headers 前缺成员失败；传输中 I/O/断连释放 locks；并发 cleanup 不删除成员；完整 tar 校验/Content-Length 正确；GET 不生成持久 tar |
| 强保护与 TTL | backend protection/submit/archive/cache owners | Preview→T1 Attempt、finalize/abort、Head CAS/回滚与低频 Head、READY；共享对象多 owner，最后强 owner 释放后 TTL；prune index 不删强引用；new pin 与清理竞态 |
| 恢复来源 | existing checkpoint/submit recovery owners | PREPARED 缺 frozen 输入稳定失败；effect 后响应丢失复用固定 package/key 查明结果；已接受 commit 可派生回填按原 Contract；scratch 清空不冒充恢复完成 |
| 清理边界/公平 | backend bounded cleanup | 四 root round-robin、busy root、unknown/malformed/symlink/子挂载、活跃与崩溃 staging、重复 delete、I/O 重试；metadata/repository/他人目录不被访问 |
| RS 分盘正确性 | RS layout/upload/publication/recovery/cleanup integration | rs-repository/rs-artifacts/rs-metadata/rs-scratch 分盘；建库 rename、ready pin、import/恢复、同库 writer、admin 锁及停服一致集合；backend 无 RS volume |
| 挂载实际生效 | backend/RS Compose gate | 默认同盘、类别分盘；缺 source、错 marker、宿主盘未挂载、只读/错误 UID、运行期卸载；无底层目录 fallback，启动不 claim，runtime 失败可诊断 |
| 资源配置 | backend settings/worker resource owner + Compose 接线 | 正/负/零/bool/溢出/未知字段；M>E−reserve、E>48、M>40、reserve<8、K>W及 S1a W>1；环境/真实 memory.max/祖先限额不符；N 与 quota/cpuset；M 非 RSS |
| 容量检查 | admission owner，纯校验无 Dolt fixture | 两 root 同盘只计一次、跨盘分别不足、inode 耗尽、source/staging 同时需求；预检通过后仍 ENOSPC；资源拒绝不发布成功、不删保护对象 |
| S1b 归属就绪 | owning adapter 的小型契约验证 | 一对象多用途/多库引用、BE/RS 相同 SHA 两副本、telemetry 不可用、负/缺失观测、未归属；无需新增统计 API 或全盘扫描 |
| 端到端身份 | 当前候选单 worker 小型真实链 + 现有业务 golden | 同盘/分盘正式结果、scope、canonical digest 相等；正常/无变化、有效下载和保护后清理；清楚区分功能验证与容量结论 |

真实不同 filesystem、容器权限/挂载、ENOSPC 故障只使用本任务隔离卷/镜像/配额，不填满共享宿主或清理他人数据。临时文件系统故障向量用于验证发布失败；正式持久性验收使用真实文件系统，不能用 tmpfs 代替。

调试在 06 focused/Contract/小型 Compose，真实 backend e2e 按 05 默认职责；04 承接权威 runner/容器/carried。均在获准 LAN 传输后的 clean 已提交 worktree、offline 缓存环境执行，遵守节点占用和日志规范。本轮不连接节点、不运行这些检查。

Owner 于 2026-11-10 明确验证节奏：A–F 按实际影响做逻辑/Contract、必要真实 filesystem/Dolt 与最小数据链验证，G 在最终候选集中构建并完成受影响权威包、必要容器及已确认最小真实范围；不因小节交接或复审重复完整构建/旅程。只能在容器内证明且影响后续接线的 mount/权限/entrypoint/cgroup 等行为，在关联实现收敛后做最小必要 Compose 验证，可合并关联包；其余容器项以 `deferred` 移交 G，不阻塞无依赖实施，不以延期关闭正确性问题。细则见 [S1a 执行方案 §5.2](p7-s1a-execution-plan.md#52-运行前提与收敛方式)。

S1a 触及 mounts/permissions/entrypoint/Compose，G 的最终候选必须重建并运行相应容器门禁；按包闭包决定受影响包，不因文档任务跑六包。依赖基础镜像仅在其定义的输入变化时重建/传输，产品镜像使用已有基础镜像与缓存；正常通过以一次集中验收为目标，修复后按影响重建复验。S5 最终六包与最终 HEAD 容器要求不变。runner 非零先处理失败，不继续 carried；任何阶段沿用仍按同节点同 worktree 和镜像身份规则判定。

## 14. 本轮交付状态与剩余责任

本会话新增本文、处理组/测试副本设计补充、S1a 实施执行方案及新会话提示词，并按 Owner 最新确认同步三份工作区 P7 来源的分组/阶段/授权说明；未编辑产品代码、Accepted Contract、P6 证据或 FE 文件；未提交、部署、推送、创建 tag 或运行产品测试。文档只做路径/来源/一致性静态核对，不以自查冒充独立审核。

已定：消费者与类别、位置编码、唯一物理归属、跨盘发布、缺挂载/运行期失败、清理与保护、资源关系、S1b 统计来源、实施顺序和验证矩阵。未定但已有 owner：S1b DTO/采样保留；S2 多 worker 槽位与恢复；S3 队列/磁盘全局准入；S5 目标硬件、输出/临时容量与最终默认值。无新的 S0 业务取舍阻塞设计。

当前审阅 HEAD 为 `a300b16485bcad2f178aaccfe0c8adbb51b5ab83`，产品设计基准为 B。本轮纯文档不触发镜像重建，不声明当前工作区 image 已验证。最后核对的产品镜像 provenance 属于 P6 B 的最终报告：RS revision 为 B、source-tree 为 `sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`，各服务 config digest/RootFS 详见其原始 provenance；本文不将它 carried 成 P7 结果。下一次镜像验证落在实际 S1a 产品候选。
