# S2b C 独立审核

结论：**C GO，无未关闭技术 blocking Finding**。日期：2026-11-06 UTC。固定产品为 `0048040af59214bf1113c820396ac4b306befe31`；最终 [handoff](p6-s2b-c-handoff.md) 与 [容量报告](p6-s2b-c-capacity-calibration.md) 为 `7cd2b548c87fe0c07390078104714cb4055d5b5a`（首次交接 `8b122480c0`，最后仅同步 Owner 已选 A）。本结论覆盖 C 组件、实际事务 hook、受约束恢复及容量交付；S2b 整体尚未退出，D 的生产路由/worker 验收仍须完成。

Owner 已选择 A，配置前置由 DC87（`3f421a846e`）闭合：worker envelope **12 GiB**、工程 reserve **4 GiB**、显式初始及上限 **M=8 GiB（8,589,934,592 B）**、**N=1/单 active operation**。M 缺失仍拒启。选择不等于已通过 production worker capacity；D 落实该配置并验证实际峰值、增长前拒绝和资源失败不发布。B 是未选备选。

## 审核对象与边界

审核者为本节新建 GPT-6.1-Sol/max；没有派生额外角色、修改产品/测试或运行测试。读取实际 main 的 AGENTS、testing conventions、C/总 kickoff、mapping/census、DC42/DC67–70/DC76–86、Canonical Storage 3.7 §5、Snapshot Table Access/Materialization、ADR 0012 与 proportional-assurance/Rust policy。B 前置为产品 `b820321c1eef78be4430c9a3f5b51d22188f4e0b`、handoff `ac59ffeb79`、独立审核 `0dc93c09a9`。设计提交 `36ede9394b` 只作批准目标，不作实现证据。

新只读 detached worktree 为 `/home/dev/gdds-test-tmp/s2b-c-review`，初始固定 `e12bf41ece`，逐次固定小步，最终固定产品 004；legacy 链接齐全，保持 clean。完整核对 B..004 的 C 产品/测试 diff，主工作区只维护本报告。

前置核到生产 Preview 仍是 `project_canonical_table_set → materialize_projected_snapshot → publish_ready_tables(Parquet)`。主协调在 `c25ea4724e` 明确 C 真实 B/A/store、UoW/Archive/终态释放与恢复能力，完整 operation caller 切换归 D。本审核按此边界，保留 raw/client Parquet、通用 locate、repository-ref 两种 policy、import replay/export 的真实消费者；不把组件测试称为生产 Preview/Submit IPC 端到端。

## 比例化矩阵与实际结论

| 对象/风险 | 最小控制与主要测试 owner | 独立核对结论 |
| --- | --- | --- |
| store/handle：derived C；root/path 为 A 边界 | `test_canonical_table_store`，原 staging/FS owner；A 原 profile/value 向量不复制 | scope 内五项 identity，business schema 含 table name；raw SHA 不代替业务 digest。唯一 Rust writer；同 mapping 分块核 size/SHA，借用 safe LargeBinary C Stream 复用 A preflight，再标准 reader；外层列名重排、独立 open、幂等 close/closed-read、真实 B 借用与 symlink/预算拒绝成立。 |
| Preview/Attempt/TTL：B；protected 删除为 A 后果 | `test_canonical_table_cache`、既有 `test_submit_transactions` | 复用 protection/UoW；T1 实际 owner 先加 Attempt 再清 Preview。共享 strong、最后释放与 TTL touch 同事务，expired lookup 拒绝；实际复用先 writable lookup/touch 再查文件。唯一 baseline 加两表/两标准索引，无 migration/双读/evidence 状态机。 |
| BaselineHead/Archive：A | 原 `test_archive_transactions`、baseline/cache owner | initial/current head 按 exact commit 归属；正式引用在实际 `save_archived_node_and_cas_head` 内切换，与 Archive CAS/result 原子提交，late failure 回滚、合法 replay 不重复修改。事务无文件读取/物化/import；Submit finalize 只释放 Attempt，不推进 Head。 |
| 冻结/恢复：B，main/冻结污染为 A 后果 | 新 `test_canonical_commit_access`；原 Submit prepare/import/recovery/worker owner | 健康 hit 免写；真实 client/session + HTTP transport/wire fixture 经 catalog pin/scope/schema/count、B digest、A/store 回填。窄整数/SET/civil DATETIME 的标准列式适配成立。错 commit/digest、network/budget 失败无 temp/ref；frozen 直接 open，无 committed-source fallback。既有 T1/PREPARED 语义屏障仍在原 owner，D 再验实际生产 IPC 接线。 |
| FULL/资源：C，越界为 boundary 后果 | 实际有限组件校准；B 既有预算 owner 一个回归 | t1/t4 双侧、输入/parser/canonical/filter/facts、unique mmap 实测；另补真实 XML/AST/composite。实测/推导/未知分列，未把 SQL bytes、06 RAM、局部 4 GiB 或小 fixture 当生产 M。D aggregate 预约及 worker 复核未被豁免。 |

ADR 0012 的协作并发、crash、普通 I/O、protected 与 root/symlink 边界保留；没有新增同 euid 敌手 broker、helper、自定义 IPC 安全协议或持久发布证明。普通 metadata/row-count/借用释放、expiry/FK 索引及 HTTP 错误归一问题均已在固定实现收口。

## 容量及真实问题闭环

t4 两侧各 311 个 SQL canonical 表，v2 284 个内容命中；parser buffers 195,208,942 B、canonical buffers 117,516,276 B、unique active mapping 85,457,516 B，最大单表 IPC 21,363,522 B。其 `ru_maxrss` 为 821,837,824 B；原始 `/proc` 窗口最大 VmHWM 830,758,912 B 另列，不强行合一。node cgroup 约 30.5 GB 既有 filecache 不作 worker RSS/M。

首次 t4 的局部 4 GiB 拒绝是真实失败。静态核到 keyed projection 把全行临时 `scratch*2` 跨行累计为 retained；实际 prepared 只保留 key frames/hash/Row。按 root 授权改为既有 SQL 分支的 keys-only 上界，整行临时 ensure、row/hash/sort/output/adapter 预算和 4 GiB cap 均保留。200×100/16 MiB 的有界回归以 frozen 业务 oracle 验证，随后经审核 GO 只做一次同 pair/同预算复验，成功。

审核者独立只读比较原/新 SQLite 插入序列：原 232 个 ID 恰等新 338 个 ID 前缀；新 JSON 未 hit 输出同为 338 项。下一项为 v1 匿名 index 233，54,150×43、buffers 21,087,590 B；原全行累计下界 7,152,998,400 B 已超过 4 GiB。该旧表定位是发布前缀/新确定性序列的**推断**；旧失败 RSS 仍 unknown，不回填。

XML 补项每侧 890,874 B、22,286 events、431 formulas、435 derived rows，AST JSON 409,338 B、point payload JSON 314,185 B；真实调用原 owner，未重跑 FULL/projection/IPC/store。补项 `ru_maxrss=669,552,640 B`。两进程相加 1,491,390,464 B 仅为含重复 runtime/parser/input 的工程估算，非实测同峰/严格上界；311 SQL 表不包含补项 derived composite IPC。

source、SQL/package SHA、全部计数与日志见容量报告。writer/adapter 复制、sort/filter 预约与最大 atomic staging 是代码/文件长度推导；HTTP 大样本 spool、完整 operation、N 变化和实际 worker 差异由 D 关闭。借用只加未在 retained/parser/mapping 计过的部分，同 mapping 的 views 一次计数；不把全部历史文件当 RAM。原输入 quota 不代表必须无条件同时全部接受，资源额度不足在增长前拒绝，不依赖 OOM 作正常拒绝。

## 实际验证与采信范围

前缀均为 06 `/home/dev/gdds-test-tmp/logs/`。审核者读取实际脚本、完整关键日志/结果和外部 SHA；没有并跑测试。

| 来源 | 实际结果与范围 | 日志 / 外部 SHA256 |
| --- | --- | --- |
| cff `cff2f20b62ec63879ddb37b956808c0fa786a751`，14:12:26–14:13:43Z | 完整 Rust fmt/all-target clippy/workspace tests/release/architecture CLI、force extension/tree、五 Python 包 Ruff/mypy、两校准工具静态，exit0 | `s2b-c-final-static-cff2f20b62.log` / `9df26b9d60636f6796e07e401df9f7f3915699efaec237e2e939b6d1f7601181` |
| cff，14:14:24–14:14:59Z | 327 focused 中 325 PASS、2 schema target 清单失败；**整体 exit1**，不是合格整包/runner 来源。通过 owner 按实际未改范围有限采信 | `s2b-c-final-focused-cff2f20b62.log` / `04bea68a9e00ea295fa0aad615d8145d5acd47ebda1c42297161c3b7c88ca340` |
| 004，14:20:20–14:20:24Z | 两表/两索引目标期望四行补齐、窄 HTTP 网络分类后，五包 Ruff/mypy、tree、schema/HTTP owner 17 PASS，exit0。没有重跑未受影响的 325 或容量 | `s2b-c-final-targeted-0048040af5.log` / `c3c740d7313d60fe4c09230f1ae0ba039a9022df3b016888a5bf9d6ec63927eb` |
| 004，14:23:33–14:24:54Z | 当前离线 image health 1 PASS、worker build、同 health image B/A/protected-store/双 mmap/B borrow/last TTL smoke，exit0 | `s2b-c-container-0048040af5.log` / `fd50960429337f6c72aebf79bd476cdb8b6a35b3cf1522a0320be82d454b997f` |

004 与 cff 的 Rust tree 同为 `d7bbe223f17a155b01ec8b948a7c4fbe51628d05`，host extension installed/expected 实际一致。cff 后只有对应 schema 期望和上述 HTTP 窄修改；其受影响 owner 在 004 重验。实际 Python architecture、Archive 并发、Submit T1/PREPARED/真实 Dolt recovery、原 FS/staging/Parquet/cache fault owners 均在所列影响面内。

前置小步 6193 store 6、3e4c refs 92、309c HTTP 12、3ae2 预算/borrow 50 的日志与容量 JSON 已逐项核对。所有已知失败及外部 SHA 保存在 handoff/容量报告；1059 初次 EXIT 曾写 self-sha，最终外部 SHA 为 `2d36fc060fc6c4c0cc7af8cb24307acfffd9bd2ebf0adb00471371839436f82d`，早报的 `3f89…` 不作最终摘要。没有把失败日志、旧 HEAD 或旧 image 改称当前全过，也没有正式 package carried。

## 架构规则与 D 移交

实际 gate 暴露的 core test runtime fixture IO 已改为同五份输入/期待的 compile-time bytes，后段 case 标签保留。正式 Rust policy v4（`f690e22aef`，`2c35b6e647` 澄清）表达既已批准的 capability 直接 native 调用：三个精确 source、exact `gateway_compute._native`、五个显式非空入口名称；whole-module/wildcard/wrong owner/target/function/mixed 拒绝用例通过。既有 composition/bootstrap 规则保留；IMPORT/CYCLE baseline 未增加例外。

按 C kickoff 已批准的切片边界，temporary unreachable 只增加这五项，D 接实际 consumer 后逐项删除，不能留到 S2b exit：

- `application.canonical_metadata.table_access`：Preview/History exact-commit reader/backfill。
- `capabilities.snapshot_materialization.canonical_store`：生产 IPC writer/handle、Preview/History/Submit 绑定。
- `capabilities.snapshot_materialization.native`：上传 SQL facts 与 filtered catalog/composite。
- `capabilities.snapshot_materialization.repository_arrow`：Repository wire 列式适配。
- `capabilities.storage_projection.native`：上传/committed projection。

D 按 Owner 已选 A 接 startup N/M 与实际 operation 预约、完整 caller、EOF/publish/control/cancel/drain/lease_lost/finite deadline、FULL/共享借用/单表拒绝，并验证部署声明/limit。M+reserve 不得超过约定且实际配置的 envelope；不因较大 host limit 建新 cgroup 框架。E 才完成最后单路径与旧算法清理。04 最终 runner/container、t1–t4 正确性及 W1/W2 的 DC83/DC84 时点保持，C 不替代。

## 节点、镜像和收尾

C sync 两脚本的完整结构及实际 named-ref bundle/advertised ref/SHA/fetch、actual remote previous、独立 exit0/clean 检查均核对；未依赖共享 main 的 HEAD~1。测试都由实施者在 06 clean/committed worktree 执行，原子 busy owner 在首次测试前已独立读取，开始 13:15:33Z；原获取工具输出无外置日志的限制如实记录，没有倒填。

离线 UV/Cargo、本机预填缓存、PATH/unset、外置 TMPDIR/target/log、强制扩展重装均核实。closeout 与审核者只读版本查询确认 rustc/cargo 1.97.0、rustfmt 1.9.0、clippy 0.1.97 解析到同一 1.97 toolchain。五 uv locks、Cargo.lock/selector 与 B 一致；没有 CT201 测试/编译/lint、代理、新预填传输或其他节点测试。

本轮 PyO3/Arrow/store runtime 触发必要当前 image 验证，已在 004 重建/执行；没有沿用 B image。dependency input `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，预填 base config `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 与全部 19 DiffID 匹配。完整列表位于 `artifacts/s2b-c-0048040af5/base-identity.txt`，SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`。preloaded=1、build network=none、非 COMPOSE_GATE_PREBUILT。

当前本机 image IDs：backend `sha256:043b88bec8b74205d3f3a5b3b4fc4790fca680567752363d741f7cde8a1d586a`（与 health/native smoke 相同）；worker `sha256:58d2649cd7c379aac3ab36f02c0d2f5978ae90186caa9d6bc5f9790a5709006d`；RS `sha256:f4b4197ef64e2c8e9c219be3f1ce5d778d16cfa105194be82e6d102b47aabfa7`。RS 当前 owning build revision/source-tree 与 label 相符。compose provenance SHA `9d5a09a700de04fbb9657d24347310eba078ad8c8da859f278a8f2de4e59e672`。容器不宣称用非空 build_input 字段通过 host checker；证据是固定 source 实际构建/同 image ID 执行。当前产品 004 的必要 C container gate 通过；本报告纯文档提交不触发再构建，不宣称正式 carried。

14:30:50Z 已释放自己的 busy，closeout exit0/SHA `00f62e93669cadb87dea729b42accd567408eea444e97ecaeef3a150cdbc7f1b`；原 owner 归档 SHA `77d22f97170f51f37128f9fbb8767176dc9b0b820cb59029f5f2fb02e81b09ea` 与先前读取一致。审核者再次只读确认 busy 不存在、06 worktree clean 004、无运行容器/Dolt。C/A/B worktree、证据、images 与 caches 保留，原 CT108/04/05/07 资源未用于本节。
