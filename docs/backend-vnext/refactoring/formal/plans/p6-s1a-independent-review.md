# Phase 6 S1a 独立阶段审核

日期：2026-10-27（UTC）。结论：**定向修订，暂不接受阶段退出**。

存在 **3 项阻塞 finding、2 项非阻塞 finding**。已复现的产品问题是未变 ordered 表仍执行完整比较中的逐行比较/LIS，以及 INSERT 单条 SQL 可突破冻结的 4 MiB 上限；另有 DC58 内容保值证据范围不足。未发现需要否定整体方案、引入兼容层或扩大信任边界的问题。

六包门禁、真实旅程、阈值/表哈希证据有合格来源；本次 focused 复跑通过。`af559ae3d2 → 26c066e9bb` 的 backend、repository_service 闭包及镜像身份等价核对通过，可以 **carried**。这些通过项不代替上述三个阻塞项的关闭。

## 1. 对象、边界与工作方式

- 审核区间：`5a2989bec2fbc269b0e567bcee4cc309513f90e4..26c066e9bbb32660573ec21147c062bc28505402`。
- 产品候选 V：`af559ae3d274e3e9df687b448edd331cdc6d7412`；交接候选 H：`26c066e9bbb32660573ec21147c062bc28505402`。
- 区间包含 `d863445bc6..55363b37e1` 早期直接进入 main 的实现，也包含后来从 main 合入的文档及调查工具。按 owner 提供的事实，早期产品提交已经推送；handoff 的“没有推送”不能解释为整个 S1a 历史从未推送。本次没有推送。
- `git diff --name-only V..H` 只有五份文档：P5 execution plan、P6 design、execution plan、owner decisions、handoff。两者 `HEAD:vnext` 均为 `833dd124540723f503ea734de06805e5f1798a16`。
- 先读 AGENTS、指定 DC39/DC45/DC55/DC57/DC58/DC59、设计 §4/§14/§16.2/§17、执行计划 S1a、H 版本完整 handoff；再读相关 Contract、S0 审核 §7.3、testing-conventions 与比例化政策。采用新决议对旧条目的修订，不要求恢复已被 DC58 取消的 snapshot/comparison digest 保值。
- 开发机审核 worktree：`/home/dev/p6-s1a-independent-audit`，以 `git worktree add --detach ... 26c066e9bb` 建立，添加指向主仓库 `legacy` 的符号链接。此 worktree 只读，始终 clean。
- 报告单独位于 `/home/dev/p6-s1a-review-report`、短期分支 `p6-s1a-review`，基于 H。唯一提交文件为本报告；不改产品、测试、设计、计划或决议，不合入诊断分支。
- 三台节点首先分别执行 `ssh -o BatchMode=yes <alias> 'echo OK'`，全部成功。05 与 04 检查 `docker ps`、`pgrep -af 'pytest|run-tests|dolt|cargo'`，除检查命令本身外无相关进程/栈。05 复跑使用其原有 clean detached `final-af559-wt`（legacy 链接存在），开始/结束均为 V；`TMPDIR=/home/dev/gdds-test-tmp`，没有设置 `GATEWAY_TEST_BASETEMP`。
- 本次没有完整 runner、Compose、真实旅程或性能重测；没有在开发机执行产品测试。没有收到 auto-mode 分类器拒绝。传输 H 的首次 Git bundle 命令因使用裸对象参数返回 `Refusing to create empty bundle`，未生成包；随后使用现有分支名正常生成。这是 Git 错误，不是自动审批拒绝。

本报告中 `B/` 指 `vnext/backend/src/gateway_backend/`；行号均指 H（其产品代码与 V 相同）。节点证据目录简称 `L=/home/dev/gdds-p6-logs/s1a`。

## 2. Findings

### F1 — 阻塞：未变 ordered 表仍执行逐行比较、LIS 与两次摘要

位置：`B/capabilities/comparison/ordered.py:139`、`:152`、`:480`、`:529`、`:594`；`docs/backend-vnext/contracts/ordered-diff.md:313`；handoff 的实现说明与计数声明。

满足 `_can_table_early_exit` 后，代码只读取 current，随后将同一个 `current_rows` 同时作为 before/current 传入通用 `_build_fact`。该函数仍构造两侧 key map、逐键逐列比较、调用 `_backbone_indices`，执行 blank 双侧处理，分别调用两次 `_ordered_digest`。因此只实现了“不读基线”，没有实现 DC55 第 1 项、设计 §4.1/§4.2 和 Ordered Diff 明文要求的“不运行完整比较算法（LIS、记录生成）/单侧摘要计算一次”。

独立复核：05、V、2026-10-27T13:19:19Z–13:19:22Z，在现有 `test_unchanged_ordered_history_reads_current_side_and_preserves_facts` 外用 `unittest.mock.patch` 包装 `_build_fact` 与 `_backbone_indices`，仅计数、继续调用原函数。记录 `before_rows is current_rows` 的分支：`same_rows_build_fact=2`、`same_rows_lis=2`；原测试仍通过。两次包含测试的 oracle 调用，故不能理解为一次产品请求运行两次 LIS；但它证明该优化分支确实运行 LIS。日志：05 `L/review-ordered-insert-probes-20261027.log`。

影响：原样重传和大量 U ordered 表仍承担被 S1a 明确要求移除的行比较成本；“kernel ≤ |X|”不能只以 before reader 未打开来证明。结果相等不等于结构性门槛成立。

建议：保持现有两侧描述符、有效 pair policy、规范 provenance、schema/read degraded 分支；专门构造相同两侧的 facts，只编码/计算当前侧 ordered 和 occupancy 一次，填入原 facts 结构。不得改用新增/删除入口 `_compare_single_side`。在现有 ordered 测试 owner 中证明事实与普通双侧路径相同，且 U 不调用完整比较/LIS；不增加生产探针或新持久机制。

### F2 — 阻塞：INSERT 的 4 MiB 单语句上限没有被执行

位置：`B/capabilities/mutation_planning/_repository_replay_renderer.py:164`、`:183`–`:215`；handoff `:77`。

INSERT 分支把一行 append 到 pending batch 后，达到字节门槛就 flush，但 flush 不拒绝超限单行；批字节数又不包含最后的 `;\n`。UPDATE/DELETE 的 `_render_limited_mutation_batches` 会在单行超限时稳定失败，INSERT 没有同等约束。总包 200 MiB 检查不能替代单语句 4 MiB 检查。

独立复核：同一 05 日志中，以合法 `insert_mutation()` 的 after-image 将 `status` 换为长度 `4*1024*1024` 的 string canonical cell，经公开 `render_change_set_replay(change_set_closure(...))` 渲染，得到 **`READY`、4,194,375 字节**；冻结上限是 4,194,304 字节。此探针只用合成字符串，没有真实数据或 Dolt 写入。

该 INSERT 缺陷在区间起点已有，但本阶段明确复测并冻结 INSERT/UPDATE/DELETE 的批规则，且 handoff 宣称三者均不超限，因此属于本次退出范围。现有 257 行测试、UPDATE/DELETE 字节拆分测试和预检的“接近 4 MiB”样本均不能覆盖 INSERT 单行超限及终止符边界。

建议：按完整 UTF-8 SQL（prefix、分隔符、值、终止符）计数，先判定可否加入批次；单行无法装入时返回既有资源超限错误，不发布部分 SQL。补足 INSERT 恰好上限/超限的行为测试。把三种语句的最终冻结规则同步写入 owning Storage Mutation Contract，S4 以修订后的最终候选产物为字节基准。

### F3 — 阻塞：DC58 报告尚未覆盖声明的全部内容保值范围

位置：handoff `:45`、`:49`–`:52`；05 `L/compare-dc58-masked-final.py:35`、`:55`、`:174`、`:273`–`:285`；`05-dc58-masked-final-existing-t1-and-golden-20261027.json`。

本次独立重用脚本函数，重新读取原 t1 两组 volume，复现了 v1 Preview 330、v2 Preview 9、History 8 个 bundle closure 产物的零差异和零 unresolved。72 个 golden 文件中的 16 处非摘要差异也能对应已批准变更。这些子结论可信。

但脚本的实际入口只比较保存的 journey state、上述三组 bundle closure，以及 golden 文件。它没有沿 materialize checkpoint/规范表 closure 读取 t1 的 snapshot-materialization descriptors 与表产物。报告中的 bundle kinds 是 RECORDS、RECORDS_MANIFEST、RECORDS_CLOSURE、RISK_ANNOTATION、RISK_ANNOTATION_MANIFEST、SURFACE、OTHER；抽查 OTHER 是 ordered record manifest，并非 snapshot table。保存的 `v1/v2-repository-read` 只有 catalog 字节数、表/行计数和 pseudo-row 计数等汇总，没有导出表内容。因此这些结果不足以推出 DC58 要求的“snapshot-materialization 内容在 t1 上也相同”和 handoff 所称“仓库读取/导出响应内容”已比较。

屏蔽规则也比授权的三类字段更宽：DTO 中任何 `_id` 均被删除，JSON 中任何 64 位 hex 字符串均被删除，不检查它是不是摘要字段。本次在 05 用脚本原 `normalize` 函数验证：`business_project_id` 从 `project-a` 改为 `project-b` 仍相等；业务 `value` 从 64 个 `a` 改成 64 个 `b`，在 artifact 模式下也相等。这是比较方法的假阴性，**不是声称真实 t1 已发生这些业务变化**。脚本的嵌套引用检查是“ID 在已读 closure 索引内”，不应表述为对所有 checkpoint/导出引用做了递归内容核对。

建议：使用同一已保存的 baseline/candidate t1 证据，补足实际 snapshot-materialization 与必要导出/事实产物的按逻辑角色内容比较；若某角色没有独立产物，明确其真实载体和比较位置。把屏蔽收敛到已识别的摘要、派生引用和运行实例字段，或列出实际被屏蔽字段并证明没有覆盖业务内容。缺失载体不能用行数相同或 golden 相同替代。无需为此创建生产 evidence 系统；一份范围明确、可复核的离线报告即可。

### N1 — 非阻塞：handoff 若干数字、时间、路径和 image ID 抄录不符

位置：handoff `:75`、`:79`–`:81`、“权威 runner 与容器门禁”。以下均以指定节点原文件为准：

| 项目 | handoff | 独立读取原证据 |
| --- | --- | --- |
| ec689 预检 UTC | 23:59:29–00:00:24 | 2026-10-27 00:02:05–00:03:01 |
| 预检 report 目录 | `05-dc57-preflight-dolt-ec689eda0a/` | `05-dc57-preflight-dolt-ec689eda0a-20261027/`；前者不存在 |
| 1% patch/rebuild 中位秒 | 0.605835 / 1.235459 | 0.614698 / 1.221495 |
| 1,000 行 adaptive/rebuild 秒 | 1.277966 / 1.252483 | 1.287732 / 1.242391 |
| t4 v2 adaptive/rebuild 总秒 | 2.514646 / 27.384033 | 2.536123 / 27.481748 |
| 04 RS image ID 尾部 | `...6e94ee9` | `...6e94ee4` |

依据是 05 预检 log/report、ct108 `ct108-af559-mutation-replay-20261027.json`、04 image build log 与 `docker image inspect`。实际 1% patch 仍快约 49.7%，三轮 hash_equal 都为 true，312/312 结论不变，因此不另阻塞阈值决策。建议修订文档引用，保留原始证据，不静默改写日志。

### N2 — 非阻塞：清理清单漏掉目录外的 stall 诊断产物

位置：handoff“过程记录”“需要 owner 后续清理的内容”；ct108 `L/ct108-af559-journey-v1preview-v2preview-20261027.log`。

失败旅程明确记录诊断目录 `/home/dev/gdds-p6-logs/s4-stall-20261027T091815873258Z`。它不在 `L/` 下，也不在 handoff 列出的真实数据 run 目录中，现有清理清单的 glob 未覆盖。建议补列此路径及实际存在的同类本轮诊断目录，仍由 owner 决定清理。此处没有执行删除、停止容器或移动 ref。

## 3. 逐项核对记录

| 核对项 | 复核与判定 |
| --- | --- |
| DC58 快照 preimage | `_digest.py:111`、`:166` 每表只有表名、compare schema、business schema、compare keys、row_count、raw_content_digest。upload、Repository-ref、compose 最终调用同一 snapshot 算法。`CanonicalBinding` 不含 snapshot_digest，Repository-ref 不采用提交摘要替代计算。通过。 |
| row-free/rowful | `repository_ref.py:213`–`:250` 从完整 catalog/manifest 构造未选中描述；选中行数/content 对 manifest 校验。`test_rowless_descriptor_matches_rowful_descriptor` 的 single_key、composite_key、keyless、ordered、zero_rows 五种逐字段相等与 snapshot 相等断言，本次全部复跑通过。限定为当前受信 canonical 数据边界，不要求从无行 metadata 推断任意损坏行的诊断。 |
| fast/order digest 删除 | `rg -n 'fast_row_digest|fast_row_hash|ordering_digest' vnext` 无匹配，涵盖实现、测试、序列化和 fixtures；active snapshot Contract 已移除 fast 字段。历史计划/决议叙述中的名称不是兼容实现。通过。 |
| raw_state 保留 | `_digest.py:142` 只含表名、行数、raw_content_digest，和包含 schema 的 canonical state 不重复；materialize、compose、repository_ref 仍生产，snapshot/checkpoint/source 绑定仍消费。保留有理由。 |
| 完整结构过滤 | Preview `_changed_canonical_tables`、History `_history_requested_tables`、comparison `_can_table_early_exit` 与 Submit `_manifest_table_identity_equal` 核对 content、schema、storage view、projection version，并校验行数；零行不只比 content。source schema 与 canonical schema 各保留其职责。未发现只按行摘要短路的新增路径。 |
| 基线消费者 | 沿 materialize→checkpoint→pair→surface/bundle 检查 version_manager identity、composite、DATASET_REPLACEMENT、删除表、恢复及 Submit 独立 parent 读取；当前侧复用仅在完整身份相等时发生。focused 覆盖未变零读取、X∪D 选择、identity/replacement 和 checkpoint 恢复。未发现 handoff 盘点之外仍强制读取全部 baseline 的消费者。 |
| ordered 输入与 facts | 保留双侧 descriptors/storage facts 构造 pair policy；current 来自当前 pair 的 artifact reader，FULL Preview 两个 pair 没有统一错误地取 MODIFIED；History 按相邻节点累加请求。CANONICAL_PSEUDO_GID、schema diagnostics、读取异常 degraded 路径保留，未复用 `_compare_single_side`。但计算路径不合格，见 F1。 |
| Submit policy/parent/checkpoint | T1、payload、domain/control schema 均切到 ADAPTIVE_PATCH；1,000/1% 用 Decimal 精确比例；GID_NO_V1 以 gid 为 key/no 为普通值；keyless、schema/projection 变化重建。`import_publication.py:309` 经 RS provider 读取可 patch 的 parent，Repository-ref 验证 manifest 行数/content，再组装 mutation snapshot；prepare checkpoint 绑定 parent digest/INITIAL 并在复用时核对。focused 通过。缺失权威 metadata 由 ADR 0019 稳定拒绝，不引入旧 metadata 兼容路径。 |
| Submit 表级输出 | 未变表不建变化集，不进入 replay；rebuild schema/DROP 在前，随后按规划的 DELETE→UPDATE→INSERT，包 manifest 仍是全部目标表。删除表由 schema replay DROP，rebuild deletes 被省去。相关发布/prepare/reuse 测试通过。 |
| CASE/DELETE 渲染 | CASE 的各 WHEN 使用完整 canonical key，非 key 列使用 after-image，ELSE 保留原列；NULL 经 `_render_literal` 为 SQL NULL，binary/decimal/日期等沿用类型编码。复合 DELETE 使用元组 IN，批身份含表/键/列，257 行测试证明边界和顺序。UPDATE/DELETE 完整语句字节检查存在；INSERT 失败，见 F2。现有 Dolt 合成预检主要是非空 integer/LONGTEXT，不能将它扩张表述成所有 NULL/类型组合都做过实际 Dolt 差分。 |
| owning 文档 | Canonical Storage 3.4.0/projection 3、Storage Mutation、Ordered Diff、ADR 0014、ADR 0019、snapshot-materialization 均写入主要目标语义，无双读写/旧字段 alias。Ordered Diff 已明文禁 LIS，故 F1 是实现与 Contract 不符；完整批量冻结规则宜按 F2 收口进 Storage Mutation。 |
| golden 范围 | `git diff --numstat ... -- vnext/fixtures` 共 23 个文件：mutation 12、snapshot-materialization 5、storage-projection 6；无其他组变化。屏蔽后的 16 个差异文件是 7 个阈值 closure、5 个 SQL、4 个 projection/contract 版本文档，逐项对应 §4.1/§4.3/DC57/DC59；不是 16 个额外未知差异。其余内容保值范围受 F3 限制。 |
| RS 日志 | `arrow_bridge.py:457` 只记录类型名和 `str(exc)`，不拼接 batch/row、不开 traceback locals。生产 provider 将底层流错误映射为稳定错误，`SqlValueConversionError` 消息只含表/列/SQL type。现有日志测试与原 abort 测试本次 2 项通过；没有发现新增显式行数据日志。 |
| §16.2 | 手算与 focused：1,000→1,002 行新增 2 行，2/1,002<1%，INSERT 2；改键 DELETE+INSERT=2；100 行改 6 行超过 1%，重建写 100；新增表写 n，删除表 DROP/写 0。Preview 只读 X∪D，History X 两侧、D old、U ordered current 的选择测试通过。单次去重/跨操作缓存属于后续阶段，不能把未来 H3 零调用当成本轮已实现。U ordered 零完整比较尚未成立，见 F1。 |
| 归因 | 独立读 V5b JSON、worker timing、RS summary、control timeline，并核对 `WorkerRuntime` 非 drain 等待没有观察 completed event。v1 差额 178.899088s、v2 70.969090s 的阶段分解算术成立；checkpoint、pair、bundle、prepare、RS wait、step 间隔、harness verification 均有处理阶段与 owner。按 DC59，环境/存储造成同代码速度差的根因留给 S1b/S3，不新增 S1a 阻塞。 |

16 个屏蔽后差异文件的逐项映射如下。路径相对 `vnext/fixtures/golden/`；M 指 `mutation/renderer/`，P 指 `storage-projection/`。这里认可的是下列可解释变更，不认可 F3 中屏蔽器对任意业务字段的宽泛豁免。

| 文件 | 已批准变化 |
| --- | --- |
| M`capability-failures/source-literal-anomaly/closure.json` | `max_patch_change_ratio` 0.05→0.01，DC57。 |
| M`valid/destructive-delete/closure.json` | 同上。 |
| M`valid/first-load-insert/closure.json` | 同上。 |
| M`valid/mixed-scalars/closure.json` | 同上。 |
| M`valid/multi-table-patch/closure.json` | 同上。 |
| M`valid/patch-single-update/closure.json` | 同上。 |
| M`valid/rebuild-replace-rows/closure.json` | 同上。 |
| M`valid/destructive-delete/expected.sql` | DELETE 元组 IN，§4.3/DC57。 |
| M`valid/mixed-scalars/expected.sql` | DELETE 元组 IN，§4.3/DC57。 |
| M`valid/multi-table-patch/expected.sql` | CASE UPDATE，§4.3/DC57。 |
| M`valid/patch-single-update/expected.sql` | CASE UPDATE，§4.3/DC57。 |
| M`valid/rebuild-replace-rows/expected.sql` | DELETE 元组 IN，§4.3/DC57。 |
| P`manifest/valid/s5-durable-roundtrip/document.json` | Contract 3.2.0→3.3.0、projection 2→3，§4.1；摘要/ordering 字段另按 DC58 核对。 |
| P`ruleset/malformed/s1-duplicate-selector/document.json` | projection 2→3，§4.1。 |
| P`ruleset/valid/s1-net-cfg/document.json` | 同上。 |
| P`ruleset/valid/s2-migrated-matrix/document.json` | 同上。 |

## 4. 证据来源与独立验证

### 4.1 本次执行的检查

05 静态与 focused 日志：`L/review-focused-static-af559-20261027.log`，2026-10-27T13:20:31Z–13:21:02Z，hostname `gw-dms-test-05`，起止 V，clean，exit 0。

```bash
# 节点 05，/home/dev/gdds-p6-logs/s1a/final-af559-wt
export TMPDIR=/home/dev/gdds-test-tmp
export PYTHONDONTWRITEBYTECODE=1
for package in shared_kernel repository_contracts repository_client backend repository_service; do
  ./vnext/scripts/uv-consume.sh -C "vnext/$package" run --no-sync ruff check .
  ./vnext/scripts/uv-consume.sh -C "vnext/$package" run --no-sync mypy
done
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -n 0 \
  tests/test_repository_ref_materialization_protocol.py \
  tests/test_repository_ref_materialization_digest.py \
  tests/test_canonical_snapshot_identity.py tests/test_canonical_state_identity.py \
  tests/test_dolt_renderer.py tests/test_mutation_planning.py \
  tests/test_preview_job_materialize.py tests/test_preview_job_assemble.py \
  tests/test_history_compare_jobs.py tests/test_submit_job_prepare.py \
  tests/test_submit_import_builder.py
./vnext/scripts/uv-consume.sh -C vnext/repository_service run --no-sync pytest -q -n 0 \
  tests/test_versioned_read_arrow_bridge.py -k worker_failure
```

结果：五包 Ruff/mypy 通过；backend **189 passed**（27.93s），RS **2 passed / 30 deselected**（0.07s）。一个现有 Starlette/httpx 弃用 warning。没有锁文件漂移，也没有 Rust 改动/编译需求。

F1/F2 探针同样经 `uv-consume.sh -C . run --no-sync python -` 在 05 的 backend 目录运行。F1 对现有 History 测试的两个函数包装只增加计数，原实现照常执行；临时目录使用 `tempfile.mkdtemp(prefix='s1a-review-ordered-')`，保留未删除。F2 的关键构造可复核如下：

```python
mutation = insert_mutation()
image = PersistedRowImage(columns=tuple(
    (name, {"kind": "string", "text": "x" * (4 * 1024 * 1024)})
    if name == "status" else (name, cell)
    for name, cell in mutation.after_image.columns
))
out = render_change_set_replay(change_set_closure(
    mutations=(replace(mutation, after_image=image),)
))
# 实测 out.status == "READY", len(out.sql_bytes) == 4194375
```

本次另用 Python 标准库只读解析各节点日志/JSON；DC58 脚本通过 AST 仅加载 import、常量和函数，避免执行其写 report 的顶层代码，再调用原 `compare_bundle`/`normalize`。未更改原证据脚本或报告。t1 v1/v2 的 `canonical_business_digest` 还直接逐值比较，baseline/candidate 分别相同，不依赖屏蔽器。

### 4.2 候选已有证据

以下原日志均独立打开并核对 HEAD、hostname、时间、退出状态/报告；没有把旧候选的失败或诊断分支结果算成 V 的门禁。

| 节点 | 证据（均在 L 下，除注明者） | 核验结果 |
| --- | --- | --- |
| 04 | `04-af559-six-package-runner-20261027.log` | 05:04:39–05:43:18 UTC；起止 V、dirty entries 0、exit 0；Rust fmt/clippy/test，shared_kernel 242、contracts 152、client 154、backend 2940+39、RS 1741（1 skip）+206。 |
| 04 | `04-af559-rs-image-20261027.log` | V 下重建，exit 0；revision V；实际 ID `sha256:14c4dde24fa90208869cf442f52ab381532efa6c277963bbbbba8b3cc6e94ee4`。 |
| 05 | `05-af559-t1-candidate-journey-20261027.log` | V，05:22:37–05:27:38，exit 0。 |
| 05 | `05-af559-t2-full-journey-20261027.log` | V，05:31:02–06:06:07，exit 0。 |
| 05 | `05-af559-t3-full-journey-20261027.log` | V，06:37:56–07:47:06，exit 0。 |
| ct108 | `ct108-af559-t4-full-journey-20261027.log` | V，05:10:27–06:40:01，exit 0；重复提交 NO_CANONICAL_CHANGE；v2 26/312 comparison changed、History 168 records。 |
| ct108 | `ct108-af559-mutation-replay-20261027.log` / `.json` | V，06:45:15–07:16:22，exit 0；98 净变化三轮 hash_equal；312/312 adaptive/full/current hash 等价；repository_main_unchanged=true。真实 storage X∪D=27 与 comparison changed=26 不是同一计数口径。 |
| ct108 | `ct108-af559-v5b-segments-20261027.log` / `.json` | 起止 V，07:17:34–07:55:56，exit 0；312 表全 baseline 与 27 表 selected baseline、pair/records/risk/surface/bundle、Submit build-input/checkpoint 段均有证据。 |
| 05 | `05-dc57-preflight-ec689eda0a-20261027.log`，真实 report 路径见 N1 | Dolt 2.1.11，ec689 语句形式预检 PASS；单键/复合键/gid，三种候选形式哈希与 modified 计数一致，等价 SELECT 谓词为 IndexedTableAccess。它是早期选型证据，不能代替 V 的最终阈值和 hash 重测。 |

04 原 manifest 的环境为 CPython 3.14.6、uv 0.11.28、Dolt 2.1.11、rustc 1.97.0、Docker 29.9.1、Compose 5.6.0；Hypothesis 为规定的逐包外部路径，Rust target 在 worktree 外并由 runner 清理，符合 DC48 门禁环境记录。

阈值 benchmark 源码已核对：先 `docker cp` 到 scratch repository-copy，再在独立回放容器操作；parent 通过 RS HTTP Arrow 读取，原 main 前后相等。不把当前 RS 仓库当 scratch；没有要求新增条件 DML/affected-row/readback 机制。

### 4.3 诊断分支与归因

`git diff --stat af559ae3d2..e52ad2c48b` 恰好九文件：pair_pipeline、preview_jobs、submit_jobs、bundle `_assembly`、comparison `artifacts`、新增 `diagnostic_timing`、import_publication、lease_session、worker_runtime。逐文件查看普通及 `-w` diff，变化为 timing span/event、perf counter、context IDs、表/行/artifact 数和为计时提取局部变量；没有产品策略、SQL、RS、golden、锁文件或部署变更。该分支不在 H 的产品历史内，不合入。

ct108 `ct108-timing-diag-full-t4-e52ad2-retry2-20261027.log` 起止 e52ad2，10:24:18–11:53:26 UTC，exit 0。独立读取 `ct108-timing-diag-worker-e52ad2-20261027.log`、`ct108-timing-diag-rs-summary-e52ad2-20261027.log`、`ct108-timing-diag-control-timeline-e52ad2-20261027.log`：

- v1 assemble：45.110388 + 625.543636 + 51.392878 + 0.999274 = 723.046176s；V5b pair+bundle=544.147088s，差额 178.899088s。
- v2 assemble：58.655686 + 49.334631 + 2.442234 + 0.763653 = 111.196204s；V5b pair+bundle=40.227114s，差额 70.969090s。
- v2 parent rows 为 25 表/129,426 行/90.520259s，plan/render 36.356887s；与 V5b 的 27 表 X∪D 测量不可直接混为相同读取任务。
- step 间隔与非 drain supervisor 的 heartbeat 等待吻合；不能把 heartbeat 并行累计 CPU/事务耗时相加当成 wall residual。
- RS summary 确有 37 次 join timeout warning、526 个 rows 200 响应；缺少逐请求 close duration，handoff 没有把 37×30s 当成串行耗时，处理正确。

对 handoff 的后续登记逐项核对如下；这些是已登记的处理责任，并非本次审核新增实现计划。

| 阶段项 | 处理方案、阶段与 owner |
| --- | --- |
| 上传解析及 snapshot 物化 | 减少多次全表遍历/摘要；S2b/S3；backend ingestion、canonical snapshot/compute owner。 |
| v1/v2 checkpoint 45.110s/58.656s | 优化 checkpoint 与 artifact 读取；S1b；backend artifact/checkpoint owner。V5b 不含此段。 |
| pair 差额 124.681s/11.112s | 按 compare、records、risk、surface 分段复测环境/存储/调度差异；S3；backend comparison/compute owner。尚未证实具体环境根因。 |
| bundle 差额 8.109s/0.438s 与 finish | 检查重复扫描、读回与 I/O；S1b；backend artifact/checkpoint owner。不能仅凭 scratch/volume 不同认定原因。 |
| Submit frozen input/projection/snapshot | 减少冻结输入重复读取和物化；S2b；Submit/backend mutation、snapshot owner。 |
| v2 plan/render 36.357s、parent 90.520s | 优化渲染与按表批处理、Arrow 吞吐/关闭；S2b；mutation renderer、Repository Service owner；保留阈值及 parent 校验。 |
| RS 异步 import 等待 | 优化 Dolt 回放，保留 await/retry/lease 语义；后续 RS 性能阶段；Repository Service/Dolt owner。 |
| step 间隔 2.6–9.95s | executor 完成唤醒 supervisor，保留 heartbeat/drain/lease；后续 worker runtime/performance 阶段；backend Worker Runtime/Operations owner。 |
| 操作间 repository verification 75–76s、2s poll | 分开展示 verification 与 operation elapsed，保留校验；benchmark harness 阶段；性能测量工具 owner。 |
| heartbeat 与 Arrow close warning | 不把并行 heartbeat 累加为 residual；补单请求关闭计时再量化 warning 占比；后续 RS 性能诊断；RS owner。 |

DC59 只要求阶段级归因，上述登记满足该决议。正式性能数字仍取 V；诊断栈和候选保留栈并存的事实不提供“诊断环境与正式环境完全相同”的证明，本报告也不作此声明。

## 5. Carried 判定

**通过，限定 V→H 的阶段退出证据沿用；不等于 S1a 已获退出批准。**

在 04 原 runner worktree `L/final-af559-wt`（不是另一个 worktree）确认空闲、clean 后，从本地 bundle 导入 H，`git checkout --detach 26c066e9bb`。只切换五份文档，没有修改产品或重建/重 tag 镜像。保留在 H，未恢复或清理 worktree。

从原 runner 日志的 `==> test input manifest package=...` 后解析完整 JSON，保存为 `review-source-{package}-af559.json`，没有重算来源 manifest。使用来源环境的 `TMPDIR`、PATH（加 `/home/dev/.cargo/bin`）、`LC_ALL=C.UTF-8`、runner 自设的 `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`，每包设置与来源相同的 `HYPOTHESIS_STORAGE_DIRECTORY` 并断言不存在，然后执行：

```bash
python3 -I vnext/scripts/test_input_closure.py manifest --package "$package" \
  > /home/dev/gdds-p6-logs/s1a/review-current-$package-26c066.json
python3 -I vnext/scripts/test_input_closure.py compare \
  --source /home/dev/gdds-p6-logs/s1a/review-source-$package-af559.json \
  --current /home/dev/gdds-p6-logs/s1a/review-current-$package-26c066.json
python3 -I vnext/repository_service/tests/support/build_context_digest.py identity
docker image inspect gateway-repository-service:local --format '{{json .Config.Labels}}'
```

| 包 | V 与 H 相同的 total_digest | compare |
| --- | --- | --- |
| backend | `4b75bd6eac952aa415290827f807a52eb1451628bb24f5799033bb5442e80b8d` | 可沿用；changed_components=[] |
| repository_service | `a814c6b62db3f02973245d13b4e835a5239b494315e5be76cb658f9efda8d3d4` | 可沿用；changed_components=[] |

RS 重算与镜像标签一致：build-input `085b54ffdc746d2ea3b7ccd1a610c629ddd4d28a`，source-tree `sha256:fddb1e93d98fcd8ca9798aeb62abbbd8670ee9bafe0829e7caca8a08e25b2209`，最后实际验证的 image revision 为 V。未按两次构建 image ID 是否相同作判断。

证据：04 `L/review-carried-26c066-20261027.log`，13:18:15–13:18:19 UTC，命令 exit 0，起止 H、clean；另有 `review-compare-{backend,repository_service}-26c066.json`。因此不触发本轮文档审核镜像重建；来源直接引用 V 的权威 runner，不链式引用另一份 carried。后续 F1/F2 产品修订必须重新判断受影响闭包及容器证据，不能提前沿用本次结果到未知提交。

## 6. 过程记录、保留物与退出建议

真实数据未写入本报告或本次 Git 提交。审核区间新增/变更的 SQL 文件仅为五个 mutation golden expected.sql；未发现导入真实 dump、database、Parquet 或压缩源包的提交。业务表名、计数及耗时属于已有验收报告信息，不复制行值。

旧 run3/run4 JSON 确认 RepositoryProviderError/RepositoryStreamError 失败，后续 benchmark diff 确认改用副本回放。仅凭这两份错误摘要不能独立证明当时所有文件的 UID 历史；root 污染的因果解释记为实现方事故记录，与修复代码及后续成功一致，不冒充本次重新制造/证明的事故。handoff 先删除再重建是作者主动披露的操作偏差，最终 Git 树不能还原未提交的删除步骤；本次没有复做。py-spy 原日志中 287.60s、358.48s 均存在，旅程 worker_stalled 且 exit 1，排除作为性能验收正确。

handoff 的 stacks/volumes、worktrees/refs/bundles、Dolt scratch 清单覆盖主要对象，但有 N2 漏项，不能宣称完整。所有原对象保留；本次新增保留物如下，交 owner 在 DC51 时点处理：

- 开发机两个审核/报告 worktree、`p6-s1a-review` 分支；`L/review-handoff-20261027.bundle`（开发机及 04 副本）。
- 04 上述 carried/source/current/compare JSON/log；原门禁 worktree 当前 HEAD 为 H。
- 05 `review-focused-static-af559-20261027.log`、`review-ordered-insert-probes-20261027.log`，以及 `/home/dev/gdds-test-tmp/s1a-review-ordered-*` 合成测试目录；focused 的普通测试缓存/临时目录保留。

**exit tag 建议：目前不创建 `p6-s1a-exit`，不指向 af559、26c066 或 e52ad2。** 实现方关闭 F1/F2，补齐 F3 并复审通过后，将修订候选、准确 handoff 和本报告/复审结果合入 main；在该最终接受的 main 提交上创建附注 tag `p6-s1a-exit`。先按 AGENTS 对最终对象完成必要门禁及 carried 判定；诊断分支始终排除。本次仅提交审核报告，不替 owner 接受阶段、不移动阶段 ref、不推送。
