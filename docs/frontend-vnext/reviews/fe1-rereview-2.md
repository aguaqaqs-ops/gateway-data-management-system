# FE1 复审报告（第 2 轮）

- **复审对象：** 分支 `fe-vnext`，代码候选 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de`（`frontend/` 树 `8e553cbf49`）；
  handoff 提交 `7732c4140e6c60570c7fe4ea2c806e436e44ac9a`（只改 handoff，`frontend/` 树相同）。
- **范围：** `918282218e..7732c4140e`，三个提交：`b55a64db8b`（B4）、`c5ee9a06bc`（行数字段修正）、`7732c4140e`（handoff）。
- **依据：** [FE1 复审第 1 轮](fe1-rereview-1.md) §3、§6。
- **日期：** 2026-11-02。
- **结论：PASS。** B4 已修复并验证，R1、R2 已处理。FE1 剩下的工作是 04 阶段退出取证（§5），以及 owner 的退出确认。

## 1. 范围

本轮只改动了以下文件：

- `frontend/src/features/view-model/model.ts`
- `frontend/src/features/view-model/model.test.ts`
- `frontend/src/features/bundle/presentation.ts`
- `frontend/src/design-system/theme.test.ts`
- `docs/frontend-vnext/fe1-handoff.md`

依赖、lockfile、`run-tests.sh`、后端 fixture、`vnext/`（树仍为 `2791d3ff3d`）、AGENTS、kickoff 和审核报告都没有改动。**通过。**

## 2. B4 核对

- **标注形状：**
  - `RiskAnnotation` 按后端定义，字段为 `annotation_id`、`risk_level`、`reasons`、`diagnostics`、`target`；
  - 只有 `target.target_type === "ROW"` 的标注进入行风险映射（`model.ts` 中的 `deriveChangeLocations`）；
  - `RiskReport`、`RiskTableReport`、`SurfaceTable`、`SurfaceColumn` 和 records 的值结构，也都改成了后端字段；
  - 我与后端 `SurfaceColumn`、`annotations.bin` 的实际键（`contract_version`、`table_name`、`annotations`）逐项对照过，一致。
  - 原来按 `display_order` 排序列，但后端没有这个字段，所以删除了，改为保持后端给出的列顺序。
- **行标识：** `identityKey` 把 records 的 32 字节和标注的 `sha256:<hex>` 统一转成小写的 `sha256:<hex>`。
- **本地读取：** `presentation.ts` 新增 `readLocalRiskAnnotations`。它按 surface 表的 `risk_refs.annotation_ref` 在 closure 中定位文件，只读取已安装的本地 bundle；文档里的 `table_name` 不符时报错。没有新增网络调用（FD3）。
- **record kind：**
  - 行级取值来自 `ComparisonRecordKind` 和 `OrderedRecordKind`，表级取值（`SCHEMA_CHANGE`、`TABLE_DEGRADED`、`ORDERED_TABLE_DEGRADED`）不进入变更定位；
  - 自造的 `UNCHANGED`、`UNCHANGED_RANGE` 已删除；
  - `filterChangedRows.changeKinds` 的类型限定为行级 record kind，并有注释说明。
- **唯一测试 owner：** `model.test.ts` 中的“maps backend row records to their local annotations and filters row changes”。
  - 它从本地安装的后端 bundle 读取 records 和标注，断言三处变更依次是 `ROW_ADDED`/中低、`ROW_DELETED`/中低、`ROW_MODIFIED`/中高；
  - 同一用例加入了一条 TABLE 标注和一条 `SCHEMA_CHANGE` 记录，验证前者不覆盖行风险、后者不产生行定位。
- **变异探针**（05 上一次性 worktree，用后已删除）：

  | 探针 | 改动 | 结果 |
  | --- | --- | --- |
  | 行标识不加前缀 | `identityKey` 的字节分支返回不带前缀的 hex | runner exit 1；只有 B4 用例失败，三处风险都变成 `null` |
  | 不过滤标注目标 | 删除 `target_type === "ROW"` 过滤 | runner exit 1；只有 B4 用例失败，`ROW_ADDED` 的风险被 TABLE 标注覆盖为 `HIGH` |

  两次都只有这一个用例失败，说明它确实是这两项行为的唯一 owner，而且不是空跑。
- **行数字段：** `rowCount` 直接读取 `row_count_before`、`row_count_current`，不再使用后端没有的候选字段名。

## 3. R1、R2

- **R1：** `theme.test.ts` 中 4 条自比较断言已删除。
- **R2：** handoff 中“完成情况”已标为原候选摘要，并指向 B4 一节；“本地 bundle fixture”已标为历史记录，写明当前唯一的 fixture 是后端产物，摘要为 `a34e8560…`。

## 4. 复跑与证据

- **源码传输：** 在开发主机执行 `git bundle create … ^0e0d14f1d1 fe-vnext`，bundle SHA256 为 `f09109ce27dc9e10b69fb248d0a223bc69a524730192aef1e05c875b369f176e`，两端一致。
  05 verify 并 fetch 后，`FETCH_HEAD` 等于候选；05 的 main 停在 `0e0d14f1d1` 未移动。
- **05 worktree：** `/home/dev/gdds-fe-rereview2-fe1-7732c414-05`，detached，clean，已建 `legacy` 符号链接，运行前确认占用标记不存在。缓存环境变量与前两轮相同。

日志在 05 的 `/home/dev/gdds-fe-logs/fe1/rereview-2/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| worktree 准备 `rereview-setup.log` | 16:00:55–16:00:56 | HEAD `7732c4140e`、`frontend/` 树 `8e553cbf49`、clean | `0111632afe997887f7c2fab77173f4181f577a584914d523712a693d8c60cad9` |
| `run-tests.sh --e2e` `frontend-tests-20261102T160108Z.log` | 16:01:08–16:01:21 | **exit 0**；HEAD 和树起止不变；9 个文件 38 项单测通过；e2e 3 passed；fixture 摘要和 tar SHA256 与上一轮相同；运行后 clean | `549a6171f1659e5e1f464829daf19bbb7914ea6726e2be44f4f783df2a14e94c` |
| B4 变异探针 `b4-mutation-probes.log` | 16:01:37–16:01:57 | 两个探针都 exit 1（符合预期） | `5ee8aafd9cbf36da068a4f80089145f2ce60c497f67f642ef30e166aa5db6aa2` |

- **handoff 日志：** fix3 一节引用的 12 份日志，我在开发主机（即 CT201）和 05 上逐一重算了 SHA256，全部一致。其中包括首次 B4 候选的 typecheck 失败日志 `0c11ece3…c062`，以及修复后 runner 日志 `f5083ca2…7705`。
- **DC68：** 三次前置错误（Docker 模板写错、bundle 前置祖先选错、缓存路径查错）都发生在 runner 启动之前，保留了日志，从步骤开头重做一次。处理符合 DC68。
- **typecheck 失败的处理：** 首次 B4 候选在 05 上 typecheck 失败。05 是调试节点，追加提交修复后重跑，处理正确；失败日志已保留。

## 5. 非阻塞意见（FE2 处理）

**R4. 本地搜索会命中二进制行标识的字节值和值结构里的类型名**（`model.ts` 中的 `containsSearchText`）
递归搜索会进入 `Uint8Array`，把 0–255 的字节当作数字来匹配，例如搜索“12”可能命中行标识中恰好含有字节 12 的行。它还会匹配值结构中的 `kind` 字段，例如搜索“string”会命中所有记录。
建议 FE2 接入搜索框时，跳过二进制值（`ArrayBuffer`/`ArrayBufferView`），只搜索 `text` 等展示值，不搜索 `kind` 这类结构字段；补一个用例即可，不用单独设 owner。

**带入 FE2 的事项**（与第 1 轮 §5 和 R3 相同）：
- N1、N2 要在 FE2 接入按钮和进度界面之前完成；N4、N6 也在 FE2 处理；
- token 补上草图的行分隔色 `#EEF1F4`；
- 导航 diagnostics 按 BE-b §4.7 改为单独的 `diagnostics_ref` 产物，并去掉 `diagnosticText`；
- FE2 审核时核对 BE-b §4.7 的文案表。

## 6. FE1 退出前剩余事项

1. **04 取证**（kickoff §6）：
   - 在 `ct108-gw-dms-04` 的 clean detached worktree 上，用代码候选 `c5ee9a06bc` 运行一次完整的 `./frontend/scripts/run-tests.sh --e2e`；
   - 工具链镜像和 npm 缓存沿用 04 上 FE0 的预填充（默认路径），运行前核对 config digest、7 个 DiffID 和缓存归档 SHA256；
   - 日志记录 hostname、起止时间、起止 HEAD 和 `frontend/` 树、exit code 以及 SHA256。04 上一次（`b67da4795f`）的运行只作为历史记录；
   - 取证提交只改 handoff，提交后由审核会话做证据核对。
2. **结论确认：** owner 确认 FE1 退出后，由设计会话打 `fe-fe1-exit` 并合入 main。
3. **合入后可以清理：** 审核会话在开发主机和 05 上的 `gdds-fe-rereview1-fe1-*`、`gdds-fe-rereview2-fe1-*` worktree，以及实施会话已经被取代的 05 worktree。
