# V1 时间与内容事实独立审核

2026-11-07。本报告由 V1 新独审角色维护；不复用 A1 的产品结论。依据 [V1 工作单](p6-v1-work-order.md)、[业务核验设计 §3–§5、§8–§9](p6-archive-business-validation-design.md)、[设计复审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)、实际 owning Contract、AGENTS、testing-conventions 与比例化保障政策。

## 1. 当前范围与结论

已预检产品前固定清单 **`2ca25b6514a10fbc29d8d66535f22d0a154e8bc5`**；首轮正式代码对象仅为 native 子候选 **`a500dd81525963775b5ee005a3aa8ba9abc041af`** 的五个 Rust 文件，不包含实施中的 backend 接线。native 修复候选 **`2c6f13731bd3b4a4ffd39c97ee2627d18009ae54`** 的同角色复审与证据见 §5。

**当前结论：native 定向审核通过，F1/N1 关闭；完整 V1 仍需修订和补齐证据。** 已追加完整候选 `3fcea5a2d0` 及修复候选 `499e378b0c` 的代码审（§6–§7），F2 的原 provenance 绑定和验证屏障仍待复核。首轮发现及失败记录保留，尚无完整 V1 GO。

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
