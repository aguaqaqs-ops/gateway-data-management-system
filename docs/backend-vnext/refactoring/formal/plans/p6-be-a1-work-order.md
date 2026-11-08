# A1 BE-a 实施与独审工作单

日期：2026-11-07。Owner 授权及角色规则见[联合 kickoff §1.1](p6-be-a-d-kickoff.md#11-实施授权与实际起点owner2026-11-07)。业务依据为已审 [BE-a 设计](p6-be-a-design.md)全部条款，尤其 §6/§9；设计 GO 报告为 `a5d87540e6` §6。本工作单不改变其语义。

## 1. 起点、交付与文件归属

从当前 clean main `8fbdcb7d54` 开始，允许其后的协调文档提交，不 checkout 回历史设计候选。先核 `git status/diff/log`，保护全部并行修改。实施者负责本节产品、测试、owning Contract 及 `p6-be-a1-handoff.md`；审核者负责 `p6-be-a1-review.md`；协调者负责本工作单、联合 kickoff 和协调交接。产品串行 main，审核用固定候选的只读 detached worktree，链接主仓库 legacy。不推送、不改写已引用提交，不创建额外角色/子 agent。

实施和独审均为 GPT-6.1-Sol / xhigh。实施者独立盘点实际文件及所有 consumer；下面是已核入口，不是封闭白名单：

| 层 | 本节入口与同步内容 |
| --- | --- |
| domain | `domain/submission/review.py` 及导出；彻底删除旧 return 动作/状态/事件、transition/reason/release 路径，保留其余语义 |
| application | `application/submission/{review,review_transaction,review_contracts}.py`，`application/workspace/{services,contracts,ports}.py`；共享 permission/本人绑定规则，mutation 内重验，Workspace/occupancy/version 同快照 |
| 归档 | `application/archive/{queries,snapshot,closure,start,contracts,errors,ports}.py`，实际 owning domain/SQL port；同 scope 当前 node/commit 的未关闭 PENDING 有界查询与硬门禁，保留 active Attempt |
| persistence | `infrastructure/control_db/schema.py`、实际 review/workspace/archive repositories、query/UoW/database；单一基线 CHECK 与序列化消费者同步，无 migration/backfill/双读 |
| HTTP | `http/{schemas,orchestration,routes}` 的 review/history/workspace/archive；required nullable 占用指针、两创建路由状态码与 response schema、权限和稳定错误/OpenAPI |
| wiring | 实际 bootstrap/session 示例及测试身份；独立 self-only 身份，不给全部用户 reviewer 权限 |
| 跨包 | 检索 repository_service 中旧枚举、拼接字面量/架构守卫，删除过时实现和断言 |

Contract 入口：`refactoring/formal/contracts/business-lifecycle-and-state.md`（§2、§4–§5）、`p5-5c-review-design.md`（状态机、§4.3/§5授权回放、HTTP/测试归属）、`p5-5d-archive-design.md`（pending受理/精确释放）、Workspace HTTP 实际 owning 说明。均位于 `docs/backend-vnext/` 下；实施者先确认真实链接/条款后同步正文。历史 DC 和旧审核报告不改写。前端源码/文档、AGENTS、testing-conventions、原基准 benchmarks/冻结资源不属于本节。

## 2. 必须成立的行为

1. 完全删除 `RETURN_FOR_REVISION` / `RETURNED_FOR_REVISION` 及被替代路径；旧 HTTP 动作拒绝且无写入，新 DB 拒绝旧状态/事件；保留 APPROVE/REJECT/WITHDRAW。没有兼容负担。
2. Workspace 两创建结果返回 `active_submit_attempt_id` / `active_submission_id`，required nullable、互斥，从同一事务快照取得 Workspace/occupancy/version，不新增持久副本。按设计 §2 全生命周期验证；review version 与 workspace version 分开。
3. GET review/WITHDRAW 接受 reviewer 或 `withdraw_own_submission`。self-only 仅能读本人全部状态、仅能新撤回本人 PENDING；APPROVE/REJECT 只允许 reviewer。当前 permission-before-object、exact scope、持久 created_by 本人判断；非本人/跨scope/不存在统一404。
4. mutation/replay 重新验证当前权限/目标授权；合法原成功 replay 先于 fresh 状态、baseline、occupancy 门禁，不改原事件 actor。保持 project-wide actor-independent idempotency/fingerprint 完整性，损坏不是普通冲突；不同目标 key 碰撞不得披露。
5. 同 exact scope/current baseline 有未关闭 PENDING 则 preview显示 `ARCHIVE_PENDING_REVIEW`、Start 在自身 `BEGIN IMMEDIATE` 再查并拒绝。草稿不阻塞，active Attempt 原门禁保持；candidate 仍完整、唯一选中/sibling排除不变。
6. 新 APPROVE 在同写事务拒绝过期 node/commit，409 `BASELINE_VERSION_CONFLICT`；合法历史成功 replay 保留。WITHDRAW/REJECT 不要求 baseline 当前；精确释放、CAS/回滚、权限/scope与完整性错误不放宽。
7. OpenAPI：history-compares 首次202/回放200，workspaces首次201/已有200；状态码和实际response schema同时验证。删除旧枚举，补指针与新增门禁错误。

## 3. 验证与证据边界

全部测试/编译/lint在专用节点，默认06；开始先 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`。现场核查有效标志/进程/Compose/8000端口，空闲时原子 `mkdir /home/dev/gdds-node-busy.d`，写角色/用途/UTC；不抢占、不删除他人标志。若有效冲突报告协调者，不擅改其他节点用途。测试在 clean 已提交 detached worktree，源码 LAN bundle，legacy 链接齐全，日志在worktree外。设置 `TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，不启代理；测试workers建议4。按实际环境核缓存与工具链，不打印凭据、不改lock。

| 唯一 owner | focused 范围 |
| --- | --- |
| review domain/persistence | `test_review_domain.py`、`test_review_persistence.py`、必要 `test_control_db_schema.py`：新状态机/基线约束/映射 |
| HTTP | `test_review_http.py`：权限/披露/current授权/replay矩阵、过期APPROVE与合法历史回放；参数表复用 |
| review transaction | `test_review_transactions.py`：idempotency closure、CAS、精确释放/失败无部分写入，不重复HTTP权限矩阵 |
| workspace query/HTTP | `test_workspace_http.py`及实际生命周期owner：两个指针、同快照/版本、required nullable、首次/已有路径 |
| archive query/transaction/concurrency | `test_archive_queries.py`、`test_archive_transactions.py`、`test_archive_concurrency.py`及必要HTTP：pending/草稿、旧集合、finalize/Start/审核竞争、无副作用 |
| OpenAPI/history | 实际 owning test 中验证两创建状态码/schema、history literal/映射；不重复全矩阵 |
| 跨包静态回归 | repository_service `-m unit`，五包ruff/mypy；Rust未改不重复parser差分或全workspace构建 |
| 真实接线 | 复用 `test_review_compose_e2e.py` / `test_archive_compose_e2e.py`，一条self-only上传→撤回→重传，一条两人PENDING阻塞→处置→归档释放。若修改实际Compose/harness，收敛后的A1候选须重建并跑受影响门禁；不逐提交构建 |

先交代码候选，独审可先核代码；06完成focused/静态与必要小型接线后同一审核者复核证据。每次结果记录节点、起止HEAD/UTC、exit、日志路径/SHA；失败保留并诊断，runner非零不继续验收。缓存缺失先停止补齐。按比例化政策测试语义屏障，一不变量一owner，不新增内部安全/evidence平台。

A1不独立办理整个任务exit、不每轮全量runner/真实全旅程。联合最终候选再集中04受影响包权威/容器、05 fresh t1及必要异常wiring；当前A1若改Compose测试则该触发的局部门禁在本节完成，不借联合计划豁免。每次handoff写当前HEAD、是否触发重建/理由、最后实际镜像revision/source-tree、deferred精确nodeid/节点与证据范围；旧S2b镜像不能宣称当前A1通过。

## 4. 本节完成与下一步

完成标准为代码候选、Contract/consumer清单、测试owner映射、06定向/静态及触发的小Compose证据、handoff与同一审核者独审/修复闭环。新时间/内容事实、来源图、逐项接受及关闭出口归V1/V2；完整tar归D。删除旧return后仍不可将APPROVED视为可本人撤回，V2关闭出口未交付须明确登记。

审核者只读候选，findings指明具体场景/证据/影响/修复边界；原则上不改产品，可提交自己的报告。小修可直接联系实施者，协调者记录结果；设计性冲突交设计者，必要时向Owner报告，仅暂停相关依赖。通过后结束本节两角色（按工具真实能力记录），协调者新建V1两角色并继续，无需重批。
