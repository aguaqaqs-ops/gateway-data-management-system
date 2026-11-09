# S5 E 独立审核归档

这是E独立原审、连续复审、失败诊断和证据核收的逐字归档，绑定最终产品V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`。最后的`e-final-evidence-review.md`给出E_CODE_GO / EVIDENCE_GO（SHA256=`332f7f1c36b03b73944111cfde31929965887bfda0f8cdb67077c667c292a653`）。各原文只描述其当时固定对象/权限与结果，早期错误判断、撤回许可及实际非零不被改写。精确H绑定、实际释放和最终EXIT回执在[handoff](p6-s5-handoff.md)指定的外置原件中，不能以本档代码/证据GO提前创建tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-code-r1.md`；SHA256：`4eaccee43c7bffad64d65e3b85dcb62f69878327565d09d3e8ae3e934fbfbf9f`。

---

# P6 S5 E 独立产品及权威执行稿审核 R1

结论：**CODE_GO，绑定最终产品 V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`；修订 authority 稿 GO。** 当前没有新的产品阻塞 finding。执行稿初稿一处占用用途错误已在执行前机械修正并由本原审核对关闭。此结论允许唯一 E 测试者按固定稿开始六包权威入口及其中适用 Compose；**不是 E EVIDENCE_GO、t1 稿 GO、carried 或 S5_EXIT_GO**。

## 1. 固定对象与独立性

- V：`16317606d4c5ea357f7b07132f71f5ab4cd783bd`，D 交接文档提交。
- 最后产品提交：`cb2ad300845f73f12ae5367d247829623b728f18`；两者 vnext tree 同为 `8a28a9ab172d967eb526132084ec2b43b34b7c04`，Rust tree 同为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- S5 产品基线：`fd9e383d76642037e4b3246c847222ea9483e033`；该点的 vnext 与设计源码基线 `4c648965286ec751c4395cd6111f11838610299c` 相同。期间 FE3b/FE3 kickoff 合并独守其来源，未归为 S5 产品实现或重新签收 FE。
- 新 clean detached 只读 WT：`/home/dev/gdds-reviews/p6-s5-e-16317606d4`；创建后与报告前均核 exact HEAD、detached、index/tracked/untracked clean；legacy 指向 `/home/dev/gateway-data-management-system/legacy`。
- 本人是新 E 独审，未继承 A–D 对话、实现职责或设计轮 Astra 临时权限；没有创建子 agent、编辑产品/测试/Contract或被审 WT，没有 SSH/访问测试节点，没有运行产品测试、语法检查、lint、fmt、编译、镜像或执行本轮任一稿，没有 push/tag。
- 直接输入包括现行 AGENTS、testing conventions、实施提示词、S5 kickoff/design/coordination、设计原审三项 finding、A–D handoff 及相关原审/复审结论；追 Comparison/Risk/Artifacts、Snapshot Table Access、Canonical Storage、Shared Canonical Encoding、Operation Lifecycle、Repository Service、Rust/比例化政策和实际 consumer。S3/S4/Q18/BE-d 只核本阶段依赖、冻结语义及来源限制，不重新审其整阶段。

## 2. 最终产品与删除矩阵核查

| 边界 | 独立源码依据与判断 |
| --- | --- |
| 完整纯任务身份 | `comparison/task_input.py` 对 task/plan 新字段先分类；完整两侧 descriptor、storage facts、effective key、resolved rules/policy、方向、detail、diagnostics、scope 和版本进入规范 JCS。实际 native policy 由同一 projection 生成。FINAL/完整存储绑定/现有 reader 的 owning canonical 验证证明是准入前提；metadata-only 无 reader 仍保完整 side facts。STANDARD 不消费的 ordered metadata 被排除，ORDERED 的实际 provenance 保留；没有仅 raw digest 或 repr 的持久 key。 |
| neutral 格式与当前绑定 | Python codec/persistence 经真实 `comparison.native` facade；Rust core 只处理内存 Arrow/metadata。最多三 facts、三 artifact、一个 STANDARD risk 视图，facts ordinal/JCS/typed frames、artifact schema/detail/count、risk schema/count及完整 family metadata 由 owner 批量校验。每 batch 最多1024行，保实际 batch/Parquet row-group 边界，不设1024批次假上限。恢复后按当前 task/descriptor/table 重新计算 facts/records/core 及当前 manifest/closure；没有复用旧 bundle 或绑定摘要。 |
| 风险事件与控制 | `_engine.py` 的同一 emit 保 cap（pair 优先）→可选候选记录→rule/level/filter→必要预约/编号/append→原 `_check_table`。被过滤事件直接返回；CHECK_RECORDS_CLOSURE 核当前 closure；1024事件 checkpoint 只核当前 operation，不前移业务 clock。持久事件为完整自然结束序列，pair 成功后才登记；组合信号当前计算，不缓存截断 outcome。 |
| metadata-first History | `describe_repository_ref` 先核 repository/exact commit/catalog/完整表集与 canonical storage schema/count/raw/ordered provenance，再返回完整无行占位。History 分别验证 diff 与 export，使用 Comparison 的同一 reader-demand owner 合并实际行需求；`ensure_committed_tables` 只从同 scope 的 exact commit 补缺。普通 materialize 仍只返回实际行需求，保 Submit 单表/Preview consumer。 |
| checkpoint 与错误边界 | materialize side v5/wrapper v2 直接替换旧格式；恢复重新核完整冻结描述与 fresh exact-commit authority，重新 lookup 后补行，不依赖上次 hit 的 reader 假设，不读 main。新增 typed input 错误只在 authority/row 输入边界映射；计算/records/risk/surface/bundle 的原 runtime 错误、控制和未知 DB 错误不被宽 catch 改成 cache miss。 |
| cache/TTL/保护 | root shared borrow→短 DB lookup+全 refs pin→事务外 hash/decode。writer 在 put 前保护全部成员，完整写/核后同短事务登记 index/TTL/uses。过期 lookup 独立过滤，有界64项 prune/touch；替换/失效比较精确旧 manifest/ref，不删或 touch 新 writer。cache lease/backing 保到最后真实 Arrow consumer，READY 前及异常 finally 窄释放 active cache intent，保 workflow/source/checkpoint/result。 |
| T3 与恢复 | MatchingFinalizeFacts 之后从 Attempt.preview_result_id 定位真实 Preview producer，并核 workspace/repository/冻结 configuration facts。缺临时 Preview 只跳过可选定位；存在矛盾必须失败。窄 SAVEPOINT 只吞 typed 坏 cache payload，未知 SQLite/事务/CAS错误传播并回滚；无文件/Repository/比较操作，无 BaselineHead 推进。FINALIZED replay 在新 touch 前早返回。T1 即 PREPARED、prepare checkpoint 前后固定来源分界保持，缺持久包不重建、不换 key。 |
| N/M、控制与释放 | 单 operation 同 M，restore 逐表 phase/seal 后才准入 miss；可选 identity/views/risk retention 进入必要输出的一次准入回退，必要 restored backing 不提前释放。FFI operation identity 必须匹配当前 Python memory owner。N1 实读1，没有每表计算池、外层 HTTP 重试或额外 M。client 单请求最多原3次，catalog/Arrow open/error body/chunk/backoff 接当前取消/绝对截止；abandon 关闭在取消窗口才返回的 transport。 |
| 实际 consumers | Preview 和 History 由 bootstrap 接同一 computation cache；当前 records→risk→surface→完整 bundle 仍走唯一 publisher。真正 records open/restore 继续走原完整 validator；tar raw/ref/closure 不是其替代。Q18 两字段 selected 和 review_version、BE-d 完整 tar、FE 本地 consumer边界保持，S5未改 HTTP DTO。 |
| 删除与保值 | 已删除旧 repr key、History 全表预读/旧 checkpoint 行可用假设、旧 private Risk event 双类型及被替代 discard_many。实际有 consumer 的 generic facade、map-only library seam、原 records validator 与独立 golden 保留；没有为了删除数量制造接口破坏。S5未改依赖/锁、SQL golden、业务 golden或部署，不增 migration/双读/journal/helper/独立安全主体。 |

设计原审三项 finding 在最终代码中均无回归：风险控制顺序、DC94 prepare checkpoint 屏障、七视图/准确 risk schema 与1024行 batch 限制。A–D 原审的身份、SET/KEYLESS预期、foreign-operation、可选预算、reader/batch释放、H1/FULL与精确错误分类、poll终态和 parent catalog 接线修订仍在最终树中。

固定 expected 仍来自手算与既有冻结 oracle/旧源；检查到的新 cache 测试同时保独立 facts/records/Parquet 预期，而非仅新 codec self round-trip。业务不变量按既有 owner 分配，未要求复制真实 FULL/三节点/损坏/恢复矩阵。

## 3. authority 稿发现与关闭

初稿：`/home/dev/gdds-s5-logs/execution/e-authority.sh`，SHA256=`f58008d38bee13db61d8c2bd46f81c897481717c2fdfd75f355f7466cf1a241c`，尚未执行。

**E1（工具 metadata，执行前修正）：** ADMIT 的占用 marker purpose 仍写“S5 D focused checks ... no full runner or Compose”，与 E 六包/Compose及保留到 H 绑定的实际用途相反，影响节点占用用途可解释性。要求只改为真实用途，不改执行范围或启动产品。

修订稿 SHA256=`8aa001aeb3002232d060e519868dfaf9a496a59e904711a098ea2299823e0fab`。本人只读核该行现为“S5 E fixed candidate ... authoritative six-package runner with Compose; retain source inputs until final H binding”，其余执行编排未变。E1 **CLOSED**。没有产品失败或 DC68 修复轮次发生；协调者报告的本地 bash-n 不是本人执行或产品证据。

修订稿可执行范围与理由：

- candidate/rust/tree/ancestor、main clean、LAN bundle摘要、节点枚举、执行时现场检查与原子本人占用均有 guard；新 WT/refs/证据路径不得覆盖既有路径。
- RS 使用本人新 WT 的正常 `.venv`，受控 wrapper locked/offline sync；三 dependency-base 核实际 lock/input label，RS 在本机 network=none build，client 由原 owner 核当前 candidate/lock 并正常重建；不手工 rmi。
- backend/worker 设置预置 dependency-base=1、固定 lock tag、network=none，不启用 PREBUILT；Compose保留本机 build。生产 Compose 明确 N1、32GiB envelope/8GiB reserve/M24；pytest/Cargo workers4与产品配置分列。
- `run-tests.sh` 不传包裁剪或业务 `--project`，实际选择全六包；其 native 强制重装/build-input、六份 manifest、Rust fmt/clippy/test及五 Python 包/适用 Compose由同一权威入口拥有，不另外重复 Compose。其内部既有汇总执行策略不变；入口非零后 wrapper 不做后续验收/身份步骤。
- 镜像记录使用 docker-save config原字节SHA和全部 RootFS DiffID，另记本机image ID与过滤label；不将 containerd inspect ID冒 config digest。缓存来源/传输链及实际节点仍须在原件核收中验证，稿 GO不代表其现场已经满足。
- 逐步/入口 numeric exit、tee、UTC/HEAD、SHA与失败原件保留；安全收尾失败不释放本人占用。成功保留当前占用、WT、uv环境和镜像，直至同节点/同WT的最终 H闭包绑定完成，属于当前实际消费者，不是未来预约；失败安全收尾后仅释放本人 marker。

## 4. 证据与退出仍待完成

没有可用 qualified runner 来源：A/B/C/D均focused，不能carry。因此 V 全六包均须当前实跑并且整次权威入口0，Rust三步及适用 Compose不能省略。D五包ruff/mypy/native已在同一 vnext 产品实际通过，源码本轮未变，不另复制其focused矩阵。

t1 的独立 expected、合法状态/必要两节点前置、仅本人派生冷态、一次冷 History/新key新operation暖查、实际 records与完整tar、warm kernel/单侧summary/Dolt行读0和分层计数、M24真实cgroup peak与预约高水位仍须审固定稿并核实际原件。本报告不批准尚未收到的 t1 稿，不推断真实成功。

最终文档 H 必须在 V 来源的同节点/同 WT、保留环境/选定镜像及 runner实际profile（包括 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`、逐包且不存在的 Hypothesis path）计算六包 manifest并逐项compare；再独立核 V..H镜像边界/RS source labels与backend binding。仅产品树相同、换WT或跨节点都不能代替。实际日志/SHA、起止HEAD/UTC、原始失败、cache/镜像来源与资源释放由本 E 原审后续核收；满足全部条件后才能给 E EVIDENCE_GO/退出回执及本地附注tag，不push。

Current HEAD：`16317606d4c5ea357f7b07132f71f5ab4cd783bd`。Container rebuild required：**yes，S5阶段最终候选门禁**。Last verified image revision/source：仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`，原身份SHA256=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算或新增carried。Current container gate：**NOT_RUN/deferred to this E authority**；Carried from：none。没有 E证据、t1或 S5退出预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-r1.md`；SHA256：`a537173a98e827b6eaa1806e40b479e50d21854f81eea5bdcabcf2da042c81cc`。

---

# P6 S5 E t1 固定执行稿独立审核 R1

结论：**SCRIPT_CHANGES_REQUIRED**。当前不可执行；四项工具/取证问题须以新固定稿修订并由本原审连续复核。没有运行产品、语法检查或本稿，没有 t1 实测、E EVIDENCE_GO 或退出预签；S5 产品 CODE_GO 不因这些外置稿问题改变。

## 固定对象与审核边界

- 被审固定稿：`/home/dev/gdds-s5-logs/execution/e-t1-r1.py`，SHA256=`0b72e6a1e11d37061df8461e1dcb7f978e3f3a74f120536597fde62299058abf`；`e-t1.py` 当前同字节，实际执行应使用 immutable 版本名而不是可变 alias。
- 初稿 r0：`/home/dev/gdds-s5-logs/execution/e-t1-r0.py`，SHA256=`eaf27d8e43bb8dd5fcc3b7daf7467b6267cc655b369192751c7dec6dd18ee5b6`，已核与初送审SHA一致。审核期间实施者自修所有权 guard 并告知，r0/r1均未执行，不计节点/DC68修复轮次。
- 只读审核 WT仍为 `/home/dev/gdds-reviews/p6-s5-e-16317606d4`；固定 V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`，vnext=`8a28a9ab172d967eb526132084ec2b43b34b7c04`。
- 本人完整只读核两版本差异及 r1全文，追实际 journey/harness、History节点解析、完整tar/records facade、RS route/logging、canonical/export schema及原t1基准。没有访问节点或启动任何执行者/产品；本地只读 package SHA和 SQL源文本核对不是产品运行或新正确性oracle。

## 必须修订

### ET1-1 — P2：ORDERED 代表记录错误要求 values 含 gid

`BundleConsumer.check_records` 从 ORDERED family 的 before/current_values 读取 `values["gid"]["text"]`。实际 `comparison/ordered.rs::resolved_value_columns` 与有效 Ordered policy 的业务value列排除 gid/no；added/deleted ORDERED locator使用 `value_columns.clone()`，STANDARD locator才使用 `selected.clone()`。`records/source.rs::build_ordered_records`忠实出版该业务value集合。合法结果会在读取 gid 时 KeyError，无法到达真实冷/暖核收。

最小修订：以固定SQL中的gid按既有 Shared Canonical Encoding/row-identity公式独立手算expected identity，再校验实际 row_identity、位置和业务 name；或通过真实STANDARD记录的含gid值及独立identity关联。不能改变产品ORDERED schema、用当前codec actual生成expected，或删除六个代表记录/三删三增断言。

已直接只读核本机两package SHA分别为 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`、`4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`；SQL确为 gid8/9/10 在no9/10/11删去、gid28/29/30在相同位置加入，name与稿中常量一致。手算代表来源成立，需修其消费方式。

### ET1-2 — P2：完整导出 schema 只有记录和自比，未核回精确commit authority

`catalog()`将当前完整Catalog立即缩为`{name: row_count}`，丢掉列序、类型、nullable、key等事实；`inspect_history()`只保存`str(table.schema)`，最后比较冷/暖两份当前结果。现在能证完整表名/每表count及冷暖schema相同，但不能证每表导出schema符合两个exact commit的已核authority。相同导出错误可在冷暖重复并通过。

最小修订：保留两个exact-commit Catalog的完整schema事实，在不增加RS rows读取的条件下，按既有canonical/client export profile核全部Parquet字段名/顺序/类型/nullable及适用encoding metadata；SET按owning逻辑声明处理，不能把Repository list和内部text物理profile直接等同。对完整表名/count仍保现断言；全部表content摘要与冷暖比较继续保留，代表逻辑值独立expected继续由固定SQL/既有golden提供。无需扩成全档或额外旅程，也不要求每表新增旧源值oracle。

### ET1-3 — P2：计数观察混用了不可见diagnostics与尚未汇总的metadata

两个独立接缝须同时修正：

- 冷态强制 `row_stream_admission_acquired > 0`。RS diagnostics只是普通命名logger的INFO事件；本产品启动为标准uvicorn且未为该logger接INFO handler。该事件不一定出现在Docker logs，不能将其设为已存在证据的硬前提，也不能在缺日志时把实际admissions写成0。已有真实HTTP `/rows?...` access log的正冷校准足够支持同栈暖窗口零rows请求；admissions仅在本栈确实可观察时分列，否则明确`null/unsupported`，不改产品日志配置或扩大取证。
- worker delta保留了` s5_history_metadata `与` s5_history_demands `，但结果未解析canonical metadata reads、control metadata resolves、demands/export hits等实际计数；仅RS catalog HTTP次数不是全部metadata输入。按已审清单将既有日志值解析、校验所属本次窗口并分列，保pair metrics中的diff lookup、restore、records validation、digest rebind和kernel/单侧summary，不合并成“零I/O”。不需要新持久evidence、profile或重复HTTP请求。

暖态仍必须新key/newoperation，比较/单侧summary为0、健康persistent restore确发生、实际RS rows请求0；不能为了可观察性修订放宽这些业务断言。

### ET1-4 — P2：运行secrets位于将递归归档的evidence根下

当前 `j._compose_environment(root / "secrets", ...)` 把session/bearer材料写进driver输出根。协调者已明确外层会递归LAN复制该journey evidence；原稿因此会把凭据材料一起归档。此接缝由协调者在准备外层时提出，本原审追 `_write_compose_secrets` 确认。

最小修订：显式传独立 `--secrets-root`，放本run的节点私有runtime目录且位于exported evidence之外；核新本人目录、与输出/源码边界不重叠，harness仍正常读取，不打印内容、不纳入SHA/归档清单。不改变真实业务认证或产品接口，不把凭据复制到报告。后续版本与外层须一起核对该接线。

## 已关闭或可接受的范围判断

- r0未取得stack所有权时的finally可能按碰撞名字stop已有栈。r1新增`owns_stack=False`，container/volume/network三项空名守卫后才置True，finally只操作已拥有的新stack；已独核r0→r1仅这些变化，此项在r1静态关闭。后续仅新版本修订，不再覆盖r0/r1。
- v2只需finalized Submission即可作为合法History节点，**不需要额外Archive**。实际 `sqlite_history_compare.resolve_node_ref` 对submission按repository/submission解析exact commit，无Archive/Review eligibility要求；当前v1 Archive只负责为v2创建合法业务baseline。保现最小两节点前置，不以措辞扩旅程。
- 两次Preview/Submit/approve、仅v1Archive均走真实现有CLI/helpers与正常状态机；固定包SHA、旧t1 125表/3733与3731总行、v2四变化表、History12/风险0、composite4/4均有旧来源。XML相同只证本稿使用的composite不变，不作为新codec oracle。
- `_compose_environment`强制PREBUILT已被显式移除；外层禁ambient PREBUILT，backend使用dependency-base1/networknone并保Compose本机构建。current源码Compose明确N1/单active，driver显式M24/envelope32，cgroup max32/OOM检查与operation预约HWM分列；实际runtime身份/资源由原件核收，不据固定常量预签成功。累计cgroup peak应按其窗口/是否重启如实标注，不冒独立每operation峰值。
- cold脚本仅作用本人新stack及指定repository的五类derived索引；worker停止、BEGIN IMMEDIATE内核全部非derived表前后hash相同，保authority manifests、commit、protection与全部physical files。后续canonical读取确由index miss进入exact-commit RS兜底，不需删冻结/共享文件。
- 下载保存四个完整单次tar（两必要Preview、冷/暖History），实际调用 `verify_bundle_tar`、`open_records_closure`及显式close的records stream；没有虚构records HTTP端点。ET1-1/2修正后仍保真实content/count/schema验证和完整tar长度/ETag/闭合；不能仅raw SHA代records语义。
- 真实t1不承担FULL、三节点、损坏/恢复、所有取消点或容量矩阵；这些仍归已核focused owner，不加真实轮次。两个History时间仅一次观察，不计算重复统计或同条件提速。

## 继续与证据边界

新 r2应固定新文件名/SHA，保r0/r1及本报告原字节；由本E原审核者复核以上四项和增量后才可签SCRIPT_GO。外层尚未独审，须保证六包authority整次exit0之后、另合格节点/本人原子占用、clean已提交WT+legacy、native强制重装/build-input、offline/cache与镜像来源、运行settings、numeric exit/UTC/HEAD/SHA、失败停止与本人资源收尾；不改authority已选镜像/环境，不破坏其同WT H绑定。

没有脚本或产品执行发生，以上均执行前修订，不以本报告反推t1实际通过。最终原件/退出仍由本E原审另核；不push、不提前tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-r2.md`；SHA256：`f4d2aaff03b237ed78ae6e21b7bc4e0f114ac045bd2d5c3f17121498a6cf23b6`。

---

# P6 S5 E t1 连续执行稿复审 R2

结论：**SCRIPT_CHANGES_REQUIRED，r2不得执行。** ET1-2/3/4已静态关闭；ET1-1的消费方式已修，但新增独立identity手帧使用了错误整数载荷，仍会使合法结果失败。需新固定r3最小修正后由本原审连续复核。未运行语法/产品/节点命令，不计DC68执行修复轮次；不签t1实测或E证据GO。

## 固定对象

- r2：`/home/dev/gdds-s5-logs/execution/e-t1-r2.py`；SHA256=`0c4b6d4582689e588532eff9791c47477e0606a900e012c290cecb68ca70568a`。
- r1：`/home/dev/gdds-s5-logs/execution/e-t1-r1.py`；SHA256=`0b72e6a1e11d37061df8461e1dcb7f978e3f3a74f120536597fde62299058abf`。r0/r1/alias原字节保持，本轮完整只读核r1→r2增量及受影响实际接口。
- 产品仍固定V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`，未改产品/Contract/锁/golden。本人未实现修订、未访问节点、未执行任一稿或其语法检查。
- R1原件：`/home/dev/gdds-s5-logs/reviews/e-t1-r1.md`，SHA256=`a537173a98e827b6eaa1806e40b479e50d21854f81eea5bdcabcf2da042c81cc`。

## ET1-1 仍待修正的确定错误

r2 `check_records.identity`将 unsigned gid标量写成`0x11 + len(decimal_text) + decimal_text`。这不符合owning编码：[Shared Canonical Encoding §3]( /home/dev/gdds-reviews/p6-s5-e-16317606d4/docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md )规定unsigned integer payload为**8-byte big-endian unsigned**，scalar frame为tag+最短ULEB128长度+payload。`gateway-shared-kernel/src/scalar.rs`的unsigned分支同样用`u64.to_be_bytes()`。

已追代表canonical gid为INT UNSIGNED，stable-key实际构造在`comparison/ordered.rs`用字段数1、字段名gid，再拼该scalar frame并调用row语义域摘要。因而手帧应为：

```text
domain = b"gateway-vnext:row:v1\0"
row_frame = b"\x01\x03gid\x11\x08" + gid.to_bytes(8, "big")
identity = SHA256(domain + row_frame).digest()
```

六个gid均在unsigned范围内，不需要新decoder或本次codec actual。当前r2的六个expected identity全部不同于合法产品identity；不能执行后再把结果当产品失败。最小新r3只修此独立frame及错误注释，保真实六条ORDERED的kind、semantic kind、REAL_STABLE、identity、position/name、对侧空values及禁止gid/no混入业务values的断言。

## 原finding其余关闭依据

| Finding | 当前修订与实际接口核对 | 结论 |
| --- | --- | --- |
| ET1-1 原gid消费错误 | 不再从ORDERED业务values读取gid；改用binary row_identity映射手算预期，仍保六条三删三增与位置/name。实际records schema与value_columns边界相符，但上节手帧还错。 | PARTIAL，仍OPEN |
| ET1-2 完整schema | Catalog保`VersionedCatalog.model_dump(mode="json")`完整columns/sql_type/nullable/primary_key；schema expected来自该exact-commit authority。逐表构造字段均对应真实Catalog模型和SnapshotColumnDescriptor，`canonical_source_descriptor`实际只读table/display/columns/primary_key；再经`canonical_columns`→`source_descriptor_from_arrow`取得同一canonical declaration，`_arrow_field`与`encode_source_columns`核完整Arrow fields和encoding bytes，并核repository metadata。不造content/digest/cache-key，不从下载schema反填。SET使用原owner profile。PK保authority记录，明确Parquet无PK字段可直接核，未虚构验证。完整表名/count、全表content摘要与冷暖比较保留。 | CLOSED |
| ET1-3 分层观察 | 冷态仍强制真实HTTP rows请求正校准，暖态强制HTTP rows0及kernel/单侧summary0、restore>0、新operation；admission诊断仅冷态确实可见时检查，否则结果为null且observable=false，未将未知写0。metadata/demands从同worker delta解析全部实际记录，核非负整数并保逐条及totals，与HTTP catalog和pair counters分列；不假定记录只出现一次。无新日志配置、profile或HTTP读取。 | CLOSED |
| ET1-4 secrets | 新必填`--secrets-root`须absolute/new，禁止与export evidence互相包含及落源码/真实输入树；两处真实harness参数均接该目录，`root/secrets`已删除。当前结果不打印secrets内容；外层须将其放私有runtime且不递归复制。 | CLOSED（driver部分，外层接线另审） |

r1的owns_stack所有权guard、固定输入/合法v1 Archive与v2 Submission节点、五类本人派生索引冷态、完整tar/真实records、M24/cgroup与HWM分列、首失败/本人stack收尾路径保持。范围没有扩成FULL/三节点/额外真实矩阵。

## 后续边界

新r3固定文件名/SHA，保r0/r1/r2和本报告不改；本原审核手帧增量后可给driver SCRIPT_GO。外层run稿仍须另审，必须在authority整次exit0后、另合格节点及本人原子占用、offline/clean/committed+legacy和正确native/镜像前提下执行，不改authority选中环境/镜像；实际日志、SHA、起止HEAD/UTC、资源与占用释放另核。没有实测/证据/退出预签，没有push/tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-r3.md`；SHA256：`910ae796c27415936dded66d325f3e07d81f7ec0a4237724a4e0ad2610d523da`。

---

# P6 S5 E t1 连续执行稿复审 R3

结论：**DRIVER_SCRIPT_GO**，仅绑定 `/home/dev/gdds-s5-logs/execution/e-t1-r3.py`，SHA256=`312dc2eb1dcb5bdd83df1b2ac5fcd153606a3b98b599978c72c686250cf9941c`。R1四项finding均静态关闭；外层run稿仍须另审，当前尚无t1实测、E证据或退出GO。

本轮只读逐行核 r2→r3：仅独立identity表达式及相邻注释变化。r2 SHA仍为`0c4b6d4582689e588532eff9791c47477e0606a900e012c290cecb68ca70568a`，错误稿保留不可执行；R2报告原件 `/home/dev/gdds-s5-logs/reviews/e-t1-r2.md` SHA256=`f4d2aaff03b237ed78ae6e21b7bc4e0f114ac045bd2d5c3f17121498a6cf23b6`。r0/r1和原报告不改。

ET1-1现在使用`gateway-vnext:row:v1\0`语义域、一个gid字段的row frame、unsigned tag11/长度08及`gid.to_bytes(8,"big")`；与Shared Canonical Encoding §3/§5、canonical INT UNSIGNED和旧stable-key路径一致。expected只取固定SQL六个gid/位置/name，未调用新codec或捕获实际identity；实际binary row_identity与六条三删三增、REAL_STABLE、业务values/对侧为空断言保留。**ET1-1 CLOSED**。

ET1-2完整Catalog→owning canonical/export schema/encoding metadata核对、ET1-3真实HTTP冷正校准/暖0及metadata分层、ET1-4外置private secrets-root均与已复核r2相同，继续CLOSED。已核owns_stack guard、合法v1Archive/v2Submission最小前置、本人五类derived索引冷态、完整四tar/真实records、M24及cgroup/HWM区分、固定source/inputs、新key/newoperation、实际kernel/单侧summary/RS rows暖0均未放宽；不扩真实矩阵。

本人未访问节点、未执行任何稿、语法检查或产品测试，未实施代码、创建子agent、push/tag。上述r0–r3均执行前修订，无DC68节点修复轮次。

唯一E测试者只能在外层固定稿也获GO后、authority整次exit0之后，于另一个合格空闲节点取得本人原子占用，按offline/clean已提交WT+legacy/native强制重装及build-input/镜像与缓存来源等规则执行本r3。外层须将`--secrets-root`置于export evidence之外并排除归档，保存原numeric exit/UTC/HEAD/SHA，核本人stack及占用收尾；实际runtime N1/M24、资源统计及原件之后另核。不以driver稿GO代外层或真实成功，不改authority保留环境/镜像，不凭同树口头carry。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-binding-r1.md`；SHA256：`4881640d8c4577470dbcf3cc95b0c772dda6398c21e51e3eb278fb190e83138b`。

---

# P6 S5 E 最终 H 绑定稿独立审核 R1

结论：**BINDING_SCRIPT_GO**，绑定 `/home/dev/gdds-s5-logs/execution/e-bind-h-r1.sh`，SHA256=`9c1022940c4a8ab51f5068bd4c9c4f2c36ada79544ce1c5388bda000ded80c1f`。未发现新的脚本阻塞。此结论仅覆盖绑定编排，**不表示当前authority已通过、H已形成、六包可沿用或S5_EXIT_GO**；这些均待实际原件及精确H审核。

## 固定对象与独立性

- 固定来源 V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`，vnext=`8a28a9ab172d967eb526132084ec2b43b34b7c04`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- H为必填完整40hex、不同于V、main精确HEAD且clean；V须为其祖先，只许docs/AGENTS差异且产品树完全不变。具体H技术/授权文字仍由原审在形成后核对，路径白名单本身不是内容核收。
- 实际来源约定为authority的06原WT `/home/dev/gdds-test-tmp/wt/p6-s5-e-authority-16317606d4c5ea357f7b07132f71f5ab4cd783bd`，原marker/运行目录保留。同源hostname校验防止把另一节点相同路径当来源；节点枚举不授权搬迁carried。
- 本人完整只读核323行稿及实际runner/closure/build-identity接口；没有访问节点、执行该稿/语法检查、产品测试、sync/build/save/tag，没有编辑产品或创建子agent。协调者的bash-n结果不当本人验证或实际绑定证据。

## 关键核查

| 边界 | 实际稿与源码核对 |
| --- | --- |
| 合格来源 | admission先核原session candidate/finish HEAD均V、node为当前host、session与cleanup0、clean、原marker保留；authority-six唯一step的HEAD/command/tee0和原log SHA一致；原日志六包均唯一passed，after-image原件存在。authority尚未结束时缺finish字段即拒绝，不会提前计算carry。 |
| 同WT与冻结 | 复用原WT/环境/镜像，只读核无Dolt/pytest/uv/Cargo进程、无运行容器和8000。本人原marker已持有，不另抢占。bundle经命名ref、源V prerequisite、完整SHA/advertised H/clean/ancestor/tree核验后，仅检出纯docs H；不sync、不改锁/venv、不重build或retag。全部产物写worktree外。 |
| 原始manifest提取 | decoder仅接受column-zero JSON且schema=`gateway.vnext.test-input-closure`、精确包名、sourceV/currentH与clean/worktree_head一致，要求每包恰一份；保存原JSON fragment及source-log SHA。与实际`test_input_closure.py`输出字段、prettyJSON及版本验证入口一致，不用摘要转录代原manifest。 |
| 实际profile | 沿authority PATH前缀/禁设Rust变量、TMPDIR、offline、Cargo/pytest workers4、normal项目venv、backend依赖base1/networknone、相同RS/client/base tags、同provenance路径及M24/envelope32。额外显式恢复runner实际导出的`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`；GATEWAY_RUST_BUILD_INPUT未误带入。环境任何实际差异仍由compare拒绝，稿不掩盖或改预期。HOME/root Dolt配置前置只读核验，不写原profile。 |
| Hypothesis/六包compare | rust不设Hypothesis；五Python包分别设原固定TMPDIR下包路径并要求不存在，不删除残留来制造可沿用。每包当前manifest、owner compare和独立assert均运行，必须status可沿用、changed_components空、source/current/compare总摘要相同且V/H一致。source直接指此次实际runnerV，无focused/链式/跨节点来源。 |
| 镜像绑定 | H上由实际owner重新生成RS build identity，核candidate为H且build-input/source-tree等V原save身份labels；所有原after-image项逐个核同节点本机ID、完整DiffID及过滤labels不变。原config digest沿用V实际docker-save原字节SHA，不把inspect ID改称config，也不为绑定再save/build/retag。backend/worker另由合格六包backend manifest判等，保原Composeprovenance；与阶段退出两类规则分别核对。 |
| 失败/收尾 | 逐step记录HEAD、UTC、numeric command/tee和完整SHA；首失败停止后续绑定，保原日志和已检出状态，不自动restore/重试或清环境。原marker保留到独立EXIT_GO，即使失败也不自行释放。local/remote入口、tee、LAN copy及copied SHA核对分别记录，local最终清单在session结束后生成。 |

script完整接口中`compare`的`status/changed_components/source_total_digest/current_total_digest`、manifest的`head/worktree_head/clean_worktree`、RS`candidate_sha/build_input_revision/source_tree_sha256`均与当前实际owner一致。没有把同树当口头carry或把本机ID拿去跨节点比较。

执行仍仅由唯一E测试者在authority整次0、t1必要结果核收后，绑定原审已核的精确纯docs H；actual环境/闭包若有变化应停止并保原件，不改预期或跨节点重算“等价”。本稿GO不授权提前tag、push、产品修订、资源增额或扩大真实范围。

## 最终 H 与外置回执闭环

已核实施提示词/kickoff/AGENTS/testing conventions：要求报告外部原件与逐字归档、最终H与独审回执、实际同源绑定及条件满足后本地附注tag；**没有明确要求在tag后再提交一个把含H回执写入H自身的文档提交**。

协调者拟定的最小闭环可接受：先实际核authority+t1，形成不预签最终H的E CODE/EVIDENCE_GO；逐字归档此前报告/证据并以纯docs提交形成H，handoff写预定最终原件路径、来源规则与待核条件，不写自己的SHA；本稿在来源同node/WT实际绑定H；本E原审另出包含exactH和实际绑定SHA的外置`e-exit-review.md`，其原字节与SHA保存在外置archive。只有EXIT_GO后本地annotatedtag精确指H，main保持clean H，最终回复链接handoff、tag和外置receipt。H由tag/回执解析，不为自引用制造H2/G。

这里“外置archive”仍须真实保原件并可追溯，不是口头声称归档；所有既有需tracked逐字归档的E报告应已纳入形成H的文档。最终回执核收及marker释放仍另记录实际动作。本判断不改变既有证据/失败/未知保留规则，不预签当前尚未出现的原件或H内容。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-code-r2-initial-794.md`；SHA256：`2709dad125cfc877148859f3a29ff5456e4b7145437db2728ad759e1e3cfedf8`。

---

# P6 S5 E 连续产品复审 R2（History checkpoint诊断consumer）

结论：**CODE_GO，绑定新候选 `79422787cdfe9bdd75b13a1ba29f2b6a66f6c709`**。旧harness将metadata-only checkpoint误当row-ready输入的已发生故障在源码中关闭；两个真实诊断consumer均接原exact-commit canonical reader owner。当前新候选尚未执行产品检查，不签focused/六包/Compose/t1或E证据GO。

## 固定对象与独立性

- 原被测V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`；新候选=`79422787cdfe9bdd75b13a1ba29f2b6a66f6c709`。
- 新vnext tree=`a444676302c0615e5f301c7cea22efeb4ff87959`，Rust仍=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 新clean detached只读WT：`/home/dev/gdds-reviews/p6-s5-e-79422787cd`；创建后与报告前核exactHEAD、detached、index/tracked/untracked clean，legacy链接正确。旧被测authority WT没有被本审访问或修改。
- 区间唯一产品路径为`vnext/backend/tests/support/compose_gate_harness.py`，111增/103删；完整逐行核增量、生成脚本的实际imports/字段/参数和两个caller，追canonical metadata binding/UOW、exact HTTP provider、ensure、canonical reader/native消费/关闭。没有业务实现、Contract、依赖/锁、Rust、SQL或业务golden修改。
- 本人没有实施修订、创建子agent、访问测试节点，未运行语法/产品测试、lint/编译/镜像或任一执行稿，未push/tag。原163的CODE_GO不被直接移作新候选结论。

## 原始失败与边界

只读原local tee：`/home/dev/gdds-s5-logs/execution/e-authority/20261109T105237Z-16317606d4c5ea357f7b07132f71f5ab4cd783bd/remote-session.stdout.log`。此时文件仍在随权威runner内部汇总写入，最终SHA/入口numeric exit尚待自然收尾，不能提前填完整证据SHA或成功结论。

已出现的实际事实：backend parallel **3642 passed**；serial **1 failed / 79 passed / 3642 deselected**，唯一失败为`tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`。真实History已SUCCEEDED，后续`local_history_compare_digest_from_materialize_checkpoint`把C的metadata-only sides直接交完整surface pipeline，`export_snapshot_table_parquet`拒绝缺scoped canonical reader。其后ordered facts诊断同样依赖rows，首失败时尚未执行。原远端digest一致性断言是test中明确声明的integration binding检查，独立业务golden继续由C/D冻结向量拥有。

旧整次runner即使其他包通过，也不能成为qualified来源；后续正式六包不能从其拆出“已过四/五包”carry。保首失败、末入口numeric exit和全部旧原件，不把本次修后代码结论改记成旧运行成功。

## 修订核查

| 边界 | 源码核查结果 |
| --- | --- |
| 两个真实consumer | 抽出唯一`_history_checkpoint_readers_script`，只共享原checkpoint读取/必要rows接线。local digest consumer仍调用真实`_run_pair_pipeline`，ordered facts consumer仍走真实plan/compare/native ORDERED batches；原remote digest相等、状态不DEGRADED及added/deleted/modified三类records断言全部保留，没有改expected、返回远端actual或绕过验证。 |
| checkpoint/exact scope | `_sides_from_materialize_checkpoint`仍由原owner严格解码v5/v2闭包、descriptor/storage facts及repository/ref/resolved exact commit。每distinct commit再按实际Compose DEVICE_KEY/PROJECT_ID/repository解析`commit_canonical_metadata.resolve`；caller fixture确使用相同scope。`canonical_binding_for_commit`取owning完整manifest/storage view/schema/count/raw identities；没有猜main或造reader-ready布尔。 |
| rows与真实接口 | `ArtifactBackedCanonicalizationManifestReader(artifact_store=store, artifact_refs=store)`、`ControlDbUnitOfWork(...canonicalization_manifest_reader=...)`、`build_http_repository_provider_factory(base_url,bearer_token,timeout_seconds)`、`build_committed_table_access`及`ensure_committed_tables`均匹配实际接口。环境名由当前Compose实际提供，token从服务secret文件读入不打印。ensure核完整table-set/view/identity集合、descriptor schema/count/raw与ordered provenance，再只按给定exact commit加载；canonical cache缺失仍走原HTTP exact-commit兜底。 |
| 需求/预算/控制 | 此两个诊断真实消费全表：完整surface需要全部export，另一consumer检查所有table facts/ordered records，因此本helper请求该checkpoint的完整表集有consumer依据，不恢复生产History全表预读。诊断保N1/显式M24同一KernelExecutionContext；metadata、canonical mapping/FFI/native/export均使用当前scope。ParserInvocationContext明确传同context probe/deadline；原helper的NeverCancel诊断语义保持，不另造生产取消或恢复机制、pool或M40预算。 |
| 生命周期/失败 | 直接sqlite checkpoint连接用closing；每短UOW退出后才ensure。ensure本身关闭失败新增reader；此前已load的commit保在loaded并由finally关闭主/batch reader。ordered diagnostic先显式关闭ORDEREDbatch，再`product.close()`释放native；local pipeline沿原closing NativeComparison返回后，公共contextmanager才关闭所有canonical主/batch readers，最后退出kernel scope释放其余resources。中途失败同样按此顺序收尾，无宽catch或错误吞没。 |
| 删除/范围 | 删除两段重复startup/DB/side解码脚本，保一个owner接线；没复制blob、没从cache造权威输入、没改产品恢复/SQL/digest公式或删旧断言。无需为字符串helper新增同构mock测试；实际existing Compose case验证其真实imports/fields/容器consumer。 |

这不是放宽产品guard：修后consumer取得`CanonicalCommittedTableAccess`标记verified的实际Arrow reader，原`export_snapshot_table_parquet`验证不变。未知manifest/scope/输入/DB异常仍真实失败，没有把它们改成optional cache miss。

## 必要复验与容器决定

新候选的native/build-input、五Python包ruff/mypy及受影响唯一Compose case均 **NOT_RUN**。可交唯一E测试者在合格空闲节点、clean已提交WT+legacy、原子本人占用和offline依赖base/networknone下，先完成上述静态/native及当前HEAD重建的一条focused Compose调试；首非零停止，修后仍由本E原审连续复核。收敛后新最终V须全六包权威runner（Rust三步及同次适用Compose）实际整次exit0，不能用失败163的任何包carry；同次已覆盖Compose不另重复。真实t1仍待该正式authority0和更新后的固定稿/外层审核，不提前执行。

Current HEAD：`79422787cdfe9bdd75b13a1ba29f2b6a66f6c709`。Container rebuild required：**yes，实际Compose harness变更且需验证容器consumer**。Current container gate：**NOT_RUN/deferred to focused current-HEAD Compose and final authority**。原163 runner仅为失败原件/诊断，非合格已验证来源；历史最后完整成功镜像仍仅S4 V6786原来源，不签当前镜像或carried。

旧driver/H-binding/authority外置稿仍绑定163；后续只能新版本更新固定V/tree/SHA，不覆盖原稿或旧运行原件。当前没有E证据/退出预签、push或tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-code-r2.md`；SHA256：`9ecd47347f741b235213a733ddc527fbeb10d5c71f908f366a6aba424963ac4b`。

---

# P6 S5 E 连续产品复审 R2（History checkpoint诊断consumer）

结论：**CODE_GO，最终绑定新候选 `2d8b29d332ceb467ba77bb4826fb0925653ebb4e`**。初修为`79422787cdfe9bdd75b13a1ba29f2b6a66f6c709`；随后以标准ExitStack闭合单个close异常不能阻断其他reader收尾的接缝。旧harness将metadata-only checkpoint误当row-ready输入的已发生故障在源码中关闭；两个真实诊断consumer均接原exact-commit canonical reader owner。当前新候选尚未执行产品检查，不签focused/六包/Compose/t1或E证据GO。

## 固定对象与独立性

- 原被测V=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`；初修=`79422787cdfe9bdd75b13a1ba29f2b6a66f6c709`，最终候选=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`。
- 最终vnext tree=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`；初修vnext=`a444676302c0615e5f301c7cea22efeb4ff87959`；Rust均仍=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 新clean detached只读WT分别为`/home/dev/gdds-reviews/p6-s5-e-79422787cd`与`/home/dev/gdds-reviews/p6-s5-e-2d8b29d332`；各自创建后及最终报告前核exactHEAD、detached、index/tracked/untracked clean，legacy链接正确。旧被测authority WT没有被本审访问或修改。
- 区间唯一产品路径为`vnext/backend/tests/support/compose_gate_harness.py`；初修111增/103删，最终增量仅标准ExitStack及回调注册。完整逐行核增量、生成脚本的实际imports/字段/参数和两个caller，追canonical metadata binding/UOW、exact HTTP provider、ensure、canonical reader/native消费/关闭。没有业务实现、Contract、依赖/锁、Rust、SQL或业务golden修改。
- 本人没有实施修订、创建子agent、访问测试节点，未运行语法/产品测试、lint/编译/镜像或任一执行稿，未push/tag。原163的CODE_GO不被直接移作新候选结论。

## 原始失败与边界

只读原local tee：`/home/dev/gdds-s5-logs/execution/e-authority/20261109T105237Z-16317606d4c5ea357f7b07132f71f5ab4cd783bd/remote-session.stdout.log`。此时文件仍在随权威runner内部汇总写入，最终SHA/入口numeric exit尚待自然收尾，不能提前填完整证据SHA或成功结论。

已出现的实际事实：backend parallel **3642 passed**；serial **1 failed / 79 passed / 3642 deselected**，唯一失败为`tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`。真实History已SUCCEEDED，后续`local_history_compare_digest_from_materialize_checkpoint`把C的metadata-only sides直接交完整surface pipeline，`export_snapshot_table_parquet`拒绝缺scoped canonical reader。其后ordered facts诊断同样依赖rows，首失败时尚未执行。原远端digest一致性断言是test中明确声明的integration binding检查，独立业务golden继续由C/D冻结向量拥有。

旧整次runner即使其他包通过，也不能成为qualified来源；后续正式六包不能从其拆出“已过四/五包”carry。保首失败、末入口numeric exit和全部旧原件，不把本次修后代码结论改记成旧运行成功。

## 修订核查

| 边界 | 源码核查结果 |
| --- | --- |
| 两个真实consumer | 抽出唯一`_history_checkpoint_readers_script`，只共享原checkpoint读取/必要rows接线。local digest consumer仍调用真实`_run_pair_pipeline`，ordered facts consumer仍走真实plan/compare/native ORDERED batches；原remote digest相等、状态不DEGRADED及added/deleted/modified三类records断言全部保留，没有改expected、返回远端actual或绕过验证。 |
| checkpoint/exact scope | `_sides_from_materialize_checkpoint`仍由原owner严格解码v5/v2闭包、descriptor/storage facts及repository/ref/resolved exact commit。每distinct commit再按实际Compose DEVICE_KEY/PROJECT_ID/repository解析`commit_canonical_metadata.resolve`；caller fixture确使用相同scope。`canonical_binding_for_commit`取owning完整manifest/storage view/schema/count/raw identities；没有猜main或造reader-ready布尔。 |
| rows与真实接口 | `ArtifactBackedCanonicalizationManifestReader(artifact_store=store, artifact_refs=store)`、`ControlDbUnitOfWork(...canonicalization_manifest_reader=...)`、`build_http_repository_provider_factory(base_url,bearer_token,timeout_seconds)`、`build_committed_table_access`及`ensure_committed_tables`均匹配实际接口。环境名由当前Compose实际提供，token从服务secret文件读入不打印。ensure核完整table-set/view/identity集合、descriptor schema/count/raw与ordered provenance，再只按给定exact commit加载；canonical cache缺失仍走原HTTP exact-commit兜底。 |
| 需求/预算/控制 | 此两个诊断真实消费全表：完整surface需要全部export，另一consumer检查所有table facts/ordered records，因此本helper请求该checkpoint的完整表集有consumer依据，不恢复生产History全表预读。诊断保N1/显式M24同一KernelExecutionContext；metadata、canonical mapping/FFI/native/export均使用当前scope。ParserInvocationContext明确传同context probe/deadline；原helper的NeverCancel诊断语义保持，不另造生产取消或恢复机制、pool或M40预算。 |
| 生命周期/失败 | 直接sqlite checkpoint连接用closing；每短UOW退出后才ensure。ensure本身关闭失败新增reader；已ensure返回的每个主/batch reader立即注册标准ExitStack回调，单个close异常仍执行其余已登记close。ordered diagnostic先显式关闭ORDEREDbatch，再`product.close()`释放native；local pipeline沿原closing NativeComparison返回后，公共contextmanager才关闭所有canonical主/batch readers，最后退出kernel scope释放其余resources。中途失败同样按此顺序收尾，无宽catch或错误吞没。 |
| 删除/范围 | 删除两段重复startup/DB/side解码脚本，保一个owner接线；没复制blob、没从cache造权威输入、没改产品恢复/SQL/digest公式或删旧断言。无需为字符串helper新增同构mock测试；实际existing Compose case验证其真实imports/fields/容器consumer。 |

这不是放宽产品guard：修后consumer取得`CanonicalCommittedTableAccess`标记verified的实际Arrow reader，原`export_snapshot_table_parquet`验证不变。未知manifest/scope/输入/DB异常仍真实失败，没有把它们改成optional cache miss。

R2写初修稿时收到协调者/实施者只读指出的close异常短路接缝；本原审连续核`794..2d8`仅导入ExitStack、注册已返回两类reader回调并删除可能短路的finally循环。ExitStack保持在同kernel scope和yield的外层，真实native/batch consumer先完成，随后batch先于其主reader关闭；所有回调均被尝试，错误正常传播，无新cleanup框架或fault矩阵。该接缝在最终候选静态关闭，两个候选均未执行。未对外送出的794初稿原字节保存在`e-code-r2-initial-794.md`，SHA256=`2709dad125cfc877148859f3a29ff5456e4b7145437db2728ad759e1e3cfedf8`，本最终R2结论只绑定2d8。

## 必要复验与容器决定

新候选的native/build-input、五Python包ruff/mypy及受影响唯一Compose case均 **NOT_RUN**。可交唯一E测试者在合格空闲节点、clean已提交WT+legacy、原子本人占用和offline依赖base/networknone下，先完成上述静态/native及当前HEAD重建的一条focused Compose调试；首非零停止，修后仍由本E原审连续复核。收敛后新最终V须全六包权威runner（Rust三步及同次适用Compose）实际整次exit0，不能用失败163的任何包carry；同次已覆盖Compose不另重复。真实t1仍待该正式authority0和更新后的固定稿/外层审核，不提前执行。

Current HEAD：`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`。Container rebuild required：**yes，实际Compose harness变更且需验证容器consumer**。Current container gate：**NOT_RUN/deferred to focused current-HEAD Compose and final authority**。原163 runner仅为失败原件/诊断，非合格已验证来源；历史最后完整成功镜像仍仅S4 V6786原来源，不签当前镜像或carried。

旧driver/H-binding/authority外置稿仍绑定163；后续只能新版本更新固定V/tree/SHA，不覆盖原稿或旧运行原件。当前没有E证据/退出预签、push或tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-debug-r1-review.md`；SHA256：`86abafd9fcb68f742fda347cfebb9ec63515a8d6d1f9ee86241be153f829081c`。

---

# P6 S5 E 受影响Compose调试稿窄审 R1

结论：**DEBUG_SCRIPT_GO**，绑定 `/home/dev/gdds-s5-logs/execution/e-debug-r1.sh` SHA256=`1fe86442d3f610d877a21e7a9f4bedd0b25711432ae7b2f23759e74d79655be7`，candidate参数仅批准`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、Rust tree=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。源码GO见`e-code-r2.md` SHA256=`9ecd47347f741b235213a733ddc527fbeb10d5c71f908f366a6aba424963ac4b`。当前无任何本稿实际结果，不签focused、qualified runner或E证据GO。

本原审完整只读核相对已审D修订稿的全部增量，并核本稿身份/admission、remote日志/finish和实际执行块；未访问节点、执行稿/语法检查、产品测试或镜像。D模板的原件不被改写，协调者bash-n不冒本人或实际产品证据。

实际19步范围为：native强制重装、其余四包locked offline sync、build-input、五Python包ruff/mypy、两必要dependency-base精确label/input核对、本人专用RS当前source build、唯一既有`test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`以serial/-n0实际运行。已删client和backend大focused批次，没有完整runner或t1；Rust树未变不重复Rust编译检查，未来权威六包仍必须实际运行Rust三步。

关键边界保持：固定main clean/candidate祖先/vnext树与Rust树、LAN named bundle/full SHA、五节点枚举和执行时空闲原子本人marker、新runroot/WT/ref不覆盖既有路径、legacy、root Cargo PATH/selector四工具/禁设环境、UV/Cargo offline、磁盘TMPDIR及外置venv/Cargo/缓存/日志。RS正常项目`.venv`供既有harness使用；其余包用本人外置环境，所有uv走wrapper，不改锁。

新增容器部分使用backend lock578e与RS当前lock基线、networknone/预置base1，禁PREBUILT与代理，保持Compose本机正常build。N1由当前Compose固定、M24/envelope32显式，pytest worker数不冒产品N。RS专用tag隔离此调试，受影响case的正常harness自行构建backend/worker并保存provenance；没有要求无consumer的client镜像或另一个Compose旅程。

逐step记录node/UTC/HEAD、原numeric command/tee和日志SHA；首非零停止后续步骤，失败环境/原件保留。只有本人资源核空后释放本人marker，成功仅清本run列明的临时环境/缓存；不全局prune、不清旧163失败WT/镜像或他人资源。local/remote/tee/copy原退出分别保留。

执行前条件：旧163完整runner应先自然结束、保存最终numeric exit/原件并安全释放原节点；唯一测试者才能现场重新核空闲原子取得本debug标记，不能抢占旧执行。旧故障为现有harness消费假设失配的产品测试代码修复，不整体归DC68工具错误，不把旧失败改成功。debug成功后原审核原件，收敛到最终V2再全六包权威实跑；失败163不能拆包carry，t1仍禁止提前执行。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-run-r1-review.md`；SHA256：`8d964ef3cea79a6956f277612828d668e683b15dd558202a6f35c7aa7c908dda`。

---

# P6 S5 E t1 外层执行稿核心预审 R1

结论：**WRAPPER_CHANGES_REQUIRED；不批准执行当前旧V稿。** 完整只读核`/home/dev/gdds-s5-logs/execution/e-t1-run-r1.sh`（337行），SHA256=`7d221b8f9dba705de8db32316c7437f0ff85994c90a878f0a3fc9a2b8e7a0187`。两处工具接缝须最小修订；其余核心结构可供未来最终V2机械更新后连续窄审。当前绑定的163 authority已有测试失败，不能运行本稿；source资格guard会拒绝它。

本人未访问节点、执行本稿、语法检查、产品测试或镜像；未改产品、创建子agent、push/tag。原稿/失败source不改，执行前修订不计节点DC68轮次，未来换V/目录不重置任何实际同根故障计数。

## 必须修订

### EW1 — P2：private umask用于source checkout，RS降权后源码不可读

REMOTE_T1开头`umask 077`，后续直接`git worktree add --detach`，将正常tracked文件/目录建成0600/0700。RS Dockerfile直接COPY repository_contracts/src与repository_service/src，保源权限；仅chown数据与home，entrypoint随后降到gateway运行。新源码/Contracts仍root私有，合法RS镜像会在降权后无法读取/导入。

最小修订：只在新source WT checkout阶段使用022，使源码文件/目录可读可遍历，再恢复077用于私有运行/证据。不要改产品Dockerfile或事后递归chmod，也不能放宽runtime-secrets/evidence私有边界。绑定稿只检出docs、原authority稿未显式改remote umask，不能据它们推本新WT权限可用。

### EW2 — P2：兜底release把他人后来取得的合法marker当成本任务失败

remote finish安全释放本人marker后，local仍复制较大证据，再在EXIT执行guarded-release。此时其他任务可按现行规则原子取得该空闲节点；当前RELEASE的`test -f old-session-marker`会非零，继而把已经成功收尾的本任务outer改失败。该分支不删除他人marker，但错误处理了正常资源交接。

最小修订：与已审authority释放逻辑一致，只有marker仍属于本会话时才核空闲并释放；non-owned或already-released明确记录skip并0返回，不触碰他人资源。remote原release失败/unsafe仍保其原numeric非零，不能以local skip改成成功。无需跨会话预约、等待他人释放或扩大清理。

## 核心结构已核

- 本地source资格在SSH/占用前只读检查完整复制的authority session/steps、candidate与finish HEAD相等、session/cleanup0、所有step command/tee0、authority原log SHA及六包唯一passed。不会直接访问/轮询authority源节点；failed163不能过guard。
- driver必须给immutable绝对路径及固定审核SHA312dc，复制后与remote各再核SHA；source V/vnext/Rust/main clean/ancestor、LAN self-contained named bundle/advertised ref/fullSHA、新WT/path/ref/stack名均有绑定。未来必须同时机械更新V/tree/driver固定值，不能只改一个tag口头放行。
- 实际目标节点现场核空闲并原子本人marker，新namespace；本稿不操作authority来源WT/环境/镜像。独有RS tag、Compose名和runroot由V+driverSHA派生，避免覆盖原失败/他人状态。执行目标仍须另合格节点，现authority保留占用不可抢。
- 九步为工具链只读、input/base前置、driver AST parse、backend强制native重装、build-input、normal RS项目环境sync、RS source build、一次已审最小driver、成功后实际镜像身份。没有全runner、client镜像或额外产品tests；五包静态归最终产品debug/authority的既定检查，不在这里复制。
- PATH/Rust selector与禁设环境、UV/Cargo offline、本地预填缓存、Dolt global versioncheck只读检查、固定两t1输入SHA、两dependency-base lock/input label、backendbase1/networknone/noPREBUILT/无代理均接真实接口。driver实际CLI为`--compose-name --output --secrets-root`；secrets明确在RUNROOT/runtime-secrets、EVIDENCE之外，不参与递归SHA/LAN复制。
- 当前driver的真实最小前置/冷暖/records/tar由其独立GO拥有，wrapper不改expected。N1由固定Compose、M24/envelope32显式；实际资源和业务结果仍待原件核。
- 成功镜像步骤核driver exit/conclusion/stop0、实际三服务tag与运行container image ID绑定、停止态；本节点docker-save config原字节SHA+全DiffID并过滤labels，未把inspect ID冒config，不做跨节点ID等价。只有成功后做身份步骤，失败不继续验收。
- 逐step/remote/local/tee/copy及recursive hashes分别保numeric exit、UTC/HEAD/SHA；本人stopped容器/卷、WT/venv与失败raw evidence保节点，不全局prune。remote安全资源/marker检查和local兜底职责区分明确；EW2修正后按实际所有权收尾。

未来最终V2需先受影响debug收敛，再全六包authority整次0；新V2/driver与EW1/2的固定新版本由本原审连续核增量及真实source前提后才能签执行GO。旧163failed结果不可拆包carry，t1继续禁止提前执行。完整t1实测/最终H绑定/退出仍另核，本预审不是证据GO。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-debug-evidence.md`；SHA256：`5686ae3a87f203d5ce2b1274d7583a25778089468adc9c5d4f707566d0606ca8`。

---

# P6 S5 E：2d8 focused 原件核收与最终 V2 六包执行许可

结论：**DEBUG_EVIDENCE_GO / V2_AUTHORITY_EXECUTION_GO**。最终产品 V2 固定为 `2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext tree=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust tree=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。原 E 审连续核收本次 19 步 focused 原件，全部真实退出 0、受影响既有 Compose 用例通过，未发现新 finding。可由唯一 E 测试者用同一已审参数化 authority 稿，在新本人占用、新 clean committed WT+legacy 上实际完整运行六包及同次 Compose。**这不是六包 qualified source、E EVIDENCE_GO 或 EXIT_GO；t1 尚未获执行许可。**

## 固定对象与实际 focused 结果

- 执行稿 `/home/dev/gdds-s5-logs/execution/e-debug-r1.sh`，SHA256=`1fe86442d3f610d877a21e7a9f4bedd0b25711432ae7b2f23759e74d79655be7`；脚本前审见 `e-debug-r1-review.md`，产品连续复审见 `e-code-r2.md`。本次核前重新核上述稿 SHA、main exact HEAD/tree 与 clean；产品没有后续修改。
- 原件根 `/home/dev/gdds-s5-logs/execution/e-debug/20261109T112643Z-2d8b29d332ceb467ba77bb4826fb0925653ebb4e/`；实际 hostname=`gw-dms-06.lan`，session=`2026-11-09T11:26:46Z–11:29:13Z`。起止 HEAD 均为 exact V2，结束 `worktree_clean_after_checks=yes`。
- admission 原件记录此前无 Compose 栈、8000 空闲并原子取得本人的 `codex-p6-s5-e-debug-2d8b29d332` 标记；bundle 固定 ref/sha 与候选相符。结束原始 numeric exit=`0`、cleanup=`0`、marker released=`yes`；local remote/tee/artifact-copy/release/local 各退出也均为 `0`。
- 独立按 `steps.tsv` 逐行核 **19** 步、每步 exact HEAD、command/tee 两个 numeric `0`、每个日志实际 SHA。native 强制重装真实成功，扩展 build input expected=installed=`c0213e18a9645c5cfbd39f310f532273a03a10cb`；另四包 locked/offline sync 通过。五 Python 包 ruff 全部 `All checks passed!`；mypy 分别 shared_kernel 34、repository_contracts 15、repository_client 26、backend 542、repository_service 201 source files 无问题。
- 两必要 dependency-base 的完整 input label 与当前锁输入匹配：backend `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`、RS `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。RS 本人专用当前 source tag 实际正常 build。profile 使用 offline、backend 预置 base1、build network none、无 PREBUILT、显式 M24/envelope32，N1 沿当前 Compose 及诊断 scope 接线。此 focused 预检不是跨节点 true config 身份核验的替代，正式 authority 的实际 save config/all DiffID 仍须核收。
- 唯一产品测试命令为既有 `tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`，serial、`-n 0`，原日志 **`1 passed in 51.20s`**，command/tee=`0/0`。本用例真实执行修后的 local digest 与 ordered facts 两个诊断 consumer，保原 remote binding 与三类 records 断言；没有删除断言或反填 expected。
- Compose provenance 记录实际 backend/worker/RS container image ID，RS tag=`gateway-repository-service:p6-s5-e-debug-2d8b29d332ce`，当前 source labels 为 build-input `e76342ef0b58bb0120fc60d8a063d838140ee28d`、source-tree `sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`。本次触碰 harness 的当前 HEAD 重建及受影响 Compose 调试已完成；阶段最终容器门禁仍由后继完整 authority 拥有，不把本 focused 当作 qualified runner。

本人只在开发主机读取已复制原件并校验其摘要，没有 SSH/访问节点、实施源码、运行产品/语法检查/lint/编译/镜像/执行稿或创建子 agent。

## 原件校验锚点

本地完整 `SHA256SUMS` 与其 checksum 实际全项通过；remote 原 checksum 文件保留原测试节点绝对路径，核收时仅在校验输入中重定位到本地复制目录，11/23 个原件及 manifest checksum 实际匹配，没有改写原 checksum 文件。

| 原件（相对本次根） | 实际 SHA256 |
| --- | --- |
| `SHA256SUMS` | `c6881f5cf4f1c9ac38cfe6dcf98016b4209df50420961d3873bc3f8633c12068` |
| `remote-evidence/session.log` | `5832fdda2bdef79a166cec8cc1e27b48e44a8058d3cb73a888fabfaf65598ced` |
| `remote-evidence/steps.tsv` | `c46e7481e9e88766464248b95c8088af6fe41eac77694f6e46e3887f3b13551c` |
| `remote-evidence/affected-compose.log` | `f2e1e9a07c647820ae94b30ac5cf58a8b40815da498681a995d33fcb2896f1f6` |

## 旧 163 失败原件连续核收

另完整只读核 `/home/dev/gdds-s5-logs/execution/e-authority/20261109T105237Z-16317606d4c5ea357f7b07132f71f5ab4cd783bd/` 本地全项 checksum、原 remote manifest 重定位后的全项 checksum、原始 session/steps/runner/local finish。node06 session=`10:52:40–11:24:13Z`，authority=`10:53:29–11:24:12Z`，起止 HEAD exact 163、clean，runner command=`1`/tee=`0`，session/remote/local 原始最终 numeric 均 `1`，cleanup=`0`，本人 marker 已释放。runner 内部继续汇总 RS 是原入口行为，不是失败后另起验收。

Rust fmt/clippy/test 均 `0`；shared 261、contracts 152、client 170、backend parallel 3642 passed；backend serial 唯一 `test_ordered_history_compare_compose_journey` 为 `1 failed,79 passed`；RS parallel `1764 passed,1 skipped`、serial `214 passed`。真实 History 已 SUCCEEDED，local diagnostic export 因 obsolete metadata-only checkpoint 无 scoped canonical reader 而失败，原记录保留该 ValueError 与完整 traceback；2d8 关闭此已发生 harness consumer 问题，未把旧运行改记成功或归为未触及产品的工具错误。

旧原件实际 SHA：`remote-evidence/session.log`=`610d51755da59af1dd293ed9ab434c9bca20fe37b6d3432a1cd474d63767cd44`；`remote-session.stdout.log`=`bd7a4f770d104620678fe5e96f60ea1acadef1461b060f64e3156e2a921324fd`；`remote-evidence/authority-six.log`=`9cf9f29e5691ceaf17d769a23ef7089f6d617d131a77c57c050c9274a1deac11`；`remote-evidence/steps.tsv`=`6044cfbaab547df5a589b0243bd605ec3163982968ab78d5d7bb803edf672dc1`。协调消息把 session SHA 简称为 remote session，应区分 session.log 与完整 stdout；steps 以此原件实算值为准。

**旧 163 整次 exit 1，任何包均不是 qualified 来源。新 2d8 focused exit 0 也不是 authority 来源。A–D focused 同理，不允许从这些运行拆包 carry。**

## 同稿新 V2 执行许可与尚待事项

重新核 `/home/dev/gdds-s5-logs/execution/e-authority.sh` SHA256=`8aa001aeb3002232d060e519868dfaf9a496a59e904711a098ea2299823e0fab` 未变；全文没有 `163176` 常量，必需 `S5_E_CANDIDATE`/`S5_E_RUST_TREE` 驱动 WT/tag/ref/source 身份。原 `e-code-r2.md` 末段将包括 authority 的外置稿统称“仍绑定163”不够精确：旧实际执行确绑定163，但此 authority 稿本身参数化；driver、H-binding、t1 wrapper 才有需新版本更换的旧 V 常量。此处明确连续复核并批准同稿绑定 **V2=2d8 / Rust=c021**，无需仅为换参数另造脚本。

唯一测试者可在 debug 已释放后，重新核现场空闲、原子本人占用，以新 final-authority WT 按同稿实际运行全部六包，包含 Rust 三步与同次适用 Compose；不设置包选择、不复用 debug WT、不从失败 163 或 focused 拆包沿用。不再额外重复该次 runner 已覆盖的 Compose。首失败停止后续验收，保原件/退出，由原 E 审连续处理。

authority 成功后继续保留其 WT/env/所选镜像及本人有效绑定，直到最终纯 docs H 同节点同 WT 的六包 compare 与 image binding 核收。t1 driver/H-binding/t1 wrapper 有固定旧 V，须各自新 immutable 版本机械更新并按实际修订另审；wrapper EW1/EW2 仍待关闭。当前没有 t1 实跑、六包实跑成功、E证据/最终H/exit/tag预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-tools-r2.md`；SHA256：`130a4da8688277cbc14416c5874096536e385a697831004d5339d016775e8721`。

---

# P6 S5 E 后继工具稿连续窄审 R2（V2）

结论：**DRIVER_SCRIPT_GO / WRAPPER_SCRIPT_GO / BINDING_SCRIPT_GO**，分别只绑定下表不可变原件。wrapper 原 EW1/EW2 均 CLOSED；三稿除所述 V2 身份更新与两处最小修复外，没有其他增量。当前不签 t1 实测、qualified 六包、H carried、E EVIDENCE_GO 或 EXIT_GO。

| 工具原件（`/home/dev/gdds-s5-logs/execution/`） | 本次实际 SHA256 | 状态 |
| --- | --- | --- |
| `e-t1-r4.py` | `3c8507cb3c1cb463d2dc22970ff0e6d4122b1544e5e68b00e5ff1a4241cb7eb3` | DRIVER_SCRIPT_GO |
| `e-t1-run-r2.sh` | `2a6e9d5c221a6e3ce10f54c1a6e9f3cf63a866b76587b47d3b28498767c4ca4e` | WRAPPER_SCRIPT_GO |
| `e-bind-h-r2.sh` | `26069b7eaf3c77346e8d58c7cfe386f2127b10c518752fb6a7795c4f9aa1bf9a` | BINDING_SCRIPT_GO |

共同固定来源 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`、Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。产品 CODE_GO 与 focused 原件核收分别见 `e-code-r2.md`、`e-debug-evidence.md`，后者许可同 SHA8aa authority 完整重跑六包；本工具报告不把正在进行或尚未核收的 authority 写成通过。

本原审独立重新计算六个新旧原件 SHA、完整逐行比对三个增量，并复核 wrapper local/remote trap、checkout 前后、source 资格与最终复制退出顺序，以及 H binding 的原 source 路径、profile、两处 RS tag 和最终 image owner 接口。旧 r3 driver=`312dc2eb1dcb5bdd83df1b2ac5fcd153606a3b98b599978c72c686250cf9941c`、wrapper r1=`7d221b8f9dba705de8db32316c7437f0ff85994c90a878f0a3fc9a2b8e7a0187`、binding r1=`9c1022940c4a8ab51f5068bd4c9c4f2c36ada79544ce1c5388bda000ded80c1f` 均保持原 SHA。未覆盖旧原件/报告，没有产品变动；本人未访问节点、执行任一稿或语法/产品测试/lint/编译/镜像，未创建子 agent、push/tag。协调者后续 bash-n 不冒本人验证或实测证据。

## 连续核查

**driver r4：**相对已 GO r3 仅两行 V/VNEXT 常量更新，确切对应最终 V2/tree。独立 uint64 八字节大端 identity framing、合法最小 v1 Archive/v2 final Submission 前置、本人隔离 derived 冷态、一次冷 History/新 operation 暖 History、旧独立12 records/4 ordered/count125及手算代表、完整 catalog/schema/encoding metadata/四 tar/真实 records facade、HTTP 冷正校准与暖 rows0、metadata/demands/restore/kernel/summary 分列、M24/HWM/cgroup 区分、private secrets-root 与 owns_stack guard 均无变化。ET1-1–4 继续 CLOSED，不扩大真实矩阵、不改新 codec/golden/locks。

**wrapper r2：**V/Vtree/driver 固定 SHA 与 r4 完全一致，派生新 WT/stack/ref/RS tag/runroot 随 V+driverSHA 改变。实际 target 仍须另一个合格节点；本轮计划为04，authority06原保留环境/所选镜像不被操作。

- **EW1 CLOSED：**仅 `git worktree add --detach` 前切换 `umask 022`，完成后立即恢复077；正常 tracked source 文件/目录可被 RS 镜像降权后的 gateway 读取/遍历。runtime-secrets、后继运行及证据创建继续077；未改产品 Dockerfile、未递归 chmod、未放宽 secrets。checkout 失败仍停止后继步骤，不会先创建或导出凭据再以宽 umask 处理。
- **EW2 CLOSED：**local fallback 首先核精确本人 marker 文件与 `session=`，non-owned/already-released 记录 skip 并返回0，不等待/读取后继任务或删除其 marker。仍属本人时才核资源空闲并移除本人 marker。remote numeric exit 先记录于 `statuses[0]`，copy/hash 后仍优先以该原非零退出；local trap 仅当原 rc=0 才把自身 cleanup/copy failure 升为非零，因此 fallback skip0 不能覆盖原 remote failure 或 unsafe release。
- source guard 仍在 SSH/占用前核 copied V2 authority 完整 session0/cleanup0、原 log SHA/六包 passed/all steps0；原 failed163 将被 exact V/source 资格拒绝。offline、native/build-input、backendbase1/networknone/noPREBUILT、九步最小执行、secrets 位于 EVIDENCE 外、完整递归 SHA/复制及成功后 docker-save true config/all DiffID/runtime 同节点绑定均未变。

**H binding r2：**相对已 GO r1 仅 V/Vtree、marker session 的十位前缀 `2d8b29d332`、两处 RS tag 十二位前缀 `2d8b29d332ce` 更新；均与参数化 authority 的实际派生规则相符。RUNROOT/WT/EVIDENCE 随 exact V2 派生，未残留旧163/旧vnext常量。H仍必需完整40hex且 main exact clean，仅 docs/AGENTS 差异且 vnext/Rust 不变；实际 H 内容须在形成后另核。来源仍须原 authority06同node/WT/marker、整次 source0/clean/after-images；同 profile 含 SKIP_LOCK_ASSERT1、逐包原 Hypothesis path absent，全六包 compare changed=[]，当前 H RS owner identity与原 save labels及同节点 image ID/全DiffID/labels，均未放宽。无 sync/build/save/tag、不释放原 marker，失败保原件。原 final H/外置 exact-H receipt 归档闭环判断保持。

## 实际执行前提

本报告授予三个固定稿的静态 GO。**t1 只能在 V2 authority 整次实际0且原 E 核收后**，由唯一测试者在另04现场核空闲、原子本人占用，新 clean committed WT+legacy、offline/native/input/cache 身份前提下，用此 r4+r2 运行一次。不得因 driver/wrapper GO 提前启动或用旧163/新 focused 拆包 carry；实际结果、预算统计、完整 tar/records/logs/源身份与收尾仍由本 E 原审独立核收。

H binding 仅在 authority+t1 必要原件核收、E CODE/EVIDENCE_GO、tracked逐字归档形成最终纯 docs H并经原审核该精确 H 后，交唯一测试者在原 authority06同 WT/env/images 执行。实际六包/image 绑定与外置 exact-H EXIT_GO 尚待完成；tag/push均未预签，且仍无 push 授权。任何实际首失败保原件停止后继验收，同根 DC68 计数不因新文件名/V/节点重置。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-authority-evidence.md`；SHA256：`0e32da3c9c5b93395f961afa07b9b6f0aa50860ce420e2c86fa845e907c72317`。

---

# P6 S5 E：V2 六包权威原件独立核收

结论：**AUTHORITY_EVIDENCE_GO / T1_EXECUTION_GO**。当前固定产品 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。本次全六包（含 Rust 三步及同次适用 Compose）实际整次0，源码起止clean，后置镜像/source身份通过，是各包合格的最初实际运行来源。可按下述固定稿、范围及另节点前提执行 t1。**t1、最终 E CODE/EVIDENCE_GO、精确H绑定和 EXIT_GO 尚未完成，均不预签。**

## 原件与完整性

原件根 `/home/dev/gdds-s5-logs/execution/e-authority/20261109T113225Z-2d8b29d332ceb467ba77bb4826fb0925653ebb4e/`。实际node=`gw-dms-06.lan`，新WT=`/home/dev/gdds-test-tmp/wt/p6-s5-e-authority-2d8b29d332ceb467ba77bb4826fb0925653ebb4e`；session `2026-11-09T11:32:28Z–12:03:59Z`，authority `11:33:10Z–12:03:13Z`。本地收尾时钟记 `12:03:58Z`、比remote finish小1秒，保两机器原值，不据此改写UTC或推跨机同步精度。

重新实算本地完整 SHA256SUMS 及其 checksum 全项通过；remote checksum 保原节点绝对路径，核收时仅对校验输入重定位到本地复制目录，14个原件及 checksum 实际匹配，未改写原件。独立解析 steps.tsv：恰8步，每步 exact V2 HEAD、command/tee=`0/0`，各log实际SHA逐一匹配。步骤为3个依赖base预检、RS环境sync、RS source build、client当前revision owner build、before true image identities、全部六包权威入口、after true image identities、RS当前source identity；其中第一个预检是一个step核三镜像，native强制重装/build-input归runner内部，不冒另一个外部step。

| 原件（相对根） | 实际 SHA256 |
| --- | --- |
| `SHA256SUMS` | `d06f00a3216792da2b45e8ac44bbf6666b3853ffee36373ef5ae810ed39df0ba` |
| `remote-evidence/steps.tsv` | `3608a5aaaa61f2241494f42d74db30dc2ecfa0e4739ec7ef22a105d3d8bf283a` |
| `remote-evidence/authority-six.log` | `dff5f6c385ad17f6dbd6a932efdd91710d68e616b34d1d3d262795b284b50b69` |
| `remote-evidence/session.log` | `8abf7728540a3737ea1e24f2850ccaae2be0983767f349ab6523f74fd115d157` |

admission记录无栈/8000空闲，原子取得本人 `codex-p6-s5-e-authority-2d8b29d332`。bundle/ref/fullSHA与candidate一致；起止HEAD均V2、`worktree_clean_after_checks=yes`、session原numeric0/cleanup0，outer remote/tee/artifact-copy/local exit均0。`marker_retained_for_final_H_binding=yes`，source WT/env/images/evidence保留；成功路径本就不释放，因此没有local-release.log符合该稿行为。本人未访问节点或执行产品/语法/lint/编译/镜像/任一执行稿，只本地读取已复制原件并做stdlib摘要/JSON核收，未实施产品、创建子agent、push/tag。

## 全量运行与六包来源

authority命令原文是没有包选择和额外pytest参数的 `bash .../vnext/scripts/run-tests.sh`。日志含受控wrapper五包sync、backend强制native重装，实际extension expected=installed=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。Rust仓库selector四工具实际1.97.0，同Cargo PATH，禁设工具链环境检查正常；Rust fmt/clippy/test三个step status均0。完整结果：

| 包/批次 | 实际结果 |
| --- | --- |
| rust | fmt0、clippy0、workspace locked/offline test0 |
| shared_kernel | 261 passed |
| repository_contracts | 152 passed |
| repository_client | 170 passed |
| backend parallel | 3642 passed |
| backend serial | 80 passed，3642 deselected；旧失败的既有Compose case已在该完整批次中通过 |
| repository_service parallel | 1764 passed，1 skipped |
| repository_service serial | 214 passed，1765 deselected |

末六包status各恰一条passed，整次runner command/tee0，清理五包专属Hypothesis与Cargo target后仍0。唯一RS skip的原 `-q` 日志只记数量、不记nodeid/理由，不能说日志直接点名，也不能把skip算pass。当前源码的host入口及`test_p2_r1_target_cgroup_smoke.py`中 `GATEWAY_P2R1_TARGET_CONTAINER != 1` 条件提示其可能是target smoke；另有两个integration条件式skip，原run未保存该flag，故具体skip身份/理由仅推断，不能确定。没有事后current env冒run-time、没有补跑测试。S5未改RS服务/cgroup能力，没有据此发现本阶段必需consumer/invariant缺失；不扩展delegated-target验收矩阵，不影响该包与同次Compose真实exit0事实。

从原runner prettyJSON以column-zero raw_decode独立提取，六包均恰一份schema `gateway.vnext.test-input-closure`，head/worktree_head=V2、clean=true。逐包总摘要如下，H必须直接引用此次最初实际来源，不能引用后继carry：

| 包 | source total_digest |
| --- | --- |
| rust | `39758d7db4e41370f9d2a8ace9fe0483aefe0124d7126e54dc10ac045fa78b04` |
| shared_kernel | `123505051e2a08cd353c1bae51f26712dc3192bc2dde976452d71dfa807f43b0` |
| repository_contracts | `6c86e24ca0b701dc46382971fefef1f16386fb42eee13e08ff85920c68d38389` |
| repository_client | `3daf7071792232cb38fecc32d308e1ecd72f65ba7e4288fec7dff723c1461e1a` |
| backend | `41a96e760b6186a2d56e50ff0b634fdbb0ddd665af25196ccdbc5d49d86db770` |
| repository_service | `4d3cdcbada36ba82dcbb7639f22deafe6fc4e15e7093239adad36f50471fda28` |

backend/RS manifests实际vnext tree为fb92；有效build selections确是backend预置base1、networknone、PREBUILT=false。实际指纹核UV_OFFLINE1、SKIP_LOCK_ASSERT1、M24=`25769803776`/envelope32=`34359738368`，代理及P2R1 cache URL无设置；Rust环境实际CARGO_NET_OFFLINE=true，source session也记录两类offline。五Python manifest指向各自 `/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<包>`，起始均already_absent，结束按原runner清理；rust无Hypothesis。worker4不冒产品N，产品N1沿当前Compose默认与诊断scope。锁/env与registry隔离由当前已审wrapper及完整runner拥有，本次没有改锁、代理/公网下载或手工镜像替换的证据。

## 镜像、Compose与依赖来源

当次当前HEAD正常RS/client source owner build，然后同runner中的适用Compose正常构建backend/worker；没有设置PREBUILT，也没有另一个重复Compose验收。before/after身份来自实际docker-save的config原字节SHA，完整RootFS DiffID与inspect Layers已在执行中相等，非把本机manifest ID叫config。独立比较before的5个selected镜像与after对应条目，全部identity字段相同；after另含最终Compose实际三服务runtime IDs。当前原件全部8项及其完整DiffID保留，关键锚点：

| 镜像 | true config digest（sha256） | DiffID数 |
| --- | --- | --- |
| backend deps lock578e | `46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` | 19 |
| RS deps lock6dc9 | `98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |
| client e2e base | `515069721c40303f942d050f0bb072aead44b63209823c890beeab494f8e2218` | 9 |
| RS current V2 | `1e5dfbfdf07564fbd736f35c2c2094bde37eab6cc66a3e1bb81abd8d0a19ec2c` | 28 |
| client current V2 | `84f6e77e8fab4d2da824a7ad27690f268a33242399be2193178f63d9346f15bb` | 17 |
| final Compose backend runtime | `e90a748884a6b6c9b3675eb539ae1527bcf1ac0d38e3638d46fb93aac3edabfb` | 13 |
| final Compose worker runtime | `b19e44cfc08969d9ec12981300c467345dee8cc2ae2959ecaf370fdc11386b00` | 13 |

`compose-provenance.json`是该runner中最后写入的submit Compose provenance，非声称一个文件记录全部旅程：backend=`sha256:e5852fc036a23af2176cee772f9399c8131202348953e1db72964a4cb2c53091`、worker=`sha256:0df1bb45d478177660f0fd045a8134b2bb8788ef75363f4008c8f5e47f983313`、RS=`sha256:9165abe9c07cf4855dc2631fb0d4215fd2b8af28f38e1f55092751bf97db5b50`，逐个匹配after saved项。同node使用这些local IDs；不跨node比较。RS及client revision labels均exact V2；RS当前owner identity也candidate=V2，build-input=`e76342ef0b58bb0120fc60d8a063d838140ee28d`、source-tree=`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`，均匹配当前RS tag及runtime save labels。

backend依赖base来源另独立核原CT201 clean source53746 build原日志（2026-11-08 09:20:30–09:26:19Z，BUILD_DRIVER_EXIT0）、原identity JSON SHA=`d5ebabf6cf39b98917adca5ebad6f66138e2a9fa00e63eb8e6526956ccdff7c3`、原04/06 LAN prefill日志SHA与final0。原archiveSHA=`1b595f069197d75a9226978a530fdb06db93e7df29dbf1f4458e00ec3f6cc648`；06 actualload09:33:48–09:34:06Z，原日志=`762c4b3f828ddee4c618e006f716c4b241cce3d186e18c7d7adb9a39a41c4d97`；04为09:33:44–09:34:05Z，原日志=`c5b960cd8c9731f8947e53b2674ac34a62255bb8833bbab4648d14404c57ad8a`。当前actual before/after config46c00…及**全部19个DiffID**直接与原53746 identity JSON相等；未用inspect ID作跨节点身份。Git复核53746..V2的backend三依赖输入、Cargo.lock/toolchain、dependency Dockerfile/buildscript零差异，完整input=`578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`。此为既有LAN依赖来源事实，非旧产品包carry；当前无新build/transfer或冻结资源改动。

Current HEAD=V2，container rebuild required=yes（harness边界）；当次必要当前HEAD重建及适用Compose已随合格authority完成。H尚未形成，后继仍须同原06/WT/profile/env/images实际六包compare和RS/backend镜像身份绑定，不能凭同树口头carry或换WT/节点。保原selected tags与env，后继t1用另节点隔离，不能覆盖它们。

## t1 唯一后继执行许可

重新核固定工具SHA不变：driver `/home/dev/gdds-s5-logs/execution/e-t1-r4.py`=`3c8507cb3c1cb463d2dc22970ff0e6d4122b1544e5e68b00e5ff1a4241cb7eb3`，wrapper `/home/dev/gdds-s5-logs/execution/e-t1-run-r2.sh`=`2a6e9d5c221a6e3ce10f54c1a6e9f3cf63a866b76587b47d3b28498767c4ca4e`，其独立静态GO及EW1/EW2关闭见 `e-tools-r2.md`。唯一测试者现可在**另04**重新核空闲并原子本人占用，以新clean committed V2 WT+legacy、offline预填缓存/native强制重装及build-input、backendbase1/networknone正常Composebuild、M24/N1，执行该固定最小t1一次。外层source evidence只取本次V2的完整 `remote-evidence`，不得取旧163或focused。

真实范围继续是必要两节点合法前置（只需v1 Archive、v2 final Submission），一次本人cold History、newkey/newoperation一次warm、实际records facade与完整tar/schema/content/独立12 records及手算代表/125tables、RS HTTP冷正校准暖0及metadata/restore/kernel/summary/digest分列、真实HWM/cgroup，private secrets-root位于evidence外；不扩FULL/三节点/损坏/恢复真实矩阵。失败首停后继验收，保原numeric/原件，由本原审连续复核，不覆写原稿或重置同根DC68计数。

旧163全量整次1已在 `e-debug-evidence.md` 核收，不能提供任何qualified包；A–D与2d8debug均focused，不能carry。本次六包是V2当前实际全跑，没有拆包carry。下一步t1尚未运行；完整E证据、纯docs最终H、H绑定、独审授权release、actualrelease0与最终exact-H EXIT_GO、本地tag依次仍待完成。无提前release/tag/push许可。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-release-r1-review.md`；SHA256：`cb4a956578877f26ba246168e83289d5813fca17fe6b1be11f7a8b0913452e6d`。

---

# P6 S5 E 最终本人 marker 释放稿窄审 R1

结论：**SCRIPT_CHANGES_REQUIRED；当前 r1 不批准执行。** 固定原件 `/home/dev/gdds-s5-logs/execution/e-release-r1.sh`，实际 SHA256=`3f31d6462324a42a8a22dd0fe19bd5562bdf13388e53b495b46f505c198a91ca`。只发现下述一处可最小关闭的工具接缝，修订须新 immutable r2，保原 r1。

## ER1 — P2：Docker 空闲查询非零会被 `test -z` 掩盖

remote guard 使用 `test -z "$(docker ps -q)"`。命令替换内 Docker daemon/query 若非零退出且 stdout 为空，外层 `test -z` 仍为0，`set -e` 不能传播已被该 test 覆盖的失败。脚本随后会删本人 marker，未实际证明无运行容器；stderr 日志不能代替 guard。

最小修订沿已审 authority/H-binding 的标准形式：先独立 `containers=$(docker ps -q)`，再 `test -z "$containers"`。assignment 的退出由 Docker 命令决定，当前 `set -e` 会在查询非零时停止到 mutation 前。不需新增框架、重试、产品变化或测试矩阵。此为执行前静态 finding，无任何节点运行/DC68轮次。

## 其余核查与后续权限

完整只读核该稿及实际 H-binding session 字段/authority marker 派生接口，未发现其他阻塞。V固定2d8，session=`codex-p6-s5-e-authority-2d8b29d332`、原 RUNROOT/WT 路径一致；动态 H 要求40hex、本地 main路径 HEAD exact H且clean，remote原WT也exact H且clean，精确本人marker文件及session字段，原 bindings/H session 要求target/end H一致、clean_end/binding_complete=yes、entry_exit_code=0。Dolt/pytest/Cargo/uv/rustc/clippy、容器与8000空闲均在删 marker 之前，ER1修后容器查询失败真实停止。

唯一远端 mutation 为移除精确本人 marker、rmdir空父目录；不改 source WT/env/images/卷，不 prune/build/tag/复测，不删除他人文件。成功后不再以全局目录必须不存在作为条件，允许正常后继任务原子取得占用；若额外文件使rmdir失败则保原非零，未授权扩大清理。remote/tee numeric分别记录且非零优先保留，外置日志记录hostname/UTC/H/marker动作并生成递归SHA。

本脚本后续GO仅是工具审核，**实际执行仍须原 E 审先核精确最终 H 的真实同node/同WT六包compare与image绑定原件成功，并明确授权释放**。可采用已说明的顺序：H绑定核收→独审允许本人release→唯一tester实际release0及原件SHA→本原审最终exact-H EXIT_GO回执→root本地附注tag精确H。旧binding稿的`retain_until_independent_EXIT_GO`应由最终报告明确解释为保留至独审确认退出前提并授权该收尾动作，final EXIT receipt在实际release后形成；无需改旧原件、另造H自引用提交或请求Owner新取舍。此顺序不降低六包/镜像/原件核收条件。

本人仅本地只读审核工具，未查看本次长测进度、访问节点、执行任一稿/语法或产品检查、改产品、创建子agent或push/tag。当前H尚未在本报告出现，不授权现在释放，不预签退出或产品证据。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-release-r2-review.md`；SHA256：`dc42a53b2a74fdfbf3de7de294d0c43ae4a617dccacd65c3bf8f465b57057926`。

---

# P6 S5 E 最终本人 marker 释放稿连续复审 R2

结论：**SCRIPT_GO；ER1 CLOSED**。仅绑定不可变原件 `/home/dev/gdds-s5-logs/execution/e-release-r2.sh`，实际 SHA256=`8045929aafecd86e1a00af8cf8ae8f0178d496425e7f017301788c193f0c23a6`。原 r1 SHA=`3f31d6462324a42a8a22dd0fe19bd5562bdf13388e53b495b46f505c198a91ca` 重新核仍不变；r1 finding报告 `e-release-r1-review.md` SHA=`cb4a956578877f26ba246168e83289d5813fca17fe6b1be11f7a8b0913452e6d` 保原。

本原审完整核唯一增量：把 `test -z "$(docker ps -q)"` 改成独立 `containers=$(docker ps -q)`，随后 `test -z "$containers"`。在 remote 的 `set -Eeuo pipefail` 下，独立assignment保留Docker查询退出，非零会在删marker前停止；查询成功才判断stdout为空。没有额外变化、重试、产品修改或扩大清理。**ER1静态关闭**，两版均未执行，此执行前修订不计节点DC68轮次。

原R1核过的exact V2/session/原WT、动态exact H/clean、bindings/H实际complete0、本人marker所有权、进程/容器/端口空闲、只删本人marker/rmdir空父目录、保source/env/images/卷和日志/退出边界全部不变。没有释放后全局absence条件，不干扰合法后继占用。

**本SCRIPT_GO不授权当前释放。** 实际只能由唯一测试者在本原 E 审先核精确最终 H 的同原node/WT六包compare及image绑定真实原件GO，并明确授权本人release后执行。随后核actualrelease0、完整日志SHA及exact H，再由本原审形成最终exact-H EXIT_GO外置回执，root才本地annotatedtag精确H、main停clean H；无push授权。旧binding稿marker_policy的序列解释沿R1报告，不改旧原件、不造自引用H2、不预签当前产品/证据/退出。

本人仅本地只读核原件SHA与差异，未访问节点、核长测进度、执行本稿/语法或产品检查、实施产品、创建子agent或push/tag；协调者bash-n不是本审执行或实际释放证据。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-preflight-failure.md`；SHA256：`a0bb09b7767f0c64c21b01275767c70680aea6228fd0bc9b618cb8b46e536b28`。

---

# P6 S5 E t1：04 首次前置失败原件核收

结论：**TOOL_PREFLIGHT_FAILURE_CONFIRMED；原失败保1，尚无 t1 产品实测。** 已独立核首次wrapper r2运行原件与实际t1调用链。失败是没有当前consumer的host Dolt全局配置前提，不是产品、缓存缺失或镜像身份不符；可按DC68第1修复轮以新不可变工具稿删除该前提、保原件并重做前置至实际旅程。新稿固定SHA尚待另审，**当前不许可执行重试**，不改产品或04全局配置。

原件根 `/home/dev/gdds-s5-logs/execution/e-t1-run/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-3c8507cb3c1c/`，实际hostname=`gw-dms-test-04.lan`，remote session=`2026-11-09T12:09:58Z–12:10:00Z`，起止exact V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、clean。源06 qualified proof确引用此前已核整次0 V2 authority，runnerSHA=`dff5f6c385ad17f6dbd6a932efdd91710d68e616b34d1d3d262795b284b50b69`，不引用旧failed163或focused。

重新实算本地完整SHA256SUMS及checksum全通过；remote本次相对路径manifest也全项通过。steps仅两行：toolchain-readonly=`0/0`；precheck-inputs-and-bases=`1/0`，后者traceback `<stdin>:7 AssertionError`，逐行映射固定wrapper r2的INPUTS脚本，第6行HOME=/root与无DOLT_ROOT_PATH断言已通过，第7行root全局config的`versioncheck.disabled == 'true'`不满足。原件没有打印该实际值，因此只认“不等于所要求字符串true”，不补造false/null等值。后面的两个输入包读取/hash、两个base inspect尚未开始；driver AST/native/envsync/RSbuild/driver/栈/业务均未进入，没有未知cache miss可归因。

| 原件 | 实算SHA256 |
| --- | --- |
| local `SHA256SUMS` | `c815ce521d3f1a54492cefae3faf1acf9aedb886540567f1c6fbff25ed22b541` |
| `remote-evidence/precheck-inputs-and-bases.log` | `6bbd81d84a6ece5b71b4d29f9a40567bde6c183058aa3f448ae5f12ae8219ed1` |
| `remote-evidence/session.log` | `9d26505c90a7b5a9908f487dace473c9ac9e7aaf37087037d2ad6fc07369d53d` |

remote原始numeric=`1`、outer remote=`1`/tee=`0`，artifact-copy/hash=`0/0`，guarded-release=`0`且记录marker已非本人或已释放；remote本人marker文件remove与父目录rmdir均0、marker_released=yes。没有继续验收，失败WT/ref/原件保留。只有必要工具checkout/ref/log状态发生变化，没有产品进程、持久化业务/缓存/镜像构建副作用。local end比remote时钟小1秒保原值，不修写其数字。06 authority成功来源/原WT/env/images及保留marker不受此另04工具前置失败影响。

## host Dolt consumer 范围

本原审只读追固定driver r4、其实际调用的`benchmarks.real_dump_journey`、`compose_gate_harness`、wrapper后继命令、RS build/identity与DoltRunner owner：

- wrapper host路径是Rust/uv工具链版本、包hash/base inspect、AST、locked offline sync/native/build-input、Docker source build；没有host `dolt version`或`test_input_closure`调用。
- driver host实际消费Git、HTTP、tar/Arrow/records与Docker/Compose。`j._submit(verify_repository=...)`通过Repository HTTP main核技术提交；`h.start_three_container_stack` seed与empty-catalog检查也通过容器内HTTP调用。h中另有dolt log/sql诊断helper，但此driver没有调用它们，不能因文件里出现Dolt字样扩大host前提。
- RS实际执行Dolt在容器内，经`DoltRunner`自己的server-root/provider/runner-home私有HOME，初始化先`_seed_private_dolt_config()`写offline versioncheck设置再validate_version。Dockerfile版本检查发生在镜像构建容器内，也不消费04 host `/root/.dolt/config_global.json`。

因此可最小删除工具预检中的HOME/DOLT_ROOT_PATH与hostglobalconfig三项约束，保实际输入/base/offline/clean/native/driver/M24/N1/容器privateHOME边界；不需要改04全局Dolt配置，不增加host版本命令或产品/兼容路径。后继必须新namespace明确profile-fix-1并在日志关联本failedroot与DC68修复轮1，不覆盖旧WT/ref/root，不把换文件名/目录当计数归零。待新稿精确SHA核增量后，才给唯一tester本轮修复执行许可；失败结果仍为1，实际再次故障按原同根计数继续处理。

本人未访问节点、执行工具或产品/语法/lint/编译/镜像、改产品/全局配置、创建子agent或push/tag；本报告只核已有原件/源码，无t1实测、最终E证据、H绑定或退出预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-run-r3-review.md`；SHA256：`6916deb0af5fd420a1faeda8c4c8752a5770c957e78ddfef987b8b898e013887`。

---

# P6 S5 E t1 wrapper 连续复审 R3（DC68 修复轮1）

结论：**SCRIPT_GO / T1_REMEDIATION_EXECUTION_GO**。仅绑定新不可变稿 `/home/dev/gdds-s5-logs/execution/e-t1-run-r3.sh`，实际 SHA256=`2563189ab5be5a96f90855d4f31e539ce2bf7c570729de6876f1414fb9c32201`，与固定 driver r4 SHA=`3c8507cb3c1cb463d2dc22970ff0e6d4122b1544e5e68b00e5ff1a4241cb7eb3` 配套。可由唯一测试者在同04重新核空闲、原子本人占用，使用新pf1命名空间从头执行一次受影响流程；实际 t1/最终E证据/退出尚未核收，不预签。

本原审重新核r2 SHA仍=`2a6e9d5c221a6e3ce10f54c1a6e9f3cf63a866b76587b47d3b28498767c4ca4e`、driver SHA不变，并完整逐行核r2→r3差异：

- 仅删除INPUTS前置里host HOME/DOLT_ROOT_PATH断言与host全局Dolt config读取/assert，换为范围注释；原包size/SHA、base完整input/lock labels、subprocess失败传播均保留。已发生故障及无consumer依据见 `e-t1-preflight-failure.md` SHA=`a0bb09b7767f0c64c21b01275767c70680aea6228fd0bc9b618cb8b46e536b28`：此driver和wrapper实际host路径不调用Dolt或test_input_closure，HTTP consumer不需要该hostglobal前提；RS容器DoltRunner仍先seed私有HOME再validate_version，Dockerfile的Dolt版本检查也在build容器内。该删除不改变真实容器offline边界，不修改04全局设置，不发host Dolt版本查询；不表示HOME对uv/Cargo一般环境完全无关。
- 固定 `TOOL_PROFILE_REV=1`，KEY/session/Compose全派生`-pf1`，其runroot/WT/ref/remote-ref/local目录随KEY独立，旧失败原件、WT及ref不覆盖。remote第12参数读取profile并要求为1，后续路径/driver输入无参数错位。
- local/remote session均明确 `DC68_fault=host_Dolt_global_config_precheck_without_host_consumer`、fix_round1、prior V及原failedroot；原precheck SHA6bbd…与session SHA9d265…逐字对应已核失败原件。local另写prior localroot，实际旧路径后缀为`V2-3c8507cb3c1c`；日志明确新namespace不重置同根计数。

V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、vnextfb92、Rustc021固定不变。除此无增量：source资格仍只取已核V2全六包0 copied remote-evidence、原log SHA/全部steps0；本地clean/committed+legacy、新源checkout022后077、本人marker/栈命名隔离、offline、native强制重装/build-input、normal RS环境/当前source build、backendbase1/networknone无PREBUILT、M24/N1、私有secrets在evidence外、driver一次/完整原件SHA复制及同节点真实saveconfig身份、EW1/EW2收尾均不变。没有扩大真实旅程、改业务expected/golden/locks或触碰保留的06 authority环境/镜像。

原r2实际失败仍为1且只到工具前置，没有产品副作用，已安全释放04本人标记；这是该同根工具问题的 **DC68第1修复轮**，不是新计数/无修改重试。只许可本修后固定稿在新pf1 WT从头运行一次；首失败停止后继验收、保原numeric/原件，交本原审连续处理，不自动重试或因换目录/节点归零。06 qualified source0继续有效；旧failed163与所有focused仍不可拆包carry。

本人仅本地只读核原件SHA与差异，未访问节点、执行脚本/语法或产品检查、实施产品/全局配置、创建子agent或push/tag。root本机bash-n不是本审或实际旅程证据。actual t1/schema/records/四tar/冷暖指标/真实资源/镜像来源/收尾仍待核收，H、release与final exact-H EXIT_GO及tag条件不变。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-entry-failure.md`；SHA256：`e28bcb0d94b47e28142c3ff8e30ea2a744ac3f61a1db599b754e28e545a64d04`。

---

# P6 S5 E t1：pf1 受控入口拒绝原件核收

结论：**TOOL_ENTRY_FAILURE_CONFIRMED**，pf1原始exit2保留，driver尚未运行，无t1业务/栈结果。前稿静态审核漏核了受控wrapper对外置.py入口的明确拒绝，实际guard正确拒绝该调用；修工具调用，不改guard/产品/依赖或clean WT。下一稿按本t1执行profile累计 **DC68修复轮2**，仍待固定稿另审，不提前许可重试。

原件根 `/home/dev/gdds-s5-logs/execution/e-t1-run/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-3c8507cb3c1c-pf1/`。实际node04=`gw-dms-test-04.lan`，session=`2026-11-09T12:17:29Z–12:18:36Z`，起止exact V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、clean。独立校验local/remote全项SHA256SUMS及其checksum均通过；steps前7步command/tee均0：toolchain、两个数据包/两base input预检、driver AST、backend native强制sync、native build-input c021一致、RS环境sync、本人RS当前source build。第8步`t1-driver`为`2/0`，原错误：`run may not execute scripts outside project directory (.../driver-copy.py)`。所以无driver main/Compose/产品业务执行；没有成功镜像取证后继步骤，own env/RS build产物与原件保留，不声称完全没有工具副作用。

| 原件 | 实算SHA256 |
| --- | --- |
| local `SHA256SUMS` | `e40c0e924b2cecf30605bf2353a5d762fa3ec992492487d5f35c0b4ab05c6943` |
| `remote-evidence/t1-driver.log` | `fad1189c07e7df34c5c4886b68444b533de745bac6213fdaa5428ffc18871fbb` |
| `remote-evidence/session.log` | `22269cef19845bd321c0dccd30cd6359a573d6a7cda916977a5bd2744421aa5e` |

remote原exit2、outer remote2/tee0、copy/hash0、本人marker remove/rmdir0、marker_released=yes，local fallback记录已释放skip0，entry仍2；未继续验收。pf1日志关联原hostDolt前置失败，原目录/WT/ref/失败1均保留；不能用新目录把计数清零。06已核合格V2六包来源及其保留环境/镜像/marker不受另04工具入口故障影响。

## owner 入口语义与最小修法

已只读实际 `vnext/scripts/lib/gateway-index-env.sh:147–221`、`uv-consume.sh`及现有`test_uv_consume_script.py`。guard对`python 外置.py`解析并realpath拒绝跨project script；现有测试明确覆盖该拒绝和`--no-sync`必须先locked/offline lock-check。`-c/-m`为显式inline支持；`python -`没有外置script target，沿同解释器command路径，仍保持原受控project、index/config隔离、lock-check、`uv run --locked --project ... --no-sync`与五锁退出assert。不是裸uv或传另project，也不应修改guard让当前外.py例外通过。

适用的最小标准stdin入口为原run_step中`... run --no-sync python - --compose-name ... --output ... --secrets-root ... < "$RUNROOT/driver-copy.py"`。stdin必须来自已SHA/AST核的同r4原字节，日志记其来源与SHA，不打印全部driver/raw业务expected。固定r4由`Path.cwd()`绑定backend，显式sys.path插入同backend，main/argparse读取原args，未使用`__file__`或外script目录；stdin语义适配。wrapper的检查/snapshot/lock-check均不消费stdin正文，run_step首管道命令继承该stdin，tee只消费stdout/stderr。

新稿还须让两处existing own-driver存活guard与新argv一致：旧`python.*RUNROOT/driver-copy.py`不匹配`python -`，应最小匹配该RUNROOT实际`--output .../evidence/journey`或唯一Compose参数，不加查杀/全局cleanup机制。source/driver/预算/业务断言、private secrets与原件、原fixed scope不变；新pf2明确关联两次原failure SHA、累计轮2，原审核固定稿后才许可一次修后执行。

本人未访问节点、运行wrapper/语法/产品测试/lint/编译/镜像、实施产品、创建子agent或push/tag。本报告核已有失败和owner源码，不是新稿GO、t1成功或最终E证据/退出预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-run-r5-review.md`；SHA256：`e5d532a01bf848f5dda2bf13e2b55d42d74692fe1b3773f53c5ba81e18a083c4`。

---

# P6 S5 E t1 wrapper 连续复审 R5（实际修复轮2）

结论：**SCRIPT_GO / T1_REMEDIATION2_EXECUTION_GO**。仅绑定 `/home/dev/gdds-s5-logs/execution/e-t1-run-r5.sh`，实际 SHA256=`d84092006acd0d6c399093c2e01383689c3f903d86c820f6e38b1b1e50252588`，配同一已审 driver r4 SHA=`3c8507cb3c1cb463d2dc22970ff0e6d4122b1544e5e68b00e5ff1a4241cb7eb3`。唯一测试者可在同04重新核现场空闲、原子本人占用，新pf2 WT/栈/RS tag，从头执行一次该最小流程。**文件r5不代表第5轮；本次为t1执行profile累计DC68修复轮2，不重置计数。** 当前没有实际t1成功、E最终证据或退出预签。

本原审重新核固定r3 SHA=`2563189ab5be5a96f90855d4f31e539ce2bf7c570729de6876f1414fb9c32201`、未执行r4 prototype SHA=`2ec7e8f133619909aa3940abcd7ba50dfdedb4668558086c49e852620329accd`和driver SHA，均保持原字节。完整逐行核r3→r5及r4→r5：后者确仅专用RS tag一行增pf后缀；其余修订如下。

## 受控 stdin 与生命周期

- 将原被guard拒绝的`uv-consume ... run --no-sync python 外置.py`改为显式当前项目解释器`... python - [原业务参数] < "$RUNROOT/driver-copy.py"`，仍由原受控wrapper完成locked/offline lock-check、project绑定、index/config隔离及五锁退出assert。原产品guard、uv参数规则和依赖均未改；没有裸uv、另project、exec/runpy外文件loader或把driver写入clean WT。接口依据及pf1实际exit2原件见 `e-t1-entry-failure.md` SHA=`e28bcb0d94b47e28142c3ff8e30ea2a744ac3f61a1db599b754e28e545a64d04`。
- stdin来源是原已复制固定driver，既有SHA+AST预检保留，临执行再核实际SHA；t1-step额外写`execution_mode=project_python_stdin`、精确input path及SHA，与原command/UTC/HEAD/numeric/SHA一起记日志，不展开rawcode/业务expected。CWD仍backend，r4以Path.cwd绑定source，无__file__依赖，main/argparse保原参数；run_step的首管道命令继承该stdin，tee消费输出，前置wrapper检查不读取正文。
- local fallback与remote finish两处own-driver存活guard均由旧script路径改为`[p]ython.*--output[[:space:]]<同RUNROOT>/evidence/journey([[:space:]]|$)`，对应实际stdin Python argv中的唯一output。`[p]`避免pgrep自匹配；此处只观测、拒绝不安全release，不新增查杀或cleanup框架。本人marker所有权、Dolt/uv/Cargo等进程、Docker查询状态/空容器与8000空闲、原numeric保留逻辑未改。

## 保原件与固定范围

- `TOOL_PROFILE_REV=2`且remote第12参数要求2，新KEY/session/Compose及全部runroot/WT/ref/local均pf2。RS tag也现在明确`gateway-repository-service:p6-s5-e-t1-<V10>-<driver12>-pf2`，不会重tag覆盖pf1已构建的专用RS tag；authority06所选tag从来不在此作用域。后续harness读取同env tag、实际运行镜像与save身份仍沿原owner核验。
- local/remote日志明确fault为外置script target、previous hostglobal前提已于pf1移除且预检实际通过，关联pf1 failedroot、driver-step SHA=`fad1189c07e7df34c5c4886b68444b533de745bac6213fdaa5428ffc18871fbb`及session SHA=`22269cef19845bd321c0dccd30cd6359a573d6a7cda916977a5bd2744421aa5e`，并保初始precheck/session两个SHA。初始失败1、pf1失败2和所有旧WT/ref/log均不覆盖；未执行prototype静态修订不另计节点轮次。
- 固定产品V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、vnextfb92、Rustc021/driver3c850不变；source资格只取已核06 V2完整authority0原件，不拆包carry旧failed163或focused。实际inputs/base/native build-input、checkout源022后私有077、offline/cache/normal RS环境、backendbase1/networknone无PREBUILT、M24/N1、private secrets在export evidence外、最小合法前置/冷暖/独立records/四tar/schema/content/预算指标与收尾全部无增量。

授权仍是同04 fresh现场原子占用、新pf2命名空间从头的一次修后执行。任何实际首失败保原numeric和全部原件、停止后继验收，交本原审连续核收；不会因版本名/目录/节点清计数，也不自动补跑。06 qualified source及原WT/env/images/marker继续保留供最终H，不因04工具故障重建或替换它们。actual t1完整原件及最终E证据、精确H绑定/独审授权release/actualrelease0/final exact-H EXIT_GO/tag仍待后继完成，无push授权。

本人仅本地只读核原件SHA、完整增量及原owner接口，未访问节点、执行脚本/语法/产品检查/lint/编译/镜像、实施产品、创建子agent或push/tag；root bash-n不冒本审或实测结果。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-pool-init-review.md`；SHA256：`6afcd0b635ec439aea90b2b002ea462e869f58d86fd1b2fab4b37d0e4ed35b68`。

---

# P6 S5 E t1：诊断 records 共享 pool 初始化连续复审

结论：**旧 r4 driver 当前执行许可撤回；新 r5 driver + r6 wrapper 联合 SCRIPT_GO / T1_REMEDIATION2_EXECUTION_GO**。仅批准下列固定组合，由唯一测试者在同04现场重新核空闲、原子本人占用、新派生pf2 WT/stack/RS tag，从头执行一次已审最小流程。pf2从未实际执行，本次是执行前静态关闭新缺口，仍为累计DC68实际修复轮2，不能按文件名r6算第6轮或重置计数。没有t1实测/E最终证据/退出预签。

| 原件（`/home/dev/gdds-s5-logs/execution/`） | 本审实算SHA256 |
| --- | --- |
| 新 `e-t1-r5.py` | `157d4f1e356da05d098b5920bb8bec58005d2ca5c7569e8d15cb06fd01dc8fe8` |
| 配套新 `e-t1-run-r6.sh` | `7f05f2c73b7a934ac8136c6bab22f65eb9eef8e4cc73da822e8f54da350b1631` |
| 旧 `e-t1-r4.py`（保原，不再批准执行） | `3c8507cb3c1cb463d2dc22970ff0e6d4122b1544e5e68b00e5ff1a4241cb7eb3` |
| 未执行 `e-t1-run-r5.sh`（保原，不得搭旧driver运行） | `d84092006acd0d6c399093c2e01383689c3f903d86c820f6e38b1b1e50252588` |

## 确定缺口与原许可撤回

本原审独立逐段追实际源码：driver首个完整Preview tar消费`verify_bundle_tar`会对其中records closure调用`open_records_closure`，其逐records验证进入`_validate_parquet_bytes`、Python`native.validate_records_batches`、Rust `comparison_records.rs:1399`的`shared_parser_pool(None)`。`lib.rs:182`起明确要求PARSER_POOL已初始化，否则稳定抛`kernel pool has not been initialized`。旧r4没有任何初始化调用，import bootstrap也只定义函数，不能初始化另一个host进程的pool。原journey CLI `_run_kernel_journey`明确先初始化；此前删独立composite native处理后漏掉这一必需启动接线，前次静态driver GO未发现该缺口。

因此立即暂停/撤回旧r4的当前执行许可，旧 `e-tools-r2.md`/authority t1许可及 `e-t1-run-r5-review.md`中搭该旧driver的执行组合由本报告取代，原报告字节不修改。两次实际04失败均未进入driver，pf2尚未下发执行；不存在把已失败产品旅程补记成功。旧失败1/2原件与历史不改。

## 最小修订核查

完整逐行核driver r4→r5：唯一代码变化是在main既有source/clean/args/private-root等前置checks通过、建立result与try之后，首输入/GET/栈前调用一次`j.initialize_compute_kernel(1)`，加两行说明。该alias确指向已导入的bootstrap owner；owner调用`_init_kernel_native(1)`并设置Arrow CPU/IO线程1，没有创建operation scope或更改M/业务参数。初始化异常在既有try/finally中保结果及原退出，env尚None不会停他人栈。

**不加kernel_execution_scope是必需的当前consumer边界**：`read_records_artifact`在artifacts.py:294–299明确拒绝非None current_kernel_context的诊断reader；当前完整tar校验/records facade位于host诊断路径，由records自身standalone预算/校验约束。只初始化固定host池使native验证可用，诊断context继续None；实际production worker的N1/M24/envelope32及其真实HWM/cgroup观测没有变化，不把host诊断池冒充production operation预算。

完整核wrapper r5→r6：仅新pinned driver SHA与两处prior-root printf参数变化。历史目录参数固定真实旧driver短SHA`3c8507cb3c1c`，与已核pf1原件/两个失败SHA相符，不随新driver变成不存在的历史路径；新KEY/session/Compose/RS tag仍按新driver短SHA`157d4f1e356d`+pf2派生，旧资源保留。TOOL_PROFILE_REV=2、受控`uv-consume ... python -` stdin入口、临执行再核同driverSHA/既有AST、step mode/path/SHA、两处实际`--output` argv存活guard及self-match保护均原样保持。没有runpy/外script/另project/裸uv、改guard/WT/锁/依赖。

V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、vnextfb92、Rustc021、scope/独立expected/HTTP冷暖/实际records与四tar/schema/预算/私有secrets及收尾均无改动。原固定source/CLI/privateHOME/input/base/offline/native/body规则沿前审；新init属于外置driver组合启动接线，无产品提交/生产源码变化，不需重新产品静态或完整六包。06已核合格V2 authority0与原WT/env/images/marker继续保留，不能因04工具修订覆盖或跨节点carry。

本组合只给同04 fresh本人占用、新namespace的一次修后执行许可；任何实际首失败保原numeric与原件、停后继验收，交本原审连续处理，无自动重试或计数归零。之后t1/schema/records/tar/资源/镜像与关闭原件仍须本审核收，最终E证据、精确H绑定、独审授权release/actualrelease0/final exact-H EXIT_GO及tag条件不变，无push授权。

本人仅本地只读核原件SHA、实际owner调用链和完整增量，未访问节点、运行产品/语法/lint/编译/镜像/任一执行稿、实施产品、创建子agent或push/tag。root工具bash-n不冒本人检查或实际执行结果。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-old-composite-capture-r1-review.md`；SHA256：`99e3873348f7df6184093b553a87bd3528c061212806e3ce78442441e7c28d2c`。

---

# P6 S5 E：pf2 composite 前提失败与固定旧 owner 捕获稿独审

结论：**pf2 原失败已核收；旧 oracle SCRIPT_GO / OLD_ORACLE_EXECUTION_GO。当前不授权重跑 t1。** 仅批准唯一测试者在04 fresh本人原子占用、新clean detached OLD WT+legacy，以固定稿捕获两个固定包的旧 composite owner 结果一次。该捕获是补齐独立预期的最小必要前置，不能代当前产品/t1成功或重置已有实际修复轮2。

固定外置原件 `/home/dev/gdds-s5-logs/execution/e-t1-old-composite-capture-r1.sh`，实算 SHA256=`13839f2da90a9ea31b7ffd3ae3ba701451dd907039d3ed20f08d634ef0f3103f`。本原审完整静态核本稿、旧source owner调用/真实imports/预算scope与现有受控入口，不运行脚本或语法检查；root本机bash-n结果不冒本人或实际oracle证据。

## pf2 实际失败及许可状态

完整只读核原件 `/home/dev/gdds-s5-logs/execution/e-t1-run/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-157d4f1e356d-pf2/`。local/remote全项SHA256SUMS及checksum均通过；前7工具步command/tee均0，第8步t1-driver实际 `1/0`。node04 session=`2026-11-09T12:33:17Z–12:34:22Z`，起止exact V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、clean。driver已由受控stdin进入、pool初始化通过，在读取两个已固定SHA包后，`independent unchanged composite XML`断言失败；尚未生成Compose环境/私有secrets、启动栈或HTTP/Preview/Submit/History。result只保原输入/预算/失败和clean状态，没有把后继预期或旅程写成完成。

实算 `remote-evidence/t1-driver.log` SHA=`beb253030b0bedaca5e4599b2de1c951788954340272b1eb2f5f161cf477e3d7`，`remote-evidence/journey/result.json` SHA=`5b667019fd5cb7e3f6bb091ce74e402377c28d34ee23ab2af29a23da3a9df535`。原driver/session/outer exit均1、tee0，copy/hash0，本人marker rm/rmdir0且released=yes，local fallback0；失败源WT、native/env/RS build等工具产物及所有raw原件保留。不是缓存/身份未知，也不是产品旅程失败。

此前driver GO未充分核实“两个XML原字节相同”的事实前提；该断言现已实际失败，不能删除它后仍硬保4/4 unchanged/risk0。XML bytes不相等也不能直接推导其业务差异计数或Risk非零，二者仍待旧owning解析/比较结果。**撤回当前r5 driver SHA157d4…与配套r6 wrapper SHA7f05…的t1重跑许可**，旧报告字节保原；后继必须先获得独立oracle及适用Risk依据，再固定修订、原审连续复核。已有pf0失败1、pf1失败2、pf2失败1和实际执行修复轮2事实保留，不按新目录/文件名清计数或无限重试。06已核qualified V2六包0、原WT/env/images/marker不受此另04工具前提失败影响，不能触碰它们。

## 固定旧 source 独立性与实际 consumer

本审新建并复核clean detached只读WT `/home/dev/gdds-reviews/p6-s5-e-oracle-6786b28a35`，legacy链接正确。exact OLD=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、vnext=`6368c9c40cf08a97eecf2a0c457a6c16ce448080`、Rust=`e2a901417b19259ece669637a41545e774261445`，均与稿一致；读旧AGENTS、`real_dump_census`完整composite helper、canonical/materialize/Comparison与pool/scope实际接口。main继续clean2d8，未修改当前或旧产品。

旧 `compare_composite_packages`实际按两包staging/SQL+XML业务materialization、只投影`composite_signal_point`、canonical authority和旧Comparison owner生成该表facts，native STANDARD family实际record count与row changes内部核对，product/readers由原owner关闭；稿只单次调用该owner，不复制当前S5实现生成expected。输出是旧 `CompositePairCensus` dataclass的完整`asdict`：实际为status+6计数共7字段，不依任务描述的误称8字段截取或伪造。

该helper自身不建新operation scope，旧CLI main1105先init+scope；固定稿同样 `initialize_compute_kernel(1)`后，以 `KernelExecutionContext(OperationMemoryBudget(25769803776), NeverCancel(), 1)`、new_operation=True包住单次旧比较，high_water从同scope真实预算读取并要求≤M24。这里是必要旧native比较scope，和当前t1诊断records facade要求None context是两个不同consumer，不混用。没有沿用S4 M40或生产默认变更。

## 脚本边界与日志

- 本地只传不可变OLD Git objects，经full bundle SHA/advertised named ref、remote精确OLD/vnext/Rust、clean已提交detached WT+legacy绑定。新源checkout022后私有077；不检出或改authority06 WT。实际imports逐个记录并要求全部在该OLD WT内，native `__build_input__`强制等OLD_RUST；关键源blob清单与五个依赖输入SHA另保原，不把模块路径列表冒所有传递import的穷举证明。
- root Cargo PATH/selector四工具1.97、禁设Rust环境、UV/Cargo offline、无proxy/PYTHONPATH覆盖、normal旧backend项目venv、强制旧native重装+build-input实际检查；只五步：toolchain、native sync、build-input、capture AST、old composite capture。无host Dolt、test_input_closure、runner、Compose/镜像build、History或完整旧旅程。若缓存/工具链/输入缺失或身份不符，首非零停下保原件，不换到开发主机或绕锁。
- 显式`uv-consume -C OLD/backend run --no-sync python - --oracle-output ...`，仍走旧受控project/locked/no-sync检查与index/五锁隔离；stdin是本固定稿生成并记录SHA的capture原字节，CWD绑定backend，无runpy/外script target或另一project配置。实际old imports均存在且接口匹配，输出路径在本人evidence外置目录。
- 只读取rd-t1-a-v1/v2固定107115/107066 bytes与各已核SHA，tar只读唯一ordinary XML member；记录每份XML bytes/hash与实际相等布尔，**没有相等/unchanged/4/4/零变更等业务expected断言**。包/成员身份失败仍拒绝，不能用新History结果作为oracle；捕获正文和result均完整保存。
- 新本人marker、工具目录/ref不覆盖；host/UTC/起止HEAD与clean、逐step command/tee numeric和日志SHA、入口/复制/recursive checksum分别保留。两处`[p]ython.*--oracle-output <同runroot>/evidence/oracle-result.json`存活guard匹配stdin argv并防自匹配；Docker查询失败拒绝release，只有本人所有权和全部空闲才移除本人marker，non-owned/already-released local fallback0。保OLD WT/venv/native/cache/sourcebundle/raw，不清旧失败或他人资源。

本SCRIPT_GO只准该旧composite捕获一次。计数/语义结果当前未知；若实际为非零composite变化，需要旧Risk owner的最小独立依据确定risk expected，不硬留0。本稿明确不提供Risk oracle；其结果原件需本审核收后才能修t1预期并审下一执行稿。不会把old capture当当前包qualified source，或声称当前S5业务已通过。

本人未访问测试节点、执行任一稿/语法/产品测试/lint/编译/镜像、实施产品、创建子agent或push/tag。当前不授权t1重跑、E最终证据/H绑定/release/EXIT/tag，亦无push授权。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-old-composite-evidence.md`；SHA256：`5a641904f91e34dc5692aa5eb8e692c3e73799ced773414a2c243c2182b052a6`。

---

# P6 S5 E：固定旧 composite oracle 原件核收与 Risk 前提复核

结论：**OLD_COMPOSITE_EVIDENCE_GO**，只覆盖固定旧source的composite独立预期。已真实核得composite `UNCHANGED`、before/current均4行、三类变更与History records均0；两份81-byte XML原字节并不相同。**当前driver整体risk0/noannotations断言存在确定静态矛盾，不批准据此重跑t1。** 需固定旧完整Comparison→Risk的最小组件捕获补齐独立风险业务预期，另审执行稿和原件；不能用新History actual回填。

## 旧 composite 真实来源与完整性

原件根 `/home/dev/gdds-s5-logs/execution/e-t1-old-composite/6786b28a3506feab3d8eac7d1288c8b22525bb8f-oracle-r1/`，fixed entry SHA=`13839f2da90a9ea31b7ffd3ae3ba701451dd907039d3ed20f08d634ef0f3103f`，与原SCRIPT_GO稿相同。actual hostname=`gw-dms-test-04.lan`，session=`2026-11-09T12:48:22Z–12:49:26Z`；本地end时钟12:49:25Z保原，不改跨机1秒差异。OLD起止均=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、clean，vnext=`6368c9c40cf08a97eecf2a0c457a6c16ce448080`、Rust=`e2a901417b19259ece669637a41545e774261445`；当前main起止仍V2=2d8。

local/remote全项recursive SHA256SUMS及各checksum实际全通过。独立逐行核steps恰5步、每步exactOLD/command0/tee0/实际logSHA：工具链、强制旧native sync、native build-input、捕获AST、单次old composite owner。原session/local/remote/tee/copy/hash/release各numeric0，本人marker rm/rmdir0且released=yes；旧WT/venv/cache/bundle/raw保留，未改06 authority冻结资源。

| 原件（相对根） | 实算SHA256 |
| --- | --- |
| `SHA256SUMS` | `8fb011f3c29b3dc303a0cdb9495a14ee6cf229d9a5e6df259d7ea1e6accad2c3` |
| `remote-evidence/oracle-result.json` | `3707ad9891efa47a2d1b5fdb88e51f9b77880d7532826db1ff4d5a6476ab5261` |
| `remote-evidence/session.log` | `b5ebc67c119854f9bea6402d28758186f62e7c142a4d02a0e52fdbb793935614` |

actual imports逐项属于该旧WT（含新旧隔离的旧`.venv` native.so），native expected/installed/captured `__build_input__`均exact OLD_RUST。捕获key_source_blobs逐行与本审OLD Git树直接相符，五依赖输入SHA保原；没有使用当前S5 codec/History输出作oracle。初始化N1后同M24 scope单次旧owner比较，真实charged high water=`25251453312` ≤ `25769803776`；这是预算HWM，不是RSS/cgroup peak或性能结论。没有host Dolt、runner/Compose/HTTP/完整旧旅程。

两个固定输入包的size/SHA与此前被测输入一致。XML v1：81 bytes，SHA=`03f90da1675345aef17d9c0cadbb81f6271f1c7bfe1ae79d8eb86213b1a68adf`；v2：81 bytes，SHA=`7d0fec1905aaa7100f1fc7eaf13347755521e79cbea45b317a14660f821801d9`；actual `xml_bytes_equal=false`。旧owner完整asdict七字段为：status=`UNCHANGED`，before/current=`4/4`，added/removed/modified/history_record_count=`0/0/0/0`。这关闭“XML byte不相同是否改变composite业务”的未知；不得继续断言raw XML相等，也不因raw差异伪造业务变化。

## 旧 Risk owner：composite 本身零风险的条件成立

独立在本审OLD detached WT只读核Risk `_facts.py`、`_engine.py`、`contracts.py`及真实composite schema。`has_visible_change`对UNCHANGED/BUSINESS_EQUIVALENT、无removed/incompatible schema或有效key变化、无行counts/records/ordered unsupported/uncovered时返回false；engine先返回空outcome，再有composite专属UNKNOWN规则，因此不是看到composite表就发风险。

真实composite schema由snapshot_materialization/compose.py的固定八列构造：source_table VARCHAR(64)、point_gid/dev_addr/device_gid BIGINT、point_name TEXT、point_payload_json LONGTEXT、nullable formula_digest TEXT/formula_ast_json LONGTEXT；key固定(source_table,point_gid)。同固定旧owner对两包构造同schema，规则固定ignored dev_addr/device_gid/point_payload_json、compare-excluded formula_ast_json/point_name；从OLD到当前V2的composite/schema/table-rules、Risk facts/contracts没有变化。已核旧composite UNCHANGED且零records因此对本pair不贡献风险。

publication只为非空outcome.annotations建table risk/artifact/closure；若所有表均零annotation，则overall.annotation_count求和0，annotation_refs/实际annotation artifacts均空。这说明“有独立SQL风险0＋本已证composite业务不变＋同schema/规则/无degraded”在逻辑上足以支持整个0/noannotations；**本次没有独立SQL风险0证据，不能把条件命题写成已证事实**，更不能从总records12推出风险0。

## ET1-RISK：整体零风险断言与旧 SQL/SYX consumer 确定矛盾

旧Risk规则独立核得：

- SYX手算三增三删的REAL_STABLE实体变化在旧Rust `comparison/ordered.rs:1024/1079`生成STANDARD locators，公共row_added/deleted counts也非零（1351起）；并非只在ORDERED records family里可见。
- 旧Python `comparison/production.py:713`保这些counts到table fact，1043–1049 prepare并加入risk_handles。旧RiskRecordView读取STANDARD family最小record_kind/row_identity/changed_columns，`_emit_row_risks`645–675按公共counts逐匹配ROW_ADDED/DELETED record发annotation。
- 原History pair pipeline注入完整V1规则与默认`RiskOptions()`：include_low_risk=True、include_unknown=True、TARGETS_ONLY，无requested_tables过滤。ROW_ADDED/ROW_DELETED都为MEDIUM_LOW，故这六条不能被默认过滤掉。当前S5改候选缓存/绑定不改这些业务规则；总records与schema/其他SQL表风险仍须另核。

因此driver直接要求overall.annotation_count=0且不存在annotation artifacts的旧预期不是合格独立基线，**至少与SYX六条旧owner风险消费相矛盾**。现有S1b/P5 handoff能直接支持12records/4ordered/composite4/4等，但本审未找到整体Risk0直接原件；不能把历史文字或当前实现看似通过当风险期望。完整风险总数、其他表、targets和annotation编号不能只凭此六条代表手算定死，需同固定OLD两包完整canonical→Comparison→Risk最小组件捕获，以保留所有旧业务字段、records族counts与编号并交叉手算SYX六条。该后继仍不应启动HTTP/DB/Compose/runner或完整旧旅程，不mock owner/用新History expected；固定稿须原审另核后才可执行。

旧r5driver/r6wrapper的t1重跑许可仍撤回，实际pf2失败/已执行修复轮2及此前全部失败原件保原；本次旧composite捕获不清计数、不代新t1重试。06当前V2 qualified六包0仍有效，main clean2d8、其原sourceWT/env/images/marker保持冻结。实际风险oracle、修后driver/wrapper组合、t1实测及最终E/H/release/EXIT/tag均未预签，无push授权。

本人仅本地读取已复制原件、用stdlib校验JSON/摘要并对照Git/source，未访问节点、执行任一稿/产品/语法/lint/编译/镜像、实施产品、创建子agent或push/tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-old-risk-capture-r1-review.md`；SHA256：`e9aad8f3aadb7fef610be6c0cea4568580b6742f5a9379b144dd6cd471e63853`。

---

# P6 S5 E 固定旧 Comparison→Risk 捕获 Python 稿独审 R1

结论：**SCRIPT_CHANGES_REQUIRED；不批准执行r1。** 固定原件 `/home/dev/gdds-s5-logs/execution/e-t1-old-risk-capture-r1.py`，实算SHA256=`c7fe6d901aaf0d3f5d222f690db13ebddf4839d7e66ca8d677b7aaf5340e7343`。此稿尚无固定外层或任何实际执行；仅为旧独立预期组件捕获的静态审，不新增DC68实际轮次，不授权t1重跑。

本原审在clean detached OLD6786 reviewer WT逐项核所有实际owner imports、字段、DTO方法、materialization→canonical/storage facts→Comparison records publication→Risk真实顺序及reader/native收尾。OLD=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、vnext6368、Ruste2a固定；不是把当前S5接口套到旧源。

## ORISK-1 — 已取得reader的清理可能被前置assert或另一组close异常跳过

`canonical_package`先取得`business`，在建立try/finally前就assert COMPLETE/snapshot/table_set；若owner返回失败但含partial table_set，则其readers没有被登记/关闭。其finally依次close projected、business、失败canonical：现有`close_tables`虽尝试本组各reader后抛首错误，但这会跳过随后其他组。外层finally同理，before关闭异常会跳过current。已发生的正常路径可能不触发，但捕获稿需要保原错误并完成已取得资源收尾，不能依赖进程退出/GC代替owner close。

最小使用标准`ExitStack`/`closing`，在每个owner返回资源后立即登记其真实主/batch reader close，保证一个close异常仍尝试所有已登记callback；保product/native先于最后canonical reader关闭、都在同kernel scope内，projected/business原必要寿命不扩大。不要新增cleanup框架、故障矩阵或修改旧产品；修订须新不可变稿，r1保原。本项已发协调者与原实施者连续修订。

## 已核接口与非finding澄清

- 协调消息所疑`RiskEvaluationInput.risk_cache_session/risk_task_keys`在真正OLD contracts.py1150/1151已存在，旧`NativeComparison.session/task_keys`在production.py427/428也已存在；旧pair_pipeline原就传这些字段。**不能将此记作S5新接口或旧源不存在的finding。** 本稿单次compare未给session时两者默认None，可为最小捕获省略，属于简化而非修复不存在字段。
- 旧`RiskReport.to_document()`确有overall/diagnostics/risk_report_contract_version/tables/annotation_refs/evaluation digest；`RiskEvaluationResult.to_document()`确能保完整旧bindings与结果status。`DetailedFactsResult.records_closure.records`、entry.family/record_count/records_content_digest，`RiskAnnotationArtifact.content_ref/content_digest`、schema_changes.schema_evolution都存在且类型匹配。
- `publish_records_closure_arrow(product.result,product.handles,output_store,context=RecordsPublicationContext(checkpoint=...))`匹配旧签名，要求同现存operation scope；产物facts/closure真实绑定。Risk默认完整V1规则、RiskOptions及record_views=旧product.risk_handles，与旧History业务路径一致；原风险产物/完整annotation documents与logical content digest保留，不从新History生成expected。
- canonical_package复用旧census实际staging/parse/business/projection/canonical owners，完整表集合配各source_schema_digest/storage facts（没有仅凭SQL文本猜标准/有序分类），固定两包输入SHA、旧source/import/native __build_input__绑定均已核。初始化pool1后同N1/M24 scope，原生Comparison关闭后再reader关闭是必要顺序；ORISK-1关闭后还需结合固定外层核整体scope/日志与退出。
- 独立SYX手算使用固定六个gid的旧uint64八字节big-endian frame，验证三ROW_ADDED/三ROW_DELETED的真实row identities、六个编号、ROW target与MEDIUM_LOW规则。其余所有表风险、targets、reasons/evidence和编号仍完整捕获，不把六条代表当整个结果总数。没有hardcode risk0、没有删guard、没有mock owner、没有HTTP/DB/Compose/runner/完整旅程。

本稿结果当前未知，任何实际业务expected仍须旧capture实际0原件及本审核收后才能进入下一t1 driver。旧composite EVIDENCE_GO只证明composite UNCHANGED4/4无变更，不能代SQL风险oracle；已执行pf2修复轮2/失败原件及06 qualified source冻结均保原。

本人仅本地只读核稿SHA与实际旧源码/Contract，未访问节点、执行本稿/语法/产品测试/lint/编译/镜像、实施产品、创建子agent或push/tag；不签oracle执行、t1/E最终证据/H/release/EXIT/tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-old-risk-capture-r2-review.md`；SHA256：`12250f991a44e17e8c6bc1bcf92bedf584fa594ace643c7d3b67363265429cfc`。

---

# P6 S5 E 固定旧 Comparison→Risk oracle 联合连续复审 R2

结论：**SCRIPT_GO / RISK_ORACLE_EXECUTION_GO；ORISK-1 CLOSED**。仅绑定下列不可变组合，可由唯一测试者在同04 fresh现场核空闲、原子本人占用、新旧源专属WT/ref/runroot中执行一次最小旧组件捕获。**此许可不是当前t1重跑许可、风险结果预签或E最终证据/退出GO。**

| 原件（`/home/dev/gdds-s5-logs/execution/`） | 本审实算SHA256 |
| --- | --- |
| `e-t1-old-risk-capture-r2.py` | `f5a3a003c822207628e11e4c829fd4524411e8efa374b8999b6828e610eb99e0` |
| `e-t1-old-risk-capture-r2.sh` | `9f63d4ff58391eed2e307fe85c33472a129770c95815b89e07669e8375d53a42` |

本原审重新核未执行r1 Python SHA=`c7fe6d901aaf0d3f5d222f690db13ebddf4839d7e66ca8d677b7aaf5340e7343`、r1 shell SHA=`b0e61483f9a01f925f9a1d6766850c4afcdb14b663638609f3fc6323f12c9493`保持原字节，完整逐行核Python增量及新shell全稿。旧接口/字段逐项核查见 `e-t1-old-risk-capture-r1-review.md` SHA=`e9aad8f3aadb7fef610be6c0cea4568580b6742f5a9379b144dd6cd471e63853`；真正OLD的cache字段原本存在，r2保留它们并非引入S5新接口。

## ORISK-1 连续关闭

Python现在在producers ExitStack内取得business后立即登记其table_set close，再检查status；projected取得后立即登记再检查；canonical取得后立即登记到外层canonical_readers ExitStack再检查。组内close_tables仍尝试全部主/batch reader后才抛首错误，跨组ExitStack确保一组close异常不跳过其他已登记组；partial/失败结果也已登记。删除原finally中会短路的组间循环及before/current顺序关闭。

projected/business在各canonical_package返回时按原必要寿命先关闭；外层canonical_readers保持两侧权威reader到其Comparison/Risk真实消费结束。`with closing(compare_plan_native(...))`位于该外层stack内，native product先关、其后两侧canonical readers均尝试close，再退出同kernel scope。没有新增cleanup框架、吞错或产品变更，ORISK-1静态关闭；不为临时捕获稿新增故障矩阵。

初始化/业务捕获不变：真正OLD的pool1+N1/M24 context包住两固定包完整canonical→Comparison→records publication→Risk，默认V1规则与RiskOptions、真实risk_handles与output store；读完整RiskReport/Result和annotation contents/logical digests，保全部targets/IDs/编号/reasons/levels/evidence、records族counts及schema/table facts。独立SYX六个uint64手帧核row identities、三增三删规则、MEDIUM_LOW和六个编号；不把六条代表冒所有表总数，不假定整体risk0，不使用新History actual生成expected。

## 外层与固定旧来源

shell沿已真实通过的旧composite捕获profile，新namespace `OLD-risk-oracle-r2`独立于旧composite和pf0/pf1/pf2，不覆盖任何原件/ref/WT/marker。固定OLD=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、vnext=`6368c9c40cf08a97eecf2a0c457a6c16ce448080`、Rust=`e2a901417b19259ece669637a41545e774261445`；current main只供Git objects，不以其不同vnext执行。完整named bundle/ref/SHA、remote exactOLD/vnext/Rust、clean detached WT+legacy、source checkout022后私有077均核匹配。

本地pinned Python绝对路径/完整SHA，复制后再核、LAN传入本人evidence、remote重核，执行前再核；AST是节点实际工具步骤。root Cargo PATH/selector四工具、禁设Rust环境、normal旧backend项目venv、UV/Cargo offline、无proxy/PYTHONPATH覆盖，强制旧native重装及build-input均沿已审规则。实际范围只五步：工具链、旧native sync、build-input、AST、old-risk-capture。无host Dolt、test_input_closure、HTTP/DB/Compose/镜像build/runner/完整旧旅程，不触06来源WT/env/images。

受控入口明确`uv-consume -C OLD/backend run --no-sync python - --oracle-output <本人evidence>/oracle-result.json < pinned_capture.py`，没有外script target/runpy/裸uv/另project，原locked/no-sync check/index隔离/五锁保护保持。程序绑定CWD/source/import路径和native旧buildinput、关键source blobs及五依赖输入SHA；两个包size/SHA及唯一ordinary XML成员严格校验，raw XML事实不冒语义。capture参数与字段均匹配真正OLD owner，`to_document`/records_closure/artifact ref/content digest/schema_evolution早前逐项核过。

逐step记hostname/UTC/HEAD/command及tee numeric/日志SHA，原entry/copy/hash分别保留，输出完整result而非仅摘要。两处`[p]ython.*--oracle-output <同runroot>/evidence/oracle-result.json`存活guard与实际stdin argv一致，Docker query失败拒绝release，只有本人所有权和全部空闲才删本人marker/rmdir空父目录；已释放/非本人local fallback记skip0，原非零不覆盖。旧WT/venv/native/cache/bundle/raw保留，不清其他任务资源、不prune/rebuild/retag。首非零停止后继，原件交本审，不自动重试。

本次是补独立风险预期的最小必要组件捕获，执行前r1→r2静态修订不增加t1实际轮次，但也不清零已执行修复轮2/pf2失败事实。actual oracle全0与完整业务字段仍待本审核收；随后才能据独立结果修正t1 driver预期并审固定新组合/所需实际修复轮许可。当前t1许可继续撤回，06 V2 qualified六包0及冻结资源保持；最终E/H/release/EXIT/tag均未预签，无push授权。

本人未访问节点、执行本稿/语法/产品测试/lint/编译/镜像、实施产品、创建子agent或push/tag，仅本地只读核source与固定原件；root或实施者语法结果不冒本审或实际oracle证据。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-old-risk-evidence.md`；SHA256：`bc20d2b8d29d6c16898b53097f60121fda0d96633c5c4dd87a38bd55d3fabb40`。

---

# P6 S5 E 固定旧 Comparison→Risk oracle 原件核收

结论：**OLD_RISK_EVIDENCE_GO**。固定OLD6786两份t1包的独立旧owner输出已核：Risk READY、overall MEDIUM_LOW、1 table、6 annotations；全部来自SYX三增三删。完整风险业务字段/targets/编号/content digest和ORDERED6＋STANDARD6的独立逻辑digest可作为后继t1期望来源。**当前不授权重跑t1；修后driver＋wrapper仍须联合原审GO，不预签E最终证据/退出。**

## 固定原件与退出

原件根 `/home/dev/gdds-s5-logs/execution/e-t1-old-risk/6786b28a3506feab3d8eac7d1288c8b22525bb8f-risk-oracle-r2/`。entry shell SHA=`9f63d4ff58391eed2e307fe85c33472a129770c95815b89e07669e8375d53a42`，capture Python SHA=`f5a3a003c822207628e11e4c829fd4524411e8efa374b8999b6828e610eb99e0`，与已审不可变稿相同，remote实读stdin原字节亦同SHA。

actual hostname=`gw-dms-test-04.lan`，remote session=`2026-11-09T13:04:09Z–13:05:14Z`。起止OLD=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、vnext=`6368c9c40cf08a97eecf2a0c457a6c16ce448080`、Rust=`e2a901417b19259ece669637a41545e774261445`，clean_end=yes；local main起止仍currentV2=2d8。local/remote完整SHA256SUMS及checksum全项通过；独立逐step核恰5步、exactOLD/command0/tee0/实际日志SHA：工具链、强制旧native sync、旧build-input、AST、old-risk-capture。原entry/remote/tee/copy/hash/release均0，本人marker rm/rmdir0且released=yes，local fallback记录已释放skip0。旧WT/env/cache/bundle/raw保留，未改06 frozen source资源。

| 原件（相对根） | 实算SHA256 |
| --- | --- |
| `SHA256SUMS` | `5d51faa2809dd1927776981dfeb0e3bf854bfd6c21ee6ffdcf7ff61efa619ef1` |
| `remote-evidence/SHA256SUMS` | `d245d2d1725a4c8dc8f42b7ef4a2c9a9df263e205a9659a0c38ef2a50e0042a4` |
| `remote-evidence/session.log` | `34887837b6790baa790a66dfe3f7ea6bc573cb98d9a6ca15257a6d563a3bfa9f` |
| `remote-evidence/oracle-result.json` | `d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a` |

实际old native expected/installed/captured buildinput均e2a；所有记录import路径在本OLD WT内，native.so也在其独立旧`.venv`。捕获key_source_blobs逐项与本审OLD Git tree对照相等，locked输入SHA保原。实际N1/M24 scope的charged high water=`25547679616` ≤ `25769803776`；这是预算HWM，不冒RSS/cgroup peak或性能结论。没有HTTP/DB/Compose/runner/完整旧旅程或host Dolt，actual native与Arrow/record/Risk消费按已审生命周期关闭，原numeric0后才释放本人marker。

## 独立业务结果与交叉核验

输入仍为固定 `rd-t1-a-v1` 107115 bytes/SHA427940…、v2 107066 bytes/SHA401973…，完整值在原JSON与此前输入审查一致。XML各81 bytes及两个不同SHA亦与已核composite oracle一致；先前XML raw相等断言已被证伪，而composite旧owner独立结果仍UNCHANGED4/4、零变更/零records，不冲突。

全部125张table facts已捕获；唯一具有row changes的表为 `b1_n2_iec104_syx_list`：MODIFIED、schema_evolution=NONE、3 added、3 deleted、0 modified、suppressed0、diagnostics空。风险完整结果READY，overall/table均MEDIUM_LOW，reason_codes=[ROW_ADDED,ROW_DELETED]，1 table/6 annotations，无其他风险表或诊断。旧规则确发逐STANDARD row annotation，因此原risk0基线不成立。

本审独立重算固定SQL六个gid的uint64八字节big-endian frame，核其实际target.row_identity及rule/level/ROW/table字段。完整编号与gid对应：

| annotation尾号（表名前缀保原） | gid | rule |
| --- | ---: | --- |
| 00000000 | 28 | ROW_ADDED |
| 00000001 | 30 | ROW_ADDED |
| 00000002 | 29 | ROW_ADDED |
| 00000003 | 10 | ROW_DELETED |
| 00000004 | 9 | ROW_DELETED |
| 00000005 | 8 | ROW_DELETED |

这六条不是仅凭总数匹配：每个完整target空/非空字段、changed_columns、编号、risk level、reasons/rule/message/evidence和diagnostics都保留在原annotation document，不归一化/遮去业务字段。本审以其确定性JSON载荷独立重序列化并算SHA/size，实际3001 bytes、content digest=`sha256:f4105ca4ae8af4c70d109fec3bb33542434f33014a11a2cd68ec5cdbbef617e4`，与旧artifact.content_digest、content_ref.raw_sha256/size以及risk_business所记值相等。无当前codec自roundtrip作expected。

完整records族只有该SYX表的两个entry：

| family | count | 旧owner logical content digest |
| --- | ---: | --- |
| ORDERED | 6 | `sha256:e79378d966f39a1296a0e7452333a43d0ef547f3a41e1989314b77b44f2a4e5b` |
| STANDARD | 6 | `sha256:0d3af5be7293af911e9a8e0e25ef0fda3a056648be3d57e5bf4997925a0b18c0` |

总logical records=12，但Risk=6是由实际旧Risk owner对STANDARD facts/targets产生，非从12除二猜出。旧risk_business完整overall/diagnostics/report contract/tables/annotation documents/content digests保存；完整risk_result_with_old_bindings另保READY、risk model=`backend-vnext/risk-model/v3`、ruleset digest、旧comparison/evaluation digests及各artifact refs/closure。不得把这些旧binding要求新当前repository/commit直接相同；只可按现行owner将当前binding另验、比较完整中立业务字段及annotation/records logical digest，不掩盖targets/编号或从新History反填expected。

## 后继限制

此OLD_RISK_EVIDENCE_GO仅提供固定旧源码、同固定输入下的独立预期，不是当前S5 t1实测、当前包qualified来源或carried。后继driver须强制pin此完整JSON SHA、OLD/vnext/Rust/inputs/source关系，核全部风险业务字段及完整records族count/digest、保六条手算，不再hardcode零风险；composite独立七字段与各XML分别SHA应引用已核旧composite原件SHA3707…，不能重新断言raw相等。

新driver和wrapper须固定不可变稿原审联合核入口/预算/冷暖/闭包/秘密/原件/收尾后，才能给下一实际修复轮的唯一执行许可；当前t1仍暂停。pf0/pf1/pf2所有原失败和实际已执行修复轮2事实保持，不因old oracle、文件名/目录/节点清计数。06 qualified currentV2全六包0及原WT/env/images/marker冻结不动，无产品变更或完整门禁重测需要。E最终证据、精确H绑定、独审授权release/actualrelease0/final exact-H EXIT_GO及tag均未预签，无push授权。

本人只本地读取已复制原件，用stdlib核摘要/JSON/手帧及Git source blobs，未访问节点、执行产品/语法/lint/编译/镜像/任一执行稿、实施产品、创建子agent或push/tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-remediation3-review.md`；SHA256：`e65e3dfe3371e1c3b3d93a109dbf5a021e15dbdaba5879d62122aa04c0f736ee`。

---

# P6 S5 E t1 独立预期修复联合复审（实际修复轮3）

结论：**DRIVER_SCRIPT_GO / WRAPPER_SCRIPT_GO / T1_REMEDIATION3_EXECUTION_GO**。仅批准下表固定组合，由唯一测试者在同04现场核空闲、fresh本人原子占用、新pf3 clean committed V2 WT+legacy、独有RS tag及私有secrets，从头执行一次既定最小t1。实际完整旅程、E最终证据/H/release/EXIT仍待原件核收，不预签；本GO不授权自动重试或第四轮。

| 固定外置原件（`/home/dev/gdds-s5-logs/execution/`） | 本审实算SHA256 |
| --- | --- |
| `e-t1-r6.py` | `7665a6ef4fbc16daa0ae611f0dbc185696bc95dcde4f108fde4561b9ecc6edf9` |
| `e-t1-run-r7.sh` | `79d8c4f5a7838a7707327d02c2020c842332f6df7a36f9e7dc933d33c03f2758` |

本原审重新核r5 driver SHA157d4…、r6 wrapper SHA7f05…保持原字节，完整逐行核两份增量及当前真实owner字段/返回形状/digest语义。原r5+r6及其旧GO均不再提供当前执行许可，原报告字节不改；此新组合取代它们。当前V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`、vnextfb92、Rustc021和06 qualified六包来源完全不变，不做产品/锁/golden修改或额外门禁重测。

## 独立风险、records 与 composite 预期

driver新必填`--old-risk-oracle`绝对文件，严格pin完整JSON SHA=`d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a`、OLD6786/vnext6368/Ruste2a/native旧buildinput、两个固定包size/SHA与各XML size/SHA、exit0及独立六identity交叉PASS。该原件已由 `e-t1-old-risk-evidence.md` 核为OLD_RISK_EVIDENCE_GO；known完整SHA本身还固定READY/默认旧规则/全部捕获字段，不由当前History生成expected。

actual Risk report business投影与旧oracle的overall、diagnostics、report contract、全部tables业务字段完整相等；完整annotation documents和每表content digests整体相等，保IDs/targets/编号/reasons/levels/evidence/空字段，无业务mask。仅分离旧source的comparison/evaluation digest及artifact refs等外层binding，当前实际risk evaluation原值继续保存并与History HTTP pair.risk_digest对齐，不把旧binding硬要求到当前repo/commit。

actual records从真实open_records_closure/read_records_artifact取得，逐族table/family/count/logical content digest完整列表等旧oracle（ORDERED6 e793…、STANDARD6 0d3a…），不只比总12或六条代表；原六uint64八字节手帧的ORDERED identities/业务values/positions/counter-side空值断言仍保留。记录完整semantic/实际rows并按原standalone diagnostic API关闭reader，host pool1已显式初始化且不加operation context。

**新增raw/content digest实际类型和语义已核**：当前`BundleClosureEntry.raw_sha256: DigestRef`且等`artifact_ref.raw_sha256`，`.value`确返回带`sha256:`前缀；Risk `_artifacts`用canonical JSON content原字节的raw_blob_digest作为artifact.content_digest并在读取时验证。annotation content不含外层comparison/evaluation/artifact绑定，bundle只重写refs，当前annotation没有待改写外层ref。因此用entry.raw_sha256.value与旧annotation content_digest.value相等比较是同一内容/格式，不是仅按字段名称猜测；先行verify_bundle_tar已校验完整成员raw SHA与闭包。

composite不再要求两个XML原字节相等；每份分别严格核81 bytes与已核03f90…/7d0fec…SHA，记录实际equal=false。完整七字段literal为旧oracle已实际证得UNCHANGED/4/4/added0/removed0/modified0/history0，并标exact OLD/vnext/Rust与composite完整原件SHA=`3707ad9891efa47a2d1b5fdb88e51f9b77880d7532826db1ff4d5a6476ab5261`。这些literal逐项对已核旧JSON相符，是获准的固定旧source捕获预期，不是当前codec自roundtrip；expected总records与v2 changed-table范围保原语义。旧错误risk0断言已被独立完整6annotation预期替代，不是删掉断言保零。

## 当前 HTTP/tar/digest 绑定

已读实际`j._history_compare`：返回tuple(result_value,operation_id)，result_value含原HTTP pair、完整下载验证的bundle manifest和原HTTP result.bundle_digest。新增`history.bundle_digest == history.bundle.bundle_digest`与该真实形状一致；History assemble/status原值存在，tar manifest digest由现有transport owner重算，不另GET。

同exact before/current pair的cold/warm分别直接比原`comparison_digest/risk_digest/surface_digest`，加上actual report.risk_evaluation_digest与HTTP risk_digest匹配，完整冷暖semantic亦继续相等。根据真实History pair输出和Comparison/Risk/Surface owning Contract：operation/request/pair外壳ID、opaque raw refs不进入业务digest；同快照/rules/options、annotation内容、closure integrity identity相同则三digest稳定，surface ref重写保持digest。故这个断言有真实业务合同依据，不要求两个operation的bundle manifest本身等同；bundle只各自与本次HTTP对账。无新增把不同operation/rawrefs任意mask来制造相等。

## wrapper 的来源、命名空间与收尾

wrapper从已核旧Risk result精确本地路径读取并验SHA，复制immutable JSON后再验、传到本人EVIDENCE独立input、remote启动与临用各再验，最后以必填flag给driver；其JSON随完整递归证据保留。原driver copied bytes/SHA/AST和临执行SHA、受控project Python stdin、normal native强制重装/build-input/RS source build保持；新remote第13参数仅oracle SHA，旧1–12解析顺序不变，无入口/argv错位。existing own-driver存活guard仍匹配唯一同RUNROOT的`--output .../evidence/journey`且防selfmatch。

profile明确3，KEY/session/Compose/WT/ref/local/RS tag均随新driver短SHA7665a6ef4fbc和pf3派生，不覆盖旧pf0/pf1/pf2、旧oracle或06来源镜像。source资格仍先核本次V2全部六包0原件；offline/cache/checkout022后077/backendbase1/networknone无PREBUILT/N1/M24/envelope32、私有secrets在EVIDENCE外、本人所有权与空闲才release、原numeric/tee/copy/hash及failure state保留均无放宽。

真实范围仍是必要两包v1/v2 Preview/Submit/approve、只v1 Archive合法基线、一次本人派生冷态History与newkey/newoperation暖History、实际records+完整四tar+全部表schema/content、RS冷HTTP正校准/暖rows0、kernel/单侧summary0及restore>0、metadata/demands/records validation/digest rebind/预算HWM与真实cgroup分列。没有扩大FULL/三节点/损坏/恢复真实矩阵，没有删除authority commit/manifests/物理资料；不改既有focused所拥有的恢复/风险/身份语义证明。

日志明确current independent expected修复、current_profile_revision3、prior_actual_repairs2及pf0/pf1全部原失败SHA；另固定pf2真实root/logSHA beb253…/resultSHA5b667…。第3轮是本t1执行profile累计实际修复轮3，独立旧oracle只是必要预期前置，既不重置计数，也不改写前两轮实际执行/全部失败事实。本许可只给一次修后流程；首失败立即停后继验收、保原件，由原审/协调者按既有DC68规则处理，不自动再开新目录/节点继续验收。

06 V2 authority source WT/env/images/marker继续冻结供最终同node/WT六包compare与image binding；当前main clean2d8。实际t1结果未知，最终E证据、纯docs H、H绑定核收、独审授权release/actualrelease0/final exact-H EXIT_GO及本地tag均未预签，无push授权。

本人只本地只读核固定稿、真实source/Contract与已核旧原件，未访问节点、执行产品/语法/lint/编译/镜像/任何执行稿、实施产品、创建子agent或push/tag。root的bash-n0不是本审或实测结果。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-pf3-diagnosis.md`；SHA256：`e5d4ede9b69ba6e62d4b324a41ca297c3951af2920a76709daa9dcbeee997ec1`。

---

# S5 E t1 pf3 原始失败核收与最小续验诊断

结论：**PF3_FAILURE_EVIDENCE_ACCEPTED；ET1-PF3-1 为外置 consumer 错误假设，尚未修订关闭。当前没有新的执行 GO，也没有 t1/E 最终证据 GO。** 可准备“保存 cold 原件只读补核，再对原合法节点作一次 new-key/new-operation warm”的固定最小续验稿，交本原审后执行；不需要自动重做两套前置或第四整旅程。

审核者为 E 原独立评审。本次仅在本地读取已复制原件、Git 固定源码，用标准库核 JSON/tar/摘要；没有 SSH、节点访问、产品 decoder/测试/语法检查、镜像构建或实现。源码审核在 clean detached `/home/dev/gdds-reviews/p6-s5-e-2d8b29d332`，HEAD=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`（V2），vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。原 source06 全六包 actual0 与其冻结环境/镜像保持独立有效；本次不重签或改动该来源。

## 1. 原始执行、失败与收尾

原件根：`/home/dev/gdds-s5-logs/execution/e-t1-run/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-7665a6ef4fbc-pf3/`。绑定 driver `e-t1-r6.py` SHA256=`7665a6ef4fbc16daa0ae611f0dbc185696bc95dcde4f108fde4561b9ecc6edf9`、wrapper `e-t1-run-r7.sh` SHA256=`79d8c4f5a7838a7707327d02c2020c842332f6df7a36f9e7dc933d33c03f2758`。

本地 `SHA256SUMS` 631 项和复制来的 `remote-evidence/SHA256SUMS` 615 项分别逐项复算，全部相符，检查退出均 0。本地 manifest SHA256=`45ae39e623c4ee1bbdc17894e23ff9ae21a3eacd31c8c44523c8f9efb3689ef8`；远端 manifest 原件 SHA256=`ef8348737b4658d3f098ae1fc9e4845c8a4a83f7fdb2644375aed322a2db1e54`。

| 原件 | 实算 SHA256 |
| --- | --- |
| `remote-evidence/session.log` | `ccbee3f70fb08ebb423be7acbf197f240b256661f503e7c3965f538f7c600e78` |
| `remote-evidence/t1-driver.log` | `c8c349868621337e8d76e2178e5cf096975cc17be93ad86ed7a85b5cf1d07415` |
| `remote-evidence/journey/result.json` | `811c255b8b01aab42dd1a844a59da3bf24d4ba17d5d15cb8ec75b856bb59854e` |
| `remote-evidence/journey/bundle-02/complete.tar` | `93da19c776c8840338ab2f89b8450a4c7572bda742d55ea06fd52fc066b769b7` |
| `remote-evidence/journey/bundle-02/transfer.json` | `8bcbb7cd00c542278fc4ebb586fd85638a65be74fc351bf53ae17cc32d75014e` |
| `remote-evidence/journey/bundle-02/members.json` | `ce28c70190ec21a76c5b7f01f26f878172e2b6bca7d02a65ca284841db29c9ea` |

04 `gw-dms-test-04.lan` remote session 为 2026-11-09 13:15:56Z–13:21:07Z。起止/逐步均 exact V2，结束 clean。前七步 toolchain、inputs/bases、driver AST、强制 native sync/build-input、RS sync、RS build 的 command/tee 均 0；`t1-driver` 为 **command1/tee0**。原入口保持 1，复制/校验及 guarded release 均 0，`stack_stop_exit=0`，本人 marker remove/rmdir0、released=yes，原 WT/venv/private secrets/本人 stopped containers 与 volumes/证据保留。没有把后续归档成功写成业务成功。

两套合法 Preview→Submit→approve 前置成功，v1 Archive 已成功建立基线；v2 的 final Submission 按已核 owning consumer 可作为 History 节点，无须附加 Archive。cold History 请求自身到达 SUCCEEDED，原日志 operation wall=44.148s；下载完整 tar 后在 driver `inspect_history` 第256行失败。**warm 未执行**；冷请求外层结果、差量日志、冷后 cgroup 与主流程 semantic 文件均未完成写入，不能表述为整段 t1 通过。

## 2. ET1-PF3-1：可选物理 risk report 被当成必需的唯一对象

失败表达式是 `closure_count == 1 and len(reports) == 1`，消息 `History records/risk closure required`。实际第一个条件成立，第二个条件为 0，不是 records closure 缺失。

当前 owning 路径逐项核对：

- `application/history/compare_jobs.py:943` 将实际 pair surface、records closure 和 exact before/current 节点交给共享 `surface_artifact_closure(... include_all_tables=True)`，再 `assemble_bundle`。
- `application/pair_pipeline.py:449` 的 `SurfaceAssemblyInput` 传入内存 `risk_report` 与 `risk_annotation_closure` 对象，并未传入可选物理 `risk_report_ref`/`risk_annotation_closure_ref`。
- `surface_assembly/contracts.py:669` 的 `SurfaceRootRefs` 明确定义这些风险物理 ref 可为 None；`_assembly.py:148` 从实际 RiskReport 生成 view risk level/evaluation digest，从 Risk closure 生成逐表 level/reason/count 及 annotation/manifest refs，物理 report_ref 保留请求值。
- `application/preview_jobs.py:1690` 的 closure `add(None)` 正常返回。RISK_REPORT kind 还可分别来自根、表或 projection，不具有“整个 bundle 恰一个主 report”的基数保证。

故本次是外置 consumer 将未获 Contract 保证的物理对象/基数作为准入条件。当前原件没有显示任何应存在的非空 report ref 指向缺失成员，不能据零 RISK_REPORT 判为产品漏闭包。相反，也不能把内存 RiskReport 对象、旧 oracle 的完整业务报告或 Surface 投影冒称成当前实际导出的物理报告。

修订应按 **Surface 的实际引用图** 选择 records closure、主/辅助报告及 annotations；非空根/table/projection ref 均要闭合及核完整性，None 则记录实际形态。当前 actual 可与独立旧 oracle 严格核对的风险内容包括：Surface overall level、全部表 risk level/reasons/count、完整 annotation JSON/编号/target/evidence 及 content digest、annotation manifest、risk evaluation digest 对 HTTP pair 的绑定。旧报告中未物理导出的 contract-version/diagnostics 等字段必须列为不可直接观察，不能以填 expected 或删除全部风险核查代替。所有 records 与 snapshot 断言保持。

## 3. 保存 cold tar 的独立原件事实

`complete.tar` 大小 **2,153,472 bytes**，116 个普通成员；114 个 closure entries。已用标准库逐个读取成员，复核 size/raw SHA、归档副本一致性和普通 JSON 中的实际引用闭合。成员 kind 为 SURFACE1、RECORDS_MANIFEST1、RECORDS1、RECORDS_CLOSURE1、OTHER2（ordered refs）、RISK_ANNOTATION1、RISK_ANNOTATION_MANIFEST1、SNAPSHOT_TABLE106，RISK_REPORT0。物理 snapshot 内容去重后有 **250 个唯一 before/current table bindings**，分别覆盖两个 exact catalog 的 125 张表，不等于只有106个业务表。

冷 operation=`op-b8408f429d026545fdd3d8fe`、pair=`op-b8408f429d026545fdd3d8fe-p0`。实际 Surface root `risk_report_ref=null`、`risk_annotation_closure_ref=null`，records closure ref 非空并闭合；所有表 report_ref 也为 null。view 为 MEDIUM_LOW、125 tables、changed4、degraded0、failed0。只有 `b1_n2_iec104_syx_list` 有6条风险 annotation，level MEDIUM_LOW，reason ROW_ADDED/ROW_DELETED，annotation/manifest ref 均闭合。

完整 annotation document 与独立 OLD oracle `d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a` 一致：6条，3001 bytes，SHA256=`f4105ca4ae8af4c70d109fec3bb33542434f33014a11a2cd68ec5cdbbef617e4`。其 manifest raw SHA256=`08d66283f13511d497e5237d94e2aca6c034dffbcecbfc0aa253e21a113165ad`，内容计数/摘要绑定相符。保存 records closure 的 ORDERED6、STANDARD6 及两个 content digest 与独立 OLD oracle 相符；原节点 `verify_bundle_tar` 在异常前已执行 native 全文 records validation，并记录完整12条。当前开发主机未执行产品 decoder。

| 实际 cold 摘要 | 值 |
| --- | --- |
| comparison | `sha256:cc51a9ff6e91d95bb8ad4f00135f031559c8938bd03b22466ce5493614d4686d` |
| risk evaluation | `sha256:cdefa93c80d7a7b09be713143cae0d8d0d3f5815f78b205f807cb5d6f399e8e3` |
| surface | `sha256:81eeff34068447eefddf20843e35bc3e1b20f9e5d91dec423f12498a056105ff` |
| bundle | `sha256:676679300e22ed95dfb781ca3f842e177a2ff04f13f49930a2af5b733d83adf1` |

本次仍须补核保存 tar 的最终 schema/每表 row count/内容摘要、手算代表及 records facade 检查结果：原 driver 曾读取 Parquet/schema，但在准入错误处抛出，后面的 `check_records`、全表 count 对账与 semantic 写入尚未完成。不能把代码本应执行的断言当作已执行。

## 4. 日志、预算与缺失的边界

保存原 worker stderr 中有唯一 exact cold pair 的 `s3_pair_metrics`：charged HWM **25,438,132,736 bytes**，小于 M24=25,769,803,776；comparison kernel1、ordered single-side8、native calls9、input reads10、cache restore0、cache records validation0、diff lookup9、digest rebind125。两条 `s5_history_metadata` 各为 canonical metadata2/catalog2，应分别保存并累计4，不能当作只有一次。已见 demands 为250、export-cache-hit0；分层值不得互相替代。

这些原日志可作为后续 supplement 的来源，但原 `worker_before/rs_before` 差量未落盘。若需恢复严格冷 HTTP `/rows` 正校准与相应窗口，必须由唯一测试者从原 stopped containers 的历史 Docker timestamp 日志提取，和已保存原 final stdout/stderr 前缀、exact operation/pair、UTC 对账。原 `history_compare_started` 为 **13:20:19.019Z**（POST前），`operation_started` 为13:20:19.049Z（accept后）；只取后一时刻至 SUCCEEDED 13:21:03.197Z 不能声称覆盖完整请求及后续 tar GET。使用可证明的冷前边界至完整下载/停止边界，并如实标注“历史时间窗重建”，不冒充原实时差量。admission INFO 不可观察时保持 null。

实际 worker `memory.max=34,359,738,368`（32GiB）已记录；现存 cgroup 仅 initial/prerequisite peak **114,012,160 / 191,356,928**，events0。**cold cgroup peak=UNKNOWN**，不能将前置 peak、预约 HWM 或事后新 cgroup 值回填为 cold 实际峰值。冷 History SUCCEEDED、真实 M24 charged HWM 与32GiB硬限额是不同证据；可证明本次按有限预算成功，不能宣称已测得冷 RSS/cgroup 高峰或性能结论。暖请求如获执行应捕获其实际新 cgroup peak/events。

## 5. DC68 具体故障与允许准备的最小续验

当前 V2 AGENTS 第68行与 testing-conventions 第65–71行写的是 **同一具体根因** 首次失败后最多三轮固定修订/适用独审/受影响复验；首次失败不计修复轮，不能换目录/候选/角色重计同根。不能仅把 pf3 的文件名或全流程累计 profile 号当作某一具体故障已经三修失败。

历史原数值及累计记录全部保留：pf0 unused host Dolt config 前提失败；pf1 外置 `.py` 被 uv-consume project guard 拒绝；pf2 独立 expected 错将两个 XML raw 相等且原风险零预期无依据。前两项由实际后继步骤证明已消除，第三项由固定旧源码 composite/Risk 捕获及 pf3 实际前置证明完成独立预期修正。本次是 **可选物理 RiskReport 必需性假设的首次实际触及**，不是上述任一具体根因连续三修仍失败。先前“实际修复轮2/当前profile3”事实不清零，但不因此人为构造新的 Owner 实质取舍。

本次产品已运行不自动剥夺现行 DC68 自主修复授权。原因已明确、本人资源已安全停止、原失败保全，且不需改冻结产品/Contract/golden/M/输入；因此未发现必须由 Owner 另作范围决定的确定硬缺口。适用最小修订仍须由本原审核固定脚本，**当前只认可下面的准备范围，不授任何现稿执行 GO**：

1. 对已保存 cold tar 在04原 clean V2/native 环境作只读补核，验证完整 actual Surface 引用图、所有 records/annotations、全表 schema/count/content 及独立代表。新 supplement 单独写出，不改原 result/exit1/log/manifest，不新增 bundle GET。
2. 对原 stopped worker/RS/backend 的历史 timestamp 日志只读提取并保原件/前缀绑定，恢复可证的冷 metadata/demands/HTTP rows 校准；缺失项继续 UNKNOWN，不重做 cold 以美化证据。
3. fresh 原子占用04后，核 exact 原 WT/legacy/native input/clean、原容器与全部镜像本机身份、现存卷/DB/合法两个 Submission commit、规则与健康缓存、私有 secrets 和无他人活动。不得 sync/build/retag、重做前置、删 derived cache、更换节点或悄悄冷启动替代健康命中。
4. 全部成立后，仅重启本人原 stack，对同有向合法 pair 发 **一个 new key/new operation warm**，完成第4个完整 tar GET；保存冷暖 comparison/risk/surface 摘要相等、实际 records/annotations/snapshots 语义相等、native compare0/single-side0/RS rows0/restore>0、metadata/cache/records validation/rebind 分列，并捕获暖 actual cgroup peak 与 charged HWM。整体 bundle 含运行绑定，不假设两个 bundle digest 必须相等。
5. 记录真实 runtime/source 与服务/两个 base 的 true save config/all DiffID/label 绑定（pf3 的 success-only image-save 步骤未运行，不冒称已保存）；关闭本人 stack/handles、释放本人 marker，保留原资源供独审。任何缓存/输入/镜像/合法节点状态不符即停止，不回退整旅程或无修改重试。

产品 V2 无改动，当前 consumer 修订不触发重建；最后合格容器门禁仍是 V2 source06 全六包同次 Compose，t1 当前仅保存04 pf3的实际运行镜像和日志，不宣称其完整旅程已通过。最终 E、H 绑定、release 与 EXIT_GO 均继续等待各自实际原件。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-cold-recheck-r1-review.md`；SHA256：`007e69ea118f29d4f04f4b6fb17ea4e0d869094cafd03dbd7a93d1af4bfbf91f`。

---

# S5 E 保存 cold 原件只读补核稿 R1 联合审核

结论：**COLD_RECHECK_SCRIPT_GO**。许可仅为唯一测试者在04取得 fresh 本人占用后，对原 pf3 保存 cold tar 作这一次只读补核；没有 warm、重启服务、HTTP、新业务请求或整旅程执行许可。没有预签补核实际成功、t1/E 证据或 EXIT。

固定审核对象：

| 文件 | 实算 SHA256 |
| --- | --- |
| `/home/dev/gdds-s5-logs/execution/e-t1-cold-recheck-r1.py` | `31af7983e1915cd3a51dc0b80ce32ebffea6dc8f0469ec7ce14e1af1513346da` |
| `/home/dev/gdds-s5-logs/execution/e-t1-cold-recheck-r1.sh` | `e724460e018f36b15bda1e5dfe0c959a50bc9977f478a0ec7bb0e9624e4a59d5` |

本原审只读脚本、固定产品源码及复制原件，未 SSH/访问节点、未运行任一稿、语法检查或产品 decoder。固定产品仍为 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`；只读 detached 审核 WT clean。

## 边界、身份和入口

外层 pin Python 完整 SHA，复制前后核字节；原 source root/WT 固定为04 pf3 `...-7665a6ef4fbc-pf3`，既存615项 manifest 的 SHA=`ef8348737b4658d3f098ae1fc9e4845c8a4a83f7fdb2644375aed322a2db1e54`。原 WT exact HEAD/vnext/Rust、clean、legacy 链接在 admission 核验；不 checkout/sync/build/retag，不改原源码、环境或停止态栈。原 native 由仓库 `check-rust-extension-build-input.sh` 的受控 `--no-sync` 路径只读核查，程序内再次核 native `__build_input__`；没有 host Dolt consumer/config 前提。

新 local/runroot/output 独立于原 evidence/WT/真实输入。程序将原 session/steps/driver/result1、两个前置、tar/manifest/members/transfer 的固定 SHA 与615项完整 inventory 全量核查，补核结束再次验证 inventory 未变。各固定 SHA 已与本地 actual pf3 原件逐项对账，包括 steps=`5c509e9c076804eb174fed5013c0149c56e025dda327e15bf65bdc06a6059543`、原 result=`811c255b8b01aab42dd1a844a59da3bf24d4ba17d5d15cb8ec75b856bb59854e`、完整 tar=`93da19c776c8840338ab2f89b8450a4c7572bda742d55ea06fd52fc066b769b7`。保持 original exit1/stack stop0，输出新 supplement；不回写原失败。

唯一实际入口是当前 backend 项目 `uv-consume ... run --no-sync python -`，stdin 为核过 SHA 的程序。AST 仅在节点上运行；程序不依赖 `__file__`。`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，隔离 ambient uv/index/proxy；`PYTHONDONTWRITEBYTECODE=1` 防止 import 写源 WT。初始化 host native pool N1 一次，不建立 operation context；这符合 diagnostic `open_records_closure/read_records_artifact` 的实际 owner，Arrow stream 在 finally 关闭。

## 修订消费语义和 owning 接口

ET1-PF3-1 在本稿静态关闭：不按 RISK_REPORT kind 全局计数选择主报告。程序从 exact pair Surface 的 typed root/table refs 解析实际对象；root report ref 为 None 时记录实际不可观察字段，不把旧 oracle 报告填进 actual。`verify_bundle_tar` 使用当前 transport owner 逐个验证普通成员、raw SHA、最终 ref 闭合、records logical digest；actual Sidecar/metrics/tar 内容再次互核。`read_bundle_transport_metadata` 的当前返回接口、BundlePair 的 `risk_evaluation_digest`、实际 Surface/row stats 字段和 annotation validator 签名均已逐项读 owner，不套用 HTTP pair 的 `risk_digest` 字段名。

补核保持以下业务约束：

- 从 Surface 非空 records closure ref 读取实际 records facade，全部族 count/content digest 与固定 OLD `d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a` 相等；完整12条、六个 unsigned-gid 手帧身份/位置/值断言不变。
- 全125个唯一 Surface table 与两个 exact catalog 相符，250 before/current snapshot bindings；每表实际 Parquet count 与对应 catalog 相等。schema 通过真实 canonical descriptor owner→Arrow field/完整 encoding metadata 比对，包含 SET 映射；PK 只保存 catalog authority，不虚构 Parquet PK。
- Surface 各表 snapshot ref 与对应 side/table binding 一致，row stats 与实际 count 相等；保存所有表逻辑内容摘要与独立代表值。
- 对所有实际风险表的 level/reason/count/source status 及 overall 可观察投影严格比旧 oracle；所有未标注表要求无新增风险/annotation ref。完整 annotation 文档（全部编号/target/rule/reason/evidence/diagnostics）与旧 oracle 原件相等，raw content digest 相等；调用实际 `validate_risk_annotation_documents` 核 canonical bytes/manifest/count/content 绑定，全部 annotation/manifest 有 owning 表且无漏核对象。
- 若实际主物理报告存在则核其业务字段及 evaluation digest；缺省的 report-only contract version/根与表 diagnostics 明确列为 unobserved，不能声称完整当前物理 RiskReport 已比对。现 Surface 的非空 projection/辅助 ref 仍由 transport owner 验闭合；当前 actual 没有该额外物理报告。

程序只读固定旧 oracle SHA/source/inputs、旧完整 composite7字段与独立两个 XML 摘要，未使用当前 History 生成 expected。完整 cold 风险/records 补核并非删除风险断言以放行。

## 占用、失败和后续限制

外层连接04后双重现场 idle 检查、原子本人 marker，核 running Docker 查询的真实退出再判空，无服务 start；原停止态容器/卷不受该检查影响。remote finally 保原 numeric command/tee/entry、起止 exact HEAD/clean；确认无自身程序/uv/编译/Dolt/运行容器/8000 后仅删本人 marker。local 失败复制及 fallback release 也核本人身份与 idle；非本人/已释放 marker不触碰。原 source06 authority 环境与 marker完全不参与。

结果/日志新目录递归 SHA，复制后全 manifest 验证；原脚本失败不会因 copy/release0 改记成功。实际补核若失败先停、保原；不在本稿内重试、清缓存、构建或请求业务。

本稿不恢复 cold 日志窗口、不补造 cold cgroup peak、不执行 warm。历史日志补证与原合法栈/健康缓存的最小 warm 续验仍须另固定稿审核。当前只是已下载原件的只读后处理，按现 DC68 不增加实际修复轮计数；pf3 原失败与此前所有实际轮次事实保持。

产品与容器边界无改动，本稿不触发重建；最后合格容器门禁仍是 V2 source06 全六包同次 Compose。COLD_RECHECK_SCRIPT_GO 不是该 supplemental 实际0、t1完成或最终 H/EXIT 的替代。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-cold-recheck-evidence.md`；SHA256：`1e4554d1751954d2680b9d3a7d01e7e8c02196e80ca90bfc5fa31bdbf61ebd80`。

---

# S5 E 保存 cold 原件只读补核实际证据审核

结论：**COLD_RECHECK_EVIDENCE_GO**。已审核固定程序在04对原 pf3 cold tar 的一次只读补核 actual0。ET1-PF3-1 的修订 consumer 现已实际核到正确的 Surface 引用图、完整 records、全部表及风险可观察内容。原 pf3 入口仍为1；本结论不表示暖请求或完整 t1 已通过，不授 warm、整旅程或 H/EXIT 执行许可。

独审只读本地复制原件、用标准库复算摘要/JSON及六个独立手帧身份；未访问节点、未执行产品程序或测试。固定产品为 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。固定 Python SHA=`31af7983e1915cd3a51dc0b80ce32ebffea6dc8f0469ec7ce14e1af1513346da`，shell SHA=`e724460e018f36b15bda1e5dfe0c959a50bc9977f478a0ec7bb0e9624e4a59d5`，均与原 SCRIPT_GO 对象一致。

## 原件、身份与退出

本地根：`/home/dev/gdds-s5-logs/execution/e-t1-cold-recheck/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-31af7983e191-cold-recheck-r1/`。本地137项与远端复制127项 SHA 清单分别逐件实算，全部一致，检查退出0。关键摘要如下：

| 原件 | 实算 SHA256 |
| --- | --- |
| 本地 `SHA256SUMS` | `108486a74bbb3617aca3bbc33c914492bcc372580fdae81f7e18a7dc3dfb4052` |
| `remote-evidence/SHA256SUMS` | `2982ef55c13c87c646027b44ad1e9c7c2b868c8185ced6540adeac8cedb926c3` |
| `remote-evidence/session.log` | `820ec4781147f301c187d5a397e81bac80ce6ed2b0f55e67f7595cdd3a5c2e61` |
| `remote-evidence/recheck/result.json` | `c3b14d934311be8fc9c5c7230e03b35ee82aae5913a2017c0853e6bbba3b9c8e` |
| `remote-evidence/recheck/cold/actual-semantic.json` | `53ebb061e66c46bf5252339f4d18b584c84171ab8ddf6f863c4069b95ebf4615` |

04 `gw-dms-test-04.lan` admission 原子取得本人 marker；remote session 2026-11-09 13:41:24Z–13:41:27Z。四步 source-evidence-integrity、native-build-input、program-syntax、cold-recheck 的 command/tee 均0；逐步及起止 HEAD 均 exact V2，clean_end=yes。native 原日志 expected/installed 均 c0213e18a9645c5cfbd39f310f532273a03a10cb。原615件清单在节点完整校验，程序结果保存核过的完整 inventory，补核结束再次核验原件未变。

remote entry0、outer tee0、copy0、复制后 SHA check0、local entry0；remote marker remove/rmdir0、released=yes，local guarded release 识别已释放后正常 skip0。原 WT/venv/私有 secrets/停止态容器/卷及失败证据保持；本次没有 HTTP、服务 start、业务操作、build、sync 或 cache reset。

## 实际补核结果

补核来源是原 tar SHA=`93da19c776c8840338ab2f89b8450a4c7572bda742d55ea06fd52fc066b769b7`，2,153,472 bytes，116普通成员、114closure、1 records closure、12条完整逻辑记录，4个 reference metadata。actual manifest/成员 sidecar/ETag/完整 transfer metrics 与原件一致；没有重新下载。

actual pair=`op-b8408f429d026545fdd3d8fe-p0`。结果中的三摘要与原 cold tar 及前份诊断一致：

| 摘要 | 实际值 |
| --- | --- |
| comparison | `sha256:cc51a9ff6e91d95bb8ad4f00135f031559c8938bd03b22466ce5493614d4686d` |
| risk evaluation | `sha256:cdefa93c80d7a7b09be713143cae0d8d0d3f5815f78b205f807cb5d6f399e8e3` |
| surface | `sha256:81eeff34068447eefddf20843e35bc3e1b20f9e5d91dec423f12498a056105ff` |

`actual-semantic.json` 的规范内容 SHA（不含文件终止换行）实算为 `7ef700c6c1022833320578df4b1f44b1785779a55226eee690e8a923a30dd66e`，与结果 `semantic_sha256` 一致。不是将原 bundle SHA 当成语义摘要。

全部125张表、250 before/current bindings、完整 schema/encoding metadata、exact catalog PK authority、逐表 count、Surface row stats/ref 绑定及逻辑内容摘要已实际检查并保存。独审再次对所有输出 count 与原 fixed catalog 比较：before125表/3733行，current125表/3731行，逐表完全相等。PK 仍仅作为 exact catalog authority 记录，不声称 Parquet 提供 PK 字段。

实际诊断 records facade 读到 ORDERED6 与 STANDARD6，全部族/count/content digest 与固定旧 oracle `d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a` 相等：

- ORDERED：`sha256:e79378d966f39a1296a0e7452333a43d0ef547f3a41e1989314b77b44f2a4e5b`。
- STANDARD：`sha256:0d3af5be7293af911e9a8e0e25ef0fda3a056648be3d57e5bf4997925a0b18c0`。

六个独立 unsigned gid 固定8字节大端手帧身份、增删种类、完整代表名称与位置在节点程序中通过；独审又用标准库从保存的 decoded 记录独立复算六身份/名称/位置，均相等。不是新 codec 自身往返生成 expected。

实际 overall MEDIUM_LOW、1个风险表、6条 annotation，reason ROW_ADDED/ROW_DELETED；只有 SYX 表 MODIFIED3add/3delete。全部表的风险可观察投影严格比旧 oracle，其他表无意外风险/annotation。完整六条 annotation（编号、target、identity、rule/reason、evidence、diagnostics）与旧 oracle 原文结构相等，content digest=`sha256:f4105ca4ae8af4c70d109fec3bb33542434f33014a11a2cd68ec5cdbbef617e4`；实际 canonical annotation manifest/count/content 绑定由 owner validator 检查并保存。独审再次比完整 annotation document/content digest/overall 与旧 oracle，均相等。

实际物理 master risk report=None，按 Surface 引用图正常消费；没有从 expected 拼出不存在的报告。结果明确 unobserved：`risk_report_contract_version`、`RiskReport.diagnostics`、`RiskTableResult.diagnostics`。这些完整物理报告专属字段不在当前 tar 中可观察；不能将本补核写为“当前完整物理 RiskReport 所有字段均导出且比对”。

## 继续保留的限制

原 pf3 完整 driver/外层仍保持 command1/tee0/entry1，本次只是其保存 cold 内容的独立后处理0，未改原失败或补造原未写出的实时结果。ET1-PF3-1 的 consumer 修正已获得保存 cold 原件的实际验证；整段 t1 尚缺真正新 operation 的 warm 及冷暖对账。

本次没有恢复 cold Docker 历史差量/实际 RS `/rows` 正校准；这仍待已说明时间边界的只读原日志补证。cold cgroup peak继续 **UNKNOWN**，不可用本次后处理或前置 cgroup 值替代；物理 report-only 未观察字段继续保留。M24/HWM/硬限额的原证据与后续 warm 实际峰值须分列。

后续仍限原合法两个 Submission、原 WT/native/镜像/DB/healthy cache 经固定稿现场核真后的一次 new-key/new-operation warm 与第4个完整 tar，不重复 cold/前置、不扩真实矩阵。该固定稿及身份恢复前提必须另由本原审审核；当前 COLD_RECHECK_EVIDENCE_GO 没有 warm 执行许可。

产品源码与容器边界无改动，无新重建；source06 合格 authority 六包/同次 Compose 及其冻结 WT/env/images 仍保持。没有 E 最终证据、H 绑定、release 或 EXIT 预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-warm-continuation-r1-review.md`；SHA256：`43ebbfa11f2b64845cacad211ebce05a8590e6a3abc9118eba212ced76d90456`。

---

# S5 E 原栈一次 warm 续验稿 R1 联合独审

结论：**WARM_CONTINUATION_SCRIPT_GO**。许可唯一测试者在04 fresh 原子取得本人占用、全部固定身份/状态前提实际满足后，执行本固定两稿一次：只读恢复已保存 cold 历史日志，重启原本人三个停止态容器，对原两个合法 Submission 发一个 new-key/new-operation warm，取得第4个完整 tar，随后关闭原栈。没有第四整旅程、重复前置/cold、build/up/sync/新栈或原 source06 操作许可。当前未运行该稿，未预签 warm/t1/E 实测通过或 H/EXIT。

| 固定对象 | 实算 SHA256 |
| --- | --- |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-resume-r1.py` | `5d1e8d7e37b2b7a23964189c59c2fa9b945cf5f72d63339e65dea42452e40513` |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation-r1.sh` | `940d0bff838f53e119de6e2895c52c779cf9d8240b330b91b675ee8cac91162f` |

本原审只读本地固定源码/脚本/已复制原件，未访问测试节点，未执行脚本、AST/产品 decoder/测试或构建。固定产品 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`；clean detached 审核 WT 仍为 exact V2。cold actual0 已独审，报告 `e-t1-cold-recheck-evidence.md` SHA=`1e4554d1751954d2680b9d3a7d01e7e8c02196e80ca90bfc5fa31bdbf61ebd80`。

## 1. 来源、实际入口与原资源准入

wrapper pin 程序完整 SHA，复制后复核；04原 pf3 WT/root 固定，查起止 exact HEAD/vnext/Rust、clean、legacy、既存 native build input。不 checkout、改锁、同步环境、重建/重 tag 镜像；uv 消费走当前 backend 的受控 `--no-sync python -`，stdin 是核过完整 SHA 的唯一程序。AST 仅由节点执行。offline、selector/root PATH、无 ambient uv project/venv/proxy、`PYTHONDONTWRITEBYTECODE=1` 保留。host 没有 Dolt/version/config consumer。

两组来源分别固定全 manifest：原 pf3 615项 `ef8348737b4658d3f098ae1fc9e4845c8a4a83f7fdb2644375aed322a2db1e54`；cold 补核127项 `2982ef55c13c87c646027b44ad1e9c7c2b868c8185ced6540adeac8cedb926c3`。cold result `c3b14d934311be8fc9c5c7230e03b35ee82aae5913a2017c0853e6bbba3b9c8e`、semantic 文件 `53ebb061e66c46bf5252339f4d18b584c84171ab8ddf6f863c4069b95ebf4615` 及其内容摘要均再次核验。完整 fixed OLD oracle d990、source/inputs、原失败1/stop0、三次既存 tar、两个 Submission exact commit 绑定均保留；本次新结果目录与原 evidence/WT/private secrets 分离。补核结束再核原两份来源未变。

程序严格限定 `gw-dms-test-04` 与原 pf3 WT。开始任何服务前，对原三容器逐个核原 ID/name、stopped/exited且无 OOM、原本机 image ID/完整 labels、Compose project/service/working_dir/config_files。image/current tag ID 须与原实际 runtime 相同；全部原挂载要求 exact destination/原 volume 名/RW 或 secret 私有路径/只读属性，private 文件保留且非 symlink。worker Env 核 N1/M24/envelope32GiB/reserve8GiB，HostConfig 实际 Memory=32GiB。只将无凭据的身份/私有路径相符事实写结果。

全部目标核过后才登记 owned，并在任何 docker start 前进入 finally 关闭范围。节点占用与原 Compose gate lock 同时保留。只 `docker start` 原 RS、backend、worker 的核过 ID，不执行 Compose up/build/recreate；RS/backend readiness 与 worker 本次新增 ready 日志核真，不把旧 ready 日志当成新进程已就绪。`compose_image_ids` 与 `capture_running_container_provenance` 必须仍等于原三服务/原 ID，无额外服务。

## 2. 历史冷窗口与只读健康检查

在启动服务前，从原 worker/RS exact container 读取 `docker logs --timestamps` 全日志及固定历史窗口 **2026-11-09T13:20:19.019Z–13:21:07Z**。去 timestamp 后完整日志须以前次保存 final stdout/stderr 为逐字前缀，窗口 worker operation 集合须只有原 cold `op-b8408f429d026545fdd3d8fe`，唯一 pair metric 须为其 `-p0`。正 cold comparison 与实际 RS `/rows` 请求>0 是强校准，不用 cache/native 计数代替 HTTP 证据；admission INFO 不可观察时为 null。保存全 timestamp/选窗原件并明确这是历史重建，不冒充原未落盘的 before/after 差量。metadata/demands 所有原记录与总和分列；cold peak 固定 null/UNKNOWN，不补造。

RS/backend启动后、worker启动前，固定健康程序在原 backend 容器执行。已逐项核当前 owning 接口：

- `verify_control_db_file` 是只读当前单一基线 schema 校验；主连接 `mode=ro`、`query_only=ON`、事务最终 ROLLBACK/close。核全部 operation 已 final terminal且原 cold SUCCEEDED，两个且仅两个 Submission 的 repo/commit 与原件一致，原初始/Archive baseline 两节点、scope/parent/source 与 BaselineHead exact version1不变，原唯一 History acceptance/全新 key未存在。
- SQL 字段对当前 schema 核实，不用旧表假定。`_entry_from_row` 当前7字段布局、ComputationCacheKey/Kind/DigestRef、`decode_cache_manifest` actual signature 与 namespace/envelope/member closure 检查相符。缓存及 cold uses 均要求未过期/索引仍匹配；所有 manifest/member 原 bytes与sidecar由 `LocalArtifactStore.read_exact` 完整读完验 size/SHA。无 lookup_and_pin、touch、prune、discard、回填或 cache重置。
- canonical table/index 的 exact两commit绑定、export entries 与两份权威 Submission canonical manifest均只读检查现存全部 bytes。`read_session` 借用既存 root inode共享锁，不建立 durable pin文件；ArtifactStore root存在后构造不创建新的资源。

健康检查不是模拟 warm，也不调用 native比较/records恢复/RS rows。原 cold status 一次必要 GET 将 original SUCCEEDED operation/两个合法 ref/commit 与保存 tar 的三摘要及bundle摘要绑定；不下载 cold bundle。然后仅启动原 worker。所有身份/缓存/来源检查异常即停，不冷启动或重做业务作为 fallback。

## 3. 唯一新 operation 与完整语义验证

new key 固定为原 Compose namespace 加 `-history-warm-resume-r1`，在 DB 中预检未受理；唯一 `_history_compare` POST 使用原两个 Submission exact commits。返回 operation 必须与 cold 不同，并与唯一 new warm tar URL一致；consumer最多调用一次，得到新目录 bundle-03 的第4个完整 tar。HTTP Content-Length/media/ETag、116/closure原件规则、所有 ordinary member/raw SHA/ref图和 logical records由实际 owner 校验，不用摘要请求代替完整下载。

`SavedHistoryConsumer`、schema/records/risk/ref消费主体与已实际0 cold 程序逐字相同。保持全部125表/250 snapshot bindings、完整 schema/encoding、逐表 count/内容摘要、OLD所有 records family count/content digest、完整12条与六手帧身份/位置/值、六完整 annotation/manifest及可观察 MEDIUM_LOW 风险投影。物理 report optional，不以 old expected 填 actual；report-only未观察字段继续列清。

新增 HTTP/bundle字段已对实际 owner核实：HTTP pair 使用 `risk_digest`，BundlePair/Surface为 `risk_evaluation_digest`；before/current ref、commit、input index/role、pair_id、bundle digest与实际 tar互核。冷暖 comparison/risk/surface 三摘要必须直接相等；整体 bundle 含运行绑定，不要求其两个摘要相等。

完整 `pair_digests/records/snapshots/risk_observable/physical_master_risk_report/unobserved` 均与已核 cold semantic 相等。Surface只允许 owning pair_pipeline 从新 pair产生的 `surface_id` 与 `view.view_id` 两个外层 ID 重绑定，其他字段完整相等：不 mask content ref/ID、digest、target、annotation编号、原因/值/evidence/diagnostics。已读 bundle `_build_final_ref/_bundle_artifact_id`：嵌入成员 artifact ID由kind/media/raw bytes/size确定，不由pair路径决定；因此没有随意把内容 ID 扩大为可变实例字段。

warm 原 worker/RS before/after 日志须 append-only，exact operation唯一；native comparison0、ordered single-side0、persistent restore>0，实际 RS `/rows`0，若冷 admission可观察则暖也0。metadata/demands、records validation、cache restore/rebind与其他 pair metrics 保存独立值；charged HWM必须在M24内。暖新 worker初始与最终实际 cgroup memory.max/peak/current/events均保存，要求32GiB且OOM0；明确峰值范围包含本次 worker启动到warm完整 tar/validation，与 pair预约 HWM不同，也不冒作cold峰值。

## 4. 收尾、镜像取证与现行规则

finally只收集并stop已核的原三个ID，逐个记录stop实际退出与post-stop inspect，保原卷/private输入/WT/native/旧原件。一个服务stop失败不会跳过后续两个stop；未停止/inspect失败会使入口非0，remote wrapper保占用。wrapper确认全机idle及本人marker后仅释放本人占用；local fallback同样受owner/idle约束，非本人/已释放正常skip，不覆盖原numeric failure。新结果/日志递归SHA、复制后全清单核查。

仅 warm body exit0+PASS+stop0 后，wrapper保存实际服务及两个base镜像。实际 runtime container image ID与所选tag再核，`docker save`读取真实 config bytes/hash、全部 DiffID并与本机 inspect层比较，只记录filtered build/source labels，无 build/retag。此补齐 pf3原success-only镜像取证未到达的缺口；真正 source/preloaded provenance及所有config值仍由事后原件核收，不预签实测身份相符。

当前ET1-PF3-1为已确认工具consumer具体故障，cold保存原件的修订已实际0；本稿是其原授权范围剩余一次warm步骤，不是新整旅程。原 pf0/pf1/pf2/pf3退出与累计profile事实全部保留，不按更换目录/脚本清零同根计数；当前固定稿也不含无修改重试。任何本次实际失败先停、保原日志/exit/SHA/状态，按具体根因及现DC68判断后继，不自动再跑。

产品/source未改、实际容器仅原ID恢复，不触发新重建；最后合格生产容器门禁仍为 V2 source06 全六包同次 Compose，source06冻结资源无触碰。执行者仅获本报告固定两稿的一次 WARM_CONTINUATION_SCRIPT_GO；实际成功、完整t1/E证据、H绑定/release/EXIT继续等待独立核收。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-warm-r1-failure.md`；SHA256：`55dfc6a99f6553f75cbd059c62108c459981ae9d0de4655e7e38e2eedf484330`。

---

# S5 E warm续验 R1 历史日志后处理失败独审

结论：**WARM_R1_FAILURE_EVIDENCE_ACCEPTED；EWARM-1 为工具日志解析错误，需固定修订后复审，当前没有重跑许可。** 本次未启动任何原容器、未进行 DB/cache/HTTP 或新业务 operation；原 cold/t1来源与source06 authority不变。

原件根：`/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-5d1e8d7e37b2-warm-continuation-r1/`。固定程序/外层仍为前次 SCRIPT_GO 的 Python SHA=`5d1e8d7e37b2b7a23964189c59c2fa9b945cf5f72d63339e65dea42452e40513`、shell SHA=`940d0bff838f53e119de6e2895c52c779cf9d8240b330b91b675ee8cac91162f`。独审仅本地读取原件/固定源码与标准库数据核查，无节点访问或产品程序运行。

## 原数值与收尾

33项本地和23项复制远端 manifest逐项实算全部相符，检查退出0：

| 原件 | 实算 SHA256 |
| --- | --- |
| 本地 `SHA256SUMS` | `6af2d9f63471bf80a364114d3fe4971f498d536ea5bc98f225c476681c33eed9` |
| `remote-evidence/SHA256SUMS` | `d7f43a3b00ebf0a185a7a33e167569ebaff01e31dd697e41f4db7652fa491bc2` |
| `remote-evidence/session.log` | `535913ac5590026e75963d5edeef03fe5ac7096798244d03c8e694aa93c08985` |
| `remote-evidence/warm-continuation.log` | `08798b95e07fea3afca98a780c2ff394eee35646b63b7fe456e1624e83ef8edb` |
| `remote-evidence/warm/result.json` | `a35a13ee0d603418ea31aaed6815076ec450b6607df2f7d55cc3bd1da18ef361` |

04 gw-dms-test-04.lan remote session为2026-11-09 13:59:34Z–13:59:37Z，起止/逐步exact V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`且clean。前四步原615项完整性、cold补核127项完整性、native build input、program AST的command/tee均0；`warm-continuation`为 **command1/tee0**，remote/local原入口1保留。finally对原三个已核ID stop及post-stop inspect均0，marker remove/rmdir0且释放，copy/hash/guarded release0。

Traceback定位程序 `reconstruct_cold_window` 第520行“fixed cold timestamp window has only exact cold operation”。该调用在 `initialize_compute_kernel`、三个docker start、健康SQL、cold status GET及唯一newwarm之前；保存结果没有warm/initial cgroup/prewarm health/cold observation完成项。历史日志读取和finally对已停止本人ID的关闭没有新业务/缓存副作用；没有把步骤入口1转成成功或声称warm执行过。

## EWARM-1 的实际根因

窗口原件 `remote-evidence/warm/cold-log-reconstruction/worker-{stdout,stderr}.cold-window-timestamps.log` 中：

- scoped `op-b8408f429d026545fdd3d8fe`：claim_succeeded3、heartbeat_succeeded4；无其他真实operation ID。
- `operation_id=-`：worker_ready1（13:20:19.594916927Z）、drain_started1（13:21:04.467748089Z）、worker_exited1（13:21:04.467768839Z）。

当前 owning `operations/worker.py` 的 `WorkerEvent.operation_id` 明确是 `str | None = None`；`bootstrap/operation_worker.py:123` 的 observer输出 `event.operation_id or '-'`。`worker_runtime.py:580` clean drain/exited和drain_started事件没有业务operation绑定，ready同属worker生命周期。故 `'-'` 是无作用域的日志占位符，不是第二个operation ID。

R1 regex将所有匹配到的token直接放同一ID集合，再要求集合恰为cold ID，从而把合法lifecycle占位符判成串入另一业务操作。同样的解析表达式在warm差量段也存在，若只修cold会留下同一工具假设。

最小修订是两处共用一个只读parser：保留原raw日志，明确区分scoped真实IDs与无scope sentinel事件，记录后者code/count；scoped真实ID集合仍严格等于唯一expected ID，任何其他真实ID继续拒绝，不删除业务隔离断言、不将所有不匹配ID静默过滤。当前source/pair metrics、正cold RS rows、完整语义/独立expected、预算和资源断言均无需放宽。

## 后继范围

这是历史只读后处理/预检 guard 的首次实际失败，发生在本次被测对象运行前；现DC68既有只读后处理不计实际修复轮的澄清适用。原pf0/pf1/pf2/pf3及本次r1 numeric failure全部保留，不因新文件名/目录改写或清零历史事实；不新增无修改自动重试。

后继固定r2需本原审联合核程序及外层source/程序SHA/新输出路径绑定后，才能重新从本受影响流程开头执行一次。仍仅原04/原WT-native/原三个ID及同一合法节点的一次newwarm，不重做cold/前置/整旅程。若新的真实ID或任何身份/缓存/资源状态不符仍停，不能借sentinel修订放行。

本次产品无改动、没有新镜像或容器启动，重建不适用；最后合格容器门禁仍为V2 source06全六包同次Compose，完全未触及其冻结资源。cold峰值UNKNOWN与物理report-only未观察限制保持，无t1/E/H/EXIT证据预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-warm-continuation-r2-review.md`；SHA256：`6c621aed047a9ad2f2fe086ac3685cedb544e02c5da0e4e2d5e23d3009102f69`。

---

# S5 E 原栈 warm续验 R2 连续联合复审

结论：**WARM_CONTINUATION_R2_SCRIPT_GO**。EWARM-1静态关闭；唯一测试者可在04重新fresh占用、所有原身份/缓存/状态前提实际满足后，以本固定两稿从受影响流程开头执行一次。仍只允许原栈一个new-key/new-operation warm及第4个完整tar，无第四整旅程。R1失败及原pf3失败保持入口1；没有warm实际通过、t1/E/H/EXIT预签。

| 固定对象 | 实算 SHA256 |
| --- | --- |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-resume-r2.py` | `a83cf4eb932fd939936a0d5ce1cf7bf4b604adf94b7dde258e137a5e6acde8ac` |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation-r2.sh` | `e7ad8dc6ee3353be52244ccaa2b826003e359caeb7bc353440b0efc95d1bb73d` |

本原审仅本地只读固定源码、实际日志和逐字diff，未访问节点、执行脚本/AST/产品检查。本报告承接完整R1工具审核 `e-t1-warm-continuation-r1-review.md` SHA=`43ebbfa11f2b64845cacad211ebce05a8590e6a3abc9118eba212ced76d90456`，及原始失败诊断 `e-t1-warm-r1-failure.md` SHA=`55dfc6a99f6553f75cbd059c62108c459981ae9d0de4655e7e38e2eedf484330`。产品V2/source06冻结来源无改。

## EWARM-1 修订

当前 reporter `bootstrap/operation_worker.py::_observe_event` 固定输出code/operation_id/step_id/worker_id/attempt/error_category六字段；optional operation_id=None渲染为`-`。R1原历史窗实际只有cold真实ID（claim3/heartbeat4），另worker_ready/drain_started/worker_exited各1为无scope sentinel。本次共用 `worker_event_scope` 按该真实六字段解析所有 worker event行，格式不符继续拒绝；仅`operation_id == '-'`归入独立的unscoped事件列表，完整保留其code与其余五字段和总数。

所有其他token仍为scoped真实ID，集合必须严格等于 `{expected_operation}`；空集合/任意其他真实ID均拒绝。未把未知ID先过滤成只剩expected，也未删除隔离断言。cold历史窗与warm实时差量两处均改为该同一helper，并将实际scope结果写入各自结果。原raw完整日志/窗口/差量照常保存。六字段regex与实际原件/owner一致，不改变产品logger。

逐字diff确认：Python其余变化仅头部示例文件名R2、保存scope字段；pool初始化、原资源核查、历史窗与前缀/metric/RS rows校准、只读DB/cache健康、原cold status绑定、完整cold consumer、唯一newwarm、第4tar及冷暖/OLD所有断言、预算/cgroup、finally全stop均未改。WARM_KEY仍是原未被POST的固定新key，R1在historical guard处失败，未受理该key；执行时仍由原read-only DB guard核它不存在，不借新key掩盖已跑业务。

## 外层与原失败保留

wrapper逐字diff仅新程序SHA、R2 KEY/SESSION及依赖该值派生的新输出目录、local/remote session两处R1失败锚点。SOURCE原pf3、private secrets、原三个容器/镜像/tag、原04/WT-native、cold0两组完整manifest与实际结果均未改；所有4flags/11个remote参数映射、offline/project stdin/native只读核、占用/释放/副本SHA及成功镜像true config/all DiffID步骤原样保留。

两处R1锚点实算正确：原入口1、本地manifest=`6af2d9f63471bf80a364114d3fe4971f498d536ea5bc98f225c476681c33eed9`、远端manifest=`d7f43a3b00ebf0a185a7a33e167569ebaff01e31dd697e41f4db7652fa491bc2`，明确service start/HTTP/newoperation均no。独立输出目录不覆盖原失败，不修改原615项或cold补核127项来源。

本修订对应只读历史日志后处理/预检错误，现DC68既有不计实际修复轮的澄清适用；原全部profile/失败数值继续保留，不因R2文件名或新输出目录重计既有同根。本许可不是无修改重试：只允许上述固定修订一次，任何真实ID/来源/镜像/缓存/合法节点状态不符继续首失败停、保原并收尾，不回退新cold/前置或完整旅程。

产品无变、新栈/构建/同步/retag均无，重建不触发；仅恢复原已核三个ID，不操作source06 authority及其carried/H绑定资源。cold cgroup peak UNKNOWN与report-only未观察限制保留；实际warm及之后E/H/release/EXIT各证据仍待原审核收。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-warm-r2-failure.md`；SHA256：`26740afb0430d07b5e4f75578fb3e894122ed8ac9584d670f7068ce72b375729`。

---

# S5 E warm续验 R2 源/最终 Surface 摘要绑定诊断

结论：**WARM_R2_FAILURE_EVIDENCE_ACCEPTED；EWARM-2 为外置工具把不同层级的 Surface 摘要强行等同。当前需固定窄修、连续复审，没有重跑许可。** 已有原件未显示 comparison/risk/records/bundle/合法节点内容不一致，不据本断言认定产品漏闭包或摘要损坏。当前 actual warm业务仍未执行。

先前R1/R2工具审核把HTTP pair与最终tar Surface摘要直接相等作为接口保证，该判断过强，本报告更正这一特定保证；旧报告/脚本/失败字节保持，不改为成功。其余完整records/risk/table/身份/资源约束继续保持，不以新actual反填expected或mask应稳定摘要。

本原审仅本地读取已复制原件、固定Git源码及owning Contract，标准库核SHA/JSON；无节点访问、产品decoder/测试/语法或构建执行。产品仍为V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。

## 1. 原始失败与实际触及范围

原件根：`/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-a83cf4eb932f-warm-continuation-r2/`。固定程序SHA=`a83cf4eb932fd939936a0d5ce1cf7bf4b604adf94b7dde258e137a5e6acde8ac`，wrapper SHA=`e7ad8dc6ee3353be52244ccaa2b826003e359caeb7bc353440b0efc95d1bb73d`。

36项本地与26项复制远端清单逐项独立复算全部相符，检查退出0：

| 原件 | 实算 SHA256 |
| --- | --- |
| 本地 `SHA256SUMS` | `b3fcdca8dccfd39cfbebea4ae3caa64c87480ed90fd0404ee646b959a40b86a8` |
| `remote-evidence/SHA256SUMS` | `6d9514c9df96b7f8d2a1c16b4d902a644ca61c758bd7dc5033001b724d9d1420` |
| `remote-evidence/warm-continuation.log` | `9df0fbe90055b7733bed731282790bb5d4744d94ae42967cb34985b6e0ca18ef` |
| `remote-evidence/warm/result.json` | `9e23df427359330e7e809a170d1df9dc0edd0819cef27747a499e7776ad5d1d5` |
| `remote-evidence/warm/original-cold-http-status.json` | `47beb6c6a38a7b992086a239a0ad2d7b5fdc0f19b1f52f2ed1693c9e59376581` |
| `remote-evidence/warm/cold-log-reconstruction/result.json` | `2fb3b5d5f4ab24c50d651236645632090c167b45ca1edf0c31bd51f568268d51` |
| `remote-evidence/warm/pre-warm-db-cache-health.json` | `a78820f6dd065a226202ee3b812c302cebea5dad6b5f3c1a0d35ed7869c86f34` |

04 remote session 2026-11-09 14:06:32Z–14:06:43Z，起止/各步exact V2、clean。前4步来源/cold0完整性、native、AST均command/tee0；warm-continuation为 **command1/tee0**，原入口1保持。三个原ID的stop和post-stop inspect全0，copy/hash/guarded release0、本人marker释放。

完整trace为main第961行调用 `check_http_pair(cold_status["result"], saved_cold_manifest, ...)`，在第766行 `actual HTTP/tar surface_digest binding` 失败。此时历史cold窗口重建已成功，原RS/backend已启动，只读DB/cache健康已完成，并GET了原cold SUCCEEDED状态；**worker尚未start、无newwarm POST、无第4tar、无暖cgroup**。不能沿早期口头误读称为“warm产品调用失败”。

## 2. 实际两个值与未变化的绑定

原cold HTTP pair `op-b8408f429d026545fdd3d8fe-p0`：

- HTTP `surface_digest`：`sha256:2971ba7d71d0605d49c7a81e25e702564b580e9a85e5307d2f8486cc898e2365`。
- 保存tar的BundlePair/实际最终Surface `surface_digest`：`sha256:81eeff34068447eefddf20843e35bc3e1b20f9e5d91dec423f12498a056105ff`。

HTTP的comparison=`sha256:cc51a9ff6e91d95bb8ad4f00135f031559c8938bd03b22466ce5493614d4686d`、risk=`sha256:cdefa93c80d7a7b09be713143cae0d8d0d3f5815f78b205f807cb5d6f399e8e3`、bundle=`sha256:676679300e22ed95dfb781ca3f842e177a2ff04f13f49930a2af5b733d83adf1`，均与原tar/已核cold相同。operation/pair/两个ref/commit顺序/12条count亦相同。原cold complete tar及125表250bindings、完整12 records和6风险annotations已独立补核通过，本次没有新cold tar下载。

## 3. Owning链路与摘要层级

实际调用链与当前Contract分层如下：

1. `application/pair_pipeline.py::_run_comparison_risk_surface` 调用 `assemble_surface`，返回当时源Surface的 `surface.surface_digest`；`run_history_pair_pipeline` 将它写入 `HistoryPairPipelineResult.surface_digest`。
2. `application/history/compare_jobs.py::_assemble_comparison` 先取得pair_state及source Surface，将它交给 `assemble_bundle`。其后持久化assemble_state的HTTP pairs仍取 **`pair_state.surface_digest`**（第994行），不是从最终 `bundle_result.bundle.pairs` 反取。HTTP `history_compare.py::_load_success_result` 从这个checkpoint assemble_state原样映射该字段。当前源码明确HTTP字段属于组装前源Surface观察值。
3. Bundle assembler `_plan_artifacts` 对声明closure的JSON嵌入引用递归规划和确定性rewrite，按最终refs重新序列化这些JSON。除opaque ref字符串外，包含嵌入refs的manifest原始bytes也可改变，因此其新的rawSHA/size会成为上层ref的integrity。
4. Bundle `_rewrite_pairs` 在替换Surface引用后明确执行 `compute_surface_digest(surface)`，将这个 **最终Surface摘要** 写入最终BundlePair和最终Surface原bytes。最终BundlePair↔其Surface直接相等仍是必须约束。

Comparison Surface Contract `comparison-surface.md` §surface_digest输入/当前S4 realization明确包含被引用artifact manifest/content digest及ref `size_bytes/raw_sha256` integrity；它排除opaque ref身份和外层运行ID，不是排除所有引用内容变化。`rewrite_surface_refs`/既有ID-only测试的digest不变，适用于相同integrity的opaque身份替换；不能推广为嵌套JSON已经改写bytes时源/最终摘要仍必相等。既有nested-json单测使用diagnostics ref，其被排除在Surface摘要外，也不证明records closure等integrity变化不影响摘要。

Comparison Bundle Contract当前v3明确嵌套ArtifactRef确定性rewrite、最终closure只保存final refs、raw content digest/size参与integrity，READY前完整回读。BE-d完整下载边界强制的是已授权History checkpoint **expected bundle_digest == prepared final bundle_digest**，并非要求HTTP source Surface digest与最终Surface digest相等。History HTTP owning设计§7.1只列该观察字段，没有把它重新定义成final BundlePair摘要；当前实现的来源如上。没有确认的consumer需要此新增cross-layer等式。

所以本次外置工具在一个条件中混用了两个真实、可不同的摘要层级。不能把最终值改为HTTP源值、改产品/golden去追随该工具断言，也不能简单把整个Surface校验删掉。若后续额外读取原assemble checkpoint，可只读核其source digest与HTTP映射及同一own bundleDigest；本次未访问该原checkpoint，不冒称取得了其独立实际副本，也没有重跑比较来生成source expected。

## 4. 已获得的最小冷日志/健康证据

R2已实际关闭EWARM-1解析问题：同exact窗口中真实operation ID仅b840…、scoped事件7，无scope sentinel事件3独立保存。原final日志前缀逐字绑定通过；实际cold kernel1、ordered single-side8、persistent restore0、RS rows129/catalog133；charged HWM=25,438,132,736≤M24。metadata/demands完整分列。admission diagnostics未观察到，保持null；cold cgroup peak依然UNKNOWN，不变造历史值。

只读健康原件记录当前单一schema、两个Submission exact commits、初始/Archive节点及BaselineHead1、所有operation terminal/原cold SUCCEEDED、原key未受理、10个unexpired computation entries及10 uses、129 canonical cache项、106 snapshot export项与全部实际字节健康。未执行lookup/pin/touch/reset/比较。必要cold status GET仍SUCCEEDED。服务恢复和正常关闭不改变原cold业务事实；新的warm key仍未POST。

## 5. 后继最小修订与限制

后继应保留并分别验证：

- HTTP source Surface：原cold HTTP与新warm HTTP的同层source摘要相等；可与其各自checkpoint源观察绑定。不得用最终tar摘要替代source字段。
- 最终BundlePair/实际Surface：各自最终摘要与其实际内容owner验证、cold最终↔warm最终摘要相等；完整Surface语义除两个owner外层ID外相等仍保留。
- comparison/risk/bundleDigest、pair/node/input顺序/12count原有跨HTTP/tar绑定不放宽；完整records/content/annotations/编号/target/风险可观察投影、125表250bindings/schema/count/逻辑值和独立OLD/手算断言不变。

这是不同于EWARM-1 sentinel的明确工具层级假设，尚未对它进行修后实际复验；按现DC68具体根因判断，不能仅用文件名R2或累计profile数宣告同根三修失败。原全部失败/计数保留；本次恢复了RS/backend但未发newwarm，下一稿仍须新固定、连续独审、一次受影响最小流程，不自动重试或重复cold/前置/整旅程。原因/副作用/输入身份若另有真实冲突继续停，不能用本诊断掩盖。

产品没有变化，原镜像/原三个ID恢复不触发新构建；source06 authority及其H绑定资源完全未触及。没有warm执行许可或完整t1/E/H/release/EXIT预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-t1-warm-continuation-r3-review.md`；SHA256：`dca8d37ba8ea4259097f8229935d3dae2fe1a6d507330e2360920e6efdbbdb20`。

---

# S5 E 原栈 warm续验 R3 连续联合复审

结论：**WARM_CONTINUATION_R3_SCRIPT_GO**。EWARM-2静态关闭：原cold HTTP源pair与实际持久化assemble checkpoint绑定，源Surface与最终Surface分别作同层冷暖核验；仅撤销无合同保证的跨层Surface等式。唯一测试者可在04 fresh本人占用及原全部前提实际满足后，运行本固定两稿一次最小续验。没有第四整旅程、cold/前置重放、source06操作或最终证据预签。

| 固定审核对象 | 实算 SHA256 |
| --- | --- |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-resume-r3.py` | `e4b4dac49cc1acd6ac20bd3b1f985a74300e02575229ee4910e1327f0198366c` |
| `/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation-r3.sh` | `a1976277b156eb74183cd2dd0b178b6720c084f61b670605ed73a87c45901212` |

本原审仅本地读取固定源码、actual原件及逐字diff，没有节点访问、脚本/AST/产品检查或构建。当前固定产品仍V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。承接完整R1工具审核43ebbfa11f2b64845cacad211ebce05a8590e6a3abc9118eba212ced76d90456、R2连续审核6c621aed047a9ad2f2fe086ac3685cedb544e02c5da0e4e2d5e23d3009102f69，以及R2实际失败诊断26740afb0430d07b5e4f75578fb3e894122ed8ac9584d670f7068ce72b375729。旧报告中过强的source/final直接等式已由后者明确更正，原字节不改。

## 1. 新checkpoint读取接口已逐项核实

新增逻辑仍在原RS/backend启动后的只读HEALTH_SCRIPT中、worker启动之前；原SQLite mode=ro/query_only/事务ROLLBACK、ArtifactStore shared read_session保持。真实当前接口如下：

- `history_compare_step_id(cold_op, HISTORY_COMPARE_STEP_ASSEMBLE)` 通过owner的suffix映射取得原step-2；ASSEMBLE常量实际为`assemble_comparison`，不是假定SQL字段值`ASSEMBLE`。
- 当前schema确有`step_records(step_id,checkpoint_ref,status,operation_id,step_name,...)`。checkpoint_ref保存canonical JSON BLOB，json.loads后可交真实 `artifact_ref_from_dict`；额外要求该step SUCCEEDED、exact cold operation/step name，防误读另一阶段。
- `application.checkpoints.load_checkpoint_envelope(store, checkpoint_ref)` 真实签名和返回`StepCheckpointEnvelope`的operation_id/step_name/job_kind均匹配。`LocalArtifactStore.locate`在解码前校sidecar/ref/size/rawSHA；无operation context时该读取不要求native pool/context。
- `history_compare_assemble_state_from_checkpoint(envelope.job_state, store)` 真实返回`(assemble_state_ref, dict)`，校闭合job_state字段及state artifact document/contract/canonical bytes；该artifact同样经LocalArtifactStore完整size/rawSHA验证。不是对HTTP字段另作推断或重新计算comparison。
- 提取的source pair必须唯一、exact cold pair与两commit；输出step/operation、两个完整actual ArtifactRef、已验证rawSHA、source pair与own bundleDigest。它是经owner读取后的实际字段提取，不宣称已复制完整原checkpoint原bytes或出版了完整源Surface对象。

主程序对必要cold状态GET返回的**全部pair字段**与该source pair完全相等，并要求HTTP bundleDigest==checkpoint own bundleDigest==保存tar bundleDigest；在worker start前保存两层摘要：HTTP/checkpoint源值、BundlePair/导出Surface最终值。此证明读取原持久化记录，不使用新History actual来回填old expected，不运行旧/新比较生成源预期。

## 2. 摘要分层保持严格约束

`check_http_pair`仅移除HTTP source `surface_digest`与final BundlePair同字段直接相等的错误条件。原comparison/risk跨HTTP/tar相等、bundleDigest/operation/pair/ref/commit/input顺序/12count严格绑定均保留。

源层：原cold HTTP三摘要与新warm HTTP comparison/risk/surface三摘要直接相等。最终层：各自BundlePair摘要与其实际最终Surface相等，cold最终与warm最终摘要相等。`WarmBundleConsumer`中全部`pair_digests`与完整records/snapshots/risk-observable/annotations等仍与cold实际semantic相等；最终Surface仍只允许两个owner外层surface_id/view_id重绑定，其余完整相等。

这没有把source2971…和final81ee…mask成同值；实际值/层级分列。当前Surface Contract把ref rawSHA/size与嵌套manifest内容纳入摘要，Bundle owner重写嵌套JSON后重算final摘要；跨层不同可以成立，同层相同输入必须稳定。R3维持后者，未放宽内容、records digest、target、编号、任何独立OLD/手算或预算约束。

## 3. 其余正文与外层变化

Python逐字diff除上述checkpoint读取/字段保存、分层绑定、头部示例文件名外无变化。已实际0 cold consumer、125表250bindings/schema/count/内容、全族12records及六手帧、六完整annotation/manifest与可观察风险对OLD、原资源ID/image/privateMount/卷/N1M24、历史窗/原日志前缀/正rows校准、EWARM-1共用scope parser、DB/cache健康、唯一未用WarmKey、第四tar唯一调用、暖0计数与cgroup、finally原三ID全stop等继续适用。

wrapper逐字diff仅pin新程序SHA、R3的新输出KEY/SESSION、两处追加R2失败事实；原SOURCE/stack/private secrets/cold0两组manifest、4flags/11remote参数、controlled project stdin/offline/no-sync/native checker、占用/复制/SHA/guarded release及success-only true镜像config/全DiffID取证步骤均原样。

新增R2锚点与独审actual一致：入口1、本地manifest=`b3fcdca8dccfd39cfbebea4ae3caa64c87480ed90fd0404ee646b959a40b86a8`、远端manifest=`6d9514c9df96b7f8d2a1c16b4d902a644ca61c758bd7dc5033001b724d9d1420`、必要cold GET=yes、worker start/newwarm POST/第4tar=no；R1原1/sentinel故障锚点也保留。新输出目录不覆盖原失败，不改变原615项/cold补核127项或SOURCE原停止态资源。

## 4. 当前许可和限制

当前EWARM-2是已诊断工具层级假设，R3是其固定首次修订；R2并未POST实际warm。原profile/失败事实全部保留，按同一具体根因的现DC68规则办理，不以R3名字假定已三修失败，也不清零既有根因。此次只允许原04/原WT/native/原三个ID，核所有状态后一次newwarm及第4tar；任何实际前提或结果失败先停、保原数值/SHA并收尾，不自动重试或fallback重冷/前置/整旅程。

产品与镜像无变、无up/build/sync/retag，无新重建；source06 authority/H绑定输入完全不触及。cold peak继续UNKNOWN，物理report-only字段仍未导出观察，实际warm/HWM/cgroup与源/最终摘要证明待本次原件核收。WARM_CONTINUATION_R3_SCRIPT_GO不等于warm/t1/E/H/release/EXIT证据GO。

---

原件：`/home/dev/gdds-s5-logs/reviews/e-final-evidence-review.md`；SHA256：`332f7f1c36b03b73944111cfde31929965887bfda0f8cdb67077c667c292a653`。

---

# P6 S5 E 最终产品与必要实测证据独立核收

结论：**E_CODE_GO / EVIDENCE_GO，绑定最终产品 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`**。vnext=`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`，Rust=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。当前无未关闭的S5产品/必要实测finding；可逐字归档本轮原审原件、记录全部失败/限制，形成仅文档最终H。**exact-H容器/六包绑定、本人source06 marker释放及EXIT_GO尚未完成，不能提前tag或宣称S5已退出。**

本原审延续E独立角色，不继承设计CLEAR作为代码结论，未实施产品或创建子agent。所有本轮工作仅在本地clean detached审核WT读取固定源码、已复制原件及标准库SHA/JSON/tar核验；没有访问测试节点、运行产品/语法/lint/编译/镜像或执行稿，没有push/tag。最终核收时main exact V2、clean。

## 1. 产品审核闭环与权威来源

完整S5实现/删除矩阵、原设计三项finding及A–D原审关键修订由 `e-code-r1.md` 独立源码审核覆盖：完整task/canonical identity、neutral codec和当前绑定重算、风险cap/filter/clock顺序、metadata-first/exact-commit补行、checkpoint/输入错误边界、cache事务/TTL/pin/释放、T3 producer定位/SAVEPOINT/幂等、FFI同operation/N1/M24、client控制与真实records/risk/surface/bundle consumers均保合同。原设计风险控制、DC94 prepare屏障、七视图及准确schema/1024行batch无回归，已替代实现删除，独立业务golden不变。

原V163全量曾在真实History成功后的旧Compose diagnostic helper把metadata-only checkpoint当row-ready输入而失败；该整次1不能提供任何qualified包。E连续产品复审 `e-code-r2.md`（SHA=`9ecd47347f741b235213a733ddc527fbeb10d5c71f908f366a6aba424963ac4b`）独立核最终V2唯一harness修订：exact scope/commit canonical owner、实际consumer所需reader、同M24/N1与ExitStack/native先关，未改产品行为/业务expected。V2 focused调试19步实际0，五包静态/native及受影响既有Compose1pass已核于 `e-debug-evidence.md`（SHA=`5686ae3a87f203d5ce2b1274d7583a25778089468adc9c5d4f707566d0606ca8`）。后续产品未再改。

**最终全部六包来自同一V2当前实际完整runner，不carry失败163、A–D focused或debug包。** qualified根：

`/home/dev/gdds-s5-logs/execution/e-authority/20261109T113225Z-2d8b29d332ceb467ba77bb4826fb0925653ebb4e/`

独审原件报告 `e-authority-evidence.md` SHA=`0e32da3c9c5b93395f961afa07b9b6f0aa50860ce420e2c86fa845e907c72317`。本轮合并核收再次对该根完整本地清单实算全0；其先前逐步、六份prettyJSON、Rust三步、运行profile/源身份与完整镜像核收保持。node06 `gw-dms-06.lan` 原source WT=`/home/dev/gdds-test-tmp/wt/p6-s5-e-authority-2d8b29d332ceb467ba77bb4826fb0925653ebb4e`；runner 11:33:10Z–12:03:13Z，session至12:03:59Z，8步command/tee全0、起止clean/HEAD V2、后置identity0、cleanup0，marker按设计保留给最终H同WT消费者。

| 权威包/批次 | 当前实际结果 |
| --- | --- |
| rust | fmt0、clippy0、workspace locked/offline test0 |
| shared_kernel | 261 passed |
| repository_contracts | 152 passed |
| repository_client | 170 passed |
| backend parallel / serial | 3642 / 80 passed |
| repository_service parallel / serial | 1764 passed + 1 skipped / 214 passed |

六包最终status均passed，整次runner0；backend既有适用Compose随同次当前HEAD正常构建/运行，无另一个重复Compose验收。runner同步native强制重装，build-input c021一致；offline、workers4、产品N1/M24、backend dependency-base1/networknone/noPREBUILT、正常RS/client source owner build与实际Hypothesis逐包路径均已核。authority主日志SHA=`dff5f6c385ad17f6dbd6a932efdd91710d68e616b34d1d3d262795b284b50b69`，session=`8abf7728540a3737ea1e24f2850ccaae2be0983767f349ab6523f74fd115d157`，steps=`3608a5aaaa61f2241494f42d74db30dc2ecfa0e4739ec7ef22a105d3d8bf283a`，manifest=`d06f00a3216792da2b45e8ac44bbf6666b3853ffee36373ef5ae810ed39df0ba`。

RS唯一skip的原-q日志未点名nodeid/理由，host入口/当前源码仅支持target-smoke推断，另有其他条件skip；其身份不能确定、不能记pass。未发现S5本阶段必需consumer缺测，不扩delegate/cgroup验收矩阵。此限制必须留在handoff。

## 2. 独立expected、合法前置及保存cold闭环

两固定t1输入：v1 107115 bytes/SHA=`42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`；v2 107066/SHA=`4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`。

独立expected来自固定OLD=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、old vnext6368c9c40cf08a97eecf2a0c457a6c16ce448080/Rust e2a901417b19259ece669637a41545e774261445的两次已审最小组件捕获及SQL手算，没有新codec self-roundtrip或从当前History回填业务预期：

- old composite原result SHA=`3707ad9891efa47a2d1b5fdb88e51f9b77880d7532826db1ff4d5a6476ab5261`：完整7字段UNCHANGED、before/current4/4、row changes/history0。两81-byte XML raw确实不同，分别03f90da…、7d0fec19…，未以raw相等作业务前提。
- old Comparison→Risk原result SHA=`d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a`：STANDARD6/ORDERED6、MEDIUM_LOW/1table/6annotations，全部risk业务/annotation内容、目标与编号、content digests原样保存；六unsigned-gid固定8字节大端手帧交叉通过。原risk0假设已被独立旧结果纠正，而非删断言。

两旧oracle根完整清单本次再核全0，先前OLD/source/native/import/生命周期/所有step0/marker释放证据保持。它们仅提供独立expected，不冒当前authority或真实完整旧旅程。

04原pf3根 `execution/e-t1-run/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-7665a6ef4fbc-pf3/` 的两套Preview→Submit→approve合法前置已成功，只有v1 Archive推进原基线；v2 final Submission按实际owner合法可读，无需额外Archive。repo=`dbf7b280-fc21-4726-bafa-71037863e909`；两commit=`o6i9dn2hlkeih7qvuieri7n00553vl3i` / `4on71tpsqvl3ddkqi07tfuhebotu9n8a`。只重置本人新栈derived索引，权威commit/manifest/冻结物理资料保持，physical files deleted0。

唯一cold operation=`op-b8408f429d026545fdd3d8fe`，自身SUCCEEDED/44.148s，完整tar2153472 bytes/SHA=`93da19c776c8840338ab2f89b8450a4c7572bda742d55ea06fd52fc066b769b7`。pf3 driver随后错要求可选物理RiskReport恰1而原入口1；实际records closure1/12、annotation6及250表binding闭合，没有缺少非空引用报告。该失败已保原，不能把pf3整次写成0。

保存cold内容后来在原04/clean V2/native只读补核 actual0：根 `execution/e-t1-cold-recheck/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-31af7983e191-cold-recheck-r1/`，4step0、原615项完整性/原1不变，result SHA=`c3b14d934311be8fc9c5c7230e03b35ee82aae5913a2017c0853e6bbba3b9c8e`；semantic规范内容摘要=`7ef700c6c1022833320578df4b1f44b1785779a55226eee690e8a923a30dd66e`。完整125表250bindings、schema/encoding、逐表count/逻辑内容、12 records全部族及手帧、6完整annotations/manifest/风险可观察投影对OLD全部通过。独审报告 `e-t1-cold-recheck-evidence.md` SHA=`1e4554d1751954d2680b9d3a7d01e7e8c02196e80ca90bfc5fa31bdbf61ebd80`。本次其原根完整清单亦再核全0。

## 3. 唯一warm的原始数字与完整语义

最终warm根：

`/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-e4b4dac49cc1-warm-continuation-r3/`

固定程序SHA=`e4b4dac49cc1acd6ac20bd3b1f985a74300e02575229ee4910e1327f0198366c`，外层SHA=`a1976277b156eb74183cd2dd0b178b6720c084f61b670605ed73a87c45901212`，为原审R3_GO对象。独算162项本地与152项复制远端清单全部匹配，检查0；各step log SHA与清单相符。

| 原件 | 实算 SHA256 |
| --- | --- |
| 本地 `SHA256SUMS` | `b5db596c5c8ea890c33b613126389e5fb98fddc84ed66547a1a9c1dcd8f5e0ef` |
| `remote-evidence/SHA256SUMS` | `190eb9af91a0540608db02ac8fe975b5b56682dc55b211773dcc003291fb4c69` |
| `remote-evidence/session.log` | `a56eb8fd38854e771a7f18979b6816bb2e2698f40baf92f59e039ae09b1289f9` |
| `remote-evidence/warm/result.json` | `c4153a1baf97f22efd92ba219cb5cd3c33a9d536f11cea9a0d19b0d7f254046a` |
| `remote-evidence/warm/warm/result.json` | `d4df28ce9a24b10e5c31f390f57e0dd1c86f2f0aae67076acd086ce9084c3e32` |
| `remote-evidence/image-identities.json` | `254479803068c5ee5c9810220f68709a9b2a0790a7fb8cf1b66e6648f6ad5109` |
| `remote-evidence/warm/bundle-03/complete.tar` | `d2c5940e157e2ef31a02b36a6c7fb9bf9c0ffbe0b1874fbf9faaaef26013f7e6` |

04 `gw-dms-test-04.lan` remote session14:38:53Z–14:40:29Z；六步 source/cold integrity、native、AST、warm、successful-image-identities的command/tee全0。起止/逐步exact V2clean；body WARM_CONTINUATION_PASS0、原三IDstop/inspect全0、remote/tee/copy/hash/local入口全0、本marker remove/rmdir0已释放。原615项和cold补核127项起止核验未变，原私有secrets在导出目录外。

唯一新operation=`op-d387b7f215cd42edfbc08aa6`，新key是原固定、此前未POST的`...pf3-history-warm-resume-r1`；与cold不同，SUCCEEDED34.118s。实际backend最终日志中总计恰2个History POST202（cold+warm），4个bundle GET200（2Preview+cold+warm），没有第五bundle/第二warm/cold或前置重做。新warm delta的真实operation集合只有d387…，未把同key replay当cache hit。

第4tar2153472 bytes、116普通成员/114closure、records closure1/逻辑12。独审用标准库逐个读取114成员，核size/raw SHA、顺序/普通成员与完整JSON的261个嵌入ArtifactRef全部闭合；下载Content-Length/ETag和owner native logical validation在actual程序通过。warm bundleDigest=`sha256:283aefc2d5783b3fd1c7cbb0f5e012651f19647438087bb2c196f9344e01f5de`，与本次HTTP相符；不要求它等于含另一operation绑定的cold bundleDigest。

独审再次直接比较保存cold/warm全部records/snapshots/risk-observable/物理报告观察状态，完全相等；最终Surface只重绑定owner定义的surface_id/view_id两外层ID，其余字段完整相等。全部125表、250bindings；before125表/3733行，current125表/3731行，逐表count/完整schema/逻辑内容相同，PK只保存exact catalog authority。全部ORDERED6/STD6及content digest分别为e79378d9…/0d3af5be…；六手帧、完整annotation6/编号/target/rule/reason/evidence/diagnostics与OLD相符，annotation raw digest=`sha256:f4105ca4ae8af4c70d109fec3bb33542434f33014a11a2cd68ec5cdbbef617e4`，实际manifest/count/content绑定通过。没有将当前codec或新History actual作为独立expected。

## 4. source/final摘要、计数与有限资源

原cold assemble step-2 checkpoint经当前owner从原DB/ArtifactStore只读加载，actual refs及rawSHA验证成功：checkpoint raw=`sha256:0a3c95186d8048a38ac1cbff61acb2ebe5928003850756657fc03c30708ed7ef`，assemble-state raw=`sha256:f56fdc877db169dabe5d02b3ef86515bf104c6c8ca606d527451906bc2b6e277`。提取的完整source pair与cold HTTP全部字段相等，own bundleDigest三方相同；不是重跑源比较或声称完整源Surface对象已出版。

| 稳定摘要域 | cold与warm共同实际值 |
| --- | --- |
| comparison（HTTP/最终包） | `sha256:cc51a9ff6e91d95bb8ad4f00135f031559c8938bd03b22466ce5493614d4686d` |
| risk（HTTP/最终包） | `sha256:cdefa93c80d7a7b09be713143cae0d8d0d3f5815f78b205f807cb5d6f399e8e3` |
| HTTP/checkpoint source Surface | `sha256:2971ba7d71d0605d49c7a81e25e702564b580e9a85e5307d2f8486cc898e2365` |
| 最终BundlePair/导出Surface | `sha256:81eeff34068447eefddf20843e35bc3e1b20f9e5d91dec423f12498a056105ff` |

源/最终Surface的差别来自当前owner嵌套JSON ref重写对manifest rawSHA/size的改变，最终重算摘要。之前工具强加两层等式的错误已明确更正，源域/最终域冷暖各自直接保值；没有mask内容或改产品/golden。

历史cold计数由原stopped容器Docker timestamp窗13:20:19.019Z–13:21:07Z重建，原final stdout/stderr前缀逐字绑定、exact operation/pair隔离；不是冒称原实时before/after差量。warm使用本次实际append-only差量。独审原件支持：

| 实际分层项 | cold | warm |
| --- | ---: | ---: |
| comparison kernel / native calls | 1 / 9 | 0 / 0 |
| ordered single-side | 8 | 0 |
| persistent restore / records validation | 0 / 0 | 9 / 1 |
| diff lookups / digest rebind | 9 / 125 | 9 / 125 |
| RS rows HTTP / catalog HTTP | 129 / 133 | 0 / 4 |
| demanded tables / export cache hits | 250 / 0 | 0 / 250 |
| control metadata resolves | 2 | 2 |
| canonical metadata / catalog reads（两条记录总计） | 4 / 4 | 4 / 4 |
| charged HWM bytes | 25,438,132,736 | **25,438,127,616** |

以上HWM按原件分别列值，不采用协调摘要曾误抄的相同数值；均≤M24=25,769,803,776。N1/active worker1、实际worker limit32GiB=34,359,738,368、reserve8GiB保持。warm实际新worker cgroup初始peak86,695,936，最终peak **109,735,936**、current109,154,304、memory.max32GiB、所有memory.events0；范围为本次worker启动至warm完整tar/validation，包含startup，不能与预约HWM互相替代。

**cold cgroup peak仍UNKNOWN**。原前置initial/prerequisite peak不能回填cold，暖峰值也不能冒作冷值。cold真实SUCCEEDED/32GiB硬限额/M24实际HWM，加上本次暖实际峰值，支持已确认功能/有限资源范围；不作冷峰值、性能容量或三样本提速结论。cold/warm admission INFO均不可观察，保持null，不把logger未开启当0；实际HTTP rows有正cold校准及warm0。

## 5. 当前镜像与缓存来源

本次成功后actual docker-save8refs/3runtime取真实config原字节SHA和全部DiffID，未build/retag。独审重比每个runtime ID对应tag的true config与全DiffID一致，均为原pf3三容器/原image ID；只记录filter labels，不复制私有凭据。

| 04镜像 | true config SHA256 | DiffID数 |
| --- | --- | ---: |
| backend deps lock578e | `46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` | 19 |
| RS deps lock6dc9 | `98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |
| backend runtime/tag | `f43afb60c88567b3dcf40116f325b805fb2058aac5293304c77708e275024772` | 13 |
| worker runtime/tag | `812079db936d6cf25b665ba5a30fdfcc79b807a67128e9949daaed7a6537959b` | 13 |
| RS runtime/tag | `279b9aab99d4cadfdee1720fb74bc20cd5c9d19bba848713afbd549d8fabf0dc` | 28 |

完整DiffID数组保存在实际image-identities.json。04与06两个dependency base的true config/全部DiffID再次直接相同；04backendbase也与原CT20153746原identity全19DiffID相同。原dependency input578e…、archive1b595f…、identity d5ebab…、CT201构建/04及06LANprefill日期SHA见authority独审，当前依赖输入未变，不把inspect ID跨节点比较或旧产品结果carry。

04RS label revision exact V2，build-input=`e76342ef0b58bb0120fc60d8a063d838140ee28d`、source-tree=`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`，与06当前source identity一致；service镜像不同节点的config不被强制相同。backend/worker由原clean V2/sourceWT正常本机Composebuild，原runtime ID在cold/warm完全相同；无source或镜像变化。node06正式authority source镜像/完整provenance仍单独保留，不能用04镜像替换其H carried输入。

## 6. 原失败与最终H条件

失败全部保原，不拼成“单次t1全0”：pf0 unused host Dolt前提、pf1外置script guard、pf2 XML/raw及独立risk预期、pf3 optional物理report假设、warm R1无scope sentinel、warm R2源/最终Surface混层均有固定诊断/修订/原始numeric1或2及日志SHA。产品V163正式runner1仍非qualified。R1/R2暖失败都未POST warm；R3是实际唯一新warm。按现DC68具体根因与只读后处理澄清连续办理，没有无修改自动重试、以目录/角色清零同根、改产品expected掩盖结果。

本次t1已满足已确认最小范围：必要两个合法节点、一次冷+一次新operation暖、实际records facade/完整tar/schema/content/独立代表风险、metadata-first与零行读取复用、有限M/N及关闭。真实FULL/三节点/损坏回填/恢复/所有取消点仍由已审focused owners承担，不在t1复制新矩阵。未知项仅RS skip身份、冷峰值、admission不可观察及未物理导出的RiskReport contract-version/根/表report diagnostics，均如实列清；完整实际annotation diagnostics/records/targets已核，不能泛称全部risk未验。

**可形成纯docs H**：逐字归档各原审/修订/失败报告与handoff，载明最终V2、原六包/Compose来源、独立oracle、savedcold0+唯一warm0组合来源、镜像/缓存来源及上述限制。H不写自身SHA，以未来annotated tag/外置exact-H receipt解析，避免自引用新提交。这个授权来自已授权E收口，不新增Owner确认点。

H形成后仍须同原source06、同原authority WT/env/images/profile实际运行已审H绑定稿：各包原Hypothesis逐包路径不存在，实际`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`等profile一致；六包manifest逐项compare必须changed=[]，直接指最初V2实际来源；RS当前source/label及原save config/allDiffID与backend/worker binding保持。不得仅凭vnext树不变口头carry，不跨节点/换WT或拿04结果代06。若任何闭包/镜像边界变化，按规则运行必要当前结果，不能强行carry。

独审核H绑定原件0后才另授本人marker释放；唯一测试者release实际0/SHA再核，最后本原审写含exact H的外置EXIT_GO回执并保原字节/摘要，root才可本地annotated tag H、main clean停H。当前 **没有release、tag、push或exact-H EXIT_GO**。无需为了把含H的最终回执写回H而无限造H2；该最终回执/绑定原件外置保留及handoff预定路径必须准确。
