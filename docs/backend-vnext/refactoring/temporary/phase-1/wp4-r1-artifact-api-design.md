# WP4 R1 — ArtifactRef / Manifest / Identity API Design

状态：R1 design authority（WP4 R1 checkout）

日期：2026-07-23

Authority：

- [Canonical Row Hash Compute Boundary §8](../../formal/contracts/canonical-row-hash-compute-boundary.md)
- [Contract Taxonomy and Ownership §4.6](../../formal/contracts/contract-taxonomy-and-ownership.md)
- [Executable Contracts R14](executable-contracts-and-walking-skeleton-notes.md)
- [WP3–WP5 Checkout Plan §5](wp3-wp5-checkout-plan.md)

Evidence：[wp4-r1-artifact-api-evidence.md](wp4-r1-artifact-api-evidence.md)

---

## 1. Ownership 与依赖方向

```text
Rust compute core / PyO3 adapter
  -> Arrow stream bytes + result JCS
  x  ArtifactRef / locator / retention / filesystem / ArtifactStore

canonical_row_hash capability
  -> CanonicalRowHashesArtifactManifest
  -> content semantics and semantic digest projection

generic artifacts
  -> ArtifactRef / ArtifactManifest envelope
  -> strict JCS codec and technical contract binding
  -> ArtifactStorePort / InMemoryArtifactStore
  -> shared-kernel DigestRef / raw_blob_digest / canonicalize_jcs
```

- Artifacts owner 只拥有通用、location-independent envelope 和 store port。
- Canonical Row Hash capability 拥有 `raw_content_digest`、`table_schema_digest`、Arrow mapping/version markers 与 content codec。
- `ArtifactManifest` 通过 `ArtifactContentManifest` protocol 组合 capability-owned DTO；generic artifacts 包不导入该 capability DTO。
- Rust core 与 PyO3 adapter 不创建或接收 artifact identity，也不拥有 location resolution。

## 2. Logical reference

v1 语法：

```text
gateway-vnext.artifacts/v1/ref/<namespace>/<artifact-id>
```

- `namespace`：lowercase kebab segment，1–63 字符。
- `artifact-id`：lowercase kebab segment，1–128 字符。
- 两段均由 `[a-z0-9]+(?:-[a-z0-9]+)*` 构成。
- logical reference 由调用方稳定分配，不从 raw 或 semantic digest 派生。
- 空 segment、`.`、`..`、反斜杠、percent encoding、NUL、绝对路径、Windows drive/UNC 和 `file:` URI 均不可表达或在解析前被拒绝。

## 3. ArtifactRef v1

| 字段 | 类型 | Owner | Validation |
| --- | --- | --- | --- |
| `artifact_ref_schema_version` | integer | Artifacts | const `1` |
| `logical_ref` | string | Artifacts | §2 语法 |
| `media_type` | string | Artifacts/contract binding | registered exact value |
| `size_bytes` | integer | Artifacts | `0..2^53-1` |
| `raw_sha256` | DigestRef | Artifacts | exact raw-byte integrity |
| `content_digest` | DigestRef | Capability projection | owner-defined semantic identity |
| `content_contract` | object | Artifacts registry | exact contract id/version |
| `content_schema_id` | string | Capability marker | exact registered schema |
| `retention_class` | enum | Artifacts | closed v1 enum |
| `access_metadata` | object | Artifacts | `{resolver: "artifact-store"}` only |

所有字段 required；所有 wire objects 均 `additionalProperties: false`。`access_metadata`
只声明 location-independent resolver protocol，不含 provider、root、path 或 capability/business
identity。

## 4. ArtifactManifest v1

Manifest 含：

- `manifest_schema_version = 1`
- 与 `ArtifactRef` 等价的 envelope projection
- capability-owned、严格关闭的 `content`

Envelope 的 media type、contract id/version、content schema marker 与 semantic
`content_digest` 必须分别绑定 content DTO 的对应投影。R1 不定义 manifest 自身 digest；
formal authority 未要求该 identity，因此没有自引用 closure digest 或新的 shared-kernel
digest kind。Manifest 的确定性 wire 由严格 JCS serialization 保证。

## 5. Canonical Row Hash content v1

Capability-owned DTO 位于
`gateway_backend.canonical_row_hash_artifact.CanonicalRowHashesArtifactManifest`。

| 字段 | Validation |
| --- | --- |
| `content_schema_id` | const canonical-row-hashes artifact schema v1 |
| `media_type` | const Arrow stream media type |
| `raw_content_digest` | exact DigestRef；semantic identity |
| `table_schema_digest` | exact DigestRef |
| `canonical_encoding_version` | const `1` |
| `arrow_mapping_schema_version` | const `1` |
| `contract_binding` | canonical-row-hash boundary / `1.0.0` |
| `result_schema_version` | const `1` |
| `row_count` | canonical unsigned decimal string |

Envelope `content_digest` 必须等于 content `raw_content_digest`。Generic artifacts
只执行声明绑定，不解释 sorted row-hash multiset 语义。

## 6. Identity 与 equality

| 层次 | 投影 | 规则 |
| --- | --- | --- |
| Logical | `logical_ref` | 稳定引用哪个 artifact |
| Raw integrity | `size_bytes`, `raw_sha256` | 覆盖实际存储 bytes |
| Semantic content | contract/version/schema, `content_digest` | capability owner 定义 |

`ArtifactRef` 显式定义 equality/cache key 为完整稳定 wire identity；不使用 dataclass
默认比较、Python `hash()`、时间、随机值或对象地址。`ArtifactManifest` 再组合
capability content 的显式 `identity_key`。Provider、host path、temporary root 和 physical
chunking 不参与任何 identity。

相同 semantic digest 不允许跳过 raw size/hash 校验；不同 raw bytes 也不自动构成
semantic mismatch。

## 7. Strict wire processing

- 输出使用 shared-kernel RFC 8785 JCS canonicalizer。
- 输入先经 shared-kernel strict JCS parser，拒绝 duplicate member、trailing data、
  invalid UTF-8/Unicode、non-I-JSON number。
- 生产 runtime validator 镜像 closed v1 envelope，不依赖 repository-relative schema
  文件或 dev-only `jsonschema`。
- Capability parser 单独验证 content closed schema；DTO 构造再次执行 contract binding。
- Draft 2020-12 JSON Schema 是跨语言 wire authority；测试同时向 schema validator 和
  runtime parser 投入有效/无效变体以防漂移。

## 8. API surface

| 模块 | 职责 |
| --- | --- |
| `artifacts/types.py` | generic DTO、identity projections、path defense |
| `artifacts/contracts.py` | immutable technical contract registration |
| `artifacts/serialize.py` | strict JCS codec、manifest composition |
| `artifacts/digest.py` | raw SHA helper、caller-owned logical-ref builder |
| `artifacts/store.py` | port 与 hermetic in-memory contract implementation |
| `artifacts/validate.py` | production closed-v1 envelope validation |
| `canonical_row_hash_artifact.py` | capability-owned content DTO/codec |

`ArtifactStorePort`：

```python
def put(raw_bytes: bytes, manifest: ArtifactManifest) -> ArtifactRef: ...
def locate(ref: ArtifactRef) -> bytes: ...
def verify_manifest(manifest: ArtifactManifest) -> None: ...
```

R1 的 `InMemoryArtifactStore` 只验证接口和 identity；不提供 filesystem writer/reader。

## 9. Wire schemas

- `vnext/fixtures/schemas/artifacts/v1/artifact-ref.schema.json`
- `vnext/fixtures/schemas/artifacts/v1/artifact-manifest.schema.json`
- `vnext/fixtures/schemas/artifacts/v1/canonical-row-hashes-artifact.schema.json`
- `vnext/fixtures/schemas/artifacts/v1/definitions.schema.json`

## 10. Deferred

- WP4 R2：Arrow IPC write/reopen、LocalArtifactStore 与 raw/semantic identity 复验。
- WP4 R3：corrupt/truncated/mismatch IPC 负向套件。
- WP4 R4：facade → PyO3 → Rust → ArtifactRef → reopen、正式 `gate.sh native` /
  `PR-NATIVE`。
- WP5：scenario YAML、runner、golden 与 container harness。
