# 实施 kickoff：设备目录系统 v1（`directory/`）

你是“设备目录系统 v1”的实施者。设备目录是独立于网关机数据管理系统（下称“网关系统”）的一套小系统：按 地区一 → 地区二 → 项目 浏览或搜索项目，再跳转到网关系统中该设备的数据提交树。设计已由 owner 确认，你按设计实现，不重新设计。

## 1. 先读

1. `AGENTS.md`：节点分工、离线缓存（DC67）、测试取证、日志与 clean worktree 规则都适用于本任务。
2. `docs/device-directory/design.md`：设计，包括业务约束 B1–B11 和已确认事项 Q1–Q5。
3. `docs/device-directory/interfaces.md`：接口约定 I1–I8，是本任务的验收依据。
4. `docs/device-directory/sketches/*.png`：界面草图（1280、1920 浏览，1920 搜索）。
5. 参考实现（只读，不修改）：
   - `vnext/backend/tests/support/compose_gate_harness.py` 中的 `seed_repository_and_mapping`、`start_three_container_stack`、`worker_ready`：建仓库、写映射文件、启动服务并等待就绪的现有做法；
   - `vnext/backend/src/gateway_backend/http/auth.py` 中的 `load_session_entries`、`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py` 中的 `load_provisioned_mapping_file` 和 `_validate_seed_batch_reverse_scope`：网关读取这两个文件的规则，I4 的自检要与它们一致；
   - `vnext/deploy/compose.yaml`、`vnext/deploy/README.md`：两个文件的挂载方式和权限名；
   - `frontend/scripts/run-tests.sh`：前端工具链镜像、身份校验和离线 npm 的做法。

## 2. 基线与边界

- 从 `main` 的最新提交（应包含 `18d290f20b`）创建短期分支 `dir-v1`，在独立 worktree 中开发，例如 `/home/dev/gdds-dir-v1`。不推送。
- 只改 `directory/` 和 `docs/device-directory/`。**不改 `vnext/`、`frontend/`。**确实需要改时先停下报告。
- 网关前端的跳转入口由另一个任务 `fe-handoff` 实现，你不实现。

## 3. 目录结构与依赖

```
directory/
  service/       Python 包 gdds_directory：目录服务与命令行
  frontend/      目录前端（Vite + React + TypeScript）
  scripts/run-tests.sh   本系统唯一的测试入口
  README.md      启动、配置、开通步骤
```

**服务（Python）：**

- 使用 `pyproject.toml`、`uv.lock`；`.python-version` 为 `3.14.6`，与 `vnext/backend` 一致。
- 运行时只用标准库：`http.server` 的 `ThreadingHTTPServer`、`sqlite3`、`csv`、`hashlib`、`unicodedata`、`gzip`、`secrets`、`json`、`subprocess`。
- 开发依赖只允许 `pytest==9.1.1`、`ruff==0.15.21`、`mypy==2.3.0`，与 `vnext/backend/uv.lock` 相同的版本，这样节点上已预填充的 uv 缓存能命中。需要其他依赖时先停下报告。
- mypy 用 `strict = true`，覆盖测试代码。
- 命令行入口是 `gdds-directory`，子命令见 I8。服务以 `gdds-directory serve` 启动；I8 没有列出这个子命令，请在本分支同时把它补进 `interfaces.md` 的 I8。
- 静态文件目录如果需要配置，新增 `GDDS_DIRECTORY_STATIC_DIR`，并同步补进 I7。

**前端：**

- 与 `frontend/package.json` 共有的包，一律用相同的精确版本：`react`、`react-dom` 18.3.1，`vite` 8.3.5，`@vitejs/plugin-react` 6.2.0，`typescript` 5.9.3，`vitest` 5.0.5，`jsdom` 30.1.3，`eslint` 10.14.0，`@eslint/js` 10.0.1，`typescript-eslint` 8.72.1，`globals` 17.14.0，`@types/react` 18.3.31，`@types/react-dom` 18.3.7，`@playwright/test` 1.64.1，可选 `lucide-react` 1.66.0。
- 不引入路由库、状态库或拼音库：拼音由导入方提供（B6）。
- `package-lock.json` 在 CT201 生成；npm 缓存按 DC67 预填充到 07 节点。handoff 中记录来源提交、缓存摘要和预填充时间。
- 不依赖 `frontend/` 的代码。视觉沿用其配色与字号，需要的 token 复制过来。

## 4. 功能要求

按下列章节实现，细节以文档为准。文档有歧义或互相矛盾时先停下报告，不自行取舍。

| 部分 | 依据 | 重点 |
| --- | --- | --- |
| 唯一键 | I2 | I2 表中的三个例子作为固定测试用例 |
| 数据库 | design §4 | 站号为主键；开通记录只在建仓成功后写入 |
| 导入 | design §5、I1 | 整份替换，全部校验通过才生效；逐行错误码；`--dry-run`；移除与恢复；输出摘要 |
| HTTP 接口 | I3 | ETag 与 304、gzip、`Cache-Control: no-store`；错误响应体格式；`return_query` 校验；`/api/` 未知路径返回 JSON 404 |
| 开通 | design §6、I4、I5、I8 | 见下文 |
| 前端 | design §8、草图 | 见下文 |
| 配置 | I7 | 必填项缺失时启动失败，并说明缺了哪一项 |

**开通（`provision`）：**

- 步骤顺序严格按 design §6：
  1. 逐台建仓库，每建成一个就写入开通记录；
  2. 停止 backend 与 worker；
  3. 自检后原子替换两个文件；
  4. 启动 backend 与 worker，等待 backend `/readyz` 返回成功、worker 就绪。
- 写文件时，带 `"issuer": "device-directory"` 的条目整体重新生成，其他条目和顶层字段原样保留。自检规则与网关加载器一致。
- Compose 调用封装成一个可替换的接口。单元测试用替身，不在单元测试里启动 Docker。
- 中断后重跑：已建仓库不重复建，文件和重启步骤可以整段重跑。用测试证明重跑不重复建仓库、不破坏不归目录管理的条目。
- token 不写入任何日志、标准输出、异常信息或测试快照。

**目录服务：**

- 运行时只读自己的 SQLite，不写网关的任何文件，不调用 Docker。用测试证明这一点。

**前端：**

- 布局与交互按草图。数据一次从 `/api/catalog` 取回，地区树、计数、搜索、同名标记都在浏览器内计算。
- 地址状态（`r1`、`r2`、`q`、`scope`、`page`）、搜索规则与排序按 design §8。
- “未开通”的设备，“进入”位置显示“未开通”，不可点击。
- 最近访问存在 `localStorage`，所有读写都包在 try/catch 中；存储不可用时页面照常工作。
- 跳转失败（404、409 未开通、409 会话过期）时，显示中文提示，不跳转。
- 还没有导入过名单（503 `CATALOG_EMPTY`）时，显示空状态。加载失败时显示错误状态并可重试。
- 键盘：↑↓ 选择，Enter 进入，`/` 聚焦搜索，Esc 清除搜索。

## 5. 测试与节点

- 唯一入口为 `directory/scripts/run-tests.sh`，可以拆成 `--service`、`--frontend` 两部分：
  - 服务部分：在 06 节点运行，`UV_OFFLINE=1`，依次执行 ruff、mypy、pytest；
  - 前端部分：在 07 节点运行，使用 `frontend/scripts/run-tests.sh` 的同一工具链镜像和身份校验，网络为 none，`npm ci --offline`，`GATEWAY_FE_TEST_WORKERS=2`，依次执行类型检查、lint、单元测试、构建，以及 mock e2e 和截图。
- 不在开发主机上运行测试。在 clean、已提交的 worktree 中运行。日志写到 worktree 之外，记录 hostname、起止时间、起止 HEAD、exit code，以及日志的 SHA256。
- 本系统不并入 `vnext/scripts/run-tests.sh` 和 `frontend/scripts/run-tests.sh`（Q2）。
- 测试按业务行为命名，每个不变量只有一个权威测试。导入校验这类只有输入和期望错误码不同的用例，收敛成模块级参数表（参照 `AGENTS.md`“测试性能红线”）。
- 截图：浏览、搜索、未开通、跳转失败、空目录，五个状态，每个状态截 1280 和 1920 两种宽度。截图存放在 worktree 外的证据目录，并记录 SHA256。与草图对照，不一致的地方要么修正，要么作为偏差写进 handoff。

## 6. 阶段与交付

**阶段 1：实现与单元验证。**完成第 4、5 节后，写 `docs/device-directory/handoff-dir-v1.md`，内容包括：

- 提交列表；
- 对文档的偏差及理由；
- 测试日志，包括节点、hostname、HEAD、exit code、SHA256；
- 缓存预填充记录；
- 截图清单及 SHA256；
- 未解决问题。

写完后停下，等待审核。审核在只读的 detached worktree 中进行。

**阶段 2：端到端验收。**审核通过、且 `fe-handoff` 已合入 `main` 之后，再开始阶段 2。在包含两项改动的提交上运行，地点是 05 节点。05 上的 Compose 占用 8000 端口，要按 DC70 补充取得整机占用标记 `/home/dev/gdds-node-busy.d`，用完删除。步骤：

1. 启动网关 Compose 栈。
2. 导入样例名单。名单至少包含：2 个地区一、同名项目、多音字拼音。
3. 开通 2 台设备 A、B。
4. 启动目录服务；以 `vite preview` 启动网关前端，`/v1` 代理到 backend。
5. 从目录搜索并进入 A。确认：
   - 地址片段已清除；
   - 显示“尚无数据”，上传入口可用；
   - 用 `frontend/e2e-real` 已有的样例包完成上传 → Preview → 提交 → `test1` 审核通过；
   - 在差异浏览页刷新，仍在 A 中。
6. 返回目录，进入 B，确认看不到 A 的数据。
7. 执行 `provision --renew-sessions`，确认旧 token 返回 401，新 token 可用。

步骤 3 和 5 同时验证 design 中待实测的三点：

- 重启后容器读到的是新写入的文件；
- 只有初始基线的设备可以上传；
- `test1` 能审核本人的提交。

任何一点与设计不符，就停下报告并附上证据，不要自行绕过。

## 7. 必须停下报告的情况

- 需要改 `vnext/` 或 `frontend/`，或需要新增依赖；
- 文档有歧义或互相矛盾；
- 网关系统的实际行为与 design 的描述不符；
- 缓存缺失，或工具链镜像身份不符（按 DC67、DC68 处理）。
