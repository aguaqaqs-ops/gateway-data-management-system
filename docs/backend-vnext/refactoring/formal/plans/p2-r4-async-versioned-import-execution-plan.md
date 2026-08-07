# P2-R4 Async Versioned Import Staged Execution Plan

状态：Accepted — Ready for staged implementation

日期：2026-08-06

适用范围：`P2-R4 — Async Versioned Import`

Owner：Repository Service delivery（阶段划分、green gate、handoff和实现提示词）

详细设计：
[P2-R4 Async Versioned Import Detailed Implementation Design](p2-r4-async-versioned-import-implementation-design.md)

上位执行规则：
[P2 Versioned Repository Execution Checklist](p2-versioned-repository-execution-checklist.md) §§1–2、§6。

本文把P2-R4拆成适合单次代码实现对话上下文容量的独立green阶段。本文不拥有public、
persisted或cross-owner语义；实现者必须直接读取详细设计列出的owning contracts。

## 1. Delivery strategy

P2-R4不采用“一次实现全部import”的大提交。拆分原则：

1. contracts、persistence、package、provider和verification先各自形成可测试构件；
2. worker只在上述构件ready后组合；
3. startup recovery和admin CLI在HTTP route激活前完成；
4. public route只在accept、execution、recovery、cleanup和poll均为真实行为时进入OpenAPI；
5. 最后一阶段只做全矩阵、正式container gate、必要修复和handoff；
6. 每阶段只读取和修改直接相关路径，避免单次对话装载全部历史P2材料。

依赖图：

```text
S1 Wire contracts
  -> S2 Durable operation store
  -> S3 Bounded package validator
  -> S4 Candidate A private-ref/CAS adapter
  -> S5 Verification engine
  -> S6 Worker orchestration
  -> S7 Startup reconciliation and shutdown
  -> S8 Private recovery CLI
  -> S9 HTTP activation and admission
  -> S10 Full fault/Dolt/Compose gate and handoff
```

不得并行实现共享文件的相邻阶段。一次实现对话只能执行一个stage；不得在“顺手”修复中
跨入下一stage。

## 2. Common execution discipline

每阶段开始前必须：

```bash
git rev-parse HEAD
git status --short --branch
git log -8 --oneline --decorate
```

首阶段HEAD必须包含P2-R3 handoff `a0ef723e0a8043beee09a0b0cb4f1408db5ffc5e`
及本设计/执行计划的文档commit；后续阶段必须包含上一阶段handoff commit。Worktree不clean或
HEAD变化时先报告差异，不覆盖、回退或重写用户改动。

每阶段共同规则：

- 完整读取本阶段列出的authority和直接相关现有代码/测试；
- 先增加失败的contract/unit/integration test，再实现最小production behavior；
- 只使用`apply_patch`做手工编辑；
- 删除、移动或更改export前先用`rg`列出consumer；
- production代码不得导入P2-R1 workflow、fixture、matrix、target gate或Candidate B；
- 不修改Backend、Repository Client、Rust/canonical owner或P2-R5路径；
- 不新增compatibility shim、generic framework、public stub route或future abstraction；
- 每个建议commit前运行定向tests、受影响package lint/type和`git diff --check`；
- 不提交已知失败状态；只有stage gate全绿才创建该stage建议commit；
- 完成后输出stage handoff，不自动进入下一stage。

Python package完整四命令：

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest -q
```

自S5期间的测试基础设施改造（`aa33d11`）起，`repository_service`的权威全量入口是
`./vnext/scripts/run-tests.sh`：fast package单进程，service先`-m "not serial"`并行
（`-n auto --dist loadgroup`），再`-m serial -n 0`。S6及之后的stage gate中第四条命令对
`repository_service`一律读作`./vnext/scripts/run-tests.sh`。裸`uv run pytest -q`现在会自动
并行，timing-sensitive和real-Dolt测试在该模式下不可靠，只允许用于开发期定向调试。

新增测试必须遵守`docs/backend-vnext/testing-conventions.md`：

- 依赖真实dolt（`lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()`）必须显式加
  `@pytest.mark.integration`；
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`）或要求进程级串行的
  必须显式加`@pytest.mark.serial`；
- 不得手写`skipif(not dolt_available())`，由`tests/conftest.py`统一分类与skip。

测试可在开发过程中定向运行，但stage commit前必须执行该阶段明确要求的package gate。
S10必须执行contracts和service两个package的全部四命令。

## 3. Stage summary and context sizing

| Stage | Primary outcome | Expected context size | Suggested commit |
| --- | --- | --- | --- |
| S1 | wire DTO/header/enums/result invariants | small：contracts约2–4 files | `feat(repository): finalize Versioned import wire contracts` |
| S2 | control DB v7与durable operation store | medium：DB/store约5–8 files | `feat(repository): add durable Versioned import operation store` |
| S3 | streaming zstd/tar和closed manifest | medium：validator/settings/tests约4–7 files | `feat(repository): validate bounded import packages` |
| S4 | Candidate A private ref/evidence/CAS primitives | medium-high：provider/process/tests约5–9 files | `feat(repository): add Candidate A import ref primitives` |
| S5 | verification与unknown-type matrix | medium-high：verification/Arrow/tests约5–8 files | `feat(repository): verify Versioned import candidates` |
| S6 | worker claim、writer ownership和happy path | high：组合约8–12 files | `feat(repository): execute durable Versioned import workers` |
| S7 | startup recovery、shutdown和artifact lifecycle | high：runtime/recovery约8–12 files | `feat(repository): reconcile interrupted Versioned imports` |
| S8 | stopped-service private admin CLI | medium：CLI/store/provider/tests约5–8 files | `feat(repository): add private import recovery CLI` |
| S9 | Submit/GetOperation route、admission和OpenAPI | medium-high：HTTP/composition/tests约7–11 files | `feat(repository): activate import and operation routes` |
| S10 | full fault matrix、Dolt、Compose和handoff | high但以tests/ops为主 | `test(repository): close Versioned import delivery gate` |

S4、S5、S6、S7和S10不合并，避免单次对话同时装载provider internals、Arrow mapping、
runtime lifecycle和container evidence。

## 4. Per-stage handoff

每阶段最终回复必须包含：

```text
round: P2-R4
stage: P2-R4-S<n>
start_sha:
commit_sha:
head_sha:
branch:
worktree_clean: yes/no

modified_paths:
explicit_non_goals_preserved:
implemented_behavior:
validation_commands:
  - command:
    result: pass/fail + counts/key output
fault_points_covered:
old_reference_searches:
first_failures_and_fixes:
known_limitations:
stage_exit: pass/no-go
next_stage_ready: yes/no
next_stage: P2-R4-S<n+1>|none
```

未创建commit、worktree不clean、required gate失败或required integration不可运行时，
`stage_exit`必须为`no-go`，不得声称下一阶段ready。

## 5. S1 — Wire contracts

### Goal

收口SubmitVersionedImport/GetOperation的contracts-owned wire shape，移除body key并补齐两个
policy与完整result binding。本阶段不修改Service route、DB或runtime。

### Allowed paths

```text
vnext/repository_contracts/src/gateway_repository_contracts/headers.py
vnext/repository_contracts/src/gateway_repository_contracts/versioned.py
vnext/repository_contracts/src/gateway_repository_contracts/types.py
vnext/repository_contracts/src/gateway_repository_contracts/__init__.py
vnext/repository_contracts/tests/
vnext/repository_contracts/uv.lock       # only if dependency metadata actually changes
```

### Required behavior and gate

- 新增contracts-owned `VerificationPolicy`和`UnknownTypePolicy`；
- 新增import header model，key长度1..255；
- 从request body删除`idempotency_key`；
- policy默认STRUCTURAL/REJECT；
- target为literal main，完整result echo；
- four-state result/error组合通过Pydantic validation拒绝非法shape；
- closed models/OpenAPI-compatible serialization保持普通Pydantic语义；
- contracts完整四命令、`git diff --check`和定向old body-key search通过。

### Code implementation prompt

```text
请在仓库 /root/gateway-data-management-system 正式执行 P2-R4-S1 — Wire Contracts。

只执行本stage，不进入S2，不修改任何Service route、SQLite、worker、provider、client、
Backend、Rust或部署文件。开始前运行git rev-parse/status/log，确认HEAD包含P2-R3 handoff
a0ef723e0a8043beee09a0b0cb4f1408db5ffc5e和P2-R4设计文档，且worktree clean；否则先报告，
不得覆盖或回退用户改动。

必须完整读取：
- docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md §§4–5；
- Repository Service Contract §§5–6、§§10–11；
- 当前repository_contracts versioned.py、headers.py、types.py、__init__.py及对应tests。

Allowed paths仅限repository_contracts的上述source/tests/必要lockfile。先写contract tests，
然后实现：contracts-owned VerificationPolicy和UnknownTypePolicy；ImportRequestHeaders；
SubmitVersionedImportRequest从body移除idempotency_key；target_ref只接受main；两个policy使用
正式default；VersionedImportResult补expected_commit_id、completed_verification_policy、
unknown_type_policy；VersionedOperation强制四态result/error组合。保持SimpleError最小shape，
不要增加wire schema version、compat alias、generic envelope或P2-R5 DTO改造。

验证：在vnext/repository_contracts运行uv lock --check、ruff、mypy、pytest -q；运行
git diff --check；用rg确认SubmitVersionedImportRequest/body test不再出现idempotency_key，
但header model与普通create/upload header仍保留正确key语义。

全部通过后创建单个green commit：
feat(repository): finalize Versioned import wire contracts

最后按执行计划§4输出handoff，next_stage只能是P2-R4-S2，不要开始S2。
```

## 6. S2 — Durable operation store and control DB v7

### Goal

增加forward-only v7 migration和独立durable import operation store，闭合idempotency、四态、
atomic claim、result/error、replay count、recovery audit和artifact consumed persistence。本阶段
不注册route、不启动worker、不调用Dolt。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/control_db.py
vnext/repository_service/src/gateway_repository_service/versioned_import/__init__.py
vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
vnext/repository_service/src/gateway_repository_service/mutation_store.py   # only artifact lifecycle integration
vnext/repository_service/tests/test_import_operation_store.py
vnext/repository_service/tests/test_auth_lifecycle.py                       # migration coverage only
```

### Required behavior and gate

- v6 -> v7、fresh v7、rollback-on-failure和newer-version fail closed；
- 不改写现有sync mutation table语义；
- repository-scoped key hash/fingerprint唯一；
- QUEUED insert与same/different fingerprint lookup；
- FIFO atomic claim QUEUED -> RUNNING；
- status/result/error DB和typed validation；
- replay count最多从0到1；
- manual terminal correction与audit同transaction；
- artifact consumed/bytes-deleted字段与查询；
- repository manual barrier和artifact protected-reference查询；
- concurrent store calls使用既有connection ownership规则；
- service完整四命令和DB定向tests通过。

### Code implementation prompt

```text
请执行 P2-R4-S2 — Durable Operation Store。仓库为
/root/gateway-data-management-system。只执行S2，不实现package、Dolt、worker、recovery CLI
或HTTP route。

开始前核对HEAD/worktree和S1 handoff；若HEAD不是S1 green commit或工作树不clean，先报告。
完整读取P2-R4详细设计§§5、8，Repository Service Contract §11、§12，以及当前control_db.py、
mutation_store.py和migration tests。保留P2-R3 create/upload ledger及user_version 1..6全部行为。

按详细设计实现单次v7 transactional migration。优先新增独立
repository_import_operations和repository_import_recovery_audit，而不是重建已通过R3 gate的
sync mutation表。为artifact_lifecycle增加consumed_by_operation_id、consumed_at、
bytes_deleted_at。实现typed ImportOperationStore：claim-or-replay、different fingerprint
conflict、atomic FIFO claim、terminal transition、result/error validation、automatic replay
count 0->1、manual correction+audit transaction和artifact consumed cleanup记录。Raw key不得
进入store API以外的持久化/log；store只接收hash。

Store还必须提供：未解决MANUAL的repository barrier查询；按artifact ID查询全部operation
references并区分QUEUED/RUNNING/MANUAL protected reference；manual correction后可原子解除
barrier。不得为此新增operation状态。

先写migration/store/concurrency tests。不得添加generic journal、checkpoint state、lease、
fencing、UNKNOWN/APPLIED/VERIFIED或worker abstraction。本阶段不得修改app.py/runtime.py。

在vnext/repository_service执行uv lock --check、ruff、mypy、pytest -q，并运行
git diff --check。确认现有create/upload migration/recovery tests仍通过。

全部通过后提交：
feat(repository): add durable Versioned import operation store

输出S2 handoff，next_stage=P2-R4-S3，不要继续。
```

## 7. S3 — Bounded package validator

### Goal

实现stdlib-based streaming zstd/tar validator、closed manifest和server-owned extraction，
精确区分single entry与total decompressed stream limits。本阶段只提供可调用构件，不接worker。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/src/gateway_repository_service/versioned_import/package.py
vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
vnext/repository_service/tests/test_import_package.py
vnext/repository_service/tests/test_settings.py
```

### Required behavior and gate

- Python 3.14 stdlib zstd/tar；无新compression dependency；
- strict two-entry order和regular-file rules；
- raw compressed size/SHA incremental verification；
- manifest 16 MiB、replay 200 MiB、payload total 4 GiB、decoder output 4 GiB；
- decoder counter包含tar headers/padding；
- no `extractall`、no full materialization；
- path/link/device/FIFO/PAX/sparse/extra/trailing拒绝；
- strict UTF-8、duplicate JSON key、closed manifest、sort/uniqueness/PK checks；
- boundary-1/equal/boundary+1和chunked reader tests；
- failure staging cleanup且原artifact保留。

### Code implementation prompt

```text
请执行 P2-R4-S3 — Bounded Package Validator，只实现package/manifest/settings及测试，不接入
operation store、worker、provider或HTTP。

开始前核对S2 handoff和clean worktree。完整读取P2-R4详细设计§§6–7、Canonical Storage
§6.1、Repository Service Contract §9，以及当前artifact layout/settings。使用Python 3.14
stdlib compression.zstd和tarfile，不新增第三方zstd dependency。

先写恶意archive与精确boundary tests，再实现counted decoder + streaming tar reader。
禁止extractall，禁止把完整archive或replay.sql读入内存，禁止使用archive member name直接
构造path。Manifest只允许在完整staging且确认<=16 MiB后做有界解析。严格要求
manifest.json、replay.sql两个regular entry且顺序固定；拒绝traversal、
duplicate、extra、link/device/FIFO/sparse、PAX/GNU extended metadata、trailing malformed data。

实现四个独立limit：compressed artifact沿用256 MiB upload binding；manifest 16 MiB；
replay.sql 200 MiB；total member payload和zstd decoder累计输出各4 GiB。Decoder输出counter
必须包含tar header/padding。实现strict UTF-8、duplicate JSON object key detection和closed
Pydantic manifest，验证name、sort、uniqueness、PK reference、row_count和bounded sql_type。

不得解析replay.sql语义，不计算business digest，不支持gzip/multipart/URL/path。
在vnext/repository_service运行完整四命令和git diff --check。

通过后提交：
feat(repository): validate bounded import packages

输出S3 handoff，next_stage=P2-R4-S4。
```

## 8. S4 — Candidate A private-ref and CAS adapter

### Goal

建立production-owned Candidate A adapter，提供deterministic private ref、marker evidence、
expected parent、second main check和serialized internal ref update。不得复用probe workflow。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/candidate_a/
vnext/repository_service/src/gateway_repository_service/versioned_import/ports.py
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/versioned_import/errors.py
vnext/repository_service/src/gateway_repository_service/process.py          # narrow shared primitive only
vnext/repository_service/src/gateway_repository_service/providers.py        # only extracting a narrow helper
vnext/repository_service/src/gateway_repository_service/settings.py         # catalog_parallel_workers only
vnext/repository_service/tests/test_import_provider.py
vnext/repository_service/tests/test_distribution_boundaries.py
vnext/repository_service/tests/test_import_package.py                       # cross-stage regression only
```

`candidate_a/` 为 probe 与 production 共享的中性 Candidate A primitive 层（ref validation、SQL/catalog/stream helper、Dolt CLI session）。`versioned_import/dolt_cli.py`、`dolt_candidate_a_sql.py` 等已迁入 `candidate_a/`；probe `providers.py` 与 production `versioned_import/provider.py` 均只依赖该层，不得交叉依赖对方 stage 模块。

`settings.py` 的S4授权仅限 `catalog_parallel_workers` 及其bounded validator：默认值为2，
允许范围为1..4。该值只限制单次catalog projection的内部并行，不是node-wide Dolt CLI
capacity保证。S4不得在`process.py`建设node-wide limiter，也不得把per-session catalog memo
描述为真实内存预算。未来可调资源参数集中由`settings.py`拥有；扩大当前validator上限必须
同时更新正式容量约束、并发/RSS/p95证据和对应tests，不得只修改production环境变量。

### Required behavior and gate

- deterministic private ref和exact marker；
- create/read/checkout/delete private ref；
- replay通过stdin file；
- unique marker/candidate/parent evidence；
- read catalog/stream ports供S5使用；
- initial/second main check helper；
- internal expected-value publish与readback；
- timeout/nonzero/readback mismatch分类为mismatch或ambiguous；
- no production import of workflow/fixtures/matrix/SqlServerProvider；
- real Dolt integration覆盖private branch和main update；
- process output/SQL/path不泄漏。
- S3 cross-stage regression：checksum-enabled zstd frame跨64 KiB compressed chunk且equal
  decoder boundary成功；
- 双tar EOF后完整512-byte zero padding成功，partial/non-zero trailing继续拒绝。

### Code implementation prompt

```text
请执行 P2-R4-S4 — Candidate A Import Ref Primitives。只实现production provider port/adapter
和定向tests；不实现verification、worker、recovery、CLI或HTTP。

开始前核对S3 handoff。完整读取P2-R4详细设计§§3、6–7、10–11、20，Canonical Storage
Contract §6.1，P2-R1 feasibility contract §§3–5和v8 go decision。检查当前DoltRunner、
OfflineCliProvider、create adapter和provider tests，
但不得把workflow.py、fixtures.py、matrix.py、target_gate.py或Candidate B当production authority。

在修改provider前先补齐并运行S3 cross-stage regression。测试必须使用Python 3.14 stdlib zstd
compressor的content checksum选项，并通过等价于临时monkeypatch
`versioned_import.package._COMPRESSED_READ_CHUNK_BYTES = len(compressed) - 4`的测试seam，
强制4-byte checksum trailer跨compressed read boundary；decompressed tar stream必须恰好等于
`max_decompressed_tar_stream_bytes`且验证成功。另测双EOF后追加完整512-byte zero padding block
仍成功，而1/511/513-byte partial zero tail和任一非零trailing必须失败。该测试只可修改
`test_import_package.py`并冻结详细设计§6/§20既有S3语义；若现有validator不能通过，暂停S4、
报告no-go并将S3修复与provider提交分离，不得借S4扩大package格式或修改counter解释。

建立gateway_repository_service.versioned_import下的窄port和Candidate A adapter。实现
read_ref、create/checkout/delete private ref、stdin replay、exact marker commit、marker/ref/
parent inspection、catalog/stream接口、main expected check、内部ref update和readback。Private ref
固定gateway-import-<operation uuid hex>，marker固定
gateway-versioned-import operation_id=<canonical uuid>。

CAS只在caller已持有root+repository writer ownership时使用：main必须先等于expected，更新后
必须readback candidate。允许adapter内部使用Dolt branch force-move primitive，但不得公开
force参数、关闭expected check或让admin调用。Command timeout/nonzero和readback矛盾必须返回
typed ambiguous evidence，不猜测not-published。Replay SQL只走stdin fd，不进入argv/log。

先写fake adapter contract tests，再写真实Dolt integration覆盖expected parent、unique marker、
private cleanup、second mismatch、successful update和ambiguous seam。若提取providers.py helper，
先rg consumer并保持P2-R1 tests不变。

运行service完整四命令、git diff --check和production-to-probe import方向搜索。
通过后提交：
feat(repository): add Candidate A import ref primitives

输出S4 handoff，next_stage=P2-R4-S5。
```

### Accepted S4 exit — 2026-08-07

```text
implementation_head: d3bafc0eb138093761a14925d2e8e3336a0b382c
targeted_gate: 379 passed
service_full_pytest: 672 passed, 1 skipped
worktree_clean: yes
stage_exit: pass
next_stage_ready: yes
next_stage: P2-R4-S5
```

S4保留`catalog_parallel_workers=2`和1..4 validator；Candidate A session只做固定4项
catalog memo。Node-wide Dolt CLI capacity limiter、真实catalog memory budget和production资源
调优统一defer到S7 runtime composition或S9 capacity owner。纯文档scope同步不改变已验证运行
行为，因此不要求重复执行service完整回归。

## 9. S5 — Verification engine and unknown types

### Goal

实现独立verification component及完整3×2 policy matrix，复用contracts-owned policy enums和
既有Arrow mapping，不激活P2-R5 public reads。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py
vnext/repository_service/src/gateway_repository_service/versioned_import/ports.py
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/arrow_mapping.py
vnext/repository_service/src/gateway_repository_service/candidate_a/dolt_cli.py   # minimal type projection via type_catalog / _load_table_schema without catalog_count
vnext/repository_service/src/gateway_repository_service/fixtures.py             # shared expected_tables linkage for unknown spelling literal preservation
vnext/repository_service/src/gateway_repository_service/versioned_import/models.py   # wire enum single-source cleanup (remove ArrowUnknownTypePolicy alias)
vnext/repository_service/tests/test_import_verification.py
vnext/repository_service/tests/test_p2_r1_primitives.py       # only shared mapping regressions if required
vnext/repository_service/tests/test_import_provider.py        # fake provider sync for read_type_catalog Protocol extension
```

### Required behavior and gate

- NONE仍做REJECT所需最小type inspection；
- STRUCTURAL exact table/schema/row_count comparison；
- FULL_SCAN包含STRUCTURAL并bounded scan；
- REJECT/STRINGIFY正交；
- known type不因STRINGIFY降级；
- STRINGIFY large_string metadata、NULL和conversion failure；
- unknown spelling在STRUCTURAL exact比较；
- no business digest、ordering或public row route；
- real Candidate A catalog/scan integration。

### Code implementation prompt

```text
请执行 P2-R4-S5 — Verification Engine。只实现import内部verification和必要的共享Arrow修正，
不实现worker/recovery/HTTP/P2-R5 reads。

开始前核对S4 handoff。读取P2-R4详细设计§12、Repository Service Contract §10 exact mapping、
Canonical Storage §6，以及当前arrow_mapping.py和S4 provider port。Wire policy必须从
gateway_repository_contracts导入，不在Service再定义第二套enum。

先写3 verification × 2 unknown-type完整matrix。实现：NONE跳过manifest structural/full scan，
但REJECT仍读取最小catalog并在publication前拒绝unknown；STRUCTURAL exact比较user table set、
column order/type/nullability、PK order、manifest row_count；FULL_SCAN按validated row/byte bounds
读取所有user rows，要求Arrow conversion成功且scanned count匹配。

STRINGIFY只作用于unknown type，输出nullable Arrow large_string，NULL保持NULL，metadata至少
gateway.sql_type=<original>和gateway.lossy=true；known type保持exact mapping；转换失败即失败。
不得计算business digest、canonical equality、排序保证，不得注册catalog/row HTTP route。

覆盖真实Candidate A catalog spelling和bounded scan。运行service完整四命令、
git diff --check及旧verification名称搜索。

通过后提交：
feat(repository): verify Versioned import candidates

输出S5 handoff，next_stage=P2-R4-S6。
```

### Accepted S5 exit — 2026-08-07

```text
implementation_head: be6e2bb (+ post-review cleanup commit on same branch)
run_tests_sh: 1038 passed, 1 skipped (repository_service: 703 parallel + 6 serial, 1 skipped)

S5 functional_changes (a7dfc0d..be6e2bb, ⊆ revised §9):
  commits: f7fcbb2, e9d17aa, 1c1b3a4, be6e2bb
  11 implementation paths ≡ §9 allowed paths (includes versioned_import/models.py)

S5 test_infrastructure (aa33d11, outside §9):
  34 files: AGENTS.md, testing-conventions/fixtures docs, pyproject.toml×6,
    Dockerfile, uv.lock, process.py, run-tests.sh, conftest + 20 test files
  independent concern: xdist parallelism, marker layering, offline dolt HOME

Do not use a single modified_paths ≡ §9 equation over a7dfc0d..HEAD (42 files).

known_limitations:
  - prior P3 six items (_refs_for_commit, _as_import_provider_error branches,
    catalog path duplication, error code literals, __all__ UnknownTypePolicy,
    test concat_batches materialize)
  - manifest charset gate vs normalizer (ENUM non-ASCII literals)
  - _STREAM_PROVIDER_FAULTS still includes bare ValueError/TypeError
  - marker auto-classification residual risk (manual mv dolt -m unit verification)

stage_exit: pass
next_stage_ready: yes
next_stage: P2-R4-S6
```

## 10. S6 — Worker orchestration and direct happy path

### Goal

组合S2–S5构件，完成durable claim、global bounded workers、per-repository ownership、完整
private-ref publication happy path、terminal persistence和success artifact cleanup。本阶段仍不
注册HTTP route，也不把worker接入默认ASGI lifespan。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py
vnext/repository_service/src/gateway_repository_service/versioned_import/command.py
vnext/repository_service/src/gateway_repository_service/versioned_import/locks.py
vnext/repository_service/src/gateway_repository_service/versioned_import/faults.py
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
vnext/repository_service/src/gateway_repository_service/versioned_import/package.py
vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
vnext/repository_service/src/gateway_repository_service/versioned_import/ports.py
vnext/repository_service/src/gateway_repository_service/versioned_import/errors.py
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/tests/test_import_worker.py
vnext/repository_service/tests/test_import_worker_integration.py
vnext/repository_service/tests/support/                          # R4-specific worker harness only
```

`models.py`、`ports.py`、`errors.py`只允许additive改动（新增worker侧result/binding类型、
port方法或error code），不得改变S1–S5已固定的wire/DTO语义与现有error code字符串。
`tests/support/`只允许新增R4 worker harness，不得改动S7 process harness以外的既有文件语义。

### Required behavior and gate

- configurable default4 worker pool和repository lock registry；
- active/manual repository-aware atomic FIFO claim，无long SQLite transaction或worker starvation；
  FIFO排序键是per-repository `enqueue_sequence`（详细设计§9），不是`created_at, operation_id`；
- package -> first check -> private ref -> replay -> marker -> verification -> second check -> publish；
- exact parent/marker/result bindings；
- failure mapping和no hidden retry；`ImportVerificationError`的两个code与
  `ImportProviderError`必须分别映射，不得依赖provider fault tuple区分
  （`_STREAM_PROVIDER_FAULTS`仍包含裸`ValueError`/`TypeError`，见S5 known_limitations）；
- SUCCEEDED+artifact consumed同transaction：S2的`mark_succeeded`已在同一transaction内调用
  `record_artifact_consumed`，S6只组合调用，不得重新实现或在worker层再开transaction；
- 同artifact存在QUEUED/RUNNING/MANUAL reference时禁止premature cleanup；
- private ref cleanup ordering；
- 新增settings：`max_import_workers`（默认4）为必需，`max_queued_imports`、
  `import_shutdown_grace_seconds`、`import_headroom_bytes`可留到S7/S9消费点再加；新增int字段
  必须同步加入`settings.py`的`_bounds_must_be_positive`显式字段列表，否则不受校验；
- direct store/worker tests覆盖same repository serialization和cross-repository bounded parallelism，
  这两类测试依赖时间预算，必须标`@pytest.mark.serial`；real Dolt worker测试必须标
  `@pytest.mark.integration`；零skip/xfail；
- fault seam存在但不进入production input；
- real Dolt happy path，不注册routes/lifespan；
- gate第四条命令为`./vnext/scripts/run-tests.sh`（见§2），不是裸`uv run pytest -q`。

### Code implementation prompt

```text
请执行 P2-R4-S6 — Durable Import Worker Orchestration。本stage组合已有构件并完成direct
worker happy path，但不得注册HTTP route，也不得在ServiceRuntime默认启动worker；startup和
shutdown integration属于S7。

开始前核对S5 handoff（含known_limitations）。完整读取P2-R4详细设计§§9、11–13、16、19及
S2–S5 production APIs。先写direct store/worker tests，再实现ImportWorkerPool、repository lock
registry、operation executor和test-only fault injector。

可直接复用的既有API，不要重新实现或另建并行抽象：

- store（`versioned_import/store.py`）：`claim_or_enqueue`、`get_operation`、
  `claim_next_queued(repository_id)`、`claim_if_queued(operation_id)`、`mark_succeeded`、
  `mark_failed`、`increment_automatic_replay_count`、`apply_manual_correction`、
  `has_unresolved_manual_barrier(repository_id)`、`list_artifact_references`、
  `can_delete_artifact_bytes`、`mark_artifact_bytes_deleted`；
- provider port（`versioned_import/ports.py` `VersionedImportProvider`）：`read_ref`、
  `create_private_ref`、`checkout_private_ref`、`replay_sql(private_ref, replay_path,
  cancellation=None)`、`commit_operation_marker`、`inspect_marker`、`read_catalog`、
  `read_type_catalog`、`stream_table(candidate, table, policy)`、
  `publish_main(expected_commit, candidate)`、`delete_private_ref(private_ref,
  expected_candidate=None)`，result union为`MarkerInspection{Zero,Unique,Ambiguous}`与
  `PublishMain{Published,Mismatch,Ambiguous}`；
- verification：`verify_import_candidate(provider, *, candidate, manifest,
  verification_policy, unknown_type_policy) -> ImportVerificationResult`，失败抛
  `ImportVerificationError(code, detail=...)`；
- models：`derive_private_ref_name`、`derive_operation_marker`、`ImportRequestBinding`、
  `StoredImportOperation`、`is_protected_operation_status`。

默认max_import_workers=4，可配置；新增settings int字段必须同时加入`_bounds_must_be_positive`
的显式字段列表。Dispatcher必须先排除active repository和未解决MANUAL barrier，reserve
repository ownership后再claim_if_queued；不得先claim同repository多个RUNNING row让worker阻塞
争锁。FIFO排序键是S2已落地的per-repository `enqueue_sequence`，不是`created_at,
operation_id`（`utc_now_iso()`只有秒级精度，同秒会退化成UUID序，且
`test_claim_next_queued_is_fifo`已固定该语义）；跨repository不要求全局FIFO，只要求无
starvation。若dispatcher需要跨repository候选查询，可在`store.py`新增只读方法，但不得改变
`claim_next_queued`现有per-repository FIFO语义。Claim必须SQLite atomic，长Dolt effect期间不
持有DB transaction或scheduler lock。Repository ownership覆盖initial main check到terminal
persistence/cleanup。执行严格顺序：validate artifact/package；first main==expected；private
ref；stdin replay；exact marker/parent；requested verification；second main==expected；internal
publish/readback；persist SUCCEEDED result与artifact consumed；delete private ref；delete
package并记录bytes_deleted。SUCCEEDED与artifact consumed的同transaction保证由`mark_succeeded`
内部的`record_artifact_consumed`提供，worker只调用它。

实现四个stable failure映射。`ImportVerificationError`按其code分别映射到`IMPORT_REJECTED`与
`VERIFICATION_FAILED_NOT_PUBLISHED`，`ImportProviderError`按effect证据映射；不得依赖provider
fault tuple区分类型（`_STREAM_PROVIDER_FAULTS`仍包含裸`ValueError`/`TypeError`）。当前进程已
证明无effect的validation/provider failure直接普通FAILED；任何publication/ref/marker ambiguity
转MANUAL并保留artifact/ref。普通failure不隐藏retry。成功cleanup失败不得改变result。public
error detail不得暴露private ref、filesystem path、SQL、完整stderr或row值。

实现详细设计列出的fault points，但注入器只能由tests直接构造，不能来自HTTP/body/header或
production env默认。测试同repository严格串行、不同repository不超过global worker bound；这两
类时间预算测试必须标`@pytest.mark.serial`，真实Dolt worker测试必须标
`@pytest.mark.integration`，不得手写`skipif(not dolt_available())`，零skip/xfail。
运行service完整四命令（第四条为`./vnext/scripts/run-tests.sh`）、真实Dolt direct
integration、git diff --check。

通过后提交：
feat(repository): execute durable Versioned import workers

输出S6 handoff，next_stage=P2-R4-S7。
```

## 11. S7 — Startup reconciliation, shutdown and artifact lifecycle

### Goal

实现evidence-first startup recovery、最多一次automatic replay、worker runtime composition、
graceful cancellation/reap和consumed artifact readiness。本阶段仍不注册import/operation route。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py
vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/runtime.py
vnext/repository_service/src/gateway_repository_service/process.py
vnext/repository_service/src/gateway_repository_service/mutation_reconciliation.py
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/tests/test_import_recovery.py
vnext/repository_service/tests/test_import_shutdown.py
vnext/repository_service/tests/test_mutation_readiness.py
vnext/repository_service/tests/support/                         # R4-specific process harness only
```

### Required behavior and gate

- startup ordering：DB/provider/sync reconcile/import reconcile/workers/ready；
- QUEUED requeue、SUCCEEDED cleanup、ordinary FAILED no retry、MANUAL retain；
- published marker补SUCCEEDED；
- private candidate继续verification/CAS且SQL replay count不增加；
- no commit自动replay恰好一次，count effect前持久化；
- second/no/ambiguous evidence转MANUAL；
- startup从durable `status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED` rows重建repository
  barrier并跳过同仓库QUEUED operation；
- shutdown stop intake/claim、grace、cancel child、join、DB close、root unlock；
- interrupted active operation保持RUNNING；
- consumed artifact readiness与R3 missing-artifact regression；
- required crash tests使用新进程，不只mock exception。

### Code implementation prompt

```text
请执行 P2-R4-S7 — Startup Reconciliation and Graceful Shutdown。不得注册public import或
operation route；admin CLI属于S8。

开始前核对S6 handoff。读取P2-R4详细设计§§14–16、External Effect and Recovery Contract
§5，以及当前ServiceRuntime、DoltRunner、sync reconciler和R4 worker/store/provider。

先建立真实restart/process-crash harness。实现startup：在root lock、DB migration、provider
capability和R3 sync reconciliation后，先reconcile import，再启动worker，最后ready。
规则严格为QUEUED requeue；SUCCEEDED残留cleanup；普通FAILED无retry；MANUAL保留；published
matching marker补SUCCEEDED；unique private candidate继续requested verification/CAS且不重放
SQL；无commit+artifact完整+count0先transaction写count1再自动replay；count1仍无证据、multiple
marker、parent/ref/artifact矛盾转MANUAL。

在worker开始claim前，从durable
`status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED` rows重建repository barrier；同
repository已QUEUED operation保持QUEUED，其他repository继续执行。Barrier不能只依赖上个
进程内存状态。

实现shutdown stopping flag、停止claim、configured grace、per-operation cancellation、Dolt
process-group terminate/kill/wait/reap、worker join、DB close、root lock最后释放。Shutdown中断不
写普通FAILED，保留RUNNING/evidence。不得使用daemon thread逃过join。

更新artifact readiness：无consuming success的missing upload仍阻塞；matching SUCCEEDED import
后的missing bytes合法；QUEUED/RUNNING/MANUAL missing必须正确分类。Manual operation一旦已完整
分类不应永久拖垮整个Service readiness。

运行service完整四命令、required restart/crash tests、git diff --check。不得skip/xfail本阶段
required cases。

通过后提交：
feat(repository): reconcile interrupted Versioned imports

输出S7 handoff，next_stage=P2-R4-S8。
```

## 12. S8 — Private recovery CLI and audit

### Goal

实现stopped-service/root-lock private inspect/apply CLI，闭合SUCCEEDED与NOT_PUBLISHED两种
evidence-only correction、audit和negative actions。不增加public API。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/versioned_import/admin.py
vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/tests/test_import_admin_cli.py
vnext/repository_service/tests/support/                         # CLI subprocess harness only
vnext/repository_service/pyproject.toml                         # only if a private console script is chosen
vnext/repository_service/uv.lock                               # only if pyproject dependency metadata changes
```

### Required behavior and gate

- module CLI inspect/apply；默认无mutation；
- service运行/root lock busy立即失败；
- exact DB version和MANUAL-only target；
- apply前fresh evidence；
- matching published补完整SUCCEEDED result；
- NOT_PUBLISHED默认IMPORT_REJECTED/operator_confirmed_not_published；
- precise evidence才使用expected/verification code；
- correction与audit同transaction；
- apply后允许的cleanup；
- no main move、SQL、history delete、force/bypass或public route；
- subprocess positive/negative tests和audit persistence。

### Code implementation prompt

```text
请执行 P2-R4-S8 — Private Import Recovery CLI。只实现private CLI、audit和tests，不注册HTTP
admin/recovery route，不修改main ref，不执行SQL replay。

开始前核对S7 handoff。读取P2-R4详细设计§§8、14、17，Repository Service Contract §11和
当前root lock/settings/store/provider/recovery code。

实现python -m gateway_repository_service.versioned_import.admin的inspect/apply命令。CLI使用
同一data-root/settings resolver，必须非阻塞取得service root lock；lock busy、service运行、
DB newer/invalid、operation不满足
`status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED`、evidence不唯一均fail closed。
Inspect默认只读并输出safe evidence summary。

Apply只允许decision=SUCCEEDED或NOT_PUBLISHED。SUCCEEDED必须fresh evidence证明main指向唯一
matching candidate、marker/parent/request binding完整，重建全部result echo；NOT_PUBLISHED必须
证明main仍为expected且不存在matching published/candidate ambiguity，默认转FAILED/
IMPORT_REJECTED，details reason=operator_confirmed_not_published。只有fresh evidence精确证明时
才用EXPECTED_COMMIT_MISMATCH或VERIFICATION_FAILED_NOT_PUBLISHED。

未解决MANUAL期间必须验证same-key replay/GetOperation仍可用、新key返回409、已QUEUED同仓库
operation不被dispatch；apply transaction完成后barrier解除并通知worker。

Status correction与recovery audit insert必须同一BEGIN IMMEDIATE transaction。Apply后只执行
新terminal状态允许的private ref/artifact cleanup。禁止force、override、yes-really、任意SQL、
main move、history deletion和host repository path。

以subprocess测试inspect、两个apply、audit持久化、service-running/root-lock、wrong operation、
stale evidence、multiple marker、missing artifact、invalid decision和重复apply。
运行service完整四命令、git diff --check和public route/admin API搜索。

通过后提交：
feat(repository): add private import recovery CLI

输出S8 handoff，next_stage=P2-R4-S9。
```

## 13. S9 — HTTP activation, polling and admission

### Goal

在所有effect/recovery构件ready后激活SubmitVersionedImport和GetOperation，完成auth、header、
OpenAPI、idempotency、queue/disk admission、response-loss replay、request/operation logging和
真实HTTP integration。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/http/routes/imports.py
vnext/repository_service/src/gateway_repository_service/http/routes/operations.py
vnext/repository_service/src/gateway_repository_service/http/routes/__init__.py
vnext/repository_service/src/gateway_repository_service/http/errors.py
vnext/repository_service/src/gateway_repository_service/http/readiness_guard.py
vnext/repository_service/src/gateway_repository_service/app.py
vnext/repository_service/src/gateway_repository_service/runtime.py
vnext/repository_service/src/gateway_repository_service/capacity.py
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/src/gateway_repository_service/versioned_import/command.py
vnext/repository_service/tests/test_import_http.py
vnext/repository_service/tests/test_operation_http.py
vnext/repository_service/tests/test_http_shell.py
vnext/repository_service/tests/test_settings.py
```

### Required behavior and gate

- exact two routes，无stub/read routes；
- bearer、request ID、SimpleError和status；
- header-only key、closed body、path/body match和literal main；
- QUEUED transaction先于202；
- same-key original202/op ID，different fingerprint409；
- GetOperation四态/result/error；
- queue 429、disk/provider/readiness 503；
- same-key replay不占新queue slot；
- unresolved MANUAL阻止新key admission但不阻止same-key replay/GetOperation；
- disconnect/response-loss后same-key replay；
- logs只含safe identifiers；
- OpenAPI只新增R4 routes；
- contracts和service完整四命令。

### Code implementation prompt

```text
请执行 P2-R4-S9 — Activate Import and Operation HTTP Routes。这是首次激活R4 public route；
不得增加P2-R5 read/client或public admin API。

开始前核对S8 handoff。读取P2-R4详细设计§§4–5、9、18，Repository Service Contract §§6、
10–11、14和当前FastAPI auth/error/readiness/create/upload patterns。确认worker/recovery/admin
全部已存在且tests green后才注册route。

实现POST /v1/repositories/{repository_id}/versioned/imports和
GET /v1/repositories/{repository_id}/operations/{operation_id}。Submit只从Idempotency-Key
header取key，closed JSON body不得含key；body/path repository一致、target main、policies默认。
新effect必须先完成same-key lookup和admission，再在SQLite持久QUEUED后返回202。Same-key/same
fingerprint即使terminal仍返回原operation ID/202，不占新queue slot；different fingerprint 409。
Repository存在未解决MANUAL时，新key返回409/MANUAL_RECOVERY_REQUIRED，same-key replay和
GetOperation继续可用。

GetOperation返回200和四态representation，terminal failure仍在operation.error，不映射HTTP
500。实现auth、SimpleError、X-Request-ID、404、422、429、503；不要泄漏raw key、SQL、path、
private ref或row。Queue default64、worker default4、headroom default1 GiB均可配置。

HTTP tests覆盖auth、OpenAPI、framework validation、same/different fingerprint、202 response
loss/replay、queue/disk admission、poll四态和server-generated request ID。OpenAPI只能新增上述
两条R4 routes，不得出现stub resolve/catalog/rows/admin。

分别在repository_contracts和repository_service运行完整四命令；运行git diff --check和route
搜索。通过后提交：
feat(repository): activate import and operation routes

输出S9 handoff，next_stage=P2-R4-S10。
```

## 14. S10 — Full fault matrix, real Dolt, Compose and handoff

### Goal

执行并闭合P2-R4完整required gate；补充缺失的process-crash、response-loss、真实Candidate A和
正式Compose coverage，只修复R4范围内发现的问题，形成最终green regression commit和handoff。

### Allowed paths

```text
vnext/repository_contracts/tests/
vnext/repository_service/tests/
vnext/repository_service/tests/support/
vnext/repository_service/src/gateway_repository_service/versioned_import/   # gate发现的R4 fixes only
vnext/repository_service/src/gateway_repository_service/runtime.py          # gate fixes only
vnext/repository_service/src/gateway_repository_service/process.py          # gate fixes only
vnext/repository_service/src/gateway_repository_service/http/               # gate fixes only
vnext/repository_service/src/gateway_repository_service/settings.py         # gate fixes only
vnext/repository_service/Dockerfile
vnext/deploy/compose.yaml
vnext/repository_service/README.md
```

任何超出上述R4 fix scope的失败先报告，不借final gate实施重构、P2-R5或R6功能。

### Required final matrix

- contracts/service各自四命令；
- QUEUED/RUNNING/SUCCEEDED/FAILED persistence；
- same-key原202/operation replay与different-fingerprint conflict；
- package streaming security及entry/single/payload-total/decoder-total边界；
- NONE/STRUCTURAL/FULL_SCAN × REJECT/STRINGIFY；
- expected parent、initial/second main check和publication readback；
- verification failure main unchanged、private ref cleanup；
- commit前crash、commit后response loss、normal failure无hidden retry；
- legacy RUNNING最多一次automatic replay；
- ambiguity保留artifact/ref并进入MANUAL；
- MANUAL barrier保留business/repository occupancy，阻止同repository新effect和dispatch；
- success artifact cleanup、ordinary TTL eligibility和manual retention；
- multi-operation artifact pin避免premature cleanup；
- admin stopped-service/root-lock/inspect/two apply/audit/negative actions；
- graceful shutdown child wait/reap和RUNNING recovery；
- real Candidate A Dolt integration；
- production Dockerfile/Compose build、create/upload/import/poll、restart/replay smoke；
- unique project name与container/network/volume cleanup；
- required fault case zero skip/xfail；
- old-reference searches、`git diff --check`和最终clean worktree。

### Code implementation prompt

```text
请执行 P2-R4-S10 — Final Fault/Dolt/Compose Gate and Handoff。该stage只闭合R4完整gate、修复
gate发现的R4缺陷并形成handoff；不得实现P2-R5、Backend consumer、TTL scheduler或完整R6
capacity/backup。

开始前核对S9 handoff和clean worktree。完整读取P2-R4详细设计§§19–22、执行计划本节、P2
Execution Checklist §6和正式Dockerfile/Compose/tests。先建立required matrix清单，逐项运行，
不要只跑聚合pytest后声称覆盖。

补齐真实process-crash faults：after_queued_before_202、after_running_claim、after_private_ref、
after_replay_before_marker、after_marker、before/after verification、before publish、after main
publish before SUCCEEDED、after SUCCEEDED before private/artifact cleanup。Required cases不得
skip/xfail。证明commit前crash、publication后response loss、normal failure无hidden retry、
legacy RUNNING replay最多一次、manual ambiguity retention和admin recovery。

分别在vnext/repository_contracts与vnext/repository_service执行uv lock --check、ruff、mypy、
pytest -q并记录精确counts。运行真实Candidate A Dolt integration。以唯一Compose project name
执行docker compose config/build/up，走正式HTTP create -> upload -> import -> poll，重启后验证
same-key replay和operation/result；使用trap做project-scoped down -v并验证container/network/
volume无残留。网络/registry/build失败必须报告no-go，不得降级成mock pass。

运行git diff --check、定向old-reference searches：body idempotency_key、旧verification/status、
generic journal、Candidate B、gzip/multipart/URL/path、public force/admin、production import
workflow/fixture/matrix。人工区分historical docs命中与current production错误引用。

只在全部gate通过后提交：
test(repository): close Versioned import delivery gate

提交后确认git status clean，按执行计划§4和详细设计§21输出完整P2-R4 handoff：所有commit
SHA、DB version、routes、limits/workers、test counts、fault matrix、Dolt/Compose/cleanup、known
limitations、production_retest_required、p2_r4_exit和p2_r5_ready。不要开始P2-R5。
```

## 15. Final old-reference searches

S10至少运行以下定向搜索，并保存人工分类：

```bash
rg -n "idempotency_key" \
  vnext/repository_contracts/src vnext/repository_service/src vnext/repository_contracts/tests \
  vnext/repository_service/tests

rg -n "PREPARED|APPLIED|VERIFIED|UNKNOWN|FailureDescriptor|FAILED_FINAL" \
  vnext/repository_service/src/gateway_repository_service/versioned_import \
  vnext/repository_service/tests

rg -n "LAST_WRITE_WINS|table.?CAS|schema.?CAS|force.?ref|CompareAndSetVersionedRef" \
  vnext/repository_service/src vnext/repository_contracts/src

rg -n "gzip|tar\+gz|multipart|host path|object storage|presigned|URL" \
  vnext/repository_service/src/gateway_repository_service/versioned_import \
  vnext/repository_service/tests/test_import*

rg -n "workflow|fixtures|matrix|SqlServerProvider|Candidate.B" \
  vnext/repository_service/src/gateway_repository_service/versioned_import \
  vnext/repository_service/src/gateway_repository_service/http
```

`idempotency_key`允许出现在header model、local command parameter和test input，但不得出现在
Submit JSON model、serialized request body、log或raw persisted field。`FULL_SCAN`不是旧`FULL`；
必须人工判断而非机械删除。

## 16. P2-R4 final exit

满足以下全部条件才完成本计划：

```text
S1..S10 stage_exit = pass
all suggested commits present and green
control_db_user_version = 7
selected_provider = candidate_a_offline_cli
required_fault_cases skipped = 0
required_fault_cases xfailed = 0
real_dolt = pass
production_compose_restart_replay = pass
runtime_cleanup = pass
git_diff_check = pass
worktree_clean = yes
p2_r4_exit = pass
p2_r5_ready = yes
```

Production-equivalent capacity retest仍按P2-R1 v8 decision保留，完整TTL/capacity/snapshot closure
仍属R6；二者不允许被误报为R4已经完成的production activation保证。
