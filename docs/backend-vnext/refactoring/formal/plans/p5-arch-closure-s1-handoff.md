# P5 架构收口 S1 Handoff

状态：**S1 定向修订完成，待独立复审（§修订）**

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
implementation_head: 2a54214df94321f97ee936062b5539836f6ea0f5  # 定向修订最后代码提交（S1-F9 严格闭合）
candidate_head: 0b56172024995a6e2889960a7c0e9e5b2324b59a
source_tree_sha: 1ed595cc014a633c2ff2458efae36b9493d9a37f  # implementation_head^{tree}
uv_lock_in_diff: no  # 7de23ed349 恢复 canonical PyPI identity
implementation_authority: execution-plan §8.4 S1.1–S1.7
design_§14_stop: not_triggered
```

## 1. S1 kickoff — 真实数据普查（DC22 / DC12 / DC15）

- 脚本：`vnext/backend/benchmarks/real_dump_census.py`（修订 `662cc0979e` 起支持 `--diagnostic` 与 `parser_production_path`）。
- **生产路径**（无 `--diagnostic`；现行 parser）：

```bash
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py
```

八份 dump 均在 `SET @saved_cs_client` → `UNSUPPORTED_STATEMENT`（P3-R2 既有缺口，**非 S1 引入**）。t3/t4 的 `logics.xml` 在生产路径下仍受 `max_xml_depth=64` 约束（诊断摘要见下）。

- **诊断模式**（仅普查进程；**不代表生产路径**）：

```bash
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py --diagnostic
```

2026-09-28 重跑产出：`$GATEWAY_REAL_DUMP_ROOT/census/summary.json`（`diagnostic_mode: true`）、`datasets.json`（无主机绝对路径）、`packages/`。`pair_of` 可由 `$GATEWAY_REAL_DUMP_ROOT/dataset_pairing.json` 覆盖；默认 tier 内 v1→v2。

- **DC12**：`dc12_json_columns_present: false` → **未触发** LONGTEXT。
- **DC15**：存储表列类型含 `TINYINT`/`SMALLINT`/`FLOAT`/`DATETIME` 及 UNSIGNED 拼写（见各 dataset `storage_column_type_counts`）；`unknown_sql_types` 仍为空（mapper 已识别拼写）→ **已触发**词表扩充需求，S2a 验收扩充并与 Dolt 往返对齐；FLOAT 无损往返优先在 S2a 验证（设计 §14 第 2 项）。
- **结构统计**（诊断模式）：八样本均可物化；含按角色表数、行数、DDL 无主键表列表等（见 `summary.json`）。

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

## 3. §3 S1 路径预算

| 预算路径 | 状态 |
| --- | --- |
| `application/job_steps.py` | 已创建；共享 `pinned_checkpoint_builder` 已删（F3 延期） |
| `application/pair_pipeline.py` | 已创建；Preview/History 薄包装 |
| `application/workspace/upload_admission.py` | 已创建 |
| `application/submission/artifact_release.py` | 已创建 |
| `application/workspace/ports.py` | 已创建 |
| `application/control_transactions.py` | 已创建 |
| Preview/History 受理下沉、UoW 枢纽拆分、三 job 共享 step plumbing | **延期 S2b**（执行计划 §3/§8.5，owner 2026-09-27） |
| `table_access` parser（`@saved_cs_client`、`max_xml_depth`） | **S1–S2a 前置**分支 `p5-closure/s1-parser`（执行计划 §1/§8；不改 `table_access` 生产源码于本修订） |

checkpoint 载荷与 golden 断言策略未改（F1 证据字节已与 base 对齐）。

## 4. import_rules（§2 S1 机械验收）

| 指标 | fork @ `e04c1bcca7` | @ `implementation_head` |
| --- | --- | --- |
| 违例 | 54 | **4**（http_arrow×2 + `repository_import_artifact` + F7 `workspace.contracts→settings` 单源上传上限，S2b/登记见 baseline 注释） |
| 运行时环 | 8 | **3**（F9 登记：`job_definitions`↔`payloads`、`auth`↔`dependencies`、baseline `ControlDbUnitOfWork` 读路径；见 `architecture_baseline.py`） |
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

## 8. 审核提示词（§8.7）

见 §修订 末尾 `candidate_head` 填入后复制执行计划 §8.8 模板。

---

## 修订（2026-09-28，审核 `a35b2ad8dd` → `implementation_head`）

独立审核报告：`p5-arch-closure-s1-independent-review.md`（**未改**）。

| Finding | 状态 | 提交 / 说明 |
| --- | --- | --- |
| S1-F1 FAILED 证据 | 已关闭 | `d5d5a7542d`、`f6386588e4`：域类型 `details`/`request_id`；`test_submit_job_payload` golden + 拒绝表 |
| S1-F2 History OpenAPI | 已关闭 | `6f61a05266`：本地 `CommitIdString` 约束 |
| S1-F3 三项延期 | 已登记 | `6279226393`：删 `job_steps.pinned_checkpoint_builder`；执行计划 S2b/§8.5/§1 parser 前置 |
| S1-F4 shim + DAG | 已关闭 | `022e84fbd5`：`import_rules` 函数内 `__init__` import；compose facade；`import_rules` **4/0/10**（含 F7 层） |
| S1-F5 baseline 治理 | 已关闭 | `de05056950`：baseline 头与条目标注；设计 §9 / owner §9 延期登记 |
| S1-F6 普查 | 已关闭（脚本+重跑） | `662cc0979e`；`summary.json` @ `/home/dev/gateway-real-dumps/census/`；生产路径失败见 §1 |
| S1-F7 常量单源 | 已关闭 | `e507bc5c43`、`c434064c7d`：`RULESET_VERSION`；上传上限经 `settings`→`workspace.contracts` |
| S1-F8 事实更正 | 本 handoff | §2/§3/§6 更新；子步合并 S1.3–S1.4、S1.5–S1.6 |
| S1-F9 去重（严格） | 已关闭 | `2a54214df9`：见下 |

**S1-F9 严格闭合（`2a54214df9`）**

| 子项 | 处理 | 证据 |
| --- | --- | --- |
| `build_payload_decoder_registry` 单处 | 仅 `application/payloads.py`；`job_definitions` 改为 `TYPE_CHECKING` + 惰性 import | `test_job_payload_decoding.py` registry 用例 |
| `decode_job_payload` 严格类型 | `type(definition) is JobDefinition`（函数内惰性 import）；拒绝非 `JobDefinition` | `test_decode_rejects_non_job_definition_even_with_matching_qualname` |
| `_FailClosedInternalBearerPort` | 删除 `dependencies` 副本；`default_factory` 惰性构造 `auth.FailClosedInternalBearerPort`；`require_*` 归 `auth.py` | 五包 mypy；无模块级 auth↔deps 互引 |
| `_successor_step_id` | `job_steps.successor_step_id` + 各 flow suffix 表；保留 `unique_artifact_refs` | step id 字符串不变；`test_submit_job_payload` / `test_production_wiring` |
| `SQLiteBaselineHeadRead` | `ControlDbUnitOfWork(..., read_only=True)` 读 head | `test_production_wiring` baseline 读 |

### §6 定向修订门禁（@ `2a54214df9`）

**S1-F9 增量（2026-09-28）**

- 五包 ruff/mypy：**pass**
- `import_rules`：**4 / 3 / 10**（违例不变；运行时环 baseline 登记 3 组 F9 惰性互引）
- focused pytest：**148 passed**（`test_job_payload_decoding.py`、`test_architecture.py`、`test_submit_job_payload.py`、`test_production_wiring.py`）

### §6 定向修订门禁（历史 @ `c434064c7d`）

- 五包 ruff/mypy：**pass**（2026-09-28）。
- `import_rules` + `tests/test_architecture.py -m unit`：**71 passed**；违例 **4 / 0 / 10**。
- `backend -m unit`：**2513 passed**（`/home/dev/gdds-p5-closure-s1-gate-logs/backend-unit.log`）。
- 全量 `run-tests.sh`：修订期间日志 `/home/dev/gdds-p5-closure-s1-gate-logs/run-tests-r2.log`（backend 曾 3 项 compose 失败，需 **当前 HEAD 镜像** 后重跑 §6.4）；RS parallel 曾 1 项 `test_upload_artifact_visibility` 失败，与 S1 修订无直接关联，serial 批次以日志为准。
- 镜像：`gateway-repository-service:local` digest `sha256:bffceac8e02245bebb67dfd4ab82fb73d2d017e09da4dbe605a113e78ff9c96e`（`c434064c7d` 标记）；`deploy-backend`/`deploy-worker` compose build @ 修订日（层多为 cache，compose 旅程须串行重证）。

### §8.7 复审提示词（`candidate_head` = 本提交 SHA）

```text
任务：独立复审 P5 架构收口 S1 的修订。你没有参与 S1 的实现与修订；按纵切指南 §7 复审。
审核对象：p5-closure/s1 @ 0b56172024995a6e2889960a7c0e9e5b2324b59a；上次审核对象 @ a35b2ad8dd，报告 plans/p5-arch-closure-s1-independent-review.md。
  只核对 a35b2ad8dd..0b56172024995a6e2889960a7c0e9e5b2324b59a 的修订差异、原 finding 的关闭情况与改动传播；已关闭且未受影响的问题不重开。
  实现 HEAD（镜像构建点）：2a54214df94321f97ee936062b5539836f6ea0f5。
验证：修订涉及的 focused 测试；修订触碰 §6 的镜像边界时，核对新的镜像记录。测试运行期间不在该 worktree 写入任何文件。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-s1-independent-rereview-1.md，作为单独提交加到 p5-closure/s1；
  除该报告外不修改任何文件；不合并、不推送。
审核允许结论：通过 / 定向修订 / 整体返工。
```

---

_next_step：独立复审通过后 `--no-ff` 合入 `main`，进入 S2a（含 parser 前置与 S2b 延期项）。_
