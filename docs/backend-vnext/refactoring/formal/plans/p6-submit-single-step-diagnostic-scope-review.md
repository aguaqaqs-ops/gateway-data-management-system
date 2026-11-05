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
