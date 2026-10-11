# P5 架构收口 G2（含 G6、G7）独立审核

- 结论：**定向修订**
- 日期：2026-10-11
- 审核对象：main @ `c9a09ddb35e4c8c5aaef0a4cba8175ac3488536a`（H；门禁提交 V = 实现 HEAD = `84177001e1858d78edf39c541242cef22e836547`），区间 `p5-s1-exit..H`。
  区间内 `50fb0c862b`、`47e9f8c34c` 是审核方提交的治理文档；实现方提交是 `3f0047139b`、`a19ae6e8be`、`b90b4f46c3`、`e3dcd8a7bc`、`6fd40aa0f4`、`84177001e1`（V）和 `c9a09ddb35`（H，仅 handoff 与治理计划状态行）。
- 依据：治理修订计划 G2、G6、G7；执行计划 §2、§3、§8；设计 §14；AGENTS.md「权威入口的运行前提」「镜像身份等价」；testing-conventions；handoff `plans/p5-arch-closure-g2-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-g2`（H）中进行，没有在主工作区运行测试。除 worktree 外还做了三类只写 Docker 的探针：
  临时 project/tag 的 backend/worker 构建、临时 tag 的 client 镜像构建（均已按 ID 清理，没有 prune，没有触碰 `gateway-repository-client-e2e*` 与任何实现方镜像），
  以及在主工作区（V 的门禁 worktree）用 V 的 project 名重建 backend/worker 复核 carried。主工作区的文件没有被写入。
- 审核者没有读取真实数据（`GATEWAY_REAL_DUMP_ROOT`），census 的运行结果没有被独立复现，只核对了提交内 census JSON 的内部一致性。

## 1. 结论摘要

G2.2（Digital 小写 `value`）、G2.3（`max_xml_depth=128` 与全链路递归边界）、G7（client 镜像分层）和 V 的权威门禁都成立；`import_rules` 为 3 / 0 / 14，golden、digest、checkpoint、HTTP DTO 没有变化。
G6 排除了 `.hypothesis`，但“在干净 worktree 重建 image ID 与门禁一致”这条验收没有达成（G2-F2）。

**一项阻塞项**：G2.1 把 `SET` 白名单收紧得比 `p5-s1-exit` 更严。`p5-s1-exit` 接受所有以 `@` 开头的 `old_*` / `character_set_*` / `collation_*` 与白名单名字（`name.lower().lstrip("@")`），
H 对任何 `@` 开头的变量只接受 `@saved_cs_client`。标准 mysqldump 文件头的 8 条 `SET @OLD_…` 语句因此从“接受”变成“拒绝”，这正是 `rd-t3-c-v1` 在 census 中失败的原因
（S1 census 里该数据集已能解析出 199 张 DDL 表，H 的记录是 0 张）。起因包含任务提示词的错误前提（见 G2-F1），但结果必须修正：G2 的目标是让真实 dump 能解析，而不是让原来能解析的 dump 失败。

另有一项须修订的文档问题（G2-F2，审核方已在本报告之后的提交中直接修订文字）和四项非阻塞问题。
修正 G2-F1 会改变生产 SQL 解析并使 backend/worker 镜像内容变化，所以必须在新的门禁提交 V′ 上真实重建并完整运行权威 runner，不能沿用 V。`p5-g2-exit` 暂不打；复审通过后在复审报告提交上打。

“原任务验收项已满足”与“阶段退出门禁已满足”分开记录：G2.2、G2.3、G6 的 `.hypothesis` 部分、G7 与 V 的门禁已满足；G2 作为阶段尚未满足，因为 G2.1 的行为回退使 census 的八份数据中仍有一份不能 COMPLETE，且该失败由 G2 自己引入。

## 2. Findings

### G2-F1：G2.1 收紧了 `SET` 白名单，标准 mysqldump 头尾语句从“接受”变成“拒绝”

- 类型：已证实缺陷（行为回退）；是否阻塞：是
- 位置：`vnext/backend/src/gateway_backend/capabilities/table_access/_sql_statements.py:832`（`3f0047139b`）；
  `vnext/backend/tests/test_table_access_sql_rejects.py:26-34`（新增三条拒绝用例，其中 `@character_set_client` 一条与原行为相反）；
  `vnext/backend/tests/test_table_access_sql_parser.py:17`（`MYSQLDUMP_SET_SHAPES` 没有覆盖标准文件头）；handoff §2 G2.4 对 `rd-t3-c-v1` 的说明。
- 依据：
  - `p5-s1-exit` 的实现是 `lowered = name.lower().lstrip("@")`，随后判断 `old_` / `character_set_` / `collation_` 前缀与 `_ALLOWED_SET_NAMES`；H 的实现是 `if lowered.startswith("@"): return lowered == "@saved_cs_client"`。
  - 我在审核 worktree 中用同一个解析入口（`tests/support/table_access_sql.parse_text`）对两种实现逐条运行：

    | 语句（mysqldump 标准输出） | `p5-s1-exit` + 仅加 `@saved_cs_client` | H |
    | --- | --- | --- |
    | `SET @saved_cs_client = @@character_set_client` | COMPLETE | COMPLETE |
    | `SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT` | COMPLETE | **FAILED** `SET @OLD_CHARACTER_SET_CLIENT is not in the source dump allowlist` |
    | `SET @OLD_CHARACTER_SET_RESULTS=…`、`@OLD_COLLATION_CONNECTION=…`、`@OLD_TIME_ZONE=…`、`@OLD_UNIQUE_CHECKS=…, UNIQUE_CHECKS=0`、`@OLD_FOREIGN_KEY_CHECKS=…, FOREIGN_KEY_CHECKS=0`、`@OLD_SQL_MODE=…, SQL_MODE=…`、`@OLD_SQL_NOTES=…, SQL_NOTES=0` | 全部 COMPLETE | 全部 **FAILED**（各自报同样形式的消息） |
    | `SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT`、`SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS`（文件尾） | COMPLETE | COMPLETE |
    | `SET @@unique_checks = 0`、`SET @@character_set_client = utf8mb4` | COMPLETE | **FAILED** |
    | `SET @other_client = 1`、`SET @@saved_cs_client = 1` | FAILED | FAILED |

  - census 对照：`p5-s1-exit` 的 census JSON 里 `rd-t3-c-v1` 有 `source_ddl_table_count: 199`、完整的 `role_table_counts` 与 `storage_column_type_counts`，失败只在 XML 深度；
    H 的 census 里同一数据集 `source_ddl_table_count: 0`、各计数为空，失败码 `UNSUPPORTED_STATEMENT`，消息 `SET @OLD_CHARACTER_SET_CLIENT is not in the source dump allowlist`。
    其余七份 SQL 解析 COMPLETE，说明它们不含这些 `@OLD_*` 语句（这是由 census 结果推断的，我没有读数据）。
  - 任务提示词（审核方撰写）写明“`@@saved_cs_client` 与其他 `@用户变量` 仍拒绝”，这一前提与 `p5-s1-exit` 的实际行为不符；实现方按提示词收紧了行为，所以起因在提示词。
    但 census 与 S1 记录的对照本该暴露回退（一个原本能解析出 199 张表的数据集变成 0 张），handoff 却把它写成“未授权的第二种用户变量”，没有与 `p5-s1-exit` 的行为比较。
  - 没有任何现有 golden 或测试覆盖标准 mysqldump 文件头，所以 V 与 H 的完整门禁都没有发现这一回退。
- 触发场景与影响：任何带标准 mysqldump 文件头（`/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;` 等）的上传，在 `p5-s1-exit` 之前能通过 SET 白名单，现在以 `UNSUPPORTED_STATEMENT` 失败。
  这直接影响现行生产路径（上传只走 SQL 物化），并使 `rd-t3-c-v1` 的 composite 与重复键统计不可得，G8 的决议依据缺一份数据。
- 最小修正方向：保持 `p5-s1-exit` 的白名单语义不变，只增加一个精确名。例如在原有 `lstrip("@")` 逻辑之前加一行，仅当 `name.lower() == "@saved_cs_client"` 时返回 True；
  `@@saved_cs_client` 与 `@other_client` 仍落入原逻辑并被拒绝。删除与原行为相反的 `@character_set_client` 拒绝用例，保留 `@@saved_cs_client`、`@other_client`；
  把标准 mysqldump 文件头和文件尾的全部 `SET` 语句（上表 8 条 `@OLD_*` 头语句 + 恢复语句）加入 `MYSQLDUMP_SET_SHAPES` 参数表。
- 关闭标准：
  1. 参数表覆盖标准 mysqldump 文件头尾全部 `SET` 语句并 COMPLETE；
  2. 与 `p5-s1-exit` 相比，接受集合只多出 `@saved_cs_client`，拒绝集合不变（复审时用同样的逐条对照复验）；
  3. census 重跑：`rd-t3-c-v1` 的 SQL 解析 COMPLETE；其 composite 阶段、重复键统计、最大深度按实际结果更新 JSON 与 handoff 的汇总数字（G8 统计会变）；
     若该数据集出现新的失败，登记完整失败码与消息，不放宽其他规则；
  4. 新的门禁提交 V′ 上完整权威 runner exit 0（见 G2-F2 对 carried 判定的要求）。

### G2-F2：G6“clean worktree 重建 image ID 与门禁一致”未达成，规则文字被提前改写

- 类型：已证实缺陷（验收未满足；文档过度声明）；是否阻塞：文档部分须随本轮修订，门禁与 S2a 不依赖它
- 位置：AGENTS.md「镜像身份等价」第 3 条（`6fd40aa0f4`，第 171 行起）；`docs/backend-vnext/testing-conventions.md` 第 183 行起；handoff §3；`g2-carried-check.log`；
  治理修订计划 G6 验收（“在干净 worktree 重建的 image ID 与门禁一致”）。
- 依据：
  - 实现方在新建的 `/tmp/gdds-g2-h-check` 里重建，得到的 backend/worker ID 与 V provenance 不同，判定 `carried=false`，随后在 H 上又完整跑了一次权威 runner（exit 0）。
    handoff 把差异归因于“9 个 `.dist-info` 生成元数据文件”，那只是缓存失配后重新执行 `uv sync` 的结果，不是原因。
  - 原因：两个镜像的前 6 层相同，从 `COPY repository_client` 起分叉。该层内容的文件元数据不同：V（主工作区）文件 644、目录 755（G7 新增的两个文件 664），
    `/tmp/gdds-g2-h-check` 的文件 664、目录 775，mtime 也不同。BuildKit 的 COPY 缓存键包含权限位，所以这一层以及之后所有层都重新构建。
  - 我用两次探针把原因隔离：① 新建审核 worktree（umask 0002，权限位与 H 检查 worktree 相同，mtime 更晚）用临时 project 构建：全部步骤 CACHED，层与实现方 H 重建的镜像完全一致（mtime 不是缓存键）；
    ② 只把审核 worktree 里 `repository_client` 的 `src/`、`tests/`、`pyproject.toml` 去掉 group 写权限（git status 仍然干净）再构建：`COPY repository_client` 及其后全部步骤未命中并重新执行（`uv sync` 21 s 与 77 s）。
  - 复核 carried：在主工作区（V 门禁运行的同一 worktree）、HEAD = H、用 V 的 project 名 `ordered-bisect-b-3655597-baseline` 重建 backend/worker，得到
    backend `sha256:1487ab34eb775bb8caefb8a761fcf19f34d5aede142af920954d48e4ddee34bb`、worker `sha256:7ff0e7548cfb4cc51cc9104ac218b651b76b11ed6f3efbe44fae91c79e649e49`，与 V provenance 完全相同（构建步骤均命中缓存）。
    RS 在审核 worktree 重算的身份 `build_input_revision=84177001e1…`、`source_tree_sha256=sha256:ff8cbb8fbd…` 与 V 的 RS 镜像 label 相同；`V..H` 只改 handoff 与治理计划两个文档。三条件都成立，**V → H 的 `carried` 应为 true**。
  - G6 的验证记录不能证明跨 worktree 可复现：`g2-g6-final-clean-worktrees.log` 里第一次构建的 #8–#28 全部 CACHED，缓存来自同一提交在兄弟 worktree 里的更早构建，两次相等只说明命中了同一份缓存。
- 影响：
  - backend/worker 的 image ID 不是源码树的函数，而取决于 worktree 的权限位（git 只记录可执行位，权限位由创建文件的 umask 决定）和 BuildKit 缓存状态。跨 worktree 重建在缓存命中之外不可复现。
  - 实现方在 `/tmp` 的新 worktree 中核对 carried，得到了一个假的“不等价”，多跑了一次完整门禁（约 26 分钟，另有一次因缺 `.venv` 与 `legacy/` 而失败的首次尝试）。没有安全影响：H 因此有自己的 runner exit 0。
  - AGENTS.md 与 testing-conventions 现在写“可在任一 clean worktree 中重建”，与上面的事实不符；原先“只接受同一 worktree 内比较”的限制恰好避免了这次误判。
- 最小修正方向：把限制恢复并写明原因（同一 worktree、缓存仍在；权限位与未跟踪状态进入构建上下文）；G6 状态改为“部分完成”，`.hypothesis` 已排除，身份可复现性另立 G6b（给 backend/worker 加与 RS 同类的 source identity label，
  或让构建上下文只取已跟踪文件）。审核方已在本报告之后的提交里直接改了这几处文字，实施方本轮不要再改。
- 关闭标准：下一轮 carried 判定在 V′ 的门禁 worktree 里按恢复后的规则执行并记录；G6b 由 owner 决定是否实施。

### G2-F3：V 的 backend/worker 镜像含有 git 中不存在的空目录，G6 对“其他缓存目录”的检查不完整

- 类型：已证实缺陷；是否阻塞：否
- 位置：V 的镜像 `/app/backend/src/gateway_backend/cache`（空目录）；handoff §3 “未发现第二个需要新增的缓存规则”。
- 依据：主工作区 `vnext/backend/src/gateway_backend/cache/` 是被 git 忽略、只含 `__pycache__` 的残留目录（`git ls-files` 无内容）；`.dockerignore` 排除 `__pycache__` 后，`COPY backend/src` 仍把这个空目录带进镜像。
  V 的 backend 与 worker 镜像里存在该目录，`/tmp` 里新建 worktree 重建的镜像里没有。实现方为通过 `test_capability_packages_match_owner_set` 删除了 `business_projection`、`comparison_projection` 两个同类残留（`g2-v-attempt1-cache-cleanup.log`），`cache/` 不在该测试范围内，被留下了。
- 影响：生产镜像含有与源码树不一致的空目录；这是 R3-F1 同一类问题（构建上下文含 worktree 本地状态）的第二个实例，`.dockerignore` 无法表达“只取已跟踪文件”。空目录无功能影响。
- 最小修正方向：随 G6b 一并解决；本轮不要求。
- 关闭标准：G6b 实施时验证两个来源不同的 worktree 构建出相同的镜像内容。

### G2-F4：G7 的两处证据与测试缺口

- 类型：非阻塞建议；是否阻塞：否
- 位置：handoff §4；`g2-g7-client-v.log`；`vnext/repository_service/tests/test_compose_lifecycle_harness.py`。
- 依据：
  1. handoff 写“候选 `815ef56a…` 的最终层数 20”，对应日志 `g2-g7-client-v.log` 只记录了 exit code，没有层数；V 与 H 的层数（20、base 12）有记录，当前镜像状态也印证（`gateway-repository-client-e2e:local` 20 层，base 12 层，经过 815ef、V、H 三次候选仍不增长）。
  2. “lock 变化时通过新的 `Dockerfile.dependency-base` 构建基础镜像”这条路径没有单元测试，门禁中也只走了 `docker tag` 种子路径。我用临时 tag 实际运行了该路径
     （`GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE=g2-review-client-base:probe`、`ensure_client_image(image='g2-review-client-final:probe')`）：基础镜像 9 层，最终镜像 17 层，约 60 秒完成，最终镜像在离线模式下由基础镜像构建成功。路径可用，但没有回归保护。
- 最小修正方向：补一条 lock 不匹配时调用 `_run_client_dependency_base_build` 的命令构造测试；层数记录在下一份 handoff 中补全。

### G2-F5：census 缺少让 G8 能直接决议的两项统计

- 类型：非阻塞建议；是否阻塞：否
- 位置：`vnext/backend/benchmarks/real_dump_census.py` 的 `duplicate_details_by_table`。
- 依据：census 显示 40,748 条额外重复行全部是“同键但取值不同”（完全相同行为 0），136 个重复表的键都来自 `EXPLICIT_RULE`。G8 要决定“规则键是否有误 / 表角色是否应改 / 数据是否清理”，
  最直接的信息是同键行之间哪些列不同，以及同键行最多有几行；这两项只需要列名与计数，不含行值，G2 之后还要因 G2-F1 重跑 census，增加它们的边际成本很小。
- 建议：每个重复表增加 `differing_columns`（同键行之间取值不同的列名，排序）与 `max_group_size`；JSON 保持不含行内容。是否纳入由 owner 裁量，不影响 G2-F1 的关闭。

### G2-F6：实现方留下的临时资源

- 类型：非阻塞；是否阻塞：否
- 依据：`git worktree list` 中有 6 个注册在 `/tmp` 的临时 worktree（`gdds-g2-h-check`、`gdds-g6-final-a`、`gdds-g6-final-b`、`gdds-g6-identity-old`、`gdds-g6-verify-a`、`gdds-g6-verify-b`），
  Docker 镜像从 G10 登记时的 892 个增至 985 个（卷仍为 76 个）。均无功能影响。
- 处置：实施方在本轮结束时用 `git worktree remove --force` 清理自己的临时 worktree（不碰 `/home/dev/gdds-p5-closure-s1`）；Docker 残留并入 G10，不在门禁期间清理。

## 3. 验收核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| G2.1 精确放行 `@saved_cs_client`（大小写不敏感），`@@saved_cs_client`、其他用户变量仍拒绝 | 部分满足 | `@saved_cs_client` 放行、`@@saved_cs_client` 与 `@other_client` 拒绝成立；但同时拒绝了原本接受的 `@OLD_*` 等，见 G2-F1 |
| G2.2 Digital 小写 `value`；缺失、大写 `Value`、多余属性行为；真实 t2 与 legacy 一致 | 满足 | legacy `composite_signal/parser.py` 的 Digital 属性为 `{"value"}`；四种形态参数表通过；census 中 t2 两份 composite COMPLETE；两个 XML fixture 只改了输入拼写，`git diff p5-s1-exit..H -- vnext/fixtures` 仅这两行；expected、digest、checkpoint、HTTP DTO 没有改动 |
| G2.3 实测深度、128 的依据、128 层通过与 129 层 fail-closed、无 RecursionError | 满足 | 深度 1,1,56,56,66,66,97,97，余量 31 层、低于 512；测试在恰好 128 层走完 XML→AST→`ast_to_json`→JCS，129 层得到 `max_xml_depth` 的 `RESOURCE_LIMIT_EXCEEDED`；我另测了递归余量：128 层链路在递归上限 300 时仍通过、250 时 `RecursionError`，默认 1000 有约 3 倍余量，512 则不安全，不应在不改实现的情况下上调到 512 |
| G2.4 生产与诊断 census、t3-c-v1 完整失败码、G4 理由、G8 统计 | 部分满足 | JSON 内部一致（各表细分求和等于数据集总数，总计 40,748 = 0 + 40,748，136 个重复表，键来源均为 `EXPLICIT_RULE`），`contains_row_data=false`，没有主机路径；`rd-t3-c-v1` 的失败是 G2-F1 的结果；G4 的“无法扩展”理由随 G2-F1 修复后不再适用 |
| G6 `.dockerignore`、容器内无 `.hypothesis`、clean worktree 同 project 重建 ID 一致 | 部分满足 | V 的 backend/worker 镜像 `find /app -name .hypothesis` 为空；跨 worktree ID 一致未达成，见 G2-F2、G2-F3；RS 身份旧/新值与 handoff 一致（revision 随 `.dockerignore` 改变，source digest 在 G6 提交不变、在 G7 提交变化） |
| G7 独立 base tag、`docker tag` 种子、lock 不变不重建、两个候选 SHA 层数相同、门禁期间无清理 | 满足 | `BASE_IMAGE` 与输出 tag 不同并有运行时断言；当前 final 20 层、base 12 层，三个候选后不增长；`g2-v2-*`、`g2-h2-*` 日志中没有镜像或卷清理记录，client 镜像与 base 现状完好；新建基础镜像路径经审核者实测可用（G2-F4） |
| 停止条件：golden/digest/checkpoint/HTTP DTO 不变 | 满足 | 区间内 fixtures 只有两行输入拼写；V 的 runner 全绿 |
| 停止条件：`import_rules` 不增 | 满足 | `test_architecture.py` 通过；区间对 `architecture_baseline.py`、`import_rules.py` 无改动；3 / 0 / 14 |
| 停止条件：AST 结构或业务语义不变 | 满足 | `_ast.py` 仅改属性名常量与消息 |
| V 的完整 runner 日志与三镜像 provenance | 满足 | `g2-v2-preflight.log`（clean、无 Dolt、无 Compose 容器、8000 空闲）、`g2-v2-runner.log`（起止 HEAD 均为 V，clean，runner exit 0；242 / 152 / 154 / 2717 / 1680+1 skipped / 205）、`g2-v2-compose-provenance.json` 三个镜像与 `g2-v2-images-inspect.log` 一致 |
| H 上 V→H carried | 实现方判定 false，审核复核应为 true | 见 G2-F2；H 自己另有完整 runner exit 0，所以无论 carried 结论如何，H 的容器门禁都有证据 |

阶段退出门禁：V 的门禁成立，但 G2-F1 修复会使 V 失效（生产 SQL 解析与 backend/worker 镜像内容都变化），退出门禁须在 V′ 上重新满足。

## 4. 实际执行的检查

| 检查 | 命令 / 方法 | 结果 |
| --- | --- | --- |
| 五包静态检查 | 审核 worktree 中各包 `../scripts/uv-consume.sh -C . run ruff check . && … run mypy` | 全部通过（34 / 15 / 26 / 464 / 198 个源文件） |
| backend 重点测试 | `pytest tests/test_architecture.py tests/test_table_access_sql_parser.py tests/test_table_access_sql_rejects.py tests/test_composite_signal_ast.py tests/test_table_access_contracts.py tests/test_table_access_xml_limits.py tests/test_real_dump_census.py` | 169 passed |
| SET 白名单新旧对照 | 同一解析入口，对 15 条语句分别在 `p5-s1-exit` 白名单（加 `@saved_cs_client` 探针）与 H 上运行 | 8 条 `@OLD_*` 头语句与 2 条 `@@` 变量语句从 COMPLETE 变为 FAILED（G2-F1） |
| 递归余量 | 128 层合成文档走 `parse_xml_text` → `materialize_logic`，在不同 `sys.setrecursionlimit` 下运行 | 1000–300 通过，250 以下 `RecursionError` |
| census 深度函数 | `_xml_max_depth` 对 3、5、128 层合成文档 | 返回 3、5、128，与解析器的深度口径一致 |
| census JSON 一致性 | 脚本逐数据集核对细分求和、主机路径、字段 | 一致；无 `/home`、`/mnt`、`/tmp` 路径；`contains_row_data=false` |
| 门禁日志 | 阅读 V 与 H 的 preflight、runner、provenance、inspect、carried 日志 | 与 handoff 一致；H 首次失败 exit 1 是 worktree 缺 `repository_service/.venv` 与被忽略的 `legacy/`，与实现方说明相符 |
| 镜像层对比 | `docker image inspect` 比较 V 与 H 重建镜像的 `RootFS.Layers`；在两个镜像里比较 `/app/repository_client` 的权限位与 mtime | 前 6 层相同，第 7 层起不同；权限位 644/755 对 664/775 |
| 缓存键探针 1 | 审核 worktree + 临时 project 构建 backend/worker | 全部 CACHED，层与实现方 H 重建的镜像相同 |
| 缓存键探针 2 | 仅修改审核 worktree 中 `repository_client` 的权限位后构建 | `COPY repository_client` 起未命中并重做 `uv sync` |
| carried 复核 | 主工作区（V 的门禁 worktree）、HEAD = H、V 的 project 名重建 | backend `1487ab34…`、worker `7ff0e754…`，与 V provenance 相同 |
| RS 身份 | 审核 worktree 中 `build_context_digest.py identity` 与 V 的 RS 镜像 label 比较 | `build_input_revision`、`source_tree_sha256` 相同 |
| 镜像内容 | V 的 backend/worker 镜像 `find /app -name .hypothesis`；列空目录 | 无 `.hypothesis`；存在空目录 `gateway_backend/cache`（G2-F3） |
| G7 基础镜像构建路径 | 临时 tag 调 `ensure_client_image` | 成功，约 60 秒；base 9 层、final 17 层；临时 tag 已删除 |
| 清理核对 | 探针后检查 V 与 H 的 backend/worker 镜像、client 镜像与其 base | 全部仍在；`ordered-bisect-b-3655597-baseline-*` 两个 tag 因 carried 复核重新指向 V 的镜像 |

没有重跑全量 runner。

## 5. 验证限制与剩余前置

- 没有读取真实数据：census 的各项数字（七份 COMPLETE、40,748 条冲突行、深度）来自实现方的运行，我只核对了 JSON 的内部一致性、字段与隐私约束，没有独立复现。
  G2-F1 的回退证据来自提交内的 S1 census 记录、H 的 census 记录和合成的 mysqldump 语句，不依赖真实 dump 内容。
- `rd-t3-c-v1` 修复解析后，其 composite 阶段、重复键统计与深度（已记录为 66）仍是未知；它们应由实现方的 census 重跑给出，若出现新的差异，按 G2 补充要求（只修格式保真问题，语义差异交 owner）处理。
- G2-F1 修复后须满足：新的 V′ 上完整权威 runner exit 0（真实重建，不沿用 V）、census 重跑与 JSON/handoff 汇总数字更新、复审通过后打 `p5-g2-exit`。
- G8 的决议在 census 重跑之后进行；G3 的实施规格在 G2 之后、S2a 之前；这两项不受本次修订影响。
- 审核方在本报告之后另提交文档修订：AGENTS.md 与 testing-conventions 的 carried 第 3 条恢复为同一 worktree 比较并写明原因；治理修订计划 G6 状态改为“部分完成”并新增 G6b；G2 状态改为“审核定向修订”；G10 增加本轮的临时资源。
  这些不属于实施方的修订范围。
