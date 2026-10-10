# P5 架构收口 S1 Handoff

状态：**S1 第 3 次复审候选（H）。最终门禁在合并提交 V `d9c2097612` 上执行：第 3 次完整运行 runner exit 0；前两次运行因 client e2e 测试镜像的构建环境失败，三次运行均已记录（§6.3）。V → H 的镜像身份等价（`carried`）判定见 §6.4，结果在复审提示词与 `final-carried-check.log` 中，不入库。**

修复与复审证据汇总：[S1 第 2 次复审修复报告](p5-arch-closure-s1-rereview-2-repair-report.md)。

日期：2026-10-10

Owner：P5 Architecture Closure

Worktree：`/home/dev/gdds-p5-closure-s1`  
分支：`p5-closure/s1`

## Traceability

```yaml
stage: P5-arch-closure-S1-structure
authorized_base: 218c211240b33e01eee1eb8965fdcca0ec4b8099  # main @ 授权基线（merge-base 一致）
implementation_fork: e04c1bcca7d17d1f7e1feda9b8329a4503942d6b  # S1 实现切点
merge_base_with_main: 5fe02db3a719eb064e3a8fce44b39056afc3321f  # V 合入 main 后的实际 merge-base；授权基线仍为 218c2112
previous_reviewed_head: 96071affd490b728aa62fe4a6f0ee9e784e42466  # 第 2 次复审的 Git HEAD；该次审核对象另含未提交的 census 补丁
previous_reviewed_patch_sha256: 492cce95f9b63849533fbd7be8a0b87d36df546249c8c4ce3e4fbe87ba654b74  # 第 2 次复审时未提交的 census 实现与测试 diff
fix_commit: ce12e245286e367d1e7e86d65a8b3a428cfb813e  # census 脚本与测试（含 reader 不可用 → partial 用例）
implementation_patch_sha256: b5542b162dde170307a464d4fe62028731c2d91db544136714a6c2aebf19875e  # git diff 96071affd4 ce12e24528 -- vnext/
last_committed_implementation_head: ce12e245286e367d1e7e86d65a8b3a428cfb813e  # 最后一个改实现代码的提交；其后的提交（含合入 main）只带入文档
last_committed_source_tree_sha: 6bde540589c1e92bd5093920bfecf52026dd33f5  # ce12e24528^{tree}
docs_commit: a371d55bbe9fdf6f3def570945759b2072c2103b  # 文档修订（决议 §10、handoff、修复报告、census JSON、design/execution plan）
main_merged: 5fe02db3a719eb064e3a8fce44b39056afc3321f  # 合入的 main；只带入文档与 AGENTS.md
candidate_gate: d9c2097612036c05741c98b702d518d54571ece2  # V：合并 main 的提交（tree 4ea3ce28543537375e9c9f7c5fa611362887e052），最终门禁在此提交上执行
candidate: p5-closure/s1  # H：分支 tip（handoff 所在提交，相对 V 只改文档）
candidate_tree_is_committed: true  # owner 于 2026-10-10 撤销“本轮不提交”指令
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

八份 dump 均在 `SET @saved_cs_client` → `UNSUPPORTED_STATEMENT`（P3-R2 既有缺口，**非 S1 引入**）。t3/t4 的 `logics.xml` 在生产路径下仍受 `max_xml_depth=64` 约束（诊断摘要见下）。这两项连同 t2 的 composite 失败，统一由治理修订计划 G2 承接（见本节末“真实数据格式缺口的承接”）。

- **诊断模式**（仅普查进程；**不代表生产路径**）：

```bash
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py --diagnostic
```

2026-09-28 的物化与重复键普查产出 `$GATEWAY_REAL_DUMP_ROOT/census/summary.json`（`diagnostic_mode: true`）。2026-10-10 用修正后的类型规范化函数重新解析 8 份 SQL DDL，确认并拆分 `UNSIGNED` 类型计数；同日重跑 t1 两个版本并只读重跑 t2 两个版本。普查器现会把“已扫描、规则跳过、键未解析、reader 不可用”分别记录；t2 的 `COMPOSITE_LOGIC_FAILED` 不再被误作 SQL 解析失败，诊断模式会单独扫描已成功物化的 SQL 表集合。逐 dataset 的结构记录现保存在仓库内的 [S1 census JSON](p5-arch-closure-s1-census.json)：含 package bytes/SHA、pairing、DDL 与物化表数、行数、角色分布、完整非 SKIP 列类型计数、词表外/JSON/可空键列/无键表清单、`saved_time`、XML 结果、完整物化诊断、重复键与有效键扫描覆盖范围；不含行数据和主机路径。

- **DC12**：`dc12_json_columns_present: false` → **未触发** LONGTEXT。
- **DC15**：存储表列类型含 `INT UNSIGNED`、`TINYINT UNSIGNED`、`SMALLINT UNSIGNED`、`FLOAT`、`DATETIME` 等（各数据集的完整计数见 census JSON）；`unknown_sql_types` 为空（mapper 已识别拼写）→ **已触发**词表扩充需求，S2a 验收扩充并与 Dolt 往返对齐；FLOAT 无损往返优先在 S2a 验证（设计 §14 第 2 项）。
- **重复键（诊断 READERS_REQUIRED）**：t1 两份数据各发现 `b1_n2_iec104_syx_list` 3 条额外行；每份仅扫描 102 张有效键表，23 张有效键未解析表未扫描，另有 8 张按规则跳过，因此状态为 **partial**。t2 的业务物化在 composite 阶段失败，但 SQL 表扫描仍运行；实际结果见下表。t3/t4 的 XML 物化失败，键扫描未评估，不能把空 map/0 解释成未检出。
- **有效键（DDL 无主键表）**：t1 每份均有 28 张无 DDL 主键表；5 张由 EXPLICIT 规则给出有效键（`app_cfg.app_name`、`b1_n1_iec61850c_cfg(page_no,no)`、`b1_n2_iec104_cfg(page_no,no)`、`pointref_forwardtbl.refname`、`rdb_cfg.no`），其余 23 张无法解析有效键。t2 的 SQL 表集合也会独立扫描；t3/t4 的 XML 失败待治理修订计划 G2 修复后，在 G2 验收的普查重跑中补齐；DC22 真实数据旅程属 S2b 验收。t2 composite 失败的完整诊断保存在 census JSON，同样由 G2 承接，不再另交 composite_signal owner。

### 八数据集结构记录（诊断模式，无行数据）

`pair_of` 规则见 `$GATEWAY_REAL_DUMP_ROOT/dataset_pairing.json`。**Owner 确认（2026-10-10）**：同规模档 v1→v2 是同一项目；不同规模档是不同项目，不跨档配对。决定已写入 `p5-arch-closure-s0-owner-decisions.md` §10；S2b/S4 同项目链路验收以此为准。

| Dataset | Pair | Package bytes / SHA-256 | Staging / materialization | DDL tables | Materialized tables / rows | No DDL PK | Duplicate scan | Effective-key scan |
| --- | --- | --- | --- | ---: | --- | ---: | --- | --- |
| `rd-t1-a-v1` | — | 107115 / `42794011…95ea8b2` | COMPLETE / COMPLETE | 132 | 133 / 6097 | 28 | **partial**; scanned 102, 23 unresolved, 8 SKIP; 3 extra rows in `b1_n2_iec104_syx_list` | partial; 102 keyed, 23 unresolved, 0 keyless |
| `rd-t1-a-v2` | `rd-t1-a-v1` | 107066 / `4019737…095bd0` | COMPLETE / COMPLETE | 132 | 133 / 6095 | 28 | **partial**; scanned 102, 23 unresolved, 8 SKIP; 3 extra rows in `b1_n2_iec104_syx_list` | partial; 102 keyed, 23 unresolved, 0 keyless |
| `rd-t2-b-v1` | — | 1247459 / `acd1b5e…3817c0` | COMPLETE / FAILED `COMPOSITE_LOGIC_FAILED` | 216 | business snapshot unavailable; SQL scan source has 216 tables | 40 | **partial**; 181 scanned, 27 unresolved, 8 SKIP; 3,032 extra rows across 16 tables | partial; 181 keyed, 27 unresolved, 0 keyless; 13/40 no-DDL-PK tables have explicit effective keys |
| `rd-t2-b-v2` | `rd-t2-b-v1` | 1197404 / `c66e3921…5fcba98` | COMPLETE / FAILED `COMPOSITE_LOGIC_FAILED` | 216 | business snapshot unavailable; SQL scan source has 216 tables | 40 | **partial**; 181 scanned, 27 unresolved, 8 SKIP; 2,653 extra rows across 14 tables | partial; 181 keyed, 27 unresolved, 0 keyless; 13/40 no-DDL-PK tables have explicit effective keys |
| `rd-t3-c-v1` | — | 3356815 / `c34e266c…15eec7e` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 199 | unavailable / unavailable | 37 | not evaluated | not evaluated; G2 验收普查重跑 |
| `rd-t3-c-v2` | `rd-t3-c-v1` | 3370171 / `658422ef…cffc28d` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 200 | unavailable / unavailable | 38 | not evaluated | not evaluated; G2 验收普查重跑 |
| `rd-t4-d-v1` | — | 5597503 / `95408cc3…5da1675` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 319 | unavailable / unavailable | 59 | not evaluated | not evaluated; G2 验收普查重跑 |
| `rd-t4-d-v2` | `rd-t4-d-v1` | 5596595 / `5a7cd54d…ee3611` | COMPLETE / FAILED `XML_DOCUMENT_FAILED` | 319 | unavailable / unavailable | 59 | not evaluated | not evaluated; G2 验收普查重跑 |

t1 的 133 个物化表包含 132 个源 DDL 表和 1 个 XML composite 表。t2 `logics.xml` complete，events=3158；composite 诊断完整消息为 **`Digital forbids attribute 'value'`**（vnext `composite_signal/_ast.py` 把 legacy 与真实数据中小写的 `value` 误写为 `Value`，G2 第 2 项）。t2 SQL-only fallback 物化为 216 张表；两版本各扫描 181 张有效键表、27 张键未解析表、8 张 SKIP 表，未遇到 reader 不可用；40 张无 DDL 主键表中 13 张有显式有效键，其名称与键列见 census JSON。t3/t4 `logics.xml` failed（`XML_DOCUMENT_FAILED`，`max_xml_depth=64`），非 S1 引入（G2 第 3 项）。8 份 `version_manager.saved_time` 均为 `VARCHAR(128)`；unknown types、JSON 列、可空键列均为空。每份完整的 UNSIGNED 类型计数、SHA 与无键表清单见上方 JSON。

### 真实数据格式缺口的承接（治理修订计划 G2）

S1 普查暴露的三处缺口，Owner 于 2026-10-10 决定统一由[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G2“真实数据格式保真前置”承接，时点为 S1 合入后、S2a kickoff 前（[决议记录](p5-arch-closure-s0-owner-decisions.md) §10 第三项）：

| G2 项 | 现象 | 位置 |
| ---: | --- | --- |
| 1 | 8 份数据在生产解析路径上 `SET @saved_cs_client` → `UNSUPPORTED_STATEMENT` | `capabilities/table_access/_sql_statements.py` `_allowed_set_name` |
| 2 | t2 `COMPOSITE_LOGIC_FAILED`：`Digital forbids attribute 'value'` | `capabilities/composite_signal/_ast.py` `_ATTR_VALUE` |
| 3 | t3/t4 `logics.xml` 超出 `max_xml_depth=64` | `capabilities/table_access/contracts.py` |

S1 未改动 G2 涉及的解析逻辑（`table_access` 的 SQL 语句白名单与 XML 预算、`composite_signal/_ast.py`）；S1 整体只在 `composite_signal` 的 facade 中搬迁了一个惰性包装，不改变行为。

**t2 不阻塞 S2b 的 DC22**：生产上传当前只走 SQL 物化，composite 与 XML 解析器处于不可达基线——§4 的 14 项不可达模块包含 `composite_signal._ast`、`_bind`、`_digest`、`materialize` 与 `table_access._xml_parser`、`table_access.xml`，由 S3 接入后关闭。第 2 次独立复审 N4 中“阻塞 S2b”的说法不成立，据此更正。

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
| 第 3 次复审（2026-10-10） | fix `ce12e24528`；docs `a371d55bbe`；合并 `main` 的 V `d9c2097612`；H = 分支 tip | census 脚本与测试；文档（决议 §10 第三项、handoff、修复报告）；合并 `main` `5fe02db3a7`；V 上的最终门禁；H 回填 handoff |
| handoff（历史） | `84fd4f3447`、`00ae9ccad1`、`96071affd4` | 第 2 次复审之前的历史门禁证据与 traceability |

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

真实数据格式缺口（`@saved_cs_client`、`max_xml_depth`、`Digital` 属性大小写）由治理修订计划 G2 承接，在 S1 合入后、S2a kickoff 前于 `main` 上实施；执行计划 §1/§8 中 `p5-closure/s1-parser` 分支与“parser 修复”的表述由治理修订计划 G1 在 S1 合入后修订。S1 不修改 `table_access` 与 `composite_signal` 的生产源码；这些缺口不属于 §3 的 S2b 路径预算。

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
```

**Owner 确认（2026-10-10）**：原包级 facade 规则给出 10 项不可达；按实际导入的 wrapper 符号重算后为 14 项。新增的 4 项是 `composite_signal._ast`、`_bind`、`_digest`、`materialize`，当前没有可达生产调用方，已按决议 §10 登记为 S3 延期。执行计划 §2 的 S1/S2b 验收（S1 第 93 行附近、S2b 第 173 行附近）与 `architecture_baseline.py` 现均记录 14；后续实现继续遵守只减不增。

## 5. synthetic / worker 装配

- Synthetic 与 external effect stub 在 `tests/support/`；worker 测试侧注入 recovery（断言不变）。

### 5.1 只改导入路径的测试（S1 预算）

下列测试仅随模块迁移更新 import，**不断言行为变更**（见执行计划 §3 S1 必改 T）：

- `test_synthetic_w2.py`、`test_operation_job_synthetic.py`、`test_operation_job_recovery.py`、`test_operation_effect_reconcile.py`、`test_operation_worker_integration.py`
- `test_canonical_row_hash.py`
- `test_submit_job_payload.py`、`test_submit_job_effect.py`、`test_submit_job_prepare.py` 中的 `canonical_import_request_bytes` 测试桩（共 3 处；复审意见所称 4 处在当前测试树中未找到）
- 其余由被迁移模块 import 方决定的同型用例（handoff 不逐文件重复列举时，以 execution-plan §3 S1 必改 T 为准）

## 6. 门禁命令与结果

最终候选 V 是合并 `main` 后的已提交提交。门禁在 V 的 clean worktree 上由权威入口执行，并遵守 AGENTS.md“权威入口的运行前提”。V 之后只提交 handoff 等文档（H），再按 testing-conventions“镜像身份等价与结果沿用”判定 `carried`。第 2 次复审修复期间的门禁记录已移入 §6.6，不作为最终证据。

日志目录：**`/home/dev/gdds-p5-closure-s1-gate-logs/`**（worktree 外）。门禁期间不在 worktree 内写文件、不提交、不重建或重新 tag 镜像；最终门禁的日志均为 `final-*.log`。

### 6.1 提交前静态检查与 focused 测试

```bash
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done
cd vnext/backend
../scripts/uv-consume.sh -C . run python -m tests.support.import_rules
../scripts/uv-consume.sh -C . run pytest tests/test_real_dump_census.py tests/test_architecture.py -m unit -q
```

结果（2026-10-10，日志 `final-precommit-static.log`）：

- 五包 ruff 与 mypy 全部通过（mypy 检查文件数：shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 464）。
- `import_rules`：**3 条违例 / 0 个运行时环 / 14 个不可达模块**。
- census 与 architecture unit focused：**87 passed**（census 含新增的“reader 不可用 → partial”形态；此前为 85）。
- 运行时的 HEAD 为 `96071affd4`，工作区含随后提交为 `ce12e24528` 的 census 脚本与测试，运行后未再修改。

### 6.2 最终门禁流程（在 V 上）

前置检查，任一项不满足则先清理，不得带着残留开跑（`final-preflight.log`）：`git status --porcelain` 为空；`pgrep -x dolt` 为空；`docker ps` 中没有带 compose project 标签的容器、`docker compose ls -a` 为空；8000 端口无监听。

```bash
cd /home/dev/gdds-p5-closure-s1   # detached worktree 需 legacy → 主工作区 legacy/，见 internal-build-environment-handoff.md
./vnext/scripts/build-repository-service-image.sh        # final-image-build.log：image ID 与全部 label
set -o pipefail
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh 2>&1 | tee -a final-run-tests.log
runner_exit_code=${PIPESTATUS[0]}                         # runner 自身的 exit code
cp vnext/backend/tests/support/.last_compose_gate_provenance.json final-compose-provenance.json
docker image inspect <provenance 中的 3 个 image ID>      # final-image-inspect.log：Id、Created、Labels
```

不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`，由 harness 在 V 上构建 backend/worker；backend 批次已包含 9 项 Compose 旅程，不再单独运行。每一步前后各记录 `git rev-parse HEAD` 与 `git status --porcelain`；五锁 SHA 与 `compose.yaml` SHA 一并记入 `final-image-inspect.log`。

失败处理：不得用定向补跑替代 runner 的 exit code。可复现的失败先修复，形成新的 V 并完整重跑；疑似环境污染时，清理后完整重跑一次，两次运行都写入记录，不挑选结果。

### 6.3 V 上的最终结果

V = `d9c2097612036c05741c98b702d518d54571ece2`（tree `4ea3ce28543537375e9c9f7c5fa611362887e052`；父提交为 docs `a371d55bbe` 与 `main` `5fe02db3a7`）。以下三次运行都是完整的权威 runner，均在 V 的已提交 clean worktree 上、`GATEWAY_TEST_WORKERS=48`、不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`；每次运行开始与结束时 `git rev-parse HEAD` 都是 V、`git status --porcelain` 都为空，前置检查均通过。backend 批次含 9 项 Compose 旅程（`pytest --collect-only -m 'integration and serial'` 在这 7 个文件上收集 9 项），无 skip。

| 运行 | 日志前缀 | 时间（+0100） | runner exit code | shared_kernel / contracts / client | backend | RS parallel | RS serial |
| ---: | --- | --- | ---: | --- | --- | --- | --- |
| 1 | `final-*` | 14:42:42–15:08:17 | **1** | 242 / 152 / 154 passed | 2704 passed，1 warning | 1678 passed，1 skipped | 203 passed，**2 failed** |
| 2 | `final-rerun-*` | 15:10:10–16:12:35 | **1** | 242 / 152 / 154 passed | 2704 passed，1 warning | 1678 passed，1 skipped | 204 passed，**1 failed** |
| 3 | `final-rerun2-*` | 16:13:16–16:39:19 | **0** | 242 / 152 / 154 passed | 2704 passed，1 warning | 1678 passed，1 skipped | **205 passed** |

**V 的最终门禁结果以第 3 次运行为准：runner exit 0。** 前两次运行的失败不被忽略，也不用定向补跑替代：

- 运行 1：`test_compose_wrong_network_cleans_up` 与 `test_compose_remote_client_commit_pinned_read_inside_network` 失败，都是 `repository-client image build failed`，buildkit 报 `failed to prepare … max depth exceeded`。
- 运行 2：只有 `test_compose_wrong_network_cleans_up` 失败，同样是 client 镜像构建失败：`uv sync --frozen --group dev` 下载 `pyarrow==25.0.0` 时 `Request failed after 4 retries in 129.3s`（`operation timed out`）。

三次运行里，失败只出现在 client e2e 测试镜像（`gateway-repository-client-e2e:local`）的构建这一步，没有任何用例断言失败；其余批次的数量与第 3 次一致。

**环境成因与处置**（日志 `final-client-image-depth.log`、`final-cleanup.log`、`final-rerun2-client-image.log`）：

1. RS 测试 harness 构建该镜像时，只要现有镜像的 uv-lock label 匹配，就把它自己的 tag 当作 `BASE_IMAGE`（`compose_lifecycle_harness.py` `client_dependency_base_image`，默认值为镜像自身）。每换一个候选 SHA 都会在上一版之上再叠层。运行 1 之前该镜像已有 124 个 rootfs 层（`docker history` 293 条），再叠加就超过 overlay2 的深度上限。
2. 运行 1 之后删除了这个镜像（`docker rmi`）。该镜像同时是环境保留的预装依赖基础镜像；删除后构建要从 `python:3.14.6-slim-bookworm` 起步并联网安装依赖，而该主机到 PyPI 的下载很慢（运行 2 日志中 `pyarrow==25.0.0`（47.8 MiB）在 4 次重试、129.3 秒后仍超时），因此运行 2 中第一次构建因下载 `pyarrow` 超时而失败，第二次构建成功（Created 16:10:33，12 层，`revision` label 为 V）。
3. 运行 3 开始时该镜像已存在且 label 与 V 匹配，harness 复用而不重建（运行 3 结束后该镜像的 Created 仍为 16:10:33，层数仍为 12），runner 通过。

这不是规程中的“清理后重跑一次”：为恢复被删除的预装依赖基础镜像共执行了 3 次完整运行，三次都已记录。**未修复的遗留问题**：client 镜像以自身为基础会随候选更换持续叠层，建议由 owner 另行决定修复方式（例如改为以单层依赖基础镜像为基础，或在构建前检查层数）。S1 不改动该 harness。

运行 3 的镜像（`final-rerun2-compose-provenance.json`、`final-rerun2-image-inspect.log`；project `ordered-bisect-b-2622496-baseline`）：

| 镜像 | image ID | 说明 |
| --- | --- | --- |
| repository-service | `sha256:c1b3a54111b1babf0d0fae856514f2dfd0a89db13a05840e84b674ffec10a78d` | Created 2026-10-10 14:42:41 +0100（运行 1 在 V 上构建）；运行 2、3 的构建步骤全部命中缓存，image ID 不变。labels：`org.opencontainers.image.revision`=V，`build-input-revision`=`4d1dc010deff17249bb2aa54b7563e7a86959096`，`source-tree-sha256`=`sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf`，`uv-lock-sha256`=`6dc9659f…`，dolt 2.1.11，uv 0.11.28 |
| backend | `sha256:020c387c63eb37ebad4a815264a249637a725b19ecffae7c386f87bfce6992fb` | gate harness 构建；Created 2026-10-10 11:33:04Z（复用 BuildKit 层）；labels 只有 compose project/service/version，没有 revision label |
| worker | `sha256:a1a8185ca8957147048df1c53db46c7134267fd694efc7c9cfc4a5fd6308c4e8` | 同上 |

运行 1、2 的 provenance（同一 RS image ID `c1b3a541…`）：运行 1 project `ordered-bisect-b-1678334-baseline`，backend `6986db9d…`、worker `8a8d14d8…`；运行 2 project `ordered-bisect-b-2136129-baseline`，backend `30eddfda…`、worker `435a442f…`。compose 把 project 名写入镜像 label，所以同一源码在不同 project 下 image ID 不同；§6.4 因此必须用 provenance 中的 project 名重建。

日志（均在 `/home/dev/gdds-p5-closure-s1-gate-logs/`）：运行 1 `final-preflight.log`、`final-image-build.log`、`final-run-tests.log`、`final-compose-provenance.json`、`final-image-inspect.log`、`final-summary.log`；运行 2 与运行 3 同名但前缀分别为 `final-rerun-`、`final-rerun2-`；另有 `final-precommit-static.log`、`final-client-image-depth.log`、`final-cleanup.log`、`final-rerun2-client-image.log`。

### 6.4 镜像身份等价判定（V → H）

判定在 H 提交之后、于 H 的 clean worktree 上执行；结果写入 `final-carried-check.log`，不再提交（H 不能引用自身之后产生的结果），并在复审提示词中给出。判定方法：

a. `git diff --name-only V H` 只含文档；
b. 用 `python3 vnext/repository_service/tests/support/build_context_digest.py identity` 在 H 上重算，`build-input-revision` 与 `source-tree-sha256` 都等于 V 所用 RS 镜像的 label；
c. 用 harness 构建 backend/worker 的同一命令（`compose_gate_harness.py` `build_compose_stack_images`：`docker compose -f vnext/deploy/compose.yaml build backend worker`，`cwd=vnext/deploy`，`COMPOSE_PROJECT_NAME` 取 provenance 中记录的 project 名）重建，image ID 须等于 `final-compose-provenance.json` 中的 ID。compose 把 project 名写入镜像 label，project 名不同则 image ID 不同，所以必须使用 provenance 中的 project 名。

任一项不等，回到 §6.2，在 H 上重跑。

### 6.5 五锁 SHA 与 compose.yaml SHA

取自三次运行的 `*-image-inspect.log`（三次相同，且与第 2 次复审时的记录一致）：

- shared_kernel `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898`
- repository_contracts `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3`
- repository_client `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`
- repository_service `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`
- backend `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea`
- `vnext/deploy/compose.yaml` `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0`

### 6.6 历史（不作为最终证据）

#### 6.6.1 2026-09-27/28 的记录

**历史记录，不是最终候选门禁**：`gate-logs/run-tests-rereview.log` 的各批次曾报告 shared_kernel 242、repository_contracts 152、repository_client 154、backend 2691、repository_service parallel 1678（1 skipped）、serial 205。日志没有记录 HEAD/tree 或 runner exit code；运行时间跨过 `41c43909be`，并与镜像重建重叠。backend 当前实现树收集 2700 项，故 2691 项的旧日志不是当前实现树的全量结果，不能据此声称 runner exit 0。

另一份历史日志 `/home/dev/gdds-p5-closure-s1-gate-logs/run-tests-r2.log` **存在**，是 2026-09-27 的失败运行：backend、repository_service parallel、serial 分别报告 3、1、3 项失败；不作为验收证据。此日志此前被误写为不存在。

镜像 fresh build（历史命令）：

```bash
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
```

**历史构建身份未证实**：`build-compose-backend-worker.log` 的 mtime 为 2026-09-28 13:50 +0100，早于 `41c43909be` 的提交时间 14:12 +0100，不能证明该 compose build 来自 `41c43909be`。backend/worker 镜像没有 revision label；其源码身份此前只是推断。以上旧镜像只作为回归材料，不表示任何当前候选已验证。

Backend Compose 旅程（历史）：9 passed，1 warning，约 1145 s（2026-09-28），日志 `gate-logs/backend-compose-9-r2.log`；没有绑定任何当前候选 HEAD。旅程实际使用的镜像：backend `sha256:b6795948…`、worker `sha256:a6234eee…`、RS `sha256:2fe98a0f…`。backend/worker 没有 revision label，源码身份未记录。

#### 6.6.2 第 2 次复审修复期间的门禁（候选 `96071affd4` + 未提交补丁 `492cce95…`）

owner 当时要求不提交，因此以下运行都不是已提交 clean worktree 上的权威运行。2026-10-10 独立评审按实测更正了此前的若干表述，以本小节为准。

| 门禁 | 结果 | 日志 |
| --- | --- | --- |
| 五包 ruff + mypy | pass | `rereview2-focused.log` |
| `import_rules` | 3 / 0 / 14 | `rereview2-focused.log` |
| census + architecture focused | 85 passed | `rereview2-focused.log` |
| `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`（dirty worktree） | **runner exit 1**；shared_kernel 242、contracts 152、client 154、backend 2702、RS parallel 1678 passed + 1 skipped；RS serial 197 passed / 8 failed | `rereview2-full-tests.log`（12:32:41 开始） |
| RS 镜像 | `sha256:4895ff38…`，见 d | `rereview2-image-build.log` |
| 手动 `docker compose … build backend worker` | 见 a、b | `rereview2-image-build.log` |
| backend Compose 旅程 | 9 passed，1 warning，1072.26 s，exit 0；见 a、c | `rereview2-backend-compose-9.log`、`rereview2-backend-compose-provenance.json` |

全量 runner 的 8 个 RS serial 失败都在 `compute_image_identity()` 的 `require_clean_worktree()` 抛出 `ProvenanceError: worktree is dirty`，没有到达各用例的服务断言。该前置与当时“不提交”的约束冲突；该约束已撤销，最终门禁见 §6.2。

**实测更正**

a. `rereview2-image-build.log` 与 `rereview2-backend-compose-9.log` 开头记录的 backend/worker 是 `b6795948…` 与 `a6234eee…`。`docker image inspect` 显示二者 Created 为 2026-09-28T12:18:11Z、现已无 tag（compose project label 为 `gateway-p5-closure-s1-gate`），是 2026-09-28 的旧镜像，不是本轮镜像，不能据此证明候选的 backend/worker 身份。

b. 本轮手动 `docker compose -f vnext/deploy/compose.yaml build backend worker` 产出 `deploy-backend` `4068fcc8…` 与 `deploy-worker` `956b052d…`（project label 为 `deploy`）；Compose 旅程没有使用这两个镜像。

c. 旅程实际使用的 backend `e6bb3b38…`、worker `44f4ce88…`（tag `gateway-p5-closure-s1-gate-{backend,worker}`）由 gate harness 构建（`build_compose_stack_images`，`GATEWAY_COMPOSE_GATE_PREBUILT=0`）。其 Created 为 2026-10-10 12:33:04 +0100，落在全量 runner 的 backend 批次内（runner 12:32:41 开始）；该时间取自复用的 BuildKit 层，同一时刻的 backend/worker 镜像 Created 均相同，仅 compose project label 与 image ID 不同。

d. RS `4895ff38…` 的 Created 为 12:06:34 +0100，早于补丁冻结（`real_dump_census.py` mtime 12:23:30、`test_real_dump_census.py` 12:13:07）；12:57 的构建各步骤全部 CACHED，没有重新构建。该镜像与补丁后候选的等价依据是镜像 label（build-input-revision `4d1dc010…`、source-tree `sha256:62a38a08…`），不是构建时间；`org.opencontainers.image.revision`（`96071…`）随提交变化，不参与比较。

e. 为核实 8 个 RS serial 用例，在 clean worktree 上共补跑 7 次，逐次如下。日志均未记录完整命令行，“方式”一列依据日志内容判断；`-n 0` 来自 owner 的说明。

| # | 日志 | 方式 | 结果 | 日志中的失败/错误 |
| ---: | --- | --- | --- | --- |
| 1 | `rereview2-rs-compose-clean-retry.log` | 8 项，xdist 并行（日志有 `bringing up nodes…` 与 gw 标记） | 6 failed / 2 passed，29.36 s | wrong-token 得到 `failed`；gate-host consumer `ModuleNotFoundError: gateway_repository_client`；多项 `dolt children remain`（列出 60 余个 PID，并行 worker 互相可见） |
| 2 | `rereview2-rs-compose-serial-retry.log` | 8 项，无 xdist 标记（`-n 0`） | 3 failed / 5 passed，100.07 s（12:59:08–13:00:49） | 见下“dolt children remain 的说明” |
| 3 | `rereview2-rs-compose-clean-retry-2.log` | 3 项，`-n 0` | 3 failed，33.49 s（13:02:18 结束） | 同上；缺的模块为 `httpx` |
| 4 | `rereview2-rs-compose-clean-retry-3.log` | 3 项 | collection error，exit 4（13:02:49） | `ModuleNotFoundError: gateway_repository_service`（配置错误） |
| 5 | `rereview2-rs-compose-clean-retry-4.log` | 3 项 | collection error，exit 4（13:03:02） | `ModuleNotFoundError: pydantic_settings`（配置错误） |
| 6 | `rereview2-rs-compose-clean-retry-5.log` | 3 项 | 3 passed，86.98 s，exit 0（13:04:52） | 日志未记录用例 id |
| 7 | `rereview2-rs-compose-clean-final.log` | 8 项单批串行，日志记录 `prepared_test_environment=repository_service_venv_plus_locked_repository_client_and_httpx_0.28.1` | 8 passed，154.14 s，exit 0（13:33:33） | — |

**`dolt children remain` 的说明**：#2、#3 各有 3 项失败。日志中这 3 项的主异常是测试环境缺包：`wrong_token` 经 gate-host consumer 运行，因此得到 `failed` 而不是 `unauthorized`；`gate_host` 与 `fresh_restart` 两项是 consumer 导入失败（#2 缺 `gateway_repository_client`，#3 缺 `httpx`）。`dolt children remain` 只出现在 `fresh_restart` 一项的清理链（链式异常）中：#2 为 `[1395623, 1395703]`，#3 为 `[1400324, 1400408]`。这些 PID 都大于 #1 日志中出现的最大 PID（1370130），倾向于是失败运行自己产生的进程，而不是前一次 xdist 尝试残留的进程，但未做进一步检查，根因未查实。`list_dolt_pids()`（`tests/support/snapshot_admin_harness.py`）扫描整机 `/proc`，所以同一主机上并行的其他 dolt 进程会被计入。

其余历史验证记录（2026-10-10）：

- 修复相关 focused tests 85 passed（`test_real_dump_census.py` 与 architecture unit tests）。
- 当时只修改主机侧普查脚本、其 unit 覆盖及治理/交接文档；未改 HTTP/worker、Dockerfile、Compose 或容器运行时边界。

## 7. 请 reviewer 重点核对

1. import 3/0/14；4 个 composite facade 实现模块按符号级可达性登记为 S3 延期；DC26 仅对 `capability:canonical_row_hash → ext:compute` 放行。
2. §3 模块已落地；job 模块仅薄包装、checkpoint 载荷未变。
3. kickoff 普查负结果未 overstated 为 S2a 类型决策；census 脚本 `96071affd4..ce12e24528` 的差异与新增用例。
4. 合并的 `main`（授权基线 `218c211240` 之后的新增提交）只带入文档与 AGENTS.md，无实现冲突。
5. 门禁绑定 V：已提交 clean worktree、runner 自身的 exit code、前后 HEAD/status、provenance 中的 3 个 image ID；三次运行（两次因 client e2e 镜像构建环境失败，§6.3）如实记录；V → H 的 `carried` 判定逐项复核（§6.4）。
6. 真实数据格式缺口的承接（§1 末、决议 §10 第三项）：t2 不阻塞 S2b DC22 的依据与 N4 更正。
7. §6.6.2 的实测更正 a–e 与 7 次补跑记录，包括 `dolt children remain` 的说明。

## 8. 审核提示词（§8.7）

reviewer 开始时解析 `candidate_ref` 的分支 tip，再依执行计划 §8.8 模板生成本轮审核提示词。

---

## 修订（2026-09-28，审核 `a35b2ad8dd` → `implementation_head`）

> 以下两个“修订”小节是历史记录。其中“parser 前置”“S2a 承接”的表述已被[决议记录](p5-arch-closure-s0-owner-decisions.md) §10 第三项取代：真实数据格式缺口改由治理修订计划 G2 承接（见 §1 末）。

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
- 全量 `run-tests.sh`：原记录引用的 `/home/dev/gdds-p5-closure-s1-gate-logs/run-tests-r2.log` 实际存在；该轮 backend、repository_service parallel、serial 分别有 3、1、3 项失败，因此不作为验收证据。§6.2 所列 2026-09-28 日志也不是最终候选的完整门禁。
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

_next_step：独立复审 rereview-3 通过后，由 owner 将 S1 合入 `main` 并在合入提交上打 `p5-s1-exit`；随后按治理修订计划 §3 依次执行 G1+G5、G3、G2，再进入 S2a kickoff。_
