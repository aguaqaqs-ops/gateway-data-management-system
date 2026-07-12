# Preview Bundle Parquet Reuse Note

本文只记录一个很小的实现结论，不是新 contract。

## 结论

- `preview` 中真正值得做复用的是 snapshot/input table parquet。
- pair 级 `diff_artifacts/*.records.parquet` 和 `risk` / `diagnostics` 输出不值得再加同类共享复用。
- 当前 `comparison-bundle` / `bundle-assembly` contract 已经足够表达 shared snapshot artifacts，不需要为这件事修改前后端协议。

## 语义边界

- snapshot/input table parquet 是“同一份输入数据”的闭合产物，可以在同一 bundle 内跨 pair / 跨装配分支复用。
- diff records 是 pair 级结果，天然绑定 `view_id` 和 pair 语义，复用收益小，维护成本高。
- 如果未来真的要做“物理单文件 + 逻辑多引用”，应该放在 bundle assembly / artifact closure 层处理，不要把它上升成新的前后端业务 contract。
- 这也是为什么本次优化落在 `backend/preview/bundle_builder.py`：当前物理 parquet 仍然由 legacy preview bundle assembly 负责，`backend_vnext` 的 snapshot materialization 侧只负责产出 provisional summary、table_set 和 reader 句柄。

## 当前实现建议

- 保持 snapshot/input table 的本地 reuse。
- 继续让 diff records 保持一次写入、一次闭合。
- 不为这条优化引入新的前后端协议字段。
