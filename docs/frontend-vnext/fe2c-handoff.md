# FE2c 定向修复 handoff（第 2 轮）— N1–N9 / M1、M8–M10

- 候选提交：`943feb20fa77a90ac2f407698330d919538a526f`，`frontend/` tree `0f15710a954bea1834b6117ade36ba754048c03c`。
- 复审范围：`680b643f39d9c83f85c8496627be03c4894c26cf..<本 handoff 提交>`；05 detached worktree `/home/dev/gdds-fe-fix2-72a4011d-05`，运行和 handoff 前均为已提交 clean 状态。
- 依据：`docs/frontend-vnext/reviews/fe2c-rereview-1.md`（N1–N9、M1–M10）、`docs/frontend-vnext/reviews/fe2c-review.md`（B1–B11）、`docs/frontend-vnext/fe2-kickoff.md` §7.1/§7.5（Q16、Q17）、AGENTS“前端测试（FD7）”。
- 05 完整 runner：exit 0，130 unit tests + 30 e2e，95 张截图；后端上传包校验脚本：exit 0，4/4 package 符合预期。04 取证待复审通过后一次运行。
- bundle：`/home/dev/gdds-test-tmp/fe2c-fix2-943feb20.bundle`，SHA256 `1daf3c947d08eaedc224a5df552095b3e9300659dcea053f2809b513eecd302a`。

## 1. 05 提交清单

`git log --oneline 680b643f..HEAD`（39 行；包含 main 合入的 docs 提交）：

```text
943feb20fa test(frontend): guard the entry limit before packaging (M1)
b5a8e795d1 test(frontend): cover the explicit empty-baseline upload state (N8)
eb76ec0c00 test(frontend): use the recorded requests in the retry test
a5a2843742 test(frontend): wait for the workbench before upload retry
abd16b37d0 test(frontend): cover upload failure and retry (N9)
cd38fdffa3 fix(frontend): serialize inert as an empty attribute for React 18
dd19d0bef5 fix(frontend): lock keyboard focus to the upload overlay (M10)
daee3017d1 test(frontend): record member sizes in the upload manifest
e59ae70b32 fix(frontend): compare upload members with backend-normalized paths
e59f22b285 fix(frontend): expose workspace packages to the upload validator
ce1fd53eae fix(frontend): expose operation failure to the resuming page
a0202dbe7d fix(frontend): keep the page locked while a refreshed preview settles
0ecdb2766f test(frontend): expect the shared permission copy
175a28094c test(frontend): restore desktop viewport before upload retry
4afd6b975d test(frontend): capture the missing FE2c error and dialog screenshots
31f635b277 test(frontend): match upload conflict copy and running stage
cf19346db5 test(frontend): open the detail panel before driving upload
d994d5cc32 test(frontend): follow submit result screen and upload card markup
6a93562a02 test(frontend): align journey expectations with per-action keys
f87f1e3df3 test(frontend): drop unused archive audit URL variable
658b41893d fix(frontend): type request validator and archive dialog error path
72a4011d83 fix(frontend): FE2c round-2 write-step keys, reachable states and error surfaces
8da5cc235c docs(frontend-vnext): design FE2c round-2 write-step keys and resume
31bff353b0 Merge main 7d9521d04b into fe-vnext (FE2c fix round 2 base)
7d9521d04b docs(frontend-vnext): define FE2c rereview-1 minor items M8-M10
9c58f6ff57 docs(frontend-vnext): FE2c rereview-1 (targeted fixes)
b7794f5bb4 docs(frontend-vnext): plan FE3 upload-mode withdraw after DC75
680f9a60f0 docs(p6): record BE-a kickoff review and clarify replay test owners
fcbfb4c1a0 docs(p6): review BE-a kickoff scope expansion
f20f08bea9 docs(p6): define BE-a workspace pointers and self-withdraw permission
d0a8143d80 docs(p6): approve corrected H2 launch commands for owner release
f8d4a3c354 docs(p6): record pending corrected launcher review
55e6c0083c docs(frontend-vnext): record FE2c review decisions Q16, Q17
a5ddaf14b7 docs(p6): review H2 launcher stop and recovery prerequisites
7c5cc2a49e docs(p6): review S2a final runner and parser evidence
dc6d1fbb2a docs(p6): prepare S2b inputs and BE-a BE-d kickoff drafts
ebb0047383 docs(p6): record DC73 backend design/review session split and handoff
4ea3099478 docs(frontend-vnext): FE2c review (targeted fixes)
c9f8dca39f docs(p6): review baseline W4 v2 preview KEY_EMPTY stop
```

## 2. 逐项对照

| ID | 提交 | 测试 / 用例 | 截图 | 状态 |
| --- | --- | --- | --- | --- |
| N1 归档每条确认/异常/开始各用 key，重试不重发 | `72a4011d`、`6a93562a` | `journeys.test.ts`：`gives each anomaly resolution its own key and expected sequence`、`resumes archive retries after a failed start without resending audit events`；探针：改回共用 key 后首条失败 | `archive-mainline-*` | 完成 |
| N2（Q17）上传包后端校验 + 请求侧约束一处实现 | `72a4011d`、`e59f22b2`、`e59ae70b`、`daee3017` | `frontend/scripts/validate-upload-package.sh`（4 包：with/without logics、missing dbcfg → `UPLOAD_CLOSURE_INVALID`、>100B 路径；成员路径/摘要比较）；`mock-data.test.ts`：`enforces the request-side constraints for every write route in one place (Q17)`；e2e 桩统一调用 `validateSimulatedRequest`，内联 422 检查已删除 | 脚本日志（§3） | 完成 |
| N3 确认后预检可达状态 | `72a4011d`、`6a93562a` | `mock-data.test.ts`：`keeps the needs-confirmation archive plan within backend preview rules (B3 probe target)`、`keeps every archive preview state consistent with the Q17 start rules`；探针：`confirmation_requirements=[]` 后两条失败 | `archive-mainline-*` | 完成 |
| N4 刷新恢复锁定、Preview 续接、提交结果、管理员信息、URL 清理 | `a0202dbe`、`ce1fd53e`、`dd19d0be` | e2e：`FE2c 执行中刷新后恢复页面锁定并继续到差异浏览`、`FE2c 提交对话框显示需要管理员处理并可跟随到成功` | `upload-locked-*`、`manual-recovery-required-*`、`submit-manual-recovery-*`、`submit-result-*` | 完成 |
| N5 上传续做 | `72a4011d` | e2e：`FE2c 提交超时重试复用同一幂等键并回放同一提交`、`FE2c 审核 403、版本冲突与超时重试复用同一幂等键`；探针：Preview 失败后单次重试成功且 upload 仅一次 | — | 完成 |
| N6 错误码就地显示/复制、审核刷新、生产构建可见 | `72a4011d`、`4afd6b97` | e2e：上传 403/版本冲突、审核 403/版本冲突、归档 403/审计冲突、提交 ABORTED；`check:production-build` 要求产物含“错误代码：/复制错误代码/操作 ID” | `upload-version-conflict-*`、`upload-permission-denied-*`、`review-version-conflict-*`、`review-permission-denied-*`、`submit-aborted-*`、`archive-audit-conflict-*`、`archive-permission-denied-*` | 完成 |
| N7 写操作场景补全 | `72a4011d` | e2e：`FE2c 提交被中止时显示原始错误代码`、`FE2c 归档 403、审计冲突与阻断项`、上传/审核 403 与版本冲突；`WORKBENCH_WRITE_SCENARIOS`/`WRITE_SCENARIO_COVERAGE` 集中声明来源；审核 token 为审核人、归档 token 为归档人 | `archive-blocked-*`、`submit-aborted-*`、`review-permission-denied-*` | 完成 |
| N8 阶段名、空基线禁用、摘要/目录卡二选一 | `943feb20`、`b5a8e795` | e2e：`FE2c 首批空基线禁用原始组态备份`、`FE2c 上传步骤卡校验目录并锁定页面`（MODIFIED_ONLY 显示“解析预览”） | `upload-empty-baseline-*`、`upload-running-modified-only-*` | 完成 |
| N9 截图补齐 | `4afd6b97`、`175a2809`、`b5a8e795` | 95 png，1280/1920 双宽度 | 目录见 §5 | 完成 |
| M1 条目上限在打包前检查 | `943feb20` | `upload-package.test.ts`：`rejects an over-limit directory before packaging` | — | 完成 |
| M8 fixture 修正与断言 | `72a4011d` | `mock-data.test.ts`：确认事件仅含确认；`TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION` 名称与内容一致；B3 断言按 subject/digest | — | 完成 |
| M9 工具栏上传 e2e | `4afd6b97` | e2e：`FE2c 上传步骤卡校验目录并锁定页面` 由顶栏“上传”按钮发起 | `upload-empty-*`、`upload-selected-*`、`upload-locked-*` | 完成 |
| M10 锁定区域 inert | `dd19d0be`、`cd38fdff` | e2e：`FE2c 执行中刷新后恢复页面锁定并继续到差异浏览` 断言 `.workspace-topbar`/`.workspace-layout` 的 `inert` 为 true | `upload-locked-*` | 完成 |

## 3. 05 运行清单

全部在 `gw-dms-test-05.lan` 的已提交 clean worktree 运行；日志目录 `/home/dev/gdds-fe-logs/fe2c/fix-2`。

| HEAD | 开始（UTC） | exit | 日志 | SHA256 |
| --- | --- | --- | --- | --- |
| `72a4011d` | 2026-11-04T10:22:11Z | 2 | `frontend-tests-20261104T102211Z.log` | `e44f319daaca8d43300e07a35093aec708c6f55f57b2ee6942e39376b3f990cd` |
| `658b4189` | 2026-11-04T10:23:19Z | 1 | `frontend-tests-20261104T102319Z.log` | `d3c103699f1ac85194e6611ad792bc9150a4be4b2072bf941ee6339a1295f259` |
| `f87f1e3d` | 2026-11-04T10:24:11Z | 1 | `frontend-tests-20261104T102411Z.log` | `e8f3ed4dff76021594f04997fc0a5bd899c8dba0c65bfc18e1dd05429d40eb7b` |
| `6a93562a` | 2026-11-04T10:25:18Z | 0 | `frontend-tests-20261104T102518Z.log` | `db1783ef9abd84243b5d1080e81ffec8bc5f66d6e842dd04f6f000bd36dece14` |
| `6a93562a` | 2026-11-04T10:26:04Z | 1 | `frontend-tests-20261104T102604Z.log` | `7ba272902a2272a73faf730b013101e725ba0e6f65916754a4c1355bd05ab712` |
| `d994d5cc` | 2026-11-04T10:27:52Z | 1 | `frontend-tests-20261104T102752Z.log` | `5451f21e587014a171e418b145fe2c2157ca71bea1800352d8a72b6f4b4cdd1d` |
| `cf19346d` | 2026-11-04T10:29:34Z | 1 | `frontend-tests-20261104T102934Z.log` | `774030015b030fe07fafbd368c8d4235874024f41e729d824a7b36978840218e` |
| `31f635b2` | 2026-11-04T10:32:05Z | 1 | `frontend-tests-20261104T103205Z.log` | `6ddf6db9468febbaaea78849ae83d969f925097eb46a64ff3bd54ffe9ed32431` |
| `4afd6b97` | 2026-11-04T10:34:15Z | 1 | `frontend-tests-20261104T103415Z.log` | `871d69034c5f57db766c5339fe2706cb9e48762453489f1527bd4f7c541a7b44` |
| `175a2809` | 2026-11-04T10:35:50Z | 1 | `frontend-tests-20261104T103550Z.log` | `57cc935cbed2674f3b68143b5dc265fe853efd2cee2a1cd75078f2a396cc9ee0` |
| `0ecdb276` | 2026-11-04T10:37:39Z | 1 | `frontend-tests-20261104T103739Z.log` | `235c3d09cfd03fb8a71da9044be21defd76f02836e9ca1c70cba6e64dc263c4c` |
| `a0202dbe` | 2026-11-04T10:39:49Z | 2 | `frontend-tests-20261104T103949Z.log` | `7850f66d54c09077bb1abf1ed60871dd1ecc933804d621e06b2a115ff21edd6f` |
| `ce1fd53e` | 2026-11-04T10:40:54Z | 0 | `frontend-tests-20261104T104054Z.log` | `74c9483a0b1f230ffe95745db243e7497432986d6dede64f4b2bf5cd406c5f38` |
| `dd19d0be` | 2026-11-04T10:52:52Z | 1 | `frontend-tests-20261104T105252Z.log` | `cc4d325086dc3b14522a86754a7a688a93cb536442d407e8cfffa90ca84b7e6e` |
| `cd38fdff` | 2026-11-04T10:54:51Z | 0 | `frontend-tests-20261104T105451Z.log` | `c74cda21a768b1875d38a2b5d115e645713015daa0d503cb0f9a5dd44666cff3` |
| `abd16b37` | 2026-11-04T10:57:57Z | 1 | `frontend-tests-20261104T105757Z.log` | `00ad0c3267554863c4ac08b1e2ee82741fe6c63331e516c34fb28081b41d80e1` |
| `a5a28437` | 2026-11-04T10:59:57Z | 1 | `frontend-tests-20261104T105957Z.log` | `8aea34d2cb61f227eb1b82ebf80a1e5602a8b14c4c95c06a6574e67a3631f160` |
| `eb76ec0c` | 2026-11-04T11:01:57Z | 0 | `frontend-tests-20261104T110157Z.log` | `2ee03cfe6839fc03897416f972ecdd27e5e7b7af26eb3c77dfd0de967ffb635d` |
| `943feb20` | 2026-11-04T11:04:57Z | 0 | `frontend-tests-20261104T110457Z.log` | `b1bfb993049e5846ff14bbb07108b273576458f4caab12ddc62e772c9b8286b5` |

后端校验脚本运行：

| HEAD | 开始（UTC） | exit | 日志 | SHA256 |
| --- | --- | --- | --- | --- |
| `ce1fd53e` | 2026-11-04T10:41:58Z | 1（`ModuleNotFoundError`；初跑仅 stdout） | `upload-validator-ce1fd53e-recheck.log`（复核） | `310611b33f67c5a034a4b21b0b7221c35c06e83249d7561f914ddb1b56e49fa4` |
| `e59f22b2` | 2026-11-04T10:42:18Z | 1（3/4 成员比较失败；初跑仅 stdout） | `upload-validator-e59f22b2-recheck.log`（复核） | `2d4e9db84cc0faf77a5bf03891c88901f2b18d1431c14dd5d2b66c0f0f4e66aa` |
| `daee3017` | 2026-11-04T10:43:29Z | 0 | `upload-validator-daee3017.log` | `a3d5ff6a62aa377fcbe6c300dfd3b0fe989890c114a2d3864c901bb360c5bc07` |
| `cd38fdff` | 2026-11-04T10:55:56Z | 0 | `upload-validator-cd38fdff.log` | `4f823a977a5c36e103021d36565da2c3fa731728dfd0a87d4b3d2e408c5d6900` |
| `eb76ec0c` | 2026-11-04T11:02:58Z | 0 | `upload-validator-eb76ec0c.log` | `b9b44c77d9038f8ce23b8127129901f79b92c34437a70e396c06ff559fae6cfe` |
| `943feb20` | 2026-11-04T11:05:58Z | 0 | `upload-validator-943feb20.log` | `f7d401bf6d564d153dda410d7fc127b70cf73f8bdc453eb241607ed4a3e1e654` |

## 4. 探针

均在一次性的已提交 detached worktree `/home/dev/gdds-fe-probe-fix2-05`（基于 `daee3017`）中做完后删除；日志 `/home/dev/gdds-fe-logs/fe2c/probes`。

| 探针 | 做法 | 结果 | 日志 / SHA256 |
| --- | --- | --- | --- |
| N1 共用 key | `resolveAuditProgress` 的 key 固定为 `shared-key` | exit 1；`gives each anomaly resolution its own key and expected sequence` 失败 | `frontend-tests-20261104T104554Z.log` / `f35f26164c4900cf034a8bf8bb56565d4305db949d2614e8c174084cf3cf5dc2` |
| N3 空 requirements | `ARCHIVE_PLAN_READY.confirmation_requirements = []` | exit 1；B3 与 Q17 两条预检规则测试失败 | `frontend-tests-20261104T104641Z.log` / `cfdcdcf2e25c8a01fc94d552b41515232025c1e2277e30649bf291a05d992ab6` |
| N2 去掉一条请求侧检查 | 从 `REQUIRED_IDEMPOTENCY_KEY_ROUTES` 删除 submit-attempts | exit 1；Q17 路由逐条测试失败 | `frontend-tests-20261104T104739Z.log` / `06a5668da0f5b65463b5821ce75c353e1920dd643402ad8f7dc0c0bf30a9068f` |
| N2 去掉 tar size 写入 | `writeOctal(header,124,12,0)` | 脚本 exit 1；3 个应接受的包被后端判 `UPLOAD_CLOSURE_INVALID` | `upload-validator-no-size.log` / `aa09a3fe6f397ca528945aec9dfe77fd53a34694419806c69c7e3da46d2b89d7` |
| N5 Preview 失败后重试 | 上传成功、`startPreview` 首次失败，第二次用同一 progress | 130 tests 通过；`uploadRevision` 仅 1 次、`startPreview` 2 次；先一次断言 `createWorkspace` 次数写错导致失败，修正后通过 | 失败 `...T104951Z.log` / `c2d714ec66040a5445fba9d94634043b65125637d319fc84a92c4a7a02efe9af`；通过 `...T105044Z.log` / `5229f33de89543af9ead893489e3b9a1c84386a22058e6d132288c47a005ba93` |

## 5. 截图

- 目录：`/home/dev/gdds-fe-evidence/fe2c/fix-2-943feb20-05/`，95 png；`sha256sum *.png | sort -k2 | sha256sum` = `f37e859849300ec9d0eb8a2f3dc1a304dacdf492dccb7bd73f2ee1bd96e9f720`。
- 本轮新增/重拍的状态（均 1280 与 1920）：`upload-version-conflict`、`upload-permission-denied`、`upload-empty`、`upload-empty-baseline`、`upload-failure-retry`、`upload-running-modified-only`、`review-permission-denied`、`review-version-conflict`、`review-reject-dialog`、`review-withdraw-dialog`、`submit-aborted`、`submit-manual-recovery`、`submit-result`、`archive-permission-denied`、`archive-audit-conflict`、`archive-blocked`、`archive-mainline`、`archive-mainline-result`、`upload-selected`、`upload-invalid`、`upload-locked`。
- 其余既有状态（`bundle-error`、`dataset-replacement-browse`、`formula-*`、`header-review`、`history-compare-*`、`loading-skeleton`、`manual-recovery-required`、`navigation-fallback`、`s1-workbench`、`s2-compare-tray`、`s3-*`、`s4-*`、`tab-overflow`、`workspace-error-no-connected`）同时覆盖 1280/1920。

## 6. 偏差

无。上传模式撤回按 Q16 决定不提供，不再列为偏差；M7（提交摘要原始 ID）不在本轮范围。

## 7. 复现与证据环境

- runner：`GATEWAY_FE_LOG_DIR=/home/dev/gdds-fe-logs/fe2c/fix-2 GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5 ./frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/fix-2-943feb20-05`
- 工具链：`mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:739bf253655693b5976ce9e90acb62a38bf813487d86ec1a591bb54a063000ac`，7 个 RootFS DiffID；`docker_network=none`；npm 缓存来源提交 `a2fb4a027a`，archive SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。
- 后端校验镜像：`gateway-backend-deps:lock-d054366c02fa`，config digest `sha256:d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff`；只读挂载源码、`network none`、`/build/backend/.venv/bin/python`。

## 8. 复审与 04 取证

- 复审范围：`680b643f39..<本 handoff 提交>`；05 worktree `/home/dev/gdds-fe-fix2-72a4011d-05`。
- 04 权威运行：待复审通过后在 `ct108-gw-dms-04` 的 clean、已提交 worktree 上完整运行一次；本轮未在 04 运行，也未在开发主机运行测试。

## 9. 写操作步骤与 key 规则（N1、N5 设计）

本轮先按本节实现，再改代码。key 只在当前页面/对话框的内存状态中保存，不写入 URL、`localStorage` 或 `sessionStorage`；刷新后只按 URL 中的 `operationId` 继续已受理的操作，未受理的步骤没有可续结果，按新意图重新开始，不重放旧 key（依据 kickoff §7.5 N2“`operation_id` 写入 URL，刷新后继续轮询”）。

| 步骤 | key 何时生成、何时复用、何时换新 | 重试从哪一步续做（已成功步骤使用的已知结果） | 依据 |
| --- | --- | --- | --- |
| 上传 `POST .../upload-revisions` | 用户点“上传并生成预览”时生成 `uploadKey`；同一次选择的重试复用它；目录选择改变、上传被 4xx 拒绝或刷新后重新开始时换新 | 上传成功后记录 `upload_revision_id`、`generation`、返回工作区的 `optimistic_version`；重试不再上传，直接从 Preview 续做。上传请求本身重放时必须仍发送首次的 `expected_workspace_version`（上传成功后工作区版本已前进，重发旧版本会与记录的指纹不符） | `application/workspace/services.py:86–151`（先按 key 查已有 revision，再比较 `compute_upload_request_fingerprint`，最后才做版本 CAS）；`application/workspace/contracts.py:86–111`（指纹含 `expected_workspace_version` 与各 artifact 的 `raw_sha256`） |
| Preview `POST .../preview-operations` | 与上传同时生成独立的 `previewKey`；同一次上传结果的重试复用；上传结果变化、刷新后重新开始或 Preview 返回 4xx 时换新 | Preview 受理后记录 `operation_id`，只轮询该操作；若受理响应丢失，用同一 `previewKey`、同一 upload revision、同一预期基线/版本重发，后端按已保存的 acceptance 回放同一个 `operation_id`，不产生第二次 Preview | `application/workspace/preview.py`（`deterministic_preview_operation_id` 与 `validate_start_preview_binding`：受理记录按 `(workspace_id, key)` 查找，指纹不符才报 `IDEMPOTENCY_CONFLICT`；回放返回先前 `operation_id`） |
| 提交 `POST .../submit-attempts` | 提交对话框打开时生成；同一提交意图的重试复用；终端 4xx（含工作区/基线版本冲突）换新，刷新事实后重新确认 | 受理后记录 `operation_id`，只轮询；操作成功后再取 `submit-attempts/{id}` 与 `submissions/{id}`。受理响应丢失时用同一 key 与同一请求体重发，返回第一次响应体；不重新上传或 Preview | kickoff §7.5“幂等回放”；`http/routes/submit_attempts.py` |
| 审核 `POST /v1/submissions/{id}/review-events` | 审核对话框打开时生成；同一 `expected_review_version` 与动作的重试复用；4xx（含 `REVIEW_VERSION_CONFLICT`）换新，界面刷新审核事实后重新确认 | 成功即结束；失败重试只重发同一动作与同一 `expected_review_version`。版本冲突后先重读 `GET .../review`，用新的 `review_version` 重新生成 key | `http/routes/reviews.py`、`http/orchestration/review.py`；kickoff §7.5 |
| 每条归档确认 `POST /v1/archive-confirmations` | 用户点“确认并开始归档”时，按 `subject_digest` 各生成一个 key 并记入对话框进度；该 subject 的重试复用；该 subject 的 `expected_sequence`、目标摘要或选择改变时换新，`ARCHIVE_AUDIT_VERSION_CONFLICT` 后刷新预检并换新 | 成功追加后记录该 subject 的 `sequence` 与事件 id；重试跳过已成功追加的记录，只处理剩余记录；开始归档请求使用已记录的 confirmation refs（`subject_digest` + `sequence`），不按新序号重发 | `infrastructure/control_db/schema.py:747–790`（`archive_confirmation_events` 的 `UNIQUE(repository_id, idempotency_key)` 与 `UNIQUE(repository_id, subject_digest, sequence)`）；`application/archive/audit.py:117–125`（按 key 查已有事件，指纹不符报冲突，否则回放）；`application/archive/contracts.py:271–311`（确认指纹含 `subject_digest`、`expected_sequence`、选择摘要等） |
| 每条异常处理 `POST /v1/archive-anomaly-resolutions` | 与确认同时、按异常的 `subject_digest` 各生成一个 key；重试复用；异常内容或 `expected_sequence` 改变时换新，冲突刷新后换新 | 成功追加后记录该异常的 `sequence` 与事件 id；重试跳过已成功记录，只处理剩余异常；开始归档请求使用已记录的 anomaly refs | `infrastructure/control_db/schema.py:793+`（`archive_anomaly_resolution_events` 同样两个 UNIQUE）；`application/archive/audit.py:238–246`；`application/archive/contracts.py:312–365` |
| 开始归档 `POST /v1/archives` | 所有确认与异常处理成功后、首次发“开始归档”时生成 `startKey`；同一次选择与同一组 refs 的重试复用；选择、候选摘要或 refs 改变时换新，刷新预检后换新 | 受理后记录 `operation_id`/归档结果；请求丢失时用同一 key 与同一组 refs 重发，后端按已保存计划回放。已成功的确认与异常处理不重发 | `application/archive/start.py:80–139`（按 key 查已保存计划，指纹不符报 `IDEMPOTENCY_CONFLICT`，匹配则回放）；`application/archive/contracts.py:367+`（开始指纹含 `candidate_set_digest`、选中集、排序后的 confirmation/anomaly refs） |

实现约定：

- 归档 journey 接受一个可变的进度对象（按 subject 的 key、已追加的 sequence、开始 key、开始结果），对话框在重试之间保留它；失败不会清空已成功的记录。
- 只有 `IDEMPOTENCY_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT` 或用户改变输入时，才丢弃对应步骤的 key 并刷新预检；网络错误、超时、5xx、429 一律保留 key 重试。
- 单元测试固定两条：两个异常各自使用自己的 key 与序号；开始归档失败后重试不重发确认/异常处理，并使用同一 `startKey`。
