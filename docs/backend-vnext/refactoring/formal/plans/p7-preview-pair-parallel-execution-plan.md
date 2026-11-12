# Preview 固定双 pair 并行实施计划

状态：与 [详细设计](p7-preview-pair-parallel-design.md) 配套的待审计划；仅设计交付，未开始产品实施、测试或部署。起点 main `64b89505f4` / `p7-s2b-exit`；实际实施前重核最新 main 与 FE4b 合入差异，不修改旧 exit tag。

## 1. 边界与前置

目标是一次 Preview 最多两个 pair 同时计算，不是更多 worker 或 S3 调度。单 pair 与双 pair 共用流水线，双路固定分配、不借用对方空闲执行位置。详设提出两线程、N2 总并发、静态内存分额及独立缓存会话；这些工程选型经独审/Owner 确认后才成为实施基线。

可以在 FE4b 合并前完成设计、独审和经授权的后端实施。最终候选需明确绑定的 frontend/backend revision；FE4b 合并引入受影响后端树、Contract、容器或 harness 变化时重新判断验证范围，不能口头 carried。

风险初评为 A/B 范围：资源所有权、并发产物、取消/失租和结果发布可能影响正确性；协调者按比例化政策正式定级。一个设计/协调会话；A/B 包新实施上下文和独审，内聚包可按现行规则合并。独审与实施者使用不同模型家族。审核意见、handoff、提示词和日志在 `/home/dev/gdds-stage-exchange/p7-preview-pair/`，不提交过程报告；阶段末入库一页总结。遵守执行时有效的 AGENTS/测试政策及 Owner 明确节点约束，不从历史文档推导新授权。

## 2. A：固定执行路径与资源准备

先做静态接点核对及最小可验证原型，不跑完整真实旅程。

- 列出 `_assemble_preview` 到 Rust comparison/probe、risk、surface、snapshot export 的实际调用链；确认哪部分需要 GIL、哪部分进入共享 Rayon 池，识别 Arrow 内部线程。
- 固定两 lane adapter：线程内 context、scratch、Metrics、事务 adapter、输入借用及结果转移 API；保留协调方唯一 LeaseSession。
- 从真实 FULL 计划及现有预约公式推导 R、B1/B2、metadata/native 必需下界，核 32/8/M24 可行性。原始 RSS 仅辅助，不当作预约下界。需要专用节点解析/运行时取数时先授权该 focused 范围，不在开发主机执行。
- 拟修订 owning Contract：operation 资源生命周期、worker N 的全局上限、comparison cache 生命周期及统计口径；不改业务 digest。变更 Contract 时标清目标，产品接入后再标生效。
- 对 Rust comparison/probe 调用改为可在调用线程执行的单份内核入口；不新建 pair 池、不让 N1 公共池把 N2 两路重新串行化。

交付：接点/所有权表、预算静态结论、设计修订、线程重叠最小证明与独审。若两线程无法在局部修改下真正重叠，或预算方案无法覆盖目标输入，停止依赖实施，回设计会话；不自动改成两个进程或翻倍 M。

## 3. B：lane scope、缓存与生命周期

建议主要代码位置：`application/kernel_execution.py`、`capabilities/table_access/kernel.py`、`capabilities/comparison/production.py`、`application/pair_pipeline.py`、必要的 scratch/metrics adapter；可新增一个仅服务 Preview 的固定两路执行模块，不建设通用 scheduler。

- 实现父预约/子分额的建立、异常回收、输出 charge 转移；同一父 scope 在并行期间不被 lane 修改。
- 每 lane 创建只包含自身计划的 ComparisonTaskSession，独立 native/Arrow handles 与缓存候选；不用共享 remaining_uses/pending_risk。
- 保留现有持久缓存协议，逐线程短事务；同 key 并发 miss 的等价发布、损坏项条件失效、pins 最终释放与 cleanup 借用覆盖所有读写路径。
- 公共 Parquet 导出留协调方；核 pair 内确需导出路径，避免无条件预导出全部表。
- lane 仅抛出/返回内部结果，协调方独占 terminal publication；用共享停止事件传播真实控制和 peer failure，不能把失败当取消。

交付：focused 结果、边界修复与原审 GO；不在每个提交重复全量门禁。

## 4. C：Preview 接线、统计与回归

- FULL/N2 固定两个线程各一个 pair；MODIFIED_ONLY/N1 使用同一流水线的单执行路径。
- 协调方启动、刷新控制、等待两路退出、稳定归并，再生成 closure/bundle、核控制并 READY。异常路径关闭顺序与正常路径一样明确。
- 统计每 lane 收集并按固定顺序有界合并；区分 pair 工作时间之和与 Preview 墙钟。默认视图、导航、诊断和正式摘要不受完成顺序影响。
- 删除被取代的 Preview 共享会话接线；History 若仍使用跨 pair session 则保留其真正消费者，不为清理而误删。
- 明确 N2 资源档模板与适用部署，产品默认 N1 不因本次代码存在而自动更改。

交付：以下测试矩阵、代码独审；之后才固定最终候选 V 做集中取证。

## 5. 必需 focused 测试矩阵

| 边界 | 有效证明 |
| --- | --- |
| 1/2 pair 分派 | 单 pair 不启动额外 lane；双 pair 同时进入且峰值 active=2，不能出现第三 lane |
| 真实计算重叠 | Rust adapter/native 重任务两路重叠；不能只用 sleep 或 Python mock 证明 CPU 并行 |
| 输入与结果 | FULL/MODIFIED_ONLY、初始基线、项目身份变化、空/无变化、standard/keyless/ordered，保持固定预期与 digest |
| 稳定顺序 | 强制 A 慢/B 快与反向顺序；bundle pair 顺序、默认视图和诊断不变 |
| 预算 | 父输入计费、两路增长前拒绝、半额边界、输出所有权转移、异常清理后无负数/漏账/提前关闭 |
| 缓存 | 双 miss 同 key、冷/暖混合、损坏项和竞争替换、pins 保留至最后消费者、cleanup 不破坏活跃输入 |
| 取消/失租/drain | 一路 native 活跃另一路已完成；全部退出前不发布/释放；真实原因不被 peer-stop 覆盖 |
| 失败与恢复 | 一路失败、双失败、线程启动部分成功、结果归并失败、join 未完成；无半 READY、无后台孤儿继续写 |
| 指标 | thread-local 绑定、missing/null、总条数/字节上限、合并顺序；累计耗时不冒称墙钟 |
| 原消费者 | 单 pair、History、Submit 受公共改动影响的 focused 回归；不改其业务生命周期 |

同步机制测试用 Event/barrier，时间预算敏感用例标 serial；pure tests 不引入 Dolt。只有需要真实 DB/文件生命周期/容器隔离的用例使用相应 integration/Compose owner。线程停止测试不得留下卡住的非 daemon 线程；测试进程监督与产品行为分别记录。

## 6. 最终真实验证范围建议（DC33 待确认）

不把历史 t1–t4 数值当本轮 N2 通过。使用真实来源与原始输入摘要，禁止把同一设备改名作为第二设备。本专项只需一个设备的一次双 pair Preview，并非多设备容量证明。

建议范围：

1. 调试：t1 FULL 小范围及一份能暴露预算边界的真实 FULL 输入，问题收敛前只跑相关步骤。
2. 最终功能：t1 完整上传→FULL Preview→Submit→Review→Archive→History，另覆盖 MODIFIED_ONLY；t2–t4 用建立合法 baseline 后的真实 FULL Preview，N1/N2 对照正式结果及 digest。若输入身份导致 dataset replacement，要记录实际路径，不把它当 detailed 双比较证据。
3. 最终计时：选择 t3/t4 中能代表真实双 pair 重任务的一档，固定同一节点、CPU/内存、输入、基线及候选，每档一次预热、三次测量；另取小 t1 单 pair 回归。N1/N2 唯一有意区别是执行并发配置，不能一边暖缓存另一边冷缓存。
4. 缓存模式分别报告冷/暖；冷档用隔离测试根建立同等起点，不清共享节点缓存或真实业务库。暖档核 cache 命中和实际工作量，不用全缓存命中证明重计算并行。
5. 记录 pair 重叠、Preview READY 中位数/范围、worker cgroup/RSS、全栈资源采样、CPU 秒/实际并行度、OOM/退出和完整配置。容量成功与性能收益分别给结论。

固定分额可能使现有 M24 不能覆盖 t4，A 包应先暴露，不到最终旅程才盲试。必要增预算、变更 DC33 或启用 N2 由 Owner 对具体清单确认；不自动提高 envelope、压缩 reserve 或试多种配置直到通过。

N2/N1 一致性承担本范围的 D24 责任；不冒称全产品所有 N>1 档均通过。既有 t4 D23 参考移交按 owning 阶段核销，不在本专项静默取消。性能目标由首次对照证据形成建议，接受前不承诺 Preview 减半。

## 7. 集中门禁、合入与退出

- 实际选定的 clean 已提交 V 在专用节点运行；依赖/镜像离线预填充，来源、config digest/RootFS DiffID、日志、HEAD、UTC、hostname、exit/SHA 齐全。
- 预计必跑 Rust + backend 权威包；若 Contract/客户端/RS 等实际闭包变化，按当前按包规则扩展。当前项目最终/发布门禁仍须全六包，不以本专项包选择替代。
- 涉及 executor/线程退出与容器进程边界：最终 HEAD 构建并跑相应 Compose 旅程，覆盖取消、drain、失租和退出后无活动执行者。N2 配置及 CPU/内存接线在容器中实证，不能只做 host focused。
- runner 非零停止本次及依赖验收，保留失败来源；只修复具体原因再执行适用入口，不从失败整次抽取通过包做 carried。
- FE4b 已合并时，使用合并后最终后端树与前端配对，补最小实际 FULL Preview 展示检查；因后端内部并发不要求无差别重做全部 FE 截图，但原有 FE4b 门禁责任不减。
- 阶段末全范围独审检查代码、Contract、真实重叠/一致性/容量/性能及最终闭包/镜像绑定。Owner 确认适用 N2 部署档和任何偏差后办理本地退出；tag 建议 `p7-preview-pair-exit`，未授权不推送。
- 不重跑已在合格最终 runner 中完成的相同 Compose 旅程；carried 必须满足实际同节点/同 worktree 闭包规则，不能用 docs-only 名义口头沿用。

## 8. 设计交付与实施授权区分

本轮交付这两份入库草案及本地文档提交；不启动角色队列、不占测试节点、不修改产品默认配置，也不宣设计 GO 或阶段 exit。下一步是独立设计审核，重点审资源分额、N2 执行上限、缓存/pins 生命周期和验证范围；审核修订收敛后提交具体实施及 DC33 清单供 Owner 确认。
