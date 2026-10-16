# P5 架构收口 S2b handoff

- 状态：**完成候选，待独立复审。S2b.8（DC29）、S2b.9（DC31）与第一轮审核修订已完成；门禁 V 通过。真实数据按 owner 确认沿用 b0175cf583 取证。**
- 日期：2026-10-16
- 分支 / worktree：p5-s2b / /home/dev/gdds-p5-s2b
- range_start：p5-s2a-exit，6f3e2ed67a03a2c452c7a13ff02d3aeb7d0f6792
- kickoff base：cae9a0f82be3415cc362e46b98da954edcf1d807
- 最后非 handoff 提交（实现 HEAD）及门禁提交 V：`753c5768a533885b5e0af0865cfe28c62df3ce27`
- handoff-only 候选 H：本文最终提交。V..H 仅包含本 handoff 文档提交。
- carried：待 handoff 草案提交后，在同一 worktree 按 §8.10 完成并记录到最终 H。
- main 上 kickoff 后的审核方文档提交不进入 p5-s2b，按提交区分：62cc7c3e0f（DC29）、1925dcedc2（DC30）、5a1a391ea8、92db9df18e（DC31）、a889acc242（Catalog 离线估算补充）。

## 1. 区间与提交

`p5-s2a-exit..HEAD` 中 kickoff 前的审核方文档提交按区间核验时应与实现提交区分：

| 提交 | 说明 |
| --- | --- |
| `0ce71cac2743ab71c8c4adc7eaa597821996edd3` | 合并 S2a |
| `a80ca8c4020da26a01a285977dae402b77f69aa1` | S2a exit 记录 |
| `cae9a0f82be3415cc362e46b98da954edcf1d807` | S2b 预算文档修订；kickoff base |

Kickoff 后的审核方文档仅存在于 main，不在 p5-s2b 分支：62cc7c3e0f（DC29）、1925dcedc2（DC30）、5a1a391ea8、92db9df18e（DC31）、a889acc242（DC31 离线 Catalog 估算补充）。实施按这些 main 文本执行；规格与决议记录没有复制或修改。

| 内容项 | 主提交 | 后续实现、修复或验证提交 |
| --- | --- | --- |
| S2a 携带 F1/F2：投影负零规范化；同一 Repository Service 启动覆盖 INT UNSIGNED、BIGINT、FLOAT 与 canonical state digest | `26560b25956db49e809dfcf5a91a0f7f9897d61a` | — |
| S2b.0：Preview/History 受理下沉、按 owner 拆 control transaction port、共享 job step plumbing | `062bf7ec65833fce409b163f42b0002ba95c6ab1` | S1-F3 关闭标准由实现结构与全量 owner 测试核对 |
| S2b.1：commit canonical metadata port、SQLite adapter、control DB 基线 | `9d2537c329b5220ce78249858c95004d0ac57ead` | — |
| S2b.2：Repository canonical binding、单遍读取、普通行数失败、传输 adapter 收窄 | `ee2205dc7d01a84ca077ce993d42b63bc0d62aad` | — |
| S2b.3：Preview 上传规范投影、PreviewResult 规范闭包 / manifest / 双侧摘要 / ruleset digest、INITIAL 空断言 | `a8fb1ba90276c347ca50581290d21f136ab6a70c` | — |
| S2b.4：AcceptSubmit 陈旧与摘要判定、冻结 T1 闭包并按闭包转移保护、删除基线自比和启发式 | `0f2fb68e7930ef87c21cafb32f58e99fed8452b8` | — |
| S2b.5：prepare 冻结 parent catalog、`removed_tables`、infrastructure publication adapter、prepare checkpoint 复用 | `90e7f907598f255d120c482e495c0e9fcbf1d8eb` | `98ec2b3637f4be4aa7e4808e304f045e2e0967e1` 修正 frozen manifest 复用；`5412e008661cf92353bf6db9d62196acb30a4311` 修正 reused snapshot reader 重开 |
| S2b.6：DC9 History incident 删除与 HTTP/OpenAPI、DC19、DC6 基线 schema | `91f68c08fbda6534bb94ae984f41b83936ab78db` | — |
| S2b.7：空 INITIAL 的 Compose 旅程与 NO_CANONICAL_CHANGE 唯一 owner | `4bf531449519e98d39cda89cd7c32628e9dd5838` | `b3d024703c1e7b6adb790db086b12f99e47b34f3` provenance 输出移出 worktree；`d36947dcfa733f325913638aac7b664dd0aaf989`、`056e9403d04f38a39c307172f834ac203fe81382`、`cffed3d0148db652c238fb1533cfe51f23707ea6`、`e0c44efb9899b2856c711666a9996cd9f5a5f080`、`e6447606e2abcefee0291b299ee9ce55ddbd1db7`、`cffda95d67d0e4195762774e188bae95a31bc1b6`、`7bd3a9e96bca8f263be2a84ac45002e3a87cf1a6` 修正 Compose fixture/oracle 的冻结输入和 Preview artifact 读取 |
| 主机侧真实数据 journey | `f83b8ec69762aaf4a572d27b85eca53c5f3d6da5` | `eb054e8566c38dc7d095e124d0a113c442c45478` 对齐 census package 布局 |
| 门禁回归修复 | `08a8d9876bf2d347dd36cf8db4fac3d615306496` | 修复 archive fixture、reader 合约、Compose unsupported-table 旅程预期与 HTTP digest 断言 |
| 真实数据暴露的比较 KEYLESS / 存储显式键缺陷 | `acbf865142382b63f57fd8c01a12721137f0c79b` | 仅对该提交跑了 focused 与静态检查；未跑新 V 的全量门禁 |

| S2b.9 DC31：Catalog 容量、超限错误与 PURE_RECOMPUTE 读取失败终态 | 34ec9ef6f2c0a97c3b359788642d1cb1b603eb43 | `adc5d87fea` 将 serial gate 的屏障拦截点从 `commit_exists` 移到 `catalog_at`；此前 `09c3e8c217` 加入 Catalog 缓存后已不再调用 `commit_exists`。随后 `cbd4b8df94`、`488c4975f2`、`b0175cf583` 只改 benchmark / real-dump tests |
| V timeout measurement / public-result baseline | 488c4975f2 | b0175cf583 按首次完整带时间戳运行设置五倍保护超时；两次 post-V 完整 real-data 运行均在最终 V 的兼容实现上复核 |
| 第一轮审核 S2b-F1：所有能力的有效 RUNNING 租约均阻断 startup，过期后保留 R5 处置 | `e94008889c` 审核 Finding | `d450f946bf`；参数表覆盖三种能力的有效 / 过期租约与事务内复查竞态 |
| 第一轮审核 S2b-F2 / F4：组装取消发布 CANCELLED；确定性 Catalog 错误经 provider 与物化路径公开诊断 | `e94008889c` 审核 Findings | `4049986e4c`；三条取消路径与 RESPONSE_LIMIT_EXCEEDED 诊断用例 |
| Compose oracle 对齐新增取消回调 | `e94008889c` 审核 Finding 导致的完整 runner 调试修复 | `753c5768a5`；传入无副作用取消 callback，focused Compose 旅程通过 |

S2a-F3 的启发式删除与 S2b.4 一起完成。S1 拆出的 comparison 行编码能力路径在 S1 已迁移；本区间没有为其另建副本。S2b.0 是 S1 复审 S1-F3 的延期收口项。

路径预算外生产路径逐项登记如下；它们均是对应内容项或可复现真实数据 / 测试缺陷所需的局部改动，没有新增生产边界、规则基线条目或兼容路径：

| 路径 / 提交 | 预算外原因 |
| --- | --- |
| `capabilities/risk_evaluation/_engine.py` / `74db10e1fe` | 对行详情被抑制的比较结果保留表级风险计数，避免 DC29 keyless / 受限记录场景丢失已有计数事实。 |
| `capabilities/bundle_assembly/_assembly.py` / `91ad5affcc` | 缺失嵌入 artifact ref 时把父 logical path 带进失败诊断，修复 bundle closure 故障定位。 |
| `artifacts/store.py`、`infrastructure/artifact_store/{bounded_store,local_store}.py` / `9d2537c329` | S2b.1 canonical metadata manifest reader 需要按 artifact id 读取并验证已存 ref；仅增加对应 port 与 adapter forwarding。 |
| `capabilities/snapshot_materialization/{materialize,artifact}.py` / `a8fb1ba902`、`e37323e220` | 前者是 S2b.3 上传侧规范投影必需实现；后者复用已验证的 Parquet rows，修复 snapshot artifact 重开时重复完整读取。 |
| `capabilities/mutation_planning/{_planner,_repository_replay_renderer,contracts}.py` / `0c48314dbe`、`ce58301a4f` | DC29 keyless fallback 的写入规划与无行补丁的 replay；批量 INSERT 保留重复行并避免逐行写入。 |
| `capabilities/storage_projection/_ordered.py` / `041640eb7b` | 冻结 ordered pseudo 身份在投影与 replay 中保持一致，满足真实 IEC104 有序表行为。 |
| `capabilities/comparison/{ordered,row_encoding,contracts}.py` | DC29 keyless 集合差异、重复行一删一增以及 ordered pseudo 行编码 / 语义必须贯通比较能力契约。 |
| `capabilities/surface_assembly/*` | DC29 的 `KEYLESS_FALLBACK` 只读提示需进入 Preview surface，不引入风险或持久状态。 |

预算内的主机真实数据 runner、fixture / oracle 修复与 S2b.8 / S2b.9 内容项按 §2、§3 和后续修订记录执行。

## 2. 导入基线与依赖

`python -m tests.support.import_rules`：

| 时点 | 违例 / 运行时环 / 不可达 |
| --- | --- |
| S2a exit 基线 | 3 / 0 / 14 |
| 最终门禁 V `753c5768a5` | 0 / 0 / 14 |

`prepare-dev-dependencies.sh` 在新 worktree 完成；随后 worktree clean，`uv.lock` 未改。当前五锁 SHA-256：

| 包 | SHA-256 |
| --- | --- |
| shared_kernel | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| repository_contracts | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| repository_client | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| repository_service | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| backend | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |

## 3. 较早验证记录（最终 V 见 §8.4）

### 旧实现 HEAD `acbf...`（DC29 owner 决议前的停止版本）

命令：

- 五个 Python 包各运行 `../scripts/uv-consume.sh -C . run ruff check .` 与 `../scripts/uv-consume.sh -C . run mypy`：全部通过。
- `cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`：0 / 0 / 14。
- `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_storage_projection_core.py -q`：36 passed。

### 上一次完整权威 runner：V 候选 `08a8...`

命令：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；开始和结束 HEAD 均为 `08a8...`，status clean，预检确认无 Dolt 进程、无 Compose project 容器、8000 端口空闲；runner exit code **0**。日志及 provenance 文件名：`s2b-gate-08a8d9876b.log`、`s2b-gate-08a8d9876b-provenance.json`。

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2,779 passed，1 warning |
| repository_service 并行 | 1,681 passed，1 skipped |
| repository_service serial | 197 passed，1,682 deselected |
| Compose | 8 passed |

§2 S2b owner 均在该次全量运行中通过：`test_comparison_canonical_domain.py`、`test_repository_ref_materialization_protocol.py`、`test_preview_job_materialize.py`、`test_submit_transactions.py`、`test_commit_canonical_metadata.py`、`test_submit_artifact_protection.py`、integration `test_submit_prepare_removed_tables.py`、`test_submit_job_prepare.py` 与按表归属的 control DB schema tests。`NO_CANONICAL_CHANGE` 的权威断言仅在 `test_submit_transactions.py`。该 runner 同时覆盖 ADR 0016 Operation integrity 测试；本阶段没有改其测试语义。

这只是 `08a8...` 的事实：其后 `acbf...` 改了 production projection 与 host journey，因此不能将该 runner 记作最终 V 的验证，也没有用定向补跑代替新 V 的 runner。

### DC9 删除核对（代码区间）

- History compare incident 记录、pending-integrity 受理阻断、基线表与索引已删除。
- `integrity-ack` 路由、History integrity orchestration、对应 OpenAPI path 已删除；Operation / History DTO 的 `integrity_incident` 已删除。
- History compare job 的二次物化、incident 发布和对应错误 / 类型已删除；`MaterializationDiagnostic.expected_digest_ref/observed_digest_ref` 已删除。
- `test_history_compare_integrity.py` 与 hidden-summary tamper 支撑钩子已删除。
- `HistoryIntegrityFailure` 保留，仍由 History projection / query 一致性校验使用。
- `08a8...` 的完整 runner exit 0 是历史事实；其后的 DC9 代码由最终 V adc5 的完整 runner 重验，见 §8.4。

## 4. Golden、digest、checkpoint、DTO 与 OpenAPI

- Golden：storage-projection `manifest/valid/s5-durable-roundtrip/document.json`、ruleset malformed `s1-duplicate-selector` 与 valid `s1-net-cfg` / `s2-migrated-matrix` 共 4 项。四项里的 storage projection version 字段由 `26560b2595` 的 S2a-F1 负零归一从 1 升到 2；ruleset 由 v2 升到 v3。DC29 `0c48314dbe` 更新 `DDL_PRIMARY_KEY_OR_KEYLESS` 规则事实与 manifest contract 3.2.0，不负责 projection version 升级。mutation renderer first-load-insert SQL golden 另由 `ce58301a4f` 的批量 INSERT 语义更新。
- Digest 与 S2a-F1/F2：`test_canonical_snapshot_identity.py` 在一次 Repository Service 启动中补充 INT UNSIGNED、BIGINT 边界、FLOAT 常见值与次正规值、负零；`test_canonical_state_identity.py` 覆盖 `-0.0` 与 `0.0` 同摘要。`acbf...` 让完整源行内容在 comparison descriptor 为 KEYLESS 时仍可按 storage key 投影。
- Checkpoint：Preview / Submit 的规范表闭包与 manifest 绑定进入持久载荷；prepare package 与 attempt 绑定纳入允许键并复用。`0d9d0d9dc5` 的 attempt 绑定与 payload 不符即 FAILED 保留；无兼容 payload 别名。
- DTO / OpenAPI：HTTP History / Operation DTO 清除 DC9 字段；Preview 与 Submit 映射新规范事实、身份结论与失败码；OpenAPI 合同测试相应更新。
- Control DB：仅改 `infrastructure/control_db/schema.py` 单一基线，未增加 migration。

## 5. 历史停止事实（2026-10-12；已由 DC29 结案）

运行脚本：`vnext/backend/benchmarks/real_dump_journey.py`，主机侧通过公开 HTTP API；原始目录只读且不挂载到容器。权威的首次运行在 `08a8...` gate 后、同一提交、clean preflight 下开始；t1-v1 Preview 未完成，operation 失败为 `BINDING_INVALID`，日志文件名 `s2b-realdata-08a8d9876b.log`。随后为取到 stage/message 做了一次诊断重跑，运行前临时改过 host script，故该次 worktree dirty，不作为门禁或合规真实旅程证据；日志文件名 `s2b-realdata-diagnostic-08a8d9876b.log`。诊断完成后脚本不输出 operation message，仅保留 stage 与错误码。所有栈与 Dolt 均 teardown；没有完成 t1–t4 的 Submit / 重传 / History 有序表四项验收。

首个失败是已修复的投影缺陷：比较域因无比较键而给 descriptor 标记 `KEYLESS`，投影此前在应用 storage rules 前拒绝任何 degraded descriptor；`acbf...` 现仅拒绝 `TABLE_FAILED` 或缺少完整源内容，并允许 storage rule 使用显式键。该提交的 focused 测试与五包静态检查已通过。

修复后对同一 t1-v1 包的只读投影诊断继续发现 23 项 `KEY_MISSING`。生产 parser 对源 SQL 的状态为 COMPLETE，132 张源表中 104 张既有源 `PRIMARY KEY` 也被 parser 解析为主键；例如 `cnt_manage_cfg`、`comm_user_data`、`forwardtbl_lst_*`、`iec104_cfg`、`project`、`sc_cfg`、`wave_cfg` 等触发项在源 DDL 中没有 `PRIMARY KEY`。当前 ruleset 对这些实际参与规范存储的表要求 `DDL_PRIMARY_KEY`，因此不是 parser 漏读。

本次数据统计仅引用已接受 census 元数据：`rd-t1-a-v1`，package SHA-256 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`，107,115 bytes；132 张 source DDL 表、census 133 张物化表、总计 6,097 行。HTTP journey 在 Preview 阶段失败，后续项目级旅程与 IEC104 记录数量没有结果可报告。

停止原因：若继续必须由 owner 决定这些无主键表的规范键 / keyless 语义或规则处置，可能改变规范状态与比较语义。按本阶段真实数据停止规则暂停；没有猜测业务键、加 application 特判、排除数据或增加导入基线项。请 owner 决定允许的 canonical semantics 与规则更新范围；决定前不得形成最终 V/H、跑 carried 或宣称 S2b ready。

该停止由 owner 2026-10-12 的 DC29 决议解决，并在 §8.1 记录实施。之后的 DC30 Catalog / operation 阻断已按 DC31 恢复处理，见 §8.2–§8.4。

DC29、DC30 与 DC31 的 owner 文档和实施映射见 §8.1–§8.3；此处只保留 2026-10-12 停止经过，避免重复 §8.1。

## 6. 镜像与 carried

第一轮审核前 S2b.9 V `adc5d87fea073545fde6416d123c3d7845e715ff` 的旧 provenance 为 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-gate-adc5d87fea-provenance.json`，Compose project 为 `ordered-bisect-b-2918210-baseline`。修订后当前门禁 V 是 `753c5768a533885b5e0af0865cfe28c62df3ce27`；V 的镜像与 provenance 见下表和 §8.10。

| 镜像 | image ID | 标签 / provenance |
| --- | --- | --- |
| repository-service | `sha256:196148beb96d508ae634212c70f560bb9f6c739f9d589e42bad4b870947b1883` | provenance: `org.opencontainers.image.revision=753c5768a533885b5e0af0865cfe28c62df3ce27`; build-input revision `adc5d87fea073545fde6416d123c3d7845e715ff`; source-tree `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`; lock `sha256:6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| backend | `sha256:4c7dd9242d867e5eec9314fc6bc549f264127e38b72715e2a34c024f73f30ebd` | provenance project `ordered-bisect-b-4106342-baseline`; no build-input / source-tree label |
| worker | `sha256:f8b59e3d42ba299f4237d7dac8cbcc305b7fa00aac349ad033fae04653eb1100` | provenance project `ordered-bisect-b-4106342-baseline`; no build-input / source-tree label |

carried 待 handoff 草案提交后执行；identity、backend / worker 重建输出和日志将在 §8.10 记录。V provenance 文件为 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5-provenance.json`，镜像 inspect 为 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5-images.txt`。H 仅增加 handoff 文档，没有镜像输入变化。

## 7. Reviewer 核对重点与交付

本 handoff 是 S2b 完成候选，不是审核报告。实现方没有打 p5-s2b-exit、不向 main 合并、不推送。所有 S2b.9、DC29 / DC31 验收证据与本阶段原有 §2 验收都请审核方按 §8.9 提示词复核；停止条件没有触发。导入规则最终为 0 / 0 / 14。

## 8. DC29 / DC30 / DC31 恢复与第一轮审核修订（2026-10-16）

### 8.1 owner 文档与 DC29 实施

DC29 按 main 审核方文档提交 `62cc7c3e0fddf53349f2df9d30c64ed6fb44d4d6` 的决议 §12 实施；DC30 按 main 提交 `1925dcedc2835b7baa5a3f5860c865a2c16b86df` 的决议 §13 与执行计划 §8.9 执行。两提交都不在 `p5-s2b`，本阶段未修改 owning specs。

DC29 的主提交是 `0c48314dbe`：加入 `DDL_PRIMARY_KEY_OR_KEYLESS` 规则语义，保留无主键重复行，以 `FULL_ROW_DIGEST_SET_DIFF` 做 keyless 比较，增加 `KEYLESS_FALLBACK` 表级只读提示，并更新 manifest contract 到 3.2.0。storage projection version 实际在更早的 S2a-F1 提交 `26560b2595` 从 1 升到 2；DC29 没有再次变更它。其后相关修正为：

| 提交 | 内容 |
| --- | --- |
| `bdd83be525` | 保留 keyless 内容变化的一删一增记录 |
| `ae5998f13c`、`dd6be19b3e`、`4fe624e771`、`2cf35a8c54` | Compose keyless 旅程固定 archived baseline、变化 pair 选择与断言修正 |
| `f3a278427b` | History comparison 继续传递规范存储事实 |
| `041640eb7b`、`f541ef7846`、`e4defddb4f` | 有序 pseudo 身份、浮点 / datetime 单元格与 replay key 顺序规范化 |
| `ce58301a4f`、`d13c088e8e`、`24e7257266` | Repository replay 批量插入、重复行断言与对应 golden 更新 |
| `055ad724e5` | real-data Preview 记录 keyless fallback 候选 |
| `09c3e8c217`、`e37323e220` | 缓存 immutable catalog；打开 snapshot artifact 时复用验证得到的 Parquet rows，避免二次完整读取 |

其余 DC29 后续提交处理 History/Submit 闭包恢复、故障诊断、runner instrumentation 与超时剖面；提交列表见本 handoff 区间。没有新增 HTTP endpoint、运行时规则激活机制或导入基线条目。恢复后的最近验证批次为 `tests/test_real_dump_journey.py` **23 passed**，五包 ruff/mypy 全通过，`python -m tests.support.import_rules` 为 **0 / 0 / 14**；它们不是最终 V 的权威 runner。

最近验证命令均使用 `GATEWAY_DEV_OFFLINE=1 ../scripts/uv-consume.sh -C . run ...`。ruff 五包均为 `All checks passed`；mypy 分别为 backend 475、repository_service 198、repository_contracts 15、repository_client 26、shared_kernel 34 个 source files，全无 issue。测试为 `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest tests/test_real_dump_journey.py -q`，23 passed；导入规则命令输出 0 违例 / 0 运行时环 / 14 不可达。五个 `uv.lock` SHA 与 §2 表相同。

### 8.2 DC30 调试历史与 DC31 Catalog 离线估算

原 t4 调试栈已删除；按 owner 2026-10-15 的补充决议 a889acc242，不为测量而重建。离线脚本在进程内复用 real_dump_census.py 的投影路径，对 t3、t4 v1 投影后仅序列化 Catalog wire 模型中的表结构、主键与行数；不读取行数据，不经 Docker。t3 174,294 bytes 低于 256 KiB，t4 285,725 bytes 高于 256 KiB，按 DC31 判据确认旧 503 来自响应超限。合成 Catalog focused 用例 1 passed，证明旧实现超限时返回 `SERVICE_NOT_READY`。

| 输入 | 投影状态 | Catalog 表数 | Catalog JSON 字节 | 与旧 256 KiB（262,144 bytes）的关系 |
| --- | --- | ---: | ---: | --- |
| t3 v1 | COMPLETE | 191 | 174,294 | 低于 |
| t4 v1 | COMPLETE | 311 | 285,725 | 高于 |

证据日志：s2b-debug-catalog-estimate-t3-finalpath-668055f55e.log、s2b-debug-catalog-estimate-t4-finalpath-668055f55e.log。两者记录 projection COMPLETE 与 wire JSON 字节数。另在旧限制下执行合成 Catalog focused 用例，1 passed，证明原实现对超限回传 SERVICE_NOT_READY；日志 s2b-debug-catalog-legacy-limit-668055f55e.log。按 owner 给定判据，t3 低于、t4 高于 256 KiB，故确认先前 503 来自响应超限。

容量公式：285,725 × 4 = 1,142,900 bytes；向上取整到 MiB 后 MAX_CATALOG_JSON_BYTES = 2,097,152 bytes（2 MiB）。取证公开 HTTP 实际值 t4 v1 / v2 均为 285,725 bytes；三倍值 857,175 bytes，最终上限高于该门槛，不需要新 V。GetOperation 的上限数值保持不变。旧调试栈没有恢复，未为 Catalog 测量重建 t4。

DC30 下曾有一个未完整结束的 b017 调试尝试，日志 s2b-realdata-b0175cf583.log；它在 t3 Preview 终态前终止，没有可作为证据的结果。没有据此改产品代码。最终运行由独立主机进程完成，日志 s2b-realdata-b0175cf583-retry1.log，exit 0。

### 8.3 S2b.9 DC31 实施与卡住路径复现

DC31 主实现提交 34ec9ef6f2c0a97c3b359788642d1cb1b603eb43 完成以下内容：

- Catalog wire 常量改为 2 MiB；超限使用 RESPONSE_LIMIT_EXCEEDED / HTTP 500；GetOperation 原数值不变，错误码统一。Repository Service Contract、wire 常量、OpenAPI 与相关测试直接更新，无兼容层。
- Preview 与 History 的 PURE_RECOMPUTE 仓库读取错误按临时 / 确定性分类：前者在现有 R5 recovery budget 中重试并带公开 diagnostic，用尽预算后 FAILED；确定性错误直接 FAILED 并带公开 diagnostic。RepositoryClientError 不再变成 UNCLASSIFIED；handler 异常被 recovery boundary 捕获，不退出 worker。
- 第一轮审核确认卡住路径适用于任何 capability：worker 进程在 lease 有效期内重启，StartupRecovery 对 EXTERNAL_EFFECT / NON_RETRYABLE 的 live RUNNING pair 曾返回 READY；正常领取循环只领取 PENDING / RETRY_WAIT，因此 worker 进入 idle-ready，lease 过期后也不会再被扫描，公开 operation 永久停在 RUNNING。F1 修复在任何 capability 的 live lease 上返回 RETRYABLE_BLOCK；事务内复查仍有效时同样阻断。lease 过期后继续依照原 R5 处置表；这不改变 EXTERNAL_EFFECT 语义，也没有新增状态、周期扫描或修改 R5。
- 故障注入参数表 owner：test_pure_recompute_repository_read_failure_uses_bounded_terminal_diagnostics，修订后确定性 Catalog 错误经 RepositoryProvider 与物化路径到达 FAILED，公开 diagnostic code 为 `REPOSITORY_CATALOG_LOAD_FAILED`、消息包含 `RESPONSE_LIMIT_EXCEEDED`；临时错误重试后成功；临时错误用尽恢复预算后 FAILED。另有 unexpected handler exception 不退出 worker 的用例。
- Compose owner：test_preview_worker_restart_takes_over_expired_running_operation，在 Preview RUNNING 时 SIGKILL worker，重启后公开 operation 最终 SUCCEEDED。Repository 上限的合成超限与未超限用例为 test_build_catalog_response_rejects_oversized_wire_payload、test_build_catalog_response_accepts_payload_within_wire_limit；GetOperation 超限也仍使用 RESPONSE_LIMIT_EXCEEDED。
- 原 S2b.9 V `adc5d87fea` 后仅改 benchmarks 与 `test_real_dump_*.py`，符合 §8.9；本轮审核修订随后形成新 V `753c5768a5`。

旧 34ec 门禁尝试发现 serial integration test 的线程 barrier 未进入：test_branch_movement_keeps_pinned_commit_immutable，exit 1。原因是 `09c3e8c217` 引入 immutable Catalog 缓存后，该测试仍拦截 `commit_exists`，而运行路径已不再调用它；`adc5d87fea` 将拦截点移至 `catalog_at` 后才重新执行完整 runner。这是测试屏障与缓存读取路径对齐，不是延长 timeout。两轮日志分别为 `s2b-gate-34ec9ef6f2.log` 与 `s2b-gate-adc5d87fea.log`。

### 8.4 第一轮修订后的最终权威 runner V

V = `753c5768a533885b5e0af0865cfe28c62df3ce27`；日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5.log`，provenance 为 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5-provenance.json`。开始 / 结束 HEAD 均为 V，status clean；preflight：legacy 链接存在、无 Dolt、无带 Compose project 标签的容器、8000 空闲。执行 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，runner 自身 exit code 0。先前 V `adc5d87fea` 的日志是历史验证，本次新 V 完整重跑。

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend（包含 Compose） | 2,847 passed，1 warning |
| repository_service parallel | 1,684 passed，1 skipped |
| repository_service serial | 205 passed，1,685 deselected |

S2b §2 owner 的实际命令是上述权威 runner（其内部按包调用受控 uv-consume / pytest）；本次 runner exit 0。`test_comparison_canonical_domain.py`、`test_repository_ref_materialization_protocol.py`、`test_preview_job_materialize.py`、`test_submit_transactions.py`、`test_commit_canonical_metadata.py`、`test_submit_artifact_protection.py`、`test_submit_job_prepare.py` 与 control DB schema tests 在 backend batch；integration `test_submit_prepare_removed_tables.py` 和 `test_canonical_snapshot_identity.py` 也都位于 `vnext/backend/tests`，在 backend batch 通过。DC31 focused owners、S2b-F1/F2/F4 tests 与 Compose journeys 同样在完整 runner 通过。旧 V `34ec`、`adc5` 的失败 / 通过均作为历史记录保留；最终 runner 在包含全部审核修订的新 V 上完成。

最终 import_rules：IMPORT_RULE_BASELINE=frozenset({})，RUNTIME_CYCLE_BASELINE=()，unreachable 14，即 0 / 0 / 14。S2a exit 为 3 / 0 / 14，全程只减不增。五个 uv.lock SHA 未变；仍为 §2 所列值。最终 V 的五包静态检查与 focused tests 见 §8.10。

### 8.5 同一 V 的真实数据与对照基准

真实数据不在审核修订轮重跑：owner 已确认沿用 `b0175cf583` 的取证。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-realdata-b0175cf583-retry1.log` 记录当时完整 t1–t4 journey 的起止 HEAD 为 `b0175cf583ba7e89b0db830607c0f9bf15dc4bf4`、status clean、exit 0、PASS；它不是新 V `753c5768a5` 上的运行。审核修订只涉及启动租约处置、取消终态和诊断测试，没有改动 benchmark、projection、comparison 或真实数据路径；owner 同意复用该证据。首次完整带时间戳校准日志 `s2b-realdata-postv-488c4975f2.log` 仍只作为校准，不作为最终取证。

| 档 | 版本 | Dataset ID | SHA-256 | 包 bytes | 源表 / 总行数 | 规范状态摘要 | Preview changed / degraded / failed / table_count | Catalog bytes / 表数 / Catalog 行数 | IEC104 pseudo 行 |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- | ---: |
| t1 | v1 | rd-t1-a-v1 | 42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2 | 107,115 | 133 / 6,097 | sha256:d2daa9277446c3d7a91749f441cdf4f033e58bc75b45bca15d696580689c2285 | 124 / 0 / 0 / 124 | 122,107 / 124 / 3,729 | 4 |
| t1 | v2 | rd-t1-a-v2 | 4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0 | 107,066 | 133 / 6,095 | sha256:17588ec83085ffbaf6401a3b77a555051048cb1296639666a905498de38473f6 | 4 / 0 / 0 / 124 | 122,107 / 124 / 3,727 | 4 |
| t2 | v1 | rd-t2-b-v1 | acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0 | 1,247,459 | 217 / 97,140 | sha256:0fd40c96957150a5d092f6cab63062cda40c395ffc673446fb0a18826fe2480b | 208 / 0 / 0 / 208 | 198,906 / 208 / 73,648 | 3056 |
| t2 | v2 | rd-t2-b-v2 | c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98 | 1,197,404 | 217 / 93,154 | sha256:054bc660c26a457dcd61580ab6461060b1b75905d9208ee5d7ffbab62a236336 | 57 / 0 / 0 / 219 | 198,911 / 208 / 68,864 | 2674 |
| t3 | v1 | rd-t3-c-v1 | c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e | 3,356,815 | 200 / 268,661 | sha256:51e8bf93050a01154b99b2873fe7a5e1a0816c4715c79087d8f52b2025e83b01 | 191 / 0 / 0 / 191 | 174,294 / 191 / 122,251 | 9858 |
| t3 | v2 | rd-t3-c-v2 | 658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d | 3,370,171 | 201 / 268,667 | sha256:36231fd386911d00a331ac0c61df90ba96633ebe822834e3d08c537c77f0bc6f | 54 / 0 / 0 / 192 | 178,196 / 192 / 122,257 | 9858 |
| t4 | v1 | rd-t4-d-v1 | 95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675 | 5,597,503 | 320 / 437,149 | sha256:961ad834b2a145371657cf6a1e60b0bc12d45d48ecc6748f1c6755310f123b42 | 311 / 0 / 0 / 311 | 285,725 / 311 / 246,359 | 12676 |
| t4 | v2 | rd-t4-d-v2 | 5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611 | 5,596,595 | 320 / 437,229 | sha256:e05a073efdf2adaa5aeebea25bb7cd5657f1c4e2ffd96c4b71be0280c907b6bc | 26 / 0 / 0 / 311 | 285,725 / 311 / 246,439 | 12688 |

每档首个 INITIAL 均为空提交。每份 v1 Preview / Submit 成功归档；同一 v1 重传后 Preview 全表 UNCHANGED，Submit 为 NO_CANONICAL_CHANGE；同档 v2 Preview / Submit 成功，随后 History 比较完成。无 Preview degraded / failed。完整 journey wall：t1 380.335 s，t2 3,057.978 s，t3 6,149.528 s，t4 10,139.016 s。各档 History public record_count 分别为 12、11,511、744、168；bundle / surface digest 见 §8.7。

### 8.6 性能 A / B / C 记录

保护超时依据首次完整带时间戳运行的实测 wall × 5，最低 300 s；未知操作保留首次运行的 3,600 s 上限。test_operation_timeout_uses_five_times_measurement_with_five_minute_floor 覆盖公式与 floor。最终运行所有 operation 均在保护超时内终态；无 A 层失败。CPU 秒按 backend / repository-service / worker 记录。t4 v2 Preview 的 worker cgroup 计数器重置，只有该格不可用。

B 层按 DC31 只记录并交 S5。当前表中可见 Preview、Submit、History 的绝对耗时高，但整体 CPU 也高，不呈现 wall 明显远大于 CPU 的空等；主机侧 journey 经批量 HTTP 接口核对，不按行逐次调用。P5 未据此改产品代码。S5 候选是按规模复核 Preview / History 的 CPU 成本与重复读取路径；未把结构性原因写成已确认事实。DC31 的主机 py-spy 热点采样是可选项，本轮未采集。C 层逐步结果如下：

### t1 — journey wall 380.335 s
| Step | Wall s | Backend CPU s | Repository Service CPU s | Worker CPU s | A 层 | B 层 | C 层 |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| v1-workspace | 0.699 | 0.027 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-upload | 0.702 | 0.017 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-preview | 52.989 | 1.495 | 1.309 | 40.985 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-submit | 41.625 | 1.799 | 62.258 | 14.024 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-repository-read | 10.726 | 0.258 | 56.924 | 0.013 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-approve | 0.693 | 0.013 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-archive | 0.748 | 0.049 | 0.106 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-workspace | 0.682 | 0.070 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-upload | 0.715 | 0.019 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-preview | 73.086 | 2.063 | 31.095 | 47.090 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-submit | 0.700 | 0.010 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-workspace | 0.697 | 0.007 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-upload | 0.726 | 0.020 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-preview | 77.113 | 2.220 | 31.445 | 47.631 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-submit | 43.561 | 1.883 | 68.438 | 13.949 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-repository-read | 10.999 | 0.246 | 59.502 | 0.016 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-approve | 0.694 | 0.009 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| history | 62.971 | 1.731 | 59.708 | 34.966 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |

### t2 — journey wall 3057.978 s
| Step | Wall s | Backend CPU s | Repository Service CPU s | Worker CPU s | A 层 | B 层 | C 层 |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| v1-workspace | 0.700 | 0.041 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-upload | 0.749 | 0.062 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-preview | 722.321 | 20.119 | 18.107 | 714.050 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-submit | 239.185 | 7.875 | 115.331 | 204.020 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-repository-read | 27.288 | 0.743 | 117.978 | 0.067 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-approve | 0.714 | 0.013 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-archive | 0.726 | 0.041 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-workspace | 0.706 | 0.007 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-upload | 0.749 | 0.061 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-preview | 603.888 | 16.994 | 75.174 | 571.636 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-submit | 0.692 | 0.066 | 0.121 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-workspace | 0.684 | 0.007 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-upload | 0.745 | 0.064 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-preview | 688.043 | 19.200 | 76.286 | 645.367 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-submit | 239.071 | 7.908 | 125.586 | 197.632 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-repository-read | 28.087 | 0.638 | 120.182 | 0.075 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-approve | 0.692 | 0.008 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| history | 502.742 | 13.724 | 137.237 | 435.037 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |

### t3 — journey wall 6149.528 s
| Step | Wall s | Backend CPU s | Repository Service CPU s | Worker CPU s | A 层 | B 层 | C 层 |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| v1-workspace | 0.680 | 0.066 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-upload | 0.828 | 0.166 | 0.002 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-preview | 1244.848 | 34.849 | 31.406 | 1238.459 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-submit | 479.276 | 15.013 | 121.944 | 439.159 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-repository-read | 24.743 | 0.619 | 101.863 | 0.050 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-approve | 0.684 | 0.013 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-archive | 0.717 | 0.042 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-workspace | 0.687 | 0.007 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-upload | 0.837 | 0.170 | 0.002 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-preview | 1363.468 | 38.795 | 102.101 | 1320.655 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-submit | 0.696 | 0.011 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-workspace | 0.680 | 0.007 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-upload | 0.844 | 0.177 | 0.002 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-preview | 1528.329 | 43.236 | 106.024 | 1485.005 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-submit | 502.930 | 15.619 | 139.734 | 450.994 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-repository-read | 25.793 | 0.640 | 112.335 | 0.058 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-approve | 0.684 | 0.008 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| history | 972.603 | 26.358 | 167.003 | 889.927 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |

### t4 — journey wall 10139.016 s
| Step | Wall s | Backend CPU s | Repository Service CPU s | Worker CPU s | A 层 | B 层 | C 层 |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| v1-workspace | 0.676 | 0.060 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-upload | 0.934 | 0.263 | 0.002 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-preview | 2567.441 | 72.550 | 64.806 | 2555.601 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-submit | 805.214 | 25.238 | 205.344 | 742.664 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-repository-read | 52.765 | 1.287 | 198.105 | 0.135 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-approve | 0.690 | 0.013 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v1-archive | 0.727 | 0.042 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-workspace | 0.672 | 0.007 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-upload | 0.956 | 0.393 | 0.055 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-preview | 2244.159 | 64.425 | 172.875 | 2174.203 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| repeat-v1-submit | 0.668 | 0.010 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-workspace | 0.691 | 0.006 | 0.001 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-upload | 0.954 | 0.272 | 0.002 | 0.000 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-preview | 2244.042 | 62.742 | 171.907 | —（cpu.stat reset） | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-submit | 814.908 | 24.871 | 226.217 | 748.357 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-repository-read | 50.529 | 1.262 | 207.391 | 0.102 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| v2-approve | 0.699 | 0.009 | 0.001 | 0.003 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
| history | 1352.081 | 36.412 | 274.586 | 1233.713 | 完成并核对 | 记录未修；重负载见 S5 | wall/CPU 已记录 |
### 8.7 DC29、IEC104 与 History 可见结果

DC29 实际结果：t1 23 张、t2 27 张、t3 v1 27 张 / v2 28 张、t4 33 张 keyless fallback 表；所有档重传时这些表均包含在 Preview 全表 changed=0 的结果中，UNCHANGED 且 Submit 为 NO_CANONICAL_CHANGE。不再出现 KEY_MISSING；keyless 表不是 DEGRADED，不产生 KEY_DEGRADED。Repository Service 同次启动的完全重复行 Dolt 往返、Compose 重传 unchanged 与一删一增用例均由 V 的 runner 通过。manifest 3.2.0；storage projection version 是 2（S2a-F1 从 1 升至 2）；DC29 下此前可成功投影表的规范字节与内容摘要不变，golden 覆盖规则事实与 manifest contract 变化。

按决议允许记录的表名如下（版本差异仅在 t3 v2 多出 comm_user_data）：

- t1（23）：cnt_manage_cfg、comm_user_data、forwardtable_yx1、forwardtbl_lst_cs、forwardtbl_lst_dz、forwardtbl_lst_qt、forwardtbl_lst_yc、forwardtbl_lst_yk、forwardtbl_lst_ym、forwardtbl_lst_yt、forwardtbl_lst_yx、iec104_cfg、iec61850c_cfg、jdxx_cfg、mms_rp_cdc_index、out_time_cfg、project、sc_cfg、scada_cfg、sg_manage_cfg、vqc_cfg、wave_cfg、wf_cfg。
- t2（27）：cnt_manage_cfg、comm_user_data、forwardtable_yc1、forwardtable_yk1、forwardtable_yt1、forwardtable_yx1、forwardtbl_lst_cs、forwardtbl_lst_dz、forwardtbl_lst_qt、forwardtbl_lst_yc、forwardtbl_lst_yk、forwardtbl_lst_ym、forwardtbl_lst_yt、forwardtbl_lst_yx、iec104_cfg、iec61850c_cfg、jdxx_cfg、mms_rp_cdc_index、nr103d_cfg、out_time_cfg、project、sc_cfg、scada_cfg、sg_manage_cfg、vqc_cfg、wave_cfg、wf_cfg。
- t3 v1（27）：cnt_manage_cfg、forwardtable_yc1、forwardtable_yk1、forwardtable_yt1、forwardtable_yx1、forwardtbl_lst_cs、forwardtbl_lst_dz、forwardtbl_lst_qt、forwardtbl_lst_yc、forwardtbl_lst_yk、forwardtbl_lst_ym、forwardtbl_lst_yt、forwardtbl_lst_yx、iec101_cfg、iec104_cfg、iec104gw_cfg、iec61850c_cfg、jdxx_cfg、mms_rp_cdc_index、out_time_cfg、project、sc_cfg、scada_cfg、sg_manage_cfg、vqc_cfg、wave_cfg、wf_cfg。
- t3 v2：上述 t3 v1 名单加 comm_user_data（28）。
- t4（33）：cnt_manage_cfg、comm_user_data、dev104_cfg、forwardtable_yc1、forwardtable_yc2、forwardtable_yk1、forwardtable_yt1、forwardtable_yx1、forwardtable_yx2、forwardtbl_lst_cs、forwardtbl_lst_dz、forwardtbl_lst_qt、forwardtbl_lst_yc、forwardtbl_lst_yk、forwardtbl_lst_ym、forwardtbl_lst_yt、forwardtbl_lst_yx、iec104_cfg、iec61850c_cfg、jdxx_cfg、mms_rp_cdc_index、nbridge_cfg、nr103d_cfg、nr103ht_cfg、out_time_cfg、project、sc_cfg、scada_cfg、sg_manage_cfg、sntp_cfg、vqc_cfg、wave_cfg、wf_cfg。

IEC104 ordered pseudo 段行数逐档符合验收：t1 v1/v2 = 4/4；t2 = 3,056/2,674；t3 = 9,858/9,858；t4 = 12,676/12,688。重传 Preview 无变化，v1→v2 ordered tables 无降级。公开 History API 可返回 pair record_count 与 bundle / surface digest，但其 bundle artifact 只给引用，没有公开读取各类记录明细的接口；脚本没有在容器内核对，也没有新增接口。因此逐类 History 记录数无法由 HTTP 取得，本 handoff 以 public record_count 与 digest 作为替代证据；IEC104 空白区间净变化、移动不误标与字段变化不显示仍由 §2 owner tests / Compose 旅程证明，未从真实项目行数据推导或记录分类数量。

DC9 删除清单与 HTTP/OpenAPI 变化沿 §3 的旧核对项；HistoryIntegrityFailure 保留；ADR 0016 Operation integrity 测试在 V 通过。Golden 变化：storage-projection manifest s5 durable roundtrip、ruleset malformed s1 duplicate selector、ruleset valid s1 net cfg / s2 migrated matrix，以及 mutation renderer first-load-insert SQL。前三类中 manifest 的 projection-version 字段 1→2 源于 `26560b2595` 的 S2a-F1 负零规范化，ruleset v2→v3 也在该提交；DC29 更新 `DDL_PRIMARY_KEY_OR_KEYLESS` 规则事实与 manifest contract 3.2.0，不改变此前能成功投影表的规范字节或内容摘要。mutation renderer golden 来自 `ce58301a4f` 的批量 INSERT。DC31 未新增 golden 文件；OpenAPI 与 wire tests 覆盖响应上限和错误码。真实数据规范状态 digest 见 §8.5 表。

### 8.8 修订轮真实数据与修订后验证口径

第一轮审核修订按 DC30 §8.9 调试 / 取证分离：focused 测试与 Compose 调试通过后，在 V `753c5768a5` 一次性完整运行权威 runner；真实数据按 owner 明确确认沿用 `b0175cf583` 的既有完整取证，不在修订轮重跑。V 后没有 production 或 test 提交；H 只改 handoff。

可选的公开 Preview `ADDED` / `REMOVED` 表数没有补入 benchmark。现有真实数据日志仍记录 t2 v2 Preview `table_count=219`、Catalog 208 张；该差值可能由新增 / 移除表造成，但本修订没有给出逐项表数，避免将推断当成观测结果。Catalog 实际 JSON 字节见 §8.5，t1–t4 均低于 2 MiB 上限。

修订轮未新增或修改 golden / digest / checkpoint / DTO / OpenAPI；F3 的 projection version 与 golden 来源更正见 §4、§8.7。修订未改 import graph，最终仍为 `0 / 0 / 14`；预算外生产路径逐项列于 §1，DC31 停止条件均未触发。

### 8.9 审核提示词

任务：独立审核 P5 架构收口 S2b。审核者未参与实施；按 formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：p5-s2b @ H（门禁提交 V = `753c5768a533885b5e0af0865cfe28c62df3ce27`），区间 `p5-s2a-exit..H`。区间内审核方文档提交 `0ce71cac27`、`a80ca8c402`、`cae9a0f82b` 与第一轮独立审核报告 `e94008889c` 按提交区分；实现修订提交从 `e94008889c` 之后核对。另有不在分支中的 main 审核方文档提交 `62cc7c3e0f`（DC29）、`1925dcedc2`（DC30）、`5a1a391ea8`、`92db9df18e`（DC31）、`a889acc242`（Catalog 离线估算补充），不得将这些文档提交视为实现差异。

审核 worktree：先执行 git worktree add --detach /home/dev/gdds-review-s2b H，再创建本地 legacy 链接：ln -s /home/dev/gateway-data-management-system/legacy /home/dev/gdds-review-s2b/legacy。只在 detached review worktree 中审核，不修改本阶段代码与 handoff。

权威依据：执行计划 §2 S2b、§3 S2b、§8.1、§8.2、§8.5、§8.7、§8.9；设计 §4.6、§4.8、§5（§5.3 受理顺序、§5.5 DC9 与 DC19）、§7.6、§9 S1 延期、§10、§12、§14；ADR 0016、0018–0021；Canonical Storage §2、§5、§7；S2a 独立审核报告；S1-F3；DC29/DC30/DC31 owner 文档。handoff 之外仍按 kickoff 版本规格执行。

必须核查：
1. §2 S2b 全部 acceptance owners 与 §3 路径预算；S2b.0 按 S1-F3 关闭；DC9 删除清单与 ADR 0016 integrity tests。
2. NO_CANONICAL_CHANGE 唯一 owner；T1 闭包转移与启发式删除；removed_tables 三种情况；prepare checkpoint 复用与 0d9d0d9dc5 attempt 绑定语义；INITIAL 恒空；S2a-F1/F2 负零与类型覆盖。
3. DC29 三类规则与 device_cfg 边界、manifest 3.2.0、已有表规范字节不变、keyless 重复行无损存储与集合比较、无 KEY_DEGRADED、KEYLESS_FALLBACK 提示、Dolt 重复行往返、Compose 与真实数据重传结果。
4. DC31 Catalog 2 MiB 计算与 t3/t4 离线估算、公开接口实测 bytes、响应超限 RESPONSE_LIMIT_EXCEEDED、GetOperation 原上限、PURE_RECOMPUTE 临时 / 确定性失败 diagnostic 与 worker 不退出、restart/reclaim 具体路径和 Compose 终态；无新增状态、无 R5 表修改、无 endpoint。
5. 真实数据日志中的 t1–t4 Preview / Submit / 重传 / History、有序 pseudo 四项、keyless 名单与计数、Catalog actual bytes；逐类 History count 无 public API 时采用的替代证据；A/B/C 表、各 operation 终态与保护超时、import_rules 0/0/14。
6. V runner 日志与 exit code、provenance 镜像、V→H carried 判定、修订轮 focused tests / 五包静态检查。检查 branch 区间时将 in-range reviewer docs commits 与 implementation commits 分开，main-only 决议文档只用于理解授权范围。
7. 第一轮 Findings：S2b-F1 所有 capability 的 live lease 与过期 R5 路径、事务复查竞态；S2b-F2 三条组装取消均为 CANCELLED；S2b-F4 provider / materialization 路径的公开 diagnostic；S2b-F3 projection version、预算外路径登记、Catalog cache 屏障拦截点、测试批次与重复小节修正。

交付：plans/p5-arch-closure-s2b-independent-review.md。审核 worktree 提交审核报告后快进到 p5-s2b；由审核方在报告提交上打 p5-s2b-exit，再以 --no-ff 并入 main；不推送。

### 8.10 第一轮审核修订记录

| Finding / 事项 | 修订提交 | 处置与证据 |
| --- | --- | --- |
| S2b-F1 | `d450f946bf` | `StartupRecovery.recover_pair` 对任一 capability 的有效 RUNNING lease 返回 `RETRYABLE_BLOCK`；事务内复查竞态另有参数行；过期后 PURE_RECOMPUTE / EXTERNAL_EFFECT / NON_RETRYABLE 仍走现有 R5 处置。`test_operation_takeover.py` 参数表覆盖 6 个能力/租约组合与事务复查。 |
| S2b-F2、S2b-F4 | `4049986e4c` | Preview assembly loop、pair_pipeline、History compare assembly 取消均发布 `_make_cancelled_terminal_builder()`；对应 tests 断言 `CANCELLED`。确定性 Catalog 错误经 provider 与物化路径到达公开 `FAILED`，diagnostic code `REPOSITORY_CATALOG_LOAD_FAILED` 且消息含 `RESPONSE_LIMIT_EXCEEDED`；删除无可达生产来源的 `if not exc.retryable: raise`。 |
| Compose oracle 调试修复 | `753c5768a5` | 第一次新 runner 暴露 `test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey` 的内部 oracle 漏传取消 callback；补传无副作用 callback。focused Compose 复验 1 passed。 |
| S2b-F3 | 本 handoff-only 提交 | projection version 1→2 与 golden 来源归于 `26560b2595`；列全预算外生产路径和理由；更正 `commit_exists`→`catalog_at` 的 Catalog cache 原因；将两项 integration tests 归入 backend batch；删除重复的 8.1 小节。 |

修订调试阶段 focused 结果：F1–F4 相关 tests 15 passed；五个相关 backend test files（operation takeover、Preview assembly、History compare jobs、Preview materialize、operation recovery policy）164 passed；在最终代码 V 上再次执行 Compose oracle journey 1 passed（调试日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-debug-compose-oracle-753c5768a5.log`）。第一轮 runner 调试失败历史：`4049986e4c` 上 backend 2,846 passed、1 failed（Compose oracle 漏传 callback）；`753c5768a5` 修复后最终 runner 全量通过，没有以 focused 重跑替代权威结果。

最终 V 的权威 runner：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，exit code **0**；日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5.log`，provenance `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5-provenance.json`。批次为 shared_kernel 242 passed、repository_contracts 152 passed、repository_client 154 passed、backend 2,847 passed / 1 warning、repository_service parallel 1,684 passed / 1 skipped、repository_service serial 205 passed / 1,685 deselected。runner 起止 HEAD 均为 V，status clean。

V 上五包静态检查全部通过（ruff / mypy；mypy source files：shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 475）；`import_rules` 为 0 / 0 / 14。runner provenance 镜像：repository-service `sha256:196148beb96d508ae634212c70f560bb9f6c739f9d589e42bad4b870947b1883`，backend `sha256:4c7dd9242d867e5eec9314fc6bc549f264127e38b72715e2a34c024f73f30ebd`，worker `sha256:f8b59e3d42ba299f4237d7dac8cbcc305b7fa00aac349ad033fae04653eb1100`。RS build-input revision label `adc5d87fea073545fde6416d123c3d7845e715ff`、source-tree label `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`、lock label `sha256:6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`；详见 image inspect 文件 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-revision-gate-753c5768a5-images.txt`。

真实数据沿用 owner 确认的 `b0175cf583` 取证，未在修订轮重跑。其日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s2b-realdata-b0175cf583-retry1.log`；Catalog 实测、DC29 keyless 与 IEC104 四项摘要见 §8.2、§8.5、§8.7。可选 ADDED / REMOVED 表计数未补；不把 t2 v2 的 Preview `table_count=219` 与 Catalog 208 的差值解释为已测得的增删计数。

Carried 将在本 handoff 的 H 提交后、同一 worktree 完成。RS 将用 `build_context_digest.py identity` 对照 build-input revision 与 source-tree label；按 V provenance 的 Compose project `ordered-bisect-b-4106342-baseline` 重建 backend / worker，两个构建之间不跑测试，并比较 image ID。记录会在 H 提交后追加至本节并随 handoff 一并提交；若需再次修改 handoff，则在最终 H 后只允许复核 doc-only diff 不改变实现 V。
