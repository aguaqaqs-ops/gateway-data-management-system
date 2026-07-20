# Phase 1 Implementation Design and Delivery Plan

状态：正式实施设计（Accepted）

日期：2026-07-20

适用阶段：Phase 1 — Executable Contracts and Walking Skeleton

Owner：Backend vNext Architecture（交付顺序与工程边界）；具体byte/schema语义仍由关联contract owner拥有

详细范围：WP0–WP2

依赖：

- [Implementation Stages](implementation-stages.md)
- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)
- [Canonical Encoding Normative Vector Schema](../contracts/canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary](../contracts/canonical-row-hash-compute-boundary.md)
- [Fixture Oracle and Conformance](../contracts/fixture-oracle-and-conformance.md)
- [Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)

## 1. 目标、authority 与非目标

本文把Phase 1前三个work package收敛为可直接实现、测试和review的delivery specification：

```text
WP0  Workspace Safety and Reproducible Gates
  -> WP1  Python Reference, Schemas and Candidate Vectors
  -> WP2  Independent Rust Core, Normative Publication and Repository Consumer
```

本文拥有package/crate拓扑、实施顺序、gate、依赖接入时点与交付验收，不重新定义canonical bytes、stable error registry、vector envelope或digest preimage。冲突时以对应owning contract为准，暂停实现并修正文档，不在代码中维持两套解释。

WP0–WP2明确不实现：

- Scenario YAML、golden envelope、runner/harness protocol或scenario registry。
- Arrow mapping、PyO3正式入口、row-hash kernel或ArtifactRef。
- Phase 2 Repository transport/Dolt integration。
- Schema codegen、通用registry、workflow框架或provider hierarchy。
- Numeric performance claim、parallelism、unsafe、nightly或低层优化。

## 2. 固定工程拓扑

### 2.1 Python Shared Kernel

```text
vnext/shared_kernel/
  pyproject.toml
  uv.lock
  .python-version
  src/gateway_shared_kernel/
  tests/
```

- Distribution：`gateway-shared-kernel`。
- Import package：`gateway_shared_kernel`。
- Python：固定3.14.6，独立`uv` project与lockfile。
- Runtime dependency：[`rfc8785==0.1.4`](https://pypi.org/project/rfc8785/0.1.4/)。
- `conformance` optional extra：[`jsonschema==4.26.0`](https://pypi.org/project/jsonschema/4.26.0/)；candidate/vector loader与consumer tests使用，production canonical core不依赖。
- Dev dependencies与现有vNext Python baseline对齐：pytest、Hypothesis、ruff、strict mypy和coverage。

### 2.2 Rust Shared Kernel

```text
vnext/rust/
  Cargo.toml
  Cargo.lock
  gateway-shared-kernel/
    Cargo.toml
    src/lib.rs
    tests/
```

- Cargo package：`gateway-shared-kernel`；library crate：`gateway_shared_kernel`。
- Production dependencies固定为`serde==1.0.229`、`serde_json==1.0.150`、[`serde_json_canonicalizer==0.3.2`](https://docs.rs/serde_json_canonicalizer/0.3.2/serde_json_canonicalizer/)、`sha2==0.11.0`和workspace `thiserror==2.0.18`。
- `base64==0.22.1`、fixture filesystem读取及case dispatch只属于dev/integration-test路径。
- Production crate不得依赖PyO3、Arrow、filesystem、environment、network、process或ArtifactStore。
- `gateway-compute-core`在WP0–WP2不依赖此crate；WP3真正使用canonical primitive时再接入。

### 2.3 唯一共享材料

Python与Rust互不调用、不共享implementation source。两者只共享：

- Accepted formal contracts。
- `vnext/fixtures/schemas/`下的JSON Schema。
- `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/`下的static normative vectors。

Repository Service复用Python Shared Kernel的`conformance` extra，但必须直接发现同一vector root；不得复制fixture或实现第三套canonical算法。

现有nullable-int doubling与`to_pylist()` adapter只保留bootstrap evidence，不是formal/public path，也不得被新Shared Kernel API引用。

## 3. 公共API与实现边界

### 3.1 Production types

Python与Rust提供语义对等、语言习惯化的typed API：

```text
CanonicalErrorCode
CanonicalEncodingError / CanonicalError
DeclaredType
LogicalLiteral
TypedScalar
EncodedScalar
RowField
EncodedRow
CollectionSemantics
DigestKind
SemanticDigest
DigestRef
```

规则：

- Python使用frozen dataclass/closed enum/discriminated union；Rust使用closed enum/struct。
- Rust DTO可以owned保存string/bytes，函数在自然位置接受borrowed input并返回owned bytes/result。
- Error对象携带normative stable code；message、exception type和stack不参与conformance。
- Result type显式命名并暴露所需的typed value、payload、完整frame、raw 32-byte digest和DigestRef；禁止含义不明的tuple或dict。
- `DigestKind`是formal registry对应的closed enum，不接受临时string kind。

Production functions：

```text
canonicalize_jcs
canonicalize_identifier
normalize_logical_literal
encode_typed_scalar
encode_row
encode_collection
semantic_digest
raw_blob_digest
```

不得公开generic scalar decoder、vector DTO production entrypoint或filesystem-aware API。

### 3.2 Test-only surface

以下能力只位于Python `gateway_shared_kernel.testing`或Rust integration-test support，不从production package root re-export：

- Schema/vector closure loader与validator。
- Vector operation dispatcher。
- `validate_scalar_frame` invalid-case helper。
- Candidate case definitions与generator。

Test-only representation不能成为PyO3 DTO、Repository wire contract或Artifact schema。

### 3.3 Canonical implementation strategy

- Python：先严格解码UTF-8，以duplicate-preserving hook parse JSON，验证I-JSON number与全部string/key Unicode，再交给`rfc8785` serialization。
- Rust：以recursive Serde visitor构造value并检测duplicate member，执行同等I-JSON/Unicode检查，再交给`serde_json_canonicalizer` serialization。
- 两边均不得解析第三方library error message来决定stable code；classification由项目validator的显式stage和typed branch决定。
- Decimal使用ASCII lexical validation/normalization，不经过binary float或定长decimal库。
- Float按声明宽度解析和舍入；float32先成为binary32；negative zero归一，nonfinite失败。
- Temporal使用严格Gregorian/component validation，不读取locale、timezone、tzdb或机器时间；MySQL TIME duration单独校验±838小时边界。
- 初版实现串行、确定、Safe Rust；vector/candidate tooling不设性能优化目标。

## 4. WP0 — Workspace Safety and Reproducible Gates

### 4.1 实施内容

Rust workspace root增加：

```toml
[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"

[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
```

每个member必须声明：

```toml
[lints]
workspace = true
```

每个crate root保留`#![forbid(unsafe_code)]`。WP0–WP2的test target同样不用`unwrap/expect` exception；测试使用`Result`、pattern match或显式断言。

新增repository-owned architecture/policy check，必须：

1. 通过Cargo metadata发现实际workspace member，不维护手写member allowlist。
2. 验证所有member继承workspace lint。
3. 验证所有crate root保留defense-in-depth forbid。
4. 验证正式toolchain是pinned stable 1.97.0且不存在nightly/feature gate。
5. 扫描vNext source import边界，禁止依赖legacy业务模块。

Compiler/Clippy是unsafe和panic shortcut的主gate；source inspection只负责member继承、toolchain和architecture等compiler不能完整表达的规则。

提供单一Phase 1 gate入口，接受：

```text
correctness   WP0实现并持续扩展
native        WP3开始实现；WP0只保留明确的unsupported/not-yet-implemented分支
```

它只编排已锁定的本地命令，不下载依赖、不生成fixture、不修改tracked files，也不绑定GitHub/GitLab等CI供应商。

### 4.2 Dependency evidence

每次新增/升级Rust dependency，记录：

- 用途和精确lock identity。
- Safe API边界及dependency内部unsafe事实。
- Proc-macro、build script、native/system-library行为。
- 维护状态、advisory/license检查结果。
- 替代方案和移除/回退路径。

WP0不引入nightly、cargo-deny、通用task framework、空crate或未使用目录。

### 4.3 WP0 gate

```text
cargo fmt --check
cargo clippy --locked --workspace --all-targets --all-features -- -D warnings
cargo test --locked --workspace --all-targets
cargo build --locked --workspace --release
architecture/policy check
```

负向test fixture必须证明：未继承lint的新member、first-party unsafe和production panic shortcut都会使gate失败。负向fixture必须在临时测试目录构造，不修改真实workspace。

WP0完成条件：上述命令可离线重复通过，gate前后tracked worktree不变，dependency inventory与toolchain/lock identity可追溯。

## 5. WP1 — Python Reference, Schemas and Candidate Vectors

### 5.1 Schema交付

在`vnext/fixtures/schemas/shared-kernel/canonical-encoding/v1/`创建：

```text
definitions.schema.json
vector-set.schema.json
jcs-case.schema.json
scalar-case.schema.json
digest-case.schema.json
invalid-case.schema.json
```

全部使用JSON Schema Draft 2020-12，固定`$schema`、stable `$id`、closed enum和`additionalProperties=false`。Schema只验证test-only data model；duplicate member、raw UTF-8、closure、ordering、digest和cross-file invariants由命名validator负责。

Declared type机器约束镜像owning contract：

```text
decimal: precision 1..=65; scale 0..=30; scale <= precision
bit: bit_width 1..=64
integer: bits in 8 | 16 | 24 | 32 | 64
```

Validation order固定为：

```text
case envelope/schema
  -> operation/input discriminant
  -> declared type/schema
  -> encoding/Unicode
  -> lexical/typed value
  -> canonical payload/frame
  -> framing/collection invariants
  -> expected bytes/digest
```

Vector自身schema/closure错误属于conformance data failure，不映射为被测Shared Kernel stable error。

### 5.2 Python reference

实现第3节production API以及formal registry的完整stable error enum。算法覆盖：

- Strict JCS与CanonicalIdentifier。
- Minimal ULEB128与typed scalar frame。
- Null、boolean、signed/unsigned integer、decimal、float32/64、string、binary/BIT、date/datetime/timestamp/time-duration和anomaly。
- Row field canonical ordering与collision rejection。
- Sequence、multiset、set与keyed collection framing。
- Registered semantic digest与direct raw blob SHA-256。

Production API不读取schema/vector文件；filesystem、base64url case decoding和operation dispatch只存在test-only package。

### 5.3 Candidate generator

Candidate命令只能写入调用方显式传入的新空目录，并必须：

- 拒绝fixed normative root、absolute escape、symlink和existing non-empty directory。
- 不覆盖任何文件，不提供`--bless`或in-place update。
- 按`case_id` ASCII bytes排序，拒绝duplicate ID。
- 输出UTF-8、LF、final LF的JCS JSONL。
- 固定四个JSONL path并按path bytes排序manifest entry。
- 先写四个JSONL，验证count/size/direct SHA-256后最后写`vector-set.json`与semantic closure digest。

Candidate case definitions是test/tooling source，不是第二个normative fixture。普通CI不运行generator；WP1产物保留out-of-tree，并明确标记“等待WP2独立确认”。

### 5.4 Case coverage

初始candidate至少覆盖：

| Area | Required families |
| --- | --- |
| JCS | ASCII/BMP/non-BMP key order；escaping；number thresholds；safe integer extrema；negative zero；duplicate；invalid UTF-8；surrogate；noncharacter；NaN/Infinity。 |
| Integer/decimal | 每个width min/max/overflow；plus、leading zero、negative zero；decimal canonical zero、leading/trailing zero、65/30 boundary、invalid exponent/plus/precision/scale。 |
| Float | float32/64 zero、negative zero、subnormal、finite extrema、rounding boundary与nonfinite。 |
| Text/binary/BIT | Empty、multibyte、non-BMP、invalid Unicode；binary empty/leading zero；BIT 1/8/9/64与unused-high-bit failure。 |
| Temporal/anomaly | Leap day及invalid date；datetime/timestamp fractions；TIME ±0、99、100、838与out-of-range；valid/invalid JCS anomaly envelope。 |
| Framing | Empty/small payload、ULEB length transition、truncated、non-minimal、overflow、unknown/reserved tag和length mismatch。 |
| Digest | Identifier ASCII fold/empty/collision；empty/mixed row与field permutation；collection ordering/duplicates；全部registered kind domain separation；direct raw hash。 |

Hypothesis以固定budget和deterministic配置补充JCS idempotence、encoding determinism、row/collection permutation、ULEB minimality和digest domain separation；property test不替代static cases。

### 5.5 WP1 gate

- `uv sync --locked --all-groups`后ruff、strict mypy、pytest和coverage全部通过。
- 所有schema通过Draft 2020-12 meta-schema与valid/invalid schema self-test。
- Candidate可离线生成并由独立read-only validator完整复验。
- Python stable error code set与formal registry完全相等。
- Generator前后fixed normative root和tracked worktree不变。
- WP1不创建或宣称正式normative vector closure。

## 6. WP2 — Independent Rust Core and Normative Publication

### 6.1 Rust implementation

`gateway-shared-kernel`独立实现第3节API与完整stable error enum：

- Recursive Serde visitor检测duplicate member；先执行明确的I-JSON/Unicode validation，再做JCS serialization。
- 使用checked conversion/arithmetic；整数、length和frame输入不得silent truncate。
- Decimal使用ASCII normalization；temporal使用独立component validation；不得调用Python实现或共享其algorithm source。
- Production core不拥有filesystem；integration test从repository fixture root读取case。
- Integration test逐case比较全部expected bytes和digest；invalid case只比较stable code，不比较message/class name。

新增production/dev dependency均完成WP0 dependency review并精确进入Cargo.lock。

### 6.2 第一次normative publication

首次发布固定执行：

1. Python向新的out-of-tree目录生成candidate。
2. Read-only validator校验schema、path、ordering、count、size、raw hash和closure digest。
3. Python reference逐case通过。
4. Rust independent implementation逐case通过。
5. Reviewer人工检查case新增范围、完整bytes/digest和success/error classification。
6. Candidate内容以普通reviewed patch写入固定normative root；不执行bless命令。
7. Python、Rust、Repository此后只读fixed root。

修改已发布v1 case的expected bytes、digest或success/error classification必须由test拒绝并要求v2。按v1规则唯一推导的新增case仍需走完整candidate/review流程。

### 6.3 Repository consumer

Repository Service的dev dependencies增加本地`gateway-shared-kernel[conformance]`，并更新自己的uv lock。Consumer test必须：

- 从repository固定root直接发现`vector-set.json`，不复制fixture。
- 复验closure并逐case调用共享Python API。
- 收集实际执行的case ID，不允许skip、xfail或operation fallback。
- 不实现第三套canonical算法，也不把test-only DTO提升为Repository wire type。

### 6.4 Coverage authority

Python、Rust与Repository分别产生executed case ID set。最终gate要求：

```text
python IDs == rust IDs == repository IDs == manifest closure IDs
```

Missing、extra、duplicate、skip、xfail或unsupported均失败。Valid case比较formal规定的完整中间bytes和digest；只比较最终digest不算通过。

### 6.5 WP2 gate

- 三方case ID set完全一致、zero skip。
- Fixed root可离线重算count、size、raw SHA-256与`vector_set_content_digest`。
- Rust通过WP0 fmt/clippy/test/release/architecture gate。
- Python Shared Kernel和Repository各自通过locked ruff/mypy/pytest gate。
- Repository没有复制algorithm、fixture或expected bytes。
- Tracked worktree不存在candidate output、automatic bless入口或generator副作用。
- `gateway-compute-core`仍未接入；新crate已具备WP3消费所需的唯一canonical primitives。

## 7. Delivery units 与联合验收

| Unit | Content | Merge state |
| --- | --- | --- |
| D0 Documentation | Temporary evidence、本文、formal导航与owner范围澄清。 | 独立docs commit。 |
| D1 / WP0 | Workspace safety、architecture check和correctness gate。 | 可独立合入。 |
| D2 / WP1 | Python reference、schemas和candidate tooling。 | 可合入；明确pending independent confirmation。 |
| D3 / WP2 | Rust implementation、Repository consumer和首次normative closure。 | 跨语言blocking gate正式启用。 |

联合验收矩阵：

| Area | WP0 | WP1 | WP2 |
| --- | --- | --- | --- |
| Workspace safety/lints | Required | Regression | Regression |
| Python typed canonical API | — | Required | Regression |
| Rust independent canonical API | — | — | Required |
| JSON Schema/closure validator | — | Required | Regression |
| Candidate-only generation | — | Required | Not in CI |
| Static normative root | — | Not published | Published after dual verification |
| Full bytes/stable-code compare | — | Python candidate | Python/Rust/Repository |
| Coverage set/zero skip | — | Python | All three equal |
| Repository direct consumer | — | — | Required |
| Arrow/PyO3/Artifact/Harness | Out | Out | Out |

D3通过后建立Phase 1中间checkpoint：canonical executable contract已经闭环，可以开始WP3 Arrow/PyO3 detailed design。它不代表Phase 1完成；完整Phase exit仍要求Implementation Stages中定义的Arrow、Artifact、Harness、scenario、native wheel/container与evidence gates。

## 8. Assumptions、change control 与完成定义

- Python固定3.14.6，Rust固定stable 1.97.0；所有dependency进入各自lockfile。
- Vector schema是test-only contract，不转化为production DTO、FFI或wire schema。
- 正确性、安全性、可维护性优先于vector tooling性能；不为WP0–WP2引入并行、cache或low-level optimization。
- First-party Rust保持zero unsafe；third-party dependency只通过reviewed safe API使用。
- Decimal、BIT和integer范围由Shared Canonical Encoding拥有；本文只安排实现与测试，不建立第二份semantic authority。
- 当前没有formal内部冲突或blocking decision。实现中若发现歧义，必须回到owner contract收口后继续。

WP0–WP2只有在D1–D3各自gate通过、三方vector coverage一致、首次normative closure经人工review并且blocking decision register为空时完成。不得以`xfail`、coverage缩减、单语言oracle、网络故障或“后续修复”替代通过。
