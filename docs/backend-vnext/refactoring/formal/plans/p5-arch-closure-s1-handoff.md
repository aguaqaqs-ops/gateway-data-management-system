# P5 架构收口 S1 Handoff

状态：**S1 复审定向修订完成，待独立复审（rereview-1 关闭项）**

日期：2026-09-28

Owner：P5 Architecture Closure

Worktree：`/home/dev/gdds-p5-closure-s1`  
分支：`p5-closure/s1`

## Traceability

```yaml
stage: P5-arch-closure-S1-structure
authorized_base: 218c211240b33e01eee1eb8965fdcca0ec4b8099  # main @ 授权基线（merge-base 一致）
implementation_fork: e04c1bcca7d17d1f7e1feda9b8329a4503942d6b  # S1 实现切点
merge_base_with_main: 218c211240b33e01eee1eb8965fdcca0ec4b8099
implementation_head: 72092dd27af85dc235e1d08c2650297508b5e49e  # 定向修订代码 tip；镜像/build 绑定此 SHA
candidate_ref: p5-closure/s1  # reviewer 开始时解析分支 tip；不引用被 amend 移除的 commit object
source_tree_sha: 7a017a4cbb97c8fce3cbc2bcae0f105bdc8d5db7  # implementation_head^{tree}
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

2026-09-28 的物化与重复键普查产出 `$GATEWAY_REAL_DUMP_ROOT/census/summary.json`（`diagnostic_mode: true`）。2026-10-10 用修正后的类型规范化函数重新解析 8 份 SQL DDL，确认并拆分 `UNSIGNED` 类型计数；同日又对 t1 两个版本重跑 `census_one`，确认重复键与有效键统计一致。逐 dataset 的结构记录现保存在仓库内的 [S1 census JSON](p5-arch-closure-s1-census.json)：含 package bytes/SHA、pairing、DDL 与物化表数、行数、角色分布、完整非 SKIP 列类型计数、词表外/JSON/可空键列/无键表清单、`saved_time`、XML 结果、重复键与有效键扫描状态；不含行数据和主机路径。

- **DC12**：`dc12_json_columns_present: false` → **未触发** LONGTEXT。
- **DC15**：存储表列类型含 `INT UNSIGNED`、`TINYINT UNSIGNED`、`SMALLINT UNSIGNED`、`FLOAT`、`DATETIME` 等（各数据集的完整计数见 census JSON）；`unknown_sql_types` 为空（mapper 已识别拼写）→ **已触发**词表扩充需求，S2a 验收扩充并与 Dolt 往返对齐；FLOAT 无损往返优先在 S2a 验证（设计 §14 第 2 项）。
- **重复键（诊断 READERS_REQUIRED）**：t1 两份数据各有 `b1_n2_iec104_syx_list` 3 条额外行。t2/t3/t4 物化失败，重复键扫描状态是未评估，不能把空 map/0 解释成未检出。
- **有效键（DDL 无主键表）**：t1 每份均有 28 张无 DDL 主键表；5 张由 EXPLICIT 规则给出有效键（`app_cfg.app_name`、`b1_n1_iec61850c_cfg(page_no,no)`、`b1_n2_iec104_cfg(page_no,no)`、`pointref_forwardtbl.refname`、`rdb_cfg.no`），其余 23 张无法解析有效键。t2/t3/t4 物化失败，重复键与物化表有效键扫描状态均标为未评估；不把空 map/0 解释为没有重复或全部有效。parser 修复后，在 S2a kickoff 完成这 6 份的有效键与重复键复查，再进入 DC22 真实数据旅程。

### 八数据集结构记录（诊断模式，无行数据）

`pair_of` 默认规则见 `$GATEWAY_REAL_DUMP_ROOT/dataset_pairing.json`（tier 内 v1→v2）。**Owner 确认（2026-09-28）**：沿用默认 pairing，与执行计划 §8.3、`p5-arch-closure-s0-owner-decisions.md` §4 一致，S2b/S4 同项目链路验收以此为准。

| Dataset | Pair | Package bytes / SHA-256 | Staging / materialization | DDL tables | Materialized tables / rows | No DDL PK | Duplicate scan | Effective-key scan |
| --- | --- | --- | --- | ---: | --- | ---: | --- | --- |
| `rd-t1-a-v1` | — | 107115 / `42794011…95ea8b2` | COMPLETE / COMPLETE | 132 | 133 / 6097 | 28 | complete; 3 extra rows in `b1_n2_iec104_syx_list` | partial; 102 keyed, 23 unresolved, 0 keyless |
| `rd-t1-a-v2` | `rd-t1-a-v1` | 107066 / `4019737…095bd0` | COMPLETE / COMPLETE | 132 | 133 / 6095 | 28 | complete; 3 extra rows in `b1_n2_iec104_syx_list` | partial; 102 keyed, 23 unresolved, 0 keyless |
| `rd-t2-b-v1` | — | 1247459 / `acd1b5e…3817c0` | COMPLETE / FAILED `COMPOSITE_LOGIC_FAILED` | 216 | unavailable / unavailable | 40 | not evaluated | not evaluated; S2a after parser repair |
| `rd-t2-b-v2` | `rd-t2-b-v1` | 1197404 / `c66e3921…5fcba98` | COMPLETE / FAILED `COMPOSITE_LOGIC_FAILED` | 216 | unavailable / unavailable | 40 | not evaluated | not evaluated; S2a after parser repair |
| `rd-t3-c-v1` | — | 3356815 / `c34e266c…15eec7e` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 199 | unavailable / unavailable | 37 | not evaluated | not evaluated; S2a after parser repair |
| `rd-t3-c-v2` | `rd-t3-c-v1` | 3370171 / `658422ef…cffc28d` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 200 | unavailable / unavailable | 38 | not evaluated | not evaluated; S2a after parser repair |
| `rd-t4-d-v1` | — | 5597503 / `95408cc3…5da1675` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 319 | unavailable / unavailable | 59 | not evaluated | not evaluated; S2a after parser repair |
| `rd-t4-d-v2` | `rd-t4-d-v1` | 5596595 / `5a7cd54d…ee3611` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 319 | unavailable / unavailable | 59 | not evaluated | not evaluated; S2a after parser repair |

t1 的 133 个物化表包含 132 个源 DDL 表和 1 个 XML composite 表。t2 `logics.xml` complete，events=3158；t3/t4 `logics.xml` failed（`XML_DOCUMENT_FAILED`，`max_xml_depth=64`），非 S1 引入。8 份 `version_manager.saved_time` 均为 `VARCHAR(128)`；unknown types、JSON 列、可空键列均为空。每份完整的 UNSIGNED 类型计数、SHA 与无键表清单见上方 JSON。

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
| Preview/History 受理下沉、UoW 枢纽拆分、三 job 共享 step plumbing | **延期 S2b**（执行计划 §3「S2b — S1 复审延期路径」、§8.5 S2b.0；owner 2026-09-27） |

**S1-F3 三项延期（逐项）**

| 延期项 | 现状（@ 复审定向修订） | 理由 | S2b 目标 |
| --- | --- | --- | --- |
| Preview/History 受理下沉 | HTTP `preview_acceptance` / `history_compare` 仍承担 DTO 映射与编排 | S1 行为不变；避免与 N-http 迁移交叉 | Application/workspace + history 用例拥有受理；HTTP 薄路由 |
| UoW 枢纽拆分 | `control_transactions.py` + 各 `*/ports.py` 已引入共享协议，SQLite 仍集中 | 需与 S2b control DB migration 同批 | 按 owner 拆分写模型；Submit/Preview/History 各端口稳定 |
| 三 job 共享 step plumbing | `job_steps.py` 已建；`pinned_checkpoint_builder` 已删 | checkpoint 载荷冻结 | §8.5 S2b.0 统一 step 辅助与 recovery 接线 |
| `table_access` parser（`@saved_cs_client`、`max_xml_depth`） | **S1–S2a 前置**分支 `p5-closure/s1-parser`（执行计划 §1/§8；不改 `table_access` 生产源码于本修订） |

checkpoint 载荷与 golden 断言策略未改（F1 证据字节已与 base 对齐）。

## 4. import_rules（§2 S1 机械验收）

| 指标 | fork @ `e04c1bcca7` | @ 复审定向修订 `implementation_head` |
| --- | --- | --- |
| 违例 | 54 | **3**（http_arrow×2 + `repository_import_artifact`；上传上限在 `application/workspace/upload_limits.py`） |
| 运行时环 | 8 | **0** |
| 不可达 | 16 | **14** |

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_architecture.py -m unit -q
# 2026-10-10：import_rules 3/0/14；facade 符号导入形态用例与架构 unit 结果见本次验证记录

**Owner 确认（2026-10-10）**：按真实符号级可达性采用 14 项不可达基线；`composite_signal._ast`、`_bind`、`_digest`、`materialize` 四项保留为 S3 延期，S3 接入其生产调用方后关闭。执行计划 §2 S1 验收、S2a 预期和 `architecture_baseline.py` 已同步。
```

## 5. synthetic / worker 装配

- Synthetic 与 external effect stub 在 `tests/support/`；worker 测试侧注入 recovery（断言不变）。

### 5.1 只改导入路径的测试（S1 预算）

下列测试仅随模块迁移更新 import，**不断言行为变更**（见执行计划 §3 S1 必改 T）：

- `test_synthetic_w2.py`、`test_operation_job_synthetic.py`、`test_operation_job_recovery.py`、`test_operation_effect_reconcile.py`、`test_operation_worker_integration.py`
- `test_canonical_row_hash.py`
- `test_submit_job_payload.py`、`test_submit_job_effect.py`、`test_submit_job_prepare.py` 中的 `canonical_import_request_bytes` 测试桩（共 3 处；复审意见所称 4 处在当前测试树中未找到）
- 其余由被迁移模块 import 方决定的同型用例（handoff 不逐文件重复列举时，以 execution-plan §3 S1 必改 T 为准）

## 6. 门禁命令与结果（@ `implementation_head`，compose/backend 在 clean worktree）

日志目录：**`/home/dev/gdds-p5-closure-s1/gate-logs/`**（持久路径；禁止引用不存在的 `/tmp/...` 占位）。

### 6.1 五包静态

```bash
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
```

结果：**五包 ruff 与 mypy 全部 pass**（2026-10-10，本轮复跑；见 `gate-logs/static-check.log`）。

### 6.2 权威全量测试

前置：detached worktree 需 `legacy` → 主工作区 `legacy/`（gitignore `/legacy/`；symlink 在 worktree 用 `.git/info/exclude` 追加 `legacy` 以保持 porcelain 空，见 `internal-build-environment-handoff.md`）。

```bash
cd /home/dev/gdds-p5-closure-s1
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh 2>&1 | tee gate-logs/run-tests.log
```

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | **2691 passed**, 1 warning |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | **205 passed** |
| 五锁 SHA 漂移 | 无 |
| runner exit | **0** |

完整日志：`gate-logs/run-tests-rereview.log`（2026-09-28；`GATEWAY_TEST_WORKERS=48`，porcelain 干净后重跑）。

### 6.3 镜像 fresh build（§6 S1 @ `implementation_head`）

```bash
cd /home/dev/gdds-p5-closure-s1  # git status --porcelain 为空
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

| 镜像 | ID / digest |
| --- | --- |
| `gateway-repository-service:local` | `sha256:2fe98a0f97ce3ee425f2ac5386f87011e33f91841ef1863e5f6be75b6fbcd2df` |
| `deploy-backend:latest` | `sha256:b8def66665452d093f6df2965b1957b8a11c08464c52fedb2360a88efd4e3938` |
| `deploy-worker:latest` | `sha256:833a8ee064b043da930a29b2173b44aa4a9eebcbb6d8aa45b8ab1fd1cf843776` |

构建日志：`gate-logs/build-rs-image.log`；compose build @ `41c43909be`（含 `gate-logs/` gitignore，保证 provenance 干净 worktree）。

镜像构建身份：compose build 的 Git commit/tree 为 `41c43909be5dd0a6b7bebeb8fef9c77e8a2ee6cb` / `814b082c88acd2128efcafbda1989d813476b1b5`。RS image labels 记录 `org.opencontainers.image.revision=41c43909be5dd0a6b7bebeb8fef9c77e8a2ee6cb`、`gateway.p2r1.build-input-revision=4d1dc010deff17249bb2aa54b7563e7a86959096`、`gateway.p2r1.source-tree-sha256=sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf`。

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

结果：**9 passed**, 1 warning, ~1145s（2026-09-28）。日志：`gate-logs/backend-compose-9-r2.log`。

**注意**：跑 9 旅程前须 `docker compose … down -v`，确保 8000 无残留 gate 容器；否则前序 `require_docker()` 用例会误报 port 冲突。

Compose provenance：`vnext/backend/tests/support/.last_compose_gate_provenance.json`（末次 archive 旅程写入）。旅程实际使用 backend image `sha256:b6795948fb268f6b0b6ab4f7b822d839881ac495678a2adb3be65f2a0c34e39f`、worker image `sha256:a6234eee385029afad6f2ebd130055f0ba834df6479b38e225f014581a6ce5c6`、RS image `sha256:2fe98a0f97ce3ee425f2ac5386f87011e33f91841ef1863e5f6be75b6fbcd2df`；compose build 引用 `deploy-backend`/`deploy-worker`，gate harness 为隔离项目构造同源项目镜像。

### 6.5 本轮复审修订定向验证（2026-10-10）

- `python -m tests.support.import_rules`：**3 / 0 / 14**。
- `pytest -m unit -q tests/test_architecture.py tests/test_real_dump_census.py tests/test_submit_job_payload.py tests/test_submit_job_prepare.py tests/test_submit_job_effect.py`：**126 passed, 16 deselected**。
- 五包 ruff/mypy：全部通过，见 `gate-logs/static-check.log`。
- focused 输出：`gate-logs/focused-rereview-repairs.log`。
- 本轮只修改架构审计工具、主机侧普查脚本、测试与 handoff/执行计划；未改 HTTP/worker、Dockerfile、Compose 或容器运行时边界。`implementation_head..41c43909be` 的 backend/repository_service 源码与测试无差异；S1-F11 所需的镜像与全量测试证据在 §6.2–§6.4。此轮不声明 S1 阶段退出；owner 批准退出前仍须按 AGENTS.md 在最终 candidate HEAD 重建镜像并运行阶段 compose 门禁。

## 7. 请 reviewer 重点核对

1. import 3/0/14；4 个 composite facade 实现模块按符号级可达性登记为 S3 延期；DC26 仅对 `capability:canonical_row_hash → ext:compute` 放行。
2. §3 模块已落地；job 模块仅薄包装、checkpoint 载荷未变。
3. kickoff 普查负结果未 overstated 为 S2a 类型决策。
4. merge `218c211240` 仅文档模板，无实现冲突。
5. 门禁绑定 **`implementation_head`** 镜像 rebuild；handoff 为 docs-only 提交。

## 8. 审核提示词（§8.7）

reviewer 开始时解析 `candidate_ref` 的分支 tip，再依执行计划 §8.8 模板生成本轮审核提示词。

---

## 修订（2026-09-28，审核 `a35b2ad8dd` → `implementation_head`）

独立审核报告：`p5-arch-closure-s1-independent-review.md`（**未改**）。

| Finding | 状态 | 提交 / 说明 |
| --- | --- | --- |
| S1-F1 FAILED 证据 | 已关闭 | `d5d5a7542d`、`f6386588e4` 恢复 golden；`61f6d03216` 接入 wire codec 严格解码 port；拒绝表覆盖 7 类 wire 约束 |
| S1-F2 History OpenAPI | 已关闭 | `6f61a05266`：本地 `CommitIdString` 约束 |
| S1-F3 三项延期 | 已登记 | `6279226393`：删 `job_steps.pinned_checkpoint_builder`；执行计划 S2b/§8.5/§1 parser 前置 |
| S1-F4 shim + DAG | 已关闭 | `022e84fbd5`：`import_rules` 函数内 `__init__` import；compose facade；`import_rules` **4/0/10**（含 F7 层） |
| S1-F5 baseline 治理 | 已关闭 | `de05056950`：baseline 头与条目标注；设计 §9 / owner §9 延期登记 |
| S1-F6 普查 | 已关闭（完整记录；失败物化的键扫描明确延期） | §1 与 `p5-arch-closure-s1-census.json`；t1 duplicate/effective-key 明细，t2–t4 未评估状态及 S2a 承接节点；pair_of owner 确认 |
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
- `backend -m unit`：原记录为 **2513 passed**，但当时引用的 `/home/dev/gdds-p5-closure-s1-gate-logs/backend-unit.log` 当前不存在；该数字不作为本轮可验证证据。
- 全量 `run-tests.sh`：原记录引用的 `/home/dev/gdds-p5-closure-s1-gate-logs/run-tests-r2.log` 当前不存在，且记录曾提示 backend compose 失败、需要当前镜像重跑；该轮结果不作为验收证据。有效的全量运行记录见 §6.2 `gate-logs/run-tests-rereview.log`，compose 结果见 §6.4。
- 镜像：`gateway-repository-service:local` digest `sha256:bffceac8e02245bebb67dfd4ab82fb73d2d017e09da4dbe605a113e78ff9c96e`（`c434064c7d` 标记）；`deploy-backend`/`deploy-worker` compose build @ 修订日（层多为 cache，compose 旅程须串行重证）。

### §8.7 原复审提示词（审核对象 `1897d5df46`）

```text
任务：独立复审 P5 架构收口 S1 的修订。你没有参与 S1 的实现与修订；按纵切指南 §7 复审。
审核对象：p5-closure/s1 @ 1897d5df46f543b645058d7e3ac0f8909426725a；上次审核对象 @ a35b2ad8dd，报告 plans/p5-arch-closure-s1-independent-review.md。
  只核对 a35b2ad8dd..1897d5df46f543b645058d7e3ac0f8909426725a 的修订差异、原 finding 的关闭情况与改动传播；已关闭且未受影响的问题不重开。
  实现 HEAD（镜像构建点）：2a54214df94321f97ee936062b5539836f6ea0f5。
验证：修订涉及的 focused 测试；修订触碰 §6 的镜像边界时，核对新的镜像记录。测试运行期间不在该 worktree 写入任何文件。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-s1-independent-rereview-1.md，作为单独提交加到 p5-closure/s1；
  除该报告外不修改任何文件；不合并、不推送。
审核允许结论：通过 / 定向修订 / 整体返工。
```

---

## 复审定向修订（rereview-1 关闭项，2026-09-28）

| Finding | 处理 |
| --- | --- |
| S1-F10 | `upload_limits` 叶子模块；三处运行时环拆解；`RUNTIME_CYCLE_BASELINE=()`；**3/0/14** |
| S1-F4 | 删除包级 facade 扩展；只在可达模块导入 wrapper symbol 时展开其惰性导入；4 个 composite 实现模块按 owner 确认登记为 S3 延期；添加导入/未导入双向形态用例 |
| S1-F1 | `RepositoryTerminalEvidenceDecodePort` + `WireRepositoryTerminalEvidenceDecodePort`；删 application 宽 schema；`MALFORMED_TERMINAL_EVIDENCE_SHAPES` 扩展 |
| S1-F6 | 修正 UNSIGNED 分布；§1 八数据集结构记录与 JSON companion；t1 duplicate/effective-key 统计；t2–t4 明示未评估并登记 S2a；pair_of owner 确认 |
| S1-F3 | 执行计划 §3「S2b — S1 复审延期路径」；handoff §3 逐项延期表 |
| S1-F8 | §4 **3/0/14**；§5.1 列出真实存在的 3 个 `canonical_import_request_bytes` 测试桩；§6 `gate-logs/` 与实际容器镜像 provenance；candidate 改用 branch ref |
| S1-F11 | 见 §6.2–§6.4（`gate-logs/run-tests-rereview.log`、fresh image build 与实际 compose provenance/9 旅程） |

_next_step：独立复审 rereview-1 通过后 `--no-ff` 合入 `main`，进入 S2a（含 parser 前置与 S2b 延期项）。_
