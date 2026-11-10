# P7-S1a A：入口、消费者与 Contract 目标

日期：2026-11-10。状态：**A 实施候选；文档目标未独审，B–G 未实施/验证，无 DESIGN_GO 或产品通过声明**。

本包只写七份 P7 输入、触及的 owning Contract/早期 artifacts 说明及本包交接/验证稿；产品、golden、P6 原件与其他会话均未修改。A 之后须由原审核收才进入 B，本文不授权实施者自行启动下一包。

## 1. 实际入口和来源

| 项目 | 固定事实 |
| --- | --- |
| P6 exit B | 附注 `p6-exit` → `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809` |
| 实际 main 起点 S | `5ddd73b962e2432f961a46f6743395a53a388435`，B 为祖先 |
| S 的 vnext tree | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`，等于 B |
| B..S | `f9fa8cd8f8`、`5ddd73b962`，分别只新增 `docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`、`docs/frontend-vnext/reviews/fe3c-fix2-check.md`；无 vnext/owning Contract 增量 |
| 源工作区 | `/home/dev/gateway-data-management-system`，FE 分支 `fe3b-evidence-04`、`a300b16485bcad2f178aaccfe0c8adbb51b5ab83`；有其他 dirty/untracked 文件，未切换/修改 |
| main 工作区 | `/home/dev/gdds-s5-design-main`；有 FE 并行工作，未写入 |
| 本包隔离 | `/home/dev/gdds-p7-s1a-a`，短期 `p7-s1a-a`，基于 S；只有本包提交，合 main 由协调者串行办理 |
| 七份原件提交 | `bc184e5007`，逐路径复制/暂存；无 `git add .`，无夹带 FE 或 architecture/implementation-stages |

本轮用户给出的 AGENTS 指令及实施提示词优先：06 focused/Contract/小型 Compose，04 权威 runner/容器/carried，05 默认真实调试；不继承 P6 的 06 完整真实旅程专项许可。S 中本地 AGENTS/testing-conventions 已记 DC91 节点池及新版 DC68，这与本轮输入不同；本轮不据此扩张节点/重试授权，不改这两份共享治理文档。本轮失败按用户给定 DC68及提示词执行，不默许三轮恢复。此差异不是业务阻塞，固定执行稿必须写明适用输入。

七份文件在 `bc184e5007` 的 SHA256（本表记录本轮复制原件，后续修订不覆盖此历史）：

| 文件（同目录） | SHA256 |
| --- | --- |
| p7-s0-owner-decisions.md | c120c608cbcc0cea234132b5ad0257ccb4a2f16470b15c92571fc100c56a009a |
| p7-design.md | 6664ed579ea6fe1be8bbc98f400f1bd600b72386ce28d2ebbaf315a749074acc |
| p7-execution-plan.md | 12ce37ad871a1e25abccd361758074c46944b28d769640d85ed2291219a6be26 |
| p7-s1a-storage-resource-design.md | 1ebfd1d8209b79da6eb35746baf65a64f224dde65b3b55d2207e47252c18e5f2 |
| p7-s1a-execution-plan.md | 7681166cf9cb89188fc3787e24d51bfd867b7bdb9e772a017fd8fe1613c2fcd3 |
| p7-processing-groups-and-test-extraction-design.md | 554668c7475f264e59ba33c39f5f8c937635a20d6a49a60f8f7e9af69e4334bf |
| p7-s1a-implementation-prompt.md | 47548deac73848fe9973cbc987e0e11ae4b0aabd9c7dc7e3a983d3d630389bec |

S1a设计§1所列P6报告、receipt与原独审只作依赖入口，不重跑P6，也不把P6镜像/真实结果 carried为P7。正式资源起始样例仍N1/M24GiB/E32GiB/reserve8GiB/W=K=1，M不是RSS；开发profile具体CPU/宿主份额须在后续节点现场检查，未知不写通过。

## 2. owning Contract 与生效边界

本轮在下列各 owning 文档新增显式“P7-S1a目标补充（待实现）”。Accepted版本、原API/状态机与当前源码不变；B–F相应实现与producer/decoder/golden必须同一逻辑批次闭合，G才记录最终已生效范围。中间目标不是兼容路径，旧ID/布局在切换实现时直接删除。

| Owner | A固定内容 | 后续实现owner |
| --- | --- | --- |
| Canonical Storage | 四字段ref、新ID/token/类别、唯一root、完整原子发布、保护锁序与bounded cleanup；PREPARED/prepare/exact-commit边界不变 | B codec，C store/保护，D链路 |
| Snapshot Table Access | canonical IPC/wrapper与raw/client Parquet分类；root borrow与Arrow lifetime、scratch与文件导入 | B ID，C handle，D消费者 |
| Operation Lifecycle | 两配置同源、N/M/E/reserve/W/K/cgroup、挂载拒启/拒新工作、跨root checkpoint/READY | B配置，C/D closure，F部署 |
| Business Lifecycle | 所有nominal/bare backend refs严格codec；T1/finalize/Head保护移交、ConfigurationFacts与归档摘要传递 | B decoder，C UoW，D业务 |
| Comparison/Risk/ChangeSet | comparison物理归属、cache/records闭合、原内容/规则摘要与恢复边界 | B producer，C store，D复用 |
| Comparison Bundle | export新成员与直接引用原成员；transport重算、混合root下载、FD上界、传递摘要 | B helper，C borrow，D下载 |
| Repository Service | 四具名roots、两个同盘发布对、metadata/WAL/HOME、scratch/capacity、admin一致集合 | E全链，F mount/entrypoint |
| artifacts.md | 修正触及的旧canonical Parquet/重建固定包/单root publication叙述，其他历史草案指向现行owner | D替代旧路径；G核文档 |

目标协议不添加ref.location字段、locator DB、broker、receipt、热迁移或旧别名。root marker是部署防错卷身份，ref.jcs是已有内容身份；都不能替代业务成功/保护事实。位置不代表授权、设备归属或TTL。作用域一环境/组；不实现路由目录、统计产品、多worker、调度或抽取器。

## 3. 实际消费者复核清单

下表按 S 的真实源码核对。`BE`=`vnext/backend/src/gateway_backend/`，`RS`=`vnext/repository_service/src/gateway_repository_service/`。B..S没有新增产品消费者；以下是对详细设计B盘点的工程补齐，不是已完成勾选表。后续包逐行记录改动或不变理由，不能只以通用codec覆盖推断闭合。

### 3.1 生产与重算身份

| S实际文件/入口 | 目标位置/动作 | 包 |
| --- | --- | --- |
| BE/artifacts/types.py、digest.py、validate.py、serialize.py | 用单codec取代宽泛128字符ID/namespace-suffix；四字段保持；InMemory一致 | B |
| BE/infrastructure/artifact_store/bounded_store.py `put_stream`；http/orchestration/multipart_upload.py | 随机ID显式durable，128-bit nonce；不由kind猜location | B/D |
| BE/capabilities/source_package_staging/staging.py `_new_id` | source-bytes/source-doc显式durable；source package/entry内容digest不加入ID | B/D |
| BE/capabilities/storage_projection/publish.py `_opaque_id`、`_publish_json` | CanonicalizationManifest及projection/structural元数据durable | B/D |
| BE/artifacts/canonical_table_store.py `CanonicalTableKey.artifact_id`；capabilities/snapshot_materialization/canonical_store.py | canonical ID保留完整scope/projection/schema/count/table/mapping输入，不能只复用旧hash截断 | B/C |
| BE/capabilities/snapshot_materialization/artifact.py `_opaque_id` | raw rows/wrapper=export，canonical wrapper=canonical；同helper按显式location分开 | B/D |
| BE/capabilities/snapshot_materialization/client_parquet.py | export ID；显式scratch、file有界导入，替代read_bytes整文件路径 | B/D |
| BE/capabilities/comparison/artifacts.py `_artifact_id`；persistence.py `_ref`；artifacts/computation_cache.py | records/manifest/closure与cache envelope/member= comparison | B/D |
| BE/capabilities/risk_evaluation/_artifacts.py；persistence.py `_ref` | risk/neutral candidates及包络=comparison；不能遗漏直接ArtifactRef构造 | B/D |
| BE/capabilities/mutation_planning/_artifacts.py；application/pair_pipeline.py | ChangeSet closure、project identity assessment=comparison；新token保留完整identity，不延续16hex截断 | B/D |
| BE/application/checkpoints.py `_content_artifact_id`及可指定artifact_id入口 | checkpoint/READY/JSON facts=durable；要求显式固定kind，不留任意旧prefix ID绕行 | B/D |
| BE/application/preview_jobs.py canonical-table-set closure；submit_jobs.py request与terminal evidence；history/compare_jobs.py | durable；prepare固定request/package/key与checkpoint引用一致 | B/D |
| BE/capabilities/bundle_assembly/_assembly.py `_bundle_artifact_id`、`surface-source`临时ref；transport.py `read_bundle_transport_metadata` | export新交付ID；assembler/transport共同构造原closure；直接既有ref保持位置，bundle_id仍是业务ID | B/D |

### 3.2 reader、decoder、保护与接线

| S实际文件/入口 | 必须关闭的路径 | 包 |
| --- | --- | --- |
| BE/artifacts/store.py及infrastructure/artifact_store/{local_store,bounded_store}.py | put/stream/file/get_ref/locate/read_exact/open_buffer/verify、mtime与delete统一resolver；删私有_validated_paths绕行 | B/C/D |
| BE/application/canonical_metadata/{manifest_reader,table_access}.py；capabilities/snapshot_materialization/{artifact,client_parquet}.py | bare manifest ID、canonical reader、raw/export cache均按同codec；exact commit不提前全量物化 | B/D |
| BE/artifacts/bundle_download.py、tar_stream.py；application/bundle_download.py；HTTP下载与bootstrap lookup_ref | 混合root closure，headers前完整校验，引用保护先于READY；流关闭释放全部roots | C/D |
| BE/infrastructure/control_db/{sqlite_canonical_tables,sqlite_snapshot_export_cache,snapshot_export_cache,computation_cache,sqlite_protection,database}.py | 完整ID/ref、root→DB锁序、store在read_session内写不升级EX；cleanup EX下短事务重核删除 | B/C/D |
| BE/infrastructure/control_db/{sqlite_operations,sqlite_workspace,sqlite_submission,sqlite_archive}.py、schema.py；operations/contracts.py | 所有JSON/ref与bare ID decoder，唯一基线必要时直接改，不双读/迁移 | B/C |
| BE/domain/{workspace/models,submission/models,configuration_facts}.py | SourceArtifactBinding、PreviewArtifactRef、PreviewResult IDs、BackendArtifactRef、Attempt/Submission bare refs；ConfigurationSideFacts当前仅_text，须严格codec；INITIAL_EMPTY保null | B |
| BE/application/submission/{artifact_refs,contracts,artifact_release,finalize_transaction}.py；submit_jobs.py自有backend/repository decoder | nominal type不混用；backend严格新ID，Repository仍RS UUID；T1/finalize/abort保护不降级 | B/C/D |
| BE/application/archive/{contracts,snapshot,closure,start}.py、domain/archive与sqlite_archive decoder | candidate/source/manifest bare refs及归档冻结/重放载荷严格校验；digest不删原绑定；Head CAS前先借root | B/C/D |
| BE/http/{mappers,schemas/upload,schemas/preview}.py；http/orchestration/{multipart_upload,submit_acceptance}.py | 输出/重新构造与现有名义refs共用验证；ID可见但不是授权能力 | B/D |
| BE/bootstrap/{composition,operation_worker}.py、settings.py | HTTP/两worker composition/恢复/下载/维护同layout；metadata固定DB；删旧root/N/M/E入口 | B/C/F |
| BE/http/routes/upload_revisions.py `accept_upload_route`；http/dependencies.py `WorkspaceHttpDependencies`；bootstrap/composition.py；http/orchestration/multipart_stream.py `parse_streaming_multipart`；multipart_upload.py acceptance/finally | route在artifact store前直接解析；由composition→WorkspaceHttpDependencies→route注入scratch能力，不能仅改store。mkdtemp当前无dir；改为显式be-scratch request/upload owner（此时尚无operation），累计全部part的temporary bytes，覆盖构造/解析/验证/发布失败及取消shield等待后的关闭；保留单part原上限，不以多part绕总cap | D |
| BE/capabilities/comparison/artifacts.py `_write_arrow_parquet` | SpooledTemporaryFile当前无dir，rollover可落系统temp；显式operation/step/attempt scratch owner，遵守原records/spool上限与共享temporary cap较小者；writer/spool所有出口关闭，最终bytes的M预约另计，不能用磁盘cap代替内存预算 | D |
| BE/infrastructure/repository_read/http_arrow.py | spool不落默认系统temp；关闭/取消释放scratch owner | D |
| BE/infrastructure/repository_write/{import_publication,wire_codec,http}.py | backend包与RS UUID边界/size/raw SHA原验；UNKNOWN保原package/key，backend不挂RS卷 | B/D |
| BE/bootstrap/storage_admin.py（目标新增） | init/check/cleanup显式维护；现有classify/delete字段不冒充已有完整sweeper | D |

### 3.3 RS与部署

| S实际文件/入口 | 目标/不变理由 | 包 |
| --- | --- | --- |
| RS/layout.py、settings.py、runtime.py | 当前DurableLayout.root/staging与assert_same_filesystem全局耦合，替为具名四roots/角色预检 | E/F |
| RS/create_repository/{command,adapters,visibility}.py、mutation_reconciliation.py | .staging/versioned→versioned留repository盘；可见性仍由ledger+complete目录决定 | E |
| RS/upload_artifact/{command,admission_pin}.py、artifact_{layout,root,cleanup,cleaner,retention}.py | artifact root独立mount；root以下同mount/symlink/pin/eligibility仍强制 | E |
| RS/versioned_import/{submission,command,worker,provider,recovery,admin}.py；capacity.py/admission.py | 临时展开/probe用scratch，来源ref/queue/result/commit不移入scratch；admission按真正写盘分组 | E |
| RS/process.py、providers.py、provider_lifecycle.py | HOME/config metadata，TMPDIR scratch/provider；Dolt全新HOME继续关闭versioncheck | E |
| RS/snapshot_admin.py及offline admin | 绑定同配置并显式枚举一致集合/单服务锁，不能构造公共祖先跨盘rglob | E |
| RS/storage.py、filesystem.py、workflow.py及probe matrix/target-gate | 只适配调用新layout的实际接口；P2/P6历史证据不改；全树snapshot不是S1b在线查询 | E/F |
| vnext/repository_service/docker-entrypoint.sh、deploy/compose*.yaml、deploy README、Dockerfile与Compose harness | 同源配置渲染、bind不自动建source、先mount核验再子目录权限；当前候选必要容器门禁 | E/F/G |

## 4. 摘要与 golden 边界

摘要是否改变取决于实际preimage，不能简单按“业务/物理”二分。以下“保持”均以固定相同业务输入、版本、descriptor/格式与实际内容bytes为前提；随机producer作同盘/分盘比较时固定nonce/业务ID，不把两个独立上传的随机ID差异当布局问题。

| 摘要/身份 | 源码依据 | 新ID影响与核验责任 |
| --- | --- | --- |
| artifact_id | artifacts/digest.py；CanonicalTableKey；各producer helper | 改为a1；canonical/transport重算同批；所有旧ID fixture改目标形态 |
| payload raw SHA、size | artifacts/store.py与producer | payload bytes不变则保持；含新ref的JSON变长/raw SHA变化；不可改raw hash公式 |
| source manifest/package/required entry digest、workspace upload fingerprint | source_package_staging/staging.py `_manifest_digest/_source_package_digest`；application/workspace/contracts.py | entry内容/角色/package kind，不含ArtifactRef，保持原公式；source/provenance JSON含ref的raw SHA另算 |
| raw_content_digest、business schema、snapshot/canonical state、row_layout、storage view、canonicalization_manifest_digest | snapshot_materialization/_digest.py；storage_projection/_digest.py | 不含物理root或新ID，保持；CanonicalizationManifest是内容文档，不因它自身ArtifactRef新ID升projection或mapping版本 |
| SnapshotTableArtifact.artifact_content_digest | snapshot_materialization/artifact.py `artifact_content_digest_of` | row media/size/raw SHA+descriptor/profile；排除row artifact_id，固定这些输入时保持；manifest JSON含row_file_refs，其raw SHA改变 |
| canonical-table-set、checkpoint/READY、request envelope raw SHA | preview_jobs.py；checkpoints.py；submit_jobs.py | 完整ref/ID载荷改变则按原JCS/raw公式重算；不要为保旧值删引用 |
| records content/manifest、facts/core/comparison/risk、neutral task key、ChangeSet/replay | comparison/artifacts.py/persistence/task_input、risk/_artifacts/candidates、mutation_planning | 原内容/规则/绑定公式不加路径/location。无ref的manifest/content保持；closure/report/cache envelope含ref的raw SHA可变 |
| records/risk closure及surface/bundle integrity | comparison/artifacts.py `_closure_payload`；surface_assembly/_digest.py；bundle_assembly/_digest.py/transport.py | ID不直接入semantic preimage，但JSON成员含新ref→raw SHA/size→surface/closure/bundle传递变化合法；逐链说明，不把旧值全冻也不全量重录 |
| ConfigurationFacts.facts_digest | domain/configuration_facts.py `asdict(self)` | 含source_artifact_id，按原公式变化；其canonical四字段content identity和时间规则保持 |
| archive candidate/candidate-set/frozen subject/fingerprint | application/archive/contracts.py/snapshot.py/closure.py/start.py、domain/archive | candidate含source IDs/manifest ID/facts_digest；依赖者随原公式传递，规则/状态机/确认语义不变；bare-ref decoder也必须严格 |
| RS ArtifactId、request fingerprint、CommitId | repository_contracts DTO与RS mutation/import | RS新上传仍分配独立UUID；不套backend codec。backend新ID不进入replay语义；不要求两个独立运行Dolt commit hash完全相同 |
| 两配置摘要/root marker | 新typed adapters与render（目标） | 配置摘要JCS+SHA256包含规范部署字段，换物理路径可能改变；不得混入业务digest；环境/组不加入artifact ID |

B须定向更新`tests/test_artifact_ref_conformance.py`中的EXAMPLE_JCS、所有旧ID构造/负向向量，Snapshot roundtrip/faults、nominal与DB/job decoder向量，以及确实含新ID的相关golden。`vnext/fixtures/golden/configuration-facts/v1/frozen-full.json`与`archive/v2/identities.json`核实际输入：换source ID则重算原公式，不改规则；不因目录名有golden就全部替换。

`vnext/fixtures/golden/comparison/s1b/semantic-results.json`、`risk/s1b/structural-risk.json`、`bundle/s1b/snapshot-table-bindings.json`、`surface/s1b/table-presentation.json`和mutation renderer向量按preimage逐项分类。共享cell、SQL parser、规范表/投影/行和replay.sql golden不因新root直接重录。B/C/D必须给raw变化和保持断言的实际证据，A只固定核验要求，不填写PASS。

## 5. 设计工程补齐与风险

1. 补齐ConfigurationFacts/domain nominal/Archive bare-ref decoder；不能只替换ArtifactRef正则。配置facts和归档绑定摘要允许原算法传递变化，不删绑定。
2. 区分artifact_content_digest（排除row ID）、manifest raw SHA与Bundle传递完整性。总体设计“location-independent”澄清为物理路径无关，逻辑location显式在ID中。
3. 单root下载FD≤2不能继续宣称多root仍≤2；目标明确最多4 root FD+1当前artifact FD，chunk/metadata预算不变。读闭包借齐roots，避免动态反序取锁。
4. root→DB顺序需在UoW入口实现；清理EX短事务不能复用会再取SH的普通wrapper；cache store已有SH内put，发布必须no-replace而非升级EX。
5. 补齐HTTP multipart接收目录与comparison Parquet spool两个系统temp入口；前者request/upload owner不伪造operation，后者归当前operation，累计temporary cap与原producer cap同时成立。D须覆盖ENOSPC/EDQUOT/取消/构造和close失败：不发表UploadRevision/READY或成功引用，按既有失败owner返回并释放句柄/本次scratch，无法清理的残留仅走已定有界非活跃owner清理，不改预期为成功；禁止靠ambient TMPDIR或系统temp回退。multipart接受线程仍在运行时取消不得提前删其输入；已发布完整前缀依原owner/TTL收尾。
6. RS旧Contract全局同filesystem/whole-root snapshot与ADR0012历史兼容段落不能驱动目标保兼容：E明确发布对/一致集合和唯一基线；不重写历史证据。

轻量风险登记：权威事实为Dolt commit/main、Head/审核、scope与冻结固定package/key；可恢复durable为operation/checkpoint/保护和业务绑定；derived为canonical accepted-commit副本、cache、scratch、配置渲染与观测。误删冻结对象或跨scope/root写入涉及A/B类，保持事务/CAS/保护与关键语义屏障；一般临时孤儿C类有界清理/诊断，不建receipt。外部archive/path输入不可信，同UID协作部署、单机本地盘是已接受假设。多机/RWX、不可信插件、在线迁移、必须保留正式数据时重开，不为其预建框架。

本包无改变已确认业务范围的设计缺口，无Owner阻塞决定。filesystem数量等具体解析上限由B按十slot/256KiB约束定稿并以共享配置向量核；实际可用CPU/硬envelope/盘容量与真实输入清单尚未验证，分别交F/G。无兼容或迁移需求。

## 6. 验证、容器决定与交接

验证稿：[A静态验证执行稿](p7-s1a-a-verification.md)。A纯文档，无生产行为/锁/依赖/镜像/部署harness变更，因此不跑pytest、ruff/mypy、Rust或Compose；文档静态核验由唯一测试角色在06 clean已提交worktree按固定稿执行，原审在readonly detached候选核全部设计/Contract语义。开发机只读核查与编辑不作测试证据。

Current HEAD：以本包报告提交的父候选及外置审核/测试回执记录精确SHA，不能自指造值。Container rebuild required：no；Reason：仅docs。Last verified image revision/source-tree：设计§14所列P6 B/`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`，仅历史回归入口。Current HEAD container gate：not-applicable；Carried from：none。必要容器门禁在B–F最终涉及mount/权限/entrypoint的产品候选及G集中验收，不以本包文档宣称产品已通过。

A完成条件是本入口/目标/消费者/摘要表被原审核收及静态原件核收。当前未签设计GO、未测产品、未push/tag、未申请节点占用。后续B接两配置/codec及所有producer/decoder/fixture同批闭合，C接实际store/保护，D接消费者/维护，E接RS，F接部署/资源，G接最终证据；依赖项不得在A提前记PASS。协调者持有本地main串行合入与真实范围确认职责。

### A R1 修订记录

原审报告`/home/dev/gdds-p7-s1a-reviews/a/a46cea2c-r1.md`对`a46cea2c048b2dfb57c5c3ab062974ae6815a4df`提出A-R1-F1/P2：缺multipart接收与comparison spool的scratch消费者交接；A-R1-N1/P3：S0总规划锚点来自未提交标题。此次只补文档：§3.2/§5、详细设计§3.1、执行方案§3.3与Comparison目标明确route/dependency注入、request/attempt owner、累计cap、close/取消/ENOSPC及无系统temp回退；S0链接改为候选已提交标题锚点，不动implementation-stages。验证稿保持原内容，继承须由原审确认；未运行测试，不以修订自签finding关闭或产品PASS。

### A 静态执行工具故障修订

06对`24394b98a6e6f9bea89c404b44cf0dde691a8044`的首份wrapper在§5前因同条local展开未初始化filename而exit1；原日志和错误记录SHA见[修订执行稿§5](p7-s1a-a-verification.md#5-首次失败与本次最小修复)。原稿SCRIPT_GO不等于完整执行通过；§5–7未完成。Owner已明确同意继续，本次只固定完整文档验证脚本`p7-s1a-a-verify.sh`并将依赖变量初始化分行，补全起止日志/原exit/本人资源释放；产品、预期和原失败原件保持。本版仍待原审与唯一测试角色执行，未由实施者运行。
