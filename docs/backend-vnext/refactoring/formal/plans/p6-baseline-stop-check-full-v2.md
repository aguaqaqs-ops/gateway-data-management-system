# Phase 6 重建对照基准：2× full-v2 停止复核

- 结论：**失败来自测量工具，不是产品结果不一致。** 工具的核对没有考虑 FULL 模式下 Preview 有两个 identity pair。另有一个工具缺陷：失败运行的 evidence 没有写出 `run.json`。两处按 DC66 第 5 项修正后，2× full-v2 场景从头重跑一次。t4 的补测处理需要在 handoff 中更正（第 4 节）。
- 日期：2026-11-01。
- 对象：`p6-baseline` handoff 提交 `f368cdd9a9`；测量工具 HEAD `46e7c52d15`；ct108 project `p6bw3full20261101a`。
- 安排：本会话负责放行检查与停止复核；基准终审仍由新开的审核对话在全部测量后进行。

## 1. 核对结果

| 项 | 结果 |
| --- | --- |
| 日志 | journey `4be4c57e…`、resources `30ea5d78…`、state `ac2efa39…`，审核者在 ct108 重算一致；runner exit 1，起止 HEAD 一致 |
| 运行前核对 | 产品 tree、V′ 镜像身份、输入核对均为程序 `RESULT=MATCH` |
| 节点 | 无容器、无 journey 进程、8000 空闲；占用标记已释放；三个失败运行卷与 S1c 保留卷在位；磁盘剩余 236 GiB |
| 运行 | v1、repeat-v1 全部通过；v2 Preview `SUCCEEDED`（4540.742 s，`pair_count=2`、`table_count=1262`、changed 64、degraded/failed 0）；v2 Submit `SUCCEEDED`（1312.992 s），未进入 R5 人工恢复 |

## 2. 缺陷一：FULL 模式的 Preview 表数核对

`_assert_synthetic_catalog_summary` 把 current 侧 SNAPSHOT_TABLE 绑定按表名收进集合，再与 Preview summary 的 `table_count` 比较。

- FULL 模式（`--full-v2`）的 v2 上传带 v1 作为 initial package，Preview 有两个 identity pair，`table_count` 是两个 pair 的表数之和。
- 审核者从失败运行保存的 v2 Preview manifest 只读统计：current 侧绑定共 **1262** 条，与 `table_count` 相等；两个 pair 使用同一批表名，去重后为 631 个。产品输出与其自身摘要一致。
- 同一产品上 `pair_count=1` 的运行（S1c 的 2× t4、本轮 2× core）这项核对都通过。这个组合（synthetic 输入 + FULL）在 S1c 修正这项核对（`95e1f02c2c`）之后第一次运行。
- 同一步在报错之前已经按 v2 期望表清单读取 Repository：Catalog 的 commit ID、composite 表与各表行读取均未报错。表名集合与表数还要等修正后的核对确认。

**修正：**
- 按 `(pair_id, table_name)` 计数，与 `table_count` 比较；
- Catalog 的表名集合与各 pair current 表名的并集比较，Catalog 表数与并集大小比较；
- `pair_count=1` 时语义不变。
- focused 测试加入两个 pair 共用表名的 manifest，以及对应的反例。
- 修正后的核对函数在失败运行保存的 manifest 上只读重放，表数这一项应通过。

## 3. 缺陷二：失败运行的 evidence 收尾

这次请求了 `history` 之前的 checkpoint，运行在更早的 `v2-repository-read` 失败。

- 收尾代码要求“请求的 checkpoint 全部已捕获”，不满足就抛错；exit code 已经是 1，异常分支不再写 `run.json`。
- 结果：evidence 目录只有 `state.json`，其中 `failure_step` 已记录，但没有 `ended_utc` 与 `exit_code`。
- DC66 第 3 项要求失败运行写完状态文件，否则其 checkpoint 不可用。CT05 的故障续跑测试中，失败发生在 checkpoint 之后，没有覆盖这条路径。handoff 没有提到 `run.json` 缺失。

**修正：**
- 失败运行只要求失败步骤之前请求的 checkpoint 已捕获；
- 无论成功失败都写出 `run.json` 与完整的状态文件，收尾错误另行记录；
- 补一个“失败发生在请求的 checkpoint 之前”的 focused 测试。

## 4. t4 补测的处理需要更正

DC66 第 1 项：偏离参考超过 10% 时补测 1 次；两次结果相差超过 5% 时测第 3 次，取中位数并报告范围。

- t4 正式 3664.874 s（偏差 10.23%），补测 1 为 3655.539 s（10.46%）。两次相差 0.26%，按规则不需要第 3 次。
- 实施方又测了一次（3675.744 s，9.97%），然后以此判定“不需补测”。这等于反复测到低于阈值为止，不符合规则。
- 三次结果很接近，说明比 S1b 参考慢约 10% 是稳定差异，不是噪声。
- **更正：**
  - handoff 记录 t4 为三次的中位数 3664.874 s，范围 3655.5–3675.7 s，偏差约 10.2%；
  - 用程序按步骤与 S1b 参考对比，说明差异落在哪些步骤；
  - 第三次运行注明不是规则要求的。
- 这不是停止条件：S1c 改了 Submit 路径（DC69），差异有可能由此解释。最终是否可以解释由终审判定。

## 5. 处置建议

1. 按 DC66 第 5 项修正第 2、3 节的两个工具缺陷：只改 `vnext/backend/benchmarks/` 与其测试，在 05 运行 focused 测试与五包静态检查。
2. 2× full-v2 场景从头重跑一次，使用新 project 名：
   - 这次没有可用的 checkpoint，DC66 第 3 项也不允许用失败运行的现场卷续跑。
   - 按 DC66 第 3 项，在每个计时步骤之前保存 checkpoint，至少包括 `v2-preview`、`v2-submit`、`v2-repository-read` 与 `history`。磁盘余量足够。
   - 失败运行的 W3-FULL 与 v2 Submit 计时只作诊断记录。重跑结果用程序与它们对比，只记录，不触发补测。
3. 失败运行的三个卷 `p6bw3full20261101a_*` 在重跑通过 `v2-repository-read` 后可以删除，删除记入 handoff。在那之前保留。
4. 恢复测量之前，在 handoff 写出剩余场景清单与新的剩余估计。若超过 48 小时，停下交 owner。
5. 本机命令失败的日志不要放在 `/tmp`，移到 `/home/dev/gdds-p6-logs/baseline/` 并更新 SHA256 记录。
6. 其余规则不变：只在停止条件出现时交 owner，全部完成后交新开的基准审核对话终审。
