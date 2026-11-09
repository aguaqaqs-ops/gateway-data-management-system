# Phase 6 S5 B 交接

固定产品候选：`e1098b2a62daaf779b758de80ffd0013b17650a2`，B基线为A关闭提交
`049ab2147ec6cc5b33b07d4f3381a96ac0926a8b`；Rust tree仍为
`c0213e18a9645c5cfbd39f310f532273a03a10cb`。当前 **B CODE_GO / EVIDENCE_GO，可进入C**；
原始空serial选择exit5与DC68续步exit0分别保留，不改称一次完整入口成功。

## 实现和当前边界

- `artifacts/computation_cache.py`拥有纯引用key、entry、operation owner、closeable lease和规范
  manifest envelope；Comparison/Risk owner继续解释payload，B不复制业务codec。
- control DB唯一基线增加entries/uses与两expiry索引，UOW实际初始化SQLite participant。
  root共享借用→短事务pin→事务外hash/decode；全部refs在首个put前受operation保护，完整文件
  验证后才原子登记index、全部TTL intents和uses。旧reader只按完整旧manifest版本失效或touch。
- TTL默认86400秒；成功store/mark_used从事务UTC续期，仅打开候选不续期。expiry每次最多清
  64 entries和64 uses，direct lookup独立核expiry；touch_producer每次最多64个匹配未过期
  producer/repository/current-manifest uses，未触达的派生值自然到期，不改变业务接受范围。
- lease.close释放本次borrow和decoded metadata资源；同operation共享cache pin保持。所有
  consumer/lease关闭后`release_operation_pins`只删`active-computation-cache` intent，不
  覆盖/删除原workflow pin。C须在READY前和异常finally接好此批次释放，不能让Preview READY
  长期强pin内部cache；原Lifecycle终态owner释放保持。
- 可选cache预约失败可miss/not_retained；mark_used仅在reserve callback/enter窗口把
  MemoryError转False。两个已知JSON/JCS解析窗口将RecursionError转typed坏载荷。控制与未知
  SQLite异常传播，T3的窄SAVEPOINT与MatchingFinalizeFacts实际接线仍归D。

本节没有Preview/History消费者或T3接线，不宣称生产跨operation命中；没有改业务golden、HTTP
DTO、SQL、依赖或锁。schema直接改到目标形态，旧control DB拒绝启动，无迁移/兼容路径。
新测试使用真实SQLite与文件系统，共25个参数化case；无Dolt fixture、线程或固定等待预算。

## 独审与必要实际验证

同一独立Sol原审R1对`911d1586a9`提出B1可选mark_used预约、B2深JSON解析边界两项finding；
e109修订后R2全部关闭为CODE_GO。原文和各SHA见[B审核归档](p6-s5-b-review.md)。

唯一Luna max执行者在06 clean detached固定e109运行。原稿
`/home/dev/gdds-s5-logs/execution/b-focused.sh` SHA256=
`ee63697fd96ef5f3c9f63f75064426e20c0980457b425acd46876aaafbab2bf7`，原18步骤中的前17步
command/tee均0：五包locked sync、native强制重装/build-input、五包ruff/mypy，以及backend
六目标文件parallel **162 passed**。末步serial只有162 deselected，pytest exit5/tee0，原入口
exit5已停止收尾，没有测试失败，也不把该入口改记为0。

原session为2026-11-09 **07:47:03Z–07:48:47Z**（native/runtime从07:47:04Z开始），节点
`gw-dms-06.lan`，起止HEAD=e109且clean。uv/Cargo使用本节点已预填缓存、无公网/代理，
PATH和selector/build-input沿既定规则；jobs4与生产N1/M24分列。原件目录：
`/home/dev/gdds-s5-logs/execution/b-focused/20261109T074700Z-e1098b2a62daaf779b758de80ffd0013b17650a2/`。

| 原件 | SHA256 |
| --- | --- |
| parallel 162 passed | `5ebe906ed148a230a25b04ef153bae5cbe4d5827722623dd1cf2879fd21616f8` |
| 原空serial exit5 | `d6ba406b092e3837348ed9724bc281a1942d14f4b123c21357043af5d69a8998` |
| steps.tsv | `55db9dcd61c10fecc1dc060608e2107a8dcb6ebcab33c5c76cbc3e1ecff5ce35` |
| session.log | `200128d0aa4aa4ed745aa4ed0ccbf5faa571e3d7d342c551b1171a436303d0d8` |

### DC68第1轮工具修复

原审确认六文件无serial用例，parallel已覆盖全部162项，故不重跑已通过17步。保留原稿，修稿
`b-focused-revised.sh`（SHA256=`7eab82f3693647bbd9a01876b38e28984290a972ed9d87d4538e3867b1e0479e`）
只删除不适用的空serial步骤；受影响续步`b-serial-selection-fix.sh`
（SHA256=`12f74e0dd1fbde57ac20fe8e3495a3843f4957615ba14191804853e2cd8a5914`）获原审窄核GO后，
在原节点、原clean WT与保留环境fresh原子取锁，仅运行原selector的collect-only。

续步07:57:08Z–07:57:11Z，起止HEAD=e109、clean，实际pytest5/tee0及162 deselected全部记录，
仅对该已明确空选择断言成立后续步exit0；原入口5不改，未重跑产品步骤。占用释放、无活动
进程/容器/8000 listener均已核。原失败环境仍保留，未因换路径重计故障次数。

续步原件目录：
`/home/dev/gdds-s5-logs/execution/b-tool-fix/20261109T075706Z-e1098b2a62daaf779b758de80ffd0013b17650a2/`。
session SHA256=`295d168aed697be9928c3a908ce704a9d9d9bad92b6c5bba39ab1d11eca8e296`，collection
SHA256=`b526d6767e91b5c476cdebaf480a1fabf378ec7d5b51832ac8673585a75c954f`，local完整清单
SHA256=`45592e4e0688681888dcb239a912203ae58d9dc7adc677e02e01d92edd817b99`。

同一原审核者已独核两组完整manifest、所有step原件/输入脚本SHA、clean身份和资源释放，确认
**B EVIDENCE_GO**。原文`/home/dev/gdds-s5-logs/reviews/b-evidence-review.md`
SHA256=`6b59ce4987b3e77e06d6466b1aeb8a725f88de138ab32dc491b69003094c166d`，逐字归档在
[B审核记录](p6-s5-b-review.md)；归档整体SHA256=
`933a4e6fc2c79095e350c0661b7c74ae5e7e6e4c394c8054199047f7b9b53fec`。

## 下一小节输入与未测边界

按Owner新规则，B核收后为C新建实施、独审、唯一测试角色，协调者持续。C读取当前AGENTS、
设计/kickoff、A/B交接与原文、各owning Contract及实际facade；不继承A/B子agent对话或临时权限。

C必须把真实Preview/History消费者接到本端口，成功pair后才store/mark_used，按同M预付所有
payload、mapping、restore和输出；缓存payload/lease保至实际最后消费者，不能提前close却留下
借用Arrow。Comparison session目前仅保同operation重复任务，不能把remaining_uses伪造为2来
保留首次持久候选；Risk完整事件按原cap/filter/clock/closure位置重放，组合信号当前计算。

History先完整exact-commit metadata/authority，再独立diff/export lookup，合并比较/ordered/
composite/导出的实际需求后ensure_rows。canonical schema绑定须复用原load_table owner算法；
metadata占位仍保完整table set/ordered provenance，导出schema与实际canonical reader同源。
checkpoint直接改目标载荷，恢复重新lookup并从exact commit补行，不读main、不兼容旧载荷。

B没有新增容器边界，Rust代码未改，本轮不重复A Rust检查。未运行权威runner、Compose、t1或
性能/容量测量；无qualified runner来源或carried结论。容器延期E最终候选，最后镜像仅为S4
历史交接线索，不能写成当前HEAD验证；E仍保必要全六包、适用Compose及已确认最小标准t1。
