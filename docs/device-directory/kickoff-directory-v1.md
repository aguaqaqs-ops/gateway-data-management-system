# 实施 kickoff：设备目录系统 v1（`directory/`）

**修订状态（2026-11-12）：** owner 已确认处理组接入修订为正式设计。阶段 1 按 [详细执行计划](execution-plan-directory-v1.md) 开始实施；本轮文档确认不表示阶段 1 已完成或阶段 2 已放行。

你是“设备目录系统 v1”的实施者。设备目录是独立于网关机数据管理系统（下称“网关系统”）的一套小系统：按 地区一 → 地区二 → 项目 浏览或搜索项目，再跳转到网关系统中该设备的数据提交树。业务范围和 Q1–Q5 已由 owner 确认；处理组接入按已确认的 design/interfaces 执行，不由实施者另行设计。

## 1. 先读

1. `AGENTS.md`：节点分工、离线缓存（DC67）、测试取证、日志与 clean worktree 规则都适用于本任务。
2. `docs/device-directory/design.md`：设计，包括业务约束 B1–B11 和已确认事项 Q1–Q5。
3. `docs/device-directory/interfaces.md`：接口约定 I1–I8，是本任务的验收依据。
4. `docs/device-directory/sketches/*.png`：界面草图（1280、1920 浏览，1920 搜索）。
   实施顺序、测试归属和证据要求另须阅读 [execution-plan-directory-v1.md](execution-plan-directory-v1.md)。
5. 参考实现（只读，不修改）：
   - `vnext/scripts/manage-processing-groups.py`：`add_device`、`session_document`、`merge_sessions`、`require_unique_session_tokens`，作为开通、会话 schema 与跨组唯一性边界；注意工具只追加会话，不承担旧 token 撤销。
   - `vnext/scripts/processing_group_locks.py`、`processing_group_entry.py`：宿主锁顺序、发布与 probe 协议；复用 helper，不复制第二套 nginx 发布器。
   - `vnext/backend/src/gateway_backend/application/provisioning/registration.py` 与 `http/routes/device_registration.py`：幂等建仓/登记和固定 INITIAL 回执；不得按旧设计自行建仓或生成 INITIAL。
   - `docs/backend-vnext/refactoring/formal/contracts/processing-groups-and-routing.md`、`vnext/deploy/compose.yaml`、`vnext/deploy/README.md`：处理组部署、公共入口及 session 父目录挂载。
   - `frontend/scripts/run-tests.sh`：前端工具链镜像、身份校验和离线 npm 的做法。

## 2. 基线与边界

- 本任务已在 `/home/dev/gdds-dir-v1` 的 `dir-v1` 分支开始，产品基线为 `main@eb6530b36e`，包含 `18d290f20b`；继续追加提交，不重新创建/重置分支或改写已有交接提交。恢复实施前核对最新 `main`、分支独有提交与工作区，处理基线变化见执行计划。不推送。
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
- 运行时只用标准库：包括 `http.server` 的 `ThreadingHTTPServer`、`sqlite3`、`csv`、`hashlib`、`unicodedata`、`gzip`、`secrets`、`json`、`subprocess`，以及宿主适配所需的 `urllib`、`fcntl`、文件与时间处理模块；复用既有网关 stdlib helper 不新增第三方依赖。
- 开发依赖只允许 `pytest==9.1.1`、`ruff==0.15.21`、`mypy==2.3.0`，与 `vnext/backend/uv.lock` 相同的版本，这样节点上已预填充的 uv 缓存能命中。需要其他依赖时先停下报告。
- mypy 用 `strict = true`，覆盖测试代码。
- 命令行入口是 `gdds-directory`，包含 I8 已定义的 `serve`。可用源代码包加仓库内可执行 launcher 实现，不为安装入口引入未经允许的第三方 build backend。
- 静态文件目录使用 I7 已定义的 `GDDS_DIRECTORY_STATIC_DIR`。

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
| 数据库 | design §4、§6 | 站号为主键；先保存待生效凭据，成功确认后保存登记回执并开放 handoff；开通更新目录版本 |
| 导入 | design §5、I1 | 整份替换，全部校验通过才生效；逐行错误码；`--dry-run`；移除与恢复；输出摘要 |
| HTTP 接口 | I3 | ETag 与 304、gzip、`Cache-Control: no-store`；错误响应体格式；`return_query` 校验；`/api/` 未知路径返回 JSON 404 |
| 开通与续期 | design §6、I4、I5、I8 | 复用宿主管理工具，续期按现有锁替换自身会话，见下文 |
| 前端 | design §8、草图 | 见下文 |
| 配置 | I7 | 必填项缺失时启动失败，并说明缺了哪一项 |

**开通与续期（`provision`）：**

- 固定一个预先部署的处理组及公共入口；使用 I7 的清单配置，从清单派生环境、端点、session 和凭据路径，不创建处理组、不自动分组。
- 新增按 design §6.1：先在目录 DB 保存目标与待生效 token，再用私有临时 session 文档调用现有 `add-device`；工具 exit 0 后查询 registration 固定回执，并用本次 token 经公共入口核 scope，完成本地记录后才允许 handoff。
- 宿主适配器可替换，单元测试用替身，不启动 Docker。目录不写 seed 映射或路由 JSON，不直接建仓、不重启 backend/worker、不自己实现 nginx 发布。
- 重跑使用同一设备/项目/环境/组及待生效凭据，证明不重复创建仓库、未完成项不提前可进入。busy/未完成保留工具 exit code 和本地记录，不能把 enabled/HUP 成功替代 available。
- 续期按 design §6.2：复用 publication → group management 锁，在锁内重读并校验会话、全局 token 唯一性和文件上限，原子替换 SQLite 精确归属的会话；保留其他合法条目。不加 `issuer` 或未知顶层字段。
- 用一个中断用例证明替换后、DB 收尾前退出可用持久待生效 token 完成恢复；其他输入/归属冲突用参数表证明拒绝且不误写。续期中 handoff 返回 `SESSION_UPDATING`，新 token 的 scope 正确、旧 token 的后续新请求为 401 后才报告成功。
- 不建立跨文件分布式事务或第二网关恢复器。过期/未知/冲突按已知状态报告，不猜测业务事实。按每文件 1 MiB 与路由目录 10000 条/8 MiB 的现有限制做批次预检，不做额外规模评估。
- token 不写入任何日志、标准输出、异常信息或测试快照；管理凭据只经受控文件读取，secret 不进 argv。

**目录服务：**

- 运行时只读自己的 SQLite，不写网关的任何文件，不调用 Docker。用测试证明这一点。

**前端：**

- 布局与交互按草图。数据一次从 `/api/catalog` 取回，地区树、计数、搜索、同名标记都在浏览器内计算。
- 地址状态（`r1`、`r2`、`q`、`scope`、`page`）、搜索规则与排序按 design §8。
- “未开通”的设备，“进入”位置显示“未开通”，不可点击。
- 最近访问存在 `localStorage`，所有读写都包在 try/catch 中；存储不可用时页面照常工作。
- 跳转失败（404、409 未开通、409 会话过期、409 会话更新中）时，显示中文提示，不跳转。
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

**阶段 2：端到端验收。**阶段 1 审核通过，且满足 `kickoff-fe-handoff.md` 的 FE4/fe-handoff 集成与目录放行条件之后，再开始阶段 2。在包含两项改动的提交上运行，地点是 05 节点。按清单核对 Compose 管理端口与公共入口端口，并按 DC70 补充取得整机占用标记 `/home/dev/gdds-node-busy.d`，用完删除。步骤：

1. 按网关既有部署流程准备并核验一个处理组及公共入口（镜像、资源、清单与父目录挂载），然后启动；这属于验收环境准备，不由目录产品创建组。
2. 导入样例名单。名单至少包含：2 个地区一、同名项目、多音字拼音。
3. 通过目录 CLI 复用 `add-device` 开通 2 台设备 A、B，核 fixed INITIAL 回执、本地完成状态和公共 scope；记录 backend/worker 原容器身份，确认热新增不重启它们。
4. 启动目录服务；以 `vite preview` 启动网关前端，使用已有 `GATEWAY_FRONTEND_ENTRY_ORIGIN` 将 `/v1` 代理到公共入口，不直连组 backend。
5. 从目录搜索并进入 A。确认：
   - 地址片段已清除；
   - 显示“尚无数据”，上传入口可用；
   - 用 `frontend/e2e-real` 已有的样例包完成上传 → Preview → 提交 → `test1` 审核通过；
   - 在差异浏览页刷新，仍在 A 中。
6. 返回目录，进入 B，确认看不到 A 的数据。
7. 执行 `provision --renew-sessions`，确认通过父目录挂载生效，旧 token 的后续新请求返回 401，新 token 的公共 scope 正确；不重启 backend/worker、不改路由。

步骤 3、5 和 7 同时验证本轮设计中待实测的三点：

- 热新增通过实际入口可用性探针，会话原子替换无需重启即可被容器读取；
- 只有初始基线的设备可以上传；
- `test1` 能审核本人的提交。

任何一点与设计不符，就停下报告并附上证据，不要自行绕过。

### 审核与推进

实施、风险分级、独审及模型安排遵循 `AGENTS.md` 与适用的标准流程；具体工作顺序、产物和验证范围见 [执行计划](execution-plan-directory-v1.md)。审核在只读 detached worktree 中进行；开通、续期、凭据相关修正交回实施方，审核方不直接修改。

阶段 1 handoff 完成后停下交审。审核通过后按既定流程处理本地合入和 `dir-v1-exit` 附注 tag；tag 明确仅覆盖阶段 1 的组件验收，不声称真实端到端已通过。推送仍需 owner 授权。阶段 2 按 `kickoff-fe-handoff.md` 的集成放行及本文前置条件执行，端到端证据须审核核收。

## 7. 必须停下报告的情况

- 需要改 `vnext/` 或 `frontend/`，或需要新增依赖；
- 文档有歧义或互相矛盾；
- 网关系统的实际行为与 design 的描述不符；
- 缓存缺失，或工具链镜像身份不符（按 DC67、DC68 处理）。
