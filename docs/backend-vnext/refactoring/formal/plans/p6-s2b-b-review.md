# P6 S2b B 独立审核

状态：**正式任务单已核对，产品与验证待审**。2026-11-06。本报告不预写 B PASS，不把 A 的结果作为 B 验证。

审核基线为 `10bf4b26e907bcd6ebe2e6b872b5d2bfd504199f`，只读 detached worktree 为 `/home/dev/gdds-test-tmp/s2b-b-review`，已建立 `legacy` 符号链接。开发主机只读源码与文档，未运行测试、编译或 lint；本报告在主工作区单独编辑。未操作 CT108 冻结资源，未创建额外 agent。

依据：[已批准 kickoff](p6-s2b-kickoff.md)、[Arrow mapping](p6-s2b-arrow-mapping-design.md)、[A handoff](p6-s2b-a-handoff.md)、[A 独立审核](p6-s2b-a-review.md)、[Canonical Storage Contract](../contracts/canonical-storage-and-repository-boundary.md)、[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)、[Snapshot Materialization](../../../capabilities/snapshot-materialization.md) 与 [Composite Signal](../../../capabilities/composite-signal-device.md)。B–E 推进授权由本会话 Owner 与主协调记录；旧 kickoff 中历史的“仅 A”文字不被本审核解读为撤销后续授权。

## 1. 范围与现有架构

B 承接 SQL 标量业务物化、完整诊断、特殊 device/point 提取，以及 canonical projection/hash；末端复用 A codec。Python 的 XML、公式 AST/binding 与 composite orchestration 保留。B 不接 C 的 store/mmap/ref/recovery、不接 D 的 worker N/M/startup、不提前执行 E 的生产 callers 切换与旧实现删除。

已直接核对 `gateway-architecture-check/src/lib.rs` 的 dependency 与 source-pattern guard：adapter 不得直接依赖或 import Shared Kernel；core 不得依赖 PyO3、adapter、artifact-store 或网络库。复用 A 的 core declared-type setter；不以 re-export 或放宽 guard 绕过边界。Arrow 批量数据走安全 C Stream，adapter 只提取有界 metadata，不把 Python bulk rows object graph 作为正式 FFI。

最小边界建议是按既有 owner 分开 SQL table facts、catalog filter facts、canonical table projection 三个窄操作，内部可复用同一 Arrow table representation。输入为 Arrow batches、已有 column descriptors、小型已解析 rule view、阶段与明确的 source/canonicalized-input 区别；输出为 Arrow batches、规范描述、行数、业务摘要与 typed diagnostics。Python 继续拥有规则解析和小型汇总 metadata。Catalog 另传原 device 行数/是否非空、精确匹配数与已过滤 point rows；这部分是既有 composite 例外，不是一般表的 Python 行物化入口。

现有 Python 源码给出两个必须保留的分层：

- SQL materialization 的重复有效键是 `DUPLICATE_EFFECTIVE_KEY` warning，全部行保留；canonical keyed projection 的重复键是 blocker。不能提前合并两层。
- A 的物理映射词汇比现有 storage projection 业务词汇更宽。`test_json_remains_fail_closed_without_dc12_evidence` 与 scalar vocabulary 参数表明确拒绝 JSON、DECIMAL、BLOB、BIGINT UNSIGNED 等投影类型；A 可表示它们不自动授权 B 接受它们。

## 2. 已核对的具体设计细节

Mapping §4 的“keyed 按既有规范键排序”需要明确 comparator 与键列顺序。当前 `project.py` 的 keyed/keyless canonical source reader 保留 source order；ordered reader 按数值 gid 排序。`import_replay._key_bytes_for_ordering` 是 replay 输出使用的 tag 加文本拼接，数字按文本排，复合字符串没有长度 framing，不应直接作为新 IPC canonical ordering 定义。

主设计随后明确采用：严格按 `StorageRuleView.canonical_key_columns` 顺序形成 canonical cell-frame tuple，逐项按无符号 bytes 词典序比较，禁止未分帧文本拼接；不承诺业务数值或展示顺序。重复/空键先按原 Contract 拒绝。Ordered 仍用 numeric gid，keyless 仍用 raw row hash 并保留重复。不为假设性 SHA 碰撞新增机制或矩阵。独立排序向量应能区分 `2`/`10`、负数和复合文本边界。

审核者核对认为该明确化没有改变业务摘要或真实 consumer 的权威顺序：raw-content 按无序 rowhash 聚合；business schema 的 primary-key 顺序仍保留；ordered 业务读取仍显式 no；Repository replay 保持自己的输出顺序。主设计已在 `4b75cf159f` 同步 mapping、Contract 与 [B 任务单](p6-s2b-b-kickoff.md)，审核者在同一 detached worktree 核对了固定差异。此结论是设计审查，不代表代码已实现。

Catalog 必须显式保留过滤前的非空事实：现有 `_require_special_device` 用 `catalog.devices` 是否为空判断原 device 表是否为空。如果只把匹配行交给旧 binder，非空但零命中会被误判为空。正式任务单固定必填 `source_device_row_count`，旧 extractor、empty factory 与测试构造方同步填写；binder 按 count 判断原表为空，身份判定仍位于原 XML/AST 之后，不造 sentinel、不设兼容默认值，业务 version/digest 不变。

实施者独立核对上述边界一致，并确认当前生产 SQL parser 仍是 Python，Rust parser 由测试 support 作差分入口。B 可用真实 Rust parser C Stream 验证新 kernel；无需为证明 B 而提前切换生产 callers，正式连通和旧算法删除留 E。`4b75cf159f` 正式任务单及 owning 改动与前置清单一致，无未解决设计冲突；产品结论保持未审。审核继续跟随同一实施者的固定代码与实际证据，不另建角色。

## 3. 一次性验收清单

以下是业务屏障，不要求每层复制同一矩阵。Rust 单元向量是新 kernel owner，backend 只保留必要的真实 adapter/既有 owner 差分；旧实现迁移完后删除临时差分入口。

| 主题 | 应保持的行为与独立依据 |
| --- | --- |
| SQL facts | 既有 `s2-minimal-create-insert`、`s2-duplicate-rows`、`s2-keyless`、`s2-null-and-types`、`s2-unknown-type-mixed` golden；重复 warning 与 keyless degraded；PROVISIONAL 无 raw digest；表级 partial 与 whole failure 分开；所有名为 gid 的源列保留 reserved pseudo 检查，包括可解析的字符串 gid。 |
| Device | 过滤前校验全部行 gid/dev_addr/description 类型与非 NULL；合法空 description 不拒绝。空表、非空零命中、一命中、多命中分别处理；坏普通行不能被过滤隐藏。 |
| Point | 必需 gid/name/dev_addr 三列先校验存在；所有 dev_addr 先校验类型，现有 NULL addr 正常跳过；只对命中行检查 gid/name 值。failed device/point tables 仍使 catalog unavailable。 |
| Composite | Python exact/case-sensitive/no-trim binding、重复点名/孤儿公式、空 derived table 与固定 canonical golden 不变。Payload 保留 IJSON 整数边界、大整数文本、float bits、binary hex、SET list 与时间文本；只有过滤结果经过 Python 例外。 |
| Diagnostic | 所有表/列 schema failures 按现有 owner 汇总，projection 的 1024 上限及 omitted count 一致；cancel/timeout 优先，失败不返回可当成功的部分 projection/manifest。 |
| Keyed/keyless | key 必须存在且 retained，NULL/空/重复稳定 blocker，无 dedup/last-write-wins。keyless 重复、空表和零列非零行保留；BROWSE_ONLY/SNAPSHOT_ONLY 的 DDL fallback 与 SKIP 语义一致。 |
| Ordered | no 正、唯一、连续 1..N；真实 gid 唯一且在 real range；0/NULL/空按 no 分配连续 pseudo。source pseudo 拒绝；canonicalized_input 只接受满足原分配规则的 pseudo。物理 gid 布局与业务 no 顺序各守其 owner。 |
| Canonical values/hash | dropped 列变值不改 canonical digest，保留/结构列变值应改变；unsigned coercion、负零归正、SET 声明序 sequence framing 与 IPC 逗号文本分开；NULL、空 SET、ENUM 空标签不混。 |
| Schema/摘要域 | business schema digest 包含 table_name 且列序无关；manifest schema digest 保留 DDL/PK 顺序；compare-schema、raw-content、raw-state、snapshot、manifest 与 raw IPC SHA 各自保持原 preimage。不能从 Arrow 物理类型推导业务 schema。 |
| Determinism | 冻结 comparator 后验证 N/chunk/行置换/DDL 列序置换的规范值、摘要、IPC bytes；不重复 A 全格式矩阵。独立 oracle 来自现存 vectors/goldens，不从 Rust actual 反向生成。 |
| Resource/control | metadata/batches/rows/input buffers 有界；sort/hash/filter/规范数组/IPC 和 adapter 复制的同时驻留纳入局部预算；增长前 checked 计算，运行中取消与 deadline，无成功部分结果。这不等同 worker M 或 RSS。 |
| Adapter | 真实 C Stream 与标准 reader 的最小往返，释放 GIL 后能取消，复用已有 pool/panic boundary；无 direct SharedKernel，guard 不改。 |

独立预期复用 `vnext/fixtures/vectors/repository/sql-enum-set/v1/values.jsonl`、Shared Kernel canonical vectors、`vnext/fixtures/golden/storage-projection/composite-signal/canonical.json` 和 SQL Snapshot goldens。SET 行 framing 不误用只能接受 scalar 的 Shared Kernel `encode_row`；业务 owner 复用 scalar/collection/ULEB/digest primitives，保持既有 SET sequence 直接进入 row 的 Contract。

对照的既有测试 owner 为 `test_snapshot_materialization_sql.py`、`test_snapshot_materialization_business.py`、`test_composite_signal_contracts.py`、`test_composite_signal_bind.py`、`test_storage_projection_core.py`、`test_storage_projection_integrity.py`、`test_storage_projection_contracts.py`。Repository-ref、export、import replay、Preview FULL/INITIAL/MODIFIED 与恢复的生产接线仍在后续切片；它们不能因 B 没有直接调用而从最终迁移清单消失。

## 4. 验证与容器状态

当前审核 HEAD：`10bf4b26e907bcd6ebe2e6b872b5d2bfd504199f`。本轮只有前置只读审核，无 B 产品变更，当前不触发重建；B 最终候选依任务单在 06 完成适用 Rust fmt/clippy/workspace/release、五 Python 包 Ruff/mypy、强制安装扩展并校验 Rust tree、focused 与必要当前 image native/health。由实施者统一执行，审核者独立读取日志、SHA、起止 HEAD 与镜像身份。

最后已验证 image revision 是 A 的 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`：06 backend image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`，对应 Rust source tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`；准确 evidence 来源见 A 审核 §7。它不作为 B 通过、carried 或当前新增产品验证。A 最终依赖 base 为 d054，994c 仅是中间产物；B 是否复用取决于最终完整 input 与目标身份。

B 当前 gate：**未运行**；carried：无。S2b 最终 04 全量 runner/container 与 t1–t4 正确性不被 B focused 取代。W1/W2、真实 FULL 峰值与生产 M 未知保持 unknown，不记录性能通过。

## 5. API 草案审核（待固定代码核实）

实施者提出三个 core 操作及薄 C Stream adapter。独立审核与主设计对齐以下具体修正，均已由实施者接受；这里不将草案认可写成产品验证：

- SQL plan 明示 materialization stage，PROVISIONAL 的 `raw_content_digest` 为 None；SQL compare key 不与 canonical key 混名。
- 业务诊断 outcome 与外层 resource/cancel/deadline failure 分开；fatal diagnostics 不携可成功发布的 Arrow 输出。Core 仍核真实 Arrow descriptor/schema/行数/必要键绑定，Python 提供的 bounded schema diagnostics 不是合法性证明。
- 诊断数量固定 1024 加 omitted count，不能通过可调小数量预算产生与既有 `ProjectionResult` 相冲突的截断结果；诊断 bytes 超限返回 Resource。
- `max_input_bytes` 计借用 Arrow，`max_live_bytes` 计 adapter/core 自有同时驻留；`max_output_bytes` 计返回 Arrow/facts 总 buffer 保留量，共享输入数组仍计入输出上限。A IPC budgets 独立，局部 cap 不冒充 M/RSS。
- Shared Kernel 的 unordered content helper 会复制/排序 hash 数组并建立 count+hash frame，semantic digest 又建立 domain+payload preimage；调用前须保守预约这些与 B 索引/输出的重叠，不要求重写 Shared Kernel 或增加 allocation registry。

## 6. 首批 API 与 Catalog 固定代码

`633e599cbce776c9db27d5bbce241707f45d9dbf` 已在 detached worktree 核对。`SpecialDeviceCatalog.source_device_row_count` 必填且严格为非负 int（bool 不接受），devices 长度不能超过源计数；旧 extractor 对实际读出的全部 devices 计数，empty factory 显式为 0，tests helper 与两个 `type(catalog)` 构造方同步填写。binder 仅将空表条件改为源 count 为 0，其余身份验证仍在原调用时点。过滤后非空零命中的定向测试断言原身份错误。该小步未改业务 version/digest，未发现 catalog 代码问题；运行结果尚待核。

Rust 新 API 有显式 stage、固定 1024 diagnostics cap、borrowed/live/returned-buffer 预算和控制，当前只是公共类型与初始 preflight。未新增 Cargo dependency 或修改 architecture guard。实际 SQL/hash/catalog/projection 操作、完整 Arrow name/type/重复绑定、adapter metadata 复制前预算及最终结果聚合尚未实现，本报告不提前认可这些功能。

首批审核发现 `TableDescriptor` 不含行数，而 projection plan 未携绑定行数，后续会漏旧 `_require_row_count` 的 `ROW_INTEGRITY` 屏障。实施者已在 `9225f78883` 加必填 `expected_source_row_count`；字段修正已复审，实际入口比对待 projection 操作实现后核。首批无其他开测阻塞，06 architecture 与 catalog/composite focused 可按原授权进行；这不是 B 完成或最终测试通过。

## 7. 源码传输操作错误与明确恢复

实施者在 CT201 生成 bundle 时两次 exit 128，尚未触及被测对象。第一次把短提交手工错误展开为 `9225f78883d3b5a2b68bb3a3b2b1f88d04846567`，Git 报 bad object；第二次使用正确裸 commit `9225f78883b9743bec3246196b226d711b56d9ae`，因没有 advertised ref 报 refusing to create empty bundle。两者原因不同，不合并成同一失败。

`/tmp/s2b-b-source-bundle-invalid-ref.log` 与 `/tmp/s2b-b-source-bundle-empty.log` 是实施者事后写的事件记录，原始 stderr/exit 仅存在工具调用记录；本审核不称它们为原捕获日志。审核者已读文件并复算 SHA256，依次为 `f6e58fce85382a3c9065ef9209f5c3663ed5aaea40158df2445f8632c7079e3c`、`3828a97b9c348f1606c077c11e416d9ea11b01a3643d1134dba6a5f5447ad9d2`。实施者说明未 scp、fetch 或创建 06 worktree；审核者另只读核 06 main 仍为 `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3`、任务专用 ref 不存在、没有 B worktree，A worktree 仍为 db776。

主设计按既有 DC80 明确恢复，审核者确认最小方案可执行：从现有具名 `refs/heads/main` 生成以 2c79 为 prerequisite 的新外置 bundle；核祖先关系、list-heads、SHA 和 verify，经 LAN 传至 06，目标复核 SHA/verify 后 fetch 到 `refs/codex/s2b-b-source`，在全新 detached worktree 检出固定 9225 并建立 legacy 链接。已独立核 2c79 和 9225 均为当时本机 main `ff2b19f427` 的祖先。该方案不改产品、不新建 branch/tag、不触碰 A 的工作区或镜像。实际恢复由实施者执行并实时捕获 stdout/stderr/exit，结果待核；本段 GO 只针对已修正的传输步骤，不代表测试通过。

实际恢复随后已独立读取并核 SHA：CT201 source 实时日志 `/tmp/p6-s2b-b-source-main-ff2b19f427.log` 为 `a6b9e21e30f310620403a4e1a160c4bac1231b6c0e2a3bbdeae333452db6d7f7`，11:20:52–11:20:53 UTC，create/verify/list-heads/exit 均 0。来源脚本 SHA 为 `ac83213c5fb6a6eedbe376b160176c59ce7bef874c47bcae449db006e43e0c0d`，bundle SHA 为 `f02a6cf267bf9b1828c5e292f57ababd531da8595a4e39223c3c8f9c58b0a06f`。两个相同 end 时间字段仅为格式冗余，不重跑来源步骤。

CT201 transfer 实时日志 `/tmp/p6-s2b-b-transfer-main-ff2b19f427.log` SHA 为 `52c208fc2d45279285cee3617fa1cda22337848208f347d2e3c3e0dd41902dd5`，11:23:55–11:23:56 UTC；scp 与远端 SHA 检查 exit 0。06 `/home/dev/gdds-test-tmp/logs/s2b-b-sync-9225.log` SHA 为 `2759050ad59c93b6959877aebe2424ad2225363f340434df2607063126aa2276`，11:24:40–11:24:41 UTC；bundle 三个 prerequisites 实际 verify 通过，target bundle SHA 相等、专用 ref 新建、固定 9225 detached worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` clean 且 legacy 链接正确，全部命令及 script exit 0。A worktree 仍为 db776。传输时本机 main 已前进到文档提交 281b，但 bundle advertised ref 固定 ff2b、测试检出固定 9225，未混用 identity。此传输停止点闭合，仅允许继续原 focused 验证，未宣称产品通过。
