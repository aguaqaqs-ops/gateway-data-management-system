# Presentation 稳定编码

本表拥有 BE-b 面向 FE4b 的编码和旧条目替换映射。中文文案由前端维护；导航诊断不得复制进 Surface summary。完整导航 target/side/params 验证由 [Business Navigation](business-navigation.md) 拥有。机器清单见 `vnext/fixtures/presentation-inputs/diagnostic-codes.json`。

## Surface、comparison records 与 Risk

| 当前编码 | 取代的旧条目/来源 | 对外语义 |
| --- | --- | --- |
| COMPARISON_INTERNAL_ERROR | Python 异常类名、任意非稳定异常字符串 | 比较未能完成；公开产物不带异常类名、路径或全文 |
| DUPLICATE_EFFECTIVE_KEY | `DUPLICATE_EFFECTIVE_KEY:<table>` | 比较有效键重复；table 由产物原有 table scope 提供 |
| RISK_TABLE_BUDGET_EXCEEDED | `max_annotations_per_table exceeded`、表级预算短句 | 风险表级计算限额降级 |
| RISK_ANNOTATION_LIMIT_EXCEEDED | `max_annotations_per_pair exceeded` | pair 标注限额降级，部分标注不发布 |
| RISK_DIAGNOSTICS_TRUNCATED | `risk diagnostics truncated` | 诊断预算不足，风险降级 |
| RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED | `risk annotation artifact budget exceeded` | 标注 artifact 未发布，不能据此推断无风险 |
| PROJECT_IDENTITY_UNVERIFIABLE | 原稳定码保留 | 项目身份不能确认 |
| DATASET_REPLACEMENT | 原稳定码保留 | 独立数据集分侧浏览 |

比较 schema 稳定码保留：`BEFORE_ONLY_COLUMNS`、`CURRENT_ONLY_COLUMNS`、`INCOMPATIBLE_SELECTED_COLUMNS`、`EFFECTIVE_KEY_CHANGED`、`SOURCE_PRIMARY_KEY_CHANGED`、`EFFECTIVE_KEY_IGNORED`、`BUSINESS_SCHEMA_CHANGED`、`DEGRADE_NO_COMPARE_KEY`、`TABLE_READER_UNAVAILABLE`。

ordered 的稳定码保留：`ORDERED_REQUIRED_COLUMN_MISSING`、`NO_SELECTED_COLUMNS`、`ROW_IDENTITY_MISSING`、`BLANK_PROVENANCE_INVALID`、`BLANK_PROVENANCE_MISSING`、`CANONICAL_BLANK_PROVENANCE_INVALID`、`CANONICAL_GID_INVALID`、`ORDERED_INTEGER_INVALID`、`ORDER_KEY_DUPLICATE`、`ORDER_KEY_INVALID`、`ORDER_KEY_MISSING`、`ROW_IDENTITY_DUPLICATE`、`ROW_SHAPE_MISMATCH`、`SCALAR_TYPE_MISMATCH`、`SCALAR_TYPE_UNKNOWN`、`SCALAR_VALUE_INVALID`、`SET_VALUE_INVALID`、`SOURCE_GID_INVALID`、`SOURCE_RESERVED_PSEUDO_GID`。它们沿 comparison records/表 scope 传递；`ORDERED_PROVIDER` 是 ordered 单侧记录已有来源码。取消、超时、资源异常和内部 native runtime failure 沿任务终态传播，不伪装成功表或无风险。

Surface summary 将上述 owner 稳定码去重排序；完整 summary 元素只允许大写 token。未知内部文本统一归 COMPARISON_INTERNAL_ERROR。surface assembly/bundle assembly 的 FAILED/CANCELLED terminal diagnostics 不进入成功 surface，pair 失败/取消的原文不混入 Surface summary。本表不将内部终态错误字符串承诺为新的客户端协议。

## 导航诊断全集

以下十二码是 v1 全集。前十码保留第一步规则，后两码为 BE-b 完整性/标量资格补充；不是替换 Surface 降级码。

| 编码 | params 键 |
| --- | --- |
| DEVICE_ADDRESS_DUPLICATE | dev_addr |
| DEVICE_GID_DUPLICATE | gid |
| DEVICE_TAB_COUNT_UNKNOWN | identity_column |
| DEVICE_ROWS_UNASSIGNED | identity_column, row_count, changed_row_count |
| CHANNEL_TABLE_UNCLAIMED | board, link_no |
| PROTOCOL_EXE_MISSING | board, link_no |
| PROTOCOL_TABLE_NOT_FOUND | board, link_no, protocol, expected_tables |
| APP_TABLE_CFG_MISSING | app_name |
| APP_TABLE_CFG_DUPLICATE | app_name, table_cfg |
| APP_TABLE_NOT_FOUND | app_name, table_cfg |
| DEVICE_TAB_FACTS_UNAVAILABLE | identity_column, reason |
| DEVICE_FILTER_VALUE_UNSUPPORTED | identity_column, reason |

`DEVICE_TAB_FACTS_UNAVAILABLE.reason`：RECORDS_UNAVAILABLE、RISK_ATTRIBUTION_UNAVAILABLE、TABLE_DEGRADED。`DEVICE_FILTER_VALUE_UNSUPPORTED.reason`：INTEGER_OUT_OF_RANGE、UNSUPPORTED_TYPE、IDENTITY_EXCLUDED。原 value、异常全文和 host path 不回传。普通事实不可用只按 table 发一条；不支持筛选按受影响存在侧各一条；replacement 全部诊断须有实际 side。
