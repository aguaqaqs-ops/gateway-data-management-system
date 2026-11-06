# S2b E：唯一生产路径与阶段最终候选

状态：**D 前置通过，按 DC86 启动 E**（2026-11-06）。D 固定产品 `93678f8439ec1393d496182f16ae5049b220242f`、[handoff](p6-s2b-d-handoff.md) `abfe7cb66b`、[独立 GO](p6-s2b-d-review.md) `78411aa40b` 已收齐，06 已释放、D 二角色结束。本节重新创建 **GPT-6.1-Sol/high 实施者、GPT-6.1-Sol/max 独立审核者**；因涉及旧算法与独立预期移交、累计恢复证据、跨节点最终门禁及闭包判定，审核选择 max。按下述范围先收敛删除与工具消费者，再固定最终候选验证，不把 D focused 结果充作最终权威来源。

## 1. 消费者收口与删除

目标是已批准的唯一 Rust 批量路径 `parse → business validation/materialization → canonical projection/hash → IPC`。Python 保留业务 orchestration、ruleset、XML/AST/composite、small metadata/digest 以及真实 IO/恢复 owner；不为语言统一迁移这些职责，不删除仍有消费者的公共 row reader/DTO。

逐项核整体 kickoff §2 的消费者表，并以实际 import/call graph 补缺：上传 FULL 双侧、Preview baseline、History exact commit、repository-ref 两种 artifact policy、pair/identity/ordered 单侧读取、export/import-replay、Submit/T1/PREPARED 与恢复。D 已切的入口只复核差异，剩余入口在 E 替换；同一消费者不保留生产 fallback、旧格式双读或引擎开关。

删除被替代 Python 批量 materialize/projection/hash 实现及只服务其差分的入口、mock/probe。保留已确认的独立 fixed vectors/Contract：删除旧 oracle 前，将仍需保留的预期明确绑定到既有 Contract/golden/旧 oracle 已验证值，不能从新 Rust actual 反写 expected，也不为了测试长期保留第二套算法。按行为与 owner 保留测试，不按修复轮次复制测试矩阵。

D 的 direct RepositoryRef capability 用例可暂用 test-only committed-tables port 适配已有 reference helper，以隔离 metadata/选表策略。fixture 必须补齐显式合法 identity/scope，生产缺 identity/port 仍拒绝；真实 HTTP/C 恢复另有 owner。E 一并删除这些临时 reference 依赖，将必要预期交给独立固定向量或真实 C port，不保留生产 fallback，也不把旧算法复制成长期 test oracle。D handoff 必须列清临时项。

D 首个生产 parser 接线后，旧 parser 已无生产 consumer；为本节删除前的临时差分移交，D 明确登记六项 `gateway_backend.capabilities.table_access.{sql,_sql_reader,_sql_scan,_sql_statements,_sql_types,_sql_values}` 的 temporary unreachable。E 必须将尚需的独立语义预期固定并核实后，删除这六模块、只服务它们的测试辅助/差分入口与六项 baseline；不能通过假 import、长期重命名 oracle 或最终豁免保留。每项删除前核当前 consumer，S2b 最终架构门禁不接受这六项临时记录。

内部 canonical IPC 与 raw/client Parquet 是不同用途；只删除被替代的内部规范表路径。面向客户端的 Parquet、通用 Repository row 访问、原始 SourcePackage 与外层 DDL/export layout 按其真实消费者保留。

已核到工具消费者 `benchmarks/real_dump_journey.py → real_dump_census.py::compare_composite_packages`：后者目前仍导入旧 parser/materialize/projection，E 删除时须同步迁移实际需要的工具调用，不能只检查 application imports。该 helper 原本就使用 production projection/comparison 计算 composite counts，属于跨层一致性检查，不是独立算法 oracle；可接唯一新生产路径，不能将这种同源结果冒称独立 golden。真正固定向量仍按上面的独立预期规则移交；已有 census/已验证结果优先复用，不为此重新生成全套输入或增加双实现完整旅程。

这些实际 CLI 的初始化按 [Rust policy v6](../policies/rust-safety-and-performance-policy.md#4-ffi-and-python-boundary) 复用薄 `bootstrap.compute_kernel.initialize_compute_kernel(threads)`，将 D 的 private initializer 精确允许边迁到该唯一 owner；worker/CLI 显式启动调用，M/control/operation scope 仍归原调用方。不引入通用配置或未来工具框架，不让工具直接访问 private FFI。仅已完成历史阶段的工具须先核真实消费者再退役或迁移；DC79 输入生成器深依赖旧 scanner/statement/literal 的部分单独核原线当前需求，不能复制旧 parser 为永久工具库，也不擅自重做 S1 输入生成或改变原冻结线。

## 2. 收敛与最终验证

日常在 06 对实际删除/迁移范围做 focused/Contract/差分残余检查、静态与必要容器验证。最终候选前收敛全部代码与测试；按 AGENTS 记录最后已验证 image revision/source tree、是否触发重建及理由。不每轮执行全量 runner、完整真实旅程或重新生成输入。

最终 S2b 候选必须覆盖：

- Mapping/业务摘要/诊断/特殊 catalog 与 FULL、MODIFIED_ONLY、DATASET_REPLACEMENT 正确性；W2 结构计数及内容命中不重写。
- IPC handle、强引用/TTL、Archive CAS、精确 commit 回填、T1/PREPARED 冻结，真实 worker cancel/drain/lease_lost/deadline 与资源拒绝。沿 A–D 已验证 owner 按最终差异核对，不机械重做所有中间测试。
- 04 权威 runner 与最终候选绑定的容器门禁；Rust 必须覆盖，其余包按同节点、同 worktree 的实际来源 V 和闭包规则判运行/沿用。包沿用和镜像身份等价分别判断；普通 06 focused 不能冒充 04 来源。
- t1–t3 在 05、t4 在 CT108 完成改动面内的 Preview/History/Submit 生产路径正确性。CT108 忙时协调窗口；若要换节点，先向 Owner 给出具体替代方案并取得授权，不能以性能延期豁免 t4。

各节点分别按有效占用、clean committed worktree、离线缓存和日志规则执行；正式测试不在开发机运行。runner 非零先停并处理失败，不接着计算 carried；最终门禁提交固定后不在运行中修改 worktree、提交或手工 retag 镜像。保留 04 门禁 worktree 至阶段退出合入，以便同节点同 worktree 判等。

真实数据入口沿当前候选的 `vnext/backend/benchmarks/real_dump_journey.py --tier <t1|t2|t3|t4> --scope full`，由受控 uv 入口在相应节点执行；使用既有 `GATEWAY_REAL_DUMP_ROOT` 输入并核绑定，不重生成输入。此处是正确性旅程，不使用原基准冻结 checkpoint/resume、卷或正式计时入口；不以旧整镜像 prebuilt 跳过当前候选的节点本机离线构建。向原线协调 05/CT108 窗口时给出最终候选、实际入口/范围、依据已完成档位估算的占用时长和本任务资源清理范围；原线 STOP 不代表节点已释放。CT108 窗口尚未确认，不能将其计作已预约。

## 3. 退出记录与后续性能复核

E handoff 将最终产品候选、删除/保留清单、逐包来源与闭包、容器 provenance、t1–t4、容量/N/M 配置、恢复/控制证据、未决问题集中交独立审核。设计会话不能自行判实施证据。S2b 的阶段退出记录与附注 tag 按既有退出流程办理，不推送、不改写被审核引用的提交。

W2 30 秒目标及口径保留，完整路径测量最迟 S6；W1 无 CT108 窗口时同样最迟 S6；W3 从 S3 起按原设计取证。未知数值保持 unknown，功能退出不写性能 PASS。原 W4 租约故障由原线跟踪，若当前功能候选出现租约或正确性故障，仍须处理，不能归入可延期性能项。

本节使用上述新建二角色，实施者修改产品/测试，审核者只读固定候选及证据、维护审核文档，明确小问题可直接通信修复后复审。设计/审核可修改各自 owning 文档。额外角色、真实设计冲突或多轮修复不收敛交 Owner；不复用 D 角色，不推送或改写被引用提交。当前进入 E 实施，不代表 E GO 或 S2b exit。
