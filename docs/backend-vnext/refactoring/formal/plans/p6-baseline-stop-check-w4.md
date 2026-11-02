# Phase 6 重建对照基准：W4/S4/H1 停止复核

- 结论：**W4 输入本身无效，是测量工具的生成缺陷，不是产品问题。** W4 生成器改写 ordered 表时不保持 `no` 连续，产品的 ordered 投影因此拒绝全部 54 张非空 ordered 表。W4 10% 与 100% 两份输入都受影响，W4、W4-FULL、W4-STRESS 都不能用现有输入运行。另外发现 W4、W4-STRESS、S4 三项锁定的 10% 参考无效（第 4 节）。修正生成器、重新生成两份 W4 输入后再测 W4 系列；不依赖 W4 输入的场景可以先继续。
- 日期：2026-11-02。
- 对象：ct108 project `p6bw4s4h120261101a`，工具 HEAD `67f90a3b77`，证据目录 `/home/dev/gdds-p6-logs/baseline/scenarios/ct108-w4s4h1-20261101a/`（launch.log `1bac5e75…`、run.json `6e383734…`、state.json `5b22145d…`、输入复核 `b748460c…`，审核者在 ct108 重算一致）。
- 依据：DC66 第 1、5 项，DC68（含澄清）；设计 §5.6、§16.3；[输入停止复核](p6-baseline-stop-check-input.md)。

## 1. 核对结果

| 项 | 结果 |
| --- | --- |
| 运行 | 2026-11-01 20:30:27–20:51:15Z。V′ 镜像身份预检通过；离线 composite 比较用时 1221.775 s；Compose 启动后、首个 operation 之前，工具因 `ordered census must be COMPLETE before the journey` 退出，runner exit 125，run.json exit 1 |
| 输入 | composite 记录的输入是 v1 `74974e5f…`（2× v1）、v2 `18b22c66…`（W4 10%），与期望一致。运行后复核为 MISMATCH，原因是没有任何上传，observed 为 null，不代表上传了错误的包 |
| 节点 | 无容器、无旅程进程；占用标记由 `p6-baseline-measure` 持有；保留三卷 `p6bw4s4h120261101a_*`；磁盘剩余 231 GiB |
| 此前场景 | 2× full-v2 正确输入重跑 `p6bw3fullretry20261101d`（HEAD `67f90a3b77`）run.json PASS，exit 0，输入复核 MATCH；错误输入运行 `p6bw3fullretry20261101c` 的卷已删除。实施方尚未把这两项写入 handoff |

## 2. 根因：W4 生成器不保持 ordered 表 `no` 连续

- 产品 `storage_projection/_ordered.py` 要求每张 ordered 表的 `no` 恰好是 1..N，否则判 `ROW_INTEGRITY`。真实数据都满足这一点：同一份 census 中 v1（2× v1）的 144 张 ordered 表全部 COMPLETE。
- `p6_s1b_synthetic_load._make_w4` 改写 ordered 表时：删除排在最前的若干行，留下空洞；把一行“位移”到 max+1，原位置空出；插入行从 max+1 往后编号。结果是 `no` 不连续。
- 审核者只读统计 `census/w4-10pct.json` 与 `w4-100pct.json`：v2 都是 144 张 ordered 表中 54 张 FAILED，全部为 `ROW_INTEGRITY: ordered no must be the continuous range 1..N`。FAILED 的恰好是 v1 中全部 54 张非空 ordered 表；其余 90 张原本为空，生成器只补了 1 行，所以通过。
- 用这样的输入，Preview 会把这 54 张表判为失败，测到的不是设计 §5.6 定义的“全部表、每表约 10% 行变化”。
- 这个缺陷从 S1b 起就存在。S1b 只运行生成器，没有让 W4 经过产品旅程，所以一直没有暴露。

## 3. 为什么没有提前发现

1. **census 状态早已记录 FAILED。** 两份 W4 census 在 10-30 生成时就是 FAILED，但输入准备、实施方的输入摘要、审核者的 `check-baseline-inputs.py` 与放行检查，都没有检查 census 状态。这是审核方核对范围的又一个缺口。
2. **输入摘要取错了 census。** `p6_baseline_inputs.py` 汇总 W4 两项时读取的是 2× census 中 v2 的计数，所以 handoff 输入表中 W4 10%/100% 的行数（874,023）实际是 2× v2 的数字。
3. **检查放在了 Compose 之后。** journey 中的 census COMPLETE 检查只读输入文件，却排在 20 分钟的 composite 比较与 Compose 启动之后。

实施方停止正确：失败虽然发生在被测对象处理任何请求之前，但输入本身无效，DC68 的重做不能解决问题。

## 4. 锁定的 10% 参考有三项无效

| 项 | 锁定参考 | 问题 |
| --- | --- | --- |
| W4 10% | S1b handoff「S1b synthetic load」737.931 s | 这是 S1b **生成器** `make-w4` 的运行时间（`/home/dev/gdds-p6-logs/s1b/ct108-w4-generation-80ce756619.log`：`ELAPSED_SECONDS=737.931`），不是产品计时。拿整次旅程与它比较必然偏离超过 10%，会触发没有意义的补测 |
| W4-STRESS | 同节 726.647 s | 同上，也是生成器时间 |
| S4 | S1c `b96fe8e4cc` 的 v3 Submit 1302.825 s | S1c 的 v3 是把 v1 重新上传到 v2 上（回退），变化面与 v2 相同（64 张表），不是 W4 的全部表变化；actual 指针 `/steps/v3-submit/...` 在 W4 运行中也不存在（W4 的 Submit 是该运行的 v2-submit） |

建议三项都改为“无参考，只记录”。W4 的验收按设计 §16.1/§16.3 的业务目标在终审判定，不经由 10% 补测规则。放行检查只要求实施方写出参考，没有逐项审查这张表，这次一并更正。

## 5. 处置建议

1. **修正生成器**（DC66 第 5 项，只改 `vnext/backend/benchmarks/` 及其测试）：
   - ordered 表的输出必须满足产品的 ordered 投影：每张表 `no` 为 1..N，不重复。做法由实施方决定，要求每表变化量仍约为设定比例，例如删除取 `no` 最大的若干行，插入接在新的 N 之后，位移用交换两行（优先 real gid）的 `no` 实现；无法位移的表记入计数。
   - 生成后对两份 W4 输入运行与旅程相同的 census，要求所有数据集 `ordered_projection.status` 为 COMPLETE、所有表 COMPLETE，否则生成失败。
   - `p6_baseline_inputs.py` 的输入摘要读取各变体自己的 census。
   - focused 测试：含 blank gid 与 real gid 的 ordered 表，生成结果通过 `project_ordered_rows`；10% 与 100% 两档各一例。在 05 运行 focused 测试与五包 ruff/mypy。
2. **把 census 检查提前到 Compose 之前**，与期望输入清单检查放在一起；不满足即 exit 非 0，不启动服务，按 DC68 属于未触及被测对象的错误。运行后输入复核在没有任何上传时报告“未上传”，与“哈希不符”区分。
3. **重新生成两份 W4 输入**，写入新的输入目录，不覆盖 `input/1ed24d38f0`（它是已完成场景的输入证据）。2× v1/v2 不变（`74974e5f…`/`121dc3b0…`），W4 的 v1 仍为 2× v1。验收条件全部由程序给出：census 全部 COMPLETE；重复生成 SHA256 一致；按表的插入/删除/修改/位移计数；由新输入生成期望输入清单。满足后实施方直接继续，不另设 owner 检查点，记入 handoff，由终审复核。
4. **更正参考表**：W4、W4-STRESS、S4 改为只记录（第 4 节），提交到 `p6_baseline_timing_references.json` 与 handoff。
5. **场景顺序**：不依赖 W4 输入的场景（H1-REFILL、H2 两节点与三节点、H3 中不需要 W4 输入的部分）可以现在继续；生成器修正在开发节点和 05 进行。重新生成要在 ct108 上运行，安排在两个场景之间，不与测量重叠。W4、W4-FULL、W4-STRESS 在新输入通过检查后运行。
6. **清理**：`p6bw4s4h120261101a` 的三卷没有任何上传，可以立即删除，记入 handoff；其 evidence 与日志保留。composite 缓存中这次新建的条目以输入摘要为键，不会被新输入命中，保留即可。
7. **handoff**：补记 full-v2 正确输入重跑的结果、错误输入卷的删除、本次停止与第 3 节第 2 项的输入表更正；更新剩余估计，超过 48 小时就停下交 owner。
