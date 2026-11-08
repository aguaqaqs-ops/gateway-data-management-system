# AGENTS 结构整理对照与交接（2026-11-08）

状态：本地修订，待 owner 安排独立会话审核；未获推送及节点 main 同步授权。

## 1. 前提与范围

整理前基线：`4b224865e42e4c3ea4a5d9d595a36ca34db0b874`；原 AGENTS 为 375 行、20,648 字符（含空白），不是任务起草时的 366 行。原文可用 `git show 4b224865e4:AGENTS.md` 逐行核对。

- `p6-s2a-exit` → `53b676a6298d408ccda3a85ee73c7ea223a2311a` 是 main 祖先。
- owner 确认本轮测量交付退出；附注 tag `p6-baseline-measurement-exit` → `1d4aa1dd63d64f76760bedda3802579a77a504d0`，tag object `683a5d6a0beffb5763a82e3eef53039be7435ea2`，与 `/home/dev/gdds-p6-logs/analysis-handoff-20261108/baseline-measurement-exit/exit-record.json` 一致。仅分版本参考交付完成，非 P6 整体退出、性能达标或当前 main 性能资格。
- 2026-11-08 05:56:22Z，04/05/CT108/06/07 均先 BatchMode `echo OK`，再查 `/home/dev/gdds-node-busy.d`，五节点均不存在标记。前轮 05:52 检查也为空；本轮退出确认后重新检查。
- 只改 AGENTS、testing-conventions、FE3 kickoff 的相互引用/状态及 owner 确认的 M1 基线文字，加本对照表和引用清单。不改 runner、测试、依赖、镜像、产品或历史证据。

AGENTS 原二级、三级标题全部保持；“权威入口的运行前提”“镜像身份等价”及其第 3 条、“镜像身份”、backend/worker、DC67/DC68 等文字入口也保留。机制仍是必须遵守的规范，只把细节集中到 testing-conventions。FE3a 临时要求 mock 每次占用不收入条文。

## 2. 原规则逐条去向

A = [AGENTS](../../../../../AGENTS.md)；T = [testing-conventions](../../../testing-conventions.md)。表中行号均指固定基线，不是修订后的行号；同一行有多个规则时拆行，跨行机制共同列出。标题与空白不算独立规则。

| 原 A 行 | 原规则（摘要） | 新位置 | 处理 |
| --- | --- | --- | --- |
| 7 | 全新项目，无使用方、历史数据、兼容/迁移要求 | A 项目前提 | 保留 |
| 9-12 | Contract/checkpoint/digest/DTO 直接目标形态；无兼容层/双读写/别名/回填；同步 golden/tests；control DB 单基线、拒绝不符 schema、删 DB/wal/shm 重建、保留数据部署时才 migration | A 项目前提 | 保留 |
| 13 | 删除替代实现，不保留旧路径 | A 项目前提 | 保留 |
| 14-15 | legacy 只参考，真实数据与 owning Contract 优先 | A 项目前提 | 保留 |
| 16-17 | 阶段不改行为仍冻结 golden/digest | A 项目前提 | 保留 |
| 21-25 | 唯一后端权威入口 run-tests.sh | A 跑测试 | 保留 |
| 29 | 测试/容器/取证只在专用节点 | A 专用测试节点 | 保留；删除后文同义重复 |
| 30 | 04/05/CT108 硬件独立，04/06/07 同宿主，不算五套独立硬件 | A 专用测试节点；T 执行入口 | 保留 |
| 32-38 | 五节点别名、用途、06/07 规格/IP 与 06 扩容事实 | A 专用测试节点表；T 执行入口 | 保留 |
| 40 | 06/07 不承接正式性能、权威 runner/carried、默认真实全旅程；真实前端 05/04 | A 专用测试节点；A 前端测试（FD7） | 保留 |
| 40 | 06/07 自主并行，不自动与 04 互斥/占 04/申请窗口汇报；保留自身占用、端口、计时独占，实际干扰/跨节点/冲突才协调 | A 专用测试节点；T 执行入口 | 收拢重复表述 |
| 40 | cpuset 分离不证明无竞争；新节点非正式性能依据；节点核对报告 | A 专用测试节点要点；T 执行入口 | 细节留 T |
| 42 | 06 pytest/Cargo 各建议 4，07 明设 FE workers=2 不照搬 48；产品 N/M 单独设置 | A 专用测试节点；T 执行入口 | 保留 |
| 42 | thin guest 空间非宿主物理容量，管理员监测 pool | A 专用测试节点链接；T 执行入口 | 细节留 T |
| 42 | 新节点离线预填充，05 代理不扩展；克隆资源非证据、不擅清 | A 专用测试节点链接；T 执行入口/测试节点网络与缓存 | 细节留 T |
| 44 | DC87/DC33 本轮 S2b E 06 fresh t1–t3、04 并行、t4 沿独审；不转移职责 | A 专用测试节点一次性用途链接；T 执行入口原段 | 历史特例保留，不推成常设授权 |
| 46 | 核空闲原子取标志、收尾释放；无需常规申请/窗口/汇报，尊重他人，前端例外 | A 专用测试节点；T 执行入口 | 保留 |
| 48 | CT201 开发/缓存非测试，测试 CT 无公网仅获准 LAN 制品、源码传输 | A 专用测试节点；T 测试节点网络与缓存 | 收拢重复 clean/非开发机措辞 |
| 50 | 逐节点准备 uv/Rust/Docker/Dolt/数据；核 LAN 端点可达，不假定 bridge 地址通用 | A 专用测试节点要点；T 测试节点网络与缓存 | 细节留 T |
| 51 | UV_OFFLINE=1，DEV_OFFLINE 只准备；canonical identity 不受机器 index 改写 | A 专用测试节点/uv 消费段；T 测试节点网络与缓存 | 保留 |
| 52 | Cargo 离线预填充，PATH 与三 override 禁设，四工具同 selector | A 专用测试节点；T 测试节点网络与缓存 | 保留 |
| 53 | 依赖/锁/基础镜像变化先 CT201 取得，经 LAN 预填并记录来源/摘要/时间 | A 专用测试节点 DC67；T 测试节点网络与缓存 | 保留 |
| 53 | 04/CT108/真实数据不代理；05 仅受限主机/无凭据/用完停、记录范围/时段/用途、非证据；缺缓存停止补齐重跑 | A 专用测试节点 DC67 要点；T 测试节点网络与缓存 | 细节留 T |
| 54 | Docker 基础与包制品均本机或获准 LAN；RS 可达 cache URL 或已校验依赖基础镜像 | A 专用测试节点链接；T 测试节点网络与缓存 | owner 澄清 Q5，保留两种方式 |
| 55 | backend/worker 六类依赖输入变化：CT201 clean --save 构建 lock-tag、LAN load；完整输入/镜像/归档/时段记录 | A 专用测试节点 backend/worker 要点；T 测试节点网络与缓存 | 细节留 T，未删触发输入 |
| 55 | backend/worker PRELOADED=1、DEPENDENCY_BASE_IMAGE、NETWORK=none；保留本机 Compose build，不设 PREBUILT | A 专用测试节点 backend/worker 要点；T 测试节点网络与缓存 | 变量清单留 T |
| 55 | 旧 p6-backend-image-exit 前产品整镜像预构建 | A 专用测试节点历史版本链接；T 测试节点网络与缓存“历史版本说明” | 移走阶段性展开，规则未删除 |
| 56 | 跨节点 config/全 DiffID 非 inspect ID；同节点包闭包本机 ID，容器等价另判 | A 专用测试节点“镜像身份”；T 测试节点网络与缓存 | 保留引用名与语义 |
| 56 | RS/client 各自预置依赖；client revision 不符由 gate 重建、不得手工 rmi | A 专用测试节点“镜像身份”；T 测试节点网络与缓存 | 保留 |
| 57 | 不关闭 Docker 本地/loopback/端口/LAN；cache miss/端点不可达停止，不回 CT201 | A 专用测试节点 DC67/运行前提；T 测试节点网络与缓存 | 收拢重复 |
| 58 | 日志节点与时间、缓存来源/使用方式；凭据不记，proxy/cache 只摘要 | A 专用测试节点日志/缓存记录；T 测试节点网络与缓存 | 收拢重复 |
| 59 | DC68 限定错误仅一次重做、失败日志 SHA、记录原因/修正/结果；再次失败/已触对象/缓存/身份停止；runner 失败不续验 | A 专用测试节点 DC68/运行前提；T 测试节点网络与缓存 | 保留 |
| 61 | BatchMode echo OK；clean 已提交 worktree | A 专用测试节点运行前提 | 合并重复 |
| 62 | 本节点单飞，跨节点按宿主/用途并行 | A 专用测试节点运行前提 | 合并重复 |
| 63 | carried 同节点同 worktree、manifest 无节点身份、不跨节点比较 | A 专用测试节点闭包段；T 执行入口 | 保留 |
| 64 | runner/carried/真实数据 hostname/起止时间、handoff 节点 | A 专用测试节点运行前提 | 合并重复 |
| 65 | 同 V 真实数据/门禁可跨节点并行，同档完整旅程不跨节点 | A 专用测试节点运行前提 | 保留 |
| 66 | 节点不可用等待、无开发机 fallback、临时换节点 owner 决定 | A 专用测试节点运行前提 | 保留 |
| 67-68 | root SSH 磁盘 TMPDIR、不改 pytest-of-root 属主；默认 BASETEMP 未设，显式验证例外 | A 专用测试节点运行前提 | 保留 |
| 69-72 | Python 包固定 Hypothesis 路径、TMPDIR 空则 /tmp；manifest 前与退出/中断清理，仅专属目录 | A 专用测试节点 Hypothesis 要点；T Hypothesis 隔离与按包闭包沿用 | 细节留 T |
| 72-74 | 不保留跨运行反例缓存、输出反例分析；runner 失败停止；worktree .hypothesis 仅 focused | A 专用测试节点运行前提/Hypothesis 要点；T Hypothesis 隔离与按包闭包沿用 | 细节留 T |
| 76-80 | GATEWAY_TEST_PACKAGES 合法六包、固定顺序、重复/未知 exit 2、默认全六包；拆分/Compose 临时目录/五锁不变 | A 专用测试节点选包段；T 执行入口 | 具体示例留 T |
| 80 | S5 最终门禁/发布全包 | A 专用测试节点选包段；T 执行入口/Hypothesis 隔离与按包闭包沿用 | owner 澄清 Q3，改项目最终门禁/发布全六包 |
| 82-86 | Rust fmt/clippy/test 三步全执行、任一失败、无 crate 排除；旧 impl 已删、新 adapter 的 Python/Arrow 由 backend 测 | A 专用测试节点 Rust 要点；T Rust 包与 backend 的 Rust 扩展（DC48） | 现行规则保留；S2a 历史描述留 T |
| 86-88 | CARGO_TARGET_DIR 外置固定路径，只缓存不入闭包，使用前/退出清理；额外参数只传 pytest | A 专用测试节点 Rust 要点；T Rust 包与 backend 的 Rust 扩展（DC48） | 细节留 T |
| 90-94 | maturin/uv 只改 rs 不重建，runner 强制重装、Git tree build input 校验、不符 manifest 前失败；focused 同样先重装 | A 专用测试节点 Rust 要点；T Rust 包与 backend 的 Rust 扩展（DC48） | 细节留 T |
| 96-104 | wrapper locked sync 后逐包 JSON manifest；Python tree/legacy/venv/Hypothesis/cache/version；uv 排除 pycache/pyc/pyo；dirty 拒绝 | A 专用测试节点闭包要点；T Hypothesis 隔离与按包闭包沿用/镜像身份等价与结果沿用 | 细节留 T；补明确同步在 manifest 前 |
| 99-104 | Rust tree/lock/selector/五锁/脚本/cargo config/四工具/解释器/设置指纹，排除 target；无 uv/Hypothesis/pytest | A 专用测试节点闭包链接；T Hypothesis 隔离与按包闭包沿用 | 完整成分留 T |
| 104-108 | compare 逐项变化；合格 V 实跑包通过、整次 exit0、clean/HEAD；部分包 runner 可来源，闭包变重跑 | A 专用测试节点闭包段；T Hypothesis 隔离与按包闭包沿用 | 保留硬约束，命令留 T |
| 108-111 | backend/RS Docker/daemon/build/base/service/dependency/client ID 与开关，prebuilt inventory，dependency-base 变化重跑、凭据摘要 | A 专用测试节点闭包链接；T Hypothesis 隔离与按包闭包沿用 | 细节留 T |
| 111-113 | 逐包摘要/运行或沿用/来源 V/日志；链直指最初实跑 | A 专用测试节点闭包段；T Hypothesis 隔离与按包闭包沿用 | 保留 |
| 114-117 | manifest 前打印 Hypothesis 且不存在，同包两遍共用、退出清理；carried 同路径且无残留，否则重跑 | A 专用测试节点 Hypothesis 要点；T Hypothesis 隔离与按包闭包沿用 | 删除重复展开，T 补打印细节 |
| 119-122 | 门禁前提与 clean；RS require_clean_worktree 的失败机制 | A 专用测试节点运行前提；T 镜像身份等价与结果沿用 | 删除重复 clean；删除 dirty 必然失败的重复解释，约束保留 |
| 123 | 运行中不写/提交/重建/retag，client e2e 正常本机重建例外 | A 专用测试节点运行前提/镜像身份 | 保留 |
| 124-125 | linked/detached legacy 链接、Git exclude；缺失 58 例失败 | A 专用测试节点运行前提；T 执行入口 | 命令保留；58 例解释留 T |
| 126-127 | 同机不得其他 Dolt/Compose，整机 /proc、8000 | A 专用测试节点运行前提 | 保留 |
| 128-129 | worktree 外日志、起止 HEAD、runner exit、tee/pipefail | A 专用测试节点运行前提 | 保留 |
| 131-140 | 阶段性非全量，backend/RS marker unit/integration/serial focused 命令 | A 专用测试节点阶段性范围；T 执行入口 | 命令示例留 T（补 backend 示例） |
| 142-150 | backend/RS 两遍、三小包单进程、Rust 先跑；worker auto/可显调48，parallel_safe 逐项隔离、backend 无例外、serial 固定0 | A 专用测试节点并行要点；T 执行入口 | 细节与命令留 T |
| 152-155 | tmpfs BASETEMP 绝对路径、只临时目录非服务卷，持久化/恢复/快照真实文件系统 | A 专用测试节点 tmpfs 要点；T 执行入口 | owner 澄清 Q1：专用测试节点 |
| 157-165 | prepare-dev-dependencies 不跑测试，internal 显式 index、pypi 剥离、DEV_OFFLINE sync locked offline | A 专用测试节点 uv 要点；T 内网构建环境变量 | 完整细节留 T |
| 167-179 | uv-consume 入口与接入脚本、run/sync locked/隔离、no-sync 先 lock-check 再 run、五锁前后检查漂移不 restore、改锁授权再同步 | A 专用测试节点 uv 要点；T 内网构建环境变量 | 细节留 T |
| 179-183 | 提交前 ruff/mypy 命令 | A 提交前 | 删除跑测试内的重复命令 |
| 185-190 | Docker build network 默认/覆盖、bootstrap 仅 build、无 runtime ENV、client host/default，不改服务网络 | A 专用测试节点构建参数要点；T 内网构建环境变量 | 细节留 T |
| 194-195 | FD7 来源与详细规则链接 | A 前端测试（FD7） | 保留，链接直达 |
| 197-198 | frontend 根目录、不入 vnext/后端闭包/context，独立 runner | A 前端测试（FD7） | 原文保留 |
| 199-201 | 前端节点 07/05/04、不用 CT108，阶段 clean 完整取证 | A 前端测试（FD7） | 原文保留 |
| 202-204 | 固定工具链镜像、宿主不装 Node、CT201 save/load/config与DiffID、版本变重传 | A 前端测试（FD7） | 原文保留 |
| 205-206 | npm 锁缓存 CT201/LAN、容器 npm ci offline、缺失停补重跑 | A 前端测试（FD7） | 原文保留 |
| 207-210 | mock 等不占用，真实 Compose DC70 原子占用与收尾、计时占用阻止所有前端运行 | A 前端测试（FD7） | 原文保留；新增一句由脚本执行占用 |
| 211-213 | 前端外置日志/HEAD/exit/SHA、镜像/缓存来源/节点 handoff | A 前端测试（FD7） | 原文保留 |
| 214-216 | FE2 起双宽截图/外置SHA、逐项视觉复核、偏差 owner | A 前端测试（FD7） | 原文保留 |
| 220 | 四 marker strict 拼错失败 | A 写测试 | 保留 |
| 222-223 | 禁止手写 skipif，Dolt 门禁唯一 conftest | A 写测试 | 保留 |
| 224-226 | 真实 Dolt integration、import fixture 自动分类 | A 写测试 | 保留 |
| 227-228 | 固定时间预算必须 serial | A 写测试 | 保留 |
| 229-234 | 移开 Dolt 再 unit、静态扫描不可靠、命令示例 | A 写测试；T 分类正确性怎么验 | owner 澄清 Q2：仅专用节点按占用规则 |
| 238-239 | 纯解析校验映射禁止真实 dolt init fixture 与全 mock 反模式 | A 测试性能红线 | 保留 |
| 240-242 | 同构输入/错误参数表，不复制测试函数 | A 测试性能红线 | 保留 |
| 243 | 构造按批，不循环 spawn | A 测试性能红线 | 保留 |
| 244-246 | 新 HOME 预置 Dolt config 关 versioncheck；offline | A 测试性能红线 | 保留 |
| 250 | 精确钉版本，用 uv add --dev | A 改依赖 | 保留 |
| 252-258 | RS lock 变更同步 Dockerfile UV_LOCK_SHA256、命令 | A 改依赖 | 保留 |
| 262 | 直接 main、必要并行短分支尽快合回 | A 主线开发与阶段边界 | 保留 |
| 263 | 附注 tag、上一 tag 到候选区间审核 | A 主线开发与阶段边界 | 保留 |
| 264-265 | 只读 detached 审核、非主工作区测试、运行期间所有人不得写 | A 主线开发与阶段边界 | 保留 |
| 266-267 | DC30 调试/取证分开，focused 非完整；收敛最终 runner/真实数据各一次；DC33 范围 kickoff/退出 owner | A 主线开发与阶段边界 | 保留 |
| 268-269 | 未经 owner 不推送，不改已引用提交，P5 §8 流程 | A 主线开发与阶段边界 | 保留 |
| 273-275 | 按边界触发镜像构建，同轮可合并到最终 HEAD | A Docker / Compose 验证 | 保留 |
| 277-279 | 强制项1 Dockerfile/依赖/基础镜像/构建传输 | A Docker / Compose 验证 | 保留 |
| 280 | 强制项2 entrypoint/Compose/env/health/readiness | A Docker / Compose 验证 | 保留 |
| 281 | 强制项3 UID/GID/权限/volume/mount/socket/pidfile/broker/helper | A Docker / Compose 验证 | 保留 |
| 282 | 强制项4 依赖容器边界的 startup/shutdown | A Docker / Compose 验证 | 保留 |
| 283 | 强制项5 容器 e2e/harness 或宣称当前 HEAD gate | A Docker / Compose 验证 | 保留 |
| 284-286 | 强制项6 阶段/S3ready/发布/production；发布最终 fresh，阶段可等价 | A Docker / Compose 验证 | 保留 |
| 288-290 | 纯逻辑/tests/docs 覆盖且未触界可延期；旧结果非当前HEAD，等价唯一例外 | A Docker / Compose 验证 | 保留 |
| 292-293 | 镜像等价限阶段退出/S3ready，合格 carried 不重跑 | A Docker / Compose 验证 | 保留“镜像身份等价”文字入口 |
| 295-296 | 等价1 合格来源 clean/权威/HEAD/exit/不写 | A Docker / Compose 验证 | 保留编号 |
| 297 | 等价2 diff 不触前五边界/e2e/harness | A Docker / Compose 验证 | 保留编号 |
| 298-306 | 等价3 RS label重算；backend manifest 同节点同WT检出H compare；非重建ID比较、权限/非Git本地态、禁止换WT；exit合入后清理WT | A Docker / Compose 验证第3条要点；T 镜像身份等价与结果沿用 | 机制留 T；第3条和保留WT硬约束仍在 A |
| 308-309 | 条件不满足最终重建重跑；同提交 runner Compose 不重跑，provenance同次 | A Docker / Compose 验证；T 镜像身份等价与结果沿用 | 保留 |
| 311-316 | 包与镜像沿用分判，backend完整context/uv/设置/镜像/prebuilt，Compose随包，但V..H另判 | A Docker / Compose 验证要点；T Hypothesis 隔离与按包闭包沿用/镜像身份等价与结果沿用 | 细节去重留 T |
| 316-319 | Hypothesis/cache 路径/内容/权限；runner前后清理、carried同路径无残留、worktree仅focused | A 专用测试节点闭包要点；T Hypothesis 隔离与按包闭包沿用/镜像身份等价与结果沿用 | 删除 A Docker 段重复 |
| 320-323 | vnext tracked tree+0o7777路径祖先根权限；dockerignore后非Git类型权限内容；未建模ignore拒绝 | A Docker / Compose 验证链接；T Hypothesis 隔离与按包闭包沿用 | 细节留 T |
| 325-327 | 每轮记录HEAD/是否重建理由/最后image revision/source-tree/延期节点/来源 | A Docker / Compose 验证；T 每轮评审记录 | 保留 |
| 331-332 | Phase0–9及维护比例化 policy | A 全局比例化保障 | 保留 |
| 334-335 | 新机制对应现有威胁/损失/consumer/可复现故障，否则平台最小机制 | A 全局比例化保障 | 保留 |
| 336-338 | 权威不可逆/可恢复durable强验证；derived/临时/内部优先bounded重试诊断人工 | A 全局比例化保障 | 保留 |
| 339-341 | 同euid单信任域；UID/helper/IPC/evidence等先改Contract/ADR，非普通Finding扩大 | A 全局比例化保障 | 保留 |
| 342-343 | 测Contract非穷举步骤、唯一owner、业务命名、删机制删mock探针 | A 全局比例化保障 | 保留 |
| 344-345 | 认证授权/secret/输入/逃逸/非shell/资源/事务CAS/跨scope不可比例化跳过 | A 全局比例化保障 | 保留 |
| 349-353 | ADR0012单信任域，协作/I/O/保护/path/root/symlink；恶意同euid新机制须先reopen | A Artifact cleanup 保障边界 | 保留 |
| 355-357 | cleanup业务命名非轮次，不可逆Dolt/mainCAS/DB/跨root强验证 | A Artifact cleanup 保障边界 | 保留 |
| 361-366 | 五Python ruff/mypy含RS strict/tests，禁止省略，wrapper命令 | A 提交前 | 原文保留；本轮失败单独记录且经owner例外授权提交 |
| 368-375 | Rust变化fmt/clippy，05/06占用、target外置与命令 | A 提交前 | 原文保留 |

## 3. 删除与历史说明

“删除”仅指重复文字或过时表述，不删除约束：

| 项 | 处理与理由 |
| --- | --- |
| 重复 clean、hostname/起止时间、禁止开发机测试 | 汇到 A“专用测试节点”的运行前提；原文其他出现处删除重复句，T 保留细则 |
| A 两处 Hypothesis 生命周期/沿用说明、两处闭包展开 | 删除 A 的重复展开；固定路径、创建前提、打印、清理范围/时机、失败处理、carried 条件完整保留在 T；A 有硬约束与链接 |
| A“跑测试”中的 ruff/mypy 示例 | 删除重复示例；A“提交前”原文与命令保留 |
| dirty 导致 RS Compose 必然失败的解释 | 删除重复解释；clean 资格、dirty manifest 拒绝、不得用 dirty 来源均保留 |
| S2a 前 cargo 排除 -impl | 基线已经删除该限制，本轮没有再次删除规则。实际 runner 第 309–312 行调用全 workspace fmt/clippy/test，无 `--exclude`；S2a 状态解释留 T，A 写当前不排除 crate |
| backend/worker 旧整镜像构建 | A 不展开，T 保留为“历史版本说明”；S1c/S2a 已退出、测量参考交付已退出。本轮不主张历史流程失效，不删除原冻结产品的复现依据 |
| “开发机”tmpfs、“S5”最终门禁 | 按 owner 已确认含义改写，见下一节，不擅自扩大阶段门禁 |
| FE3a handoff §8 第 5 条节点纪律 | 不收入，沿用 FD7 现行 07/05/04 分工与 mock 无占用规则；不带入 FE3a 最后一次运行的临时占用要求 |

原文件其余所有二级/三级标题、比例化、artifact cleanup、依赖与主线边界保持。AGENTS 修订为 240 行、约 1.28 万字符，字符数约为原文 62%、行数约 64%；略高于目标上沿，以保留硬约束和 FD7 原文为先。

## 4. 前端收入来源与 owner 问题

| 收入项 | 来源 | 新位置 |
| --- | --- | --- |
| 独立入口、必填 session、脚本自取释放占用、已有 marker exit 3 | 本任务明确指令；FE3a handoff §8.1；实际脚本 269–290 行 | A FD7 新增一句；T“真实 backend e2e” |
| mkdir → marker → flock → 残留核对；清理 → 核对 → flock → marker → rmdir；失败保留 cleanup-failed | handoff §8.1，FE3 kickoff §4.2/4.8 | T“真实 backend e2e” |
| 输入来源一句指向 Q10 | 本任务指令、kickoff §4.6 | T“真实 backend e2e”，不复制派生输入清单 |
| secret 0644/服务用户可读、只外置 | handoff §8.3，实际脚本 session/token chmod | T“真实 backend e2e” |
| M1 clear_refs=5、VmHWM、renderer 判断、主进程只报告、manifest size、data-phase | handoff §8.4，kickoff §8.4，下面 Q4 | T“真实 backend e2e”；kickoff §8.4 回链并澄清基线 |
| 全部日志字段及 M1 报告字段 | handoff §8 末段，kickoff §4.9/8.4 | T“真实 backend e2e”；既有 FD7 日志段保留 |
| 双向引用 | 本任务指令 | kickoff §4、§8.4 → T；T → kickoff §4、§4.6、§8.4 与 handoff §8；kickoff §4.1/§12 更新落文状态，历史审核记录不改 |

以下问题均先提交 owner，本会话未自行定规则；2026-11-08 本会话回复已确认：

| 问题 | owner 确认 | 落点 |
| --- | --- | --- |
| Q1 tmpfs “开发机”与专用节点冲突 | 改为专用测试节点，仍保持持久化/恢复/快照真实文件系统要求 | A 专用测试节点；T 执行入口 |
| Q2 移开 Dolt 的执行地点缺失 | 明确仅专用测试节点按占用规则执行 | A 写测试；T 分类正确性怎么验 |
| Q3 S5 是否指 P5 收口 | 已核 P5 执行计划 §8.9/DC35 和 G12；owner 确认改“项目最终门禁与发布门禁必须运行全部六包”，其他阶段仍按范围和闭包规则 | A 选包段；T 两处最终门禁表述；不改历史 P5 文件 |
| Q4 handoff/实现用重置后 VmHWM，kickoff 写 VmRSS 基线 | owner 选“统一为 VmHWM 基线，保留 VmRSS 记录” | T M1 与 kickoff §8.4；不改实现和原测量数字 |
| Q5 A 允许 RS cache URL 或已校验依赖镜像，T 却称 URL 必设 | owner 选“保留两种方式并同步澄清” | T 测试节点网络与缓存，保持 A 原义 |
| Q6 本轮五包静态在既有 backend Ruff 错误处停止 | owner 选“允许文档提交，记录失败” | 仅为本轮纯文档提交例外，A“提交前”不变；不修其他会话代码 |

当前没有未答的条文歧义。尚待 owner 安排独立审核、接受最终文本，并另行决定推送和节点同步。原任务说“同步三个节点”，本轮不自行把它扩大为五节点；实际同步节点清单随后续授权明确。

## 5. 引用核对与文档检查

编辑前实际运行 `git grep -n "AGENTS"`，共 451 处，逐条保存在 [引用核对清单](agents-restructure-2026-11-08-references.tsv)，含固定基线文件/行、完整原引用文字与处理结果。清单不是只抽查标题：涵盖标题引用、carried 第 3 条、backend/worker、镜像身份、DC67/DC68、命令、历史行号与普通文件引用。

- A 原全部二级/三级标题按顺序逐字不变；T 原有标题全部保留，只新增两个细节标题。
- “镜像身份等价”第 3 条仍为第 3 条，“权威入口的运行前提”“镜像身份”文字定位仍有效；backend/worker 粗体条目标识保持原样。
- 历史 `AGENTS.md:11` 等行号按历史报告的固定提交解释，本轮不改写已引用证据。当前规则去向由 §2 给出。
- FE3 kickoff 两处“条文尚未写入”现状文字更新；§15 的历史处理记录以及历史 handoff/审核报告原文保留。
- 所有本轮新增/修改的本地 Markdown 目标与标题锚点核对；`git diff --check`。这是 CT201 上的文档静态核对，未在开发主机运行产品测试、lint、类型检查或构建。

## 6. 验证与边界

五包静态使用 06 的独立 clean detached worktree `/home/dev/gdds-agents-restructure-20261108-static`，起止 HEAD 均为基线 `4b224865e42e4c3ea4a5d9d595a36ca34db0b874`；不切换节点 main。该提交为本轮整理前的代码，检查时主工作区的其他会话仍在编辑产品代码，不混入本次检查/提交。

| 项 | 实际结果 |
| --- | --- |
| 节点/时间 | `gw-dms-06`，2026-11-08 06:01:31Z–06:03:02Z |
| 前提 | 核空闲后原子取得本人 marker；无运行容器、Dolt/pytest/Cargo/rustc/Ruff/mypy 冲突；clean detached、legacy 链接、外置 TMPDIR/Cargo target |
| 来源/缓存 | CT201 Git bundle 经 LAN scp；SHA256 `5b3b9e03212e981c72705fa5d99dc1f8200fa91d21aa6a3597dc6ecdf239bf11`，两端相同；节点既有 uv/Cargo/toolchain 预填缓存，无新依赖/镜像传输，无 proxy，UV_OFFLINE=1/CARGO_NET_OFFLINE=true |
| 工具链 | 仓库 selector Rust/cargo 1.97.0；rustfmt 1.9.0、clippy 0.1.97，同工具链；无 Rust overrides |
| shared_kernel / repository_contracts / repository_client | 各 Ruff/mypy 通过，mypy 分别 34/15/26 files |
| backend | Ruff F401：`snapshot_materialization/__init__.py:11` 导入 `canonical_comparison_profile` 未使用；mypy 未执行 |
| repository_service | 因前项失败停止，未执行；不报告五包全通过 |
| 结果/收尾 | exit 1；起止 HEAD 一致、worktree clean；本人 marker 已释放，后续只读确认 marker 不存在；保留 worktree/日志 |
| 日志 | 06 `/home/dev/gdds-test-tmp/agents-restructure-20261108-logs/static.log`，SHA256 `8b02aebb106d07deaf8c3974fa0548e66ab9da978c47fe292eba91db4de620a8` |
| 脚本 | 06 `/home/dev/gdds-test-tmp/agents-restructure-20261108-static.sh`，SHA256 `efbdd2f14ad56f4dcc8343e9fbc8ad64cf15e30bbc80f0ae38881f92bd837ef7` |

这不是权威 runner、carried、容器或真实数据验收；没有重复测量。首次本地 bundle 命令使用裸 commit 而非命名 ref，Git 报 `Refusing to create empty bundle`，未生成包、未触被测对象。一次修正使用 main ref 后成功，bundle 含所需固定基线；节点检出的是指定基线而非运输 ref 的最新文档 HEAD。失败诊断与命令保留在 worktree 外（§7 列补充检查记录）。backend 的实际 Ruff 失败未重试，未做后续检查，按 owner Q6 提交文档。

本轮仅文档，**不触发镜像重建**；没有新的 image revision/source-tree 验证，不宣称当前 HEAD 容器通过，不计算 carried、不把旧镜像当本轮结果。最后验证镜像：本轮未读取/未验证；延期：本轮无新增容器门禁，产品会话按其自身最终候选判定。

## 7. 交接

请 owner 安排独立会话，在只读 detached worktree 按 §2 的每条规则对照固定原文与新位置，检查两文件无丢失/冲突、§4 的 owner 澄清落实，以及引用清单全部有效。审核未通过前不宣布本次治理整理接受。

审核通过且 owner 确认后，由 owner **另行授权推送**；之后对授权的三个节点逐个确认没有占用标记，再仅 fast-forward 各节点 main，不切换任何在用 worktree。本轮不推送、不办理该同步。

补充检查记录：CT201 `/home/dev/gdds-agents-restructure-20261108/document-check.log`，SHA256 `7bb4fa46e550b2da7de8d9c4d30aff3df25ce367efe7364ab9e66ffcd5ec67e3`：12 个 A 标题、28 个 T 旧标题保留，19 个新增/修改本地链接有效，原 A 非空规则行均有映射，451 条引用清单原文一致且其 AGENTS 链接有效。机械检查先发现对照表中部若干行号偏移，修正后通过；不把覆盖检查代替独立语义审核。实际字符数为 20,648 → 12,813（62.05%）。
本地 bundle 准备诊断转录（明确标注为工具结果转录，不冒称新执行原始日志）：`/home/dev/gdds-agents-restructure-20261108/bundle-preparation-note.txt`，SHA256 `9630c058f53fc0ce42a9e011da1599a39dffe4949ca250a2ac981e54e4b71866`。
