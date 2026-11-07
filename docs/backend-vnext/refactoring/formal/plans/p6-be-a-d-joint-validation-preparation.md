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

## 6. 首轮实际失败与修订（不作合格来源）

04原run的backend parallel为**3383 passed / 3 failed**、207秒、批次exit1；三处均期望旧`unknown artifact_id`，实际正确typed拒绝消息为`artifact ref is not available`。异常类型与缺失拒绝/未发布不变量均命中，协调和同独审独立读trace确认，非缓存/身份/保全异常。最小修订 **`2ae2d825ea775e5ef35c449d924a9edcc6aa8b81`** 仅两原test owner三行expected message，vnext变为`220ba52851eebf2886a109c32d6dd7f8c1ff80a2`；产品src/benchmarks/Rust/harness/Contract无diff，待原独审静核。原runner自身serial另已出现F，尚无完整trace/最终exit；不能将2ae预判为完整最终修订。

原运行期间不改节点WT、不重tag，暂停启动后续验收/carried。失败整次不能作任何包的合格carried源；旧S2b公共fixtures已变，下一合格最终runner仍须六包。05已启动的fresh原run现command/final0、endclean/owner真，完整JSON/镜像/结束UTC待同审核收；若最终增量确属test-only且产品/consumer不变，可按逐步骤影响审查引用其a999实际来源，不冒称新候选实跑，也不默认重跑整档。

04 backend serial完整为**56 passed / 4 failed**、637.99秒（runner记录639秒）。失败为Archive dualactor、History zero-write/restart、ordered History、Submit removed-tables四Compose，均止于共用helper对实际preview逐项resolution POST被409 `BASELINE_VERSION_CONFLICT / subject digest does not match current anomaly`拒绝。根/实施者/同独审分别核原trace及`application/archive/audit.py`273–287：当前next只按kind/code/target四字段取首项，合法FULL同一Submission INITIAL/MODIFIED同时GENERATION_TIME_MISSING有不同subject，第二项被错比首项；不是旧message或caller伪造。

设计者已静核业务设计§6.2/§7.1回执无冲突：这是已审逐项subject实现缺陷，原字段候选集合内再按command.subject_digest精确选取，缺集合/错digest仍拒绝；不能按code合并接受或只信caller digest绕过其余字段/当前snapshot。auth/scope/CAS/actor-bound append/旧成功replay/冻结payload保持，后续sequence及持久subject_payload取该精确项。原audit owner补双side同code独立接受/序列和伪digest拒绝小向量，修后同审；原runner结束后先必要focused/一个共用resolution真实wiring，再六包。当前原RS批次仍自身收尾，不写被测WT、不重tag、不启动外部后继验收；05影响判断暂停直至实际完整修复diff明确。

精确修复 **`eff1dc531b7f011d870bb100912f079cf500c497`** 已固定，vnext **`56720104af34a1eb677336f57bdbc07444a56615`**；相对a999仅audit选择21行+原audit67行回归向量+2ae三文案，无consumer/harness/Contract/digest/版本/auth/CAS/replay变更。原独审`7f8eb20a3e`§19静核通过（活动说明随后`7338dab5dd`精度更正）：保留四字段候选集合及两原409，再精确digest；双side独立接受/序列、冻结side、伪digest拒绝、独立撤销+Start阻塞的小向量已静审，实际补验待做。设计者明确无设计冲突。

原04整次于**12:59:22Z**结束，command/final1、end exact a999/clean/本人owner真；原失败来源绝不作任何包carried。本人cleanup后复用原04门禁WT/本人占用做该失败必要诊断：三原owner两marker、backend静态及一条共用resolution Submit removes_deleted Compose，固定新actual source后执行，未动已释放05/06或修改budget。通过后才启动新六包。05旧成功路径未影响的代码论证已静核成立：原成功蕴含四字段首项digest相等，新精确搜索仍取同项、后继不变；实际有限步骤引用仍待必要补验收敛，不冒称新HEAD fresh或image/package carried。

## 7. 05实际fresh证据与释放

实际a999 fresh于**12:40:42Z**结束，command/final0、endclean/owner真；原run log SHA=`66cdeb8c906434bbdfbdf2b63ee438c4537f1a9aab10bedafe5d3a36189e83c1`。[原结果JSON](/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/p6-be-ad-final-05/run-fresh-t1-8skuj66m/final-result.json)为原log offset53374/length40044原字节行，SHA=`505f9731235430c21c53ff39316bec1f0f4e22b7465275bdea12e4a04823cf1d`，18步序完整；v1 identity N/A、v2 SAME_PROJECT、repeat NO_CANONICAL_CHANGE。FULL helper实际严格核完整双pair；result里默认initial_to_modified单view的summary.pair_count=1不等于完整FULL只有一pair。

| 完整tar | 实际bytes | closure entries | 适用逻辑records | GET秒（只报告） |
| --- | ---: | ---: | ---: | ---: |
| v1 MODIFIED_ONLY Preview | 2834432 | 354 | 0 | 0.529 |
| v2 FULL Preview | 2660352 | 118 | 12（2 records closures） | 0.214 |
| repeat-v1 Preview | 2055680 | 105 | 0 | 0.163 |
| History | 2153472 | 114 | 12 | 0.183 |

均由原consumer逐项核原metadata/closure/size/raw SHA及适用逻辑摘要；不把小共享header-only向量计入4完整tar。实际镜像身份三config/全部54DiffID已核；bridge来源准确为**原tool报告的image-tag inspect IDs与事后保留镜像同机桥接，加fresh build/up证据**，没有另取running-container ID，不改原证据字段或虚构采样。

LAN完整副本 `/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/`；旧10-run index SHA=`5f551201c49fabaca2cc1e6a86e2cf72283b78b3602068357931a8b3fbbdf459`，释放后[metadata索引](/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/p6-be-ad-final-05/release-index.json) SHA=`f0bb6b07ec725f5243105ecb0bca750e5edf2a3553303b4c1ad43e1c66749a87`链接旧index、其生成run及release，共11run四项SHA均独审相符。cleanup12:43:52Z/0，log SHA=`987eaad6058cf1a2289d26e0ab000f9c6b5d110b5956f03951e96fd502f2414d`；**12:46:02Z** cmp本人owner后释放，release log SHA=`f4a1625250c8f88f17db56e1ab4222fbe5d97f8010254d07aff59b78cc661b54`。独审12:47:58Z另核marker不存在、a999 WT clean、项目容器/卷/网络/8000空。WT保留，未清他人资源/缓存/历史证据。

以上只成立a999实际来源。最终全部04失败修复后，仍须逐步骤审查diff是否影响05引用；不预先给2ae/后继候选fresh实跑或沿用结论，不以05成功抵消04失败。

## 8. 修复候选49403与后继验证

原04失败run log完整SHA=`d84088eda0bdb8f9995c27ef5dacb5252524ed1343b3d14542d6f053e949ff23`；六份起始manifest按原log exact byte ranges保存，同run `original-starting-manifests/`，index SHA=`af518bd41c7c56940c60bbd14a8d4be3c94ed0db549e928fda636b3a585fca36`，原独审已逐份核原字节/包名/HEAD/总摘要/offset。原RS实际1744+207pass/1skip，整次仍失败，不作包carried。本人cleanup **12:59:57Z**/0，log SHA=`a1256931a8ea5a51869b3f07592ed259583c0994b460cfad6cc6e52af618260f`，运行容器/8000/Dolt/pytest/编译及runner Hypothesis/CargoTarget均空；保留04本人marker继续门禁修复。

原独审已核六条完整诊断argv与§19一致。协调固定当时clean main **`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`**（tree56720104），仅04于**13:02:42Z** source_ready：`transfer-6zMscy3m` exact expected/advertised/checkout/clean/prepare0；bundle SHA=`a7601befad4ee00dbb4bf9a5f478a9c28a133dc43856ffcd20f98f1dbf9040be`，prepare SHA=`58a4091b59382f04958eaf7a3f1d7cedef88d518467c0c7004a3747501c3d9a7`。guard仍原b86cb3，本人owner连续有效，旧run/manifests未改；主线短窗口已解除。

同49403逐项extension核/三原owner两marker-n4/n0（真空5=N/A）/backend ruff+mypy/唯一Submit removes_deleted Compose，prebuilt及BASETemp unset、base preload/networknone不变；RS复用本任务a999tag，源码a687/13cb未变，backend/worker正常当前build。任失败先停原审处理；全部通过后同49403直接新六包，不因后继纯docs提交再改测试WT或重复05。当前仅已开始诊断，未报新权威通过。

修复实际补验：三owner非serial **66 passed**（13:03:22–34Z），`run-audit-owner-focused-6Wj1fzDF` log SHA=`f4a1ccb21e02c8e7de47096a49eb725f277aa372857ecb04072a0e097660be69`；serial66deselected/原exit5=N/A，`run-audit-owner-serial-HWIvxAoB` log SHA=`fff0e3fbfcc3990313d4c84864e35b88bd483bf46a90292ab4e18ae2e801ba06`。extension input0、backendruff0/mypy516files0。唯一共用Submit removes_deleted实际Compose **1 passed / 52.67s / 13:05:21Z command/final0**，`run-resolution-compose-cgJnj4OW` log SHA=`b9ea0e253ecbcdd0d671d00e2941a54645db1b7806f37783643e599bd4da2f9e`，end49403clean/owner真；backend/worker按当前source正常build。此真实复现补合法双subject→Archive路径，不称自然05已覆盖新增双subject分支。

全部必要诊断通过后，同49403于**13:06:41Z**正式启动最终六包 `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-04/run-authority-six-final-DTWWhQP4`，48workers及所有已审离线/base env不变，没有切源、重复05或增加角色。当前执行中，原failed run独立保留，不报最终GO。

## 9. 最终核收待填

当前候选49403/tree567201，F6及三文案修复的必要诊断均通过；原独审`9c0e098bbe`正式接受05 a999旧成功路径的有限步骤引用，来源/新增分支边界见上文。最终04六包仍在执行，末exit/六manifest/current images/资源收尾及最终handoff待核，尚无联合最终GO。

拟提交Owner的DC33最终真实数据范围为：05实际a999一次fresh t1（18步、v1/repeat MODIFIED_ONLY及v2 FULL双pair、四完整Preview/History tar，按实际49403 diff限界引用）；异常/关闭重提/self-only及新增同码双side由04当前Compose、原owner和本次共用复现覆盖。不新增t2/t3/t4或性能测量，不把未知W1/W2值记为通过。此为具体范围提案，**尚未取得Owner最终范围确认**；门禁/独审齐后交Owner确认，再按仓库规定另办退出。FE3同tar解析/摘要/OPFS证据独立pending，不把后端核收当FE3完成。不推送、不改写引用提交、不自动打退出tag、不启动S3。
