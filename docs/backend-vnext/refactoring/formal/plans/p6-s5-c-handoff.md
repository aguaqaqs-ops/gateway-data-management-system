# Phase 6 S5 C 交接

固定产品 `fdb2a69a437f669150f9c3c2eed15f220e77f7f3`，C 基线
`c1e88ce67862d7edce2e3cb4b8d1e8b3785754a8`；vnext tree
`e2bca77c31c3faccf277fdccf890ba50e0530c16`，Rust tree 仍为
`c0213e18a9645c5cfbd39f310f532273a03a10cb`。**C CODE_GO / EVIDENCE_GO，可进入 D**；420 focused/五包静态实际通过并由原审核收。

## 产品与接口

- Preview/History 通过实际 `bootstrap/operation_worker.py` 共享 B 的 computation cache；
  独立 diff 与完整纯 Risk events 成功 pair 后才 store/mark_used。当前 records、risk、surface
  与完整 bundle 仍由本次 operation/pair 出版，不返回旧 bundle。
- Comparison 持久保留与真实 remaining uses 分离，单次真实任务也可形成持久候选。预查每表
  restore phase/seal 后才准入 miss。完整 identity/JCS 可驱逐，必要 restored backing 与轻量
  binding 保留；冷 miss 或暖命中的必要预约拒绝仅同计划重准入一次，不扩大 M 或伪造 use。
- payload/lease/预算随实际最后 Arrow consumer 释放。Preview/History assembly finally 在消费
  关闭后窄释放 `active-computation-cache`，READY 不长期强 pin 内部缓存；原 workflow/source/
  checkpoint/result 保护保持。
- History side checkpoint 直接改 v5、wrapper v2，只有完整描述。恢复重新核同 scope/exact commit
  的完整 authority/catalog；再分别 lookup diff/export，合并实际行需求，缺失才读 canonical
  或该 exact commit。materialize/assemble fresh authority 与 ensure 的已知输入失败沿原
  deterministic/retryable 分类，checkpoint 矛盾、控制与未知 DB 错误继续传播；原计算/出版
  错误保持原 runtime 边界。
- `describe_repository_ref(request)` 返回完整 metadata/ordered provenance，占位 reader=None，
  不读行。`ensure_committed_tables(table_set, repository_ref=, canonical_binding=,
  committed_tables=, requested_tables=, context=, timeout_policy=)` 在任何新行前复用原 owner
  算法核全表，按需补 reader，保完整集合、顺序、digest 与已有 reader。结果预约拒绝或返回
  取消均只关闭新增主/batch reader。通用 `materialize_repository_ref` 继续只返回实际行需求，
  不让新占位形态影响 Submit 单表 consumer 或 Preview 部分 artifact 出版。
- `canonical_source_descriptor` 为 metadata export 与 loaded reader 提供同一编码 schema。
  `lookup_snapshot_table_parquet` 可不读 canonical 行就核实际 ref/hash/footer/schema/count/
  layout/repository；root borrow 与先保护后核验沿原设施。损坏 export 以
  `discard_if_same(key, ref)` 精确失效，不删新 writer。旧 `discard_many` 已删除。

owning Comparison/Risk/Snapshot Table Access/Artifacts/Operation Lifecycle Contract 已同步。
未改 HTTP DTO、SQL、业务 golden、依赖、锁、Rust 或生产 N/M；无旧 checkpoint 兼容路径。

## 独立审核与实际验证

按 Owner 新规则，C 新建实施、独审、唯一测试三角色，未沿用 A/B 会话；协调者持续。
同一 C 原审在 clean detached WT 连续 R1–R7：C1 新 reader/batch 释放、C2 可选身份 M 回退、
C3 H1/FULL 真 producer→consumer 与风险实际 hit 判据、C4 精确输入错误分类均静态关闭。
原文与逐件 SHA 见 [C 审核归档](p6-s5-c-review.md)。证据原件
`/home/dev/gdds-s5-logs/reviews/c-evidence-review.md` SHA256=`5aee78c21953eeed134d50cd73dc074d1ebe01c88c16d77646bdab1d8e7c5fff`；
追加证据原文后的归档整体 SHA256=`a02621fc964d5b25aa5e1090fb6d9e560c9afb593580414acda25962bca54c19`。

唯一 C 测试者在 `ct107-gw-dms-06` / `gw-dms-06.lan` 固定 clean fdb2 执行：本地开始
2026-11-09 **09:33:18Z**，远端 **09:33:20Z–09:35:24Z**，runtime 09:33:21Z–09:35:23Z。
17 步 command/tee 全 0：强制 native 重装、四包其余环境同步、build-input、五包 ruff/mypy，
15 文件 focused **420 passed / 4 warnings / 31.68s**。无 serial 用例，不调用空 serial。
入口/remote/local/outer tee/copy 均 0，起止 HEAD 相同且 clean，cleanup=0、本人标记释放。

入口 `/home/dev/gdds-s5-logs/execution/c-focused.sh` SHA256=
`c4d81235b9fb82fc4181401ab16bebfa1bf9b48621ea96ffc68c138222edd79a`。
成功原件根：
`/home/dev/gdds-s5-logs/execution/c-focused/20261109T093318Z-fdb2a69a437f669150f9c3c2eed15f220e77f7f3/`。

| 原件 | SHA256 |
| --- | --- |
| session.log | `95ff94a694a790e48c6e4d255754a50b7e7803251bba5328636c82c03a4ad0ed` |
| steps.tsv | `1b99944b61473bda45164a9399ff13c5d0cf681feafdb00609f6127c48b13778` |
| focused log | `dbba5578a1e093399921f5f80f53ba77cede05b5133e783daf89e0274b0bf51b` |
| LAN source bundle | `ec128d850fed55f8349f239f60e6517a6bebd0c1009e43074ea908cd9d9c7292` |
| local SHA256SUMS | `40b21183f56cbc69ac6169893357b9ceed83e6173ab019f2632aab5073151494` |

实际覆盖包括真实 SQLite/FS 跨 operation、直接/三节点/反向/同 commit、损坏回填、必要 M
回退与最后消费者；FULL Preview 只计算其两个相邻 pair，History B→C 实际 kernel0/risk hit
无 store，未算过 A→C 首次 kernel1/risk miss+store，新 operation 再次 kernel0/risk hit
无 store。读当前 records closure、风险 target/编号和完整节点 Parquet，预期来自手算/既有
固定 golden。不是新建全量真实旅程。

节点使用本地既有获准 LAN 预填 uv/Cargo，UV_OFFLINE=1、CARGO_NET_OFFLINE=true，无公网/
代理；uv0.11.28，Rust selector 四工具1.97.0，Cargo jobs/pytest workers4。生产仍 N1、单
active、worker32GiB−reserve8GiB/M24；focused 小向量的专属预算不作为额外生产 M 授权。

## 失败原件与修订

全部原 numeric exit、日志、SHA、未跑项及失败现场保留；以下均产品 finding，不记 DC68
工具重试。各 run 同节点、固定 clean HEAD、首非零停并释放本人占用。

| 固定候选 / 06 session UTC | 首失败 / 已执行范围 | 关键失败日志 SHA256 |
| --- | --- | --- |
| `3895b879b9`；09:06:01–09:07:14 | ruff-backend1/tee0；前12步0，backend mypy/RS静态/pytest未跑 | `2d537768161d3c16193b8e125a20cbb647235584dd93eb87a0226a526c5b8349` |
| `07a1a38041`；09:11:08–09:12:31 | mypy-backend1/tee0；前13步0，RS静态/pytest未跑 | `4c6abf922484b41aec3864c3d675d7abe0b4e7f9f41c89932a2ec99d4929adbc` |
| `addc576c31`；09:15:25–09:17:24 | focused1/tee0；前16步0，410 passed/7 failed | `302146aa50a5a139b43b29b83c5ffe281239901e9b646bcebf8f35c9a06ccf04` |

失败根分别为同目录前缀下 `20261109T090559Z-3895b879b9fc6a70b7998bc00847e137dd41fbee`、
`20261109T091105Z-07a1a380412117bb5077631648ff438ab1cc305b`、
`20261109T091523Z-addc576c31bb2d42c2c12cc52c56b9e58336f46d`。

先修无用导入、重复局部名/Optional 缩窄、公有 owner import，以及按既有 INT→SourceCell
Contract 写显式 SignedIntegerScalar 独立预期，数值不变。focused 后修空 STANDARD consumer、
JCS side 顺序下同内容总单读、按需阶段的坏 wire 失败、新 key 的严格 builder、typed reader
closed 错误与共享 fixture 父节点。坏 wire 也暴露新 ensure/authority 的真实异常分类缺口；
ad8f 初修经独审发现 catch 过宽，fdb2 用最小 typed input 子类/局部边界保原计算错误分类。
`ad8f09120b` 仅审代码，未执行产品检查；未按 actual 反填业务 golden。

## D 输入与未测范围

C 证据已核收，下一步新建 D 实施、独审、唯一测试角色；C 角色只完成本节固定交接与收尾，不
跨小节复用。D 从当前 main/本交接及 owning Contract/原件接手，不继承旧对话或临时权限。

T3 participant 已有 `unit_of_work.computation_cache.touch_producer(producer_operation_id=,
repository_id=)`，按 B bounded/精确 current manifest/expiry/uses 规则。D 在原
MatchingFinalizeFacts 后从 attempt.preview_result_id 解析真实 Preview producer，仅 SQL，
原 finalize 事务内窄 SAVEPOINT；缺 cache 不阻合法 finalize，已 FINALIZED replay 不续期，
不推进 BaselineHead，不读文件/Repository/重算。保持已知 optional 错误与未知 SQLite/外层
事务/CAS 错误边界。RS/client 通用控制与 prepare checkpoint/DC94 屏障仍归 D。

C 未触发独立容器重建边界；current HEAD 镜像/Compose **deferred 到 E 最终候选**，最后
验证来源仅为历史 S4 V `6786b28a3506feab3d8eac7d1288c8b22525bb8f`，本节不重算其身份。
没有权威 runner、qualified 包来源、carried、Compose、真实 t1 或性能/容量结论。E 保持必要
全六包与适用 Compose、已确认标准 t1 最小冷查/新 operation 复查及实际 records/完整 tar。
无 push、无 S5 exit tag。
