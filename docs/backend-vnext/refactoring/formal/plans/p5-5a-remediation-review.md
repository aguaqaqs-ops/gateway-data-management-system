# P5-5A Remediation Review

状态：**PASS — remediation review 闭合；HOLD 保留；S6 未授权**

日期：2026-09-12

Owner：Architecture Acceptance

上游：[P5-5A Upload/Preview Execution Plan](p5-5a-upload-preview-execution-plan.md)、
HEAD `33bf0fb9`（parent `dd1c8c4d`）。

```yaml
stage: remediation_review
candidate_head: 33bf0fb9bf09a93b0bcff7ae04c0ad73b218eddf
parent: dd1c8c4d90196ebb05c09d67ae4ad365fe0a229a
conversation_context: independent_review
remediation_review: pass
hold: retained
s6_authorized: no
container_gate: stale
container_rebuild_required_at_s6: yes
next_step: P5-5A-S6
next_step_authorized: no
```

本轮仅判定 remediation review 通过；**不解除 HOLD，不进入 S6，不宣称 slice exit pass**。

## 1. Remediation items closed

| # | 级别 | 来源 | 结论 | 实现要点 |
| --- | --- | --- | --- | --- |
| 1 | P2 | `33bf0fb9` 前一轮复审 | 已闭合 | `parse_streaming_multipart` 在 `mkdtemp` 前要求 media token（大小写不敏感）为 `multipart/form-data`，否则 `422 REQUEST_VALIDATION_FAILED` |
| 2 | P3 | `33bf0fb9` 前一轮复审 | 已闭合 | `test_stalled_body_times_out_while_waiting_for_next_chunk` 同时具备 `unit` 与 `serial` marker |

此前 session 重读、stream deadline、multipart bounds、protection transfer/cancel cleanup 等定向整改未见回退。

## 2. Verification matrix

| 检查项 | 结果 |
| --- | --- |
| 非 multipart media | `422 REQUEST_VALIDATION_FAILED`；未读取 body、未创建 staging |
| 大小写混合 `MuLtIpArT/FoRm-DaTa` | 正常接受 |
| stalled-timeout 测试 marker | `unit` + `serial` |
| Backend focused | 30 passed |
| ruff + mypy | 通过，308 files |
| `uv lock --check` | 通过 |
| `git diff --check` | 通过 |
| 工作区 | clean；HEAD/parent 正确 |
| compose.yaml SHA-256 | `113224e1ba968ed2ce588640d7fb07c7f8f2bb10ce136dd444f314dbe6591c81`（`dd1c8c4d` 以来未改） |

## 3. Container provenance（stale 确认）

`dd1c8c4d` 与 `33bf0fb9` 未触碰 Compose/Dockerfile/entrypoint/env 接线，**本轮不重建镜像**。
旧镜像不得表述为 current-HEAD 已验证。

| 项 | 值 | 说明 |
| --- | --- | --- |
| last_verified_image_revision | `sha256:7a8e2834e67f0131092b575e8ce11c0d02dcdcee219699ee5d22d07629d18faf` | `218d4a24` 时 `deploy-backend`；**historical** |
| last_verified_source_tree | `sha256:8dfc303b3019e6436842e1a170702eb1a1bc929ff0bce16c9bf27f6eb4f59eaf` | 配对 `218d4a24`；**historical** |
| current_source_tree | `sha256:68682f21bff051de42908d5c84b019a525054bff535436051cf4c99b0636104a` | `33bf0fb9` candidate |
| compose.yaml | `sha256:113224e1ba968ed2ce588640d7fb07c7f8f2bb10ce136dd444f314dbe6591c81` | 未变 |
| container_gate | **stale** | 旧镜像源码摘要与当前源码不同；S6 须重建并记录新 digest |

历史 P4 image 一律标 `historical`，不得关闭本 HEAD 的 container finding：

- `sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf` — historical (P4-R3)
- `sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95` — historical (P4-R5)
- `sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b` — historical (P4-R4)

## 4. Authority boundary

- `p5_5a_implementation`：S1–S5 代码已落地（`6532a6eb` → `33bf0fb9`）
- `p4_r6_exit`：仍 **pending**
- `p5_5a_slice_exit`：仍 **pending**（等待 S6 独立授权）
- [P5-5A S5 Handoff](p5-5a-s5-handoff.md)：**superseded**（脏树 `774bacb6` 语境；S3/S4 已在 `18e7155a` 提交）

## 5. Next step

S6 slice acceptance 已完成，见 [P5-5A S6 Handoff](p5-5a-s6-handoff.md)。

- `p5_5a_slice_exit`: **pass**
- `hold`: **released**
- `container_gate`: **deferred_rebuild_blocked**（rebuild 尝试因 Docker 内 rust-lang 网络不可达失败）
