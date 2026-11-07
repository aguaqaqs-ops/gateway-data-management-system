# V2 归档核验与关闭出口独立审核

2026-11-07。V2 新独审角色 `/root/be_v2_review`，依据 [V2 工作单](p6-v2-work-order.md)、[归档业务设计](p6-archive-business-validation-design.md)、[联合 kickoff §1.1/§4/§6](p6-be-a-d-kickoff.md)、[设计终审 §6](p6-be-a-d-archive-design-review.md)、V1 最终 [handoff §7](p6-v1-handoff.md) / [独审 §11](p6-v1-review.md) 及实际 owning Contract。只写本报告，不改产品、测试或前端；不新增子角色。

## 1. 起点与当前结论

V2 产品起点为 `5dc01deeb543d4bdc07da02b0e0c6ba1f1472533`，协调启动提交 `d0add6bd16ff8ebb902d849a5feef2529713f3de` 只改文档。基线只读 detached worktree 为 `/home/dev/gdds-reviews/p6-v2-baseline-d0add6bd16`，clean、legacy 链接已核。V1 当前最终产品为 `c229582a9e72a591cf00a70de526b1b0792c1c18`，handoff `6183ae3ca4`、独审 `5dc01deeb5` 已关闭 F1–F5/N1；不沿用早先 3dd GO 的完成含义。

**当前仅完成审核准备，尚无 V2 产品 GO。** 精确实施清单、固定代码候选及专用节点证据均待本角色独立复核。设计 GO 不能替代产品审核；04 联合权威/必要 Compose、05 fresh t1、D 与 FE3 不在本准备结论内。

## 2. 风险与唯一验证 owner

| 对象 / 风险 | 本轮最小控制与唯一验证 owner |
| --- | --- |
| Submission、终局处置、ArchivePlan/Result、BaselineHead、Workspace 占用与首次成功命令结果，A 类权威事实 | archive transaction owner：同短写事务、精确 CAS、失败回滚、成功 replay、Start/close 与双 close 两种提交顺序；不逐 SQL 构造故障平台 |
| 接受/撤销的 append-only 个人审计事实，A 类 | audit owner：actor-bound append、subject 身份与失效、最新肯定 sequence、exact references、容量及递增安全整数边界；不把可撤销误当可重建事实 |
| 当前 permission/exact scope 与对象披露，A 类边界 | HTTP owner：permission-before-object、最小 target binding/scoped SQL 先于 full facts、当前授权后成功 replay、跨 actor CLOSE 原事实返回；授权内损坏须实际 HTTP typed 503，不以 strict TestClient 抛异常冒充 |
| 来源图、时间诊断与预览，C 类派生数据 | 单一纯规则 owner：完整身份固定点、未知弱连通分量、三时间关系与质量分组、跨规则身份、关闭桥接后的 UNKNOWN、8N+1 上界；接受不把 UNKNOWN/NOT_COMPARABLE 改成 PASS |
| History/Review/Result 组合读模型，C 类（披露边界仍 A 类） | History owner：ARCHIVE/MANUAL_CLOSE 两来源、分页与完整 snapshot、self-only；Review/Result 仅各自必要接线，不复制图/事务矩阵 |
| codec、DTO 和 mapper，D 类实现（公开输入边界仍 A 类） | 原 shape/digest/HTTP/OpenAPI owner：闭合字段、版本及 golden、UTF-8/body bytes、I-JSON safe integer；不新增兼容层或通用 evidence 状态机 |

本节没有需要另建的 B 类可恢复流程；既有辅助 durable workflow 沿原 owner。可信内网、协作同 UID 与单 control DB 的部署假设保持，不扩大同 UID 对抗模型。

## 3. 精确清单预检

固定清单提交 `0d7a714bfc`（产品写入前），审核以 `git show` 读取固定对象，没有读取实施中的 dirty 产品。已列 V1 四层事实、纯规则输入/诊断、统一处置/关闭字段、唯一 DDL、Archive 全部 digest 升 v2、核验 rule v1、HTTP/History/Review 目标 DTO 与 golden 路径。来源组沿既有代表 target 字段，但接受对象由服务端重算的完整 subject 决定，不接 caller affected 列表；与设计边界一致。

清单预检没有核心设计阻塞。已直接交实施者补充 owning Contract 精确路径、明确实际 DDL owner `test_control_db_schema.py`，并把 digest preimage 写成精确的一次 SHA256 公式；这些常规文档精度项尚待后续固定提交核收。此预检不代替代码或证据结论。

## 4. 已识别的审核接缝

- 来源与时间必须从当前 exact scope/current Head 和全部未处置 APPROVED durable facts 派生；不能仅核 selected、靠 SQL 过滤丢掉损坏候选，或把旧历史/关闭对象当来源锚。合法旧 A→新 B 身份边依设计 `a24b7034e9` 解释，未知版本/绑定损坏仍硬拒。
- 新 subject/fingerprint 必须绑定完整候选、facts/规则、relations/全部分组成员；来源组 append 只接 subject，服务器重算完整组。固定引用容量为 confirmation 1 / anomaly 1601，399 反例、1601 shape /1602、256 KiB 和安全整数分别交原 owner。
- CLOSE 先当前授权及最小 target binding，再合法 replay，再 fresh Head/APPROVED/精确 Workspace。它不依赖全图、容量、其他 Workspace Attempt 或先接受异常；旧 baseline 的合法占用仍可关闭。actor-independent CLOSE 与 actor-bound audit append 不混同。
- 统一 `submission_disposition_records` 必须覆盖 candidate 查询、Review closedness、ArchiveResult 装配、History 分页及完整 snapshot。删除旧表/类型/查询双路径；手工关闭不造 ArchiveResult、不动 Head/main、保持 APPROVED/OPEN/generation、清指针并 version+1。
- 新读 consumer 保留 V1 F5 的目标授权顺序；未知/跨 scope 对象先于完整 facts 解码被过滤。Archive 已定完整性边界使用窄 typed 503，不新增全局异常框架。

## 5. 证据与容器决策

```text
Reviewed preparation HEAD: d0add6bd16ff8ebb902d849a5feef2529713f3de
Container rebuild required for this report: no（仅审核文档）
Last verified V1 image revision: c229582a9e72a591cf00a70de526b1b0792c1c18
V2 current container result: deferred（不得冒称旧 V1 结果为 V2 结果）
Carried from: none
Required V2 evidence: 固定候选后 06 focused/Contract/五包静态及必要当前 Compose provenance
Joint final gates: 04 权威/必要 Compose；05 fresh t1，仍待联合最终候选
```

审核准备没有运行测试、编译、lint、容器或真实数据，也没有占用节点。06 上节 09:36:28Z 释放仅作历史；实施时须现场重核并取得有效标志。正式候选将另建只读 detached worktree；只读核原始日志、脚本、SHA、host/起止 HEAD/UTC/exit、offline/build-input、当前镜像身份及现场清理。focused 明确非 serial / serial 两批；实际零选择的 exit 5 只能记 N/A。
