# P2-R3 Staged Implementation Task Prompts

状态：Draft / Active temporary execution prompts

日期：2026-08-05

适用：按独立对话或独立checkout串行执行P2-R3 S1-S5。

这些提示词是执行辅助，不是contract。每次使用前都必须读取
[P2-R3 Synchronous Create and Upload Execution Plan](p2-r3-synchronous-create-upload-execution-plan.md)
及其中列出的正式owner。上一阶段handoff与当前仓库事实优先于提示词中的历史快照。

## 使用规则

- 一次只使用一个stage prompt，不把S1-S5压进同一实现对话。
- 每个stage开始时记录实际`start_sha`和clean status；确认R2 handoff `f6a127e`是ancestor。
- 如果计划文档仍未提交，先形成docs-only clean baseline，不在dirty worktree上开始业务代码。
- 只在本stage gate green后创建建议commit；不得amend上一stage handoff。
- 遇到用户已有改动时保留并协同，不得reset/checkout覆盖。
- stage结束必须报告命令与结果、commit SHA、known limits和下一stage readiness。

## Prompt S1 - Wire and persistence foundation

```text
你在 /root/gateway-data-management-system 仓库执行 P2-R3 S1。

目标：实现同步 create/upload 的 wire/header 决定、配置、SQLite migration、minimal effect
ledger 和 idempotency store；本阶段不得注册任何 /v1/ 业务 route。

开始前：
1. 读取 docs/backend-vnext/refactoring/temporary/phase-2/
   p2-r3-synchronous-create-upload-execution-plan.md 的 S1 与 cross-stage invariants。
2. 完整读取正式 owner：Repository Service Contract §§7-9、§11-12、§14.1，P2 Execution
   Checklist §5，P2 Implementation Design 的 authority/create/upload 章节，P2-R1 v8 go decision。
3. 运行 git status、git rev-parse HEAD，确认 worktree clean 且 f6a127e 是 ancestor；记录实际
   start_sha。检查是否有用户已有改动并保留。

已确认且不得重问的决定：
- Create 无 JSON body，Idempotency-Key 只在 header。
- Upload 为 raw body + Content-Type/Content-Length/Idempotency-Key/X-Artifact-SHA256。
- 唯一 media type 是 application/vnd.gateway.repository-import.v1+tar+zstd；不支持 gzip/gz。
- effect ledger 只表达 PENDING/SUCCEEDED；terminal-not-published 保存在独立 idempotency
  metadata，旧 key 不重做。
- disk/upload/TTL 默认值由 deployment settings 配置，caller 不得覆盖。

实现：
- 修正 repository_contracts 的 create/upload wire DTO，使 JSON model 不携带 idempotency key，
  并用 tests 锁定 header/raw-body boundary 和 response/ArtifactRef shape。
- 增加并严格校验 max_upload_bytes=256 MiB、artifact_ttl_seconds=24h；保留并复用
  min_free_disk_bytes=5 GiB、min_free_disk_fraction=0.10。
- 将 control DB 做 forward-only transactional migration，增加最小 create/upload effect ledger
  与独立 idempotency metadata；newer version 继续 fail closed。
- 实现 transactional claim/lookup/PENDING/SUCCEEDED/original-response/terminal-not-published API。
- idempotency scope 固定为 mutation kind + nullable repository scope + SHA-256(raw key)；DB、log、
  repr、exception 不得出现 raw key。Create fingerprint 为 versioned constant；upload fingerprint
  覆盖 media type、declared size、raw SHA。
- 并发 same-key claim 不得产生 duplicate owner/effect。
- 保持 production OpenAPI 只有 /healthz 和 /readyz。

测试：
- migration 0/1/current/newer/rollback/reopen；
- same key same/different fingerprint、kind/scope 隔离、stored response；
- raw key absence 和 settings boundary；
- contracts/client/service 各自 uv lock --check、ruff、mypy、pytest；
- git diff --check。

非目标：route、Dolt create、filesystem publication、upload body、startup reconciliation、import
worker、Candidate B、gzip、multipart。

所有 gate green 后创建建议 commit：
feat(repository): add synchronous mutation ledger

结束报告：start_sha、commit SHA、schema/user_version、changed paths、全部命令与结果、known
limits、S2 ready yes/no。不要开始 S2。
```

## Prompt S2 - Crash-safe CreateRepository

```text
你在 /root/gateway-data-management-system 仓库执行 P2-R3 S2。S1 handoff 必须已提交且
worktree clean。

目标：交付 POST /v1/repositories 的真实 Candidate A create 纵切，同时交付 typed async
client create 和真实 HTTP/Dolt integration tests。

开始前读取 P2-R3 execution plan 的 S2/cross-stage invariants，以及正式 Repository Contract
§7、§11、§14.1、Execution Checklist §5、selected provider decision。记录 start_sha，核对 S1
handoff、control DB version 和测试结果。

实现：
- 建立清晰的 application command/port/private adapter 边界；HTTP route 不直接编排 SQLite、
  subprocess、fsync 或 rename。
- POST /v1/repositories 无 body，只要求 Idempotency-Key header；使用现有 bearer、request ID、
  SimpleError 和 readiness boundary。
- 在 filesystem effect 前 claim idempotency、分配 UUID、写 PENDING。路径只能使用 UUID hex。
- 在 server-owned staging 用 selected Candidate A offline CLI 初始化 Dolt、main 和 initial empty
  commit，取得 opaque CommitId；子进程必须受现有 timeout/output/shutdown/reap boundary 约束。
- 按 contract barrier fsync staged tree并 atomic no-replace publication，随后写 SUCCEEDED 和完整
  201 response。
- same key/same fingerprint 返回原 201/body；mismatch 返回 409；DB+filesystem 双条件才可见。
- 把 R1 publication primitive 提升/封装为 production-owned adapter，保持 R1 probe tests green，
  不复制第二套 rename/fsync 实现。
- route、真实behavior、client和integration test必须同阶段出现。Client对允许的network/502/503
  使用同一key bounded retry。
- 增加private fault seams供S4使用，但本阶段不伪称完整restart closure。

测试至少覆盖：
- happy path真实RepositoryId/main/initial CommitId；
- no body、header validation、auth、request ID、SimpleError、OpenAPI；
- same-key replay、conflict、no-replace、same-filesystem和DB/FS visibility；
- client same-key retry；
- selected Dolt integration，不以mock替代；
- contracts/client/service四命令及git diff --check。

非目标：upload、startup full reconciliation、import/operation/read、TTL scheduler、Candidate B。

所有 gate green 后创建建议 commit：
feat(repository): add crash-safe repository creation

结束报告：start/end SHA、commit、route/OpenAPI、Dolt命令边界、测试结果、deferred fault points、
S3 ready yes/no。不要开始 S3。
```

## Prompt S3 - Bounded UploadArtifact

```text
你在 /root/gateway-data-management-system 仓库执行 P2-R3 S3。S2 handoff 必须已提交且
worktree clean。

目标：交付 POST /v1/repositories/{repository_id}/artifacts 的 bounded raw streaming、
ArtifactRef publication、typed async client upload和boundary tests。

开始前读取 P2-R3 execution plan 的 S3/cross-stage invariants，以及 Repository Contract §8-9、
§11-12、§14.1和Execution Checklist §5。记录start_sha并核对S2真实create仍green。

实现：
- route只接收raw body和四个必需headers：Content-Type、Content-Length、Idempotency-Key、
  X-Artifact-SHA256；禁止multipart和JSON request DTO。
- Content-Type exact接受 application/vnd.gateway.repository-import.v1+tar+zstd；gzip/gz及其他
  类型返回415，不做扩展名或magic-byte嗅探。
- effect前确认repository以DB+filesystem双条件可见，并校验declared size、configured
  max_upload_bytes及disk admission：
  free_bytes - declared_size >= max(min_free_disk_bytes, total_bytes * min_free_disk_fraction)。
- claim idempotency、分配repository-scoped ArtifactId、写PENDING后，逐chunk写入专属staging
  file并增量计算size/SHA。不得一次性materialize完整body。
- short/long/超限/hash mismatch/disconnect不发布ready artifact，只清理本request明确拥有的
  partial staging。
- 完整close后fsync并atomic no-replace rename到ready，再写SUCCEEDED和原201 response。
- ArtifactRef严格只有artifact_id/media_type/size_bytes/raw_sha256；保存TTL所需created/updated
  metadata但不启动scheduler。
- route、真实behavior、client和integration test同阶段出现。Client只对rewind/reopen source
  自动完整重传；nonrewindable source不得隐式spool。
- 增加private fault seams供S4使用。

测试至少覆盖：
- raw body正常、0、接近上限、等于/超过上限、short/long、SHA mismatch、disconnect；
- media type exact/415、headers、404 repository、auth和SimpleError；
- disk公式等号两侧、配置非法、拒绝发生在PENDING/effect之前；
- same-key replay、different content conflict、repository scope隔离；
- atomic ready publication、无partial ready、DB/FS visibility；
- client rewindable retry与nonrewindable failure；
- contracts/client/service四命令及git diff --check。

非目标：解压/manifest验证、gzip、import worker、TTL scheduler、full concurrency closure、read。

所有 gate green 后创建建议 commit：
feat(repository): add bounded artifact upload

结束报告：start/end SHA、commit、streaming/admission证据、boundary counts、测试结果、deferred
fault points、S4 ready yes/no。不要开始 S4。
```

## Prompt S4 - Startup reconciliation and recovery closure

```text
你在 /root/gateway-data-management-system 仓库执行 P2-R3 S4。S3 handoff 必须已提交且
worktree clean。

目标：关闭create/upload全部PENDING fault point、startup reconciliation、双条件visibility、
readiness failure、terminal-not-published和response-loss replay。

开始前完整读取P2-R3 execution plan的S4 recovery table/fault matrix，以及Repository Contract
§7-8、§11、§14.1和Execution Checklist §5。记录start_sha，核对S1-S3 commits与gates。

实现：
- 将startup顺序固定为settings/layout/root lock/control DB/provider/reconcile/readiness/intake。
  reconciliation结束前不得ready或接受业务traffic。
- create PENDING + complete matching published repository：读取main/head并补记SUCCEEDED，恢复原
  201 body；无complete target则清理明确staging、记录terminal-not-published，旧key不重做。
- upload PENDING + ready size/SHA exact match：补记SUCCEEDED并恢复原201 body；无matching ready
  则清理明确partial staging、记录terminal-not-published，旧key不重做。
- SUCCEEDED create目录缺失/不完整，或SUCCEEDED artifact缺失/size/SHA mismatch：service保持
  not ready，保留证据等待operator；不得重建、覆盖、删除metadata或选择一侧为真。
- terminal-not-published不是publicOperation；新的业务attempt必须使用新key。
- same key successful replay始终返回原201/body；client retry不得duplicate effect。
- fault injection保持private test seam，不进入settings、wire或production OpenAPI。

逐一实现fresh-process restart测试：
- create：PENDING后、staging后、Dolt init后、rename前、rename后/SUCCEEDED前、
  SUCCEEDED后/response前；
- upload：PENDING后、partial body、完整close后、rename前、rename后/SUCCEEDED前、
  SUCCEEDED后/response前。

每个case断言SQLite、filesystem、visibility、readiness、replay、staging cleanup和无duplicate
effect。Required case不得skip/xfail。

同时检查日志/error不含raw key、token、host path或敏感body。运行contracts/client/service
四命令、git diff --check和受影响scope old-reference search。

非目标：import recovery、manual admin CLI、TTL scheduler、R6 capacity closure、任何P3能力。

所有 gate green 后创建建议 commit：
test(repository): close synchronous mutation recovery

结束报告：start/end SHA、commit、fault matrix逐项结果、readiness cases、全部gate、known limits、
S5 ready yes/no。不要开始 S5。
```

## Prompt S5 - Full P2-R3 exit and handoff

```text
你在 /root/gateway-data-management-system 仓库执行 P2-R3 S5 final gate。S4 handoff必须已提交，
worktree clean。S5不增加feature，只修复R3 required gate暴露的问题。

开始前读取P2-R3 execution plan的S5、P2 Execution Checklist §1/§2/§5/round report template和
全部formal owners。记录final-gate start_sha并核对S1-S4 commits。

执行并报告：
1. repository_contracts、repository_client、repository_service各自：
   uv lock --check
   uv run ruff check .
   uv run mypy
   uv run pytest -q
2. 真实HTTP + selected Candidate A create/upload integration和完整fault/restart matrix。
3. docker compose -f vnext/deploy/compose.yaml config。
4. 使用唯一project name执行repository-service build/up/auth/create/upload/restart/replay smoke；
   使用独立test volume，结束确认container/network/volume无非预期残留。
5. OpenAPI只含/healthz、/readyz、POST /v1/repositories、
   POST /v1/repositories/{repository_id}/artifacts。
6. 对production source、OpenAPI和deploy config做定向rg，确认无stub/v2/compat、gzip/gz、
   multipart/resume、Candidate B默认启用、import worker或read route提前激活。计划文档与明确
   的负向测试命中应逐项审阅，不要求机械zero-match。
7. git diff --check、git status和worktree clean。

registry/network/daemon等外部失败不得标pass。任何required gate失败时先在R3 scope修复并重跑；
无法修复则round_exit=no-go、next_round_ready=no，不创建虚假handoff。

最终输出严格包含：
round: P2-R3
start_sha:
end_sha:
commits:
selected_provider: candidate_a_offline_cli
changed_paths:
wire_routes:
control_db_version:
verification: 每条命令的pass/fail和counts
fault_restart_matrix:
container_smoke:
reference_search:
known_limits:
worktree_clean:
round_exit: pass/no-go
next_round: P2-R4
next_round_ready: yes/no

只有全部gate通过才可报告：可取得真实RepositoryId、initial CommitId、ArtifactRef，P2-R3
exit=pass，P2-R4 ready=yes。不得声称import、read、TTL scheduler或Phase 2 complete。
```
