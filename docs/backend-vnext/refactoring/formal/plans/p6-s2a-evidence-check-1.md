# Phase 6 S2a 证据复核 1

- 结论：**证据不成立，需要一次测试修订后重取证。** 04 六包权威 runner exit 1，原因是候选删除旧 crate 时漏掉了 repository_service 中一项引用旧测试文件路径的测试。产品与镜像准备没有问题；实施方按停止规则停下，没有重跑、没有启动第 ④ 层差分，处理正确。
- 日期：2026-11-01。
- 对象：候选 `30d67140d4`；证据 handoff `cd97c5c71e`（`p6-s2a`，只改 `p6-s2a-handoff.md`）。
- 依据：DC64、DC67（含补充与澄清）、DC68（含澄清）、DC70 补充；[针对性复审 1](p6-s2a-rereview-1.md)。

## 1. 核对结果

| 项 | 证据 | 结果 |
| --- | --- | --- |
| dependency-base 传输 | 开发节点 `dependency-base-and-source-transfer-04-30d67140d4.log`（`b618846b…`） | 来源提交 `132fc621d5`，归档 SHA256 `3fd85920…` 传输前后一致；起止 `01:20:35Z–01:20:55Z`，exit 0 |
| 04 身份 | `dependency-base-identity-04-30d67140d4.log`（`dd3d401c…`），期望值 JSON（`b187cbf6…`）由归档机器生成 | `RESULT=MATCH`：config digest `sha256:b5b54224…`，19 个 DiffID 无错位 |
| 离线构建 | backend/worker（`f6b6d2f0…`）、RS（`fa64c27b…`）、client e2e（`b6cb4247…`） | 均 exit 0；backend/worker 用预置依赖与 `network=none`，未设 PREBUILT |
| 预检 | `offline-env-preflight-04-30d67140d4-retry2.log`（`a40c5d94…`） | exit 0；两次失败都是只读预检命令错误（PATH、selector 目录），发生在测试前、无副作用，按 DC68 澄清不计次数，失败日志保留 |
| runner | 04 `authoritative-runner-04-30d67140d4.log`（`7a2c5ba3…`，审核者在 04 重算一致） | hostname `gw-dms-test-04`；起止 HEAD 均为候选，worktree clean，六包全选；rust、shared_kernel、repository_contracts、repository_client、backend 通过；repository_service 并行批次 1 failed / 1742 passed / 1 skipped，串行批次 207 passed；`runner_exit=1` |
| 节点 | 审核者现场检查 | 04 无容器，占用标记已释放 |

## 2. 失败分析

失败用例 `repository_service/tests/test_uv_consume_script.py::test_uv_consume_allows_component_pytest_invocation_pattern` 断言 `vnext/rust/gateway-compute-python/tests/test_v1.py` 存在。S2a 按 kickoff §3 删除了旧 crate 的 Python 测试，这项测试没有随之处理。

- 这是候选自身的测试缺陷，不是环境、缓存或操作错误。被测对象已经运行，不适用 DC68 的重做；按 runner 停止规则处理。
- `uv-consume.sh` 中没有针对该组件的专门逻辑。该测试保护的是旧 `native_kernel_component.sh` 从 backend 目录对组件测试文件运行 pytest 的调用方式，这个脚本已在 S2a 删除。“允许对项目外的测试文件运行 pytest”这一通用行为由相邻的 `test_uv_consume_allows_pytest_external_test_path` 覆盖。
- 审核者在候选中重新扫描了已删除路径和名称：其余 `gateway-compute-python` 出现都是复用的新 adapter 名，陈旧引用只有这一处。runner 的其余全部用例通过。
- 审核疏漏：代码审核第 1 节写“代码中已无旧实现引用”，但该路径由多个片段拼接而成，文本扫描没有命中；两轮 focused 集合也都不含这个文件。今后有删除的阶段，focused 验证加跑 `repository_service -m unit`（约 12 秒）。

## 3. 处置建议

1. **修订**：实施方追加一个只改测试的提交，删除该测试（理由同第 2 节：所保护的调用方式随 `native_kernel_component.sh` 删除，通用行为已有 owner），不改写已有提交。在 05 运行 `test_uv_consume_script.py`、`repository_service -m unit`，以及 repository_service 的 ruff 和 mypy。
2. **审核方式**：改动只有一个测试删除，不单独安排复审；本会话在证据复核 2 中审查这个提交的 diff。如果复核不同意这项修订，证据需要重取。
3. **04 runner 在新候选上完整重跑六包**：本次 exit 1，不能作为任何包的沿用来源，AGENTS 要求来源 runner 整次 exit 0；本次各包用时合计约 22 分钟。dependency-base 已在 04 加载并校验，不再传输；重跑时记录本机 image ID 与本次加载一致即可。backend/worker、RS、client e2e 的构建与 runner 环境同本次。
4. **05 第 ④ 层差分在新候选上运行**，可以与 04 runner 并行（不同节点、互不依赖）。新候选的 Rust tree 与 `30d67140d4` 相同，差分仍以最终候选为准。
5. 节点占用标记与基准优先规则照旧；证据不经代理。

## 4. 之后

两项证据完成后交本会话做证据复核 2（含第 3 节第 2 项的 diff 审查）。S2a exit 仍在基准 exit 之后办理。
