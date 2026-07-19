# SourcePackage Contract

本文定义 `SourcePackage` 作为多目录多文件输入容器的正式边界。SQL/XML 解析均不属于 `SourcePackage`；业务 materialization 从容器中解析唯一的 `/sql/dbcfg.sql`，并可选解析 `/comps/logic/logics.xml`。

## 职责

`SourcePackage` 负责：

- 接收并持久化用户上传或系统导入的完整源包。
- 安全解包或索引 package 目录树。
- 计算 package、entry 和 required entry digest。
- 校验当前阶段必须存在唯一的 `/sql/dbcfg.sql`。
- 为后续解析流程提供 `SourceDocumentRef`。

`SourcePackage` 不负责：

- 解析 SQL。
- 解析 XML 或其他业务文件。
- 生成 SnapshotTable。
- 计算 comparison、risk 或 repository commit。
- 管理 Dolt branch、server、commit 或 ref。

## SourcePackage

```text
SourcePackage:
  source_package_id
  source_origin optional: USER_PROVIDED | SYSTEM_IMPORTED | TEST_FIXTURE
  package_kind: ZIP | TAR_GZ | DIRECTORY | SQL_FILE | SQL_GZ
  source_package_digest
  package_manifest_digest
  required_entries_manifest_digest optional
  entries:
    - SourcePackageEntry
  artifact_ref
  size_bytes
  created_by
  created_at
  expires_at optional
  retention_policy
  diagnostics_ref optional
```

规则：

- `SourcePackage` 是 L1 staged durable。
- 业务流程决定何时必须等待 SourcePackage durable；capability 本身不理解 upload、submit 或 history compare。
- 同一完整 package 内容重复上传可以得到不同 `source_package_id`，但应得到相同 `source_package_digest`、`package_manifest_digest` 和 required entry digest。
- `artifact_ref` 是内部 artifact 引用，不是 host path。
- `SQL_FILE` 仅用于测试或 benchmark 裸 SQL 输入；正式业务输入仍以完整 package 为准。
- `SQL_GZ` 表示单个 gzip 压缩 SQL 文件输入，解压后映射为 `/sql/dbcfg.sql`。
- `TAR_GZ` 表示多文件 tarball 经 gzip 压缩；普通 `.gz` 不是多文件容器。
- `TAR_GZ` 流式 staging 只物化当前可解析文档路径：required SQL 与可选 composite XML；两者都生成 entry digest 和 content artifact，其他成员保持 metadata-only。

## Retention Policy

`retention_policy` 是保留意图标签，不是 digest input、cache key 或 materialization 开关。

规则：

- `SourcePackageInput.retention_policy` 与 `SubmitSourcePackage.retention_policy` 使用同一语义。
- 默认值 `DEFAULT` 表示：
  - 已持久化的 source package、submit source package、binding 和诊断记录默认保留；
  - 只允许清理 L0 临时态、scratch files、server session workdir 和其他可恢复的 transient resources；
  - 不能因为 flow cleanup 自动删除已经提交或已经固化的业务事实。
- 如果某条流程需要更短生命周期，应通过显式 retention job 或 TTL 过期策略处理，而不是把删除行为隐藏进 capability cleanup。
- `retention_policy` 不参与 `source_package_digest`、`package_manifest_digest`、`required_entries_manifest_digest` 或 SQL materialization 结果计算。

## SourcePackageEntry

```text
SourcePackageEntry:
  normalized_path
  original_path optional
  entry_kind: FILE | DIRECTORY | SYMLINK_UNSUPPORTED
  size_bytes
  content_digest optional
  media_type_hint optional
  role_hint optional
  diagnostics optional
```

Path 规则：

- `normalized_path` 使用 package 内部规范路径，以 `/` 分隔。
- 禁止绝对路径、`..`、空 path segment、host path 和不可解析编码。
- 大小写冲突或 canonical path 冲突应作为 package 诊断；影响 required entry 时为 final failure。
- symlink 默认不支持。

## SourceDocumentRef

`SourceDocumentRef` 是 package 内某个可解析文档的内部引用。

```text
SourceDocumentRef:
  source_package_id
  normalized_path
  document_kind: SQL_DUMP | XML
  document_content_digest
  size_bytes
  encoding_hint optional
  entry_manifest_digest
```

规则：

- `SourceDocumentRef` 不暴露 host path。
- `document_content_digest` 基于 entry bytes 或规范化文本内容；具体语义由 document parser contract 定义。
- `SourceDocumentRef` 可以被不同 parser 消费；当前正式消费者包括 SQL dump parser 和 composite logic XML parser。
- 文档 ref 不包含 upload generation、operation id、cache key 或临时目录。

## 当前业务文档入口

当前阶段固定要求：

```text
required_sql_document:
  normalized_path: /sql/dbcfg.sql
  document_kind: SQL_DUMP
```

```text
optional_composite_logic_document:
  normalized_path: /comps/logic/logics.xml
  document_kind: XML
```

规则：

- 必须存在唯一 `/sql/dbcfg.sql`。
- 不考虑多个 SQL 文件合并、排序或同名表覆盖。
- `/comps/logic/logics.xml` 缺失时返回稳定 EMPTY source，不产生 package diagnostic。
- composite XML 走独立 parser/capability，不进入 SQL dump parser。
- 除上述两项外的文件只进入 package manifest 和 diagnostics。

GZ 规则：

- 如果输入是单个 `.sql.gz`，使用 `SQL_GZ`，解压后作为 `/sql/dbcfg.sql`。
- 如果输入是包含多目录多文件的 `.tar.gz`，使用 `TAR_GZ` 并按 package entry 规则索引。
- TAR 中 `/comps/logic/logics.xml` 存在时必须与 required SQL 一样完成流式提取、digest 和 artifact 固化；成员顺序不影响结果。
- 单独 `.gz` 不表达目录结构；除 `SQL_GZ` 外不作为正式多文件 SourcePackage。

## SqlDumpSource

`SqlDumpSource` 是 SQL materialization 的输入，不是 package 容器。

```text
SqlDumpSource:
  source_document_ref
  sql_source_digest
  parser_input_contract_version
  encoding
  source_size_bytes
  diagnostics optional
```

规则：

- `sql_source_digest` 是 SQL parser 输入身份；当前业务默认由 `/sql/dbcfg.sql` 派生，compat/test 输入可由 synthetic document identity 派生。
- SQL Snapshot materialization 主要依赖 `sql_source_digest`，不直接依赖整个 zip bytes digest。
- zip 文件顺序、压缩参数、mtime 等 package 物理差异不应改变 SQL Snapshot。
- 如果 SQL parser 对文本做换行或编码规范化，规范化规则必须由 `parser_input_contract_version` 固定。

## Digest 边界

| Digest | 覆盖内容 | 用途 |
| --- | --- | --- |
| `source_package_digest` | package 容器规范身份 | source artifact 审计、重复输入诊断。 |
| `package_manifest_digest` | 完整 entry 清单和 entry digest | 证明系统收到的目录树。 |
| `required_entries_manifest_digest` | 调用方指定的 required entries | 外部 binding、replay validation 和快速复现。 |
| `document_content_digest` | 单个 entry 内容 | document parser 输入校验。 |
| `sql_source_digest` | SQL dump parser 输入 | Snapshot materialization cache key。 |
| `composite_logic_source_digest` | XML entry 内容或稳定 EMPTY marker | 业务 Snapshot materialization identity。 |

这些 digest 都不包含：

```text
source_package_id
业务对象 ID
operation_id
generation
host path
临时文件名
cache key
```

## 错误与降级

Package 级 final failure：

- 缺少 `/sql/dbcfg.sql`。
- `/sql/dbcfg.sql` 不唯一或 canonical path 冲突。
- package path traversal。
- required entry digest mismatch。
- package artifact 无法持久化。

SQL 级 failure 或表级降级不属于 `SourcePackage`：

- SQL 语法不支持。
- DDL 不支持解析。
- identifier canonical 冲突。
- 行值解析失败。

## Cache 接入点

第一阶段只需要薄 cache 边界：

- `source_package_index_cache` 可选，用于复用 package entry index；不是业务事实。
- SQL-only benchmark 的 `source_snapshot_cache` 继续使用 `sql_source_digest + SQL parser/materialization versions + table_ruleset_version`。
- 正式业务 Snapshot identity 使用 SQL digest、XML digest/EMPTY marker、两类 parser/materializer version 和 table ruleset version 的组合。
- `snapshot_table_artifact_cache` 不直接使用 package bytes，而使用 table descriptor / raw content digest。

调用方可以要求写入 `PROVISIONAL` cache candidate；只有经过 repository/readback 或等价权威校验后才能 promote 为 `COMMIT_VALIDATED`。具体哪些业务流程允许读取或写入这些状态，由 `flows.md` 映射。

## 验收标准

- 同一 package 内容重复 staging，entry manifest digest 稳定。
- 改变 zip 物理元数据但不改变 `/sql/dbcfg.sql` 内容时，SQL Snapshot 不应变化。
- 缺少或重复 `/sql/dbcfg.sql` 时，SourcePackage staging 明确失败。
- 缺失 composite XML 时业务 Snapshot 可正常生成；XML 内容变化必须改变业务 Snapshot identity。
- 除 composite XML 外的非 SQL 文件被记录为 unconsumed members，不影响业务 Snapshot。
- 裸 SQL / `.sql.gz` benchmark 输入必须通过 `SQL_FILE` / `SQL_GZ` 或测试 helper 显式标记，避免混入正式业务 contract。
