# Composite Signal Device Execution Plan

本文记录复合信号虚装置能力的分段实施、验证和完成状态。正式合同见 `../capabilities/composite-signal-device.md`。

## 执行阶段

### 1. 文档与合同

- [x] 固化 source、AST、Snapshot/Dolt 表、diff、risk、projection、bundle 和 frontend 合同。
- [x] 同步 SourcePackage、Snapshot、business projection、risk、bundle 与 flows 总文档。

### 2. XML source、parser 与派生表

- [x] 可选 XML `SourceDocumentRef` 与 EMPTY source。
- [x] 受限流式 parser、canonical AST/digest 和失败矩阵。
- [x] 特殊装置/测点绑定与 `composite_signal_point` SnapshotTable。
- [x] parser/materializer unit tests 与 large fixture oracle。

阶段 2 通过后可在同一上下文合并执行阶段 3。

### 3. Snapshot、正式流程与 Dolt

- [x] 组合 SQL 与 composite table 后统一重建 Snapshot/Summary/TableSet digest。
- [x] 接入 formal upload、submit finalization、repository import/readback 和 history compare。
- [x] 验证 XML-only change 改变业务 Snapshot identity。

### 4. Comparison、Risk 与 Business Projection

- [x] 注册 `ALL_CHANGES` 表规则及字段忽略规则。
- [x] 单表级 UNKNOWN risk annotation。
- [x] 生成 points/formulas supplemental artifacts。
- [x] 特殊 item 排序、普通 65532 item 剔除、状态与风险合并。

阶段 4 bundle fixture 固定后可在同一上下文合并执行阶段 5。

### 5. Bundle 与 Frontend

- [x] upload preview/history bundle closure 收录 supplemental artifacts。
- [x] frontend contract/read model 与特殊 points loader。
- [x] 公式入口和 COMPARE/BEFORE/CURRENT 完整展开业务公式。
- [x] 合成公式列紧跟测点描述并共同冻结；特殊 tab 复用普通二次装置业务顺序。
- [x] formulas artifact v2 携带 side-local `dev_addr → description`，前端仅名称化展示且保持原始公式比较语义。
- [x] 命名嵌套表达式使用分组标题与逐行操作数，公式正文升级为 13px 中文无衬线排版，并使用有序锚点稳定对齐。

### 6. 集成与收尾

- [x] backend vNext unit/integration/Dolt journeys。
- [x] frontend test/typecheck/build。
- [x] large fixture 性能与 bundle size 记录。
- [x] 回填本文件验证结果和最终版本。

## 暂停条件

- 派生表无法通过通用 repository import/readback 无损恢复。
- supplemental artifact 无法进入 bundle closure 或 ref/digest 无法闭合。
- XML parser 需要放宽已确认的业务不变量才能接受正式 fixture。
- 实现引入 devices × formulas 或 devices × rows 的交叉扫描。

## 验证命令

```bash
gateway-data-management-system/backend/.venv/bin/pytest \
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_composite_signal.py -q

gateway-data-management-system/backend/.venv/bin/pytest \
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_business_projection_capability.py \
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_flow.py \
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_history_compare_flow.py -q

cd gateway-data-management-system/frontend
npm test
npm run typecheck
npm run build
```

## 完成记录

完成日期：2026-07-18。

- source/parser：正式流程支持可选 XML、EMPTY marker、受限流式解析及组合 identity；large fixture oracle 为 431 个公式、435 个特殊测点、4 个合法无公式测点。
- Snapshot/Dolt：新增 `composite_signal_point` 与通用组合最终化；专门的 repository-ref readback 回归测试验证 canonical payload、AST 和 digest 可无损恢复。
- comparison/risk/projection：表规则升至 `backend-vnext/table-ruleset/v2`，二次装置 projection 升至 v2；公式变化映射为“合成公式”字段 UPDATE，派生变化只产生单个 UNKNOWN。
- bundle/frontend：upload preview、history comparison 和 Dataset Replacement 均携带 pair-local supplemental artifacts；前端支持本地懒加载及三种视图。展示层压平同类运算链并完整展开业务公式，按有序行对齐差异；合成公式列紧跟测点描述并共同冻结，特殊 tab 按状态类优先的 registry 顺序展示且省略空 tab。
- 装置名称化展示：formulas artifact 升至 v2，按 side 提供唯一且非空的 `dev_addr → description`；前端将 `Device <地址>:` 精确前缀替换为装置名称，同时以原始文本判断公式差异。缺失、空名称和重复地址均原样回退，不修改 Dolt/AST/digest/risk。
- 公式可读性与分组展示：命名表达式改为 `父运算符 + 名称 =` 分组标题，内部信号逐行展开；结构化行通过 occurrence-aware 有序锚点对齐，插入/删除不再导致后续误高亮。正文使用 13px 中文无衬线字体和 1.6 行高，未改变任何后端合同。
- TAR_GZ staging 修复：required SQL 与可选 composite XML 使用统一的物化文档路径注册和流式 artifact 流程；普通附件仍为 metadata-only，前端 `directory-tar-gzip` 上传无需改动。

最终验证：

- 功能相关 backend 集（含 SourcePackage TAR_GZ、formal upload 和 repository sidecar readback）：150 passed；backend integration：8 passed、8 skipped，contract：1 skipped。
- backend 全量 unit：461 passed、1 skipped，另有 2 个既有 `table_presentation` 的 SYX 默认列顺序断言失败；相关文件未被本能力修改，功能相关集全部通过。
- frontend：207 passed；`npm run typecheck` 与 `npm run build` 通过。
- frontend directory-tar-gzip 定向回归：5 passed；上传协议无需修改。
- `ruff check`、`compileall`、`git diff --check` 通过。
- 本轮展示与 tab 顺序优化：composite signal 28 passed，business projection/upload preview/history/formal app 96 passed，backend integration 8 passed、8 skipped。
- 本轮装置名称化展示：composite signal 30 passed；business projection/upload preview/history/formal app 96 passed；backend integration 8 passed、8 skipped；formulas artifact v2 的正式 TAR_GZ 上传内容已定向验证。
- 本轮公式分组与字体优化：frontend 207 passed，typecheck/build 通过；composite signal、history 和正式 TAR_GZ upload 定向回归共 36 passed；`git diff --check` 通过。

large fixture（SQL 约 76 MiB、XML 约 872 KiB，单 worker）记录：

- SQL requested-table materialization：约 24084.68 ms；XML parse：约 71.38 ms。
- XML node count 6425、最大深度 97；catalog 绑定约 245.53 ms；supplemental artifact 构建约 120.78 ms。
- points artifact 约 771027 bytes，formulas artifact 约 1007974 bytes，合计约 1779001 bytes。
- 公式与测点均先建 key index 后线性合并，未引入 devices × formulas 交叉扫描。
