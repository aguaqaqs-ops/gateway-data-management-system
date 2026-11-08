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

## 5. 运输与 launcher 候选静态审核（`p6-baseline@9da69886869cdf17f8cf3bbf91cf2892c9067955`）

**跨节点 checkpoint 复现方式可接受；这份候选尚不具备直接启动条件。** 以下裁定基于只读检查 e798 的原恢复路径，不要求产品补丁或改写来源 manifest。设计随后授权实施者仅补精确 metadata、05 资源/镜像/解释器身份，尚未授权数据复制或真实 POST。

1. 在 05 将已绑定且校验通过的三个 checkpoint 完整物化为源名 Docker 卷，再由原 resume 克隆独立诊断目标卷，符合此次隔离诊断。逐卷名称取自 checkpoint，保留源 project/逻辑卷 labels；任何已存在同名卷（包括没有 project label 的卷）或源 project 运行容器均停止，不覆盖、不接管。它们是 05 的 checkpoint 副本，不是 CT108 失败后 live volumes。原 `_clone_project_volumes` 对失败来源只检查源名集合，实际复制仍从 checkpoint 路径读取并核对原摘要，再核对目标卷摘要。因此不能用空占位卷代替完整物化，也无需改变产品恢复分支。源 run/state/log、checkpoint 与 manifest 的绝对路径和内容保持原样，在独立运输记录中注明来源节点与副本性质。
2. 原卷摘要包含路径、类型、权限、uid/gid、mtime_ns、大小及文件内容。运输和物化必须保留相关属性，最终以原校验结果为准，不能通过重写摘要消除差异。容量按 staging、源名副本、目标卷共 `3C`，加尚未落盘输入/cache/临时归档和余量计算；不假定旧的 211 GiB 足够，不重新扫描无关 live volumes。
3. prebuilt 恢复路径只检查 Repository Service 镜像存在，不会调用其自动 identity/build helper。启动前应固定 `GATEWAY_REPOSITORY_SERVICE_IMAGE`，以 e798 的 `vnext/repository_service/tests/support/build_context_digest.py identity` 重算 build-input/source-tree，与实际镜像标签核对。该 helper 不消费 dependency-base 镜像；若完整 RS 镜像已在本机且身份匹配、此次不构建，未使用的 dependency-base 缺失不另设阻塞。缺少所需完整镜像或身份不符则停止，另行安排获准预填充，不在此命令中隐式构建/下载。backend/worker 沿用第 4 节身份，在 05 增加新 project tag，原 tag 不改。
4. launcher 的 sampler 与 child 使用同一 manifest/census/evidence 变量，child 的字面解释器为指定 worktree 的绝对 `.venv/bin/python`；静态接线通过。`python -c` 后的 `--` 参数由 sampler 检查，child 实际用 options/env；目前两者值一致，不必为形式重写。实际 `.venv` 是否存在、是否为所需已预填充环境仍须核对，不能把前次借用其他 worktree 的 canary 解释器当成该路径已经可用。wrapper/observer 的 CT05 实际落点也须与命令一致并核对已接受摘要。
5. 来源选择固定为 b 的 `v2-submit` 前 checkpoint，普通 resume、e798、全 t4、单次新幂等键；未启用 capacity-fix/final-state/debug 路径。wrapper 仍将成功后的业务步骤截断。输入最小集可按清单搬运，不需复制其他变体；但唯一 composite cache entry 的存在和身份必须在调用前显式检查，因为原 journey 在条目缺失时会执行重新计算，不能靠其默认行为实现候选声明的“缺失即停止”。

**资源边界已由设计明确，具体接线待交付。** 依据 `main@5af1aca75d` 的[诊断设计](p6-submit-single-step-diagnostic-plan.md)，启动前 `MemAvailable ≥ 48 GiB`；相关文件系统可用空间覆盖尚需落盘的 `3C + I + R + 归档临时量 + 10 GiB`，已占空间不重复扣、跨文件系统分别核算。POST 执行期间每 5 秒轻量采样，worker RSS ≥ 40 GiB、宿主 MemAvailable < 8 GiB、相关数据文件系统 free < 10 GiB 或资源指标不可读，均停止此次诊断并记录原因，不能称为产品失败。沿用外置 observer 的中断与目标步骤结束即关闭机制，不改 Docker 配额、产品 timeout/lease/stall，不扫描文件树或新增测试矩阵。现有 `p6_baseline_resources` 只记录资源，不实现这些阈值；不能把使用 sampler 或 45 分钟 POST deadline 当作资源停止已接入。

目前待闭合的是上述轻量 metadata/本机身份与容量结果、资源停止最小补丁及最终 launcher 绑定；已通过的 canary 与一次 POST 边界不重开。此次只读静态审核没有访问 CT108、复制数据、运行测试或启动 Compose。

## 6. 资源守卫补丁复核（2026-11-05）

**资源守卫实现通过，启动绑定仍待完成。** 接受 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/resources/submit_observer.py`，SHA256 `4912e9542e11c273c0deee332c7d79aebf7ff81c40c8d54b3b94157cb370a662`；wrapper 保持第 4 节的 `8f4cb3fb…` 不变。审核读取完整改动及四个定向测试，本地 SHA256SUMS 全部通过，经只读 SSH 核对 05 原件脚本/测试/日志摘要相等。`focused.log` SHA256 `36c2535e82c3e977c82997e622e557a39f697ca1f12f40397ec43e9678f6a65f`，记录 clean e798、05、21:53:07Z、4 passed、0.005 秒、exit 0；postflight 记录自有锁释放。本审核没有运行测试。

补丁在既有独立 guardian 内增加 POST arm 后立即及每 5 秒的轻量资源读取，按第 5 节三个准确阈值或不可读停止，日志分类为 `diagnostic_resource_stop`，沿已有 SIGINT 收束。绑定 worker PID starttime 与宿主数据目录的 st_dev；没有新增扫描、哈希、Docker 配额或服务。stop 消息处理先于到期采样，F1 的目标 step finally 先 close 顺序保持。定向检查覆盖阈值边界、实际轻量读取及身份不符、不可读/超限停止、到期时先 close 并回收 dump；足以覆盖此次差异，不要求重跑已通过业务栈 canary。采样仍不是连续硬资源上限。

新 `observer_factory` 必须传入 `data_filesystem=`，为已存在的真实宿主数据文件系统目录；最终 launcher 须确认所有相关数据卷/路径位于该文件系统，不能随意传 scratch 或容器内路径。若实际跨文件系统，此单目录版本不足以覆盖全部路径，须先补齐对应范围。启动时 48 GiB 内存及按文件系统计算的空间门槛仍由 launcher 执行。第 5 节原命令尚未传新参数，不能原样运行；需绑定本节脚本实际路径/摘要及数据目录，再与运输/镜像/解释器/容量结果一起复核启动条件。

## 7. e798 本地环境准备与检查命令修正

此前 focused 实际借用 413832 worktree 的环境并显式插入 e798 源码路径，不能证明第 5 节所指定的 e798 本地 `.venv` 已可用。设计因此明确授权实施者在 05 自有占用下，通过已有缓存、受控 locked/offline 入口准备 clean e798 的本地 backend 环境，重装扩展并核对当前 Rust tree；不跑业务测试，缺缓存即停。以下文件均位于 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/`。

| 执行记录 | SHA256 | 实际结果 |
| --- | --- | --- |
| `environment-sync-ct05-e798.log` | `b79bcffe273791f07b2ebefa6180f64881b801a6ff8101b61fbcbfe8069d5b4c` | 22:08:19Z，仓库根目录未命中 Rust selector，exit 1，未调用同步 |
| `environment-sync-ct05-e798-retry.log` | `34849b7ef594fc4dc63cb92159c02c9016a31c96ff024a5fa81af4f07f78dc87` | 22:09:34Z，工具链检查正确；uv 因重复 `--locked` 在参数解析阶段 exit 2，未进入依赖同步 |
| `environment-sync-ct05-e798-final.log` | `057490a18069eb5863c69c7eed7ef10c76562cb3d4ba5fb105119dae70711369` | 22:11:04–22:11:32Z，同步/扩展构建成功，随后导入检查错误导致整体 exit 1 |

第三次在“先交完整命令”提醒到达前已启动。审核没有重复执行或中断回滚；读取最终日志确认创建的是 `/home/dev/gdds-prepare-import-e798-05/vnext/backend/.venv`，Python 3.14.6，workspace 包来源均为 e798，官方扩展检查 expected/installed 均为 `58436908aee9dd449f4d3e0542a6a8c1920b6d5e`。失败点是后续 probe 误用分发包名称 `gateway_compute_python`，实际导入模块为 `gateway_compute.gateway_compute`。不能将整个 enclosing command 宣称 exit 0，也不需因该导入错误重新同步或编译。审核另外只读 SSH 确认 clean e798、本地解释器存在、节点标记已释放。

实施者随后落盘的实际完整命令 `environment-sync-ct05-e798-attempt3.remote.sh`，SHA256 `a9e73d53ea31d9d8cbda6aa6fc3a39913f7a066c8377b4259f1cd100abfa9a39`，已静态核对：Rust 检查 cwd 为 `vnext/rust`，PATH 以 `/home/dev/.cargo/bin` 开头，未设置 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME；受控 wrapper 自动加 locked，调用只传 `sync --offline --reinstall-package gateway-compute-python`；UV/Cargo offline、当前 Rust tree 与 worktree 外 target 均保持。此为事后命令复核，不补称事前审核通过。

修正后的只读 probe `environment-import-probe-corrected.py`，SHA256 `13d7095d014211cfaf718031fe1741ae35c72734573b4d8c3cdf805d7d130edd`，静态审核通过。已按设计 DC80 最小工具修正通知实施者：在自有 05 占用下，仅以 e798 的绝对 `.venv/bin/python -I -B <probe绝对路径>` 执行一次，核对源码导入归属、native build-input、已审核 wrapper/observer 的路径与摘要；小工具文件落点须与 probe 一致。三份原日志保留，不再把连续错误描述成 DC68 的一次重试。不重新 sync/编译，不增加业务测试/canary，不搬 CT108 数据，不启动 Compose/POST。probe 结果与其余启动材料仍待接续审核。

## 8. 本地环境、精确清单与容量证据闭项

第 7 节获准 probe 在 05 于 22:20:03Z exit 0。`environment-import-probe-05.log` SHA256 `42b276e12cb3623df24970860b106795b5a252f51ab16f42142a4a6a243bbc65`，审核核对文件摘要及完整输出：字面解释器为 e798 本地 `.venv/bin/python`；两个 benchmarks 与四个 Python 源码包均从该 worktree 导入；native 位于本地 `.venv`，build-input 为当前 Rust tree；外置 wrapper、资源 observer 的路径、摘要与必填 `data_filesystem` 签名正确。起止 HEAD 均 e798、tracked clean。此前工具小文件缺失已由此次成功导入闭合；无需再同步环境或重复 canary。

同目录 `ct108-source-metadata-confirmed.json` 实际为 JSON 首行加结果行的取证日志，SHA256 `9f28af49357b5d9e83be5174c2d5fd7d0d74a93b66d44e3ba673a6b610b3a866`；`ct05-four-way-post-env.log` SHA256 `5204c85922ef0b4c09c08ae4c50c60de9317b786b1b04aeff988ab8f852e1950`。审核核对本地完整日志与摘要，没有重扫/重哈希 CT108 快照或业务输入。精确 metadata 给出：

- checkpoint 为 b 的 Submit 前快照，completed_through=v2-preview，三卷后缀依次为 `backend-artifacts`、`backend-control`、`repository-service-data`；内容 bytes 分别为 861,914,708、3,608,576、75,222,091，总 `C=940,745,375`。这些是原记录值，不代表运输后的内容校验已经完成。
- 必要输入及来源 run/state/log 合计 `I=38,874,215` bytes，唯一 composite cache entry 为 `496d3fefee7557f388434733449cd633590ebcff8aa854624ad9ea835ae3f1a0.json`，`R=689` bytes；审核按源码算法重算 cache key 与所列两包/比较器摘要匹配。流式运输不额外落 tar 归档时，`3C+I+R+10GiB=13,598,529,269` bytes，与报告一致。
- 05 的 22:17:55Z 只读记录为 MemAvailable 65,985,872 KiB、可用空间 224,879,476,736 bytes；日志/TMPDIR/Docker 根/volumes 均 st_dev 64526，可用一个真实宿主目录覆盖当前相关数据文件系统。启动前仍按既定门槛检查实时值，不需重新测量或扫描文件树。
- RS 期望/实际标签相等：build-input `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`；本机 image ID 为 `sha256:642b9ff31c6b862266087cfc1b6033ff85439242fc3727860da0c06725191b56`，仅用于本机绑定，不是跨节点比较。最终命令仍须明确采用该已检查镜像的实际 tag。各来源/输入目标路径记录为 ABSENT，尚未运输；卷名碰撞仍由运输前精确检查拒绝。

metadata 日志的 `inputs.manifest.expected_sha256` 错填为 accepted document 摘要 `6b63cf…`；该 manifest 的 `actual_sha256=4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7` 与先前固定值一致。已要求最终运输清单使用正确固定值并标明展示错误，原日志保留；不把该错误列当运输期望值，不为修正文案重读/重哈希 CT108。

这些证据关闭环境准备与清单/容量不明确项，不新增测试要求。尚待交付的是具体运输/完整源名卷物化与新版 launcher 命令，绑定第 6 节 observer、宿主数据目录、固定 RS tag、实时门槛和既定失败停止；`9da69886` 中的旧命令不能代替该最终版本。可按先运输/物化校验、后一次 POST 的边界接续审核，无需重开已通过前置。

## 9. 首批运输工具静态审核与 F2

已先行审核 `diagnostic_preflight.py`（SHA256 `eef3e6babecc46318a5e4bb2cde46ed38571704f22670ea2a25eba031f122d79`）及 `materialize_ct05.py`（SHA256 `3a919f94294c6270d4514ca14b7a0b24fe477ca7593b85b15bbac26a77448644`），均在上述外部证据目录；不等待完整 handoff 排版。审核只读脚本及对应 e798 helper，没有执行脚本或测试。

**F2：镜像 tar 读取依赖成员顺序，会拒绝现有合法镜像。** preflight 的 `verify_image_archive_identity` 用 `tarfile` 流式 `r|` 读取，仅在已见 `manifest.json` 后才把其 Config 路径加入接收集合；位于 manifest 之前的 config 被跳过，之后报 requested tag/config 缺失。只读既有 `backend-worker-p6bw4s4h120261105b.tar` 的 header 元数据确认：config header offset 为 368,442,880，manifest 为 397,079,552，实际就是 config 在前。该核对没有提取镜像或重算归档 SHA。最小修复是复用 e798 已有 journey 镜像 metadata/config-digest 读取 helper，再比较固定 config digest 和全部 DiffID，删除此次新建的顺序敏感解析器；不需镜像重建、业务测试或新的解析框架。已即时通知实施者及设计，由既有任务修正后交摘要复核。

两脚本其余主体暂未发现阻塞问题：固定 source/input/checkpoint 常量与第 8 节一致，manifest 期望 SHA 已正确使用 `4c5638…`；先核 staging 文件/目录摘要，拒绝 project-label 卷和无 label 的精确同名卷，移动到原绝对路径后保留 manifest，按新建源名卷 labels、空卷、同文件系统检查再 `cp -a`，复制后重算原 digest，失败保存结果且不删除副本。该物化脚本本身不启动 Compose/Submit。

物化脚本依赖尚待交付的外层 transport wrapper：必须在任何复制/移动前取得 05 自有占用并执行实时资源门槛、精确目标路径/名称检查，不能用物化末尾的容量检查替代启动前检查。`ct05-tools/diagnostic_preflight.py` 的实际落点/摘要也须由该 wrapper 固定。本轮接受物化主体的静态方向，不等于外层运输已放行；F2 影响后续镜像校验，修复交回即可定向闭项，不重开此前前置。

**F2 已关闭。** 随后交付的 `diagnostic_preflight.py` SHA256 `364ec3c5ca4885820c796661782bdcc56edc6cf79e50ba8e347e05c9a221a93d` 已删除自写 tar 流解析，改用 `verify_image_project_identity(journey, project, expected_path=...)` 调用 e798 的 `_compose_backend_worker_image_metadata`，比较固定 config digest 与全部 15 个 DiffID，不比较 image ID。静态复核通过，无需镜像重建或重复业务测试；materializer 摘要不变。已通知两实施方更新调用接口及固定摘要，不能继续调用已删除的 `verify_image_archive_identity`。外层 transport/launcher 仍单独审核，闭合 F2 不自动放行执行。

## 10. 单步 launcher 独立静态审核

已读取 `launcher-candidate/launch.sh`（SHA256 `fb043c7ba9a6a52dc70f4f9732a5fae3d71f443ed11e4e29852b616e6e90af04`）、`submit_diagnostic_launcher.py`（SHA256 `a6574d38c2ad28cb204fe3d3ed29a49093f64234435d1a5d423437f284a6f0a6`）及 README（SHA256 `288b5959a038c4c1742d203d9a438fd433456ffdbb1c508bd26f89f20396b75c`）。**单步行为和收束接线静态通过；helper 最终版本/路径需与运输任务对齐后固定。** 没有执行候选、测试、Compose 或 POST。

脚本拒绝既有输出目录，校验自有诊断 owner 的 session/purpose/token；不获取或释放节点锁，由外层实施者按 README 原子 mkdir 并在运行资源全部结束后仅释放自身 token。它固定 clean e798、本地 `.venv`、native tree、F1 wrapper/资源 observer/py-spy 摘要、普通 resume 选项与 RS tag；sampler 与 child 的 manifest/census/evidence 参数精确一致，仅调用一次 sampler，无自动重试。物化 MATCH 后仍核对来源 checkpoint/源名卷、输入/cache、镜像；剩余空间按目标卷 `C+10GiB`，内存仍 48GiB。目标服务启动后、POST 前只核目标卷完整名称/labels及 mountpoint st_dev，不错误地把已运行卷内容要求为原 checkpoint 摘要；随后接入已接受 observer。F1 的目标步骤结束前关闭 guardian 保持，原 journey 保存与清理路径不改。现有目标镜像仅在缺失时从已验证源 tag 增加新 tag，已有不匹配镜像停止。

两任务在审核期间仍修改候选：launcher 固定 helper `364ec3…` 于 `ct05-tools-20261105a/`，运输侧新 helper 增加锁/运输前置后摘要已变化，而 materializer 仍引用 `ct05-tools/`。已通知统一一个最终版本目录及摘要，并更新 shell 对入口文件的 pin；不能把旧 launcher 搭配新 helper 直接执行。另建议 shell 保留既有 `umask 077`，确保输出日志私有。以上是最终接线收敛，不要求新测试矩阵或重新验证已通过 canary。运输外层仍单独审核，不因 launcher 静态通过自动获得执行许可。

**最终 helper 扩展已静态通过。** 固定唯一 05 落点为 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/ct05-tools/`；helper SHA256 `02985d19c373980ab411242c17a019a3d7ce165bfa413c068b331f8d97440e22`，materializer SHA256 `69fcaafcaea37c6ae785e8660c444d1a6205444195de7c04747fe04a2c6192ec`。新增 `require_node_lock(token,purpose)` 和 `preflight_transport(journey)` 核对运输占用、解释器/HEAD、固定工具/expected image 摘要、源/目标精确路径与卷名空闲、同文件系统、启动容量以及已有镜像身份；materializer 入口新增同 token/purpose 校验。F2 修复及原来源校验保持，未调用 Compose、同步或业务测试。已通知 launcher 同步新 pin/路径。外层 transport 仍须在流复制前调用该 preflight，持续持有同一锁到物化收束；helper 本身通过不替代外层命令审核。

**launcher 最终接线已闭合。** 当前固定 `launch.sh` SHA256 `e0075f7253b7b8b84ba3e633dd931226080eb6d14bb946c9d4bb31ea3de554c6`、Python 入口 SHA256 `17ba08615f8dc5181ca7677fdf9207fa0d576258dd63a3740046fb1360185c2c`、README SHA256 `37eca1f3a053c77df6f069054c471c6794fe89d88744b4ee6e985dcfbcab572c`，接口文件 SHA256 `fdff3ed4fe60c2bddc4119d9673ef57a0566a502dc702f55ed30c3b3efcb49ee`。本轮将 helper 路径/pin、shell 入口 pin 及 `umask 077` 反向替换后，可精确恢复前次两个脚本的完整 SHA，确认没有额外算法变化。唯一落点及新 helper 摘要已一致，静态审核通过，不需要重测；旧 `fb043c…/a6574d…` 不再作为启动候选。实际 POST 仍以运输/物化结果及既定启动前提通过为前置，尚未执行。

## 11. 外层运输候选的 F3/F4（尚不执行）

按设计委托，直接审核已落盘的 `transport_source_to_ct05.py`，固定 SHA256 `ba1fdd78941df0f6a65e670598c2c2003c57a3fb98d1e6a5bd2464094f2f435c`，不等待 handoff 排版。当前有两个需修正的实质项，已直接通知原实施者及设计；未执行运输。

**F3：metadata 读取和释放命令存在确定性错误。** `build_transfer_plan` 对整份 `ct108-source-metadata-confirmed.json` 使用 `json.loads`，但第 8 节已确认该文件是 JSON 首行加 RESULT/ssh_exit 行，必然报 extra data。随后 `accepted_paths` 循环还从 `inputs` 下读取不存在的 run/state/launch/cache/accepted 字段；实际 accepted 为 `accepted_document`，cache 在 `cache.matches`，源 run/state/log 使用既定固定路径即可。应按已保存日志的实际结构读取、保持固定来源摘要和路径，不重新取证。`release_lock` 的 raw Python 代码使用双反斜线 n，匹配的是字面反斜线而非 owner 文件的换行；远端断言失败还因未检查 returncode 被吞掉。须修正字符串并明确检查释放结果，不能将空 stdout 记作成功释放。

**F4：远端状态未知时不得释放占用。** `main` 在 finally 无条件释放锁，但流传输或远端 materializer 超时/控制端中断时，本地 SSH 结束不能证明远端复制/物化已退出。最小修正为不确定收束的失败保留自身 owner，记录需检查原因，确认本次活动停止后再释放；成功路径检查远端退出及释放标志。不需要新增监控框架或故障矩阵。执行入口还应固定校验已审核 helper/materializer/expected-image 的摘要，而非仅复制后动态记录当时内容；可由脚本常量或已审调用命令落实。

其余运输方向符合已批准范围：精确列举三份 checkpoint 及必要输入/元数据/cache，PAX 流经局域网到新 staging，不读取失败后的 live volumes、不落完整 tar 临时归档；计划在复制前检查 05 锁/容量/路径、再使用已审核物化入口，原来源保持不改，失败保留副本。F3/F4 修正后只复核对应差异，不重开 helper、launcher 或 canary。

## 12. F3/F4 关闭与一次运输/物化 GO

**明确 GO：允许原实施者执行一次固定 CT108 → CT05 运输及 source-name checkpoint 物化；不包含 Compose 或真实 Submit。** 已将结论直接通知原实施者与设计，不需要再次等待 owner 确认。运行入口为 CT201 上的 `python3 -I -B /home/dev/gdds-p6-logs/submit-diag-preflight-20261105/transport_source_to_ct05.py`，执行前核对以下固定摘要，不使用仍在修改的字节：

| 文件 | SHA256 |
| --- | --- |
| `transport_source_to_ct05.py` | `f435f1f623e7992bbe7c66e4579d5971d29af916098dee6f08631fc10728c329` |
| `diagnostic_preflight.py` | `762b640b4cdaf9f89390834c1b1fcd793dc81f32696ed2ed1bbb9e5b6c328dec` |
| `materialize_ct05.py` | `69fcaafcaea37c6ae785e8660c444d1a6205444195de7c04747fe04a2c6192ec` |
| `expected-image.json` | `09b0924196c4cbefa2fd64e3cb284f999771f69c5dba7c08e6de68345f052e95` |

F3 已按原日志三行结构修正，并固定原 metadata 摘要 `9f28af49…`；输入路径使用真实字段，源 run/state/log 从固定路径列举，三个上传步骤与两份唯一 package 分别绑定。释放代码按真实 owner 行解析，检查准确 session/purpose/token、远端 returncode 与唯一 `NODE_LOCK_RELEASED` 输出，不再吞掉释放失败。F4 在流传输/物化启动前标记远端动作未确认；timeout、中断或 SSH 255 不会将其当作已收束，保留锁并记录 `PRESERVED_UNCERTAIN_REMOTE_ACTION`。成功释放未获确认时整体不能 exit 0。控制端管道收尾也改为有界 communicate，不增监控机制。

helper 的 `02985d… → 762b640b…` 差异已另外核对：source run 的 manifest 类型/path/census 绑定加强，保留卷名改为集合比较（重复已由原 source loader 拒绝）。将这些变更反向替换后可精确恢复旧摘要，确认没有其他逻辑改动；materializer 保持不变。执行前固定校验 helper/materializer/image，不再只作动态事后记录。审核未运行候选或业务测试，既有 canary、镜像与环境证据继续有效。

该 GO 的范围是脚本列明的 13 个源路径（含三个 checkpoint 目录）、固定新 staging、完整源名卷副本及原摘要核对；门槛/身份/路径/复制校验任一失败即停止，保留原始来源、已复制内容和日志，不自动重试。未知远端状态先保留自身占用，确认活动结束再处置；不得为了新开发会话提前释放占用。成功后提交 transport log、plan、materialize result 的完整结果与 SHA，以及节点锁/本次活动状态，再核实际 Submit 资格。DC81 允许后续开发不改变本次 W4/S4/H1 的冻结对象、停止条件或正式基准 exit 状态。

## 13. 运输结果闭合与一次 Submit 诊断 GO

**明确 GO：允许原实施者在 CT05 执行一次固定 e798 的 v2-submit 诊断。** 已直接通知原实施者及设计，不需再次等待 owner 确认。本审核只读核验材料，没有运行测试、重复扫描卷、启动 Compose 或 POST。

运输日志 `transport-source-to-ct05-20261105a.log` SHA256 为 `0e0ecdc1a14ccadae4bc3870abdff9fdaf6e496c4ac3a3612d30d89dc5eacc17`，计划 `transport-plan-20261105a.json` 为 `6ab845d97c3e58ab17cdc7c992790ce275a1384ca2e15780f8461d0cc5e4fef0`。日志记录控制端 23:09:45–23:10:18Z，13 项流式运输两端 exit 0，materializer exit 0、MATCH，随后 NODE_LOCK_RELEASED、整体 exit 0。CT05 结果中的本机结束时间为 23:10:19Z；保留各节点原时间，不将跨节点秒级差异推算为子段耗时。

审核经 BatchMode SSH 独立读取 CT05 `transport-materialize-result-20261105a.json` 并核对 SHA256 `cf8eb1c58a7944247b91f356b659042937150656740691d2c82035e1e1b3035a`，与控制端日志一致。source/state/input MATCH，census COMPLETE，固定 source/target project 与 e798 相符；checkpoint 总量 940,745,375 bytes，源卷和相关输入/cache/日志/TMPDIR 均 st_dev 64526。物化后 MemAvailable 67,311,659,008 bytes、可用空间 222,692,999,168 bytes，超过 48 GiB 与剩余 11,678,163,615 bytes 门槛；目标卷 ABSENT、相关运行容器 NONE。另只读确认当前 e798 worktree clean、节点锁不存在、Docker 无运行容器。启动时仍由既有 launcher 重核实时前提。

最终 `launcher-candidate/submit_diagnostic_launcher.py` SHA256 `544bfc0e4e53ad6ef16d90e1787e406985794bad2dd7c124c0b4231380db396e`，`launch.sh` SHA256 `692868fc9267050ba7a29db8f246cb92df990a3ed343b72a093b30470e6c4cc5`。分别反向替换唯一 helper pin 和入口 pin 后，精确恢复第 10 节的 `17ba0861…` 和 `e0075f72…` 完整摘要，确认没有其他脚本改动；helper 使用第 12 节的 `762b640b…`。README SHA256 `8aaf0000242db2da62f01afc643277ac574d442e07b55d96a42fe2f69ff64228`，interface SHA256 `2d9f422a12b1cf59b01369ada3f36f969c8fa5f2eafd20c19d4080964138977e`。

实施者报告此前只读回读命令因 shell 引用错误 exit 2，尚未运行远端 Python；失败日志 `postcheck-result-read-20261105a.failure.log` 及 SHA256 `5b94ce75df1523fa5f64db12e5727b830231cdb98c535728b4e91a22a98d6312` 已保留。修正回读没有重复物化；本审核独立 SSH 回读成功。该命令错误不改写运输成功证据，也不需新测试。

执行范围为 README 的外层自有节点锁、必要的已审小脚本同步及摘要核对，然后仅运行一次 `bash /home/dev/gdds-p6-logs/submit-diag-preflight-20261105/launcher-candidate/launch.sh`。冻结产品、普通 resume、单次 POST、有效业务栈前提、45 分钟预算、资源阈值及 F1 提前关闭 observer 均保持。任何前置或运行失败均停止、保留证据，不自动重试；确认自身容器、observer/guardian 和日志输出结束后才释放自身锁，保留所有数据卷与副本。后续交回实际 exit、独立诊断结果、原 journey/finalization、observer/资源日志、结束 HEAD、日志摘要和收束状态。此 GO 不表示 Submit 已成功、完整旅程 PASS、正式测量恢复或 benchmark exit。

## 14. 实际单次诊断失败分类（保持 STOP）

**本次确实执行了一次 Submit，并收到业务 operation 的 FAILED；不是成功后的 DiagnosticComplete 截断，也不是观察器或资源预算停止。** 第 13 节的一次执行授权已消耗，不授权自动重试或后续业务步骤。已通知设计与原实施者继续只读取证、保留卷及原始日志；当前材料不能认定纯工具问题，也不能将此次失败等同于 CT108 原 `lease_lost` 的根因。

审核经只读 SSH 读取 CT05 `/home/dev/gdds-p6-logs/baseline/scenarios/p6bws4submitdiag20261105a/` 的 launcher、launch、独立结果、run、observer 及 Compose 日志。launcher 于 23:19:34Z 开始，sampler 于 23:22:14.832Z exit 1，起止 HEAD 均 e798；preflight MATCH。独立结果 `post_count=1`、`submit_completed=false`、`status=STOPPED`、`exception_type=JourneyFailure`；Compose 中仅一次 Submit POST 于 23:20:35.466Z 返回 202，operation 为 `op-906304d3bc614a5f2abfafac`。23:22:10.158Z 轮询观察到 FAILED / STORAGE_PROJECTION_FAILED，v2-submit step 记录 97.363 秒，后续业务步骤未执行。该时间是失败路径的 step 时间，不是成功 Submit 性能数字。

实际 observer preflight 有效，7 次离散 dump 全部 exit 0、valid，无 timeout、stop 或资源指标不可读；采样 worker RSS 最大 132,300,800 bytes、宿主 MemAvailable 最低 66,681,286,656 bytes、数据文件系统 free 最低 221,584,683,008 bytes，均未越线。Compose 中有 9 次 heartbeat_succeeded，没有此次租约失效证据。最后一次栈仍在 `parent_catalog.py:31 get_table_names` → `submit_jobs.py:1607` 读取冻结父提交 catalog；该 adapter 会把 Repository 读取异常转换为投影失败诊断，但尚须完整 diagnostic.message 判断具体失败分支，不能仅凭约 97 秒猜测超时，更不能据此提高产品 timeout 重跑。

| CT05 证据（上述目录内） | SHA256 |
| --- | --- |
| `launcher.log` | `da4af0bacdcff7d210ba4c4d3bb024af12ef7ee2fbaac5722586c261faf4ee2a` |
| `launch.log` | `d06e79855d31087944ce0d0432f3efbf2b39d0c8af0a349315d904dcfcae213e` |
| `submit-diagnostic-result.json` | `33e41ac3004eaa43450b06b5219433e2922b1ffb96aa05a27a5fd04331f0f490` |
| `evidence/run.json` | `95ccbf7dcd5ab7646e140bef033397428b9c9173436b3a71dfd7ba92a4afd9ac` |
| `evidence/state.json` | `ca3a7d0ca6e85dca2bcb36ac97f6db249575eeaedfbf65a8b37126433b9b26c3` |
| `evidence/observer/observer-events.jsonl` | `13a118a423e1cb190e75cdf8628e6787694e57cc067666e1a09385c62294e116` |
| `compose/real-dump-t4-20261105T232210648526Z.compose.log` | `7be25ecd289e423b8b1359adc0de833efa155c3e6c18ce84bc4ebdd8fc40d16d` |

run 记录三个目标数据卷保留，无 retained-volume listing error；审核另外查询本项目全部状态容器与网络，均无残留。observer/guardian/runner 收束及自身 token 释放由原实施者完成并交回；不需为等待报告继续占用已确认空闲的节点。完整诊断消息与最终收束材料待接续补记，不启动服务取证、不重复运输或重开全套前置。

**精确消息的归因边界。** 设计随后转交消息 `frozen Repository parent catalog is unavailable`，由原实施者补原始提取记录。审核静态核对 e798：该消息来自 `parent_catalog.py` 对 `ValueError`、`RepositoryClientError`、`RepositoryProtocolError`、`httpx.HTTPError` 的统一捕获，能够覆盖入参校验、连接/传输、HTTP 和响应解析问题，单凭消息无法区分。返回 commit 与期望不符、重复表、catalog 与 canonical manifest 表集合不符分别使用其他消息；不应混成此次已证明的原因。worker 使用 settings 的 Repository URL/token/timeout 接线，catalog GET 使用客户端既有幂等重试；一次 Submit POST 不等于仅一次底层 GET。日志中已完成的 initial commit catalog 200 是另一项启动校验，不证明被冻结父提交 catalog 可读；卷摘要 MATCH 也只证明副本身份。此次证据支持失败位置，尚不支持超时、RS 内部故障或原 lease_lost 根因定论。按 DC80 当前仅由既有工具任务列最少诊断字段，原实施者核已保存日志的请求/status/code与父绑定摘要；没有额外 POST、起栈、扫卷或修改 timeout 的授权。

**冷 catalog 候选解释。** 既有工具任务提交静态线索后，审核另读 `accept_transaction.py`、RS `versioned_read/application.py`、`candidate_a/dolt_cli.py` 和 HTTP middleware。新 Submit POST 经 backend resolve main 冻结实际 expected commit，核对对象应取本次 attempt/payload 的 repository/expected commit/workspace/attempt 绑定，再与既有 v1 提交对应；不能拿 Preview 父引用代替。RS 进程内 catalog cache 不随三卷快照复制，cache loader 在锁外；冷 catalog 需要列出表并逐表读取 schema/COUNT。这使“冷读耗时、前次请求尚未完成时 GET 重试可能重复工作”成为合理候选，但未证明实际请求重叠、耗时或最终异常类型。原日志只取已有字段，middleware 的 request_id/duration/size/status 没有 route，不可独立绑定到冻结父请求；access log 的完成状态也不能补出未记录的开始时间、响应体或客户端异常 cause。若现有记录不足以区分，则明确证据缺口后再选最小下一步，不扩大验证矩阵、不先调超时或预热后重跑。

## 15. 父绑定闭项与冷 catalog 单请求方案方向

已读取 `parent-binding-compare-v1-corrected-20261105a.log`，SHA256 `febf9e14bdd5079cf3719046c6363a87005fa2d758a02e376ce74bfc4305a8b9`。该记录只对已捕获的 SQLite mode=ro 查询输出作比较，原后处理错误日志保留为 `parent-binding-compare-v1-postprocess-error-20261105a.log`、SHA256 `e6b3dbe93c94a468dda9c71a1f497058137817e887261586edfad1dee3271456`；不能把原误比 Preview/upload revision 的结果当最终结论。本次 attempt `sa-1657448dab865741d522572b` 与既有 v1 attempt 的 repository/workspace 匹配，冻结父 commit 与 v1 repository commit 均为 `c48dec7folb33jpli59sv533r2b36974`，repository 为 `c5a9df09-c169-4dec-a8c7-fedbb078bd56`。设计与实施者确认既有记录没有 worker HTTP 原始 cause，停止追加同类搜查。

**接受最小方案方向，尚未放行复制或运行。** 工具任务拟用独立项目 `p6catalogdiag20261105a`，仅从 05 已核、停止且无 writer 的源 RS 数据卷复制到新同 logical 卷（75,222,091 bytes），只起原 Compose 的 RS 服务，readyz 不预读 catalog。以已核原 worker 镜像在该项目网络内运行无产品卷的单次 `RepositoryClient.get_versioned_catalog`，绑定上述精确父引用，保留原 30 秒 HTTP timeout 与最多三次内部重试。冷仅指新 RS 进程缓存，OS 页缓存未知，不作冷磁盘性能测量。薄 hooks/parser finally 记录脱敏类型、status/error code、受限 request_id、耗时及实际读取大小，原 parser/重试不变，不预读或输出 body、业务行、token 或异常 details。

建议分段上限为复制 60 秒、健康等待 120 秒、client 容器启动起 180 秒、收束 90 秒。client 成功/失败或预算到期均须及时停止独立 RS；不能只结束客户端而让服务端请求继续运行。日志采集也有界，确认复制进程、两个自有容器及网络均收束后才释放自有锁，保留新卷和全部失败证据。具体脚本/命令及摘要待审核，重点核对观察逻辑不覆盖原始异常、headers 到达不冒充完整响应完成、无 response 时不编造状态/大小以及未知远端活动不提前释放锁。既有启动/资源门槛保持，不新增产品机制或验证矩阵。

## 16. 冷 catalog client 首版静态审核

读取外部 `cold-catalog-candidate/client.py`，SHA256 `82bce3a5adf025012eda13bdb864663426d0e93a2528fb0df580cad27c8fb034`，未执行。一次 `ObservedClient.get_versioned_catalog` 的固定引用正确；`super()._json_client()` 仅加事件 hooks，原 transport/env/timeout 保持。实际模块的 parser alias 由薄 finally 包装，原 parser 参数、返回、重抛和关闭语义保持，不预读 body；headers 与 parse-finished 分别记录，无 response 时不编造 HTTP 状态和大小。只输出受限错误类型/code/request_id、计时及数量，不输出异常文本、响应体或凭据。

**需最小修正：** 嵌套 `observed_parser` 的记录异常分支赋值 `logging_failed=True`，但该函数没有 `global logging_failed`，实际产生局部变量，可能漏报观测记录不完整。已通知设计转工具任务增加该声明并交新摘要，不要求新测试矩阵。最终 harness 还须把 `commit_matches=false` 或 `instrumentation_incomplete=true` 判为诊断不通过；client 当前 SUCCESS 仅表示 RepositoryClient 返回，不能单独当成父 catalog 语义通过。除该修正和外层判定接线外未发现阻塞 client 的实质项；完整执行 harness 仍待审核，本节不放行复制或运行。

**同节点镜像轻量核对可接受。** 冷 catalog 复用已在同一 CT05 验证的现存镜像，无需调用会重新 docker save 的 helper。worker 用第 14 节 CT05 诊断 run 的本机 image ID `sha256:26cc11f61544ae07b7006ccd6bf9270b52bc69338b245fc52972646dc08ac64c` 绑定当前源 tag，再核完整 RootFS DiffID；不能取 CT108 来源 run 的本机 ID。RS 用第 8 节 CT05 四向记录的本机 ID `sha256:642b9ff31c6b862266087cfc1b6033ff85439242fc3727860da0c06725191b56`，并核既定 build-input/source-tree 标签。此前 config digest 与全部 DiffID 的验证继续作为来源证据；本轮 ID 只用于同节点现存对象核对，不作为新跨节点等价证明。若本机对象已变或字段无既有记录，停止并说明，不能反填旧记录。具体 harness 须固定这些小记录/摘要并落实检查。

**client 修正已关闭。** 最终 client SHA256 `74bfa2b56eb7f4465caf7b5e69b7661e3494c74f99e87c0d275df963267ed864` 加入嵌套函数的 global 声明，并在返回 commit 不匹配或记录不完整时 exit 2。反向替换这两处后精确恢复首版 `82bce3a5…` 完整摘要，确认无额外改动。静态通过，无需新测试；controller 仍待固定版本及镜像身份小记录复核，尚未放行执行。

## 17. 最终冷 catalog 候选复核与单次 GO

**明确 GO：允许原实施者按最终 README 在 CT05 执行一次冷 catalog 诊断，包括单个既有源 RS 卷的本机复制、新 RS 进程及一次逻辑 GET。** 已直接通知原实施者及设计，无需再次等待 owner 确认。不包含 Submit、后续业务步骤或正式测量恢复。本审核未执行候选、测试、复制或启动服务。

最终文件位于 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/cold-catalog-candidate/`：

| 文件 | SHA256 |
| --- | --- |
| `client.py` | `74bfa2b56eb7f4465caf7b5e69b7661e3494c74f99e87c0d275df963267ed864` |
| `execute.py` | `f0ce6eaf972d8cca3083471e9053c3969b87b320703916c14b475a7bed957502` |
| `node-identity.json` | `7395cfaaccf99e6345bdc2291330ceb71bb7c7f7013ad02b20f5936e7162d21d` |
| `README.md` | `0dee1af755417bf2bc88d18cd43678206cfbd5dbb55e1336789270aaf93597ed` |

审核读取 `ct05-local-image-inspect-20261105a.log` 并核 SHA256 `a631ab29b22d7c4af840eb9ac9d4c7f5849d47b14a386130c46a76e08ba8f2c6`。worker 本机 ID 与已审 CT05 run 相同，全部 15 条 DiffID 与既有 loaded-image-identity 逐项相同；RS 本机 ID 与既有四向记录相同，28 条 DiffID 完整。`node-identity.json` 两对象的 ID/数组逐项精确来源于该日志，并固定其来源摘要、节点与产品 HEAD，没有编造缺失字段。原实施者 handoff 提交 `a96c1004fa83ccbe190390a99ed9a2dbc31be785` 已记录上述来源与 helper 绑定；本审核读取该文档增量，不将其作为正式测量恢复结论。

controller 已完整静态审核：先原子自取节点锁、检查 clean e798/节点空闲、已审文件摘要/实时资源/镜像身份/精确名称碰撞，再仅复制已验证源 RS 卷。原 Compose 只启动 RS，同 worker 镜像客户端没有产品卷，保持固定父引用、30 秒 timeout 和原内部最多三次尝试。成功必须同时满足 exit 0、唯一 SUCCESS、commit_matches=true、instrumentation_incomplete=false、尝试数 1–3。阶段预算与资源停止按第 15 节，退出先停止/杀掉 client 与 RS，再有界采集日志和移除本项目容器/网络，不删除数据卷；复制完成状态不确定或收束失败保留占用。最终 `execute.py` 反向去除身份 pin、两处 `--pull never` 与日志截断声明后，精确恢复已审核初稿 `456a0b1104718e93d4b591ff21b9d22ad8356a1a0780be50560705a70cbf269f`，没有其他逻辑变化。helper 仍固定 `762b640b…` 且只调用轻量同文件系统检查，不做镜像导出或重哈希卷。

执行前按 README 确认 BatchMode SSH，并经获准 LAN 同步这组固定小文件、核对摘要；controller 自取锁，不另建冲突的外层锁。使用 README 所列 e798 绝对解释器及隔离环境命令，仅执行一次。任何失败即停止、保留源卷/新卷/日志，不自动重跑；确认自身活动停止后才释放自身 token，未知状态保锁。交回完整 client/events、实际 exit、摘要与锁/收束状态；Docker 日志每容器仅末尾 2000 行，不能称全量。CATALOG_RETURNED 仅证明该次直接客户端请求返回，不证明原 Submit 成功或排除先前失败；OS 页缓存未重置，结果不作冷磁盘基准。

## 18. 冷 catalog 实际结果：响应头前 ReadTimeout，保持 STOP

审核在 2026-11-06 经只读 SSH 读取 CT05 `cold-catalog-run-20261105a/` 全部 events/client 与现存两份 Docker 日志，并逐项核对 SHA256SUMS 全过。节点记录执行于 2026-11-05 23:54:55–23:56:41Z：prepare 4.027 秒、RS healthy 6.206 秒、client 容器阶段 91.470 秒、cleanup 4.009 秒。控制端 `cold-catalog-controller-20261105a.log` SHA256 `7ba4a46248f6fad3f6de2d5ab6e1f322a05164763b49313d5073598a31db8d16` 记录实际 execute exit 1、起止 e798；外层 wrapper exit 0 仅表示取回结果成功。保留各节点原时间，不用控制端与节点约一秒偏差推算阶段耗时。

**已证明的症状：** 同 worker 镜像客户端对固定 repository/父 commit 发起一次逻辑 GET，记录三个 attempt_started，逻辑调用 90.453 秒后以 `ReadTimeout → ReadTimeout` cause chain 结束，instrumentation_incomplete=false。没有 response_headers 或 response_parse_finished，故本次最终错误发生在获得响应头之前，不是已收到正文后的 DTO/大小解析错误。前两次没有单独异常记录，只能确认发生过内部重试，不能称每次均已独立证明 ReadTimeout。未触发 180 秒外部预算、资源阈值或准备失败；结果为 DIAGNOSTIC_NOT_PASSED，不是完整 Submit、原 lease_lost 重现或根因定位完成。

| CT05 `cold-catalog-run-20261105a/` 证据 | SHA256 |
| --- | --- |
| `client.jsonl` | `e7a601e37f1e1f5510b079ebc6d7b866264d4fbde0b0bd8715c560f616940e47` |
| `events.jsonl` | `d15162a67a39e28acc83cac6be8a725edc09073143b2ef360527e320592decc3` |
| `p6catalogdiag20261105a-client.docker.log` | `31dd480849937209d94ed295ed39dd13c189954c2b69cce3175a8d0e6b61463a` |
| `p6catalogdiag20261105a-repository-service-1.docker.log` | `a5f5b70dd7e14ac5a00a3d1681ea1b83aecd4eb728972b2af374ca42e9457603` |

**新增工具取证缺口：Docker stderr 未保存。** 复核发现 `command(output=log)` 将 stdout 写目标文件，stderr 仍进入临时 capture；cleanup 忽略其返回 data，临时文件随即关闭。因此现存 Docker 日志除 tail 2000 限制外还缺 stderr，不应称为双流日志。RS 文件只有 19 条 readyz 200 access 记录，无 catalog 完成状态；不能据此认定服务端没有错误、未收到请求或没有执行 catalog。原实施者后处理 `cold-catalog-rs-log-readout-20261106a.log`（SHA256 `76acb0607042cf120ffba9c6e1d522b0331d4d5b776faf81bbcbaf551fa7d218`）同样仅能说明保存文件的内容。已通知设计与实施者补注，并要求后续最小工具修正保留两流；不以补日志为由自动重跑，也不抹掉有效的客户端症状证据。

events 确认 own_activity_confirmed_stopped=true、copy_uncertain=false、lock_released；审核另查节点标记不存在、本项目容器及网络均无残留。源卷、新卷和日志按既定边界保留。此次一次执行授权已消耗，保持 STOP。

现有源码给出的服务端候选路径为同步 catalog route → repository visibility/provider → commit_exists → catalog cache loader → 表清单与逐表 schema/COUNT → DTO 构造后返回；响应头前超时不能在这些阶段间定位，readyz 200 也不能替代该定位。未再搜索同类日志、扫描卷或运行请求。若继续诊断，最小候选是同一固定 GET 期间少量有界 RS Python 栈（无 locals/native），配合双流日志修正，先判断请求是否进入 catalog 以及所在阶段；仍须另审具体方案，不改 timeout、不预热、不恢复 Submit、不扩大矩阵。本节未授权下一次运行。

**handoff 记录完整性通过。** 定向读取原实施者仅文档提交 `6920325d55b46531a31f3d3f2d26b2a1a48476f2`，结果、起止 HEAD/节点时间、execute 与外层 exit 区别、候选/镜像/helper 摘要、客户端证据、stderr/tail 限制、收束和卷保留均与本节已核材料一致；未把最终异常扩称为每次 attempt 已证明的 cause，也未宣布原租约根因或正式恢复。另对照本地既有 transfer/check/postflight 日志及文档摘要一致，后验记录明确 marker ABSENT、四项 SHA 检查通过。无新增 finding，无新节点取证或请求；新 RS 栈候选另行审核。

## 19. 独立 RS 栈候选复核与单次 GO

**明确 GO：允许原实施者按固定新 README 在 CT05 执行一次 `p6catalogdiag20261106b` 冷 catalog + RS Python 栈诊断。** 已直接通知设计与原实施者，无需另等 owner 确认。范围仍是从原已核且无 writer 的 source RS 卷复制一个新卷、新 RS 进程、固定父提交的一次逻辑 GET；不包含 Submit、预热、改变产品 timeout、正式测量或其他场景。审核仅静态读取，未执行候选或测试。

新目录 `/home/dev/gdds-p6-logs/submit-diag-preflight-20261105/cold-catalog-stack-candidate/`：`execute.py` SHA256 `8ef5ee804e193ce32c3548eb2a2d448fcc7094f45b3cf310357eea3571b72b4d`，README SHA256 `7d3dd26f77db6b47ef3e607a3b59fb2b16c6215ab675b5850e4aad26fcb79616`；client `74bfa2b5…`、identity `7395cfaa…` 保持第 17 节完整摘要。已逐段核对相对 `f0ce6eaf…` 的完整差异，原候选与旧证据未改。输出固定为 `cold-catalog-stack-run-20261106b/`，新锁 token 为 `p6baseline-cold-catalog-stack-20261106b`。

RS Compose 有 `init: true`，新脚本只把 `.State.Pid` 作为 init 锚点，通过本容器 `docker top` 的 pid/ppid/comm 找唯一 Python，验证祖先链（允许 runuser 中间层）、PID namespace 和 init/Python starttime，并核容器 image identity。不是把 init 当解释器采样。每次采样前重核进程绑定；不读取 argv、业务数据或 secret 环境。RS 版本从已核镜像的 `PYTHON_VERSION` 白名单字段取出，并要求与 e798 RS Dockerfile 默认 3.14.6 及实际首份 dump 一致；缺失/不同为观测兼容性停止，不冒称 worker canary 已证明 RS 支持。

py-spy 沿用固定 `9b4d1f39b2a47ae44f4c6a46f615dcc0287d7755beba5065f32391951e07d594`，只用普通 `dump --pid`，不加 native/locals。从 client 启动起 10/40/70 秒至多三次异步 Popen；每份预算 1 秒，到期 kill，由现有循环回收，180 秒调用截止先检查。该预算受约 50ms 轮询及系统调度影响，不是硬实时精度承诺。首份没有所需 RS 业务帧/版本/PID/线程或有 invalid frame 即停止诊断并收束；之后失败明确记为缺口。客户端提前返回取消后续采样，活动采样先 kill/reap，再停止双方容器；采样回收未确认则保锁。无有效业务栈不能推导“未执行 catalog”或产品失败。

Docker log 采集已把 stdout/stderr 同写有界文件，修复第 18 节丢失 stderr 的问题，仍仅 tail 2000 且不称完整日志。原 60/120/180/90 秒阶段预算、资源门槛、一次 GET/原内部重试、`--pull never`、不删除卷和不确定时保锁均保持。README 完整说明停止分类及观测干扰；直接 GET 成功但未取得栈时仍标 stack_observation_incomplete，不作阶段耗时或原 lease 根因结论。

执行前按 README 做 BatchMode SSH 确认、获准 LAN 同步固定文件并核 SHA，使用既有 e798 绝对解释器及隔离环境；controller 自取锁，不叠加外层锁。任一失败即停，不自动重试；保留源卷、新卷、events/client、两份双流有界日志、最多三份栈与 SHA256SUMS。确认自身进程/容器/网络停止后才释放自身 token，未知状态保锁。交回实际 exit、原始结果及收束，不把单次诊断授权扩展成正式恢复。

## 20. RS 栈结果：冷 catalog 构建与重试重叠已定位

**此次诊断有效地缩小了问题范围：请求已进入 RS，冷 catalog 正等待逐表 schema/COUNT 的 Dolt 子进程，后续重试期间先前 catalog 处理仍未完成。** 不再重复相同诊断；正式测量保持 STOP。该结论不解释 CT108 原 Submit 的 lease_lost，也不证明单个 Dolt 调用为何慢。

审核只读取得 CT05 `cold-catalog-stack-run-20261106b/` 的完整 client/events、三份 Python 栈及双流有界 RS 日志。SHA256SUMS `d9e2df84f2e84783f04c82cc19a0c47f85198d1690d29ef7ee0d169134683f7b` 的七项均校验通过。CT05 controller 日志 `cold-catalog-controller-20261106b.log` SHA256 `dfc59bb7825ac34284c9bec3bed141a94bf20703b13b20cbb45dbd06bea904e8` 记录 00:12:20–00:14:06Z、exit 1、起止 e798。prepare 4.032 秒、RS 启动与 PID 绑定 6.610 秒、client 阶段 91.441 秒、cleanup 4.008 秒。三份栈均 exit 0/valid、约 0.050 秒被循环确认，无采样/资源/180 秒预算停止；这不是无观察输出的盲重试。

client 仍为一次逻辑 GET、三个 attempt_started、逻辑耗时 90.453 秒，只有最终 cause chain 明确为两层 ReadTimeout，未收到 headers/parser 事件。前两次没有逐次 cause，不称三次均已分别证明 timeout。绑定的实际 RS Python host PID 1694760、init PID 1694732，版本 3.14.6；每份业务栈都通过 `get_versioned_catalog → get_catalog → get_or_load → provider.catalog_at → dolt_cli.catalog_at`，已越过 visibility/commit_exists，处于并行逐表构建而非 DTO 序列化阶段。

| client 启动后采样点 | 同时处于 catalog route/futures 等待的线程 | 等待 Dolt 输出的 pool 线程 | 对应语句阶段 |
| --- | --- | --- | --- |
| 10.020 秒 | 1 | 2 | 1 个 SHOW CREATE schema，1 个 COUNT |
| 40.031 秒 | 2 | 4 | 4 个 COUNT |
| 70.043 秒 | 3 | 6 | 2 个 SHOW CREATE schema，4 个 COUNT |

这些是离散时刻的线程位置，不是累计 SQL 次数、完整阶段耗时或子进程 CPU/I/O 状态。栈中的 `_load_table_schema:414` 对应 SHOW CREATE，`_load_table_catalog:441` 对应 SELECT COUNT，均经 `query_json/run_cli → Dolt._collect:1380` 等待 stdout/stderr。同一 pool 线程可以在采样间处理不同表，不能说某个 COUNT 连续卡了 70 秒。隔离场景只有该固定父引用的一次逻辑 GET，且出现新 handler 的时间与内部重试相符，结合锁外 cache loader 实现，支持同 key 重试重复加载的解释；栈未包含 request_id，不作具体线程到某 attempt 的硬绑定。

RS 双流日志现在包含 startup、19 次 readyz 200 和 cleanup 引发的 shutdown/等待后台任务/终止记录，未保存 catalog 完成状态。栈已证实到达服务端，所以不再把“服务端是否收到请求”作为本次未决项；仍不能从无完成 access line 推断 HTTP 错误码或最终自然结果。日志保持 tail 2000 限制，cleanup 的 kill 不是产品自然退出。events 确认三个有效采样、无不确定复制/回收、own_activity_confirmed_stopped 和 lock_released；审核另查 marker ABSENT、本项目容器及网络无残留，原后验记录列源/目标卷保留。

| 主要证据 | SHA256 |
| --- | --- |
| `client.jsonl` | `279a71dbf17875e9746143845b5662ded478731e12aec942a6003c163f417d0e` |
| `events.jsonl` | `09b99021d9a6bc89815fad8b86b553e618940d70bea914b872f6c04a15197a05` |
| RS 双流 Docker 日志 | `b78a8cbfcf0b7b0400f26fea79341574694de1a1a9c5c8a4951c24c7e1317547` |
| `rs-stack-1.txt` | `115d2a9405e93058bb0a6dec64fcbcec6104dda7f652d7b7459f8ed4ae8c7cbd` |
| `rs-stack-2.txt` | `ea6b8e81c0aaaa311fd4dcfdc252a2c5642d91f62bc57177921311b900e7e38f` |
| `rs-stack-3.txt` | `05ee1a03291aabdfbf67c4d0ce152e6348dd1446c5edac112437dddd83747d20` |

**最小后续建议是转入冷 catalog 实现的修复设计。** 同时考察首次冷读的逐表 Dolt 调用成本与同 key 未完成加载的重复工作，保留 catalog 的表集合/schema/row_count/错误语义；单纯合并并发请求只能抑制放大，不能声称首次冷读已在原请求预算内完成。backend parent port 只消费表名是减少工作量的设计线索，但不能未经 owning Contract 决定直接用本地 manifest 代替权威 RS 校验或删除 catalog 的 COUNT 语义。冻结 e798 不原地改写，后续另候选定向验证；不提高 timeout、不预热掩盖，不追加相同诊断或完整 Submit，也不要求先证明 Dolt 内部所有慢因再处理已定位的重复工作。此次审核没有修改产品或授权后续运行。

**栈诊断 handoff 定向复核通过。** 原实施者仅文档提交 `127e85e8491723731bb61c95b7d9fef2c4cac993` 的追加与本节已核结果和摘要一致，保留逐 attempt cause 未知、线程无 request_id 硬绑定、schema/COUNT 等待、双流 tail 限制、保留卷/收束及正式 STOP；未把本次线索认定为原 lease 根因。对照本地既有 transfer-check/postflight/corrections 摘要一致；corrections 文件明确是错误转录摘要而非原始 stdout/stderr，handoff 也按错误摘要引用。无新增 finding、无新节点取证或请求，后续产品修复与冻结基准关系仍须另行明确。

**H3 状态勘误。** 原追加末句误将 H3 也列为 STOP，前次完整性复核未指出此处；已核对仅一句文案修正提交 `48a0970397986dcb59f948967f2da422ddc2050d`。准确状态为 H3 已通过、原合格证据保留，当前 STOP 仅指 W4/S4/H1 与其余剩余正式测量。本报告中“正式测量保持 STOP”按此范围理解，不撤销 H3 结论。

## 21. 冷 catalog 最小修复方向的只读预审

既有工具任务提出有界多语句 CLI 与同 key Future 合并，审核接受作为设计方向，**不构成产品修改、测试执行或测量恢复授权**。已直接核对 [Dolt 2.1.11 官方 sql.go](https://raw.githubusercontent.com/dolthub/dolt/v2.1.11/go/cmd/dolt/commands/sql.go)：多语句经同一输入逐条执行并输出各结果，默认错误返回，`-b` 是 no-op。它支持减少独立 CLI 启动的方向，但不证明现场 JSON framing、首次性能或唯一成本来源；不直接搬入测量用常驻 SQL server/socket/connector 设施。

设计须明确以下最小边界：

- 批大小 B 按 SQL 语句/结果数定义，DDL+COUNT 占两条。每条保持相同 exact AS OF、现有标识符转义、DDL/count 严格解析及最终排序/DTO；多结果必须明确数量、顺序与表绑定，不能直接把拼接输出交给单对象 json.loads。任何语句失败、非零退出、截断或缺结果均整批失败，不发布部分 cache。
- 现有单命令 capture 为 256 KiB；不能让一批仍共用 256 KiB 而误拒绝原可接受结果。可评估窄的每结果原限额与有界批总限额，字节数按实际 UTF-8 输出计算，其他调用默认不变。不使用估计 count，不删 row_count 或权威父校验。
- **30 秒预算语义必须显式决策。** 原 metadata timeout 作用于每条独立命令，整批共用 30 秒会收紧可完成工作量；仅保持设置值不能宣称行为等价，小 fixture 也不能证明所有旧输入不受影响。批次预算、成功输入范围和失败映射需在设计中说明，不能静默扩大/收紧或提高外部请求 timeout。
- 同 `(repository, commit)` 可用标准 Future 在原 leader 请求线程执行 loader，followers 锁外等待，不新建 executor；不同 key 不全局串行，成功/失败均移除 in-flight，失败不负缓存，超现有 cache 容量的结果只共享本次。关闭处理仅补足新 waiters 不挂死及既有 Dolt 终止所必需的接线，不自动建设新生命周期框架；Future.cancel 不是终止子进程，若新增关闭错误路径须明确现有错误映射。

后续授权后的验证应复用现有不变量，集中证明多结果 framing/精确语义/整批失败、同 key 一次 loader/不同 key 并发/失败后可再加载等业务屏障，不重复铺开所有类型矩阵。首次冷读与重试放大分别验：新 RS 进程中 attempt 1 成功才支持首次冷读改善，attempt 2/3 或预热成功不能代替；仅合并 in-flight 不能证明首次成本已解决。新 RS 产品/并发/镜像变更须独立候选和范围审核，明确与冻结基准的版本绑定；32768 cap 专用恢复例外不能外推，原 lease 问题仍 OPEN。

**预算核查后的方案收敛（仍仅设计）。** 现有 `DoltRunner._collect`/`ProcessStream` 都是进程整体绝对预算，`call_timeout` 只在启动前换算；没有逐完整结果通知/重置或 per-call capture 接口。A 若引入完整结果推进 deadline，测得的是主进程观察到的结果间隔，受 Dolt 输出缓冲/调度影响，仍不等价旧逐命令 30 秒，不应扩成握手 IPC。B 若直接给 16 条语句 480 秒，则放宽单条命令存活和后台/关闭等待，不等价原两 lane 墙钟或失败时点；不建议本轮采用。整批固定 30 秒则是预算收紧，三者都不能包装成“设置值不变所以行为相同”。

工具随后推荐更窄的 COUNT-only 批查询加同 key 合并，审核认为更适合作为最小候选：每批至多 16 表，使用同一 exact AS OF 的 ordinal+COUNT UNION ALL，仍单 JSON 结果、原 256 KiB capture 和原进程控制，不新增多结果 parser/流式进度接口；校验 ordinal 完整唯一、精确非负 count，DDL 路径/解析/排序保持，最多两 lane 且不嵌套线程池。规划调用数从 `2+2N` 降为 `2+N+ceil(N/16)`，不代表已测性能，N 次 DDL 仍可能主导首读。多个 COUNT 共享 30 秒依然需要设计显式接受成功范围/失败时点收紧；若不接受，则本轮仅评估 singleflight 抑制重复，首读问题保持 OPEN，不称完整修复或恢复。当前没有产品修改、测试或新请求授权，等待设计最终冻结范围。

## 22. COUNT-only 修复 kickoff 独立范围审核

**范围 GO，无阻塞 finding。** 审核对象为设计文档提交 `7bb5642d33` 的 [冷 catalog 最小修复候选](p6-cold-catalog-repair-kickoff.md)，代码参照冻结产品 `e798ec87a37330250b0c051162e7962dba1daa60`。这是设计范围结论，供设计下达后续实施任务；本节不授权节点执行、冷 catalog 再取证或正式测量恢复。本轮仅本地只读核查 Contract、实现与文档，未运行测试或节点操作。

冻结版 Repository Service Contract §13 要求绑定 caller 的 immutable commit、normalized SQL type 及既定 read-route 错误映射；§14 要求有限并发和简单资源上限。未发现 owning Contract/ADR 承诺每张表独立获得 30 秒或保证该预算内成功。现有 `metadata_timeout_seconds=30` 是单命令实现配置。kickoff 已明确接受最多 16 表 COUNT 共用该预算所收紧的成功范围，且保持超时/损坏输出经原 provider 边界返回 `503 SERVICE_NOT_READY`，不静默改成估计值、部分结果或逐表回退；无需为此修改公开 Contract。原每表 DDL、同一 AS OF、完整表集合、精确 count 和最终排序仍是代码验收条件。

COUNT-only 只产生一个至多 16 行的 ordinal/count JSON，复用既有 `query_json`、严格 JSON/列校验和非负 count 解析，原 256 KiB capture 足够表达该受限结果，不需要第 21 节讨论的 DDL 多结果 framing 或总 capture 扩容。ordinal 应严格按程序生成的整数身份校验（包含拒绝布尔值），验证完整、唯一、在范围内，再按固定表列表绑定；不能依赖 UNION 返回顺序。schema 与 COUNT 调度合计不得超过原配置并发上限，不能各建一套同时运行的池。冻结配置为两路，配置允许范围保持原样；具体调度由实施说明并接受代码审核。

singleflight 属于现有进程内派生缓存的最小控制，符合比例化政策的 C/D 类保障。缓存命中、leader 选取必须原子协调，loader 与 follower 等待均在锁外。代码审核须确认失败处理覆盖 loader 以及结果计量/缓存发布阶段的异常，leader 的 BaseException 退出也不能遗留 pending Future；清除 in-flight 与完成等待结果要有一致顺序，异常原样经现有边界处理，不吞掉异常或形成负缓存。超缓存预算只共享当前等待者、不同 key 可并行的规则完整。现有同步 leader 无客户端断连取消承诺，不因本次合并新增关闭状态机；具体实现若暴露新增等待者无法释放的缺口，再按 kickoff 回设计处理。

验证范围适当：复用解析不变量，最小真实 Dolt 场景覆盖跨批、转义和历史 commit 的精确 schema/count/排序；用事件同步证明同 key 合并、不同 key 并行、失败释放与重试、超预算共享。无需穷举线程窗口或全类型矩阵。新 RS 进程 attempt 1 成功才支持首次冷读改善，N 次 DDL 仍在，计划调用数不能当性能证据。后续单次副本调用仍须固定产品提交、镜像、对照方式和执行脚本再审；调试 focused 不替代最终按包/容器门禁。

冻结基准边界明确：候选从 e798 独立建立，不能混入 main 的其他产品变更，也不适用 READY 32768 cap 的恢复例外。新产品验证后另列 V→H 影响表，决定可沿用与需重测内容。H3 原通过证据保留，W4/S4/H1 及剩余正式测量继续 STOP；原 lease_lost 根因仍 OPEN。DC81 已解除的 S2a/S2b 依赖不被本修复重新引入。未修改三份 DC81 工作中文档。

## 23. 冷 catalog 候选代码与局部证据审核

**代码与局部验证通过，无阻塞 finding。** 代码候选 `4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`，实现提交 `dae01d557e150a078e813794d44d12d95c7ac34e`，handoff 文档提交 `eaf247c67af4c23de9aa333f07acc5e8f2ab0590`。审核读取独立 worktree `/home/dev/gdds-p6-cold-catalog-repair` 相对 e798 的完整四文件代码/测试增量及 handoff；工作区 clean，`git diff --check` 通过。未运行测试或节点命令。本结论可供设计准备下一固定镜像/单次诊断候选，不放行镜像执行、冷调用、Submit、合并或正式测量恢复。

产品仅改 `candidate_a/dolt_cli.py` 与 `versioned_read/application.py`，符合已审范围。COUNT 每批至多 16 表、同一 escaped AS OF literal，复用严格单 JSON/列校验；ordinal 拒绝 bool、非整数、越界、重复或缺失，按输入列表绑定，计数沿用原解析。schema/COUNT 分两阶段共用原受限池，单路配置顺序执行，空 catalog 不发 COUNT；完整成功后才缓存并排序。单命令预算/capture、provider 映射、import `catalog` 和 `type_catalog` 未变。原 `_load_table_catalog` 仍有 import 调用者，保留不是兼容死路径。

缓存与 leader 选取在同一锁下，loader/follower 等待在锁外，无新增 executor。loader、计量和缓存发布均处于失败处理范围；BaseException 也完成等待 Future、移除 in-flight 并重抛。发布失败移除该 key，并按最多 8 项重算占用；超 16 MiB 结果只共享当前等待者，不留存。Future 为内部对象，没有公开取消/回调接线；本次不需要另建生命周期机制。不同 key 独立，成功/失败后续请求的行为及原缓存上限保持。

测试覆盖 0/1/16/17 表批次、乱序/错 ordinal、失败不缓存或回退，以及同 key 合并、不同 key 并行、超限共享、loader/计量/发布异常释放和重试。并发用例使用事件/Barrier 且标 serial；真实 Dolt 用例已标 integration，一次批量构造 17 表、视图和转义名，再推进 main 的行数/schema 后读取历史 commit，与原逐表精确查询比较完整结果。没有为纯解析使用真实 Dolt。`4497` 相对 `dae01` 仅把测试参数的两个字典字面量改为显式 `dict[str, Any](...)`，键值/顺序相同；不要求因此重复 focused。

直接读取 LAN 回传至 CT201 的五份原始日志，路径均在 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/`，逐项 SHA256 与 handoff 相符：

| 日志 | SHA256 |
| --- | --- |
| `focused-dae01d557e.log` | `29234ec411a2287fe7834ad89a7d2c7a6c97e01b51de9dfc331df54b0d0cb9a2` |
| `focused-dae01d557e-corrected.log` | `d5b859a220e9856d58f5a2ed403a8fc2f219c9d633241e5290fcd41081f98895` |
| `static-dae01d557e.log` | `6eb19213484d0da408803a40900493775abfbf98f216e3dbf7d71f9f92f0a34f` |
| `static-4497ded8ff.log` | `e2107d634e435f3a8c1f815e4a807f03bdd40c6ef7e8688025faa47cd331f4c5` |
| `closeout.log` | `7d19185a6d45a4e4ae55188934529c5fd0b744430c7fee4dc1774b81cbce6bc9` |

CT05 hostname `gw-dms-test-05`：首次 00:40:00–00:40:02Z 为 wrapper 切目录后的参数路径错误，collected 0 / exit 4，尚未执行测试对象；保留失败后按 DC68 修正一次，00:40:23–00:40:41Z 在 dae01 **83 passed / 17.72s / exit 0**。00:41:18–00:42:11Z 五包 Ruff 与前四包 mypy 通过，RS mypy 仅新测试异构参数推断报错、整体 exit 1；4497 的 00:43:04–00:43:05Z RS Ruff/mypy（201 文件）通过、exit 0，native build input 的 expected/installed 同为 `58436908aee9dd449f4d3e0542a6a8c1920b6d5e`。各日志起止 HEAD 和五锁摘要一致，声明使用本机预置缓存、offline/no proxy；closeout 记录 00:43:44Z 已确认无自有运行容器/任务并释放自有锁。本审核核验保存日志，没有重新访问节点或把收尾记录冒称实时状态。

83 项实际来源为 dae01；其结果可作为本候选的局部回归证据，不称 4497 实际跑过、权威 runner 或 carried。五包静态通过按上述两次记录共同支持。当前 HEAD 未验证新镜像；本轮内部 Python 改动未触碰容器专属边界，镜像与相应门禁延期至设计安排的下一固定候选，旧 e798 镜像不沿用为本候选通过。独立单次冷调用仍须提交产品/镜像身份、对照方式和脚本供审核。

同时已核设计补充 `7c4da1b79c` §6：30 秒不是不可商议业务 SLO，attempt 1 条件仅判断原配置首次读是否解决。若最小修复仍发生 ReadTimeout，保留失败事实，带实测、规模/硬件及请求预算、重试和后台资源影响交 owner 讨论，不要求无限优化或重复全量，也不改写旧配置结果。正确性与身份边界不放宽；H3 保留，W4/S4/H1 及剩余正式测量停止，原 lease_lost 根因仍 OPEN。

## 24. 修复后单次冷 catalog 候选审核与 GO

**明确 GO：允许原实施者按最终 README 在 CT05 执行一次 `p6catalogdiag20261106c` 诊断。** 已直接通知实施者与设计，无需再等 owner 确认。范围为一个已核源 RS 卷的本机独立复制、启动新 4497 RS 与原 e798 客户端的一次逻辑 GET，保留原 30 秒/最多三次内部尝试；不含 Submit、py-spy、手工重试或正式测量恢复。本审核仅本地读取/比对脚本与保存日志，未执行候选、镜像命令或节点操作。

最终文件根目录为 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogdiag20261106c/`：

| 文件 | SHA256 |
| --- | --- |
| `candidate-manifest.json` | `a2e9f7d1c73fb25b479ec655f6605f271dcfbdc2eed34174bf7ce6c411b50e22` |
| `candidate/execute.py` | `3f9a390632139eb7d3104732e205a4b7ce9ff801a8c75d3fe29cda11a17fbe68` |
| `candidate/client.py` | `aba44b6cdcac1b14ae78a3d01ed579b37bcbc51cf07cdd67adb0089f59bf679e` |
| `candidate/README.md` | `9f4c2ea4e276d340ab8ed971be8b57e0909de65c0f024f7a61b1a559f349af62` |
| `candidate/node-identity.json` | `72d74b789850cc6cba3831e9e2e71bfbdb93b1fe9f71e7c9895e4f548e942d53` |
| `archive-image-identity.json` | `a3bfcf294a4af9ccf471f19e8979f19adb396ffbc4ce178f2bc2edb5089b3b36` |

manifest 全部 14 个文件的实际摘要逐项匹配。首版 execute `850912f1…e054` 的 `RS_EXPECTED_SHA` 手抄漏一个 `c`，会在 `fixed_tool_identity` 确定停止；发现后未执行候选。修正只补该字符，反向替换精确恢复首版 SHA，未夹带逻辑变化。README 另明确完整 canonical SHA 仅标识本响应，并纠正 checker 结束 `01:04:21Z` 与释放锁 `01:04:51Z` 的区别；这两处文案与原日志一致。

已读取 CT201 `ct201-rs-build-4497.log`、save 日志及 CT05 load/严格传输复核/identity checker/锁释放记录：构建起止为 4497，预置 dependency-base、build network none，build/save exit 0。归档 SHA `0f75b1b3db03761298e58cafe5c801ca3d79064348e1f3e28f2e9a9716606772`；新 RS config digest `sha256:39e0668b05a814c835ae8214dd486c5641d0ff61b9a2c6044a53b71c6e05a1f2`、全部 28 DiffID 在 CT05 checker 三项相等，`RESULT=MATCH` / exit 0，核验日志 SHA `e0f4cc507ba52cea0ead5b6d7bd65e90344e049bb7cdb07e91f890f8749fae34`。vnext tree `b59b592b83a5adf31fbe5610ee9b797bff072092` 与 Git 一致，source-tree label 值与构建日志一致。跨节点不比较 inspect ID；worker 继续绑定既有 CT05 本机 ID 和完整 15 DiffID。首次 checksum 行格式警告、引用 CT201 路径的只读失败及旧 helper 路径缺失均已保留/说明，后续严格三文件核验及 checker 通过；无须重载或重复准备。

controller 保持既有边界：固定 CT05 hostname、e798 clean worktree/字面解释器/backend cwd，离线无代理；先自取占用锁，核资源、工具/镜像/来源摘要与目标名称碰撞。源为已核且停用的 `p6bw4s4h120261105b_repository-service-data`，只 `cp -a` 到新空卷，不重扫大输入。新 RS 使用原 Compose `--no-build --pull never --no-deps --wait`，readyz 不预热 catalog。阶段仍为准备 60 秒、启动 120 秒、client 180 秒、收束 90 秒；资源检查与失败停止保持。双流 Docker 日志仅末尾 2000 行，不称完整；先停双方、确认自有容器/network 收束再释放自有 token，不确定则保锁，保留新卷和来源。最终事件与 launcher 记录实际 exit、起止 HEAD/时间，未把外层取证成功冒称诊断成功。

client 只加观测与返回后完整 DTO 指纹，未改原 transport、parser 或重试，也不二次读取 HTTP body。固定 repository/commit，完整 `VersionedCatalog` 包含 commit、所有表/列/schema/primary_key/row_count；与 repository id 一起作 sort_keys/compact/ASCII JSON 的 SHA256，只输出摘要、大小和汇总数量。该指纹不独立证明与旧大样本逐字段等价，已有小 Dolt 历史 commit 差分是本轮局部正确性证据。只有 client exit 0、唯一 SUCCESS、commit 匹配、观测完整、摘要生成且 attempts=successful_attempt=1 才为 `CATALOG_RETURNED_FIRST_ATTEMPT`；重试后成功另列且整体非零，不替代首读结论。单次成功仍不证明原 lease 问题解决或正式门禁通过。

执行前按 README 再确认 BatchMode SSH/空闲，LAN 同步后核上述固定文件摘要，controller 自取锁，不叠加外层锁。任一失败即停并交回 client/events、双流有界日志、launcher 实际 exit、SHA 与收束/锁状态，不自动重跑。后续按实测决定最小预算/设计讨论，H3 原证据保留，其余正式测量仍停止。

## 25. 修复后冷 catalog 结果：逻辑调用成功，首尝条件未达

**证据复核通过：产品逻辑 GET 最终成功，首尝返回的诊断条件未达。** 不将工具 exit 1 等同产品最终 ReadTimeout 或此次业务调用失败。审核直接读取 LAN 回传 `p6catalogdiag20261106c/run-evidence/` 的 client/events、launcher 与双流有界 Docker 日志；`SHA256SUMS` 四项全过，launcher 自身摘要另核一致。本轮没有节点操作、追加 GET 或测试。

CT05 `gw-dms-test-05` 于 2026-11-06 01:24:17–01:25:40Z 执行一次；起止控制 worktree 为 e798，events 的 controller/client 摘要与第 24 节最终 GO 相同，新 RS config digest/28 DiffID 实时核对 MATCH。准备 8.828 秒、RS 启动 6.205 秒、client 容器阶段 64.048 秒、收束 4.008 秒；没有阶段预算或资源停止。启动前传输曾把新 execute/README 放错目录，保存的复核显示 candidate 仍为旧 SHA；随后修正目标，实际 run 的脚本摘要正确，错误候选未执行，不计作第二次诊断。

一次逻辑调用用时 **62.919 秒**，记录三次 attempt_started。仅第三次有响应头与 parser 记录：HTTP 200、约 2.457 秒收到 headers、约 2.487 秒 parser 返回，wire bytes 578,800；client exit 0、唯一 SUCCESS、commit 匹配、instrumentation_incomplete=false。前两次没有逐次 cause、headers 或 parser 记录，不能称已分别证明 ReadTimeout。第三次耗时也不能当成首次冷 catalog 构建耗时或独立冷读性能；此前同一进程内的加载可能仍在推进。

完整返回 DTO 汇总为 **631 表、7,538 列、683,508 行**，canonical JSON 为 599,414 bytes，指纹 `f08a8a83932553dab91cec22dafbb12fead5baa348ece6436882f3d0174b467d`。固定 repository/commit 与目标一致。该 SHA 是本次完整响应的身份，不是与旧大样本逐字段等价的独立证明，也不证明 singleflight 在现场具体合并了几个请求。RS 日志包含该 catalog route 的 200 和正常 application shutdown；不以未保存前两请求完成日志推断其服务端状态。

controller/launcher 均 exit 1，结果为 `CATALOG_RETURNED_AFTER_RETRY`，原因是 successful_attempt=attempts=3，不符合首尝诊断条件。events 记录 own_activity_confirmed_stopped=true、copy_uncertain=false、lock_released，数据卷按脚本保留；实施者另报告 marker absent。审核只核保存日志，不把该报告冒称本审核实时节点检查。Docker 日志仍为双流末尾 2000 行；cleanup 引发的 shell 终止不是产品自然失败。

| 主要证据 | SHA256 |
| --- | --- |
| `client.jsonl` | `dcc4acd90cd63d659be2a4ffceb8a8db50be45b4091262c3c66cde01d6bf701e` |
| `events.jsonl` | `33282c78c91b8198c86d84a63d5a291f771c31e7c34a6ffb7145d0d28e34dba7` |
| `launch-20261106c.log` | `1cebefe89674cee2457c21fb749ab9a6cac678f7ddb1e68919e6b82294b20a74` |
| RS Docker 双流日志 | `ee971da0349ca833b53c0195a02a0cc0026af6a7a23405608128bdb77659bae5` |
| `SHA256SUMS` | `adca606ecb7cde99a7aae8fc4c9a0aba9a6d34f9d00a7d61905e6a0901b57efd` |

**边界建议：按 owner 性能补充保留首尝未达这一余项，可转入新 RS 下单步 Submit 的具体方案准备。** 当前逻辑读取已能在原内部重试机制内返回，不要求先把所有冷读压入 30 秒才允许继续诊断；不追加相同 GET、不预热、不擅改 timeout，也不继续无限优化。新方案应使用已核 pre-submit checkpoint 的独立副本，不能续用失败 Submit 或本次冷读产生的运行卷；固定 e798 backend/worker 与 4497 RS 的混合身份、原输入/规则/parent 绑定和租约/心跳/请求预算，仅一次 POST 加必要有界观测，具体脚本、预算和收束再审后才执行。第 13 节旧 GO 和 READY cap 例外都不能外推。

该建议不是新的 Submit 执行授权，不把局部成功认定为原 lease_lost 已修复。H3 原证据继续保留；W4/S4/H1 与剩余正式测量仍须另定 V→H 影响和恢复口径。

## 26. 新 RS 单步 Submit 接续范围

**范围 GO，无阻塞 finding。** 已核设计提交 `34bd19e5e4` 在 `p6-submit-single-step-diagnostic-plan.md` 新增的 2026-11-06 接续节，与第 25 节建议一致。原 pre-submit 三卷 checkpoint、输入/cache 按 e798/旧 RS 的源身份核验，目标明确记录 e798 backend/worker 加 4497 RS 的固定组合；只允许独立外置工具表达这一精确关系，不改源 manifest、不写假 MATCH 或增加通用 skip。新 project、证据目录、幂等键和目标三卷保持隔离，原 parent/规则/输入/cache/TTL、租约/心跳/timeout 与 45 分钟观察及资源/栈停止边界完整。

可直接进入实施者固定脚本/身份/命令的定向审核，无需重复范围确认。本节不授权 POST 或节点执行；具体候选通过后才给本次单步 GO。已核观测能力可按相同 worker 镜像/解释器绑定引用，不要求重复 canary、冷 GET、预热或重 Preview。该混合版本诊断既不是原冻结失败的原样复现，也不代替新 RS 正式门禁、合入或 V→H 恢复判定；H3 证据保留。

## 27. 源运行 RS 身份记录的实际边界

设计要求定向核查后，审核先读本地既有报告和精确记录，再经 BatchMode SSH 只读 CT108 三个已知文件：`capacity-resume-h-20261105/ct108-repository-service-image-build-and-identity.log`、`p6bw4s4h120261105b/evidence/run.json` 与该项目 `launch.log`。未运行 docker inspect/save、服务或查询，也未扫描业务卷。三文件 SHA256 分别仍为 `4faf2c492d1e853776b9943ff825769a9f63019d661124745270992c5838d6ca`、`b1c0c939f090b3e95981791f8de44aeafa1ce5ff35d0dac603df3b6ffbd08317`、`6b5a40958b973d5c699b0efe22b4a5b4b4c66eae00db51bd5fba7072f99d486b`，与原审核记录一致。

旧恢复 GO `e89dc0db35` 的报告 §3 对 RS 实际确认的是当时 CT108 构建及标签匹配：revision e798、build-input `4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00` 和 lock。原构建日志另保存导出 config digest `sha256:2018c3ae5409b04aeb1c393fe278a9aefaed5b3e0292c767ae39764aaddbbe12`，但没有源运行 RS 容器的完整 DiffID 绑定。run 的 `compose_image_metadata` 只含 backend/worker，launch 的 RS CPU/步骤记录不能补出镜像身份。05 后来的本机 RS ID/28 层记录证明的是 05 当时对象，不能倒填为 CT108 源 run 使用的对象；当前 tag、warmup 或构建时 config 也不能冒充运行绑定。

**明确缺口是 source-run RS 完整镜像身份未记录/未闭合，不是 checkpoint 内容来源失效。** 三卷 pre-submit checkpoint 的内容与属性摘要、运输物化、源 run/state、parent/input/cache 已按既有流程核验；此次只改查询/进程内缓存的目标 RS 也没有引入持久格式变化。对限定单步诊断，建议保留并使用这些已核源材料，同时把旧 RS provenance 分为“构建标签/config 已知”和“运行时完整身份 unavailable”，不制造源 RS MATCH，不新增通用 skip，不修改历史 manifest。新目标 RS 仍须按固定 config digest 和全部 DiffID 核验。

已交设计决定对第 26 节“按旧 RS 身份核验”的措辞作这一窄化；无需无限搜寻不存在字段、扫描卷或重做 warmup。该建议不支持冻结运行原样复现、正式镜像等价/carried 或性能归因，也不授权 POST。设计明确后，外置候选只表达该固定来源及缺口、新目标完整身份和其余不变检查，接续具体脚本审核。

**设计窄化已通过。** 已核 `13dbd76af194001c74fdd674830fd76eedaaae45` 的实际文本：明确 `run-bound RS full identity unavailable`，构建记录不升级为运行证明，已核 checkpoint 仅作为新目标诊断输入；内容/parent/input 不符仍停止，目标全 config/DiffID 身份保持。正式恢复或 carried 若需要缺失证明，须另带具体处置方案交 owner。本节缺口已明确处理，可直接继续外置固定候选审核，不再索取未保存字段，也不新增 POST 授权。

## 28. 固定单 Submit 首版候选：收尾需修订

候选项目 `p6catalogsubmit20261106d`，manifest SHA `efaefc6a4c069aa155730e95aa1883f65a0e3ce3ca3e302a9d65bc0235e64562`，launcher SHA `bbbe6311bdb2ed6b91545fe6267f5f2dadefe29888794e306b71bbf5487b04b6`，shell SHA `8bee28350189c3a3c4efa51651f723a8c48b0834ff7ce447148ab1cbd11b3ad1`；handoff 提交 `a158022d8cb5893bb2d48910c5cc0da28980fc4d`。已核 manifest 六项大小/摘要及候选 `SHA256SUMS` 全过。经 BatchMode SSH 只读核 CT05 引用的原 helper、F1 wrapper、resource observer、py-spy、expected-image 与 checker 六个文件，实际摘要均等于 pin；没有执行候选或节点测试。

**需修订收尾接线，当前不 GO。** `run-once.sh` 在 sampler 返回后新增直接 `docker compose ... down --remove-orphans`，但父 shell 未提供 Compose `secrets.file` 使用的 `GATEWAY_P2R2_BEARER_TOKEN_FILE`、`GATEWAY_BACKEND_SESSION_FILE` 和 `GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE`。原 journey 仅在子进程 `_compose_environment` 的局部 env 中生成这些路径，子进程退出不会回传父 shell；因此这条新增裸命令缺少解析原 Compose 所需的 secret 配置，可能在 journey 已正常收束后仍产生 cleanup 错误并保锁。它同时没有外层执行超时，不满足外置收束有界要求。原 journey 自身的 `run_compose(env, down, timeout=600)` 接线完整，不能据此认定新增 shell 命令也完整。

已要求最小修正：保持原 journey 正常收尾；外层先查固定 project 的残留，无残留只核 quiescence，有残留则用固定 project 的有界停止/移除容器与 network，或提供明确可解析且有界的 cleanup 环境。未知状态保留锁，不删除卷，不增加通用生命周期框架或业务测试。修订后交固定文件与 manifest 新摘要，暂不 POST。

其余定向审核未见阻塞：源 RS 明确 UNAVAILABLE/build-time provenance，源 run/state/checkpoint/input/cache 按原 helper 严格核验，新目标 4497 逐 config/全部 28 DiffID 与标签核验，backend/worker 仍原 e798；没有旧 RS 身份造假或修改源 manifest。普通 resume 只比较原 backend/worker 身份，新 RS 由外置候选单独绑定；复用 F1 单 POST wrapper、45 分钟独立 guardian、15 秒 Python dump/5 秒资源停止，以及目标步骤 finally 先关闭 observer 的接线。固定新 project/key/目标卷及同 manifest sampler/postflight 保持，采样与观测职责未扩展。

## 29. 单 Submit r1 复核与明确 POST GO

**明确 GO：允许原实施者按 r1 README 固定命令，在 CT05 执行一次 `p6catalogsubmit20261106d` 单步诊断。** 已直接通知实施者与设计，无需再等 owner 回执。仅原 pre-submit checkpoint 的独立目标三卷、新 project/key、e798 backend/worker 与已核 4497 RS、一次 `v2-submit` POST；不包括 Preview、后续步骤、失败重跑或正式测量恢复。源 RS run-bound full identity 仍明确 UNAVAILABLE，诊断许可不补造缺失身份。

handoff 提交 `716ef8ae5df7a891566bc051627ea075f8b23bca`。候选根路径沿第 28 节，最终固定身份如下：

| 文件 | SHA256 |
| --- | --- |
| `candidate-manifest.json` | `2a4c6cefd0febef40e0a09e918f6c396872619fa2e1b32d81e593ef16a2da1e8` |
| `candidate/submit_diagnostic_launcher.py` | `6686e81085eb8c6e833140c0994a03d3a993b063b089f44f406c409dbdabb977` |
| `candidate/run-once.sh` | `7f5089eaf7b1b242271a85961f634428e934a8fa093fb2538f0d0a90a9340a49` |
| `candidate/README.md` | `68fdd8241216286d0296f606e42b2afd5e7e74a35e4009d094f228ddd9d88eee` |
| `candidate/SHA256SUMS` | `67b39365a40b9a15275b6dc8e7f425100becc436fb9d116a56174c8058aa2a41` |

source readout 与 target RS identity 均保持第 28 节摘要。审核程序核对最终 manifest 的六个候选文件和五个准备日志，大小/摘要全部匹配，shell 内 launcher pin 相等。`preparation-validation-final.log` SHA `be6a2e6ddf7b8921de85399859abb44aa66dd8e05ae77e0e7bf5b379c5fb888d`，记录候选 SUMS、bash syntax、AST、pin/28 DiffID 检查通过，未运行候选。初次 pin 检查的正则误报及两次 manifest 生成路径/字段错误保留日志，不将其冒称产品或节点验收失败；不要求新增业务测试。

**第 28 节收尾问题关闭。** 删除裸 Compose down，原 journey 继续以自身 secret 环境完成正常收尾。外层 cleanup 先按固定 project label 列容器/network，无残留仅重复确认；有残留才使用 30 秒单命令预算、`stop --time 10`、不带 `-v` 的 `rm --force` 和对应 network rm。记录每条命令及最终空集合；任何超时/非零/无法确认均失败并保留锁，不接触源项目或数据卷。审核者仅在内存字符串中反向去除新增 cleanup 函数和 main 入口，所得摘要精确等于首版 `bbbe6311…04b6`，用于确认其余逻辑未变；没有改动执行文件，也不要求实施者移除 cleanup。实际 GO 始终绑定上表含 cleanup 的 r1 launcher `6686e810…b977`，首版不获执行授权。

shell 对 preflight、cleanup、postflight 各加 300 秒 outer timeout（TERM 后 15 秒 kill），journey/sampler 整体为 3600 秒（INT 后 30 秒 kill），原 POST guardian 的 2700 秒预算不变。固定 sampler 子进程没有另建 session，继续使用原 child 终止/等待路径；正常 wrapper 仍先关闭 observer 再进行 journey finalization。这些外层上限是诊断截断保护，不延长产品请求/租约或把单步预算改成 60 分钟。缺失/不符 state 与 sampler manifest 比较会使验收非零；锁释放依据自身资源静止，不能以释放锁表示业务成功。

执行前确认 BatchMode SSH/节点空闲，LAN 同步后核固定摘要，使用 README 的唯一 `run-once.sh` 命令，由 shell 自取锁，不叠加外层占用。身份/输入/缓存/源副本不符或任一停止条件触发即停留证，不自动重跑；未知收束状态保锁。交回 controller/launch、preflight/目标镜像检查、独立 Submit 结果、原 run/state、observer/resource、cleanup/postflight、实际 exit 与 SHA/锁状态。独立结果成功也不等于原 journey 完整 PASS、lease 根因闭合或正式恢复；H3 证据保留。

## 30. r1 启动接线失败与 DC68 判定

**r1 属于尚未触及被测对象的外置 launcher 工作目录错误，符合 DC68 一次修正重做范围；不作为产品回归失败。** 审核前次漏看 sampler 以仓库根目录启动 child，导致第 29 节 GO 未发现 launcher 要求 backend cwd 的矛盾。原 sampler 的 `--worktree` 同时用于定位 `vnext/backend/.venv/bin/python`，因此保持其仓库根目录含义，仅修外置 launcher 的固定目录接线。

CT05 保存日志显示 2026-11-06 02:26:45–02:27:12Z 起止 HEAD 均为 e798。preflight 的 source/input/cache、backend/worker 与目标 RS 身份核验通过；sampler 于 02:27:09.080Z 启动 child，child 在 `require_fixed_context` 的 cwd 断言处退出，尚未 import journey、创建目标卷、运行 Compose 或 POST。sampler/launcher exit 125，state 为 NO_STATE、run SHA 为空，resource 无容器样本。不能把 sampler child 已启动表述成“没有启动 child”。

cleanup 保存的每条操作均为固定 project 的容器/network 列举，初始与最终集合为空，没有 stop/rm 或卷删除；postflight 为 VERIFIED_QUIESCENT。controller 记录释放锁，02:28:39Z 只读后查亦记录 node_lock=ABSENT。preflight 已进行授权内目标镜像 retag 和证据写入，这些保留，不声称整次执行完全没有任何写入；失败未影响源 checkpoint、业务状态或被测服务，故不妨碍本次 DC68 判定。

已核回传 `failed-run-readonly/SHA256SUMS` 九项全部匹配。launch SHA `8b71c98f4ebdad3741c680b39ce8174e195edd0dc5ba49b448898bab5465f7ba`；SUMS SHA `704507a035603b5e69cb097a40603c54036b25689d48f75a979ba0f6f1a36808`；只读后查日志 SHA `a3aee64520e4221b10c6d989eb0df14ea3b00b8260ca640a684c182314048b71`。旧项目、失败目录与镜像保留，不能覆盖后重试。

最小修订限于：submit 模式只接受 sampler 传入的确切仓库根目录，经原 hostname/owner/解释器/HEAD/clean/工具 pin/环境检查后切换到固定 backend 目录，再 import journey；其他模式仍只接受 backend 目录。保留 sampler 原参数、业务 wrapper、原预算与收尾，记录入口及实际 journey cwd。新 project/key/证据目录隔离失败尝试。修订候选固定摘要复核后可直接给予一次从 preflight 开始的重做 GO；再次失败即停止交回，不再自动重试，不重开已确认范围或旧场景。

## 31. r2 固定候选审核与一次重做 GO

**明确 GO：允许原实施者按 r2 README 唯一命令，在 CT05 从 preflight 开头重做一次 `p6catalogsubmit20261106e` 单步 Submit 诊断。** 已直接通知实施者和设计，不必等待 owner 或本报告提交回执。本次是第 30 节 DC68 修正后的唯一重做；再次失败即停止交回，不可自动再次重试。旧 d 项目证据和镜像保留。

候选根路径 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogsubmit20261106e/`：

| 文件 | SHA256 |
| --- | --- |
| `candidate-manifest.json` | `e34546dac931be3ebb4d07aa328908ba5a452a7df6ba2c053bf3e82fcdd924ab` |
| `candidate/submit_diagnostic_launcher.py` | `9bb25a936248fae294adb01bf928d43cc8d18767832becf66c72cc0e19e1ed75` |
| `candidate/run-once.sh` | `ee8573d082aa7990b789ed202c179d4947fbc70e8edd22c93ce89c3b8a698990` |
| `candidate/README.md` | `f411c635884d37f49be6df8f64b03213600b9826458afd9fa11d3f5b44324e0c` |
| `candidate/SHA256SUMS` | `eac27308f8c117ffe33862b00ebec9396babe659c3a57e3c37db4928a2fbdb4e` |

已核 manifest 六个文件大小/摘要全部匹配，SUMS 五项匹配；source readout 和 target RS identity 沿用原字节与摘要。准备日志 SHA `34a7055868bebd729479155910e07538e7a305fb35a1c01cf5fdcefb50d50543`，仅语法/AST/固定 pin 核对；CT05 sampler cwd 只读日志 SHA `346b1a7bc754c321c9196adcc3c81557c3c5025c5594079a9d33dad71f3f22a3`，确认原模块 `Popen(..., cwd=worktree)`。审核未执行候选、测试、Compose 或 POST。

逐行 diff 仅含 d→e 固定项目/路径/token、launcher mode 参数及明确 cwd 校验/切换、入口与 journey cwd 日志、shell launcher pin。submit 必须从确切 REPO 进入，原检查成功后才切到 BACKEND；其他三个模式仍要求 BACKEND。保留 sampler `--worktree REPO` 与其解释器定位关系，没有允许任意 cwd 或删除检查。source provenance、目标 RS 全身份、普通 resume、单 POST wrapper、输入/cache、45 分钟 guardian、观测和外层清理/超时均不变。

执行前 LAN 传输并核以上固定摘要、确认 SSH/节点空闲，由原 shell 自取锁；仅新目标三卷与新 key。执行范围和失败收尾沿第 29 节，源 RS 仍为 run-bound full identity UNAVAILABLE，目标 RS 必须全身份 MATCH。不得追加 Preview、冷 GET、预热或后续旅程，也不授权正式测量恢复。一次结果与实际 exit、输入比较、资源/observer、cleanup/锁状态及 SHA 交回；本 GO 不预判业务成功或原 lease_lost 根因。

## 32. r2 实际停止原因、收尾与最小下一步

**本次直接停止原因是观察器连续两次无法发现 Python 解释器，按既定规则发送 SIGINT；不是已证明的产品终态失败或 lease_lost 复发。** 设计要求立即分类后，审核于 2026-11-06 03:10 UTC 起经 BatchMode SSH 只读 CT05 已有 evidence/observer、Compose 保存日志、launch/controller/postflight，以及冻结 e798 源码；未追加 GET、测试、采样、Compose 操作或业务卷扫描。实施者 `b6fb6255e8` 的运行中快照保留，但“收尾尚未完成”已被后续完整文件更新。

唯一 Submit POST 于 02:40:13.107935505Z 返回 202，operation 为 `op-24f7e8882f5178345fcd55c9`。观察器 02:40:10Z 已绑定 worker PID `1864826`、starttime `194257036`。95 次运行期 dump 中 89 次有效，6 次 exit 1；此前第 6/35/45/69 次无效后均恢复，最后第 94/95 次于 03:03:26/41Z 连续失败，均约 0.101 秒、非超时，保存文本均为 `Error: Failed to find a python interpreter in the .data section`。stop 文件为 `two_invalid_dumps`，observer 源码明确向父 launcher 发 SIGINT；traceback 为 `_poll_operation` 的 `time.sleep(2.0)` 收到 KeyboardInterrupt。故 03:03:41.985Z 的 `step_failed` / wall 1411.262 秒是这次诊断截断的记录，不能据此生成业务失败码或宣称自然运行已达终态。

最后有效栈第 93 次（03:03:11Z）仍显示 active+gil 的 `row_digest_from_image/encode_row`，调用来自 `_mutation_snapshots_from_repository`。最后资源读取 03:03:38Z 成功，worker RSS 17,161,650,176 bytes、host available 49,893,886,976 bytes、数据空间 219,002,765,312 bytes，均未触阈值。`read_resources` 每次先比较该 PID 的 starttime，故已有证据支持原进程绑定至少持续至 03:03:38Z；第 95 次 dump 的准确时刻没有新的身份读取，**不能把前一次成功升级为该时刻身份已独立证明，也不能凭 py-spy 错误断言进程已退出/替换**。现有记录没有 PID identity changed/resource_unreadable 停止，解释器发现为何间歇失败仍未知；不再为该未知点重复同类现场取证。

已保存 Compose 日志有 136 次 `heartbeat_succeeded`，最后为 03:03:35.784918210Z，相邻最大间隔约 22.022 秒；未发现 `lease_lost`、`heartbeat_busy_deadline`、`STORAGE_PROJECTION_FAILED` 或 `code=operation_failed`。这些只覆盖保存日志截至截断前的窗口，不证明原 lease 问题已修复，也不证明之后业务自然完成。有效栈按完整调用链分组：frozen projection 7 次（02:43:26–02:44:56Z）、frozen mutation 构造 14 次（02:45:11–02:48:26Z）、parent materialization 37 次（02:48:56–02:58:26Z）、parent mutation 构造 19 次（02:58:41–03:03:11Z），另有前期 12 次；这是采样点分布及阶段推进证据，不换算成精确阶段耗时或成本占比。

收尾已完成：03:03:42.252Z 保存 Compose 日志，03:06:47.164Z 记录三目标卷保留，03:06:49Z controller 结束并释放锁。约 185 秒的日志保存后收尾没有超过原 journey down 600 秒上限，原 Compose backend/worker `stop_grace_period=180s`，不能只凭数分钟无最终文件就定性卡死；没有足够子段证据把这 185 秒全部归因到某一服务。run exit 1/failure_type KeyboardInterrupt；sampler child exit -2，在 shell 为 runner/launcher exit 254；独立结果 STOPPED、post_count=1、submit_completed=false。cleanup/postflight 均 0、VERIFIED_QUIESCENT，目标容器/network 空，state 与 sampler 输入比较双 MATCH；审核随后只读确认锁 ABSENT。输入匹配和清理成功不等于 Submit 成功。

| 已读证据（项目 e 根目录下） | SHA256 |
| --- | --- |
| `launch.log` | `2baf057e53d541afa9c782dc8f9585de1fc84639bc035e6fc810f1404ee1cbf7` |
| `controller.log` | `f8b19e1684e681c352ba0acb2c844ef64f7bf8704731b76d48a855f559d5dc2a` |
| `evidence/observer/observer-events.jsonl` | `dd49991aab90fafb3c2f96e2e6503e506d9ce4a05941fcd6ac45113cca7305c2` |
| `evidence/observer/observer-stop.txt` | `8f9ddb6ab9d70fdad4dcbb09f19107514cbcb3e334acf384a76118172c1e9b1b` |
| `worker-stack-0094.txt` / `0095.txt`（observer 内） | `7623002d191aeeef3df3341a856705ebabf0ba1152a2812665441fd6d68e04ea` |
| `compose/real-dump-t4-20261106T030342163105Z.compose.log` | `8f40f2855788027205b2f8afcbf14bde0c7d46ce3123d7531ed0a80839361761` |
| `evidence/run.json` | `8d03e8da82037495f05ed8233f88832251a48c137f47846458fee9844520da88` |
| `evidence/state.json` | `32a2b987b77be4e38f95f7840e7b4f176c833649deafa2b1ee09177ef98306b9` |

**DC80 下一步范围建议：接受设计提出的最小外置观测降级方案准备，无需等待 owner 催办，但本节没有再次 POST GO。** 已有有效 Python 栈之后，遇到本次确切的解释器发现错误，可先即时重新验证固定 worker PID/starttime 与资源读取；成功才记录明确观测缺口并停止后续 dump，保持独立 guardian 存活、5 秒资源检查、原 45 分钟 POST 截止和原客户端产品终态判定。身份变化/未知、资源读取失败、guardian 失效、阈值或截止触发仍立即停止；其他未分类工具失败不通过通用 ignore 放行。首次有效栈仍为 POST 前提，不增加新 profiler、完整 canary 或全程重复取证。旧 e 结果始终 STOPPED，不能套用新规则改判。

该变更需要设计把“两个无效 dump 必停”的既定规则明确改为上述窄范围降级，再核固定外置脚本、状态日志及新 project/输入/镜像绑定；已触及被测对象的 r2 不能再套 DC68 一次重做。后续若需新单步执行，走 DC80 的新候选定向审核，不使用失败运行末态或重开旧项目。原 lease 根因保持 OPEN，正式测量仍停止。

已有栈与源码也提供有限的后续优化入口：`repository_ref.py` 每表已算 `mapped_columns`，逐行 `encode_repository_row` 又重新映射所有列；`import_publication.py` 逐 cell 重复解析不变 SQL 类型、逐 row 重复排序不变列集合。可据此准备循环不变量外提及小样本等价验证方案，保留原错误、schema/row 校验和 digest 语义，不建设全局缓存或提前跳过验证。但这不是本次停止原因，不应为下一单步诊断先捆绑产品优化、无限追求性能，亦不以采样数量推算其收益。

## 33. 采样降级设计范围通过；45 分钟预算保留

**范围 GO，无阻塞 finding。** 已读设计 `c74314cd40` 及收窄提交 `20490781ce` 的最终文本：两次均为 exit 1、非 timeout、固定解释器发现错误，才允许当场重核原 PID/starttime、文件系统和全部资源；通过后记录事实与观测缺口，停止后续 dump，独立 5 秒资源/身份守护、45 分钟截止、guardian 存活和产品轮询继续。未知/混合错误和 timeout 不通用降级，启动有效业务栈要求不变，关闭顺序保留。该范围与第 32 节一致，可直接继续外置工具及少量 CT05 定向验证准备，无需再问 owner；具体新单 POST 候选仍须核脚本、测试证据、固定摘要及身份后取得执行 GO。

仅基于现成证据，**没有足够依据认定 45 分钟明显不足，保持 2700 秒观察预算，不给完成 ETA。** 本次读取 `b6fb6255e8` 中既有 baseline handoff：已 PASS 的 CT108 2× core 项目 `p6b2xcore20261101b` 记录 S1/v1 Submit 1435.835 秒、S3/v2 Submit 1302.874 秒；相近 2× full-v2 首次运行的 v2 Submit 自然 SUCCEEDED 为 1312.992 秒，但整个旅程随后因 repository-read 工具核对失败，不能称该全旅程 PASS。这里引用既有 handoff 的已记录结果，没有重新运行测量或将其当作本次同输入/节点的直接性能基准。

当前 e 在约 1411 秒被观测规则截断，最后栈显示仍推进到 parent mutation 构造；它既不证明会在 2700 秒内完成，也不证明至少需要超过 2700 秒。上述历史运行与当前 CT05 的输入变更比例、冷热状态、镜像和节点不同，无法从历史倍数或采样阶段数可靠推算剩余时间。原业务轮询打印的 4055 秒 timeout 也只是另一个上限，不是实测最低完成时间，不能据此自动扩大独立诊断预算。H3 是 History 证据，整旅程 elapsed 包含其他步骤，均不拿来替代 Submit 完成时间。若新诊断真正触及 45 分钟，则保留截断事实，再据届时已有业务/资源证据给出具体处置；本次不预先扩预算或承诺会完成。

循环热点仅允许既有任务只读评估，不默认产品优化，也不作为工具修正或后续业务观察的前置。旧 e 仍为诊断工具中止；原 lease 根因、正式基准恢复资格保持未决。本轮只审文档与现存记录，未执行测试、采样或业务请求。

## 34. observer c 组件审核通过（不含 POST 授权）

**组件审核通过，无阻塞 finding；可直接装配完整的新单 POST 候选。** 设计通过通信探针 `P6LINK-20261106T035600Z-REVIEW` 转交 baseline handoff `7082fb2bd1`，审核已回显并直接告知设计代转实施者。本结论只绑定外置 observer 组件，不能把其 manifest 当成完整 POST 候选，也不复用旧单步 GO。

组件目录 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogobserver20261106c/candidate/`：

| 文件 | SHA256 |
| --- | --- |
| `candidate-manifest.json` | `9fc05f8d63518bc897d6fb07bf873024d51bcbfce177d1f4bec817cadfe4eb2d` |
| `submit_observer.py` | `0c8799a3aa29d13544009e5201ea1a8833c2ec629ca8dce8dfdfaef300857097` |
| `test_resources.py` | `3bf493361296d32b1827534d1ddeb27a7dd116fa1ca25e6931d23acc5b4f72a9` |
| `README.md` | `51e1a97d448c32b2e034698304df5e6ae72088f2d2f46c66a3f9422a46d34dc7` |
| `SHA256SUMS` | `aabcd5275d53263f9a1e276311d55de7a76a5f883d6d289da5b233e2782a304f` |

已直接核本地 SUMS 四项全部匹配，并经 BatchMode SSH 只读复核 CT05 的 observer、tests、manifest 相同。逐行比较原 `4912e954…0a662`：仅新增精确错误 classifier/常量并修改 `_guard`。已有 `WorkerObserver`、factory、有效启动栈、PID/starttime/文件系统读取、资源阈值、py-spy pin、2700 秒截止和 1/15/5 秒预算不变。两次失败都须 exit 1、非 timeout、固定文本加单个换行；有效 dump 清零连续失败，混合/未知/timeout 仍停。允许降级时明确再调用原 `read_resources` 并检查阈值；通过后只关闭后续 dump，记录两份失败及即时绑定/资源事实，guardian 继续资源循环和截止判断，不自动恢复采样。读不到、越限或其他守护异常仍停止。关闭分支仍优先处理并回收活动 dump/pipe。

审核读取 CT05 原始 `focused-tests.log`，2026-11-06 03:42:26Z，hostname `gw-dms-test-05`，起止 HEAD e798，**11 项通过，exit 0**；SHA `015a9fd6b069266c3d8285b15273e735a7455e66504a57f85aa346501dba5310`。测试覆盖精确分类、双错误降级、后续资源读取、降级后截止仍发 SIGINT、即时复核失败/越限、混合/未知/timeout、有效栈打断连续失败，以及关闭回收；另有真实轻量 `/proc` 与文件系统绑定检查。已静态读测试及其 fake clock/process 接线，不把模拟测试称为新产品现场运行。原始 transfer 日志 SHA `3d0824d3b6dd9384a5f2b21f9e775c3632a0f1b99b528f911e1bb48df691c04b` 记录 clean e798、固定解释器和 NODE_LOCK_ABSENT；错误字节核验日志 SHA `b163766de550c9f30af7c7d2d6f5fdf284ddb623382a8fd4ead0bd059d35275e` 对旧 94/95 两文件各 64 bytes 精确 MATCH。三份实际日志摘要与 handoff 相同。

a 的宽松匹配已被替代，b 的夹具失败和只读准备命令错误保留，不要求重跑通过的 c 测试。此轮未改仓库产品/包闭包，不要求无关五包静态或权威 runner；审核未运行任何测试、采样、服务或请求。下一步只需将此 observer 精确 pin 纳入新 project/key/证据目录的完整 launcher/shell/manifest，核其相对已审版本的必要接线和固定来源/目标，再给一次新候选执行决定。45 分钟与正式停止边界沿第 33 节。

## 35. 完整 f 候选审核与一次单步 Submit GO

**明确 GO：允许原实施者按 f README 的固定命令，在 CT05 执行一次 `p6catalogsubmit20261106f` 单步 Submit 诊断。** 审核主动读取原实施会话的正常回复和本地完整候选，已通过可用 TUI 直发实施者并抄送设计；无需等待实施者外发接口恢复、owner 或本报告提交回执。这是 DC80 下新候选的执行决定，不是再次套用 DC68，不续用旧 e 的运行卷或 GO。

完整候选根目录 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogsubmit20261106f/`：

| 文件 | SHA256 |
| --- | --- |
| `candidate-manifest.json` | `93eade9a4689d623a103b8fa96f879a0fe18d61c02007e9f6b9c7ef49e21e01c` |
| `candidate/submit_diagnostic_launcher.py` | `d6f60276bd741e10913b891f491264ec36bacb8fe37911a88c79061dad2056d5` |
| `candidate/run-once.sh` | `d00f2d1c73636d9aba4932121d5a958b217db72aa7ec46f41872693d7703f4e5` |
| `candidate/README.md` | `bd8b37bcc2fe1d2a36260701d313b2dc4843a93e99f02d7d277653497fe0a3bc` |
| `candidate/SHA256SUMS` | `6451e4eb47fadcae9c0a8f40ce9aace1c72976b7b097dc75a692acdbcd99e16c` |

manifest 八个候选文件大小和摘要逐项 MATCH，SUMS 七项 MATCH，shell ENTRY pin 与最终 launcher 相同；observer `0c8799a3…857097` 及复制的组件 manifest `9fc05f8d…eb2d` 与第 34 节通过对象完全相同。来源 readout 与目标 RS identity 文件未变。准备日志 SHA `69b43e633987fea20a4e4f1d2d7ca61d7cdd92bfa94887451a86f32a1549b2c8`，差异核对日志 SHA `9dbe35530a4adb2b44e94ae637dd54bb09f38c52ca08a78c243445b3ed2d04ab`，实际摘要均匹配 manifest；记录仅静态语法/AST/固定绑定检查，候选尚未执行，不重复组件测试。

审核直接比较 e→f 最终文件：launcher 只换新 project/目录/token，把 observer pin 和实际 `load_module` 路径同时改为候选内已审组件，并固定组件 manifest 摘要；shell 只换新项目/路径/token 和 ENTRY pin。准备稿中的额外运行时解析/SUMS 步骤已在封存前移除，最终无此变化。原 repo-root→backend cwd 接线、源 checkpoint/input/cache 校验、e798 backend/worker 与 4497 RS config/全部 DiffID、源 RS UNAVAILABLE 说明、F1 单 POST、sampler、收尾及锁规则不变。没有产品改动或预算扩大。

执行入口为 README 中 `ssh -o BatchMode=yes ct108-gw-dms-05 'cd /home/dev/gdds-prepare-import-e798-05/vnext/backend && /bin/bash /home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogsubmit20261106f/candidate/run-once.sh'`。执行前按原规则确认节点空闲，经 LAN 同步并复核固定摘要，由 shell 自取锁；仅原 pre-submit checkpoint 的独立目标三卷/新 key，一次 v2-submit POST，不做 Preview、预热、后续步骤、自动恢复或失败重跑。保留原 2700 秒 POST guardian、5 秒身份/资源守护、必要停止条件；精确已知双 dump 错误才按第 34 节即时复核后停采，出现降级须如实记录后续栈缺口。

失败即停留证，不自动再次执行；未知收束状态保锁，已确认静止后按脚本释放，卷和旧证据保留。交回真实 exit、独立结果、run/state/input 比较、observer/资源、Compose 及 cleanup/postflight/锁状态与 SHA。后续正常回复可由审核/设计直接读取，不将消息无法外发当成继续等待的理由。单步结果不自动恢复正式测量，也不预判原 lease 根因。审核本轮只读候选与现存证据并提交本报告，未运行候选、测试、容器或业务请求。

## 36. f 结果复核：先失去 lease，后触发 stall；根因继续定向定位

**确认产品 worker 已发出 lease_lost；约 89 秒后 journey 的 120 秒无心跳规则触发 WorkerStalledFailure。** 不能把本次仅写作可选观察器失效或仅工具误报，也不能把这一事件直接等同完整 Submit operation 已返回 FAILED。审核收到设计转交 `f768d68f67d1ad071b90145c8ce66b45f3e768e2` 后，只读 CT05 已存日志、observer、stall 文件及冻结 e798 源码，未重新查询服务/DB、扫描业务卷、取新栈或运行测试。第 35 节一次 GO 已用完。

项目 f 的 launch/controller/preflight/resources/provenance/run/state/独立结果/postflight/cleanup/observer events/stack 0131/Compose 共 13 项实际 SHA256 与 handoff 全部一致。关键时间线（UTC）：

| 时间 | 已存证据 |
| --- | --- |
| 04:12:15.083 | v2-submit step 开始；observer 已有效启动并 arm |
| 04:12:17.486053247 | 唯一 Submit POST 返回 HTTP 202，operation `op-c8a03f307842b1d97d65b7b9` |
| 04:42:58.287417 | 已存 selected control rows 的最后 step updated_at；lease_expires_at 为 04:43:28.287417 |
| 04:42:58.403570249 | 最后一次 heartbeat_succeeded，共 176 次 |
| 04:43:31.053992336 | Compose 明确记录 `code=lease_lost`、`error_category=heartbeat_busy_deadline`，同 operation/step |
| 04:44:47 | 最后有效 Python 栈：主线程在 worker_runtime:319 异常分支 join，执行线程仍做 change-set digest |
| 04:44:56 | 最后资源/原 PID-starttime 核验成功，未触阈值 |
| 04:44:59.050 / .692 | stall capture / worker_stalled 事件，监视器 observed_stalled_seconds=120.647 |
| 04:44:59.955 | step_failed，wall 1964.872 秒；随后固定收尾，run 于 04:48:05.143 结束 |

监视器的 120.647 秒是其追踪时钟的观测值，不把它改写成两个日志 UTC 的精确差。observer 本次 131 次 dump、129 次有效；仅第 38/60 次无效且不连续，没有 `stack_observation_degraded`、observer stop 或 2700 秒截止事件，不能归因于本轮降级修订。绑定 worker PID `2103940`、starttime `194809474`，既有资源 reader 每次验证身份，记录持续至 04:44:56Z。末次 RSS 23,867,850,752 bytes、host available 43,245,912,064 bytes、data free 217,919,131,648 bytes；全程 RSS 峰值 25,055,125,504 bytes、available 最低 42,059,630,592 bytes、data free 最低 217,900,478,464 bytes，均未触资源停止线。handoff 所列 available 43,246,160,896 实际属于 04:44:51Z，不改变资源结论。

stall 保存的 worker inspect 为 running、PID 相同、OOMKilled=false、RestartCount=0；48 个线程的 wchan 中 47 为 futex_do_wait、1 为 0。futex 等待和单份 active+gil 栈本身不证明 deadlock 或长期独占 GIL。已保存 selected control rows 为 operation/prepare_import step RUNNING、attempt 1、step optimistic_version 177，Repository operation id 尚为空，未到 R5 对账。它同时保存最后 lease 的 30 秒期限，与 lease_lost 发生在期限之后一致。保留取证限制：`diagnostic-errors.txt` 有 `control DB snapshot: JourneyFailure`，因此不能称完整 control snapshot 成功；已有 selected rows 仍独立列证。旧 stall collector 的 `py-spy-unavailable.txt` 只表示其按 PATH 未找到工具，不否定外置 observer 已用固定绝对路径保存的有效栈。

**源码归因边界。** `WorkerRuntime._heartbeat_until_due` 在调用 `session.heartbeat()` 前发现 `now >= lease_deadline`，同样会经 `_fence_lease_for_busy_budget` 发 `heartbeat_busy_deadline`；该标签不专指 SQLite busy 重试。本次已存日志没有 `code=heartbeat_busy`，故没有证据把丢租约归因为 DB 写锁竞争。`LeaseSession.heartbeat` 以事务时间续租，runtime 保守使用调用前 monotonic anchor 计算下一次心跳/期限；不能未经证明就改成调用返回时间或扩大 TTL。丢租约后 `_run_claim` 的异常路径先 join 执行线程，后续不再心跳；第 126–131 栈与这条路径一致，解释了之后持续无心跳，但没有解释最初为何错过续租期限。

第 117–122 栈显示执行线程在 JCS serialization/Unicode 校验，第 123–125 栈在 `change_set_mutations_payload` → `ChangeSetMutation.to_document` → `PersistedRowImage.to_document` 构造整份 change-set 载荷，主线程仍在 Event.wait；第 126 起主线程转入 join，执行线程继续全量 Unicode/digest 计算。调用链是 `_changeset.build_change_set_closure` 先算 digest，随后 `ChangeSetClosure.__post_init__` 再构造 `ChangeSetArtifact`，其校验重新计算 digest；之后还有 closure digest。这里存在重复的全量载荷构造与遍历，且和失租约窗口重叠，是应优先定位的有限代码区域。**这些离散栈不能独立证明 GIL 饥饿、GC 停顿、具体调度延迟或哪次分配是根因**；当前只确认与原 CT108 相同的 lease_lost/error_category 症状再次发生，原根因仍 OPEN。

最小下一步建议按 DC80 直接组织定向定位，无需再跑完整 Submit 来采同类栈：复用 `test_operation_worker_scheduler.py`、`test_operation_lease_session.py` 和现有 mutation planning fixture，在 CT05 准备一个受限的纯内存 change-set 工作负载及必要临时 control DB，用现有 worker/LeaseSession 复现续租调度；记录少量 heartbeat 入口/返回 monotonic anchor、DB lease 时间与载荷构造/校验/序列化子段。若需要区分 GC/调度停顿，仅在该局部诊断内加短期观测，不扩为产品常驻 profiler 或新监控框架。既有 fake-clock 测试已覆盖 busy budget 与 observer 延迟，不需要重复证明旧分支；应针对“无 busy 事件而错过 deadline”的新证据缺口。定向代码和验证方案交设计/审核后执行，本审核没有运行这些测试。

修复边界优先是已定位的重复整份载荷/不可中断计算及其与心跳调度的关系，方案必须保持完整 mutations、JCS 字节、digest、Contract 错误边界和 CAS/lease fencing。不能为了减少遍历直接删掉外部输入/载荷完整性校验；如采用复用或增量计算，须用小样本字节/digest 与异常等价验证。若只加失租约后的协作取消，可减少 join 等待，但不能称已修复最初丢租约。不得先加大 TTL、heartbeat/stall/45 分钟预算、删除 join/fencing，或直接引入独立服务/进程隔离；也不把之前逐列映射优化捆绑为必做。先区分因果，再给最小修复候选。

收尾结论仍成立：独立结果 post_count=1、STOPPED、submit_completed=false；runner 1，cleanup/postflight 0，输入/state 双 MATCH 只证明来源，目标容器/network 空，三卷保留，controller 记录释放锁。没有新运行授权，正式测量继续停止。

| 定向复核新增/关键证据（f 项目根目录下） | SHA256 |
| --- | --- |
| `compose/real-dump-t4-20261106T044500146057Z.compose.log` | `730470050a084fef462142ea9521512e769ec16ebf6d515882b21cdbf4c25c21` |
| `evidence/observer/observer-events.jsonl` | `6282fd49c3c904deff255e7294bf604afe6017454d90a2738fb9618925a17cc0` |
| `evidence/observer/worker-stack-0131.txt` | `71bfb7ab3818b66b5c7a5d629b291cd9a78275f424b3afaaa9563b58bfe3df61` |
| `s4-stall-20261106T044459050676Z/stall.json` | `d4f360e0c70dc1663396fe19a903d8c493fae27c4f93cfa5ad10d28d09d20039` |
| `s4-stall-20261106T044459050676Z/control-db-selected-rows.json` | `28519cb557bba6a0fec2ff16900219a21250f75154c5035da512da475c7ccc48` |
| `s4-stall-20261106T044459050676Z/docker-inspect-worker.json` | `b461c3c7495bb8d684fb604959a15584fb900adb1a4ae783e6c65b09f50ff05c` |

## 37. change-set/heartbeat 局部 probe 设计范围通过

**范围 GO，无阻塞 finding；可直接准备固定外置工具，尚无 probe 执行 GO。** 已核设计 `55fa70a489` 的 `p6-change-set-heartbeat-probe-plan.md`，与第 36 节因果定位建议一致。本轮只读设计和 e798 既有 scheduler fixture，未运行测试或新取证；已直接将范围结论发设计，由其交原实施者准备。

固定为 CT05 clean e798、真实 Thread/Event/monotonic/UTC、原 10 秒 heartbeat/30 秒 lease，复用现有内存 Store/UOW 与 LeaseSession。单 case 的具体 mutations 数量/构成/生成规则须在候选固定，最多 20,000×33 列、字符串最多 64 UTF-8 bytes；一次真实 compute，构造至线程退出共 120 秒、RSS 2 GiB，独立外层每 200ms 核 PID/starttime/RSS，截断后终止回收且不加规模重试。不启动 DB、Dolt、HTTP 或完整旅程。GC/阶段记录有界聚合且无回调 I/O，不能替换真实计算；输入构造、返回/释放和正常/异常 join 都计入观察与总预算。

具体接线审核应注意已有 fixture 不是现成真实时钟模型：`RuntimeUowFactory` 默认用 BASE_TIME 加调用次数，`_active_records` 初始 lease 为 BASE_TIME+300 秒，`ThreadFactory` 返回 ControlledThread。候选须按设计替换这些时钟/初始 lease/线程接线，使用真实 UTC 事务时间和 30 秒初始 lease，并保留原 fence/安全 handoff；不能仅把外层 sleep 换成真时间就宣称真实续租关系。内存 UOW 的结果明确不覆盖 SQLite，短于一次心跳则只报告未覆盖，不额外等待或重复计算。这些是既定设计要求的实现核点，不增加新测试矩阵。

现有 20,000 行/2 GiB 上限与现场约 24 GB 不同；结果不能外推唯一根因或产品性能，也不自动授权产品修正或 Submit。逐 mutation canonicalize/hash 的错误顺序不等价风险已明确，后续若采用 writer/hash sink 须另核原 JCS 字节、digest、全局校验顺序和完整 payload 的边界。本次只准备定向诊断，不捆绑流式化、Rust 迁移、租约调整或重复 closure 校验删除。固定 harness/监督命令/manifest 齐备后再给候选执行决定。

## 38. 局部 probe a 执行候选审核：两项定向修订，暂不 GO

P6-PROBE-0600 接续纠偏后，实际读取 `p6heartbeatprobe20261106a/candidate/` 的 `probe.py`、`supervisor.py`、`run-once.sh`、README、manifest 和准备记录，并对照冻结 e798 的 WorkerRuntime、scheduler fixture 与 digest 实现。此前误接续 S1b 的答复不构成本 probe 的审核或授权。本次没有执行 probe、测试、服务或远程取证。

审核对象为 handoff `7dd555db330346c0fff1cc0f2c8779fdfd77e0e9`，manifest SHA256 **`a856913c022cef966e04618f2355771ae1a4393e7f3fe5d4ef969a80a607de48`**。实际文件摘要与 manifest 全部一致：probe `8d22265ac2474c78dd1e870afec1d137e5c7c2d29723ea2ebe0b4b8befe9cfc8`，supervisor `3697e085c8897981fe7aca704d76128a716627ce749f13839ca925b6e99449a9`，launcher `14ed0c778518062d8f2775cb9a91925343af6e49e968085ead609922e0a91d1d`。

已满足的接线：固定 CT05 clean e798 与绝对 venv 解释器，真实 Thread/Event/monotonic/UTC，初始 30 秒 lease 与 10 秒 heartbeat，原 LeaseSession 和 checkpoint/safe-handoff；UPDATE 后 INSERT 的 20,000 项顺序符合原 Contract，每行 33 列、字符串不超过 64 bytes。只调用一次真实 digest，各 wrapper 委托原函数，无算法替换。GC 聚合加最多 64 个窗口且 callback 不做 I/O。外层独立进程正常路径按 200 ms 采样 PID/starttime/RSS，117 秒停止留出 120 秒总预算，2 GiB 阈值；GO 文件绑定 manifest，持久 attempt marker 阻止自动重跑。这些不需要重新设计或重复范围确认。

### P1：异常与截断路径丢失本次定位需要的观测

`probe.py:240–256` 仅在 `_heartbeat_until_due` 正常返回后保存 handler 入口、deadline 和结果。实际目标分支是父实现先发现 `now >= lease_deadline`、发 lease_lost 并抛 StoreBusy；此时这个 handler 完全不入结果。`probe.py:351–367` 同样只在 runtime 正常返回后挂入局部 worker events，故异常时连已产生的 lease_lost/error_category 都丢失。digest 子段 metrics 也只在成功后挂入 observed。

此外，子段只记 calls/total/max，没有 monotonic 起止窗口；JCS 同时覆盖 20,000 次 key canonicalization 和最后全量文档，不能据这些累计数与 GC/heartbeat 窗口对齐。脚本没有 process CPU 观测，也没有正常/异常 join 的时间边界。最终 JSON 只在所有工作结束后写出；若 supervisor 按设计截断，已完成的构造、heartbeat、phase 记录仍全在子进程内存中，无法留存。

最小关闭要求：先将共享有界记录挂入结果，handler/runtime/digest 的异常结束用 finally 保留入口、deadline、异常类别与结束；对粗粒度构造、ordering、payload、完整 JCS、hash、释放、线程退出/join 记录有界 monotonic 窗口和 process CPU。key JCS 保持聚合并与完整 payload 阶段区分，不逐 key/cell 输出。关键粗粒度边界低频保存已完成记录，使截断至少保留最后已保存边界；GC callback 仍只更新有界内存聚合，不做 I/O，不为保存 GC 内部数据新增常驻监控。明确最后未保存窗口及原生调用内部仍不可见，不把差额冒充精确类型检查耗时。

### P2：监督进程中断可留下脱离监督的子进程并提前释放占用

`supervisor.py:132–194` 创建 `start_new_session=True` 的 child 后没有覆盖监督生命周期的 try/finally，也没有 SIGTERM/INT 的回收处理。监督进程收到终止信号或 KeyboardInterrupt 时，子进程不随原进程组退出；外层 launcher 随后执行 EXIT cleanup 释放节点锁，剩余 probe 却没有 117 秒监督。另 `_stop_process` 在 SIGKILL 后 wait 超时返回 `None`，调用方仍退出并释放锁，没有明确“未回收”处置。这里是当前标准子进程管理缺口，不涉及新产品生命周期或同 euid 恶意行为模型。

最小关闭要求：在外层监督的信号/异常路径统一进入有界 terminate/kill/reap，保存停止原因与回收结果；launcher 的退出处理配合监督进程，只有确认 probe 已退出才释放节点占用。若预算内仍无法确认退出，明确标记未回收并保留占用供人工处理，不宣称成功回收、不自动重试。保持 120 秒总预算与现有单次范围，不引入新服务或产品机制。

两项已直接发原实施者并抄设计。**该 manifest 暂无执行 GO**；修正后更新固定候选及摘要，复核这两项即可。正式测量与新的 Submit 仍未获授权。

## 39. P6-PROBE-R2：修订候选单次执行 GO

**执行 GO，仅绑定 `p6heartbeatprobe20261106a` 的 manifest SHA256 `c5163458bf7c289fb6ea7f16c45ef83dff07aa4d4e48528028de3f3a92ceb548`**，handoff `33415389a19659fc95228ebe2dfb209cb0e219e4`。旧 `a856913c…`、`db28ecde…` 不获授权。本次实际重读三份脚本、README、manifest 与 handoff 修订，未执行 probe 或测试，未扩大原范围。

实际摘要均匹配：probe `7323f8d107c0addade28c406372d0107d0910584d87539470ffa86f9dcccb00d`，supervisor `2667611a048988282a9e80c59556d065f7b20f57bed386808882c794ea11e042`，launcher `ab2af167e529b5a0ce13f34848b290ebf766d77b502a43e8bf8d603535d6b8c5`，README `6933c797ae824a3f584521971978dc80b5a553f6bfdea0bce29141a1bfbae981`，checksum list `78056a96fb2e57007f38e33e8bcd91812d39f0e82eeea285abb24bafaf28ef96`。

P1 的阻塞部分已关闭：worker events、digest metrics 先挂入共享结果，heartbeat handler 在调用前记入口/deadline，异常和正常结束均由 finally 补齐并保存。构造、digest、释放、handoff、runtime 有 monotonic 窗口与 process/thread CPU；子段有聚合与最多 32 个不短于 5 ms 的窗口，截断/丢弃计数显式保留。最多 48 份粗粒度边界 checkpoint 和 latest 文件保留已完成观察，GC callback 仍无 I/O，写失败进入结果且最终非零退出。没有修改原 digest 或 worker 的判断逻辑。

P2 已关闭：监督的 SIGINT/SIGTERM 记录停止意图，监视循环退出后与异常共用 finally；TERM 0.5 秒、KILL/reap 最多 2 秒，共用从启动起 119.5 秒的绝对 child 截止，原 117 秒 stop guard 与 120 秒预算不变。明确输出 child_started/child_reaped/return_code；未回收或结果缺失时 launcher 保留节点占用，仅确认 reaped 才释放。无法确认退出的情况保留人工处置，不自动再起 probe。

接受为本次诊断限制而不扩修订矩阵：没有独立 join 起止探针，只有真实 runtime 退出（包含 join）及 executor 的 handoff 边界，不能推算精确 join 耗时；key JCS 与全量 JCS 共用子段聚合，解释保留窗口时须按 ordering/payload 的时间边界区分，不能把累计时长当纯全量 JCS。GC 只保留前 64 个窗口，truncated 后不能以无匹配窗口排除 GC。checkpoint 序列化/fsync 在两个线程中执行，heartbeat handler 入口还先保存再委托产品逻辑，因此观测本身会影响调度；即使出现迟滞也须保留这一替代解释，不能直接认定原产品根因。README 对 per-row raw digest 的表述不应扩读为产品调用语义；本 probe 的 Contract digest 仍是一次完整 mutations 包装对象计算。

已直接向原实施者发送绑定上述 SHA 的一次 GO 并抄设计：按既有 SSH、单飞和 clean e798 前提传输、校验后运行，固定 venv，20,000 项/33 列/64 bytes、一次 compute、10/30 秒与 2 GiB/200 ms 均保持。无心跳仅报未覆盖；失败、截断或完成都不自动重试/扩规模。未授权 Submit、产品修复或正式测量；本次不是 DC68 重做。后续只审本次实际结果及收尾，不等待实施者不存在的外发工具。

## 40. P6-PROBE-RESULT：单次局部诊断完成，现场 lease 根因仍 OPEN

**证据复核通过；第 39 节 GO 已消耗，没有新的运行授权。** 只读 handoff `22251147a8`、本机 `p6heartbeatprobe20261106a/ct05-run-evidence-r2/` 和既有 transfer/preflight/GO/postflight/summary 日志，没有重新访问节点、服务或卷，没有执行测试/probe。清单中的 stdout、stderr、supervisor、12 个编号 checkpoint 与 latest 共 16 项本机副本 SHA256 全部匹配；清单自身 `7069645f82929718b66a5b9c8684ca2c739b4e1f3aa9ce1545f4b1f7baec9615`，summary `ad510284301348560fca6d6aad889c5784f8bbcd1d7a696d330c0061f9b6f2c7` 与 handoff 一致。

CT05 于 2026-11-06 06:37:59–06:38:14 UTC 执行唯一候选，transfer/GO 文件绑定 manifest `c5163458…`。launcher 起止 e798、固定 backend cwd 与字面 venv 解释器，候选 checksum 全 OK，probe exit 0；postflight 确认 clean、HEAD 不变、节点锁 ABSENT、attempt marker PRESENT。第一次预检 shell 引号错误日志保留，修正后预检一次通过，发生在 probe 启动之前。该错误不构成第二次 probe。

probe `completed`、error null，child 耗时 **14.094292s**；supervisor `completed`、child exit 0、reaped=true、无 signal/forced termination，总耗时 **14.416423s**。PID `2395233`、starttime `195684268`；72 次初始采样后的检查，峰值 RSS **688,930,816 bytes**，未达 2 GiB。20,000 个 mutations 的真实 digest 调用恰一次，结果 `sha256:5aadf7311ded1b922275c788d9e8cd5016abbd0dc220d464770481c0215b98c4`。输入构造 1.641744s、digest 11.715115s、引用释放 0.069598s、safe handoff 0.000205s；runtime 13.485678s。checkpoint 写入错误为 0，stderr 为空，最终 safe_handoff、drain_started、worker_exited 均记录。没有验证监督的异常/强杀分支，本次正常退出不能写成这些分支的运行覆盖。

**确实跨过一次真实续租。** handler 入口 monotonic 1956853.311818807，旧 deadline 1956873.306596258；按固定 30/10 秒设置反推首次 due 为 1956853.306596258，入口晚约 **5.223ms**。handler 入口至 heartbeat attempt 约 **96.719ms**，该区间包含 checkpoint 保存和调度扰动，不是 DB/lease 调用耗时。renewal anchor 1956853.408533628 至 attempt 约 **4.030µs**；heartbeat attempt 本身 **0.215ms**。内存事务 UTC 06:38:10.431807，更新期限 06:38:40.431807，严格 30 秒；anchor 尚早于旧 deadline **19.898s**。没有 heartbeat_busy、lease_lost 或 executor_failed。上述 UTC/monotonic 数据不能跨时钟直接相减来宣称精确 anchor→事务耗时。

完整 payload 的 Unicode 窗口约 **5.147s**、数值校验 **0.620s**、JCS serialization **4.104s**，唯一 heartbeat 的入口/调用都落在 serialization 窗口内。因此该规模下序列化与 worker 心跳可以交错，不能把“单次 digest 总耗时超过 heartbeat 间隔”本身当作必然失租约证据。ordering 0.558s 包含 key JCS；JCS 各项共 20,001 次调用，累计数与排序有重叠，不能直接相加。raw hash 只有 **1 次**、约 0.043s，也澄清候选 README 中 per-row raw digest 的不准确说明。

GC 聚合为 gen0/1/2 各 1385/126/8 次，累计约 0.073/0.107/1.267s，最大单次约 0.000293/0.002434/**0.308437s**。`gc_truncated=true`；实际保存的前 64 个窗口位于 monotonic 1956842.739381962–1956843.193520476，**全部早于 worker 开始 1956843.306580128**，不能用这些窗口定位 digest 内 GC。全程聚合也不能确定最大停顿属于哪个阶段。join 没有独立计时，checkpoint I/O 和 instrumentation 扰动仍在；这些限制与小内存、合成共享值、仅一次 digest、内存 UOW 的边界一起保留。

本次证明固定小样本完成并正常续租，**不证明现场约 24 GB 堆、完整 closure 重复计算或 SQLite 场景不再失租约**，不关闭第 36 节产品问题，也不改变 H3/正式测量停止状态。保留 candidate、GO、attempt marker、证据与收尾状态，不重跑或扩大输入。

最小下一步建议已直发实施者并抄设计：在现有 e798 源码和本次数据上，先只读列出完整 closure 调用链的 digest 次数、整份 payload/serialized bytes 的创建和存活边界，区分可消除的临时分配与必须保留的 Contract 校验；据此提出一个最小候选。可评估原全树 Unicode/数值校验之后使用 JCS writer→hash sink 消除完整 bytes，但必须保留原包装前像、字节/digest、错误类别和全局优先顺序，且明确它仍保留 payload 图、不能承诺解决 lease 根因。不要直接删重复验证、逐 mutation 改校验顺序、调整 TTL，或以小样本成功触发新一轮完整 Submit。设计明确方案及必要等价验证后再审具体修复；本报告不自动授权该修复或新测量。

关键原始摘要：stdout `9dbbe466394bcfbc4145803a98d7464955471dc7a7d53b9270e7ad837c10e54a`；supervisor `ee8b01d754777d463a56e7e779d6bd4c7c2d3b472e87402d3d95dfcdba62d5c8`；launcher `0aeed61c4ec544b3fc5a32e3ace00e9ac19d7733dcac5e63b9d05814da4b93d2`；postflight `bf763ca1d2dc6ac71338867be9aecc5bbee80f91c503993fe136f86c752e1335`。

## 41. JCS hash sink 分配削减设计：范围通过

**设计 `f02515b95a5d3ba52d700745f0508d57d7aac7bd` 范围通过，无阻塞 finding。** 定向核对 `p6-change-set-heartbeat-probe-plan.md` 新增结果、完整 closure 分配链、单一候选和验证边界；复用前述只读分析，没有重新调查、测试或取证。结论已直接发送设计，由设计按该文档分配明确实施责任；本节不是产品候选通过或运行 GO。

该方案准确区分可消除的完整 JCS 输出 bytes 与仍保留的 mutations/payload 图、排序及序列化器自身分配；不把顺序发生的三次 payload 峰值相加，不把省去输出聚合等同有界总内存或 lease 修复。shared_kernel 持有共用的原全树 Unicode→数值校验及固定 rfc8785 writer/异常映射；新摘要入口使用私有至多 64 KiB 的合并缓冲，大块直接 hash，成功才返回 DigestRef。原 bytes API 留给需要 bytes 的消费者，两个指定 digest consumer 不做运行时 fallback。这符合职责边界，没有新编码器、兼容层或依赖升级。

backend 改动仅限 `compute_change_set_digest` 与 `compute_change_set_closure_digest`；前像包装、完整 payload 构造、排序及 artifact/closure 再次验证不变。原全局校验优先级和 payload 构造先于 JCS 的边界已明确，因此没有采用会改变跨 mutation 错误顺序的逐条流式方案。实际 writer 签名、write 返回语义及原异常映射仍须在实现时核实，不能由设计文本替代具体代码审核。

验证范围适当：shared_kernel 单一 owner 负责现有公开 bytes/golden 对应的摘要、Unicode/数值/序列化错误优先级及 buffer 边界；backend 负责真实 change-set/closure 的绑定、错误摘要拒绝和代表性跨 mutation 语义，不重复共享层矩阵，不引入 Dolt。只计划专用节点 clean 提交上的一次限域 focused 和五包静态检查；镜像和恢复门禁留到必要候选另行绑定，不据此宣称镜像通过。

既有 probe GO 已用完，文件与计时不作新旧性能对照；现场 lease 根因继续 OPEN。范围结论不授权新 probe、Submit、正式测量、放宽租约或省略校验，也不要求重新跑已完成的调查。后续审核以该精确范围内的实际实现和必要等价证据为对象。

## 42. JCS hash sink 候选：代码与局部语义证据通过

**代码候选 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 通过本次独立代码与局部证据审核，无阻塞 finding。** handoff `172d53cfebeb1a6dc6ae1ea4068483b129285e70` 仅增交接文档；审核区间 `eaf247c67af4c23de9aa333f07acc5e8f2ab0590..1f9731dfc3`，基点为 e798 加既有 RS 修正。本地创建 detached 审核 worktree `/home/dev/gdds-p6-jcs-sink-review-1f9731` 并链接 legacy，在其中只读审五文件增量及相关原实现，没有运行测试或改产品。本轮报告之外未修改 main 的其他工作。

shared_kernel 的 bytes 与 digest API 共用 `_write_canonical_json`，仍依次全树 Unicode、全树数值、原 serializer；异常映射的三条分支没有改变。新入口只在全部 writer 输出成功后返回 `DigestRef.from_raw_digest`，无 domain prefix、fallback 或部分摘要返回。backend 仅切换 change-set 与 closure 两处消费，完整前像、payload 构造、排序及 artifact/closure 重复校验均保留。公开 bytes consumer 仍取得原 bytes 语义。

`_HashSink` 只分配固定 65,536-byte bytearray；小块在容量不足时先 flush，大于等于容量的块直接 hash，尾块最终 flush。有效长度始终受容量约束，slice 写入长度与替换范围相等，不增大 bytearray；flush 使用短期 memoryview，没有再聚合整份输出。调用标准 SHA-256 并按原 DigestRef 格式返回。该结论仅限新增 sink buffer，不包括 payload/字符串/原库内部拷贝，不是实测整体内存峰值。

固定依赖已独立核实：读取本机已有 `rfc8785` 0.1.4 的 `_impl.py`，实际 SHA256 `c25bc3a046528482d53bee3487b837f31dd9c05f33e8f13288c7aab320932cec` 与 CT05 closeout 一致。`dumps` 正是 BytesIO→dump→getvalue；dump 及其字符串/浮点 helper 只调用 write(bytes)，不使用其他 IO 方法。因此私有窄 Protocol 到第三方 IO 类型的一处 cast 有实际来源支持，没有替换编码规则。候选未改依赖或 golden。

测试对照具有独立依据：成功样本以原 `rfc8785.dumps` 输出 bytes 为参照，覆盖 Unicode/转义/UTF-16 键序/数字与缓冲边界；故障表核对全树 Unicode 优先于前部数字、数字优先于 serialization 失败，及 tuple 进入原库错误映射的 code/message/cause。后部 unsupported value 亦验证部分写出后不返回摘要。一个混合小块/大块/尾块测试核缓冲上限和总摘要。backend 的真实 DELETE/UPDATE/INSERT 前像与 closure 绑定、错误摘要拒绝及跨 mutation 错误优先级由相应测试覆盖，没有扩为重复矩阵或 Dolt fixture。

读取 CT05 回传的原始日志而不重跑：2026-11-06 06:55:02–06:55:05 UTC，shared_kernel 三文件 **172 passed**，backend mutation contracts **19 passed**，exit 0；06:55:31–06:55:36 五包 Ruff/mypy 全通过、exit 0，起止 HEAD 均为候选，五锁前后摘要一致。日志记录本机预置缓存/offline/no proxy；handoff 记录 clean 提交、局域网 bundle、专用 TMPDIR。closeout 06:56:14 记录自有节点锁释放、无任务进程/容器，并核 native 扩展 tree `58436908aee9dd449f4d3e0542a6a8c1920b6d5e` 与源码一致。三份日志实际 SHA 与 handoff 全匹配：

| `/home/dev/gdds-p6-logs/change-set-jcs-writer-20261106/` 文件 | SHA256 |
| --- | --- |
| `focused-1f9731dfc3.log` | `70aeda0bbcab35dbdcef1fa02711873fa2669a8b27a2e3ca947ec846c054f629` |
| `static-1f9731dfc3.log` | `c65d7b3248432c7e3cca5636fe22f013aaf00176430907c33caf1b5258fa75a0` |
| `closeout.log` | `d6bf9b5013758a2c07dc8343b9bbc508dadb4f1a32114f22a56f38c6c8c5fae6` |

**通过的只是该候选代码与局部语义证据。** 没有新旧分配/速度对照，不以旧 probe 14 秒作改进基线；现场大堆 lease 根因仍 OPEN。当前未触容器专属接线，本轮按设计先做内部逻辑验证，镜像构建/容器及正式恢复门禁延期至下一份明确候选流程；没有此候选新的 image revision/source-tree 验证，旧 e798/RS 镜像不得称为本候选已通过或 carried。未授权合 main/baseline、推送、重跑 probe、Submit 或正式测量。已将结论直发设计供其转既有实施任务；新增审核 worktree 保留供后续清理。

## 43. 完整 closure 局部诊断：设计范围通过

**设计 `c5373a359a6e78bb640a6cdc3cda8db7bac6c354` 范围通过，无阻塞 finding；可准备新候选，尚无执行 GO。** 实际读取 `p6-change-set-closure-probe-plan.md`，复用第 36–42 节代码/结果，不新取证、调查或测试。结论已直接发送设计，由其交原实施者准备新目录、harness、manifest 和一次性命令，不再等待范围确认。

本次选择在已审 `1f9731dfc3` 上观察完整产品 closure 链，优先于另做旧/新小样本性能对照，理由是当前缺口在重复 payload/释放/GC 与续租的关系，省去完整输出 bytes 的结构事实已核实。实际 builder 只调用一次，由合法 request/plan/decision/snapshot 生成恰 50,000 UPDATE + 50,000 INSERT，每个 after-image 33 列、字符串至多 64 UTF-8 bytes；不靠手工三次 compute 或无关填充堆伪造链路。候选审核须看生成规则、前后数据/row digest/manifest 绑定和实际调用计数，不能只接受 manifest 的期望数。

300 秒全程上限、290 秒停止、RSS 8 GiB、独立 200 ms PID/starttime/资源监督具有明确边界，包含导入、fixture 构造、全部计算、handoff、引用释放和线程退出。184 秒/3.45 GB 仅是以旧样本做的预算估算；新链额外 snapshots/校验和非线性 GC 都可能导致截断，截断允许且不追加预算。启动 host available 至少 16 GiB、运行低于 4 GiB 停；证据盘 1 GiB 启动、512 MiB 停，与节点单飞/有效占用前提并用。实际脚本仍须对必要指标不可读停止，TERM/KILL/reap 共用截止，未确认回收保留锁。

观测修正适合本次问题：heartbeat 前不保存/fsync，heartbeat/GC 只写有界内存；业务粗边界低频保存并计开销。GC 全程聚合加最近 128/最长 32 窗口，不再只留导入期前 64；阶段、事件和 checkpoint 均有数量上限及丢弃/覆盖/写失败记录。按真实顺序区分多次 payload/change-set/closure digest，逐 key JCS 只聚合并与全图阶段区分，适配新共享 writer；委托原实现，不变更校验和异常顺序。无法隔离的释放/join 与未保存的硬截断窗口明确缺口，不做差额推算。

原 10/30 秒租约、真实线程和 UTC/monotonic/内存 UOW 保持。旧 probe/证据不改，独立候选/manifest/attempt marker；不启动 SQL、DB、Dolt、Compose、HTTP、Submit、CT108 或全量 runner。本范围不授权产品改动、合入或正式恢复。数 GiB 合成结果不等于现场 24 GB 或 SQLite 行为；即使成功也不能直接转完整 Submit。固定候选送审后再给一次执行决定。

## 44. 完整 closure 候选 a：暂不 GO，三项具体修订

**manifest `bbab2573b387248e27186d55e614efa988c8db1e39c48a4ffa3cf94a59cab137` 暂不获得执行 GO。** 实际读取 `p6changeclosureprobe20261106a/candidate/` 的 probe、supervisor、launcher、README、manifest、准备记录与静态验证器，并对照已审 1f9731 detached worktree 中 builder/Contract/fixture；没有导入或执行候选、没有运行测试/远程取证。另用只读 AST 检查确认以下名称/参数问题，不把语法检查当运行通过。

manifest 与六文件摘要匹配，checksum list 为 `d95f383af94d79ef853d87e0d842a1a1c5d9f79b25f8d22efcb832f26c1eb2c4`。运行文件绑定：probe `7c57b14f5f6f18765f0ebdeca44031de3bc699a1b66457d1ec39fc4441235bf8`，supervisor `e90c76ecd0e3bb6a3524af37d94f9c8ea633d879c4c0988e41421310d4e04043`，launcher `be14b34fdeaed0c4ee5cb753c7b8251243aeb422f1e28b06a62d0bd7e890818f`。

### C1：名称和参数接线错误会阻止执行并破坏结果收尾

`probe.py:892–893` 的 `_make_worker` 使用 `replace`，但文件没有相应 import、定义或赋值；因此 worker setup 必然 NameError，尚未到输入生成。snapshot 构造同样在 544/549 行使用该未定义名称。其次，`set_value` 在 258 行定义为 `(section, name, value)`，1243/1246/1248 行更新顶层 status 及 1250 行更新 ended_utc 都只传两个参数。即使修复 replace，正常路径仍 TypeError；异常路径和 finally 也会再次 TypeError，掩盖原错误并阻止最终 JSON/GC 回调收尾。

修订仅需正确引用 dataclasses.replace，并为顶层字段提供符合实际数据结构的更新路径，统一检查正常、异常与 finally 的实参。静态准备须核未定义名称和调用签名，不能只依据 ast.parse 或关键词存在即宣称该接线正确。无需因此运行 100k 负载、扩测试矩阵或改变产品。

### C2：builder 内部已完成阶段未排入保存队列，截断时仍丢目标窗口

`_install_builder_timers` 仅 `record_stage`，没有向 pending queue 请求保存。全文件只有 766（inputs-built）、873（整个 builder 和结果验证完成）、879（释放完成）、1079（handoff 完成）四处 request_checkpoint。heartbeat handler 的 finally 只消费已有 pending；inputs-built 保存一次后，长时间 builder 中的多次 ordering/payload/digest 与 GC/续租记录都只在内存。若在第二次 payload 附近失租，runtime 随即 join 而执行线程迟迟不结束，外层截断时磁盘最后有效记录可能仍是输入完成快照；即便 handler 已记录 lease_lost，也没有无条件保存该异常结果。这正是本次要区分的窗口，不能靠最终成功输出覆盖。

修订要求：实际完成的粗粒度 ordering/payload/digest 等边界排入有界保存队列，按现有委托关系消费，避免逐 key/cell 保存；heartbeat handler 失败后即使 pending 为空，也保留最后有效阶段、deadline/失败和 GC 记录。真实 heartbeat 前及事务内仍不得 checkpoint/fsync，保存开销和硬截断未保存窗口仍明确。保持原 64 checkpoint 上限和有界记录，不增常驻观察器。阶段尚未完成时不能伪造完成值。

### C3：停止条件与子进程自行退出竞态可把截断写为成功

`supervisor.py:474–502` 只在 `stop_reason is not None and child.poll() is None` 时把 status 写成停止原因。如果监视已发现 RSS/host memory/disk 越限、信号或截止，但 child 在此间自行 exit 0，便落入 else，被写为 child_completed；exit_code 又优先判断 child_completed/0，最终返回 0。该路径连 stop_reason 都不写入结果，使已触发停止条件消失。必要指标读取失败也有相同竞争窗口。

修订要求：停止分类独立于是否仍需发送信号/回收。任何已经触发的 stop_reason 均写入结果并返回非零，child 已退出时只免去 kill，保留其真实 return code/reaped 状态；只有未触发停止条件的正常 exit 0 可归类成功。锁释放继续由实际回收状态决定，不能为保留失败结果无故扣留已回收子进程的锁。

其余主要方向与已审范围一致：固定 1f9731 与新独立目录/attempt marker；真实 builder 一次，通过原 row_digest/Request/Plan/Snapshot 构造输入而非手调三次摘要；100k 的 PATCH_DML 是显式 synthetic builder decision，未宣称 adaptive planner 会选择它。原 Thread/Event/时钟/10/30 租约、300/290 秒、8 GiB、host 16/4 GiB、disk 1 GiB/512 MiB 和新 GC 环形/最长窗口均有接线。这里不重开设计范围，只定向修复上述可执行性、截断留证与停止分类。

三项已直接发送原实施者并抄设计。当前没有 GO，旧探针授权不能复用；修订后更新 manifest/文件摘要和准备记录，再审实际差异。未修改候选或产品，正式测量继续停止。

## 45. P6-CLOSURE-RB：C1/C3 关闭，C2 的逐 key 排队仍阻塞

**新 manifest `acfd8ae328d3d0a1d40df0ec8a8073554159efe9d9ec90c49aeb71ca116da181` 暂不 GO，仅剩 C2。** 按 §44 定向读取修订脚本及 review-request/preparation-record；六文件实际摘要与 manifest 均匹配，checksum list `d2c82ad72d5cae3de5a7ca5cc7afc298f454612f2cce55d41af5b551bd8da606`。probe `21a019ea52ee3a09f9d8c278412a17a41f06b71232a021e32e30c3c389a8c3b2`，supervisor `185dd07ea40c8c9687c966636a0c0276a73e544c52c0e0f6acc23d3af7750c8b`，launcher 未变。仅做源码、哈希和 AST 实参检查，没有导入/执行候选或产品，没有新增测试矩阵。已向设计回显 P6LINK-0820-R，消息工具返回送达确认。

C1 关闭：真实导入 dataclasses.replace，顶层 status/ended_utc 改用有明确字段约束的 `set_root_value`，所有相关实参符合各自方法签名。C3 关闭：stop_reason 在回收判断前写入结果，停止原因非空时即使 child 已 exit 0 也保留停止分类并返回非零；是否释放锁继续取决于确认回收。

**C2 修订尚未满足“逐 key 只聚合”。** `probe.py:644` 在通用 `install_delegate` 的 finally 无条件 `request_checkpoint`；此 wrapper 除 ordering/payload 外，还安装到 `_validate_unicode_tree`、`_validate_ijson_numbers`、`_serialize_jcs`。临时恢复 original 仅避免树内递归重复进入 wrapper，不能避免每个 canonical key 的独立 JCS 调用。产品 `_patch_mutations` 的 key_bytes_for_ordering 以及多次 validate_change_set_ordering 都会产生大量独立 key JCS；它们会先填满 pending queue，并在下一轮 heartbeat 后保存时快速耗尽 63 个普通 checkpoint。后续真正 payload/digest/GC 阶段及 `heartbeat-handler-failed` 仍被 `BoundaryCheckpoint.save` 的限额拒绝，只有最终第 64 个槽保留；如果异常 join 被硬截断，该最终槽也不能救回目标证据。修订前缺少阶段保存，修订后却由 key 调用占完名额，仍不能关闭同一个留证问题。

最小修订只需明确 checkpoint 资格：ordering/payload、两次 change-set digest 和 closure digest 等粗边界排队，key JCS 保留统计而不排队；若确需全量 JCS 边界保存，应明确识别其上下文，不能将通用 JCS 回调全部视为粗边界。保持原次数上限、final 预留、handler 失败后快照及真实 heartbeat 前/事务内无 fsync，不以增加预算/队列容量掩盖问题。静态验证应检查 key 路径不排队，不能仅检查 wrapper 中存在 request_checkpoint。

已将该唯一剩余阻塞直接发原实施者并抄设计；不重开已通过范围，不新增运行或产品授权。修订后更新摘要，下一次只核 C2 的排队与保存边界及其绑定。

## 46. P6-CLOSURE-RC：C2 关闭，精确候选单次 GO

**C2 定向复审通过，C1/C3 维持关闭；仅下列 manifest 获得一次 CT05 局部诊断 GO。** 只读检查 revision c 的实际源码、manifest、文件清单、定向请求、准备记录及 r11 日志；没有导入或执行候选/产品，没有新增测试或访问测试节点。既有 §43 范围和 §44–45 其余结论不重开。

`install_delegate` 默认没有 checkpoint label，只有显式标记的 mutation diff、ordering、payload 粗阶段可以排队；两次 change-set digest 和一次 closure digest 继续各自排队。三个 JCS delegate 均未传 checkpoint label。线程局部 key context 覆盖 `_patch_mutations` 和 `validate_change_set_ordering`，将其中 JCS 调用送入独立 `key_jcs_*_aggregate`；`record_stage` 更新累计值后立即返回，早于窗口候选和窗口保存。完整 digest 的 JCS 窗口保持独立。因此大量独立 key 调用既不占保存队列，也不占逐调用窗口；没有用扩容规避原阻塞。

64 个 checkpoint 上限、第 64 个 `probe-final` 预留和队列上限保持。heartbeat handler 的 finally 仍在实际 handler 返回/抛错后消费粗阶段队列，失败时即使队列为空也请求保存 `heartbeat-handler-failed`；真实 heartbeat 前及事务内没有新增文件 I/O。保存开销、写失败和硬截断可能丢失尚未保存窗口的限制保留。本结论是代码边界审核，不声称异常/强杀分支已运行验证。

静态验证器实际检查 delegate 的默认值、三个固定粗标签、两个 key-context 入口、JCS 循环无 label，以及 aggregate-only 返回早于窗口追加，不再只查 request_checkpoint 是否存在。r11 AST 日志与 shell/摘要检查均 exit 0，实际 SHA256 分别为 `8fbd16ab86eb27a10c2061c495adb49dcfa83544456a532c34bfdf708dd84ad8`、`fc0008b051823798b27a11cde7eec1b574a666cc17025278cb5bcf36a18220b8`，与准备记录一致；r10 验证器自身 kw-only default 错误保留，不作为产品失败或运行证据。

候选清单六项实际文件检查全 OK，绑定如下：

| 对象 | SHA256 |
| --- | --- |
| manifest.json | `221f8a1491f120faf9055567341622e931c70aedc9393f1631b17abf6ea41445` |
| candidate-files.sha256 | `958fb5097d8d39e6125532f48e73197d9386e90b955e4de38f2b82df4b0e2b1a` |
| probe.py | `2963835f10732edc0b73a73f17b573a2b345af9df0b0979b214d2aa22fdc59af` |
| supervisor.py | `185dd07ea40c8c9687c966636a0c0276a73e544c52c0e0f6acc23d3af7750c8b` |
| run-once.sh | `be14b34fdeaed0c4ee5cb753c7b8251243aeb422f1e28b06a62d0bd7e890818f` |

独立执行决定：

```text
decision=GO
candidate=p6changeclosureprobe20261106a
manifest_sha256=221f8a1491f120faf9055567341622e931c70aedc9393f1631b17abf6ea41445
```

原实施者可按候选 README 的唯一命令完成 LAN 传输、固定身份/clean/单飞/资源预检后执行一次；源提交固定 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，节点 `ct108-gw-dms-05`，字面 backend venv 解释器及 cwd 不变。100k mutations、真实 builder 一次、原 10/30 秒租约、全程 300 秒/290 秒停止、8 GiB RSS、200 ms 独立监督，以及 host/disk 门槛和回收截止均保持。任何触发停止、截断或失败均留证并停；不自动重试、放大输入或增加预算，未确认回收则保留节点锁。旧 a/b manifest 均不得执行或复用此次 GO。

本次仅授权固定合成内存 closure 诊断，不授权 Submit、正式基准、CT108、SQL/Dolt/Compose 或产品合入；没有新镜像 revision/source-tree 验证，容器门禁仍按 §42 延期。现场 lease 根因继续 OPEN，正式测量保持停止，成功结果也不能自动解除该状态。执行后交原始 stdout/stderr、supervisor、checkpoint、摘要与节点收尾状态复核。

## 47. P6-CLOSURE-RESULT：预算截断，已保存窗口内续租正常

**本次唯一尝试按 290 秒预算停止，完整 closure 未完成；不是产品失败或成功验收结论。§46 GO 已消耗，没有重试/扩容授权。** 只读原实施者回传的 `p6changeclosureprobe20261106a/runs/20261106T084827.859853825-2396923/` 原始证据和本地预检日志，没有访问测试节点、导入产品、运行测试或新取证。清单内 13 个编号 checkpoint、latest、stdout、stderr、supervisor 共 17 项实际 SHA256 全通过，launcher 独立摘要亦匹配。

首次 transfer preflight 的命令误填旧文件清单摘要；日志止于六文件检查，修正后的 r2 明确确认 GO/attempt/runs/node lock 全 ABSENT，再核最终文件清单 `958fb509…` 和 manifest `221f8a14…`。后续 GO preflight 匹配唯一授权，启动前 attempt/runs/node lock 仍为空。该准备操作错误不是第二次产品运行。失败日志 SHA256 `cba95df3702904958091d91eb2de51a3389308c133fbd27cf728cbbcecf47bdc`；r2 `94334c7562c6b69ad245e37000a1a2a3a3a1066fb84b130297c1dd1ab21eda4d`；GO preflight `89e2eabcb637d0504122071528d8ff031c8fb440b6dd496b9d349c885bf664be`。没有据首次缺少结束行的日志单独推导 exit code。

supervisor 记录 CT05、clean `1f9731dfc3`、精确 manifest/六文件/GO MATCH，起止 2026-11-06 08:48:27.936189–08:53:18.269022 UTC，总 **290.332847s**。`stop_reason=status=failure_detail=outer_290_second_stop_guard`，exit **124**；child PID 2396958/starttime 196467093，收到 TERM 后 return code **-15**、reaped=true，未 SIGKILL，supervisor_error=null。launcher 起止 HEAD 相同，并记录 `node_lock_release=child_exit_confirmed`。外层 SSH 记载结束时间比远端日志早约一秒，分别保留，不跨主机墙钟相减判定预算；预算结论取 supervisor 本机 elapsed。

共 1,443 次资源采样、无丢弃；峰值 RSS **3,203,710,976 bytes**（约 2.984 GiB），最低 host available **64,404,956,160 bytes**，最低证据盘空闲 **217,913,937,920 bytes**，均未触相应停止阈值。这些是本次截断运行的采样结果，不代表完整链峰值或现场 24 GB 场景。

最后有效 checkpoint 为 **13 / builder-stage-payload-construction**，保存于 08:52:41.819113 UTC；到 supervisor 结束尚有约 **36.450 秒未保存窗口**。stdout/stderr 都为空，没有 probe-final、closure 返回、最终 Contract 数量/绑定验证、引用释放、safe handoff 或 runtime 正常退出证据。snapshot 的 `status=starting`、mutation_count=0 与 digest=null 是尚未更新的初值，不能读成产品生成零 mutations。调用计数表明 builder 已进入一次、change-set digest 已进入两次、closure digest 已进入一次；完成窗口另证前两次 digest 已完成，不能把 closure digest 的入口计数当完成。

| 已保存完成阶段 | wall time |
| --- | --- |
| input construction | 67.409849s |
| mutation diff/key ordering | 4.941476s |
| change-set digest 1 / 2 | 81.567445s / 77.689866s |
| payload construction 1 / 2 / 3 | 7.579521s / 3.606792s / 5.500193s |
| 完整 JCS Unicode 1 / 2 | 25.472344s / 25.336674s |
| 完整 JCS number validation 1 / 2 | 3.096770s / 3.102548s |
| 完整 JCS serialization 1 / 2 | 41.926393s / 42.114106s |

上述窗口有包含关系，不能累加为独立开销；第三份 payload 已完成，但其后 JCS/closure digest 没有完成记录。67 秒输入与两次约 80 秒摘要已说明旧小样本预算估计不能充当本完整链预测；不据此推算剩余耗时或自动增加预算。这里也没有旧实现的同负载对照，不能报告 hash sink 的实测加速/降幅。

最后快照内 **25 次** heartbeat handler/attempt/transaction 全部成功，事务 UTC→expiry 均 30 秒；没有保存到 heartbeat_busy、lease_lost 或 executor_failed。按实际 30/10 秒设置，handler 相对首次 due 的最大延迟约 **0.826s**，renewal anchor 相对旧 deadline 最小余量 **19.174s**。两次完整 Unicode 窗口各包含 2 次 handler 入口，两次数值校验各 1 次，两次 serialization 各 4 次。因此已记录的长 JCS 阶段可以与真实续租交错，阶段 wall time 超过 10/30 秒不等于连续阻塞 GIL 同样时长。尾部未保存窗口未知，不能扩写为全程无失租，也不能用最后保存的 expiry 与终止时间比较来臆断实际失租。

GC 聚合截至最后快照：gen0/1/2 分别 15,137/1,376/20 次，gen2 最大 **2.248569s**，累计 **16.808256s**；最近环覆盖 16,405 条旧记录、最长列表为 32，callback_errors=0。最大窗口位于首份 payload 构造内；时间相关性不证明 GC 是现场失租唯一原因。三个 key JCS metric 各 **550,000 次**、aggregate_only=true、窗口为空；pending drops=0、checkpoint_errors=[]，仅 13 个文件名额已用，C2 的逐 key 耗尽问题没有发生。最后快照含前 12 次保存的 I/O 累计 **1.172456s**、最大 **0.124691s**，第 13 次自己的保存开销尚未进入其快照，不能声称这是全程保存总耗时。

关键摘要：evidence 清单 `a20836c574b532a24e06a1cd9fa1d1c5bcf058e2873bc2b7fcc9c01313031aae`；supervisor `8fc0a0197b375bb8b681ccd7e5a1f1db89816681a96d6c10446034b3e335a1a7`；checkpoint 13/latest `a6850cee7be0a737d79307ed12c8198ed9f65824102a3eab678f3ca11baf7dce`；launcher `688abdba85a072ee4b058b41dc001cba9702d7a0fe134f1e9356a223ab468a7e`。

实施者已补充 preparation-record 的执行收尾：报告只读后检确认节点锁和匹配任务进程不存在；该后检原始输出未单独列为本次本地日志，因此独立可复核的回收/解锁依据仍是上述 supervisor 和 launcher。第一次 LAN 复制把 20 个文件放在 runs 根，第二次保留 timestamp 子目录；两份副本逐项摘要一致，是同一次执行的重复副本，均保留，不计作两次运行。

**下一步建议转候选镜像准备与验证方案，不要求再跑合成负载直到 completed。** 300 秒是诊断资源预算，不是产品性能门槛。§42 的候选代码/局部语义证据与本次已保存的 25 次续租，足以支持设计推进下一验证阶段；并不等于 lease 已修复，也不能替代容器门禁。该证据已否定“摘要总时长直接等同心跳连续受阻”的推论，但没有复现/关闭现场大堆、SQLite 或完整链退出问题。现在没有必须再做一个局部 probe 才能准备镜像的证据缺口。

实际镜像验证与另审一次真实输入诊断仍需以下具体绑定：

- 冻结最终产品提交及 RS/JCS 组合，按该源码的 Dockerfile/缓存流程准备精确镜像身份、传输身份和相应容器门禁；旧镜像结果不能直接称为该候选通过或 carried。
- 真实输入明确来源、摘要、复用方式和执行边界；优先围绕现场失败的 closure 路径提出问题。是否包含 DB、HTTP 或不可逆 Submit 必须明确，不能由“真实输入诊断”隐含扩大。
- 根据真实规模另定全程预算、RSS/host/disk 停止条件及回收/残留处置；不得把本次 300 秒当性能门槛，也不以“跑完”为由无限延长。尾部阶段、续租失败、释放/join 的保存方式和已知缺口须明确，避免再次只能以未保存尾部猜测结论。
- 判别目标应是具体的，例如真实 payload 在重复 digest 或释放阶段是否仍导致续租失败；若目标是验证 SQLite 场景，则内存 UOW 不足，方案须直接注明。若仅为获得 completed 而缩放合成输入，没有新增必要性。

这些建议已直接交设计和原实施者；没有授予新构建/运行 GO，不放宽 TTL 或删 Contract 校验。正式测量继续停止，lease 根因 OPEN，镜像/合入边界维持 §42。

## 48. JCS 候选镜像与真实输入诊断：设计范围通过

**设计 `949bef422a3182e1c39910c31636333f1ed94d8e` 范围通过，无阻塞 finding。** 实际读取 `p6-jcs-candidate-image-diagnostic-plan.md`、既有单步诊断设计及 §42/47 证据；在既有 clean detached `1f9731` 审核 worktree 只读核所选测试、Compose harness、Compose 与 Dockerfile，没有构建、访问节点、运行测试或新取证。设计可直接向既有产品工具任务分配三镜像准备、LAN 传输和这一项限定 CT05 容器验证，原测量实施者负责后续真实输入候选准备；无需再向 owner 重问已明确的范围。实际 v2-submit 仍无 GO。

冻结候选是 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，保持 e798 + RS 4497 + JCS sink 的既定组合，不掺入 main 正在开发的 Rust/产品或新版依赖基础镜像接线。按该冻结产品适用的 DC67 整镜像流程在 CT201 准备/构建，测试留在 CT05；backend、worker、RS 均绑定实际输入及新镜像身份，不套用旧服务镜像结果。跨节点 config digest/全部 DiffID、归档 SHA 和源 context/标签完整记录是本次具体交付内容，不能由本范围结论替代。`network=none` 下的依赖可用性亦须实际落实：冻结 Dockerfile 有 curl、Python 安装和 uv sync 步骤，不能从宿主有缓存直接推断所有失效构建层均可离线完成；缺失时按设计补齐明确制品/构建缓存，不能临场换 Dockerfile、锁或旧产品镜像。若原流程确实无法表达，再报告最小工具差异，不扩大产品范围。

所选 `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` 是现有小 fixture 三服务路径；调用 `start_three_container_stack` 后执行 accept/upload/import/preview/Submit/read，并只对自己的项目做 down -v。这是一项有实际组合覆盖的容器验证，不是正式真实数据 t3，也不冒充权威 runner/阶段退出。单项 `-n 0`、固定 clean 提交/离线 uv、独立项目与节点单飞、原日志和失败停止要求均保留，不增加重复 smoke 或全量测试。

具体接线须按设计 §3 在运行前静态落实：`build_compose_stack_images` 会先执行 RS identity 核验，再判断 prebuilt；因此 `GATEWAY_COMPOSE_GATE_PREBUILT=1` 并不跳过 RS 检查，标签不匹配仍可能触发构建。backend/worker 的冻结 Compose 未显式写 image，须以 harness 支持的固定项目名正确绑定其项目镜像名；`start_three_container_stack` 使用 `up --no-build`，不能仅提供两个任意 tag 即假设会选中。该接口可以表达固定候选，当前没有理由修改产品/harness；实施交付中给出准确环境、tag 接线和实际运行容器身份。测试临时项目的清理不得指向任何保留 source/target。

真实输入设计充分区分来源和目标：复用已核 `p6bw4s4h120261105b` 的 v2-preview checkpoint、原 parent/input/rules/cache，仅作为可恢复诊断输入；`run-bound RS full identity unavailable` 缺口不补造、不写 source/target MATCH。目标是新项目/三卷/幂等键和完整 `1f9731` 三镜像身份，显式包含真实 control DB、Dolt/RS 与一次 v2-submit POST，不是离线摘要，也不包含 Preview/预热/后续旅程。普通 resume 的旧 backend/worker 身份检查同样必须由外置候选准确表达这一个来源→新目标关系，不能仅替换 RS tag 或采用通用 skip；具体代码和完整 manifest 仍待审核。

原真实诊断的 45 分钟独立 guardian、40 GiB worker RSS、8 GiB host available、10 GiB disk 停止线与 48 GiB 启动内存、逐文件系统剩余空间核算保持；它与合成 probe 的 300 秒预算目的不同，不是临场加时。5 秒身份/资源守护和 15 秒/最多 1 秒纯 Python 栈复用既有工具；新镜像必须重新绑定真实解释器/PID并在 POST 前获得有效业务栈。只有原已审精确双 interpreter-discovery 错误可在即时复核成功后停采，其余必要守护/身份/资源/未知错误继续停止；不增加 profiling 或产品 GC hook。结果/回收/保卷/只释放自有占用分别留证，栈缺口不作失败瞬间证明。

容器结果先由独立 reviewer 核验，通过后再审完整真实输入候选并给 manifest 专属一次 GO。§47 不要求为取得 completed 重跑合成 probe，本设计也没有这样安排。后续诊断可回答新候选在真实输入与 DB 下能否续租并完成、失败是否仍落在重复 payload/digest/释放附近；单次离散栈仍不能唯一证明 GC/GIL 因果。未授权合 main/baseline、推送、正式恢复或复用任何旧 GO；H3、正式 V→H 和最终门禁继续独立办理。

## 49. 镜像缓存缺失：保留失败，优先同输入预填充

工具任务报告 CT201 首次冻结 Dockerfile 离线构建失败。只读核 `jcs-image-gate-1f9731-20261106/backend-build-offline-initial.log`，实际 SHA256 `085fca8b147108fbc1c8d9d021e3ed8c7e39751342d974e6247ebcbc68be9349`，与报告一致。日志记录 heavy-dev-01、2026-11-06 09:07:28 UTC、起止 `1f9731`，`docker build --network=none --pull=false`；两个 FROM 已缓存，但 uv 安装 RUN 未命中，curl DNS 失败后管道尾端 sh 仍退出成功，后续 `uv python install` 因 uv 不存在而 exit 127，整次 docker build exit 1。这是构建缓存缺失，不是测试失败或产品行为证据；没有 CT05 测试/锁操作。不按 DC68 把缺缓存描述为自身参数错误重做。

**提出的 named-context→任务私有 cache 基础镜像尚不在 §48 授权内。** 它实际替换 FROM 输入；尤其 runtime 基础镜像新增的工具、缓存、配置/ENV 会进入最终 rootfs，不能以产品 Dockerfile 文件未改就宣称只是透明缓存。预装 uv 还可能让上述 curl 管道失败被掩盖后继续；这不是要求修冻结 Dockerfile，而是说明需区分真实基础输入与缓存命中。当前仅有建议，没有可审核的具体制品/差异，未批准该替换，也不要求建立新 dependency-base 体系。

已向设计提出更小补充：在允许联网的 CT201，以精确冻结源码、同一 Dockerfile/context、固定 base identity 和同一 build args 预填充原 BuildKit 构建层；只构建、不运行测试，再以相同输入 `network=none` 做最终构建。记录联网预填充的来源、起止、实际输入/制品摘要与原锁 identity，缓存预填充结果不得冒充最终离线构建或容器验证。这样不引入新 FROM 映射，也不借 main 开发线的依赖基础镜像。该补充须由设计明确后定向核，不需要 owner 重确认整个范围；当前没有该联网预填充或替换基础镜像的执行决定。RS 原有预置接口及其准备仍在 §48 已通过范围内。

审核意见已发设计；直发工具子任务被 app-server 以 multi-agent v2 sub-agent 不允许直接输入拒绝，已请设计转交，未声称子任务直接收到。

## 50. CT201 联网构建冻结候选：最小替代范围通过

**设计提出的替代无实际治理阻塞，可在设计文档明确替换 §2 的本轮离线加严后按既有任务执行，不需 owner 重确认。** 已核 `testing-conventions.md` 的 CT201 联网开发节点边界及 `p6-backend-image-exit` 之前产品按 DC67 整镜像构建/传输的例外。`network=none` 是设计 `949bef422a` 自加限制，不是禁止 CT201 联网构建的 owner 决议。§49 的“联网预填充后再 none”只是建议，不是必须新增的门禁；不需要为了兑现 none 再绕一轮缓存验证。

本轮允许在 CT201，以精确 `1f9731` clean worktree、原 Dockerfile、原 context、固定基础镜像身份和明确 build args，直接联网取得冻结依赖并构建最终镜像。如实记录实际网络模式、制品来源/摘要、工具/基础镜像与最终身份、构建及传输起止；不得称为离线构建。不更换 FROM、不使用 named-context cache 基础镜像、不改锁/产品或掺入 main 的新 dependency-base。CT201 不运行测试；CT05 的公网隔离、离线依赖消费、三镜像身份核对和单项门禁范围均不变。

唯一需落入具体构建命令的缓存细节：首次失败中 `curl | sh` 那层表面成功却未安装 uv，不能假定切换网络模式一定使该层失效。联网构建须对受影响构建阶段显式避开该失败产物，例如使用任务内明确的 no-cache/stage cache 控制；不清理整机共享缓存、不为此改产品 Dockerfile。固定原 base digest/本机身份，不能通过重新拉取可变 tag 顺带升级基础输入。该要求用于消除已发生的缓存缺失残留，不要求额外产品测试或第二次离线构建。

原失败日志保留，最终镜像/小 Compose 实际证据仍交独立审核。此范围只接续 §48 的镜像任务，不授予真实 v2-submit POST、产品合入或正式测量恢复。

## 51. 构建导出修正与小用例运行身份留证

只读核 CT201 构建日志：`backend-build-final-network-host.log` SHA256 `4be54071960ad08961949e1d964efe5834a80be94a4fe1636d9abd0e5ac3cdcc`，记录 `1f9731` 原输入、任务内 no-cache、network=host，安装/编译成功、build exit 0；docker-container driver 未指定输出，明确警告结果仅存 cache，随后 wrapper tag 步骤失败。实施者保留该错误，使用同一显式 builder、源码/context/base/args/network 加 `--load` 消费成功缓存导出，没有再次 no-cache 编译或测试。`backend-final-export.log` 实际 SHA256 `3a7ef4d60c61c9cd28b85e0e3134b9bd242d74cd12b952353bca3eee40763861`，09:21:55–09:22:07 UTC、exit 0。两次实际 FROM 解析 digest 与事先记录的 rust/python RepoDigest 一致，未见基础输入替换；最终 build metadata config digest 为 `sha256:c4baaf17da52a29dd95a92f7801ce5dec3890db41ebb4b162c7e8596239f1898`。RS 原预置接口日志另记录离线构建 exit 0。这里只确认构建/导出进度，三镜像归档身份、LAN 传输及 CT05 测试结果尚待成套核验，不提前宣称镜像门禁通过。

所选小 fixture 用例及其 `start_three_container_stack` 确实不调用 `persist_compose_gate_provenance`。工具提出的外置只读 collector 属于 §48 要求的“实际运行镜像身份”留证，可随唯一已授权用例接入，不要求修改测试/harness 或再开范围审批。限定固定 project 和 backend/worker/repository-service 三个服务，在容器存活期间记录容器 ID、Name、`.Image`、必要 Compose project/service 标签、时间和运行状态，并逐一核对 CT05 已加载镜像的本机 image ID；跨节点仍以 config digest/全部 DiffID 为依据。collector 的等待有界且随测试退出，不影响业务、延长容器生命周期或触发自动重跑；未取到有效身份则明确证据缺口，不把测试 exit 0 代替身份绑定。

意见已发设计转工具任务；后续继续既有单项门禁，不授予真实数据 POST。

## 52. 固定三镜像与唯一小 Compose：证据审核通过

**`1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 的三镜像身份及 §48 指定单项容器验证通过独立证据审核，无阻塞 finding。** 本轮只读 `/home/dev/gdds-p6-logs/jcs-image-gate-1f9731-20261106/` 原始日志、机读身份、collector/launcher 源码与镜像归档；没有访问测试节点、执行容器或重跑测试。结论直接绑定下列原始证据，不等待 handoff 排版，也不将其扩称为权威 runner、真实数据 t3、阶段退出或发布门禁。

独立重新计算 CT201 实际归档的 SHA256，并直接解析 tar 中 manifest/config：932,099,584 bytes，SHA256 **`18d3050fc4ebf7a6ad751d7540024e2d346cc8c6aada6ca3067aeb0cff1e95f7`**。实际三个 config 摘要、全部有序 DiffID 及 labels 与 source-image-identity 完全一致，再逐项对 node-image-identity 比较亦完全一致；不是只接受工具的 MATCH 字符串。CT05 load/save 后归档 SHA 可以变化，本轮跨节点判定没有使用归档相等或 inspect ID 相等替代 config/全部 DiffID。

| CT05 固定 tag | config digest | DiffID 数 |
| --- | --- | --- |
| `p6jcsgate20261106a-backend:latest` | `sha256:c4baaf17da52a29dd95a92f7801ce5dec3890db41ebb4b162c7e8596239f1898` | 15 |
| `p6jcsgate20261106a-worker:latest` | 同 backend | 15 |
| `p6jcsgate20261106a-repository-service:latest` | `sha256:b81faa1f970999676087a55f0fc63e17d4285fba73b04c5eca6a69612e1419aa` | 28 |

backend/worker 同一构建镜像分别用于两个服务，均来自 §50–51 已记的 CT201 原冻结输入/network=host 构建及导出；不声称离线构建。RS 使用既有预置接口离线构建。RS revision 为 `1f9731`，build-input-revision 为 `4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`，source-tree 为 `sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`，与 CT05 exact-candidate identity calculator 输出一致；build-input 没变不代表偷偷使用旧服务镜像，其本次完整 config/标签和构建结果已绑定。LAN 传输日志为 09:25:23–09:25:31 UTC、exit 0。

CT05 09:27:31–09:27:57 UTC，仅运行 `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`，`uv-consume.sh run --no-sync`、`-n 0`，**1 passed in 25.37s，pytest_wrapper_exit=0**。实际脚本固定 clean `1f9731`、prebuilt、项目 `p6jcsgate20261106a`、RS tag，设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、专用 TMPDIR，清除代理。日志起止 HEAD 相同，五锁 SHA 一致；preflight 的既有 native 扩展输入 `58436908aee9dd449f4d3e0542a6a8c1920b6d5e` MATCH，没有同步/重编译宿主环境。冻结测试/harness 未改，没有额外真实数据旅程或全量 runner。

collector 在 **09:27:45.156072 UTC** 取得同一项目三服务均 running 的记录，exit 0。逐项核实际容器 `.Image` 与 node-local-images：backend/worker 均为本机 `sha256:51307bca08c1fbb7a08a629c13b81bacce2da1f7c8b5732580ff4a26205f725d`，RS 为本机 `sha256:a75aa535046937dab51156c8a8acad0deec913a4daaee9a930c4b62d23cc7e39`；service 集合、project、名称与三镜像映射一致。这些 ID 仅用于 CT05 同节点运行身份，未跨节点比较。collector 只读 Docker inspect，最多 900 秒、单次 5 秒，随脚本 EXIT stop 标记结束；此次在 13.6 秒取得记录即退出，没有延长测试或引发第二次测试。

09:26:14 的首次 load preflight 因节点无 rg 在 owner 只读检查处 exit 127，尚未 load 或测试；保留日志 SHA `75530207765ab1f5b30c14e926d7b231b6f7a97f34b1c5b2a7941dc5c9ecd878`。改用 grep 后同一步一次通过，日志 SHA `95f0400e091bb2d719c8bbf33029de356bf137676306c0d59bea16179870e692`，不是门禁失败重跑。此前构建缓存缺失与 --load 导出遗漏按 §49–51 分别保留，不混称同一种错误。

postflight 09:29:02–09:29:03 UTC、exit 0，确认自有 project 容器/network/临时卷为空、加载镜像 ID 未变、collector 已退出、clean `1f9731`，核自有 owner/token 后释放占用。该测试只清理自己的临时项目，原诊断三卷等保留材料不在清理范围。

| 原始证据文件 | SHA256 |
| --- | --- |
| compose-gate.log | `0cce193acc5020d8e9642efdd2ce9e3e8bf27af4dbe649eaf6d827effc3d7850` |
| source-image-identity.json | `c71abf3d566a62faff89463db852d448a409fb8d78b28323be2f611cefa10e2d` |
| node-image-identity.json | `c07e2f02f32d3bd88366b71da9bbb60323e9c3db4da780de32e26c6a984656d2` |
| running-images.json | `ccf2e9961f0ccf39b34c2907f8caa1bef4402640756db7621e82c598be331d72` |
| node-postflight.log | `60aa21c1b5868c4c042f6c380e8c06449c0174a10381c68f1a7ac9b7af9efe39` |

可接续准备并送审完整真实输入 manifest/launcher，精确引用本次已核三镜像；不再为此加测或重建。来源 checkpoint/缺失 RS 运行身份、旧 backend/worker→新目标绑定、新项目/三卷/key、资源/采样/回收条件仍须在实际候选内核对。**本节没有 v2-submit POST GO**，lease 根因仍 OPEN，正式测量、合入与最终门禁边界不变。

最终交接补绑定：已读 `5dfe46b67fcb378e967dcde9c114eedb0ce7071d` 的 `p6-jcs-candidate-image-gate-handoff.md`，该提交仅增加该文档；相对产品 `1f9731` 也只有两份 handoff 文档差异，`vnext` tree 仍为 `dad054c32501c3bce462491af06c506c1c2acdf1`，交付 worktree clean。`evidence-sha256.txt` 实际摘要为 `dc3015dd3577d30f1f1595822967e6d0aac758f63a82773ac6b3a1588fdbf8ea`，其中 24 项日志/脚本/身份文件独立校验全 OK，与上述原始证据一致。handoff 明确联网构建、未单独归档中间下载物、RS 有效输入标签及仅局部门禁的限制；没有新增产品、测试或扩大结论。§52 通过结论现与该最终 handoff 绑定，执行授权边界不变。

## 53. 真实输入候选 g 初审：三项定向修订，暂不 POST GO

**manifest `5d4bcac787651e6ec264f94bfca66c1e5a89870136efff1210c3535d2e2c22f2` 暂不获得执行 GO。** 已读 `p6catalogsubmit20261106g` 的 review-request、manifest、准备记录、全部运行入口和关键身份/输入 helper，比较 f→g 增量及冻结 `1f9731` journey 的实际接线。独立核 15 文件 SHA/字节数/权限全部 MATCH，Python AST 可解析；三角色 archive identity 与 §52 实际文件一致，POST-GO 不存在。没有执行候选、导入产品、访问 CT05 或发 POST。静态语法和摘要匹配不能替代以下运行路径正确性。

### G1（阻塞）：流式 docker-save 读取错误地要求 manifest 先于 config

`candidate/check-image-identity.py:47–67` 在 `r|*` 单向流中，只有读到 manifest 后才设置 config_path，之后才接收该 config。合法 Docker-save 归档允许 config 在前，当前逻辑会错过它并在 75–76 行报 omitted config。已有且已审的真实三镜像归档就符合该反例：manifest 位于第 79 个成员（从 0 计），backend/worker config 位于第 61 个、RS config 位于第 56 个。该观察来自本地既有 tar 目录，不是重新 docker save 或运行候选；它足以说明不能假定节点导出遵从相反顺序。

最小修订可复用 §52 已核的 CT05 同节点 image ID→config/全部 DiffID/labels 绑定并实时核本机对象，避免新增重复导出；若保留 save，则正确处理任意合法成员顺序且保持有界资源与子进程回收，不能用忽略缺失 config 放行。保持跨节点 config/全部 DiffID 规则，不把 inspect ID 当跨节点 config。不得为修这个 parser 重跑容器用例或真实 POST。

### G2（阻塞）：启动后的活动目标卷被要求等于启动前 checkpoint

`submit_diagnostic_launcher.py:503–518` 新增对目标卷 `_volume_tree_digest` 与原 checkpoint 完全相等的检查；它经 `checked_factory`（669–671 行）在 wrapper 进入 v2-submit 时执行。冻结 journey 已先在 `real_dump_journey.py:9738–9758` 完成 clone 和 copied digest 对照，再由 `_run_journey_impl` 的 8736 行 `compose up -d` 启动/恢复服务，之后才进入 guarded v2-submit。此时 control DB/worker 运行记录、SQLite WAL 和服务文件允许正常变化；对运行中卷做完整文件摘要也不是稳定快照。因此该检查会把正常 startup 写入误报为输入不符，且在真正 POST 前中止。

恢复已审 f 的边界即可：checkpoint/source 内容及复制后的静止目标摘要交给原 journey 已有的复制前后校验，必要记录复用该位置的既有 copied digest；`checked_factory` 只核固定目标卷集合、名称/labels、mountpoint/文件系统与资源，不把活动内容当静止 checkpoint。禁止删除原复制校验或绕过来源校验。该问题已经在本报告 §13 明确过，不应在新目标接线中重新加入。

### G3（阻塞）：固定 composite cache 的完整 SHA 未被执行路径校验

manifest/scenario 与准备记录固定唯一 cache SHA `7263db55ad726a16c505db86aca87401eb4dd57775b1974d90964f04703d72ff`，但 `source_input_preflight.py:259–280` 只查存在、key、输入和 comparator identity，并调用原缓存复用；返回值只是记录当前文件 SHA，未与候选固定 SHA 比较。原 journey 只校验 cache schema/这些身份和 counts 的形状/内部和式，不能证明是此次授权的同一份 cache 内容。因此完整 manifest 绑定与实际启动条件不一致。

在现有 helper 读取/复用 cache 前增加与固定摘要的比较即可，并让 preflight 与 submit 前复查共用；保留原 key/package/comparator/schema 校验。若预期摘要实际需要更新，先说明既有证据来源并换 manifest 送审，不能以运行时观察值替代授权固定值。无需重新生成输入/cache 或设计新的证据机制。

其余关键方向可保留：原 observer SHA `0c8799a3…` 和单 POST wrapper SHA `8f4cb3fb…` 与已审版本逐字相同；45 分钟 guardian、资源/采样降级及目标步骤结束先关闭 observer 未改。固定 e798→1f 的 product/image guard 分别核两个确切端点和完整身份，未通用跳过；来源 RS 缺口显式保留，sampler/journey 共用原输入 manifest。新 project/key/三卷、唯一 log 目录拒复用和清理保卷范围未扩展。§52 镜像和小 Compose PASS 不受这些外置接线问题影响。

另有一项非阻塞说明修正：README 声称 state comparison 未核实会保留锁，但 shell 在 postflight exit 0 后先释放锁，再判 state/sampler MATCH；postflight 对 NO_STATE/比较错误仍可因已确认静止而返回 0。该事实应写准确：资源回收确认与业务/输入判定是不同结果，不能声称已实现并不存在的锁条件；无需为文字承诺新增持久状态或无故保留已静止节点的锁。比较不符仍保持失败分类。

合并修订 G1–G3，并更新全部受影响 pin、manifest、准备记录后定向复审即可；不重开设计范围、不重建镜像或重跑已通过门禁，不创建 POST-GO、不试发 POST 来验证修订。必要的局部校验仍遵守专用节点规则。本轮发现已直接交原实施者并抄设计，正式测量保持停止。

## 54. 真实输入候选 g 定向复审：G1–G3 关闭，精确清单一次 GO

**候选 `p6catalogsubmit20261106g` 复审通过；仅 manifest SHA256 `ba296d36c8a23f61d312eb5124d49a35e9aaceefc0e2a4f440afb822f69f90f0` 获得一次限定 v2-submit 诊断 GO。** 这不是 H3 复审或正式测量恢复。旧清单 `5d4bcac7…` 的 §53 NO GO 不可用于执行，新结论不适用于其他摘要或候选。复审时 POST-GO 不存在；本审核没有创建 GO 文件、传输候选、访问 CT05、导入产品、运行候选/测试或发 POST。

实际读取新的复审请求、准备记录、完整 manifest 和修订 helper，并沿冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 的只读 detached worktree 核接线；该 worktree clean。独立核验 manifest 的完整 SHA，以及清单内全部 **15 文件**的 SHA256、字节数、权限均 MATCH；Python 文件仅作 AST 解析，未导入执行。launcher 内部 pin 与实际候选一致。observer 和单 POST wrapper 分别仍为 `0c8799a3aa29d13544009e5201ea1a8833c2ec629ca8dce8dfdfaef300857097`、`8f4cb3fb99312261071263fc778712a2db56dbc37c475ccc89f374095625247f`，未改变已审守护和单步边界。

- **G1 关闭。** `check-image-identity.py` 改为实时 inspect 每个已审 tag/目标项目 tag，比较 §52 已审 CT05 同节点 image ID、完整有序 DiffID 与 labels；固定 identity 文件还核 archive→node 的 config/DiffID/labels 映射及准确 handoff/report。删除了有成员顺序缺陷的 docker-save 流式读取，不再重复导出。config digest 通过已审归档到本机对象的映射绑定，没有把本机 inspect ID 当跨节点 config digest。checker SHA256 `0754135df876c9232635dda96bbcf5f4b5c40a3a7472e20c5ae02b9ddb0e45b7`。
- **G2 关闭。** `require_target_filesystem(preflight)` 及调用点一致，启动后仅核三卷集合、名称、Compose labels、解析后的 mountpoint 和文件系统；不再对活动内容求 checkpoint 摘要。来源 snapshot 的严格摘要检查保留，冻结 journey 的 clone 后摘要对照仍发生在服务启动之前。记录明确区分该静止复制校验与运行中卷的 metadata 核验。launcher SHA256 `46516373bea3795f8bcc2d1fa56eca759e7a01a192b1b0f760c5b169d30147a8`。
- **G3 关闭。** source helper 在读取/复用 composite cache 前，实际调用 `require_sha` 比较固定 `7263db55ad726a16c505db86aca87401eb4dd57775b1974d90964f04703d72ff`；preflight 和进入 journey 前复查共用该路径，原 key/package/comparator/schema 检查保留。helper SHA256 `c37d1e2a7562f72cba7eb721fefad99aadc049b361029e53286966c90ec4fd97`。

README 已准确区分“确认 Compose 静止后释放节点锁”和“state comparison 失败仍返回非零”；不要求为文书承诺保留已静止节点的锁。另有一个**非阻塞文书遗漏**：清单外 `preparation-record.md` 仍写旧中间摘要 `bd1dfab5791f0d70347482d1c62c10705092f17657a912130f72cdcc3bfc11d4`。实际清单、用户交付和 review-request 均为上述 `ba296d36…`。实施者归档前更正这一行即可；不改清单内文件，不需要为此再开审核轮次。该旧摘要没有 GO。

本次仍只接受来源 `p6bw4s4h120261105b`、`e798ec87a37330250b0c051162e7962dba1daa60` 的 v2-preview checkpoint，到新项目 `p6catalogsubmit20261106g`、clean `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 的固定关系；新三卷/幂等键，一次 v2-submit POST，包含已明确的真实 DB/Dolt/RS。来源 run/state/launch、checkpoint、上传包和原输入 manifest 继续严格核验；sampler/journey/postflight 使用同一输入 manifest。来源 RS run-bound full identity 缺口仍明确为 UNAVAILABLE，不宣称 carried。不得增加 Preview、预热、后续步骤、自动重试或人工 recovery。

本轮只改外置诊断接线，没有产品/Dockerfile/依赖/容器 harness 改动，**不触发镜像重建或重复小用例**。最后验证的产品镜像 revision 是 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`；RS build-input `4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`、source-tree `sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`。三镜像身份及小 Compose 证据引用 §52 / `main@cfc429b20c` 与 handoff `5dfe46b67fcb378e967dcde9c114eedb0ce7071d`，运行前仍须实时核对已审本机对象；没有据本次静态审核宣称新实际运行已通过。

实施者可为精确清单写入以下候选专属 `POST-GO.txt`，再使用清单内固定命令执行唯一尝试：

```text
decision=GO
candidate=p6catalogsubmit20261106g
manifest_sha256=ba296d36c8a23f61d312eb5124d49a35e9aaceefc0e2a4f440afb822f69f90f0
```

```bash
ssh -o BatchMode=yes ct108-gw-dms-05 'cd /home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend && /bin/bash /home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogsubmit20261106g/candidate/run-once.sh'
```

固定 backend cwd、literal `.venv/bin/python`、clean HEAD、15 文件/GO/image/input 检查、节点独占、离线且无代理和仅本机 prebuilt 三镜像均保留。45 分钟独立 guardian、40 GiB worker RSS、8 GiB host available、10 GiB disk 停止阈值及 48 GiB 启动可用内存不变；POST 前有效 Python 业务栈和既有精确采样降级条件不放宽。失败按现有停止规则保留原始证据，不以本 GO 自动重跑；只清理自己的运行资源、保留目标卷，回收未核实则保留锁。执行后交完整原始日志、状态/输入比较、身份、资源/栈及收尾证据独立核验。

**本 GO 不授权产品合入、推送、打 tag、正式基准恢复或扩大诊断范围。H3 既有结论不变，正式测量继续停止，lease 根因继续 OPEN；一次运行结果也不能自动关闭根因或替代最终门禁。**

## 55. P6-G-RESULT：采样器双超时触发诊断中止，产品结果未定

**g 的唯一 POST 已实际发生，§54 GO 已消耗。结果分类为外置采样器触发的诊断中止；没有 Submit 完成证据，不能定为产品失败、lease 复现或修复成功。** 本轮只读本地 `p6catalogsubmit20261106g/ct05-evidence/`、准备记录和已审候选源码，没有访问节点、读取保留卷、运行测试或新增取证。index 实际 SHA256 `199d7ea8cdb31eac3eb6c3df8581ff4f150bbe3f6b8f649cfd15cb5b7fae47c6`；其中 **23 项**原始材料逐项长度和 SHA256 全部 MATCH。原 manifest `ba296d36…f69f90f0` 和 15 文件摘要仍相符。

首次固定 SSH 命令因远端尚无脚本而 exit 127，保存记录 SHA256 `816bf08967d0d1787ef3d1ba7eec7dcf4a5b57ae7bc308161601e95b5c4993bd`。它是实施者留存的命令/输出记录，说明 shell 未加载脚本；不把它当一次产品执行。补传同一候选后执行的 controller 才记录 CT05 `gw-dms-test-05`、起止 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、11:02:52–11:07:57 UTC。准备记录的旧 manifest 摘要已更正，POST-GO 精确绑定已审候选。

### 实际停止链与取证边界

| UTC | 实际记录 |
| --- | --- |
| 11:04:19 | POST 前有效 Python 栈；guardian armed，45 分钟 deadline；dump 1 有效，耗时 0.020601s |
| 11:04:21.940861779 | 唯一 `/submit-attempts` POST 返回 202；operation `op-b83bd85a87781980e3f49985` |
| 11:04:22.172687268 | worker claim 成功，attempt 1 |
| 11:04:32.175356164 | 同一 operation/worker heartbeat_succeeded |
| 11:04:34–35 | dump 2 超时，1.024930s，exit -9，failure_kind=timeout |
| 11:04:42.166043155 | 同一 operation/worker 再次 heartbeat_succeeded |
| 11:04:49–50 | dump 3 超时，1.024748s，exit -9，failure_kind=timeout |
| 11:04:50 | observer 写 two_invalid_dumps / diagnostic_stop，按已审代码向父进程发 SIGINT |
| 11:04:51.141 | v2-submit step_failed；父调用栈在 `_poll_operation` 的 `time.sleep(2.0)` 收到 KeyboardInterrupt |
| 11:04:51.402 | Compose 日志保存完成，随后原 journey 收尾 |
| 11:07:54.836–57 | 保留三卷、原调用退出、cleanup/postflight 确认静止、controller 释放节点锁 |

`submit-diagnostic-result.json` 的 post_count=1 与 HTTP 日志吻合；submit_completed=false，state 没有持久化 v2-submit 成功条目。observer stop、父线程 KeyboardInterrupt 和失败顺序一致。run.json 的 FAILED / exit 1 是旅程的异常归档；sampler 的子进程 exit -2 与 shell/controller 的 254 是 SIGINT 的不同表示，不是三次独立失败。不得据这个 FAILED 字段改写为产品返回失败。

两个超时的 **py-spy 子进程已被回收**：绑定源码 `_guard` 在超时分支先 `active.kill(); active.wait()`，返回后才关闭文件并输出 dump_end；两条实际 dump_end 都为 -9。因此本次不是仅发送 kill 而未等到退出。事件未单列 sampler PID/reaped 字段，该结论来自固定源码执行顺序与实际返回记录，不冒充另有 `/proc` 后检。preflight 与 dump 1 指向 host worker PID **2406642**、Python **3.14.6**、`gateway_backend.bootstrap.operation_worker`；binding 的 starttime **197281922**、data filesystem `/var/lib/docker/volumes`、st_dev **64526**。

每次 resource 读取先重新核 `/proc/<pid>/stat` starttime 和文件系统设备，再读 RSS/host/disk；本次共 7 条成功记录。最后一次是 **11:04:49**，距 stop **1.025062s**。已保存资源窗口中 worker RSS 最大 **134,086,656 bytes**、host available 最低 **66,910,173,184 bytes**、data free 最低 **214,393,626,624 bytes**，未触原停止线。但 dump_end 的 worker_starttime 是原 binding 的记录值；旧代码对双 timeout 直接停止，**没有在第二次 reap 后即时重读身份/资源**，不能声称本次已执行拟议的新降级检查。独立 guardian 在实际窗口内约每 5 秒检查且确实触发了中止；它没有在本次中止后继续守护业务。

最后有效栈（dump 1）只有主线程在 `worker_runtime._wait_interruptibly` 等待，位于 claim 之前。后两个文件只有进程和 Python 版本头，没有线程/业务帧，不能定位为 JCS、payload、GC、GIL 或 SQLite 阻塞；超时自身也不能证明上述因果。Compose 保存窗口中有两次成功续租，未见 lease_lost、heartbeat_busy 或 worker stall。最后成功续租到诊断停止约 8 秒；这仅支持保存窗口内的正常续租，**23 项材料不含该时刻/停机后的 control DB lease 快照，也不含完整收尾期间的 worker 日志**，不能从 HTTP 200 或 absence of error 推出停机后的最终 lease/Submit 状态。原 lease 问题继续 OPEN。

### 输入、身份、回收与计时口径

source/target 三镜像 checker 全部 MATCH；run.json 中 backend/worker 的 config、全部 DiffID 和同节点 ID 与 §52 固定身份逐项一致。preflight 原输入/cache/source checkpoint MATCH；run.parent_source 保存三份 copied-volume digest，与授权 checkpoint 对应，原 G2 静止复制校验已落实。target-volume-binding 仅核 metadata/filesystem，没有再哈希活动卷。sampler/postflight 的输入比较都为 MATCH、issues=[]，且引用同一 `4c5638df…` expected manifest 和实际 state SHA `069af4889b3055e2e2f13e51c9ffce58883c1d6b53c56c9c8305ce752a5426de`。这是上传输入身份一致，不是业务成功或未发生任何 durable 写入的证明。

cleanup/postflight 各 exit 0，固定项目 containers/networks 为空、status=QUIESCENT，未删三卷；controller 记录 node_lock_released=true。准备记录还报告后续只读锁 absent，但 index 内没有该后检的单独原始输出，因此本轮独立依据是 controller 解锁和 cleanup/postflight，而不是把该描述升格为新增核验。SIGINT 结束客户端轮询后服务仍可能在原 Compose down 期间执行；不能把停止轮询等同于那一刻业务已静止，亦不能推导该期间业务完成。

时间口径需在清单外准备记录纠正：**278.958s 是 sampler 11:03:16.892–11:07:55.926 的 elapsed**；journey 11:03:40.161–11:07:54.836 相差 **254.675s**，目标 step 记录 **31.599s**。step_failed 到保卷记录相差约 183.695s，包含原收尾，不能全归因于 Submit 执行。resources 的 **3,714,203,648 bytes** 是全程容器 memory peak 汇总的保守上界，不是单 worker RSS；约 28 秒的 POST→诊断停止窗口不构成完整性能测量。

关键原始摘要：controller `1c29201c4dc689bd44877b725d7d48f18bcb0fbe92d70e8e0499e526c1a501ba`；observer events `a6a20cc6136d8c459e6f53fc3dd39e1f2e9197113c1d7fe46347fba332a59a75`；Compose `51e2beda0f2d46d0fd4d41085e708dad1173de61c67e1d2c61bdeb6653c8ef63`；run `06fdbd6f595f2bfccd28cc57ed4637a454f709d3a632844d8c5593b54ddf92db`；cleanup `20f97359ca3549187f2a8c077fa69515c318bc23f7b6a5dd999192f959251f9a`；postflight `c8e5e263b1a46ae09657748e22c75484c41dbaaf816ef722e4ccf0eb0b76207b`。controller 尾部自身 SHA 行写入时文件尚未最终结束，以本次 index/完整实际文件摘要为准。

### 最小工具修订建议与范围判断

设计提出“已知有界采样超时停采，独立守护和业务继续”的方向足够，不需要修改产品、延长 dump 或扩大诊断负载。现有 g 按旧已审规则停止是符合规则的；新的规则须在新工具候选中明确，不能追认 g 为已经降级继续。建议仅作以下收敛改动：

1. 保留 POST 前有效真实 worker 栈的硬条件；仅在 POST 后，连续两次都明确为 **1 秒预算到期且该 py-spy 子进程 kill/reap 已确认**时允许进入新的 timeout 降级分支。原精确双 interpreter-discovery 分支保持；未知错误、未知退出、无帧的普通失败及混合错误仍按原规则停止，不概括为“任意两次无效即可继续”。
2. 第二次 timeout **完成回收后**立即调用现有 `read_resources`，重新核同一 worker PID/starttime、filesystem device 及原 RSS/host/disk 停止线；失败或触线则停止。合格才记录专门的 timeout degradation、两次原始失败及新鲜 metrics，永久停止本轮 dump，保留栈缺口；继续原 5 秒资源/身份检查、45 分钟 deadline 和业务 poll，不重置预算或再试 dump。
3. 现有 timeout 分支的 `active.wait()` 及 finally 的同类回收均无 timeout。**最小补强是统一短而有界的 kill/reap（例如 kill 后最多再等 1 秒）**，记录 sampler 子 PID、退出码、reaped 和回收 elapsed；未确认回收不得降级，须记录并触发诊断停止。清理异常仍不得写成回收成功，不留另一条 finally 无界 wait 抵消前面的边界。无需另建 guardian/sidecar；现有每 5 秒守护与父进程停止路径可复用。

这三个条件只调整已发生的采样器故障处理及其已有回收路径；不改变产品 Contract、镜像、续租 TTL、输入、单 POST、节点、资源阈值或测试范围。新工具具体代码与 pin/manifest 需定向审核；不要求为工具改动重建 §52 镜像或重跑小 Compose。本轮当前产品 HEAD 和最后验证 image revision/source-tree 仍按 §54，未触发重建。

**本节没有新 GO，没有重试/新取证授权。** g 归档为 diagnostic_stop，保留原始 FAILED/KeyboardInterrupt 事实及全部卷/日志；若推进后续候选，必须使用新的精确绑定，不复用 g 的一次 GO。正式测量继续停止，H3 不变；不以这次中止关闭现场 lease 根因。

## 56. 双采样超时与预算规划：定向设计范围通过

**设计 `ba77e33781bc4973eff3c1e96c6e9d2b018ba6f7` 新增末节范围通过，无阻塞 finding。** 已读 `p6-submit-single-step-diagnostic-plan.md` 的实际 17 行增量并与 §55 对照；仅审文档，没有节点操作、测试、新取证或业务运行。原实施者可在既有角色内准备外置工具修订及指定的少量 CT05 工具测试，不需重问已明确的范围；具体代码、测试证据和最终 manifest 仍待审核，本节不授予下一次 POST GO。

预算原则区分计算/业务观察、可选采样与产品正确性期限，符合 owner 要求。按同版本同路径、规模、复杂度和资源证据给区间及一次性裕量，截断材料只能支持已完成阶段或下界；跨版本/不同形状不盲目线性外推，资料不足明确未知。软预期和事前固定的硬截止分开，不因性能预期落空就判产品失败，也不在执行中加时或自动重跑。当前新产品 Submit 缺乏可靠完整耗时，设计未虚构估算，仍保留 45 分钟观察上限；这不构成新的性能承诺或正式测量恢复。后续若确实触及该上限，再依已有证据一次重估具体窗口，无需预先增加校准轮次。

新增降级范围准确：POST 前有效真实 worker 栈仍是前提；只有 POST 后连续两次明确 1 秒 dump timeout、各自采样子进程回收已确认，且第二次回收后即时同 PID/starttime、文件系统与原资源复核合格，才停止 dump 并继续业务及 5 秒守护/原绝对 deadline。原精确双 interpreter-discovery 分支保留，未知、混合和其他无效结果继续停止；不延长 attach，不重试 dump，不追加 profiler。统一 kill 后最多 1 秒 reap 及 finally 的有界收束，既约束采样故障的阻塞，也不把工具退出期限混同于计算完成预算。

具体实现审核时核清一处接线即可：**未确认 sampler 回收的事实必须传递到现有 cleanup/postflight/controller 的节点解锁判定**，不能仅记录在 observer 日志却由 Docker 容器/网络为空放行；核实回收前保留占用并报告人工处置。该要求已经写入本设计，不是新增 finding 或新治理机制；复用现有结果/退出路径即可，不要求建立持久状态机、sidecar 或重设计 guardian。普通 state 输入比较失败与资源回收失败仍分别判定，不能借此重新无故保留已静止且回收确认的节点锁。

少量既有 fixtures 覆盖双 timeout 合格降级且守护继续、即时复核失败、未回收、未知/混合停止及关闭回收，范围与实际改动相称。测试仍在 CT05 clean 已提交环境内按仓库规则运行；不要求全量 runner、重建镜像或重复小 Compose。本轮没有产品/容器输入变化，目标产品 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，最后验证镜像 revision/source-tree 与 §52/54 相同，不触发重建。g 的旧脚本、证据和 GO 消耗状态保留；下一次业务候选须新项目/key/目标副本及专属清单 GO，不续跑 g 目标卷。H3 不变，lease 根因 OPEN，正式测量停止。

## 57. 候选 h 工具与最终绑定复审：通过，当前不授业务 GO

**`p6catalogsubmit20261106h` 的工具修订、17 项 focused 证据和最终候选绑定通过，无阻塞 finding。** 唯一审定 manifest SHA256 是 `8d8e674e6582deecaa13ab75b727e9189df84ed9ef4b58525e2974d148a84aa8`；handoff `0527c6e5b5de1b1c37cd0b4f3500d3aed94fc516` 与实际材料一致。本次 review-request 明确只请求修订和测试审核、不请求执行授权，故**本节没有 POST GO**；POST-GO 实际不存在。技术上没有发现阻碍该精确候选后续一次限定诊断 GO 的问题，后续决定可沿既有协调范围办理，不需要为相同文件重复测试或重建准备包。

复审只读本地候选、全部关键接线及已有 CT05 日志，并与 §54/56 和 g 的已审实现比较；没有导入候选/产品、执行测试、访问节点或新取证。独立核 manifest 完整 SHA、15 个文件的实际集合/SHA/字节数/权限、组件 manifest 和 launcher 内部 pin 全部 MATCH；Python 仅作 AST 解析。运行入口、来源/输入 helper、镜像 identity 和 checker 的 g→h 差异限候选名称/token/purpose 以及本次回收接线，原 G1–G3 修订保留。最后已审产品的 detached worktree 仍 clean `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`。

两项草稿观察已关闭：

- **普通退出不会被时间观察误归类。** observer 155–163 行先 poll，只有结果仍为 None 且明确 1 秒预算到期才设置 timed_out，并进入有界 kill/reap。已退出的结果走原退出码/输出分类，即使观察较晚也不成为 timeout_pair；普通成功可保持有效，未知退出仍保持未知。新增测试直接证明迟到观察的正常退出不触发 timeout/reap/降级。
- **preflight wait 异常不会误报已回收。** Popen 后先登记该 child 的 reaped=false，成功 wait 才改 true；TimeoutExpired 和其他 BaseException（包括 KeyboardInterrupt）均进入有界回收，异常仍向上传递。回收未确认或回收自身异常时保持 false，`close()` 不会用原默认成功状态放行。测试分别覆盖 wait 中断后成功回收，以及 wait 异常且回收超时，结果为 REAPED / UNCONFIRMED；两条 wait 均带 1 秒界限。

双 timeout 降级只接纳两个明确 timed_out 且 reaped=true 的连续记录；混合/未知配对仍停止。第二次回收后先检查原绝对 deadline，再即时调用现有同 PID/starttime、filesystem device 和原资源阈值校验，合格才记录降级并永久停采本轮 dump。既有精确双 interpreter-discovery 分支保留。降级不重置 deadline；原 5 秒资源检查和业务 poll 继续。timeout 和 finally 都使用 `_kill_and_reap` 的 1 秒 wait，留 child PID/exit/reaped/elapsed；回收未确认立即停止，finally 仍仅作有界收束，不能降级。

§56 要求的**节点解锁接线已落实**：guard 在 finally 回传 sampler 状态，父进程对 guard 作有界 join，只有 guard 已退出、preflight 已回收及 shutdown 确认 sampler 回收，才由 `WorkerObserver.close()` 报 REAPED；缺失 acknowledgement 或父进程强制终止 guard 但无 sampler 确认均为 UNCONFIRMED。wrapper 在成功/异常退出都把 close 结果写入 `submit-diagnostic-result.json`，close 异常显式记未确认。postflight 在已尝试运行时读取该结果并用共同 predicate 判定，缺失/损坏/false 均非零；controller 还要求 postflight exit 0 且记录中 sampler_reaping_confirmed=true，才进入核 owner token 的解锁分支。未尝试 Compose 的准备失败路径可按 NOT_STARTED 处理；普通输入比较不符继续独立返回失败，不制造已确认静止和回收后的锁残留。

最终工具 SHA256：observer `f197042fa0f5ef0abd065ac4d6dc014e7a460c3181a94abd3bd5b3545c4be023`；wrapper `ae8e64ccb15d6acb5703372e4be08d06e2dc46a1498c0d557d7feb90cda13cbe`；launcher `a63c0253776f80aced8644c97581d961955cf697a3aa9dc327a5bfab92d723ec`；shell `54f41023b3e13e6935b2aa49ec7991360ffe5bc26851e072dcd39977548c23f3`；component manifest `9c730140bed5dd725531c4fedd8575b1a3e072fdba732acaeddd4eddee0c6e34`。

CT05 最终日志 `ct05-focused-tests-final2.log` 的实际 SHA256 `74fcf037175f5aad3e67dc25fda37fdd5b5f47bc0c97f87dc7ef20a0cad0bdb4`，记录 hostname `gw-dms-test-05`、12:14:08–09 UTC、起止相同 `1f9731`、literal backend Python，以及精确 manifest、observer、两份测试源码 SHA。13 个 resource 测试和 4 个 lifecycle 测试均通过、两批 exit 0。内容覆盖原资源阈值/PID/文件系统、两种合格降级、降级后守护/截止、即时复核拒绝、有效样本清空连续失败、未知/混合拒绝、未回收、关闭回收和前述两项修订。无需重跑这批已通过的相同测试。测试使用受控 fixtures，不把其通过表述为真实 Submit、实际 py-spy attach 在负载下已成功或产品 lease 已修复。

最终 CT05 binding 日志 SHA256 `5d7c25745cf457a96761b6e0e80bac28c9dc93d694b1e7e24c04afeac9fa5927`，15 文件 MATCH、post_go_present=false；释放日志 SHA256 `cded8f9fbd7d49025d32c6f83c1cefefbe9e16eb2b8f99a3e36fc8372b18e8ec`，记录同一 HEAD/manifest、12:15:30 无 Compose/test 进程、owner 核验移除及 node_lock=FREE。本地当前文件全部匹配最终日志的绑定，未把 11:58 的旧 15 项通过结果当最终证据。

前期传输参数/目录层级错误、isolated unittest module lookup 失败和 focused fixture 失败均有留档。已核最终前两次日志实际 SHA 分别 `59e26dee75af6bdd303d9b5f14fe342b1b5509e80769e5f3bc3ee8e927e248dc`、`fef16cfecd354e701c43d85a9a7c18d3939b9356d2d2456c1184fed249585a22`。后一轮 observer SHA 已与最终相同，失败来自 fixture 按资源读取次数注入故障和固定次数断言；最终改为在第二个 dump_end 之后注入即时复核故障，并保留实际拒绝/不降级/发停止信号的断言，没有删去业务边界来求通过。它是调试 focused 结果，不是权威 runner 失败或业务重跑；原记录不改写。

h 保持新 project/三份目标副本/幂等键、原 e798→1f9731 精确关系、同一 accepted input/cache、单 v2-submit POST 和无后续步骤；保留卷及 g 既有证据不复用运行。45 分钟 watchdog、1 秒 dump、15 秒采样、原资源停止线及预算原则不变。产品和镜像未变，**不触发重建或重复 Compose**；最后验证镜像 revision `1f9731`，RS build-input `4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`、source-tree `sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`，身份与小用例引用 §52。未来若给该清单一次 GO，仍须运行前实时核对节点、clean worktree、输入、镜像及节点占用；本次审核不预先声称这些未来现场条件已满足。

**工具与候选绑定技术审核完成；业务执行决定另记，当前不运行。H3 不变，正式测量停止，lease 根因仍 OPEN。**

## 58. 候选 h 精确清单：一次限定 v2-submit GO

**候选 `p6catalogsubmit20261106h`，manifest SHA256 `8d8e674e6582deecaa13ab75b727e9189df84ed9ef4b58525e2974d148a84aa8`，获得一次限定 v2-submit 诊断 GO。** 设计在 §57 工具/候选审核通过后，沿 DC80、`ba77e33781` 和 §56 的既定单步诊断范围明确请求执行决定；因此本节接续 §57，不再把早先 review-request 的“仅审核修订”当作当前阻塞。没有新增业务取舍，不需要 owner 重确认。

决定前再次只读核验完整 manifest SHA、15 文件的 SHA/字节数/权限，全部保持 §57 的精确绑定；POST-GO 仍不存在。没有重跑测试、访问节点或执行业务。§57 的 CT05 17 项工具测试、固定产品/三镜像和源输入证据继续适用，不要求改包、重测、重建或重复小 Compose。未来现场是否可运行仍由固定入口实时核验，不能用本次静态决定替代。

实施者可创建仅含以下三行的候选专属 `POST-GO.txt`：

```text
decision=GO
candidate=p6catalogsubmit20261106h
manifest_sha256=8d8e674e6582deecaa13ab75b727e9189df84ed9ef4b58525e2974d148a84aa8
```

仅使用已绑定的固定命令执行一次：

```bash
ssh -o BatchMode=yes ct108-gw-dms-05 'cd /home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend && /bin/bash /home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6catalogsubmit20261106h/candidate/run-once.sh'
```

节点须为空闲且可原子取得自己的占用；不能抢占/清除他人锁。保持 clean `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、固定 backend cwd/literal Python、§52 已审三镜像实时身份核验、本机 prebuilt/离线无代理、原 `p6bw4s4h120261105b` e798 pre-submit checkpoint、原 accepted input/cache 和严格摘要检查。使用新 h project/key/三份目标副本，不续跑 g 卷或修改来源。仅一次 v2-submit POST，无 Preview、预热、后续步骤、重试或人工 recovery；日志目录拒复用和候选/GO 的执行前绑定保留。

维持原 45 分钟绝对 watchdog、外层 3600 秒预算、1 秒 dump/15 秒频率、5 秒资源守护、48 GiB 启动可用内存及 40 GiB worker RSS/8 GiB host available/10 GiB disk 停止线；不在执行中加时。只按 §57 已审精确条件允许两次已知采样失败后停采，继续原守护和业务轮询；未知/混合、即时身份/资源失败或回收未确认仍停止，不能放宽。原始栈缺口如实保留。

失败按现有停止规则保存证据，不自动再试。结束后保留三卷；原项目资源回收、observer preflight/guard/sampler 的确认结果须传入 postflight/controller，未核实则保留节点锁报告人工处置。回交完整 controller/launch/run/state、observer 事件/栈、身份/输入比较、资源和收尾原始证据及摘要，独立审核再分类；不得仅据外层退出码或输入 MATCH 宣称产品成功。

**本 GO 仅属于该清单的一次诊断；不授权正式计时/基准恢复、产品合入、推送、tag 或范围扩展。** H3 既有结论不变，正式测量停止，lease 根因 OPEN。当前产品 HEAD 及最后验证镜像 revision/source-tree 仍为 §57 所记，外置工具范围不触发重建。

## 59. P6-H-RESULT：真实失租后触发 stall，诊断工具正常降级与收尾

**h 的一次 POST 已消耗，Submit 未完成；原始证据确认先发生 `lease_lost / heartbeat_busy_deadline`，随后触发 WorkerStalledFailure。** 这次具有实际失租证据，不能沿用 g 的“采样工具主动中止”分类，也不能以输入 MATCH 或工具回收成功宣布产品通过。观察目标没有达到，按既定失败停止规则保留现场交设计处理；具体导致续租越过期限的原因仍 OPEN，不据错误类别名称直接认定 SQLite 锁竞争。

已读 handoff `p6-baseline@60b2c6184860ce03b97a37d8d33f989ac8346146`、冻结 `1f9731` 源码及 CT05 原始场景文件。现有结果未复制到本地；先按仓库要求 SSH `echo OK`，再只读既存 JSON、日志和已保存 inspect/thread 文件，未读活动 `/proc` 或保留卷、未执行候选/测试/profiling、未生成新快照或负载，也未唤醒旧实施者。后续实施任务仅交设计协调已确认接管者。

### 授权绑定、输入和镜像

CT05 现存 manifest SHA `8d8e674e6582deecaa13ab75b727e9189df84ed9ef4b58525e2974d148a84aa8` 及 15 文件 SHA/权限仍与 §57–58 一致；POST-GO 三行精确绑定，实际 SHA256 `2d561c523c013037cf52b964273de0d583ae4f9aaa13d1c5afcf8175f529b87c`。controller 起止 HEAD 均 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，记录节点 `gw-dms-test-05`。preflight 输入、cache 和来源核对 MATCH；run.parent_source 记录三份复制后 digest 等于授权 e798 pre-submit checkpoint。没有续跑 g 卷。

run 中 backend/worker 的 config digest、全部 DiffID 及同节点 ID 与 §52 已审身份逐项相等；stall 当场保存的 backend、worker、RS 三份 inspect 中 `.Image` 以及 project/service labels 亦与 h 的固定身份匹配。三容器当时均 running，worker PID **2475208**、OOMKilled=false；这只是已有 inspect 的历史事实，不是本次重新查询运行态。postflight 的 state SHA `df3c8db86d8410f0dd8abf9a7b10fda8b570cddd123a74c5d0cbd875b37434c5` 和 expected manifest `4c5638df…` 比较 MATCH、issues=[]；sampler provenance 与其一致。失败 state 没有持久化 v2-submit 成功条目，输入身份一致不证明业务成功或没有 durable 副作用。

### 失租与 stall 的实际顺序

| UTC | 原始事实 |
| --- | --- |
| 12:34:10–11 | preflight 有效 Python 栈；独立 observer armed，绝对预算 2700 秒 |
| 12:34:13.394943161 | 唯一 submit-attempts POST 返回 202，operation `op-cb5dda7aa259720264260083` |
| 12:34:13.639223341 | worker `worker-d39ab359-7291-453b-ad9a-f9e069b99270` claim 成功，attempt 1 |
| 12:34:23.640328416 起 | 同一 operation/step 连续记录 heartbeat_succeeded，共 **191 次** |
| 13:07:00.058541982 | 倒数第二次成功心跳 |
| 13:07:22.253269 | 已保存 DB selected rows 中该 step 的最后 updated_at_us |
| 13:07:22.366958444 | 最后一次成功心跳日志；距上次约 22.308 秒 |
| 13:07:52.253269 | selected rows 中 lease_expires_at_us；与最后更新相差 30 秒 |
| 13:07:54.505173957 | worker 明确记录 lease_lost，error_category=heartbeat_busy_deadline |
| 13:09:24.032 | stall.json 保存 observed_stalled_seconds=121.665、threshold=120 |
| 13:09:24.676–25 | journey 记录 worker_stalled、step_failed，关闭 observer，保存 Compose 日志 |
| 13:12:30–34 | 保留三卷、退出并完成 cleanup/postflight 与解锁 |

HTTP 和 wrapper 均支持仅一次 POST；`submit_completed=false`、run FAILED/exit 1、failure_step=v2-submit、failure_type=WorkerStalledFailure 相互一致。stall 的 121.665 秒基于最后成功心跳，不是 worker 一直没有 CPU，也不是可直接当作持续持有 GIL 或 SQLite 锁的时长。

**“control DB snapshot: JourneyFailure”不表示 DB 字段全部不可用。** 同目录实际有 `control-db-selected-rows.json`（SHA256 `631971a71370d15604139b784cff64b2e1805c1e21006f92841f433b85b701fb`），包含该 operation 和 `prepare_import` step 均 RUNNING、attempt 1、owner、最后更新时间和到期时间，completed_at/diagnostic_code 均 null；submit_attempt `sa-eba75792efb85bd340ecdf97` 的 repository_operation_id=null。冻结源码的 `_capture_submit_attempt_control_rows` 先成功写 selected rows，随后才要求非空 Repository operation ID；本次 null 触发其 JourneyFailure，由外层统一标成 “control DB snapshot”。所以诊断错误来自同一 collector 的后续必要字段检查，不是这次 SQLite snapshot/query 全失败，也不是证明 SQLite 忙。Repository import status 因该 ID 缺失未继续采集。

冻结 worker runtime 的 `heartbeat_busy_deadline` fence 可在调用下一次 `session.heartbeat()` **之前**发现本机续租 deadline 已到而触发，也可从 StoreBusy 重试预算耗尽触发。两份已保存容器日志均有 191 次成功和一次 lease_lost，**没有 heartbeat_busy 事件**。现有证据确认失租和过期仍 RUNNING 的快照，不能仅凭这个通用 error_category 唯一认定数据库忙，也不能排除线程调度/长计算/其他延迟。runtime 在 heartbeat 异常后可等待 executor thread.join；保存的 main 线程 futex wait 与此兼容，但没有当时 Python 帧，不能把该推测当作已定位的调用栈。

### 新 observer 分支、资源与栈缺口

preflight py-spy child **2476612** exit 0/reaped=true，耗时 0.007638 秒；dump 1 child **2476894** 正常且有效，0.020591 秒。dump 2 / 3 child **2484190 / 2494799** 均在仍运行时达到 1 秒预算，随后 kill/reap，exit -9、reaped=true；总 dump 耗时约 **1.005708 / 1.005512 秒**，reap 单独约 **0.001148 / 0.001125 秒**。第二次后实际即时重读同 worker PID/starttime **197821067**、filesystem device **64526** 及资源，合格才写 two_reaped_py_spy_timeouts。该次 RSS **134,361,088 bytes**、host available **66,907,409,408 bytes**、data free **213,311,533,056 bytes**，与授权分支一致；此后没有第四次 dump，也没有 observer stop/resource_unreadable/deadline 事件。

observer 共 437 条事件，其中 **422 次**周期资源读取；降级后一直持续至 13:09:23，再由业务失败的关闭路径退出。相邻周期记录最大间隔约 **6.048 秒**，不是声称每个间隔精确 5 秒。整个保存窗口 worker RSS 最大 **23,869,075,456 bytes**，host available 最低 **43,138,623,488 bytes**，data free 最低 **213,291,245,568 bytes**，均未触原停止线。worker RSS 从约 0.12 GB 增长到 13:04 左右约 23.87 GB，失租前后仍维持这一大堆；单次 JCS sink 语义修订没有据此证明消除了真实大堆或续租故障。该相关性仍不足以定位 GC/GIL/JCS 根因。全程 resources.json 的 **24,303,439,872 bytes** 是三容器 memory peak 汇总保守上界，与单 worker RSS 分开。

最后有效 Python 栈只有 claim 前 worker idle；两个 timeout 文件只有进程/版本头。因此后续约 35 分钟没有 Python 业务帧，不可把失租定位在 payload、digest、JCS 或释放阶段。旧 stall collector 另留 `py-spy-unavailable.txt`，意思是它按 PATH 未找到系统 py-spy；不否定外置候选按固定绝对路径已执行采样。已有 49 个线程的 kernel/status 文件仅显示当时主线程 sleeping/futex、一个 executor 命名线程 running、其他多为 sleeping；这不等于 Python 栈或 CPU/profile 因果证明。

observer shutdown/close、wrapper 和 postflight 均记录 preflight/sampler/guard REAPED，guard PID **2476613** 已由父进程确认退出；controller `OBSERVER_REAP_RESULT=CONFIRMED`。因此这次不是未回收 sampler、资源越线或采样器 SIGINT 导致的中止。绝对 deadline 仍未到达，外层退出也不是 timeout。延长当前计算/attach/45 分钟预算无法解释或修复发生在预算内的失租，不建议以扩大预算直接重跑。

### 收尾、计时与摘要更正

cleanup QUIESCENT、postflight VERIFIED_QUIESCENT，固定项目容器/网络为空，未删三卷，controller postflight/observer check 均 exit 0、node_lock_released=true，最终 launcher_exit=1 保留业务失败。实际保留卷名单与 §58 一致。handoff 报告节点锁 ABSENT；本次未新增当前锁查询，独立依据取已有 controller 解锁和 cleanup/postflight，不把报告文字当作另一次现场核验。

controller **12:32:44–13:12:34**；sampler **12:33:08.185–13:12:32.486，2364.222s**（取其 monotonic elapsed）；journey **12:33:31.521–13:12:30.183，2338.662s**；v2-submit step **2113.962s**。step_failed 到保卷约 185.245 秒属于原收尾窗口，不能全记成有效业务执行。不是性能基准或完成耗时。

handoff 列出的 12 项关键 SHA 中，**11 项完整文件匹配；controller 的引用是自身尚未结束时的前缀摘要**。已核 `63f48169ff596ffbb1517720b9beee35e144d9536024ed94bce44aa4773a18fc` 正好等于 controller 写自身 SHA 行前的 **26,072 字节**；写完自身及后续几行后全长 **26,668 字节**，完整实际 SHA256 为 **`9a36b49d6e8f9e10d7d6b61502e42d6f1dc84b062ac6abddf2c8f28bebb6e978`**。这解释了差异，不据此指称来源损坏；handoff 应将它更正为完整摘要，并注明前者来源，保留原日志。

其他可复核原始 SHA256：Compose 日志 `7fad8bc8fe6cec7c0ac8c738d95267d8eee7b82efa5d942e0d8caec572e53c8e`；stall all-container-logs `64e814f42403e7acd7daf6b59bad9fd1ce03b11f51b6b62457d31c35013506b4`；observer events `92a4f3d2b26e6fd8f55d59e85ce8152bcedc8bf4b41bf85cb3b69b0774c13a4f`；stall.json `60c82e72cb52d16031db9ef9605b9f4a796790451a9edf94bd5d5493f0582deb`；worker inspect `6be9e62506a43ae027ef8925aa0833931362e5640003a399ad3429b6a407dc88`；postflight `2056ca4807358638f692937db1f6f02ec189787ef3c013a0c3e60945afa002cf`；run `adaa16d958a2537dc67dcdbe367f774fc3150a951d69cf7062c8fac1ea0a4812`。

### 交设计的后续边界

当前足以关闭“新 observer 是否仍因双 timeout 打断业务”的疑问：本次合格降级、守护和回收路径已有真实证据。需要继续处理的是**真实续租失效**，不能以工具通过替代产品关闭。建议先由已确认接管者修正 handoff 的完整 controller SHA、DB selected rows 可用性及失租时间线，复用原日志/冻结源码，梳理 prepare_import 中大堆与续租/取消检查的位置；尚无依据直接移除 Contract 校验、改 TTL/heartbeat、升资源阈值或归罪 SQLite。既存栈缺口决定了任何后续局部诊断仍须先提出具体问题、最小取证方式和一次性预算范围，不默认要求再跑完整 Submit 或新增 profiler。

本次仅有外置工具/证据审核，产品 HEAD 与最后验证镜像 revision/source-tree 继续取 §57 / §52；没有触发新镜像构建或重复门禁。**h 原 GO 已消耗，无重试、新运行或正式恢复 GO；H3 不变，正式测量停止，lease 根因 OPEN。** 后续任务交设计安排确认接管者，旧实施会话不再由本审核唤醒执行。

## 60. 接任 handoff 与冻结源码映射：只读核对通过

**接任实施者文档提交 `547e5ae388f671568ec4cf83a39b256436eeb560` 的 §59 结果更正与主要源码映射通过，无阻塞 finding。** 已核该提交只改 handoff，并在 clean detached `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 只读检查所引 worker runtime、LeaseSession、prepare handler、import publication，以及它调用的 mutation replay 和 canonical publication/package；没有节点查询、导入产品、测试或新诊断。这里只核事实和建议，不授权实现或运行。

controller 完整/前缀 SHA、191 次成功心跳→失租→stall 的时间线、selected rows 实际可读与 repository_operation_id=null 后置检查、observer 资源/回收、三个耗时口径均与 §59 一致。handoff 顶部将正式测量与后续运行停止写明，避免旧执行计划被读成仍有效授权。末节标题应把 `P6-G-RESULT §59` 更正为 **P6-H-RESULT**，属于非阻塞文书笔误，不影响本次内容结论；保留前文历史记录，由新末节明确更正其口径是可接受的。

源码映射的准确边界如下：

- `worker_runtime._run_claim` 的父循环负责续租，executor 是同进程非 daemon 线程；heartbeat 异常路径会 join 该线程，fence 不等于强制终止 executor。`LeaseSession.heartbeat` 在 mutation lock/事务内核身份、RUNNING、expiry 并传播 cancel，使用 transaction_now 续租。该结构支持分析调度/锁/执行线程响应，但不能从结构本身认定本次哪一处阻塞。
- `build_prepare_import_handler` 在开始和建包/检查点处理后 refresh_control 并检查 cancel；`_build_prepare_import_build_input` 读 ready closure、canonical bindings、parent metadata/catalog。`import_publication` 的 parent materialization 和 canonical publication 分别使用 NeverCancel context，内部物化/排序路径没有传入 worker 的 cancel/lease control；不能把此静态取消盲区直接等同于失租原因。
- changed artifact rows 先形成 `ImportReplayKeyedRow` tuples；`mutation_planning/import_replay.build_import_mutation_snapshots` 再包装 key/image、逐 row digest 并排序。可比较的 changed parent rows 另物化为 `MutationKeyedRow` 并排序，之后 mutation planning、schema/DML/replay SQL，再由 `storage_projection/publish.py` 生成 package、写入/读取并 validate round-trip；package 编码/解码在 `storage_projection/package.py`。这些层各有不同的驻留对象，引用共享不能当作所有内容都深拷贝两次，reader.close 也不证明这些 tuple/list/计划/SQL/package 已释放或 RSS 已下降。handoff 的“可能来源、非根因”限定正确。

**既存材料还能收敛的范围：** 已记录的 current step 为 prepare_import、尚无 Repository operation ID，故优先分析该步骤内的输入转换、mutation 与 publication，不需要为定位此故障把后继 submit_import/await_import 或后续旅程再跑一遍。不能据此排除所有 RS/Dolt 影响：prepare 的 parent catalog/materialization 仍有 RS 只读路径。容器未 OOM、资源线未触、observer 正常、预算未到、没有 heartbeat_busy 事件，已排除这些作为本次已记录的直接停止触发；仍没有失租附近的 Python 业务栈、heartbeat 实际入口/返回和 lock/事务等待时段，所以 SQLite、GIL、GC、mutation lock 或某段序列化均未获唯一归因。取消盲区与 join 还关系到失租后的退出响应，应与“为何先失租”区分。

**下一步建议不必默认完整真实 Submit。** 先交设计一个最小具体问题和局部候选：复用冻结 builder 及已绑定输入/parent 事实，按需要覆盖真实 changed-table 形状的 prepare 子链，在少量粗阶段入口/出口记录 duration/RSS；局部构造可以回答哪段消耗/持有大堆，不能凭小样本或不同 shape 推断现场完成时间。若问题转为续租为何越过 deadline，应区分 runtime due/实际 heartbeat 入口/返回与本地 deadline，保留相同线程和 LeaseSession/事务边界；纯内存 heartbeat 或假 DB 不能证明 SQLite 现场原因。只有局部路径确实无法保持必要边界时，再具体说明为何需要真实 DB/容器或完整 prepare；不能直接跳到完整 Submit。这里不是要求依次跑两套诊断，而是让设计按首要证据缺口选择一次必要范围。

粗阶段记录应复用已有入口与结果，不逐 row/key 排队、不重建持续 profiling/GC hook；不取消 Contract/digest 校验，不临场加时。候选准备前说明输入与现场差异、估算依据和未知项，再按 §56 固定一次性预算；旧合成 probe 截断值不足以预测完整 prepare。handoff 的“若 owner 决定继续诊断”不应成为重复授权门槛：按既有 DC80，由设计先形成并审具体最小范围，随后工具/清单/一次 GO 分别办理；没有新业务取舍时不需再等 owner 重确认。当前提案仍只是方向，未授新取证或运行。

结论直接交新唯一实施会话 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 并抄设计，后续不唤醒旧实施者。产品/镜像输入没有变化，不触发重建或重复 Compose；最后验证 image revision/source-tree 仍见 §57 / §52。**h GO 已消耗，正式测量停止，lease 根因 OPEN。**

## 61. prepare-only 续租诊断：具体设计范围通过

**设计 `fd19703bf487db9cdd8c681169013277e015759b`、`p6-prepare-step-lease-diagnostic-plan.md` 定向范围通过，无阻塞 finding。** 已读实际新增设计，并只读冻结 `1f9731` 的 WorkerRuntime/WorkerLifecycleController、bootstrap composition 与前述 acceptance/prepare 调用边界。未访问节点、执行测试或新诊断。新唯一实施者可按本范围准备外置候选和少量 CT05 focused 工具测试；这是准备范围通过，不授 acceptance POST、启动诊断栈或其他业务运行 GO。

本次从完整 Submit 收窄为 prepare-only，有明确证据依据：h 在 prepare_import 失租，且尚无 Repository operation ID。一次真实 acceptance 复用原 route/application/事务，避免为省 HTTP 建手造 DB 或第二套 acceptance；保留真实 parent catalog/materialization，不能称完全离线计算。acceptance 创建 PREPARED attempt/QUEUED operation/PENDING prepare 本身是有状态业务写入，仍须等待最终候选专属一次 GO；完成 prepare 也不等于完成 Submit。

停止下一 claim 的实现方向已有冻结源码支持：原 `_run_claim` 正常返回前已 join executor、验证 acknowledgment 并 mark_executor_completed；没有提前 drain 的正常路径仍为 READY_TO_CLAIM、executor_active=false。之后调用同一 lifecycle 的 request_drain 转 DRAINING，原 run 循环会在下一次 claim 前完成 clean drain。**只在原调用正常返回后请求 drain，不放在 finally，也不在执行中提前 SIGTERM。** 异常原样传播、单 worker/no-restart、唯一目标 operation/prepare/attempt 与原函数只委托一次的要求足以表达局部边界，不需复制 claim/heartbeat loop、改变 drain timeout 或新建状态机。successor 的正常持久化保留，结果再核 prepare terminal、submit_import PENDING 且未 claim；不能为了实现“单步”跳过 successor 事务。

候选必须落实设计已列的 acceptance→worker 身份绑定顺序，不能只写概念保证。可利用仅 backend/RS 就绪后 acceptance 取得目标 ID、再启动唯一受控 worker 等现有接线，或给出同样明确的无竞态顺序；不额外要求新增通用启动 gate。来源其他可领取/恢复工作、实际目标 claim 的核验及未知任务拒绝仍必要。no-restart 要核实际 Compose override/容器配置，不以 worker 正常退出的意图代替防止重启领取后继的事实。具体 override、入口挂载/命令和 production composition 的绑定待候选审核；本节不预先声称容器接线已验证。

观测收窄合理：既有 prepare 函数入口/返回及同线程嵌套深度可回答最后进入/未返回的粗阶段，不能将嵌套耗时重复求和；保留所有原校验、返回值和异常。`_run_claim` 的真实 claim_anchor、`_heartbeat_until_due` 的实际入口/返回参数和 `LeaseSession.heartbeat` 入口/返回，足以区分 helper 入口前的延迟、入口时已过 deadline、session 调用内的滞留。derived due 必须明确派生，不叫实际 loop-entry；session 调用内部同时包括 mutation lock/事务等，当前不插入细分是合理的最小范围，不能据这些事件唯一归因 SQLite/锁/GIL/GC。

**不再使用 py-spy 或有效栈前置条件的变更通过。** h 已有可选采样持续缺失的事实，本次用已绑定入口 ready、实际 worker PID/starttime/镜像、guardian 就绪和明确函数边界直接回答新问题；这不是降低产品校验或忽略必要资源守护，不需要重复旧 canary。候选须证明 ready 属于真正加载这些 wrappers 的目标 worker，不能只有外层 controller 自报已就绪。记录线程 ID/monotonic，并保留“入口前未进入”和“入口后未返回”的证据差异，不把线程活跃当续租成功。

每条 2 KiB、总量 4096 条/8 MiB 的标准有界日志，阶段与约 10 秒一次的 heartbeat 事件规模相称；RSS 复用原 5 秒外采样，无逐 row/key、GC、stack 或热路径 fsync。日志写入会扰动同进程调度/I/O，设计已经说明，不能将新结果当正式性能。候选对写入/上限/必要观测失败须明确诊断缺口与停止分类，并仍保住单步及回收边界；不把 logging 异常改写成产品 lease 结论。未要求自定义持久队列或新的 evidence 状态机。

45 分钟绝对上限、3600 秒外层上限及原资源线不变，h 的 2114 秒失败窗口只支持预算覆盖选择，不证明完成时间。具体起算点须将初始化和清理纳入设计所说的外层约束，不能把几个各自独立 timeout 的和称为整次 3600 秒。lease_lost/cancel/stall 后仍保留实际 fence/join 语义，不能假定 Python 线程可以被安全强杀；外层仅对自有进程/容器有界收束，强制退出与正常 prepare 完成分别记录。未回收不解锁、保卷不重试和关闭 controller 后另记完整 SHA 均落实 §59 已发生的问题。

少量 CT05 工具 focused 覆盖真实 run 委托及成功后 drain/no second claim、目标/异常拒绝、真实参数与 derived 标识、记录上限和未回收不解锁即可。不要求重跑已通过的合成 probe、小 Compose 旅程或全量 runner，不为该外置诊断准备重建相同产品镜像。产品 HEAD 继续 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、最后验证三镜像 revision/source-tree 取 §52/57；新的 override/入口边界必须在具体候选中审清，并在获准实际诊断时核运行身份和退出事实，不能称这些新接线已经 carried。

结论已直接交新实施者并抄设计，可接续准备，无需 owner 重复授权。最终清单、源码/工具/override 摘要、测试证据、输入、预算及固定命令仍待独立审核后给予专属一次运行 GO。**当前无新运行 GO；h GO 已消耗，H3 不变，正式测量停止，lease 根因 OPEN。**

## 62. P6PREP-REVIEW-20261106-01：候选 a 初审需修订，六项阻塞

**manifest `0ef213ab81f19cf4424c8afb18e90d9fa5d6c94f574b6e15881774d2665a3d67` 尚不能取得运行 GO。** 已只读审核 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6preparelease20261106a/candidate/` 的最终 14 文件、清单、准备记录、全部 controller/worker/Compose/测试接线，并对照冻结 `1f9731` 源码。完整 manifest、实际文件集合/SHA/权限及 Python AST 均匹配。测试时清单 `f3a0a66100bbc6f1eb1f0a153b2af82f8ef168b5f9e93b99020f953de48bdd97` 实际字节已保留，最终仅 preparation-record/review-request 内容变化；运行和测试代码未变。

按 SSH echo OK 前提，只读取得 CT05 既存 `focused-tests.log`，完整实际 SHA256 `b2e3c4a499fd35a4b16e527544f9b249ad89fce1e25f227dc2a082f1dc75503b`，记录 15:05:43–44、起止 `1f9731`、5 passed/exit 0 与解锁。这些通过记录真实，但测试用自建 Fake Runtime/Lifecycle 和 predicate，没有覆盖以下实际 controller 路径。审核未运行测试、导入候选/产品、查询运行容器或发 POST。§61 的设计方向仍成立；以下是具体候选接线问题，不是要求扩张产品范围。

### P1：新证据文件在创建前 chmod，正常启动必失败

`prepare_step_controller.py:78–83` 的 `_write_json` 创建父目录后，对尚不存在的目标 `path.chmod(0o700)`，随后才 `path.open("x")`。新证据目录按要求为空，首次调用写 `EVIDENCE/preflight.json`（1037 行）就会 FileNotFoundError；finally 对 result/postflight 的相同调用也会失败，连停止/收尾记录都不能保存。这不是需实际 POST 才能确认的问题。

使用现有 umask 或在独占创建文件后设置所需文件权限，保留拒绝覆盖语义。补一个使用真实临时目录的“新运行证据可创建、重复写拒绝”工具用例即可，不需要 Compose。

### P2：isolated controller 无法解析同目录 resource_watch

`run-once.sh:74` 用 literal Python **`-I -B`** 执行 controller；controller 只在 993 行加入 BACKEND，没有将候选目录加入 import 路径，也未通过 `_load_module` 注册 resource_watch。611、685、934 行却普通 `from resource_watch import ...`。isolated script 不把脚本目录加入 sys.path，因此真实 worker ready 后首先在 611 行 ModuleNotFoundError，尚未进入资源监控；cleanup 的同样导入也受影响。focused 测试的加载方式未到达这些导入，不能证明此路径。

沿现有显式文件 loader 加载已经清单绑定的 helper，或使用等效受控模块接线，保留 -I。用实际 isolated 入口的最小导入检查绑定此修订，不要求启动 worker。

### P3：restart policy 读错 Docker inspect 层级，合法 worker 被拒绝

`prepare_step_controller.py:591–605` 从 **Config.RestartPolicy** 读取重启策略；标准 container inspect 的该字段在 **HostConfig.RestartPolicy.Name**。本仓库已有 h 的真实 inspect 亦如此。合法 restart=no 会被读成 None，ready 必报 identity binding differs。771 行的运行中复核同样错误；835 行记录也用错层级。这个故障发生在 acceptance 已实际写入之后，会白白中止一次机会。

统一修正真实字段来源，保留 restart=no、RestartCount=0 和实际 image/PID 绑定。使用已有真实 inspect 形状的受控 fixture 覆盖 ready/监控/退出读取，不能用测试造出 Config.RestartPolicy 来配合错误实现。

### P4：成功发布的 PENDING successor 被当成未知工作，且正常快速退出存在误判

`prepare_step_controller.py:746–763` 先读取 active steps，并在 749 行拒绝任何不是 prepare step ID 的 active row，之后才检查 prepare terminal。冻结 handler 的成功事务必须创建 **submit_import=PENDING/attempt 0**；原 runtime 又按包装立即 drain。监控看到合法 successor 时因此先报 unknown_claimable_work，无法走设计要求的成功后置核验。两次独立 DB 查询还可能跨这个正常转换，不能只按一次读取的先后假设其不出现。

监控和 `_post_snapshot` 使用一致的允许状态：唯一目标 prepare 运行，或该 prepare 已成功且仅其预期未 claim successor PENDING；其余工作/已 claim 后继仍拒绝。另一起修复 730 行先读 PID 资源、后查 terminal 的完成竞态：worker 正常完成并退出时 PID 已不存在，不应在确认 terminal/正常退出前一律误报 resource_unreadable；`compose ps -q worker` 也不能作为获取已退出 worker 的唯一方法。用成功转换/正常退出的 focused 场景证明，不要靠真实 acceptance 试错。

### P5：3600 秒硬边界与 5 秒必要守护没有独立执行保证

`run-once.sh:74` 直接同步执行 controller，没有外层 watchdog；`run_once` 的 deadline 仅由部分 `_remaining` 调用协作检查。source/input 验证、复制及多处 Docker 调用不受剩余总预算约束，ready 另开 180 秒窗口，cleanup 240 秒后还可追加独立 30 秒查询；signal handler 只设 STOPPING，且仅 monitor 循环处理。因此文档“整体包含初始化/清理的 3600 秒硬上限”未实际成立。

同一 `_monitor_prepare` 在 728 行先同步 `_worker_logs`，该函数先 compose ps（20 秒）、inspect（20 秒），再 logs（10 秒），之后才执行 5 秒资源检查；此外还有 DB/inspect 调用。只要这些调用变慢，必要资源守护会随之停顿，不能把同循环内 `RESOURCE_SECONDS=5` 当作独立 5 秒 guardian。它还每秒重复读取 60 分钟全量 worker logs，与最小扰动目标不符。

复用既有已审的独立有界监督方式落实总截止及必要资源检查，明确业务停止、清理保留时间和回收失败留锁；控制命令按真实剩余预算收敛，不以多段 timeout 的和冒充总量，也不为此新建通用框架。避免每秒重复全日志扫描，日志缺口检测与最终原始日志保存各有界即可。focused 可用受控慢命令/时钟 seam 验证 guardian 和总截止仍推进，不需要新业务负载或修改产品 TTL。

### P6：down 前未保存原始服务日志/失败末态，POST 异常会错误记 0 次

`_worker_logs`（791–804 行）读取 product stdout/stderr 仅搜索 gap 后即丢弃；`_cleanup`（903–910 行）直接 down/remove 容器，没有把 backend/worker/RS 原始日志保存至证据。原 bootstrap 异常 traceback、最后原生 heartbeat/lease 记录会随容器删除失去本次可复核入口；自定义 worker-events 不能代替完整原日志。`_post_snapshot` 只在正常 monitor 返回且 worker exit 后调用（1130 行），失败/失租路径也没有保存最后可读的目标 DB selected rows。这样新的 35 分钟失败可能又只剩观测事件和概括错误，违背本次保留原始证据的范围。

此外 acceptance_post_count 默认 0，仅 `_accept_once` 成功返回后在 1081 行改为 1。POST 已发出但 HTTP/解析/ID 核验失败时，报告仍写 0，不能据此判断是否允许重做。应在调用前记录“唯一尝试已开始”，将已发送尝试、响应/业务接受是否确认分别表示；无论响应如何都不重试。不是要求把未知状态强行判为接受成功。

在有界清理前保存已有 Compose/container 原始日志、已知 identity/exit 事实及失败时最后可读 selected rows，记录各自采集错误，不因缺少 repository operation ID 再丢弃已经获得的字段；然后 down 保卷。结果保留最后已知目标/claim/观察状态，不能只有成功返回才记事实。日志关闭后在外层计算完整摘要。只补已有诊断范围内的留证与计数，不增加 profiler、逐行跟踪、持久状态机或新业务验证轮次。

### 修订与复审范围

原始候选 a、两份 manifest 和通过日志保持不改写；新实施者已确认先保留原包，待本合并报告后准备独立修订候选。以上六项都针对实际边界，少量新增 controller focused 应覆盖新文件/isolated helper、标准 inspect、prepare→successor/正常退出、监督不被慢命令阻塞、失败留证与 POST 未知结果；复用当前 fixtures 和已审 helper，避免只继续测试 Fake Runtime 的正常顺序。现有 worker 正常委托后 drain、异常原样传播、真实 deadline 与 derived due 区分及事件上限方向可保留。

仅外置工具变化，不要求重建 §52 镜像、重跑已通过的小 Compose/全量 runner 或发一次 acceptance 验证修订；产品 HEAD `1f9731`、最后验证三镜像 revision/source-tree 沿 §57。修订代码、测试及精确清单重新绑定后定向复审；本报告也不预先授权另一个候选运行。**没有新 GO，h GO 仍已消耗，正式测量停止，lease 根因 OPEN。** 发现直接投递新唯一实施者并抄设计。

## 63. prepare 候选 b 复审：主要接线已修，守护与最终收束尚有三组问题

**manifest `b7b57790caaaffb5200131ce44e8103adb304b04afc425b590462eda1bbf7e9c` 本轮不获 GO。** 只读最终 b 包、a→b 差异、17 项测试及现有证据；没有运行候选/测试、访问节点或新增取证。独立核最终清单、14 文件 SHA/权限/AST、测试时清单 `6076f314d7a4e2c8b07b2a63d477f46bd70ee63179f0e7de8e7988e0f17aa4f5` 和 retained 文件字节全部匹配。测试后仅 README/preparation-record/review-request 变化，代码与测试未变，未要求为文书传输修正重跑测试。

完整 `focused-tests.log` SHA256 `6139dbec602b89e54591e7b604d7d3731f4cc3329bff29b0271f8d309fc0c8bc`，CT05 16:31:54–55、起止 `1f9731`、17 passed/exit 0；最终绑定记录 SHA256 `570b7a785b5f60582530680b5b8bfd7b8d83acde9f643ee2cda6f1a49a6d1608`、MATCH/no GO。误传文档副本与失败记录 SHA256 `9f8380d483e4ebf57189aaadf52344283f907d539aee54d2cff475a21e338272` 已留档；按 DC80 最小恢复处理，未把已经写入的根目录副本说成无副作用重试。

§62 前四项的主要修订可以关闭：新文件 O_EXCL 后设私有权限；isolated controller 用固定文件 loader 取得 resource helper，实际 -I 导入测试通过；统一从 HostConfig 读 restart policy，并以保存的 container ID 覆盖已退出 worker；同一个 SQLite read transaction 取得目标及 active rows，允许成功 prepare 的未 claim successor，terminal 先于 live PID 检查。POST 调用前记录一次尝试、未知响应只读按既有 idempotency 记录定位，且失败路径在 down 前保存末态/原始日志的方向也正确。外层 timeout 与独立 guardian 已加入；下面是其新具体路径未闭合之处，修复不需要扩大产品/诊断范围。

### B1：监护空窗及最终 guardian 停止结果未纳入成功判定（§62 P5 未完全关闭）

`resource_watch.py:156–216` 只有 worker-binding.json 存在时才读 host/disk/worker 资源；没有 binding 的循环只检查时钟/parent/gap 后等待。controller 虽在初始化前启动 guardian，但 `_write_worker_binding` 在 `up worker` 和 `_verify_worker_ready` **完成之后**才调用；此时真实 worker 已可 claim/执行 prepare。ready 包含 Docker 查询和 DB 读取，最长等待 180 秒，因此这段时间不能宣称有独立 5 秒资源守护，已有慢 Docker 不应拖住 guard 的测试只覆盖 binding 预先存在的情况。

在初始化时明确绑定 host/data filesystem 并持续监测；worker 实际进入无约束 prepare 前，应保证同 PID/starttime 的必要 worker 监护已就绪，而不是等 ready 查询全部结束才开始。具体采用最小既有入口/监护交接即可，不要求建立通用启动状态机；若需要在外置入口暂候监护绑定，不能改变 production heartbeat/claim_anchor 的含义。

同时，`_stop_guardian` 的 guardian_result 只被并入 cleanup/postflight，最终返回成功的条件不检查其 status/stop_reason 或必要结果缺失。若 guardian 在 monitor/exit 最后一次 `_check_stop` 后、post-state/finalization 前报告资源/观测错误，或者提前退出而结果不完整，当前代码仍可能只凭 process reaped 报成功。应在最终结果分类中保留这一停止/缺口并返回诊断非零；**回收已确认时仍可安全解锁**，不把“业务/观测失败”重新混为“进程未回收”。补 binding 尚无、ready 慢和最后时刻 guardian 停止/结果缺失的 focused 边界，不重跑业务。

### B2：日志采集的 EOF/退出等待仍可越过自身界限，未回收 helper 可被遗漏（§62 P5/P6 残留）

`prepare_step_controller.py:1150–1177` 的采集循环以“selector 还有 fd 或 process 尚存活”为条件，deadline/TERM/KILL 却仅在 **process.poll() is None** 时执行。Docker CLI 退出但继承 stdout 的子进程仍持有管道时，没有 EOF，循环会持续；deadline 之后 selector timeout 变成 0，还可能忙转。对 Docker CLI 超时只杀 parent 而 plugin/descendant 保留输出管道，是正常故障收束需处理的情形，不依赖恶意同 euid。外层 3600 秒 kill 只是最后保护，不能把当前阶段耗尽整个清理 reserve 当成已按 20 秒界限收束。

异常路径 1197–1202 行对 kill 后 `wait(timeout=1)` 再超时直接 pass，返回 record 没有 child PID/reaped=false；`_finalize_run_resources` 只把 guardian 的回收状态合入 postflight，owned_processes_quiet 由容器/网络/guardian 推导。因此日志采集 helper 尚未确认回收时，也可能允许节点锁释放，违背已审自有进程静止条件。

让读取/EOF 等待本身受绝对截止约束，必要时关闭读端并明确 truncated/timeout；使用标准进程控制对自己的采集子进程/进程组有界退出与回收，留 child PID/exit/reaped/elapsed。把不确定回收传入现有 postflight 的 owned_processes_quiet/锁判定，未确认则保留锁；不创建 broker、持久状态机或广泛扫描其他进程。增加一个保留管道的受控 CLI fixture 和未回收结果传播用例即可，原 byte-cap 测试仍可保留。

### B3：正常 finalization 分支引用未赋值变量，摘要缺失被吞后仍可返回成功

`prepare_step_controller.py:1701–1756`：正常已有 journey/env 时只接收 `_finalize_run_resources` 返回的 pre_down_record/cleanup_record；guardian_record 仅在 **else** 分支 1733 行赋值，1753 行却在两条路径都使用它。正常路径必然 UnboundLocalError，被宽泛 except 吞掉，只记 pre_down_finalization_record_write_failed=true，`pre-down-finalization.json` 不会写出。最终成功 predicate 并不看这个标记，仍可返回 0。这是具体作用域错误，不是要求补充新的证据机制。

从实际 finalizer 返回/cleanup 中取得统一的 guardian 记录，保证正常和异常路径写相同的已有摘要；真正写失败按诊断证据缺口记录、不能宣称全部观测完成。当前测试覆盖 `_finalize_run_resources` 辅助函数的调用顺序，却未覆盖它在 `run_once` finally 中的实际接线；针对该正常 finalization 路径补最小回归，而不再造一套 fake worker loop。

三组问题已直接交新实施者，沿 DC80/§61 的常规修订、必要 focused 和清单复审闭环，不等协调者中继。保留 b 原包、测试时和最终清单、现有日志；独立修订包只针对这些路径，已经关闭的问题和未变代码不用重复证明。若代码实际变化，再按受影响范围绑定新测试，不能只换清单沿用未匹配的实现证据。

本轮仍只涉及外置工具，不触发产品或 §52 镜像重建，不要求重复 Compose、小合成 probe 或全量测试；产品 HEAD 和最后验证 image revision/source-tree 继续 §57/61。**没有新 GO，h 原 GO 已消耗，H3 不变，正式测量停止，lease 根因 OPEN。**

## 64. prepare 候选 c 准备期：focused 失败按 DC80 直接修订，B1 接线补充

本节记录准备期检查，不是候选 c 最终清单复审或运行许可。只读本地已有日志、候选文件和冻结 `1f9731` 源码，没有执行候选/测试、访问节点或运行业务。`focused-targeted-tests.log` 独立 SHA256 为 `ffaadcab0d377fdc9cd9773313a9aca524f441ed265d85f8c4d71507a0ddd1ff`；测试时清单 `focused-tests-candidate-manifest.json` 为 `e5cd7b77ecd08f22e34e5da178f89047376266a77d78309272a94c7eaf815a53`。CT05 17:25:12–15、起止 `1f9731`、10 passed / 4 failed / 12 deselected、exit 1，节点锁已释放。

四项失败分别是：旧 slow-command guardian 用例只有 worker-binding，缺少修订后必需的 host-resource-binding，尚未取得样本；正常 finalization 参数用例中的三项在 rc/status/可解锁检查通过后，将正常省略的顶层失败字段 `None` 与 `False` 作身份比较而失败。生产路径只在写失败时加入该 key=true，postflight 则始终输出明确 bool。因此可补齐真实 fixture，并分别断言正常 key 不存在、故障 key=true 及 postflight bool；保留原有 rc/status/锁释放/最终摘要检查，不为测试改生产输出约定。

这是工具调试用 focused 失败，按 DC80 直接定位、最小修订及必要重测，不是已开始的权威 runner 或实际诊断失败，不需 owner 逐次许可。已直接告知唯一实施者保留失败日志、测试时清单和修订差异，新测试日志绑定新测试 SHA/清单。未变且已有通过证据的路径不用重复运行。

准备期只读另发现 B1 新接线仍有确定问题：当时 `prepare_step_worker.py` SHA256 `a3e6d0767bd816783aa662a31c765ed760434b9e186e62d5242119b8c29a937f`，runtime builder 对返回实例赋 `runtime.run_until_drained = ...`。冻结产品 `WorkerRuntime` 使用 `__slots__`、无实例字典，也未声明该 slot，实际 builder 将在此抛 AttributeError；新增测试返回 SimpleNamespace 掩盖了约束。已直接要求使用现有 class 级 hook 或等效最小委托，保留原 run loop/claim 之前等待，并用真实类或相同 slots 约束的 fixture 覆盖；不能发 POST 试错。若 class 级入口影响原委托/drain/no-second-claim 用例，相应 focused 一并覆盖。

当时 controller SHA256 `99d9f6f12920c88064cff75fbfea16009354b708742883d523822fc26270d691` 的 host binding 仍在 `_resume_source` 完成校验与复制之后才写，guardian 的初始化前段仍无 host/disk 样本。已要求在既有初始化接线中提前绑定实际 data filesystem、覆盖校验/复制，再核目标 control 卷设备一致性；注意 host/worker binding 当前还比较路径字符串，不能仅核 st_dev 后写不一致的路径。两点都属 §63 B1 的最小修复，不扩大观测、产品或预算范围。

实施者已直接收到并接续修订；最终候选清单、受影响 focused 和剩余 B1–B3 结论待后续复审。**没有新的诊断 GO，h GO 已消耗，产品与镜像继续冻结，H3 不变，正式测量停止，lease 根因 OPEN。**

## 65. prepare 候选 c 最终复审：B2/B3 关闭，B1 使用不存在的 runtime 入口仍阻塞

**最终 manifest `8069dc64c32178ebce0994e9dbbc615eced89d4eaffcbb691cf37f5b9b10c192` 不获运行 GO。** 独立核验最终 14 文件集合、SHA256、权限和全部 Python AST，均匹配；只读冻结审核 worktree 的 HEAD 为 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、状态干净。没有执行候选/测试、访问节点、启动业务或发 POST。本节审核新增工具接线，不要求产品或 §52 镜像重建；最后验证 image revision/source-tree 继续 §57/61。

§64 的初次失败日志和精确清单已保留，`candidate-run1/` 的 14 文件与模式也逐项匹配该清单。重测清单 `focused-targeted-tests-rerun1-candidate-manifest.json` 的独立 SHA256 为 `2cef36aa1bb046f6e1d891d772e411d2faafaa4bb952602af4688c6591c8388b`；原始重测日志 `focused-targeted-tests-rerun1.log` 为 `e883fb4eb98f8a0317f559d3b57428d9c23a35e443cb4c5a821c6bc958211c63`，记录 CT05 17:43:19–20、起止 `1f9731`、8 passed / 19 deselected、pytest/script exit 0、锁已释放。最终相对该测试时清单只变 README/preparation-record/review-request，运行代码和测试未变。通过记录真实，但不证明未覆盖的真实产品 API。

### 可以关闭的修订

B2 的采集循环现在无论 direct child 是否已退出都执行绝对 deadline；使用自己的 session/process group 作 TERM/KILL 和有界 EOF 退出，保留 capture PID/exit/reaped/group quiet/elapsed。不确定回收传入现有 postflight 并保留节点锁。受控 descendant 保持输出 pipe、byte cap 及未回收传播用例已在初次 focused 中通过，相关代码最终未变；不把该轮整次 exit 1 写成权威 runner 通过，也不要求重复这些未变路径。

B3 的正常 `run_once()` finally 现在统一接收 pre_down/guardian/cleanup 三项，写已有摘要；guardian STOPPED/结果缺失和 finalization 写失败会把原拟成功结果降为非零。四个实际 finally 参数用例在重测中通过，保留状态、摘要及安全解锁断言，正常顶层 key 省略与 postflight 明确 bool 的约定也核实。观测失败与进程已回收分开判定，已静止时可释放锁。

B1 的部分修订可接受：host/data filesystem 在只读 offline/source preflight 后、checkpoint clone 及服务启动前绑定，随后校验目标 control 卷设备；不能表述成 controller-start 之前已有 host 样本。guardian 允许同设备的 host-root/volume 不同路径，并在真实 worker PID/starttime 首样本后发布 marker；late guardian stop/缺失结果已进入最终失败分类。这些改进不弥补下面的启动 API 问题。

### B1 剩余阻塞：真实产品没有 run_until_drained

最终 `prepare_step_worker.py` SHA256 为 `a4c82399129c323be40648a9aaf536c82dfca39e54aeea043a0b1d94a9410516`。391 行直接读取 `worker_runtime.WorkerRuntime.run_until_drained`，398 行再覆盖同名方法。冻结产品 `operations/worker_runtime.py:166` 实际定义的是 **`run(self, drain_requested, wait)`**，bootstrap `operation_worker.py:455` 实际调用 **`runtime.run(stop_requested.is_set, stop_requested.wait)`**；该类没有 run_until_drained。故 `_install_hooks` 读取原方法即抛 AttributeError，尚未构建 runtime 或进入 guardian 等待。实际流程此时已发 acceptance，不能靠一次业务运行验证这个可静态确认的错误。

当前测试虽加入 `__slots__`，仍自建了产品不存在的 `run_until_drained`，因此 slots 和 gate 顺序通过不能代表真实入口接线。**§64 上轮审核只指出实例赋值的 slots 问题，未继续纠正这个方法名；本节按冻结源码校正该遗漏。** 应在外置工具中 hook 真实 class `run`，保持原参数、返回/异常、startup/claim 以及真实 claim_anchor 起算不变。用冻结真实类/API 绑定的最小 focused 证明 gate 在原 run 之前且仍委托原入口；不再只靠带相同虚构方法的 fake loop。若修订影响原成功后 drain/no-second-claim 场景，一并定向覆盖即可，不新增产品机制、TTL 修改、Compose 试跑或全量 runner。

另有文书事实错误：preparation-record 的 identity 部分称候选 b “one candidate run remains spent / result awaits independent review”。b 按 §63 未获 GO、未运行业务；已消耗 GO 且有实际结果的是 h。该处应改正并重新绑定文档清单，无需为文书更正重测。

阻塞和最小修复范围已直接交唯一实施者，抄设计；可沿 DC80 继续修订与受影响 focused，无需 owner 重复许可。保留本轮最终 c、测试包/manifest 和日志，新的代码/测试与最终清单重新绑定后再定向复审。**本轮无新 GO，h GO 已消耗，H3 不变，正式测量停止，lease 根因 OPEN。**

## 66. prepare 候选 c revision 2 复审通过，精确清单一次诊断 GO

**候选审核 PASS，§65 的 B1 剩余阻塞关闭；仅向下述 revision 2 manifest 给一次诊断 GO。** 最终清单路径为 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6preparelease20261106c/candidate-manifest-revision2.json`，完整 SHA256 **`e330a9fb79ca8b48885b4cb162b9148211cd925a0f4d3a67e5e1d1ddc72b974f`**；候选目录是同根下 `candidate-revision2/`，candidate ID 仍为 `p6preparelease20261106c`、candidate_revision=2。旧 `candidate/` 和 manifest `8069dc64c32178ebce0994e9dbbc615eced89d4eaffcbb691cf37f5b9b10c192` 逐字保留，不获本次 GO。

本地独立核验最终 14 文件集合、SHA256、权限及 Python AST，全部匹配；相对精确测试时清单 `focused-targeted-tests-rerun2-candidate-manifest.json`（SHA256 `115f701a69c73155db70c09898b1d0ee1ee8aae19575c38d663ecb96a29662e6`）只变 README/preparation-record/review-request，代码/测试/绑定及全部模式未变。按 BatchMode echo OK 后，只读 SSH 独立核 CT05 最终 14 文件/模式均 MATCH、HEAD `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` clean，实际日志摘要一致，发本次 GO 前 POST-GO 不存在。审核没有执行测试、候选、Compose 或 POST。实施者最终 CT05 binding 日志 `candidate-revision2-final-binding-check.log` SHA256 `88ad97a52c6ceb658ae51a1d6aacd8c894224c62d44fe00997288fc4bc8a8a2c`，18:04:56、同一最终 manifest、14 文件、review-only MATCH。

`prepare_step_worker.py` 最终 SHA256 为 `839e4753f55ff384520d512be85bd56a40f87a5f34a036fc4ee50d6896279b1a`。现在 class 级 hook 读取/覆盖的是冻结产品真实 **`run(self, drain_requested, wait)`**，先等待同 PID/starttime 的 guardian 首样本 marker，再原样传两个 callable 到原 run；不向 slotted 实例加字段，不增加虚构 API，不改原 startup/claim 或 claim_anchor 起算。真实 runtime 子类用例继承生产 run，证明 guardian 等待先于实际 startup，并保持原异常对象；claim hook 用例证明原 anchor 及原调用正常返回后才 request_drain。简化 fake 的单次调用本身不作为真实 loop 无第二 claim 的独立证明；冻结原 loop 在下一次 claim 前处理 DRAINING 的控制流与 §61/65 一致。没有提前 SIGTERM、修改 drain TTL、替换事务/续租或复制生产循环。

CT05 focused 原始 `focused-targeted-tests-rerun2.log` SHA256 **`5d60258a557c8d2e28588c77d6d788b80a3651ad5af15514683fc6abe9284a70`**；17:57:18–19、起止 `1f9731`、**2 passed / 25 deselected / 0.64s、pytest/script exit 0、节点锁已释放**。postflight 日志 SHA256 `1caff0ad0d2746957dfef935c2c4e5161915bbc8516ff3f00994b3bb5a5d0863` 记录 clean、busy lock absent、8000 unused、no Dolt。测试没有发 HTTP/POST 或启动 worker/Compose。准备记录一处称 focused 日志直接记录 wrapper SHA；实际原始日志打印的是 verifier/test SHA，wrapper SHA 由该日志所绑定的精确测试时 manifest 记录。本节澄清其证据来源，不因此修改已冻结候选或要求重测。

controller 最终 SHA256 `0ce89c8319e674321049b56fc79f9a5cb498c0ed198852aef03d6d2bb5cf54ec`，相对 §65 只改候选/manifest 字面路径；verifier、两个脚本及 Compose 环境挂载均一致指向 revision 2，不会读取旧 c。host/data 采样与 PID 绑定、末尾 guardian 成功判定、B2 日志截止/回收、B3 finalization 及一次 POST 计数路径未变，沿 §65 的代码与 focused 结论关闭。b/h 文书状态已修正。两项本地只读路径/校验 cwd 错误有失败日志和修正记录，未触及产品，不引出新的业务许可或测试范围。

### 本次 GO 的精确边界

依已记录的 Owner/DC80 工作流（设计计划 `f7d53c1c41`），审核者直接向唯一实施者投递，不等待协调者回执。本次决定编号 **`P6PREP-C-R2-GO-20261106-01`**，仅用于上述完整最终 SHA256，在 **CT05/root**、clean 冻结产品 `1f9731` 和 §52/57 已审三镜像身份、原 `p6bw4s4h120261105b:v2-preview` checkpoint/既有输入的条件下运行一次。固定 cwd 为 `/home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend`；固定入口为 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6preparelease20261106c/candidate-revision2/run-once.sh`，无参数。执行前由该入口重核源码、清单、节点/缓存与镜像前提；身份或必要缓存不符即停止。

可在该候选根目录写既有格式的 `POST-GO.txt`，内容严格为：

```text
decision=GO
candidate=p6preparelease20261106c
manifest_sha256=e330a9fb79ca8b48885b4cb162b9148211cd925a0f4d3a67e5e1d1ddc72b974f
```

只准克隆三卷到该新 project、一次真实 acceptance POST、一个返回 ID 绑定的 prepare_import claim；正常原 `_run_claim` 完整返回后才 drain，后继 submit_import 保持未 claim。沿用 45 分钟绝对观察上限、3600 秒总上限（含初始化/清理）、既有资源线/120 秒 stall/身份及必要观测停止条件。失败或任一停止条件触发后保存原始日志、最后可读目标状态和回收事实，不自动重试；保留卷及历史证据，自有进程/容器/网络未确认静止时留锁。收束后由外层在日志完整关闭后记录完整摘要，结果交本审核会话独立复核。

**这是一次专属诊断 GO，不是结果通过或正式测量恢复。** 不授权更新产品/镜像、推送、打 tag、清理原证据/卷或扩张观测预算；H3 仍 PASS，lease 根因仍 OPEN，正式测量仍 STOP。本节结论直接交唯一实施者并简要同步设计。

## 67. prepare c revision 2 结果复核：真实失租，延迟位于最后 heartbeat helper/session 调用之前

**§66 的一次 GO 已消耗，prepare 未成功，不能重试或恢复正式测量。** 独立复核确认：固定 CT05 launcher 运行 2026-11-06 18:13:02–18:49:58，控制器结果结束于 18:49:57、elapsed 2215.653s；controller/script exit 1，status=STOPPED、stop_category=diagnostic_stop、stop_reason=lease_lost。本次执行边界、停止及回收证据可接受，但不是产品旅程通过。新函数边界证据缩小了失败位置，**lease 根因仍 OPEN，H3 仍 PASS，正式测量仍 STOP**。

### 身份、一次执行和证据绑定

按 BatchMode echo OK 后只读 SSH 核 CT05：冻结产品仍为 clean `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，运行 manifest 仍为 §66 的 `e330a9fb79ca8b48885b4cb162b9148211cd925a0f4d3a67e5e1d1ddc72b974f`，POST-GO 三行精确绑定一致。launcher 起止 HEAD 相同、记录的 controller SHA 为 `0ce89c8319e674321049b56fc79f9a5cb498c0ed198852aef03d6d2bb5cf54ec`。本审核没有运行候选/测试、发 POST、改卷或启动后续诊断。主日志及关键结果本地/CT05 摘要一致：

| 证据 | SHA256 |
| --- | --- |
| 候选根 `controller-launcher.log` | `c19e7303814d6b6f38ec5da64db6f737b9244527dcb234bde376e57adc956b18` |
| `evidence/prepare-step-result.json` | `ff770c5e1d2fe7d656e21ec4a39f8ca0f1272496a3fb44f4074e1bd5168c13a7` |
| scenario 根 `postflight.json` | `bb01cd2369ccd18f95298a1c35ab5be413bd69933b8007e87223efaeb60265c0` |
| `evidence/worker-events.jsonl` | `0fbdf1b9d3dd0a35f28d39f5db91d3be1364b73493083ad46e1abc0e8b0c45ed` |
| `evidence/resource-samples.jsonl` | `1f7211e916be962cee131d8e8fea531581dd8d36c52dba29d8949e799880f028` |

候选根是 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6preparelease20261106c/`；scenario 根是 `/home/dev/gdds-p6-logs/baseline/scenarios/p6preparelease20261106c/`。preflight 记录原 checkpoint/input cache 及已审三镜像本机身份/labels MATCH、restart=no，无 acceptance 前可领取工作；未改变 §52/57 image revision/source-tree，未触发重建。真实 wrapper ready 的 SHA 是 §66 的 `839e4753f55ff384520d512be85bd56a40f87a5f34a036fc4ee50d6896279b1a`。worker-binding 的 host PID `2784465`、starttime `199857378` 与实际 wrapper/container PID 1/starttime 一致；guardian 首 worker 样本 marker monotonic_ns `1998575323126249` 先于 ready 和 claim。host-root/control volume 同 st_dev `64526`。

acceptance-attempt/response、target ID、事件及 DB selected rows 相互一致：attempt/count=1/1、HTTP 202、RESPONSE_VALIDATED，operation `op-33f22872ee3934e05f64c814`，attempt `sa-887389d969abefdf1dd9ffb4`，目标 step 为该 operation 的 `-step-1`/prepare_import；只见一次 claim_entry、attempt_count=1。末次已保存 DB snapshot 18:46:53 为 TARGET_FOUND：operation/prepare step RUNNING、attempt PREPARED、cancel=false、repository_operation_id 均 null，只有目标 prepare active，没有 submit_import 后继或第二 claim。它是失败时实际 selected rows，不是 prepare 成功/终态，也没有用手写 DB 状态代替结果。

### 失败时尚未返回的业务阶段

同一 executor 线程 `124521208428224` 的边界如下，内层时间不与外层累计：

| 阶段 | 已观察结果 |
| --- | --- |
| prepare_build_input | 18:13:32.740–18:14:39.224，return，66.483s |
| frozen_projection | 18:16:31.871–18:18:15.886，return，104.016s |
| mutation_snapshots | 18:18:15.886–18:21:52.377，return，216.490s |
| parent_materialization | 18:21:52.377–18:36:59.679，return，907.302s |
| mutation_plan | 18:36:59.688 进入，失租及最后证据中没有 phase_end |

失租时 prepare_handler、prepare_package_publish、mutation_plan 三层仍开放；mutation_plan 已开放约 592.435s，但这不是该调用完整耗时或逐内部步骤归因。没有 canonical_publish 的入口记录。对应冻结 `import_publication.py` 的顺序是 parent materialize → plan_import_mutation → render → publish_canonicalization；因此可以定位到 **mutation planning 调用尚未返回**，不能将外层名称中的 publish 当成已完成 canonical 发布或 Dolt commit。

### heartbeat 延迟的实际边界

主监督线程 `124521380375424` 记录 191 次 helper entry/exit、190 次 LeaseSession.heartbeat entry/exit 和 190 次 heartbeat_succeeded；190 次 session 均正常 return，观察到的最大 wrapper elapsed 为 1.005747s，没有 session 异常或 heartbeat_busy 事件。最后几次关键 entry 使用实际 monotonic，与由真实返回 anchor+10s 派生的 due、传入 helper 的真实 deadline 比较：

| helper entry UTC | 比 derived due 晚 | 相对传入 deadline | 随后的 session |
| --- | --- | --- | --- |
| 18:45:52.411 | 0.005239s | 尚余 19.994761s | return，heartbeat 成功 |
| 18:46:19.841 | 17.424816s | 尚余 2.575184s | return，18:46:19.981 heartbeat 成功 |
| 18:46:52.118 | 22.272004s | 已过 2.272004s | 没有进入 |

最后 helper entry monotonic=`2000575.095527520`，derived due=`2000552.823523427`，实际 lease_deadline 实参=`2000572.823523427`。随后 18:46:52.124 出现 lease_lost/error_category=heartbeat_busy_deadline，18:46:52.129 helper 以 StoreBusy 返回异常；没有第 191 次 LeaseSession.heartbeat entry。冻结 `_heartbeat_until_due` 在调用 session 前检查 `now >= lease_deadline` 并 fence/raise，与此轨迹一致。最后成功 session exit 到 lease_lost 约 32.137s，远小于 120s stall，所以本次由真实 lease_lost 停止，而不是 stall 或观察预算耗尽。deadline 来自记录的实参；selected snapshot 未保存 DB lease expiry，不为它推造另一组 DB 时刻。

**本次支持的结论是：最后一次续租机会的延迟在 session 调用之前，进入 helper 时已经越过 deadline。** 不是此次 session 已执行 SQL 但忙等超时；事件名 heartbeat_busy_deadline 也不能单独证明 SQLite busy。入口前的调度、原 loop/observer、GIL、GC、native/Python 工作及外置观测扰动没有被这些边界继续区分，不能据 mutation_plan 同时开放就唯一归因其中之一；不把 derived due 称为实际 loop-entry 或线程被唤醒时刻。

### 守护、停止与收束

事件日志 969 条、321806 bytes、最大单条 422 bytes，未达既定上限。guardian 有 404 个资源样本、64500 bytes，18:13:12 开始 host 采样，18:13:32 开始有 worker RSS；样本最大间隔 5.010405s，最后样本 18:46:48。worker RSS 最大 23894142976 bytes、host available 最小 43288124416 bytes、data free 最小 212212736000 bytes，均未触发既有停止线；这不排除 CPU/调度等非阈值问题。guardian 最终 CLOSED、stop_reason=null、exit 0/reaped，worker_exited_cleanly=false；该 CLOSED 是 observer 的正常收束，不能等同 worker 业务正常退出。

down 前 18:46:53 保存最后可读 DB selected rows 和三服务 raw logs，三个捕获 helper 均 exit 0、reaped/group quiet、无 timeout/truncation，实际字节/SHA 与 raw-service-logs.json 匹配。worker.log 为 0 bytes；没有 claim_exit、clean_drain_requested 或 worker_run_exit 事件，不能宣称原 `_run_claim` 正常返回或 worker clean exit。raw-service-logs 是 down 前的捕获，不是完整覆盖随后约 185s 清理过程的 worker 原生输出；当前没有保存 worker 最终 exit signal/code，不能仅按耗时推定具体强杀信号。既有 source 在 supervision 异常后 join executor，也不能因 lease_lost 就假定 Python 线程已经终止。

最终 controller 以 1 结束，Compose down exit 0，postflight 内嵌/独立 JSON 完全相同，owned/log-capture/guardian/worker 回收及 project containers/networks quiet、postflight_complete、lock_release_allowed 均 true，最终摘要写入无失败。launcher 明确 node_lock_released=true。只读 SSH 复核该 project 的容器/网络均为空、busy lock 不存在、三 target volumes 全部保留，与 postflight 一致；没有把“回收成功”改写成“prepare 成功”。该失败不满足正常 prepare terminal/后继 PENDING 成功条件，也不能作为性能基准。

结论及入口前延迟的具体数值已直接交实施者，正式结果同步设计；不要求为解释现有记录重跑诊断，不新增产品修复、观测或预算。**本次 c GO 已消耗，无后续运行/正式测量 GO；保留三卷、候选、完整原证据。**

## 68. c 结果 handoff 常规事实复核

只读核对 `/home/dev/gdds-p6-baseline/docs/backend-vnext/refactoring/formal/plans/p6-baseline-handoff.md`、该 worktree 的 clean 提交 `117f1a94333e912d7eae3c46172a13e843aff647` 及新增 c revision 2 段落。运行/结束时间、2215.653s、单 POST/claim、各主要摘要、190 次 session return、最后 helper 的 due/deadline 差值、mutation_plan 开放、资源/回收/三卷、h/b/c GO 状态和 H3/根因/正式测量边界均与 §66/67 一致；额外核 SSH 调用日志 SHA256 `9332ecd115058d22cf926baf2652a0357e35951ebbe05bb713159e6202ee41ce` 匹配。本轮没有测试、节点探测、业务运行或新取证。

已直接交实施者两项非阻塞文书澄清：顶部“最后一次 LeaseSession.heartbeat 调用之前”改为“最后 helper 进入时已过 deadline、未进入第 191 次 session”，避免将未发生的调用写成已发生；旧 c “review-only verifier 仍 MATCH/post_go=false”明确为 §66 前历史记录，不能在共享 POST-GO 已存在时称当前 review-only 仍返回 false。只改 handoff，不改冻结候选/manifest/log，不需要重测或暂停设计已派的只读分析。

本轮不触发产品/镜像重建，冻结产品仍 `1f9731`、最后验证 image revision/source-tree 沿 §57。设计已决定由唯一实施者只读收窄 mutation_plan 内部与 EventWriter 时间戳/锁/flush 扰动；本核查不另行授权 probe、大中间 checkpoint、加测、重跑或 TTL 修改，具体新诊断待设计。**§67 的失败结论和 GO 已消耗状态不变，没有新的运行或正式测量 GO。**

后续已只读核实施者 handoff 提交 `fceeb6dd4a1dc312a0ceee2e08a8f18252eaf228`：仅该文档两行更正，分别准确说明第 191 次 session 未进入和旧 review-only 检查属于 GO 前历史；该 worktree clean，现有停止边界未变。两处文书澄清关闭，handoff 常规事实复核完成；没有新增测试、节点操作或运行许可。

## 69. mutation_plan GC/observer 观测范围审核：PASS，仅准候选准备与必要 focused

**设计 `95e2016228e3b5a9b7d8ab381bb7790e13a6450a` 的 `p6-mutation-plan-gc-window-diagnostic-plan.md` 范围通过。** 唯一实施者可直接准备新外置候选和计划列出的少量 CT05 focused，不等待协调者回执。当前不是新诊断 GO；最终精确 manifest、代码/测试/日志和固定命令仍须独立审核后另给一次专属 GO。已消耗的 h/c 许可不可复用，正式测量仍 STOP、H3 PASS、根因 OPEN。本轮只读计划、冻结源码、原始证据及标准 API 文档，没有测试、节点访问、候选实现或业务运行。

有限 GC 例外有已发生的真实漏续租及明确未知区间作为依据，符合比例化政策；它明确替代前计划的 no-GC 观测约定，但不改变产品、GC 策略、线程/续租/事务、信任模型或 owning Contract。新增观测只涉及派生临时诊断状态，用一个自有标准 callback 和小型聚合即可，不引入持久 evidence 状态机、profile 平台或 planner 内部新阶段。固定 `1f9731` 与 §52/57 三镜像不变；外置候选无需产品重建，新增 wrapper/override 的实际接线仍随候选审核。

### 先用现有证据关闭能关闭的分支

c 的 EventWriter 在 JSON 编码和 RLock 之前就生成 monotonic marker。最后 helper entry 的 marker 已越 deadline 2.272004s，helper exception-return 事件的 `elapsed_ns=10383664` 从 wrapper 开头量至返回事件 emit 之前，包含入口 emit 及原 helper 调用。因此最后这次 entry emit 本身不能解释 22.272004s 的 marker lateness，原 helper 实际调用只会更晚，不会因此推翻 §67 的真实失租。已有数据不能拆开**前一次 helper 返回事件的 emit 完成时间**与随后原 loop/调度等时间，也没有 c 的 GC start/stop 区间；不能据此排除 observer 的其他阶段或确认 GC 原因。

旧 100k 探针 checkpoint 13 的独立 SHA256 为 `a6850cee7be0a737d79307ed12c8198ed9f65824102a3eab678f3ca11baf7dce`，路径 `/home/dev/gdds-p6-logs/cold-catalog-repair-20261106/p6changeclosureprobe20261106a/runs/checkpoint-13-builder-stage-payload-construction.json`；已保存 generation 2 max_duration_ns=`2248569206`（约 2.249s），同时记录 events_overwritten=16405。它是另一形状/堆状态的局部 checkpoint，不能按行数、RSS 或堆量线性外推 c 的停顿，也不能把缺失的最终窗口当作没有长 GC。现有证据只关闭上述小分支，**不足以免去全部新问题的现场观测**。

冻结 `import_replay.plan_import_mutation` 构造 request 后直接 `plan_storage_mutation(request)`，没有传可选 artifact_store；c 也未进入随后 canonical_publish。现有材料没有完整可直接重放的 MutationTableSnapshot/request。理论上重建输入不是已验证的磁盘重放方案，而且 GC 问题还受此前分配/存活历史影响，不能承诺用单独重建 planner 输入等价替代真实路径。计划不新增大 checkpoint/pickle、承认 parent_materialization 907.302s 的重复参考成本、只安排一轮且不保证完成时长，范围合理。

### 候选应落实的观测语义和边界

标准 `gc.callbacks` 提供 collection 前/后和 generation 信息，可用于这类统计；它不覆盖所有引用计数释放、allocator/native 工作或线程调度。[Python GC 文档](https://docs.python.org/3.14/library/gc.html#gc.callbacks)支持该用途。冻结 selector 为 Python 3.14.6；[对应 CPython callback 实现](https://github.com/python/cpython/blob/v3.14.6/Python/gc.c#L1117)将逃逸 callback 异常报告为 unraisable，不能依赖异常自动传播到 worker。因此候选自己的 callback 错误必须留最小内存标记，在既有普通观测路径报告 incomplete/必要观测失败；不在 callback 中写 gap/log、取得 EventWriter 锁或扩张为全局 unraisable hook。

固定三代当前区间/统计、每代自上次 snapshot 后的最长一个区间及全程最多 16 个完整区间足够有界，但这是选择性保留。候选要让窗口覆盖起止、计数和任何省略/开放/异常可解释；不能把没有保留到的区间当作不存在 GC，也不能将嵌套/累计时间相加为因果分解。callback 只更新固定规模内存，不扫描对象、不主动 collect 或改 threshold/disable/freeze、不覆盖其他 callbacks；只移除自己注册的 callback，snapshot/记录路径也不能与 callback 形成锁等待循环。CPU 只解释为区间中的 CPU 消耗；[thread_time 只可在同一线程的读数间作差，process_time 是全进程 CPU](https://docs.python.org/3.14/library/time.html#time.thread_time)，均不独立证明 GIL 归属或整段 wall 被 GC 独占。

wrapper marker、entry emit、original call 起止及 wrapper 总耗时应分开。原调用前时间只在 entry emit 完成后取得，原参数、返回/异常及 anchor 不变；返回或异常事件可携带该起点及耗时。若原调用未返回、日志不完整或 worker 在 join/cleanup 中被停止，缺少持久化起点/最终小摘要就是缺口，不增加一次入场写入或延长预算来追求闭合。EventWriter 锁等待/write/flush 统计供下一条事件/最终摘要，不能为测量自身再递归发事件；当前返回事件自身尚未完成的 emit 耗时也不能声称已包含在它里面。

每事件最多三个窗口加固定计数，必须在真实最大形状下仍满足原 2 KiB/4096 条/8 MiB，最终小 JSON ≤32 KiB；达到上限、callback 错误或未取得最终摘要沿既有诊断缺口/必要观测停止分类，不伪装产品失租原因或“没有 GC”。没有最终摘要不能抹掉已经有效的 bounded 片段，但要限制结论的覆盖范围。无需为负面结论新增完整 collection 队列、后台线程或持久证明机制。

原 45 分钟观察、3600 秒全流程硬上限、初始化/清理 reserve、资源/身份/lease_lost/cancel/stall 停止和保卷/未静止留锁不变；新项目/key/三卷副本/证据目录，不能从已失败 c 继续。05 的空闲需在实际执行时取得，不把历史释放当预约，不给 CT108 加负载。仅补真实 callback/有界聚合及 incomplete、最大事件形状、emit 与原调用计时/返回异常透传的 focused；生产 callback 不 collect 与测试为触发真实 collection 的受控调用应区分。保留真实 WorkerRuntime.run/LeaseSession API，不重测已关闭 controller/回收矩阵、旧大 probe、小 Compose 或全量 runner，不排第二轮全输入。**范围通过及候选准备许可已直接投递实施者并同步设计；没有新的 POST、worker/Compose 诊断或正式测量 GO。**

## 70. GC-window 候选 a 初审：两组阻塞，无运行 GO

**`p6mutationgcwindow20261106a` 最终 manifest `1ddb96be4d5081c42f6ae2ac2969056e119a47beae4f2852d2fa9fb114210d45` 尚不通过候选审核。** 独立只读候选目录 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106a/candidate/`，15 文件集合、SHA256、全部模式和 Python AST 均匹配。测试时清单 `d3500bb664ad65b19de53b36319e181e58d079046a0bbd0163ecc870da59f257` 与最终清单仅 README/preparation-record/review-request 三文档不同，12 个非文档文件与所有模式未变。原始 `focused-tests.log` SHA256 `9abc35fb60764df48855087799b428cc4137b8f6363c97ad7e503c6ee183afc8`，记录 CT05 20:10:37–38、clean 起止 `1f9731`、8 passed / 25 deselected / 0.67s、pytest/script exit 0、锁已释放；最终 binding 日志 `1dfb44ccfb9085e316894b887cd60dfbf10c1563b61d4da19d112e8f3347befa` 记录 15 文件 MATCH/POST-GO absent。通过日志真实，但以下范围未获这些测试证明。本轮没有访问节点、执行候选/测试或发 POST。

### G1：最大事件/retention 用例漏选，现有样本不代表真实最大形状

`run-focused-tests.sh:19` 的选择式包含 `test_gc_window_observer`、`test_gc_callback` 等，**不匹配** `test_gc_window_retention_is_bounded_and_event_shape_stays_within_limit`（测试文件 402 行）。当前 8 项实际选中的是五个新 observer/timing/summary 用例与三个既有用例，该 retention/shape 用例在 25 deselected 中；README/preparation-record 关于本轮已经覆盖 top-16/maximum event shape 的表述不准确。

即便补选当前用例，其 event fixture 也只给每代 generation/count/longest，省略 `snapshot_since_previous` 的 elapsed/process/thread totals、missing/error/open 字段；使用短 ID/小时间数值，没有验证真实 helper/session return/exception 携带 original-call/wrapper 计时和完整 EventWriter metrics 的形状。运行代码 `prepare_step_worker.py:203–208,228–238,260–270` 实际将这些字段同时放进 2 KiB 记录。三代均有保留窗口是设计允许的情况，不能以简化 fixture 证明真实组合不超限；触发 event_too_large 会使必要观测失败，可能恰好丢掉本次要看的长 GC 周期。

把实际完整 entry/return/exception 字段、允许的三代窗口/开放形状及实际长度的 ID/时钟值用于必要 focused，并确认真正被 runner 选中；若超限则精简固定字段/采用紧凑表示，保留可解释的计数、窗口与真实调用边界，不抬高原上限或无标记丢数据。本审核没有执行候选，不将该未验证组合写成已有业务现场超限事实；在证明真实最大形状前不能签运行 GO。32 KiB summary 的边界可在同一小型工具覆盖中核实，不扩成全量门禁。

### G2：snapshot 读后逐项清零会丢 collection，仍可能声称 complete

`gc_observer.py` SHA256 `04faada3133f162d35e6ca6f1ed842cfd193b8f377a090b66e6bdb6c73bb6c27`。`snapshot_since_previous`（187–215 行）先从可变 stats 读值构造/append dict，再于 203–208 行逐项清零 since counters/max。**snapshot 自身的容器分配也可能触发正在观测的真实 GC callback**；callback 同时更新这些字段。若 collection 发生在旧值已取得、尚未清零之间，新 count/total/max 会被清掉或形成来自不同时间的混合字段，而返回仍 `incomplete=false`。callback 在另一线程的协作交错同样不被版本/交接机制识别。这不需要引入恶意同 euid 或穷举调度窗口，是本 callback 与其 snapshot 的正常重入边界。

全程累计或 top-16 可能保留部分信息，但不能因此保证本次 heartbeat 的 since-window 没有丢失；而 §67 已证明失败可能没有最终 summary，不能指望正常收尾再补回缺口。需要一个最小固定规模交接/累计差分，或轻量交错检测并明确 incomplete，避免静默丢失后输出“该窗口没有 GC”。不要求完整事件队列、GC 暂停/阈值修改、阻塞 callback 锁或新状态机。补一项 collection 与 snapshot 交错后累计/分段一致或明确 incomplete 的语义 focused 即可，不穷举每个内部步骤。

### 其余接线与后续范围

候选正确保留真实 `WorkerRuntime.run` 及原 heartbeat/session 参数、返回/异常、renewal anchor；原调用前时间在同步 entry emit 返回后捕获，logger 不递归发事件。callback 按固定三代与 top-16 保留、同线程 CPU 差分、只内存记录错误并保留其他 callbacks；summary 路径接入 Compose/controller，正常收尾只移除自己的 callback，重复 worker_run_exit 已消除。缺失/不完整 summary 阻止成功，失败仍可凭回收事实安全解锁；这些方向与 §69 一致，不能替代 G1/G2 的修正。controller 环境 dict 中 `P6_DIAG_GC_SUMMARY_PATH` 重复同值两次是非阻塞清理项，可同轮去重，不单独加测试。

两组阻塞已直接送达唯一实施者并抄设计；当前角色和 §69 准备/必要 focused 授权持续有效，无需再确认接管、设计回执或 owner 许可。保留本最终 a 包/manifest、精确测试时清单及原日志；用独立修订目录绑定新代码、受影响 focused 和最终清单再定向复审。handoff 的额外本地 checksum 错误留档/文书提交不改变候选字节或上述结论。未变 controller/回收矩阵不重测，不发试验 POST、不重跑大 probe/Compose 或全量 runner。

产品继续冻结 `1f9731`、最后验证 image revision/source-tree 沿 §57，无产品/镜像重建。**本轮无候选专属 GO，无 POST/worker/Compose 诊断或正式测量许可；H3 PASS、lease 根因 OPEN、正式测量 STOP。**

## 71. GC-window 候选 d 最终复审：候选审核 PASS，G1/G2 关闭；本轮未发运行 GO

**`p6mutationgcwindow20261106d` 候选审核 PASS。** 最终 manifest 路径 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106d/candidate-manifest.json`，完整 SHA256 **`b4db000f83194000f6d7a89180f63490327545c130a403cb3b636d5a81031571`**，15 文件集合/摘要/模式及全部 Python AST 均独立核验匹配。相对精确测试时清单 `f30afe04d8a3c633e95a265fbb8424b3f8df05ec0c9cec3f9288bfc719bb498a`，最终只改 README/preparation-record/review-request，12 个非文档文件及全部模式未变。按本轮 review-request 的审核请求给出此结论，**它不等于候选专属诊断 GO，本轮没有签发 GO**；不得据 PASS 创建 POST-GO 或运行 launcher。

原始 CT05 focused 日志 SHA256 **`e6a560e90b9c3344a020ec5d9d9ac98bacaf4d42cf36cc60f16f9cb5796523a3`**，21:04:46–47、起止 clean 冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、**4 passed / 31 deselected / 0.67s、pytest/script exit 0、node_lock_released=true**。最终 binding 日志 `6e213a63db520762e0ffdd871ddb662ee78da8bbdb73d07e6d87122116a76375` 记录 21:08:09、同一最终 manifest/15 文件 MATCH、POST-GO absent；postflight 日志 `68241436d948861e2a833f5cefbb9188ac5dbe30680e542f8bc01fc7a336af83` 记录 clean/head 不变、节点锁 absent、无 Dolt/8000 占用。BatchMode echo OK 后另只读 SSH 独立核最终 15 文件/模式、clean HEAD、focused 日志 SHA 与 POST-GO absent 均一致。本审核未执行测试、候选或新业务，也未访问 CT108。

### G1 关闭：真实完整形状、top-16 及失败 fixture 已覆盖

d 的 runner 明确选中 top-16 retention、实际 helper/session 字段、完整事件形状与计时透传四个受影响用例。常量从其 owner `gc_observer` 取得，不为测试增加 worker 兼容别名。完整形状用例调用已安装的 helper/session wrappers，覆盖两者 entry 及 return/exception；给三代完整窗口、19 位纳秒、最长 255 字符 ASCII opaque IDs、所有退出计时及 writer metrics，保持 2048-byte cap。只读读取 CT05 已保留的 `pytest-242/test_real_event_writer_bounds_0/{success,failure}/events.jsonl`，共 13 条、helper/session 四类各两条，**最大实际记录 1439 bytes**。这是既有测试产物的复核，不是新增测试或再次运行。

最终 worker SHA256 `e30771db2b536debd23a4dbcc487509ffe2218ae58ccf4fa6d9de075a5e69377`。generation/window/writer metrics 用固定顺序数组保留计数、wall/process/thread CPU、missing/error/open、线程与窗口起止；重复 generation 由外层行承载，短键减少重复 JSON 名称，原始完整 summary 仍用描述性字段。计时单位与位置由 helper 文档及 focused 字段断言绑定，incomplete 继续是显式 bool，controller/guardian 的消费字段未失配；未抬上限或无标记截断必要字段。

b 的两项失败原样保留：整体 9 passed/2 failed，日志 SHA256 `2f813240f1c9596e6de634805fe5cf8540fb7b71dde8ae77987d397d65280868`；它实际发现测试常量引用错误及完整事件 event_too_large。c 的整体 3 passed/1 failed 与日志 `e70cdcf323818587c25319c9af4eeebc51bf3a4743f2aece962adcab197ee9dd` 也保留；c 上限断言已通过，随后缺初始三代窗口的 fixture 断言失败。d 相对 c 的语义测试变化仅在 failure helper 调用前补齐三代窗口，原完整字段、cap 和异常断言保留，另有候选 d 的 ID 字面替换。没有为通过测试改生产结果或放宽断言。

### G2 关闭：轻量交错留缺口，单项工具证据关联准确

observer 最终 SHA256 **`47fde594b69e5bd93970552496055634e49fe8c6b34519ca29d5ada91d1bbef7`**，b/c/d 字节相同。新增 snapshot-active/interleaved、正在更新 generation 与当前 snapshot 标记；callback 的入口/收尾遇 snapshot，以及 snapshot 遇到正在更新状态，会使该 snapshot 和后续 observer 明确 incomplete，避免本轮指出的读后清零重入仍假称完整。没有 callback 阻塞锁、GC 设置修改、完整 collection 队列或新后台机制；这是诊断性有限检测，不把它表述成任意线程调度的形式化原子性证明。开放/选择性保留的区间仍只按其实际覆盖解释，不能因 complete 字段或 top-16 未见某窗口就宣称没有 GC；正常最终摘要有开放区间则不完整。

独立计算 b/d 的 `test_gc_snapshot_interleave_is_incomplete` 原始函数字节摘要，均为 `9ff1ca2438cb7bde8d634db1acc0927761394f5b893d30fe25b99fab3f8d134b`。该用例由 b 的固定选择式实际选中且在九个通过项中，验证 collection 与 snapshot 读取交错后 snapshot/final summary 不完整。`g2-carry-association.json` SHA256 `88ef42f45db13acb01220e0c7e5246d421cd7b65d75858b7966f31140a165fc5` 与本审核独立摘要一致。这里是未变工具及单项 focused 的证据关联，**不是权威 runner carried，也没有把 b 整轮 exit 1 写为通过**；未要求重复该未变路径。

### 运行接线、结论边界

controller、verifier、两个脚本与 Compose 挂载均指向 d 的项目/清单/目录；launcher 和 controller 的 lock token 一致，token 的历史 c 字面标签不代替实际 d 的 manifest/POST-GO/project 身份。summary 环境键重复已去除。真实 WorkerRuntime.run、原 heartbeat/session 参数/返回/异常与 renewal anchor 委托、entry emit 后才取 original-call 时间、logger 下一条/最终报告自身耗时的接线保持；callback 仅内存、保留其他 callback、正常收尾只移除自己的 callback，最终摘要独占/有界写入，缺失/不完整阻止成功但不妨碍安全回收后解锁。新候选仍用原 source checkpoint 的新副本，不恢复失败 c 的卷。

候选 d 的摘要复制命令错误已留失败与本地更正日志，没有据此重跑 focused。产品继续 clean 冻结 `1f9731`，最后验证 image revision/source-tree 沿 §57；外置 wrapper 变化不触发产品或镜像重建，实际运行身份仍须由未来获准的固定入口重核。原 45 分钟/3600 秒预算、资源/身份/失租/cancel/stall 停止、保卷留证/未静止留锁和 05 实际占用条件不变。本次不新增测试、修复轮次或 Owner 身份/准备确认门槛。

**候选审核结论已直接交唯一实施者并同步设计；实际诊断仍须另行明确签发绑定本完整最终 manifest 的一次 GO。当前没有新的 POST/worker/Compose 诊断或正式测量许可，H3 PASS、lease 根因 OPEN、正式测量 STOP。**

## 72. GC-window 候选 d：精确一次限定诊断 GO

**现签发 `P6-GC-D-GO-20261106-01`，仅对 §71 已 PASS 的 d 最终 manifest 给一次限定 GC/observer 诊断 GO。** 完整清单路径 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106d/candidate-manifest.json`，SHA256 **`b4db000f83194000f6d7a89180f63490327545c130a403cb3b636d5a81031571`**，candidate ID `p6mutationgcwindow20261106d`。独立复核 §71 的所有候选条件已经满足，本轮只核清单仍为该摘要和固定命令/预算字面值，没有改包、重测或新增节点操作。

设计已明确请求本次精确 GO，既有 Owner/DC80 及 `f7d53c1c41` 直接闭环授权也已涵盖此步骤。§71 的 review-only 结论与本节显式 GO 分别记录，不建立新的 Owner/协调者申请门槛；以后同范围具体候选通过且既定条件齐备时，直接办理精确一次 GO，不因 review-request 的“本次仅审包”措辞再等待协调者补发启动申请。直接投递唯一实施者 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 并抄设计，不以回执或重复身份确认为接续条件。

仅 **CT05 `gw-dms-test-05`/root**，产品 clean 冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，§52/57 原三镜像身份、原 `p6bw4s4h120261105b:v2-preview` pre-submit checkpoint、既有输入/缓存不变。只准 d 的新项目/key/三卷副本和新证据根，不能使用 h/c 已失败卷继续。实际执行前按既有节点协调取得 05 的有效占用；E 或其他有效占用未释放时等待，本 GO 不预约/抢占节点、不绕过目录锁，不向 CT108 扩张。源码、清单、镜像身份或必要缓存不符即停止，不能改包/换输入后沿用此 GO。

允许唯一实施者在该候选根写 `POST-GO.txt`，严格三行：

```text
decision=GO
candidate=p6mutationgcwindow20261106d
manifest_sha256=b4db000f83194000f6d7a89180f63490327545c130a403cb3b636d5a81031571
```

固定命令（在 CT05/root，入口无参数）：

```bash
cd /home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend
/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106d/candidate/run-once.sh
```

只准一次真实 acceptance POST、唯一返回 ID 绑定的 prepare_import claim，原 production `_run_claim` 正常完整返回后才 drain、后继不 claim、restart=no；不安排合成大输入或第二轮全输入诊断。parent_materialization 907.302s 仅为旧参考成本，不保证本次完成时间。保留 **45 分钟绝对观察、3600 秒全流程硬上限、3120 秒 work/480 秒 cleanup reserve**，原 48 GiB 启动可用内存、5 秒 guardian、全部 RSS/host/disk/身份/lease_lost/cancel/120 秒 stall/必要观测停止条件不变；不改 lease、heartbeat、drain、GC 设置或产品线程/事务语义。

观测限于 §69/71 的 GC 有界内存 callback、既有函数边界和 observer/实际调用计时；没有 planner 新插桩、大中间 checkpoint、callback I/O 或额外后台 sampler。incomplete、开放/遗漏覆盖或未取得最终摘要按已有缺口与停止分类保留，不伪装“没有 GC”或唯一因果；新 GC overlap/CPU 数据也不自动确定 GC/GIL 根因，不视为正式性能。不得为取得摘要延长任一预算或提前触发业务 drain。

实际诊断失败或停止后不自动重试，保留最后可读 target DB selected rows、raw service/event/resource 日志、GC summary 状态及捕获错误、原始失败与完整摘要。使用原有有界 cleanup，仅自有进程/容器/网络均确认静止后解锁；未确认则留占用报告，保留三卷及所有旧证据/候选。logger/guardian 正常关闭不等于 worker 正常业务退出，missing summary 不能说全部观测完成。控制器日志完整关闭后由外层记录完整 SHA，结果直接交本审核会话独立复核。

**本节只授权此精确候选的一次限定诊断；不是产品/旅程验收通过，不是正式测量恢复或失败重试许可。** 不改产品/镜像或 retag，不推送/打 tag/合入产品，不清理原卷或证据。H3 仍 PASS，lease 根因仍 OPEN，正式测量仍 STOP；其余候选和已消耗 GO 均不因本节恢复。

## 73. GC-window d 运行结果复核：观测不完整停止，未到 mutation_plan；一次 GO 已消耗

**§72 GO 已唯一执行并消耗，本轮诊断未完成，不能重试或恢复正式测量。** CT05 控制器 2026-11-06 21:22:21–21:32:23、602.095s，controller/script exit 1，STOPPED / diagnostic_stop / gc_observer_incomplete，GC summary=MISSING。本轮执行边界、既定停止与回收证据核验可接受；**没有观测到 lease_lost，不把这次观测停止写成又一次产品失租或 prepare 成功**。H3 仍 PASS，原 lease 根因 OPEN，正式测量 STOP。

### 精确身份与一次执行

BatchMode echo OK 后，只读 SSH 独立核 CT05 clean 冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`、manifest 仍为 `b4db000f83194000f6d7a89180f63490327545c130a403cb3b636d5a81031571`，POST-GO 三行精确绑定 d，未改包/重建镜像。preflight 及实际 wrapper SHA/PID/starttime/guardian 首样本与 §71/72 输入、身份和启动顺序一致：worker wrapper `e30771db2b536debd23a4dbcc487509ffe2218ae58ccf4fa6d9de075a5e69377`，host PID `2922373`、starttime `200993265`，container PID 1，首样本 marker 先于 ready/claim。本审核没有测试、启动新业务、重试或访问 CT108。

本地证据在 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106d/diagnostic-evidence/`，远端原始 scenario 根在 `/home/dev/gdds-p6-logs/baseline/scenarios/p6mutationgcwindow20261106d/`；launcher 在候选根。关键摘要本地/CT05 一致：

| 证据 | SHA256 |
| --- | --- |
| controller-launcher.log | `022aff5c6dd93ce8e3e2df6e3cd5860a85fc18906966365452eed7372c3259e3` |
| evidence/prepare-step-result.json | `9f3e6f0491e101908389b3de06f2b8e69b3321b458866f7fefd0c60e3ce0165f` |
| postflight.json | `b1bcd047d95ba890a6e31e5c0c8758049a06b9a48c181f794508b3be1a27eb8d` |
| evidence/worker-events.jsonl | `f358cd36e3c34d3a63d8d9affaa14004a62a2854d7c3286c5ff95fdc031a2950` |
| evidence/resource-samples.jsonl | `a2852d38d5d12e5257563aaa8137c9141a1d2b4f910ad58ba4f4015480866f91` |

一次 acceptance attempt/count=1/1、HTTP 202、RESPONSE_VALIDATED，一次 target-bound claim/attempt_count=1。operation=`op-39d77db02a24401421ce1691`、attempt=`sa-8e7583c89a0cbbcc00341bee`，step 为其 `-step-1`/prepare_import。21:29:19 最后可读 selected rows 是 TARGET_FOUND：operation/step RUNNING、attempt PREPARED、cancel=false、repository_operation_id 均 null，只有目标 prepare active，未产生 submit_import 后继。身份、返回 ID、事件与末态一致；没有把 durable RUNNING 改写为终态成功。

### 停止来自保守的 snapshot 交错判定

286 条事件中 54 次 helper/session 入口与退出、54 次 heartbeat_succeeded，session 全部 return，没有 lease_lost/heartbeat_busy。首次 `gc_since_previous.incomplete=true` 在**第 201 行、21:29:18.516 的第 38 次 session exit**；原 session 本身正常返回（call_elapsed 0.164990s），callback/observer/invalid 计数均为 0，伴 executor 线程 `127152133236416` 的一个开放 gen0 窗口。这与候选代码 snapshot/callback 交错时主动标记 incomplete 的保护一致，不是 callback 抛错或产品 heartbeat 失败证据，也不证明发生了实际漏计。

共 66 条事件携带 true，是 sticky incomplete 状态的后续输出数，**不是 66 次独立观测错误或 66 次长 GC**。控制器据此进入既定停止，21:29:19 保存 pre-down 证据。说明保守交错保护会在目标问题阶段之前先触发；不能通过忽略该标记、改 GC 设置或自动重跑来继续消耗已用 GO。

源码上，callback/observer/invalid 错误路径会分别增加已记录计数；worker 尚未返回，也未执行正常收尾的 callback 移除/final_summary。首条不完整载荷仍有完整类型的三代 rows/open list，不是 compact 编码遇非法形状的 fallback。因此可以把这次状态归入 **`GCWindowObserver._mark_snapshot_interleaved` 的交错保护类别**，而不是已证实的 callback/记录异常。该函数可由 callback 入口/收尾、snapshot 内的正在更新检查或重入检查调用；现有事件没有记录 reason/callsite，不能继续唯一确定哪一调用点先置位。开放 gen0 是当时观察到的状态，不独自证明具体丢计；错误计数为零也不能成为未来通用放行规则。本次没有足够的 producer 累计/最终摘要证明实际漏计，能确认的是一致性保护判定本身触发了停止。

| 时刻 UTC | 实际边界 |
| --- | --- |
| 21:22:51.640–21:23:58.971 | prepare_build_input return，67.331s |
| 21:25:54.117–21:27:43.470 | frozen_projection return，109.353s |
| 21:27:43.470 | mutation_snapshots 进入 |
| 21:29:18.516 | 观测 incomplete，mutation_snapshots 此时尚未返回 |
| 21:29:19.284 | 停止处理期间 drain_started |
| 21:31:23.897 | 清理期间 mutation_snapshots 才 return（220.427s），随后 parent_materialization 进入 |
| 21:32:19.284 | drain_timed_out，距 drain_started 180s |
| 21:32:23 | 控制器结束并完成回收 |

没有 mutation_plan/canonical_publish 入口，也没有 parent_materialization 结束、claim_exit、clean_drain_requested 或 worker_run_exit。后续业务线程在停止处理中继续运行，不代表 controller 忽略停止或 prepare 正常完成；原 fence/join/drain 语义保留，不能假定线程在停因出现时即终止。后续 drain/timed-out 不当作初始停止原因，本次没有覆盖 §67 的 mutation_plan 漏续租窗口。

### 早期片段的有效 GC/计时信息与限制

首次 incomplete 前仍有可解释的正向窗口：executor 线程 gen2 的 callback 区间 monotonic_ns `[2010282474930725, 2010291286937959]`，**wall 8.812007234s、process CPU 8.819902953s、同线程 CPU 8.811169980s**。第 183 行 helper marker= `2010291286870428`（21:28:48.310），derived due=`2010284.863481389`，传入 deadline=`2010304.863481389`；marker 比 due 晚 **6.423389039s**，但尚余 deadline **13.576610961s**。该时点报告开放 gen2，下一条 session entry 保存相同 start/thread 的完整 stop 窗口，stop 比 helper marker 晚 67531ns；因此该 callback 区间覆盖了这次 derived due→marker 的迟到区间，之后 session 正常返回、heartbeat 成功。

这是真实进程中 GC 边界与续租迟到共现且 collection 线程有明显 CPU 消耗的证据，比旧 100k checkpoint 更接近现场；**仍不是 GC/GIL 唯一因果证明，更不能外推为 §67 的 22.272s planner 延迟原因**。它发生在 mutation_snapshots 阶段，没有漏 deadline；callback 起止包含相关 callback/collection 区间，不当作 GC 内部独占 CPU 或逐步归因。停止后的不完整片段另有约 11.082s gen2 窗口，只按该片段说明，不当完整覆盖或独立性能测量。

首次 incomplete 之前 38 次 helper marker 的最大 due lateness 为上述 6.423389s；全程 54 次最大约 11.018532s，均未越传入 deadline。54 次 session 原调用最大 0.295496s。首次 incomplete 事件携带的前 200 次已完成 writer 操作最大 encode/lock-wait/write/flush 分别为 1.156515ms/0.003580ms/5.353299ms/0.001860ms，未显示这些已报告操作的秒级阻塞；不覆盖未报告尾部，也不把 line-buffered write/flush 当独立 syscall 或无扰动证明。

事件 286 条、165420 bytes、最大 855 bytes，未触发大小/数量上限；没有最终 GC summary，不能宣称完整 collection 统计或“没有 GC”。尤其不能用本次早期/不完整采样排除其他阶段，或替代对旧真实失租的解释。后续可利用这些保留片段作只读分析，继续运行须由新的具体方案与精确 GO 决定，本审核不自动排下一轮。

### 回收与证据留存

guardian 82 样本，21:22:31–21:29:16、最大间隔 5.010667s；worker RSS 最大 8284733440 bytes、host available 最小 58928576512 bytes、disk free 最小 211148898304 bytes，未触既有资源线。guardian CLOSED、exit 0/reaped、worker_exited_cleanly=false；它在清理前关闭，不作为随后完整资源覆盖或 worker 正常业务退出证据。

pre-down 于 21:29:19 保存 MISSING summary 状态、最后 selected rows 和三服务 raw logs；文件字节/摘要与索引逐项匹配，三个 capture helper 均 exit 0、reaped/group quiet、无 truncation/timeout。worker.log 为 0 bytes，最终 summary 文件在节点也不存在，没有最终 worker exit signal/code 记录；不补造正常退出或结束计时。Compose down=0、postflight_complete/lock_release_allowed=true、自有进程和 project 容器/网络 quiet/reaped，三目标卷完整保留、volumes_removed=false，launcher node_lock_released=true。只读 SSH 另核该 project 容器/网络空、三卷全在、busy lock absent，与原记录一致。

**结果与限制已直接交实施者并同步设计。执行边界、停止与回收核验通过，原诊断问题未闭合；本 GO 已消耗，无自动重试、产品/GC/TTL 改动或正式测量许可。** 保留全部旧候选、卷、原始证据和本次有效片段，不为补 summary 重跑。

## 74. 已知 GC 覆盖缺口继续观测：窄设计修订范围 PASS

**`63c2bf219d2963adfc7466d4af6f35273ce9b34d` 对 GC 计划新增末节的定向范围审核 PASS。** 本节独立于 §73 的 d 结果复核：d 仍按当时约定停止、GO 已消耗，不追认改判或自动重跑。唯一实施者可按新范围最小修包和必要 CT05 focused，随后交新精确 manifest；当前没有实际诊断 GO。结论已直接投递实施者并同步设计，不等回执，不重复身份、接管或 Owner 准备许可。

修订有 d 的真实过早停止作为依据，并正确将 GC 统计作为 derived/可选诊断覆盖，未放松产品、身份、续租、资源或核心日志边界。其目标是保留有解释的 partial 并继续原必要守护，不是追求无损的 GC 事件平台；沿现有固定大小统计/标记即可，不要求无丢失队列、后台线程、持久状态机或新的同步框架，也不改 GC/lease/heartbeat/drain/超时。

### 允许继续的状态必须有正向分类

只允许 producer 明确分类的 **snapshot/callback 交错**或**采样时 collection 尚开放**两类窗口覆盖缺口。用最少有界原因字段保留当前/历史 partial，不能以通用 incomplete=true、error_count=0、看起来有开放窗口或缺少字段来泛化放行。缺原因、未知原因、损坏字段或无法解释的组合仍停止；若已知 gap 同时伴实际 callback/observer/非法转换/cleanup 或核心日志错误，真实错误优先，不因 gap 标签转为可继续。来源判定应来自 producer 实际置位分支，不让 consumer 从零计数推造原因，也不反向补给旧 d 一个未记录的具体 callsite。

交错可丢弃当前混合窗口统计，保留完整闭合的正向区间，在下一普通边界自然取新 snapshot；不紧循环抢采或“补完整”。不得为恢复 complete 清 producer 累计计数、真实错误事实或历史覆盖缺口；正常每窗口 accumulator 的 rollover 与已有累计事实应区分。一旦某段 coverage 未闭合，不能再宣称全程完整或没有 GC；部分统计可以有效，但其实际覆盖必须可解释。

### 核心运行与最终结果不能被 optional partial 绕过

controller、guardian 和 worker 都须使用一致的已知 gap/实际错误边界。**known partial 仅改变 GC 覆盖判断，不能 `continue` 跳过整条核心 event。** session heartbeat 正常返回仍刷新既有 last_success，claim/lease_lost/executor_failed/cancel/drain/资源/身份及 deadline/stall 均照原路径处理；独立 guardian 继续采样和执行原资源停止，不把当前 GC gap 写成 EventWriter 核心故障或 observation-gap.flag。实际 callback/记录异常、日志不可写/过界/损坏和未知异常仍沿必要观测失败停止，不能因“GC 可选”吞掉它们。

最终结果分开陈述 prepare 的 durable/运行结果、核心观测是否有效及 GC coverage 是否完整/缺口原因。prepare 失败、失租或核心错误仍按原非零/停止语义，已有产品主因不能被 missing/partial GC summary 覆盖；反之 GC 覆盖 partial 也不伪造 prepare 已失败。正常 prepare 若完成，必须有候选约定的有效、可解释 summary，缺失/损坏/未知状态不能借 partial 接受；即使 prepare 成功且只有已知覆盖缺口，也不能把整体诊断描述为“全部观测通过”。具体小型结果字段/exit 表述随候选审核，不预设新的状态机或产品状态变更。

worker 未正常返回时没有最终 summary，则保留有效事件片段与明确缺失事实，不补造结束、完整计数或无 GC。原 45 分钟观察/3600 秒全流程硬上限、资源/身份/续租/120 秒 stall、一次 POST/claim、no-restart、正常原 claim 完整返回后才 drain、保卷留证/未静止留锁全部不变；不为收齐 summary 延长预算或改变业务退出。产品和 §52/57 镜像继续冻结 `1f9731`，不触发产品/镜像重建，CT108 不加负载，05 遵守实际有效占用。

### 只补受影响的验证

复用当前 callback/observer/worker/guardian 和最终结果 fixtures，证明两类已知 partial 下后续真实调用、heartbeat 成功计时及守护仍继续，实际/未知错误和错误与 gap 同时存在时仍停止；核最终 prepare/核心失败主因与 GC coverage 分开，不被最终摘要重新分类覆盖。不重跑已关闭的 controller/回收矩阵、旧大 probe/Compose 或全量 runner；新增原因/状态字段改变 payload 时顺带原实际最大形状用例，继续满足 2 KiB/4096 条/8 MiB 与 32 KiB summary，保持测试与实现/最终清单绑定。

**范围 PASS 仅准新候选准备与上述必要 focused，不授权实现后直接运行业务；实际运行须新候选审核通过并另记精确一次 GO。** 既有直接闭环流程继续，不设置额外协调者/Owner 门槛。旧 d 包/结果/GO 消耗事实、所有旧证据和卷保持；H3 PASS、原 lease 根因 OPEN、正式测量 STOP。

## 75. e 准备期 focused 失败：直接修正常量引用并继续必要验证

只读核对 e 原始 `focused-tests.log`（SHA256 `6e6d69eec60d1030d996d05683dc96404b3706a6929d8b5d132fc344714e4e08`）：CT05 22:13:15–16、起止冻结 `1f9731`、9 failed / 2 passed / 28 deselected、pytest/script exit 1、node_lock_released=true。`prepare_step_worker.py:225` 裸用 `GENERATION_COUNT`，该文件只导入 GCWindowObserver；常量实际由 gc_observer.py 定义。直接解码调用报 NameError，受保护路径捕获后产生的字段/分类断言也出现级联失败；修复后仍须看有无独立逻辑问题，不能预断九项均已关闭。本轮审核未执行测试、访问节点或运行业务。

已直接交唯一实施者：保留 e 精确包/manifest 与失败原日志，在独立修订中从 owner 显式导入/引用常量，做受影响的计划内 CT05 focused；可顺带现有 Ruff F821 未定义名称检查，不扩为完整门禁。§74 的候选准备/必要 focused 授权已经包含这类调试修复，不因一次 focused 失败新增 Owner/设计/审核逐次许可，也不重新要求接管或身份确认。若修复后暴露其他同范围工具/fixture 问题，继续定位、最小修改、受影响验证，不原样盲重跑或每次停等许可；最终代码/测试/清单/原始日志绑定后再独立复审。

这是计划内工具调试失败，沿既有 DC80 修订闭环处理，不把 DC68 当成新增逐次 Owner 授权门槛；权威 runner、真实业务诊断、缓存/身份异常、真实副作用及新范围/预算仍遵原停止边界。没有实际 GC 诊断 GO，不启动 POST/worker/Compose 或测量，产品与镜像冻结不变。

## 76. GC-window 候选 g 最终复审 PASS，并签精确一次诊断 GO

**`p6mutationgcwindow20261106g` 候选审核 PASS；现签发 `P6-GC-G-GO-20261106-01`，仅准本节精确清单的一次限定诊断。** 最终清单 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106g/candidate-manifest.json`，完整 SHA256 **`64e0376bd8939176bdc7fd7e3f91473de46d01266edc613cfebcf3d05e1ce3e4`**。本节落实 §74 已通过的新范围，不追改 d 的停止、结果或已消耗 GO；H3 仍 PASS，原 lease 根因 OPEN，正式测量 STOP。

### 文件、测试与现场绑定

独立只读核本地候选的 15 文件集合、逐文件摘要、全部模式及 Python AST，均 MATCH。精确测试时清单 SHA256 **`e57ee3e6735ff727543b373630f35ca4f8e3463c771372c5b36781d20b7b03be`**；测试后只有 README/preparation-record/review-request 三份文档变化，12 个非文档文件及全部模式未变。BatchMode echo OK 后，于 CT05 22:47:46Z 独立只读 SSH 再核最终清单、全部文件/模式、focused 日志摘要、clean 冻结 HEAD `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 与 POST-GO absent，全部一致；当时 node busy lock absent 只代表当时状态，不是后续预约。本审核未执行测试、候选或业务，不访问 CT108。

原始 `focused-tests.log` SHA256 **`1c4d85b114866c7a6f6f1f933c4bfa580d68cb46d5bb61118d2b79c1ca53445b`**：CT05 `gw-dms-test-05`，22:31:44–45Z，clean 起止冻结 HEAD，Ruff F821 全通过，**11 passed / 28 deselected / 0.82s，pytest/script exit 0，node_lock_released=true**。一条 multiprocessing fork deprecation warning 已保留；本轮 guardian 用例的子进程已收束，不把 warning 隐去或将它写成业务现场故障。选择式实际包含受影响的 producer partial/error、交错/开放、top-16、完整事件、原 helper/session 透传计时、summary、heartbeat/cancel/lease 主因与 guardian 继续采样；没有重复旧回收矩阵或完整门禁。

只读检查 CT05 已有 `pytest-244/test_real_event_writer_bounds_0/{success,failure}/events.jsonl`，文件时间属于本轮 focused，共 13 条，最大 **1500 bytes**，未超过原 2048-byte cap。这里是既有测试产物复核，不是新增测试。最终 worker SHA256 `813f228d97154a5493c7e7508cde4b4bec0af8183700a83fd8e97a80431af750`，observer SHA256 `3dcf230ad422048429a554e00438c0f7fa8f758ad39d76c6c5d417e5cb3c78e7`。

e/f 的失败包与日志保留：g 从 owner `gc_observer` 显式导入已有 `GENERATION_COUNT` 和 `MAX_RETAINED_WINDOWS`，没有增加兼容别名。e 的 NameError 与 f 的 F821 缺失导入已由最终代码和这次实际 focused 关闭，未把旧失败轮次写成通过。

最终文档传输曾把三份更新文档写到远端候选根，而非 `candidate/`；这是有实际文件写入的操作错误，不归为无副作用 DC68 重试。按既有 DC80 最小恢复授权，只补入正确目录，原根目录副本、失败日志与测试证据均保留，未重跑测试。`final-binding-review-attempt1.log` SHA256 `08a31e0539268b296ff47485b7624639ce5e732821a988bb171ce50aa6a7b2bf`；恢复后的 `final-binding-review-recovery.log` SHA256 **`13671f62909d5fb683629b5cc1d4ace1941be69314ee0eade0decde9224c7944`**，记录两份清单 sidecar 和 15 文件 MATCH/POST-GO absent。`run-result.md` SHA256 `03d0f2a27a6a4c61cb64faa003dac4682109ed9f23e97a05270ab6ccdbc5a649` 与上述事实一致。

### §74 的 partial 语义已落实

producer 只从实际分支累计 `snapshot_callback_overlap` / `collection_open` 两类有界覆盖原因，历史 incomplete 与错误事实保持。重入改记 observer error；callback/observer/invalid/cleanup 错误及未知、损坏、无法解释的分类均 fatal，不以零错误计数泛化放行。compact event 保留完整核心事件、显式 classification/reasons 和四类错误计数；known partial 不污染 EventWriter 核心失败状态，也不声称恢复完整覆盖。未改 GC 设置、callback 内 I/O/锁、产品线程或续租参数，未新增队列或无损观测框架。

controller 先处理核心 event：正常 session return 更新 last_success，lease_lost 等原主因优先，再判断 GC 覆盖；known partial 没有跳过整条 event。guardian 也只接受结构有效、原因已知、错误为零的 partial，随后继续原身份/资源/截止守护；真实及未知错误仍停止。summary v2 将 COMPLETE、可解释 PARTIAL 与错误/缺失分开；只有正常 worker 成功、核心日志有效、已知原因且完整结构成立的 PARTIAL 才能满足 prepare 成功的摘要条件，整体 observation_complete 仍为 false。最终摘要拒绝仅在原 prepare-success 分支降级，已有产品失败/失租主因不被缺失或 partial 摘要覆盖。focused 与源码检查对这些受影响语义提供了足够证据，不要求派生诊断统计获得与 durable 业务状态相同的证明。

### 精确一次 GO 的执行边界

按既有 Owner/DC80、`f7d53c1c41` 和 §72 的直接闭环授权，审核合格后直接交唯一实施者 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 并同步设计，不等新的 Owner/协调者回执，也不因 review-request 的“仅审包”措辞增设启动申请门槛。本节是明确的新 GO；此前 g 无 GO、不运行的状态正确。

仅 CT05 `gw-dms-test-05`/root，在正常取得整机占用后执行以下固定命令，无附加参数；产品须保持上述 clean 冻结 HEAD，§52/57 原三镜像由固定入口重核，不重建、pull 或 retag：

```bash
ssh -o BatchMode=yes ct108-gw-dms-05 'cd /home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend && /bin/bash /home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106g/candidate/run-once.sh'
```

实施者可据本明确 GO 在候选根新建 `POST-GO.txt`，内容必须恰为：

```text
decision=GO
candidate=p6mutationgcwindow20261106g
manifest_sha256=64e0376bd8939176bdc7fd7e3f91473de46d01266edc613cfebcf3d05e1ce3e4
```

只用原 `p6bw4s4h120261105b:v2-preview` checkpoint 的新项目/key/三个隔离卷副本，最多一次 acceptance POST、唯一返回 ID 绑定的一次 prepare_import claim；原 claim 正常完整返回后才 drain，不 claim 后继、restart=no。旧 d/c 失败卷及 GO 不复用。保持 **45 分钟绝对观察、3600 秒全流程硬上限、3120 秒 work/480 秒 cleanup reserve**，启动 available memory 48 GiB、guardian 5 秒、worker RSS 40 GiB/host available 8 GiB/disk free 10 GiB、身份/lease_lost/cancel/120 秒 stall 和核心观测停止线全部不变。仅上述有明确分类的 GC 覆盖缺口可继续；真实/未知错误仍停止，partial 结果不能称“全部观测通过”。不延长预算、TTL、heartbeat 或 drain 来取得 summary。

实际诊断失败或停止后不自动重试；保留最后可读 selected rows、完整 raw service/event/resource 日志、summary 状态/缺失事实与原始失败。日志关闭后记录完整 SHA256。只按既有有界 cleanup 回收自有进程/容器/网络，确认 quiet/reaped 才解锁；未确认则留占用并报告。保留三卷、所有旧候选及证据；collector 关闭不等于业务完成。结果直接交本审核会话复核。

**GO 仅限这个精确候选的一次局部诊断，不是正式测量恢复、产品/旅程验收通过、失败重试、产品修改、推送/tag 或旧卷/证据清理许可。** 产品 HEAD 与最后验证 image revision/source-tree 沿 §57，无产品/镜像重建触发；CT108 不加负载。

## 77. GC-window g 结果复核：真实失租，24 秒 GC 区间覆盖迟到窗口；GO 已消耗

**§76 的一次 GO 已执行并消耗。** CT05 2026-11-06 22:51:36–23:29:02Z、2246.255s，controller/script exit 1，STOPPED / diagnostic_stop / lease_lost。原始事件于 23:25:57.083Z 记录 `heartbeat_busy_deadline`；GC summary=MISSING。执行边界、既定停止和回收证据核验可接受，**不是 prepare 成功或全部观测通过**。H3 仍 PASS，原 lease 根因 OPEN，正式测量 STOP；没有重试或下一轮诊断 GO。

### 身份、一次执行与证据绑定

BatchMode echo OK 后独立只读 SSH 核查：产品 worktree 仍 clean 冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a`，最终 manifest 仍为 §76 的 `64e0376bd8939176bdc7fd7e3f91473de46d01266edc613cfebcf3d05e1ce3e4`，15 文件及全部模式未变；POST-GO 三行精确绑定 g。preflight 记录原 source checkpoint/input/cache MATCH、三镜像原本机 ID/完整 DiffID 与 labels 核验、no-restart 和新隔离副本，未变为新 build 或 carried 产品结果。实际 wrapper SHA256 仍为 §76 的 `813f228d…31af750`；host PID `2985681`、starttime `201528781`，container PID 1，guardian 首次绑定样本 `2015289290696115` 先于 wrapper ready `2015289726403831` 和 claim。审核未执行测试、新业务、重试或 CT108 操作。

本地复制证据根 `/home/dev/gdds-p6-logs/prepare-step-lease-20261106/p6mutationgcwindow20261106g/diagnostic-evidence/`，远端原始 scenario 根 `/home/dev/gdds-p6-logs/baseline/scenarios/p6mutationgcwindow20261106g/`。本地 `diagnostic-evidence-sha256.txt` SHA256 **`c1006e39cff8d50c4b865639916a8bac99e11ac186eb513a40da53d4d6b9608c`**；独立核 25 项复制文件均匹配远端清单，关键原始文件另从节点核读：

| 证据 | SHA256 |
| --- | --- |
| controller-launcher.log | `8fb88da9f923a61fd67134db6eb0c41ac99f7eeda6cb8ec5ae4eaa34e44dabf3` |
| evidence/prepare-step-result.json | `3b4d00ebebbe8ecdfa1dd4247e867809a05fb6058330fb69989c65746cda75ae` |
| postflight.json | `ba8fb9368c492d28fafbc214b933ccb341a5d6e4737860de81843312d5899970` |
| evidence/worker-events.jsonl | `a68f9c88df50037d375423628b6971cb0ac5d5a21dcff8f3451c47f279b01b7f` |
| evidence/resource-samples.jsonl | `b95db8596b8cf0c971cf74fcd8113bacb791d11f9d2831c099cc3a1de3061d95` |

launcher 完整关闭后的 SHA sidecar 也独立匹配。一次 acceptance attempt/count=1/1、HTTP 202、RESPONSE_VALIDATED，一次 target-bound claim/attempt_count=1；operation=`op-0f698575683380a4bd98b96a`，attempt=`sa-98e14502b0e07e5a1afccfbb`，目标 step 为该 operation 的 `-step-1`/prepare_import。23:25:57 最后可读 selected rows 是 TARGET_FOUND：operation/step RUNNING、attempt PREPARED、cancel=false、repository_operation_id 均 null，只有目标 prepare active。它是停止时的可读快照，不补造成功终态或清理后业务最终状态。

### 失租时已进入 mutation_plan，最终 helper 在 session 前越 deadline

| 实际边界 | UTC / 已返回耗时 |
| --- | --- |
| prepare_build_input return | 22:53:13.829 / 67.033s |
| frozen_projection return | 22:56:55.708 / 107.496s |
| mutation_snapshots return | 23:00:36.707 / 221.000s |
| parent_materialization return | 23:15:59.477 / 922.770s |
| mutation_plan entry | 23:15:59.487，未见 return |
| 最后一次 session heartbeat 成功 | 23:25:24.616 |
| 最后 helper marker / lease_lost | 23:25:57.078 / 23:25:57.083 |

没有 mutation_plan return、canonical_publish entry、claim_exit、clean_drain_requested 或 worker_run_exit。192 次 helper、191 次 session entry/exit，191 个 session 全部 return、191 次 heartbeat_succeeded；最后 helper 抛 StoreBusy，没有进入第 192 次 session。此前 session 原调用最大 11.097s，因此“全部 return”不等于每次都快，也不能用函数总耗时推造其中的数据库等待。

最后 helper 真实传入 deadline=`2017317.426300572`，前次返回 renewal_anchor=`2017287.426300572`，derived due=`2017297.426300572`。其 marker=`2017320054930779ns`，**比 due 晚 22.628630207s、比 deadline 晚 2.628630207s**。entry emit=`5205468ns`，原 helper 真正调用起点=`2017320060110616ns`，已晚 deadline **2.633810044s**；原调用耗时 `5162256ns`、wrapper 至退出 emit 前共 `10459716ns`。所以这次入口日志的约 5ms 不能解释 marker 之前的 22.629s 迟到。

冻结源码 `_heartbeat_until_due` 在调用 session 前检查 now/deadline，过期即 `_fence_lease_for_busy_budget` 并抛 StoreBusy。原始事件和此分支一致；`heartbeat_busy_deadline` 是该 guard 的类别名称，**不是本轮发生 SQLite busy 重试的证据**，本轮没有 heartbeat_busy 事件。GC summary 缺失没有改写这个产品主因。

### 闭合 GC 区间与最后迟到窗口直接重叠

最后 helper entry（第 972 行）带开放 gen2，executor 线程 `131576990004928`、start=`2017296039936871ns`；helper exception exit（第 974 行）保留相同 start/thread 的闭合区间，stop=`2017320055013320ns`。**wall 24.015076449s、process CPU 24.043098116s、同线程 CPU 24.011767181s**。start 比 derived due 早 **1.386363701s**，stop 比 helper marker 晚 **82541ns**；因此该实际 callback 区间完整覆盖 derived due、deadline 到 helper marker 的迟到窗口，且 collection 所在线程在该区间消耗了约 24s CPU。

这是本轮目标窗口的直接正向证据，不再只是粗阶段、旧合成探针或没有 GC 时间戳的推测。它支持“失租空窗与长 gen2 collection 区间重叠”的结论；**不单独证明 GC 独占 GIL、所有 wall 都由 collection 内部独占、唯一根因或未插桩环境必然同样失败**，也不反向补给旧 c/h 相同的 GC 区间。callback 时间边界与普通核心线程能在 stop callback 前后运行的事实均照录，不把两条不同线程 marker 的微小交错改写为原子时间线。

前一个 helper（第 967–971 行）已记录另一闭合 gen2：wall 21.437151563s、同线程 CPU 21.433839698s，该次 session 仍成功。两者表明长 collection 可与显著 heartbeat 延迟共现，但并非每次都越 deadline；不能仅按“GC 大于 20s”阈值推导所有运行的产品结局。无需为保留这一正向证据再跑一次全输入或追补最终 summary；修复策略须由设计基于现有事实提出，本节不预排运行或改变产品语义。

### 核心观测有效片段、覆盖缺口与回收

事件 974 条、618239 bytes、最大 1035 bytes，未达原条数/字节上限。766 个带 GC 字段的事件中 72 complete、694 known_partial；首个 partial 为第 101 行 22:55:17.624 的 `collection_open`，随后保持历史缺口，**不是 694 次独立错误或 collection**。已记录 callback/observer/invalid/cleanup error 均为零、原因只有 collection_open，继续原调用与守护直至真实失租，符合 §74/76 新范围。正向闭合窗口按其覆盖解释；无最终 summary，不能宣称全程完整 collection 统计或“没有其他 GC”。

最后 exception exit 携带前 973 次已完成 emit 的累计统计：encode/lock-wait/write/flush 最大分别 **0.351504ms / 0.010101ms / 5.850636ms / 0.002000ms**，writer failure_count=0。没有这些已报告操作秒级阻塞的证据，但它不覆盖未完成/未报告尾部，不是 observer 无扰动或没有其他调度耗时的证明。最后这次 entry emit 和实际调用耗时单独见上，不把退出记录自身尚未完成的写入计入已报告 metrics。

guardian 411 样本，22:51:46–23:25:57，最大相邻间隔 5.010891187s；worker RSS 最大 23863128064 bytes、host available 最小 43309871104 bytes、disk free 最小 210053865472 bytes，未触资源线。guardian CLOSED/exit 0/reaped，但 worker_exited_cleanly=false，不解释为 worker 正常业务返回，也不覆盖随后完整清理期间资源状态。

pre-down 在停止时保存最后 selected rows、MISSING summary 和三服务 raw logs；索引 bytes/SHA256 与文件匹配，capture 均 exit 0/reaped/group quiet，无 timeout/truncation，worker raw log 仍为 0 bytes。节点也无最终 summary，没有补造正常 worker exit。Compose down=0，postflight_complete/lock_release_allowed=true，自有进程/worker/guardian/capture reaped、project 容器/网络 quiet。独立 SSH 再核 project 容器/网络空、三个目标卷均在、busy lock absent；未删除卷，launcher 已安全解锁。

**本结果和限制直接交实施者并同步设计：GO 已消耗，维持不重试、保卷留证、产品/GC/TTL 不改和正式测量 STOP。** 本节关闭的是这一次运行的边界/停止/回收复核，并提供失租窗口的 GC/CPU 新证据，不宣称产品验收或完整根因修复已经完成。

## 78. Worker GC 调度修复：隔离产品候选范围 PASS，无真实 prepare 运行 GO

**`3759ffbff5` 新增 `p6-worker-gc-scheduling-repair-plan.md` 的定向范围审核 PASS，无阻塞 Finding。** 允许唯一实施者按该范围，从 clean 冻结 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 准备隔离产品修复、必要 CT05 focused/五包静态检查及计划内镜像和一个既有小 Compose 接线验证；不合入当前 main。产品代码与最终镜像/工具/精确清单仍须独立审，真实输入的 prepare-only 验证另签候选专属一次 GO。§76 g 的已消耗 GO 不复用，本节不授权新的真实 POST/prepare 诊断或正式测量。

### 已有故障与最小边界相符

§77 已提供实际失租窗口与 24.015s gen2 区间/同线程 CPU 的直接共现证据。将自动循环 GC 调度移至没有活跃 executor/续租责任的间隙，是针对已发生故障的标准平台策略候选；不要求先证明唯一 GIL 根因才准隔离验证，也不据共现追认 GC 是所有旧失败的唯一原因。方案没有新线程、进程、durable 状态、GC 队列、跨线程设置协议或信任域扩张，符合比例化政策；业务事务/CAS、LeaseSession、ack/发布、checkpoint/digest 和资源显式 close 仍是原语义 owner。

只读核冻结 detached worktree 中真实 `WorkerRuntime.run`：startup 后串行读取 claim_anchor、claim_one、调用 `_run_claim`；每次最多一个 executor。`_run_claim` 正常路径在 thread.join 后检查结果/ack 并 mark_executor_completed，监督异常路径也先 join 后重抛。独立 operation_worker 只组合一个 runtime；进程的 SIGINT/SIGTERM handler 设置 stop event/wakeup，原 drain/fence/join 机制保持。control DB UnitOfWork 的 COMMIT/ROLLBACK 和 connection.close 在显式 `__exit__`/finally 中，不靠自动循环 GC 释放该事务资源。第一方 backend/shared_kernel/repository_client/repository_contracts 生产源码扫描未发现 GC enable/disable/collect/freeze/threshold 调用，未识别需先另建协调协议的已存在竞争 GC owner；这不证明所有第三方永远不调用手动 GC。

按冻结 selector 对照 [CPython 3.14.6 GC 文档](https://github.com/python/cpython/blob/v3.14.6/Doc/library/gc.rst)，disable 控制自动循环回收，引用计数仍存在；[该版本 gc 模块的 collect 实现](https://github.com/python/cpython/blob/v3.14.6/Modules/gcmodule.c#L78)仍可直接请求手动回收。GC enabled 状态属于解释器而非某个 executor 线程，[自动 GC 入口读取该共享状态](https://github.com/python/cpython/blob/v3.14.6/Python/gc.c#L1745)。所以该方案影响独立 worker 的全部线程，不能描述成只暂停 executor 的 GC，也不能承诺活跃期间绝无显式 collection。当前单 runtime/单活跃 executor 的生产组合允许使用这一小范围策略；若未来同解释器嵌入多个独立 runtime 或新 GC owner，须重新界定归属，不能照搬本结论。

### 实施和代码复审应落实的既有条件

暂停必须在读取 claim_anchor/claim_one 之前，覆盖原 claim 和 `_run_claim` 完整收束；不能把一次 collection 移到新 lease anchor 之后再声称已避开预算。无 work 和 claim_one 的 StoreBusy 在原 idle/backoff 等待前恢复；只保留原 claim_one 的异常捕获范围，不能顺手把 `_run_claim` 的 StoreBusy/失租也纳入 claim_busy 重试。正常路径、原异常及提前退出通过 finally 保住原 enabled/disabled 状态，初始 disabled 不被强制 enable 或 collect。

fence、业务异常或 drain 意图不等于 executor 已结束。恢复/可选一次标准 full collect 应位于原 executor join、正常 ack/发布完整收束之后，丢弃已无用途的当前 claim 局部持有，且先于下一次 anchor；不能强杀线程、提前取消 join、复制监督循环或放宽 ack 来到达这个边界。存在原业务失败时，恢复/回收错误不得覆盖主因；正常退出也不能因吞掉真实失败而变成成功。这里是原 runtime 的语义屏障，不要求在每条语句间新增故障注入或持久证明机制。

空闲 collect 本身可以较慢，引用计数也不等于没有循环对象；暂停自动回收可能提高 claim 中峰值。原 40 GiB worker RSS/8 GiB host available/10 GiB disk 守护和 48 GiB 启动条件继续作为这次隔离验证的既定边界，不是精确内存上界或无 OOM 的形式化保证。既有未知循环滞留量可以由这一受控候选记录、触线则停止，不能用“尚未知峰值”预建新回收平台，也不能在触线后自行提高限额。主线 DC87 的 12 GiB worker/kernel M=8 GiB 未被此范围覆盖；即使旧 envelope 下 prepare 成功，也不证明满足主线预算、可合入部署或 Rust 路径已经修复本问题。

### 验证、镜像和接续权限

使用既有真实 WorkerRuntime/生命周期与必要 SQLite fixtures，覆盖 enabled/disabled、空队列/claim_busy 等待、正常完成、原异常恢复和下一 anchor 顺序；保留 heartbeat/发布/ack 的原语义断言。新增或受影响的全局 GC 状态、线程/固定时间用例按 serial 运行，在测试 finally 还原原设置并只移除自有 callback。纯 GC 状态不引入 Dolt；同构状态用共享参数，不靠自造 fake runtime/API 替代真实接线，也不重测已关闭的回收矩阵。五 Python 包 Ruff/mypy 继续按约定在测试节点执行，Rust/依赖未变不另加 Rust 门禁或编译轮次。本轮审核只读源码/文书及版本对应官方资料，未访问测试节点或执行任何测试/业务。

按计划，受影响 focused/静态检查收敛后先交最终 clean 产品提交和源码差异独审，再推进新镜像/小门禁。产品 runtime 已变，原 backend/worker 镜像不能代表新候选。按冻结版本 DC67 在 CT201 构建独立 tag，经 LAN 至05，比较 config digest 与全部 DiffID，并保留来源提交/构建/传输摘要；不覆写旧镜像或借此迁入 main 的新 dependency-base/Dockerfile。RS 仅在原代码/构建输入身份确实满足原等价规则时复用，不因标签 revision 统一而无故重建，也不能用通用 skip 放弃新组合身份。一个计划内既有小 Compose 足以作为本局部候选的接线检查，不宣称阶段退出/完整 production gate，也不追加外挂 ablation 或两轮全输入。

产品差异、镜像和小门禁通过后，在最终新清单中精确绑定旧 source checkpoint→新产品/镜像及必要 wrapper 差异、新项目/key/三个隔离卷。原 g controller/observer 的已知 partial 语义可复用，但不把新 GC 策略伪装成原产品或沿用旧性能数字。保留 45 分钟/3600 秒、原资源/身份/lease_lost/cancel/120 秒 stall 停止与有界回收/保卷/未静止留锁；05 以执行时正常取得占用为准，CT108 不加负载。

**范围 PASS 和准备/必要验证许可直接投递唯一实施者并同步设计，不等新的 Owner/协调者回执。** 同范围普通代码/工具 Finding、修订和必要 focused 沿既有 DC80 双方直接闭环；只有新增范围/预算/资源或业务取舍才带具体证据与选项交 Owner。当前无精确候选真实 prepare GO、主线合入/推送/tag 或正式恢复许可；H3 原 PASS 仅保留历史身份事实，原 lease 根因 OPEN，正式测量 STOP。

## 79. GC 调度修复未提交 diff 预审：线程未启动路径须恢复 GC

2026-11-07，应实施者请求，只读审 `/home/dev/gdds-p6-worker-gc-scheduling-repair` 相对冻结 HEAD `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 的三个未提交文件。**发现一项 P2，最终候选前须修；这是 WIP 预审，不是已提交产品候选/测试结果的最终审核。** 未改该 worktree、未运行测试或访问节点。

审查时 SHA256：worker_runtime.py=`c9d6550087ae0b5a361fddf47c28e346fd004e2dd0f2aaaf16952ae32314b72a`，test_operation_worker_scheduler.py=`b5835c23b5a1789a3d5710586337de55d6f76adaf9cef87888cbaac15c81dcc0`，test_operation_worker_integration.py=`d36a430beac8540b16e9b0a0f4aa8269f407569b2e8febb5812f735c5312de64`。

**G1 / P2：未成功启动 executor，也被归为 join 未确认，泄漏 GC disabled 状态。** worker_runtime.py:358 在 thread.start 前置 join_status.confirmed=False，start 位于同一个监督 try 中。真实线程创建失败时 start 可直接抛异常；except 又对未启动线程 join，后者也抛错，confirmed 保持 false。外层 `_run_claim_cycle` 的 finally 因而不恢复原 enabled 状态，仅追加“join 未确认”note。此路径根本没有活跃 executor，不能套用“活跃 executor 尚未 join 所以暂缓恢复”的规则；GC 初始 enabled 时，run 异常退出后解释器仍 disabled，违反 §78 的原状态恢复条件。[CPython 3.14.6 Thread.start 的创建失败分支与 join 前置检查](https://github.com/python/cpython/blob/v3.14.6/Lib/threading.py#L918)支持该静态调用链，不是新业务现场故障或实际耗尽线程的实验。

已直接交实施者：最小区分“未成功启动”和“已启动但未确认 join”，保留原启动异常，不对未启动线程追加不必要 join/collect，不把它归为 claim_busy 重试；补一项原 runtime 的标准 start 失败语义 focused，核原 GC 状态、无 collect/重试及原错误。无需真实耗尽 OS 线程、扩大注入矩阵或新增 Owner 许可；其余必要 focused/静态验证沿 §78 继续。

**后续工具接线待办：** 新 `_run_claim` 增加 join_status 参数，而原 g 的外置 `prepare_step_worker.py:759` hook 只接受 claim_anchor，原字节直接复用会因 unexpected keyword argument 失败。到新真实 prepare 工具候选时应显式接收并透传同一 join_status 对象，不能只吞掉关键字而失去收束事实；不改旧 g 包、不增加生产兼容路径。此项不阻止当前产品修订/必要 focused，须在新精确 manifest 的接线审核中关闭。

其余 inspected 主路径保持 claim_one StoreBusy 的独立捕获、anchor 前暂停、正常 join/ack 后恢复与空闲 collect；新增 GC 状态测试标 serial，另有真实组合 runtime/SQLite 的发布收束用例。当前只是静态方向检查，不预判其执行通过。产品变化仍要求新 backend/worker 镜像及计划内小门禁；旧 §52/57 image 身份不代表新候选，本轮不构建/重跑。§78 范围 PASS 持续有效，无真实 prepare/测量 GO，正式测量 STOP。

## 80. GC 调度产品候选 0c97cb9c：代码静态复审通过，验证尚未完成

**`0c97cb9c095ef4dde3401ffd874c80ac94d9ac3d` 的代码静态复审无新增阻塞；§79 G1 在代码侧关闭。** 本结论不接受尚未运行的 focused/Ruff/mypy，不是产品修复效果、镜像/容器门禁或真实 prepare 候选验收。实施 worktree 该 HEAD clean；另创建只读 detached 审核 worktree `/home/dev/gdds-p6-worker-gc-review-0c97cb9c` 并链接 legacy，核 HEAD/clean、完整冻结基点增量、调用点和测试组合。差异仅 worker_runtime.py 与 scheduler/integration 两个既有测试文件，未改依赖、Contract/Schema、golden、parser/planner 或部署。diff whitespace 检查及三文件 AST 解析通过，均为静态检查；未运行测试、访问节点或改产品。

候选文件 SHA256：worker_runtime.py=`e5218425d03e6e2d880f098b04802ff7eaff0ceb3115c5043cfadb35664c3b91`，test_operation_worker_scheduler.py=`7204dfcbae4075481425df9e7ef9931e8657e2d51a335835402870866a733c6e`，test_operation_worker_integration.py=`d36a430beac8540b16e9b0a0f4aa8269f407569b2e8febb5812f735c5312de64`。

G1 修正将 thread.start 的异常单独处理：标准未启动失败时 ident=None，确认没有 executor 需 join，原异常重抛，由外层 finally 恢复初始 enabled；不 collect、不等待、不产生 claim_busy 重试。已开始线程的路径仍 join，只有收束确认后才允许恢复；join 失败保留原业务/启动主因并留下最小 note，不因提前恢复 GC 伪称 executor 已停。`_ExecutorThread` 的新增只读 ident 由真实 threading.Thread 提供，共用 ControlledThread fixture 也同步，lifecycle 测试继续引用同一 fixture，没有复制另一套线程 API。没有为现有默认生产 signal handler 不会触发的任意异常时点新增协议或证明矩阵。

其余边界保持：GC 暂停在 claim_anchor 之前，claim_one StoreBusy 单独捕获；真实 `_run_claim` StoreBusy/失租/业务异常原样向外。正常 `_run_claim` join 和 ack 后，外层释放 work 局部引用、恢复原 enabled，再做一次 idle collect，下一次 anchor 尚未读取；无 work/claim_busy 先恢复再等待，初始 disabled 不被强制 enable/collect。私有 claim-cycle 返回 enum 和 join-status 只承载本次进程内分支/收束事实，不新增 durable 状态或并发框架。

必要测试已写入正确 owner：enabled/disabled 的 claim 与空队列/busy 分支、原业务错误、标准 start 失败、未确认 join 及既有 heartbeat 语义，GC 状态用例均 serial/finally 还原；真实组合 runtime/SQLite 用例通过 publish_operation 完成 durable terminal 和原 ack/退出路径，未引入 Dolt。释放引用的 fixture 避免测试自身保留已退出线程 target。以上只核测试内容与接线，**不是用例已通过的声明**。

唯一实施者可沿 §78 现有授权，在 CT05 实际占用释放并正常取得节点后，完成受影响 worker/runtime focused 与五包 Ruff/mypy，记录 clean 起止 HEAD、节点、时间、exit 和完整日志摘要；同范围失败最小修订后直接继续必要验证，不新增 Owner/协调回执门槛。证据齐备后直接交本审核会话，不需要重复申请准备身份；尚不能据此跳过验证构建新镜像或运行业务。

验证通过后仍按原计划准备新 backend/worker 镜像与一个原小 Compose，原 §52/57 镜像不能代表该产品差异；真实 prepare 的新工具 hook 必须显式传递 join_status，§79 接线待办继续保留到精确新 manifest 审核。没有重跑旧 g、扩大预算、主线合入/push/tag、真实 prepare 或正式测量 GO。H3 原历史 PASS 保留，lease 修复效果/内存代价未验证，正式测量 STOP。

## 81. 工具准备两次失败：保留先停，固定脚本待独审后按 DC80 接续

实施者报告 CT05 候选 `0c97cb9c` 已在 clean detached worktree `/home/dev/gdds-p6-worker-gc-scheduling-repair-0c97cb9c-20261107T0049Z`，准备占用已释放，未开始测试/build/lint/manifest/真实 prepare，也未改 E 资源。本审核仅核本地两份错误摘要及其 SHA256，**未把它们称作完整原始 shell stdout/完整命令，也未另起第三次节点检查**。

第一份 `/tmp/p6-gc-node-toolchain-check-0c97cb9c.failure.log` SHA256 **`271453f5a7d378cd9924a93a80fdaaf49547543acac99af34d1f3997cbe64f4b`**，记录 2026-11-07 00:51:27Z、rustc 从 `/home/dev` 执行而未应用仓库 selector，rustup 无 default、exit 1；这不证明仓库选定工具链或缓存缺失。第二份 `/tmp/p6-gc-node-toolchain-check-retry-0c97cb9c.failure.log` SHA256 **`4ad85da76eecd8535f4a6bf5582da927a801c1fc234e460aec4978f75e4c4aa5`**，记录修正命令因本地未闭引号 exit 2、在 SSH 前失败。两份摘要均报告没有测试/产品运行或副作用；不据此修改产品或撤销 §80 代码侧结论。

按现行 AGENTS/testing-conventions 的 DC68，重做再次失败先停是正确历史事实；`f7d53c1c41` 也保留实际失败停止规则，不能把普通 focused 修复流程解释成原样预检无限重试。设计随后明确本次 DC80 的最小修正、独审及合格恢复授权：**具体固定小脚本经本审核核命令、本地 bash -n 与完整 SHA 后，实施者可直接接续 §78/80 必要 focused/五包静态，不等新的 Owner/设计/协调回执。** 不抹掉原两次失败或假称第二次未发生。

已交实施者仅在 CT201 准备独立脚本，避免嵌套引号，固定候选目录和实际所需离线环境/扩展身份前提；Rust/依赖未改，不另加 Rust 编译或门禁，任何版本查询不得隐式下载。原失败证据保留，具体脚本尚待交付/审查，**当前没有工具准备恢复合格结论，节点仍停**；其后正常取得有效占用再执行。本节不设置重新审核产品或扩大测试矩阵的门槛，也不消耗/替代未来真实 prepare 精确 manifest 的一次 GO；正式测量 STOP。

## 82. 固定只读预检脚本首版：语法绑定匹配，两组最小命令修订待关闭

只读核 `/tmp/p6-gc-ct05-readonly-preflight-0c97cb9c.sh` SHA256 **`8f1b93841f3a37f1aa4b66147ba956745f3739a5976febb6e7e23e69c7574e87`**，独立 remote payload `/tmp/p6-gc-ct05-readonly-preflight-0c97cb9c.remote.sh` SHA256 **`ccb962c000476e3ae0bbc922fec9a4147a6b6eaed90ca913ef081917509cfcbf`**。独立 bash -n 均 exit 0，提取内嵌 heredoc 与 remote 文件逐字节相等。只做本地静态检查，未执行 SSH 或脚本，原两次节点准备失败和先停事实不变。**该首版尚不具备工具准备恢复资格**，不据语法通过直接启动节点。

两组最小修订已直接交实施者，不涉及产品差异或新增测试矩阵：

- **Python 禁写字节码的接线失效。** 脚本设置 PYTHONDONTWRITEBYTECODE=1，但 native import 使用 `python -I -c`；[Python 命令行文档](https://docs.python.org/3.14/using/cmdline.html#cmdoption-I)明确 -I 忽略 PYTHON 环境变量，-B 才直接禁止 import 写 pyc。须显式 `-I -B`，不能把当前形式认定为保证不写源/venv 的只读探测。本轮没有实际执行，因此不是已发生的 pycache 写入。
- **环境来源和失败条件不足。** BASE_BACKEND_PY 指向正在并行开发的 main checkout `.venv`，不适合作为已核冻结 1f 环境；改用已核 `/home/dev/gdds-p6-cold-catalog-repair-05/vnext/backend/.venv/bin/python` 并按候选 Rust tree 实测核身份。当前 extension mismatch/unreadable 分支仅 printf 后继续，须非零停止；不把探测结果默认为满足 focused 前提。同时将已打印的 hostname/root/完整候选 HEAD 加固定等值断言，避免 clean 错提交仍输出预检成功。candidate 自有 venv absent 可以作为待准备信息，不冒称其运行环境已通过。

其余命令沿固定 heredoc、候选 vnext/rust cwd、RUSTUP_AUTO_INSTALL=0 和只读版本查询，不新增 Rust 编译/门禁。执行时已正常取得并持有自己的节点占用是脚本前提，不能抢 E 的有效占用；本轮不提前取锁。保留首版及原失败，修订后重新给脚本/payload 完整 SHA 和本地语法证据，沿 §81 DC80 直接复核；合格即可接续既定必要 focused/五包静态，不等新的 Owner/协调回执。§80 产品代码侧结论持续，无真实 prepare/正式测量 GO。

## 83. 固定预检 r2 复审通过：精确工具准备恢复许可

**r2 命令级复审 PASS，§82 两组修订关闭；按 §81 已明确的 DC80 授权，签发 `P6-GC-PREP-RECOVERY-20261107-01`，允许工具准备接续。** 仅绑定 CT201 入口 `/tmp/p6-gc-ct05-readonly-preflight-0c97cb9c-r2.sh`，完整 SHA256 **`6f931d777fd4459ca21531c0092a459a8540981c2ac28795febb7a8b8cdf85a3`**，独立 remote payload `/tmp/p6-gc-ct05-readonly-preflight-0c97cb9c-r2.remote.sh` SHA256 **`cc3aa4a0235f7032f5c9e13b8557a0b40d10a28d9c7227f65be1b0c4097cd823`**。固定执行入口为 CT201 上 `/bin/bash /tmp/p6-gc-ct05-readonly-preflight-0c97cb9c-r2.sh`，经已审 heredoc 调用 CT05 `/bin/bash -s`；不使用旧脚本或临时嵌套引号重拼命令。

独立分别执行两次 bash -n（wrapper 与 remote 各一条命令），均 exit 0；独立提取 r2 heredoc，与 remote 逐字节相同，SHA 与上值相等。也补核首版 remote 的单独 bash -n，exit 0；此前对两个文件放在同一 bash -n 调用中不能单独证明第二个文件语法，本次明确分开记录。首次本地 payload 比对辅助命令沿用首版标记，发生 IndexError；按 r2 实际标记更正后的本地只读比对成功。原错误转录 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-review-20261107/r2-payload-compare-attempt1.log` SHA256 `b59950ce8714c28dd11d0d673e1e0d523fbbf47ee4e866beae22c15ba7968c9d`；不是节点操作或被测对象运行。本审核未执行脚本/SSH/测试，原 DC68 两次失败和先停事实保持。

r2 固定并断言 hostname、仓库根、候选完整 HEAD `0c97cb9c095ef4dde3401ffd874c80ac94d9ac3d`、clean 和 legacy link，源环境固定 clean `1f9731` worktree `/home/dev/gdds-p6-cold-catalog-repair-05` 的 venv；native import 显式 `-I -B`，源与候选 Rust tree/已安装 extension build-input 不符或不可读均非零退出。候选自有 venv absent 明确只是待准备状态。其余为占用/进程/容器查询、离线 uv/Python 信息及候选 vnext/rust selector 下 `RUSTUP_AUTO_INSTALL=0` 的 rustc 版本读取；无 sync/build/test/download、镜像或 Compose 动作，不新增 Rust 门禁。

唯一实施者可在 CT05/root 按既定方式正常取得自身有效占用，再核入口 SHA 并执行该固定脚本。脚本要求 `/home/dev/gdds-node-busy.d/session` 绑定 `p6-worker-gc-scheduling-repair-0c97`；占用不存在不代表已获预约，不能抢 E 占用或伪造他人标记。记录 hostname、起止时间、HEAD、exit 和关闭后的完整日志 SHA；错误/身份/缓存异常留证停止，不原样自动重试，也不在摘要中掩盖旧失败。

预检通过只证明其实际检查项；仍须按原批准流程准备候选自己的 locked/offline 环境并核扩展身份，不能把源 venv 的 MATCH 写成候选环境已验证，或用复制环境继续加载旧产品源码。随后直接完成 §78/80 必要 focused 与五包 Ruff/mypy并交原始证据，无需新 Owner/设计/协调回执。原代码侧结论保持；测试结果、镜像及一个既有小 Compose 仍待产生和独审。

**恢复许可已直接交唯一实施者并同步设计；只准本次具体工具准备及既定必要验证，不是实际 prepare 的精确 manifest GO，也不准正式测量恢复、旧 g 重试、产品合入/push/tag、清理证据或扩大资源/测试范围。** H3 原历史 PASS 保留，lease 修复效果与内存代价未验证，正式测量 STOP。

## 84. Scheduler focused 两项断言失败：补齐原正常退出事件后直接验证

BatchMode echo OK 后，仅只读 CT05 已关闭的 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-20261107/focused-worker-scheduler.log`，完整 SHA256 **`d91ed98213f437fbf654d34dbe31816a63f8ed4c5e395ed5aea21712678f7c1c`** 与实施者一致。日志记录 `gw-dms-test-05`、2026-11-07 01:19:32–35Z、起止 `0c97cb9c095ef4dde3401ffd874c80ac94d9ac3d`、离线 uv-consume --no-sync/pytest -n 0 的 scheduler 模块，**20 passed / 2 failed / 1.78s，exit 1**。本审核未运行测试、修改被测 worktree 或继续其他节点步骤。

两项失败均是 `test_claim_busy_and_empty_restore_original_gc_state_before_wait_without_collecting[True/False]` 的事件列表断言：当前只期待 CLAIM_BUSY。该用例在第二次 wait 设置 drain，原 `_observe_drain_intent` 发 DRAIN_STARTED，原 `_finish_clean_drain` 发 WORKER_EXITED；这两处生产语义未被本轮产品差异改变。因此完整有序预期应是 **CLAIM_BUSY、DRAIN_STARTED、WORKER_EXITED**，不是删掉产品正常退出事件或过滤掉实际多余事件。wait 顺序、claim 次数及 wait 内 GC 状态断言已走到；**失败行之后的 collect_calls==[] 和最终 GC 状态断言未执行，不能称旧运行已经证明这些尾部条件**。

已直接交实施者保留失败包/日志，只补精确有序事件列表、其他断言不变，不改 runtime。该具体 test-only 修订 clean 提交后，按 §78/80/83 已有授权直接从 scheduler 模块开头重跑，通过后接续既定 SQLite focused/五包静态；不为已经审清的这一断言再等一次 Owner/设计/审核许可。若出现独立新问题，仍按同范围最小修订和受影响验证处理，不原样盲重跑。原 exit 1 不写成通过，不提升为权威 runner/业务诊断证据；没有镜像、真实 prepare 或正式测量 GO，正式测量 STOP。

## 85. Backend mypy 四项测试类型错误：最小修订可直接验证

BatchMode echo OK 后，只读核 CT05 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-20261107/backend-mypy.log`，完整 SHA256 **`52ba8e462afd36b261dec3948f5e27eb6e36190da80e141b0926bc22fdc50670`**。记录 2026-11-07 01:24:24–34Z、起止 `eee60c165e232c0f5100de4f9d900cbcd7f132ef`、离线 uv-consume --no-sync mypy、499 source files、四项 error、exit 1。三项 attr-defined 指 scheduler 测试通过 worker_runtime_module.gc 访问未显式导出的导入；一项 func-returns-value 指 waits.append(timeout) or False 使用返回 None 的 append。本审核未运行检查或继续节点步骤；不将该失败写为静态通过。

独立读实施 worktree 实际 diff，只有 scheduler 测试：去掉 worker_runtime_module 导入，三处改 patch 标准 gc.collect；wait 改为具名函数先 append 再 return False。生产 runtime 中 gc 仍是同一个标准模块对象，mock 目标不变；等待函数返回与记录行为不变。**修订方式通过，无新产品 Finding；不添加显式 re-export/兼容别名或 type: ignore 来迁就测试。**

已直接交实施者保留失败，提交此精确 test-only 修订后按既有授权完成受影响 scheduler focused、backend Ruff/mypy，再接续尚未运行的 repository_service 静态，不等新的 Owner/设计/审核许可。其他源码/输入未变且已有完整成功日志的包不因本类型修正重跑；若 SQLite 用例已有合格证据且生产/该用例未变，保留原来源，不重复业务矩阵。最终 clean 提交、各通过/失败日志及身份来源须完整交接，本节不预判这些结果。无镜像、真实 prepare 或正式测量 GO，正式测量 STOP。

## 86. GC 调度候选 9704d0b：代码及定向验证通过，可直接接续新镜像和原单项 Compose

**最终产品候选 `9704d0b286049073529d60036dbd999032f97e0a` 的代码及计划内 focused/五包静态证据通过本次审核，无剩余阻塞 Finding。** 现在可按 §78/80 原范围直接准备新 backend/worker 镜像和 §52 的同一项小 Compose，不需要新的 Owner/设计/审核启动确认。该结论尚不包含未产生的镜像/容器结果、真实 prepare 修复效果或正式测量恢复；H3 原历史 PASS 保留，lease 修复效果及内存代价仍待真实候选验证。

### 最终代码与实际运行环境

本地创建 clean detached `/home/dev/gdds-p6-worker-gc-review-9704d0b` 并链接 legacy，核对冻结 1f 到最终候选仅改 runtime 与两个既有测试文件，diff whitespace 通过。`0c97→eee60c→9704d0b` 的 runtime SHA256 始终 **`e5218425d03e6e2d880f098b04802ff7eaff0ceb3115c5043cfadb35664c3b91`**，SQLite 集成测试文件始终 **`d36a430beac8540b16e9b0a0f4aa8269f407569b2e8febb5812f735c5312de64`**。eee60c→最终提交只有 §85 已审的 scheduler 测试类型写法修正，没有生产/集成用例或其他包变化；§79 产品缺陷及 §84/85 测试问题均已闭合，不重复未变矩阵。

BatchMode echo OK 后，只读 CT05 原始日志及当前 worktree，最终 HEAD 精确匹配且 clean。环境为候选自己的 Python 3.14.6 venv，由受控入口离线 sync；`candidate-env-sync.log` SHA256 **`461f7dac95a61d659b3b8e4e75fec473fa87d53b2676d3f0cc3262186fe01e66`**。Rust 输入未变，未重编；native 从已核冻结 1f 环境复用，实际 `.so` SHA256 `85df42dc6122307edd44d321e7b93282d02e6b886527117b886abdbb315ad71d`、build-input=`58436908aee9dd449f4d3e0542a6a8c1920b6d5e`，与候选 Rust tree 相符；backend 实际模块位置明确指向候选 src，未继续加载旧产品 Python 源码。`candidate-native-identity.log` SHA256 **`32ecfac08b162b1afc7725c8723e247f5045b39c0cf6405dfbf260db2ccb24f5`**，01:18:41–42Z、exit 0。RS 环境 sync 日志 SHA256 `fc3151858875081a01483ac6e5badcc0d06a3a4537a9bf676067876f6739b0cf`，同样离线/受控/exit 0。

最终提交的部分日志 command 行只打印 uv-consume 命令，没有重复写 export 前缀；实施者确认实际外层 `/bin/bash -s` 在执行前 export UV_OFFLINE=1、CARGO_NET_OFFLINE=true、TMPDIR=/home/dev/gdds-test-tmp，原命令保留在其工具调用记录，没有独立脚本文件。本审核没有把这项说明补写成原始日志里的环境行；受控 --no-sync 另先强制 offline lock check，再 locked/no-sync 消费。保留这一记录形式，不因命令展示省略前缀重复已经通过的检查。本审核未运行任何测试或改测试节点状态。

### Focused 与静态证据

CT05 scheduler 在最终候选 01:26:26–27Z，**22 passed / 0.76s、起止 HEAD 精确相同、exit 0**；完整日志 `focused-worker-scheduler-rerun-9704d0b2.log` SHA256 **`530ef22086ab358bfe66bd0e4dd2e62997b174803fec1cacb69ba44e7ce0277a`**。§84 原先未走到的尾部 collect/GC 状态断言现已实际通过。

真实组合 SQLite 新用例在 eee60c 于 01:23:46–47Z，**1 passed / 0.97s、起止该 HEAD、exit 0**；`focused-worker-sqlite-integration-ee60c16.log` SHA256 **`5d434d4d7ff79aa11c837117706ee586397900d35b1e41fee56775cab269141e`**。因生产 runtime、用例、相关输入/依赖未变，可准确关联至最终候选。这里是 focused 证据关联，**不是权威 runner 的按包 carried，也不是 23 项均在最终 HEAD 重跑**。

五包 Ruff/mypy 的十份完整日志逐项读取、重算 SHA，均 exit 0。shared_kernel/contracts/client 在 eee60c 于 01:24:15–24Z，最终仅 backend 测试类型修正，不影响它们；backend 在最终 HEAD 01:26:44Z，repository_service 在最终 HEAD 01:27:09–16Z。日志根为 CT05 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-20261107/`：

| 包 | Ruff 日志 SHA256 | mypy 日志 SHA256 |
| --- | --- | --- |
| shared_kernel | `3dc37c4e6e05ddf35eef0041b2032fb766cf67ec5e37bf9c8e6cc404c0279399` | `f90fbe0ccd9591d4677292f3b6d7c1c00881ff927eecf75fd4d3d287537e248f` |
| repository_contracts | `8dc01e1188c707829fb7e7f191e40d0b8b830462ae8be69990585fbd678132ca` | `bd891a2430658665f58a4586878130688f0ac33f5860f85688eee298fd21d94b` |
| repository_client | `f8b6ce227bf5439549bb0965131c6f33e6c16800fb03d47dfb58d208570c3a34` | `e02faa9409f77590915230af3a9ede29acd9c091049112c6bae81eeae29765bf` |
| backend | `15be7bffd23dddb68141e10249976dc66eb8271d37ac89472207aef474137f3b` | `1ea5e71e74fed83f2029ca500576a21bf39b327264e2767c2a77ff893f9caea8` |
| repository_service | `1462587e221fad72f1a60eacb145702ee14bde8d2fcdd69e5a5a6e74fcb5a608` | `f0aaeee04ef3d41474625045fdb692ce66f4ae41ced8fb62539d35b5ccdacaf4` |

0c97 scheduler exit 1 和 eee60c backend mypy exit 1 的原始日志/提交继续保留，未被替换为通过；本轮没有全量 runner、Rust 门禁或正式基准证据。

### 原范围内镜像和单项容器验证直接接续

生产 runtime 已变，触发新 backend/worker 镜像和容器接线验证；最后验证的 §52/57 backend/worker 仍是旧 1f 镜像，**不能沿用为新产品已验证**。仅从 clean 最终候选按冻结版本 DC67/既有构建路径在 CT201 构建，使用独立 tags，不覆盖已审镜像；LAN 传至05，保留来源提交、输入/构建/传输时间、归档 SHA256、config digest 与全部有序 RootFS DiffID 的跨节点逐项比较，不能拿 inspect ID 替代。保持冻结 Dockerfile/锁/依赖，不迁入 main 的新 dependency-base 流程。RS 只有实际重算有效 build-input/source-tree 等价于 §52 已核身份时才复用；不得跳过身份或为了标签统一无故重建。

CT05 正常取得有效占用后，只对最终镜像运行 §52 已用的 **`tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`**，保持冻结原 harness、离线、prebuilt 及清除代理的既定设置，不追加全量 runner、第二个 Compose、合成 probe 或真实 t1–t4。记录 clean 起止 HEAD、日志/exit、实际三服务运行镜像身份和已审镜像对应关系；使用既有只读 collector，不为取证再启动一轮旅程。按原 harness 回收本次临时项目，保留所有旧候选/真实诊断卷和证据；确认自有资源静止后解锁。失败留证停止，不原样自动重试。

**结论与明确接续许可直接交唯一实施者并同步设计，不再等待回执。** 这些是已通过设计的镜像/单项接线验证，未签真实 prepare GO。镜像/小门禁原始结果随后独审，届时新工具候选须准确传递 join_status 并绑定旧 checkpoint→新产品/三镜像、新 project/key/三卷及完整 manifest；只有候选专属一次 GO 才运行业务诊断。无主线合入/push/tag、正式恢复、提高资源或旧 g 重试许可，正式测量 STOP。

## 87. 9704d0b 新镜像与唯一小 Compose：证据审核 PASS，可直接准备新真实 prepare 候选

**候选 `9704d0b286049073529d60036dbd999032f97e0a` 的 CT201 构建、跨节点镜像身份与 CT05 指定单项 Compose 证据审核 PASS，无阻塞项。** 复用 §86 已通过的代码/focused/静态结论，新增证据准确绑定该候选；不是全量 runner、真实数据完整旅程、实际 prepare 成功或 lease 根因关闭。唯一实施者仍为 `01a1b107-11ba-7681-a7cf-afb1591a67d2`，现可按已通过范围直接准备新工具/精确 manifest 和受影响 focused，不因通信编号回传重新确认角色或等待 Owner/设计/协调回执。**本节不触发实际 prepare，也未签其一次 GO；正式测量 STOP。**

### 构建、归档与跨节点身份

CT201 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-20261107-ct201/` 的 build log SHA256 **`a29198e18db691cab4d327e9a441e23f4a453f6aa70ab1af143e8d61cd756d0d`**、build script `798992fb0368d993bda8917afa3861766ba2c19dba7b6bd3972ef53624955671`、metadata `5d4725608ee701b69625d4d2ec9b5a51802d2da37e14fcff7645156a30bf8623` 均独立重算。记录 `heavy-dev-01`、2026-11-07 01:43:11–01:45:00Z、起止最终 HEAD、clean 输入及 build_exit=0；vnext tree=`f5757bcb56e3e8ee8cde5fba6f903717d91412a2`。Dockerfile/.dockerignore/backend uv.lock/Cargo.lock 的日志 SHA 与该提交 Git blob 相等，未迁入 main 的新构建流程。实际 FROM 的 Rust/Python RepoDigest 与已记录基础镜像相同。按冻结 DC67 在 CT201 host network、无代理、`--load --pull=false --no-cache` 构建，**不称离线构建**；原 Dockerfile 内的 maturin 编译属于本次镜像构建，没有另加调试节点 Rust 门禁。

独立流式重算实际 Docker-save 归档：**397096448 bytes**、SHA256 **`ddbff1b364af2a06b86a16491c3b7b17a140b6c677e2be2b54ec95469397b711`**。只在内存解析其 manifest/config 和对应源代码层，未解包写入磁盘；两 tag 均为 `p6gcgate20261107a-{backend,worker}:latest`，config digest **`sha256:66e362d44814d3db4a98ac8c0c6b5e9175812cd50bbc0895a822baf790648e62`**、全部有序 **15 个 RootFS DiffID**、空 labels 与 source identity 逐项完全相等。metadata 中的 config digest 也一致。归档 `/app/backend/src/gateway_backend/operations/worker_runtime.py` 与最终 Git blob 逐字节相同，SHA256 仍为 `e5218425d03e6e2d880f098b04802ff7eaff0ceb3115c5043cfadb35664c3b91`，确认镜像包含已审 GC 调度实现。

`source-identity.json` SHA256 `02d2e2127d697443298f36f07f115393eb714845ec4ed87a4781969cb336f532`。LAN 传输记录 01:46:14–17Z、exit 0，日志 SHA256 `35dc598f0412307b07232b799976c32c55b6435933faf985bbdb94497aa510fd`。CT05 preload identity（`c98e886a04c69f405e545c5ab0c4c5ac094a3b3b556140ba8b303cc4d3e384d3`）和实际 load/save 后 identity（`7a10ef831772827a398310303023cea1aaf36ff9798ceb350f69b4e5e8d44070`）的两镜像 config/全部 DiffID/labels 与上述实际源归档一致。BatchMode echo OK 后，另只读解析 CT05 roundtrip 归档 config 并核当前 tag 的全部 RootFS 与本机 ID；均一致。跨节点没有用 inspect ID 或 save 归档字节相等代替镜像身份。

新 backend/worker 的 CT05 本机 ID 均为 `sha256:e803ccc6a27aecd8cd32d8409833f85de28c7f063a1e350a0951d816bec74b23`，仅用于本节点容器绑定。RS 在最终候选重算 build-input=`4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`、source-tree=`sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`，与 §52 已核镜像标签完全相同；当前本机 ID 仍为 `sha256:a75aa535046937dab51156c8a8acad0deec913a4daaee9a930c4b62d23cc7e39`，按原范围复用成立，不无故重建或改 revision 标签。旧 backend tag 仍为原本机 `sha256:51307bca08c1fbb7a08a629c13b81bacce2da1f7c8b5732580ff4a26205f725d`，未被新 tag 覆盖。

### 唯一小 Compose 的实际运行与收尾

CT05 `gw-dms-test-05`，01:51:30–01:51:55Z，clean 起止最终 HEAD、五锁 SHA 一致，只执行 **`tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`**、`-n 0`、原 harness，**1 passed / 24.73s、pytest_wrapper_exit=0**。已读实际 launcher：使用候选自己的既有 venv、UV_OFFLINE=1/CARGO_NET_OFFLINE=true、prebuilt 三服务、build network=none、清除代理与专用 TMPDIR，未改 Compose fixture/harness。gate log SHA256 **`189461380a373f22f72db5bb09e6dd4eb810543bf0dbab2c0e1d9c5391939805`**；本审核没有运行容器/测试或触发新的业务诊断。

既有只读 collector 于 **01:51:43.849817Z** 取得项目 `p6gcgate20261107a` 的三服务均 running、服务集合/项目标签与实际镜像 ID 精确相等的记录；独立核行值，不只接受 same_node_image_ids_match 字段。`running-images.json` SHA256 **`33ab95e8358328eb3553803f0405fbe088dae1ccb1fdbf2bc01d710b3836171c`**；`node-local-images.json` SHA256 `56812c5c1bc0909ab542eae62f8af68c6d841b12f0219f2d5258bdcc07311698`。collector 日志 SHA256 `980ebf36d7b9335b6183d0f5f4356cbe602628b297cf0c4599a0bf59149276e4`，记录捕获成功及 exit 0，launcher 退出时 wait 确认收束；没有为取证启动第二次旅程。

postflight 01:52:42Z 记录本项目容器/网络/临时卷均 0、8000 无监听/发布、无 Dolt/pytest/Compose 栈、worktree clean；`postflight.log` SHA256 **`4a511b8df82fc40eea6b28b695441e7c10eb555a1ae68b8367f72a2cfe547200`**。01:52:55Z 收尾释放标记，日志 SHA256 **`d8510bb34de3bb6c39d2777a397e9b5e04576d5c87cb3e85980adc9279081b18`**。本轮只读 SSH 再核该项目容器/网络/卷空、最终 HEAD clean、旧 g 三卷仍存在；不把历史释放当作未来预约，也不为按 DC82 常规取用资源增加跨会话回执条件。只回收本次已授权小门禁临时资源，未清理旧真实诊断材料。

### 文书勘误、接续与结论边界

CT201 镜像副本目录 `...-ct201/ct05/remote-evidence-sha256.txt` SHA256 **`9380749a202a0de1350924dff37fa913f92bc1ca7b1e204267ccb112e4779244`**，独立核实际 **27 行、27 个不同文件，全部 MATCH**。handoff 的“26/26”仅为数量文案错误，已直接交实施者修正；不改原 manifest/日志、不重拷或重跑，不影响本节 PASS。

一次审核端只读 Docker Go-template 查询因 backend Config 无 Labels 键失败，随后改从完整 inspect JSON 安全读取缺省空 labels，一次更正成功；没有写节点、改镜像或执行产品。错误转录 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-review-20261107/image-inspect-template-attempt1.log` SHA256 `07fdfdbdb52491f3c349bdd61dad37cd94546b880da19ea3d1534d767087586d` 保留，不当作 Compose 或镜像失败。

**结论直接交唯一实施者并同步设计，可接续新真实 prepare 候选准备/必要定向修订。** 继续原 source checkpoint 的新 project/key/三卷副本，精确绑定新产品、新 backend/worker 和复用 RS 的身份；旧 g 包/GO/失败卷不复用。原 hook 必须显式接收并传递同一 join_status 对象，原/活跃/恢复后的 GC 状态仅按已审最小观测接线，partial/真实错误和产品主因规则不放宽。准备新完整 manifest 后独立审核，再签仅该精确清单的一次真实 prepare GO；本节没有 POST、worker 诊断或正式测量运行许可，不保证完整规模内存安全、修复效果或唯一根因。无主线合入/push/tag/清理旧证据许可，正式测量 STOP。

## 88. 执行 Owner 新授权：既定范围直接运行一次 prepare，结果事后独审

**已核并执行 `c58f227875c388d4461d699561690d11d32c9854` 的 Owner 2026-11-07 测试环境补充授权。** GC 修复计划新节明确取代本诊断链后续“每个最终 manifest 再签一次 GO”的前置；当前 `9704d0b286049073529d60036dbd999032f97e0a` 已满足 §86–87 的代码/定向验证/新镜像与单项 Compose 审核。此前各节的独立 GO 条件是当时流程记录，不再作为本次后续接线或原定一次 prepare-only 的启动门槛；旧失败、运行和 GO 消耗事实不改写。

已直接通知唯一实施者：完成已批准范围内必要工具接线/focused/预检、核清 clean 源码/已核镜像/原输入与 checkpoint 来源、新 project/key/三卷副本、节点有效占用及既有守护/截止/回收条件，并保存实际 manifest/日志后，**直接执行原定一次真实 prepare-only，不等待本审核者、Owner、设计或协调者再确认**。manifest 用于追溯与运行输入一致性，不是每版审批凭据；不要求 POST-GO.txt。工具若保留授权字段，记录本 Owner 范围授权，不伪称其最终字节已独审。本节记录提交本身也不充当新增启动凭据。

同范围普通脚本接线、测试断言/类型、语法、日志和文书修正，完成必要检查后直接接续；低风险准备命令失败保留日志、查明原因、最小修正，不原样试错，也不因累计失败次数再等 Owner。此前 §81–83 的先停及具体恢复核验事实保留，但不能据其旧流程再制造同类逐次许可。非阻塞文案、计数和补充统计后置更正，不据此重跑已通过场景。

只有实际产品语义、输入来源、镜像身份例外、必要守护或资源/运行范围的关键变化，才集中交审核者/设计评估关键差异。真实产品失败仍停止受影响运行并保卷留证，按 DC80 直接诊断/修复；需要关键修正时将代码与恢复资格合并一次审核决定，不再追加最终 manifest GO。没有修正或新依据，不重复同一大输入；既定一次运行和预算不增加。旧 g 不因此恢复或追加执行。

独立职责改为事后核验本次实际执行清单、运行结果/GC 覆盖、停止/回收、资源和证据来源。原 45 分钟观察/3600 秒总限、资源线、身份/缓存与必要守护失败停止、原业务语义和正式基准验收口径不变。**正式基准仍未恢复；主线合入/push/tag、清理旧证据和扩大资源/范围不在本授权内。** 本轮只核已提交政策并直接同步实施者/设计，没有启动测试节点或业务。

## 89. Prepare a 事后独审：观察预算停止；续租稳定且 mutation_plan 已返回，完整 prepare 未完成

**`p6mutationgcwindow20261107a` 的执行范围、停止分类和收尾/保卷证据核验可接受。** 这是 Owner §88 授权的原定一次 prepare-only，已执行；controller/script exit 1、STOPPED / diagnostic_stop / **prepare_observation_budget**，不是 prepare 成功。03:50:22Z 最后可读目标仍 RUNNING，最终 GC summary=MISSING；没有本次 lease_lost 记录。预算内的续租和已闭合阶段提供有效正向证据，但完整修复、正常 GC 恢复/空闲回收及容量安全尚未证明。**不原样自动重跑；正式测量 STOP。**

### 实际清单与一次执行

最终产品 clean `9704d0b286049073529d60036dbd999032f97e0a`，实际 manifest SHA256 **`141158b3b05132e912d86b09fdc2b947d04a666477d5e03aa1a907ff8ccd619b`**。独立核本地与 CT05 15 文件集合、逐文件 SHA/模式、Python AST，全部匹配；preflight 输入/checkpoint/cache 为 MATCH，新 target volumes 原先不存在、原来源仍是 `p6bw4s4h120261105b:v2-preview`。源记录三卷摘要与实际 manifest 一致；本轮不重复扫描原 940745375-byte checkpoint。目标 backend/worker config **`sha256:66e362d44814d3db4a98ac8c0c6b5e9175812cd50bbc0895a822baf790648e62`** 及全部 15 DiffID 对应 §87 已核归档，RS 继续使用该节已核复用身份。

清单忠实记录 Owner scope 授权 c58f227875、authorized_run_count=1、最终字节未事前独审，不要求 POST-GO。其 status/pre_execution_state 保留准备时快照，真实执行由后续结果/日志记录；不因不可变清单仍写 acceptance_post_sent=false 误判没有 POST。新 wrapper 显式透传同一个 join_status 对象，其余 GC observer/resource guardian/原调用语义沿既有范围。CT05 03:01:44–45Z 的受影响 focused 为 **12 passed / 28 deselected / 0.81s、Ruff F821 通过、exit 0**，原 fork deprecation warning 保留；日志 SHA256 `e3ce02e4fc091df77faca2c5234fb1cd2fac1e610c3523c19461f546db69abd1`，worker/test/verifier 摘要与最终文件相同。

运行 CT05 `gw-dms-test-05`，**2026-11-07 03:04:56–03:53:27Z，2910.532s**，起止 clean 最终 HEAD；一次 acceptance attempt/POST，HTTP 202 / RESPONSE_VALIDATED，一次目标 prepare_import claim/attempt_count=1。operation=`op-2d21a29a34fc33119bd9edb3`、attempt=`sa-73ed1728b8432060ff65c250`、step 为该 operation 的 `-step-1`。停止时 operation/step RUNNING、attempt PREPARED、cancel=false、repository_operation_id 均 null，只有目标 prepare active。没有补 POST、第二 claim 或后继执行；最后可读快照不当作清理后最终业务终态。

Worker host PID `3562604`、starttime `203048848`，guardian 绑定首样本 `2030489645377009ns` 先于 wrapper ready `2030490381330928ns` 和 claim entry；实际 wrapper SHA256 `eb9e00cec10e7e62027c8b81b20818107ce7204d5a52376bf658477b362985f8`。实际来源、镜像、原守护和 no-restart 与已审范围一致。本审核只读本地证据和 CT05 原始已关闭文件/项目元数据，未重跑、重启、修改卷或访问 CT108。

### 停止含义与真实进展

controller 保持 post_started+2700s 的绝对观察截止，并受外层 work deadline/cleanup reserve 约束；实际因观察截止而停止，未触 3120s work/3600s 外层硬限。03:50:22.263Z drain_started 是预算停止后的既定清理，03:53:22.268Z drain_timed_out 距其约 180s，是原 drain 收束状态，不能倒置成初始停因。GC summary 缺失未覆盖预算停止或伪造产品失败。

| 原始边界 | UTC / 已返回耗时 |
| --- | --- |
| prepare_build_input return | 03:06:33.675 / 66.225s |
| frozen_projection return | 03:09:52.433 / 90.236s |
| mutation_snapshots return | 03:13:08.109 / 195.676s |
| parent_materialization return | 03:27:51.912 / 883.803s |
| mutation_plan entry → return | 03:27:51.922 → **03:49:24.784 / 1292.862s** |
| 观察预算停止 | 03:50:22，目标仍 RUNNING |

本次确实通过了此前失租时尚未返回的 mutation_plan，约在预算截止前 57s 正常返回。未记录 canonical_publish entry、claim_exit、clean_drain_requested 或 worker_run_exit。源码在 plan 返回与 canonical publication 之间仍有 schema replay SQL、mutation DML rendering 及拼接；现有粗边界只能界定这一未闭合区间，**不能唯一断言具体哪个子调用正在运行、死锁或其剩余时长**。不以 plan 返回代替完整 prepare/发布/ack，也不据截断时长线性外推完成预算。

### 续租、GC 和资源的有效覆盖

完整事件文件 **1454 条、830799 bytes、最大 797 bytes**，没有事件条数/字节越界。287 次 helper/session 全部正常 return、287 次 heartbeat_succeeded，其中 **269 次在预算停止的 drain_started 之前，18 次在清理中**；没有 lease_lost、heartbeat_busy 或 executor_failed。全部已保存 helper marker 相对 derived due 最大迟到 **0.385090132s**，距实际 deadline 最小余量 **19.614909868s**；session 原调用最大 **0.301487450s**。这表明本轮已覆盖阶段内续租稳定，不把清理后的 18 次计入额外正常观察预算或当作 prepare 已完成。

1148 个 GC snapshot 均 classification=complete、四类错误计数为零。首个 snapshot 含启动期 gen0 73/gen1 7 次，所保留最长区间均早于 claim；之后已保存窗口没有新增 collection 计数或开放窗口，没有 gen2 记录。这与已审产品在 active claim 暂停自动 GC 一致，支持处置方向；**没有单独持久化原/活跃/恢复后的 isenabled 字段，也没有最终 summary，不能据此独立证明整个尾部绝无手动 collection、完整累计统计或 GC 已恢复。** 正常 join 后恢复及 idle collect 在此截断运行中没有完成证据，不为补这一统计重跑本次输入。

最后返回事件携带前 1452 次已完成 emit 的 metrics：encode/lock-wait/write/flush 最大 **0.348255ms / 0.002450ms / 5.138227ms / 0.005120ms**、failure_count=0。它只覆盖已报告操作，不包括该退出记录自身未完成的 emit 或最后尾部，不作为 observer 无扰动证明。

guardian **543 样本**，03:05:06–03:50:17Z，最大间隔 **5.010221738s**；worker RSS 最大 **24260669440 bytes（约 22.6 GiB）**，host available 最小 **42901659648 bytes**，disk free 最小 **202260586496 bytes**，未触原诊断资源线。guardian 于清理开始前 CLOSED/exit 0/reaped，不覆盖随后完整清理期，也不代表 worker 正常退出。该峰值是未完成运行的采样值，既不保证最终峰值，也不满足“已证明主线 12 GiB 预算”的表述。

### 证据、回收与后续边界

本地 `/home/dev/gdds-p6-logs/prepare-step-lease-20261107/p6mutationgcwindow20261107a/collected-run-evidence/scenario-evidence.tar` SHA256 **`1a839f533387d12a20883671e55caec3b1d4705e72830c2bc09b8b1090d39331`**，20 个结构化文件与本地 scenario 副本逐字节一致；关键结果和日志再与 CT05 原件摘要比较相同：

| 证据 | SHA256 |
| --- | --- |
| controller-launcher.log | `aad64e82b9e46dd962511a68ec695f19d0fd36d4dab2f1d45fd8669f9522331e` |
| evidence/prepare-step-result.json | `76f978e4f0fdce95d5f124a45c3317dd691a4938160924c2df32b4988f2d5a69` |
| postflight.json | `e05150991cdf253f34d0de6ec1b95a2860833a105069cf36db89afa3bbb4cc01` |
| evidence/worker-events.jsonl | `55472a17de3a63050f63ed3d636dcd2db71eac7409562360c3974d8248f60fdb` |
| evidence/resource-samples.jsonl | `212f05409307cd1a9e60adce95f8436d6cf4f0258e24230f393e1aac22132e8a` |

tar 没有包含三份 raw service 文件，不能称它单独已含全部原始日志；原件仍在 CT05 scenario 的 evidence/raw-service-logs/，已只读核其 bytes/SHA 与索引相等：backend 54602 bytes / `8a95186627c2d1cf55bc8ccdbaa3835ca54b399966fc444efcba2d123e027122`，RS 220730 bytes / `68cd53c1fcd6d73f4f679a454cdfd5452a44520f35362413f994d0c341c5510a`，worker 0 bytes。pre-down 捕获均 exit 0/reaped/group quiet，无 timeout/truncation；只覆盖捕获时刻，不补造全部清理期间 service log 或正常 worker exit。可后置补齐便携副本，不为复制重跑。

postflight_complete/lock_release_allowed=true，Compose down=0，自有进程/worker/guardian/capture reaped，project 容器/网络 quiet，三个新目标卷完整保留、volumes_removed=false。独立 SSH 另核当前该项目无容器/网络、三卷存在、最终 HEAD clean、占用标记 absent；launcher 已记录安全解锁。missing GC summary 在节点亦确认，没有补写或追跑。

一条审核端本地补充统计命令因 comprehension 的 assignment-expression 语法被拒，未执行读文件主体；更正为普通循环后完成已有证据读取，不触发节点/产品动作。原错误转录 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-review-20261107/prepare-a-local-summary-attempt1.log` SHA256 `4a1189dda68e91e91119b6e2f7c88c7e79d28679166b9bf7959e458b620c4717` 保留，不影响核心结果/停止核验。

**结果直接交实施者并同步设计：原定一次运行已用，执行/预算停止/回收核验可接受，完整 prepare 尚未完成。** 后续基于已保存的 plan 返回、后续源码边界及实际资源决定处置或预算取舍，不自动增加时限或重复同一大输入；关键变化按 §88 集中审，不重新引入逐 manifest GO。保留全部旧/新候选、卷和原始证据，无主线合入/push/tag/正式恢复许可，正式测量 STOP。

## 90. a 恢复资格与 3h/4h 完成性验证集中审核：范围 PASS，准备合格后直接一次运行

**设计提交 `1f84f30654` 的 GC 修复计划末节范围 PASS，无剩余阻塞 Finding。** 本节一次决定 a 的恢复资格及新的预算、日志容量和两个渲染边界；实施者按下列范围完成必要工具修订、受影响 focused 和运行前核对后，直接执行一次新的完成性验证，不再提交最终 manifest 等待 GO、POST-GO 文件或 Owner/设计/协调回执。实际 manifest 用于追溯，不能写成最终字节已事前独审。此处采用设计最终的 **10800s observation / 14400s 全流程硬限**，取代此前 90/105 分钟的早期提案；不追认延长 a，也不恢复其已用运行次数。

本轮只读该计划差异、本地既有 a 结果/事件和冻结 `9704d0b286049073529d60036dbd999032f97e0a` 源码、原 a 工具；没有 SSH、新节点取证、产品导入、测试、业务请求或运行。§89 原始结果与限制全部保留。

### a 不具备本次可用的续接 checkpoint

冻结 `infrastructure/repository_write/import_publication.py:235–307` 在 plan 返回后仍构造 schema input、调用 schema replay SQL 与 mutation DML renderer、拼接并完成 canonical publication，之后才创建 PrepareImportCheckpoint。`application/submit_jobs.py:547–562` 等 publication 返回后才调用 `_prepare_step_checkpoint` 持久化；plan 返回本身没有 durable 续接点。a 的全部已保存阶段事件未出现 canonical_publish entry、prepare_package_publish return 或 prepare_handler return，最后可读目标仍为 RUNNING；没有已核完整 checkpoint 可供复用。最后 snapshot 的 steps 投影不含 checkpoint_ref，不能把字段未查询写成数据库中已实测 null，也不声称已扫描证明卷中不存在任何孤立文件。

**本次恢复资格结论为不能续用 a 的 RUNNING 卷或内存 planner 结果。** 新 project/key/三个新目标卷只能从已核 `p6bw4s4h120261105b:v2-preview` 来源建立，原 W4 输入/cache/规则、source provenance 限制及 §87 三镜像身份保持；全部 a 与旧候选/卷留存。不为寻找恢复机会再启动 a、访问其活动数据库、造中间态持久化或追加全卷扫描。

### 新预算与既有守护

- 一次业务观察上限 **10800s**，保持原 post_started 起算；全流程工作截止为 launcher 起点后 **13500s**，预留 **900s** 清理，全流程硬限 **14400s**。shell 的 timeout/kill-after、controller 的 observation/work/cleanup 截止与 guardian 的 soft deadline须一致接线，不能只改展示字段或仅延长一层；运行中不滑动截止，完成即收尾。这是避免反复重做约 44 分钟前沿的一次受控上限，不是完成时间预测。
- 启动 available 至少 48 GiB、worker RSS 40 GiB/host available 8 GiB/disk 10 GiB 原停止线、lease/heartbeat/stall、单 POST/单 target claim、no-restart、异常/身份/必要观测停止及原收束/保卷/安全解锁条件保持。延长窗口不屏蔽资源或产品失败，不把该隔离诊断 envelope 当成主线 DC87 部署预算的合格证明。
- 仅复用原 `_phase` 委托方式，为 import_publication 实际使用的 `render_repository_import_schema_replay_sql` 与 `render_planned_import_mutation_dml` 增加入口/返回/异常事件，原参数、返回对象和异常原样传递；不逐行观测，不改变 renderer/planner 或重建镜像，不增加合成探针、Compose 或全量 runner。

### 日志容量核对及必要接线

计划“每轮四个调用事件”漏计原 worker_event/heartbeat_succeeded。a 实际 287 次正常续租对应四个 helper/session 边界各 287 条，加成功事件 287 条，即**正常每轮五条**。按 4 小时、10 秒间隔保守估算约 **7200 条**，再加少量阶段/生命周期事件，仍低于 **8192 条/16 MiB**，无需另扩大额度；异常重试可能增加记录，保留超限即停止，不承诺任何异常序列都不会触限。单条 2 KiB、最终摘要 32 KiB 保持。

实现必须同步所有 worker-event consumer：原 controller `_verify_worker_ready` 有 8 MiB 文件上限、观测循环有 4096 条计数上限；resource_watch `_read_worker_events` 同样用 8 MiB 检查 worker 日志。不能只改 EventWriter，留下旧读取限制提前截断。guardian 自己的资源日志继续 **4096 条/8 MiB** 即可：4 小时约 2880 次、计入首样本约 2881 次，且每条不超过 2 KiB，仍在其原有上限内；worker-event 读取上限与资源日志写入上限应明确区分，不无故扩展其他日志/原始服务日志限额。controller/guardian 继续消费同一实际 event 文件，既有 GC partial 与错误分类不变。

这些是已审范围内的具体实现要求，不是追加候选审批门槛。复用现有用例，只验证两个真实符号的委托接线以及改动的写入/读取容量边界，保留必要的 AST/语法/文件摘要与 clean/镜像/输入检查；不重测未变矩阵。实施者准备合格即可按 §88 和本节运行一次，保存实际清单、hostname/时间/HEAD/exit、事件/资源/正常收尾或停止证据后交事后独审。要评价完整修复，仍需实际 prepare 完成、原正常 claim/join/worker 收尾与 GC 恢复/空闲回收路径的证据，不能仅凭未失租或 planner 返回判定成功。

**本范围许可仅为上述一次完成性验证；不是新的正式计时、产品合入/push/tag 或正式基准恢复。** 无变更无新依据不原样重复大输入，实际失败停止保卷并按 DC80 最小修订；普通修订直接闭环，不重建逐摘要 GO。H3 原历史 PASS 保留，正式测量继续 STOP。

## 91. Prepare b 完成性事后独审：限定范围 PASS，GC 覆盖与空闲回收成立，guardian 派生标记不阻塞

**`p6mutationgcwindow20261107b` 的一次 prepare-only 完成性验证、已注册 GC observer 覆盖及正常收尾审核 PASS，无阻塞 Finding。** 固定输入下 prepare 已完成、375 次续租均成功，后继 submit_import 未领取；这关闭 §89 的“只到 planner 返回、未覆盖正常收尾”缺口。结论仅属于本次隔离候选，不证明全部历史失租的唯一原因，不代表完整 Submit/业务旅程、主线资源预算或正式性能验收。**本次运行已用，不授权重跑、继续后继步骤或恢复正式测量。**

### 候选、身份与证据绑定

最终实际 manifest SHA256 **`97d7e90685e1f0747c5e887243ec61a14fa067b163fbdb279288a6ca64ac275f`**，15 个候选文件的集合、逐文件 SHA/整数权限模式及 Python AST 独立核对通过。a→b 的 worker 只扩大既定事件预算并增加两个真实 renderer 的 `_phase` 委托；controller/guardian 的 worker-event 读取上限同步，资源日志仍 4096 条/8 MiB，原 GC observer 未变。shell/controller 的 10800/13500/900/14400 秒接线符合 §90。没有新增产品代码或依赖，故不触发镜像重建；产品保持 **`9704d0b286049073529d60036dbd999032f97e0a`**，最后合格镜像仍 §87 的 backend/worker config `sha256:66e362d44814d3db4a98ac8c0c6b5e9175812cd50bbc0895a822baf790648e62`（15 DiffID）与 RS config `sha256:b81faa1f970999676087a55f0fc63e17d4285fba73b04c5eca6a69612e1419aa`（28 DiffID），不把本诊断当新的容器门禁。

已保存 preflight 的源码/输入/cache/镜像核验与该候选相符，source 三卷摘要、完成至 v2-preview 与 a 的已核来源逐项相同，目标为全新 b 项目，未复用 a RUNNING 卷。source RS run-bound full identity 仍明确 UNAVAILABLE，沿既有诊断来源限制保留，不写成 carried。CT05 focused 日志记录 clean 起止最终 HEAD、04:36:35–36Z、**14 passed / 28 deselected / 0.82s、原 fork warning、Ruff F821 PASS、exit 0**，SHA256 **`ddde0e989ca7ad4b98147e144745eebc8426ae5bc0a32c6555a4ca26dcd58214`**。

本轮只读本地已交原始候选、结构化归档/副本、节点原日志副本及冻结源码；没有 SSH/实时节点确认、新取证、导入、测试或运行。归档 `/home/dev/gdds-p6-logs/prepare-step-lease-20261107/p6mutationgcwindow20261107b/collected-run-evidence/scenario-evidence.tar` 为 **1290240 bytes**，SHA256 **`f627cd36c28f7af2eb7c8ad32f53cd0ff348fa13fd532b918e925fcb897fd2f2`**；22 个普通文件逐字节等于本地 scenario 副本，也全部匹配交回的 remote inventory（SHA256 `1cef2a2ac261778f39a5759dd1901efc3c90e1b6d9c8a9e7b6f267192da1b992`）。该归档不含 secrets/三份 raw service 内容，不宣称本轮重算了远端 raw 原件；其捕获索引记录均 exit 0/reaped/quiet、无 timeout/truncation。

DC68 两组准备错误及七份绑定证据摘要均核对通过：旧 image-identity 常量导致只读 preflight 退出，另一次 transfer 的额外 manifest/checksum 被候选集合检查拒绝，均发生在 scenario/worker/POST 前。修正后的 controller 摘要与新日志名已固定，原失败未覆盖；不把它们计作两次 prepare，也不因准备错误新增回执或重跑门槛。

### 唯一业务执行与明确的尾部耗时

CT05 `gw-dms-test-05`，**2026-11-07 04:39:22–05:42:33Z，3791.155s，controller/script/SSH exit 0**；launcher SHA256 **`1e4f175f057417bdcc06fe7d86c01683733fd7c2db11b619d057f1537a65950f`**，clean 起止最终 HEAD。单 acceptance POST 返回 HTTP 202 / RESPONSE_VALIDATED，单 prepare claim/attempt_count=1；operation=`op-e9585d1c707fabe7b130f1c7`、attempt=`sa-c82720c7299c57bed1eff3a9`。prepare step SUCCEEDED，后继 submit_import PENDING/attempt_count=0，operation/attempt repository_operation_id 均 null，没有第二 claim。operation 仍 RUNNING、attempt 仍 PREPARED 是限定 prepare-only 停点的实际状态，不能写成整个 Submit 已成功。

10 个 phase 均正常 return；prepare observation **3755.338s**，prepare_handler **3755.815s**。关键阶段如下，存在外层包含关系，不累加全部 phase 时长：

| 阶段 | 实际耗时 |
| --- | --- |
| prepare_build_input | 65.387s |
| frozen_projection | 89.104s |
| mutation_snapshots | 195.029s |
| parent_materialization | 876.438s |
| mutation_plan | 1296.669s |
| schema replay SQL renderer | 0.004329s |
| planned mutation DML renderer | **1115.868s** |
| canonical_publish | **0.805933s** |

因此 §89 未闭合的主要尾部现已明确在 **mutation DML 渲染约 18.6 分钟**，不是该次 canonical publication 本身的长耗时；它正常返回，没有证据支持死锁。本次为带观测的完成性运行，不据此生成正式性能数字、比较新旧加速或外推其他输入。

### 续租和 GC 的实际覆盖

事件共 **1904 条、1088165 bytes、单条最大 798 bytes**；helper/session 入口出口各 375 条全部正常返回，worker_event/heartbeat_succeeded=375，没有 lease_lost、heartbeat_busy、executor_failed。helper marker 相对 derived due 最大迟到 **1.588280016s**，距实际 deadline 最小余量 **18.411719984s**。1500 个 gc_since_previous snapshot 均 complete，cb_err/cleanup_err/invalid/obs_err 均为零，incomplete/open/gap 均为空。

最终 summary 的 complete/overall_observation_complete/event_writer_complete 均 true，callback/cleanup/observer/invalid-transition 错误均零，coverage_gaps/open_windows 为空；成功 emit 数 1904 与实际完整文件相等。callback 在 bootstrap 导入/运行前注册，bootstrap 正常返回后移除并生成最终摘要；源码与这些结果支持**这一注册窗口内的 bounded observer 覆盖完整**，不扩写为 callback 移除后全部解释器退出过程或每对象堆审计。

gen0/1/2 分别报告 collected **1575/147/44640**，uncollectable 均零；gen2 唯一完整区间 `2039912110453083–2039912606841184ns`，耗时 **496.388101ms**，与 claim/worker 主线程相同。独立核单调时序：claim_exit=`2039912110353432ns`，clean_drain_requested=`2039912110417642ns`，然后该 gen2 开始/结束，最后 worker_run_exit=`2039912607186688ns`。所以这次确有 **claim 正常返回后的空闲 generation-2 collection**，不是把“未见 GC”当成回收成功；结合已审 `_run_claim_cycle` 的 join 确认、恢复 gc.enable 后 collect 控制流，正常收尾路径已走通。没有单独持久化 isenabled 值，也不由 collected 对象数推算回收字节或 RSS 下降归因。

writer 最终 metrics 的 encode/lock-wait/write/flush 最大为 **0.345144/0.119541/26.199919/0.005630ms**、failure_count=0；这不是 observer 零扰动证明。最终 GC summary 完整不建立旧失租唯一因果，也不把旧 g 的失败追改为通过。

### guardian false 的含义、资源与收尾

**guardian.worker_exited_cleanly=false 不构成本次业务/收尾阻塞。** 它只在自己的 5 秒轮询消费到 worker_run_exit 时置 true；controller 正常 `_stop_guardian()` 则 set stop_event、唤醒 wait，guardian 可以直接结束循环而不再消费一次事件。实际最后采样为 `2039912272865494ns`，比 worker_run_exit 早 **0.334321194s**；guardian CLOSED 于 `2039913.474661739s`，比该退出事件晚 **0.867475051s**，仍早于下一次约 5 秒采样。原 handoff 的“其后约 3.8 秒”不是这一单调时间差，应后置更正文案；不修改原 guardian flag。

原控制流先 `_wait_worker_exit` 确认容器 exit 0/no-restart/进程已回收，再 capture、关闭 guardian 和 Compose down；实际 worker_exited/worker_run_exit=0、容器 exited/exit_code=0、postflight reaped 相互一致。guardian 无 stop_reason、无 signal、正常 exit 0/reaped/ready，未出现资源守护异常提前停止。上述控制流和时间关系足以解释 flag 未消费到退出事件；不需为派生标记重跑大输入、补造最终采样或新增生命周期机制。离散采样不覆盖两次样本间的瞬时峰值，关闭后的清理期也不冒称持续资源采样。

资源为 **756 样本**，04:39:32–05:42:29Z，最大间隔 **5.010789925s**，guardian 绑定首个 worker 样本早于 wrapper ready/claim。worker RSS peak/last **24266887168/2527236096 bytes（约 22.6/2.35 GiB）**，host available 最低 **42892359680 bytes**，disk free 最低 **201185333248 bytes**，未触原隔离诊断停止线。该峰值不能替代主线 DC87 的容量验收。

postflight complete、down=0、owned processes/项目容器/网络 quiet、worker/guardian/capture 均 reaped、lock_release_allowed=true，三个 b 卷保留、未清理 a 或其他旧证据。已保存 05:43:24Z 节点后检日志记录 clean、锁 absent、无项目资源/8000/Dolt/候选进程；SHA256 **`bcebb615ac532c7fea3046ae299cc28c7d2e2efc646e209ad0a7516b1f77ea33`**，不是本审核的实时节点复核。

| 核心证据 | SHA256 |
| --- | --- |
| prepare-step-result.json | `13d68d338d524c008ff900e0ac0a9ff6c375b023bec69197d86abff1774dd829` |
| worker-events.jsonl | `d00270e803e975ef2dc8afe061c484baab8078b4dc92a86f002d8cf0c0a1ae69` |
| gc-observer-summary.json | `397fb0d1d9a418c36118959a79d27ac30372bbf6b282e45c9038b4372ee4b354` |
| guardian-result.json | `f461f88fc41cd5cac4aea768d7b0f821db07dbb93f657cf3119fb551a593c0dd` |
| resource-samples.jsonl | `fa6dc02acc5578ad636bee42d3e25eaf8256111b6d1c311978664353ae84826e` |
| postflight.json | `4587d14019d38201ec78a915f8764ddbad53164d4ed93e7b083ba50735f9fa2e` |

**结果直接交实施者并同步设计：本次限定完成性 PASS，guardian 派生 false 按上述限制保留，不要求新 focused 或重跑。** 普通 handoff 时间文案后置更正。没有下一次运行、后继 submit_import、清理卷、合入/push/tag 或正式计时许可；H3 原历史 PASS 保留，正式测量恢复与版本/来源资格另按原范围处理。

## 92. Owner A 的有限恢复关系集中核验：PASS，按分版本口径直接准备并接续首轮

**设计已记录 Owner 选择 A，`ad22c99c16`、首轮预算补充 `d137a47d0fd96ea53e3d09998085e04d5a7102ba` 及既有有界执行方式澄清 `469e5d2b901f3b6ff3e119c500309eb4bc4c0837` 的有限 source→目标、计时起点、必要守护与关键预算集中核验 PASS。** 既有唯一实施者可直接完成必要工具修订、受影响 focused、目标节点/离线缓存/镜像前提和固定运行材料，合格后现场取锁执行首轮并按方案 A 顺序补缺；不等新 Owner/设计/协调回执，不另签最终 manifest GO。实际清单留作追溯，结果事后独审。本会话只核本次有限恢复关系与其结果，不接管基准 exit；04 收口和全部历史证据的终审不变成首轮启动前置。

本轮只读已提交方案、既有 §87/91 证据和冻结源码，并用本地 Git 核祖先/产品路径；无 SSH、节点取证、导入、测试或测量。此前的“Owner 尚未选择/所有后续测量 STOP”是历史快照，**不再阻断已批准的 A 分版本接续**；统一版本完整正式基准并未因此恢复。

### 来源例外和目标继承关系

恢复输入只取原 **`p6bw4s4h120261105b/evidence/checkpoints/v2-submit`**，其 **completed_through=v2-preview、resume_step=v2-submit**。这是 §89/91 已核的原来源，不是更早 a 项目的 Preview 前 checkpoint，也不是诊断候选 b 的 prepare 后状态。已核三卷内容、W4 manifest/cache/规则及 TTL 继续检查，新 project/key/三卷隔离，原源卷、a/b 诊断卷及旧证据只读保留。源 RS run-bound full identity 仍记 **UNAVAILABLE**；Owner A 只接受其作为受控输入的限定例外，不能伪造 identity MATCH、正式 carried 或把旧步骤计时归为目标版本。

本地 `git merge-base --is-ancestor e798ec87a37330250b0c051162e7962dba1daa60 9704d0b286049073529d60036dbd999032f97e0a` exit 0；`application/checkpoints.py` 的对应 diff 为空。目标确实包含 READY 容量修复，而非需要证明两棵树相同。其后 7 提交/12 个 vnext 文件覆盖 RS metadata/cold catalog、JCS sink、worker GC 调度及必要导出/测试；这不扩 DC80 原 READY 特例，新的跨版本输入资格来自 Owner A 本次决定。

目标固定为 **9704 产品及 §87 全身份已核三镜像**；允许在隔离参考线上形成仅含必要 benchmarks/tests/docs 的 clean 工具候选 V_ref，运行前证明生产源码、依赖/锁、Contract/schema/载荷和部署输入与已审目标相同，不混当前 main/S2b。普通恢复工具只能表达这一个已批准来源→目标关系、真实 completed/resume step 和实际镜像绑定，不用通用 skip 放行其他身份差异，也不借旧 READY approval 冒充本次授权。既有镜像按 config digest/全部有序 DiffID 离线预置 CT108，完整同节点容器身份绑定照常；这些工具修订本身不改变已审产品镜像内容，不为标签统一重建。若实际触及 Dockerfile/Compose/生产依赖或容器运行边界，仍按原规则处理，不能称纯工具。

### 首轮实际选项、计时与固定上限

首轮是 **t4、scope=full、MODIFIED_ONLY、resume=v2-submit**，full_v2/three_node_history/cross_project 均 false，history_cache_mode=none。新执行 v2-submit→v2-repository-read→v2-approve→history，再作原有尾部核对；没有新增 Archive/v3 业务旅程，不重做已完成 Preview。完整 v2-submit 从原受理边界开始，包含 prepare、Repository 提交/等待和原可见性核验；不能接诊断 b 的 successor、跨节点拼接耗时或拿其约 63 分钟观察结果填正式字段。

| 首轮阶段 | 工具预算 |
| --- | ---: |
| 初始化/预检/恢复/必要快照 | 1800s |
| 完整 v2-submit | 10800s |
| v2-repository-read/approve/所属普通 HTTP | 1800s |
| History/结果读取 | 7200s |
| 尾部表哈希/比较/artifact/归档及正常证据 | 3600s |
| 固定工作截止，自 launcher 起 | **25200s** |
| 停止/reap/Compose cleanup/postflight 预留 | **1800s** |
| 同一起点的全流程硬截止 | **27000s** |

五阶段之和为 25200s；Submit/History 等长操作截止=min(操作起点+操作预算，固定 work 截止)，不重置总起点或运行中逐次加时，完成即收尾。辅助阶段的数值用于计算总 work 和余量，沿原单 HTTP/I/O 超时和既有外层 work/hard 控制，不要求为每个 helper 新建强取消层。10800s 是本 W4 工具等待覆盖，替代旧 `ceil(810.961×5)=4055s`；History 阶段预算包含其原操作轮询及结果读取，初始化和尾部不得漏出外层总限。1800s 的 read/approve 段不新增 v2-archive 业务步骤；尾部 3600s 的“归档”指原有证据/artifact 收尾，不是增加 Archive operation。冻结源码的 v2-archive 仅在 three_node_history=true 分支执行，本轮 false；旧模板的 checkpoint 名称列表不能驱动额外业务。保持产品 lease/heartbeat/stall、HTTP 单请求、RS 业务超时与错误分类，不能把工具预算当成产品配置、ETA 或性能门槛。沿既有有界进程/容器收束，work 耗尽停止新业务、使用预留清理，全部受 hard 截止约束；不新建 guardian/持久状态机。

CT108 按实际现场空闲/有效占用与独占测量规则取锁，满足该节点实际离线缓存/数据/空间和已核目标镜像前提；不用预约/回执替代现场条件。复用原轻量采样、状态感知的健康/续租监视、真实数据一致性和失败留证/保卷/安全解锁规则，不把诊断 wrapper、GC callback 或 profiling 带进参考计时。普通脚本/接线修订由实施者做必要 focused/静态和固定预算检查后直接接续，不要求重跑已通过小 Compose 或 prepare-only。

### 分版本交付与收口归属

已完成 t1–t4、2× core、W3-FULL/H1-FULL、H1-REFILL、H2/H3 按各原记录的产品/镜像/节点保留历史结论，不回填为 9704；较新的实际完成记录优先于旧待办快照，索引真有缺口则如实标记。W4-FULL/STRESS、631 表 hash、DC63 #1、V5b、JSON/comparator 只补实际未完成范围，沿方案既定定义和实际来源记录，不以名称相似重复运行或扩展本次来源例外。记录无法表达多版本时，用多份真实记录加总索引或最小工具修正，不能伪填统一 HEAD、填零或写未证 PASS。

04 最终 runner 归冻结参考线最终 V_ref；按实际包闭包与合格来源决定运行/沿用，不借 main/S2b 结果，不把 focused 当权威 runner，也不把本报告当最终门禁通过。该项与 CT108 可按原节点分工并行推进，阶段 exit 另由适格角色办理。

**本次有限恢复关系已通过，执行方无需等待本会话复核另一份最终摘要。** 正常准备合格即按上述固定首轮运行、随后按 A 补既定缺项，结果独审；实际身份/缓存/守护/数据不符仍停并按 DC80 最小诊断修正，不原样盲重试。需要新业务取舍、资源上限或超出本次来源条件的例外时给具体替代方案，不外推本 PASS。未授权主线产品合入、push/tag、清理旧证据或提前办理基准 exit。

## 93. c898 实际接续工具审核：固定绑定通过，外层超时收束存在一项具体阻塞

按实施者请求，独立读 `/home/dev/gdds-p6-baseline-vref` 的 clean 最终候选 **`c898922ffa5e8541783f4e47567cbaf4efc8eee8`**。产品基准仍为 9704，候选 vnext tree=`be56bf9a3fef7aa5b20f0b761e557c4e915164bf`；相对 9704 的 vnext 差异只有 backend benchmarks/tests，其余为文档。ad06cf9bb9→c898 实际只追加 handoff，focused 对应代码未变。本节不重开 §92 的来源例外、版本口径或历史矩阵，不扩基准 exit；**CT108 只读前提核验及镜像准备可按原授权并行，不应等待新审核回执。**

### 已核绑定与证据

- 固定 identity JSON SHA256 **`eb9fc808eef9221dd2d8169607ad914f3643b557d58588a95fa6f39b796a5e09`** 与代码 pin 相符；其三镜像 config/全部有序 DiffID/labels 与 §87/91 已核身份逐项匹配。源码在复制 checkpoint 前及 Compose 启动路径重核目标身份，源 RS 缺口持续记 UNAVAILABLE/input only，未变为 MATCH/carried。
- `_require_post_gc_source_evidence` 绑定原 b 项目的 run/state/log SHA、e798 HEAD/exit1/v2-submit 失败、completed_through=v2-preview、相同 input manifest/census；原 checkpoint 实物摘要及克隆后逐卷比较仍在既有路径中。固定 target/new project/key、full/MODIFIED_ONLY、无 three-node/cross-project/full-v2、无 cache 操作、完整 Submit 计时及通用参数拒绝守卫与 §92 相符。未把诊断 b 的 prepare 后态用于续接。
- Python AST 只读解析通过；代码 pin 的产品 commit/tree 与候选 tree 分别记录，生产路径与 9704 相等，未错误要求包含工具改动的整个 vnext tree 相等。backend/worker 的 labels 已包含在 config digest 内，RS 另逐项比较完整 labels；不要求用跨节点 inspect ID 替代。
- BatchMode echo OK 后只读 CT05 已关闭日志：clean 起止 `ad06cf9bb9d8edf3ae1c67291247eb9b4edc6332`，07:08:17–20Z，**5 passed / 152 deselected / 1.91s、exit 0**；focused log SHA256 `cc151b1965ff304650b90c28859c2cb3fa17387f58b0beab0cfbbc4e1e70e488`、meta `1b20fd7c05cc0c9909d6fcdcc6590e618b99571a157fb2ffe6861a95cba11667`。候选 locked/offline sync 和 native build-input MATCH 日志存在，07:09:42Z postflight clean/quiet，SHA256 `5f9f887a7d1d8f32b59d2621e750827e8143cc7a5c7a6c9829d378cde02d009b`。这些不是完整 runner、五包静态或 CT108 前提已通过。

本轮未导入/运行候选、复跑测试、复制卷、启动 Docker/业务或访问 CT108。CT05 操作仅为读取上述既有日志，不称新的测试证据。实际 CT108 source/input/cache/TTL、node/target tag/层身份仍由实施者按 §92 在运行前实核，不能把本静态结论当已实测。

### F1（阻塞，P2）：总截止可打断旅程 finally，外层未保证 Compose 业务停止

候选 `vnext/backend/benchmarks/p6_s1b_measurement_runbook.md:1010` 仅以 `timeout --signal=INT --kill-after=1800 25200` 包住共享 p6_baseline_resources；上层 set -e、没有自己的 EXIT/INT/TERM 清理 trap。共享 sampler **`p6_baseline_resources.py:510–519`** 捕获 BaseException（包括超时信号引起的 KeyboardInterrupt）后立即 `child.terminate()`，即 SIGTERM 旅程子进程，再等 30s/kill。这会与 journey 已因 SIGINT 进入的 finally/Compose down 竞争，并可能直接终止该清理。采样器只回收宿主子进程，不负责停止 daemon 管理的 Compose 容器；外层命令非零后 shell 直接退出。因此当前固定入口不能保证 work 截止后停止新业务、清理期间终止自有 worker/栈并安全释放占用，host process 被 kill 不等于 Docker 业务已停止。没有执行失败实验，本 Finding 来自实际控制流，不能说已复现泄漏。

**最小修订已直接交实施者：** 保持共享 sampler/step timer 和产品不变，复用既有 launcher 的有界外层清理、postflight 和安全解锁；只针对固定新 project/自有进程/容器/网络，保留全部源/目标卷，处理成功、非零、INT/TERM/工作截止。清理用原 1800s 预留并受同一 27000s 硬截止约束，不在 handler 重置一套完整新预算；未确认静止则保留占用并如实失败，不回报安全解锁。不要为此修改共享采样器而重跑历史计时、添加 guardian/持久状态机、扩大停止预算或补跑真实 prepare/Compose。用一个小的外层停止路径 focused/既有 fixture，加脚本语法检查，验证超时非零、清理调用与保卷/未知状态保锁的实际接线即可，不铺新矩阵。

另已直接提醒：handoff 尚未给出本轮五包 Ruff/mypy 的合格记录；按 AGENTS 补必要静态检查或明确关联确实未变包的既有合格来源，尤其 backend 新工具/测试须有本轮检查。该项是准备验证待补，不虚构为产品断言失败或要求完整 runner。

**当前结论：固定绑定与代码范围通过，F1 必须在实际业务启动前最小修正；§92 范围许可保持，准备工作继续。** 按上述已审具体修订完成必要检查后直接接续原授权，交修订/日志供短复核，不再请求新的 Owner/范围/最终 manifest GO。没有新产品、依赖、镜像运行边界变化，不据该工具 Finding 无故重建 §87 镜像；04 最终门禁与基准 exit 仍另行收口。

## 94. d426 F1 最小修订短审：外层清理已接入，真实 timeout 的组边界尚须修正

只读审核 **`d42646b7a1f11da3f521a5e2d31466bb5a55757a`** 的 project-scoped guarded launcher、runbook 和两项 serial fixture。产品、共享 sampler/timer 没有改动；本轮无节点访问、测试或运行。工作 INT 改置 sampler 的 journey 子命令，外层独立 sampler watchdog，再由 launcher EXIT trap 做固定 project 的 Compose down（无 -v）、postflight 与条件解锁，符合 §93 最小修订方向。配置等待上限为 `26420+5+185+63=26673s < 27000s`；这是等待预算核对，不是实际耗时或所有命令的独立 wall-time 证明，初始化及正常收尾仍须纳总限。

**F1 尚有同一信号路径缺口：** 真实 GNU timeout 默认创建自己的 process group，内层 `timeout --signal=INT --kill-after=1200s 25200s` 因而可能与 WATCHDOG_SESSION_PID 的外层组分离。手动 INT/TERM 的 stop_watchdog 只 kill 外组；sampler 收 TERM 默认退出，不能据此保证另一个组内的 journey/timeout 被停止。postflight 亦只查外组是否存在，故可在内层仍存活时把外组 quiet 当作充分依据。已有 fixture 的 fake timeout 使用 start_new_session 加主动 signal forward，不能替代真实 GNU nested timeout 的组语义；没有运行这些 fixture，也不宣称已经复现残留。

已直接交实施者继续同一最小修订：内层采用 **`--foreground` 留在已经隔离的外层组**，或同等的自有组停止方式，保持软截止只向旅程发送 INT、手动信号能停全部自有宿主进程，之后仍走 project-only Compose 收束。复用现有停止 fixture，以真实 GNU timeout 和 fake journey/Docker 触发短 deadline/手动中断；仅在 fixture 缩短等待，不能用主动 exit124 代替真实超时，也不新增真实 Compose/prepare 或测试矩阵。保留原 25200/27000 和清理预留，不新造 guardian/IPC/持久机制。

**这是 F1 的接线修正，不是新的范围、Owner 或最终摘要审批。** 实施者直接完成修订、必要 focused/语法/静态及已授权节点准备，交原始结果短复核；§92 的恢复范围与直接接续流程保持，不因本节重开来源或历史矩阵。当前没有把未产生的测试/静态结果认定通过。

## 95. 源 checkpoint 导出缓存全过期：mode=none 下不阻塞 A 接续，不改 TTL 或预热

**原来源的 523 个 snapshot_table_export_cache 项已过期，不阻塞 §92 固定 `history_cache_mode=none` 的输入恢复。** 这不是缓存健康证明或新的来源例外，只是按已有 Contract/产品读取语义解释前提；不能把“核实 TTL”扩大为 none 模式必须全部未过期。其他 source/checkpoint 摘要、输入/规则、目标镜像和必要守护仍须满足；F1 launcher 修订另行闭环，本节不代表其已经通过。

BatchMode echo OK 后，仅只读 CT108 已关闭 `/home/dev/gdds-p6-logs/baseline/preflight/p6w4resume970420261107a-ct108/checkpoint-cache-ttl.log`，SHA256 **`4dac4836be733644015828ea7b723aa57bde5073ff8d9251ef2edb403e361322`**。记录 hostname=gw-dms-test、07:58:32–33Z、state SHA=`f86e5bf4fda11ee37b17a4b08319955fe9df7c7a14b7c398c5480ded79bdf9e0`、**523/523 expired、missing_artifact_files=0、剩余 TTL -46344.753 至 -45568.762s**。日志中的 worktree_head=20cf 是该只读检查的工作目录记录，不把它冒称 source e798 或 target 9704 的执行身份，也不据此重新比较不同对象的 HEAD。本审核未查询源 DB、修改卷、启动 Compose/业务或追加扫描；完整 source 实物绑定仍由既定 preflight 承担。

冻结 9704 的 `SQLiteSnapshotTableExportCache.lookup_many` 先有界 prune，且对 expires_at_us<=now 的项删除缓存索引/保护并跳过；`snapshot_materialization/repository_ref.py:271–320` 在未获得有效缓存项时从规范表读取/物化。冻结 [Snapshot Table Access](../../../contracts/snapshot-table-access.md) 的 S1b IO cache 规则及 Comparison Bundle 规定该 Parquet 缓存可重建，miss/损坏回规范表读取与导出，缓存不是权威 checkpoint 内容。`real_dump_journey._change_history_cache_condition` 仅对 healthy/refill 等特定场景要求健康 TTL；本轮 mode=none 不调用该准备路径，没有这一零过期门槛。

实施者保持原源卷、时间/TTL/缓存内容不动，不预热、不延长到期时间、不清缓存、不改成 healthy。仅在新的目标副本中由正常产品 lookup/miss/回填运行，记录起始 expired 事实和 Submit 后/History 时实际可观测状态；过期起点不能写成 TTL 内健康命中表现，也不能据此改名为 H3 或人为构造的 H2 cold 场景。普通相邻 History 的实际结果按方案 A 如实报告缓存条件，不预判命中或性能。

**非阻塞解释已直接交实施者并同步设计，无需新 Owner/最终摘要 GO，也不为取得 ttl_valid=true 重跑或生成输入。** 恢复仍沿 §92，其余实际前提及 F1 修订不被本节跳过。

## 96. 5de F1 修订与实际验证通过：无剩余工具阻塞，按 §92 直接接续

**最终工具候选 `5de35b60afd45a1007fc236e79574cc8fde049f3` 的 F1 短复审 PASS，§93–94 的超时/信号收束 Finding 关闭，必要静态证据已补齐，无剩余接续工具阻塞。** CT108 实际 source/input/目标镜像/节点等前提满足后，实施者按 §92 已批准范围直接执行首轮，事后交结果；不等待本报告之外的新 Owner/设计/协调回执或最终 manifest GO。§95 的 mode=none 缓存过期非阻塞解释保持，不改源 TTL/内容或预热。本结论不是实际 CT108 前提已通过、旅程成功、04 权威 runner 或基准 exit。

### 最终实现与预算

已只读 d426→2cda→da6→5de 完整差异。内层真实 GNU timeout 增加 **--foreground**，工作截止只向旅程发送 INT；外层仍由 setsid 隔离。stop_watchdog 的 TERM/KILL 和 postflight 静止判定覆盖该自有 **session**，不再只看可能漏掉内层组的 PG。之后始终进入固定 project 的无 -v Compose down、postflight、条件解锁；未知残留或检查失败保锁并 exit125。使用标准 setsid/timeout/pgrep/pkill，没有新 guardian/IPC/持久状态机；产品与共享 sampler/step timer 均未改。

原 work25200、内层 grace1200、外层 watchdog26420+5、项目 down180+5、postflight60+3 的配置口径保持，等待上限 `26673s < 27000s`，不扩大已批总限、不把它当实际耗时。内层前景模式本身不向全部后代逐个计时，剩余自有 session 仍由外层停止/postflight 覆盖；不能再把宿主子进程返回单独当成 Compose 停止证明。

最终候选 vnext tree=`40e9d75502ee25d8a2797e1f02203336b252c85f`；相对 9704，benchmarks/tests 之外 vnext 差异为空，diff whitespace 检查通过。da6 仅将真实 timeout 的 KILL 结果预期改为137；5de 仅在已有测试 helper 返回处补 cast，未改变生产/恢复工具。现有 product tree、固定 identity JSON、源→目标及 §87 三镜像绑定不变，不因宿主 launcher 修订无故重建产品镜像或另跑 Compose/prepare。

### CT05 原始结果

BatchMode echo OK 后只读 `/home/dev/gdds-p6-logs/baseline/ct05-vref-5de35b60-validation.log`：**gw-dms-test-05，2026-11-07 08:11:36–49Z，起止 clean 最终 HEAD，validation_exit_code=0**。SHA256 **`1fcd8e9b1cbfd6ecb577788489c1840a46da888979938b58c5c53ceedf6c836b`**。bash -n exit0；真实 GNU timeout launcher focused **2 passed / 3.70s**；shared_kernel、repository_contracts、repository_client、backend、repository_service 五包 Ruff/mypy 十项均 exit0，backend mypy 覆盖500 source files，RS覆盖201。

两项 serial fixture 使用真实 GNU timeout，仅在测试副本缩短等待；fake journey/Docker 不启动真实 Compose。实际覆盖软 INT 后继续至 KILL/137、内层信号不先打断 sampler、自有 session 的中断停止及无残留、project-only down 不删卷、未知容器残留时保锁。它们证明本次 launcher 接线，不冒称真实 Docker stop 已在该 focused 中执行。原五项 source/image/参数 focused 仍引用 §93 的 ad06 来源，不写成七项都在最终 HEAD 重新运行。

08:12:13Z 的 `/home/dev/gdds-p6-logs/baseline/ct05-vref-5de35b60-postflight.log` SHA256 **`dcbee0f83a8d93b89b9826f0260771e735cc324b1cb70aeff382861775057274`**，记录最终 HEAD clean、无容器/8000/Dolt/pytest/Cargo、自有占用释放、postflight exit0；这是读取既有 postflight，不是审核者新做的节点检查。本轮没有测试、导入候选、访问源 DB/卷、启动 Compose/业务或测量。

首次 da6 验证 08:08:23–46Z 的原日志继续保留，SHA256 **`2b8bf224129386c663457c46e9ea113ee4977edefdfff94b3faa937d57941855`**：launcher 两项和先行静态通过，backend mypy 报测试 helper no-any-return，整次 exit1；不能写成首次十项全过。5de 的 cast 修正和最终完整重验关闭此项，原失败没有替换为通过，不增加业务失败计数或 Owner 审批。

**修订及验证结论直接交实施者并同步设计，当前无需继续等待工具审核回执。** 保留所有旧失败、源/诊断卷与证据；只按 §92 做 A 分版本接续，不把旧记录改成统一版本、不借本报告办理最终 runner/exit。实际前提或运行失败仍按原停止/保卷/DC80 规则处理。

## 97. 原 control 快照新增 SQLite sidecar：停止正确，允许留证后可逆恢复原已记录形状

**当前 source 目录完整摘要确实 MISMATCH，不能直接续跑或把它标成 MATCH。** 本轮独立证据同时证明原 `control.sqlite3` 的内容及摘要覆盖的元数据仍精确匹配原 checkpoint；没有主 DB 数据丢失证据。按 DC80 对已定位工具操作错误的最小修正，允许以下一次、可逆的原形状恢复：完整保留事故副本，只把两个已确认新增的临时 sidecar 原样移出 control 快照，再由**未修改的完整摘要守卫**核验。此处不改 source 内容资格、expected digest 或产品，不需要重跑旧业务/生成输入，也不新增 Owner/最终 manifest GO。

### 独立只读事实

BatchMode echo OK 后，只读 CT108 原失败核验、incident 与 postflight：SHA256 分别为 **`9a1f34c6445e33ced78fb5bdd50c585d24ef97af779c728281d8a0362def14e2`**、**`e412a2f67006a8c263b9551af0fd7718b2104d1bc12b0cadfd006a4f885f37a0`**、**`931de8672208252d589f8f91f1b373b4bdaf375bea702f442e7eb1e75cb58538`**，均与实施者一致。08:34:49Z 守卫拒绝 control 快照：原 1 文件/3608576 bytes、tree=`623ec7034f89244a7718068a6aacf47955d07bed964a92689ab6edf8ee2a06cd`；当前 3 文件/3641344 bytes、tree=`d3002e4003fad81f33580bb80c60fbfbf0c288f8eb3da8a02ca4aa5eaa7926d7`。新增只有：

- `control.sqlite3-shm`，32768 bytes，SHA256 **`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`**。
- `control.sqlite3-wal`，0 bytes，SHA256 **`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`**。

sidecar 的 mtime 与 07:58:32Z TTL SQL 查询时间一致，支持该检查产生 sidecar 的解释，但不称已唯一证明创建者。`mode=ro` 的 SQLite 连接并不保证不创建 WAL/SHM，§95 的缓存语义结论不等于那条检查对文件系统绝无写入；原“只读检查”操作描述必须保留此次纠正。

本审核没有再用 SQLite 打开快照。只用 raw 文件读取和 lstat，按原 `_volume_tree_digest` 的文件名/类型/mode/uid/gid/mtime_ns/size/字节算法计算**原单文件集合的投影**，结果精确等于原完整 control tree **`sha256:623ec7034f89244a7718068a6aacf47955d07bed964a92689ab6edf8ee2a06cd`**。主 DB 为3608576 bytes，raw SHA256 **`8f0fa78c110dce23c4e6537c22ae623fe320545cf86c5929fb18d39cd1e8678b`**，mode0644、uid/gid0、mtime_ns=1793907257820020960；读取前后这些元数据及 inode 稳定。该投影只证明原文件未变，**不是当前三文件目录 MATCH**。审计输出副本 `/home/dev/gdds-p6-logs/worker-gc-scheduling-repair-review-20261107/source-control-single-file-readonly-proof.json` SHA256 **`c86c54080f8f0fb311ec8863948513a95556fcc4611b4d8d4c13e945ac1f2dfd`**。

失败日志中 artifacts 快照仍按原完整算法 MATCH；run/state/log 三份 SHA 与固定来源一致。失败发生在 sampler/Compose/目标卷复制/POST 之前，target run 目录及目标卷均不存在。08:38:46Z postflight 记录 clean、无容器/8000/Dolt/pytest/Cargo，自有锁已释放。未消费本次实际业务尝试，不因这个准备事故重复计时或改动镜像。

### 唯一允许的恢复动作与边界

1. 实施者现场核空闲并原子取得自身 CT108 占用，停止本会话所有对该源快照的 SQLite 检查；恢复期间不启动业务。再次确认当前 control 目录仅上述三个普通文件、主 DB 单文件投影仍等原623ec、WAL仍为空、SHM仍为上述固定摘要。条件变化则停止，不把本许可泛化。
2. 在**所有原 source evidence/checkpoint/卷根之外**的新事故证据目录，按原权限/uid/gid/mtime完整保存当前三文件 control 目录副本、失败日志和上述摘要；副本完整 tree 应等当前 d3002e。保留这份事故原状，不覆盖旧证据。
3. 只把上述两个新增 `control.sqlite3-shm`、`control.sqlite3-wal` **原样移至该事故证据目录**，不删除、不覆盖、不开 DB，不触碰 `control.sqlite3` 或原 run/state/log/checkpoint JSON，不改任何 expected digest。该操作是移走原 checkpoint 未记录的临时文件并保留全部事故事实，不是授权清理其他源数据或改写业务状态。
4. 用未改的 `_volume_tree_digest` 完整重核本 control 树，必须重新为1文件/3608576 bytes/原623ec。其余两卷不因本事故额外重扫或改写；正常 preflight/复制阶段原有校验不取消，原 run/state/log SHA 和输入绑定保持。单独报告“事故前已记录值、污染后 MISMATCH、留证可逆恢复后实测值”，不得改旧失败日志或声称源一直未变。任何失败保留现场，不再移动其他文件，不改摘要来放行。
5. 上述完整核验及 §92 其他实际前提通过后，按原授权直接首轮，无第二次 source/manifest GO。只读原文件与可逆恢复不改变代码，**不要求再跑 focused、静态、runner 或真实数据**；保留本次恢复操作、结果和 SHA 即可。今后需要 SQL 查看 checkpoint 时，只查询单独的临时工作副本；原源只作普通文件摘要读取，不再次以 SQLite 打开它。

**原源尚未恢复，本审核未移动/删除/修改任何源文件。** 本处置只覆盖这个已精确证明的主 DB 未变、WAL为空且新增 sidecar 已识别的事故，不提供通用 WAL 忽略、过滤文件计算 MATCH 或新来源映射。§95 的过期缓存正常 miss 解释和 §96 的 F1/工具 PASS 保持；实际恢复和正常前提通过前继续不启动业务。具体步骤直接交实施者并同步设计，不把可逆临时文件修正升级成新的业务/冻结口径取舍。

## 98. 恢复记录复核通过；日志自引用摘要与文件名错误可直接修正接续

**§97 的限定恢复留证通过本次结果复核。当前两次启动前核对失败已定位为命名和日志封口错误，不是 source 再次变化；可以修订记录后从只读启动核对开头继续，正常实际守卫通过即按 §92 执行唯一接续，不等新 Owner/最终摘要 GO。** 不重复恢复源、SQL 检查、输入生成或已过测试，也不把两次失败追改为 PASS。

BatchMode echo OK 后，只读 CT108 既有封口日志与 abort/postflight，没有扫描源卷、打开 DB、移动文件、测试或启动业务。`source-control-incident-20261107T084925Z/recovery.log` 记录在自有占用/无打开源 DB fd 的状态下，完整三文件副本及元数据复制后 tree 精确=d3002e，保留四份原日志；随后只移出已识别 SHM/空 WAL，主文件不动。正常原算法结果为 **1文件/3608576 bytes/原623ec**，run/state/log SHA一致，08:52:11Z恢复结束。这与审核已核原单文件投影及 §97 边界吻合，不声称原源从未受污染。

**日志封口的字节级关系已独立证明：** 当前 recovery.log 为 **4854 bytes**、SHA256 **`8887a76025e09974ee6d8e6fcddf12beaff1d3ce36c31f5f081c41bf58d7729b`**，读取前后稳定。仅排除最后一行“40642e40… + 两空格 + 本 recovery.log 绝对路径 + 换行”的完整前缀，其 SHA256 精确为 **`40642e40ca75201b9f730d6230625289b572e1e2d414fe4c29a11e13bf1b5918`**。旧摘要是在追加自身 sha256sum 输出前计算的正文前缀摘要，不能继续作为当前整文件摘要；这不说明恢复正文被改写。保留现文件及尾行原样，不删行、不再追加；最终整文件摘要写到独立的 sha256/索引文件，旧4064明确标为追加前正文摘要。恢复日志属于操作证据索引，不重开已核源内容资格的审批门槛。

08:57:06Z 首次核对把 source run 文件猜作 root/run.log，日志 SHA **`7a56f87a976127fdd75d861864b387d17a73efa6e0d9c7b012a58ef01aa88385`**、incident SHA **`d80f1069ba6241750f402bfba6600d7a889da348ca1c427fd8d80af4db6a0576`**。实际固定对象分别为 **source/evidence/run.json、source/evidence/state.json、source/launch.log**。09:00:24Z 更正后核对已走过 source 三份摘要和原 DB raw SHA匹配，只因用旧4064检查现8887而退出；日志 SHA **`9e61db589c86daa0e240423e1b8e324ef12862944463631b223e9046925a9244`**。路径与完整封口摘要按上述事实修正，不猜另一个 run 文件，不调整权威 source 的 expected SHA。

09:02:12Z abort SHA **`758ff39a691df95f1826b4ba3978c4464b8d10b114453a4d2e2067eb3497d970`**，postflight SHA **`8bcebb8b602de3bf45c27d814161abd8ea66569a98d4145d5f2678948155feb8`** 均独立匹配。记录 run_started=false、target run目录/容器/卷不存在、无 Dolt/pytest/Cargo/launcher/8000冲突、source DB和run/state/launch未变、自有锁安全释放。没有 sampler、Compose、Submit 或测量开始，没有消耗原授权的一次业务运行。

本次接续适用 Owner **c58f227875** 的“测试环境执行授权”，`p6-worker-gc-scheduling-repair-plan.md:13` 已明确：**“低风险准备命令失败先停止原样试错、留日志、查明原因后最小修正；恢复不因累计失败次数再等 Owner。”** 方案 A 当前执行条文继承这一普通接线/文书直接闭环流程。因此停止错误命令、保存两次非零记录是正确的，但不能仅凭“重做又失败”的次数增加 Owner 等待；本次恢复依据是已经查明并验证的具体修正，而不是忽略错误。实际产品、输入/镜像身份例外、必要守护或资源/范围变化仍按原边界处理，权威 runner 失败规则也未放宽。

**具体指示已直接交实施者并同步设计：冻结当前封口文件，分开保存最终 SHA，使用三个固定权威路径，现场重新核空闲/取自有锁，从正常启动前核对开头继续。** source/checkpoint/input/目标三镜像/占用等实际守卫全部通过后直接运行，不再新增日志摘要审批层、重复 source 恢复或等待本会话另一份回执；结果事后独审。其余 §92/95/96 边界保持。

## 99. 09:08 guarded 入口拒绝：真实 sampler 命令契约漏检，最小修正后改用唯一新身份

**5de 的 guarded 入口在真实 sampler 前置校验退出，没有启动 journey、Submit 或资源采样，不能作为正式测量或已消费的业务 continuation。** 当前入口需修正这一具体工具接线问题后再执行；保留失败 project **`p6w4resume970420261107a`** 及所有证据，不复用其目录。新唯一执行 project 固定为 **`p6w4resume970420261107b`**，仍属 Owner 方案 A；产品9704、源 checkpoint、三镜像内容、输入/cache、预算及一次业务运行范围不变。不是增加第二次实际 Submit，不重做来源恢复/SQL/输入生成或已通过业务。

### 实际失败与审核纠正

BatchMode echo OK 后，只读 CT108 已关闭三日志，SHA256 精确匹配：最终 preflight **`7ab83c2f75b8dd24365e383afc7f28096b27c0fba68ff1bacc85d0982f54588c`**、controller **`d6379b746b32cdf0298fdff0d3e447cac0d88e209100f11022cf89f9e34e907a`**、postflight **`3a90caaf20751d986a8fc8e57a35ec4d999b52cab1364fb2ac837747c080e601`**。记录 clean5de，09:08:13–15Z，reason=`formal journey must use this worktree's backend .venv Python`、launcher exit125，project down/postflight/cleanup exit0、锁释放。final preflight 的 source/run/state/log、恢复、输入、native身份与预置镜像均已到 MATCH；这不消除随后实际入口的拒绝。

真实 `p6_baseline_resources._launch_metadata`（原315行附近）直接把 `command[0]` 当作解释器；launcher 在 sampler 的子命令前加了 `timeout --foreground --signal=INT --kill-after=1200s 25200s`，所以 command[0]=timeout。该校验在 started_utc/采样循环/Popen 之前抛错，吻合只有 postflight 留下的事实。controller 后续的“watchdog PID is not the isolated session process group”处于快速退出后的身份检查，是同一入口失败后的派生信息，不另计一次产品/租约失败；原主要 reason 已保存。

**上一轮审核漏检了真实 sampler 的消费者约束。** §96 两项真实 GNU timeout fixture 验证了信号/清理，但使用 fake sampler，未证明实际 producer argv 能被真实 `_launch_metadata` 接受；不能把那两项 PASS 扩写为该集成契约已经覆盖。F1 信号修订和静态通过事实保持，先前“无剩余工具阻塞”结论现按这一新实证接线问题收窄。为本次实际代码审创建了 clean detached `/home/dev/gdds-p6-vref-review-5de35b60` 并链接 legacy；本审核未运行测试、启动业务或改实施 worktree。

### 准许的最小契约修正与验证

1. **只修 sampler 的前置命令识别边界。** 识别 committed launcher 的固定 GNU timeout argv 前缀（固定工具路径/foreground/signal/grace/work值，优先固定绝对GNU路径），再对后面的真实命令执行原解释器、manifest/root/census/evidence 校验。真实 Python 仍须为当前 worktree 的字面 `.venv/bin/python`；空子命令、其他解释器、shell/env/任意 wrapper 或不匹配前缀仍拒绝。不能改成在任意 argv 中搜索 Python，也不能关闭原检查。
2. 保持原直接 Python 命令的行为，记录实际完整 command 和真正 python_interpreter，不把 timeout 冒称解释器。改动限定于采样起点之前的启动校验；**采样循环/频率、资源统计、operation timer、计时边界和产物口径不变**。这不是修改已成功历史计时的路径，不要求因共享文件中一处前置 validator 修改而重测历史场景；若实现另触及时段/采样语义，再按实际影响处理。
3. 在现有 sampler 命令校验用例中覆盖固定 wrapped 命令接受、原直接命令保持及错误解释器/不受支持 wrapper 拒绝；增加或复用一个**实际 launcher argv→真实 `_launch_metadata`** 的契约核验，不能继续只由 fake sampler 接受任意数组。复用已通过的小 GNU timeout/清理 fixture及必要五包静态，不加真实 Docker/Compose、prepare、全量 runner 或新矩阵。用例属于命令入口行为，不按本轮 Finding 编号命名。
4. 同步更新新 project 的固定 identity JSON/其代码摘要、target evidence/log/key、launcher固定project及runbook/相应用例；原源仍是 `p6bw4s4h120261105b:v2-preview`，不得误改 source b 或旧 A 事故记录。预置镜像内容不变，为新 project 增加已核内容的别名而不覆盖旧tag/重建；在 CT108 对实际新tag照常核 config/全部有序DiffID/labels。

本审核另只读检查了新 project 的目录/容器/卷/网络，结果均不存在，Docker查询均exit0。它只是本轮现场事实，不是预约；实际执行前仍现场核空闲/原子取自有占用及全部既定条件。旧 A 的 postflight、source事故/恢复和其image别名保留，不清理或改写。

**上述具体修正、必要 focused/静态与新身份准备已在原工具修复范围内明确允许。** 合格后按 §92 正常前提核验直接执行新身份的唯一业务接续，交代码/原始结果供短复核，不再追加 Owner、最终 manifest 或身份文件摘要 GO。此前 source恢复和 F1 不因本命令校验错误重开；本次失败及125记录保留。该决定直接送现有实施者与设计者，不新增会话/角色，不扩基准 exit。

## 100. 3fd 真实 sampler 契约修复与证据复核 PASS：新身份 b 可按原授权接续

**候选 `3fd64dc2fe9a9c11ceebf8cd458983b9507f5364` 的 §99 接线修正代码及必要验证 PASS，无剩余工具阻塞。** 新唯一 project 为 **`p6w4resume970420261107b`**；实际 CT108 新身份/镜像别名/环境与原核心前提满足后，按 §92/99 直接执行一次业务 continuation，结果事后独审，不再等待 Owner/设计/审核回执或最终 manifest GO。旧 a 入口失败、日志/目录/别名保留，本节不把它追改为成功，也不是 CT108 新运行已经开始或已通过。

### 实际最小差异

在 detached 审核 worktree 中读 immutable3fd Git 对象及完整差异、只读解析 Python AST，diff whitespace 通过。sampler 仅在 `_launch_metadata` 的解释器识别前增加固定五项 timeout 前缀识别，匹配才剥离；仍按原字面 worktree .venv Python、环境 root、manifest、census、evidence 校验。未改成任意 argv 搜索，未知 wrapper 仍落回原拒绝路径。**采样循环/period、资源计数、Popen/计时起点、step timer 与结果口径均未改变**；前置识别在原计时起点之前，直接 Python 路径保持原行为，无需重测历史成功计时。

独立提取当前 committed launcher 的真实前缀，与 validator 的 AST tuple 逐项精确相等：`timeout --foreground --signal=INT --kill-after=1200s 25200s`。现有 sampler integration 用例已删除对 `_launch_metadata` 的替身，wrapped argv 实际经过真实 `run_sampled→_launch_metadata` 后才进入模拟子进程/资源 I/O；另有直接/固定前缀正例、其他解释器及不支持前缀负例。结合上述 producer 前缀核对，覆盖了本次现场拒绝点，不再只凭 fake sampler 接受数组认定契约通过。原真实 GNU 短超时/手动中断/清理 fixture继续保留。

新 identity JSON SHA256 **`98bfba51108ace6a5bf011247752ff11c41e6a4fcc9a0a96a487a66e986b938f`**，代码pin及runbook一致；相对旧身份，source、inputs、identity_evidence、三镜像内容和预算逐项不变，只改目标 project/evidence/log 绑定，launcher及fixture项目一致。源仍为原 b/v2-submit前checkpoint，产品仍9704，配置/格式/依赖不变；候选 vnext tree=`3eb04338477b7d37d2d5c6ac83ff2727b814d88f`，新增差异仅已核工具/测试/identity文书。不重做源修复/SQL/生成，也不无故重建旧镜像。

### CT05 实际验证与范围

BatchMode echo OK 后，仅只读已关闭 `/home/dev/gdds-p6-logs/baseline/ct05-vref-3fd64dc2-validation-corrected.log`，**09:29:58–09:30:03Z、gw-dms-test-05、end_head=完整3fd、validation_exit=0**，SHA256 **`56e8e31ce862fce791d2c14fd31a701ec2abb3616e4f01bb51afe778fa9eee18`**。bash语法、sampler/guarded launcher focused **14 passed / 3.64s**、backend Ruff及mypy（500 source files）均通过。前一09:29:32的 checkout记录也明确切到3fd，但日志未写执行结束，SHA `0257d65144c43f2ed919aecd9e0c5192d5b51cbf7354eb2e6b3d8b6ef177f8fb`；不把该运输/切换记录本身当成功验证。最终日志没有重复打印起始HEAD/clean，按checkout记录和end_head准确关联，不补造原日志字段。

其余四包源码/依赖未变，静态状态关联 §96 最终5de的实际合格来源；不是权威 runner carried，也不声称十项静态都在3fd重新运行。09:30:15Z 的简略 postflight SHA256 **`c7feda0fe95ca72b73995aca825090269a3c339b005be41ed83795e410ad4aa9`** 匹配，仅记录 hostname/锁释放/时间，不扩称它独立证明整机全部资源 quiet。此前两项launcher fixture对自有测试session/保锁的结果有效；CT108 正常现场守卫仍必须执行，未因简略文书新增测试或业务重跑。

本轮没有导入/执行候选、运行测试、Compose、复制源卷或启动业务；只读代码/Git对象与CT05原日志。**结论直接交实施者并同步设计，当前修正已合格，不再为本 identity SHA 另开 GO。** 新身份现场核验与原预算/停止/保卷条件保持；统一版本矩阵、04收口、主线合入/push/tag/基准exit均不由本节代办。

## 101. 107b 实际有限接续结果独立审核 PASS

**CT108 project `p6w4resume970420261107b` 的本次有限接续结果 PASS，无新增阻断 Finding。** 真实 sampler 接受了 §100 修正后的入口，新的 v2-submit、v2-repository-read、v2-approve、history 四步均成功；先前入口拒绝和本路径 prepare 无法完成的阻塞已解除。本结论接受 Owner A 下该次分版本参考结果，不将旧步骤改记为当前产品，不承担完整基准矩阵或阶段 exit 审核。

### 版本、来源及证据

实际运行 HEAD 为 **`3fd64dc2fe9a9c11ceebf8cd458983b9507f5364`**，产品仍为 **`9704d0b286049073529d60036dbd999032f97e0a`** / `vnext` tree **`f5757bcb56e3e8ee8cde5fba6f903717d91412a2`**；工具候选 tree 为 `3eb04338477b7d37d2d5c6ac83ff2727b814d88f`。handoff 提交 **`945d9141c45ceeee5d3bcb561c50278c6e4f97a0`** 相对运行 HEAD 只有 handoff 文档增加11行，未改变被测代码。审核开始时主 checkout HEAD 为 `c1d1beefb1260f21810a6809cc9f8ffb4b6bf78d`，并非本次产品/运行对象。

读取已关闭的原证据，并将六份运行文件经 LAN 复制到审核者目录 `/home/dev/gdds-p6-logs/p6-w4-continuation-review-20261107/p6w4resume970420261107b/`；逐份重算摘要均与原记录一致：

| 文件 | SHA256 |
| --- | --- |
| launch.log | `63d2da3b33a8742e681b992227c46c8746c69cfb224de5dbdc240599375b722f` |
| evidence/run.json | `2f2197d65fd192b5b96a690286af2668901fe72145cca6fe7702cf7c93f37f07` |
| evidence/state.json | `0281f0e07b124c24ad7f24d66cbefadb511ba9db99cb92e8b66e65ec495fc897` |
| resources.json | `fed0d959c3d26c1c0a78f0c1320c6224c9767a7ce8d996c60e5a00f0e502a94b` |
| resources.input-provenance.json | `9ae4639544c9110f1a2c5464b8138b31964959bfb8e9447a06f9c6a3f6990c26` |
| postflight.log | `acdea2a40311572ee730d76426fbf6d52a5d43099771bbc55145623b41f13e2f` |

run/state 的 step_checks、post_gc_resume 和 compose_image_metadata 逐项相同。18项检查均 PASS，其中13项保留 `20cf0ec87e7e0c068aaa61c33ad49014cae36f52`、v2-preview 保留 `e798ec87a37330250b0c051162e7962dba1daa60`，只有上述四项新步骤绑定3fd及当前日志。日志也实际记录14项 step_reused、四项新的开始/成功，无新 v2-archive/v3；冻结配置 `full_v2=false`、`three_node_history=false`、`cross_project=false` 与 §92/计划一致。

新 identity JSON 原始字节 SHA256 为 **`98bfba51108ace6a5bf011247752ff11c41e6a4fcc9a0a96a487a66e986b938f`**，与 run 绑定一致。源仍为原 b、completed_through=v2-preview、resume=v2-submit，源 run/state/log 摘要保留原值；源 RS 完整身份继续明确 **UNAVAILABLE / source checkpoint input only; never MATCH or carried**。三项上传输入的 role/bytes/SHA 与 expected manifest 全部匹配，provenance 的 state_sha256 精确等于本次 state 文件，issues 为空、result=MATCH；不冒称这些旧上传在新版本重新执行。

将实际 compose metadata 与 committed identity 逐字段比较，三个服务 config digest、全部有序 RootFS DiffID、要求的 labels 均匹配；run 的 target identity 与其 compose 共同字段也一致。backend/worker 为 `66e362d4…648e62`、各15层，RS为 `b81faa1f…419aa`、28层，build-input/source-tree/revision 保留 §87 已核值。宿主入口修订及本次文档不触及产品镜像边界，**不触发重建**；实际业务使用原已核9704产品镜像的新107b别名，不把宿主3fd写成镜像 revision，也不比较跨节点 inspect ID。

### 实际完成与性能口径

两个 operation 的 terminal 均为 SUCCEEDED、diagnostic_code=null。Submit 已生成 submission/Repository commit；History 的一对 before/current commit 分别精确对应 v1/v2 Submit，record_count=70634，bundle/fingerprint 已保存。Repository read 记录631张表、682805行，其中 ordered 144张表/133548行；approve=true。既有旅程的 HTTP/结果核对通过，本审核没有重新下载或重跑业务。

| 新步骤 | step wall 秒 | API 用户可见秒 | 进一步定位 |
| --- | ---: | ---: | --- |
| v2-submit | 4030.503 | 4027.732 | prepare_import 3800.712802；submit_import 0.287299；await_import_result 225.216005 |
| v2-repository-read | 96.689 | 未单列 | 当前版本实际读取 |
| v2-approve | 0.622 | 未单列 | 当前版本实际审核 |
| history | 2354.226 | 2352.010 | materialize_inputs 1496.565867；assemble_comparison 848.163671；publish_result 0.031273 |

Submit completion=4027.743s，用户可见以 terminal 观察为准；prepare 占其约94%，是本次主要耗时。Repository import 最终 SUCCEEDED，await仅1个session、3次healthy handoff，未耗尽R5预算；prepare及History各worker阶段 attempt_count均为1。History的物化和装配均有实际 step 起止，不把等待/检查点复制时间拼入API计时，也不从这些粗段推算 checkpoint-read、bundle或JCS等未单列子段。当前完成证明修复在该路径有效，**不把先前 GC/心跳关联追认成已唯一证明所有历史失败原因**。

sampler 起止为 **2026-11-07 09:34:35.316–11:24:15.385Z**、elapsed **6579.985s**；journey 自身 run_result elapsed=6522.846s，二者边界不同，不互换。实际耗时低于 work25200/hard27000预算，没有通过扩大预算填PASS。history_cache_mode=none；保留523/523缓存项已过期、artifact完整的观察，**不把本结果记作healthy-cache、TTL内命中、refill或H3**。

资源摘要为2s配置周期、3003次采样；并发 memory.current 采样和的峰值 **24500322304 bytes（约22.82GiB）**，各容器 memory.peak 之和 **25545502720 bytes（约23.79GiB）**，后者是保守上界，不能作为同时峰值或单worker RSS。peak_parallel_cores=2.931，temporary_disk_high_water=4866588672 bytes。0.622s approve 未落入采样点，samples=0、memory=null，不能补成零内存/CPU。没有原始逐点序列，不从样本数虚构最大采样间隔；CT05诊断RSS/分段也不拼进本次CT108正式记录。

### 收尾与结论边界

BatchMode echo OK 后只读既有 CT108 `preflight/p6w4resume970420261107b-ct108/start-preflight.log` 与 `controller.log`，SHA256分别为 **`42694cb26140e8de709cb0b5209f1369f699ff61ae611dce5e4ec981d7b21e3c`**、**`1ca003e046e28c57af8a7597ebcead97da8ca7f503e832c30d18c5495b52cd61`**。前者记录源/输入/同节点别名/单飞核对匹配；后者记录09:34:35–11:24:15Z、起止完整3fd、launcher_exit_code=0、tee_exit_code=0。run、resources 均 exit0，HEAD stable；postflight记录 project Compose down、node postflight、cleanup均exit0、自有锁释放。按已审postflight实现，这是既有节点检查成功记录，本审核没有额外现场扫描或宣称独立证明未检查的网络项目。

本次三卷名称正确且 retained_volume_listing_error=null；checkpoint键为 v2-repository-read、v2-approve、history。按原规则保留107b、源、107a失败、source事故及恢复证据；没有删除卷/worktree/镜像或修改源DB。**本审核未运行测试、Compose、sampler或新业务，仅只读代码、既有日志和证据副本。** 结果直接同步现有实施者和设计者；无需再为本次结果等GO或重复该业务。A既定剩余未测范围、正式record/comparator与04权威门禁按原分工继续，不由本有限PASS代替，未宣称完整单版本P6或阶段退出，也未推送、合入、打tag。

## 102. W4-FULL fresh 配置、预算接线及定向验证 PASS，继续实际测量

**W4-FULL 的最小工具修订和准备关键差异审核 PASS，无待确认的新语义或身份例外。** 实施者按原授权完成实际节点/输入/镜像/占用预检后直接执行 `p6w4full20261107a`，不等新 Owner、设计、审核回执或逐摘要GO；实际结果仍须独审。107b 已闭合，不重跑。Owner持续推进A剩余真实缺项的安排保持，不能把本节工具PASS当成全部测量结束；最终基准exit权限不扩。

### 实际差异及范围

代码候选 **`236b5b325e15ee63393e734db94c26577c9696cf`**；实际运行文书候选 **`18a4851d8c52d53afdb95ee4df9fae04e6e36d77`**。本轮在原detached审核worktree读取immutable Git对象和完整diff，未执行候选。236b相对9704的 `vnext` 差异仅位于 backend benchmarks/tests；18a相对236b只明确runbook的两节点checkpoint列表，diff whitespace检查均通过。候选 `vnext` tree分别为 `4a7f1d55bbbf9c519880ab77e040fd2c19a9181f`、`a6a44fd41b02965ba35e04654e41b74327fde97e`；产品仍为9704及其原tree，不混入main/S2b。本轮报告写入前主checkout HEAD为 `b1a43480d426e4e8959fb7cfab5bb2ffeb935227`，不是该参考运行对象。

启动前独立发现并已关闭的具体预算缺口：fresh路径的旧t4 v2-submit预算仍为 `ceil(810.961×5)=4055s`，107b较轻路径实际已4027.732s；专用post-GC恢复的10800s并不会自动用于fresh FULL。现在 `_w4_full_budget_enabled` 只在t4、固定accepted W4 root、scope=full、synthetic、full-v2、cold Preview、healthy History、非post-GC恢复时启用；实际v2 Submit和History两个调用接到既有10800/7200，v1及其他路径保持。原history模式验证统一拒绝resume+full-v2+healthy，所以本次是**fresh两节点完整旅程**，不用107b或旧b的checkpoint/后prepare状态。没有增加product配置、lease/heartbeat/HTTP业务超时或新的guardian。

guard仅增加固定project到预算的第二个映射；原107b映射保持。sampler仅增加精确 `timeout --foreground --signal=INT --kill-after=1200s 70200s` 前缀，原25200及直接Python路径保持，仍严格核worktree解释器/manifest/census/evidence。通过AST只读提取validator tuple，分别与launcher两case及实际command模板比较，**两前缀逐项匹配**；未改采样循环、period、资源/step计时、指纹或结果口径，不因前置命令识别改动重测历史成功场景。

18a runbook末节固定了实际journey参数：t4、collect-timing、full-v2、cold Preview、healthy History、stop-on-manual-recovery、原composite-cache和新evidence/project。checkpoint只请求本次实际经过的17项，从v1-upload至history，明确排除v2-archive和全部v3，避免沿用三节点列表导致成功收尾时缺checkpoint。源来源例外不扩展到这一fresh运行；目标产品和三镜像内容仍沿§87已核9704身份，在实际CT108新project别名下正常复核。宿主bench/tests/docs修订不触及产品runtime/image边界，本次**不触发产品镜像重建**，不将该判断冒称04最终runner或backend闭包carried。

### FULL输入与一次性预算

BatchMode连接确认后，只读CT108新manifest `/home/dev/gdds-p6-logs/baseline/preflight/p6w4full20261107a-ct108/expected-inputs.json`，1924bytes，SHA256 **`ae0b281f224f5adabd801ee331e9022b42291399f983db42ef6dd69b2edc143a`**，与实施记录和runbook一致。scenario为full_v2=true/full/t4/cross_project=false，原accepted root和census SHA `04952cb5…e66a67`不变。四条expected_uploads完整：v1/repeat的MODIFIED使用v1；v2 INITIAL使用v1（10652436B、`74974e5f…ebd4c`），MODIFIED使用v2（10486420B、`4cb82a16…bbd27c`）。旧107b manifest full_v2=false且v2只有MODIFIED，未被复用来冒充FULL。这里只派生新场景清单，不重生成SQL或重做已接受输入。

实际各operation上限：v1-preview12887、v1-submit4047、repeat-v1-preview11271、repeat-v1-submit3600、v2-preview11300、v2-submit10800、history7200秒，合计 **61105s**。v1保留原4047，依据同2×v1输入及既有约1450s实际，不无依据统一扩容。初始化/快照1800、尾部3600、read/approve1800、其他1800合计9000，加总 **70105s**；固定 **work70200 / cleanup1800 / hard72000**，从同一起点计算，不在进入新步骤时重置或运行中滑动延长。

沿原机制，inner work70200、INT grace1200、outer watchdog71420+KILL5、project down180+5、postflight60+3，配置等待之和 **71673 < 72000s**；不把此算术称为所有不可中断系统调用的形式化墙钟证明。完成即清理退出，这20小时hard是等待上限而非ETA或实际耗时。预算已与实施者、设计者直接核对，不新增配置摘要审批层。

### CT05原始证据与下一步

BatchMode echo OK后只读 `/home/dev/gdds-p6-logs/baseline/ct05-w4full-236b5b-validation.log`，SHA256 **`29c984470c2934bb1eaf8d881abadf025f7992988afa6fe304601a6dcfa710ba`**：gw-dms-test-05、2026-11-07 11:46:39–49Z，日志明确checkout到236b并以完整236b结束，validation_exit=0。bash -n通过；sampler/guard **18 passed /7.05s**（含两个project真实GNU短超时），budget定向 **4 passed /0.83s**；backend Ruff、mypy（500files）通过。sampler集成用例经真实metadata校验，覆盖新增前缀；解释器/不支持wrapper负例及原入口保持。GNU fixture缩短测试副本等待并模拟Docker/journey，不能冒称它已执行真实Compose或本次FULL业务。

该日志没有额外打印起始完整HEAD/clean字段，不补造；18a仅文书改变，不声称这两批测试在18a重新运行。其余四包源码/依赖仍不变，静态来源保持§96的5de实际结果，不写成当前权威runner carried或五包都在236b重跑。11:47:00Z简略postflight SHA256 **`0c69ccb81149f14c5738029a81704e81f5bfe3739b4eab2317ec6ca63a9f3d2d`**，仅记录hostname/锁释放/时间，不扩称独立整机quiet证明。CT108实际现场守卫仍正常执行。

**代码与必要验证已合格，结论直接送现有实施者并同步设计，不要求等待本报告提交或另一份回执。** 本审核未测试、启动容器、复制源卷、访问SQLite或启动业务。继续W4-FULL及A真正剩余范围，真实失败保留现场并停止受影响运行，普通已定位工具错误最小修正直接闭环；严重设计冲突、无法解决或多轮修复仍失败再交设计/Owner，不在本节扩展整体exit权限。

## 103. W4-STRESS参考与S4派生记录取值：保留record_only，修正旧v3指针

**W4-FULL继续运行；本节不形成新的测量启动/恢复门禁。** 在既有范围内并行读取18a冻结工具，确认 W4、W4-FULL、W4-STRESS、S4 均已设为 `record_only`。S1b 的726.647s是输入生成耗时，不能充当压力Preview参考、工具预算依据或10%补测基准；这与DC66既有澄清一致。W4-STRESS工具观察上限需独立明确有限值及实际依据，不能伪造100%产品实测。实施者在CT201准备，不在W4-FULL运行期间另占CT108或更改其worktree。

**发现尚存的S4后处理取值缺口：** `18a4851d8c52d53afdb95ee4df9fae04e6e36d77:vnext/backend/benchmarks/p6_baseline_timing_references.json` 的S4 actual仍为 `/steps/v3-submit/operation_timing/completion_seconds`；`p6_baseline_timing.py` 的spec生成映射同样将S4设为v3-submit。其求值顺序先执行actual JSON pointer及秒值校验，再进入record_only返回分支，所以record_only不会跳过缺失actual。W4两节点旅程不执行v3；已审107b state也只有v2-submit，其 completion=4027.743s，不存在该v3路径。若使用默认选择器，S4派生结果会因缺字段失败，不是新的Submit产品失败。

此处仅需最小修正生成spec/JSON到W4实际v2-submit，或在既有CLI中明确选择正确v2 metric并绑定记录索引；由原evidence重建派生S4材料即可，不改原run/state/log、采样、计时边界或产品，不重跑107b、当前FULL或历史旅程。若已使用显式正确override，保留其实际命令/选择器，不把默认配置也写成正确。该具体缺口已直接通知现有实施者并同步设计，普通工具/文书修正沿原授权闭环，不等新Owner、回执或GO；修正后的实际差异与必要结果仍待核，尚未标关闭。本审核只读Git对象和已有证据，未在开发机执行产品/测试或到测量节点运行新检查。

## 104. S4默认选择器修正与107b派生记录独审PASS，关闭§103缺口

**§103的S4默认指针缺口已关闭；代码、必要验证与实际派生结果PASS。** 候选 **`5b407f2e81988238e70f100e8579343e478422ef`**，`vnext` tree=`153eb4f27ce207ca9c6e3ab5f16ba7384e727276`。独立读取immutable完整diff并做whitespace检查：相对18a仅改timing spec/提交JSON的S4选择器为v2-submit及相应测试，policy仍record_only，未改产品、采样、operation计时、阈值或其他reference。新增行为例使用真实evaluate和committed reference、state仅含v2-submit，验证直接得到正确秒值及“只记录”，覆盖原缺字段路径。

BatchMode连接确认后只读CT05 `/home/dev/gdds-p6-logs/baseline/ct05-s4-timing-5b407f-validation.log`，SHA256 **`ddbb72541de65bcd9ac3a6bee72252d8ae5c9ac30929bb8a46c22c78d67f1d14`**：gw-dms-test-05、2026-11-07 11:55:09–10Z，明确checkout到5b并以完整5b结束，validation_exit=0；focused **15 passed /0.12s**、backend Ruff/mypy（500files）通过。未补造起始clean/HEAD字段；其余四包静态来源仍按前节保留，不声称当前六包runner通过。简略postflight于11:55:29Z记锁释放，SHA256 **`a8cc0e1f9bb54c0894a456a72fa66e88494fa7ecdfed16e57b565a1fc193f1bc`**，不扩称它独立证明整机quiet。

实际派生在CT05的 `/home/dev/gdds-p6-logs/baseline/s4-107b-derivation-5b407f/` 完成。实施者从审核者已核CT201副本经LAN取得原107b run/state；本审核再次直接hash **CT05实际副本字节**：run44967B、SHA `2f2197d6…37f07`，state39934136B、SHA `0281f0e0…5fc897`，均精确等于§101原件，不只信派生JSON自报值。没有为这次处理读取运行中的CT108大文件或改其worktree。

独立核对三份已关闭输出：`s4.json`（887B）SHA256 **`b86ca2ac7bbac1ce2b6fde3343fac9f7675a1c66f7cc1f217fd1a31ac1ba8233`**；`derivation.log` SHA256 **`4aec3678866d850a370fd6753a27f4d515028c90a73f918aa76bae33729f557f`**，11:56:09Z、tool HEAD5b、exit0；`postflight.log` SHA256 **`4d06cb8ec0af93d2388432eb603b33fee03bb578a9a80b4ddc91791b51155292`**，11:56:29Z记CT05锁释放。记录的reference_file_sha256=`3b3c4352c3ff0bd55cd6afdf38e1be4b2b6d1ca5ae8676798f83b9b5cade1f05`，与Git中5b reference JSON原始字节独立计算值一致。

S4实际选择 `/steps/v2-submit/operation_timing/completion_seconds`，**4027.743s / record_only / 只记录**；reference与relative_deviation均null，不拿旧S1c v3或生成器时间比较。输出准确保留**测量HEAD3fd、hostname gw-dms-test及原run/state SHA**；CT05/5b只是后处理执行来源，不改记为在5b或CT05重新测量。该值是completion，不与§101 API用户可见4027.732s互换。

本轮未运行测试、产品或业务，只读代码及CT05已完成的证据。产品/镜像边界不变，不触发重建，未宣称最终container gate carried。结论直接送实施者并同步设计；W4-FULL仍按18a在CT108继续，107b不重跑，W4-STRESS及A其他真实缺项继续原分工，无新增GO或整体exit结论。

## 105. 631表旁证可复用原最终summary，实际三组对照仍待核

**既有副本哈希路径满足原旁证的取证方式，完整原记录可复用；不要求先重复复制原卷或重跑旅程。** 原要求仍是2× v1、v2及三节点v3，与S1c `s1c-vprime-ebd1_*` 同输入结果逐表对照，不以旧1030b比较替代本次目标。本节只审证据路径及复用条件，**尚未取得并比较这三组实际目标映射，不标631旁证完成**；W4-FULL继续运行，不将其作为测量新门禁。

只读原始Git对象：S1c `b96fe8e4cc`、2× core `bb348a9299`、H2三节点 `e0768fbeae` 及当前FULL工具 `18a4851d8c` 的 `_measure_dolt_table_hashes`、`_dolt_table_hashes_from_copy` 两项主函数AST分别精确相同。前者用docker cp将served仓库复制到worktree外scratch，再以无网络隔离容器绑定该副本；后者在副本checkout指定commit、批量读取DOLT_HASHOF_TABLE，并检查缺表、多表及32字符Dolt hash格式。不能仅凭当前函数存在，倒推历史实际运行了该路径；历史源代码、成功日志及结果绑定仍须对应。

**实际索引位置需要纠正：** 代码将S1/S2/S3的 `dolt_table_hashes`、三节点 `H2-3NODE.third_commit.dolt_table_hashes` 写入完整最终summary的 `datasets[].baseline_operations`。bb348的run.json只保存conclusion/elapsed等摘要；不能因run/state没有maps就判原证据缺失。审核者CT201已核107b副本也实际如此：run_result仅conclusion/elapsed、state无baseline_operations，**原launch最终summary的S1/S2/S3各有631项**。该例只证明保存位置，107b的W4 v2不是2× v2，不被拿来关闭目标旁证；S2直接复用S1 map，也不算独立第三组证明。

实施者在FULL结束后先检查原2× core/H2及S1c vprime完整journey/launch summary或其已认证JSON：保留原文件SHA、run/state、实际输入包SHA/bytes、Repository commit和版本/镜像来源，按原三组配对比较**完整表名集合恰为631且逐值全等**，不只比较交集或计数。S1c handoff已记录参考v1 `gc0j1d5316nui249o5d1petnncn8u881`、v2 `ej01n1u7srga41mdsqbht4lri82kl1mp`、v3 `jlpa7e30svqudnem8uo40vrbf5j2upt6`；原vprime journey也包含这套副本哈希输出，应优先查其原summary，不只查旧1030b对照JSON。A下仍保留各历史真实版本，不回填9704；当前107b/W4-FULL不同输入不替代2×目标。

若这些原记录齐全，直接离线对照并写旁证结果即可，不增加新的取卷/业务。只有确实缺失的单组map才沿既有只读卷副本流程补该commit；该函数现有入口依赖live RS的ps查询，**不能为复用函数启动旧源栈或在原仓库checkout**。原631不符的停止/报告规则保持，不用输入相似、canonical digest或旧1030b相等概括替代本次表哈希事实。路径结论已直送实施者并同步设计，无新GO。本轮只读CT201代码、已有日志副本和索引，未访问运行中的CT108、运行测试/容器或修改产品；无镜像重建触发，也未宣称新容器门禁。

## 106. 保护预算复核：外层一致，局部未全部实测校准；FULL条件恢复方案已明确

**不能声称所有阶段的局部保护超时都已证明留足。** 当前FULL的总工作/清理/hard配置及真实接线一致；v2 Preview等局部仍沿旧t4量级，可能先于全流程work截止结束。没有证据证明它们当前必然不足，也没有把未结束的阶段标性能PASS。按Owner与设计要求，**不修改、加时、重启或预跑在途FULL**；后续STRESS、DC63/V5b、record及04各自启动前另行固定局部/外层/清理安排，不把ETA上沿机械当硬限，不新增逐摘要GO。

### 已核实际接线与局部边界

本轮只读immutable运行HEAD **`18a4851d8c52d53afdb95ee4df9fae04e6e36d77`**，并轻量读取CT108现有launch.log头部，未查询进程、运行Docker或新探针。原头部明确11:49:34.763Z、gw-dms-test、完整18a，实际child前缀为 **`timeout --foreground --signal=INT --kill-after=1200s 70200s`**；解释器为该18a worktree的字面backend .venv Python，实际FULL/cold/healthy及17 checkpoint与§102相同，manifest SHA为ae0b…c143a。该日志仍开放，未将它封口hash或称结果完成。

guard的FULL分支为work70200、watchdog71420；内层1200 grace、外层kill5、down180+5、postflight60+3，配置等待和71673小于hard72000，清理余量没有漏掉。实施者提供的实际外部controller是前台 `ssh -o BatchMode=yes ct108-gw-dms 'bash -s'` heredoc及tee，未另加timeout，工具长期session72199的yield/等待不是业务deadline；heredoc未独立存脚本，外部调用事实按其明确报告与既有controller记录限定，不补造独立进程审计。

| FULL等待 | 实际秒数 | 证据与边界 |
| --- | ---: | --- |
| v1 Preview | 12887 | 旧t4 2577.296×5向上取整；不是本次已完成值 |
| v1 Submit | 4047 | 旧t4 809.218×5；同2×v1历史约1450s提供量级背景，未据此冒称9704本次已完成 |
| repeat Preview | 11271 | 旧t4 2254.054×5 |
| repeat Submit | 名义3600 | NO_CANONICAL_CHANGE同步路径直接返回，不进入operation轮询；单次HTTP仍为600s |
| FULL v2 Preview | **11300** | **旧t4 2259.980×5；没有9704 FULL同口径实测，确可早于70200s截断** |
| FULL v2 Submit | 10800 | W4固定profile实际接线；107b的4027.732s仅是较轻路径实测，非FULL证明 |
| History | 7200 | W4固定profile实际接线；本次healthy FULL仍待实测 |

上列名义operation上限合计61105；辅助9000、work70200是一次规划余量，**不是已经证明所有helper最坏等待之和均被覆盖**。更短的现有局部保护仍存在：backend单次HTTP600、RS读取300、Compose up600、checkpoint pause/unpause各120、每卷cp及Dolt hash复制/SQL各3600、sampler若干Git/Docker查询各10秒，均可能在外层之前失败；它们不是整个异步operation的观察时长。产品lease/heartbeat/stall及Repository业务超时另属被测行为，不为凑工具预算放宽。本轮未发现另一处把FULL v2 Submit仍接回4055或sampler误用25200的情况；尚未发生的慢I/O、FULL或压力成本仍据实报告。

### 确认的FULL恢复接线缺口与最小处置

当前18a **不能按原FULL/cold/healthy参数直接使用普通失败checkpoint恢复**：`_validate_history_cache_mode` 的fresh healthy要求非resume，已有history_resume要求非full-v2且final-state；8452行cold Preview校验同样拒绝普通resume。guard还只登记107b和当前FULL两个project，失败后新身份需窄登记。不能把“保存了checkpoint”扩写为当前入口已经可直接恢复。

恢复还须避免一处实际状态偏移：6095行的cold准备在 `runner.run("v2-preview")` 外无条件执行。若从v2-submit或更后checkpoint恢复并复用已完成Preview，照原代码重清cache会改变该checkpoint的缓存条件；只放宽validator仍不足。最小方案已直接交实施者并获设计认可：

1. 仅在真实失败、原因已定位并保留现场后，用新project/key，认证**同9704产品、原FULL manifest/输入/目标镜像、源失败step-before checkpoint及完整卷摘要**。保留原source/run/state/log及旧运行结论，不启动旧源栈或从头重做已通过业务。
2. 对这一已认证FULL恢复窄放cold+healthy校验，并登记对应新guard身份/实际预算；普通image/input/source约束保持，不泛化为任意resume、H3或skip。实际失败若是局部工具等待不足，恢复前一次明确该剩余步骤及总截止，不在在途动态续时。
3. **仅当v2 Preview将实际执行时做cold准备**；复用源已完成Preview时，保留原缓存状态及其来源记录，不再次清除。History仍实查原条件/TTL；不满足则明确诊断，不静默改none、延TTL或伪称healthy。
4. checkpoint仅按原resume边界选择后续步骤，沿用保留的合格失败前checkpoint，不把整个原17项列表重新传入导致“早于resume边界”拒绝。普通bench修正及必要focused后，实际前提满足即可按既有DC80授权恢复，不另等Owner/GO；证据沿用不确定或新业务取舍再交设计处理。

这只是已明确的条件恢复方案，**尚无FULL失败、未实现/执行恢复、未宣称未来恢复代码已经PASS**。它解决“若失败是否只能整档从头重做”的具体工具限制，不新增恢复框架或预跑矩阵。源码/产品/在途worktree和镜像均未修改；最后产品镜像仍为§87绑定9704身份，无重建触发。本轮没有测试、容器/业务或原SQLite访问；结果及未实测的预算边界直接同步设计和实施者，整体测量继续。

## 107. DC63现成计时限制、9704边界映射及最小诊断方向预核

**现有粗段不能直接补成同口径DC63细段；边界草图已核，可按以下纠正继续最小工具实现，无新GO。** 本节不是新诊断代码/结果PASS。设计已用 **`db0e72f61989a54f3e17ed3874aff52909ed05be`** 的 `p6-dc63-v5b-measurement-completion-plan.md` 固定原授权内的最小补缺：普通t4 v1/v2 Preview、同一两节点History的checkpoint/bundle与导出迁移，以及复用其准备状态跑V5b A–D；不新增冷热/refill/H2/H3诊断矩阵。实施者边界草图为独立诊断分支 **`cb724abc6a213d62b2a9fe2bdc4287fbc6d4f5a6`** 的 `p6-dc63-9704-diagnostic-boundary-map.md`，相对5b仅新增该文档，diff whitespace通过。产品来源9704、正式参考线和在途18a FULL保持不变。

### 已有材料能证明什么

只读18a timing reference：共21个DC63 selector，Preview每版checkpoint-read/pair-pipeline/bundle/finish共8；Submit v1七项、v2六项。S1a参考确来自非候选e52ad2对af559的诊断，handoff SHA `15860f93b1e4760ae4c254f76c0720f261332e941dd00840005ddafd6c7e5cb7` 与5b Git原始字节匹配。其九文件诊断未进入产品候选，不能把这组旧值当9704实测，也不能cherry-pick旧实现覆盖新产品。

已核普通9704生产路径无e52的细span；现有API、operation_step、step间隔和await会话可保留其自身口径，**当前材料未给出可直接填入21项目标的同口径记录**，不是将缺值计为0。连prepare-total也不能机械复用DB step：e52的 `worker.step.execution` 用perf_counter包executor调用，当前旅程从DB started_at_us/completed_at_us作差，端点包含claim/确认等差别。Preview assemble总段不等于pair；materialize包含迁移来的导出成本，也不等于checkpoint-read。W4/GC诊断的631表合成输入与普通t4的312表不同，已有细段可作该实际输入的旁证，不能填为普通t4同输入对照。若后续找到真正匹配输入/端点的细span，可认证复用，本节未要求重取其数据。

21个selector是台账，不形成21次旅程或新增21项性能门槛。原DC63核心是实际checkpoint/bundle拆分与成本迁移说明；其中History没有已接受的S1a同口径细段，保留历史API背景并说明不可比，不伪造逐项差。旧finish也不是e52源码中的单个同名span，原日志/已接受汇总算式尚未核到时，不自创bundle_end→executor_exit再与0.999274/0.763653比较；可先记录当前实际覆盖并标不同口径。

### 对草图的具体边界纠正

- Preview materialize的 `_materialize_all_sides` 包含baseline/upload等子调用，父子不相加。assemble checkpoint读取从 `_load_step` 开始，包含envelope读取/匹配及 `_materialized_preview_inputs_from_checkpoint`，不是只量最后一个函数；之前完成的Parquet/export成本另记。
- 旧pair span包私有 `_run_pair_pipeline`；`_assemble_preview` 是含pair、bundle等的父段。pair后还有 `surface_artifact_closure`，bundle后到handler finish前还有 `_required_ready_refs` 与assemble state组装；这些实际成本不得漏记或硬塞bundle。ready closure、state/checkpoint/pin、lease/successor的归属需明确，readback和嵌套span不重复求和。
- History在 `application/history/compare_jobs.py`：materialize distinct commits及 `_materialize_commit` / `materialize_repository_ref` 的导出/cache成本另列；assemble由 `_load_step`、load_checkpoint_envelope、`_sides_from_materialize_checkpoint` 恢复绑定，pair/assemble_bundle再分。只补同一两节点普通t4，不用Preview字段代替History测量。
- Submit旧frozen-input对应 `_open_projection_inputs`，build-input另列；resolve manifests/changed/removed检查、before snapshot组装及reader close需明确余量。after-snapshots包括after_by_name构造和changed_after筛选；只量 `build_import_mutation_snapshots` 函数会漏掉调用方工作。旧plan/render覆盖plan调用、rebuild选择、schema/DML渲染到replay_sql拼接整个组，只加plan及DML两个wrapper不等于该旧组。publish不含后续prepare checkpoint，fresh/reuse/取消/异常分支分别记录。
- 草图中的publication类名应为 **`infrastructure.repository_write.import_publication.SubmitImportPublicationAdapter`**，已直接告实施者修正文书。Preview与History各自已from-import绑定assemble_bundle；薄wrapper必须覆盖真实消费namespace，仅改capability导出名不能保证拦到它们。必要focused应经过实际消费调用并核异常/返回传播，不只单测wrapper本身。

### 可推进的最小方式与当前边界

设计已认可：优先在冻结9704镜像上的独立诊断project只读挂载非候选入口，在正常worker前安装精确薄wrapper，仅粗阶段perf计时/计数，保留真实worker、GC调度、lease、事务与Compose artifact路径。多语句组只在能直接捕获已核起止时记录，捕获不了则标当前不同口径/未测，不为凑selector重构产品、逐行trace或按父子差额伪填。若确需最小诊断overlay/镜像，另记完整诊断身份、差异和实际runtime接线，不覆盖冻结tag或宣称等于正式产品执行配置。

优先复用已认证素材；需要新worker内部细段时，按既有DC63授权一次必要普通t4诊断链覆盖v1/v2及一条两节点History，并复用其合格准备状态和独立scratch跑现有V5b A–D。先集中固定普通t4包/规则/commit/cache、边界/readback、工具身份及充分的局部/总/清理预算；不把旧42分钟或规划区间作为hard限。实际诊断只在FULL/STRESS等正式测量结束、CT108空闲并取得占用后进行，不修改原state来满足 `/measurement` 指针，不将诊断数值回填为正式operation elapsed。

本轮只读CT201的Git对象、已存副本和索引，未访问在途CT108、运行测试/容器或改产品/镜像。必要工具实现、focused和一次实际诊断结果尚待交付；结论与边界纠正已直送实施者并同步设计，普通修正直接闭环，不逐点等待设计/Owner回执。正式V_ref产品、最终04及整体exit不由本节代判。

## 108. 隔离DC63工具821代码及必要验证PASS，实际诊断准备仍在推进

**独立诊断候选 `82164291f658be9ca94a972f8d2c17179cea7888` 的本轮代码及必要focused/静态复核PASS。** 诊断tree=`7ff0b0ef864e827b030a31d024d0ba2066b28b5a`，不是正式V_ref或9704产品tree。真实普通t4输入/状态、最终计时覆盖期望、各操作及总预算仍待一次固定；本节不把它称为已完成诊断、V5b执行或可以忽略既定启动前提。FULL在18a继续，不修改/重启；沿原授权直接完成剩余准备，不另等Owner/设计/逐摘要GO。

### 最终代码及本轮修订

读取独立诊断worktree及immutable 3456→01000→f911→d5fe→821完整差异；相对5b，变动为边界文档、两个benchmark诊断模块、其测试及诊断分支Compose worker三行接线，业务src未改，diff whitespace通过。worker用只读挂载脚本在正常bootstrap main之前install，再进入原worker main；后者仍设置正常INFO日志并构造原composition。已核composition在运行时调用被替换的factory全局名，Preview/History各消费namespace的assemble_bundle也实际替换，未仅修改capability导出别名。

wrapper按executor用ContextVar隔离operation/step/handler上下文，返回原值、传播原异常并在finally清上下文；计时日志异常不改业务返回。只在粗函数/组边界计时，不逐行profile，不排checkpoint或建立持久evidence状态机。checkpoint组从load-step至inputs恢复，after-snapshots从构造快照入口至parent入口，plan/render从plan入口至publish入口，覆盖调用方多语句工作；后续函数自身时长另列为嵌套观测，不相加。parent rows重复包装已合并。

Preview/History直接增加ready refs、ready closure、state artifact、checkpoint prepare小段；它们**不是旧finish的同口径总量**。ready_refs仅包handler的 `_ready_closure_refs_from_assemble`，不含assemble内部 `_required_ready_refs`、state组装等未直接覆盖的工作；pin/lease/successor等也不据父段差值填数。文档已明确这些限制，实际交付按覆盖范围说明，不强填21 selector。

History按实际调用序号记录binding/requested/export表数和export_cache_configured。源CanonicalBinding确有table_identities，且实际调用使用这些keyword；这些是元数据计数，不读取/输出行值，也不把“已配置cache”当命中率。真实cache条件仍关联诊断输入/准备记录。计时上下文/阶段缺失或metadata不可用不能虚构，结果审核仍核本次具体输入与角色。

独立coverage工具要求非空、无重复的operation/handler/stage期望，并将缺失stage或异常/未完成事件判为INCOMPLETE；修正前仅看stage/outcome的缺口已补，**相关事件必须有非bool、有限、非负elapsed_seconds**。缺值、NaN、Inf、负数不计为0。期望须从真实旅程绑定v1/v2/History等operation角色，coverage仅证明给定期望的事件覆盖，不独立代表DC63/V5b全计划完成；输入身份、阶段定义及业务结果仍由原记录与结果审核约束。

### CT05原始证据

BatchMode连接确认后，只读 `/home/dev/gdds-p6-logs/baseline/dc63-static-8216-20261107.log`，SHA256 **`1f09020b5c1ff56eff32a5a14d79122aa4ddc7124a0800795e5c34bdb98b5b6c`**：gw-dms-test-05、2026-11-07 14:17:31–32Z、起止完整821，**11 passed /0.63s、Ruff通过、mypy 501files通过，三项exit均0**。覆盖真实消费namespace解析、原返回/异常、未闭合组、组在下一调用前关闭、缺失/异常覆盖及无效秒值；没有在本轮focused中执行真实312表或A–D。其余四包无变动，静态来源仍沿前节已验证来源，不写成821上权威runner/carried。

`dc63-container-check-f911-20261107.log` SHA256 **`b3ac68ea73e21852dff19a80d3b1ade1c24486aa991fd899b1a452abf5ab6fbf`**，14:07:36–38Z、起止完整f911、wrapper_install_ok、exit0；worker脚本及Compose从f911至821无差异，所以该最小挂载install检查关联当前相同接线，不重复容器。日志未打印完整镜像config/DiffID或整个业务启动过程，**不能只凭install_ok独立声称镜像身份已全核或完整诊断链通过**；诊断实际启动仍按原预检绑定冻结镜像完整身份、wrapper SHA及command/mount。Compose的command/只读mount是诊断runtime边界变化，此检查仅服务该诊断接线，不代替正式产品门禁；不重建/覆盖冻结镜像，不把诊断分支合为V_ref产品。

失败及较早通过均原样保留：首份focused因Rust PATH准备错误退出1，日志SHA **`93ce5e0bdaad7492ec9e593b421d10ca7902956f0e1690ff1a6b3896154559f7`**，修正后同一步4passed；后续6/11项验证反映新增范围，不把首份改成pytest通过。首次4b2b静态失败日志SHA **`cf08f875e97dcd80eb078a3267f2daa533ef108d4ec634fc8f982eb5b864d284`** 已匹配，类型修正后以821完整日志关闭，不按准备失败次数另等Owner。V5b接口 `--help` 成功仅是CLI解析/导入事实，未跑A–D。

### 下步及报告边界

普通修订已与现有实施者直接闭环，本节作为准备代码里程碑汇总。真实诊断仍在FULL/STRESS正式测量之外的CT108独占窗口执行；局部I/O、操作/工作/清理预算和同一普通t4准备状态需集中核实，不将旧42分钟、ETA或当前W4耗时充当充分性证明。V5b原输出是segments列表，而旧reference的A/B/C默认选 `/measurement/elapsed_seconds`、D选measurement字段；派生后处理须按真实segment角色/原值使用既有明确selector或独立派生文档，不能给所有子段同填总wall，也不改原state/原始输出。此接线提醒已交实施者，不影响保留原测量。

本轮只读代码和CT05已关闭日志，未在开发机运行测试、未启动容器/业务、未访问运行中的CT108或原SQLite。实际诊断与A–D结果尚未交付，正式V_ref、04及整体exit仍按原分工；源产品/冻结镜像不变，所有新计时将标诊断来源，不冒称正式operation elapsed。

## 109. 角色绑定修正与V5b派生代码复核PASS；STRESS仅完成结构预审

**DC63 coverage真实state绑定修正 `fe437f516b218d4203ede3150f094d673196deb9` 及V5b派生工具 `ce97abdf2bb91830741cf75c557090b74421d540` 的代码/必要局部证据PASS；尚无实际DC63或A–D结果。** 本节汇总直接与实施者闭环的普通工具修订，不引入新GO或业务重跑。

f33角色绑定首版将Preview ID读自 `preview.operation_timing.operation_id`，与真实producer不符。实际 `_preview` 将ID保存在 `preview.result.operation_id`，timing不含该字段；此前17项fixture也误造了timing ID，所以通过不能证明该真实接口。fe437只改v1/v2 Preview两条读取路径，并使fixture的result含ID、timing为空；Submit仍读自身operation_timing、History仍读operation_id，不增别名/双读、不改原state或旅程producer。五角色绑定八个handler，History materialize还要求两个distinct commit ordinal各出现一次；异常/缺段/重复/无效秒值仍拒绝。BatchMode确认后直接读CT05 `dc63-coverage-fe43-20261107.log`，SHA256 **`173d89b2a5cf7c9f40eff425daa688dd6fe9bec16b969b51a87ecc64a64ca565`**：14:50:07–08Z、起止完整fe437、17passed/0.64s、Ruff/mypy502files、三项exit0。该Finding关闭，旧f33通过记录按其实际覆盖保留。

V5b派生六份独立参考文档，原raw不改：A取materialization total加其后独立readback，已核producer的total终点在readback之前；B按v1/v2各取pair（已含records closure）、surface closure、bundle、bundle及records两项显式readback，不再叠加records等嵌套子段；C取七项明确stage；D分别取Preview/Submit的serialize-verify-publish、readback-decode及pin transaction三项，ready closure和state artifact位于该D计时外，保留此边界。已核真实B scenario由metrics覆盖为t4_v1/v2_preview_bundle，C末项record没有failed字段，不能误当失败；非法秒值、重复/缺失/失败stage和非PASS或HEAD不符的raw仍拒绝。raw SHA由原字节独立计算，文件在worktree外以新目录写出；312表计数及自报HEAD不替代独立输入/commit/镜像来源证明。

CT05 `v5b-reference-focused-ce97-20261107.log` SHA256 **`d24ae420140799b48c4b77a5f538dce9ac323c6467075b4abcdc8e2ffba7a412`**：14:25:51–52Z、完整ce97起止、5passed/0.09s、Ruff/mypy502、三项exit0。只证明派生及格式/错误边界，不冒称执行A–D、实际312表验证或性能结果。

STRESS分支 `1742a8bcd62287fd9eb9fbd0a839615a470b2664` /tree `801e3925f634f92725c17a3c3a2539cb81b130a8` 已完成结构预核：只对固定100%输入root/project及t4-v2-preview scope启用压力预算，实际v2 Preview调用已接专用值，并在其返回后结束，不运行v2 Submit/History；13 checkpoint、三次MODIFIED上传、full_v2=false/history=none，与FULL四上传/17 checkpoint明确不同。源码/Compose产品边界未改。此前示例把18h Preview并入23h工作上限不足，已更正为work106200/watch107420/hard108000的**规划示例**：prefix31805+Preview64800+辅助9000=105605，配置清理等待107673<108000；不能把这些保护上限当ETA或已经充分校准，也不把S1b生成器726.647s当产品Preview参考。实际100% manifest及最终预算仍待FULL结束后固定，现不具备实际启动的完整前提。

已核CT05 `w4stress-focused-11104-20261107.log` SHA **`117d9b4d84a09e3da1f3381c7748318e0480406e70e30eaad1b5f74956858f85`**，14:20:21–14:21:01Z、完整11104起止、profile2passed及guard/resource/manifest25passed/bash语法0；`w4stress-focused-1742-20261107.log` SHA **`8969f4f2e243dcf1fc585606dbd957c5df7c40b16dd597a182076b3bf597faab`**，14:21:50–14:22:01Z、完整1742起止、manifest6passed/Ruff/mypy500/exit0。小fixture验证角色规则，不是实际100%输入验收。当前压力scope拒绝resume，checkpoint存在不表示恢复入口已实现；若真实失败，按原DC80最小修正保留该压力scope，不切full绕过并额外跑业务。

本轮只读Git对象、已有副本及CT05关闭日志；未运行测试、容器/业务，未访问运行中的CT108或SQLite。冻结产品9704/镜像、FULL18a及历史结果不变；正式V_ref、04与整体exit尚未收口。

## 110. DC63保活chain及有界launcher dc829代码/必要验证PASS，实际前提尚待固定

**独立诊断候选 `dc829345dd8c0056f7223a6a360c349b011b69f8` /tree `0ddc80fa5f4a1c56a7171acc7b5a7cf8aa1350f2` 的本轮chain、sampler接线及有界清理审核PASS。** 实际普通t4 manifest/输入、完整镜像与wrapper/runtime身份、最终实际argv及启动现场条件仍未交齐，尚未运行诊断或V5b；本节不把准备代码通过写成实际测量完成。按原授权继续必要准备，无新Owner/设计/逐摘要GO。

只读0773→47d7→3b62→3722→dc829完整变化；chain相对0773未再改。它先用real profile manifest、仓库real census及t4/full/non-full-v2参数执行真实verify_before_run，再以普通keep-stack旅程正常完成v1/v2及两节点History。真实producer保存flat `root/runs/<新project>/t4.state.json`，_stack项目/tier/HEAD及v1-submit.repository_commit_id与consumer一致；secrets为同目录t4-secrets。只在旅程成功、真实state角色coverage PASS后，定位本项目唯一RS容器及地址、同次v1 commit和token，用现有V5b真实CLI运行A–D，保存raw原字节SHA及派生文档。不启动旧源栈，不改原state；阶段间仍属于同一链，RS保活至V5b结束。

非formal薄入口仅调用已有 `run_sampled(expected_input_manifest=None)`，避免formal sampler的evidence-out要求与keep-stack冲突；输入验证由chain及journey原消费者实际执行，不关闭formal validator或改变采样周期/计数。输出按隔离诊断标识，不能作为正式operation baseline或补造formal input-provenance。actual argv还须固定guard project、chain project、GATEWAY_REAL_DUMP_ROOT及--root一致；真实312表包/规则/commit/cache与诊断镜像/command/ro mount来源照常关联，不能仅凭代码默认值认定准备齐全。

诊断project用非foreground GNU timeout包整个chain，使INT到子进程组；外层仍用原独立session/watchdog。实际发现parent先响应INT退出时，timeout返回不保证忽略INT的孙进程退出；3722在wait之后对残余诊断session调用原stop_watchdog，TERM后最多5秒再KILL，最后执行EXIT down/postflight。手动INT/TERM同样回收整个session。旧两个正式project分支保留原foreground规则；不把诊断Compose挂载/command合到正式V_ref，也不声称可拿诊断worktree替代正式项目执行。

本轮另直接指出并关闭父子环境缺口：journey内部构造Compose env不会反向更新guard，dc829将父guard的五个secret/mapping变量固定为同一新project/t4-secrets，避免结束日志/down用错路径。EXIT在down前有界保存新项目日志；docker ps为30+5秒、logs为180+5秒，随后原down180+5、postflight60+3秒，不删卷。日志获取失败仍执行down，但保留节点锁并exit125；残留或静止无法确认同样不解锁。配置work77400、watch78620/hard79200，按watch结束再计kill5、残余session5、ps35、logs185、down185、post63合计**79098<79200**；1200 grace已含watch内，不重复相加。这是已配置等待关系，不是helper/外部I/O所有最坏时间的保证或实际ETA；计划所列63000/14400是工作规划分配，实际代码以同一全链77400截止，阶段切换不重置截止。

直接核CT05已关闭日志：`dc63-chain-0773-20261107.log` SHA256 **`9f15d39f4b4f017d6d827450e04589dfe269c3a6360e9975c67a8c00a56617b4`**，14:52:43–45Z、完整0773起止、19passed/Ruff/mypy503/exit0；fixture证明coverage不完整不进入V5b，成功传递本次repo/commit。`dc63-guard-dc82-20261107.log` SHA256 **`afdbde772b30210a6a9ced142dc8562472da1e26e9746bff04a55481329acf35`**，15:00:57–15:01:09Z、完整dc829起止、40passed/11.15s、Ruff/mypy503/bash-n全0，含实际GNU timeout的孙进程INT、忽略INT后TERM收束、旧项目路径、down环境、保卷及日志失败保锁。它们使用模拟业务/Docker，不冒称真实诊断Compose或312表链已跑过。

较早47d7的37passed/1failed为孙进程fixture嵌套转义语法错误，失败SHA **`6599215e044b2344a6d516f103665424ddaa98bc94e2d2693da323fd38047698`** 保留，不当成真实诊断失败或已覆盖信号。3b62的38项及3722的39项仅记录新增覆盖历程，最终以上述40项日志为本轮证据；前次chain d582的mypy测试导入失败同样保留。其余四包静态按既有来源，不声称dc829权威runner/carried。

本轮仅独立只读代码与CT05关闭日志，未运行测试、业务/容器或访问在途CT108。新接线是隔离诊断runtime边界，最小mount/install来源仍§108及相同worker脚本，实际完整身份在启动预检绑定；不重建或覆盖冻结tag，不把这些mock/focused升级成正式容器门禁。准备继续，真实结果再按原范围独审；FULL、STRESS、631旁证、最终04及整体exit各自保持原状态。

**参数草案及后续小修订复核：** `40610231ee9109959d82b14bf0567ce5de76522c` 仅文档，所示guard五个位置参数及分隔符后的chain参数与真实consumer相符，manifest由guard单次注入。审核直接指出manifest无PROJECT字段、generate示例须补必填路径两处文案；最终 `52ab097f0e49d9ede1d7cee42a8a3c012aead519` 已修正文书，并在guard导出固定project、chain第一条外部命令之前校验project及规范化root与guard环境完全一致。正常调用保持原参数；错误project/root各自拒绝，防止child运行项目与父清理目标偏离，没有新的业务或证明矩阵。

BatchMode确认后只读CT05 `dc63-guard-52ab-20261107.log`，SHA256 **`65af63d59dd15f8d2c789787ed2c3437f1f347d59225f06abe29a13613a0b733`**：15:07:04–16Z、起止完整52ab、42passed/11.14s、Ruff/mypy503/bash-n全0。代码/该必要验证PASS，worker/Compose/预算未改，不重跑挂载install或业务。实际输入身份、规范化绝对ROOT及新project、完整镜像/runtime身份和实际启动现场仍待固定；未运行诊断、未访问在途CT108，不新增Owner/设计/审核GO。

**成功退出但残留子进程的状态修正亦已关闭。** 实施者随后发现52ab虽收束残余诊断session，却会沿用chain的0而误报成功；`bbe577c6d8ab9cf11452b3441b85cd9c8d280ea0` /tree `d974f75967053c7212e6b5a1cb20b11ff5ddfcd6` 仅在这一分支将0改125，再沿原stop_watchdog及EXIT清理，既有非零状态不覆盖。新增focused证明正常主进程遗留的孙进程收到TERM、整体125且已安全清理时可解锁；原保卷/残留不明保锁保持。只读CT05 `dc63-guard-bbe5-20261107.log`，SHA256 **`daa70a8e2ba0a422a5466b7f5c78e8e616c8c2f0f029f0dddca38c10002c07fd`**：15:09:15–28Z、起止完整bbe577、43passed/11.42s、Ruff/mypy503/bash-n全0，代码及必要验证PASS。本次未增加deadline或product/runtime修改，未重跑install/业务；实际诊断准备与FULL等待状态同上。

补充直接核CT05 `dc63-entry-bbe5-20261107.log` SHA256 **`65c83018f070cfd111e4b7eb9455aa5d23f18ab114f1362f9bdd712e03257d31`**：15:39:37–38Z、完整bbe577起止、实际路径chain --help及非formal sampler模块 --help均exit0。仅证明CLI导入/解析入口，不是实际chain、容器接线或业务通过；不因此缩减真实启动前提或重复运行。

## 111. W/H及S2偏差工具误取整旅程：已定位，按原单operation定义修派生

**实施者提示并经本审核独立确认：timing reference工具的14项actual选择存在单operation/整旅程口径错误；修订与实际原件派生尚未交齐，本节不关闭该Finding。** 其中13项为record_only（W1/W2/W3/W3-FULL/W4/W4-FULL/W4-STRESS，H1/H1-FULL/H1-REFILL/H2/H3，S2）；另有compare的H2-3NODE actual及其旧reference同时取整旅程。问题在后处理选择器及参考取值，不是新测量定义；当前在途FULL、原run/state/计时及已完成业务均不修改或重跑。

只读18a实际参考表和 `_specs`，这些actual均指run `/run_result/elapsed_seconds`；H2-3NODE还以S1c b96 run同路径19361.157s为reference。`implementation-stages.md` §9、DC53及设计§1/16.3明定W为单Preview、H为单History；W主READY并另报完成，H1/H2/H3主READY，H2三节点按完成，S2为原样重传的同步受理且不产生Repository operation。runbook的full journey仅是同时产出多个场景的执行载体；scope=t4-v2-preview也包含v1/repeat前缀，不能把该scope wall当v2 Preview。

明确映射为state `/steps/` 下：W1取 `v1-preview/preview/operation_timing/user_visible_seconds`，W2取 `repeat-v1-preview/preview/operation_timing/user_visible_seconds`，W3/W4及其FULL/STRESS取 `v2-preview/preview/operation_timing/user_visible_seconds`；H1/H1-FULL/H1-REFILL/H2/H3取 `history/result/operation_timing/user_visible_seconds`，H2-3NODE取同处completion_seconds；S2取 `repeat-v1-submit/operation_timing/user_visible_seconds`。各operation的completion仍单独保留，不用completion替换READY；原t1–t4完整旅程及已经正确的S1/S3/S4选择器保持。record builder `_sample_scenario` 本来就按operation_timings分取ready/completed，**不能据此把现有全部record或原测量判无效**；实际受影响的派生文件须逐项按其metric_pointer核对。

只读审核者§101已认证CT201副本即可核出区别：107b run elapsed6522.846s；继承的v2 Preview user_visible/completion各4743.456s；本次History各2352.010s；repeat-v1-submit同步NO_CHANGE各0.008s。它们来自不同实际操作及日期，W4继承Preview不能因为顶层run为3fd/产品9704就改记在9704重测。此处没有在开发机执行benchmark或测试，仅解析已核原JSON；也未访问在途CT108。

H2旧参考的S1c b96确为2×、三节点、cold History，原handoff/state SHA及immutable producer均支持该same-operation路径；**本审核尚未拿到其实际原state副本，不能填History reference数字**。FULL后从已关闭原件认证取同端点值及SHA，再与实际H2操作对照；原19361.157只保留为整旅程历史，不能继续与单History相比较。设计已明确同意最小后处理修正、原policy/统计保持，A已关闭场景仅修派生，不因错误selector或跨版本差异机械补测；参考确实不能恢复则写UNAVAILABLE/不可比及原因，不填零/伪造或静默切record_only，需要新业务取舍才报设计。已直接交实施者在独立工具worktree修订并做必要定向检查，无新GO、不改正式采样/计时或重跑已完成旅程；最终代码及实际派生结果待复核。

**13项record_only选择器代码修订已通过，H2-3NODE及实际逐场景派生仍待闭合。** 独立工具候选 `132ac85f085df5193a11be4de25e50f7c903bfd9` 相对5b仅改timing工具、参考JSON和其测试；13项actual路径与上述映射一致，_specs和提交JSON同步。独立解析两版JSON：仅这13项actual有语义差异，其余entry、policy、reference和顶层threshold均相等；Unicode转义是同值序列化，不当作参考内容变化。H2-3NODE旧entry尚未修，当前不调用它出比较，不声称该第14项或完整Finding已经关闭。

直接读取CT05 `timing-selectors-132a-20261107.log`，SHA256 **`72e99e5fedbc2a8da4934d3514992ed7c9a39a8f0ebfa16691e3723bd0169026`**：gw-dms-test-05、15:15:40–15:16:18Z、起止完整132ac、28passed/0.47s、Ruff/mypy500、三项exit0。新增参数表以各场景真实嵌套结构调用实际evaluate，刻意区分整journey wall、可见及完成三个数，证明取READY；S2用0.008/0.009分辨同步可见字段。未运行真实业务、Compose或全量runner；正式计时、产品及镜像不变，不触发重建。

实际派生须逐项使用各自合格原场景及原版本/cache条件，保留run/state/SHA和工具来源；§101的107b数字只证明字段位置及错误选择的差别，mode=none的History不能替代H1健康缓存或H2/H3，继承W4 Preview也不改记为9704。不能把同一107b依次冠以13个场景标签。实际源与H2原state读取仍等FULL结束后的适当窗口，不因这次代码PASS新增业务重跑或把记录收口宣称完成。

**缺失计时拒绝用例复核PASS。** `464c037000eec37ff6f80cb11835e931ba617387` 相对132ac仅新增一个用例：原run有999s整旅程值但state缺所需operation timing时，实际evaluate抛TimingError，不静默回退。CT05 `timing-selectors-464c-20261107.log` SHA256 **`8517dc9dceb4f1e08252432b4a268abf3dc053ad2fbb74428498219258649694`**，15:23:01Z、完整464c起止、29passed/0.14s、focused_exit0。首次仅提交focused，审核要求对已改测试文件补当前候选backend静态，而非将132ac旧静态冒称464c实际结果；`timing-static-464c-20261107.log` SHA256 **`123e60bad8568e5515daa91bd0272a4e027e1bfb0175a30991db0b44b02d348f`**，15:24:01–02Z、完整464c起止、Ruff/mypy500及exit均0。两日志已直接只读核验；其余包不变沿既有来源，无install/业务/容器或全量runner重跑。本小修订关闭，H2第14项及逐场景实际派生仍未关闭。

## 112. 源W4历史数值派生核验成立，metric_source区分继承操作与外层证据版本

**来源标注工具 `2abcf55c0fbb33148880006ac2e8dd35ae279206` 的代码/必要验证PASS；4743.456s派生仅是旧e798 W4 Preview的历史观测，不升级该运行资格。** Owner A下源RS run-bound full identity仍UNAVAILABLE/source input only，不把此值写成9704实测、完整身份合格或carried。H2-3NODE参考及逐场景记录收口仍待办，当前资源不归继承Preview、none History不占H1/H2/H3。

为避免在途CT108取件，审核者只读复算§101 CT201已认证副本run/state、launch及resources四文件，仍与原SHA精确一致，并将已存路径交实施者经LAN到CT05。本审核又直接hash **CT05实际输入副本** `/home/dev/gdds-p6-logs/baseline/derived-inputs/p6w4resume970420261107b/run.json`（44967B，SHA `2f2197d6…37f07`）及state.json（39934136B，SHA `0281f0e0…5fc897`），精确等于§101原件；不只信派生JSON的自报值。独立解析原run/state，两者的v2-preview PASS行均为source_head=`e798ec87a37330250b0c051162e7962dba1daa60`、source_log=原p6bw4s4h120261105b/launch.log；repeat Submit为20cf原a，新Submit/History为3fd。当前顶层source_head/current_head不能替代这些逐操作来源。

464c初次派生 `w4-source-visible-464c.json`（906B）SHA **`159c8a77a47a63be64f18ec10c28868f6d2d86772875dd6a29213c0523d72fec`**、日志 `w4-source-timing-464c-20261107.log` SHA **`82b78498aef4ac2b0c74e44cfa7f50e6dd8ce9eee6d75ad58976db76588d1a17`** 均已独立核验，CT05 15:45:48Z、464c起止、exit0。数值及selector正确，但measurement.head只有外层3fd，单独引用有误归版本风险；旧文件保留，不改raw或覆盖结果。

最小修订只在state `/steps/<step>/…` 指针上，从已有对应PASS step_check附 `measurement.metric_source={step,head,log}`；保留measurement.head为外层run。缺来源显式为null，不推定run HEAD；来源非字符串则拒绝，不同PASS来源冲突也拒绝，同值重复不捏造新执行。首版ecc0未过滤state行的PASS，而原_validate_journey优先检查run行，审核直接指出后在2ab仅加PASS筛选；正常流程、正式采样/计时、所有数值/参考/policy均不变，不建立新证据状态机或读取旧源栈。现有用例以FAILED干扰行及两份冲突PASS验证不取错误来源，原正常及缺失字段拒绝用例保持。

CT05 `timing-provenance-ecc0-20261107.log` SHA **`0725eef38d78f92d89f392cbdb205bbd159888ab1ad3c5362867fb4d4e659601`**，15:48:15–16Z、完整ecc0起止、30passed/Ruff/mypy500全0；最终 `timing-provenance-2abc-20261107.log` SHA **`994ba48488d0ff50a0e9f1c99c215ae1a72f78d90f299b68a10cbf7633bcdb6a`**，15:50:16Z、完整2ab起止、30passed/0.14s、Ruff/mypy500及三项exit0，均直接只读核验。其余包不变关联原静态来源，不冒称本候选全量runner或carried。

新派生 `w4-source-visible-ecc0.json` 与 `w4-source-visible-2abc.json`（上述derived-inputs目录）本审核直接比较**逐字节相等**，各1109B、SHA256 **`f6357e4b4ec96c10680eb1a2e9b5bba1f298f99fd13f9dc6d91613c5ad7456d3`**；输入对应行本来就是PASS，所以过滤修订不改变该实际结果。新文件已先产生，均保留，不要求为同值再运行。各派生日志 `w4-source-timing-ecc0-20261107.log` SHA **`3e764ece1459ffdaf44bcee2ac40aacfdbfc9eea985c9c039daca68104c0e793`**（15:48:33–34Z）和 `w4-source-timing-2abc-20261107.log` SHA **`324c350c32f70f3fc5e639989a96f6adfe88e151a8d6fe92ad3fb8d0c99ba163`**（15:50:35Z）起止HEAD分别为各实际工具、exit0。结果取原v2-preview user_visible_seconds=4743.456、record_only、reference/deviation=null，metric_source精确指e798/原b，外层head仍3fd；reference_file_sha `7a688b10c8b39e3a097ce74eb069fb731264b68c51f59a1b8f628d24054b8e17` 与Git中464c原字节独立hash一致。

这关闭的是数值/来源派生小项，不是源W4身份资格或完整record验收。来源RS identity限制必须随条目/总索引保留；107b资源只覆盖新接续步骤，旧W4完整资源资料仍按其原来源处理，不填零或借当前资源。当前普通工具修订及必要后处理已直接与实施者闭环、设计已确认限制；无新重测/GO，不触正式产品或镜像，不访问在途CT108或SQLite，FULL继续原运行。

## 113. W4-FULL真实旅程及取证独审PASS，RS完整身份经原immutable ID后验链接闭合

**CT108 `p6w4full20261107a` 的本次fresh FULL旅程、数据/模式及取证审核PASS。** 运行HEAD为 **`18a4851d8c52d53afdb95ee4df9fae04e6e36d77`**，产品9704及冻结镜像不变；18/18 check均PASS且source_head均18a，没有继承步骤或人工恢复。此结论不等于S5/S6性能目标达标、04最终门禁或全部测量exit；STRESS及剩余诊断/记录继续原授权，无新GO或重跑本次旅程。

11:49:34.763–15:56:39.809Z、gw-dms-test，sampler elapsed **14824.959s**；journey run_result elapsed **14793.296s**，run本身11:49:36.448–15:56:33.811Z，三者端点不互换。controller、launcher、tee及journey均exit0，起止完整18a稳定。审核在旅程结束后将六份已关闭原件经LAN复制到 `/home/dev/gdds-p6-logs/p6-w4-full-review-20261107/p6w4full20261107a/`，逐份独立hash匹配：

| 文件 | bytes / SHA256 |
| --- | --- |
| launch.log | 2099684 / `b2daac6179bb68332db64a7cfd647081128d9c26b437061d9f477fe2b9e71674` |
| evidence/run.json | 33898 / `b03ab360ef8a9d5f02bb4c1951b69489abb6ea61afd2166f9ab728bd6560908d` |
| evidence/state.json | 87959612 / `41b090bfba3f2346ab19b4ffe9ca57a77656393bd59a47c23b25fd0d71f5fa3c` |
| resources.json | 6441 / `6eb25f987652dc3f31e14399a32ba2194191de70a5e323da72dd3068a28c1d6e` |
| resources.input-provenance.json | 2559 / `afaed3de2fb3cc1da3cffe50c8a168f6a456d0b84a51d57964fbf80e3010c5ad` |
| postflight.log | 697 / `c0ca191d7324825566adde6f2a44df27218376bb77c2068834478fd970bbac49` |

相应关闭preflight文件也已复制并核SHA：controller **`d282bd0c09395632638c38240de2dd6f05f2553fc1bfddf2a760b6af28170661`**，setup **`891189be37e61a85108fd19c5bb2bdb967be62be723bc428b9da6651340b8dca`**，start **`d83d89274e93329ef5dfa91bee2c3f26bdabb629c001ddcb2803322433bab12e`**，manifest-generation **`a0d8f3b8f1d75653fe53fdf3e8a5710fb4b70b8cce5bf00c59eac47c6380fedc`**。setup关联clean detached18a、已预置环境及native expected/installed tree584369相等；不把环境同步当测试。实际argv为§102/106所核full-v2/cold Preview/healthy History及70200s work，没有post-GC resume、v2 archive或v3步骤；17个before checkpoint与18个成功业务步骤准确对应。preflight manifest1924B、SHA **`ae0b281f224f5adabd801ee331e9022b42291399f983db42ef6dd69b2edc143a`**，census04952cb5；原件provenance四个上传角色/bytes/SHA全部MATCH，含FULL v2 INITIAL=v1 74974e5f及MODIFIED=W4 v2 4cb82a16，不拿2×普通v2包替代。

FULL v2 Preview的pair_count=2、table_count=1262、changed=628、failed/degraded=0；首次/重复v1分别631表全变/全未变。冷Preview缓存274项、expired/missing均0，清后0并删548文件。History开始前healthy缓存522项、TTL有效、expired/missing0、removed0，结束663项且expired/missing0。原summary通用键虽叫H1，这是FULL后首次History，不能改作普通H1零读零比证明；FULL例外允许重算变化表。History记录70634条，原bundle/fingerprint与旅程检查通过，不从此粗记录伪填DC63细段。

| 本次操作 | READY / user-visible s | completion s |
| --- | ---: | ---: |
| v1 Preview | 1711.256 | 1711.256 |
| v1 Submit | 1747.996 | 1748.008 |
| repeat v1 Preview | 1411.651 | 1411.651 |
| repeat Submit同步NO_CHANGE | 0.008 | 0.008 |
| FULL v2 Preview | **4007.919** | **4007.919** |
| v2 Submit | 3949.217 | **3949.229** |
| History | **1650.446** | **1650.446** |

v2 Submit journey step3952.126s不是上表API端点；prepare **3721.878947s**、submit_import0.301061s、await225.245225s，prepare约占completion94.24%。v1/v2各1 attempt、1 captured await session、3次healthy handoff、timing_complete=true、R5未耗尽且remaining2；Repository公共观察只给import耗时边界，不把await全段充作精确导入时间。History materialize788.533837、assemble855.498409、publish0.032048s，均attempt1。这些是当前实际口径，未作跨模式/版本加速归因。

镜像身份有一项实际记录遗漏并已按最小只读方法闭合。backend/worker在本次run记录config **66e362d4…8e62**及全部15有序DiffID，与冻结target逐项全等。fresh分支8612附近仅post_gc_resume才加入完整RS metadata，所以本次run未直接存11:49 RS config/DiffID；08:29旧loaded-image-identities虽MATCH但没存本机ID，不能伪造同ID关联。本审核核18a producer：fresh `start_three_container_stack` 用新project执行up --no-build；`_run_tier:5566` 在栈启动后、首operation之前按同一所选RS tag调用compose_image_ids，保存的images到最终summary原样输出（6628），不是尾部重新inspect。原summary实际记录RS本机ID **`sha256:a75aa535046937dab51156c8a8acad0deec913a4daaee9a930c4b62d23cc7e39`** 及9项labels；它是当时所选image对象的ID，不是独立保存的container.Image。

按本审核预核、设计确认的可信daemon/协作冻结tag模型，实施者在CT108空闲且持自有占用时，以**该原始immutable ID而非当前tag**调用18a既有 `_compose_repository_service_image_metadata`，16:13:38–42Z保存后验metadata。先核关闭launch SHA及固定identity文件SHA98bfba51，实际返回ID及labels与原summary相等，再对冻结target比较config **`sha256:b81faa1f970999676087a55f0fc63e17d4285fba73b04c5eca6a69612e1419aa`**、全部28有序DiffID和9labels，本审核独立比较亦全等。labels的build-input4497、source-tree319720、revision1f973保持。此处链接的是相同不可变image对象的内容身份，**不称11:49新快照、独立container.Image或跨节点inspect ID比较**，不扩Owner A的旧source输入例外；无重建/改tag/业务重测。

补证原目录 `/home/dev/gdds-p6-logs/baseline/preflight/p6w4full-postrun-immutable-20261107/` 三文件均已读取并复制到审核目录 `/home/dev/gdds-p6-logs/p6-baseline-evidence-review-20261107/full-rs-postrun/`：script **`9ab69a49d156d47d7b49a538f57489164278d44881c2dff3987306502761169e`**，result **`f06154343f34007adfb46f6badc631f239735e27196bb220a73661ee9926dc40`**，run **`fe426de17e672404e47984e892bb5e30105eb0afa96c8432cf291bd87988be4d`**。日志完整18a起止、gw-dms-test、exit0；helper inspect60/save600秒、外层660+5秒限界，实际约5秒。后续新run应在正常预检/producer记录三服务完整身份，避免同一fresh分支遗漏再需补链，不修改旧raw。

资源6762个离散样本，跨容器并发memory.current峰值 **25809965056B /24.04GiB**；各容器memory.peak之和 **26849656832B /25.01GiB** 是保守上界，不是并发峰值或单worker RSS。peak_parallel_cores2.969，temporary disk high-water10407845888B/9.69GiB。短同步步骤有0样本/空CPU/null memory，不能报告实际资源为0。postflight15:56:39Z project down、node检查、cleanup全0、锁释放，三个本项目卷保留；未删旧卷。down出现三条secret环境变量缺省warning，实际退出及静止检查仍0，不改写warning或据此重跑。当前是完整成功样本，不等于3分钟/10分钟等未来性能目标通过。审核只取关闭记录和独立读取原数据，未重跑测试/业务、打开SQLite或探测在途测量；实际只读补证由实施者在空闲节点完成。

## 114. H2-3NODE同operation参考及第14项selector修正闭合

**候选 `0cbf14f611ad0822c7603ef8870fb8740b67cc85` 的代码/必要验证及实际H2派生复核PASS。** 至此§111定位的14项actual selector及H2旧reference口径已修正；各场景完整JSON record/SHA/comparator收口仍另待完成，不将代码修正说成全台账交付。

原参考b96与目标e076的CT05实际副本已独立流式重算SHA并只读解析：b96 run=`98fa0c68…59b4`、state32318173B=`072a2f5a…e56b`；e076 run=`6861b30d…dd60`、state113034451B=`3d8b77e7…cf6e`，均与原S1c/H2登记相等，run/state exit0、失败step null、HEAD分别b96/e076。相应History PASS行也分别保留各原HEAD/log，两个输入包SHA/bytes均为原接受2×，不是W4。实际state同一 `/steps/history/result/operation_timing/completion_seconds` 分别为 **4892.584s**、**4886.678s**；原19361.157s只属于S1c整旅程，不能再作History参考。

_specs和提交JSON仅改H2-3NODE entry：actual从目标state同端点取；reference从b96原state、原SHA及同端点提取，compare/10% threshold保持。独立解析前后JSON只有此entry变，其他项不变；新参考文件原字节SHA **`1c4b3899183d0e2225e8b9ba444239728e11597401f56d7789ed38ba2ba4b272`** 与派生记载相等。新增测试刻意使READY=4000而完成=4886.678，证明取completion，并对齐_spec与JSON；fixture不校原source的限制由这次实际原件核验补足。

CT05 `timing-h2-0cbf-20261107.log` SHA **`0e0f48b1094ef650e1b278ba03229a527136bbe016ffa35d724aaba9040b25b3`**：16:10:06–08Z、gw-dms-test-05、完整0cbf起止、31passed/0.15s、Ruff/mypy500及focused/ruff/mypy/derived四项exit0。实际派生 `derived-inputs/h2-three-node-completion-0cbf.json` 1538B、SHA **`9555ba912211040490b6e00dea3fbd2ac65b5810da18b318428577cd7009f102`** 已独立读取并复制到审核目录h2/；原run/state SHA及metric_source准确保留e076/原三节点log，工具0cbf/CT05不冒充新测量版本/节点。

程序结果relative_deviation **0.0012071330814146472 /约0.1207%**，原偏差规则为“不需补测”。**这不是600s业务目标达标：4892.584/4886.678都超过该目标。** 设计已明确本轮是DC66参考基准，性能未达如实报告，Owner A已关闭场景不因抽取修正或旧跨版本差异机械重测/停整体，也不降低后续S5/S6目标。实际目录是 `ct108-independent-2x-20261104c`，原b路径不存在的只读find错误已留存incident SHA `70a3f3b32de433ba1f9bf5c95edae9f45e779cea60d93bbb2ddbaf0005896feb`；无产品/卷副作用，不另计业务失败或新GO。本轮未启动旧栈、访问旧卷或重新运行History。

## 115. 三组631表旁证独立核验通过，关闭§105实际对照待办

**2× core的v1/v2及H2三节点v3，对S1c vprime对应commit的三组完整表哈希均631/631 MATCH。** 这是复用已认证原最终summary的离线旁证，不是当前重新读取Dolt/复制卷；按Owner A保留bb348/e076/b96各原版本，不改记9704，不借W4不同输入替代。

CT05 `/home/dev/gdds-p6-logs/baseline/derived-631-20261107/` 的脚本 **`50ae08e9af1abcfd2942ca3dbc0b402018cf9859e64e0faa76123dba6aa60bf0`**、result **`088cfa885398c8882fcf6cfcb4f0b5665db793729cb89004370413565a69920b`**、run.log **`054be0f61c93aabc55f34ac9704a42e36f80dc73a3be6a2d4a8a283898fc6838`** 已直接读取、逐份hash并复制到审核者631/目录。16:08:26–27Z、gw-dms-test-05、脚本SHA在执行日志中相同、exit0；它是普通外置只读派生脚本，不称产品测试或权威runner。

审核逐行读脚本：认证三来源各log/run/state，共九原件SHA；检查唯一PASS最终summary及对应HEAD、t4、run/state exit/失败/check；两包恰为接受的74974e5f…/10652436B与121dc3b0…/10649536B。每张map必须631个非空表名及32位合法Dolt hash，随后比较**完整key集合和整个dict相等**，不只交集/计数；还核参考commit固定为原三值，输出实际目标commit。§105已核历史同一副本哈希helper/调用语义，本次不靠当前函数存在倒推历史执行。

本审核另直接只读CT05实际九原件，流式重算均匹配result登记，独立解析每份原log均恰有一份对应HEAD的PASS summary；source run/state也分别为bb348、e076、b96，无失败。原log SHA依次为core **`e0085bad1b9d4e3d1e6e3883e72e818be09933e5b720df02fd6a06eb891d086e`**、H2 **`853d373e22055e0a2932c3ea5a98a616a6151dddffb6029961665daf840d054c`**、vprime **`376a51af9b8e3dbb99c82616aee4097cd60de3fe11a8c8194f2ec9e6f4013bac`**。core state SHA **`503e73ab17b402c5abdb5a537701b818386bb999c65a267f5459de8ffc017898`**、run **`bf3a152818940541bbbcd5b50c4bc0c209b9033d5f6f584c741fac87c69aa18a`**；另两组run/state与§114相同。九条绝对原路径及完整摘要保存在已认证result，不修改原件。

| 对照 | 目标commit /来源HEAD | S1c参考commit /来源HEAD | 结果 |
| --- | --- | --- | --- |
| v1 | `081v3bk8jinfcnh5fosup8jabemtmnm2` /bb348 | `gc0j1d5316nui249o5d1petnncn8u881` /b96 | 631/631 MATCH |
| v2 | `i7vjr58lv5mjrqr83m8246utafgr5lng` /bb348 | `ej01n1u7srga41mdsqbht4lri82kl1mp` /b96 | 631/631 MATCH |
| v3 | `1juiuh4nnueo3aslmosqc8eqoqqu46h7` /e076 | `jlpa7e30svqudnem8uo40vrbf5j2upt6` /b96 | 631/631 MATCH |

独立读取原summary完整maps后，v1两侧的排序JSON摘要同为30ee5c63…70b9，v2同为fc6398f2…5959，v3同为30ee5c63…70b9；每侧均631。v3回退到v1因此同值是原场景序列，不省掉该组独立匹配，也不将S2直接复用S1当第四组证明。本次不触旧仓库、旧卷或启动旧栈，未重做原journey，结束§105实际对照缺口；其余STRESS/DC63/V5b/record/comparator/04及整体exit仍按原分工推进。

## 116. W4-STRESS真实准备复核PASS，1742已单次启动，结果待交

**§109的结构预审现已补齐本次真实manifest、三服务完整身份、最终argv/预算及节点预检，准备复核PASS；实际压力结果尚未完成。** 实施者按原授权于CT108 **2026-11-07 16:21:02.742Z** 启动唯一project `p6w4stress20261107a`，HEAD **`1742a8bcd62287fd9eb9fbd0a839615a470b2664`**。审核只读已关闭的小preflight文件及一次开放launch头部，实际解释器、manifest、root及子命令前缀与下述一致；未hash开放log、查询Docker/进程或启动探针，不修改/加时在途运行，也不提前判压力性能PASS。

真实manifest1711B、SHA256 **`cf288bdd321cedd846851d55d8f2276ecf1726f93b5758be87b00200ddf62830`**，profile=w4-100pct、root为接受的w4-generator-correction-20261105b/roots/w4-100pct，accepted summary SHA6b63cf2e…3896、census **`29c1e25c3925040fe3b9020354581ccbcb838377776034302a4223869f445fe6`**。三个上传均MODIFIED：v1及repeat-v1各74974e5f…/10652436B，v2为 **`c6f7c5e74f48715d2e33e9efe32a5679e913caccd8f93398f3ad4d1322eb4ec6`** /9173579B；scope=t4-v2-preview、full_v2/cross_project均false。它不是FULL的四角色或10%输入，压缩包大小不用于推断实际变化量/耗时。

preflight原目录 `/home/dev/gdds-p6-logs/baseline/preflight/p6w4stress20261107a-ct108/`，`check-input-images.py` SHA **`df11bd4a71c6c32cc25f82fa0d3dd4a28ce5be5966913f78980d04fe9bd3d98a`** 已逐行读：固定identity SHA98bf、manifest及已接受summary摘要，调用真实verify_before_run，要求真实100%/三角色，检查9704..1742差异只在benchmarks/tests/docs；各tag先解本机ID，再按该immutable ID调用原metadata helper，逐项比较config、全有序DiffID及labels，不只看计数。`input-images.json` 8543B SHA **`01cf16ea7882bb8ce89420617be8deafa359e20a334e3db4bf1590388e714d01`** 与脚本/原始输出相符：backend/worker同66e362d4 config及全部15DiffID、labels为空，RS同b81faa1f及28DiffID、9labels；三服务本机ID分别e803…/e803…/a75aa…。16:17:36–48Z完整1742起止、gw-dms-test、exit0，`input-images.log` SHA **`30001ecc68ae6955ff1755d8fca350ab8d447890508c93534aedbb0bf3751ab2`**。由FULL同节点给两个新tag加别名，未重建/改旧tag，不作跨节点inspect ID比较。

setup.log SHA **`456f30f661fc9e599841615acda0ddb8b57df546cdce7bac93a8627ebbff6400`**，16:14:52–16:15:19Z，源码通过从18a的增量bundle到clean1742、legacy链接及新project无资源检查，uv离线同步并强制重装Rust扩展，expected/installed584369一致；缓存使用本机预置，不把环境同步当测试。源节点缺5b对象的只读cat-file失败已保留incident SHA **`0c4febf4bbca3aca59c6c643223b9c5639ea0de2f0058059d96f56e83b1e54fe`**，改用已存在祖先18a的增量bundle SHA **`b3c7276cccf24cc0489cf2d569b5230fad2215e680b1e27470f2fb9efd6a6d9a`**，无产品/镜像/测试副作用，不增业务重做。

最终 `start-preflight.sh` SHA **`a5b7c553af3dbc2916b1c4b9a68268ec8e311aa6bef0b3b4add8a569697759ed`**、log SHA **`a95282bb9769690fd6e379dab3fe99c2b3bd6cf1b0c14af26174bebeffc3c9ef`** 已读：16:20:32Z，clean1742、同manifest/input-images SHA、三tag重新解析ID逐项与16:17完整metadata相等；自有锁在、docker无运行容器、8000无监听、Dolt/pytest/Cargo无进程，MemAvailable100314733KiB、TMPDIR/Docker各free152424856KiB，均过本次既定门槛，两路径的空间不能相加当双倍容量。这是当时现场事实，不是未来资源保证。

controller草案7f9d21…在启动前补unset NO_PROXY/no_proxy，最终2114B SHA **`71812d3312686bc1677d341e52fe9d8d04d369d2829202ea536eeb2edb50e900`** 已重新bash-n并被上述start-preflight记录；审核指出摘要变化后实施者明确了差异与实际执行版本，旧摘要只作准备历史。最终controller离线/无proxy、固定ROOT/project/RS tag、cold Preview/history none、非FULL，13 before checkpoint正好结束v2-preview，不调用v2 Submit/History，不另套较短timeout。原既有launcher提供独立session/watchdog/保卷down/postflight/条件解锁；实际launch头部为 `timeout --foreground --signal=INT --kill-after=1200s 106200s` 加本worktree字面Python。

本次将§109示例明确固定为工作保护：v2 Preview64800s，prefix12887/4047/11271/3600，aux9000仅规划量，work106200/watch107420/hard108000、清理1800，配置等待闭包107673<108000。FULL实际prefix约4870.923s、10% FULL v2 Preview4007.919s只提供量级；100%成本未知，不按10×机械当承诺、不是30h ETA，也不保证所有局部HTTP/I/O先天足够。实施者当前低置信实际剩余估计10–28h、未超过48h；不把各保护上限相加替代实际估计，若实际重估超过48h仍按原Owner规则处理。当前scope没有恢复入口，若真实失败按原DC80定位后最小修订，不能为绕过校验切full而额外跑Submit/History。

准备与实际启动事实已直接交实施者并同步设计，无新GO。之后本审核不在测量中读取大文件或做新探针；利用已认证CT201副本和独立节点继续记录/04准备，DC63/V5b实际链仍待CT108空闲。正式压力结果、完整record/comparator及04/整体exit均未由本节提前结案。

## 117. 非在途工具集成及五项实际时间派生通过；单run多版本record边界已明确

**独立集成 `a55414c827a488758beba8c788cb15e940734180` 的本轮合并代码/必要验证PASS，尚非最终V_ref或04结果。** 两父为已审0cbf及在途1742；独立读Git对象，timing三个文件精确等于0cbf，9704..集成仅docs/benchmarks/tests，无业务src/锁/部署/诊断Compose；未合当前main或改在途worktree。CT05 `vref-integration-a554-20261107.log` SHA **`bbba3415ef1775742b7443be29a85226a9a8f84d53438b99621b940a414390d6`** 已直接核：16:25:20–16:26:11Z、gw-dms-test-05、完整a554起止、57focused/10.78s、profile2passed/1.54s、backend Ruff/mypy500及bash-n全0。其余包静态仍沿既有未变来源，不称此HEAD全六包runner或新镜像门禁。

0cbf在CT05对已认证bb348原run/state派生四项READY/同步值，本审核直接核原state字段与各实际JSON相等，源SHA与§115九原件重算相同，metric_source均bb348及原core journey：

| 派生（derived-core-operations-0cbf/） | 秒 | JSON SHA256 |
| --- | ---: | --- |
| W1.json | 1719.244 | `ced3b3ef91c1d831db29659ed874bb4bd1def69a8bf1800ec6c369ea8f01a844` |
| W2.json | 1413.672 | `768df02da2d82cf41351dadd0a7c7a97e9bc56a8f95856b673d13bffe06bcdec` |
| W3.json | 3332.207 | `4e898f8ea20319cb062e1735dc35b6a5912719736222cf79f94df2b9ce09bbe3` |
| S2.json | 0.008 | `db707e1ef3853c8754d485ee59a1725918b47c965eaec1efa04c52a807ab32fb` |

run.log SHA **`f3c6c9a0f8cdefe18724b03b2cc688221f939a1de0540b178dc389cab5916e85`**，16:22:48–49Z、完整0cbf起止、四次及总exit0。均record_only、reference/deviation null；前三者不满足DC53未来目标，如实保留，不据此机械重跑已关闭参考样本。这里是单一时间派生，不声称已完成标准record或资源/所有计数。

FULL的run/state从审核者已认证CT201副本经LAN到CT05，本审核独立hash实际CT05副本再次精确等于§113（run33898B、state87959612B），没有读取在途CT108大文件。`derived-inputs/p6w4full20261107a/w4full-visible-0cbf.json` 1101B、SHA **`f25c08a52e127e115f495321a3ace181a26edb111919e6b76b017a31f9804d38`**，取4007.919s、record_only，metric_source=18a自身v2-preview，输入run/state及reference文件SHA准确。日志 `w4full-visible-0cbf-20261107.log` SHA **`c194b5643c1f662bad7bcb7af605ff2054fd3903744400f7904cf30965938558`**，16:23:37–38Z、0cbf起止、exit0；数值与§113原数据一致，不重复测量。

记录组织按Owner A使用**每个真实run/版本各一份标准record，再加普通外部索引**：run.head/六个product_tree_ids取其实际测量HEAD对应Git对象，工具HEAD另列，不把bb348/e076/18a等装成统一9704。builder已支持单数journey/resource，DC66单次无需伪造四份warmup/repetition；单样本统计不能宣传三次稳定性。索引列场景、record路径/SHA、真实版本、原始来源/输入/cache条件和限制，继承W4仅保留§112受限历史数值，不拼107b资源；缺原件先留缺项，不以旧失败摘要重造run/state。当前CT201并无其余W3-FULL/H1-FULL、H1-REFILL、H2两节点/H3完整认证副本；另一个旧input-summary SHA c31c18f6与已接受6b63不同，未当替代输入。实施者随后在CT05找到551463B、SHA **`6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896`** 原接受summary，本审核直接核字节及结构，可继续合法派生，不必等CT108取该文件。

现comparator即使--scenario也比较**全inputs对象**，随后比较指定scenario的fingerprint/count/state，忽略run.head与product_tree_ids以允许真实版本比较；它明确返回timing_comparison=not_compared。实际replay只作语义/结构一致性，不能作性能达标/加速证明，不弱化输入检查或把不同缓存条件强比；source完整身份/资源等在索引说明，不向严格record schema塞未建模字段。这些是既有consumer的实际边界，方向已直接反馈实施者，无新框架/GO。

## 118. 标准record的Preview worker步骤缺采及H1条件缺口已定位，补证待独占窗口

**W4-FULL标准record尚未生成；阻塞是旧collector漏采Preview worker步骤，不是FULL业务失败或原API计时失效。** CT05 a554用认证FULL launch/resources及6b63输入准备metadata成功，但builder exit2：`W4-FULL has no worker step timings for v2_preview`。原 `record-w4full-20261107/run.log` SHA **`28a2fef69a31f9b81aff36d9c05cf04c3193d281aaf131b83ca01bb84064e380`**、metadata SHA **`4460fd4f9f249ba411f78603ed6d7c6cbcc7c8204eee81e6f39af83fbf23cfac`** 均已直接读取；16:31:45Z、完整a554起止、metadata_exit0/record_exit2，失败保留不改写成功。metadata的输入五字段取原接受summary，包SHA/bytes与FULL四角色对应；六tree从实际18a Git对象取，不是当前工具工作树。

实际根因是 `_run_tier` 的record_operation_timing只从value.operation_timing.operation_id找ID，Preview producer的ID在value.result.operation_id。这个接口错位与§109 coverage曾犯的是同类问题，但此处是真实旅程另一个consumer；bb348及e076原final summary也没有Preview worker步骤。Submit与History的timing原本含ID、S2同步无operation，现有记录不因此抹去。已直接交实施者最小修未来非在途collector并覆盖真实producer→consumer，不改_preview返回形状、建别名、改时钟或触1742在途运行；修订及验证尚待交付。

历史优先从**同次原控制库快照**补真实DB步骤：FULL before-v2-submit已在Preview完成后保存；bb348 core在History前也有checkpoint（completed_through=v2-approve），control快照2150400B/1文件、原volume digest **`4baede398e55e77569836c0b51c98d1edd6b7aab6451b7cbb7d9793ff6d1aad4`**，artifact快照1043552482B/12168文件、digest **`0204887939ccff4e532fb4ba9b8157830c7a47758b68ea6e52cbe8117d84e357`**。源路径由已认证state.checkpoints.history.volume_snapshots固定，正式压力结束后合并一次必要小副本取证，在CT05的**私有复制件**开SQLite，按原SQL/UTC端点和原operation ID取同run步骤、绑定原state/快照摘要；不打开原SQLite造成WAL/SHM，不启动旧栈、取RS大卷、重跑业务或把诊断executor span拼入正式步骤。确实不能恢复时才列明确UNAVAILABLE并与设计限定record资格，不为出JSON先弱化原步骤要求/填0。设计已确认这一路径，无新Owner/GO。

另一个实际派生边界已指出：_sample_scenario缺step_resources时的全run资源fallback不能当单operation指标；FULL S2等0样本下的空CPU/cores0/disk0也不证明实际资源为0。应在既有record的nullable统计及unavailable原因中保留缺观测，coarse全run资源只留原run/索引，不改sampler/raw或构建新资源证明机制。此项最小修订尚待交付，不能把它与有原DB可补的worker步骤混成同一“缺计时”。

H1也需补既有条件证据，暂不将core History自动签为健康H1。DC38明确H1为**普通Preview/Submit之后的相邻首查**，H3是TTL内重复查询，不能互换。独立读bb348原argv未指定history_cache_mode，raw H1 cache_condition/cache_after及tier condition均null；W2在06:16记录274缓存项、TTL有效、无expired/missing，这不直接等于07:36:37.516Z History起点的健康证明。原before-History control/artifact快照可在上述同一空闲窗口按**历史起点UTC**核规则/TTL/相关缓存对象，不能用今天TTL判断旧时失效、改历史none为healthy或重跑首查。H1原API 2426.267s可保留为未补条件的历史观测，角色资格待这项核验；若源确实不足再给设计明确缺项/选择，不暂停STRESS等独立工作。当前以上均为已定位的记录/条件补证任务，标准record/comparator和整体exit仍未完成。

## 119. 未来Preview worker采集及资源缺观测表达修订复核PASS，旧证据补取仍待

**非在途集成线的 `2b6b947dfed785d28ad672ee65e0b5b9891d9dec` Preview ID修订，以及最终 `fcc827aec2750b2cc6d36c241c40de7415c7a1ea` 资源表达修订，代码/必要验证PASS。** 只改benchmarks/tests，不改产品、时钟、采样、原始记录或在途1742；不是已经修复旧raw、生成完整标准record、最终V_ref冻结或04通过。

2b新增小helper按明确operation角色取ID：Preview取真实result.operation_id，其余Submit/History保原timing.operation_id，类型为非空str才收；同步NO_CANONICAL_CHANGE没有op，不伪造。真实record_operation_timing将该ID放入原operation_ids；各partial/full return的capture均读取同一集合，未发现压力scope过滤遗漏或只改孤立helper而消费者未接入。单个focused实际调用原_preview和HTTP MockTransport，生成result有ID而timing没有ID的真实形状，再核实际消费helper；同时核Submit/History及S2路径。CT05 `vref-preview-2b6b-focused-20261107.log` SHA **`4296ac4f932dbce9f02f74f7f8df588af781c10c76847a8ffada034e9aad3d74`**，16:38:48–49Z、完整2b起止、1passed/0.83s；`vref-preview-2b6b-static-20261107.log` SHA **`b723f66369356fb239ba7fac45af19600fce292fc9cf55917fc095055007ca07`**，16:39:03–04Z、Ruff/mypy500及exit0，均已直接核验。必要覆盖足够，不要求为这处元数据采集重跑业务；旧worker数据仍按§118原快照补证。

资源修订删除operation记录对全run峰值的fallback：只有对应step_resources确有正整数samples时，才取该步骤的cores/memory/disk高水位，否则三者统计为null并在counts.unavailable.operation_resource_peaks说明缺周期样本。full-journey场景原本的整程资源不因本修订改作单操作，sampler原始数据不变。

**审核者前次“缺周期样本则CPU也null”的泛化已纠正。** 独立追源表明原record CPU来自journey step_metrics的三服务起止cgroup计数，不是periodic sampler或全run CPU。真实FULL S2虽周期samples=0，但原step有7284/802/1923µs增量、记录的舍入CPU分别0.007/0.001/0.002s；这些是已观测的步骤边界值，不能因周期没碰到该短步骤就丢弃，也不将其充作精确API窗口CPU。650ac首版曾一并清空CPU，其8项通过不能证明语义正确；本审核直接收窄要求，fcc仅删除该清空并将unavailable限定为周期峰值，保留原完整CPU/缺失或reset为null的规则，不读global resource替代。

CT05 `vref-resource-650a-20261107.log` SHA **`c07187baac8d282d6702b0c398b9c959861a5cb034e2c6f3627ec71fb448d9a2`**（16:40:32–33Z）按准备历史保留；最终 `vref-resource-fcc8-20261107.log` SHA **`8a457f06f09d3aa89444e5ace89485c314ddf8b8c62f04ab56c33d80a7957251`**，16:44:18–19Z、完整fcc起止、8passed/0.12s、Ruff/mypy500、exit0，已直接核验。测试用缺step资源与零周期样本两种情况证明峰值不回退，同时独立完整CPU仍为6.0；已有单字段缺失统计不默默删除样本的用例保持。其余四包无变化关联既有来源，不称本轮全量runner/carried。

两项工具Finding现关闭；数据层面§118历史worker步骤、H1缓存条件及其他原件尚待合并补证，不能把未来采集路径修好当作旧数据已存在。05可继续原版本record准备、04可按既定分工准备最终身份/缓存，冻结前集中完成必要工具，避免测中修改04 worktree；不触CT108在途STRESS、原镜像或旧source，无新Owner/GO。

**FULL预制DB来源索引核对通过，仅为PREPARED_ONLY。** CT05 `record-w4full-20261107/source-index-prepared.json` 961B、SHA **`91b27a331459459379b8c821fe9c92416b65b11400bcdb22167e3ba5b5e3e830`** 已独立读取，与审核者§113认证state副本逐项相符：18a、state SHA41b090bf、v2-submit before checkpoint且completed_through=v2-preview、原control路径、tree3854336B/1文件/SHA **`05577662288d708a673eeb40fe219668550fe5f764d6f03dca909f9c47eddfed`**，三个Preview ID分别来自各自真实result。没有访问CT108快照或断言其当前存在/DB行已取到；树摘要不是单一SQLite文件SHA，后续按原树摘要核复制件并另记实际DB文件摘要。原快照及同次步骤补证仍待压力结束后的空闲窗口，本核对不新增GO或允许改原source。

core配套 `derived-core-operations-0cbf/source-index-prepared.json` 1356B、SHA **`11ef88f4a5c01849068a21cad9a9edbd72dac6f59ffe99e35ec3671ba6540fec`** 也已直接读取，与再次核SHA503e73ab的原state逐项相同：bb348、history before checkpoint完成至v2-approve，control/artifact路径及4baede/020488树摘要、bytes/count均与§118一致，三个Preview ID来自该次真实result。仅确认准备来源映射，不表示已读原快照、worker数据已恢复或H1缓存合格；原件补取窗口及限制同上。

## 120. 04待门禁候选及本机离线RS构建路径已核，实际镜像和runner结果待交

**`fcc827aec2750b2cc6d36c241c40de7415c7a1ea` 可作为本冻结参考线的04待门禁工具候选，尚非04通过或整体exit。** 本审核再次只读确认独立集成worktree HEAD精确等于该提交且clean；9704..fcc为18个docs/benchmarks/tests文件、2006增/979删，diff-check通过，没有产品src、依赖锁、部署或诊断Compose变更。各组件必要验证见§117/119，不能用其代替当前候选权威runner。§118历史补证与记录派生仍使用外部来源索引/派生输入，不改原raw或在途STRESS。

04的Repository Service镜像须在backend闭包计算之前固定到候选身份。独立核两套现有harness：backend只核build-input/source-tree，而Repository Service另要求candidate revision及uv-lock。因此若backend先记录旧revision镜像、随后RS门禁才重建同tag，会改变同节点闭包；已直接交实施者先构建并核新tag的revision=fcc，再开始backend manifest/runner，期间不手工改tag。当前候选官方identity的build-input为4497ded8ff3a9156bbe4c7a75ba44ae9e4675792、source-tree为sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027、uv-lock为6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11；实际新镜像完整身份仍待构建产物核验。

最初尝试SSH旧开发地址10.10.60.4超时，不能据此把构建/测试改到任意节点。本机heavy-dev-01与既有CT201构建及LAN传输记录一致，但实施者随后在04找到原保留dependency-base，无需开发节点新构建或传输。本审核先BatchMode确认04，再只读核hostname=gw-dms-test-04及tag `gateway-p2r1-repository:lock-6dc9659f0aee`：本机ID **`sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f`**，uv-lock label精确等于上述完整锁摘要。此为04本机ID，不充作跨节点config digest。

独立读fcc的官方build脚本和Dockerfile，预置base存在且lock label相等即走USE_PRELOADED_DEPENDENCIES=1分支；已同意实施者在04 clean detached fcc上用该入口、UV_OFFLINE=1及network=none构建新RS tag，按原规则记录base来源及实际完整config digest、有序全部DiffID、身份labels和04本机ID。缓存缺失仍停该步骤，不走公网；不另起重复CT201构建，也不触CT108在途镜像或测量。此处只确认已存在的离线路径与候选准备，未执行测试、构建或假称镜像/runner已通过，无新增Owner/设计/审核GO。

**04实际RS构建及完整身份现已复核PASS，权威runner仍未由本节判定。** 源证据目录 `/home/dev/gdds-p6-logs/baseline/preflight/p6-vref-fcc827-ct04/`，审核者BatchMode确认后直接读全preflight/build/identity，六份小原件经LAN存入CT201 `p6-baseline-evidence-review-20261107/ct04-rs-fcc827/` 并逐份重算SHA相同。build-preflight.json 3147B、SHA **`597e0114a8a8f09b4e873e4fbd86b040eace6f359592f554c267d5eaa0fd1367`** 固定04、clean fcc、新tag此前不存在、lock匹配的base及离线/network=none；build.log 5226B、SHA **`94a1a486609daf7ddff71f980acb45425e61ea0933b3cccb77c216c414d8b3b7`** 记录18:32:33–37Z、fcc起止、官方入口实际走保留base分支、版本/uv pip check和五锁检查通过、exit0，未运行测试或业务。

最终image-identity.json 4758B、SHA **`26aeb529cb65ef1863cbf260c363ff2371df323befd29205e4393e7856009111`** 绑定新tag `p6vref-fcc827-repository-service:latest`，config digest **`sha256:4bae0e8e09191e90502e16f82c89ab568d45ef035d2fb4eb1841eace3f4b2a4e`**、28个有序RootFS DiffID，以及04 containerd本机ID **`sha256:368c4295355fcc7840865c31da0c768ebcd494d601a1178710d0cddef6fc35d9`**。四个候选身份labels与本节预期精确相等，其余版本labels完整保留。审核者在04独立重读660680192B docker-save归档并重算完整SHA **`5e2ac2b9b882bf69e77116ef1befe78a4b4d138ee903eb70d31114a499cc7d30`**，由tar manifest所指真实config字节另算config SHA，逐项比较全部有序DiffID/labels，再与当下tag的本机ID、RootFS和labels比较，均MATCH；再次确认对应detached worktree HEAD=fcc且clean。archive-identity.json SHA **`28d4c2f590425560e6613013fc05d0b318b26e2ccb1b26e6650c999ddbfadbeb`** 与最终JSON引用相同，不只采用实施者自报MATCH。

首次inspect派生曾把containerd本机manifest-list ID写成config digest；原 `image-identity-inspect-attempt1.json` SHA **`b1639e94ca476c691d175c37afecf15968e701195b05bfc17195dded9c7a6473`** 保留且被最终JSON明确supersede，未冒称首版正确。后续只读归档纠正，未重建镜像或重跑业务；两种digest在本结论中严格分开。已直接通知实施者可沿原授权继续backend manifest/最终门禁，另提醒旧backend-only失败的RS host .venv前提须在runner前实际准备；不新增测试轮次或GO。本PASS不把新04镜像替换为CT108正式测量镜像，STRESS及旧快照均未触碰。

## 121. CT201 backend/worker预构建两次自身命令失败，留证并沿普通准备授权最小修正

**停止原错误命令、保留两次失败是正确的，但本次普通构建准备不应再次等待Owner。** 本节初稿提交8acf8595de曾机械套用旧DC68次数限制并要求停该步骤等Owner，属审核判断错误，现明确更正。已直接重核[接续计划“普通准备命令与派生日志封口”](p6-baseline-post-gc-resume-plan.md)及Owner连续完成授权，并与本报告§88/97的已核c58授权交叉一致：低风险准备命令留证、查因、最小修正后直接继续，不按累计次数再等Owner；此前失败事实不撤销、不重置或删除。已立即撤回对实施者的等待要求，普通包装修复沿原授权接续，无新GO。04 RS身份PASS及在途CT108压力保持，实际产品/身份/输入/资源异常与权威runner失败规则不放宽。

本审核直接读并重算CT201 `/home/dev/gdds-p6-logs/baseline/preflight/p6-vref-fcc827-ct201/` 原件：18:50:47Z的backend-worker-build-preflight-final.log 283B、SHA **`d0fa892dee3ac4be79dde17705f701a578b91894bb4437ba24bc155e45ede1a2`** 在clean fcc上因当前vnext/目录内再引用vnext/backend/Dockerfile报No such file；18:51:24Z的backend-worker-build-preflight-corrected.log 961B、SHA **`3235bf319ab6a506d2e1e349e8157f72d6242388a2c765f78eddeadce905693e`** 已核正确路径、候选vnext tree f7cee1856bb6927bf53faede412eb90833690e5d、两base镜像及候选两tag不存在、proxy变量未设。后续包装命令又在Bash解析阶段失败，实施者落盘backend-worker-build-launch-error-20261107.log 763B、SHA **`a15d12db62ee00bbe132299219e73a4661fc3c3a345bf47bc709ca4f2413cdcb`**，记unexpected EOF while looking for matching单引号，attempt=2、Docker build未开始。该文件是失败整理记录，不冒充完整原始stderr或已独立定位具体引号源行；已要求交原包装命令/脚本和原失败输出。

审核者另外只读当前CT201 Docker元数据，p6vref-fcc827-gate-backend:latest与p6vref-fcc827-gate-worker:latest均返回No such image，与未产出候选镜像相符；没有执行build、tag或测试。建议修正固定工作目录/绝对路径，并把原构建命令保存为独立脚本文件，移除多层嵌套引号的-c包装，交可审文本及必要语法结果以验证具体修正；精确候选、Dockerfile、完整vnext context、既有pre-exit整镜像流程和输出新tag不变。此核验不成为新的摘要/GO前置，具体修正成立即可沿原授权构建。设计协调者已指出适用条款，审核者亦独立核原文并完成上述纠正；STRESS原运行及其他独立取证准备继续，旧卷/证据不清理，最终04 runner尚未启动。

**落盘包装的具体修正已复核PASS，可直接恢复本次构建。** `backend-worker-prebuild.sh` 5174B、SHA **`fc16f7bbab80186f66e1db78d21e7f4e5cf0abcd34dbe8f71e2a1c46bed09736`** 已逐行独立读取并在CT201以bash-n检查exit0；这是构建准备的语法核验，未执行build或产品测试。脚本先固定候选repo root并核HEAD/tree/clean及四输入文件SHA，再在repo/vnext中使用backend/Dockerfile和完整点目录context；无原多层-c包装。实际命令为CT201 docker build、network=host、新backend tag，成功后把同一image tag为新worker；记录build/tag退出码、本机ID、起止时间/HEAD及结束clean，失败不接续。现有base和未设代理的原构建输入/流程保持，不套main后续dependency-base流程。

18:58:49Z实际preflight日志 `backend-worker-build-script-preflight.log` 1244B、SHA **`41924d09c46f247d6f4282c743400e9badd55cb2df9ad7a41d2505a8e2b42666`**，固定heavy-dev-01、default context/overlay2 daemon、两精确base ID、无代理及候选tag不存在。本审核独立重读候选Git HEAD/tree/clean及Dockerfile/.dockerignore/backend uv.lock/Cargo.lock四SHA，与日志精确一致；再读Docker确认两新tag仍无、实际build日志尚未创建。已立即通知实施者按Owner既有授权只恢复该已修正脚本的build模式一次，实际产物/归档完整身份另交结果复核；没有宣称B/W构建、04 runner或整个基准完成，亦无新Owner/设计GO。

**随后CT201实际backend/worker构建及源归档身份复核PASS。** `backend-worker-build-script.log` 9925B、SHA **`c2757f0410417d47a7b69345c7953ebfac7c0e1577a3ebdd4ca5dba92dc30209`** 记录19:01:40–19:03:01Z、heavy-dev-01、fcc起点、完整vnext context和上述Dockerfile、实际build与tag各exit0、结束HEAD断言及clean通过；日志中只有镜像依赖准备/编译，没有产品测试。CT201按原许可取构建所需制品，不代表测试节点可联网。审核者再次独立读Git HEAD/tree/status，仍为精确fcc/f7cee185且clean。

19:04:18–20Z docker-save exit0，源归档397096448B，SHA **`7b3771afb7409eb313de15c97c25017e5bceeef2d085eac69f914e92cc66aa4f`**；`backend-worker-image-identity.json` 3136B、SHA **`2796f44dd7bbdfbace2dbf63444ab5e3aa2841396faa1d783956f8b582d73c78`**。审核者独立重算整个tar的SHA，从manifest分别解析backend/worker实际config字节，各得 **`sha256:ab2f029188ebdad5e6942e59f3d4b8427b20d12c948361a587e54cfb52931d24`**，逐项比较全部15个有序RootFS DiffID及空labels，两tag完全相同且与当前源daemon inspect一致。此源daemon为overlay2，恰好本机ID等于config digest；不能将此事实套到04 containerd或作跨节点ID比较。已直接通知实施者可LAN传04/load，比较config/全部有序DiffID/labels并另记04本机ID；04加载身份及runner结果仍待，不更换CT108冻结测量镜像。

metadata helper不支持--help的自有命令失败亦保留：`archive-identity-help-command-failure.log` 309B、SHA **`21318eba7cf501cc691850e51b2b0b476a6980021196c13887c3e8ab688fc95b`**；按其既有位置参数archive/output提取后成功，实际helper日志SHA **`0c27fa4794690351d334bd297cc6a96d90e89dbd54eed221958279db2bf93b76`**、save日志SHA **`8e2214fbbbf2f4b3ab0326558c5c86d3e398a383690b6fb25c4769b11dbd85ac`** 均已直接核验。该准备纠正未重建镜像、运行测试或业务，无新GO。

## 122. 04 backend/worker加载后的完整身份独审PASS，最终runner待结果

**04加载及round-trip完整镜像身份PASS；可沿原授权继续该V_ref的最终权威runner，无新GO。** 这只关闭镜像准备，不等于测试已开始/通过、完整record已生成或整体exit。源仍是§121的clean fcc CT201构建，目标仅04新tag，不触CT108冻结测量镜像或在途STRESS。

直接读取CT201 transfer日志753B、SHA **`7b72a20fe44eb8aa30c5718a28b047b01a104e8c1ba64b9b5b30d4612f3a7109`**：19:06:24–28Z、SCP经批准LAN到04，397096448B归档目标SHA等于源7b3771af；04 load日志704B、SHA **`9ecbb6cf649162ae3de87492ff6f2ba1fdf781bef4903c74b71800b0b1b5370b`**，19:07:12–16Z、原两tag不存在、load exit0。04两tag本机ID均 **`sha256:0b84061f0976b2be8451d96f8288949b058096428340abed4bf28d88233dbd29`**，与CT201 ID不同是containerd store的正常本机manifest身份，不判作跨节点失配。

目标 `backend-worker-target-image-identity.json` 3177B、SHA **`fa0ad4cf1cb5ae6b551050dc7c2c19a71249497cdb28ef48a37f76cf8187224d`**；04 round-trip tar397075456B、SHA **`9b1b178806cdea3aae6a70e882879e9a43b7764aae0fd718301e7d3943b7ff55`**。审核者BatchMode后在04独立重算整个目标tar SHA，由manifest解析两tag的实际config字节，各得源config **`sha256:ab2f029188ebdad5e6942e59f3d4b8427b20d12c948361a587e54cfb52931d24`**；全部15个有序DiffID与空labels，逐项精确等于已核源JSON和当前04 inspect，两个tag也相同。04收到的源JSON完整SHA仍为2796f44d…73c78，不只信helper的source_identity_match=true；两份save tar的封装SHA不同不影响这些已逐项相等的镜像身份。save/helper日志SHA分别为 **`c046790900107ef6610e9d5dd99f0712d58906dce1f037c87b6e6f769aa92576`** / **`b1e864b8dd1b647c54ec5a3497605d4e17e6f3c9dc052965307513ef9747bd14`**，闭合小原件已LAN存CT201 `p6-baseline-evidence-review-20261107/ct04-bw-fcc827/` 并逐份核SHA相同。

同时独立只读确认RS当前tag的本机ID、全部28层及全部labels仍等于§120，04对应worktree仍为clean fcc；runner期间不得手工改tag/写worktree。实际RS host环境已离线同步、辅助Python可用，sync日志SHA **`5515b35f593a19139cb52bd029d3f937a054344c84114f33a490745d8073871d`**、起止fcc/lock稳定/exit0，旧backend-only缺RS环境前提已处理。rust-toolchain-preflight日志SHA **`6de9c115eb38df1cd7809be427f8fe7aac7c1f0b7dae4920754535ec6f445769`** 在vnext/rust按selector确认1.97及cargo/rustfmt/clippy同工具链；先前repo根目录因没有全局default而报错的原日志SHA da158f19…24c9保留，不能将其当作selector目录缺缓存或擅装default。已直接告实施者继续原离线、legacy、TMPDIR、取锁及起止HEAD/exit规则；本节未运行测试或获取在途CT108状态。

## 123. 04最终六包runner已实际启动，启动记录与后取占用标记已核

**04于2026-11-07 19:19:37Z在clean fcc启动本次全六包权威runner，结果待运行结束。** 审核者只读外部日志header和status，直接确认gw-dms-test-04、准确HEAD、./vnext/scripts/run-tests.sh、packages=all-six、TMPDIR=/home/dev/gdds-test-tmp、UV_OFFLINE=1/CARGO_NET_OFFLINE=true、旧产品线prebuilt开关、项目p6vref-fcc827-gate、已核RS tag及B/W本机ID。日志/状态位于04 `/home/dev/gdds-p6-logs/baseline/runners/p6vref-fcc827-ct04-20261107T1914Z/`；目录标签1914不冒充实际启动时刻。没有hash尚未封口的run-tests.log或认定任何最终包结果。

已直接读04外置 `run-full-gate.sh` 3581B、SHA **`532de75ce315923bdb6c3b075bfe211bb7742c1bdab17760fd4f97405544792d`**：拒绝覆盖旧日志、核准确clean HEAD及主机前提、设置上述离线/项目/env、清Rustup/Cargo home覆盖与全部代理，选包变量unset使权威入口运行全六包；最终trap将另记end HEAD/clean/runner真实exit和完整日志SHA。本次runner中不改worktree或镜像tag，不能拿header替代尚未产生的结束信息。

CT201保存的04 `full-run-preflight-corrected.log` 1780B、SHA **`15d4acdb928a969ff2d40e73227e0fc9eae721baacc4fdbd91150c4befa24664`** 已独立读全并hash：19:14:18Z、准确clean fcc，legacy符号链接、TMPDIR与RS host .venv可用，无Dolt/pytest/cargo/Compose冲突进程且8000空闲、三镜像为已核本机ID；PATH前缀正确、Rustup/Cargo home变量unset，selector目录四工具同1.97；all-six、无代理、preflight/SSH exit0。先前路径错误的准备记录保留，修正后沿Owner普通准备授权接续，不新增GO。

**占用标记是启动后补取，未倒填。** 审核读wrapper发现只检查busy目录不存在而未mkdir，遂要求实施者按现有节点协调方式补记，不中断在途测试或改worktree/tag。`node-busy-marker-acquisition.log` 447B、SHA **`bb185c48a3926f3795bc1d46c170bc3172d9794f6b5d87ff4377484ff47b04b0`** 已独立核，且只读04实际session.txt内容一致：session=p6vref-fcc827-ct04-final-gate、runner PID1245677、runner_started_at=19:19:37Z、marker_acquired_at=19:23:20Z，明确后取。本节不将后取记录当作启动前已持锁的证明；已通知结束时按session所有权及postflight仅清自有marker。当前只是启动与协调补记核验，不宣称runner/整体exit，也未干预CT108在途STRESS。

## 124. W4-STRESS真实旅程与取证独审PASS，100%压力Preview已完成

**CT108 `p6w4stress20261107a` 的本次fresh压力旅程及取证独审PASS。** 工具HEAD **`1742a8bcd62287fd9eb9fbd0a839615a470b2664`**、产品9704、§116冻结三镜像及输入保持；14/14 step check均为本run/同1742来源，没有继承或恢复，13个before checkpoint与既定清单相同。实际scope=t4-v2-preview、MODIFIED_ONLY、full_v2/cross_project均false、cold Preview；没有执行v2 Submit或History。此结论关闭压力样本的实际旅程/取证，不宣称性能目标、全部标准record、04门禁或整体exit通过，无需重跑STRESS或新GO。

审核先在已结束节点直接读小原件与closed controller，再将下列六份闭合原件及小preflight资料经LAN只读取到CT201 `/home/dev/gdds-p6-logs/p6-w4-stress-review-20261107/p6w4stress20261107a/`，逐份独立hash；此后从副本审核，不与新计时叠加源节点大件读取：

| 原件 | bytes / SHA256 |
| --- | --- |
| launch.log | 1066632 / `d02900afbf675c66448a076e2c1f3b64fd863069c807bbd728b2516fc7659b93` |
| evidence/run.json | 27320 / `356ead5183c0960bd8e953c42274824be9080ef94cc50f1e293e06aa2784ad96` |
| evidence/state.json | 42428808 / `c2fbdbce37f009df65a7183788ded191efbd6ba723f0fc32675690a5a19535f5` |
| resources.json | 5176 / `cca7d76ed7244a2c578eb46231fbf169154207ac194b9abd86450abee6632ab1` |
| resources.input-provenance.json | 1990 / `e167dbaa2ecc22eae8bf1018ed630da4f7a0ffbdcd0521f640caef5df9e5bb84` |
| postflight.log | 699 / `9b134ac00e6a4147f01b58ad574453dded417b56adf48645369bfe18273489d0` |

controller.log 4195B、SHA **`91c70e7510de81291800b42a1e3d410850bd99d1b6c8d2a9b03c428fad4b95a9`** 记录16:21:02–19:24:06Z、1742起止、launcher_exit0；实际sampler **16:21:02.742–19:24:06.572Z / 10983.743s**、exit0/head_stable，run metadata为16:21:03.509–19:24:01.692Z，run_result elapsed **9731.384s**。这三个窗口按各自定义保留，不互相代用。原日志另有计时入口外offline composite computation 1222.909s，不能把整段sampler或run wall误写成单Preview。所有数据来自认证原件，无时间戳差推算worker细段。

独立解析launch唯一final summary并与state逐操作同字段比较：

| operation | user_visible / completion 秒 |
| --- | ---: |
| v1 Preview | 1725.233 / 1725.233 |
| v1 Submit | 1766.107 / 1766.118 |
| repeat v1 Preview | 1421.759 / 1421.759 |
| repeat v1 Submit | 0.010 / 0.010，同步NO_CANONICAL_CHANGE |
| v2 Preview | **4661.281 / 4661.281** |

v2为1 pair/631表/628 changed，failed与degraded均0；repeat Preview changed0，S2 no_repository_operation=true。cold准备日志在18:06:10Z显示274缓存行清至0、548文件移除、此前expired/missing均0；W2之前/之后274行且TTL健康是另一个实际窗口，不改记为压力Preview缓存命中数。该压力场景按既定record_only如实记录；这些分钟级值不被宣传为S5/S6目标达成，也不对不同输入/模式的FULL数值作性能回归判定。

输入provenance的三项实际upload bytes/SHA/role均MATCH、无issues，绑定state完整SHA及manifest **cf288bdd…62830**，census **29c1e25c…45fe6** 与§116一致。副本input-images.json完整SHA **`01cf16ea7882bb8ce89420617be8deafa359e20a334e3db4bf1590388e714d01`**、start-preflight SHA a95282bb、controller脚本SHA71812d33仍等已审启动原件。独立将三服务config digest/全部有序DiffID/labels与冻结identity文件（SHA98bfba51）逐项比较相等；run的B/W identity及本机ID也与preflight相同。fresh分支原run metadata只包含B/W，RS完整身份引用§116启动前对实际tag解析immutable ID的全量证据及启动前重核，按既有受控冻结tag模型绑定；没有伪造运行中container.Image观察或要求重复postrun Docker取证。

资源共5051个周期样本：全run并发sampled memory.current峰 **18396356608B / 17.13GiB**；各容器memory.peak和 **19748859904B / 18.39GiB** 是保守上界，不能当同一时刻并发值或worker RSS。全run peak cores2.693、临时磁盘高水位5984108544B/5.57GiB；v2 Preview步骤2127样本、并发memory.current峰10602758144B/9.87GiB、peak cores1.866、worker累计CPU4449.793s。短同步步骤0周期样本仍按§119表达未知峰值，不把raw的0/null扩成实际资源为0。

postflight sampler/Compose down/node check/cleanup均0、锁已释放，三卷保留；down时三项secret路径环境未设的原warning与FULL相同，未据此重跑。旧collector仍仅有v1_submit worker细步骤，Preview原始API计时有效而标准record补证尚待；已指明STRESS最后checkpoint位于v2 Preview之前，补该步骤应从同次停止后的final control卷取私有小副本，按run最终tree **7ace1b8fcbfa6b06cb27d00bd3245d0ac93901902b8fe5dc2a4b9cd73d7dc05b / 3850240B / 1文件** 认证，再只开复制件。FULL/core各自已审快照路线保持，不能开源SQLite或借本压力结果替代H1。实施者可集中完成必要小源取件后启动已审DC63/V5b链，05记录派生与04在途门禁可并行；本节不引入新的等待许可。

## 125. 04 fcc最终runner exit1：两项RS测试环境假设及一项launcher中断超时，待定向修正

**本次04全六包权威runner未通过。** 独立读结束status及原完整日志：19:19:37–19:41:16Z、起止完整fcc且clean、真实runner_exit_code=1；未中断其原定串行批次，也不以部分包通过冒称整次成功。日志及status/sha侧文件已LAN取CT201 `p6-baseline-evidence-review-20261107/ct04-fcc827-runner/`：run-tests.log460719B、SHA **`0170ed2c2d594d2f22df23ea75f50daea80ed85db6a3b5424e0ccc8015ef2b5e`**，与原sha侧文件精确相等；run-tests.status306B、SHA **`9a8747d2deb0be3a3a0ecd81e8d935defc367201339f62cf39ae9b40b593c583`**。源位置同§123。postflight及自有marker释放仍待实施者结果，不能以启动或镜像身份PASS代替此失败。

实际有**三项失败**，不能只记录实施者首报的RS两项。backend parallel status0；serial为1 failed/75 passed/3315 deselected、559.28s、status1。Repository Service parallel为2 failed/1759 passed/1 skipped、46.23s、status1；serial214 passed/1762 deselected、582.61s、status0。各组按权威入口自身流程执行完毕，整次非零结果原样保留。该run整体exit1，不能将其中单独通过的包直接作为规则要求exit0的qualified carried来源；其他既有合格来源仍须独立按原同节点/同worktree闭包规则判定。

**RS根因已从实际失败与源码对齐确认。** 两失败为test_compose_build_harness的rebuilds_when_labels_stale和skips_rebuild_when_labels_match；均断言返回harness.DEFAULT_IMAGE=gateway-repository-service:local，实际为本次必需的p6vref-fcc827-repository-service:latest。DEFAULT_IMAGE自身是固定常量，真实ensure调用resolve_service_image，后者合法读取GATEWAY_REPOSITORY_SERVICE_IMAGE；unit没有显式设置所测环境，错误假设ambient override不存在。保持门禁实际override、真实resolver和重建/身份语义；已交实施者仅修两现有测试的显式输入隔离，可用default/custom小参数表覆盖同一边界，不删断言或全局unset候选image来凑过。

**backend的中断失败另行定位，当前尚不能归因结案。** 精确失败是test_interrupt_stops_isolated_launcher_group_then_runs_cleanup：fixture观察journey_started后向launcher Popen发送SIGINT，随后communicate(timeout15)抛TimeoutExpired，Popen尚未返回。独立读测试和真实launcher：测试直接Popen Bash并继承ambient信号处置；launcher用INT trap停止隔离session再cleanup。候选假设是外层后台/nohup入口继承SIGINT_IGN，需原启动命令及05最小定向证据确认，不能先当作确定根因、仅拉长15s或标flaky。已要求在05核真实信号继承及默认/后台入口差别，保持停止、孙进程收束、cleanup、无卷删除和锁语义断言；没有因此改真实guard或重测已通过FULL/STRESS。

两类普通测试/接线修正继续Owner既有授权，无新Owner/设计GO；先在独立非在途worktree提交最小修订、05必要focused及受影响静态，再交具体代码/结果复核。04原候选、失败日志和身份保留，不原样重跑、改动被测worktree或沿用该失败为PASS。若最终候选改变，镜像candidate revision、实际输入闭包和必要当前候选验证重新按原规则绑定；不因本次04局部失败暂停CT108既定小源取件/分段准备和05记录派生，整体仍未完成。

**04失败运行的收尾证据已补核。** 直接读04 postflight.log1072B、SHA **`b56d6bb2de29c8ec84b5dfd1bed4bf6bc147498dcda5d25a5eaf634a2d0a1de4`**（19:50:56Z）：clean fcc、原runner PID及busy marker已无，Docker/项目容器查询exit0且无结果、8000查询exit0且无监听、所查测试/旅程/runner进程无，backend/RS Hypothesis及Cargo临时目录均无。原件已取CT201审核副本。node-busy-marker-release.log895B、SHA **`f7f791770d94cbc352449da9b7687d051038ce25b58a603051e7fe7ff7ac0e9d`** 直接核明19:43:13Z按准确session/PID/log核对后仅清自有marker，引用原acquisition及上述postflight；后取标记的事实保持。收尾成立不把exit1改作PASS。

## 126. 同run worker旁证绑定已核，core原主DB完整可证明，有限私有派生准备继续

**FULL/STRESS新worker sidecar的数据绑定/UTC计算已核一致，正式提取节点证据仍待05闭合；core当前源全目录仍MISMATCH，原主文件则完整匹配原snapshot。** 这不是重跑业务、改写raw或沿用不符checkpoint的许可。两类旁证准备和§125测试修正继续原授权，无新Owner/设计GO；未将标准record或H1资格提前结案。

CT201 `baseline/derived-control-timing-20261107a/worker-step-timings.json`10918B、SHA **`88d312b5c84fa1b9c0c39581165f89797f9a5ab2b36c249a7cae0f244cf3203d`**，包含STRESS v2及FULL三个Preview。审核者独立用§113/124认证state核四组operation ID、upload_revision_id/generation、真实来源SHA；重算每个UTC elapsed/gap与sidecar相等。私有DB当前主文件SHA分别 **`fddbfba8962cf57a148f251ef091b8642164aee2cb9c29352ebcef8b409510eb`**（STRESS3850240B）、**`84bf3e997b9e3c341ca40399702ce7420c03b0a008ff6a02debc16dc21ebf1b9`**（FULL3854336B）。没有把STRESS before-v2-preview当作完成后快照，采用其final control卷；FULL仍取before-v2-submit。

已直接读source-copy-tree-hash-evidence.log2296B、SHA **`aef553416d8d6c3d44dc887203072683ef0bc633bc8b1349daf470738df73ca2`** 及脚本4b1b1515…5b564：SSH在CT108用原字段算法核两source full tree精确为7ace1b8f/05577662，各原main SHA等于对应私有副本；原run/state/launch、FULL来源索引与state SHA均等已认证值。guard日志1339B、SHA **`ba67446380c494c4b486eaec3960f92addc371fb135cfe0b6e55028412f0ec61`** 另明确core全目录失配，没有将它混为通过。

实际初次SQL及复提节点为**heavy-dev-01/CT201**，不是05，节点事实原样保留。verify-worker-step-timings.py5756B、SHA **`64cc0be38f6a0825aa8d6b369fc5907eb6ccf204888a277b82b6d56b62ec049c`** 仅对私有copy用ro URI、backup到临时DB，按原SELECT验证SUCCEEDED/attempt、step顺序及非负gap，再核preview_result绑定；CT201复提日志877B、SHA **`f5f63b01dec88a38d02ae6d23a8f8a2502a401817d84df5c570dd04c5df03524`** 自报12行全部相同。该节点不能冒称已完成约定的05取证；已要求仅将现有认证私有DB/脚本LAN到05作同查询提取并记录实际hostname/起止及输入输出SHA，可与core私有副本合并安排，不重新取CT108或重测业务，也不与05中断focused并行。审核者此轮只做文件/hash与JSON数学核验，未在CT201开SQLite或运行测试。

**core原主文件的独立只读核验成立。** 19:54:35Z确认CT108无占用标记后，本审核仅lstat/二进制hash原history control目录，不copy、SQL、移删或调整元数据：当前full tree仍 **`2ce71212c8efec1593a6d3ed7763e46a02aeb3ca6d2182a39bcf5efe0f6fdc79`**、3文件/2183168B；只按原算法对原应有control.sqlite3一文件作**明确标注的投影**，精确得到原expected **`4baede398e55e77569836c0b51c98d1edd6b7aab6451b7cbb7d9793ff6d1aad4`**、1文件/2150400B。主文件SHA **`9b2c1afc466f1cdad160a1d5bbb6230c3ba0b50f2074eeb73cb86d45f9e500f8`**、mode0644/uid0/gid0、mtime_ns1793518591951172251、ctime仍Nov1 07:36:36Z；读取前后size/mtime/ctime一致。新增SHM32768B/SHAfd4c9fda及WAL0B/空文件SHAe3b0c442，均为**Nov2 07:23:55Z**产生，不能归因本次工具新建。谁创建这些文件尚未唯一确认，但不影响已证明的原main完整性；未将投影冒称当前完整目录MATCH。

实施者独立调查log2533B、SHA **`debbfd64da66e574123b8080e8e4ce7ad50073206393efedc0b396e0af950e33`**、脚本c1358225…3958c与本审核文件元数据/全部SHA/两种tree结果一致，且原core state503e73ab及准备索引11ef88f4仍相同。旧W4源sidecar可逆恢复§97不自动覆盖此源；本次不需要为补metadata修改原目录。

**设计已认可具体有限派生方案，可直接准备：** 原三文件原位保留、当前源full tree继续明确MISMATCH；只将与原checkpoint主文件投影精确一致的DB以保留真实元数据的复制方式放入新私有目录，开库前以未改原算法核该**完整私有目录**精确等于原4baede/1文件/2150400B，再在05私有副本补同run worker步骤/H1历史DB字段。不得作新业务恢复checkpoint或carried，不增加通用WAL/SHM ignore，不为读取派生字段先移动/删除源sidecars；不把唯一确定旧SHM创建者增加为门槛。H1还须独立核原artifact来源及实际缓存对象，不能仅凭DB或旧W2健康值标健康；TTL使用原H1起点UTC及原缓存读取规则，不用当前日期判旧时过期。私有副本实际准备/提取、H1对象证据及05结果仍待交，不停止其他已授权工作。

## 127. 三来源历史worker步骤及core H1输入缓存补证独审PASS

**合并补证 `worker-step-timings-and-h1-source-supplement.json` 16927B、SHA `9bdce65c7e519cd56264c1f01b73f3d5ee7829e8fad173b1a5555c09ba7a03de` 独审PASS。** 资格限于core/FULL/STRESS三来源的历史worker步骤及core原H1查询起点输入条件，可作为标准record的明确派生输入/外部索引依据；不改原run/state/log、原none模式或未知cache_after/命中数，不作业务恢复或carried。本结论关闭§118/126在这三来源上的步骤缺采及H1起点条件缺口，不泛化其他来源，也不替代DC63/V5b实际细分、正式record/comparator或最终门禁。JSON中的REVIEW_PENDING保留产生时快照，以本报告记录审核结论，不要求改字节再签。

05源目录 `baseline/derived-control-timing-20261107a-ct05/` 的闭合JSON、脚本及日志已LAN取CT201 `p6-baseline-evidence-review-20261107/historical-control-ct05/`，逐份独立hash相等。`worker-and-h1-history-db-extraction.run.log`2255B、SHA **`3b8301f44e48e5f26232c63c7f162ebb27b923aef45769f5681f0617405c880e`** 记录gw-dms-test-05、20:14:37Z、无冲突/占用、一次extractor exit0及输入/输出SHA。JSON264460B、SHA **`afc0ece772d393b11178bbf5a29b95ddff6387829fd9d6d29337616e2b9b16b1`**；脚本SHA **`de1f3f25e2aacac41d6115573d1b0fa4791a01c45257a3bacc9e455183133132`** 已逐段审阅，先核三私有DB大小/SHA及无WAL/SHM，再仅以mode=ro&immutable=1打开私有件、backup到临时DB，按原SQL验证SUCCEEDED/attempt/顺序/gap及preview_result。初稿CT201节点及88d312副本事实保留，05复提对FULL/STRESS的bindings、preview rows和全部12行数值逐项相同，未冒称初稿原在05。

core私有原main目录开库前的完整树核验日志961B、SHA **`e6e59b4fdd46e4e22722eaaf58e36c87a8eae01fe185ea09ab87471b8cd7f22a`** 已直接核：新目录原算法full tree精确4baede/1文件/2150400B、main SHA9b2c1afc，原源完整目录继续2ce712/3文件；源三文件未移删。05收到main SHA与之相等。此为§126限定私有重建的实际结果，不是对当前源目录过滤后宣称MATCH。

审核者重取05已认证core原state/run/journey副本并独立hash仍为503e73ab/bf3a1528/e0085bad；与已有FULL/STRESS原件逐operation核7组ID、generation、upload_revision_id、原source_head，21行UTC elapsed/gap重新计算全部一致。各行attempt=1，三步骤依次materialize_inputs/assemble_preview/publish_preview：

| 来源 / Preview | materialize / assemble / publish 秒 |
| --- | ---: |
| core v1 | 1553.584566 / 160.696548 / 1.506816 |
| core repeat v1 | 1260.532421 / 148.875345 / 0.564922 |
| core v2 | 1605.197707 / 1721.657862 / 1.204833 |
| FULL v1 | 1552.916983 / 154.422832 / 1.505013 |
| FULL repeat v1 | 1266.030409 / 143.177066 / 0.563616 |
| FULL v2 | 3116.634867 / 884.797682 / 2.813100 |
| STRESS v2 | 2255.807895 / 2397.093684 / 3.183598 |

这些是同run原DB的粗worker阶段，未用API差值、跨版本结果或诊断span拼接。不能据这三段进一步推算checkpoint-read/pair/bundle子段；后者仍由DC63/V5b既定实际链完成，也不将不同输入/模式的三来源相互作性能回归结论。

**H1起点条件现有实际对象证明。** 原e008日志独立定位：checkpoint_saved=Nov1 07:36:37.516Z，history_compare_started及step_started=07:36:37.829Z，operation_started=.853Z；05对原core DB342行按该历史compare时刻计算expired0，而非使用今天时钟。对象清单225405B、SHA **`c01805ac16a00938b18cc87ee02bd85d7fc578f73daa5889a7c1c2f211551a4b`** 与DB提取的全部cache rows精确相同；本审核逐项核repository scope等于原_stack.repository_id、artifact_id唯一、原路径hash派生、expiry及所有342对象/引用对应。原API可见/完成时间 **2426.267s** 保持bb348来源，未更改原cache_condition/cache_after缺失或argv默认none的事实。

CT108同run before-History artifact snapshot的只读验证：报告399477B、SHA **`be8ce870330302c9b9352bf11a306bf076dcee1ea4ea8d9f14b1a7156bf848a0`**，运行日志1108B、SHA **`ccb0b30e0368917368aa574227ea00020d61f2d33878599ade64c0bc05a09739`**，20:18:57Z、exit0；脚本SHA **`5086f6875ab5ad48b9f4b04d24a9ed180c4870202d4301ba937f999c3a660539`** 已读，固定原snapshot root，核342对象和342 ref文件均存在、root边界、四字段canonical ref形状/身份及每一对象size/SHA与ref相符，missing/invalid/content mismatch均0。本审核进一步逐项核报告与清单的repo/layout/writer/expiry、object/ref路径与size/SHA相等，且全部对象mtime早于历史起点。报告明确**未重hash整个1043552482B artifact树**；原02048879树身份只作来源索引，本结论仅认证实际342引用范围，符合原缓存健康consumer的行/TTL/对象存在条件，不扩为新业务checkpoint完整资格、实际命中数或History之后状态。

20:22:42Z合并脚本及日志SHA分别7d7ac906/4f0db9d7，绑定上述原输入，已独立核合并结果与提取/对象报告全部相等。已直接通知实施者消费本补证、继续正式record/comparator及既有分段/测试修订，无新GO、不重测core/FULL/STRESS；两类测试修订与05focused实际实施仍由唯一实施者完成，审核者仅只读诊断/独审，避免互等对方写代码。

## 128. e0dd两测试修正只读初审：环境隔离方向成立，新增兜底回收仍需收口

**`e0dd178d8c8c3111b57b2f0be2bcb5b12f29ad89` 尚未整体判PASS。** 父为fcc，仅改backend与RS两个既有测试文件，85增/7删；已建立只读detached审核worktree `/home/dev/gdds-p6-review-gate-e0dd178d`，HEAD准确且clean、diff-check通过。生产src、真实launcher/harness、依赖及计时均未变；05定向验证由实施者在clean已提交worktree执行，审核者未在开发机跑测试。原04失败结果仍保留。

RS的两现有用例共用default-unset/custom参数表，按场景显式delenv或setenv，仍调用实际resolve_service_image，检查预期image及是否重建，monkeypatch作用域结束自动恢复外层真实门禁image。没有将默认断言改成随ambient浮动、删检查或修改实际harness；该代码方向成立，当前候选实际focused/静态结果待交。

SIGINT继承探针在05执行，日志276B、SHA **`2bde62570001f3a664426298c86a442d1bf5586e470d0637bf0ac187cbc41fca`** 已直接只读核：20:34:15Z，前台Python及直接子进程为default_int_handler，Bash异步job的Python及直接子进程为SIG_IGN。该机制有实际探针支持；原04外层具体launch命令的关联仍已要求补记，不以一般机制伪造原进程已退出后的信号观察。已分别读05/04的GNU env帮助确认支持--default-signal。测试只在launcher Popen argv前加 `/usr/bin/env --default-signal=INT`，恢复该子进程初始处置；原15s、exit130、journey TERM、孙进程静止、Compose down及锁释放断言保持，不改真实guard或全局信号。

新增失败兜底仍有一个有界性缺口：_stop_timed_out_fixture在TERM/10s之后的最终communicate()没有timeout；已交实施者给最后回收明确短上限，超限仍失败，不能由兜底TERM/KILL成功冒充原SIGINT测试通过。另_kill_fixture_sessions使用killpg(session_id)，实际只选择同号PGID；若按函数意图收束整个自有session，应复用已有guard的native pkill -s语义并排除非正/当前session ID。此为本次已出现挂起的fixture收束范围，不新增安全状态机、探针或测试矩阵。

若05已经运行e0dd，先完整保留其结果再提交窄修，不改在途worktree。最终修订须在普通及明确SIGINT_IGN父入口下定向验证相关模块和RS两组用例、受影响两包静态；后续最终H及镜像/闭包/必要权威验证再按原规则一次绑定，不提前将e0dd或旧失败runner称合格最终候选。普通测试修正直接闭环，无新Owner/设计GO，不阻已审DC63/V5b准备与记录派生。

**窄修后 `78000beb62e927190092e315135e7bc1cbdda615` 代码复核PASS，实际05验证仍待。** 父e0dd、相对fcc仍仅两测试文件99增/7删；新建只读detached `/home/dev/gdds-p6-review-gate-78000beb`，HEAD/clean及diff-check已独立核。fallback仅从自有trace取>1且非当前SID，使用绝对native pkill -KILL -s、每次2s；超时先记错误再收束launcher，最终communicate也限2s，仍不返回时关闭本端stdout并返回显式reap timeout给原pytest.fail。原15s及全部业务停止/清理断言未弱化，RS原两用例default/custom四分支保持实际resolver。e0dd未在05实际运行，不冒称其有focused结果。

已直接通知实施者代码小项关闭、继续既定05正常/IGN入口及受影响静态，不增加teardown实现镜像测试或新证明矩阵。当前只读源码变化不改冻结产品/真实Compose runtime；最终必要镜像与当前H闭包绑定集中延期到这轮定向结果收敛后，RS的fcc candidate label不能冒充新H，旧fcc失败runner仍不作qualified carried来源。本节未认定新H已过focused、容器门禁或整体退出，也不新增Owner/设计GO。

## 129. 78000两类修正的05必要定向结果独审PASS，待静态补齐及新H权威门禁

**`78000beb62e927190092e315135e7bc1cbdda615` 的两类测试修正现已完成代码及必要定向验证独审PASS，§125修复Finding关闭。** 当前不将原fcc失败runner改为PASS，也不宣称新H通过04或整体exit。实施者可沿原授权直接准备最终H镜像及必要权威验证，无新GO；DC63/V5b和正式record/comparator继续独立推进。

本审核直接读05原脚本及下列closed日志，逐份重算SHA，LAN副本存CT201 `p6-baseline-evidence-review-20261107/gate-fixes-78000-ct05/`，再次核SHA相等；worktree为05独立clean提交78000：

| 结果 | 05日志 / SHA256 |
| --- | --- |
| launcher完整模块，普通入口4 passed/10.64s，20:48:15–26Z、exit0 | backend-launcher-focused-normal.log / `68695e82677111885c182fda3246329721faef11b238328d04eea9a3f749b0b4` |
| 同模块，明确SIGINT_IGN父入口4 passed/10.19s，20:48:49–59Z、exit0 | backend-launcher-focused-sigint-ignored-parent.log / `5eb0d00f9a2bc0697ede14e49cbaf4bec2bf7433397c31605cdc865d16075535` |
| RS两函数default/custom四项4 passed/41 deselected，20:49:16–17Z、exit0 | repository-service-image-assumptions-focused.log / `3b1556f45eb74f2ebd6af14a622a5aca8d9cbb10828277bdb48b72f60de415c2` |
| backend Ruff/mypy500及RS Ruff/mypy201均过，20:49:43–20:50:00Z、结束clean | affected-package-static.log / `e45b5d92c6ae57a1a7e1dc9ddadf37027916c3a91e2bddf4bde35bd803d52922` |

实际脚本均用受控uv入口、UV_OFFLINE=1、外置TMPDIR，launcher以-n0跑完整模块；IGN入口先trap忽略INT，并由独立Python确认parent_sigint=1后才启动pytest，未将普通入口也悄改成ignore。新env只恢复被测launcher子进程的初始INT处置；同一原15s及全部断言通过，不靠兜底TERM转成绿色。RS两函数在实resolver上分别显式unset/custom，不调用真实Docker/Dolt；不是删除默认场景。未增加业务旅程、容器矩阵或真实runtime行为变更。

05 postflight/所有权释放日志340B、SHA **`b0b52b50a44a4b1a5340da981af216df9ac0815d32b575b812af1e16fadbc973`** 及脚本已读：20:51:01Z、准确clean H、相关测试/Dolt/Cargo进程无、容器/8000无，清本会话自有cargo target后核原session owner再释放标记；没有把失败清理当作原INT语义通过。原04外层具体launch命令仍未形成新增独立信号观察，本结论是对已证ambient继承机制和修正后受控入口的验证，不伪造旧进程的历史处置位。

当前交付静态仅backend/RS两包。按AGENTS提交前五Python包要求，已交实施者在05补shared_kernel/repository_contracts/repository_client的Ruff/mypy，刚过两包不重跑；真实时间/节点继续记录，不把两包日志冒称五包。静态补齐可与独立节点的镜像/分段准备并行，不新增审核许可。最终容器/闭包与H绑定仍按§120–122及冻结产品线规则，测量用冻结镜像不替换，最终权威结果尚待实际执行及独审。

**五包静态证据现已补齐并核验通过。** 05 `remaining-three-static-checks.log`836B、SHA **`b792939fe1d75f9e2684c94eaeb423a7110c345bf38809d7e28248d7a6452db3`** 已直接读取、重算SHA并LAN存上述审核目录：20:57:44–49Z、准确78000起止、shared_kernel Ruff/mypy34、repository_contracts Ruff/mypy15、repository_client Ruff/mypy26六项全部通过、总exit0。未重复刚过两包、未跑测试/服务；审核者又独立读05当前HEAD/status，仍精确78000且clean。五包静态及本轮修复必要验证全部闭合，已直接告实施者继续最终H镜像/04权威验证，不等新GO；原fcc失败及其他尚未完成收尾资格保持原判。

## 130. DC63实际启动材料核查：输入/预算成立，RS来源校验会重建冻结tag，先修诊断入口

**本次实际启动前存在一个真实阻塞：bbe诊断Compose参与canonical build-input revision，普通stack harness会因与冻结RS label不等而调用构建脚本。** 尚未启动容器、旅程、POST或测量，不计失败运行/消耗一次身份；不能因此改冻结tag或使用新建未核RS。输入、预算及普通工具修复授权保持，不重开Owner/逐摘要GO。设计已确认在非正式DC63入口做严格、有限的source→冻结target绑定，具体修正和必要focused待交。

先前实施者曾预报77400s timeout会被metadata当作Python；其自行撤回后，本审核也独立读bbe的run_sampled及p6_dc63_resource_runner确认：wrapper明确expected_input_manifest=None，_launch_metadata仅非None时执行，实际Popen保留完整timeout向量。疑点不成立，没有改代码/加测试或产生失败尝试。

实际CT108 clean工具HEAD为bbe577c6d8ab9cf11452b3441b85cd9c8d280ea0；离线同步/扩展核验log SHA **`0f79ce0ea920aed8467f4cda9d67c828f5fc1140603674696d70b28f0d4e519d`** 已直接核：21:27:23–50Z、Python/uv缓存可用，Rust1.97四工具同selector、PATH前缀正确及覆盖unset、UV_OFFLINE=1/CARGO_NET_OFFLINE=true，已安装扩展build_input精确58436908，结束HEAD/clean稳定。21:26:54Z取得本次node lock，新project路径/资源无、整机空闲；21:42:56Z launch-preflight SHA **`2c8a7d6b6e51e66017065d576c0e361b06e39222be0f2a3d6ce6e3c0a7203e68`** 再核同条件、LOG/CHAIN_OUT为空新目录、SCRATCH和project data/容器/卷/网络均无、锁owner匹配，MemAvailable约100323842KiB、同一文件系统可用140GiB，不将TMPDIR/Docker所在同一设备容量相加。

real manifest1551B、SHA **`11958befddf729cfe769cc1d3576321a3a3e89cc8ee4cb80697134ff8a634061`** 绑定root=/home/dev/gateway-real-dumps、real/t4/full、full_v2/cross_project false。独立比较Git中已接受census（733b506e…6988）的两个t4 package字段：v1/repeat均5597503B、SHA95408cc3…a1675，v2为5596595B、SHA5a7cd54d…e3611，与实际manifest/节点包hash一致；census320总项、8SKIP，对应普通312表路径。不是只用当前datasets.json自证来源。第一次--validate-inputs误带journey controls的239B失败log SHA2c40e8f6保留；修正为纯--validate-inputs后INPUTS_VALID、exit0、clean，6198B日志SHA **`d846cbe8385547cef6dc6940557b2a75a5bbd88a277efc668d9c2d40dddffb85`** 已读，未执行业务。

三冻结镜像当前快照6518B、SHA **`1637d003488f7e4b2b447772dd35f248caad2f5815a7552745f7987494f8cd37`**；比较JSON2409B、SHA **`d8c4664efa7f3369ebb522f3e2d440efb9c10830a4f7634bdc2e7baf773fbf94`** 绑定§116原全身份01cf16ea，当前同节点immutable ID和全部15/28/15有序DiffID等于原冻结记录，config digest由同一已核immutable对象关联，没有把本机ID当config SHA。最初缺本project B/W别名的实际映射已由审核指出；21:41:59Z仅从已核同节点ID生成新p6dc6320261107a-backend/worker别名，3244B记录SHA **`bf352e0d0dc9cd2d93e4b23331c2dc1b04a862b6a0aa34ae911c06f7a7387a05`** 核两者ID/全部15层一致，未build或修改原STRESS tag。RS仍显式选冻结p6jcsgate20261106a-repository-service:latest。

完整尚未执行controller规格1526B、SHA **`dc93a191c2a31dbf455847b065440a4ebf4b35fb60bac6bdeb848ca5aac0f4e8`** 已直接读：repo/project/manifest/root和guard/chain映射相同；LOG=scenarios/p6dc6320261107a，CHAIN_OUT=diagnostics/p6dc6320261107a-output，SCRATCH=diagnostics/p6dc6320261107a，均在worktree外；普通keep-stack旅程后从同project state绑定v1 commit及live RS，不新增Archive/v3。work77400、INT后最多1200、watch78620及原配置尾部最坏79098<79200预算未变、各阶段不重置；不是ETA或充分性保证。已要求新controller随必要诊断修正更新准确HEAD，并补NO_PROXY/no_proxy unset使“全部代理清除”一致，不重生成已核manifest、不重跑输入校验或换未使用身份。上述小原件已LAN存CT201 `p6-baseline-evidence-review-20261107/dc63-preparation-bbe577/` 逐hash相同，后续从副本审核。

**RS阻塞的直接证据与消费者路径：** 本审核在CT108实际clean bbe worktree只运行官方identity元数据入口，返回build_input_revision **`3456bd7fbbd6a6c7ae807303a54f5548a4136a7f`**，source_tree_sha256仍 **`sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`**。冻结RS label的build-input为4497ded8ff3a9156bbe4c7a75ba44ae9e4675792，源树相同。canonical manifest明确将deploy/compose.yaml列为build definition；调用start_three_container_stack会调用build_compose_stack_images，后者在判断prebuilt之前先ensure_repository_service_image，严格比较build-input/source-tree两字段，不等即调用构建脚本。若按当前显式冻结RS tag启动，会尝试向该tag构建；镜像快照MATCH和新别名无法替代这个真实消费者检查。

已直接告实施者先不启动此旧路径。设计认可仅该非正式诊断子入口记录诊断HEAD/Compose→冻结产品镜像关系，核当前RS source-tree仍等冻结产品及实际三镜像config/全部有序DiffID/目标labels精确匹配，再消费预置镜像并禁止build/pull；3456与4497差异保持真实，不重tag凑label、不改普通门禁/共享harness比较、不加通用skip。chain原来通过subprocess执行journey，修正必须进入实际子入口，父进程patch不算接通。实施者负责最小接线/05必要focused，审核者集中核具体代码及结果后沿原预算接续，不扩大旅程或新建证明矩阵。

## 131. 8783诊断镜像保护已接真实子入口，旧HEAD硬编码仍会拒绝新候选

**`bbe577c6..8783cf69e175d86ec4f0b27ca177fac490144efa` 的冻结镜像保护接线方向成立，当前尚未整体PASS。** 两提交a20e3bca/8783cf69仅改chain、增加专用journey及对应两组测试，4文件691增/2删；普通harness、产品、Compose及guard预算未改。只读detached审核worktree `/home/dev/gdds-p6-review-dc63-8783cf69` 绑定准确候选；审核者只读Git/源码和已有日志，未跑测试、Docker或业务。

chain实际subprocess命令现为p6_dc63_diagnostic_journey.py，向其传project、expected-head、approved-images、output及原journey参数。该子进程先核固定已审W4三镜像记录原始SHA01cf16ea、目标project refs、当前官方RS身份和Compose字节，再用原metadata helper取得实际config digest/全部有序DiffID/labels。与冻结记录逐项核三服务；3456诊断build-input与4497冻结label明确分列false，source-tree319相等，没有把诊断来源冒称冻结label MATCH。临近真实start时再核同节点immutable ID/全部层/labels，关联此前完整config证明；未修改冻结tag。

专用进程替换harness模块中的ensure及run_compose，同时替换real_dump_journey导入的run_compose；真实start_three_container_stack的模块全局查找确会消费这些guard。普通build_compose_stack_images仍按prebuilt返回，up统一规范为单个--no-build与--pull never，显式build/pull或up的重建/拉取覆盖均拒绝；共享实现文件未变。现有focused通过真实start_three_container_stack控制流观察两次guarded up，保留缺/不符镜像在journey前拒绝，没有靠只patch父进程认定接线成功。

**确定阻塞为新入口DIAGNOSTIC_HEAD仍字面bbe577c6。** `_assert_fixed_context`既要求传入expected_head==bbe，又要求实际git HEAD==bbe，所以clean8783无论传当前还是旧HEAD均不可能通过。当前两entry测试整体stub该函数，9项绿色没有覆盖此真实入口错误。已直接交实施者：运行HEAD与外部固定expected_head精确比较，bbe只作已审来源/Compose基点记录；不尝试将提交自身hash硬编码进自身。用实际context函数的最小focused核相等及不等拒绝，可替换外部Git/metadata命令，不能再整体替换此函数来证明该修正；不增业务旅程或矩阵。

BatchMode确认05连接后，独立直接读并LAN保存已关闭 `ct05-image-guard-validation-8783cf69.log`，SHA **`7fbab55170637851b62ea5f5eb28cf11b69f140cec7b65f5fa351be2dc364ad0`** 与两端重算相等，副本位于CT201 `p6-baseline-evidence-review-20261107/dc63-image-guard-8783cf69/`。日志22:19:42–43Z、gw-dms-test-05、完整8783起止clean，Ruff0、两个文件9 passed/0.63s、pytest0。实施者另报第一轮重复--no-build断言失败已留证；该原件本轮未独立读取，不将其摘要冒称已核。当前交件没有mypy，已要求最终窄修完成backend必要静态，不重复未改四包/已过业务。

最终controller还须随实际候选更新HEAD、补新required --approved-images及NO_PROXY/no_proxy unset；原11958输入manifest、冻结镜像、未使用project、77400/78620/79200预算和Owner持续授权保持。无测量、容器或POST启动，无身份消耗；此普通接线修正由唯一实施者直接闭环，不增Owner/设计GO，也不阻独立新H镜像/04权威门禁及正式记录准备。

## 132. 6ffb运行HEAD修正代码及focused通过，mypy四项普通类型修订待闭合

**`6ffb3ccc8d1b761b3dda503a50057990700b3a6f` 的HEAD修正代码复核PASS，§131旧HEAD阻塞关闭；当前候选静态仍未全部通过。** 增量仅专用journey及对应测试，未改共享harness/Compose/预算或产品。独立读完整diff、diff-check、实际Git祖先关系和Compose SHA，另建立只读detached `/home/dev/gdds-p6-review-dc63-6ffb3ccc`；bbe是该候选实际祖先，Compose仍a7d04f92。现在实际HEAD与launcher的40位expected_head精确比较，clean独立检查，bbe只作reviewed_base_head及祖先核验，不要求新提交等于旧基点。新增参数用例实际调用_assert_fixed_context，仅替换外部Git/identity/resource读取，覆盖相等通过及不等在后续检查前拒绝。

BatchMode确认05连接后已直接读闭合 `ct05-image-guard-validation-6ffb3ccc.log`，SHA **`5ac6ede3c7f311d03ebfd6cf7b2124f8019aaf4b5a918cbef85cec618361206b`**；22:24:27–29Z、gw-dms-test-05、准确6ffb起止clean，Ruff0、两测试文件 **11 passed/0.64s、pytest0**。mypy检查504文件，四项报错、exit1：专用journey及测试引用real_dump_journey未显式re-export的run_compose，测试JSON字典推断为Collection[str]不可indexed赋值，以及测试经diagnostic访问未显式re-export的subprocess。不能将本日志表为静态全绿；已直交实施者仅修局部类型/实际模块patch表达，保持真实接线及断言，不加ignore、不改共享harness、不等新授权。修后当前候选必要静态/受影响focused待交，不重跑业务或未改包。

§131尚未核原件的首轮失败现也直接读取：`ct05-image-guard-validation.log` SHA **`67e0ba757db477b89323b1f9d134c96a434c6ff92e7577a74aca71a8b892f783`**，22:17:42–43Z、cleana20e3bca，真实start路径保留原--no-build后又前置一个，导致1 failed/8 passed；8783用规范化去重复而非删断言修复。上述两份closed日志已LAN存§131审核目录，两端重算SHA精确相等，原失败均保留。查询日志目录时05无rg已改用ls，纯只读目录查询未触被测对象，不算测试/测量失败或重试。

无DC63旅程、容器或POST启动、预算/身份未消耗；运行HEAD修正没有增加Owner/设计/审核GO条件。最终controller/实际环境的required approved-images、准确候选HEAD和八项proxy unset继续在同一集中包核查。独立04新H门禁、标准记录/比较器收口仍按原授权推进，本节不宣称整体exit。

## 133. d2ffe诊断镜像保护代码与必要05验证独审PASS，实际controller绑定待核

**`d2ffe1ac3af5e06ab6cf2a6f760124e0512e7dd6` 的本轮诊断镜像保护、HEAD绑定及必要05验证独审PASS，§130–132具体代码/静态阻塞关闭。** 相对6ffb仅改四项类型/模块patch写法：真实journey模块同名属性用setattr安装、测试JSON显式dict[str, Any]、测试直接patch已import的subprocess对象，以及用monkeypatch登记真实journey别名以恢复测试作用域。真实guard、三镜像完整校验、当前/基点HEAD语义、start控制流与所有断言保持，没有type-ignore、共享harness/产品/Compose或预算变化。独立读完整diff/diff-check，建立准确只读detached `/home/dev/gdds-p6-review-dc63-d2ffe1ac`；未在CT201执行测试。

BatchMode确认05后，直接读取闭合 `ct05-image-guard-validation-d2ffe1ac.log`，SHA **`0d9670a0c8bd3abc93427b44801d14f02e971c07cf808ff6f2eceaedaac65817`**，LAN审核副本存§131同目录，两端重算相等。实际22:26:04–05Z、gw-dms-test-05、完整d2ffe起止clean；Ruff0、两文件 **11 passed/0.64s**、pytest0，**backend mypy504 files/no issues/exit0**。6ffb的mypy四项及a20e的重复flag失败原日志保留，不改为PASS；本结论无需重跑已通过业务、输入校验、其他未改包或大输入旅程。

原§130已核11958真实输入、冻结三镜像/source-tree与诊断build-input差异、未消耗project及77400/78620/79200预算继续适用。实施者正在将准确d2ffe提交同步CT108并更新controller，需核其新required --approved-images、实际HEAD及全部大小写proxy unset是否接通；不是要求新Owner/设计GO或逐摘要许可。当前尚未收到修订实际controller，不宣称DC63已启动/通过或整体exit；镜像保护修复代码无剩余Finding，双方直接完成最后具体接线后沿原授权接续。

## 134. CT108最终controller-r1实际绑定独审PASS，原授权一次接续

**最终待执行 `controller-command-r1.txt` 复核PASS，已直接告唯一实施者按原持续授权执行一次DC63/V5b，不等新GO/回执。** 这是§133最后具体接线核验，不是重新发放逐摘要许可；截至本节只读核验时尚未启动容器、旅程、POST或测量，也不宣称最终结果/整体exit。实际命令原件位于CT108 `baseline/prep/p6dc6320261107a/`，SHA **`541733bb8fbd479c5d30c82a36cc40485cb63f843d110bc0b8e7c064c9c81e28`**，已BatchMode确认连接后完整读取、LAN取§131审核目录，两端重算相等；实施者记录bash -n通过，审核者未执行controller。

命令REPO仍为原bbe577命名的CT108 worktree，但显式HEAD现为完整d2ffe，传入真实chain的expected-head正确；新增--approved-images精确指向同prep/input-images.json。原五个guard位置参数/分隔符及chain project/root/output/scratch参数接通，manifest仍由guard追加到chain。固定root=/home/dev/gateway-real-dumps、project=p6dc6320261107a、三个外置日志/输出/临时路径与§130相同；prebuilt与冻结RS tag保持。HTTP_PROXY/HTTPS_PROXY/ALL_PROXY及各小写、NO_PROXY/no_proxy八项均unset，UV/Cargo离线、PATH/TMPDIR正确。拒绝覆盖controller.log，保留真实guard退出码及最后日志SHA；77400/1200/78620/79200原预算/收尾界不变，无阶段重置。

本审核直接在CT108重算实际approved record SHA仍 **01cf16ea7882bb8ce89420617be8deafa359e20a334e3db4bf1590388e714d01**、真实输入manifest仍 **11958befddf729cfe769cc1d3576321a3a3e89cc8ee4cb80697134ff8a634061**，不是新生成/重新验输入，继续§130的census与冻结身份结论。22:29:55.567296Z只读元数据独立观察hostname=gw-dms-test、实际HEAD精确d2ffe且status空；CHAIN_OUT存在且空，scratch、project runs、controller.log均不存在，node lock也不存在。此前准备期取得锁的§130历史记录保持，不能冒称当前仍持锁。

已明确告实施者：**按原机制先取得自有node lock并做原现场单飞/资源/镜像核对，再执行该命令。** guard自身在进入业务前要求owner文件的session=p6-baseline-measure；当前缺锁不能裸跑，不要求为此改controller、增加许可或另换未用身份。保护器中三镜像完整校验及临近start的同节点重核继续生效，禁止build/pull；失败保存并遵守原停止/收尾，不原样自动重试。后续实际启动与结果仍待实施者交回，测量中审核不作节点探测或大文件取件。04新H门禁及正式record/comparator收口保持独立推进。

## 135. DC63单次启动已报，closed锁/三镜像预检原件独立核验通过

实施者报告按§134原命令于22:34Z单次启动，当前仅至初始化阶段；本节**核验启动前材料，不认定业务步骤或最终结果通过**，不以存活PID、CPU/RSS或compose_images_ready代替成功。原预算/停止/保留证据条件保持，不重置时钟、不重试。审核者测量中只读取下面两份closed小日志，经LAN存§131审核目录；未探测进程/容器/端口、重算Docker身份或扫描数据目录。

CT108 `node-lock-acquire-r1.log` SHA **`f83f4f3c1e771e400e41cf22cd986bd32286d312c1c18fad5ba5d8934bc360a8`**、`prestart-image-identity-r1.log` SHA **`173f9ffa5d00b86485b35f68fc0cf5c58c4fe430d10cddf28c5fda246257b92f`** 已BatchMode确认后直接读取、两端重算相等。原件位于 `baseline/prep/p6dc6320261107a/`。前者22:33:24Z、gw-dms-test、d2ffe clean，记载running/project containers、项目volumes/networks和8000均空，成功取得准确session=p6-baseline-measure、project/worktree/HEAD及用途对应，preflight0；这是当时预检结果，不是审核者新做的现场扫描。

后者22:34:08–19Z、起止d2ffe clean、readonly_identity_exit0；实际context官方身份3456/319，冻结RS label4497/319，build_input_revision_match=false、source_tree_match=true、compose build/pull=false。审核者在CT201只读解析已复制JSON，先重hash§124已认证原input-images.json仍精确01cf16ea，再独立逐服务比较config digest、全部有序DiffID、labels及同节点immutable ID/approved source tag，backend/worker各15层、RS28层均相同；不是仅信JSON自报MATCH，也不把跨节点inspect ID当config SHA。wrapper原文件SHA **`4465c9f9bec7abb6b5517350dcbf7269df9c0d079e8b6665f501aa2882f248b4`** 与本审核d2ffe detached副本字节精确相等。

上述启动前两项材料无新增Finding，结论直接交实施者；实际controller/旅程/coverage/V5b及收尾的最终原件仍待运行交回集中独审。测量期间仅必要既有阶段/采样日志低频观察，不追加大取件或全身份重扫；04新H门禁和正式记录在独立节点继续，不因等待本长运行新增许可或整体暂停。

## 136. 剩余独立收尾范围澄清：无Owner后续收窄，沿既有授权并行推进

实施者在DC63低频状态更新中将当前交接摘要理解为“只推进DC63/V5b，未获用户/设计者扩展前不另启04/record”，故尚未启动这两条独立收尾线。本审核指出与§129/133–135既有剩余范围不一致，直接交设计核最近真实指令；**设计明确确认没有本轮Owner后续收窄指令，已直接通知实施者现在并行收尾。** 依据是Owner持续完成授权及接续计划场景表，且交接本身允许设计明确范围；这是消除旧交接摘要/当前分工差异，不是重新请求Owner GO，也不把范围核实变为暂停在途DC63的理由。

设计澄清的具体范围保持既有冻结线：H780 backend/worker在CT201按旧冻结整镜像流程构建、经LAN到04；RS在04用官方既有预置dependency-base离线构建独立tag，重算canonical identity，不能以旧fcc身份或CT108冻结测量镜像代替。04取得现场自有锁，在clean已提交worktree按原规则运行全六包；05独立worktree完成标准record、SHA、comparator及逐版本来源外部索引，不要求重跑已通过业务。必要工具若后续形成新H，最终闭包/镜像及权威证据仍按原规则绑定，未运行780不能提前称gate PASS。

CT108原监控/预算/进程/tag及在途worktree保持，不新增角色、不推送、不改测量对象；节点分工/离线/锁/保留证据规则保持。本审核已将该明确范围直接回实施者，不再等待额外回执。当前只是工作范围澄清，未宣称04已运行、标准record/comparator完成或DC63整链成功；后续按实际原件分别独审。

设计已将同一澄清落为提交 **`5e93a9b5497a1b1fce25c91847e410c25f58c05c`**，本审核独立读该提交的完整单文档diff，与上文范围一致；准确出处为[接续计划“并行收尾范围澄清”](p6-baseline-post-gc-resume-plan.md)。其中明确同一唯一实施者现在直接并行、不以旧“先只DC63/V5b”摘要等待扩展，04/05现场原子取自有占用、不设置窗口预约/跨会话回执前置，CT108在途边界和新H最终绑定保持。该设计文书补记不触发产品/镜像或在途运行变化，也不新增审核启动条件。

## 137. H780第二轮04门禁出现两项单测失败：归因及原停止规则已独立核实

**H780本轮权威runner已有失败，不能宣称PASS或用单独通过包作qualified carried来源。** 实施者报告该唯一全六包run于Nov7 23:55:57Z启动；Nov8本审核BatchMode确认04后，只读现有 `baseline/parallel-closeout-20261107a/ct04-h780-authoritative-runner.log` 的具体失败和末段，未运行测试或改在途worktree/镜像。backend parallel实际1 failed/3314 passed，serial76 passed；RS parallel实际1 failed/1762 passed/1 skipped，serial在读取时仍自然运行。日志尚未闭合，本节不将其当前字节/SHA封为最终证据，不伪造结束时刻/最终exit或postflight。

**backend的初报归因已校正：guard实际比较9704→H780，而不是e798→H780。** 失败为test_post_gc_resume_identity_and_product_tree_are_fixed，真实current_head=78000。独立读immutable H780 helper及真实Git diff：identity.source=e798用于核来源，实际changed命令以identity.target.product_commit=9704为基点；9704..H780完整19项变化只有docs、backend benchmarks/tests及 `vnext/repository_service/tests/test_compose_build_harness.py`。最后这一项是§129已审的显式镜像环境单测修正，也是唯一不在该固定resume路径前缀中的文件。backend/RS/shared_kernel产品src、Rust、脚本、Compose或锁在这一区间均未变。e798→9704的已批准COUNT/JCS/GC修复不能误记为新H产品漂移。

原guard按其有限关系拒绝该当前checkout，并未证明产品回归；错误在于固定历史身份测试始终把整仓库当前HEAD当作那次有限resume的工具候选。**设计最终统一采用最窄修正：该测试使用§100/101实际已审continuation工具提交3fd64dc2fe9a9c11ceebf8cd458983b9507f5364，生产guard/白名单不改。** 本审核又独立核9704..3fd只有原准许工具路径；保留source=e798、9704祖先/固定树、clean及真实差异断言。历史测试PASS不证明H780可执行该固定resume，当前V_ref产品/镜像身份仍按原规则另核。此前讨论的RS路径扩展不实施，不增加通用tests/support或src资格。

**RS失败根因也已直接核实。** test_build_script_defaults_docker_build_network_to_host实际none≠host；_base_env从os.environ.copy继承门禁必需的GATEWAY_DOCKER_BUILD_NETWORK=none，没有为默认场景移除该输入，而真实build脚本正确使用`${GATEWAY_DOCKER_BUILD_NETWORK:-host}`。保持实际门禁network-none及脚本/harness原语义；仅在unit helper先隔离ambient变量，再由既有extra_env明确覆盖，保留默认/override断言。必要05focused在实际外层none下证明这两个场景，不将全局unset门禁输入作为修复，也不改默认断言为随ambient浮动。

**自然结束在途runner符合权威入口自身行为。** 已独立读H780 run-tests.sh：各pytest批次失败设置test_exit=1并继续原选中批次，最后统一exit test_exit及执行清理；当前不是runner已经exit1后继续carried/另跑验收。无需人工中断剩余串行组；结束后先保留实际exit、closed日志/SHA、起止HEAD/clean和收尾，失败整次结果不得作为qualified carried，不能原样重试。本轮新H780镜像实际构建/传输/启动前材料尚待集中交审，未将旧fcc镜像或通过包追记为当前最终门禁资格。

两项普通工具/测试修订已直接交唯一实施者并与设计统一单一路径，可在独立非在途worktree准备小diff、05必要focused/静态后独审，最终新H的镜像/闭包/权威证据依原规则绑定。保持CT108 DC63原运行/预算/冻结tag及源卷，独立record收口继续；没有新Owner/设计GO、额外旅程或矩阵，也不把本轮局部失败变为整体等待。
