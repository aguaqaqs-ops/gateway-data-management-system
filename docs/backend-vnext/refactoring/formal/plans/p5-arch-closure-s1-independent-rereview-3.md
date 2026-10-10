# P5 架构收口 S1 独立审核（第 3 次复审）

- 结论：**通过**
- 日期：2026-10-10
- 审核对象：p5-closure/s1 @ `442473b09ad7aa4948f85ee435342e57b9fe0e46`（H；实现 HEAD `ce12e245286e367d1e7e86d65a8b3a428cfb813e`；门禁提交 V `d9c2097612036c05741c98b702d518d54571ece2`），
  base main @ `218c211240b33e01eee1eb8965fdcca0ec4b8099`；V 合入了 main `5fe02db3a719eb064e3a8fce44b39056afc3321f`，因此当前 merge-base 即该提交。
  上次审核对象为 `96071affd490b728aa62fe4a6f0ee9e784e42466` 加未提交补丁 `492cce95…`，见 `plans/p5-arch-closure-s1-rereview-2-repair-report.md`。
- 范围：`96071affd4..442473b09a` 的差异（fix `ce12e24528`、docs `a371d55bbe`、merge main = V、H），原 finding 的关闭情况与改动传播。
  `vnext/` 下该区间只有 `real_dump_census.py` 与 `test_real_dump_census.py` 两个文件。
- 依据：执行计划 §2 S1、§3 S1、§6、§7、§8；设计 §9；纵切指南 §7；AGENTS.md「权威入口的运行前提」与「镜像身份等价」；testing-conventions；handoff。
- 审核在只读 detached worktree（`/home/dev/gdds-review-s1-r3`）中进行，没有在实施 worktree 写入文件；本报告是该 worktree 中唯一的新增文件。

## 1. 结论摘要

第 2 次复审留下的 F6、F8、F11、F12、N2–N5 都已关闭，F1–F10 没有被这一轮改动影响。S1 的阶段退出门禁满足：V 上的权威 `run-tests.sh`
第 3 次完整运行 exit 0（backend 2704、RS 并行 1678 + 1 skipped、RS 串行 205 全部通过），前两次失败只来自 client e2e 测试镜像的构建环境；V → H 只改一个 handoff 文档，
镜像身份等价（`carried`）判定成立。`import_rules` 为 3 / 0 / 14。

没有阻塞项。本次发现 4 项非阻塞问题（R3-F1 至 R3-F4），都不影响 S1 合入：其中两项是 S1 暴露的、尚未登记承接的后续事项
（backend/worker 镜像身份依赖本地缓存目录；真实数据中存在重复有效键），一项是测试 harness 的叠层缺陷，一项是文档记录的小偏差。
这些问题应在合入后登记到治理修订计划，并在 G2 之前或随 G2 处理，不由 S1 修复。可以合入 `main`；进入 S2a 之前须完成治理修订计划 G2 与本报告 R3-F3 的 owner 决议。

“原复审 finding 已关闭”与“S1 阶段退出门禁已满足”是两个独立结论，本报告的结论是两者都成立。

## 2. Findings

### R3-F1：backend/worker 镜像的 image ID 依赖构建 worktree 里的未跟踪缓存目录

- 类型：已证实缺陷；是否阻塞：否
- 位置：`vnext/.dockerignore`（没有排除 `**/.hypothesis`）；`vnext/backend/Dockerfile:34`（`COPY shared_kernel /app/shared_kernel`）；
  AGENTS.md「镜像身份等价」第 3 条与 testing-conventions「镜像身份等价与结果沿用」第 3 条。
- 依据：
  - 门禁用的 backend 镜像 `sha256:020c387c…` 中实测存在 `/app/shared_kernel/.hypothesis`（108 KB，来自 worktree 里被 git 忽略的 Hypothesis 缓存）。
  - 在干净的 detached worktree（同一提交内容）里用 provenance 记录的 project 名重建 backend/worker：缓存只命中到 `COPY backend/...` 层，
    自 `COPY shared_kernel` 起全部未命中，与实施方在原 worktree 中的结果（57 步中 42 步命中）不同。我在约 10 分钟后中止了这次构建，没有得到新的 image ID，
    所以“ID 会不同”是由缓存失配推断，而不是直接观测。
- 触发场景与影响：
  - backend/worker 的 image ID 不是源码树的函数：同一提交在不同 worktree 中、或同一 worktree 在两次构建之间运行过 shared_kernel/backend 测试后，ID 都可能不同。
  - carried 判定的 (c) 项因此只有在“同一 worktree、两次构建之间没有测试写入缓存目录”时才有意义；本次 (c) 满足这些条件（实施方在原 worktree 中立即重建，ID 相同）。
    规则文本没有写明这些前提，换一个人或换一个 worktree 复核会得到假的“不等价”，反过来也可能掩盖缓存目录之外的差异。
  - 开发缓存会被打进镜像，不属于 production 内容。
- 最小修正方向：
  1. 把 `**/.hypothesis` 加入 `vnext/.dockerignore`。这改变构建上下文，按 AGENTS.md 属于必须重建并重跑容器门禁的改动，应并入 G2 的门禁一起验证。
  2. 在此之前，AGENTS.md 与 testing-conventions 的 carried 第 3 条写明前提：在 V 的 worktree 中重建，两次构建之间不运行任何测试。
  3. 可选：给 backend/worker 增加与 RS 同类的 source identity label，把判定从 image ID 改为 label。
- 关闭标准：规则文本与 `.dockerignore` 已修订；下一次阶段门禁中 backend/worker 镜像内没有 `.hypothesis`，且从干净 worktree 重建的 ID 与门禁一致。

### R3-F2：RS 测试 harness 的 client e2e 镜像以自身为基础镜像，叠层会随候选更换持续增长

- 类型：已证实缺陷；是否阻塞：否（handoff 已如实记录，S1 不改该 harness）
- 位置：`vnext/repository_service/tests/support/compose_lifecycle_harness.py` 的 `client_dependency_base_image`（默认候选为镜像自身）与 `_run_client_build`（`BASE_IMAGE=<自身 tag>`、`-t <同一 tag>`）。
- 依据：`final-client-image-depth.log` 记录该镜像有 124 个 rootfs 层、`docker history` 293 条；`final-run-tests.log` 中两项失败都以 `failed to prepare … max depth exceeded` 结束，
  构建日志第 5 步是 `FROM docker.io/library/gateway-repository-client-e2e:local`。
- 触发场景与影响：只要镜像带有相同的 uv-lock label，换一个候选 SHA 就重建一次并叠加在上一版之上；层数到达 overlay2 上限后，所有依赖该镜像的 Compose 用例失败，
  报错信息指向 buildkit，而不是 harness。处置方式只能是手工 `docker rmi`，而这又会失去预装依赖基础镜像，使下一次构建在慢网络上超时（本次运行 2 的成因）。
- 最小修正方向：依赖基础镜像与最终测试镜像使用不同 tag，基础镜像只在 uv-lock 变化时重建；或者在构建前检查层数并重建。修改 harness 属于 AGENTS.md 的强制重建项，随 G2 的门禁一并验证。
- 关闭标准：连续在两个不同候选 SHA 上运行权威 runner，client 镜像层数不增长。

### R3-F3：真实数据中存在重复的有效键，与 Canonical Storage 的整表唯一要求冲突，尚无承接

- 类型：待验证假设（census 事实已证实；其后果未验证）；是否阻塞：对 S1 否，对 S2b 的 DC22 是
- 位置：`plans/p5-arch-closure-s1-census.json`（`duplicate_key_scan`）；Canonical Storage §3（“普通 canonical keyed table 必须验证 effective key 存在且 retained、tuple 非空、整表唯一……不得用 dedup、last-write-wins”）；设计 §4.2（“无键、重复键、缺键按 Canonical Storage §3 fail closed”）。
- 依据：
  - t1 每份数据在 `b1_n2_iec104_syx_list` 有 3 条额外行；t2 v1 有 3,032 条（16 张表），v2 有 2,653 条（14 张表），集中在各 `b1_n<k>_iec104_syx_list`（每张 362 条）与 `_yc_list`（每张 17 条）。
  - 这些统计是 partial 的：t1 只覆盖 102/133 张表，t2 只覆盖 181/216 张表，未覆盖表中也可能有重复；t3/t4 未评估。
- 触发场景与影响：按现行契约，这些表在 Preview 的投影阶段会 fail closed。DC22 要求 4 份 dump 经公开 HTTP 完成 Preview → Submit → History，t1、t2 的 Preview 因此不能成功，
  除非先决定这些重复是“规则里的有效键定义不对”“该表不应作为 canonical keyed table”还是“源数据需要清理”。handoff 与治理修订计划都没有登记这个后果和决议人。
- 最小修正方向：由 owner 在 S2a kickoff 前决议处置方向，并在 S2a 验收中写明 DC22 对这些表的预期结果。契约明确禁止 dedup 与 last-write-wins，所以处置只能落在规则键定义、表角色或数据本身上，不能由实现侧悄悄去重。
  G2 修复后的普查重跑应同时补齐 t3/t4 与未覆盖表的统计。
- 关闭标准：决议写入决议记录，并体现在 S2a/S2b 的验收文字中。

### R3-F4：文档记录的小偏差

- 类型：已证实缺陷；是否阻塞：否
- 位置与事实：
  1. 决议记录 §10 与 handoff §1 写“S1 不修改 `table_access` 与 `composite_signal` 的生产代码”。相对授权基线，S1 改过 `composite_signal/__init__.py` 与 `contracts.py`
     （把 `materialize_composite_signal` 的惰性包装从 contracts 移到 facade，提交 `a5a62e58d3`、`d42a740e7d`，属于 §3 A7 预算）。`table_access` 没有改动。
     这一轮（`96071affd4..H`）两者都没有改。应改写为“S1 未改动 G2 涉及的解析逻辑（`_sql_statements.py`、`_ast.py`、`max_xml_depth`）”。
  2. handoff traceability 的 `merge_base_with_main` 仍为 `218c2112`；V 合入 main 之后实际为 `5fe02db3a7`。
  3. 执行计划 §8.5 仍写“自 `main` 切分支（例如 `p5-closure/s1-parser`）”，与治理修订计划 G2（在 `main` 上实施）不一致；计划已声明由 G1 改写，合入后一并处理。
  4. handoff §6.3 称主机到 PyPI“约 60 KB/s（实测 20 秒下载 1.16 MB）”，没有日志支撑；运行 2 的日志里 27.1 MB 的 uv 轮子是以 671.6 kB/s 下载的。不影响结论，建议删除或补日志引用。
- 最小修正方向：合入后在 `main` 上以一个文档提交更正。
- 关闭标准：上述文字已更正。

## 3. 验收核对

| 验收项（执行计划 §2 S1） | 结果 | 证据 |
| --- | --- | --- |
| import 违例基线只剩 3 条，运行时环基线为空，不可达 14 项 | 满足 | 审核者在 H 上读取 `IMPORT_RULE_BASELINE`、`RUNTIME_CYCLE_BASELINE`、`UNREACHABLE_MODULE_BASELINE`：3 / 0 / 14；`import_rules` 实际输出与基线一致（`test_architecture.py` 通过）；`96071affd4..H` 对 `architecture_baseline.py`、`import_rules.py`、`test_architecture.py`、`backend/src` 无改动 |
| golden、digest、checkpoint 载荷、HTTP DTO 不变 | 本轮未受影响 | `96071affd4..H` 的 `vnext/` 差异只有普查脚本与其测试；backend 全量 2704 项在 V 上通过 |
| 阶段退出：权威 runner 在已提交 clean worktree 上 exit 0 | 满足 | 见 §4 第 7 行：`final-rerun2-*`，runner exit 0 |
| 容器门禁绑定最终候选 | 满足（`carried`） | V → H 只改 handoff；RS 身份重算相等；backend/worker ID 在原 worktree 重建相等；见 §4 第 9–11 行与 R3-F1 |
| S1 未改 container 边界 | 满足 | 相对授权基线，`backend/Dockerfile`、`deploy/`、`repository_service/Dockerfile`、五个 `uv.lock` 与另外四个包均无 diff |
| 真实数据记录完整且不把缺失读成“无重复” | 满足 | 8 份记录、`pair_of`、partial/not_evaluated 标注；见 §6 F6、N2 |

## 4. 实际执行的检查

| # | 检查 | 命令或方法 | 结果 |
| ---: | --- | --- | --- |
| 1 | 审核对象与差异 | `git rev-parse HEAD`；`git log 96071aff..HEAD`；`git diff --name-only d9c2097612 HEAD`；`git diff --stat 96071aff HEAD -- vnext` | tip = `442473b09a`；V → H 只含 `p5-arch-closure-s1-handoff.md`；`vnext/` 只有两个 census 文件 |
| 2 | handoff 哈希 | `git rev-parse ce12e24528^{tree} d9c2097612^{tree}`；`git diff 96071aff ce12e24528 -- vnext/ \| sha256sum` | `6bde5405…`、`4ea3ce28…`、`b5542b16…`，与 handoff 一致 |
| 3 | gate 时的树与最终补丁的差异 | `git diff db2809090d ce12e24528 -- vnext/` | 只有测试改为参数表 `KEY_SCAN_COVERAGE_SHAPES`，脚本逻辑未变 |
| 4 | focused 测试 | 实施 worktree 的 venv 解释器 + `PYTHONPATH` 指向审核 worktree 源码（已确认 `gateway_backend` 从审核 worktree 导入）；`pytest -m unit tests/test_real_dump_census.py tests/test_architecture.py` | 87 passed |
| 5 | backend 静态检查 | 同上，`ruff check --no-cache .`；`mypy` | pass；464 个文件 |
| 6 | 其余四包静态检查 | 读 `final-precommit-static.log`；`git diff --stat 218c2112 HEAD` 对四个包 | 全部 pass（34/15/26/198 个文件）；相对授权基线四个包无 diff。审核者没有重跑 |
| 7 | V 的三次完整运行 | 读 `final-*`、`final-rerun-*`、`final-rerun2-*` 的 `*-run-tests.log`、`*-summary.log`、`*-preflight.log` | 运行 1、2：exit 1；运行 3：exit 0；三次起止 HEAD 均为 V，`status_porcelain` 均为空，前置检查均通过 |
| 8 | 前两次失败原因 | 读失败 traceback | 运行 1：`test_compose_wrong_network_cleans_up`、`test_compose_remote_client_commit_pinned_read_inside_network`，均为 client 镜像构建 `max depth exceeded`；运行 2：`test_compose_wrong_network_cleans_up`，`uv sync` 下载 `pyarrow==25.0.0` 超时（“Request failed after 4 retries in 129.3s”）。没有任何用例断言失败；计数 203+2、204+1、205 对得上 |
| 9 | harness 叠层缺陷 | 读 `compose_lifecycle_harness.py:772–840`；读 `final-client-image-depth.log`、`final-cleanup.log`、`final-rerun2-client-image.log` | 属实：`BASE_IMAGE` 取自身 tag；124 层；运行 3 复用运行 2 中构建的镜像（12 层，revision label = V） |
| 10 | carried (b)：RS 身份 | 在审核 worktree 运行 `build_context_digest.py identity`；`docker image inspect gateway-repository-service:local` | `build-input-revision 4d1dc010…`、`source-tree-sha256 sha256:62a38a08…` 与镜像 label 相等；`org.opencontainers.image.revision` 为 V，按规则不参与比较 |
| 11 | carried (a)(c) | 读 `final-carried-check.log`、`final-carried-rebuild.log`、`final-rerun2-compose-provenance.json`；`docker image inspect` 当前 tag | (a) 只有文档；(c) 实施方用 provenance 中的 project 名在原 worktree 重建，ID `020c387c…`、`a1a8185c…` 与 provenance 相等；当前 tag 仍指向这两个 ID。**审核者自己的重建没有完成**，见 R3-F1 与 §5 |
| 12 | 镜像内容 | `docker run --rm --entrypoint sh <backend 镜像> -c 'ls -a /app/shared_kernel; find /app -name .hypothesis'` | 存在 `/app/shared_kernel/.hypothesis`（108 KB） |
| 13 | census JSON | 脚本核对：8 份记录、`pair_of`、各覆盖计数之和、无主键表与显式键之和、有无主机路径与行数据 | t1：102+23+8=133；t2：181+27+8=216；23+5=28、27+13=40；重复行之和 3 / 3,032 / 2,653 与 handoff 表一致；无主机路径、`contains_row_data=false` |
| 14 | 范围核对 | `git diff 218c2112 HEAD -- table_access composite_signal` | `table_access` 无改动；`composite_signal` 只有 facade 包装搬迁（R3-F4 第 1 点） |
| 15 | handoff §6.6 实测更正 | 对照 `rereview2-*` 日志与 `docker image inspect` | 更正 a–d 属实；e 表 7 次补跑的数量、耗时、失败原因与日志一致；`dolt children remain` 只出现在 `fresh_restart` 一项的链式异常中，另两项失败是测试环境缺包（`wrong_token`：`failed` ≠ `unauthorized`；`gate_host`：consumer 导入失败） |

## 5. 验证限制与剩余前置

- **没有读取真实数据**（`summary.json`、dump 目录），因为没有读取授权；census JSON 只做内部一致性核对。
- **没有重跑全量 runner、Compose 旅程或镜像构建。** V 的门禁结果取自实施方的日志；日志的起止 HEAD、状态与 exit code 已逐项核对，
  但“运行期间没有写 worktree”只能由首尾 `git status --porcelain` 为空来佐证。
- **carried 的 (c) 项没有被独立复现。** 我的重建从干净的 detached worktree 出发，缓存在 `COPY shared_kernel` 处失配，约 10 分钟后被我中止（用 `pkill -f` 时误杀了自己的 shell，`docker` 标签与两个 worktree 状态已核对，都未被改变）。
  这一失配与 R3-F1 的机制一致，所以 (c) 的成立依赖于：实施方日志、V → H 只改一个不在构建上下文内的文档（构建上下文是 `vnext/`，handoff 在仓库根的 `docs/` 下）、以及 (b) 的独立复现。
  我认为 `carried` 成立，但这是在 (c) 未独立复现的前提下作出的判断。
- Compose provenance 文件只记录最后一次旅程的容器镜像；其余 8 个旅程各自使用以各自 project 命名的镜像，内容相同但 ID 不同（见 handoff §6.3）。
- focused 测试用的是实施 worktree 的 venv 解释器，不是在审核 worktree 里新建的环境（该主机访问 PyPI 很慢）。
- 门禁依赖的 client e2e 镜像是运行 2 构建的，运行 3 复用；harness 的这一行为本身属于 R3-F2。
- 第 2 次复审中我对 N4 的判断有误（把 t2 的 composite 失败当成 S2b 的阻塞项），也误把 `dolt children remain` 当作 3 项失败的共同原因。实施方按日志核对后已更正，本次复核确认更正是对的。
- 进入 S2a 之前须满足：
  1. 合入 `main`，打阶段 tag；
  2. 治理修订计划 G1、G5（主线开发规则）；
  3. G2 真实数据格式保真前置（`@saved_cs_client`、`Digital value`、XML 深度），含普查重跑；
  4. R3-F3 的 owner 决议；
  5. R3-F1、R3-F2 随 G2 的门禁处理，R3-F4 的文字更正。
- 延期项：control DB migration 是否合并为基线 schema（治理修订计划 G3），由 owner 在 S2a kickoff 前决议。

## 6. 复审记录

| 原 finding | 关闭情况 | 依据 |
| --- | --- | --- |
| F1、F2、F7、F9 | 保持关闭 | 本轮 `vnext/backend/src` 无改动 |
| F3、F4、F5、F10 | 保持关闭 | `96071affd4..H` 没有改动基线或 `import_rules`；3 / 0 / 14；设计 §9 与执行计划（第 93、173 行）、handoff §4 均为 14；决议记录 §10 登记了 10→14 |
| F6 | **已关闭** | 8 份记录，覆盖计数之和与 handoff 一致；t1、t2 标为 partial 并列出范围；t3/t4 标为 `not_evaluated_materialization_failed`；`pair_of` 与跨规模档不配对的确认已登记；后果见 R3-F3 |
| F8 | **已关闭** | traceability 的 `last_committed_implementation_head`、补丁 SHA、tree 逐项核对一致；handoff §6.6 更正 a–e 与日志一致（残留见 R3-F4） |
| F11 | **已关闭** | 在已提交 clean worktree 的 V 上，权威 runner exit 0；前两次失败成因经日志与源码核实；V → H 的 `carried` 判定：(a)(b) 已独立复现，(c) 见 §5；R3-F1、R3-F2 为后续项 |
| F12 | **已关闭** | t2 的 `COMPOSITE_LOGIC_FAILED` 现在由诊断模式下的 SQL 回退扫描继续统计；完整消息写入 JSON；承接为 G2，且不阻塞 S2b 的 DC22（composite 与 XML 解析器处于不可达基线，生产路径只走 SQL 物化） |
| N2 | **已关闭** | `_duplicate_and_effective_key_stats` 在存在未解析表或 reader 不可用时标 `partial`；`KEY_SCAN_COVERAGE_SHAPES` 三种形态（全部扫描、未解析 + 规则跳过、reader 不可用）收敛为一个参数化测试，无重复函数，带 `unit` 标记，没有引入 dolt fixture |
| N3 | **已关闭** | implementation_head、`run-tests-r2.log` 的存在、历史镜像身份未证实、代码围栏均已更正 |
| N4 | **已关闭（原判断撤回）** | t2 不阻塞 S2b；承接为 G2。原“阻塞 S2b”的判断是错的 |
| N5 | **已关闭** | handoff §6.6.2 的 a–e 与日志一致；7 次 RS 补跑逐次列出 |
