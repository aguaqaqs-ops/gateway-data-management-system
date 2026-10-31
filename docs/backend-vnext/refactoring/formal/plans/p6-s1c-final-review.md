# Phase 6 S1c 终审

- 结论：**具备 exit 条件。** 代码、权威 runner、容器门禁、真实数据与两项对照都已满足执行计划 S1c 的验收，没有未关闭的阻塞 finding。办理 exit 前，owner 需完成第 4 节的三项处置；其中第 4.2 项涉及 DC70 的一处表述，与 S2a 的起点有关。
- 日期：2026-10-31。
- 对象：代码候选 V'=`ebd1b60a3f7ad962bf1348d166a7ff18969d06c0`；最终 HEAD H=`9f288ad50475030ddb496ad00b3b79f4abdc0082`（handoff 补记），分支 `p6-s1c-impl`。审核区间 `p6-s1b-exit..H`，共 41 个提交，其中 `5bc5a22605` 合并了 main `43c1d4d513`。`V'..H` 只改 `p6-s1c-handoff.md`。
- 依据：执行计划 S1c；DC64、DC65 及其修订与澄清；DC66 及其修订；DC67 及其补充与澄清；DC68；DC69；以及第 1 节的审核链。

## 1. 审核链与 finding 状态

| 报告 | 提交 | 结论 | 处理结果 |
| --- | --- | --- | --- |
| [首次审核](p6-s1c-independent-review.md) | `cc683b0601` | 定向修订 F1–F4 | F3 由 owner 裁定（DC65 澄清）；F1–F4 在复审 1 关闭 |
| [复审 1](p6-s1c-independent-rereview-1.md) | `7d85b38d9b` | 代码通过（V=`3008d578cf`） | — |
| [取证复核 1](p6-s1c-evidence-check-1.md) | `97a275359d` | 04 预检停止原因为身份口径，不是镜像差异 | DC67 澄清 |
| [取证复核 2](p6-s1c-evidence-check-2.md) | `cd4a7dee85` | 04 runner 与 05 t1 通过（V） | — |
| [取证复核 3](p6-s1c-evidence-check-3.md) | `876a60be7c` | ct108 停止于测量工具核对缺陷 | 工具修正（DC66 第 5 项） |
| [取证复核 4](p6-s1c-evidence-check-4.md) | `22f234c9cb` | v3 回退 Submit 失败，为产品缺陷 | 诊断后由 owner 决定 |
| [v3 诊断审核](p6-s1c-v3-diagnosis-review.md) | `27fef81378` | 根因为 `_patch_mutations` 排序 | DC69 采纳甲，并入 S1c |
| [DC69 修复复审](p6-s1c-dc69-rereview.md) | `0f5e4f02c9` | 通过（V'） | — |
| [取证复核 5](p6-s1c-evidence-check-5.md) | `71d14f637f`、`19228bda41` | DC69 证据实质通过；05 t1 第二次重做由 owner 追认 | handoff 补记 `9f288ad504`（第 3.1 节） |

F1–F4 全部关闭，DC69 缺陷已修复并验证。剩余的只有第 4 节的 owner 处置项，都不涉及产品缺陷。

## 2. 验收逐项核对（执行计划 S1c）

| 验收项 | 证据 | 结论 |
| --- | --- | --- |
| 权威测试 | 健康等待不消耗会话、超上界转人工、崩溃/lease 丢失/结果未知计数、drain、safe handoff 不增加 `attempt_count`、命令后免重启续行与再失败回人工、命令后重启不判用尽，已在首次审核与复审 1 逐项核对。DC69 的权威测试 `test_patch_mutation_closure_orders_mixed_row_changes_by_operation_phase` 在 DC69 复审核对 | 满足 |
| 五包静态检查 | V' 在 05 通过（日志 `31e08b48…`，DC69 复审核对） | 满足 |
| 权威 runner 与容器门禁 | 04 六包 runner 在 V' 上 exit 0，起止 HEAD 为 V'，环境符合 DC67 补充（复核 5）。backend Compose 旅程在该次 runner 内运行，backend/worker 为开发节点预构建的 V' 镜像（config digest `sha256:6d0aab7e…`、15 个 DiffID 四机一致）；RS 镜像 label 指向 V'。H 只改 handoff，按第 5 节第 2 步沿用 | 满足 |
| 2× t4 v1 Submit 无人工干预 | 三次独立运行（`78d8cf6727`、`47832ee94d`、`b96fe8e4cc`）的 v1、v2 Submit 都无人工干预完成；最终一次 v1/v2/v3 恢复会话均为 0，`await_import_result` 每次只领取一次 | 满足 |
| Submit 结果与 1030b 一致 | v1 commit 与 1030b 保留卷 631/631 表哈希相同，canonical state 均为 `sha256:1f53df33…`。审核者用保存的逐表哈希复算，并与 1030b 原始哈希文件比对 | 满足 |
| v3 回退 Submit 成功且与 v1 一致 | 三节点旅程 26/26 step checks PASS，v3 commit 与同次 v1 commit 631/631 表哈希相同 | 满足 |
| 真实数据（DC66 修订、DC69） | 05 t1 通过；ct108 2× t4 三节点完整旅程 exit 0，冷 History，五个 checkpoint，保留卷 | 满足；范围待 owner 确认（4.1） |

## 3. 终审补充核对

### 3.1 handoff 补记（`5eca3b728a..9f288ad504`）

- 补记新增了“DC69 取证补记”一节，六项尝试的时间、原因、修正与日志 SHA256 与复核 5 第 3 节一致；05 t1 的追认、04 runner 重跑的授权、postflight 所在主机与 ct108 cargo target 清理项都已写入。“无未解释偏差”的表述已改正。client e2e 日志 SHA256 已更正。
- **勘误（不阻塞）：** 补记中第 3 个 RootFS DiffID 仍写作 `…606d47ba4b53…`，并称与身份日志一致；原清单中的同一错误也没有改。正确值是
  `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`。
  审核者在开发节点、04、05、ct108 四台机器的镜像，以及 ct108 state 文件中都读到这个值（复核 5 第 4 节）。镜像身份以节点日志与本报告为准。handoff 已有提交不改写；后续阶段引用 V' 镜像身份时，以本报告为准。

### 3.2 区间与合入

- `p6-s1b-exit..V` 已在首次审核与复审 1 阅读，`V..V'` 在 DC69 复审阅读，`V'..H` 只改 handoff。分支自合并基点 `43c1d4d513` 起共改 26 个文件，没有改动 AGENTS.md、testing-conventions.md、执行计划或 owner 决议记录。
- `git merge-tree --write-tree main H` 无冲突。main 自 `43c1d4d513` 起改了 13 个非文档文件（主要是 backend 镜像依赖层任务），与 S1c 改动的文件没有交集。
- 合入后的 main 同时包含 S1c 与 `p6-backend-image-exit`，这个组合没有整体跑过权威 runner。两边改动的文件互不相交，backend 镜像任务也不改应用代码，风险低。合入后第一次在 main 系列上运行的权威 runner（S2a 的 04 runner）会覆盖这个组合；建议在 S2a kickoff 中写明，S2a 在 05 的首轮 focused 测试以合入后的 main 为起点。

### 3.3 沿用前提

- 闭包 manifest 中，`docs/` 下只有 `p2-r1-runtime-provider-feasibility.md` 一份文件（`repository_service` 的 test authority），`V'..H` 没有改动它。H 的六个包与 backend 镜像应判为可沿用。
- 04 门禁 worktree `/home/dev/gdds-p6-s1c-dc69-vprime-04` 位于 V'，clean，legacy 链接存在，可用于第 5 节第 2 步（DC51）。04 上还没有 H 对象，需要先用 bundle 传过去。
- 来源 runner：`/home/dev/gdds-p6-logs/s1c/04-runner-vprime-ebd1-retry.log`（`a77654a1…`），六包 manifest 都在日志中。

## 4. owner 处置项

### 4.1 DC33：真实数据范围确认

DC66 修订与 DC69 第 2 项写明的范围是：05 t1；ct108 一次 2× t4 三节点完整旅程（冷 History、五个 checkpoint、保留卷）；v1 对 1030b、v3 对 v1 两项只读对照。这些均已在 V' 与取证合并提交 `b96fe8e4cc` 上完成（复核 5）。请 owner 确认以此作为 S1c 的真实数据证据。

### 4.2 DC70 的起点表述（建议澄清）

- DC70 第 1 项写 `p6-s2a`“基于 `p6-s1c-exit`”。按 DC67 与 testing-conventions，`p6-s1c-exit` 是 `p6-backend-image-exit` 之前的产品提交，打在 S1c 分支的 H 上，不含 backend 镜像依赖层的改动。
- S2a 要改 `vnext/backend/Dockerfile`，并按 AGENTS 在节点离线构建 backend/worker 镜像，必须建立在新 Dockerfile 之上。如果从 tag 本身分支，S2a 会退回整镜像预构建流程，合入 main 时还会在 Dockerfile 上冲突。
- **建议澄清为：** `p6-s2a` 基于把 `p6-s1c-exit` 合入 main 的那个 merge commit，它同时包含 `p6-s1c-exit` 与 `p6-backend-image-exit`。基准仍测量 `p6-s1c-exit` 这个提交本身，DC70 的其余内容不变。

### 4.3 遗留：非 operator 会话的 startup 阻断（建议登记）

首次审核记录：会话已用尽、lease 过期的 RUNNING step，在非 operator 会话中 startup 时仍会转人工恢复，并阻断该次启动（`BLOCK_STARTUP_FATAL`）。这与 P4 R5 §8“人工恢复记录不阻断 readiness”的表述有出入。这是 S1c 之前的基线行为，S1c 没有改变它。

建议登记到 worker runtime 的后续维护（与 S1b 遗留 O1 同一归属），不阻塞 exit，也不并入基准或 S2a。需要时由 owner 另立短任务。

## 5. exit 办理步骤（owner 授权后）

1. 在 owner 决议记录中登记第 4 节的处置（DC33 确认、DC70 澄清、遗留登记），并把执行计划 S1c 的状态更新为已通过，写明 V'、H、审核链与证据绑定。
2. 将 H 用 bundle 传到 04。在 `/home/dev/gdds-p6-s1c-dc69-vprime-04` 中检出 H，按与来源 runner 相同的环境计算六包 manifest：
   - 环境为 `HOME=/root`、`LC_ALL=C.UTF-8`、`LANG=C`、PATH 以 `/home/dev/.cargo/bin` 开头、umask 022、`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`、`GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-vprime-ebd1`、RS/client dependency-base 与来源一致，`GATEWAY_DOCKER_BUILD_NETWORK` 与代理不设置；
   - `HYPOTHESIS_STORAGE_DIRECTORY` 使用相同的逐包路径，并确认这些目录不存在。
   与来源 runner 日志中的 manifest 逐项 compare，RS 镜像 label 在 H 上重算。全部判定可沿用后，在 H 上打附注 tag `p6-s1c-exit`。
3. 在 main 上用 `--no-ff` merge commit 合入 `p6-s1c-impl`，不改写已审核的提交。
4. 推送 main 与 tag，并用 git bundle 同步三节点（需 owner 授权）。
5. 合入之后，经 owner 授权清理：
   - S1c 的 worktree：开发节点的实施与审核 worktree，04、05、ct108 上的门禁、取证与诊断 worktree；
   - V、V' 及取证用的 backend/worker 镜像与归档、bundle、ct108 的 `/home/dev/gdds-test-tmp/s1c-dc69-ct108-cargo-target`；
   - 卷：`s1c-v-3008-rerun-fb534_*`、`s1c-v-3008-rerun-20e634_*`、`p6b2xwarmr5fix1030b_*`，以及 1030b 的 backend/worker 镜像。
   - **建议保留** `s1c-vprime-ebd1_*`（约 1.8 GB）到基准 exit：它是 `p6-s1c-exit` 产品在同一 2× t4 输入上的 v1/v2/v3 结果，基准正式测量可以把它作为正确性对照，不必另跑。
   - 1030b 对照哈希文件与本阶段日志按 handoff 清单处理。客户端 e2e 镜像不手工删除。

## 6. 本次执行记录

- 开发节点只读 git 与文档。节点上只做了只读检查：04 门禁 worktree 状态与来源 runner 日志、ct108 卷清单。没有运行测试，没有写入任何 worktree、卷或镜像。
- 镜像：本次只提交审核文档，不触发重建。H 的容器证据取自 V' 的 04 runner 与 RS label，在第 5 节第 2 步确认沿用。
- 没有推送、打 tag 或合入。

## 7. exit 办理记录（2026-10-31）

- owner 按本报告建议授权 exit，第 4 节处置记为 DC71。
- carried：H 经 bundle 传到 04，在 `/home/dev/gdds-p6-s1c-dc69-vprime-04` 检出 H，按来源 runner 的环境计算六包 manifest 并与 `04-runner-vprime-ebd1-retry.log`（`a77654a1…`）中的 manifest 逐项 compare：六包全部“可沿用”，changed 为空，total digest 相同。RS 构建身份在 H 上重算，build-input `4158ea39…`、source-tree `sha256:1d23f369…` 与 04 本机 RS 镜像（`sha256:adb2aa7e…`）的 label 一致。日志 `gw-dms-test-04:/home/dev/gdds-p6-logs/s1c/exit-carried-9f288ad504.log`，SHA256 `d6abb4ab9685606983bcbe2587e062396e16f64f60339d8a88ce60b5f679b9d9`；结束时 worktree 位于 H，clean。
- 附注 tag `p6-s1c-exit` → `9f288ad504`；`p6-s1c-impl` 以 `--no-ff` 合入 main，merge commit `49d0846d86`。
- 清理（合入后，owner 授权）：
  - 开发节点：删除 S1c 的五个 worktree 与分支 `p6-s1c-impl`、`p6-s1c-t1-prebuilt`（后者未合入，归档为 `refs/archive/p6-s1c/t1-prebuilt-469a154963`）；删除 V 镜像与归档、旧 bundle。
  - 取证合并提交只存在于节点，已归档到开发节点 `refs/archive/p6-s1c/evidence-{929bf18664,78d8cf6727,47832ee94d,b96fe8e4cc}`。
  - ct108：删除四个 S1c worktree 与五个 S1c 分支；删除卷 `s1c-v-3008_*`、`s1c-v-3008-rerun-fb534_*`、`s1c-v-3008-rerun-20e634_*`、`p6b2xwarmr5fix1030b_*` 及对应镜像；删除 S1c 的 cargo target、1030b 临时副本、归档、bundle，以及 fb534 运行的 checkpoint（state 与日志保留）。日志 `exit-cleanup-gw-dms-test.log`。
  - 04：删除门禁 worktree（exit 已合入，DC51）与 V worktree、V 镜像、归档、bundle。日志 `exit-cleanup-gw-dms-test-04.log`。
  - 05：删除五个 S1c worktree 与两个 S1c 分支、S1c 调试镜像与 cargo target、归档、bundle；V 镜像的层仍被基准会话的 `p6resume-*` 标签引用，只去掉了 S1c 标签。日志 `exit-cleanup-gw-dms-test-05.log`。
  - **保留到基准 exit：** ct108 卷 `s1c-vprime-ebd1_*` 与证据目录 `evidence/ct108-vprime-b96fe8e4cc`（含五个 checkpoint）；V' 镜像 `s1c-vprime-ebd1-{backend,worker}` 在开发节点与三节点均已加载，开发节点保留归档 `backend-worker-s1c-vprime-ebd1.tar`。V' 与 `p6-s1c-exit` 的 Docker context（`vnext/`）相同，基准可直接使用这组镜像。
  - 各节点 `/home/dev/gdds-p6-logs/s1c/` 的日志保留。基准会话的 worktree、分支、目录与镜像未触碰。
