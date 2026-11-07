# Phase 6 S3 kickoff：比较与逐行记录

2026-11-07；状态：待独立 kickoff 审核，待 Owner 确认范围与启动。依据 [详细设计](p6-s3-design.md)。本文件不是实施授权，也没有创建角色。

## 1. 前置与职责

正式前置 `p6-s2b-exit` 已满足；实际设计代码起点 `5dde965a65`，BE-a/d 已退出、FE3b 与原基准独立。开工时重新核 clean main、阶段 tag 和本候选以来增量，不回退 main。S3 不做 S4 SQL/存储 diff、S5 持久缓存/History 优化或前端新功能。

建议 Owner 在 kickoff 独审通过后指定一个实施者与一个独立审核者，连续负责同一比较/记录/预算不变量；不为模型分工拆散生命周期或事务。复杂跨语言实现与审核建议具备完整 Rust/Arrow/Python 上下文的高推理配置，不强行切小模型。设计者只接设计澄清/范围升级；本轮不自行创建任何角色。

审核者独立核代码、Contract、expected来源、证据和最终闭包；不能用设计自审代替独审。沟通经 Owner 按 DC73 转交。单节 GO 不是阶段退出；最终退出也不等于发布或推送授权。

## 2. 小节与依赖

按 A→B→C→D→E 顺序；每节固定提交后独审，阻塞 finding 修复并复审才进入依赖部分。Owner 如只授权 A，后续不得自动启动。

| 节 | 交付边界 | focused 验证与退出条件 |
| --- | --- | --- |
| A 语义/接口与独立预期 | 将 design §3/4/5 的现行语义落实 Comparison、Ordered Diff、Risk；盘点实际 records/DTO/digest消费者；固定 Arrow schema、排序及风险batch接口、预算owner；建立独立向量与覆盖移交表 | 06 Contract向量：负零/NULL/UTF-8与JCS顺序、keyless重复、LIS并列、schema变化、三族records；expected来源可审。不接生产、不更新冻结golden。确认name含于完整key的miss实例 |
| B 共用比较内核 | standard/keyless + ordered原型重构；共有列/规范编码/identity/facts；单侧ordered摘要；复用池/取消/预算；临时差分只在测试支持层 | 06固定/性质差分、空表/重复键/退化/全重排、随机batch；1与允许N确定性；t1–t4按表差分（获准输入传输后，非完整旅程）。结果与旧生产及独立向量一致；无新生产开关 |
| C Arrow记录与读写 | 三族builders、全局排序/去重检查、流式JCS；Python直接Arrow写Parquet；真实读取Arrow→Rust校验；删除发布后全量读回 | 06 schema/nullability、0/1/1023/1024/1025跨batch、可变宽/嵌套/offset上限；JCS逐字节、content与raw golden分开核；损坏与I/O；Arrow生命周期/GIL progress；预算增长前拒绝 |
| D 风险/操作内去重/生产接线 | pair_pipeline及Preview/History换唯一Rust路径；风险批消费与pair汇总；FULL共享操作去重域；实际资源重新计费，保持M24/N1 | 06小型真实Preview MO/FULL、History；三族/风险/去重on-off结果一致；调用/读取/派发计数；FULL峰值、取消/截止与实际容器/native错误路径。HTTP/bundle不变，W3/W4阶段诊断起测 |
| E 删除与集中验收 | 删除被替代Python/原型/临时双实现及旧专用测试；完成断言移交；固定唯一产品V；集中门禁、真实数据与性能报告 | 06删除后focused及五包ruff/mypy、Rust fmt/clippy/release相关检查；04最终权威受影响包与必要Compose；DC33确认范围的真实旅程；独审核证，最终H绑定。不留永久oracle |

A首节建议任务范围明确限制为 Contract、固定向量、内部接口与消费者清单；纯内存codec/比较实现归B/C。生产接入前必须得到A/B/C独审结论和Owner适用授权，不能因本文已写好就改路由。

## 3. 验证矩阵与权威 owner

| 层/问题 | 输入与断言 | 位置/责任 |
| --- | --- | --- |
| scalar/规范编码 | 负零、NULL、UTF-8、supplementary Unicode、binary/SET/anomaly；与Shared Canonical固定向量相同 | Rust/shared kernel既有owner；comparison只测接线，不复制全编码测试 |
| 比较语义 | keyed增删改、key变化/缺失/重复、keyless multiplicity、共有列/只增列、table role、replacement、ordered位移/移动/LIS并列/空白首尾 | Rust独立向量/proptest；backend planner/业务Contract保留 |
| 差分 | 旧生产与新kernel临时对比：facts、诊断、逻辑records、顺序及JCS；t1–t4两版全部相关表；记录输入身份/seed | 06 focused为主，05真实调试；E前转独立向量并删除临时入口 |
| 记录完整性 | 三族每个字段/nullable/metadata/detail policy；随机输入batch分割、固定1024输出组；raw/content/schema/count损坏分别拒绝 | records.rs validator + backend artifact adapter；不为纯测试启动Dolt |
| 风险 | 规则/等级/排序/编号、per-table与pair cap前后1项、组合信号、degraded、未知target；两种facts/产物排序不可混用 | backend risk测试；整份元组/Parquet回读调用计数为0 |
| 去重 | 相同完整key命中、方向/规则正文/版本/schema/key/scope变化miss；含表名schema跨表miss；on/off facts/records/risk/bundle一致 | operation内测试；重绑定后的摘要比较，不要求不同table的digest相等 |
| 生命周期/资源 | reader关闭后输出有效、提前终止/异常后owner释放、FULL两pair驻留、预算拒绝、取消/截止、GIL释放 | backend已安装扩展/worker测试；必要native crash/Compose复用现恢复owner |
| 编排 | 小型真实Preview/History实际调用Rust；未变化ordered只读当前、0 before读/0 LIS/0 records；变化task每个完整key一次计算；整表新增删无records | pair_pipeline/Preview/History集成；Submit已有冻结构/CAS回归，不实现S4 |
| 外部产物 | 原golden逻辑/JCS/content/raw分别对照；真实bundle读取/closure校验；FE HTTP/tar/schema稳定 | backend artifacts/surface/bundle，前端互通另归FE owner |

不穷举内部步骤；每不变量一个权威测试owner，引用其他层结果。纯逻辑禁Dolt fixture，同构输入参数化；时间敏感serial。临时差分expected来自旧已冻结行为与Contract，不从新Rust批量生成。

## 4. 节点与执行规则

本轮设计不运行任何测试、编译、lint、容器、真实旅程或大输入生成。以下供授权后的实施使用：

- 06：后端focused/Contract/差分、小型Compose；初始pytest4/Cargo jobs4，N独立为1。
- 05：调试与默认t1–t3真实功能旅程。S2b专用06全旅程授权不自动继承。
- 04：最终权威runner/carried与容器。07由前端owner负责；CT108正式测量保持原基准独占，先协调实际冲突再取用。
- 运行前 `ssh -o BatchMode=yes <alias> 'echo OK'`；核现场进程/端口/有效标志，原子 `mkdir /home/dev/gdds-node-busy.d` 并写用途/会话/开始时间，只释放自己的标记。04/06/07共享宿主不自动跨节点互斥。
- clean、已提交测试worktree，linked WT准备legacy symlink；日志在WT外，记录hostname、起止UTC/HEAD/exit/SHA。运行期不写worktree、不重tag镜像。
- `TMPDIR=/home/dev/gdds-test-tmp`；UV_OFFLINE=1、CARGO_NET_OFFLINE=true；root PATH以`/home/dev/.cargo/bin`起始，selector/toolchain核对。Rust修改先强制重装gateway-compute-python并核build input。
- 必需缓存缺失停下从CT201经获准LAN预填充；04/真实旅程/测量无代理。backend锁/toolchain变化按依赖基镜像流程记录输入/config digest/全部DiffID/归档SHA；offline Compose本机构建，network=none，不设prebuilt。镜像跨节点不比较inspect ID。

最终预计至少实际跑 `GATEWAY_TEST_PACKAGES=rust,backend ./vnext/scripts/run-tests.sh`，且Rust/FFI改变需当前镜像/Compose。其余包逐项闭包核判，变化则加入最终集中运行；不能凭“只改Rust”口头沿用。五包静态检查在专用节点完成。全部六包仅在实际闭包或最终规则要求时运行，不每小节重复。一次权威runner中已执行的Compose不另跑。runner非0先停处理，不能继续carried或后续验收；DC68仅适用于规定的无副作用自身操作错误。

最终产品V实际通过后，报告修订形成H；同节点同来源WT重算逐包closure与镜像等价，引用最初实际通过V及原日志，保留WT直到退出。每轮审核写HEAD、是否重建及原因、最后image revision/source-tree与carried来源；不凭docs-only宣告沿用。

## 5. 真实数据建议与性能

建议DC33范围：替换期间t1–t4比较差分；E最终在05对t1–t3 fresh完整功能旅程，覆盖MO/FULL必要pair、Preview→Submit→History及真实读取；t4完整功能/容量与W3/W4在CT108可用窗口安排，由Owner在退出前确认。理由：比较、记录与风险全部变化，原S2b的t4 bound无法证明新算法。可以沿用的仅为未改消费者/恢复不变量的具体既有证据，须列输入、diff、条件及源日志；不能按tier大小或旧技术GO推导。若Owner批准在06跑本轮完整旅程，再记录专项用途扩展。

W3/W4从D/E开始测量，不统统延期S6：

| 场景 | 工作量/口径 | S3与S6 |
| --- | --- | --- |
| W3 | 2×t4，MODIFIED_ONLY；另FULL一次；允许上一Preview临时条目并写明 | S3诊断起测；S6正式READY≤60s，完成≤10min |
| W4 | 全部表约10%混合增删改，ordered含位移；MO冷启动，另FULL一次 | S3核比较/记录/风险各段；S6正式READY≤3min，完成≤10min |
| W4压力 | 每表100%行变化 | S3与S6均报告时间/资源/结果；无性能门槛，业务失败不记通过 |

正式场景每负载1预热+3测量，中位数及范围；失败样本保留、排除成功统计，不静默重写。受理到READY含assemble/export，完成另计；下载传输不能挪走READY内工作。固定输入/版本/N/M/冷暖状态/镜像/正确性，当前N1不能冒称历史N4同条件比较。S6再定N，不通过加线程隐藏内存风险。

分项互不重叠：输入读取/投影、index+compare、records列与JCS、Parquet写、Python风险必要列转换、surface/bundle；记录峰值与调用数，写后全份回读应为0。P6设计g段W4约5–10s、h风险约5s仅是假设，在S3实测核对；风险明显超预算且成为主热点，按DC47单独评估语言边界，不自动迁Rust。W2没有行比较，S3比较提速不计其削减；只有未变化ordered单侧摘要等实际子段可按独立证据归因。

CT108无窗口时先06做小型/容量诊断，明确非正式性能；报告缺哪些W3/W4/FULL/压力项、对退出的影响及Owner待定窗口。不能擅换正式节点，不能以“最迟S6”取消本阶段正确性、资源、起测和必要门禁。本轮设计不预约、不占用CT108。

## 6. findings、停止与交接

finding必须包含复现/源码证据、业务影响、严重度、负责文件及最小修复；实施固定修复提交，独审独立复核，关闭表引用证据，不由实施自签。禁止通过放宽Contract、删断言或改golden消除差异。

以下停受影响部分并交设计/Owner：语义/digest/golden变化；需要改格式、M或部署旋钮；风险进入Rust；冻结/CAS/恢复变化；FE接口变化；S4/S5扩项；持续资源拒绝；实际业务失败或runner非0。报告场景、证据、影响、选项、推荐；其余独立文档工作可继续。

E handoff列：实际起止SHA与变更区间、产品/文档候选、逐包运行/沿用、镜像/Compose provenance、输入身份与真实范围、失败保留、性能实测/推导/未知、旧代码与断言移交、资源释放、未决项。独审固定detached WT（需要测试时在指定节点）；不改被审提交。Owner确认后另办阶段退出/tag；本轮不push/tag、不改已引用提交。

## 7. 独审前补充约束

Owner 已同意设计者补齐技术缺口，并授权 GPT-6-Astra high 独立 kickoff 审核、直接按finding修订与复审；尚未授权产品实施。A需核收[设计§9](p6-s3-design.md#9-审核前补充摘要与生命周期的具体接口)的逐消费者迁移清单、三种记录逻辑视图及risk emit边界向量；C/D必须验证facts-core流式字节而非table hash拼接、FULL实际驻留、去重不足预算时安全miss。风险纯候选必须保留过滤项，pair/table上限和原降级控制流在消费时重放；不完整/超时结果不复用。代码与证据阶段规则不变。
