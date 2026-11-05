# Phase 6 重建对照基准：W4 重复主键生成缺陷定向复核

- 结论：**修正审核通过，无阻塞项；可按原授权在新根重新生成一次，既定验收全部通过后继续 W4 场景。** 这是生成器克隆插入行未更新 DDL 主键的工具缺陷，属于 DC66 第 5 项；旧 `20261104a` 输入仍作废保留。测试通过不等于新 W4 输入已经接受，本报告不评价尚未运行的正式场景。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 代码：`a7a13d6987bf34e9979f4a0aba56db6b7e93f5f9`，父 `42f923457a828c3cef79092cddb1c2257012cb0c`；handoff：`2946521d91a5bfd33aba8d83cfbb3fdaf0389c4e`。
- 方法：在 clean detached worktree `/home/dev/gdds-p6-w4-review-2946521d` 只读审核；程序核对完整 HEAD、detached、clean，以及代码候选与 handoff 的 vnext tree 相同。05/ct108 仅读取已有日志与身份信息，不取占用、不写节点、不运行测试、生成器、Compose 或正式测量。临时分析程序通过 stdin 执行，未落盘。
- 依据：DC66 第 5 项、DC68、[KEY_EMPTY 停止复核](p6-baseline-stop-check-w4-key-empty.md) §4 的既定重新生成/全表验收安排，以及本次 handoff。

## 1. 失败与原因

生成运行 `bd9cfe33f37c1856fab18df85e3b14e4f29edbe7` 于 ct108 `2026-11-04T15:16:26Z–19:08:28Z` exit 1；日志起止 HEAD 相同，worktree status count 0。失败在 W4 10% 包的完整 Preview 前置验收，诊断为 `DUPLICATE_EFFECTIVE_KEY`。此处生成工具直接调用生产 business materialization 与 canonical projection；不能表述为“没有执行任何产品函数”，但并未启动 Compose/产品服务或正式场景。

只读重放返回 `EXPECTED_REJECTION`；已保存的 DDL/规则诊断与代码路径相符：`com_cfg`、`net_cfg`、`scdmod_para` 的 DDL 主键均为 `no`，规则比较键分别为 `index`、`(board, link_no)`、`ied_model`。三表规则比较键的重复计数均为 0；materializer 的 compare-key index 为 0 项，因此此路径按 DDL 主键检查。旧生成器只替换规则比较键，克隆行保留源行 `no`，导致前置验收出现重复有效键诊断。

根因证据支持工具缺陷分类；本次全表验收在正式场景前拦住了错误输入。没有通过替换 manifest、过滤诊断或修改产品放行错误包。失败根及日志保留，`input-summary.json` 未形成；不能把已生成部分包视为 INPUTS_READY。

## 2. 修正与覆盖

| 项目 | 核对结果 |
| --- | --- |
| 改动面 | 代码提交仅修改 synthetic load 工具及对应测试。AST 比较确认工具只改变 `_fresh_key_replacement`、`_make_w4`；`make_2x`、空表默认值、保护列选择与普通字段变异逻辑未改变。handoff 提交只改文档。 |
| 两套键 | 分别建立规则比较键与 DDL 主键的占用集合，去重相同键集合；插入行依次分配新键，后续替换同时检查已满足的键约束，最终将两套键加入占用集合。普通字段变异仍避开两套键和位置列。 |
| 有序表 | 先为插入行赋删除后连续位置，再处理键唯一性；独立主键集合按存活行重建，避免把已删除的尾部位置误判为占用。现有 ordered 10%/100% 用例继续检查连续 no、位移计数及真实 gid 位移。输出仍经 ordered projection 拒绝非法位置。 |
| 三表回归 | 单列、复合、字符串比较键三种参数化用例，分别核对比较键和主键无重复，再调用 `validate_full_preview_materialization`，要求 COMPLETE、零诊断且表进入 projected table names；不是仅以解析成功或模拟 materializer 替代。 |
| 既有覆盖 | 同键 10%/100% 插删改计数、特殊点保护、空表字符串键、ordered 连续位置及不可位移情况保留；2× unchanged-copy、包重打包和确定性相关用例保留。 |
| 输入接受屏障 | `p6_baseline_inputs` 对 2× v1/v2 先核对接受摘要并运行完整 Preview 验收；W4 10%/100% 同样跑全表 business materialization/canonical projection，再做各 census COMPLETE、重复 SQL/package SHA 与计数等检查，成功后才写 summary。此次未删除或收窄这些检查。 |

新增三表用例使用 10% 小规模输入，尚不证明真实 638 表及 W4 100% 新包已经成功；后者由已有全表生成验收承担，不追加真实场景或扩大授权。

## 3. 验证证据

下列文件实际字节已从节点读取、重算 SHA256 并程序比较，均与 handoff 一致。真实输入未输出行值。

| 节点 / 文件 | SHA256 |
| --- | --- |
| 05 `/home/dev/gdds-p6-logs/baseline/ct05-a7a13d6987/validation.log` | `2fb063097b4bc0d416b652ad8809ea01de9f11c0f05af791290d211572f80de0` |
| ct108 `/home/dev/gdds-p6-logs/baseline/scenarios/w4-generator-correction-20261104a/generation-run.log` | `617a0ba7a714d6bdcf3cea01e3a035deecd8e994e7b96f06762a47d021d0436b` |
| 同目录 `generation.log` | `661262386f443129563b833f975e8ecd864322ce3373114b147021d0a4d65672` |
| 同目录 `preview-diagnostic-replay.log` | `ce1fef2045807652f36bd647a17adfb51489f0ca1e79a0f09f3396c5d737d29d` |
| 同目录 `key-count-diagnostic.log` | `2bb11b2abfc46d6f544f5f58d1a32a2f31dc0296849f3594fe0e6e6351f0acc7` |
| 同目录 `primary-key-ddl-diagnostic.log` | `c116d396d1c7c3405620118355c99839018e4b85520ed20f7c54b068a1082809` |
| 同目录 `ruleset-key-path-diagnostic.log` | `4cb77a3015ef88ea88a1a41a1ff218d28c3f8763344891796a99e95141f8dab9` |

05 验证 hostname `gw-dms-test-05`，`20:23:26Z–20:24:21Z`，记录代码候选完整 HEAD、开始/结束 worktree status count 0、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、proxy unset；focused **18 passed**，五包 Ruff/mypy 全通过，exit 0。`git diff --check` 通过。

非阻塞记录精度：handoff 称 05“起止 HEAD 相同”，但该 validation.log 只打印了一次 `head=`，结束处记录的是 clean 计数；本次只读访问所列 focused worktree 已不存在，不能追认未记录的 end HEAD。本报告接受其为该已提交候选的 focused/static 验证，不把它提升为权威 runner 或阶段退出证据；后续日志显式记录 end HEAD，handoff 按现有日志准确表述即可，不要求为此重复本轮测试。

## 4. 可继续范围与镜像判定

按 handoff 使用新输出根 `/home/dev/gdds-p6-logs/baseline/input/w4-generator-correction-20261105a`、候选 `a7a13d6987` 的 clean CT108 worktree 重新生成一次，原 `20261104a` 保留作废。runbook 示例仍写旧 `20261104a`，实际展开命令须采用本次 handoff 的新根并确认不存在，不能照抄后覆盖旧证据；其余接受输入摘要、源包、S1 census 参数和检查不变。

新输入须重新通过已批准的 2× 身份、全表 Preview/canonical projection、全部 census COMPLETE、重复 SHA、逐表 W4 计数与 expected-input manifest 验收；满足后按原授权从头运行 W4/S4/H1、W4-FULL、W4-STRESS，不从含错误包的 checkpoint 续跑，不另设 owner 检查点。已完成且未受影响场景不重跑。再次出现生成/验收失败、身份或缓存不符、产品失败等仍按 DC66/DC68 与既有停止规则处置；剩余估计 `14–30 小时` 为实施方估计，超过 48 小时即停交 owner。

本轮无产品/镜像构建边界变化，不触发产品镜像重建。冻结产品仍为 S1c V′（`p6-s1c-exit`），最后接受的 backend/worker config digest 为 `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1`；正式启动前仍须程序核对其完整 config digest 与全部 DiffID。工具提交不作为新产品 image revision，本报告不声明当前候选容器门禁或 carried。基准终审、最终 runner 和 S2a exit 顺序不变；本次未推送、未办理 tag/合入/阶段 exit。
