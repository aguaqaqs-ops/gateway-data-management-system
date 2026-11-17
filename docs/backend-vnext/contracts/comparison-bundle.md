# Comparison Bundle Contract

<a id="be-b-v4实施中"></a>

## 当前版本 v4

当前 selector 为 `backend-vnext/comparison-bundle/v4`，transport decoder 只接受该版本。外层 flow/job HTTP DTO 不因内部 surface 字段变化盲升版本。本文规定当前闭包与下载行为；阶段证据和交付身份由 BE-b 交付记录绑定。

- closure kind 增加 ROW_LOCATOR；surface 引用导航(PROJECTION)、诊断(DIAGNOSTICS)、locator 及 before/current/browse 表均须遍历、绑定、改写、下载校验并纳入现有保护/READY/恢复/清理。safe path builder 生成位置，不拼原用户标识符。最终 ref 仅指 bundle 实际唯一成员或 existing shared binding，不能指 canonical/scratch。
- 普通 device/composite_signal_point 有逻辑 before 时必须有 before_table_ref：有变化独立导出，未变可别名 current，不为新增表造 before。保持既有 export cache/shared 去重，locator 按最终导出文件行序计算。replacement 继续两侧独立浏览，不造跨侧 row pair。
- locator 为五列 Parquet：`row_identity:binary(32) not null`、`before_row_index:int64 nullable`、`current_row_index:int64 nullable`、`before_filter_context_json:utf8 nullable`、`current_filter_context_json:utf8 nullable`。按 identity 字节升序，每条已发布普通行记录一行；schema/ordered/blank 用原语义。无 records、超发布上限、replacement 为 null ref。
- 各侧 index 为最终 Parquet 解码 file/row-group/batch 顺序的全局 0 起位置，每条存在侧记录恰好命中一行；无法绑定是 producer 错误。native standard encoder/occurrence 为唯一 identity owner；keyless 等价副本按最终文件遍历 occurrence 绑定，不能总指首行。不把行号写入 comparison identity。
- 逻辑行存在但缺该侧 bundle 快照且发布筛选 tabs 时，context required 非 null，为 JCS 最小导航身份对象；缺列 `{}`、SQL NULL `{identity_column:null}` 均不匹配。有快照侧或逻辑不存在侧 context=null；整表入口两侧 context=null。缺快照侧 index 永远 null；context 从同一 canonical/native identity 流仅为已发布 records 取值，不补全旧单元格或全行索引。
- context/predicate 类型与 FE12 无记录行完整性依据 [Business Navigation Contract](business-navigation.md)；不能由空 records/null locator 单独推断 before 未变。整数保持 client Parquet UTF8 与同侧 metadata，不改 writer schema。
- operation-relative→bundle-relative 改写包含 locator ref，semantic surface digest 必须相等；locator 内无 ref。物理表或 locator 字节重排可改变 bundle digest；同目标版本内规范内容/其他语义产物不变时 surface digest 不变。

B3 row_location contract 拥有行身份/索引/context 验证；现有 test_bundle_assembly、test_bundle_download 与 operation integration 拥有闭包/混合 root/保护，B4 generator 生成真实导航/locator/surface/bundle 五类 golden。FE4b 负责本地 loader/ref/closure 消费与删除浏览器规范编码，不要求重算 surface digest。

> comparison-bundle v2 / preview-bundle v3 加入逐 pair identity assessment artifact、顶层 assessment-set digest 与 replacement confirmation requirement。comparison-bundle v3 将 Preview/History 的完整表数据闭合为 Parquet 并按 layout 与 writer 版本复用导出。只支持当前合同；历史产物需重新生成。详见 `../capabilities/project-identity-and-dataset-replacement.md`。

本文定义 backend vNext 第一版 comparison bundle contract。Bundle 是一个或多个 `ComparisonSurface` 及其 artifacts 的闭合交付单元，可用于前端加载或下载。

前后端简化策略见 `../frontend-surface-simplification.md`。Bundle core 只做闭合交付；preview/upload/submit 绑定语义属于 flow envelope，不写入通用 bundle contract。

## 范围

Comparison bundle 负责：

- 组装一个或多个 `ComparisonSurface`。
- 闭合 surface 引用的 comparison records、risk report、risk annotations、diagnostics 和可选 snapshot table artifacts。
- 提供 bundle manifest、artifact closure manifest 和 bundle digest。
- 支持 flow-specific envelope 在上层引用。

Comparison bundle 不负责：

- 计算 diff、risk 或 surface。
- 读取 SourcePackage、RepositoryRef 或 repository server。
- 写 repository 或推进业务状态。
- 定义 upload/submit/history compare 状态机。
- 定义 ordered diff algorithm。

对于 `DATASET_REPLACEMENT` pair，bundle 必须同时闭合 surface/preview index 中每张表的 `replacement_summary` 与可用侧 snapshot parquet refs。前端按 `comparison_mode` 进入独立双侧浏览模块，不得把两侧 parquet 拼接为普通 diff dataset，也不得为全部替换行生成增删或风险展示。

## 分层

```text
Flow / Operation
  -> BundleAssemblyInput
  -> ComparisonBundle
  -> optional FlowEnvelope
```

规则：

- `ComparisonBundle` 是 flow-neutral derived artifact。
- `FlowEnvelope` 可以保存 upload/history/archive 等业务 metadata，但不改变 surface 内容。
- History compare 2/3 节点由 bundle 持有多个 pair surface；每个 pair surface 仍是完整 directed comparison。

## BundleAssemblyInput

```text
BundleAssemblyInput:
  bundle_contract_version
  bundle_profile:
    SINGLE_PAIR
    MULTI_PAIR
  inputs
  pairs:
    - pair_id
      before_input_index
      current_input_index
      surface_result
      surface_artifact_closure
  shared_artifacts optional
  artifact_policy
  ref_scope: BUNDLE_RELATIVE
```

`surface_result` 是已完成的 `SurfaceAssemblyResult`。Bundle 只接受 `READY` Surface；取消是
bundle `CANCELLED`，required pair 失败是 `FAILED`，optional pair 失败可生成不含 partial
artifact 的 closure-valid `DEGRADED` bundle。

`BundleArtifactBinding` 只在输入 closure 中保存 source `ArtifactRef`、kind、pair/shared scope
和 normalized logical path。最终 manifest/closure 只保存 bundle final ref；source ref 不进入
bundle semantic digest。

`inputs` 是展示输入，不是 source truth：

```text
BundleInput:
  input_index
  role
  display_name
  display_metadata optional
  snapshot_digest optional
```

规则：

- 第一版 `bundle_profile` 只区分 `SINGLE_PAIR` / `MULTI_PAIR`。
- `inputs` 可以表达节点顺序和展示标题，但不暴露 repository commit hash、host path 或 cache refs。
- Preview 的 `inputs[].role` 是封闭集合 `baseline`、`initial`、`modified`（`PreviewBundleInputRole`），按实际输入模式使用其子集（`FULL` 为 `(baseline, initial, modified)`，`MODIFIED_ONLY` 为 `(baseline, modified)`）；由 Preview 构造边界（`preview_bundle_input` / `preview_jobs.assemble`）校验并拒绝集合外角色。消费者可通过 `before_input_index` / `current_input_index` 找到角色，不从 `pair_id` 子串推断。
- History compare 的 `inputs[].role` 维持现有 node `ref_id`（节点引用，不是 Dolt commit hash），按原顺序输出，不套 Preview 三值枚举。通用 `BundleInput.role` 因而仍是字符串，不能全局收窄。
- 上述构造边界已在 G1 落地，不改字段、内容/字节、bundle digest 或 golden，不增加兼容别名。空 GID 的显式引用留待下一次 surface/bundle 文档变更，不在本轮加字段。
- Flow 可以在自己的业务 record 中保存真实 source/ref identity。
- Bundle assembly 不根据 input kind 计算 comparison。

## ComparisonBundle

```text
ComparisonBundle:
  bundle_contract_version
  bundle_digest
  bundle_id
  bundle_profile
  status: READY | DEGRADED
  inputs
  pairs:
    - BundlePair
  table_aliases optional
  summary
  manifest_ref
  artifact_closure_ref
  failed_pairs
  diagnostics
```

`BundlePair`：

```text
BundlePair:
  pair_id
  before_input_index
  current_input_index
  surface_ref
  surface_digest
  comparison_digest
  risk_evaluation_digest optional
  summary
```

`bundle_digest` 输入：

- bundle manifest canonical semantic payload。
- pair surface digests。
- artifact closure semantic manifest digest。
- bundle contract version。

不进入 digest：

- bundle id。
- operation id。
- flow id。
- download URL。
- host path。
- generated_at。

Manifest/closure 的 serialized `ArtifactRef.artifact_id`、source ref、host path 和 runtime metadata
不进入 semantic digest；artifact media type、size 和 raw content digest 进入 closure integrity。

## Table Alias Mapping

Bundle 可以携带 summary-driven table alias mapping，用于让前端展示 logical table，同时复用 canonical table records。

```text
TableAliasMapping:
  logical_table_name
  canonical_table_name
  alias_scope: PROVISIONAL_FAST | CANONICAL
  pair_id optional
  diagnostics optional
```

规则：

- `logical_table_name` 是用户看到和选择的业务表名。
- `canonical_table_name` 是 bundle 中实际携带 records / artifacts 的表名。
- 前端打开 alias table 时读取 canonical records，但 UI 仍显示 logical table。
- 发布到 `preview_index.table_aliases` 的 mapping 两端都必须存在于同一 `pair_id` 的
  `preview_index.tables`。比较引擎可以在内部复用空且未变表的 alias；若 surface 隐藏了该表，
  bundle 不得发布该 alias。
- `PROVISIONAL_FAST` 只来自 upload preview / preview cache，不能作为 submit/archive/history 的权威事实。
- `CANONICAL` 只能来自 FINAL summary / repository readback，可被 history compare、archive 和正式 cache 消费。
- Alias mapping 是正式 bundle/display contract，不得包含 host path、cache-local ref、debug registry 或 repository internal ref。

## 完整 tar 传输

Preview `/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle` 和 History
`/v1/history-compares/{operation_id}/bundle` 成功时只返回一次完整、不压缩 POSIX tar，媒体类型
`application/x-tar`。普通文件顺序固定为原发布 `manifest.json`、原发布 `artifact-closure.json`、
最终 closure 的每个 entry 按原顺序各一个 `logical_path` 文件。PAX 扩展头只是 tar 编码，不是业务
成员；不添加其他业务成员，不使用 hardlink/symlink，不在下载层按 source ref/hash 再去重。
assembler 已合并成一个 entry 的共享产物只发一次；同一 ref 若由最终 closure 声明为两个合法
不同路径，则两个普通文件都发。保留 metadata 路径、绝对路径、空段、`.`/`..`、NUL、反斜线、
重复/冲突路径及非普通文件均拒绝。

`Content-Length` 是全部 header、PAX、padding、成员及两个512字节零结束块的精确字节数；不加
record padding。`ETag` 是用 HTTP 双引号包裹的 bundle digest，安全 attachment filename 为
`bundle-<bundle digest hex>.tar`。uid/gid/mtime=0、mode=0644、uname/gname为空。长路径或
非 ASCII 路径使用局部 PAX `path` 保留 UTF-8 原值；size 超出11位 octal 时使用标准 PAX
decimal `size`，不缩小 ArtifactRef 的 I-JSON size 范围。PAX `<length> <key>=<value>\n`
的 length 按整条 UTF-8 字节数计算到固定点，包括其前缀自身；例如 `12 path=中\n` 为12字节。

当前权限、exact scope、readiness/TTL 检查先于 artifact 读取。同步 `prepare_bundle` 在响应头
前实际读回并验证 manifest、原 closure 和所有成员：canonical metadata/版本、semantic digest、
ref/size/raw SHA、既有有界 reference metadata 引用闭合及安全普通文件。generic projection / diagnostics /
OTHER 业务 JSON 沿 assembler 发布时的引用校验和最终 raw SHA 逐块读回，不新增16 MiB产物限制。
缺失/不可读保持 Preview 404
`RESOURCE_NOT_FOUND`、History 404 `ARTIFACT_UNAVAILABLE`；矛盾、损坏、非法路径/文件类型等
窄完整性错误为503 `BUNDLE_INTEGRITY_FAILURE`，不披露 server path 或业务行。其他鉴权/状态
错误沿各 owning HTTP Contract，不能统一包装成404或空 tar。

通过预检的 bundle digest 还必须等于已授权 PreviewResult 的 `digests.bundle_digest` 或已授权
History assemble checkpoint 的 `bundle_digest`。已解析 PreviewResult 的 expected 不等/空值、
History checkpoint 的 expected 缺失/不等，或指向另一个完整有效 bundle，均在头前503并关闭
准备对象，不能凭 artifact 本身可读发200。原始 Preview 行缺少 digest 键而在既有 mapper 提前
失败的分类沿原读取 Contract，不由此处扩称所有原始行结构错误统一503。

prepare 返回明确的 digest、准确长度、quoted ETag、安全 filename、stream 和幂等 close。
Local artifact 公开 bounded read session 在已有 root 目录 FD 上持共享 flock；协作 cleanup 在
同目录排他非阻塞 flock 内重查 eligibility，读流仍活动时返回 retryable。无新 lock 文件或
durable 下载状态；ADR0012 的可信协作边界不变。准备失败、未开始迭代的响应、正常结束、异常、
断连和取消均释放借用及当前文件。头后 I/O 失败中断，不补 padding 或成功结束块；预检不保证
后续 I/O 永不失效。

原发布 ready closure / required_refs 必须包含 assembler `referenced_artifacts` 的全部 final
rewritten artifacts、manifest 和原 artifact closure。它们随原 lease/checkpoint/protection
publication事务发布并沿原owner释放/TTL；不能等第一次下载才补保护，source/canonical恢复refs
也继续保留。不新增永久pin或独立保留生命周期。

每次只打开当前成员，四位置 root 借用 FD 与当前 artifact FD 合计≤5；无 mmap 或全包 bytes。工作 chunk
≤64 KiB，PAX 路径按片段编码。manifest / closure 各沿原16 MiB JSON上限；原字节、临时验证
字节及 parsed metadata/index 单独按这些 metadata 上限计账，不能把任意产物装入内存冒称流式。

## 建议 Layout

```text
bundle-root/
  manifest.json
  artifact-closure.json
  inputs/
    input-0/
      tables/...
    input-1/
      tables/...
  pairs/
    <pair_id>/
      comparison-surface.json
      tables/
        current/
          <table_id>.parquet
        before/
          <table_id>.parquet
      comparison/
        facts.json
        records/
          <table_id>.records.parquet
          <table_id>.records.manifest.json
      projections/
        business_navigation.json
        business_navigation-diagnostics.json optional
      risk/
        risk-evaluation.json
        risk-report.json
        annotations/
          <table_id>.risk-annotations.json
          <table_id>.risk-annotations.manifest.json
        projections/
          <projection_id>.risk-summary.json
      diagnostics/
        ...
```

规则：

- Bundle 内所有 refs 都必须是 bundle-relative。
- Snapshot/input table artifacts 可以跨 pair 复用。
- 跨 pair 复用的 snapshot table artifact 使用 `shared/snapshot-tables/...` bundle-root ref；bundle
  pair ref rewrite 不得再次把这类 ref 改写到 `pairs/<pair_id>/shared/...`。
- 相同内容的 snapshot table rows 使用一个 `shared/snapshot-tables/{digest}.parquet` 文件。
  对应 closure entry 的 `table_bindings` 保留每个 pair、`before | current | browse` side 和
  `table_name` 的绑定；共享文件不得丢弃其中任一绑定。普通 pair-scoped snapshot entry 也使用
  单元素 `table_bindings`，不再用单个 `pair_id` / `table_name` 表示 snapshot binding。
- MULTI_PAIR 闭包中若出现相同 `source_ref` 且相同 artifact kind 的非 snapshot binding，assembler
  将其提升为 `shared/{kind-segment}/{digest-suffix}/artifact`。Snapshot table binding 使用上面的
  `table_bindings` 合并规则。该结构属于当前 Bundle v4 Contract。
- Upload preview 的 `before_table_ref`、`current_table_ref` 和 `browse_table_ref` 若非空，必须直接指向
  可读取的 Parquet snapshot rows；不得以 JSON descriptor 或 metadata envelope 占位。
- 普通 Preview 默认 current 侧存在时发布 current；删除表保留 before。`device` 与 `composite_signal_point` 有逻辑 before 时另必须绑定 before，未变允许别名 current；新增表的 before 为 null。History 每个节点绑定完整两侧。replacement 两侧独立，不产生 row pair。
- Preview bundle 闭合上传侧全部表以及被删除表的基线侧数据；History 每个节点闭合全部表。bundle 清单为每个 pair/node 保留表名到 Parquet ref 的绑定。相同内容的 Parquet rows 按内容地址共享，不合并或丢弃绑定。
- `records_ref` 若非空同样必须闭合为 bundle 内 Parquet diff rows，并与其 manifest ref 一起发布。
  Bundle assembler 不得自动生成 descriptor、diff envelope 或其他 metadata 来替代这些 row artifacts。
- Bundle artifact closure 必须覆盖最终 rewritten surface 引用的 snapshot parquet、standard/ordered
  records parquet、records manifest、risk annotation content/manifest 和 business projection artifacts。
  Upload preview 与 history compare 使用同一套 writer/validator；发布层不得再手工补写 records/risk。
- Upload preview 的 `preview_index.tables[].diff_artifact_ref` 在正式 vNext 路径中等同于 direct
  Parquet records ref：标准 records 表使用 `CURRENT_INLINE`，ordered records 表使用
  `CURRENT_SLOTTED` 并必须携带 `position_column`。
- History/formal comparison bundle 在 comparison input 带有 snapshot table set 时，应发布可浏览的
  `current_table_ref` / `browse_table_ref` Parquet snapshot rows。标准 records 表使用 `CURRENT_INLINE`，
  ordered records 表使用 `CURRENT_SLOTTED`，从而复用 upload diff 浏览和 full/diff/risk 过滤逻辑。
- History compare 的 snapshot table 发布应复用 upload preview 的 snapshot ref 绑定、fast candidate
  去重、cross-pair shared ref rewrite 和 Parquet export helper。三节点 history compare 中相同内容的
  snapshot rows 可以跨 `left_to_middle` / `middle_to_right` pair 共享为 `shared/snapshot-tables/...`。
- Upload preview 和 history compare 使用同一套 snapshot Parquet cache/export capability。
  跨 operation 持久 cache 只允许使用 repository scope、`SnapshotTableDescriptor.row_layout_digest +
  parquet_writer_contract_version` 精确命中；缓存引用经 artifact protection intent 登记并按 TTL 过期。
  schema/export layout 不同不得命中；`fast_candidate_key` 只用于同次 dedupe、shared ref
  rewrite 和 dry-run/估算，不得作为持久 cache identity。
- Repository-ref materialization 先用 canonical identity 的 `raw_content_digest`、目录 schema、ordered
  row metadata、repository scope 与 writer version 计算 key 并查询缓存。命中时校验并使用缓存行文件，
  不打开 Dolt 表 reader；未命中或缓存文件校验失败时才读取规范表、导出并回填。
- Snapshot Parquet cache hit 恢复到 bundle 时必须登记为当前 bundle 的 bundle-relative
  Parquet closure member。符合下述未变成员复用条件的正式 ArtifactRef 可保持原身份；
  cache-local path 不得出现在 surface、preview index 或 bundle manifest 中。
- 如果 history/formal comparison bundle 缺少 snapshot table refs，但存在 ordered records，前端可以
  以 `FORMAL_ORDERED_RECORDS` 直接读取 `ordered_extension.ordered_records_ref` 指向的 Parquet records。
  该 fallback 只展示 ordered 差异记录本身，不要求 `current_table_ref`。
- Formal comparison surface 中没有 `records_ref` / `ordered_records_ref` 的表应作为 `SUMMARY_ONLY`
  展示摘要；这不是 artifact 读取失败。
- Alias member 默认不重复携带 records artifact；closure 只需闭合 canonical table records 和 alias mapping。
- Comparison records、business projections、risk report、risk annotations 和 diagnostics 是 pair 级 artifacts，默认不跨 pair 合并。
- 业务导航与诊断分别由 PROJECTION/DIAGNOSTICS 闭合。复合信号从同侧普通 `device`/`composite_signal_point` 表读取名称、payload/AST，不生成 points/formulas supplemental artifacts。
- 正式 row records artifact 固定为 Parquet；JSON 只用于 manifest、surface、projection、risk 和 diagnostics 等小型结构化 metadata。
- Layout 是建议，不是 digest 身份；manifest/closure 才是可校验事实。

## Flow Envelope

Flow envelope 是上层业务对象，不属于通用 bundle core。

允许的 envelope：

```text
PreviewComparisonEnvelope
HistoryComparisonEnvelope
ArchiveComparisonEnvelope optional future
```

规则：

- Envelope 可以引用 `bundle_digest`、`bundle_artifact_ref`、operation id、TTL 和权限信息。
- Envelope 可以保存 flow-specific display metadata。
- Envelope 不应改变 `ComparisonSurface` 或 `ComparisonBundle` core payload。
- History compare 不伪装成 preview bundle；preview 的 submit/source binding 不进入 history bundle。

GW08 提交结果重看读取 Submission 已保护的原 Preview bundle，保持 Preview 的 pair/side
闭包与提交时冻结规则；它不转换成 History bundle，也不声称 FULL 两 pair 的净变化。
相同有序节点、scope、规则、比较 Contract 和 History job Contract 的 History 结果在有效期内可返回原 operation
及原 bundle，不重写 manifest、side binding 或 bundle digest。新 History pair 及缓存未命中
仍遵守本 Contract 的每节点完整两侧和 cache/export 校验；提交不可变性不允许仅凭
Preview bundle 地址或单个 content digest 补齐缺失的 History 侧。

## Artifact Closure

Bundle READY 前必须闭合所有可读取 artifacts：

```text
ComparisonBundleArtifactClosure:
  bundle_manifest_digest
  surfaces
  comparison_records
  business_projections
  row_locators
  risk_reports
  risk_annotations
  diagnostics
  shared_snapshot_artifacts optional
```

Bundle v4 的 closure entry 至少包含 `logical_path`、final `artifact_ref`、kind、size/raw digest
和 pair/shared scope。`SNAPSHOT_TABLE` entry 使用按 `(pair_id, side, table_name)` 排序的非空
`table_bindings`；同一内容文件可绑定到多个 pair/table。其他 kind 使用 `pair_id` / `table_name`
表达单一 scope。Bundle assembler 会对 JSON closure 中嵌套的 ArtifactRef 做确定性 rewrite，
拒绝未声明 ref、重复 entry、环依赖、非法 path 或 integrity mismatch。新成员写入、manifest/closure
发布及全部 final referenced artifacts（含复用成员）的完整回读校验完成前，不返回 READY/DEGRADED public result。

规则：

- Bundle 不得引用 cache-local path。
- Cache hit 恢复到 bundle 时必须进入 bundle-relative closure；是否改变 ArtifactRef 按下述复用规则。
- Closure 缺失时 bundle 不能对外 READY。
- Bundle digest 可以包含 closure manifest digest；closure refs 本身可重写。
- Core closure 不闭合 upload-specific 的 `preview_index.json`、`diff_summary.json`；它们由 preview bundle delivery 层根据当前 Preview delivery contract 生成。
- 所有 `ComparisonSurface.tables[].risk_refs.annotation_ref` 与
  `annotation_manifest_ref` 必须在 bundle 内闭合为真实
  `backend-vnext/risk-annotations/v1` content / manifest JSON。任何非当前合同或空 placeholder 都不能占用 annotation ref。
- `RiskReport.tables` 缺席某个表表示该表没有 annotation；正式/preview consumer 应将该表风险
  展示为 `risk_level: null`、`annotation_count: 0`，不得因存在 surface 或缺失 source artifact
  合成 `UNKNOWN`。

## Cache 边界

第一版不要求实现 bundle cache。Snapshot Parquet persistent cache 已作为 snapshot artifact IO cache
实现，但它只缓存可重建的 snapshot rows parquet，不缓存 surface、risk、records 或 bundle assembly。

未来 cache 层：

```text
comparison_surface_cache optional
flow_assembly_cache optional
```

规则：

- `comparison_core_cache` 不缓存 surface/bundle。
- `risk_evaluation_cache` 不缓存 surface/bundle。
- `comparison_surface_cache` 命中后仍需进入当前 operation/bundle artifact closure。
- `flow_assembly_cache` 是 flow-level assembly cache，不是 comparison fact。
- `comparison_surface_cache` 和 `flow_assembly_cache` 是 downstream optional caches，不合并为单一 pair-total cache。

## Ordered 与缓存边界

Bundle 只闭合 surface 引用的已发布 ordered records、blank/interval 与风险产物，不重算算法。标准 locator 与 ordered records 分开解码。计算缓存不缓存 surface/bundle；snapshot export cache 只复用可重建的行文件。缓存命中仍须当前 bundle ref rewrite、完整 raw 校验和原 operation 保护，不建立新保留生命周期。

## 验收标准

- Bundle 不包含 host path、cache-local ref 或 repository internal ref。
- Bundle manifest 可由 artifact closure 完整校验。
- History 2/3 节点可以表达为 1/2 个 pair surface。
- Upload FULL preview 发布 `baseline_to_initial` 与 `initial_to_modified` 两个 pair surface，不做三方 diff。
- Preview 的默认 view 是 `initial_to_modified`；`manifest.comparison_surface_ref` 指向该默认 surface 的顶层副本，`preview_index.views[].derived_artifacts.comparison_surface_ref` 指向各自的 `pairs/{pair_id}/comparison-surface.json`。
- Upload preview snapshot、records、risk 和 projection artifact 默认 pair-scoped；不同 `source_ref`
  不得共享同一 pair-scoped logical path（`tables/...`、`comparison/records/...`、`risk/...` 等）。
  相同 `source_ref` 的跨 pair 重复允许提升为 `shared/...`（见上条）。
- Ordered unsupported bundle 仍可 READY，并提供 review-required risk/diagnostics。

<a id="p7-s1a-目标补充混合位置交付待实现"></a>

## P7-S1a 生效补充：混合位置交付（已生效）

状态：S1a 多 root 下载已实现并经 G 核收，不提升 bundle 合同版本；实际 literal 路径/字段集合比较、ID/raw integrity 传递变化及适用边界见 [S1a 总结](../refactoring/formal/plans/p7-s1a-summary.md)。[A 入口](../refactoring/formal/plans/p7-s1a-a-entry-and-contract.md)保留当时仅固定目标的历史事实。

新bundle manifest/closure、被实际rewrite的新交付成员归export。未改变身份且直接引用的成员保持原ref/location；bundle-relative logical_path是交付路径，不是磁盘类别。producer `_bundle_artifact_id` 与transport重算原closure ID必须共用相同export codec，含surface-source内部临时ref也需合法新格式。bundle_id不是ArtifactRef，不因同名前缀套codec。

### 未变成员复用（Preview publication 优化）

assembler 先校验 source exact ref、完整原始字节与 JSON canonical/引用闭合，再递归确定最终 ref。
未改变字节的 durable/comparison/export 正式成员保持四字段 ArtifactRef 完全相等；canonical
成员继续复制到 export，不将 canonical/scratch 对象直接作为 bundle 成员。JSON 子 ref 实际变化
时重写其父内容并产生 export ref，递归到所需层级；无变化的 JSON 保持原字节/ref。
新 surface、bundle manifest 和 closure 仍发布为 export。不改变 Bundle v4 的字段或摘要 preimage；
ref rewrite 减少可能改变 JSON raw SHA、size 及其传递的 surface/bundle digest，更新相应 golden。

相同内容 snapshot 仍合并为一个 shared logical_path，并保留全部 table_bindings。该组以非canonical
优先、再按 artifact_id 字典序选择稳定代表，所有 alias 与父 JSON 指向代表的最终 ref；每个 source
仍独立校验，不用声明的 hash 代替原始内容校验。此规则不合并不同内容或普通成员的不同合法路径。

只有 `destination_store is source_store` 且上述规划已确认 final ref 直接复用既存正式成员时省略
该成员的 put/即时读回；不查询 exists、不增加 storage fast path。独立 destination（即使是包装器）
必须复制全部 final 成员，使用相同最终 ref 映射，并在该 destination 完成全部 final 校验。
READY/DEGRADED 的完整读验、资源预算与取消边界保留。原 READY/publication 事务接收完整 final refs
并按原保护与 Submit 移交规则管理复用成员；cache/source 的旧保护不是本 bundle 的保护替代物。
不增加保留生命周期或第二权威来源。

下载仍在headers前核授权绑定、完整metadata/成员及size/raw SHA，跨root持有有序borrow，不新建持久tar。原单root“FD合计≤2”在多root目标下改为至多4个root FD加当前1个artifact FD；不预开所有成员，无整包bytes/mmap。正常/未消费响应/断连/取消/异常都释放所有borrow。清理遇借用retryable；头后I/O失败中断，不补成功尾部。READY完整final refs仍在原publication/protection事务中闭合。

artifact_id不直接进入semantic digest的规则不变，但被rewrite的JSON metadata含新ref，其raw SHA/size会变，并可经surface integrity、closure integrity传递至surface/bundle digest。不得以“排除了ID”断言所有旧semantic golden不变，不得删除raw完整性输入来保旧摘要。同一新版本仅改挂载时所有身份/摘要保持相等；A摘要表给出直接/传递变化边界。


S1a ref校验补充：所有四字段backend `ArtifactRef` 使用统一严格a1 codec；旧cache/flow/repository前缀不是合法artifact ID，也不保留为独立前缀判别路径。location只定位root，不替代kind/scope/完整closure/READY校验；合法opaque ref可由export/cache恢复后正式移交，不能按hash前的调用方标签猜授权。bundle-relative logical_path继续使用原路径约束，cache-local/host/repository/flow路径禁令不变。

## 后台结构审计与 READY（2026-11-13）

后台 `comparison-structure-audit` 是 ArtifactStore 产物，独立于前端 bundle 完整闭包；不得加入 bundle manifest、risk annotations 或普通 diagnostics。每个 pair 的共享 pipeline 在成功发布隐藏展示前写入及 exact-ref 校验，缓存命中同样恢复证据并建立当前 pair 的审计。Preview assemble-state v4 / History assemble-state v2 保存每对 `structure_audit_bindings={pair_id,comparison_digest,audit_artifact_id|null}`；严格解码，READY 创建、checkpoint 重放及最终 publish 均核对引用在完整 closure 内、审计可读且 pair/comparison 绑定相等。缺失、损坏和错绑定拒绝发布。

现有 READY closure 的原始 SHA/size 和原有 operation/Preview/History 保护覆盖审计；closure 本身形状/preimage 不变。D 的 Submit 衔接必须在既有事务内把 **完整 READY closure 输出（含审计和审核 bundle）** 转为提交所有保护，再释放 Attempt/临时引用；终态与 workspace 复用不得释放该提交记录仍持有的审核闭包。C 仅建立并验证结果闭包，提交所有保护移交由 Submit/Review owning lifecycle 实施。

### Submission 审核结果的闭包与保留

Submission 复用其不可变 PreviewResult 的 bundle；新增审核读取不改变 bundle v4 preimage，不把后台结构审计加入下载包。PreviewResult 的 comparison_pairs 冻结每组 snapshot/comparison/risk/surface/ruleset digest 和可空审计 ID；AcceptSubmit 和每次审核读取将其与 READY 的 exact refs、manifest pair digest、bundle closure 及严格审计文档核对。Preview assemble-state 由 v4 升至 v5，持久 Preview 绑定直接采用新字段，不兼容旧记录。

AcceptSubmit 的原事务保护完整 READY（含 closure 本身、bundle manifest/final closure 与全部成员、后台审计），并把 READY root exact ref 记录为原 Submit Operation 输入。finalize 原事务先转为 submission-review/submission_id 所有，再释放 Attempt/checkpoint。该保护随 Submission 保留，不随退回、撤回、归档关闭或工作区复用释放；没有提交消费者的失败 Attempt 仍仅按原临时生命周期收尾。

审核摘要与下载都先执行 submission 的当前权限和 exact scope，再核固定结果与完整后台闭包。当前规则变化不重算旧结果。本地缓存不得免除这次服务器授权及摘要身份核对；缺失与完整性错误明确返回，不以空结果或新 History 替代。JSON 元数据读取沿 bundle 的 16 MiB 上限，整表成员以流式 chunks 验证。

审核页面直接读取 `/v1/submissions/{submission_id}/result` 与 `/result/bundle`，不创建或轮询 History。FULL 的 `baseline_to_initial` / `initial_to_modified` 与 Preview 同义，组名与提示共用 Preview 的“原始组态视图”/“本次组态视图”及两侧来源说明，默认 `initial_to_modified`；MODIFIED_ONLY 仍使用单一 `initial_to_modified`（基线→修改）。URL 中有效 pair 选择可恢复，失效选择回到服务端默认。两组的表/行统计、风险和导航各自展示，不计算净变化。页面复用当前比较视图切换与本地浏览；每次打开、刷新（含冲突确认框中的“刷新审核信息”）以及审核动作后的上下文刷新，先重新授权并核对提交 ID、bundle digest 和完整有序 pair digest tuple，再使用已有本地 bundle。失败清空可浏览状态并提供重新读取，不以缓存掩盖权限、缺失或完整性错误。仅服务器明确返回 `SUBMISSION_RESULT_UNAVAILABLE` 或 `SUBMISSION_RESULT_INTEGRITY_FAILURE` 时，允许退回与本人撤回（权限、PENDING 状态及处置限制照旧），审核通过禁用；其他失败仅可重试。核对期间保留已显示的比较视图，但禁用三项审核动作；核对失败仍清空视图，会话切换与重试仍重新读取服务器。

摘要不新增用于预告当前基线的字段。审批沿用原 Review version、基线 CAS 与 canonical eligibility；`BASELINE_VERSION_CONFLICT` 明确提示所基于的基线已更新、不能通过，并保留退回/本人撤回路径。结果本身仍保持原绑定。


Operation.artifact_refs 继续只存有限 root refs（含接受时的 READY exact ref），不塞入完整输出清单。worker 在 finalize 前读取已接受 READY 的 root+outputs；finalize 请求必需携带这些 exact refs，事务内重新构造 READY canonical bytes，与接受时 root 的大小及 raw SHA 核对，并核完整 Attempt 保护后移交。由 READY 唯一确定的成员不成为第二权威来源；删、换、加成员或缺少保护均拒绝并回滚。Preview result/READY job contract 升为 v3 以拒绝缺少固定 pair 绑定的旧结果，assemble-state 为 v5；bundle 内容形状与 preimage 仍为 v4。

`SubmitAttempt.preview_ready_closure_digest` 沿既有字段升级到 v2：`v2:` + raw SHA256(JCS(binding preimage))。preimage 的 `binding_contract_version` 为 `backend-vnext/preview-ready-binding/v2`；包括 Preview ID、workspace/upload/generation/repository、baseline node/commit/head version、ruleset/contract/provider versions、全部 Preview digests、canonical content/facts digest 与 canonical exact refs/digests、identity set 与完整 identity pairs、comparison_pairs（含各 snapshot/rules/comparison/risk/final surface 与审计 null/ID）、bundle/READY ID、producer operation ID。exact ref 表达为 `[artifact_id, media_type, size_bytes, raw_sha256]`；不纳入读取时派生 stale 或 workspace 指针。字段由 `application/preview_binding.py` 拥有。T1 writer、finalize/replay 和每次提交结果读取重算核对，防止同一 READY 下的 pair/规则/审计缺省绑定或 scope 被错换；这是原受理绑定摘要的目标 preimage，不增加另一权威结果或兼容路径。

## 新语义与冻结结果

普通展示的删除值先取真实 before snapshot，否则取已验证的 record.before_values；locator context 只供身份筛选与一致性核对，不是完整行。Navigation v4 的公共风险、归属与定义变化遵循其 owning Contract，均进入已有 projection、surface 与 bundle 闭包。

Preview job v5 在服务器 job payload 的 capability_contract_versions 绑定 risk model、risk ruleset digest 和 business navigation；worker 及新 Submit 的 T1 准入核当前值，不加入 HTTP 请求幂等指纹。同键同请求继续返回原 operation，新键新建；旧结果不满足新受理时要求新键重新预览。已受理 Attempt、finalize 与 Submission 审核只核原冻结 Preview/READY/closure 和绑定完整性，不核当前 global 版本。History job v3 的受理指纹与跨键复用检查绑定 job contract。Preview assemble-state v11 与 History v8 的解码器拒绝旧状态，不改变 READY 闭包格式。
