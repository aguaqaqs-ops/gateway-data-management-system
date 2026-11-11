# FE4b 摘要

FE4b 完成业务导航、行定位与 BE-b 消费者判据，并把 fe-handoff 的设备目录会话合入前端。

- 候选 `fcf4268c1a531a8f44fe04038668ab475507acb5`，前端树
  `f3f1fdf1238346f3ed561cd80d6799c4dc64f4a2`，`vnext` 树
  `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`；相对 `fe4b-base`（`3e5f24583d`）
  39 个提交、615 个文件，仅 `frontend/` 与 `docs/`（fe-handoff 另带入一份设备目录 handoff 报告）。
- 修复 `duplicates-orphans` 截图冻结：1280 视口下侧栏默认收起使导航项不可见；
  `expandNavigation()` 在打开预览/项/页签前展开侧栏。同一提交修正 `openTab` 选择器，
  并让 `freezeColumns` 包含元列后的 pinned 业务列。
- 新增 `frontend/e2e-real/lib/consumer-criteria.ts`：按 kickoff §5.3 对每个下载 bundle 断言
  导航形状、未引用表、按侧覆盖与行定位；journeys 与 t1 全部接线，报告逐 surface 的页签数、
  `TABLE_FALLBACK` 数、定位表/行数。
- 合入 fe-handoff（`e225b63224`），新增 `fe4b-preview-topbar-device`，设备栏与「返回目录」在
  比较页可见。
- 截图：mock 19 名 ×2 宽（38 张）；t1 13 名 ×2 宽 + 4 张沿用（30 张）。
- 最终候选证据（同一提交）：07 mock ×2（252 vitest + 106 Playwright）、04 mock（106）、
  04 journeys 20/20、04 上传校验 4/0、05 t1 1/1。全部 exit 0，日志与 SHA256 见
  `fe4b-handoff.md` §5。
- t1 M1：`t1-v1-modified` 19.39 MiB，低于 FE3a 24.86 MiB 的 2× 上限。
- 偏差：`fe4b-no-canonical-change` 在 mock 与 t1 最短旅程中都不可达；`fe4b-columns-pinned`
  的「pinned + 中文显示名」无单一 fixture，当前分开覆盖；均待 owner 确认。详见
  `fe4b-handoff.md` §7。
