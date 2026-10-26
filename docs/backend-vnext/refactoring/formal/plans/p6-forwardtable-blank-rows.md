# `forwardtable_*` 空点行专项调查（DC56 第 4 项）

## 运行记录

- 调试节点：SSH 别名 `ct108-gw-dms-05`，运行时 hostname `gw-dms-test-05`。
- 运行前确认节点空闲：`docker ps` 无容器、无 host `dolt` 进程。
- 分支与代码 HEAD：`p6-forwardtable-blank`，`f13b4874cbd708294b34dcfddca683ea6df180bd`。
- 测量起止：2026-10-26 15:46:20–16:26:05 UTC；脚本 exit 0，起止 HEAD 相同，worktree clean。
- 六张目标表 × 八份数据共 48 个组合均纳入；存在表按 source-order scan 记录，缺表显式记为 absent/零计数。
- 原始统计 JSON 保存在节点 worktree 外：`/home/dev/gdds-p6-logs/keyless/forwardtable/forwardtable-blank-f13b4874cbd708294b34dcfddca683ea6df180bd.json`（目录 0700、文件 0600）。测量日志：`/home/dev/gdds-p6-logs/keyless/forwardtable/measurement-f13b4874cbd708294b34dcfddca683ea6df180bd.log`（0600）。两个文件都不进入 Git。
- 提交前 backend Ruff 与标准 mypy 均通过；记录在节点 `/home/dev/gdds-p6-logs/keyless/forwardtable/static-8191ea5-proxy2.log`。检查针对最终提交中的同一脚本内容。
- 初次完整扫描使用了“任一非 gid 列非空”的宽 proxy，`desc` 非空的重复模式因此被误列为点行。该次输出已由本次排除 `desc` 的 payload proxy 扫描取代，旧 JSON/Markdown 仅保留作取证，不用于本报告结论。初次调用的模块路径错误日志也保留在外部日志目录。

## 数据结论摘要

- 30 个存在表/数据组合中，22 个有完全重复组，均为一个重复组，且 22 组拥有同一列状态模式：`gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO`。没有一个重复组合包含多种状态模式；这 22 组中，同模式的非重复行数均为 0。模式的业务含义仍由 owner 判断。
- 完全重复组共有 6,177 行（6,155 多余行）。移除重复组全部行后，30 个存在组合均无 NULL gid，非 NULL gid 均唯一，重复组为 0。
- 对顺序采用排除 `desc` 的非 gid payload 状态 proxy：39,371 行 proxy payload 均无 NULL gid、无重复 gid 组；30 个组合中 27 个出现下降相邻对，共 10,242 个下降点，3 个组合为非递减，0 个组合出现相等相邻点。
- 同一 proxy 的补集共 6,177 行：首部 0、交错 6,176、尾部 1、无点参照 0。唯一尾部行位于 `forwardtable_yx1/rd-t3-c-v1`；其余候选模式行均落在首末 proxy 点之间。此位置分类是状态 proxy 的计数，不是空点业务分类。
- v1→v2 行数总变化仅为 `forwardtable_yx1/rd-t4-d` 的 +6：重复模式组 +1 行/多余行 +1，非重复 payload 行 +5。其余行数、重复组数和 gid 唯一性计数不变。源序相邻下降点的差值、列状态模式的变化及各表数据对逐项列在下文。


## 方法

- 输入为调试节点上的 t1–t4 v1、v2 共 8 份真实数据；原始 SQL 与单元格值仅在进程内处理，不写入 JSON、日志或本报告。
- 先通过现有 staging、业务物化与规范投影路径验证表规则分类；任一目标表不是 `SNAPSHOT_ONLY` 且 keyless 时立即拒绝。随后统计取自 production SQL parser 的 `ParseResult` / `SqlTableReader`，在业务物化和规范投影之前。原始解析列与投影列、原始读取行数与投影行数逐表核对。
- 源顺序核对：`parse_sql` 按 SQL statement 扫描顺序调用 `parse_insert`；后者按 VALUES tuple 顺序追加 `TupleSpan`；`_assemble` 将 span 顺序交给 `SqlTableReader`，其 `iter_rows()` 顺序遍历 span。故此处记录的是各表 INSERT tuple 的源顺序，不是规范投影或重排后的顺序。
- 完全重复按解析后的完整行（包含列名、SQL 类型和 typed cell）指纹分组。重复组模式按每列的 `NULL`、`EMPTY_STRING`、`NUMERIC_ZERO`、`OTHER_NONEMPTY` 分类；空字符串只匹配长度为零的字符串，数值零只匹配解析为数值类型且值为零的单元格。指纹只留在进程内。
- “非重复行”指其完整行只出现一次；第 3 项移除完全重复组的全部行后检查其余（单例）行的 gid。NULL 单独计数，重复组只统计非 NULL gid。
- 业务空点定义由 owner 判断，本报告不代为指定。顺序敏感性 proxy 将 `desc` 列排除，`non-empty point proxy` 定义为至少一个其余非 gid payload 列为 `OTHER_NONEMPTY` 的行；`blank point proxy` 是其补集。该列状态约定不是业务分类；逐状态模式给出相对 proxy 行的首部、交错、尾部计数，owner 可按认定的模式汇总。
- 顺序使用 proxy 行的 gid typed numeric 值；`gid_non_decreasing` 为非递减判断，另列下降相邻对和相等相邻对。存在 NULL 或非数值 gid 时标为不可判定，并报告数量。
- v1→v2 差值为 v2 减 v1；缺表按零行、零组计，并另列是否出现/消失及 schema 是否变化。状态模式差值按完整列状态向量对应。

## 状态标签

| 标签 | 含义 |
| --- | --- |
| `NULL` | SQL NULL |
| `EMPTY_STRING` | 空字符串 |
| `NUMERIC_ZERO` | typed numeric value 等于 0（含 bit 数值 0） |
| `OTHER_NONEMPTY` | 其余解析值；不输出值本身 |

## 逐表统计

### `forwardtable_yc1`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t1-a-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 525 | 1 | 18 | 19 | 506 | 0 | 0 | 是 | 506 | 0/0 | 0 | 否 | 43 | 0 | 0/19/0/0 |
| rd-t2-b-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 525 | 1 | 18 | 19 | 506 | 0 | 0 | 是 | 506 | 0/0 | 0 | 否 | 45 | 0 | 0/19/0/0 |
| rd-t3-c-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 552 | 1 | 5 | 6 | 546 | 0 | 0 | 是 | 546 | 0/0 | 0 | 否 | 139 | 0 | 0/6/0/0 |
| rd-t3-c-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 552 | 1 | 5 | 6 | 546 | 0 | 0 | 是 | 546 | 0/0 | 0 | 否 | 139 | 0 | 0/6/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 857 | 1 | 48 | 49 | 808 | 0 | 0 | 是 | 808 | 0/0 | 0 | 否 | 183 | 0 | 0/49/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 857 | 1 | 48 | 49 | 808 | 0 | 0 | 是 | 808 | 0/0 | 0 | 否 | 183 | 0 | 0/49/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 19 | 18 | 0 | 0 | 0 | 19 | 0 | 0 |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 478 | 478 | 0 | 0 | 0 | 0 |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 28 | 28 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 19 | 18 | 0 | 0 | 0 | 19 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 471 | 471 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 35 | 35 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 6 | 5 | 0 | 0 | 0 | 6 | 0 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3 | 3 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 543 | 543 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 6 | 5 | 0 | 0 | 0 | 6 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3 | 3 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 543 | 543 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 49 | 48 | 0 | 0 | 0 | 49 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 96 | 96 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 712 | 712 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 49 | 48 | 0 | 0 | 0 | 49 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 96 | 96 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 712 | 712 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +2 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1→rd-t2-b-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | -7 | -7 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +7 | +7 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |

### `forwardtable_yc2`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t1-a-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t3-c-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t3-c-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 74 | 1 | 3 | 4 | 70 | 0 | 0 | 是 | 70 | 0/0 | 0 | 否 | 31 | 0 | 0/4/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 74 | 1 | 3 | 4 | 70 | 0 | 0 | 是 | 70 | 0/0 | 0 | 否 | 31 | 0 | 0/4/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t4-d-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 68 | 68 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 68 | 68 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t4-d-v1→rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |

### `forwardtable_yk1`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t1-a-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 91 | 0 | 0 | 0 | 91 | 0 | 0 | 是 | 91 | 0/0 | 0 | 否 | 20 | 0 | 0/0/0/0 |
| rd-t2-b-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 91 | 0 | 0 | 0 | 91 | 0 | 0 | 是 | 91 | 0/0 | 0 | 否 | 21 | 0 | 0/0/0/0 |
| rd-t3-c-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 269 | 1 | 2 | 3 | 266 | 0 | 0 | 是 | 266 | 0/0 | 0 | 否 | 45 | 0 | 0/3/0/0 |
| rd-t3-c-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 269 | 1 | 2 | 3 | 266 | 0 | 0 | 是 | 266 | 0/0 | 0 | 否 | 45 | 0 | 0/3/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 276 | 1 | 11 | 12 | 264 | 0 | 0 | 是 | 264 | 0/0 | 0 | 否 | 27 | 0 | 0/12/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 276 | 1 | 11 | 12 | 264 | 0 | 0 | 是 | 264 | 0/0 | 0 | 否 | 27 | 0 | 0/12/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 80 | 80 | 0 | 0 | 0 | 0 |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 11 | 11 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 79 | 79 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 12 | 12 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 3 | 2 | 0 | 0 | 0 | 3 | 0 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 266 | 266 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 3 | 2 | 0 | 0 | 0 | 3 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 266 | 266 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 12 | 11 | 0 | 0 | 0 | 12 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 264 | 264 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 12 | 11 | 0 | 0 | 0 | 12 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 264 | 264 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +1 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | -1 | -1 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +1 | +1 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |

### `forwardtable_yt1`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t1-a-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 是 | 1 | 0/0 | 0 | 是 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 是 | 1 | 0/0 | 0 | 是 | 0 | 0 | 0/0/0/0 |
| rd-t3-c-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 69 | 1 | 3 | 4 | 65 | 0 | 0 | 是 | 65 | 0/0 | 0 | 否 | 8 | 0 | 0/4/0/0 |
| rd-t3-c-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 69 | 1 | 3 | 4 | 65 | 0 | 0 | 是 | 65 | 0/0 | 0 | 否 | 8 | 0 | 0/4/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 81 | 0 | 0 | 0 | 81 | 0 | 0 | 是 | 81 | 0/0 | 0 | 否 | 6 | 0 | 0/0/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 81 | 0 | 0 | 0 | 81 | 0 | 0 | 是 | 81 | 0/0 | 0 | 否 | 6 | 0 | 0/0/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 65 | 65 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 65 | 65 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 81 | 81 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 81 | 81 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 是→是 (可判定 是→是) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |

### `forwardtable_yx1`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 17 | 1 | 3 | 4 | 13 | 0 | 0 | 是 | 13 | 0/0 | 0 | 否 | 1 | 0 | 0/4/0/0 |
| rd-t1-a-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 17 | 1 | 3 | 4 | 13 | 0 | 0 | 是 | 13 | 0/0 | 0 | 是 | 0 | 0 | 0/4/0/0 |
| rd-t2-b-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 4609 | 1 | 362 | 363 | 4246 | 0 | 0 | 是 | 4246 | 0/0 | 0 | 否 | 309 | 0 | 0/363/0/0 |
| rd-t2-b-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 4609 | 1 | 362 | 363 | 4246 | 0 | 0 | 是 | 4246 | 0/0 | 0 | 否 | 309 | 0 | 0/363/0/0 |
| rd-t3-c-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 5305 | 1 | 1629 | 1630 | 3675 | 0 | 0 | 是 | 3675 | 0/0 | 0 | 否 | 1041 | 0 | 0/1629/1/0 |
| rd-t3-c-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 5305 | 1 | 1629 | 1630 | 3675 | 0 | 0 | 是 | 3675 | 0/0 | 0 | 否 | 1040 | 0 | 0/1630/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 9822 | 1 | 993 | 994 | 8828 | 0 | 0 | 是 | 8828 | 0/0 | 0 | 否 | 3253 | 0 | 0/994/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 9828 | 1 | 994 | 995 | 8833 | 0 | 0 | 是 | 8833 | 0/0 | 0 | 否 | 3256 | 0 | 0/995/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t1-a-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t1-a-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 13 | 13 | 0 | 0 | 0 | 0 |
| rd-t1-a-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 4 | 3 | 0 | 0 | 0 | 4 | 0 | 0 |
| rd-t1-a-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 13 | 13 | 0 | 0 | 0 | 0 |
| rd-t2-b-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 363 | 362 | 0 | 0 | 0 | 363 | 0 | 0 |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3853 | 3853 | 0 | 0 | 0 | 0 |
| rd-t2-b-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 393 | 393 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 363 | 362 | 0 | 0 | 0 | 363 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3821 | 3821 | 0 | 0 | 0 | 0 |
| rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 425 | 425 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 1630 | 1629 | 0 | 0 | 0 | 1629 | 1 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 364 | 364 | 0 | 0 | 0 | 0 |
| rd-t3-c-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3311 | 3311 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 1630 | 1629 | 0 | 0 | 0 | 1630 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 364 | 364 | 0 | 0 | 0 | 0 |
| rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 3311 | 3311 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 994 | 993 | 0 | 0 | 0 | 994 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 739 | 739 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 8089 | 8089 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 1 | 995 | 994 | 0 | 0 | 0 | 995 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 739 | 739 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 8094 | 8094 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | -1 | +0 | +0 | +0 | +0/+0 | 否→是 (可判定 是→是) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | -1 | +0 | +0 | +1 | -1/+0 | 否→否 (可判定 是→是) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +6 | +0 | +1 | +1 | +5 | +0/+0/+0 | +5 | +0/+0/+0/+0 | +3 | +0 | +0 | +1 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t1-a-v1→rd-t1-a-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t1-a-v1→rd-t1-a-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | -32 | -32 | +0 | +0 | +0 | +0 |
| rd-t2-b-v1→rd-t2-b-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +32 | +32 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +1 | -1 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t3-c-v1→rd-t3-c-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=NUMERIC_ZERO; devaddr=NUMERIC_ZERO; desc=OTHER_NONEMPTY; fun=NUMERIC_ZERO; inf=NUMERIC_ZERO; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +1 | +1 | +0 | +0 | +0 | +1 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +5 | +5 | +0 | +0 | +0 | +0 |

### `forwardtable_yx2`

| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |
| rd-t1-a-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t1-a-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t2-b-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t3-c-v1 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t3-c-v2 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 不可判定 | 0 | 0/0 | 0 | 不可判定 | 0 | 0 | 0/0/0/0 |
| rd-t4-d-v1 | gid, devaddr, desc, fun, inf, fcda, icseq | 223 | 0 | 0 | 0 | 223 | 0 | 0 | 是 | 223 | 0/0 | 0 | 否 | 13 | 0 | 0/0/0/0 |
| rd-t4-d-v2 | gid, devaddr, desc, fun, inf, fcda, icseq | 223 | 0 | 0 | 0 | 223 | 0 | 0 | 是 | 223 | 0/0 | 0 | 否 | 13 | 0 | 0/0/0/0 |

**按列状态模式的重复组、单例与源顺序分布**：

| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| rd-t4-d-v1 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 222 | 222 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | 0 | 0 | 0 | 222 | 222 | 0 | 0 | 0 | 0 |

**v1→v2 计数变化**：

| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t2-b-v1→rd-t2-b-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t3-c-v1→rd-t3-c-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 不可判定→不可判定 (可判定 不可判定→不可判定) |
| rd-t4-d-v1→rd-t4-d-v2 | no/no | +0 | +0 | +0 | +0 | +0 | +0/+0/+0 | +0 | +0/+0/+0/+0 | +0 | +0 | +0 | +0 | +0/+0 | 否→否 (可判定 是→是) |

**v1→v2 状态模式差值**：

| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=EMPTY_STRING; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |
| rd-t4-d-v1→rd-t4-d-v2 | gid=OTHER_NONEMPTY; devaddr=OTHER_NONEMPTY; desc=OTHER_NONEMPTY; fun=OTHER_NONEMPTY; inf=OTHER_NONEMPTY; fcda=OTHER_NONEMPTY; icseq=NUMERIC_ZERO | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 | +0 |

## 对 DC56 第 4 项的结论

- 重复行状态模式：有重复组的表/数据组合 22 组；其中跨多个状态模式的组合 0 组（无）。其余有重复组的组合各自只有一种模式；具体模式与组数/行数见明细。该结果只比较列状态，不断定模式的业务含义。
- 非空点 gid 唯一性：按上述排除 desc 的 payload proxy，有行的组合 30 组；gid NULL 或非 NULL 重复组的例外为 无。具体 NULL、重复组数及多余行数见明细。
- 源顺序与 gid：按 proxy 有行且 gid 可数值比较的组合 30 组；其中有下降点的组合 27 组（forwardtable_yc1/rd-t2-b-v1、forwardtable_yc1/rd-t2-b-v2、forwardtable_yc1/rd-t3-c-v1、forwardtable_yc1/rd-t3-c-v2、forwardtable_yc1/rd-t4-d-v1、forwardtable_yc1/rd-t4-d-v2、forwardtable_yc2/rd-t4-d-v1、forwardtable_yc2/rd-t4-d-v2、forwardtable_yk1/rd-t2-b-v1、forwardtable_yk1/rd-t2-b-v2、forwardtable_yk1/rd-t3-c-v1、forwardtable_yk1/rd-t3-c-v2、forwardtable_yk1/rd-t4-d-v1、forwardtable_yk1/rd-t4-d-v2、forwardtable_yt1/rd-t3-c-v1、forwardtable_yt1/rd-t3-c-v2、forwardtable_yt1/rd-t4-d-v1、forwardtable_yt1/rd-t4-d-v2、forwardtable_yx1/rd-t1-a-v1、forwardtable_yx1/rd-t2-b-v1、forwardtable_yx1/rd-t2-b-v2、forwardtable_yx1/rd-t3-c-v1、forwardtable_yx1/rd-t3-c-v2、forwardtable_yx1/rd-t4-d-v1、forwardtable_yx1/rd-t4-d-v2、forwardtable_yx2/rd-t4-d-v1、forwardtable_yx2/rd-t4-d-v2）。gid 不可判定的组合 0 组（无）；相等相邻点另计于明细。
- 空点位置 proxy：存在 proxy 行交错分布的表/数据组合 22 组（forwardtable_yc1/rd-t2-b-v1、forwardtable_yc1/rd-t2-b-v2、forwardtable_yc1/rd-t3-c-v1、forwardtable_yc1/rd-t3-c-v2、forwardtable_yc1/rd-t4-d-v1、forwardtable_yc1/rd-t4-d-v2、forwardtable_yc2/rd-t4-d-v1、forwardtable_yc2/rd-t4-d-v2、forwardtable_yk1/rd-t3-c-v1、forwardtable_yk1/rd-t3-c-v2、forwardtable_yk1/rd-t4-d-v1、forwardtable_yk1/rd-t4-d-v2、forwardtable_yt1/rd-t3-c-v1、forwardtable_yt1/rd-t3-c-v2、forwardtable_yx1/rd-t1-a-v1、forwardtable_yx1/rd-t1-a-v2、forwardtable_yx1/rd-t2-b-v1、forwardtable_yx1/rd-t2-b-v2、forwardtable_yx1/rd-t3-c-v1、forwardtable_yx1/rd-t3-c-v2、forwardtable_yx1/rd-t4-d-v1、forwardtable_yx1/rd-t4-d-v2）；各组合的首部、交错、尾部行数以及逐模式位置计数见明细。空点模式须由 owner 确认后再解释该分布。
- 本调查不定义空点行的业务语义，也不提出规则改动；如重复行并非同一业务空点模式，或顺序有业务含义且不能由 gid 恢复，按 DC56 另行立项条件处理。


## 后续清理候选（本次未删除）

依照任务约束，本次未删除任何文件、分支或 worktree。owner 完成审阅与合入决策后，可评估清理：

- 调试节点 `/home/dev/gdds-p6-logs/keyless/forwardtable/` 下本次最终 JSON/Markdown、superseded 的 `8191ea...` JSON/Markdown、`measurement-*` 与 `static-*` 日志、`mypy-cache/`、`p6-forwardtable-blank-6ada548.bundle`。
- 开发主机同名日志目录下导入阶段留存的 `p6-forwardtable-blank.bundle`、`p6-forwardtable-blank-7a91cbe.bundle`、`p6-forwardtable-blank-6ada548.bundle`，以及 clean、停在 `6ada548d450989840601af6cb68c9453a04a85f2` 的 linked worktree。
- 调试节点上的正式 linked worktree `/home/dev/gdds-p6-logs/keyless/forwardtable/worktree` 与 `p6-forwardtable-blank` 分支需待 owner 决定合入方式后再处理。
