# DC63 与 V5b 剩余分段测量的最小补缺方案

2026-11-07，p6-backend-design。执行依据为 DC62 §4、DC63 §1、DC66、Owner A 分版本参考及连续完成授权。本项属于原已授权旁证，现有实施者与接续审核者直接闭环；不新增角色、逐摘要 GO 或阶段 exit 权限，不重跑已关闭的 W4-FULL/STRESS。

## 实际缺口与目标

DC63 要求普通 t4 的 checkpoint 读取与 bundle 子段拆分，并说明 S1b 将整表 Parquet 导出移入 `materialize_inputs` 后的成本迁移。现有 API/DB step 时间保留其实际端点，不能代替 worker executor 内 `perf_counter` 边界。W4 合成 631 表诊断也不能填为普通 t4 312 表的同口径数值。

reference JSON 中的 21 个 Preview/Submit selector 是既有工具字段，不是 21 次旅程或 21 项新增性能门槛。按下述最小覆盖补缺，同时逐项标明这些 selector 的实际来源、定义变化或未测原因；不能为填满字段而重构产品、填零、作粗段相减或修改原 state。历史 e52/af559 只作定义和参考，不作为 9704 实测。

| 最小覆盖 | 实际记录及解释 |
| --- | --- |
| 普通 t4 v1/v2 Preview | checkpoint 读取、pair pipeline、bundle、finish 的实际当前边界；列清 readback、ready closure 与嵌套子计时归属。边界已迁移时记录新位置，不能把旧范围冒称未变化。 |
| 同一两节点普通 t4 History | 当前 checkpoint/绑定读取与 bundle 的实际子段，以及 `materialize_inputs` 中整表导出/绑定成本所在位置；保留现有 API/step 粗段作背景。不新增冷/热、refill、H2/H3 的诊断矩阵。 |
| Submit 与 V5b C/D | 对 v1/v2 的 build input、冻结行读取、projection、snapshot、parent、plan/render、publish 等现有边界按可复用程度取真实计时；worker 内总段与 DB step、独立 capability 总段分别记录，不强行等同。已删除或无直接对应的内部边界说明原因。 |
| V5b A–D | 原 A 完整基线 commit 物化、B pair/records/bundle 与回读、C Submit build input、D checkpoint 序列化/读回/pin；保留 wall/CPU、输入计数、缓存状态及嵌套关系，不重复加总 I/O 子计数。 |

目标是取得上述必要测量并建立新旧语义映射，不要求证明所有历史残差的唯一根因。S1a 未保存同口径 History 子段、规则或阶段范围已改变等限制如实说明，不伪造逐项差值或性能 PASS；可比较部分作对照，其余说明可解释范围与仍未消除的差距。

## 一次隔离诊断，复用其准备状态

1. 先在 CT201 核对 e52 的计时定义与 9704 实际调用位置，形成简短边界映射。不得把旧九文件诊断实现直接 cherry-pick 覆盖当前产品。优先沿现有非候选诊断方式，仅增加阶段计时/计数；不加逐行 profiler、轮询守护或持久 evidence 状态机。
2. 采用原普通 t4 v1/v2 包及当前真实规则，记录实际 SHA、表/行数、规则和节点。优先复用已认证的合格素材；需要 worker 内新子段时，以一次必要的普通 t4 v1/v2 两节点诊断链覆盖上述缺项。现有旅程若必须经过重复上传等正常前缀可保留，不重跑 t1–t4 全矩阵、2× 或 W4 场景。
3. 诊断以 9704 为产品来源，插桩/overlay 或专用镜像另记完整身份和差异，不修改冻结 tag、在途 worktree 或正式 V_ref 的产品内容。读写仍走实际生产路径；计时不得改变原异常、返回、lease、GC 调度、artifact 或事务语义。若实现需要改业务/Contract，先报告具体冲突。
4. 在同一 CT108 独占时段复用该诊断准备出的合格 v1 commit/隔离服务，运行现有 V5b A–D 工具及独立 scratch，避免为 A–D 再起一整轮旅程。旧 retained 栈不因取素材重新启动；服务/输入不满足时用本次独立新项目准备。明确缓存状态，不把正常已有缓存称冷启动。
5. 本地准备和必要 focused 在 CT201/05 按既有分工进行；实际诊断仅在 CT108 当前正式测量结束、现场可用并取得有效占用后执行，不与 FULL/STRESS 正式计时重叠。token 等凭据不进日志或 Git。

**诊断专用预置镜像绑定（2026-11-07）：** bbe启动预检发现，诊断Compose也参与canonical build definitions，当前RS helper计算build-input revision为`3456bd7fbbd6a6c7ae807303a54f5548a4136a7f`，冻结目标label为`4497ded8ff3a9156bbe4c7a75ba44ae9e4675792`；两者source-tree均为`sha256:31972029672961ad00d2a2da022f4d1430cb60157a2d944246483195a9344027`。普通startup在prebuilt判断前先ensure RS，直接复用会触发冻结tag重建，故先停在业务启动前。该build-input差异如实保存，不能靠alias、重tag或宣称两个revision相同消除。

允许仅在本非正式诊断入口增加明确的“诊断HEAD/Compose与冻结目标镜像”映射：启动前用实际manifest固定诊断身份，并确认当前RS source-tree仍等冻结产品、三镜像实际config digest/全部有序DiffID/目标labels均与已审冻结对象精确匹配。只有本诊断入口在该验证成功后消费预置镜像，不调用build/pull；普通门禁、共享harness及正式V_ref的身份比较保持，不新增通用skip或产品回退。实际缺失或不符即停该运行并按DC80处理，不自动重建、取网或替换冻结tag。实施者完成最小接线和真实调用路径的必要focused，接续审核者集中核映射/实现及原已核关键预算一次后直接沿原范围接续，不再申请Owner、逐摘要GO或协调回执。诊断身份与冻结镜像身份分别交付，该映射不用于普通门禁carried或冒充单一正式版本。

## 预算、验证和交付

实施者在启动前按实际选定步骤一次给足保守操作、局部 I/O、工具及总工作/清理余量，接续审核者集中核关键映射和预算。不得把原 V5b 42 分钟或旁证 3–5 小时规划区间直接作保护硬限，也不在运行中滑动加时。复用现有有界 session/清理和保卷机制，不新增监控；普通工具修正不重开 GO。

必要 focused 只核诊断 wrapper/输出的实际调用契约、阶段归属、异常传播及报告提取，先在小输入发现工具错误，不为不进入产品的诊断触发整轮权威 runner。若实际 container 入口/overlay 需额外接线验证，按真实边界做最小验证；诊断镜像结果不代替正式产品门禁。

交付包括：边界映射、一次诊断及 A–D 的真实输入/产品与诊断身份、UTC/节点/起止 HEAD/exit、原始输出与 SHA、分段数据及限制说明。原已完成测量继续保留原来源，诊断数值标为诊断，不回填成正式 operation elapsed；正式参考线的最终 04 门禁仍只针对已批准产品和必要正式工具。实施者维护结果与 handoff，接续审核者独立核实际证据，设计不代判。
