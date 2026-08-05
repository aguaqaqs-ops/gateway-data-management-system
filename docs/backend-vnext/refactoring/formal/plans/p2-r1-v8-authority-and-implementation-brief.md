# P2-R1 v8 Authority and Implementation Brief

状态：审核通过的 v8 实现基线；formal decision 已完成并纳入 authority。
本文档继续定义 v8 的决策规则和实现边界，当前结果见
[P2-R1 v8 Formal Go Decision](p2-r1-v8-go-decision-2026-08-05.md)。

formal run 前的项目状态为：

```text
formal_status = no-go
selected_provider = null
enter_p2_r2 = false
```

formal run 已通过审核后的当前状态为：

```text
formal_status = go
selected_provider = candidate_a_offline_cli
candidate_b_status = reserved_not_evaluated
p2_r2_status = authorized
production_retest_required = true
```

## 1. 目的与决策原则

v8 将安全性、正式支持范围和资源规划参考分开。资源观测仍必须完整采集、
写入 raw/summary 并生成 warning，但不再把 synthetic workload 的内存比例、
absolute RSS 或 capacity projection 机械地作为 provider selection gate。
方法学版本的精确字符串为 `p2-r1-audit-corrective-v8`。

真正的 hard gate 仍然保护数据正确性、进程生命周期、可取消性、存储证据和
bounded batching。任何 hard gate 失败都不得进入 P2-R2。

## 2. v8 formal coverage

v8 formal runner 只评估 Candidate A：

```text
Candidate A normal:   5 workloads × (1 warm-up + 5 measured) = 30 records
Candidate A scaling:  3 scales × 2 row bounds × (1 warm-up + 5 measured) = 36 records
总计: 66 records
```

normal workloads 为 `W0`、`W1`、`W2`、`W3-1pct` 和 `W3-10pct`；scaling
workloads 为 `S10`、`S40` 和 `S100`，row bounds 为 `256` 和 `1024`。
normal records 不增加 row-bound 维度，统一使用默认 `1024` row bound 和
`1 MiB` byte bound；scaling records 才分别覆盖 `256`/`1024`。

每条 record 的 key 必须唯一；每个组合必须恰好包含一个 warm-up 和五个
measured record。缺失、重复或额外 key 是 formal coverage failure。已写入 raw
的失败 sample 仍占据其 key，不得从 coverage 中删除或静默重跑替换；它应通过
execution/correctness hard gate 使整体 `no-go`，而不应被误报为 missing key。

Candidate B 在 v8 formal summary 中明确写为：

```text
candidate_b_status = reserved_not_evaluated
```

该状态不是 missing、fail 或 inconclusive，不计入 66 条 formal coverage，也
不能参与 provider selection。B 只允许运行独立的 diagnostic W0 smoke，结果
必须标记为 diagnostic-only。

如果审核要求 v8 必须保留同版本 A/B 横向比较，则应另行批准继续执行 132 条
矩阵；本 brief 默认不采用该路径。

## 3. Hard gates 与 advisory observations

### 3.1 继续作为 hard gate

以下任一项失败，v8 必须输出 `formal_status = no-go`，不得选择 provider：

- execution 和 correctness 零失败；
- commit、pinned catalog、NULL、UTF-8、binary 和 tagged CSV 保真；
- cancellation、restart、atomic publication 和 cleanup 成功；
- storage provenance、W3 lifecycle 和 signed storage evidence 完整；
- 实际执行 row bound 与 byte bound；
- oversized row 被单独隔离并记录；
- raw、summary、report 的 coverage、唯一性和 provenance 完整；
- 无 timeout、OOM、provider/server 进程泄漏或 cgroup 残留；
- target named-volume、filesystem 和 storage-root identity 经过 typed manifest 验证。

### 3.2 只作为 warning/advisory

以下数据仍必须进入 raw/summary，但不自动阻止 A 通过：

- bounded-stream `1.5x` ratio；
- provider、workflow 和 cgroup absolute memory；
- anonymous/file memory；
- capacity projection；
- 推荐并发数和生产内存配置；
- synthetic workload 与参考资源预算的偏离。

资源 warning 不得掩盖真正的 timeout、OOM、cleanup failure 或其他 execution
failure；这些仍按 hard gate 处理。
“观测值超过参考”不是 hard failure，但要求的 memory/cgroup/raw evidence
缺失、未验证或无法聚合仍是 evidence-completeness hard failure。Ratio
继续使用 v7 零值规则：三个 scale 全为零时 ratio 为 `1.0`；最小值为零且
存在正值时 ratio 为无穷大并产生 warning。`unavailable` 表示证据不完整，
在 formal run 中必须同时触发 evidence-completeness hard failure；不得用
advisory 语义掩盖采样缺失。

## 4. Provider 与 lifecycle policy

若 Candidate A 的 66 条 formal records 全部通过 hard gates，v8 的 proposed
decision 为：

```text
default_provider = candidate_a_offline_cli
candidate_b_sql_server = preserved_but_disabled_by_default
```

Candidate A 保持每次 query 启动 Dolt CLI、完成后退出的 lifecycle，不增加
restart-before-stream 作为默认正式流程。Candidate B 保留代码、配置和历史
证据，但不在本轮默认启用；只有未来业务明确需要 long-lived server 或
concurrent-read 时，才单独提出启用、测试和决策。

该默认策略已由 v8 formal go decision 采用。Candidate A 仍需在生产等效环境和
实际业务样本上完成 production retest；在该复测前不得宣称 production activation。

## 5. Batch contract

v8 的机器可校验 batch contract 为：

```text
effective formal byte bound = 1 MiB
row bounds = 256 / 1024
configurable byte target range = 256 KiB .. 4 MiB
single row > 1 MiB = one-row batch + oversized_row=true
encoded tagged-CSV line > max_stream_line_bytes = reject
```

`1 MiB` 是 v8 formal 的固定 effective bound；`4 MiB` 只是配置允许的上限，
不能在正式运行中悄然替代 1 MiB。后续若选择 `512 KiB` 或 `256 KiB`，必须在
新的 methodology/configuration 中显式记录。

普通 batch 的 decoded payload 必须满足：

```text
1 <= batch_rows <= effective_row_bound
batch_payload_bytes <= effective_formal_byte_bound
```

唯一允许超过 1 MiB 的情况是单行无法拆分且该 batch 恰好只包含这一行。该
oversized row 必须记录 `oversized_row=true`、`row_bytes`、原因和实际 batch
bytes。Candidate A 对应的 encoded tagged-CSV line 仍必须独立通过
`max_stream_line_bytes` 检查。空结果集可以产生零个 batch。

`max_batch_bytes` 的计算使用 decoded row payload 之和，而不是 Arrow allocator
大小、CSV delimiter 大小、SQL 文件大小或 connector buffer 大小。

`max_stream_line_bytes` 是 Candidate A tagged-CSV 传输层的 encoded line safety
limit，与 decoded `row_bytes` 不是同一口径。实现必须独立验证 raw
encoded line 不超过该上限；不得通过将 decoded `row_bytes` 与
`max_stream_line_bytes` 直接比较来代替。

## 6. Payload 与 batch measurement contract

Candidate A/B 必须使用同一 `_row_bytes()` 口径。每条成功的 stream record 至少
写入以下字段：

```text
total_rows
total_stream_payload_bytes
max_row_bytes
batch_count
max_batch_rows
max_batch_bytes
oversized_single_row
oversized_row_count
max_oversized_row_bytes
batch_contract_valid
batch_contract_violation_count
```

`total_stream_payload_bytes` 定义为所有成功解析并输出的 canonical decoded
row payload bytes 总和。`_row_bytes()` 的规范化计数规则固定为：

- 字符串按 UTF-8 编码后的字节数计算；
- binary 按原始 binary 字节数计算；
- NULL 不贡献 payload bytes；
- 其他 normalized scalar 按 `str(value).encode("utf-8")` 的字节数计算；
- 不包含 SQL 文本、CSV 分隔符、换行、Arrow metadata 或 allocator overhead；
- 行内字段顺序和类型转换必须与最终 Arrow schema 一致。

`max_row_bytes` 是单行 decoded payload 的最大值；`max_batch_rows` 和
`max_batch_bytes` 分别是实际输出 batch 的最大行数和最大 decoded payload。
这些指标必须从 worker 实际 emitted batches 产生，不能由 workload 配置值推导。
`total_rows` 必须等于所有 emitted batch 的 `num_rows` 之和，
`total_stream_payload_bytes` 必须等于各 batch decoded payload 之和。
对多表 catalog，workflow 必须跨所有 `stream_table()` 调用累加 count/total，
并对 max 字段取最大值；不得被最后一张表的 `last_stream_metrics`
覆盖。
`oversized_single_row` 等于 `oversized_row_count > 0`，每个超过 byte bound
的 batch 都必须恰好只有一行。`batch_contract_valid` 必须由 worker 对每个
emitted batch 逐个检查后得出；任何 violation 都必须使它为 `false` 并触发
hard gate。空结果集的上述计数和 max 字段统一为 `0`，
`batch_contract_valid=true`。

## 7. Supported envelope

支持范围是同时满足行数和 package 大小条件，而不是二选一：

```text
validated:
  total_rows_at_commit <= 100,000
  max_table_rows <= 100,000
  import_package_bytes <= 200 MiB

controlled_preview:
  100,000 < total_rows_at_commit <= 1,000,000
  max_table_rows <= 1,000,000
  import_package_bytes <= 200 MiB
```

`validated` 是 v8 可以声明的初版正式验证范围。`controlled_preview` 只表示
允许在受控条件下试运行，不提供 capacity 或 production SLO 保证；默认单并发
或低并发，并必须记录实际 rows、payload bytes、RSS、cgroup 和 duration。

此处 `import_package_bytes` 是解包/解压后实际 replay SQL 文件的字节数，
不是压缩包、HTTP body 或对象存储封装大小。多表 import 同时受
`total_rows_at_commit` 和 `max_table_rows` 限制，不允许通过分成多表绕过总行数边界。
`total_rows_at_commit` 是 pinned target commit 中所有被流式读取表的 catalog
row count 之和，不是本次 replay SQL 中 INSERT/UPDATE/DELETE 语句的数量。

超过 1,000,000 总行数或 200 MiB replay SQL 需要显式人工批准。
未收集足够真实业务样本前，不得把
controlled preview 宣称为正式支持能力。

## 8. Resource advisory

资源数据不是 provider selection 的机械 gate，但 summary 必须包含机器可读的
advisory：

```text
resource_advisory:
  ordinary_workflow_reference_bytes
  boundary_workflow_reference_bytes
  service_reference_bytes
  four_worker_burst_reference_bytes
  recommended_concurrency
  observed_max_workflow_cgroup_peak_bytes
  exceedances
  status: within_reference | above_reference
  affects_formal_decision: false
```

初始规划参考为：

```text
single ordinary workflow reference = 2.5 GiB
single boundary workflow reference = 3 GiB
recommended concurrency            = 2
ordinary service memory reference   = 8 GiB
four-worker burst reference         = 16 GiB
test safety ceiling per workflow    = 8 GiB
```

对应的精确 bytes 值为 `2684354560`、`3221225472`、`8589934592` 和
`17179869184`，不使用 decimal GB 换算。

这些值来自 synthetic/diagnostic 观察，只用于容量规划和告警，不是 production
SLO 或 acceptance budget。`test safety ceiling` 是保护测试宿主的 emergency
ceiling；触发它时运行应按 OOM/timeout 或 safety failure 处理，但不能把 8 GiB
解释成 provider 的生产资源承诺。

resource advisory 的比较口径是每个 workflow cgroup 的 absolute
`memory.peak`（包含 anonymous memory 和 file cache），不是 process-tree RSS。
`W2` 使用 boundary reference，其他 formal workloads 使用 ordinary reference。
`observed_max_workflow_cgroup_peak_bytes` 取 66 条 raw（包括 warm-up 和失败
sample）中所有 available/verified memory evidence 的最大观测值；失败 sample
不得仅因失败而从资源报告中过滤。`exceedances` 列出超过其对应 reference 的 record keys
和观测值。任一超出时 `status=above_reference`，但不改变 formal decision。
service 和 four-worker 数值只作为规划参考，因为 66-record matrix 不测量并发
workflow，不得将单 workflow 观测伪造成 service-level measured peak。

formal target 必须将 sample child cgroup `memory.max` 设为
`8 * 1024 * 1024 * 1024` bytes，并在 raw 中记录同一
`memory_limit_bytes`。无法委托 controller、无法设置或无法回读精确值时
preflight fail closed。这是测试安全上限，不参与 advisory status 比较。
如任一 ancestor cgroup 存在低于 8 GiB 的 finite `memory.max`，preflight
也必须 fail closed，不得只回读 sample child 的局部值。Raw 应同时记录
`memory_limit_bytes=8589934592` 和沿 hierarchy 计算的
`effective_memory_limit_bytes`。

默认并发建议为 2。大 package 可以按权重占用两个调度 token；4 workers 只作为
可配置 burst。资源 warning 应触发记录和告警，不应阻止满足安全 hard gates 的
workflow。

## 9. Formal decision output

v8 runner 必须动态生成以下字段，不得硬编码选择结果：

```text
formal_status
selected_provider
candidate_b_status
p2_r2_ready
resource_advisory_status
production_retest_required
```

为保持现有 consumer/report 兼容，decision aliases 必须与上述字段一致：

```text
measurement_outcome = formal_status
p2_r1_exit = formal_status
round_exit = formal_status
proposed_provider = selected_provider
next_round_ready = p2_r2_ready
formal_decision = true
records = actual raw record count
normal_records = actual normal record count
scaling_records = actual scaling record count
unique_measurement_keys = actual unique key count
performance_excluded_warmups = actual recorded warm-up count
expected_records = 66
expected_normal_records = 30
expected_scaling_records = 36
expected_warmups = 11
```

上述 actual 字段必须从 raw 动态聚合，不得硬编码为 expected 值。
只有完整成功的 v8 coverage 才会同时满足 `records=66`、
`normal_records=30`、`scaling_records=36`、`unique_measurement_keys=66` 和
`performance_excluded_warmups=11`。

如果 A 的全部 hard gates 通过，预期输出形状为：

```text
formal_status = go
selected_provider = candidate_a_offline_cli
candidate_b_status = reserved_not_evaluated
p2_r2_ready = true
resource_advisory_status = within_reference | above_reference
production_retest_required = true
```

如果 coverage、correctness、lifecycle、provenance、batch safety 或 cleanup 任一
失败，则必须输出：

```text
formal_status = no-go
selected_provider = null
candidate_b_status = reserved_not_evaluated
p2_r2_ready = false
production_retest_required = false
```

`production_retest_required=false` 在 `no-go` 时表示“尚未到生产复测阶段”，
不表示生产复测被永久免除。

Candidate A matrix 必须分开发布：

```text
batch_safety_gate
scale_ratio_observation: pass | warning | unavailable
capacity_advisory_status: within_reference | below_reference | unavailable
hard_gate
result: pass | fail
```

`batch_safety_gate` 只由 row/byte/oversized contract 决定。为兼容旧 consumer，
v8 如仍发布 `bounded_stream_gate`，必须令其等于 `batch_safety_gate`，并同时
发布 `bounded_stream_gate_semantics=batch_contract_v8`；不得再令它等于
`1.5x` ratio 结果。现有 `capacity_gate` 不得纳入 v8 `hard_gate`，新报告以
`capacity_advisory_status` 为准。

Candidate B 的 `candidate_matrix` entry 只发布
`status=reserved_not_evaluated`、`hard_gate=null` 和 `result=not_evaluated`，不得填充
虚假的 pass/fail 数据。

在 v8 authority 尚未落地或 v8 formal 尚未通过审核前，外部项目状态仍固定为
`no-go`，不选择 provider，不进入 P2-R2。

## 10. Required machine checks

v8 implementation 必须增加或修订以下检查：

- v8 authority version 与 settings/methodology metadata 一致；
- formal coverage exact 66，A-only；B 为 `reserved_not_evaluated`；
- missing/duplicate/extra key、warm-up/measured 数量错误均 fail closed；
- `1 MiB` effective byte bound 实际生效；
- normal records 统一使用 1024 row/1 MiB byte bound；
- W2 在 1024 row bound 下由 byte bound 自动拆批，并证明
  `max_batch_rows < 1024`、`max_batch_bytes <= 1 MiB`；
- oversized single row 独立 batch、marker、row bytes 和 reason 完整；
- multiple oversized rows 逐个独立 batch，count/max 指标及 batch contract 一致；
- total payload、max row、batch count、max rows/bytes 使用同一 `_row_bytes()` 口径；
- 多表 catalog 的 count/total/max 在 workflow 级别正确聚合，不被最后一表覆盖；
- tagged-CSV encoded line safety limit 与 decoded row/batch accounting 分开测试；
- A 的 ratio/absolute memory/resource 只生成 advisory，不改变 selection；
- required absolute memory/cgroup evidence 缺失时 fail closed，不会被 advisory
  分层降级为 warning；
- B small W0 smoke 不进入 candidate matrix 或 selection；
- target named-volume、cgroup、provenance、publication 和 cleanup hard gates 保持；
- resource advisory 与 raw/summary 的 observed peaks 一致；
- sample child 和 ancestor cgroup 的 effective 8 GiB safety ceiling 得到设置、
  回读和 raw 记录；
- failed sample 保留 key coverage 但使 execution/correctness gate 失败；
- decision aliases、record counts、warm-up exclusions 和 Candidate B reserved entry 一致。

## 11. Execution order and commit boundaries

建议按以下顺序执行：

1. 提交当前 v7 diagnostics、paired analysis 和 PID monitor 修复；
2. 将本 brief 纳入文档，单独更新 v8 authority，并进行 authority diff 审核；
3. 实现 v8 runner、settings、summary schema 和 tests；
4. 执行 lock、Ruff、mypy、pytest、Compose、systemd、shell 和 diff checks；
5. 运行小型 Candidate A W0 smoke；
6. 运行 Candidate B reserved W0 smoke，只执行一个 diagnostic W0 sample，
   必须写入 `diagnostic_only=true`、`formal_decision=false`，不产生
   candidate-matrix pass/fail 或 selection；
7. 从 clean、provenance-qualified revision 构建镜像；
8. 使用全新路径只运行一次 66-record A-only v8 formal matrix；
9. 由 raw/summary/report 计算正式 decision，提交独立 v8 artifacts。

在步骤 8 完成并通过审核前，不修改历史 v7 artifacts，不覆盖任何旧输出，不
选择 provider，也不进入 P2-R2。

## 12. Explicit non-go conditions

即使资源数据看起来良好，以下情况仍为 `no-go`：

- 任一 execution/correctness failure；
- batch/byte bound 未执行或 evidence 不完整；
- cancellation、restart、publication 或 cleanup 失败；
- storage provenance、W3 lifecycle 或 commit-pinned read 不完整；
- timeout、OOM、进程泄漏、PID/cgroup 残留；
- raw/summary/report coverage、唯一性或 provenance 不完整；
- target image、dependency lock 或 source revision 不匹配。

相反，单独的 `1.5x` 超标、absolute memory warning 或 capacity projection warning
不应在 hard safety conditions 全部满足时自动淘汰 Candidate A；它们必须在报告
中清楚标注为 advisory，并保留足够数据供生产容量规划和后续 retest 使用。
