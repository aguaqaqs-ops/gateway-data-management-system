# Phase 6 S4：执行计划与开工边界

2026-11-08。状态：固定设计候选 `de0eb3a8b2f9881737a183f0a4663dad9a75d67f` 已获 [Sol 连续复审](p6-s4-design-review.md)及 [GPT-6-Astra high 第二次独审](p6-s4-astra-review.md) **DESIGN_CLEAR_FOR_OWNER**；本轮仅设计，不授权产品实施或任何测试/编译/lint/构建。
依据 [详细设计](p6-s4-design.md)；Owner已确认本文§6的DC33范围，不等于执行放行。

## 1. 前置与角色

起点main=`572359d3a7`；开工重新核actual HEAD、status/index/untracked、tags、worktree和并行路径，不回退历史起点。S3 A–D已GO、E仍BLOCKED_CAPACITY；DC92允许S4设计独审后提前实施，S3 exit不是本阶段开工前置。设计独审和届时实施授权仍是前置；S5仍需S3/S4各自exit。

本轮设计材料固定后可按任务提示创建一个独立设计审核者，Sol xhigh（必要时max），在clean detached WT只读审核；设计者不能自签独审。后续实施者Sol xhigh、独审者独立且连续负责同节复审，测试执行者Luna max，含协调者最多四活跃槽，不递归扩队。每次运行只有一个责任人；机械执行脚本先固定并由原审核者检查。角色配置只是计划，未启动实施/测试角色。

每节顺序：实施与必要focused → 固定提交 → 独审 → 修复及原审复审 → 适用证据核收 → 下一节。明确授权仅覆盖A时，不自动进入B；若Owner授权A–E连续推进，日常范围内修复不反复申请。存在需改变冻结边界的finding，先处理设计/Owner决策。

## 2. 分节交付与依赖

把存储diff、表级owner和渲染的整体接线放在D；不能在B先把新diff经全量PythonChangeSet接回生产，或在C增加部署开关。

| 节 | 输入/输出与路径归属 | focused与核收标准 |
| --- | --- | --- |
| A 语义、接口、独立预期 | 输入：本设计、S1a原SQL/Contract、当前consumer。输出：StorageTableTask/summary/handle签名、三种顺序与hash域、内存所有权表、renderer失败映射和迁移矩阵。路径：owning Contract/政策、`mutation_planning/contracts.py`必要内部类型、`tests/support`、新增固定输入/expected；不改生产路由 | 手算净diff/阈值；JCS key、keyless重复排序、完整DDL前缀；既有expected.sql和包golden按文件SHA登记。补充边界expected只来自手算或固定旧版本节点捕获并独核，不由新Rust产生。A无运行时优化声明 |
| B 列式storage diff与表级规划 | 输入A；输出：Rust storage view/index/diff及小summary、Python共用decision predicate、表级lease。路径：core `storage_mutation/`及最小共享kernel/cell抽取，Python `mutation_planning`轻量规划；只在测试支持层接新入口 | keyed增删改/键变、多列一次、ordered gid/no/伪gid、keyless重复、空/缺侧、schema/view/version差异、source-only候选NOOP、重复键拒绝；1000/1001及1%边界按整数断言；N1与允许N、输入batch分割确定；t1–t4逐表替换期差分（不跑完整旅程） |
| C Rust SQL与通用facade | 输入A/B；输出唯一SQL编码/长度累计/chunk流，通用ChangeSet及schema renderer薄适配。路径：core `sql_replay/`，PyO3 `storage_mutation.rs`，B `mutation_planning/native.py`、旧renderer facade、`storage_projection/import_replay.py`及其已有`native.py`；精确import guard与Rust政策同步，不引入Projection→Mutation依赖 | 既有SQL/golden逐字节；DELETE IN/CASE UPDATE/INSERT、DDL顺序、Unicode/float/SET等边界；255/256/257/512，恰4MiB/超1B/单行5MiB，byte flush与256窗口交叉；最终DDL+DML 200MiB等号/超1B拒绝；直接计数验证不重复编码已入批行；safe FFI/GIL/取消/提前关闭 |
| D Submit唯一接线、资源和删除 | 输入B/C独审；输出：lazy逐表打开→native summary→planner decision→DML汇集→DDL前置→原publisher。路径：`infrastructure/repository_write/import_publication.py`、必要canonical reader接口/exports、`application/submission`及`submit_jobs.py`仅适配/计量需要、旧import wrapper删除与测试移交 | 真实已安装扩展小型Submit；U/X/A/D及source-only NOOP；parent错count/content/commit拒绝；frozen坏/缺；普通I/O/预算/取消；表A结束再表B不保留A输入/索引；checkpoint复用与unknown outcome不再渲染；旧行物化/ChangeSet调用计数为0；通用/外部ledger仍正常；删除临时双实现 |
| E 最终固定V、集中证据与退出交接 | 输入A–D全部代码finding收敛及预检；输出：产品V、逐包与容器证据、§6真实范围、性能/容量账本、累计handoff H及独审核收。路径：benchmarks/必要driver及tests、S4 handoff/review/协调引用；脚本先审后跑 | 权威受影响包整次exit0；当前镜像Compose绑定；fresh t1–t4、2×t4统计、S1a阈值/真实Dolt表结果；原失败保留；V→H在来源节点同WT比较闭包/镜像；分别写S4及联合候选的结论，不倒签S3 |

每节单独交接固定SHA、实际差异、独立预期来源、已跑/待跑项、容器是否触发及理由。B/C可以在同一实施者上下文连续开发，但后节依赖只有在前节独审核收后启用；禁止为切节把Arrow owner生命周期拆成不成立的中间产品路径。

## 3. 路径所有权与三线协调

| 路径/对象 | 主责及次序 |
| --- | --- |
| `import_publication.py` | S4；S3-only首次拒绝诊断如需触及，先固定最小诊断提交，再由S4接续。不得两人同时编辑 |
| `table_access/kernel.py`、公共native资源 | S3诊断先声明字段；S4复用/扩展。移出comparison公共lease时保S3错误/预算回归，不为复用扩大接口 |
| `comparison/*`、`records/*` | S3；S4只做必要共用低层抽取与受影响回归，不重开已核收算法 |
| `archive/*`、HTTP/OpenAPI、FE快照 | Q18/FE owner；S4只在最终联合候选核接口前置状态，不修改产品 |
| `real_dump_journey.py`与测量driver | E唯一责任人；S3/S4共享改动先固定工具候选/脚本，避免一个运行中WT承接另线编辑 |
| 原失败归档、原基准、04 carried WT | 原owner；S4只引用不写入/清理，不从成功清理过的旧卷声称可续跑 |

记录 S3-only D、S4代码候选 S、Q18 Q、最终联合 J 的完整SHA/增量范围。J可给受影响模块共同功能证据，但不可给D/774倒签性能。最新main另有前端/文档提交时逐路径核影响，不要求退回S3原V。

每个在测WT保持clean已提交，运行中不写入、commit、build或retag；按脚本事先固定的构建阶段完成后才进入测量，client e2e由权威门禁正常本机重建的既有例外保留。报告改动形成H后同源WT只做适用闭包/镜像绑定；不要在正式运行中追加日志代码。

## 4. 测试owner与最小断言矩阵

| 不变量 | 权威owner/现役起点 | 必需移交 |
| --- | --- | --- |
| scalar/content | Shared Kernel vectors、canonical codec | 复用语义测试；SQL拼写由Rust SQL向量独立拥有，区分raw-content与mutation排序hash |
| 表级策略/净diff | `test_mutation_planning.py`、新storage native测试 | 共用decision predicate；0/1/1000/1001、比例边界、ordered/keyless/schema；通用ChangeSet测试继续 |
| SQL字节/批次 | `test_dolt_renderer.py`、`test_storage_projection_import_replay.py`、`fixtures/golden/mutation/renderer` | 旧完整expected保留，调用Rust；不以旧Python并跑作为永久oracle |
| Submit构包/跳表/删除 | `test_submit_import_builder.py`、`test_submit_prepare_removed_tables.py`、`test_canonical_snapshot_identity.py` | 移交旧mock到真实新facade；全target manifest/DDL+DML cap、无全表Pythonrows |
| 包安全/出版/真正读取 | `test_repository_import_artifact_package.py`、`test_repository_import_artifact_diagnostics.py` | package member/raw/size/structural语义保持；不新增生产readback |
| owner/取消/预算 | `test_operation_kernel_context.py`、`test_worker_kernel_resources.py`、新storage bridge tests | 输入和结果最后owner、双表峰值、超大单元格、GIL；时间敏感serial |
| T1/T2/幂等/恢复/保护 | `test_submit_job_prepare.py`、`test_submit_job_effect.py`、`test_submit_recovery.py`、`test_submit_artifact_protection.py` | 原有语义屏障；checkpoint存在不调用renderer，缺失冻结输入不调用RS |
| 真实Dolt和容器 | `test_submit_compose_e2e.py`、`test_ordered_submit_bisect_compose.py`及既有RS import集成 | mixed/noop/ordered、表hash/规范内容、CAS与恢复。复用既有owner，避免重复crash矩阵 |
| S3共用低层回归 | `test_comparison_s3_c_arrow.py`和现役comparison/native测试 | 比较/records原golden及预算/取消映射不变，不重跑已退出阶段完整历史测试 |

新增同构输入共享参数表，纯编码/策略不用Dolt fixture。每个不变量一个权威owner；删除旧实现时删专用mock/probe，但不能删除其独有业务断言。renderer大输入边界用合成精确字节，只在专用节点执行；不要靠生成200MiB真实库验证纯size admission。

C必须落实设计§3.4两个保留facade的显式context签名、调用方/fixture迁移及bytes结果预约期限，不能只更换函数内部实现。B/D区分通用planner完整keyless净计数与Submit未读before的`net_counts=None`，保原source-only keyed NOOP/keyless rebuild行为，不补无消费者的parent读取。

## 5. 执行和集中门禁

本节只是后续命令与规则，**本轮不执行**。以仓库现行AGENTS/testing-conventions为准，DC91覆盖旧节点分工：

1. 选当时空闲且本次缓存/工具链/输入合格的池内节点，BatchMode连接；核全机`/proc`、Dolt/Compose/8000和有效标志。原子`mkdir /home/dev/gdds-node-busy.d`，记录会话/用途/UTC/HEAD；不抢占他人，已有自管标记入口不重复取。04/06/07共享宿主，实际干扰才协调；正式计时本节点独占。
2. clean提交经获准LAN bundle同步，linked WT链接legacy；日志、Cargo target和pytest磁盘TMPDIR在WT外。root PATH以`/home/dev/.cargo/bin`起始，核四个Rust工具同selector，不设RUSTUP_TOOLCHAIN/HOME或CARGO_HOME替代选择。
3. `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`；缓存缺失先停，经CT201补实际节点。无依赖变更授权不改锁；Rust源进入dependency-input时按实际脚本闭包判断是否重建dependency-base，不能只看Cargo.lock。所有镜像完整身份、来源/预填时刻与摘要按DC67，不比较跨节点inspect ID。
4. Rust改变后先`vnext/scripts/uv-consume.sh -C vnext/backend sync --reinstall-package gateway-compute-python`并跑既有build-input checker，再跑backend focused。节点上完成五包ruff/mypy、Rust fmt/clippy；pytest serial按两遍拆分，初始workers/jobs4与产品N1分开。

focused命令骨架（实际精确nodeid及环境由每节固定执行稿列明）：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -m 'not serial' <本节路径或nodeid>
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -m 'serial and not parallel_safe' -n 0 <本节路径或nodeid>
# Rust：在vnext/rust，CARGO_TARGET_DIR为WT外绝对路径
cargo fmt --all --check
cargo clippy --workspace --locked --offline --all-targets -- -D warnings
cargo test --workspace --locked --offline
```

A–D只跑必要focused/小型集成和触发的容器smoke，不每节全量。E最终代码独审收敛后至少实际运行rust/backend；其余四包按最终完整闭包比较，改变的包加入本次权威入口，没有合格来源就实际跑。backend/RS Docker context覆盖vnext，不能仅因RS源码未改就宣称其包闭包相等。最坏本次需要六包；项目最终/发布仍必须六包。

```bash
GATEWAY_TEST_PACKAGES=rust,backend ./vnext/scripts/run-tests.sh
# 上述选包仅为下限示例；执行稿以实际闭包判定的固定包集合为准。
```

S4改Rust和backend镜像内扩展，最终候选必须重建并运行适用Compose；使用预置dependency-base、`GATEWAY_DOCKER_BUILD_NETWORK=none`，保留Compose本机构建，不设prebuilt。权威runner里已执行的Submit/Archive旅程不再重复。每轮审核记录HEAD、触发理由、最后验证image revision/source-tree、deferred/current/carried状态。

runner非0停后续验收，保失败原件。工具错误按现DC68最多三轮有修订/适用复审的修复复验；不无修改重试，不把产品容量失败归为工具错误。日志记录hostname、起止UTC/HEAD、入口exit（pipefail/PIPESTATUS）、SHA；失败/成功、外层/入口exit分别保留。

V→H carried须原来源节点、原WT、原环境和Hypothesis不存在路径，指最初实际整次runner0的包来源。镜像等价与按包closure各自满足；最终H改生产/镜像边界则重跑受影响项，不口头把docs-only算passed。保留新来源WT至实际exit；04旧S3来源由原owner决定释放。

## 6. Owner已确认的DC33范围与统计

2026-11-08 本轮Owner明确确认以下**设计验收范围**，没有授权本轮执行。

| 范围 | 固定条件/工作 | 验收 |
| --- | --- | --- |
| t1–t4 | 每档fresh、全档同节点同worker；v1/重复Preview MO、v2 FULL；真实Preview→Submit→读取/审核→Archive→History。Archive异常按真实输入和现有有理由接受流程，不造时间、跳Review或直改DB | canonical结果、表集合/schema/count/必要独立表hash、冻结SQL、业务状态/CAS/保护和资源正确；不沿用旧Submit算法证明S4 |
| 首次Submit（负载S1） | 冻结2×t4 v1，fresh INITIAL，N1/32−8/M24 | 接受到完成且技术main前移≤5min；全目标表rebuild；业务Archive后head才前移 |
| 原样重传（S2） | 同规范状态重新上传/Preview | AcceptSubmit `NO_CANONICAL_CHANGE`，零Repository operation，不计一个假Submit用时 |
| 少量变化（S3） | 冻结W3/2×t4 v2，在同worker真实准备/Submit/Archive的v1基线上；MO及FULL分别成组 | Submit完成≤2min；PATCH净计数、NOOP跳表与真实表结果 |
| 几乎全变（S4） | 冻结W4-10%输入，MO冷条件及FULL分别成组；不能用100%输入替代10%目标组 | Submit完成≤5min，所有Submit≤10min；实际策略/计数/结果 |
| 100%压力 | 冻结W4-100%，模式分别报告 | 时间/资源只报告，无性能阈值；业务或容量失败仍失败 |

正式计时每组1次预热+3次成功测量，给原始值/中位数/范围；一组同节点/硬件/存储/候选/N/M/冷暖条件。每轮fresh的“预热”是业务/OS预热的单独运行，不保留该轮业务状态伪装下一轮fresh。相同真实完整旅程可同时提供功能与对应性能证据，按断言引用，不为两个标题重复跑。

输入直接核已冻结metadata/census及原包SHA，不重生成/微调以适配实现。S3 coordination已有2×t4/W4来源，E执行稿固定实际路径/SHA/规则并独核；真实数据不进Git。不同节点/配置样本分组，64GiB guest不改变worker M24。计时driver保same-worker/cgroup guard，基线准备也受原预算；如果准备失败就没有合格正式样本。

S1a阈值复核另用同一冻结真实t4 v2表样本（handoff原件：9822→9828、98逻辑变化、92UPDATE+6INSERT）和实际RS回放，对最终renderer的PATCH与REBUILD表结果/耗时交替比较；只能在本任务仓库副本/正常服务接口运行，不在服务正在用的Dolt目录做root checkout。若1%仍慢于重建，报告实测给Owner，不能自己降低比例/改batch/golden。

S3 W3/W4 READY和比较归因另由其owner核收；联合旅程可提供后续J证据，不补成原774成功。S4结果必须分栏：SQL/功能正确、M24完整容量、目标时间、压力、未知/失败。性能未达按DC81交Owner讨论，保留目标和失败，不自签S4 exit。临时大预算仍是另案，不纳入本表通过。

## 7. E固定候选与最终交接

E前：A–D代码独审关闭、临时差分和旧算法删除、五包静态/Rust检查及必要focused通过、最终测量driver固定独审、输入/缓存本节点就绪。再固定产品V，集中运行一次必要证据；失败修订后按DC64重跑真实受影响步骤，只有完整前提成立才续跑，否则整档fresh。

handoff必须给：实际起止SHA和并行增量、职责/消费者删除矩阵、独立expected清单、各包运行或carried的源V/闭包/日志、镜像及Compose绑定、每档真实范围/输入/资源/结果、S3-only与joint归因、失败/未知、节点收尾及保护资源。H引用V证据并完成实际同源绑定，原审核者独核E累计A–D和证据，不只看最后删除diff。

本设计轮最终输出固定设计候选和两次独审原文；Sol初审F1–F3经修订关闭，Astra未发现新增阻塞，均为DESIGN_CLEAR_FOR_OWNER。无剩余Owner设计决策，无产品V/性能PASS。下一对话核最新并行状态及实施授权，从A开始；尚未授权时不执行。临时大预算具体参数仍属S3另案，不阻塞本S4设计。不推送、不tag、不改写已引用提交。
