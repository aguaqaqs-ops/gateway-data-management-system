# V1 时间与内容事实独立审核

2026-11-07。本报告由 V1 新独审角色维护；不复用 A1 的产品结论。依据 [V1 工作单](p6-v1-work-order.md)、[业务核验设计 §3–§5、§8–§9](p6-archive-business-validation-design.md)、[设计复审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)、实际 owning Contract、AGENTS、testing-conventions 与比例化保障政策。

## 1. 当前范围与结论

已预检产品前固定清单 **`2ca25b6514a10fbc29d8d66535f22d0a154e8bc5`**；首轮正式代码对象仅为 native 子候选 **`a500dd81525963775b5ee005a3aa8ba9abc041af`** 的五个 Rust 文件，不包含实施中的 backend 接线。native 修复候选 **`2c6f13731bd3b4a4ffd39c97ee2627d18009ae54`** 的同角色复审与证据见 §5。

**最终结论：V1 本节 GO，F1–F4/N1 全部关闭，无剩余阻塞。** 产品/最小容器候选为 **`84bad715a2faf281e94fa9c0c534414dc7246608`**，handoff/owning 文档核至 **`5b7812164a`**，最终证据与范围见 §9。04 权威及联合必要 Compose、05 fresh t1、V2、D/tar 与 FE3 均不在本节完成声明内；不办理联合 exit。首轮发现及失败记录保留，不用后续成功覆盖原运行。

只读 detached worktree：`/home/dev/gdds-reviews/p6-v1-native-a500dd8152`，HEAD 固定为上述候选，已链接主仓库 `legacy/`，审核期间保持 clean。未读取 main 中后续 dirty 实现，未修改产品或测试，未运行测试、编译、lint 或容器，未占测试节点；本角色只写本报告。

## 2. 需修订项

### F1（P2）：按 SQL token 形状排除了已解码为 TEXT 的合法值

定位：`vnext/rust/gateway-compute-core/src/table_access/generation_time.rs` L31–49，调用点 `values.rs` L182–192。

新 `observe` 只接受 `Lit::Str`。既有 `convert.rs::require_text`（L206–224）允许 TEXT 列的 hex literal 解码为逻辑文本；该转换成功后，`Lit::Hex` 却被新逻辑计为 INVALID。已审业务 grammar 作用于 SQL 解码后的单元格逻辑文本，而不是引号形式。

静态可达场景：

```sql
CREATE TABLE version_manager(saved_time TEXT);
INSERT INTO version_manager VALUES
  ('2026-11-07T12:00:00Z'),
  (X'323032362d31312d30375431313a30303a30305a');
```

第二行逻辑文本是 `2026-11-07T11:00:00Z`。目标为 selected=11:00@2、max=12:00@1、valid=2、invalid=0、LAST_NOT_MAX=true；候选会保留 selected=12:00@1、valid=1、invalid=1、LAST_NOT_MAX=false。TEXT 的 `X''` 同样应为 EMPTY，候选会记 INVALID。这会错误冻结业务时间及后续可接受异常，属于当前已接受的 A 类事实边界。

最小修正：在成功 typed 转换后的既有逻辑文本边界取值，复用原转换 helper，保持非文本类型与原 typed scalar 硬拒绝规则；在唯一 Rust owner 加合法 hex/空 hex 的小向量，不另建解析器或 Python 路径。实施者已确认技术遗漏，修复提交与专用节点证据待复审。

### N1：新测试尚未通过仓库 clippy 门禁

新 integration test 多处直接 `unwrap`，与 workspace `clippy::unwrap_used=deny` 冲突。实施者已报告 06 首轮 fmt 与 3 个 focused 用例通过、clippy 在 8 处测试 `unwrap_used` 失败，承诺保留失败日志/SHA 并按既有测试 helper 约定修正。这是已知静态检查失败，当前不能声明 native 整体通过；本角色尚未读取原始日志，不把实施者口头结果当已复核证据。

## 3. 清单预检与已核 native 边界

- 清单首次将全 EMPTY 与含 INVALID 但无有效值合并，已直接要求修正。native 候选现明确 `VALID/TABLE_ABSENT/COLUMN_ABSENT/NO_ROWS/NO_VALUE/NO_VALID_VALUE`；handoff 清单同步仍待固定提交核对。事实摘要须明确为 `raw SHA256(JCS facts body bytes)`，不改变原 canonical 内容摘要。
- `values.rs` 在整行原 typed 转换成功后累积，每个源行只进入一个 chunk；`mod.rs` 的 indexed Rayon 收集保持 chunk 顺序，再按 source-order 归并，不按 PK、规范行序或输出批次选时间。空/非法行计数进入 ordinal，selected 取最后有效值，max 严格大于才更新，等值保留首次行号。
- grammar 限 ASCII digit/指定 trim、T 或单空格、完整日期和秒、1–6 位 fraction、Z/带冒号 offset、±14:00 上限、0001–9999 与 UTC 归一越界；使用整数微秒比较和 proleptic Gregorian，不依赖 float、timezone 或宿主 `fromisoformat`。Shared Kernel scalar 未修改。
- parser document/resource/cancel/deadline 失败不发布事实；version_manager 表本身 typed 转换失败或未知类型时事实为 None。原 partial/failed 表及错误优先级不被时间质量诊断改写。PyO3 只新增固定大小 metadata 字典，未搬整列到 Python。
- 新 Rust owner 参数化 grammar、缺表/列/行/全空/非法、跨 INSERT 和列序、N/chunk 不变、最后有效非最大与 max 等值首行；未引入 Dolt fixture、Python 参考解析器或大输入基准。原 parser canonical bytes/golden 未纳入新 metadata，也未被重录。

完整候选还须核：FULL initial 的全规范表内容身份；baseline 来源 Submission 自身 rules/projection/scalar 身份；Preview checkpoint 与 READY 的完整冻结、损坏和取消/失租/旧 generation；T1/finalize 同事务复制、replay/重启不重提取及 Preview/SQL TTL 后持久读取。现有 `_unchanged_baseline_identity_table_set` 只可用于工程身份，不能因 canonical rowset 相同而复用 SQL 源序时间；`NO_CANONICAL_CHANGE` 仍沿原 owning 规则，不因 facts 差异改变内容判定。

## 4. 证据与容器决策

本轮仅完成固定提交的静态阅读与 Git diff 检查；06 由实施者占用并验证，待其提供固定修复候选、日志与 SHA 后本角色只读复核。全部编译、测试、lint 必须在专用节点的 clean 已提交 worktree 上；Rust 后 backend 仍须强制重装扩展并核当前 Rust tree build input。没有本轮 carried 声明。

```text
Current reviewed HEAD: a500dd81525963775b5ee005a3aa8ba9abc041af
Container rebuild required: yes（本节收敛候选）
Reason: production native 与后续持久接线改变实际镜像；本次只是未完成接线的 native 子候选
Last verified V1 image revision/source-tree: none
Container gate for current HEAD: deferred
Carried from: none
Deferred focused gate: native 修复提交的 fmt/clippy 与 tests/configuration_generated_time.rs
Deferred minimum container nodeid: tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey（06 完整 V1 候选）
Required execution point: V1 收敛候选；04 联合权威/必要 Compose、05 fresh t1 留联合候选
```

本报告不交付 V2 来源图/归档接受/Start/关闭出口、D tar 或 FE3，不办理联合 exit。普通修复仍由同一实施者与本独审角色闭环；后续复审追加固定候选与证据，不抹去本轮发现及失败记录。

## 5. native 修复候选 2c6f13731b 复审

同一独审角色新建只读 detached worktree `/home/dev/gdds-reviews/p6-v1-native-2c6f13731b`，固定 HEAD **`2c6f13731bd3b4a4ffd39c97ee2627d18009ae54`**，legacy 链接和 clean 状态齐备；原 a500 审核 worktree 保留。只审 `a500dd8152..2c6f13731b` 的三份 native 实际修复文件，期间的协调文档/本报告提交不改变产品范围，未读取 dirty backend。

**F1 关闭。** `generation_time.rs::observe` L31–48 仍在 typed 转换成功后执行；限定 String/Enum/DateTime/Timestamp 的逻辑文本，复用 `convert::require_text`，不另写 token 解码或放宽原 scalar。TEXT hex 时间被按已解码文本处理，空 hex 为 EMPTY；非文本值仍计 INVALID，非法 typed 时间仍为 parser 硬失败。同一 Rust owner L181–188 增加 hex 时间/空 hex 的计数向量；既有 grammar、源序、N/chunk、缺失和 typed 拒绝向量保持。

**N1 关闭。** 新测试改为仓库既有 `match`/`unreachable!` helper 约定，无 `unwrap`；06 修复候选 workspace/all-targets clippy 实际成功。首轮失败是测试静态 lint，不是缓存缺失、身份不符或产品运行失败，修正后在新 clean 提交运行，不删除失败证据。

独审先以 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'` 确认连接，再只读原始日志并重新计算 SHA256。节点 hostname 为 **`gw-dms-06`**，测试 worktree `/home/dev/gdds-test-tmp/wt/p6-v1` 当前 clean、HEAD 为修复候选、legacy 链接正确；有效占用记录归 `/root/be_v1_impl`，开始 `2026-11-07T08:29:49Z`，本角色未另占或执行测试。日志均位于该节点 `/home/dev/gdds-test-tmp/artifacts/p6-v1/`：

| 日志 | UTC 起止 | 起止 HEAD / exit | 独立重算 SHA256 |
| --- | --- | --- | --- |
| `native-clippy-a500dd8152.log` | 08:31:33–08:31:48 | 均 a500dd8152 / 101；8 处测试 unwrap 失败 | `eca201e5cb53b1f92c4205f1c867f2be3325e8a1a8a998ed8af76f63ecade4b1` |
| `native-toolchain-2c6f13731b.log` | 08:38:28–08:38:28 | 均 2c6f13731b / 0 | `d0d98cda4c0f349e7ef2f1325f7b6f3f5a8e49759d07ca8761cccabbcda8620c` |
| `native-fmt-2c6f13731b.log` | 08:38:28–08:38:28 | 均 2c6f13731b / 0 | `6ea64037ad1edbdcc4c642696f9c0a3d8bf714c7c827ba6fbb0d95cef417e6c9` |
| `native-focused-2c6f13731b.log` | 08:38:28–08:38:29 | 均 2c6f13731b / 0；3 passed | `67d59af2e961dcce3914aa8c3e9aa75262db3c2d62098c4c9eb25bfe20e723ae` |
| `native-clippy-2c6f13731b.log` | 08:38:30–08:38:31 | 均 2c6f13731b / 0 | `b0727188b7ce4e7294609c3b6d4847f9ab8b4e0e0ee2e49679d296c798b3e140` |

实际命令由实施者声明并与日志输出相符：`cargo fmt --all --check`；`cargo test --locked --offline -p gateway-compute-core --test configuration_generated_time`；`cargo clippy --workspace --locked --offline --all-targets -- -D warnings`。toolchain 日志记录 rustc/cargo 1.97.0，rustfmt/clippy 对应同一 1.97 工具链且四工具均解析到 `/home/dev/.cargo/bin/`。实施者声明 UV/CARGO offline、无 proxy、复用本节点预填缓存，`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-v1-cargo-target`；focused 日志中的实际 binary 路径位于该 worktree 外目录。本次只核既有成功记录，未补跑测试。

因此 **native 定向代码及修复证据 GO，无剩余 native Finding**。这不是 Rust 全包门禁、扩展安装/构建输入验证、容器或完整 V1 通过；清单缺失枚举与精确 digest 文案修订仍随完整候选核对，backend 尚未提交的接线不在本结论内。

容器决策更新：`Current reviewed HEAD=2c6f13731bd3b4a4ffd39c97ee2627d18009ae54`；本节收敛候选仍须重建并执行 §4 的 06 最小旅程，当前 gate=`deferred`，V1 image revision/source-tree=`none`，`carried=none`。04 联合权威/必要 Compose、05 fresh t1 继续留联合候选，不能提前宣称 exit。

## 6. 首个完整候选 3fcea5a2d0 代码审

固定对象 **`3fcea5a2d0e61a82cdddd5c91e240f15f14a3a2a`**；只读 detached worktree `/home/dev/gdds-reviews/p6-v1-full-3fcea5a2d0`，legacy/clean 已核。审核覆盖从 V1 起点到该候选的实际产品、Contract、版本和 golden；Rust tree 相对已审 2c6 未改变。该候选的新增冻结断言、静态/功能证据尚在实施者补齐，代码审不代替执行证据。

### F2（P2）：把合法历史 provenance 差异升级为 Preview 硬拒绝

`preview_jobs.py` L1220–1239 使用 runtime ruleset 构造 baseline identity，再要求 source Submission.modified 的原 identity 与之全等；`domain/configuration_facts.py` L178–180 另要求三侧 rules/projection/scalar 完全相同。已存在的 `test_additive_ruleset_previews_nonempty_baseline_from_older_manifest` 明确支持旧基线 A、当前新增无关规则 B 的正常 Preview；该场景会在上传物化后被新校验提前拒绝。

此项已交协调者/设计者澄清，正式依据为 **`a24b7034e98159ced826d387e539884f3e506fbd`** 的业务设计 §3.1/§8：baseline 保留 source Submission 原身份，MODIFIED_ONLY.initial 精确复制，FULL 两上传侧使用本 operation 规则；合法版本差异不使 Preview 整体失败，也不成为 V2 全局不可接受的硬门禁。V2 仅禁止跨身份直接判等/合并，未解释来源仍走既有分量与接受机制；不新增 issue 类别/容量轴。runtime/operation mismatch、T1 derived-stale、STORAGE_BREAKING 和损坏/未知编码拒绝保持。

最小修复须同时保留两条边界：允许各侧合法原身份不同；source facts 的原 rules/projection 必须与其 exact commit 的权威 manifest 一致。不能通过删掉全部身份校验、重标旧事实或把原 ADDITIVE 测试改成拒绝来关闭。

### F3（P2）：Submission 独立读取未验证自己的上传源引用

`domain/submission/models.py` L304–311 只验证 facts 的 Workspace/revision/baseline/canonical 绑定，没有 Attempt L217–223 已有的上传侧 source ID 归属校验。单独把持久 `submission_records.source_artifact_refs` 改为 `other-source` 不改变 facts body/digest，原 reader 仍会接受，后续 baseline source 读取可信任一份源引用互相矛盾的记录。

此项不要求防御同 UID 恶意重签 facts，而是两个既有持久字段的普通完整性边界。最小修复为 Attempt/Submission 共用同一上传源绑定校验，并在现有 SQLite read owner 用一例原 facts 未变、外层源 refs 损坏的记录证明硬拒绝，不读取原 SQL。

### F4（P2）：把真实 parser 失败误判为漏保存 facts

`preview_jobs.py` L1498–1501 在调用既有 materialization 之前，遇到 metadata=None 就抛出无 `diagnostic_code` 的 `PreviewJobError`。native 的真实 document/typed 失败也明确不产生 facts，因此原 `TABLE_READER_UNAVAILABLE` 等 source diagnostic 会被通用“facts missing”抢先覆盖。成功解析漏 metadata 与输入本身解析失败不是同一原因。

最小修复：让原 parser/materialization 的错误与控制边界先成立，再对成功输入缺 metadata 作硬完整性拒绝；不增加任何默认 missing 或解析回退。

### 已核完整链路与当前验证范围

- FULL initial 与 modified 摘要均复用完整 canonical summary 的 `canonical_state_digest_of`，没有排除 version_manager/BROWSE_ONLY/SNAPSHOT_ONLY 或改用 comparison/snapshot/raw SQL digest；SQL 源摘要和提取规则进入独立 facts。
- materialize/assemble checkpoint 严格包含 facts envelope、必需字段与初始摘要，READY 沿原 LeaseSession 整体发布；未增加业务状态旁路。T1 复制 exact Preview facts，Attempt CAS 拒改，finalize 同事务复制且 replay 比对；读取 Submission 不需要 Preview 或 SQL。
- 唯一基线增加 Attempt/Submission 必需 BLOB；旧 DB 沿既有 sqlite_master 结构拒绝。job/materialized-sides/assemble-state/Submit 版本为 v2/v2/v3/v2；旧活动版本读取路径未保留。新增唯一 facts golden，既有业务 golden 未重录；HTTP DTO/OpenAPI none 的清单与实际 diff 相符。
- 初版清单 NO_VALUE 和精确 digest 文案现已同步；native metadata 在 application 转 domain，capability 保持 leaf。测试工厂显式构造新必需事实，不把 production 缺字段默认为业务 missing。另已反馈空 source refs 的旧 fixture 适配遗漏，不能用产品默认填补。

## 7. 修复候选 499e378b0c 的代码复核与剩余项

新只读 detached worktree `/home/dev/gdds-reviews/p6-v1-full-499e378b0c`，固定候选 **`499e378b0c`**，legacy/clean 齐备，原工作树保留；只读其实际修复，不读后续 dirty。

- **F3 代码修复成立，执行证据待核。** 新 `ConfigurationFacts.assert_source_artifacts` 由 Attempt/Submission 共用；SQLite 原 owner 增加外层 source refs 损坏的读取拒绝断言。
- **F4 代码修复成立，执行证据待核。** 必需 native facts 检查移至 business materialization 成功之后，真实 parser FAILED 先保留原诊断，成功输入漏 metadata 仍硬失败。
- **F2 部分修复，尚未关闭。** 去除三侧一律相等，保留 FULL 两上传侧同 operation 规则，MO.initial 复制原 baseline，未知 projection/scalar 硬拒绝；原 ADDITIVE 测试继续要求 Preview 成功并增加 A/B 原身份断言。但新增 baseline 校验仅比较 manifest digest 与 source 引用，尚未比较 facts 原 ruleset digest/projection 字段与该 manifest 自身字段。相同 canonical state digest 可以来自规则 A/B，不能因此信任另一合法 SHA 表达的伪造 provenance。已直接要求按原 manifest 补最小绑定和一条负例，不与 runtime 身份比较。
- **冻结验证仍需补齐。** 新测试证明正常 materialize→assemble→READY 保留 native 时间，但未进入 materialize checkpoint 已存在的恢复分支；TTL 断言只删除 Preview 并直接读 Submission，尚未沿 BaselineNode.source_submission_id 且使旧 SQL 不可用证明独立读取。已请在原 owner 扩展各一个代表屏障。取消/旧 generation 复用原发布测试补无持久 PreviewResult 断言；失租沿既有 lease owner，不新建调度矩阵。T1/finalize 复制和原 replay 的新事实断言已到位，等待实际成功记录。

06 的扩展重装/build input、五包静态、focused 和本节最小容器由实施者在 clean 提交上继续执行；本角色尚未核这些完整候选的成功日志。首轮静态失败日志须保留，不用后续成功替换。当前 `Current reviewed HEAD=499e378b0c`，容器重建仍需于本节收敛候选完成，gate=`deferred`、V1 image revision/source-tree=`none`、`carried=none`；§4 的 06 最小 nodeid、04/05 联合验收落点不变。

## 8. 837e3b016a→c4640fc6fb→b73713ea9e 代码与定向证据复审

分别固定新只读 detached worktree `/home/dev/gdds-reviews/p6-v1-full-837e3b016a`、`/home/dev/gdds-reviews/p6-v1-full-c4640fc6fb`、`/home/dev/gdds-reviews/p6-v1-full-b73713ea9e`，legacy/clean 已核，原工作树保留。最新完整 SHA 为 **`b73713ea9e2cb2588ebaee80e0c30ea53a4f6ded`**；上述区间实际产品修复只有原 manifest provenance 对比及 DDL 末尾列顺序调整，其他是测试/fixture 适配与 F4 回归，不审中间 dirty。

**F2 关闭。** 837 的 baseline 校验现将 facts 原 ruleset digest/projection 与 exact commit 的原 manifest 自身字段比较；继续允许旧 baseline A/current upload B，不与 runtime 误比。原 ADDITIVE 成功测试保留 A/B 断言；同一 Preview owner 新增 source facts 伪造另一合法 ruleset digest 而原 manifest 不变的拒绝向量。未知 projection/scalar 仍严格拒绝，FULL 两上传侧仍绑定本 operation。

**F3 关闭。** 共享上传源校验及 SQLite 独立读取坏 refs 拒绝的原 owner 已实际通过。History consumer 原测试把 source refs 清空作为合法正例，与新必需源绑定冲突，现保留一致的两源正例；没有放宽产品 validator，坏绑定负例仍归唯一 mapper owner。

**F4 关闭。** `f6d1a574f5` 新增真实非法 typed DATETIME 的唯一 Preview wiring smoke：原 `TABLE_READER_UNAVAILABLE`、Operation FAILED、无 READY closure/PreviewResult；在 b737 单独 `-n 0` 实际通过。完整 native grammar 矩阵未复制到 Preview。

恢复测试在 durable materialize checkpoint 已发布、successor 未发布的屏障中止；新建 LeaseSession，禁用 SQL parser 后重入实际已有 checkpoint 分支并继续 READY，冻结 facts 完全一致。初版实例 monkeypatch 与 LeaseSession slots 冲突，c464 改为局部 context 内 class barrier，实际通过。Submit 原事务 owner 证明 T1/finalize 同事实、合法 replay 不改；删除 Preview、阻断原 source store 读取，再经真实 BaselineNode.source_submission_id 读同一 durable Submission。Attempt CAS 拒改 facts、旧 generation 不留下 PreviewResult 行也在原 owner 断言。失租仍由原 LeaseSession 屏障与唯一 owner 保证，未另建调度矩阵。

所有以下原日志由本角色在 **06 / `gw-dms-06`** 只读核验并重新计算 SHA256，目录均为 `/home/dev/gdds-test-tmp/artifacts/p6-v1/`，记录起止 HEAD/UTC/exit；没有在开发主机执行测试：

| 日志 | 固定 HEAD / UTC 起止 / 结果 | 独立 SHA256 |
| --- | --- | --- |
| `backend-focused-c4640fc6fb.log` | c464 / 08:52:09–08:52:24 / 320 passed、exit 0；其中两项 serial 当时在 -n4，合格 serial 来源另见下行 | `4c9e119afdfaff35bd87a6b3cc6db4667dcbdbfc3afcd918ea75e64b46cc312a` |
| `native-adapter-serial-b73713ea9e.log` | b737 / 08:57:10–08:57:11 / adapter 两项 `serial and not parallel_safe`、-n0、2 passed，修正前批次执行条件 | `26be9c5309d8f95f5fe1d15e7fd1a9cc21a71d0b4c7c1168fc1b03123afb3267` |
| `parser-diagnostic-b73713ea9e.log` | b737 / 08:57:08–08:57:10 / F4 smoke -n0、1 passed、exit 0 | `21ff1b439cf992e5e73112a382b762bc3675b4bb0c480137a62fd3479e0b7b8f` |
| `backend-consumers-b73713ea9e.log` | b737 / 08:57:11–08:57:50 / 明示非 serial 主体 -n4、453 passed、exit 0 | `f1cdd2e1f0b7c3df49397bd97ad17c2a8ab9fe3934c68fe7bd0125a43a6b041d` |
| `backend-consumers-serial-b73713ea9e.log` | b737 / 08:57:50–08:57:55 / 明示 serial -n0、5 passed、exit 0 | `d0a86ef3ef74e71d9307172156b0e9370bd3f9b9dfe505531b24715da80f91fc` |
| `rust-all-c4640fc6fb.log` | c464 / 08:53:03–08:53:32 / cargo test --workspace --locked --offline、exit 0 | `8e33c7d8cd98fbd7074d01a8e0b0958b8d87503774b7178331ea2a6f096c3265` |
| `extension-build-input-c4640fc6fb.log` | c464 / 08:52:08 / expected=installed=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`、exit 0 | `a4cf2d92ac05f70f99e5522b34d1a0f8c4e9226f2af0c5165760ff395cb214e1` |
| `sync-backend-3fcea5a2d0.log` | 3fcea / 08:41:39–08:42:57 / 受控 sync --reinstall-package gateway-compute-python、exit 0 | `f174cc0bd6a8627cb333c0503d5d9c9aca21b0568cebfb2c433f4df34ec3c30d` |

c464 正常非 serial 318 项未为修正两项 serial 重跑。b737 consumer 的精确文件清单在日志 argv 内，覆盖 Workspace/Preview/Submit HTTP 和查询、worker、Review、Archive query/transaction/http/concurrency/audit、History、commit metadata 等实际受影响 consumer；原事实拒绝没有被 skip 或改成默认。最终 DDL 仅把必需 facts 列排在 identity_confirmations 后，与 mapper/raw fixture 顺序一致，NOT NULL/类型 CHECK 不变；新 schema owner 及 fresh DB 最小 Compose 仍待本角色核证。

五包 c464 同 HEAD ruff/mypy 原日志均 exit 0，已逐份读原文并重算 SHA（`final-{ruff|mypy}-{package}-c4640fc6fb.log`）；backend 后续测试变化的最终增量静态尚待核。Rust tree 在 2c6→b737 保持 **`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`**，fmt/clippy 仅限定引用 §5 未变源码结果，不声称权威 Rust 包或容器 carried。

原失败证据均保留并已独立核到根因：

| 原日志 | 实际失败与后续处理 | SHA256 |
| --- | --- | --- |
| `ruff-backend-3fcea5a2d0.log` | 3 个测试 unused import；后续删除过时 import | `781258c1b69d64739705d5a8d2ab7e74a485dece5890619c976178f552145c08` |
| `mypy-backend-3fcea5a2d0.log` | 4 个 cast/optional 类型问题；后续显式收窄 | `150223b8035e55d23b8d9e1d6433bb294cfa43025acd3e3865911027e0601833` |
| `backend-focused-efcb362bec.log` | 239 passed / 55 failed；fixture 改名 operation 未同步内层 facts 等适配问题，固定提交修正 | `1c466f3d30e610a61ce860ced51cb22f1a846581f140ea5c0c454aab088c4607` |
| `backend-focused-ef8af78e2c.log` | 318 passed / 2 failed；slots 实例 patch 及剩余 no-change fixture rebind，c464 修正 | `8885f03cdd1437b99d4c2e1066bd098a9bd6bd47bb3a5acb3e4a2dfd53ccd1d6` |
| `backend-consumers-c4640fc6fb.log` | 169 passed / 7 failed；sibling fixture rebind、raw INSERT 漏必需 BLOB、空 refs 旧正例，5864/b737 显式适配 | `81ab2e0a6e636b863928923f1f5c1315a5dce70c0bb41a95f8af721b2ae810a5` |

另只读核 `checkout-command-error-efcb362bec.log`，SHA `4ba72ca9a87fcd60de6396ceabe6fed15ec426192fca174b52ca6555cb803cbc`：FETCH_HEAD 不存在的自身命令错误，未派发测试、未写 worktree；修正工具后在固定 clean 提交运行。上述运行都不是权威 runner 来源，不作任何包闭包/容器沿用。

当前 `Current reviewed HEAD=b73713ea9e2cb2588ebaee80e0c30ea53a4f6ded`；V1 最小 Compose 正在实施者的 06 clean WT 上执行，schema owner/最后 backend 静态及镜像 provenance 尚待核，故 gate=`deferred`、`carried=none`、无完整 V1 GO。04 联合权威/必要 Compose 与 05 fresh t1 仍未执行，不能由本节定向通过提前关闭。

## 9. 最终产品 84bad715a2、交接 5b7812164a 与本节结论

同一独审角色固定最后产品 worktree `/home/dev/gdds-reviews/p6-v1-full-84bad715a2`、文档 worktree `/home/dev/gdds-reviews/p6-v1-docs-5b7812164a`，均 detached/clean、legacy 齐备；此前审核 worktree 保留。`b737..84bad` 唯一产品树内变化是既有 Submit Compose 旅程四行复用既有 capture/persist provenance，没有改变业务或门禁判定。37a401924d/5b7812164a 的实际 handoff/owning diff 仅文档：正文 Preview/Submit v2、必需 facts digest 和当前 closed payload 对齐；清单冻结时点与实际完成状态已分开。独审核对产品、最终文档的 `vnext` tree 同为 **`608f4b7a837db4a76f1448d4d9d065d66b4e4436`**，Rust tree 仍为 §8 所列值。

**最终 schema、backend 静态及 06 最小 Compose 均已核实成功。** 以下日志均位于 06 `/home/dev/gdds-test-tmp/artifacts/p6-v1/`，hostname 为 `gw-dms-06`；起止 HEAD 均为 84bad，原文/argv/起止 UTC/exit 和 SHA256 已独立只读复核：

| 日志/产物 | 实际结果及 UTC | SHA256 |
| --- | --- | --- |
| `schema-owner-84bad715a2.log` | 09:02:19–09:02:21，最终唯一基线 schema owner 14 passed，exit 0 | `e204d151dfde3397aa5d5106bed807cb32e2e3fc1e8ae694357d5ec8bd2661ce` |
| `compose-final-ruff-84bad715a2.log` | 09:02:19，ruff check .，exit 0 | `07959fc20998f4137923eaac2a558e55eb24116f5caf0fdc89f03399110bbe55` |
| `compose-final-mypy-84bad715a2.log` | 09:02:19，503 source files，exit 0 | `97e33352920935d2ea2666d4df9a11bcd2e060da652ca2b1bd3d95b679ea357e` |
| `compose-submit-84bad715a2.log` | 09:02:39–09:03:10，既有 Submit 旅程 -n0/serial，1 passed，exit 0 | `a5c44cb1e5ac17967f4a7e3fa71d815db8a5fc0799630de108b7fface96ff88b` |
| `submit-provenance-84bad715a2.json` | 实际运行 backend/worker/RS 镜像及 RS source labels | `d1ecc47cd556f5e30e7051bdbb05cc77b04f62945fb0fc23bfea93ff0e17e85a` |
| `image-identities-84bad715a2.json` | 实际 docker save config digest 与全部 RootFS DiffID | `6ca6ac126f51bfefebf94dbdd482e619ceae0d98eec3a80c99e13bf7bbb5b008` |
| `frozen-business-b73713ea9e.log` | b737 08:58:38–08:58:40，既有 comparison/bundle/risk/surface 101 passed，exit 0 | `c472fa7f5e2b1ec6af9603ac07c645aa0a0860d9c9d14ec0e4d9f29884624f3c` |
| `node-release-84bad715a2.log` | 09:05:20，清理后核本人 owner 并释放，exit 0 | `6c3b5d83cf03eabffc5cd6b756ad2cd7c2680189765efbd9bcb8aeeb2a6c15fa` |

精确容器 nodeid 为 `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`。已读归档执行脚本：每步先核 clean worktree 和本人占用标志；明确 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、外置 TMPDIR/target/jobs4，剥离 proxy 与 Rust toolchain overrides；backend/worker 使用预置 dependency-base，保留 Compose build、`GATEWAY_DOCKER_BUILD_NETWORK=none`、prebuilt 未设置。RS 由最终候选本机离线构建新 tag `gateway-repository-service:v1-84bad715a2`；真实 fresh project/DB/卷旅程成功，finally 执行 down -v/remove-orphans。没有在开发机运行测试，没有本轮新依赖/制品下载或跨节点传输。

运行 provenance 的本机 image ID 为 backend `sha256:bccf76316a3814b69b87a9bc5d1e9e50e56dc1a1004aa38d5928ab8686b45d07`、worker `sha256:2ad106246e21d09570c9b4422c5fe715ac52d9f81a3030fa4848836c71ffb28c`、RS `sha256:960267b20db0c11431f162be0037cd4dcbf43fd21308be173da92cda157a2246`；与身份 JSON 各 ref 一致。已读身份脚本，它从 docker save 的实际 config bytes 计算 SHA，并核全部 DiffID 与本机 Layers 完全相同，没有把 containerd inspect ID 当 config digest。backend/worker config digest 分别为 `sha256:e33455ebb9d3df8eb7b193accf8234881264a6825aa17c1864abea4bb95ba3ef` / `sha256:ff6df3be31d6bc01a237a7aece3a53fc5f103478583ff065ea15c0d29e2f08ae`，各 13 个 DiffID；RS config 为 `sha256:a5a530f5afc229bd411b1678df61b5523cfc58cf9ad30ce30a39ddfa8d51c2dc`、28 个 DiffID。完整列表及 dependency-base 身份保存在上述 JSON，不重复另建镜像权威。

RS `org.opencontainers.image.revision=84bad`；其未变源码的 build-input revision 为 `a6876d560050285321fd9f62942d590a03f35d64`，source-tree 为 `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`，既有 harness 在保存 provenance 时实际重算并核对。backend dependency input 实际仍为 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`；本节依赖/lock/base 未改，使用 06 原本地预填 uv/Rust/Docker 缓存，历史 CT201 制品来源与预填时间在 handoff/06 readiness 引用，不伪造本轮新传输。

`evidence-index.json` SHA 为 **`a1ef262e92482d90ecf87d95d259f8d3637cc1e7a4063fc5618e37acfda26249`**；本角色在 06 用标准库只读逐项重算全部 **78 份日志、14 个附件/脚本**，无摘要不符。关键成功、原失败与实际执行条件已逐项核对，不把索引替代原测试结果。另只读现场确认：测试 WT 仍 clean/HEAD84bad，busy 标志不存在，该 project 的容器/卷/网络均无残留，8000 无监听；未占节点或清理他人资源。

最终容器决策：

```text
Reviewed product HEAD: 84bad715a2faf281e94fa9c0c534414dc7246608
Reviewed docs through: 5b7812164a
Container rebuild required for V1 product: yes，已在最终产品候选完成
Last verified image revision: 84bad715a2faf281e94fa9c0c534414dc7246608
Container gate for reviewed product: passed（06 既有最小 Submit 旅程）
Docs-only follow-up: not-applicable（无 vnext 变化；不另作产品/容器通过声明）
Carried from: none（本节没有权威 runner 包闭包或镜像 carried 判定）
Deferred: 04 联合权威/必要 Compose；05 fresh t1 及联合范围
Required execution point: V2/D 后联合最终候选，不在本节办理 exit
```

**V1 本节 GO。** 已审范围满足同次 Rust 源序时间提取、完整内容身份、checkpoint/READY→T1→不可变 Attempt/Submission、损坏拒绝及 TTL 后基线来源独立读取的交付要求；无剩余产品 Finding、文档缺口或缓存阻塞。审核与修复始终由原两角色闭环，未通过更换审核者消除 finding。本角色只改本报告、未运行产品测试/编译/lint、未修改产品/前端/冻结基准、未推送或改 tag，至此停止本节写入与执行。

后续唯一范围：V2 使用本领域类型与持久 Submission 端口，把 facts digest 纳入 candidate/selection/anomaly subject，并按 a24 的逐侧身份规则完成来源/时间核验、接受/Start 和关闭出口；D 完成 tar，FE3 由前端 owner 处理。04 六项尚未执行的既有容器 owner 及 05 真实入口已在 [handoff §6](p6-v1-handoff.md#6-明确交接与延期) 明列；`--scope full` 是旅程范围，不等于已覆盖 FULL 输入模式。本节 06 证据不冒充联合最终、真实数据或前端 GO。
