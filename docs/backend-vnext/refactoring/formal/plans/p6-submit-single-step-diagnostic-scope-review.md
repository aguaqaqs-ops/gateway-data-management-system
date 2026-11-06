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
