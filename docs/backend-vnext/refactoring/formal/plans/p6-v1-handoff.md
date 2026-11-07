# V1 时间与内容事实交接

当前状态：F5授权读取顺序补验已完成，固定产品候选为`c229582a9e`，实际证据与释放见§7；§3–§6保留先前84bad候选的历史记录，不再以其旧GO代替F5终审。

2026-11-07。实施起点 `72bb929b1f22b17ace85a803ce76a5e9a7b5752a`（A1独审 `c1ee962755` 后的协调文档提交）；清单在产品写入前固定。仅V1，不交付V2规则/审核/关闭或D传输，不推送。

## 1. 精确字段、版本与owner（实施前清单）

源序提取的唯一owner为Rust `gateway-compute-core/src/table_access/values.rs` 的成功typed转换行：仅 `version_manager.saved_time`，每chunk有界累积，`mod.rs` 按已有源序chunk合并；不是Arrow规范排序后的列统计，不另扫SQL。`generation_time.rs`实现业务grammar与精确微秒UTC；Shared Kernel原scalar不改。typed转换失败仍按原parser拒绝。`SqlParseOutput.configuration_generated_time` 经PyO3 `lib.rs::parse_output_object`输出小型字典，Python `table_access/native.py`传递有界metadata字典，`ParseResult.configuration_generated_time`携带；application在唯一上传入口严格转换domain对象（capability保持leaf，不导入domain）；XML/手工非业务ParseResult可明确为None，生产上传materialize要求真实事实，缺失硬失败。取消/截止沿原chunk与operation checkpoints，事实随失败结果废弃。既有parser canonical encoding/golden不加入此业务metadata，原值/digest保值。

新增业务类型归 `domain/configuration_facts.py`（供workspace/submission及后续archive读取，不反向依赖capability）：

- `ConfigurationGeneratedTime`：`rule_id=gateway-vnext/configuration-generated-time/v1`、`status=VALID|TABLE_ABSENT|COLUMN_ABSENT|NO_ROWS|NO_VALUE|NO_VALID_VALUE`、`selected_time_utc`、`max_valid_time_utc`、`valid_count`、`empty_count`、`invalid_count`、`last_valid_source_row`、`max_valid_source_row`、`last_not_max`。UTC固定canonical文本；ordinal从1且空/非法占位，max并列首次。缺表/列/无行/全EMPTY/含INVALID但无有效值均分别明确（按§4.1修正首版清单的NO_VALUE遗漏），绝不将漏存metadata当missing。
- `CanonicalContentIdentity`：`canonical_state_digest`、`storage_projection_ruleset_digest`、`storage_projection_version`、`scalar_encoding_version`。state digest复用完整规范表的 `canonical_state_digest_of`，包含现有BROWSE_ONLY/SNAPSHOT_ONLY、version_manager及规则保留字段；不增加/替换内容哈希算法。
- `ConfigurationSideFacts`：`content_identity`、`generated_time`、`source_artifact_id`、`sql_source_digest`。真实上传侧后三项必需；INITIAL空基线复用侧三项显式null（N/A），不能虚构业务时间。
- `ConfigurationFacts`：`schema=backend-vnext/configuration-facts/v1`、`operation_id`、`workspace_id`、`upload_revision_id`、`generation`、`repository_id`、`business_baseline_node_id`、`business_baseline_commit_id`、`baseline_head_version`、`baseline_is_initial`、`baseline_source_submission_id`、`initial_origin=UPLOADED|BASELINE_REUSED|INITIAL_EMPTY`、`baseline_content_identity`、`initial`、`modified`。来源/输入/规则/内容及时间共同进入独立facts身份。序列化为严格JCS `{facts:<上述body>, facts_digest:<sha256>}`；digest为raw SHA256(JCS facts body bytes)，preimage是body，所有嵌套字段精确集合与类型/相互不变量校验，不双读/缺省/回填。PreviewResult ID在publish随机生成，因此事实绑定已有稳定operation_id及exact输入，T1另保留Preview ID绑定。

`preview_jobs._materialize_uploaded_side`从同一parsed结果与staged SQL digest形成源时间事实，随其返回；snapshot materialization/compose不另计算也不改行scalar或业务摘要。`_materialize_all_sides`对FULL initial与modified分别复用完整canonical摘要；对MODIFIED_ONLY读取exact BaselineNode.source_submission_id的持久Submission.modified（INITIAL空节点明确N/A），核repository/commit/manifest/content绑定并保留来源原rules/projection/scalar身份，绝不使用 `_unchanged_baseline_identity_table_set` 的规范行来重算时间。已有 `WorkspaceControlTransaction`补足baseline及submission只读端口。

`_CanonicalPreviewMetadata.configuration_facts`、`PreviewCanonicalBindings.configuration_facts`为必需字段；metadata同时补 `initial_canonical_state_digest`（DigestRef）。现有materialize/assemble checkpoint serialize/decode均严格包含新字段并核payload/side/content绑定；READY沿既有LeaseSession事务整体发布，无旁路。版本改为 `backend-vnext/preview/v2`、`backend-vnext/preview/materialized-sides/v2`、`backend-vnext/preview/assemble-state/v3`；通用checkpoint envelope/Operation runtime版本及canonical table closure版本不变。

`SubmitAttempt.configuration_facts`与`Submission.configuration_facts`均为必需不可变类型；T1从绑定Preview复制并验证源refs/输入/基线/完整身份；Attempt更新拒绝facts变化；finalize从Attempt同事务复制，已有成功replay不重新扫描/提取。Submit payload增加 `configuration_facts_digest`并由decoder/attempt绑定校验；`backend-vnext/submit/v2`。没有新caller通过标志，没有facts独立resource/receipt/state machine。

唯一DDL仍为 `infrastructure/control_db/schema.py::CONTROL_DB_SCHEMA_STATEMENTS`：Preview事实在既有 `preview_result_records.binding` BLOB的canonical对象中（不新增平行列）；`submit_attempt_records`和`submission_records`各增加 `configuration_facts BLOB NOT NULL CHECK(typeof(configuration_facts)='blob')`。无数字schema/migration版本轴；既有sqlite_master结构比较拒绝旧DB。真实mapper为 `sqlite_workspace.py`与`sqlite_submission.py`，严格decode facts并核所在record绑定；基线不增时间副本，V2从BaselineNode→Submission持久字段读取。

HTTP/DTO/OpenAPI本节 **none**：现有Preview/Submit响应形状不变，新增事实只经领域类型/已有持久submission读取端口交V2；本节不提前加入归档诊断API。既有canonical state、snapshot、comparison、risk、surface、bundle摘要算法及golden保值；新增facts metadata不并入业务内容哈希。

## 2. Golden、测试owner与验证安排

新事实固定向量与独立digest golden放 `vnext/fixtures/golden/configuration-facts/v1/`；已有业务golden目录不重录。现有job/checkpoint版本断言同步到目标值，若无磁盘golden则在其原owner测试中更新，不虚构兼容向量。Contract同步 `business-lifecycle-and-state.md`、`canonical-storage-and-repository-boundary.md`、`capabilities/snapshot-materialization.md`、`contracts/snapshot-table-access.md`、P5-5A/5B设计的实际冻结条款；历史DC/审核不改写。

| 不变量 | 唯一权威测试owner |
| --- | --- |
| grammar/UTC/非法分类/源序跨INSERT与chunk、N确定性、typed scalar拒绝 | Rust `gateway-compute-core/tests/configuration_generated_time.rs`；PyO3/backend保留一个adapter smoke，不重复grammar矩阵 |
| facts严格shape、digest与相互绑定、明确N/A与missing区别 | backend `tests/test_configuration_facts.py` |
| FULL完整initial身份、MODIFIED_ONLY基线source事实、materialize checkpoint restart不重提取、坏字段拒绝 | `tests/test_preview_job_materialize.py`及已有checkpoint owner；取消/失租/旧generation在既有worker/publish owner增加最小事实断言，不复制调度矩阵 |
| T1/finalize事实复制、replay/重启、拒绝无部分写及Preview/SQL清理后的独立读取 | `tests/test_submit_transactions.py`（沿现有事务屏障）；domain/mapper只做必要shape smoke |
| 公开payload固定字段与版本 | 现有 `test_submit_job_payload.py`/preview registry decoder owner |
| 最小容器接线 | 收敛候选06已有真实Preview→Submit Compose owner中最小相关旅程，04联合完整门禁延期，不另起新容器矩阵 |

全部测试/编译/lint在06，执行前现场核空闲并原子占用；clean提交独立WT、LAN bundle、legacy符号链接、离线预填缓存、UV_OFFLINE/CARGO_NET_OFFLINE、TMPDIR及jobs/workers4。Rust后强制重装backend扩展并核Rust tree build input；五包ruff/mypy、Rust fmt/clippy及相关focused。未改依赖时复用本节点已预填缓存。原A1 WT/镜像/证据保留。产品含native与持久接线，触发本节收敛候选最小容器验证；清单冻结时点尚无V1镜像/测试证据；实际完成的image revision/source-tree与证据已在§4–§5列明。04联合权威/Compose与05 fresh t1仍留联合候选。

## 3. 实际候选与证据

产品候选 **`84bad715a2faf281e94fa9c0c534414dc7246608`**，`vnext` tree=`608f4b7a837db4a76f1448d4d9d065d66b4e4436`；Rust tree=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`。首个native候选a500、修复2c6；完整跨层3fcea，按正式澄清a24修复499，原manifest绑定/恢复屏障837；consumer/schema适配5864/b737；84bad只为同一Submit容器旅程复用既有provenance保存（4行），未新增runtime机制。未推送、未改写引用提交；并行协调/设计/独审文件未暂存。后续本页与P5正文版本同步仅docs，不改变此产品/容器候选。

实际owning接口为`domain/configuration_facts.py`三层不可变类型及严格`to_document/from_document/assert_binding/assert_source_artifacts`；V2使用既有SubmissionRepository.get_submission，BaselineNode.source_submission_id定位modified。当前支持storage_projection_version=`3`、scalar_encoding_version=`1`；未知编码硬拒绝，合法历史ruleset digest差异按后文澄清处理。独审代码/定向复审`91707082e4`已关闭F1–F4/N1，最后容器/清理证据由同审核者复核。

跨版本澄清（设计者经协调者2026-11-07确认，正式设计提交`a24b7034e9`）：已有additive ruleset Preview保持可用；baseline_content_identity保存source Submission原完整身份，MODIFIED_ONLY.initial原样复制，FULL实际上传两侧使用本operation冻结规则。合法版本差异禁止V2直接判等/合并来源节点，不是整批硬门禁；MO旧A→新B为合法边。FULL无已解释同身份来源时使用既定UNEXPLAINED与版本差异诊断，可有理由接受，不新增issue/额度。未知格式/不支持版本与损坏绑定仍硬拒绝。3fcea初稿三侧规则强制相等已删除，不改既有additive regression为拒绝。

## 4. 实际验证与原始证据

所有编译/测试/lint均在SSH别名`ct107-gw-dms-06`（hostname `gw-dms-06`），测试WT `/home/dev/gdds-test-tmp/wt/p6-v1` 为clean detached已提交候选；`legacy`链接到本节点主参考目录。08:29:49Z现场核无有效busy/Dolt/Compose后原子占用，09:05:20Z清理完成后核对本节owner并释放。测试WT/本节镜像/证据保留，A1与原基准资源未改。

证据根 `/home/dev/gdds-test-tmp/artifacts/p6-v1/`。`evidence-index.json`列出78份日志各自的SHA256、hostname、起止HEAD/UTC、exit、argv与结果，另14个sidecar/script摘要；SHA256=`a1ef262e92482d90ecf87d95d259f8d3637cc1e7a4063fc5618e37acfda26249`。本机只读副本 `/home/dev/gdds-v1-evidence/`。下表日志均在该根；除明确的旧失败记录外exit均0。

| 结果/实际候选 | UTC起止 | 日志 | SHA256 |
| --- | --- | --- | --- |
| native固定向量3；2c6 | 2026-11-07T08:38:28Z–2026-11-07T08:38:29Z | `native-focused-2c6f13731b.log` | `67d59af2e961dcce3914aa8c3e9aa75262db3c2d62098c4c9eb25bfe20e723ae` |
| Rust fmt；2c6 | 2026-11-07T08:38:28Z–2026-11-07T08:38:28Z | `native-fmt-2c6f13731b.log` | `6ea64037ad1edbdcc4c642696f9c0a3d8bf714c7c827ba6fbb0d95cef417e6c9` |
| Rust clippy workspace/all-targets；2c6 | 2026-11-07T08:38:30Z–2026-11-07T08:38:31Z | `native-clippy-2c6f13731b.log` | `b0727188b7ce4e7294609c3b6d4847f9ab8b4e0e0ee2e49679d296c798b3e140` |
| Rust workspace全部测试180；c464 | 2026-11-07T08:53:03Z–2026-11-07T08:53:32Z | `rust-all-c4640fc6fb.log` | `8e33c7d8cd98fbd7074d01a8e0b0958b8d87503774b7178331ea2a6f096c3265` |
| 相关focused318非serial；c464（见批次修正） | 2026-11-07T08:52:09Z–2026-11-07T08:52:24Z | `backend-focused-c4640fc6fb.log` | `4c9e119afdfaff35bd87a6b3cc6db4667dcbdbfc3afcd918ea75e64b46cc312a` |
| consumer非serial453；b737 | 2026-11-07T08:57:11Z–2026-11-07T08:57:50Z | `backend-consumers-b73713ea9e.log` | `f1cdd2e1f0b7c3df49397bd97ad17c2a8ab9fe3934c68fe7bd0125a43a6b041d` |
| consumer serial5；b737 | 2026-11-07T08:57:50Z–2026-11-07T08:57:55Z | `backend-consumers-serial-b73713ea9e.log` | `d0a86ef3ef74e71d9307172156b0e9370bd3f9b9dfe505531b24715da80f91fc` |
| adapter serial2修正批次；b737 | 2026-11-07T08:57:10Z–2026-11-07T08:57:11Z | `native-adapter-serial-b73713ea9e.log` | `26be9c5309d8f95f5fe1d15e7fd1a9cc21a71d0b4c7c1168fc1b03123afb3267` |
| 原parser失败诊断wiring smoke1；b737 | 2026-11-07T08:57:08Z–2026-11-07T08:57:10Z | `parser-diagnostic-b73713ea9e.log` | `21ff1b439cf992e5e73112a382b762bc3675b4bb0c480137a62fd3479e0b7b8f` |
| 既有comparison/bundle/risk/surface冻结101；b737 | 2026-11-07T08:58:38Z–2026-11-07T08:58:40Z | `frozen-business-b73713ea9e.log` | `c472fa7f5e2b1ec6af9603ac07c645aa0a0860d9c9d14ec0e4d9f29884624f3c` |
| 最终DDL schema owner14；84bad | 2026-11-07T09:02:19Z–2026-11-07T09:02:21Z | `schema-owner-84bad715a2.log` | `e204d151dfde3397aa5d5106bed807cb32e2e3fc1e8ae694357d5ec8bd2661ce` |
| 最终Submit Compose1；84bad | 2026-11-07T09:02:39Z–2026-11-07T09:03:10Z | `compose-submit-84bad715a2.log` | `a5c44cb1e5ac17967f4a7e3fa71d815db8a5fc0799630de108b7fface96ff88b` |

Rust命令为`cargo fmt --all --check`、`cargo clippy --workspace --locked --offline --all-targets -- -D warnings`、`cargo test --workspace --locked --offline`；native固定向量用`cargo test --locked --offline -p gateway-compute-core --test configuration_generated_time`。2c6→最终候选Rust tree完全相同，fmt/clippy证据只指这棵未变源码；未称权威runner/carried。Rust四工具按selector为1.97.0，同工具链；PATH以`/home/dev/.cargo/bin`开头，未设置RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME。`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-v1-cargo-target`位于WT外，Cargo jobs=4；产品N/M与pytest workers独立。

Python命令均通过`vnext/scripts/uv-consume.sh -C vnext/<package> run --no-sync ...`（锁只读检查）。backend最初强制`sync --reinstall-package gateway-compute-python`，设置`GATEWAY_RUST_BUILD_INPUT=<HEAD:vnext/rust tree>`；安装后和后续候选均由`check-rust-extension-build-input.sh`核expected=installed=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`，没有复用错误旧so。安装日志`sync-backend-3fcea5a2d0.log`及各build-input日志均在索引。

五包ruff/mypy实际通过：shared_kernel、repository_contracts、repository_client、backend、repository_service在c464同HEAD全通过（`final-{ruff,mypy}-<package>-c4640fc6fb.log`）；后续只改backend consumer/test/DDL，backend在b737及最终84bad再次通过（`compose-final-ruff-84bad715a2.log` / `compose-final-mypy-84bad715a2.log`）。其余四包源码/环境未变，不重跑；每份完整命令、UTC/HEAD/SHA见索引。

批次修正：c464主focused日志原命令漏非serial过滤，报告320通过；其中adapter两项serial的混跑结果不作合格证据，318非serial保留。仅这两项随后在b737以`-m 'serial and not parallel_safe' -n 0`实际补过。consumer正式两批均显式`-m '(not serial) or parallel_safe' -n 4` / `-m 'serial and not parallel_safe' -n 0`；最终Compose nodeid也为serial/-n0。冻结4 owner与schema owner批次显式非serial过滤，实际无serial选择。后续本节/V2/D沿此明确两批入口。

唯一测试owner仍见§2：实际源序/grammar参数矩阵只在Rust；Preview扩一个checkpoint已落盘、successor前模拟停止→新LeaseSession进入materialize已有checkpoint分支，禁止SQL重提取再发布READY，验证FULL initial全规范身份、MO source Submission及原manifest/rules/projection绑定。Submit owner验证T1/finalize同份facts、合法replay、CAS事实不可改；删除Preview并阻断source store读取后，经真实BaselineNode.source_submission_id独立读Submission。坏源绑定读取拒绝只在mapper owner留权威断言；cancel/旧generation沿既有发布屏障，旧generation额外核无PreviewResult行。没有另造恢复状态机或穷举调度。

旧business golden未改；只新增`vnext/fixtures/golden/configuration-facts/v1/frozen-full.json`。full事实digest是独立JCS body的raw SHA256，原canonical state/snapshot/comparison/risk/surface/bundle算法保值，101既有冻结测试通过。HTTP DTO/OpenAPI仍none；V2取得纯领域事实，不导入私有capability/provider或临时artifact。

### 4.1 原失败与修正（不抹除失败）

- a500 clippy因新test的8处unwrap_used失败；2c6使用既有match helper并修正独审F1指出的TEXT hex逻辑文本（含X''为空），同owner小向量重验成功。原日志`native-clippy-a500dd8152.log` SHA=`eca201e5cb53b1f92c4205f1c867f2be3325e8a1a8a998ed8af76f63ecade4b1`保留。
- 3fcea静态首轮unused import/4个typing、499新增test导入、837新增test Optional变量均为明确最小修复后新clean候选重验，原ruff/mypy日志保留；没有改锁、联网补包或回退开发主机。
- efcb focused239通过/55失败为Submit seed改名operation未同步新facts；9df修fixture。ef8 focused318通过/2失败为LeaseSession slots测试patch与另一处nochange fixture；c464修为class scoped patch及显式rebind后通过。失败日志SHA分别`1c466f3d30e610a61ce860ced51cb22f1a846581f140ea5c0c454aab088c4607`、`8885f03cdd1437b99d4c2e1066bd098a9bd6bd47bb3a5acb3e4a2dfd53ccd1d6`。
- c464 consumer169通过/7失败定位旧review改名Preview、手写INSERT漏必需facts与旧History把源refs清空的正向样本；集中扫描所有直接构造/raw INSERT/相关replace并同步，产品校验未放宽。b737复验453+5成功。原失败`backend-consumers-c4640fc6fb.log` SHA=`81ab2e0a6e636b863928923f1f5c1315a5dce70c0bb41a95f8af721b2ae810a5`。
- 一次自身checkout用了linked WT不可见的FETCH_HEAD，在测试派发前exit128，无WT写入/产品执行；按DC68保留说明日志SHA=`4ba72ca9a87fcd60de6396ceabe6fed15ec426192fca174b52ca6555cb803cbc`，从该步改明确efcb hash后仅重做一次成功。

## 5. 容器、缓存与清理

本节Rust/native、持久接线及实际Compose测试改动触发重建；最终**84bad**在06以fresh Compose DB/卷、本机offline build运行精确nodeid `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`。保留Compose build，`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、dependency-base=`gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，未设置prebuilt。第一次b737同旅程成功但未持久provenance；84bad复用仓库已有capture/persist函数补四行后在当前HEAD重建/复验，最后证据只以84bad计。

`submit-provenance-84bad715a2.json` SHA=`d1ecc47cd556f5e30e7051bdbb05cc77b04f62945fb0fc23bfea93ff0e17e85a`，记录三容器实际image ID及RS source labels。`image-identities-84bad715a2.json` SHA=`6ca6ac126f51bfefebf94dbdd482e619ceae0d98eec3a80c99e13bf7bbb5b008`，由docker save真实config核出config digest及全部RootFS DiffID（非以inspect ID冒充config identity）：

| 镜像 | config digest | DiffID数量 |
| --- | --- | --- |
| 本次backend | `sha256:e33455ebb9d3df8eb7b193accf8234881264a6825aa17c1864abea4bb95ba3ef` | 13 |
| 本次worker | `sha256:ff6df3be31d6bc01a237a7aece3a53fc5f103478583ff065ea15c0d29e2f08ae` | 13 |
| RS tag `gateway-repository-service:v1-84bad715a2` | `sha256:a5a530f5afc229bd411b1678df61b5523cfc58cf9ad30ce30a39ddfa8d51c2dc` | 28 |
| backend dependency-base d054 | `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` | 19 |
| RS dependency-base `gateway-p2r1-repository:lock-6dc9659f0aee` | `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |
| client e2e base `gateway-repository-client-e2e-base:local` | `sha256:515069721c40303f942d050f0bb072aead44b63209823c890beeab494f8e2218` | 9 |

backend/worker无source label，由clean HEAD84bad fresh build与harness运行/构建镜像等式及provenance绑定。RS镜像revision=84bad，实际build-input revision仍`a6876d560050285321fd9f62942d590a03f35d64`，source-tree=`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`；RS源码未因本节变化。全部DiffID列表及本机image ID见上述JSON，不另比较跨节点inspect ID。

缓存来源全部为06既有本地预填充（uv环境/缓存、Rust 1.97工具链与registry、Docker base/dependency images）；没有修改依赖、lock或base，本轮没有新制品传输，也无需远端LAN缓存端点/转发代理。各脚本显式`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，unset各大小写HTTP/HTTPS/ALL_PROXY，TMPDIR=`/home/dev/gdds-test-tmp`，未设置GATEWAY_TEST_BASETEMP。源码经开发机`heavy-dev-01`→06获准LAN Git bundle/fetch到clean已提交WT；开发机没有运行测试/编译/lint。backend完整dependency input重算仍=`d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，见`dependency-input-84bad715a2.log`（SHA=`b647b2692761ff69344a50629c6df08bc4c3b8a85d6f660cd51118139a83362d`）。d054历史CT201来源提交`132fc621d5711ae39ac8f1dc66f4349b2f6fe428`、archive SHA=`3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`及预填时间沿[06 readiness §3/§7](p6-node-06-07-readiness.md#3-源码与制品来源)；本轮核本地真实config/DiffID，不创造新预填时间。

Compose正常结束已down -v/remove-orphans；本节project无残留容器/volume/network、8000无监听、整机无dolt/pytest/cargo/rustc进程，测试WT clean。释放日志`node-release-84bad715a2.log` 09:05:20Z，SHA=`6c3b5d83cf03eabffc5cd6b756ad2cd7c2680189765efbd9bcb8aeeb2a6c15fa`；有效占用标志已释放。本节测试WT/镜像/日志和A1原资源均保留。

## 6. 明确交接与延期

V1事实提取/完整内容身份/冻结链已交付候选与06证据；V2继续来源图、时间关系/issue、candidate/selection/anomaly subject纳入facts digest、接受/Start及有理由关闭；按a24保留逐侧原身份，合法版本差异不扩大为整批硬拒绝。D仍拥有完整tar。前端源码/设计、AGENTS/testing-conventions、原冻结基准资源未改，本节HTTP DTO/OpenAPI none。

联合最终仍**延期到04**实际受影响包权威runner与联合候选所需Compose（按闭包规则判断未变包，不引用本节focused冒充runner）；**05**一次fresh t1 FULL/MODIFIED_ONLY、Submit/Review/Archive、Preview/History完整tar及必要小型异常wiring。具体入口为`vnext/scripts/run-tests.sh`及`vnext/backend/benchmarks/real_dump_journey.py`的联合授权范围，04/05精确组合由联合候选工作单固定；本节精确最小容器nodeid已在§5列出。不办理联合exit、不宣称归档业务核验/V2、tar/D或FE3完成，不延用S2b的06真实完整旅程特许。无剩余产品Finding或缓存阻塞，最终GO由同一独审报告确认。

04联合runner中尚未在本节实际执行的容器owner精确nodeid为：`tests/test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart`、`tests/test_submit_compose_e2e.py::test_compose_submit_removes_deleted_user_and_sibling_tables`、`tests/test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey`、`tests/test_review_compose_e2e.py::test_compose_self_only_submit_withdraw_and_upload_again`、`tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect`、`tests/test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart`。它们在联合最终所选包runner中执行后不再单独重复。05真实入口为`vnext/backend/benchmarks/real_dump_journey.py --tier t1 --scope full`（D按目标tar修consumer后运行；输入/项目等环境参数沿联合kickoff固定）。没有提前把当前focused或A1旧容器结果当作这些联合最终结果。


## 7. F5授权读取顺序收口（取代旧GO状态）

原独审在84bad后确认：新ConfigurationFacts完整decode早于target exact scope/created_by校验，坏facts或source refs可抢在既定404前失败。沿既有A1授权边界最小修复，不新增权限、状态或安全框架：`d7c1b8d82e885787e4a39672e752ef4e7ef7f845`先固定scope读取；`c229582a9e72a591cf00a70de526b1b0792c1c18`恢复Review既定完整性响应。当前产品候选为后者，`vnext` tree=`954caffe70c00c9268cd026477298a73f8e47976`；Rust tree仍为`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`。后续本页补证仅docs，不改变产品/镜像输入。

Review同UoW先读持久最小`SubmissionAccessBinding(workspace_id,repository_id,created_by)`，完成当前permission/fresh mapping/exact scope/self-only creator授权后才解完整Submission facts与源绑定；最小binding不替代最终完整模型。授权后full getter已知数据decode/绑定错误，及cross-target existing-key的内部权威引用损坏，窄转换为既有`ReviewIntegrityFailure`→HTTP503 `SERVICE_NOT_READY`，不披露raw row；正常跨目标key仍409。Attempt/Submission点读、SUBMIT Operation以及Preview点读先授权URL workspace/current mapping，再以SQL WHERE workspace+repository过滤目标，mapper只解已绑定目标。Submit受理caller preview_id在HTTP预读和application同样scoped。无权foreign/missing均404；缺permission在业务对象读取前403。其余已授权损坏向量只证明原domain硬拒绝，未宣称新增统一HTTP503分类。生产/facade/fake端口同步；DTO/OpenAPI、DDL、facts/job/checkpoint版本与golden本次均未变。

### 7.1 定向验证与证据

执行节点仍`ct107-gw-dms-06`/`gw-dms-06`。09:26:57Z现场核空闲后原子取得本节marker，09:36:28Z清理并核owner后释放；新独立clean detached WT=`/home/dev/gdds-test-tmp/wt/p6-v1-f5`，最终停留c229。原A1及84bad WT/镜像/证据保留，未占用或清理他人资源。源码经LAN Git bundle/fetch到clean提交；全部编译/测试/lint只在06执行。

新证据根`/home/dev/gdds-test-tmp/artifacts/p6-v1-f5/`；`evidence-index.json`含28份日志和9个sidecar/脚本的完整SHA、hostname、起止HEAD/UTC、argv、exit，SHA256=`e8d464785d53393c2403accda8ba4983a064264575d35699cdde6e29e57513a4`。本机只读索引/镜像/provenance/释放副本在`/home/dev/gdds-v1-f5-evidence/`。以下除明确空串行批次外均exit0：

| 实际候选/结果 | UTC起止 | 日志 | SHA256 |
| --- | --- | --- | --- |
| d7受影响非serial358 | 2026-11-07T09:29:17Z–2026-11-07T09:29:42Z | `f5-focused-d7c1b8d82e.log` | `b0ecd2a22eacec1210ebc6e2eb41644b54564d6301ab4aa418971b56d993d236` |
| d7受影响serial1 | 2026-11-07T09:29:42Z–2026-11-07T09:29:48Z | `f5-focused-serial-d7c1b8d82e.log` | `aed066f128fa476ab64313d2a5f5a438c90a13c1fa91ce574a499c538ab473e4` |
| c229 Review非serial118 | 2026-11-07T09:33:59Z–2026-11-07T09:34:12Z | `review-focused-c229582a9e.log` | `db01e62834f105c48d1c2d96458c65ab6ec24f4249baa19b98973c32f3e9e8d0` |
| c229 Review串行空批次N/A；118 deselected，实际exit5 | 2026-11-07T09:34:12Z–2026-11-07T09:34:13Z | `review-focused-serial-c229582a9e.log` | `b935f709e3f14963e67bd9d5a73674faff568d1bf664e78f58fc88a9024f8101` |
| c229 fresh self-only Review Compose1 | 2026-11-07T09:34:47Z–2026-11-07T09:35:21Z | `compose-review-self-c229582a9e.log` | `99f4f63d33f9af5d17db9d495a9f6ad19ba9054a2485f2e67a641946e0b9671b` |

每次pytest均经`vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync`，非serial为`pytest -n 4 -q --maxfail=5 -m '(not serial) or parallel_safe'`（c229为maxfail3），serial为`pytest -n 0 -q --maxfail=3 -m 'serial and not parallel_safe'`。d7精确文件为`test_review_http.py`、`test_submit_read_http.py`、`test_operation_http.py`、`test_preview_read_http.py`、`test_submit_http.py`、`test_submit_application.py`、`test_submit_transactions.py`、`test_preview_application.py`、`test_sqlite_submit_repository.py`、`test_sqlite_workspace_repository.py`、`test_review_transactions.py`、`test_production_wiring.py`、`test_architecture.py`，均在backend `tests/`。c229只补`test_review_http.py`、`test_review_transactions.py`、`test_review_persistence.py`。c229三文件无serial，exit5原日志保留并记N/A，不计通过、不重跑或补造serial。d7 serial1只作为其原文件范围实际覆盖。新HTTP共享向量仅missing_facts/source_binding两类；原owner证明404/permission-before-object403，Review实际授权503/no raw/no writes及正常跨key409，不复制权限矩阵。

五包ruff/mypy在d7全部exit0（`{ruff,mypy}-{shared_kernel,repository_contracts,repository_client,backend,repository_service}-d7c1b8d82e.log`）；c229只改backend Review接线/测试，backend再次`ruff check .`与mypy通过504源文件，日志SHA分别`eeaafa5a96bec6a61478d48c27d9fbd45e3998f66e59906e05a0b363096ae8a9`、`8a22ad064d23d9e587f7dcfe78252742019b09f786de858e163074bcae42ea01`。d7新WT已offline强制`sync --reinstall-package gateway-compute-python`，build input=e6ac；c229未改Rust，不重复编译。两次`check-rust-extension-build-input.sh`均expected=installed=e6ac，c229日志SHA=`3182583318e9da9203e3c2ad1d1da2880dba09fd0b337f5936f512312e809ddc`。原Rust/业务golden及F1–F4证据保留，未为F5重跑全量runner或真实旅程。

### 7.2 当前最小容器、缓存与释放

Python授权边界变更本可先延期镜像；为本节最终候选绑定当前容器接线，c229在新WT以fresh项目/DB/卷、本机offline build运行既有`tests/test_review_compose_e2e.py::test_compose_self_only_submit_withdraw_and_upload_again`（`pytest -n 0 -q -s -m 'serial and not parallel_safe'`）。覆盖实际生产scoped facade/SQL读、self-only Review读/撤回及再次上传；未新建容器权限矩阵。保留Compose build，未设prebuilt。dependency input仍d054，日志`dependency-input-c229582a9e.log` SHA=`7e4a47d959bb4ba6a15be1ee606272b511a071d2e6e1c855c94067890e296c81`；RS新tag `gateway-repository-service:v1-f5-c229582a9e`构建exit0，日志SHA=`9302818307274309cf06e50a8b8f5e3d9407a068793604592742ee7bb69334b8`。

`review-self-provenance-c229582a9e.json` SHA=`6940d7b6cf1ce5155520e970c8f49d86fed916224162904adf6efb38ba9ab236`；`image-identities-c229582a9e.json` SHA=`cafb565752514e0328764c0c5d750634005f7f38e7a61c9bb97b0e5d1a8195cd`。后者由docker save实际config核出config digest及全部RootFS DiffID，包含三个service和三个dependency base；并非将本机inspect ID当跨节点config identity。

| 当前service | config digest | 全部DiffID数量（完整列表见JSON） |
| --- | --- | --- |
| backend | `sha256:7c006bc1b93f925709fbed8d67a4e0af61e5c2015dd07109a4c799cbc3163443` | 13 |
| worker | `sha256:9c480f9d4792bbb952cf538ccc9c1db2a43f392df7b1e8a05ab6677724566d40` | 13 |
| RS v1-f5-c229582a9e | `sha256:07193eb2efc33d10af22bf11d496bbcf19eec30d0aef29185dab05896ec25f63` | 28 |

backend/worker绑定clean HEADc229 fresh build与harness运行/构建镜像等式；RS revision=c229，build-input revision仍`a6876d560050285321fd9f62942d590a03f35d64`、source-tree仍`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。三个dependency base config/全部DiffID均与§5一致。缓存仍为06既有本地预填uv/Rust/Docker，来源提交/摘要/预填时间沿§5和readiness；无依赖、lock或base变化，无新依赖制品传输，无公网访问/转发代理。显式`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`、Cargo jobs4、WT外原Cargo target，PATH及unset RUSTUP/CARGO_HOME/大小写proxy沿§4；Compose env预置dependency开关/tag与`GATEWAY_DOCKER_BUILD_NETWORK=none`沿§5。

Compose已正常down -v/remove-orphans，project=`gateway-review-s5-294147-test_compose_self_only_submit_0`的容器/卷/网络均空，8000无监听，无Dolt/pytest/cargo/rustc进程，WT clean。owner核对后09:36:28Z释放；`node-release-c229582a9e.log` SHA=`0955f25645ed9066cebb00108816871c55a057e1604d28538a4499262ac68d60`。WT、镜像、原始日志和旧证据均保留。F5代码与证据已交原独审闭环；旧3dd GO被本轮追加终审取代，不提前宣称本节退出。04联合runner/其余Compose、05 fresh t1及V2/D/前端范围仍按§6延期；本节06 self-only Review结果只声明此候选实际补验，不冒充联合最终runner。V2继续按a24保存逐侧原身份，合法版本差异不扩大为整批硬拒绝。
