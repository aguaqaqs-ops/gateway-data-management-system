# P5 架构收口 G2 handoff

## 1. 区间、提交与范围

- `range_start`: `p5-s1-exit` = `139ee5fffd5b8d3bc229d9a6a5db1a4e06cbfc57`。
- `implementation HEAD`: `84177001e1858d78edf39c541242cef22e836547`。
- `V`: `84177001e1858d78edf39c541242cef22e836547`，最终完整权威门禁 exit code 0。
- `H`: 添加本 handoff 与下方三个治理状态标记的提交；精确 SHA 由该提交对象确定，最终回复记录。
- 审核区间：`p5-s1-exit..H`。G2 获得授权，含 G6、G7；G3、G8 不在本次实现范围。
- G4 未实施：剩余的 `rd-t3-c-v1` 失败发生在 SQL 解析阶段；SQL fallback 不能从失败的 parse result 得到 reader/table set，不会产生额外键统计。现有 fallback 触发范围保持不变。

| 子项 | 提交 | 结果 |
| --- | --- | --- |
| G2.1 SQL SET 白名单 | `3f0047139bf4058f3b04bf723bc8bb608c2a16a4` | 精确放行 `@saved_cs_client`，大小写不敏感；其他用户变量及 `@@saved_cs_client` 仍拒绝。 |
| G2.2 Digital AST 属性 | `a19ae6e8be68e65a8ec14ef170ca6bfbe61f946f` | 只接受小写 `value`；缺失、大写 `Value`、多余属性均有测试。 |
| G2.3 XML 深度 | `b90b4f46c3954a8593f5537498172d67ffdcda37` | `max_xml_depth=128`；同步更新资源预算断言。 |
| G2.4 普查与 census | `e3dcd8a7bcf46b90b5a72a80a9f5524056f0ebf7` | 移除诊断 SQL monkeypatch，重跑生产/诊断路径并更新 census。 |
| G6 构建上下文 | `6fd40aa0f4da2d1ae111388e56b2b2898a5e7637` | 排除 `.hypothesis`，更新两处 carried 文字并验证跨 worktree 身份。 |
| G7 client e2e 层叠 | `84177001e1858d78edf39c541242cef22e836547` | 独立依赖 base tag；最终镜像每次从 base 构建，层数稳定。此提交也是 V 与 implementation HEAD。 |

## 2. G2 验收

### G2.1

`_allowed_set_name` 对 `@` 名称执行精确比较，只放行 `@saved_cs_client`，不使用变量名前缀或通配规则。`MYSQLDUMP_SET_SHAPES` 覆盖三种真实 mysqldump 前导语句及大小写变体；拒绝参数表覆盖 `@@saved_cs_client` 和其他 `@` 用户变量。golden SQL parser/reject 测试通过。

### G2.2

`_ATTR_VALUE` 与诊断消息使用小写 `value`。参数表覆盖正常属性、缺属性、`Value` 与多余属性；`Value` 被判为 `UNKNOWN_ATTRIBUTE`。t2 的真实 `logics.xml` 与 legacy parser 一致：改名后两个 t2 数据集的 composite 阶段均 `COMPLETE`，没有继续暴露 AST 结构或业务语义差异。

原 composite golden 的两个 `input.xml` 将属性拼写从 `Value` 改为真实格式 `value`：
`vnext/fixtures/golden/composite-signal/xml/valid/s3-minimal-logic/input.xml` 和
`vnext/fixtures/golden/composite-signal/xml/valid/s3-nested-express/input.xml`。这两处是输入 fixture 修正；对应 expected JSON、digest、checkpoint 载荷与 HTTP DTO 均未修改。`digest.ast_to_json` 输出键原本就是 `value`。

### G2.3

8 份 `logics.xml` 的 G2 实测最大深度依次为 `1, 1, 56, 56, 66, 66, 97, 97`（见下表）。最大实测 97，增加 31 层余量，约 32%，设为 128，低于 512。边界合成测试在恰好 128 层走完 XML 解析、AST 构建、`ast_to_json` 与 JCS 序列化；129 层得到 `max_xml_depth` 资源超限诊断，不抛 `RecursionError`。

### G2.4：8 份数据新旧对照与 G8 统计

S1 生产 SQL 路径的 8 份数据都因 `SET @saved_cs_client is not in the source dump allowlist` 失败。S1 诊断物化中 t1 两份完成，t2 两份因 `Digital forbids attribute 'value'` 在 composite 阶段失败；t3/t4 的键统计未评估。S1 未记录逐份 XML 最大深度，也未分类整行重复和冲突行。

G2 生产路径与诊断路径均重跑 8 份。诊断模式现在只表示 `READERS_REQUIRED` 键统计，不改 parser。7 份 SQL 生产解析、物化与 composite 均完成。`rd-t3-c-v1` 保留完整失败：`UNSUPPORTED_STATEMENT` — `SET @OLD_CHARACTER_SET_CLIENT is not in the source dump allowlist`；对应 materialization diagnostic 为 `TABLE_READER_UNAVAILABLE`，composite 为 `NOT_REACHED`。不扩大白名单来接受未授权的第二种用户变量。

| 数据集 | S1 业务 / 重复键统计 | G2 XML 最大深度 | G2 生产 SQL / composite | G2 重复键：额外行 / 完全相同 / 冲突；重复表 / 已扫描表 |
| --- | --- | ---: | --- | --- |
| `rd-t1-a-v1` | `COMPLETE`；3 行、1 表、102 表已扫描 | 1 | `COMPLETE / COMPLETE` | `3 / 0 / 3`；`1 / 102` |
| `rd-t1-a-v2` | `COMPLETE`；3 行、1 表、102 表已扫描 | 1 | `COMPLETE / COMPLETE` | `3 / 0 / 3`；`1 / 102` |
| `rd-t2-b-v1` | composite `FAILED`；3,032 行、16 表、181 表已扫描 | 56 | `COMPLETE / COMPLETE` | `3,032 / 0 / 3,032`；`16 / 182` |
| `rd-t2-b-v2` | composite `FAILED`；2,653 行、14 表、181 表已扫描 | 56 | `COMPLETE / COMPLETE` | `2,653 / 0 / 2,653`；`14 / 182` |
| `rd-t3-c-v1` | materialization `FAILED`；未评估重复键 | 66 | `FAILED / NOT_REACHED` | reader 不可用；未扫描，**不是零重复** |
| `rd-t3-c-v2` | 未评估重复键 | 66 | `COMPLETE / COMPLETE` | `9,817 / 0 / 9,817`；`24 / 165` |
| `rd-t4-d-v1` | 未评估重复键 | 97 | `COMPLETE / COMPLETE` | `12,616 / 0 / 12,616`；`40 / 279` |
| `rd-t4-d-v2` | 未评估重复键 | 97 | `COMPLETE / COMPLETE` | `12,624 / 0 / 12,624`；`40 / 279` |

可读表的重复有效键额外行总数为 40,748：完全相同行额外行 0，冲突行 40,748。共有 136 个 dataset-table 重复记录；其键来源均为 `EXPLICIT_RULE`，没有 DDL 主键来源。每个重复表的表名、有效键列、来源与分类计数均在 census JSON 的 `duplicate_key_scan.table_details` 中；未序列化任何行值。扫描状态仍为 partial，未解析的有效键表不在该计数内。G8 不在本次作处置，不改规则键或去重行为。

生产路径输出：`summary-production.json`；诊断路径输出：`summary-diagnostic.json`，均位于决议 §4 授权的外部 `census/` 目录。提交内 census JSON 的 `contains_row_data` 为 false，`census_output_contains_host_paths` 为 false。G4 未扩展：唯一剩余失败在 SQL parser，fallback 无法产生 SQL table set；其余可解析数据的 composite 已完成。

## 3. G6 构建上下文与身份

`vnext/.dockerignore` 增加 `**/.hypothesis`。检查 `shared_kernel`、`repository_client`、`repository_contracts` 的 COPY 源根：`.venv`、`__pycache__`、`.pytest_cache`、`.mypy_cache` 与 `.ruff_cache` 已由原规则排除，未发现第二个需要新增的缓存规则。repository-service `build_context_digest.py` 的 54 项测试通过。

在最终 G6 提交 `6fd40aa0f4da2d1ae111388e56b2b2898a5e7637` 的两个 detached worktree 中，以相同命令和 project `g2-g6-final-6fd40` 构建 backend/worker。worktree A 有一个 `.hypothesis` 缓存文件，B 没有；验证专用 Git excludes 将该缓存按本机缓存规则视为 ignored，构建前后两个 worktree 的 `git status` 均 clean。两次构建之间未跑测试。image ID 相同：backend `sha256:475c824a6b75ddc11ea73c1ee11984324c5b07e82079524263a42ecacea415b1`，worker `sha256:01a37521bb43f4091d94d4d1a7597967dddcdba0d3d7b39ec6c2823ca0310b2e`；两边均为 15 层，Compose project/service labels 正确。两镜像运行 `find /app -name .hypothesis` 均为空。记录见 `g2-g6-final-commit-cache-cross-worktree.log`。较早的 rebase 前比较仅作历史记录，不作为最终 G6 验收依据。

RS identity 的旧、新值（SHA 均完整记录于门禁 provenance/build log）：

| 点位 | `build_input_revision` | `source_tree_sha256` |
| --- | --- | --- |
| G6 前，G2.4 HEAD `f5e8d02cb292b59c2ea396cdcb78cda8314daa63` | `4d1dc010deff17249bb2aa54b7563e7a86959096` | `sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf` |
| G6 HEAD `6fd40aa0f4da2d1ae111388e56b2b2898a5e7637` | `6fd40aa0f4da2d1ae111388e56b2b2898a5e7637` | `sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf` |
| V `84177001e1858d78edf39c541242cef22e836547` | `84177001e1858d78edf39c541242cef22e836547` | `sha256:ff8cbb8fbd618351c16d811af0a8d32dc37eb620b6121bf544a23f6e9235ddbb` |

helper 的当前契约把 `.dockerignore` 作为 build-definition 输入，因此 G6 使 `build_input_revision` 前进；`source_tree_sha256` 只哈希 `repository_service` 与 `repository_contracts` source roots，故 G6 单独提交时该值不变。它在 G7 因 `compose_lifecycle_harness.py` 的 source-root 内容变化而更新。V → H 仍须在 H clean worktree 重算并与 V 镜像 labels 比较；最终判定写入外部 `g2-carried-check.log`。

## 4. G7 client e2e 镜像

依赖 base 固定为 `gateway-repository-client-e2e-base:local`，最终镜像仍为 `gateway-repository-client-e2e:local`。首次 base seed 是 `docker tag` 将已有 lock 匹配的最终镜像加别名完成，没有重建或联网。lock 不变的单测确认不重建 base；最终 `BASE_IMAGE` 与 `-t` 输出 tag 不同。

两个不同候选 SHA 的 `ensure_client_image` 结果：候选 `815ef56a30b3796cb379887d601b4d8a53e91334` 的最终层数 20；最终 V `84177001e1858d78edf39c541242cef22e836547` 的最终层数 20。独立 base 两次均为 image `sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764`、12 层、lock SHA `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`；候选变化未重建 base。测试 `test_compose_lifecycle_harness.py` 92 项通过。没有执行 `docker rmi`、image prune 或 system prune；门禁期间没有重建或重打任何 tag。

## 5. 静态、focused 与 import_rules

G2/G6/G7 提交后五个 Python 包均通过 `ruff check .` 与 `mypy`。最终 V 前 focused 结果：backend 相关 92 项通过；`test_capability_packages_match_owner_set` 1 项通过；repository_service harness 与 build-context 测试 146 项通过；`import_rules` 与起点相同：3 violations / 0 runtime cycles / 14 unreachable。

首次完整门禁发现：预算断言仍为旧值 64，以及两个仅有 `.pyc` 的 Git-ignored 空能力目录造成 owner-set 扫描误报。没有添加 baseline 条目。删除前确认它们不含源码且仅含 `__pycache__/*.pyc`，记录于 `g2-v-attempt1-cache-cleanup.log`；G2.3 的预算断言修正并入原提交，clean 后 owner-set 测试通过。随后形成新 V 并完整重跑；没有用定向补跑替代 runner。

## 6. V 门禁与镜像 provenance

### 已废止候选尝试

初次候选 SHA `815ef56a30b3796cb379887d601b4d8a53e91334`（后续为把预算断言并入 G2.3 提交而重放提交链；不是最终 V）在 clean worktree 上真实重建 RS 并运行权威入口，runner exit code 1。批次：shared_kernel 242 passed；repository_contracts 152 passed；repository_client 154 passed；backend 2,715 passed / 2 failed；repository_service parallel 1,680 passed / 1 skipped；serial 205 passed / 1,681 deselected。失败为旧预算断言和上述 ignored-cache 环境污染。原始日志、provenance 与 inspect 保留供审核。

### 最终 V

`84177001e1858d78edf39c541242cef22e836547` 上执行第二次 preflight、重建 `gateway-repository-service:local`，再运行
`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。runner exit code 0，worktree 起止 clean，HEAD 起止相同。批次：shared_kernel 242 passed；repository_contracts 152 passed；repository_client 154 passed；backend 2,717 passed / 1 warning；repository_service parallel 1,680 passed / 1 skipped；serial 205 passed / 1,681 deselected。

V provenance project 为 `ordered-bisect-b-3655597-baseline`：

| 镜像 | provenance image ID | labels 摘要 |
| --- | --- | --- |
| backend | `sha256:1487ab34eb775bb8caefb8a761fcf19f34d5aede142af920954d48e4ddee34bb` | compose project=`ordered-bisect-b-3655597-baseline`, service=`backend`；15 layers |
| repository-service | `sha256:722f5bb63e80b88db55fd7714a91f7c2deb096aacc5f256f70b50bee17c4d309` | revision/build-input-revision=`84177001e1858d78edf39c541242cef22e836547`; source-tree=`sha256:ff8cbb8fbd618351c16d811af0a8d32dc37eb620b6121bf544a23f6e9235ddbb`; uv lock=`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`; 28 layers |
| worker | `sha256:7ff0e7548cfb4cc51cc9104ac218b651b76b11ed6f3efbe44fae91c79e649e49` | compose project=`ordered-bisect-b-3655597-baseline`, service=`worker`；15 layers |

## 7. 日志与 reviewer 重点

所有 gate/census/G6/G7 日志写在 worktree 外 `/home/dev/gdds-p5-closure-s1-gate-logs/`：

- census：`g2-real-dump-census-runs.log`。
- G6：`g2-g6-final-commit-cache-cross-worktree.log`（最终 G6 commit 的缓存差异比较）；`g2-g6-final-clean-worktrees.log`（同 commit、两个无缓存 clean worktree 的比较）；rebase 前记录 `g2-g6-cross-worktree.log` 仅作历史记录。
- G7 client image：`g2-g7-client-v.log`、`g2-g7-client-final-v.log`。
- 首次尝试：`g2-v-preflight.log`、`g2-v-repository-service-build.log`、`g2-v-runner.log`、`g2-v-compose-provenance.json`、`g2-v-images-inspect.log`、`g2-v-attempt1-cache-cleanup.log`。
- 最终 V：`g2-v2-preflight.log`、`g2-v2-repository-service-build.log`、`g2-v2-runner.log`、`g2-v2-compose-provenance.json`、`g2-v2-images-inspect.log`、`g2-v2-post-run-state.log`。
- H 后 carried：`g2-carried-check.log`。

请 reviewer 重点核对：精确 SQL SET 白名单边界与完整 mysqldump 形态；Digital 四种属性形态及真实 t2/legacy 对照；128 层递归全链路与 129 层 fail-closed；普查输出的失败码、深度、重复行分类、有效键来源与无行数据/路径约束；G6 context 排除规则和跨 worktree image ID；G7 独立 base tag、无重建 seed、lock 复用和固定层数；V 最终门禁日志、三镜像 provenance 与 H 上 V→H carried 日志；本文列出的全部停止条件。不得把 G8 统计扩展为规则键变更或去重行为。

## 审核提示词

按 §8.7 的审核模板填写；H 的 SHA 在审核时由 `main` 解析：

```text
任务：独立审核 P5 架构收口 post-S1 G2（含 G6、G7）。你没有参与本阶段实现；按 docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：main @ <H>（门禁提交 V = 84177001e1858d78edf39c541242cef22e836547，实现 HEAD 84177001e1858d78edf39c541242cef22e836547），区间 p5-s1-exit..H。只审该区间的差异。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-review-g2 <H>；不在主工作区运行测试或写入。
权威依据：plans/p5-arch-closure-post-s1-governance-plan.md（G2、G6、G7）、plans/p5-arch-closure-execution-plan.md（§2、§3、§8）、plans/p5-arch-closure-design.md（§14）、ADR 0018–0021、AGENTS.md；实现方记录 plans/p5-arch-closure-g2-handoff.md。
必须核查：
  1. G2.1 精确放行 @saved_cs_client（大小写不敏感），@@saved_cs_client 与其他用户变量仍拒绝；三种 mysqldump 前导形态进入现有 owner 测试。
  2. G2.2 Digital 小写 value、缺失/大写 Value/多余属性行为；真实 t2 与 legacy 对照；expected digest、golden 输出、checkpoint payload、HTTP DTO 是否保持不变，并审查两个仅修改输入拼写的 XML fixture。
  3. G2.3 八份 logics.xml 实测深度、128 上限余量、XML→AST→ast_to_json→JCS 的 128 层成功与 129 层 max_xml_depth fail-closed 诊断，确认无 RecursionError。
  4. G2.4 生产与诊断 census、t3-c-v1 完整失败码/消息、G4 未扩展理由、G8 重复统计与键列/来源；确认 JSON 无行内容/主机路径且 contains_row_data=false，不作规则键或去重改动。
  5. G6 .dockerignore 覆盖与其他 COPY 缓存检查、容器内无 .hypothesis、两个 clean worktree 同 project 重建 image ID 相同；核对 source-tree identity 的旧/新值及实现依据。
  6. G7 首次 docker tag seed、base/final tag 始终分离、lock 不变不重建 base、两个不同候选 SHA 的 ensure_client_image 层数相同；确认门禁期间未清理或改 tag。
  7. 核对设计 §14 和本任务停止条件：golden/digest/checkpoint/HTTP DTO 输出变化、import_rules 增长（预期 3/0/14）、AST 结构/语义变化、512 内深度无法容纳或递归失败；核对 V 的完整 runner 日志与三镜像 provenance，以及 H 上 V→H carried 判定日志。
验证：在审核 worktree 中自行运行五包 ruff/mypy 与 import_rules；核对 V 的日志（起止 HEAD、clean status、runner exit code、镜像 provenance），按 AGENTS.md“镜像身份等价”复核 V→H carried。无需重跑全量 runner；如需重跑，按 AGENTS.md 在 clean worktree 整机单飞。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-g2-independent-review.md，作为单独纯文档提交并快进合入 main；除审核报告外不修改文件；不推送、不打 tag。
审核允许结论：通过 / 定向修订 / 整体返工。
```

## 8. 修订轮（G2 定向修订，2026-10-11）

### 8.1 区间与提交

修订后说明：本节为本轮复审后的结果汇总；原 handoff 的历史记录保持不动，与本节覆盖同一验收项时，以本节的修订后状态和新旧对照为准。

- `range_start`: `p5-s1-exit` = `139ee5fffd5b8d3bc229d9a6a5db1a4e06cbfc57`。
- 上次审核对象 H = `c9a09ddb35e4c8c5aaef0a4cba8175ac3488536a`；当前修订基线 main = `ab4db5791d8cbb3344543f1b46d7f2e648c90002`。
- R1 `fix(p5-g2): restore mysqldump set allowlist behavior`：`6a6eb546ec`。
- R3a `fix(p5-g2): cover client dependency base rebuild`：`29f7dfd3c3`。
- R2（含获 owner 同意保留的 F5）`fix(p5-g2): complete real dump census after set repair`：`0889fa953da9116d2fc0722bf1031ecaa7352cf6`，也是门禁提交 V′。
- H′ 是本节追加后的 handoff 提交；精确 SHA 由该提交对象确定。
- 本轮只修 G2-F1、补 G2-F4 测试、重跑并更新 census；G2.2、G2.3、G7 不改。G3、G6b、G8 不实施。`c9a09ddb35..H′` 区间内审核方报告与治理文档按文件路径排除，不作为实现修订范围。

### 8.2 G2-F1：恢复 S1 白名单并关闭四项标准

R1 的 `_allowed_set_name` 在原 `name.lower().lstrip("@")` 与 `old_` / `character_set_` / `collation_` 前缀和 `_ALLOWED_SET_NAMES` 判断之前，只增加精确且大小写不敏感的 `name.lower() == "@saved_cs_client"` 判断。原接受语义全部保留；`@@saved_cs_client` 与其他 `@` 名称仍由原逻辑拒绝。

`MYSQLDUMP_SET_SHAPES` 现有参数表覆盖 10 条标准头部 SET、8 条恢复 SET，以及三种带 `/*!NNNNN ... */` 的 saved-client 形态和大小写变体，共 22 个形态；22/22 均为 `COMPLETE`。拒绝参数表保留 `@@saved_cs_client`、`@other_client`，删除此前错误拒绝、而 S1 本来接受的 `@character_set_client`。

按 G2-F1 关闭标准 2，把 `p5-s1-exit` 的 `_sql_statements.py` 通过 `git show` 复制到 worktree 外临时目录，以真实 owner 解析入口比较相同语句。下表列出 30 个输入；状态为 `FAILED` 的诊断码均为 `UNSUPPORTED_STATEMENT`。只有精确变量名 `@saved_cs_client` 的大小写形式从拒绝变为接受，`@@saved_cs_client` 与其他用户变量的拒绝不变。

| SQL 输入 | `p5-s1-exit` | V′ 实现 |
| --- | --- | --- |
| `/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;` | COMPLETE | COMPLETE |
| `/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;` | COMPLETE | COMPLETE |
| `/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;` | COMPLETE | COMPLETE |
| `/*!50503 SET NAMES utf8mb4 */;` | COMPLETE | COMPLETE |
| `/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;` | COMPLETE | COMPLETE |
| `/*!40103 SET TIME_ZONE='+00:00' */;` | COMPLETE | COMPLETE |
| `/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;` | COMPLETE | COMPLETE |
| `/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;` | COMPLETE | COMPLETE |
| `/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;` | COMPLETE | COMPLETE |
| `/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;` | COMPLETE | COMPLETE |
| `SET TIME_ZONE=@OLD_TIME_ZONE;` | COMPLETE | COMPLETE |
| `SET SQL_MODE=@OLD_SQL_MODE;` | COMPLETE | COMPLETE |
| `SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;` | COMPLETE | COMPLETE |
| `SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;` | COMPLETE | COMPLETE |
| `SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT;` | COMPLETE | COMPLETE |
| `SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS;` | COMPLETE | COMPLETE |
| `SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION;` | COMPLETE | COMPLETE |
| `SET SQL_NOTES=@OLD_SQL_NOTES;` | COMPLETE | COMPLETE |
| `/*!40101 SET @saved_cs_client = @@character_set_client */;` | FAILED | COMPLETE |
| `/*!50503 SET character_set_client = utf8mb4 */;` | COMPLETE | COMPLETE |
| `/*!40101 SET character_set_client = @saved_cs_client */;` | COMPLETE | COMPLETE |
| `SET @SAVED_CS_CLIENT = 1;` | FAILED | COMPLETE |
| `SET @@unique_checks = 0;` | COMPLETE | COMPLETE |
| `SET @@character_set_client = utf8mb4;` | COMPLETE | COMPLETE |
| `SET @character_set_client = utf8mb4;` | COMPLETE | COMPLETE |
| `SET @other_client = 1;` | FAILED | FAILED |
| `SET @OtHeR_Client = 1;` | FAILED | FAILED |
| `SET @@saved_cs_client = 1;` | FAILED | FAILED |
| `SET @saved_cs_client = 1;` | FAILED | COMPLETE |
| `SET @SaVeD_Cs_CliEnT = 1;` | FAILED | COMPLETE |

以上满足关闭标准 1（完整 mysqldump 头尾参数表）、2（接受集合只增加精确 saved-client 名）、3（census 中 t3-c-v1 SQL、物化、composite 与键统计完整）、4（V′ 权威 runner exit 0）。30 条新旧对照明细另存于外部 `g2r-set-allowlist-comparison.log`；未提交对照脚本和临时 S1 文件。

### 8.3 G2-F2 与 G2-F3

本轮依照已恢复的 AGENTS.md carried 第 3 条，在 V′ 的门禁所在主工作区 `/home/dev/gateway-data-management-system` 上做 V′→H′ 检查，不使用新 worktree。V′ 的 repository-service 镜像标签为 `build-input-revision=29f7dfd3c349f9943590765c2b90ca49e47f8eb3`、`source-tree-sha256=sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`；提交后同 worktree 的重算值、backend/worker 同项目重建 ID 与 carried 最终结论见外部 `g2r-carried-check.log`。V′..H′ 只修改本 handoff。

G2-F3 的 `.hypothesis` 与残留目录身份问题关联 owner 决议 G6b；G6b 不在本轮授权范围，本轮未新增 `.dockerignore` 规则、未改变 backend/worker 构建上下文，也不声称关闭 G2-F3。

### 8.4 G2-F4：client dependency base 重建分支

R3a 增加业务行为测试 `test_client_dependency_base_rebuilds_when_lock_and_final_image_are_stale`。测试模拟基础镜像 lock label 与当前 uv-lock 不匹配、最终镜像也不匹配的状态，拦截 `subprocess.run`，断言 `ensure_client_dependency_base_image` 走 `_run_client_dependency_base_build` 的 `docker build` 命令构造；不实际构建镜像。repository_service harness 与 build-context focused 测试合计 147 项通过。

候选 `815ef56a30b3796cb379887d601b4d8a53e91334` 当时没有记录最终镜像层数，不据此补造数值。旧 H 与 V′ 的 final 镜像均为 20 层、独立 base 均为 12 层；V′ runner 后 final ID 为 `sha256:ca24dce188da6548531bb5ea87f1f6c59aaac1ef3d782878d8719c3c19788760`（20 层），base ID 为 `sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764`（12 层），两者 uv-lock label 均为 `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`。V′ 前的 H final 也为 20 层；运行后 base 未变，final 层数未增长。

### 8.5 G2-F5：重复键统计补充

owner 同意保留 F5。`duplicate_key_scan.table_details` 对每张重复表新增排序后的 `differing_columns` 和 `max_group_size`；只序列化列名与计数，不序列化任何行值。参数表覆盖相同行、单列冲突、多列冲突（并验证列名排序）、混合重复组及最大组大小；reader 单次消费也由测试强制验证。

修订后重复键汇总相对原 handoff 为：额外行 `40,748 → 50,565`，完全相同额外行 `0 → 0`，冲突额外行 `40,748 → 50,565`，重复 dataset-table 记录 `136 → 160`；键来源仍全部为 `EXPLICIT_RULE`（原 136、新 160；`DDL_PRIMARY_KEY` 均为 0）。更新后共有 50,565 条重复有效键额外行：完全相同行额外行 0、冲突行 50,565；共有 160 个 dataset-table 重复记录，键来源均为 `EXPLICIT_RULE`（`DDL_PRIMARY_KEY` 来源 0）。160 张重复表均有至少一个 differing column；`differing_columns` 合计 430 个表-列名记录；最大重复组为 1,625 行。所有细分、有效键列、键来源及列名只在 census JSON 中记录；扫描仍为 partial，未解析有效键表不计为无重复。

### 8.6 G2-F6：临时 worktree

完成最后的 carried 检查后，已按要求用 `git worktree remove --force` 清理 `/tmp/gdds-g2-h-check`、`/tmp/gdds-g6-final-a`、`/tmp/gdds-g6-final-b`、`/tmp/gdds-g6-identity-old`、`/tmp/gdds-g6-verify-a`、`/tmp/gdds-g6-verify-b`；保留 `/home/dev/gdds-p5-closure-s1`。没有执行 Docker image/container/volume 清理，也没有移除或重打 `gateway-repository-client-e2e:local` 和 `gateway-repository-client-e2e-base:local`。

### 8.7 census 重跑与新旧对照

真实输入根目录 `/home/dev/gateway-real-dumps` 全程只读；生产与诊断输出仅写到授权的 `census/` 目录。生产路径 8 个 SQL parse 全部 COMPLETE，生产 materialization 与 composite 也全部 COMPLETE。诊断初次尝试因 F5 实现二次消费单次 reader 而得到 `ValueError: table reader is single-consumer and non-rewind`，记录在 `g2r-census-diagnostic.log`；改为单遍 reader 聚合并加单消费测试后，诊断重跑 exit 0，记录在 `g2r-census-diagnostic-retry1.log`。这不是业务数据失败。

| 数据集 | SQL / composite（旧→新） | XML 最大深度 | 重复额外行 / 完全相同 / 冲突 | 重复表 / 已扫描有效键表 |
| --- | --- | ---: | ---: | ---: |
| `rd-t1-a-v1` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 1 | 3 / 0 / 3 | 1 / 102 |
| `rd-t1-a-v2` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 1 | 3 / 0 / 3 | 1 / 102 |
| `rd-t2-b-v1` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 56 | 3,032 / 0 / 3,032 | 16 / 182 |
| `rd-t2-b-v2` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 56 | 2,653 / 0 / 2,653 | 14 / 182 |
| `rd-t3-c-v1` | FAILED `UNSUPPORTED_STATEMENT` / NOT_REACHED → COMPLETE / COMPLETE | 66 | 未评估 → 9,817 / 0 / 9,817 | 未评估 → 24 / 165 |
| `rd-t3-c-v2` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 66 | 9,817 / 0 / 9,817 | 24 / 165 |
| `rd-t4-d-v1` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 97 | 12,616 / 0 / 12,616 | 40 / 279 |
| `rd-t4-d-v2` | COMPLETE / COMPLETE → COMPLETE / COMPLETE | 97 | 12,624 / 0 / 12,624 | 40 / 279 |

除 t3-c-v1 的预期恢复和 F5 两个新增字段外，其他 7 份数据的 census 既有字段与上一版完全一致。t3-c-v1 更新为 199 张源 DDL 表、200 张 materialized 表、268,661 行；角色计数为 `BROWSE_ONLY=13`、`ORDERED_DIFF=54`、`SKIP=8`、`SNAPSHOT_ONLY=4`、`STANDARD_DIFF=120`。其重复键扫描为 partial：165 张有效键表已扫描、27 张键未解析、8 张规则跳过、0 张 reader 不可用。没有暴露后续 AST 结构或业务语义差异，因此没有改 composite AST；八份数据的 max depth 仍为 `1,1,56,56,66,66,97,97`。G4 不适用，现有 SQL 回退扫描触发范围未改。G8 只提供统计，未改规则键或去重行为。

提交 census JSON 的 `contains_row_data=false`，不含行值和主机路径；`differing_columns` 为排序列名。生产输出、诊断输出、字段对照记录见外部 `g2r-census-production.log`、`g2r-census-diagnostic-retry1.log`、`g2r-census-compare.log`。

### 8.8 V′ 门禁与镜像 provenance

V′ = `0889fa953da9116d2fc0722bf1031ecaa7352cf6`。preflight clean，`pgrep -x dolt` 无进程、无 Compose project 标签容器、8000 端口空闲。按顺序重建 repository-service 镜像并运行 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；runner 起止 HEAD 相同、status clean、自身 exit code 0。批次：shared_kernel 242 passed；repository_contracts 152 passed；repository_client 154 passed；backend 2,734 passed / 1 warning；repository_service parallel 1,681 passed / 1 skipped；serial 205 passed / 1,682 deselected。

Compose provenance project=`ordered-bisect-b-1055182-baseline`，三个实际运行镜像如下：

| 镜像 | Image ID | labels 摘要 | 层数 |
| --- | --- | --- | ---: |
| backend | `sha256:668e532f9771d2bda53247e2236cb5d26a1ba67fd925c57c2f61f199dfe3ede2` | project=`ordered-bisect-b-1055182-baseline`, service=`backend` | 15 |
| repository-service | `sha256:e184e610e4066ecfbcf87e72bcbf6d12d994d8993ece7b0621eae6916e76191e` | revision=`0889fa953da9116d2fc0722bf1031ecaa7352cf6`; build-input-revision=`29f7dfd3c349f9943590765c2b90ca49e47f8eb3`; source-tree=`sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`; uv-lock=`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` | 28 |
| worker | `sha256:55dd7a9f88306f86d870190328a5e5596ccd4cea8a0bfbf285067ebe7512cd41` | project=`ordered-bisect-b-1055182-baseline`, service=`worker` | 15 |

构建日志、runner 日志、provenance 原件副本和三个 image inspect 记录分别为外部 `g2r-repository-service-build.log`、`g2r-runner.log`、`g2r-compose-provenance.json`、`g2r-images-inspect.log`；preflight 为 `g2r-preflight.log`。提交后静态与 focused 检查汇总见 `g2r-focused-checks.log`。

停止条件核查：golden、digest、checkpoint payload、HTTP DTO 均未变化；`import_rules` 仍为 3 violations / 0 runtime cycles / 14 unreachable；G2.2/3 与 AST 语义未改；t3-c-v1 composite COMPLETE；设计 §14 停止条件未触发。门禁期间没有写 worktree、提交、外部重建/重打镜像或 Docker 清理。

### 8.9 V′ → H′ carried

按 AGENTS.md 镜像身份等价第 3 条，在 V′ 门禁运行的同一主工作区完成 post-commit identity 重算和 backend/worker 同 project 重建。V′..H′ 只修改本 handoff；RS 的 build-input/source-tree identity 与 V′ provenance labels 一致；backend/worker rebuilt IDs 与 V′ provenance 中实际运行 IDs 一致，因此 carried 判定为 **true**。完整身份值、重建命令与同一性比较记录在外部 `g2r-carried-check.log`。
