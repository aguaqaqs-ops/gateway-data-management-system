# P2-R1 Runtime and Provider Feasibility Contract

状态：Accepted

日期：2026-08-01

适用轮次：Phase 2 `P2-R1`

Owner：Backend vNext Architecture（provider选择、feasibility probe、P2-R1退出判断）

Runtime/layout owner：
[Repository Service Contract](../contracts/repository-service.md#141-durable-root-layout-and-publication)

Measurement owner：
[Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)

## 1. Goal and boundary

P2-R1只回答目标Linux容器与durable filesystem中，Repository Service能否以真实Dolt
完成create/import/read主机制，以及offline CLI或service-owned sql-server哪一条路径
进入P2-R2+。

本轮允许实现private adapter、probe、fixture、fault point和measurement runbook；不
注册HTTP route，不生成`/v1/` OpenAPI，不实现client、production create/upload/import
operation，不创建长期Repository durable data，也不进入P2-R2。

P2-R1结果只对实际记录的Dolt版本、container image、filesystem/storage class和
workload成立。目标部署条件改变时必须重跑相关probe，不得把一次开发机结果扩张为
通用保证。

## 2. Fixed target profile

首轮target profile固定为：

- `gateway-repository-service` Linux container；
- Dolt exact `2.1.11`；
- Python exact project toolchain；
- Docker named volume或等价single-node block-backed ext4/XFS filesystem；
- single ASGI owner、single durable-root `flock`；
- 同一mounted filesystem内完成staging、fsync和atomic rename；
- 4个跨Repository import workers用于容量投影，同Repository仍为单writer。

若执行环境只能提供network/shared writable filesystem，本轮不得以开发机local
filesystem结果判定ready，必须先把真实storage class纳入matrix。

## 3. Provider matrix

不得在测量前预选provider。两个候选使用相同Dolt binary、layout、fixture、operation
marker、catalog projection和Arrow batch contract。

### Candidate A — Offline CLI

- repository-scoped执行`dolt` CLI；
- `replay.sql`通过只读file descriptor/stdin流式输入，不把SQL放入argv或内存bytes；
- metadata query使用machine-readable result；
- row stream从child stdout增量读取、按catalog type转换并形成bounded Arrow
  RecordBatch；不得先收集完整stdout或全表rows。

### Candidate B — Service-owned sql-server

- 首先验证单个service-owned long-lived `dolt sql-server`，其`data_dir`指向
  `<data_root>/versioned/`；
- server只监听loopback或private Unix socket，由Repository Service lifecycle启动、
  readiness探测、终止和reap；不得作为共享root sidecar或外部第二owner；
- driver candidate固定为`mysql-connector-python==9.7.0`，使用async API和
  non-buffered cursor/fetchmany验证bounded streaming；
- checkout、replay、commit和ref检查保持在同一database session；
- 若long-lived server不能可靠发现atomic-published repository，才增加
  repository-scoped on-demand sql-server子候选；该子候选仍由Service监督，不改变
  durable-root owner。

Driver和server topology只是P2-R1 feasibility candidate，不进入contracts或public
wire。若Candidate B胜出，正式dependency由本轮lockfile精确固定；不得在失败后静默
替换成未测driver。

## 4. Dolt process boundary

CLI与sql-server共享一个private Runner/Supervisor boundary：

- Dolt binary使用settings提供的绝对路径，开始时验证exact version；
- 使用显式argv和`shell=False`，cwd必须解析到server-owned probe repository；
- environment采用allowlist；author和committer固定为
  `Gateway Repository Service <repository@gateway.invalid>`，不读取developer identity；
- child file descriptor最小化，root lock descriptor不得继承；
- child使用独立process group；timeout或cancellation先terminate group，短暂grace后
  kill，并始终wait/reap；
- metadata/server-start默认30秒timeout；P2-R1 import使用60分钟防挂死上限。该上限
  只控制probe，不自动成为production timeout；
- stdout/stderr按bytes设上限，只记录脱敏tail、exit code、duration和command kind；
  不记录replay SQL、token、完整environment或host path；
- sql-server必须在退出前停止接受新连接、关闭active cursor并完成graceful stop；
  graceful stop失败后才强制kill。

## 5. Fixed probe workflow

两个candidate必须逐项执行相同workflow：

1. 在disposable target-volume root上验证第一个进程取得root lock，第二个进程fail
   closed，owner退出后lock可重新取得；
2. 按owning contract创建component-first probe layout，并验证所有publication path
   具有相同`st_dev`；
3. 在`staging/versioned/<repository_key>.<nonce>/`初始化Dolt，创建fixed initial
   empty commit，确认默认ref为`main`并取得initial CommitId；
4. 完成staged tree fsync和atomic rename后重新打开
   `versioned/<repository_key>/`，确认initial commit/ref未变化；
5. 执行固定`replay.sql`并创建唯一operation-marker commit；marker使用commit message
   `gateway-versioned-import operation_id=<uuid>`，UUID由probe生成且不复用；
6. 确认新commit的parent是initial/expected CommitId，`main`指向新commit，并能从
   commit log按exact marker定位唯一commit；
7. committed table set、column order/type/nullability、primary key order和row count与
   manifest exact一致；
8. 分别以initial与new immutable CommitId读取，证明新commit可见且旧commit结果不变；
9. 以fixed RecordBatch upper bound完成Arrow stream，记录time-to-first-batch、总rows、
   throughput和peak RSS；不得全表materialize；
10. 在首批后取消stream，确认cursor/child及时关闭且下一次read不受污染；
11. 重启provider和probe owner后重新验证commit、ref、marker、catalog和pinned read；
12. 在repository rename前和rename后设置独立fault point。rename前失败不得出现visible
    repository；rename后必须能通过restart inspection判定完整成功或明确失败，不能
    出现被当作成功的半发布目录。

P2-R1只证明上述CAS所需primitive和expected-parent检查可行，不实现P2-R4 durable
operation、worker pool或完整recovery state machine。

## 6. Workloads and measurement

至少使用以下workload：

- `W0 correctness`：小型多表fixture，覆盖NULL、UTF-8、主要physical SQL type、单列与
  复合primary key；
- `W1 representative`：production-representative package，落在已确认10–100 MB范围，
  schema、row width、key/index和重复数据比例应接近当前consumer；
- `W2 boundary`：至少一个接近200 MB的package；
- `W3 incremental`：从W1 commit分别产生约1%和10%业务row变化的新commit。

优先使用脱敏真实样本；没有可共享数据时允许确定性synthetic fixture，但报告必须标记
synthetic及其与真实业务不可比项。P2-R1 measurement是provider/component feasibility，
不得冒充P2-R6真实HTTP consumer end-to-end结果。

每个candidate/workload先warm-up一次，再执行至少五次measured run；失败sample保留，
不得静默重跑替换。报告至少记录：

- dataset ID/revision、package size、table/row规模和change ratio；
- Dolt、driver、Python和image版本；
- CPU/memory、filesystem、volume backend和warm/cold条件；
- import/startup/first-batch/total-stream原始时长；
- rows/s、peak RSS与cancel cleanup时长；
- commit前后Dolt logical bytes、allocated bytes和temporary staging high-water；
- W3的1%/10%增量storage及相对W1 full commit的比例；
- correctness result、raw samples、summary calculation和known limitations。

sql-server background statistics必须关闭或单独隔离，避免把provider stats写入误算为
canonical Dolt增量。测量完成后停止provider并quiesce filesystem再读取storage数据。

## 7. Acceptance and selection

以下是两个candidate各自的hard gate：

- 第5节全部workflow通过，zero skip/xfail；
- W0、W1和W2均在60分钟probe safety limit内完成；
- W1/W2 stream的内存随RecordBatch bound保持有界，不随全表size线性累积；
- cancellation、restart、root-lock exclusion和rename fault point通过；
- W1按4 workers、70% target utilization和五次measured run中的最慢成功样本计算：

```text
projected_daily_capacity = 4 * 86400 * 0.70 / max_measured_import_seconds
```

  结果必须不低于已确认的1,000 imports/day极端日负载；该计算只是feasibility projection，
  不是SLO。
- W2必须完成并记录资源峰值，但不假设1,000次/天全部为200 MB边界package；
- W3必须产生可解释的增量storage记录。没有已确认disk budget时不建立虚假ratio gate，
  但无法解释的full-rewrite行为必须列为known limitation并阻止容量保证。

选择顺序固定为simplicity-first：

1. candidate未通过任一hard gate则淘汰；
2. Candidate A通过全部hard gate时选择offline CLI；
3. 只有Candidate A失败而Candidate B通过时选择sql-server + locked driver；
4. 两者均失败时P2-R1为`no-go`，不得进入P2-R2；
5. 两者均通过时仍选择Candidate A，Candidate B结果只作为未来真实read/concurrency
   压力触发后的备选记录。

选择CLI不允许删除sql-server原始测量结果；选择sql-server也必须记录CLI失败的具体
hard gate。不得以主观“更现代”或单次最快样本替代上述顺序。

## 8. Deliverables and verification

P2-R1必须提交：

- private layout/lock/fsync/process/provider probe code及其unit/integration tests；
- two-candidate matrix runner和相同fixture/workload入口；
- raw measurement result与简短Markdown decision；
- target container/volume smoke；
- ordinary repository-service lock、ruff、strict mypy和pytest结果；
- `git diff --check`和全文旧provider/layout引用搜索。

Measurement文件是普通工程记录，不生成evidence digest、baseline状态机、gate attempt或
exact-commit bundle。Probe产生的repository、container和volume必须清理，不得把
runtime data提交到Git。

P2-R1 exit只有两种：

- `go`：至少一个candidate通过hard gate，按第7节选定provider，记录限制并允许进入
  P2-R2；
- `no-go`：没有candidate通过，保持P2-R2未开始并回到具体失败机制讨论。

## 9. Non-goals

本轮不得：

- 创建`current/`、SQLite文件或Current marker；
- 建立generic dual-store/StoreKind adapter；
- 激活HTTP auth、health、business route或OpenAPI；
- 实现upload/import operation、worker pool、public CAS或manual recovery；
- 保留旧WP1 compatibility adapter、traceability/gate/evidence subsystem；
- 把probe timeout、synthetic benchmark或增量比例提升为public SLO/保证。

## 10. Related authority

- [Repository Service Contract](../contracts/repository-service.md)
- [Phase 2 Implementation Design and Delivery Plan](phase-2-implementation-design-and-delivery-plan.md)
- [Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)
- [ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
