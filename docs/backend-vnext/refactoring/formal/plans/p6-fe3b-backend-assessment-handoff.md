# FE3b 任务评估：后端交付与前端注意事项（Owner转发）

2026-11-07，后端协调者维护。本页提供后端事实、已知前端接缝和评估建议；FE3b交互设计、范围确认与实施安排仍由前端owner负责。本轮未改前端源码或前端kickoff。

## 1. 评估起点与已解除的依赖

- S2a已退出，仓库存在`p6-s2a-exit`；当前main也已包含S2b生产Rust接线。S2a早期handoff中“生产仍用Python、worker接线留S2b”是历史状态，不应拿来决定当前FE3b行为。前端继续消费HTTP/Bundle Contract，不增加Rust/Python选择器或浏览器SQL计算回退。
- 解析诊断按公开code和结构字段消费，不匹配Python/Rust内部异常名或message逐字文案；S2a错误差分核对的是约定diagnostic code/table/offset。解析成功也不代表归档来源/时间核验自然通过。
- BE-a、归档业务核验及BE-d已实现并获联合后端技术GO：实际产品`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`，`vnext` tree=`56720104af34a1eb677336f57bdbc07444a56615`，独审`ccdd1eb39d`§25，最终实施handoff`233e6f788b`。Owner已确认本轮DC33真实数据范围，见[最终协调交接](p6-be-a-d-joint-validation-preparation.md#13-owner最终dc33范围确认与交接)。
- **正式退出已补齐**：本地附注`p6-be-a-d-exit`→独立退出报告F`77b9aeea74b08b527ef1c78637e0cbe000b60d2f`，在main可达；原04同WT实际六包／镜像／五锁最终绑定与原审核收完成。产品/API/tar不变，见[退出交接§15](p6-be-a-d-joint-validation-preparation.md#15-联合正式退出完成与前端交接)。前端可将后端“已退出并在main”这一条件记为满足；FE3b自己的kickoff及验收条件仍分别核对。
- 旧FE3 kickoff中的三个后端前置已有明确交付：S2a已退出；过期baseline新APPROVE拒绝/同baseline PENDING硬阻塞已实现；tar与最终closure逐entry对应已确定。无需再等原基准性能线或重新选择这些已审业务规则。
- 后端GO不替代FE3b浏览器验收或FE3退出。当前仍缺前端同字节tar解析/摘要/OPFS证据。

**前端首先需要更新自己的FE3 kickoff。** 其§2.1、§2.3、§3.2、§6、§8、§12仍包含2026-11-05的旧事实；特别是新增归档核验、逐项接受及关闭出口超出原“刷新类型＋撤回＋跑旅程”的稿面，需由前端owner纳入设计和工作量评估。

## 2. 当前schema及清理范围

使用当前联合候选的实际生产[OpenAPI原件](/home/dev/gdds-reviews/artifacts/p6-be-ad-final-04-copy-mop1T4t8/p6-be-ad-final-04/resume-a-5OBTboKj/new-authority-compose-53h3ekqp/production-openapi.json)，SHA256=`977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`。前端刷新快照/生成类型，真实e2e继续与当次运行中的`/openapi.json`比对；早期f8/V2 schema不作为当前快照。

- 删除`RETURN_FOR_REVISION`、`RETURNED_FOR_REVISION`的产品动作、显示、mock、类型和替代映射。新项目不保留旧别名或“退回映射成拒绝”的兼容路径。原R6“退回后重提”旅程应按新动作重新设计，可用REJECT→重提，并另覆盖手工关闭出口。
- `POST /v1/workspaces`明确201首次/200已有；`POST /v1/history-compares`明确202首次/200 replay。删除为旧OpenAPI缺漏保留的类型绕过。
- `WorkspaceResponse.active_submit_attempt_id`与`active_submission_id`为required-nullable、互斥，不能把缺字段当正常null。
- Review增加required-nullable `submission_disposition`；History的`archive_disposition`直接改为`submission_disposition`并消费source/closure信息，不双读旧字段。

本次静态盘点基于main `d4efe7de3b`、`frontend` tree=`44a9b5177b68d1d230da0879009b2c0e595cca7f`，未核前端其他工作区的dirty diff。当前main可见接缝包括：

| 位置 | 需评估的实际内容 |
| --- | --- |
| `frontend/src/features/api/generated/openapi.d.ts` | 仍含退回枚举和旧History字段，须重新生成 |
| `frontend/src/features/api/client.ts::safeReviewStatus/safeReviewEvent` | 仍将退回映射为拒绝，须随目标Contract删除 |
| `ComparisonPage.tsx`、`features/view-model/workspace.ts` | 仍有旧状态文案/映射 |
| `ArchiveMainlineDialog.tsx::anomalyAction`、`api/journeys.ts` | 目前只处理identity/sibling类别，不能将新增三类异常落到旧action |
| `features/bundle/posix-tar.ts` | PAX按字符切片、只消费path而忽略标准size，见§5 |
| `frontend/scripts/run-real-backend-e2e.sh` | 当前仅smoke；journeys/t1/input-root仍明确exit2，须在FE3b交付实际入口 |

由前端以自身分支和实际diff核对以上工作量；不要覆盖其尚未合入main的改动。

## 3. BE-a：占用、本人撤回与旧旅程调整

- 刷新后按Workspace指针定位Attempt或Submission。Attempt仍存在、结果UNKNOWN或需人工恢复时，占用保持；不能按Operation终态或一次轮询失败自行清指针、解锁新提交。
- **重新核对FE3a的n3断言。** 旧稿中“读取失败后恢复提交按钮”不能机械沿用到存在权威占用指针的状态；应刷新Workspace/Attempt状态，明确释放后才允许新提交，未决时提供重查/恢复提示。
- `withdraw_own_submission`允许本人读取全部审核状态、撤回本人PENDING；APPROVED不能本人撤回。GET/POST的403与他人/跨scope统一404按服务端处理。此能力不额外授予History、归档列表或他人Workspace权限。
- e2e需要真实的self-only身份（基础工作台能力＋本人撤回、无`review_submission`），不能只拿reviewer全权限证明“本人撤回”。保留无两项审核能力的403用例。
- 撤回的`expected_review_version`取Review的`review_version`，不要用Workspace版本。
- 同当前baseline的PENDING会阻塞归档，草稿不阻塞；消费`pending_submission_ids/count`及`ARCHIVE_PENDING_REVIEW`。新APPROVE遇过期baseline返回409，合法历史成功replay保留。旧“先归档A，再通过同baseline仍PENDING的B”不可继续作为正常路径。

权限、状态和错误矩阵详见[BE-a交接](p6-be-a1-handoff.md)。

## 4. 归档业务核验及关闭：需要前端设计评估的新增块

### 4.1 展示与逐项接受

- 展示`business_validation`及source/time issues，按closed details union和`subject_kind/issue_code`渲染；区分原`detected_status`与人工`resolution_status`。接受后仍可能UNKNOWN/UNEXPLAINED/NOT_COMPARABLE，不显示为自然PASS。
- 时间/来源事实由后端冻结与判定；不要在浏览器重新解析SQL、计算来源图、用上传时间代替生成时间，或改为选最大saved_time。后端选择的是**源序最后可解析值**，最大值和“最后非最大”诊断另存。
- 新增三个action：CONFIGURATION_SOURCE→ACKNOWLEDGE_SOURCE_EXCEPTION；CONFIGURATION_TIME_QUALITY→ACKNOWLEDGE_TIME_QUALITY；CONFIGURATION_TIME_ORDER→ACKNOWLEDGE_TIME_ORDER。既有identity、sibling和选择确认继续保留。
- 每个subject明确填写reason，可REVOKE；直接使用服务端subject/target/sequence和同次Head/candidate_set_digest，不由UI自己派生。**同code/target但INITIAL、MODIFIED不同subject_digest是两个独立项**，分别展示/接受/撤销，不能按code合并或默认为全选接受。
- candidate/facts/Head/来源组变化后刷新预检，旧审计引用不能强套新subject；冲突不自动重发变更请求。损坏、越权、事务冲突没有“填写理由强制继续”的入口。
- 候选上限200，选择确认引用上限1，异常引用上限1601，body上限262144bytes，version/sequence为0..9007199254740991安全整数。清除旧共用200引用限制，不能因UI分页漏掉必要引用。

### 4.2 有理由关闭、不归档

- 新`POST /v1/submissions/{id}/closure`：Idempotency-Key及expected review/baseline版本、非空reason；仅`archive_submission`可用，不由reviewer/self-only自动取得。
- 首次201、同命令replay200；显示服务端首次actor/time/reason，不改成重放人的信息。
- 成功保留APPROVED历史、释放Workspace并清当前输入/Preview；用户重新上传/预览/提交。baseline不移动，没有ArchiveResult。
- Review审核status与终局`submission_disposition`分开显示。MANUAL_CLOSE的result_id=null不代表仍未关闭；History全树/分页和按钮准入都消费统一处置。
- 关闭来源桥接提交后，其余候选可能重新UNKNOWN：刷新预检，不能自动放行、接受或级联关闭。

完整字段、权限、错误、replay与终局显示见[V2前端交接包](p6-v2-frontend-handoff.md)。后端测试用的“测试库逐项接受”reason不是前端真实用户的默认自动理由。

## 5. BE-d：完整tar与必须修复的consumer

- 两个bundle路由均返回完整、不压缩`application/x-tar`；原manifest、原closure在前，之后严格按最终closure顺序逐entry一个普通文件。共享由assembler的最终closure表达，下载端/前端不自行按内容再去重，不接受hardlink/symlink替代。
- 检查Content-Length、ETag及每成员路径/顺序/size/对应摘要。HTTP200或Operation SUCCEEDED不等于本地bundle安装成功；截断/流错/摘要错必须abort OPFS事务，不能commit半包或显示成“无差异”。不要回退成只解析manifest JSON。
- PAX长度按UTF-8字节读取和切边界，含前缀自身位数固定点；需覆盖中文/非BMP/相邻记录及99→101等位数边界。
- 支持标准PAX十进制`size`覆盖ustar八进制size字段；保持安全整数/资源边界。给定size向量仅header，不是完整可安装包；不造>8GiB测试文件。
- 前端现`PAX_LIMIT=1MiB`与合法producer路径域需评估对齐，不能盲目取消资源保障，也不能偷偷截短/ASCII化路径。实际域冲突给出具体字节数与影响交设计者。
- 头前错误按实际schema处理：Preview缺失404 RESOURCE_NOT_FOUND，History缺失404 ARTIFACT_UNAVAILABLE，完整性503 BUNDLE_INTEGRITY_FAILURE；权限/scope/readiness规则仍在前。不可据错误响应构造空bundle。

**同制品互通是FE3b自己的交付项。** 使用[D前端包§3](p6-be-d-frontend-handoff.md)的同一个生产encoder `bundle.tar`（24576bytes，SHA256=`b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`），验证解析、所有摘要和OPFS安装，回传前端固定提交、同SHA及专用节点证据。该小包records count=0，不用它冒充真实records覆盖；真实Preview/History旅程另测。

## 6. FE3b真实旅程与取证评估

- 前端owner更新旧R1–R11：用新审核动作替换R6退回路径；把当前占用语义、pending/过期approve、接受/撤销、关闭重提、History/Review处置、新tar成功/错误与同subject独立项纳入。
- 扩展现smoke框架的真实journeys/t1/input-root，而非只运行原9个smoke。旧smoke曾以出现bundle下载失败提示为成功判据，不能当当前下载/浏览成功证据。
- FE3a的空INITIAL FULL smoke只证明被接受/可比较；FE3b仍须在归档后证明FULL两pair、身份确认和两/三节点History实际浏览。后端t1四tar通过不替代前端规定的浏览器旅程/三节点历史。
- 浏览器t1使用完整组态目录（含`.pmc`），不能把仅含SQL/XML的后端规范源包加占位`.pmc`冒充真实输入。05已传原件的历史位置为`/home/dev/gateway-real-dumps/source-dirs/t1-v1`、`t1-v2`；实际执行时按[FE3a交接§4.1](../../../../frontend-vnext/fe3a-handoff.md)重新核原SHA和只读挂载，不将旧存在性当实时证明。
- t1预期值从同一被测`vnext`树取；FULL显式按pair_id核`baseline_to_initial`与`initial_to_modified`两pair，默认单view summary的pair_count不能代表完整FULL，业务计数须对应实际所选pair。实际后端对照见[原t1结果JSON](/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/p6-be-ad-final-05/run-fresh-t1-8skuj66m/final-result.json)。
- FE3a M1已获接受：原renderer峰值/外推满足Q12，不默认增加流式上传重构。FE3b按既定t1旅程复核和待带入指标处理；上传打包与下载tar是不同工作面。BE-b/FE4展示导航和首批空基线业务仍按原边界，不能以播种空INITIAL说已经交付。
- 日常类型/lint/构建/截图/mock优先07（Playwright workers2）；真实backend调试05；最终权威证据04，均clean已提交worktree、离线缓存、镜像身份/日志，截图1280/1920。使用时现场原子核占用；本轮释放事实不是FE3b预留。CT108仍归原基准线。
- RS harness还比较candidate revision：按FE3b自己的固定候选预建/核齐RS镜像并预先保存原身份；不复用旧a999/49403 tag当新FE候选。取证按实际阶段container.Image→不可变image原config/全部DiffID，不拿末尾tag替前段；custom RS tag参与后端包闭包，不改规则凑等价。详见[本轮身份接缝及补验](p6-be-a-d-joint-validation-preparation.md#10-身份收尾停止与owner选择)。

建议评估拆为五个交付块：契约/类型与旧路径清理；Workspace/本人撤回；归档核验/接受/关闭及终局显示；tar/PAX/OPFS互通；真实旅程脚本、t1与最终前端证据。新增界面由前端owner补设计和范围确认；后端接口已经交付，遇具体Contract冲突再反馈设计者，不把旧文档的待决项当作后端仍未实施。
