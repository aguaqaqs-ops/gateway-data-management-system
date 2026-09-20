# P5-5D-S0 Independent Docs Acceptance

状态：**PASS — 文档审核通过；Business Lifecycle 3.0.0 accepted；implementation 未授权**

日期：2026-09-20。

评审者：本会话 Codex reviewer（审核用户提供的文档，非初稿编写者）。
授权依据：用户明确授权“如果已具备条件，直接标记 P5-5D 文档审核通过”；
随后提交固定归属 Contract 补充供复审。该授权在本次剩余条件满足后执行。
本记录不声称获得未参与本会话的人员签署。

## 1. Decision and authority

```yaml
independent_docs_review: pass
p5_5d_design: accepted
p5_5d_execution_plan: accepted
business_lifecycle_contract_version: 3.0.0
repository_scope_contract_amendment: accepted
p5_5d_s1_contract_precondition: satisfied
closed_document_findings: 4
open_document_findings: 0
p5_5d_implementation_authorized: no
first_authorized_implementation_stage: none
production_deployment_authorized: no
new_repository_effect_authorized: no
p5_5d_slice_exit: not_evaluated
next_step: separate_p5_5d_s1_implementation_authorization
```

接受 [Entry Brief](p5-5d-s0-entry-brief.md)、[Archive Design](p5-5d-archive-design.md)、
[Execution Plan](p5-5d-archive-execution-plan.md) 及
[Business Lifecycle §1A / §9A](../contracts/business-lifecycle-and-state.md#repository-scope-ownership-amendment)。
固定归属补充以不兼容版本 `3.0.0` 生效，前版为 `2.0.0`。没有剩余文档阻塞项。

S1 设计及 Contract 前置已齐备，下一步由用户向实现者明确授予 S1 实现范围。
initial-empty 修复、schema v5、seed/reader 接线及全部运行验证仍是实施交付项；本次未启动实现，
未推进 5D slice exit，也不授予 production migration/deployment 或新的 Repository effect 权限。

## 2. Findings closure

| Finding | 结论与依据 | 实施验证 owner |
| --- | --- | --- |
| P1 initial-empty 执行预算遗漏 | closed：Design §2.1、Execution Plan S1 明确空 checkpoint 阻塞、原 owner 精确修复预算、完整 pipeline/digest 与恢复验证；不能用零行表替代零表仓库 | Preview/Comparison/Submit 原测试 owner，最终真实 Compose journey |
| P2 audit fingerprint 漏绑定 | closed：Design §3.2/§4.2 覆盖 selected、candidate-set 和全部语义请求；同 key 改绑定冲突，subject 过期后的同请求仍可重放 | test_archive_audit.py |
| P2 Repository→scope 反向基数缺失 | closed：Contract §1A 明确固定归属、含 disabled/history 的原子拒绝、mapping 移走不释放归属、同 scope 合法复用、新 Repository 改绑、当前历史权限与重开条件；§9A 和 Design §6 验收一致 | migration/query/transaction/HTTP 各原 owner，沿用 Design §9 |
| P2 字符与字节上限不一致 | closed：ID/key 255 UTF-8 bytes、reason 4096 UTF-8 bytes；HTTP/Application 同规则及中文/四字节边界 | test_archive_http.py |

前三项沿用本会话上一轮复审结论；本次重点核对最后一项 Contract 补充及关联文档同步。
固定归属以已有 INITIAL BaselineNode 为事实依据，不增加归属 registry 或状态机；
同 scope 多 actor 不受影响，跨 scope 共享/转交须重开 Contract。未发现新增阻塞 finding。

## 3. Reviewed workspace and evidence

Current HEAD：`16f4112ee10536c3c8b82765167ff0454ad5f05f`；工作区为 dirty，审核对象包括未提交文档，不能只用 HEAD 定位本次设计。
下面记录接受后的九份文件 SHA-256，不包含本审核记录本身，避免自引用摘要。
文件集合按仓库相对路径排序，UTF-8 行格式为 `path\tsha256\n`：

- 接受前审核输入集合摘要：`sha256:f0b6be5ecff124cbc2c7c297a88ddd8970ec215e9167ebb3c59ab3c026cb83dd`。
- 接受后九文件集合摘要：`sha256:5d75e02a01d7f5cab2380b6ac9a862a8275dcd228eef2c254dc5294265faae36`。

| 文件 | SHA-256 |
| --- | --- |
| `docs/backend-vnext/README.md` | `7310e42c2c3767395c6dc745d00c7f5b7ff30c01fa7385ba3e11c4e9090a34c3` |
| `docs/backend-vnext/refactoring/formal/README.md` | `ad4f4aa0debdda163761ce1022ab5777bd50b22a49a6a29f4b094979016eb6b1` |
| `docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md` | `ea2817b185cc54e378dbf1e4954cb326a16e23311581200627d6e74d01f37152` |
| `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md` | `93fe45504cd40b0aa9f622cc9fe975b0e8820c9db8017d87eae837d61c0bd6c5` |
| `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md` | `45a623e37cc15c496f05aacc4b8e8f2eb8a047442a229352a93f731ada3bc99e` |
| `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-design.md` | `1ee5fa234da7d27fc373fa832e08b8692f38f3c0a85f117c13cd6ad01d141dbb` |
| `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md` | `0101fdc8615a10d9c19c9e5d3dfc0350f10ba0f2b91abc7f6f43f3d4df17fb0c` |
| `docs/backend-vnext/refactoring/formal/plans/p5-5d-s0-entry-brief.md` | `ea659966c1cfa59c3b8cd052e531d2c78378aff3b37fac99c99ae6a0e669d13e` |
| `docs/backend-vnext/refactoring/formal/plans/p5-business-vertical-slices-design.md` | `2c260167f0c51390b35f357cda9fc8f88b8c5b1e4f75f352db345c649c23aaf6` |

本次检查通过：10 份文档的 293 个相对链接/锚点、九份接受文件 SHA-256、
状态与授权一致性、`git diff --check`、源码禁区差异检查。
审核接受时未修改源码、测试、依赖或部署，未运行实现测试、五包静态检查、全量 runner 或容器门禁，未提交 Git。

2026-09-20 文档提交前补充：用户已授权提交；五包 ruff/mypy 全部通过。修正 P5 总纲 §13
残留的 Contract 前置未解除表述，与 accepted 3.0.0 一致，并同步上表及集合摘要。
本次仍不运行实现测试或容器门禁，不改变审核结论及 implementation authority。

Container rebuild required：no；原因是 docs-only 审核接受，未触碰容器边界，亦非实现阶段退出。
Current container gate：not-applicable。最后验证的 image revision 为 `04317788c2`，
source-tree 为 `sha256:9b7f863c4d24596fdddb3bbd82a4e5b25a85fcf1af26dd8af2124dbb06c885d9`；
实际 image IDs 见 [5C 历史接受记录](p5-5c-s5-independent-acceptance.md#acceptance-and-evidence)，本轮未复跑。
后续必须执行点：S1 最终候选及此后触发容器边界的节点，5D 最终 fresh-image conjunction；
精确测试范围见 Execution Plan §4 / §6。
