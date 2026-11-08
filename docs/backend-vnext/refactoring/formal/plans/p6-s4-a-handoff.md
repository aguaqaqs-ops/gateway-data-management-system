# P6 S4 A：表级语义、接口与独立预期交接

2026-11-08。A base `8e144b83455d6975499d036fe045308abc6d763e`；候选提交由协调者固定。
本节只固定 B/C/D 将消费的进程内类型和预期，未接生产路由、未实现 Rust diff/SQL、未宣称性能或容量改善。Q18 未提交 report 与其他并行会话文件不属本节。

## 固定接口与后续 owner

`mutation_planning/contracts.py` 新增 `StorageTableSideV1`、`StorageTableTaskV1`、
`StorageNetCounts`、`StorageTableSummary`、`StorageTableDecision`、`StorageTableHandle`
与 `StorageTablePreparer` typing 形状。B 实现 native prepare/summary 与 Python 唯一
`choose_table_mutation`；C 实现同一 handle 的 SQL chunk render，D 接 Submit。`before=None`
与存在的空 before stream 有不同语义；after 存在时必须带 stream、schema 与匹配 DDL layout。
强制 rebuild 的 before stream 可缺，`net_counts=None`；已完成 diff 才给实际净计数。旧
`TableMutationSummary` 属通用 ChangeSet，不改其载荷或计数。

实际传入的 operation 必须是 caller 已开启的有效 `KernelExecutionContext`。因现架构 DAG
只允许 Mutation Planning 导入 Storage Projection，本节用内部 `StorageTableOperation`
Protocol 描述既有 M ledger、cancel、N、deadline、resources、checkpoint，避免新增
Mutation Planning→Table Access import。Protocol 不是新预算或初始化路径。B/C 的 FFI owner
须验证 active context 身份、未关闭、共享池已初始化及同 M/N；caller 不能凭结构相同对象
创建旁路。后续实现发现此 typing view 不足时，以最小拥有者边界修订，不放宽 import guard。

| 边界 | 固定选择与顺序 |
| --- | --- |
| storage input/key | 完整 persisted canonical IPC；manifest `canonical_key_columns`，ordered `gid/no` 只以 gid 为键，no 可更新；不读 comparison records/effective key |
| key/SQL order | key columns UTF-8，key document object JCS UTF-16，完整 JCS bytes 排序；表/SQL列 UTF-8；删除表 DROP→全部 rebuild DROP+CREATE→全部 DML；每表 DELETE→UPDATE→INSERT |
| keyless/hash | 保留重复；重建插入按 `(JCS([]), mutation row_digest)`，digest 为 Shared Kernel `encode_row` 域，不是 IPC raw、业务 content/SET sequence 或 ChangeSet identity |
| diff/policy | 多列同键更新=1，键变=2；`changed≤1000` 且 `100*changed≤max(before,after,1)`；不合格/坏绑定 effect 前失败；未读 before 不伪造净差 |
| input/memory | metadata 小而跨表；当前 after/必要 before Arrow backing 去重计费；native index/scratch/locator/chunk 是同 M 内子额度；保留 2528 MiB package envelope 覆盖 DML/DDL/包汇集；表级关闭后才打开下一表 |
| last owner | render 停止或结束→native Arrow/index/chunk 释放→streams/readers/mmap 关闭→native 子额度退还；package bytes 的 charge 留到最终消费者，不靠 GC；异常同序 |

`StorageTableOperation` typing view 已包含真实 budget 的 limit/used/available/ensure/reserve、
cancel、deadline、threads 与 resources，但不承担 runtime 认证。Native Arrow C Stream 使用
公开 safe API 且转移所有权；只有 Mutation Planning `native.py` 拥有新增 FFI，Storage
Projection schema facade 通过其已有 native owner 调同一 Rust SQL 模块，不反向导入
Mutation Planning。

## 失败映射

| core/native 事实 | backend / public 边界 |
| --- | --- |
| cancel | 现 `InterruptedError` / `KernelStopped` 分类，worker保留原 reason |
| deadline | `TimeoutError` |
| M admission | `KernelMemoryLimit`，不包成普通发布错误 |
| invalid binding/profile/duplicate key/unsupported SQL cell | effect 前稳定拒绝；Submit 经现 ImportReplay/SubmitPublication 边界；通用 facade 的 unsupported 返回 `ReplayRenderOutcome` + `TARGET_CAPABILITY_UNSUPPORTED` |
| replay总字节超过 200 MiB | Submit 稳定拒绝；通用 facade 返回 `ReplayRenderOutcome` + `RESOURCE_EXCEEDED` |
| unexpected panic | 内部失败；不发布部分 SQL、不伪装 capability failure；不增 HTTP/Repository code |

## facade 消费者迁移矩阵（C/D 负责执行）

| 现入口 | 现已核 consumer | 迁移后 |
| --- | --- | --- |
| `render_change_set_replay(closure)` | `test_dolt_renderer.py`、`test_mutation_planning.py`；`mutation_planning/import_replay.py` 间接调用 | C 改为 `render_change_set_replay(closure, *, context: KernelExecutionContext, expected_renderer_capability=None)`；原 bytes/outcome/capability digest 不变；测试显式传 fixture context；旧 Python SQL 算法在 C 删除 |
| `render_repository_import_schema_replay_sql(import_input, *, removed_tables)` | production `import_publication.py`；`test_storage_projection_import_replay.py`、`test_submit_import_builder.py`、`test_canonical_snapshot_identity.py`、待移除 import replay 测试 | C 改为显式 `context: KernelExecutionContext`；D production 传同一 operation；Schema facade 经 Storage Projection native owner 调 Rust；不产生 Projection→Mutation import |
| `mutation_planning/import_replay.py` build/plan/render wrappers | production `import_publication.py`、`test_mutation_planning_import_replay.py`、identity/builder support | D 改为表级 Submit facade，移交业务断言后删除 wrappers/专属重复测试；通用 planner/ChangeSet 仍留 |
| `tests/conftest.py::operation_kernel_context` | autouse，现 `yield None` | C 显式 yield 当前 context 给需调用两种 facade 的测试；复用既有 session pool，不引入默认预算或新全局 fixture |

显式 context 是现有 active operation 的参数，不是公开 SDK；关闭后调用与未初始化池/N 不符
必须拒绝。通用 closure 的创建/驻留由 caller 在同 M 内计费，转换 scratch 临时计费，返回
bytes 的 charge 持续到最后消费；不得无预算调用或移交到另一个 operation。

## 固定预期、来源与 SHA

新向量 `vnext/fixtures/vectors/mutation/storage-table/v1/cases.json` 为人工推导的输入与
expected：`.15g` 的 -4/15 指数界、15 位舍入与 float32 精确 binary64 扩展；key 的
JCS 数组/object 次序及非 BMP UTF-16；keyless 重复排序；净 diff 与 1000/1% 双阈；
完整 DDL 前缀；DELETE 256 行原窗口与 4 MiB byte flush 交叉。DELETE 单键 `t` 前缀 30
bytes、尾缀 3 bytes、逗号 1 byte，故 255/256 个单字节 key 分别为 542/544 bytes，
第 257 行另起 34 bytes；4 MiB 单 key token 恰为 4,194,271 bytes。第 255 行放该大
token 时，前 254 行先 flush，原窗口第 256 行仍必须独立 flush，得到 `[254,1,1,1]`。
keyless 示例中的固定 hash **仅演示已给定 digest 的排序与重复**，不声称证明真实 row hash；
B 须复用 Shared Kernel `encode_row` 向量及小型实际 keyless 表验证 hash 来源。

旧 S1a SQL/包 golden 保持未改；下列为本工作区只读 `sha256sum` 登记，不是运行测试：

| 文件（相对 `vnext/fixtures/golden/`） | SHA256 |
| --- | --- |
| `mutation/renderer/valid/destructive-delete/expected.sql` | `e2b4bc30771a85c50a89559a1856f888cae5292e49f992b629004c871a0ffe6a` |
| `mutation/renderer/valid/first-load-insert/expected.sql` | `a515fc893fb4b83f3cdab6fbad3937c2cae9b45c27d243b2d24cfc0c3de5e2c4` |
| `mutation/renderer/valid/mixed-scalars/expected.sql` | `e9e2893748a93ed995f4244b170ec0bcf2a3e0740cfdb9baa2dd783ded52de7b` |
| `mutation/renderer/valid/multi-table-patch/expected.sql` | `c84ec98f7951db3ff61b97b8b735c3fd698de96d588b9e8de6b87e95a137e483` |
| `mutation/renderer/valid/patch-single-update/expected.sql` | `c84ec98f7951db3ff61b97b8b735c3fd698de96d588b9e8de6b87e95a137e483` |
| `mutation/renderer/valid/rebuild-replace-rows/expected.sql` | `57d43d26faf3b29b626372b3adc5febecde2fd19bbced610e88200e6696f0718` |
| `storage-projection/package/valid/s5-structural-shape/manifest.json` | `39a1121ad17b613035b94ab9a48b53467a506957eead475458f00c284adc3850` |
| `snapshot-materialization/package/valid/s1-minimal-tar-gz/expected.json` | `bcfbb0a6df3c7256e186b6eb49c89c3694720c3b2c32f39616024fbeb6721586` |
| `snapshot-materialization/package/valid/s1-missing-xml-empty/expected.json` | `fdbceb9092d490b93b7160900f6d45ba57e4a24d24ef7331370220764b68c047` |

Repository Client 的版本化包 fixture 也登记作既有包字节锚点（相对 `vnext/`）：
`repository_client/tests/fixtures/versioned_v1/c1/package.tar.zst` 为
`83e6e96e643ee8ea4520aaaba65f2c31dbfaed1f798757d54dbee7303a142547`；
`repository_client/tests/fixtures/versioned_v1/c2/package.tar.zst` 为
`ecf9958a757b39ebf0b1baac4f7ad68994d076e0e3ed3abb199c304485393d1a`。
它们是 client 协议包 fixture，不是 S4 Submit 新生成包的期望字节。

既有 SQL 源为 S1a 产品 `7d0ce6220ac2541b76ab75191d43ce6113003966` 的 frozen
grammar，包 golden 属现已提交 fixture。未从新 Rust 输出生成/反填。新向量的输入形式
尚需 B/C 消费；B/C 若需复杂精确 4 MiB 旧字节捕获，先在固定旧提交测试节点捕获并独立
核算，不能用新实现 bless。

## 验证状态和后续

A 实施者未运行任何测试、编译或 lint。worktree 外执行稿：
`/home/dev/gdds-test-tmp/p6-s4-a-plan/execution.md`，仅供唯一 Luna operator 与
协调者审定；focused 含 `test_architecture.py`、Mutation Planning、Dolt renderer、
Storage Projection schema 与新向量测试，按 marker 两遍。五 Python 包 ruff/mypy 由
协调者统筹在专用节点执行。A 只触及内部 contract、向量、测试及文档，未触碰镜像/
deployment/container-only runtime；本节不触发当前 HEAD 镜像重建，最终 B/C/D/E 另判。
