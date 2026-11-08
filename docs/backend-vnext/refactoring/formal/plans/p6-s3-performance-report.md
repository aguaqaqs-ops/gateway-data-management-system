# S3 W3/W4 诊断与容量补测记录

2026-11-08，**执行中记录，尚无完整负载 v2 Preview 的有效样本或 S3 E GO**。本文把实测、重构及未运行分开；不将准备、失败或未知计为通过。当前源码与门禁见[累计交接](p6-s3-candidate-handoff.md)、[协调 §30](p6-s3-coordination.md#30-隔离v1e门禁核收与两节点剩余执行)及原 E [独审 §68 起](p6-s3-e-review.md)。

## 1. 固定条件与计时范围

产品 V=`1e669c053f2486c50a8413c58de11d923d7f3cad`，Rust tree=`9d4f84ce0897099402226c77c548c487c4912008`，与 main 后续 S4 B 算法隔离。CT108／`gw-dms-test`，32 vCPU／64GiB guest；本次唯一增预算档为 **48GiB worker hard envelope、8GiB reserve、M40GiB、N1、单 active**。生产默认仍32/8/M24。实际容器及端点资源守卫须逐次取证，授权与静态配置不证明生效。

性能范围为现役 `--scope t4-identity`：fresh v1 Preview→Submit→Archive 建立基线，再测 v2 Preview；省略重复 Preview、v2 Submit 和 History。完整功能由另组默认 N1/32−8/M24 的 fresh t1–t4 证明，两种范围不相互替代。READY 观察是接受响应到首次可见结果／终端的 host 端计时，保留实际 polling 粒度；不冒充服务器内部精确 READY 瞬间。每组需1次成功预热和3次成功测量，预热不进入中位数／范围，失败不补位。

accepted 输入13文件清单 SHA256=`cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3`，原字节归档 SHA=`4008b3f876d554b96aca5c59e09c0a906e51d032dbb533397a87543f1eaa949f`。W3为2×t4；W4普通档每表约10%混合变化，另100%压力档；MO与FULL分组。数据、规则、冻结golden及schema不因资源支持改变。同组固定节点、资源和输入，硬件／资源档变化后的结果另组报告，不与原基准混算提速。

## 2. 原M24失败和只读重构

原产品 V774 的 W3 MO warm 已进入基线 v1 Submit，因 `operation memory reservation exceeded` actual exit1，未到 v2 Preview。首拒 stage、表号、requested/live仍未知；不是已证物理OOM。v1 Preview114.783s、631新增表、0 native compare属于另一前置操作，**不是 W3 v2 READY 或比较提速样本**。原始失败、私有三卷归档及完整 SHA 见[容量停止报告](p6-s3-e-capacity-stop.md)。

CT108 对原归档只读重构631表、683,508行：实际 Arrow nbytes152,303,216B；按现行行预约、reader/replay生命周期复算总29,677,814,302B（27.640GiB）。M24模型出现交叉，M40模型未出现；没有同时打开全部reader、未覆盖全部pre-adapter预约，也未构造v2 canonical，不能倒填原首次拒绝点或证明M40/FULL容量。报告 SHA=`89fb32ffe03c87852fa4a0a9a688ca687b29066efb0e2ebc434bdbfecb5a5fc6`，原 E §66–67核收；据此固定新档设计，而非修改算法或降低预约式。

## 3. 当前首轮新档实际失败

04 当前 V1e 全六包及同次 Compose／镜像绑定 actual0，原 E §71已独核；CT108源码、13输入及镜像准备也已核收0。首个 M40 W3 MO warm 于18:19:35–18:23:09Z运行，**node／outer exit1，成功预热数0**。

旅程在 `wait_repository_service_ready` 失败，唯一RS容器 exit3、`OOMKilled=false`，日志为无法导入 `gateway_repository_service.app`。三服务ready、开始端点guard、worker及首业务动作均未到；result `start_resource_guard_count=0`、`worker_count=0`、`resource_verdict=INCOMPLETE_OR_FAILED`、`acceptance_complete=false`。这次失败没有测到M40预约或v2比较，不能写成容量失败或通过。

控制端原件：`/home/dev/gdds-test-tmp/p6-s3-resource-performance-e76342ef0b/warm-control/`，实际源为V1e；outer SHA=`4143fc2f389a3e1e62905d3332686838a446b594c6a1f72cc8d28e352f7082fa`、result=`02201f9dfcaea5e18fa6a3a2e78a8659bb0ac18f9830866706a018b67d9ac478`、journey=`231076e7bbe21434f3eddb117cb519af9f3f6de14833b35d3afd11cbf4e8c624`、RS log=`165fcc9811c5e757beca09b54bddd4f7c205cda781555684adb42ed8f242c8e8`，控制捕获与节点原件SHA一致。原 E §73／`e236037ef7`核收。原停容器、镜像／tar、卷和本人marker保留待修复；没有改写原result或无修改重试。

只读stat显示：CT108和05新worktree的源码目录0700、文件0600，04过门禁worktree对应0755／0644；RS Dockerfile COPY保留源权限，entrypoint由root降为gateway。此链支持准备环境权限根因，容器内底层ImportError未单独重演。原实施者正固定只处理公开tracked源码权限的新准备稿及新镜像／fresh warm；secret、venv、输入和原失败资产不放宽或覆盖。此为同根工具错误的第1轮修复准备，实际复验尚未执行；05 t1尚未开始并因同根前提暂停。

## 4. 样本矩阵与目标

| 组 | 当前实际执行 | 有效warm／测量 | v2 READY／完成、中位数／范围 |
| --- | --- | --- | --- |
| W3 MO | 原M24基线Submit失败；M40首轮RS启动失败；修订M40 warm在v2 Preview失败 | 0／0 | v2失败尝试221.885s；无成功READY／完成统计 |
| W3 FULL | 未运行 | 0／0 | UNKNOWN |
| W4约10% MO | 未运行 | 0／0 | UNKNOWN |
| W4约10% FULL | 未运行 | 0／0 | UNKNOWN |
| W4 100% MO | 未运行 | 0／0 | UNKNOWN，压力业务成功也须独立确认 |
| W4 100% FULL | 未运行 | 0／0 | UNKNOWN，压力业务成功也须独立确认 |

S3诊断起测与S6正式取证分开。保留S6 W3 READY≤60s、W4 READY≤180s、完成≤600s目标；100%压力档无性能门槛，失败仍报告失败。未形成1warm+3，不给正式统计或达标结论。剩余23项外置稿待首warm成功及原E复审，当前没有启动；磁盘须按首warm实际归档大小、现存原件和现场余量核准，不能自动删除保护证据腾空间。

## 5. 分项与结论边界

修订M40 warm已到完整负载v2，但在assemble步骤失败，未形成完整pair／bundle分段。该次已观察的MODIFIED上传投影为5.8700875s；比较、records/JCS、Parquet、Risk必要列转换、surface/bundle、native调用／输入读取／去重计数及v2 M40账本高水仍 **UNKNOWN**。D阶段两表六场景已核诊断只说明其明确有限范围，不能顶替本矩阵。W2没有行比较，不计入S3比较提速；真实0去重命中合法，不承诺跨表或FULL命中率。

后续只按实际v2操作／step窗口归属服务日志：compare-read/build包含native records builder及其中未独测artifact JCS；随后table/facts-core JCS另计；Parquet写属于records publication内部。Risk必要Arrow转换属于lazy view遍历时rules evaluation内部，digest/report JCS及artifact publication属于Risk publication内部，不能将嵌套值再次加总或用残差声称纯规则CPU。pair局部未观测的投影／bundle `null`不当0。cgroup各容器生命周期峰、进程RSS峰、操作M预约高水和host可用内存分列，各自峰不代表同一时刻总峰。

后续实际结果、修复复验和独审结论追加到本文；当前没有性能豁免、S3 E GO、最终新H绑定或阶段退出，tag／push／发布均未办理。

## 6. 首轮工具修复准备核收与进行中状态

原 E §74／`70bc1d5dfc`已独核CT108第一轮修复的**准备范围**：从同V1e和bundle新建umask022的运行WT，910 tracked公开文件／95源码目录分别核644／755，旧WT和坏镜像不动；强制native input9d4f、六锁0漂、clean、三镜像真实config／全DiffID及原marker释放0。18:39:08–18:40:29Z outer/node/capture0，直接原件`/home/dev/gdds-test-tmp/p6-s3-resource-repair-r1-1e669c053f/prepare-control/`：outer SHA=`e0dbed5c93495953023603cfbdf9a5b16ab782406eeb2281870c6495f658c0cc`、node=`380a26b8dce86e9cae23150c3573257472496854e6bf7810e4160b76abc97e86`、prepared-images=`0affc906dade8840daf419ed93bc23463dcbc317c1590b5aa16919bd646da1d9`。这是PREP_PASS，不是RS运行或M40容量结论。

未执行的旧r1warm稿因在释放标记后重hash大型tar被撤回；修订稿先在占用内封node核心result、tar SHA及manifest，最后删owner／rmdir，真实释放事件绑定封口SHA经stdout返回，控制端核原exit／远近原件／postflight后另封最终acceptance receipt。node pending快照不预填释放成功；postflight失败仍先捕获原件，再判失败。业务、输入和48/8/M40不改。固定driver SHA=`5bc3a65c1776e66808364a73d621be4981ef33b8a90458fa0606c3d521c20e54`、controller=`cd3d857f36766b03955b80ded88547567bff2e1e731f9222aac81b048fbdb956`，原E静审CLEAR后由同一Luna仅执行一次。

截至本节提交，修订warm已在CT108实际运行，监控观察到三服务ready、首业务前资源guard通过、v1 Preview成功，随后进入v1 Submit；**尚无封口完成结果、v2样本或本轮成功warm**。该监控状态不代替最终原件与独审。第4节仍为0有效样本／UNKNOWN，剩余23未启动。05默认32/8/M24完整功能证据另在累计交接逐档列出，不混入此性能矩阵。

## 7. M40修订warm终局、局部排序限额与新修复候选

§6修订warm现已封口：node18:48:18–19:24:07Z、outer截至19:24:12Z，原exit1，成功warm数0。v1 Preview119.097s、v1 Submit1658.57s及真实read／approve／Archive成功；v2 Preview从19:20:11.233Z到19:23:52.809Z失败，step尝试耗时221.885s，原诊断`RESOURCE_LIMIT_EXCEEDED`。**失败尝试耗时不是成功READY／完成样本**，没有启动后续23项。

直接原件`/home/dev/gdds-test-tmp/p6-s3-resource-repair-r1-1e669c053f/warm-r1-control/`：outer SHA=`026decbb0a245bc76cb303bf3675fa63030c40781305b1de3ed225b6f7eaccf8`，node stdout=`93bd357797d38f304993545d18b61b4b0e0410c0aa07b511d2967a62adc4b50b`，result=`06c0ad41e0aae2a0e1739b6b8534ab9d419228f73b57f138f658559d51431a72`，journey=`7e3201eaa15fe162777b4c8bab47d0f792ace8960c4346a72679622bd42dad33`，manifest=`8ffa2908b930d2513cee4cffad3de7631d88c26d1b17fbb4bdb463436b24cfb5`。原E §78／`1cba6b0331`已逐项对节点原SHA独核。

资源守卫与业务结论分列：同一worker的48/8/M40/N1配置、三服务开始／结束guard、全部OOM三键0、正常SIGTERM、当前镜像绑定、clean／六锁均合格，worker生命周期cgroup峰16,869,629,952B，host MemAvailable起67,335,496,704B／尾64,861,898,752B；这些峰不是原生排序charge或M账本。业务仍exit1、node sealed success=false、acceptance=false、warm=0，失败停资源与原marker保留；`resource_verdict=PASS`不能作为整轮PASS。

只读control DB副本诊断actual0，原E §79／`df50b0058d`核收：materialize_inputs attempt1成功，assemble_preview attempt1失败；持久message长度28、SHA=`0544e9a68fbb93babbd3c2708859535a3e67180a58f6d2393c78f6aa449677b7`，没有原requested／live细节。该SHA精确等于固定Rust源码`records sort budget exceeded`，出自`records/source.rs::build_family`六个局部排序guard；Python比较生产入口每表固定传`max_sort_bytes=2 GiB`，与M40独立。原E §80核收此源码归因。**不能将本次失败称为已证明的M40总预约拒绝，也不能靠单纯增M解除该固定guard。** 具体表、记录族、哪一guard及首次被拒字节数仍UNKNOWN。

可选checkpoint引用盘点首次执行被受控uv wrapper拒绝外部脚本路径，node／outer exit2，尚未读取checkpoint；原E §81保留其原件、未重试。该工具失败不覆盖前述原M40业务失败，引用盘点并非修复必要前置，也不绕过wrapper限制。

原E对局部设计`a01149fc…`给DESIGN_CLEAR：仅把已在Python M账本预扣并交同一Rust KernelContext的`native_budget`透传为排序上限，保留FULL JCS排序、全部增长前租约、M40／N1及现役512MiB输出／reader、2m记录／1024行组界限，无新开关或Rust／FFI改动。第一代码候选acb417只因低cap测试释放断言不可达而修订为 **`4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb`**，原E §83静态CODE_CLEAR；06 focused于20:14:04–20:15:22Z actual0并在§85／`1207de61b6`独核，native9d4、backend Ruff／mypy0、134 nonserial＋1 serial通过。原expected／golden和业务断言未回填新Rust输出。

新候选尚待集中门禁、当前产品完整fresh及新的W3 MO warm。旧V1e在05的t1–t4已各档fresh且独立PASS，仅记旧源功能回归；不冒新V4b0或M40性能结果。第4节仍0有效warm／0测量，23项及聚合仍HOLD；后续只有新合格warm、独审和实际tar／磁盘准入满足后才推进。
