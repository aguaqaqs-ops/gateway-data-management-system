# 设备目录 v1 详细执行计划

状态：正式设计配套执行计划，2026-11-12。设计及处理组接入修订已经 owner 确认；本文件安排实施与验证，尚未执行，不表示代码、节点缓存或端到端已验收。

依据：[design.md](design.md)、[interfaces.md](interfaces.md)、[kickoff-directory-v1.md](kickoff-directory-v1.md)、仓库 `AGENTS.md`。职责、模型与审核流程按仓库标准执行，不在本文另设安排。

## 1. 范围、基线与阶段边界

- 工作分支/目录：既有 `dir-v1` / `/home/dev/gdds-dir-v1`。产品基线 `eb6530b36ef645d920627208fdc3a004a0409d25`；已有阻塞报告 `deb88a1123`、设计对齐草案 `c788306fd5` 保留历史，后续追加提交。
- 只改 `directory/`、`docs/device-directory/`。`frontend/`、`vnext/` 及其锁文件、Compose、权威 runner 均不改。调用既有网关宿主工具/helper 是设计允许的接点，不复制其业务实现。
- 恢复前重读 `AGENTS.md`，核对 `main`、分支独有提交、所有关联 worktree 及本工作区状态；不动其他工作区的未提交内容。`main` 如有变化，先核对网关接点；可无冲突地合入已确认的更新，不能 reset/rebase 已引用提交。接点与正式设计再次不符则停止报告。
- 阶段 1：实现目录服务、CLI、目录前端，在 06/07 完成组件验证与十张截图，交 handoff 审核。真实网关热新增、撤销与上传审核旅程留到阶段 2，阶段 1 结果明确记其未运行。
- 阶段 2：仅在阶段 1 审核通过且满足 FE4/fe-handoff 集成放行后，在包含两项改动的 clean 提交上于 05 执行 §7。不因 tag 已存在就自动视为放行。
- 不推送；`dir-v1-exit` 如按既定流程建立，附注限定为阶段 1 组件退出，不替代阶段 2 结论。

## 2. 风险与验证取舍

| 对象 | 风险/实际后果 | 最小保障 | 验证 owner |
| --- | --- | --- | --- |
| 网关设备归属、仓库与固定 INITIAL | A：错误 scope 可能登记到其他设备或组 | 复用既有登记幂等性；核目标及固定回执，不自行建仓/改组 | 既有网关测试拥有内部算法；本系统测适配与本地成功边界，阶段 2 测接通 |
| 会话签发、撤销、handoff | A：泄漏凭据或覆盖其他主体授权 | 私有存储、精确归属、既有锁、严格 schema、旧 token 撤销；secret 不进入日志 | 服务测试；真实撤销由阶段 2 拥有 |
| CSV 整份替换、开通/续期待生效凭据 | B：部分名单或中断后无法确定当前凭据 | SQLite 事务/唯一约束，effect 前保存候选，代表性中断恢复 | 服务测试 |
| 地区树、计数、排序、搜索、最近访问、分页 | C/D：可由完整目录重建 | 普通输入与交互测试，存储不可用仍工作 | 前端单测，mock e2e 只测用户流程 |
| 临时 session 文件、前端测试容器、截图 | C：残留或凭据暴露 | 私有路径、用毕释放、证据与源码分离 | 对应 runner 与必要文件系统测试 |

不增加注册任务表、第二恢复器、跨文件事务框架或通用 evidence 平台。不为同 euid 恶意改名建立新进程/UID。必须保留输入、secret、路径/静态根、非 shell 执行、跨 scope、文件上限及授权覆盖边界；测试证明业务语义，不枚举每个 syscall 窗口。

## 3. 按依赖顺序实施

下面是工作内容分段，按标准流程分包与交审；不是新增阶段 tag 或独立模型角色。

### 3.1 基础工程、数据库与导入（B）

交付：

- `directory/service/pyproject.toml`、`uv.lock`、`.python-version`，标准库包 `gdds_directory`；Python `3.14.6`，开发工具仅 kickoff 允许的三个固定版本。
- 使用源代码包及仓库内可执行 `gdds-directory` launcher；README 说明 PATH 和 `python -m gdds_directory` 的等价用法。不为生成入口另加未经授权的 build backend。依赖环境由 uv 消费，运行时不导入 pytest/ruff/mypy。
- 单一基线 schema：项目、开通/凭据记录和目录元数据；外键、站号及设备/项目唯一约束，错误 schema 拒绝。目录管理锁覆盖本系统写命令，HTTP 只读不取管理锁。
- I1 全文件校验、逐行错误码、I2 固定向量、整份替换摘要、dry-run、移除/恢复、`status`。规范化仅用于站号；生成后的设备/项目键按 exact identity 传给网关。
- 导入在事务外完成解析/校验，在一笔事务内应用名单与元数据；碰撞检查包含保留的移除项，恢复时沿用原开通记录。
- `directory/scripts/run-tests.sh --service` 的服务运行路径、日志与 clean/locked/offline 前置检查。支持必要的 pytest focused 参数透传，以参数数组传递，不拼 shell。

验证：I1 同构错误收敛成模块级参数表；三条固定向量；有错误时整份不写、dry-run 不写、改名/换地区键不变、移除恢复保留开通回执；一个事务回滚用例。使用临时 SQLite，不使用 Docker/Dolt 或网关 fixture。

依赖准备：锁文件在 CT201 生成并核 canonical source；把实际 lock 所需 Python 工具、解释器和 uv 缓存按 DC67 预填充到 06，记录来源提交、摘要与时间。不能以其他包“看起来版本相同”代替实际离线命中检查。

### 3.2 HTTP、静态服务与跳转（A）

交付：

- `serve` 用 `ThreadingHTTPServer`，每次查询使用自己的只读 SQLite 连接；同一响应的数据与元数据从一致快照读取。服务不初始化/更新目录 DB，不加载网关管理凭据，不向网关或其他服务发出网络请求，不调用 Docker 或 subprocess。
- I3 catalog、ETag/304、gzip、healthz、错误 JSON 与静态文件；静态根只允许构建产物，拒绝路径逃逸/符号链接逃逸，不列目录或暴露 DB/源码。
- handoff 仅使用 I7 的固定 URL 配置和本地当前凭据，按 I6 编码；逐项校验 device_key、return_query 和到期时间；目录已移除/未开通/过期/续期未收尾分别按接口拒绝。响应及 handoff 错误使用 no-store，不把片段或 token 交给访问日志。
- 开通完成事务在 `provisioned` 变化时更新目录版本；仅轮换 token 不改变 catalog 可见数据，不靠目录版本控制会话有效性。

验证：真实本地 HTTP server 加临时目录/SQLite，覆盖 I3 状态、gzip/ETag、I6 UTF-8 base64url 与固定 return origin、当前凭据恢复、静态根边界。HTTP 测试禁止网关适配器/子进程被调用，运行前后核 DB、网关哨兵文件未变；不复制前端搜索矩阵。

没有导入过的 DB 视图按 I3 返回 `CATALOG_EMPTY`；不能为方便查询在 `serve` 路径自动建库。已存在却 schema 错误或不可读的数据库按配置/依赖故障拒绝，不伪装为空目录。

### 3.3 开通适配、会话续期与恢复（A，含 B 状态）

交付：

- 一个可替换 `GatewayHostAdapter` 边界，承担配置/只读预检、`add-device`、登记查询、公共 scope/旧凭据探针、受锁会话替换。名称可按实现调整，职责不扩大。
- 从已确认的 `GDDS_DIRECTORY_GATEWAY_ROOT` 定位既有 stdlib helper；复用配置 parser、session validator、跨组 token 唯一性及宿主锁。若 helper 与设计边界不符，报告后再改设计，不能复制另一套网关模型规避。
- 新增全批次只读预检：站号、固定环境/组、已有绑定、session schema 与容量、路由目录条数/字节上限。dry-run 不发写请求、不产生 token、不写文件。预检不是跨工具全批事务，后续其他管理方并发变更仍由既有锁内检查裁决。
- 开通先事务保存候选，再以 0600 私有文件传给既有 `add-device`；命令使用 argv，无 shell。只继承明确所需环境，HTTP 不继承 proxy、不跟随重定向，所有 I/O 有超时与响应大小限制。候选文件用毕删除，重跑不依赖临时文件。
- 保留工具原始 0/1/2/3 退出码与安全诊断，逐设备记录已完成列表；任何非 0 停止本次批次。无法知道网关内部步骤时报告未知，不把异常正文或输出原文当日志打印。
- 工具 exit 0 后查询 registration 与本次 token 公共 scope；在一笔短事务内保存固定 INITIAL 回执、激活 token、更新时间和 catalog_version。丢失本地成功响应时重跑仍使用原绑定和候选。
- 续期严格按 design §4.1/§6.2：先读取/恢复既有候选；publication → group management 锁内重读、完整条目归属校验、预检；保存本轮全部候选后一次替换本组会话文件，保留其他合法条目。保留原权限/属主、fsync 文件、replace、fsync 父目录。
- 新 token 的公共 scope 与旧 token 后续请求 401 全部确认后，原子激活本轮候选。失败保留待收尾状态；重跑识别旧/候选条目，不再产生新一轮。存在待续期的设备 handoff 返回 `SESSION_UPDATING`。
- README 写出启动前提、开通、busy/未完成、续期与中断后的同身份恢复命令；不提供清空网关目录、改组、换键或忽略冲突的“恢复”捷径。

验证按语义集中，不运行真实 Docker：

| 不变量 | 一个主要验证位置/代表场景 |
| --- | --- |
| 目标与凭据边界 | 参数表覆盖错误组/环境、scope/仓库回执不符、未知字段、归属冲突、文件超限；失败不误写其他会话 |
| 不提前报告成功 | 替身返回 exit 0/1/2/3、登记查询失败、公共 scope 不符；只有全部确认才激活本地凭据 |
| 开通重跑 | 替身持有登记事实，模拟登记已发生但本地未收尾；重跑用同候选、同仓库/INITIAL，无第二建仓事实 |
| 续期与恢复 | 真实临时文件，在 replace 后/DB 收尾前中断；重跑保留第三方合法新增会话，完成相同候选，不再次轮换 |
| 锁与文件行为 | 既有 flock 的普通争用、原权限/属主与原子发布；一个语义用例验证 busy 不写，避免调度窗口矩阵 |
| helper 接通 | 仅用临时文档调用实际 stdlib session validator/锁 helper，确认严格 schema；不重复测试网关内部注册/路由算法 |

独审重点是跨 scope、凭据泄漏、第三方会话误覆盖、success 边界与中断收尾。实际容器读取热替换、真实 401 和实际入口发布仍记为阶段 2 待验证。

### 3.4 目录前端与浏览器交互（A 接入；普通 UI 为 C/D）

交付：

- `directory/frontend/` 独立 Vite + React + TS；版本严格用 kickoff 清单，锁在 CT201 生成。不从 `frontend/` import 源代码，不新增路由/状态/拼音依赖。
- 一次加载完整 catalog：地区树、当前地区及全局范围搜索、匹配计数、默认排序、同名标记、50 条分页；URL 状态按 `r1/r2/q/scope/page` 恢复并响应浏览器前进/后退。
- 最近访问最多 10 个 device key，所有 localStorage 读写在 try/catch 内，删除已不存在的设备；未开通不可进入。键盘、焦点及 disabled 原因按设计/草图。
- handoff 仅在成功时同标签跳转；覆盖中文错误、空目录、可重试加载失败。最近访问不保存 token、handoff URL 或 session；不把跳转响应写 console/浏览器快照。
- 只复制必要颜色/字号 token。测试用 React 自带能力、Vitest/jsdom 与 Playwright，不能为测试方便增加未授权库。

验证：纯搜索/排序/计数/地址状态由前端单测拥有；mock e2e 只覆盖浏览筛选、搜索、最近访问与键盘、成功跳转和错误不跳转。接口错误用参数表，不为每个错误复制整段旅程。

截图固定五种状态：浏览、搜索、未开通、跳转失败、空目录；各 1280/1920 两张，共十张。跳转失败截图取一个有代表性的中文错误，其他错误由测试覆盖。与已有三张草图核对布局、层级、语义色、按钮与焦点，不作像素级比较；偏差逐项列明。

### 3.5 阶段 1 集中验证与交接

代码收敛到 clean 已提交候选后，在 06/07 分别从唯一入口完成各自完整组件检查；调试期间只做必要 focused 运行。中间已通过且闭包无变化的结果保留为回归参考，阶段交付的两部分证据要绑定同一个最终产品候选。

- 06：`UV_OFFLINE=1 directory/scripts/run-tests.sh --service`，依次 ruff、mypy strict（含 tests）、pytest。
- 07：`GATEWAY_FE_TEST_WORKERS=2 directory/scripts/run-tests.sh --frontend --screenshots <worktree 外绝对目录>`，固定工具链身份、network none、npm ci offline，依次类型检查、lint、unit、build、mock e2e、截图。
- 检查 README 的命令/配置与 I7/I8 一致，launcher 能运行，所有锁与源码范围无漂移。
- 更新 handoff，完成标准独审及 findings 复审；附完整范围、候选提交、原始成功/失败记录与阶段 2 待验证项。审核期间源码只读，修正回实施树后生成新候选，按影响范围补测并更新最终证据。
- 阶段 1 到此交审，不执行真实开通命令，不以替身测试宣称网关热新增或撤销已验证。

## 4. 节点与 runner 操作要求

### 4.1 运行前

1. 以 `ssh -o BatchMode=yes <别名> 'echo OK'` 确认连接；服务 06、前端 07、真实旅程 05。核实际占用标记、进程/容器、端口与可用空间，不用上轮空闲快照代替现场检查。
2. 按当前 `AGENTS.md` 原子 `mkdir /home/dev/gdds-node-busy.d`，记录会话、用途、UTC；前端静态检查/mock 也按当前规则取标记。已有入口自行取标记时不重复取。冲突等待，不删除他人标记，不退回开发主机测试。
3. 经获准 LAN Git bundle/文件传输把已提交源码送到节点，建立本任务 clean worktree；若为 linked worktree，按规则建立本地 `legacy` 参考链接，但本系统测试不依赖 legacy。保留原 worktree，不在测试中检出/提交源码。
4. Python 核版本和本节点离线 uv 工具闭包；前端核固定镜像的 config digest 与全部 DiffID（沿用既有前端入口的校验逻辑，不比较跨节点 inspect ID）。检查本次锁对应的缓存档案及来源。不得通过试跑失败后临时联网补依赖。
5. 准备 worktree 外的日志、临时区、环境与证据路径。设置 `TMPDIR=/home/dev/gdds-test-tmp`；服务 uv 环境、pytest/mypy/ruff 缓存与测试临时目录放在本任务外部目录；前端从 HEAD archive 到一次性容器内运行，截图挂到证据目录。

### 4.2 runner 与离线缓存

- `directory/scripts/run-tests.sh` 是唯一入口，模式为 `--service` 或 `--frontend`；两部分在对应节点执行，不自动把测试调度到开发机。不并入现有两个权威 runner。
- 服务同步与运行均 `UV_OFFLINE=1`、locked，隔离 ambient index/config，不改变 canonical lock source；实际环境首次同步先于测试冻结。运行前后核 `uv.lock` SHA256，漂移失败且不自动 restore。
- 前端使用既有固定工具链镜像；在 CT201 依目录自己的 `package-lock.json` 生成完整 npm 缓存包，经 LAN 送 07。网络 none，`npm ci --offline --no-audit --no-fund`，workers=2；宿主不安装 Node。
- 即使依赖与网关前端相同，也记录本次 cache 来源提交、归档 SHA256、取得/传输/预填充时间及目标节点；镜像另记完整 config digest、全部 DiffID。既有缓存可复用，但不能省略本任务 lock 闭包核对。
- 不打印带凭据的缓存 URL/proxy 值。缓存缺失、LAN 不可达、镜像身份不符时停止受影响验收，先按 DC67/DC68 与当前环境修复规则处理；不换 registry 身份、不跳过身份校验。
- 每次日志写 worktree 外，含 hostname、开始/结束 UTC、开始/结束 HEAD、入口 argv、runner exit code；管道保留真实 exit（pipefail/PIPESTATUS），日志关闭后计算 SHA256。测试失败不继续依赖的截图/验收，不把失败续接成成功运行。
- 收尾确认无本人子进程/容器再释放本人占用；只清理确认无需保留的本人临时文件。保留原始成功/失败日志、截图、缓存来源和审核仍需的 worktree。

## 5. 阶段 1 证据与退出清单

handoff 固定包含：

| 内容 | 必填信息 |
| --- | --- |
| 源码 | 基线、提交列表、最终产品候选、设计偏差、路径范围；文档追加提交与产品候选区分 |
| 两部分检查 | 节点别名/hostname、起止 UTC/HEAD、入口、真实 exit、日志绝对路径及 SHA256 |
| 缓存 | 来源 CT201 的实际 hostname/提交、Python/npm lock SHA、缓存归档 SHA、预填充时间、使用的目标节点；镜像完整身份 |
| 十张截图 | 状态、宽度、证据绝对路径、每文件 SHA256、清单 SHA256、草图核对及偏差 |
| 审核 | 被审提交区间、原审/复审结论与 findings 对应修正/测试，不用“无意见”替代范围 |
| 运行前提 | 未改 frontend/vnext、未推送、依赖范围、无 worktree 漂移；网关镜像是否构建及理由 |
| 未完成项 | 阶段 2 三个真实行为及完整旅程明确未运行，不列为阶段 1 通过项 |

本系统新增源码不触碰网关 build context，不为阶段 1 重建 backend/worker/RS 或运行六包门禁；前端工具链容器身份仍要校验。阶段 2 使用的既有网关镜像与来源必须单独核验，不能从本系统的单元验证推导镜像结论。

## 6. 阶段 2 开始前检查

必须同时满足：

- 阶段 1 已完成组件证据与标准审核，所有影响开通、凭据、scope 的 findings 已关闭。
- `kickoff-fe-handoff.md` 规定的 FE4/fe-handoff 集成与目录放行已经发生；核具体集成提交及通知/退出记录。核对时已有相关 tag/祖先关系只是线索，不自行把条件标为通过。
- 在含目录与网关前端改动的最终 clean 提交上执行。若主线集成改变目录行为，先补受影响组件检查；若只追加文档，明确组件证据来源，不能把历史日志改写成新 HEAD 的实跑。
- 05 空闲并原子取得整机占用，当前配置所需固定镜像、离线依赖、样例包及空间齐备；环境不是他人的运行栈。
- 已按网关标准部署流程准备一个处理组与独立入口，固定环境/组、镜像 revision、roots/预算、session 父目录挂载、内部 bearer 路径和 loopback 端点；记录现有 deployment 检查结果。不修改 `vnext/` 或由目录重建部署管理器。

不额外扩成 t1–t4 或性能/容量全旅程。真实范围就是 §7 的两台设备及一条上传审核链。

## 7. 阶段 2 真实旅程与证据

1. 样例 CSV 至少两个地区一、同名项目、多音字读法；导入后核目录数量和固定设备键。准备两台 A、B，公共 scope 之外的设备不加入样例。
2. 保存 backend/worker 原容器身份，执行目录 `provision` 开通 A、B；记录无 secret 的退出/登记回执和公共 scope 检查，确认没有重启已有 backend/worker。
3. 启动目录与网关前端 preview，`GATEWAY_FRONTEND_ENTRY_ORIGIN` 指向公共入口。从目录搜索进入 A，核片段清除、地区/项目标题、尚无数据、上传入口。
4. 使用网关现有 `frontend/e2e-real` 样例包完成上传 → Preview → 提交 → `test1` 审核通过；不得绕过 UI 伪造审批成功。在差异页刷新，确认仍为 A。
5. 返回目录，进入 B，核看不到 A 的业务数据。记录回到目录后的 URL 状态恢复。
6. 执行 `provision --renew-sessions`，经公共入口验证新 token 的 A/B scope 正确、旧 token 的后续新请求返回 401，backend/worker 身份保持；目录再次跳转使用新 token。凭据只在受控文件/内存，不写日志、截图、浏览器 trace/HAR 或异常。
7. 关闭本人服务和 Compose 栈，确认本人端口/进程释放，核容器与原始证据保留需要，再释放占用。不得清理其他镜像/卷或全局 prune。

每一步记录节点、起止 HEAD/UTC、真实 exit 与证据 SHA256。容器父目录热替换、新设备首次上传、`test1` 审核本人提交三点必须真实证明。任一点不符，立即保留证据并停止依赖验收，不改后端/前端规避；结论交审核核收，未通过或未知不宣布完成。

## 8. 停止与修正

新依赖、越界改动、正式文档冲突、实际网关行为不符，均按 kickoff 停止报告；不扩大权限/部署语义或改测试预期。普通实施 bug 在标准修正/复审流程内处理，构建/命令/缓存故障按当前 AGENTS 的已授权修复规则处理，保留原日志及原因。

执行计划只安排已确认范围。未来多组分配、设备迁移/禁用、SSO、全规模开通或新增发布/恢复机制必须先调整 owning 设计；不从审核建议自动扩大本轮任务。
