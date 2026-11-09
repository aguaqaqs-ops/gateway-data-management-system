# Phase 6 S6 实施计划

状态：**DESIGN_GO**（固定候选`9b466d788f00ea1edb9e98b88f1746f2a7bcfee7`）；尚未获实施授权。依据 [详细设计](p6-s6-design.md) 与本轮Owner已确认范围。
本计划规定授权后的完整顺序，设计GO不代替CODE/EVIDENCE/EXIT_GO。

## 1. 三节依赖与角色

协调者持续；按下列每个新小节新建实施、独立审核、唯一测试/等待子agent。创建前核实际并发槽，含协调者最多4活跃角色；不递归扩队，不跨节换任务复用。角色不继承旧Astra或节点特权；按当时明确授权/可用模型创建。同节finding由原审连续复审至关闭，结束角色需用真正任务分派唤起，不只发消息。新角色读取固定候选、Contract、前节交接、原始证据和未测/未决，不靠历史聊天继承。实际未授权前不预占实施/测试角色。

### I 工具范围收敛与文档一致性

输入：本设计及comparison/ordered文档纠偏、固定main、标准t4数据清单、现`real_dump_journey.py`。输出：新`t4-w1-w2` scope、focused测试、固定工具候选与交接。默认无runtime、Rust、依赖、schema、HTTP DTO变化。

文件：`vnext/backend/benchmarks/real_dump_journey.py`、`vnext/backend/tests/test_real_dump_journey.py`，必要现runner调用说明；不得增加通用测量平台。详细路径/断言以设计§4.2为准。新scope参数前置必须覆盖CLI parser与`run_journey`校验，且不可绕过原资源guard、输入SHA或clean检查。

实施顺序：先梳理当前scope前置和返回payload→最小扩充scope与repeat后返回→复用真实mutation/catalog/独立内容检查→固定稿→独审→专用CT focused与代码提交要求的五Python包ruff/mypy。测试不启动真实Dolt验证纯参数，不复制业务矩阵。Rust未改不为此单独编译；最终六包仍覆盖Rust。实际调整容器harness即触发本节对应门禁，否则集中III最终gate。

预期focused/静态为分钟级至十余分钟，首次环境准备另计，非性能承诺。任何必要依赖缺失先按DC67预填充，不能在开发机测试。

### II 固定最小真实稿与报告来源

输入：I已核工具、实际标准t4 v1/census/独立预期、S5完整tar原件、历史存储/性能来源。输出：一份可审执行稿、来源表、报告结构与停止/收尾说明；此节只做必要准备/工具验证，**真实链留III最终候选执行一次**。

执行稿使用现公开CLI参数，新增scope只在I实际实现后可用；不把本页命令草案冒现成可运行命令。不直接写control DB/Repository制造基线，不挂他人原卷进行写入，不拷贝不匹配control DB后迁移。新项目/新空基线建立v1，scope固定N1/M24，fresh且非派生负载。

独立预期、输入摘要与实际计数采集严格按[设计§4.2.1](p6-s6-design.md#421-独立预期与计数采集的固定来源)，不留给执行者临场选择；该节必需计数UNKNOWN会阻止证据核收，不能自行降格为测试已代证。

真实清单：

1. 核标准datasets.json与t4 v1文件SHA、真实规模、source oracle版本；确认磁盘余量、工具链/缓存、runtime镜像、资源实际配置及同一worker身份。
2. 空业务基线第一次upload/Preview，核表集合/摘要/identity与完整bundle；按现有首次预期核`NOT_APPLICABLE`/`DETAILED`及真实表内容。
3. 首次Submit，核technical main/完整catalog/schema/count和独立代表表；此时业务head不动。读审核材料、合法approve、Archive，核业务head绑定v1、引用及版本。
4. 新workspace/key重复原字节upload/Preview，核`SAME_PROJECT`/`DETAILED`与零变化。记录分层读取/比较事实；W2基线行需求/实际读取为0，不要求上传解析、当前单侧ordered、metadata/校验为0。没有具体计数来源时报告缺口，不从延时或缺日志推零；复用现指标与测试owner，必要工具采集在I/II固定，不临时扩production日志。
5. 无变更Submit返回`NO_CANONICAL_CHANGE`，Repository mutation集合、technical main和业务head均不变。完成即停止，不进入v2/History。
6. 两次Preview的既有完整tar GET顺带BE-c；核实收/Content-Length、closure/成员/摘要。原timing口径按设计§4.3，不统计median/提速。
7. 同worker资源峰/事件、M配置/可得预约HWM、退出与本人清理记录；UNKNOWN保留。只清本人此次允许清理的派生栈资源，保护失败、输入、基准和有效来源。

BE-c历史包来源从S5 final handoff/外置receipt逐个定位；已有完整性核收可引用，记录原软件/模式/输入和实际tar bytes。保存文件缺失或摘要不符不虚构替代，先定位归档；不为补体积新开旅程。计算/报告脚本如需要运行只在专用CT，使用普通结果JSON/Markdown，不建新持久协议。来源表可在最终候选前填完历史已知部分。

成本：S2b旧t4首次Submit观察535.712秒、S3大派生输入前置曾达千秒级，不能给本轮保证；预算一次真实链1–2小时（含栈准备/核验，不含首次镜像制品和失败修复），最终runner参考S5约30分钟，预留1小时。超预估只报告；沿用现有限operation timeout，不为赶时删断言/调预算。不存在按次数自动重试的队列。

### III 最终候选、实跑与退出交接

输入：I/II无阻塞、独立源码/执行稿审核、Owner实施与本轮真实范围授权。输出：最终H上六包完整runner/适用Compose、一次t4链、BE-c/存储/时长报告、独立原件核收和外置回执。

1. 先在main提交全部产品/工具/Contract和最终tracked报告结构，冻结最终候选H。tracked文档预先指向确定的外置回执目录，不预填结果或自身SHA。新建clean detached审核及测试worktree并接legacy，固定审区间`p6-s5-exit..H`。独审确认CODE_GO及执行稿可用后才实际gate。
2. 通过获准LAN传源码/缓存到选定合格空闲CT。配置本地依赖镜像与完整来源。最终H在节点本机重建适用镜像，保Compose正常build；最终完整`./vnext/scripts/run-tests.sh`不设选包缩减，六包必须实际通过。同次runner已经运行的Compose不再单独重复。
3. t4最小链可在另一合格CT对同H并行，单档完整链保持同节点/配置；不以S5 carried替代当前gate。两者失败均先停止该次及依赖后续核收，保原numeric exit与日志/SHA；无故障时唯一测试者等待完成，不由协调者重复轮询。
4. 所有新结果写worktree外。记录hostname、起止UTC/HEAD、clean事实、工具/输入/镜像身份、exit、日志SHA、实际释放。原审检查原始证据和未测限制，签EVIDENCE_GO；不因报告字段缺失无理由重跑完整业务。
5. 若发现需修代码/工具/文档形成新提交H2，先固定修复并原审复审；最终六包/最终容器须绑定真正最终H2，不能把普通阶段carried当项目最终豁免。真实数据只重跑受影响步骤/范围，依原规则和独审决定；旧失败保留。避免为把刚完成的结果写入tracked文件制造H2。
6. 结果、报告正文、最终字面SHA绑定与审核结论放预定外置不可变回执；本轮设计建议路径为`/home/dev/gdds-s6-logs/final/<H>/`。仓库预置交接页仅说明解析位置与规则，不声称尚未发生的结果。后续若要将结果归档入Git，应单独明确为退出后文档归档，不挪动已验H/tag、不把新docsHEAD冒原验收对象。
7. 原审核实际本人资源释放、未知/取消/未测，独立EXIT_GO后，只有取得退出/tag授权才创建本地附注tag；本设计轮不授权该动作，不推送。Phase6完成不代签FE3c/P7/发布上线。

## 2. 节点、离线与来源纪律

五节点均32 vCPU/64GiB统一池：04、05、CT108、06、07；04/06/07共享物理宿主。按执行时有效占用/服务/端口核空闲，先`ssh -o BatchMode=yes <alias> 'echo OK'`，原子`mkdir /home/dev/gdds-node-busy.d`并记录会话/用途/UTC；只释放本人标记，不预约、不抢占。真实冲突/他人资源才协调。同节点整机单飞，统计/计时独占，跨节点不自动互斥。

专用CT clean已提交worktree运行所有产品测试、静态、编译、镜像及新增取证。root PATH以`/home/dev/.cargo/bin`开头，不设RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME；`TMPDIR=/home/dev/gdds-test-tmp`真实磁盘，默认不设GATEWAY_TEST_BASETEMP。初始pytest workers/Cargo jobs各4，与产品N1/M24分开。

`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，所有uv消费经wrapper/locked，Rust变化后强制重装并核build-input。每个节点独立预填充缓存；先核实际LAN endpoint，不假设固定bridge地址。依赖变化CT201取得/构建再LAN传输，记录source commit、摘要、prefill UTC；不直连公网、不经代理做证据。backend预置dependency-base、network=none、本机Compose build、不设GATEWAY_COMPOSE_GATE_PREBUILT。跨节点镜像比config digest及全部RootFS DiffID，同节点闭包按现规则，凭据只摘要。

carried只用于符合规则的普通小节，原来源同节点同worktree/env/images/Hypothesis路径实际compare；引用最初实跑来源。最终项目六包与最终HEAD本机重建/容器不能carry。测试中不写worktree/提交/手工retag；client e2e由门禁正常revision重建例外保留。

## 3. 失败、交接与最小验收

每节handoff记录固定候选、改动/Contract、已完成/未测/待决、原始证据、是否触发重建与理由、最后验证image revision/source-tree、延期节点/来源。设计文档变更不触发产品运行，不冒容器等价。

工具/取证故障按现DC68：原次先停、保exit/log/SHA并核安全收尾，同一根因最多三轮有修订、适用独审及受影响复验；不无修改重试，不换目录/节点重置计数。原因/副作用不明、三轮仍失败或超授权交Owner。产品语义/资源失败按本节实际授权处理，不改oracle/golden掩盖，不把cache缺失/身份冲突绕过去。只读后处理例外照现条款，不为字段补齐重跑业务。

验收只包含：F1文档一致；F2/F3工具scope与计时真实；已确认t4真实链；BE-c/存储/门禁报告的来源与限制；全部六包/适用容器和最终H独审。清理核查不要求零Python或删除仍有consumer接口。新增实际业务finding须定位到owning Contract并补最小方案，不借S6收尾泛化恢复、安全或测量平台。
