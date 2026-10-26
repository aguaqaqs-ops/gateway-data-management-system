# Phase 6 S0 kickoff 小修：轻量审核

- 日期：2026-10-26
- 审核对象：分支 `p6-s0-kickoff`，`a64f9a1b7d..8513cae600`（实现与门禁提交 V = `b46a799d80`；handoff `8513cae600`）
- 依据：[执行计划](p6-execution-plan.md) §2 S0（kickoff 小修的范围与审核方式）；[kickoff handoff](p6-kickoff-handoff.md)（在该分支上）；AGENTS
- 审核方：Phase 6 S0 讨论会话（编写任务提示词，未参与实施）
- 结论：**通过，没有阻塞问题。** 可以合入主线；合入后 S1a 的前置“kickoff 小修经轻量审核通过”成立。

## 1. 核对内容

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 改动范围 | `git diff --stat` | 11 个文件：`uv-consume.sh` 与其测试、`real_dump_journey.py` 与其测试、`deploy/compose.yaml`、5 份文档整理与 handoff。没有改产品 Python/Rust 代码、Phase 6 设计、执行计划或决议记录 |
| uv 锁快照清理 | 阅读 `uv-consume.sh` 与新测试 | 新增 `trap cleanup_lock_snapshot EXIT`；脚本中没有 `exec` 与其他 EXIT trap，trap 不会失效或被覆盖；原有显式清理保持幂等。两个回归用例覆盖 uv 失败与 SIGTERM，信号用例标为 `serial`（固定时间预算，符合 AGENTS“写测试”） |
| SQLite 旁路文件 | 阅读 `real_dump_journey.py` 与测试 | 残留来自测量工具中查询 control DB 副本的内联脚本，只在 finally 中补删 `-shm`、`-wal`；两个用例改用独立 `TMPDIR` 并断言无残留。不涉及产品持久化 |
| RS defunct `dolt` 进程 | 阅读 Compose 改动与 handoff 的复现记录；核对测试 harness 的 Compose 来源 | 根因为容器 PID 1（`runuser … uvicorn`）不回收 dolt 派生的孤儿进程；`repository-service` 增加 `init: true`。修复前 60 次逐表读取使僵尸进程从 74 增至 134，修复后读取前后均为 0（05，日志见 handoff）。backend 与 repository_service 的 Compose 测试 harness 都使用 `deploy/compose.yaml`，修复同时覆盖生产与测试 |
| 文档整理 | 阅读 5 份文档的差异 | 只加“已由 ADR 0019 取代（历史表述）”标注、“历史 Deferred register”与“P5 exit 后的当前处置”小节，补齐 DC28–DC34 索引、澄清 DC26；没有改动决议内容。抽查两条“已关闭”的断言：`defer_operation_terminal=True` 在 `submit_jobs.py` 中有生产调用；`test_http_admission_shutdown_process.py` 现标为 `integration` 与 `serial`，均属实 |
| 04 全量门禁 | 读取 `04:/home/dev/gdds-p6-logs/p6-s0-kickoff/authoritative-runner-b46a799d80-rerun1.log` 与 postflight、镜像构建日志 | `hostname=gw-dms-test-04`；起止 HEAD 均为 `b46a799d80`；六个包全部 passed（237 个 Rust 测试；backend 2917 + 39；repository_service 1740 + 206，1 skipped）；`runner_exit_code=0`；构建输入检查 `status=ok`；postflight 无 Dolt、容器与 8000 端口占用；RS 镜像 revision 标签为 `b46a799d80` |
| 门禁 worktree | 节点上核对 | `/home/dev/gdds-p6-s0-gate04` 停在 `b46a799d80`，clean；按 DC51 保留到合入之后 |

## 2. 观察（不阻塞）

1. **门禁环境偏差：** 第一次 runner 预检因 SSH root 的 PATH 不含 Rust 工具链而失败，没有运行任何包；重跑时把 `/root/.rustup/toolchains/1.97.0-x86_64-unknown-linux-gnu/bin` 直接加入 PATH。版本与 `rust-toolchain.toml` 一致，结果有效。但这与 DC48 门禁固定环境（PATH 含 `/home/dev/.cargo/bin`，rustup 按 selector 选择工具链）不同；`rust` 包闭包记录 PATH 指纹，日后若以本次为来源 V 做 carried，须使用相同环境。建议之后的门禁都沿用 DC48 的门禁脚本（`/home/dev/gdds-p6-logs/dc48/run-gate.sh` 的环境设置），由负责 DC36 的会话考虑是否把它固化进 testing-conventions。
2. **合入：** 分支基于 `a64f9a1b7d`，之后 main 增加了 keyless 普查工具提交 `e5840be32c`，两者改动的文件不重叠。按惯例用 merge commit 合入，不改写已被引用的提交。
3. **镜像身份：** 本次 Compose 改动属于强制重建项，已在 V 上重建并运行；合入后的 HEAD 只多文档与测量工具提交，S1a 的门禁会在其最终候选上重新建立证据，不需要为合入单独重跑。

## 3. 待 owner 决定

1. 用 merge commit 将 `p6-s0-kickoff` 合入 main，并推送、同步三台节点。
2. 合入后清理：04 的门禁 worktree `/home/dev/gdds-p6-s0-gate04`；开发主机的 linked worktree `/home/dev/gdds-p6-s0-kickoff` 与已合入的分支。节点上的日志保留作证据。
