# S1b 逐尝试摘要与 N=2 核对设计入口

2026-11-10；落实 P7-D21–D24，不替代 S1b 全部占用/只读查询详细设计，不授权提前实施 S1b，也不收窄其他 P7 范围。

## 1. 记录位置和 schema

摘要属于可丢弃诊断，不是业务事实，不进入任何 digest、checkpoint 或 business commit 事务。采用 S1a metadata/telemetry 位置下独立诊断 SQLite 的一条 attempt 记录，按现有 scope 授权查询/导出；表数组作为该行 JSON 字段，不增第二套事件流水。每次尝试一行，重试独立 attempt；失败、取消及部分结果尽力记录，进程硬崩可缺失，查询明确标 unavailable，不增加 durable receipt/补写恢复机制。替代 `s3_pair_metrics`，不永久双写。

| 字段组 | schema 与语义 |
| --- | --- |
| 关联 | schema_version、environment/group/repository、operation_id、attempt_id、程序/规则版本、输入身份、有效 N/M/E/reserve/W/K、冷暖及观测来源；不写原始 SQL 或私有路径 |
| input | table_count、total_rows、max_table_rows、sql_bytes、changed_tables、changed_rows、ordered_rows：非负整数或 null。行数取本次当前输入表描述符；SQL 字节取输入字节长度，多文件求和；变化计数沿用 surface owning 口径，不二次解析/扫描 |
| duration_ms | parse、materialize、compare、risk、export、bundle、rs_import、finalize：单调时钟 elapsed 毫秒，未执行/未知为 null 并带缺失原因；有已完成部分时标 partial。嵌套、并行段明确窗口，不把各段相加冒充总 wall time |
| caches | canonical、comparison、export、risk_candidate 各层 lookups/hits；未知为 null，分母为零时命中率未定义。comparison 可另记 cache_restores，不能把 lookup/restore 混称 hit |
| tables | 按表名确定序的数组：name、comparison_mode、before_rows、after_rows、changed_rows。新增/删除表的缺失一侧行数为 0；未知为 null；比较模式取实际执行结果，不推测 |
| bound | 首版 tables 上限 1024，超出保留前 1024，记录 tables_total/tables_truncated；不为诊断拒绝业务输入。t4 约 312 表可完整容纳。具体行大小、总容量与保留配置由 S1b 全设计核定，达到上限可丢诊断并显式标缺失，不阻塞业务 |

不为这些字段新增一次数据扫描、跨服务私有路径访问或深度硬件采集。按表数组只拷贝产品已生成描述符/统计。S1b 全设计补齐 SQLite 保留/容量上限、权限/分页/导出 DTO、可用性与缺失语义；原设计要求的资源观测和限期曲线继续保留，D3 未定不能提前删除。

## 2. 计时与计数接点

现有 `application/pair_pipeline.py` 的 `s3_pair_metrics`、`capabilities/comparison/production.py` 的 `ComparisonRunMetrics` 为 comparison/risk/surface 与缓存统计来源。复用 `cache_hits`、`persistent_cache_lookups`、`cache_restores`，逐字段核对内存命中与持久恢复口径，不能简单相除构造误导命中率。surface 导出窗口须标清与 export/bundle 的重叠。

解析、物化、bundle、RS 导入、finalize 当前无完整计时；建议在其现有调用边界记单调起止时间，RS 导入先记客户端端到端窗口并注明含网络/等待，不宣称 Dolt 内部耗时。canonical/export/risk_candidate 在现有查找/命中分支记普通计数。Owner 已确认 [流程规格 §6](p7-gate-and-stage-workflow-design.md#6-来源冲突的已确认处理) 的解释：允许上述普通计时/计数，不增加扫描、profiler 或采集服务。

## 3. N=2 真实核对与参考点

S1b 退出安排 t1，同一节点（优先 05）、同一提交/输入/规则、相同业务初态与冷暖条件，各运行 N=1、N=2，除 N 外资源参数固定且符合 envelope。比对正常生产路径的正式结果和全部适用 digest，诊断时长/资源值不参与相等判定；任一失败或不一致不得开放 N>1。若既定验收范围无法容纳，记录原因并交 Owner 决定范围，最迟 S5 且开放调整之前完成，不能只把延期当通过。

将 `real_dump_journey.py` 中固定线程数 1 的配置生成与资源 guard 一并参数化，默认仍 1，guard 核实际 N 等于请求值；不得只改启动环境而放松核对。真实数据不因本项增加合成放大或正式性能测试。独立重复运行须建立等价初态，不用第二次幂等命中代替 N=2 实际执行。

阶段退出原本要跑的 t4 旅程导出摘要至阶段交接区 `reference/<sha>/t4/`，携带输入身份、配置、冷暖、正式结果与原旅程日志引用。比较同输入变慢时也核配置和硬件条件；参考点非速度门槛，不额外跑一套 t4。真实范围变更仍按 DC33 确认。

## 4. 试运行现象到参数映射

S5 操作说明交付以下映射；每次按硬件余量与既有约束小步调整并保存摘要，调整不能突破资源预算、写入和租约 Contract。N>1 先过 §3。

| 现象 | 含义及动作 |
| --- | --- |
| 排队长，CPU/内存有余量 | 检查并发槽位，增加 W/K；核整机各组预算及 RS 限制 |
| 比较/解析占单任务耗时多数，CPU 有余量 | 内核计算瓶颈，核 N=2 正确性后增加 N |
| 准入预算拒绝频繁，实际内存远低于 E | M 可能过紧，在 E/reserve 约束内增加 M |
| 实际内存接近 E 或 OOM | 增加 E 或减少 K，并核机器总余量；OOM 是功能问题 |
| 风险段占比高 | 调资源参数不能解决，按 DC47 重开条件评估风险热点进 Rust |
| RS 导入占比高 | Dolt 写入瓶颈，单独立项分析，不自动扩大本轮范围 |

默认不优化；新增机制须列真实操作累计耗时占比、预计收益与机制成本，适用比例化政策 §5。最大累计耗时阶段处理后，下一项需新机制且仅惠及少数操作则停止；低命中缓存列为删除候选。真实操作因期限、租约、内存失败须按功能缺陷处理，不以撤回时间目标豁免。
