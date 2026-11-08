# V1 时间与内容事实：实施准备工作单

2026-11-07。Owner已授权本节，**A1已获独审GO并结束两角色，现启动V1**，实际起点/角色见§5。依据[联合kickoff §1.1](p6-be-a-d-kickoff.md#11-实施授权与实际起点owner2026-11-07)、[业务核验设计 §3–§5/§8–§9](p6-archive-business-validation-design.md)、[设计复审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)。这里固定实施边界，不重新选择时间语法或业务规则。

## 1. 范围与归属

V1交付源序时间提取和initial/modified内容事实，经Rust→Preview materialize/checkpoint→READY→AcceptSubmit T1→immutable Attempt/Submission完整冻结；归档日后读取不依赖临时Preview/原SQL TTL。来源图、异常接受/Start、统一终局处置和关闭出口归V2，tar归D。现有canonical业务内容哈希保值，不重做S1–S2b、不恢复Python SQL解析/计算路径、不改Shared Kernel原scalar语法、不碰原冻结测量资源。

实施建议GPT-6.1-Sol/xhigh；独审建议GPT-6.1-Sol/max，原因是native源序与checkpoint/lease/generation、T1/finalize持久冻结跨层相连。实际创建由协调者在A1收尾后执行，每节两个新角色，禁止额外子agent。实施者拥有本节产品/测试/Contract、本文§2精确清单与`p6-v1-handoff.md`；审核者只写`p6-v1-review.md`；协调者负责启动/状态和总交接。保护并行dirty，显式暂存，不推送、不改写引用提交。

## 2. 精确变更清单须在产品写入前固定

以下为按A1时点实际源码确认的入口。实施者先核当前候选，补充本文或handoff中的**具体fields、所属类型/序列化字段、唯一基线DDL、版本/digest preimage、DTO/OpenAPI有无变化、golden路径和唯一测试owner**，随后按已定语义实施；常规技术落点不重复请求Owner批准。若发现核心冲突交协调者/设计者，不能用临时默认值或兼容读法填缺口。

| 实际入口 | 必须落实的变化 |
| --- | --- |
| Rust `gateway-compute-core/src/table_access/` 与实际唯一上传materialization入口；PyO3 `gateway-compute-python/src/{lib,business}.rs` | 在规范排序前按version_manager INSERT源行序提取；小型metadata随原输出传递，不把整列搬到Python，不另扫SQL。明确取消/截止/预算与Arrow跨批次的传递 |
| `capabilities/snapshot_materialization/{contracts,native,materialize,compose}.py`及实际owner | 传递源时间事实，复用完整规范表的`canonical_state_digest_of`；规则/投影/scalar身份一起绑定，不把snapshot/commit/raw SQL hash当内容身份 |
| `application/preview_jobs.py` `_CanonicalPreviewMetadata`、materialize/assemble artifacts和decode/encode；`domain/workspace/models.py` `PreviewCanonicalBindings`/`PreviewResult` | 补FULL initial规范内容身份，initial/modified时间及源绑定、facts digest；明确MODIFIED_ONLY BASELINE_REUSED与显式INITIAL空基线。新必需载荷随现有checkpoint、LeaseSession及READY原子发布；删除旧解码路径，不缺省填充新事实 |
| `application/submission/{accept,accept_transaction,job_payload,finalize,finalize_transaction}.py`；`domain/submission/models.py` | T1从精确绑定Preview复制并校验到Attempt，finalize同事务复制到Submission，幂等/恢复不能重提取或改写；caller不提交通过标志 |
| `infrastructure/control_db/{schema,sqlite_workspace,sqlite_submission}.py`及真实mapper | Preview/Attempt/Submission小型事实在唯一基线持久化、严格读取/源绑定校验，无迁移/回填/双读。持久Submission可在Preview/SQL清理后独立解释；基线沿source_submission_id取得事实，不另立一份Baseline时间权威 |
| Preview查询/HTTP和其他consumer | 按实际必要性同步DTO/OpenAPI；若本节不新增公开字段，清单明确写none，不另造接口。V2消费的facts读取端口/类型归属清楚，不反向依赖私有capability/provider或临时artifact |
| owning文档 | Business Lifecycle、Snapshot Materialization、Canonical/Preview/Submit及native metadata实际Contract；冻结字段/checkpoint/job contract/digest/golden同步到目标形态，历史DC/审核报告不改写 |

事实至少表达业务设计§4.1已定的selected/max UTC、有效/空/非法计数、last/max源行序、源摘要/提取规则身份与明确质量状态。规则身份固定`gateway-vnext/configuration-generated-time/v1`。missing业务原因、INITIAL不适用与程序漏保存facts严格区分；后者硬完整性错误。facts摘要与既有业务内容摘要分开，不增加独立receipt/evidence平台。

## 3. 固定语义与验收owner

- 完整UTC grammar、ASCII trim、T/单空格、可省略fraction（出现时为1–6位）、offset≤14:00、0001–9999及归一越界、非法/空值分类，严格按业务设计§4.1；不用宿主`fromisoformat`隐式扩展。无zone按UTC，精确微秒比较，无float/tzdb。
- selected取源序最后有效值；max并列保留首次达到max行号；序号从1跨INSERT/Arrow batch连续，空/非法仍占序号。selected<max单独保存LAST_NOT_MAX，不替换为max，不按规范排序/PK/输出批次猜源序。
- Rust/native一个权威owner参数化覆盖已审全部单值/源序向量、ASCII/非法/缺表列行/全空、跨INSERT/batch、N/chunk/规范排序不变，保留原typed scalar硬拒绝。纯语法不引入Dolt fixture。
- Preview owner（`test_preview_job_materialize.py`、相应worker/publish/checkpoint owner）验证重启读取冻结事实、源/规则/内容绑定与缺必需字段损坏，取消/失租/旧generation不能部分发布。复用既有冻结恢复语义屏障，不穷举内部步骤。
- Submit owner（`test_submit_transactions.py`及实际T1/finalize owner）验证T1与finalize复制一致、原成功回放/重启不改事实、拒绝不写部分Attempt/Submission；一个代表案例证明Preview/SQL过期后仍可从Submission及baseline source独立读取。不要在归档事务重扫文件/调用Repository。
- 只更新所属新facts/版本/checkpoint身份golden；既有业务digest/比较结果应保值，不以无兼容包袱为由重录所有golden。V2将facts身份纳入candidate/selection/anomaly subject的后续变更须明确交接，不漏consumer。
- **已发生接线澄清`a24b7034e9`**：保留既有ADDITIVE旧基线Preview；baseline identity取source Submission.modified原rules/projection/scalar，核commit/manifest/facts绑定，MODIFIED_ONLY initial精确复制，FULL两上传侧用本operation冻结规则。不能强制三侧规则全等或以runtime重标历史。operation/runtime mismatch、T1 derived stale、STORAGE_BREAKING及未知/不支持格式/损坏仍按原边界拒绝。原`test_additive_ruleset_previews_nonempty_baseline_from_older_manifest`保留并补相应事实断言；V2仅禁止跨身份直接判等，不把合法差异变整批硬拒绝。

## 4. 节点、证据与收口

全部编译/测试/lint在06（冲突按既有用途协调），先SSH、现场核空闲并原子占用；clean已提交测试WT、legacy链接、LAN bundle与离线缓存、TMPDIR、日志host/起止HEAD/UTC/exit/SHA按AGENTS。Rust四工具按仓库selector，同toolchain、PATH以`/home/dev/.cargo/bin`开头，UV_OFFLINE/CARGO_NET_OFFLINE，建议jobs/workers4，与产品M/N分开。Rust改动后backend必须`--reinstall-package gateway-compute-python`并核当前Rust tree build input，不相信旧so。

先native/Rust相关focused、fmt/clippy与backend冻结/Contract，五包静态按实际改动执行；不逐轮全量runner、真实完整旅程或新大输入。Rust/native及持久接线影响当前镜像，按实际diff在本节收敛候选完成必要最小容器边界验证；04联合权威/必要Compose、05 fresh t1留联合候选。依赖/锁有变按DC67在CT201预填制品，不让06联网；缺缓存停止补齐。

正式pytest focused显式按marker分批：主体`-m '(not serial) or parallel_safe' -n 4`，其余`-m 'serial and not parallel_safe' -n 0`，不凭选中文件名称猜是否有serial。已发生的c464混跑保留实际320pass诊断，318非serial可核；两项adapter serial单独补一次，不重复全套、不改变marker来凑通过。

先交固定代码候选供只读独审，证据随后由同审核者复核；失败留证、最小修复/重审，不换审核者清finding。每轮handoff写当前HEAD、容器触发/理由、最后实际revision/source-tree与精确deferred nodeid/节点。通过后结束本节两角色，新建V2角色自动推进；不宣称归档核验、tar或FE3已交付，不办理联合exit。

## 5. 启动记录

A1最终独审报告为`c1ee9627559dcf752e82bcd6ad68735ea0d8fc59`，F1/F2/N1关闭；产品/容器候选`d8bee1a5914d00f473dc41fb76d9c57ca4b01f48`，交接至`fb53d4f60f73615a6e893f725eae801054351728`。A1实施者已确认本地/06无遗留执行、停止写入；审核者报告已提交并停止本节。工具只有停止能力，角色历史未销毁。

V1实际起点为clean main **`c1ee9627559dcf752e82bcd6ad68735ea0d8fc59`**（允许随后本轮协调文档提交，不回退历史候选）。默认顺序仍A1→V1→V2→D。新实施者选择**GPT-6.1-Sol/xhigh**、新独审者**GPT-6.1-Sol/max**；创建后ID记总协调交接。先完成§2精确fields/schema/version/checkpoint/digest/DTO/golden清单，落盘后按已定语义实施；设计冲突再升级，不让缺失事实以默认值进入产品。

实际角色已创建并启动：`/root/be_v1_impl`（GPT-6.1-Sol/xhigh）、`/root/be_v1_review`（GPT-6.1-Sol/max），均独立上下文；协调启动提交`72bb929b1f`。实施者先提交§2精确清单，审核者独立准备/固定候选后审；两角色互通普通修复，协调者跟踪结果，不新增角色。

06现仅按A1已核08:09:12Z释放记录定位；这不是V1的预约或实时空闲证明。V1执行前重新现场核空闲并原子占用，日志/源码/测试WT与A1分开归属，不删除A1证据、镜像或WT。尚无V1测试证据，04/05联合验收不提前宣称完成。
