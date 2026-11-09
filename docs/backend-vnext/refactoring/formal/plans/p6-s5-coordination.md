# Phase 6 S5 设计协调记录

## 1. 起点与现场

2026-11-09，本轮用户要求完整读取S5提示词、核实现/缺口、详细设计、分节实施和验证计划，并独立设计审核；仅本次审核子agent临时授权GPT-6-Astra high。

原路径`/home/dev/gateway-data-management-system`检出`fe3b-evidence-04`、HEAD=`a3b72d4461437f6c3d64c6ae3689156a42feb769`，初始index/tracked/untracked clean。该分支没有S5提示词；从Git发现提示词在main=`4c648965286ec751c4395cd6111f11838610299c`。未切换或改写前端目录，新增linked worktree `/home/dev/gdds-s5-design-main`检出main并链接legacy。已核本地worktree列表、tags、相关进程，有其他Codex会话；不推断其他节点空闲，不占用节点。

S3/S4 tag精确指各自H，main Rust tree=e2a901417b19259ece669637a41545e774261445；S3历史合回保留S4树。原审与来源边界见设计§1。本轮未运行产品测试、编译、lint、构建、真实旅程、节点清理；只读源码/文档与Git核对不作为产品测试证据。

## 2. 已确认的讨论结论

| 问题 | Owner本轮回答 | 计划落点 |
| --- | --- | --- |
| DC33最小真实范围 | 同意标准t1 v1/v2、合法已提交状态复用、仅History冷查/复查与真实records/bundle读取；FULL/三节点/损坏/恢复focused，不做fresh t1–t4或1暖3测 | kickoff§5，设计§1/9 |
| 用户贴出节点分工与main DC91/DC97冲突 | 明确采用main统一空闲池 | AGENTS/testing conventions、kickoff§6 |
| 执行说明历史要求 | 额外授权更新AGENTS，仅最新要求；其他注意事项也不保留历史要求 | 清理AGENTS及直接对应testing conventions失效步骤/阶段注记；历史handoff/原审/证据不改 |

无需Owner选择的技术收口：DC43已经决定单表纯结果，修旧pair-level条款不构成另选缓存产品；源码已明确Archive推进业务head，修总设计finalize措辞不改变业务。采用生产默认M24，未扩用S3/S4 M40专项。其余机械接口选择由详细设计和独审闭合，不反复请示。

## 3. 角色和独立性

工具并发上限4（含root）。持续协调者负责History、事务/生命周期与最终文档；按提示词创建新设计者Sol xhigh只读核Comparison/Risk/FFI/资源，未改产品或跑测试，返回完整技术意见。独立审核使用用户本轮临时授权的GPT-6-Astra high，新角色、无设计者上下文，在固定clean detached WT只读原审并连续复审。没有测试执行授权，不创建Luna执行任务。

设计者补充的关键发现已纳入：operation-local repr不可作持久key；facts/artifact两序与blank字段不可仅由Parquet恢复；Parquet batch/row group边界影响raw SHA；目前无独立records HTTP endpoint；History export需求无条件物化与Contract查找顺序不符。

## 4. 本轮检查与容器边界

- 只改文档，不改`vnext`、`frontend`、部署、锁文件、golden、镜像或运行资源。
- 文档提交检查：Git差异、空白、相对链接与源码符号/来源核对；明确设计任务不运行产品ruff/mypy，AGENTS记录当前纯文档边界，代码提交五包检查仍保留。
- Container rebuild required: no，纯文档。Last verified product/image source仅引用S4 V6786交接，不声明当前HEAD gate passed/carried；Container gate for this design: not-applicable。产品阶段E须按真实闭包/镜像完成验证。
- 独审原文与固定候选见`p6-s5-design-review.md`。设计CLEAR不授权S5实施、push或exit tag。

## 5. 固定候选原审与修订

R1候选`309571984d96d171e9b0c3e24a9cb82ec64c2ead`在`/home/dev/gdds-s5-design-review-r1`只读detached审核，原文/SHA见[独审归档](p6-s5-design-review.md)。GPT-6-Astra high独立结论为DESIGN_CHANGES_REQUIRED，三项均不需新增Owner决策：

- R1风险控制：恢复cap→候选记录→level过滤→预约/编号/append→原`_check_table`；批次operation检查与table/pair时间分开，补cap/时间同时触界、过滤和末条emit向量归属。
- R2恢复来源：按T1前、T1后至prepare checkpoint前、checkpoint持久化后三段写明；PREPARED不表示已有包，遵守DC94，不改Submit状态机。
- R3缓存格式：3 facts + 3 artifact + 1 STANDARD risk视图，精确risk schema；每batch至多1024行而非1024个batch；修正Rust records路径，新增facts-row validator归属明确。

一并澄清client三次是单请求上限，durable retry归原Lifecycle；继续清除AGENTS/testing conventions的过往S3 ready、固定全量runner句及过时计数。没有扩大真实范围、生产M或测试矩阵。修订候选须由原审核者连续复审关闭；本轮仍未运行产品测试/构建，也未修改产品源码。

## 6. 设计关闭

原审核者在clean detached `/home/dev/gdds-s5-design-review-r2`连续复审固定候选`75267e9a72cfb9f428b1c1e5182c1fe55f6e697f`，给出**DESIGN_CLEAR，产品实施仍未授权**；R1三项finding全部关闭，无新增阻塞或Owner待决。R2原文SHA256=`198ed8cdbb953186372ec8497f63ec1ec5be3b1f41e8ecd491b08b446ac438f5`，已逐字纳入[独审归档](p6-s5-design-review.md)。

关闭提交只归档原文并更新状态，按R2明确允许的机械归档范围核对：两轮原文字节/SHA不变、相对文档目标可解析、Git空白检查通过、`vnext`与`frontend`树等于源码基线，主线工作区clean。没有运行产品测试、lint、编译、镜像或真实旅程，没有新增carried、推送或S5 exit tag。main位于本轮独立工作区`/home/dev/gdds-s5-design-main`，原前端工作区未切换或覆盖。

下一步待Owner另行授权S5产品实施，再按kickoff A→E推进；本次临时Astra high授权仅用于上述设计原审及连续复审，不延伸实施阶段。
