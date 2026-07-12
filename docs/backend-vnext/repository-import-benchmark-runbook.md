# Repository Import Benchmark Runbook

本文说明如何在 backend vNext 中手动运行 repository import benchmark，重点是外部真实业务数据的执行方式、结果产物和验收口径。

当前 Phase 4 已把 benchmark 拆成两条线：

- `flow_journey` 负责 upload / submit / open 这条用户旅程。
- `history_compare` 负责 repo-backed history compare、native route 和 cache 命中观察。
- `workflow_ladder` 负责真实三节点链路 `upload -> submit -> approve -> archive -> history compare`，默认用 `business_small_cut/small_cut`、`business_small_cut/small_cut-1`、`business_small_cut/small_cut-2` 做 smoke，并在同一 suite 里观察 2-node compare 和 3-node dual-pair compare。
- 本 runbook 只覆盖 repository import benchmark，不再把这两条 benchmark 线混成一条主路径。

## 什么时候需要手动跑

- 只验证代码是否可 import、单元测试是否通过：不需要手动跑真实业务数据。
- 要验证 benchmark runner 在真实业务数据上的行为、产物和性能对比：需要至少手动跑一次 Phase A。
- 当前建议优先跑 `business_small_cut + IMPORT_HEALTH_SMOKE`，确认环境、数据根和 provider runner 都正常，再逐步扩到 Phase B / Phase C。

## 前置条件

- 后端虚拟环境使用 `gateway-data-management-system/backend/.venv/`。
- `dolt` 和 `mysql` 可在当前环境中执行。
- 运行时需要把 `gateway-data-management-system/backend` 放进 `PYTHONPATH`，因为 benchmark runner 直接从 `backend_vnext` 包加载。
- 真实业务数据放在仓库外的 dataset root，例如 `/home/issac/test-dir/business-benchmark-data/`。

## 数据目录

推荐结构如下：

```text
/home/issac/test-dir/business-benchmark-data/
  business_small_cut/
    dbcfg.sql
    dataset.yaml optional
  business_small/
    dbcfg.sql
    dataset.yaml optional
  business_medium/
    dbcfg.sql
    dataset.yaml optional
  business_large/
    dbcfg.sql
    dataset.yaml optional
    large/
      sql/
        dbcfg.sql
    large-1/
      sql/
        dbcfg.sql
    large-2/
      sql/
        dbcfg.sql
```

`dataset.yaml` 只保存非敏感描述。常用字段包括：

```text
dataset_id
dataset_kind
business_label optional
anonymization_note optional
requested_tables optional
validation_tables optional
source_sql_file optional
```

当某个业务大类下有多个显式样本目录时，可以把子目录直接作为 benchmark 输入，例如 `business_large/large`、`business_large/large-1`、`business_large/large-2`。如果某个目录没有单独的根部 `dbcfg.sql`，resolver 会优先找该目录下的 `sql/dbcfg.sql` 作为 source SQL。

注意事项：

- 真实业务数据不要放进 git。
- `gateway-data-management-system/backend/tests/backend_vnext/fixtures/` 只用于可提交的小样本、回归样本和本地调试中转，不用于正式 benchmark 数据。
- 如果你在准备过程中需要临时摆放原始输入，仍应放在仓库外目录，或者只放到 `fixtures/external/` 这种本机调试位置。

## 运行方式

`repository_import` benchmark 目前仍以 Python API 方式调用，默认 validation policy 是 `VERIFY_SCHEMA_ROW_COUNT_SUMMARY`，这样 benchmark 更接近“导入成本 + 轻量校验成本”的真实口径；如果要做纯吞吐观察或验证极大数据集的导入速度，可以在代码里切到 `DISABLED`，但它不参与 correctness 结论。
`history_compare` 已补齐独立的 `python -m backend_vnext.benchmarks.history_compare` 入口，默认 validation policy 是 `DISABLED`，适合单独跑 repo-backed compare、native route 和 cache 命中观察。
当前 history compare 不再承担单独准备阶段，运行时必须通过 `--repository-backed-inputs` 提供 benchmark-local 的 repository-backed compare 事实。真实对外 contract 仍然只认 repository refs；`repository_path` 和 `requested_tables` 只是 benchmark-local 的桥接信息。
当前 history compare 的 cache 补写已经拆成独立的 `ASYNC_COMPARISON_CORE_CACHE_COMPLETION` step，report 会额外展示 `Comparison Core Cache Completion ms`，用来和 compare / risk / surface 主路径分开计时。
如果 async completion 里出现 `records_closure_missing`，说明当前 compare 结果链没有携带可回填的 canonical `ComparisonRecordsClosure`，这会让补写跳过；它不是 cache store 失效，而是结果侧没有提供可写入的 closure。
比较稳妥的 cache 口径是：preview 阶段可以先写 provisional key，但 `SUBMIT_FINALIZE` 拿到最终 repository-backed commit / ref 后，还要把同一份 compare 结果 promotion / rekey 成 canonical compare-core key，让后续 `history_compare` 统一读取最终身份。
如果你跑的是 `journey_history_compare` suite，`flow_journey` 和 `history_compare` 会共享同一个 `run_root` 级持久化 `comparison-core-cache`，`SUBMIT_FINALIZE` 负责把 preview 期间的临时 key 迁到 canonical key，`history_compare warm-full` / `warm-verify` 才能观察到真正的命中。
如果某个 dataset 需要对少量关键表做额外 row digest 校验，也可以显式传 `validation_table_names`。
如果你跑的是 full journey / submit finalize 收口路径，当前实现已经固定 `SUBMIT_FINALIZE` 为 `SQL_DUMP_REPLAY` replay-only；正式提交不再依赖 CSV/TSV staging。
这里说的 compact replay-only layout 指最终的 repository import artifact：每表一个 `table.json`，再加一个 `bundle.json` 和一个顶层 `replay.sql`。因此单次 build 的文件数大致是 `table_count + 2`，例如 `business_large` 现在约 `321` 个文件。
`history_compare` 这条 benchmark 不再有单独的准备路径，也不会再因为 compare benchmark 自身去生成临时 `rows.tsv`。如果你需要 standalone compare，请先准备一个 `repository-backed-inputs` JSON，里面按 dataset_id 显式写出 `before_repository_path`、`current_repository_path`、`before_repository_ref`、`current_repository_ref` 和 `requested_tables`。

### History Compare

独立运行 repo-backed history compare 时，可以直接使用下面的模块入口：

```bash
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python -m backend_vnext.benchmarks.history_compare \
  --run-root /tmp/backend-vnext-history-compare-benchmark \
  --dataset-root /home/issac/test-dir/business-benchmark-data \
  --repository-backed-inputs /tmp/backend-vnext-history-compare-repository-backed-inputs.json \
  --datasets business_small_cut business_large business_large/large business_large/large-1 business_large/large-2 \
  --profiles REPO_BACKED_COLD REPO_BACKED_WARM \
  --validation-policy DISABLED
```

说明：

- `--repository-backed-inputs` 是必需参数，runner 不再从单独准备阶段生成 compare 输入。
- 这个 JSON 只用于 benchmark-local 复现，不是 public flow contract；真实 `history compare` 仍然只输入 repo refs。
- `--datasets` 和 `--profiles` 都可省略；省略时分别使用 runner 默认数据集和默认 profile。
- `--validation-policy DISABLED` 适合纯 compare / native route / cache 观察，不把 repository import validation 计入结论。
- `run_root` 默认会保留，便于复盘 `summary.json`、`report.md`、`repos/` 和 `repository-ref-cache/`。
- 当前实现里 `Open Baseline Ref` 是 summary-first / selective materialization：它会先根据 repo-backed summary 做 route plan，再只 materialize row-level 真正需要的 baseline 表。
- `Open Current Ref` 的实现口径是“先复用已 materialized snapshot，其次 summary-first / selective / lazy，最后才 fallback 完整 materialization”。这条路径的目标是让 current ref 在 warm 场景里尽量少做重复 IO，同时不改变 compare 语义。
- report 里会额外显示 `materialized_table_count` 和 planned route 计数，方便区分 baseline selective 成本和 compare 本身的成本。
- 如果 `requested_tables` 省略，benchmark 会按 repo-backed summary 中可比较的表集推进；显式传入时只作为 benchmark-local 的路由提示，不会扩展真实 flow contract。

### Workflow Ladder

如果你要模拟更贴近真实使用路径的三节点链路，可以直接跑新的 `workflow_ladder` suite。这个 suite 会依次执行：

1. `small_cut` 的 `upload -> submit -> approve -> archive`
2. `small_cut-1` 的 `upload -> submit -> approve -> archive`
3. `small_cut-2` 的 `upload -> submit -> approve -> archive`
4. 2-node compare: `(small_cut, small_cut-1)`
5. 3-node dual-pair compare: `(small_cut, small_cut-1)` + `(small_cut-1, small_cut-2)`

命令示例：

```bash
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python -m backend_vnext.benchmarks.workflow_ladder \
  --run-root /tmp/backend-vnext-workflow-ladder-benchmark \
  --dataset-root /home/issac/test-dir/business-benchmark-data \
  --datasets business_small_cut/small_cut business_small_cut/small_cut-1 business_small_cut/small_cut-2
```

说明：

- 这个 suite 仍然只消费正式 repo refs 和 repo-backed readback 事实，不新增 public flow contract。
- `approve` / `archive` 是正式 flow 入口，`Open Ref` 仍作为 archive 最后收尾步骤。
- compare 只使用 `history_compare` 的正式 compare 路径，benchmark-local 只负责把三节点 ladder 编排好。

### Phase A

```bash
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python - <<'PY'
from pathlib import Path

from backend_vnext.benchmarks.repository_import import (
    RepositoryImportBenchmarkProfile,
    RepositoryImportBenchmarkRunner,
)

runner = RepositoryImportBenchmarkRunner(
    dataset_root=Path("/home/issac/test-dir/business-benchmark-data"),
    run_root=Path("/tmp/backend-vnext-repository-import-benchmark/phase-a"),
)
summary = runner.run(
    profiles=(RepositoryImportBenchmarkProfile.IMPORT_HEALTH_SMOKE,),
    datasets=("business_small_cut",),
    validation_policy="VERIFY_SCHEMA_ROW_COUNT_SUMMARY",
)
print(summary.run_id)
print(len(summary.results))
PY
```

如果要针对单个 dataset 覆盖关键表列表，可以传字典：

```python
summary = runner.run(
    profiles=(RepositoryImportBenchmarkProfile.IMPORT_HEALTH_SMOKE,),
    datasets=("business_small_cut",),
    validation_policy="VERIFY_TABLE_DIGESTS",
    validation_table_names={"business_small_cut": ("version_manager", "device_cfg")},
)
```

### Phase B

```bash
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python - <<'PY'
from pathlib import Path

from backend_vnext.benchmarks.repository_import import (
    RepositoryImportBenchmarkProfile,
    RepositoryImportBenchmarkRunner,
)

runner = RepositoryImportBenchmarkRunner(
    dataset_root=Path("/home/issac/test-dir/business-benchmark-data"),
    run_root=Path("/tmp/backend-vnext-repository-import-benchmark/phase-b"),
)
summary = runner.run(
    profiles=(RepositoryImportBenchmarkProfile.END_TO_END_COLD,),
    datasets=("business_small", "business_medium"),
    validation_policy="DISABLED",
)
print(summary.run_id)
print(len(summary.results))
PY
```

### Phase C

```bash
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python - <<'PY'
from pathlib import Path

from backend_vnext.benchmarks.repository_import import (
    RepositoryImportBenchmarkProfile,
    RepositoryImportBenchmarkRunner,
)

runner = RepositoryImportBenchmarkRunner(
    dataset_root=Path("/home/issac/test-dir/business-benchmark-data"),
    run_root=Path("/tmp/backend-vnext-repository-import-benchmark/phase-c"),
)
summary = runner.run(
    profiles=(
        RepositoryImportBenchmarkProfile.END_TO_END_COLD,
        RepositoryImportBenchmarkProfile.IMPORT_ONLY_WARM_ARTIFACT,
        RepositoryImportBenchmarkProfile.SERVER_SESSION,
    ),
    datasets=("business_medium", "business_large"),
    validation_policy="DISABLED",
)
print(summary.run_id)
print(len(summary.results))
PY
```

默认情况下，runner 会使用第一批 benchmark provider：

```text
SQL_DUMP_REPLAY
SINGLE_TABLE_CLI_IMPORT
MULTI_TABLE_CLI_IMPORT
LOAD_DATA
PARQUET_IMPORT
DOLT_SERVER_BULK_LOAD
SERVER_SESSION_BULK_LOAD
```

如果只想跑一部分 provider，可以在 `runner.run(...)` 里传 `providers=(...)`。

## 产物

单次运行的输出根目录默认是 `run_root`，通常包含：

```text
summary.json
report.md
datasets/
artifacts/
repos/
logs/
```

其中：

- `summary.json` 是权威结果。
- `report.md` 由 `summary.json` 生成。
- `datasets/<dataset_id>/manifest.json` 保存数据集摘要。
- `datasets/<dataset_id>/snapshot-summary.json` 保存 materialization 结果摘要。
- `logs/benchmark.log` 保存过程日志。
- 如果你跑的是 `journey_history_compare` suite，`run_root` 下还会额外出现 `comparison-core-cache/`、`projection-table-cache/` 和 `repository-ref-cache/`，它们是 suite 级共享缓存，而不是单条 flow 的临时产物。

## Retention / Cleanup

默认策略是保留整个 `run_root`，因为它同时承载 summary、report、datasets、artifacts、repos 和 logs，便于复盘和排障。

- benchmark runner 不会在结束时自动删除 `run_root`。
- 如果只是本地查看结果，通常在确认 `summary.json` 和 `report.md` 已生成并被消费后，再手工删除整个 `run_root`。
- 如果是 CI、定时任务或长时间运行环境，建议由外部 retention job 统一清理旧 run_root，而不是在 benchmark 进程内部做激进删除。
- `business_large` 这类大数据集尤其适合保留一段时间，因为失败时通常需要回看 `artifacts/`、`repos/` 和 `logs/`。

## 验收口径

- `summary.json` 和 `report.md` 都生成成功。
- `summary.json` 可以被重新读取并 round-trip。
- Phase A 中同一 Snapshot 的 `IMPORT_HEALTH_SMOKE` 结果应全部通过。
- `status = PASSED` 的结果必须同时满足导入、提交、readback 和验证通过。
- 真实业务数据如果暴露出不支持的 DDL、readback digest mismatch 或明显的 provider 语义差异，应暂停讨论，不要硬绕过。

## 性能观察

以下结论基于 Phase A / Phase B / Phase C 的 `validation_policy=DISABLED` 结果，也就是纯导入吞吐，不包含 validation 成本。对应 run id 分别是 `repository-import-benchmark-20260620-6e61002b`、`repository-import-benchmark-20260620-ec0c9738`、`repository-import-benchmark-20260620-db3e7e6a`。`commit_duration_ms` 一直稳定在 `179-501ms`，因此整体排序主要由 `import_duration_ms` 决定。

`business_small_cut` 不是极端压测样本，而是裁切后的常规业务数据，所以它更适合用来验证默认归一化路径是否引入明显回归；真正的性能排序建议以 `business_small`、`business_medium`、`business_large` 为主。

### 关键数据

| Provider | Phase A `business_small_cut` | Phase B `business_small` | Phase B `business_medium` | Phase C `business_medium` range | Phase C `business_large` range |
| --- | ---: | ---: | ---: | ---: | ---: |
| `SQL_DUMP_REPLAY` | `873 ms` | `6,434 ms` | `15,106 ms` | `15,637-15,798 ms` | `24,805-25,856 ms` |
| `LOAD_DATA` | `3,833 ms` | `11,229 ms` | `21,033 ms` | `21,369-22,529 ms` | `32,709-32,934 ms` |
| `DOLT_SERVER_BULK_LOAD` | `4,482 ms` | `11,003 ms` | `21,591 ms` | `21,411-21,715 ms` | `32,756-38,033 ms` |
| `SERVER_SESSION_BULK_LOAD` | `4,089 ms` | `10,904 ms` | `21,529 ms` | `21,406-21,674 ms` | `32,824-39,655 ms` |
| `PARQUET_IMPORT` | `8,754 ms` | `17,455 ms` | `22,027 ms` | `22,027-24,100 ms` | `36,740-37,711 ms` |
| `SINGLE_TABLE_CLI_IMPORT` | `8,365 ms` | `20,657 ms` | `25,066 ms` | `25,032-27,801 ms` | `40,736-43,150 ms` |
| `MULTI_TABLE_CLI_IMPORT` | `8,002 ms` | `20,372 ms` | `25,142 ms` | `25,141-25,303 ms` | `40,629-40,720 ms` |

补充观察：

- `SQL_DUMP_REPLAY` 在 A/B/C 全部阶段都是最快基线，适合作为“上界参考”。
- `LOAD_DATA`、`DOLT_SERVER_BULK_LOAD`、`SERVER_SESSION_BULK_LOAD` 在中大数据集上基本处于同一梯队，和 `SQL_DUMP_REPLAY` 之间有稳定差距，但通常比 `PARQUET_IMPORT` 和两种 CLI import 更有竞争力。
- `SINGLE_TABLE_CLI_IMPORT` 和 `MULTI_TABLE_CLI_IMPORT` 在表数较多的数据集上最容易变慢，是当前结果里最不适合作为默认快路径的两类 provider。
- Phase C 中同一 dataset 不同 profile 的 provider 排名没有改变，说明 provider 选择比 profile 切换更重要。
- `business_small_cut` 只有 6091 行但有 132 张表，固定开销被放大得很明显；它适合 smoke，不适合作为唯一性能结论来源。

### 初步方案推荐

1. 如果源数据本身就是 SQL dump，且业务 contract 允许 replay SQL，那么 `SQL_DUMP_REPLAY` 继续作为 correctness baseline 和 replay baseline；当前三轮结果里它始终最快，适合作为上界参考。正式 submit finalize 已固定 replay-only，但 repository-import benchmark 的最终默认性能 provider 仍应由同机同数据的对比结果决定。
2. 纯性能观察时继续使用 `DISABLED`，这样可以把 validation 成本从导入成本中剥离出来，避免 benchmark 被 validation 主导。
3. 正式轻量校验跑法继续保留默认 `VERIFY_SCHEMA_ROW_COUNT_SUMMARY`，用于轻量确认导入结果没有明显结构性偏差。
4. 如果需要非 SQL 路径，优先把 `LOAD_DATA` 作为第一候选，再根据实际环境比较 `DOLT_SERVER_BULK_LOAD` 和 `SERVER_SESSION_BULK_LOAD`。
5. `PARQUET_IMPORT` 可以作为列式 staging 的对照方案保留，但当前结果不支持把它作为优先快路径。
6. `SINGLE_TABLE_CLI_IMPORT` 和 `MULTI_TABLE_CLI_IMPORT` 建议定位为兼容、fallback 或对照方案，而不是大数据量默认路径。

## 常见排错

- `dolt` 或 `mysql` 不在 PATH：先确认本机工具安装和 `gateway-data-management-system/backend/.venv/` 可用。
- dataset root 不存在：确认外部业务数据已经放到指定目录。
- 误把老项目测试一起跑了：只执行 `gateway-data-management-system/backend/tests/backend_vnext`。
- `summary.json` 有了但 `report.md` 不对：正常情况下不应发生，`report.md` 必须从 `summary.json` 生成。
