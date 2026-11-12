# FE4b 摘要

FE4b 完成业务导航、行定位与 BE-b 消费者判据，并把 fe-handoff 的设备目录会话合入前端。

- 最终候选 `cafd65a0fa`（`fe-vnext`）；`HEAD:frontend` = `f8962e9bdbea63f43fab4db274f0dbeb9826b101`，`HEAD:vnext` = `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`。
- 修复 `duplicates-orphans` 截图冻结：1280 视口下侧栏默认收起使导航项不可见；`expandNavigation()` 在打开预览/项/页签前展开侧栏；同一提交修正 `openTab` 选择器，并让 `freezeColumns` 包含元列后的 pinned 业务列。
- 新增 `frontend/e2e-real/lib/consumer-criteria.ts`：按 kickoff §5.3 对每个下载 bundle 断言导航形状、未记录表、按侧覆盖与行定位；journeys 与 t1 全部接线，报告逐 surface 页签数、`TABLE_FALLBACK` 数、定位表/行数。
- 合入 fe-handoff（`e225b63224`），新增 `fe4b-preview-topbar-device`，设备栏与「返回目录」在比较页可见。
- R10–R16（一句话）：R10 同侧 parquet footer 严格解码整数/字符串标量（规范十进制加 BigInt 与声明位宽/符号/safe 核对，字符串原值比较，矛盾即解码错误）；R11 三条解码不变量（suppressed 为零、记录数相符、locator 一一对应）只对 exactTable 执行，另加复用正例与反向用例；R12 六个反例由生成 fixture 变异覆盖；R13 抽取 F6 helper 加单测、F7/F8 加 e2e 断言、orphans 视图改无条件可见、筛选页签加 scope 标记产品改动；R14 fe-handoff 用例旧 pair 改名并断言；R15 用 ResizeObserver 实测顶栏高度写入 CSS 变量覆盖 8 处 100px，侧栏遮挡降为 0；R16 删除 `.compare-status` 换行并加 W6 忙态溢出断言；R9 加 `.compare-header` 双截图字节相同稳定门（根因未查明）。

四项证据（候选 `cafd65a0fa`；证据 handoff `fe4b/handoffs/fe4b-evidence-cafd65a0fa-handoff.md`；核对报告 `fe4b/reviews/fe4b-final-evidence-cafd65a0fa.md`；证据副本 `fe4b/evidence/fe4b-evidence-cafd65a0fa/`）：

- 04 mock 全量通过：vitest 41 文件 323 项、e2e 108 项、截图 250 张。日志 `/home/dev/gdds-fe-logs/fe4b-evidence-cafd65a0-04/`（wrapper 与 entry），截图 `/home/dev/gdds-fe-evidence-04/fe4b-cafd65a0fa/shots`。
- 04 上传包校验通过：`packages=4 failures=0`。日志同上目录，产物 `/home/dev/gdds-fe-evidence-04/fe4b-cafd65a0fa/validate-output`。
- 04 journeys 19/20：`r10-archive` 失败见下，其余通过，OpenAPI 比对一致。日志同上目录（含 Compose 日志与 `artifacts/journeys-r10-archive/trace.zip`），`evidence` 落 `/home/dev/gdds-fe-evidence-04/fe4b-cafd65a0fa/journeys`。
- 05 t1 通过：判据行、表数与异常均符合预期。日志 `/home/dev/gdds-fe-logs/fe4b-evidence-cafd65a0-05/`（含 Compose 日志），`evidence` 落 `/home/dev/gdds-fe-evidence-05/fe4b-cafd65a0fa/t1`。

journeys `r10-archive`：e2e 轮询单次 `503 SERVICE_NOT_READY: deployment storage unavailable`，该操作 worker 无异常。已知后端缺陷（`2faac9fc` 中 `check_database_files` 旁路文件竞态，经 API 503 表现；main `bd1f3c171c` 已修），按 owner 2026-11-12 决定接受；FE4b 前端连修复后后端的回归，在 FE4 退出合并后的验证中进行（原定 S2b E 前端审核，S2b 已于 2026-11-12 退出）。

第 ③ 次比较按 owner 决定接受（`fe3b-w6-withdraw-busy`，R9 同类）。

t1 M1：第 1 步 MODIFIED_ONLY renderer 增量 20619264 字节（19.66 MiB；FE3a 24.86 MiB、FE4a 18.41 MiB，上限 49.72 MiB，未超）。

待 owner 确认的偏差：`fe4b-columns-pinned`（pinned 且中文名无单一 fixture，分开覆盖）；t1 导航诊断只复现 `APP_TABLE_NOT_FOUND`；t1 `located-rows-1280` 表格主体空白（`baseline_to_initial-1280` 正常，1920 正常）；D1a 对齐（顶端对齐与否）、D1b 原因换行（220px 处折出“新上传”）；`NO_CANONICAL_CHANGE` 标为可重试。详见看图材料 `fe4b/reviews/fe4b-final-viewing-cafd65a0fa.md` §3–§6。
