# DC48 轻量审核：Rust 测试进入权威门禁

- 日期：2026-10-25
- 审核对象：`0c5a3f458c..4d1f70af33`（实施提交 V = `4526084da1`，handoff `4d1f70af33`）
- 依据：[交接说明](p6-dc48-rust-test-gate-handoff.md)、[实施 handoff](p6-dc48-handoff.md)、[Phase 6 S0 Owner 决议记录](p6-s0-owner-decisions.md) DC48、DC51、DC52
- 审核方：Phase 6 S0 讨论会话（编写交接说明，未参与实施）
- 结论：**通过，没有阻塞问题。**

## 1. 核对内容

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 改动范围 | `git diff --stat` | 9 个文件：runner、闭包脚本、新检查脚本、扩展 `lib.rs`、两个测试文件、AGENTS、testing-conventions、handoff。没有改动 Phase 6 讨论稿、决议记录、implementation-stages 或旧扩展的生产代码，符合交接说明第 5 节 |
| runner | 阅读 `run-tests.sh` 的差异 | `rust` 包最先运行，三步都执行，任一失败则该包失败、其余包照常运行；`CARGO_TARGET_DIR` 在 worktree 外，使用前与退出时删除；backend 同步强制重装扩展，随后检查构建输入，不一致时在 manifest 之前停止 |
| 构建输入检查 | 阅读 `lib.rs` 与检查脚本 | 扩展以 `option_env!("GATEWAY_RUST_BUILD_INPUT")` 在编译时嵌入 `vnext/rust` 的 tree id；cargo 跟踪 `option_env!` 读取的环境变量，值变化即重新编译。runner 要求 clean worktree，工作区文件与 HEAD 一致，比较 HEAD 的 tree id 成立。没有新增 `build.rs` 或依赖 |
| 闭包 manifest | 阅读 `test_input_closure.py` 的差异 | `rust` 包的组成与交接说明一致，另记录 PyO3 构建脚本所选解释器、`CARGO_*`/`RUST*`/`PYO3_*` 等设置指纹与 cargo config 内容；这些只会使判定更倾向“运行” |
| 文档 | 阅读 AGENTS 与 testing-conventions 的差异 | 与实现一致；DC51 的门禁 worktree 保留规则已写入 |
| 04 全量门禁 | 读取 `04:/home/dev/gdds-p6-logs/dc48/04-full-runner-4526084da1.log` | `hostname=gw-dms-test-04`；起止 HEAD 均为 V，`end_dirty_entries=0`；六个包均 `passed`；`runner_exit=0`，2456 s；`rust` 包 26 s，205 个 Rust 测试通过；构建输入检查 `status=ok` |
| 04 carried 演练 | 读取 `04-carried.log` | 同一 worktree、同一 HEAD，六个包均“可沿用”，`changed=[]`；`rust` 包总摘要 `ce1386874287…` |
| 05 反例 | 读取 `05:/home/dev/gdds-p6-logs/dc48/05-counterexample.log` | 只提交 `.rs` 改动后，普通 `uv sync` 保留旧扩展，检查失败（rc=1）；runner 强制重装后检查通过；检出旧提交而不重新同步，检查再次失败。讨论稿 §12 中“Python 测试可能使用过时的 Rust 扩展”由此**实测确认** |
| 独立复跑 | 审核方在 05 的验收 worktree（detached，V，clean）运行 `GATEWAY_TEST_PACKAGES=rust ./vnext/scripts/run-tests.sh`，日志 `05:/home/dev/gdds-p6-logs/dc48-review/05-review-rust-runner.log` | fmt、clippy、test 均通过，205 个测试，26 s；起止 HEAD 均为 V，worktree 仍 clean，`runner_exit=0` |

## 2. 观察（不阻塞）

1. **impl crate 也被排除。** `gateway-compute-python-impl` 的测试同样嵌入 Python 解释器，owner 2026-10-25 确认一并排除到 S2a；其中 11 个不需要 Python 的单元测试在此之前也不运行。旧扩展已决定在 S2a 删除（DC52），可以接受。已补入决议记录 DC48、DC52。
2. **每次门禁都重建扩展。** 若同一 worktree 在 V 之后又被 runner 重新同步，而 maturin 构建不是逐字节可复现的，backend 的 uv 环境摘要会变化，carried 判定为“运行”。这只会更保守，不会误判“可沿用”；如以后因此多跑门禁，再评估构建可复现性。
3. **开发者 focused 测试。** 一致性检查只在 runner 中执行；AGENTS 已写明开发者改 Rust 后跑 backend focused 测试前要强制重装。

## 3. 待 owner 决定

1. **05 节点清理**（实施方的清理被 auto-mode 分类器拒绝后停止，按规则未绕过）：实验 worktree `/home/dev/gdds-p6-dc48-exp`、`/home/dev/gdds-p6-dc48-debug`，分支 `dc48-exp-plain`、`dc48-exp-cachekeys`，以及 TMPDIR 中的 `dc48-*-cargo-target`、`pytest-of-root`、`uv-*.lock`。验收 worktree `/home/dev/gdds-p6-dc48-accept05` 已完成审核复跑，也可一并清理。
2. **04 节点 TMPDIR 的遗留物**：与节点核对报告 §7.3 同类，不来自 `rust` 包。
3. **门禁 worktree** `/home/dev/gdds-p6-dc48-gate04`：DC48 属于 S0，没有阶段 exit tag；建议在推送并同步节点之后清理。
4. **推送与节点同步**：本地 main 上的提交尚未推送，三台节点的 main 仍在 `0c5a3f458c`。
