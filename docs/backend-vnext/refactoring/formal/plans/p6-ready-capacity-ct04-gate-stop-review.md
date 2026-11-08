# Phase 6 READY 容量恢复：04 门禁停止定向复核

- **结论：首次 runner exit 1 必须保留；7 项失败均归因于新 worktree 未准备 Repository Service Python 环境，定向归因成立。按 DC80 及本次 owner 接续授权，在同一 clean 候选补齐离线环境并重跑既定 backend 门禁，无需再次请求 owner/design 确认。尚未放行 CT108 恢复。**
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 门禁/镜像候选：`a16439d7cf9a7d2d90ed7cb6da0330bd649e0fb8`；停止 handoff：`3ac1839cb4c80c243a53c322e6ed1e2a366a104b`；接续授权补记见 main `386571cb39` 的 DC80。
- 方法：在 `/home/dev/gdds-p6-capacity-gate-stop-3ac1839c` detached worktree 只读核对源码与 handoff；04 只读原日志，CT201 只读构建归档；未取节点标记、未写运行 worktree、未启动测试或修改环境。

## 1. 失败归因

04 原日志 `/home/dev/gdds-p6-logs/baseline/scenarios/capacity-resume-h-20261105/ct04-backend-container-gate.log` 重算 SHA256 为 `f1b3e05504907b25cd209ca493fe7c98573ebd9ea1d381fff434f88b1ccde6a5`，匹配 handoff。起止 HEAD 均为 a16439；运行时间 16:44:39Z–16:54:36Z，runner/wrapper exit 均为 1。并行批次 3,280 passed/5 failed，serial 批次 60 passed/2 failed，合计 3,340 passed/7 failed。

7 个失败的最终异常均为 `tests/support/submit_job_harness.py:427` 的 `RuntimeError: repository_service .venv is missing; run ./vnext/scripts/prepare-dev-dependencies.sh`。源码 `_repository_service_python()` 检查 `repository_service/.venv/bin/python`，在构造子进程命令参数时即抛错；这些用例尚未启动其所需的 RS 子进程、未进入对应产品断言。`run-tests.sh` 确实只同步所选 Python 包，本次只选 backend，不能保证新 worktree 的 RS 环境已经存在。

这不把整次 runner 改判成功，也不把已开始测试的失败追溯为不限次数预检。失败日志保留，后续整次既定 backend runner 重新执行；不扩大为无关全基准重测，不绕过失败用例。现有 DC80 和 owner 本次明确授权已覆盖环境修正与接续，handoff 中“等待 owner”不再是阻塞理由。

## 2. 修复路径与重跑前提

原实施者重新取得 04 自有占用，在 `/home/dev/gdds-p6-baseline-capacity-resume-a16439-04` 保持 clean a16439，使用 `UV_OFFLINE=1 GATEWAY_DEV_OFFLINE=1 ./vnext/scripts/prepare-dev-dependencies.sh` 补齐环境；核对 RS Python、五锁与 HEAD、Rust 工具链/扩展输入及原候选镜像身份。保留不经代理、`CARGO_NET_OFFLINE=true` 和原预置镜像配置，重跑相同 `GATEWAY_TEST_PACKAGES=backend` 权威入口。

补齐环境会改变测试输入环境，应以新 runner 的起始 manifest 和实际结果作证据，不沿用首次失败 manifest 为通过结果。代码未变且镜像身份仍匹配时，不要求仅因补齐 host venv 重新构建 H 镜像。若再有实际失败，继续按授权主动诊断处理，保留证据，不能跳过未通过的验收。

## 3. 并行完成的镜像材料核对

已提前核对 CT201 构建归档，缩短后续等待；此节不替代 04 成功门禁或最终目标 approval：

- 构建日志 SHA256 `ceb8a8bd35d03101ab01764f77199136b71549d3e09661e7823dffb977ad20d1`、传输日志 SHA256 `f71ea3897d1ca5b762578f9e7badcc1ea7ad572acd5cc858e8447fc493c67d9e` 均独立重算匹配。构建起止 clean a16439、vnext tree `0ebce55391446c056d0cf1b259412d1ef5770d97`、exit 0。
- 独立重算 397,088,256 字节 Docker 归档 SHA256 为 `a4072b448219bd3b0b0a75d49d7e70681ba5e3fddf4aa0c8f01e695ebcd90561`；从归档 manifest/config 直接取得两个 project tag，config digest 均为 `sha256:8f03a1fbcf8333ad752793d7ca1e8d9983c4b13a0956881be1c4f2e31749010b`，全部 15 个 RootFS DiffID 与机读清单程序比较一致。
- 归档身份清单 `archive-image-identity.json` SHA256 为 `eccffd7e8ef9295da4661601e33945518baf2371b3eb36e3cc7ca590cbf37873`。它仅是构建/传输身份记录，不能替代 04 门禁后从实际目标 tags 生成的 fixed approval JSON。
- 04 首次预检日志 `ct04-pre-gate-identity-preflight-retry.log` SHA256 `7a2b2ce34723c3c605f2aaebd20895cdc3872f9e112b707fbe6d354f77fc6b49` 重算匹配，记录 backend/worker config 和全部层、RS build-input/source-tree/uv-lock 标签及 worktree/legacy 均 MATCH。RS 构建日志 SHA256 `8c5534daee6af86a99da54b1a5ede8d820807aa3df2173c3bde66581b81ccc90` 和首次 postflight SHA256 `d040a56dbafd9090846231f36a36e1d90e37735c769943f919f08156f7020827` 亦重算匹配。最终恢复仍核对最新目标身份，不能只引用首次预检。

## 4. 后续放行

收到重跑 exit 0 的原始 runner 日志、backend manifest、起止 HEAD、容器结果及收束记录，并取得程序生成/提交的目标身份 JSON 后，立即作最终恢复条件审核。验证满足 DC80 即直接通知实施者启动，无额外 owner/design 审批；不因审核排队重复跑已通过项目。

本报告没有宣布任何 H 容器门禁通过，也没有声明 CT108 已恢复。未改产品、设计或执行计划正文，未推送；自身审核 worktree 用后清理。
