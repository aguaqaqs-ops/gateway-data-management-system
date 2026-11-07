# V1 时间与内容事实交接

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

全部测试/编译/lint在06，执行前现场核空闲并原子占用；clean提交独立WT、LAN bundle、legacy符号链接、离线预填缓存、UV_OFFLINE/CARGO_NET_OFFLINE、TMPDIR及jobs/workers4。Rust后强制重装backend扩展并核Rust tree build input；五包ruff/mypy、Rust fmt/clippy及相关focused。未改依赖时复用本节点已预填缓存。原A1 WT/镜像/证据保留。产品含native与持久接线，触发本节收敛候选最小容器验证；当前还没有V1 image revision/source-tree或测试证据，04权威/Compose与05 fresh t1留联合候选。

## 3. 实际候选与证据

尚未写入产品；第一份代码候选提交后填写。本文清单为已审语义的具体技术落点，正常技术修订在同页说明，核心业务/权威事实/恢复冲突交协调者设计澄清。

跨版本澄清（设计者经协调者2026-11-07确认，正式设计提交`a24b7034e9`）：已有additive ruleset Preview保持可用；baseline_content_identity保存source Submission原完整身份，MODIFIED_ONLY.initial原样复制，FULL实际上传两侧使用本operation冻结规则。合法版本差异禁止V2直接判等/合并来源节点，不是整批硬门禁；MO旧A→新B为合法边。FULL无已解释同身份来源时使用既定UNEXPLAINED与版本差异诊断，可有理由接受，不新增issue/额度。未知格式/不支持版本与损坏绑定仍硬拒绝。3fcea初稿三侧规则强制相等已删除，不改既有additive regression为拒绝。
