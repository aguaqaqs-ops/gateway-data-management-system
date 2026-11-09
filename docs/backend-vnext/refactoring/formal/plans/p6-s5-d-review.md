# S5 D 独立产品审核归档

固定产品候选 `cb2ad300845f73f12ae5367d247829623b728f18` 已 **D CODE_GO / EVIDENCE_GO，可进入E**。原始失败与未跑项保留，无 qualified runner、Compose、t1 或 carried 结论。

---

原件：`/home/dev/gdds-s5-logs/reviews/d-r1.md`；SHA256：`b8c410a13e5b9aec59cf98feb83cd370a285aeeb402cce897eeab5ec1dd1aa8c`。

---

# P6 S5 D 独立产品审核 R1

结论：**CODE_GO，绑定最终候选 `8d7a1580f3321608382a06e16334c733d1a0f4a8`**。完整 D 区间未发现剩余代码阻塞；本轮核查期间发现的 poll 完成观察回归和实际 Submit parent-catalog consumer 控制缺口均已在固定后继中连续核闭。唯一 D 测试者可按下述固定稿执行必要检查。当前产品检查全部 **NOT_RUN**，本结论不是 D EVIDENCE_GO、qualified runner、carried、Compose、真实 t1 或 E 退出结论。

## 1. 固定对象与独立性

- 完整审核 base：`bf1f15393e1c1bfba8e906a9b2cc071affb1e7e2`。
- 初始候选：`048bd714568dee12dfde8deadcedc0dc273a30cc`；第一窄修订：`7ebc438c046eb858cad701048547059ec3640028`；最终候选：`8d7a1580f3321608382a06e16334c733d1a0f4a8`。未把初版或中间稿写成已实测通过。
- 最终 vnext tree：`59832ebbb50ebec638c933282064658315fc6929`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`，与 C/A 的已核产品相同。
- 三稿分别建立只读 detached WT：`/home/dev/gdds-s5-review-d-048bd71456`、`/home/dev/gdds-s5-review-d-7ebc438c04`、`/home/dev/gdds-s5-review-d-8d7a1580f3`。逐稿核 exact HEAD、detached、index/tracked/untracked clean；`legacy` 均指 `/home/dev/gateway-data-management-system/legacy`。根实施 main 的提交与 clean 状态亦已只读核对，未接触原前端工作区。
- 完整 `bf1f..8d7a` 为 19 路径、809 增/40 删：T3/事务 port/UOW、HTTPArrow 与 Submit parent catalog、通用 client 控制及测试、四份 owning Contract；未改依赖、锁、Rust、生产 N/M、wire DTO、SQL/planner/publisher、schema、部署或容器 harness。
- 本人是本 D 新建独立 Sol 审核角色，未参与被审实现。未编辑产品、测试、Contract 或被审 WT，未运行任何产品检查（包括语法、lint、fmt、编译）、节点测试、镜像或真实旅程，未创建子 agent、push/tag；只写本外置报告。Git/源码/文档/已有原件和脚本 SHA 核对不是产品执行证据。

准备输入已读当前 AGENTS、testing conventions、S5 实施提示词、设计/kickoff/coordination、设计原审及 A/B/C handoff/必要原审和证据原件；相关 DC38–43/47/55/68/91/94/97/98、比例化/Rust 政策和 ADR0009/0012/0013；S3 §9、S3/S4 exit 与历史来源；Q18/BE-d 的实际 consumer 边界。依实际调用链核 Comparison/Risk/Snapshot/Artifacts/Canonical Storage/Shared Encoding/Operation Lifecycle/Repository Service、Surface/Bundle owning 条款。设计 CLEAR 和 A/B/C GO 均未代签本 D。

## 2. 本轮发现与连续关闭

### D1：通用 retry 的成功后检查覆盖了原 poll owner 的完成观察边界 — CLOSED

初稿 `048bd` 的 `repository_client/retry.py` 在 `control.run(operation)` 已返回成功结果后无条件 `control.check()`。这也作用于既有 `get_operation(deadline_at=...)`，使 `test_operation_poll_client.py::test_last_observed_wait_keeps_terminal_result_at_deadline` 明确接受的“handler 返回成功时 clock 恰到 deadline”的 terminal 观察先被丢弃；首次观察无 last_observed 时会抛 timeout。该问题由协调者与本人分别只读定位，没有运行失败测试，也未修改原 poll expected。

`7ebc` 仅改 client/retry 两文件 9 增/3 删：通用 retry 把已完成的原观察交回 poll owner；显式 cancel callback 路径仍检查当前控制；新 catalog API 在自己的公开返回边界显式执行完整 cancel/deadline 检查。Arrow 在已接住 transport、可确保关闭的 owner 边界检查。原 poll 实现和 expected 未动。本人与实际 `wait_for_operation_or_last_observed`、上述固定原测试及 get_operation 调用链逐项核对，此回归静态关闭。

既有慢在途 GET 的真实时间向量在 base 与全部 D 候选中本来已带 `serial`，未为误读追加 marker 或改变预算。

### D2：实际 Submit parent catalog consumer 尚未传当前控制，且新文档泛称全部 Backend commit reads — CLOSED

核 `infrastructure/repository_read/parent_catalog.py` 及 Submit prepare 的 `_build_prepare_import_build_input` 真实调用链时，发现该 consumer 仍直接调用新 catalog API、不传当前 probe/deadline。其位于既定 repository-read owner 内；不要求改 Submit planner/SQL/publisher 或引入新状态机。

`8d7a` 对 parent_catalog、既有 production-wiring 参数化 smoke 和 RS Contract 三路径作 27 增/6 删：入站先核当前 context，显式传当前 probe 与绝对 deadline；控制异常先恢复当前 KernelStopped/Timeout，普通 provider 错误仍沿旧 SubmitImportPublicationError。复用同真实 HTTP/client 参数表增加 parent-catalog 分支，未创建第二套控制矩阵；Contract 精确指 HTTPArrow 和 Submit parent catalog 两 adapter。原 exact-commit/表集校验、构包及恢复均未改。此缺口与文档精度已静态关闭。

## 3. 最终代码与 Contract 核查

| 边界 | 独立源码判断 |
| --- | --- |
| T3 校验与真实 producer | `finalize_submit` 已先完成 MatchingFinalizeFacts/replay 校验；随后从 `attempt.preview_result_id` 读取真实 Preview，核 workspace/repository 与完整冻结 configuration facts 相等，再用 `preview.operation_id` 触达。ConfigurationFacts 和 Preview 自身 owner 校验保证该 producer 与冻结事实闭合，不猜 pin owner 或 Submit operation。 |
| 临时 Preview 可选性 | T1 已把权威冻结输入移交 Attempt，原 T3 不依赖临时 Preview 行；缺行只跳过无法定位的可选维护，不猜 producer、不回填。存在行的解码、scope/frozen-facts 矛盾正常传播。owning Artifacts/Canonical Storage/Lifecycle 明确该边界，没有声称已发生 Preview GC 或新增生命周期机制。 |
| 窄事务和失败隔离 | UOW 在原活动 write transaction 内建立窄 SAVEPOINT；仅 typed `InvalidComputationCachePayload` 可在 ROLLBACK TO/RELEASE 成功且 outer transaction 仍 active 后脱敏记录并继续。未知 SQLite/IntegrityError、IOERR/CORRUPT/FULL/BUSY、rollback/release 或 outer-loss 错误均不在 catch 内吞掉；之后 CAS/业务写失败仍回滚全部 T3 和本次 TTL。 |
| 精确触达和回放 | 既有 SQL participant 按 producer/repository/kind/task/current manifest 和两表未过期 JOIN，稳定排序最多64项，触达 entry、精确 uses 和成员 TTL；不读文件、不调用 Repository/compute、不回填。FINALIZED replay 在新增触达前保原 closure/review 校验早返回。Submit 不推进 BaselineHead，原 Archive CAS owner 保持。 |
| DC94 | T1 即 PREPARED，prepare checkpoint 前冻结输入缺失稳定失败；checkpoint 后复用原包/ref/raw SHA/effect key，缺包不得重建。产品恢复路径未改；新增缺包向量放在原 import-builder owner，既有 prepare 前冻结输入失败与 checkpoint 重放 owner 保留，不复制恢复矩阵。 |
| client 请求边界 | `RequestControl` 只接通用 callback/absolute deadline，无 Backend import，不拥有 retry policy。catalog、Arrow open/error-body、每次 read/chunk 和 backoff 都受同一控制；pending IO 被取消后 await 收尾。open 在取消窗口恰返回时，abandon hook 关闭真实 client/response，避免失去已完成结果的清理 owner。 |
| 有界尝试和部分流 | 沿原 502/503/transport 策略的单请求共享最多3次 attempts；先关闭失败 attempt 再 backoff，没有 Backend 外层 HTTP retry。已暴露 bytes 后失败只报 stream failure，不从头拼接；控制异常先于 OSError 重试分支传播。关闭顺序与原 cleanup notes owner 保留。 |
| Backend 接线/分类 | HTTPArrow 和 parent catalog 显式传当前 probe/deadline；HTTP phase timeout 取原值与剩余 deadline 的较小值，原 idle timeout 仍在。原 provider timeout 分类保留；当前 operation 的 cancel/deadline 恢复为原控制异常，不变 cache miss/provider 包装。session policy 0 在请求前失败。 |
| N/M 与生命周期 | D 无新 pool、调度或预算；N1 实读仍1，上限 min(N,8)。spool、mapping、reader、consumer charge 沿原同 operation M/最后消费者，C 的 optional-first 释放、lease/root borrow/活动 pin 窄释放代码未改；没有因命中免计 M 或提前释放 backing。 |
| 删除/分层 | `_task_key` 已委托唯一完整 task identity，无旧 repr key；History 走 C 的 metadata-demand/独立 export lookup，不恢复全表预读或旧 checkpoint。client 无 Backend import，无新增 architecture baseline；未添加 migration/兼容/journal、独立 UID/helper 或范围外 proof。 |

新 T3 用真实 SQLite 的轻量向量证明真实 producer 与历史 pin owner 不同、精确 TTL/uses/成员触达、response-loss replay 不续期、缺 Preview 不阻合法 finalize、坏 payload 回滚维护前缀且脱敏、scope/producer 矛盾、未知 SQL/constraint 与后续 Attempt CAS 回滚。BaselineHead 不动由现 `test_t3_finalize_inserts_submission_and_switches_occupancy` 的权威断言保留。纯 SQL/type/cache 测试未引入 Dolt fixture；故障维度使用共享参数化表，无业务 golden 改写或由新 actual 反填 expected。

## 4. 固定执行稿与待验范围

已完整只读核 `/home/dev/gdds-s5-logs/execution/d-focused.sh`，最终 SHA256：
`331ebe525102bdd3d7cb98ea0306827be1d2dde5dacb284102aea18b6ea7925d`。

该稿可用于上述最终 candidate/不变 Rust tree，由唯一 D 测试者在合格空闲 CT 执行；本人未运行该稿或其 shell 语法检查。必要19步为：强制 native 重装、其余四包 locked offline sync、extension build-input、五包 ruff/mypy、client 五文件单进程，以及 backend 十文件 parallel/serial 两遍。Rust tree未改，本节不重复 fmt/clippy，不冒称本节已执行 Rust 检查。

client 选择原 GET retry、Arrow、poll、large catalog、versioned-read owner；backend 选择 finalize、transactions、prepare、import builder、parent removed-tables、recovery、computation cache、canonical commit、production wiring、architecture。新增真实等待向量及原 slow-poll 向量均为 serial；client 本就单进程。backend 用原 `(not serial) or parallel_safe -n4` 和 `serial and not parallel_safe -n0`，包含真实 Dolt/restart owner，无不适用空 serial 续步。

工具边界符合现行要求：BatchMode、执行时核空闲并原子本人占用；LAN bundle 身份与 clean detached/legacy；root Cargo PATH/禁设环境守卫、selector 四工具；本节点 offline uv/Cargo、磁盘 TMPDIR、worktree 外 venv/Cargo/日志/pytest/Hypothesis；新增 Dolt 可执行文件存在/hash 前置；所有 uv 消费经 wrapper，强制 native/build-input 绑定当前 tree。首非零停止后续执行，保 numeric command/tee/entry、HEAD/UTC/SHA 与失败现场；只在本人资源核空后释放标记，成功清理限定本 run 临时目录。该稿不是权威 runner，不生成 qualified 包闭包来源。

当前 **NATIVE/BUILD-INPUT、FIVE-PACKAGE STATIC、CLIENT FOCUSED、BACKEND FOCUSED = NOT_RUN**。返回真实原件后，仍须由本 D 原审核者核源码身份、每步 exit/SHA、失败/未知与资源释放，才可给 D EVIDENCE_GO；不能由本 CODE_GO 推算通过数量。

## 5. 容器、来源与后续边界

Current HEAD：`8d7a1580f3321608382a06e16334c733d1a0f4a8`。
Container rebuild required：本 D 内部 Python/SQL/Contract/测试改动无独立触发；未改依赖/锁、部署、entrypoint、容器 harness 或 container-only 行为。阶段最终候选的必要门禁仍须在 E 绑定。
Last verified image revision：仅历史 S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`；历史 backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`，镜像身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`。本轮未重算这些身份，未据其签当前镜像通过。
Container gate for current HEAD：**deferred 到 E 最终候选**；Carried from：none。
Deferred gates：E 的必要权威包与其中适用 Submit/History/Ordered Compose；实际闭包变化必须实跑，不能口头或跨节点 carry。同候选权威入口已覆盖的 Compose 不另重复。

没有 qualified runner、包 carried、Compose、真实 t1 或性能/容量结论。E 仍完成已确认标准 t1 最小冷查、新 operation 复查、真实 records 与完整 tar，以及最终实际/沿用/未验证矩阵和独立退出核收。本人仅连续完成 D findings/证据核收，D 固定交接后退出，E 必须新建角色；无 push 或提前 S5 exit tag。

---

原件：`/home/dev/gdds-s5-logs/reviews/d-r2.md`；SHA256：`ae51803fbcf5c88f7ed845d6c573a559e5ee85332392353067c66ade147c3c11`。

---

# P6 S5 D 连续产品复审 R2（首次 mypy 失败修复）

结论：**CODE_GO，绑定 `5610ae7025ac5c6269233a3d04613480292c99c8`**。本轮两项实际 mypy 类型错误已按真实 transport tuple 边界窄修，未发现新增代码阻塞。修后产品检查尚未运行，D EVIDENCE_GO 继续等待；不将原候选前十一项通过或 R1 代码结论改记为修后实测通过。

## 固定对象与独立性

- Candidate：`5610ae7025ac5c6269233a3d04613480292c99c8`；原被测候选：`8d7a1580f3321608382a06e16334c733d1a0f4a8`；完整 D base 仍为 `bf1f15393e1c1bfba8e906a9b2cc071affb1e7e2`。
- vnext tree：`9b1d4305cd416d123f87ed1328b74f26cc3582a3`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-d-5610ae7025`；exact HEAD、detached、index/tracked/untracked clean、正确 legacy 链接均已核。`8d7a..5610` 仅 `repository_client/arrow_stream.py` 一文件3增/2删，无测试/expected、Contract、依赖、锁或 Rust 变化。
- 本人仍为 D 原独立审核者，未实现或编辑被审修订，未改被审/被测 WT，未执行产品测试、语法、lint、fmt、编译、镜像或真实旅程，未创建子 agent、push/tag。只核 Git、源码、原件和摘要，仅写外置报告。
- R1 原文保留，SHA256=`b8c410a13e5b9aec59cf98feb83cd370a285aeeb402cce897eeab5ec1dd1aa8c`。

## 原始失败及实际执行边界

原件根：`/home/dev/gdds-s5-logs/execution/d-focused/20261109T101631Z-8d7a1580f3321608382a06e16334c733d1a0f4a8/`。

已读取原 mypy 日志、完整 steps.tsv 和 session，重新计算以下 SHA256，与交接相符：

| 原件 | SHA256 |
| --- | --- |
| `remote-evidence/mypy-repository_client.log` | `660a3251a34c25785792ec3f088600b8289c1ffbc4e7f62b875c9f6a3c62d47a` |
| `remote-evidence/session.log` | `66f251d95ee73eb3a11af9ad61965df28d0069bff03ed8abbfa461c511fb5235` |
| `remote-evidence/steps.tsv` | `061cc4d30c64a795a354d914ef1f78a9c4161c484a2b049a1f0b68dd49a132b0` |

06 session为2026-11-09 10:16:32Z–10:17:46Z，实际产品步骤10:16:35Z开始；起止及逐步 HEAD 均8d7a。前11项 command/tee0；第12项 mypy-repository_client 为 command1/tee0，报告两项错误：`RequestControl.run` 的泛型被外部 Optional cleanup 局部变量推宽，导致 abandon 回调 tuple 不兼容；validator 闭包捕获的 response 仍被视为 Optional。原入口1停止，backend/RS静态、client/backend focused均未运行；session记录 clean、failed temp preserved、cleanup0、本人 marker释放。该问题是产品源码静态失败，不按 DC68 工具重试计，不覆盖原日志或改记失败为通过。

## 修订核查与下一次执行

`_open_with_retry` 先让 `opened` 直接接住 `control.run(self._open_attempt, abandon=_close_opened_pair)` 的真实非 Optional tuple，再把它赋给原可清空的 `client/response` cleanup locals；validator闭包从 `opened[1]` 捕获真实 Response。两个泛型约束均来自实际 open API 和 abandon 类型，没有 cast/ignore 或扩宽类型。

新增的是无 await 的局部赋值：control检查、open、取消时 abandon、response校验、transport所有权转移、失败 finally关闭、503退避与总attempt数的顺序和函数体均未改变。真实 opened pair 在控制检查前仍可达；成功后仍转交 self._client/self._response，异常时仍由原 locals/finally关闭。保留 closed tuple 的短局部引用不替代或阻止实际关闭。R1 的 T3、poll终态观察、parent catalog控制与其余完整区间结论保持。

执行稿 `/home/dev/gdds-s5-logs/execution/d-focused.sh` SHA256仍为
`331ebe525102bdd3d7cb98ea0306827be1d2dde5dacb284102aea18b6ea7925d`，已重核未变。可交唯一 D 测试者绑定本 candidate/不变 Rust tree，在合格空闲 CT 按原19步必要范围复验；首非零停止、原numeric exit/SHA、离线/clean/占用和资源收尾规则均不变。本人未执行该稿。

Current HEAD：5610。Container rebuild required：本轮无独立触发，只有内部 client 类型推断修订；未触依赖/部署/容器 harness/container-only边界。Last verified image revision/source仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`，身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算。Current container gate：**deferred 到 E 最终候选**；Carried from：none。无 qualified runner、Compose、t1 或 E 预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/d-r3.md`；SHA256：`4d76f13cdeebc6bb00e5cdd2d1f5a213b861a2d49a3af28a71c30e260a6f5c0e`。

---

# P6 S5 D 连续产品复审 R3（合法故障前置与 RS 环境 profile）

结论：**CODE_GO，绑定 `cb2ad300845f73f12ae5367d247829623b728f18`；修订执行稿 GO**。两项新增测试的非法前置已窄修，原业务断言保持；三个现有集成 owner 的 Repository Service 环境位置故障有明确工具修订。可交唯一 D 测试者执行修订稿。修后候选和修订稿均未实际运行，D EVIDENCE_GO 继续等待；本轮混合失败不整体归为工具错误。

## 固定对象与独立性

- Candidate：`cb2ad300845f73f12ae5367d247829623b728f18`；原被测候选：`5610ae7025ac5c6269233a3d04613480292c99c8`；完整 D base仍为 `bf1f15393e1c1bfba8e906a9b2cc071affb1e7e2`。
- vnext tree：`8a28a9ab172d967eb526132084ec2b43b34b7c04`；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读 detached WT：`/home/dev/gdds-s5-review-d-cb2ad30084`；已核 exact HEAD、detached、index/tracked/untracked clean 和 `legacy -> /home/dev/gateway-data-management-system/legacy`。`5610..cb2` 仅 `test_submit_finalize.py` 一文件13增/7删，无产品、Contract、golden、依赖、锁、Rust或部署改动。
- 本人是 D 原独立审核者，未实现/编辑修订、未改被审/被测 WT，未运行产品测试、语法、lint、fmt、编译、节点、镜像或真实旅程，未创建子 agent、push/tag；只读原件/源码/Git和摘要，仅写本报告。R1/R2原文保持。

## 第二次原始执行及分类

原件根：`/home/dev/gdds-s5-logs/execution/d-focused/20261109T102051Z-5610ae7025ac5c6269233a3d04613480292c99c8/remote-evidence/`。已读取完整 steps.tsv、session及失败堆栈，重算以下SHA：

| 原件 | SHA256 |
| --- | --- |
| backend-focused-parallel.log | `cbca3b0623a75f560353d11e3d8041932b56a831ae7ef9c05558ad3187610aae` |
| client-focused.log | `3af7576f416a6363d5867f77224742003388419766374548e5e69bcf6202468c` |
| steps.tsv | `6929a0debbcce96a734aea9700efbd854b2264e5a04fcee98e9a39053e818c44` |
| session.log | `8df6d056308a0d0e28037a9d49242bbffd2070fd72dfbb20fcfaa51abfaebf0f` |

06 session为2026-11-09 10:20:53Z–10:22:46Z（runtime10:20:54Z开始），每步和收尾HEAD均5610且clean。前17步command/tee均0：native/build-input、五包静态及client **74 passed**；第18步 backend parallel **251 passed / 5 failed**、command1/tee0，原入口1停止，backend serial未运行。session明确失败临时现场保留、cleanup0、本人marker释放。

五个失败分别是：

- 两个新 scope 故障测试在 T3 前置阶段失败：workspace变异使用不存在的workspace触发FK；workspace-repository变异使用T1前缓存的旧version，实际已为2而非1。它们是产品测试源码前置错误，不按DC68工具修复计。
- 三个既有集成 owner 在 `submit_job_harness.py::_repository_service_python`（约424行）拒绝缺少 `vnext/repository_service/.venv/bin/python`。原稿确已把RS locked sync到外置uv-env并成功，但该真实consumer固定取项目内正常 `.venv`。这是执行profile和真实consumer不匹配，按同一具体工具故障的DC68第1轮修订处理，不改测试/expected、不跳过测试。

原混合失败和未跑serial均保原值；不因client74通过或前三包静态成功而把原入口改为0。

## 两项测试前置核查

workspace故障现在用既有 `seed_submit_ready_workspace(..., actor_id="another-actor")` 真实创建另一合法workspace，再把被审Preview绑定改到其ID。该helper按actor建立独立workspace、upload/preview身份；因此FK满足，但原Attempt的workspace与被篡改Preview仍确实不同。没有关闭外键或绕过域对象构造。

workspace-repository故障现在在变异事务中重读当前workspace，以其fresh optimistic_version执行原CAS并只改变repository；不再使用T1已推进前的seed版本。仍通过正常 `save_workspace`，未硬改版本或放宽CAS。

四个故障维度、`FinalizeBindingMismatch(match="scope")` 及 `_assert_effect_pending` 的Attempt/Submission/occupancy/ReviewSeed断言原样保留。repository和producer两个原有变异内容不变。没有改T3实现、错误类型或业务expected来接受失败；R1/R2的其余完整产品核查继续保持。

## 执行稿窄审

原稿 `/home/dev/gdds-s5-logs/execution/d-focused.sh` SHA仍为
`331ebe525102bdd3d7cb98ea0306827be1d2dde5dacb284102aea18b6ea7925d`，保留未改。
新稿 `/home/dev/gdds-s5-logs/execution/d-focused-revised.sh` SHA实核为
`5a16b2bc44a57f0f76dc4197a425605302383f6a51c0f47f3f7e9212736387e2`。

逐行diff仅：RS sync/ruff/mypy统一使用新建本人WT的 `vnext/repository_service/.venv`；session记该路径；成功且资源核空后，把该本人新环境加入现有清理列表。其他包仍用外置环境；19步、client五文件、backend十文件parallel/serial、离线wrapper/native/build-input、工具链/占用/clean/日志SHA和首失败停止规则均未改。没有symlink接线、临时改harness、跳过用例、允许空批或放宽断言。

fresh WT存在性守卫确保本次环境不是他人目录；uv同步创建正常项目环境，失败保留，只有成功且本人相关资源核空才清理该精确目录。该修订对应实际缺失前置，未接管旧失败现场或共享资源，也未改变产品镜像/依赖。可由唯一测试者绑定cb2及不变Rust tree执行；无需重开控制或恢复矩阵。本人未执行任一稿或其语法检查。

Current HEAD：cb2；修后产品检查与DC68 profile修订复验均 **NOT_RUN**。Current container gate：**deferred 到 E 最终候选**，Carried from：none；本轮测试前置/外置执行profile不触发独立容器重建，历史最后验证镜像仍仅S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`及其身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`，本轮未重算。无qualified runner、Compose、t1、carried或E退出预签。

---

原件：`/home/dev/gdds-s5-logs/reviews/d-evidence-review.md`；SHA256：`70c06d1ccf7a38e083e3e386800bdfe3434fb9e5f761f9c3b3fc09b568a16405`。

---

# P6 S5 D 独立证据核收

结论：**D CODE_GO / EVIDENCE_GO，绑定产品 `cb2ad300845f73f12ae5367d247829623b728f18`**。R1–R3连续审核的代码、测试前置和执行profile修订已有固定候选的必要实际成功原件。无剩余 D 阻塞 finding，可固定交接后进入 E。本结论不签 qualified runner、按包 carried、Compose、真实 t1、性能/容量或 E 最终门禁；E使用新角色。

## 固定对象与独立性

- D base：`bf1f15393e1c1bfba8e906a9b2cc071affb1e7e2`；最终产品：`cb2ad300845f73f12ae5367d247829623b728f18`。
- vnext tree：`8a28a9ab172d967eb526132084ec2b43b34b7c04`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`，与 A/B/C 相同。
- 原只读 detached WT `/home/dev/gdds-s5-review-d-cb2ad30084` 已再次核 exact HEAD、两棵 tree、detached、tracked/untracked clean及正确 legacy 链接。根实施者没有修改该审核 WT 或已运行候选。
- 同一 D 原独审 R1–R3 原文分别保持 SHA256 `b8c410a13e5b9aec59cf98feb83cd370a285aeeb402cce897eeab5ec1dd1aa8c`、`ae51803fbcf5c88f7ed845d6c573a559e5ee85332392353067c66ade147c3c11`、`4d76f13cdeebc6bb00e5cdd2d1f5a213b861a2d49a3af28a71c30e260a6f5c0e`。
- 本人未实施或编辑产品、测试、Contract、被审/被测 WT，未运行产品测试、语法、lint、fmt、编译、镜像或真实旅程，未访问测试节点、创建子 agent、push/tag。本机 Python 仅解析既存 TSV并以标准库hashlib核既存原件，不import/执行产品。只写本外置报告。

## 原件与逐项完整性

成功原件根：`/home/dev/gdds-s5-logs/execution/d-focused/20261109T103403Z-cb2ad300845f73f12ae5367d247829623b728f18/`。

| 原件 | 独立重算 SHA256 |
| --- | --- |
| 已审执行稿 `/home/dev/gdds-s5-logs/execution/d-focused-revised.sh` | `5a16b2bc44a57f0f76dc4197a425605302383f6a51c0f47f3f7e9212736387e2` |
| remote-evidence/session.log | `264979dd0e73eba148096edc889ce717db76dfaedeaddd0126193be0fb7bcb19` |
| remote-evidence/steps.tsv | `b1cfff7ba17c36829c6285987c87ff8ac160a777f794695d8f7b9cfb48b8fe6c` |
| remote-evidence/client-focused.log | `9921d43b13663261822d35c45b8f8153f81b33fe9ee384374960f204d1dd3437` |
| remote-evidence/backend-focused-parallel.log | `b4d0df3647aef2e8fb8184268444b422eb43b3dd6c7f7f85c202c78e567be07d` |
| remote-evidence/backend-focused-serial.log | `42d843a7cd3688487cf5fdc6ec7e5cdbdefd990ed183ec947925359f1d874ad2` |
| remote-evidence/extension-build-input.log | `d5bea696dcb6b10a24b7e63f34c96b27fbb32fa9df1ec0775d1157b3be8c893c` |
| source.bundle | `0e03cfa620169dce09f9ef7aa978452093c957220e4dfe009657cd9742f517d7` |
| 本地 SHA256SUMS | `b13f879fe9a93193810f8df5d843dcf9c24d213b6fd0c8984b4eb2977916acc8` |
| remote-evidence/SHA256SUMS | `ab5ff678bb6c3669e0cc2f704798149542d43cb85b96e3e3561f7af3064a1d1d` |

成功批次本地manifest31项、remote manifest22项全部重新计算匹配；两份manifest自摘要及orchestrator自摘要亦匹配。remote清单记录的节点绝对路径按同名复制原件映射到remote-evidence后逐件核验，没有在另一节点计算产品闭包。19行steps的HEAD、start/end、command/tee数值和对应日志SHA逐项与日志原文一致，全部command0/tee0。先前执行摘要曾把serial日志SHA误贴为steps SHA；实际steps原件上述b1cfff未错，未修改原件接受转录值。

bundle-build及remote verify日志绑定唯一ref精确cb2，5,776,172 bytes及SHA一致；本人只读列出bundle heads亦精确cb2。来源main、远端checkout/每步/finish HEAD一致。脚本的fresh WT/clean/legacy守卫已通过，finish明确clean；环境、日志和运行产物按已审路径隔离。

## 实际成功范围与执行边界

执行节点 `ct107-gw-dms-06` / `gw-dms-06.lan`。controller local开始2026-11-09 **10:34:03Z**；remote session **10:34:06Z–10:36:18Z**，runtime/实际产品步骤 **10:34:07Z–10:36:17Z**。时间分别按其原日志报告，不由摘要转录替换。admission保存Compose空、8000无listener和原子本人marker；执行稿前后检查相关Dolt/pytest/Cargo/uv等进程、容器和端口。finish记录cleanup0、本人marker已释放，local兜底释放记录已释放/非本人且0，未删除他人标记。remote、outer tee、copy和local入口全部0。

实际19步均通过：

1. backend经受控wrapper locked/offline同步，显式强制重装gateway-compute-python，原日志实际出现Building/Built；其余四包同步成功。build-input实核 expected=installed=`c0213e18a9645c5cfbd39f310f532273a03a10cb`。
2. 五包ruff/mypy共10步成功；mypy分别为shared_kernel34、repository_contracts15、repository_client26、backend542、repository_service201个source files无问题。
3. client五个既定HTTP/Arrow/poll/large catalog/versioned-read owner文件单进程实际 **74 passed / 0.89s**。
4. backend十个既定文件以非serial/parallel_safe表达式、4workers实际 **256 passed / 2 warnings / 27.20s**；serial非parallel_safe、`-n0`实际 **4 passed / 256 deselected / 9.61s**。deselected不计为运行；两条warning为现存Starlette/httpx弃用提示，非失败或skip。

这批实际覆盖D的T3真实producer与scope/frozen-facts、精确TTL/uses/成员、缺Preview/cache可选性、坏payload窄回滚、未知SQL/constraint与CAS整体回滚、回放不续期；DC94冻结输入和checkpoint复用/缺包；真实HTTPArrow/Submit parent-catalog控制接线；client三尝试/退避、在途取消/deadline、transport关闭及原poll完成观察。既有实际Submit parent-table removal和恢复consumer已进入本次成功集合。没有用纯mock代替实际client/SQLite路径，也未改业务golden来接受失败。

RS sync/静态的实际命令使用本人新WT下正常 `vnext/repository_service/.venv`，日志明确 `Creating virtual environment at: .venv`；其余包仍为外置uv-env。这使固定取该python路径的原harness真实启动，未使用symlink或改harness。成功临时环境按已审稿在资源核空后清理，旧失败现场和全部原件保留。

session明示UV_OFFLINE=1、CARGO_NET_OFFLINE=true，使用本节点既有预填uv/Cargo缓存，无新依赖/锁变化、无公网/转发代理步骤。uv0.11.28、Python3.14.6；root PATH与selector四Rust工具均为/home/dev/.cargo/bin的1.97.0，禁止Rust环境守卫保持；Dolt可执行文件SHA实录。TMPDIR为磁盘/home/dev/gdds-test-tmp，Cargo jobs4/pytest workers4是测试并行度。生产仍N1、单active、32GiB−8GiB/M24；focused小预算向量不是额外生产M授权或M24容量/RSS测量。Rust tree未变，本节只实际native/build-input，不宣称另跑Rust fmt/clippy/test。

## 两次旧失败与修订闭合

两次旧run的local/remote manifests、各自manifest自摘要、orchestrator自摘要及每步HEAD/exit/log SHA也已独立重核，全相符；第一次分别24/15项、第二次30/21项，原numeric exit未改为0。

| 原候选及原事实 | 当前闭合 |
| --- | --- |
| 8d7a：12步，前11步0，client mypy2项错误、command1/tee0；其后静态/全部focused未跑；原入口1 | R2用真实opened tuple窄修泛型/Optional推断；最终五包静态及client74实际通过。不是DC68工具错误。 |
| 5610：前17步0含client74，backend parallel251通过/5失败、command1/tee0；serial未跑；原入口1 | R3两项fixture前置分别改为合法外workspace FK与fresh workspace CAS，原业务断言保持；最终四个scope维度通过。另三个RS正常环境路径前置由已审profile首轮DC68修订闭合，最终真实集成consumer通过。原混合失败不整体改称工具错误。 |

旧失败session均记录clean、失败临时现场保留、cleanup0和本人marker释放。R1本轮核查期间发现的poll成功后deadline回归及parent-catalog实际consumer缺口、R2类型修订和R3两项合法前置/工具profile均已同原审连续关闭，并在本次固定cb2实际范围完成复验。不以成功候选倒改原失败、未运行项或qualified来源资格。

首轮8d7a的原session另精确区分为start `10:16:33Z`、runtime_start `10:16:34Z`、首个产品step `10:16:35Z`，均止于 `10:17:46Z`。R2报告中沿早前交接写的session开始 `10:16:32Z` 是文字转录误差，本报告按原件订正，不改R2原文或原日志。已只读核外置D handoff草稿，其产品/tree、成功结果与SHA、旧失败分类和E边界相符；首轮表内 `10:16:35Z` 应标为“产品步骤”，或把runtime开始写回原件 `10:16:34Z`，不能混作session开始。草稿的EVIDENCE_PENDING是本报告前状态，协调者可逐字附入本报告/SHA后机械更新为D EVIDENCE_GO。

## 容器、E与角色收尾

Current product HEAD：`cb2ad300845f73f12ae5367d247829623b728f18`。Container rebuild required：D没有独立依赖/锁/部署/entrypoint/container harness/container-only触发；当前镜像/容器门禁 **deferred 到 E 最终候选**。Last verified image revision/source仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、backend runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、镜像身份原件SHA=`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`；本轮未重算身份。Carried from：none。

D使用focused脚本，不是run-tests.sh权威包执行，没有qualified runner manifest或包沿用来源；没有Compose、真实t1、性能/容量或阶段退出结论。E仍在固定最终产品V完成实际闭包要求的权威包/适用Compose和已确认标准t1最小冷查、新operation复查、真实records/完整tar，明确实际/沿用/未验证，独立核收后才可退出。不得口头或跨节点carry，不能用设计CLEAR或本D GO代E。

协调者可逐字归档R1–R3和本报告，按上述固定身份/原件/SHA/失败边界完成D交接；报告结论始终绑定cb2，不给后续产品变动预签。D原审完成本节findings和必要证据核收后退出活动分工，E由新建实施/独审/唯一测试角色接手，不以follow-up复用D角色；无push或提前S5 exit tag。
