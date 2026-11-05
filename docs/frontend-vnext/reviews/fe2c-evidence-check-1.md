# FE2c 证据核对（第 1 次）

- **核对对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `e3835718eb6879a7461c176820c5576f87c48b81`，`frontend/` 树 `960ab1f6a1f7f368d47824b3e1570be85be517c5`；
  - 04 运行的提交 `220325da3770fc94ce610a73f983cd26871e4a65`（第 4 轮 handoff，`frontend/` 树相同）；
  - 证据 handoff 提交 `749f219d5ff0d621d8e35a3fcb4b5521ecb6f264`。相对 `220325da37` 只改 `docs/frontend-vnext/fe2c-handoff.md`，`frontend/` 树相同。
- **依据：** [复审第 4 轮](fe2c-rereview-4.md) §3、§5；AGENTS“前端测试（FD7）”“镜像身份”。
- **日期：** 2026-11-04。
- **结论：通过（PASS）。** 04 的 runner 与上传包校验各运行一次，都通过；日志、镜像身份、npm 缓存、截图都与 handoff 一致；复审第 4 轮 §3 的 4 处改正都已完成。可以在 `749f219d5f` 上打 `fe-fe2c-exit`。

## 1. 04 运行

节点 `ct108-gw-dms-04`，hostname `gw-dms-test-04.lan`。核对时 04 没有占用标记。

| 项 | 核对结果 |
| --- | --- |
| bundle | `/home/dev/gdds-test-tmp/fe2c-fix4-220325da.bundle`，SHA256 `504c2c53…92a2ef`，与 handoff 一致 |
| worktree | `/home/dev/gdds-fe-fix4-220325da-04`：已在 04 主仓库注册的 detached worktree，HEAD `220325da37`，clean，`legacy` 链接正确 |
| runner | 日志 `/home/dev/gdds-fe-logs/fe2c/fix-4-04/frontend-tests-20261104T160110Z.log`，SHA256 `71f91ada…6e6550`，与 handoff 一致。`16:01:10Z`–`16:02:02Z`，起止 hostname 都是 04，起止 HEAD `220325da37`，起止 `frontend/` 树 `960ab1f6a1`，`run_e2e=1`，exit 0；27 个单测文件 130 项、生产检查、32 个 e2e 全部通过 |
| 上传包校验 | 日志 `upload-validator-220325da37-20261104T160214Z-1550759.log`，SHA256 `2e4b62c0…560630`，与 handoff 一致。`final_stage=done`，exit 0；`required_inputs_match=true`，`pyproject.toml`、`Cargo.lock` 只记录差异；4 个包结果符合预期（`missing-dbcfg` 被拒收，`UPLOAD_CLOSURE_INVALID`）；输出目录在 worktree 外 |
| 运行次数 | `/home/dev/gdds-fe-logs/fe2c/` 下只有 `fix-4-04/` 一个目录，其中只有上述两份日志；bundle 之后没有其他新日志。与“各运行一次”一致 |
| npm 缓存 | runner 日志记录 `/home/dev/gdds-fe-cache/frontend/npm-cache`，来源归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，来源提交 `a2fb4a027a`。我在 04 上重新计算归档 SHA256，为 `0d861824…089f4` |

## 2. 镜像身份

我从 04、05 的日志中取出两个镜像的 config digest 与全部 DiffID，用脚本逐项比较。05 的日志是我在复审第 3、4 轮中运行的。

- **工具链** `mcr.microsoft.com/playwright:v1.64.1-noble`：
  - config digest 均为 `sha256:a0d7b2b4…a1017`；
  - 7 个 DiffID 在以下四份日志中顺序与取值都相同：04 runner、05 runner、04 校验脚本、05 校验脚本。
- **依赖镜像** `gateway-backend-deps:lock-d054366c02fa`：
  - config digest 均为 `sha256:b5b54224…e4b92a`，与 FE1 handoff 的记录相同；
  - 19 个 DiffID 在 04、05 两份校验日志中相同。
- **handoff §7：** 列出的 7 个与 19 个 DiffID，和日志逐项相同。
- **上传包：** 04 与 05 生成的 4 个 `.tar.gz` 的 SHA256 相同，前端打包结果在两个节点上可重现。

## 3. 截图

- 04 目录 `/home/dev/gdds-fe-evidence/fe2c/fix-4-220325da-04`，94 张，1280 与 1920 两种宽度。
- 按 handoff 写明的公式（`sha256sum *.png | sort -k2 | sha256sum`）重算，聚合 SHA256 为 `c2420b21…e0e920a`，与 handoff 一致。按前几轮的公式（`find . -name '*.png' -print0 | sort -z | xargs -0 sha256sum | sha256sum`）计算为 `cbd234529171f1efd8bec9fc8a258f18735626bb578e5d79e918fbb4db1a7af3`。
- 文件名与我在 05 上的运行（复审第 4 轮）一致，84 张逐字节相同。不同的 10 张是执行中、抽屉与几个对话框，属于前几轮就有的渲染差异。
- 抽看了 `archive-audit-conflict-1920`、`review-withdraw-dialog-1920`：
  - 错误码与“刷新预检”在可视区域内；
  - 撤回说明完整显示“此操作不可撤销”。

## 4. handoff 改正

复审第 4 轮 §3 的 4 处都已改正：

1. n2 改为“完成”，已从偏差中删除；
2. R6 的描述写明审核“刷新审核信息”仍在正文中，只补了断言；
3. §3、§4 注明探针是未提交改动上的 focused Playwright，不作为证据；
4. §5 写明截图聚合公式。

剩余偏差只有 n3（提交续做的失败分支没有专门 e2e）。N8 的“部分”来自 Q18，已登记为缺口。两项都已在复审中接受。

## 5. 退出建议

- 在 `749f219d5ff0d621d8e35a3fcb4b5521ecb6f264` 上打 `fe-fe2c-exit`。tag 说明中写明：
  - 测试提交 `220325da37`（代码候选 `e3835718eb`）；
  - `frontend/` 树 `960ab1f6a1`；
  - 范围 `fe-fe2b-exit..749f219d5f`。
- 合入 main 时一并带上 FE2c 的审核报告：
  - `fe2c-review.md`、`fe2c-rereview-1.md`～`fe2c-rereview-4.md`；
  - 本报告。
- **FE2c 遗留与后续：**
  - 复审第 4 轮 n8（需要管理员处理那一行的排版）；
  - n3 的失败分支 e2e；
  - Q16、Q18 的缺口：前端 kickoff §3.3。
- **退出后清理：**
  - 审核会话的 worktree、bundle、日志与截图（复审各轮报告 §6 列出）；
  - 实施会话的 worktree 与 bundle；
  - 04 上的 `/home/dev/gdds-fe2c-gate`：FE2c 首轮在 04 上留下的 detached worktree，HEAD 为 `dfe0ed52`，即原审核 M5 所述；
  - 04 上的 `/home/dev/gdds-fe-evidence/fe2c/{a2bcaf86,48f4e020,dfe0ed52}-04`。
  - 04 取证的 worktree、日志与截图保留到合入之后。
