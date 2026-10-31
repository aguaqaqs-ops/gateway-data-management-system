# Phase 6 重建对照基准：正式测量前放行检查

- 结论：**放行。** 接手核对、t1 预热、运行计划与耗时估计均满足条件，正式测量可以开始。第 3 节的三项在测量中补齐，不需要再停下来等待放行。
- 日期：2026-10-31。
- 对象：`p6-baseline` handoff 提交 `7c518e9212`；被测工具 HEAD `1cc780afa8`（合并 `p6-s1c-exit` 的 `2d4f6acf86` 之上的 handoff 提交）；实施会话 `p6-baseline-measure`。
- 安排（owner 2026-10-31）：正式测量前的放行检查由本会话（S2a 审核会话）完成；放行后实施者连续推进，只在停止条件出现时交 owner；全部完成后由新开的基准审核对话终审。DC70 第 5 项“两条线分开审核”的本意由终审保持。

## 1. 核对结果

审核者在 ct108 上核对了以下各项的 SHA256 与结论。

| 项 | 证据 | 结果 |
| --- | --- | --- |
| 产品 tree | `takeover-product-identity-20261031.json`（`962b906f…`） | 六个产品路径与 `p6-s1c-exit` 程序比对 MATCH |
| 输入 | 指定脚本 `check-baseline-inputs.py`（`afd4355c…`），日志 `ct108-baseline-input-check-20261031.log`（`d8d82fae…`） | `RESULT=MATCH`；真实 t1–t4 用 `/home/dev/gateway-real-dumps`，生成的 2×/W4 用 `input/1ed24d38f0`（76/638） |
| 镜像身份 | 对两个项目 tag 运行 `check-vprime-identity.py`，日志 `scenarios/ct108-t1warm-20261031/image-identity.log`（`a4cb21a5…`） | `RESULT=MATCH`，两个镜像的三项检查均通过 |
| t1 预热 | journey `t1-full.log`（`23f8a0a7…`）、state `evidence/p6bt1warm20261031a/state.json`（`9b4cae9a…`）、run（`e5552936…`） | exit 0，`failure_step` 为空，18/18 PASS，HEAD `1cc780afa8`；v1、v2 Submit 均 `COMPLETED_WITHIN_R5_WAIT_BUDGET`，日志中无人工恢复 |
| 节点 | postflight（`14e7705c…`）与审核者现场检查 | 无容器，占用标记已释放；预热卷 `p6bt1warm20261031a_*` 与 S1c 保留卷 `s1c-vprime-ebd1_*` 在位 |
| DC68 记录 | handoff | 两次自编输入脚本失败、一次 SHA 预检命令错误，以及 owner 授权的指定程序核对，均已记录；会话标签已更正 |

## 2. 运行计划

- 范围与 2026-10-29 授权一致：§16.3 的 13 个场景（含 W3/W4 的 FULL、W4 压力档、H1-FULL、H1-回填、H2 两节点与三节点）及其 S1–S4；t1–t4 完整旅程；DC63 子段；V5b 四段；正式 JSON record 与 SHA256；对照工具实测 replay；04 最终 runner。
- 方式符合 DC66：单次测量，偏离参考超过 10% 时补测，composite 按摘要复用，计时点前保存 checkpoint，失败从 checkpoint 续跑。
- 估计剩余 24–36 小时（计划约 30 小时），低于 48 小时停止阈值。以 S1c 三节点旅程 5 小时 23 分作为单个大场景的参照，区间合理。

## 3. 测量中补齐的三项

1. **补测基准要先写明。** 第一个正式场景开始前，在 handoff 中逐个场景写出“偏离超过 10% 时补测”所比较的参考证据（例如 t1–t4 用 S1b handoff 的完整旅程，2× t4 的 Submit 与 H2-三节点用 S1c DC69 取证运行 `b96fe8e4cc`，V5b 用 V5b 报告），没有参考的场景写“无参考，只记录”。补测判定由程序计算，不手工比较。
2. **正确性旁证。** 2× t4 的 v1、v2 Submit 与三节点 v3 的 Repository commit，与 ct108 保留卷 `s1c-vprime-ebd1_*` 中同一输入的结果做只读表哈希对照（同一产品、同一输入，应 631/631 一致）。只在卷副本上进行；结果写入 handoff，不一致即停止交 owner。
3. **04 最终 runner 的镜像。** backend/worker 按 DC67 补充第 2 项由开发节点从基准最终 HEAD 预构建整镜像再传到 04，用 config digest 与全部 DiffID 程序比对；V' 镜像只代表 ct108 测量中的产品，不用于这次 runner。04 上先获取节点占用标记（DC70 补充），S2a 也会使用 04。

## 4. 之后

实施者连续推进，只在停止条件出现时交 owner：产品失败、身份或缓存不符、对照不一致、剩余估计超过 48 小时、DC68 重做后再次失败。全部完成后，handoff 写完整，交新开的基准审核对话终审。
