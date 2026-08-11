# P2 Versioned Repository Execution Checklist

状态：Accepted

日期：2026-08-02

适用范围：`P2-R1`至`P2-R6`逐轮实现

设计owner：[P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md)

## 1. Execution discipline

每个round单独执行。开始前必须确认HEAD包含上一round handoff commit、worktree clean，
完整读取本round章节及引用的owning contracts。不得跨入下一round、实现P3 capability、
Current、table/schema CAS或旧compatibility adapter。删除/改名之前先用`rg`确认全部
consumer。任何本轮测试失败都在本轮修复；允许为reviewability拆分多个green commit，
但不得提交已知失败状态。

每轮固定流程：

1. 记录`start_sha=$(git rev-parse HEAD)`和clean status。
2. 列出本轮allowed paths、explicit non-goals和expected commits。
3. 先写/更新本轮contract tests，再实现最小纵切。
4. 每个green commit前运行受影响package定向检查与`git diff --check`。
5. 本轮结束执行规定的full package/integration gate、旧引用搜索和worktree检查。
6. 只在全部required gate通过后提交handoff；外部registry/network失败不能标成通过。

### 1.1 P2后半段container gate合并规则（2026-08-09起生效）

为避免每个代码修复都重复支付镜像构建和跨主机传输成本，P2-R4 post-audit后续修复及
P2-R5默认只执行功能门禁；最终production image build、镜像传输和Compose全链路合并到
P2-R6退出前执行一次。该规则是对后续gate时点的前瞻性修订，不改写P2-R1至R4已经形成的
历史镜像、Compose和handoff证据，也不允许把旧镜像称为后续代码的验证结果。

允许延期的前提是本次变更不触碰container/build/deployment boundary。以下任一情况出现时，
不得等待R6，必须在该变更所属round立即恢复与风险匹配的build/Compose gate：

- 修改`Dockerfile`、base image、OS package、build context/provenance算法、镜像label或
  `build-repository-service-image.sh`；
- 修改`uv.lock`、production dependency、lock SHA/build arg或会改变镜像依赖闭包的配置；
- 修改`compose.yaml`、container command/user/path/volume/network/secret/env wiring、healthcheck
  或部署启动/关闭语义；
- 修改真实Docker/Compose harness本身，或功能测试暴露仅能在container boundary验证的失败；
- 安全、数据持久化或恢复结论依赖新的镜像/Compose证据。

普通application source、纯Python测试和文档变更不单独触发镜像重建。延期期间仍必须在每个
green commit做定向检查，并在R4 post-audit/R5出口跑§2定义的P2功能门禁。handoff必须同时记录
`validated_code_sha`、最近一次真实容器验证的`container_validated_code_sha`、
`container_validation_deferred_to: P2-R6`及完整`deferred_container_gate_nodeids`；两者SHA不同
时不得写`image_matches_build_context: true`，旧`image_id`只能标为historical/superseded。

该延期不等于P2完成。P2-R5可以在功能门禁通过后进入R6，但P2-R6最终候选必须通过§8的单次
完整container gate，且关闭`production_retest_required`后，才允许记录`Phase 2 complete`。

### 1.2 Candidate SHA封板与provenance提交原则

需要执行container gate时，candidate SHA与记录该SHA的provenance提交必须分离，避免
“为了写入SHA而改变SHA”或在gate后再次改变build context：

1. **先封板candidate commit**：所有production、测试、lock、Dockerfile、Compose/build/deploy以及
   `vnext/repository_service/**`、`vnext/repository_contracts/**`内的文档变更必须在candidate
   commit中完成；确认整个worktree clean后记录字面量`CANDIDATE_SHA`。
2. **candidate不得自引用自己的SHA**：位于build context内的文件只能预先写不依赖实际SHA的
   通用说明；actual SHA、image ID、source-tree digest和gate结果只能写入后续的、build context
   外部的provenance文档。
3. **gate期间不得改写candidate历史**：不得amend、rebase、squash、cherry-pick到另一个SHA后
   继续沿用原结果。任一build-input变更都产生新candidate，并使旧image/gate成为superseded。
4. **远端使用独立detached worktree**：bundle/fetch写入专用ref，再从字面量
   `CANDIDATE_SHA`创建clean detached worktree；不得强制checkout覆盖活跃开发worktree，也不得
   fetch覆盖远端当前checked-out branch。
5. **gate前后双重校验**：local/remote必须同时匹配`CANDIDATE_SHA`、
   `build_input_revision`和`source_tree_sha256`；image label也必须重放相同revision/digest。
6. **最后再提交provenance**：该提交只能修改digest范围外路径。handoff分别记录
   `validated_code_sha`/`container_validated_code_sha`（candidate）和
   `provenance_documentation_sha`（记录提交）；两者不同是预期状态，不得把文档HEAD误写为已验证
   candidate。provenance commit同样不能在自身内容中写自己的最终SHA；其SHA须在commit完成后的
   外部handoff、review记录或tag中登记，不得再创建一个只用于回填前一提交SHA的递归提交。

一旦provenance提交触及`vnext/repository_service/**`或`vnext/repository_contracts/**`，即使只是
README或测试，现有digest算法也会改变`build_input_revision`或`source_tree_sha256`，必须重新封板
和执行container gate。

## 2. Common commands

受影响Python package在其目录执行：

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest -q
```

涉及Backend consumer时在`vnext/backend`执行同组命令。涉及Rust/canonical owner时执行：

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-targets --all-features
cargo build --workspace --release
```

不涉及Rust/canonical代码的P2 round只需全文确认未触碰相关路径，不机械运行Rust gate。
Container round统一以`docker compose -f vnext/deploy/compose.yaml config`开始，再执行本轮
明确的build/up/smoke/down；project name必须唯一，结束用trap清除container/network/
volume。网络下载失败必须记录原命令和错误并保持round uncommitted或明确no-go。

按§1.1延期container gate时，P2功能门禁的整仓入口为：

```bash
./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
```

当前被延期的实际Docker nodeid只有
`tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay`。
该命令仍会运行静态Dockerfile/Compose断言、build script/harness单测以及真实Dolt测试。若R5
新增实际启动Docker/Compose的测试，必须把精确path/nodeid加入handoff inventory并从功能门禁
明确排除；不得用宽泛marker表达式顺带漏掉非container测试。P2-R6最终门禁必须运行无
`--ignore`的`./vnext/scripts/run-tests.sh`并逐项执行inventory，届时本临时排除失效。

## 3. P2-R1 — Runtime and provider feasibility

Owning contract：
[P2-R1 Runtime and Provider Feasibility](p2-r1-runtime-provider-feasibility.md)。

Allowed：Repository Service private settings/layout/lock/process/provider/probe、test
fixtures、matrix runner、measurement records、target container probe。禁止HTTP业务route、
control DB、production operation/client与长期durable data。

Suggested green commits：

1. `feat(repository): add durable layout and process probes`
2. `test(repository): measure and select Dolt provider`
3. `docs(repository): record P2-R1 feasibility handoff`

Required gate：两candidate共享workflow；W0/W1/W2/W3 matrix；zero skip/xfail；selected
candidate通过全部hard gate；service package四命令；container/volume smoke；probe runtime
清理；`git diff --check`。报告exact Dolt/image/filesystem/workload/raw samples、selection、
limitations与`P2-R1 exit=go|no-go`。只有go允许进入R2。

## 4. P2-R2 — Service shell, auth and control lifecycle

Prerequisite：P2-R1 go handoff。完整读取Repository contract §§2–6、§11、§14.1及selected
provider decision。

Allowed：contracts shared DTO/enums/errors；FastAPI composition/lifecycle；settings；bearer；
healthz/readyz；request ID/error mapping；control DB migration/open/close；selected provider
capability check与subprocess shutdown/reap。禁止注册任何stub业务route；禁止创建import
worker pool（worker lifecycle属R4）；真实`/v1/` OpenAPI从R3首个业务route开始。

Suggested green commits：

1. `feat(repository): activate v1 contracts and service shell`
2. `feat(repository): add auth readiness and control lifecycle`
3. `test(repository): close service shell integration`

Required gate：contracts/service四命令；health/ready OpenAPI、status/error assertions；
missing/invalid/valid token；health/ready visibility；root lock contention；DB migration/newer
version failure；secret/log redaction；provider start/stop/reap；compose config/build/health
smoke；旧stub/v2/compat route搜索。Exit：真实shell ready但create/upload/import/read effect
仍未声称完成。

## 5. P2-R3 — Synchronous create and upload

Prerequisite：P2-R2 handoff。完整读取Repository contract §§7–9、§11–12、§14.1。

Allowed：create/upload DTO/route/application/ports/adapters与首个真实`/v1/` OpenAPI；
SQLite minimal ledger；Dolt create；bounded raw upload；artifact lifecycle/admission；
Remote client中仅create/upload所需部分。禁止async import worker、verification与
commit-pinned reads。

Suggested green commits：

1. `feat(repository): add crash-safe repository creation`
2. `feat(repository): add bounded artifact upload`
3. `test(repository): close synchronous mutation recovery`

Required gate：contracts/client/service四命令；same/different-key fingerprint；原201/body
重放；create/upload每个PENDING fault point和restart reconciliation；DB/filesystem双条件
visibility；raw length/SHA/media/compressed-size/disk boundary；nonrewindable client behavior；
真实HTTP + selected Dolt integration；compose smoke和无orphan resource。Exit：可取得真实
RepositoryId/initial CommitId/ArtifactRef。

## 6. P2-R4 — Async Versioned import

Prerequisite：P2-R3 handoff。完整读取Repository contract §§9–12、External Effect contract
及Canonical Storage §6。

R4详细内部设计、十阶段green boundary和逐阶段实现提示词见
[P2-R4 Async Versioned Import Detailed Implementation Design](p2-r4-async-versioned-import-implementation-design.md)
与
[P2-R4 Async Versioned Import Staged Execution Plan](p2-r4-async-versioned-import-execution-plan.md)。
两文档从属于本checklist和owning contracts，不改变本节required gate。

Allowed：import DTO/route、durable queue/worker、private ref、marker、mandatory commit CAS、
verification/type policies、operation polling、startup reconciliation、private admin CLI。
禁止read public routes/client纵切、table/schema CAS、LWW/force和business digest。

Suggested green commits：

1. `feat(repository): add durable Versioned import queue`
2. `feat(repository): publish verified imports with commit CAS`
3. `feat(repository): add import recovery and admin inspection`
4. `test(repository): close Versioned import failure matrix`

Required gate：contracts/service四命令；QUEUED/RUNNING/SUCCEEDED/FAILED persistence；
same-key原202/operation replay；streaming extraction entry/single/total expanded limits；
NONE/STRUCTURAL/FULL_SCAN矩阵；REJECT/STRINGIFY矩阵；
expected parent与second main CAS；verification failure保持main；private ref cleanup；commit前
crash、commit后response loss、normal terminal failure无hidden retry、legacy RUNNING一次
replay、manual ambiguity保留artifact/occupancy；CLI stopped-service/root-lock/audit/negative
actions；真实Dolt integration与compose restart smoke。

## 7. P2-R5 — Commit-pinned read, client and fixture consumer

Prerequisite：P2-R4 handoff。完整读取Repository contract §§13、17及DX handoff。
冻结选择、green stage边界和逐阶段命令见
[P2-R5 Commit-pinned Read Staged Execution Plan](p2-r5-commit-pinned-read-execution-plan.md)；
本节继续拥有跨round required gate和container延期规则，不复制该执行文档的阶段细节。

Allowed：resolve/catalog/row routes；exact SQL/Arrow mapping；bounded Arrow IPC stream；
Remote client全部V1 surface；Backend-independent contract-owned fixture consumer。禁止
Phase 3 capability、业务Submit policy、ordering guarantee、diff/export和LATEST read。

R5开始时必须先复核并处置以下从R4结束后静态评审带入的read-path事项，再形成R5
allowed paths、实现计划和首个green commit；本段只登记问题，不预先选定具体实现。不得因
R4 handoff已经通过、既有测试为green或准备直接注册public route而静默遗漏：

- `arrow_mapping.py`的SQL type到Arrow type映射位于逐cell热路径，且当前重复构造integer
  mapping、执行temporal/decimal/bit/character解析。实施计划必须在bounded cache、模块级
  immutable常量和table-level预编译之间作出有证据的选择；禁止引入由caller-controlled
  SQL type spelling驱动的无界process-lifetime cache，也不得暴露可被调用方修改的共享
  metadata。
- Candidate A和Candidate B row stream当前先逐row调用`normalize_rows()`用于payload/batch
  边界计算，随后`record_batch()`再次归一化同一批值。实施计划必须定义raw rows与
  already-normalized rows的内部边界，证明每个cell只转换一次，同时保留既有public/helper
  调用的校验语义、`SqlValueConversionError`列归属和bounded batch accounting。
- FULL_SCAN的batch contract当前按batch、按column重复计算Arrow type/metadata。实施计划
  必须讨论table-level expected Arrow schema预计算或与前述bounded mapping复用，并保持每批
  field name/type/nullability/metadata的完整比较。
- `CandidateAImportProvider.read_catalog()`与`read_type_catalog()`重复candidate parent解析。
  R5触碰catalog path时必须明确选择抽取共享的严格parent解析，或记录继续保留重复的理由；
  不得顺手改变parent、revision pinning或错误映射语义。
- 上述hot-path改动完成后，R5必须重新记录mapping/stream真实性与性能证据，并明确处置
  P2-R1 v8的`production_retest_required`：旧benchmark不得自动覆盖修改后的代码；若R5不
  承担完整production retest，必须把exact owner、剩余命令和最迟关闭gate显式交给R6。

R5实施计划至少要给出选择方案、缓存/生命周期边界、失败语义、定向回归、避免逐cell重复
转换的可观察断言，以及time-to-first-batch和bounded-memory验证方法。不得只以脆弱的单次
wall-clock阈值代替call-count、schema和真实stream证据。

Suggested green commits：

1. `feat(repository): add commit-pinned catalog and Arrow stream`
2. `feat(repository): complete remote Repository client`
3. `test(repository): add Versioned fixture-consumer e2e`

Required gate：contracts/client/service四命令；known SQL family mapping与unknown
REJECT/STRINGIFY metadata；NULL、decimal/temporal/unsigned/binary边界；bounded batches、
time-to-first-batch、cancel/disconnect cleanup；old/new commit immutability；unordered contract；
client GET bounded retries、mutation same-key retries、nonrewindable upload；真实HTTP
`create -> upload -> import -> poll -> resolve -> catalog -> stream`；Fixture consumer不得
import Backend/Phase 3代码。若未触发§1.1的提前条件，本轮以§2的P2功能门禁代替重新build和
compose内外client smoke，并在handoff明确记录container验证已延期；R5 exit只表示功能纵切
通过和`P2-R6 ready`，不表示production image或Phase 2完成。compose内外client smoke作为
deferred gate由R6最终候选执行。

**P2-R5 handoff（2026-08-12）**：

```yaml
p2_r5_exit: pass
p2_r6_ready: yes
validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
production_retest_required: yes
phase_2_complete: no
```

完整handoff见[P2-R5 Commit-pinned Read Staged Execution Plan — P2-R5-S7 final handoff — 2026-08-12](p2-r5-commit-pinned-read-execution-plan.md#p2-r5-s7-final-handoff--2026-08-12)。

## 8. P2-R6 — Operational closure

Prerequisite：P2-R5 handoff。完整读取Repository contract §§12、14–18及P2 design §§18–21。

Allowed：artifact cleanup scheduler、configurable concurrency/admission、structured
diagnostics、snapshot/restore/admin runbook、capacity test/report、final compose wiring与CI。
禁止public GC/backup/repair、metrics platform、RPO/RTO guarantee或P3设计实现。

R6开始时必须先复核并处置以下从R4结束后静态评审带入的operational/capacity事项，形成
单独的实施计划或逐项写明继续defer的owner、证据与最迟关闭点。不得以“尚未在线上出现”
作为唯一defer理由，也不得在Phase 2 exit记录中静默省略：

- `inspect_marker()`当前枚举全部branch head并为每个branch启动一次Dolt查询。计划必须用
  normal branch数量和保留MANUAL/private ref的增长场景测量退化，讨论single-query、bounded
  lookup或其他保持marker uniqueness/parent/ref证据的方案。
- import dispatcher空闲时约10 Hz执行queued候选查询；存在候选时还逐repository扫描FAILED
  rows并解析`error_json`寻找MANUAL barrier。计划必须区分idle query与candidate-only barrier
  成本，考虑operation history不受queue size 64限制的事实，并讨论sticky notification且无
  lost wakeup的唤醒模型、query/index形状及barrier durable表示，不能用放宽轮询后静默增加
  admission latency来换取通过。
- FULL_SCAN的4 GiB限制只约束package tar stream，不约束replay后Dolt table规模；当前
  `import_timeout_seconds`沿table stream逐次应用，也不是整个FULL_SCAN的global deadline。
  capacity计划必须在完成R5 mapping/单次归一化优化后，讨论whole-operation deadline、
  cancellation/cleanup、multi-table累计时长，并以10–100 MB和接近200 MB package及可产生
  更大table结果的受控样本记录边界。
- `_try_claim_one()`的in-flight检查与claim后的递增在多dispatcher模型下不是原子容量许可。
  当前single dispatcher不构成缺陷；若R6改变dispatcher/concurrency模型，必须先设计原子
  permit/claim边界。若仍保持single dispatcher，必须把该不变量和覆盖证据写入handoff。
- 清理确认无consumer的dead helper（当前包括`CandidateAImportProvider._refs_for_commit()`）
  及完成R4/R5后仍残留的局部死分支；删除前必须按本checklist纪律用`rg`确认全部consumer，
  且不得借清理改变marker、catalog、tar safety或public contract。
- 若R5未完成P2-R1 v8 production retest，R6必须执行其明确移交的exact命令并关闭
  `production_retest_required`，或保持Phase 2/production exit为no-go；普通R6 capacity样本
  不得在未证明矩阵等价时被称为该retest。

R6实施计划必须把上述事项与既有cleanup、capacity、snapshot/restore工作统一排序，逐项
给出acceptance evidence和gate归属；登记本身不授权提前建设metrics platform、通用scheduler
或多dispatcher架构。

Suggested green commits：

1. `feat(repository): close artifact and capacity operations`
2. `docs(repository): add snapshot recovery and capacity runbook`
3. `test(repository): close Phase 2 operational regression`

Required gate：三个Repository package和fixture consumer四命令；success cleanup、ordinary
TTL、RUNNING/manual retention；upload/import concurrency、per-repo writer、free-space+
headroom；10–100 MB代表样本和接近200 MB边界样本；whole-root quiescent snapshot/restore；
`git diff --check`；所有P2旧引用搜索。随后以最终candidate source tree执行一次完整容器
退出门禁：在保留cache的指定builder构建production image，记录build command、
`build_input_revision`、`source_tree_sha256`和remote image ID；通过`docker save | load`或等价
可审计流程传回gate host并校验remote/local image identity；要求
`image_matches_build_context=true`；运行无排除项的`./vnext/scripts/run-tests.sh`；执行R4
restart/replay、R5 compose内外client完整链路及fresh/restart/restored Compose e2e；清除并
确认无残留container/network/volume。所有§1.1 inventory、P2-R1 v8 production retest和
`production_retest_required`必须在此关闭，否则Phase 2 exit为no-go。Exit必须记录
P2-R1..R6 handoff SHA、最终image provenance、capacity limitations和Phase 2 complete。

## 9. Mandatory old-reference searches

每轮至少按受影响scope运行；R6对整个repository运行：

```bash
rg -n "NONE \\| STRUCTURAL \\| FULL|completed_verification_level|SnapshotManifest" .
rg -n "PREPARED/APPLIED/VERIFIED|UNKNOWN/APPLIED|FailureDescriptor|FAILED_FINAL" .
rg -n "LAST_WRITE_WINS|CHECK_EXPECTED|table.?CAS|schema.?CAS|StoreKind|CurrentTableStore" .
rg -n "repository_path|run_dir|multipart|LATEST_AT_START|/v2/|compatibility adapter" .
rg -n "Repository wire JSON/gRPC|before_readback_verified|after_readback_verified" .
```

搜索结果必须人工区分当前`FULL_SCAN`与旧`FULL`。Historical/superseded ADR可保留且
必须明确标记；current formal、code、test、CI和runbook不得依赖旧语义。删除前另以
symbol/path的精确`rg`列出consumer并在报告中保存结果。

## 10. Round report template

每轮实现者必须完整汇报：

```text
round:
start_sha:
commit_shas:
head_sha:
worktree_clean: yes/no

modified_scope:
deleted_scope:
explicit_non_goals_preserved:

green_commits:
validation_commands:
  - command:
    result: pass/fail + counts/key output
first_failures_and_fixes:
old_reference_searches:
consumer_search_before_delete:
runtime_cleanup:

known_limitations:
validated_code_sha:
container_validated_code_sha:
provenance_documentation_sha:
container_validation_deferred_to:
deferred_container_gate_nodeids:
round_exit: pass/no-go
next_round_ready: yes/no
next_entry:
```

不能用“主要通过”“仅网络失败”替代逐命令结果。除§1.1明确允许延期的container gate外，
未完成required Compose/Dolt smoke时不得提交该round最后的regression/handoff commit，
`next_round_ready`必须为`no`。使用延期规则时必须保留上述SHA和inventory字段；R6不得再次
延期最终container gate。

## 11. Phase 2 and Phase 3 boundary

P2-R6通过前，P3完整设计和实现均不开始。P2-R5的fixture consumer只验证Repository
public contract，不拥有业务schema、digest、Submit lifecycle或verification choice。
P2-R6 exit后下一项是“Phase 3完整设计”，不是直接实现P3；只有该设计单独收口后才
判定P3-R1 readiness。
