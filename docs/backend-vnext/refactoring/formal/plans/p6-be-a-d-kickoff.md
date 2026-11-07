# BE-a / BE-d 与归档业务核验：联合 kickoff（设计已审）

状态：**设计已独审 GO；Owner 于 2026-11-07 授权 A1→V1→V2→D 及联合最终验收准备。A1/V1已本节GO（V1 F5闭环，最终报告5dc01deeb5），现启动V2，D按序待启动**。实时候选/角色/证据见[协调交接](p6-be-a-d-coordination-handoff.md)。Owner已确认DC89/DC90：BE-a待审核归档门禁与过期APPROVE、BE-d最终closure成员规则、归档生成时间及来源核验的业务方向。原BE-a审核`fcbfb4c1a0`只覆盖2026-11-04原稿，本修订候选`16472197b4`及业务链路已由报告`a5d87540e6`独审GO。旧基准exit不再是前置，S2a/S2b已退出。此文不向FE3声明依赖已交付。

引用基线：`ebb0047383300a3754a4be6a6a78f72286600c83` 的 [前端 kickoff §4.4/§5/§9](../../../../frontend-vnext/frontend-kickoff.md)、[后端交接 §2.3](p6-backend-session-handoff.md)、DC64/DC67/DC70/DC73。任务业务范围来自已确认的前端决议；本页新增安排已通过设计独审，具体实施起点、角色及验收范围仍须在实施kickoff填写确认。BE-b 设计与实现不并入这两项。

原本人撤回/Workspace设计引用main `d0a8143d804e158e16b0712cc5f2aa007066f9cb`，前端Q16来源`55e6c0083c`。本轮源码核查main `a8de5e5346d2421e1237d52e8ff3f5025dc84aea`；目标依据[BE-a设计](p6-be-a-design.md)、[BE-d设计](p6-be-d-design.md)、[归档业务核验设计](p6-archive-business-validation-design.md)及DC89/DC90。旧阶段文档的“待S2a/基准退出”排期已被新决议取代；历史审核结果保留其原范围。DC74整包体积的正式测量落点不在本次改动中默默定稿。

## 1. 发出前填写

前置已满足：`p6-s2a-exit`→`53b676a6298d408ccda3a85ee73c7ea223a2311a`；`p6-s2b-exit`→`9220f3cdecba7df3e50fec00d77d1dd9efb0f678`。发实施提示词前填写当前main、修订设计独审提交、具体小节/验收范围、Owner实施授权、角色会话及模型/思考强度。原S2b已结束角色不复用；如需新角色先按Owner要求说明用途及模型并报告，不自动创建额外角色。

建议小节：A1 BE-a→V1源时间/内容事实与冻结→V2来源/时间规则及归档审计→D BE-d；D的设计与纯传输准备可前置，最终顺序在设计审核后确认。每节代码/证据分别可审，只有联合最终候选才集中跑必要完整门禁。所有内容串行main优先，确需并行才短分支，不为实施并行制造同节点正式测量竞争。

原基准线继续独立，冻结worktree、镜像tag、输入、卷和证据均不改；本轮新规则和tar工具只进入新产品候选，引用测量按版本/节点分别说明。

### 1.1 实施授权与实际起点（Owner，2026-11-07）

- 实际起点为 clean `main` **`8fbdcb7d54097a45cbbb7511f130f0585249930a`**（已用 `git rev-parse` 核实，不回退历史候选）。设计候选 `16472197b486908b4ed16cd4b4305f49360d7c38`、最终独审报告 `a5d87540e66313b830e9960cc6bc174b6ddb5e40`；B1/B2 已关闭，N1 按 BE-d §2.1 交付前端。
- 协调者会话 **`01a1b4f1-df13-7331-b3c4-77bb560203f2`**，Owner 指定 GPT-6-Sol / xhigh；负责进度、角色、节点、通信、kickoff 与交接，原则上不改产品。设计者仍为 `01a1ac15-9b35-7ea0-9952-c4a31d3d4f6d`，只承担设计澄清与决策问题。
- 授权正常修复、Contract/文档同步、本地提交、按范围验证、每节实施者与独审者。每节独审通过后自动启动下一节，无须逐次申请；顺序先 A1、V1、V2、D，若前端主要受下载阻塞可说明理由将 D 提到 A1 后。
- 实施默认 GPT-6.1-Sol / xhigh；明确独立任务可用 GPT-6-Luna / max。Luna 同根因连续两轮无效、上下文混乱或跨层接线失败，可在停写、保留候选/diff/失败证据并确认无遗留任务后，重建为 GPT-6-Sol / xhigh。不能靠换模掩盖设计冲突。独审 GPT-6.1-Sol / xhigh 或 max，原则上只写自己的报告；本节修复沿用原审核者，每节结束后新建下一节两角色。工具未提供销毁能力时只记录停止/结束，不声称删除。
- A1 两角色均选 **GPT-6.1-Sol / xhigh**，原因是本人权限、scope/replay、同快照指针及归档事务不变量跨层相连；不拆给额外实施者。角色 ID、候选与证据持续记入[协调交接](p6-be-a-d-coordination-handoff.md)。额外角色或约定外模型须先向 Owner 说明。
- A1 实际文件、Contract、测试 owner 与交付边界见[工作单](p6-be-a1-work-order.md)。协调文档与角色产品文件分开归属，只显式暂存本人文件；共享 main 不 reset/restore 他人修改，不推送、不改写引用提交。
- 06 日常 focused/Contract/必要差分及小型接线，05 默认最终 fresh t1，04 联合权威/容器/carried；不占 CT108。先现场核空闲再原子取得本节点标志，完成清理后释放；不反复申请窗口。04 权威取证时避免同宿主重负载干扰。严格 clean 已提交测试 worktree、离线缓存、节点日志与身份规则。
- 联合最终候选准备范围：04 受影响包权威 runner、必要 Compose；05 一次 fresh t1 覆盖 FULL/MODIFIED_ONLY、Submit/Review/Archive、Preview/History 完整 tar；小型真实 wiring 补异常接受、关闭重提与 self-only。未受影响证据只按闭包复用；此处不沿用 S2b E 的 06 真实旅程例外，退出前仍按 DC33 请 Owner 确认最终真实数据范围。
- 未授权 S3、接管原基准、改冻结资源或推送。产品交付、FE3 同制品互通、阶段退出分别记录；本次设计 GO 不替代产品验收。后续设计页中“待实施确认/尚未启动”等局部旧措辞，以本记录及实际小节状态核对，不反复请求已经给出的授权。

## 2. BE-a 实施提示词（已授权；实际工作单见 §1.1）

你是 BE-a 后端实施会话。先读 AGENTS、本文、[BE-a 设计补充](p6-be-a-design.md)、前端 kickoff §5（引用上方提交）、Business Lifecycle、P5-5C 状态机设计、DC64/DC73/DC75。按已填写的 main 起点工作。

范围：

1. 完全删除 `RETURN_FOR_REVISION` 动作、`RETURNED_FOR_REVISION` 状态和事件：domain/application、HTTP review/history literal、control DB 基线 CHECK、读写映射、Contract 与测试。没有兼容/迁移要求；删除旧路径，不保留别名。不得误删其他审核、撤回或拒绝语义。
2. 修正 `POST /v1/history-compares` OpenAPI：首次 202、幂等回放 200；`POST /v1/workspaces`：新建 201、已存在 200。让 schema 声明与实际响应吻合，保持现有运行时业务行为。
3. 当前源码起点涉及 `domain/submission/review.py`、`application/submission/review.py`、`http/schemas/{review,history}.py`、`infrastructure/control_db/schema.py` 与两创建路由。先盘点所有枚举使用者、持久序列化、拼接字符串与测试，handoff 给全量清单，不以历史“约 18 文件”作完成判据。
4. 按设计补充 §2 为 WorkspaceResponse 增加 active_submit_attempt_id/active_submission_id（required nullable），在新建/已有工作区路径一致返回；应用查询必须同事务快照读取 Workspace、占用与版本，不新增持久字段。
5. 按设计补充 §3–§4 新增 withdraw_own_submission，覆盖本人 GET review、POST WITHDRAW、当前权限及归属下的幂等回放；保留 reviewer 能力与状态/事务屏障。同步 session 示例与独立 self-only 测试身份。此项是授权语义修改，不归为纯 DTO 修改。
6. 同步 P5-5C 授权/回放/HTTP 条款、Business Lifecycle 与 Workspace HTTP 说明；具体条款和实现路径见设计补充 §5。
7. 前端 OpenAPI 快照在 FE3 由前端刷新；不编辑 `frontend/`、前端设计文档、AGENTS 或 testing-conventions。
8. 按BE-a设计§9增加同baseline PENDING归档硬门禁与过期baseline新APPROVE拒绝。Start写事务重查，保留Submit active gate、REJECT/WITHDRAW出口与原成功回放顺序；不得把共同未知来源或时间异常的完整业务核验冒称在A1已经完成。

程序验收：

- 通过公开 HTTP 输入验证旧动作拒绝且无业务写入；剩余动作的合法/非法状态转换、权限、幂等与并发条件仍成立。domain 测试负责状态机不变量，HTTP 测试负责边界，不复制两套证明。
- 新基线 DB 不能写入被删状态/事件；合法状态写入与 History 映射正常。既有 schema 不匹配按现有启动拒绝机制；不增加迁移器。
- 实际路由与 OpenAPI 同时断言两组首次/回放或已存在响应的 status、response schema；被删枚举不出现在生成的 OpenAPI 中。
- 逐项完成设计补充 §6 的程序验收：新权限 GET/POST/replay；本人/他人/跨 scope；权限撤销；终态回放；指针全生命周期与同快照；self-only 用户的真实 wiring Compose 旅程。不得用 reviewer 全权限身份代替 self-only 验证。replay 权限与披露由 `tests/test_review_http.py` 的公开 HTTP 测试负责；事务测试负责完整性、CAS、原子释放与失败无部分写入，不重复整套权限矩阵。
- 静态检索区分历史文档记录与活动实现/Contract；历史 DC 不改写。focused 集合含 RS `-m unit`，防止跨包过时断言遗漏。
- pending预览与直接Start拒绝、finalize/approve/reject/withdraw/归档竞争、过期新APPROVE拒绝但合法历史replay成功，依BE-a§9唯一测试owner补验。空草稿不阻塞，多个已通过候选仍逐项排除确认；失败无部分写入。

按 §4 共用流程执行。真实数据建议为 05 t1 一次完整旅程（schema/持久状态改变，不沿用旧 DB）；审核动作使用合成 HTTP/Compose 旅程补全 t1 未覆盖的状态；04 权威 runner 与当前 HEAD 容器门禁。真实数据范围先在 kickoff 确认，exit 前再次由 owner 确认。完成交代码候选与 handoff，由 owner 转后端审核会话，不自行宣布 exit。

## 3. BE-d 实施提示词（已授权，按小节顺序启动）

实际准备工作单见[BE-d工作单](p6-be-d-work-order.md)；待前节GO后填写起点并新建本节角色，不重复请求开工授权。

你是 BE-d 后端实施会话。先读 AGENTS、本文、前端 kickoff §4.4/§5、Comparison Bundle/Surface Contract、artifact 保护与读取接口、DC64/DC67/DC73。从已填写的 main 起点工作。

目标：按[BE-d设计](p6-be-d-design.md)让Preview/History一次请求返回完整、不压缩POSIX tar（application/x-tar，长路径pax）。普通成员依次为manifest.json、artifact-closure.json、最终closure每个entry按其logical_path各一个文件，不添其他业务成员。

成员规则已由Owner确认：共享由assembler的最终closure表达，下载层不按source_ref/hash再次去重。一个共享entry只发一次；相同源若有两个合法不同logical_path，则必须发两个普通文件，不用hardlink/symlink替代。对照前端fixture与真实closure固定向量核实，不改前端解析以容忍残缺包。若assembler不满足已声明Contract，单独报告producer缺口，不擅改业务digest或golden。

传输要求：

- 响应头前校验 manifest/closure 和全部成员可读，大小与引用一致；缺失/损坏走现有稳定错误语义，Contract/OpenAPI 列明实际错误码。授权与精确 workspace/project scope 校验在读取前完成。
- `Content-Length` 计算包括 header、padding、pax 和结束块，必须等于实际响应字节数；ETag 使用 bundle digest（HTTP 引号格式正确）。使用有界分块，不把整包读成 bytes。
- 读取期间沿用现有保护/文件句柄生命周期以应对协作 cleanup；头前预检不能保证后续 I/O 永不失败。发送中异常应中断流，不能吞异常补成成功 tar；断连、错误及正常结束都释放资源。不新建持久下载状态机。
- 准备阶段必须实际执行后才返回StreamingResponse，不能把预检推迟到generator第一次迭代。避免为全包同时持有所有FD/mmap；保留S2b已修复的资源边界，按BE-d§3给出buffer/handle上限与验证。
- 不增加按 artifact 读取接口或导航产物。传输格式只包装既有 closure；业务表、records、风险与摘要保值。将 Comparison Bundle 的传输格式与 OpenAPI 同步到目标形态，无 JSON/tar 双格式兼容。
- `benchmarks/real_dump_journey.py` 改读 tar 中 manifest，解析并核对 closure；记录 GET 开始到完整读完的时间与实际响应字节数（只报告）。不改变 READY/operation 完成的既有计时锚，不把旧 manifest JSON 字节数当作整包。

程序验收必须参数化覆盖两个公开路由以及真实生产 wiring，不只测 fake BundleReader：

| 场景 | 检查 |
| --- | --- |
| Preview MODIFIED_ONLY、FULL、DATASET_REPLACEMENT；History 两节点/三节点 | manifest/closure 顺序，成员集合/顺序、长度、摘要、全部表及各侧引用闭合；新增/删除/未变表均按 Contract 存在 |
| 共享产物、同源不同路径、长路径、空文件/空表 | 最终closure一对一规则；pax长度；实际响应长度等于Content-Length；无额外业务成员或链接成员 |
| 无权限/跨 scope、结果未就绪/过期 | 原鉴权与状态边界稳定，未泄露成员 |
| 头前 manifest/closure/任一成员缺失或损坏 | 稳定错误响应；不返回成功 tar |
| 流中读取失败、客户端断连、cleanup 协作 | 不产生可误认完整的响应，资源释放；复用现有 artifact 保护能力 |
| closure 路径异常 | 绝对路径、`..`、重复冲突路径及非普通文件按现有 server-owned path 边界拒绝；不引入同 euid 对抗模型 |

通过公共 HTTP 下载完整 tar 后，由程序逐项核验 closure 的逻辑 SHA/raw SHA（按各自 Contract）、成员映射与已冻结的业务结果；不能仅解出 manifest 即 PASS。合成测试承担边界矩阵，真实数据承担完整闭包与传输旅程，不重复每一内部步骤。

真实数据建议：05 t1 完整旅程含 Preview 与 History 下载；t4/2× t4 体积采集跟随获授权的后续 P6 测量，完整 BE-c 报告建议 S6（DC74 草案），不为 BE-d 单独重跑全部基准。04 权威 runner 包含真实服务路由/容器旅程；阶段退出须有绑定当前 HEAD 的容器门禁，即使没有 Dockerfile 修改也不能写“无需门禁”。前端 FE3 随后验证浏览器接收与本地解析；本任务不改前端源码。

## 4. 联合任务共同执行约束

- DC81比例化执行：06/05focused、Contract、差分和必要小Compose，五包ruff/mypy；Rust变更在专用节点fmt/clippy与相关测试。修订收敛后04最终候选运行受影响包权威runner，未受影响包按闭包沿用；当前HEAD容器绑定不能由旧阶段证据替代。不每节/每轮重复全量runner、真实全旅程或合成输入生成。
- 专用节点 clean 已提交 worktree；先 SSH 连通，按 DC70 原子获取占用，不抢占计时测量。日志在 worktree 外，记录 hostname、起止时间/HEAD、exit、SHA256。预填充缓存，`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`；backend dependency-base、RS/e2e 依赖模式按 AGENTS/DC67；取证不用代理。
- 调试不跑全量取证。runner非零、产品失败、缓存缺失、身份/结果不符先停止该次验收；按DC80主动诊断、最小修正与独审，不无限等待或原样重试。自身工具错误按DC66/DC68适用范围处置，不绕过拒绝。
- 手工清理本地 DB 仅针对本任务可重建数据；不动其他会话保留卷或证据。只显式暂存角色文件；不改写已引用提交，不擅自推送。handoff 列改动、验收映射、逐包结果、真实数据范围、镜像重建理由与 revision/source-tree、遗留；设计问题经 owner 转交。

## 5. 确认记录与当前缺口

- 历史BE-a原稿审核通过（`fcbfb4c1a0`），非阻塞测试归属建议已采纳；不扩称本修订独审通过。
- Owner2026-11-07已确认DC89/DC90业务方向：pending硬门禁、过期新approve拒绝、tar一对一、当前轮次initial/modified匹配与共同未知根、逐项人工接受、UTC源序最后有效时间及最后非最大诊断，以及无法接受异常时“有理由关闭、不归档”的释放出口。
- 当前设计已独审，A1及后续V1/V2/D实施已获本次Owner授权（§1.1）。BE-a/BE-d/新增核验均未产品验收，S1–S2b退出状态不变。
- 首轮独审`e92afaa53f`要求修订B1/B2，另有N1交接项；2026-11-07设计修订已固定时间提取grammar/范围/规则身份及向量（业务设计§4.1），200候选的异常上界8N+1=1601、选择确认1和197,265-byte Start预算（§7.1）。这些技术选择不改变Owner业务方向；候选`16472197b4`经报告`a5d87540e6`复审GO，B1/B2关闭。
- 其余实施收口项：facts/DTO/checkpoint/digest具体变更位置、已定时间向量的native seam、初始空基线边界接线、前端新增诊断消费、最终真实数据与角色安排；按业务设计§9执行，不将时间语法/引用容量再留给实施者选。若独审发现超出已确认业务的冲突，先交Owner讨论。
- N1：现有frontend PAX按JS字符数解析UTF-8字节length；BE-d必须标准编码并交ASCII/中文/非BMP共享向量，前端owner修consumer且使用同一真实tar验证，是FE3解除依赖的额外条件（BE-d§2.1）。本次只明确交接，不编辑前端源码或替前端启动任务。

## 6. 归档业务核验实施小节（已授权，按小节顺序启动）

具体文件/owner/测试边界见[V1工作单](p6-v1-work-order.md)、[V2工作单](p6-v2-work-order.md)，当前状态见协调交接。

V1先完成Rust源序时间提取、initial/modified内容身份、Preview/checkpoint与T1/Submission事实冻结；时间取version_manager.saved_time最后可解析值并统计max，不能在排序后重算。V2再做当前轮次来源图、时间关系、确认及Start，来源未知和人工接受分开表达；同时完成§10有理由关闭的业务出口、统一终局处置、History/Review读取及前端契约。具体业务、状态形态、案例、事务及测试owner以[业务链路设计](p6-archive-business-validation-design.md)为准。

约束：不把原SQL引用当持久事实本身，不在Start重扫文件或调用Repository，不恢复Python计算路径；生成时间不是上传/归档时间。无需新增Archive Operation、batch状态机或通用策略框架。schema直接改基线，checkpoint/DTO与golden同步，原基准保留卷不升级、不回填。

建议联合最终验收：04受影响包runner及必要真实容器接线；05 fresh t1同时覆盖FULL/MODIFIED_ONLY、Submit/Review/Archive与Preview/History tar，异常用小型合成wiring验证。若BE-a单独先退出，则其候选按影响取证，后续候选仅依闭包复用，不能预先承诺不重跑。新验证范围待kickoff与退出前Owner确认，06真实全旅程不是本稿自动授权。

面向FE3交接必须给出：实际实现提交、OpenAPI及错误/权限矩阵、tar固定向量、正常与异常归档流程和测试证据。来源/时间诊断页面超出现有FE3稿的部分由前端设计owner修订；不静默把新验收推给前端实施者。

V1按`gateway-vnext/configuration-generated-time/v1`实施，不改变Shared Kernel原table scalar；V2同步拆分confirmation/anomaly refs限制及HTTP/application/replay校验，不沿用旧200上限。D后端交付与FE3 UTF-8 PAX同制品互通分别记录，不能以旧ASCII fixture替代。

## 7. 本轮文档校验记录

本轮仅修改7份设计/计划文档，未改产品、测试、锁文件、节点配置或前端文件。`git diff --check`通过，7份文档的本地文件链接及代码围栏检查通过。核查基线main与S2b实际V=`a6876d560050285321fd9f62942d590a03f35d64`的`vnext` tree同为`92c1d6403d7cf3cbc4cf2746100699ed8d028ba7`；五包ruff/mypy沿用该未改源码的06实际通过记录（[E独审记录](p6-s2b-e-review.md)，log SHA `8af309bc680872fb21d0e6981fde0109881b744199f65d2661265ec90e075d97`）。没有重复测试、编译或容器构建，也不把该旧静态记录当作新业务验收。

本轮不触发镜像重建：没有image/deploy/runtime边界改动。最后实际产品镜像仍绑定S2b V；新业务实现后的镜像与最终候选验证另办。本轮自检不是独立设计审核；未推送、未改写阶段tag、未启动S3或任何产品实施角色。

### 7.1 首轮独审后的修订记录

首稿`6995fe46a8`的独审报告为`e92afaa53f`，结论需修订；原报告不改写。本次仅修订业务核验、BE-d、联合kickoff、执行计划和DC90技术细化五份文档，对应B1/B2/N1。以标准JSON形状完成静态字节预算（非产品测试），文档diff/链接/围栏核对通过；vnext tree保持§7值，静态证据适用范围不变。原独立审核角色复审新提交，未新建角色、未运行测试/编译、未占节点、未启动产品或前端实施。

### 7.2 设计复审收口

修订候选为 `16472197b486908b4ed16cd4b4305f49360d7c38`，独立报告为 `a5d87540e66313b830e9960cc6bc174b6ddb5e40`，见[独审报告 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)。结论为设计 GO：B1 时间语法、B2 异常引用容量已关闭，无剩余设计阻塞；N1 前端 PAX 交接建议已采纳，实际修复与同一 tar 制品互通仍是 FE3 交付条件。

本次后续提交仅同步设计/计划状态，不改变已审技术内容，不扩大原 Owner 授权。产品实施尚未启动，角色已收尾，审核 worktree 保留；新实施角色及 kickoff 按 §1 另行确认。没有新增测试、编译、容器或节点运行，S1–S2b 退出及原基准线均保持原状态。
