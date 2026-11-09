# FE3c 审核报告

- **审核对象：** 分支 `fe-vnext`。
  - 代码候选 `09351e42adf91a17d48c57c47ac24444e39f051a`，`frontend/` 树 `6158d776080e82a7fa9696a1a18675e1208dd799`；
  - handoff 提交 `1df3dc05e23e147b30afe822414b9cf3aa089313`（只新增 `docs/frontend-vnext/fe3c-handoff.md`，`frontend/` 树相同）。
- **范围：** `fe-fe3b-exit..1df3dc05e2`（`fe-fe3b-exit` → `ed5d2c24e9`）。来自 main 的文档与 `vnext/` 不在范围内。
- **依据：** [FE3 kickoff](../fe3-kickoff.md)（main `b7ef13d884`）§2.3、§4.6、§4.7、§5.2 末段、§5.3“FE3c 的补充”、§6.4、§8、§9、§10、§13.6、§16；V2 交接；归档业务核验设计 §6、§7.1、§10；Q18 答复与交接。
- **日期：** 2026-11-09（时间均为 UTC）。
- **结论：定向修复。** 不需要重写（§7）。
  - 已做到：路径核对全部通过；快照与后端原件规范化后逐字节一致，生成类型一致；`selected` 由一个构造函数生成，生产路径没有转发候选对象；关闭的 `expected_review_version` 取自同一次加载的候选；
    §4.6 的 `anomalies` 集合在 J1、J2 每次预检都与表一致；handoff 中 193 个十六进制值逐个回源，54 组“路径 + SHA”配对全部正确；07、05 上我的独立运行都通过；kickoff 规定的探针中 P1–P4 与 P5 的“工作区版本号”变体在预期位置失败，P5 的“读 Review”变体没有被拦住，J2 的“重试不带 key”只在后面偶然失败（§2.3）。
  - 需要修复（§4）：J2 第 4 步的中断发生在请求到达 backend 之前，真实 backend 上没有验证同 key 的 200 回放，也没有先接受 BTU（B1）；§4.6 的 `business_validation.issues` 只在 J1 第 2 步比较（B2）；
    阻断项与若干错误、禁用原因的文案与 §16.3–§16.6 不符（B3）；“一次加载”的重新加载只重做预检（B4）；多个 V 用例没有区分力或缺断言，§16.9 要求的单测缺失（B5）；
    t1 运行脚本没有按 §8.1 核对输入清单，`baseline_to_initial.table_count` 未记录（B6）；§9 的截图缺口（B7）；handoff 多处与实际不符（B8）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| 合并提交 `03880f1e75` 的父提交 | `ed5d2c24e9`（`fe-fe3b-exit` 指向的提交）与 `fd9e383d76` |
| `HEAD:vnext`（`09351e42ad` 与 `1df3dc05e2`） | 都是 `6368c9c40cf08a97eecf2a0c457a6c16ce448080` |
| `git diff --name-only fd9e383d76 1df3dc05e2` | 只有 `frontend/`（54 个路径）与 `docs/frontend-vnext/`（7 个，含 handoff） |
| `--print-input` | 05 的 t1、journeys 日志与我的 journeys 日志都是 `dependency_input_sha256=578e079b762e…`，即 `lock-578e079b762e` |
| `frontend/openapi.json` | SHA256 `4c2ddca7…620a`，等于我在开发主机对原件 `ce58f20a…c079` 按 §5.1 规范化的结果；相对 FE3b 快照只多 `ArchiveCandidateResponse.review_version` 两处 |
| 生成类型 | 07 运行中 `generated-types.test.ts` 逐字节重新生成通过 |
| 运行时比对 | 05 上 t1、journeys 与我的 journeys 运行都是 `openapi_compare=match` |

本轮前端改动：`ArchiveMainlineDialog.tsx`（业务核验、接受/撤销、关闭）、`journeys.ts`（`buildArchiveSelectedRef`，删除逐项追加异常）、`ReviewActions.tsx`（§16.7）、`archive-validation-data.ts`（新，V 场景数据）、`mock-data.ts`（错误码、`selected` 422、关闭路由幂等键）、`e2e/archive-validation.spec.ts`（新，V1–V10、V13、V14）、`e2e-real/journeys.spec.ts`（J1、J2）、`e2e-real/t1.spec.ts`（新）、`run-real-backend-e2e.sh`（fe3c 完整集与 t1）。
打包代码（`features/upload/`、`UploadStepCard.tsx`）在本范围内没有改动，按 Q20 不需要 t4 重测。

## 2. 证据、独立运行与探针

### 2.1 handoff 中的证据（逐项回源）

- 用脚本把 handoff 中每个十六进制值（193 个）与来源对照：节点上重算的文件 SHA256（05 的 `fe3c-05/` 与 07 的 `fe3c-07/`、截图目录，共 317 个文件）、开发主机的 git 对象、四个最终运行日志原文、原件重算。188 个命中来源；其余 5 个不是 SHA（UUID 片段两处、旧 tag 名 `lock-d054366c02fa` 两处、`9007199254740991`），都核实无误。
- 按“路径 + SHA”逐对核对 54 组：42 张模拟截图（宽度与文件名对应）、4 张 t1 截图、4 个运行日志、4 个校验包（与校验日志一致），**全部正确**。没有长度异常的 SHA。
- 四个最终运行日志都记录 hostname、起止 HEAD、`frontend_tree`、exit 0；05 的两次真实运行 `cleanup_status=ok`、`openapi_compare=match`。
- t1 输入：我在 05 上进入 `t1-v1`、`t1-v2` 按 FE3a 清单逐文件核对，19/19 一致，两份清单文件的 SHA256 与 FE3a handoff §4.1 相同（`cdb598cd…0163`、`fa2450fa…a96a`）。即本次 t1 用的是正确输入，但这一核对不是运行脚本做的（B6）。
- t1 case log 中 §8.3 的数值与 handoff 一致：`t1-step3 anomalies=[]`、`composite_changed=0`、M1 两行；`baseline_to_initial.table_count` 确实未记录。

### 2.2 我的独立运行

源码以 git bundle 传入（`refs/review/fe3c-r/candidate` → `09351e42ad`、`refs/review/fe3c-r/handoff` → `1df3dc05e2`，bundle SHA256 `2e725481b5da3178e3442622fae50b6c78e97f1014de9a2b2b141ed03e854e5f`，两节点 `bundle verify` 通过），在 detached worktree `/home/dev/gdds-fe3c-review-run` 上运行，起止 HEAD 都是 `09351e42ad`、`frontend/` 树 `6158d776`，起止 `git status --porcelain` 为空。外层包装记录 hostname、起止时间与 HEAD、入口 exit；日志在 `/home/dev/gdds-fe-logs/fe3c-review/`。运行前两节点都没有占用标记。

| 节点 | 内容 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 07（`gw-dms-07`） | `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2`，默认缓存路径，14:33:15–14:35:23Z | exit 0：单测 33 个文件 188 项（含生成类型逐字节核对），Playwright 80 项；截图 172 张，目录 `/home/dev/gdds-fe-shots/fe3c-review-09351e42`，清单 `shots.sha256` 的 SHA256 `2c70fdbb82cd71735a540173073964f4812a512b0952b4b3db23f258cc705502`；工具链 config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，npm 缓存归档 `0d861824…89f4` | 入口 `1cbca6478147d25bdde7cc998ecc7bdd4a6fba7b9d733071f92473a543e15898`；外层 `33bb9886696aa568a33a17ea3049c29fa3beabb080585ce4d7649025daaeb175` |
| 05（`gw-dms-test-05`） | `run-real-backend-e2e.sh --suite journeys --subphase fe3c --session fe3c-review`，fe0 缓存两变量，14:32:53–14:40:19Z | exit 0：20/20（含 J1、J2）；`openapi_compare=match`；`cleanup_status=ok`；`dependency_input_sha256=578e079b…`；RS config digest `sha256:9b8c208d…014a9f`（与 handoff §9.2 相同）；日志无 token；占用标记由脚本取得并释放 | 入口 `632aecbcc2789eb3647c103a43a75ad4f5f498ef25220a34eaec5e6681eedc68`；外层 `794a7718851d5f2103209578b772e8be3c9e3ef2bf81cf42c00f2c5a9248a8d2` |

我的 journeys 运行中 §4.6 的各次 `anomalies` 集合与实施会话的运行相同（J2 第 4 步 C 的 `review_version=1`）。t1 按 §13.6 不重跑（§2.1 已核日志与截图 SHA256）。

### 2.3 探针（一次性提交，只在节点上）

每个探针是在节点上从 `refs/review/fe3c-r/candidate` 新建的 detached worktree 中的一个已提交改动，ref 为 `refs/review/fe3c-r/probe-<名>`，diff 存于日志目录。07 的探针在工具链容器中（网络 none，离线 `npm ci`）运行 `e2e/archive-validation.spec.ts` 全部 15 项；05 的探针用 `run-real-backend-e2e.sh --suite journeys --subphase fe3c --session fe3c-review` 运行完整集。

| 探针 | 节点 | 提交 | 改动 | kickoff 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | 07 | `08ebef4593` | 分组内按 `target_submission_id + issue_code` 去重（同码同目标两卡合并） | V2 失败 | **符合**：只有 V2 失败 | `e9f17a0aef133c0af3fac273d5619e21f5389d68d6e3d20a8a43bd5fb394f80e` |
| P2 | 07 | `b2d43ee961` | 已接受的卡另加成功色标签“通过” | V3 失败 | **符合**：只有 V3 失败 | `2aa6c8f90da0ffd9a83bb192c1e6ef471678e97cf3af25e862569458903a1fa4` |
| P2b（附加） | 07 | `a32b088f10` | 只把“已接受”标签改为成功色 | （§16.3 不允许） | **15 项全部通过**：V3 不检查色调（B5） | `13c973d3135f70a2c08f341f0fcdd7d118b8d0f977ac0df749ac014982cfa602` |
| P3 | 07 | `1796724495` | 开始归档只发送前 50 项引用 | V6 失败 | **符合**：只有 V6 失败 | `a0d922618845371599deb7670fde1949d4101d8738c4f811c9e057ab4bf0d338` |
| P4 | 07 | `eb56cb5fc2` | 预检改回转发整个候选对象（含 `review_version`） | V14 失败 | **符合**：路由桩返回 422，对话框停在加载失败，15 项全部失败（含 V14） | `31282d77dd618d351e435d88b824b9dda0e3f9cb51d62b9a8ded6dba53bfbd7e` |
| P5a | 07 | `bc0486e9d2` | 关闭的 `expected_review_version` 改为读 Review GET | V9 失败 | **不符：15 项全部通过**。模拟 Review 与候选的版本按 §5.3 相同，V9 又没有断言“没有 `GET .../review`”（B5、D1） | `4d9b93cd1ff954191529a2e96e6848a714b7ae9c926442d3165ff6a25bcf392c` |
| P5b | 07 | `09fe60584b` | 关闭的 `expected_review_version` 改为工作区 `optimistic_version` | V9 失败 | **符合**：只有 V9（关闭携带同次候选版本）失败 | `2ab658a3e7ec4088389a7e19c2e1640db3760f140f4d7873927bccf59721d79b` |
| J2a | 05 | `4e505084be` | 关闭重试不带 `Idempotency-Key` | J2 第 4 步失败 | **J2 失败，但失败点不在第 4 步**：backend 对重试返回 422，`closeDialog.getByText("已关闭")` 却被对话框静态文字“标记为‘已关闭（未归档）’”满足而通过，直到第 1780 行等“候选集合已变化”提示才失败（B1）；其余 19 项通过 | `d950ff3691ff5e9f6a02246d528de122e7fc20efb7a8956539eb8ca6330aaaf8` |
| J2b（附加） | 05 | `ab43497cb6` | 关闭重试改用新的 `Idempotency-Key` | （§16.6 要求同一 key） | **20 项全部通过**：第一次请求被 `route.abort` 拦在浏览器内，backend 只收到一次关闭（201），没有回放可验证（B1） | `bb2c312bb4aeae755591eb61bb963464624f1a5c57a2006b1c3c31c1505a3c58` |

07 探针日志的 SHA256 另记于 07 `/home/dev/gdds-fe-logs/fe3c-review/probes/SHA256SUMS`；提交号在节点上按 ref 核对。

**清理：** 探针 worktree 运行后即删除；探针 ref、节点上的传输 bundle 与探针打包文件已删除；diff 与日志保留在两节点的 `/home/dev/gdds-fe-logs/fe3c-review/`。为复审保留：05、07 的 `/home/dev/gdds-fe3c-review-run` 与 `refs/review/fe3c-r/{candidate,handoff}`，开发主机的只读审核 worktree `/home/dev/gdds-fe3c-review-wt` 与同名 ref；FE3 退出时清理。

## 3. 逐项核对（§13.6 重点）

### 3.1 业务核验界面（§16.2–§16.5）

| 要求 | 结果 |
| --- | --- |
| `selected` 每项恰好两个键，由一个构造函数生成 | **符合。** `buildArchiveSelectedRef`（`journeys.ts:378`）逐字段构造；对话框初次预检（`:230`）、接受/撤销（`:312`）、开始归档（`:428`）都用它；`runArchiveJourney` 只转发它的结果；`ArchiveMainlineDialog.tsx:87` 的整对象转发已删除。模拟路由桩对多出或缺少的键返回 422，单测覆盖四条路由。探针 P4 证实 |
| 原始诊断与处理状态分开，接受后不显示为通过 | 符合；“已接受”用中性色调。但 V3 不检查色调（P2b，B5） |
| 每个 `subject_digest` 一张卡，① 与 ② 分别接受、撤销 | 实现符合（卡片以 `subject_digest` 为 key，不合并）；P1 证实 V2 有区分力。V2 没有覆盖“各自撤销”与 ② 的请求（B5） |
| 理由必填，1–4096 UTF-8 字节，超过 3500 显示字节数 | 实现符合（`TextEncoder` 计数，去首尾空白判空，发送原文）。V9 没有覆盖 4096/4097 的多字节边界（B5） |
| 没有批量接受或默认理由 | 符合：没有多选、全选，理由框初始为空 |
| 接受请求的绑定字段取自同一次预检 | 符合：`head`、`candidate_set_digest`、subject 各字段、`expected_sequence = latest_sequence` 都取自当前 `plan`；`action` 按 `subject_kind` 穷举（`assertNever`） |
| 冲突后只刷新、不自动重发 | 符合：四个 409 关闭对话框并 `refresh()`，不重发；V5 断言只有一次请求 |
| 阻断项没有接受入口 | 符合（阻断项只有文字与“重新预检”）；但文字不符 §16.5（B3） |
| 开始归档的引用来自最新预检，不分页、不截断 | 符合：`runArchiveJourney` 重新预检后取全部 `ACCEPTED` 项；V6 的 399 项在全部分组折叠时仍全部发送；P3 证实 |
| “一次加载”候选与预检的 `candidate_set_digest` 相同 | 有比较，但不同时只重做预检、不重读候选，重新加载必然失败（B4） |
| 核验概况、分组、详情 | 基本符合 §16.3；BTU 问题文字缺后半句，来源详情的摘要没有悬停全文，理由没有 3 行折叠（B3、N3） |
| “确认归档”禁用原因 | 顺序与文字不符 §16.5（B3） |

### 3.2 关闭（§16.6）

| 要求 | 结果 |
| --- | --- |
| 入口（Q16 甲） | 符合：只在对话框第 4 节“候选提交”，每行“关闭（不归档）”，选中项也可关闭；组态树与顶栏没有入口 |
| 对话框文案 | 标题、目标名、五条影响说明、理由规则、确认勾选、危险按钮“确认关闭”都与 §16.6 一致 |
| `expected_review_version` | 符合：打开对话框时把同一次加载的候选对象与 `head` 固定在 `closeSnapshot`，重试用同一 key 与同一 body；对话框内没有 Review GET。P5b 证实 V9 能拦住工作区版本号；P5a（改读 Review GET）**没有被 V9 拦住**（B5、D1） |
| 201/200 显示服务器返回的关闭人、时间、理由 | 实现符合（显示 `closeResult` 的字段）。但模拟用例与真实旅程都没有走到 200 回放（B1、B5） |
| 关闭后自动重新预检 | 符合，并显示“候选集合已变化”提示（V10、J2 第 4 步） |
| 409/403/404/422 等 | 409 各码按 §16.6 处理；404 没有专用文案，413/429/503 显示服务器 message 而不是“关闭未完成”（B3） |

### 3.3 审核顶栏（§16.7）

`APPROVE` 的 `BASELINE_VERSION_CONFLICT`：提示原文一致，之后“通过”禁用、原因正确，“退回”“撤回”可用（V11）；`ARCHIVE_CLOSED` 提示一致（V12）。
两处不足列为非阻塞（N2）：过期通过只重读 review、不重读 History；V12 的模拟数据重读后仍无处置，没有断言“按 §6.4 显示”。

### 3.4 模拟数据（§5.3、§16.8）

- 候选全部带 `review_version`，用生成类型约束；V 场景取 11/12/13，与工作区（3）、基线（7）不同，且等于同一提交的 Review GET（§5.3）。
- `selected` 422 与关闭路由的 `Idempotency-Key` 都在 `validateSimulatedRequest` 一处实现，有单测。
- 错误码：关闭路由与 `POST /v1/archives` 的新码已加入取值表，由既有的“按 OpenAPI 描述核对”单测覆盖。
- 可达性单测覆盖 `UNRESOLVED` 的三项为空、来源 `UNEXPLAINED`、BTU 的 `BASELINE` 与全部候选、两侧不同 subject、399 项的构成、阻断与待审核。缺：`ACCEPTED`/`REVOKED` 的字段规则、MODIFIED_ONLY 只有 ② 侧、数量不超过 8N+1；也没有任何 `REVOKED` 的模拟数据（B5）。

### 3.5 真实旅程与 t1

- **J1：** 每次预检的 `anomalies` 集合都与 §4.6 表一致（第 2、7、11、13 步）；第 3 步在界面上接受→撤销→再接受；第 6 步待审核阻塞显示 C 的名字与附注；第 9 步第二个 context 撤销后，第一个 context 开始归档被服务器拒绝，重新预检显示“已撤销接受”；D 的身份确认、三节点历史比较都在。
  第 8、10、11、13 步的接受用 API 助手完成，不经界面（N4）。第 7 步来源 `EXPLAINED`、各步 `business_validation.issues` 未断言（B2）。
- **J2：** 第 3、5、8 步集合一致，第 3 步三个来源 `EXPLAINED`；关闭后 s2 工作区释放、树显示“已关闭（未归档）”与关闭人、Review 为 `APPROVED` + `CLOSED_NOT_ARCHIVED`；第 7 步 E 显示“归档时选中了其他提交”。第 4 步见 B1。
- **t1：** §8.3 由程序判定；预期值在宿主机用 `python3 -I` + `ast.literal_eval` 从同一 vnext 树读取；FULL 两个比较对按 `pair_id` 取用。`composite_changed` 取不到时按 0 处理、`baseline_to_initial.table_count` 未记录（B6）。
- **M1：** v1 MODIFIED_ONLY renderer 增量 30,351,360 B（28.95 MiB），为 FE3a 24.86 MiB 的 1.164 倍，低于 2 倍；FULL 7,270,400 B 只报告。FULL 的数值低于 MODIFIED_ONLY，原因是两次测量在同一个浏览器实例中进行，第 4 步复用了第 1 步已扩大的堆（§8.4 要求每次测量用新浏览器）。t1 只作回归对照，不影响结论（N6、D2）。

## 4. 需要修复（阻塞）

### B1 J2 第 4 步没有在真实 backend 上验证同 key 回放，也没有先接受 BTU

- kickoff §4.6 J2 第 4 步：“接受 `BASELINE_TIME_UNAVAILABLE`；…关闭请求**送到 backend 后**对浏览器中断一次，前端用同一 key 重试 | 201 后回放 200；界面显示服务器返回的关闭人、时间与理由”。R5 的做法是 `route.fetch()` 送到 backend 后再 abort。
- 实现（`journeys.spec.ts:1748-1758`）第一次直接 `route.abort("failed")`，请求没有到达 backend；重试得到的是首次 201，**没有走到 200 回放**。用例只比较两次 body 相同，不比较 `Idempotency-Key`，不断言重试的状态码，也不断言界面显示的关闭人、时间、理由。
- 探针 J2b（重试换一个新 key）20 项全部通过，backend 只收到一次 201；探针 J2a（重试不带 key）时 backend 返回 422，但第 4 步的 `getByText("已关闭")` 被对话框里的静态影响说明“标记为‘已关闭（未归档）’”满足，J2 到后面才偶然失败（§2.3）。handoff §4.3 写的“同 key 重放 201→200”不成立。
- 第 4 步也没有先接受 BTU，因此第 5 步“此前接受的 BTU 也回到未处理”（§4.6 的要点）没有被证明，“7 项全部 `UNRESOLVED`”是平凡成立。
- **修复：** 先在界面接受 BTU；关闭请求用 `route.fetch()` 送到 backend 后对浏览器 abort，重试后断言：两次请求的 `Idempotency-Key` 相同、body 相同，重试响应 200，界面显示的关闭人等于归档确认人的 `actor_id`、时间与理由等于响应体；第 5 步断言原 BTU 的 subject 不再出现、全部项 `UNRESOLVED`。另断言归档确认人的会话全程没有 `GET .../review`（§16.9 末段的 V9 真实覆盖）。

### B2 §4.6“实测校正”只比较了一半

- §4.6 规定每次带 `selected` 的预检都把 `business_validation.issues`（去掉同级、身份两类）与 `anomalies` 的 `(subject_kind, issue_code, side, 受影响提交)` 与表比较。实现只在 J1 第 2 步比较了 `issues`，且 `businessIssueSet` 不含受影响提交；J1 第 7、11、13 步与 J2 全部预检只比较 `anomalies`。
- J1 第 7 步表中写明“来源：B `EXPLAINED`（匹配当前基线）”，未断言（handoff 自认缺口）。
- **修复：** `expectAnomalySets` 同时比较两个集合（含受影响提交）并写入 case log；J1 第 7 步断言 B 的来源 `EXPLAINED` 且匹配当前基线。

### B3 文案与 §16.3–§16.6 不符

| 位置 | 现状 | kickoff |
| --- | --- | --- |
| 阻断项（`ArchiveMainlineDialog.tsx:574`） | `ACTIVE_SUBMIT_ATTEMPT`、`ARCHIVE_INTEGRITY_FAILURE` 与其他编码都只显示原始码（正文与 `<code>` 各一次）；V7 断言的正是原始码 | §16.5 表：“已有提交正在处理，完成后才能归档”“归档数据完整性校验未通过，不能继续，请联系管理员”；其他“当前不能归档”加原始码；原始码放悬停/Debug（C6） |
| 禁用原因（`:439-448`） | 顺序：正在预检→阻断→未知→未处理→勾选→预检失败；预检失败且未勾选时显示“请确认归档选择”；文字“还有 n 项未处理” | 预检失败排第 1；“还有 {n} 项异常未处理” |
| BTU 问题文字（`:36`） | “当前基线没有可用的生成时间” | “当前基线没有可用的生成时间，本轮无法比较时间先后” |
| BTU 详情 | `NO_VALUE`/`NO_VALID_VALUE` 不带计数 | 同 `GENERATION_TIME_MISSING` 的文字（含计数） |
| 关闭 404（`closeError`） | 显示服务器 message | “未找到该提交，请重新预检” |
| 关闭与接受的 413/429/503 等 | 显示服务器 message | “关闭未完成”/“操作未完成”加错误码 |
| `retryClose` 收到 `ARCHIVE_CLOSED` | “提交或基线已变化，已重新预检” | “该提交已归档或关闭” |

**修复：** 按表改正，并在用例中断言 kickoff 文案（V7 改为断言中文文字，原始码只出现在悬停或错误码区）。

### B4 “一次加载”的重新加载只重做预检

§16.2：两次读取的 `candidate_set_digest` 不同“即作废该次加载并重新加载”。实现（`:237-245`）不同时只再预检一次，并与**旧的**候选读取比较；候选集合确实变化时 digest 不会回到旧值，于是必然报错，用户只能手动“重新预检”。
**修复：** 不同时把候选读取与预检一起重做一次（用新候选构造 `selected`），仍不同再报错；加一条模拟用例（候选读取后集合变化）。

### B5 用例的区分力与 §16.9 的单测

| 项 | 问题 |
| --- | --- |
| V3 | 只检查文字，不检查色调；P2b（“已接受”改用成功色）全部通过 |
| V4 | 撤销后的预检桩仍返回已接受数据，界面从未显示“已撤销接受，需要重新处理”；“确认归档禁用”在未勾选选择确认时本来就成立，断言无区分力；没有 `REVOKED` 模拟数据 |
| V9 | 没有断言全过程没有 `GET .../review`；模拟 Review 的 `review_version` 按 §5.3 与候选相同，因此 P5a（改读 Review GET）通过（见 D1）；只有一次 201，没有 200 回放（首次关闭人与当前身份不同）；404、422 的提示与“`REVIEW_VERSION_CONFLICT` 后再次打开取新值”没有走到；没有 4096/4097 字节的多字节边界 |
| V2 | 没有“各自撤销”，没有 ② 的接受请求及其 `subject_digest`/`expected_sequence`；“已接受”的定位没有限定在 ① 卡 |
| V1 | 只断言九类问题文字，不断言 §16.3 的详情文字 |
| V8 | 配置了开始归档 409 `ARCHIVE_PENDING_REVIEW` 但没有触发，提示未断言；点击名字后只断言对话框关闭，没有断言树中选中 |
| V13 | §16.9 末段的 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 提示没有用例 |
| 单测 | §16.9 要求的“问题文字与详情的映射、状态标签、`action` 映射、理由字节计数”没有单测（相关函数是组件内私有函数）；“只取 `ACCEPTED`”的单测数据全部是 `ACCEPTED`，无法证明过滤 |
| §16.8 | 见 §3.4 |

**修复：** 把映射与计数函数移到 view-model 并补单测；按上表补断言与模拟数据（含 `REVOKED`、200 回放、无 Review GET）。

### B6 t1 的输入核对与 §8.3 记录

- §8.1：“每次运行前重新核对清单与 SHA256（不把旧存在性当作实时证明）”。脚本只检查结构并打印两个文件的 SHA256，不与 FE3a 的 `SHA256SUMS-t1-v*.txt` 比较（§10：输入核对不符即停止）。
- §8.3：`baseline_to_initial` 的 `table_count`“记录实际值”，未记录。
- `compositeChanged` 取不到 `composite_signal_point` 时返回 `null`，随后按 0 计入预期；应失败。
- **修复：** 脚本在启动 Compose 前按清单逐文件核对并记录清单文件 SHA256，不符以非 0 退出；case log 记录 `baseline_to_initial.table_count`；取不到派生表状态即失败。

### B7 §9 的截图缺口

handoff §8.2 自报的缺口中，以下是 §9 明确要交 owner 看图的：时间倒退卡与“最后一个不是最大值”卡；“确认归档”的各种禁用原因（预检中、阻断、未处理、未知编码、未勾选）；审核顶栏的终局处置在真实 backend 下的参考截图（J1/J2 已有树与详情面板的截图，缺审核顶栏）。
**修复：** 在模拟用例中补拍前两类（1280、1920）；J1/J2 补拍 D1–D3 的审核顶栏参考截图。

### B8 handoff 与实际不符

- §4.3“J2 step 4 … 同 key 重放 201→200”、§5.1 V9“200 回放显示首次关闭人”：都没有走到 200（B1、B5）。
- §6.4“`UploadStepCard.tsx` 的 diff 只是开始按钮的占用原因禁用/提示”：该文件在 `fe-fe3b-exit..09351e42ad` 中没有改动（那是相对 `fd9e383d76` 的 FE3b 差异）；结论“没有改打包代码”成立。
- §10 第 7 项把 `test.pmc` 为 0 字节列为偏差：开发主机原件 `small_cut-1/2` 中的 `test.pmc` 本身就是 0 字节（2026-09-27），t1 输入就是用户的原目录，不是偏差。
- §6.5“t1 截图在 `fe3c-05/evidence/`”与 §6.1 命令中的 `--evidence-dir /home/dev/gdds-fe-evidence-05/fe3c-t1-r2` 不一致（后者只有空的 `test-results`）：说明截图实际写入位置的原因。
- §2 写“6 个 `docs/frontend-vnext/` 路径”指代码候选；含 handoff 为 7 个。
- **修复：** 修复轮的 handoff 改正上述各处。

## 5. 非阻塞

- **N1** `validate-upload-package.sh` 默认 `lock-d054366c02fa`，与当前树的 `--print-input` 不符，本轮靠环境变量覆盖。建议改为按 `--print-input` 取 tag；不改时，04 取证必须显式设置 `GATEWAY_BACKEND_DEPS_IMAGE=gateway-backend-deps:lock-578e079b762e` 并记录。
- **N2** §16.7：过期通过后只重读 review，没有重读 History；V12 重读后的模拟数据仍无处置，没有断言“按 §6.4 显示”。
- **N3** 来源详情的摘要前 12 位没有悬停全文；理由没有超过 3 行折叠；原始码（`issue_code`、`subject_digest` 等）没有放进悬停提示（C6）。
- **N4** J1 第 8、10、11、13 步与 J2 第 1、7、8 步的接受用 API 助手（自己拼 `selected`）完成，界面上的接受只在 J1 第 3 步走了一次真实 backend；J1 第 14 步由提交人而非审核人做历史比较。可在修复中顺手改用界面，不强制。
- **N5** `collectionNotice` 在同一对话框会话中不清除，后续成功操作后仍显示旧提示。
- **N6** M1 的两次测量在同一浏览器实例中（§3.5）；handoff 应注明 FULL 数值因此偏低、不可与 MODIFIED_ONLY 比较。
- **N7** 本地 main 已前进到 `2d8b29d332`：§13.5 明确“不合入其后的 main”，FE3c 不需要重新合并；FE3 退出合入 main 时再处理。不是设计问题。

## 6. 交设计会话

- **D1** §16.9 V9 写“模拟数据按 §5.3 使该值与 Review、工作区、基线的版本号都不同”，而 §5.3 规定候选的 `review_version` **等于**同一提交 Review GET 的值（两者同源，后端可达）。两条不能同时满足；实现按 §5.3。审核意见：保留 §5.3，V9 对“改读 Review”的区分力改由“全过程没有 `GET .../review`”的断言提供（B5 已要求）；请设计会话改正 §16.9 的措辞。不阻塞修复轮。
- **D2** §8.4 要求每次测量启动新浏览器，FE3c 又要求“在 t1 旅程中”复测、每个场景一次。t1 只作回归对照，是否要求 FULL 在新浏览器中测量，请设计会话决定；不阻塞。
- **Q21（后端已答，`p6-fe3-q21-answer` 分支 `d3450675bf`，未推送）：** 三个旧码（`COMPARISON_MODE_NOT_DETAILED`、`ORDER_KEY_UNSUPPORTED`、`ROW_IDENTITY_UNSUPPORTED`）已无产生点，前端可删除文案；四个新码若触发，转为表级 `DEGRADED` 诊断写入 surface。FE3c 不处理，列入 FE4 带入项，由设计会话决定删除旧文案与是否给新码补文案。

## 7. 代码质量与是否需要重写

不需要重写。`selected` 构造、关闭快照、逐项接受与“只刷新不重发”的结构清楚，探针表明主要不变量（两侧独立、不合并、引用完整、两键）都有用例守护。
问题集中在三处：文案与 kickoff 的逐条对照不够细（B3）；真实旅程中最关键的两点（同 key 回放、关闭后已接受项失效）用例走了捷径（B1）；部分 V 用例只验证“能走通”，没有区分力（B5）。
`ArchiveMainlineDialog.tsx` 已近 700 行，修复 B5 时把映射、计数与禁用原因移到 view-model，既便于单测也减小组件。

## 8. 下一步

1. 实施会话按 B1–B8 定向修复，提交修复候选与 `fe3c-handoff-fix1.md`；07 上 `run-tests.sh --e2e --screenshots`、05 上 `--suite journeys`（完整集）各一次调试运行；t1 只在 B6 改动后于 05 跑一次 `--suite t1` 调试。SHA 用脚本逐个回源。
2. 审核会话做定向复审（`fe3c-rereview-1.md`），重跑 P2b、P5a、J2b 三个探针确认已被拦住。
3. 复审通过后再指明 04 取证与 05 的 t1 证据运行。
4. D1、D2 交设计会话；Q21 结果列入 FE4 带入项。
