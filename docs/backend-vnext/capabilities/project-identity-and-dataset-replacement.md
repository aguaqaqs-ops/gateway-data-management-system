# 项目身份判定与 Dataset Replacement

本文定义 formal upload preview 的逐 pair 项目身份判定，以及检测到跨项目数据时的安全 replacement 路径。该能力解决的不是“禁止用户上传错误数据”，而是同时满足：尽早告知、允许有审计地继续、计算量有界、展示结果不会错误配对业务实体。

## 目标与非目标

目标：

- 在 snapshot/SQL 物化完成后、comparison/risk/business projection 前判定每个 directed pair 的项目身份。
- 同项目完全保留现有 detailed comparison 和实体身份语义。
- 跨项目不执行行级实体配对，生成完整、可下载、可审阅的 replacement bundle。
- preview 查看、submission 接受和 archive promotion 分成三次独立决策；后两次必须有服务端审计。
- 身份判定的日志、API 和 bundle 不泄露 `version_manager` 原始行。

非目标：

- 第一版不判断数据是否是时间上的“最新版本”。
- 不改变正常 detailed mode 的 channel/device/entity identity。
- history compare 不主动执行项目身份判定。
- 只定义并支持当前 contract；历史 preview/bundle 和持久化状态不提供读取、转换或迁移路径。

## 数据流与状态

```text
source staging / SQL or archive materialization
  -> per-pair project identity assessment
       SAME_PROJECT      -> DETAILED
       UNVERIFIABLE      -> confirmation gate -> DETAILED + degraded diagnostic
       NOT_APPLICABLE    -> DETAILED
       DIFFERENT_PROJECT -> DATASET_REPLACEMENT
  -> [confirmation gate when UNVERIFIABLE]
  -> risk + surface + business projection
  -> complete preview bundle
  -> READY or DEGRADED result and workspace latest preview
```

FULL 上传的 `baseline_to_initial` 与 `initial_to_modified` 独立判定并可选择不同 mode。例如归档基线属于 small-cut、FULL 两份新数据都属于 large 时，前一个 pair 是 replacement，后一个 pair 仍是 detailed。任一 pair 为 replacement，整个 preview 都要求 replacement submit confirmation；`UNVERIFIABLE` 先要求独立 continuation confirmation，不能用 submit confirmation 代替。

身份判定失败不能把已识别为 `DIFFERENT_PROJECT` 的 pair 降级回 detailed；replacement projection 局部失败时仍发布表级双侧快照和诊断。

## version-manager-overlap/v1

输入是两侧 `SnapshotMaterializationResult`。规则固定如下：

1. 读取 canonical table `version_manager`。
2. 排除代理主键 `NO`（canonical name 为 `no`）。
3. 其余列按 canonical column name 排序；双方列集合必须完全相同。
4. 每个值按该列 `SnapshotTableColumn.scalar_type` 使用 snapshot canonical scalar normalizer 规范化。
5. 字符串不 trim、不折叠大小写；`NULL` 与空字符串不同。
6. 去重后任一完整条目相同即为 `SAME_PROJECT`；双方均有可比较条目但交集为空为 `DIFFERENT_PROJECT`。
7. 缺表、空表、没有非 `NO` 列、字段集合不一致或 reader 失败为 `UNVERIFIABLE`。

`saved_time` 没有特殊处理，它只是完整身份条目的一部分。第一版规则刻意简单：宁可在不能判定时显式给出 `UNVERIFIABLE`，也不引入模糊匹配或隐藏启发式。

### Assessment contract

`ProjectIdentityAssessment` 使用 `project-identity-assessment/v1`：

```text
schema_version
rule_version = version-manager-overlap/v1
before_snapshot_digest / current_snapshot_digest
status
comparable_columns
before_row_count / current_row_count
before_distinct_entry_count / current_distinct_entry_count
matched_entry_count
before_entry_set_digest / current_entry_set_digest
assessment_digest
diagnostics
requires_continuation_confirmation
requires_submit_confirmation
```

entry-set digest 根据规范化条目计算；payload、日志和 API 只包含计数和 digest，不包含原始条目。assessment digest 覆盖规则版本、两侧 snapshot、状态、列、计数、entry-set digest 和诊断。

状态语义：

| status | comparison mode | 确认/授权 |
| --- | --- | --- |
| `SAME_PROJECT` | `DETAILED` | 否 |
| `DIFFERENT_PROJECT` | `DATASET_REPLACEMENT` | 是 |
| `UNVERIFIABLE` | confirmation gate；确认后 `DETAILED` | 是，使用独立 continuation action；submit 另行校验 |
| `NOT_APPLICABLE` | `DETAILED` | 否 |

`UNVERIFIABLE` 在确认前 fail-closed：只发布 assessment/diagnostic gate，不执行 comparison、risk、surface 或 business projection，也不发布 READY 或 `ComparisonFacts`。前端确认 `ALLOW_DETAILED_ON_UNVERIFIABLE` 后，受信 orchestrator 必须重新校验 workspace、upload generation、snapshot digests、assessment-set digest、actor policy 和 policy version，才能以显式 policy 继续 DETAILED。确认后的结果保留 `UNVERIFIABLE`，overall 为 `DEGRADED`，并展示 `PROJECT_IDENTITY_UNVERIFIABLE` 诊断。普通用户获得的是可撤销的 server-side policy allowance，不获得 trusted caller 身份。

## DATASET_REPLACEMENT comparison

replacement pair 不调用 normal comparison engine、ordered diff、records writer、row risk 或 comparison-core cache。facts 按两侧 table name union 线性构造：

| 表存在性 | status | counts |
| --- | --- | --- |
| 双方存在 | `REPLACED` | deleted=before rows, inserted=current rows, updated=0 |
| 仅 before | `DELETED_TABLE` | deleted=before rows |
| 仅 current | `ADDED_TABLE` | inserted=current rows |

每张表只保留双方 descriptor、schema 摘要、row count、projection schema 和 snapshot parquet refs；`effective_compare_key` 为空，不生成 changed columns 或 records closure。surface 与 preview index 额外发布 `replacement_summary.before/current`，每侧包含存在状态、row count 和列的 `name/display_name/scalar_type/nullable`；`null` 表示该侧无表，非 null 且 row count 为 0 表示存在空表。空表继续保留在 comparison/surface/bundle 审计事实中，但 replacement business projection 只为对应侧实际存在且 row count 大于 0 的表发布导航项，避免空表和不存在侧形成无内容节点。复杂度是 `O(before tables + current tables)`，随后 snapshot export 是 `O(before rows + current rows)`。

Risk 仅生成 comparison/view-level `HIGH`，reason codes 为：

- `PROJECT_IDENTITY_MISMATCH`
- `DATASET_REPLACEMENT`

不生成 table/row annotations，避免把大量预期 replacement 行放大成风险 artifact。

## Surface、表浏览和业务 projection

当前锁步 contract 为 `backend-vnext/comparison/v3`、`backend-vnext/comparison-surface/v3`、`backend-vnext/comparison-bundle/v3`、`backend-vnext/business-projection/v2`、`backend-vnext/risk/v2`，upload delivery 使用 `preview-bundle/v3`、`preview-index/v3`、`preview-strategy-manifest/v3` 和 `diff-summary/v3`。Reader 只接受这些当前字段语义；旧产物必须重新上传生成。

replacement surface 发布：

```text
comparison_mode = DATASET_REPLACEMENT
project_identity_assessment_ref/digest
change_kind = REPLACED             # 双方同名表
table_processing_mode = DATASET_REPLACEMENT
display_strategy = REPLACEMENT_SIDE_BY_SIDE
```

同名表必须同时导出 before/current parquet。前端使用与 detailed preview 隔离的 replacement 模块，不构造 `PreviewGridRow`、change group、row role、changed columns 或 row risk overlay。表区域提供三个轻量 Tab：

- `替换前`只读取 before parquet；
- `替换后`只读取 current parquet；
- `两者对比`展示双侧 row/schema 摘要，并列展示两个独立只读表格。

双侧原始行不显示逐行 `REMOVED` / `ADDED`，不使用风险颜色或 change navigation。对比 Tab 不做行对齐、同步选择或实体配对，相同行号、`dev_addr`、`gid` 或字段值不表示同一实体。before/current 根据活动 Tab 懒加载并按 artifact URL 缓存。

side-local 业务节点只在来源侧应用 row filter：`before:` 默认打开替换前，`current:` 默认打开替换后；手动切到反侧时展示完整反侧并提示筛选未应用；对比 Tab 始终展示双方完整表。

Business projection 分别以 before-only 和 current-only 输入运行 assembler，再加 side namespace：

- before keys 使用 `before:`，`change_kind=REMOVED`；
- current keys 使用 `current:`，`change_kind=ADDED`；
- channel/device/protocol/parameter/item/stable/tab key 都必须 side-local；
- 不合并相同 `dev_addr`、`gid`、`board/link` 或 table identity；
- `SECONDARY_DEVICES` item/tab 保留结构性空 `risk_summary`（level 为 null、reason codes 为空、annotation count 为 0），以满足 projection v2 的稳定字段合同；
- side projection 失败只记录 `REPLACEMENT_PROJECTION_SIDE_FAILED`，表级 replacement bundle 仍可用。

因此 small-cut IEC104 的 `b1_n2` 与 large dev103 的同名 key 是两个独立实体，不会互相继承名称、tabs、标签、二次装置信息或风险。

## Bundle 与 API

每个 pair 写入：

```text
pairs/<view_id>/identity/project-identity-assessment.json
```

preview index view、surface 和 strategy pair 以显式类型字段发布 `comparison_mode`、identity status、assessment ref/digest、`requires_continuation_confirmation` 和 `requires_submit_confirmation`；这些字段不得塞入通用 options 或 extensions。READY/DEGRADED result、workspace `latest_preview` 和 preview bundle record 保存：

```text
project_identity:
  schema_version: project-identity-assessment-set/v1
  assessment_set_digest
  requires_continuation_confirmation
  requires_submit_confirmation
  pairs[]
```

assessment-set digest 按 view id 与每个 assessment digest 的有序列表计算，用于绑定提交确认到 workspace 的最新 preview。

埋点：

- `upload.preview.project_identity.start`
- `upload.preview.project_identity.completed`
- `upload.preview.comparison_mode_selected`

completed 记录 view、status、两侧行数/distinct 数、matched 数、assessment digest 和耗时，不记录原始条目。

## 三段式交互与审计

### 查看 preview

前端收到 replacement READY 后，在下载/打开 bundle 前强提示可能上传了其他项目的数据，并列出所有受影响 pair（使用稳定的业务阶段名称）。提示不展示规则名、判定表、字段、行数、匹配数或 digest。用户可返回重新上传或继续查看安全预览；该动作只控制本地查看，不是提交授权。

### 提交

Submit 可选字段：

```text
project_identity_assessment_set_digest
project_identity_confirmation_action = ACCEPT_DATASET_REPLACEMENT
project_identity_confirmation_reason
```

`UNVERIFIABLE` 继续 detailed 使用独立的
`ACCEPT_UNVERIFIABLE_DETAILED_RESULT` action，绑定最新 preview/bundle/assessment digests；
它不复用 `ACCEPT_DATASET_REPLACEMENT`，也不把普通用户提升为 trusted caller。replacement
submit confirmation 与 unverifiable continuation 是两个独立的 server-side policy check。

普通 preview 不需要这些字段。replacement preview 必须满足：

- digest 与 workspace latest preview 完全一致；
- action 精确匹配；
- reason trim 后长度为 1–1000。

缺失或空理由返回 `409 PROJECT_IDENTITY_CONFIRMATION_REQUIRED`；digest 不匹配返回 `409 PROJECT_IDENTITY_CONFIRMATION_MISMATCH`。actor 与时间只由 session 和服务端 clock 生成。Submission 持久化 assessment 摘要、理由、确认人和确认时间，review 必须展示。

### 归档

已审核 replacement submission 生成 archive candidate 时设置：

```text
abnormal_kind = PROJECT_IDENTITY_REPLACEMENT
requires_explicit_confirmation = true
```

归档确认必须再次填写非空理由。确认绑定 candidate id、source submission、preview revision 和 bundle digest；candidate 内容变化会删除旧确认。该确认独立于 submit confirmation，不能复用提交理由作为自动授权。

## 失败、安全和性能边界

- `DIFFERENT_PROJECT` 一经确定，不允许由于 projection/risk 失败回退 detailed。
- replacement 不依赖 records artifact，任一表不会出现 `ROW_MODIFIED`。
- snapshot parquet export 对 replacement 同名表必须导出两侧，不能沿用“只选择一个 browse side”的优化。
- cross-pair shared ref 和 parquet cache 仍可复用物理 artifact，但不能改变 side-local ref/展示语义。
- API READY 仍以完整 bundle 可用为条件；本设计不通过放宽 HTTP 超时隐藏计算问题。
- 身份 assessment 是业务事实；comparison core cache 不是事实，replacement 不写该 cache。

## 验收矩阵

身份数据：

- large-1 与 large-2/3/4/5：`SAME_PROJECT`。
- large-1 与 small-cut-1/2/3/4：`DIFFERENT_PROJECT`。
- small-cut-1 与 small-cut-2/3/4：排除 `NO` 后 `SAME_PROJECT`。
- SQL reader 与 snapshot archive reader 对相同数据生成相同 assessment。
- 缺表、空表、字段不兼容：`UNVERIFIABLE` 并先进入 confirmation gate；确认后才可继续 detailed。

replacement：

- detailed engine、records writer、row risk、cache completion 均不调用。
- 双方同名表有独立 refs，modified count 为 0。
- side-local projection key、名称、tabs、二次装置信息和标签不串联。
- comparison-level HIGH risk 存在，row annotation 数为 0。
- bundle/tar 完整生成、下载并由前端解析。

正式流程：

- 归档 small-cut-1 后上传 large-1：READY replacement。
- FULL large-1 + large-2：baseline pair replacement，initial-to-modified detailed。
- 缺确认、错误 digest、空理由提交失败；有效确认进入 `PENDING_REVIEW` 并持久化。
- 审核通过后的 archive candidate 再次要求带理由确认。
