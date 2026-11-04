# BE-a / BE-d 任务提示词草案

状态：DRAFT；2026-11-04，p6-backend-design。DC75 的 BE-a 扩项方向已由 owner 于 2026-11-04 确认，详细设计和验收待审核。两任务实施提示词尚未发出；须先经后端审核会话审核，再经 owner 确认，并在 S2a exit 合入 main 后、FE3 前执行。

引用基线：`ebb0047383300a3754a4be6a6a78f72286600c83` 的 [前端 kickoff §4.4/§5/§9](../../../../frontend-vnext/frontend-kickoff.md)、[后端交接 §2.3](p6-backend-session-handoff.md)、DC64/DC67/DC70/DC73。任务业务范围来自已确认的前端决议；本页新增的安排与验收仍待审核确认。BE-b 设计与实现不并入这两项。

补充引用：本人撤回与 Workspace 指针以 main `d0a8143d804e158e16b0712cc5f2aa007066f9cb` 为源码基线，依据 [DC75](p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限) 和 [BE-a 设计补充](p6-be-a-design.md)；前端 Q16 来源为 `55e6c0083c`。BE-d 与 DC74 待决项不因本次扩项改变。

## 1. 发出前填写

记录 S2a exit tag/合入提交、当前 main、kickoff 审核提交、owner 确认日期、实施/审核会话名。建议 BE-a 先做、BE-d 后做，避免同时修改 HTTP 测试与 Contract；不要求等 S2b exit。与 S2b 并行时才开短期分支和独立 worktree，明确 `preview_jobs`/artifact store/benchmarks 的归属交界。基准 exit 前不改其正在使用的测量 worktree。

## 2. BE-a 实施提示词（草案，勿提前发出）

你是 BE-a 后端实施会话。先读 AGENTS、本文、[BE-a 设计补充](p6-be-a-design.md)、前端 kickoff §5（引用上方提交）、Business Lifecycle、P5-5C 状态机设计、DC64/DC73/DC75。按已填写的 main 起点工作。

范围：

1. 完全删除 `RETURN_FOR_REVISION` 动作、`RETURNED_FOR_REVISION` 状态和事件：domain/application、HTTP review/history literal、control DB 基线 CHECK、读写映射、Contract 与测试。没有兼容/迁移要求；删除旧路径，不保留别名。不得误删其他审核、撤回或拒绝语义。
2. 修正 `POST /v1/history-compares` OpenAPI：首次 202、幂等回放 200；`POST /v1/workspaces`：新建 201、已存在 200。让 schema 声明与实际响应吻合，保持现有运行时业务行为。
3. 当前源码起点涉及 `domain/submission/review.py`、`application/submission/review.py`、`http/schemas/{review,history}.py`、`infrastructure/control_db/schema.py` 与两创建路由。先盘点所有枚举使用者、持久序列化、拼接字符串与测试，handoff 给全量清单，不以历史“约 18 文件”作完成判据。
4. 按设计补充 §2 为 WorkspaceResponse 增加 active_submit_attempt_id/active_submission_id（required nullable），在新建/已有工作区路径一致返回；应用查询必须同事务快照读取 Workspace、占用与版本，不新增持久字段。
5. 按设计补充 §3–§4 新增 withdraw_own_submission，覆盖本人 GET review、POST WITHDRAW、当前权限及归属下的幂等回放；保留 reviewer 能力与状态/事务屏障。同步 session 示例与独立 self-only 测试身份。此项是授权语义修改，不归为纯 DTO 修改。
6. 同步 P5-5C 授权/回放/HTTP 条款、Business Lifecycle 与 Workspace HTTP 说明；具体条款和实现路径见设计补充 §5。
7. 前端 OpenAPI 快照在 FE3 由前端刷新；不编辑 `frontend/`、前端设计文档、AGENTS 或 testing-conventions。

程序验收：

- 通过公开 HTTP 输入验证旧动作拒绝且无业务写入；剩余动作的合法/非法状态转换、权限、幂等与并发条件仍成立。domain 测试负责状态机不变量，HTTP 测试负责边界，不复制两套证明。
- 新基线 DB 不能写入被删状态/事件；合法状态写入与 History 映射正常。既有 schema 不匹配按现有启动拒绝机制；不增加迁移器。
- 实际路由与 OpenAPI 同时断言两组首次/回放或已存在响应的 status、response schema；被删枚举不出现在生成的 OpenAPI 中。
- 逐项完成设计补充 §6 的程序验收：新权限 GET/POST/replay；本人/他人/跨 scope；权限撤销；终态回放；指针全生命周期与同快照；self-only 用户的真实 wiring Compose 旅程。不得用 reviewer 全权限身份代替 self-only 验证。
- 静态检索区分历史文档记录与活动实现/Contract；历史 DC 不改写。focused 集合含 RS `-m unit`，防止跨包过时断言遗漏。

按 §4 共用流程执行。真实数据建议为 05 t1 一次完整旅程（schema/持久状态改变，不沿用旧 DB）；审核动作使用合成 HTTP/Compose 旅程补全 t1 未覆盖的状态；04 权威 runner 与当前 HEAD 容器门禁。真实数据范围先在 kickoff 确认，exit 前再次由 owner 确认。完成交代码候选与 handoff，由 owner 转后端审核会话，不自行宣布 exit。

## 3. BE-d 实施提示词（草案，勿提前发出）

你是 BE-d 后端实施会话。先读 AGENTS、本文、前端 kickoff §4.4/§5、Comparison Bundle/Surface Contract、artifact 保护与读取接口、DC64/DC67/DC73。从已填写的 main 起点工作。

目标：Preview 和 History 两个 `/bundle` 路由一次请求返回完整闭包。当前 `bootstrap/composition.py::LocalArtifactBundleReader` 只读单个 manifest artifact。改为流式、不压缩 POSIX tar（`application/x-tar`，长路径 pax）：`manifest.json`、`artifact-closure.json`、按 closure 顺序的唯一产物；产物名用 `logical_path`，不添额外业务成员。共享文件只发送一次，但全部逻辑引用必须仍能由 manifest/closure 解析。

上述成员名已由引用基线的 `frontend/src/features/bundle/posix-tar.ts` 第一个/第二个成员检查确认。实施时对照前端 fixture 与现有 closure，把成员名和同一 source_ref 对应多个 logical_path 时的去重/引用规则写入 Contract 与固定测试向量。不得仅按内容 hash 擅自丢掉前端需要的路径；若现有 closure 不能表达该规则，先交设计会话，不能自行更改业务 digest 或 bundle golden。

传输要求：

- 响应头前校验 manifest/closure 和全部成员可读，大小与引用一致；缺失/损坏走现有稳定错误语义，Contract/OpenAPI 列明实际错误码。授权与精确 workspace/project scope 校验在读取前完成。
- `Content-Length` 计算包括 header、padding、pax 和结束块，必须等于实际响应字节数；ETag 使用 bundle digest（HTTP 引号格式正确）。使用有界分块，不把整包读成 bytes。
- 读取期间沿用现有保护/文件句柄生命周期以应对协作 cleanup；头前预检不能保证后续 I/O 永不失败。发送中异常应中断流，不能吞异常补成成功 tar；断连、错误及正常结束都释放资源。不新建持久下载状态机。
- 不增加按 artifact 读取接口或导航产物。传输格式只包装既有 closure；业务表、records、风险与摘要保值。将 Comparison Bundle 的传输格式与 OpenAPI 同步到目标形态，无 JSON/tar 双格式兼容。
- `benchmarks/real_dump_journey.py` 改读 tar 中 manifest，解析并核对 closure；记录 GET 开始到完整读完的时间与实际响应字节数（只报告）。不改变 READY/operation 完成的既有计时锚，不把旧 manifest JSON 字节数当作整包。

程序验收必须参数化覆盖两个公开路由以及真实生产 wiring，不只测 fake BundleReader：

| 场景 | 检查 |
| --- | --- |
| Preview MODIFIED_ONLY、FULL、DATASET_REPLACEMENT；History 两节点/三节点 | manifest/closure 顺序，成员集合/顺序、长度、摘要、全部表及各侧引用闭合；新增/删除/未变表均按 Contract 存在 |
| 共享产物、长路径、空文件/空表 | 去重规则可解析；pax 长度计算；实际响应长度等于 Content-Length；无额外业务成员 |
| 无权限/跨 scope、结果未就绪/过期 | 原鉴权与状态边界稳定，未泄露成员 |
| 头前 manifest/closure/任一成员缺失或损坏 | 稳定错误响应；不返回成功 tar |
| 流中读取失败、客户端断连、cleanup 协作 | 不产生可误认完整的响应，资源释放；复用现有 artifact 保护能力 |
| closure 路径异常 | 绝对路径、`..`、重复冲突路径及非普通文件按现有 server-owned path 边界拒绝；不引入同 euid 对抗模型 |

通过公共 HTTP 下载完整 tar 后，由程序逐项核验 closure 的逻辑 SHA/raw SHA（按各自 Contract）、成员映射与已冻结的业务结果；不能仅解出 manifest 即 PASS。合成测试承担边界矩阵，真实数据承担完整闭包与传输旅程，不重复每一内部步骤。

真实数据建议：05 t1 完整旅程含 Preview 与 History 下载；t4/2× t4 体积采集跟随获授权的后续 P6 测量，完整 BE-c 报告建议 S6（DC74 草案），不为 BE-d 单独重跑全部基准。04 权威 runner 包含真实服务路由/容器旅程；阶段退出须有绑定当前 HEAD 的容器门禁，即使没有 Dockerfile 修改也不能写“无需门禁”。前端 FE3 随后验证浏览器接收与本地解析；本任务不改前端源码。

## 4. 两任务共同执行约束

- DC64：05 focused、五包 ruff/mypy、门禁前预检后交代码候选；代码通过再跑 04 权威 runner 与约定真实数据，按包沿用及容器 carried 只按 AGENTS。Rust 若未改不新增 Rust 调试工作；最终 runner 范围按阶段约定。
- 专用节点 clean 已提交 worktree；先 SSH 连通，按 DC70 原子获取占用，不抢占计时测量。日志在 worktree 外，记录 hostname、起止时间/HEAD、exit、SHA256。预填充缓存，`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`；backend dependency-base、RS/e2e 依赖模式按 AGENTS/DC67；取证不用代理。
- 调试不跑全量取证。runner 非零、产品失败、缓存缺失、身份或结果不符即停；自身工具错误按 DC66/DC68 的适用范围处置，不绕过拒绝。
- 手工清理本地 DB 仅针对本任务可重建数据；不动其他会话保留卷或证据。只显式暂存角色文件；不改写已引用提交，不擅自推送。handoff 列改动、验收映射、逐包结果、真实数据范围、镜像重建理由与 revision/source-tree、遗留；设计问题经 owner 转交。

## 5. 确认记录

kickoff 审核：待 owner 转交。owner 方向确认：2026-11-04 同意 DC75 扩项；kickoff 细则审核后实施确认：待记录。S2a main 合入提交：待填。BE-a/BE-d 提示词发出：均未发出。
