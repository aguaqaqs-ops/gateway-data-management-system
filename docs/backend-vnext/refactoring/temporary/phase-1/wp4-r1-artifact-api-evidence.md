# WP4 R1 — ArtifactRef / Manifest / Identity API Evidence

状态：R1 strict review / sign-off evidence

日期：2026-07-23

Design：[wp4-r1-artifact-api-design.md](wp4-r1-artifact-api-design.md)

Gate：`PR-CORRECTNESS`；非 `PR-NATIVE`

---

## 1. 审核结论、findings 与边界

**WP4 R1 ArtifactRef / manifest / identity API sign-off passed; ready to enter WP4 R2.**

审计不是按既有摘要签字；已读取完整实现、schema、fixtures、tests、diff 与相关 authority。
首轮发现均已关闭：

| ID | 等级 | 初始问题 | 关闭方式 |
| --- | --- | --- | --- |
| M1 | Major | `logical_ref` 从 raw SHA 派生，混淆 logical/raw identity | 改为 caller-assigned、版本化 namespace/id |
| M2 | Major | 擅自增加 manifest self digest 与 shared-kernel digest kind | 删除；R1 不发明 authority 未要求的 manifest identity |
| M3 | Major | capability content DTO 位于 generic artifacts package | 移至 capability-owned module，以 protocol 组合 |
| M4 | Major | JSON 输出并非 RFC 8785 JCS，生产解析导入 testing helper | 全部改用 shared-kernel production JCS API |
| M5 | Major | production validator 依赖 repo-relative schema/dev dependency，并留有 R2 stub | production 使用 fail-closed v1 validator；删除 filesystem stub |
| m1 | Minor | contract/media/schema/version、path confusion、equality 与负向测试不完整 | 收紧 DTO/schema/runtime 并补齐正负测试 |
| m2 | Minor | logical segment 长度在 schema/runtime 间漂移 | schema 分段限长并增加双向拒绝测试 |
| m3 | Minor | design/evidence 预填内容与实际实现、计数不符 | 重写 design/evidence，使用最终执行结果 |

未发现未闭合 findings。

本轮只签核 envelope/manifest/identity API、strict wire/schema、capability binding、
in-memory port contract 与 architecture boundary。没有实现 Arrow IPC write/reopen、
filesystem store、corrupt IPC suite 或 native end-to-end。

## 2. 审计环境

| 项 | 值 |
| --- | --- |
| OS | Linux 6.6.114.1-microsoft-standard-WSL2 x86_64 |
| Python | 3.14.6 |
| uv | 0.11.30 |
| rustc / cargo | 1.97.0 / 1.97.0 |
| backend pyarrow | 25.0.0（locked） |

## 3. WP3 R5 固定基线

| 项 | 值 |
| --- | --- |
| baseline | `49118e3a6a296e9a0d44d8ac9814f280c1fabcb8` |
| subject | `chore(vnext): finalize WP3 R5 dependency audit` |
| baseline existence | verified |
| `git merge-base --is-ancestor 49118e3... HEAD` | exit 0 |

历史 WP3 R5 evidence 未修改。

## 4. HEAD、branch、worktree 与 patch identity

| 项 | 值 |
| --- | --- |
| review start/current pre-commit HEAD | `49118e3a6a296e9a0d44d8ac9814f280c1fabcb8` |
| branch | `main` |
| merge-base | baseline 本身 |
| worktree | 仅预期 WP4 R1 code/schema/fixtures/tests/gate/docs/dependency lock |
| deterministic non-evidence patch SHA-256 | `41c3f57410c48a1310f0367935e8efc71788a2ed3d8930503e3eaa1721ab15f0` |
| `git diff --check` | exit 0 |

Patch hash 使用 baseline 到 staged tree 的 binary diff，明确排除本 evidence 文件，避免
evidence 自引用。本文件不填写同一提交自身 SHA；最终提交 SHA 在提交后报告。

`.gitignore` 的 `artifacts/` 收窄为 `/artifacts/`，避免误屏蔽 source/schema 内的
`artifacts` 目录。

## 5. Authority 清单与冲突处理

| Authority | 审核结果 |
| --- | --- |
| `contract-taxonomy-and-ownership.md` | generic envelope 与 capability content owner 分离 |
| `canonical-row-hash-compute-boundary.md` §8 | raw SHA 与 raw-content semantic digest 分离 |
| `shared-canonical-encoding.md` | 复用现有 strict JCS；未改 digest registry/normative vectors |
| `architecture-and-refactoring-plan.md` | wire 稳定；store/location resolution 留在 Python infrastructure |
| `rust-safety-and-performance-policy.md` | Rust 无本轮变更；unsafe/lint/panic policy 回归通过 |
| `implementation-stages.md` | 本轮为 correctness，不是 native sign-off |
| Phase 1 delivery plan / ADR 0001 | 保持 Python orchestration、Rust pure compute 边界 |
| `wp3-wp5-checkout-plan.md` §2/§3/§5/§8 | R1 closed；R2–R4 deferred |
| executable notes R14 | Rust/PyO3 不创建或接收 ArtifactRef |
| WP3 R1/R5 design/evidence/inventory | 只读前置依据 |

冲突处理：初始实现增加 `DigestKind.ARTIFACT_MANIFEST`，但 formal digest registry 是 closed
authority，且 R1 未要求 manifest identity；已删除该扩展和 self-digest 设计。没有修改
canonical encoding、row-hash semantics 或 normative vectors。

## 6. WP4 R1 交付物

- Generic Python package：`gateway_backend/artifacts/`（7 modules）。
- Capability content：`gateway_backend/canonical_row_hash_artifact.py`。
- Draft 2020-12 schemas：4 files。
- Fixtures：2 valid + 4 invalid。
- Artifact tests：6 files / 82 collected cases；architecture：6 cases。
- Design 与本 evidence。
- Backend 直接 production dependency：workspace `gateway-shared-kernel`。
- Dev-only schema conformance dependency：`jsonschema==4.26.0`。
- Correctness gate 的 backend test target 扩展为完整 `tests/`。

旧的单文件 bootstrap `artifacts.py` 被 package API 取代；没有保留含糊 `digest` 字段或
bootstrap fallback contract。

## 7. ArtifactRef / Manifest wire schema

| 对象 | 唯一版本轴 | Schema |
| --- | --- | --- |
| ArtifactRef | `artifact_ref_schema_version = 1` | `artifact-ref.schema.json` |
| ArtifactManifest | `manifest_schema_version = 1` | `artifact-manifest.schema.json` |
| Canonical Row Hash content | schema id + const v1 markers | `canonical-row-hashes-artifact.schema.json` |
| shared definitions | parent versioned ids | `definitions.schema.json` |

所有 public object schema 均关闭 unknown fields。`logical_ref` 为：

```text
gateway-vnext.artifacts/v1/ref/<namespace>/<artifact-id>
```

namespace 为 1–63、artifact-id 为 1–128 字符的 lowercase-kebab segment。logical ref
不由任一 digest 派生。

## 8. 字段 ownership、类型与 validation

### Generic envelope（全部 required）

| 字段 | 类型 | Owner | Validation |
| --- | --- | --- | --- |
| version marker | integer | Artifacts | exact `1`；bool 不作为 int |
| `logical_ref` | string | Artifacts/caller | closed grammar 与分段长度 |
| `media_type` | string | contract registration | exact registered value |
| `size_bytes` | integer | Artifacts | `0..9007199254740991` |
| `raw_sha256` | DigestRef | Artifacts | `sha256:` + 64 lowercase hex |
| `content_digest` | DigestRef | capability projection | 不回退到 raw SHA |
| `content_contract` | closed object | technical registry | exact owner contract/version |
| `content_schema_id` | string | capability marker | exact registered schema |
| `retention_class` | enum | Artifacts | 3 个 closed values |
| `access_metadata` | closed object | Artifacts | resolver const `artifact-store` |

### Capability-owned content（全部 required）

| 字段 | Validation |
| --- | --- |
| schema/media markers | exact registered constants |
| `raw_content_digest` | DigestRef；投影为 envelope semantic digest |
| `table_schema_digest` | DigestRef |
| canonical/Arrow mapping/result versions | exact `1` |
| `contract_binding` | exact boundary id / `1.0.0` |
| `row_count` | canonical unsigned decimal，无 leading zero |

Manifest 构造和解析同时验证 envelope/content 的 media、contract、schema 与 semantic
digest binding。R1 未定义 manifest self identity。

## 9. Logical / raw / semantic identity

| 层次 | 明确定义 | 证明 |
| --- | --- | --- |
| Logical | caller-assigned `logical_ref` | builder 不接收 digest；独立 mutation tests |
| Raw integrity | `size_bytes + raw_sha256` | put/locate 均重验实际 bytes |
| Semantic | contract/version/schema + `content_digest` | capability content 投影和 mismatch tests |

`ArtifactRef` 和 `ArtifactManifest` 均禁用 dataclass 默认 equality，显式定义 stable
`cache_key`/content `identity_key`。没有使用 Python `hash()`、UUID、时间或对象地址。
相同 semantic digest 不能跳过 raw 校验；不同 raw identity 不会自动改变 semantic
identity。

## 10. Location independence / host-path 排除

- Wire 没有 provider/root/path/context/任意 metadata 字段。
- Access metadata 只有 closed resolver token。
- DTO/runtime 防御拒绝 path-shaped keys，以及 absolute、`..`、backslash、Windows
  drive/UNC、`file:`, NUL、percent-encoding confusion。
- 两个不同 `BackendSettings.artifact_root` 产生相同 serialized ref。
- `InMemoryArtifactStore` 只按 logical ref 查找并要求完整 ref equality；不存在 cwd/env
  fallback 或 filesystem scan。
- Local filesystem implementation 明确 deferred 到 R2，R1 不留会被误调用的 stub。

## 11. Content owner / generic envelope 边界

Generic artifacts 仅依赖 capability-neutral `ArtifactContentManifest` protocol，并只验证
声明的 contract/media/schema/digest 投影。`CanonicalRowHashesArtifactManifest` 及其
`raw_content_digest`、`table_schema_digest`、mapping/version/row-count 规则位于
capability module。Artifacts package 没有导入该 module，也没有第二套 row-hash digest
算法。

## 12. Rust core / PyO3 / ArtifactStore 依赖方向

```text
Rust core / PyO3 -> Arrow stream + result JCS
Python capability -> content manifest
Python artifacts -> shared-kernel digest/JCS
Python infrastructure -> ArtifactStorePort
```

Architecture tests 与 workspace checker 证明 Rust core/PyO3 request 无 ArtifactRef、
logical ref、retention、filesystem/object-store/environment/store dependency。Compute
facade 不导入 artifact identity；artifacts 不导入 compute 或 shared-kernel testing。

## 13. Strict JSON / JCS / schema 证据

- Public output 使用 shared-kernel RFC 8785 canonicalizer，不使用 `repr` 或普通
  `json.dumps(sort_keys=True)` 冒充 JCS。
- Public input 使用 production `canonicalize_jcs`，拒绝 nested duplicate、trailing
  data、invalid UTF-8、surrogate/noncharacter 与 non-I-JSON number。
- Runtime validator 不从源码树读取 schema，不依赖 dev-only `jsonschema`。
- Tests 使用 Draft 2020-12 validator 做 schema meta-validation，并将有效 fixtures 和
  closed invalid mutations同时投入 schema/runtime。
- Schema/runtime 共同覆盖 exact digest、safe integer 上下界、logical segment 长度、
  enums/version/media/contract/schema binding。

## 14. 正向、负向与 architecture 测试矩阵

| 类别 | 覆盖 |
| --- | --- |
| Ref 正向 | 最小构造、完整 dict/JSON round-trip、JCS deterministic、显式 equality/cache key |
| Manifest 正向 | generic/capability composition、JCS、round-trip、fixture |
| Identity | logical/raw/semantic 独立 mutation；store raw revalidation；logical collision |
| Schema | 4 meta-valid；valid schema/runtime；17 schema alignment cases |
| Strict JSON | duplicate/trailing/invalid UTF-8/Unicode/non-I-JSON |
| Closed values | missing/unknown/debug/context/provider；version/media/retention/resolver/contract/schema |
| Numeric/digest | negative/float/bool/overflow size；uppercase/short/padded/bare SHA |
| Path | absolute/`..`/Windows/UNC/`file:`/NUL/backslash/percent |
| Content binding | raw/semantic swap、owner/version/schema/digest mismatch、row count/version |
| Architecture | artifacts/compute/Rust/PyO3/store boundary；无 deferred production stub |

Artifact suites 共 82 cases；加 architecture 共 88，真实执行为 88 passed。

## 15. Dependency、lock、license / advisory

| 项 | 结论 |
| --- | --- |
| `gateway-shared-kernel==0.1.0` | 新增直接 workspace prod dependency；复用 DigestRef/raw digest/JCS，必要且无新外部存储依赖 |
| `jsonschema==4.26.0` | dev-only，用于 schema conformance tests；production runtime 不导入 |
| backend `pyproject.toml` SHA-256 | `006c197bb3bac68416b34797e16e6710869034da9184a43b30f7a93eb250c0b6` |
| backend `uv.lock` SHA-256 | `681a3f4e4b0ff0b4890761736f8dd35e8a84afaebc8cf2310ccf3221adde680c` |
| Rust `Cargo.lock` SHA-256 | `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544`；未变 |
| shared-kernel `uv.lock` SHA-256 | `fe79bf4df1231bf308ad19614a0b5690ef1e5489a0b99d8194e8f363e36e4f74`；未变 |

联网核验：PyPI 将 jsonschema 4.26.0 标为 2026-01-07 发布、Production/Stable、
Python 3.14、SPDX MIT、非 yanked，并声明 Draft 2020-12 支持；官方 JSON metadata 的
`vulnerabilities` 为空。审计日未发现该锁定版本的已列 advisory。
[PyPI release](https://pypi.org/project/jsonschema/4.26.0/)；
[PyPI JSON metadata](https://pypi.org/pypi/jsonschema/4.26.0/json)。

## 16. 验证命令、退出码与计数

| 命令 | Exit | 结果 |
| --- | --- | --- |
| `bash vnext/scripts/gate.sh correctness` | 0 | correctness gate passed |
| backend `uv run --offline --no-sync pytest -q` | 0 | 91 passed, 1 third-party deprecation warning |
| backend `ruff check .` | 0 | clean |
| backend `ruff format --check .` | 0 | 21 files formatted |
| backend `mypy .` | 0 | 21 source files |
| targeted artifact + architecture pytest | 0 | 88 passed |
| `cargo fmt --check` | 0 | clean |
| cargo clippy locked/offline/all targets/features | 0 | clean |
| cargo test locked/offline/workspace/all-targets | 0 | 240 passed, 0 failed |
| cargo build locked/offline/workspace/release | 0 | built |
| `gateway-architecture-check` | 0 | passed |
| `bash vnext/scripts/gate.sh native` | 2 | expected placeholder boundary |
| `git diff --check` | 0 | clean |

Correctness gate 内计数：shared-kernel 131 passed（coverage 82.58%）；
repository-service 5 passed；Rust 240 passed；native-kernel component 18 passed；
backend gate 111 passed（完整 backend 91 + compute facade/production 20）。

Native 命令的精确输出为
`native gate is not implemented until WP4 R4`。Exit 2 只证明 R4 边界保持，未记为
passed 或 failed。

## 17. Cleanup / hermeticity

| 项 | 结果 |
| --- | --- |
| 测试生成 tracked 污染 | 无 |
| source-tree `.so` | 无 |
| non-ignored untracked wheel / project tmp | 无 |
| production extension | gate 后恢复到 backend `.venv/.../site-packages` |
| production extension test-hook exports | `[]` |
| arbitrary `/tmp` | 未删除所有权不明内容 |

Build/test caches 与 ignored `target/` 产物不进入提交。

## 18. Deferred register

| Checkout | Deferred item |
| --- | --- |
| WP4 R2 | Arrow IPC write/reopen、LocalArtifactStore、raw/semantic identity 复验 |
| WP4 R3 | corrupt/truncated/mismatch IPC 负向套件 |
| WP4 R4 | facade → PyO3 → Rust → ArtifactRef → reopen；正式 native gate / PR-NATIVE |
| WP5 | scenario YAML、runner、golden、container harness |

## 19. Unresolved findings 与最终结论

未发现未闭合 findings。

**WP4 R1 ArtifactRef / manifest / identity API sign-off passed; ready to enter WP4 R2.**

本结论不涵盖 PR-NATIVE，不表示 artifact write/reopen 或整个 Phase 1 已完成。
