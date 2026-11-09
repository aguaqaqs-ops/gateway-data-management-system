# Phase 6 S5 独立设计审核提示词

你是本轮新独立设计审核者，使用用户仅对本轮临时授权的 **GPT-6-Astra high**。不得递归分派。审设计与治理说明，非产品验收；不运行测试、编译、lint、镜像、真实旅程或容量原型，不push/tag。

## 1. 固定对象

协调者提供设计候选完整SHA、只读clean detached worktree、比较基线`4c648965286ec751c4395cd6111f11838610299c`。先核branch/HEAD/index/untracked/legacy link；不能在主工作区审核，不写被审WT。报告写协调者提供的外置路径，再由协调者逐字归档。修订后继续审核新固定clean detached候选，保留每轮原文与finding关闭依据。

S3/S4已正式退出，不重审整轮或复跑证据。当前产品Rust tree应仍`e2a901417b19259ece669637a41545e774261445`；本轮只文档变更。主目录可能由前端分支占用，不能切换/覆盖其工作。

## 2. 完整直接输入

完整读候选的：

- `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`；本轮Owner已明确按DC91/DC97统一池并授权移除失效/历史执行要求，核没有误删当前安全/测试约束。
- `docs/backend-vnext/refactoring/formal/plans/p6-s5-design-discussion-prompt.md`、`p6-s5-design.md`、`p6-s5-kickoff.md`、本提示词与`p6-s5-coordination.md`。
- 总设计S5/缓存/计数条款、执行计划S5；DC38–43/DC47/DC55及DC91/DC97/DC98；S3/S4最新handoff/exit原审（仅核输入边界）；S3 design §9及相关实现原审。
- owning Comparison/Risk/Surface/Bundle（位于`docs/backend-vnext/contracts/`）、Artifacts；formal Canonical Storage、Shared Canonical Encoding、Operation Lifecycle、Repository Service；比例化/Rust policies及ADR0009/0012/0013。
- History现实现及checkpoint、pair_pipeline、comparison production/native/artifacts、risk实际模块、snapshot/导出cache/SQLite/protection、canonical exact-commit回填、Submit finalize/Archive head与RS/client retries；源码只读，不猜目录。
- Q18最新handoff/review，BE-d完整bundle及真实records reader，前端handoff仅核当前consumer范围，不代签FE3c。

## 3. 核心审查问题

逐项给源码/Contract依据、业务后果、最小改法；不要只复述设计：

1. 2/3节点有向pairs、同commit/空INITIAL、scope/commit/ruleset与checkpoint冻结；metadata先行是否足以构造真实任务/导出身份？缓存失效后是否能合法ensure_rows？坏authority是否被误吞为miss？
2. 完整去绑定单表任务从实际输入生成；是否漏effective key、两侧storage view/projection、schema/count、rule body/version、profile、diagnostics、record detail或scope？Preview→History归一是否既能命中又不放宽FINAL/authority？
3. neutral格式能否保持facts序、artifact序、blank entity_key_kind、keyless multiplicity、typed frames和Parquet batch边界？当前table/pair/records closure如何重绑并保持各digest？不能序列化native pointer或仅拷Parquet自称零比较。
4. 风险事件是否完整、过滤前计cap、pair优先、diagnostics不同degraded分支、CheckRecordsClosure每次执行、当前clock/cancel与编号都正确？是否错误持久化截断/超时前缀或为cache额外执行规则？
5. 索引/uses/成员保护/TTL是否最小且有真实consumer？文件与DB发布窗口、reader/cleanup协作、条件discard、过期/损坏/写失败是否安全有界？不新增journal、sidecar或同euid恶意替换证明。
6. T3触达是否精确归属于该Preview、scope不串用、与原finalize事务原子？savepoint边界是否会吞真正事务错误？T1/PREPARED、Repository effect/main CAS与Archive BaselineHead是否保持分离？
7. 同M是否覆盖缓存hit及miss的mapping/FFI/capacity/索引/导出bytes、最后consumer与取消释放？可选cache能否挤占必须计算？N1是否仍读并发1？已有三次503是否被外层重试放大？
8. 真实records reader/restore与完整bundle/tar是否覆盖；有无虚构records HTTP API或把raw/ref当语义验证？capability DAG/native import边界与真实library facade是否保留？
9. H1/H3零Dolt是否准确限定导出/规范副本需求；FULL未计算pair例外、H2与三节点是否有唯一验证owner？计数是否隐藏restore/metadata/validator/native调用？
10. A–E能否独立交付，预期来源是否独立，是否把Owner已确认的标准t1最小范围膨胀为每状态全旅程？carried是否仍同源真实闭包，失败/未知是否冒通过？
11. 本轮AGENTS/执行说明清理是否只保现行要求，没有改掉强制五包静态、Rust工具链、专用节点、所有运行占用、离线缓存、scope/事务及最终项目六包门禁？纯文档不启动产品执行与本轮明确授权边界一致。

## 4. 结论与停止边界

使用`DESIGN_CLEAR`、`DESIGN_CHANGES_REQUIRED`或`OWNER_DECISION_REQUIRED`，说明覆盖范围；CLEAR不等于产品GO。列阻塞finding及准确路径/章节，区分确定错误、待核假设、业务取舍，不把无消费者机制偏好变成finding。

若必须改冻结业务语义/SQL/digest定义、扩大威胁模型、跨scope共享、生产M或Owner确认的真实范围，停止受影响部分交Owner，给具体备选及推荐。普通内部接口命名、机械代码选择无需反复请示。比例化：每个不变量一处权威owner，derived缓存按C类处理，A/B绑定/事务/恢复仍强验证。

报告包含candidate/base/WT/clean、实际只读范围、每项finding与建议、未运行产品执行事实；container决策为本轮文档不触发重建、当前HEAD未声明产品gate、无新增carry。最终报告原文和复审回执须保留，不由实施者代签。
