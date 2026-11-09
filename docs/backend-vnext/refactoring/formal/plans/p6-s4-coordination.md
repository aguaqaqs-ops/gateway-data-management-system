# Phase 6 S4 持续协调记录

## 1. 本次授权与起点（2026-11-08）

Owner授权见[DC96](p6-s0-owner-decisions.md)，执行依据[kickoff](p6-s4-kickoff.md)与固定设计de0eb3a8b2。连续A–E，不重开整轮设计；SQL/阈值/事务/恢复冻结，实质冲突诊断后交Owner。资源上限32C/64GiB，具体档位固定独审、保其他服务和系统余量；M24原档和新档分列。

只读核查：main起点`a264697e8e432b33666ac659903d685f5c849b4e`，index为空，唯一tracked dirty为他会话`p6-be-q18-review.md`，无untracked。现有大量linked/审核/基准worktree均保留；没有S4 exit tag。实际本线程仅协调者活跃，工具最多四活跃槽；逐节新Sol xhigh实施/独审及唯一Luna max执行者，不递归。

Q18固定产品仍为a1ca3bad93；原报告已增加focused/容器脚本静审与语义修复，进程现场有06 focused执行，不干预。尚未核到Q18实际成功原件，不解除FE3c前置。S3原V774acf33a3/H685c97f4e2和最终报告0bf6454038仍为BLOCKED_CAPACITY，不冒用后续S4结果倒签。

本次授权落盘仅文档，container rebuild=no；无S4产品证据、无carried判定。历史S3镜像资格限原报告，S4最终Rust/backend候选须重建及适用Compose。起点节点检查仅只读，不构成预约；执行时重新核标记/全机进程/端口/缓存。

## 2. 路径和提交协调

协调者仅提交本任务明确路径，不使用git add全目录。A实施者拥有A接口/Contract/独立向量及handoff；审核者只在固定clean detached WT读取，报告在WT外交协调者。S3共用kernel/import_publication/driver写入须按现场顺序，不接管Q18/archive/FE。每节固定候选、原审findings与证据核收后继续。

## 3. 逐节状态

A：产品fb9c7fbcd95b411d7598ade2a93bc8a7e6514697，原审A GO，05 focused151pass与五包静态0，详见[A handoff](p6-s4-a-handoff.md)/[原审](p6-s4-a-review.md)。B：产品788ed36e7742a067bf01c16ad2e6aaed2fed91fb，原审B GO，04 focused209+3及850表差分核收，详见§8与[B原审](p6-s4-b-review.md)。C：产品48053253f9a3c46b0d227167a4d0ca1f8ad94bf3，原审C GO，06 Rust207及focused318+4，详见§10。D：产品41d1944208fe99911df0a15641ab651505d1274c，原审D GO，06 focused327+18，详见§11。按DC96直接进入E；最终权威/Compose/真实/资源性能待实测，尚无S4 exit tag。

## 4. A核收后的并行事实

main期间新增Q18 `94b25a3279`（真实旅程/三Compose helper只投影selection双字段，原独审及节点由Q18负责），和S3 `99254318c8`资源方案文档。A source fixed fb9c只核本节六文件，不冒用Q18 CLEAR解除FE前置。最新[S3资源方案](p6-s3-resource-profile-plan.md)拟48/8/M40、保持生产默认；明确不写import_publication.py或table_access/kernel.py，S4 B可按既有owner处理kernel最小自检。S4最终增配档尚未选择，不把S3方案自动算本阶段通过。A新增共享fixtures会进入包闭包，E按实际闭包准备六包集中验证，不能用跨节点旧来源口头carried。

## 5. B首候选、原审与调试失败

B首个固定候选`43a8f1e16592ae9726d019e73a2c65a4d03253ec`，直接base`e76342ef0b58bb0120fc60d8a063d838140ee28d`含S3资源档产品；本节20文件是storage core/native/共用policy/context及测试/精确FFI登记。Rust tree=`5b87acea208ec03af3e22c1b6a61b4f584eda059`。新B原审在clean detached WT静核，报告[p6-s4-b-review.md](p6-s4-b-review.md)，**CHANGES_REQUIRED**：B-F1真实输入backing同M/最后owner未接实，B-F2 schema/count冒称完整身份/NOOP风险，B-F3 native与唯一policy可比条件分叉，B-F4输入batch头部先分配后预约。rebuild决定后before/actions早释放也须在后继接口接实。均属职责内实现修复，非Owner设计冲突，不进入C。

原审允许唯一Luna跑首候选小fixture focused调试，05实际17:25:36–17:26:01Z：fmt **1**（格式diff），clippy **101**、workspace test **101**（同E0618：局部usize `indexed_rows`遮蔽函数，230→258/275）。三步实际执行后停止，未运行native重装/五包静态/Python/真实逐表差分/Compose；不得写成这些项已过。起止HEAD43a8 clean、六锁无漂、node/outer1、capture0、marker释放0，17:27:20现场无构建/测试/8000/运行容器，原件与WT保留。此为产品源码/格式失败，不冒工具故障、不无修改重试。

原件`/home/dev/gdds-test-tmp/p6-s4-b-plan/controller-43a8f1e165/`：outer SHA256=`097660e1215789933580dbedce4772373126bcfcc2998b7ff6f18600e0937470`，captured/focused.log=`ae385835712c1ef48f9211ce8bc9fdba2a665e10e4adba6f1c673f971efb9080`，与节点sidecar同值。后继实施接实既有canonical reader/进程内stream lease的来源、绑定、费用及最后owner，不建新持久证明/协议；由原审连续复核，再固定新候选/适用脚本。

## 6. Q18最新独立核收与S3写入

并行Q18报告`27eab454b7`/最终交接`964d900d44`已核固定产品`94b25a3279`为 **BE-Q18 GO**：06增量focused74+3、五包静态与四项当前候选Compose均核收；source/原件见[Q18 review §12–13](p6-be-q18-review.md)。FE附加生产OpenAPI抓取curl7/HTTP000仍缺失，不称快照已交付；FE刷新类型与前端真实e2e仍由其owner处理。S4不把Q18证据当自己的Rust/SQL/真实性能通过。

S3资源档产品`e76342ef0b`已在main，修改settings/Compose、worker资源测试和real_dump_journey资源CLI/守卫；B未写这些路径。新资源档和S3-only实测仍由S3原owner独审/执行，S4最终配置须独立记录实际值。S4 E继承当前driver时核精确SHA/差异，正式组同worker/配置守卫不删，S4结果不倒签原S3 V774成功。

## 7. B修复、已通过项与未完成项

原审继续提出B-F5：可变长cell/SET声明metadata解析的同时驻留上界不足；实施者补分阶段预预约、checked容量、同operation真实input owner与完整manifest绑定。原审静核为修复已就绪，仍须实际focused及t1–t4逐表差分，不以静审代替B GO。

05后继调试均在各自clean固定WT、日志/target在外、offline、本人marker内执行；原件保留，不将任何整次非0记为权威包通过：

| 候选/运行 | 实际结果与停止点 | node focused.log SHA256 |
| --- | --- | --- |
| 83fd51aeade5 / r2 | Rust tests207pass；fmt1、core clippy101，Python未跑 | df32403ac2eded3e4be6faa61587033199d99d2842baa7d431c21fc8630adc75 |
| b9c8783cdafc / r3 | fmt0、Rust tests207pass；adapter clippy101，Python未跑 | cd4678ef3bb50c60e79689c90af4408526d16b55058b65764a34d68baf297524 |
| b7fc36b2d922 / r4 | clippy0、Rust tests207pass；alias格式fmt1，Python未跑 | e687fdeec3d74287e2dd01da44d9c263baadeaf41a6d56c87be5639e2039bd4e |
| ece2ec745fd1 / r5 | fmt/clippy/tests207pass、native强制重装及build-input0；前三Python包ruff/mypy0、backend Ruff0；backend mypy1后停止，RS static/六focused未跑 | b2af25679405a7f87c76f90f53ba6b3da2dfad52809dc932245a5ffb40d81826 |

r5起止18:15:58–18:17:51Z，Rust tree=`fdfe6daed59cb58d5c2aa7c39fa3cccba94424d2`，clean/六锁不漂、entry/final/outer1、capture0、marker释放0；18:19现场无本人测试/构建/Dolt/8000。其outer SHA256=`927361995595623984a6d659d18dda42240f7e694ba00490c07dfd7b49926323`，原件目录`/home/dev/gdds-test-tmp/p6-s4-b-r5-ece2ec745f/controller/`。

r5失败是两个Python文件的typing源码问题，不冒DC68工具错误。修复后按实际Rust tree决定受影响复验，不无修改重跑、不宣称失败整次可按包carried。t1–t4 driver还须固定metadata/census摘要、验证完整manifest、独立断言diff资格及净计数存在性；其InMemory与临时旧Python oracle仅供差分正确性，不是生产容量/性能证据。B仍未GO，C–E依赖未放行。

## 8. B实际核收与C接续

B最终产品`788ed36e7742a067bf01c16ad2e6aaed2fed91fb`，原B独审报告已原文归档，SHA256=`bcf325e72bd5a8c48f4c69b8558b9d1c515de3c392e874cb9c830f37dcd68bd5`，结论 **B GO**，F1–F7在B范围内闭合。B实施/原审连续修复及原件见[B handoff](p6-s4-b-handoff.md)、[B review](p6-s4-b-review.md)；全部历史失败仍为失败，不由后继成功倒改。

后续真实数据先后暴露并修复fresh writer缺canonical profile（F6）和fresh profile UTF8物理序与manifest/cached declaration序不同（F7）；共享SnapshotMaterialization view owner供Comparison/Storage双消费，保同M metadata/BIT charge、partial profile拒绝与原S3输出。未改manifest、原输入或SQL/golden迎合。r7外部脚本被uv-consume拒绝属工具错误，r8 stdin修复解除；其后的真实产品失败分别归因。r11 05仅一次busy预检exit2、无staging/节点执行，05当时为S3有效占用，不抢占；04新运行不搬05缓存/包沿用证据。

04 `gw-dms-test-04` r11在clean edfa实际跑Rust fmt/clippy/workspace test三步0（tree fdfe6dae），focused因新cached用例遗漏已有operation-lived manifest AST收费而失败，原件SHA=`e439172505db084aa74d21770d3e76456a584387872508423ce9ee18918a408e`。788只修测试精确结账，保生产收费；04 r12 **未重复Rust三步**，同树先前调试结果不是正式包carried。r12实际19:08:45–19:15:14Z，force native reinstall/check0、五包ruff/mypy十步0，七文件非serial209pass、serial3pass；t1–t4共850表全0。入口/最终/outer/capture均0，起止788 clean、六锁不漂、marker双释放0；19:16现场无测试/构建/Dolt/8000/运行容器。保留本人WT/target/log/input，不清既有carried或他人资源。

原件`/home/dev/gdds-test-tmp/p6-s4-b-r12-04-788ed36e77/controller/`：outer SHA256=`21ecf1714eba271a4c444590d19d0816ce7cfc3f846a762247e4b2b80feb340d`，captured/focused.log=`8fb0db9d7cde02e24d503859dab845295dee655b5abdf9f38f5448a5cce84e28`。按tier表数125/220/193/312；NOOP/PATCH/REBUILD分别121/0/4、159/1/60、139/0/54、285/12/15。实际完成diff的表43/88/71/138均与旧Python oracle独立D/U/I及整数阈值逐项一致，其余`net_counts=None`，不伪造全局净计数。八冻结包、metadata78c7与census733b摘要先核；InMemory/oracle/M24读数仅差分诊断，不是生产M24容量或完整旅程PASS。

C须解决prepare reconcile缩小Python native charge后新render分配的同M预约/封存，不能直接二次消费原Rust剩余额度。C接唯一Rust SQL与两个显式context facade，D接实际Submit并删除旧热路径及两项临时unreachable登记，E才核当前镜像/Compose、完整权威包、真实旅程/资源/性能。C用全新Sol实施/独审，唯一Luna执行者复用；不再申请逐节开工许可，不进入S5或倒签S3 exit。

## 9. C当前修复与独立预期

C首轮固定候选`ccc46f4a6d`之后，原C审核者在clean detached WT连续审查，尚未给C GO。显式context消费者迁移`bbb9063de5`保留实际调用方、原SQL expected和publisher；Rust renderer/facade不再以Python算法为生产fallback。当前职责内修复包括：大单行prepared-row/有界chunk输出、同表累计200MiB cap与M错误区分、转换graph预预约、导出bytes最后消费者收费、cursor/input引用释放，以及schema真实SQLcap和内存上界分离。仍是实现修复，不重新打开已清除的设计，也不把编译或focused尚未运行写成通过。

固定旧S1a renderer`7d0ce6220ac2541b76ab75191d43ce6113003966`源SHA `761bb6097166edd8720921ca1baa0fc53269404512395af1dec1097cee273cc7`；04原子占用下受控捕获已由原C审核者核收。四组DELETE/UPDATE/INSERT的257行及4MiB交叉窗口expected已登记在`vnext/fixtures/vectors/mutation/sql-replay/v1/batch-boundaries.json`（`ab2c86f52f`），原件`/home/dev/gdds-test-tmp/p6-s4-c-old-sql-capture/controller/`。outer SHA `3a0c0538ae68c33c500a0281a20a1cdce719e07aa527db1fa40497ea44611478`，node log SHA `77d8395e0f506b7c8ec2eb6e2b23616b3ae2dbdd09488c4a0548eb5d4618a114`；这是旧SQL字节来源，不是C或Dolt性能证据。

`a1a1e1bfa5`另登记手算`replay-cap.json`：单UPDATE含200个非键列和长度1,043,309的string key，SQL总长`201L + 10,033 + padding`；padding58/59分别恰209,715,200/209,715,201字节。原C审核者独立复算一致；新Rust输出不参与expected生成，不改六份既有SQL golden。C新固定候选及精确脚本复审后才由唯一Luna运行Rust三步、强制扩展、五包静态和受影响focused，失败先停保原件。当前没有C权威包/Compose/容量或性能PASS；Rust/backend镜像重建延至E最终候选。

C r1固定产品`282b379d1756d71e73a1c3f2fedd2b12bee6cea6`、Rust tree `18fe638012d909a2c542aee3c167e3b711c860aa`，执行稿经原C独审CLEAR，04于20:21:24–20:21:31Z实跑：四Rust stdout格式制品均0，workspace fmt1、clippy101、test101；后二者同为`decimal(value: &Value, kind: &str) -> &str`的E0106借用来源不明。三步均实际执行，之后停；扩展、五包静态和Python focused均未运行。起止282b clean、六锁无漂、入口/最终/outer1、capture0、marker双释放0，原件`/home/dev/gdds-test-tmp/p6-s4-c-r1-04-282b379d17/controller/`，outer SHA `8d19eab733616066561114910321d3b4593326f5afdc0837c76060cf92cf96e4`，node SHA `ffc30242a9b9c2275513ae43bc2011e2db686699c611cb3ac2ff56af2caddfba`。源码失败不冒工具错误。根核四制品source/result SHA后纯格式回填`5613d11a88`；原审同时要求删除无消费者的整段literal分支、内部长度/预算不变量错误不得映caller能力错误，修订固定后再复验。

r2固定`a4f3f8478e157ab5fe18ab149833696732c599c2`，04 node起止20:26:10–20:26:22Z：四stdout格式制品0；fmt1、clippy101（两处`manual_is_multiple_of`）、test101（PyO3 `adapter_boundary`要求`PyResult<T>`，closure的String错误尚未转换，E0308及其推导错误）。Python仍未开始；clean/六锁0漂/本人marker双释放0，原件`/home/dev/gdds-test-tmp/p6-s4-c-r2-04-a4f3f8478e/controller/`，outer SHA `dc179dbe48ba2d360f53d6a0026256df9bfc4a368411f3ac3946e7320de63d95`、node SHA `a2660c61a1c34671c59e21be50c617d3fec5588aa190496ac03a47a181de0e94`，原C独审已独核。格式回填`dd98f6cbc7`后，修复候选`5ee3b39d74b845452aba5b19f46c81dbf71692e4`集中映射String→PyErr，保SQLcap/M/stop/internal分类，并补大型schema/同shape run循环的有界取消检查；后继r3精确稿另审，不把前两次失败算成测试通过。

r3 `5ee3b39d74`于04 20:30:35–20:30:50Z实际Rust test0、207通过，fmt1仅adapter格式、clippy101仅一个8参PyO3桥；Python未跑，整体仍1。node SHA `a220cda8b8dbb574c7279311b62808bf1aeb10978e01856470021b24805bce1c`、outer SHA `4eaed179f8a0d9874332d7422776c28cf2cc69d0f2955807b0475c67e1057cf5`。纯格式`b420bc4f20`及单函数窄lint例外修复`ae0abb960c2fd97df5b5eecbfedc25f794ac1288`由原C复核。04在本人正常释放后由S3合法占用，05亦为S3有效prepare，已审r4-04稿**未执行**；DC91改06，未搬04缓存或判跨节点carried。

r4在06 `gw-dms-06` 20:34:29–20:36:23Z实际Rust fmt/clippy/test全0（207）、强制扩展和build-input全0，Rust tree `4f20f7e13c48f327a7f9bc2264b0311f536ef6c2`；前三Python包静态及backend Ruff0，backend mypy因根新增controls测试三处导入/类型问题1，RS静态及focused未跑，整次exit1。原件`/home/dev/gdds-test-tmp/p6-s4-c-r4-06-ae0abb960c/controller/`，node SHA `8d881052ffd191eaf790dd13bb4ec4f77bcbdecb850b1f4a942689cfa00f905d`、outer SHA `67e44c934c4d2132bf99fb08916089297714f6d9983fa0fedfb69cf82f74b4b8`。原C已独核clean/六锁/标记收尾和上述分步结果。根测试修复`15ea2c9eb0`后，`f433bbd6d9`另按原审补generic closure manifest summaries驻留费；r5保持同Rust tree、同06，仅引用r4三Rust为调试结果，重装扩展、五包静态及13文件focused实跑，不称正式包carried。

r5 `f433bbd6d9`在06 20:39:50–20:40:46Z五包静态全0、nonserial315过/3败，serial按失败停止；两项旧native测试误将导出SQL 97/143B的scope-lived费用断为0，另一17MiB测试尾部多写opening quote。原审及根核源码/原始断言后，仅测试修`9c08623dd1`，保手写SQL字节/最后输出费用和scope归零语义，不改产品或golden。r5 node SHA `894bda6cede048c3ea16234c3b2154656f1ad36aeb5c992887597b58d7205340`、outer SHA `614fb86a9c2375d8838676f38c919e9f4b5016602d790e41e0443725930a80cc`，原件保留。

r6 `9c08623dd1bd5f55a7ad6021883002efa9607f56`在06 20:43:26–20:44:29Z实际forceextension/build-input0、五包静态全0、13文件非serial318及serial4全过，entry/final/outer全0、clean/六锁0漂/本人marker双释放0；原C与根已独核。node SHA `ed90fb215bd27832f7b4700b4ea3ad7efcb8ca07028d3b18c61c7c805d7ddc9c`、outer SHA `fffdff9dffc8306f2e81dc81b2ab21ab13d3755dcab59de6a10940745bf01040`，原件`/home/dev/gdds-test-tmp/p6-s4-c-r6-06-9c08623dd1/controller/`。这仍只是C focused成功，不是权威/Compose/性能或S4 exit；原审随后核实施者自查的UPDATE after-image键literal冗余，`48053253f9`改为零heap键槽、CASE/WHERE复用唯一key literal。新Rust tree `e2a901417b19259ece669637a41545e774261445`必须r7重新Rust三步、强制扩展和focused，不能冒r6为新树通过。

## 10. C最终核收、D接续与S3路径预约

C最终产品V=`48053253f9a3c46b0d227167a4d0ca1f8ad94bf3`，handoff最终H=`f4d9e19ac966a9b96d5587bab284bc25a36c4c22`（原bb0790仅被后继纯措辞细化，不改写历史）。原C审核者已在clean detached WT逐一核V/H六包tree相同，并给 **C GO**、所有C源码finding关闭；原文报告[p6-s4-c-review.md](p6-s4-c-review.md) SHA `8df7d838a7ca60fadf1fd26a77da6bd3afbbe9ca6ae825adaa0314abf969ec81`，未由协调者改写。

06 `gw-dms-06` r7于20:49:05–20:50:21Z实际Rust fmt/clippy/test207、强制扩展和build-input e2a9014、五包ruff/mypy、13文件非serial318及serial4均0；entry/final/outer/capture均0，起止480 clean、六锁0漂、本人marker双释放0。原件`/home/dev/gdds-test-tmp/p6-s4-c-r7-06-48053253f9/controller/`，node SHA `fb07cb17000a0c584f38f06ca4e124d9ab6364e5fc0b2a6323ed268c9e16fb27`、outer SHA `41f7068eb86bf8761a5ddf2b162f627a5d76e8a79c63c67314ca29a7410c92a1`。四格式source=result，无额外回填。C全部历史失败及WT/target/log保留；06当前本人资源正常释放，已有来源和他人资源未清。此GO不覆盖生产Submit、组合DDL+DML cap、最终六包/Compose/真实/容量/性能；最后C image revision/source-tree仍none，E最终候选须重建与适用容器门禁。

C实施/原审已完成本节职责；D新Sol xhigh实施者与独立Sol审核者接手唯一Submit生产路径及旧热路径删除，唯一Luna继续专用节点执行。S3原协调者已申请并获短期独占`comparison/production.py`及两份`test_comparison_s3_c_arrow.py`/`test_comparison_s3_d_production.py`，用于把隔离4b0的已预扣sort预算最小移植到main；D避开三路径，收到固定移植候选/释放后才核实际集成，S3-only取证不外推为含S4的main或倒签原V774成功。当前无S4 exit tag，不进入S5。

## 11. D核收、真实消费者与E证据接续

D最终产品V=`41d1944208fe99911df0a15641ab651505d1274c`，文档H=`9d91653ac96908cc9cafe159fcb7b76a5a3525bd`，原D独审 **D GO**、F-D1–4关闭；报告[p6-s4-d-review.md](p6-s4-d-review.md) SHA `6ab8e80e37a042ec89c9c5a98d94709b6882f083466c6bef4f35cf544db8badf`，原文归档。H2相对V仅D handoff和S3原审文档，不把S3内容纳D结论。Submit现在用真实逐表storage task/summary/共用policy/SQL，再合完整DDL前缀与DML交原publisher；旧Python行graph、import replay wrapper/专属类型和mock删除，保generic library APIs及实际checkpoint/readback/外部ledger消费者。

原审首先关闭了非INITIAL parent读取依赖runtime ruleset的问题：frozen storage-only请求明确`ruleset=None`，从完整parent binding取storage key，普通comparison路径保原ruleset；full catalog、exact commit、count/content、同M backing不减。合法冻结A与实际runtime B不同的非INITIAL100行/1改回归接真实committed reader/native PATCH，错commit/count/content拒绝；没有造回已删除函数alias的probe。无consumer的Submit-only base digest入参删除，外部ledger同名字段保留。

Ce首轮06 21:26:30–21:27:30Z五包静态0、nonserial326过/1架构失败、serial未跑，node SHA `f46ac480f7aaac9ebc1645933833eb83b83821a819de9c13883c728cb4eddcc0`、outer SHA `298a6e3b9e6bfe771ee139ff23191d5bdd74f6385c89ee753d45b650add1ea16`，原失败保留。原审核明generic `_planner/_changeset/_artifacts/_digest/_repository_replay_renderer` 当前无app/worker运行consumer，external target仅消费DTO；Owner明确保留standalone API，所以按原架构规则以精确5项永久library seam及退休条件收口，不造生产调用、不扩大root图。B临时`storage/native`项已移除。

41d复验06 `gw-dms-06` 21:32:59–21:34:21Z实际forcedextension/build-input e2a9014、五包ruff/mypy均0，16文件非serial327、serial18均过；entry/final/outer/capture全0，起止41d clean、六锁0漂、本人marker双释放0。原件`/home/dev/gdds-test-tmp/p6-s4-d-r2-06-41d1944208/controller/`，node SHA `746e81deb09450194960a823971c198f3f736a514f331677537a958824adc0df`、outer SHA `5c12eb21a7777cfcff473fe7a8685b11a16af097056efdbc3b1590197452b847`；Rust源未变，C r7三步仅作同node调试参考，不是formal carried。日志的`native_calls=2`仅coarse prepare/render入口，不是所有FFI/chunk pulls；`parent_read`不包含frozen after IPC打开，E按明确口径报告。

S3已完成主线最小移植`1ecb17f6de4c71ddb001a6829d2222cd28bacb34`并释放三路径；06 21:01:08–21:02:29Z affected focused134+1、backend静态/forceext0由其原E独核，来源`/home/dev/gdds-test-tmp/p6-s3-main-port-focused-1ecb17f6de-fixed/focused-control/`，node SHA `aff29570a93d3d0a24f2dd0ad98ca29d382bb216915575ad989b8501d2f63ebd`、outer SHA `955b53d3607d9026b2b4da11ebce39e02a4ca33d88124ef61b7978b2c0a15e1e`。仅该main接口移植事实，不等于隔离4b0或原774的容量成功。S3另明确把main `real_dump_journey.py`交S4 root准备Submit测量，隔离4b0/固定driver/输入和原件均不动。

D角色完成职责后E用新实施/原审。root在D期间仅准备了未提交的journey度量/测试两路径（不在D被测V/H）；E先固定独审这些输入与命令，再集中当前候选六包、镜像/Compose、DC33真实旅程/正式统计/S1a复核。资源保持原M24归因与授权内固定增配档分列；没有这些实际原件前不签E/S4 exit，也不进入S5。

## 12. E独立预期核收与集中验证进度

E当前实际候选为 `c9e9b3e74ab2e2895f9e0f6aac78740e7f48f008`（Rust仍为 `e2a901417b19259ece669637a41545e774261445`），原E审核者已在clean detached WT静审CLEAR；这不是当前产品、资源或性能PASS。`875ed92ad42de4675a2e6c33e9c1354990c48750` 固定了实际Submit请求开始到技术main核实前移的保守计时、Repository三类mutation ID的重复上传零新操作证明、独立schema/选表多重集内容核验、正常停止后的本人三卷原件归档。合成MO明确跳过repeat-v1以避免该额外baseline预热，FULL与官方四档保留repeat；两种条件分组统计。fresh两次Submit分别必须有table→summary→publish→readback，恢复专用checkpoint_verify仅记录，不要求fresh出现。仅本轮固定增配档N1/envelope48GiB/reserve8GiB/M40GiB用于计划中的28次功能及正式旅程；实际worker/cgroup尚待运行，不冒原M24成功或更改生产默认。

06的旧S1a独立控制捕获已由原E审核者核收：2026-11-08 21:58:20–22:20:02Z，在旧 `7d0ce6220ac2541b76ab75191d43ce6113003966` 的clean WT/锁定环境重建冻结t4样本。原CT108历史scratch已经不存在，本轮是固定旧generator受控复建，历史JSON SHA为 `0b61f8c7d373a89776bcc3489a9aa143b3e6a7383a5fda2273a178bf1b5a162d`。重现9822→9828、自然13加85合成变化、总98=92UPDATE+6INSERT；旧PATCH为36,238B、SHA `2663cf81f62fb1b490c400ca1adfa11258e64e6abd0cfb8b7c277f49ea66636b`，旧REBUILD为1,576,977B、SHA `3ede2a8bc05a3234fe98ff9cafd90c3d185fc83b6b9cc0f003e7bfdf547b7131`。raw SQL、base SQL、typed rows五实体均按封存清单复核；capture JSON SHA `d8b515bd4cad57d7270cede61091987e6e793dea476915d145dc178c687654cc`。原件 `/home/dev/gdds-test-tmp/p6-s4-e-s1a-fixed/controller/`，node log SHA `a2b0ba940abcab6f8f04ecdf80f2a63d230078a1acb6599bac00b1f7367520ec`、outer SHA `4b61323b468b93b3bc1f4b4e8d6b5a68e52940a0e1ba89f6773e4505efed0abb`。入口/outer0、六锁无漂、起止旧HEAD clean、本人marker双释放0；结论仅 **OLD_EXPECTED_CAPTURE_PASS**，当前native/Dolt复核未跑。

04另一全新旧B WT `788ed36e7742a067bf01c16ad2e6aaed2fed91fb` 的独立控制也已核收：22:17:10–22:20:57Z，标准八个及合成六个dataset occurrence共14case均0，逐profile单独封存schema/行数与keyed/ordered/keyless/composite选表typed-row多重集摘要，防同dataset ID跨输入根覆盖。13个合成输入文件使用已接受manifest `cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3`；未调用新SQL/native diff来生成expected。原件 `/home/dev/gdds-test-tmp/p6-s4-e-b-expected-control/controller/`，report SHA `373c6e9558e3b9b1777dc777a096d2a6bc46bfcc4f0e2624dca7d70ecf3cb7b2`、36实体manifest SHA `79f41a121a2f6d4eb94cc338778457e2b7b229c465b98537812f4ec5906148be`，root和原审均逐项复核零失配；入口/outer0、oldHEAD clean、marker释放0。七个profile的expected JSON为后续真实Repository的独立输入；结论仅 **B_INDEPENDENT_EXPECTED_CAPTURE_PASS**。

首轮集中稿在 `ea096ae81ff48958635e1eaae0554f36485cfa0b` 的全新04 WT实际执行至backend mypy停止：22:25:58–22:27:49Z，driver布尔返回的no-any-return与测试间接访问journey.httpx的attr-defined两错误；不是工具DC68错误。后续focused、权威runner和Compose均未开始。原件 `/home/dev/gdds-test-tmp/p6-s4-e-final-ea096ae81f-fixed/controller/`，node SHA `33f1e12b73fe76f60bc7c09401ebb2be56267e62e9dcf3c084415fede57760b5`、outer SHA `99651290a2ac734162823a51b400ed7ef6bb4bf421c849a460386e8bae9426ae`；入口/outer1、六锁无漂、HEAD clean、本人marker双释放0。c9e仅修这两项类型问题，未加ignore或更改预期，原审已连续复审CLEAR。

04 c9e r2完整固定稿已获 **SCRIPT_CLEAR_FOR_c9e_R2_FOCUSED_ALL_SIX_COMPOSE**：`/home/dev/gdds-test-tmp/p6-s4-e-final-r2-c9e9b3e74a-fixed/` 的run SHA `31b7396bcfc4ab6a3d1fcd87a1a2b58573539c25de1a8f1cf82dd1fd07fabe10`、node SHA `acde2c336a03f50eed7e5ba7860ff077e483038a223a6c9539dfc993db959fd2`、assets SHA `4d1219cba9f5b05cf2176a253412b0fc236e7ae152043271d6da0502eb090975`。22:31:48Z唯一Luna已启动，使用全新WT、tag和日志，仅同节点复用旧Cargo编译缓存，不carry任何测试结果。五包静态/必要focused后才全六包权威入口与当前HEAD normal Compose build；任何非0停止。实际结果待原件核收，当前无权威/Compose/真实旅程/资源性能PASS、无S4 exit tag。05准备亦须固定c9e与精确脚本独审；原S3基准、carried WT和原件不改，S5未获授权。

## 13. E 当前DC97口径与后继候选

Owner在本轮直接确认采用[DC97](p6-s0-owner-decisions.md#dc97-性能可靠测量与节点协调补充owner2026-11-08)：5/2/10分钟目标继续逐次报告原秒数和达标事实，纯数值超目标不阻止正确且有效的样本进入1预热＋3测量统计，也不单独阻止S4退出。缺失、负数或非有限计时、技术main未前移、Repository/业务/冻结产物/资源硬边界失败仍拒绝；100%压力档只报告时长。此前c9e的数值超目标即抛错口径须由E最小修订后独审、受影响backend/RS及当前镜像Compose复验；旧c9e的05 stage2/queue脚本尚未运行，不将其静审CLEAR当新候选的实际结果或自动沿用。

## 14. E 已核收的 c9e 权威与 S1a 组件原件

04 `c9e9b3e74ab2e2895f9e0f6aac78740e7f48f008` 于22:31:48–23:04:30Z实际完成五包静态、强制native e2a/build-input、focused94+3及全六包权威入口，原E审核者独核 **04_FOCUSED_ALL_SIX_CURRENT_COMPOSE_ACTUAL_PASS**。Rust fmt/clippy/test全部0（207 tests）；shared_kernel261、repository_contracts152、repository_client161；backend3497+77；repository_service1764+既有skip1、serial214。整次runner0、起止HEAD clean、六锁无漂、Hypothesis按包清理、本人marker双释放0。原件 `/home/dev/gdds-test-tmp/p6-s4-e-final-r2-c9e9b3e74a-fixed/controller/`：outer SHA `6dd184fd1a23c31481f52d74f1918da627f958ba4b46f08d1b4f3b62ee1a3140`，node `9e6509b6adbb8a208e301471d321c766c605367d55051610a73e86100f19d85c`，runner `a32acbdb407b3059222ad786dfec4c98b7a581195d549f4ea741a790fcf4baae`。同次正常Compose三服务本机image ID已绑定保存tag；04 runtime tar实体SHA `da3d8ac19dac74638637768a8ebb8d62aa65cfe4b4bc9e1beba4143803960ef3`，identity JSON `dc73d0fde179be6ff8ce0299248889983f48104d7c6382907654ff0437d257fd`含config digest及全部DiffID。此为c9e历史实测，不能自动写成DC97后继候选当前包或镜像PASS。

05 S1a r4于23:11:40–23:12:36Z实际通过，原E审核者独核 **S1A_GENERIC_RENDERER_PRIVATE_DOLT_ACTUAL_PASS**。原件 `/home/dev/gdds-test-tmp/p6-s4-e-s1a-current-r4-c9e9-05-fixed/controller/`：outer SHA `dbe201fbdd0e0a4d88a8eabd679e64288b152e0c78d2641704d31eae634b5f98`、component `913e0b89f7fa1a747665ac031738673b1dcc98a48f77fcae7c83090c5d60ecd0`、result `bb7c9e5b44c9841714d10bda670b743588c28de2e795f6b150abf08ecd264544`、19实体manifest `c729d912981b79fec8a777d0da999214c363a3db7d0f1b71d0890c60b3749004`。两完整generic计划与唯一Rust SQL/schema facade输出同旧SQL逐字节相等；private Dolt2.1.11交替1warm+3，两路均9828行且表hash相等。PATCH正式秒 `[0.3154786308296025,0.31754007702693343,0.32211968721821904]`，中位 `0.31754007702693343`；REBUILD `[0.7705712681636214,0.7759391567669809,0.7827327148988843]`，中位 `0.7759391567669809`，范围分别取各数组最小/最大。after的合成no不满足正式canonical连续性，因此此项只证generic planner/Rust facade与private Dolt，不能冒native StorageTableTask、生产Submit或worker容量；r1/r2错误入口适配、r3字段错误的失败原件全部保留，r4是DC68第三轮有修订复验。c9e→6786未改该组件源码，后继可明示来源/不变影响面，不冒权威包carried或新生产实测。

## 15. DC97 固定新候选与节点进展

新产品与执行文档候选 `6786b28a3506feab3d8eac7d1288c8b22525bb8f` 已获原E审核者clean detached静审 **SOURCE_REVIEW_CLEAR_FOR_DC97_6786**。相对c9e仅改backend benchmark计时判定及其8个focused参数用例；保留真实有限原值/冻结目标/met，拒绝负数/NaN/Inf，纯数值超目标继续后续业务与资源核验。SQL、Rust、生产Submit、默认N/M及S1a通用组件均未变。

04固定稿 `/home/dev/gdds-test-tmp/p6-s4-e-dc97-6786b28a-fixed/` 已逐字独审CLEAR，run SHA `a69d91262c849c8f0e222cea4ebea84eb3b19a6034ac36f1ee915681a2ff823b`、node `97ccf7f2157a60f1671310216aa4134a2e1b220840ebe936b0a820f39fb80ac0`、assets `43391cd837ee8288836ecd6ff6d22ee14d7fb1ee2780a6a631568b3005159bcd`、bundle `c0df7465725e743825a284ec3c049084af89ce5818c03722e04ce8acbcfe5e7c`。唯一Luna正于c9e原来源同04同WT/env实际比六包闭包，四包判可沿用时直接指c9e原始合格runner，受影响backend/RS实际运行及当前新tag正常Compose。23:52Z已过五包静态、native强制重装/树核、8focused与backend非serial3505，串行/Compose及RS仍在进行；整次权威与镜像原件未完成，不提前标记PASS。

05新6786独立sourceprep已实际完成并由原审核收 **05_6786_SOURCE_PREP_ACTUAL_PASS**，仅源/env/cache。原件 `/home/dev/gdds-test-tmp/p6-s4-e-05-6786-plan/source-prep-control/`，23:38:21–23:40:02Z，outer SHA `96b6ebc71569c2254f3dc8dcab539f9124ec60777c67949498f9d4782481ca81`、node `8d65497afb9e0befa479533ba279e9a8aa05d2a93a19c8773cff68aecb275b31`；native e2a与dependency-base config/全部DiffID实核、六锁无漂、clean、entry/outer0、marker双释放0。旧05 c9e stage2/queue均未执行；新6786 stage2资产待04实际新runtime封存后固定独审，28完整旅程尚未开始。05 CPU只读预检发现systemd leaf不暴露cpuset，外部新queue已改为记录真实祖先约束链/affinity/32CPU及每组一致性，未派运行、不计DC68失败。当前无S4 exit tag，原M24与增配M40/S3-only/S4来源仍分列。

## 16. 2026-11-09 权威封口、镜像修复与真实旅程调度

04新6786权威稿已于00:08:34Z自然退出0并由原E审核者核收 **AFFECTED_AUTHORITY_COMPOSE_ACTUAL_PASS + FOUR_DIRECT_CARRIED**。五包静态与8focused0，backend3505+77、RS1764+既有skip1+214；另四包在原c9e同04同WT/env实际闭包零变化，直接引用c9e合格来源，不写成6786重新跑Rust。原件 `/home/dev/gdds-test-tmp/p6-s4-e-dc97-6786b28a-fixed/controller/`，outer SHA `2d4cdff9bb7463e1e02d4d4646c2a4615090a670c5482688e3cf3860ec7baae1`、node `79713c20e94cb89efd231e5a44236883821072f0579c808519a1f0eff41c4b12`、runner `7e4a066156890ab8cbca03b4e6fbfed6bad17682e1fde4eceaae322c592128e5`、identity `1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`。当前正常Compose三镜像config/全部DiffID及容器本机ID绑定通过；实际runtime tar为747,837,440B，SHA `5d476b9634dc64ba2a87c3d1ae98cc70d8423c386c033be89101b831f5431785`，04原件不改。后继正式按包来源用runner实际source manifest：backend total `cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`、RS `3207cd853f66d6783c8ba2666404354cb2fedc4c401ebc2df4dcf330ab14b26a`；backend的885ab预检摘要不是通过来源。

05 stage2首稿00:14:19–31Z在工具把inspect.Id与保存config字节SHA比较处拒绝，未进入业务。outer SHA `7e5ade5b22928082f7b58ce01855ae3ec4e87ffb58c93de9dfbbea8baa544e68`、result `2a2b5e4e5931fbf6ef5c2af9533146cf7c2d56b43a42a4d67393525a2e3c0a5a`，原件位于05原plan的stage2-control并保留；只读诊断stdout SHA `1bb534049a0713214fc22d68f612d0fd5b10d9560d654938e88d979ac9f9b054`，19个DiffID与预期相同、本机Id与config不同。原审撤回旧稿CLEAR；同类误比较在05/04新稿中统一改为daemon实际save解析原config字节SHA/全部DiffID，本机Id只本机绑定。本人r0 marker经精确owner SHA、失败原件及整机idle守卫受控释放，outer `2919ccc6c0605c1d627636414f1f2ca1ec849ac2267617f85186e47891c2f72c`、receipt `27c4ad8aab18e6b7a62c00dc7d6b624ea270f8357b4bd4c5bef8dfb8ccd37443`，实际0并原审核收。不是产品或容量失败，不抹除原件。

05独立r1 stage2于00:27:32–29:40Z实际0，原件 `/home/dev/gdds-test-tmp/p6-s4-e-05-6786-r1-plan/stage2-control/`：outer `a6d41622f1369580ab4cac0cb7a7932477b475df121437220900a1c36f88032f`、result `a673175f2dd707ad8d53d701601eae706e30fee93b9d89f293afd790f5f08dc3`、manifest `578750b59cf2e134847679996fc441b9267a1b3b5fd96bcdcb3f33fd85bb7ec0`。04全新real WT/env与原authority/carried隔离，sourceprep实际0；其stage2于00:28:45–29:33Z实际0，原件 `/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-plan/stage2-control/`：outer `463a2cb70e2bfe13e1e61b439256a50f97a0e2ddc6150d0be26eabfc5a1cc7e2`、result `a90eb2e8dbb5819ca7d5033266674a8531b5b413738c4e57ccc10e8e3a31081b`、manifest `68b7e20b23b54741be61b4100a63a1823b455b4cf403a881097641ccd4f04fbd`。原审分别核收 **05_R1_STAGE2_ACTUAL_PASS / 04_REAL_STAGE2_ACTUAL_PASS**：12资产、标准8包/合成13文件/七expected、两base真实config+全部DiffID及新RS/Compose build；05跨节点load后新export和04本机原地新export均匹配authority config+全部DiffID+labels。两边HEAD6786 clean、marker释放、无服务残留。这些仍仅准备事实，不证明样本业务或M40容量。

实际调度按[执行稿](p6-s4-e-execution.md)整组分配：05为4官方FULL与W3 MO/W4 FULL/100% MO共16旅程；04为W3 FULL/W4 MO/100% FULL共12旅程，各正式组1warm+3测量，不跨节点混样本、不比较跨宿主模式提速。48GiB envelope/8GiB reserve/M40/N1均固定，不改生产默认。04队列已启动W3 FULL warm；05首次入口00:35:47Z被FE在00:35:43Z先取得的有效标记正确拒绝，未进样本。占用拒绝outer SHA `b7da0f58100dfd459b056bae2b203a7a0a6f42b5b7bbe33467b1922dd684ba8e`保留，不计DC68或成功样本；仅换独立CONTROL的新外层SHA `fd15d7092a1a97333a806a7385ab67fce0fe06afa4d59fb0e11720f15bc253ca`已原审CLEAR，待05实时空闲后执行一次，不动FE资源。原四包carried来源WT/env/镜像始终保留，当前仍无S4 exit。

Owner随后明确的低频事件监视、五节点无功能分工已落入 `0551f4a94e` 并获原审文档CLEAR。测试者等待异常/完成唤醒，稳定长测可小时级只读巡视；协调者不重复轮询或转述分钟进度。五节点均只按实时空闲与既有准入选取，本次04/05分组不是未来用途绑定。只有实际资源冲突/同路径写入/他人资源才协调，未缩减任何核收条件。

## 17. DC98收敛与04失败定向诊断（2026-11-09）

**当前执行范围覆盖上节历史调度。**Owner已明确缩减验证，以业务正确性为主，见[业务验证清单](p6-s4-business-validation-scope.md)。`75a0e2a867`固定DC98，原E核收S4范围文案CLEAR；旧28旅程、04/05的12/16队列及after-FE恢复稿全部撤回，不再派执行。剩余为关闭当前Repository差异、一组真实t4 v1/v2的首次/增量生产Submit及必要合法前置、最终来源绑定和原E核收，不跑History/重复性能/合成压力。`94200deb30`澄清DC33与DC50的历史范围，`c72b87e4a1`补具名大表并行优化只参考现有真实样本、真实规模接入后按分布决定，均获原E文档CLEAR；不改小型正确性向量、表名业务规则、N1或预算，不自动转S6/P7任务。

04首个W3 FULL warm于00:35:50–01:15:30Z运行，journey本身0、外层独立Repository核对1，**不是合格预热或成功统计样本**。原项目`s4-w3-full-warm-6786b28a35`的三个容器停止、卷及本人HELD标记保留；05在有效他人占用处拒绝，未产生样本。04原件位于`/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-node/samples/01-w3-full-warm`及原plan的`samples-control/captured/`；result SHA `4cb46452aa8fcbcd828f70b3d3e6fd224fec54720b3faf3a0af114530486fe79`，manifest `65a1e5395ec89e5d891e6b90d685386955afe032b80ae872a3f45ca2fca20bd4`，queue outer `fc64e0b8eae246aa182d9dcfa804bd03e33b2eccbea2caa7bfbf438e645a3ef9`。原时长仍保留，不将失败混入成功统计。

原E已确认两项过强工具假设不作为业务finding：同源码第二次正常build不保证与prebuild本机ID相等（DC34），运行容器须绑定实际build来源与当前镜像；worker INFO默认stderr，而旧采集只解析stdout，原日志实际存在。RS退出143如实记录；私有诊断容器同样143且原日志含完整Uvicorn正常shutdown，不能据143或停机前采集不到shutdown直接判数据损坏，也不改产品以强凑0。

针对原Repository失败，只克隆停止的RS卷到私有副本，以相同已验证镜像、loopback 18080/8GiB/4CPU做exact-commit只读诊断，无Preview/Submit/History。r0因token权限失败，r1因uv-consume拒绝外部script失败，原件分别保留；r2改固定reader经stdin传入，于01:59:12–02:01:41Z实际entry/capture/outer全0。原卷before/copy/after指纹均为`600e0321504919bbb7e2a941e9e35f90b60cf58b97ad3fab804d1d67caac5e6a`，100,622,533B/18 files，原marker/容器未动，私有容器已停止、无OOM。原件`/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-plan/private-repo-diagnostic-r2-control/captured/`，outer SHA `a34fde734d730f2339ab7f7903efd874bc0143c2f1be07e21d0a19fc25463ff9`，result `73d816ceedb2c50907f4b9b8bf911c78ca287cf04630db3879a2162232358962`，actual `38abd1c8e271035e1a75bca60f257bf98d3f8ec21a1fe83a36080c8c2bb97868`，manifest `54582128c3ef9910bb72e30f6ba3c74f063567ff5e55175901c87df921daa91f`。

**诊断过程完成，业务差异尚未关闭。**exact v1 `1mt1esgnm6lldejke8hbe47r4p0bome8`与v2 `h44k3alqnj79fid3iob3b9am3fquin4g`的631表完整schema/count摘要均与固定旧B预期一致；五个代表表的row_count和其余四表typed multiset摘要均一致，唯keyless `app_cfg__x2`的24行两版均有同一差异：actual `sha256:36a3ac30031fcd987f448ebd25a6846998686a56ecf1e19395f2e500d7bb06b1`，旧B expected `sha256:52ad359c677d92bd131518221c945758f99537542cf08e6aa10ae3db41035ec6`。下一步仅24行逐列typed值/重复行重数对照，双侧各自强核上述旧digest，依据具体差异归因，不删断言、不用当前输出反填预期。当前仍无E GO或S4 exit tag；原04 authority/carried WT、环境和镜像持续保护。

## 18. SET口径闭合与DC98短真实验证固定稿

原E已完成上述24行原件独核：旧B `run_board`内部SET为14行文本`1`、10行文本`1,3,5,7`，Repo为对应list；其他六列无差。按Canonical Storage §5.1及Repository Service §10.1/ADR0013，从旧B原件依冻结声明`SET('1','3','5','7')`独立映射后摘要精确为上述36a3；actual逆映射的完整24行Counter old_only/actual_only均0（本例24唯一，无NULL/空SET）。故具体Repository持久行差疑点关闭为外部expected跨合法物理profile误比较，不改产品或原expected，原warm外层exit1仍为失败。05新短验证将用独立wire预期重核，不能据本诊断自签S4退出。

04本人原HELD标记于02:21:31–32Z实际受控释放，原E独核outer/node0；outer SHA `3c52e58616978055cda40faea21c33678c650947984df0d69861124586fba08e`，receipt stdout `21d969aedd12118ce59917d99b3754b863cf090974efb8ac99babaf623ffa604`。所有停止容器、失败卷、私有副本与原件保留，未动S3原来源WT/env/images；节点不按用途保留。

旧B真实t4 v1/v2的app_cfg独立映射捕获于04 02:30:43–02:31:02Z实际outer/node/capture0、旧V788 clean，完成后本人标记释放。原件`/home/dev/gdds-test-tmp/p6-s4-e-04-6786-real-plan/appcfg-t4-b-mapped-r0-control/`，outer SHA `7fdcfeb965185c85404ae1f03ed9f89ec26469cbfe693a1cdd89c3ffff96ea26`，mapped JSON `258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f`。各24行先重算原B raw摘要`sha256:1ac38b4634a80eb8f1d42d13ce197a507781317869f554a1a8418d1d71427149`，仅按声明映SET为wire list后各得`sha256:2c9c580537840e71b6d35f4704a9ade016adbc8521894e1483621d28da696a93`；原E另从raw独立重建全行Counter一致。原0e67 B expected及其他四表/schema/count不变；无当前SQL/current产品输出参与expected生成。

05短验证r0于02:38:13–15Z实际outer/node2、capture0，uv-consume在业务core运行前拒绝参数`--project`，未启动Compose/Submit/Repo。原件`/home/dev/gdds-test-tmp/p6-s4-e-dc98-minimal-t4-plan/control-r0/`，outer SHA `410d998e11e28e8d93c4ea45558f62d9ace296fc269cdc2698c8df3a7c87cb92`，node-result `219416a50d9527c122c02770712482504c23977593cd81574229bc0ba5c3e10c`，business stdout `69971d56dd89ce4a6186ed63246c2df4b122a903b5496f4931c0578946cf3947`，manifest `4f17b934f589e479428f9d6e1155b8a6ed876b037dd1ff983966b3c8dd5768e2`。原审确认是外部工具参数名错误；本人marker d245于02:42:45–47Z实际受控释放、outer/node0，release outer SHA `30f3fe14216eefc82aca53a31cc21b4cbac947c403993b98bc426c99b32fef21`、receipt stdout `5fee5b3dd637fab5546bda6b97da9d446362edc3c7c501a94ca81db29bcb9adb`。旧失败原件保留，不当产品或资源失败、不无修改重试。

DC68本具体工具故障第一轮修订为外部CLI改`--compose-name`，不改uv-consume保护、产品/输入/expected或验证范围；r0全部冻结保留。新目录`/home/dev/gdds-test-tmp/p6-s4-e-dc98-minimal-t4-r1-plan/`，已获原E **SCRIPT_CLEAR_FOR_DC98_OFFICIAL_T4_SHORT_R1**：outer `8d30040738c4959fbe33493ab53c4f9171fdab47adbb893e761f6a873dd0b89a`、assets `3b28c41efd8996aaf0c90507e322fe1ab4ac8027679771b8e4b0b0a1e8004732`、core `5b02e2f53e7ed1381e4c896ba02274e00c02efe575ca36ec9cac858a9d5de982`、wrapper `043f5a1e3305c4c03a9843c6dd095b0257ba854f6351f30bb60fc49c2ca8900e`、mapped `258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f`。本人r0 marker释放实际0后已派唯一Luna按05现场原子准入执行一次；仅真实首次/增量Submit及合法前置、独立Repo/有限资源和正常停止，14,400s宽工具上界不作性能目标，无History/重传旅程/完整bundle下载/统计采样。实际结果待核，静审CLEAR不是运行PASS，当前E仍未GO。

## 19. DC98真实t4实际核收与最终H条件

05 `gw-dms-test-05` r1唯一实际运行已原E核收 **E_IMPL_AND_DC98_REAL_BUSINESS_GO_AT_V6786**。控制器原UTC02:44:21–02:50:31Z、节点业务02:44:24–02:50:32Z（两机原时钟分别保留），outer/node/capture全0；起止产品V6786 clean、Rust e2a/native一致、六锁无漂、本人标记真实释放。已完成v1合法Preview→Submit技术main前移→exact Repo独立核对→Approve/Archive合法baseline，再v2 MODIFIED_ONLY Preview→Submit/main前移→exact Repo核对，没有History、bundle下载、重复采样或新完整旅程。

原件`/home/dev/gdds-test-tmp/p6-s4-e-dc98-minimal-t4-r1-plan/control-r1/`：outer SHA `142a2b50d9b5079c0ae83f382935b05d5e98d347ed04690247085aaa6c0b3cc2`，node stdout `345f2c27becc6f49f7691e31ad92cf4a884e0425f3a52074b625f5e814810fb2`，node-result `77ae69e01b068196e524731f0b27f866de0962519060f605f41385cf534f6861`，business-result `3cf9db7a9e8dc7a76a7f871497dbaebacc339628c27e986a6a430e4d4a5d89cb`，business stdout `9c87d282cb16d880a48505eb89909f85fb738f62f6c5b36f1534913358b536fb`，13实体manifest `ead2315ba21ea79362aec105488db5ec557bc4bc9f84b470bfd6adfcfd47f317`，release receipt `df2a6a4182a2bb9be085258eb553111aaa13a5dc9c852644e092885a0d7645c6`。root及原E各自逐SHA核实体零失配。

两次technical main分别`1c9u40na8fosd9cc9i47h4bnnusif5iu`、`g2030m91c52sd4evr1ml5enkn2p7o1t0`；两版完整312表Catalog/schema/count、四表旧B摘要及app_cfg旧B+Contract全24行wire Counter均一致。ordered代表表9822→9828行、composite435行。Submit调用至内部已HTTP核main返回的单次保守原秒数104.105179/77.447006，原参考目标300/600均met；没有median/range或正式少量/几乎全变统计结论。

worker原日志记录首次312个TABLE_ADDED REBUILD、净计数全未计算，SQL 50,566,368B（DDL174,265/DML50,392,103）；增量27候选中12 PATCH、13超阈值REBUILD、2 BEFORE_ROWS_UNAVAILABLE REBUILD，parent_reads25，SQL 2,125,772B（DDL11,613/DML2,114,159）。25张实际diff表合计D/U/I=11,558/88/11,632仅是该25表净计数，另2表仍None，不伪作全部输入净计数。两个包实际publisher/readback均COMPLETE，包大小2,156,704/263,702B；原样重传零Repo operation、checkpoint复用/CAS/恢复等沿已核现役测试，不加重复真实流程。

固定N1/envelope48GiB/reserve8GiB/M40；实际guest32CPU/affinity0–31，worker HostConfig NanoCpus0/cpuset空（guest内无额外CPU硬限），实际cgroup memory.max=51,539,607,552B。worker cgroup peak926,642,176B、RSS HWM648,097,792B，三服务OOM/重启均0，同容器/配置守卫通过。账本预约high-water为42,949,672,960B，summary used为2,817,757,936/2,759,311,116B，预约口径不等于RSS需求，不据此降M或改默认。TERM后worker/backend exit0，RS exit143且stderr有正常application shutdown complete；全部停止，cleanup_errors空，本人标记释放。成功停机资源及既有失败/私有卷保留。

原E已暂停其完整报告供原文归档，SHA `978fb940253e55665aefefd4774963b330999e59d7d33bbfad16d94c7c02f7f9`。最终产品V仍6786，交接H为本节、累计handoff及原审快照的固定提交；正式S4 exit以H在原04 authority WT实际六closure/RS与原镜像身份绑定且原E最终核收为条件。未提前tag/push，不授权S5，原M24/合成大负载/稳定统计未知及失败持续分列。
