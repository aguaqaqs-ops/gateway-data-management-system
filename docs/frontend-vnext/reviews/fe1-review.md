# FE1 审核报告

- **审核对象：** 分支 `fe-vnext`，代码候选 `b67da4795fd22afcab1365f4138b131ab4c736d1`（`frontend/` 树 `3fdda26532`）；
  handoff 提交 `c1a76ea345f3b183cc9b04a2e90d3f58257626d7`（只改 `docs/frontend-vnext/fe1-handoff.md`）。
- **范围：** `14ea5e8e89..b67da4795f`（owner 指定的起点）。范围内的 `36047efe5a` 是设计会话的 kickoff 提交（§4.4 传输格式、BE-d），
  作为审核依据阅读，不算实施改动。
- **日期：** 2026-11-02。
- **结论：定向修复。** FD1–FD4、FD6 都遵守了，P2 组件齐全，测试命名合格，05 复跑通过。但有三项阻塞：
  - **B1：** 前端 bundle 校验与后端真实 manifest 不兼容，而 fixture 与校验器由同一方编写，测试是自证。
  - **B2：** 审核比较用的是当前 head，不是提交所基于的基线。
  - **B3：** P1 token 与已确认草图不一致。

  修复后需要重新在 04 取证。

## 1. 范围

`14ea5e8e89..c1a76ea345` 中，实施提交只改动了 `frontend/`（42 个文件）和 `docs/frontend-vnext/fe1-handoff.md`。
没有改动 `vnext/`、AGENTS、kickoff、UI 优化方向和 `.gitignore`。**通过。**

## 2. FD 遵守情况

| FD | 结论 |
| --- | --- |
| FD1 | 没有 legacy 引用和兼容层。通过。 |
| FD2 | 全部网络请求只经过一个入口，即 `authenticated-fetch.ts:33`；bundle 下载（`client.ts:194`、`:212`）也经过这个认证 fetch。token 由 provider 提供，不写入浏览器存储（源码中没有任何 storage 或 cookie 调用）。通过。 |
| FD3 | 逐个检查了调用点：`frontend/src` 中除上述入口外，没有 `fetch`、XHR、WebSocket、`href` 下载或动态网络 import。浏览路径（`presentation.ts` 的 `readLocalTable`、`readLocalChangeRecords`，以及 `parquet-reader.ts`）只读取已安装的本地 bundle。下载是流式写入 OPFS 的，不在内存中攒整包。通过。 |
| FD4 | 审核操作只有 `APPROVE`、`REJECT`、`WITHDRAW`；退回时必须填写理由；快照中残留的 `RETURNED_FOR_REVISION` 在客户端映射为 `REJECTED`（`client.ts:146-163`）。BE-a 之前可以接受。通过。 |
| FD6 | 没有导航产物时回退为“全部表”单组（`model.ts:158-172`）；按 `groups` 通用渲染，未知 `group_key` 也能显示；未认领的表放进 `OTHER_TABLES`；风险只取自 RiskReport，不从记录推断（`model.ts:125-128`）。通过。 |
| FD5 | FE2 起审。 |

后端契约核对：幂等 key 走 `Idempotency-Key` 请求头；错误体是 `{code, message, details}`；CreateOrGetWorkspace 不带 key；归档启动是同步返回的。这些都与 `vnext/backend/src/gateway_backend/http` 一致。

## 3. 复跑与证据

- **复跑：** 把 `c1a76ea345` 打成 bundle（`^14ea5e8e89 fe-vnext`，SHA256 `66c70ce7…3bee`，两端一致）传到 05，fetch 后建 detached worktree
  `/home/dev/gdds-fe-review-fe1-c1a76ea3-05`（clean，`frontend/` 树 `3fdda26532`）。05 的 main 停在 `14ea5e8e89` 未移动，占用标记不存在。
- **复跑日志：** `/home/dev/gdds-fe-logs/fe1/review/frontend-tests-20261102T132320Z.log`，SHA256
  `275bf963bd9624cfff507ba5c421e3830b26b3ba506648311ac26b94d8b1fd11`。`run-tests.sh --e2e` exit 0，`13:23:20–13:23:34Z`，HEAD 和 `frontend/` 树起止不变；
  8 个测试文件 32 项单测通过，e2e 3 passed；fixture 摘要 `sha256:c108ea2c…be8c` 与 handoff 一致。运行后 worktree 仍 clean。
- **后端形状探针：** 日志 `/home/dev/gdds-fe-logs/fe1/review/backend-manifest-shape-probe.log`，SHA256 `c1ee5f9c…fa73`。在 05 上用 `s1c-vprime-ebd1-backend` 镜像
  （network none，候选树的 `vnext/` 源码只读挂载）调用后端 `manifest_semantic_payload`，输出的 `closure` 是 `{"entries": []}`（dict）。用于 B1。
- **实施方证据：**
  - 05：`frontend-tests-20261102T125601Z.log` 的 SHA256 `76698b09…a563`；
  - 04：`frontend-tests-20261102T125742Z.log` 的 SHA256 `af5f9eaf…0f46`；
  - 两个节点上的 preflight、bundle-fetch（含 DC68 首次失败日志）和 worktree-add 日志，以及 CT201 上的 source-bundle、transfer 和 `dc68-operations-summary.log`，SHA256 都与 handoff 一致；
  - 两次运行都记录了 hostname、起止 HEAD 和 `frontend/` 树（`b67da4795f`、`3fdda26532`）、32 项单测、3 项 e2e、exit 0；两个 worktree 都 clean；两节点的 main 都是 `14ea5e8e89`。
  - 由于本轮需要修复，04 的这次运行**不能作为 FE1 退出证据**。修复候选通过复审后，要在 04 重新运行一次。
- **FE0 遗留：** N1 已处理（`test:unit` 不再使用 `--passWithNoTests`）；R2 已处理（日志记录了 `frontend_tree_start/end`）。

## 4. Findings

### 阻塞

**B1. bundle manifest 的 `closure` 形状与后端不一致；fixture 由前端自造，测试无法发现这一点**

- **位置：**
  - `frontend/src/features/bundle/posix-tar.ts:44`：类型把 `closure` 定义为数组；
  - `posix-tar.ts:319`：`Array.isArray(manifest.closure)`；
  - `posix-tar.ts:325`：拿 `manifest.closure` 与 `closure.entries` 比较；
  - `posix-tar.ts:347`：`closure_manifest_digest` 按 `hashJson({ entries: manifest.closure })` 计算；
  - `frontend/scripts/build-golden-bundle-fixture.mjs:190`：fixture 中写成 `closure: semanticEntries`（数组）。
- **后端事实：** `vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_digest.py:65` 写的是 `"closure": closure_semantic_payload(closure)`，
  即 `{"entries": [...]}`；manifest 文件由 `manifest_bytes` 在它的基础上加入 `bundle_digest`、`closure_manifest_digest`、`closure_entries`；
  `closure_manifest_digest` 等于 `sha256(JCS({"entries": [...]}))`。05 探针实际输出的 `closure` 是 `{"entries": []}`（dict）。
- **失败场景：** FE3 接上 BE-d 之后，真实后端的每个 Preview 或 History bundle 在 `validateManifests` 一步就会因“bundle closure 列表缺失”被判为
  `BundleIntegrityError`，重试一次后仍然失败，用户永远打不开比较结果。
- **为什么测试没发现：** fixture 生成脚本和校验器出自同一方，按同一种错误理解构造和验证数据。所谓 golden 只是从 `vnext/fixtures/golden` 复制了三个 case 文件，
  抽查三个字段（`build-golden-bundle-fixture.mjs:123-125`），里面没有一份后端产出的 manifest、closure 或摘要。surface 和 risk fixture 是手写的；
  三份 Parquet 由 PyArrow 生成，但生成脚本没有提交。kickoff §7 的 FE1 退出条件要求“A 用 golden bundle……覆盖全部旅程的数据流”，目前的 fixture 不能证明与后端兼容。
- **建议修复：**
  1. 用后端代码生成 fixture 的内容：在已有的后端依赖镜像中（network none，源码只读挂载，与 FE0 生成 OpenAPI 快照的方式相同），调用 `bundle_assembly`
     （以及 surface、risk、records 的后端组装代码），以一组最小 snapshot 输入产出 manifest、closure 和全部 closure 产物。提交生成脚本（例如 `frontend/scripts/` 下的
     Python 脚本加调用命令）和产物，handoff 记录来源提交、镜像身份和产物摘要。tar 封装仍由前端脚本按 §4.4 完成。
  2. 按后端形状修正前端：`manifest.closure.entries`、`closure_manifest_digest = sha256(JCS(manifest.closure))`，类型同步修改。
  3. 加一个由后端产出 fixture 驱动的测试，断言前端重算的 `bundle_digest`、`closure_manifest_digest` 和 `bundle_manifest_digest` 与后端值相等。这个测试是“前后端摘要算法一致”的唯一 owner。
  4. Parquet fixture 也改用后端 writer 产出，或者至少提交生成脚本。
  5. BE-d 实现后，在 FE3 用真实 `/bundle` 再验证一次。本轮不依赖 BE-d。

**B2. 审核比较用当前 head，没有用提交所基于的基线**

- **位置：** `frontend/src/features/api/journeys.ts:158-165`（`ref_id: history.head.node_id`）；测试 `journeys.test.ts:83` 把这种行为写成了预期。
- **失败场景：** 提交 S 基于基线 B1。之后另一个提交被归档，head 推进到 B2，S 在历史中被标记为 `eligibility_note = NOT_CANDIDATE_BASE_ADVANCED`。
  审核人这时打开 S，比较的是 B2 → S，差异里会混入“撤销 B2 新归档内容”的变更，审核人看到的不是提交人实际做的修改，可能据此做出错误的通过或退回。
  head 未推进时两者相同，所以现有测试发现不了。
- **后端事实：** 历史节点 `HistoryNodeResponse.parent` 就是提交所基于的基线节点；`SubmissionResponse.based_on_baseline_node_id` 也给出了同一事实，但审核人不一定有工作区权限读取它。
- **建议修复：**
  - 从 `listHistory` 中找到该提交节点，用它的 `parent` 作为比较起点。`listHistory` 需要处理 `next_cursor` 分页，见 N5。
  - 测试改为 head 已推进的场景，断言比较起点是 parent。
  - 如果设计会话认为审核就应该和当前 head 比较，需要在 kickoff §8 写明，测试名也要说明这一点。

**B3. P1 token 和风险文案与已确认草图不一致**

- **位置：**
  - `frontend/src/design-system/tokens.css:45-47`：强调色 `#1f5efb`、悬停 `#174bd0`、浅底 `#e8efff`；
  - `tokens.css:36-43`：中性色 `#202833`、`#596779`、`#d9e0e8`、`#f5f7fa`；
  - `tokens.css:3`、`:7`：字体族 `"Noto Sans CJK SC", sans-serif`；
  - `frontend/src/design-system/components.tsx:27`：风险徽章文案为“较高风险”“较低风险”。
- **草图事实：** S1–S4 全部草图中，主按钮、链接和强调色都是 `#1F5FBF`（悬停 `#174A96`，浅底 `#E9F0FB`），共出现约 130 次；主要文字 `#1B2229`，次要文字 `#5F6B78`、`#4A5563`，
  边框 `#DDE2E7`、`#C9D0D8`，页面底色 `#EEF1F4`、`#F7F9FB`；字体族是 `'IBM Plex Sans', 'PingFang SC', 'Noto Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif`；
  风险文案是“中高风险”“中低风险”。
  UI 优化方向 §3 还要求中低风险的天蓝与强调色“深蓝”分开，而 `#1f5efb` 是偏亮的蓝。
  风险语义色（`--risk-*`）和差异中性色与 S4 画板逐项一致，这部分没有问题。
- **失败场景：** P1“token 单一来源”是 FE1 的退出条件。按现在的 token 实现 FE2 页面，所有主按钮、焦点框和当前变更框的颜色都会偏离已确认草图，FE2 截图验收时又要整体返工；
  风险等级文案也与草图、UI 优化方向的五级名称不一致。
- **建议修复：** 按草图修正强调色、中性色和字体族 token，风险文案改为“中高风险”“中低风险”。草图里如有不在 12/13/14/16/20 五档字号内的尺寸，以 UI 优化方向 §3 为准。
  `theme.test.ts` 中写死的 token 值同步修改。

### 非阻塞（建议本轮一并处理的已标注）

**N1. 幂等 key 没有按“用户意图”复用**（`client.ts:123-125`；`journeys.ts` 中除 `runArchiveJourney` 外都不传 key）
每次调用都生成新的 UUID。网络中断后用户重试时，后端无法回放第一次请求的结果，只能靠版本 CAS 返回冲突，用户看到的是“版本冲突”而不是原来的结果。
后端有 CAS，不会产生重复的业务效果，因此不阻塞 FE1。FE2 接入按钮前，应改为每个用户意图生成一次 key、重试时复用；旅程函数按步骤接收 key。

**N2. 轮询的超时和临时错误处理**（`journeys.ts:33-48`）
默认 5 分钟超时就抛错，而 t4 规模的 Preview 可能超过这个时间（P6 的 t4 完整旅程中位数约 3665 秒），后端仍在运行，前端却报失败；
轮询期间一次网络抖动也会让整个旅程失败。建议超时只表示“仍在运行”而不判为失败，并对临时错误做有上限的重试。FE2 前处理。

**N3. Preview 结果没有与本次操作绑定**（`journeys.ts:78-81`）
旅程从工作区的 `current_preview_result_id` 取结果，没有核对 `preview.operation_id === accepted.operation_id` 以及 `upload_revision_id`。
如果有并发的另一次 Preview，就会打开别人的结果。建议加上这一核对（本轮可以一并处理）。

**N4. 已缓存的表每次读取都对整个文件重算 SHA-256**（`local-bundle.ts:116-126`）
本地缓存属于派生、可重新下载的数据（比例化保障政策：派生状态优先有界处理）。用纯 JS 对大表每次打开都整文件重算，会给 t4 规模的数据带来可感知的延迟。
建议安装时校验一次，之后每个会话首次读取时校验，或者只在读取失败时重新下载。

**N5. `listHistory` 忽略了 `next_cursor`**（`client.ts:206-209`）
FE2 的组态树和 B2 的修复都需要完整的节点列表。

**N6. 应用代码的 tsconfig 引入了 Node 类型**（`tsconfig.app.json` 的 `types` 中加入了 `"node"`）
这样应用代码里误用 `Buffer` 等 Node API 也能通过类型检查，到浏览器中才报错。建议为测试单独建一个 tsconfig。

**N7. fixture 生成目录没有加入 `.gitignore`**
`frontend/src/test/fixtures/generated/` 未被忽略（已用 `git check-ignore` 确认）。如果在容器外运行 `test:unit`，会生成未跟踪文件，worktree 变脏，runner 随即拒绝运行。

**N8. `Dialog` 使用固定 id**（`components.tsx:79-81`，`dialog-title` 和 `dialog-description`）
同时存在两个对话框时 `aria-labelledby` 会冲突。建议改用 `useId`。

**N9. handoff 勘误**（`docs/frontend-vnext/fe1-handoff.md:50`）
第 4 个 DiffID 末尾少了一位 `d`，正确值是 `…c4e5aef3d`。runner 按固定值自动比对并已通过，所以不影响运行结果；下一次更新 handoff 时更正，以后用机器生成，不要手抄。

### 交设计会话（不阻塞 FE1）

**D1. BE-b 的 `BusinessNavigation.diagnostics` 缺少结构定义**（handoff“待 BE-b 明确”一项）
前端目前的过渡处理（字符串，或者从 `code`/`message` 拼成文本）可以接受。请在 BE-b 第二步的 Contract 中定义 `Diagnostic` 的字段和用户文案映射，FE2 设计 diagnostics 展示时以此为准。

## 5. 测试核对

- 测试按业务行为命名，没有使用轮次或 finding 编号；没有为覆盖率而写的探针；32 项单测和 3 项 e2e 都实际执行了，日志中有逐文件计数。
- **不变量 owner：**
  - 认证头、错误体、幂等头：`client.test.ts`；
  - tar 完整性：`posix-tar.test.ts`；
  - 回退与通用分组：`model.test.ts`；
  - 命令层与 URL：`commands.test.ts`；
  - OPFS 真实浏览器路径：e2e 第 3 项。

  没有发现重复 owner。
- **不足：**
  - B1 所说的跨实现摘要一致性没有测试 owner；
  - `journeys.test.ts:83` 把 B2 的错误行为写成了预期；
  - `pollOperation` 的失败、取消和超时路径没有测试（与 N2 一起补）；
  - 三节点历史比较及比较对切换的数据流没有单独覆盖（FE2 比较托盘接入前补上）。

## 6. kickoff §7 FE1 退出条件

| 条件 | 状态 |
| --- | --- |
| A：认证封装、API 客户端、轮询与幂等、bundle 本地化与解析、视图模型、命令层 | 都已实现；幂等和轮询的健壮性见 N1、N2 |
| A 用 golden bundle 与模拟接口覆盖全部旅程的数据流 | 模拟接口覆盖了 Preview、数据集替换、提交、审核、审核动作、归档（两例）；**golden bundle 不是后端产出的，不满足（B1）**；审核数据流有错（B2） |
| B：token、组件、表格主题、对话框 | 已实现；token 值与草图不一致（B3） |
| B 覆盖 UI 优化方向 P1、P2 | P1：按钮四档、字号五档、差异与风险语义色分离都满足，token 值与字体族不满足（B3）。P2：X1（不用原生弹窗）、X2（内联错误并保留选择）、X3（理由必填对话框）、X4（确认与影响摘要）、F3（已选目录）、F4（禁用原因）、A1（应用内确认）、T1（阶段时间线与重试）、T2（骨架屏）、T3（错误码、复制、重试）都在组件预览中落地，满足 |
| 04 阶段退出取证 | 已在 `b67da4795f` 上运行并通过，但因为需要定向修复，要在修复候选上重新运行 |

## 7. 复审范围

复审对象为 `c1a76ea345..<修复候选>`，核对内容：

1. **B1：** fixture 由后端代码产出，生成脚本、来源和摘要可以复现；前端按后端形状校验；跨实现摘要一致性测试存在并实际通过。
2. **B2：** 比较起点取提交节点的 `parent`，测试覆盖 head 已推进的场景（或设计会话另有结论）。
3. **B3：** token 和风险文案与草图一致。
4. 实施会话选择处理的 N 项（建议至少处理 N3、N7、N9），以及 handoff 的更新。
5. 05 复跑；复审通过后在 04 重新取证。
