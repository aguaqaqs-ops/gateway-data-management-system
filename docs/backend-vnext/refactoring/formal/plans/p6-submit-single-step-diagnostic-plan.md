# W4 Submit 单步隔离诊断设计

2026-11-05，p6-backend-design；依据 Owner 的 DC80 主动诊断授权。
本方案只用于 05 定位已发生的 Submit 租约失效，不是正式测量恢复或阶段 exit。
实施材料见 p6-baseline 的 handoff；独立审核见
[有限审核报告](p6-submit-single-step-diagnostic-scope-review.md)。

## 范围与分工

- 来源固定 `p6bw4s4h120261105b` 的 v2-submit 前 checkpoint，completed_through=v2-preview；
  产品固定 `e798ec87a37330250b0c051162e7962dba1daa60`，镜像按 config digest 与全部 DiffID 核对。
- 原实施者负责最小运输清单、启动与清理；既有工具任务负责外置诊断入口和观察器；
  接续审核者 `01a182d8-4dfd-7441-b9db-4deefdc4e0ac` 核对实施与启动条件。
  设计会话仍为 `01a1a628-e59a-7981-aad5-6bf31e919d38`。
- 只在取得有效占用后的 05 独立项目副本执行一次 v2-submit；不重生成输入、不重跑 Preview、
  不执行成功后的其他业务步骤，不改变产品、Docker 配额或 lease/stall 阈值。
- CT108 原 live volumes、checkpoint 和原始证据保持不变。正式计时仍只在 CT108，
  05 的观察结果不作为正式性能数字，也不以诊断成功代替正式恢复审核。

## 副本与启动绑定

运输仅包含已绑定的 run/state/launch 元数据、三卷 checkpoint、必要输入和唯一 composite
cache entry；引用路径与原 manifest 一致。先从精确已知 metadata 得到名称、摘要和大小，
不以全卷扫描代替清单。缺失缓存、镜像或路径先补齐明确方案，不默认重新生成或构建。

05 可以从已校验 checkpoint 完整物化三个 source-name volumes，再沿原 resume 入口
克隆独立目标；拒绝已存在的同名卷，核对精确名称/labels，无关联运行容器。不得造空占位卷、
复制 CT108 失败后的 live volumes 或修改原 manifest 来绕过检查。复制保留原摘要涉及的
mtime_ns、uid、gid、mode 等属性，并按原校验核对副本。

实际解释器、干净 worktree、离线依赖、Repository Service 镜像、输入/cache、卷绑定、
新项目名及资源预算须在具体 launcher 中确定。方案审核通过不自动表示这些实施事实已核验。
当前可继续精确元数据及 05 身份/容量只读核实；实际运输和 POST 待成套启动条件审核后接续。

## 观察与停止

外置入口在 POST 前确认真实 worker 的有效 Python 3.14.6 文件/行号业务栈，只允许一次 POST。
当前 py-spy 纯 Python dump 的同镜像 canary 已通过；native unwind 不可用，不宣称具有原生栈。
离散 dump 每 15 秒一次、单次最多 1 秒，无 locals、业务行或 secret，不运行 record/top。
这是 05 诊断的限定观察例外，不改变正式基准禁止挂载采样 profiler 的口径。

独立守护从 POST 前 arm 起计最多 45 分钟；两次无效 dump、观察器失效、产品失败、R5 或
原停止条件触发即收束，不自动重试。目标步骤成功或失败结束后先关闭观察器，再进入原 journey
清理，避免观察器信号打断证据保存。dump 不得阻塞独立时限。

资源边界只用于此次诊断，采用轻量读取，不建立新的产品资源机制：

- 启动前宿主 MemAvailable 至少 48 GiB；相关文件系统可用空间覆盖尚需落盘的 checkpoint
  staging、源名副本、目标卷（共 3C）、输入 I、cache R、归档临时量及 10 GiB 余量。
  已占用的材料不重复从当前 df 可用值扣减；跨文件系统分别核算。
- POST 执行期间每 5 秒读取绑定 worker 的 RSS、宿主 MemAvailable 和实际数据文件系统
  可用空间。worker RSS 达到 40 GiB、MemAvailable 低于 8 GiB、任一相关文件系统可用空间
  低于 10 GiB，或必要指标不可读时，记录原因并停止此次诊断。
- 资源监测复用同一外置守护及生命周期，不新增独立监控服务。资源/预算截断属于诊断停止，
  不据此认定产品断言失败；采样阈值也不宣称连续硬上限。

## 结果与收束

保存独立结果、原 run/state、资源与观察日志、起止身份、退出码及摘要。
成功后的 DiagnosticComplete 可能使原 journey 记为 FAILED；独立报告只能陈述单步结果，
不得称完整旅程 PASS。另核 finalization_errors、容器/network 清理与卷保留。
只清理本次项目的运行资源并释放自有占用，不使用 down -v；保留原始来源、目标卷和诊断证据。
根因与正式恢复资格仍由后续独立审核判断，不由设计会话判定实施证据。

## 2026-11-06：新 RS 下的单步接续候选

本节替换下一次诊断的目标 RS 身份，其他观察、资源和单步边界沿用上文；具体 launcher 与身份材料仍须独立审核后才能执行。不复用此前的 Submit GO，也不使用 READY cap 的限定恢复 approval。

冷 catalog 修复代码 `4497ded8ff3a9156bbe4c7a75ba44ae9e4675792` 与局部证据已通过审核 `78f43ebe31`。随后固定新 RS 的一次冷调用由审核者复核为逻辑调用成功：62.919 秒、第三次尝试返回完整 HTTP 200 catalog；工具 exit 1 仅因首尝成功条件未达。前两次没有独立异常记录，不补造其 cause。依据 owner 关于性能目标可讨论的补充，将本次首尝目标未达记为性能余项，不再重复相同 GET、预热或为该目标扩展优化。本次没有调整原 HTTP 预算或重试，不需要以新配置冒充旧口径成功；原 lease 问题仍 OPEN。

下一候选用于观察原先在 `prepare_import` catalog 读取处提前失败后的剩余 Submit 行为，只允许一次 POST，不把它称为冻结产品失败的原样复现或正式基准恢复：

- 来源仍为 `p6bw4s4h120261105b` 的 `completed_through=v2-preview`、v2-submit 前 checkpoint。复用已运输并核验的 05 原始三卷材料、输入与 cache；不能使用前次失败 Submit 的目标卷或本次冷读目标卷。CT108 原源不新增扫描、复制或负载。
- backend/worker 保持原 e798 产品及已核镜像；只将目标 Repository Service 替换为 4497 的新镜像 `p6catalogdiag20261106c-repository-service:latest`。其已核 config digest 为 `sha256:39e0668b05a814c835ae8214dd486c5641d0ff61b9a2c6044a53b71c6e05a1f2`，全部 28 项 DiffID 以已审机读身份文件为准。运行前核实际本机身份，不能仅凭 tag。4497 的变更范围严格引用已审四文件 diff，不并入其他 main 产品或镜像变化。
- 源 checkpoint 按其原 e798/旧 RS 身份核验；目标按 e798 backend/worker 与 4497 RS 的组合记录。源与目标的 RS 身份明确不同，不能改旧 manifest、写假 MATCH 或启用通用 skip identity。若现有工具不能表达该精确组合，只在独立外置候选中增加这一个固定来源与目标的核验关系，交审核，不放宽其他身份检查。
- 使用全新项目、证据目录、幂等键和目标三卷副本；名称由具体 launcher 固定并检查未占用。保留父 repo/commit、规则、输入、缓存及 TTL 原核验，不改 lease、heartbeat、stall、Docker 配额或产品 timeout。RS 为新进程，不预热 catalog；不重跑 Preview，不执行 Submit 后任何业务步骤。
- 原 45 分钟 POST 观察上限、5 秒轻量资源采样、worker Python 栈观测与停止收束继续适用。原工具已经验证的观测能力按真实镜像/解释器绑定引用，不为本次重新跑同样 canary。实际开始前核 05 有效占用和资源；旧材料实际已占用的空间不重复计入待复制量。无新通用监控、无额外 RS profiling。

审核者核具体差异、来源与目标绑定、单 POST 截止、原始材料沿用和清理范围后给本次明确 GO，原实施者即可沿 DC80 执行，不另等待 owner 回执。失败时保留证据并按实际分类处理，不自动重试；单步成功也只表示该诊断候选的步骤成功。新 RS 的正式产品门禁、合入与基准 V→H 恢复资格仍须另行完成，不能用本次诊断替代或撤销 H3 已通过的证据。
