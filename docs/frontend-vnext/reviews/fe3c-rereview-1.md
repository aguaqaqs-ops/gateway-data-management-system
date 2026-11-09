# FE3c 复审第 1 轮

- **审核对象：** 分支 `fe-vnext`，范围 `1df3dc05e2..031dc3d754`。
  - 代码候选 `cbb14f578cd22f37355db78a62ba9264f71477d3`，`frontend/` 树 `f626a8f0b3ab4ebd2a3e1d7a3eb15e1803c48908`；
  - handoff 提交 `031dc3d754e754feb22bba793324f3d53bd80825`（只新增 `docs/frontend-vnext/fe3c-handoff-fix1.md`，`frontend/` 树相同）。
- **依据：** [FE3c 审核](fe3c-review.md)（`ccd7b80fa2`）§4–§6；[FE3 kickoff](../fe3-kickoff.md)（main `1be218b6b5`，含 Q22、Q23 修订后的 §8.4、§16.9 V9）§16；fix1 handoff。
- **日期：** 2026-11-09。
- **结论：通过。** B1–B8 都已修复，没有新的阻塞项，可以进入 04 取证（§6）。
  - B1：J2 第 4 步先在界面接受 BTU，关闭请求用 `route.fetch()` 送到 backend 后再中断，同 key 重试得到 `201,200`。关闭人、时间、理由按响应体断言，归档确认人会话全程没有 `GET .../review`。探针 J2a（重试不带 key）、J2b（重试换新 key）都在第 4 步失败；
  - B2：8 次带 `selected` 的预检都比较两个集合，J1 第 7 步断言 B 的来源；
  - B3：阻断项、禁用原因、BTU 文字、关闭与接受的错误文案都与 §16.3–§16.6 一致，并有单测；
  - B4：两次读取的 digest 不一致时，候选读取与预检一起重做，新探针 P6（只重做预检）使 B4 用例失败；
  - B5：P2b（成功色）、P5a（改读 Review GET）现在都失败，P5a 失败在“没有 `GET .../review`”的断言上，符合 Q22 后的 V9；新探针 P7（撤销项不计入未处理）使 V2、V4 失败；
  - B6：t1 运行前逐文件核对 FE3a 清单，记录 `table_count`，派生表取不到即失败；
  - B7、B8 已补齐和改正；fix1 handoff 的 SHA 全部回源一致；
  - 新发现 4 项非阻塞（§5 M1–M4），不需要再修一轮。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse cbb14f578c:vnext`、`031dc3d754:vnext` | 都是 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`，与原候选相同 |
| `git diff --name-only fd9e383d76 031dc3d754` | 只含 `frontend/`（56 个）与 `docs/frontend-vnext/`（8 个） |
| `git diff --name-only 1df3dc05e2 cbb14f578c` | `frontend/` 下 11 个文件（+1075/−320），无其他路径 |
| `git log --merges 1df3dc05e2..031dc3d754` | 无合入 |
| 提交序列 | `f34f98df10`、`76603a77c7`、`9aadd8622e`、`396a983624`、`4905ebe916`、`741ad4bfba`、`cbb14f578c`、`031dc3d754`，与 handoff 开头的表一致 |
| `frontend/openapi.json`、`src/features/api/generated/` | 与 `09351e42ad` 相同（blob `5cb982793b`） |
| `features/upload/`、`UploadStepCard.tsx`、`package.json`、`package-lock.json` | 本轮无改动：不需要 t4 重测（Q20），npm 缓存不变 |

本轮改动：

| 内容 | 文件 |
| --- | --- |
| 映射、文案、禁用原因、错误文案移入 view-model，加 16 项单测 | `view-model/archive-dialog.ts`（新）、`archive-dialog.test.ts`（新） |
| 对话框只负责渲染；一次加载重做候选读取；关闭结果区加 `aria-label` | `ArchiveMainlineDialog.tsx` |
| 模拟数据：`REVOKED`、两侧各自接受/撤销、MODIFIED_ONLY、B4、V8 可开始的预检；§16.8 可达性单测 | `archive-validation-data.ts`、`.test.ts` |
| 模拟 e2e：V1–V4、V7–V10、V13 补断言，B4、B7 新用例 | `e2e/archive-validation.spec.ts` |
| “只取 ACCEPTED”单测加入未处理项 | `api/journeys.test.ts` |
| 真实旅程：J1/J2 两组集合、J1 第 7 步来源、J2 第 4 步、D1–D3 顶栏截图 | `e2e-real/journeys.spec.ts` |
| t1：清单核对；`table_count`；派生表缺失即失败 | `scripts/run-real-backend-e2e.sh`、`e2e-real/t1.spec.ts` |
| N1：默认依赖镜像按 `--print-input` 取 tag | `scripts/validate-upload-package.sh` |

## 2. 独立运行与探针

我在开发主机建了 `refs/review/fe3c-rr1/candidate`（`cbb14f578c`）与 `refs/review/fe3c-rr1/handoff`（`031dc3d754`），打成 git bundle（`1df3dc05e2..031dc3d754`，SHA256 `fd343d5a9ff75ac23c8f18870183325888b75fc1d164c346b0fab2a95b4ab6a9`），在 07、05 上校验后 fetch，随即删除 bundle。两节点都在 detached worktree `/home/dev/gdds-fe3c-rereview1-run` 上运行，起止 HEAD 都是 `cbb14f578c`，`frontend/` 树起止都是 `f626a8f0b3`，`git status --porcelain --untracked-files=all` 起止都为空。日志目录 `/home/dev/gdds-fe-logs/fe3c-rereview-1/`。

运行前 07、05 都没有占用标记。05 的真实 backend 运行由脚本自行取得、释放标记，每次结束 `cleanup_status=ok`，没有残留容器。

### 2.1 独立运行

| 节点 | 运行 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 07（`gw-dms-07`） | `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2`，17:19:54–17:22:29Z | exit 0：单测 34 个文件 207 项，Playwright 86 项；截图 190 张，目录 `/home/dev/gdds-fe-shots/fe3c-rereview1-cbb14f57`，清单 `shots.sha256` 为 `c44f4f723ff1da776627f1bb4bd1d6ba62bd8ebc2ced2e47efc91fd20ffcf36a`；工具链 config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017` | 入口 `cd1bb585265f55cfbdb51a2ec147bc1c4e331f75ec14971a81148357236c994b`；外层 `4d2f78543b27b33063e1c5bb6f74c0c70ccdf338c357d712d27be444aa3d5a62` |
| 05（`gw-dms-test-05`） | `run-real-backend-e2e.sh --suite journeys --subphase fe3c --session fe3c-rereview-1`，npm 缓存两变量指向 `/home/dev/gdds-fe-cache/fe0/`，17:19:54–17:27:34Z | exit 0：20 passed；`openapi_compare=match`；RS config digest `sha256:60bcfe0f470396d1c626a2c3d402fdaa2cd10e87870a0af273615db167d3902d`；`j2-step4 … statuses=201,200`，两次请求 key 相同；case log 中 8 行同时记录 `anomalies` 与 `business_issues` | 入口 `5a6b3777cc2127f18a2c49dc41f0773cb1ae14fc70a6269cbb11e4512bc13cf8`；外层 `85f5cfe490912b7918fea88d7c134623ee3b4f00bed728a66aad36a3f6aa0141`；case log `2fe39ce2a537d33f540de34d7b23fe5bf1cab6cf522dfdd53878dc469d82d58c` |
| 05 | `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，17:46:42–17:50:47Z | exit 0：1 passed；两份清单 SHA256 与 FE3a 一致、各 19 个文件 `sha256sum -c` 通过；`baseline_to_initial.table_count=125`，`composite_changed=0`；M1 见 §3 B6 | 入口 `b39d969b5686176c9ce6bfeb5318a792f7b21a0663068febcd3ca094dd5198ab`；外层 `99268aaf90162a86acec3ddd0b0318c3cf8bec6676836c10e561e685b40b2e3f`；case log `6f5eb9a2d452fec451f026933d0589727fa6e3762e537c2c174da774591e297f` |
| 05 | `validate-upload-package.sh`，**不设** `GATEWAY_BACKEND_DEPS_IMAGE`，17:50:47–17:52:04Z | exit 0：默认解析为 `gateway-backend-deps:lock-578e079b762e`（N1 已修） | 入口 `d302115f71409a083326751934ee23ce79083184fef4cef68ba007b51098d825`；外层 `a2ffb7f8b153579814160ba13ac83fb147abf451ca281d9167744ef3cd161b03` |

### 2.2 探针（已提交的一次性 worktree，只在节点上）

| 探针 | 提交 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| P2b：“已接受”标签改用成功色（07） | `14a8ce8468` | V3 失败 | **符合**：只有 V3 失败，失败在 `toHaveClass(/status-tag--neutral/)`（收到 `status-tag--success`） | `1d28c565e6e43973ae5767dbbcc79ef2dc1c2d3d6eadb6c170b5c3fb32872e62` |
| P5a：关闭的 `expected_review_version` 改读 Review GET（07） | `db2191f894` | V9 失败，且失败在“没有 `GET .../review`” | **符合**：V9 第一条失败在 `expect(reviewGets).toBe(0)`（收到 1）；“版本冲突后重新打开”一条也失败 | `a3c255b98c18819411e6b8c3b58b028f3730cc6aa43cdd8778f4c32dd4bb8cd5` |
| P6：一次加载不一致时只重做预检，沿用旧候选读取（07，新） | `1a743a9fff` | B4 用例失败 | **符合**：只有 B4 失败（显示“归档候选集合已变化”，预检状态节不出现） | `fb3056a5bfa3fa9750ea799dc71e86af1774fcd6b53e7efc45c2af2c833da790` |
| P7：`REVOKED` 不计入未处理（07，新） | `812ff9b34d` | V2、V4 失败 | **符合**：V2、V4 都失败在“确认归档”应禁用处 | `da9e5f643a1d26c8ad56bb51bb6b1e3f2fedd066788471b2646d5cc9e3dd28a9` |
| J2a：关闭重试不带 `Idempotency-Key`（05） | `610b5015bb` | J2 第 4 步失败 | **符合**：backend 对重试返回 422，界面显示“理由或请求不符合要求”，第 4 步在 `closeResult` 处失败；静态影响说明不再能满足断言；其余 19 项通过 | 外层 `c330a524407c4ee5da71a6e3ce4e4583fdf1ea28bdb3a958ad36cddeb265b32e`；入口 `a153a367d5774814dc7924126bec037b3b564927f265b6b1d7382a721f3a9c26` |
| J2b：关闭重试换新 key（05） | `37cca7884e` | J2 第 4 步失败 | **符合**：backend 对新 key 返回 409 `ARCHIVE_CLOSED`，对话框按 §16.6 关闭并提示“该提交已归档或关闭”，第 4 步失败；其余 19 项通过 | 外层 `8fe974ed61440e5883ff025320fbac8623613680229b2e1eddd3b3d6fa3f33ee`；入口 `57815444af0a84b5ebe8180e1ebda6d50f31cc8b766d9a69cf8f2b48a7219c67` |

07 探针只运行 `e2e/archive-validation.spec.ts`（21 项），方法与审核报告 §2.3 相同。各探针的 diff 存于 07 的 `probes/*.diff` 与 05 的 `j2*.diff`。探针 worktree 与 `refs/review/fe3c-rr1/probe-*` 都已删除。

## 3. 逐项核对

### B1 J2 第 4 步：符合

- 关闭前在界面展开“基线时间”并接受 BTU，断言卡片从“未处理”变为“已接受”。
- 路由处理器每次都先 `route.fetch()`，第一次拿到响应后 `abort`，第二次 `fulfill` backend 的回放。断言两次请求的 key 与 body 都相同，状态码为 `[201, 200]`，响应体 `closed_by` 等于归档确认人 `actor_id`，结果区（`aria-label="关闭结果"`）按响应体显示关闭人、UTC 时间与理由。
- 归档确认人会话从打开起监听 `GET /v1/submissions/{id}/review`，第 4 步断言为 0。这是 Q22 后 V9 在真实 backend 上的覆盖。
- 第 5 步先重新读取候选再预检，断言 7 项都是 `UNRESOLVED`，且原 BTU 的 `subject_digest` 不再出现。
- 我的运行：`statuses=201,200`。J2a、J2b 都在第 4 步失败（§2.2），审核报告中 J2b 全部通过的缺口已关闭。

### B2 两组集合：符合

- `businessIssueSet` 带受影响提交（排序后拼接），`expectAnomalySets` 对每次带 `selected` 的预检比较两个集合，并写入 case log。期望表从同一张 kickoff 表去掉同级、身份两类得到。
- 覆盖 J1 第 2/7/11/13 步与 J2 第 1/3/5/8 步：我的 case log 中有 8 行 `business_issues=`，都与期望一致。
- J1 第 7 步断言 B 的来源为 `EXPLAINED`，`matching_sources` 含 `BASELINE`。

### B3 文案：符合

逐项对照 §16.3–§16.6：

| 位置 | 现状 |
| --- | --- |
| 阻断项 | `ACTIVE_SUBMIT_ATTEMPT`、`ARCHIVE_INTEGRITY_FAILURE` 显示 kickoff 文字，其他显示“当前不能归档”；原始码只在“错误代码：`<code title>`”中。V7 断言中文文字，原始码限定在 `.archive-blockers code` |
| 禁用原因 | 正在预检 → 预检失败 → 阻断 → 未知编码 → 未处理/已撤销（“还有 {n} 项异常未处理”）→ 未勾选 → 归档中。§16.5 把未知编码与未处理并列在第 3 条，实现先判未知编码，符合 |
| BTU | 问题文字完整；详情与 `GENERATION_TIME_MISSING` 共用计数文字，为空时“基线没有生成时间记录”，随后“比较结果：无法比较” |
| 关闭错误 | 404 →“未找到该提交，请重新预检”；`ARCHIVE_CLOSED` →“该提交已归档或关闭”（首次与重试一致）；413/429/503 与其他码 →“关闭未完成”加错误码，不取服务器 message |
| 接受/撤销错误 | 其他码 →“操作未完成”加错误码 |

单测覆盖以上映射。另见 M1：为了让冲突提示在重新加载后不被覆盖，实现引入了 `pendingNotice`，带来一个新的小问题。

### B4 一次加载：符合

两次读取的 `candidate_set_digest` 不同时，`load()` 重读候选，用新候选重建 `selected` 再预检一次；仍不同才报错。新用例断言候选请求 2 次、预检 2 次，第二次预检的 `selected.expected_candidate_digest` 为新值。探针 P6 证明用例能区分“只重做预检”。

### B5 用例区分力与单测：符合

- V3：断言中性色调，P2b 失败。
- V4：撤销后的预检返回 `REVOKED`，界面显示“已撤销接受，需要重新处理”与撤销理由。先勾选选择确认再断言禁用，并断言“还有 2 项异常未处理”；请求为 `REVOKE`、`expected_sequence=3`。P7 失败。
- V9（按 Q22 后的措辞）拆成五条：
  - 中断后同 key 重试，回放 200 显示首次关闭人 `reviewer`（当前身份 `archive-confirmer`），全程 `reviewGets=0`；
  - `REVIEW_VERSION_CONFLICT` 后重新打开，取新加载的 `review_version=22`；
  - 404、422 的文案；
  - 403、413 的文案；
  - `"多"×1365+"x"` 为 4096 字节时可用，4097 字节时禁用。

  P5a 失败在“没有 `GET .../review`”上，符合 V9 末句“只能由这条断言区分”。
- V2：两卡各自接受、各自撤销，四个请求的 `action`、`subject_digest`、`expected_sequence`、`reason` 逐项断言；“已接受”限定在卡内。
- V1：补了 BTU 全文、基线无记录与无效值计数的详情；V8 触发 409 并断言组态树选中行；V13 补 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`。
- 单测：映射、状态色调、`action`、字节计数、禁用原因顺序、阻断与错误文案共 16 项。“只取 ACCEPTED”的数据含未处理项。§16.8 可达性单测覆盖 `ACCEPTED`/`REVOKED` 字段组合、MODIFIED_ONLY 与 8N+1。详情映射的单测没有覆盖全部类型，见 M3。

### B6 t1：符合

- 脚本在启动 Compose 前按版本比较清单文件 SHA256（硬编码 FE3a 值，不符 exit 2），再在版本目录内 `sha256sum -c`，失败时经 `pipefail` 非 0 退出。
- 我的运行记录：清单 `cdb598cd…0163`、`fa2450fa…a96a`，各 19 个文件通过。
- `baseline_to_initial.table_count=125` 已写入 case log；`compositeChanged` 为 null 时断言失败。
- M1（Q23）：第 1 步 MODIFIED_ONLY 的 `renderer_increment_bytes=22093824`（21.07 MiB），FE3a 为 24.86 MiB，比值 0.848，低于 2 倍。第 4 步 FULL `2068480` 字节，只报告：与第 1 步同一浏览器实例，增量偏低，不可比较，不作基线。fix1 handoff §10 第 2、6 项已注明，符合 Q23。

### B7 截图：符合

- 模拟截图在 1280、1920 下都有：时间倒退卡（①②同屏）、LAST_NOT_MAX 卡、“确认归档”的五种禁用原因（预检中、阻断、未处理、未知编码、未勾选）、关闭结果。
- 真实 backend 的 D1–D3 审核顶栏参考截图在 J1/J2 中补拍（1920）。

我看过其中几张，布局与层级符合 §16.2。交 owner 看图时一并看 M2。

### B8 handoff 更正：符合

fix1 handoff §8 逐条改正：200 回放、`UploadStepCard.tsx`、`test.pmc`、t1 截图位置、§2 路径计数，都与审核报告一致。

### fix1 handoff 的 SHA 回源核对

用脚本对 handoff 中每个十六进制值逐个回源（来源：07、05 上 `fe3c-fix1-*` 目录全部文件的现场 `sha256sum`、日志文本、05 的 `docker image inspect`、git 对象）：

- 201 个值全部命中来源；长度都在 7–12、40、64 之内，没有异常长度。
- 路径与 SHA 配对 33 处全部正确：模拟截图 8 行 16 个（按 `screenshots/<宽度>/<名称>.png`）、真实 backend 截图 3 个（在 `fe3c-fix1-05-r4` 中）、4 条最终运行日志、2 个 case log、8 条调试运行日志（日志所在目录的轮次与表中一致）。
- 7 个 DiffID 与 05 上工具链镜像一致（第 3 行为修正后的 64 位值），依赖镜像 ID、npm 缓存归档 SHA256 一致。

## 4. 节点与工作区

- reflog 检查：开发主机主 worktree 自 11-09 03:48Z 起无切换；S5 的 worktree（main，现为 `50047f1476`）只有 S6 的提交，状态 clean；07、05 主 worktree 只有 `refs/sync/main` 的快进。没有他人或共享 worktree 被切换。
- 实施会话在 07、05 留有 `/home/dev/gdds-test-tmp/wt/fe3c-*` worktree 与 `fe3c-fix1-*` 日志，我没有动。
- 04 当前没有占用标记；`gateway-backend-deps:lock-578e079b762e` 已在本机（ID `sha256:2d13e70a…dfbd`）；工具链镜像的 DiffID 列表与 05 相同；npm 缓存在默认路径。

## 5. 非阻塞

- **M1** `pendingNotice`（`ArchiveMainlineDialog.tsx:142`、`:271`、`:301`）：关闭返回 409 后，冲突提示存入 `pendingNotice`，下一次加载若候选集合变化，就用它**替代**“候选集合已变化，之前的接受不再适用，请重新核对”（§16.4 要求的提示）。若集合没变，`pendingNotice` 不清除，之后同一对话框会话中真正的集合变化会显示过时的冲突文字。两种情况都只在并发或冲突时出现，卡片本身的处理状态仍正确。与审核报告 N5（`collectionNotice` 不清除）属同一机制，建议 FE4 把“冲突提示”与“集合变化提示”分成两处显示，并在每次加载后清除待用提示。
- **M2** 关闭对话框正文写成“关闭提交提交 2（不归档）。”（`:522`，`"关闭提交" + displayName`），显示名本身已带“提交”。该行在原候选中已存在，首轮审核漏看。另外关闭成功后“确认关闭”仍可点击；同 key 再点只会得到回放 200，不造成重复关闭。两处都交 owner 看图时判断，或列入 FE4。
- **M3** 详情映射单测覆盖了 BTU、`GENERATION_TIME_MISSING`、`TIME_ABNORMAL_MODIFIED`（基线一侧）与同级排除。`INITIAL_SOURCE_UNEXPLAINED`、`GENERATION_TIME_LAST_NOT_MAX`、`TIME_ABNORMAL_INITIAL` 与 ② 早于 ① 的详情只由截图与部分 e2e 覆盖。可在 FE4 补齐。
- **M4** fix1 handoff §10 第 1、2 项仍写“设计会话尚未修正”“由设计会话决定”。Q22、Q23 已于 2026-11-09 确认并在 main `1be218b6b5` 落地，实现与新措辞一致（V9 由“没有 `GET .../review`”区分；t1 FULL 只报告）。证据 handoff 应按新措辞引用，不改 fix1。
- 审核报告的 N2、N3、N4、N5、N7 未改，继续列为非阻塞，进入 FE4 带入项。N4 中 J2 第 4 步已改走界面。N6 已在 fix1 handoff 注明；证据 handoff 对 t1 FULL 作同样注明。
- 真实 backend 的 D1–D3 参考截图只有 1920；同一画面的模拟截图有两种宽度。可以接受。

## 6. 下一步：04 取证与 05 t1 证据（给实施会话的提示词）

> 你是 FE3c 实施会话。FE3c 复审第 1 轮通过（`docs/frontend-vnext/reviews/fe3c-rereview-1.md`，main 上的本地提交）。请在 `fe-vnext` 的 `031dc3d754`（代码 `cbb14f578c`，`frontend/` 树 `f626a8f0b3`）上做 FE3c 证据运行，不改代码。
>
> 1. **04（`ct108-gw-dms-04`）**：
>    - 用 git bundle 把 `031dc3d754` 送到 04，在新的 clean detached worktree 中运行（建 `legacy` 符号链接）。
>    - 每次运行前确认 04 没有他人的有效占用标记；若标记用途为计时测量，等待释放。
>    - 默认 npm 缓存；设 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`。
>    - 以下各运行一次：
>      - `frontend/scripts/run-tests.sh --e2e --screenshots <04 证据目录>`；
>      - `frontend/scripts/validate-upload-package.sh --output … --log-dir …`（不设 `GATEWAY_BACKEND_DEPS_IMAGE`，记录日志中解析出的 `lock-578e079b762e`）；
>      - `frontend/scripts/run-real-backend-e2e.sh --suite journeys --subphase fe3c`（脚本自取占用标记，外层不要先取）。
> 2. **05（`ct108-gw-dms-05`）**：
>    - 同一提交运行 `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs` 一次。
>    - 设 `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`、`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`。
> 3. **每次运行记录：**
>    - hostname、起止时间、起止 HEAD 与 `frontend/` 树、起止 `git status --porcelain --untracked-files=all`；
>    - 入口 exit code、入口日志与外层日志的 SHA256；
>    - 工具链镜像 config digest 与 7 个 DiffID；RS config digest；`openapi_compare`、`cleanup_status`；
>    - 截图目录与 `shots.sha256` 清单的 SHA256。
>
>    t1 另记两份清单核对行、`table_count`、`composite_changed` 与两次 M1：第 1 步与 FE3a 24.86 MiB 对照；第 4 步 FULL 按 §8.4（Q23）注明“同一浏览器实例，增量偏低，不可比较，不作基线”。
> 4. **失败处理：** 任一运行失败先停下。按 DC68 判断能否重做一次（未触及被测对象的自身操作错误），不能则交审核会话。
> 5. **证据 handoff：**
>    - 新增 `docs/frontend-vnext/fe3c-evidence-04.md`，作为 `031dc3d754` 之上单独的 docs-only 提交，不改其他文件。
>    - 引用 Q22、Q23 后的 kickoff 措辞，写明 fix1 handoff §10 第 1、2 项已由 main `1be218b6b5` 处理。
>    - 列出非阻塞项去向（审核报告 N2–N5、N7；本报告 M1–M4，进入 FE4 带入项）。
> 6. **提交前 SHA 核对：** 用脚本把文中每个十六进制值与来源（节点上现场 `sha256sum`、日志、`docker image inspect`、git 对象）逐个对照，路径与 SHA 逐行配对，并报告长度不是 7–12、40、64 的值；核对结果写进 handoff。
> 7. **范围限制：** 不合入 main、不 rebase、不推送；运行结束后删除 04 上的传输 bundle。

证据运行后由审核会话写 `fe3c-evidence-check-1.md`，再交 owner 看 §16 与 §9 的截图（含 M2），之后按 kickoff 进入 FE3 退出。

## 7. 保留与清理

- 保留到证据核对：
  - 07、05 的 `/home/dev/gdds-fe3c-rereview1-run` 与 `refs/review/fe3c-rr1/{candidate,handoff}`；
  - 开发主机上的同名 refs；
  - 07、05 的 `/home/dev/gdds-fe-logs/fe3c-rereview-1/`；
  - 07 的截图目录 `/home/dev/gdds-fe-shots/fe3c-rereview1-cbb14f57`。
- 首轮审核的 `/home/dev/gdds-fe3c-review-run`、`refs/review/fe3c-r/*` 与日志也保留，到 FE3 退出清理时一并处理。
- 已删除：探针 worktree、`refs/review/fe3c-rr1/probe-*`、开发主机与节点上的传输 bundle。
