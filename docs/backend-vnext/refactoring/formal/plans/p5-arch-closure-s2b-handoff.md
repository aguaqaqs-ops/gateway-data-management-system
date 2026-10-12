# P5 架构收口 S2b handoff

- 状态：**暂停，等待 owner 决定真实数据中的无主键表语义；S2b 未完成。**
- 日期：2026-10-12
- 分支 / worktree：`p5-s2b` / 独立 worktree
- `range_start`：`p5-s2a-exit`，`6f3e2ed67a03a2c452c7a13ff02d3aeb7d0f6792`
- kickoff base：`cae9a0f82be3415cc362e46b98da954edcf1d807`
- 最后代码提交（实现 HEAD）：`acbf865142382b63f57fd8c01a12721137f0c79b`
- 最后一次完整 runner 的提交：`08a8d9876bf2d347dd36cf8db4fac3d615306496`（仅为历史门禁结果，**不是最终 V**）
- 最终门禁提交 V / 候选 H / carried：**未形成 / 未形成 / 未执行**。真实数据停止条件在 V→H 前触发；`acbf...` 之后没有再跑完整 runner或真实 HTTP 旅程。

## 1. 区间与提交

`p5-s2a-exit..HEAD` 中 kickoff 前的审核方文档提交按区间核验时应与实现提交区分：

| 提交 | 说明 |
| --- | --- |
| `0ce71cac2743ab71c8c4adc7eaa597821996edd3` | 合并 S2a |
| `a80ca8c4020da26a01a285977dae402b77f69aa1` | S2a exit 记录 |
| `cae9a0f82be3415cc362e46b98da954edcf1d807` | S2b 预算文档修订；kickoff base |

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

S2a-F3 的启发式删除与 S2b.4 一起完成。S1 拆出的 comparison 行编码能力路径在 S1 已迁移；本区间没有为其另建副本。路径预算外仅增加了真实数据 runner 和上述可复现门禁 / fixture 修复，没有新增生产边界、规则基线条目或兼容路径。S2b.0 是 S1 复审 S1-F3 的延期收口项。

## 2. 导入基线与依赖

`python -m tests.support.import_rules`：

| 时点 | 违例 / 运行时环 / 不可达 |
| --- | --- |
| S2a exit 基线 | 3 / 0 / 14 |
| 当前 `acbf...` | 0 / 0 / 14 |

`prepare-dev-dependencies.sh` 在新 worktree 完成；随后 worktree clean，`uv.lock` 未改。当前五锁 SHA-256：

| 包 | SHA-256 |
| --- | --- |
| shared_kernel | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| repository_contracts | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| repository_client | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| repository_service | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| backend | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |

## 3. 实际验证

### 当前实现 HEAD `acbf...`

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
- `08a8...` 的完整 runner exit 0；当前 HEAD 的 DC9 代码没有在新完整 runner 上重验。

## 4. Golden、digest、checkpoint、DTO 与 OpenAPI

- Golden：`vnext/fixtures/golden/storage-projection/manifest/valid/s5-durable-roundtrip/document.json`、ruleset malformed `s1-duplicate-selector` 与 valid `s1-net-cfg` / `s2-migrated-matrix` 更新到新规范投影语义。
- Digest 与 S2a-F1/F2：`test_canonical_snapshot_identity.py` 在一次 Repository Service 启动中补充 INT UNSIGNED、BIGINT 边界、FLOAT 常见值与次正规值、负零；`test_canonical_state_identity.py` 覆盖 `-0.0` 与 `0.0` 同摘要。`acbf...` 让完整源行内容在 comparison descriptor 为 KEYLESS 时仍可按 storage key 投影。
- Checkpoint：Preview / Submit 的规范表闭包与 manifest 绑定进入持久载荷；prepare package 与 attempt 绑定纳入允许键并复用。`0d9d0d9dc5` 的 attempt 绑定与 payload 不符即 FAILED 保留；无兼容 payload 别名。
- DTO / OpenAPI：HTTP History / Operation DTO 清除 DC9 字段；Preview 与 Submit 映射新规范事实、身份结论与失败码；OpenAPI 合同测试相应更新。
- Control DB：仅改 `infrastructure/control_db/schema.py` 单一基线，未增加 migration。

## 5. 真实数据与停止事实

运行脚本：`vnext/backend/benchmarks/real_dump_journey.py`，主机侧通过公开 HTTP API；原始目录只读且不挂载到容器。权威的首次运行在 `08a8...` gate 后、同一提交、clean preflight 下开始；t1-v1 Preview 未完成，operation 失败为 `BINDING_INVALID`，日志文件名 `s2b-realdata-08a8d9876b.log`。随后为取到 stage/message 做了一次诊断重跑，运行前临时改过 host script，故该次 worktree dirty，不作为门禁或合规真实旅程证据；日志文件名 `s2b-realdata-diagnostic-08a8d9876b.log`。诊断完成后脚本不输出 operation message，仅保留 stage 与错误码。所有栈与 Dolt 均 teardown；没有完成 t1–t4 的 Submit / 重传 / History 有序表四项验收。

首个失败是已修复的投影缺陷：比较域因无比较键而给 descriptor 标记 `KEYLESS`，投影此前在应用 storage rules 前拒绝任何 degraded descriptor；`acbf...` 现仅拒绝 `TABLE_FAILED` 或缺少完整源内容，并允许 storage rule 使用显式键。该提交的 focused 测试与五包静态检查已通过。

修复后对同一 t1-v1 包的只读投影诊断继续发现 23 项 `KEY_MISSING`。生产 parser 对源 SQL 的状态为 COMPLETE，132 张源表中 104 张既有源 `PRIMARY KEY` 也被 parser 解析为主键；例如 `cnt_manage_cfg`、`comm_user_data`、`forwardtbl_lst_*`、`iec104_cfg`、`project`、`sc_cfg`、`wave_cfg` 等触发项在源 DDL 中没有 `PRIMARY KEY`。当前 ruleset 对这些实际参与规范存储的表要求 `DDL_PRIMARY_KEY`，因此不是 parser 漏读。

本次数据统计仅引用已接受 census 元数据：`rd-t1-a-v1`，package SHA-256 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`，107,115 bytes；132 张 source DDL 表、census 133 张物化表、总计 6,097 行。HTTP journey 在 Preview 阶段失败，后续项目级旅程与 IEC104 记录数量没有结果可报告。

停止原因：若继续必须由 owner 决定这些无主键表的规范键 / keyless 语义或规则处置，可能改变规范状态与比较语义。按本阶段真实数据停止规则暂停；没有猜测业务键、加 application 特判、排除数据或增加导入基线项。请 owner 决定允许的 canonical semantics 与规则更新范围；决定前不得形成最终 V/H、跑 carried 或宣称 S2b ready。

## 6. 镜像与 carried

`08a8...` 权威 runner 的最后已验证镜像记录（不是 `acbf...` 的镜像验证）：

| 镜像 | image ID | 标签 / provenance |
| --- | --- | --- |
| repository-service | `sha256:2a823aed0a7b2f9c2cb6105990f86114adfbf2132837be73f8932331e5aab36c` | revision `08a8d9876bf2d347dd36cf8db4fac3d615306496`；source-tree `sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f` |
| backend | `sha256:d9d6792456e462f90a37fbd7e431add58d5a78ba99e996ee057f99cc191b3742` | provenance project `ordered-bisect-b-897226-baseline`；无 build-input / source-tree label |
| worker | `sha256:a61e3bb0ec2403ed0e8a07ad7a76f03b79a80ae4aadc17c9f68afc616a2d0ed9` | provenance project `ordered-bisect-b-897226-baseline`；无 build-input / source-tree label |

`acbf...` 晚于上述镜像与门禁；没有重建 backend / worker 或重算 repository-service source-tree 身份，因此 V→H carried **不适用 / 未判定**。恢复后最终实现 HEAD 需要重新执行完整 runner、记录新 image identities，再生成仅含 handoff 的候选提交。

## 7. Reviewer / owner 核对重点与当前未完成项

当前交付的是停止记录，不是审核候选，也不附 §8.7 的候选审核提示词。Owner 恢复后，独立审核仍需区分 R0 与三项审核方文档提交，并核查：§2 验收 owner、§3 路径预算、S1-F3、DC9 与 ADR 0016、`NO_CANONICAL_CHANGE` 唯一 owner、T1 闭包转移与启发式删除、`removed_tables` 三种情形、prepare checkpoint 复用、INITIAL 恒空、S2a-F1/F2、有序表四项真实数据结果、0/0/14 与最终 V 门禁及 carried。

未完成项：无主键表语义 owner 决议；新 V 全量 runner；完整 t1–t4 HTTP 真实数据旅程；V→H carried 判定；最终候选 H 与审核提示词。
