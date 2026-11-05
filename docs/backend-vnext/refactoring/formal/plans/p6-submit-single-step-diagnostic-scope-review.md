# W4 Submit：05 单步隔离诊断范围审核

结论：**方案实质边界通过，可继续已授权的 wrapper/observer 准备与 05 短 canary；尚不放行 CT108 复制、数据传输或真实 Submit POST。** 当前没有发现必须扩大产品改动或实验范围才能解决的设计冲突。具体实现、canary 及最小运输清单尚未交付，不能把范围通过当作启动条件已满足。本结论不是正式恢复、性能验收或基准 exit GO。

审核依据为设计会话 2026-11-05 的明确委托、`p6-baseline@647926e50ad8be02469953d0f0ab7a553594efc2` handoff，以及[停止复核与 B/B2 证据](p6-ready-capacity-resume-submit-stop-review.md)。本轮只读核对 handoff 和已有 e798 journey 接线，未运行测试、canary、测量或数据复制。工具准备由现有 `baseline_input_tools` 任务承担，原基准实施者只列运输清单；审核方不接管实施。

## 1. 诊断对象与可接受边界

- 只诊断 W4/S4/H1 的 `v2-submit`。来源为 `p6bw4s4h120261105b` 保存的 Submit 前 checkpoint，`completed_through=v2-preview`；不使用失败末态，不重跑 Preview。
- 05 使用 clean、已提交的 e798 产品及等价镜像，新 project、新 evidence、独立三卷副本及新幂等键；原 checkpoint、卷和证据保持不变。来源 run/state/log、manifest、checkpoint 与镜像关系沿用已有明确身份，并在运输清单中绑定；不因此重扫无关历史卷。
- 外置 wrapper 只发起一次 Submit，不自动重试。Submit 完成即停止，后续 repository-read/approve/archive/history 等旅程步骤零执行；不能依赖人工看到成功后停止终端。
- 原 lease 与 120s stall 判定保持不变。独立 watchdog 从真实 POST 开始计算，至多 45 分钟，不能被 HTTP 等待、业务线程或 observer 阻塞拖延；失败、预算到达或 observer 失效均收束目标项目并保存诊断与副本。
- POST 前在同 Python 3.14.6 与实际容器进程可观察边界上，以已知业务调用链 canary 证明进程外栈可读。只有工具退出 0、版本宣称支持或只有 kernel wait 栈，不足以证明有效观测；B2 中大量 invalid frame 的输出不能直接复用为该证明。
- 离散 dump 仅用于此次 05 诊断，不计为正式性能证据。记录采集起止、退出/超时及有效性；单次采集自身有界且不妨碍独立 watchdog。采集失败或只剩不可用输出不能静默继续真实操作。仅保存必要调用栈，不采 locals、业务行或凭据；不把 observer 可能造成的停顿误判为原故障。

以上是把现有授权落实为可检查行为，并非新增产品机制、扩大威胁模型或要求额外测试矩阵。使用现有标准观察工具；所需制品仍经 CT201 和获准 LAN 缓存到 05，不能让测试节点直接下载公网。

## 2. 尚待交付的具体材料

1. 固定的外置 wrapper/observer 脚本及摘要，说明真实 POST 的触发点、单次请求、成功/失败停止路径、watchdog 与 observer 的独立性。准备期 canary 不得触发真实 Submit。
2. 已授权短边界 canary 与有效业务栈 canary 的原始日志，足以核对“成功后没有后续步骤”和预算/观察器失败时停止。只验证这些实质边界，不要求为日志格式、命名或已通过的无关场景重跑。
3. 原实施者的最小运输清单：固定来源 checkpoint/run/state/log/manifest、需要的三卷快照与镜像、目标项目及副本位置、身份核对与保留安排。现阶段只准备清单，不复制 CT108 数据或启动真实 POST。

上述材料是已安排工作的待交付结果，不是新发现的产品缺陷。收到后立即按实际实现与证据审核；如果准备途中出现观察工具不支持目标解释器、无法获取有效栈或无法可靠限定单步等实质问题，再明确缺口和最小处置，不用扩大诊断掩盖。

## 3. 已有证据的解释与协作记录

最新 handoff 的 B2 `tick_max_gap=1.780999s` 应始终限定为最后已完成阶段记录，截断尾段没有全程最大值；这一表述补注不阻塞 wrapper/observer 准备。B2 的预算截断不是产品断言失败；现有样本没有定位真实租约失效根因，不能推导提高 lease/stall 阈值。

审核已向设计与原实施者发送上述边界。尝试向工具子任务通过 app-server 直接传递审点被工具拒绝（该入口不接受 multi-agent v2 子任务），已交设计经其既有 collaboration 通道转发；未新建任务或改变分工。

本报告基于 main `96cbf7c9b0` 新增，仅文档，不触发镜像重建，不宣称新的 image/container gate 通过，未推送、未打 tag。正式测量保持停止，既有 H2/H3 结论不变。

## 4. 外置工具前置复核与 F1 关闭（2026-11-05）

结论：**F1 修正版 wrapper、observer 与已有短 canary 前置通过；仍未放行 CT108 复制、传输或真实 Submit。** 本轮未发现其他阻塞工具准备的实质问题。最小运输清单与实际 launcher 的来源、项目、副本、选项和资源观察绑定仍待审核；本结论不替代它们。

材料位于 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/`，最终 wrapper 在其 `f1/` 子目录：

| 材料 | SHA256 |
| --- | --- |
| `f1/submit_only.py` | `8f4cb3fb99312261071263fc778712a2db56dbc37c475ccc89f374095625247f` |
| `f1/submit_observer.py`（与原候选相同） | `0577fb4973d05128d64940934abf7ee3345cae6ce6bc03522313f0fc23f68699` |
| `f1/focused.log` | `e0ee55229846c3c189e86cdc3b0bb208d4229e967686aa4bdd704717edb5439c` |
| `canary-backend-run.log` | `356b41ebe2462afa9cbab65afde2560e904acc377fcdce92682ff6e8e4d54f19` |
| `canary-backend-dump.txt` | `f73cf9d66f7b87ea33f3a49a7c301dd383aef5b65579c314e1056ebbfc4cf071` |
| `real-runner-fixed.log` | `270247662a0c20014f924d655b2e2b756da407d0e084ec15df633cec58db2728` |

审核读取了完整脚本、边界测试、相关日志及未改动 e798 的 step/Submit/teardown 接线；本地两份 SHA256SUMS 全部通过，并经 BatchMode SSH 只读核对 05 原件脚本和关键日志摘要一致。05 的 `f1/` 没有 SHA256SUMS 文件，改用逐文件摘要核对，没有补写远端文件。审核方未运行测试、canary、测量或复制数据。

**F1 原缺陷与最小修正。** 原 wrapper 仅在 `run_submit_only` 最外层 finally 关闭 observer；成功边界异常或业务失败须先穿过原 journey 的日志保存、Compose down（最长 600 秒）和证据收束。在该期间 worker 退出造成连续无效 dump，或原 POST deadline 到达，guardian 仍可能再次 SIGINT 父进程，打断清理。修正版在目标 step 的 try/finally 内先 close 并清空 observer，再传播成功边界或原错误；真实 POST 执行期间的独立 deadline 不变。05 新增一个短生命周期测试，成功/失败两分支均证明 close 早于 cleanup，worker 退出及清理跨过原截止时间不再触发信号，一次 POST、原失败传播和后续零执行保持；21:34:43Z exit 0，0.001 秒。该修改不涉及 dump/解析器/镜像，无需重跑 live canary 或扩大测试矩阵。

**已接受的工具行为。** wrapper 在原 runner 持久化成功步骤后主动停止，限制一次 Submit POST，拒绝后续步骤及非 get/post 客户端入口；原 lease/stall 判定不改。observer 在 POST 前验证固定二进制摘要和有效 worker Python 栈，独立进程在转发 POST 前 arm/ack，2700 秒截止；离散 dump 每 15 秒一次、单次 1 秒上限，连续两次无效即停止，轮询也检查 observer 可用性。成功后的正常清理不计入 POST 诊断预算。实际 live worker 仍须通过 `start()`，小 canary 的成功不能跳过这一检查。

**证据及限制。** Python-only canary 在同 backend/worker 镜像的 Python 3.14.6 上读到 `gateway_backend/.../_digest.py:40`、shared-kernel 调用链、active+gil 与 idle 两线程，无 invalid frame，dump 约 5.12 ms，start/arm/dump/close 集成通过。加载镜像的 config digest 和全部 15 个 RootFS DiffID 与既有 e798 approval 的 backend、worker 对象分别完全相等；未比较跨节点 inspect ID。native 模式先前因 UNW_EBADREG 失败，其日志保留，不能称 native 观测通过。Python 栈可以定位业务调用位置，不能独自证明 native GIL/GC 根因。

七个 fake 边界/独立 watchdog 检查在 `boundaries-fixed.log` 中通过；同一日志随后因 real-runner 测试 fake CPU 字典缺键而 exit 1，不能称整份日志成功。修正 fake 后 `real-runner-fixed.log` exit 0，证明未改动的 e798 runner 复用前一步、持久化目标步骤后停止。canary 早于父进程关系/EOF guard 调整，该调整由 focused 检查覆盖；不宣称最终所有字节均再次经过 live canary。F1 后只增加上述定向生命周期检查。

独立报告的 `SUBMIT_DIAGNOSTIC_COMPLETE` 只表示目标步骤完成；原 journey 因有意的 `DiagnosticComplete` 提前结束可记录 FAILED，不能改称完整旅程 PASS。后续结果审核仍须读取原证据中的 finalization errors、stack 停止与卷保留结果；工具前置通过不预先证明实际收束成功。05 postflight 记录 clean e798 与自有节点锁释放。此补充仅审核文档，不触发产品镜像重建，不新增正式门禁结果，不推送、不打 tag。
