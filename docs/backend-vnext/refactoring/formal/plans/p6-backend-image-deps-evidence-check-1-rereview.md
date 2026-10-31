# Phase 6 backend 镜像依赖层调整：证据复核 1 的短复审

状态：**通过。** 可以在新候选上重跑 04 六包权威 runner，第 1–4 步沿用（[证据复核 1](p6-backend-image-deps-evidence-check-1.md) §4）。

## 1. 对象

- 新代码候选 `861ab2467329c9784f1d64c70855d50c84dc36f6`，由测试修订 `9600b33927` 与 `861ab24673` 组成；handoff 提交 `b8507fd6f8` 与 `315e37c949`（tip）。
- `642f2d3ac7` 与 handoff `815a898155` 未改写。
- 审核 bundle `/home/dev/gdds-p6-backend-image-deps-evidence-check1-review-315e37c9.bundle`，SHA256 `b3d93aed…`，`git bundle verify` 通过。

## 2. 核对

- 范围：`642f2d3ac7..315e37c949` 共 5 个文件，只涉及 `vnext/backend/tests/` 两个文件、`vnext/repository_service/tests/` 两个文件与 handoff。backend 镜像不复制这些测试目录，Dockerfile、构建脚本与闭包脚本均未改动。
- E1：两个 `_compose_env` 改为在 `os.environ.copy()` 上 `update`，键与原来相同，与其他 Compose 测试一致。已关闭。
- E2：fixture 清单加入 `backend/Dockerfile.dependency-base`。另外，fixture 原先给 `rust/rust-toolchain.toml` 放的是占位文本，候选的闭包脚本按 TOML 读取该文件取默认基础镜像，读取失败。修订改为复制仓库中真实的 `rust-toolchain.toml`。这一处复核 1 没有指出，是在 05 调试时发现并修正的。已关闭。
- E3：测试先 `monkeypatch.delenv("GATEWAY_DOCKER_BUILD_NETWORK", raising=False)`。已关闭。
- 05 日志（审核者在 05 上核对）：
  - `p6-backend-image-deps-evidence-check1-861ab246-validation.log`：构建脚本测试 20 passed，闭包测试 37 passed，E1 两个文件收集到 3 个用例，五包 ruff/mypy 通过。
  - `p6-backend-image-deps-evidence-check1-retry-861ab246-05.log`：`test_run_tests_script.py` 21 passed。
  - 两份日志的 HEAD 都是 `861ab24673`。
- 05 上的首次失败（fixture 中 Rust selector 无效）发生在修订轮的调试测试中，属于 DC30 的调试，不是取证步骤；修正后通过。

## 3. 下一步

在 04 新候选 `861ab24673` 的 clean worktree 中重跑六包权威 runner，环境按复核 1 §4 与修订提示词第 3 步（与 S1c 的 04 runner 一致，另加预置开关、dependency-base tag 与 `GATEWAY_DOCKER_BUILD_NETWORK=none`）。handoff 记录 `642f2d3ac7..861ab24673` 的 diff stat 与第 1–4 步沿用，然后交证据复核。
