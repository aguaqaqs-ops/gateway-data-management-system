# 人工联调：审核结果复用与空基线降级

记录时间：2026-11-13。来源为 CT110 `gw-dms-08` 单设备 A 人工联调，非正式测试证据。源码临时分支 `gw08-dual-env`，调查时 HEAD `b985a6496587e36014a7eea5349b3d807c562844`；运行中 A 的 `production.py` 与 `compare_jobs.py` 已分别按 SHA256 核对，与该工作区文件一致；其余运行源码未逐项核对。

## 后续需求：审核直接使用 Preview 结果

Owner 要求后续审核浏览直接使用对应提交的 Preview 阶段结果，不重新发起差异计算。当前工作台只传 submission ID，审核页每次创建基线到提交的 History compare；Preview 属工作区 scope，审核者可能无权访问。实施需设计提交与不可变 Preview 结果的绑定、审核者的授权读取、结果生命周期及完整性，不能简单放宽工作区权限。FULL 上传的 Preview 有基线→原始和原始→修改两个比较对，当前审核 History 是基线→提交；两者语义并非总相同，需在实现前明确审核显示的比较对及提交后引用的保留策略。重复打开应读取提交绑定的结果，不再为此启动比较任务。与现有 FE kickoff 中审核使用 History 的约定冲突，以本次 Owner 新要求为后续变更方向。

## 空基线 History 错误降级

现象：t4 v1 经 MODIFIED_ONLY 上传，Preview 表显示整表新增；提交 `sub-a003ffc4-07a5-4921-bcad-1653ba1bd7f7` 之后，审核 History 的空基线→提交表错误降级。一次实际 surface 共 312 表：264 表 `DEGRADED`、48 表 `ADDED_TABLE`；其中 144 张带 `ORDERED_DIFF_UNSUPPORTED` 和 `TABLE_READER_UNAVAILABLE`，120 张带 `TABLE_READER_UNAVAILABLE`。例如 `b1_n11_iec104_syx_list`（当前 9822 行）被降级。另一次 surface 有 162 张降级，结果受读取需求/缓存状态影响；未断言所有运行均有同一数量。两个 surface 分别保存在 08 的 be-export 对象 `53daeabfd4a05975e951b5bf5d8981bb51ab22368dc91c96237106eb1e12f617` 和 `619a30af438763d60228dfb76e0cf56e315f9f528431018bd17d349efcd90e7b` 的 payload。

静态路径和现场证据指向读取需求规划与单侧比较不一致：

1. `application/history/compare_jobs.py` 的 `_ensure_history_demands_once` 按 `comparison_row_demands`、导航需求和导出缓存缺失决定哪些表加载 reader；导出缓存命中不会单独要求 reader。现场日志显示某次 312 个导出缓存命中，仅 14 个表有读取需求。
2. `capabilities/comparison/production.py` 的 `_task_arrow_inputs` 在 before/current 任一侧不存在时返回空，故单侧新增表不产生比较行读取需求。
3. 实际 `_compare_task_native` 对单侧任务调用 `_compare_task_metadata`，而 `comparison/ordered.py` 与 `comparison/standard.py` 的 `_compare_single_side` 在现存侧 reader 缺失时返回 `TABLE_READER_UNAVAILABLE` 降级，即使表描述符和缓存的整表导出存在。

这解释了空基线场景中已有完整表却被标成内部错误：导出缓存命中使 reader 无需为打包加载，而单侧比较仍要求它。此前端的“比较时发生内部错误”映射了后端诊断，不应误判成 UI 独有问题。以上是代码与现场证据支持的根因分析，尚未用隔离 focused 测试验证因果，也未修复。修复应统一单侧任务的 reader 前置条件与需求规划，明确仅凭 descriptor 及可用整表产物能否判定新增/删除，并覆盖有序、标准及导出缓存命中/未命中；避免为整表新增引入无必要的逐行读取，保持内存与容量约束。验证需在专用测试节点的 clean 已提交 worktree 上进行。不要把直接复用 Preview 当作修复 History 正确性的替代。

当前 A 提交仍待审核，未归档；t4 v2 尚未上传。调查前为了打开审核页曾创建多个 History 任务，单 worker 队列与耗时不代表单次性能基准。空 `.pmc` 文件仅为目录校验补充，t4 原包 SQL 与 XML 未修改。

后续对另一旧代码库的逐项对照、初步适用性判断与源码索引见 [比较正确性参考清单](comparison-correctness-reference-inventory.md)。
