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
