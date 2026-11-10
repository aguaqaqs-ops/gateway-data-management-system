# FE4a 提示词发出前的重核（FE4 kickoff §11.1 前置条件）

- **执行者：** FE4 kickoff 审核会话，2026-11-10（UTC）。
- **依据：** FE4 kickoff（main `a4c4d60827`）§11.1 前置条件第 1–3 项；§2.5、§6.1、§6.2、§7.1。
- **结论：前置条件全部满足，可以发出 FE4a 实施提示词。**

## 1. 定向复核与合入（前置条件 1）

- 定向复核通过：`fe4-kickoff-rereview-1.md`（`be3dc218f8`）。
- 修订 3（`f118e0fbbe`）处理了 R1–R4，并把 §4、§10 中的后端记录改为与 `e2eaab4db9` 一致。
- 设计会话已用 `--no-ff` 把 `fe4-kickoff` 合入本地 main，合并提交 `a4c4d60827`，两个父提交为 `e2eaab4db9` 与 `f118e0fbbe`。合入只带进 `docs/frontend-vnext/` 下 4 个文件，未推送。
- 提示词中的 `[kickoff 确认提交]` 与 `[确认提交]` 填 `a4c4d60827`。

## 2. 分支、tag、main 与常量（前置条件 2，开发主机只读）

| 项 | 实测 | 结论 |
| --- | --- | --- |
| `fe-vnext` | `e22e39ba15`，worktree `/home/dev/gdds-fe` clean，reflog 末条仍是 FE3c fix2 handoff 的提交；`e22e39ba15` 是 `16ffe72829` 的祖先 | 可以快进 |
| `p6-exit` | 指向 `b0fc25e881`，`vnext/` 为 `49c1de43be` | 不变 |
| `16ffe72829:vnext` | `49c1de43be` | 不变 |
| main 当前头（只记录） | `a4c4d60827`，`vnext/` 为 `49c1de43be` | FE4a 合入点仍为 `16ffe72829`，不随 main 改变 |
| t1 常量 | `16ffe72829:vnext/backend/benchmarks/real_dump_journey.py` 第 192 行 `S2B_DATASET_BASELINE`、第 234 行 `S1B_V2_PREVIEW_CHANGED_COUNTS`，都是模块级常量 | 存在 |

## 3. 节点现场核对（前置条件 3）

**方法：**
- 每个节点先原子 `mkdir /home/dev/gdds-node-busy.d` 取得占用标记，会话名 `fe4a-prompt-recheck`，用途写明“预检，不运行测试”；核对完立即释放。三个节点开始时都没有他人的标记。
- 镜像身份：用 `docker image save` 流式读取，计算 config digest 与全部 RootFS DiffID，不使用 inspect ID。
- `--print-input`：在节点上 clean 的 main 检出（HEAD `16ffe72829`，`vnext/` 为 `49c1de43be`）中运行 `vnext/scripts/build-backend-dependency-base.sh --print-input`。该命令只读输入文件，并把基础镜像临时保存后删除；没有运行测试，也没有构建。

| 项 | 05 `gw-dms-test-05` | 04 `gw-dms-test-04` | 07 `gw-dms-07` | 预期（FE3c 记录） |
| --- | --- | --- | --- | --- |
| 核对时间 | 06:14:03–06:14:54；`--print-input` 复跑 06:16:14 | 06:14:54–06:15:45；复跑 06:16:28 | 06:15:45–06:16:03 | — |
| 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble` | config `a0d7b2b4…a017`，7 个 DiffID | 同左 | 同左 | config `a0d7b2b4…a017`，7 个 DiffID |
| 三节点 DiffID 列表 | 相同（按行拼接后 SHA256 的前 12 位 `7a4c3e9927de`） | 同左 | 同左 | 三节点相同 |
| npm 归档 | `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`：`0d861824…89f4` | `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`：`0d861824…89f4` | 同 04 路径：`0d861824…89f4` | `0d861824…89f4`，来源提交 `a2fb4a027a` |
| `gateway-backend-deps:lock-578e079b762e` | config `46c00a3b…e939`，19 个 DiffID；label `578e079b…3ff5` | 同左，DiffID 列表与 05 相同 | 不需要 | config `46c00a3b…e939`，19 个 DiffID |
| `gateway-p2r1-repository:lock-6dc9659f0aee` | config `98d0801b…9ec9`，16 个 DiffID | 同左，DiffID 列表与 05 相同 | 不需要 | config `98d0801b…9ec9`，16 个 DiffID |
| `--print-input` | exit 0；输入摘要 `578e079b…3ff5`，即 `gateway-backend-deps:lock-578e079b762e`；基础镜像 `rust:1.97.0-bookworm` | 同左，输入摘要相同 | 不需要 | `lock-578e079b762e` |
| t1 目录 | `SHA256SUMS-t1-v1.txt` `cdb598cd…0163`、`-t1-v2.txt` `fa2450fa…a96a`，各 19 行，`sha256sum -c` 全部通过；`SHA256SUMS-t4-v1.txt` `b8938dcc…9165`，528 行（仅在打包流程改变时使用） | 没有 t1 目录 | 没有 | 与 FE3a handoff §4.1 相同 |

**结论：**
- 05 可以承担真实 backend 与 t1 的调试；
- 07 可以承担模拟接口的调试；
- 04 可以承担模拟接口全量、上传包校验与 `journeys` 证据，但没有 t1 目录，t1 证据按 kickoff §7.1 在 05 运行；若改在其他节点，需先按 DC67 整目录传输并逐文件核对。

证据运行前，审核会话会在所选节点上再做一次同样的核对。

## 4. 本记录的十六进制核对

本记录的十六进制值，用首轮审核的同一脚本回源到 git 对象、FE3c 记录（`fe3c-handoff.md` §9.2、`fe3-kickoff.md` §2.2、`fe3a-handoff.md` §4.1）与上述节点输出。截断值写成“前 8 位…后 4 位”，各唯一对应一个 64 位原值。结果见文末。

**结果：**
- 共 20 个不同值，全部回源：
  - git 对象 9 个，唯一命中（commit 8、tree 1）；
  - 12 位镜像 tag 后缀 2 个，在来源文档中原样出现；
  - 截断值 8 个，在 FE3c 记录或节点输出中各唯一对应一个 64 位值；
  - DiffID 列表摘要 1 个，与节点输出的前 12 位一致。
- 没有未命中值，没有长度异常值。
- 起草时有两处错误，已在提交前更正：工具链 config 的末 4 位误抄为 `1017`，正确为 `a017`；DiffID 列表摘要原写 16 位，已改为 12 位。
