# 前端专项整顿总结（中期合入后）

- **范围与基线：** 从 `main` 中期出口 `gw08-midterm-exit`（`B′ = d7b54533f0`）切出 `fe-remediation` 分支重做，冻结候选 `C = fda178f502`（未改动 `vnext/`；`B′..C` 共 16 个线性提交，仅 `devDependencies` 新增 `prettier@3.9.10`）。
- **验证：** 第 9 步独立审核、F5–F7 定向复审及第 10 步 `04`/`05` 退出证据核对全部通过（E1–E3 与 F1–F3 已由 Owner 确认并修订计划 §11.4，候选代码无须修复；`04` mock/上传包逐字节/`smoke`/`journeys`、 `05` `t1`、全目录凭据检索、截断 hex 回源全部合格）。**未测限制：** `cfgtest` 没有在改动后的入口上运行（Owner 2026-11-17 决定不加验证）。证据与审核原件见阶段交换区 `evidence/post-midterm/` 与 `reviews/`（`handoffs/` 含三份交接与更正）。

## 做了什么

- **H4（Prettier）：** 引入 `prettier@3.9.10`（`.prettierrc.json`、`.prettierignore`、`format` / `format:check`），`FormulaCard` 标题保持三子节点不用 `prettier-ignore`，全 `frontend/` 格式化至幂等并通过入口检查。
- **H1（分层门禁）：** 在 `frontend/eslint.config.js` 落地三条 `no-restricted-imports` 规则（含单测，A 层测试仅例外允许 `features/dev`），迁出 `ConnectionStatusIndicator.tsx` 及单测至 `features/workbench/` 并新增 13 项 `layering-rules.test.ts` 验证正/反例。
- **H2（`ComparisonPage.tsx` 机械拆分）：** 拆出 11 个纯展示与纯辅助模块至 `src/pages/comparison/`，同步收窄 `e2e/` 与 `e2e-real/` 的 `tsconfig.json` `exclude`。
- **H3（三个组件抽 hook）：** `ComparisonPage` 抽 13 个 hook、`WorkbenchPage` 抽 7 个 hook、`ArchiveMainlineDialog` 取用 6 个 hook 调用，三组件体内 `useState`/`useReducer`/`useEffect`/`useLayoutEffect` 计数均为 0，仅保留两处计划允许的 effect 换序并保持无 JSX 非 DOM ref 读写。
- **G1（按输入角色推导视图文案）：** `viewLabel`/`viewTitle` 在 `PREVIEW` 与 `REVIEW` 均按 `(before, current)` 角色推导并删除 `pair_id` 子串匹配与 `total` 参数，附 11 项参数化 `view-copy.test.ts`。
- **O1（`loadTable` 纯函数接线与敏感探针）：** 拆出 `checkTableRowLocations`、`decodeTableEncodings`、`assembleTableRows` 三段纯函数至 `features/view-model/table-assembly.ts` 并加 4 项 `table-assembly.test.ts` 用例，R10d 与 R11f 探针均击中预期失败。
- **O2 / O4（静态确认）：** 确认 `DerivedTable.tableScope` 死代码（O2）与 `.compare-status` 过时 N5 注释（O4）均已于中期清理，仅保留有消费者的 `NavigationTableNotice.table_scope`，本轮未再改动。
- **R9 / T4（无滚动稳定门）：** `upload-mode.spec.ts` 与 `t1.spec.ts` 改为视口可见区域 clip 稳定门并记录 `scroll_before`/`scroll_after`，`styles.css` 修正 `.operation-status-card__heading strong` 半像素行高消除原生抖动。
- **T1（真实运行 trace 脱敏）：** `run-real-backend-e2e.sh` 结束后在 `set +e` 下调用只读标准库 `redact-entry-tokens.py` 对明文与 `trace.zip` 成员按值脱敏并记 `trace_redaction=ok|failed`。
- **T3（复用日志目录前置拒绝）：** `run-real-backend-e2e.sh` 在取得节点占用之前核查 11 项固定名输出，存在任一项即列出并以 `2` 退出。
- **T5（凭据检索）：** 新增只读标准库 `scan-credentials.py`，单一正则覆盖四类 token，先逐份自检 6 份样本再递归扫描明文与 zip 成员。
- **T6（截断 hex 回源）：** 更新 `check-handoff-hex.py` 校验 `<hex>…<hex>` 截断形式（前后缀各不少于 4 位且唯一匹配已知完整值），对三份交接与审核报告全部回源通过。

## 与设计的偏差

1. **R9 最小产品样式修复（Owner 2026-11-17T09:43–09:45Z 授权）：** 在 `frontend/src/styles.css` 的 `.operation-status-card__heading strong` 增加一行 `line-height: 20px;`（本轮唯一产品样式改动，解决卡片 `71.5px` 半像素高度引起的 1px 垂直跳变），导致 5 个 `.operation-status-card` 场景共 10 张截图（1280/1920）卡片高 `71.5px→72px` 且下方整体下移 `0.5px`（计划 §11.4 第 2 条）。
2. **G1 截图例外由 4 张扩为 6 张（Owner 2026-11-18 确认，F1）：** `schema-keyless` 用例另包含 `f-search-nonempty-count` 的 1920 与 1280 两张截图，6 张允许差异均严格限于顶栏面包屑一行。
3. **T4 判据 ② 按 B′ 新顶栏改写（Owner 2026-11-18 确认，F3）：** 未带 pregate 的 `device-tabs`、`forward-channel` 顶部均匀行数为顶栏内边距 `5`（非 0），`t1` 样本数为 `shot-gate` 24 行、pregate 10 组、PNG 38 张（两处 `fe4-t1-nav-diagnostics` 按诊断数有条件跳过）。
4. **`smoke.spec.ts` `waitForOperation` 竞态修复 `9f2f1030c3`（Owner 2026-11-17T11:12:27Z 授权）：** 改为 Node 侧 `page.request.get` 并在导航销毁上下文时等待重试，原有断言未改。
5. **T1 故意失败 `smoke` 运行节点不同（F6）：** 临时失败 `smoke` 提交运行在 `04`，而非计划正文所写的 `05`；保留 `trace.zip` 逐成员脱敏检索已通过验证。
6. **第 10 步两项阈值边界抗锯齿噪声认定（Owner 2026-11-18 确认，E1、E2）：** `04` mock 的 `s3-workbench-upload-1920`、`s4-grid-main-1920`、`s4-grid-hover-1920`（各 112 像素、`<=2` 通道差、连通块 10，全在圆角与边线）按噪声处理，不改脚本阈值、不重跑；`05` `t1` 的 `fe4-t1-nav-groups-1280`、`fe4-t1-review-1280` 与 pregate 各差 57 像素 Canvas 网格线交点，按噪声处理且不加跑 `t1`。

## 遗留事项与未完成项

- **E3（`fe4-t1-columns` 落在空页签）：** 第 7、10 步 `t1` 均选中 `0→0` 行空表（来自中期合入后导航顺序变化，非本轮引入）；下一前端阶段将 `pickColumnsTab` 改为优先选有数据行的表并在该阶段 `t1` 中验证。
- **5 个 mock 覆盖缺口（第 9 步审核报告记录）：** `ComparisonPage` 表读取错误路径、`expandedRuns` 切换重置与未归属回退先后、`WorkbenchPage` Preview 续接失败解锁、无进行中提交时清除续接 ID、归档对话框再次打开时确认勾选重置。
- **F8（T1 脚本与计划文字差异）：** `redact-entry-tokens.py` 不处理 `gdds-handoff=` 载荷（当前 `e2e-real/` 无此路径且由事后 `scan-credentials.py` 兜底），待设计会话决定修改脚本或计划文字。
- **既有架构遗留（计划 §11.1）：** A 层目录中的 `SessionComponents.tsx` 与 `table-state.tsx` 组件待后续改动触及时再迁至 C 层。
- **退出合入后待办（路线 A / 计划 §9.1 方式 2）：** 退出合入 `main` 后，于短期分支按后端 `Sb` 执行 **G2** 刷新 `frontend/openapi.json` 与生成类型并单审合入（`M2`），随后在 `04` 基于 `M2`（含后端退出提交 `Sx`）补跑一次完整 `journeys` 与凭据检索并回执 `FE-SCHEMA-ACK`、`FE-JOURNEYS`。

## 门禁说明（交规则会话收录，源自计划 §12）

| 门禁 | 实际命令与触发点 | 失败处理 | 豁免与规则 |
| --- | --- | --- | --- |
| 前端格式检查 | `frontend/scripts/run-tests.sh` 在 `npm ci --offline` 之后执行 `npm run format:check`（`prettier --check .`，Prettier 3.9.10，配置 `frontend/.prettierrc.json`） | 列出未格式化文件并以非零退出，入口失败；须在开发 worktree 重复运行 `npm run format` 至无变化且 `npm run format:check` 通过后提交 | 仅限 `frontend/.prettierignore` 所列生成类型、测试夹具、OpenAPI 快照与 lockfile；禁止行内 `prettier-ignore` |
| 前端分层规则 | 同一入口接续执行 `npm run lint`（`eslint .`，三条 `no-restricted-imports` 规则定义于 `frontend/eslint.config.js`，由 `src/test/layering-rules.test.ts` 证明生效） | ESLint 报 `no-restricted-imports` 与层次约束说明并退出非零，入口失败 | 生产代码无豁免；A 层测试仅例外允许导入 `features/dev` |
