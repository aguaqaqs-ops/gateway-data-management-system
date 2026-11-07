# BE-a / 归档核验 / BE-d 联合验证准备

2026-11-07。协调者维护；Owner 已授权 A1→V1→V2→D 及联合最终验收准备。依据[联合 kickoff §1.1](p6-be-a-d-kickoff.md#11-实施授权与实际起点owner2026-11-07)、[设计终审 §6](p6-be-a-d-archive-design-review.md)、AGENTS / testing-conventions / DC33。本文只固定收敛后的执行与交接条件，不把准备状态记为验证通过，不自动办理阶段退出或扩大业务范围。

## 1. 收敛条件与角色

A1 最终独审 `c1ee962755`；V1 最终独审 `5dc01deeb5`，产品 `c229582a9e`，旧 V1 `3dd4735dce` 不作最终依据。V2 最终独审 `9ec62e82ad`，产品/Compose `f8fb796f02`、handoff `3cd4400f9f`，06 已10:39:24Z清理释放。D本地里程碑及固定handoff已通过：产品 `0ba45e5ef83f54bfb2585f963f9518d32086f942`、vnext tree **`0301aee3a39e3a5dfc37360e9c2062e660eb01ea`**，独审`6ad7e54fa0`、handoff`41386e12e6`核收`cd2d395fbc`，06于12:05:51Z本人释放。D encoder同tar/OpenAPI及其SHA见[前端制品包§3](p6-be-d-frontend-handoff.md#3-已实际生成的同字节制品)。当前完整04/05执行稿为`ec586cbc2d`的[D handoff §9](p6-be-d-handoff.md#9-联合0405执行清单稿静核协调对齐后启动尚未执行)，独审最后核可后协调固定当时clean main同一完整SHA用于两节点；此处不是04/05通过或image carried声明。

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

V2实际交付后静态更新：f8的fixtures tree为 **`594aa44c74aeb08f4f8ac584963a3634fae6b355`**，已含facts与archive v2 golden；六包共同输入相对S2b仍明确不同。D清单不新增业务golden，但不改变最终实际闭包核收责任。

已有来源仅作定位：S2b V `a6876d560050285321fd9f62942d590a03f35d64`，04 原 WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate`，原始起始 manifests `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-m24-a6876d56/six-package-authority-01/original-starting-manifests/`。本文没有访问、检出或修改该 WT、镜像、卷或证据。

## 3. 真实旅程的交付边界

现有 `real_dump_journey.py --scope full` 表示步骤范围；它本身不证明上传 manifest 的 `input_completeness=FULL`。D 必须交付实际 FULL 功能入口及必要定向验证，并在此页/实施 handoff 写可复核的最终命令、输入配对和各分支覆盖。正常数据应保持已有比较摘要；时间/来源接受只冻结原诊断和明确理由，不伪造 PASS，不用 force 或无理由自动接受。

当前 `_assert_preview_summaries` 明确假定一个 pair；FULL 实际有 `baseline_to_initial` 与 `initial_to_modified` 两个 pair。建议在同一 fresh t1 的 v1 用 MODIFIED_ONLY、v2 用 FULL（INITIAL=v1、MODIFIED=v2）集中覆盖，实施清单固定最终形态。下游业务摘要/identity consumer 必须按真实 pair 身份适配，完整 tar 验证覆盖两 pair 全部成员及共享 binding；只改 mode 字符串不构成 FULL 证据。

V2主线归档consumer已改为显式`GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON`（`{subject_digest或issue_code:非空reason}`）；缺理由即失败。联合执行清单须写真实采用的理由映射及其验收目的，保留原异常，不捏造数据产生原因或无理由自动接受。D精确清单`cf2091eadd`已选同一次t1 v1 MO/v2 FULL配对，最终以实际落地CLI/断言/证据固定命令。

最终profile已找到实际fresh t1来源：06 `/home/dev/gdds-test-tmp/artifacts/s2b-e-m24-t1-a6876d5600/command.json`，只读提取实际host CLI为`--kernel-threads 1 --kernel-memory-budget-bytes 25769803776`，原命令文件SHA=`1e725ec83e54c2ad40ee7d631216673b310e02817970e07b516d5e983a2009ae`。本轮05 t1沿此host N1/M24GiB；Compose worker独立核其N1/M24GiB、32GiB envelope/8GiB reserve/单active。不得用Cargo/pytest workers4、早期N4/24MiB示例、t3 cal的48GiB或06物理96GiB代替真实profile；不新增试预算矩阵。当前尚未执行本轮05命令。

Preview 和 History 必须完整读取 `application/x-tar` 响应，并按 owning Contract 校验原 manifest / closure、全部普通成员的路径、顺序、尺寸及相应物理/逻辑摘要；不能只解 `manifest.json`。报告单列 GET 开始到读取完成时间及实际字节数；READY / Operation 完成锚保持原定义。这些是本轮功能/传输证据，不作为 W1/W2 或正式性能测量。

按 kickoff 暂定 05 fresh t1；不借用 S2b E 授予 06 的 t1–t3 例外，不新增 t2/t3/t4、大输入或正式性能矩阵。退出前将实际候选、范围、各分支/异常来源、必要沿用依据及剩余项组成具体 DC33 确认包交 Owner；已有小节开工授权无须重复申请。未取得所需范围确认及退出手续前，不宣布联合验收/阶段退出完成。

## 4. 执行前提与停止点

10:10:34Z 协调只读准备快照：04=`gw-dms-test-04`、05=`gw-dms-test-05`，BatchMode `echo OK` 均0；当时均无 busy marker，均有 `/home/dev/gateway-real-dumps/datasets.json`，均列出 `gateway-backend-deps:lock-d054366c02fa` / `lock-c668cef8e47e`。只核存在性和连通性，未运行测试/容器、未读改原基准 WT、未核完整缓存/输入摘要或镜像身份，也未获取/预约节点；不能用该快照代替执行时前提。

- 先 SSH BatchMode 核连通，现场尊重有效占用，原子获取本节点标记；无提前预约或反复请示。04 权威运行时本任务不在同宿主 06/07 发起重负载；05 可按节点用途跨节点并行。CT108 正式测量和原基准资源不占用。
- 新建本轮独立 clean 已提交 WT、legacy 链接、WT 外日志与 TMPDIR；源码经获准 LAN 传输。节点环境/缓存/依赖基础镜像实际可用，`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，Rust 扩展强制同步并核 Git tree build input。依赖身份、config digest/全部 DiffID、离线构建和 provenance 沿既有规则，不输出凭据。
- LAN fetch后对linked WT一律按已验证的明确commit SHA创建/checkout，不依赖另一个WT的`FETCH_HEAD`；前节已实际遇到不可见导致的操作失败，不在04/05重犯。此项只是调用精度，不新增传输/证据框架。
- 固定被测提交后不在 WT 写入/提交或并行重新 tag 镜像。权威 runner exit 非 0 先停下处理失败，不继续 carried / 后续验收。DC68 仅用于满足原条件、未触及被测对象且无副作用的自身操作错误，失败日志及 SHA 保留；不得据此连续重试产品或前提失败。
- 日志记 hostname、起止 UTC / HEAD、命令/脚本身份、原始 exit 及 SHA；handoff 记节点、缓存来源、镜像身份、起始 manifests 和每包实际运行/合格沿用。清理确认无本任务服务、进程、端口占用后只释放自己的标记，保留证据与必要 WT 至最终绑定完成。
- 前端判断确实阻塞时给 Owner 具体场景、实际接口/制品、问题与推荐，暂停该依赖等手动转发回复；其余已授权工作继续。未收到回复不能当作同意，也不猜测前端修复完成。

## 5. 已固定候选及实际准备

完整执行稿ec586已由原独审`467abe6e10`§17静核通过。协调提交当前态后固定clean main **`a999869c7f4714c95ee9a5b82866e52cd265e377`**，vnext仍0301。04于12:26:16Z、05于12:26:17Z分别现场核空闲后原子取得本人marker；新WT及证据根原先不存在。两节点LAN namedHEAD bundle准备分别为04 `transfer-IUOsNXCG`（12:26:25Z）、05 `transfer-cwKZNNWF`（12:26:38Z），均exact a999/clean/prepare0/source_ready。主线短提交窗口已解除，测试WT仍固定该同一SHA。

两节点claim/source/对应guard安装与prereq均0，独审核实际offline/toolchain/BASETemp unset。base身份实际从docker-save config原字节及全部DiffID核对：backend与RS base逐项等06已审来源；04 log SHA=`e6f4738c33e358d600058427415b72801f55eecfc70698fce118aa29a99fe066`、JSON SHA=`dee4c57577d2527aa18a56e43f87a4b8d5ac8bf440df381d6e45705d3c46b86e`，05 log SHA=`fa4fd7e5faf6ec08147bc5d37d197c297a347be2c64032f024e2f35c7fc4fe0e`、JSON SHA=`b5343a80611bc0635e026c0a5ee78041ed01f16c7a3affff9043605a33015ccf`。Python/Rust/client base分别保留本节点全身份，不把无06来源者伪称source match。d054输入实际重算0，无新依赖或缓存补造。

RS离线build均0：04 `run-repository-build-AqbozR9J` log SHA=`58e74acc3be3c67bbb38a5250a4b6fb417ebb704094c36168197da0891032d6f`，05 `run-repository-build-pbMa965Y` SHA=`9634b847c87f62fe535a9aadb071c77869281a55cb70bfcd9bc9d1dfa157dbf2`。04 **12:32:24Z**启动唯一六包runner `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-04/run-authority-six-n3pnBrzg`；05 **12:32:31Z**启动强制扩展同步 `run-backend-sync-3U0NQiGH`，核input后再唯一fresh t1。当前尚无完整runner/journey结果，不将中途步骤通过拼为联合通过。04/05独立资源，本任务06已释放，CT108不使用。

05证据精度沿已审consumer：逐项验证完整metadata/closure路径、顺序、size/raw SHA及适用records逻辑摘要，最终持有现有JSON聚合counts/digest/bytes/time、原log及8项固定reason文件；不声称每成员原字节或所有原HTTP diagnostic/resolution响应已外置留存。原diagnostic事实/逐项接受审计的不变量由未变V2 owner与04规则、05实际流程合并核收，不为报告临时扩建持久取证字段。

05强制sync已0，log SHA=`0ad22dedda643d6e8e4698838545153a91efce311586470929fb0835b03fa6a9`；`run-extension-build-input-913obiwP`核expected=installed=e6ac，log SHA=`d3d9e128c4342a3d7644c84abcd33d4854018c7c6bf840761279673360c1bdb7`。**12:35:37Z**启动唯一fresh t1 `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-05/run-fresh-t1-8skuj66m`，保持已审FULL/MO CLI、N1/M24GiB与单env显式reason JSON，非resume。04原六包run继续，当前均未完成。

## 6. 最终核收待填

产品tree已收敛0301；完整执行稿已固定，04 workers48/六包一次runner及Compose，05 fresh t1 FULL/MO、N1/M24GiB、8项明确测试库reason、四份节点专用guard/路径与停止边界均见D handoff§9。原独审静核及协调固定source后，两节点已按既有授权开始；当前尚无完整runner/journey结果、最终manifests、DC33最终范围确认或退出报告。D收尾时补齐实际提交/角色、节点占用和命令、证据索引、每包判定、当前镜像绑定、同制品前端交接状态及明确未决项；协调者整理供Owner审查的具体结果。不推送、不改写引用提交、不打退出tag、不启动S3。
