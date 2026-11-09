# FE3 kickoff：对接真实 backend

- **状态：** 修订 3，2026-11-09，补齐 FE3c 开始前缺的设计内容，待审核会话核对后发出 FE3c 实施提示词（§15.5）。
  - Q1–Q12 已确认（owner，2026-11-05）。**FE3a 已退出（2026-11-05，§3.2）**。**FE3b 已退出（2026-11-09，§3.2）**。
  - owner 2026-11-07 决定把 FE3 剩余工作拆成 FE3b（契约与基础）与 FE3c（归档核验与完整旅程），补记为 §11 Q13。Q14 已决定（owner 2026-11-08）；**Q15–Q20 已确认（owner 2026-11-09），全部按 §11 的建议**。
  - owner 2026-11-08 就 [修订 2 审核](reviews/fe3-kickoff-rev2-review.md) B1 选甲：FE3b 合入 main `748de5034d`（`vnext/` 树仍为 `56720104af`），FE3b 期间不再合入 main（§2.1、§3.2）。
  - owner 2026-11-09 决定 **FE3c 合入 main `fd9e383d76`**（`vnext/` 树 `6368c9c40c`，与 `p6-s4-exit` 相同，含 S3、S4 的退出与 Q18；§2.1、§3.2）。
  - 第 1 步（`d702307836`）写定 FE3b 需要的全部内容（§1–§6、§9、§10、§12、§13.3、§13.4、§15.2）。
  - 第 2 步写定 FE3c 的设计：§16 归档界面、§4.6 FE3c 的上传序列与预期异常、§4.7 R8 与 R12、§8 t1 调整、§9 FE3c 截图、§13.5、§13.6、§15.3。
  - 修订 3：Q18 已由后端交付（`94b25a3279`，独审 GO），§16.6 定稿：`expected_review_version` 取自同一次候选读取中目标候选的 `review_version`。
    后端已为 `vnext/` 树 `6368c9c40c` 补交生产 OpenAPI 原件（2026-11-09，SHA256 `ce58f20a…c079`，设计会话已核，§5.2），FE3c 提示词的前置条件已全部满足，待审核会话核对本修订后发出。
- **修订记录：**
  - 初稿 `5c360bfb1b` 经 [kickoff 审核](reviews/fe3-kickoff-review.md)（`920f068da4`），结论为定向修订；
    修订 1 `de9cd5cb6f` 处理 B1–B4 与采纳的非阻塞意见（逐条见 §15）；
    [定向复审第 1 轮](reviews/fe3-kickoff-rereview-1.md)（`e91d9db6eb`）通过。
  - 确认记录 `3d3373e7fa` 改正复审 §3 的 R1–R4，并按复审 §4 登记基线已前移的已通过提交永久占用工作区的后端缺口。
  - 2026-11-05 按 [FE3a 审核](reviews/fe3a-review.md)（`a0b9604ddd`）中交设计会话的事项修订：§4.6 真实 e2e 上传输入（Q10）、§7 M7 基线显示序号（Q11）、§8.4 M1 结论（Q12）。逐项见 §15.1。
  - 2026-11-07 修订 2 第 1 步：依据审核会话的 [FE3b 前置条件核对](reviews/fe3b-precondition-check.md)（`5dde965a65` 的 §1–§8，`80e74d116c` 的 §9–§10）、
    后端交接与 DC89、DC90（见“依据”），吸收 BE-a、归档业务核验与 BE-d 的交付，按 owner 决定拆段。逐项见 §15.2。
  - 2026-11-07 修订 2 第 2 步：FE3c 设计，依据同上，另读后端源码 `application/archive/business_validation.py`、`queries.py`、`audit.py`、`manual_close.py` 与 `application/submission/review.py` 核对预期异常与权限。逐项见 §15.3。
  - 2026-11-08 按 [修订 2 审核](reviews/fe3-kickoff-rev2-review.md)（`d076903d7f`，owner 答复 `244a24b811`）定向修订：第 1 步 B1–B3 与 N1–N4（`dfdcd00b90`），第 2 步 C1–C3 与 N5–N8（逐条见 §15.4）。
  - 2026-11-08 记录后端对 Q18 与生成时间预期的答复（[S3 协调 §16](../backend-vnext/refactoring/formal/plans/p6-s3-coordination.md#16-fe3c-q18-与生成时间预期当前事实和建议交接)，`1981882cc6`）：Q18 缺口属实，仍是 FE3c 前置；§4.6 的生成时间预期与后端源码一致。不改设计，只改 Q18 的状态与 FE3c 前置的写法（§3.2、§10、§11、§12、§13.5、§13.6、§16.6、§16.9）。
  - 2026-11-09 修订 3：记录 owner 对 Q15–Q20 与 FE3c 合入点的决定；按 Q18 交付定稿 §16.6，写明 `selected` 只含两个字段；FE3c 依赖镜像；`56720104af..6368c9c40c` 其余后端变化的前端影响；改正修订 2 定向复核第 1 轮的 E1、R1。逐项见 §15.5。
- **日期：** 2026-11-05；修订 2：2026-11-07；修订 3：2026-11-09。
- **起点：**
  - FE3a：`fe-fe2c-exit`（tag 对象 `86901e038d` → `749f219d5f`），main 合入提交 `0430e0e738`。
  - FE3b：`fe-fe3a-exit`（tag 对象 `8dd0f765b3` → `0e7caf66f4`，`frontend/` 树 `8a9f11c84f`），main 合入提交 `86fa2e4e8a`。
  - FE3c：`fe-fe3b-exit`（tag 对象 `8da25ee3f5` → `ed5d2c24e9`，`frontend/` 树 `54b5a333c6`），main 合入提交 `ffccdd411b`；开始时合入 main `fd9e383d76`（§3.2）。
  - 修订 2 以本地 main `e8c45eb642` 核对：`vnext/` 树 `56720104af`，与 `p6-be-a-d-exit` 的产品提交 `49403f21aa` 相同。
  - 修订 3 以 main `fd9e383d76` 核对：`vnext/` 树 `6368c9c40c`，与 `p6-s4-exit`（`1e778aae05`）相同。
- **依据：**
  - [前端 kickoff](frontend-kickoff.md)（§3.3、§4.2–§4.4、§5、§6、§7、§7.1；FD4）、[FE2 kickoff](fe2-kickoff.md)（§4.1、§6.5、§7、§9 Q16–Q19、§10）；
  - FE3a：[handoff](fe3a-handoff.md)、[审核](reviews/fe3a-review.md)、[复审第 1 轮](reviews/fe3a-rereview-1.md)、[第 2 轮](reviews/fe3a-rereview-2.md)、[证据核对](reviews/fe3a-evidence-check-1.md)；
  - [FE3b 前置条件核对](reviews/fe3b-precondition-check.md)（下称“核对报告”）；
  - 后端：[FE3b 评估交接](../backend-vnext/refactoring/formal/plans/p6-fe3b-backend-assessment-handoff.md)、
    [BE-d 前端交接](../backend-vnext/refactoring/formal/plans/p6-be-d-frontend-handoff.md)（含 §2.1 接收预算，澄清 `20d3b885f6`）、
    [V2 归档界面交接](../backend-vnext/refactoring/formal/plans/p6-v2-frontend-handoff.md)、[BE-a 交接](../backend-vnext/refactoring/formal/plans/p6-be-a1-handoff.md)、
    [归档业务核验设计](../backend-vnext/refactoring/formal/plans/p6-archive-business-validation-design.md)、
    [DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)、
    [DC89](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc89-be-abe-d-重启设计与归档待审核门禁)、
    [DC90](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc90-归档时间倒退与来源解释的业务补充)、
    [Q18 交接](../backend-vnext/refactoring/formal/plans/p6-be-q18-handoff.md)（最终产品 `94b25a3279`，[独审](../backend-vnext/refactoring/formal/plans/p6-be-q18-review.md) GO）；
  - FE3b 使用的生产 OpenAPI 原件（`vnext/` 树 `56720104af`；FE3c 的比对原件见 §5.2）：`/home/dev/gdds-reviews/artifacts/p6-be-ad-final-04-copy-mop1T4t8/p6-be-ad-final-04/resume-a-5OBTboKj/new-authority-compose-53h3ekqp/production-openapi.json`，
    SHA256 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`（设计会话已核）；
  - FE3c 的生产 OpenAPI 原件（`vnext/` 树 `6368c9c40c`）：`/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`，SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`（设计会话已核，§5.2）；
  - AGENTS（“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”）、testing-conventions“前端测试（FD7）”。
- **会话分工：** 与前端 kickoff §10 相同。本文由前端设计会话维护。后端由 `p6-backend-design`（DC73）负责，
  前端设计会话不写后端提示词；需要后端新增字段或发现 Contract 冲突时，交 owner 转后端，不在本文中假设。

## 1. 目标

- 前端对接 Compose 中的真实 backend，跑通全部业务旅程（前端 kickoff §7 FE3 一行）。
- 刷新 OpenAPI 快照，删除被替代的旧路径（退回修改、201/202 变通、`archive_disposition`），并在 e2e 中与运行中的 `/openapi.json` 比对（前端 kickoff §4.2）。
- 接回上传模式顶栏的撤回，工作区被占用时禁用“提交”与“上传”（前端 kickoff §7.1，DC75）。
- 修复 bundle tar 的接收（PAX 按字节、标准 PAX `size`、接收预算），用后端生产 encoder 的同一份 tar 证明解析、摘要与 OPFS 安装互通（BE-d 前端交接）。
- 显示提交的终局处置（已归档、已关闭未归档），与审核状态分开（V2 交接 §3）。
- 归档主线接入业务核验：原始诊断与人工处理分开显示，逐项接受与撤销；有理由关闭、不归档的出口；待审核阻塞与过期通过的提示（DC89、DC90，FE3c，§16）。
- 用 t1 真实数据从浏览器走完一次完整旅程（FE3c）。
- 完成 FE2 带入项（FE2 kickoff §6.5：M1、M7、n3、n8）。

不在范围：BE-b 的分组、列展示与行定位（FE4）；首批空基线（FE2 kickoff Q18，仍为缺口）；正式 SSO 与部署形态（Phase 8/9）；外部驱动通道与深色主题。
浏览器不重新解析 SQL、不计算来源图或生成时间，这些事实以后端返回为准（FE3b 评估交接 §4.1）。

## 2. 当前事实（main `e8c45eb642`，2026-11-07 核对；2026-11-08 补 main 的后续变化；2026-11-09 补 FE3c 合入点 `fd9e383d76` 与 Q18）

### 2.1 后端依赖

全部已交付，不再有等待项（核对报告 §1、§9）。Q18 已于 2026-11-08 交付（§2.3 第 19 行）；FE3c 的生产 OpenAPI 原件已于 2026-11-09 补交（§5.2）。

| 项 | 状态 |
| --- | --- |
| S2a | 附注 tag `p6-s2a-exit`（对象 `ec02169f35`）→ `53b676a629`，在 main 第一父链上 |
| BE-a、归档业务核验（V1、V2）、BE-d | 合并为一个附注 tag `p6-be-a-d-exit`（对象 `66b9083941`）→ 退出报告提交 `77b9aeea74`；产品提交 `49403f21aa`；`vnext/` 树 `56720104af`；退出 handoff `9ee1f47b32`。`49403f21aa..748de5034d` 没有改动 `vnext/`（之后的变化见本节末） |
| 后端澄清 | `20d3b885f6`（只改文档）：PAX 接收预算；已处置提交的 `NOT_CANDIDATE_BASE_ADVANCED` 只作历史说明 |

**后端规则（本文据此设计，不需要再问后端）：**

- **DC89：**
  - 同一 scope、当前 baseline 下有未关闭的 `PENDING` 时阻塞归档（`ARCHIVE_PENDING_REVIEW`）；只有上传或 Preview 的草稿不阻塞；
  - 新的 `APPROVE` 在写事务中检查当前 baseline，过期返回 409 `BASELINE_VERSION_CONFLICT`；`REJECT`、`WITHDRAW` 保留为出口；
  - 归档仍唯一选中，其余已通过的同级提交关闭；
  - tar 中 `manifest.json`、`artifact-closure.json` 在前，之后最终 closure 每个条目按顺序对应一个普通文件，下载层不去重，不用 hardlink/symlink。
- **DC90：**
  - 时间倒退、来源不明、必要生成时间缺失，可由 `archive_submission` 持有人逐项填写理由后接受；原始诊断不改为通过；
  - 数据损坏、越权、事务冲突不可接受；
  - 新增“有理由关闭、不归档”出口：保留 `APPROVED` 历史，释放工作区，不推进基线。
- **20d3b885f6：**
  - 单个路径的 UTF-8 接收上界 8,388,608 字节（8 MiB）；单个局部 PAX payload 上限 16,777,216 字节（16 MiB），不含 512 字节 header 与 padding；先检查、再分配；
  - 已处置的提交仍可能带 `NOT_CANDIDATE_BASE_ADVANCED`，只作历史说明；终局状态看 `submission_disposition`，占用看工作区指针。

2026-11-05 版本中的排期估计与协调建议（基线前移、tar 成员对应）已由上述交付关闭，见 §12。

**main 的后续变化与 FE3b 合入点（2026-11-08，修订 2 审核 B1，owner 选甲）：**

- S3（P6 比较与风险的 Rust 接线）直接在 main 上提交 `vnext/`。`748de5034d`（docs(p6): record S3 implementation authorization…）是 main 第一父链上 `vnext/` 仍为 `56720104af` 的最后一个提交，
  已含 `p6-be-a-d-exit`、`20d3b885f6`、`55d56efb6e` 与本文第 1、2 步；其后的 S3 提交改了计算路径与 `rust/Cargo.lock`（审核核对时 main `5ff82b303e` 的 `vnext/` 为 `e0a40d93ef`），
  `--print-input` 得 `gateway-backend-deps:lock-ca0ba0a24a5e`，04、05 没有该镜像。HTTP 层没有改动。
- **FE3b 合入 `748de5034d`**：被测 backend 是已退出的 `p6-be-a-d-exit` 树，依赖镜像仍为 `lock-d054366c02fa`，§5.1 的“运行时 OpenAPI 与原件同树”成立。FE3b 期间不再合入 main；后端可以继续在 main 上推进 S3、S4。
- **FE3c 合入 main `fd9e383d76642037e4b3246c847222ea9483e033`（owner 2026-11-09）**，不合入之后的 main：
  - 理由：之后的 main 已含 S5 正在实施的代码。`fd9e383d76` 是 S5 写代码前的最后一个提交，`vnext/` 树为 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`，与 `p6-s4-exit`（`1e778aae05`）相同，已包含 S3、S4 的退出与 Q18（最终产品 `94b25a3279`）；
  - 审核会话已试合并：`ed5d2c24e9` 与 `fd9e383d76` 无冲突，合并后 `frontend/` 树仍为 `54b5a333c6`；
  - 依赖镜像为 `gateway-backend-deps:lock-578e079b762e`，04、05 已有，不需要新的预填充（§2.2、§4.3）；
  - FE3c 期间是否再合入 main，按 §3.2“FE3c 期间”一条：只在后端再改 `vnext/` 且 FE3c 需要时按需重新合入，不为跟进 main 而合入。
- FE3b 的证据绑定 `p6-be-a-d-exit` 的 backend 树；FE3b 前端与 S3、S4 backend 的组合到 FE3c 才在真实 backend 上验证。`56720104af..6368c9c40c` 的后端变化对前端的影响见 §2.3 末段。

### 2.2 节点、镜像与数据

核对时间 2026-11-07 15:35–15:37Z（核对报告 §4），2026-11-08 07:13–07:23Z 复核（修订 2 审核 §2.1）。FE3b 所需都已就绪，**FE3b 不需要 DC67 预填充**。
FE3c 的依赖镜像 `lock-578e079b762e` 已由审核会话 2026-11-09 在 04、05 上只读核对（下表），**FE3c 也不需要新的预填充**（§4.3）。发出提示词前审核会话再现场核对一次。

| 项 | 04（取证） | 05（真实 backend 调试、t1） | 07（模拟接口各项） | 说明 |
| --- | --- | --- | --- | --- |
| 前端工具链 `mcr.microsoft.com/playwright:v1.64.1-noble` | 有 | 有 | 有 | config `sha256:a0d7b2b4…a1017`，7 个 DiffID 三节点相同；身份见 `frontend/scripts/run-tests.sh` |
| npm 缓存 | `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 `npm-cacache.tar.gz` | `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz` | 与 04 相同的路径 | 三份归档 SHA256 相同（`0d861824…0089f4`），来源提交 `a2fb4a027a`；`package-lock.json` 自 FE0 未变。`run-tests.sh` 的默认路径是 04 的路径；在 05 上要设置 `GATEWAY_FRONTEND_NPM_CACHE` 与 `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`；三节点都设置 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`。新脚本使用同样的变量 |
| backend 依赖镜像 `gateway-backend-deps:lock-d054366c02fa`（`748de5034d` 的 `--print-input`，FE3b） | 有 | 有 | 不需要 | label 一致；config `sha256:b5b54224…e4b92a`，19 个 DiffID 与开发主机相同。FE3a 用的是 `lock-c668cef8e47e`，S2a 合入后改为此 tag |
| backend 依赖镜像 `gateway-backend-deps:lock-578e079b762e`（`fd9e383d76` 的 `--print-input`，FE3c） | 有 | 有 | 不需要 | 输入 `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`；来源为后端 S3 已核收的预填充链，Q18 交接记录 config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`。审核会话 2026-11-09 在 04、05 上只读核对：label 一致，19 个 DiffID 两节点相同；config digest 由运行时的入口脚本再核 |
| RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee` | 有 | 有 | 有 | config `sha256:98d0801b…ad9ec9`，16 个 DiffID 相同。FE3c 不变（`repository_service/uv.lock` 在 `56720104af..6368c9c40c` 中未改） |
| `gateway-repository-service:local` | 有 | 有 | — | 由后端会话使用，前端不重新 tag（§4.3） |
| t1 组态目录 | — | `/home/dev/gateway-real-dumps/source-dirs/t1-v1`、`t1-v2` | — | 清单 SHA256 `cdb598cd…0163`、`fa2450fa…a96a`，与 FE3a handoff §4.1 相同；目录内 `sha256sum -c` 19/19 通过 |
| 真实数据源包 `/home/dev/gateway-real-dumps/packages/rd-t{1..4}-*.tar.gz` | 有 | 有 | — | 规范化的源包，只含 `/sql/dbcfg.sql` 与 `/comps/logic/logics.xml`，没有 `.pmc`，不能用于浏览器上传 |

- 07（`ct109-gw-dms-07`，8 vCPU、16 GiB）只跑类型检查、lint、单测、构建、截图与模拟接口 e2e，设置 `GATEWAY_FE_TEST_WORKERS=2`；不跑真实 backend（没有 backend 依赖镜像，AGENTS 也不让新节点承接前端真实 backend e2e）。
- 07 与 04、06 共享物理宿主；07 上的结果不作为取证（AGENTS）。

**组态目录与数据档的对应（按 `sql/dbcfg.sql` 与 `comps/logic/logics.xml` 的 SHA256 核对；8 个目录的两个成员都与对应源包一致）：**

| 档 | 目录（开发主机） | 文件数 | 目录大小 |
| --- | --- | --- | --- |
| t1 v1 / v2 | `small_cut/small_cut-1`、`small_cut-2` | 19 / 19 | 6,853,875 / 6,854,427 字节 |
| t2 v1 / v2 | `small/small-1`、`small-2` | 229 / 230 | 约 66 / 64 MB |
| t3 v1 / v2 | `medium/medium-1`、`medium-2` | 223 / 226 | 约 237 / 238 MB |
| t4 v1 / v2 | `large/large-1`、`large-2` | 528 / 528 | 约 317 MB |

- 前端上传要求所选目录根下恰好一个 `.pmc` 且有 `sql/dbcfg.sql`（`upload-package.ts`，沿用 legacy 的规则）。t1 v1、v2 与 t4 v1 的目录原件已由 FE3a 传到 05（§8.1）。
- t1 两个目录各有 3 个非 ASCII 文件名与 3 个空文件；`large-1` 有 498 个非 ASCII 文件名，另有 2 个路径超过 100 字节（最长 103 字节）。

### 2.3 后端接口与 FE3 的需要

依据：FE3b 的生产 OpenAPI 原件（SHA256 `977b2258…b8a7`）、核对报告 §3 的逐项比对、后端交接；第 19 行依据 Q18 交接与 `56720104af..6368c9c40c` 的 `http/schemas` 差异。
**结论：满足 FE3b 与 FE3c 的需要，不需要新增后端字段或接口。** FE3c 关闭出口原有的缺口（第 14 行，§11 Q18）已由第 19 行补上。超出 2026-11-05 预期的部分（第 9 行起）按子阶段分配，“子阶段”一列写明在哪里消费。

| # | FE3 需要 | 后端交付 | 子阶段与位置 |
| --- | --- | --- | --- |
| 1 | 定位上传模式下当前提交（Q16） | `WorkspaceResponse.active_submission_id`，required nullable，201 与 200 两条路径都返回 | FE3b §6 |
| 2 | 刷新后找回进行中的提交尝试 | `active_submit_attempt_id`，经 `GET .../submit-attempts/{id}` 取 `operation_id`；执行、等待恢复或结果未知时保留，确认 `ABORTED` 后才清空；与 `active_submission_id` 至多一个非空 | FE3b §6.2；不按 operation 终态推断指针已清空 |
| 3 | 本人读取审核状态（含终态） | `withdraw_own_submission` 可读本人提交的 `GET .../review`，所有状态；不授予 History、归档列表或他人工作区 | FE3b §6.1 |
| 4 | 撤回请求的预期版本 | `ApplyReviewRequest.expected_review_version` 取 `review_version`，不用工作区版本 | FE3b §6.1 |
| 5 | “无权限”的判定 | 两个审核权限都没有时 GET 与 POST 返回 403 `SCOPE_FORBIDDEN`；他人、跨 scope 与不存在统一 404 `RESOURCE_NOT_FOUND` | FE3b §6.1；前端不按 actor 推断 |
| 6 | 撤回、退回后可重新上传 | 指针、当前上传与 Preview 清空（OpenAPI 无对应字段） | FE3b W2、R6，在真实 e2e 中验证 |
| 7 | 两个创建接口的状态码 | `POST /v1/workspaces` 201/200；`POST /v1/history-compares` 202/200 | FE3b §5.3，删除 FE2 的类型变通 |
| 8 | 删除退回修改 | OpenAPI 与源码中都没有 `RETURN_FOR_REVISION`/`RETURNED_FOR_REVISION`；`action` 为 `APPROVE`、`REJECT`、`WITHDRAW` | FE3b §5.3，删除前端映射 |
| 9 | 整包 tar | 两个 bundle 路由 200 为 `application/x-tar`，带 `Content-Length`、`ETag`、`Content-Disposition`；成员结构见 §2.1 DC89。头前错误：Preview 404 `RESOURCE_NOT_FOUND`、503 `SERVICE_NOT_READY`/`BUNDLE_INTEGRITY_FAILURE`；History 404 `RESOURCE_NOT_FOUND`/`ARTIFACT_UNAVAILABLE`、503 `BUNDLE_INTEGRITY_FAILURE` | FE3b §5.5（成员对应与前端要求一致，2026-11-05 的“有前提”已消除） |
| 10 | tar 接收修复 | BE-d 前端交接 §1–§2.1：PAX 记录按 UTF-8 字节解析；标准 PAX `size` 覆盖 header 中的八进制 size；接收预算 8 MiB / 16 MiB | FE3b §5.5 |
| 11 | 同字节互通 | 生产 encoder 生成的 `bundle.tar`（24,576 字节，SHA256 `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`）与 PAX、size 向量 | FE3b §5.5 |
| 12 | 终局处置 | Review：required nullable 对象 `submission_disposition`（`submission_id`、`disposition`、`source_kind`、`result_id`、`closure`）。History 节点：`archive_disposition` 改为 `submission_disposition`（枚举 `ARCHIVED_BASELINE`、`CLOSED_NOT_ARCHIVED`），另有 `disposition_source_kind`（`ARCHIVE`、`MANUAL_CLOSE`）、`disposition_result_id`、`closure`（`closed_by`、`closed_at`、`reason`）；`ArchiveDispositionResponse` 删除，归档结果的 `dispositions` 改用 `SubmissionDispositionResponse` | FE3b §6.4 只读显示；FE3c 在真实 e2e 中覆盖 |
| 13 | `NOT_CANDIDATE_BASE_ADVANCED` | 仍按“`APPROVED` 且所基于的 baseline 不是当前 head”派生，已处置的提交也带（`application/history/projection.py:210-218`）；只作历史说明，不表示占用或需要处理 | FE3b §6.1、§6.4 |
| 14 | 关闭出口 | `POST /v1/submissions/{id}/closure`：`Idempotency-Key`；body `expected_review_version`、`expected_baseline_node_id`、`expected_baseline_head_version`、`reason`（1–4096 UTF-8 字节，`validate_utf8_reason`）；只有 `archive_submission`；201 首次、200 回放（返回首次操作者、时间与理由）；409 `IDEMPOTENCY_CONFLICT`、`BASELINE_VERSION_CONFLICT`、`REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`ARCHIVE_CLOSED`、`WORKSPACE_OCCUPANCY_CONFLICT`；另有 403、404、413、422、429、503 | FE3c §16.6。原缺口（只有 `archive_submission` 的身份读不到 `review_version`，§11 Q18）**已交付**，见第 19 行 |
| 15 | 归档业务核验 | `PreviewArchivePlanResponse.business_validation`（`rule_id`、`baseline_facts_digest`、`source_diagnostics`、`time_comparisons`、`issues`）；`ArchivePreviewAnomalyResponse` 新增 `affected_submission_ids`、`side`、`relations`、`details`（按 issue 区分的闭合 union）、`detected_status`、`resolution_status`、`latest_sequence`、`accepted_by`、`accepted_at`、`reason`；新 `subject_kind` 与 action：`CONFIGURATION_SOURCE` → `ACKNOWLEDGE_SOURCE_EXCEPTION`、`CONFIGURATION_TIME_QUALITY` → `ACKNOWLEDGE_TIME_QUALITY`、`CONFIGURATION_TIME_ORDER` → `ACKNOWLEDGE_TIME_ORDER`；`REVOKE` 保留 | FE3c §16；FE3b 只按 §5.3 修正 action 映射 |
| 16 | 待审核阻塞 | `ArchiveCandidatesResponse`、`PreviewArchivePlanResponse` 新增 required `pending_submission_ids`、`pending_submission_count`，有待审核时 `blockers` 含 `ARCHIVE_PENDING_REVIEW`；`POST /v1/archives` 409 含 `ARCHIVE_PENDING_REVIEW` | FE3c §16；FE3b 只补模拟数据字段 |
| 17 | 引用上限 | `StartArchiveRequest.confirmation_refs` 上限 1，`anomaly_resolution_refs` 上限 1601（候选仍上限 200，body 上限 262,144 字节） | FE3b 随类型生效；FE3c §16 不分页、不截断 |
| 18 | review-events 新错误码 | `POST .../review-events` 409 新增 `BASELINE_VERSION_CONFLICT`（过期 `APPROVE`）、`ARCHIVE_CLOSED`（提交已归档或关闭） | FE3b：撤回失败按 §6.1 处理，审核顶栏走通用文案；FE3c §16：过期通过的专用提示 |
| 19 | 关闭请求的审核版本（Q18，FE3c 合入的 `vnext/` 树 `6368c9c40c`） | `GET /v1/archive-candidates` 的 `candidates[]`（`ArchiveCandidateResponse`）每项新增必填 `review_version`（非负 I-JSON 安全整数，0–2^53−1），取自同一只读事务中的审核投影版本；只读，不进入候选摘要、候选集合摘要、选择或关闭的 fingerprint。Review GET 的 ACL 不变（只有 `archive_submission` 时仍 403）；关闭时版本过期返回 409 `REVIEW_VERSION_CONFLICT`。预检、确认、异常处置、开始归档请求中的 `selected`（`ArchiveSelectedRefRequest`，`extra="forbid"`）仍然只能含 `submission_id` 与 `expected_candidate_digest`，多出的键返回 422；后端已修过四处把整个候选读取对象转发进 `selected` 的消费者。`56720104af..6368c9c40c` 中 `http/schemas` 只改了 `archive.py` 的这一字段，路由与错误映射未改 | FE3c §16.6（取值）、§16.4–§16.6（`selected`）、§5.3（模拟数据）、§16.9 V9、V14 |

实施中若运行时接口与本表不符，按 §10 停止。

**`56720104af..6368c9c40c` 的其余后端变化（修订 3 核对，结论：已核，无前端可见变化；三个诊断码交后端确认）：**

该区间改了 `backend/src` 下 47 个文件，集中在 S3（比较与风险接 Rust）与 S4（Submit 规划与写入）。设计会话按前端能看到的四类逐项核对：

| 类别 | 核对 | 结论 |
| --- | --- | --- |
| bundle、manifest、closure、tar | `artifacts/`（含 `tar_stream.py`）、`capabilities/bundle_assembly/`、`domain/` 未改；`fixtures/golden/` 下已有的 archive、bundle、comparison、risk、surface 等 golden 一个字节都没改，只新增 `comparison/s3-e/old-python-expected.json` 与三个 mutation 向量。S3 设计 §8 把“pair_id 与 FULL 两个比较对、surface/bundle 摘要、三族 Parquet/manifest/closure、tar/PAX 下载”列为不改的稳定面，§4 规定 manifest/surface/bundle 冻结语义与 golden 不变、不许改 golden 抹平差异；S4 设计规定同输入 `replay.sql` 逐字节一致 | 无变化 |
| 比较与风险结果的字段与取值 | `risk_evaluation/contracts.py` 只加了运行期的预算与缓存端口（`RiskOperationPort` 等），注明不进入持久的摘要与 DTO；`ComparisonMode` 仍只有 `DETAILED`、`DATASET_REPLACEMENT`；记录数上限仍为 2,000,000（原 `_MAX_DEFAULT_RECORDS`，现 `production.py::_MAX_RECORDS`）。`mutation_planning/storage.py` 新增的 `PATCH_THRESHOLD_EXCEEDED`、`STORAGE_SHAPE_CHANGED` 等是 Submit 的内部存储决策原因，不进入 HTTP 响应或 bundle | 无变化 |
| 错误码与上限、默认值 | `http/` 下只改了 `schemas/archive.py`（第 19 行），`http/errors.py` 与路由未改；`application/workspace/upload_limits.py` 未改。`settings.py` 与 `deploy/compose.yaml` 把 worker 的内存包络与 kernel 预算改为可由环境变量设置，**默认值与原固定值相同**（32 GiB、24 GiB）；前端运行脚本不设置这两个变量 | 无变化 |
| 比较诊断码（写入 manifest 与 surface，前端 `view-model/diagnostics.ts` 有文案） | 新树中不再有 `COMPARISON_MODE_NOT_DETAILED`、`ORDER_KEY_UNSUPPORTED`、`ROW_IDENTITY_UNSUPPORTED` 的产生点。前两个在旧树中就走不到：`ComparisonMode` 只有两个值；有序表的 `order_key` 总是由 `pair_planning.py` 设为单列的位置列。第三个在旧树中当有序表的有效键多于一列时产生（`ordered.py::_single_column`），新树（Rust 有序比较）怎样处理多列行标识，设计会话没能从源码确定。另有 `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`、`METADATA_ROUTE_REQUIRES_NATIVE_ROWS`、`METADATA_ROLE_REQUIRES_NATIVE_ROWS` 四个新码可能作为表诊断写入，前端没有专门文案时按现有规则显示“比较过程有提示”加原始码（`formatSurfaceDiagnostic`），不会出错 | **交 owner 转后端确认（§11 Q21）**，不阻塞 FE3c：确认前 `diagnostics.ts` 保留这三个码的文案，新码走通用文案；确认后再决定是否删除或补文案 |

- 以上不改变 FE3c 的范围；t1 的预期值仍由 §8.3 在运行时从同一 `vnext/` 树的 `real_dump_journey.py` 读取，不受影响。
- FE3c 真实旅程中若出现上表没有预期的诊断码，按 §8.3“有诊断时……handoff 列出出现过的编码”记录，不作为停止条件。

## 3. 阶段安排

### 3.1 甲、乙两个方案（2026-11-05，历史）

- **甲：** 整个 FE3 等 BE-a、BE-d 合入 main 后开始。
- **乙（owner 2026-11-05 同意，§11 Q1）：** 拆成 FE3a（不依赖新接口的部分）与 FE3b（新接口合入后）。
  - 理由：运行框架与新接口无关、工作量最大，可以先做实、先审核；M1 提前测量。

2026-11-07 后端交付超出原 FE3b 的范围（§2.3 第 9 行起），owner 决定把 FE3a 之后的工作再拆成 FE3b 与 FE3c（§11 Q13，核对报告 §8.2）：

- 归档核验与关闭是新界面，需要先出设计并经 kickoff 审核；FE3b 只需本步修订即可开始，不等这部分设计；
- 同字节 tar 互通是后端写明的“FE3 依赖解除”条件，可以先完成；
- 合成输入没有生成时间，A 之后的每次归档都要先接受业务核验异常（核对报告 §8.1 第 1 项），因此需要归档的旅程都放进 FE3c，边界清楚；
- 代价：多一次审核与 04 取证。

### 3.2 子阶段

| 子阶段 | 内容 | 前置条件 | 退出 tag | 审核范围 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| FE3a 运行框架与带入项（已退出） | §7 的 M7、n3、n8；§4 运行框架与冒烟；§4.6 上传输入；§5.4 生成类型一致性；M1 的打包测量 | 本文经 owner 确认 | `fe-fe3a-exit` | `fe-fe2c-exit..<FE3a 候选>` | 审核通过；04 上模拟接口全量 runner（含截图）、上传包后端校验、真实 backend 冒烟各一次通过；M1 测量完成并经审核会话与 owner 判断 |
| FE3b 契约与基础（已退出） | `fe-vnext` 合入 main `748de5034d`（含 `p6-be-a-d-exit`，§2.1）；§5.1–§5.3 快照刷新、类型与模拟数据同步、旧路径清理；§5.5 tar 接收修复与同字节 OPFS 互通；§6.1–§6.3 上传模式撤回、占用禁用与刷新恢复（含 n3 改为基于指针）；§6.4 终局处置只读显示；§4.7 中标为 FE3b 的真实旅程（不需要归档）；FE3a 带入的 N1、N2、N5（§15.2） | 本文第 1 步经 kickoff 审核与 owner 确认（含 Q14）；审核会话现场核对接口、镜像与节点占用后发出提示词 | `fe-fe3b-exit` | `fe-fe3a-exit..<FE3b 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图，含 §5.5 的同字节互通用例）、上传包后端校验（`validate-upload-package.sh`）、`--suite journeys`（FE3b 部分）各一次通过；§6、§6.4 截图经 owner 确认 |
| FE3c 归档核验与完整旅程 | §16 归档业务核验的显示与逐项接受/撤销、关闭出口、待审核阻塞与过期通过的界面；§4.7 中标为 FE3c 的真实旅程（R4 身份确认、R8、R9 三节点、R12 关闭）；§4.6 A–D 序列及其核对；§8 t1 旅程与 M1 复测；FE3 退出 | `fe-fe3b-exit`；本文第 2 步经 kickoff 审核与 owner 确认（含 Q15–Q20，2026-11-09 已确认）；§11 Q18 的后端补缺已交付（`94b25a3279`，独审 GO），§16.6 已定稿（修订 3）；后端为 `vnext/` 树 `6368c9c40c` 补交的生产 OpenAPI 原件已交付（§5.2）；所需草图或文字规格已提交（Q19：用 §16 的文字规格） | `fe-fe3c-exit` | `fe-fe3b-exit..<FE3c 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图）、上传包后端校验、`--suite journeys`（完整集，含 FE3b 部分）各一次通过；05 上 `--suite t1` 证据运行一次通过（§9）；§16 截图经 owner 确认 |

- FE3c 结束即 FE3 结束，FE4 以 `fe-fe3c-exit` 为起点。
- FE3c 的设计（本文第 2 步）可以在 FE3b 实施期间进行；FE3c 的实施从 `fe-fe3b-exit` 开始。
- 三个子阶段都在 `fe-vnext` 上进行，合入 main 只用合并，不 rebase：
  - FE3b 开始时合入 `748de5034d`（§2.1，owner 选甲），期间不再合入 main；
  - FE3c 开始时合入 main `fd9e383d76`（owner 2026-11-09，§2.1；`vnext/` 树 `6368c9c40c`，含 S3、S4 的退出与 Q18），不合入其后含 S5 实施代码的 main；FE3c 期间是否再合入，见下文“FE3c 期间”。
- **路径核对（每个子阶段都做）：** 设 `<main>` 为最后一次合入 `fe-vnext` 的 main 提交：
  - `git rev-parse <候选>:vnext` 与 `git rev-parse <main>:vnext` 相等；
  - `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径。
- 审核范围中来自 main 的文档与 `vnext/` 不在前端审核范围内；`vnext/` 由后端审核负责。
  **例外：** main 上直接提交的 `frontend/` 改动属于前端审核范围。FE3b 合入会带入 `55d56efb6e`（06/07 节点就绪时加入 `GATEWAY_FE_TEST_WORKERS`，只改 `frontend/scripts/run-tests.sh`），由 FE3b 审核一并核对（核对报告 §6 第 8 项）。
- **FE3b 期间 main 的变化：** 后端继续在 main 上改 `vnext/` 不影响 FE3b：路径核对以 `748de5034d` 为 `<main>`，候选的 `vnext/` 树应为 `56720104af`。
  main 在 `748de5034d` 之后若有 `frontend/` 或 `docs/frontend-vnext/` 的改动（本文与审核报告除外），FE3b 不合入；到 FE3c 合入时进入 FE3c 审核范围（同 `55d56efb6e` 的例外）。
- **FE3c 期间：** 路径核对以 `fd9e383d76` 为 `<main>`，候选的 `vnext/` 树应为 `6368c9c40c`。后端若再改 `vnext/` 并合入 main，前端按需要重新合入，路径核对以最后一次合入的 main 为准；运行时 OpenAPI 与快照不一致时按 §5.2 处理。
  重新合入可能改变 §4.3 的依赖镜像 tag 与 §5.2 的比对原件，先停下交审核会话重新核对并填写 §13.5 的对应值，不自行沿用。

**FE3a 已退出（2026-11-05）：**

- **tag 与范围：**
  - 附注 tag `fe-fe3a-exit`（tag 对象 `8dd0f765b3`）指向证据 handoff 提交 `0e7caf66f4`，审核范围 `fe-fe2c-exit..0e7caf66f4`；
  - 04 运行的提交为 `58c6c9e29f`，代码候选为 `09715b2205`，tag 目标与它们只差 `docs/frontend-vnext/fe3a-handoff.md`；
  - 三者 `frontend/` 树相同，都是 `8a9f11c84f`；`vnext/` 树 `2791d3ff3d` 未改动。
- **04 权威运行**（都在 clean detached worktree `/home/dev/gdds-fe-fe3a-evidence` 上）：

  | 运行 | 结果 | 日志 | SHA256 |
  | --- | --- | --- | --- |
  | 模拟接口全量 runner | exit 0 | `/home/dev/gdds-fe-logs/frontend-fe3a-evidence/frontend-tests-20261105T114845Z.log` | `3383d9a2…4dfa4b72b` |
  | 真实 backend 冒烟 | exit 0，9 个用例通过 | `/home/dev/gdds-fe-logs/fe3a-04/smoke/real-backend-e2e-smoke-fe3a-evidence-58c6c9e2-20261105T114950Z-1558148.log` | `98768dfd…7c14355` |
  | 上传包的后端校验 | exit 0，由审核会话补跑（[证据核对](reviews/fe3a-evidence-check-1.md) §2） | `/home/dev/gdds-fe-logs/fe3a-04/upload-validation/upload-validator-58c6c9e29f-20261105T120740Z-1568674.log` | `395d0f3b…5a1a963` |

- **截图：** 96 张（1280、1920），在 04 的 `/home/dev/gdds-fe-evidence/fe3a-04/screens/`。
  - 聚合 SHA256 `15e316d3…fc0fb1e065e9`，公式 `cd <目录> && sha256sum *.png | sort -k2 | sha256sum`；
  - owner 已看图确认，以后可能微调符号与字体，不需要大改。
- **M1：** 在 05 上测量，t4 v1 的 renderer 峰值增量最大 670.62 MiB，外推到 1 GB 约 2.06 GiB。按 Q12 满足，不改流式。
  owner 接受“用生产构建测量”这一偏差（§8.4 写的是开发构建）。
- **依据：** [审核](reviews/fe3a-review.md)：定向修复；[复审第 1 轮](reviews/fe3a-rereview-1.md)：定向修复；[第 2 轮](reviews/fe3a-rereview-2.md)：通过；[证据核对第 1 次](reviews/fe3a-evidence-check-1.md)：通过。
- **handoff 勘误**（不改 handoff，FE3b handoff 不再沿用错误说法）：
  - §9 第 5 项：接受偏差的是 owner，不是实施方；
  - §9 第 4 项：“04 取证未执行”已过时；
  - §0.5 标题：标题写“复审通过前”，实际上 04 取证是在复审第 2 轮通过之后进行的；
  - 漏项：handoff 没有记录上传包的后端校验。
- **交 owner：** handoff §8 中给 AGENTS 与 testing-conventions 的建议条文，由 owner 转治理会话（§12）。

**FE3b 已退出（2026-11-09）：**

- **tag 与范围：**
  - 附注 tag `fe-fe3b-exit`（tag 对象 `8da25ee3f5`）指向 04 证据 handoff 的勘误提交 `ed5d2c24e9`，审核范围 `fe-fe3a-exit..ed5d2c24e9`；
  - 04 运行的提交即代码候选 `dac69890a8`，tag 目标与它只差 `docs/frontend-vnext/fe3b-handoff-fix4.md` 与 `fe3b-evidence-04.md`；
  - `frontend/` 树 `54b5a333c6`；`vnext/` 树 `56720104af`，与最后合入的 main `748de5034d` 相同，`748de5034d..ed5d2c24e9` 只改 `frontend/` 与 `docs/frontend-vnext/`（路径核对通过）；
  - main 先合入审核报告分支（`dae8192ed8`），再合入 tag（`ffccdd411b`）。main 在 `748de5034d` 之后没有 `frontend/` 改动，合入后 `frontend/` 树仍为 `54b5a333c6`。
- **04 权威运行**（都在 clean detached worktree `/home/dev/gdds-test-tmp/wt/fe3b-evidence-04-dac69890` 上，各一次）：

  | 运行 | 结果 | 日志 | SHA256 |
  | --- | --- | --- | --- |
  | 模拟接口全量 runner（含截图） | exit 0；单测 175、e2e 63 通过 | `/home/dev/gdds-fe-logs/fe3b/evidence-04/frontend-tests-20261109T033153Z.log` | `577e044b…a092ac70` |
  | 上传包的后端校验 | exit 0；4 个包，`failures=0` | `/home/dev/gdds-fe-evidence-04/validate-logs/upload-validator-dac69890a8-20261109T033445Z-1562748.log` | `40836269…5dcb25d` |
  | 真实 backend `--suite journeys` | exit 0；18/18 通过，`openapi_compare=match`，`cleanup_status=ok` | `/home/dev/gdds-fe-evidence-04/real-logs/real-backend-e2e-journeys-fe3b-evidence-04-dac69890a8-20261109T033636Z-1563806.log` | `9037ff78…96728e6` |

- **截图：** 146 张（1280、1920），在 04 的 `/home/dev/gdds-fe-shots/fe3b-04-dac69890/`；清单 `shots.sha256` 的 SHA256 为 `13c705e3…1692f222`。
  owner 2026-11-09 已看图确认（含 N3、N4、N7）。
- **依据：** [审核](reviews/fe3b-review.md)：定向修复；[复审第 1 轮](reviews/fe3b-rereview-1.md)、[第 2 轮](reviews/fe3b-rereview-2.md)：定向修复；
  [第 3 轮](reviews/fe3b-rereview-3.md)：通过；[N5 定向复核](reviews/fe3b-rereview-3-n5.md)：通过；
  [证据核对第 1 次](reviews/fe3b-evidence-check-1.md)：实质通过，handoff 定向勘误；[勘误复核](reviews/fe3b-evidence-check-1-errata.md)：通过。
- **handoff 勘误：** 04 证据 handoff 原提交 `a300b16485` 有 5 个 SHA 抄错，已由 `ed5d2c24e9` 更正，并改为用脚本核对（证据核对 E1）。
- **流程偏差（证据核对 P1）：** 取证时实施会话把开发主机主工作区从 `main` 切到了分支 `fe3b-evidence-04`。该分支的提交已包含在 `fe-vnext` 中，主工作区切回 `main` 后删除该分支。
- **非阻塞项，交 FE3c kickoff 决定是否纳入**（审核建议，不作 FE3c 退出条件）：
  - N2：`resumeNotice` 在页面生命周期内不归零，再次提交后的执行提示仍显示在红色提示框里；
  - N6：`retryResume` 不经过在途合并，快速连点“重试”会并行两次读取序列；W9④ 第一次重试后的断言文字不能区分新旧状态；G3 的“提升基线等于 head 可不在数组里”的放宽也作用于合并数据集；
  - N7：预览页顶栏撤回与提交的禁用原因并排、无分隔；
  - N8：截图中的等待时长按墙钟计算，每次运行的截图不同，建议截图用例固定时钟。

### 3.3 FE3a 在当时 backend 上无法验证的内容（历史）

FE3a 时 backend（vnext 树 `2791d3ff3d`）的两个 bundle 路由只返回 manifest JSON，前端按 tar 解析必然失败。FE3a 冒烟因此只断言 Preview 结果可读，对页面自动下载 bundle 失败不作断言。

- 当时“要等 BE-d”“要等 BE-a”的各项，现在按 §3.2 分到 FE3b 与 FE3c（§4.7 的“子阶段”一列）。
- **FE3b 删除冒烟中以“下载比较结果失败”为判据的临时断言**（`e2e-real/smoke.spec.ts` 中等待“预览已生成，但下载比较结果失败，请重试”的断言），改为断言 tar 下载、安装成功并进入差异浏览（§4.7）。

## 4. 真实 backend e2e 的运行框架

通用执行与证据约定见 [testing-conventions「真实 backend e2e」](../backend-vnext/testing-conventions.md#真实-backend-e2e)。

FE3a 已实现本节（`frontend/scripts/run-real-backend-e2e.sh`、`playwright.real.config.ts`、`e2e-real/`，见 FE3a handoff）。FE3b、FE3c 在其上增加套件与场景，规则不变。

### 4.1 入口

- 提交在 `frontend/scripts/` 下的独立脚本 `run-real-backend-e2e.sh`，**不作为 `run-tests.sh` 的选项**（§11 Q4）。理由：
  - 前提条件不同：占用标记、Compose、backend 镜像与 vnext 树；
  - `run-tests.sh` 不依赖后端镜像（AGENTS FD7），这一点不变；
  - 与上传包后端校验脚本（FE2 kickoff §7.1）做法一致。
- 套件参数：
  - `--suite smoke`：FE3a 的冒烟，FE3b 按 §3.3 改判据后保留，作为起栈后的快速检查；
  - `--suite journeys`：FE3b 实现，包含 §4.7 中标为 FE3b 的旅程；FE3c 补入标为 FE3c 的旅程，成为完整集；
  - `--suite t1 --input-root <目录>`：FE3c 实现（§8）。
  目前 `journeys`、`t1` 与 `--input-root` 以 exit 2 拒绝，由各自子阶段实现。
  另有 `--log-dir <绝对路径>`、`--evidence-dir <绝对路径>`（失败时的 trace、截图与参考截图），都必须在 worktree 外。npm 缓存路径与 `run-tests.sh` 使用同样的环境变量（§2.2）。
- Playwright 使用单独的配置与目录（`playwright.real.config.ts`、`e2e-real/`）；`run-tests.sh` 的 `playwright test` 不收集这些用例。
- 不修改 `vnext/`。只读使用 `vnext/deploy/compose.yaml`、`vnext/scripts/build-backend-dependency-base.sh --print-input`、
  `vnext/scripts/build-repository-service-image.sh`。需要改它们才能运行时，停下交设计会话（§10）。
- AGENTS FD7 已列独立入口与占用管理；执行细节见 [testing-conventions「真实 backend e2e」](../backend-vnext/testing-conventions.md#真实-backend-e2e)（FE3a handoff §8，owner 2026-11-08 授权治理整理）。

### 4.2 节点、占用与单飞

- **节点（AGENTS 2026-11-06/07）：**
  - 类型检查、lint、单测、构建、截图与模拟接口 e2e 在 07，设置 `GATEWAY_FE_TEST_WORKERS=2`，不获取占用标记，可与后端并行；
  - 真实 backend 调试、上传包后端校验的调试运行与 t1 在 05（DC36：t1–t3 在 05）；
  - 取证在 04，只在审核通过后运行（DC30）；
  - 前端不使用 `ct108-gw-dms`；新节点 06 不跑前端。
- 真实 backend 运行开始时按 DC70 补充用 `mkdir /home/dev/gdds-node-busy.d` 原子获取整机占用，写入会话名、用途、开始时间（UTC）、hostname、worktree 与 HEAD。
  - 会话名按角色与子阶段写，例如 `fe3b-impl`、`fe3b-review`、`fe3c-impl`；
  - 目录已存在即退出（非 0），等待对方释放，不抢占；
  - 占用标记的用途为计时测量时，前端在该节点上的任何运行（含 07 以外不需要占用的项）都等待（前端 kickoff §6）。
- 获取后另以非阻塞方式（`flock -n`）持有后端 Compose 门禁使用的 `/tmp/gateway-compose-gate.lock`（`compose_gate_harness.py`），失败即退出，与占用标记的处理一致。
- 运行前的残留检查（AGENTS 整机单飞）：
  - 没有容器发布 8000 端口（`docker ps --filter publish=8000`）；
  - `/proc` 中没有 dolt 进程；
  - 没有本脚本命名前缀的 Compose 项目、卷、网络与工具链容器残留（§4.5）。

  任一不满足即退出，不清理他人的资源。
- 退出时（含失败与可捕获的中断）先清理（§4.8），确认没有本次的容器、卷、网络与进程后，释放 flock，最后删除占用标记。
  清理核对失败时保留占用标记，把用途改写为 `cleanup-failed` 并以非 0 退出，交 owner 处理。

### 4.3 镜像

- **backend/worker：** 按 AGENTS“backend/worker（自 `p6-backend-image-exit` 起）”，在节点本机离线构建：
  - `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`；
  - `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<tag>`，`<tag>` 由 `vnext/scripts/build-backend-dependency-base.sh --print-input` 对当前 HEAD 算出，
    该镜像必须已在本机且 `gateway.backend.dependency-input-sha256` label 与输入一致，否则停止（缓存缺失），不在测试节点上构建依赖镜像；
  - `GATEWAY_DOCKER_BUILD_NETWORK=none`；
  - 保留 Compose build，不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- **依赖镜像的来源：**
  - FE3b 合入的 `748de5034d` 需要 `gateway-backend-deps:lock-d054366c02fa`，04、05 都已有且身份一致（§2.2）。合入后的 HEAD 上 `--print-input` 必须仍得此 tag，否则停止并报告；
  - FE3c 合入的 main `fd9e383d76` 上 `--print-input` 得 `gateway-backend-deps:lock-578e079b762e`（输入 `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`）。合入后的 HEAD 上必须仍得此 tag，否则停止并报告：
    - 来源为后端 S3 已核收的预填充链；Q18 交接记录 config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`；
    - 审核会话 2026-11-09 已在 04、05 上只读核对：label 与输入一致，19 个 DiffID 两节点相同；config digest 由运行时的入口脚本再核；
    - **这次不需要新的预填充。** 修订 2 预计的 `lock-ca0ba0a24a5e` 不再使用；
    - RS 依赖镜像仍为 `lock-6dc9659f0aee`（`repository_service/uv.lock` 未变）；
  - 不在测试节点上构建依赖镜像。
  （FE3a 用的 `lock-c668cef8e47e` 已不再需要。）
- **Repository Service：**
  - 构建前由程序核对 `gateway-p2r1-repository:lock-<repository_service/uv.lock 的 SHA256 前 12 位>` 在本机存在，且 `gateway.p2r1.uv-lock-sha256` label 一致；
    不一致即停止。否则 `build-repository-service-image.sh` 会自动改用缓存 URL 构建；
  - 用 `vnext/scripts/build-repository-service-image.sh` 按当前 HEAD 构建，`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE` 设为上述 tag，`GATEWAY_DOCKER_BUILD_NETWORK=none`；
    构建失败（包括需要访问网络）即停止，视为缓存缺失；
  - `GATEWAY_REPOSITORY_SERVICE_IMAGE` 设为本次运行专用的 tag（例如 `gateway-repository-service:fe-<HEAD12>`），不覆盖后端会话使用的 `gateway-repository-service:local`，也不复用后端旧候选的 tag（FE3b 评估交接 §6）；
  - 所有 `docker compose up` 都带 `--no-build`（同 `compose_gate_harness.py`）：compose 中 RS 同时有 `image:` 与 `build:`，tag 不存在时会按 compose 的参数联网构建；
  - 运行结束时删除本次 tag，保留构建层缓存。
- **身份记录（每次运行）：**
  - 依赖镜像：tag、`dependency-input-sha256` label、本机 image ID、`docker image inspect` 的 `RootFS.Layers`；
  - RS：tag、本机 image ID，以及 build-input、source-tree、revision label；
  - backend/worker：本机 image ID；
  - Docker 与 Compose 的版本。

  config digest 与全部 DiffID 只在跨节点传输时比较一次，写进 handoff；每次运行不对依赖镜像做 `docker save`（约 4.7 GB）。
  `backend/Dockerfile` 在预置依赖模式下已核对 tag、输入摘要与五个输入文件。
- **前端工具链：** 与 `run-tests.sh` 相同的固定镜像与身份核对、npm 离线缓存。

### 4.4 Compose 栈

1. 项目名 `gdds-fe-<子阶段>-<HEAD12>-<UTC 时间戳>`，全部小写（Compose 项目名只能用小写字母、数字、`-` 与 `_`；时间戳写成 `20261105t101500z` 这样的格式）。
   命令为 `docker compose -f vnext/deploy/compose.yaml -p <项目名>`。
2. secret 与配置写在 worktree 外的本次运行目录（容器可读的权限）：Repository bearer、internal bearer、session 文件、部署映射。
   token 每次随机生成，不提交，不进入构建产物，也不写进脚本日志。Playwright trace 中含有本次的临时 token（§4.9）。
3. `build backend worker` → `up -d --no-build repository-service` → 等 RS ready → 播种全部 scope 的仓库（§4.6） → 写好全部映射 →
   `up -d --no-build backend worker` → 等 `/readyz` 与 worker 就绪。backend 启动后才读取映射，因此映射要在此之前写好。
4. 运行时 OpenAPI 比对（§5.2）通过后才运行浏览器用例。

### 4.5 工具链容器与 backend 的网络

- 工具链容器加入本次 Compose 项目的默认网络（`--network <项目名>_default`），`GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000`。
  浏览器只访问容器内的前端服务器，由它代理 `/v1`、`/readyz`、`/openapi.json` 到 backend（`vite.config.ts` 的代理不分模式，preview 沿用；与生产同源反向代理的形态一致）。
- 工具链容器使用固定的名称（`<项目名>-toolchain`）与 label `com.docker.compose.project=<项目名>`。它不属于 Compose 项目，中断时如果仍连在网络上，`compose down` 删不掉网络。
  因此清理时先停止并删除它（§4.8），运行前残留检查与清理后核对也包括它。
- 不用 host 网络：不在宿主机上新增端口；8000 由 Compose 发布，仍按 §4.2 占用。
- `npm ci --offline` 照常离线；日志记录所用网络名与 `docker network inspect` 的 ID。
- **被测构建（§11 Q5）：** 真实 e2e 测生产构建（`npm run build` 后 `vite preview`），不测开发构建：
  - 生产构建是用户实际拿到的产物；
  - 生产构建中没有身份选择（FE2 kickoff §6.2）。`currentGatewaySession()` 在每次请求时读取 `window.__gatewaySession`，
    由 Playwright 在页面脚本运行前注入（`addInitScript`）；token 来自 §4.4 生成的身份文件，以只读方式挂进容器；
  - **每个身份用一个 browser context**，各自注入；需要两个身份同时在线的场景（例如 §6.3 W5）开两个 context；
  - OPFS 按 context 隔离，“再次打开同一 Preview 不重新下载”要在同一个 context 中验证；
  - 开发构建的模拟身份切换（`DevIdentityControl`）与模拟接口只用于模拟接口 e2e，不改动。

### 4.6 测试身份与初始数据

**身份：** 会话文件按 backend 已支持的格式生成（`sessions[]`：`token`、`actor_id`、`gateway_device_external_key`、`business_project_id`、`permissions`；
同 `real_dump_journey.py` 的 `_write_compose_secrets`；前端 kickoff §4.3）。每个 scope 一组，权限是精确字符串，没有继承（`vnext/deploy/README.md`）。

- 每个身份有不同的 `actor_id`：工作区按 actor 隔离，本人撤回按 `Submission.created_by` 判定。
- 组态树读 History，审核模式的历史比较与轮询也要读 History，因此各身份都带 `workspace_read` 与 `read_project_history`。

| 身份 | 权限（在上述两项之外） | 用途 |
| --- | --- | --- |
| 提交人（本人撤回） | `upload_submit_workspace`、`preview_workspace`、`withdraw_own_submission`；**不带** `review_submission` | 上传、Preview、提交、上传模式撤回（§6） |
| 提交人（仅上传） | `upload_submit_workspace`、`preview_workspace` | §6“无权限”场景 |
| 提交人（无 Preview 权限） | `upload_submit_workspace` | Preview 403（R10） |
| 审核人 | `review_submission` | 审核模式的通过、退回、撤回 |
| 归档确认人 | `archive_submission` | 归档主线；FE3c 的逐项接受与关闭（§16） |
| 无权限身份 | 无 | 上传、审核查询、归档候选的 403（R10） |
| 提交人 2（本人撤回，FE3c） | 同“提交人（本人撤回）”，另一个 `actor_id` | FE3c 中第二个提交人：待审核阻塞、被关闭后读取本人提交的审核与处置、重新上传（§4.6 J1、J2） |

- FE3a 中“本人撤回”身份不带 `withdraw_own_submission`（当时 backend 没有该权限）；FE3b 补上。
- 验证本人撤回时不用审核人或全权限身份代替（前端 kickoff §4.3；FE3b 评估交接 §3）。
- 身份文件同时给出 `business_project_id`、`gateway_device_external_key`，由用例按身份注入；脚本日志只记录身份名与权限，不记录 token。

**初始数据：**

- **仓库与映射：** 做法同后端 Compose 门禁（`compose_gate_harness.seed_repository_and_mapping`）：在 RS 容器内 `POST /v1/repositories`，
  核对 `INITIAL` 提交为空，再把 `repository_id`、`initial_commit_id` 写入部署映射（`baseline_head_version = 0`）。backend 启动时据此创建 `INITIAL` 基线。
  多个 scope 时：
  - 每个 scope 播种用不同的 RS `Idempotency-Key`。harness 固定使用 `compose-seed-repo`，照抄会回放同一个仓库；
  - 每个 scope 的 `business_baseline_node_id` 互不相同；
  - 全部映射在 backend 启动前写好。
- **scope 隔离：** 每个互相独立的旅程用自己的 scope（一条映射、一个仓库、一组身份），失败不连带其他旅程。用例单 worker 串行（`workers: 1`，不重试）。
- **共用上传输入（FE3a 已完成）：** bundle fixture 生成器的输入在 `frontend/src/test/fixtures/source/upload-inputs/`，与原字符串逐字节相同，此后继续保持逐字节不变。
- **真实 e2e 的上传输入（owner 2026-11-05，§11 Q10）：**
  - **与模拟 fixture 分开的理由：** 共用的 `sql-baseline.sql`、`sql-initial.sql`、`sql-modified.sql` 都含没有 `gid` 列的有序表 `b1_n1_iec104_yc_list`。
    这是有意的设计，用来产生模拟 fixture 中的有序表诊断；真实 Preview 对它返回 `KEY_MISSING`。改共用文件会改变全部已提交的 bundle fixture 与诊断场景，所以真实 e2e 另备输入，模拟 fixture 不动。
  - **来源规则：** 从共用文件派生，只补真实 backend 接受所需的最少列，不改数据本身：
    - 派生文件在 `frontend/e2e-real/fixtures/upload-inputs/`，与共用文件同名：`sql-baseline.sql`、`sql-initial.sql`、`sql-modified.sql`；
    - 三份文件都只改 `b1_n1_iec104_yc_list` 的两行：表定义加 `gid INT NULL` 作为第一列，`INSERT` 的那一行补 `gid = 1`，其余逐字节相同；
    - 不需要改的文件（`sql-replacement-current.sql`、`logics-1.xml`、`logics-2.xml`、`logics-3.xml`）由运行脚本直接从共用目录读取，不复制；
    - 单测（进入 `run-tests.sh`）核对派生规则；以后若要再补列，按同一规则扩展替换表与单测；无法只靠补列让 backend 接受时，停下交设计会话。
    - 派生规则只为“backend 接受上传”补列，不补 `version_manager.saved_time`（§11 Q15）。缺生成时间正好产生 FE3c 需要的“同码、同目标、两侧独立”的时间质量项。
  - **`logics.xml` 配对：** `sql-baseline` ↔ `logics-1`，`sql-initial` ↔ `logics-2`，`sql-modified` ↔ `logics-3`，`sql-replacement-current` ↔ `logics-3`。
  - **上传目录：** 每个上传目录包括：根目录一个占位 `.pmc`、`sql/dbcfg.sql`、`comps/logic/logics.xml`。目录写在 worktree 外的本次运行目录；FULL 的 ① 与 ② 各用一个目录。
- **四类上传（下表“派生”指上面的派生文件，“共用”指共用目录中的文件）：**

  | 输入 | 用途 | ② 本次归档组态 | ① 原始组态备份（只 FULL） | 相对当时基线的规范变化 |
  | --- | --- | --- | --- | --- |
  | A | 第一次 MODIFIED_ONLY（基于空 `INITIAL`） | 派生 `sql-baseline` + `logics-1` | — | 全部表都是新增 |
  | B | 归档 A 后的 FULL | 派生 `sql-initial` + `logics-2` | 与 A 相同 | 相对 A：`device` 改一行、删一行、增一行；`keyless_demo` 内容；`schema_demo` 结构与值；`b1_n1_iec104_syx_list` 移动与空行；`logics.xml` |
  | C | 归档 B 后再一次 MODIFIED_ONLY | 派生 `sql-modified` + `logics-3` | — | 相对 B：`device` 改一行；`keyless_demo`；删除表 `retired_table`、新增表 `added_table`；`schema_demo` 加列与值；`logics.xml`（`b1_n1_iec104_syx_list` 不变） |
  | D | `DIFFERENT_PROJECT`（R4 的身份确认） | 共用 `sql-replacement-current` + `logics-3` | — | `version_manager` 为 `project-b`，而 A、B、C 都是 `project-a`；表集合也不同 |
  | E（FE3c） | FULL，① 取 C 的内容，用来产生“来源靠同轮提交解释、关闭后变为未解释”（§4.6 J2） | 派生 `sql-initial` + `logics-2`（与 B 的 ② 相同） | 派生 `sql-modified` + `logics-3`（与 C 相同） | 相对 A：同 B 的 ②。① 与 A 不同，只能由同轮中 C 的 ② 解释 |

  - **上传顺序：** 每个 scope 内，每次提交都必须相对当时的基线有规范变化，否则提交返回 409 `NO_CANONICAL_CHANGE`。实施会话写出每个 scope 的上传序列，并在 handoff 列出：
    - 被退回或撤回后重新上传，可以用同一输入：规范变化是相对基线计算的，不是相对上一次上传；
    - 已归档某输入后，再上传同一输入会得到 `NO_CANONICAL_CHANGE`，序列中不要这样排；
    - D 必须在至少归档过 A、B、C 之一的 scope 上进行。
  - **FE3b 的上传（不需要归档）：** 都基于空 `INITIAL`：A 的 MODIFIED_ONLY；B 的 FULL（① = A，② = B 的 ②）。退回、撤回后重新上传用同一输入。
  - **FE3c 的上传：** 两个 scope，J1 与 J2，见下文。
- **FE3a 的核对（已完成）：** 5 个独立 scope 的上传都被真实 backend 接受并 Preview 成功（FE3a handoff）。FULL 在空 `INITIAL` 上走到 `SUCCEEDED`。
- **FE3a 证实不了、留给 FE3c 的（都需要归档，在 J1 中核对）：**
  - B 的 FULL 中，`baseline_to_initial` 比较对 `changed_table_count = 0`（① 与已归档的 A 相同；不为 0 时停下交设计会话），`initial_to_modified` 比较对 ≥ 1；
  - C 相对 B 有变化；D 的身份对为 `DIFFERENT_PROJECT`；
  - A、B、C、D 的提交都不返回 `NO_CANONICAL_CHANGE`。

**FE3c 的上传序列与预期的业务核验异常（第 2 步）：**

- **预期异常的来源：** 设计会话阅读后端源码（`application/archive/business_validation.py` 的 `derive_archive_business_validation` 与 `_append_time_quality`，`queries.py:424`）推出，未运行产品：
  - 每个实际上传的一侧都检查生成时间质量，与基线是否为空无关；合成输入的 `version_manager` 没有 `saved_time` 列（状态 `COLUMN_ABSENT`），每个上传侧都会有一项 `GENERATION_TIME_MISSING`。
    MODIFIED_ONLY 只检查 ②（① 为 `BASELINE_REUSED` 或 `INITIAL_EMPTY`）；FULL 检查 ① 与 ②；
  - 基线为空 `INITIAL` 时没有基线时间项，来源为 `NOT_APPLICABLE`；基线来自已归档提交且没有有效时间时，每轮有一项 `BASELINE_TIME_UNAVAILABLE`，受影响提交为本轮全部候选；
  - 没有有效时间时比较结果为 `NOT_COMPARABLE`，不产生 `TIME_ABNORMAL_*` 与 `GENERATION_TIME_LAST_NOT_MAX`；
  - 每个未选中的候选一项 `APPROVED_SIBLING_EXCLUDED`；选中项有身份确认时一项 `PROJECT_IDENTITY_EXCEPTION`。
  - **与核对报告 §8.1 第 1 项的推断不同：** 核对报告认为归档 A 没有时间异常；按上述源码，A 的 ② 也有一项 `GENERATION_TIME_MISSING`。以下表格按源码推断。
  - **后端已核对（2026-11-08，`1981882cc6`）：** 上传侧的时间质量检查与基线是否为空无关，合成 A 预期一项 `GENERATION_TIME_MISSING`（`MODIFIED`），与本节一致；后端语义不改。表格仍是未经产品实测的推断，下面的实测校正规则不变。
- **实测校正（规则）：** FE3c 在 05 调试首轮中，每次打开归档预检时由用例把 `business_validation.issues` 与 `anomalies` 的 `(subject_kind, issue_code, side, 受影响提交)` 集合与下表比较，并写入日志。比较口径（修订 2 审核 C3）：
  - 每次比较用**带选中项**（`selected`）的预检：`anomalies` 只在预检带 `selected` 时非空；
  - `business_validation.issues` 只含三类业务 `subject_kind`（来源、时间质量、时间顺序），与下表**去掉** `APPROVED_SIBLING_EXCLUDED`、`PROJECT_IDENTITY_EXCEPTION` 两类后的集合比较；
  - `anomalies` 与下表全部项比较（含同级排除与身份例外）；
  不符即停止，交设计会话：设计会话判断推断有误时改正本表；判断为后端缺陷时转后端。不改输入、不放宽判据去迁就。校正后的表写进 FE3c handoff。

**J1：主线、待审核阻塞、两侧独立项与身份确认（R1、R4、R8、R9）**

身份：提交人（本人撤回，下称 s1）、提交人 2（s2）、审核人、归档确认人（同一身份可开两个 context）。

| 步 | 操作 | 预期 |
| --- | --- | --- |
| 1 | s1 上传 A（MODIFIED_ONLY）→ Preview → 提交；审核人通过 | — |
| 2 | 归档确认人打开 A 的归档主线 | 异常 1 项：`GENERATION_TIME_MISSING`（`MODIFIED`，A）。来源 `NOT_APPLICABLE`。“确认归档”禁用 |
| 3 | 接受该项 → 撤销 → 再接受；确认选择 → 确认归档 | 接受后原始诊断仍显示“缺少组态生成时间”，处理状态为“已接受”；撤销后为“已撤销接受”，“确认归档”禁用；归档成功，head 前移，树显示“归档基线 1”，A 节点“已归档”（§6.4 D1 的真实覆盖） |
| 4 | s1 上传 B（FULL，① = A，② = B 的 ②）→ Preview | `baseline_to_initial` 的 `changed_table_count = 0`，`initial_to_modified` ≥ 1 |
| 5 | s1 提交 B；s2 上传 C（MODIFIED_ONLY，基于归档基线 1）→ 提交；审核人通过 B | B `APPROVED`，C `PENDING` |
| 6 | 归档确认人打开 B 的归档主线 | `blockers` 含 `ARCHIVE_PENDING_REVIEW`；待审核列表显示 C 的显示名；“确认归档”禁用 |
| 7 | 审核人退回 C；s2 重新上传 C → Preview（不提交，作为草稿）；归档确认人重新预检 | 待审核阻塞消失（草稿不阻塞）。异常 3 项：`GENERATION_TIME_MISSING`（`INITIAL`，B）、`GENERATION_TIME_MISSING`（`MODIFIED`，B）、`BASELINE_TIME_UNAVAILABLE`（`BASELINE`，[B]）。来源：B `EXPLAINED`（匹配当前基线） |
| 8 | 只接受 B 的 `INITIAL` 项 | B 的两张卡分别显示，`MODIFIED` 仍为“未处理”，“确认归档”禁用（两侧独立） |
| 9 | 接受其余两项；在第二个 context 中撤销 B 的 `MODIFIED` 项；回到第一个 context 点“确认归档” | 服务器拒绝（409 `ARCHIVE_ANOMALY_UNRESOLVED`：`start.py` 先校验审计，B ② 的最新事件是 `REVOKE`；`ARCHIVE_AUDIT_VERSION_CONFLICT` 只由审计追加产生）；界面提示核验结果已变化，点“重新预检”后 `MODIFIED` 项为“已撤销接受”；不自动重发 |
| 10 | 重新接受 → 确认归档 | head 前移到 B（归档基线 2） |
| 11 | s2 的草稿基于旧基线，重新上传 C → Preview → 提交；审核人通过；归档确认人打开 C 的归档主线 | 异常 2 项：`GENERATION_TIME_MISSING`（`MODIFIED`，C）、`BASELINE_TIME_UNAVAILABLE`（[C]）。接受后归档，head 前移到 C |
| 12 | s1 上传 D（MODIFIED_ONLY）→ Preview → 提交 | 身份对为 `DIFFERENT_PROJECT`，提交对话框要求身份确认（R4） |
| 13 | 审核人通过 D；归档确认人打开 D 的归档主线 | 异常 3 项：`GENERATION_TIME_MISSING`（`MODIFIED`，D）、`BASELINE_TIME_UNAVAILABLE`（[D]）、`PROJECT_IDENTITY_EXCEPTION`（D）。接受后归档 |
| 14 | 审核人历史比较三节点：初始基线、归档基线 1、归档基线 2 → 打开结果浏览 | R9 三节点；结果抽屉计数 |

**J2：有理由关闭、关闭后的重新核验与终局处置（R12；§6.4 D1–D3 的真实覆盖）**

身份：s1、s2、提交人（仅上传，下称 s3）、审核人、归档确认人。

| 步 | 操作 | 预期 |
| --- | --- | --- |
| 1 | s1 上传 A → 提交 → 通过 → 归档 | 同 J1 第 2、3 步（1 项，接受后归档） |
| 2 | s1 上传 B（FULL）→ 提交；s2 上传 C（MODIFIED_ONLY）→ 提交；s3 上传 E（FULL，① = C 的内容，② = B 的 ②）→ 提交；审核人通过三者 | 三个候选 |
| 3 | 归档确认人打开 B 的归档主线 | 异常 8 项：`GENERATION_TIME_MISSING` × 5（B ①、B ②、C ②、E ①、E ②），`BASELINE_TIME_UNAVAILABLE`（[B, C, E]），`APPROVED_SIBLING_EXCLUDED` × 2（C、E）。来源：B 匹配当前基线、C 复用当前基线、E 的 ① 匹配 C 的 ②，三者 `EXPLAINED` |
| 4 | 接受 `BASELINE_TIME_UNAVAILABLE`；在“候选提交”中关闭 C（填写理由）。关闭请求送到 backend 后对浏览器中断一次，前端用同一 key 重试 | 201 后回放 200；界面显示服务器返回的关闭人、时间与理由。关闭由只有 `archive_submission` 的归档确认人完成，请求的 `expected_review_version` 等于同一次候选读取中 C 的 `review_version`（§16.6），不读取 Review |
| 5 | 关闭后自动重新预检 | 异常 7 项：`INITIAL_SOURCE_UNEXPLAINED`（`INITIAL`，[E]），`GENERATION_TIME_MISSING` × 4（B ①、B ②、E ①、E ②），`BASELINE_TIME_UNAVAILABLE`（[B, E]），`APPROVED_SIBLING_EXCLUDED`（E）。**全部项**处理状态为“未处理”：每项的 subject 含 `selection_subject_digest`，它由 `candidate_set_digest` 派生（`queries.py:349-420`），关闭 C 后全部 subject 重新派生，此前接受的 BTU 不再适用（不只是受影响集合变化的项）。界面提示“候选集合已变化，之前的接受不再适用” |
| 6 | s2 刷新工作台 | 两个指针为空，“上传”可用；树中 C 为“已关闭（未归档）”，详情面板显示关闭人、时间、理由；s2 读取 C 的审核：“已通过”＋“已关闭（未归档）” |
| 7 | 归档确认人接受全部 7 项（来源项接受后仍显示“来源未解释”）→ 确认归档 | B 成为归档基线 2（“已归档”），E 为“已关闭（未归档）”，原因“归档时选中了其他提交”（D2），s3 工作区释放 |
| 8 | s2 重新上传 C（基于归档基线 2）→ Preview → 提交；审核人通过；归档确认人打开 C 的归档主线 → 接受 → 归档 | 异常 2 项：`GENERATION_TIME_MISSING`（`MODIFIED`，C）、`BASELINE_TIME_UNAVAILABLE`（[C]）；归档成功 |

- J1、J2 中每次提交都不返回 `NO_CANONICAL_CHANGE`（相对当时基线都有规范变化，已按 A–E 的规范变化核对）。
- E 的 ① 与 C 的 ② 内容相同，假定两者的规范内容身份相同（同一组文件、同一规则）。第 3 步 E 不是 `EXPLAINED` 时按“实测校正”停止。
- 时间倒退（`TIME_ABNORMAL_*`）与 `GENERATION_TIME_LAST_NOT_MAX` 需要输入带生成时间，合成输入产生不了（Q15），只由模拟接口覆盖。
- 真实 e2e 以外，模拟接口 e2e 与 fixture 生成器只用共用目录；派生文件不进入 fixture 生成器。
- 真实数据只在 t1 套件中使用（§8）。

### 4.7 场景

**冒烟（`--suite smoke`）：** FE3a 的各项保留；FE3b 删除“下载比较结果失败”的临时断言，改为：tar 下载并安装成功，页面进入差异浏览后再断言没有未捕获错误（FE3a 复审 N5）。
各输入 scope 的 bundle 标识记 tar 的 `ETag` 与 manifest 的 bundle 摘要（FE3a 复审 N2）。

**全部旅程（`--suite journeys`）：**

| # | 旅程 | 子阶段 | 要点 |
| --- | --- | --- | --- |
| R1 | 工作区与组态树 | FE3b；归档后的树 FE3c | CreateOrGet 第一次 201、刷新后 200；树中 `INITIAL` 基线；提交、退回、撤回后的树节点与状态。归档与关闭后的节点、终局处置显示在 FE3c（R8、R12） |
| R2 | 上传与 Preview | FE3b | 浏览器打包、上传、Preview 轮询、下载 tar（`Content-Length`、`ETag`、逐成员摘要）、安装到 OPFS、进入差异浏览；MODIFIED_ONLY 与 FULL 各一次。FULL 断言恰好两个比较对（0→1 与 1→2），点击上传前等到页面显示“原始备份 + 本次归档”（FE3a 复审第 1 轮 R2）；在同一 context 中再次打开同一 Preview 不重新下载 |
| R3 | bundle 截断重下 | FE3b | 路由拦截截断一次真实 tar 响应：本次安装中止、不留下半包，界面显示下载失败而不是“无差异”；重新下载后可浏览 |
| R4 | 提交 | 提交到 `PENDING`：FE3b；身份确认：FE3c | 从 Preview 顶栏提交到 `PENDING`；`DIFFERENT_PROJECT` 输入 D 的身份确认需要归档过的 scope（§4.6），在 FE3c |
| R5 | 幂等重试 | FE3b | 提交或审核之一：用 `route.fetch()` 把请求送到 backend 后对浏览器 `abort`，前端用同一 key 重试，界面显示成功。回放状态码按 route：提交 202，审核 200。上传是含 Blob 的 multipart，不用于本项 |
| R6 | 审核 | FE3b | 审核人在审核模式（History bundle）退回（`REJECT`，必填理由）→ 提交人工作区两个指针清空 → 重新上传同一输入 → Preview → 提交 → 审核人通过；另回归审核顶栏的撤回（W7） |
| R7 | 上传模式撤回 | FE3b | §6.3 中标为真实 e2e 的场景 |
| R8 | 归档主线 | FE3c | 按 §4.6 J1：候选 → 首次预检 → 业务核验各项的原始诊断与处理状态分开显示 → 逐项接受、撤销、再接受（理由必填）→ 两侧独立项分别处理，撤销其一后服务器拒绝开始归档 → 待审核阻塞（显示待审核提交，草稿不阻塞）→ 身份例外接受 → 开始归档 → head 前移，树显示归档基线。每次预检的异常集合按 §4.6 的表核对。过期 `APPROVE` 的 409 在单个 scope 的正常操作中走不到（§16.7），只由模拟接口覆盖 |
| R9 | 历史比较 | 两节点：FE3b；三节点：FE3c | 两节点用 `INITIAL` 与一个提交；结果抽屉计数（FE2 kickoff §6.4 D1）；打开 History 差异浏览。三节点需要归档基线，在 FE3c |
| R10 | 权限拒绝 | FE3b | 真实 backend 上覆盖四项，都显示“当前身份没有该操作的权限”与错误码：① 无权限身份上传 403；② 无 Preview 权限的提交人发起 Preview 403；③ 无权限身份打开审核模式时 review 查询 403（发生在页面加载时，不在按钮上）；④ 无权限身份进入归档主线时候选查询 403（入口在组态树的提交节点上，只对已通过、无处置的提交可用：该 scope 的上传序列中先安排一个提交经审核通过，handoff 写明）。提交 403 在真实 backend 上产生不了，只由模拟接口覆盖，handoff 说明 |
| R11 | 版本冲突 | FE3b | 审核版本冲突：另一身份先行动作后，界面提示并刷新，不自动重发；工作区版本冲突一例 |
| R12 | 有理由关闭 | FE3c | 按 §4.6 J2：在归档主线中关闭一个已通过的候选（理由必填）→ 中断一次后重试得到 200 回放，界面显示服务器返回的首次关闭人、时间与理由 → 自动重新预检，来源项变为未解释、受影响集合变化的项回到未处理 → 提交人工作区释放、baseline 不动，树与审核显示“已通过”＋“已关闭（未归档）” → 提交人重新上传、预览、提交 → 通过 → 归档。D1–D3 在此得到真实覆盖。关闭请求的 `expected_review_version` 取自同一次候选读取中目标候选的 `review_version`（§16.6），关闭人只有 `archive_submission` |

- Preview、提交等操作在小输入上很快完成，“仍在运行”、刷新后继续轮询与 `MANUAL_RECOVERY_REQUIRED` 继续由模拟接口覆盖，真实 e2e 不强求。
- 浏览器控制台出现未捕获错误即判失败。
- 失败时保存 trace、截图与该次的 Compose 日志；成功时为 R2、R6、R7、R9 的关键页面各存一张参考截图（不作验收，FE4 用 t1 数据重拍）。FE3c 补 R8（业务核验面板、待审核阻塞）与 R12（关闭对话框、关闭后的树与审核顶栏）。
- R4 的身份确认与 R9 的三节点在 J1 中完成（第 12、14 步），R1 的归档后组态树在 J1、J2 中断言。

### 4.8 清理

1. 停止并删除本次的工具链容器（§4.5）。
2. `docker compose ... logs --no-color --timestamps` 写入日志目录。
3. 执行 `down -v --remove-orphans --rmi local`。backend/worker 没有 `image:` 键，`--rmi local` 只删除本项目的 `<项目名>-backend`、`<项目名>-worker`；RS 有自定义 `image:`，不会被删。
4. 按 `com.docker.compose.project=<项目名>` label 删除残留的卷与网络（同 `compose_gate_harness._teardown_compose_project_resources`）；删除本次 RS tag 与 secret 目录。
5. 核对：没有该项目的容器（含工具链容器）、卷与网络；8000 端口空闲；`/proc` 中没有 dolt 进程。之后才按 §4.2 释放。

不删除共享镜像（依赖镜像、工具链、`gateway-repository-service:local`、client e2e 镜像），不运行 `docker rmi` 或 prune 清理他人资源。
节点上后端 Compose 门禁遗留的 `*-backend:latest`、`*-worker:latest` 镜像不属于前端，不要清理。

### 4.9 日志

日志写在 worktree 外的 `--log-dir`，运行结束后写 SHA256 旁注文件。字段：

- 开头与结尾：hostname、UTC 时间、`git rev-parse HEAD`、`HEAD:frontend` 与 `HEAD:vnext` 树、worktree 是否 clean；结尾记录 exit code；
- 占用标记的获取、释放时间与内容，flock 的获取、释放时间；残留检查结果；
- 工具链镜像身份、npm 缓存归档 SHA256 与来源提交；§4.3 的镜像身份；Compose 项目名、网络 ID 与工具链容器名；
- 运行时 `/openapi.json` 的 SHA256 与比对结果；
- 身份名与权限（不含 token）；播种的仓库 ID 与 `INITIAL` 提交 ID；
- 每个用例的名称、起止时间与结果；每次 bundle 下载的 `Content-Length`、实收字节、`ETag`；
- 清理核对结果；
- t1 套件另记：输入目录的文件数、字节数与逐文件 SHA256 的聚合值；§8.4 的 M1 指标；各步骤耗时（只报告）。

以下文件只留在节点上，不写进仓库与 handoff 正文，handoff 只记路径与 SHA256：

- Playwright trace：网络记录中含本次的临时 token（栈清理后失效），也可能含输入数据；
- Compose 日志；
- t1 套件的参考截图：含真实业务值。

## 5. OpenAPI 与 bundle 契约

### 5.1 快照刷新（FE3b）

- 在已合入 `748de5034d`（含 `p6-be-a-d-exit`）的 `fe-vnext` 上，用 §4 的脚本起栈，取运行中的 `/openapi.json`，规范化后写入 `frontend/openapi.json`。
- **规范化（两处都用）：** 在宿主机用 `python3 -I` 执行 `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`。
  不用 Node：快照中有 `9007199254740991.0`、`0.0` 这样的浮点写法，`JSON.stringify` 会写成整数，逐字节比较必然失败。
  脚本先核对当前快照按该规则重排后逐字节不变，否则停下，说明规则不对。
- **与后端原件比对：** 运行时取得的 JSON 与生产 OpenAPI 原件（SHA256 `977b2258…b8a7`，路径见文首“依据”）按同一规则规范化后应逐字节相同（两者来自同一 `vnext/` 树）。不同即停止，交设计会话（§10）。FE3c 的比对原件按 §5.2 末段。
- 用 `npm run generate:api-types` 重新生成 `src/features/api/generated/openapi.d.ts`；快照与生成类型在同一个提交中更新，提交说明写明来源 main 提交与 vnext 树。
- 刷新快照的运行在 05 调试；最终以 04 证据中的运行时比对为准（§5.2）。

### 5.2 与运行中 `/openapi.json` 的比对

- 每次真实 e2e 运行在浏览器用例之前比对。运行时的 `/openapi.json` 在工具链容器内经 preview 服务器的代理读取，顺带证明代理可用；
  两侧都按 §5.1 规范化后逐字节比较。
- 不一致时脚本以非 0 退出，不运行浏览器用例，日志目录保存两份规范化 JSON 与 diff。处理：
  - 差异来自已合入 main、前端尚未刷新的后端改动：按 §5.1 刷新，从头运行；
  - 差异与 §2.3 不符，或出现前端没有预期的 schema 变化：停下交设计会话（§10）。

**FE3c 的比对原件（修订 3）：**

- FE3c 合入 `fd9e383d76`（`vnext/` 树 `6368c9c40c`）后，按 §5.1 刷新快照与类型；§5.1 的“与后端原件比对”与本节的运行时比对，都用后端为 `vnext/` 树 `6368c9c40c` 补交的生产 OpenAPI 原件。
  Q18 交接没有交付新的原件（交接 §5：单次读取 `/openapi.json` 失败，未生成文件），由后端另行补交。
- **已交付（2026-11-09）：** `/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`，SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`，79,082 字节，未规范化，权限 0444。
  - 取件：节点 `ct107-gw-dms-06`（hostname `gw-dms-06`），clean detached worktree `/home/dev/gdds-test-tmp/p6-openapi-6368c9c40c/wt`，起止 HEAD `fd9e383d76642037e4b3246c847222ea9483e033`，`HEAD:vnext` `6368c9c40c`；2026-11-09 06:30:14–06:32:22 UTC，单次 GET 返回 200，无重试，exit 0；起止 worktree clean，资源已清理，占用已释放；
  - 方法与 BE-a/BE-d 相同（生产 Compose helper、`httpx.Client.get("/openapi.json")`、`response.content` 直接写入），指定依赖镜像 `lock-578e079b762e`、本机构建、build network none，未用代理或公网。范围差别：省略取件前的上传业务旅程，在生产栈 ready 后读取（schema 只由路由与 DTO 决定）；
  - 运行日志 `/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/node/run.log`，SHA256 `65052f8d6403eee52797cf473685bc9e403859b5a4b5621236ac0bc7ee35ff9e`；后端的规范化 diff 与交接记录在同目录的 `openapi.normalized.diff`、`handoff.txt`。
- **设计会话核对（2026-11-09，开发主机只读）：** 原件与日志的 SHA256、长度、权限与上文一致；按 §5.1 规则规范化后（SHA256 `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a`），与 FE3b 原件（`977b2258…b8a7`）只差两处：`ArchiveCandidateResponse.properties` 新增整数 `review_version`（0–9007199254740991），`required` 新增 `review_version`。`fe-fe3b-exit` 的 `frontend/openapi.json` 已是规范化形式，与 FE3b 原件规范化后逐字节相同。因此 FE3c 刷新快照后的差异应恰好是这两处，与 §2.3 第 19 行一致。
- 发出提示词前，审核会话在 §13.5 填写原件路径与 SHA256 并重算核对；不以前端自己起栈取得的 `/openapi.json` 代替原件。
- 预期差异：相对 FE3b 快照，只有上述两处。出现其他差异时按上文停下交设计会话。

### 5.3 刷新后的同步（FE3b）

按 FE2 kickoff §7.5 的规则同步，规则本身不变（模拟响应按 OpenAPI 类型、错误码取自 route 描述、字符串取值表与后端枚举对照、只模拟后端可达的状态）。

- **删除退回修改（前端 kickoff FD4；AGENTS：删除被替代的实现）：**
  - `client.ts::safeReviewStatus/safeReviewEvent` 中 `RETURNED_FOR_REVISION` → `REJECTED` 的映射（`client.ts:93`、`:98`）；生成类型中的对应取值随快照刷新消失（`client.test.ts` 中没有对应用例）；
  - `view-model/workspace.ts` 中 `RETURNED_FOR_REVISION` 的状态文字与色调（`:39`、`:52`）；`ComparisonPage.tsx` 状态表中的 `RETURNED_FOR_REVISION: "需修改"`（`:38`）；
  - 模拟数据与用例中的同类取值；FE2 kickoff §4.1 末段的映射说明随之作废；
  - `review_status`、事件动作的取值以新生成类型为准。
- **`REJECTED` 的界面用词统一为“退回”：** 前端 kickoff FD4 定义“退回 = `REJECT`”，审核按钮、对话框、组态树与 §6.1 都用“退回/已退回”。
  `ComparisonPage.tsx` 状态表中的 `REJECTED: "已拒绝"` 改为“已退回”，模拟接口 e2e 中断言“审核：已拒绝”的用例（`e2e/workspace-shell.spec.ts:1248`）同步改为“审核：已退回”；全前端不再出现“拒绝”作为该状态的显示。
- **201/202：** `POST /v1/workspaces` 新建 201、已存在 200；`POST /v1/history-compares` 第一次 202、回放 200。
  模拟响应改用各状态码自己的生成类型，删除 FE2 kickoff §7.5“幂等回放”中“响应体用 200 的类型约束”的变通。
- **指针字段：** 全部 `WorkspaceResponse` 模拟数据补 `active_submit_attempt_id`、`active_submission_id`（必需键，值可 null；缺键不能当作 null），两者至多一个非空，与场景的生命周期一致
  （BE-a 交接“对外接线”的生命周期；场景注明依据），包括“operation 已到终态、attempt 未结束、指针保留”的场景（§6.2）。
- **终局处置（`archive_disposition` → `submission_disposition`）：** 直接改为新字段，不双读旧字段。模拟数据只构造后端可达的组合，并在模拟数据单测中断言：
  - 处置只出现在 `review_status = APPROVED` 的 `SUBMISSION` 节点上；
  - `ARCHIVED_BASELINE` ⇒ `disposition_source_kind = ARCHIVE`、`disposition_result_id` 非空、`closure` 为空，且 History 中有对应的 `ARCHIVED_SUBMISSION` 基线节点（`promoted_baseline_node_id`）；
  - `CLOSED_NOT_ARCHIVED` + `ARCHIVE` ⇒ `disposition_result_id` 非空、`closure` 为空（归档时关闭的同级提交）；
  - `CLOSED_NOT_ARCHIVED` + `MANUAL_CLOSE` ⇒ `disposition_result_id` 为空、`closure` 非空；
  - 没有 `ARCHIVED_BASELINE` + `MANUAL_CLOSE`；
  - `eligibility_note` 只出现在 `APPROVED` 且父基线不是 head 的节点上，与处置无关（`projection.py:210-218`）。现有模拟数据中 `PENDING` 节点带该标记（`mock-data.ts:458`）不是后端可达的状态，改正；
  - **防御性例外：** `APPROVED` + 标记 + 无处置（§6.4 D5）按 DC89 不可达（基线前移时已通过的同级提交都已归档或关闭），只为验证界面的防御性显示而保留，不受“只构造可达组合”约束。
    这类数据单独放在 D5 用例使用的数据中，并注明“DC89 不可达，防御性”；模拟数据单测把它列为唯一允许的例外。
    现有 `mock-data.ts:120`（FE2a 历史中的 `APPROVED` + 标记 + 身份例外，无处置）正是这种形态，改为可达形态（加“归档时关闭”的处置，即 D4 形态），或改标为 D5 的防御性数据，二者择一并在 handoff 写明；
  - 同一提交的 Review `submission_disposition` 对象与 History 节点一致；
  - 已处置的提交不是任何工作区的 `active_submission_id`（归档与关闭都会释放工作区）；“工作区读取过时”的竞争场景单独注明。
- **归档相关的新 schema（FE3b 只保证类型与形状）：**
  - `ArchiveCandidatesResponse`、`PreviewArchivePlanResponse` 补 `pending_submission_ids`、`pending_submission_count`（与模拟 History 中当前基线下的 `PENDING` 提交一致）与 `business_validation`；
  - 两者 `blockers` 的取值表（`mock-data.ts:46-52`）加 `ARCHIVE_PENDING_REVIEW`，来源改为 `application/archive/queries.py`（候选 `:147`、预检 `:172` 在有待审核提交时追加）；
  - `ArchivePreviewAnomalyResponse` 补新增的必需字段，`details` 按闭合 union 中与 `issue_code` 对应的类型构造；
  - 归档业务核验的场景化模拟数据（各类异常、两侧独立项、关闭响应）在 FE3c 构造（§16）。
- **归档对话框的 action 映射（最小修正）：** `ArchiveMainlineDialog.tsx::anomalyAction`（`:35-36`）目前只区分身份例外与同级排除，其他 `subject_kind` 都会被发成 `ACKNOWLEDGE_EXCLUSION`。
  FE3b 改为按 §2.3 第 15 行的表对 5 个 `subject_kind` 穷举映射（新增未知取值时类型检查失败），不改界面；业务核验的显示、撤销与理由规则在 FE3c（§16）。同时改：
  - `api/journeys.ts:374` `ArchiveJourneyInput.anomalyResolutions[].action` 的类型：现只有三值，改为生成类型中的 `AppendArchiveAnomalyResolutionRequest["action"]`（5 个 `ACKNOWLEDGE_*` 与 `REVOKE`），不手写取值；
  - `dev/mock-data.ts` 取值表（`:58-68`）按后端枚举补全：`ArchiveAuditEventResponse.subject_kind` 为 `ArchiveSubjectKind` 的 6 值（含 `CONFIGURATION_SOURCE`、`CONFIGURATION_TIME_QUALITY`、`CONFIGURATION_TIME_ORDER`）；
    `action` 为 `CONFIRM`、`REVOKE` 与 5 个 `ACKNOWLEDGE_*`；`issue_code` 加 7 个业务编码（`INITIAL_SOURCE_UNEXPLAINED`、`GENERATION_TIME_MISSING`、`GENERATION_TIME_INVALID_VALUES`、`GENERATION_TIME_LAST_NOT_MAX`、`TIME_ABNORMAL_MODIFIED`、`TIME_ABNORMAL_INITIAL`、`BASELINE_TIME_UNAVAILABLE`），来源写 `domain/archive/models.py` 与 `application/archive/business_validation.py`。
- **新权限与错误：** 错误码单测解析新快照，覆盖 §2.3 中新增或变化的状态码与 code（review 查询的 403/404、review-events 的 `BASELINE_VERSION_CONFLICT`、`ARCHIVE_CLOSED`、bundle 的 `BUNDLE_INTEGRITY_FAILURE`、`ARTIFACT_UNAVAILABLE` 等）。
  FE3b 为 §6.1 的撤回失败与 bundle 错误给出文案；审核顶栏的新码先走通用文案加错误码（C6）；归档与关闭的专用文案在 FE3c。
- **模拟身份：** 模拟接口新增“本人撤回”等身份时，同步扩充 `check-production-build.mjs` 的模拟 token 禁用模式（目前为 `dev-token-(?:submitter|reviewer|archive-confirmer|no-permission)`）。
- **bundle 错误码：** 两个 bundle 路由在 OpenAPI 中列出的错误码各有前端文案，加入 FE2 kickoff §7.5 的取值核对；没有列出的不模拟。不能据错误响应构造空 bundle。
- **fixture 的 tar（设计决定）：** FE1–FE2 的 bundle fixture 内容由生成器在后端镜像中产生，模拟接口在本地拼装 tar。FE3b **不改生成器、不重新生成 fixture**：
  - 改用后端 encoder 会改变全部已提交的 fixture 字节，超出 FE3b 范围；
  - 前端解析与后端生产 encoder 的互通由 §5.5 的同字节制品与 R2、R3 的真实 tar 证明；
  - 模拟接口拼装的 tar 与后端格式（成员顺序、PAX 只含 `path`/`size`）保持一致，由解析器的同一套校验接受。

**FE3c 的补充（修订 3，Q18；规则沿用 FE2 kickoff §7.5）：**

- **`review_version`：** 全部 `ArchiveCandidatesResponse.candidates[]` 模拟数据补必需键 `review_version`，用生成类型约束（缺键或类型不对编译失败）。现有位置：`dev/mock-data.ts:578`（`TEST_ARCHIVE_CANDIDATES`）、`e2e/workspace-shell.spec.ts:426`（路由桩中现拼的候选列表，同时改为带生成类型）。
  - 取值：非负安全整数。按“后端可达状态”，同一场景中同一提交的候选 `review_version` 等于该提交 Review GET 模拟响应的 `review_version`（两者都来自审核投影版本，`application/archive/snapshot.py:122`、`manual_close.py:99`）；
  - 为使 V9 的断言有区分力，场景中候选的 `review_version` 不取 0 或 1，各候选互不相同，也不等于工作区或基线的版本号；
  - 409 `REVIEW_VERSION_CONFLICT`（关闭路由）按“读取候选之后审核版本被其他操作改变”的竞争构造，场景注明依据 `manual_close.py:99-100`；错误码仍只取关闭路由 409 描述中列出的值（§7.5 错误码单测）。
- **`selected` 只含两个字段：** 预检、确认、异常处置、开始归档四个请求体中的 `selected`（`ArchiveSelectedRefRequest`）在后端是 `extra="forbid"`。
  - 模拟路由桩按 §7.5“请求侧约束”补一条：`selected` 有 `submission_id`、`expected_candidate_digest` 以外的键时返回 422 `REQUEST_VALIDATION_FAILED`，与后端相同；在同一处实现，由请求侧单测覆盖；
  - 生成类型拦不住这类错误：把类型为 `ArchiveCandidateResponse` 的变量赋给 `selected` 时，TypeScript 不做多余属性检查。因此靠显式取字段（§16.4）与 §16.9 V14 的断言保证。
- 关闭路由 `POST /v1/submissions/{submission_id}/closure` 必须带 `Idempotency-Key`（§16.6），按 §7.5 加入“必须带 `Idempotency-Key` 的路由”的核对。

### 5.4 生成类型的一致性（FE3a 已完成）

由 `frontend/openapi.json` 重新生成类型到临时目录，与已提交的 `openapi.d.ts` 逐字节相同，否则失败。FE3b 刷新快照后照常生效。

### 5.5 bundle tar 的接收修复与同字节互通（FE3b）

依据：BE-d 前端交接 §1–§3（含 §2.1）、DC89、FE3b 评估交接 §5。成员结构不变（§2.1）：`manifest.json`、`artifact-closure.json` 在前，之后与 closure 条目逐个对应、顺序相同；路径安全、重复成员、closure 顺序、逐成员 size 与摘要、总长度的校验都保留。

**PAX 记录按字节解析：**

- 在 `Uint8Array` 中读取 ASCII 十进制长度与其后的空格；长度是整条记录的字节数，包括长度前缀自身的位数、空格、`key=value` 与结尾换行（前缀位数进入固定点，例如 `12 path=中\n` 为 12 字节）；
- 记录必须以 `\n` 结束且不越过 payload 末尾；相邻记录按字节边界依次切分；
- 切出记录后，用严格模式（遇到非法序列即失败）把 key 与 value 解码为 UTF-8；
- **分两层校验（修订 2 审核 B2）：**
  - **记录切分层**：只做上面的按字节切分与严格解码，不判断 key 是否允许，输出 `(key, value)` 序列；
  - **成员层**：一个局部 PAX payload 作为下一个成员的扩展头时，只接受 `path` 与 `size` 两个 key（后端 `artifacts/tar_stream.py` 只生成这两种）；重复的 key、其他 key、空 value 都拒绝，安装中止。
    后端格式将来变化时，按 BE-d 交接 §2.1 末段重新核对，不预先放宽；
- 删除现有 `parsePaxPath` 中先整体解码再按 `text.length`/`slice` 推进的实现。

**标准 PAX `size`：**

- `size` 为十进制非负整数，只含 ASCII 数字，不超过 `Number.MAX_SAFE_INTEGER`（2^53 − 1）；
- 有 PAX `size` 时以它作为下一个成员的大小，覆盖 header `[124:136]` 中的八进制 size（后端此时 header size 为 0）；
- 生效后的 size 必须等于对应 closure 条目的 `size_bytes`，且不超过按 `Content-Length` 算出的剩余字节，否则在写入 OPFS 之前拒绝。

**接收预算（先检查、再分配）：**

| 对象 | 上界 | 计数口径 |
| --- | --- | --- |
| 单个局部 PAX payload | `MAX_PAX_PAYLOAD_BYTES = 16,777,216` | header 声明的 payload 大小，不含 512 字节 header 与 padding；超出即在读取与分配前拒绝 |
| 单个路径 | `MAX_PATH_UTF8_BYTES = 8,388,608` | 路径的 UTF-8 字节数，不按 JS `length`；ustar `name`/`prefix` 拼出的路径同样检查 |
| `manifest.json`、`artifact-closure.json` | 各 16,777,216（现有 `METADATA_LIMIT`） | 不变，不改成路径预算 |
| 普通成员 | 不设前端固定上限 | 按 closure 与剩余字节核对后流式写入 OPFS，不整块读入内存（沿用现有实现） |

- 删除 `PAX_LIMIT = 1 MiB`。不截短、不 ASCII 化路径。8 MiB 是保守接收上界，不是后端保证可达的最大值（BE-d 交接 §2.1）。

**失败处理：** 截断、流错误、size/路径/顺序/摘要不符或超出预算时，中止本次 OPFS 安装：不提交半包、删除本次的临时内容；界面显示 bundle 下载失败（FE2 已有文案加错误码），不显示为“无差异”，不回退到只解析 manifest JSON。
已安装成功的同一 bundle 不受影响。HTTP 200 或 operation `SUCCEEDED` 都不等于本地安装成功。

**同字节互通（设计决定：原样提交为前端 fixture）：**

- **来源：** 开发主机 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/` 下的 9 个原件（BE-d 交接 §3；后端候选 `0ba45e5ef8` 的生产 encoder 生成）：
  `bundle.tar`、`manifest.json`、`artifact-closure.json`、`index.json`、`pax-records.json`、`size-vectors.json`，以及 3 个 header-only 文件 `size-8589934591-header-only.bin`、`size-8589934592-header-only.bin`、`size-9007199254740991-header-only.bin`。
- **提交：** 原样复制到 `frontend/src/test/fixtures/backend-interop/be-d-0ba45e5ef8/`，不改字节、不改名，另加一份 `SHA256SUMS`（`sha256sum` 格式，覆盖 9 个原件），目录中共 9 个原件加 `SHA256SUMS`。合计约 45 KB。
  理由：后端要求“用同一个 `bundle.tar`”，提交后审核与 04 取证都能在 clean worktree 中复现；小文件不影响仓库体积；测试先断言 SHA256，复制出错会立即失败。
- **单测（`run-tests.sh` 的单测阶段）：**
  - 先断言 `bundle.tar` 长度 24,576、SHA256 `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`（常量写在测试中），其余文件的长度与 SHA256 与 `index.json` 一致；
  - 用解析器读 `bundle.tar`（内存 sink）：成员恰好 6 个；`manifest.json`、`artifact-closure.json` 与同目录的两个文件逐字节相同；4 个普通成员的路径、size 与 `raw_sha256` 与 `index.json` 的 `ordinary_artifacts` 一致（含 ASCII 长路径、中文与非 BMP 路径）；bundle 摘要等于 `index.json` 的 `bundle_digest`；
  - `pax-records.json`（按两层分别断言）：
    - `literal_utf8`、`prefix_99`、`prefix_101`：切分层得到一条 `path` 记录（`中`、`a` × 90、`a` × 91），成员层接受；
    - `adjacent_records`：切分层切出两条记录，`path=中` 与 `comment=😀`；作为成员的 PAX payload 时因 `comment` 被成员层拒绝；
    - 3 个非法向量（错误字节长度、缺换行、截断的 UTF-8）在切分层拒绝；
  - `size-vectors.json`：3 个 header-only 文件只解析 header 与 PAX，得到的 size 分别为 8,589,934,591、8,589,934,592、9,007,199,254,740,991；随后因数据不完整被拒绝。它们不是完整 tar，不当作可安装包；
  - 预算边界：在内存中构造的小向量覆盖 1 MiB 以上的合法路径（例如 1.5 MiB）被接受、8,388,609 字节的路径被拒绝、header 声明 16,777,217 字节的 PAX payload 在读取前被拒绝（只构造 header）、非安全整数的 `size` 被拒绝。不写入磁盘，不提交大文件，不生成 >8 GiB 的数据。
- **模拟接口 e2e（`run-tests.sh --e2e`）：**
  - 模拟 bundle 路由以 `bundle.tar` 的原字节响应（`Content-Length: 24576`，`ETag` 为 `index.json` 的 `bundle_digest`），浏览器走真实的下载与 OPFS 安装；
  - 断言安装成功：经 `page.evaluate` 读取 OPFS 中已提交的 bundle，6 个文件的大小与浏览器内计算的 SHA256 与 `index.json` 一致；
  - 负例：同一字节截去末尾 512 字节、改动一个 parquet 成员的一个字节，各一次：安装中止，OPFS 中没有该摘要的已提交内容，界面显示下载失败；
  - 该 bundle 没有 records（`verified_logical_record_count = 0`），只证明 tar 与 OPFS 互通，不要求差异浏览能渲染它；records 的消费由 R2、R3 的真实 tar 证明。
- **证据：** 单测与模拟 e2e 在 07 调试，04 全量 runner 取证即“专用节点证据”。handoff 记录 fixture 目录与 `SHA256SUMS` 的 SHA256、用例名、运行节点与日志 SHA256；
  FE3b 证据核对通过后，由 owner 把修复提交、同文件 SHA256 与 04 证据回传后端（BE-d 交接 §3）。

## 6. 上传模式撤回、占用与终局处置显示

### 6.1 状态与文案（FE3b）

数据来源与请求规则见前端 kickoff §7.1：指针非空时调用 `GET /v1/submissions/{id}/review`，撤回携带 `review_version`。
前端不按 actor 推断权限，也不把指针非空当作可撤回：GET review 成功，说明调用方持有两个审核权限之一，再加上 `PENDING`，才可撤回（BE-a 交接的权限表）。

撤回按钮在上传模式顶栏始终显示（草图 `header-upload`），不可用时禁用并给出原因（F4，§11 Q7）。危险按钮样式、二次确认（X4）、幂等 key 与审核顶栏的撤回相同。
已有的审核顶栏文案（`ReviewActions.tsx` 的 `STATUS_REASON`）沿用，新增的按下表：

| 条件（按顺序判断） | 按钮 | 禁用原因 / 提示 |
| --- | --- | --- |
| `active_submit_attempt_id` 非空，提交操作为 `QUEUED` 或 `RUNNING` | 禁用 | 提交正在执行，完成后才能撤回 |
| `active_submit_attempt_id` 非空，提交操作为 `MANUAL_RECOVERY_REQUIRED`，或已到终态但 attempt 未结束（§6.2） | 禁用 | 提交结果待确认，需要管理员处理 |
| `active_submit_attempt_id` 非空，attempt 或提交操作读不到；或工作区本身读不到（§6.2 续做规则） | 禁用 | 无法确认提交状态（另附“重试”） |
| 两个指针都为空 | 禁用 | 当前没有待审核的提交 |
| 正在查询审核状态 | 禁用 | 正在读取审核状态 |
| 查询返回 403 | 禁用 | 当前身份没有撤回权限 |
| 查询返回 404 | 禁用 | 未找到该提交，请刷新后重试（另附“刷新”） |
| 查询失败（临时错误超过重试上限、5xx） | 禁用 | 无法读取审核状态（另附“重试”） |
| `submission_disposition` 非空 | 禁用 | 处置后指针会清空（归档、关闭都释放工作区），只有工作区读取过时才会出现。先重新读取一次工作区，再按新状态显示；仍是该状态时，显示“该提交已归档”或“该提交已关闭（未归档）”。本行优先于下面按审核状态判断的各行，也优先于 `NOT_CANDIDATE_BASE_ADVANCED` |
| `status = PENDING` | 可用 | — |
| `status = APPROVED` | 禁用 | 该提交已通过审核，不能撤回 |
| `status = REJECTED` 或 `WITHDRAWN` | — | 撤回或退回后指针会清空，只有工作区读取过时才会出现。先重新读取一次工作区，再按新状态显示；仍是该状态时，显示“该提交已退回”或“该提交已撤回” |

- `NOT_CANDIDATE_BASE_ADVANCED` 不参与判断（§2.3 第 13 行）：DC89 之后，过期的 `APPROVE` 被拒绝，归档会关闭其余已通过的同级提交，“已通过、基线已前移、仍占用工作区”不再可达。2026-11-05 版本中两张表里的暂定行删除。
- 403、404 与查询失败都按 C6 在悬停提示中附错误码，可复制。
- **撤回对话框：** 标题“撤回提交”，影响说明与确认勾选沿用审核顶栏的撤回对话框。
- **撤回失败（对话框底部提示区，FE2c R6）：**
  - 409 `REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT`、`ARCHIVE_CLOSED`：提示“审核状态已变化，已重新读取”。
    同时重新查询工作区与 review，按新状态更新按钮，不自动重发；
  - 403：“当前身份没有撤回权限”；404：“未找到该提交，请刷新后重试”；
  - 其他错误（包括 `IDEMPOTENCY_CONFLICT`）：通用文案“撤回未完成”加错误码（C6）。
- **撤回成功：** 重新读取工作区。指针、当前上传与 Preview 都为空时，离开 Preview 页回到工作台的上传步骤卡，提示“已撤回，可以重新上传”。
- 文案按 FE2 kickoff §4 的原则：只说原因，原始码放悬停提示与 Debug。

**工作区被占用时的“提交”与“上传”：**

- **Preview 顶栏的“提交”：** 任一指针非空时禁用，原因按下表。指针非空时后端会返回 409 `SUBMIT_OCCUPANCY_CONFLICT`。
- **工作台的“上传”（工具栏与上传步骤卡，§11 Q9）：** 任一指针非空时同样禁用。后端不拦截这时的上传，但上传后：
  - 待审核时，撤回、通过、退回都会因为占用绑定不符返回 409 `WORKSPACE_OCCUPANCY_CONFLICT`（`assert_review_workspace_bindings`）；
  - 已通过时，开始归档或关闭会清空该工作区的当前上传与 Preview，刚上传的内容会丢失。

  这是界面决定，不需要后端新增字段。

| 工作区状态 | “提交”与“上传”的禁用原因 |
| --- | --- |
| `active_submit_attempt_id` 非空，提交操作为 `QUEUED` 或 `RUNNING` | 提交正在执行，完成后才能继续 |
| `active_submit_attempt_id` 非空，提交操作为 `MANUAL_RECOVERY_REQUIRED`，或已到终态但 attempt 未结束 | 提交结果待确认，需要管理员处理 |
| `active_submit_attempt_id` 非空，attempt 或提交操作读不到；或工作区本身读不到 | 无法确认提交状态（另附“重试”） |
| `active_submission_id` 非空，`PENDING` | 已有待审核的提交，撤回后才能重新上传 |
| `active_submission_id` 非空，`APPROVED` | 该提交已通过审核，归档或关闭后才能重新上传 |
| `active_submission_id` 非空，`submission_disposition` 非空（工作区读取过时） | 先重新读取一次工作区；指针已清空时恢复可用 |
| `active_submission_id` 非空，审核状态读不到（403、查询失败） | 已有提交在处理中，完成后才能重新上传 |

### 6.2 刷新恢复与 `active_submit_attempt_id`（FE3b）

- URL 中的 `operation_id`（FE2 kickoff N2）保持不变，仍是操作卡片与轮询的依据。
- **URL 中操作的类型：** 删除 `sessionStorage` 标记后，以 `GET /v1/operations/{id}` 返回的 `job_kind` 为准
  （`backend-vnext/submit` 或 `backend-vnext/preview`，FE2 kickoff §7.5 取值表）。上传与提交写入 URL 时都用 `operationKind=operation`，不靠参数区分。
- **页面加载或刷新时：** 读取工作区。
  - `active_submit_attempt_id` 非空，URL 中没有该 attempt 的提交操作时，经 `GET .../submit-attempts/{id}` 取 `operation_id`，写入 URL，显示操作卡片并继续轮询；
  - URL 中的操作是提交（按 `job_kind`），但与指针所指 attempt 的 `operation_id` 不同时，以服务器（指针）为准，替换 URL 中的值；
  - 续做卡片显示在刷新时所在的页面：Preview 页在顶栏之上（`ComparisonPage` 的 `comparison-resume` 排在 `compare-header` 之前），工作台在组态树标题下方（`WorkbenchPage` 的 `OperationStatusPanel`）。
- **提交操作到达终态后：** 重新读取工作区与 attempt（`GET .../submit-attempts/{id}`）：
  - attempt 为 `FINALIZED`：指针转为 `active_submission_id`，按 FE2c 已有的提交结果处理；
  - attempt 为 `ABORTED`：两个指针都为空，显示“提交未完成”与原始码（FE2 kickoff §7.5），“提交”按 §6.1 的表恢复可用；
  - operation 已到终态，但 attempt 仍为 `PREPARED` 或 `EFFECT_PENDING`、指针仍非空：显示 FE2c 已有的“需要管理员处理”提示（含操作 ID），不自动重试。
    指针在执行、等待恢复或结果未知时保留，不能按 operation 的终态推断已释放（BE-a 交接；FE3b 评估交接 §3）。
- **续做得到 `ABORTED` 或读取失败之后（§11 Q14，核对报告 §8.1 第 3 项）：**
  1. 先重新读取工作区（沿用已有的临时错误重试）。
  2. 工作区读取成功：
     - 两个指针都为空：“提交”与“上传”可用；保留原提示（“提交未完成，请检查上传与 Preview 后重试”或“无法读取提交结果，请刷新后重试”）；
     - `active_submission_id` 非空：按 §6.1 的表（提交实际已完成）；
     - `active_submit_attempt_id` 非空：读取 attempt 与其操作，读得到时按 §6.1 的表；读不到时禁用，原因“无法确认提交状态”，附“重试”。
  3. 工作区也读不到：保持禁用，原因“无法确认提交状态”，附“重试”。“重试”从第 1 步重新开始，不自动循环。
  - 这样提示与禁用原因始终一致（满足 FE3a 审核 B7：不在失败后仍写“确认中”），也不在指针未清时解锁（满足后端“查询失败、operation 终态都不等于占用已释放”）。
- **FE2c 的 `sessionStorage` 提交标记（§11 Q6）：** `gateway-submit-operation` 只能在同一标签页内找回提交，指针可以跨标签页与设备。
  FE3b 删除该标记，由指针与 `job_kind` 取代（AGENTS：删除被替代的实现）。全部位置：
  - 写：`SubmitDialog.tsx:173`、`:184`；
  - 读与清除：`ComparisonPage.tsx:188`、`:199`、`:208`、`:476`；`WorkbenchPage.tsx:106`、`:145`、`:150`、`:455`；
  - 模拟接口 e2e：`e2e/workspace-shell.spec.ts:1584`、`:1610` 预置该标记的两个用例（n3），改为预置工作区指针与 attempt，覆盖不减。
  上传的 `gateway-preview-operation` 标记不受影响。

### 6.3 必测场景（FE3b）

本人撤回用“提交人（本人撤回）”身份，无权限用“提交人（仅上传）”身份。“真实”一列标明是否进入真实 backend e2e（R7）；其余只在模拟接口覆盖，handoff 说明原因。

| # | 场景 | 真实 | 断言 |
| --- | --- | --- | --- |
| W1 | 本人撤回 | 是 | `PENDING` 时按钮可用；确认后撤回成功，回到上传步骤卡 |
| W2 | 撤回后重新上传 | 是 | 工作区两个指针、`current_upload_revision_id`、`current_preview_result_id` 都为空；重新上传、Preview、提交成功，指针指向新提交 |
| W3 | 无权限 | 是 | 仅上传身份提交后，review 查询 403，按钮禁用且原因为“当前身份没有撤回权限” |
| W4 | 已通过 | 是 | 审核人通过后，提交人刷新：`active_submission_id` 仍非空，撤回禁用且原因为“该提交已通过审核，不能撤回”；“上传”禁用且原因为“该提交已通过审核，归档或关闭后才能重新上传” |
| W5 | 冲突刷新 | 是 | 撤回对话框打开后，审核人先撤回或退回（真实 e2e，两个 context 同时在线）或模拟 `REVIEW_VERSION_CONFLICT`（模拟接口）；界面重新读取后按新状态显示，不自动重发 |
| W6 | 提交执行中与结果待确认 | 否（真实 backend 上提交很快完成） | `active_submit_attempt_id` 非空时撤回、“提交”与“上传”都禁用；刷新后按 §6.2 找回操作卡片；operation 终态而 attempt 未结束时显示“需要管理员处理” |
| W7 | 回归 | 是 | 审核人在审核顶栏撤回，行为与 FE2c 相同 |
| W8 | 待审核时不能上传 | 是 | `PENDING` 时工作台“上传”禁用，原因为“已有待审核的提交，撤回后才能重新上传”；撤回后恢复可用 |
| W9 | 续做失败后的占用判定 | 否（需要注入读取失败） | 按 §6.2 续做规则：① `ABORTED` 后指针为空，“提交”恢复可用；② 操作读取失败、工作区重读得到 attempt 指针且 attempt 也读不到：禁用，原因“无法确认提交状态”，点“重试”后恢复读取；③ 工作区读取失败：同 ②。任何分支都不出现“确认中”与失败提示并存 |
| W10 | 工作区读取过时，提交已处置 | 否（需要构造竞争） | `active_submission_id` 指向的提交在 review 中已有 `submission_disposition`：先重读工作区；重读后指针为空则恢复可用；模拟“重读仍过时”时显示“该提交已归档”或“该提交已关闭（未归档）” |

模拟数据按 BE-a 交接的生命周期构造指针，按 FE2 kickoff §7.5 的“后端可达状态”规则核对跨响应关系，场景注明依据。
REJECTED、WITHDRAWN 与 W10 按“读取工作区之后被退回、撤回或处置”的竞争构造。

### 6.4 终局处置的只读显示（FE3b）

依据 V2 交接 §3、FE3b 评估交接 §3–§4.2、§2.3 第 12、13 行。审核状态与终局处置分开显示：处置不是新的审核状态，有理由关闭也不是撤回。FE3b 只做显示，不做关闭入口（FE3c，§16）。

**数据来源：** 组态树与详情面板用 History 节点的 `submission_disposition`、`disposition_source_kind`、`disposition_result_id`、`closure`；审核模式顶栏用 Review 的 `submission_disposition` 对象（含 `closure`）。

| 处置 | 来源 | 组态树状态位 | 详情面板 | 审核模式顶栏 |
| --- | --- | --- | --- | --- |
| 空 | — | 按审核状态：待审核、已通过、已退回、已撤回（FE2 kickoff §4.1） | “审核状态”一行 | 审核状态 |
| `ARCHIVED_BASELINE` | `ARCHIVE` | “已归档”（`info` 色调） | “审核状态：已通过”；“终局处置：已归档，成为归档基线 n”。基线名由 `promoted_baseline_node_id` 在树中找到节点，用 §7 M7 的标签函数取得；找不到时只写“已归档” | 状态“已通过”，旁加处置标签“已归档” |
| `CLOSED_NOT_ARCHIVED` | `ARCHIVE` | “已关闭（未归档）”（`neutral` 色调） | “审核状态：已通过”；“终局处置：已关闭（未归档）”；“原因：归档时选中了其他提交” | 状态“已通过”，旁加“已关闭（未归档）”，下方一行“归档时选中了其他提交” |
| `CLOSED_NOT_ARCHIVED` | `MANUAL_CLOSE` | “已关闭（未归档）”（`neutral` 色调） | “审核状态：已通过”；“终局处置：已关闭（未归档）”；“关闭人：{closed_by}”；“关闭时间：{closed_at}”；“关闭理由：{reason}” | 状态“已通过”，旁加“已关闭（未归档）”，下方一行“由 {closed_by} 于 {closed_at} 关闭”，理由可展开 |

- **组态树：** 状态位只有一个，有处置时显示处置，审核状态放在详情面板（FE2 kickoff §4.1 已规定“有处置时以它为准”，FE2 没有实现）。
  有理由关闭的节点状态位悬停提示“有理由关闭，详情见右侧面板”。
- **关闭理由：** 全文显示，保留换行，不截断；超过 3 行时折叠，提供“展开”。理由是用户输入，按文本显示，不解析标记。
- **关闭人：** 显示 `closed_by` 原值（actor ID；vnext 没有用户目录）。
- **时间：** 与组态树其他时间相同的本地格式（`toLocaleString("zh-CN", …)`），悬停显示 UTC 原值。
- **原始值：** `ARCHIVED_BASELINE` 等枚举、`disposition_result_id` 放悬停提示与 Debug（C6），不出现在正文中。
- **`NOT_CANDIDATE_BASE_ADVANCED`（§2.3 第 13 行）：**
  - 处置非空时不显示“基线已更新”标签，详情面板也不显示原来的“归档原因”；
  - 处置为空时（按 DC89 正常数据不可达，防御性保留）显示说明标签“基线已更新”，悬停与详情只写“该提交所基于的基线已不是当前基线”，删去现有文案中的“不能归档”；
  - 任何情况下都不显示为阻塞或“需要管理员处理”。
- **审核模式的按钮：** 有处置时，通过、退回、撤回的禁用原因写“该提交已归档”或“该提交已关闭（未归档）”，代替“该提交已通过审核”。
- **组态树的“归档主线”动作（修订 2 审核 B3）：** 现有 `workspace.ts:247` 只看 `APPROVED` 且无标记（`archiveReady`），有理由关闭且基线未变的提交（J2 的 C）仍能进入归档主线，已归档的提交则因带标记显示“…不能归档”。改为：
  - 有处置时禁用，原因“该提交已归档”或“该提交已关闭（未归档）”，处置优先于标记；
  - 无处置、只有标记（D5，防御性）时禁用，原因“该提交所基于的基线已不是当前基线”，不写“不能归档”；
  - `PENDING` 等其他情况的原因不变（`workspace.ts:255`）；`workspace.test.ts:62` 的期望随之改。
  - `WorkbenchPage.tsx` 中的旧文案一并按本节改：`:457` 状态标签、`:478`“基线已更新”标签的 `title`（含“不能归档”）、`:534` 详情面板的“归档原因”。
- **上传模式：** 提交被归档或关闭后工作区指针清空，上传模式不需要单独显示；树中可以看到处置（§6.1 W10 处理过时读取）。

**必测（模拟接口，FE3b）：**

| # | 场景 | 断言 |
| --- | --- | --- |
| D1 | 已归档 | 树状态位“已归档”；详情面板写出审核状态与“成为归档基线 n”；审核模式顶栏两个标签与禁用原因；“归档主线”禁用，原因“该提交已归档” |
| D2 | 归档时关闭 | 树状态位“已关闭（未归档）”；详情面板与顶栏写“归档时选中了其他提交”；“归档主线”禁用，原因“该提交已关闭（未归档）” |
| D3 | 有理由关闭 | 关闭人、时间、理由完整显示；多行理由折叠与展开；`result_id` 为空仍显示为已关闭；父基线仍是 head（无标记）时“归档主线”也禁用，原因“该提交已关闭（未归档）” |
| D4 | 处置优先 | `APPROVED` + 处置 + `NOT_CANDIDATE_BASE_ADVANCED`：不显示“基线已更新”；“归档主线”的禁用原因按处置 |
| D5 | 只有标记（防御性，DC89 不可达） | `APPROVED` + `NOT_CANDIDATE_BASE_ADVANCED`、无处置：显示说明标签；“归档主线”禁用，原因“该提交所基于的基线已不是当前基线”；全部文案不含“不能归档” |

- 单测覆盖 `view-model/workspace.ts` 的映射（上表四行、标记的优先级与“归档主线”的启用条件）。
- 真实 backend 要归档或关闭才能产生处置，D1–D3 的真实覆盖在 FE3c（R8、R12）。

## 7. FE2 带入项（FE2 kickoff §6.5）

| ID | 子阶段 | 内容与完成标准 |
| --- | --- | --- |
| M7 | FE3a（已完成） | 提交对话框的摘要不显示原始 ID：History 节点用组态树中的显示名，Preview 结果显示“本次预览”。**基线序号（§11 Q11）：** 组态树与摘要共用同一个标签函数；`ARCHIVED_SUBMISSION` 基线显示为“归档基线 n”，n 按 `created_at` 升序从 1 编号，同时刻时按 `ref_id`；`INITIAL` 为“初始基线”。§6.4 的“成为归档基线 n”使用同一函数 |
| n3 | FE3a 已覆盖；FE3b 改为基于指针 | e2e（模拟接口）覆盖续做时 `ABORTED` 与读取失败的提示，以及续做期间“提交”按钮禁用并显示原因。FE3b 删除 `sessionStorage` 标记后，按 §6.2 续做规则（§11 Q14）改写，覆盖不减，并由 §6.3 W9 覆盖新增的分支 |
| n8 | FE3a（已完成） | “需要管理员处理”一行：ID、“复制 ID”与正文分开排版，使用同一区域其他提示的提示样式 |
| M1 | FE3a 测量（已完成）；FE3c 复测 | 见 §8.4 |

## 8. t1 真实数据旅程（FE3c）

FE3b 不跑 t1。第 2 步按核对报告 §8.3 与 FE3b 评估交接 §6 调整：第 4 步改为 FULL（§11 Q17），归档时显示业务核验，M1 复测补 FULL。

### 8.1 输入

- 需要组态目录原件（§2.2）：t1 v1、v2 即开发主机的 `small_cut/small_cut-1`、`small_cut-2`。节点上的源包没有 `.pmc`，浏览器上传会在校验阶段拒绝；
  不用源包加占位 `.pmc` 代替：那样不是用户的真实目录，M1 的测量也没有意义。
- **传输（§11 Q2）：** FE3a 已传到 05 的 `/home/dev/gateway-real-dumps/source-dirs/t1-v1`、`t1-v2`、`t4-v1`，清单 SHA256 见 FE3a handoff §4.1。
  每次运行前重新核对清单与 SHA256（不把旧存在性当作实时证明），一律以只读 bind mount（`:ro`）挂进容器。

### 8.2 节点与步骤

- 节点 05（DC36：t1–t3 在 05），按 §4.2 获取占用；与后端在 05 上的 t1 等运行互斥。
- `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，一个独立 scope。步骤按后端 t1（`real_dump_journey.py`）的主线顺序，
  省略 repeat-v1（同一输入重复上传）；历史比较改用三节点。两者并不逐步对应：
  1. 提交人：工作区 → 选择 t1 v1 目录 → MODIFIED_ONLY 上传（基于空的 `INITIAL`） → Preview → 下载并浏览（全部为新增表） → 提交；
  2. 审核人：审核模式下载 History bundle → 通过；
  3. 归档确认人：归档主线 → 预检显示业务核验 → 有异常时逐项接受（理由写明“t1 证据运行”与异常编码）→ 确认归档 → head 前移到 v1；
  4. 提交人：选择 FULL，① 选 t1 v1 目录、② 选 t1 v2 目录 → 上传 → Preview → 下载并浏览两个比较对 → 提交；
  5. 审核人：通过；
  6. 审核人：历史比较三节点（`INITIAL`、归档 v1、v2 提交） → 打开结果浏览。
- **第 3 步的预期：** t1 v1 的 `version_manager` 有 `saved_time`（核对报告 §8.1），基线为空 `INITIAL`，预期没有业务核验异常。
  若出现异常：只可能是 ② 的时间质量或顺序项（`GENERATION_TIME_INVALID_VALUES`、`GENERATION_TIME_LAST_NOT_MAX` 等），按界面逐项接受，并在 handoff 列出编码与 `details`；
  出现来源项、基线时间项或其他不应在空基线上出现的编码时停止，交设计会话。
- t1 不归档 v2，v2 的业务核验不在 t1 中产生。

### 8.3 通过标准

全部由程序判定，读取下载到的 bundle manifest 中 `pairs[].summary` 的四个汇总数：`table_count`、`changed_table_count`、`degraded_table_count`、`failed_table_count`。

- **预期值的来源：** 从被测候选同一 vnext 树的 `vnext/backend/benchmarks/real_dump_journey.py` 读取，不手抄。
  在宿主机用 `python3 -I` 的 `ast.literal_eval` 读取模块级常量 `S2B_DATASET_BASELINE` 与 `S1B_V2_PREVIEW_CHANGED_COUNTS`；读不到即停止。
  前端上传的是整个目录（19 个文件），后端忽略 Contract 以外的成员；后端 t1 上传的是规范化源包。两者的 `dbcfg.sql` 与 `logics.xml` 逐字节相同（§2.2），因此预期值可以直接沿用。
  核对报告 §4 已核：当前 vnext 树上 t1 v1/v2 的 `preview_table_count` 均为 124，v2 changed 为 4。
- **v1 Preview：**
  - `table_count = changed_table_count = S2B_DATASET_BASELINE["rd-t1-a-v1"]["preview_table_count"] + 1`。+1 是派生表 `composite_signal_point`；
  - `degraded_table_count = failed_table_count = 0`。
  - 依据：`_assert_s1b_preview_summary`。
- **v2 Preview（FULL）：** 恰好两个比较对，按 `pair_id` 取用，不按顺序或默认视图取（FE3b 评估交接 §6：默认视图的 `pair_count` 不能代表完整 FULL）。
- **`baseline_to_initial`（归档 v1 → ① t1 v1）：** ① 与已归档的 v1 是同一目录：
  - `changed_table_count = degraded_table_count = failed_table_count = 0`；
  - `table_count` 记录实际值，不设预期（这一对没有后端 t1 的对照常量）；
  - `changed_table_count` 不为 0 时停止，交设计会话（同 §4.6 中 B 的规则）。
- **`initial_to_modified`（① t1 v1 → ② t1 v2）：** 与原 MODIFIED_ONLY 的 v2 预期相同（① 与当时的基线内容相同）：
  - `table_count` 等于 `S2B_DATASET_BASELINE["rd-t1-a-v2"]["preview_table_count"] + 1`；`degraded_table_count = failed_table_count = 0`；
  - `changed_table_count = S1B_V2_PREVIEW_CHANGED_COUNTS["rd-t1-a-v2"] + composite_changed`。
    `composite_changed` 为 1 或 0，前端按同一 bundle 中 `composite_signal_point` 的状态是否属于 `UNCHANGED`、`BUSINESS_EQUIVALENT` 取值；
  - 派生表本身是否变化，只在有对照时独立核对：同一 vnext 树上有后端 t1 运行结果时，核对两者的 `composite_changed` 相同；取不到时 handoff 记录实际值，并注明没有对照。
- 每一步在浏览器中完成，没有未捕获错误；每次下载都通过 tar 成员与摘要校验。
- 有诊断时，界面显示对应文案而不是通用文案（FE2 kickoff §5.5），handoff 列出出现过的编码。
- 各步骤耗时、bundle 体积与下载耗时只报告，不设门槛。05 不是计时参考节点，这些数字不作为性能证据（DC36）。
- 关键页面（工作台、v2 Preview 差异浏览、审核模式、历史比较结果）在 1280 与 1920 下各存参考截图，只留在节点上，SHA256 写入 handoff；不作验收，FE4 重拍（前端 kickoff §6）。

### 8.4 M1：打包峰值内存

通用方法与日志字段见 [testing-conventions「真实 backend e2e」](../backend-vnext/testing-conventions.md#真实-backend-e2e)；本节保留场景、次数与判断标准。

- **测量内容：** 目录字节数与文件数、压缩后包大小、打包耗时，以及打包期间 Chromium 各进程的内存峰值。
- **场景：**
  - MODIFIED_ONLY：只打 ② 一个包；
  - FULL：先打 ①，再打 ②（`UploadStepCard`）。打 ② 时 ① 的压缩包还在内存中；`buildTar` 先存一份文件内容，再拼一份整包。FULL 是更可能超标的场景。
  - t1 v1 测 MODIFIED_ONLY；t4 v1 测 MODIFIED_ONLY 与 FULL（① 和 ② 都用 `large-1`）。
- **测量方法：**
  - **新浏览器：** 每次测量启动一个新的浏览器实例；
  - **进程：** 经浏览器级 CDP 会话（`browser.newBrowserCDPSession()`）调用 `SystemInfo.getProcessInfo` 取各进程 PID；拿不到时，从浏览器主进程向下遍历 `/proc` 中的子进程，按命令行中的 `--type=` 区分；
  - **记录全部进程：** renderer、browser 主进程、utility/network、GPU。主指标是 renderer；
  - **峰值清零：** 在“确认上传”之前，对每个进程向 `/proc/<pid>/clear_refs` 写入 `5`，重置 `VmHWM`，以重置后的 `VmHWM` 为基线，同时记录 `VmRSS`（owner 2026-11-08 确认，与 FE3a 实现一致）；
    上传请求发出后（打包已完成）读取 `VmHWM`。峰值增量 = `VmHWM` − 基线；
  - `performance.memory` 只作参考，它不含 `ArrayBuffer` 的外部内存；
  - **包大小：** 从 multipart 中 `manifest` 部分的 `size_bytes` 读取；
  - **打包耗时：** 用上传步骤卡已有的阶段计时（`begin("packaging")` 到下一阶段开始）；
  - 每个目录、每个场景测 3 次，报告中位数与最大值。
- **FE3a（已完成）：** 在 05 上用模拟接口测量，结果在 FE3a handoff。
- **FE3c：** 在 t1 旅程中用生产构建复测，与 FE3a 对照：第 1 步 t1 v1 的 MODIFIED_ONLY，第 4 步的 FULL（① t1 v1 + ② t1 v2）。
  旅程中每个场景只有一次，不要求 3 次；报告该次的值，并注明与 FE3a“3 次取中位数”的方法差异。
  **t1 复测只报告、作回归对照，不按线性外推判定（§11 Q20，修订 2 审核 C1）：** t1 目录约 6.5 MiB，增量主要是固定开销（FE3a t1 v1 MODIFIED renderer 24.86 MiB，线性外推到 1 GB 约 3.5 GiB，按比例放大没有意义）。
  - 回归对照：MODIFIED_ONLY 的 renderer 增量与 FE3a t1 v1 的 24.86 MiB 对照；超过其 2 倍时在 handoff 中报告并交设计会话判断。FE3a 没有 t1 FULL 的数值，FULL 只报告；
  - 超标判断仍只用 t4（FE3a 的结论，Q12）；
  - FE3b 或 FE3c 改动了打包代码（`features/upload/` 下的打包、压缩与 `buildTar`，或 `UploadStepCard` 的打包流程）时，按本节方法在 05 用 t4 v1 重测 MODIFIED_ONLY 与 FULL，各 3 次，按下面的判断标准判定。
- **判断（§11 Q3）：** 默认标准对 MODIFIED_ONLY 与 FULL 都适用：t4 v1 的 renderer 峰值增量不超过 1 GiB；按目录大小线性外推到前端上限 1 GB 时不超过 3 GiB。线性外推只用于 t4 这样的大目录，不用于 t1。
  任一不满足即改为流式打包（逐文件读取、边打包边压缩），FE2 kickoff §7.1 的后端校验继续接受产物，改后重测。
- **FE3a 的结论（owner 2026-11-05，§11 Q12）：**
  - **判定：** 只看 renderer。t4 v1 renderer 峰值增量最大 676.3 MiB（审核复测 668.2 MiB），线性外推到 1 GB 约 2.08 GiB，两项都满足。不改流式，除非 FE3c 复测时 renderer 不满足上面的标准。
  - **浏览器主进程：** 作为报告项，不参与判定。FE3a 实测：MODIFIED 时增加约 200 MiB，FULL 时约 420 MiB。两进程合计外推到 1 GB 约 3.4 GiB。
  - **理由：** renderer 是持有 `ArrayBuffer`、内存不足时崩溃的进程；64 位桌面版 Chromium 的浏览器主进程 Blob 存储在内存中最多 2 GiB，超过后写入磁盘；主进程的增量更可能来自读取文件，改流式未必能降低它；用户机器内存按 16 GB 及以上估计（owner）。
  - **FE3c 复测补充：** 打包期间约每 100 ms 采样一次各进程 `/proc/<pid>/status` 的 `RssAnon`、`RssFile`、`RssShmem`，报告各项最大值，以确认主进程的增量是否属于可回收的文件页；
    只报告、不作判定。`VmHWM` 增量的方法不变。

## 9. 证据

| 子阶段 | 节点 | 内容 | 性质 |
| --- | --- | --- | --- |
| FE3a | 04 | `run-tests.sh --e2e --screenshots`；上传包后端校验；`--suite smoke` | 证据（已完成） |
| FE3a | 05 | M1 打包测量（§8.4） | 测量（已完成） |
| FE3b | 07 | `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`），含 §5.5 的同字节互通单测与模拟 e2e | 调试 |
| FE3b | 05 | `--suite journeys`（FE3b 部分）；`validate-upload-package.sh` | 调试 |
| FE3b | 04 | `run-tests.sh --e2e --screenshots`；`validate-upload-package.sh`；`--suite journeys`（含运行时 OpenAPI 比对）。各一次 | 证据 |
| FE3c | 07、05 | 同 FE3b 的调试项，`--suite journeys` 为完整集；`--suite t1` 调试 | 调试 |
| FE3c | 04 | 同 FE3b 的三项，`--suite journeys` 为完整集 | 证据 |
| FE3c | 05 | `--suite t1` 一次（含 M1 复测与参考截图） | 证据（耗时只报告） |

- 调试与取证分开（DC30）：
  - 调试只跑 focused 与出问题的那一段；
  - 04 证据与 05 的 t1 证据只在审核通过后，于最终候选的 clean、已提交 detached worktree 上各运行一次；
  - 07 的运行只作调试，不作为证据（AGENTS：新节点结果不作正式依据）。
- 运行日志、截图与 trace 都在 worktree 外的证据目录，记录 SHA256；handoff 记录工具链与依赖镜像身份、npm 缓存来源、运行节点。
- **需要重拍并交 owner 看图确认的截图（1280 与 1920）：**
  - FE3b：
    - §6.1：上传模式顶栏撤回可用，以及表中每种禁用状态各一张（含“无法确认提交状态”）；
    - 上传模式撤回对话框、撤回冲突提示、撤回成功后的上传步骤卡；W8 中工作台上传的禁用状态；
    - §6.4 D1–D5：组态树、详情面板与审核模式顶栏；
    - 快照刷新与退回用词统一后显示有变化的页面。
  - FE3c（模拟接口，§16.9 的场景）：
    - 业务核验面板：核验概况；含两侧独立项（同码、同目标，① 与 ② 两张卡，一张已接受、一张未处理）；来源未解释且已接受的卡；时间倒退与“最后一个不是最大值”的卡；多项分组（含 399 项的列表首屏）；
    - 接受对话框、撤销对话框（含理由为空时的禁用原因）；
    - 关闭对话框；关闭成功与 200 回放（显示首次关闭人）的结果；
    - 待审核阻塞；阻断项（完整性失败）没有接受入口；
    - “确认归档”的各种禁用原因；开始归档被服务器拒绝后的提示；
    - 审核模式顶栏：过期通过的 409 提示与之后的禁用原因；`ARCHIVE_CLOSED` 提示；
    - 终局处置（§6.4 D1–D3）在真实数据下的组态树与审核顶栏，取真实 backend 的参考截图对照。
- 真实 backend 与 t1 的参考截图只作参考；FE4 用真实 backend 与 t1 数据重拍关键页面（前端 kickoff §6，节点见 §12）。

## 10. 实施会话的停止条件

除 AGENTS、前端 kickoff 与 FE2 kickoff §10 已有的规则外：

- 合入后的接口与 §2.3 不符，或运行时 OpenAPI 与后端原件（FE3b 为 `977b2258…`，FE3c 为后端为 `6368c9c40c` 补交的原件，§5.2、§13.5）规范化后不同、出现前端没有预期的变化（§5.1、§5.2）；
- 真实 e2e 发现后端缺陷，或后端不接受 §4.6 的输入：保留日志与 trace，交设计会话与后端设计会话处理；不在前端绕过，不改 `vnext/`；
- 需要后端新增字段或接口；
- §5.5 的 fixture SHA256 与本文不符，或后端 tar 需要 `path`、`size` 以外的 PAX key 才能解析；
- 依赖镜像、RS 依赖镜像、工具链镜像或 npm 缓存缺失，身份或 label 不符，或构建需要访问网络；FE3b 合入 `748de5034d` 后 `--print-input` 不得 `lock-d054366c02fa`，或候选的 `vnext/` 树不是 `56720104af`；FE3c 合入 `fd9e383d76` 后 `--print-input` 不得 `lock-578e079b762e`（§4.3，审核会话在 §13.5 现场核对后填写），或候选的 `vnext/` 树不是 `6368c9c40c`；
- 运行需要修改 `vnext/` 下的 Compose、脚本或配置；
- t1 或 M1 的输入核对不符（§8.1），或 §8.3 的预期值读不到（FE3c）；
- FE3c：归档预检的异常集合与 §4.6 的表不符；t1 归档 v1 出现 §8.2 所列以外的编码；`baseline_to_initial` 的 `changed_table_count` 不为 0；
- FE3c：关闭请求的 `expected_review_version` 不能按 §16.6 取自同一次候选读取中目标候选的 `review_version`（例如运行时候选响应没有该字段，或与 §2.3 第 19 行不符），或者只有追加审核权限、读取 Review、写死或推断才能完成关闭；`selected` 只含两个字段时请求被拒绝。不在前端绕过，交设计会话；
- 清理核对失败（§4.2）。

脚本自身的错误（尚未触及被测对象、没有副作用）按 DC68 重做一次，重做再失败即停止；被测对象运行后的失败不按 DC68 重做。

## 11. owner 决定

Q1–Q9 由 owner 于 2026-11-05 确认，按下表的建议执行。Q1–Q7 经 kickoff 审核（`920f068da4`）逐条判断成立；Q9 经定向复审（`e91d9db6eb`）核对成立。

| # | 事项 | 决定 |
| --- | --- | --- |
| Q1 | 阶段安排（§3） | 乙：FE3a 先开始，FE3b 在 S2a、BE-a、BE-d 合入后开始（2026-11-07 由 Q13 进一步拆分） |
| Q2 | t1 输入（§8.1）：节点上没有组态目录原件 | 把 `small_cut-1`、`small_cut-2` 与 `large-1`（只用于 M1）经局域网传到 05 的 `source-dirs/`，只读挂载，并记录 SHA256 清单。不用源包加占位 `.pmc` 代替 |
| Q3 | M1 的测量与判断（§8.4） | FE3a 用 t1 与 t4 目录测打包内存，之后在 t1 旅程中复测；默认标准按 §8.4，对两种模式都适用 |
| Q4 | 真实 e2e 的入口（§4.1） | 单独提交的脚本，不并入 `run-tests.sh` |
| Q5 | 真实 e2e 的被测构建与身份注入（§4.5） | 测生产构建；身份由 Playwright 按 context 注入 `window.__gatewaySession`，token 每次随机生成，不进入构建产物 |
| Q6 | FE2c 的 `sessionStorage` 提交标记（§6.2） | 由 `active_submit_attempt_id` 与 `job_kind` 取代并删除；URL 中的 `operation_id` 保留 |
| Q7 | 上传模式顶栏撤回的显示（§6.1） | 始终显示，不可用时禁用并给原因（与 F4 一致）；文案按 §6.1 |
| Q8 | 目录传输晚于 FE3a 其余工作时，FE3a 能否先退出 | M1 测完才能退出 FE3a（已按此退出） |
| Q9 | 工作区被占用时是否禁用上传（§6.1） | 任一指针非空时禁用“上传”与“提交”，原因按 §6.1 的表 |

Q10–Q12 来自 FE3a 审核（`a0b9604ddd`），由 owner 于 2026-11-05 确认（§15.1）。

| # | 事项 | 决定 |
| --- | --- | --- |
| Q10 | 真实 e2e 的上传输入：共用 SQL 含没有 `gid` 列的 `b1_n1_iec104_yc_list`，真实 Preview 返回 `KEY_MISSING` | 新增真实 e2e 专用的合法输入，模拟 fixture 不动。来源规则与四类上传按 §4.6 |
| Q11 | 组态树的基线是否显示序号 | 甲：树也显示“归档基线 n”，与摘要共用同一个标签函数（§7 M7） |
| Q12 | M1 的判定是否只看 renderer | 只看 renderer，FE3a 满足，不改流式；浏览器主进程只报告，复测时补记 `RssAnon`、`RssFile`、`RssShmem`（§8.4） |

Q13 起来自 2026-11-07 的修订 2（Q13、Q14 来自第 1 步，Q15–Q19 来自第 2 步，Q20 来自修订 2 审核），Q21 来自修订 3。Q13–Q20 已由 owner 决定（Q15–Q20 于 2026-11-09 全部按“建议”一列确认）；Q21 交 owner 转后端。

| # | 事项 | 建议与理由 | 状态 |
| --- | --- | --- | --- |
| Q13 | FE3 剩余工作是否拆段（核对报告 §8.2） | 拆成 FE3b（契约与基础）与 FE3c（归档核验与完整旅程），tag `fe-fe3b-exit`、`fe-fe3c-exit`，FE4 从 `fe-fe3c-exit` 开始；内容、前置与退出条件按 §3.2。理由见 §3.1 末段 | **已决定（owner 2026-11-07）**，补记 |
| Q14 | 续做得到 `ABORTED` 或读取失败后，“提交”“上传”是否恢复可用（核对报告 §3.3、§8.1 第 3 项；FE3a 审核 B7） | 按 §6.2 的续做规则：先重读工作区，按指针与 §6.1 的表决定；工作区或 attempt 读不到时保持禁用，原因“无法确认提交状态”，附“重试”。理由：① 提示与禁用原因一致，满足 B7；② 不在占用指针未清时解锁，满足后端“查询失败、operation 终态都不等于占用释放”；③ 不需要后端新字段。不采用“读取失败即恢复可用”（会在指针未清时允许新提交，后端返回 409，用户看到的是更难理解的冲突） | **已决定（owner 2026-11-08）**，按建议；修订 2 审核 §2.6 判断成立 |
| Q15 | 真实 e2e 的合成输入是否补 `version_manager.saved_time`（核对报告 §8.1 第 1 项） | **不补。** 理由：① Q10 的派生规则只为“backend 接受上传”补列，补时间会改变规则的含义；② 缺时间正好产生后端要求重点覆盖的“同码、同目标、两侧独立”项（FULL 的 ① 与 ② 各一项 `GENERATION_TIME_MISSING`）与 `BASELINE_TIME_UNAVAILABLE`；③ 来源未解释可以用现有输入构造（§4.6 J2 的 E）。代价：每次归档都要先接受时间项；时间倒退与“最后一个不是最大值”在真实 e2e 中产生不了，只由模拟接口覆盖，t1 的真实时间另作补充。若 owner 希望真实覆盖时间倒退，可另加一组只用于 FE3c 的带时间输入，作为对 Q10 的扩展 | **已决定（owner 2026-11-09）**，按建议：不补 |
| Q16 | 关闭入口放在哪里（核对报告 §8.3） | **甲：归档主线对话框的“候选提交”一节**（§16.6），每个候选一个“关闭（不归档）”按钮。理由：① 关闭通常在看到不愿接受的业务核验后决定，入口与异常在同一处；② 打开该对话框要读归档候选，没有 `archive_submission` 的身份读不到（403），入口自然只对归档确认人出现，前端不需要推断权限；③ 关闭请求需要当前基线（`expected_baseline_node_id`、`expected_baseline_head_version`），对话框已从预检取得；④ 提交人与审核人的顶栏不出现危险按钮。不采用：乙，组态树已通过节点的工具栏（所有身份都看得到，只能靠 403 提示，且需要另取基线）；丙，审核模式顶栏（审核人通常没有归档权限） | **已决定（owner 2026-11-09）**，按建议：甲 |
| Q17 | t1 第 4 步是否改为 FULL（核对报告 §8.3；FE3b 评估交接 §6） | **改为 FULL：** ① = t1 v1、② = t1 v2，按 `pair_id` 核对两个比较对（§8.3）。理由：① 后端要求浏览器 t1 覆盖 FULL 两个比较对；② ① 与已归档的 v1 相同，`baseline_to_initial` 必须为 0，是一个独立的强判据；③ `initial_to_modified` 与原 MODIFIED_ONLY 的预期相同，原有判据不丢；④ M1 复测顺带覆盖真实目录的 FULL。MODIFIED_ONLY 仍由第 1 步覆盖 | **已决定（owner 2026-11-09）**，按建议：改为 FULL |
| Q18 | 关闭请求的 `expected_review_version` 从哪里取（§16.6，设计会话核对后端源码发现） | **交 owner 转后端设计会话，前端不假设。** 事实：`CloseSubmissionRequest` 要求 `expected_review_version`；`GET /v1/submissions/{id}/review` 只对 `review_submission` 或本人撤回权限开放（`application/submission/review.py::assert_review_permission`），只有 `archive_submission` 的身份得到 403；`ArchiveCandidateResponse`、`PreviewArchivePlanResponse`、`HistoryNodeResponse` 都没有该字段。后端 Compose 测试用全权限身份并写死 `1`（`tests/test_archive_compose_e2e.py`）。前端可以接受的方向（由后端选择）：在归档候选或预检响应中给出每个候选的 `review_version`；或允许 `archive_submission` 读取当前 scope 候选的 review。不采用前端写死 `1` 或要求归档确认人同时持有审核权限。**后端答复（2026-11-08，`1981882cc6`）：** 缺口属实；建议作为独立的后端补缺，在归档候选只读响应中逐候选增加 `review_version`（同一读事务取自权威 review projection；不改 candidate digest、选择与关闭的 fingerprint、CAS 与审核读取权限），先固定 Contract/OpenAPI，再实施、独审并在 06 验证只有归档权限的身份可完成关闭。该答复不是实施授权。**交付（2026-11-08，[Q18 交接](../backend-vnext/refactoring/formal/plans/p6-be-q18-handoff.md)）：** 最终产品 `94b25a3279`，独审 GO；`GET /v1/archive-candidates` 的 `candidates[]` 每项新增必填 `review_version`，Review GET 的 ACL 不变，版本过期返回 409；`selected` 仍只含两个字段（§2.3 第 19 行）。后端没有交付新的生产 OpenAPI 原件，已另请补交（§5.2） | **已交付（2026-11-08）**；owner 2026-11-09 确认按建议（前端不假设，由后端补缺）。§16.6 已于修订 3 定稿 |
| Q19 | FE3c 的新界面是否需要 HTML 草图 | **不另画草图，用 §16 的文字规格与线框。** 理由：归档对话框在 FE2 也没有草图，按“无草图页面”由审核会话对照 UI 原则核对、owner 看图确认；新内容是对话框内的列表与卡片，沿用现有令牌与组件，线框足以确定位置与层级。owner 希望先看草图时，由设计会话补到 `sketches/s5-archive-validation/`，FE3c 实施等草图确认 | **已决定（owner 2026-11-09）**，按建议：不另画草图 |
| Q20 | FE3c 在 t1 上复测 M1 时如何判定（修订 2 审核 C1；改变 Q3、Q12 下的判定口径） | **t1 只报告并与 FE3a 的 t1 数值作回归对照，超标判断仍只用 t4；打包代码有改动时在 05 重测 t4**（§8.4）。理由：① t1 增量主要是固定开销，按 §8.4 线性外推，FE3a 的 24.86 MiB 已对应约 3.5 GiB，照此判定会误触发改流式；② t4（317 MB）的外推才反映随目录增长的部分，FE3a 已按 t4 判定满足；③ 回归对照（2 倍）能发现打包实现的退化；④ 打包代码改动时重测 t4，保证判定仍基于大目录。不采用：在 t1 上照旧外推（必然“超标”）；FE3c 无条件重测 t4（打包未改时重复 FE3a 的结果） | **已决定（owner 2026-11-09）**，按建议 |
| Q21 | `56720104af..6368c9c40c` 后不再产生的三个比较诊断码与新出现的诊断码（§2.3 末段，修订 3） | **交 owner 转后端设计会话确认，前端不假设：** ① `ROW_IDENTITY_UNSUPPORTED`（旧树：有序表有效键多于一列时降级）在新树中是否已不再产生；多列行标识的有序表现在按什么结果输出（详细比较、其他诊断码或失败）；② `COMPARISON_MODE_NOT_DETAILED`、`ORDER_KEY_UNSUPPORTED` 是否可以确认为已删除（设计会话判断两者在旧树中就不可达）；③ `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID`、`METADATA_ROUTE_REQUIRES_NATIVE_ROWS`、`METADATA_ROLE_REQUIRES_NATIVE_ROWS` 能否写入 manifest 或 surface 的诊断，是否取代了 `BLANK_PROVENANCE_*`。前端据答复删除不再产生的码的文案、为新码补文案；答复前保留现状（未知码显示“比较过程有提示”加原始码）。不阻塞 FE3c | 待 owner 转后端 |

## 12. 开放项

| 项 | 说明 | 何时 |
| --- | --- | --- |
| 基线已前移后才通过的提交永久占用工作区（2026-11-05 定向复审 §4） | **已关闭：** DC89 拒绝过期 `APPROVE`，归档关闭其余已通过的同级提交，并有手工关闭出口；20d3b885f6 澄清标记只作历史说明。§6.1 已删除暂定行（§2.3 第 13 行） | — |
| tar 成员与 closure 的对应（2026-11-05 审核报告 D1） | **已关闭：** DC89 与 BE-d 交接 §3 确认与前端要求一致（§2.3 第 9 行） | — |
| FE3c 的设计 | 第 2 步已写（§16、§4.6、§4.7、§8、§9、§13.5、§13.6），修订 2 审核为定向修订，C1–C3 已改（§15.4）；owner 2026-11-09 已确认 Q15–Q20；修订 3 补齐 §16.6 定稿与合入点（§15.5），待审核会话核对 | 发出 FE3c 提示词前 |
| 关闭请求的 `expected_review_version`（§16.6） | **已交付：** Q18 最终产品 `94b25a3279`（独审 GO），归档候选逐项返回 `review_version`（§2.3 第 19 行）。修订 3 已定稿 §16.6、§5.3 的模拟规则与 §16.9 V9、V14 | — |
| FE3c 的生产 OpenAPI 原件 | **已交付（2026-11-09）：** SHA256 `ce58f20a…c079`，设计会话已核，与 FE3b 原件规范化后只差 `review_version` 两处（§5.2）；审核会话发出提示词时填入 §13.5 并重算 | — |
| 比较诊断码的变化（§2.3 末段，§11 Q21） | 三个旧码不再产生、四个新码可能出现，交 owner 转后端确认；答复前前端保留现状 | 后端答复后（不阻塞 FE3c） |
| §4.6 预期异常的实测校正 | 预期异常由源码推断，FE3c 05 调试首轮实测，不符即停（§4.6） | FE3c 调试首轮 |
| FE4 真实数据重拍的节点 | 前端 kickoff §6 写“FE4 在 04 上用真实 backend 与 t1 数据重拍”，但 DC36 规定 t1–t3 在 05。建议 FE4 kickoff 时改为：t1 数据的重拍在 05，04 只跑合成输入的真实 backend e2e；如需在 04 使用 t1 数据，由 owner 作例外决定 | FE4 kickoff |
| 首批空基线（FE2 kickoff Q18） | 仍为缺口，不在 FE3。FE3 的输入都从空的 `INITIAL` 开始，界面不禁用第 ① 步 | 后端提供该事实后 |
| P6 计时与整包下载（DC74 草案） | t1 旅程的下载耗时与体积只报告；DC74 确认后，按其结论更新前端 kickoff §9 | DC74 确认后 |
| AGENTS 与 testing-conventions 的真实 e2e 条文 | 2026-11-08 已收入 AGENTS FD7 与 [testing-conventions](../backend-vnext/testing-conventions.md#真实-backend-e2e)，待独立审核与 owner 确认；不阻塞 FE3b | 治理会话 |
| `--color-warning-soft` 未定义（FE3a 复审 N8） | “需要管理员处理”等提示为灰底。owner 已看 FE3a 截图接受，FE3 不改；如要改成黄色，属于设计令牌，在 FE4 视觉微调时由设计会话提出 | FE4 |

## 13. 实施与审核提示词

以下提示词在各自的前置条件满足、并经 owner 确认后发出（或由 owner 转发）。发出时填写方括号中的值。13.1、13.2 已发出并完成（FE3a），保留备查。

### 13.1 FE3a 实施（已发出，历史）

> 你是 FE3a 前端实施会话。先读 AGENTS、[前端 kickoff](frontend-kickoff.md)（§4、§6、§7）、[FE2 kickoff](fe2-kickoff.md)（§6.5、§7、§10）、本文（main `[确认提交]`）全文、[本文的 kickoff 审核](reviews/fe3-kickoff-review.md)，以及 FE2c 复审第 4 轮与证据核对第 1 次。
>
> - **起点与分支：** `fe-vnext`（`fe-fe2c-exit` = `749f219d5f`）。先把 main `[确认提交]` 合入 `fe-vnext`（只合并，不 rebase），在开发主机 worktree `/home/dev/gdds-fe` 开发；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行。
> - **先做两项准备：** 按本文 §8.1 把 t1 v1、v2 与 t4 v1 的组态目录原件传到 05；按本文 §4.3 把 `gateway-backend-deps:lock-c668cef8e47e` 补到 05。两项都在 handoff 中记录。
> - **范围（本文 §3.2 FE3a 一行）：** §7 的 M7、n3、n8；§4 的运行框架与 `--suite smoke`；§4.6 的上传输入；§5.4 生成类型一致性检查；§8.4 的 M1 打包测量。
> - **不做：** 不改 `vnext/`；不刷新 OpenAPI 快照；不做 §6。
> - **停止条件：** 本文 §10。脚本自身错误按 DC68 重做一次。
> - **交付：** 05 上完整运行 `run-tests.sh --e2e --screenshots` 与 `--suite smoke` 各一次通过后，提交代码候选与 handoff（`docs/frontend-vnext/fe3a-handoff.md`）。

### 13.2 FE3a 审核（已发出，历史）

> 你是 FE3a 审核会话。审核 `fe-fe2c-exit..[FE3a handoff 提交]`；依据本文 §3.2、§3.3、§4、§5.4、§7、§8.1、§8.4、§10。重点：运行框架、冒烟、上传输入、带入项、M1、传输记录；在 05 上独立运行一次 `run-tests.sh --e2e --screenshots` 与 `--suite smoke`。报告写入 `docs/frontend-vnext/reviews/fe3a-review.md`。

### 13.3 FE3b 实施（前置：本文第 1 步经 kickoff 审核、定向复核与 owner 确认，Q14 已决定；审核会话现场核对后发出）

以核对报告 §10 的草案为基础，按本文修订后的章节编号整理。发出前审核会话现场核对接口、镜像与节点占用，并填好方括号中的值。

> 你是 FE3b 前端实施会话。FE3 已拆成 FE3b（契约与基础）与 FE3c（归档核验与完整旅程），本阶段只做 FE3b。
>
> **先读：**
> - AGENTS：“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”；testing-conventions“前端测试”与“真实 backend e2e”；
> - 前端 kickoff §4.3、§4.4、§7.1 与 FD4；FE2 kickoff §4.1、§7.5；
> - FE3 kickoff（main `[kickoff 确认提交]`）全文，重点 §2.1（含“main 的后续变化与 FE3b 合入点”）、§2.3、§3.2 FE3b 一行、§4、§5、§6、§9、§10；
> - FE3a handoff 与 `reviews/fe3a-*.md`；`reviews/fe3b-precondition-check.md` 的 §3、§6、§8、§9；
> - 后端：[FE3b 评估交接](../backend-vnext/refactoring/formal/plans/p6-fe3b-backend-assessment-handoff.md)、[BE-d 前端交接](../backend-vnext/refactoring/formal/plans/p6-be-d-frontend-handoff.md)（含 §2.1）、[V2 交接](../backend-vnext/refactoring/formal/plans/p6-v2-frontend-handoff.md) §3、[BE-a 交接](../backend-vnext/refactoring/formal/plans/p6-be-a1-handoff.md)。
>
> **后端事实（已核对，不需要再等后端）：** 见 kickoff §2.1、§2.2。`p6-s2a-exit` → `53b676a629`；`p6-be-a-d-exit` → `77b9aeea74`（产品 `49403f21aa`）；FE3b 合入的 main `748de5034d` 的 `vnext/` 树 `56720104af`；生产 OpenAPI 原件 SHA256 `977b2258…b8a7`；依赖镜像 `lock-d054366c02fa`、RS 依赖镜像、工具链与 npm 缓存在 04、05 上齐备（07 有后三者），不需要预填充。
> 当前 main 的 `vnext/` 已因 S3 改变，FE3b 不合入（kickoff §2.1，owner 选甲）。
>
> **起点与分支：**
> - `fe-vnext` 在 `fe-fe3a-exit`（→ `0e7caf66f4`），开发主机 worktree `/home/dev/gdds-fe`；
> - 先把 main `748de5034d` 以 `--no-ff` 合入 `fe-vnext`，不 rebase，FE3b 期间不再合入 main；合并会带入 main 上的前端提交 `55d56efb6e`（`GATEWAY_FE_TEST_WORKERS`），保留，由 FE3b 审核核对；
> - kickoff 以 main `[kickoff 确认提交]` 为准阅读（它晚于 `748de5034d`，不需要合入）；
> - 合并后按 kickoff §3.2 做路径核对（`<main>` 为 `748de5034d`；候选 `vnext/` 树必须为 `56720104af`；差异只含 `frontend/` 与 `docs/frontend-vnext/`）；
> - 合并后的 HEAD 上 `build-backend-dependency-base.sh --print-input` 必须仍得 `lock-d054366c02fa`，否则停止。
>
> **范围（kickoff §3.2 FE3b 一行）：**
> 1. **快照与清理（§5.1–§5.3）：** 用真实 backend 起栈取 `/openapi.json`，按 §5.1 规范化写入并重新生成类型，同一提交；与原件规范化后逐字节相同，不同即停止。按 §5.3 删除退回修改的全部路径、201/202 变通，`archive_disposition` 直接改为 `submission_disposition`；`REJECTED` 统一显示为“已退回”；模拟数据按 §5.3 的可达组合与指针规则；归档对话框的 action 按 5 个 `subject_kind` 穷举映射；错误码单测解析新快照；`check-production-build.mjs` 覆盖新增模拟 token。
> 2. **tar 与 OPFS（§5.5）：** PAX 按字节解析，记录切分层与成员层分开，成员层只接受 `path`/`size`；标准 PAX `size`；接收预算先检查再分配；失败中止 OPFS 安装。把后端的 9 个互通原件原样提交到 `frontend/src/test/fixtures/backend-interop/be-d-0ba45e5ef8/` 并加 `SHA256SUMS`，单测与模拟 e2e 按 §5.5 编写。不自造替代 fixture，不生成大文件。
> 3. **上传模式撤回与占用（§6.1–§6.3）：** 按 §6.1 的两张表实现撤回按钮与“提交”“上传”的禁用原因；撤回带 `review_version`；不按 actor 或指针推断可撤回；冲突后重新读取，不自动重发。§6.2 按 `active_submit_attempt_id` 与 `job_kind` 恢复，删除 `gateway-submit-operation` 标记，续做失败按 §6.2 的规则；n3 用例改为基于指针，覆盖不减。§6.3 W1–W10 在模拟接口全部覆盖；“真实”一列为“是”的进入真实 e2e。
> 4. **终局处置只读显示（§6.4）：** 组态树、详情面板与审核模式顶栏按 §6.4 的表；处置优先于 `NOT_CANDIDATE_BASE_ADVANCED`；组态树“归档主线”有处置时禁用；D1–D5 由模拟接口覆盖（D5 为防御性数据，§5.3）。不做关闭入口。
> 5. **真实 backend 旅程（`--suite journeys`，§4.7 中“子阶段”为 FE3b 的部分）：** R1、R2、R3、R4（到 `PENDING`）、R5、R6（`REJECT` → 重提 → 通过）、R7、R9（两节点）、R10、R11；身份按 §4.6，“提交人（本人撤回）”带 `withdraw_own_submission`、不带 `review_submission`；上传按 §4.6 的“FE3b 的上传”，handoff 写出每个 scope 的上传序列。冒烟按 §3.3、§4.7 删除“下载比较结果失败”的临时断言，进入差异浏览后再断言 `pageErrors`。
> 6. **FE3a 带入：** 为 `e2e*/` 加 tsconfig 并纳入类型检查（FE3a 复审 N1）；按 tar 的 `ETag` 与 bundle 摘要记录 bundle 标识（N2）。
>
> **不做（FE3c）：** 归档业务核验的显示、逐项接受与撤销、关闭出口、待审核阻塞与过期通过的界面、R4 身份确认、R8、R9 三节点、R12、§4.6 的 A–D 归档序列及其核对、t1 旅程、M1 复测。不改 `vnext/`；不在浏览器中重算 SQL、来源或时间。
>
> **节点：**
> - 类型检查、lint、单测、构建、截图、模拟接口 e2e 在 07，设置 `GATEWAY_FE_TEST_WORKERS=2`，不获取占用标记；
> - 真实 backend e2e 与上传包校验在 05，由脚本按 kickoff §4.2 获取占用（会话名 `fe3b-impl`）与 `flock -n`，结束后清理并释放；
> - 某节点占用标记的用途为计时测量时，前端在该节点上的任何运行都等待；
> - 不在 04 上运行，04 取证在审核通过后进行；
> - 05、07 上运行时按 kickoff §2.2 设置 npm 缓存的环境变量；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行，日志与截图写在 worktree 外。
>
> **停止条件：** kickoff §10。脚本自身的错误按 DC68 重做一次，重做再失败即停止；被测对象运行后的失败不按 DC68 重做。
>
> **交付：** 07 上 `run-tests.sh --e2e --screenshots`、05 上 `--suite journeys` 与 `validate-upload-package.sh` 各一次通过（均为调试运行）后，提交代码候选与 handoff `docs/frontend-vnext/fe3b-handoff.md`，内容包括：
> - 合并提交、所合入的 main 与 `vnext/` 树、路径核对结果；
> - 快照来源与比对结果；清理清单（删除的退回路径、类型变通与 `sessionStorage` 标记）；
> - W1–W10、D1–D5 与用例的对应；旅程各项结果，只由模拟接口覆盖的项及原因；每个 scope 的上传序列；
> - tar 修复与同字节互通：fixture 目录与 `SHA256SUMS` 的 SHA256、用例名、运行节点与日志 SHA256；预算边界用例；
> - 截图清单（kickoff §9 FE3b）；
> - 每次运行的节点、hostname、起止时间、起止 HEAD、exit code、日志 SHA256；工具链（config digest 与全部 DiffID）、npm 缓存（来源提交、归档 SHA256）、依赖镜像（tag、label、config digest、全部 DiffID）与 RS 镜像身份；
> - 偏差与未决事项。不沿用 FE3a handoff 的勘误项（kickoff §3.2）。
>
> 不推送。
>
> **审核通过后的 04 取证（由审核会话指明）：** 在 04 的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys`。

### 13.4 FE3b 审核（前置：FE3b handoff 已提交）

> 你是 FE3b 审核会话（不与实施会话为同一会话）。审核 `fe-fe3a-exit..[FE3b handoff 提交]`：来自 main 的文档与 `vnext/` 不在前端审核范围，main 上的前端提交 `55d56efb6e` 在范围内；先按本文 §3.2 的“路径核对”检查候选。依据：本文（main `[确认提交]`）§2.3、§4.7、§5、§6、§9、§10，前端 kickoff §7.1 与 FD4，FE2 kickoff §7.5，BE-a 交接，BE-d 前端交接 §1–§3，V2 交接 §3。
>
> 重点：
> 1. **快照与清理：** 与运行时及后端原件规范化后逐字节一致；退回修改的映射、状态与文案已删除，“已拒绝”已统一为“已退回”；201/202 不再使用变通；`archive_disposition` 没有残留或双读；模拟数据符合 §5.3 的可达组合（含指针生命周期、处置组合、`eligibility_note` 只在 `APPROVED`）；归档对话框的 action 映射穷举；错误码单测覆盖新状态码；生产构建检查覆盖新增的模拟 token。
> 2. **tar（§5.5）：** fixture 与后端原件逐字节相同（重新核对 SHA256）；PAX 按字节解析、只接受 `path`/`size`；`size` 覆盖与安全整数；预算在分配前检查；失败时中止 OPFS 安装、不显示“无差异”。
> 3. **§6：** 文案与 §6.1、§6.4 一致；前端没有按 actor 或指针推断可撤回；没有按 operation 终态推断指针已清空；撤回使用 `review_version`；冲突后不自动重发；工作区被占用时“提交”“上传”禁用；续做失败按 §6.2 的规则；URL 中操作的类型按 `job_kind` 判断；删除 `sessionStorage` 标记后 n3 的覆盖不减少。
> 4. **测试与探针：** §6.3 W1–W10、§6.4 D1–D5 都有对应用例；本人撤回没有用审核人或全权限身份。用已提交的一次性 worktree 做探针：
>    - （05，会话名 `fe3b-review`）把撤回的预期版本改为工作区版本：真实 e2e 应失败（先确认场景中两个版本的取值不同）；
>    - （07）去掉 403 分支：W3 应失败；
>    - （07）把 PAX 解析改回按字符切片：`literal_utf8` 等向量与同字节互通单测应失败；
>    - （07）让摘要不符时仍提交 OPFS 安装：§5.5 的负例 e2e 应失败。
> 5. **旅程：** §4.7 中 FE3b 的各项符合要求，R10 的四项在真实 backend 上覆盖；冒烟已删除下载失败判据。
> 6. **运行：** 在 07 上独立运行一次 `run-tests.sh --e2e --screenshots`，在 05 上独立运行一次 `--suite journeys`。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3b-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明 04 取证项（本文 §9 FE3b 行），取证后做证据核对，并给出 FE3b 退出建议（FE3 在 FE3c 结束时退出）。

### 13.5 FE3c 实施（前置：`fe-fe3b-exit`；第 2 步经 kickoff 审核与 owner 确认，含 Q15–Q20；Q18 的后端补缺已交付且 §16.6 已定稿；后端为 `vnext/` 树 `6368c9c40c` 补交的生产 OpenAPI 原件已交付）

发出前审核会话现场核对依赖镜像、RS 依赖镜像与节点占用，并填写方括号中的值（原件路径与 SHA256 必填，原件未交付不发出）。

> 你是 FE3c 前端实施会话。本阶段完成 FE3：归档业务核验、有理由关闭、待审核阻塞与过期通过的界面，完整真实旅程，t1 旅程与 M1 复测。
>
> **先读：**
> - AGENTS：“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”；testing-conventions“前端测试”；
> - 前端 kickoff §4.3、§7.1；FE2 kickoff §4.1、§7.5；
> - FE3 kickoff（main `[kickoff 确认提交]`）全文，重点 §2.3 第 12–18 行、§3.2 FE3c 一行、§4.6（J1、J2 与预期异常）、§4.7、§6.4、§8、§9、§10、§16；
> - FE3b handoff 与 `reviews/fe3b-*.md`；
> - 后端：[V2 交接](../backend-vnext/refactoring/formal/plans/p6-v2-frontend-handoff.md)、[FE3b 评估交接](../backend-vnext/refactoring/formal/plans/p6-fe3b-backend-assessment-handoff.md) §3–§4、[归档业务核验设计](../backend-vnext/refactoring/formal/plans/p6-archive-business-validation-design.md) §4.2、§6、§7.1、§10，以及后端对 Q18 的答复（[S3 协调 §16](../backend-vnext/refactoring/formal/plans/p6-s3-coordination.md#16-fe3c-q18-与生成时间预期当前事实和建议交接)）与补缺的交付（[Q18 交接](../backend-vnext/refactoring/formal/plans/p6-be-q18-handoff.md)，最终产品 `94b25a3279`）。
>
> **起点与分支：** `fe-vnext` 在 `fe-fe3b-exit`。先把 main `fd9e383d76642037e4b3246c847222ea9483e033` 以 `--no-ff` 合入 `fe-vnext`，不 rebase，不合入其后的 main（kickoff §2.1、§3.2）；按 kickoff §3.2 做路径核对（`<main>` 为 `fd9e383d76`，候选 `vnext/` 树必须为 `6368c9c40c`）；合并后 `--print-input` 必须得 `[FE3c 依赖镜像 tag，预期 gateway-backend-deps:lock-578e079b762e]`（审核会话现场核对后填写；04、05 已有，不需要预填充，kickoff §2.2、§4.3），否则停止。RS 依赖镜像仍为 `lock-6dc9659f0aee`。
> 合入带来 Q18 的 OpenAPI 变化：按 §5.1 刷新快照与类型；§5.1、§5.2 的比对原件为后端为 `vnext/` 树 `6368c9c40c` 补交的生产 OpenAPI：`[原件路径]`，SHA256 `[原件 SHA256]`。相对 FE3b 快照的预期差异只有 `ArchiveCandidateResponse.review_version`（kickoff §2.3 第 19 行），其他差异即停止。
>
> **范围（kickoff §3.2 FE3c 一行）：**
> 1. **归档主线对话框（§16.2–§16.5）：** 核验概况；按 `subject_digest` 的独立项卡片，原始诊断与处理状态分开显示；接受与撤销对话框（理由必填）；预检刷新规则；阻断项没有接受入口；“确认归档”的禁用规则与开始归档的引用（不分页、不截断）；待审核阻塞。预检、确认、异常处置、开始归档请求中的 `selected` 显式只取 `submission_id` 与 `expected_candidate_digest` 两个字段，不转发候选读取对象（§16.4；现有 `ArchiveMainlineDialog.tsx:87` 转发整个候选，Q18 后会被后端以 422 拒绝，必须改）。
> 2. **有理由关闭（§16.6）：** 入口、对话框、201/200 处理与关闭后的刷新；`expected_review_version` 取自打开关闭对话框时同一次候选读取中目标候选的 `review_version`，不读取 Review、不写死、不推断、不给归档确认人追加审核权限。
> 3. **审核模式顶栏（§16.7）：** 过期通过的 409、`ARCHIVE_CLOSED`。
> 4. **模拟数据与错误码（§5.3 FE3c 的补充、§16.8）：** 按可达组合构造业务核验与关闭的模拟数据；候选补 `review_version`；路由桩对 `selected` 多出的键返回 422；§16.9 的 V1–V14 在模拟接口全部覆盖。
> 5. **真实旅程：** `--suite journeys` 补入 R4 身份确认、R8、R9 三节点、R12，按 §4.6 的 J1、J2 执行；首轮按 §4.6“实测校正”记录每次预检的异常集合，不符即停。完整集包含 FE3b 的全部旅程。
> 6. **t1（§8）：** 实现 `--suite t1 --input-root`；按 §8.2 的步骤（第 4 步 FULL）与 §8.3 的判据；M1 复测（§8.4，含 `RssAnon`、`RssFile`、`RssShmem` 采样）：t1 只报告并与 FE3a 的 t1 数值作回归对照，不按外推判定；改动了打包代码时在 05 用 t4 v1 重测并按 §8.4 判定（Q20）。
>
> **不做：** 不改 `vnext/`；不在浏览器中重算 SQL、来源或时间；不提供批量接受或默认理由；不给阻断项（完整性、越权、冲突）提供“填写理由继续”的入口。
>
> **节点：** 同 FE3b（07 模拟接口各项，`GATEWAY_FE_TEST_WORKERS=2`；05 真实 backend 与 t1，会话名 `fe3c-impl`；04 只在审核通过后取证）。t1 输入运行前重新核对清单与 SHA256，只读挂载。
>
> **停止条件：** kickoff §10。脚本自身的错误按 DC68 重做一次；被测对象运行后的失败不按 DC68 重做。
>
> **交付：** 07 上 `run-tests.sh --e2e --screenshots`、05 上 `--suite journeys`（完整集）、`--suite t1` 与 `validate-upload-package.sh` 各一次通过（均为调试运行）后，提交代码候选与 handoff `docs/frontend-vnext/fe3c-handoff.md`，内容包括：
> - 合并提交、所合入的 main 与 `vnext/` 树、路径核对结果；
> - §4.6 预期异常表的实测结果（逐次预检的集合），以及与本文的差异和设计会话的处理；
> - V1–V14、J1、J2 各步与用例的对应；只由模拟接口覆盖的项及原因；构造 `selected` 的全部位置及其只取两个字段的方式；
> - t1：§8.3 逐条核对（含两个比较对按 `pair_id`），第 3 步出现的业务核验编码，与后端 t1 的对照或其缺失说明；M1 数据与结论；
> - 截图清单（kickoff §9 FE3c）；
> - 每次运行的节点、hostname、起止时间、起止 HEAD、exit code、日志 SHA256；工具链、npm 缓存、依赖镜像与 RS 镜像身份；
> - 偏差与未决事项。
>
> 不推送。
>
> **审核通过后的取证（由审核会话指明）：** 04 的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys`；05 上 `--suite t1` 证据运行一次。

### 13.6 FE3c 审核（前置：FE3c handoff 已提交）

> 你是 FE3c 审核会话（不与实施会话为同一会话）。审核 `fe-fe3b-exit..[FE3c handoff 提交]`：来自 main 的文档与 `vnext/` 不在前端审核范围；先按本文 §3.2 的“路径核对”检查候选。依据：本文（main `[确认提交]`）§2.3、§4.6、§4.7、§6.4、§8、§9、§10、§16，V2 交接，归档业务核验设计 §6、§7.1、§10，后端对 Q18 的答复与补缺交付。
>
> 重点：
> 1. **业务核验界面：** 预检、确认、异常处置、开始归档请求中的 `selected` 每项恰好两个键（V14）；原始诊断与处理状态分开，接受后不显示为通过；每个 `subject_digest` 一张卡，同码同目标的 ① 与 ② 分别接受、撤销；理由必填（1–4096 UTF-8 字节）；没有批量接受或默认理由；接受请求的绑定字段全部取自同一次预检；冲突后只刷新、不自动重发；阻断项没有接受入口；开始归档的引用来自最新预检、不分页、不截断（399 项用例）。
> 2. **关闭：** 入口位置按 Q16 的决定；对话框文案与 §16.6 一致；201 与 200 回放都显示服务器返回的首次关闭人、时间与理由；关闭后自动重新预检；`expected_review_version` 取自同一次候选读取中目标候选的 `review_version`（§16.6），没有写死、推断、读取 Review 或追加审核权限。
> 3. **审核顶栏：** 过期通过的 409 与 `ARCHIVE_CLOSED` 按 §16.7。
> 4. **模拟数据：** 符合 §16.8 的可达组合；错误码单测覆盖关闭路由与归档新码。
> 5. **真实旅程与 t1：** J1、J2 各步的断言；每次预检的异常集合与 §4.6 的表（或经设计会话校正后的表）一致；t1 按 §8.3 由程序判定，两个比较对按 `pair_id`；复核 M1 数据（按 Q20：t1 只作回归对照；打包代码有改动时核对 t4 重测）。
> 6. **探针（用已提交的一次性 worktree）：**
>    - （07）把同码同目标的两张卡按 `issue_code` 合并：V2 应失败；
>    - （07）让接受后的卡显示为“通过”：V3 应失败；
>    - （07）开始归档时只发送界面上可见的前 50 项引用：V6 应失败；
>    - （07）预检请求改回转发整个候选对象（含 `review_version`）：V14 应失败；
>    - （07）关闭请求的 `expected_review_version` 改用 Review 或工作区的版本号：V9 应失败；
>    - （05，会话名 `fe3c-review`）关闭请求不带 `Idempotency-Key` 重试：J2 第 4 步应失败。
> 7. **运行：** 在 07 上独立运行一次 `run-tests.sh --e2e --screenshots`，在 05 上独立运行一次 `--suite journeys`。t1 不要求审核会话重跑，只核对日志与参考截图的 SHA256。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3c-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明 04 取证项与 05 的 t1 证据运行（本文 §9 FE3c 行），取证后做证据核对，并给出 FE3 退出建议。

## 14. 不在 FE3 范围

- BE-b 的分组、列展示、Preview 改前公式与行定位产物（FE4）。
- 首批空基线（FE2 kickoff Q18）。
- Preview 顶栏的上传快捷入口、历史比较结果抽屉布局、1280 下提交对话框滚动：已接受为 FE2 的偏差（FE2 kickoff Q19），FE3 不再处理。
- 浏览器中重新解析 SQL、计算来源图或生成时间；以上传时间代替生成时间。
- 正式 SSO、部署形态、外部驱动通道、深色主题。

## 15. kickoff 审核与定向复审意见的处理（`920f068da4`、`e91d9db6eb`）

| 意见 | 处理 | 位置 |
| --- | --- | --- |
| B1 t1 表数与对照 | 改为从同一 vnext 树读取预期值，核对四个汇总数 | §8.3 |
| B2 冒烟走不到的两项与判据 | 删去归档候选界面（移入“要等 BE-d”）；403 限于上传与 Preview；写明 Preview 结果的判据 | §3.3 |
| B3 R10、R5 | R10 改为四项，新增无 Preview 权限的身份，提交 403 只由模拟接口覆盖；R5 回放状态码按 route | §4.6、§4.7 |
| B4 提交失败后的指针 | 按 attempt 状态处理，增加“结果待确认”；URL 中操作的类型按 `job_kind`；写明续做卡片位置；模拟场景补充 | §6.1、§6.2、§5.3 |
| N1 05 的 npm 缓存 | 改正路径，新脚本使用同样的变量 | §2.2、§4.1 |
| N2 tar 前提 | 写明前端的前提，交 BE-d 确认（D1） | §2.1、§2.3、§12 |
| N3 RS 构建 | 核对 RS 依赖镜像、禁网、全部 `up --no-build` | §4.3、§4.4 |
| N4 依赖镜像传输 | 按 AGENTS 的 `--save` 流程；FE3b 按 `--print-input` 核对 | §4.3 |
| N5 身份记录的比例化 | 每次运行记录 label、image ID 与层；config digest 与 DiffID 在传输时比较 | §4.3 |
| N6 项目名小写 | 写明 | §4.4 |
| N7 工具链容器 | 固定名称与 label，清理时先删，残留检查包括它 | §4.2、§4.5、§4.8 |
| N8 每个身份一个 context | 写明，含 OPFS 隔离 | §4.5 |
| N9 trace 中的 token、t1 截图 | 改正说法，t1 截图只留在节点上 | §4.4、§4.9、§8.3 |
| N10 OpenAPI 经代理读取 | 写明 | §5.2 |
| N11 身份文件、`actor_id`、多 scope 播种 | 写明 | §4.6 |
| N12 上传输入 | `logics.xml` 移到文件；上传序列；replacement 输入；05 上先走一遍 | §4.6 |
| N13 Python 规范化 | 写明，固定 `ensure_ascii=True` | §5.1 |
| N14 生产构建检查、占用时禁用提交 | ① 补入 §5.3；② 补入 §6.1；上传是否禁用按 D2 处理（§11 Q9） | §5.3、§6.1 |
| N15 REJECTED/WITHDRAWN 两行 | 先重新读取工作区，再按新状态显示；模拟场景按竞争构造 | §6.1、§6.3 |
| N16 W5 两个 context、探针前提 | 写入 W5 与 13.4 | §6.3、§13.4 |
| N17 t1 步骤与后端的关系 | 改为“按主线顺序，省略 repeat-v1，历史比较用三节点” | §8.2 |
| N18 传输执行者与只读挂载 | 写明由 FE3a 实施会话执行，只读 bind mount | §8.1 |
| N19 M1 方法 | 补 FULL、全部进程、`clear_refs`、包大小与打包耗时的取法 | §8.4 |
| N20 t1 证据的时点 | 写明调试与证据的区别 | §9 |
| N21 / O1 | owner 决定：M1 测完才能退出 FE3a | §3.2、§11 Q8 |
| N22 路径核对 | 改为树相等加路径白名单，每个子阶段都做 | §3.2 |
| N23 占用用词与会话名 | 改正，规定会话名 | §4.2 |
| N24 AGENTS 条文 | FE3a handoff 写出建议条文 | §4.1、§12 |
| N25 `flock -n` | 写明 | §4.2 |
| D2 占用时禁用上传 | 设计会话建议禁用，owner 2026-11-05 确认 | §6.1、§11 Q9 |
| 复审 R1 M1 的测量时点 | 在送审候选上测量；打包代码改动后重测 | §9（FE3a） |
| 复审 R2 Preview 页续做卡片的位置 | 改为“顶栏之上” | §6.2 |
| 复审 R3 `composite_changed` 的来源 | 写明前端与后端 t1 的来源不同，派生表只在有对照时核对 | §8.3 |
| 复审 R4 `MANUAL_RECOVERY_REQUIRED` 的归类 | 并入“提交结果待确认”，两张表都分开写 | §6.1 |
| 复审 §2.2 占用绑定适用于通过与退回 | 补入 | §6.1 |
| 复审 §4 基线已前移的已通过提交 | 交后端设计会话；§6.1 增加暂定的一行；列为 FE3b 前置条件。2026-11-07 修订 2 按 DC89 删除暂定行（§15.2） | §2.1、§6.1、§12 |
| 复审 N1 补充 | 写明 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT` | §2.2 |

### 15.1 FE3a 审核中交设计会话事项的处理（`a0b9604ddd`）

| 意见 | 处理 | 位置 |
| --- | --- | --- |
| §6、B10 真实 e2e 的上传输入 | 补记 owner 当时的决定；写明分开的理由、派生规则与目录、`logics.xml` 配对、A–D 四类上传及其规范变化、FE3a 的核对与判据、留给后续的项 | §4.6、§11 Q10 |
| N2 基线序号 | 甲：树也显示“归档基线 n”，与摘要共用同一个标签函数，在 FE3a 做 | §7 M7、§11 Q11 |
| §5 M1 的判定 | 只看 renderer；浏览器主进程只报告，复测时补记 RSS 拆分 | §8.4、§11 Q12 |
| B7 续做读取失败后“提交”是否保持禁用 | FE3a 恢复了 FE2c 行为。FE3b 改为基于指针后，由 §6.2 的续做规则统一（§11 Q14） | §6.2、§11 Q14 |
| N6 AGENTS 建议条文 | 不在设计会话范围，由 owner 转治理会话 | §12 |

### 15.2 FE3b 前置条件核对的处理（修订 2，2026-11-07）

依据核对报告（`5dde965a65` 的 §3.3、§6、§8；`80e74d116c` 的 §9、§10）。“第 2 步”指本文第 2 步修订（FE3c 设计）。

**§3.3 对 kickoff 的影响：**

| 核对报告位置 | 处理 | 位置 |
| --- | --- | --- |
| §1、§3.2、§13.3 范围 | 按 owner 决定拆成 FE3b、FE3c；目标补入新交付；FE3b 提示词并入草案 | §1、§3.1、§3.2、§11 Q13、§13.3 |
| §2.1、§2.2 旧事实 | 按核对报告 §1、§4、§9 更新；07 并入节点表 | §2.1、§2.2 |
| §2.3 未覆盖新变化 | 重写为 18 行，补关闭、业务核验、`submission_disposition`、`pending_submission_ids`、引用上限、review-events 新码、tar 接收修复与同字节互通，并标出子阶段 | §2.3 |
| §4.6“留给 FE3b” | 改为“留给 FE3c”；FE3b 只用不需要归档的上传；每步预期的业务核验异常在第 2 步写出 | §4.6；第 2 步 |
| §4.7 R6 依赖退回修改 | 改为 `REJECT` → 重提 → 通过；关闭出口另设 R12（FE3c） | §4.7 |
| §4.7 R8 场景不足 | R8 归 FE3c，第 2 步扩充 | §4.7；第 2 步 |
| §5.3 同步规则 | 补 `submission_disposition` 改名与可达组合、新 schema 的形状、新错误码、action 映射；删除退回映射 | §5.3 |
| §6.1、§6.3 暂定行与用词 | 删除暂定行；“已退回”按 FD4 保留，`ComparisonPage` 的“已拒绝”统一为“已退回”；§6.3 补 W9、W10 | §5.3、§6.1、§6.3 |
| §6.2、§7 n3 与“指针为准” | 写定续做失败规则，交 owner 决定 | §6.2、§7、§11 Q14 |
| §8.2 t1 只有 MODIFIED_ONLY | t1 归 FE3c；FULL 等调整在第 2 步 | §8；第 2 步 |
| §12 两个开放项 | 标为已关闭 | §12 |

**§6 带入事项：**

| # | 事项 | 处理 | 位置 |
| --- | --- | --- | --- |
| 1 | §4.6 留下的 B FULL、C、D 与 `NO_CANONICAL_CHANGE` 的核对；FULL 的上传方式断言 | 前者归 FE3c；FULL 恰好两个比较对的断言在 FE3b R2 | §4.6、§4.7 R2 |
| 2 | M1 复测 | 归 FE3c，方法不变 | §8.4 |
| 3 | 本人撤回身份补权限；n3 改为基于指针 | FE3b | §4.6、§6.2、§7 |
| 4 | 复审非阻塞项 N1、N2、N5、N8 | N1、N2、N5 进入 FE3b；N8 不改（§12） | §4.7、§12、§13.3 |
| 5 | `journeys`、`t1`、`--input-root` 的实现；删除下载失败判据 | `journeys` 与判据在 FE3b，`t1` 在 FE3c | §3.3、§4.1、§4.7 |
| 6 | 04 退出条件包含上传包后端校验 | FE3b、FE3c 两行都写明 | §3.2、§9 |
| 7 | FE3a handoff 勘误不再沿用 | 写入 §3.2 与提示词 | §3.2、§13.3 |
| 8 | main 上的前端提交 `55d56efb6e` | 列为前端审核范围的例外 | §3.2、§13.3、§13.4 |
| 9 | 节点分工 07/05/04 | 写入 | §2.2、§4.2、§9 |
| 10 | AGENTS 条文未写入 | 仍为开放项 | §12 |

**§8 修订建议：**

| 核对报告位置 | 处理 | 位置 |
| --- | --- | --- |
| §8.1 第 1 项：合成输入没有生成时间 | 第 1 步只写明派生规则不补 `saved_time`；是否补、每步预期异常与实测校正在第 2 步，并作为新 Q 交 owner | §4.6；第 2 步 |
| §8.1 第 2 项：`NOT_CANDIDATE_BASE_ADVANCED` | 采纳：删除暂定行；处置优先，标记只作说明（后端已澄清，`20d3b885f6`） | §2.3、§6.1、§6.4 |
| §8.1 第 3 项：n3 与指针 | 采纳建议的规则，交 owner 决定 | §6.2、§11 Q14 |
| §8.2 拆段 | owner 已决定，补记 | §3、§11 Q13 |
| §8.3 §2.1–§2.3 | 采纳 | §2 |
| §8.3 R6 | 采纳 | §4.7 |
| §8.3 关闭旅程、关闭入口、R8 | 第 2 步 | §4.7 R12、§16 |
| §8.3 §5.3 | 采纳 | §5.3 |
| §8.3 §6.1 | 采纳；“已退回”保留 | §5.3、§6.1 |
| §8.3 §8 t1 改 FULL | 第 2 步，作为新 Q 交 owner | 第 2 步 |
| §8.3 tar/PAX 预算 | 后端已给出数值（`20d3b885f6`），采纳 8 MiB / 16 MiB；另定 fixture 原样提交 | §5.5 |
| §8.3 §4.2、§9 节点与截图 | 采纳；FE3c 截图在第 2 步 | §4.2、§9 |
| §8.3 §13.3 | 并入；起点合入含 `p6-be-a-d-exit` 的 main（2026-11-08 按修订 2 审核 B1 定为 `748de5034d`，§15.4） | §13.3 |
| §8.4 阻塞项 | 后端退出与两项澄清已完成（核对报告 §9） | §2.1 |
| §9 后续核对 | 采纳全部事实 | §2.1、§2.2 |
| §10 提示词草案 | 并入 §13.3，按修订后的章节编号整理；W 场景扩到 W10，补 D1–D5、REJECT 用词、归档 action 映射与 fixture 路径 | §13.3 |

核对报告 §5（推送状态）与 §7（还差的条件）是状态记录，不需要修订 kickoff。

### 15.3 第 2 步：FE3c 设计中对核对报告与后端交接的处理（修订 2，2026-11-07）

| 来源 | 处理 | 位置 |
| --- | --- | --- |
| 核对报告 §8.1 第 1 项：合成输入没有生成时间 | 建议不补（Q15）；写出 J1、J2 每次预检的预期异常；FE3c 05 调试首轮实测校正，不符即停。**改正：** 按源码，归档 A 也有一项 `GENERATION_TIME_MISSING`（核对报告推断为无） | §4.6、§11 Q15 |
| 核对报告 §3.3、§8.3：R8 场景不足 | R8 扩为 J1：独立项接受、撤销与服务器拒绝，待审核阻塞与草稿，身份例外 | §4.6 J1、§4.7 |
| 核对报告 §8.3：新增关闭旅程 | R12 按 J2；另用输入 E 证明“关闭后来源变为未解释” | §4.6 J2、§4.7 |
| 核对报告 §8.3：关闭入口 | 建议放在归档主线对话框的“候选提交”一节（Q16），文字规格与线框 | §16.6、§11 Q16 |
| 核对报告 §8.3：§8 t1 改 FULL；M1 复测指标 | 建议采纳（Q17）；两个比较对按 `pair_id` 核对；M1 复测含 FULL 与 RSS 拆分 | §8、§11 Q17 |
| 核对报告 §8.3：FE3c 截图清单 | 写入 | §9 |
| FE3b 评估交接 §4.1：原始诊断与处理状态分开、三个新 action、按 `subject_digest` 独立、理由必填、刷新不重发、不可豁免项无入口、引用上限 | 写入 | §16.3–§16.5 |
| FE3b 评估交接 §4.2、V2 交接 §2：关闭的 201/200、首次操作者、释放工作区、其余候选可能变为未解释 | 写入；关闭请求的 `expected_review_version` 来源不可得，交后端 | §16.6、§11 Q18 |
| FE3b 评估交接 §3：待审核阻塞、过期 `APPROVE` 409 | 待审核阻塞写入 §16.5 并在 J1 真实覆盖；过期 `APPROVE` 在单 scope 正常操作中走不到，只由模拟接口覆盖，说明见 §16.7 | §16.5、§16.7 |
| 新界面是否画草图 | 建议不另画，用文字规格与线框（Q19） | §16.2、§11 Q19 |
| 前端审核用的提示词 | FE3c 实施与审核 | §13.5、§13.6 |

### 15.4 修订 2 审核意见的处理（2026-11-08）

依据 [修订 2 审核](reviews/fe3-kickoff-rev2-review.md)（`d076903d7f`）与 owner 答复（同报告 §6，`244a24b811`）。第 1 步在 `dfdcd00b90`，第 2 步在其后的提交。

| # | 意见 | 处理 | 位置 |
| --- | --- | --- | --- |
| B1 | 当前 main 的 `vnext/` 已因 S3 改变，依赖镜像需 `lock-ca0ba0a24a5e` | owner 选甲：FE3b 合入 `748de5034d`，期间不再合入 main；FE3c 合入当时的 main 并预填充新依赖镜像 | §2.1、§2.2、§3.2、§4.3、§5.1、§10、§13.3 |
| B2 | PAX key 白名单与 `adjacent_records` 冲突 | 采纳推荐：记录切分层与成员层分开；`adjacent_records` 切分层接受、成员层拒绝 | §5.5、§13.3 |
| B3 ① | 已关闭提交仍可进入归档主线；旧“不能归档”文案 | §6.4 补“归档主线”按处置禁用、D5 的原因；点名 `workspace.ts`、`workspace.test.ts`、`WorkbenchPage.tsx` 的位置；D1–D5 补断言 | §6.4、§13.3 |
| B3 ② | `gateway-submit-operation` 清单不全 | 补 `WorkbenchPage.tsx` 四处与 e2e 两处 | §6.2 |
| B3 ③ | action 映射只点名 `anomalyAction` | 补 `journeys.ts:374` 类型（改用生成类型）、`mock-data.ts` 审计事件三张取值表、两处 `blockers` 加 `ARCHIVE_PENDING_REVIEW` | §5.3 |
| B3 ④ | e2e 中的“已拒绝”断言 | 点名 `e2e/workspace-shell.spec.ts:1248` | §5.3 |
| B3 ⑤ | D5 与“只构造可达组合”冲突；`mock-data.ts:120` | D5 写成唯一的防御性例外；`:120` 改为可达形态或改标为 D5 数据 | §5.3、§6.4 |
| N1 | §13.3 先读补 testing-conventions「真实 backend e2e」 | 采纳 | §13.3 |
| N2 | §15.2 补核对报告 §5、§7 的说明 | 采纳 | §15.2 |
| N3 | R10 ④ 需要已通过的提交节点 | 采纳 | §4.7 |
| N4 | `client.test.ts` 没有对应用例 | 改为点名 `client.ts` 两处，生成类型随刷新消失 | §5.3 |
| Q14 | owner 同意建议 | 标为已决定 | §11 |
| C1 | t1 上的 M1 线性外推会误判超标 | t1 只报告并作回归对照（FE3a t1 的 2 倍）；超标判断只用 t4；打包代码改动时在 05 重测 t4。改变判定口径，交 owner（Q20） | §8.4、§11 Q20 |
| C2 | 关闭理由缺 4096 字节上限 | §16.6 补上限、禁用原因与计数；§2.3 第 14 行改为 1–4096 UTF-8 字节；V9 补边界 | §2.3、§16.6、§16.9 |
| C3 | 实测校正的比较口径 | 写明用带 `selected` 的预检；`issues` 与去掉同级、身份两类后的表比较，`anomalies` 与全表比较 | §4.6 |
| N5 | J2 第 5 步“回到未处理”的原因 | 改为全部 subject 随候选集重新派生 | §4.6 J2、§16.9 V10 |
| N6 | J1 第 9 步的 409 码 | 写定 `ARCHIVE_ANOMALY_UNRESOLVED` | §4.6 J1 |
| N7 | V6 的构造；`ARCHIVE_SCOPE_LIMIT_EXCEEDED` | 写明可达的构造；该码给专用文案“候选提交超过归档上限，需要管理员处理” | §16.5、§16.9 |
| N8 | FE3c 的比对原件与依赖镜像 | §5.1、§10 注明 FE3c 按 §13.5（第 1 步已改）；§4.3 写明预填充（第 1 步已改）；§13.5 的 tag 改为审核会话填写的占位 | §4.3、§5.1、§10、§13.5 |

### 15.5 修订 3（2026-11-09）

依据：owner 2026-11-09 的决定；[Q18 交接](../backend-vnext/refactoring/formal/plans/p6-be-q18-handoff.md)（最终产品 `94b25a3279`，独审 GO）；`fe-fe3b-exit` 的 `frontend/` 源码；`56720104af..6368c9c40c` 的后端差异；修订 2 定向复核第 1 轮的 E1、R1。

| # | 事项 | 处理 | 位置 |
| --- | --- | --- | --- |
| 1 | owner 确认 Q15–Q20 | 全部按 §11 的建议确认；改状态行与 §11 表，§3.2、§12、§16.6 入口中的“待 owner 决定”“建议”随之改为已决定 | 文首状态、§3.2、§11、§12、§16.6 |
| 2 | FE3c 合入点 | 合入 main `fd9e383d76`（`vnext/` 树 `6368c9c40c`，与 `p6-s4-exit` 相同，含 S3、S4 退出与 Q18），不再写“合入当时的 main”；写明理由与审核会话的试合并结果（无冲突，`frontend/` 树仍为 `54b5a333c6`）；FE3c 期间按需重新合入，重新合入时交审核会话重核镜像与原件；FE3c 的路径核对以 `fd9e383d76` 为 `<main>` | 文首起点、§2.1、§3.2、§13.5 |
| 3 | §16.6 定稿 | `expected_review_version` 取自打开关闭对话框时同一次候选读取中目标候选的 `review_version`；不在其他读取间混用；409 `REVIEW_VERSION_CONFLICT` 按“结果”重新预检；不增加审核权限；删去“来源待定”。另写明“一次加载”的候选读取与预检必须 `candidate_set_digest` 相同，第 4 节只列该次候选读取中的提交 | §16.2、§16.6、§4.6 J2 第 4 步、§4.7 R12 |
| 4 | `selected` 只含两个字段 | §2.3 新增第 19 行；§16.2 写明规则与现有构造位置（`ArchiveMainlineDialog.tsx:87` 转发整个候选，Q18 后会被拒，`:133` 与 `journeys.ts` 五处转发），要求用一个函数显式取两个字段；§16.4、§16.5 引用该规则 | §2.3、§16.2、§16.4、§16.5、§13.5 |
| 5 | §5.3 模拟规则 | 候选补 `review_version`（取值与同场景 Review 一致，V9 用有区分力的值）；409 `REVIEW_VERSION_CONFLICT` 按竞争构造；路由桩对 `selected` 多出的键返回 422；关闭路由加入 `Idempotency-Key` 核对 | §5.3、§16.8 |
| 6 | §16.9 | V9 补“关闭请求携带的 `expected_review_version` 等于目标候选的 `review_version`”与“没有 Review 请求”；新增 V14：预检、确认、异常处置、开始归档请求中 `selected` 恰好两个键；删去“V9 随 Q18 定稿”的说明 | §16.9 |
| 7 | Q18 状态与停止条件 | §11 Q18 记交付事实并标为已交付；§12 原第 1002 行改为已交付，另加“FE3c 的生产 OpenAPI 原件”前置；§10 的停止条件改为“不能按 §16.6 取值，或需要追加权限、读取 Review、写死或推断”，并补 `selected` 两字段被拒的情形与 FE3c 的 tag、树 | §10、§11、§12 |
| 8 | §4.3 依赖镜像 | `--print-input` 得 `lock-578e079b762e`（输入 `578e079b…3ff5`），替换“预计 `lock-ca0ba0a24a5e`”；来源为后端 S3 已核收的预填充链，Q18 交接记录 config `sha256:46c00a3b…e939`；审核会话 2026-11-09 在 04、05 只读核对 label 与 19 个 DiffID，config digest 由运行时入口脚本再核；RS 依赖镜像仍为 `lock-6dc9659f0aee`；不需要新的预填充 | §2.2、§4.3、§13.5 |
| 9 | 其余后端变化的前端影响 | 按 bundle/manifest、比较与风险结果、错误码与上限默认值、诊断码四类核对：前三类已核，无前端可见变化（依据列在表中）；三个诊断码不再产生、四个新码可能出现，交 owner 转后端（新 Q21），不阻塞 FE3c | §2.3 末段、§11 Q21、§12 |
| 10 | 比对原件 | FE3c 用后端为 `vnext/` 树 `6368c9c40c` 补交的生产 OpenAPI，路径与 SHA256 由审核会话在发出提示词时填写；原件未交付前不发提示词；预期差异只有 `review_version` | §5.1、§5.2、§12、§13.5 |
| 11 | E1 | §5.5 与 §13.3 的“10 个文件”改为 9 个原件加 `SHA256SUMS` | §5.5、§13.3 |
| 12 | R1 | §16.5 括注改为：`ARCHIVE_SCOPE_LIMIT_EXCEEDED` 只在候选或待审核提交的读取超过上限时返回；请求中引用超过 maxItems 返回 422；异常数超过 8N+1 返回 503 `ARCHIVE_INTEGRITY_FAILURE`（已按 `6368c9c40c` 的 `application/archive/snapshot.py`、`contracts.py`、`queries.py` 核对） | §16.5 |
| 13 | 审核提示词 | §13.6 补 V14 与两个探针（预检转发整个候选、关闭用 Review 或工作区的版本号） | §13.6 |
| 14 | FE3c 生产 OpenAPI 原件交付（修订 3 追加） | 记录后端 2026-11-09 补交的原件（路径、SHA256 `ce58f20a…c079`、节点、worktree、起止 HEAD、取件方法与范围差别、日志 SHA256）；设计会话独立规范化核对：与 FE3b 原件只差 `review_version` 两处，FE3b 快照与 FE3b 原件规范化后相同。§12 该前置标为已交付；§13.5 的路径与 SHA256 仍由审核会话在发出时填入并重算 | 文首状态、依据、§2.1、§5.2、§12 |

## 16. FE3c：归档业务核验、有理由关闭与待审核阻塞

### 16.1 依据与原则

- 依据：V2 交接 §1–§3、FE3b 评估交接 §3–§4、归档业务核验设计 §4.2、§6、§7.1、§10、DC89、DC90，以及 §2.3 第 12–18 行。
- **事实以服务器为准：** 时间、来源、受影响集合与 subject 都由预检返回，前端不解析 SQL、不推导来源图、不用上传时间代替生成时间、不拆分或合并 subject（FE3b 评估交接 §4.1）。
- **原始诊断与人工处理分开：** 接受只表示“已由某人说明理由并接受”，不改为“通过”或“来源已匹配”。
- **逐项处理：** 每个 `subject_digest` 是一项，各自接受与撤销，理由必填；没有批量接受、全选或默认理由。
- **只刷新、不重发：** 预检结果变化、写请求冲突后，前端重新读取并显示新状态，不自动重发写请求（FE2 kickoff §6.2 的原则）。
- **不可豁免项没有入口：** 完整性失败、越权、事务冲突、进行中的提交、待审核阻塞，界面上没有“填写理由继续”的入口（DC90）。
- 文案按 FE2 kickoff §4 的原则：只说原因，原始码（`issue_code`、`subject_kind`、`subject_digest`、枚举值）放悬停提示与 Debug（C6）。
- 新界面都在现有的归档主线对话框（`ArchiveMainlineDialog.tsx`）与审核模式顶栏中，沿用现有令牌与组件；没有新增页面。

### 16.2 归档主线对话框的结构

入口不变：组态树中已通过的提交节点（FE2c）。对话框从上到下分为六节，打开时先读候选、再预检（现有 `load`）。

```text
┌ 归档主基线 ───────────────────────────────────────────────────────────────┐
│ 1 预检状态   当前基线：归档基线 1（版本 1）   选中：提交 2                     │
│   ┌ 阻断项 ────────────────────────────────────────────────────────────┐  │
│   │ 有 1 个待审核的提交，审核通过、退回或撤回后才能归档：提交 3            │  │
│   │ 只有上传或预览、尚未提交的工作区不影响归档。          [重新预检]      │  │
│   └────────────────────────────────────────────────────────────────────┘  │
│ 2 归档选择确认   ☐ 确认把“提交 2”归档为新的业务基线                          │
│ 3 业务核验                                                                  │
│   核验概况（表）：提交 │ 原始组态来源 │ 生成时间比较                          │
│   待处理项   未处理 2 ／ 共 3                                                 │
│   ▾ 生成时间（2）                                                            │
│     ┌ 提交 2 · ①原始组态备份 ─────────────────────────────────────────┐    │
│     │ 缺少组态生成时间  [原始诊断：已发现]  [处理：未处理]      [接受]   │    │
│     │ version_manager 表没有 saved_time 列                              │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│     ┌ 提交 2 · ②本次归档组态 ─────────────────────────────────────────┐    │
│     │ 缺少组态生成时间  [原始诊断：已发现]  [处理：已接受]   [撤销接受]  │    │
│     │ 已由 archiver-1 于 11-07 15:20 接受：现场旧版本没有写入生成时间     │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│   ▾ 基线时间（1） …                                                          │
│ 4 候选提交                                                                  │
│     提交 2（选中）   已通过                              [关闭（不归档）]    │
│     提交 4           已通过                              [关闭（不归档）]    │
│ 5 确认后的影响   …                                                          │
│                              [重新预检]  [确认归档]（禁用：还有 2 项未处理）  │
└────────────────────────────────────────────────────────────────────────────┘
```

- 提交一律用组态树的显示名（“提交 n”，§7 M7 的标签函数），找不到时才显示 ID；ID 放悬停提示。
- 对话框内容较多，正文区域滚动，标题与底部按钮固定（沿用 `Dialog` 组件）。1280 宽度下卡片单列，1920 下同样单列，不并排。
- 第 4 节“候选提交”在有阻断项时仍显示（关闭不要求先解除阻断，V2 交接 §2）；预检读取失败时不显示。
- **一次加载 = 一次候选读取 + 一次预检：** 两者的 `candidate_set_digest` 必须相同，不同即作废该次加载并重新加载，不把候选与预检拼自不同的快照。§16.4–§16.6 所说的“同一次预检”“同一次候选读取”都指同一次加载。

**选择引用 `selected` 的构造（修订 3，Q18；§2.3 第 19 行）：**

- 预检、确认、异常处置、开始归档四个请求的 `selected` 每项恰好两个键：`submission_id` 与 `expected_candidate_digest`。后端 `ArchiveSelectedRefRequest` 为 `extra="forbid"`，多出的键返回 422。
- Q18 之后候选读取对象（`ArchiveCandidateResponse`）多了 `review_version`，**不能把候选对象或预检响应中的对象整个传进 `selected`**，也不用展开（`...candidate`）。实现时用一个函数显式取这两个字段构造选择引用，全部请求都用它的结果；生成类型拦不住这类错误（§5.3）。
- 前端现在构造或转发 `selected` 的位置（`fe-fe3b-exit` 的 `frontend/src/`）：

  | 位置 | 现状 | FE3c |
  | --- | --- | --- |
  | `features/workbench/ArchiveMainlineDialog.tsx:87` | `previewArchive({ selected: candidate })`：把 `listArchiveCandidates()` 返回的候选对象整个转发。Q18 后会带上 `review_version`，真实 backend 返回 422（J1 第 2 步即失败） | 改为显式取两个字段 |
  | `features/workbench/ArchiveMainlineDialog.tsx:133` | 构造 `{ submission_id: submissionId, expected_candidate_digest: selectedDigest }` 交给 `runArchiveJourney` | 改用同一个构造函数 |
  | `features/api/journeys.ts:423`、`:478`（预检）、`:436`（确认）、`:462`（异常处置）、`:487`（开始归档） | 转发 `input.selected`（`:372` 类型为 `ArchiveSelectedRefRequest`），是否只有两个键取决于调用方 | 只转发构造函数的结果；`:448-477` 逐项追加异常接受的部分按 §16.5 删除；§16.4 的接受、撤销请求同样用构造函数的结果 |

- 模拟数据中的 `selected`（`dev/mock-data.ts:561`，`e2e/workspace-shell.spec.ts:446`、`:455`、`:462`）是预检**响应**里的选择引用，后端也只返回两个键，保持不变。

### 16.3 业务核验：核验概况与独立项

**核验概况（只读）：** 每个候选一行，来自 `business_validation.source_diagnostics` 与 `time_comparisons`。

| 列 | 内容 |
| --- | --- |
| 提交 | 显示名；选中项加“（选中）” |
| 原始组态来源 | `detected_status`：`EXPLAINED` “已解释”，并列出 `matching_sources`（“当前基线”或“提交 n 的 ①/②”）；`UNEXPLAINED` “未解释”；`NOT_APPLICABLE` “不适用（首次归档）”。`initial_origin` 为 `BASELINE_REUSED` 时加注“沿用当前基线（只上传了本次归档组态）”。`rules_identity_differs_from_baseline` 为真时加注“规则版本与当前基线不同” |
| 生成时间比较 | 每个 `relation` 一行：`MODIFIED_BEFORE_INITIAL` “② 与 ① 比较”、`MODIFIED_BEFORE_BASELINE` “② 与当前基线比较”、`INITIAL_BEFORE_BASELINE` “① 与当前基线比较”；结果 `NORMAL` “正常”、`BACKWARD` “倒退”、`NOT_COMPARABLE` “无法比较”、`NOT_APPLICABLE` “不适用”；附左右两个时间 |

- 时间按服务器返回的 UTC 值显示为 `YYYY-MM-DD HH:MM:SS[.ffffff] UTC`，不换算本地时区（比较是按 UTC 做的）。
- 概况只读，没有操作；需要处理的都在“待处理项”中。

**待处理项：** 来自 `anomalies`，每个 `subject_digest` 一张卡。按类别分组，组内按显示名、再按 ①、②、基线的顺序排列：

| 组 | `subject_kind` |
| --- | --- |
| 原始组态来源 | `CONFIGURATION_SOURCE` |
| 生成时间 | `CONFIGURATION_TIME_QUALITY`（不含 `BASELINE_TIME_UNAVAILABLE`） |
| 基线时间 | `CONFIGURATION_TIME_QUALITY` 中的 `BASELINE_TIME_UNAVAILABLE` |
| 生成时间先后 | `CONFIGURATION_TIME_ORDER` |
| 同级提交 | `APPROVED_SIBLING_EXCLUDED` |
| 项目身份 | `PROJECT_IDENTITY_EXCEPTION` |

- 组标题显示“未处理 n ／ 共 m”。有未处理项的组默认展开，全部已接受的组可以折叠；折叠只影响显示，不影响开始归档时发送的引用（§16.5）。
- **不分页、不截断：** 全部项都在列表中（上限 1601，§2.3 第 17 行）。项多时可用浏览器原生滚动；不使用“显示更多”隐藏项。

**卡片内容：**

- **标题行：** “{显示名} · {一侧}” 与问题文字。一侧：`INITIAL` “①原始组态备份”，`MODIFIED` “②本次归档组态”，`BASELINE` “当前基线”；没有 `side` 时省略。
- **两个状态标签，并排、分开：**
  - 原始诊断：`detected_status` 为 `UNEXPLAINED` 时“来源未解释”，为 `DETECTED` 时“已发现”；警示色调，接受后不变；
  - 处理状态：`UNRESOLVED` “未处理”（警示）；`ACCEPTED` “已接受”（中性，不用成功色，不出现“通过”“已解决”）；`REVOKED` “已撤销接受，需要重新处理”（警示）。
- **处理信息：** `ACCEPTED` 时一行“已由 {accepted_by} 于 {accepted_at} 接受：{reason}”；`REVOKED` 时一行“已撤销，原因：{reason}”。理由全文显示，超过 3 行折叠。
- **受影响提交：** `affected_submission_ids` 全部列出（显示名），不截断；`BASELINE_TIME_UNAVAILABLE` 与来源组通常有多个。
- **问题文字与详情：**

| `issue_code` | 问题文字 | 详情（按 `details` 的类型） |
| --- | --- | --- |
| `INITIAL_SOURCE_UNEXPLAINED` | 原始组态备份的来源无法解释 | “与当前基线及本轮已通过的提交都对不上，可能漏传了现场的改动。”列出组内全部提交（`edges`）及其 ①、② 的内容摘要前 12 位（悬停显示全文）；状态数（`states`） |
| `GENERATION_TIME_MISSING` | 缺少组态生成时间 | 按 `generated_time.status`：`TABLE_ABSENT` “SQL 中没有 version_manager 表”；`COLUMN_ABSENT` “version_manager 表没有 saved_time 列”；`NO_ROWS` “version_manager 表没有数据行”；`NO_VALUE` “saved_time 全部为空（{empty_count} 行）”；`NO_VALID_VALUE` “saved_time 没有可识别的时间（{invalid_count} 个无法识别）” |
| `GENERATION_TIME_INVALID_VALUES` | 生成时间中有无法识别的值 | “{invalid_count} 个值无法识别，采用最后一个有效值 {selected_time_utc}（第 {last_valid_source_row} 行）。” |
| `GENERATION_TIME_LAST_NOT_MAX` | 最后一个生成时间不是最大值 | “采用最后一个有效值 {selected_time_utc}（第 {last_valid_source_row} 行），最大值为 {max_valid_time_utc}（第 {max_valid_source_row} 行）。不会自动改用最大值。” |
| `TIME_ABNORMAL_MODIFIED` | 本次归档组态的生成时间早于对照 | 每个 `comparisons` 一行：“② {left} 早于 ① {right}”或“② {left} 早于当前基线 {right}” |
| `TIME_ABNORMAL_INITIAL` | 原始组态备份的生成时间早于当前基线 | “① {left} 早于当前基线 {right}” |
| `BASELINE_TIME_UNAVAILABLE` | 当前基线没有可用的生成时间，本轮无法比较时间先后 | 基线的 `generated_time` 状态（同 `GENERATION_TIME_MISSING` 的文字，为空时写“基线没有生成时间记录”）；“比较结果：无法比较” |
| `APPROVED_SIBLING_EXCLUDED` | 归档后该已通过的提交将被关闭（不归档） | 目标提交的显示名 |
| `PROJECT_IDENTITY_EXCEPTION` | 选中的提交有项目身份例外 | 沿用 FE2c 的身份说明 |
| 其他（新增的未知编码） | 显示原始编码 | 不提供“接受”，提示“当前版本不能处理该项，请刷新或联系管理员”，“确认归档”禁用 |

- 行号（`*_source_row`）是 SQL 中 `version_manager` 表数据行的源顺序，写作“第 n 行”，悬停说明“按 SQL 中出现的顺序计数，从 1 开始”。
- 详情中不显示 SQL 原文或私有路径（服务器也不返回）。

### 16.4 接受与撤销

- **按钮：** `UNRESOLVED`、`REVOKED` 的卡显示“接受”（次要按钮）；`ACCEPTED` 的卡显示“撤销接受”（次要按钮）。不提供多选。
- **接受对话框：**
  - 标题“接受异常”；正文重复卡片的标题行、问题文字与受影响提交；
  - 影响说明：“接受表示你已核对该问题并说明理由。原始诊断不会改为通过，接受记录会写入归档审计，可以撤销。”
  - 理由（必填）：多行文本；去掉首尾空白后为空、或超过 4096 个 UTF-8 字节时禁用“确认接受”，禁用原因分别为“请填写接受理由”“理由不能超过 4096 字节”；超过 3500 字节时显示字节计数；
  - 主按钮“确认接受”。
- **撤销对话框：** 标题“撤销接受”；影响说明“撤销后该项回到需要处理的状态，归档前需要重新接受”；理由必填（后端对撤销同样要求 1–4096 字节理由），规则同上；危险按钮“确认撤销”。
- **请求：** `POST /v1/archive-anomaly-resolutions`，每次打开对话框生成一个 `Idempotency-Key`。body 的全部绑定字段取自**同一次**预检，不由前端推导：
  - `expected_baseline_node_id`、`expected_baseline_head_version`（`head`）、`candidate_set_digest`；
  - `selected`：按 §16.2 只含 `submission_id`、`expected_candidate_digest` 两个键，由构造函数显式取得；
  - 该项的 `subject_digest`、`subject_kind`、`issue_code`、`target_submission_id`、`target_candidate_digest`；
  - `expected_sequence` = 该项的 `latest_sequence`；
  - `action`：接受按 §2.3 第 15 行的表由 `subject_kind` 决定（`APPROVED_SIBLING_EXCLUDED` → `ACKNOWLEDGE_EXCLUSION`，`PROJECT_IDENTITY_EXCEPTION` → `ACKNOWLEDGE_IDENTITY_EXCEPTION`，三类业务项见表），撤销为 `REVOKE`；
  - `reason`：用户输入的原文（不去空白、不改写）。
- **成功（201 或回放 200）：** 关闭对话框，重新读取候选并预检；卡片按新预检显示。
- **失败（对话框底部提示区）：**
  - 409 `BASELINE_VERSION_CONFLICT`、`CANDIDATE_SET_CONFLICT`、`CANDIDATE_BINDING_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`：“归档候选或核验结果已变化，已重新预检”，关闭对话框并重新预检，不重发；
    （后端在该项的 subject 已不在当前预检中时也返回 `BASELINE_VERSION_CONFLICT`，`application/archive/audit.py`）
  - 409 `IDEMPOTENCY_CONFLICT`：“本次操作与服务器记录不一致，请关闭对话框后重试”；
  - 403：“当前身份没有该操作的权限”；
  - 422：“理由或请求不符合要求”；413、429、503 与其他：通用文案“操作未完成”加错误码（C6）。
- **预检变化的提示：** 同一次打开对话框期间，新预检的 `candidate_set_digest` 与上一次不同时，在“业务核验”节顶部提示“候选集合已变化，之前的接受不再适用，请重新核对”（旧的 subject 由服务器重新派生，处理状态会回到“未处理”）。

### 16.5 开始归档、阻断项与待审核阻塞

**阻断项（`blockers`）：** 列在“预检状态”节，每项只有文字、错误码与“重新预检”，没有接受入口。

| 编码 | 文字 |
| --- | --- |
| `ARCHIVE_PENDING_REVIEW` | 见下文“待审核阻塞” |
| `ACTIVE_SUBMIT_ATTEMPT` | 已有提交正在处理，完成后才能归档 |
| `ARCHIVE_INTEGRITY_FAILURE` | 归档数据完整性校验未通过，不能继续，请联系管理员 |
| 其他 | 显示原始编码，“当前不能归档” |

**待审核阻塞：**

- 文字：“有 {pending_submission_count} 个待审核的提交，审核通过、退回或撤回后才能归档：”，随后列出 `pending_submission_ids` 的显示名（全部列出，不截断）；
- 附注：“只有上传或预览、尚未提交的工作区不影响归档。”
- 每个名字可点击：关闭对话框并在组态树中选中该节点，便于审核人打开审核模式（前端不判断当前身份能否审核）。

**“确认归档”的禁用原因（按顺序判断）：**

1. 正在预检：“正在预检”；预检失败：沿用现有文案；
2. 有阻断项：“当前预检存在阻断项”；
3. 有未处理或已撤销的项：“还有 {n} 项异常未处理”；有无法处理的未知编码：“存在当前版本不能处理的项”；
4. 需要选择确认而未勾选：“请确认归档选择”；
5. 正在归档：按钮文字“归档中…”。

**开始归档：**

- 选择确认沿用 FE2c：勾选后在开始归档时追加 `CONFIRM`（`runArchiveJourney`），得到确认引用（上限 1）。确认与开始归档请求的 `selected` 按 §16.2 只含两个键。
- 异常不再在开始归档时追加：全部项已在 §16.4 中逐项接受。`anomaly_resolution_refs` 取**最新一次预检**中全部 `ACCEPTED` 项的 `{subject_digest, sequence = latest_sequence}`，一项不漏，不按界面是否展开或可见筛选，不分页。
- `runArchiveJourney` 中逐项追加异常接受的部分随之删除（AGENTS：删除被替代的实现）。
- **失败：**
  - 409 `ARCHIVE_ANOMALY_UNRESOLVED`、`ARCHIVE_CONFIRMATION_REQUIRED`、`ARCHIVE_AUDIT_VERSION_CONFLICT`、`CANDIDATE_SET_CONFLICT`、`CANDIDATE_BINDING_CONFLICT`、`BASELINE_VERSION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT`：“归档候选或核验结果已变化，请重新预检”，附“重新预检”；不自动重发；
  - 409 `ARCHIVE_PENDING_REVIEW`：“出现了新的待审核提交，请重新预检”，附“重新预检”；
  - 409 `ACTIVE_SUBMIT_ATTEMPT`：“已有提交正在处理，完成后才能归档”；
  - 409 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`（只在候选或待审核提交的读取超过上限时返回；请求中引用超过 maxItems 返回 422；异常数超过 8N+1 返回 503 `ARCHIVE_INTEGRITY_FAILURE`）：“候选提交超过归档上限，需要管理员处理”，附错误码；不自动重试；
  - 其他沿用 FE2c（403、`IDEMPOTENCY_CONFLICT` 等）。
- **成功：** 沿用 FE2c 的结果页；“处理结果”按 `dispositions`（`SubmissionDispositionResponse`）计数“归档 n 项，关闭 m 项”。

### 16.6 有理由关闭（不归档）

**入口（§11 Q16 甲，owner 2026-11-09 确认）：** 归档主线对话框第 4 节“候选提交”，列出同一次加载中候选读取的全部提交（与预检的候选集合相同；显示名、审核状态“已通过”），每行一个“关闭（不归档）”（危险样式的次要按钮）。选中项也可以关闭。不在组态树工具栏、提交人或审核人的顶栏放入口。

**关闭对话框：**

- 标题“关闭提交（不归档）”；正文写出目标的显示名。
- 影响说明（逐条）：
  - 该提交保留“已通过”的审核记录，标记为“已关闭（未归档）”，不会成为基线；
  - 提交人的工作区被释放，当前上传与预览被清空，需要重新上传、预览并提交；
  - 当前基线不变；
  - 关闭后其余候选的核验结果可能变化，需要重新处理；
  - 关闭不可撤销。
- 关闭理由（必填）：多行文本；去掉首尾空白后为空、或超过 4096 个 UTF-8 字节时禁用“确认关闭”，禁用原因分别为“请填写关闭理由”“理由不能超过 4096 字节”；超过 3500 字节时显示字节计数（同 §16.4；后端 `validate_utf8_reason` 对关闭同样要求 1–4096 字节）。请求发送用户输入的原文；
- 确认勾选“我已了解关闭不可撤销”；
- 危险按钮“确认关闭”。

**请求：** `POST /v1/submissions/{submission_id}/closure`，每次打开对话框生成一个 `Idempotency-Key`，网络错误重试用同一 key（R12 的中断重试）。body：

- `expected_baseline_node_id`、`expected_baseline_head_version`：取自同一次预检的 `head`；
- `reason`：用户输入的原文；
- `expected_review_version`（修订 3 定稿，Q18 交付 `94b25a3279`，§2.3 第 19 行）：取自**打开关闭对话框时**，同一次加载（§16.2）的候选读取中目标候选（`candidates[]` 中 `submission_id` 等于目标的那一项）的 `review_version`。
  - 与同一次加载的预检 `head` 一起在打开对话框时固定；网络错误重试用同一 key 与同一 body，不重新取值；
  - **不在其他读取间混用：** 不取 Review GET、History 或另一次候选读取（更早或更晚）中的值；
  - 409 `REVIEW_VERSION_CONFLICT` 按下文“结果”关闭对话框并重新预检（重新加载候选与预检），不自动重发；用户再次打开关闭对话框时取新加载中的值；
  - **不增加审核权限：** 归档确认人只持 `archive_submission`（§4.6），不调用 `GET .../review`，也不要求另持 `review_submission`；
  - 不写死、不推断；该字段只用于关闭请求，不放进 `selected` 或其他归档请求（§16.2）。

**结果：**

- 201 或 200（回放）：对话框显示“已关闭”，并显示**服务器返回的** `closed_by`、`closed_at`、`reason`（回放时是首次操作者的信息，不是当前身份）；随后重新读取候选并预检，组态树刷新（被关闭的节点按 §6.4 显示）。
- 409：
  - `BASELINE_VERSION_CONFLICT`、`REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT`：“提交或基线已变化，已重新预检”，关闭对话框并重新预检，不重发；
  - `ARCHIVE_CLOSED`：“该提交已归档或关闭”，重新预检；
  - `IDEMPOTENCY_CONFLICT`：“本次操作与服务器记录不一致，请关闭对话框后重试”。
- 403：“当前身份没有该操作的权限”；404：“未找到该提交，请重新预检”；422：“理由或请求不符合要求”；413、429、503 与其他：通用文案“关闭未完成”加错误码。
- 关闭后不自动接受、不自动关闭其他提交（V2 交接 §2）。

### 16.7 审核模式顶栏：过期通过与已处置

- **`APPROVE` 返回 409 `BASELINE_VERSION_CONFLICT`：**
  - 提示“该提交所基于的基线已更新，不能通过。可以退回，或由提交人撤回后基于当前基线重新提交。”加错误码；
  - 重新读取 review 与 History；本页面内“通过”禁用，原因“该提交所基于的基线已更新，不能通过”；“退回”“撤回”照常可用；
  - 前端不在请求前按 History 推断“过期”而预先禁用（动作以服务器资格为准，FE3b 评估交接 §3）。
  - **真实 backend 上走不到：** 待审核会阻塞归档（DC89），进行中的提交也阻塞归档，单个 scope 中不会出现“基线已前移、提交仍待审核”的状态；该 409 是后端在并发下的防护。只由模拟接口覆盖，handoff 说明。
- **任一审核动作返回 409 `ARCHIVE_CLOSED`：** 提示“该提交已归档或关闭，已重新读取”，重新读取后按 §6.4 显示处置与禁用原因。

### 16.8 模拟数据与错误码

按 FE2 kickoff §7.5 的规则，只构造后端可达的组合，并在模拟数据单测中断言（依据写在场景注释中）：

- `detected_status`：`CONFIGURATION_SOURCE` 为 `UNEXPLAINED`，其余为 `DETECTED`（`queries.py:424`）；
- `resolution_status`（`queries.py:540-552`）：`UNRESOLVED` ⇒ `latest_sequence = 0`，`accepted_by`、`accepted_at`、`reason` 为空；`ACCEPTED` ⇒ 三者非空；`REVOKED` ⇒ `accepted_by`、`accepted_at` 为空，`reason` 为撤销理由，`latest_sequence ≥ 2`；
- `side`：来源项为 `INITIAL`；`BASELINE_TIME_UNAVAILABLE` 为 `BASELINE`；其余时间项为 `INITIAL` 或 `MODIFIED`；MODIFIED_ONLY 的候选只有 `MODIFIED` 侧的时间质量项；
- `details` 的类型与 `issue_code` 对应（闭合 union）；`BASELINE_TIME_UNAVAILABLE` 的受影响集合为全部候选；每个未选中候选一项同级排除；数量不超过 8N+1（归档业务核验设计 §7.1）；
- 基线为空 `INITIAL` 时没有来源项与基线时间项，来源为 `NOT_APPLICABLE`；
- 关闭响应：`disposition = CLOSED_NOT_ARCHIVED`、`source_kind = MANUAL_CLOSE`；回放（200）时 `closed_by` 可以与当前身份不同；
- 关闭后的 History 与 Review 处置按 §5.3 的可达组合。
- 候选的 `review_version`、`selected` 的 422 路由桩与关闭路由的 `Idempotency-Key` 核对，按 §5.3“FE3c 的补充”。
- **错误码：** 关闭路由、`POST /v1/archives` 的新码与 review-events 的新码各有文案（§16.4–§16.7），加入取值核对；错误码单测解析快照中这些路由的描述。

### 16.9 必测场景（模拟接口）

| # | 场景 | 断言 |
| --- | --- | --- |
| V1 | 各类问题的卡片 | 7 个业务编码与同级、身份两类各一张卡；`details` 各类型按 §16.3 显示；未知编码没有“接受”，“确认归档”禁用 |
| V2 | 两侧独立项 | 同码、同目标的 ① 与 ② 两张卡；接受其一后另一张仍为未处理；各自撤销；请求中的 `subject_digest`、`expected_sequence` 各自正确 |
| V3 | 接受后不显示为通过 | 来源项接受后原始诊断仍为“来源未解释”，处理状态“已接受”，没有成功色与“通过” |
| V4 | 撤销 | 撤销后为“已撤销接受，需要重新处理”，“确认归档”禁用；撤销理由为空时禁用 |
| V5 | 预检变化与冲突 | 接受请求返回 `ARCHIVE_AUDIT_VERSION_CONFLICT` 时提示并重新预检，不重发；`candidate_set_digest` 变化时显示“候选集合已变化”提示 |
| V6 | 引用完整 | 200 个 FULL 候选（199 项同级排除、200 项生成时间缺失，共 399 项）全部接受后，开始归档请求含 399 项异常引用与 1 项确认引用；折叠分组不影响引用 |
| V7 | 阻断项 | `ARCHIVE_INTEGRITY_FAILURE`、`ACTIVE_SUBMIT_ATTEMPT` 只有文字与“重新预检”，没有接受入口 |
| V8 | 待审核阻塞 | 列出全部待审核提交的显示名与附注；点击名字定位到组态树；开始归档返回 409 `ARCHIVE_PENDING_REVIEW` 时的提示 |
| V9 | 关闭 | 关闭请求携带的 `expected_review_version` 等于同一次候选读取中目标候选的 `review_version`（模拟数据按 §5.3 使该值与 Review、工作区、基线的版本号都不同）；201 显示服务器返回的关闭人、时间、理由；200 回放时显示首次关闭人（与当前身份不同）；409 各码（含 `REVIEW_VERSION_CONFLICT` 后重新加载、再次打开时取新值）、403、404、422 的提示；理由为空、超过 4096 字节（含多字节字符的边界：4096 字节可用、4097 字节禁用）或未勾选时禁用；归档确认人身份只有 `archive_submission`，全过程没有 `GET .../review` 请求 |
| V10 | 关闭后重新核验 | 关闭后自动重新预检，来源项变为未解释；全部项（含原已接受的基线时间项）回到未处理，因为候选集合变化后全部 subject 重新派生 |
| V11 | 过期通过 | 审核顶栏 `APPROVE` 返回 `BASELINE_VERSION_CONFLICT`：提示、重新读取，“通过”禁用，“退回”“撤回”可用 |
| V12 | 已处置 | 审核动作返回 `ARCHIVE_CLOSED`：提示并按 §6.4 显示 |
| V13 | 开始归档被拒 | 开始归档返回 `ARCHIVE_ANOMALY_UNRESOLVED`：提示“归档候选或核验结果已变化”，点“重新预检”后显示最新状态 |
| V14 | 选择引用只含两个字段 | 候选模拟数据带 `review_version`；一次完整的归档主线（预检、接受、撤销、选择确认、开始归档）中，预检、确认、异常处置、开始归档每个请求体的 `selected` 键集合恰好为 `{submission_id, expected_candidate_digest}`，值与目标候选一致；路由桩对多出的键返回 422（§5.3），用例中不出现该 422 |

- 单测覆盖：问题文字与详情的映射、状态标签、`action` 映射、引用的取法（只取 `ACCEPTED`，不受折叠影响）、理由的字节计数。
- 单测另覆盖 `selected` 的构造函数：输入带 `review_version` 等多余字段的候选对象，输出恰好两个键（V14）。
- 真实 backend 对 `selected` 多出的键返回 422，J1、J2 中每次预检、接受、撤销与开始归档因此同时在真实 backend 上检验 V14 的规则（R8、R12）；J2 第 4 步由只有 `archive_submission` 的身份完成关闭，真实覆盖 V9 的取值规则。
- **V6 的构造（修订 2 审核 N7）：** 按后端规则可达：基线为空 `INITIAL`（无基线时间项，来源 `NOT_APPLICABLE`）；200 个 FULL 候选，① 有有效生成时间、② 缺生成时间（各一项 `GENERATION_TIME_MISSING`，`MODIFIED` 侧；① 有效、② 缺失时比较为 `NOT_COMPARABLE`，不产生时间倒退项）；选中 1 个，其余 199 个各一项同级排除；无身份例外。
- 另加 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 的提示断言（§16.5），可并入 V13。
