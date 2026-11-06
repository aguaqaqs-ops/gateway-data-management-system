# Phase 6 S2a 收尾独立审核

状态：**修后候选 `3b037adf4caf33f65e124a34f56f12f42e529641` 的代码、06 定向检查及 04 五包权威 runner/容器证据审核通过；Rust 与第④层沿用各自原合格来源。`38ccf8234f` 的失败证据保留，不作来源。最终 H 的同节点同工作区闭包/镜像身份绑定尚待核对；绑定通过并获独立 GO 后可打 S2a exit 附注 tag，当前不提前声明阶段已退出。**

- 日期：2026-11-06。
- 角色：本节独立审核者 `s2a_closeout_review`；设计协调与实施者分别处理整合设计和实施证据，审核者不修改产品、测试或原证据。
- 原候选 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`；handoff `c3c95282bf`；原证据复核 `7c5cc2a49efb5ac101a136efb063cfe013ee6422`。
- 初盘主线 `a89acb12ee88e77d1a3255cb0d55706f9c21a5d7`；整合输入主线 `5c867985647592c9f5d2ae1aa4be2bacc84ddf0c`。后者相对前者仅修改四份设计/计划文档，`vnext/` 不变。
- 初盘在 detached worktree `/home/dev/gdds-p6-s2a-closeout-review-a89acb12` 阅读固定提交；04、05 仅只读检查原工作区与日志。未运行测试、未取节点占用、未访问 CT108、未更改原证据工作区、镜像或卷。
- 依据：AGENTS、testing-conventions、执行计划 S2a、DC70/DC72/DC76–DC83、原代码审核/针对性复审/两次证据复核。

## 1. 原候选与证据资格

分支共同起点为 `49d0846d8625a8a928735c4fa0ea5126cf7ab741`。初盘时 `p6-s2a` 停在 handoff 提交 `c3c95282bf`，尚未合入 main，尚无 `p6-s2a-exit` tag。

原代码审核的 F1–F5 已由 `797f499b923c96cacc6074d20d2a0a40e0eae094` 针对性复审关闭。随后 `3b3d9c97bc` 只删除已经失去调用方的旧组件 pytest 路径测试；相邻通用外部 pytest 路径用例保留。原失败 runner `30d67140d4` 不作为任何包的沿用来源。当前合格来源是 `3b3d9c97bc` 的六包 runner，整体 exit 0。

2026-11-06T03:43:26Z 现场只读核对：

| 项目 | 结果 |
| --- | --- |
| 04 来源 worktree | `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04`，HEAD 为完整原候选，clean；legacy 链接有效 |
| 05 差分 worktree | `/home/dev/gdds-p6-s2a-evidence2-05`，HEAD 为完整原候选，clean；legacy 链接有效 |
| 04 原 runner | hostname `gw-dms-test-04`；2026-11-01T02:45:07Z–03:06:41Z；起止 HEAD 均为候选；六包 passed；runner exit 0 |
| 05 原差分 | hostname `gw-dms-test-05`；02:10:48Z–02:28:50Z；起止候选、结束 clean；8 个唯一输入覆盖 10 个别名、33,895,148 个值，逐值/诊断差异均为 0；四种 Rust 配置确定性一致 |
| manifest | 从与原节点 SHA 一致的 runner 副本重新提取六份 JSON，与保留 manifest 全相等；按来源摘要结构重算六个 total_digest 全一致；六份 clean_worktree 均为 true、HEAD 均为原候选 |

现场重新计算的主证据 SHA256：

| 原节点文件（`/home/dev/gdds-p6-logs/s2a/`） | SHA256 |
| --- | --- |
| 04 `authoritative-runner-04-3b3d9c97bc.log` | `e39675de73554a9908d2c9b1b8c3485f8278cef80c04bd40a9452dffba986ce5` |
| 05 `layer4-formal-diff-3b3d9c97bc-05.log` | `da4be0d15e903016b1c74f0d093641f6b36de69d3f6d1a7f958e1259dad339bc` |
| 05 `run-layer4-3b3d9c97bc.py` | `a9be5e67226a33d8c4a30c3d20e6e339b7e2a816ea10c216621e3ab30528e2c8` |

保留的六份 JSON 位于 CT201 `/home/dev/gdds-p6-logs/s2a/evidence-check-2-review/<package>-manifest.json`；权威来源是上述原 runner 日志中 `==> test input manifest package=...` 后的 JSON。CT201 副本与原 runner 的 SHA 相等；不是以复制环境或克隆节点替代原来源工作区。

04 只读命令末尾查询不存在的 busy marker，`ls` 返回 2；此前源码身份与日志读取均完成。这是读取“不存在”所得的退出状态，不是测试或取证运行失败，未重试、未获取或删除占用。当前空闲状态不作为后续执行前提保证。

原证据复核 2 的预检勘误仍须在新 handoff 修正：旧 04 预检的四个 Rust 版本查询实际未选中工具链，不能称为通过。正式 runner 的 Rust manifest 记录正确工具链且 fmt/clippy/test 通过，因此不影响原来源资格，不要求为勘误重跑。

## 2. 主线后续变更与影响

`49d0846d86..5c86798564` 的 `vnext/` 变更只有 `979c39db74492d5f90fd9f3920ffcec3cf5d4596`：

- `backend/application/checkpoints.py` 的 READY 闭包引用上限从 4,096 增至 32,768。
- `test_operation_checkpoint_contracts.py` 增加固定旧 wire/digest 与完整 refs 边界覆盖，保留既有闭包语义。

没有新增锁文件、runner/wrapper、共享 fixture、Rust、部署或 parser 变化。前端工程不进入后端 `vnext/` 闭包。容量修正已由原容量审核覆盖；本节须核对它与 S2a 的组合，不冒称原容量门禁已经验证新 adapter。

| 对象 | 影响与最小处置 |
| --- | --- |
| backend | 产品包变化且完整 Docker context 变化；整合候选实际运行该权威包和其 Compose 旅程 |
| repository_service | 虽无 RS 算法变化，其闭包包含完整 `vnext/` Docker context；必须实际运行该权威包及对应容器门禁 |
| rust、shared_kernel、repository_contracts、repository_client | Git 输入预计不变；只具备尝试沿用的条件，仍须在 04 原来源 worktree 用来源环境实算 manifest/compare；任何实际变化只补跑对应包 |
| 第④层 parser 真值差分 | 主线容量修正不改变 Python/Rust parser、差分工具、既有输入或结果语义；保留原来源证据，不默认重跑真实数据 |

初盘 `git merge-tree` 发现唯一 content conflict 为 `p6-design.md`。ADR 0001、implementation-stages 与 Rust policy 自动合并不代表语义已核，固定候选仍需确认保留 DC78/DC83，避免恢复永久 Python oracle、生产引擎开关或旧基准 exit 前置。

## 3. 最小执行与最终沿用条件

固定整合候选并审核差异后，04 的最小权威包集合为 `backend,repository_service`；另四包由实际 compare 决定。不得将未知状态、缺失 manifest 或环境漂移记为“可沿用”，也不因尚未比较而默认六包重跑。

执行前仍须确认 04 本节点占用、残留进程/端口、离线缓存、工具链、依赖基础镜像和构建设置。backend/worker 保留本机离线 Compose build，不设置 PREBUILT；RS/client 使用本节点预置依赖。镜像身份按同节点闭包与跨节点 config digest/全部 DiffID 的各自规则记录。运行期间固定 clean HEAD，不写工作区或重新 tag 其他镜像。

对其余四包，compare 需使用原 04 来源 worktree、同一有效 Hypothesis 路径及其不存在的状态，保留原 runner 起始 manifest。沿用直接引用最初实际运行的 `3b3d9c97bc`，不以中间 carried 结果作新来源。

受影响包通过后，若最终退出 HEAD 只追加报告/普通文档，则仍须独立核对 V..H 容器边界差异、同节点同来源 worktree 的 backend manifest 与 RS build-input/source-tree 身份。只有满足条件才能绑定到最终 HEAD；否则按变化范围补验。权威 runner 已覆盖的同提交 Compose 旅程不另行重复。

## 4. W4 租约与后续阶段边界

原 W4 `v2-submit` 在 `prepare_import` 发生显式 `lease_lost`/`heartbeat_busy_deadline`，随后 `worker_stalled`；操作仍 RUNNING，`repository_operation_id` 为 null。原停止复核不能从该类别推断 SQLite BUSY，也没有证明根因或修复完成。失败耗时不是成功性能样本。

该问题是未完成的业务正确性路径，不能归为普通性能参数。与此同时，S2a 的生产路由继续使用 Python，改动不涉及 Submit/worker 租约路径，DC81 已明确解除整体基准退出依赖。因此它作为原基准线的未解产品问题保留，不据此要求 test-only S2a 重跑 W4 或等待全部基准 exit。

设计协调告知：RS 独立候选 `4497ded8ff` 尚无最终门禁/合 main 授权，当前没有租约产品修复合入；本节冻结不纳入该候选。若后续产品修复进入整合候选，须重新计算具体影响，不能套用本文两包边界。

DC83 已确认 S2b 功能 exit 与 W2 性能复核分开，30s 目标保留，CT108 可用时补完整路径测量、最迟 S6 收口。未知数值不得记通过，W4 租约业务失败也不因此变为可延期的纯性能项。S2b 触及相关消费者、冻结/恢复或租约路径时仍须明确其验证归属；本报告不批准 S2b 开工或产品修复。

## 5. 初盘待办（后续完成情况见 §6–7）

1. 整合 diff 保留 READY 容量修正和 S2a 产品/测试，不夹带未审产品变更。
2. handoff 修正预检勘误与 DC81 次序，原失败/成功证据保持可追溯。
3. 获授权角色同步 AGENTS/testing-conventions 的旧 crate 排除与已删除入口，执行计划路径清单与阶段状态按实际进度更新。
4. 固定候选的 04 运行计划、来源 manifest、包比较和镜像准备满足第 3 节后，再放行最小门禁。
5. 实际结果与最终 HEAD 绑定尚待独立证据复核。

初盘未发现新的产品阻塞 Finding；原审核中的非阻塞优化观察不升级为本节新增验收。本节列的是初盘状态，不覆盖后续候选与证据结论。

## 6. 固定整合候选审核

结论：**`38ccf8234fa559c47146ed93d054354201a4953a` 的整合产品差异、治理同步与 handoff 修订通过，无新增阻塞 Finding。实际门禁仍待第 7 节。**

审核在另建的 clean detached worktree `/home/dev/gdds-p6-s2a-closeout-review-38ccf823` 进行，legacy 链接有效。完整 parents 为 `5c867985647592c9f5d2ae1aa4be2bacc84ddf0c` 与 `c3c95282bfe90f2d2fd0f2110b7be9bfa134ab38`；没有改写既有候选/证据提交。

核对结果：

- 相对原候选 `3b3d9c97bc`，`vnext/` 恰好只有第 2 节的 READY 容量代码与测试两文件；两文件与 `979c39db74` 逐字一致。Rust workspace、scripts、fixtures 没有额外变化。容量修正完整保留，未夹带独立 RS 候选或租约修复。
- `p6-design.md` 冲突解决使用 S2a 实际能力：取消/截止传入 core，在解析检查点读取；core panic 与 adapter FFI error envelope 分开描述；共享有界池为 adapter 一次创建、固定 N；生产仍使用 Python，S2b 接入验证后删除被替代实现及临时差分入口。DC78 的无永久 oracle/回退和 DC81/DC83 时点保留。
- AGENTS/testing-conventions 删除旧 crate 排除与已删除组件入口；完整 workspace cargo test、backend 扩展强制重装及 `gateway_compute._native.__build_input__` 与现有脚本一致。implementation-stages 不再把已删除 Contract 列为现行 owner。ADR 0001 与 Rust policy 的自动合并仅移除该旧 Contract 链接，主线 DC78 规则保留。
- 预读提出的两处措辞已修正：执行计划分别标注 `capabilities/table_access/` 的 O2 与 `tests/support/table_access_sql.py` 的 test-only 入口；设计覆盖表注明三项 reader 生命周期用例仍仅 Python，由 S2b 生产替换时移交。没有据此新增测试或扩大范围。
- handoff 已更正旧预检 Rust 版本说法，保留原正式证据与失败记录；§13 明确两包必跑、四包实际比较、原节点/工作区、离线环境、runner 非零停止及第④层不重复运行。没有提前宣称当前整合候选通过。
- `git diff --check 5c86798564 HEAD` 通过。以上均为静态核对，没有运行测试。

主线后续 `ef2bb8b148` 仅在原基准的 `p6-submit-single-step-diagnostic-scope-review.md` 追加文档；不纳入本次产品候选，不触发重复产品审核或全量测试。最终合 main 后仍需绑定真实最终 HEAD 的同节点同工作区 carried。

## 7. 04 执行计划与实际证据

实际外置脚本为 `/home/dev/p6-s2a-closeout-04.sh`，不进入产品闭包。首轮只读审核确认其四包 compare、逐包 Hypothesis 路径、两包 runner 和非零停止方向正确；直接交实施者补齐以下具体执行条件：

1. checkout 原来源 worktree 前取得本节点占用，compare/run 共用该占用并验证 owner。
2. 使用来源 Rust manifest 已核对的环境：`LANG=C`、`LC_ALL=C.UTF-8`、`PATH=/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`，不设置 `CONDA_PREFIX`、`VIRTUAL_ENV`、`TZ`。这三个已知字符串分别与来源指纹 `6b23c0…`、`99fed2…`、`f00542…` 一致；不是通过修改 cache 消除差异。其余差异仍如实比较。
3. 任务独立 RS tag 在权威 runner 前通过既有脚本离线构建；确认所需 dependency-base/client 镜像可用，不以缺失新 tag 启动测试。
4. compare/run 记录 hostname、起止 HEAD/UTC/exit 和日志摘要；不覆盖已有失败日志。
5. 清理判断传播 `docker ps`/`ss` 自身失败，不能把状态读取失败当作无残留后释放标记。

这是对实际运行计划的窄修，不新增产品测试或通用治理机制。

**修后计划 GO（2026-11-06）：** 审核者只读复审修后实际文件，独立重算脚本 SHA256 为 `2935acf2ec7e312201d0509a2708635ee9be3e0093417017a6a4d9d1d02d09d0`，上述五项已闭合。允许实施者对固定候选 `38ccf8234f` 执行 acquire → LAN 传输/同来源 worktree checkout → 四包 compare → 必要包 runner → 清理/release。脚本按操作建立新日志目录，不删除来源 cache；source log SHA、原 HEAD/clean、逐包 Hypothesis 路径、原 Rust 环境、新 RS tag 离线构建/身份与读取状态失败停止均已核对。

实际执行须保留每个 mode 的 stdout/stderr（错误说明可能写 stderr），连同 operation log、镜像前提、源码/脚本传输摘要一并交接。存在实际包闭包变化时仅追加该包；缓存缺失、身份不符或 runner 非零依原停止规则处置。本 GO 只放行本次取证，尚未宣称 04 新结果或 S2a exit 通过。

计划放行时再核 main 前进：`9277e87896` 只追加基准 scope-review 文档；中间 `c83fb2aaaa` 仅更新 S2b kickoff 文档。`5c86798564..9277e87896` 的 `vnext/` 没有变化，不改变本次固定产品候选与最小验证范围。

运行期间主线继续到 `ce39190dfd`：`e60e5e89b2`、`55fa70a489`、`ce39190dfd` 相对 `9277e87896` 仅在 `p6-change-set-heartbeat-probe-plan.md` 与 `p6-submit-single-step-diagnostic-scope-review.md` 追加共 90 行，`vnext/` 不变。审核只核本次整合影响，保留原线文档，不重新审核原基准内容或重跑产品。

### 7.1 四包实际比较

审核只读核对 04 原路径 `/home/dev/gdds-p6-logs/s2a/closeout-38ccf8234fa5/compare-20261106T042621Z-1730364/` 中的 source/current manifest、compare JSON 和 operation log。节点 `gw-dms-test-04`，04:26:21Z–04:26:28Z，起止 HEAD 均为 `38ccf8234f`，operation exit 0；source runner SHA 与第 1 节一致。

| 包 | 结果 | 独立核对的变化 |
| --- | --- | --- |
| rust | 可沿用 | changed_components 为空；total_digest 仍为 `94e1a069bfe912f3521cbf5351da0b19a0de0d989aed13eb2835b315786a173f` |
| shared_kernel | 运行 | 仅 environment:runtime-and-docker-build |
| repository_contracts | 运行 | 同上 |
| repository_client | 运行 | 同上 |

三个 Python 包的 environment values 唯一差异均为 `dolt_version` 的附加提示：原值为 `dolt version 2.1.11` 加 `Warning: you are on an old version of Dolt. The newest version is 2.6.0.`；当前为同一版本号加 `Warning: unable to query latest released Dolt version`。这不证明 Dolt 二进制升级或产品回归，但现行闭包包含完整版本输出，比较结果必须视为变化，不能人工忽略、修改摘要器或清缓存制造 carried。

因此确认本次实际 runner 集合为五个 Python 包：`shared_kernel,repository_contracts,repository_client,backend,repository_service`，顺序由权威 runner 固定。Rust 直接沿用原合格来源 `3b3d9c97bc`，不重复运行；第④层保留原证据。此集合已直接告知实施者与设计协调，仍保持离线，不为版本提示开放公网。五包实际结果待复核。

### 7.2 实际证据核对表（修后候选）

| 证据 | 来源/绑定要求 | 当前结论 |
| --- | --- | --- |
| 本次五包 runner | 04 原 worktree，固定 `3b037adf4c`；起止 hostname/HEAD/UTC、整次 exit、五包结果及起始 manifest | exit 0，§7.6 通过 |
| shared_kernel | 本次 runner 实际运行；摘要见 §7.5 | 243 passed |
| repository_contracts | 同上 | 152 passed |
| repository_client | 同上 | 161 passed |
| backend | 同上；新 adapter build-input、READY 容量组合、Compose provenance | parallel 3,238、serial 52 passed |
| repository_service | 同上；任务 RS tag 本机身份及 build-input/source-tree | parallel 1,744 passed / 1 skipped；serial 207 passed |
| rust | 第 7.1 节比较相等；直接来源为原 `3b3d9c97bc` exit-0 runner | 候选可沿用；最终 H 待比较 |
| 离线/缓存/镜像 | 预置依赖身份、本次构建网络、无代理；传输记录归实施 handoff | 实际 manifest/准备日志通过，§7.5 |
| 清理与释放 | runner target/Hypothesis 清理、worktree clean、无本次进程/容器/端口遗留 | 清理通过；本会话 marker 保留至最终 H 绑定后释放 |
| 最终 H | 允许文档差异、逐包直接来源比较、RS source identity | 待合 main 后核对 |

两次原始日志分别保留在 04 的 `closeout-38ccf8234fa5/`（失败）与 `closeout-3b037ad/`（修后成功）目录；具体引用见 §7.3、§7.5–7.6。原 parser 第④层来源仍见第 1 节，不重新取证。

### 7.3 首次整合门禁停止复核

结论：**停止有效，本次不能作为任何包的沿用来源；不是产品业务断言失败，而是两项 unit 测试未隔离合法部署环境变量。须完成小修及新候选验证，不原样重试。**

审核者直接读取 04 原日志：`run-20261106T042819Z-1731032/authoritative-runner.log`，SHA256 `c3438c9a45669e6cfc8258ca712dd5093be2c61ce1028c684ea7c27e9841263b`。hostname `gw-dms-test-04`，04:28:25Z–04:49:16Z，起止 HEAD 均为 `38ccf8234f`，runner exit **1**。RS parallel 为 1,740 passed、1 skipped、2 failed；同一 runner 已排定的 RS serial 完成 207 passed 后退出。其余四个 Python 包状态 passed 不改变整次来源不合格的结论。

两个失败均位于 `tests/test_compose_build_harness.py`：`test_ensure_repository_service_image_rebuilds_when_labels_stale` 与 `test_ensure_repository_service_image_skips_rebuild_when_labels_match`。测试 mock 镜像检查/构建，但调用的 `ensure_repository_service_image()` 正常读取 `GATEWAY_REPOSITORY_SERVICE_IMAGE`，实际返回本次批准的 `gateway-repository-service:s2a-closeout-38ccf8234fa5`；测试仍无条件断言 `DEFAULT_IMAGE`。该 env 是既有合法部署输入，错误不在生产 helper。它是在测试实际运行后暴露的测试缺陷，不按 DC68 的未触及被测对象操作错误处理。

最小修订已直接与实施者达成一致：仅在这两个现有 unit 使用共享 default/custom 参数，default 明确删除 ambient env、custom 明确设置固定测试 tag；期望值来自默认常量或独立固定字符串，不调用被测 resolver 生成期望。保留原 mock，不新增真实 Docker 操作，不改生产 harness/闭包规则，不使用或改写原默认镜像 tag 绕过失败。

实施者可在独立 CT201 worktree 修改并提交，06 clean 已提交候选运行该模块 focused 与已安排静态检查；原 04 运行和清理不受本地编辑影响。新固定候选经独立审核后，最小权威集合仍为五个 Python 包：`38cc` 整次失败不能供其中任何包沿用；原 `3b` 的三个小 Python 包已有实际环境变化，backend/RS 又包含该测试文件的完整 Docker context 变化。Rust 保持直接来源 `3b` 的合格证据，按新候选比较相同后沿用，不重复第④层差分。未授权原样重复失败 runner。

现场只读时本会话 marker 仍保留；日志显示 runner 正常清理 Cargo target 与五个 Hypothesis 目录。最终无进程/容器/端口遗留与 marker 释放由实施者完成并另交日志，本节不提前宣称已释放。

### 7.4 测试隔离修正复审

**静态复审通过：** 候选 `3b037adf4caf33f65e124a34f56f12f42e529641`，parent 为 `38ccf8234fa559c47146ed93d054354201a4953a`。审核在 clean detached worktree `/home/dev/gdds-p6-s2a-closeout-review-3b037adf` 完成，legacy 链接有效。

相对 parent 仅修改 `repository_service/tests/test_compose_build_harness.py`：两项原 unit 共同使用 `_SERVICE_IMAGE_ENV_CASES`，分别明确删除 ambient `GATEWAY_REPOSITORY_SERVICE_IMAGE` 或设定固定 `gateway-repository-service:test-selected`。默认期望来自既有 `DEFAULT_IMAGE` 常量，配置期望为独立固定字符串；没有调用 resolver 自生成期望。重建路径保留一次调用及参数断言，不重建路径保留未调用断言，原 mock 保持，无外部 Docker 调用。生产 helper、产品、锁和 golden 全未变；`git diff --check` 通过。

06 定向证据已复核通过：节点 `gw-dms-06`，worktree `/home/dev/gdds-p6-s2a-testfix-3b037ad-06`，04:56:24Z–04:57:21Z，起止完整 HEAD 均为本候选，operation exit 0、结束及现场 clean。该模块 45 passed；五包 Ruff 与 mypy 均通过（backend 490 files、RS 200 files）。审核者在原节点重新核对 11 份 step 日志 SHA，与同目录清单全部相等。

证据根为 06 `/home/dev/gdds-p6-logs/s2a/closeout-3b037ad/06-validation-20261106T045624Z-23250/`；`operation.log` SHA256 `3bd29ab7bf286d040def026b757ff973c4b12794da362b06f54e0a3d213b9229`，focused 日志 SHA256 `395d4d516282ac052a9305f554defd98078a4e711a07020ef04e4332b09b11f4`。实施者报告使用专属 RS_IMAGE ambient；原 operation 只记录 command=env，具体命令/离线环境引用由 handoff 补充，不为记录细节重跑。

**04 新候选五包 GO：** 静态修正与 focused 通过，允许将已审 wrapper 定向替换候选、专属 RS tag 和日志目标，接续现有自有节点占用后执行既定五包门禁。原 `38cc` 失败日志保留；不得作为来源。新候选 04 实际结果与最终 H 绑定仍待复核。

### 7.5 修后门禁的起始身份预核

本次原日志目录为 04 `/home/dev/gdds-p6-logs/s2a/closeout-3b037ad/run-20261106T050200Z-2118255/`。runner 于 05:02:05Z 开始，固定 HEAD 为 `3b037adf4caf33f65e124a34f56f12f42e529641`，umask 0022。审核仅从正在写入日志取得只读快照，没有运行新 manifest 或修改被测 worktree。以下摘要已按来源结构独立重算，五份均匹配、clean_worktree=true、HEAD 为本候选；整体来源资格仍须等待 runner 最终 exit 0。

| package | 起始 total_digest |
| --- | --- |
| shared_kernel | `f9fe40f63740ced4a09c7fc5502a18fee4b061a249d2e58f2340430b233c8ec6` |
| repository_contracts | `2e453dc3c13a0b43764b4a4e7386604e7dbe4daeb706dd333efb670ba1aa6c07` |
| repository_client | `83de1194e8817e19992e65ce87fa0b6805be6f2946206d3e3560ca5f2c50e2f1` |
| backend | `5cfba3009e1b635aa591cae106f0490b0d2c185f134b6cb7a4f81c199a6676df` |
| repository_service | `706f50e7cbe0ee151aabebd8445d9f33e5aa58de6a4756d411bd890ef2ac0b41` |

backend 与 RS 的实际环境记录 `GATEWAY_DOCKER_BUILD_NETWORK=none`、PREBUILT=false、预置依赖开关 1、`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`。实际 RS tag 为 `gateway-repository-service:s2a-closeout-3b037ad`，本机 image ID `sha256:f51527e212b04db1b1a29d6c5e1fb1611ece0a6139bf123e9a524eb308893257`。其 build-input revision 与 candidate revision 均为完整 `3b037adf4c`，source-tree 为 `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`，锁 label 为当前 RS lock。三份 dependency-base 本机 ID 与原来源记录一致，未重新传输依赖层。扩展检查实际 expected/installed 均为 Rust tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`。

| 已完成的准备证据（本次目录） | SHA256 |
| --- | --- |
| repository-service-image-build.log | `b0f25906441e091acf10a7d729f4803932a616b9965df61c948af8550e2c8b30` |
| repository-service-image-identity.txt | `6ff4c19035f0f98c285707fa42c607527093613f67b056d719a4b7d384c401d5` |
| image-prerequisites.log | `f01042d7cea8d4682936a3fd92bccc1065dfc39b4a898b3ebb683efc7de5017b` |

当前 harness 将 backend Compose provenance 写到 `/home/dev/gdds-test-tmp/gateway-compose-gate-provenance.json`，不是旧文档所写的 worktree 内 `.last_compose_gate_provenance.json`。预核的最后一份 provenance SHA 为 `951b06c6468243aea45d3fa85663dbe294079ff3d34fc80c598ee05e4af2a0af`，其中 RS image ID/source identity 与上述实际镜像一致；已请实施者在运行结束后复制到本次外部证据目录，不重跑 Compose。最终 runner SHA、exit 和清理待末端核验。

### 7.6 修后实际证据结论

**通过。** 审核者在原 04 节点读取完成的 `run-20261106T050200Z-2118255/authoritative-runner.log`，重新计算 SHA256 为 `ba965907119c962fa5b23372cce4b6885b0b5269e85ac9d55f97f2f450bfea27`。运行时间 2026-11-06T05:02:05Z–05:22:57Z，起止完整 HEAD 均为 `3b037adf4caf33f65e124a34f56f12f42e529641`，hostname `gw-dms-test-04`，五包各自 passed、整次 runner exit 0。实际计数见 §7.2；RS 两项环境污染测试经修订后已随完整包通过。不存在测试超时或性能异常结论。

从完成日志重新提取的五份起始 manifest 与 §7.5 预核版本逐项完全一致，摘要重算仍匹配。CT201 审核副本位于 `/home/dev/gdds-p6-logs/s2a/closeout-review-3b037ad/authoritative-runner-final.log`，SHA 与原节点相等；本次 `operation.log` SHA 为 `bb74ff2788453fcb932aa752ab472aef1e1113c8fe6e5f97112ed69cbdb2ccca`。

运行结束后的 backend Compose provenance 已保存为该 run 目录下的 `backend-compose-gate-provenance.json`。审核者在 04 对副本重新计算 SHA256，仍为 `951b06c6468243aea45d3fa85663dbe294079ff3d34fc80c598ee05e4af2a0af`，与原 TMPDIR 文件及 §7.5 预核相等；无需追加 Compose 运行。

运行后现场原 worktree HEAD 为本候选且 clean。05:27:54Z 独立只读残留检查确认：Dolt `pgrep` 返回 1 且无输出，`docker ps` 和端口 8000 查询均 exit 0 且无输出；五个 Hypothesis 路径和 Cargo target 均不存在。本会话原 marker 仍保留，用于最终 H 的同节点绑定；没有删除其他会话的标记或更改冻结镜像/卷。

代码、定向复审、当前五包实际结果与容器门禁已充分，可以合入 handoff/本文及已核主线文档以固定最终 H。当前五个 Python 包的直接来源为此次 `3b037adf4c`，Rust 仍直接来源为合格 `3b3d9c97bc` 原 runner；不能引用失败 `38cc` 或将中间 carried 结果当新来源。第④层 parser 与其输入/Contract 未改变，原 05 真值差分继续适用。阶段退出仍以 §8 最终绑定和独立 GO 为条件。

## 8. 最终 HEAD 绑定计划（尚未执行）

本节是为成功运行后准备的最小计划。候选运行期间不检出、不写被测 worktree，不改变镜像或其 tag。

1. 确认修后候选 runner 整体 exit 0、所有选中包通过、清理完成。`38cc` 失败运行不能作为该来源；实际来源 V 及日志待新结果确认。先保存成功日志和五份起始 manifest，再取得或继续持有本会话 04 占用。设计协调合入纯文档/报告后给出完整最终 H，审核 `V..H` 的实际差异及容器边界；只有满足既有沿用规则才继续。
2. 在同一 04 `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04` 检出 H，确认 clean 与 legacy。不运行 uv sync、不重装扩展、不构建或重新 tag 镜像，不删 `.pytest_cache` 或 Hypothesis cache 制造相等。各包 Hypothesis 目录应由已成功的 runner 正常清理；若仍存在，保留状态并处理，不擅自抹除。
3. 从实际成功 runner 提取五个 Python 包 source JSON；Rust source 仍直接取 `3b3d9c97bc` 原六包成功日志，不把第 7.1 节的 carried 结果当作新 source。按实际来源环境逐包计算 H 的 manifest 并 compare，记录总摘要及变化项。五个 Python 包 source 绑定本次实际运行，Rust source 绑定原实际运行。

最终直接调用 manifest 所需的关键设置：

| 设置 | 值/规则 |
| --- | --- |
| `TMPDIR` | `/home/dev/gdds-test-tmp` |
| `UV_OFFLINE` / `CARGO_NET_OFFLINE` | `1` / `true` |
| `PATH` | `/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` |
| `LANG` / `LC_ALL` | `C` / `C.UTF-8` |
| `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES` | `1` |
| `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE` | `gateway-backend-deps:lock-d054366c02fa` |
| `GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES` | `1` |
| `GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE` | `gateway-p2r1-repository:lock-6dc9659f0aee` |
| `GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE` | `gateway-repository-client-e2e-base:local` |
| `GATEWAY_REPOSITORY_SERVICE_IMAGE` | `gateway-repository-service:s2a-closeout-3b037ad`，实际成功 runner 的精确 tag |
| `GATEWAY_DOCKER_BUILD_NETWORK` | `none`，匹配本次 runner 的真实设置 |
| `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT` | **`1`**；`run-tests.sh` 第 209 行内部导出，外部直接调用 manifest 时必须恢复该真实输入；这不授权跳过额外实际验证 |
| `HYPOTHESIS_STORAGE_DIRECTORY` | 每个 Python 包单独设 `/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<package>`；Rust 不设 |
| `CARGO_TARGET_DIR` | 如保留脚本设置则为 `/home/dev/gdds-test-tmp/gateway-runner-cargo-target`；此项不参与闭包，不创建或重建 target |
| 其余环境 | 保持已核 wrapper/source manifest 对应状态；PREBUILT、代理、`RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME/CARGO_BUILD_JOBS/PYO3_PYTHON`、`CONDA_PREFIX/VIRTUAL_ENV/TZ` 均不设；不把 `GATEWAY_RUST_BUILD_INPUT` 导出到 manifest（runner 只向扩展同步子进程传它） |

实际新 runner manifest 是最后依据；若与上表计划有额外实际输入，记录其来源并复原真实配置，不修改 source JSON。所有镜像 tag 与本机 ID 保留本次验证值，尤其任务独立 RS tag 不得因最终文档提交变化而重新构建。

逐包命令使用现有入口：`python3 -I vnext/scripts/test_input_closure.py manifest --package <package>`，输出至 worktree 外；再以 `compare --source <实际来源.json> --current <H.json>` 比较。所有相等才写 carried；任何变化均如实处理对应包，不能因“只有文档”人工覆盖程序结果。

RS 另用 `python3 -I vnext/repository_service/tests/support/build_context_digest.py identity` 在 H 计算身份，与本次已验证 RS 镜像的 `gateway.p2r1.build-input-revision` 和 `gateway.p2r1.source-tree-sha256` 比较。`candidate_sha` 与 `org.opencontainers.image.revision` 可随 H 改变，不参与 source identity 等价判定，也不因此重 tag/rebuild。backend/worker 由同 worktree 的 backend manifest 比较绑定；同提交 runner 已覆盖的 Compose 旅程不重跑。

最终比较日志继续记录 hostname、起止 HEAD/UTC、exit 和 SHA，结果交独立审核。全部满足后才办理退出，本文当前没有提前声明该结果。

### 8.1 一次最终绑定与附注 tag

收口采用一次固定 H：实际 runner 证据审核通过后，将代码候选、handoff、本文及主线已核纯文档整合，阶段正文先写“证据通过，待最终绑定及 exit tag”。随后在原 04 worktree 对固定 H 执行本节比较与 RS 身份核对；独立审核明确 GO 后，附注 `p6-s2a-exit` 指向 H，注释记录完整 H、直接来源 V、04/worktree、最终比较日志路径/SHA、RS 身份和审核通过结论。

此安排符合 P6 §8.1 的附注阶段边界与 AGENTS 的最终 HEAD 绑定要求；H 包含已经通过的代码/实际运行证据审核，最后的身份绑定结果由可追溯的外置日志与附注 tag 记录，不为追加这份结果再制造一个未绑定的新候选。任一比较不相等则不得创建 exit tag。

如成功 tag 后需要将阶段正文改为“已退出”，可追加纯文档状态提交，明确阶段退出点仍为该 tag 指向的 H；该后续文档 HEAD 不冒称新被测提交，不移动 tag，也不为状态文字重复构建、测试或绑定。本文已确认 §7.6 实际 runner，最终 H 绑定结果仍待独立核对。
