# S3 E 取证范围收敛与剩余执行清单

2026-11-09状态：**Owner在本S3会话直接确认的`ffa1ee70bb`最小清单已完成技术核收，18个未启动项取消且未后移。** 原E §104–108记录范围、FULL r1及一次受控部分聚合核收，§110／`90ca3ebec4`已核最终Hf9ef六包／镜像绑定并给S3 E技术GO。DC33的fresh t1–t4没有缩减，已经在V4b0完成；W4未测、原M24失败保留。完整固定源与原件见[最终交接§18](p6-s3-candidate-handoff.md#18-最终v与h绑定技术核收及退出交接)，正式退出／tag／push另办。

## 1. 决策依据与固定候选

Owner在并行S4会话指出每阶段全量测量代价过高，应重点保障业务正确性，并询问S3是否也可按此收敛。DC97已明确性能数值达标不作退出门槛；本建议进一步请求明确S3剩余测量的具体范围，不能由DC97推导取消既定样本。DC98的通用原则及S4生效范围由该会话记录，S3以本清单的Owner确认和原E核收为准。

固定产品 **V=`4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb`**，Rust tree=`9d4f84ce0897099402226c77c548c487c4912008`。它与main后续S4算法分开归因；main最小移植`1ecb17f6de`的focused只证明该移植的受影响范围。本文不改生产代码、冻结Contract/golden、默认N1/32GiB worker−8GiB reserve/M24或新诊断档N1/48−8/M40。

## 2. 已具备的业务与资源证据

| 范围 | 已独立核收的事实 | 实际来源 |
| --- | --- | --- |
| A–D及E累计代码 | standard/keyless/ordered、完整facts-core、三族Arrow记录/JCS与真实reader、风险控制流、FULL任务与有限操作内去重、预算/取消/owner，以及被替代Python删除；20例旧实现固定独立expected及现役业务断言 | A–D限定GO、E §101／`6a91c4cf88` |
| 当前V门禁与容器 | 04同来源WT：四包直接沿用V1e最初实跑，backend/RS在V4b0实跑；当次Compose、真实config/全部DiffID及runtime provenance绑定 | E §92／`da66ded9b9`、候选交接§11 |
| 真实输入完整功能 | 05同V默认N1/32−8/M24，fresh t1–t4：v1/重复MO、v2 FULL、Submit、真实读取/approve/Archive/History；同worker、OOM三键0及正常收尾 | E §90、94、97、99／累计`6e30955ff4` |
| W3 MO诊断 | CT108同V、同输入/镜像/资源档N1/48−8/M40，一预热三测量均合格；组统计尚待单次受控聚合 | E §98、103／`296a46770e` |
| W3 FULL诊断 | 同V同档预热actual0；原worker日志在同一Preview中出现baseline_to_initial与initial_to_modified两pair，bundle pair_count=2；631表/64变更/0失败降级、同worker/OOM三键0及正常stop | 原E本轮只读原件评估；warm outer `b2f243a135f9bf3251261e1968131d67a21607f60f870d9ecfc7163e868e1f75`，receipt `7b0099f6b04afaa9d5c33c14c0d88ecca0fd7b9ed704467faf7cd2e0d819c3f9` |

W3 FULL r1已开始且未终局，继续等待自然封口；不因缩减建议强杀，不提前写成功。W3 MO组和W3 FULL诊断的输入为2×t4派生负载，不能据此宣称所有真实生产分布或S4优化收益。默认真实t1–t4与增预算派生负载两类证据分别列示。

## 3. 建议取消的本阶段重复测量

建议在当前W3 FULL r1自然封口后，**取消全部18个未启动项**：W3 FULL r2/r3两项；W4约10% MO/FULL和100%压力MO/FULL四组各warm+r1+r2+r3共16项。不另加一轮完整旅程，不为补齐性能表追加W4单次大负载，也不把这些取消项自动移到S6或其他阶段；以后确有需求时另定实际范围。

理由：05四档fresh已实际覆盖默认资源档的两pair及下游业务消费者；W3 FULL预热又在2×t4、M40下实际执行同一Preview的两pair并通过既有owner／资源守卫，具体两侧同时驻留量未单列。FULL r2/r3增加重复统计，未增加生产路径。W4已有独立accepted输入形状/计数和D节两表×模式的native/Arrow业务断言，但没有631表全负载旧oracle；增加四组统计不能替代独立业务预期。

取消后必须保留这些限制：W4约10%及100%在V4b0的全表运行、容量、输出和性能均为 **NOT_RUN／UNKNOWN**；W3 FULL只保留实际warm及r1观察，不给一暖三测统计、中位数或范围；不记为原计划六组完成。原M24的W3基线Submit预约拒绝、首次拒绝点未知，旧M40准备/局部排序失败全部保留，不改为成功，不以新档通过证明M24的2×t4容量。

## 4. 确认后仍必须执行的最小清单

1. 等待当前W3 FULL r1自然封口，由原E核其原exit、receipt、原件SHA、实际两pair、同worker/资源与收尾；若失败，保留首失败并按既有普通finding/DC68规则处理，不用取消范围掩盖故障。
2. 使用已审固定`aggregate-run.sh`在CT108原子占用下**只执行一次受控只读聚合**，读取实际收据集合。W3 MO一暖三测出真实中位数/范围及分段；W3 FULL原始观察单列，其余组保留NOT_RUN、统计UNKNOWN、`all_groups_complete=false`。外层exit0只代表聚合过程及捕获合格，不代表六组通过。不在开发机计算统计，不修改原始样本或聚合器来填缺项。
3. 更新累计交接、性能报告及协调/计划：列真实结果、原始失败、未知、Owner批准取消项和适用资源档；保留Q18独立GO、FE/原基准/S4/S5边界。业务与冻结bytes/golden要求不减。
4. 固定最终docs-only H，保持V4b0的vnext产品树，在04原受保护来源WT逐包实际比较六闭包并绑定RS build identity/三镜像；实际闭包要求RUN的包由权威入口运行，不能口头认定carried。字面H执行稿由同E复审后交唯一测试者执行。
5. 原E核收A–D累计结论、上述实际证据及H绑定，给出整体结论与可独立核收的退出交接候选；不代办正式退出手续，不tag、不push、不改写引用提交。

固定聚合稿目录为`/home/dev/gdds-test-tmp/p6-s3-v2-sort-performance-remaining-4b0a2eec72-fixed/`，原E §100已静审：`aggregate-readonly.py` SHA=`e256e485ebe73c3a31db576f24d3bf081d3c4c7090567e2c17b1fe778ef17d85`、`aggregate-node.sh`=`85fa3e9598a547df9520c200339232bdd09b1d3f768b55cf56c8df222960ac9a`、`aggregate-run.sh`=`6f10ee5cbb89fe9b8d170017946314a49c255010554687017d8812afa26a5eec`。原稿本就支持部分样本及未知，不需改变采样/聚合语义。执行仍需Owner确认本具体范围、r1实际结果与原E适用核收、协调放行及现场原子准入；本文不把准备当执行结果。

## 5. Owner确认及生效范围

Owner对引用本稿`ffa1ee70bb`的具体问题直接回复“确认按最小清单收敛（推荐）”，据此§3的18项取消和§4最小清单生效。依据是已有合格业务/容器/真实数据证据及原E的缺口评估，代价是明确不提供W4整组容量/性能结论与W3 FULL一暖三测统计。§1–4中“建议／请求／确认后”保留提案措辞，由本确认落实；执行时仍须r1实际结果、原E适用核收、协调放行与现场准入，不把范围确认写为测试PASS。若以后需要另一个大负载业务证明，须另定输入/独立预期和执行稿；本次不追加或自动顺延。

## 6. 执行状态

§4(1)已在原E §106独核完成；§4(2)一次原聚合于CT108 01:54:35–01:54:39Z原exit0，真实报告/receipt及统计见[性能§13](p6-s3-performance-report.md#13-本次已批准范围的受控报告)，原E §107已核收PASS。§4(3)职责内报告已更新；§4(4)Hf9ef于04原同WT六包全部实际可沿用、三镜像身份绑定原exit0；§4(5)原E §110／`90ca3ebec4`给整体技术GO。18取消项均未启动，不自动后移；正式退出／tag／push未执行。
