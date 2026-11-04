# FE2c 复审报告（第 2 轮）

- **复审对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `943feb20fa77a90ac2f407698330d919538a526f`，`frontend/` 树 `0f15710a95`；
  - handoff 提交 `e42d40e52614385f2242acbc46592b431a6fcc5a`（相对代码候选只改 handoff，`frontend/` 树相同）。
- **范围：** `680b643f..e42d40e526`。
  - 其中 `31bff353b0` 合入 main `7d9521d04b`（只有文档）；
  - FE2c 的改动为 23 个提交、17 个 `frontend/` 文件（975+/151-），加上 handoff。`vnext/` 没有改动。
- **依据：** [复审第 1 轮](fe2c-rereview-1.md) §3、§5；[FE2c 审核](fe2c-review.md)；[FE2 kickoff](../fe2-kickoff.md) §7.1、§7.5、§9 Q16、Q17；后端源码（各条注明位置）。
- **日期：** 2026-11-04。
- **结论：定向修复，范围小。**
  - 这一轮质量明显提高：
    - handoff 先写了步骤与 key 规则，再实现；
    - 运行清单完整，包括失败的运行；
    - 逐项对照可追溯。
  - 实测通过的有：N1、N2 的请求侧约束、N3、N5 的旅程续做、N6 的主体、N9。我在 05 上的完整运行、上传包校验和回归探针都通过（§2）。
  - 剩下 5 项需要修复（§3）：
    - R1：“首批空基线”的判断没有后端依据，e2e 用的是后端不会产出的状态。需要 owner 决定（D1）；
    - R2：上传与 Preview 被 4xx 拒绝后，“重试”仍用旧的版本和 key，与 handoff 自己写的规则不符，重试不会成功；
    - R3：上传包校验脚本没有按 §7.1 的入口约束做，日志中的 “config digest” 实为本机 image ID；
    - R4：审核版本冲突提示中的“刷新审核信息”超出对话框，两种宽度都被截断；
    - R5：归档成功路径与退回仍用提交人身份。
  - 都是局部修改。修完后第 3 轮只核对这些项，然后去 04 取证。

## 1. N1–N9 与次要项核对

| 项 | 核对 | 结论 |
| --- | --- | --- |
| N1 | `runArchiveJourney` 接收一个进度对象，按 `subject_digest` 分别保存 key、`expected_sequence` 和已得到的序号；开始归档的 key 与结果也保存在其中。已成功的记录不再重发。对话框在重新加载预检时新建进度对象；修改处理原因时，只丢弃尚未发出的那条异常的 key。我上一轮的探针（两条异常、按对话框实际参数调用）现在通过（§2.2） | **通过** |
| N2 | 请求侧：`validateSimulatedRequest` 是唯一的实现，e2e 中 8 条写路由、`POST /v1/workspaces` 与审计查询都调用它；单测逐条核对。上传包校验：脚本能产出四种包并交给后端校验，结果正确（§2.1）。但脚本本身不符合 §7.1 的约束，见 R3 | 请求侧**通过**；脚本见 R3 |
| N3 | 确认后的预检保留 `selected`、选择摘要、`confirmation_requirements` 与异常；新单测按规则核对三个预检场景 | **通过** |
| N4 | 刷新后按 `sessionStorage` 中记下的 Preview 操作恢复页面锁定，成功后下载 bundle、进入差异浏览；提交对话框显示“需要管理员处理”与可复制的操作 ID，成功后显示结果页；操作结束后清除 URL 中的 `operationId`。两条 e2e 已加 | **通过**，次要问题见 m1、m4 |
| N5 | 上传成功后重试从 Preview 开始，不再上传；上传响应丢失时用第一次的 key 与版本重放。我另写的两条探针都通过（§2.2）。4xx 之后的处理见 R2 | 续做**通过**；4xx 见 R2 |
| N6 | 归档、审核、提交的错误码就地显示并可复制；审核 `REVIEW_VERSION_CONFLICT` 有“刷新审核信息”，刷新后换新 key 并使用新版本；生产构建检查要求产物含错误码界面的文字 | 功能**通过**；版面见 R4 |
| N7 | 上传/Preview、审核、归档的 403 与冲突，提交的 `ABORTED`，归档阻断项都有 e2e；审核通过、归档冲突两条 e2e 切换了身份并核对 token | **部分**，见 R5 |
| N8 | 只传本次归档时显示“解析预览”；摘要行与目录卡片只显示一个；空基线时第 ① 步禁用 | 前两项**通过**；空基线见 R1 |
| N9 | 95 张截图，两种宽度。原审核 §8 列出的状态都有了 | **通过**；截图问题见 R4、m2 |
| M1 | 条目数检查移到打包之前，并有单测 | **通过** |
| M8 | 事件 fixture 名实一致；D1 断言补齐 | **通过** |
| M9 | 上传 e2e 由工具栏“上传”发起 | **通过** |
| M10 | 锁定时顶栏与工作区加 `inert`，e2e 断言了属性 | **通过** |

## 2. 我在 05 上的核对

源码经 bundle 传到 05（`/home/dev/gdds-test-tmp/src-rereview2-fe2c-e42d40e5.bundle`，SHA256 `6f869a71…22490974bc1`，ref `fe-vnext`，只取 `FETCH_HEAD`），worktree `/home/dev/gdds-fe-rereview2-fe2c-e42d40e5-05`（detached `e42d40e526`）。
开发主机的只读 worktree 为 `/home/dev/gdds-fe-rereview2-fe2c-e42d40e5`。日志在 05 的 `/home/dev/gdds-fe-logs/fe2c/rereview-2/`，驱动日志 `rereview-05.log` SHA256 `c3eb8cd9…45b863a`（`11:16:19Z`–`11:18:15Z`）。运行期间 05 没有占用标记。

### 2.1 完整运行与上传包校验

- runner（`--e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/rereview2-e42d40e5-05`）：
  - 日志 `frontend-tests-20261104T111642Z.log`，SHA256 `c402833b…f134d10ec`；`11:16:42Z`–`11:17:34Z`，`gw-dms-test-05.lan`，起止 HEAD `e42d40e526`，`frontend/` 树 `0f15710a95`，exit 0；
  - 27 个单测文件 130 项、生产检查、30 个 e2e 全部通过；工具链 config digest `sha256:a0d7b2b4…a1017`；运行前后 worktree clean。
- 截图 95 张，文件名与实施会话的 `fix-2-943feb20-05` 一致。84 张逐字节相同。不同的 11 张中，6 张是上传、提交执行中的页面，显示等待时长（见 m2）；另外 5 张是抽屉、S3/S4 与退回对话框，前几轮也有同类渲染差异。04 取证时以 04 的截图为准。
- 上传包校验（`frontend/scripts/validate-upload-package.sh`，输出目录 `/home/dev/gdds-test-tmp/fe2c-rereview2-upload-validation`）：exit 0。`with-logics`、`without-logics`、`long-path` 被接受，成员一致；`missing-dbcfg` 被拒收，`UPLOAD_CLOSURE_INVALID`。日志 `upload-validator.log` SHA256 `02edad63…f77b83371`。运行后 worktree clean。

### 2.2 回归探针

在以 `e42d40e526` 为基础的一次性 worktree 中加入两个测试文件，以 `review-probe` 身份提交后运行 runner（不含 e2e），结束后删除 worktree。runner exit 0，133 项通过（`probe-regressions.out` SHA256 `024247a1…445b863a`）。

| 探针 | 内容 | 结果 |
| --- | --- | --- |
| 上一轮 P1 | 按 `ArchiveMainlineDialog` 实际传入的参数调用 `runArchiveJourney`，两条异常；模拟 API 对同 key、不同请求返回 409 | 通过（上一轮失败） |
| Preview 受理失败 | 上传成功，`startPreview` 第一次返回 503；同一进度对象重试 | 通过：只上传一次，两次 `startPreview` 使用同一 key |
| 上传响应丢失 | `uploadRevision` 第一次网络错误，之后工作区版本已前进；同一进度对象重试 | 通过：第二次上传使用第一次的 key 与版本 |

## 3. 需要修复

**R1. “首批空基线”没有后端依据；e2e 用了后端不会产出的状态**（`WorkbenchPage.tsx`，`emptyBaseline={…node.parent === null}`；`e2e/workspace-shell.spec.ts:109–111`）

- **现状：**
  - 实现把“当前基线没有父节点”（即 `INITIAL` 基线）当作空基线，禁用第 ① 步；
  - 后端没有“空基线”这一事实。`INITIAL` 基线的提交来自部署映射文件中的 `business_baseline_commit_id`（`infrastructure/control_db/sqlite_mapping.py:191–223`），可以是一个有内容的提交；
  - 后端也不拒绝在 `INITIAL` 基线上做 FULL 上传。按现在的判断，凡是当前基线为初始基线的项目都不能选择原始组态备份；
  - e2e 的 `emptyBaseline` 把当前的**归档**基线的 `parent` 改成 `null`。后端不允许这种状态：`ARCHIVED_SUBMISSION` 基线必须有父节点（`domain/baseline/models.py:40–47`）。截图 `upload-empty-baseline-*` 中，树上的当前基线仍是“归档基线”，下面还有“初始基线”。这违反 §7.5 的后端可达状态。
- **请 owner 决定（D1）：**
  - **甲（建议）：** FE2 不禁用第 ① 步。前端没有可靠的判断依据，禁用会挡住合法的 FULL 上传；在空基线上多传一份原始备份不会出错。UI 优化方向 §7.2 的这一条写为缺口，登记到前端 kickoff §3.3，由后端在 History 中提供“基线为空”的事实后再接入。
  - **乙：** 以 `baseline_kind === "INITIAL"` 视为空基线，接受“初始基线有内容的项目不能 FULL 上传”的限制，并在 kickoff 中写明这条约定。
- **无论选哪个，都要改：**
  - e2e 不再修改归档基线的父节点。如选乙，用一个只有 `INITIAL` 基线的 History 场景；
  - 判断用 `baseline_kind`，不用 `parent === null`；
  - 第 ① 步下的两段说明保留一段（m3）。

**R2. 上传、Preview 被 4xx 拒绝后，“重试”仍发送原来的请求**（`UploadStepCard.tsx` 的 `start()` 异常处理）

- handoff §9 的规则是：“上传被 4xx 拒绝……时换新”“Preview 返回 4xx 时换新”。
- 实现只在 `IDEMPOTENCY_CONFLICT` 时重建进度对象。上传的 `WORKSPACE_VERSION_CONFLICT`、Preview 的 `WORKSPACE_VERSION_CONFLICT` 与 `PREVIEW_BINDING_CONFLICT`（`openapi.json` 中这两条路由声明的 409）之后，进度对象中仍是原来的工作区版本、上传 key、Preview key，`baselineHeadVersion` 也仍取自页面加载时的 History 头；
- 卡片提示“工作区或基线已被更新，请刷新后重试”，同时给出“重试”按钮。点“重试”会发出同样的请求，必然再次冲突。e2e `FE2c 上传与 Preview 的 403、版本冲突就地显示错误码` 只断言了错误码，没有点“重试”。
- **修复：**
  - 按 §9 的规则实现：确定的 4xx 之后，丢弃该步及其后各步的 key 与已知结果。429 `ADMISSION_LIMIT_REACHED` 与上传的 408 `UPLOAD_STREAM_TIMEOUT` 结果不确定，保留 key；
  - 版本冲突时不显示“重试”，改为“刷新”，重新读取工作区与 History 头；或者在重试前先重新读取；
  - 加一条测试：版本冲突之后操作一次，第二次请求带新版本、新 key 并成功。

**R3. 上传包校验脚本不符合 §7.1 的入口约束；“config digest” 实为 image ID**（`frontend/scripts/validate-upload-package.sh`）

§7.1 要求该脚本的约束与日志字段“同上文‘生成入口’”。`generate-backend-bundle-fixtures.sh` 已经实现了这些，可以直接沿用。目前缺少：

- 运行前核对 `vnext/backend/uv.lock`、`vnext/backend/.python-version` 与依赖镜像记录的输入，不一致即停止；`pyproject.toml`、`Cargo.lock` 的差异只记录；
- 输出目录须为空；现在用 `mkdir -p`，已有内容也照常运行；
- 脚本自己写日志文件（worktree 外）并记录 exit code 与各输入的 SHA256；现在只输出到 stdout，日志由调用者 `tee`，handoff §3 也写了“初跑仅 stdout”；
- config digest 用 `docker image inspect --format '{{.Id}}'` 取得。在节点的 containerd image store 下，这是本机的 manifest 摘要，不是 config digest（AGENTS“镜像身份”）。日志中的工具链“config digest” `sha256:739bf253…` 与 runner 记录的 `sha256:a0d7b2b4…a1017` 不同。依赖镜像也要用同样的方法取得 config digest。handoff §7 的两个 config digest 都要改正。

**R4. 审核版本冲突提示中的“刷新审核信息”超出对话框**（`ReviewActions.tsx` 的 `renderError`）

截图 `review-version-conflict-1280/1920`：错误文字、错误码、“复制错误代码”和“刷新审核信息”在同一行，后两个按钮超出提示框和对话框，“刷新审核信息”只露出一个字。这是 N6 新加的操作，用户看不到。

- **修复：** 错误码与操作另起一行，允许换行，并检查其他对话框的同类提示；重拍涉及的截图。

**R5. 归档成功路径与退回仍用提交人身份**（`e2e/workspace-shell.spec.ts:1206`、`:1242`）

N7 要求审核用审核人身份、归档用归档人身份，并核对 token。

- 现在只有审核通过（`:1330`）与归档冲突（`:1409`）两条切换了身份；
- `FE2c 审核退回必须填写理由并可撤回` 的退回、`FE2c 归档主线确认预检、异常与影响` 都在提交人身份下完成，截图右上角为“提交人”；
- 撤回由提交人发起，符合 DC75，不用改。
- **修复：** 退回切换到审核人，归档主线切换到归档确认人，并核对这些请求的 token；重拍这两组截图。

## 4. 次要问题（不阻塞）

- **m1：** `OperationStatusPanel` 的 effect 依赖 `onSucceeded`、`onFailed`。`WorkbenchPage` 在恢复场景下每次渲染都传入新的箭头函数，父组件每次重新渲染，轮询都会中止并重启，“已等待”的计时也从 0 开始。用 `useCallback` 或 ref 保持引用不变。
- **m2：** `FE2c 上传失败后重试不重复上传` 没有固定页面时钟。截图 `upload-failure-retry-*` 顶部的操作卡片显示“已等待 26 小时 16 分 59 秒”，两次运行的截图也不同。另外：
  - 失败发生在 bundle 下载，卡片标题直接显示了模拟接口的 `message`（“比较结果暂时不可用”）。按 C6，界面文案应取自前端文案表，不显示后端 `message`；
  - 页面顶部的操作卡片显示“已完成”，同时上传卡显示失败，用户看到的是两个相反的状态。建议上传卡负责的操作不再另显示操作卡片，或卡片说明“预览已生成，下载失败”。
- **m3：** 空基线时第 ① 步下有两段内容相同的说明（`disabledReason` 与段落）。见 R1。
- **m4：** 提交执行中刷新页面后，只显示操作状态卡片；成功后没有提交结果与“查看提交”入口。上传路径已经能续到差异浏览，提交路径可以照此处理，或在卡片中给出入口。
- **m5：** 生产构建检查只要求产物中出现“错误代码：”等文字，而这些文字在其他组件中本来就有，检查不出某个对话框的错误码被开发模式条件包住。可以保留，但不要把它当作 N6 的证据。
- **m6：** 归档场景中，异常的目标提交仍是 `submission-1`，候选是 `fe2a-history-ref-2`（截图 `archive-blocked-*`）。这本身可能成立（目标提交可以是其他提交），但请在场景注释中写明。

## 5. 复审第 3 轮的范围与要求

1. 等 owner 答复 D1，然后修复 R1–R5。m1–m6 能一起修就修，不修的在 handoff 中说明。
2. 测试：
   - R2：版本冲突后重试或刷新再操作，第二次请求带新版本、新 key 并成功；
   - R3：`uv.lock` 不一致时脚本停止（可用临时改动的一次性 worktree 验证，结果写进 handoff）；
   - R4、R5：重拍涉及的截图。
3. 在 05 的已提交 detached worktree 上完整运行 runner（`--e2e --screenshots`）一次，并运行上传包校验脚本一次。
4. handoff 改正 §7 的 config digest，更新逐项对照中 N7、N8 的状态。
5. 第 3 轮范围为 `e42d40e526..<新 handoff 提交>`，只核对上述各项；通过后在 04 取证一次。04 取证时同样运行上传包校验脚本。

## 6. 本轮在节点上留下的内容

- **开发主机：** 只读 worktree `/home/dev/gdds-fe-rereview2-fe2c-e42d40e5`；bundle `/home/dev/gdds-test-tmp/src-rereview2-fe2c-e42d40e5.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-rereview2-fe2c-e42d40e5-05`；
  - bundle `/home/dev/gdds-test-tmp/src-rereview2-fe2c-e42d40e5.bundle`；
  - 上传包输出 `/home/dev/gdds-test-tmp/fe2c-rereview2-upload-validation/`；
  - 日志与探针 `/home/dev/gdds-fe-logs/fe2c/rereview-2/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2c/rereview2-e42d40e5-05/`。

  探针 worktree 已删除。FE2c 退出合入后，与第 1 轮的内容一起清理。
