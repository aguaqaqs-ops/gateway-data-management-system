# WP5 R1 — Scenario / Golden / Protocol / Result Schema 与 Strict Closure Evidence

状态：**PASS — EXT-REVIEW-REAUDIT-6 signed off; ready to enter WP5 R2**

日期：2026-07-24

前置基线：[wp4-r4-artifact-path-closure.md](wp4-r4-artifact-path-closure.md)（`f1a6135ebf532d83d8179f22bad6637ed24b6d02`）

Gate：**`PR-CORRECTNESS`**（`vnext/scripts/gate.sh correctness`）

---

## 1. 结论与边界

| 项 | 声明 |
| --- | --- |
| 本轮范围 | 5 个 fixture oracle JSON Schema、Conformance Harness 严格 YAML + 语义闭包 validator、测试与 gate 集成 |
| **不是** | WP5 R2–R5、Phase 1 exit、真实 canonical-row-hash scenario、runner/registry、`PR-NATIVE` |
| 审核状态 | **PASS** — No blocking findings；REAudit-6 独立验证与完整 `PR-CORRECTNESS` 通过 |

### R1 边界澄清

| 项 | 声明 |
| --- | --- |
| BLK-002 test-owner | R1 仅注册 **test-capability** test-owner；**不得**宣称与 formal capability owner digest 完全等价 |
| canonical-row-hash owner | **defer R3** |
| MAJ-005 preimage | formal §4.4 唯一规定 projection/framing；vectors 固定 `collection_frame`（含 shared-structured）；Python+Rust 双实现 oracle；fixture child identity 对 shared structured 使用 owner `content_digest` |
| MAJ-008 run evidence | `DigestKind.RUN_EVIDENCE` + JCS(bundle \\ content_digest)；Python/Rust/schema/formal 已同步 |

### Out of scope（本轮未做）

- R2 runner lifecycle / registry / fake harness / result precedence 执行
- R3 正式 `vnext/fixtures/scenarios/` 真实 data scenario
- R4 profile 全矩阵 / R5 container / Phase 1 exit
- auto-bless / golden rewrite
- `gate.sh native` / `PR-NATIVE`（未触及 native/wheel 路径）

---

## 2. 基线、HEAD、merge-base

| 项 | 值 |
| --- | --- |
| 约定 baseline | `f1a6135ebf532d83d8179f22bad6637ed24b6d02` |
| HEAD | `f1a6135ebf532d83d8179f22bad6637ed24b6d02`（与 baseline 相同，未前进） |
| merge-base | `f1a6135ebf532d83d8179f22bad6637ed24b6d02` |
| branch | `main` |
| 交付形态 | 最终 PASS 后由单一签核提交收束（含本 evidence） |

---

## 3. Authority 与冲突处理

| Authority | 采用 |
| --- | --- |
| [fixture-oracle-and-conformance.md](../../formal/contracts/fixture-oracle-and-conformance.md) | 主权威 |
| [shared-canonical-encoding.md](../../formal/contracts/shared-canonical-encoding.md) | digest kinds `scenario-input` / `scenario-fixture` / `run-evidence` |
| [contract-taxonomy-and-ownership.md](../../formal/contracts/contract-taxonomy-and-ownership.md) | Conformance Harness owner |
| [implementation-stages.md](../../formal/plans/implementation-stages.md) | `PR-CORRECTNESS` |
| [ADR 0006](../../formal/adr/0006-language-neutral-fixture-oracle.md) | language-neutral oracle root |
| [wp3-wp5-checkout-plan.md](wp3-wp5-checkout-plan.md) | WP5 R1 范围 |
| [wp4-r4-artifact-path-closure.md](wp4-r4-artifact-path-closure.md) | 基线事实（不反向修改） |

### Temporary vs Formal 冲突（以 formal 为准）

| 冲突 | Formal（采用） | Temporary（弃用） |
| --- | --- | --- |
| manifest 字段 | `expected[]`、`track`、`legacy_classification` | 旧 `expectations[]`、无 `track` |
| provenance | `HANDCRAFTED` / `SANITIZED_REGRESSION` | 小写 `handcrafted` |
| shared 根 | `vnext/fixtures/shared/` | `vnext/fixtures/assets/sha256/` |

### R1 Design Decisions（已记录，非 blocker）

| 决策 | R1 采用 |
| --- | --- |
| Shared asset ref wire | `sha256/<64-hex>/<logical-name>` → `vnext/fixtures/shared/sha256/<hex>/<name>` |
| Golden/structured `content_digest` | test-owner registry resolver（`owner/`）；非 Harness 自选 kind |
| Run evidence `content_digest` | `semantic_digest(RUN_EVIDENCE, JCS(bundle \\ content_digest))` |
| Fault/recovery owner registry 全矩阵 | R1 governance v1 最小矩阵；完整 subject registry defer R2/R3 |

---

## 4. Owner / 依赖决策

| 组件 | Owner | 路径 |
| --- | --- | --- |
| Scenario / golden / protocol / result / evidence schema | Conformance Harness | `vnext/fixtures/schemas/*.schema.json` |
| Semantic validator | Conformance Harness | `vnext/conformance/` → `gateway_conformance` |
| JCS / digest / framing | Shared Kernel | `gateway_shared_kernel`（依赖，非业务扩展） |

依赖：

- `jsonschema==4.26.0`
- `ruamel.yaml==0.19.1`（MIT；safe loader + 源码预扫描拒绝 anchor/alias/merge/tag/directive）
- `gateway-shared-kernel[conformance]`（editable path）

---

## 5. Schema `$id`、版本与用途

| 文件 | `$id` | 用途 |
| --- | --- | --- |
| `definitions-v1.schema.json` | `gateway-vnext.fixture-oracle.definitions.v1` | 共享 `$defs` |
| `scenario-manifest-v1.schema.json` | `gateway-vnext.fixture-oracle.scenario-manifest.v1` | `scenario.yaml` 解析后 JSON model |
| `golden-envelope-v1.schema.json` | `gateway-vnext.fixture-oracle.golden-envelope.v1` | expected golden envelope |
| `harness-protocol-v1.schema.json` | `gateway-vnext.fixture-oracle.harness-protocol.v1` | validated plan DTO（无 golden 泄漏） |
| `runner-result-v1.schema.json` | `gateway-vnext.fixture-oracle.runner-result.v1` | 四态 status + 三态 comparison |
| `run-evidence-v1.schema.json` | `gateway-vnext.fixture-oracle.run-evidence.v1` | RunEvidenceBundle |

全部：JSON Schema Draft 2020-12、`additionalProperties: false`、离线本地 `$ref`、metaschema 自校验。

---

## 6. Strict YAML 矩阵

| 类别 | 接受 | 拒绝 |
| --- | --- | --- |
| 文档 | 单 UTF-8 文档 | 多文档、`%YAML`/`%TAG` directive |
| 结构 | string-key mapping、sequence | anchor、alias、`<<:` merge、explicit tag |
| 标量（JSON tag-resolution） | `true`/`false`/`null`、I-JSON safe JSON number、普通字符串（含 `True`/`FALSE`/`Null`/`~`/`-label`/`1label`/`1e`） | NaN/Inf、implicit timestamp、YAML core `0o`/`0x`/`0b`/underscore/leading-zero、`+12`/`.5`/`-.5`/`+.5`/`1.`、explicit tag、alias；token 扫描 `ScannerError` 归一为 `StrictYAMLValidationError` |
| 键 | string key | complex/non-string key、duplicate key |
| 语义 | 解析后 JSON-compatible tree | 非 JSON-compatible 宿主类型 |
| Identity | 引号日期、注释内 `&anchor` 不影响语义 | — |

实现：`gateway_conformance.strict_yaml`（ruamel `typ=safe` + **JSON Schema Resolver**；token 扫描用 `_JSON_NUMBER` / `_CORE_NUMBER` 正则；I-JSON `[-(2**53)+1, (2**53)-1]`）。

---

## 7. 验证矩阵（semantic validator）

| 维度 | 实现 |
| --- | --- |
| ID/path 可逆 | `scenarioId` 恰好 3 段 `track.subject.scenario-name`；双向 `scenario_id` ↔ path |
| 排序/唯一 | `contract_bindings`、`input_assets`、`expected`、`required_profiles` UTF-8 字节序；declared path/ref 唯一 |
| 路径安全 | `secure_io` fd-rooted `O_NOFOLLOW` `openat`；拒绝目录/文件 symlink；TOCTOU 负向探针（open 后路径替换不影响 fd 读取） |
| Raw closure | `size_bytes` + `raw_sha256` 先于 semantic digest；shared `ref` digest 必须匹配 `raw_sha256` |
| Structured vs raw | structured 用 test-owner `content_digest`（schema validate + JCS）；raw 用 direct SHA-256 |
| Golden binding | manifest `expected[]` ↔ envelope；owner resolver 重算 inline/artifact digest |
| `input_digest` | projection 含 `content_binding` + owner `content_digest` |
| `fixture_content_digest` | `expected[]` 剥离 transport-only；golden 仅用 owner `content_digest` |
| Protocol | schema conditionals + semantic cross-field；**wire 充分条件 = schema ∧ `validate_runner_result_semantics`**（禁止只跑裸 schema）；`validate_run_evidence_bundle` 重算 `content_digest` 且校验 checkpoint outcome↔digest |
| Governance | `SANITIZED_REGRESSION` policy + **approval authority** registry；fault/recovery legality；golden security scan |
| 错误消毒 | 剥离主机绝对路径；不输出 payload/stack |
| Read-only | 无 bless/write-back |

---

## 8. 变更清单（delivery manifest）

| 状态 | 路径 |
| --- | --- |
| M | `.gitignore`（`.cursor/` / `.vscode/`） |
| M | `docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md`（`run-evidence`） |
| M | `docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md`（§4.4 byte preimage） |
| M | `vnext/scripts/gate.sh` |
| M | `vnext/shared_kernel/src/gateway_shared_kernel/types.py` + `tests/test_typed_models.py` |
| M | `vnext/fixtures/schemas/shared-kernel/canonical-encoding/v1/definitions.schema.json` |
| M | `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/{digest.jsonl,vector-set.json}` |
| M | `vnext/rust/gateway-shared-kernel/src/types.rs`（`RunEvidence`） |
| M | `vnext/repository_service/tests/conformance/test_vector_conformance.py`（case count 126） |
| A | `vnext/rust/gateway-shared-kernel/tests/scenario_digest_vectors.rs` |
| A | `vnext/scripts/verify-wp5-r1-patch-sha.sh`（git toplevel 锚定；新增文件相对 baseline 统一用 `/dev/null` diff） |
| A | `vnext/fixtures/schemas/{definitions,scenario-manifest,golden-envelope,harness-protocol,runner-result,run-evidence}-v1.schema.json` |
| A | `vnext/fixtures/schemas/conformance/owners/v1/` |
| A | `vnext/fixtures/schemas/conformance/governance/v1/`（含 `recovery-legality.json`；fault 无 `recovery_kinds`） |
| A | `vnext/fixtures/shared/sha256/.../table-json`（shared-structured normative asset） |
| A | `vnext/fixtures/vectors/conformance/scenario-digest/v1/`（含 `shared-structured-input` + `collection_frame_base64url`） |
| A | `vnext/conformance/`（secure_io、strict YAML/JSON、owner、policy opaque allowlist、protocol 真值矩阵、单次加载 validate） |
| A | `docs/.../wp5-r1-scenario-schema-closure-evidence.md`（本文件） |

签核前 `git ls-files -o`（排除 `.vscode/`）：**65**；最终由单一签核提交收束。

---

## 9. 验证命令与结果

| 命令 | exit | 结果 |
| --- | ---: | --- |
| `git diff --check` | 0 | 无冲突标记 |
| `cd vnext/conformance && UV_OFFLINE=true uv sync --locked --offline --all-groups` | 0 | lock 一致 |
| `uv run ruff check src tests` | 0 | pass |
| `uv run ruff format --check src tests` | 0 | pass |
| `uv run mypy` | 0 | pass |
| `uv run pytest -q` | 0 | **397 passed**, 0 skipped |
| `uv run pytest --collect-only -q` | 0 | **397 collected** |
| Rust `scenario_digest_vectors` | 0 | pass |
| repository vector conformance | 0 | pass |
| `bash vnext/scripts/verify-wp5-r1-patch-sha.sh` | 0 | 与 §10 SHA 一致 |
| `EXPECTED_SHA=<§10> bash vnext/scripts/verify-wp5-r1-patch-sha.sh` | 0 | 一键校验 |
| BASE-only 临时 index + 同一 verify 脚本 | 0 | 新文件处于 untracked / tracked 状态时 SHA 相同 |
| `bash vnext/scripts/gate.sh correctness` | 0 | **PR-CORRECTNESS passed** |

### Gate 摘要（2026-07-24 Strict YAML JSON Schema 修复后）

| 组件 | passed | skipped | collected |
| --- | ---: | ---: | ---: |
| shared_kernel pytest | 139+ | 0 | — |
| repository_service pytest | 5 | 0 | 5 |
| **conformance pytest** | **397** | **0** | **397** |
| rust workspace tests | 114+ | 0 | — |
| backend pytest | 246 | 3 | 249 |

### Skipped tests（backend，非 R1 引入）

| 测试 | 原因 |
| --- | --- |
| `test_pr_native_gil_progress.py` 等 3 项 | 既有 PR-NATIVE 可选探针；R1 未触及 native gate，保持 skip |

R1 **未运行** `gate.sh native`。

---

## 10. Patch SHA（排除本 evidence）

```bash
bash vnext/scripts/verify-wp5-r1-patch-sha.sh
# 可选：EXPECTED_SHA=<下方值> bash vnext/scripts/verify-wp5-r1-patch-sha.sh
```

排除项：本 evidence 文件、`.vscode/*`、`.cursor/*`。脚本先 `cd` 到 git toplevel，避免 cwd 影响。BASE 默认 `f1a6135ebf532d83d8179f22bad6637ed24b6d02`。相对 BASE 已存在的路径使用 canonical tracked diff；相对 BASE 新增的路径无论当前为 untracked、staged 或 committed，均按路径字节序并统一使用 `/dev/null` diff，避免提交动作改变哈希。

| 项 | 值 |
| --- | --- |
| deterministic patch SHA-256 | `2536b7763d68f2d5c34338bd2b18c045764160f0036c95b382dc106ef8b775b0` |

---

## 11. Deferred（R2–R5）

| 轮次 | 内容 |
| --- | --- |
| R2 | runner lifecycle、registry、fake harness、result precedence 执行 |
| R3 | 真实 `canonical-row-hash` data scenario 入正式 oracle root |
| R4 | reference / integration / provider-matrix 全矩阵 |
| R5 | container、`PHASE-EXIT-CONTAINER`、Phase 1 exit |

---

## 12. Findings register

| ID | 严重性 | 描述 | 状态 |
| --- | --- | --- | --- |
| WP5-R1-REV-MAJ-001 | Major | structured input asset `content_digest` 未独立验证 | **CLOSED** — `structured_asset_content_digest` + closure 重算比对；正向/负向测试 |
| WP5-R1-REV-MAJ-002 | Major | strict YAML 接受 `0o`/`0x` core 数字 | **CLOSED** — 引号外 token 级源码预扫描（block/flow/sequence）；octal/hex/underscore + flow 回归测试 |
| WP5-R1-REV-MAJ-003 | Major | stimulus `asset-ref` 未校验 `logical_name` 已声明 | **CLOSED** — `assert_binding_references` 扩展；`support.py` stimulus 序列化修复 |
| WP5-R1-REV-MIN-001 | Minor | `1_000` 下划线数字 | **CLOSED** |
| WP5-R1-REV-MIN-002 | Minor | `fixture_content_digest` 独立 oracle 测试 | **CLOSED** |
| WP5-R1-REV-MIN-003 | Minor | symlink 拒绝回归测试 | **CLOSED** |
| WP5-R1-REV-MIN-004 | Minor | `support.py` 硬编码 inline stimulus | **CLOSED** |
| WP5-R1-REV-MIN-005 | Minor | artifact golden `content_digest` 未重算 | **CLOSED** — owner resolver 验证 artifact closure inner/outer digest |
| WP5-R1-REV-MIN-006 | Minor | flow mapping 内 `0o`/`0x` 绕过块级预扫描 | **CLOSED** — token 级扫描；flow/sequence 回归测试 |
| WP5-R1-REV-MIN-007 | Minor | architecture guards / oracle | **CLOSED** — https/unsafe-yaml/大小写敏感 guard + vector oracle |
| WP5-R1-REV-BLK-001 | Blocker | symlink directory 逃逸 + TOCTOU | **CLOSED** — 固定 `SecureRoot` fd；逐段 `openat(O_NOFOLLOW)`；ancestor rename+symlink 回归拒绝 |
| WP5-R1-REV-BLK-002 | Blocker | Harness 发明 owner content digest | **CLOSED** — test-owner registry；canonical-row-hash **defer R3**（见 §1 边界澄清） |
| WP5-R1-REV-MAJ-004 | Major | strict YAML 子集不完整 | **CLOSED** — 删除整文件 `:\s*+`/`:\s*.` regex；未加引号 `+12`/`.5` token 拒绝；quoted/comment 接受 |
| WP5-R1-REV-MAJ-005 | Major | digest preimage/coverage | **CLOSED** — shared structured fixture child 使用 owner `content_digest`；`shared-structured-input` vector + Python/Rust oracle |
| WP5-R1-REV-MAJ-006 | Major | ID/path 碰撞与 shared-ref | **CLOSED** — semantic binding tuple 唯一；`expected` 精确匹配恰好一个 binding |
| WP5-R1-REV-MAJ-007 | Major | JSON duplicate member | **CLOSED** — `strict_json.py` |
| WP5-R1-REV-MAJ-008 | Major | protocol/result/evidence 不可能状态 | **CLOSED** — 聚合真值矩阵 + MATCH/MISMATCH 必须对照 expected/actual digest 对 |
| WP5-R1-REV-MAJ-009 | Major | runtime 缺 `jsonschema` | **CLOSED** — 移入 runtime deps + wheel smoke |
| WP5-R1-REV-BLK-003 | Blocker | `run-evidence` digest kind 未在 formal authority 登记 | **CLOSED** — [shared-canonical-encoding.md](../../formal/contracts/shared-canonical-encoding.md) §5 登记 |
| WP5-R1-REV-MAJ-010 | Major | patch SHA 不可复现 | **CLOSED** — §10 重算；verify 脚本固定 git toplevel；`EXPECTED_SHA` exit 0 |
| WP5-R1-REV-MAJ-011 | Major | governance/fault/security policy | **CLOSED** — **011A** 独立 `recovery-legality.json` + binding/parameters；**011B** opaque allowlist grammar（拒 http(s)/Windows/UNC/`..`） |
| WP5-R1-REV-MAJ-012 | Major | `secure_io` intermediate fd 泄漏 | **CLOSED** — `_openat_relative` 前进后立即 close intermediate；`/proc/self/fd` 净增≈0 回归 |
| WP5-R1-REV-MAJ-013 | Major | `run-evidence` closed digest registry 跨语言不一致 | **CLOSED** — Rust `DigestKind::RunEvidence` + `digest.jsonl` / vector-set 同步 |
| WP5-R1-REV-MAJ-014 | Major | shared correctness asset size accounting 错误 | **CLOSED** — shared 不计入 local 1 MiB；单独 `SHARED_ASSET_MAX_BYTES` |
| WP5-R1-REV-MAJ-015 | Major | `load_validated_scenario` 双加载不一致快照 | **CLOSED** — `_validate_loaded_closure` 单次加载；manifest is closure.manifest |
| WP5-R1-REV-MIN-008 | Minor | shared-structured 测试写仓库 `SHARED_ROOT` | **CLOSED** — 强制临时 shared_root + monkeypatch；向量测试不再写入 `vnext/fixtures/shared/` |
| WP5-R1-REV-MIN-009 | Minor | `_looks_numeric` 误拒非数字标量 | **CLOSED** — 以 `_JSON_NUMBER`/`_CORE_NUMBER` 正则判定；接受 `-label`/`1label`/`1e`/`.label`/`+label` |
| WP5-R1-REV-MIN-010 | Minor | Core scalar 解析把 `True`/`FALSE`/`Null`/`~` 转成 bool/null | **CLOSED** — YAML 1.2 JSON Schema Resolver；仅 `true`/`false`/`null` 为 bool/null |
| WP5-R1-REV-MIN-011 | Minor | token 扫描 `ScannerError` 未归一 | **CLOSED** — `_scan_forbidden_tokens` 捕获 `YAMLError` → `StrictYAMLValidationError`；`value: -` 回归 |
| WP5-R1-REV-MIN-012 | Minor | Core 伪数字拒绝不对称（`-.5`/`1.`） | **CLOSED** — `_CORE_NUMBER` 覆盖伪数字形式；quoted 仍接受 |
| WP5-R1-REV-MIN-013 | Minor | opaque allowlist 接受伪 URI/盘符（`http:…`/`c:…`） | **CLOSED** — allowlist 后拒绝危险 scheme 前缀与 Windows 盘符；保留 `review-ticket:42` |
| WP5-R1-REV-MIN-014 | Minor | checkpoint outcome↔`content_digest` null 不一致 | **CLOSED** — MATCH/MISMATCH 需非 null digest；NOT_RUN 需 null |
| WP5-R1-REV-MIN-015 | Minor | runner-result schema 宽于语义（UNSUPPORTED/ASSERTION cleanup） | **CLOSED** — schema 收紧 + Evidence 声明 schema∧semantic；architecture guard |
| WP5-R1-REV-MIN-016 | Minor | Core 伪科学计数 `1.e2`/`1.e+2` 未拒 | **CLOSED** — `_CORE_NUMBER` 覆盖；quoted/`1.0e+2` 仍接受 |
| WP5-R1-REV-MIN-017 | Minor | opaque scheme denylist 不完整（`mailto:`/`ws:` 等） | **CLOSED** — colon-prefix allowlist（`approval`/`review-ticket`）+ 扩展 denylist + 盘符收紧 |
| WP5-R1-REV-MIN-018 | Minor | golden/sanitize Windows 路径正则漏检（字面双 `\`） | **CLOSED** — `_WINDOWS_DRIVE_PATH` + `_UNC_PATH`；单 `\`/`/`/UNC 拒绝 |
| WP5-R1-REV-MIN-019 | Minor | opaque colon-prefix 后可嵌套 scheme/盘符 | **CLOSED** — `prefix:rest` 的 `rest` 须为无冒号 opaque（`_OPAQUE_REST`） |
| WP5-R1-REV-MIN-020 | Minor | golden/sanitize 漏检 `file://` 内绝对路径 | **CLOSED** — 共享 `host_paths.FILE_URI` + 放宽边界 |
| WP5-R1-REV-MIN-021 | Minor | 路径检测 lookbehind 边界过窄（`=`/`[`/`{` 等） | **CLOSED** — `_BOUNDARY = (?:^|[^A-Za-z0-9_.-])`；golden/sanitize 共用 |
| WP5-R1-REV-MIN-022 | Minor | `host_paths` 漏检百分号编码 `file:` URI | **CLOSED** — unquote 变体双重检测 + `FILE_URI` 覆盖编码形式 |
| WP5-R1-REV-MIN-023 | Minor | `contains_host_path` 与 `redact_host_paths` 编码检测不对称 | **CLOSED** — regex 后若仍命中则 token 级 fallback 脱敏 |
| WP5-R1-REV-MIN-024 | Minor | 含空格路径脱敏在空白处截断并残留泄漏 | **CLOSED** — `_PATH_BODY` 允许单空格续段，整段替换 |
| WP5-R1-REV-MIN-025 | Minor | Unicode/全角斜杠绕过 detect+golden | **CLOSED** — `_SLASH_FOLD` 归一后再 detect/redact |
| WP5-R1-REV-MIN-026 | Minor | `~user/...` 家目录路径漏检 | **CLOSED** — `HOME_PATH`；unquote 覆盖编码形式 |
| WP5-R1-REV-MIN-027 | Minor | Unicode/非 `[ \t]` 空白续段泄漏 | **CLOSED** — `_PATH_GAP=\s+`；语料表驱动 |
| WP5-R1-REV-MIN-028 | Minor | `$HOME` / `%USERPROFILE%` 家目录变量漏检 | **CLOSED** — `ENV_HOME`；corpus 覆盖 |
| WP5-R1-REV-MIN-029 | Minor | 全角 `：`/`～` 与未折叠 solidus（`⧸`/`﹨`） | **CLOSED** — punct+slash fold 扩展；corpus 覆盖 |
| WP5-R1-REV-MIN-030 | Minor | `_FORBIDDEN_NUMBER` 过宽误拒 / 漏判 Core 数字（含 sexagesimal MIN-033） | **CLOSED** — `_CORE_NUMBER` 精确匹配；`+1label` 放行 |
| WP5-R1-REV-MIN-031 | Minor | timestamp 词法不全（单数字字段 / 偏移 / tab） | **CLOSED** — YAML 1.1 !!timestamp 词法（后由 MIN-037 纠偏裸单数字） |
| WP5-R1-REV-MIN-032 | Minor | unquote 后未再 fold（编码全角逃逸） | **CLOSED** — unquote↔fold 稳定化；corpus 编码全角 |
| WP5-R1-REV-MIN-034 | Minor | JSON 指数零填充被 YAML 误拒（`1e+02`） | **CLOSED** — `_JSON_NUMBER`/`_JSON_FLOAT` 指数 `[eE][+-]?[0-9]+` |
| WP5-R1-REV-MIN-035 | Minor | `_CORE_NUMBER` 下划线过宽（`_1`/`1_`） | **CLOSED** — `_` 仅夹在数字之间 |
| WP5-R1-REV-MIN-036 | Minor | host_paths fold 缺口（`╱`/`∼`/`⁓` 等） | **CLOSED** — 扩展 slash/punct fold；corpus 正例 |
| WP5-R1-REV-MIN-037 | Minor | 裸单数字日期误拒（过严；非 yaml.org !!timestamp） | **CLOSED** — `_IMPLICIT_TIMESTAMP` 双分支；`2001-1-1` ACCEPT |
| WP5-R1-REV-MAJ-016 | Major | Patch SHA 在新增文件由 untracked 转为 committed 后变化 | **CLOSED** — baseline 新路径统一 `/dev/null` diff；BASE-only 临时 index 与 committed 状态复算一致 |
| EXT-REVIEW-REAUDIT-2 | — | 第二轮修复后外部重审 | **CLOSED** |
| EXT-REVIEW-REAUDIT-3 | — | 第三轮修复后外部签核 | **CLOSED** — 复审项 BLK-003/MAJ-010 已修复 |
| EXT-REVIEW-REAUDIT-4 | — | 第四轮外部签核 | **CLOSED** — Round-4 Blocker/Major 已在 worktree 闭合 |
| EXT-REVIEW-REAUDIT-5 | — | 第五轮外部签核 | **CLOSED** — MAJ-005/008/011/015 已由 REAUDIT-6 独立确认 |
| EXT-REVIEW-REAUDIT-6 | — | 第六轮外部签核（最终） | **CLOSED / PASS** — 全部 findings 闭合；§10 SHA 在提交状态转换前后稳定，完整 `PR-CORRECTNESS` 独立复现 |

**host_paths / strict_yaml 策略注记：** 裸 `~alice` / `~root/`（无路径续段）**defer**；此后 **仅当语料破口再开 finding**。

---

## 13. 外部审核检查清单（建议）

- [x] Schema `$id` / closed union 与 formal contract 一致（Round-4：`provider_id` / `canonical_encoding_version`）
- [x] Shared ref wire shape 与 digest projection 可接受为 R1 最小闭合（含 shared structured child identity）
- [x] Conformance Harness owner 边界（未迁入 backend/shared_kernel 业务模块）
- [x] Strict YAML 拒绝矩阵充分（JSON 指数零填充；Core 下划线收紧；YAML 1.1 !!timestamp 双分支）
- [x] 测试 oracle 独立性（formal §4.4 + Python/Rust dual-impl vectors + shared-structured；临时 shared root）
- [x] `PR-CORRECTNESS` 组件可复现（conformance pytest；SHA 脚本 exit 0）
- [x] REAUDIT-6：确认 MIN-037 + 既有 FIXED 项；语料全绿；§10 SHA 与 verify 脚本一致

---

## 14. Sign-off

**PASS — No blocking findings.**

`WP5 R1 scenario/golden/protocol/result schema and strict closure sign-off passed; ready to enter WP5 R2.`

- 不是 Phase 1 complete
- 全部 findings → **CLOSED**
- `EXT-REVIEW-REAUDIT-6` → **CLOSED / PASS**
- 本轮创建唯一签核提交：`feat(vnext): add WP5 R1 conformance schema closure`
