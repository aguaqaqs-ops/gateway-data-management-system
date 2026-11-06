# P6 S2b B 独立审核

状态：**推进暂停 / B 未 GO**。2026-11-06。主协调已按先前明确的重复操作错误停止点，暂停 B 并交 Owner 决定后续角色安排。当前产品候选 `5621bd48531b7af465e878f1bc7f87f707a772a3` 仅含 API/preflight 骨架、catalog count 接线及已有 example 的 policy 修正；业务算法和最终验证未完成。本报告不将 A 的结果作为 B 验证。停止时的确切范围与待办见 §9。

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

当前审核产品 HEAD：`5621bd48531b7af465e878f1bc7f87f707a772a3`。B 最终候选的容器重建与 native/health 按正式任务单必须执行，当前因实现未完成而延期，未给 API 小步反复构建镜像。当前 HEAD 没有 B 容器结果、没有 carried。B 最终候选还需在 06 完成适用 Rust fmt/clippy/workspace/release、完整 architecture CLI、五 Python 包 Ruff/mypy、强制安装扩展并校验 Rust tree、focused 与必要当前 image native/health。由实施者统一执行，审核者独立读取日志、SHA、起止 HEAD 与镜像身份。

最后已验证 image revision 是 A 的 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`：06 backend image ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0`，对应 Rust source tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`；准确 evidence 来源见 A 审核 §7。它不作为 B 通过、carried 或当前新增产品验证。A 最终依赖 base 为 d054，994c 仅是中间产物；B 是否复用取决于最终完整 input 与目标身份。

B 最终 gate：**未运行**；early focused 的两次失败见 §8，carried：无。S2b 最终 04 全量 runner/container 与 t1–t4 正确性不被 B focused 取代。W1/W2、真实 FULL 峰值与生产 M 未知保持 unknown，不记录性能通过。

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

## 8. 早期 focused 记录

06 `/home/dev/gdds-test-tmp/logs/s2b-b-early-focused-9225.log` 已独立读取并复算 SHA256 `6a6b43c4f454b57cba4e1ff4f56cd806f579ec522adb2bf7230bc87b99de4a61`。11:29:23 UTC 起止，HEAD 均为 9225/clean，Rust tree `46592e9cc1de7e181a7c6ff58fdf6b7b856e4db3`，Rust/cargo/rustfmt/clippy 均为仓库 1.97 工具链；offline、jobs 4、TMPDIR 与外置 target 明确。

实际 `cargo fmt --all --check` exit 1，只有 `business_kernel.rs` 两处格式换行与 `lib.rs` module 顺序差异。脚本在这里停止，compile、architecture 与 Python tests 尚未执行；script exit 1，不记通过。实施者按实际 diff 修正，候选与复验随后记录；本审核未改产品，也未在开发主机运行格式检查。

`75f2ddac93fc5b1b5cfb9f41dd7fb51dae421cbf` 已在 detached worktree 复审，恰为上述三个格式差异，无语义变化。其增量 source bundle 已生成并验证，来源实时日志 `/tmp/p6-s2b-b-source-main-75f2ddac93.log` SHA256 `5d28c20d47101215b613af4d27cae09e77cc5eedd89183e210b64931559ad3b9` 已独立核对；advertised ref 为 75f2、prerequisite 为 ff2b，11:31:53 UTC create/verify/list-heads/exit 均 0，bundle SHA256 `097f83f4a418f07b792f712c0a39063b20341b909531b4f24937a5718cae8f56`。

该增量传输的实时日志 `/tmp/p6-s2b-b-transfer-main-75f2ddac93.log` SHA256 `e21d4765aa57561f4b1ef03bc9a9d8828bb269a16278eb3b082494ed031aa06b` 已读并核：11:33:34 UTC scp exit 0，随后 SHA 检查路径误写 `...75f2.bundle`，实际文件为 `...75f2ddac93.bundle`，因此检查及 script exit 1。目标脚本的 bundle 变量有同一错误，尚未执行。审核者只读核 06 正确路径的 bundle SHA 与来源相等，脚本 SHA `fbcd057a456f106a4ff643d9f3cb7f8a8810dccf4d10c43284cf894480dd4d3c` 也与来源相等；任务 ref 仍 ff2b、worktree 仍 9225，没有 fetch/checkout 或测试。

主设计明确本次最小恢复 GO：保留原日志/脚本，新脚本使用正确 bundle 路径、新日志名，并在 checkout 前断言 porcelain 为空（原脚本只打印 status 与 unstaged diff，不足以拒绝 staged 改动）；不重建或重传已经正确的 bundle。审核者先核固定脚本再由实施者执行。主设计已明确，若本次再次出现同类人为 ID/路径错误，则停止并交 Owner，不无限循环。后续路径单一变量复用现有脚本，不建设同步框架。

脚本静态复审在执行前发现新增 `merge-base` 检查被放到 fetch 之前，目标尚无新 commit，该检查已删；这是执行前修正，不虚构第三次实际失败。最终脚本 `/tmp/s2b-b-sync-target-75f2-corrected.sh` SHA256 `581e70e1f2376c7d6e5ee25b173f30ed9a6b9d06698450d31bc8b85de4447f74` 已独立核准。06 实际 `/home/dev/gdds-test-tmp/logs/s2b-b-sync-75f2-corrected.log` SHA256 `07cdb2772cc9efe861bffc85bdc411a6a81311d417bba982a3c29158f5126f23` 已独立读取、复算；11:39:29 UTC，固定脚本、bundle SHA、verify、fetch、checkout 与 script exit 均通过，worktree clean 并固定 75f2。该同步停止点已闭合，可继续原 focused。

75f2 的实际 early focused 由 06 SSH 输出捕获到 CT201 `/tmp/s2b-b-early-focused-75f2-remote.log`，审核者已读并复算 SHA256 `1f2da23f501a363e70947f49b0d3792659cb9eccfab1df1cc4dfb3b43b4aafa0`：06 11:41:21–11:41:24 UTC，起止 75f2/clean，fmt exit 0；随后实际执行 `cargo run --locked --offline --package gateway-architecture-check --bin gateway-architecture-check -- --rust-workspace-root . --vnext-root ..`，因 `gateway-compute-core/examples/ordered_compare.rs` 首行缺 `#![forbid(unsafe_code)]` 而 exit 1。core tests、uv、pytest 均未开始；script exit 1。

这是已存在的源码 policy 缺口：独立 diff 确认 A 产品 db776 到 75f2，该 example 与 guard 都未变；workspace 已继承 forbid unsafe。A 的实际证据为 fmt/clippy/workspace tests/release，其中 architecture unit test 的真实 workspace 检查只调用依赖边界，不能等同完整 CLI 的 `run_checks`，本审核不虚构 A 运行过且通过完整 CLI。主设计授权当前 main 仅补该 example 的首行，冻结 CT108 工作区与 guard 不动；此为真实 policy 修正，不是源码传输第三次操作错误。

`5621bd48531b7af465e878f1bc7f87f707a772a3` 已在 detached worktree 复审，唯一 diff 是该首行属性与空行，无算法/运行时语义变化。可继续原 06 fmt/完整 guard/focused，结果待核。

## 9. 停止点与后续交接

5621 的 CT201 bundle 生成已成功，审核者仅在本机读取实际来源日志 `/tmp/p6-s2b-b-source-main-5621bd4853.log` 并复算 SHA256 `28df61e7b28d697764804ab6adcf9126933e34fbb8337f4eb729593b656f068d`：11:43:37 UTC，具名 main 为 5621、prerequisite 为 75f2，create/verify/list-heads/exit 均 0。bundle SHA256 `92adc55e3b0c55082c64571e0be02cce43c6a060f351a6966283dcd97ba5b29a` 同样独立核实。此操作从已提交 Git 对象生成 bundle，不包含当时 dirty 的本审核文档，也不是开发机运行产品测试。

随后实施者报告：本地生成 5621 目标同步脚本时，多处相同 75f2 完整值导致替换断言未命中，脚本没有生成，后续 chmod/bash/hash/diff 报文件不存在；没有 SSH/scp/fetch、工作区或节点测试操作。这一失败的原输出保存在实施工具记录，本审核不把消息摘要冒充独立读取的实时捕获日志。它再次触及主协调已明确的同类操作错误停止边界；主协调已暂停 B 并向 Owner 说明角色调整决定待定。审核者没有批准又一次恢复，没有继续节点操作，没有创建新 agent。

停止时范围：

| 项目 | 准确状态 |
| --- | --- |
| 当前产品 | `5621bd48531b7af465e878f1bc7f87f707a772a3`；前序 API/catalog `633e599cbc`、行数绑定字段 `9225f78883`、格式 `75f2ddac93`、example 首行 policy 修正 `5621bd4853` 均已静态复审。 |
| 已实现 | `business_kernel.rs` 公共 budgets/control/input/plan/output/outcome 类型与初始 `preflight_table_input`；必填 `source_device_row_count`、旧 Python extractor/factories/binder 接线与一个 filtered-nonempty 测试；没有三项业务操作实现。 |
| 06 最后实际状态 | 最后独立核实工作区 `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` 为 clean 75f2，专用 source ref 也为 75f2。最后实际执行的 early focused 在完整 architecture CLI 失败，未进入 core tests/uv/pytest。5621 尚无节点运行证据；暂停后未再查询节点。 |
| 已有运行结果 | 9225 fmt exit 1；75f2 fmt exit 0、完整 architecture CLI exit 1。两次日志已独立读取、核 SHA，不能称 B 通过。 |
| 尚无证据 | B core 算法/adapter 行为、完整 schema diagnostics、运行中控制/预算、workspace/clippy/release、五 Python 静态、重装扩展及 build-input、B 当前镜像 native/health 均未完成或未运行。 |
| 保留资源 | 现有 06 B worktree、专用 ref、外置 bundle/脚本/日志留给后续接手；A 工作区/镜像与 CT108 冻结资源未在本次审核中修改。 |

后续必须完成：SQL cell/row framing、duplicate 与 raw-content facts；device/point Arrow 完整验证过滤及 composite 例外；canonical keyed/keyless/ordered projection、actual source-row-count 比对、规范化/排序/hash 与 A IPC；真实 C Stream adapter 的复制前 metadata preflight、资源/控制与错误映射；既定独立向量/差分及最终 06 验证和 handoff。现有完整清单见 §3，不因停止而增加矩阵，也不漏掉 C–E 的 repository-ref/import-replay/export/恢复消费者。

本轮审核在提交此记录后结束，独立审核身份保留；是否继续由当前审核者复审后续 B，等待 Owner/主协调明确安排。B 未 GO，C 的实施启动不得引用本报告为 B 完成证据。
