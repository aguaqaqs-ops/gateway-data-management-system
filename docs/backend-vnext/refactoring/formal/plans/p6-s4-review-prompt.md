# S4 独立设计/实施审核提示词

本轮先审核设计；不是实施、测试或阶段退出授权。协调者必须提供固定候选完整SHA、base和路径清单；不审核移动中的main。

## 1. 角色与环境

你是未参与该候选设计/实施的独立审核者。使用Sol xhigh，复杂FFI/资源可max；不递归创建角色。`git worktree add --detach`创建固定候选审核WT，链接主仓库legacy（忽略、不入Git），确认clean。只读代码/文档/历史证据，不在开发机测试、编译或lint，不改产品、锁、golden、节点、原基准或其他worktree。审核报告单独提交或交协调者落盘；不要签自己的设计。

先读实际AGENTS、testing-conventions、比例化/Rust政策，`p6-s4-design.md`、`p6-s4-kickoff.md`、P6设计/执行计划/DC45/55/57/78/91–93及本轮决议、S1a原件/终审、S3累计交接/E容量报告和最终独审、Q18最新状态。Owning Contract含Storage Mutation、Canonical Storage、Shared Encoding、Business/Operation Lifecycle、Repository Service和ADR0014。

## 2. 设计审核检查点

1. 设计是否足以直接分节实施：每节输入/输出、精确路径、依赖、API、错误、owner与验证可落地；没有把尚未实现的接口/预算改善/性能写成事实。
2. 存储键/full persisted列独立于FE records/effective key/共有列/LIS；ordered gid/no/伪gid、keyless重复、schema/view/version、source-only NOOP、非INITIAL缺parent拒绝准确。表级policy仍在planner，通用ChangeSet/external ledger保留。
3. JCS key字节序、旧mutation row hash的keyless排序消费者与业务content域分开；DDL列序与DML列序分开；全部DDL前于全部DML、DELETE→UPDATE→INSERT不变。
4. SQL字节和独立expected：CASE全部非键列、IN标点、literal escaping、`.15g`与指数、SET/JSON/NULL/BIT/binary/时间/Unicode；unsupported不stringify。INSERT与UPDATE/DELETE的256窗口细节、4MiB完整语句、大单行和最终DDL+DML 200MiB精确限制，增量计数不重新编码已有整批。
5. 粗粒度Arrow FFI、safe API、共享N/同operation M、GIL、cancel/deadline/panic；core不依赖业务/I/O。逐表释放、输入backing去重与复制区别、Vec capacity、超大值、最后consumer、FFI字节复制、publisher/readback同时驻留均计费；不能把mmap/低RSS当零预算。
6. 2528MiB原package预约保留时有界DML汇集是否自洽；没有偷偷引入streaming tar、spool或第二恢复系统。共用kernel抽取是否控制范围并保S3接口/错误映射；通用renderer复用唯一Rust编码而非保完整旧Python oracle。
7. T1即PREPARED、prepare checkpoint才固定包；effect/unknown outcome不得重渲染换key。parent count/content、expected-parent CAS、STRUCTURAL全catalog、pin/release、Submit与业务BaselineHead区别完整。
8. S3原失败stage仍未知、S3-only与joint不混归因；Q18静态CLEAR不等于FE前置解除；W2无行比较。三线文件次序、同源carried、镜像closure、DC33已确认范围、同worker原预算、统计与压力/未知分列可执行。
9. 测试按语义owner移交，不删独有断言，不穷举私有步骤；最终集中权威/容器/真实数据而非每节重复全量。S4独审通过不代表产品实施已获授权、S3通过或S5放行。

逐条核当前源，尤其`import_publication.py`、mutation planner/renderer、storage publisher/package、canonical reader/budget、submit prepare/T1/T2恢复。提示列举不是上限，发现其他会改变实施方案的缺口也应报告。

## 3. 输出与复审

报告给固定base/candidate/审核WT/实际读取范围、结论 `CHANGES_REQUIRED` 或 `DESIGN_CLEAR_FOR_OWNER`。finding含严重度、路径/行/源码事实、业务后果、最小修正及验收；区分阻塞与实现期验证，不因没有运行未来代码而制造设计finding，也不因实现未知就默认为性能PASS。

修复由设计者另固定提交，原审核者增量复核并累计关闭；报告不能冒签产品测试或owner实施授权。记录本轮container rebuild=no（仅设计文档）、当前产品验证未运行、最后S3来源及不能沿用为新产品证据的边界。

后续代码/证据独审沿同清单，额外核实际包closure/镜像、真实日志入口exit/HEAD/SHA、原失败保留、expected来源、旧consumer删除和最后owner。所有执行须由唯一获准测试者在合格专用节点固定clean WT进行；reviewer仅凭脚本CLEAR不能签实际证据。
