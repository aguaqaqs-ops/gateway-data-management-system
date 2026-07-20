# Phase 1 Executable Contracts and Walking Skeleton Discussion Notes

状态：Resolved（2026-07-19；讨论证据，正式规则见第 20 节映射）

适用阶段：Phase 1 — Executable Contracts and Walking Skeleton

讨论范围：normative vector schema、scenario manifest/golden envelope schema、conformance runner/harness contract、Arrow/PyO3 walking skeleton 最小边界、Phase 1 验收矩阵。

## 1. 本轮边界

- Phase 0 formal 结论均视为 Accepted；除非发现正式文档内部冲突，不重新讨论其业务语义。
- 本轮只做设计访谈和文档收口，不实现业务代码、schema validator、runner、harness、Rust kernel 或 fixture。
- 讨论证据保留在本目录。收敛后的正式规则按 semantic ownership 重新撰写到 `formal/`；不得把本文件直接移动或改名为正式文档。
- 本文件中的“推荐”在用户确认前不是正式决定。

## 2. 已读取上下文

已完整阅读：

- `formal/README.md`
- `formal/contracts/contract-taxonomy-and-ownership.md`
- `formal/contracts/shared-canonical-encoding.md`
- `formal/contracts/fixture-oracle-and-conformance.md`
- `formal/adr/0001-python-rust-hybrid-compute-strategy.md`
- `formal/adr/0005-shared-canonical-encoding.md`
- `formal/adr/0006-language-neutral-fixture-oracle.md`
- `formal/plans/implementation-stages.md`

另以只读方式核对了 Phase 0 fixture/oracle 讨论中与本轮直接相关的章节、环境准备记录、Phase 1 环境执行台账，以及现有 `vnext/backend`、`vnext/rust`、`vnext/repository_service` 最小 bootstrap。

## 3. 已确认事实

### 3.1 权威与 ownership

- Shared Kernel 唯一拥有 canonical encoding byte contract、`canonical_encoding_version`、CanonicalIdentifier、typed scalar frame、row/collection framing 与 semantic digest。
- Conformance Harness 拥有 scenario manifest schema、runner result、profile dispatch、fault protocol 和 evidence bundle；每个 expected semantic payload 仍由其对应 Domain/Application/Capability/Repository contract owner 唯一拥有。
- Python Backend、Rust compute core 和 Repository Service 都必须直接消费同一组正式 vectors/scenarios；任何实现语言都不是正式 oracle owner。
- Manifest schema version、scenario-bound semantic contract version、canonical encoding version、provider implementation version是独立版本轴。

### 3.2 Normative vectors

- 唯一根为 `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/`。
- 固定文件为 `vector-set.json`、`jcs.jsonl`、`scalar.jsonl`、`digest.jsonl`、`invalid.jsonl`。
- Valid case 必须固定完整 canonical bytes，适用时同时固定 digest；只比较最终 digest 不算通过。
- Invalid case 只固定 stable error code，不固定语言异常类型、错误消息或堆栈。
- 普通 CI 不生成或 bless vectors；generator 只能产生 candidate diff。改变既有 v1 case 的 bytes/digest/success classification 必须发布 v2。

### 3.3 Scenario/golden

- `scenario.yaml + input/ + expected/` 是无继承、无脚本、无 hook 的 declarative closure。
- Scenario ID、track、subject 和 kebab-case path 必须可逆一致。
- Unknown field、path escape、duplicate key、closure/digest/size mismatch 和 ID/path mismatch 必须 fail closed。
- Golden 必须绑定唯一 semantic owner、contract ID/version、payload media/schema、canonical encoding version、comparison mode 和 content digest。
- Structured golden 做 schema validation 后的 exact canonical compare；artifact golden 比 schema/digest/closure；recovery golden 比 checkpoints 和最终事实。

### 3.4 Runner/harness

- Runner core 只负责 schema/closure validation、profile dispatch、stable clock/ID、result aggregation 和 evidence packaging。
- Subject harness registry 通过 `(track, subject)` 解析 owner-registered public entrypoint；manifest 不携带语言或函数入口。
- 结果全集固定为 `PASSED | ASSERTION_FAILED | HARNESS_ERROR | UNSUPPORTED`。
- Recovery 使用单一 primary typed fault、test-only arm/consume exactly-once protocol、至少 `after_failure`/`after_recovery` checkpoints、stable-read barrier，以及 production restart/reconcile/takeover 入口。

### 3.5 Arrow/PyO3 walking skeleton

- 正式边界必须是粗粒度 Arrow batch/table 调用；小型 options、metadata、errors 和 diagnostics 使用版本化 DTO/schema。
- 不允许逐 row/scalar FFI，也不允许把大规模 Python dict/dataclass/object graph 作为正式输入。
- Rust 计算释放 GIL；panic、timeout、cancel、OOM/native failure 映射到稳定 capability error/diagnostics。
- Phase 1 只要求首个 Linux x86_64 glibc 部署目标，不建立完整 wheel 平台矩阵或网络 compute service。
- Walking skeleton 必须可被 Phase 3 复用，并完成 `Python facade -> Arrow/PyO3 -> Rust batch kernel -> ArtifactRef/diagnostics` 闭环。

## 4. 正式文档一致性审计

当前未发现需要重新打开 Phase 0 业务语义的正式冲突。

发现以下 Phase 1 必须补齐的 executable under-specification；这些是本轮设计对象，不是对 Accepted 业务语义的否定：

1. `scenario.yaml` 的 YAML source grammar、JSON-compatible data model 和 schema dialect尚未固定。
2. `manifest_schema_version` 是 manifest wire field；ownership taxonomy 中的 `fixture_manifest_schema_version` 是版本轴名称。两者需要明确为“wire 字段名”和“概念轴”，避免被实现成两个字段。
3. `digest` 在资产完整性、semantic payload identity、fixture closure identity 三个层次的字段名和 preimage 尚未逐项固定。
4. Vector case 的 test-only logical input representation 尚未固定，尤其是 lexical numeric normalization、binary、temporal、anomaly 与已经 typed 的 Arrow value 之间的边界。
5. Stable canonical invalid-code registry 尚未落为可执行枚举和 validation stage。
6. Manifest `expected[]`、golden envelope 与 golden payload 之间的引用/内联规则尚未固定。
7. Runner 与 harness 之间的 typed request/observation/fault/cleanup contract，以及谁负责 semantic comparison，尚未固定。
8. `UNSUPPORTED` 与 `required_profiles[]` 的 aggregate gate 关系尚未固定为机器规则。
9. Walking skeleton 的最小可复用 kernel、Arrow schema、small DTO 和 ArtifactRef ownership 尚未固定。

## 5. 当前 bootstrap 观察

- 仓库已有 Python、Rust、Repository Service 独立项目和首个平台的构建环境。
- 当前 Rust demo kernel 只做 nullable `int64` double，PyO3 adapter 通过 `to_pylist()` 把 Arrow 列转换为 Python object list，再构造新的 PyArrow array。
- 因此当前 demo 能证明 extension build、一次调用、GIL detach 和简单结果往返，但不能证明正式 Arrow C Data/Stream 边界，也违反“不以大规模 Python object graph 作为正式输入”的既定约束。
- 当前 `ArtifactRef` 只是 Python 本地 dataclass，对序列化版本、artifact contract marker、location-independent recovery 和 diagnostics 尚无正式表达。
- 这些均记录为 Phase 1 设计/后续实现缺口，不把现有 demo 结构提升为 contract。

## 6. 初始推荐（历史状态；现已接受）

### R1. Authoring 与 canonical data model 分离

`scenario.yaml` 采用严格 JSON-compatible YAML 1.2 子集作为 authoring format；禁止 anchors、aliases、merge key、custom tags、implicit timestamp、非 JSON scalar 和 duplicate key。解析后得到唯一 JSON data model，再以 JSON Schema 2020-12 fail-closed 校验，参与相等性/digest 时转为 JCS。

理由：保留 YAML 可读性，同时避免不同 YAML parser 产生不同类型或 merge 结果。

### R2. Vector 使用 test-only discriminated input

Vector 不把 Python/Rust 对象序列化方式变成 contract。每个 case 声明 `operation` 和 schema-declared test input；scalar 输入使用 test-only discriminated union 表达 lexical logical literal、raw bytes 或 typed value。Arrow schema conformance 使用独立 operation/case，避免把 SQL parser token、Arrow physical value和 scalar normalization 混成一个入口。

### R3. 三层 digest 显式命名（用户已确认）

- `raw_sha256`：直接 SHA-256(asset bytes)，用于 byte/size/closure integrity。
- `content_digest`：由 semantic owner 定义、使用 domain-separated canonical payload 的语义 identity。
- `fixture_content_digest` / `vector_set_content_digest`：由 Conformance Harness/Shared Kernel 对 closure 定义的集合 identity。

禁止用一个模糊 `digest` 字段根据上下文猜测层次。

### R4. Golden envelope 与 payload 分层

Manifest 的 `expected[]` 只登记 closure/dispatch 所需的 expected asset identity；每个条目指向一个 golden envelope。Envelope 负责 owner/contract/schema/comparison/content identity。Structured/recovery 小 payload 可内联在 envelope；artifact payload 必须通过显式 content-digested closure ref 引用。Manifest 与 envelope 的重复 binding 必须逐字段相等，否则 fail closed。

### R5. 精确版本字段名

Scenario wire field 固定为 `manifest_schema_version`。`fixture_manifest_schema_version` 只作为文档中的版本轴全名，不成为第二个 wire field。Vector 独立使用 `vector_set_schema_version`；golden 独立使用 `golden_envelope_schema_version`。

## 7. 访谈状态

### 已确认决定

- 用户确认 R3：schema 强制区分 raw asset integrity、owner semantic content identity 和 closure-level content identity；不保留依赖上下文解释的裸 `digest` 字段。
- 用户确认修订 R1：受限 YAML authoring + JSON Schema 2020-12 structural validation + named semantic validators + JCS equality/digest。
- 用户确认修订 R2：logical-literal normalization、language-neutral typed scalar encoding、owner-owned Arrow mapping 三层分离；vector 解析性能不作为优化目标，production Arrow boundary shape 前置。
- 用户确认修订 R4：manifest expected entry 指向自描述 golden envelope；由 kind/size policy 决定 inline payload 或 closure ref，重复 binding 必须一致。
- 用户确认 R5：`manifest_schema_version`、`vector_set_schema_version`、`golden_envelope_schema_version` 分离；`fixture_manifest_schema_version` 只作为概念轴全名。

### 暂定假设

- Phase 1 schema 可以采用 JSON Schema 2020-12，但不因此建设通用 schema registry 或 codegen pipeline。
- Repository Service 的 Phase 1 conformance consumer 可以是最小独立入口；不要求提前实现 Phase 2 wire service。
- Walking skeleton 的 production-shaped kernel 应替代当前 nullable-int doubling demo，而不是把 demo 合同化。

### 已识别风险

- YAML parser 差异可在 digest 前制造不同 data model。
- Vector test input 若未区分 lexical normalization 与 typed Arrow value，会把 SQL parser 或某语言对象模型错误提升为 Shared Kernel contract。
- Raw asset hash、semantic content digest 和 closure digest 若同名，会产生错误的缓存/版本兼容判断。
- 若 harness 自行判断 pass/fail，runner 会失去语言中立的 comparison authority；若 runner理解业务 payload，又会侵犯 semantic owner。
- Arrow IPC bytes 不天然等于 semantic digest bytes；把 IPC serialization hash 当成业务内容 digest会造成版本/实现耦合。

### 延后事项

- 完整 OS/architecture wheel matrix。
- Phase 2 Repository transport 与完整 wire contract。
- Process-crash 的真实容器/进程编排实现细节。
- Provider registry、schema codegen、通用 DAG/workflow。

## 8. 第一轮问题：schema authority 与 identity

以下问题等待用户决定；回答会决定 vector、manifest 和 golden 的顶层形状。

1. 是否接受 R1：YAML 只作为严格 JSON-compatible authoring format，JSON Schema 2020-12 是唯一结构 schema，JCS data model 是 equality/digest authority？
2. 是否接受 R2：scalar vector 使用 test-only discriminated input，并把 lexical normalization 与 typed Arrow conformance 分成不同 operation/case，而不是建立一个模糊的通用 `value` 字段？
3. 是否接受 R3：schema 中强制区分 `raw_sha256`、owner `content_digest` 和 closure-level content digest，不保留上下文相关的裸 `digest` 字段？
4. 是否接受 R4：`expected[] -> golden envelope -> inline payload 或 content-digested artifact closure ref` 的两层模型，并要求 manifest/envelope 重复 binding 一致？
5. 是否接受 R5 的三个独立 schema-version wire 字段，以及 `manifest_schema_version` 与概念轴 `fixture_manifest_schema_version` 的命名解释？

用户答复状态：

- Q1：要求给出建议，尚未确认。
- Q2：要求详细解释、建议和性能取舍，尚未确认。
- Q3：已同意。
- Q4：要求结合场景详细解释和建议，尚未确认。
- Q5：要求详细解释，尚未确认。

## 9. 第一轮展开说明与修订建议

### 9.1 Q1：YAML authoring、JSON Schema 与 JCS 如何分工

推荐接受 R1，但把“唯一结构 schema”精确化为以下四层，避免让 JSON Schema 承担它不能表达的 closure 校验：

```text
UTF-8 scenario.yaml
  -> 受限 YAML 1.2 JSON tag-resolution subset
  -> JSON-compatible data model
  -> JSON Schema 2020-12 structural validation
  -> named semantic validation: path/ID/closure/digest/cross-field invariants
  -> JCS bytes for equality and semantic/closure preimage
```

#### Authoring 层允许

- 单一 YAML document。
- String-keyed mapping、sequence、string、boolean、null，以及满足 I-JSON/JCS 范围的有限 number。
- Block/flow presentation、comments 和普通 whitespace；这些 presentation details 不进入 semantic identity。

#### Authoring 层禁止

- Anchor、alias、merge key、custom/local/global tag 和 directive。
- Complex/non-string mapping key、duplicate key、multi-document stream。
- Implicit timestamp/date、binary/object constructor、NaN/Infinity 和 YAML Core schema 的扩展 numeric forms。
- 超出 JCS safe range 的 integer、decimal、uint64、binary 和 temporal 直接作为 YAML number/native type；这些必须由字段 schema 规定为 string/typed representation。

#### 两种 “schema” 不得混淆

- YAML 1.2 的 JSON schema/tag-resolution：只决定 plain scalar 如何解析成 JSON-compatible scalar。
- JSON Schema Draft 2020-12：验证解析后的 object/array/field structure。

每个 JSON Schema 文件应固定 `$schema` 和 `$id`，对象默认 fail closed。不得单靠 `format` annotation 承担安全或 identity 校验；path escape、scenario ID/path 可逆性、asset closure、hash/size 和 self-exclusion 必须由 Conformance Harness 的命名 semantic validator 执行。

#### Digest 建议

- YAML 原始空白、注释、单双引号选择不改变 manifest semantic identity。
- `fixture_content_digest` 使用 schema-valid JSON data model 的 JCS bytes，加上 closure asset 的显式 `raw_sha256`/size identity；不直接 hash authored YAML bytes。
- 原始 asset/envelope bytes 仍由已确认的 `raw_sha256` 验证。

#### 选择理由

- 保留 `scenario.yaml` 对人工编辑和 review 的可读性。
- 避免不同 YAML parser 对 timestamp、merge、alias、numeric scalar 产生不同 native value。
- 不改动 Phase 0 已接受的 JCS authority。
- Schema validation 和 cross-field/closure validation 各自拥有清晰错误类别。

不推荐 full YAML，也不建议现在把 Accepted 的 `scenario.yaml` 改成纯 JSON。前者引入不必要的图/类型语义；后者改善机器一致性但降低 scenario authoring 体验，且不能消除 closure semantic validator 的需要。

### 9.2 Q2：为什么必须区分 lexical normalization、typed value 与 Arrow mapping

单一 `value` 字段无法无歧义覆盖 Shared Canonical Encoding：

- `+001`、`01`、`-0` 和 `0` 可归一到相同 integer value；一旦先解析为 JSON/Arrow integer，原 lexical case 已丢失。
- Float32/Float64 有不同 width/rounding；negative zero、subnormal 和精确 bit pattern 不能可靠由普通 JSON number 表达。
- Decimal 的 precision/scale 属于 schema，payload 是 canonical decimal text；普通 language decimal object 不是跨语言 contract。
- Binary/`BIT(n)` 必须保留 leading zero bits；不能用字符串猜测 bytes。
- DATETIME、TIMESTAMP 和 TIME duration 的 semantic kinds 不同；不能由宿主 datetime class 推断。
- Anomaly 需要 post-unquote/unescape、pre-coercion logical raw bytes；SQL token 本身又属于 SourcePackageArtifact，而非 Shared Kernel。

因此推荐把 executable coverage 分成三个边界：

1. `normalize_logical_literal` vectors：输入 canonical declared-type descriptor + test-only logical literal/raw-byte union，验证 normalization 或 stable error code。
2. `encode_typed_scalar` vectors：输入 canonical declared-type descriptor + language-neutral typed value union，验证 payload bytes 和完整 scalar frame。
3. Arrow mapping conformance：不放进 Shared Kernel vector schema；由 walking-skeleton/capability owner 的 Arrow schema fixture 验证 Arrow physical type/null bitmap/metadata 如何映射到同一 typed scalar semantics。

一个示意 case（字段名仍待下一步精确化）：

```json
{
  "case_id": "scalar.signed-integer.leading-plus",
  "operation": "normalize_logical_literal",
  "declared_type": {"kind": "signed-integer", "bits": 32},
  "input": {"kind": "utf8-logical-literal", "text": "+001"},
  "expected": {
    "typed_value": {"kind": "signed-integer", "decimal": "1"},
    "scalar_frame_base64url": "..."
  }
}
```

该 union 是 test-only oracle representation，不得直接成为 production FFI DTO。

#### 是否优先考虑程序性能

不应以 vector JSONL 的读取或 union 分派性能为优先，原因是 normative vectors 是小规模 CI/review 资产，不是 production data plane。这里的优先级应为：

```text
byte semantics 完整、确定、可诊断
  > ownership 清晰
  > validator 简洁
  > vector 解析速度
```

但必须优先固定“有利于性能的正式边界形状”：

- Production bulk data 走 Arrow C Data/Stream 或等价零/受控拷贝边界。
- 一次 FFI 处理一个 batch/stream，不逐 scalar 调用。
- Rust 直接读取 Arrow buffers/null bitmap，计算期间释放 GIL。
- Test-only lexical union 只用于 oracle，不迫使 production Arrow path 重放 text parsing。
- Phase 1 验收性能是结构性证据（无 Python row materialization、FFI call granularity、GIL release、bounded batch memory），不是尚无 accepted baseline 的吞吐数字。

这既不牺牲正确性，也避免 vector schema 把正式实现锁进慢路径。

### 9.3 Q4：Manifest、golden envelope 与 payload 的场景

三层对象解决三类不同问题：

```text
scenario manifest
  owns execution identity, inputs, required profiles and closure
        |
        v
golden envelope
  binds expected asset to one semantic owner/contract/schema/comparison mode
        |
        v
golden payload or artifact closure ref
  contains the actual stable expected facts/bytes identity
```

#### 场景 A：Structured data golden

例如 row digest 或 comparison facts。`expected[]` 指向 `expected/result.golden.json`；envelope 声明 Shared Kernel/Comparison owner、contract version、payload schema、`exact-canonical` comparison 和 `content_digest`，小型 JSON payload 直接内联。Runner 对 actual observation 做同一 schema validation 和 JCS compare。

#### 场景 B：Artifact golden

例如 RepositoryImportArtifact/Parquet。二进制或多文件 closure 不内联。Envelope 声明 artifact content owner、media/schema、comparison mode 和 semantic `content_digest`，再引用每个 payload asset 的 path/size/`raw_sha256`。Runner 比 schema、semantic digest 和 closure；不把 Parquet/IPC serializer 的偶然 byte layout 当成业务 digest，除非内容 owner明确规定 exact bytes。

#### 场景 C：Recovery golden

Envelope 的小型 structured payload 内联 `after_failure`、`after_recovery` checkpoints 和 stable final facts/evidence projections。Host path、PID、trace、随机 timestamp、log、stack 和数据库 dump 不进入 payload。Harness 返回 observations；runner 按 envelope 的 checkpoint schema/comparison 比较。

#### 推荐的 manifest expected entry

```yaml
expected:
  - logical_name: result
    kind: structured
    path: expected/result.golden.json
    size_bytes: 1234
    raw_sha256: sha256:...
    contract_binding:
      owner: comparison
      contract_id: gateway-vnext.comparison-facts
      semantic_version: 1.0.0
    content_digest: sha256:...
```

Envelope 重复 `kind`、contract binding 和 `content_digest`，并必须完全匹配。该重复是 Accepted formal 已要求的离线 manifest binding 与 envelope semantic binding，不是两个 owner：

- Manifest copy 让 closure/profile dispatch 在加载 payload 前即可验证 expected identity。
- Envelope copy 让 golden 离开某个 scenario manifest 后仍是自描述、可审查资产。
- 不一致一律是 `HARNESS_ERROR`，不能选择其中一个覆盖另一个。

#### Inline/ref 建议

- Structured/recovery 的小型 JSON payload 内联，减少无意义的小文件和 ref 层。
- Binary、Parquet/Arrow、多文件或接近 closure size limit 的 payload 必须使用 explicit closure refs。
- 不提供任意“inline 或 ref 都行”的自由选择；由 golden `kind` 和 size policy 决定，避免同一语义出现两种随意布局。
- Envelope 的 `content_digest` 只覆盖 semantic payload descriptor/content，避免自引用；manifest 的 `raw_sha256` 覆盖完整 envelope bytes；`fixture_content_digest` 再覆盖整个 scenario closure identity。

推荐接受 R4 的两层引用模型，并采用上述 kind-driven inline/ref 规则。

### 9.4 Q5：为什么需要三个 schema version 字段

三个字段分别版本化三种不同结构，不能用一个 `version` 或目录 `v1/` 代替：

| Field | 出现位置 | Owner | 改变时机 |
| --- | --- | --- | --- |
| `manifest_schema_version` | `scenario.yaml` | Conformance Harness | manifest 字段、closure/self-exclusion、profile/fault 描述结构变化 |
| `vector_set_schema_version` | `vector-set.json` | Shared Kernel vector governance | vector-set closure 和 JSONL case envelope结构变化 |
| `golden_envelope_schema_version` | 每个 golden envelope | Conformance Harness | owner binding、payload descriptor、comparison mode 或 envelope framing变化 |

这些都只是 container/schema structure version，不替代：

- `canonical_encoding_version`：JCS/scalar/framing/digest bytes。
- `semantic_version`：scenario expected payload 所绑定 contract 的业务/计算语义。
- Artifact/Arrow/Parquet owner schema version。
- Provider implementation version。

例子：

- Rust 内部优化但 bytes 不变：只变 provider version，三个 schema version 都不变。
- Comparison facts 新增有语义字段：变 Comparison semantic contract version 和 golden；不必变 manifest/envelope structure version。
- Golden envelope 新增一种 comparison descriptor：变 `golden_envelope_schema_version`；不必改变 scenario manifest schema，除非 manifest entry 也变。
- Scenario 增加新的 required fault-plan 结构：变 `manifest_schema_version`；canonical encoding 不变。
- Scalar frame tag/bytes 改变：变 `canonical_encoding_version`；不是靠 bump vector-set schema 掩盖 byte contract breaking change。

`fixture_manifest_schema_version` 保留为文档中的完整版本轴名称；实例 wire field 固定为 formal 已列出的 `manifest_schema_version`。这样不需要在同一 manifest 中保存两个同义字段。目录中的 `v1/` 仅用于组织和离线一致性检查，不能单独成为 version authority。

推荐接受 R5。下一步 formalization 时应在 Contract Taxonomy 与 Fixture Contract 中补一句上述命名映射，消除实现歧义。

## 10. 第二轮决定（已接受）

1. 是否接受 9.1 的修订 R1：受限 YAML authoring + JSON Schema structural validation + 命名 semantic validators + JCS equality/digest？
2. 是否接受 9.2 的修订 R2：logical-literal normalization、language-neutral typed scalar encoding、owner-owned Arrow mapping 三层分离，并明确 vector 性能不作为优化目标？
3. 是否接受 9.3 的修订 R4：manifest entry 指向自描述 golden envelope，由 kind/size policy 唯一决定 inline 或 closure ref，重复 binding 必须一致？
4. 是否接受 9.4 的 R5 版本轴和 wire-field 命名？

答复：用户接受以上全部建议。本组问题已 Resolved。

## 11. Phase 0 详细记录与 formal authority 核对

Phase 0 临时讨论稿中的部分旧形状已被后续 Accepted formal 改写：

- 临时稿曾不在 manifest 保存独立 `track`，Accepted Fixture Contract 明确要求 `track`。
- 临时稿曾由 suite config 单独拥有 profile selection，Accepted Fixture Contract 明确要求 manifest 声明 `required_profiles[]`。
- 临时稿曾把 `expectations[]` 本身作为唯一 public envelope，并让 expected 文件只保存 owner payload；Accepted Fixture Contract 明确要求 manifest `expected[]` 与自描述 golden envelope 都声明 contract binding/comparison/content identity。

这些属于 temporary 到 formal 的已完成演进，不是正式文档内部冲突。依据 `formal/README.md` 的权威规则，本轮以 Accepted owner contract 为准，不恢复旧临时形状。

Phase 0 临时稿中未被 formal 改写、且与本轮直接相关的固定原则继续作为设计证据：

- Runner 不解释业务语义，owner harness 只调用 public entrypoint 和 typed observer。
- Golden comparison 顺序是 resolve owner contract、validate expected/actual、owner canonicalize、exact compare、独立重算 digest。
- Required profile cell 未运行或非 `PASSED` 时 suite 失败；`UNSUPPORTED` 不是 pass。
- Recovery 只有一个 primary fault、两个 checkpoints 和固定 production recovery trigger，不扩张任意 action DSL。
- Stable-read barrier 不推进状态；logical clock 与 runner deadline 分离。

## 12. Runner/harness contract 推荐（已接受）

### R6. Schema-neutral protocol，Phase 1 使用 in-process registry

Runner/harness protocol 的 request、support decision、observation 和 failure 都定义为 language-neutral、versioned schema；但 Phase 1 的实际 dispatch 使用 Python in-process registry：

```text
runner core (Python)
  -> resolve (track, subject)
  -> Python SubjectHarness adapter
       -> Python reference/application facade
       -> PyO3/Rust capability facade
       -> Repository public client when its phase exists
```

不在 Phase 1 建立跨语言 plugin ABI、subprocess JSON-RPC、动态 module import、entrypoint string 或独立 harness service。Rust provider 通过 capability facade 被 harness 调用；Repository 通过 public client 被 harness 调用。Protocol schema 保持可序列化，未来 process runner 可以复用，但当前不提前建设 transport。

推荐理由：fixture/oracle 必须语言中立，不代表 harness extension mechanism 也必须第一版跨进程；后者会提前引入部署、认证、streaming、timeout 和 plugin compatibility。

### R7. Runner 固定 lifecycle，harness 提供关闭集能力

Runner 拥有不可扩展为任意 workflow 的固定 lifecycle：

```text
validate closure/contracts
  -> preflight support
  -> provision isolated profile
  -> harness seed through public setup contract
  -> arm one fault when declared
  -> harness invoke production entrypoint
  -> stabilize and observe final/after-failure
  -> drive declared production recovery when required
  -> stabilize and observe after-recovery
  -> runner validate/canonicalize/compare/recompute
  -> evidence packaging
  -> teardown/disarm
```

SubjectHarness 只实现以下关闭集：

```text
preflight(plan_descriptor) -> SupportDecision
seed(run_context, input_refs) -> SeedReceipt
invoke(run_context, typed_stimulus) -> InvocationReceipt
stabilize_and_observe(run_context, observation_point, observation_requests)
  -> ObservationSet + StableReadReceipt
drive_recovery(run_context, typed_recovery_trigger) -> RecoveryReceipt
cleanup_subject(run_context) -> CleanupReceipt
```

不允许 manifest 或 harness 注册任意 phase/callback/action list。`drive_recovery` 仅 recovery track 合法；data/command 不暴露该阶段。Invocation receipt 只证明调用发生，不裁定业务结果。

### R8. Harness 不接收 golden payload，也不返回 pass/fail

Runner 向 harness 传递：

- Execution identity、profile/provider、fixture digest、logical time/seed。
- 已验证的 read-only input asset refs/resolver。
- Typed stimulus/fault/recovery descriptors。
- Observation request：`expectation_id + kind + contract binding + payload schema/comparison descriptor`。

Runner 不传递 expected payload、expected `content_digest` 或 golden path。Harness 返回与 observation request 一一对应的 actual `ObservationEnvelope`：

```text
expectation_id
observation_point
contract binding
payload media/schema/version
canonical_encoding_version
actual content_digest
inline actual payload or runtime artifact closure ref
stable diagnostic codes optional
```

Harness 不返回 `PASSED` 或 `ASSERTION_FAILED`。只有 runner 读取 golden、校验 expected/actual、调用 owner canonicalization 并 exact compare，才能产生 correctness status。生产 use-case rejection、business failure 或 anomaly 都是 schema-valid observation，不是 harness failure。

Runner 要求 observation set 与请求集合严格相等：missing、duplicate、unexpected observation 均为 `HARNESS_ERROR`。

### R9. Input asset 使用 verified resolver，不把 host path 变成 contract

Harness 不接收 fixture root 或任意 filesystem path，也不能自行扫描 scenario 目录。Runner 在执行前完成 closure/size/`raw_sha256` 校验，并只暴露：

```text
logical_name
media_type
size_bytes
raw_sha256
owner content_digest when applicable
opaque read handle / verified stream resolver
```

本地 in-process 实现可以把 opaque handle 映射为只读文件或 stream，但 host path 不进入 protocol DTO、golden、result 或 reproduction identity。Harness 读取未声明 asset 或在运行中发现额外 fixture 文件必须失败。

### R10. Support/result 与 failure precedence

`UNSUPPORTED` 只允许由无副作用的 `preflight` 返回，并必须带 stable reason code。开始 provision/seed 后发现能力缺失是 `HARNESS_ERROR`，不能回退为 `UNSUPPORTED`。

推荐最终 status 判定：

```text
preflight unsupported
  -> UNSUPPORTED

无法形成可信 observation / schema-contract resolution / fault-barrier / isolation 失败
  -> HARNESS_ERROR

可信 observation 与 golden 不同，且 cleanup 完整
  -> ASSERTION_FAILED

可信 observation 与 golden 相同，且 cleanup 完整
  -> PASSED

comparison 已完成，但 fault/process/resource cleanup 泄漏
  -> HARNESS_ERROR final status
     + comparison_outcome 保留 MATCH/MISMATCH
```

理由：cleanup 泄漏会污染后续 execution，最终结果不能宣称 correctness pass/fail 环境可信；但 result/evidence 必须保留已经形成的 comparison outcome，避免覆盖原始语义证据。Evidence packaging 的非关键附件失败不改变已有 `ASSERTION_FAILED`，记录为 secondary diagnostic；关键 identity/observation evidence 无法保存则是 `HARNESS_ERROR`。

自动 retry 禁止。显式重跑创建新的 execution identity，第一次结果和 evidence 保留。

### Protocol identity 建议

每次执行的稳定组合键为：

```text
scenario_id
profile
provider_id nullable
fixture_content_digest
```

`run_id` 只用于隔离和 evidence correlation，不进入 golden。`provider_id` 对 `provider-matrix` 必填；其他 profile 仅在 suite 明确选择 provider 时填写，不能由 harness 隐式猜测。

## 13. 第三轮问题：runner/harness authority

1. 是否接受 R6：protocol schema language-neutral，但 Phase 1 registry/dispatch 使用 Python in-process adapter，不建设跨进程 plugin ABI？
2. 是否接受 R7：runner 固定 lifecycle，SubjectHarness 只提供关闭集 `preflight/seed/invoke/stabilize_and_observe/drive_recovery/cleanup_subject`？
3. 是否接受 R8：harness 不读取 golden payload、不返回 correctness status，只返回严格一一对应的 actual observation envelopes；runner 唯一负责 compare？
4. 是否接受 R9：harness 只通过 verified asset resolver 读取 manifest-declared closure，不把 host path 或 fixture root 作为 protocol contract？
5. 是否接受 R10：`UNSUPPORTED` 仅限 preflight；cleanup/isolation 泄漏最终为 `HARNESS_ERROR`，但保留 comparison outcome 和 secondary evidence？

答复：用户接受 R6–R10。本组问题已 Resolved。

### 三轮收敛检查

- Vector/schema authority、digest layers、golden layering、runner/harness authority 已确认。
- 未发现 Accepted formal 内部业务语义冲突。
- Runner/harness 不再存在会改变架构的阻塞问题。
- 剩余架构级问题仅为 Arrow/PyO3 walking skeleton 的正式 capability shape，以及由全部决定导出的 Phase 1 验收矩阵。

## 14. 锁定依赖能力核对

仓库锁定的 `pyo3-arrow 0.19.0` 已提供：

- 通过 Arrow PyCapsule/C Data/C Stream 在 Python 与 Rust Arrow objects 间转换。
- `PyRecordBatchReader` 对应 `__arrow_c_stream__`，输入不要求整表 materialize。
- Rust `RecordBatchReader + Send` 可导回 `pyarrow.RecordBatchReader`。
- PyO3 计算区域可以使用 `py.detach` 释放 GIL。

因此 Phase 1 不需要通过 `to_pylist()`、Python list 或逐列 Python callback 建立边界。当前 demo 的 `to_pylist()` 路径应在实现阶段被正式 walking skeleton 取代。

## 15. Arrow/PyO3 walking skeleton 推荐（已接受）

### R11. 首个 kernel 是 canonical row-hash multiset，不保留 doubling demo contract

正式 walking skeleton 只发布一个 production-shaped Rust batch operation：

```text
canonical_row_hashes_v1
```

固定语义：

1. 输入一条 Arrow RecordBatch stream 与 JCS `CanonicalTableRequest`。
2. 按 request 的 declared semantic schema 校验 Arrow physical schema。
3. 使用 Shared Canonical Encoding v1 生成每行 canonical `row_frame` 与 raw row hash。
4. 将 raw 32-byte row hashes unsigned lexicographic sort，保留重复。
5. 计算 schema digest、row count 和 unordered `raw_content_digest`。
6. 输出按 hash 排序的 Arrow row-hash stream，以及 compact JCS result metadata。

输出 Arrow schema 第一版只有：

```text
row_hash: fixed_size_binary(32), non-null
```

该输出能被后续 standard hash diff、digest、artifact 和 cross-provider conformance 复用。Doubling nullable integer 只保留为已完成环境证据，不成为 contract、fixture subject 或长期 API。

选择该 kernel 而非 identity echo 的理由：它真正执行 Phase 3 首批候选中的 scalar/row/table digest；选择它而非 projection/comparison，是因为后两者需要尚未由各 capability owner 收口的业务 schema。

### R12. Formal native boundary 是 stream + JCS bytes

Python facade 可以接受 `RecordBatch`、`Table` 或 `RecordBatchReader`，但进入 native adapter 前必须统一为 `pyarrow.RecordBatchReader`。正式 PyO3 entrypoint 形状为：

```text
canonical_row_hashes_v1(
  request_jcs: bytes,
  input: Arrow C Stream
) -> (
  output: Arrow C Stream,
  result_jcs: bytes
)
```

约束：

- 一次 native call 消费一条 table stream，不按 row/scalar/column 重复 FFI。
- `request_jcs` 必须已经 schema validate 并是 JCS bytes；Rust 再次 fail-closed validate contract/version。
- Input/output 通过 owned `PyRecordBatchReader`/Arrow C Stream transfer，不调用 `to_pylist()` 或 Python iterator callback。
- Rust 在导入 schema/capsule 后释放 GIL，完成 stream consumption、row encoding、hash/sort/digest；导出 Python Arrow object 时重新取得 GIL。
- 不承诺“整个 operation 零拷贝”：输入 Arrow buffers 可以零拷贝导入，row-hash 输出必然分配新 buffers；任何必要 copy 必须发生在 Arrow/native 层并可观测，不得物化 Python rows。
- Single `RecordBatch` convenience wrapping 属于 Python facade，不形成第二个 native overload contract。

#### R12 性能风险核对

基于仓库锁定的 PyArrow 25.0.0 做了只读结构/微开销核对：

- `RecordBatchReader.from_batches(schema, [batch])` 往返后的 validity/data buffer address 与原 batch 相同。
- 两个 chunk 的 `Table.to_reader()` 产生两个 batch，各 data buffer address 与原 chunk 相同。
- 本机 wrapper creation 观测中，10 rows 与 1,000,000 rows 处于同一微秒以下量级；该数字只证明成本不随 row count 线性增长，不建立任何正式 latency gate。

因此 wrapper 本身主要创建 reader/capsule/schema metadata view，复杂度接近 schema + batch/chunk 数，而不是 row 数；不会复制整表 payload。真正风险来自：

1. 大量极小 batch 导致 C Stream `get_next`、schema check 和 kernel loop 固定成本被放大。
2. 接受任意 Python generator/iterator 作为 stream producer，可能在每个 batch 回调 Python 并重新争用 GIL。
3. 为减少 chunk 数自动调用 `combine_chunks()`，会产生完整 data copy 和额外峰值内存。
4. 在 facade 中调用 `to_pylist()`、`to_pydict()`、逐 row validator 或 Python-side scalar normalization。
5. 重复包装/重复消费同一 one-shot reader，造成生命周期错误或隐藏 materialization。

R12 因此修订为：

- Formal fast path 只接受 PyArrow/Arrow-compatible C Stream exporter，不接受任意 Python generator 作为 production bulk provider。
- `RecordBatch` 使用单 batch reader view；`Table` 使用保留现有 chunks 的 `to_reader()`；不自动 `combine_chunks()`。
- Native ABI 仍只有 stream 形状，不为节省亚微秒级 wrapper 创建建立第二个 batch overload。
- Component evidence 记录 `batch_count`、rows-per-batch distribution、C Stream import/export 和 Python materialization count；batch sizing 是 execution policy，不进入 semantic digest。
- 若未来 accepted vNext baseline 证明 tiny-input wrapper/stream overhead显著，再在不改变 capability semantics 的前提下评估 adapter fast path；Phase 1 不预优化。

`CanonicalTableRequest` 最小语义字段：

```text
request_schema_version
contract_id / semantic_version
canonical_encoding_version
arrow_mapping_schema_version
declared_table_schema
```

Execution resource limits、thread count、provider build version 不进入 semantic request/digest，由 execution policy/config 拥有。

Result metadata 最小字段：

```text
result_schema_version
contract/version markers
canonical_encoding_version
arrow_mapping_schema_version
table_schema_digest
row_count as schema-declared decimal string
raw_content_digest
diagnostics[]
```

### R13. Arrow mapping v1 覆盖全部 canonical scalar kinds，最小化 operation 而非删减类型

推荐 Phase 1 固定完整 Arrow mapping v1，而不是只支持当前 demo 的 nullable `int64`：

| Canonical semantic kind | Arrow physical type |
| --- | --- |
| null | 任一 declared nullable field 的 validity bitmap |
| boolean | `bool` |
| signed integer | `int8/int16/int32/int64` + declared width |
| unsigned integer | `uint8/uint16/uint32/uint64` + declared width |
| decimal | `decimal128/decimal256(precision, scale)` |
| float32/float64 | `float32/float64` |
| string | `utf8` |
| binary / `BIT(n)` | `binary` + declared semantic kind/bit width |
| date | `date32` |
| datetime civil | `timestamp[us]` without timezone |
| timestamp instant | `timestamp[us, UTC]` only |
| time duration | `duration[us]` |
| source literal anomaly | `binary` containing schema-valid JCS envelope + declared anomaly semantic kind |

第一版拒绝 `large_utf8`、`large_binary`、dictionary、union、list/struct/map、non-UTC timestamp timezone、纳秒精度和 Arrow extension type；需要时由 Arrow mapping schema version治理。

Arrow field metadata 不是 semantic authority。Declared semantic schema 只来自 JCS request；Arrow field name/type/nullability 与 request 必须 exact cross-check。Field input order 不参与 row identity，CanonicalIdentifier collision 失败。

推荐完整映射的原因：Shared Canonical Encoding v1 的所有 scalar kinds 本来就是 Phase 1 executable contract，Rust core也必须通过它们的 vectors。只做 `int64` 会把最危险的 decimal、civil/instant、binary/anomaly mapping 推迟，并使首个 kernel 无法成为 Phase 3 复用基础。最小化应体现在“一个 kernel、一个 stream boundary、一个 mapping version”，而不是建立残缺的 v1 type semantics。

### R14. Rust 不拥有 ArtifactRef；Python artifact boundary 保存 Arrow IPC stream

Rust core/adapter 返回 Arrow row-hash stream + compact result metadata，不接收 filesystem/object-store locator，也不创建 `ArtifactRef`。

Python facade 将 output stream 交给 ArtifactStore adapter：

```text
Rust output Arrow stream
  -> Arrow IPC stream writer
  -> ArtifactStore
  -> ArtifactRef
  -> reopen/verify/decode
  -> recompute schema/content digest
```

Phase 1 最小 `ArtifactRef` 只表达 Artifacts owner 已允许的 envelope：logical reference、media type、size、`raw_sha256`、content contract/version、schema marker、semantic `content_digest` 和 location-independent locator。它不包含 host path。

两种 identity 必须分离：

- IPC bytes 的 `raw_sha256` 用于存储完整性与按 ref 恢复。
- Sorted row-hash multiset 的 `raw_content_digest` 用于 semantic equality。

PyArrow/Rust/版本或 batch chunking 造成不同 IPC bytes 时，不应导致 semantic mismatch；除非 artifact content owner 未来明确发布 exact IPC byte contract。Phase 1 artifact round-trip 必须验证 size/raw hash、Arrow schema、sorted row hashes 和 semantic digest，而不是只验证文件存在。

### R15. Pure-compute failure envelope 与结构性性能证据

Native adapter 对 deterministic contract/schema/Arrow/canonical failures 返回一个 versioned `ComputeFailureEnvelope`，至少包含：

```text
failure_schema_version
stable code
stage: request | arrow-import | schema | canonicalize | compute | arrow-export
effect: none
retry classification
sanitized diagnostics[]
```

Python exception class 只是 facade mapping，不是 normative contract；stable code/envelope 才是。Rust panic 必须在可恢复边界被捕获并映射为 `NATIVE_PANIC`。Allocator abort、segfault 或其他无法在进程内捕获的 native termination 不能伪装为普通 exception；Phase 1 记录为 worker/process failure evidence，完整 takeover 属于 Operation/production crash phase。

Phase 1 不设置尚无 accepted vNext baseline 的吞吐数字，但必须取得结构性 component evidence：

- Native entrypoint 一次调用消费多 batch stream。
- 无 Python row/list/dict materialization。
- Rust compute/sort/digest 主区间释放 GIL。
- Input batch partition、field order 和 serial execution 不改变 formal bytes/digests。
- Memory evidence 至少分离 input Arrow buffers、row-hash vector/sort 和 output IPC materialization；不宣称 constant memory。
- Panic、invalid schema、unsupported Arrow type、digest mismatch 和 corrupt artifact 都产生确定分类。

Timeout/cancellation API、Rayon 并行、external sort、SIMD、Parquet 和独立 Rust worker 不进入 walking skeleton 最小边界。

## 16. 第四轮问题：Arrow/PyO3 最小边界

1. 是否接受 R11：首个正式 kernel 为 reusable `canonical_row_hashes_v1`，输出 sorted row-hash stream + table digest，不保留 doubling demo contract？
2. 是否接受 R12：正式 native boundary 统一为 one Arrow C Stream + JCS request/result bytes；单 batch/table 只由 Python facade 包装？
3. 是否接受 R13：Arrow mapping v1 一次固定全部 canonical scalar kinds，但拒绝复杂/large/dictionary/extension types；以“一个 operation”控制 Phase 1 范围？
4. 是否接受 R14：Rust 不创建 ArtifactRef；Python ArtifactStore 持久化 Arrow IPC，并严格分离 raw IPC hash 与 semantic table digest？
5. 是否接受 R15：failure 使用稳定 envelope，Phase 1 只验结构性性能/GIL/materialization evidence，不设 numeric throughput gate，也不引入 timeout/cancel/parallel/external-sort？

答复：用户接受 R11–R15。本组问题已 Resolved。

## 17. Phase 1 验收矩阵推荐（已确认）

### R16. 分离 PR gate、Phase-exit gate 与 deferred gate

推荐三个层次：

| Gate class | 运行条件 | 失败影响 | 内容 |
| --- | --- | --- | --- |
| `PR-CORRECTNESS` | 每个相关 PR；离线、确定、无外部网络 | 禁止合入 | schema/closure、vectors、runner contract、architecture、Python/Rust/Repository unit/conformance |
| `PR-NATIVE` | 每个相关 PR；Linux x86_64 glibc | 禁止合入 | release wheel build/import、Arrow C Stream、PyO3 integration、GIL/failure/artifact round-trip |
| `PHASE-EXIT-CONTAINER` | phase exit candidate exact commit | 不一定阻断所有普通 PR，但禁止宣布 Phase 1 complete | pinned image build、container smoke、Compose、wheel-in-image、immutable build identity/evidence |

Phase ledger 可以把外部 registry/network 故障记为 `BLOCKED`，但它不是 runner 的第五种 result，也不能被当成 pass。Phase exit 只接受 exact commit 的 `PASS`；现有 `Partially verified` 环境台账不能作为最终退出证据。

以下明确 deferred，不伪装为 optional Phase 1 pass：

- 完整 OS/architecture wheel matrix。
- 真实 process-crash/takeover journey。
- Numeric throughput/latency baseline 和收益声明。
- Rayon/parallel、timeout/cancel、external sort、Parquet、独立 Rust worker/service。
- Phase 2 Repository transport/Dolt integration。

### R17. 三方直接消费 vectors，但只要求两份独立实现

| Consumer | Gate | 独立实现要求 |
| --- | --- | --- |
| Backend Python Shared Kernel | 全部 valid/invalid case，完整 bytes/error code | 独立 reference implementation |
| Rust compute core | 全部 valid/invalid case，完整 bytes/error code | 独立 production-shaped implementation |
| Repository Service consumer | 从唯一 vector root 加载同一 case set，调用 Repository-owned conformance entrypoint | 可以复用 owner-published Python Shared Kernel package，不要求复制第三套算法 |
| Cross-consumer aggregate | case ID set、success/error classification、bytes/digests 必须一致；zero skip | 不拥有实现 |

“直接消费”定义为 Repository test 自己发现/校验 `vector-set.json` closure 并逐 case 调用可部署依赖路径；只读取 Backend 的测试报告、复制 aggregate JSON 或只比最终 digest 不算直接消费。

Vector candidate bless 仍要求人工审查 + Python/Rust 两个独立实现验证。强制 Repository 再写第三份 Python encoding algorithm 会制造同语言分叉，不增加足够独立性，因此不推荐。

### R18. Phase 1 required scenario/profile matrix

Phase 1 不伪造尚无 owner/public entrypoint 的 business command/recovery scenario。推荐矩阵：

| Material | Reference | Integration | Provider matrix | Process-crash |
| --- | --- | --- | --- | --- |
| Canonical encoding normative vectors | Python 全量 | Repository consumer 全量 | Python/Rust 全量逐 bytes | 不适用 |
| Canonical row-hash formal data scenario | Python reference 全量小场景 | Python facade → PyO3 Rust → IPC ArtifactRef/reopen 全量关键场景 | Python/Rust 对全部 Arrow mapping cases | 不列入 required profiles |
| Manifest/golden schema conformance samples | data/command/recovery valid+invalid schema fixtures | 不建立虚假业务 integration | 不适用 | 只校验 schema/lifecycle contract，不冒充真实 crash |
| Runner/harness self-tests | fake owner harness 覆盖固定 lifecycle/result precedence | walking-skeleton real harness | support/observation comparison | process control protocol unit tests only |

规则：

- 只有 walking-skeleton 的 `data` scenario进入正式 `vnext/fixtures/scenarios/` oracle root。
- Command/recovery manifest 示例和 fake harness 只属于 Conformance Harness 自身 contract tests，不作为业务 golden，也不制造假的 subject owner。
- Walking data scenario 的 manifest `required_profiles[]` 固定 `reference | integration | provider-matrix`；不声明 `process-crash`，因此不产生伪造 `UNSUPPORTED`。
- Required cell 未执行、缺 case、`UNSUPPORTED` 或非 `PASSED` 都使 suite/phase gate 失败。

### R19. Phase 1 完整验收矩阵

| Area | Required assertions | Evidence/gate |
| --- | --- | --- |
| Schema self-validation | JSON Schema 2020-12 dialect/meta-schema；unknown/duplicate fields fail closed | `PR-CORRECTNESS` |
| YAML subset | anchors/aliases/merge/tags/multi-doc/implicit non-JSON scalars拒绝；formatting不改 semantic digest | `PR-CORRECTNESS` |
| Manifest identity | ID/track/subject/path 可逆；path escape/symlink/undeclared asset失败 | `PR-CORRECTNESS` |
| Closure/digests | size/`raw_sha256`、input/fixture digest、自引用排除、structured/raw asset traversal | `PR-CORRECTNESS` |
| Golden envelope | manifest/envelope binding一致；kind-driven inline/ref；owner schema/canonical exact compare | `PR-CORRECTNESS` |
| Vector-set | closure、case ID unique、operation/input/expected schema、candidate mutation policy | `PR-CORRECTNESS` |
| Python/Rust/Repository vectors | 所有 valid完整 bytes；invalid stable code；zero skip；case coverage set一致 | `PR-CORRECTNESS` |
| Runner registry/lifecycle | `(track, subject)` resolve；fixed phases；golden不传给 harness；observation exact set | `PR-CORRECTNESS` |
| Result precedence | 四态、preflight-only unsupported、cleanup override + comparison outcome、no auto retry | `PR-CORRECTNESS` |
| Asset resolver | 只能读取 manifest closure；host path不进入 protocol/result/golden | `PR-CORRECTNESS` |
| Arrow mapping v1 | 每个 canonical scalar kind正向、null、boundary和拒绝 physical types；schema exact cross-check | `PR-NATIVE` |
| Stream invariance | empty/one/multi batch；batch partition、row order、field order不改变 formal table digest；duplicates保留 | `PR-NATIVE` |
| FFI shape | one native call per stream；owned C Stream import/export；无 Python row/scalar FFI | `PR-NATIVE` |
| Materialization | production bulk path禁止 `to_pylist/to_pydict/as_py` row path、auto `combine_chunks`、Python generator；runtime counters/evidence为零 Python rows | `PR-NATIVE` |
| GIL/concurrency | compute/sort/digest期间另一 Python thread可进展；serial repeat完全确定 | `PR-NATIVE` |
| Failure mapping | request/version/schema/Arrow/canonical/panic/unsupported type稳定 envelope；effect none | `PR-NATIVE` |
| Artifact round-trip | IPC write、size/raw hash、schema、sorted row hashes、semantic digest、reopen；corrupt/truncate/mismatch拒绝 | `PR-NATIVE` |
| Artifact identity separation | 不要求不同 provider/chunking IPC raw bytes相同；semantic digest必须相同 | `PR-NATIVE` |
| Architecture | vNext不 import legacy；Rust core不依赖 PyO3/filesystem/ArtifactStore；adapter依赖 core单向；无无主 common DTO | `PR-CORRECTNESS` |
| Builds | frozen Python/Rust locks；fmt/lint/type/unit；release wheel build/import on Python 3.14/Linux x86_64 glibc | `PR-CORRECTNESS` + `PR-NATIVE` |
| Container | pinned toolchain/base、release wheel in image、health/native smoke、Compose config、build identity | `PHASE-EXIT-CONTAINER` |
| Component evidence | versions、input scale/batches、GIL proof、materialization count、input/hash-sort/output IPC memory breakdown | `PR-NATIVE` artifact + phase ledger |
| Governance | human vector review + two independent implementations；no auto bless；blocking decisions resolved | Phase-exit review |

Property/fuzz tests覆盖 frame parser、ULEB128、scalar boundaries和 permutation，但只能补充 static vectors。Phase 1 可以固定 seed/budget 形成 PR gate；长时间 fuzz campaign 不作为每个 PR 的阻塞任务。

### R20. Phase 1 exit decision 不接受语义 waiver

Phase 1 只有同时满足以下条件才可标记完成：

1. `PR-CORRECTNESS` 与 `PR-NATIVE` 在 exit commit 全部通过。
2. `PHASE-EXIT-CONTAINER` 在同一 commit/toolchain/lock identity 上通过，immutable evidence已记录。
3. Required scenario/profile matrix 全部为 `PASSED`，不存在 required `UNSUPPORTED`、missing run 或自动重试覆盖。
4. Python/Rust 两个独立实现验证全部 normative vectors，Repository consumer直接通过同一 root。
5. Walking skeleton artifact 可按 ref 恢复并重新验证 raw/semantic identity。
6. 当前 doubling/`to_pylist()` demo 不再是 public/formal path；若保留历史测试，只能明确标记 bootstrap evidence。
7. Blocking decision register 为空；无 `UNRESOLVED` legacy classification、formal internal conflict 或未分配 owner。
8. 本轮收敛规则已按 ownership 重新写入 formal contract/plan/必要 ADR；temporary 仍保留并标记 Resolved，不直接移动/改名。

不得用 waiver、`xfail`、advisory-only lane、临时减少 vector/profile coverage 或“网络暂不可用”宣布 Phase 1 complete。非阻塞 implementation detail 可以进入 deferred register，但不能改变上述 formal semantics。

## 18. 第五轮问题：Phase 1 验收矩阵

1. 是否接受 R16 的三层 gate：semantic/native 每 PR 阻断，container/image 只在 exit candidate 阻断 Phase 完成，deferred 明确排除？
2. 是否接受 R17：Backend Python 与 Rust 是两个独立 canonical implementations；Repository 直接消费同一 vectors，但复用 Shared Kernel Python package，不复制第三套算法？
3. 是否接受 R18：Phase 1 只发布真实 walking-skeleton `data` scenario；command/recovery 用 schema/fake-harness contract tests，不伪造业务 scenario，process-crash不进入 required profile？
4. 是否接受 R19 的完整验收矩阵及“结构性性能证据、无 numeric gate”的落点？
5. 是否接受 R20：Phase 1 exit 无 semantic waiver；外部 registry/network blocked 可以记录，但不能把 Partially verified 当完成？

答复：用户接受 R16–R20。本组问题已 Resolved；不存在继续改变Phase 1核心架构的阻塞问题，`$grill-me` 访谈收敛。

## 19. 收敛后的需求与设计基线

以下基线区分为：`事实`是Accepted formal或已核对环境；`决定`是用户直接接受或接受本轮建议；`假设`是实施前仍需由环境验证、但不改变架构的前提。

1. **项目目标（决定）**：把Phase 0 Accepted语义变为可执行contract，并以可复用的canonical-row-hash data walking skeleton验证Python/Arrow/PyO3/Rust/Artifact闭环。
2. **用户与使用场景（事实）**：主要消费者是Shared Kernel/capability/Repository实现者、semantic owner、Conformance Harness维护者和CI/phase reviewer；核心场景是跨语言byte conformance、真实data scenario和artifact recovery。
3. **范围内事项（决定）**：normative vector schema、scenario manifest/golden envelope、runner/harness protocol、Arrow/PyO3最小边界、Phase 1验收矩阵。
4. **范围外事项（决定）**：完整业务command/recovery、Repository transport、Operation runtime、完整平台matrix、network compute service和数值性能优化。
5. **核心流程（决定）**：离线validate closure/contracts → runner preflight/provision/seed/invoke/observe → 必要时production recovery → runner canonical compare/digest recompute → evidence/cleanup；native data path是reader → one C Stream call → sorted row hashes/result → IPC ArtifactRef/reopen。
6. **功能需求（决定）**：发布严格vector/manifest/golden/protocol schema；三个consumer共享oracle；两个独立canonical实现；固定runner/harness authority；实现阶段只发布一个正式kernel和一个真实data scenario。
7. **非功能需求（决定）**：fail closed、逐bytes确定、跨batch/row/field order不变、无Python row materialization、GIL release、owner/version可追溯、离线PR correctness可重复。
8. **核心数据与状态关系（决定）**：raw SHA、owner semantic digest和closure digest三层分离；manifest expected与golden envelope重复binding必须相等；harness actual与runner result分离；ArtifactRef envelope与capability artifact content分离。
9. **数据规模与性能约束（决定）**：Phase 1不设numeric gate；以one-call multi-batch、零Python rows、保留chunks、GIL证据和分段memory evidence作为结构性性能要求。Vector解析性能不是production优化目标。
10. **一致性要求（决定）**：Python/Rust valid vectors逐bytes一致、invalid code一致；Repository zero-skip直接消费同一closure；row-hash结果对batch partition/input ordering确定；raw IPC bytes差异不等于semantic mismatch。
11. **权限与安全要求（事实/决定）**：harness只能读取verified declared assets；host path、secret、stack、arbitrary script/SQL/shell和provider-private object不得进入contract/golden；fault control只走test composition/side channel。
12. **部署与运行环境（事实/决定）**：Phase 1首个native gate为Linux x86_64 glibc release wheel/image；container exit evidence绑定exact commit/toolchain/locks；完整OS/architecture matrix延后。
13. **外部接口与依赖（事实）**：PyArrow/Arrow C Stream、PyO3/`pyo3-arrow`、Rust Arrow、JSON Schema 2020-12、YAML 1.2 JSON-compatible authoring、JCS和ArtifactStore boundary。
14. **兼容性与迁移要求（决定）**：canonical/vector/manifest/golden/protocol/Arrow mapping各自版本化；改变既有v1 expected bytes/digest/classification发布v2；当前doubling/`to_pylist()` demo不能成为public/formal path。
15. **边界与失败场景（决定）**：覆盖empty/one/multi-batch、24-bit integer、decimal/temporal/BIT/anomaly、unsupported Arrow type、panic、schema/version mismatch、corrupt/truncated artifact、missing/duplicate observation和cleanup leak。
16. **已确认决策（决定）**：R1–R20全部接受；其中R3及R6–R20为用户直接确认，本轮解释后的R1/R2/R4/R5也已由用户接受。
17. **已排除方案及原因（决定）**：排除full YAML、模糊`value/digest/version`、harness读取golden、任意workflow/plugin ABI、Python object graph FFI、`to_pylist`、自动`combine_chunks`、残缺int64-only正式mapping、Rust拥有ArtifactRef和用numeric benchmark替代正确性。
18. **明确采用的假设（假设）**：锁定Arrow/PyO3依赖在首个平台持续提供C Stream owned transfer与GIL-detach能力；实际实现必须由`PR-NATIVE`重新证明，不能仅引用本轮只读微观察。
19. **延后事项（决定）**：process crash/takeover、timeout/cancel、Rayon/SIMD/external sort、Parquet、worker/service、numeric vNext baseline、完整platform matrix、Phase 2 Repository integration。
20. **主要风险（事实/决定）**：tiny batches放大固定开销；reader one-shot生命周期误用；decimal/temporal/anomaly跨语言分叉；native crash不可包装；IPC raw identity与semantic identity误混；required lane被错误降级；外部registry/network阻塞container evidence。
21. **验收标准（决定）**：R19矩阵全部required cells通过；R20八项exit条件在同一commit满足；无semantic waiver、required `UNSUPPORTED`、coverage缩减、自动重试覆盖或未分配owner。

## 20. 架构建议与 formalization mapping

本轮只有一个明显占优且已接受的架构：Shared Kernel拥有canonical bytes/vectors，Canonical Row Hash capability拥有Arrow mapping/compute DTO/artifact content，Conformance Harness拥有scenario/golden/protocol/compare/result，Artifacts只拥有generic `ArtifactRef`。Python control plane通过一个Arrow C Stream粗粒度调用Rust data plane；不引入第二条object-graph入口或提前建设network/plugin框架。

| 收敛主题 | 正式 owner 文档 |
| --- | --- |
| Canonical bytes、digest-kind registry | `formal/contracts/shared-canonical-encoding.md` |
| Normative vector manifest/cases/errors | `formal/contracts/canonical-encoding-normative-vector-schema.md` |
| Manifest、golden、runner/harness、result/evidence | `formal/contracts/fixture-oracle-and-conformance.md` |
| Canonical-row-hash request/result/failure、Arrow/PyO3、artifact content | `formal/contracts/canonical-row-hash-compute-boundary.md` |
| Ownership与version axes | `formal/contracts/contract-taxonomy-and-ownership.md` |
| PR/native/container gates与Phase 1完整验收矩阵 | `formal/plans/implementation-stages.md` |
| 混合计算、canonical encoding和language-neutral oracle决策理由 | `formal/adr/0001`、`0005`、`0006` |

本文件保留讨论、解释、只读实验和决策接受记录，不作为实现时的第二份normative authority；不得移动或改名代替上述formal文档。
