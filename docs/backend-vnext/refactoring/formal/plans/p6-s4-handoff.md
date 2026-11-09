# P6 S4 累计交接

当前状态（2026-11-09）：**A–E GO，S4已正式退出。** 最终产品V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`，最终交接H=`1e778aae0522db75ea1f507ecfa83a6d7b714d65`。
本地附注`p6-s4-exit`于03:11:54Z创建，tag对象`93b251daf2b436baca5593f10e180831294d0af6`精确指H；[最终原审回执](p6-s4-exit-review.md)结论 **S4_EXIT_GO**。本次补记为退出后文档，不移动H/tag，不宣称在补记提交上新跑门禁。
不授权S5，不推送，不代签S3。

## 固定候选与原审

设计候选`de0eb3a8b2f9881737a183f0a4663dad9a75d67f`、设计报告归档`e2bbbe85d348d6d90cb595b9090786fa842f7313`；两次设计CLEAR只覆盖设计。
实施授权、资源授权及后续验证收敛分别见Owner DC96、DC97、DC98；最新范围以[业务验证清单](p6-s4-business-validation-scope.md)为准。

| 小节 | 固定产品候选V | 原审核者结果及交付 |
| --- | --- | --- |
| A | `fb9c7fbcd95b411d7598ade2a93bc8a7e6514697` | GO；[handoff](p6-s4-a-handoff.md)、[原审](p6-s4-a-review.md) |
| B | `788ed36e7742a067bf01c16ad2e6aaed2fed91fb` | GO，F1–F7关闭；[handoff](p6-s4-b-handoff.md)、[原审](p6-s4-b-review.md) |
| C | `48053253f9a3c46b0d227167a4d0ca1f8ad94bf3` | GO；H=`f4d9e19ac966a9b96d5587bab284bc25a36c4c22`；[handoff](p6-s4-c-handoff.md)、[原审](p6-s4-c-review.md) |
| D | `41d1944208fe99911df0a15641ab651505d1274c` | GO，F-D1–4关闭；H=`9d91653ac96908cc9cafe159fcb7b76a5a3525bd`；[handoff](p6-s4-d-handoff.md)、[原审](p6-s4-d-review.md) |
| E | 最终产品V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f` | GO；[原审快照](p6-s4-e-review.md)与[最终实际核收回执](p6-s4-exit-review.md)，H绑定条件已实际满足 |

A–D逐节focused、修复与失败原件均在各节handoff及[协调记录](p6-s4-coordination.md)，不由后继成功覆盖。
当前Rust tree=`e2a901417b19259ece669637a41545e774261445`。
E当前V相对`c9e9b3e74ab2e2895f9e0f6aac78740e7f48f008`只改benchmark时间判定及8个测试，DC97时间数值不作退出门槛；生产Submit与Rust未改。

## 实现、独立预期与消费者

- Submit以完整persisted列、canonical storage key逐表构造native storage task，Rust给精确summary，Python共用policy决定NOOP/PATCH/REBUILD，再由唯一Rust SQL渲染；所有删除/重建DDL前置，仍交原publisher/包API。
- ordered gid/no、伪gid、keyless重复行和mutation hash顺序、1000行/1%、原连续256行窗口内4MiB拆分、最终200MiB admission及冻结SQL字节保持。强制重建未diff时`net_counts=None`，不反填净计数。
- 两保留facade显式接有效context；同operation M覆盖表级owner、输入/Arrow/FFI、capacity、SQL导出bytes至最后消费者。T1 PREPARED、prepare checkpoint固定包/key复用、非INITIAL parent严格校验、技术main与业务BaselineHead分界及恢复/CAS屏障保留。
- D已删除被替代Python行graph、Submit旧replay wrapper/专属类型与无消费者digest入参、对应mock/probe。五个standalone generic library seams按现役架构规则明确保留，不能冒称app/worker消费者；真实planner/ChangeSet、外部ledger、publisher/readback/恢复消费者见[A迁移矩阵](p6-s4-a-handoff.md)与[D交接](p6-s4-d-handoff.md)。
- 六份既有SQL golden未由新实现重写。257行/4MiB边界来自固定旧`7d0ce6220ac2541b76ab75191d43ce6113003966`受控捕获；200MiB边界向量来自手算，原C独核。来源/原件见[协调§9](p6-s4-coordination.md#9-c当前修复与独立预期)。
- B真实t1–t4的850表差分已实际通过：340表真实净计数与旧oracle逐项一致，510表保持未计算；这是独立差分诊断，不冒生产M24容量/完整旅程。
- S1a复核仅覆盖generic planner/Rust facade和private Dolt：旧/当前PATCH 36,238B与REBUILD 1,576,977B逐字节相等，实际Dolt两路9828行/hash相等。其合成after不满足正式canonical连续no，不能冒native StorageTableTask/生产worker证明；原件与限定结论见[协调§14](p6-s4-coordination.md#14-e-已核收的-c9e-权威与-s1a-组件原件)。

## 已核收的权威与镜像来源

以下均由唯一Luna在04 `gw-dms-test-04`执行、原E独立核原件。来源WT为
`/home/dev/gdds-test-tmp/p6-s4-e-final-r2-c9e9b3e74a-node/wt/subject`，
当前持续保护其环境、按包路径和镜像；最终H已在该同节点/同WT实际比对，六包全部可沿用。

| 包 | 产品V6786的方式 | 直接实际通过来源 |
| --- | --- | --- |
| rust | carried | c9e全六包runner：fmt/clippy/test均0，207 tests |
| shared_kernel | carried | 同c9e原runner，261 |
| repository_contracts | carried | 同c9e原runner，152 |
| repository_client | carried | 同c9e原runner，161 |
| backend | actual | 6786 runner，3505非serial＋77 serial |
| repository_service | actual | 6786 runner，1764＋既有skip1、214 serial |

c9e runner全次0，22:31:48–23:04:30Z（11-08），SHA
`a32acbdb407b3059222ad786dfec4c98b7a581195d549f4ea741a790fcf4baae`。
6786受影响两包runner全次0，23:37:52Z（11-08）–00:08:34Z（11-09），SHA
`7e4a066156890ab8cbca03b4e6fbfed6bad17682e1fde4eceaae322c592128e5`；
五包ruff/mypy、强制扩展/build-input及8focused均0。
四包是同来源WT实际闭包零变化直接沿用，不表述为6786重跑Rust。
当前backend实际runner source total=`cb7bc6c2ec0c913a85613077f2d7cf6c5914d35ec4937170ff42544b28f9a024`，
RS=`3207cd853f66d6783c8ba2666404354cb2fedc4c401ebc2df4dcf330ab14b26a`；885ab预检摘要不是通过来源。

同6786权威运行有正常本机Compose build/三容器旅程结果，原E核收
`AFFECTED_AUTHORITY_COMPOSE_ACTUAL_PASS + FOUR_DIRECT_CARRIED`。
config digest、全部DiffID、labels及本机容器image ID的原件identity SHA
`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`，
runtime tar SHA `5d476b9634dc64ba2a87c3d1ae98cc70d8423c386c033be89101b831f5431785`（747,837,440B）。
缓存/两dependency-base/跨05传输和04隔离real WT实际身份核对见[协调§16](p6-s4-coordination.md#16-2026-11-09-权威封口镜像修复与真实旅程调度)，不以inspect.Id冒保存config字节SHA。
最终H容器等价和逐包carried已于04实际绑定：六包changed_components均空，四包直接c9e、backend/RS直接6786；H RS build-input/source-tree等原标签，三镜像本机ID/全部DiffID/labels等原身份，未重建、重tag或运行runner。原件见[协调§20](p6-s4-coordination.md#20-最终h实际绑定与本地s4-exit)。

## 真实业务核收与取消项

04 W3 FULL warm的journey本身0、独立Repository核对1，未记为合格warm或成功统计。
私有RS副本只读诊断已将差异缩到`app_cfg__x2`的24行；v1/v2的631表完整schema/count及其余四代表表内容均与固定旧B一致。
旧B单表明细受控捕获再次核回原52ad摘要；原E按冻结SET声明从旧B独立映射wire后精确得到36a3，并反向核完整24行Counter相等。
差异是Canonical Storage §5.1内部SET文本与Repository §10.1/ADR0013正式list物理表示，未发现该表持久行变化；具体业务疑点已关闭，原warm外层失败仍保留，不倒改为成功样本。
原件、SHA和前后卷指纹见[协调§17](p6-s4-coordination.md#17-dc98收敛与04失败定向诊断2026-11-09)。

真实t4的新独立SET wire预期只从固定旧B两包重取app_cfg原24行，各先核回旧1ac摘要，再按声明映射2c9摘要；其他四表及完整schema/count沿原B JSON。
mapped JSON SHA=`258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f`，原E独核完整行多重集，旧expected不改。
短验证r0在uv-consume拒绝保留参数`--project`处exit2，core/Compose/产品尚未执行；本人r0标记已于02:42:47Z受控释放、outer/node0，原件持续保留。修订r1只改外部参数名为`--compose-name`并用新namespace，唯一Luna已在05实际完成，原E独核通过。详见[协调§18](p6-s4-coordination.md#18-set口径闭合与dc98短真实验证固定稿)及[实际结果§19](p6-s4-coordination.md#19-dc98真实t4实际核收与最终h条件)。

05 r1于02:44:21–02:50:31Z（控制器原UTC；节点业务02:44:24–02:50:32Z）outer/node/capture均0，起止6786 clean、六锁/native e2a一致、本人标记已释放，三服务正常TERM停止、无OOM/重启；RS退出143且stderr有完整正常application shutdown。两次Submit后的technical main分别为`1c9u40na8fosd9cc9i47h4bnnusif5iu`、`g2030m91c52sd4evr1ml5enkn2p7o1t0`，各版完整312表schema/count及五代表表内容均与独立旧B/Contract预期一致，app_cfg全24行Counter一致；v1合法审批/Archive建立增量baseline。一次观察的Submit调用起点至已HTTP核main返回的保守秒数为**104.105179 / 77.447006**，不是重复统计或跨源提速证据。

首次312表REBUILD、净计数未计算，SQL 50,566,368B；增量27候选表为12 PATCH/15 REBUILD，25表有真实净计数、2表未计算，SQL 2,125,772B。完整日志含逐表事实/预算，未把未计算补0。单operation账本预约高水位40GiB不等于RSS需求；worker实际cgroup peak 926,642,176B、RSS HWM 648,097,792B，不由低RSS下调估算或宣称M24成功。原件目录及SHA见协调§19。

按DC98撤回28旅程、04/05的12/16队列及after-FE稿，取消完整fresh t1–t4重复旅程、2×t4/W4/100%压力和1暖3测；不跑History或为本节完整消费FE records。
剩余真实范围仅冻结标准t4 v1/v2的一次首次/增量生产Submit及必要合法Preview/审批/Archive、真实表核对。
原样重传零Repo operation等已有合格业务断言复用，按实际改动补必要focused；时间顺带记录，不新设每段耗时验收。
取消项记范围取消/未验证，不记PASS，不自动搬到S6/P7。

## 配置归因、保留与退出收尾

- 原基线N1/envelope32GiB/reserve8GiB/M24保留；S3原M24容量失败仍属S3。S4未完成M24生产容量测量，不写M24成功或从S4倒签S3。
- 本轮选定显式N1/envelope48GiB/reserve8GiB/M40，RS及系统留余量；05真实短验证资源已通过，guest32CPU/affinity0–31、worker无额外NanoCpus/cpuset限制、kernel仍N1，实际cgroup限48GiB。仅覆盖本次真实输入，不外推大负载容量；原失败样本的低RSS或无OOM本身不等于容量PASS，不降估算、不改生产默认。
- 原失败/工具失败、被冻结输入、旧expected及新明细、日志、WT/env/镜像均保留；04失败卷/私有副本已停，本人原HELD标记02:21:32Z实际受控释放，后续旧B映射捕获亦已释放自己的标记。05短验证已按本人标记和实时准入完成，失败与成功原件均保留；后续使用仍遵守节点准入，不动S3/Q18/FE资源。
- 最终H实际逐包/镜像绑定、原E回执及本地附注tag均已完成。源码V及Rust没有因工具修订变化，未重复已合格权威包/业务旅程；H绑定r0的PATH工具失败及受控恢复也按原值保留。
- H内[原E快照](p6-s4-e-review.md)原文SHA=`978fb940253e55665aefefd4774963b330999e59d7d33bbfad16d94c7c02f7f9`；退出后归档[最终独立回执](p6-s4-exit-review.md)原文SHA=`510b035244c1b8e65a4cac9b7a1d85b30d68c1467760b8b20271c0f96fa0c05e`，未改写快照/H/tag。保留原04来源WT/env/images、引用成功/失败原件及真实输入；05成功停机卷/容器与04失败/私有卷均保留供核查，04/05本人标记已释放，整机不因此保留。S3/Q18/FE结论各自独立，未push、不进入S5。
