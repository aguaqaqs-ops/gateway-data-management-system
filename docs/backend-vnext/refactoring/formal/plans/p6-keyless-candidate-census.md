# 真实数据 keyless 表候选键普查

## 方法

- 输入为调试节点上的 t1–t4 v1、v2 共 8 个 SourcePackage；不写回数据包。
- 每份数据通过现有 staging、SQL/XML 解析、READERS_REQUIRED 业务物化与 `project_canonical_table_set`；仅以规范投影 manifest 中 `canonical_key_columns` 为空的表作为纳入条件。
- 行数、列数与候选键均取自规范投影后的表。被规则丢弃的列已不参与候选键。规则类别取当前规则解析结果。
- 候选键为所有出现数据集中共同存在的列中，均无 NULL 且唯一的最小列组合，最多 3 列。空表不提供唯一性证据；至少一个数据集有行才报告候选键。浮点列参与项单独标记。
- 完全相同行按规范投影后的列名、类型和值指纹计数，报告每组保留一行后多出的行数。新增/删除按整行多重集合差计数；候选键变化按唯一键的插入、删除和整行变化计数。
- 工具做两遍同一物化与投影：第一遍收集每数据集的投影 schema 与规则，第二遍只对纳入表统计指纹。业务单元格值只在进程内处理，不写入 JSON、日志或报告。
- 表名不在 DC29 §12 已知 35 表清单时标记为“本次新表”。结果不包含任何业务单元格值；无候选键结论不代表建议新增规则。

## 运行记录

- 节点：`ct108-gw-dms-05`（hostname `gw-dms-test-05`）。运行时间：2026-10-26 13:27:54–14:40:36（UTC+08:00），退出码 0。
- 起始 HEAD：`e5840be32c06187c515f8ffc75ccc85291766baa`；结束 HEAD：`5a2989bec2fbc269b0e567bcee4cc309513f90e4`。运行期间节点 `main` 于 14:23:25 经正常 merge 推进。检查提交差异后，候选键普查脚本、表规则、解析、物化和规范投影代码均未变化；原始数据包只读。
- backend Ruff、项目 mypy（486 个源码文件）及普查脚本定向 mypy 均通过，检查时 HEAD 为起始提交。
- 原始统计 JSON 保存在节点外部日志目录 `/home/dev/gdds-p6-logs/keyless/keyless-census-e5840be.json`，权限 0600；目录权限 0700。运行日志同目录保存，包含 hostname、起止时间、起止 HEAD 与退出码。JSON 未纳入 Git。

## 汇总

共纳入 **35** 个表名（在至少一个数据集中 canonical key 为空）。

| 分组 | 表数 | 表名 |
| --- | ---: | --- |
| 恰有一个全局最小候选键 | 0 | — |
| 有多个全局最小候选键 | 22 | comm_user_data、dev104_cfg、forwardtable_yx2、forwardtbl_lst_yc、forwardtbl_lst_yk、forwardtbl_lst_yt、forwardtbl_lst_yx、iec101_cfg、iec104_cfg、iec104gw_cfg、iec61850c_cfg、jdxx_cfg、mms_rp_cdc_index、nbridge_cfg、nr103d_cfg、project、sc_cfg、scada_cfg、sg_manage_cfg、sntp_cfg、vqc_cfg、wave_cfg |
| 无全局候选键 | 13 | cnt_manage_cfg、forwardtable_yc1、forwardtable_yc2、forwardtable_yk1、forwardtable_yt1、forwardtable_yx1、forwardtbl_lst_cs、forwardtbl_lst_dz、forwardtbl_lst_qt、forwardtbl_lst_ym、nr103ht_cfg、out_time_cfg、wf_cfg |
| 至少一份数据有完全重复行 | 5 | forwardtable_yc1、forwardtable_yc2、forwardtable_yk1、forwardtable_yt1、forwardtable_yx1 |
| DC29 清单之外的新表 | 0 | — |

## 逐表统计

### `cnt_manage_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `comm_user_data`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 1 | 2 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：data_key、data_val
- rd-t1-a-v2：data_key、data_val
- rd-t2-b-v1：data_key、data_val
- rd-t2-b-v2：data_key、data_val
- rd-t3-c-v2：data_key、data_val
- rd-t4-d-v1：data_key、data_val
- rd-t4-d-v2：data_key、data_val

**全局最小候选键**：
- `(data_key)`
- `(data_val)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (data_key) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (data_val) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (data_key) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (data_val) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 1 | 0 | (data_key) | 1 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 1 | 0 | (data_val) | 1 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (data_key) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (data_val) | 0 | 0 | 0 | 0/0 | 0/0 |

### `dev104_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 62 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 62 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no, page_no)`
- `(option_desc, page_no)`
- `(option_name, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `forwardtable_yc1`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t2-b-v1 | 525 | 7 | SNAPSHOT_ONLY | keyless | 18 |
| rd-t2-b-v2 | 525 | 7 | SNAPSHOT_ONLY | keyless | 18 |
| rd-t3-c-v1 | 552 | 7 | SNAPSHOT_ONLY | keyless | 5 |
| rd-t3-c-v2 | 552 | 7 | SNAPSHOT_ONLY | keyless | 5 |
| rd-t4-d-v1 | 857 | 7 | SNAPSHOT_ONLY | keyless | 48 |
| rd-t4-d-v2 | 857 | 7 | SNAPSHOT_ONLY | keyless | 48 |

**各数据集规范投影列**：
- rd-t2-b-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t2-b-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 7 | 7 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtable_yc2`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 74 | 7 | SNAPSHOT_ONLY | keyless | 3 |
| rd-t4-d-v2 | 74 | 7 | SNAPSHOT_ONLY | keyless | 3 |

**各数据集规范投影列**：
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtable_yk1`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t2-b-v1 | 91 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t2-b-v2 | 91 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t3-c-v1 | 269 | 7 | SNAPSHOT_ONLY | keyless | 2 |
| rd-t3-c-v2 | 269 | 7 | SNAPSHOT_ONLY | keyless | 2 |
| rd-t4-d-v1 | 276 | 7 | SNAPSHOT_ONLY | keyless | 11 |
| rd-t4-d-v2 | 276 | 7 | SNAPSHOT_ONLY | keyless | 11 |

**各数据集规范投影列**：
- rd-t2-b-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t2-b-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


**仅在部分数据集唯一的最小组合（需业务判断）**：
- `(gid)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(desc, devaddr)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(devaddr, fun, inf)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 1 | 1 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtable_yt1`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t2-b-v1 | 1 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t2-b-v2 | 1 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t3-c-v1 | 69 | 7 | SNAPSHOT_ONLY | keyless | 3 |
| rd-t3-c-v2 | 69 | 7 | SNAPSHOT_ONLY | keyless | 3 |
| rd-t4-d-v1 | 81 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t4-d-v2 | 81 | 7 | SNAPSHOT_ONLY | keyless | 0 |

**各数据集规范投影列**：
- rd-t2-b-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t2-b-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


**仅在部分数据集唯一的最小组合（需业务判断）**：
- `(desc)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(devaddr)`：唯一于 rd-t2-b-v1、rd-t2-b-v2、rd-t4-d-v1、rd-t4-d-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=UNIQUE；rd-t4-d-v2=UNIQUE
- `(fcda)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(fun)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(gid)`：唯一于 rd-t2-b-v1、rd-t2-b-v2、rd-t4-d-v1、rd-t4-d-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=UNIQUE；rd-t4-d-v2=UNIQUE
- `(icseq)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(inf)`：唯一于 rd-t2-b-v1、rd-t2-b-v2；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=DUPLICATE；rd-t3-c-v2=DUPLICATE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtable_yx1`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 17 | 7 | SNAPSHOT_ONLY | keyless | 3 |
| rd-t1-a-v2 | 17 | 7 | SNAPSHOT_ONLY | keyless | 3 |
| rd-t2-b-v1 | 4609 | 7 | SNAPSHOT_ONLY | keyless | 362 |
| rd-t2-b-v2 | 4609 | 7 | SNAPSHOT_ONLY | keyless | 362 |
| rd-t3-c-v1 | 5305 | 7 | SNAPSHOT_ONLY | keyless | 1629 |
| rd-t3-c-v2 | 5305 | 7 | SNAPSHOT_ONLY | keyless | 1629 |
| rd-t4-d-v1 | 9822 | 7 | SNAPSHOT_ONLY | keyless | 993 |
| rd-t4-d-v2 | 9828 | 7 | SNAPSHOT_ONLY | keyless | 994 |

**各数据集规范投影列**：
- rd-t1-a-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t1-a-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t2-b-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t2-b-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t3-c-v2：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 32 | 32 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 2 | 2 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 6 | 0 | — | — | — | — | — | — |

### `forwardtable_yx2`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 223 | 7 | SNAPSHOT_ONLY | keyless | 0 |
| rd-t4-d-v2 | 223 | 7 | SNAPSHOT_ONLY | keyless | 0 |

**各数据集规范投影列**：
- rd-t4-d-v1：gid、devaddr、desc、fun、inf、fcda、icseq
- rd-t4-d-v2：gid、devaddr、desc、fun、inf、fcda、icseq

**全局最小候选键**：
- `(desc)`
- `(gid)`
- `(devaddr, fcda)`
- `(devaddr, inf)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (gid) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (devaddr, fcda) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (devaddr, inf) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (gid) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (devaddr, fcda) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (devaddr, inf) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (gid) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (devaddr, fcda) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (devaddr, inf) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (gid) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (devaddr, fcda) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (devaddr, inf) | 0 | 0 | 0 | 0/0 | 0/0 |

### `forwardtbl_lst_cs`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtbl_lst_dz`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtbl_lst_qt`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtbl_lst_yc`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 2 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 2 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：
- `(name)`
- `(tbname)`


**仅在部分数据集唯一的最小组合（需业务判断）**：
- `(isic)`：唯一于 rd-t2-b-v1、rd-t2-b-v2、rd-t3-c-v1、rd-t3-c-v2；rd-t1-a-v1=NO_ROWS；rd-t1-a-v2=NO_ROWS；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=UNIQUE；rd-t3-c-v2=UNIQUE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(type)`：唯一于 rd-t2-b-v1、rd-t2-b-v2、rd-t3-c-v1、rd-t3-c-v2；rd-t1-a-v1=NO_ROWS；rd-t1-a-v2=NO_ROWS；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=UNIQUE；rd-t3-c-v2=UNIQUE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |

### `forwardtbl_lst_yk`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：
- `(isic)`
- `(name)`
- `(tbname)`
- `(type)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |

### `forwardtbl_lst_ym`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `forwardtbl_lst_yt`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：
- `(isic)`
- `(name)`
- `(tbname)`
- `(type)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (isic) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (type) | 0 | 0 | 0 | 0/0 | 0/0 |

### `forwardtbl_lst_yx`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 1 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 2 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 2 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：type、tbname、name、isic
- rd-t1-a-v2：type、tbname、name、isic
- rd-t2-b-v1：type、tbname、name、isic
- rd-t2-b-v2：type、tbname、name、isic
- rd-t3-c-v1：type、tbname、name、isic
- rd-t3-c-v2：type、tbname、name、isic
- rd-t4-d-v1：type、tbname、name、isic
- rd-t4-d-v2：type、tbname、name、isic

**全局最小候选键**：
- `(name)`
- `(tbname)`


**仅在部分数据集唯一的最小组合（需业务判断）**：
- `(isic)`：唯一于 rd-t1-a-v1、rd-t1-a-v2、rd-t2-b-v1、rd-t2-b-v2、rd-t3-c-v1、rd-t3-c-v2；rd-t1-a-v1=UNIQUE；rd-t1-a-v2=UNIQUE；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=UNIQUE；rd-t3-c-v2=UNIQUE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE
- `(type)`：唯一于 rd-t1-a-v1、rd-t1-a-v2、rd-t2-b-v1、rd-t2-b-v2、rd-t3-c-v1、rd-t3-c-v2；rd-t1-a-v1=UNIQUE；rd-t1-a-v2=UNIQUE；rd-t2-b-v1=UNIQUE；rd-t2-b-v2=UNIQUE；rd-t3-c-v1=UNIQUE；rd-t3-c-v2=UNIQUE；rd-t4-d-v1=DUPLICATE；rd-t4-d-v2=DUPLICATE


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (tbname) | 0 | 0 | 0 | 0/0 | 0/0 |

### `iec101_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t3-c-v1 | 337 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 337 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 337 | 337 | (option_desc) | 0 | 0 | 337 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 337 | 337 | (option_name) | 0 | 0 | 337 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 337 | 337 | (no, page_name) | 0 | 0 | 337 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 337 | 337 | (no, page_no) | 0 | 0 | 337 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `iec104_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 334 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 334 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 337 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 337 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 330 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 330 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 334 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 334 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 330 | 330 | (option_desc) | 0 | 0 | 330 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 330 | 330 | (option_name) | 0 | 0 | 330 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 330 | 330 | (no, page_name) | 0 | 0 | 330 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 330 | 330 | (no, page_no) | 0 | 0 | 330 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `iec104gw_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t3-c-v1 | 209 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 209 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 209 | 209 | (option_desc) | 0 | 0 | 209 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 209 | 209 | (option_name) | 0 | 0 | 209 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 209 | 209 | (no, page_name) | 0 | 0 | 209 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 209 | 209 | (no, page_no) | 0 | 0 | 209 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `iec61850c_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 30 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 30 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 33 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 33 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 17 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 17 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 30 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 30 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no)`
- `(option_desc)`
- `(option_name)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 17 | 17 | (no) | 0 | 0 | 17 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 17 | 17 | (option_desc) | 0 | 0 | 17 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 17 | 17 | (option_name) | 0 | 0 | 17 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |

### `jdxx_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 3 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no)`
- `(option_desc)`
- `(option_name)`
- `(value)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (value) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |

### `mms_rp_cdc_index`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 42 | 2 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 42 | 2 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：idx、cdc
- rd-t1-a-v2：idx、cdc
- rd-t2-b-v1：idx、cdc
- rd-t2-b-v2：idx、cdc
- rd-t3-c-v1：idx、cdc
- rd-t3-c-v2：idx、cdc
- rd-t4-d-v1：idx、cdc
- rd-t4-d-v2：idx、cdc

**全局最小候选键**：
- `(cdc)`
- `(idx)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (cdc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (idx) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (cdc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (idx) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (cdc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (idx) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (cdc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (idx) | 0 | 0 | 0 | 0/0 | 0/0 |

### `nbridge_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 44 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 44 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no, page_name)`
- `(no, page_no)`
- `(option_desc, page_name)`
- `(option_desc, page_no)`
- `(option_name, page_name)`
- `(option_name, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_desc, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_name, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `nr103d_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t2-b-v1 | 41 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 41 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 41 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 41 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`
- `(no, val_type)`
- `(no, value)`
- `(enum_set, max, no)`
- `(enum_set, min, no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, val_type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (enum_set, max, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (enum_set, min, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, val_type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (enum_set, max, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (enum_set, min, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, val_type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (enum_set, max, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (enum_set, min, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, val_type) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (enum_set, max, no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (enum_set, min, no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `nr103ht_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 0 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 10 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `out_time_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 4 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：board、link_no、com_no、protocol_name
- rd-t1-a-v2：board、link_no、com_no、protocol_name
- rd-t2-b-v1：board、link_no、com_no、protocol_name
- rd-t2-b-v2：board、link_no、com_no、protocol_name
- rd-t3-c-v1：board、link_no、com_no、protocol_name
- rd-t3-c-v2：board、link_no、com_no、protocol_name
- rd-t4-d-v1：board、link_no、com_no、protocol_name
- rd-t4-d-v2：board、link_no、com_no、protocol_name

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

### `project`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 14 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t1-a-v2 | 14 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t2-b-v1 | 326 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t2-b-v2 | 326 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t3-c-v1 | 13 | 10 | BROWSE_ONLY | keyless | 0 |
| rd-t3-c-v2 | 14 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t4-d-v1 | 590 | 12 | BROWSE_ONLY | keyless | 0 |
| rd-t4-d-v2 | 590 | 12 | BROWSE_ONLY | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`
- `(no, value)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | (no, page_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | (no, page_no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 3 | 3 | (no, value) | 3 | 3 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 3 | 3 | (no, page_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 3 | 3 | (no, page_no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 3 | 3 | (no, value) | 3 | 3 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 14 | 13 | (option_desc) | 1 | 0 | 13 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 14 | 13 | (option_name) | 1 | 0 | 13 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 14 | 13 | (no, page_name) | 1 | 0 | 13 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 14 | 13 | (no, page_no) | 1 | 0 | 13 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 14 | 13 | (no, value) | 6 | 5 | 8 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 3 | 3 | (no, page_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 3 | 3 | (no, page_no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 3 | 3 | (no, value) | 3 | 3 | 0 | 0/0 | 0/0 |

### `sc_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 8 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_name)`
- `(enum_set, page_no)`
- `(no, page_no)`
- `(option_desc, page_no)`
- `(page_no, value)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (enum_set, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (page_no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (enum_set, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (page_no, value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_name) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (enum_set, page_no) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (no, page_no) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_desc, page_no) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (page_no, value) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (enum_set, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (page_no, value) | 0 | 0 | 0 | 0/0 | 0/0 |

### `scada_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 8 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no)`
- `(option_desc)`
- `(option_name)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (no) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_desc) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_name) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |

### `sg_manage_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 3 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no)`
- `(option_desc)`
- `(option_name)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |

### `sntp_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t4-d-v1 | 17 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 17 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(option_desc)`
- `(option_name)`
- `(no, page_name)`
- `(no, page_no)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no, page_no) | 0 | 0 | 0 | 0/0 | 0/0 |

### `vqc_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 8 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 8 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(no)`
- `(option_desc)`
- `(option_name)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (no) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_desc) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 8 | 8 | (option_name) | 0 | 0 | 8 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |

### `wave_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 3 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 3 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：
- `(max)`
- `(min)`
- `(no)`
- `(option_desc)`
- `(option_name)`
- `(value)`


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (max) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (min) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (max) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (min) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (max) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (min) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (no) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_desc) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (option_name) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t3-c-v1→rd-t3-c-v2 | 3 | 3 | (value) | 0 | 0 | 3 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (max) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (min) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (no) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_desc) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (option_name) | 0 | 0 | 0 | 0/0 | 0/0 |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | (value) | 0 | 0 | 0 | 0/0 | 0/0 |

### `wf_cfg`

| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |
| --- | ---: | ---: | --- | --- | ---: |
| rd-t1-a-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t1-a-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t2-b-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v1 | 0 | 10 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t3-c-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v1 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |
| rd-t4-d-v2 | 0 | 12 | RAW_PK_FALLBACK | keyless | 0 |

**各数据集规范投影列**：
- rd-t1-a-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t1-a-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t2-b-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t3-c-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set
- rd-t3-c-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v1：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips
- rd-t4-d-v2：no、page_no、page_name、option_desc、option_name、val_type、value、min、max、enum_set、config_type、tips

**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。


| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| rd-t1-a-v1→rd-t1-a-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t2-b-v1→rd-t2-b-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t3-c-v1→rd-t3-c-v2 | 0 | 0 | — | — | — | — | — | — |
| rd-t4-d-v1→rd-t4-d-v2 | 0 | 0 | — | — | — | — | — | — |

## 需要业务判断的观察

- 共记录 14 个仅在部分数据集唯一的最小列组合；具体唯一/重复/NULL 状态见逐表表格。
- DC29 已知清单以外的表名：无。
- 含浮点列的全局候选键：无。

本报告仅提供测量事实，不判断哪些表应补为显式键规则。
