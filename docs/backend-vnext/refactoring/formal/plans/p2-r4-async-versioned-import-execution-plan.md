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
S10必须执行contracts的完整四命令，以及service的lock/ruff/mypy、
`pytest -m "not serial"`和`pytest -m serial -n 0`拆分gate；最后使用
`./vnext/scripts/run-tests.sh`覆盖全部五包。

## 3. Stage summary and context sizing

| Stage | Primary outcome | Expected context size | Suggested commit |
| --- | --- | --- | --- |
| S1 | wire DTO/header/enums/result invariants | small：contracts约2–4 files | `feat(repository): finalize Versioned import wire contracts` |
| S2 | control DB v7与durable operation store | medium：DB/store约5–8 files | `feat(repository): add durable Versioned import operation store` |
| S3 | streaming zstd/tar和closed manifest | medium：validator/settings/tests约4–7 files | `feat(repository): validate bounded import packages` |
| S4 | Candidate A private ref/evidence/CAS primitives | medium-high：provider/process/tests约5–9 files | `feat(repository): add Candidate A import ref primitives` |
| S5 | verification与unknown-type matrix | medium-high：verification/Arrow/tests约5–8 files | `feat(repository): verify Versioned import candidates` |
| S6 | worker claim、writer ownership和happy path | high：组合约8–12 files | `feat(repository): execute durable Versioned import workers` |
| S7 | startup recovery、shutdown、worker composition和artifact lifecycle | high：runtime/recovery约10–14 files | `feat(repository): reconcile interrupted Versioned imports` |
| S8 | stopped-service private admin CLI与recovery audit | medium：CLI/evidence helper/barrier收口/tests约5–8 files | `feat(repository): add private import recovery CLI` |
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
vnext/repository_service/src/gateway_repository_service/control_db.py          # B1: ControlStore.transaction_lock
vnext/repository_service/src/gateway_repository_service/runtime.py           # B1: MutationStore shared lock injection
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/tests/test_import_worker.py
vnext/repository_service/tests/test_import_worker_integration.py
vnext/repository_service/tests/test_import_operation_store.py                # B1: _seed_artifact lock discipline
vnext/repository_service/tests/test_versioned_import_errors.py
vnext/repository_service/tests/support/                          # R4-specific worker harness only; may modify existing harness files for transaction_lock (P3-2)
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
  `import_shutdown_grace_seconds`、`import_headroom_bytes`可留到S7/S9消费点再加；新增字段
  必须按类型同步加入`settings.py`对应validator显式列表（int → `_bounds_must_be_positive`，
  float → `_timeouts_must_be_positive`），否则不受校验；
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
的显式字段列表；float timeout字段加入`_timeouts_must_be_positive`。Dispatcher必须先排除
active repository和未解决MANUAL barrier，reserve
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
vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py   # 新文件
vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py     # 移除daemon=True、暴露cancellation/join
vnext/repository_service/src/gateway_repository_service/versioned_import/locks.py      # barrier seeding API + 有界化（S6 defer项）
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py      # 仅additive：recovery所需查询helper
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py
vnext/repository_service/src/gateway_repository_service/versioned_import/command.py      # scope amendment：interruption_check + S6不可达分支清理
vnext/repository_service/src/gateway_repository_service/versioned_import/faults.py       # scope amendment：ImportRecoveryFaultPoint崩溃探针
vnext/repository_service/src/gateway_repository_service/runtime.py                     # import worker/recovery composition
vnext/repository_service/src/gateway_repository_service/process.py
vnext/repository_service/src/gateway_repository_service/mutation_reconciliation.py
vnext/repository_service/src/gateway_repository_service/settings.py                    # import_shutdown_grace_seconds
vnext/repository_service/tests/test_import_recovery.py                                 # 新文件
vnext/repository_service/tests/test_import_shutdown.py                                 # 新文件
vnext/repository_service/tests/test_mutation_readiness.py                               # 既有文件，扩充
vnext/repository_service/tests/test_import_worker.py                                    # daemon/join与barrier回归
vnext/repository_service/tests/test_import_worker_integration.py                        # real Dolt并发/多仓库case
vnext/repository_service/tests/support/                         # R4-specific process harness only
```

**Scope amendments (post-implementation)**：`command.py` 与 `faults.py` 原不在 §11 白名单；
实现阶段为 shutdown 中断屏障（维度 7）与 recovery 子进程 at-most-once 探针所必需，已在
`4e6cdd8` 合入且不回退。`tests/test_import_runtime_concurrency.py` 已删除，nested-transaction
断言迁入 `test_import_worker.py`。

**S7 → S8 handoff**：S8 admin resolve 必须联动
`RepositoryLockRegistry.clear_manual_barrier(repository_id)`（或改为仅以
`store.has_unresolved_manual_barrier()` 为准）；否则 MANUAL 解除后本进程仍被内存 barrier 阻塞。
S7 结束时 `clear_manual_barrier` 在 `src/` 下没有任何调用点，`seed_manual_barriers` 只在
`ServiceRuntime.start` 播种；§12「Post-apply cleanup and barrier handoff」把该项列为 S8 的
必须闭合项并给出 (a)/(b) 两条允许路径，S8 必须二选一并在 handoff 中说明选择与影响面。

`store.py`、`locks.py`只允许additive改动：可新增recovery查询与barrier seeding/eviction API，
不得改变S2–S6已固定的claim/FIFO/terminal语义或既有方法签名。`command.py`、`errors.py`、
`models.py`、`ports.py`本阶段不在范围内；若recovery确实需要改动其中任一文件，先作为scope
question上报，不要自行放宽。

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
- required crash tests使用新进程，不只mock exception；
- **production composition闭合S6 B1**：`ServiceRuntime`必须以
  `ImportOperationStore(control_store.connection, transaction_lock=control_store.transaction_lock)`
  构造store。S6只在harness/integration test里注入了共享lock，`src/`至今没有任何
  `ImportOperationStore`构造点，因此production侧目前只有`MutationStore`受保护；S7是第一个
  真正在production里同时跑dispatcher与`MutationStore`写入的阶段，必须有一个断言
  "shared connection上不出现nested transaction"的测试；
- **`worker.py` `start()`当前用`daemon=True`创建dispatcher与worker线程**（见
  `versioned_import/worker.py`），与本阶段"不得使用daemon thread逃过join"直接冲突：S7必须
  改为非daemon并让`stop()`的join成为真正的屏障（join超时后必须报告，不得静默丢弃线程）；
- **新增settings**：`import_shutdown_grace_seconds`（float，正数）必需，用于shutdown grace；
  若readiness/capacity真的消费`import_headroom_bytes`才一并新增，否则留给S9。新增字段必须
  按类型同步加入`settings.py`对应validator显式列表（float → `_timeouts_must_be_positive`，
  int → `_bounds_must_be_positive`），否则不受校验；
- **barrier重建需要`RepositoryLockRegistry`新API**：现有registry只有
  `try_reserve/release_reservation/is_active/repository_execution`，没有任何"从durable
  MANUAL rows播种barrier"的入口，也没有eviction（`_repository_locks`字典无界增长，S6 defer
  到本阶段）。S7需同时补上seeding入口与有界化/清理；
- **real provider gate扩面**：S6的real Dolt gate只覆盖单operation happy path。S7必须至少新增
  一个`@pytest.mark.integration`的real Dolt case，覆盖"restart后recovery + 多仓库并发claim"，
  不得再以fake provider结果代替real provider gate。

### Carried-over non-blocking items from S6

S6以pass收口，以下6项为非阻断遗留，S7顺带清理（不要求全部关闭，但需在handoff中逐项给出
关闭或继续defer的结论）：

- `errors.py`脱敏对单位数字（`duplicate key 7`、`column age: 9`）与字符串字面量row value
  （`duplicate entry 'alice smith'`）仍有缺口。当前判定为不可达，依据是provider所有
  `ImportProviderError`消息均为固定字面量，唯一外部文本通道是`provider.py`的
  `ImportProviderError(str(exc))`且DoltRunner把它放在`stderr=`标签下已被整段替换。**S7若新增
  任何provider error路径，必须重新验证这个假设。**
- `command.py`两个mapper里`main_unchanged() and not has_marker_evidence()`分支在
  `_has_private_ref_without_marker()`前置后已不可达（探针：0个可达组合），可删或加注释。
- 测试名`test_failure_mapping_import_rejected_on_replay_failure`已过时（现在断言的是
  `MANUAL_RECOVERY_REQUIRED`）。
- `test_failure_mappers_agree_on_private_ref_evidence`只覆盖单个evidence组合，建议
  parametrize到9组合矩阵。
- `_STDERR_RE`按行尾整段替换，会连带吞掉`stderr=`之后的良性尾部键（`reason=`、
  `stage_elapsed=`），损失可诊断性。
- `tests/support/import_worker_harness.py`里`configure_connection(self.connection)`是冗余调用
  （`ControlStore.open`内部已调用）。

### Code implementation prompt

```text
请执行 P2-R4-S7 — Startup Reconciliation and Graceful Shutdown。不得注册public import或
operation route；admin CLI属于S8。

开始前核对S6 handoff（包含本节"Carried-over non-blocking items from S6"6项，handoff里逐项
给出关闭或继续defer的结论）。读取P2-R4详细设计§§14–16、External Effect and Recovery Contract
§5，以及当前ServiceRuntime、DoltRunner、sync reconciler和R4 worker/store/provider/locks。

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

在`ServiceRuntime`里组合import runtime：以
`ImportOperationStore(control_store.connection, transaction_lock=control_store.transaction_lock)`
构造store（`src/`当前没有任何构造点，production侧只有MutationStore受共享lock保护），并加一个
断言"同一connection上dispatcher与MutationStore并发写不出现nested transaction"的测试。
`RepositoryLockRegistry`需新增从durable MANUAL rows播种barrier的入口，并补上eviction/有界化
（S6 defer项）。新增settings `import_shutdown_grace_seconds`（float，正数）并同步加入
`settings.py`的`_timeouts_must_be_positive`字段列表；int字段加入`_bounds_must_be_positive`；
`import_headroom_bytes`只在readiness/capacity
真正消费时才加，否则留给S9。

实现shutdown stopping flag、停止claim、configured grace、per-operation cancellation、Dolt
process-group terminate/kill/wait/reap、worker join、DB close、root lock最后释放。Shutdown中断不
写普通FAILED，保留RUNNING/evidence。不得使用daemon thread逃过join：`worker.py` `start()`当前
以`daemon=True`创建dispatcher与worker线程，必须改为非daemon，且`stop()`的join成为真正屏障，
join超时必须报告，不得静默丢弃线程。

更新artifact readiness：无consuming success的missing upload仍阻塞；matching SUCCEEDED import
后的missing bytes合法；QUEUED/RUNNING/MANUAL missing必须正确分类。Manual operation一旦已完整
分类不应永久拖垮整个Service readiness。

运行service完整四命令（第四条为`./vnext/scripts/run-tests.sh`）、required restart/crash tests、
至少一个`@pytest.mark.integration`的real Dolt case（restart后recovery + 多仓库并发claim；S6的
real provider gate只覆盖单operation happy path，不得再用fake provider顶替）、git diff --check。
依赖时间预算的shutdown/grace与并发测试必须标`@pytest.mark.serial`。不得skip/xfail本阶段
required cases。

通过后提交：
feat(repository): reconcile interrupted Versioned imports

输出S7 handoff，next_stage=P2-R4-S8，并对"Carried-over non-blocking items from S6"的6项逐项
给出关闭或继续defer的结论。
```

## 12. S8 — Private recovery CLI and audit

### Goal

实现stopped-service/root-lock private admin CLI（`inspect` / `apply`），闭合SUCCEEDED与
NOT_PUBLISHED两种evidence-only correction、recovery audit和全部negative actions。S8只补"人工
收口"这一条通道：不增加public API、不注册HTTP route、不移动`main`、不执行replay或任意SQL。

S8的durable写入语义已在S2落地（`ImportOperationStore.apply_manual_correction`，见下
"Already available"），因此本阶段的实现重心是**CLI进程边界**：settings/layout resolution、
非阻塞root lock、exact control DB version、fresh evidence重新采集、safe output/audit字段、
post-apply cleanup，以及与S7内存barrier的联动。实现者不要重写correction transaction。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/versioned_import/admin.py    # 新文件：CLI entry + evidence collector
vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py # additive：抽出可复用evidence helper
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py    # additive only：read API；不改apply_manual_correction语义
vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py # additive only：只读inspection helper
vnext/repository_service/src/gateway_repository_service/versioned_import/locks.py    # 仅barrier handoff所需的最小改动
vnext/repository_service/src/gateway_repository_service/versioned_import/worker.py   # 仅barrier判定单一化(路径a)所需的最小改动
vnext/repository_service/src/gateway_repository_service/settings.py                  # 仅在CLI确实需要新settings时
vnext/repository_service/tests/test_import_admin_cli.py                              # 新文件：subprocess CLI tests
vnext/repository_service/tests/test_import_worker.py                                 # 仅barrier handoff受影响的既有断言
vnext/repository_service/tests/test_import_recovery.py                               # 仅barrier handoff受影响的既有断言
vnext/repository_service/tests/support/                                              # CLI subprocess harness only
vnext/repository_service/pyproject.toml                                             # only if a private console script is chosen
vnext/repository_service/uv.lock                                                    # only if pyproject dependency metadata changes
```

**Scope amendment（S8 审核后 retroactive，2026-08-08）**：下列路径在二次审核 no-go 修复中正式纳入：

```text
vnext/repository_service/src/gateway_repository_service/control_db.py               # additive only：
  ControlStore.preflight_exact_version + open(allow_migration=False)；不 bump user_version
vnext/repository_service/src/gateway_repository_service/runtime.py                  # barrier handoff 路径 (a)：
  删除 seed_manual_barriers 调用（一行 dead-code removal）
docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-*.md         # S8 handoff 与 scope 修订
vnext/repository_service/tests/support/import_worker_harness.py                     # FakeImportProvider.private_ref_exists mock
vnext/repository_service/src/gateway_repository_service/layout.py                 # additive only：
  DurableLayout.bind_existing（admin existing-layout resolver，不 mkdir）
```

`test_import_recovery.py` 在审核修复中**仅**迁出 `test_collect_recovery_evidence_returns_none_on_provider_private_ref_probe_failure`
至 `test_import_admin_cli.py`（纯 unit）；recovery 测试文件恢复为仅 barrier handoff 断言范围。

`locks.py`与`worker.py`只为「Post-apply cleanup and barrier handoff」一项开口：允许删除或收敛
barrier判定路径，不得改动`try_reserve`/`release_reservation`/`repository_execution`语义、
worker claim/FIFO顺序或`_RepositoryLockEntry` holders refcount（S7 P2-N1 修复项）。
`test_import_worker.py`与`test_import_recovery.py`只允许改动因barrier路径收敛而失效的断言，
不得删除既有case。

`control_db.py`、`runtime.py`、`layout.py` 已通过上列 **Scope amendment** 纳入 S8 remediation；
不得 bump `CONTROL_DB_USER_VERSION` 或新增 migration step。`command.py`、`models.py`、
`ports.py`、`app.py`、`http/` 仍不在范围内。

`pyproject.toml`当前没有`[project.scripts]`，模块调用形式（`python -m ...admin`）是零改动路径；
优先选它，则`pyproject.toml`/`uv.lock`两行保持未使用。

### Already available from S2–S7 (不要重复实现)

实现者必须先确认这些既有构件，S8只是把它们组装成一个CLI进程：

| 已存在 | 位置 | S8如何使用 |
| --- | --- | --- |
| `ImportOperationStore.apply_manual_correction(operation_id, *, decision, evidence_summary, final_result=None, final_error=None)` | `versioned_import/store.py` | **唯一**的correction入口。已在单个`BEGIN IMMEDIATE`里完成MANUAL-only前置校验、`validate_result_matches_operation_row`、conditional UPDATE、`record_artifact_consumed`和`repository_import_recovery_audit` insert。CLI只负责采证并调用 |
| `ManualCorrectionDecision.{SUCCEEDED,NOT_PUBLISHED}`、`RecoveryAuditAction.{INSPECT_APPLY_SUCCESS,INSPECT_APPLY_NOT_PUBLISHED}`、`ORDINARY_TERMINAL_ERROR_CODES`、`MANUAL_RECOVERY_REQUIRED_CODE`、`is_manual_recovery_error` | `versioned_import/models.py` | 直接引用，不要新增enum或字符串字面量 |
| `DurableRootLock.acquire()` 已是 `flock(LOCK_EX \| LOCK_NB)`，busy时抛 `RootLockBusy` | `locking.py` | 直接`acquire()`并捕获`RootLockBusy` = "service还在运行"，不需要新增非阻塞变体 |
| `ControlStore.open(path, *, expected_version, busy_timeout_ms)` 已对 newer/invalid `user_version` fail closed | `control_db.py`（`CONTROL_DB_USER_VERSION = 7`） | 以`expected_version=CONTROL_DB_USER_VERSION`打开；不要放宽 |
| store read API：`get_operation`、`load_execution_context`、`list_operations_by_status`、`list_repositories_with_manual_barrier`、`has_unresolved_manual_barrier`、`list_artifact_references`、`list_protected_artifact_pins`、`can_delete_artifact_bytes`、`mark_artifact_bytes_deleted` | `versioned_import/store.py` | inspect输出与post-apply cleanup判定 |
| evidence helper：`_try_recover_published_marker`、`_artifact_is_valid`、`_resolve_manifest_digest`、`_cleanup_succeeded_residuals_for_context`、`_cleanup_staging` | `versioned_import/recovery.py`（`ImportStartupReconciler`） | 采证与cleanup**复用**这些逻辑；若需要在CLI里调用，抽成模块级函数或公开方法，不要在`admin.py`里复制一份 |
| provider只读面：`read_ref`、`inspect_marker`（`MarkerInspection{Zero,Unique,Ambiguous}`）、`delete_private_ref` | `versioned_import/provider.py`、`ports.py` | 采证只允许用只读调用；`publish_main`、`replay_sql`、`commit_operation_marker`、`checkout_private_ref`在S8**禁止调用** |
| settings/layout/provider组合顺序 | `runtime.py` `ServiceRuntime.start` 与 `_build_provider_factory` | CLI必须复用同一顺序：`DurableLayout.create_service(settings.data_root)` → `DurableRootLock(layout.service_lock)` → `ControlStore.open(...)` → `ImportOperationStore(connection, transaction_lock=control_store.transaction_lock)` → `OfflineCliCapabilityGate.verify` → `DoltRunner` → provider factory |

### Required behavior and gate

**CLI surface**

- `python -m gateway_repository_service.versioned_import.admin inspect --operation-id <uuid>` 与
  `... apply --operation-id <uuid> --decision SUCCEEDED|NOT_PUBLISHED`；`argparse` subcommand，
  仓库既有precedent见`matrix.py`与`target_gate.py`；
- settings来自同一`RepositoryServiceSettings`（`GATEWAY_REPOSITORY_` env prefix + `.env`），
  允许`--data-root`覆盖`data_root`，**不接受**host repository path、control DB path或任何直连
  DB/repository的参数；
- 退出码固定且可测：`0` 成功；`2` 参数/decision非法；`3` root lock busy（service运行中）；
  `4` control DB version或schema不受支持；`5` operation不存在或不满足
  `status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED`；`6` evidence不足/不唯一/与decision
  矛盾。stdout只输出single-line JSON（safe fields），诊断文本走stderr；
- `inspect`零mutation：不写control DB、不写audit、不删除任何ref或bytes。

**Fail-closed preconditions（顺序固定，任一失败立即退出且不做后续采证）**

1. 参数校验（uuid可解析、decision在两值内）；
2. `DurableRootLock(layout.service_lock).acquire()`；`RootLockBusy` → exit 3；
3. `ControlStore.open(..., expected_version=CONTROL_DB_USER_VERSION)`；newer/invalid → exit 4；
4. target operation存在且`status=FAILED`且`is_manual_recovery_error(error)` → 否则 exit 5；
5. fresh evidence重新采集（不复用durable row里的旧结论），与decision不一致 → exit 6。

**Evidence and decisions**

- 采证内容至少：`provider.read_ref("main")` 当前值、`provider.inspect_marker(operation_marker)`
  结果、private ref是否存在、artifact ready bytes是否存在且valid（复用`_artifact_is_valid`的
  size + `validate_and_extract_import_package` 探针，probe staging目录必须在`finally`里rmtree）、
  `expected_commit_id`、`canonicalization_manifest_digest`；
- `SUCCEEDED` 仅当fresh evidence证明：`inspect_marker` 为 `MarkerInspectionUnique`、`main`
  正指向该唯一matching candidate、marker/parent/request binding完整。此时重建**完整**
  `VersionedImportResult` echo（`commit_id`、`target_ref="main"`、`artifact_id`、
  `canonicalization_manifest_digest`、`expected_commit_id`、`completed_verification_policy`、
  `unknown_type_policy`），由`apply_manual_correction`的`validate_result_matches_operation_row`
  兜底；任一字段无法从evidence重建 → exit 6，不允许填占位值；
- `NOT_PUBLISHED` 仅当fresh evidence证明：`main` 仍等于 `expected_commit_id`，且不存在matching
  published/candidate ambiguity（`MarkerInspectionAmbiguous` 一律拒绝）。默认写
  `FAILED` + `IMPORT_REJECTED`，`details={"reason": "operator_confirmed_not_published"}`；
- 只有fresh evidence精确证明时才改用 `EXPECTED_COMMIT_MISMATCH`（main已被他人推进且证明与本
  operation无关）或 `VERIFICATION_FAILED_NOT_PUBLISHED`（private candidate存在但verification
  证明未发布）。三个code都必须在`ORDINARY_TERMINAL_ERROR_CODES`内，`request_id`必须为`None`；
- 两个decision都通过`store.apply_manual_correction`落库，correction与audit insert共享同一
  `BEGIN IMMEDIATE`（已实现，不要另开transaction或在CLI里手写SQL）。

**Audit and safe output**

- `evidence_summary`只含safe field：operation/repository/artifact ID、status、stable code、
  policy、marker inspection kind、main/expected/candidate commit ID、size、duration、时间戳。
  禁止token、raw idempotency key、replay SQL、full stderr、internal/host path、private
  credential、complete row或sensitive conversion value；
- audit行的`action`与decision严格对应（`INSPECT_APPLY_SUCCESS` / `INSPECT_APPLY_NOT_PUBLISHED`），
  `prior_status`/`prior_code`取correction前的durable值；
- 结构化event `admin apply audit identity`（详细设计§18）以相同safe field集合输出。

**Post-apply cleanup and barrier handoff**

- apply成功后只执行新terminal状态**允许**的cleanup：`SUCCEEDED` 走
  `_cleanup_succeeded_residuals_for_context` 等价路径（private ref删除 + 在
  `can_delete_artifact_bytes` 为真且无`list_protected_artifact_pins`时删除ready bytes并
  `mark_artifact_bytes_deleted`）；`NOT_PUBLISHED` 只删private ref与staging残留，artifact按
  ordinary TTL规则保留。cleanup失败为best-effort，不得回滚已提交的correction；
- **S7 → S8 handoff（必须闭合）**：`RepositoryLockRegistry.clear_manual_barrier` 目前在
  `src/` 里没有任何调用点，只有`seed_manual_barriers`在`ServiceRuntime.start`播种。CLI在
  stopped-service下运行，进程内barrier本就不存在，因此S8必须在两条路里选一条并落实：
  (a) 让`worker.py`的barrier判定仅以`store.has_unresolved_manual_barrier()`为准，删除内存
  barrier分支与`clear_manual_barrier`；或 (b) 保留内存barrier，但补上"apply后同进程/下次
  startup重新播种时正确清除"的路径并加测试。**不允许两条路都留着且只更新一条**，也不允许
  留下无调用者的`clear_manual_barrier`。
- 未解决MANUAL期间的既有语义必须仍成立（S2/S6已有测试，S8只需回归确认）：same-key replay与
  GetOperation可用、新key返回409、同repository已QUEUED operation不被dispatch。

**Prohibitions（任一出现即S8不通过）**

- 移动或force `main`；调用`publish_main`/`replay_sql`/`commit_operation_marker`/
  `checkout_private_ref`；
- 执行任意caller SQL、raw SQL参数或replay文件；
- 创建commit、删除history、接受host repository path；
- 修改非MANUAL operation，或修改`status != FAILED`的row；
- 提供`--force`、`--yes-really`、`--skip-evidence`或任何evidence bypass；
- 注册public/admin HTTP route，或把CLI逻辑挂到`app.py`/`http/`；
- 新增migration或改动`CONTROL_DB_USER_VERSION`。

**Tests（`tests/test_import_admin_cli.py`，全部真实subprocess调用CLI）**

- positive：`inspect` 输出safe summary且零mutation；`apply --decision SUCCEEDED` 补完整result
  并写`INSPECT_APPLY_SUCCESS` audit；`apply --decision NOT_PUBLISHED` 写
  `IMPORT_REJECTED`/`operator_confirmed_not_published` 与`INSPECT_APPLY_NOT_PUBLISHED` audit；
- audit persistence：重开control DB断言audit行字段（action、prior/final status与code、
  evidence summary无禁止字段）；
- negative：service运行中（root lock被持有）、control DB version newer、operation不存在、
  operation非MANUAL（QUEUED/RUNNING/SUCCEEDED/ordinary FAILED各一）、stale evidence
  （main已变）、`MarkerInspectionAmbiguous`、missing/invalid artifact、invalid decision值、
  重复apply（第二次因不再是MANUAL而fail closed且不写第二条audit）；
- 断言exit code与stdout JSON，不只断言"非零退出"；
- 至少一个`@pytest.mark.integration`的real Dolt case，覆盖真实`main`/marker采证下的一个
  positive apply；依赖时间预算的case标`@pytest.mark.serial`；本阶段required case零skip/xfail；
- 定向运行约定：在`vnext/repository_service`下`uv run pytest tests/test_import_admin_cli.py -n 0`
  （`addopts`注入`-n auto --dist loadgroup`，`-p no:xdist`无效）。

### Code implementation prompt

```text
请执行 P2-R4-S8 — Private Import Recovery CLI。只实现stopped-service private CLI、audit和
tests。不注册任何HTTP admin/recovery route，不修改main ref，不执行SQL replay，不做DB
migration。

开始前必读：本执行计划§11（S7 allowed paths与S7→S8 handoff）、本节全文（Allowed paths、
Already available、Required behavior and gate）、P2-R4详细设计§§8、14、17、18、20，
Repository Service Contract §11，External Effect and Recovery Contract §5。然后读当前代码：
locking.py（DurableRootLock）、control_db.py（CONTROL_DB_USER_VERSION与
repository_import_recovery_audit DDL）、runtime.py（ServiceRuntime.start组合顺序与
_build_provider_factory）、versioned_import/store.py（重点读apply_manual_correction全文）、
models.py、ports.py、provider.py、recovery.py、locks.py、worker.py的barrier判定。

先确认这些已经实现，S8不要重写：
- store.apply_manual_correction已在单个BEGIN IMMEDIATE里完成MANUAL-only前置校验、
  validate_result_matches_operation_row、conditional UPDATE、record_artifact_consumed和
  repository_import_recovery_audit insert。CLI只负责采证 + 调用它；
- DurableRootLock.acquire()已是flock LOCK_NB并在busy时抛RootLockBusy；
- ControlStore.open(..., expected_version=CONTROL_DB_USER_VERSION=7)已对newer/invalid版本
  fail closed；
- ManualCorrectionDecision、RecoveryAuditAction、ORDINARY_TERMINAL_ERROR_CODES、
  MANUAL_RECOVERY_REQUIRED_CODE、is_manual_recovery_error都已存在；
- control DB已是v7且audit表已建，禁止新增migration或bump user_version。

实现python -m gateway_repository_service.versioned_import.admin的inspect与apply子命令
（argparse，precedent见matrix.py与target_gate.py；pyproject.toml没有[project.scripts]，
优先保持模块调用形式）。CLI复用同一RepositoryServiceSettings与
DurableLayout.create_service(settings.data_root)，允许--data-root覆盖data_root，不接受host
repository path、control DB path或任何直连DB/repository的参数。stdout只输出single-line JSON
safe summary，诊断走stderr。

固定前置顺序，任一失败立即退出且不做后续采证：参数校验(exit 2) → root lock acquire，
RootLockBusy即service运行中(exit 3) → ControlStore.open exact version(exit 4) → target满足
status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED(exit 5) → fresh evidence与decision一致
(exit 6)。成功为0。inspect零mutation：不写DB、不写audit、不删ref或bytes。

采证只允许只读provider调用：read_ref("main")、inspect_marker(operation_marker)、private ref
存在性、artifact ready bytes valid（复用recovery.py的_artifact_is_valid逻辑：size +
validate_and_extract_import_package探针，probe staging在finally里rmtree）。禁止调用
publish_main、replay_sql、commit_operation_marker、checkout_private_ref。若需要在CLI里复用
recovery.py的helper，把它抽成模块级函数或公开方法，不要在admin.py里复制一份实现。

Apply只允许decision=SUCCEEDED或NOT_PUBLISHED。SUCCEEDED要求fresh evidence证明
inspect_marker为MarkerInspectionUnique、main正指向该唯一matching candidate、marker/parent/
request binding完整，并重建完整VersionedImportResult echo（commit_id、target_ref="main"、
artifact_id、canonicalization_manifest_digest、expected_commit_id、
completed_verification_policy、unknown_type_policy）；任一字段无法从evidence重建就exit 6，
不得填占位值。NOT_PUBLISHED要求main仍等于expected_commit_id且无matching published/candidate
ambiguity（MarkerInspectionAmbiguous一律拒绝），默认写FAILED/IMPORT_REJECTED，
details reason=operator_confirmed_not_published。只有fresh evidence精确证明时才改用
EXPECTED_COMMIT_MISMATCH或VERIFICATION_FAILED_NOT_PUBLISHED；三者都在
ORDINARY_TERMINAL_ERROR_CODES内且request_id为None。

evidence_summary只含safe field（operation/repository/artifact ID、status、stable code、policy、
marker inspection kind、main/expected/candidate commit ID、size、duration、时间戳），禁止
token、raw idempotency key、replay SQL、full stderr、internal/host path、credential、complete
row或sensitive conversion value。audit的action与decision严格对应，prior_status/prior_code取
correction前的durable值。结构化event admin apply audit identity用同一safe field集合。

Apply成功后只执行新terminal状态允许的cleanup：SUCCEEDED走_cleanup_succeeded_residuals_
for_context等价路径（删private ref；can_delete_artifact_bytes为真且无protected pin时删ready
bytes并mark_artifact_bytes_deleted）；NOT_PUBLISHED只删private ref与staging残留，artifact按
ordinary TTL保留。cleanup为best-effort，失败不得回滚已提交的correction。

必须闭合S7→S8 handoff：RepositoryLockRegistry.clear_manual_barrier目前在src/里没有调用点，
只有seed_manual_barriers在ServiceRuntime.start播种。二选一并落实：(a) worker.py的barrier判定
只以store.has_unresolved_manual_barrier()为准，删除内存barrier分支与clear_manual_barrier；
或 (b) 保留内存barrier但补上apply后正确清除的路径与测试。不允许两条路都留着只更新一条，也不
允许留下无调用者的clear_manual_barrier。若选(a)需改worker.py/locks.py，先在handoff里说明这是
本节授权的最小改动范围。

未解决MANUAL期间的既有语义须回归确认仍成立：same-key replay与GetOperation可用、新key返回409、
同repository已QUEUED operation不被dispatch。

在tests/test_import_admin_cli.py里以真实subprocess调用CLI，覆盖：inspect零mutation、两个
positive apply、audit持久化（重开control DB断言字段且无禁止字段）、service-running/root-lock
busy、DB version newer、operation不存在、非MANUAL operation（QUEUED/RUNNING/SUCCEEDED/ordinary
FAILED各一）、stale evidence、ambiguous marker、missing/invalid artifact、invalid decision、
重复apply（第二次fail closed且不写第二条audit）。断言exit code与stdout JSON，不只断言非零。
至少一个@pytest.mark.integration的real Dolt case覆盖真实main/marker采证下的positive apply，
不得用fake provider顶替。依赖时间预算的case标@pytest.mark.serial。本阶段required case零
skip/xfail。定向运行用：cd vnext/repository_service && uv run pytest
tests/test_import_admin_cli.py -n 0（addopts注入-n auto --dist loadgroup，-p no:xdist无效）。

运行service完整四命令（第四条为./vnext/scripts/run-tests.sh）、git diff --check，以及
public route/admin API搜索（确认app.py与http/下无新route、无新FastAPI dependency）。

通过后提交：
feat(repository): add private import recovery CLI

输出S8 handoff，next_stage=P2-R4-S9，并明确写出：barrier handoff选了(a)还是(b)及其影响面、
最终exit code表、audit safe field集合、以及本阶段是否动用了pyproject.toml/uv.lock。
```

### S8 completion handoff

```text
round: P2-R4
stage: P2-R4-S8
start_sha: b06ce5b
commit_sha: 251ac8b
head_sha: 6ac63bd
branch: phase1/gate-ownership-repair
worktree_clean: yes

modified_paths (round-6 remediation on top of 062cb28):
  - vnext/repository_service/src/gateway_repository_service/control_db.py
  - vnext/repository_service/tests/test_import_admin_cli.py
  - vnext/repository_service/tests/support/import_admin_cli_harness.py
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-execution-plan.md

explicit_non_goals_preserved:
  - no HTTP/admin route registration
  - no CONTROL_DB_USER_VERSION bump or new migration steps
  - no pyproject.toml [project.scripts] or uv.lock changes
  - no --force / evidence bypass flags
  - CLI does not accept host repository path or control DB path
  - CLI uses allow_migration=False; preflight is read-only; no WAL/journal auto-repair

implemented_behavior:
  - admin gate order: bind layout (exit 4) → root lock (exit 3) → control DB preflight (exit 4)
    → operation gate (exit 5) → provider (exit 6)
  - control DB preflight validates v7 table_xinfo column shapes, literal-preserving
    sqlite_master table/index/trigger DDL (strip only), FK, WAL mode
  - bind_existing fail-closed on unreadable/invalid layout.json (JSON/OSError, components)
  - load_execution_context/get_operation ValueError or sqlite3.Error → exit 4 (stable stderr)
  - NOT_PUBLISHED writes only IMPORT_REJECTED when main==expected and artifact_valid (round-3)
  - barrier handoff path (a) unchanged
  - all provider-pre gate tests use AdminCliControlDbEnvironment (no dolt init)

barrier_handoff: path (a) (unchanged from be36d6d)

exit_codes (verified round-6):
  - 0: inspect/apply success
  - 2: invalid operation id or decision
  - 3: durable root lock held (including when control DB missing)
  - 4: missing data-root, unreadable layout marker, missing/unreadable control DB,
    user_version mismatch, invalid v7 schema signature (columns/literal-preserving DDL/
    triggers/FK), journal_mode != WAL, malformed operation row decode or sqlite3.Error
    during operation load
  - 5: operation not found or not awaiting manual recovery (before provider)
  - 6: provider unavailable, evidence unavailable, decision/evidence mismatch

audit_safe_fields (stdout/audit may include):
  - operation_id, repository_id, artifact_id, status, prior_status, prior_code,
    final_status, final_code, marker_inspection, main_commit_id, expected_commit_id,
    candidate_commit_id, manifest_digest, verification_policy, unknown_type_policy,
    artifact_size_bytes, artifact_bytes_present, private_ref_present, stable_code,
    decision, action, applied_at

audit_forbidden_fields (stdout/audit must not include):
  - token, idempotency_key, replay_sql, stderr, host_path, credential,
    raw_sha256, private_ref_name, operation_marker

fault_points_covered (round-6):
  - CHECK literal case change ('main' → 'MAIN') → exit 4, no traceback
  - trigger literal case change ('SUCCEEDED' → 'succeeded') → exit 4, no traceback

fault_points_covered (round-5 retained):
  - missing CHECK/UNIQUE (column shape intact) → exit 4
  - root lock busy / non-MANUAL gates without dolt init

fault_points_covered (round-4 retained):
  - no-op trigger body → exit 4; wrong column types → exit 4; malformed layout → exit 4
  - root lock busy + missing control DB → exit 3; malformed operation UUID → exit 4
  - round-3 retained: NOT_PUBLISHED IMPORT_REJECTED, DELETE journal, missing data-root,
    non-SQLite control DB, corrupt operations table

validation_commands:
  - uv run ruff check src tests → pass
  - uv run mypy → pass
  - dolt parked: pytest tests/test_import_admin_cli.py -m unit -n 0 -q → 27 passed
  - pytest tests/test_import_admin_cli.py -n 0 -q → 41 passed
  - ./vnext/scripts/run-tests.sh → 809 passed + 1 skipped (parallel), 30 passed (serial)
  - git diff --check → pass

old_reference_searches:
  - rg "_admin_cli_ddl_signature|_normalize_sql" control_db.py
  - rg "corrupt_operations_check_literal_case|corrupt_trigger_succeeded_literal_case" import_admin_cli_harness.py
  - rg "case_sensitive_check_literal|case_sensitive_trigger_literal" test_import_admin_cli.py

first_failures_and_fixes:
  - DDL .upper() collapsed quoted literals → strip-only _admin_cli_ddl_signature
  - head_sha sibling mismatch → head_sha set to doc commit tip (no self-reference amend loop)

known_limitations:
  - no positive CLI test for VERIFICATION_FAILED_NOT_PUBLISHED (deferred until durable evidence exists)
  - barrier SQLite query per queued candidate; no capacity benchmark
  - inspect acquires service.lock with O_CREAT when lock file absent (existing layout only)

stage_exit: pass
next_stage_ready: yes
next_stage: P2-R4-S9
```

## 13. S9 — HTTP activation, polling and admission

### Goal

在所有effect/recovery构件ready后激活SubmitVersionedImport和GetOperation两条
public route，完成auth、header/body/path validation、OpenAPI、replay-first idempotency、
transactional queue/MANUAL/artifact admission、disk headroom、response-loss replay、safe logging和
真实ASGI + SQLite HTTP integration。S9不扩大到P2-R5 public reads、public admin API或S10
real-Dolt/process-crash/Compose closure。

S8代码基线为`251ac8b`，S8 handoff文档tip为`fe734b4`。S9开始时必须用
`git merge-base --is-ancestor 251ac8b HEAD`验证代码基线在当前分支上，不要为追逐
S8 handoff中的self-referential short SHA做amend或重写history。保留任何已有用户
改动；若除本计划/设计文档外还有未说明的code/test改动，先停止并报告。

### Allowed paths

```text
vnext/repository_service/src/gateway_repository_service/http/routes/imports.py
vnext/repository_service/src/gateway_repository_service/http/routes/operations.py
vnext/repository_service/src/gateway_repository_service/http/routes/__init__.py
vnext/repository_service/src/gateway_repository_service/http/errors.py
vnext/repository_service/src/gateway_repository_service/app.py
vnext/repository_service/src/gateway_repository_service/runtime.py
vnext/repository_service/src/gateway_repository_service/capacity.py
vnext/repository_service/src/gateway_repository_service/settings.py
vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
vnext/repository_service/src/gateway_repository_service/versioned_import/command.py
vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
vnext/repository_service/tests/test_import_http.py
vnext/repository_service/tests/test_operation_http.py
vnext/repository_service/tests/test_import_submission.py
vnext/repository_service/tests/test_import_operation_store.py
vnext/repository_service/tests/test_import_worker.py
vnext/repository_service/tests/test_capacity.py
vnext/repository_service/tests/test_runtime.py
vnext/repository_service/tests/test_http_shell.py
vnext/repository_service/tests/test_settings.py
vnext/repository_service/tests/support/http_harness.py
docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-execution-plan.md  # S9 handoff only
```

`submission.py`是S9新增的application boundary；route只负责HTTP解码/映射，不在
route内手写SQLite查询或复制store invariant。`command.py`仍是worker executor，只允许为
extraction前重复disk/headroom gate做最小改动。不修改`repository_contracts`、control DB
schema/user_version、provider/recovery/admin/lock语义；若发现必须越出上述路径，先说明
缺口和最小scope amendment，不要顺手扩展。

### Required behavior and gate

- production OpenAPI exact新增两条route：
  `POST /v1/repositories/{repository_id}/versioned/imports`和
  `GET /v1/repositories/{repository_id}/operations/{operation_id}`；Submit显式声明
  `202/401/404/409/422/429/503`，GetOperation声明`200/401/404/422/503`；无stub
  resolve/catalog/rows/admin；
- 两条route都需bearer auth，每个response都有server-generated `X-Request-ID`；所有JSON
  error（含framework validation）映射为`SimpleError`；
- Submit只从`Idempotency-Key` header读取1..255 UTF-8 opaque key；使用contracts-owned
  `ImportRequestHeaders`/`SubmitVersionedImportRequest`，body closed、不得出现key，path/body
  repository exact match，`target_ref` literal `main`，policy defaults保持STRUCTURAL/REJECT；
- 先做durable same-key lookup：matching fingerprint在任何effect-only gate之前返回原
  operation ID/202（包括terminal operation），different fingerprint在这些gate之前返回
  `409 / IDEMPOTENCY_CONFLICT`；raw key只在内存中hash，不持久化、不写日志；
- 只对missing key做新effect admission。外部preflight不持SQLite transaction；随后一个
  `BEGIN IMMEDIATE` transaction必须recheck key、repository/artifact durable binding、MANUAL
  barrier和global QUEUED count，并插入QUEUED。必须先commit QUEUED再通知dispatcher、
  再返202；并发same-key只有一个operation ID，different-key不超queue limit；
- repository必须可见；artifact lifecycle的repository/artifact/media type/size/raw SHA exact
  match，未consumed/deleted且ready file存在。Artifact absent、cross-scope、binding mismatch、
  consumed/deleted统一`404 / ARTIFACT_NOT_FOUND`；不泄漏跨repository信息；
- repository unresolved `FAILED / MANUAL_RECOVERY_REQUIRED`时新key返回
  `409 / MANUAL_RECOVERY_REQUIRED`；same-key replay和GetOperation继续可用；
- `max_queued_imports=64`是global QUEUED-only正整数上限，不计RUNNING或replay；满时
  新key返回`429 / IMPORT_QUEUE_FULL`。保持`max_import_workers=4`既有默认不变；
- 新增非负`import_headroom_bytes=1 GiB`。Import admission和worker extraction前共用同一
  fail-closed helper：`free >= max(min_free_disk_bytes, floor(total * fraction)) + headroom`；
  exact boundary接受，boundary-1拒绝，measurement/writable error不得fail open；
- 不直接使用现有`require_service_ready`作两条route dependency，因为它会用provider/
  disk gate阻断replay/poll。GetOperation只需auth和可读control DB；shutdown/provider/disk/
  queue/MANUAL只阻止新effect。Root lock/provider不可用的新effect映射
  `503 / SERVICE_NOT_READY`，writable/headroom映射`503 / DISK_ADMISSION_DENIED`；control DB
  operational failure时无法完成lookup，Submit replay和GetOperation也返回`503 / SERVICE_NOT_READY`；
- GetOperation用repository ID + operation ID scope lookup；absent/wrong-repository都是
  `404 / OPERATION_NOT_FOUND`。成功返回contracts-owned
  `GetOperationResponse` (`{"operation": {...}}`)和200，四态result/error invariant不变；
  terminal FAILED仍是200，durable `operation.error.request_id` 仍为空，不改写poll ID；
- structured logs至少区分accepted/replayed/conflicted/admission-denied，只含request ID、
  operation/repository/artifact ID、policy、size、status和stable code；不得包含token、raw key、
  expected/raw SHA全值、SQL/stderr、host path、private ref/marker、credential或complete row；
- DB-only HTTP/store/capacity tests经真实ASGI stack和SQLite执行，不直接调route function，
  不`dolt init`，在dolt parked时`-m unit`通过；S10仍拥有real-Dolt/process-crash/Compose
  matrix；
- required package gates、五包ruff/mypy、权威`run-tests.sh`、`git diff --check`和route/
  secret old-reference search全部green后才能stage exit。

### Code implementation prompt

```text
请直接执行 P2-R4-S9 — Activate Import and Operation HTTP Routes，完成实现、测试、
验证、commit和handoff。不要只做审核或给建议。这是R4首次激活public import/
operation route；不增加P2-R5 resolve/catalog/rows/client，不增加public admin API，不提前
执行S10 real-Dolt process-crash/Compose matrix。

一、基线与权威

1. 先运行git status --short、git rev-parse --short HEAD和
   git merge-base --is-ancestor 251ac8b HEAD。S8代码基线必须包含251ac8b；S8 handoff
   文档tip为fe734b4。不要为S8 handoff的head_sha做amend、hash固定点搜索或history
   rewrite。保留用户已有改动；若除当前计划/设计文档外还有未说明code/test
   diff，停止并报告。
2. 完整读取：
   - docs/backend-vnext/refactoring/formal/contracts/repository-service.md §§6、10–11、14；
   - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md
     §§4–5、9、18、20–21；
   - 本计划S8 handoff和S9全节；
   - repository AGENTS.md、docs/backend-vnext/testing-conventions.md；
   - 现有app.py、auth/error/request-ID/readiness、create/upload route/command patterns，以及
     settings.py、capacity.py、runtime.py、versioned_import/{models,store,worker,command}.py。
   权威优先级为formal contract > implementation design > S9 plan/prompt > current code。
3. 确认当前app尚未注册import/operation route，contracts DTO、v7 store、worker/recovery/admin
   已存在；不重写已完成的S1–S8语义。

二、实现边界

4. 新增versioned_import/submission.py作application boundary。HTTP route只负责解码
   contracts-owned header/body/path、调用submission/store并映射response；不在route内手写SQL、
   复制fingerprint/store invariant或调Dolt。command.py仍是worker executor，只做重复
   disk/headroom check的最小改动。
5. 注册且只注册：
   - POST /v1/repositories/{repository_id}/versioned/imports -> 202 SubmitVersionedImportResponse
   - GET /v1/repositories/{repository_id}/operations/{operation_id} -> 200 GetOperationResponse
   两者都要bearer auth、SimpleError和server-generated X-Request-ID。Submit只从
   Idempotency-Key header读取key，显式通过ImportRequestHeaders验证；body使用closed
   SubmitVersionedImportRequest，禁止body key/extra field，检查path/body repository一致、
   target_ref == main，保持STRUCTURAL/REJECT默认。OpenAPI显式声明Submit的
   202/401/404/409/422/429/503与GetOperation的200/401/404/422/503。
6. 不要把require_service_ready直接挂到这两条route。它包含provider/disk/writable
   gate，会错误阻断replay和poll。GetOperation只做auth + scoped control-DB lookup。Submit
   先处理durable replay/conflict，再对missing key做route-specific new-effect admission。

三、replay-first与原子admission

7. 用(repository-scoped key hash + versioned_import_fingerprint_v1)先查durable row：
   - same key/same fingerprint：无论QUEUED/RUNNING/SUCCEEDED/FAILED，立即返回原
     operation_id + 202；
   - same key/different fingerprint：立即409 / IDEMPOTENCY_CONFLICT；
   - 这两个结果都必须先于shutdown/provider/disk/queue/MANUAL/artifact effect-only gate。
   Raw key只做SHA-256，不持久化、不记录、不出现error details。
8. 只对missing key做外部preflight：runtime仍accepting effects，root lock/control DB/provider
   capability可用，repository可见，durable root可写，disk/headroom达标。外部
   provider/filesystem/statvfs检查期间不得持SQLite transaction或store lock。
9. 然后在一个BEGIN IMMEDIATE transaction内再次lookup key，并在插入前recheck：
   - repository create durable ledger仍为SUCCEEDED；filesystem visibility已在外部preflight确认；
   - artifact lifecycle的repository/artifact/media type/size/raw SHA exact match，
     consumed_at/bytes_deleted_at为空，matching ready file已在外部preflight确认；
   - repository无unresolved FAILED/MANUAL_RECOVERY_REQUIRED；
   - global status=QUEUED count < max_queued_imports。
   最后插入QUEUED并commit。必须先commit再notify worker，再返202；new insert必须
   notify，replay允许作为幂等liveness hint notify，但不得写新row或消耗slot。并发
   same-key必须收敛为一个operation ID，并发
   different-key不得突破global queue limit。
10. Error mapping固定：REPOSITORY_NOT_FOUND 404；ARTIFACT_NOT_FOUND 404（absent/cross-scope/
    binding mismatch/consumed/deleted统一）；OPERATION_NOT_FOUND 404（wrong repository也统一）；
    IDEMPOTENCY_CONFLICT 409；MANUAL_RECOVERY_REQUIRED 409（new key only）；
    IMPORT_QUEUE_FULL 429；SERVICE_NOT_READY 503（shutdown/root lock/control DB/provider）；
    DISK_ADMISSION_DENIED 503（writable/measurement/headroom）。这些都是request-layer error，不写
    operation.error_json。Control DB operational/query failure映503 / SERVICE_NOT_READY（对poll/replay也
    一样）；DB可读但row违反schema/DTO invariant时才sanitize为不泄漏的500，不返回
    SQL、row或host path。

四、capacity、poll和observability

11. Settings新增max_queued_imports=64（positive int）和import_headroom_bytes=1*1024**3
    （non-negative int），自动对应GATEWAY_REPOSITORY_MAX_QUEUED_IMPORTS /
    GATEWAY_REPOSITORY_IMPORT_HEADROOM_BYTES。保持max_import_workers=4和shutdown默认不变。
12. 新增共享import disk helper：
    baseline=max(min_free_disk_bytes, floor(total_bytes*min_free_disk_fraction))；
    admitted=free_bytes >= baseline+import_headroom_bytes。
    Submit和worker extraction前使用同一helper；exact boundary通过，boundary-1失败；
    statvfs/writable OSError fail closed。Worker侧若证明尚无Dolt effect，按现有终局
    IMPORT_REJECTED落库，不hidden retry。
13. GetOperation必须返回{"operation": {...}}外层，不得拉平。四态使用contracts
    DTO验证；FAILED仍返200，error在operation.error中且persisted request_id为None。
    Response header使用当前poll request ID，不改写durable error。
14. Structured event至少覆盖accepted/replayed/conflicted/admission-denied。只记录request ID、
    operation/repository/artifact ID、policy、duration/size、status/stable code。禁止token、raw key、
    expected/raw SHA全值、replay SQL/full stderr、host path、private ref/marker、credential和complete row。

五、测试

15. 新增DB-only unit harness：真实FastAPI TestClient/ASGI middleware + 真实SQLite v7 store +
    paused/fake dispatcher，不直接调route function，不运行dolt init。仅在需要真实
    ServiceRuntime.start/DoltRunner的case上标integration；不手写dolt skipif。只有payload/
    expected error不同的同构case使用模块级共享参数表。
16. HTTP/store/capacity tests至少覆盖：
    - auth，caller X-Request-ID不能覆盖server ID，SimpleError，missing/invalid header，invalid
      JSON，body extra/idempotency_key，path/body mismatch，policy defaults/enums；
    - new accept的QUEUED-before-202、丢弃首次202后replay原operation ID，四种operation status的
      same-key replay，different fingerprint 409；
    - replay/conflict在shutdown、provider unavailable、disk denied、queue full和MANUAL下的优先级，
      以及这些状态下GetOperation仍可读；
    - repository/artifact/operation 404、artifact cross-scope/binding/consumed/deleted、operation
      wrong-repository；
    - MANUAL只拒绝new key，global QUEUED-only limit，RUNNING/replay不占slot，并发不超限；
    - disk formula exact boundary +/-1、statvfs/writable exception fail closed、worker重复检查；
    - GetOperation {"operation": ...}四态，terminal FAILED=200，persisted error request_id=None；
    - production OpenAPI path exact set为healthz、readyz、create、upload、import、operation，断言
      import/operation method和status declarations，且无resolve/catalog/rows/admin/_test；
    - logs/caplog中无raw key、token、SQL/path/private ref/marker/row。

六、验证与提交

17. 开发时先跑定向unit。改分类后必须临时park /usr/local/bin/dolt，在
    vnext/repository_service运行uv run pytest -m unit，用trap确保恢复dolt；运行后
    明确确认dolt已恢复。
18. 提交前运行：
    - 在vnext/repository_contracts依次运行uv lock --check、uv run ruff check .、
      uv run mypy、uv run pytest -q。
    - 在vnext/repository_service依次运行uv lock --check、uv run ruff check .、
      uv run mypy、uv run pytest -q -m "not serial"、uv run pytest -q -m serial -n 0。
    - 在vnext/backend、vnext/repository_client、vnext/shared_kernel各自分别运行
      uv run ruff check . 和 uv run mypy。
    - 在仓库根运行./vnext/scripts/run-tests.sh和git diff --check。
    任一失败必须修复并重跑受影响gate，不得以历史S8计数代替S9结果。
19. 定向搜索production OpenAPI/routes，确认只新增两条route；搜索body
    idempotency_key、raw-key logging、public resolve/catalog/rows/admin/force、multipart/URL/path import、
    Candidate B和production对workflow/fixture/benchmark的依赖。Historical formal artifacts可命中，
    production code/tests/OpenAPI/current plan不得依赖旧语义。
20. Gate全green后提交code/test：
    feat(repository): activate import and operation routes
    不要把无关文档改动混入code commit。然后在本计划追加S9 handoff，至少记录
    start_sha、validated_code_sha、code_commit_sha、branch、actual modified paths、exact route set、
    admission ordering、status/code matrix、settings defaults、test markers/counts、validation commands/results、
    fault points、old-reference searches、first failures/fixes、known limitations、stage_exit和
    next_stage=P2-R4-S10。
    上述SHA字段是本节对§4通用handoff template的S9明确替代。为避免commit自引用，
    已提交的handoff正文不填它自己的SHA，不通过amend追逐
    head_sha；最终回复单独报告实际handoff commit SHA和当前git rev-parse HEAD。
    未提交、worktree不clean、required gate失败或required test被skip/xfail时，
    stage_exit=no-go、next_stage_ready=no。
```

### S9 handoff

```yaml
start_sha: fe734b4
validated_code_sha: 11fcf1b
code_commit_sha: 11fcf1b
branch: phase1/gate-ownership-repair
actual_modified_paths:
  - vnext/repository_service/src/gateway_repository_service/app.py
  - vnext/repository_service/src/gateway_repository_service/capacity.py
  - vnext/repository_service/src/gateway_repository_service/settings.py
  - vnext/repository_service/src/gateway_repository_service/http/routes/imports.py
  - vnext/repository_service/src/gateway_repository_service/http/routes/operations.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/command.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/__init__.py
  - vnext/repository_service/tests/test_capacity.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_operation_http.py
  - vnext/repository_service/tests/test_import_submission.py
  - vnext/repository_service/tests/support/http_harness.py
  - vnext/repository_service/tests/test_import_operation_store.py
  - vnext/repository_service/tests/test_import_worker.py
  - vnext/repository_service/tests/test_settings.py
  - vnext/repository_service/tests/test_http_shell.py
  - vnext/repository_service/tests/test_create_repository_http.py
  - vnext/repository_service/tests/test_upload_artifact_http.py
  - vnext/repository_service/tests/test_auth_lifecycle.py
  - vnext/repository_service/tests/test_p2_r2_compose_integration.py
  - vnext/repository_service/tests/test_dolt_runner_shutdown.py
  - vnext/repository_service/tests/test_import_shutdown.py
exact_route_set:
  - POST /v1/repositories/{repository_id}/versioned/imports -> 202 SubmitVersionedImportResponse
  - GET /v1/repositories/{repository_id}/operations/{operation_id} -> 200 GetOperationResponse
production_openapi_paths:
  - /healthz
  - /readyz
  - /v1/repositories
  - /v1/repositories/{repository_id}/artifacts
  - /v1/repositories/{repository_id}/versioned/imports
  - /v1/repositories/{repository_id}/operations/{operation_id}
admission_ordering:
  - durable same-key lookup (replay 202 or conflict 409) before any effect-only gate
  - missing key external preflight: shutdown/root lock/control DB/provider/repository/artifact/disk
  - BEGIN IMMEDIATE admit_new_import: create ledger, manual barrier, global QUEUED count, artifact lifecycle binding, insert QUEUED
  - commit then worker notify then 202
status_code_matrix:
  submit: [202, 401, 404, 409, 422, 429, 503]
  get_operation: [200, 401, 404, 422, 503]
  replay_conflict_priority: replay and IDEMPOTENCY_CONFLICT precede shutdown/provider/disk/queue/MANUAL gates
settings_defaults:
  max_queued_imports: 64
  import_headroom_bytes: 1073741824
  max_import_workers: 4
  import_shutdown_grace_seconds: 2.0
test_markers_counts:
  repository_contracts_pytest: 64 passed
  repository_service_unit_parked_dolt: 600 passed, 1 skipped
  repository_service_parallel: 853 passed, 1 skipped
  repository_service_serial: 30 passed
  run_tests_sh: green (five packages)
validation_commands_results:
  - "vnext/repository_contracts: uv lock --check, ruff, mypy, pytest -q -> pass (64)"
  - "vnext/repository_service: uv lock --check, ruff, mypy, pytest -m 'not serial', pytest -m serial -n 0 -> pass"
  - "vnext/backend, repository_client, shared_kernel: ruff, mypy -> pass"
  - "./vnext/scripts/run-tests.sh -> pass"
  - "git diff --check -> pass"
fault_points:
  - nested mutation_store transaction deadlock inside admit_new_import (fixed with locked SQL helpers)
  - HTTP harness provider readiness when /usr/local/bin/dolt parked (fixed with tmp_path dolt stub)
old_reference_searches:
  - production routes: only import/operation added; no resolve/catalog/rows/admin/_test
  - body idempotency_key: only negative validation test payload
  - raw-key logging: caplog asserts no raw key/token in import HTTP tests
  - Candidate B / multipart / URL path import: no production hits
first_failures_and_fixes:
  - admit_new_import deadlock on mutation_store nested lock -> inline locked SQL for create/artifact checks
  - import HTTP tests hung on missing dolt binary -> harness dolt stub + provider_gate path
  - unit gate with dolt parked: dolt_runner_shutdown + worker-hang shutdown tests marked integration
known_limitations:
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
  - integration submit happy-path depends on real create/upload/import stack
stage_exit: pass
next_stage_ready: yes
next_stage: P2-R4-S10
```

#### S9 handoff amendment (review fixes)

```yaml
review_fix_commit_sha: 46a6037
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope, out of S9
review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_operation_http.py
  - vnext/repository_service/tests/test_import_operation_store.py
  - vnext/repository_service/tests/test_dolt_runner_shutdown.py
  - vnext/repository_service/tests/test_import_worker.py
review_fix_summary:
  - ValidationError from durable row mapping -> 500 INTERNAL_ERROR (not 503) on lookup/admit/get_operation
  - admit_new_import rechecks has_published_artifact_file inside BEGIN IMMEDIATE via layout parameter
  - expanded replay/admission HTTP test matrix; dolt_runner_shutdown restored to unit (dolt stub + _validate_version patch)
  - worker disk-admission test starts pool only after patch to avoid parallel flake
test_markers_counts:
  repository_service_unit_parked_dolt: 618 passed, 1 skipped
  repository_service_parallel: 869 passed, 1 skipped
  repository_service_serial: 30 passed
validation_commands_results:
  - "directed import/operation/submission/store/dolt_runner/worker tests -n 0 -> pass (77)"
  - "repository_service: uv lock --check, ruff, mypy -> pass"
  - "repository_service: pytest -m 'not serial', pytest -m serial -n 0 -> pass"
  - "repository_service unit (dolt parked): pytest -m unit -> pass (618)"
  - "./vnext/scripts/run-tests.sh x3 -> pass (one unrelated provider flake on attempt 2)"
  - "git diff --check -> pass"
first_failures_and_fixes:
  - P1 invariant row mapping returned 503 -> _map_store_error separates ValidationError (500) from sqlite3 operational (503)
  - P2 admit transaction skipped ready-file recheck -> layout + has_published_artifact_file in _verify_artifact_lifecycle_binding
  - P2 incomplete replay/admission matrix -> parametrized HTTP/submission/store tests
  - P2 dolt_runner_shutdown mis-tagged integration -> dolt stub + patch _validate_version, removed pytestmark
  - P2 worker disk test flake -> defer pool.start() until after patch
  - P3 integration happy path -> assert 202 + GET 200 with matching operation_id (no worker timing dependency)
stage_exit: no-go
next_stage_ready: no
```

#### S9 handoff amendment (re-review remediation)

```yaml
re_review_fix_commit_sha: 86b84dd
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
contracts_scope_amendment:
  - RepositoryArtifactRef.size_bytes Field(le=2**64-1) aligned with fingerprint struct.pack(">Q")
re_review_fix_paths:
  - vnext/repository_contracts/src/gateway_repository_contracts/versioned.py
  - vnext/repository_contracts/tests/test_versioned.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/admin.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/__init__.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_operation_http.py
  - vnext/repository_service/tests/test_import_submission.py
  - vnext/repository_service/tests/test_import_operation_store.py
  - vnext/repository_service/tests/test_import_worker.py
  - vnext/repository_service/tests/support/http_harness.py
re_review_fix_summary:
  - ImportStoreInvariantError + lookup_replay_state; JSON/UUID decode -> 500, sqlite3 -> 503
  - removed in-tx has_published_artifact_file; submission _assert_artifact_ready_for_admission outside tx
  - contracts size_bytes upper bound; submission OverflowError/ValueError -> 422
  - closed S9 required test matrix (RUNNING poll, conflict gates, artifact 404 variants, notify-after-commit, caplog, writable, serial worker)
  - reverted versioned_import/__init__.py extra exports; admin CLI catches ImportStoreInvariantError exit 4
test_markers_counts:
  repository_contracts_pytest: 66 passed
  repository_service_unit_parked_dolt: 630+ passed, 1 skipped
  repository_service_parallel: 888 passed, 1 skipped
  repository_service_serial: 31 passed
validation_commands_results:
  - "directed import/operation/submission/store tests -n 0 -> pass (97+)"
  - "repository_contracts + repository_service: uv lock --check, ruff, mypy -> pass"
  - "repository_service: pytest -m 'not serial', pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> pass"
  - "git diff --check -> pass"
first_failures_and_fixes:
  - P2 bidirectional store error misclassification -> ImportStoreInvariantError + lookup_replay_state + _map_store_error
  - P2 uint64 size_bytes fingerprint overflow -> contracts Field(le=2**64-1) + submission 422 guard
  - P2 in-tx file SHA-256 under store lock -> moved FS recheck to submission pre-admit (TOCTOU documented)
  - P2 incomplete required test matrix + worker serial marker -> expanded parametrized HTTP/submission tests
  - P2 handoff stage_exit pass with dirty worktree -> corrected to no-go
  - P3 __init__.py export surface -> reverted to pre-S9 exports
known_limitations:
  - preflight-to-insert artifact TOCTOU remains; full pin protocol deferred
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 remediation/re-review
```

#### S9 handoff amendment (third-review remediation)

```yaml
third_review_fix_commit_sha: 2c0a4d6
re_review_fix_commit_sha_retroactive: 86b84dd  # corrects 4c037f5 TBD omission
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
third_review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/upload_artifact/admission_pin.py
  - vnext/repository_service/src/gateway_repository_service/upload_artifact/visibility.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/command.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_import_submission.py
  - vnext/repository_service/tests/test_import_operation_store.py
third_review_fix_summary:
  - ArtifactAdmissionPin flock protocol coordinates submit admission with cleanup try_unlink_ready_artifact
  - preflight DB-backed checks map sqlite3 faults to 503 via _map_store_error(context=preflight)
  - _parse_request_fingerprint rejects non-bytes SQLite types as ImportStoreInvariantError -> 500 on replay
  - TOCTOU regression tests (unlink-before-admit, cooperative cleanup blocked during pin)
test_markers_counts:
  repository_contracts_pytest: 66 passed
  repository_service_unit: 647 passed, 1 skipped
  repository_service_parallel: 896 passed, 1 skipped
  repository_service_serial: 32 passed
validation_commands_results:
  - "directed admission/fingerprint/preflight/sqlite tests -n 0 -> pass (15+)"
  - "repository_service: uv lock --check, ruff, mypy -> pass"
  - "repository_service: pytest -m unit, pytest -m 'not serial', pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> pass"
  - "git diff --check -> pass"
first_failures_and_fixes:
  - P2 artifact TOCTOU accepted QUEUED without ready file -> admission pin + assert_unchanged before BEGIN/INSERT
  - P2 preflight SQLite faults returned 500 -> wrap _preflight_new_effect with _map_store_error
  - P2 fingerprint TEXT/INTEGER replay returned 503 -> _parse_request_fingerprint -> ImportStoreInvariantError
  - P3 handoff 4c037f5 re_review_fix_commit_sha TBD -> retroactive 86b84dd + third amendment records 2c0a4d6
known_limitations:
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 fourth-review remediation
```

#### S9 handoff amendment (fourth-review remediation)

```yaml
fourth_review_fix_commit_sha: 2a20e80
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
fourth_review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/upload_artifact/admission_pin.py
  - vnext/repository_service/src/gateway_repository_service/mutation_store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/tests/test_import_http.py
fourth_review_fix_summary:
  - finalize_new_admission + __exit__ st_nlink guard; abort_queued_import on artifact loss
  - removed all filesystem checks from BEGIN IMMEDIATE path in admit_new_import
  - MutationStoreInvariantError for malformed artifact_lifecycle decode -> 500 on preflight
  - preflight explicit error taxonomy; _map_store_error no longer default-maps unknown to 503
  - serial TOCTOU tests including post-finalize unlink; malformed lifecycle scope HTTP test
test_markers_counts:
  repository_contracts_pytest: 66 passed
  repository_service_unit: 649 passed, 1 skipped
  repository_service_parallel: 896 passed, 1 skipped
  repository_service_serial: 34 passed
validation_commands_results:
  - "directed admission/finalize/lifecycle/preflight/sqlite tests -n 0 -> pass (12+)"
  - "repository_service: ruff, mypy -> pass"
  - "repository_service: pytest -m unit, pytest -m 'not serial', pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> pass"
  - "git diff --check -> pass"
first_failures_and_fixes:
  - P2 in-tx assert_unchanged + post-check TOCTOU -> finalize outside tx + __exit__ nlink guard + abort_queued_import
  - P2 malformed lifecycle preflight -> 503 -> MutationStoreInvariantError + explicit preflight mapping
  - P2 TOCTOU test missing serial marker -> @pytest.mark.serial + post-finalize regression
  - P2 handoff pass with dirty worktree -> third-review corrected to no-go; fourth stays no-go until clean
known_limitations:
  - cooperative cleanup excluded by admission pin flock; external durable-root tampering outside support surface
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 fourth-review remediation
```

#### S9 handoff amendment (fifth-review remediation)

```yaml
fifth_review_fix_commit_sha: 8a9b435
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
fifth_review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/control_db.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_import_operation_store.py
  - vnext/repository_service/tests/test_operation_http.py
  - vnext/repository_service/tests/test_auth_lifecycle.py
  - vnext/repository_service/tests/test_import_admin_cli.py
  - vnext/repository_service/tests/test_settings.py
  - vnext/repository_service/tests/support/import_admin_cli_harness.py
fifth_review_fix_summary:
  - two-phase admission ADMISSION_PENDING -> publish_queued_import -> QUEUED closes commit/finalize vs dispatcher claim race
  - publish runs only after ArtifactAdmissionPin __exit__ succeeds; abort_admission_import on failure
  - abort failure must not return false 404 when row already QUEUED/RUNNING; replay-safe 202 via _abort_pending_admission_or_replay
  - control DB v8 migration extends repository_import_operations status CHECK with ADMISSION_PENDING
  - queue count and protected artifact pins include ADMISSION_PENDING; wire poll still maps to OperationStatus.QUEUED
test_markers_counts:
  repository_service_unit: 654 passed, 1 skipped
  repository_service_parallel: 899 passed, 1 skipped
  repository_service_serial: 36 passed
validation_commands_results:
  - "directed admission/pending/publish/claim_before tests -n 0 -> pass (13)"
  - "repository_service: ruff, mypy -> pass"
  - "repository_service: pytest -m unit, pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> pass"
first_failures_and_fixes:
  - P1 admit QUEUED before finalize let dispatcher claim -> ADMISSION_PENDING durable status + publish after pin release
  - P1 abort_queued_import false on RUNNING still returned 404 -> abort_admission_import + replay when publish/claim won race
  - schema CHECK blocked ADMISSION_PENDING -> control DB migration v8
known_limitations:
  - cooperative cleanup excluded by admission pin flock; external durable-root tampering outside support surface
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 fifth-review remediation
```

#### S9 handoff amendment (sixth-review remediation)

```yaml
sixth_review_fix_commit_sha: 4d7c60b
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
sixth_review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/recovery.py
  - vnext/repository_service/src/gateway_repository_service/mutation_reconciliation.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/admin.py
  - vnext/repository_service/tests/test_import_operation_store.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_import_recovery.py
sixth_review_fix_summary:
  - StoredImportOperation/ReplayLookup retain durable_status; pending no longer maps to wire QUEUED
  - same-key replay waits for publish/abort via _await_admission_resolution; GET hides pending rows
  - ImportStartupReconciler publishes or aborts orphan ADMISSION_PENDING before worker start
  - list_artifact_references and readiness handle pending as protected internal reference
  - sqlite publish failure on pending admission routes through abort/replay instead of orphaning
fifth_review_correction:
  - fifth-review handoff claimed wire poll maps pending to QUEUED; sixth review removes that mapping
test_markers_counts:
  repository_service_unit: 658 passed, 1 skipped
  repository_service_parallel: 902 passed, 1 skipped
  repository_service_serial: 37 passed
validation_commands_results:
  - "directed pending/replay/reconcile tests -n 0 -> pass (40+)"
  - "repository_service: ruff, mypy -> pass"
  - "repository_service: pytest -m unit, pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> pass (one import_provider flake on run 2)"
first_failures_and_fixes:
  - P1 same-key replay returned 202 for unpublished pending -> durable_status + admission wait loop
  - P1 crash/publish orphan ADMISSION_PENDING -> startup reconciler publish/abort + sqlite abort path
  - P2 list_artifact_references ValueError on pending -> durable_status on ArtifactOperationReference
  - P3 handoff uncommitted_paths incomplete -> sixth amendment lists actual dirty files
known_limitations:
  - cooperative cleanup excluded by admission pin flock; external durable-root tampering outside support surface
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 sixth-review remediation
```

#### S9 handoff amendment (seventh-review remediation)

```yaml
seventh_review_fix_commit_sha: 78d546a
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
seventh_review_fix_paths:
  - vnext/repository_service/src/gateway_repository_service/versioned_import/submission.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/store.py
  - vnext/repository_service/src/gateway_repository_service/versioned_import/models.py
  - vnext/repository_service/tests/test_import_http.py
  - vnext/repository_service/tests/test_import_submission.py
  - vnext/repository_service/tests/test_import_operation_store.py
seventh_review_fix_summary:
  - pending replay checks fingerprint before _await_admission_resolution for immediate 409
  - _raise_after_pending_admission_failure maps sqlite/store errors to 503 and artifact loss to 404
  - abort/await helper DB calls wrapped with _map_store_error
  - validate_pending_operation_row rejects terminal payload on ADMISSION_PENDING rows
sixth_review_correction:
  - sixth-review validation_commands claimed run-tests.sh x3 pass with parenthetical flake; accurate record is 2 pass / 1 flake
test_markers_counts:
  repository_service_unit: 663 passed, 1 skipped
  repository_service_parallel: 905 passed, 1 skipped
  repository_service_serial: 39 passed
validation_commands_results:
  - "directed pending/fingerprint/sqlite/invariant tests -n 0 -> pass (31)"
  - "repository_service: ruff, mypy -> pass"
  - "repository_service: pytest -m unit, pytest -m serial -n 0 -> pass"
  - "./vnext/scripts/run-tests.sh x3 -> 2 pass, 1 flake (test_import_provider.py::test_concurrent_streams_keep_field_limit on run 2)"
first_failures_and_fixes:
  - P1 pending different-fingerprint waited then 404/503 -> fingerprint conflict before admission wait
  - P1 publish sqlite error returned 404 after abort -> _raise_after_pending_admission_failure cause typing
  - P2 helper sqlite errors became 500 -> _map_store_error on abort/await durable-status reads
  - P2 pending row accepted error_json -> validate_pending_operation_row fail closed
  - P3 handoff x3 pass overstated -> seventh amendment records 2 pass / 1 flake
known_limitations:
  - cooperative cleanup excluded by admission pin flock; external durable-root tampering outside support surface
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 seventh-review remediation
```

#### S9 handoff amendment (eighth-review remediation)

```yaml
eighth_review_fix_commit_sha: 426c712
worktree_clean: false
uncommitted_paths:
  - docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md  # S8 scope
eighth_review_fix_paths:
  - vnext/repository_service/tests/test_import_submission.py
eighth_review_fix_summary:
  - test_pending_admission_resolution_sqlite_fault_maps_to_service_not_ready marked @pytest.mark.serial
  - try/finally ensures resume_admit.set() and first_thread.join on assertion failure
test_markers_counts:
  repository_service_unit: 663 passed, 1 skipped
  repository_service_parallel: 904 passed, 1 skipped
  repository_service_serial: 40 passed
validation_commands_results:
  - "test_pending_admission_resolution_sqlite_fault_maps_to_service_not_ready -n 0 -> pass"
  - "repository_service: pytest -m serial -n 0 -> pass (40)"
  - "repository_service: pytest -m not serial --co confirms test excluded from parallel collection"
  - "repository_service: ruff check tests/test_import_submission.py -> pass"
first_failures_and_fixes:
  - P2 timing-sensitive admission test missing @pytest.mark.serial -> serial marker + try/finally thread cleanup
known_limitations:
  - cooperative cleanup excluded by admission pin flock; external durable-root tampering outside support surface
  - S10 still owns real-Dolt/process-crash/Compose matrix
  - no P2-R5 public reads or public admin API
stage_exit: no-go
next_stage_ready: no
next_stage: P2-R4-S9 eighth-review remediation
```

### Accepted S9 exit and S10 readiness — 2026-08-08

`426c712`闭合第八轮唯一P2测试分类问题，`7850ef3`记录最终S9 handoff；第八轮独立复审
未发现新的production问题。此前`stage_exit: no-go`的唯一剩余原因是S8起源的详细设计文档
仍有未提交澄清。用户已明确授权把该文档与S10准备修订一并提交；该documentation commit
完成且worktree clean后，较早的no-go记录由本节取代：

```yaml
s9_final_production_fix_sha: 78d546a
s9_final_test_fix_sha: 426c712
s9_final_handoff_sha: 7850ef3
control_db_user_version: 8
wire_operation_statuses: [QUEUED, RUNNING, SUCCEEDED, FAILED]
internal_admission_status: ADMISSION_PENDING
s9_review_exit: pass
stage_exit: pass
next_stage_ready: yes
next_stage: P2-R4-S10
```

S10实现者以包含本节的clean HEAD为`start_sha`，不重开已闭合的S9复审；若HEAD或worktree
发生漂移，仍按§2暂停并报告。

## 14. S10 — Full fault matrix, real Dolt, Compose and handoff

### Goal

以S9最终v8两阶段admission为基线，执行并闭合P2-R4完整required gate；补齐全部真实
process-crash、response-loss、Candidate A/Dolt和正式Compose restart/replay coverage，只修复
gate暴露的R4缺陷，形成最终green regression commit与P2-R4 handoff。S10不重新设计wire、
operation四态、provider选择或admission协议。

### Entry baseline and authority

开始条件：包含上节S9 accepted exit、worktree clean、HEAD未漂移。实现者必须完整读取：

- Repository Service Contract §§9–12、§14、§17；
- External Effect and Recovery Contract §§5、7、9；
- 详细设计§§14、19–22；
- P2 Execution Checklist §§1–2、§6；
- `AGENTS.md`与`docs/backend-vnext/testing-conventions.md`；
- 当前production `Dockerfile`、`compose.yaml`及所有import recovery/fault harness。

固定入口事实：`CONTROL_DB_USER_VERSION = 8`；`ADMISSION_PENDING`只在SQLite内部存在；
public operation仍只有QUEUED/RUNNING/SUCCEEDED/FAILED。S10不得恢复v7 schema假设，也不得把
pending映射成wire QUEUED或提前返回202。

### Allowed paths

```text
vnext/repository_contracts/src/gateway_repository_contracts/                # gate fixes only
vnext/repository_contracts/tests/
vnext/repository_service/tests/
vnext/repository_service/tests/support/
vnext/repository_service/src/gateway_repository_service/versioned_import/   # gate发现的R4 fixes only
vnext/repository_service/src/gateway_repository_service/upload_artifact/    # admission pin fixes only
vnext/repository_service/src/gateway_repository_service/control_db.py       # v8 gate fixes only
vnext/repository_service/src/gateway_repository_service/mutation_store.py   # binding fixes only
vnext/repository_service/src/gateway_repository_service/mutation_reconciliation.py
vnext/repository_service/src/gateway_repository_service/capacity.py         # gate fixes only
vnext/repository_service/src/gateway_repository_service/runtime.py          # gate fixes only
vnext/repository_service/src/gateway_repository_service/process.py          # gate fixes only
vnext/repository_service/src/gateway_repository_service/http/               # gate fixes only
vnext/repository_service/src/gateway_repository_service/settings.py         # gate fixes only
vnext/repository_service/src/gateway_repository_service/app.py              # composition fixes only
vnext/repository_service/pyproject.toml                                     # test/dependency fix only
vnext/repository_service/uv.lock                                            # only if exact dependency changes
vnext/repository_service/Dockerfile
vnext/deploy/compose.yaml
vnext/scripts/run-tests.sh                                                  # gate infrastructure fixes only
vnext/scripts/build-repository-service-image.sh                             # S10 compose provenance build
vnext/deploy/p2r1-cache/README.md                                           # S10 compose cache reuse note only
vnext/repository_service/README.md
docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p2-r4-async-versioned-import-implementation-design.md
```

任何超出上述R4 fix scope的失败先报告，不借final gate实施重构、P2-R5或R6功能。不得修改
Repository Client、Backend、Rust/canonical owner、P2-R1 workflow/matrix或公开R5 route。
若修改`uv.lock`，依赖必须`==`精确钉版本并同步Dockerfile `UV_LOCK_SHA256`。

### Required final matrix

先建立一张可审阅matrix，至少有`case/nodeid`、`fault boundary`、`pre-crash durable evidence`、
`restart action`、`expected final state`、`marker`和`result`列；不得仅用聚合pytest通过推断覆盖。

1. Baseline regression：
   - v6 -> v8、v7 -> v8、fresh v8/newer-version；pending row shape、protection、publish/abort；
   - four wire states、same-key原202、different-fingerprint立即409、poll/replay priority；
   - package streaming security与entry/single/payload-total/decoder-total exact boundaries；
   - `NONE/STRUCTURAL/FULL_SCAN × REJECT/STRINGIFY`、expected parent、两次main check、publish readback；
   - verification failure main unchanged、normal failure无hidden retry、private-ref/artifact cleanup；
   - MANUAL barrier/occupancy、multi-operation artifact pin、admin全部positive/negative/audit；
   - graceful shutdown child TERM/KILL/wait/reap与RUNNING restart recovery。
2. Admission/HTTP process crash：
   - `after_admission_pending_commit`：不得返回202；crash后DB保留同一pending identity，restart在
     artifact有效时发布同一operation并最终执行，无效artifact的定向case只abort pending；
   - `after_queued_publish_before_202`：DB已QUEUED但caller无response，原key/body重放必须返回
     同一operation ID/202，不创建第二row、不多占slot；
   - pending期间same-fingerprint等待resolution，different-fingerprint不等待并立即409；
   - harness只能位于tests/support或test process，不能新增public/env production fault开关。
3. Worker/recovery真实process crash：
   - `ImportWorkerFaultPoint`现有十项逐项覆盖：after running claim、package extracted、private ref、
     replay before marker、marker before verification、verification before second main check、second
     main check before publish、main publish before SUCCEEDED、SUCCEEDED before private cleanup、
     SUCCEEDED before artifact cleanup；
   - 每项使用真实Candidate A/Dolt subprocess和`os._exit`后重启，不以同进程exception测试代替；
   - 每项断言operation、main、marker/private ref、artifact、automatic replay count和最终cleanup；
   - `after_automatic_replay_count_increment`再次crash/restart后count仍为1，绝不第二次replay SQL；
   - ambiguous evidence进入MANUAL并保留artifact/ref，确定性evidence最终收敛到唯一SUCCEEDED或
     ordinary stable failure。
4. Required test integrity：
   - 上述process/runtime/Dolt tests同时标`integration`与`serial`；Event/join/subprocess timeout
     tests不得进入parallel pass；
   - required case的passed/skipped/xfail逐项统计，required skipped=0、xfail=0；
   - DB-only/parser/validation tests在Dolt parked时`pytest -m unit`通过且零`dolt init`。
5. Production Compose：
   - 正式Dockerfile和`repository-service` service，不使用P2-R1 `repository-probe`代替；
   - 唯一project name、临时bearer secret、真实named durable volume；先config/build，再up/health；
   - 通过正式HTTP完成create -> upload -> import -> poll SUCCEEDED，保存operation/result；
   - 不删除volume地stop/recreate或restart service，再验证GetOperation与same-key Submit仍返回
     原operation/result；不得调用尚未激活的R5 resolve/catalog/rows；
   - trap执行project-scoped `down -v --remove-orphans`，并按Compose project label验证container、
     network、volume零残留；registry/network/build失败必须no-go，不能降级为host/mock pass。
6. Final hygiene：old-reference searches、`git diff --check`、精确test counts和最终clean worktree。

### Code implementation prompt

```text
请执行 P2-R4-S10 — Final Fault/Dolt/Compose Gate and Handoff。该stage只闭合R4完整gate、修复
gate发现的R4缺陷并形成handoff；不得实现P2-R5、Backend consumer、TTL scheduler或完整R6
capacity/backup。

开始前核对上节accepted S9 exit、HEAD和clean worktree，记录start_sha。完整读取本节Entry
baseline列出的authority及当前代码/测试。固定control DB v8与内部ADMISSION_PENDING；public
operation仍为四态。先建立required matrix清单，逐项关联现有nodeid、缺口和期望durable
evidence，不要只跑聚合pytest后声称覆盖。

先补测试缺口：tests/support admission subprocess harness覆盖
after_admission_pending_commit与after_queued_publish_before_202；扩展真实Dolt crash harness覆盖
ImportWorkerFaultPoint全部十项及after_automatic_replay_count_increment。每例必须真正终止进程、
重开DB/runtime并断言operation/main/marker/private-ref/artifact/replay-count/final cleanup。
Process、restart、Event/join和真实Dolt tests必须正确标integration+serial；不得把production
fault开关加入DTO、header、settings默认或OpenAPI。Required cases零skip/xfail。

验证顺序：先定向tests，再执行contracts的lock/ruff/mypy/pytest；service执行lock/ruff/mypy、
pytest -m "not serial"和pytest -m serial -n 0。按AGENTS.md用trap临时park Dolt并执行
pytest -m unit，确保失败也恢复binary。最后运行./vnext/scripts/run-tests.sh覆盖五包并记录精确
counts。不要对repository_service裸跑全量pytest作为权威结果。

运行真实Candidate A/Dolt matrix。以唯一Compose project name和临时secret执行正式
repository-service Dockerfile/Compose config/build/up/health，通过HTTP完成create -> upload ->
import -> poll SUCCEEDED；保留named volume重启service后验证GetOperation和same-key replay的
原operation/result。用trap执行project-scoped down -v --remove-orphans，并按project label确认
container/network/volume零残留。网络/registry/build失败必须报告no-go，不得降级成mock pass。

运行git diff --check、定向old-reference searches：body idempotency_key、旧verification/status、
generic journal、Candidate B、gzip/multipart/URL/path、public force/admin、production import
workflow/fixture/matrix。人工区分historical docs命中与current production错误引用。

只在全部code/test/container gate通过后创建green commit：
test(repository): close Versioned import delivery gate

随后把final matrix与handoff写入执行计划并提交：
docs(p2-r4): record final Versioned import handoff

提交后确认git status clean，按执行计划§4和详细设计§21输出完整P2-R4 handoff：所有commit
SHA、DB version=8、internal admission/wire boundary、routes、limits/workers、test counts、逐项
fault matrix、Dolt/Compose/cleanup、old-reference分类、known limitations、
production_retest_required、p2_r4_exit和p2_r5_ready。任一required gate失败、skip/xfail、Compose
残留或worktree dirty都必须no-go。不要开始P2-R5。
```

### S10 interim handoff — 2026-08-09（Compose gate 待远端 cache）

`start_sha`: `74ccbebe02cfa8b3f408f7ca38fe80dd87996be7`（`docs(p2-r4): prepare S10 final delivery gate`）

实现与定向 gate 已完成；正式 Compose restart/replay gate 最初因本机无 P2-R1 cache 阻塞。
本节保留为历史记录；**最终 accepted exit 见下节**。

```yaml
stage_exit: no-go
production_compose_restart_replay: blocked
blocker: "P2-R1 cache 502; compose e2e 未跑通"
```

### S10 audit remediation — 2026-08-09

`start_sha`: `4b0078f589c1a9608d2ce83e62c51a45e2308e19`（`test(repository): unify build context content digest`）

审计 NO-GO 后 Wave1+Wave2 修复已闭合；formal exit 见下节。

```yaml
audit_remediation_closed:
  wave1:
    - import startup recovery: provider/read-ref failure → blocking_failures + ServiceStartupError
    - dependency-base reuse bound to uv.lock digest label
    - compose gate rerun at HEAD with matching image provenance
  wave2:
    - admission crash abrupt os._exit; queued publish asserts DB QUEUED + replay 202
    - dolt crash durable evidence helper (main/private-ref/records row count)
    - mutation reconciliation multi-reference + published artifact hash check
    - compose cleanup: container ls -a; compose down exit code enforced
    - serial markers on timing-sensitive integration tests
    - automatic replay count SQL side-effect bounded (records_row_count <= 1)
```

### Accepted S10 exit and P2-R4 handoff — 2026-08-09 (audit remediation round 2, final)

`start_sha`: `74ccbebe02cfa8b3f408f7ca38fe80dd87996be7`
`validated_code_sha`: `f0a14abde13799025637f9bf989ed33ece498aa2`
`handoff_record_commit_sha`: pending

```yaml
round: P2-R4
review_state: pass
s10_start_sha: 74ccbeb
validated_code_sha: f0a14abde13799025637f9bf989ed33ece498aa2
handoff_record_commit_sha: pending
handoff_fixup_commits:
  - 414574c9284b013decdbb2ace8987fb2968c0c58
s10_round2_prior_commits:
  - 49d123d9335301ee468c2a03ac8d6c6af6ec64a7
  - 197dcff453a3f3526e53fb917897f0be62ca1d99
  - 3bb7d32eda629a5eafa0bd65018da4328add1a1b
  - eaf9afca2c966f8214b172fe7c3cff4cc396c978
branch: phase1/gate-ownership-repair
worktree_clean: pending
control_db_user_version: 8
stage_exit: pass
production_compose_restart_replay: pass
p2_r4_exit: pass
p2_r5_ready: yes
production_retest_required: yes

internal_admission_protocol:
  internal_status: ADMISSION_PENDING
  wire_statuses: QUEUED | RUNNING | SUCCEEDED | FAILED
  boundary: ADMISSION_PENDING only in control DB / recovery / directed tests

selected_provider: candidate_a_offline_cli
dolt_version: 2.1.11

activated_routes:
  - POST /v1/repositories/{repository_id}/versioned/imports
  - GET /v1/repositories/{repository_id}/operations/{operation_id}

package_and_worker_settings:
  max_upload_bytes: 268435456
  max_replay_sql_bytes: 209715200
  max_manifest_json_bytes: 16777216
  max_total_expanded_entry_bytes: 4294967296
  max_decompressed_tar_stream_bytes: 4294967296
  max_import_workers: 4
  max_queued_imports: 64
  import_headroom_bytes: 1073741824
  min_free_disk_bytes: 5368709120
  min_free_disk_fraction: 0.10
  admission: disk admission before package extraction

contracts_gate:
  command: uv lock --check && uv run ruff check . && uv run mypy && uv run pytest -q
  result: pass
  test_count: 66

service_gate:
  commands:
    - uv lock --check && uv run ruff check . && uv run mypy
    - uv run pytest -q -m "not serial"
    - uv run pytest -q -m serial -n 0
    - pytest -m unit with dolt parked
  result: pass
  parallel_count: 935
  parallel_skipped: 1
  serial_count: 61
  unit_dolt_parked_count: 700
  unit_dolt_parked_skipped: 1

fault_matrix_results:
  admission_process_crash: passed=3 skipped=0 xfailed=0
  worker_dolt_process_crash: passed=10 skipped=0 xfailed=0
  recovery_count: passed=1 skipped=0 xfailed=0
  mutation_restart: passed=1 skipped=0 xfailed=0
  production_compose_restart_replay: passed=1 skipped=0 xfailed=0

real_dolt_result: pass
compose_project: ephemeral_per_run
compose_project_pattern: gateway-p2r4-s10-*
compose_cleanup_result: pass
startup_replay_result: pass
manual_recovery_result: pass
artifact_cleanup_result: pass
git_diff_check: pass

repository_service_image:
  tag: gateway-repository-service:local
  image_id: sha256:65dea7e7e30963e5897a192ee4ecf7e7d9acdcbca424d55a6e2d26ffc56b6ba1
  source_tree_sha256: sha256:5ef954100c58ae3d2822fa587515b59ca34e2424b7161b3f6d92756c5aba85be
  build_input_revision: f0a14abde13799025637f9bf989ed33ece498aa2
  image_matches_build_context: true

gate_counts:
  shared_kernel: 232
  repository_contracts: 66
  repository_client: 15
  backend: 18
  repository_service_parallel: 935
  repository_service_parallel_skipped: 1
  repository_service_serial: 61
  unit_dolt_parked: 700
  unit_dolt_parked_skipped: 1

static_closeout_pending: []

required_fault_matrix_nodeids:
  admission_process_crash:
    - test_import_admission_crash.py::test_crash_after_pending_commit_restarts_to_succeeded
    - test_import_admission_crash.py::test_crash_after_queued_publish_replay_returns_same_202
    - test_import_admission_crash.py::test_crash_after_pending_commit_aborts_on_restart
  worker_dolt_process_crash:
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_running_claim]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_package_extracted]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_private_ref_created]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_replay_before_marker]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_marker_before_verification]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_verification_before_second_main_check]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_second_main_check_before_publish]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_main_publish_before_succeeded]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_succeeded_before_private_ref_cleanup]
    - test_import_dolt_crash.py::test_dolt_crash_recovery[after_succeeded_before_artifact_cleanup]
  recovery_count:
    - test_import_recovery.py::test_crash_after_automatic_replay_increment_preserves_count
  mutation_restart:
    - test_mutation_readiness.py::test_consumed_artifact_missing_bytes_does_not_block_readiness
  production_compose_restart_replay:
    - test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay

round2_remediation_closed:
  - dolt crash-state marker zero/unique/refs/head evidence
  - import_replay_audit table absent assertions
  - compose build subprocess timeout (harness + script)
  - handoff schema uses validated_code_sha / handoff_record_commit_sha

old_reference_searches:
  idempotency_key: production code uses header-only; no body persistence
  legacy_verification_states: historical formal artifacts only
  candidate_b: not in production import path
  admission_pending_wire: internal only; not in contracts enum or OpenAPI
  timeout_markers: timing-sensitive import tests marked serial

known_limitations:
  - production_retest_required 仍按 P2-R1 v8 decision 保留
  - TTL/capacity/snapshot closure 属 P2-R6
```

### Accepted S10 exit and P2-R4 handoff — 2026-08-09 (audit remediation)

本节已由 **Accepted S10 exit and P2-R4 handoff — 2026-08-09 (audit remediation round 2)** 取代。

### Accepted S10 exit and P2-R4 handoff — 2026-08-09 (superseded)

本节已由 **Accepted S10 exit and P2-R4 handoff — 2026-08-09 (audit remediation)** 取代。

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

rg -n "ADMISSION_PENDING" \
  vnext/repository_contracts/src vnext/repository_service/src/gateway_repository_service/http \
  vnext/repository_service/src/gateway_repository_service/versioned_import

rg -n "Event\(|\.wait\(timeout=|\.join\(timeout=|subprocess.*timeout" \
  vnext/repository_service/tests/test_import* vnext/repository_service/tests/support/import*
```

`idempotency_key`允许出现在header model、local command parameter和test input，但不得出现在
Submit JSON model、serialized request body、log或raw persisted field。`FULL_SCAN`不是旧`FULL`；
必须人工判断而非机械删除。`ADMISSION_PENDING`允许出现在control DB/store/recovery及定向测试，
不得进入contracts enum、public response或OpenAPI。Timeout搜索必须逐个核对integration/serial
marker，不能只依赖静态扫描自动判定正确。

## 16. P2-R4 final exit

满足以下全部条件才完成本计划：

```text
S1..S10 stage_exit = pass
all suggested commits present and green
control_db_user_version = 8
selected_provider = candidate_a_offline_cli
internal_admission_status = ADMISSION_PENDING
wire_operation_statuses = QUEUED | RUNNING | SUCCEEDED | FAILED
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

### S10 closure status — 2026-08-09

§16 条件已由 S10 audit remediation round 2 handoff 闭合；commit SHA 在提交后填入。
