# 后端会话交接：设计与审核分设（DC73）

- 日期：2026-11-04。
- 交出方：原后端审核会话。它负责 P5 收口审核，并在 P6 中兼做审核与 DC64–DC72 的记录。
- 接收方：设计会话 `p6-backend-design`、审核会话 `p6-backend-review`。分工见 [DC73](p6-s0-owner-decisions.md#dc73-后端会话分为设计与审核两个角色)。
- 本文记录交接时点的状态，不随后续进展更新。最新状态以各 handoff 与审核报告为准。

## 1. 文件归属

| 文件 | 写入方 |
| --- | --- |
| `p6-s0-owner-decisions.md`（DC）、`p6-design.md`、`p6-execution-plan.md` 正文、`p6-*-kickoff.md` 的确认记录 | 设计会话 |
| `p6-*-review*.md`、`p6-*-evidence-check-*.md`、`p6-baseline-stop-check-*.md`、`p6-*-final-review.md`；exit 时执行计划的阶段状态行 | 审核会话 |
| 各阶段 handoff、`p6-baseline-handoff.md`、`vnext/` 代码 | 对应实施会话（S2a 为 `p6-s2a-impl`；基准为 `p6-baseline-measure`，只改 `vnext/backend/benchmarks/`） |
| `AGENTS.md`、`docs/backend-vnext/testing-conventions.md` | 治理会话 |
| `docs/frontend-vnext/`，包括 BE-b 设计草案 | 前端设计会话与前端审核会话 |

## 2. 进行中的工作

### 2.1 重建对照基准（审核会话跟进）

- 实施：`p6-baseline-measure`，分支 `p6-baseline`。测量节点 ct108 由它独占；ct108 上的 worktree 以 HEAD 命名，例如 `/home/dev/gdds-p6-baseline-measure-<HEAD>-ct108`。
- 被测产品：`p6-s1c-exit`（`9f288ad504`）。镜像身份用 `/home/dev/gdds-p6-logs/s1c/vprime-ebd1-identity.json` 与 `check-vprime-identity.py` 程序比较。
- 已 PASS：
  - t1–t4；
  - 2× core；
  - 正确输入的 2× full-v2（`p6bw3fullretry20261101d`）；
  - H1-REFILL；
  - H2 两节点。
- 停止复核历史（均为工具或输入缺陷，没有产品缺陷）：
  - [放行检查](p6-baseline-release-check.md)
  - [full-v2](p6-baseline-stop-check-full-v2.md)
  - [输入](p6-baseline-stop-check-input.md)
  - [W4](p6-baseline-stop-check-w4.md)
  - [2× 身份](p6-baseline-stop-check-2x-identity.md)
  - [W4 KEY_EMPTY](p6-baseline-stop-check-w4-key-empty.md)
- 当前状态：
  - W4/S4/H1 在 v2 Preview 报 `KEY_EMPTY`。原因是生成器给空表补充的行在 key 列写了空字符串。
  - 处置见 KEY_EMPTY 停止复核 §4（`c9f8dca39f`，交接时尚未推送）。
  - 实施方已在 `p6-baseline` 提交生成器修正 `b150f76f41`、`e0768fbeae`。
  - 2026-11-04T00:05Z 起，ct108 占用标记的用途为 H2 三节点测量、W4 输入重新生成与 H3 测量。
- 剩余：
  - W4 输入重新生成并通过程序验收；
  - W4/S4/H1、W4-FULL、W4-STRESS；
  - H2 三节点、H3；
  - 只读 631/631 表哈希对照；
  - DC63 子段、V5b 四段；
  - 正式 JSON 与 SHA256、comparator replay；
  - 04 最终 runner。
  - 剩余估计超过 48 小时时停止，交 owner。
- 测量完成后：基准终审，由审核会话负责。终审中要复核：
  - DC66 第 5 项下全部工具修正提交，范围为 `p6-s1c-exit..p6-baseline` 中 `vnext/backend/benchmarks/` 与测试；
  - 参考表更正（W4、W4-STRESS、S4 只记录）。
  - S1c handoff 的 DiffID 勘误已于 `13bfb4df33` 推送，终审不再处理。
  - 终审通过后办理基准 exit，再办理 S2a exit（DC70）。

### 2.2 S2a SQL 解析器（审核会话跟进）

- 实施：`p6-s2a-impl`，分支 `p6-s2a`，开发主机 worktree `/home/dev/gdds-p6-s2a`。
- 审核历史：
  - [kickoff 审核](p6-s2a-kickoff-review.md)；
  - [代码审核](p6-s2a-code-review.md)，定向修复；
  - [复审 1](p6-s2a-rereview-1.md)，通过，候选 `30d67140d4`；
  - [证据复核 1](p6-s2a-evidence-check-1.md)：04 runner 有一个过时的 RS 测试失败，其余通过。
- **待办：证据复核 2。**
  - 新候选 `3b3d9c97bc` 只删除过时测试；handoff 为 `p6-s2a` 上的 `c3c95282bf`，§11。
  - 实施方报告：04 六包 runner exit 0；05 第 ④ 层 t1–t4 与 testdata1 逐值差分为 0。
  - 要核对：测试删除的 diff、逐包 manifest、日志 SHA256、停止规则。
- exit 在基准 exit 之后办理（DC70），exit 时更新执行计划路径清单（DC72 第 2 项）。
- handoff 中给 AGENTS/testing-conventions 的建议条文由 owner 转交治理会话。
- 待清理的审核 worktree：
  - 开发主机：`/home/dev/gdds-p6-logs/s2a-review-wt`、`/home/dev/gdds-p6-s2a-review-30d67140`、`/home/dev/gdds-p6-s2a-evidence-review-cd97c5c`、`/home/dev/gdds-p6-s2a-evidence-review2-c3c95282`；
  - 05：`/home/dev/gdds-p6-s2a-review-05`、`/home/dev/gdds-p6-s2a-rereview-05`；
  - 05 上其余 `gdds-p6-s2a-*` 属于实施方，exit 时由其清理。
  - 清理前用 `git worktree list` 确认来源。

### 2.3 下一阶段与后端任务（设计会话负责）

- **S2b kickoff**（前置：S2a exit）：
  - 设计 §8；
  - 设计核对项：上传侧原始表的其他使用方、规范表存储的磁盘估算；
  - DC63 第 1 项中基准子段拆分留下的差距；
  - DC72 第 3、6 项转入的生产 feature flag、worker 共享池接线与 N/M 配置；
  - W2 可达性检查点（设计 §16.1）。
  - kickoff 写成后交审核会话做 kickoff 审核。
- **BE-a、BE-d**（[前端 kickoff](../../../../frontend-vnext/frontend-kickoff.md) §5）：
  - 2026-11-07 Owner已授权A1→V1→V2→D及联合最终准备，设计候选16472197b4/终审a5d87540e6已GO；S2a/S2b退出，不等待原基准测量线。
  - A1本节GO c1ee962755、V1最终GO 5dc01deeb5、V2最终GO 9ec62e82ad（产品/容器f8fb796f02、handoff3cd4400f9f）；D已从clean 9ec启动，新实施/独审6.1-Sol xhigh/max，先精确清单cf2091eadd。实际角色/候选/节点/证据见[持续协调交接](p6-be-a-d-coordination-handoff.md)及[联合kickoff](p6-be-a-d-kickoff.md)。
  - 实施协调会话01a1b4f1-df13-7331-b3c4-77bb560203f2负责正常推进/节点/交接，设计者仅处理设计澄清与决策；前端由Owner手动转发[V2接口包](p6-v2-frontend-handoff.md)，不要求设计者日常催进度。
  - D本地0ba/tree0301、F1–F5已核收；联合eff1修复精确subject F6后，49403/tree567201六包13:33:56Z原exit0（RS按设计1skip），05 a99918步/四tar实跑通过并按有限成功路径引用，05/06已释放。实际交接当前态见[D handoff §12](p6-be-d-handoff.md)及[联合记录§10](p6-be-a-d-joint-validation-preparation.md#10-身份收尾停止与owner选择)。
  - **联合后端技术GO `ccdd1eb39d` §25，Owner已确认DC33范围**：固定49403/tree567，handoff233e；四包direct DTW原0+实际compare，两包mvzi新原0，runtime原cfg/54DiffID及RS预后一致、原manifest/LAN/释放均独核。04/05/06已释放，原D两角色完成并正常停止/历史保留，无新角色。Owner明确确认05 a999一次fresh t1/18步/四tar及04异常接线范围，见[最终交接§13](p6-be-a-d-joint-validation-preparation.md#13-owner最终dc33范围确认与交接)。旧RS/aaa缺口不伪补、不称新docsHEAD实跑；FE3同tarOPFS、实际最终HEAD退出绑定/手续另待，不tag/push/S3或动冻结资源。
  - **后续正式退出已完成（Owner明确授权，2026-11-07）**：BE-a／归档核验／BE-d联合本地附注`p6-be-a-d-exit`（对象66b9083941）精确指独立退出报告F`77b9aeea74b08b527ef1c78637e0cbe000b60d2f`，在main可达；F原04同WT实际六包／镜像／五锁绑定通过并获原审最终GO，16:17:03Z本人标记释放。产品仍49403/tree567，无新产品diff；[最终交接§15](p6-be-a-d-joint-validation-preparation.md#15-联合正式退出完成与前端交接)闭合此前退出pending。此为post-exit记录，未push，FE3b／原基准／S3实施独立。
- **BE-b**：
  - 设计由前端设计会话负责（草案 `docs/frontend-vnext/be-b-navigation-and-presentation-draft.md`）；
  - 实现在 P6 退出后、Phase 8 前（FD8）。
- **BE-c**（t4 与 2× t4 bundle 体积，只报告）：交接时基准计划中没有对应场景。设计会话确认放在基准还是 S6。
- **前端 kickoff §9**：P6 计时是否计入整包下载，待设计会话或 owner 决定。
- **执行计划 §3 设计阶段待定项**中仍未定的：写后回读、Arrow 列映射、磁盘估算、N 定稿、H2 门槛。

### 2.4 已登记的遗留（不阻塞）

- worker runtime 维护：
  - startup 阻断 `BLOCK_STARTUP_FATAL`（DC71 第 3 项）；
  - DC63 第 3 项的 O1。
- RS 容器累积 defunct `dolt` 进程（交 RS owner）。
- surface `diagnostics_summary` 中的自由文本收敛为编码（前端 kickoff §9）。

## 3. 节点与开发主机保留项（基准 exit 前不删）

- ct108：
  - S1c 卷 `s1c-vprime-ebd1_*`；
  - 证据目录 `/home/dev/gdds-p6-logs/s1c/evidence/ct108-vprime-b96fe8e4cc`；
  - 基准输入根 `/home/dev/gdds-p6-logs/baseline/input/*`，作废的根保留为证据；
  - `p6bw4s4h120261103a` 三卷：在 handoff 记下摘要后删除，按 KEY_EMPTY 停止复核 §4 第 6 项。
- V′ 镜像 `s1c-vprime-ebd1-{backend,worker}`：开发主机与三台节点都有，config digest `6d0aab7e…`。开发主机另有归档 `/home/dev/gdds-p6-logs/s1c/backend-worker-s1c-vprime-ebd1.tar`。
- 05 上基准会话留下的 `p6resume-*` 镜像 tag。
- `gateway-backend-deps:lock-c668cef8e47e`（开发主机与 04）、`lock-d054366c02fa`（S2a 与前端使用）。
- 永远不要 `docker rmi` client e2e 镜像。

## 4. 审核经验（交审核会话）

1. 身份、输入与参考值一律由程序比较，不手抄哈希。手抄 DiffID 曾导致误停。
2. 输入核对要绑定“实际被消费的输入”：full-v2 曾按文件名取到真实 t4。重新生成后要与已接受值比较，不能只核对自洽（2× 身份）。
3. 验收检查要覆盖产品实际走的全部路径与全部表，并检查状态字段本身。census 只对一张表做规范投影，漏掉了 KEY_EMPTY；W4 census 早已是 FAILED，但没人检查状态字段。
4. 审核方自己列的 checkpoint 或场景清单会扩大取证范围（S1c v3 三节点）。写进建议前确认它在授权范围内。
5. 删除代码或测试时，focused 集合加上 RS `-m unit`，并检索由片段拼接的路径（S2a 过时测试）。
6. 停止复核先判断失败是否发生在被测对象运行之后（DC68）：
   - 工具缺陷按 DC66 第 5 项处置，不需要新 DC；
   - 产品缺陷交 owner，按 DC69 的方式决定修复落点。
7. 读取真实数据只输出计数与摘要（DC22）。临时脚本放在节点 `/home/dev/gdds-test-tmp/` 下，用后删除。审核的只读核对不取节点占用标记。

## 5. 其他会话

| 会话 | 职责 |
| --- | --- |
| 治理会话 | AGENTS.md、testing-conventions |
| 前端设计、实施、审核会话 | `docs/frontend-vnext/`、`frontend/`。FE2c 进行中；其提交也在本地 `main` 上，推送时一并列出 |
| `p6-baseline-measure` | 基准测量与 `benchmarks/` 工具修正 |
| `p6-s2a-impl` | S2a 实施（分支 `p6-s2a`） |
