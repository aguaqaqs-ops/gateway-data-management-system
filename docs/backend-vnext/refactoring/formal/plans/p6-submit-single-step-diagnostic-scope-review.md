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
