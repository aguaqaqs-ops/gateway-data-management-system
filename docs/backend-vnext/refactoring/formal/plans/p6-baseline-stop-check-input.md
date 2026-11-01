# Phase 6 重建对照基准：full-v2 重跑输入错误的停止复核

- 结论：**测量输入选择错误，影响范围只有这一次重跑。** 已完成的 2× core、第一次 full-v2 与 t4 各次运行都消费了正确的输入。根因是工具没有把实际上传的 SourcePackage 绑定到场景要求的输入。修正工具后，用正确输入重跑 full-v2。
- 日期：2026-11-01。
- 对象：`p6-baseline` handoff 提交 `8b12d5b995`；工具 HEAD `60f8ec5801`；ct108 project `p6bw3fullretry20261101c`。
- 依据：DC66 第 5 项、DC68（含澄清）；[full-v2 停止复核](p6-baseline-stop-check-full-v2.md)。

## 1. 影响范围（审核者从各运行的 state 读取实际上传的包）

| 运行 | v1 | v2 | 结论 |
| --- | --- | --- | --- |
| 2× core `ct108-synthetic2x-core-retry-20261101` | `74974e5f…` | `121dc3b0…` | 正确（2×） |
| 第一次 full-v2 `ct108-synthetic2x-full-20261101` | `74974e5f…` | INITIAL `74974e5f…`、MODIFIED `121dc3b0…` | 正确（2×） |
| full-v2 重跑 `ct108-synthetic2x-full-retry-20261101` | `95408cc3…` | INITIAL `95408cc3…`、MODIFIED `5a7cd54d…` | **错误**（真实 t4） |
| t4 正式与两次补测 | `95408cc3…` | `5a7cd54d…` | 正确（真实 t4） |

`74974e5f…` 与 `121dc3b0…` 就是 ct108 输入目录 `input/1ed24d38f0/generated-packages/rd-t4-d-v{1,2}.tar.gz` 的 SHA256。重跑的 PASS 与计时只是真实 t4 在 FULL 模式下的诊断事实，不是 2× 结果。

## 2. 根因

- `real_dump_journey.py` 按文件名从 `GATEWAY_REAL_DUMP_ROOT` 下取包。真实 dumps 与生成的 2× 包同名（`rd-t4-d-v1.tar.gz`、`rd-t4-d-v2.tar.gz`），选哪一份完全由这个环境变量决定。`--synthetic-census` 只决定用哪份 census。
- 重跑启动时这个变量指向 `/home/dev/gateway-real-dumps`。两次 full-v2 的 launch log 都没有记录这个变量，事后只能从 state 推断。
- 运行前的 `check-baseline-inputs.py`（审核者编写）只核对两个目录里的文件，不核对旅程实际消费哪一份。这是审核方设计的缺口。
- 实施方在运行后用程序比较 state 中的 `source_artifacts` 发现了问题，按输入身份停止，处理正确。这是测量输入选择错误，被测对象已经运行，不适用 DC68 的自行重做。

## 3. 其他观察

1. 重跑的 launch log 显示 Python 环境来自另一个 worktree（`…-bb348/vnext/backend/.venv`），而工具源码来自 `…-60f8ec5801`。产品在 V′ 镜像中运行，不受影响，但正式运行应使用本 worktree 自己的环境，并记录在 launch log 中。
2. 第一次失败运行的卷，按上一份复核的条件（重跑通过 `v2-repository-read`）删除了。当时这个条件默认输入正确。那三个卷只用于诊断，其 state 与日志仍在，删除没有造成证据损失。
3. 修正后的 FULL 模式核对（`52e9c14c04`）还没有在正确输入上运行过，下一次重跑同时验证它。

## 4. 处置建议

1. **工具修正**（DC66 第 5 项，只改 `vnext/backend/benchmarks/` 及其测试）：
   - **上传前绑定输入**：正式运行必须提供期望输入清单，内容是每个上传角色的 SHA256 与字节数。工具在启动服务前计算将要上传的每个包，与清单比较，不符即以 exit 非 0 退出，不启动 Compose。期望清单由程序从已接受的输入生成，例如扩展 `check-baseline-inputs.py`，为每个场景输出一份 JSON，不手抄。
   - **运行后复核**：把这次的 `compare-full-v2-input-provenance.py` 提交到 benchmarks，每个场景结束后从 state 的 `source_artifacts` 与期望清单比较，作为结果接受的必要条件。
   - **launch log 记录**：`GATEWAY_REAL_DUMP_ROOT`、census 路径、期望清单 SHA256、Python 解释器路径。
   - 在 05 运行 focused 测试与五包静态检查。
2. 输入不符在服务启动前就能发现，属于未触及被测对象的错误，按 DC68 可以修正后重做一次，并记录。
3. **用正确输入重跑 2× full-v2**：新 project 名，使用本 worktree 自己的环境；checkpoint 照上一份复核（至少 `v2-preview`、`v2-submit`、`v2-repository-read`、`history`）。
4. 错误输入运行的三个卷与 checkpoint 快照：在正确输入的重跑通过 `v2-repository-read` 并经运行后复核确认输入后删除，删除记入 handoff。它的 evidence 与日志保留。
5. **后续每个场景**都使用期望清单与运行后复核；已完成场景不需要重跑（第 1 节已核实输入）。剩余估计 23–36 小时，低于 48 小时阈值，可以继续。
6. 节点占用标记现在仍由 `p6-baseline-measure` 持有，继续使用即可。
