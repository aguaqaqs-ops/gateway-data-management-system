# P5 架构收口 S1 Handoff

状态：**S1 closure ready for independent review**

日期：2026-09-27

Owner：P5 Architecture Closure

Worktree：`/home/dev/gdds-p5-closure-s1`  
分支：`p5-closure/s1`

## Traceability

```yaml
stage: P5-arch-closure-S1-structure
authorized_base: 218c211240b33e01eee1eb8965fdcca0ec4b8099  # main @ 授权基线（merge-base 一致）
implementation_fork: e04c1bcca7d17d1f7e1feda9b8329a4503942d6b  # S1 实现切点
merge_base_with_main: 218c211240b33e01eee1eb8965fdcca0ec4b8099
implementation_head: 1caf2ffc26f690188f8311904bce24693fb61d43  # 最后代码提交（merge 授权 main §8 模板，无实现冲突）
candidate_head: 7b0db60b441d9a4f9922aecbf6b4219f4274e154
source_tree_sha: 6ac8db947335661d182e9f8d37ed0e9df0c9735f  # implementation_head^{tree}
uv_lock_in_diff: no  # 7de23ed349 恢复 canonical PyPI identity
implementation_authority: execution-plan §8.4 S1.1–S1.7
design_§14_stop: not_triggered
```

## 1. S1 kickoff — 真实数据普查（DC22 / DC12 / DC15）

- 脚本：`vnext/backend/benchmarks/real_dump_census.py`（`2c0d49fae9`）。
- 命令：

```bash
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py
```

- 产出：主机侧 `$GATEWAY_REAL_DUMP_ROOT/packages/`、`datasets.json`、`census/summary.json`（不入库）。
- **pair_of**：每 tier 内 `*-1` → `*-2` 同项目前后版本；t1–t4 为不同项目 alias（a–d）。
- **DC12**：八样本 `json_columns` 为空 → **未触发** LONGTEXT；S2a 仍 fail-closed JSON。
- **DC15**：八样本 `unknown_types` 为空 → **未触发** 词表扩充。
- **普查局限**：SQL 多为 `UNSUPPORTED_STATEMENT`；business materialization 多 FAILED；结构统计多为空——**不得**当作 S2a 强证据。

## 2. 子步 ↔ 提交

| 子步 | 提交 | 摘要 |
| --- | --- | --- |
| kickoff | `2c0d49fae9` | `real_dump_census.py` |
| S1.1 | `eb4ccfb863` | dead 模块；synthetic → T/support |
| S1.2 | `69d6b82632`, `7d9ee45e2b` | canonical row hash + DC26 |
| S1.3–S1.4 | `a5a62e58d3` | wire_codec、composition、facade |
| S1.5–S1.6 | `d42a740e7d` | control_transactions、pair_pipeline、job_steps、upload_admission、artifact_release、workspace/ports |
| S1.7 | `d97428ed22`, `7de23ed349` | import 终态；lock/wire 修复 |
| merge 授权基线 | `1caf2ffc26` | merge `main @ 218c211240`（§8 审核/复审模板） |
| handoff | （本提交） | 门禁证据与 traceability |

## 3. §3 S1 路径预算（已闭合）

| 预算路径 | 状态 |
| --- | --- |
| `application/job_steps.py` | 已创建 |
| `application/pair_pipeline.py` | 已创建；Preview/History 薄包装 `_run_pair_pipeline` |
| `application/workspace/upload_admission.py` | 已创建；HTTP `source_package_admission` 重导出 |
| `application/submission/artifact_release.py` | 已创建 |
| `application/workspace/ports.py` | 已创建（domain port 别名） |
| `application/control_transactions.py` | 已创建 |

无 §3 定向偏差；checkpoint 载荷与 golden 断言策略未改。

## 4. import_rules（§2 S1 机械验收）

| 指标 | fork @ `e04c1bcca7` | @ `implementation_head` |
| --- | --- | --- |
| 违例 | 54 | **3**（http_arrow×2 + `repository_import_artifact`，S2b 关闭） |
| 运行时环 | 8 | **0** |
| 不可达 | 16 | **10** |

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_architecture.py -m unit -q
# 2026-09-27：71 passed
```

## 5. synthetic / worker 装配

- Synthetic 与 external effect stub 在 `tests/support/`；worker 测试侧注入 recovery（断言不变）。

## 6. 门禁命令与结果（@ `implementation_head`，compose/backend 在 clean worktree）

### 6.1 五包静态

```bash
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

结果：**五包均 pass**（2026-09-27）。

### 6.2 权威全量测试

前置：detached worktree 需 `legacy` → 主工作区 `legacy/`（gitignore `/legacy/`；symlink 在 worktree 用 `.git/info/exclude` 追加 `legacy` 以保持 porcelain 空，见 `internal-build-environment-handoff.md`）。

```bash
cd /home/dev/gdds-p5-closure-s1
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | **2674 passed**, 1 warning |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial, 含 RS compose 8) | **205 passed** |
| 五锁 SHA 漂移 | 无（runner 末尾 lock assert pass） |
| runner exit | **0** |

日志：`/tmp/s1-run-tests-final.log`。**勿**用 `| tail` 包裹 runner。

### 6.3 镜像 fresh build（§6 S1 @ `implementation_head`）

```bash
cd /home/dev/gdds-p5-closure-s1  # git status --porcelain 为空
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

| 镜像 | ID / digest |
| --- | --- |
| `gateway-repository-service:local` | `sha256:f4957f1a61159af0dc29cd8e21b2b3f3b568b9754d56141a51e59714ef81f520` |
| `deploy-backend:latest` | `6610f2c6b7f0` |
| `deploy-worker:latest` | `9e1672eca5e4` |

`vnext/deploy/compose.yaml` SHA-256：`f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0`

五锁 SHA-256（与 runner 一致）：

- shared_kernel `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898`
- repository_contracts `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3`
- repository_client `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`
- repository_service `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`
- backend `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea`

### 6.4 Backend compose 旅程（9/9，clean worktree）

```bash
cd vnext/backend
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-closure-s1-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
GATEWAY_COMPOSE_GATE_PREBUILT=0 \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_archive_compose_e2e.py \
  tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py \
  tests/test_backend_http_container_gate.py \
  tests/test_history_compose_e2e.py \
  tests/test_ordered_compare_compose.py \
  tests/test_ordered_submit_bisect_compose.py
```

结果：**9 passed**, 1 warning, ~1074s。日志：`/tmp/s1-backend-compose.log`。

## 7. 请 reviewer 重点核对

1. import 3/0/10 与 DC26 单条 `capability:canonical_row_hash → ext:compute` 放行。
2. §3 模块已落地；job 模块仅薄包装、checkpoint 载荷未变。
3. kickoff 普查负结果未 overstated 为 S2a 类型决策。
4. merge `218c211240` 仅文档模板，无实现冲突。
5. 门禁绑定 **`implementation_head`** 镜像 rebuild；handoff 为 docs-only 提交。

## 8. 审核提示词（§8.7，除分支末端 SHA 外已填）

见实现方最终回复中的审核块（分支末端 SHA = `candidate_head`）。

---

_next_step：独立审核通过后 `--no-ff` 合入 `main`，进入 S2a。_
