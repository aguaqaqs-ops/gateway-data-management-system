# V2 归档核验与关闭出口独立审核

2026-11-07。V2 新独审角色 `/root/be_v2_review`，依据 [V2 工作单](p6-v2-work-order.md)、[归档业务设计](p6-archive-business-validation-design.md)、[联合 kickoff §1.1/§4/§6](p6-be-a-d-kickoff.md)、[设计终审 §6](p6-be-a-d-archive-design-review.md)、V1 最终 [handoff §7](p6-v1-handoff.md) / [独审 §11](p6-v1-review.md) 及实际 owning Contract。只写本报告，不改产品、测试或前端；不新增子角色。

## 1. 起点与当前结论

V2 产品起点为 `5dc01deeb543d4bdc07da02b0e0c6ba1f1472533`，协调启动提交 `d0add6bd16ff8ebb902d849a5feef2529713f3de` 只改文档。基线只读 detached worktree 为 `/home/dev/gdds-reviews/p6-v2-baseline-d0add6bd16`，clean、legacy 链接已核。V1 当前最终产品为 `c229582a9e72a591cf00a70de526b1b0792c1c18`，handoff `6183ae3ca4`、独审 `5dc01deeb5` 已关闭 F1–F5/N1；不沿用早先 3dd GO 的完成含义。

**当前已完成准备及首个子候选静审，尚无 V2 产品 GO。** 完整固定候选和专用节点证据仍待本角色复核。设计 GO 不能替代产品审核；04 联合权威/必要 Compose、05 fresh t1、D 与 FE3 不在当前结论内。

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

清单预检没有核心设计阻塞。已直接交实施者补充 owning Contract 精确路径、明确实际 DDL owner `test_control_db_schema.py`，并把 digest preimage 写成精确的一次 SHA256 公式；补充 `8cd19a9217` 已核收，History 文件名笔误在 `35c4a20456` 已修正为 `p5-5e-history-compare-design.md`。此预检不代替代码或证据结论。

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

## 6. 首个子候选 35c4a20456 代码审

固定子候选 `35c4a20456`，只读 detached worktree `/home/dev/gdds-reviews/p6-v2-code-35c4a20456`，clean/legacy 已核。实施者明确它尚未验证且不是出口候选：持久 subject 正文/fingerprint 校验、Start 成功 replay closure、增量事务/HTTP/History 测试、benchmark consumer、正文与 golden 仍在补齐，本轮不把这些已声明待办误记为已交付或产品 GO。

已核纯规则按完整四字段内容身份建立固定点，未知同根/无锚环不互证；只将未解释状态放进弱连通分量，已解释终点不会把独立未知根错误合组；完整成员/边/facts 进入 subject。source/time 原诊断和接受状态分离，全部候选参与时间质量与倒退诊断，baseline 历史质量不重开，规则 A→B 与时间分组大体符合设计。以下普通修复已直接交实施者，同角色复审。

### F1（P2）：INITIAL_EMPTY 的 modified/initial 比较未标不适用

`business_validation.py` L159 仅在 `baseline is None` 且 relation 不是 `MODIFIED_BEFORE_INITIAL` 时返回 `NOT_APPLICABLE`。真实首次 MODIFIED_ONLY 的 V1 facts 为 `initial_origin=INITIAL_EMPTY`、initial 时间为 null；它的 modified/initial 关系也引用不存在的 baseline，却被显示为 `NOT_COMPARABLE`。业务设计 §3.3 要求此类比较 N/A；只有 FULL 两实际上传侧仍比较。由纯规则 owner 修正并补实际 INITIAL_EMPTY 小向量，不复制时间 grammar 矩阵。

### F2（P2）：CLOSE 跨目标幂等冲突遮蔽已存关闭绑定损坏

`manual_close.py` L68 在 existing target 与请求 target 不同后直接返回 409，早于 `_assert_manual_close_binding`。A 成功关闭后，若 A 的持久 `configuration_facts_digest` 损坏为另一合法 digest，当前授权 caller 以相同 key 请求关闭 B，会得到普通冲突而不是既定完整性错误。设计 `043705af06` 要求仍校存储关闭事实/原请求绑定，不能把损坏伪装成冲突；V1 cross-target existing-key 已有同原则。请求 B 授权后，内部 existing A 应经 scoped bound 读取和原事实校验，再决定正常跨目标 409；不披露 A 内容。CLOSE/HTTP 原 owner 验证该边界。

### F3（P2）：候选 Attempt 损坏未映射为 Archive 完整性 503

`closure.py` L48 裸调用 finalized Attempt getter；合法授权候选的 Attempt `configuration_facts` 缺字段/源绑定损坏时，mapper `ValueError` 绕过 `ArchiveIntegrityFailure`，而新 snapshot 仅捕获 candidate Submission mapper 的同类错误。应在 Archive owning seam 窄映射已知 decode/binding 错误，保持硬拒并返回实际 HTTP `503 ARCHIVE_INTEGRITY_FAILURE`；HTTP owner 用非 strict server-exception 模式断言分类及无写入。baseline source Attempt 分支已覆盖同类窄映射，无须全局异常框架。

### F4（P2）：Start 可把合法上界 Head 推进至不可引用的整数

`start.py` 仍以 `head_record.optimistic_version + 1` 推进，BaselineHeadRecord 与基线 DDL 只约束非负，Start response 的版本仍为普通 int。若当前 Head 为合法协议上界 `9007199254740991`，完整确认/Start 可以提交 `9007199254740992`，产生下一轮 HTTP/application 无法引用的 Head。按已定 Head I-JSON 范围在写入前明确拒绝溢出，必要模型/DDL/响应约束同步；原事务 owner 以设定 max Head/facts 的小向量验证无 Plan/Node/Result/Workspace 副作用，不迭代大数据。

此子候选不作 V2 完成结论，容器结果仍 `deferred`。测试/编译/lint 由实施者在 06 执行；审核者本轮只读代码，尚未核其日志或现场。

## 7. 修复候选 7878e41ad3 代码复核

固定候选 `7878e41ad3`，新只读 detached worktree `/home/dev/gdds-reviews/p6-v2-code-7878e41ad3`，clean/legacy 已核。F1 的真实 INITIAL_EMPTY N/A、F2 的内部既有关闭来源先校验、F3 的候选 Attempt 窄异常映射、F4 的 Head max 写前拒绝及模型/DDL/响应限制均已见代码修正与对应小向量；执行证据尚待核收，暂不据此关闭。新增 closed business response 模型已描述来源、时间、issue、审计 subject 与 Result 冻结诊断，原 opaque DTO 收口建议已采纳。

新 audit 校验从持久完整 subject 重算摘要，并核事件与原请求、sequence、action、actor-bound fingerprint；preview/Start/原 append replay/审计读取均调用。新增成功 Result/Start replay helper 读取冻结原候选与原 Head 来源，不检查当前集合/occupancy；公开 Result 已先按 exact scope SQL 过滤再解正文。benchmark consumer 仅接受已限定 subject kind，并从显式 reason map 取得逐项原因，缺理由拒绝，不提供 force。完整 owning 正文、golden、必要小 Compose 与本轮验证仍由实施者补齐。

### F5（P2）：原成功闭包缺少冻结 selection confirmation 的来源校验

`integrity.py` 比较 frozen confirmation references、Plan references 与 Start fingerprint，却从未读取被引用的 confirmation event。成功单候选归档后，该 mandatory selection confirmation 丢失或损坏，GET/Start replay 仍会通过。应验证冻结原 sequence 的 scope/subject、CONFIRM 和 actor-bound 原请求绑定，不重查当前 latest 或新门禁。由原事务/HTTP owner 验证一个小型损坏向量。

### F6（P2）：原成功 replay 可从已变更 Submission 返回不同 commit

同 helper 只比较当前 Submission 的 configuration facts digest，不比较 selected `repository_commit_id` 与冻结 Plan/Node。若成功后该字段损坏为另一合法字符串，helper 仍可通过，而 `start.py` replay 再从当前 Submission 取 baseline commit，返回与原 Plan/Node 不同的值。须校原不可变绑定，并从冻结 Plan 返回原 commit；损坏硬拒。既有 `assert_submission_attempt_binding` 并不检查 repository_commit_id，复用它也不能代替这一显式绑定。不得为该修复引入当前 occupancy/Head/新候选门禁。

F5/F6 已直接交原实施者处理。另要求 audit owner 用一个两成员来源组 consumer smoke 核完整 states/edges/affected 冻结及接受后仍 UNEXPLAINED，不复制纯图矩阵。本角色仍未执行产品测试或占用节点；尚无整体 GO。
