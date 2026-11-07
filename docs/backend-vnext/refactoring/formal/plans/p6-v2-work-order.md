# V2 归档核验与关闭出口：实施准备工作单

2026-11-07。Owner已授权V2，**V1独审GO并结束本节两角色后才启动**；当前仅准备，不创建产品角色、不宣称已交付。依据[业务核验设计](p6-archive-business-validation-design.md)§3–§10、[联合kickoff](p6-be-a-d-kickoff.md)§1.1/§4/§6及[最终设计独审](p6-be-a-d-archive-design-review.md)§6。时间语法和异常容量已定，不重选B1/B2；MANUAL_CLOSE幂等澄清为设计者提交`043705af06`。

## 1. 实施/文件边界

本节交付当前轮次来源/时间诊断、逐项原因接受及撤销、Start原子验收、有理由关闭而不归档、单一终局处置及History/Review全部consumer。V1 facts作为不可变输入，不在Archive事务重扫SQL/Preview/产物或调用Repository；不恢复旧Python路径/旧return，不另建图数据库、持久诊断状态机、Archive Operation或并行closedness权威。tar归D，FE3页面由前端owner设计/实施，信息经Owner手动转发。

建议实施GPT-6.1-Sol/xhigh、独审GPT-6.1-Sol/max，理由是审计subject/回放、短事务、统一终局事实和多consumer闭环；实际创建等V1收尾后由协调者记录，每节两个新角色，无额外子agent。实施者写产品/测试/owning Contract及`p6-v2-handoff.md`；审核者只写`p6-v2-review.md`；协调者维护启动及总交接。开始前保护所有dirty、显式暂存，不推送、不改写引用提交/原冻结基准资源。

先在handoff提交精确新fields/schema/类型/版本/digest preimage、audit/HTTP/History DTO/OpenAPI/golden路径与唯一owner，再产品写入；从V1最终实际类型/端口出发，不用本准备文档猜未完成的V1字段。常规技术接线自主推进；改变权限、权威事实、事务/恢复或验收范围的核心缺口交协调者设计澄清。

## 2. 规则、身份与容量

- 仅exact scope当前baseline和同轮未终局处置APPROVED全集，最多200；PENDING/active Attempt按A1硬门禁，草稿不阻塞。旧历史/关闭/他scope不当来源锚，损坏不通过SQL过滤隐藏。
- 完整内容身份含规范集合/摘要、projection/ruleset/scalar。从当前baseline固定点扩展initial→modified，可匹配已解释initial/modified，支持链/分叉；未知同根/无锚环不能互证。尚不可达子图按弱连通分量稳定分组，subject冻结全部成员/边/影响，人工接受不插入证明边。初始空baseline为明确NOT_APPLICABLE；FULL两侧质量仍查，MODIFIED_ONLY为BASELINE_REUSED，不假称上传initial已验。replacement/身份接受不豁免来源/时间。
- **身份空间差异澄清（设计提交`a24b7034e9`，§3.1/§8）**：合法旧A/newB不是事实损坏/整批硬门禁，只禁止跨身份直接判等。MODIFIED_ONLY允许baseline锚定的旧A initial→新B modified边，之后其他B initial可匹配已解释B；FULL B不能仅凭digest同匹配A，无其他解释来源时按既定UNEXPLAINED分组及有理由接受，版本差异只作诊断细节，不新增issue突破1601。未知/不支持格式、绑定损坏和operation/runtime失配等原硬边界不变，不重标历史事实。纯规则owner补A→B已锚/无锚向量。
- 时间严格按设计§4/§7.1固定分组：每实际上传侧质量一项（缺有效值/INVALID互斥）及LAST_NOT_MAX单列；modified对initial/baseline倒退relations合并为一项，initial对baseline独立。baseline原质量只作历史展示；必要时间缺失另产生全局BASELINE_TIME_UNAVAILABLE，仍NOT_COMPARABLE。所有APPROVED候选参与，不能通过改选择隐藏异常。
- 权限/scope、PENDING/active、Head/集合/事实损坏/规则身份矛盾、资源边界和CAS不可豁免。只有已定来源/时间问题由`archive_submission`逐项非空reason接受/撤销；detected UNKNOWN与resolution ACCEPTED分开，不能改成PASS。复用现有audit，不做自由issue/忽略全部。
- 新subject/fingerprint绑定Head、完整candidate-set、V1 facts/规则身份、issue与完整relations/group，按对应subject失效；Start exact最新肯定references，缺/多/重/过期拒绝。原成功replay在当前鉴权后按冻结原输入返回，不重判新门禁。Plan/Result冻结输入、规则、问题及接受引用，与Baseline/Head/Workspace同事务。
- 删除两字段共用`ARCHIVE_MAX_AUDIT_REFS`路径，固定`ARCHIVE_MAX_CONFIRMATION_REFS=1`、`ARCHIVE_MAX_ANOMALY_REFS=8*ARCHIVE_MAX_CANDIDATES+1=1601`；HTTP/application/fingerprint/replay全部同步。Start body仍256KiB，reason/大组正文不塞Start；来源组append只传subject，由服务器事务重算全组，不接受caller可删减affected列表。
- sequence/Head version HTTP与application统一0..9007199254740991、拒bool/指数或字符串突破协议预算，append递增超界拒绝。小向量验证正常200候选/399接受反例、1601形状上限/1602拒绝、exact集合、实际256KiB字节门禁与规则8N+1上界，不造伪业务全异常样本、不生成大数据做性能测量。

## 3. 统一终局处置和手工关闭

旧`archive_disposition_records`/`ArchiveDisposition`直接推广为单一`submission_disposition_records`/`SubmissionDisposition`，实际模块归属依现有依赖方向固定；删除旧表/类型/查询双路径。submission_id唯一，`ARCHIVE`引用真实result/actor时间来源，`MANUAL_CLOSE`仅CLOSED_NOT_ARCHIVED、result_id为null且冻结scope/actor/UTC/reason/key/fingerprint/review版本和精确Workspace绑定。基线DDL以CHECK/FK/unique约束来源二选一、每ArchiveResult仅一个选中；不伪造ArchiveResult或新增同义关闭表，不迁移/回填。

公开关闭路由按设计`POST /v1/submissions/{submission_id}/closure`，固定CLOSE_NOT_ARCHIVED，不接caller actor/commit/自由action/force。请求含幂等键、expected_review_version、预期当前baseline node/head version及非空reason；具体DTO/header形状与现有命令入口对齐并写清单。仅`archive_submission`可执行，reviewer-only/self-only不自动获权，越权/不存在沿exact scope披露规则。

同一短写事务：当前认证/权限/目标scope→合法同键成功replay→fresh当前Head→APPROVED/未处置/精确generation-upload-preview-occupancy→唯一终局事实与Workspace CAS释放/清当前输入和Preview/version+1→提交。保持OPEN/generation及APPROVED历史，不动Head/Repository main/Submission内容、不删历史、不恢复旧Preview。旧baseline但合法占用对象可关闭，预期仍是当前Head；不要求candidate图PASS、无其他active Attempt或先接受异常，容量超限也不能堵死此出口。

MANUAL_CLOSE命名空间为exact repo/device/project+CLOSE+key，actor不入namespace/fingerprint；fingerprint固定命令/scope/目标/请求expected版本/reason，不含当前可变状态。当前授权重验后，另一合法actor同key/payload回放首次actor/time/reason，不二次释放；不同payload冲突，新key重复关闭409。审计append仍actor-bound，不混同个人接受声明。Start/close及双close同写事务屏障，late失败全部回滚。关闭桥接后来源重算，下游可能重新UNKNOWN，不自动接受或级联关闭。

所有candidate、Review closedness、ArchiveResult装配、History分页及完整snapshot/DTO、结果审计统一读新事实。Review status与终局处置来源/摘要分开展示，self-only仍仅本人；旧archive来源完整回归，不留只看ArchiveResult的旁路。

## 4. 验证owner与联合工具接线

纯规则一个参数化owner涵盖设计全部图例/排列、时间三关系/相等、空baseline/缺失与损坏、BASELINE_REUSED/replacement、接受不改原诊断、关闭桥接后UNKNOWN。audit owner验接受/撤销/序列/集合与facts变化失效、exact引用和容量；archive transaction owner验Head/Plan/Result/处置/释放的原子效果、失败回滚、成功replay及Start/close/双close竞争。HTTP owner验当前权限/404、跨actor关闭replay/撤权/冲突与新DTO；History owner验ARCHIVE/MANUAL_CLOSE两来源及self-only边界，不复制全矩阵。

一条小型真实生产wiring验证异常拒绝→有理由关闭→新上传重提→归档，不能以fake reader或自然t1未触发异常冒称覆盖。代码收敛后06必要Compose重建/绑定，不逐提交重建或全量runner；五包静态、focused/Contract按实际修改收敛。04权威及05最终fresh t1留联合最终候选，退出前仍按DC33由Owner确认范围。

main `vnext/backend/benchmarks/real_dump_journey.py::_archive`当前只接受身份异常，本节至少固定并同步新增来源/时间诊断与逐项明确理由的consumer，不引入force/无原因自动放行。FULL入口和完整tar消费者可与D一起收口，但必须在联合运行前实现；handoff逐项写实际已支持/待D，不能称现有工具已覆盖。原冻结V_ref脚本/输入/镜像/卷/证据不改；不为本任务重跑旧性能基准。

## 5. 启动与收口

尚未启动。实际V1 GO/起点/新角色、精确字段清单及06占用/证据在启动后填写。测试/编译/lint全在专用节点，06现场核空闲/原子标志、clean已提交WT/LAN bundle/legacy、离线依赖、日志host/起止HEAD/UTC/exit/SHA按AGENTS，保留前节WT/证据。先固定代码候选只读审，证据由同一审核者复核，普通修复双方直接闭环；核心冲突仅暂停依赖并给具体问题包。前端所需判断经Owner手动转发，真正阻塞时等其回复，无依赖工作继续。通过后结束两角色并自动进入D，不办理联合exit、不宣称FE3完成。
