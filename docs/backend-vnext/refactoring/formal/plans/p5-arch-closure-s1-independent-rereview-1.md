# P5 架构收口 S1 独立审核（第 1 次复审）

- 结论：**定向修订**
- 日期：2026-09-28
- 审核对象：p5-closure/s1 @ `1897d5df46f543b645058d7e3ac0f8909426725a`（实现 HEAD `2a54214df94321f97ee936062b5539836f6ea0f5`），base main @ `218c211240b33e01eee1eb8965fdcca0ec4b8099`；
  上次审核对象 @ `a35b2ad8dd`，报告 `plans/p5-arch-closure-s1-independent-review.md`
- 范围：只核对 `a35b2ad8dd..1897d5df46` 的修订差异（33 个文件，+660/−310）、原 finding 的关闭情况与改动传播
- 依据：执行计划 §2 S1、§3 S1/S2b、§6、§7、§8.1–§8.5、§8.8；设计 §9；纵切指南 §7；AGENTS.md；handoff 修订一节

## 1. 结论摘要

S1-F2 已关闭：审核者从 base 与 HEAD 分别生成的 OpenAPI 字节一致。S1-F1 的证据字节已经恢复，拒绝表也已补上，但解码仍比 base 宽。
S1-F3、S1-F5、S1-F7、S1-F9 的主体处理到位。

但修订引入了一个新的阻塞回归：为关闭非阻塞的 S1-F7、S1-F9，import 违例基线由 3 条增至 4 条，运行时环基线由空增至 3 组。
这与 §2 S1 的机械验收、§7“不得以新增基线条目绕过”以及 §8.1“只减不增”直接冲突。此外还有以下问题：

- S1-F4 实质未关闭：新的可达性规则按包整体标记 facade，效果与删掉的 shim 相同；
- S1-F6 的关闭标准未满足；
- 修订改动了 HTTP 与 worker 装配，属于 §6 的镜像边界，实现 HEAD 上却没有镜像与 compose 旅程证据。

阻塞项共 6 个（S1-F10、S1-F4、S1-F1、S1-F11、S1-F6、S1-F3），都能局部修正，所以结论是定向修订。复审通过之前，不合入 `main`，
也不进入 parser 修复与 S2a。

## 2. Findings

### S1-F10：修订使 import 基线回涨，违例 3→4，运行时环 0→3（新增）

- 类型：已证实缺陷；是否阻塞：是
- 位置：`vnext/backend/tests/architecture_baseline.py`（新增 1 条 `layer` 违例与 3 组 `RUNTIME_CYCLE_BASELINE`）；
  `application/workspace/contracts.py:21-24`（`from gateway_backend.settings import FIXED_UPLOAD_*`）；
  `application/payloads.py:112,175` ↔ `application/job_definitions.py:180`（互相在函数内导入）；
  `http/auth.py:202-245` ↔ `http/dependencies.py:42-45`（互相在函数内导入）；
  `infrastructure/control_db/sqlite_baseline.py:187` ↔ `database.py`（`__enter__` 内导入 `sqlite_baseline`）。
- 依据：
  - §2 S1 验收写明“违例基线只剩”3 条（http_arrow×2、`repository_import_artifact`），并要求“运行时环基线为空”；
  - §8.4 S1.5 要求结束时运行时环基线为空；
  - §7 规定不得以新增基线条目绕过；§8.1 规定 `import_rules` 输出只减不增；
  - 基线文件头恢复的治理规则同样要求新增条目必须经过评审。
- 事实：审核者在审核对象上运行 `import_rules`，输出为 **4 / 3 / 10**，与 handoff §4 一致。
  - 违例在 `c434064c7d`（S1-F7）由 3 条变为 4 条。
  - 3 组环都由 `2a54214df9`（S1-F9）引入。以 `auth`↔`dependencies` 为例：在 `a35b2ad8dd`，`dependencies` 只在 `TYPE_CHECKING` 下导入
    `auth`，不存在运行时环；现在两侧都在函数内导入对方，`import_rules` 把它计为运行时环。
  - 新条目的注释只写了“F7”“F9”，没有设计 §9 的分组与关闭阶段。
  - 设计 §9 的新增登记仍写“冻结 3 条 import 违例”，handoff §7 第 1 项仍写“3/0/10”，都与基线文件不一致。
- 影响：S1 的机械验收不再成立。更重要的是，S1-F7 与 S1-F9 本是非阻塞项，这次修订用新增基线条目换取了它们的关闭，
  S1.5 已消除的运行时环又回到了基线中。
- 最小修正方向（都有不新增条目的做法）：
  - F7：由组合根注入上传上限（设计 N-http-bypass 的原意）；或者常量定义在 application 侧，由 `settings` 引用；或者按原关闭标准在
    owner 测试中断言两处相等。`RULESET_VERSION` 的单一来源可以保留，它没有产生违例。
  - payloads/job_definitions：`build_payload_decoder_registry` 只保留在 `job_definitions`（它本来就单向导入 `payloads`）。
    严格的 `type(...) is JobDefinition` 检查所需的类型移到两者都能导入的叶子模块，或者由 `job_definitions` 持有校验入口。
  - auth/dependencies：`FailClosedInternalBearerPort` 放到一个叶子模块，两侧都从这个模块导入；`require_*` 回到 `dependencies`，
    由 `auth` 单向重导出（与 `a35b2ad8dd` 的方向相同）。
  - baseline head 读：由组合根给 `SQLiteBaselineHeadRead` 注入只读 UoW 工厂，或者把 UoW 的 BEGIN 与 busy 映射抽成
    `control_db_connect` 层的共享函数，`sqlite_baseline` 不再反向导入 `database`。
- 关闭标准：`import_rules` 输出为 **3 / 0 / 10**，`architecture_baseline.py` 中没有 F7/F9 条目；S1-F7、S1-F9 的去重与单一来源仍然成立；
  设计 §9 与 handoff 中的计数和基线文件一致。

### S1-F4（未关闭）：按包标记 facade 的可达性规则，效果等同于删除的 shim

- 类型：已证实缺陷；是否阻塞：是
- 位置：`tests/support/import_rules.py:436-495`（`_mark_package_facades`，以及对 `__init__` 中函数内导入的计边）。
- 已完成的部分：
  - shim `_ensure_composite_signal_production_anchor` 已删除；
  - DAG 测试改为放行上游 facade（`remainder == ""`），三处私有模块例外已删除；
  - `compose`、`row_encoding`、`project` 改为从 facade 导入。
  这些满足原关闭标准的第 1 项与第 3 项。
- 事实：
  - 新规则的做法是：只要包内任一子模块可达，就把该包的 `__init__` 标为可达，再计入 `__init__` 中所有函数内导入的边。
  - `composite_signal.materialize_composite_signal` 的唯一生产调用方是 `snapshot_materialization/compose.py`，而 `compose` 本身
    在不可达基线中（S3）。这 4 个 composite 模块之所以“可达”，只是因为 `composite_signal.contracts` 可达。
  - 审核者在 scratch 进程中关掉 `_mark_package_facades`，其余规则不变，重算结果为 **14**：多出
    `composite_signal._ast`、`_bind`、`_digest`、`materialize`，与上次去掉 shim 后的结果相同。
  - 对照上次建议的“把函数内导入计入该符号”：`table_rules.resolver` 经 `project.py` 导入 `resolve_table_rule` 这个符号，按符号计仍然可达；
    composite 这 4 个模块按符号计仍然不可达。可见按包整体标记这一步只影响这 4 个模块。
  - `IMPORT_RULE_SHAPES` 或其他规则形态测试中都没有新增可达性用例，handoff 也没有说明这条规则。
- 影响：§2 S1 的“不可达基线只剩 10 项”仍然是靠放宽工具得出的。S3 接入 composite 时，基线无法显示这 4 个模块何时真正变为可达。
- 最小修正方向：二选一。
  1. 可达性按符号计算：只有当可达模块导入 facade 中的 wrapper 符号时，才计入该 wrapper 的函数内导入。删除 `_mark_package_facades`，
     并补一条模块级参数表用例（wrapper 被导入时可达，未被导入时不可达）。
  2. 如实登记 4 个 composite 模块为不可达（S3 关闭），在 handoff 中说明与 §2 列表的偏差，交 owner 确认。
- 关闭标准：去掉“按包整体标记”之后，`import_rules` 的不可达集合与基线一致；新规则有形态用例。

### S1-F1（部分关闭）：FAILED 证据字节已恢复，但证据解码仍比 base 宽

- 类型：已证实缺陷；是否阻塞：是
- 位置：`application/submission/contracts.py:424-478`（`_EvidenceVersionedOperation` 等镜像模型）；
  `infrastructure/repository_write/wire_codec.py:101`（`import_operation_from_evidence_payload` 仍然没有调用方）。
- 已完成的部分：
  - 领域错误值保留了 `details` 与 `request_id`，`_serialize_terminal_repository_evidence` 显式列出字段；
  - golden `test_failed_terminal_evidence_bytes_match_base_golden` 与上次审核者从 base 得到的字节逐字一致；
  - `MALFORMED_TERMINAL_EVIDENCE_SHAPES` 覆盖了原关闭标准列出的 5 类拒绝情形；
  - 两个未用 helper 已删除，`repository_artifact_ref_to_wire` 已接入。
- 事实：application 层手写了一份 `VersionedOperation` 的镜像，但 result 字段全部是 `str`，`code`、`message` 也没有长度约束。
  审核者用 base 的 `VersionedOperation.model_validate`（`repository_contracts` 自 base 以来未改）与 HEAD 的
  `repository_import_operation_from_evidence_payload` 解码同一组输入，下列 7 类输入 base 拒绝、HEAD 接受：
  - `target_ref="feature"`（wire 为 `Literal["main"]`）；
  - `artifact_id` 不是 UUID；
  - `commit_id` 为空，或长 2000 字符（wire 为 1–1024）；
  - `completed_verification_policy`、`unknown_type_policy` 不在枚举中；
  - `error.message` 为空。
- 依据：原最小修正方向要求“解码恢复与 `VersionedOperation` 等价的校验”。终态证据决定提交结果，属于权威 durable 状态
  （AGENTS.md 比例化保障：保持强 Contract）。
- 影响：损坏或不一致的证据可以通过解码，并以错误的 result 进入后续流程。此外，这份镜像要手工与 wire 模型保持同步，
  wire 侧收紧或扩展时会静默分叉。
- 最小修正方向：解码委托给 infrastructure codec。现成的 `wire_codec.import_operation_from_evidence_payload` 就是
  `VersionedOperation.model_validate` 加映射，可以经 port 或组合根注入 submit job，然后删除 application 中的镜像模型。
  如果保留镜像，字段类型须逐一与 wire 等价，并给出等价性测试。
- 关闭标准：上面 7 类输入加入 `MALFORMED_TERMINAL_EVIDENCE_SHAPES` 并被拒绝；application 中没有与 wire 模型重复且更宽的 schema；
  `wire_codec` 中没有无调用方的 helper。

### S1-F11：修订触碰 §6 镜像边界，实现 HEAD 没有镜像与 compose 证据（新增）

- 类型：已证实缺陷（验收证据缺失）；是否阻塞：是（S1 阶段验收）
- 位置：handoff §6 与修订一节的“§6 定向修订门禁”。
- 依据：
  - §6：S1 因 HTTP/worker 装配改动需要重建；
  - AGENTS.md：阶段退出与最终候选 HEAD 无论此前是否延期都必须重建，旧镜像结果不得表述为当前 HEAD 已验证；
  - 上次报告 §5：修订若改动组合或受理路径，须在新的实现 HEAD 上重建并运行 compose 旅程，记录旅程实际使用的镜像 ID。
- 事实：
  - 本次修订改动了 HTTP 装配（`http/auth.py` 与 `http/dependencies.py` 的默认 internal bearer 工厂、`require_*` 的归属）、
    worker 组合（`build_job_worker_composition` 的 decoder registry 构造）以及 control DB 读路径。
  - 本机 `gateway-repository-service:local`（`sha256:bffceac8…`）的 label 为 `org.opencontainers.image.revision=c434064c7d`；
    `deploy-backend`/`deploy-worker`（`5dfb7cbd…`/`49df9edd…`）构建于 2026-09-28 00:27 JST。两者都早于实现 HEAD `2a54214df9`
    （10:05 JST），而 `c434064c7d..2a54214df9` 改动了 13 个文件。
  - 实现 HEAD 上只有 ruff/mypy、`import_rules` 与 focused 148 项。handoff 自己也写明 `c434064c7d` 的全量运行曾有 backend 3 项 compose
    失败和 RS 1 项失败，“需当前 HEAD 镜像后重跑”，但之后没有重跑的记录。
  - handoff §6.2–§6.4 仍然标注“@ `implementation_head`”，数字与镜像却是修订前的（2674/205，`6610f2c6b7f0`/`9e1672eca5e4`）。
    修订一节引用的 `/home/dev/gdds-p5-closure-s1-gate-logs/backend-unit.log` 与 `run-tests-r2.log` 在该目录中不存在。
- 最小修正方向：S1-F10 等修订完成后，在最终实现 HEAD 上：
  1. 在干净 worktree 中运行 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；
  2. 重建 RS 镜像并运行 backend 与 RS 的 compose 旅程；
  3. 按 testing-conventions 模板记录 image revision、source tree，以及 compose 实际使用的镜像 ID（provenance）；
  4. 日志放在不会被覆盖的路径。
- 关闭标准：handoff 的门禁结果与镜像记录绑定最终实现 HEAD，引用的日志都存在；runner exit 0。

### S1-F6（未关闭）：handoff 仍没有 8 份数据集的结构记录，`pair_of` 仍无 owner 确认

- 类型：已证实缺陷；是否阻塞：是（S1 阶段验收与 S2a 开工的前置）
- 已完成的部分：
  - 脚本增加了 `--diagnostic`，只在普查进程内放行 `@saved_cs_client`，不改 table_access 源码；
  - 生产路径的诊断码与消息写入 `parser_production_path`；
  - `has_logics_xml` 如实取值，`datasets.json` 不再含主机路径；
  - 诊断模式改用 `READERS_REQUIRED`，可以计数行数；
  - DC12 记为未触发，DC15 记为已触发，并标明 FLOAT 往返优先验证；
  - parser 修复已在执行计划 §1 与 §8.5 登记。
- 事实（对照原关闭标准“handoff 中有 8 份数据集的完整结构记录”）：
  - handoff §1 没有逐个数据集的记录（dataset ID、SHA-256、规模、表数、总行数、非 SKIP 表的列类型分布、无键表、可空键列、
    `saved_time` 类型、XML 结果），只让读者去看主机上的 `summary.json`。该文件不在仓库中，审核者也没有得到读取授权。
  - §1 写“t3/t4 … 诊断摘要见下”，下文没有这份摘要。
  - 脚本仍然没有重复键检测，无键表也没有按规则解析有效键后核对（原修正方向第 2 项）。
  - `pair_of` 默认仍是“同档 v1→v2”，允许通过 `dataset_pairing.json` 覆盖，但 handoff 没有 owner 确认的记录（§8.3 要求）。
- 最小修正方向：把 8 份数据集的结构统计写进 handoff（按决议记录 §4 只写结构统计，不写行数据）；补上重复键与有效键的统计，
  或者写明未统计的项及其承接节点；记录 owner 对 `pair_of` 的确认。
- 关闭标准：同原 S1-F6。

### S1-F3（残留）：§3 S2b 路径预算未登记延期项，handoff 未逐项写明现状与理由

- 类型：已证实缺陷（记录）；是否阻塞：是（owner 设定的关闭条件未全部满足，修正只涉及文档）
- 对照 owner 的 4 项条件：
  - 第 1 项（删除 `pinned_checkpoint_builder`）满足；
  - 第 4 项（更正“已闭合”“无 §3 定向偏差”的表述）满足，handoff 中已没有这两处表述；
  - 第 3 项部分满足：§2 S2b 新增第 8–10 项，§8.5 新增 S2b.0，但 **§3 S2b 的路径预算没有改**。延期项涉及的
    `http/orchestration/preview_acceptance.py`、`application/workspace/{preview,ports}.py`、`application/archive/ports.py`、
    `application/control_transactions.py`、`application/job_steps.py` 等不在 S2b 的必改或条件路径中。handoff §3 却写“执行计划 §3/§8.5”已登记；
  - 第 2 项不满足：handoff 修订一节只有一行“已登记”，没有逐项写明现状、延期理由与 S2b 目标。
- 影响：S2b 的审核会把这些改动判为超出预算。
- 最小修正方向：在 §3 S2b 补上上述路径（必改或条件）；在 handoff 修订一节逐项写明三项的现状、理由与目标。
- 关闭标准：满足 owner 的 4 项条件。

### S1-F8（未关闭，并出现新的记录错误）

- 类型：已证实缺陷（记录）；是否阻塞：否（随本轮修订更正）
- 原问题仍在：
  - “只改导入路径的测试”清单（含 `canonical_import_request_bytes` 的 4 个测试桩）没有写入；
  - §3 预算表仍然没有逐项覆盖必改路径；
  - §6.3 仍然记录 `deploy-*:latest`，而不是 compose 实际使用的镜像，也没有 provenance；
  - §6.4 仍然引用已被覆盖的 `/tmp/s1-backend-compose.log`（现在内容为“6 failed, 3 passed”）。
- 新问题：
  - `candidate_head` 与 §8.7 复审提示词写的是 `926fac4869`。该提交已被 amend 掉，不是分支上的祖先提交。
  - 审核对象之后，分支上又多了一个提交 `3f0c4dffb5`（只改 handoff），把 `candidate_head` 改成 `0b56172024`，同样不是祖先提交。
    worktree 中还有一处未提交的 handoff 改动，把它改回 `1897d5df46`，这处改动不是审核者做的，审核者也没有触碰。
    上次报告已经说明，文件不能记录包含自己的提交；应当只记录实现 HEAD，分支末端由审核提示词给出。
  - handoff §4、§7 与设计 §9 的计数不一致（见 S1-F10）。
  - 修订一节的门禁引用了不存在的日志（见 S1-F11）。
- 关闭标准：handoff 与仓库、镜像事实一致；traceability 中不出现非祖先 SHA；分支末端只比实现 HEAD 多 handoff 提交。

## 3. 验收核对

| 验收项（执行计划 §2 S1 / §8.4） | 结果 | 证据 |
| --- | --- | --- |
| 违例基线只剩 http_arrow×2 与 `repository_import_artifact` | 不满足 | `import_rules` 输出 4 条，多出 `workspace.contracts → settings`（S1-F10） |
| 运行时环基线为空 | 不满足 | 3 组（S1-F10） |
| 不可达基线只剩列出的 10 项 | 形式满足，实质不满足 | 关掉按包标记后为 14（S1-F4） |
| 改名条目理由、Phase 6 与 `external_target_sync` 延期登记 | 满足 | 设计 §9 新增登记；owner 决议 §9；基线条目注释。新增的 F7/F9 条目没有关闭阶段，归入 S1-F10 |
| DC26 精确放行 | 满足（未受影响） | 修订没有改动这条放行规则 |
| 行为不变：HTTP DTO | 满足 | base 与 HEAD 的 OpenAPI JSON 的 SHA-256 均为 `d11f6931…`，字节一致（S1-F2 关闭） |
| 行为不变：checkpoint 载荷、证据字节 | 满足 | FAILED golden 与 base 字节一致；step id 字符串不变（三个 suffix 表逐项核对） |
| 行为不变：证据解码 | 不满足 | 7 类输入比 base 宽（S1-F1） |
| 受影响测试只改导入路径、不改断言 | 满足 | 修订只新增测试（backend 用例 2674 → 2681，多出 1 + 1 + 5 项），另有 1 处测试桩签名格式化 |
| backend 全绿；五包 ruff/mypy | 部分核对 | backend ruff/mypy 通过；non-serial 2629 passed。serial/compose 与另外四包没有在本次复审中运行（修订没有改动另外四包） |
| 阶段末在 current HEAD 重建镜像并运行 compose 旅程 | 不满足 | 镜像为 `c434064c7d` 时期构建（S1-F11） |
| 分支末端只比实现 HEAD 多 handoff | 审核对象满足；当前分支末端存在记录问题 | `git diff 2a54214df9 1897d5df46` 只改 handoff；`3f0c4dffb5` 与 worktree 未提交改动见 S1-F8 |
| S1-F3 延期登记（owner 条件） | 部分满足 | §3 S2b 未登记（S1-F3 残留） |
| kickoff 普查记录 | 不满足 | S1-F6 |
| parser 修复前置登记 | 满足 | 执行计划 §1 与 §8.5 |

## 4. 实际执行的检查

在 scratch 目录另建 detached worktree 运行，没有在 `/home/dev/gdds-p5-closure-s1` 中写入任何文件；报告在全部检查结束后写入。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 修订差异 | `git diff a35b2ad8dd 1897d5df46`（逐文件） | 33 个文件，逐项对应 finding |
| backend 静态 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy` | 通过（459 个文件） |
| 导入边界 | `../scripts/uv-consume.sh -C . run python -m tests.support.import_rules` | 4 / 3 / 10 |
| 可达性反事实 | scratch 脚本复制 `unreachable_modules`，只去掉 `_mark_package_facades` 的两处调用后重算 | 14，多出 composite 4 个模块（S1-F4） |
| backend focused 与 non-serial | `../scripts/uv-consume.sh -C . run pytest -q -m "not serial" -p no:cacheprovider` | 2629 passed，52 deselected，110 s |
| OpenAPI 对比 | 分别以 base（`218c211240`）与审核对象的 `src` 经 `create_workspace_http_environment` 生成 `/openapi.json` | 字节一致 |
| 证据解码对比 | scratch 脚本分别用 `VersionedOperation.model_validate` 与 HEAD 的 `repository_import_operation_from_evidence_payload` 解码同一组输入 | 7 类输入 base 拒绝、HEAD 接受（S1-F1） |
| 基线来源 | `git show 218c211240:…/submit_jobs.py`；`git diff --stat 218c211240 1897d5df46 -- vnext/repository_contracts` | base 用 `VersionedOperation` 读写证据；repository_contracts 无改动 |
| 镜像记录 | `docker image inspect`；`tests/support/.last_compose_gate_provenance.json`；gate-logs 目录 | 均早于实现 HEAD；handoff 引用的日志缺失（S1-F11） |
| 分支拓扑 | `git reflog p5-closure/s1`；`git merge-base --is-ancestor` | `926fac4869`、`0b56172024` 都不是祖先提交（S1-F8） |

## 5. 验证限制与剩余前置

- 没有运行完整的 `run-tests.sh`、serial/compose 批次与另外四包的静态检查：本次修订只改 backend 与文档；实现 HEAD 上也没有可以核对的
  新镜像（S1-F11）。按 AGENTS.md，旧镜像结果不能作为当前 HEAD 的证据。
- 真实数据普查的产出（`summary.json`）没有读取：本次复审没有获得 owner 的读取授权。S1-F6 的判断只依据 handoff 与脚本源码。
- 审核对象是 `1897d5df46`。分支末端 `3f0c4dffb5` 只改 handoff 的 `candidate_head` 与提示词，不影响本报告的代码结论。本报告作为
  单独提交加在该末端之上，worktree 中他人未提交的 handoff 改动保持原样。
- 进入第 2 次复审的前置：
  - 关闭 S1-F10、S1-F4、S1-F1、S1-F6、S1-F3，并更正 S1-F8；
  - 在最终实现 HEAD 上完成全量运行、镜像重建与 compose 旅程，关闭 S1-F11。
- 复审通过后，按上次报告 §5 的顺序执行：S1 合入 `main`，然后是 parser 修复，然后是 S2a kickoff。

## 6. 复审记录（仅复审）

| 原 finding | 关闭情况 | 依据 |
| --- | --- | --- |
| S1-F1 | 部分关闭（阻塞） | 字节与 5 类拒绝已修复；result/message 解码仍比 base 宽，application 中有重复 schema，`wire_codec` 中有无调用方的 helper |
| S1-F2 | 已关闭 | OpenAPI 字节与 base 一致 |
| S1-F3 | 部分关闭（阻塞，只涉及文档） | 条件 1、4 满足；条件 3 缺 §3 S2b；条件 2 未逐项 |
| S1-F4 | 未关闭（阻塞） | shim 已删、DAG 已改；按包标记使反事实结果仍为 14 |
| S1-F5 | 已关闭（原条目） | 治理头、分组与关闭阶段、两处延期都可以查到；新增条目的问题归入 S1-F10 |
| S1-F6 | 未关闭（阻塞） | handoff 没有逐个数据集的记录；缺重复键、有效键统计与 `pair_of` 确认 |
| S1-F7 | 目标达成，但方式引入新违例 | 单一来源成立；`workspace.contracts → settings` 违例归入 S1-F10 |
| S1-F8 | 未关闭（非阻塞） | 原 4 项仍在，另有新的 SHA、计数与日志错误 |
| S1-F9 | 去重与严格检查达成，但方式引入 3 组环 | 5 个子项逐项核对属实；环归入 S1-F10 |
