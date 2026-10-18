# P5 架构收口 S3 独立审核

- 结论：**通过**。初审结论为定向修订（唯一阻塞项 S3-F1）；owner 于 2026-10-18 澄清约束范围（main `d65a39ad98`，治理修订计划 G10 第 3 项、§3 第 9 项），S3-F1 改为已关闭的观察项，结论改为通过。
- 日期：2026-10-18
- 审核对象：`p5-s3` @ `96c835ac90c597ce7cd35c351f9c567925d9d5ef`（门禁提交 V `dc9c08a410829f303aae1e0f826c674b335cb94b`，实现 HEAD 与 V 相同），区间 `p5-g11b-exit` (`944982eb910dab9cbfc117a976dea6721cdd6ca2`) .. H
- tag：`p5-s3-exit`（附注 tag，指向提交本报告的提交）。按 owner 授权，由审核方直接定稿、打 tag 并 `--no-ff` 合入 main。
- 依据：执行计划 §2 S3、§3 S3、§4、§6、§7、§8；设计 §8、§4.4、§4.6、§12、§14；S3 handoff

## 1. 结论摘要

S3 的 composite 接入、operation 查询修复、真实数据验收和代码检查达到阶段要求；四项追加核查均在 handoff 中披露并经独立核对。

初审唯一的阻塞项 S3-F1 是：V 的 Compose 测试构建通过 `docker build -t` 改变了 `gateway-repository-client-e2e:local` 的指向。owner 已澄清，这是 G7 之后 harness 的预期行为，不在禁令范围内，S3-F1 关闭。`completed.wait()` 的无界等待会延迟 drain，但不改变已提交 operation 的终态，且旧异常路径同样无界等待，保留为非阻塞观察 S3-F2。S3 通过；S4 按治理修订计划 §3 第 10 项，在 G12 第 1 项完成后 kickoff。

## 2. Findings

### S3-F1：权威 runner 改变了受保护的 client e2e tag 指向（已关闭，观察项）

- 类型：初审为已证实缺陷（门禁执行约束偏差）、阻塞；owner 澄清后改为观察项，已关闭，不阻塞
- 位置：`vnext/repository_service/tests/support/compose_lifecycle_harness.py:889-963`；handoff §7
- 依据：原实施授权明确要求不得删除或重新 tag `gateway-repository-client-e2e:local` 和 `gateway-repository-client-e2e-base:local`。Compose harness 在候选镜像 label 不匹配时调用 `_run_client_build()`，其命令参数包含 `docker build ... -t <现有 image tag>`；V runner 的结果记录确认 `gateway-repository-client-e2e:local` 指向新 image ID `sha256:55c506d6ef4895a6c8bf8d734c3e9fc21772554186a1cad66f386dba83aacb90`，base tag 保持原 ID。没有执行独立的 `docker tag` 或 `docker rmi` 命令，但 `docker build -t` 已将受保护 tag 绑定到新 image，效果上改变了 tag 指向。handoff 没有声称镜像未变，并说明没有 runner 紧邻开始前的快照，也没有尝试恢复。
- 触发场景与影响：权威 runner 执行 repository-client Compose 测试时，旧 tag 的 candidate label 与 V 不同，`ensure_client_image()` 重建并对原 tag 赋新 image。它违反或至少越过了“不得重新 tag”的明确边界；缺少 owner 解释时，不能以“没有手工运行 `docker tag`”推定该副作用获准。
- 最小修正方向：请 owner 明确 `docker build -t` 对现有受保护 tag 的重绑定是否属于禁令范围，并给出明确接受或合规重跑的决议。未获授权前不要恢复或再次移动该 tag。
- 关闭标准：owner 对该副作用作出书面 waiver/解释并确认当前门禁可接受；若不接受，则须按 owner 授权的方式完成不改变受保护 tag 的权威门禁及镜像记录。
- **关闭（owner 决议 2026-10-18，main `d65a39ad98`）：**
  - 禁令的范围是：手工对 `:local` 与 `-base:local` 执行 `docker rmi`、`docker tag` 或其他删除操作，以及任何会让 `-base:local` 被重建或删除的操作。权威 runner 按候选 label 以 `-base:local` 为底重建、用 `-t` 改变 `:local` 的指向，属于预期行为，不需要豁免，也不需要重跑。
  - 事实核对：该行为自 G7（`84177001e1`，2026-10-10）起存在，S1 之后各次门禁都会发生；`p5-g11b-exit..H` 没有改动 `vnext/repository_service`、`vnext/repository_client`、`deploy`、`vnext/scripts`。`-base:local` 仍为 `sha256:dafde407…`（2026-10-10 构建，12 层），carried 前后不变；`:local` 为 `sha256:55c506d6…`（20 层），建在 base 之上，label 为 V。
  - 提示词措辞没有排除 runner 的内部构建，责任在提示词；初审按字面把关是正确的。之后各阶段提示词按治理修订计划 §3 第 9 项的统一措辞书写。

### S3-F2：终态确认后的无界等待会阻塞 worker drain（非阻塞）

- 类型：非阻塞建议；是否阻塞：否
- 位置：`vnext/backend/src/gateway_backend/operations/worker_runtime.py:259-306,359-363`；`vnext/backend/src/gateway_backend/bootstrap/operation_worker.py:684-690`；handoff §11.4
- 依据：`completion_acknowledgment()` 已确认 durable terminal 状态后，heartbeat 遇到 `StaleWrite` / `LeaseExpired` 时执行无超时的 `completed.wait()`。若 executor 在线程中提交终态后卡住，runtime 无法离开 wait 去处理 drain intent、调用 drain timeout 检查或回到 claim loop。SIGTERM/SIGINT handler 只设置 `stop_requested`，不会唤醒 `completed.wait()`；worker Compose 的 `stop_grace_period` 为 180 秒，之后 Docker 可用 SIGKILL 结束容器。
- 触发场景与影响：终态已提交但 executor 未返回时，graceful drain 和停止会延迟；其他排队 operation 也会等待 worker 恢复或重启。该操作已是 durable terminal，不会被重置为 RUNNING 或重新领取。原未修复路径在 StaleWrite 后会无界 `thread.join()`，因此 executor 卡住时同样不能 drain；本次修复没有新增这类 operation 状态风险。无证据证明 executor 必定会在终态提交后返回，但该风险已如实披露，且 S3 A 层 operation 已在保护超时内进入终态。
- 最小修正方向：S3 不要求增加超时或改变固定预算；若后续需要强制 worker drain 上限，先由 owner 确认边界与 Contract，再按独立授权处理。
- 关闭标准：不作为本次 S3 exit 的关闭前置；handoff 对等待、drain、SIGTERM、180 秒后强制终止和 durable terminal 后果的描述准确。

## 3. 验收核对

| 验收项（执行计划 §2 S3） | 结果 | 证据 |
| --- | --- | --- |
| DC20：派生表 `source_table` 为 `VARCHAR(64)` 并校验长度 | 通过 | `snapshot_materialization/compose.py`；handoff §2、§3；超长使用既有 `COMPOSITE_LOGIC_FAILED` diagnostic。 |
| Preview 业务物化、XML/EMPTY 摘要、规范状态范围 | 通过 | Preview 走 `materialize_business_snapshot`；缺省 XML 使用稳定 EMPTY 来源进入 `snapshot_digest`；composite 经过规范投影进入存储、比较与风险；见 handoff §6。 |
| DC8：无效 logics.xml / composite 业务不变量失败 | 通过 | Preview 返回 FAILED 并沿用 P3-R3 公开 diagnostic；focused 测试与 handoff §2、§11.1。 |
| composite 规则、canonical golden、checkpoint / digest | 通过 | 规则沿用 S2a 事实；golden 明确列出键、保留、ignored 与 compare-excluded 列；checkpoint 未加字段或兼容层。变化原因逐项见 handoff §6。 |
| 生产路径测试 owner 与 canonical baseline 不变量 | 通过 | `test_comparison_canonical_domain.py` 恢复原测试名和全表 UNCHANGED / 零记录；Repository fixture 走生产业务物化与投影，包含零行 composite 表。 |
| Compose XML-only 公式旅程 | 通过 | 扩展既有 History Compose；公式变化使 `formula_digest` 变化、composite 行 MODIFIED，History 记录 1；测试 serial，无新独立栈。 |
| 8 个 S3 unreachable modules 移出基线 | 通过 | 最终 `import_rules` 为 0 import violation / 0 runtime cycle / 6 unreachable；预计 14 降至 6。 |
| V 权威 runner 与镜像 provenance | 通过（S3-F1 已关闭） | V clean，runner exit 0；用例数为 shared_kernel 242、repository_contracts 152、repository_client 154、backend 2,839 parallel + 36 serial、Repository Service 1,684 + 1 skipped / 205。RS identity 的两个 provenance label 与 V 上计算值相同。V 镜像记录见 handoff §7。 |
| 真实数据：t1、t4 当前 V，t2、t3 沿用 | 通过 | 最终 V t1 和 t4 日志分别记录完整冒烟及完整旅程；t4 `run6` exit 0。f73 日志证明 t1、t2、t3 各档 journey 完成，但整个四档命令因 t4 v1 Submit 的 HTTP 500 以 exit 1 结束；更正后的 handoff 不再声称该整次 run 通过。按 owner 决议和精确路径审计沿用 t2/t3。 |
| 汇总对照、离线 composite 计数与原有不变量 | 通过 | 四档 composite v1/v2 行数均相等且 UNCHANGED，ADDED/REMOVED/MODIFIED/History records 均为 0：t1 4、t2 45、t3 201、t4 435。Catalog 去除 composite 后行数分别为 t1 3,729/3,727、t2 73,648/68,864、t3 122,251/122,257、t4 246,359/246,439，与 S2b 相同；History 为 t1 0、t2 11,511、t3 744、t4 168，与 S2b 相同。Preview v1/v2 table_count 与 changed 分别为 t1 125/125、125/4；t2 209/209、220/57；t3 192/192、193/54；t4 312/312、312/26；degraded/failed 均为 0。INITIAL 为空；v1 重传全表 UNCHANGED、Submit 为 `NO_CANONICAL_CHANGE`；IEC104 与 DC29 keyless 项符合 S2b。t1/t4 来自最终 V；t2/t3 来自各自成功的 f73 逐档 journey。详见 handoff §8–§10。 |
| A/B/C 与 operation 保护超时 | 通过 | handoff §9–§10 逐步记录 wall/CPU/A/B/C；最终 t1/t4 的 operations 均在保护超时内终态，状态查询无 500、503 retry、StaleWrite 或 worker restart。 |
| 第二次 STOP 修复与 owner 四点 | 通过 | 真实调试“未复现”500 / StaleWrite，未找到 >5 s 写事务 owner；去掉修复时确定性测试失败；read-only `BEGIN` 消除 GET 通过 `BEGIN IMMEDIATE` 遇锁再落入 500 的机制路径。StoreBusy handler 的全局 503、受影响 POST 路由、其他 GET 事务模式以及 `completed.wait()` 后果均在 handoff §11 列明。 |
| 停止条件与设计 §14 | 无触发（S3-F1 经 owner 澄清不构成违规） | 8 份 XML 均 COMPLETE，来源表名不超 64 字符；Preview degraded/failed 均为 0；S2b 汇总中 composite 之外无变化；未改 Contract/wire/schema/固定预算/Dockerfile/Compose/依赖；S3 unreachable 模块已移除；S4 尚未开始。 |

## 4. 实际执行的检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 五包 Ruff + mypy | 在 `/home/dev/gdds-p5-s3-review-final` 的 detached H=`96c835a` 中，逐包运行 `UV_PROJECT_ENVIRONMENT=/tmp/gdds-p5-review-final-env-<package> ../scripts/uv-consume.sh -C . run ruff check .` 和 `... run mypy` | 全部通过：shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 476 source files。 |
| import_rules | `UV_PROJECT_ENVIRONMENT=/tmp/gdds-p5-review-final-env-backend ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`（backend detached H） | exit 0；0 import violations / 0 runtime cycles / 6 unreachable modules。 |
| V 权威 runner 证据 | 审阅 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-dc9c08a4-authoritative-20261018.log` 与 provenance | clean V 起止一致，exit 0；计数与 provenance 见 handoff §5、§7。未重跑 runner。 |
| t4 最终真实数据 | 审阅 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-post-fix-t4-final-run6-20261018.log` 及 preflight | t4 完整旅程 exit 0；preflight 无 Dolt、无 Compose project、8000 空闲，记录 nproc/loadavg 和全部容器。未重跑真实数据。 |
| t1 / f73 运行状态 | 审阅 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-post-fix-t1-20261018.log`、`s3-realdata-v-f73deee6-journey.log` | t1 最终 V 通过；f73 的 t1–t3 逐档通过，t4 v1 Submit HTTP 500，整次 exit 1。 |
| final H carried | 审阅 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-h2-carried-20261018.log`、`s3-final-h2-preflight-20261018.log` | clean H=`96c835a` 的 RS build-input/source-tree identity 与 V provenance 一致；同 worktree 下连续两次 backend/worker image ID 都等于 V provenance，两次之间未运行测试。protected client/base ID 在 carried 前后不变。 |
| STOP / deterministic debug | 审阅 handoff §1、§11 与 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-debug-deterministic-repro-20261017.log`、debug run/compose logs | 真实 debug 未复现；无修复时的确定性失败和插桩事实与 handoff 一致。调试日志不作为门禁证据。 |
| 候选区间与工作树状态 | `git diff --name-status c3bb549aeca2d09a52cf397b09aea42947f57378..96c835ac90c597ce7cd35c351f9c567925d9d5ef`；检查 main、p5-s3 refs/status | 最终 H 相对旧 H 只修改 handoff；审查开始时 main=`c09c95fd81f889bc85a7630d1722f6ed5165f6e9` clean，p5-s3=`96c835ac90c597ce7cd35c351f9c567925d9d5ef`。未在实现 worktree 修改代码，未打 tag、未合并、未推送。 |

## 5. 验证限制与剩余前置

没有重跑完整 runner 或真实数据旅程；按审核提示核对外部日志。真实 debug 没有查明最初超过 5 秒写锁的 owner，故结论限于确定性复现和只读事务机制分析，不声称找到了原现场持锁者。t2/t3 未在最终 V 重跑，沿用范围限于 handoff 列出的 `f73deee604..V` 文件没有改动 composite 物化、投影、比较、规范存储或 census 业务路径。初审时，V runner 的 client tag 副作用是唯一阻止 S3 exit 的 finding；owner 澄清后已关闭。

## 6. 定稿核对（2026-10-18）

owner 授权审核方直接定稿、提交与合并，实现方与初审方不再介入。定稿前在只读状态下复核了以下事实，均与初审和 handoff 一致：

- `dc9c08a410..96c835ac90` 只改 `plans/p5-arch-closure-s3-handoff.md`（3 个提交）；`p5-g11b-exit..H` 共 29 个提交，均带 trailer。
- `s3-final-v-dc9c08a4-authoritative-20261018.log`：起止 HEAD 都是 V，起止 clean，`runner_exit_code=0`。
- `s3-post-fix-t4-final-run6-20261018.log`：HEAD 为 V、clean、`runner_exit_code=0`、`conclusion: PASS`；`s3-post-fix-t1-20261018.log`：`real_journey_exit=0`，两处 `conclusion: PASS`。
- `s3-final-h2-carried-20261018.log`：起止 HEAD 都是 H、clean；RS 两个 label 与 `s3-v-dc9c08a4-provenance.json` 一致（`adc5d87f…` / `sha256:5b34d0c5…`）；用 V 的 project `ordered-bisect-b-2871524-baseline` 连续两次构建，backend `sha256:88f61746…`、worker `sha256:eb8e6d23…` 均与 V provenance 相同。
- 本地镜像：`-base:local` 为 `dafde407833e`（12 层），`:local` 为 `55c506d6ef48`（20 层，label 为 V）。

剩余观察：S3-F2 不阻塞，若后续需要强制 worker drain 上限，另行授权。G12 第 1 项完成并打 `p5-g12-exit` 之前，不开始 S4。
