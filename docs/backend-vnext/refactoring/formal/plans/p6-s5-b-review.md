# S5 B 独立产品审核归档

固定产品候选 `e1098b2a62daaf779b758de80ffd0013b17650a2` **B CODE_GO / EVIDENCE_GO，可进入C**。原空serial入口exit5及DC68续步exit0分别保留；不改称一次完整入口成功，不作为qualified runner、Compose或E证据。以下为同一独立审核者原文，逐字保留；原始 SHA 与归档整体 SHA 分别记录。


---

原件：`/home/dev/gdds-s5-logs/reviews/b-r1.md`；SHA256：`2f76ae2c21472794c92dc9f97d127f6c0ac5d8acb0cc252fd23497cf897988e7`。

---

# P6 S5 B 独立产品原审 R1

结论：**CODE_CHANGES_REQUIRED**。主事务、并发替换和lease/pin边界符合已审设计；两处有限派生失败仍可反向影响业务，需最小修订后连续复审。产品检查全部 **NOT_RUN**；本报告不预签C/D、T3实际接线或E。

## 1. 固定对象与独立性

- Candidate：`911d1586a92b6cbb02eb1208a726d882f333b0b2`。
- B base：`049ab2147ec6cc5b33b07d4f3381a96ac0926a8b`（A产品eb645已证据GO）；Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`。
- 只读detached worktree：`/home/dev/gdds-s5-review-b-911d1586a9`，创建后及报告前核exact HEAD、detached、index/tracked/untracked clean，legacy链接正确。
- 完整核8路径1200新增：Artifacts引用端口/envelope、SQLite participant/adapter、UOW、唯一基线schema、窄intent释放、Artifacts Contract、新SQLite/FS测试及schema集合。相关既有LocalArtifactStore/root borrow、protection、UOW和export cache接口亦已核。
- 本人未实现被审产品/测试/Contract，未改被审worktree；未运行产品测试、Python语法检查、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。以下由固定源码核查，不冒称23个向量已通过。

## 2. 需修订 findings

### B1 — P2：成功pair后的可选 mark_used 预约失败直接传播

位置：`infrastructure/control_db/computation_cache.py:352`，`_ReadLease.mark_used`。

此接口在pair成功后可选延长TTL/登记uses，先调用当前checkpoint，再以`self._reserve(_DB_METADATA_BYTES)`预约4MiB。该预约抛MemoryError时没有有限回退，会穿出API；lookup/store对同类可选预约分别为miss/False。必要输出已持有当前M、可选维护暂无4MiB余量时，不能因缓存使用记账使已完成业务失败。

最小修订：仅将本可选预约/维护范围的MemoryError转为False，不touch TTL/use；保require-open、当前cancel/deadline、未知SQLite及其他异常传播。补一个健康lease建立后只拒绝mark_used预约的小向量，核entry/TTL/use不变且lease仍可用；可复用当前控制异常参数，不要求新重试/资源治理或完整fault矩阵。

### B2 — P2：深嵌套派生JSON的已知解析失败未进入载荷失效边界

位置：`artifacts/computation_cache.py:114`的`decode_cache_manifest`；`infrastructure/control_db/computation_cache.py:75`的`_entry_from_row`。

两处均调用json.loads/JCS递归校验，但仅转换ValueError/TypeError/CanonicalEncodingError。小于现有1MiB/64KiB上限的深嵌套文档仍可触发RecursionError；此为明确的载荷解析失败，当前会沿adapter的BaseException路径传播，导致坏派生cache不能按原协议条件失效/miss。该问题不需要扩大输入预算，也不能以字节上限推定解析深度安全。

最小修订：在现有两个载荷转换边界窄认定RecursionError为InvalidComputationCachePayload，沿原完整ref条件失效；不捕获SQLite/控制或任意异常。用共享最小deep文档分别覆盖envelope和DB refs解析即可，不引入新decoder、持久proof或泛化安全框架。

## 3. 其余关键核查

| 边界 | 源码结论 |
| --- | --- |
| authority/ref envelope | key绑定repository/kind/完整DigestRef，manifest/ref closure有严格类型、大小、JCS、顺序与kind成员数界限；payload仍交Comparison/Risk owner，SQLite不复制业务codec。ArtifactRef id拒路径，LocalStore拒同id不同ref覆盖。 |
| 读取次序 | adapter先持root共享read_session，再短BEGIN IMMEDIATE事务按未过期key查entry并pin所有登记refs；事务退出才逐块hash manifest/member及decode，lookup不续TTL。metadata预约转给lease的ExitStack，失败关闭borrow/charge。 |
| 写入原子性 | 当前operation pin在任何文件put前一次登记全部refs；文件全部写完、逐块完整校验后才短事务upsert entry/TTL/use。触发SQL异常UOW回滚旧entry及旧TTL/use，不发布半条目；只留下原operation pin覆盖的可回收候选。 |
| stale reader/重复writer | discard比较完整manifest ref、members和format；mark_used按当前未过期完整entry比较。后writer替换TTL owner时旧reader仍持独立operation pin/root borrow，旧lease不能删/touch新值。 |
| lease/强pin | lease.close只关本borrow/decoded metadata资源，重叠lease共享同operation pin；最终batch在全部consumer关闭后release_operation_pins仅删active-computation-cache intent。DO NOTHING保同owner已有workflow intent，窄释放保checkpoint/source保护。实际C生命周期接线仍待下一节审核。 |
| TTL/清理 | store、成功mark_used和touch以同事务UTC更新entry、全部TTL intents和uses；默认86400秒。每批prune至多64entry+64uses，direct lookup仍有独立expiry过滤。TTL owner从scope/kind/key派生、与活动owner分离，不挂业务Head或commit链。 |
| touch_producer | JOIN限定producer/repository/kind/task/current manifest id和两表未过期，稳定kind/task排序LIMIT64，事务内不读文件；Artifacts Contract明确这是有界派生维护，未触达值可自然到期。此限额只影响后续miss率，符合比例化，无需增加后台框架。D须在原MatchingFinalizeFacts与窄SAVEPOINT内接线，本轮不代签。 |
| schema/UOW | 直接修改唯一基线与两expiry索引，严格schema集合同步；无迁移、双读或别名。真实UOW每次创建当前事务participant，read-only守卫保持，commit/rollback与其余业务participant共用connection。 |
| 异常 | 已识别文件/ref和派生载荷错误为条件失效/miss，optional lookup/store MemoryError回退；InterruptedError/TimeoutError显式传播，sqlite异常未混同OSError/ValueError吞掉。B1/B2为剩余两项有限边界。 |

已读23向量的实际输入/断言：双kind/scope、7类envelope错配、4类file故障、TTL时钟、重叠borrow及workflow保留、stale版本、写一半、同事务rollback、未知SQLite触发器、精确producer触达、65entry清理/expiry，以及可选预算/取消。使用真实SQLite和FS，纯envelope校验无Dolt fixture；未写同构函数矩阵。保留原独立payload和业务expected。B1/B2补最小向量后再实际执行。

## 4. 执行稿与必要验证

独核 `/home/dev/gdds-s5-logs/execution/b-focused.sh`，SHA256=`ee63697fd96ef5f3c9f63f75064426e20c0980457b425acd46876aaafbab2bf7`。相对已核A稿仅A→B参数/path/refs、6个backend目标文件及删除3个Rust步骤；两40hex、五节点枚举、clean/ancestor/完整vnext tree守卫、本人runroot Cargo target、offline/native强制重装/build-input、首失败停、日志和owned标志释放保持，无编排阻塞。未执行。

修订固定clean候选并获连续CODE_GO后，唯一测试角色运行五包sync/ruff/mypy、实际native build-input和backend6文件parallel/serial focused，共18步骤。Rust tree本节未变，A已验证的Rust代码不重复Rust检查；本轮不把native构建或focused称作权威runner/Compose。首失败保原件，不推进C/D或E。

## 5. 容器边界

Current HEAD：`911d1586a92b6cbb02eb1208a726d882f333b0b2`。本B子节未改依赖/锁/部署/container harness/container-only行为，不单独触发容器重建；current container gate仍 **deferred** 至E最终候选或实际触发边界，Carried from：none。最后已验证镜像仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`来源线索，本审核未重算或新增carried。当前产品检查均NOT_RUN，不以A证据GO替代B。


---

原件：`/home/dev/gdds-s5-logs/reviews/b-r2.md`；SHA256：`3b02b95007961da10ef276a5641ff9929c6febc4e52f57c79cb2ea796738c4c0`。

---

# P6 S5 B 连续产品复审 R2

结论：**CODE_GO，绑定 `e1098b2a62daaf779b758de80ffd0013b17650a2`**。B1/B2均静态关闭，未发现新代码阻塞；唯一测试角色可按已核执行稿正式执行必要18步骤，无须另申请许可。当前产品检查仍NOT_RUN，B证据GO及C接线尚未放行。

## 1. 固定对象与独立性

- Candidate：`e1098b2a62daaf779b758de80ffd0013b17650a2`；上轮候选：`911d1586a92b6cbb02eb1208a726d882f333b0b2`；B base仍为 `049ab2147ec6cc5b33b07d4f3381a96ac0926a8b`。
- Rust tree仍为 `c0213e18a9645c5cfbd39f310f532273a03a10cb`，精确不变。
- 只读detached worktree：`/home/dev/gdds-s5-review-b-e1098b2a62`；创建后及报告前核exact HEAD、detached、index/tracked/untracked clean，legacy链接正确。
- vnext仅3路径变化：Artifacts envelope、control DB cache及共享测试；无业务expected、Contract格式、锁、依赖或Rust变化。中间b93bed6仅Owner新角色规则文档；已读AGENTS/实施提示词/kickoff/coordination修订，本轮B finding由原审核者连续收口，B固定交接后退出活动分工，从C起新建角色，不改写A/B历史。
- 本人未实现本修订，未改产品、测试、Contract或被审worktree，未执行产品测试、语法检查、编译、fmt、lint、镜像或真实旅程，未创建子agent、push/tag。

## 2. 原finding闭合

| Finding | 当前修订与独核 | 结论 |
| --- | --- | --- |
| B1 optional mark_used预算 | 当前checkpoint及require-open仍在前；ExitStack中的try只包含reserve callback创建及enter，MemoryError返回False。UOW进入、当前entry比较、TTL/useSQL及事务退出均在catch外，未知SQLite/其他异常正常传播，取消/超时亦未吞。拒绝时不建立维护事务，不改lease payload/borrow。 | CLOSED |
| B2深JSON解析 | envelope和DB row两处既有parse/JCS转换边界仅追加RecursionError→InvalidComputationCachePayload；adapter沿原完整manifest/ref条件失效/miss。没有catch任意异常，没有更改SQLite/控制处理，也未增加decoder/深度平台。 | CLOSED |

必要向量复用原共享参数表/函数，合计25 cases，无扩展fault矩阵：

- manifest故障表新增4001字节deep JSON并收紧全部fault为精确InvalidComputationCachePayload断言；JSON深度失败独立于文件hash或大小拒绝。
- file/index故障表新增真实SQL member_refs_json深JSON，另保存独立健康key；失败只删目标entry/TTL，根借用可释放，健康entry仍可实际lookup，最终精确entries集合只含健康manifest。
- 健康lease建立后才打开预算拒绝开关；mark_used返回False，entries/uses/protection三表快照相同。关闭拒绝后触发当前cancel，仍抛InterruptedError且三表不变。
- 原未知SQLite触发器例扩展至已建立lease.mark_used，要求OperationalError传播，原事务rollback/旧entry/旧TTL/use保持；finally关闭lease再撤trigger。

没有弱化原事务/ref/并发/TTL/资源预期。当前MemoryError只认定可选预约失败，不吞原业务必需输出或native M失败；新的deep例没有把健康cache误失效。静态核查未发现其他错误。

## 3. 保持的B范围与待验

R1中完整8路径的事务顺序、root共享借用→短DB pin→外部hash/decode、写前全ref operation保护、完整写后原子index/TTL/use、旧reader不删/touch新值、重叠lease关闭及最后consumer后窄释放、expiry direct过滤、64项prune/producer触达和唯一基线schema/UOW结论保持。B1/B2修订不触及这些SQL或生命周期。

R1原文 `/home/dev/gdds-s5-logs/reviews/b-r1.md` SHA256=`2f76ae2c21472794c92dc9f97d127f6c0ac5d8acb0cc252fd23497cf897988e7`，保留未改。

执行稿 `/home/dev/gdds-s5-logs/execution/b-focused.sh` SHA256=`ee63697fd96ef5f3c9f63f75064426e20c0980457b425acd46876aaafbab2bf7`已重新校验未变。正式参数绑定本candidate、上述Rust tree和合格池节点；唯一测试角色核空闲/离线缓存并原子占用后执行五包sync/ruff/mypy、native实际强制重装/build-input及6文件backend parallel/serial，共18步骤。Rust源码未变不另跑三项Rust检查；失败保原件、首非零即停。

当前 **NATIVE/BUILD-INPUT / FIVE-PACKAGE STATIC / BACKEND FOCUSED = NOT_RUN**（本报告核收状态）。此代码GO不是B证据GO，不提前C/D/E；C仍须真实assembly接同owner lease和最后consumer窄释放，D仍须原T3/SAVEPOINT/producer接线审核。

## 4. 容器与阶段边界

Current HEAD：`e1098b2a62daaf779b758de80ffd0013b17650a2`。本B子节未改依赖/锁/部署/container harness/container-only行为，不单独触发容器重建；current container gate仍 **deferred** 至E最终候选或实际触发边界，Carried from：none。最后已验证镜像仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`来源线索，本审核未重算或新增carried。

B原审将继续核本轮必要执行原件及固定交接；完成后按Owner新规则退出，不以follow-up接下一节，也不把A/B既有报告改写成当时已按节新建。


---

原件：`/home/dev/gdds-s5-logs/reviews/b-evidence-review.md`；SHA256：`6b59ce4987b3e77e06d6466b1aeb8a725f88de138ab32dc491b69003094c166d`。

---

# P6 S5 B 独立执行证据核收

结论：**B EVIDENCE_GO，可进入 C**。B1/B2原审findings已连续关闭，17项必要产品检查实际通过；多余空serial选择的工具错误已按现DC68第1修复轮完成受影响复核。原入口exit5保留，不改称入口0。本结论不是qualified runner、Compose、真实旅程或E退出GO，不预签C/D。

## 1. 固定产品与独立性

- 实际产品候选：`e1098b2a62daaf779b758de80ffd0013b17650a2`；B base：`049ab2147ec6cc5b33b07d4f3381a96ac0926a8b`。
- vnext tree：`3a75a5be00d48895c265dcb7cbe5c3c50ba00040`；Rust tree：`c0213e18a9645c5cfbd39f310f532273a03a10cb`，与A已核产品相同，B未改Rust/锁/依赖。
- 原审核者只读detached worktree：`/home/dev/gdds-s5-review-b-e1098b2a62`，exact HEAD、detached、index/tracked/untracked clean及正确legacy链接已再次核对。
- B R1原件SHA256=`2f76ae2c21472794c92dc9f97d127f6c0ac5d8acb0cc252fd23497cf897988e7`；R2原件SHA256=`3b02b95007961da10ef276a5641ff9929c6febc4e52f57c79cb2ea796738c4c0`，位于`/home/dev/gdds-s5-logs/reviews/`，保留未改。
- 本人未实现被审产品、测试或Contract，未改被审worktree，未运行产品检查、额外诊断或重复测试，未创建子agent、push/tag；只核源码/Git/原件和摘要。测试均由唯一测试角色在06执行。

## 2. 原B运行：17项产品成功与真实工具失败

原件根：`/home/dev/gdds-s5-logs/execution/b-focused/20261109T074700Z-e1098b2a62daaf779b758de80ffd0013b17650a2`。

| 原件 | SHA256 |
| --- | --- |
| remote-evidence/session.log | `200128d0aa4aa4ed745aa4ed0ccbf5faa571e3d7d342c551b1171a436303d0d8` |
| remote-evidence/steps.tsv | `55db9dcd61c10fecc1dc060608e2107a8dcb6ebcab33c5c76cbc3e1ecff5ce35` |
| backend-focused-parallel.log | `5ebe906ed148a230a25b04ef153bae5cbe4d5827722623dd1cf2879fd21616f8` |
| backend-focused-serial.log | `d6ba406b092e3837348ed9724bc281a1942d14f4b123c21357043af5d69a8998` |
| local SHA256SUMS | `37dc1faf0d412a22c86cdba0290fc7d13b5b48f09efadb750ce723dcedbc0c55` |
| remote-evidence/SHA256SUMS | `a5ec7706bc818c6460c4d621bcfbefed7c33df1ff3ef515feb7e03799dad246c` |

本人逐项重算local清单30项、remote清单21项、清单自身及orchestrator.log.sha256，全匹配；逐行核全部18步日志SHA/HEAD/command及tee exit。remote绝对路径通过同名复制原件映射核对，没有跨节点计算闭包或伪造实时日志。

节点为`gw-dms-06.lan`，session UTC **2026-11-09 07:47:03Z–07:48:47Z**。开始/结束及每步HEAD均为e109，Rust tree精确一致。LAN源码bundle摘要`8f915cf6cdaf093afb4d36a09dc1aef8b7f9c23d773a77122dee5d0823254b88`已在输入/remote verify中绑定；执行前原子取得本人标志，核空闲/无容器/8000监听，固定clean detached WT，正确legacy。

实际使用预填本地uv/Cargo缓存，UV_OFFLINE=1、CARGO_NET_OFFLINE=true；PATH以/home/dev/.cargo/bin开头，禁设RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME的守卫保持，selector与四Rust工具同为1.97.0，uv0.11.28，TMPDIR为磁盘/home/dev/gdds-test-tmp。Cargo target/环境/日志在本人runroot和worktree外，没有占用他人缓存。

前 **17个必要步骤command/tee均0**：

- 五包locked/offline同步；backend显式强制重装gateway-compute-python并绑定当前Rust tree，日志确认实际native build成功。
- extension build-input通过，expected=installed=`c0213e18a9645c5cfbd39f310f532273a03a10cb`，原日志SHA256=`78c6fad80eddf1910d3e28dc1cf8e4e5dd0d69ffc6d1e4943a6c785333e0e2a6`。
- 五包ruff/mypy均通过；mypy分别检查shared_kernel34、repository_contracts15、repository_client26、backend539、repository_service201个source files。
- 6文件parallel focused **162 passed**。范围为computation cache、control DB schema、workspace artifact store、canonical table cache、snapshot export cache、architecture。包括25个新的真实SQLite/FS及共享envelope向量，覆盖B1预算维护不影响三表、取消/未知SQLite传播、B2深JSON目标精确失效并保健康key，以及R1已核事务/替换/TTL/lease/pin边界。没有更新业务golden。

第18步为多余serial选择：原日志仅 **162 deselected**，无测试失败/收集错误，pytest真实exit5、tee0；脚本当场exit5停止，session最终HEAD仍e109、clean、failed_run_temp_state_preserved=yes、cleanup_status=0、marker_released=yes，local orchestrator同为exit5。六文件及conftest不存在serial声明，全部162已被parallel表达式选择。故此为明确的执行范围编排错误，不能冒充产品失败，也不能把原入口改记成功。

## 3. DC68第1轮工具修复及受影响复核

先停止并保留上述原件后固定、独审两稿：

- 原`b-focused.sh`保留，SHA256=`ee63697fd96ef5f3c9f63f75064426e20c0980457b425acd46876aaafbab2bf7`。
- `b-focused-revised.sh` SHA256=`7eab82f3693647bbd9a01876b38e28984290a972ed9d87d4538e3867b1e0479e`，相对原稿只删除不必要空serial步骤。修订完整稿没有被重新运行，17项结果仍明确来自原运行。
- `b-serial-selection-fix.sh` SHA256=`12f74e0dd1fbde57ac20fe8e3495a3843f4957615ba14191804853e2cd8a5914`，仅对同旧clean WT/保留uv环境/同6文件执行原serial selector的collect-only，不执行产品测试、不重跑17步；断言真实pytest5、tee0及162deselected，保原入口5。

上述范围符合当前testing-conventions DC68：同一已明确工具根因首次失败后的第1轮有修订/适用独审/受影响复核，未无修改重跑、改产品或放宽业务断言，无需扩大矩阵或另建治理机制。

续步原件根：`/home/dev/gdds-s5-logs/execution/b-tool-fix/20261109T075706Z-e1098b2a62daaf779b758de80ffd0013b17650a2`。

| 续步原件 | SHA256 |
| --- | --- |
| remote-evidence/session.log | `295d168aed697be9928c3a908ce704a9d9d9bad92b6c5bba39ab1d11eca8e296` |
| serial-collection.log | `b526d6767e91b5c476cdebaf480a1fabf378ec7d5b51832ac8673585a75c954f` |
| local SHA256SUMS | `45592e4e0688681888dcb239a912203ae58d9dc7adc677e02e01d92edd817b99` |
| remote-evidence/SHA256SUMS | `5fdd2b3aa960e2956e82b52160b5483a1601ab48a588966a23e454d9ec5fd529` |

local清单9项、remote清单2项、remote清单自身摘要及inputs.sha256所列3个固定脚本输入逐项重算，全匹配。06 session UTC **07:57:08Z–07:57:11Z**，起止HEAD仍e109，clean；实际输出`no tests collected (162 deselected)`，pytest5/tee0保真，continuation及copy均exit0。

续步fresh BatchMode SSH与原子本人标志、前后idle检查、offline/磁盘TMPDIR/外置pycache均沿已核脚本执行；结束worktree_clean_after=yes、marker_released=yes。只有资源闲置才释放本人标志；旧环境/失败现场保留，没有删他人占用或篡改旧原件。工具根因已在第1轮闭合，不需要再跑产品步骤。

## 4. B闭合与下一节交接

代码与实际证据现已闭合B1/B2；B的引用envelope、唯一基线schema/UOW/SQLite participant、完整写后原子登记、条件discard/mark、86400秒TTL/64项prune和touch、同operation强pin及root共享借用具备本节必要证据。**可进入C，无需再次申请许可。**

以下属于后续未实施/未验证边界，不能由B预签：C须在真实Preview/History authority核验之后接入完整候选，metadata-only前置精确catalog/schema/count/commit校验，按需ensure_rows；当前pair统一出版；lease/root borrow与M资源保持到最后consumer，并在READY前及异常finally窄release_operation_pins，不清同owner workflow/source pins。D须在原MatchingFinalizeFacts之后、原control DB事务和窄SAVEPOINT内按真实Preview producer调用touch_producer，保未知SQLite/控制传播及DC94恢复屏障；本节只核了SQL participant，没有执行T3接线。无持久journal/refcount/迁移平台。

## 5. 容器、runner与角色结束

Current product HEAD：`e1098b2a62daaf779b758de80ffd0013b17650a2`。B未改依赖/锁/部署/container harness/container-only行为，不独立触发容器重建；current container gate仍 **deferred** 至E最终候选或实际触发边界，Carried from：none。最后已验证镜像仍仅历史S4 V=`6786b28a3506feab3d8eac7d1288c8b22525bb8f`来源线索，本核收未重算镜像/新增carried。

原B入口始终exit5；本报告核收的是17项已实际成功的必要检查加DC68受影响工具确认，绝非qualified runner/按包闭包沿用来源。没有Compose、真实t1、性能测量或E退出结论。Rust未变仅说明本节无需重复Rust矩阵，不宣称本节另跑Rust。

按Owner在B进行中补充的AGENTS/实施提示词角色规则，本原审已完成B finding连续复审与必要执行核收；固定交接后退出活动分工。C/D/E由协调者按阶段新建实施、独审、测试/等待角色，读本固定候选/Contract/handoff与必要原件，不继承本角色临时对话权限。
