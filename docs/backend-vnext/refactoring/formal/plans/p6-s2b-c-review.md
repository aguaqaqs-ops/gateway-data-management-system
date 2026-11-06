# S2b C 独立审核

状态：进行中；2026-11-06 UTC。当前仅完成前置设计与真实消费者核对，未给 C GO。

审核者为本节新建的 GPT-6.1-Sol/max，依据 DC86 与 C kickoff；不派生额外角色，不修改产品或测试。前置读取实际 `AGENTS.md`、testing conventions、C/总 kickoff、Arrow mapping、capacity census、DC42/DC67–70/DC76–86、Canonical Storage `3.7.0` §5、Snapshot Table Access/Materialization、ADR 0012 及 proportional-assurance policy。A/S2a 不重审；B 前置为产品 `b820321c1eef78be4430c9a3f5b51d22188f4e0b`、handoff `ac59ffeb79`、独立交付审核 `0dc93c09a9`，不把设计提交 `36ede9394b` 当产品证据。

前置只读 detached worktree：`/home/dev/gdds-test-tmp/s2b-c-review`，固定起点 `e12bf41ece777f275ec9286db7081365bf7b5828`；按仓库要求链接本地 `legacy/`。最终产品候选、证据与结论待实施者交付后固定。测试由实施者在 06 持有真实原子占用执行，审核者不并跑。

## 实际接线与切片边界

前置源码确认 `application/preview_jobs.py::_materialize_uploaded_side` 仍由 `project_canonical_table_set` 产出 Python projection，再调用 `materialize_projected_snapshot` → `publish_ready_tables` 发布 Parquet。B 的三个 Arrow native entry 尚无生产 application caller；现有 native 测试真实消费 Rust parser → B → A，并不等于生产路由已迁移。

按总 kickoff 的 worker/operation caller 顺序，C 可以交付唯一 A codec + B kernel 的真实 store/handle 组件闭环、实际 UoW/protection/BaselineHead 事务 hook 与受约束恢复能力；完整 Preview/History/Submit IPC 路由留给 D。主协调已在 `c25ea4724e` 将此源码澄清写入 C kickoff §1/§5，保留 C 的 storage/ref/recovery 验收。C 不因此新增 Python 逐行 writer，也不把 seeded 组件测试称为 production end-to-end；若具体恢复 consumer 必须扩大迁移范围，先列出 caller 与 owning Contract 交主协调裁定。

保留的真实消费者包括 raw `SnapshotTableArtifact`/Parquet、client surface/export Parquet、`ArtifactStorePort.locate`、repository-ref 的 `READERS_REQUIRED` 与 `ARTIFACTS_REQUIRED`、import replay。仅在其真实 caller 切换后删除被替代算法。

## 一次性比例化核对矩阵

| 对象/风险 | 最小控制与真实后果 | 权威验证 owner/语义屏障 | 本节证据边界 |
| --- | --- | --- | --- |
| canonical store/handle；C，外部 path/root 为 A 边界 | scope 内五项内容身份；raw SHA 与业务 digest 分开；同 mapping 分块核 size/SHA；固定 profile/metadata/descriptor；真实 FS temp/fsync/rename；独立 open、幂等 close、closed-read 失败，实际借用先于 mapping 释放 | 既有 artifact storage + snapshot artifact owner，补一个 canonical store Contract owner；流失败无可发布 ref、普通 I/O、root/symlink、外层列名重排 | 不复制 IPC writer；Rust 无 path IO/unsafe；不建外来 IPC 业务导入框架或同 euid 对抗 broker |
| Preview/Attempt/TTL；B，protected 删除为 A 后果 | 复用 `sqlite_protection` 与已有 bounded cache 模式；T1 同事务转 owner；共享 strong；最后 strong 释放与 TTL touch 同事务；expired lookup 拒绝；先保护后查文件 | `test_preview_job_materialize`/Submit T1 owner + SQLite protection/cache owner，各不变量只一处权威断言 | 不新增 durable evidence 状态机；单一基线 schema，无迁移/双读 |
| BaselineHead/归档；A | initial/current-head exact-commit 归属正确；`StartArchive.save_archived_node_and_cas_head` 与 refs/result 同事务；失败无前缀，合法 replay 不重复改变引用 | 既有 baseline/Archive SQLite transaction owner；stale CAS、失败 rollback、重放；无长 IO/物化/import；cache miss 不重算业务 | Submit finalize 只释放 Attempt，不移动业务 Head |
| 冻结与已提交恢复；B，main/冻结污染为 A 后果 | T1 前 rePreview；T1 后 PREPARED 前缺损 stable fail，不换 source/parent/ruleset、不前移 main；PREPARED 复用冻结包；committed 从绑定 exact commit 核 digest 回填 | 既有 snapshot artifact faults、`test_submit_import_builder`、`test_submit_job_prepare`；generic lease/CAS/recovery 不另建框架 | 明确 C 组件能力与 D 实际生产 IPC caller 接线；不能靠 mock 换源自证 |
| FULL/资源；C，越界为 boundary 后果 | 同活跃期分列输入/parser、两侧输出、sort/filter、writer/adapter copy、opened mmap 与 staging；区分 reservation/RSS/page cache/disk；同 mapping 一次，未打开历史不计 RAM | 真实 B/A/store 有界校准 + 既有大表分布，附输入/commit/节点/口径；D 再验 actual worker cancel/drain/EOF | 小 fixture/SQL size/06 32 GiB 不证明 production M；生产 envelope 未确认时停止依赖它的 D 步骤 |
| 执行/镜像；证据前置 | 06 原子 busy、clean 固定 SHA、legacy、offline、Rust selector/PATH、强制扩展 reinstall+checker、日志外置；固定 named-ref bundle，actual remote previous，sync rc0 独立确认 | 实施者日志/脚本与审核者只读核证；必要静态/当前容器 runtime，按实际改动面收敛 | 06 不冒充 04 runner/carried 或 CT108 正式性能；A/B 保留工件不改；W1/W2/t1–t4 仍按最终 S2b 时点 |

## 前置缺口与后续 gate

容量 census 只证明固定 t1 parser buffers 和两行 fixture；没有生产 FULL/M、worker envelope/reserve 结论。C 必须补真实 kernel/codec/store 双侧活跃期校准与可解释候选；缺部署输入时明确逐项上报，不能虚假 GO 到依赖它的 D wiring。

当前起点 `e12bf41ece` 仅文档较 B 增量，无新增 container boundary；本报告本身不触发镜像重建。最后已验证 image revision 为 B 产品 `b820321c1e`，身份和日志见 B handoff；此处仅作历史前置，不声明当前 C 候选 passed/carried。C 最终候选 image 决定、固定 SHA、handoff/容量报告、实际证据及 busy 释放待复核。
