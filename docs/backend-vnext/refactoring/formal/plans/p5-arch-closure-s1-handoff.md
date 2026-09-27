# P5 架构收口 S1 Handoff

状态：**S1 implementation complete — pending container gate evidence on final HEAD**

日期：2026-09-27

Owner：P5 Architecture Closure

Worktree：`/home/dev/gdds-p5-closure-s1`  
分支：`p5-closure/s1`

## Traceability

```yaml
stage: P5-arch-closure-S1-structure
parent_head: e04c1bcca7d17d1f7e1feda9b8329a4503942d6b
candidate_head: 450e15e5486454eb0335636477a0c304b8c5546d
uv_lock_in_diff: no  # 7de23ed349 恢复 canonical PyPI identity；禁止再次用 ambient index 改写 lock
implementation_authority: execution-plan §8.4 S1.1–S1.7
```

## 1. S1 kickoff — 真实数据普查（DC22 / DC12 / DC15）

- 脚本：`vnext/backend/benchmarks/real_dump_census.py`（提交 `2c0d49fae9`）。
- 命令：

```bash
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py
```

- 产出：`$GATEWAY_REAL_DUMP_ROOT/packages/*.tar.gz`、`datasets.json`、`census/summary.json`（主机侧，不入库）。
- **pair_of（owner 确认）**：每 tier 内 `*-1` → `*-2` 为同一项目前后版本；四个 tier（t1–t4）为不同项目 alias（a–d）。
- **DC12**：八份样本 `json_columns` 均为空 → **未触发** LONGTEXT 路径；S2a 仍 fail-closed JSON。
- **DC15**：八份样本 `unknown_sql_types` 均为空 → **未触发** 词表扩充；登记为 kickoff 负结果。
- **普查局限（须如实写入，不可当作 S2a 强证据）**：
  - SQL 解析在样本上多为 `UNSUPPORTED_STATEMENT`（`dbcfg.sql` 形态）；
  - business materialization 多为 `FAILED`（`TABLE_READER_UNAVAILABLE` / 中档以上 `XML_DOCUMENT_FAILED`）；
  - 结构统计字段（表数、行数、storage 类型计数等）多为空。

## 2. 子步 ↔ 提交

| 子步 | 提交 | 摘要 |
| --- | --- | --- |
| kickoff | `2c0d49fae9` | `real_dump_census.py` |
| S1.1 | `eb4ccfb863` | 删除 cache / dead projection；synthetic 移 T/support |
| S1.2 | `69d6b82632`, `7d9ee45e2b` | canonical row hash 迁入 capability；删 manifest/cells 重复；DC26 import 放行 |
| S1.3–S1.4 | `a5a62e58d3` | wire_codec、facade、composition root、history_reader 等 |
| S1.5–S1.6（部分） | `d42a740e7d` | control_transactions、artifact_refs、comparison 行编码破环、import 基线 |
| S1.7 | `d97428ed22` | architecture 基线/import_rules 终态、reachability shim |
| S1.7 修复 | `7de23ed349` | 恢复 canonical `uv.lock`；wire_codec 上传 ref；busy_timeout 测试补丁 |

## 3. import_rules 前后对照（§2 S1 机械验收）

| 指标 | S1 base @ `e04c1bcca7` | S1 HEAD @ `7de23ed349` |
| --- | --- | --- |
| 层/私有违例 | 54 | **3**（http_arrow×2 + `repository_import_artifact` unowned，均 S2b 关闭） |
| 运行时环 | 8 | **0** |
| 不可达模块 | 16 | **10**（composite/XML/external_target_sync/canonical_row_hash 等待后续阶段） |

权威核对：

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules
# 输出须与 tests/architecture_baseline.py 一致
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_architecture.py -m unit -q
```

## 4. §3 路径预算偏差（定向修订风险）

以下文件在 §3 S1 预算中列出，**HEAD 上尚无独立模块**（或仅部分等价迁移）：

| 预算路径 | 状态 | 实际替代 |
| --- | --- | --- |
| `application/job_steps.py` | 未创建 | step 逻辑仍在各 job 模块 + `application/job_definitions.py` |
| `application/pair_pipeline.py` | 未创建 | `_run_pair_pipeline` 仍内联于 `preview_jobs.py`、`history/compare_jobs.py` |
| `application/workspace/upload_admission.py` | 未创建 | 上传受理仍在 `http/orchestration/*` + staging capability |
| `application/submission/artifact_release.py` | 未创建 | 释放逻辑仍在 submission 模块内 |
| `application/workspace/ports.py` | 未创建 | 仍使用 `domain/workspace/ports.py` |

行为与 checkpoint 载荷未改；偏差需在独立审核中显式接受或要求补提交。

## 5. 装配与测试注入（synthetic / worker）

- `application/synthetic_jobs.py`、`external_effect_stub` 已移至 `tests/support/`；`operation_worker` 不再默认装配 synthetic recovery。
- Worker 集成测试通过 harness 注入 recovery port（见 `test_operation_job_synthetic.py` 等）；**断言未改**。

## 6. 门禁命令与结果

### 6.1 五包静态（@ `7de23ed349`）

```bash
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

结果：**五包均 pass**（2026-09-27）。

### 6.2 权威全量测试

```bash
cd /home/dev/gdds-p5-closure-s1
# 可选：ln -sf /home/dev/gateway-data-management-system/legacy legacy
# （table_rules legacy oracle 依赖 repo 根下 legacy/backend_vnext，不在 git 中；与 P3-R5/R7 handoff 已知缺口一致）
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

结果：**见本节末尾更新块**（运行中勿用 `| tail` 包裹，会阻塞 pytest 输出）。

### 6.3 镜像重建与 compose（§6 / 与 5E exit 对齐）

S1 要求 current HEAD fresh 构建并跑既有 compose 旅程。`build-repository-service-image.sh` 与 compose provenance **要求 worktree clean**（不含未跟踪 `legacy/`  symlink）。

计划命令（在 **clean** @ `7de23ed349` 上）：

```bash
cd /home/dev/gdds-p5-closure-s1
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
# repository_service 串行 8 项 compose e2e（run-tests.sh serial 批次同集）
cd vnext/repository_service && ../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_import_compose_e2e.py \
  tests/test_versioned_read_compose_e2e.py \
  tests/test_compose_lifecycle_negative_probes.py
```

`vnext/deploy/compose.yaml` SHA-256（与 5D/5E 记录一致）：

`f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0`

**镜像 / compose 证据**：见下方「更新块」（提交 handoff 前填入 image ID、8/8 pass）。

### 6.4 已知环境项

- **`uv.lock` 污染**：`a5a62e58d3` 曾误提交 LAN mirror lock；已在 `7de23ed349` 恢复。后续仅通过 `uv-consume.sh` 消费依赖。
- **legacy oracle**：`tests/test_table_rules_resolver.py`（58 项）需要主机上 `legacy/backend_vnext/`（主工作区已有；S1 worktree 需 symlink 或拷贝）。无 legacy 时失败为 **已知外部 fixture 缺口**，非 S1 回归。

## 7. 请 reviewer 重点核对

1. import 终态是否与 §2 S1 完全一致（3/0/10 + DC26 单条放行）。
2. §3 五项缺失路径是否接受当前等价实现，或要求补 `job_steps` / `pair_pipeline` 等。
3. kickoff 普查负结果是否未 overstated 为 S2a 类型决策证据。
4. synthetic 移出生产包后 worker 测试注入是否仅装配变化、无行为变化。
5. `7de23ed349` 上全量测试 + clean worktree compose 8/8 + 三镜像 fresh build 证据是否齐备。

## 8. 审核提示词（§8.7）

```text
独立审核 P5 架构收口 S1：对象为 p5-closure/s1 @ 7de23ed3498ac4914ec2a15684a648f2d90aa4fd（base main @ e04c1bcca7d17d1f7e1feda9b8329a4503942d6b）与 plans/p5-arch-closure-s1-handoff.md。
按执行计划 §2 S1 的验收、§3 S1 预算与纵切指南 §6 给出结论。
必须核查：import 3/0/10；§4 路径偏差；kickoff DC12/DC15；synthetic 注入；全量测试与 compose 镜像 provenance（handoff §6）。
```

## 9. 更新块（阶段门禁收尾 @ `450e15e548`）

| 项 | 值 |
| --- | --- |
| 五包 ruff + mypy | pass @ `7de23ed349` |
| `run-tests.sh` @ `450e15e548`（含 legacy symlink 时） | shared_kernel 242、repository_contracts 152、repository_client 154、backend **2665 passed**（9 个 backend compose 因 **handoff 未提交导致 worktree dirty** 失败，非代码回归）、repository_service 并行 1678（1 skipped）、串行 **197 passed**（8 compose 同样 dirty 失败） |
| legacy oracle | 未跟踪 `legacy/` symlink 指向主工作区 `legacy/backend_vnext`；无 symlink 时 `test_table_rules_resolver` 58 项失败为已知缺口 |
| repository_service compose 8/8 | pass @ `450e15e548`，`-n 0`，164s；镜像 `gateway-repository-service:local` **`sha256:37df612e38c700cf6c0d1acfb54854dc1acb89024900e004e8f95d3a842cc14d`** |
| backend compose 9/9 | pass @ `450e15e548`，1069s；`deploy-backend:latest` **`6610f2c6b7f0`**、`deploy-worker:latest` **`9e1672eca5e4`**（compose build @ 同 HEAD） |
| worktree clean at compose gate | yes（handoff 已提交；compose 前无未跟踪 `legacy/`） |

**说明**：权威 `run-tests.sh` 与 compose provenance 对 worktree 洁净性要求冲突（table_rules 需要 legacy 目录）。阶段验收采用：**全量 runner 覆盖非 compose 批次 + clean worktree 上单独重跑 RS 8 + backend 9 compose**（与执行计划 §8.6 基线做法一致）。

---

_next_step: 独立审核 `p5-arch-closure-s1` @ `450e15e548`；结论 pass 后 `--no-ff` 合入 main，再进入 S2a。_
