# BE-a / 归档核验 / BE-d 联合验证准备

2026-11-07。协调者维护；Owner 已授权 A1→V1→V2→D 及联合最终验收准备。依据[联合 kickoff §1.1](p6-be-a-d-kickoff.md#11-实施授权与实际起点owner2026-11-07)、[设计终审 §6](p6-be-a-d-archive-design-review.md)、AGENTS / testing-conventions / DC33。本文只固定收敛后的执行与交接条件，不把准备状态记为验证通过，不自动办理阶段退出或扩大业务范围。

## 1. 收敛条件与角色

A1 最终独审 `c1ee962755`；V1 最终独审 `5dc01deeb5`，产品 `c229582a9e`，旧 V1 `3dd4735dce` 不作最终依据。V2、D 须各自完成固定候选、同角色复审、06 定向证据及清理。最终联合产品提交、vnext tree、各 owning Contract / schema / checkpoint / digest / HTTP 版本、D encoder 制品清单待实际收敛后填写，不能预先用 main dirty 或旧镜像替代。

D 启动时将本工作单及最终工具接线、集中验证执行/证据核收纳入该节已授权实施者和独审者职责；不临时复用已结束小节角色，不新增第三角色。D 小节 GO 与联合最终证据结论分别记录，两角色在其约定收尾职责完成后结束。

## 2. 门禁与工具清单

| 项目 | 收敛后的执行范围 | 当前状态 / 准备责任 |
| --- | --- | --- |
| 04 权威 runner | 在本轮独立 clean 已提交 WT 上由 `vnext/scripts/run-tests.sh` 集中执行实际受影响包，保留起始 manifests、六包逐项结论和总 exit；不逐轮全量 | 未执行；公共 fixtures 已变化，预计六包均须实际运行，以最终实际闭包核收 |
| 当前容器 | 最终实际候选的 backend/worker 与必要依赖镜像，按既有预置 dependency-base 离线本机构建；权威 runner 中相同 Compose 旅程不额外重跑 | 未执行；06 各节 Compose 只作各节定向证据，不能冒充 04 当前结果 |
| 05 fresh t1 | 一次集中功能旅程，实际输入 FULL / MODIFIED_ONLY，Submit / Review / Archive、Preview / History 完整 tar | 未执行；V2 负责新异常接受 consumer，D 负责真实 FULL 输入入口、完整 tar consumer；命令待实际 CLI 落地后固定 |
| 异常真实接线 | 来源/时间异常阻塞与逐项理由、关闭不归档→新上传重提、self-only；用必要小型生产 wiring 补足自然 t1 未触发的场景 | 复用合格各节证据前先核最终影响，不重复整套权限/规则矩阵 |
| FE3 同制品互通 | D 生产 encoder 的同字节 ASCII / 中文 / 非 BMP tar，前端解析、摘要和 OPFS 安装 | 前端 owner 负责；Owner 手动转发，不把后端 GO 当作 FE3 完成 |

`test_input_closure.py::COMMON_GIT_COMPONENTS` 将整个 `vnext/fixtures` 作为各包的 `shared:fixtures`。静态 Git 对象核实：S2b V 的 fixtures tree 为 `9cff7f677d4fda582747e33c1394d1fe2a07d7e1`，V1 c229 / 当前基础候选35c4为 `606b05d28a214369cf842c52fbc2c228e3bd43d2`（新增 facts golden）；六包相对该旧来源均有明确闭包变化。V2 亦计划新增 archive v2 golden。因此不能仅凭某包源码未改而记 carried，也不为争取 carried 删除必要 golden 或改闭包政策。若最终各包均受影响，直接运行六包，无须检出或改动原基准 WT 来制造沿用。若仍有未受影响证据，严格按原合格来源/同节点同 WT/实际 manifest 比较核收，不口头沿用。这是静态范围准备，不是实际 manifest 比较或门禁结果。

已有来源仅作定位：S2b V `a6876d560050285321fd9f62942d590a03f35d64`，04 原 WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate`，原始起始 manifests `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-m24-a6876d56/six-package-authority-01/original-starting-manifests/`。本文没有访问、检出或修改该 WT、镜像、卷或证据。

## 3. 真实旅程的交付边界

现有 `real_dump_journey.py --scope full` 表示步骤范围；它本身不证明上传 manifest 的 `input_completeness=FULL`。D 必须交付实际 FULL 功能入口及必要定向验证，并在此页/实施 handoff 写可复核的最终命令、输入配对和各分支覆盖。正常数据应保持已有比较摘要；时间/来源接受只冻结原诊断和明确理由，不伪造 PASS，不用 force 或无理由自动接受。

Preview 和 History 必须完整读取 `application/x-tar` 响应，并按 owning Contract 校验原 manifest / closure、全部普通成员的路径、顺序、尺寸及相应物理/逻辑摘要；不能只解 `manifest.json`。报告单列 GET 开始到读取完成时间及实际字节数；READY / Operation 完成锚保持原定义。这些是本轮功能/传输证据，不作为 W1/W2 或正式性能测量。

按 kickoff 暂定 05 fresh t1；不借用 S2b E 授予 06 的 t1–t3 例外，不新增 t2/t3/t4、大输入或正式性能矩阵。退出前将实际候选、范围、各分支/异常来源、必要沿用依据及剩余项组成具体 DC33 确认包交 Owner；已有小节开工授权无须重复申请。未取得所需范围确认及退出手续前，不宣布联合验收/阶段退出完成。

## 4. 执行前提与停止点

- 先 SSH BatchMode 核连通，现场尊重有效占用，原子获取本节点标记；无提前预约或反复请示。04 权威运行时本任务不在同宿主 06/07 发起重负载；05 可按节点用途跨节点并行。CT108 正式测量和原基准资源不占用。
- 新建本轮独立 clean 已提交 WT、legacy 链接、WT 外日志与 TMPDIR；源码经获准 LAN 传输。节点环境/缓存/依赖基础镜像实际可用，`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，Rust 扩展强制同步并核 Git tree build input。依赖身份、config digest/全部 DiffID、离线构建和 provenance 沿既有规则，不输出凭据。
- 固定被测提交后不在 WT 写入/提交或并行重新 tag 镜像。权威 runner exit 非 0 先停下处理失败，不继续 carried / 后续验收。DC68 仅用于满足原条件、未触及被测对象且无副作用的自身操作错误，失败日志及 SHA 保留；不得据此连续重试产品或前提失败。
- 日志记 hostname、起止 UTC / HEAD、命令/脚本身份、原始 exit 及 SHA；handoff 记节点、缓存来源、镜像身份、起始 manifests 和每包实际运行/合格沿用。清理确认无本任务服务、进程、端口占用后只释放自己的标记，保留证据与必要 WT 至最终绑定完成。
- 前端判断确实阻塞时给 Owner 具体场景、实际接口/制品、问题与推荐，暂停该依赖等手动转发回复；其余已授权工作继续。未收到回复不能当作同意，也不猜测前端修复完成。

## 5. 最终核收待填

当前尚无联合最终代码候选、04/05 运行、最终 manifests、DC33 最终范围确认或退出报告。D 收尾时补齐实际提交/角色、节点占用和命令、证据索引、每包判定、当前镜像绑定、同制品前端交接状态及明确未决项；协调者整理供 Owner 审查的具体结果。不推送、不改写引用提交、不打退出 tag、不启动 S3。
