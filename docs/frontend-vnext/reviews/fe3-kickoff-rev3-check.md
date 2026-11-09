# FE3 kickoff 修订 3 与 FE3c 生产 OpenAPI 原件核对

- **日期：** 2026-11-09（开发主机只读核对；06 与 04、05、07 只读查看，约 06:40–06:50Z）。
- **会话：** 前端审核会话（不是前端设计会话，也不是后端会话）。
- **对象：**
  - kickoff 修订 3：分支 `fe3-kickoff-rev3` 的 `9fb8656282`（修订 3）与 `33e654d772`（记录 OpenAPI 原件），只改 `docs/frontend-vnext/fe3-kickoff.md`；
  - 后端补交的生产 OpenAPI 原件：`/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/`（`handoff.txt`、原件、日志与比对材料）。
- **依据：** owner 2026-11-09 的决定（Q15–Q20 按建议确认；FE3c 合入 main `fd9e383d76`）；[Q18 交接](../../backend-vnext/refactoring/formal/plans/p6-be-q18-handoff.md)；kickoff 修订 2 定向复核第 1 轮的 E1、R1。

## 0. 结论

| 对象 | 结论 |
| --- | --- |
| 生产 OpenAPI 原件 | **通过。** 取自 `vnext/` 树 `6368c9c40c` 的生产栈，原始字节、身份与差异均复核一致 |
| kickoff 修订 3 | **通过。** 两项 owner 决定已记录，§16.6 已定稿，`selected` 规则、模拟数据规则、V9 与 V14、镜像、停止条件、E1 与 R1 均已处理；所引源码位置与后端事实逐项核对无误。另有一处不阻塞的小问题 n1 |

FE3c 实施提示词的前置条件已全部满足，可以发出。本报告与修订 3 一起合入 main。

## 1. 生产 OpenAPI 原件

- **原件：** `production-openapi.json`，SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`。
  - 06 上的节点原件 `/home/dev/gdds-test-tmp/p6-openapi-6368c9c40c/runtime/production-openapi.json` 与开发主机副本 SHA256 相同；
  - 交付目录的 `SHA256SUMS`（81 项）用 `sha256sum -c` 全部通过；
  - 旧原件副本 `previous-production-openapi.json` 为 `977b2258…b8a7`，与 FE3b 所用原件相同。
- **取件：**
  - 日志 `node/run.log`（SHA256 `65052f8d…ff9e`，与 06 原件相同）记录了：hostname `gw-dms-06`；起止 HEAD `fd9e383d76`；起止树 `6368c9c40c`；生产栈 ready 后单次 `GET /openapi.json`；`capture_exit`、`entry_exit`、`exit_code` 均为 0；本次容器、卷、网络清零，`marker_release_exit=0`。
  - 06 现场：没有占用标记，没有运行中的容器；取件 worktree 仍在 `fd9e383d76`，是 detached 的，没有改动。
- **方法：** 与 BE-a/BE-d 相同，用生产 Compose helper 和 `httpx` 直接写入响应字节。省略了取件前的业务旅程，理由（schema 只由路由与 DTO 决定）成立。
  - 日志里出现的 `Bearer compose-submit-bearer` 是 harness 中固定的测试常量（`vnext/backend/tests/support/compose_gate_harness.py:649`），不是凭据。
- **差异：** 我按 kickoff §5.1 的规则独立规范化：新原件得 `4c2ddca7…620a`，旧原件得 `e26d9e14…574a`。两者只差两处：
  - `ArchiveCandidateResponse.properties.review_version`（整数，0–9007199254740991）；
  - `required` 中新增的 `review_version`。

  与后端交接和设计会话的核对一致。`fe-fe3b-exit` 的 `frontend/openapi.json` 规范化后也是 `e26d9e14…574a`。`ArchiveCandidatesResponse` 与 `PreviewArchivePlanResponse` 都有必填的 `candidate_set_digest`，§16.2 的“一次加载”规则可以实现。

## 2. kickoff 修订 3

**owner 决定：**
- 文首状态、§11、§12 记录了 Q15–Q20 于 2026-11-09 按建议确认；
- 文首起点、§2.1、§3.2、§13.5 写定合入 `fd9e383d76`，不合入其后含 S5 代码的 main；FE3c 期间重新合入时停下交审核会话重核。

**源码与事实核对：**

| 修订内容 | 核对 | 结论 |
| --- | --- | --- |
| §16.2 `selected` 的构造位置 | `ArchiveMainlineDialog.tsx:87` 为 `previewArchive({ selected: candidate })`，整个候选转发；`:133` 显式构造两个字段；`journeys.ts:423/436/462/478/487` 转发 `input.selected`（`:372` 类型为 `ArchiveSelectedRefRequest`）；`runArchiveJourney` 唯一的产品调用方是 `:132` | 一致 |
| §2.3 第 19 行、§5.3 | 后端 `ArchiveSelectedRefRequest` 为 `extra="forbid"`（`http/schemas/archive.py:99-103`）；`snapshot.py:122` 的 `review_version=projection.optimistic_version`；`manual_close.py:99-100` 比较版本并抛出 `ReviewVersionConflict`；`mock-data.ts:578` 与 `workspace-shell.spec.ts:426` 是现有的候选模拟数据 | 一致 |
| §16.6、V9、V14、§13.6 探针 | 取值来自同一次加载中目标候选的 `review_version`；409 后重新加载，再次打开时取新值；不读取 Review。V9 断言“没有 `GET .../review`”且取值有区分力；V14 断言四个请求的键集合；两个探针分别对应 V14 与 V9 | 一致，可测 |
| §2.3 末段：其余后端变化 | `56720104af..6368c9c40c`：`artifacts/`、`bundle_assembly/`、`domain/`、`http/errors.py`、`upload_limits.py` 没有改动；golden 只新增文件，没有修改；worker 内存默认值仍为 32 GiB 和 24 GiB（`settings.py` 与 `compose.yaml` 的默认值），只放宽了可设置的上限。三个旧诊断码在新树的 `backend/src` 与 `rust` 中已不再出现，四个新码出现 | 一致；Q21 交后端合理，不阻塞 |
| §4.3、§2.2 镜像 | `--print-input` 得 `lock-578e079b762e`（审核会话 2026-11-09 已在 `fd9e383d76` 上重算）；04、05 的 label 与 19 个 DiffID 相同；RS 依赖镜像仍为 `lock-6dc9659f0aee` | 一致 |
| R1（§16.5） | `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 只在 `snapshot.py:82/125/155` 的读取上限处抛出；`ARCHIVE_MAX_ANOMALY_REFS = 8 * ARCHIVE_MAX_CANDIDATES + 1`（`contracts.py:27`） | 一致 |
| E1（§5.5、§13.3） | 改为 9 个原件加 `SHA256SUMS` | 一致 |

**n1（不阻塞）：** §13.5 的“先读”只写了 §2.3 第 12–18 行，没有第 19 行和 §2.3 末段。审核会话在发出提示词时补上，不需要设计会话另行提交。

## 3. 合入与下一步

- 修订 3 分支基于当时的 main `3af4b920db`。审核会话在当前 main 上以 `--no-ff` 合入该分支，与本报告一起快进 main，不改写设计会话的提交。
- 节点占用（06:49Z）：04、05、07 都没有占用标记。
- 下一步：发出 FE3c 实施提示词，填入的值为：
  - 依赖镜像 `gateway-backend-deps:lock-578e079b762e`；
  - 原件 `/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`，SHA256 `ce58f20a…c079`；
  - kickoff 确认提交为本次合入后的 main。
