# Phase 6 S5 最终交接

最终产品 V2=`2d8b29d332ceb467ba77bb4826fb0925653ebb4e`，vnext tree=
`fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`；最后产品修订即V2，Rust tree保持
`c0213e18a9645c5cfbd39f310f532273a03a10cb`。

V2已获E_CODE_GO / EVIDENCE_GO：六包/Compose及最小t1全部核收。最终原审SHA256=
`332f7f1c36b03b73944111cfde31929965887bfda0f8cdb67077c667c292a653`，逐字见[E审核归档](p6-s5-e-review.md)。
本文所在纯文档提交作为最终H候选；精确H绑定、资源释放及EXIT回执记录在外置不可变证据中，
实际退出以附注`p6-s5-exit`和最后一节指定的exact-H回执为准，不能仅凭产品/证据GO提前标记。
最终文档 H 不在自己的提交内容中写自身 SHA，由最终外置回执及附注 `p6-s5-exit` 解析；
H 必须在原 V 的同节点、同 worktree 完成逐包闭包与镜像绑定，之后独立 EXIT_GO 才标记。
未经明确授权不 push。S6、Phase 6 总退出、FE3c 与正式容量/性能工作不在本次交付范围。

## 实现与审核

| 小节 | 固定产品 | 状态与原始证据 |
| --- | --- | --- |
| A | eb64578925398a6402f6e7b21790226c5f4e78e6 | CODE/EVIDENCE_GO；[A交接](p6-s5-a-handoff.md)、[原审](p6-s5-a-review.md) |
| B | e1098b2a62daaf779b758de80ffd0013b17650a2 | CODE/EVIDENCE_GO；[B交接](p6-s5-b-handoff.md)、[原审](p6-s5-b-review.md) |
| C | fdb2a69a437f669150f9c3c2eed15f220e77f7f3 | CODE/EVIDENCE_GO；[C交接](p6-s5-c-handoff.md)、[原审](p6-s5-c-review.md) |
| D | cb2ad300845f73f12ae5367d247829623b728f18 | CODE/EVIDENCE_GO；[D交接](p6-s5-d-handoff.md)、[原审](p6-s5-d-review.md) |
| E | 2d8b29d332ceb467ba77bb4826fb0925653ebb4e | CODE_GO / EVIDENCE_GO；六包/同次Compose、冷包补核与唯一warm全部核收；H绑定另见退出回执 |

- 完整去外层绑定的单表有向任务 key 与真实 native policy 共用 projection。neutral 格式保
  三族 facts/artifact 的两种序、typed frame、blank 信息和原 Parquet batch/row-group，
  加一个完整 STANDARD risk 视图；恢复经真实 facade，在本次 pair/operation 重新出版。
- Risk 完整事件保原 cap（pair优先）→候选记录→等级过滤→预约/编号/append→业务clock；
  被过滤候选不前移clock，当前 closure 核验位置保持。未缓存最终截断风险 outcome。
- 唯一基线 schema 直接包含 entries/uses。先 pin 后校验，完整成员原子登记，精确条件失效，
  lookup 期限与64项 bounded prune/touch；没有迁移/双读、持久 refcount、额外 journal。
- Preview/History 实际接线；History exact commit/完整 authority metadata 先行，diff 与 export
  独立 lookup，再按完整导出/composite/比较实际需求补行。checkpoint 恢复重新验证冻结
  metadata与缓存。当前 records/risk/surface/完整 bundle 仍走唯一 publisher。
- T3 在原事实校验后解析真实 Preview producer，只在原 SQL 短事务窄 SAVEPOINT 触达现存
  匹配cache；缺临时记录跳过可选触达，存在矛盾必须失败，未知SQL/CAS传播；不推进业务head。
  DC94 的 T1/PREPARED 与 prepare checkpoint 固定包/key 屏障保持。
- 通用 client 控制覆盖 catalog/Arrow open/read/chunk/backoff，最大3次总尝试和原 poll
  完成观察保持；取消窗口返回的 transport 仍关闭。backend 实际 HTTPArrow 与 parent
  catalog consumer 都转发当前 context，无外层重试/新 pool/额外 M。
- 删除被替换 repr identity、History 全表预读/旧 checkpoint 行假设和旧条件失效路径；
  保有真实 consumer 的 generic seams、records validator 和独立业务/SQL golden。

从 C 起每节新建实施/独审/唯一测试三角色，协调者持续，阶段内同一原审连续复审；A/B历史
分工按发生事实保留。E为新 Sol high / Sol xhigh / Luna max，未延续 Astra 临时授权。

## 权威与容器

全部六包均在V2由权威入口实际运行，整次exit0；A–D focused及旧V1整次非零均不作
qualified source。同次backend/RS内适用Compose不再另跑。原审核收见E审核归档中的
`e-authority-evidence.md`，原件SHA256=
`0e32da3c9c5b93395f961afa07b9b6f0aa50860ce420e2c86fa845e907c72317`。

| 包/批次 | V2实际结果 | source total_digest |
| --- | --- | --- |
| rust | fmt/clippy/workspace test均0 | 39758d7db4e41370f9d2a8ace9fe0483aefe0124d7126e54dc10ac045fa78b04 |
| shared_kernel | 261 passed | 123505051e2a08cd353c1bae51f26712dc3192bc2dde976452d71dfa807f43b0 |
| repository_contracts | 152 passed | 6c86e24ca0b701dc46382971fefef1f16386fb42eee13e08ff85920c68d38389 |
| repository_client | 170 passed | 3daf7071792232cb38fecc32d308e1ecd72f65ba7e4288fec7dff723c1461e1a |
| backend | 3642 parallel +80 serial passed | 41a96e760b6186a2d56e50ff0b634fdbb0ddd665af25196ccdbc5d49d86db770 |
| repository_service | 1764 parallel +214 serial passed，1 skip | 4d3cdcbada36ba82dcbb7639f22deafe6fc4e15e7093239adad36f50471fda28 |

RS的原-q日志没有skip nodeid/reason，具体身份未知；target-container smoke是源码推断，
不冒已证明理由或pass，不补无依据矩阵。S5未修改RS服务/cgroup，原审未发现阶段必需
consumer缺口。原日志保留这一限制。

执行稿 `/home/dev/gdds-s5-logs/execution/e-authority.sh` SHA256=
`8aa001aeb3002232d060e519868dfaf9a496a59e904711a098ea2299823e0fab`。
E原审 CODE/稿 GO原件 `e-code-r1.md` SHA256=
`4eaccee43c7bffad64d65e3b85dcb62f69878327565d09d3e8ae3e934fbfbf9f`。

authority来源06 / gw-dms-06.lan，2026-11-09本地11:32:25Z启动；remote session
11:32:28–12:03:59Z，runner11:33:10–12:03:13Z，8个外部步骤均command/tee0，起止V2
clean。原件根`/home/dev/gdds-s5-logs/execution/e-authority/20261109T113225Z-2d8b29d332ceb467ba77bb4826fb0925653ebb4e/`；
bundle SHA=`877efea6f4d3ba18b00f58467275bd72137427201a0156f9676aa1f7f094fb5a`，
manifest SHA=`d06f00a3216792da2b45e8ac44bbf6666b3853ffee36373ef5ae810ed39df0ba`，
steps SHA=`3608a5aaaa61f2241494f42d74db30dc2ecfa0e4739ec7ef22a105d3d8bf283a`，
runner SHA=`dff5f6c385ad17f6dbd6a932efdd91710d68e616b34d1d3d262795b284b50b69`，
session SHA=`8abf7728540a3737ea1e24f2850ccaae2be0983767f349ab6523f74fd115d157`。
原来源 worktree：
`/home/dev/gdds-test-tmp/wt/p6-s5-e-authority-2d8b29d332ceb467ba77bb4826fb0925653ebb4e`。
原 runroot：
`/home/dev/gdds-test-tmp/p6-s5-e-authority-2d8b29d332ceb467ba77bb4826fb0925653ebb4e`。
成功后保本人标记/环境/镜像到H绑定，不能换WT或跨node判定carried。原runner强制native
reinstall/build-input匹配c021；五Python包专属Hypothesis路径均在manifest前不存在，
runner后清除；UV_OFFLINE1/CARGO_NET_OFFLINEtrue，N1/M24、worker envelope32GiB，
backend preloaded base1/networknone、PREBUILT未启用。无新依赖/代理/公网下载。

actual docker-save config原字节与全部RootFS DiffID保存在before/after identity原件，
未把containerd inspect.Id当config。before5个selected镜像与after对应项全同，after还含
最终Compose三服务runtime。after JSON SHA=
`634e02cc8eb98be4e98ab129248de6f49c850df0a2156427f06fa36f11e4cfa4`；
各完整DiffID见该原件及原审。backend deps config46c00…/19层与原53746来源逐项匹配。
RS tag=`gateway-repository-service:p6-s5-e-2d8b29d332ce`，build-input=
`e76342ef0b58bb0120fc60d8a063d838140ee28d`，source-tree=
`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`。
最后Compose provenance SHA=
`6a5f09ed797db35975a412407bee8fca405ffbb5414264a2b78b37382d960492`，
只记录最后旅程，不冒全部旅程清单。V2→H的carried必须由原06同WT/profile的实际六包
compare及镜像身份核准，结果在最后一节的外置精确H回执，不以同树口头代替。

## 标准 t1 最小范围

已确认两包：v1 107115B / `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`；
v2 107066B / `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`。
既有已知真实状态源早于 S5 的唯一新 schema，缺新增cache表；不迁移或启动冻结旧卷。
本人隔离命名空间仅补必要 Preview/Submit/审批；v1 Archive 建立v2业务基线，已finalized的
v2 Submission 可作History第二节点，不额外要求Archive。然后只一冷、一新key/newoperation
暖查及实际 records/完整 tar。FULL/三节点/损坏/恢复等归各focused owner，不扩真实旅程。

driver及wrapper当前已保留至r5/r6；pf2实际在业务前发现两包XML原始字节不同，旧稿
“原XML相同”的依据错误，原重跑许可已撤回。固定旧S4源码的小组件捕获已经实际完成，
组合表逻辑UNCHANGED/4→4行，added/removed/modified/history_record均0；两XML各81B，
v1 SHA=`03f90da1675345aef17d9c0cadbb81f6271f1c7bfe1ae79d8eb86213b1a68adf`，
v2 SHA=`7d0fec1905aaa7100f1fc7eaf13347755521e79cbea45b317a14660f821801d9`。
这独立证明逻辑不变，不把原raw equality失败改成通过。

旧source=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`、vnext=
`6368c9c40cf08a97eecf2a0c457a6c16ce448080`、Rust=
`e2a901417b19259ece669637a41545e774261445`。04 / gw-dms-test-04.lan于
12:48:22–12:49:26Z完成5步全command/tee0，oldnative强制重装/build-input一致；N1/M24，
scope charged hwm=`25251453312`，组件耗时约0.686s仅观察，不冒当前S5性能。old WT
起止clean，main起止2d8，marker rm/rmdir0且释放，无Compose/HTTP/runner/History。
原件根`/home/dev/gdds-s5-logs/execution/e-t1-old-composite/6786b28a3506feab3d8eac7d1288c8b22525bb8f-oracle-r1/`，
result SHA=`3707ad9891efa47a2d1b5fdb88e51f9b77880d7532826db1ff4d5a6476ab5261`，
local manifest SHA=`8fb011f3c29b3dc303a0cdb9495a14ee6cf229d9a5e6df259d7ea1e6accad2c3`。
该捕获不含Risk，不能由其推出整体risk0。后续只读检查发现SQL增删应产行risk，原稿
零风险断言不符合owner；随后固定旧Comparison→Risk最小组件捕获实际成功：04同host于
13:04:09–13:05:14Z，5步全command/tee0，native与输入身份一致，N1/M24，charged hwm=
`25547679616`，组件耗时2.604s仅观察；source/main起止clean，entry/copy/hash/release全0。
唯一非UNCHANGED表SYX为3增3删，STANDARD6+ORDERED6共12条，风险READY、MEDIUM_LOW、
1表6annotations。所有六risk row target与独立gid手帧、ROW_ADDED/ROW_DELETED、等级及
00000000–00000005编号交叉PASS；其余124表UNCHANGED，composite不额外发risk。
原件根`/home/dev/gdds-s5-logs/execution/e-t1-old-risk/6786b28a3506feab3d8eac7d1288c8b22525bb8f-risk-oracle-r2/`，
result SHA=`d99035bbd9afd5d941440d7a65a61938a4c6071cad61999a520aaa49c94d3f7a`；
manifest SHA=`5d51faa2809dd1927776981dfeb0e3bf854bfd6c21ee6ffdcf7ff61efa619ef1`。
两个record族logical content digests分别为ORDERED
`sha256:e79378d966f39a1296a0e7452333a43d0ef547f3a41e1989314b77b44f2a4e5b`、STANDARD
`sha256:0d3af5be7293af911e9a8e0e25ef0fda3a056648be3d57e5bf4997925a0b18c0`；
完整annotation内容digest=
`sha256:f4105ca4ae8af4c70d109fec3bb33542434f33014a11a2cd68ec5cdbbef617e4`。
旧源capture没有HTTP/DB/Compose/runner/业务旅程。风险稿R1在执行前因跨组异常可能跳过
reader收尾，经R2标准ExitStack修正、原审关闭ORISK-1后才执行；OLD两个cache字段实际
原本已有，不把此前协调者接口疑点记成真实finding。当前t1以该独立来源核实际结果，
不使用新History actual回填expected。

旧composite证据原审SHA=
`5a641904f91e34dc5692aa5eb8e692c3e73799ced773414a2c243c2182b052a6`；
旧Risk证据原审SHA=
`bc20d2b8d29d6c16898b53097f60121fda0d96633c5c4dd87a38bd55d3fabb40`。
新固定driver `e-t1-r6.py` SHA=
`7665a6ef4fbc16daa0ae611f0dbc185696bc95dcde4f108fde4561b9ecc6edf9`；
wrapper `e-t1-run-r7.sh` SHA=
`79d8c4f5a7838a7707327d02c2020c842332f6df7a36f9e7dc933d33c03f2758`。
两者联合修复轮3原审GO，SHA=
`e65e3dfe3371e1c3b3d93a109dbf5a021e15dbdaba5879d62122aa04c0f736ee`，
原件仍逐字保留旧失败/许可撤回事实。执行稿只新增固定旧oracle数据输入，不接受项目外
Python脚本target；仍受控project stdin/locked/no-sync/离线。完整当前risk与record族对旧
business/count/content digest逐项核，冷暖本次comparison/risk/surface原摘要直接核相等。
pf3于13:15:53Z本地启动，04 remote13:15:56–13:21:07Z；两次Preview/Submit和v1Archive
实际成功，cold History操作13:21:03.197Z返回SUCCEEDED/44.148s，完整tar下载与基础闭合
通过。但诊断脚本把可选物理RISK_REPORT当必存在，实际kind0/Surface root ref=null，
其严格“records closure1且risk report1”断言失败，driver1/tee0，warm未执行。该来源
尚未通过全部业务断言，不冒t1 PASS；source起止clean，stack_stop0，marker正常释放。
保存完整cold tar2153472B、116普通成员/114closure、records closure1/逻辑12，
tar SHA=`93da19c776c8840338ab2f89b8450a4c7572bda742d55ea06fd52fc066b769b7`，
原失败result SHA=`811c255b8b01aab42dd1a844a59da3bf24d4ba17d5d15cb8ec75b856bb59854e`，
outer manifest SHA=`45ae39e623c4ee1bbdc17894e23ff9ae21a3eacd31c8c44523c8f9efb3689ef8`。
所有631/615 local/remote清单项校验0，原数据/容器停止态/卷/私密secrets/环境保留。
实际cold后cgroup峰值未捕获，不能以先前prerequisite峰值代替。

原审pf3诊断SHA=`e5d4ede9b69ba6e62d4b324a41ca297c3951af2920a76709daa9dcbeee997ec1`：
确认当前共享Surface引用owner允许report_ref=null、add(None)跳过，源pair pipeline把
RiskReport对象送Surface风险投影，并未传物理report_ref。这是外置consumer的首次具体
假设错误，不是漏必需引用闭包；同一故障最多三轮的DC68不按不同profile总数造新阻塞。
全部原始轮次和exit1保留，不做第四完整旅程。

只读保存cold tar补核稿经原审GO后，04于13:41:24–13:41:27Z在原clean2d8 WT/nativec021
执行4步全command/tee0，完整核原615项SHA；独立新输出，未HTTP/服务操作/新operation。
实际验证全部125表、250节点导出绑定、3733/3731行、所有字段/编码schema、全部12条
records的两个族contentdigest与六手算、6条annotation完整业务JSON/manifest/contentdigest，
及Surface真实可观察风险level/count/reasons汇总，全部对独立旧oracle通过。
不将未物理发布的risk_report_contract_version、RiskReport.diagnostics、RiskTableResult.
diagnostics伪作actual；这些report-only字段是当前bundle未暴露的可选物理形态，非新增
未闭合业务finding。原审核收SHA=
`1e4554d1751954d2680b9d3a7d01e7e8c02196e80ca90bfc5fa31bdbf61ebd80`。
补核原件根`/home/dev/gdds-s5-logs/execution/e-t1-cold-recheck/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-31af7983e191-cold-recheck-r1/`；
result SHA=`c3b14d934311be8fc9c5c7230e03b35ee82aae5913a2017c0853e6bbba3b9c8e`，
local manifest SHA=`108486a74bbb3617aca3bbc33c914492bcc372580fdae81f7e18a7dc3dfb4052`，
remote manifest SHA=`2982ef55c13c87c646027b44ad1e9c7c2b868c8185ced6540adeac8cedb926c3`。
postprocess/entry/copy/hash/release全0，source起止clean，原pf3 exit1未改。之后按已审窄稿
核历史冷日志窗及原停止态合法节点/DB/缓存/镜像，仅补一次新key暖查，实际结果见下。

既有固定旧SQL基线为125表中非composite124表、3729/3727行、12记录；composite的
行数、变化与风险预期由上述固定旧源独立捕获补齐。代表三删三增从两份固定SQL手算，
按Shared Canonical Encoding v1独立编码 unsigned gid 8-byte big-endian row identity，
真实records facade核identity/position/name与对侧空值。全部12条又以固定旧源两个族的
count及logical contentdigest独立比对，不把六条代表手算冒称为全部字段的手算。完整exact catalog列/type/PK
与现 owning canonical/export profile核全部Parquet fields/encoding，PK按authority记录，
不虚构Parquet携带PK。SET按逻辑members保重复行与顺序语义。

metadata/canonical/control lookup、export/cache恢复、records验证/digest rebind和实际RS行
HTTP分别记录；Dolt行0须正校准日志中的真实warm请求0，不能只凭native0推断。RS可选
admission diagnostics不可观察时标null，不把无日志记0。cgroup实际peak与预约hwm分开，
默认N1/单active、worker32GiB−reserve8GiB/M24，不以S4 M40成功外推本次。

## t1 最终实际结果与资源

最终窄续验在04 / `gw-dms-test-04.lan` 于2026-11-09 **14:38:53–14:40:29Z**完成，
原pf3同一clean V2 WT/native/三容器与私密挂载原身份通过后，仅start既有服务；未build、
sync、新建栈、补两前置或重跑cold。6步command/tee全0，driver和实际镜像取证0；三原
容器stop/post-stop inspect全0，entry/copy/hash/marker释放全0，保原卷/停止态/证据。

冷op=`op-b8408f429d026545fdd3d8fe`，暖op=`op-d387b7f215cd42edfbc08aa6`，两个实际
operation不同。暖key为原未使用的
`p6-s5-e-t1-2d8b29d332-7665a6ef4fbc-pf3-history-warm-resume-r1`，R1/R2均未POST。
只有两份必要Preview、一份cold、一份warm共四次完整bundle GET；重验已保存tar没有新GET。
前后精确commits为`o6i9dn2hlkeih7qvuieri7n00553vl3i`、`4on71tpsqvl3ddkqi07tfuhebotu9n8a`；
两个Submission refs分别为`sub-2972b367-1dcc-4a66-95af-f1fabdfbf537`、
`sub-53794a35-a079-46d5-a2c2-e969613aa4ab`。

| 指标 | 原cold实际 | 唯一warm实际 |
| --- | --- | --- |
| History操作完成观察 | 44.148s，SUCCEEDED | 34.118s，SUCCEEDED |
| comparison kernel / ordered single-side | 1 / 8 | 0 / 0 |
| persistent diff lookup / restore / records validation | 9 / 0 / 0 | 9 / 9 / 1 |
| digest rebind | 125 | 125 |
| 实际RS rows HTTP / catalog HTTP | 129 / 133 | 0 / 4 |
| demanded table / export cache hit | 250 / 0 | 0 / 250 |
| control metadata resolves | 2 | 2 |
| canonical metadata reads / catalog reads | 4 / 4 | 4 / 4 |
| 同一operation预约高水位bytes | 25,438,132,736 | 25,438,127,616 |
| worker cgroup实际peak bytes | UNKNOWN，原cold后未捕获 | 109,735,936 |

metadata每次保两份原记录、各distinct_commits=2；4是两轮累计读取次数，不虚构4个不同
commit。RS admission诊断未暴露，cold/warm都null，不把无日志记0。cold行读取以同一
原Docker container历史timestamps从POST前13:20:19.019Z至原stop13:21:07Z重建，
并核原final日志前缀、唯一cold业务ID和pair metrics；不是伪造原before/after差量。
7条有scope事件与3条`operation_id=-`生命周期事件分别保留。

N1/单active，M=`25769803776`，两次实际预约高水位都在M内。暖cgroup max=
`34359738368`、peak=`109735936`、current=`109154304`、memory.events全部0；
peak观察范围为原worker再次启动到暖tar验证结束，不能代替cold峰值或把预约额当RSS。
两次延时仅为这两个操作的观察，未预热/重复采样，不计算median或宣称同条件性能提升。

冷暖均125表、250个snapshot bindings、3733/3731行；完整STD6+ORDERED6及6条
MEDIUM_LOW注释的所有业务字段/target/编号/contentdigest对独立旧oracle一致；各表完整
schema/encoding与exact catalog owner一致。实际读原records facade，完整content校验，
不能以tar/closure条数代替records消费。只有owner定义的Surface外层surface_id/view_id按
新operation重绑，未mask目标ID、编号、records/contentdigest或业务值。

comparison digest冷暖均
`sha256:cc51a9ff6e91d95bb8ad4f00135f031559c8938bd03b22466ce5493614d4686d`，risk digest均
`sha256:cdefa93c80d7a7b09be713143cae0d8d0d3f5815f78b205f807cb5d6f399e8e3`。
Surface的两层分别核实：HTTP源值与真实cold ASSEMBLE checkpoint逐字段一致、冷暖源摘要均
`sha256:2971ba7d71d0605d49c7a81e25e702564b580e9a85e5307d2f8486cc898e2365`；
BundlePair与tar Surface最终摘要一致、冷暖最终值均
`sha256:81eeff34068447eefddf20843e35bc3e1b20f9e5d91dec423f12498a056105ff`。
Bundle递归改写引用元数据会改变其rawSHA/size，随后重算final Surface；不能把源与最终
两层强行等同。比较/风险/bundle/输入索引/两个node/record_count跨HTTP与tar仍严格绑定。

暖tar2153472B、116普通成员/114closure、4份引用metadata、1份records closure/12records；
tar SHA=`d2c5940e157e2ef31a02b36a6c7fb9bf9c0ffbe0b1874fbf9faaaef26013f7e6`，
bundle digest=`sha256:283aefc2d5783b3fd1c7cbb0f5e012651f19647438087bb2c196f9344e01f5de`。
ETag/Content-Length/完整body/全部成员与引用闭合均过；bundle实例摘要不同符合当前绑定，
没有返回旧cold bundle冒暖结果。

原件根`/home/dev/gdds-s5-logs/execution/e-t1-warm-continuation/2d8b29d332ceb467ba77bb4826fb0925653ebb4e-e4b4dac49cc1-warm-continuation-r3/`；
local manifest SHA=`b5db596c5c8ea890c33b613126389e5fb98fddc84ed66547a1a9c1dcd8f5e0ef`，
remote manifest SHA=`190eb9af91a0540608db02ac8fe975b5b56682dc55b211773dcc003291fb4c69`；
总体result SHA=`c4153a1baf97f22efd92ba219cb5cd3c33a9d536f11cea9a0d19b0d7f254046a`，
暖result SHA=`d4df28ce9a24b10e5c31f390f57e0dd1c86f2f0aae67076acd086ce9084c3e32`。

实际镜像原件`remote-evidence/image-identities.json` SHA=
`254479803068c5ee5c9810220f68709a9b2a0790a7fb8cf1b66e6648f6ad5109`，保存8个tag/runtime
ref的true config原字节SHA及全部RootFS DiffIDs；runtime三服务与原V2 local IDs逐一一致。
backend config=`sha256:f43afb60c88567b3dcf40116f325b805fb2058aac5293304c77708e275024772`（13层），
worker=`sha256:812079db936d6cf25b665ba5a30fdfcc79b807a67128e9949daaed7a6537959b`（13层），
RS=`sha256:279b9aab99d4cadfdee1720fb74bc20cd5c9d19bba848713afbd549d8fabf0dc`（28层）。
两dependency base config46c00…/19层、98d080…/16层与既有来源匹配；没有把containerd本机
manifest ID当config，也不将04/06两个worktree或image ID作carry比较。

## 失败、取证修订与未测

A–D历次实际非零、未跑范围和修复原文见各节交接，均保原值；后继成功不倒改原失败。
E所有脚本原审/连续复审及失败诊断已逐字归档，不以最终GO覆盖早期CHANGES_REQUIRED或
撤回许可。最终warm r3脚本SHA=
`e4b4dac49cc1acd6ac20bd3b1f985a74300e02575229ee4910e1327f0198366c`，
wrapper SHA=`a1976277b156eb74183cd2dd0b178b6720c084f61b670605ed73a87c45901212`；
原审GO SHA=`dca8d37ba8ea4259097f8229935d3dae2fe1a6d507330e2360920e6efdbbdb20`。
warm r1于13:59:34–37Z的只读历史日志预检误将`operation_id=-`当业务ID，r2改为真实六字段
scope解析，无scope lifecycle完整单列；r2于14:06:32–43Z在必要cold GET后又误把源/最终
Surface摘要跨层等同。两次均原entry1，未start worker、未warm POST、无第4tar；原三容器
正常关闭、marker释放，两份清单/源原件保留。r3按真实checkpoint与owner分层修正，两次
真实失败不记成实际暖旅程，也不因输出目录改变清零。没有第四完整旅程或再次冷查。
一次复审材料误用仅留言调用、未唤醒已结束回合，造成额外等待；协调者核实并改为任务调用。
这属于协调派发错误，不把其等待时间归作产品性能或节点阻塞。
E authority初稿占用用途误写D在执行前修正，旧f580稿保留，非DC68运行轮次。t1 r0/r1/r2
均未执行；原审依次关闭资源所有权、ORDERED无gid、完整schema、计数观察/metadata与
secret归档边界，r2的unsigned text手帧又经r3修为8-byte BE，未以新actual重录expected。

t1三次前置失败均为04本人新隔离路径，原件保留，未成功开始Preview/Submit/History：

| 实际尝试 | 失败与原numeric | 后续修订/证据 |
| --- | --- | --- |
| pf0，12:09:58–12:10:00Z | unused host global Dolt config字段assert失败，entry1；driver未进入 | 修复轮1仅删除t1未消费的hostDolt前提，未改host全局配置；失败log SHA6bbd81d84a6ece5b71b4d29f9a40567bde6c183058aa3f448ae5f12ae8219ed1 |
| pf1，12:17:29–12:18:36Z | wrapper拒绝项目外.py路径，driver未进入，entry1；前7步0 | 修复轮2改受控project python stdin，保locked/lock-check/no-sync/五锁；失败log SHA fad1189c07e7df34c5c4886b68444b533de745bac6213fdaa5428ffc18871fbb |
| pf2，12:33:17–12:34:22Z | driver pool初始化后在independent unchanged composite XML失败，driver1/tee0 | XML字节不同，旧预期来源不足；转固定旧源最小捕获，未进行新History；失败log SHA beb253030b0bedaca5e4599b2de1c951788954340272b1eb2f5f161cf477e3d7 |

pf1前七步及pf2前七步包括实际旧/新指定native与RS准备，不冒业务通过。pf2结果JSON SHA=
`5b667019fd5cb7e3f6bb091ce74e402377c28d34ee23ab2af29a23da3a9df535`；
env尚未创建、owns_stack=false，不能把result的通用volumes_preserved字段理解成本轮实际起过
容器。各次sourceclean、本人marker释放、worktree/venv/原件保留；前两次框架修订与本轮
预期缺口分别说明，不清零已实际执行两轮修复事实，不无修改重试。r4driver缺host native
pool初始化由静态追查发现，在pf2前修为r5，未额外执行失败轮次。

E预检曾在06和CT108调用dolt version；CT108回包有无法查询latest的warning，原始回包
只在会话工具记录，没有外置原日志。`e-preflight/20261109-dolt-version-preflight-derived.md`
是明确派生说明，SHA256=`9b6f8cad0dd0b49478f0a1aa49f91cf401f7c532a9ec261e619f8b9220585884`，
不能冒原日志或证明零副作用。06后续只读核有效 `/root/.dolt/config_global.json` 的
versioncheck.disabled='true'，HOME=/root/DOLT_ROOT_PATH unset；本次权威manifest的
Dolt version消费该既有配置。CT108该预检不作门禁来源；实际产品执行不使用转发代理。

正式性能/大负载容量、fresh t2–t4、多worker调度、SDK、S6、FE3c 不在本轮范围。


## E 已发生产品测试失败与必要调试（原件保留）

旧V1=`16317606d4c5ea357f7b07132f71f5ab4cd783bd`在06 session 10:52:40–11:24:13Z，
权威入口10:53:29–11:24:12Z，原整次exit1/tee0。Rust三步0、shared261、contracts152、
client170、backend3642 parallel、RS1764+skip1/214均过；backend serial唯一失败
`test_ordered_history_compare_compose_journey`，79过。真实History已经成功，旧诊断把新
metadata-only checkpoint当成row-ready交完整surface，verified canonical reader guard拒绝。
既有原误差不改为工具前置、partial包不作为qualified来源。

原件根 `/home/dev/gdds-s5-logs/execution/e-authority/20261109T105237Z-16317606d4c5ea357f7b07132f71f5ab4cd783bd/`。
完整runner SHA=`9cf9f29e5691ceaf17d769a23ef7089f6d617d131a77c57c050c9274a1deac11`，
steps SHA=`6044cfbaab547df5a589b0243bd605ec3163982968ab78d5d7bb803edf672dc1`，
session SHA=`610d51755da59af1dd293ed9ab434c9bca20fe37b6d3432a1cd474d63767cd44`。

初修794227再经标准ExitStack改成最终2d8；只改existing compose_gate_harness两个诊断
consumer，用actual scope/exactcommit authority及原ensure owner补实际全表reader，并在最后
native/batch消费者结束后关闭。原remote digest/records断言保留，没有修改生产或业务expected。
原审R2 CODE_GO SHA=`9ecd47347f741b235213a733ddc527fbeb10d5c71f908f366a6aba424963ac4b`。

06必要debug于11:26:46–11:29:13Z、19步全command/tee0，强制native/input/五pkg静态和
唯一原受影响Compose **1 passed / 51.20s**，新HEAD2d8 clean、cleanup0、本人marker释放。
这不是qualified runner来源。原审核收及新六包执行许可原文 SHA256=
`5686ae3a87f203d5ce2b1274d7583a25778089468adc9c5d4f707566d0606ca8`。
原件根 `/home/dev/gdds-s5-logs/execution/e-debug/20261109T112643Z-2d8b29d332ceb467ba77bb4826fb0925653ebb4e/`，
manifest SHA=`c6881f5cf4f1c9ac38cfe6dcf98016b4209df50420961d3873bc3f8633c12068`。

## 已有依赖缓存来源

当前backend依赖输入和其Dockerfile/build脚本与53746c7236a79c96bd41587165e80683da283400
零Git变化。CT201原构建2026-11-08 09:20:30–09:26:19Z、exit0，归档SHA
`1b595f069197d75a9226978a530fdb06db93e7df29dbf1f4458e00ec3f6cc648`；tag
`gateway-backend-deps:lock-578e079b762e`，完整input
`578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`。原config
`sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`及全部19DiffIDs
的原identity JSON SHA=`d5ebabf6cf39b98917adca5ebad6f66138e2a9fa00e63eb8e6526956ccdff7c3`。
04原LAN load09:33:44–09:34:05Z、logSHA
`c5b960cd8c9731f8947e53b2674ac34a62255bb8833bbab4648d14404c57ad8a`；06原LAN load
09:33:48–09:34:06Z、logSHA=`762c4b3f828ddee4c618e006f716c4b241cce3d186e18c7d7adb9a39a41c4d97`。
两预填原过程均09:34:32Z final0，当前不重新传制品。原路径/完整逐件数据见外置
`/home/dev/gdds-s5-logs/e-cache-provenance.md`和S3 E handoff；本次实际saved config/全部DiffIDs
须独立匹配，不能跨节点比inspect.Id。既有cache事实不冒产品门禁carried。

## 最终H绑定与退出回执

H只包含本交接、逐字审核归档和计划/协调状态；产品vnext tree必须仍为fb92、Rust仍c021。
最终源码/测试/Contract不再变化。H不将自身SHA或后续绑定结果写进自身内容，避免为引用
自己的回执再生成H2；精确目标由本地附注`p6-s5-exit^{commit}`和外置回执解析。

固定绑定稿`/home/dev/gdds-s5-logs/execution/e-bind-h-r2.sh`，SHA256=
`26069b7eaf3c77346e8d58c7cfe386f2127b10c518752fb6a7795c4f9aa1bf9a`，
在原06/authority WT检出H，不sync/reinstall/build/retag，按原profile/同包Hypothesis缺失路径
重算六包manifest，全部compare必须“可沿用”、changed=[]、total_digest同本交接最初V2。
RS的H身份必须与原build-input/source-tree label相等，backend包闭包与全部本机镜像身份
也须匹配。实际H证据位于原authority runroot的`bindings/<H>`，保全部原件及SHA。

原审对实际绑定给GO并明确授权释放后，唯一测试者用
`/home/dev/gdds-s5-logs/execution/e-release-r2.sh`（SHA256=
`8045929aafecd86e1a00af8cf8ae8f0178d496425e7f017301788c193f0c23a6`）
核exact H/原marker/整机无活跃被测进程和容器，再只移除本人06占用；WT/env/images/原件
保留。实际release0后，原审核者把**精确H EXIT_GO**及binding/release证据锚点写入
`/home/dev/gdds-s5-logs/reviews/e-exit-review.md`，其SHA256和最终闭合回执另存于
`/home/dev/gdds-s5-logs/archives/`，不反写H。只有上述条件齐全才创建本地附注tag；
tag说明记录外置EXIT原件及SHA。未经明确授权不push，没有S6/P7或FE3c退出声明。
