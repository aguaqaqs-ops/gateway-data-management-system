# S3 累计产品候选与验证交接

**当前恢复状态（2026-11-08）：** Owner 后续已授权 Q18 实现、S3 剩余验证和 DC95 限定增预算诊断；S4 在另一对话按 DC96 独立推进。本稿 §1–6 保留原 V774/H685 的受阻交接事实，其中“Q18 未修”“不开始 S4”“不重启样本”等均为当时边界，不能覆盖后续授权和实际结果。最新候选、隔离范围及恢复状态见 §7–8；原 M24 失败不撤销，也未因增预算授权变为通过。

2026-11-08。Owner已明确选择：**保持阶段边界，保留性能阻塞，完成其余交接**。这不是性能待项豁免；S3 E不签GO、S3不退出，不提前实施S4，不改N1/32-8/M24，不tag/push/发布。

固定产品 **V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`**；Rust tree=`9d4f84ce0897099402226c77c548c487c4912008`。本累计交接稿连同最后职责内文档形成候选H；其完整SHA及实际逐包/镜像绑定结果以外置binding收据与原E独审最终节为准，不在本稿中循环填写自身提交SHA。H只增加文档，须以实际Git tree及同04同来源WT比较证明，不能口头认定。

## 1. 累计职责与独立核收

固定设计依据 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，设计独立复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` 最新结论READY_FOR_OWNER；实现起点 `5dde965a65`。主线并行前端/原基准文档不混入S3产品范围，不回退设计起点，不重开历史首轮设计结论。

| 节 | 产品/交接来源 | 原独立结论与职责 |
| --- | --- | --- |
| A | 产品`4d5a4b0d98ee`、交接`b8c0697df2be` | `f28c89eff5ac` A GO；Contract细化、三视图/消费者、预算与风险接口、独立固定向量 |
| B | 产品`fbb7fca65d81`、交接`4918cc5440d0` | `17fd6739b809` B GO；standard/keyless/ordered共用batch核、当前侧ordered摘要、取消/截止/预算、t1–t4替换期逐表差分 |
| C | 产品`854d3888a9de`、交接`c5bbc4544f97` | `ce217c0ad777` C GO；三族Arrow builder、完整JCS/facts、直接Parquet写、真实读取Arrow→Rust验证、raw golden一致 |
| D | 产品`a9da0c59277e`、交接`d1aad819be5e` | `055707a98436` D GO；Preview/History唯一生产接线、必要Risk列/原控制流、完整key操作内去重、有限阶段诊断 |
| E | 当前V774、实施交接`36a11750992e` | 原E审核者连续核修复及证据；代码清理与功能候选证据收敛，**整体E性能受阻，无E GO** |

原报告：[A](p6-s3-a-review.md)、[B](p6-s3-b-review.md)、[C](p6-s3-c-review.md)、[D](p6-s3-d-review.md)、[E](p6-s3-e-review.md)。E最终核收须覆盖A–D接口和跨节接线，不能只看删除增量；最终结论以E末节为准。

## 2. 唯一生产路径与冻结不变量

现役Preview/History由pair pipeline统一走canonical Arrow→Rust standard/keyless/ordered→三族Arrow records；Python直接把Arrow写Parquet，真实records读取经Arrow→Rust完整validator。Risk按需要的Arrow列批消费，逐行Python转换仅保留其实际消费边界。replacement、小metadata、Submit规划及raw/ref bundle校验各有独立consumer，未误删或强塞入S3；无Python fallback、生产切换开关或改名旧oracle。

facts的值帧、原记录顺序与blank私有字段保留；records Scalar/schema、排序及流式JCS是另一个逻辑视图；facts_core仍包含完整table payload，不用table hash拼接替代。content_digest与Parquet raw SHA分别回归，保原writer参数/1024行组；未改冻结golden或产物格式。风险上限仍先于等级过滤、pair优先、table异常与正常degraded累加差异、pair超限丢弃全部部分标注，命中仍重做closure及当前取消/时间检查。FULL仍为baseline→initial、initial→modified；完整schema/task_kind/key不为命中率裁剪，0命中合法。

同一operation持有输入/导出Arrow backing至最后consumer，builder/index/JCS/writer/risk/FULL按阶段计费；缓存可被必要计算释放并正常重算。节点workers/Cargo jobs4与产品N1分开，06的96GiB不当作生产预算。具体语义/生命周期向量及消费者归属见A–D交接和[E逐函数移交矩阵](p6-s3-e-handoff.md)。

E已移除旧Python keyed/keyless/ordered逐行算法、旧tuple writer/重复row encoder、旧Rust ordered Vec入口及其独有例子、B probe/薄桥/临时差分。实际删除文件包括：

- `backend/benchmarks/p6_v1_ordered_diff.py`、`s3_b_real_table_diff.py`；
- `backend/tests/test_comparison_standard.py`、`test_comparison_ordered.py`、`test_comparison_blank.py`、`test_comparison_s3_b_differential.py`；
- `rust/gateway-compute-core/examples/ordered_compare.rs`、`src/comparison/probe.rs`、`gateway-compute-python/src/s3_compare_probe.rs`。

以上均相对`vnext/`。旧suite独有业务断言已移至现役C/D/E live/records/rule-role/native tests，未把业务断言连同旧入口删除。C/D固定expected来自06旧a9 Python（算法追溯A 4d5）的20组捕获，JSONL SHA=`7c629fdbe64bc4ffb016135accd86cc74edacd93cd7b32347d4ed2364e0027f9`，不由新Rust回填。

Owner另授权的三个最小移植已纳入：claim间GC `028aff2da7e6`、cold catalog批COUNT/同key合并`c6a2792901ad`、bounded JCS hash sink `968e8ec7ee3f`。未合并原基准整分支。移除只供旧Parquet分支的21个Cargo包，保留其它锁身份；现依赖base `gateway-backend-deps:lock-578e079b762e`、完整input `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`、config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`及全部19 DiffID来源见E交接。四节点LAN预填已独核，未借此宣产品镜像通过。

## 3. 04权威、逐包来源与镜像

当前V在04 `gw-dms-test-04` 的**原3a同一来源WT**执行：`/home/dev/gdds-test-tmp/p6-s3-e-final-3a7e088b2a/wt/subject`。先实际六包closure比较，四未变包直接引用3a7官方整次runner0源，backend/RS闭包变化并实际运行当前权威入口；14:00:56–14:29:14Z runner0，node/outer均0，clean HEAD774/六锁无漂/本人marker释放。backend非serial3417、serial74通过；RS非serial1764通过/1 skip、serial214通过。未重复执行runner中的Compose。

| 包 | 最初实际运行来源/本次动作 | 来源总closure digest |
| --- | --- | --- |
| rust | 3a7，当前同WT实比carried | `a0c39ae3942c1446faed5354768d0ef48a113b52e377421bf09762bff802c0f9` |
| shared_kernel | 3a7，当前同WT实比carried | `ae3f5a4d585baf032c2d087d961878d7d4d586c0c6757f5d613161e755556436` |
| repository_contracts | 3a7，当前同WT实比carried | `713fa6e1db03f194e6d2adc1e7591996929e6c606162a4f2b37fbe4cab2791f4` |
| repository_client | 3a7，当前同WT实比carried | `129ae16353fb52b5f1147fca831dee92f376fa2c3e0394fd987b34dd31a49e5e` |
| backend | 774，本次实际运行 | `47662ae45adc05c4ecdbb7c0bc763cdb3ed3665cd5ffb5272a8f03783846e3a8` |
| repository_service | 774，本次实际运行 | `140fc887f95d517bcbfba2201b9047dd5e02f2637208e2e6e158babd9aa7612c` |

3a7完整SHA=`3a7e088b2a1d66a6c7ab847d5119eb465628a601`，最初实际六包官方runner SHA=`0b8c865d77d8a9818eee80a2180385e1643b8772dc34e1fede6da1209855b88e`。其自定义外层镜像绑定exit1仍保留；该原runner整体0可作四包源，不能把旧镜像外层改称0。774补末Submit Compose当前provenance后，当前镜像出口实际0。

当前原件根 `/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3-control/authority/`：outer SHA=`a9bb2f0ff2d635e4e28526560fa4fc2a4b295daab8d4992630bdf5a9cb35038c`，runner=`e835612e1f91431fa15b97fbdf2ae326e2d728ca076fb964c99574b3d39f0461`，driver=`e0ef297b3eb15fc599d8183ecd5c744ccadbc33b6205e900efbb856d29eb1059`。`source-manifests/`六份保最初实跑head，`carry-comparison/`含本次真实六比较；不引用沿用结果作新来源。

| 当次镜像 | config digest | 全部DiffID所在原件 |
| --- | --- | --- |
| backend | `sha256:ce1d46ac3d2574c0ecb1faa706c4744b18db9d5de4e2f24950845da6632bab04` | identity JSON全13项 |
| worker | `sha256:81b5a33b5ab871d72fd705f08b396417a65daec175300450d8e5bf58d08278c6` | identity JSON全13项 |
| Repository Service | `sha256:cecc1bd75b98f7047b2af4a58b9d496ee0d869aa45704801a1557d7d2506bcff` | identity JSON全28项 |

`captured/image-identities.json` SHA=`edba3acf92c4a8b84ed7419b1b3112e7f7a187775293d1b853f20e24fa50ef2f`，provenance=`57d2dcb55a70e30912ad3b63e4d5b4e9b3b8c8c83c9ae1e92f082c9eacc9686f`，RS官方identity=`67478f02b35f95519c0793747c49d9b547efad9aaad5c83a775f1e296d4b1a19`。实际container.Image与当次同节点tag ID逐项相等；config/全DiffID另域核，未混比containerd ID。当前V→H容器沿用仍须另实际绑定；V的门禁PASS不代替H结果。

## 4. DC33真实范围与未改consumer的原source证据

Owner已确认fresh t1–t4完整功能范围，又专项批准本轮t1–t3从05改06；不继承S2b例外。每档v1/重复Preview MODIFIED_ONLY、v2 FULL，覆盖Submit、实际Repository读取/approve、History，N1/32-8/M24不变。3a7四档已fresh通过；后来774仅改host benchmark及两测试、生产src对象ID不变，又实际重跑774 t1验证新Monitor。t2–t4按kickoff §5（第61行）作为未改consumer的原source既有证据引用，不能写成774实测。

| 档 | 实际源/节点/result起止UTC（截取整秒） | 直接原件与核收 |
| --- | --- | --- |
| t1 | 774 /06；14:03:18–14:07:14Z | 新control `s3-e-final-t1-774acf33a3/`；E review §55；完整功能、同worker/cgroup/镜像/清理0 |
| t2 | 3a7 /06；12:35:06–12:48:52Z | 原control `s3-e-final-t2-3a7e088b2a/`；E review §45；原source业务/资源证据 |
| t3 | 3a7 /06；12:54:17–13:16:24Z | 原control `s3-e-final-t3-3a7e088b2a/`；E review §47；原source业务/资源证据 |
| t4 | 3a7 /CT108；12:25:24–12:46:16Z | 原control `s3-e-final-t4-3a7e088b2a/`；E review §44；原source业务/资源证据 |

原control根为 `/home/dev/gdds-test-tmp/p6-s3-e-final-3a7e088b2a-control/`。t2–t4直接引用原实跑，不从S2b旧算法沿用；三个原result/outer/manifest均由原审独算。原运行成功后已删除其项目卷，故**不称DC64保卷qualified source R，不宣称卷副本续跑**；这与04同来源WT保留的按包closure沿用是不同判定。只能说明未改consumer的原V业务/资源事实，不能由此自签“最终774全部四档fresh通过”。该边界及源证据矩阵以E末节独核为准。

## 5. 性能：实测、推导与未知

当前完整负载W3 MO warm原exit1：已过输入与census前检，但v1 Submit被操作M24预约拒绝，未到v2 Preview。失败操作 `op-b9453ef4993e76865434ad01` / step1，readonly终端诊断 `operation memory reservation exceeded`。不是已证物理OOM，也未观测首拒stage/表/need/live；源DDL估算不作调整M的依据。详见已独审[容量阻塞报告](p6-s3-e-capacity-stop.md)，含原始SHA与Owner三个方向；Owner已选择保持边界。

| 范围 | 已发生 | 可声明与未知 |
| --- | --- | --- |
| D两表阶段诊断 | 06的2x、10%、100% × MO/FULL六例0 | 只属两表/631表、InMemory store/M外等已列条件；不是完整Preview/READY或最终统计 |
| 当前W3 MO | 基线v1 Preview通过，v1 Submit资源失败 | 无成功warm，无v2比较/READY/完成时间 |
| W3 FULL | 未运行 | 受同v1基线前置阻断，未知 |
| W4 10% MO/FULL | 未运行 | 同v1包SHA与前置，推导受阻；不是已测失败/成功 |
| W4 100% MO/FULL | 未运行 | 同前置，压力结果未知，无性能门槛也不记通过 |
| 正式1warm+3、median/range | 未形成 | 剩余23队列从未启动，不推统计或S6达标 |

作为失败前业务事实，v1 Preview114.783s属于空initial新增表路径（631 dispatch、0 native compare），不计W3比较提速。该operation的只读分段如下，均不能代替v2：uploaded projection5.860s、comparison0.196s（read/build0.049s + 后续table/facts JCS0.147s）、native index/build各0、records publication0.016s/Parquet写0、Risk总15.346s（必要Arrow转换0、rules0.017s、publication15.320s）、surface/table export15.942s、bundle26.468s。这些数值未覆盖端到端所有等待/解析/调度，不把残差称纯Python。

计时包含关系保留原名：native records build包含其内部未单测artifact JCS；`records_jcs_seconds`另计后续table/facts-core JCS，不能从native build扣除。Risk必要Arrow转换属于rules_evaluation的嵌套子段，fact_extraction只建lazy view；不能重复相加。native input read只覆盖Rust桥阶段，全部Python/Parquet/上游I/O未独立覆盖。W2无行比较，不计S3比较收益；真实0去重命中合法。S6 READY≤60s/3min、完成≤10min目标未豁免，当前无该目标的合格测量。

## 6. 失败、资源及后续责任

旧C/D/集中候选、dcfa mypy和838预检首败均保原件，未改expected/golden消差。774第三轮focused实际74+3后恢复职责内验证；这不把后续真实容量失败重分类成工具重试。旧3a因孤儿日志collector导致的W3失败也保持exit1；当前774已到业务的新失败独立留存。

当前CT108失败现场已按独审固定稿归档再清理：私有目录 `/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3/w3-capacity-preserved-state/` mode0700，`stopped-volumes.tar` 387,051,520B、SHA=`ba1b07d4e5d19824532f70a432dc0557cc7781904c26e4f1621a90a16cae4444`，只保该节点，不传内容。收尾日志 `/home/dev/gdds-test-tmp/p6-s3-e-w3-capacity-cleanup-774/archive-cleanup.log` SHA=`ca8689f4049e333dc3bb6b7e471179c195c5a7d4fb1717e9dd28f468d30802b3`，实际exit0；own3容器/3卷/1网已删、marker与8000释放，原failure result SHA未变。归档只是本次故障的一次性私有快照，不是产品evidence机制。

06已释放，05/07及前端服务未接管，原性能基准所有冻结WT/镜像/输入/卷/证据未修改。04门禁WT/五环境/当前镜像/原日志保留，供H绑定及之后真正阶段退出DC51核收；H绑定本身只读比较和checkout，不再跑门禁或重tag镜像。

FE3b/FE3c仍由前端Owner核收，不冒认完成。FE3c Q18归档权限用户获取不到close所需expected_review_version的接口缺口仍未修，须独立后端项；空initial上传A缺一次generation time是现规则，不改S3语义。S4/S5只移交接口与容量问题，不在本轮启动；S4前置S3 exit的顺序冲突需要Owner另决，不能自动跨过。原基准性能线保持独立。

剩余责任：原E审核者完成累计A–D/删除/独立expected、真实source证据边界及H绑定核收；产品候选和功能证据可独立复核，整体性能阻塞持续。Owner后续若改变范围/场景/阶段顺序，须另形成固定设计与适用验证；当前不重启样本、不放宽M/输入/同worker守卫，正式退出/tag/push均未办理。

## 7. 恢复执行与隔离候选（取证进行中）

Owner 的 DC91 将五个 32C/64GiB 节点合为按有效 marker 调度的测试池；DC95 允许本轮 worker 在现有资源内上调，最大 32C/64G；DC96 允许 S4 另线设计实施。现按原 E 独审通过的[资源小稿](p6-s3-resource-profile-plan.md)只验证一个新档 **N1、单 active、48GiB worker／8GiB reserve／M40GiB**，生产默认 N1/32−8/M24 不变。增预算结果按实际条件另列；原 M24 W3 基线 Submit 失败、原始日志和私有卷归档保留。

Q18 已完成：产品 `94b25a32792821cbc5b3230d98a0aa6f13493c32`，原审核报告 `27eab454b7`、最终交接 `8cf472a4dd` 及其独审 `964d900d44`，结论 **BE-Q18 GO**。归档候选读取在同一 read transaction 返回必需的 `review_version`，归档请求 `selected` 仍严格只投影原两字段；权限、CAS、schema、digest 和生成时间业务预期不变。06 的 focused 及四条实际 Compose 旅程原件、镜像绑定与可转前端回复见 [Q18 交接](p6-be-q18-handoff.md)。附加 live OpenAPI 抓取缺失，未记通过；FE 快照、类型和 mock 由前端在自己的实际栈更新。Q18 GO 不代替 S3 验收。

资源支持提交 `e76342ef0b58bb0120fc60d8a063d838140ee28d` 仅修改限定 settings、Compose、host benchmark guard、两个 tests 和资源设计文档。main 后续 S4 B 已修改 Rust 树，因此 main 的测试 typing 修复 `a39339f18d` 不直接作为 S3 测量 V。按并行短分支例外，从 e763 只接该单测试文件修复，固定 **V=`1e669c053f2486c50a8413c58de11d923d7f3cad`**，分支 `p6-s3-resource-candidate`；Rust tree 仍 `9d4f84ce0897099402226c77c548c487c4912008`，没有并行 S4 B。main 未回退或改写。新最终 H 将只在这一候选上增加职责内文档并做同来源绑定；任何结果均不冒称并行最新 main 的 S4 代码已经验证。

| 本轮范围 | 截至本次文档提交的实际状态 | 来源及限制 |
| --- | --- | --- |
| 资源首轮 focused | e763 的 backend mypy exit1；后续步骤未到 | 原失败及 SHA 见协调 §29、E review §68，不改写 |
| 修复 focused | CT108／V1e669，outer/node 0；102 nonserial +3 serial，backend/RS Ruff、mypy、native input 及两档 Compose config 通过 | 原 E §68 独核；前三包静态同源码事实直接引用 e763 实跑，非权威 carried |
| 当前六包／容器门禁 | 04／V1e 全六包、同次 Compose、镜像出口实际0，原 E §71已独核 | 六包均因实际闭包变化而重跑，无carried；原04同来源WT保留，最终H绑定仍待 |
| fresh t1–t4 | V1e在05四档完整fresh均actual0且原E逐档独核PASS | 每档完整v1/重复MO、v2FULL，N1/32−8/M24；属于V1e直接原件，不冒后续sort修复候选实跑 |
| 新档 W3/W4 | 首warm在RS启动时actual1；修订M40 warm已完成v1全前置，但v2 Preview因native records sort局部2GiB cap失败 | 原失败及0有效warm保留；剩余23未启动，无合格M40 warm／1warm+3统计，见[性能记录](p6-s3-performance-report.md) |
| E 整体与退出 | **尚未 GO／未退出** | 最终 H、逐包／镜像绑定、fresh 原件和性能报告仍待；tag/push/发布未办理 |

focused 直接原件：`/home/dev/gdds-test-tmp/p6-s3-resource-1e669c053f-focused-r1/`，outer SHA=`2b1bbc8095d8622d7c660c0d57aeab82a383ddccd65991e4e63534cd0d0dd7f3`、node/captured SHA=`cbc4c7b32e1ab98cd71940486693c6c43c950a9425b3d770a898776f3ed12d65`。CT108 性能准备直接原件：`/home/dev/gdds-test-tmp/p6-s3-resource-performance-e76342ef0b/prepare-control/`，outer SHA=`c32722d0968aae7fe3bcaf526a251a9e79a3796ec38fb201bc91dc5dfc1d874f`、node/captured SHA=`895a6f19b2b0b3ac1206f8963d36143e8b609d4c9b059c71cc6d58db07bf7783`。后者路径名称含旧 e763，实际固定 source 为 1e669；prepared-images.json 的 `config_digest` 字段只是 Docker inspect 本机 ID，不能拿它作跨节点 config。真实 runtime config 与全部 DiffID 由当次 docker-save 原件核收。

恢复后的权限工具修复、容器收尾次序修订及当前实际原件见协调§31和[性能记录](p6-s3-performance-report.md)。原05全旅程稿2408／18c9与旧CT108r1warm8992／d58c在执行前撤回，修订稿在node marker持有期间封核心原件和大tar哈希，最后释放，经stdout真实事件与控制端独立receipt核实际释放；未修改原失败。05当前新完整稿b82a／e7d8的t1已通过，节点result的pending快照不能冒作最终释放结论，也不因pending否认实际control核收。

当前仍无整体E GO或最终新H绑定，未对未知项给通过结论。后续四档、W3/W4及最终交接按各自原件继续核收。

## 8. 排序预算局部修复候选与待验证面

最新修复候选 **`4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb`**（parent acb417，再上为V1e），仍在S3隔离分支，Rust tree9d4不变、无并行S4 B/C。生产仅透传既有已预扣`native_budget`替代每表固定2GiB sort cap，另两测试及设计说明；不改变算法、FULL JCS排序、M40/N1、512MiB输出／reader、2m／1024或冻结golden。原E §81设计CLEAR、§83代码CLEAR，§85已核06 focused实际0，外置执行稿、原始SHA与限制见[性能记录 §7](p6-s3-performance-report.md#7-m40修订warm终局局部排序限额与新修复候选)。

截至20:43Z，本候选04集中门禁已启动，尚无整轮原exit／镜像封口；05新准备actual0、原E §87核PREP_PASS及full稿静态CLEAR，协调仅放行t1完整fresh，后续仍逐档核收。原E报告§86–88提交`dd40f20041`分别记录新04静态、05实际准备／旅程静态，以及CT108原失败标记release-only实际PASS；最后一项仅释放本人标记，全部失败停资源／原件保留，原M40 warm仍失败／0有效样本。

本候选的集中按包门禁／镜像、新产品t1–t4完整fresh、48/8/M40新W3首warm及后续样本均待实际取证。新warm必须先有新04 actual0与原E镜像核收；剩余23及聚合仍HOLD。旧源V1e门禁与四档各自合格事实保留，后续仅按实际闭包／影响／直接源判沿用，不能由“改动小”口头认定。main的S4工作继续独立，当前修复尚未移植main，也不冒main已经验证。最终产品V、文档H及同04原WT绑定在收敛后重新固定；当前仍无E GO、阶段退出或tag／push。
