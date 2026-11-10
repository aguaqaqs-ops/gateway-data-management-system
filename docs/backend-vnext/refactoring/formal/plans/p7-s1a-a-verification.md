# P7-S1a A 静态验证执行稿

日期：2026-11-10。状态：**供原审；未执行**。唯一测试角色只在原审核准并收到精确候选A_SHA后执行本稿，不修改产品/参数/预期，不自行重试或换节点，不签GO。

## 1. 范围和前提

本轮用户明示AGENTS/实施提示词优先于main内DC91/新版DC68：使用`ct107-gw-dms-06`做本包静态核验。A只改docs，不跑无关产品测试/lint/编译/容器；完整设计/Contract语义属于独审。开发机不执行本稿。

先`ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`。现场只读核空闲/有效占用与本次源码LAN传输前提；需要占用时原子`mkdir /home/dev/gdds-node-busy.d`并写本会话、用途、UTC，不抢占他人。源码经获准LAN传到本任务独立clean已提交detached worktree；不得在他人路径写入；linked树建legacy link。无依赖/镜像变化，不需要uv/npm/Cargo/Docker制品；不触网补缓存，不运行任何服务。

收到协调者固定：A_SHA、06独立worktree绝对路径、worktree外日志目录/会话名。启动前原审报告须明确本稿对应A_SHA或明确其无语义变化的稿摘要，不能边运行边改树。

## 2. 固定静态核验内容

测试角色只读运行以下项目，完整记录命令stdout/stderr、原numeric exit。基准S固定`5ddd73b962e2432f961a46f6743395a53a388435`，输入提交I固定`bc184e5007`；A_SHA必须是I后继。

1. 记录hostname、UTC、HEAD、`git status --porcelain`；要求HEAD=A_SHA且tracked/untracked clean（legacy链接已由Git忽略）。`git merge-base --is-ancestor S HEAD`及`git merge-base --is-ancestor I HEAD`都为0。
2. `git diff --check S HEAD`要求0。`git diff --name-only S HEAD`逐路径只允许本稿§3清单；不得有产品/golden/FE/P6证据/共享AGENTS与testing-conventions改动。
3. `git rev-parse HEAD:vnext`必须为`49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`；`git diff --exit-code S HEAD -- vnext frontend AGENTS.md docs/backend-vnext/testing-conventions.md`要求0。
4. 只读核`git diff --name-only b0fc25e881cb4ce39b1cc847bad92b4ccb06b809 S`，应仅`docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`及`docs/frontend-vnext/reviews/fe3c-fix2-check.md`；`git rev-parse p6-exit^{commit}`等于B。tag不在传输范围则记录源对象核验限制并停止，不伪造tag。
5. 用`git show I:<七路径>`逐一`sha256sum`，与入口§1七行完全一致；这是原件身份核验，不要求后续编辑的当前文件仍等于原件。
6. 逐一确认新增A入口/本稿和各新增Contract目标中的Markdown本地文件链接指向存在的tracked文件；anchor由原审核标题/显式anchor，不让通用slug脚本误判中文或旧锚点。本轮新目标均标“待实现”，现行Contract版本未提升；这是静态状态核查，产品断言不记PASS。
7. 结尾重新记录hostname、UTC、HEAD、clean、各项exit/整稿exit；HEAD不变。日志worktree外，退出后计算SHA256并旁注。失败停止依赖验收，保原日志/SHA按本轮DC68处理；不无修改重试。

可用标准Git、sha256sum、rg、Python标准库作纯文档链接/白名单核对，不安装依赖，不运行仓库Python产品模块。输出不过滤掉失败/未知。已有错误修订先固定新稿并经原审，测试者不现场改预期。

## 3. 允许变更路径

七份输入（`docs/backend-vnext/refactoring/formal/plans/`下）：`p7-s0-owner-decisions.md`、`p7-design.md`、`p7-execution-plan.md`、`p7-s1a-storage-resource-design.md`、`p7-s1a-execution-plan.md`、`p7-processing-groups-and-test-extraction-design.md`、`p7-s1a-implementation-prompt.md`。

本包新增同目录`p7-s1a-a-entry-and-contract.md`、`p7-s1a-a-verification.md`。

`docs/backend-vnext/refactoring/formal/contracts/`下：`canonical-storage-and-repository-boundary.md`、`operation-lifecycle-and-integrity.md`、`business-lifecycle-and-state.md`、`storage-mutation-and-change-set.md`、`repository-service.md`。

`docs/backend-vnext/contracts/`下：`snapshot-table-access.md`、`comparison-bundle.md`、`comparison.md`、`risk.md`；及`docs/backend-vnext/artifacts.md`。

## 4. 收尾/回执

没有服务/容器/临时卷需启动或清理。只核本任务资源并释放本人占用；保留被引用成功/失败原日志与源码worktree。交付节点、A_SHA、起止UTC/HEAD、原exit、日志/SHA、各检查实际结果、限制与本人占用释放事实。不能将本包静态核验表述为B–F产品已实现或P7容器通过；原审决定是否核收A。
