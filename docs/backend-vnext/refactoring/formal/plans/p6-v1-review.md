# V1 时间与内容事实独立审核

2026-11-07。本报告由 V1 新独审角色维护；不复用 A1 的产品结论。依据 [V1 工作单](p6-v1-work-order.md)、[业务核验设计 §3–§5、§8–§9](p6-archive-business-validation-design.md)、[设计复审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)、实际 owning Contract、AGENTS、testing-conventions 与比例化保障政策。

## 1. 当前范围与结论

已预检产品前固定清单 **`2ca25b6514a10fbc29d8d66535f22d0a154e8bc5`**；首轮正式代码对象仅为 native 子候选 **`a500dd81525963775b5ee005a3aa8ba9abc041af`** 的五个 Rust 文件，不包含实施中的 backend 接线。native 修复候选 **`2c6f13731bd3b4a4ffd39c97ee2627d18009ae54`** 的同角色复审与证据见 §5。

**当前结论：2c6f13731b 的 native 定向审核通过，F1/N1 关闭；不是完整 V1 GO。** 首轮 a500dd8152 需修订的结论和失败记录保留。backend facts 类型、checkpoint/READY、T1/finalize、DDL/mapper、TTL 后基线读取尚未进入代码审，不能由这份子候选结论替代。

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
