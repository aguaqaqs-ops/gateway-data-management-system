# Phase 6 前置验证 V5：operation 耗时归因

## 运行与取证

- 节点：SSH alias `ct108-gw-dms`，hostname `gw-dms-test`；Linux `7.0.14-22-pve`，128 vCPU，Docker Server `29.9.1`，Dolt `2.1.11`。
- Worktree：节点上的 clean `main`，起止 HEAD 均为 `19a21c1874cccc471aef268e02d1ccacdf5782b8`。
- 测量：t4 完整旅程，结构沿用 S5 命令并指定 `--keep-stack`；开始前节点无其他测试、Dolt、Compose、port 8000 使用者。旅程结论 `PASS`，exit code `0`。
- 起止时间：`2026-10-25T03:40:26Z` – `2026-10-25T05:47:48Z`。
- Journey 日志：`/home/dev/gdds-p6-logs/v5/v5-t4-journey-20261025T034026Z.log`（0600）；完整 operation/step 摘要导出：`/home/dev/gdds-p6-logs/v5/step-records.json`（0600）。日志目录为 0700。均留在节点、工作区外；本报告不含行值、commit ID、operation ID、artifact ID 或 digest。
- 只读查询 control DB 的 `operation_records` 与 `step_records`，共 6 个成功 operation、18 条成功 step 记录。除两个 Submit 的 `await_import_result` 各为 2 次尝试外，其余 step 的 `attempt_count` 为 1。重复 v1 Submit 是幂等回放，没有新增 operation。
- 为 V7 保留：在 Compose teardown 前停止容器并复制 Repository Service 数据根至 `/home/dev/gdds-p6-v7/repo`（约 40 MiB，目录 0700，已核实包含初始化提交及 t4 v1/v2 导入提交）；随后 `docker compose down -v --remove-orphans` 成功，V5 容器、卷与网络已移除。该副本只用于 V7，完成 V7 后删除。
- 未改产品代码或 benchmark harness。

operation wall 采用 control DB 的 `completed_at_us - created_at_us`；step wall 采用 `completed_at_us - started_at_us`。这些 DB 边界不同于 Journey 的 HTTP 计时边界。以下时间以秒计，四舍五入到毫秒。

| Operation | S5 operation terminal | V5 control DB wall | 差值（V5−S5） |
| --- | ---: | ---: | ---: |
| t4 v1 Preview | 1684.782 | 1674.533 | −10.249 |
| t4 v1 Submit | 565.761 | 570.581 | +4.820 |
| t4 v1 重传 Preview | 1463.686 | 1451.591 | −12.095 |
| t4 v2 Preview | 1477.774 | 1467.357 | −10.417 |
| t4 v2 Submit | 573.831 | 575.548 | +1.717 |
| t4 History | 892.522 | 883.980 | −8.542 |

## Step 耗时

| Operation | Operation wall | Step | Step wall | 尝试 |
| --- | ---: | --- | ---: | ---: |
| t4 v1 Preview | 1674.533 | `materialize_inputs` | 931.434 | 1 |
|  |  | `assemble_preview` | 723.714 | 1 |
|  |  | `publish_preview` | 1.086 | 1 |
| t4 v1 Submit | 570.581 | `prepare_import` | 477.120 | 1 |
|  |  | `submit_import` | 0.249 | 1 |
|  |  | `await_import_result` | 70.099 | 2 |
| t4 v1 重传 Preview（changed=0） | 1451.591 | `materialize_inputs` | 1299.601 | 1 |
|  |  | `assemble_preview` | 140.710 | 1 |
|  |  | `publish_preview` | 0.768 | 1 |
| t4 v2 Preview（changed=26） | 1467.357 | `materialize_inputs` | 1301.010 | 1 |
|  |  | `assemble_preview` | 144.022 | 1 |
|  |  | `publish_preview` | 0.815 | 1 |
| t4 v2 Submit | 575.548 | `prepare_import` | 477.406 | 1 |
|  |  | `submit_import` | 0.249 | 1 |
|  |  | `await_import_result` | 71.764 | 2 |
| t4 History | 883.980 | `materialize_inputs` | 730.835 | 1 |
|  |  | `assemble_comparison` | 144.443 | 1 |
|  |  | `publish_result` | 0.030 | 1 |

## Operation 内的间隔

间隔按“受理（operation `created_at_us`）至首 step、相邻 step、末 step 至 operation terminal”计算。`sum` 是所有 step 间隔合计；末 step 到 terminal 均为 0。

| Operation | 受理→首 step | materialize/prepare→下一 step | assemble/submit→下一 step | 末 step→terminal | 间隔合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t4 v1 Preview | 0.308 | materialize→assemble 9.246 | assemble→publish 8.744 | 0.000 | 18.299 |
| t4 v1 Submit | 6.961 | prepare→submit 6.400 | submit→await 9.751 | 0.000 | 23.112 |
| t4 v1 重传 Preview | 0.146 | materialize→assemble 1.007 | assemble→publish 9.360 | 0.000 | 10.513 |
| t4 v2 Preview | 4.916 | materialize→assemble 9.629 | assemble→publish 6.966 | 0.000 | 21.510 |
| t4 v2 Submit | 6.765 | prepare→submit 9.613 | submit→await 9.752 | 0.000 | 26.130 |
| t4 History | 0.601 | materialize→assemble 1.124 | assemble→publish 6.946 | 0.000 | 8.671 |

各 operation 的 step wall 与间隔合计和 DB operation wall 相符。V5 的长耗时不是 step 之间的空等：间隔最多 26.130 秒，Preview 的 685–773 秒缺口以及 History 的大部分耗时都发生在 step 内。

## Preview 与 S5 capability 分段对照

S5 capability 测量的是独立函数/能力边界，不是完整 worker step。下表将 S5 同档的 materialize 与 Preview capability 之和作为对照；“operation 超出”按 V5 DB wall 减去该和计算。

| 旅程 | S5 materialize capability | S5 Preview capability | S5 合计 | V5 operation wall | V5 超出 S5 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t4 v1 Preview | 724.955 | 176.255 | 901.210 | 1674.533 | 773.323 |
| t4 v1 重传 Preview | 725.375 | 40.952 | 766.327 | 1451.591 | 685.264 |
| t4 v2 Preview | 729.743 | 39.598 | 769.340 | 1467.357 | 698.016 |

分段与完整 step 的差值如下。它把缺口定位到哪个 step，但不把 step 内的调用进一步虚构成精确成本：

| 旅程 | materialize step 超出 S5 materialize | assemble step 超出 S5 Preview | publish step | step 间隔 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t4 v1 Preview | 206.479 | 547.459 | 1.086 | 18.299 | 773.323 |
| t4 v1 重传 Preview | 574.226 | 99.757 | 0.768 | 10.513 | 685.264 |
| t4 v2 Preview | 571.267 | 104.424 | 0.815 | 21.510 | 698.016 |

**v1 Preview 缺口主要落在 `assemble_preview`（约 547 秒）与完整 `materialize_inputs`（约 206 秒），不是等待或 `publish_preview`。** 生产 `assemble_preview` 包含 pair pipeline、bundle 组装、ready closure、state artifact/checkpoint 序列化与引用 pin。Journey 汇总记录该次 Preview 的 `pair_count=1`，因此不能把缺口归因于额外 pair。S5 的 capability runner 测量 planning/comparison/risk/surface/pair artifact 边界，没有调用完整 `assemble_bundle`。生产 bundle assembler 会遍历 closure：从 ArtifactStore 读取并校验 source artifact、重写引用、写入并再次校验生成的 artifacts，再写 closure/manifest；这是数百秒 step 内缺口的强候选（尤其完整表 artifact closure），但本次没有给这些子阶段计时，不能把候选写成实测结论。checkpoint 序列化与 pin 同样在该 step 内，独立耗时未知。

**重传与 v2 成本没有随变化量下降，主要因为变化量只约束比较结果，不约束当前输入的全量物化。** 三次均重新经过对全量上传包的 `materialize_inputs`；S5 计时仍显示约 725–730 秒。重传 changed=0、v2 changed=26，但完整 V5 materialize step 分别为 1299.601 秒和 1301.010 秒；而 assemble 分别为 140.710 秒和 144.022 秒。S5 单独测得的 repeat/v2 pair capability 约 40 秒，完整 step 仍多约 100–104 秒。t4 有 320 张 source table、312 张 canonical table；完整操作的全量 scan/解析、投影与 artifact/checkpoint 路径不会因为只有 0 或 26 张表有差异而自动跳过。

重传/v2 的完整 materialize 比首个 v1 Preview 多约 368–370 秒，S5 单独 materialize 测量没有出现同样增量；t4 已提交 baseline 的 S5 Arrow 读取为约 51.8 秒，单凭这项读取不足以解释差值。step 记录只能定位到 `materialize_inputs`，不能再分解 worker 侧解析/投影、repository 读取及 artifact 写入/读回。首个 v1 的 `assemble_preview` 又比两次后续操作多约 580 秒，也超过单独 capability 计时可解释的范围。两项是本次最显著的未解释 step 内差异。

## Submit 与 History

### Submit 的约 100 秒

| Operation | S5 prepare adapter outer | V5 `prepare_import` step | V5 worker CPU（Journey step 采样） | step 比 S5 多 | worker CPU 比 S5 多 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t4 v1 Submit | 373.980 | 477.120 | 478.987 | 103.140 | 105.007 |
| t4 v2 Submit | 369.456 | 477.406 | 479.357 | 107.950 | 109.901 |

额外约 100–110 秒**定位在 `prepare_import`**。实际 worker CPU 与该 step wall 接近；`submit_import` 仅约 0.25 秒，`await_import_result` 虽有约 70–72 秒墙钟，却在 worker CPU 总量中没有显示为额外约 100 秒。S5 adapter outer 与实际 prepare step 的计时范围不同，漏掉的成本在这个 prepare 执行边界内；现有 step 记录不能进一步归因到 snapshot build、mutation planning/render、checkpoint 或 artifact 序列化中的某一项。

### History 的三个 step

| History step | V5 wall | V5 CPU 观测 | S5 capability 对照 |
| --- | ---: | ---: | ---: |
| `materialize_inputs` | 730.835 | worker 与 Repository Service 均有计算；全 History Journey step 记录 worker 758.784、RS 218.220 CPU 秒 | 无对应的完整 commit materialization capability |
| `assemble_comparison` | 144.443 | 包含 pair pipeline 与结果组装 | History planning/comparison/risk/surface/pair store 合计 38.989 秒 |
| `publish_result` | 0.030 | 近零 | 无显著差值 |
| step 间隔 | 8.671 | — | — |

因此，893 秒 S5 History 的主体不是比较 capability：V5 operation 为 883.980 秒，其中约 731 秒落在 `materialize_inputs`，约 144 秒落在 `assemble_comparison`，publish 约 0.03 秒。History handler 会逐一物化两个 distinct t4 commit，然后才运行 comparison；S5 的约 39 秒只覆盖比较/组装的一部分，没覆盖两份 commit 的冷读取、规范 materialization 与其 artifact/checkpoint 边界。assemble step 比 capability 多约 105 秒，细项仍未测量。

## py-spy

在首个 t4 v1 Preview 的 `materialize_inputs` step 期间从主机侧采样 60 秒；worker Python 为 3.14.6。0.4.0 无法识别 Python 3.14，随后使用增加 Python 3.14 支持的 [py-spy 0.4.2](https://github.com/benfred/py-spy/releases/tag/v0.4.2)。私有文本与 raw profile 分别留在节点日志目录；raw profile 不入 Git。

- inclusive 栈：`_materialize_all_sides` / `_materialize_uploaded_side` → `parse_sql` 约 97.6%；`parse_insert`、`_parse_value_tuples` 各约 75.7%，`_parse_tuple_values` 约 28.4%。这些 inclusive 百分比互相包含，不可相加。
- 热点栈摘要：`execute → _materialize_all_sides → _materialize_uploaded_side → parse_sql → parse_insert → _parse_value_tuples → take_balanced_paren`，约 16%。叶函数占比靠前的还有 `_scan_plain_statement` 15.3%、`parse_literal` 8.5%、`_parse_quoted_bytes` 6.8%、`_starts_with` 6.6%；`checkpoint` 约 6.6%。
- 采样输出 2488 samples、3546 errors，作为函数方向性证据而非精确 CPU profile。采样覆盖 materialize，不覆盖最大差值所在的首个 `assemble_preview`；因而不能据此声称已经分清其内部时间。

## 对 Phase 6 设计的含义与限制

- SQL parser、表物化/投影与摘要处于 worker 热路径，py-spy 与约 479/759 CPU 秒的 step 观测支持对该路径采用 Phase 6 已定的 Rust/table-parallel 优化方向。
- 表级摘要/存储与缓存、Preview 冻结规范表复用有机会跳过重传及 v2 的未变化表全量工作；但第一次冷读、artifact/checkpoint 发布、按规范顺序合并不会因此自动消失。需要分别测冷/热与 I/O，不把 Rust CPU 加速外推到这些成本。
- D10 的变化表跳过与阈值式行级修改减少 Submit 的 Dolt 写入；它不直接消除当前约 477 秒的 prepare step。该 prepare 的约 100 秒 capability 差额需要在 Phase 6 新实现/测量后复核。
- History 的 manifest 过滤和比较结果缓存可压低重读/重复比较；首次冷 History 仍需读取两个 commit。DC38 的 H2 冷读门槛不能由 S5 的 39 秒 comparison 单独证明，V7 的并发 Arrow 冷读结果仍是必要证据。
- 本次 History 前同一 stack 已完成 v1/v2 Submit 及 commit 读取，不是受控冷启动；其 730.835 秒物化耗时是当前顺序旅程的实测值，不能代替 DC38 H2 的两节点冷读证据。
- 当前 step 记录已排除长时间 step 间等待，但不能区分 step 内 pair pipeline、bundle、artifact I/O、checkpoint 与序列化。若 Phase 6 决策需要这些子项的精确预算，就必须由 owner 决定是否增加产品插桩；本 V5 未增加任何插桩。
- S5 operation terminal 与本次 DB 创建/完成边界存在约 1–12 秒差异；本次 Journey log 的 operation wall 与 DB wall 也相差约 1–3 秒。所有 operation 均成功、无 `MANUAL_RECOVERY_REQUIRED`；未见数据/断言异常。上述边界和单次运行差异不足以解释 100–700 秒量级的 step 内剩余。
