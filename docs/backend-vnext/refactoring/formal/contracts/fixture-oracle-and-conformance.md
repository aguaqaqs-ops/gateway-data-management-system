# Fixture Oracle and Conformance Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 1–8 持续执行

Contract ID：`gateway-vnext.fixture-oracle-and-conformance`

Owner：Conformance Harness；scenario expected content 由对应 semantic owner 拥有

Semantic version：`1.0.0`

Manifest schema version：`1`

Golden envelope schema version：`1`

Harness protocol/result/evidence schema version：`1`

## 1. Oracle 权威与不兼容变更

权威顺序为：已接受 formal contract/ADR、人工确认的业务结果、versioned golden fixture、legacy observable behavior。Legacy 仅用于发现旅程、边界 case 和差异，不拥有 vNext 结果，不作为内部结构、目录、状态、provider、cache、Dolt layout 或性能 oracle。

新旧差异必须归类为 `MATCH | OLD_BUG | NEW_BUG | INTENTIONAL_CHANGE | UNRESOLVED`。`UNRESOLVED` 不可自动 bless。正式 intentional change 包括最小持久状态、canonical Dolt、effect-first recovery 和本文语言中立 fixture 体系。

## 2. 根目录与 scenario identity

```text
vnext/fixtures/
  scenarios/
    data/<subject>/<scenario-path>/
    command/<subject>/<scenario-path>/
    recovery/<subject>/<scenario-path>/
  shared/
  vectors/
```

每个 scenario 目录是自包含 closure：

```text
scenario.yaml
input/
expected/
```

Scenario ID 使用稳定 dot notation；物理路径 segment 使用 kebab-case，二者必须可逆一致。ID 至少包含 track、subject 和语义名称，例如 `recovery.submit.timeout-success-journal`；manifest 的 track/subject 必须与路径一致。

不按“最小样本/回归样本”建立目录分类；provenance 表达 handcrafted 或 sanitized regression。Scenario 不继承其他 scenario，不提供模板 DSL、脚本或可执行 hook。共享 immutable asset 只能通过显式 content-digested ref 引用。

## 3. Authoring、schema 与 canonical data model

Schema root：

```text
vnext/fixtures/schemas/
  scenario-manifest-v1.schema.json
  golden-envelope-v1.schema.json
  harness-protocol-v1.schema.json
  runner-result-v1.schema.json
  run-evidence-v1.schema.json
```

所有 schema 使用 JSON Schema 2020-12，固定 `$schema`、stable `$id`，object默认 `additionalProperties=false`。JSON Schema负责结构；Conformance Harness命名 semantic validator负责 ID/path可逆、closure、digest、cross-field、profile/fault legality和size/sanitization policy。

`scenario.yaml` 是 human authoring format，只允许 YAML 1.2 JSON tag-resolution 的 JSON-compatible子集：单一 UTF-8 document、string-key mapping、sequence、string、boolean、null和I-JSON safe finite number。禁止 anchor、alias、merge key、tag/directive、complex/non-string key、duplicate key、multi-document、implicit timestamp、NaN/Infinity和YAML Core扩展 numeric form。Decimal、uint64、binary和temporal使用字段 schema声明的string/typed representation。

YAML whitespace、comment、单双引号和mapping presentation order不进入semantic identity。解析后的JSON-compatible model经schema validate后，使用 [Shared Canonical Encoding](shared-canonical-encoding.md) JCS参与equality/digest。

## 4. Scenario manifest schema v1

Top-level exact shape：

```yaml
manifest_schema_version: 1
scenario_id: data.canonical-row-hashes.mixed-scalars
track: data
subject:
  kind: capability
  name: canonical-row-hashes
description: Stable human description.
provenance:
  kind: HANDCRAFTED
contract_bindings:
  - binding_id: subject
    owner: canonical-row-hash-capability
    contract_id: gateway-vnext.canonical-row-hash-compute-boundary
    semantic_version: 1.0.0
canonical_encoding_version: 1
input_assets: []
stimulus:
  contract_binding_id: subject
  payload:
    storage: inline
    value: {}
input_digest: sha256:...
fixture_content_digest: sha256:...
expected:
  - expectation_id: row-hashes
    kind: structured
    path: expected/row-hashes.golden.json
    size_bytes: 1
    raw_sha256: sha256:0000000000000000000000000000000000000000000000000000000000000000
    contract_binding:
      owner: canonical-row-hash-capability
      contract_id: gateway-vnext.canonical-row-hash-compute-boundary
      semantic_version: 1.0.0
    content_digest: sha256:0000000000000000000000000000000000000000000000000000000000000000
required_profiles:
  - integration
  - provider-matrix
  - reference
legacy_classification: NOT_APPLICABLE
```

示例中的size和digest是shape placeholder，不是normative fixture value。

### 4.1 Identity 与 ordering

- `manifest_schema_version` 必须为 `1`。文档中的完整版本轴名是 `fixture_manifest_schema_version`；它不是第二个 wire field。
- `scenario_id` 第一段、`track`、`subject.name` 与物理 path 必须可逆一致。
- `subject.kind` v1为 `capability | journey`。
- `contract_bindings[]` 以唯一 lower-kebab `binding_id` 标识，按 ID bytes升序；每项必须有唯一 owner、contract ID和semantic version，optional wire schema version只在owner contract声明时出现。
- `input_assets[]` 按 `logical_name` bytes升序；`expected[]` 按 `expectation_id` bytes升序。
- `required_profiles[]` 是unique set，authoring按profile ID bytes升序，v1值为 `integration | process-crash | provider-matrix | reference`。
- `contract_bindings[]`、`expected[]`和`required_profiles[]`各至少一项；`input_assets[]`可以为空。`description`必须是non-empty stable human text，但不作为semantic owner payload。
- Unknown field、unknown enum、duplicate/canonical collision、unsorted declared set/list fail closed。

### 4.2 Input asset 与 stimulus

每个 `input_assets[]`：

```text
logical_name
path xor ref
media_type
size_bytes
raw_sha256
content_binding optional
content_digest optional; must appear with content_binding
```

`content_binding` exact shape为：

```text
contract_binding_id
schema_id
schema_version
canonical_encoding_version optional; only for canonical JSON/structured content
```

它必须引用top-level唯一binding；`content_digest`由该binding的semantic owner定义。Raw/binary asset禁止伪造content binding来把transport bytes提升为业务语义。

`path` 是scenario-local POSIX relative path；`ref` 是 `vnext/fixtures/shared/` 下content-addressed immutable ref。禁止absolute path、`..`、symlink和undeclared file。`raw_sha256`直接覆盖asset bytes；structured owner content可以另声明semantic `content_digest`。

`stimulus` 必须绑定一个 `contract_binding_id`，payload是关闭 union：

```text
{storage: inline, value: JSON-compatible owner payload}
{storage: asset-ref, logical_name: declared input asset}
```

它不允许script、environment substitution、callback、implementation entrypoint或arbitrary action list。

### 4.3 Track conditional fields

- `data`/`command` 禁止 `fault` 和 `recovery_trigger`。
- `recovery` 必须声明第 8 节的一个 `fault` 与一个owner-versioned `recovery_trigger`。
- Command business rejection是owner observation，不通过expected exception或runner timeout表达。
- `legacy_classification` 关闭集为 `NOT_APPLICABLE | MATCH | OLD_BUG | NEW_BUG | INTENTIONAL_CHANGE | UNRESOLVED`；`UNRESOLVED` 阻断 bless/cutover。纯vNext contract使用 `NOT_APPLICABLE`，不伪造legacy差异。

### 4.4 Input 与 fixture digest

计算前必须先验证所有 raw hash/size/closure。Semantic traversal规则：

- Schema-declared structured asset：schema validate后使用owner canonical bytes/content digest。
- Raw/binary asset：使用raw bytes/direct SHA-256。
- Relative path按UTF-8 bytes排序并length-frame；mtime、absolute path、directory enumeration order不参与。

#### Normative byte preimage（authority）

`input_digest` 与 `fixture_content_digest` 的 preimage 由下列算法唯一决定（实现不得另选 framing）：

1. **Projection**
   - `input` projection object：`contract_bindings`（仅 stimulus/fault/recovery 引用的 binding）、`stimulus`、`input_assets`（每项含 `logical_name`；structured 另含 `content_binding` canonical subset 与 owner `content_digest`；raw 另含 `raw_identity` = direct SHA-256 wire form）、以及可选 `fault` / `recovery_trigger`。
   - `fixture` projection object：完整 manifest 的深拷贝，移除顶层 `input_digest` 与 `fixture_content_digest`；structured `input_assets[]` 与全部 `expected[]` 剥离 transport-only `size_bytes`/`raw_sha256`。
2. **Keyed-collection frame**
   - 先追加 entry `(key=UTF-8("manifest"), value=JCS(projection))`。
   - `fixture` 另追加 child entries：scenario-local 非 `scenario.yaml`、非 `expected[]` path 的 input，按 path UTF-8 字节序；identity 为 structured owner `content_digest` 的 32-byte raw，或 raw asset 的 `SHA256(raw bytes)`；再追加每个 golden path，identity 为 envelope `content_digest` 的 32-byte raw。
   - Shared asset 计入 fixture identity（path = shared ref 相对路径），但不计入 scenario-local 1 MiB 体积上限。
   - 使用 Shared Kernel `keyed-collection` framing 编码上述 entries，得到 `collection_frame`。
3. **Digest**
   - `input_digest = semantic_digest("scenario-input", collection_frame)`
   - `fixture_content_digest = semantic_digest("scenario-fixture", collection_frame)`
   - wire 形式为 `sha256:` + lowercase hex。

Normative vectors（`vnext/fixtures/vectors/conformance/scenario-digest/v1/`）固定完整 `collection_frame` bytes；Python 与 Rust 必须独立对同一 frame 复算 digest。

### 4.5 Provenance exact shape

Handcrafted：

```yaml
provenance:
  kind: HANDCRAFTED
```

Sanitized regression：

```yaml
provenance:
  kind: SANITIZED_REGRESSION
  source_reference: non-sensitive-opaque-reference
  sanitization_policy:
    policy_id: owner-registered-lower-kebab
    version: 1
  approval:
    authority: stable-team-or-role
    reference: non-sensitive-approval-reference
```

`source_reference`和approval reference不得允许反查敏感原文；sanitization policy/version和approval必须可在repository governance中验证。除此之外不允许provenance扩展字段。

## 5. Expected entry 与 golden envelope v1

Manifest `expected[]` entry：

```text
expectation_id: scenario-local unique lower-kebab
kind: structured | artifact | recovery
path: scenario-local expected envelope path
size_bytes
raw_sha256
contract_binding: owner + contract_id + semantic_version + optional wire version
content_digest: owner semantic content identity
```

`path` 指向自描述 golden envelope。Envelope exact shape：

```json
{
  "golden_envelope_schema_version": 1,
  "expectation_id": "row-hashes",
  "kind": "structured",
  "contract_binding": {
    "owner": "canonical-row-hash-capability",
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  },
  "payload_descriptor": {
    "media_type": "application/json",
    "schema_id": "gateway-vnext.canonical-table-result.v1",
    "schema_version": 1,
    "canonical_encoding_version": 1,
    "comparison_mode": "exact-canonical"
  },
  "content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "payload": {
    "storage": "inline",
    "value": {}
  }
}
```

示例 digest是shape placeholder。Manifest entry与envelope的 `expectation_id`、kind、contract binding和content digest必须逐字段相等；不一致是 `HARNESS_ERROR`，不能选择一份覆盖另一份。

Manifest expected entry的contract binding还必须逐字段匹配top-level `contract_bindings[]` 中唯一条目；golden不能通过重复binding引入manifest未声明的owner或contract version。

Kind固定storage/comparison：

| Kind | Payload | Comparison |
| --- | --- | --- |
| `structured` | `storage=inline` JSON-compatible owner payload | `exact-canonical` |
| `recovery` | `storage=inline` owner checkpoint/final-facts payload | `recovery-checkpoints` |
| `artifact` | `storage=closure`，value为content-digested artifact closure manifest | `artifact-closure` |

Structured/recovery不支持external arbitrary payload ref；如果内容不适合在scenario 1 MiB limit内inline，semantic owner必须发布artifact contract并使用artifact kind。Artifact不inline binary。第一版不提供regex、subset、ignore list、numeric tolerance、`oneOf`、dynamic sort或“任一输出通过”matcher。

Envelope `content_digest` 由payload semantic owner contract定义，并覆盖contract/schema/canonical version所需identity；Conformance Harness不发明第二套业务digest。Envelope raw bytes由manifest `raw_sha256`验证；formatting可以改变raw hash但不改变schema-valid canonical content digest。

Host path、PID、trace/correlation ID、随机timestamp、log/stack、provider/build metadata和非contract ordering不进入golden。

## 6. Provenance 与材料边界

`HANDCRAFTED` 由最小人工输入组成。`SANITIZED_REGRESSION` 必须记录安全来源标识、sanitization policy/version、审批、不可逆脱敏和预期业务边界；任何敏感原文、内部路径或可逆映射不得进入 Git。

Scenario-local closure 上限 1 MiB；单个 shared correctness asset 上限 5 MiB。超限必须裁剪、拆分或通过评审转为外部 dataset。第一版不使用 Git LFS。

外部 benchmark dataset 不进入 Git scenario closure。每个 dataset 必须有 `dataset.yaml`，固定 safe dataset ID/revision、provenance、validation rules、logical composition/change chain、generator version/seed（如适用）和内容 identity。缺失或 identity 不匹配产生 `HARNESS_ERROR`，不能被当作 pass。

## 7. Runner 与 harness protocol v1

Oracle runner core只负责schema/closure validation、profile lifecycle/dispatch、stable clock/ID、fault/checkpoint control、canonical comparison、result aggregation和evidence packaging。Subject harness registry由subject owner注册public entrypoint/typed observer；manifest不保存语言实现入口。

Protocol DTO使用 `harness_protocol_version=1` 的language-neutral schema。Phase 1实际registry/dispatch是Python in-process adapter；Rust通过capability facade/PyO3调用，Repository通过public client调用。不建立subprocess JSON-RPC、dynamic module/function string、跨语言plugin ABI或harness service。未来transport可以复用DTO，但不是v1 requirement。

### 7.1 Execution identity 与 request

每个execution key：

```text
scenario_id
profile
provider_id nullable; provider-matrix required
fixture_content_digest
```

`run_id` 只用于隔离/evidence correlation，不进入golden。Runner向harness传递validated plan descriptor：execution/subject identity、contract bindings、logical time/seed、verified input asset refs、typed stimulus/fault/recovery和observation requests。

Observation request只包含 `expectation_id + kind + contract binding + payload schema/comparison descriptor`。Runner禁止把expected payload、expected content digest或golden path传给harness。

Serializable request只保存asset metadata/ref；actual `VerifiedAssetResolver` 是run-context只读capability，不持久化。Harness不能接收fixture root、扫描目录或读取undeclared asset；host path不进入DTO/result/golden。

Validated plan DTO关闭shape：

```text
harness_protocol_version
execution_key
run_id
subject
contract_bindings[]
logical_time_start
deterministic_seed
verified_assets[] metadata/ref only
stimulus
fault nullable
recovery_trigger nullable
observation_requests[]
```

`observation_requests[]`按expectation ID排序；plan不含expected payload/digest/path。Profile-owneddeadline、process handle、resolver capability和secret token属于runtime context，不进入serializable plan。

### 7.2 Fixed lifecycle 与 SubjectHarness

```text
validate closure/contracts
  -> preflight support
  -> provision isolated profile
  -> seed through public setup contract
  -> arm one fault when declared
  -> invoke production entrypoint
  -> stabilize_and_observe final/after-failure
  -> drive declared production recovery when required
  -> stabilize_and_observe after-recovery
  -> validate/canonicalize/compare/recompute
  -> evidence packaging
  -> teardown/disarm
```

SubjectHarness关闭集：

```text
preflight
seed
invoke
stabilize_and_observe
drive_recovery recovery-only
cleanup_subject
```

`preflight`只返回：

```text
{harness_protocol_version, support: SUPPORTED, diagnostics: []}
{harness_protocol_version, support: UNSUPPORTED, reason_code, diagnostics: []}
```

其余method成功返回统一receipt header `{harness_protocol_version, phase, outcome: COMPLETED, diagnostics[]}`，再附加owner-schema-validated typed payload；`stabilize_and_observe`另返回stable-read receipt与observation set。基础设施失败返回 `{harness_protocol_version, phase, outcome: FAILED, stable_code, diagnostics[]}`，由runner映射为`HARNESS_ERROR`。Receipt不包含correctness status、expected value或任意未版本化context bag。

禁止custom phase/callback/action list。Invocation receipt只证明调用发生，不判断业务结果。

### 7.3 Actual observation

Harness为每个observation request返回且只返回一个actual envelope：

```text
harness_protocol_version
expectation_id
observation_point
contract binding
payload media/schema/version
canonical_encoding_version
actual content_digest
inline actual payload or runtime artifact closure ref
stable diagnostics optional
```

Missing、duplicate、unexpected observation是 `HARNESS_ERROR`。Harness不读取golden，也不返回 `PASSED/ASSERTION_FAILED`。Runner唯一负责resolve owner contract、validate expected/actual、owner canonicalize、exact compare和independent digest recomputation。Schema-valid business rejection/failure/anomaly是actual observation，不是harness error。

Execution profiles：

- `reference`：小规模 semantic oracle。
- `integration`：真实组件边界与 artifact。
- `process-crash`：进程终止/restart/takeover。
- `provider-matrix`：同 contract 的 Python/Rust/Repository conformance；不用于比较内部实现结构。

### 7.4 Result schema 与 precedence

Runner result schema v1关闭shape：

```json
{
  "runner_result_schema_version": 1,
  "execution_key": {
    "scenario_id": "data.canonical-row-hashes.mixed-scalars",
    "profile": "integration",
    "provider_id": null,
    "fixture_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  },
  "run_id": "opaque-run-id",
  "contract_bindings": [
    {
      "binding_id": "subject",
      "owner": "canonical-row-hash-capability",
      "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
      "semantic_version": "1.0.0"
    }
  ],
  "status": "PASSED",
  "comparison_outcome": "MATCH",
  "expectations": [
    {
      "expectation_id": "row-hashes",
      "expected_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "actual_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "outcome": "MATCH"
    }
  ],
  "evidence_ref": null,
  "cleanup": {"status": "CLEAN", "diagnostics": []},
  "diagnostics": []
}
```

示例digest是shape placeholder。`contract_bindings[]`复制validated semantic/wire versions并按binding ID排序；expectations按expectation ID排序。Per-expectation outcome为`NOT_RUN | MATCH | MISMATCH`，未产生actual时`actual_content_digest=null`。`evidence_ref`为null或test-evidence owner的location-independent ref。Cleanup status为`CLEAN | LEAKED | FAILED`。

`status` 只有 `PASSED | ASSERTION_FAILED | HARNESS_ERROR | UNSUPPORTED`；`comparison_outcome` 是 `NOT_RUN | MATCH | MISMATCH`，保留已经完成的semantic comparison而不增加第五种result。

- `UNSUPPORTED` 只允许无副作用preflight返回stable reason；provision/seed后发现缺能力是 `HARNESS_ERROR`。
- 无法形成可信observation、contract/schema resolution、fault/barrier/isolation失败是 `HARNESS_ERROR`。
- Trustworthy mismatch且cleanup完整是 `ASSERTION_FAILED`。
- Match且cleanup完整是 `PASSED`。
- Comparison已完成但fault/process/resource cleanup泄漏：final `HARNESS_ERROR`，保留 `MATCH/MISMATCH`。
- 非关键evidence附件失败作为secondary diagnostic；关键identity/observation evidence无法保存是 `HARNESS_ERROR`。

只有PASSED可进入性能aggregate。禁止automatic retry覆盖第一次证据；显式重跑产生新execution identity并保留第一次result。

## 8. Fault 与 recovery protocol

Recovery manifest只允许以下typed shape：

```yaml
fault:
  contract_binding_id: subject
  target: owner-declared-logical-target
  boundary: owner-registered-lower-kebab
  action: owner-registered-lower-kebab
  occurrence: 1
  parameters: {}
recovery_trigger:
  contract_binding_id: subject
  kind: owner-registered-lower-kebab
  repetitions: 1
  parameters: {}
```

`occurrence` 与 `repetitions` 是positive safe integer；`parameters` 是对应owner/version schema验证的optional JSON-compatible object，generic manifest schema不解释其业务含义。Fault owner必须发布target/boundary/action legality matrix，recovery owner必须发布kind registry；unknown value或binding/profile组合不合法在执行前产生`HARNESS_ERROR`。Fault envelope禁止exception class、函数/代码行、SQL/shell/path和任意脚本。

Recovery scenario只声明一个primary typed fault；runner先验证该fault对subject/profile合法，再通过test-only side channel arm。Harness必须回报armed/consumed exactly once；未消费或重复消费是`HARNESS_ERROR`。生产request/wire schema不携带fault字段。

每个 recovery scenario 至少有 `after_failure` 与 `after_recovery` checkpoint。断言通过 stable public reads 和 Repository journal/evidence 完成；使用 logical clock/deadline 与 stable-read barrier，不使用固定 sleep 猜测完成。恢复使用生产 restart/reconcile/takeover 入口，不由 runner 篡改数据库或目录。

`RunEvidenceBundle` 是 test-only、content-digested evidence，包含 run/profile/scenario identity、environment/component versions、fault receipt、observations/checkpoint results、diagnostics 和 cleanup status。它不是生产 artifact，也不新增业务状态。

## 9. CI lane

Correctness CI校验manifest、closure、golden、normative vectors和required profile matrix；小规模reference/integration必须在普通CI可重复运行。Phase 1 gate class与exit authority由 Implementation Stages拥有。Process-crash/provider matrix可按真实required profile进入专用lane，但不能对已经声明required的cell永久optional。

External benchmark lane 使用同一 dataset identity、runner result和 correctness gate，但其数字、repository 和 raw evidence 保存在 Git 外。性能发现的 semantic mismatch 必须回流为最小 correctness scenario；benchmark 不能成为唯一正确性测试。

Golden 更新必须显示 candidate diff、owner approval、intentional-change 分类、contract/version/digest 影响；普通测试运行禁止自动 bless。

## 10. Classification 与版本

Module public：是。Persisted：fixture/golden/evidence manifest。Wire：YAML/JCS JSON/owner artifact formats。

Manifest schema、golden envelope schema、harness protocol/result/evidence schema与scenario-bound semantic contract分别版本化。目录变化不能伪装语义兼容；已发布ID不因重排目录而复用为另一场景。

## 11. 验收标准

- 所有 scenario ID、path、track、subject、closure 和 digest 可离线验证。
- 每个 expected asset 只有一个 semantic owner 和显式 contract version。
- Python、Rust、Repository 共享同一 vectors/scenarios；不存在实现语言专属的正式 oracle root。
- Recovery tests 不依赖 sleep、内部代码行或数据库 dump。
- Git fixture 无敏感数据、超限资产或 LFS 依赖。
- Legacy 差异均已分类，`UNRESOLVED` 会阻断 bless/cutover。
- Harness无法读取golden payload或返回correctness status；runner唯一拥有compare/result。
- Required cell未运行、`UNSUPPORTED`或非PASSED会使suite失败。
- YAML presentation、host path、directory order不影响semantic fixture identity。

## 12. 关联文档

- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [Canonical Encoding Normative Vector Schema](canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary](canonical-row-hash-compute-boundary.md)
- [Performance Measurement and Baseline](performance-measurement-and-baseline.md)
- [ADR 0006](../adr/0006-language-neutral-fixture-oracle.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
