# GW08 提交结果重看与 History 复用设计、执行方案

日期：2026-11-15。状态：Owner 已同意产品入口与精确结果复用方向；本文定义待实施目标，不表示代码、前端或性能验收已完成。

## 1. 目的、依据与边界

工作台「重看提交时的差异」读取该 Submission 绑定的不可变 Preview 结果；用户显式选择任意有序的 2–3 个历史节点时，才发起使用**当前**运行期规则的 History。两者展示的时间点和比较对不同，界面必须明示。FULL Preview 固定为 `baseline_to_initial`、`initial_to_modified`，不是父节点到最终提交的净变化；需要净变化时使用 History。MODIFIED_ONLY 的提交结果仍不充当 History 的双侧完整浏览包。

同一设备/项目、同一有序节点绑定和同一比较语义的 History 请求，复用进行中作业或保留期内成功且完整产物可读的作业：返回原 operation ID 和原 bundle，不重做规范表需求/读取、比较或组装；复用请求仍核结果产物和当前授权。不同请求共享提交时，允许现有精确身份的目录/Parquet/比较缓存发挥作用；不把「提交不可变」当作可跳过当前授权、产物可读性或跨 scope 绑定的证明。表需求是 pair、方向、规则与导航的函数，不能只按单个 commit 缓存后套给其他 pair。

依据：[History 小样本报告](/home/dev/gdds-stage-exchange/gw08-history-small-diagnostic/REPORT.md)在固定 `5aa97fbc` 的空基线、125 表样本中，首次/紧接重复 History 端到端为 28.705/12.632 秒，比较各约 1.1 秒。首次两次 catalog 响应之间约 13.2 秒并非 Repository Service 的内部计时；重复运行的 step 2 仍约 9.1 秒，不能归因于比较判等。Preview 的独立真实样本见 `/home/dev/gdds-stage-exchange/gw08-preview-materialize-assemble-diagnostic/REPORT.md`；不同输入、版本、运行不能拼成同一性能账。

当前代码起点：`application/history/compare.py` 只按幂等键重放；`compare_jobs.py` 的三步作业在 assemble 重验 exact-commit 描述；`snapshot_materialization/client_parquet.py` 命中导出缓存仍校验 Parquet 与引用；History 发布后 `history-compare-operation` 强保护目前不设到期。实施前固定本分支实际 HEAD、clean 候选和部署版本，核其增量；不把移动分支 HEAD 当作上述诊断源码。

本设计覆盖提交结果入口、History 精确去重、任务找回、保留/清理、排队上限，以及提交级缓存的诊断决策。Preview 计算路径的优化由既有 Preview 诊断/实施方案另行负责，不借 History 的收益声称 Preview 提速。不改比较算法、内容摘要、判等条件、风险语义、资源档位或当前双侧 History bundle Contract；不接受漏报差异的误判率。无新兼容层或历史数据迁移。

## 2. 结果来源与权限

| 用户动作 | 结果权威 | 规则与两侧语义 | 读取权限 |
| --- | --- | --- | --- |
| 重看某 Submission 的提交时差异 | 该 Submission 的 `preview_result_id`、已保护 READY/bundle | 提交时冻结的 Preview pair；FULL 两组分别展示，不算净变化 | 现有 Review/本人撤回读取权限及其 scope 检查 |
| 显式比较 2–3 个历史节点，含父节点→提交净变化 | History Operation | 受理时当前规则集；每个节点完整浏览 | `read_project_history`，每次重新鉴权 |

工作台跳转提交结果时使用现有 `GET /v1/submissions/{submission_id}/result` 与 `/result/bundle`，保留其 Preview/Submission/Attempt、READY、pair digest、bundle 和当前权限核对；不通过工作区 current preview 指针找旧结果，也不把提交 Review 权限隐式授给 History 用户。只有 `read_project_history`、无上述提交结果读取权限的主体，仍可按原权限发起 History。遇到提交结果的 unavailable/integrity 503，不自动伪装成 History 成功或悄悄发起新作业；向用户显示错误及其有权限的显式 History 操作。

审核人**不是必然**有 `read_project_history`。仓库示例 session 的 reviewer 仅授予 `review_submission` 和 `archive_submission`；它可按提交结果接口的现有权限读取同 scope 提交时结果，却不能据此打开任意 History 比较。08 实际部署的授权要以其当前 session 配置核实；前端入口按服务器权限和响应决定，不预设角色自动含 History 权限。

工作台「查看提交时差异」与「比较选中节点」应分开命名。FULL 的默认 pair 为 `initial_to_modified`，可切换 `baseline_to_initial`；如果用户要求父节点→最终提交，须另选 History。前端变更仅作交接，后端会话不修改 `frontend/`。

## 3. History 受理、去重与幂等

1. 受理先核当前 session、`read_project_history`、fresh provisioned scope、Repository 归属，并把请求的有序 `ref_kind/ref_id` 解析为 exact commit。相同 commit 但不同业务 node ref 仍是不同展示绑定；`[A,B]` 与 `[B,A]`、两节点与三节点不互用。
2. 沿用现有 `accept-binding` digest 算法，**扩充其 preimage**：设备/项目、Repository、有序节点绑定、冻结 `comparison_ruleset_digest`、实际 Comparison capability 的 `COMPARISON_CONTRACT_VERSION`、History `HISTORY_COMPARE_JOB_CONTRACT_VERSION`、view kind、pair count。当前 History 常量写死 `comparison/v3`，而 Comparison capability 已是 `comparison/v4`；实施时改为引用实际常量，不能以旧 v3 继续作为复用身份。History job contract 升到下一版，兼作整条 History 输出语义的版本闸门：比较算法/投影、表需求、风险、导航、surface、bundle 的语义变化只要可能使同一输入的结果不同，维护该路径者就必须升版。受理者核当前版本，worker 对冻结 job 版本执行既有核对，结果复用者比较当前 preimage 与原 acceptance 指纹；版本不一致不跨键复用。这样复用现有、已由双方核对的摘要，不新增只计算不核对的 digest；版本升级后同一原始幂等键与当前请求指纹不同，明确返回 409 `IDEMPOTENCY_CONFLICT`，新版本请求须用新键，不把旧结果冒充新版本结果。
3. **同一幂等键优先。** 已绑定相同指纹的活动/失败/取消作业返回原 ID；成功且未到期、闭包可读时返回原 ID；成功但未到期而闭包损坏时返回现有 unavailable/integrity 503，保留原 operation，重跑须用新键。同键不同指纹保持 409 `IDEMPOTENCY_CONFLICT`。创建原始作业的键在该作业结果过期后，不重用确定性 operation ID，返回明确的 409 `HISTORY_COMPARE_REQUEST_EXPIRED`，提示使用新键重新发起。FAILED/CANCELLED 的同键仍可读取原终态，新的尝试用新键。跨键复用形成的别名在其有效期内也按此规则回放；别名过期清理后，同字符串可作为一次新请求的键。
4. 对新键查同 scope、同指纹候选：优先 QUEUED/RUNNING；否则按受理时间、operation ID 倒序检查最多 8 个 SUCCEEDED 候选，要求在保留期内、result owner 保护仍有效、READY/assemble checkpoint/bundle 引用与冻结绑定完整且 bundle 可读。建 `(device, project, request_fingerprint, created_at_us)` 查询索引。不能只凭 Operation.status、缓存索引或 HEAD 判成功；候选损坏/丢失不返回，记录诊断后允许新作业重建。FAILED/CANCELLED/过期不作内容去重候选。成功结果的完整预检在短写事务**外**通过现有 bundle download prepare/read-session 完成：它会读遍成员并验证元数据，持有读取借用直到事务复核结束，随后关闭而不向客户端传 tar。预检有实际 I/O 成本，不能把复用宣称为纯索引命中；focused 与真实样本须记录这段耗时。写事务中重新核候选 operation、scope、指纹、到期与保护仍有效，才绑定新键。借用/复核做不到时不放行缓存命中，不能在长写事务里扫描 bundle。
5. 命中时写事务写入新键→原 operation 的别名映射，再返回原 ID、当前状态、`replayed=true`（对外沿用现有 DTO）。映射保证有效期内 response loss 后同键仍指向同一作业；原始 operation/acceptance 是唯一结果 owner。未命中时同事务写新 operation、初始 step 和含原始幂等键的 acceptance，不写别名。现有 control DB 写事务使用 `BEGIN IMMEDIATE`；在其中同时查询原始键和别名键，再检查候选与配额并插入，靠 SQLite writer 串行而非两张表之间虚构的唯一约束或进程锁。若预检后已有更新的活动候选，事务内改用该候选；若原成功候选变化且无法证明仍可用，就新建作业，不把「预检曾成功」当作持久事实。活动候选优先按受理时间、operation ID 倒序选取。

两段事务的安全边界：预检前可用只读事务完成初次授权/节点解析，**最终 `BEGIN IMMEDIATE` 内再次核当前 session 权限、fresh mapping、节点→exact commit 和请求指纹**，使用事务时刻判断是否到期，再写键与作业；任何变化均拒绝或重新计算，不拿预检前的授权/绑定直接落库。结果下载在响应开始时核授权与到期；响应已开始而时间跨过 TTL，可在既有 read-session 下完成这一次下载，之后的新读取返回 410。

目标 control DB 基线保留原受理记录作为 operation 的规范绑定和原始幂等键唯一 owner，并存受理时冻结的正整数 `result_retention_seconds`；另以受约束的**别名**表保存 `(device, project, idempotency_key) → (operation_id, request_fingerprint)`，外键指向原 acceptance/operation。受理事务在原始键索引和别名索引两处查重，不向同一 operation 创建多个相互竞争的结果 owner。无已部署数据，直接改基线、严格启动 schema，不做迁移。原始 operation 的键绑定与既有 acceptance 同寿命；跨键复用形成的别名只保留到原作业完成后该 acceptance 的保留期，活动期间不能清理。到期删除别名后，其旧键可作为新请求生成自身的新 operation ID；原始键仍指向原作业。它仅防有效窗口内重复受理，由受理事务核对，不作为新的比较结果摘要。每个原作业最多 64 个有效别名，超限返回 429 `HISTORY_COMPARE_ALIAS_LIMIT` 与可见的原 operation ID；清理以有索引的小批次进行，不能因重复点击无限积累。

`GET /v1/history-compares/{operation_id}`、bundle 与任务列表均每次使用现有 History 权限、fresh scope、operation/acceptance 绑定；返回复用的 ID 不转让权限。HTTP 200 表示复用已有作业，202 表示新建；已完成结果的旧 operation ID、pair 内容与 bundle digest 不改。授权后的 SUCCEEDED 结果到期时，直接结果与 bundle 读取返回 410 `HISTORY_COMPARE_RESULT_EXPIRED`，新请求须用新幂等键；未到期而产物损坏仍按现有 unavailable/integrity 错误，不以新作业覆盖原失败证据。

## 4. 找回、保留与上限

- `GET /v1/history-compares` 按当前设备+项目列 QUEUED/RUNNING 与保留期内终态；按 `(acceptance.created_at_us, operation_id)` 倒序，游标编码这两个值并限制在同一 scope 内，每页仍核当前权限；`limit` 默认 50、最大 100，游标不匹配/格式错误为 422。status 可在两页之间变化，游标只保证不重复/跳过受理顺序，不承诺跨页状态快照。每项含 operation ID、有序节点、状态、受理/完成时间、成功结果到期时间；FAILED/CANCELLED 可列出诊断状态但不参与完成结果复用，其列表窗口由完成时间与冻结保留期计算，不占用结果保护。不按发起人分组或持久化发起人字段。scope/permission 改变后重读，不用浏览器保存的任务列表当权威。
- 每个终态的到期事实由原 acceptance 的 `result_retention_seconds` 与 operation 的不可变 `completed_at` 计算；成功的 `result_expires_at` 与失败/取消的列表截止时间均用 `completed_at + result_retention_seconds`。成功发布时在**同一事务**把 `history-compare-operation` 的全部结果闭包保护设置为同一计算到期时刻；读取、列表、复用和清理均核这个持久事实，protection expiry 必须一致，不能仅从可被清掉的保护行推断到期。现有 `set_protection` 不写 expiry，实施时在该接口增加受限到期参数；同 owner 已有 intent 的幂等写也必须核/更新 expiry。到期后原 operation 状态与原始幂等映射保留作审计/重试解释；有界扫尾器在 control DB 写事务中按已到期 operation 清除 History result owner，调用现有 `clear_protection` 以恢复 canonical cache TTL，然后按保留规则分批删别名。`touch_canonical_ttl` 现只把无 expiry 的其它 intent 当作强 owner；扩展有限期保护时必须改为核**所有尚有效**的其它 owner，不能提前使共用 canonical cache 可清。其它 owner 的强引用及进行中 checkpoint 保护不受影响；即使文件尚未删除也不可复用。扫尾延迟不延长接口可见期。
- 配置默认保留 24 小时、单设备+项目最多 2 个进行中 History、所有作业类型合计最多 32 个 QUEUED；实施时在现有配置入口固定有界正整数，生产资源档不变。已命中的作业不占新名额。上限判断和插入必须同一写事务；scope 计数为同 scope 的 History QUEUED/RUNNING，超限为 409 `HISTORY_COMPARE_SCOPE_LIMIT` 并返回至多 2 个当前活动 ID；global 计数为所有 job kind 的 QUEUED，超限为 429 `OPERATION_QUEUE_FULL`。跨 Preview/Submit/History 及其它作业受理入口都须接同一 global 检查，不能只限制 History 而声称全局。先完成同键/跨键复用，再判断配额；API 并发受理 gate 与 durable 排队上限是两个独立约束。
- 工作区读模型增加 `active_preview_operation_id: string | null`，只指向当前 Workspace generation/revision 的 QUEUED/RUNNING Preview，排除 superseded/cancelled；同一当前 generation 出现多个候选属状态完整性错误，不能任取。供跨标签页/终端接回；Preview 的既有 supersede 规则不变。此项与 History 列表/上限同属已确认的后台任务找回需求，可在独立包实施，不能靠前端 sessionStorage 作为权威。

若现有 bundle 读取在到期并发清理时不能保证一次已开始下载的稳定性，实施者在现有 read-session/保护能力内补短生命周期借用；不得以永不清理掩盖问题，也不为此新建持久 evidence 状态机。维护任务只处理已到期的派生结果，保留成功/失败原始测试证据及其它保护 owner。配置改变仅作用于以后**受理**的作业；已受理作业使用冻结的保留期。

维护落点是现有 `bootstrap/storage_admin.py` 的显式 storage maintenance 入口：每次文件候选扫描前先以索引和 `LIMIT 32` 处理一批已到期且**仍有 History result intent 或别名**的原作业，单批短写事务提交，随后按既有 bounded artifact cleanup 运行；查询应有 owner/alias 索引，已清完的旧 operation 不得被反复选中。重复调用直至数据库待清理数为零，不另建服务或持久状态机。部署运行手册给该命令固定的定期调用（建议每小时，失败告警并重试），阶段验收须验证从到期到释放的调用链和批次接续。接口过期判断直接按持久时间事实执行，不等待维护调用；维护停跑只影响磁盘/数据库回收，不能令过期内容重新可见。

## 5. 提交不可变性与下一层缓存

完全相同 History 请求走 §3 返回原结果，此路径不进入三步 worker，因此无需重新组装。共享单个不可变 commit 的**不同** pair 仍执行当前规则的 planner 和真实行需求：方向、另一侧、ordered、导航与两侧完整浏览可能改变所需行。已有 per-table comparison/export cache 保持精确 `repository_id`、schema/layout、row count/content、storage/projection、规则/算法版本身份；损坏或过期时从同一 exact commit 重建，不从可变 `main` 或 Preview bundle 猜测。

不在本轮直接持久化「表需求已核验」布尔值或免校验凭证。现行 History assemble 在 checkpoint 后重验 exact-commit authority/catalog；首次冷 catalog、热 export lookup、重复 metadata resolve、重复导出和 bundle 组装分别计时，再决定最小改动：

1. 冷路径：在 Repository Service 内部量 schema、count、缓存装载及 HTTP 边界；仅在证明可避免重复工作后，评估把 import 时已取得的 exact-commit catalog 安全供随后读取，或改进当前有界进程内 memo。不得把 Backend manifest 当作未验证的 Dolt catalog。
2. 热路径：按互斥边界量每个逻辑表的 lookup、命中验证、miss 行读/导出、导航、pair 输出和 bundle；先考虑同一 operation 内对同一 exact ref 去重及有界批量索引。不要把调用计数当作唯一表数或节省秒数。
3. 真正评估 Preview→History 的逐表比较缓存时，用非空 before/current 且规则、来源、方向一致的代表 pair；空基线增表的 metadata-only 任务不持久缓存，不能以 0 hit 推广。必要时保留既有精确身份并减少提交/查找固定开销，不放宽摘要等价条件。

仅当细分证据显示可减少的工作并能保持当前 Contract 屏障时才把相应候选列入实施。若需要修改 checkpoint 恢复的重验规则、跨请求缓存验证责任或 Repository/Backend 权威关系，先修订 owning Contract 并给一个等价的失败/恢复语义证明；不能靠「提交不可变」一句跳过产物可读、授权或存储损坏处理。

## 6. 工作包、风险与验收

| 包 | 实施内容与完成标志 | 风险与主要 owner |
| --- | --- | --- |
| A | 后端提交结果读取接口维持现有绑定/权限；交前端路由与 pair 文案；审核页行为不退化。仅交接前端，不改 `frontend/` | A：提交内容与权限；Business Lifecycle / Bundle |
| B | History 规范受理、跨键幂等映射、原子去重与精确候选核验；同请求零新作业、零新 bundle | B，授权核对为 A；History Application / control DB |
| C | History 列表、结果 TTL 与 storage maintenance 保护释放、单 scope/全局队列上限；Workspace active Preview 读模型可独立交付 | B：状态/保护；History / Operation / Workspace |
| D | 仅量化必要的冷 catalog 与热 step 2 成本；有证据才选择一个局部缓存优化，不默认实施新的持久缓存或简化校验 | C/D：派生缓存；Repository/Snapshot/Comparison 各 owner |

按 [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md) 分包：权威 Submission/Repository 内容和权限是 A；operation/幂等/结果保护是 B；可重建缓存是 C。A/B 包逐包独审，阶段末不同模型家族新上下文全范围独审；实际门禁闭包由协调者依据代码差异与脚本定，不因设计文档自动跑全部六包。更改容器/清理接线时先读 testing-conventions 对应触发条件。

权威测试 owner 应覆盖：同键同/异指纹、跨键同时受理只建一个作业、同 scope/跨 scope、方向与 node ref 不同、ruleset/version 变化、FAILED/CANCELLED/过期/不可读不复用、response loss 后 alias 回放、结果权限变化、列表分页与排队上限、结果发布与到期清理并发、Reader 仍可完整读取；FULL/MODIFIED_ONLY 提交结果 pair 与冻结规则语义。测试按业务行为命名，不对每个私有查询复制矩阵。缓存优化另测精确身份、坏/缺文件重建和一条关键 crash/恢复屏障；不通过更新 golden 接受业务结果变化。

验证分层：实施者在专用节点按占用规则运行受影响 focused、五 Python 包 ruff/mypy；Rust 变化按规范 rustfmt/clippy及 backend 扩展重装。最终候选用 `run-stage-gate.py` 运行脚本查出的必要包和容器结果；所有原始失败保留。真实数据由 Owner 确认最小范围：建议先在独立测试节点做 `small-test` 的首次/重复 History，再选一个非空双侧 pair 核实际缓存身份、完整比较/导航/双侧浏览；不用本次空基线样本代替后者。性能比较同节点、同输入/资源/版本身份，报告用户等待、作业创建数、catalog 和热阶段互斥分段；单样本只作为观察，不承诺绝对秒数或 08 延迟。

退出条件：提交结果入口对适用权限用户不创建 History；相同 History 请求在有效期内跨键并发也只出现一个 operation 与原 bundle；过期/损坏可用新键重建，旧结果不伪装成功；权限与 scope 隔离、队列上限及保护清理正确；产品比较、风险、导航、双侧闭包与 frozen/current rules 区别仍符合 Contract。前端改动须由前端设计会话自行审核与验证；未实施的 D 候选记为未知，不写优化通过。

## 7. 实施顺序与交接

先冻结目标源码与接口行为，完成 B 的受理/幂等/结果复用及 focused；再交付 C 的列表、TTL、上限与找回，**B+C 同一最终候选验收，不把永久保留的 B 单独发布**；最后与前端会话对接 A。D 在核心复用验收后按剩余成本单独决策，避免对已消失的重复作业做缓存优化。

实施映射：B 优先改 `application/history/{compare,contracts,compare_bindings,ports}.py`、`infrastructure/control_db/{schema,sqlite_history_compare}.py` 与 History HTTP orchestration/errors，完成原始键和别名键的事务查找、成功候选的事务外预检及 B 的 focused；C 接 `application/history/compare_jobs.py` 发布保护、`sqlite_protection.py` 的到期处理、`bootstrap/storage_admin.py` 的有界扫尾、History 列表 DTO/路由、Workspace read model 和所有作业受理的队列计数入口。C 同步部署维护运行手册及必要的容器接线验收。完成每包后删掉被替代的旧查找路径；schema、HTTP golden 与受影响测试同步目标形态，不保旧字段别名。D 若获证据支持，从 `repository_service/candidate_a/dolt_cli.py` 或 `snapshot_materialization/client_parquet.py` 的实测热点选择**一个**局部包，不与 B/C 暗中合并范围。

接口落点：History `POST` 沿用 `{operation_id,status,replayed}`；新增 `GET /v1/history-compares?limit=<1..100>&after=<opaque>`，响应为有序 items 与可空 next cursor。每项固定 `operation_id,nodes,status,accepted_at,completed_at,result_expires_at`，后两项可空，`result_expires_at` 仅成功时非空；输入超界 422，越权遵循原隐藏规则。新增 `HISTORY_COMPARE_REQUEST_EXPIRED`（409）、`HISTORY_COMPARE_RESULT_EXPIRED`（410）、`HISTORY_COMPARE_SCOPE_LIMIT`（409）、`HISTORY_COMPARE_ALIAS_LIMIT`（429）与 `OPERATION_QUEUE_FULL`（429）。WorkspaceResponse 增加可空 `active_preview_operation_id`；后端 DTO/OpenAPI 按这些名称落地后，前端会话据此接入，Contract 不接受同义字段。

各包完成后追加阶段日志和外部 handoff，设计/Contract 入库，审核意见和机器原件留 `/home/dev/gdds-stage-exchange/gw08-history-reuse/`。不推送、部署或修改正在联调的 08 数据；阶段真实范围与前端修改由相应 owner 确认。

前端交接重点：工作台旧提交使用提交结果读取接口仅在具备原权限时展示「提交时差异」；FULL 两 pair 不称净变化；显式选择节点调用 History；新 History 列表用于找回；复用返回原 ID 时按当前状态接回；旧本地 bundle 先经服务器当前授权/摘要核对。详见交接区 `FRONTEND-HANDOFF.md`。
