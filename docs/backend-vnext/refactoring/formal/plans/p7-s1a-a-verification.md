# P7-S1a A 静态验证执行稿

日期：2026-11-10。状态：**工具故障后修订稿，供原审；本版未执行**。唯一测试角色只在原审核准并收到精确候选A_SHA后执行本稿，不修改产品/参数/预期，不自行重试或换节点，不签GO。

## 1. 范围和前提

本轮用户明示AGENTS/实施提示词优先于main内DC91/新版DC68：使用`ct107-gw-dms-06`做本包静态核验。A只改docs，不跑无关产品测试/lint/编译/容器；完整设计/Contract语义属于独审。开发机不执行本稿。

先`ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`。现场只读核空闲/有效占用与本次源码LAN传输前提；本脚本在执行时原子`mkdir /home/dev/gdds-node-busy.d`并写本会话、用途、UTC，不抢占他人。外层不得预取同一标记；已有有效标记就停止。源码经获准LAN传到本任务独立clean已提交detached worktree；不得在他人路径写入；linked树建legacy link。无依赖/镜像变化，不需要uv/npm/Cargo/Docker制品；不触网补缓存，不运行任何服务。

收到协调者固定：A_SHA、06独立worktree绝对路径、worktree外全新日志目录/会话名，以及本稿/脚本SHA256。启动前原审须明确批准该候选和这两个文件的精确内容，不能边运行边改树。

完整脚本为同目录[p7-s1a-a-verify.sh](p7-s1a-a-verify.sh)。脚本只用Bash、Git、Python标准库、coreutils，无rg依赖；06只读核实已有`/usr/local/bin/rg`、ripgrep 15.1.0不改变本稿逻辑。不得在开发机运行本稿、bash -n或脚本。

脚本路径必须为固定候选clean worktree中的绝对路径。测试角色先在06只读核`bash -n <绝对脚本>`并记录原exit；非0停止。执行前核hostname为`gw-dms-06`，log父目录已存在且在worktree外，新log目录不存在；当前工作树无测试/服务运行者，busy标记空闲。源码/tag/原件对象由获准LAN传输已备妥，linked树legacy链接已被Git忽略。只运行下列固定形式，由协调者填四个参数；脚本自行建日志目录/占用并收尾，不外套另一个改写exit的wrapper：

```bash
bash <CLEAN_WORKTREE>/docs/backend-vnext/refactoring/formal/plans/p7-s1a-a-verify.sh \
  <A_SHA> <CLEAN_WORKTREE> <NEW_LOG_DIR> <SESSION>
```

A_SHA为40位小写hex，SESSION为1–64位`[a-z0-9][a-z0-9_-]*`。不得复用旧失败日志目录、覆盖旧文件或直接在`24394b98`原worktree运行修订稿；新候选用新的clean detached源码/日志。执行从§1重新开始，旧§1–4不拼接为本版完整成功。

## 2. 固定静态核验内容

测试角色只读运行以下项目，完整记录命令stdout/stderr、原numeric exit。基准S固定`5ddd73b962e2432f961a46f6743395a53a388435`，输入提交I固定`bc184e5007`；A_SHA必须是I后继。

1. 记录hostname、UTC、HEAD、`git status --porcelain`；要求HEAD=A_SHA且tracked/untracked clean（legacy链接已由Git忽略）。`git merge-base --is-ancestor S HEAD`及`git merge-base --is-ancestor I HEAD`都为0。
2. `git diff --check S HEAD`要求0。`git diff --name-only S HEAD`逐路径只允许本稿§3清单；不得有产品/golden/FE/P6证据/共享AGENTS与testing-conventions改动。
3. `git rev-parse HEAD:vnext`必须为`49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`；`git diff --exit-code S HEAD -- vnext frontend AGENTS.md docs/backend-vnext/testing-conventions.md`要求0。
4. 只读核`git diff --name-only b0fc25e881cb4ce39b1cc847bad92b4ccb06b809 S`，应仅`docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`及`docs/frontend-vnext/reviews/fe3c-fix2-check.md`；`git rev-parse p6-exit^{commit}`等于B。tag不在传输范围则记录源对象核验限制并停止，不伪造tag。
5. 用`git show I:<七路径>`逐一`sha256sum`，与入口§1七行完全一致；这是原件身份核验，不要求后续编辑的当前文件仍等于原件。
6. 逐一确认新增A入口/本稿和各新增Contract目标中的Markdown本地文件链接指向存在的tracked文件；anchor由原审核标题/显式anchor，不让通用slug脚本误判中文或旧锚点。本轮新目标均标“待实现”，现行Contract版本未提升；这是静态状态核查，产品断言不记PASS。
7. 结尾重新记录hostname、UTC、HEAD、clean、各项exit/整稿exit；HEAD不变。日志worktree外，退出后计算SHA256并旁注。失败停止依赖验收，保原日志/SHA按本轮DC68处理；不无修改重试。

脚本完整承载上述断言：§2的白名单检查与§6的新增Markdown文件链接检查在同一标准库块执行（先于其余内容检查），不校验旧存量链接/中文slug，不增加产品断言。Contract生效/版本语义与anchor仍由原审核收；脚本只确认待实现标识，不把文本标识当实现证明。不安装依赖，不运行仓库Python产品模块。输出不过滤掉失败/未知。测试者不现场改脚本、预期或用替代命令继续失败链。

## 3. 允许变更路径

七份输入（`docs/backend-vnext/refactoring/formal/plans/`下）：`p7-s0-owner-decisions.md`、`p7-design.md`、`p7-execution-plan.md`、`p7-s1a-storage-resource-design.md`、`p7-s1a-execution-plan.md`、`p7-processing-groups-and-test-extraction-design.md`、`p7-s1a-implementation-prompt.md`。

本包新增同目录`p7-s1a-a-entry-and-contract.md`、`p7-s1a-a-verification.md`、`p7-s1a-a-verify.sh`（纯文档验证工具，不在vnext/闭包中）。

`docs/backend-vnext/refactoring/formal/contracts/`下：`canonical-storage-and-repository-boundary.md`、`operation-lifecycle-and-integrity.md`、`business-lifecycle-and-state.md`、`storage-mutation-and-change-set.md`、`repository-service.md`。

`docs/backend-vnext/contracts/`下：`snapshot-table-access.md`、`comparison-bundle.md`、`comparison.md`、`risk.md`；及`docs/backend-vnext/artifacts.md`。

## 4. 收尾/回执

没有服务/容器/临时卷需启动或清理。脚本EXIT trap在成功/失败均记录结尾hostname/UTC/HEAD/clean与原numeric exit；只在自己原子取得标记且owner内容仍匹配时删除本人marker文件、rmdir忙目录，不递归删内容，不动他人标记。busy冲突时不释放；owner不符或release失败非0保现场，交协调者，不抢占。传输/source/原件保留，不自动删本任务证据。

stdout/stderr写NEW_LOG_DIR/verification.log并同时tee；等tee结束再计算日志SHA256。另记exit-codes.txt的VERIFIER_EXIT与LOGGER_EXIT；保RUN_ORIGINAL_EXIT与收尾后的RUN_FINAL_EXIT，失败不被后续成功覆盖。tee失败也非0，不能拿缺失日志签通过。最终原始SSH numeric exit由测试角色另保留。原日志SHA在verification.log.sha256旁注，不写进自身产生自引用。只核本任务资源并释放本人占用；保留被引用成功/失败原日志与源码worktree。交付节点、A_SHA、起止UTC/HEAD、原exit、日志/SHA、各检查实际结果、限制与本人占用释放事实。不能将本包静态核验表述为B–F产品已实现或P7容器通过；原审决定是否核收A。

## 5. 首次失败与本次最小修复

Owner已明确允许修复继续。原运行节点06，候选`24394b98a6e6f9bea89c404b44cf0dde691a8044`，稿SHA256=`5b5e7737bee7fc1f5fd6b3ee1b505f5da3f95ee864bf601c7c61ddae36a5ef47`。§1–4有部分原日志，§5第一个git show/SHA命令之前wrapper因`set -u`退出1，§5–7未完成，不能称静态验证PASS。

故障原行：

```bash
local filename="$1" expected="$2" output="$logdir/original-${filename%.md}.sha.out"
```

同条local的全部RHS在赋值前展开，output读取尚未赋值的filename。最小修复是先独立声明/赋值filename与expected，再单独赋output（完整脚本check_original函数）；不改七份原件hash、范围、candidate/tree断言、预期或产品。完整wrapper当时未独立保存，原始行与stderr留在错误记录；本次脚本从已审§1–7定稿为可直接审阅的完整文件，不把重建脚本冒称当时原件。

只读核对原件，均保留不覆盖：

| 06原件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-test-tmp/p7-s1a-a-static-24394b98/logs/verification.log` | `9199ceffb160f6e2243732159c5d98013f0a3b7a0e06b43cc33166fe053965bc` |
| `/home/dev/gdds-test-tmp/p7-s1a-a-static-24394b98/logs/verification-wrapper-error.log` | `8c295a62fae7017a9c1da8017ddfa329b78f804be097ae683d92fecbad9cc93b` |

错误记录绑定最后只读核的2026-11-10T03:34:34Z、原HEAD与clean；没有产品/原worktree改动。恢复前仍由测试角色核现场空闲并按新稿取本人标记，不以旧快照预留资源。首次故障和本次修复写入handoff；本修订尚未执行，待原审SCRIPT_GO后唯一测试角色运行。
