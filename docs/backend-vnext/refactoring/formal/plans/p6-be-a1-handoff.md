# A1 BE-a 实施交接

2026-11-07。实施角色 `/root/be_a1_impl`，GPT-6.1-Sol/xhigh；协调者 `/root`，独审 `/root/be_a1_review`。入口为 [A1 工作单](p6-be-a1-work-order.md)、[BE-a 设计](p6-be-a-design.md)。产品起点 `8fbdcb7d54`；首候选 `adc2863e7f93c34c5e96b298228d38e227772892`；修复候选 `2d9a39f19107752a074f3d972fb6c7c56d066959`；最终本节容器候选 **`d8bee1a5914d00f473dc41fb76d9c57ca4b01f48`**。2d9→d8 仅补 review Compose 的运行镜像一致性与 provenance；产品/Contract 未再变。审核结论以[同一独审报告](p6-be-a1-review.md)为准，本页不办理联合 exit。

## 实现与 owning consumer

- 删除退回修改的 domain 动作/状态/事件、transition/reason/release 路径、review/history HTTP literal 与基线 CHECK；负例只保留在 HTTP/DB/OpenAPI owner。原 APPROVE fingerprint golden 不变，domain/History/持久映射回归通过。
- Review 共享当前 permission 与持久 `Submission.created_by` 规则：粗粒度 permission 先于任何业务对象读取，最小目标/scope/本人资格先于完整 closure/key；mutation 内重验。原 project-wide actor-independent key、project/Submission/event/fingerprint 完整性和首次 actor 不变；合法成功 replay 早于 fresh state、baseline、occupancy 门禁。
- Workspace create/get 接收完整 transaction，结果包含当前 occupancy；route 在同一写事务读取/构造 Workspace、version、occupancy。两个指针 required nullable、互斥；不新增持久字段、不回退 History。全部直接服务 caller 与 mapper/DTO/OpenAPI 同步。
- Archive SQL 有界 helper 分别读取 APPROVED 与 PENDING；missing projection/event 或 latest event 与 projection 分叉仍进入 closure 验证，不能过滤掉损坏事实。snapshot 验 scope、Workspace/occupancy、finalized Attempt closure；pending 单次最多200，超界返回范围错误，不返回可 Start 的部分集合。candidates/preview 返回 pending IDs/count，Start 在自身 `BEGIN IMMEDIATE` 重查并以 `ARCHIVE_PENDING_REVIEW` 硬拒绝。草稿、旧 baseline PENDING 不阻塞；active Attempt 门禁、完整候选、唯一选择与 sibling 审计保持。
- fresh APPROVE 同写事务检查冻结 node/commit，不符409 `BASELINE_VERSION_CONFLICT`；REJECT/WITHDRAW 仍可处置旧 PENDING。精确 occupancy、Workspace CAS、失败全部回滚保持。APPROVE 不增加 Workspace version。
- session 示例区分本人能力与 reviewer；真实 Compose 有独立 self-only 身份，未用 reviewer 全权限替代本人证明。

Owning 正文为 Business Lifecycle `4.0.0`、P5-5A Workspace HTTP、P5-5C 状态/授权/replay、P5-5D 候选/受理/错误；旧迁移/backfill 条款同步为单一基线 schema。历史 DC、旧审核报告不改写；没有编辑 frontend、前端文档、AGENTS、testing-conventions、benchmarks 或冻结资源。Repository Service 未发现活动旧枚举 consumer，无跨包产品修改；RS unit 实际回归见下。

## 对外接线与前端手动转发包

实际 OpenAPI：06 与 CT201 副本均为 `/home/dev/gdds-test-tmp/artifacts/p6-be-a1/openapi-d8bee1a591.json`、`/home/dev/gdds-reviews/artifacts/p6-be-a1/openapi-d8bee1a591.json`，SHA256 **`e495013955516a283e8f2ef32901c2eda6e2717e6de2dcb41c3f4c0bdfa9725f`**。前端由 Owner 手动转发，后端未改其快照。

| 当前 session 能力 | GET review | 新 WITHDRAW | 新 APPROVE / REJECT |
| --- | --- | --- | --- |
| `review_submission` | exact scope 全部 | scope内 PENDING | scope内 PENDING；APPROVE另验当前baseline |
| 仅 `withdraw_own_submission` | 本人全部状态，含归档后 | 仅本人 PENDING | 403 |
| 两者都有 | reviewer能力 | reviewer能力 | reviewer能力 |
| 两者都无，即使能上传 | 403，先于对象读取 | 403 | 403 |

非本人/不存在/跨scope统一404；closure损坏503；不同目标key碰撞409且不披露旧结果；成功 replay 每次重验当前权限/目标授权并保留首次actor。本人权限不授予 History、Archive 列表或他人 Workspace。

`WorkspaceResponse.active_submit_attempt_id`、`active_submission_id` 为必需键、值可null；无占用均null。受理指向Attempt，未知/人工恢复不按Operation终态清除；ABORTED释放、finalize原子切Submission、REJECT/WITHDRAW及StartArchive释放均按原规则加Workspace version，APPROVE不加。审核另用 `review_version`。

创建路由的运行时与 OpenAPI schema 同时验证：`POST /v1/workspaces` 201新建/200已有；`POST /v1/history-compares` 202首次/200回放。Archive candidates/preview 新增 `pending_submission_ids` / `pending_submission_count`，有同scope当前baseline未关闭PENDING时 blocker=`ARCHIVE_PENDING_REVIEW`；直接Start亦409且无Plan/Result/Head/Workspace部分写。

## 唯一测试 owner 与本轮结果

全部测试/编译/lint在 **06 `gw-dms-06`**，未在CT201执行。LAN bundle到 clean detached WT `/home/dev/gdds-test-tmp/wt/p6-be-a1`，legacy 链接主仓库参考目录；日志在WT外。设 `TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，Cargo jobs4；pytest并行主体4、serial0；无代理。fresh五venv离线同步，Rust扩展输入=`137d499975f3c104ae9c3268b9e12befb2817ba1`与当前Rust tree一致；未改Rust，不重复Rust全workspace或parser差分。

| Owner / 范围 | 来源提交、UTC（2026-11-07） | 实际结果 |
| --- | --- | --- |
| domain/DB、HTTP授权/replay/过期APPROVE、review CAS/精确释放、Workspace生命周期/同快照、archive query/transaction/竞争、OpenAPI/History、必要architecture/wiring | 2d9，08:02:28–08:03:17并行；08:03:17–08:03:18 serial | **573 + 1 passed，均exit0** |
| 五包ruff/mypy | backend 2d9 07:58:39–07:58:40，其余四包07:59:53–08:00:09；d8 backend重核08:04:02–08:04:03 | **10项全部exit0**；d8增量亦0 |
| RS `-m unit -n 0` | 2d9，08:00:09–08:02:28 | **1555 passed，1 skipped，396 deselected，exit0**；skip为仅delegated target container执行的既有cgroup smoke |
| reviewer Submit→APPROVE Compose | d8，08:05:24–08:05:55 | **1 passed，exit0** |
| self-only Submit→GET→WITHDRAW→指针释放→再次上传/Preview Compose | d8，08:05:55–08:06:28 | **1 passed，exit0** |
| 双actor PENDING阻塞preview/直接Start→两项APPROVE→唯一选中+sibling/identity处置→归档释放/重启 Compose | d8，08:06:28–08:07:25 | **1 passed，exit0** |

权限/披露/replay由 `test_review_http.py`；完整性、CAS、精确释放由review transaction；ABORTED公开投影只在submit原owner证明；Attempt→finalize→Submission指针由Workspace owner；active→finalize→pending两次Start拒绝由archive concurrency owner。没有复制HTTP整矩阵到Compose。

## 原始证据、镜像与缓存

证据根：06 `/home/dev/gdds-test-tmp/artifacts/p6-be-a1`；CT201只读副本 `/home/dev/gdds-reviews/artifacts/p6-be-a1`。`SHA256SUMS` SHA256 **`0011e81b42951b0744f2311c9222052329039857989c48d49d80384fbbe4a4be`**，包含全部原始日志、三份provenance、OpenAPI与镜像身份。日志有hostname、起止UTC/HEAD、argv、exit。

| 文件（相对证据根） | SHA256 |
| --- | --- |
| `setup-adc2863e.log` | `d5f399fe9ea9712e5be525ffa350d55877e4f072def20a8a0da0c4e35bb8cb99` |
| `backend-parallel-2d9a39f1.log` | `5f131053eb1eb8cfa43c8f1756371a99fd98411c13cb8653537efa2c84c1e99b` |
| `backend-serial-2d9a39f1.log` | `7947e985d4f44dc6a31469986316b59ed7691ae00238da95f2b3d8c669d57ad9` |
| `repository-service-unit-2d9a39f1.log` | `b32ee1fb326de64317736b276b1840269d3dc0c7771d7117b58dc2ffd325beac` |
| `compose-review-approve-d8bee1a591.log` | `87b63a15ea96e766381cbebc5f76fe486e66ebd6b6d6f2af847f62adb41f0b01` |
| `compose-review-self-d8bee1a591.log` | `e47c995c5050a8010906bb10b3c4943c4b661b63854c0141790d0113a3c934ab` |
| `compose-archive-dual-d8bee1a591.log` | `5ffcfe8f529ff03d69c4d901503cd868c409df8d6ac8e7d58c2e9a3cfc316642` |
| `review-approve-provenance.json` | `48c7569f6eaf750cb5c65fd5f65779af6998f6a64ba67318589e72d0aff08dda` |
| `review-self-provenance.json` | `c8d3865102e7efa1bb66defcab6e04e8480c7c96105334a4c8a7ea5096e2dc10` |
| `archive-dual-provenance.json` | `61b66b7b9a537b5745d7e0b639145d896a8d956a37ee4e477e71ad6073623f5d` |
| `image-identities-d8bee1a591.json` | `2f97f0f1e3ae48f9aad6297bc73d3aa9d7e53d2a7f045a4d1c363f3a47098d6c` |
| `cleanup-d8bee1a591.log` | `193182e98fc50acf52369e9d930402e29e0bfa329acfe39c569aac1dff6c66c1` |

本节修改实际Compose测试/session接线，**触发并已完成候选d8本机离线重建和上述受影响门禁**。backend/worker用 `gateway-backend-deps:lock-d054366c02fa`、预置开关1、`GATEWAY_DOCKER_BUILD_NETWORK=none`，未设置prebuilt。RS实建新tag `gateway-repository-service:be-a1-d8bee1a591`；其 source identity稳定为build-input `a6876d560050285321fd9f62942d590a03f35d64`、source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`，不是声称RS源码在A1变化。

三份provenance逐次记录运行容器与本次build的本机image ID；最后双actor门禁backend ID=`sha256:0fd31de9ad7ed308b183bbfa1bc13987becfb4d113f42783ef299b6f2debeaca`、worker ID=`sha256:2c16bd4d32cdd75e1edbf3d6521c41e19f1f68c062c010b56c09131b04d180eb`、RS ID=`sha256:42f33b7a5b6c91f8e8ca04a3854681b28b3e454ff46a31c3670d03c54c832007`。实际docker-save提取10个运行/依赖镜像config digest及全部RootFS DiffID，逐一与本机inspect RootFS相等，完整列表在identity JSON；不把inspect ID当跨节点config digest。本节无跨节点镜像传输、无carried声明。

缓存均为本机现有预填充：uv/Rust toolchain+registry、Python/Rust base image、backend d054、RS `gateway-p2r1-repository:lock-6dc9659f0aee`、client e2e base。未改依赖/锁/base，故本轮没有新增依赖预填传输，无需远程缓存端点或转发代理；源码LAN bundle的SHA分别为 `8dd0f07bbd6aa95215b887d7aaad2d144ccb0c4efa54642c79c43a134d2222d2`、`0dcc0f85b80d39e6d9be560b3558cf92c0ce0de4a87c2903d78e49d1d0ead8e6`、`11da741f58f63b461ee0fb979216c8a1979e03932351160b0cdcc848a71f29ac`。A1重新计算完整dependency input=`d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，实际d054 config=`sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`及19 DiffID仍与已核CT201来源相同。历史来源提交 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`、archive SHA=`3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`，预填/构建时间见[06 readiness §3/§7](p6-node-06-07-readiness.md#3-源码与制品来源)，本轮仅复用并重新核实际身份。

收尾08:09:12Z：06 WT仍clean d8，三栈已`down -v`，无活动容器/Dolt及8000监听；比较本人owner文件后删除本人标记并释放节点。WT、镜像、证据保留供只读审核，没有清理他人/冻结资源。

## 失败、修复与后续边界

首轮adc：ruff0；mypy因旧closure向量漏必填字段及测试类型注解失败（log SHA `f82f36812e4b2d5210f1137ca70ad29dbc1cc5920f678871d42d3d4fb6861727`）；focused为491 passed但domain模块收集失败（`eae2f567faecc1f1de24aefa3caefacdc28aac558837934ff5bd04654b9bfe04`），不作来源。2d9修为完整REJECTED whitespace反例并补同Attempt finalize语义屏障；原审核者复审，无新增代码finding。2d9首次574项混跑包含一个serial，仅保留诊断，正式证据为后续573+1分批，不混称权威runner。

OpenAPI导出首次外置script被uv wrapper在执行前拒绝exit2：`openapi-command-rejected-d8bee1a591.log` SHA `79486c208c72e713029c33450d88764b6c10ade461b9ca65c23769564bab25aa`，原raw日志及observed UTC/exit/correction metadata保留。目标未执行且无副作用，按DC68改用入口明确支持的内联`python -c`，从OpenAPI步骤重做一次成功；未改wrapper、未继续失败的产品门禁。

A1不办理联合exit：04的受影响包权威runner/必要容器、05 fresh t1由联合最终候选集中执行，不能把本轮06focused写成权威包沿用。具体容器增量nodeid为本节上述review两条及archive双actor一条；后续V1/V2/D若改变其边界，在04联合候选重建并按当时范围运行，不把d8结果绑定到未知后续HEAD。05联合fresh t1须先补齐新产品候选上的真实旅程工具：当前 `vnext/backend/benchmarks/real_dump_journey.py` 仅有MODIFIED_ONLY入口，`_archive`仅消费身份异常，并未覆盖FULL或新增来源/时间异常及完整tar。V2/D须先增加FULL入口、新异常逐项处置消费、Preview/History完整tar校验，再执行联合旅程；不能把既有工具冒称已经覆盖这些目标。本角色未编辑或运行该工具，原冻结V_ref及其工具保持不动。

V1/V2/D仍待交付：时间/内容事实、来源图/逐项接受、完整tar及有理由关闭。APPROVED仍不可本人撤回；没有恢复旧return，也没有把本节pending gate冒称完整归档业务核验完成。没有推送、改写引用提交或启动S3。

## 实际文件盘点

以下为 `8fbdcb7d54..d8bee1a591` 本角色46个产品/测试/owning文档文件；另有本交接。协调文档与独审报告由各自角色维护。

```text
docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md
docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-design.md
docs/backend-vnext/refactoring/formal/plans/p5-5c-review-design.md
docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-design.md
vnext/backend/src/gateway_backend/application/archive/errors.py
vnext/backend/src/gateway_backend/application/archive/ports.py
vnext/backend/src/gateway_backend/application/archive/queries.py
vnext/backend/src/gateway_backend/application/archive/snapshot.py
vnext/backend/src/gateway_backend/application/archive/start.py
vnext/backend/src/gateway_backend/application/submission/review.py
vnext/backend/src/gateway_backend/application/submission/review_transaction.py
vnext/backend/src/gateway_backend/application/workspace/contracts.py
vnext/backend/src/gateway_backend/application/workspace/ports.py
vnext/backend/src/gateway_backend/application/workspace/services.py
vnext/backend/src/gateway_backend/domain/submission/ports.py
vnext/backend/src/gateway_backend/domain/submission/review.py
vnext/backend/src/gateway_backend/http/errors.py
vnext/backend/src/gateway_backend/http/mappers.py
vnext/backend/src/gateway_backend/http/routes/archives.py
vnext/backend/src/gateway_backend/http/routes/history.py
vnext/backend/src/gateway_backend/http/routes/reviews.py
vnext/backend/src/gateway_backend/http/routes/workspaces.py
vnext/backend/src/gateway_backend/http/schemas/archive.py
vnext/backend/src/gateway_backend/http/schemas/history.py
vnext/backend/src/gateway_backend/http/schemas/review.py
vnext/backend/src/gateway_backend/http/schemas/workspace.py
vnext/backend/src/gateway_backend/infrastructure/control_db/schema.py
vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py
vnext/backend/tests/support/http_workspace_harness.py
vnext/backend/tests/test_archive_compose_e2e.py
vnext/backend/tests/test_archive_concurrency.py
vnext/backend/tests/test_archive_queries.py
vnext/backend/tests/test_archive_transactions.py
vnext/backend/tests/test_http_openapi.py
vnext/backend/tests/test_production_wiring.py
vnext/backend/tests/test_review_compose_e2e.py
vnext/backend/tests/test_review_domain.py
vnext/backend/tests/test_review_http.py
vnext/backend/tests/test_review_persistence.py
vnext/backend/tests/test_review_transactions.py
vnext/backend/tests/test_sqlite_workspace_repository.py
vnext/backend/tests/test_submit_transactions.py
vnext/backend/tests/test_upload_application.py
vnext/backend/tests/test_workspace_http.py
vnext/deploy/README.md
vnext/deploy/config/session.json
```
