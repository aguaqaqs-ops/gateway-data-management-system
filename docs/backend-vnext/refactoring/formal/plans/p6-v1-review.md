# V1 时间与内容事实独立审核

2026-11-07。本报告由 V1 新独审角色维护；不复用 A1 的产品结论。依据 [V1 工作单](p6-v1-work-order.md)、[业务核验设计 §3–§5、§8–§9](p6-archive-business-validation-design.md)、[设计复审 §6](p6-be-a-d-archive-design-review.md#6-修订候选-16472197b4-复审与最终设计结论)、实际 owning Contract、AGENTS、testing-conventions 与比例化保障政策。

## 1. 当前范围与结论

已预检产品前固定清单 **`2ca25b6514a10fbc29d8d66535f22d0a154e8bc5`**；本轮正式代码对象仅为 native 子候选 **`a500dd81525963775b5ee005a3aa8ba9abc041af`** 的五个 Rust 文件，不包含实施中的 backend 接线。

**结论：native 子候选需修订、补齐证据后复审；不是完整 V1 GO。** F1 已由实施者认领。native 的 UTC 算术、源序归并与缺失分类未发现其他阻塞；backend facts 类型、checkpoint/READY、T1/finalize、DDL/mapper、TTL 后基线读取尚未进入本轮代码审，不能由这份子候选结论替代。

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
