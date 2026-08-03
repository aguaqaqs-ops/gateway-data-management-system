# P2-R1 Audit Correction

状态：薄复审通过，formal exit 保持 `no-go`；未选择 provider，未进入 P2-R2

本次审计修复的 authority 版本为 `p2-r1-audit-corrective-v5`。它覆盖
sample-cgroup identity、真实 target-container delegation、baseline-adjusted
plateau、connector fetch bound、durable raw publication 和 provenance verification。

本文件记录审核意见对应的代码和方法学修复范围。它不是新的 provider decision，
也不覆盖 2026-08-02 历史 raw measurements、summary 或 decision report。

## Historical evidence status

此前 60-record matrix 的 bounded-stream evidence 标记为
`measurement-method-invalid/inconclusive`：W1/W2 不是同shape scaling workload，
CSV framing 把 NULL、空字符串和 literal `"NULL"` 折叠，catalog 使用了
revision-unaware `information_schema`，并且 per-workflow RSS/cancellation 口径不足以
支持原 hard gate。因此历史文件不能继续证明 Candidate A 或 B 已被有效 bounded gate
淘汰。

## Corrective implementation

本轮 v5 追加修复无效 slice delegation、raw/W3即时持久化不一致、zero-delta规则、
memory.stat baseline/final/delta、UTF-8 decoded byte计算和clean-source provenance。

- method version 固定为 `p2-r1-audit-corrective-v5`；新增 S10/S40/S100 same-shape
  scaling、row bound 256/1024、4 MiB byte bound和first/middle/final 10% plateau；
- bounded gate 统一使用所有memory subjects的 `max/min <= 1.5`，coverage缺失为
  `inconclusive`，W2仅作wide-row boundary，W3仅作storage observation；
- Candidate A 使用null-bit/value pair tagged CSV，binary/BIT使用HEX；W0和代表性
  workload row oracle覆盖NULL、空值、literal `NULL`、UTF-8和binary；
- 两个provider通过`dolt_schema_diff(base_commit,target_commit)`取得commit-pinned
  DDL catalog，保留initial/base/new pinned read和schema mutation regression；
- ProcessStream使用selector/non-blocking chunk parser，超时和超长未换行记录均
  fail closed；Candidate B取消不drain全表，未读cursor触发connector session reset；
- 移除`RUSAGE_CHILDREN.ru_maxrss`作为per-workflow peak，保留process-tree、Arrow
  pool和cgroup scope字段；publication增加目录fsync和Linux no-replace rename；
- Dockerfile及dependency-base增加Dolt、uv wheel、lockfile、精确版本和venv/package
  consistency校验。
- `run_matrix()`是唯一formal runner：联合收集60条常规记录与72条scaling记录，只有
  完整、无重复、无失败的coverage才计算mechanical gates；诊断subset和
  `run_scaling_diagnostic()`不能产生formal `go`。artifact默认fail-closed且不覆盖历史
  文件。
- target container由安装式`gateway-p2r1-runner@.service`承载；`Delegate=yes`只在service，
  `.slice`不设置Delegate。launcher通过实际`ControlGroup`动态解析slice路径，gate住container
  后授权精确container cgroup，再释放target；sampler为四类
  memory subject分别记录三个plateau window。cgroup无法隔离、任一subject/window缺失
  时bounded状态为`inconclusive`。
- W3 storage读取移到provider/server关闭、cursor/connection close、process reap和
  filesystem quiesce之后；4 MiB允许单个不可拆分oversized row独立成batch并显式标记。
- target Compose改为宿主预委托subtree的`cgroup: host` read-write bind mount；formal
  runner在fixture前执行真实child cgroup preflight，并以fork/exec新worker隔离每个sample，
  不再迁移长期父runner。cgroup peak FD持续到stream结束，window evidence使用
  `memory.current`窗口峰值。
- formal selection恢复为动态simplicity-first；bounded ratio先按scale聚合五次measured
  的保守peak，再计算scale间ratio。warmup correctness失败、执行错误和W3缺失/零/负或
  未quiesce storage evidence均阻止hard gate。
- raw metadata补充实际Dolt/connector/PyArrow版本、image digest、build revision、cache
  condition及warmup/warm条件；Candidate B使用`fetchmany(32)`并记录最大fetched payload。

### 7.1 Audit corrective constraints

- 每个sample必须先创建child cgroup，再把该child path写入worker settings；provider
  tracker root、worker PID和child `cgroup.procs`必须一致，父supervisor不得进入child。
- `cgroup: host`不能单独证明delegation。正式 target 必须通过
  `gateway-p2r1-runner@.service`、其专用`gateway-p2r1.slice`、Compose `cgroup_parent`
  和宿主 launcher 启动，并验证容器 supervisor、delegated root和共同ancestor；静态
  bind失败时保持fail closed，`.slice`本身不得设置`Delegate=yes`。
- query执行前保存workflow、provider、Arrow和cgroup四类baseline；raw同时保存absolute
  与delta plateau，bounded ratio只使用`max(0, current-baseline)`的delta。cgroup raw
  还保存`memory.stat`的anon/file及stream-level peak；累计peak不得伪装成window evidence。
- Candidate B的`connector_fetch_row_bound=32`是配置上限，不是无条件fetch size。实际
  fetch size按catalog可证明最大row width计算，无法证明上界的类型使用单行fetch；普通
  fetch payload必须不超过4 MiB，唯一oversized row必须单独fetch并标记。
- formal runner在preflight后以`open("x")`预留raw，并在每条record后flush/fsync；异常
  保留已写records和`incomplete/no-go` terminal status。只有完整coverage才发布summary/report。
- worker result必须临时文件fsync后atomic rename，父supervisor要求正常零退出；partial
  或异常result只能成为失败sample。
- formal provenance必须是Docker实际immutable image ID与image labels交叉验证的digest、
  clean source revision/tree digest、lock SHA、精确依赖版本和cache condition；manifest必须
  只读挂载并由matrix校验，未经过launcher验证的自由CLI字符串不得产生formal `go`。
- W3 record必须在首次raw fsync前完成W1 baseline注释；最终summary从重新读取的raw独立重算，
  并与内存records逐字段一致，否则追加`incomplete/no-go` terminal status。
- delta plateau允许`>=0`；三个scale全零时ratio为`1.0`，零/正混合时为`inconclusive`，
  不使用epsilon。

### 7.2 Delegated target topology and project isolation

本轮审核修复将正式 target 的 cgroup 选择固定为 per-run slice 下、由 launcher 生成的三层拓扑：

```text
container delegated root (empty, memory+pids enabled)
├── supervisor (target gate/matrix PID)
└── samples (empty, memory+pids enabled)
    └── gateway-p2r1-<sample> (isolated worker PID)
```

launcher 把合法的 per-run slice unit name 用作 Docker `cgroup_parent`，并读取 slice/service
的实际 ControlGroup 作为 ancestry evidence；它不会把 service ControlGroup filesystem
路径传给 Docker，也不会向含有 target PID 的父 slice 或 container root 提前写
`cgroup.subtree_control`。container
启动后先创建 `supervisor`/`samples`，把 container root 的所有直接 PID 迁移到
`supervisor`，确认 root 为空，再启用 root 和空 `samples` 的 `memory`/`pids` controller。
随后 launcher 写入只读 `cgroup-layout.json`，target gate 最后才释放。formal
`run_matrix()` 读取该 layout，验证自身位于 `supervisor`，并把 `samples` 固定为
sample root；`resolve_current_cgroup()` 仅保留给 diagnostic，不得覆盖 formal root。

每次 launcher 运行生成并校验唯一 `gateway-p2r1-<run-id>` Compose project。`up`、`ps`、
`logs`、`down` 和失败清理全部显式携带该 project，禁止 `down --remove-orphans` 作用于
共享 Compose project。清理必须确认 container cgroup、`supervisor`、`samples` 和 sample
child 均消失；残留即 cleanup failure。target停止并reap后才允许`docker cp`导出artifact；
只有raw、summary、report三份artifact完成完整性和no-replace publication后才允许
`down -v`。异常target或导出失败只执行不带`-v`的runtime cleanup并保留source volume。

## Verification record

本轮本地验证结果：

- `uv lock --check`：通过；
- Ruff：通过；
- strict mypy：通过；
- pytest：`61 passed, 1 skipped`；
- 两种 Compose config：通过；
- `systemd-analyze verify`：通过；
- launcher `sh -n`：通过；
- `git diff --check`：通过。

远端 target smoke 使用以下命令完成，未运行正式矩阵：

```text
sudo env GATEWAY_P2R1_REPO_ROOT=/home/tmpuser/p2r1-smoke-current \
  GATEWAY_P2R1_IMAGE=gateway-p2r1-repository:current-smoke3 \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --diagnostic --workloads W0 \
  --output /var/lib/gateway/repository/p2r1-smoke-w0d.jsonl
```

结果为 launcher exit `0`，三份 artifact 已导出，container、network、volume 和本轮
cgroup 已清理。该 smoke 仅作为真实 delegated-cgroup、Compose、非 root、发布与清理链路
证据，不作为 provider correctness 或 formal selection 证据。

远端 smoke image provenance：

- image digest/ID：`sha256:1c8af0d147bb9a5dfae6d42dfbd5416da222e1303272dd6c7cc3fcc3a03ad100`；
- source revision：`869b93d22401fb340a82ebf4dfe847b29e602339`；
- source tree：`sha256:c24f09fb2cc216007980860ffb24e00fb76f6070cac55a43098406b199d75db6`；
- lock SHA-256：`fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`；
- Dolt：`2.1.11`；uv：`0.11.28`；mysql connector：`9.7.0`；PyArrow：`25.0.0`；
- cache condition：`retained-dependency-cache`。

远端 smoke artifact SHA-256：

```text
672730e9ce701574c247f05567c986b76dbea73701077aa4842a4a92c5b78f59  p2r1-smoke-w0d.jsonl
9a926ef8cdbd123911fc1bfa3472fb41209863b32d2ed32456bd35b74224e5a4  p2r1-smoke-w0d.summary.json
0a43747e50fc4e2e42903fabf83be5650be7ea9e639006d2a97f2126f01ae272  p2r1-smoke-w0d.md
```

旧 quarantine `gateway-p2r1-20260803021647_3977199` 已先完成盘点：
`gateway-p2r1-20260803021647_3977199_repository-data` volume 内容为空，staging
`.p2-r1-export-20260803021647_3977199.ZAFTw8` 内容为空，未发现该 project 的
container/network；随后已精确停止该 run 的 service/slice，删除该 project 的 volume
和空 staging，并确认无 container、network、volume、slice/cgroup 残留。其他 Docker
project、dependency cache 和 image 未修改。

## Interrupted formal rerun diagnostic

在修复前 commit `e75fa3f` 上启动的远端 formal rerun 因预计耗时过长而受控中断，
不构成完整 132-record evidence。该轮使用 image
`sha256:640021056acddfe89a27ab81a679b318a0ac727f58bb5a220860033008a1eca8`，
provenance 为同一 commit、source tree
`sha256:02a84566a292e831ded3a7784b119660d7ed45a15dcf7da7297c5eb3362825d3`、
lock SHA `fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65`，
cache condition 为 `retained-dependency-cache`。

partial raw 保留于远端 staging：

```text
/var/lib/gateway/repository/audit-rerun/.p2-r1-export-20260803073414_1504884.FzJgWA/raw.jsonl
records: 22
bytes: 96559
sha256: cba26b732f2772334de86e27e22c18fefd1857049a55b701c45950954e5cb330
```

其中包含 14 条 representative NULL oracle failure、7 条 workflow cgroup cleanup
failure 和 1 条 `MatrixInterrupted`；该 project 的 source volume 保留，container、
network、sample cgroup 和 per-run slice 已清理。该 raw 仅用于修复诊断，不得进入 provider
selection 或覆盖任何历史 artifact。

后续修复确认了 representative flag expected-value 使用了错误的 row-id 奇偶基准，
并将 sample cgroup cleanup 改为有界等待、逐 PID terminate/kill/reap 和残留诊断；修复后
必须重新完成定向 smoke，再使用新的 audit-rerun 路径执行完整矩阵。

## Execution boundary

当前 authoritative project state 仍为 `no-go`、`selected_provider=none`、不进入 P2-R2。
完成 clean implementation commit 和匹配 provenance image 后，只允许通过新的
`audit-rerun` 输出路径执行一次完整 `60 + 72 = 132` record formal matrix；不得使用
`--diagnostic`、`--workloads` 或历史 artifact 路径。runner 的机械性
`measurement_outcome/proposed_provider` 仅作为待审核证据，即使通过也不自动激活 provider
或推进 P2-R2。
