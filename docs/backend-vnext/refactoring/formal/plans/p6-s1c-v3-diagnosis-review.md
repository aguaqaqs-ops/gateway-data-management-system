# Phase 6 S1c：v3 Submit 失败诊断的审核

状态：**诊断成立。** 根因是 mutation planner 的变更集排序缺陷，自 P3-R7 起就存在，不是 S1c 引入的。修复范围小且局部，符合复核 4 第 5 节第 2 项“甲”的前提。修复放在哪里，由 owner 决定。

## 1. 对象

- 诊断报告 ct108 `/home/dev/gdds-p6-logs/s1c/v3-submit-diagnostic-20261031/diagnosis.md`，SHA256 `c4ec54d3…`。
- traceback 与操作序列 `attempt3/diagnostic-ordering.log`，`59edc2c7…`；最小复现 `attempt3/minimal_reproducer.py`，`1358c911…`；镜像身份 `attempt3/image-identity.log`，`369db727…`。审核者在 ct108 上核对了 SHA256。
- 诊断栈与副本卷已删除；fb534、20e634、1030b 的九个保留卷仍在，节点无容器。

## 2. 核对

| 项 | 结果 |
|---|---|
| 异常位置 | `contracts.py:805` `validate_change_set_ordering`，由 `_changeset.py:47` `build_change_set_closure` 调用，与 traceback 一致 |
| 缺陷 | `_changeset.py:109` `_patch_mutations` 按主键顺序遍历父表行，DELETE 与 UPDATE 交错输出；校验器要求同表内按 DELETE → UPDATE → INSERT 分阶段，每阶段内按主键排序 |
| 失败表 | `b1_n11_iec104_syx_list__x2`，PATCH_DML，父表 9828 行、目标 9822 行；7 个 UPDATE（主键 9816–9822 一带）之后接 6 个 DELETE（9823 起） |
| 排序口径 | planner 的 `key_bytes_for_ordering` 与校验器都用 `canonicalize_json_value(key.to_document())`，口径相同。修复只需分阶段输出，阶段内顺序不变 |
| 来源 | `_changeset.py` 最后一次修改是 `e09ff32cc3`（P3-R7）；`p6-s1b-exit..V` 没有改动 mutation planning 与 publication adapter |
| 为什么 v2 成功 | 正向变化中对应的行是 INSERT，UPDATE → INSERT 合乎顺序；反向（v3）变成低主键 UPDATE、高主键 DELETE |
| 影响面 | 任何 PATCH_DML 表，只要某个 UPDATE 的主键小于某个 DELETE 的主键就会触发，不限于回退。失败发生在纯计算阶段，不会向 Repository 发起导入，没有数据损坏，表现为 Submit 稳定失败 |

补充：复核 4 预期 v3-submit checkpoint 含失败状态。实际上“step 之前的 checkpoint”只保存到 v3-preview 结束、operation 创建之前，这是该机制的正常含义，是复核 4 的表述不准。诊断改用失败运行卷的只读副本，原卷 SHA256 不变，做法合理。

## 3. 修复要求（无论放在哪里）

1. `_patch_mutations` 先收集 DELETE、UPDATE、INSERT 三组，各组内保持现有主键顺序，再按 DELETE → UPDATE → INSERT 输出。`_rebuild_mutations` 已满足这个顺序，不改。
2. 测试在 `test_mutation_planning.py` 中按业务行为命名，只设一个权威 owner：
   - 用 `plan_import_mutation` 或 `build_change_set_closure` 的公开入口，覆盖“低主键 UPDATE 加高主键 DELETE 加 INSERT”的形态；
   - 断言闭包通过校验、三组顺序与内容正确，渲染出的 DML 顺序与之相同。
   - 已有 Hypothesis 工具时，可加一条属性测试：任意前后快照生成的闭包都通过 `validate_change_set_ordering`。
3. 变更集 digest 对受影响的形态会变化。项目没有兼容要求，同步更新相关 golden。
4. 同时在 `recovery.py` 的 PURE_RECOMPUTE 兜底分支用日志记录异常堆栈（只写 worker 日志，不进入 diagnostic 与 API），使下一次此类失败能直接定位，不另立机制。

## 4. 放置建议

- **甲（建议）并入 S1c。** 修复约 20 行加测试。并入后，ct108 的三节点完整旅程一次就能同时证明 S1c 与本修复，基准仍以 `p6-s1c-exit` 为起点，DC65 不变。需要 owner 决议记录这次 S1c 范围扩展（拟 DC69）。
- **乙 单独任务。** S1c 先补齐两节点旅程再 exit。修复另起短任务，基准起点改为它的 exit tag（DC65 修订）。ct108 要多跑一次。
