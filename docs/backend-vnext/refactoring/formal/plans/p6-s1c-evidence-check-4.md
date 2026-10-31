# Phase 6 S1c 取证复核 4（ct108 三节点旅程 v3 Submit 失败）

状态：**产品缺陷，不是测量工具问题，也不在 S1c 的改动面内。** S1c 自身要验证的内容在本次运行中再次通过；失败发生在 v3 Submit，这一步属于三节点 History 场景，不在 DC66 修订约定的 S1c 取证范围内，是我上一份提示词的 checkpoint 清单把它带进了这次运行。根因尚未定位，先诊断，再由 owner 决定修复放在哪里（第 5 节）。

## 1. 对象

- 工具修正：`p6-baseline` 上 `95e1f02c`、`c33a505b`、`fb534592`，handoff `d87e2924`。05 focused 134 passed，五包 ruff/mypy 通过（日志 SHA256 `8d3d30f4…`）。
- 取证合并提交 `47832ee94d`：第一父 V=`3008d578cf`，第二父 `fb534592`。diff 只涉及 benchmarks、测试与 docs。
- 节点 ct108（`gw-dms-test`），project `s1c-v-3008-rerun-fb534`，2026-10-31 06:37:55–10:22:34 UTC，exit 1。
- 日志与状态（审核者在 ct108 上核对 SHA256）：
  - journey `/home/dev/gdds-p6-logs/s1c/ct108-2xt4-fb534/journey-attempt2.log`，`e497adcc…`；
  - state `/home/dev/gdds-p6-logs/s1c/evidence/ct108-2xt4-fb534-attempt2/state.json`，`652501a8…`；
  - compose `…/compose-attempt2/real-dump-t4-20261031T102226544180Z.compose.log`，`83d9c66d…`。
- 镜像：backend/worker config digest `sha256:b1f3c7b6…` 与 15 个 DiffID 同预构建镜像一致。
- 保留：本次卷 `s1c-v-3008-rerun-fb534_*`、五个 checkpoint（v1-submit、v2-preview、v2-submit、v3-preview、v3-submit）、上次卷 `s1c-v-3008-rerun-20e634_*`、1030b 卷。

## 2. 已通过的部分

| 项 | 结果 |
|---|---|
| 工具核对修正 | 旧 state 的 v1、repeat、v2 Preview 用新核对只读验证，均为 631，通过（日志 `3f0dcd60…`） |
| 1030b 对照（上次运行 v1） | commit `t65vcsdn…` 与 1030b `v5fu8c7e…` 的 631 张表哈希全部一致；canonical state 均为 `sha256:1f53df33…`（日志 `b763b3ec…`） |
| v1 Submit | SUCCEEDED；三个 worker step 均 `attempt_count=1`，`captured_session_count=1` |
| v1 repository-read、repeat v1 | 通过 |
| v2 Preview / Submit / repository-read | 通过；v2 Submit 同样三步 `attempt_count=1`、一次会话 |
| v2 approve / archive、v3 Preview | 通过；v3 Preview 631 表、64 changed |

S1c 的核心行为（2× t4 的 Submit 无人工干预完成）在两次独立运行中都已出现，修正后的 repository-read 核对也已在真实运行中通过。

## 3. 失败事实

- 操作 `op-08fb99454d85d34e7c8d2738`（v3 Submit），失败在第 1 步 `prepare_import`，`attempt_count=1`，用时 688 s。诊断为 `OPERATION.PURE_RECOMPUTE_FAILED`，消息 `pure-recompute handler raised ValueError`（来自本次 control DB 的副本，只读读取，原卷 SHA256 读取前后一致）。
- submit attempt `sa-7197c624…` 停在 `PREPARED`。这一步是纯计算，没有向 Repository 发起导入（`repository_operation_id` 为空），没有外部副作用。
- worker 时间线：10:10:59 认领 → 10:11:01 读 v2 commit 的 catalog → 10:15:26 再读 catalog → 10:15:26–10:19:30 读 61 张父表的行 → 约 3 分钟计算 → 10:22:24 失败。v2 Submit 的第 1 步按相同顺序读了同样数量的父表，之后计算约 11 分钟成功。所以异常出现在读完父表之后的 patch 计划或包构建阶段。
- worker 与 Repository Service 日志都没有 traceback。`recovery.py` 对 PURE_RECOMPUTE 能力的兜底分支只记录异常类型名。这个分支在 `p6-s1b-exit` 已经存在（当时位于第 746 行），不是 S1c 新增的。
- v3 的输入：工具在 v2 Archive 之后再次上传 **v1 的包**（`real_dump_journey.py` `v3-upload` 使用 `v1_bytes`），以 v2 为基线。v3 的 `canonical_business_digest` 等于 v1 的 canonical state `sha256:1f53df33…`。这是“回退到更早内容”的 Submit。

## 4. 判定

1. **不是工具缺陷。** 失败由产品 operation 返回，工具只是观察到终态。DC66 第 5 项与 DC68 都不适用，停止正确。
2. **不在 S1c 改动面内。** S1c（`p6-s1b-exit..3008d578cf`）在 Submit 路径只改了 await_import_result、恢复与租约相关代码，没有改 prepare_import、`import_publication.py`、mutation planning 或 storage projection。初步判断是此前就存在的缺陷，回退型 Submit 第一次在真实数据上执行就暴露了。确认要等第 5 节第 1 项的 traceback。
3. **不在 S1c 的约定取证范围内。** DC66 修订约定的是一次 2× t4 完整旅程，上一次 ct108 运行（`78d8cf6727`）没有用 `--three-node-history`。我在复核 3 的重跑要求里把 v3-preview、v3-submit 列入 checkpoint，基准会话因此开启了三节点模式。偏差的原因在审核方，不在实施方。
4. **执行偏差可以接受。** 第一次启动因“三节点要求冷缓存”参数校验在被测对象运行前失败，修正后重做（DC68）。`--evidence-out` 不能与 `--keep-stack` 同用，因此没有保留运行中的容器；卷、checkpoint 与日志都已保留，诊断所需材料齐全。
5. **但缺陷必须修。** 用户重新上传旧版本是正常业务操作，现在会稳定失败。设计 §16.3 的 H2-三节点场景（基准阶段只报告）也会因此拿不到数据。基准正式测量前必须修好。

## 5. 处置

1. **诊断（S1c 实施者，ct108，只用副本）**：
   - 从 `checkpoints/v3-submit` 复制三个卷到新 project 并启动栈。
   - 在 V 的 worker 镜像内用调试脚本直接调用 prepare_import 的构建（`_build_prepare_import_build_input` → `SubmitImportPublicationAdapter.build_and_publish`），捕获完整 traceback。
   - 定位抛出 ValueError 的函数、涉及的表与行形态。
   - 不改产品代码，不写原卷与 checkpoint。按 DC30 只做这一段。
   - 产出：traceback、根因说明、最小复现（理想情况是一个不依赖真实数据的单元测试），日志 SHA256。
2. **owner 决定修复放在哪里**（诊断后）：
   - **甲（建议）并入 S1c。** 修复作为 S1c 的追加提交，形成新的 V'，经审核后：
     - 04 跑权威 runner，按包沿用只跑变化的包；
     - 05 跑 focused 测试与 t1；
     - ct108 跑一次 2× t4 三节点完整旅程，exit 0，并做 1030b 对照。
     - 优点：ct108 只需再跑一次（约 4.5 h），基准仍以 `p6-s1c-exit` 为起点，不用改 DC65。
   - **乙 单独修复任务。** S1c 先补齐两节点旅程的剩余步骤（从 v2-submit checkpoint 续跑，或整档重跑）后 exit。修复另起短任务、另打 tag，基准起点改为该任务的 exit tag（DC65 修订）。ct108 要多跑一次。
   - 若诊断表明修复涉及面大（例如需要改 Contract），回到 owner 重新决定。
3. **保留**：本次与上次运行的卷、checkpoint、日志保留到 S1c exit 合入之后。
4. **另记**：PURE_RECOMPUTE 兜底分支不记录 traceback，本次因此只能离线诊断。建议在修复时同时记录异常的堆栈（只写日志，不进入 diagnostic 与 API 输出），作为同一处修复的一部分，不另立机制。

## 6. 结论

| 项 | 判定 |
|---|---|
| 测量工具修正 | 通过（DC66 第 5 项） |
| 1030b 对照 | 一致 |
| S1c 约定范围内的行为 | 再次通过 |
| v3 Submit | 产品缺陷，初步判断此前就存在；先诊断，再按第 5 节第 2 项由 owner 决定 |
| S1c exit | 暂不具备条件 |
