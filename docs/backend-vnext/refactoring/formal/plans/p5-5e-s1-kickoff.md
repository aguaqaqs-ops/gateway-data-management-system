# P5-5E-S1 Kickoff Gate

状态：**PASS — S1 实现可启动**

日期：2026-09-23。

核查基线：`6707a1ca01c7325220ec47261b4b69a6232313ab`（主工作区 HEAD）。
权威执行计划：[p5-5e-history-compare-execution-plan.md](p5-5e-history-compare-execution-plan.md) §3 S1。

本记录为只读 kickoff gate；不授予 S2+、不签署 stage exit、不跑实现测试或容器门禁。

## 1. Gate summary

```yaml
kickoff_gate: pass
p5_5d_slice_exit: pass
p5_5d_gate_head: af833695ef1c16b1ea0744d1b6eff6b5ada9924c
implementation_baseline_head: 6707a1ca01c7325220ec47261b4b69a6232313ab
vnext_diff_gate_to_baseline: 0 lines
workspace_schema_version: 5
design_revision_required: no
s1_implementation_authorized: yes
```

## 2. 5D slice exit 前置

| 项 | 证据 | 结论 |
| --- | --- | --- |
| Slice exit 签署 | [p5-5d-slice-exit-final.md](p5-5d-slice-exit-final.md)：`p5_5d_slice_exit: pass` | pass |
| Gate-tested HEAD | `af833695ef1c16b1ea0744d1b6eff6b5ada9924c` | 与 exit 记录一致 |
| Gate → 实现基线 `vnext/` | `git diff af833695ef..6707a1ca01 -- vnext/` | **无差异** |
| 5D 历史 S1 文档缺口 | 5D exit 已接受限定豁免 | 不阻塞 5E kickoff |

## 3. 表形、port 与 submission 字段（Plan S1 kickoff 重核）

设计 §3「D 表字段警示」已声明 accepted 设计字段名可能与实现列名不同；以下以 **5D 最终实现** 为准。

| 设计/计划关注点 | 实现事实（`6707a1ca01`） | 判定 |
| --- | --- | --- |
| Workspace schema 版本 | `WORKSPACE_SCHEMA_VERSION = 5`（`vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py`） | pass |
| `baseline_node_records` | 存在；`commit_id`（非设计摘要名 `business_baseline_commit_id`）、`kind`、`parent_node_id`、`source_submission_id`、frozen scope 列 | pass — 映射至 `BaselineNode.commit_id` |
| `baseline_head_records` | 存在；`repository_id`、`node_id`、`optimistic_version` | pass |
| `archive_disposition_records` | 存在（v5 archive migration） | pass |
| Baseline 读 port | `BaselineHeadReadPort`：`domain/baseline/ports.py`；adapter DTO `BaselineHead`：`domain/workspace/models.py` | pass |
| Archive disposition 读口 | `domain/archive/ports.py` `list_dispositions_for_submission` 等 | pass |
| Submission commit 字段 | `Submission.repository_commit_id`、`Submission.business_baseline_commit_id`（`domain/submission/models.py`） | pass |
| v6 DDL / integrity 表 | 未创建 | 符合计划 — S2 交付，S1 禁止 |

**无需修订设计 §3/§4/§6.4**：设计已预留 kickoff 重核；实现与 5D accepted 语义一致，仅 baseline 节点列名为 `commit_id`。

## 4. initial-empty 与零表旅程证据

5E 不能仅凭 5D slice exit pass 省略下列逐项挂接。证据链如下：

| 层级 | 权威记录 / 测试 | 结论 |
| --- | --- | --- |
| 5D-S1 stage exit | [5D Execution Plan](p5-5d-archive-execution-plan.md) §S1：**pass**；含 initial-empty preview 修复与 focused gate | pass |
| 5D-S1 focused（零表 preview/submit） | `tests/test_preview_job_assemble.py`：`test_empty_baseline_assemble_produces_ready_closure_and_matching_digest`、`test_empty_baseline_assemble_produces_ready_closure_for_table_addition`、`test_empty_baseline_submit_accepts_table_addition`、`test_empty_baseline_submit_rejects_no_canonical_change_before_attempt`；harness `tests/support/preview_job_harness.py` `empty_baseline=True` | 可核对 — S1 前置链路存在 |
| 5D-S4 真实零表 compose | `tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect`；[5D S4R2 acceptance](p5-5d-s4r2-independent-acceptance.md) T3 记录 passed | pass |
| 5D S4R2 签署缺口说明 | S4R2 注明 initial-empty **owner sign-off** 未能从记录独立核对 | **注意项** — 不阻塞 kickoff；5E-S3 零表腿仍为必跑项，须以冻结输入实跑 |

**Kickoff 判定**：5D-S1 pass + focused 测试 nodeid + S4 compose 零表旅程证据对应齐备 → **pass**。
5E-S3 `test_history_compose_e2e.py` 零表腿仍为必跑项（执行计划 §3 S3 / 设计 §8）。

## 5. S1 实现范围确认（不变）

按已接受执行计划，S1 **仅**交付：

1. History 读查询与 `HistoryTreeProjection`；
2. `GET /v1/history` HTTP 读面；
3. production wiring（`http/wiring`、`dependencies`、registry 等计划内文件）；
4. focused 单元/集成验证（计划 §3 S1 文件预算）。

**明确不在 S1**：compare accept、3-step operation job、integrity record/v6 migration、
internal-bearer ack 路由、materialization 公开面改动（属 S2 窄例外）。

## 6. 停止条件（kickoff 未触发）

以下任一成立则 **停止 S1** 并回设计/计划修订，不 stage 内绕过：

- `p5_5d_slice_exit` 失效或 `vnext/` 自 gate HEAD 起出现未验收业务改动；
- workspace schema ≠ v5 或 baseline/archive 表形偏离上表；
- initial-empty / 零表证据链断裂；
- kickoff 发现需新建 v6 DDL 才能完成 S1 读面。

当前核查：**均未触发**。

## 7. Container / 验证边界

```text
Container rebuild required: no (kickoff 只读核查)
Current container gate: not-applicable
Last verified 5D image revision: af833695ef (see p5-5d-s4r2-compose-gate-provenance.json)
S1 末候选 fresh-image 节点: 见 execution plan §6.1
```

本轮未运行 pytest、ruff/mypy、权威 runner 或镜像构建。
