# P5-5D-S3 Closure Verification（round-3 修复核验）

日期：2026-09-22。结论：**round-3 修复全部实测通过；仅剩 1 项 provenance 绑定缺陷（V-1，P2）**。
V-1 是纯文档 + 一次提交即可修复；修复后可由独立 acceptance authority 签署
`p5_5d_s3_stage_exit: pass`（`delivery_recommendation: pass_recommended` 保持）。

绑定：`git HEAD = 3a78150ce54533c868e829908c1399475c59b7cf`（实现提交 `cf0d34cb9d`；
二者 `vnext/**` 内容相同，见 §0）。工作区有一处未提交修改，见 V-1。

本次为**只读复审**：未修改实现/handoff/authority，未提交、未部署、未产生 Repository effect。
取证过程运行了 E1/E2/E3/`-m unit`（E2 会构建镜像并起停容器，`down -v` 已清理），并使用 `/tmp`
下的临时探针脚本（未落入仓库）。

## 0. 本次实际运行

| 运行 | 结果 |
| --- | --- |
| E1 focused gate（六文件） | ✅ **136 passed, 1 warning, 7.43s**（与报告一致） |
| E2 conjunction（我自行 fresh build，project `gateway-p5-5d-s3-final-verify`，宿主 8000 空闲） | ✅ **6 passed, 0 skipped, 335.77s** |
| E3 五包 ruff + mypy | ✅ 全通过（421 / 198 / 26 / 15 / 34 files） |
| `-m unit` 全量回归 | ✅ **2355 passed, 163 deselected, 87.9s**（上轮基线 2350） |
| 中间件断连修复（单元级） | ✅ 假 `receive`（部分 body → `http.disconnect`）下 `receive()` **恰好调用 2 次**、线程正常退出（修前：每秒 470 万次、永不返回） |
| 中间件断连修复（端到端） | ✅ 真实 uvicorn + 裸 socket 中断 `POST /v1/archives` 后 `/healthz` **0.001s 仍 200**（修前：3s 超时、`SERVER STALLED`） |
| 镜像内容 == HEAD 源树 | ✅ `sha256:51ef519dd6a8…` 内 `/app/backend/src` 摘要 = 本地 `12ecd51e624f23f56bba048044cd6424018d716a13569f227b9abce6f74324e0` |
| Source-tree digest 复算 | ✅ `6006d443268f51a6474cca28357da0dd81e8c4a2ddebe73f86e1d17293def985`（905 文件，统一 `path\tsha256` recipe）；在 `cf0d34cb9d` 及两个 amend 变体上亦相同 |
| 运行中容器 provenance | ✅ `vnext/backend/tests/support/.last_compose_gate_provenance.json` 含 container ID + `sha256:` 不可变镜像 ID + project name |

## 1. 逐条核验（round-3 报告条目）

| 条目 | 结论 | 我的核验方式 |
| --- | --- | --- |
| R-1 断连死循环 | ✅ 关闭 | `dependencies.py` 仅 `continue`→`return` 一行；上述两项探针实测；新用例 `test_archive_body_middleware_returns_on_client_disconnect` 用线程 + 5s join 断言，结构性可失败（修前线程不退出） |
| R1（R-4.4）Start 跨 actor 重放 | ✅ 关闭 | `test_archive_cross_actor_start_idempotency_replay_preserves_accepted_by`：第二 actor 同 key/body → 200、plan/result id 一致、`archived_by` 保持 `actor-1`；对照的 confirmation 跨 actor 仍 409 `IDEMPOTENCY_CONFLICT` |
| R2 scope limit HTTP | ✅ 关闭 | `seed_bulk_approved_archive_candidates(count=201)` → `GET /v1/archive-candidates` 409 + `code`，且断言响应无 `candidates` 键 |
| R3 非 string 边界 | ✅ 关闭 | `ARCHIVE_HTTP_NON_STRING_FIELD_CASES`（`reason: 5`、`expected_sequence: "0"`）同表内 DTO `ValidationError` + HTTP 422 |
| R7 七响应泄漏扫描 | ✅ 关闭 | `test_archive_responses_do_not_leak_internal_fields` 现覆盖 candidates/preview/confirm/resolve/audit/start/result 七个体 |
| R5 immutable 容器 ID | ✅ 关闭（且加强） | harness 改为 `docker inspect --format {{.Image}}`，非 `sha256:` 直接 fail；新增 `assert_running_backend_worker_images_match_build`（container inspect vs 构建 tag inspect，非自证式断言）；产物落盘固定路径并打印 |
| R4/R8 provenance | ✅ 关闭 | 记录值在本候选复现（§0）；recipe 统一为 `path\tsha256`；旧值标注 Superseded；容器 ID/镜像 ID 直接写入 handoff 表 |
| R6 `app.py` 路径 | ✅ 关闭 | handoff 已改为 `vnext/backend/src/gateway_backend/app.py` |
| R9 countersign 命名 | ✅ 关闭 | 改为 `delivery_recommendation: pass_recommended` + `review: pending`；`p5_5d_s3_stage_exit: not_evaluated` |
| Plan 残留（上轮 R-3） | ✅ 关闭 | plan §1 与 §4 S3 段均更新为 "re-review remediation complete / 136 passed / conjunction"；`next_step: P5-5D-S3-re-review`；S4 明确以签署为前置 |
| 容器门禁口径 | ✅ 记录完整 | `container_rebuild_required: yes`（T0 src 改动）、`prebuilt_used: no`；我的独立复跑为 fresh build 且 6/6 通过 |

## 2. 余留 finding

### V-1（P2，阻断签署）handoff 记录的候选 HEAD 是悬空提交，且该修改未提交

证据：

- `git status` → `M docs/backend-vnext/refactoring/formal/plans/p5-5d-s3-handoff.md`（未提交）。
- 已提交版本记 `implementation_candidate_head` / `Git HEAD` = `b9924be4da075fd99bd18d67f5e9fe50314151d5`；
  未提交修改把两处改为 `c7c7aa921fa5405c54b0a9094e6ccff41b5a7425`。
- `git merge-base --is-ancestor`：两者对 HEAD 均为 **no**；reflog 显示 amend 链
  `b9924be4 → c7c7aa92 → 3a78150ce5`。即 handoff 记录的是**被 amend 掉的提交**，历史中不存在。

影响：§6.3 要求"完整 Git HEAD"且候选不得有未记录差异；当前记录无法绑定到任何存在的提交，工作区也不干净。
`vnext/**` 内容本身是明确的（摘要 `6006d443…` 在 amend 链上与 HEAD 一致），因此这是记录缺陷而非内容缺陷。

修复（纯文档 + 一次提交）：

1. 把 `implementation_candidate_head` / `Git HEAD` 改为**在历史中**的 `cf0d34cb9d`（实现提交），
   并注明 `3a78150ce5` 为 docs-only 提交、二者 `vnext/**` 摘要同为 `6006d443…`（本报告 §0 已给证据）；
   或直接沿用 `introduced_by_this_commit` 写法并附实现提交 SHA。
2. 提交这次 handoff 修改；提交后不要再尝试"记录包含本文件的 HEAD"——amend 链永远不自洽。
3. 由于仅 docs/** 变化，`vnext/**` 摘要与镜像 `51ef519d…`/`6e88dd57…` 不变，本次 E1/E2/E3 证据继续有效，
   **无需重建或重跑**；若后续任何修复触及 `vnext/**`，则必须重算摘要并重跑三套门禁。

### V-2…V-5（P3，可随同一次提交处理）

- **V-2**：`.gitignore` 新增一行（`vnext/backend/tests/support/.last_compose_gate_provenance.json`）不在 S3
  预算清单内，handoff 的 Scope delivered 未列明；补一行说明（该文件为测试产物，已 gitignore）。
- **V-3**：上轮 R-4.2 未加强——"技术 main 在后提交者"仍只断言
  `main_after_both != initial_commit_id`；如需与 Plan §4 措辞完全对齐，可断言 main == 后提交者的
  submission commit。
- **V-4**：中间件短路响应仍不带既有 envelope 的 `details`（上轮 G 项）；补 `details` 或记为已知差异。
- **V-5 更正说明（关于我上轮结论）**：round-2 handoff 的 `a963b15a…` 确实与提交内容不符——
  `git archive 2233e80cc1` 复算为 `9ed8121a…`，与我当时测量一致，故上轮 R-2.1/R4 成立；
  本轮 `6006d443…` 正确复现。本轮我最初测得的 `9512d3eb…` 是交付方仍在编辑工作树时的瞬时状态，
  非缺陷，特此更正。

## 3. 签署建议

1. 完成 V-1（必须）+ V-2/V-3/V-4（处理或记录）后提交。
2. 由独立 acceptance authority 签署 `p5_5d_s3_stage_exit: pass`；交付方保持
   `delivery_recommendation: pass_recommended`，不得自签。
3. 签署记录中绑定：`cf0d34cb9d`（实现）与 docs 提交 SHA、source-tree digest `6006d443…`、
   backend src `12ecd51e…`、镜像 `51ef519dd6a8…` / `6e88dd57d583…` / `70c25d76bb1a…`、
   E1 136 / E2 6 passed 0 skipped / E3 / `-m unit` 2355。
4. S4 仍须按计划对最终候选执行 fresh-build 全量 conjunction，不得沿用本阶段镜像。

本次仅新增本报告，不代签 handoff，不修复实现，不执行 commit、部署或 Repository effect。
