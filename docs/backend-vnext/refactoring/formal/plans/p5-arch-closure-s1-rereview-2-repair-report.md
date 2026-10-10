# P5 架构收口 S1 第 2 次复审修复报告

日期：2026-10-10  
状态：本报告记录第 2 次复审修复完成时（候选 `96071affd4` + 未提交补丁）的状态。2026-10-10 owner 撤销“本轮不提交”指令，修订已提交，最终门禁在合并 `main` 后的提交 V 上重新执行，以 [handoff](p5-arch-closure-s1-handoff.md) §6 为准；本报告的“门禁结果”一节是历史记录，已按实测更正。

## 审核对象

| 项目 | 值 |
| --- | --- |
| 分支 | `p5-closure/s1` |
| Git HEAD | `96071affd490b728aa62fe4a6f0ee9e784e42466` |
| 授权 merge-base | `218c211240b33e01eee1eb8965fdcca0ec4b8099` |
| 本轮实现补丁 SHA-256 | `492cce95f9b63849533fbd7be8a0b87d36df546249c8c4ce3e4fbe87ba654b74` |
| full-test / image-build 起始候选 source tree | `db2809090dc20035795ccc2107e4aca8f71684ee`（临时 Git index tree） |
| gate-time full candidate diff SHA-256 | `1547a4ae01699d7bfdc932c0a83889410b534e83f5a50e9128385b44e20eb2c0` |
| repository-service image source tree | `sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf` |
| 提交状态 | 报告完成时未提交、未合并、未推送；owner 随后撤销不提交指令，修订已提交到 `p5-closure/s1`（见 handoff §6 traceability），仍未推送，`main` 未修改 |

HEAD 本身不包含未提交修订；复审时应同时核对实现补丁 SHA 和 gate source-tree 记录。全量测试与 Compose 旅程运行时的 HEAD 和实现补丁 SHA 前后相同。门禁后只更新了 census、handoff 和本报告文档；实现脚本和测试补丁 SHA 未变。

## Finding 处置

| Finding | 处置 | 修复与证据 |
| --- | --- | --- |
| F1 | 已关闭（沿用前轮代码修复） | Evidence 解码由 Application 委托严格 wire codec；HTTP/worker composition 均注入实现；7 类拒绝形态及 FAILED/SUCCEEDED 字节基准已独立核实。本轮未改 wire 行为。 |
| F2 | 已关闭（沿用前轮验证） | base 与 HEAD 的 `/openapi.json` 字节一致；前轮复审已按变化后的 base↔HEAD 重新测量。 |
| F3 | 已关闭 | S2b 路径预算已登记延期；handoff 逐项记载现状与理由。真实数据格式缺口（原“parser 前置”）改由治理修订计划 G2 承接，S1 合入后、S2a 前实施，移出 S2b 路径表；相关表格格式已修正。 |
| F4 | 已关闭 | 删除包级 facade 可达性扩展；按实际导入的 wrapper 符号展开惰性导入。基线为 3 条 import violation / 0 个 runtime cycle / 14 个 unreachable module。4 个 composite 模块依据不可达的唯一调用方登记为 S3 延期。 |
| F5 | 已关闭 | 设计 §9 的冻结计数从 3/10 更正为 3/0/14，并在 owner 决议、执行计划及 handoff 记录工具语义和延期归属。 |
| F6 | 已关闭为“记录完整、未评估项有明确承接” | Census companion 有 8 份结构记录、package bytes/SHA、DDL 与物化表数、类型统计、键扫描范围和 pair_of。t3/t4 的 XML 失败仍标为未评估，由 G2 承接并在 G2 验收的普查重跑中补齐。 |
| F7 | 已关闭（沿用前轮代码修复） | 上传限制常量在 application 叶子模块，依赖方向为 settings→application；无新增反向 import。 |
| F8 | 已关闭 | handoff 记录当前候选 HEAD `96071…`、最后已提交实现 HEAD `00ae9cc…` 和未提交补丁身份；更正 `canonical_import_request_bytes` 为 3 个测试桩、`run-tests-r2.log` 实际存在、历史镜像构建时间早于其声称的 revision，并修复代码围栏和 S2b/S2a 描述。 |
| F9 | 已关闭（沿用前轮代码修复） | Decoder registry、严格 JobDefinition 类型和 internal bearer port 均单一来源；当前 runtime cycle baseline 为空。 |
| F10 | 已关闭 | 架构基线复测为 3/0/14，没有新增 F7 violation 或 F9 runtime cycle。owner 决议明确批准 10→14 的测量语义更正；只减不增规则仍适用于真实 violation/cycle。 |
| F11 | 部分完成，阻塞阶段退出 | RS 镜像 label 与候选一致，但该镜像的构建早于补丁冻结，等价依据是 label；backend Compose 9 项通过，但日志开头记录的 backend/worker 是 2026-09-28 的旧镜像，手动 build 的 `deploy-*` 镜像没有被旅程使用，旅程实际使用的镜像由 gate harness 构建（handoff §6.6.2 更正 a–d）。权威全量 runner 实际 exit 1（dirty worktree）。因此不将 F11 或 S1 阶段退出标为已关闭；最终门禁见 handoff §6。 |
| F12 | 已修复 | t2 `COMPOSITE_LOGIC_FAILED` 被明确识别为 composite 阶段失败。诊断模式用新 parser context 独立重建 SQL snapshot 并继续扫描 216 张 SQL 表；诊断完整消息写入 JSON。该失败与 `@saved_cs_client`、`max_xml_depth` 一并由 G2 承接，不阻塞 S2b 的 DC22（决议 §10 第三项）。 |
| N2 | 已修复 | t1 duplicate scan 改标 partial，并明确 102 张已扫描、23 张有效键未解析、8 张规则跳过；102 张扫描得到每份 3 条额外重复行。 |
| N3 | 已修复 | 历史 build、日志存在性、implementation HEAD、source-tree 和 handoff 代码围栏均按实测更正。backend/worker 无 revision label 的事实被明确保留，不再推断历史 build revision。 |

## 普查修订细节

脚本改动位于 [`real_dump_census.py`](../../../../../vnext/backend/benchmarks/real_dump_census.py)，测试位于 [`test_real_dump_census.py`](../../../../../vnext/backend/tests/test_real_dump_census.py)，8 份结构与统计记录位于 [S1 census JSON](p5-arch-closure-s1-census.json)。

- t1 两份数据：133 张物化表；键扫描由 misleading `complete` 改为 `partial`。每份为 102 scanned、23 unresolved、8 SKIP、0 reader unavailable；每份检测到 3 条 duplicate extra rows。28 张无 DDL 主键表中 5 张有显式有效键。
- t2 两份数据：SQL DDL/materialization input 有 216 张表；业务 snapshot 在 composite stage 失败，XML `complete`、events=3158，诊断为 `Digital forbids attribute 'value'`。fallback SQL-only snapshot 对每份 181 张键表完成扫描，27 张键未解析、8 张 SKIP、0 reader unavailable；状态为 partial。v1 有 3,032 条 duplicate extra rows（16 张表），v2 有 2,653 条（14 张表）。40 张无 DDL 主键表中各有 13 张具显式有效键，具体表名与键列写入 JSON。
- t3/t4：结构记录保留；XML `max_xml_depth=64` 失败，duplicate/effective-key 统计明确为 not evaluated，承接在 G2 验收的普查重跑。
- 原始 t2 dump 仅按授权只读访问；未在 census JSON 写入行内容或主机路径。

## 门禁结果

> **本节已被 [handoff §6](p5-arch-closure-s1-handoff.md) 的最终门禁取代。** 以下是第 2 次复审修复完成时的记录（未提交候选、dirty worktree），不作为最终证据；其中的镜像与补跑描述已按 2026-10-10 的实测更正，完整更正与 7 次补跑的逐次记录见 handoff §6.6.2。

### 静态、架构和 focused tests

- 五包 ruff 与 mypy 全部通过；backend mypy 覆盖 464 个文件。
- `import_rules`：3 violations / 0 runtime cycles / 14 unreachable modules。
- `test_real_dump_census.py` + architecture unit tests：85 passed。

日志：[rereview2-focused.log](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-focused.log)。

### 权威全量测试

执行 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`。runner 结果：

- shared_kernel：242 passed
- repository_contracts：152 passed
- repository_client：154 passed
- backend：2702 passed，1 条 Starlette deprecation warning
- repository_service parallel：1678 passed，1 skipped
- repository_service serial：197 passed，8 failed；runner exit code **1**

8 项失败的共同 traceback 是 `compute_image_identity()` 的 `require_clean_worktree()` 抛出 `ProvenanceError: worktree is dirty`。这些用例在计算候选 image identity 时退出，未到达服务行为断言。owner 指令要求本轮不提交；因此没有通过临时 commit 或掩盖 dirty 状态来绕过该前置。

为核实这些 RS serial 用例，在 detached clean worktree @ 相同 Git HEAD、使用 candidate RS image 并强制 `-n 0` 一次性复核全部 8 项：**8 passed，exit 0**。clean worktree 中 RS package 与有效 image inputs 与候选相同；本轮实现改动仅位于 backend census 与文档。该定向结果是补充证据，不能改写原始全量 runner 的 exit 1。它是第 7 次补跑的结果；此前 6 次（xdist 并行、`-n 0`、collection error）的结果见 handoff §6.6.2 更正 e。

日志：[rereview2-full-tests.log](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-full-tests.log)、[8 项 clean-worktree 串行复核](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-rs-compose-clean-final.log)。此前 6 次补跑中，#1 为 xdist 并行且缺 `gateway_repository_client`，#4、#5 为 collection error（缺 `gateway_repository_service`、`pydantic_settings`），#2、#3 的 3 项失败主异常同样是测试环境缺包，`dolt children remain` 只出现在其中 1 项的清理链、根因未查实，#6 为 3 passed；逐次记录见 handoff §6.6.2 更正 e，均不计入通过证据。

### 镜像与 backend Compose

RS 镜像 `sha256:4895ff38e760bc230e9815ebd5ebaad87ec46c6ae5c75137b104e16c08a3b809` 的 Created 为 2026-10-10 12:06:34 +0100，早于补丁冻结；12:57 的构建全部命中缓存，没有重新构建。它与补丁后候选的等价依据是 label：candidate HEAD `96071…`、build-input revision `4d1dc010…`、source tree `sha256:62a38a08…` 和 repository-service uv lock SHA `6dc9659f…`。随后手动执行的 `docker compose -f vnext/deploy/compose.yaml build backend worker` 产出 `deploy-backend` `4068fcc8…` 与 `deploy-worker` `956b052d…`，Compose 旅程没有使用这两个镜像。

随后执行 9 项 backend Compose journey：**9 passed，1 warning，1072.26 秒，exit 0**。外部 provenance JSON 记录了实际运行容器的 backend image `sha256:e6bb3b380423c4cea058a14486b8645d7e53786e4dab29da95bd5d79d7e2c433`、worker image `sha256:44f4ce88211881672414f022b8450989b10053232819c67b33d1f439f9adced6` 和 repository-service image `sha256:4895ff38e760bc230e9815ebd5ebaad87ec46c6ae5c75137b104e16c08a3b809`；backend/worker 由 gate harness 构建，Created 为 2026-10-10 12:33:04 +0100，落在全量 runner 的 backend 批次内。journey 日志与 image-build 日志开头记录的 backend/worker `b6795948…`、`a6234eee…` 是 2026-09-28 的旧镜像（现已无 tag），不是本轮镜像。backend/worker 没有 revision/source-tree label，因此不能用 build 日志中的候选身份与这些 image ID 建立绑定；该绑定由最终门禁中 V 的 runner provenance 与 `carried` 判定重建。

日志：[image build](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-image-build.log)、[9 journeys](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-backend-compose-9.log)、[Compose provenance](/home/dev/gdds-p5-closure-s1-gate-logs/rereview2-backend-compose-provenance.json)。

## 结论

F1–F10、F12、N2、N3 的代码或记录修订已完成；F11 的镜像与独立 Compose 部分已完成。原始全量脚本未 exit 0，因此**本报告不建议将 S1 标记为阶段退出，也不建议据此合入 main 或开始 S2a**。本候选可交独立 reviewer 核对修复和证据；全量 runner 的 clean-worktree 约束须由 owner 决定后再完成退出门禁。（2026-10-10 更新：owner 已撤销不提交指令，最终门禁见 handoff §6。）
