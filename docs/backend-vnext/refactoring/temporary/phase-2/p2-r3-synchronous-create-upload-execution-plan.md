# P2-R3 Synchronous Create and Upload Execution Plan

状态：Draft / Active temporary execution coordinator

日期：2026-08-05

适用轮次：Phase 2 `P2-R3`

本文件只负责把正式 owner 拆成可执行 checkout、测试矩阵和 handoff。它不拥有 public
wire、持久状态或恢复语义；与正式文档冲突时，必须停止执行并以正式 owner 为准。

## 1. Authority

按以下顺序读取和处理冲突：

1. [Repository Service Contract §§7-9, 11-12, 14.1](../../formal/contracts/repository-service.md)
2. [P2 Versioned Repository Execution Checklist §5](../../formal/plans/p2-versioned-repository-execution-checklist.md)
3. [P2 Versioned Repository Implementation Design](../../formal/plans/p2-versioned-repository-implementation-design.md)
4. [P2-R1 v8 Formal Go Decision](../../formal/plans/p2-r1-v8-go-decision-2026-08-05.md)

本轮准备度审核还确认了四项实施决策：

- `CreateRepository`无JSON request body，只接收必需的`Idempotency-Key` header；
- Upload只接受`application/vnd.gateway.repository-import.v1+tar+zstd`，不支持gzip/gz，
  不按扩展名或内容嗅探；
- startup遇到`PENDING + no complete published effect`时，清理明确的staging，并在独立
  idempotency metadata中持久化内部`terminal-not-published` disposition；旧key不得重做
  effect，新业务尝试必须使用新key；
- upload admission参数由部署配置，caller不得覆盖；接受条件为
  `free_bytes - declared_size >= max(configured_min_free_bytes,
  total_volume_bytes * configured_min_free_fraction)`。

这些决定必须先进入contract tests，再进入production实现。若未来要改变其中任一项，先
修订正式owner或形成明确superseding decision，不在代码中静默漂移。

## 2. Entry snapshot

准备度审核时的仓库状态：

```text
R2 handoff SHA: f6a127ecb6429a2efb15313987a0653073cd4e09
branch: phase1/gate-ownership-repair
worktree: clean before temporary planning documents
selected provider: candidate_a_offline_cli
active business routes: none
import worker pool: deferred to P2-R4
```

基线包检查：

```text
repository_contracts: lock/ruff/mypy pass; pytest 15 passed
repository_client:    lock/ruff/mypy pass; pytest 4 passed
repository_service:   lock/ruff/mypy pass; pytest 215 passed, 1 skipped
```

正式实现不得直接假设`start_sha=f6a127e`。这些临时文档产生后，执行者必须从包含本文档的
clean commit开始，确认`f6a127e`是当前HEAD的ancestor，并记录实际`start_sha`。不得在
未提交的计划文档之上混入业务代码。

## 3. Scope

### 3.1 Allowed

- create/upload public DTO、header boundary、response model和首个真实`/v1/` OpenAPI；
- service application、ports、private adapters和selected Candidate A create路径；
- SQLite create/upload minimal effect ledger、idempotency metadata、migration和transaction；
- server-owned repository/artifact staging、no-replace publication和fault injection；
- bounded raw upload、size/SHA/media type校验和per-request disk admission；
- create/upload startup reconciliation、双条件visibility和readiness failure；
- Remote Client中仅create/upload所需的typed async facade、retry和source rewind规则；
- R3 contract/unit/integration/restart/HTTP/container tests及round handoff。

### 3.2 Explicit non-goals

- async import route、worker pool、operation polling、private import ref和commit CAS；
- package extraction、manifest/replay SQL validation、verification或Arrow mapping；
- resolve/catalog/row stream和Backend/Phase 3 consumer；
- gzip/gz、multipart、range resume、URL、host path、object storage或presigned URL；
- create/upload public Operation、generic effect journal、lease、fencing或background executor；
- artifact TTL scheduler、RUNNING/manual retention和完整concurrency/capacity closure；这些属于
  P2-R6；
- Candidate B、sql-server或provider重新选型；
- public delete/repair/GC/backup API、CurrentTableStore或compatibility adapter。

## 4. Cross-stage invariants

1. Distribution方向固定为`repository_contracts <- repository_client`和
   `repository_contracts <- repository_service`；client与service不得互相import。
2. Idempotency key只经header传输；只持久化SHA-256，不持久化或记录raw key。
3. Create fingerprint是versioned constant request shape；upload fingerprint至少覆盖media
   type、declared size和raw SHA。Repository scope属于idempotency scope，不靠路径字符串
   拼入fingerprint。
4. Filesystem effect前必须durably写入PENDING和server-owned resource ID；publication完成
   后才能durably写入SUCCEEDED。
5. 成功response必须持久化足够字段，使same key/same fingerprint返回原`201`和原body。
6. `terminal-not-published`是private idempotency disposition，不是public Operation，也不把
   effect ledger扩成通用FAILED状态机。
7. Repository或Artifact只有control DB SUCCEEDED与matching complete filesystem同时存在
   时可见。
8. Create和upload publication都使用同filesystem、flush/fsync、atomic no-replace rename、
   parent directory fsync；不得使用`os.replace`覆盖target。
9. Upload从request stream增量写盘并计算SHA-256，不得调用一次性body materialization，
   不得为nonrewindable client source做隐式spool。
10. Service启动完成reconciliation前不得ready；矛盾状态不得自动选DB或filesystem一侧
    覆盖另一侧。
11. Partial staging在能够明确证明未发布时即时清理。R3只保存TTL所需时间和生命周期
    metadata，不启动周期性TTL scheduler，也不删除已发布ordinary orphan artifact。
12. 现有Compose `repository-service`和`p2-r2` profile名称在R3保持不变，避免非contract
    部署命名 churn；P2-R6负责final compose wiring。若正式owner另有修订则以owner为准。

## 5. Delivery sequence

```text
S1 wire + persistence foundation
  -> S2 crash-safe CreateRepository vertical slice
  -> S3 bounded UploadArtifact vertical slice
  -> S4 startup reconciliation and mutation recovery closure
  -> S5 full gate, container smoke and P2-R3 handoff
```

五个checkout串行执行。S2和S3都会修改application composition、contracts/client surface和
shared persistence，不并行施工。每个阶段必须从上一阶段clean green commit开始。

| Stage | Outcome | Suggested commit |
| --- | --- | --- |
| S1 | wire/header决定、settings、migration、minimal ledger与idempotency store | `feat(repository): add synchronous mutation ledger` |
| S2 | 真实create route、Candidate A effect、client与integration tests | `feat(repository): add crash-safe repository creation` |
| S3 | 真实raw upload route、artifact publication、client与boundary tests | `feat(repository): add bounded artifact upload` |
| S4 | 全部fault/restart reconciliation、visibility/readiness与replay closure | `test(repository): close synchronous mutation recovery` |
| S5 | final package/container gate和handoff；无新feature | 无强制commit；只在修复或文档确有变化时提交 |

## 6. Stage S1 - Wire and persistence foundation

### Objective

在不注册业务route的前提下，先把R3 wire决定、配置、数据库migration和transactional
mutation primitives变成可执行contract tests。

### Required work

- 修正`gateway_repository_contracts.versioned`：JSON DTO不得携带idempotency key；create
  route无body；upload request不是JSON model。保留/收敛response和ArtifactRef模型。
- 为create/upload header值建立bounded validation；SHA只接受lowercase 64 hex；media type
  固定为已确认的tar+zstd value。
- 增加配置并校验：默认upload上限`256 MiB`、artifact TTL metadata默认`24h`；复用现有
  `min_free_disk_bytes=5 GiB`和`min_free_disk_fraction=0.10`。这些只来自deployment settings。
- 将control DB从当前空v1 migration向前升级，建立最小create/upload effect ledger与独立
  idempotency metadata。migration必须transactional、forward-only、可重复open，newer
  version继续fail closed。
- 提供transactional store API：claim/lookup fingerprint、分配resource ID、写PENDING、
  完成SUCCEEDED、保存/读取原response、记录terminal-not-published。
- 明确定义deterministic internal fingerprint编码和测试；禁止把raw key放入DB、exception、
  log或repr。
- 为并发same-key claim提供no-duplicate-effect语义；具体使用短事务、process-local lock或
  明确409均可，但不得让两个handler同时拥有同一effect。

### Stage gate

- contracts和service migration/store定向tests；
- same key/same fingerprint、same key/different fingerprint、kind/scope隔离；
- migration 0 -> current、1 -> current、current reopen、newer rejection和rollback；
- raw idempotency key absence scan；
- contracts/client/service的lock、ruff、mypy、pytest；
- OpenAPI仍只有`/healthz`和`/readyz`。

### Stop conditions

- 不为方便持久化把raw key或host path写入SQLite；
- 不提前注册create/upload stub route；
- 不增加import operation表、worker或R4状态。

## 7. Stage S2 - Crash-safe CreateRepository

### Objective

交付首个真实业务纵切：`POST /v1/repositories`、Candidate A staging create、原子publication、
持久成功重放和Remote Client create。

### Required work

- 建立application command/port与private filesystem/provider adapter；route不得直接编排
  SQLite、Dolt和fsync细节。
- Service生成UUID，filesystem key只使用lowercase UUID hex；不得接受display name或路径。
- 在PENDING之后创建`staging/versioned/<repository_key>.<nonce>/`，用selected offline CLI
  初始化Dolt、`main`和initial empty commit，取得opaque initial CommitId。
- 将R1 publication primitive提升或封装为production-owned adapter，移除“probe-only”误导，
  同时保持R1 probe行为和tests不回归。
- publication成功后写SUCCEEDED并保存完整`201` response；same key/same fingerprint重放
  原body，different fingerprint返回409。
- 注册真实route时同时接入bearer、SimpleError、request ID、OpenAPI和typed async client。
  Client在network/502/503类失败上使用同一key做bounded retry。
- 增加unit、application、真实Dolt integration和HTTP tests；mock不得替代selected Dolt
  create exit gate。

### Stage gate

- create happy path返回真实RepositoryId、`main`和initial CommitId；
- route无JSON body，缺少/非法Idempotency-Key失败；
- same-key replay、different fingerprint conflict、auth/error/request ID；
- DB/FS双条件visibility；no-replace和same-filesystem failure；
- client same-key retry；
- contracts/client/service四命令和`git diff --check`。

### Deferred to S4

本阶段必须留出fault injection seam，但完整crash/restart matrix在S4统一关闭。不得因此伪称
P2-R3 exit已通过。

## 8. Stage S3 - Bounded UploadArtifact

### Objective

交付`POST /v1/repositories/{repository_id}/artifacts`的raw streaming纵切、ArtifactRef
publication和Remote Client upload。

### Required work

- 只接收四个必需headers：`Content-Type`、`Content-Length`、`Idempotency-Key`、
  `X-Artifact-SHA256`；request body为raw bytes，不使用multipart。
- Content-Type只接受确认的tar+zstd media type；gzip/gz和其他类型返回415。
- 在写PENDING前执行repository visibility、declared size、configured max和disk admission。
  Admission使用上传后剩余空间公式，不接受caller override。
- Service分配repository-scoped ArtifactId；staging与ready位于
  `artifacts/<repository_key>/staging|ready`。
- 逐chunk写入staging file并增量计算size/SHA。断连、超限、short/long body或hash mismatch
  不发布，且只清理能够明确归属本次请求的partial staging。
- 完整close后fsync并no-replace rename到ready，再写SUCCEEDED和原`201` response。
- ArtifactRef只含artifact ID、media type、size和raw SHA；不得加入schema、digest、retention
  或host path。
- Client只对可rewind/reopen source自动完整重传；nonrewindable source失败后直接向caller
  暴露，不隐式spool。
- 保存created/updated lifecycle metadata，为R6 TTL scheduler提供输入；R3不启动scheduler。

### Stage gate

- raw 0/正常/边界/超限length，short/long stream，SHA mismatch，断连和nonrewindable source；
- exact media type与415；
- disk formula等号两侧、配置校验和PENDING前拒绝；
- same-key replay、different content conflict和repository scope隔离；
- DB/FS双条件visibility、atomic no-replace和无partial ready artifact；
- 真实HTTP/client tests；
- contracts/client/service四命令和`git diff --check`。

## 9. Stage S4 - Recovery closure

### Objective

把S2/S3的fault seams、startup reconciliation、terminal-not-published、readiness和response
loss收敛为完整同步mutation recovery gate。

### Startup order

```text
load/validate settings
  -> validate layout marker
  -> acquire durable-root lock
  -> migrate/open control DB
  -> verify selected provider
  -> reconcile create/upload ledgers and filesystem
  -> evaluate writable/disk/readiness
  -> accept traffic
```

### Required recovery rules

| Durable state | Filesystem evidence | Required action |
| --- | --- | --- |
| create PENDING | complete published Dolt repository with matching main/head | 补记SUCCEEDED并恢复原201 body |
| create PENDING | no complete published repository | 清理明确staging；记录terminal-not-published；旧key不重做 |
| create SUCCEEDED | matching complete repository | visible |
| create SUCCEEDED | missing/incomplete/mismatched repository | service不得ready；等待operator |
| upload PENDING | ready file size/SHA exact match | 补记SUCCEEDED并恢复原201 body |
| upload PENDING | no matching ready file | 清理明确partial staging；记录terminal-not-published；旧key不重做 |
| upload SUCCEEDED | ready file size/SHA exact match | visible |
| upload SUCCEEDED | missing或size/SHA mismatch | service不得ready；等待operator |

Reconciler不得重新执行Dolt create、不得伪造upload bytes、不得删除SUCCEEDED metadata或覆盖
矛盾filesystem。普通terminal-not-published不是public manual recovery Operation。

### Mandatory fault matrix

- create：PENDING后、staging创建后、Dolt init后、publication rename前、rename后/SUCCEEDED前、
  SUCCEEDED后/response前；
- upload：PENDING后、partial body、完整close后、rename前、rename后/SUCCEEDED前、
  SUCCEEDED后/response前；
- 每个fault均执行fresh process restart，断言DB、filesystem、visibility、replay和readiness；
- fault injection只通过private test seam，不进入public settings或wire。

### Stage gate

- 上表和fault matrix全部通过，zero xfail/required skip；
- response-loss create/upload返回原201/body；
- raw key、path和sensitive input不出现在log/error；
- client retry不产生duplicate effect；
- 三包四命令、`git diff --check`和受影响old-reference scan。

## 10. Stage S5 - Full exit and handoff

S5不增加feature，只允许修复R3 gate暴露的问题。

### Full gate

在三个Python package各自运行：

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest -q
```

此外必须运行：

- 真实HTTP + selected Candidate A create/upload integration；
- `docker compose -f vnext/deploy/compose.yaml config`；
- 唯一project name的repository-service build/up/auth/create/upload/restart/replay smoke；
- container/network/volume无非预期残留；
- `/openapi.json`只有health/readiness和两个已实现的`/v1/` route；
- 对production source、OpenAPI和deploy config做定向`rg`，确认无stub/v2/compat、gzip/gz、
  multipart/resume或import worker提前激活；计划文档和明确的负向测试命中必须逐项审阅，
  不得用机械zero-match替代语义判断；
- `git diff --check`和最终worktree clean。

外部registry/network失败不能报告pass。任一required test失败时不得提交最终handoff，
`next_round_ready`必须为`no`。

### Handoff format

```text
round: P2-R3
start_sha:
end_sha:
commits:
selected_provider: candidate_a_offline_cli
changed_paths:
wire_routes:
control_db_version:
verification:
fault_restart_matrix:
container_smoke:
reference_search:
known_limits:
worktree_clean:
round_exit: pass/no-go
next_round: P2-R4
next_round_ready: yes/no
```

Exit只表示可取得真实RepositoryId、initial CommitId和ArtifactRef，并且同步mutation recovery
通过。不得声称import、verification、read、TTL scheduler或Phase 2整体完成。

## 11. Stop and reopen conditions

出现以下任一情况时停止当前stage，不用局部补丁绕过：

- Candidate A exact version、provider command或Dolt initial commit/main行为与R1决定不一致；
- target filesystem无法提供同filesystem no-replace publication和directory fsync；
- minimal ledger无法在SQLite事务与filesystem barrier之间维持owner contract；
- FastAPI/http client无法在不buffer完整body的情况下满足upload boundary；
- 新需求要求gzip、multipart、object storage、shared writer或multi-node takeover；
- 正式owner之间出现无法按authority order消解的冲突。

普通类名、表名、模块切分、日志字段和test fixture组织不是reopen理由，由执行者按现有代码
风格保守选择。
