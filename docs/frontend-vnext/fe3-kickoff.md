# FE3 kickoff：对接真实 backend

- **状态：** 草案（设计会话，2026-11-05），待 kickoff 审核与 owner 确认（§11）。确认前不发出实施提示词。
- **日期：** 2026-11-05。
- **起点：** `fe-fe2c-exit`（tag 对象 `86901e038d` → `749f219d5f`，测试提交 `220325da37`，`frontend/` 树 `960ab1f6a1`），
  main 合入提交 `0430e0e738`；`fe-vnext` 在 `749f219d5f`。本文以 main `2c79d0947f` 为准核对。
- **依据：** [前端 kickoff](frontend-kickoff.md)（§3.3、§4.2–§4.4、§5、§6、§7、§7.1）、
  [FE2 kickoff](fe2-kickoff.md)（§6.5、§7、§9 Q16–Q19、§10）、FE2c 各轮审核报告（`reviews/fe2c-*.md`）、
  后端 [DC73](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc73-后端会话分为设计与审核两个角色)、
  [DC75](../backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc75-be-a工作区占用指针与本人撤回权限)、
  [BE-a 设计补充](../backend-vnext/refactoring/formal/plans/p6-be-a-design.md)（`f20f08bea9`，审核 `fcbfb4c1a0`）、
  [BE-a / BE-d 任务提示词草案](../backend-vnext/refactoring/formal/plans/p6-be-a-d-kickoff.md)、AGENTS（“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”）、
  testing-conventions“前端测试（FD7）”。
- **会话分工：** 与前端 kickoff §10 相同。本文由前端设计会话维护。BE-a、BE-d 归后端设计会话 `p6-backend-design`（DC73），
  前端设计会话不写后端提示词，只核对接口是否满足 FE3 的需要（§2.3），并经 owner 协调排期。

## 1. 目标

- 前端对接 Compose 中的真实 backend，跑通全部业务旅程（前端 kickoff §7 FE3 一行）。
- 刷新 OpenAPI 快照，并在 e2e 中与运行中的 `/openapi.json` 比对（前端 kickoff §4.2）。
- 接回上传模式顶栏的撤回（前端 kickoff §7.1，DC75）。
- 用 t1 真实数据从浏览器走完一次完整旅程。
- 完成 FE2 带入项（FE2 kickoff §6.5：M1、M7、n3、n8）。

不在范围：BE-b 的分组、列展示与行定位（FE4）；首批空基线（FE2 kickoff Q18，仍为缺口）；正式 SSO 与部署形态（Phase 8/9）；外部驱动通道与深色主题。

## 2. 当前事实（main `2c79d0947f`，2026-11-05 核对）

### 2.1 后端依赖

| 项 | 状态 | 对 FE3 的影响 |
| --- | --- | --- |
| S2a | 证据复核 2 通过（[报告](../backend-vnext/refactoring/formal/plans/p6-s2a-evidence-check-2.md)，候选 `3b3d9c97bc`）；exit 排在基准 exit 之后（DC70）。main 上没有 `p6-s2a-exit` | BE-a、BE-d 都排在 S2a 合入 main 之后 |
| 基准测量 | 进行中。[后端交接](../backend-vnext/refactoring/formal/plans/p6-backend-session-handoff.md) §2.1 列出的剩余项：W4 输入重新生成与验收、W4 各场景、H2 三节点、H3、表哈希对照、DC63/V5b 分段、正式 JSON、04 最终 runner，之后是基准终审。W4 修正已通过定向复核（[报告](../backend-vnext/refactoring/formal/plans/p6-baseline-stop-check-w4-duplicate-key.md)），实施方估计 W4 部分剩余 14–30 小时。ct108 当前占用标记：`p6-baseline-measure`，用途 `corrected-keyless-w4-generation-and-acceptance`，自 2026-11-04T23:10:53Z | 决定 S2a 合入时间 |
| BE-a | 设计补充 `f20f08bea9`；kickoff 审核通过（`fcbfb4c1a0`，归属订正 `680f9a60f0`）；owner 实施确认待记录；提示词草案未发出 | 接回撤回（§6）、OpenAPI 状态码与指针字段（§5） |
| BE-d | 任务草案在 `p6-be-a-d-kickoff.md` §3；kickoff 审核未安排；提示词未发出 | 当前 `/bundle` 只返回 manifest JSON，所有需要下载 bundle 的旅程都要等 BE-d |

**预计时间（设计会话估计，不是后端承诺）：** 基准剩余项与终审约 1–2 天，随后办理基准 exit 与 S2a exit。
BE-a、BE-d 各含实施、审核、04 runner、容器门禁与 05 t1，后端草案建议先 BE-a 后 BE-d，各约 2–3 天；
BE-d 还需先完成 kickoff 审核。按此估计，两者合入 main 约在 S2a 合入后一周内，即 11 月 10–14 日前后。排期以后端设计会话为准。

**协调建议（经 owner 转后端设计会话）：**

- BE-d 的 kickoff 审核是纯文档工作，建议现在安排，与基准测量并行；BE-a 的实施确认也可以现在给出。这样 S2a 合入后两项都可以立即开始。
- 对 FE3 而言，BE-d 解锁的旅程比 BE-a 多（差异浏览、提交、审核、历史比较都要下载 bundle），BE-a 只解锁 §6 与快照中的状态码和字段。
  若后端认为两项可以并行或调换顺序，FE3 会更早进入真实旅程调试；不并行也不影响本文的安排。

### 2.2 节点、镜像与数据

| 项 | 05 | 04 | 说明 |
| --- | --- | --- | --- |
| 前端工具链 `mcr.microsoft.com/playwright:v1.64.1-noble` | 有 | 有 | 身份见 `frontend/scripts/run-tests.sh` |
| npm 缓存 `/home/dev/gdds-fe-cache/frontend/` | 有 | 有 | 来源提交 `a2fb4a027a` |
| backend 依赖镜像（当前 main vnext 树 `2791d3ff3d` 需要 `gateway-backend-deps:lock-c668cef8e47e`，由 `build-backend-dependency-base.sh --print-input` 得出） | **缺** | 有 | 05 上只有 `lock-d054366c02fa`（fixture 生成用）。05 调试真实 e2e 前要按 DC67 从开发主机传入 |
| RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee` | 有 | 有 | RS 镜像本身按当前 HEAD 构建（§4.3） |
| `gateway-repository-service:local` | 有（revision `80ce756619`） | 有（S2a 候选 `3b3d9c97bc`） | 由后端会话使用，前端不重新 tag（§4.3） |
| 真实数据包 `/home/dev/gateway-real-dumps/packages/rd-t{1..4}-*.tar.gz` | 有 | 有 | 规范化的源包，只含 `/sql/dbcfg.sql` 与 `/comps/logic/logics.xml`，没有 `.pmc` |
| 组态目录原件 | **无** | **无** | 只在开发主机 `/home/dev/gateway-real-dumps/{small_cut,small,medium,large}` |

**组态目录与数据档的对应（设计会话按 `sql/dbcfg.sql` 与 `comps/logic/logics.xml` 的 SHA256 核对）：**

| 档 | 目录（开发主机） | 文件数 | 目录大小 | 与源包 |
| --- | --- | --- | --- | --- |
| t1 v1 / v2 | `small_cut/small_cut-1`、`small_cut-2` | 19 / 19 | 6,853,875 / 6,854,427 字节 | 与 `rd-t1-a-v1/-v2` 两个成员的 SHA256 都一致 |
| t2 v1 / v2 | `small/small-1`、`small-2` | 229 / 230 | 约 66 / 64 MB | `dbcfg.sql` 一致 |
| t3 v1 / v2 | `medium/medium-1`、`medium-2` | 223 / 226 | 约 237 / 238 MB | `dbcfg.sql` 一致 |
| t4 v1 / v2 | `large/large-1`、`large-2` | 528 / 528 | 约 317 MB | `dbcfg.sql` 一致 |

前端上传要求所选目录根下恰好一个 `.pmc` 且有 `sql/dbcfg.sql`（`upload-package.ts`，沿用 legacy 的规则）。
节点上的源包不满足，不能直接用于浏览器上传；组态目录原件满足。**t1 旅程的输入需要 owner 授权把目录原件传到 05，是阻塞项（§8.1、§11 Q2）。**

### 2.3 BE-a、BE-d 与 FE3 需要的接口核对

依据 BE-a 设计补充 §2–§4 与任务草案 §3。结论：**满足 FE3 的需要，不需要新增后端字段或接口。**

| FE3 需要 | 后端设计 | 结论 |
| --- | --- | --- |
| 定位上传模式下当前提交（Q16） | `WorkspaceResponse.active_submission_id`，required nullable，新建 201 与已存在 200 两条路径都返回 | 满足 |
| 刷新后找回进行中的提交尝试 | `active_submit_attempt_id`，经已有 `GET .../submit-attempts/{id}` 取 `operation_id` | 满足 |
| 本人读取审核状态（含终态） | `withdraw_own_submission` 可读本人提交的 `GET .../review`，所有状态 | 满足 |
| 撤回请求的预期版本 | `expected_review_version` 取 `review_version`，不用工作区版本 | 满足 |
| “无权限”的判定 | 两个审核权限都没有时 GET 与 POST 返回 403；他人、跨 scope 与不存在统一 404 | 满足；前端不按 actor 推断（§6.1） |
| 撤回后可重新上传 | 指针、当前上传与 Preview 清空 | 满足 |
| 两个创建接口的状态码 | `POST /v1/workspaces` 201/200，`POST /v1/history-compares` 202/200 写进 OpenAPI | 满足；FE3b 去掉 FE2 的类型变通（§5.3） |
| 整包 tar | 成员 `manifest.json`、`artifact-closure.json`、按 closure 顺序的产物；`Content-Length`、`ETag`；头前预检的错误码写进 Contract 与 OpenAPI | 满足；成员名与 `frontend/src/features/bundle/posix-tar.ts` 一致。前端按 OpenAPI 列出的错误码给文案（§5.3） |

实施中若合入后的接口与本表不符，按 §10 停止。

## 3. 阶段安排

### 3.1 甲、乙两个方案

- **甲：** 整个 FE3 等 BE-a、BE-d 合入 main 后开始。
  - 好处：一个阶段、一次审核与取证；运行框架直接按最终接口做。
  - 代价：前端空等约一周或更久（§2.1）。M1 是否需要改流式打包要到 t1 旅程才知道，届时才改，FE3 的后半程变长。
- **乙（建议）：** 拆成两个子阶段。
  - **FE3a（现在开始）：** 不依赖新接口的部分。包括 M7、n3、n8（模拟接口）；真实 backend e2e 的运行框架，在当前 backend 上跑冒烟；
    真实 e2e 用的上传输入；生成类型与快照的一致性检查；M1 的打包内存测量（只需组态目录，不需要 backend）。
  - **FE3b（BE-a、BE-d 合入后）：** 刷新快照、§6 撤回、全部真实旅程、t1 旅程。若 FE3a 的 M1 结论为“需要流式”，流式打包也在 FE3b 做。
  - 理由：
    - 运行框架（Compose、占用标记、镜像、身份、数据准备、清理、日志）与新接口无关，工作量也最大，可以先在当前 backend 上做实、先审核；
    - FE3b 开始时只需加场景，审核也集中在业务旅程；
    - M1 提前测量，需要改流式时不占 FE3b 的关键路径。
  - 代价：多一次审核与 04 取证。FE3a 冒烟时 backend 仍是 BE-a 之前的形态，FE3b 中会话文件的权限要补 `withdraw_own_submission`，属于预期的小改动。

### 3.2 乙的子阶段

| 子阶段 | 内容 | 前置条件 | 退出 tag | 审核范围 | 退出条件 |
| --- | --- | --- | --- | --- | --- |
| FE3a 运行框架与带入项 | §7 的 M7、n3、n8；§4 运行框架与当前 backend 上的冒烟（§4.7）；§4.6 上传输入；§5.4 生成类型一致性；§7 M1 的打包测量（§8.4，需要 §11 Q2 的数据） | 本文经 owner 确认 | `fe-fe3a-exit` | `fe-fe2c-exit..<FE3a 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图）、上传包后端校验、真实 backend 冒烟各一次通过；M1 测量结果写入 handoff 并经 owner 判断（§8.4） |
| FE3b 真实旅程 | `fe-vnext` 合入含 BE-a、BE-d 的 main；§5 快照刷新与类型、模拟数据同步；§6 撤回；§4.7 全部真实旅程；§8 t1 旅程；M1 在旅程中复测；M1 需要时改流式 | S2a、BE-a、BE-d 都已合入 main，owner 确认发出 FE3b 提示词 | `fe-fe3b-exit` | `fe-fe3a-exit..<FE3b 候选>` | 审核通过；04 上：模拟接口全量 runner（含截图）、上传包校验、真实 backend 全部旅程各一次通过；05 上 t1 旅程通过；§6 截图经 owner 确认 |

- FE3b 结束即 FE3 结束，FE4 以 `fe-fe3b-exit` 为起点。
- 两个子阶段都在 `fe-vnext` 上进行。开始时先把当时的 main 合入 `fe-vnext`（只用合并，不 rebase）。
  FE3b 合入 main 后，候选的 `vnext/` 树必须与所合入的 main 提交相同；审核用 `git diff <main 提交> <候选> -- vnext` 为空来核对。
- 审核范围中来自 main 的提交（文档与 `vnext/`）不在前端审核范围内；`vnext/` 由后端审核负责。

**FE3b 的提前调试：** BE-a、BE-d 先后合入时，实施会话可以在先合入的一项上开始在 05 调试相关旅程，例如 BE-d 合入后先调差异浏览。
FE3b 的候选与审核仍在两项都合入后进行，不为单项另设 tag。

### 3.3 FE3a 在当前 backend 上无法验证的内容

当前 backend（vnext 树 `2791d3ff3d`）上，`GET .../preview-results/{id}/bundle` 与 `GET /v1/history-compares/{id}/bundle` 只返回 manifest JSON。前端 bundle 下载按 tar 解析，因此：

- **要等 BE-d：** Preview 差异浏览，以及由此进入的提交（提交入口在 Preview 顶栏）；审核模式（History bundle）中的通过、退回、撤回；
  需要已通过提交的归档主线；历史比较的结果浏览与抽屉计数（需要至少两个节点）；bundle 截断后重新下载；t1 旅程。
- **要等 BE-a：** §6 全部内容；快照中的 201/202、指针字段与 `RETURN_FOR_REVISION` 的删除；本人撤回身份。
- **FE3a 可以验证：** 运行框架本身；运行时 OpenAPI 与当前快照比对（预期一致，§5.2）；工作区 CreateOrGet；组态树读取 History（只有 `INITIAL`）；
  浏览器打包的上传被真实 backend 接受；Preview 操作轮询到 `SUCCEEDED` 并读到 Preview 结果；无权限身份的 403 显示；归档候选为空时的界面；
  请求侧约束（`Idempotency-Key` 等）由真实 backend 检查。

FE3a 的冒烟在“Preview 结果可读”处结束，不为 bundle 下载失败写断言（这是即将删除的临时行为）。

## 4. 真实 backend e2e 的运行框架

### 4.1 入口

- 新增提交在 `frontend/scripts/` 下的独立脚本，例如 `run-real-backend-e2e.sh`，**不作为 `run-tests.sh` 的选项**（§11 Q4）。理由：
  - 前提条件不同：占用标记、Compose、backend 镜像与 vnext 树；
  - `run-tests.sh` 不依赖后端镜像（AGENTS FD7），这一点不变；
  - 与 FE2c 的上传包后端校验脚本（FE2 kickoff §7.1）做法一致。
- 套件参数：`--suite smoke`（FE3a）、`--suite journeys`（FE3b 全部旅程）、`--suite t1 --input-root <目录>`（§8）。
  另有 `--log-dir <绝对路径>`、`--evidence-dir <绝对路径>`（失败时的 trace、截图与参考截图），都必须在 worktree 外。
- Playwright 使用单独的配置与目录，例如 `playwright.real.config.ts` 与 `e2e-real/`；`run-tests.sh` 的 `playwright test` 不收集这些用例。
- 不修改 `vnext/`。只读使用 `vnext/deploy/compose.yaml`、`vnext/scripts/build-backend-dependency-base.sh --print-input`、
  `vnext/scripts/build-repository-service-image.sh`。需要改它们才能运行时，停下交设计会话（§10）。

### 4.2 节点、占用与单飞

- 调试在 05，取证在 04（testing-conventions“前端测试”节点表）。t1 在 05（DC36，§8）。
- 脚本开始时按 DC70 补充用 `mkdir /home/dev/gdds-node-busy.d` 原子获取整机占用，写入会话名、用途、开始时间（UTC）、hostname、worktree 与 HEAD。
  目录已存在时退出（非 0，不等待、不抢占），由操作者稍后重试；占用标记的用途为计时测量时，前端在该节点上的任何运行都等待（前端 kickoff §6）。
- 获取后另持后端 Compose 门禁使用的 `flock /tmp/gateway-compose-gate.lock`（`compose_gate_harness.py`），与同节点的后端门禁互斥。
- 运行前的残留检查（AGENTS 整机单飞）：
  - 没有容器发布 8000 端口（`docker ps --filter publish=8000`）；
  - `/proc` 中没有 dolt 进程；
  - 没有本脚本命名前缀的 Compose 项目、卷与网络残留。

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
- **依赖镜像的来源：** FE3a 需要 `lock-c668cef8e47e`，04 已有；05 缺，按 DC67 从开发主机 `docker save`、经获准的局域网传入、`docker load`，
  比较 config digest 与全部 RootFS DiffID 后使用，handoff 记录来源、归档 SHA256 与传输时间。FE3b 使用合入 S2a、BE-a、BE-d 后
  main 所需的依赖镜像，通常已由后端任务传到 04、05；仍按标签与身份核对，缺失即停止并报告。
- **Repository Service：** 用 `vnext/scripts/build-repository-service-image.sh` 按当前 HEAD 构建，
  `GATEWAY_REPOSITORY_SERVICE_IMAGE` 设为本次运行专用的 tag（例如 `gateway-repository-service:fe-<HEAD12>`），
  不覆盖后端会话使用的 `gateway-repository-service:local`。使用本机已有的 RS 依赖镜像（预置依赖模式）；构建需要访问网络即停止（缓存缺失）。
  运行结束时删除本次 tag，保留构建层缓存。
- **身份记录：** 日志记录依赖镜像 tag、输入摘要、config digest 与全部 DiffID；RS 镜像 tag、本机 image ID 与 build-input、source-tree、revision label；
  backend/worker 本机 image ID；Docker 与 Compose 版本。跨节点比较只用 config digest 与 DiffID。
- **前端工具链：** 与 `run-tests.sh` 相同的固定镜像与身份核对、npm 离线缓存。

### 4.4 Compose 栈

1. 项目名 `gdds-fe-<子阶段>-<HEAD12>-<UTC 时间戳>`，`docker compose -f vnext/deploy/compose.yaml -p <项目名>`。
2. secret 与配置写在 worktree 外的本次运行目录（容器可读的权限）：Repository bearer、internal bearer、session 文件、部署映射。token 每次随机生成，不提交，不进入构建产物，日志中不输出。
3. `build backend worker` → `up -d repository-service` → 等 RS ready → 播种仓库（§4.6） → 写部署映射 → `up -d backend worker` → 等 `/readyz` 与 worker 就绪。
4. 运行时 OpenAPI 比对（§5.2）通过后才运行浏览器用例。

### 4.5 工具链容器与 backend 的网络

- 工具链容器加入本次 Compose 项目的默认网络（`--network <项目名>_default`），`GATEWAY_FRONTEND_BACKEND_ORIGIN=http://backend:8000`。
  浏览器只访问容器内的前端服务器，由它代理 `/v1`、`/readyz`、`/openapi.json` 到 backend（`vite.config.ts` 已有代理，与生产同源反向代理的形态一致）。
- 不用 host 网络：不在宿主机上新增端口；8000 由 Compose 发布，仍按 §4.2 占用。
- `npm ci --offline` 照常离线；日志记录所用网络名与 `docker network inspect` 的 ID。
- **被测构建（§11 Q5）：** 真实 e2e 测生产构建（`npm run build` 后 `vite preview`，preview 沿用 server 的代理设置），
  不测开发构建：
  - 生产构建是用户实际拿到的产物；
  - 生产构建中没有身份选择（FE2 kickoff §6.2）。身份由 Playwright 在页面脚本运行前注入 `window.__gatewaySession`（`addInitScript`），
    token 来自 §4.4 生成的身份文件，以只读方式挂进容器；
  - 开发构建的模拟身份切换（`DevIdentityControl`）与模拟接口只用于模拟接口 e2e，不改动。

### 4.6 测试身份与初始数据

**身份（会话文件按 backend 已支持的格式生成，前端 kickoff §4.3）：** 每个 scope 一组。权限是精确字符串，没有继承（`vnext/deploy/README.md`）。
组态树要读 History，因此各身份都带 `workspace_read` 与 `read_project_history`：

| 身份 | 权限（在上述两项之外） | 用途 |
| --- | --- | --- |
| 提交人（本人撤回） | `upload_submit_workspace`、`preview_workspace`、`withdraw_own_submission`（BE-a 之后） | 上传、Preview、提交、上传模式撤回（§6） |
| 提交人（仅上传） | `upload_submit_workspace`、`preview_workspace` | §6“无权限”场景 |
| 审核人 | `review_submission` | 审核模式的通过、退回、撤回 |
| 归档确认人 | `archive_submission` | 归档主线 |
| 无权限身份 | 无 | 写操作的 403 |

- FE3a 中“本人撤回”身份不带 `withdraw_own_submission`（当前 backend 没有该权限，写入也不生效）；FE3b 补上。
- 验证本人撤回时不用审核人或全权限身份代替（前端 kickoff §4.3）。
- 身份文件同时给出 `business_project_id`、`gateway_device_external_key`，由用例按身份注入；日志只记录身份名与权限，不记录 token。

**初始数据：**

- **仓库与映射：** 与后端 Compose 门禁相同（`compose_gate_harness.seed_repository_and_mapping`）：在 RS 容器内 `POST /v1/repositories`，
  核对 `INITIAL` 提交为空，再把 `repository_id`、`initial_commit_id` 写入部署映射（`baseline_head_version = 0`）。backend 启动时据此创建 `INITIAL` 基线。
- **scope 隔离：** 每个互相独立的旅程用自己的 scope（一条映射、一个仓库、一组身份），失败不连带其他旅程。用例单 worker 串行（`workers: 1`，不重试）。
- **上传输入（FE3a）：** 不另写 SQL。把 bundle fixture 生成器（`frontend/scripts/generate-backend-bundle-fixture.py`）中的 SQL 输入移到提交的 `.sql` 文件，
  生成器与真实 e2e 共用：
  - 移动后重新生成全部 fixture，与已提交的逐字节相同，跨实现摘要测试照常通过；
  - 真实 e2e 由这些文件组成上传目录（根目录一个占位 `.pmc`、`sql/dbcfg.sql`、按场景的 `comps/logic/logics.xml`），写在 worktree 外的本次运行目录；
  - 覆盖：第一次 MODIFIED_ONLY 上传（基于空的 `INITIAL`）、归档后的 FULL 上传（① 原始组态备份 + ② 本次归档组态）、MODIFIED_ONLY 上传；
  - 真实 backend 拒收或无法 Preview 这些输入时停下交设计会话，不改写输入去迁就。
- 真实数据只在 t1 套件中使用（§8）。

### 4.7 场景

**FE3a 冒烟（`--suite smoke`）：** §3.3“FE3a 可以验证”所列各项。

**FE3b 全部旅程（`--suite journeys`）：**

| # | 旅程 | 要点 |
| --- | --- | --- |
| R1 | 工作区与组态树 | CreateOrGet 第一次 201、刷新后 200；树中 `INITIAL` 基线；提交与归档后树节点与状态按 FE2 kickoff §4.1 |
| R2 | 上传与 Preview | 浏览器打包、上传、Preview 轮询、下载 tar（`Content-Length`、`ETag`、逐成员摘要）、进入差异浏览；MODIFIED_ONLY 与 FULL 各一次；再次打开同一 Preview 不重新下载 |
| R3 | bundle 截断重下 | 路由拦截截断一次真实 tar 响应，前端丢弃本地副本、重新下载后可浏览 |
| R4 | 提交 | 从 Preview 顶栏提交到 `PENDING`；输入产生需要确认的身份结论时覆盖确认，不产生时由模拟接口覆盖，handoff 说明 |
| R5 | 幂等重试 | 一次写操作（提交或审核）用 `route.fetch()` 把请求送到 backend 后对浏览器 `abort`，前端用同一 key 重试，backend 回放 200，界面显示成功 |
| R6 | 审核 | 审核人在审核模式（History bundle）退回（必填理由），工作区指针清空；重新上传、提交后通过；审核顶栏撤回回归 |
| R7 | 上传模式撤回 | §6.3 全部场景 |
| R8 | 归档主线 | 候选 → 首次预检“待确认” → 确认 → 异常处理（若有） → 开始归档 → head 前移，树显示归档基线 |
| R9 | 历史比较 | 两节点与三节点；结果抽屉计数（FE2 kickoff §6.4 D1）；打开 History 差异浏览 |
| R10 | 权限拒绝 | 无权限身份的上传、Preview、提交、审核、归档各返回 403 并显示“当前身份没有该操作的权限”与错误码 |
| R11 | 版本冲突 | 审核版本冲突：另一身份先行动作后，界面提示并刷新，不自动重发；工作区版本冲突一例 |

- Preview、提交等操作在小输入上很快完成，“仍在运行”、刷新后继续轮询与 `MANUAL_RECOVERY_REQUIRED` 继续由模拟接口覆盖，真实 e2e 不强求。
- 浏览器控制台出现未捕获错误即判失败。
- 失败时保存 trace、截图与该次的 Compose 日志；成功时为 R2、R6、R7、R9 的关键页面各存一张参考截图（不作验收，FE4 用 t1 数据重拍）。

### 4.8 清理

- `docker compose ... logs --no-color --timestamps` 写入日志目录后，执行 `down -v --remove-orphans --rmi local`；
  再按 `com.docker.compose.project=<项目名>` label 删除残留的卷与网络（同 `compose_gate_harness._teardown_compose_project_resources`）；删除本次 RS tag 与 secret 目录。
- 核对：没有该项目的容器、卷与网络；8000 端口空闲；`/proc` 中没有 dolt 进程。之后才按 §4.2 释放。
- 不删除共享镜像（依赖镜像、工具链、`gateway-repository-service:local`、client e2e 镜像），不运行 `docker rmi` 或 prune 清理他人资源。

### 4.9 日志

日志写在 worktree 外的 `--log-dir`，运行结束后写 SHA256 旁注文件。字段：

- 开头与结尾：hostname、UTC 时间、`git rev-parse HEAD`、`HEAD:frontend` 与 `HEAD:vnext` 树、worktree 是否 clean；结尾记录 exit code；
- 占用标记的获取、释放时间与内容，flock 的获取、释放时间；残留检查结果；
- 工具链镜像身份、npm 缓存归档 SHA256 与来源提交；§4.3 的全部镜像身份；Compose 项目名与网络 ID；
- 运行时 `/openapi.json` 的 SHA256 与比对结果；
- 身份名与权限（不含 token）；播种的仓库 ID 与 `INITIAL` 提交 ID；
- 每个用例的名称、起止时间与结果；
- 清理核对结果；
- t1 套件另记：输入目录的文件数、字节数与逐文件 SHA256 的聚合值；§8.4 的 M1 指标；各步骤耗时与 bundle 的 `Content-Length`、实收字节、`ETag`（只报告）。

Compose 日志与 Playwright trace 可能包含输入数据；t1 套件的这些文件只留在节点上，不写进仓库与 handoff 正文。

## 5. OpenAPI

### 5.1 快照刷新（FE3b）

- 在已合入 BE-a、BE-d 的 `fe-vnext` 上，用 §4 的脚本起栈，取运行中的 `/openapi.json`，按现有快照的格式（键排序、2 空格缩进、末尾换行）写入 `frontend/openapi.json`。
  脚本先核对：当前快照按该格式重排后逐字节不变，否则先停下，说明格式规则不对。
- 用 `npm run generate:api-types` 重新生成 `src/features/api/generated/openapi.d.ts`；快照与生成类型在同一个提交中更新，提交说明写明来源 main 提交与 vnext 树。
- 刷新快照的运行可以在 05 调试；最终以 04 证据中的运行时比对为准（§5.2）。

### 5.2 与运行中 `/openapi.json` 的比对

- 每次真实 e2e 运行在浏览器用例之前比对：两侧都按 §5.1 的格式规范化后逐字节比较。
- 不一致时脚本以非 0 退出，不运行浏览器用例，日志目录保存两份规范化 JSON 与 diff。处理：
  - 差异来自已合入 main、前端尚未刷新的后端改动：按 §5.1 刷新，从头运行；
  - 差异与 §2.3、§6 或 BE-a 设计不符，或出现前端没有预期的 schema 变化：停下交设计会话（§10）。
- FE3a 在当前 backend 上比对，预期一致（快照自 `a2fb4a027a` 起，后端 HTTP 层没有改动）；不一致即停止。

### 5.3 刷新后的同步（FE3b）

按 FE2 kickoff §7.5 的规则同步，规则本身不变：

- **删除 `RETURN_FOR_REVISION`：** 删除 FE2 kickoff §4.1 末段的 `RETURNED_FOR_REVISION` → “已退回”映射及 `client.test.ts` 中的对应用例（AGENTS：删除被替代的实现）；
  `review_status`、事件动作的取值以新生成类型为准。
- **201/202：** `POST /v1/workspaces` 新建 201、已存在 200；`POST /v1/history-compares` 第一次 202、回放 200。
  模拟响应改用各状态码自己的生成类型，删除 FE2 kickoff §7.5“幂等回放”中“响应体用 200 的类型约束”的变通。
- **指针字段：** 全部 `WorkspaceResponse` 模拟数据补 `active_submit_attempt_id`、`active_submission_id`，两者至多一个非空，与场景的生命周期一致
  （BE-a 设计补充 §2 的表；场景注明依据）。
- **新权限与错误：** 错误码单测解析新快照，覆盖 BE-a 新增或变化的状态码与 code（例如 review 查询的 403、404）。
- **bundle 错误码：** BE-d 在 OpenAPI 中列出的 bundle 错误码各有前端文案，加入 FE2 kickoff §7.5 的取值核对；没有列出的不模拟。
- **fixture 的 tar：** FE1–FE2 的 bundle fixture 由前端按 §4.4 格式在本地拼装 tar。BE-d 若在生产代码中提供可以直接调用、不经 HTTP 的 tar 封装函数，
  生成器改用它；没有时保留现有拼装，由 R2、R3 覆盖，handoff 说明。

### 5.4 生成类型的一致性（FE3a）

增加一项检查：由 `frontend/openapi.json` 重新生成类型到临时目录，与已提交的 `openapi.d.ts` 逐字节相同，否则失败。放进 `run-tests.sh` 的单测阶段或作为单测。

## 6. 接回上传模式顶栏撤回（前端 kickoff §7.1）

### 6.1 状态与文案

数据来源与请求规则见前端 kickoff §7.1：指针非空时调用 `GET /v1/submissions/{id}/review`，撤回携带 `review_version`；前端不按 actor 推断权限，指针非空不等于可撤回。

撤回按钮在上传模式顶栏始终显示（草图 `header-upload`），不可用时禁用并给出原因（F4，§11 Q7）。危险按钮样式、二次确认（X4）、幂等 key 与审核顶栏的撤回相同。
已有的审核顶栏文案（`ReviewActions.tsx` 的 `STATUS_REASON`）沿用，新增的按下表：

| 条件（按顺序判断） | 按钮 | 禁用原因 / 提示 |
| --- | --- | --- |
| `active_submit_attempt_id` 非空 | 禁用 | 提交正在执行，完成后才能撤回 |
| 两个指针都为空 | 禁用 | 当前没有待审核的提交 |
| 正在查询审核状态 | 禁用 | 正在读取审核状态 |
| 查询返回 403 | 禁用 | 当前身份没有撤回权限 |
| 查询返回 404 | 禁用 | 未找到该提交，请刷新后重试（另附“刷新”） |
| 查询失败（临时错误超过重试上限、5xx） | 禁用 | 无法读取审核状态（另附“重试”） |
| `status = PENDING` | 可用 | — |
| `status = APPROVED` | 禁用 | 该提交已通过审核，不能撤回 |
| `status = REJECTED` | 禁用 | 该提交已退回 |
| `status = WITHDRAWN` | 禁用 | 该提交已撤回 |

- 403、404 与查询失败都按 C6 在悬停提示中附错误码，可复制。
- **撤回对话框：** 标题“撤回提交”，影响说明与确认勾选沿用审核顶栏的撤回对话框。
- **撤回失败（对话框底部提示区，FE2c R6）：**
  - 409 `REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT`：提示“审核状态已变化，已重新读取”。
    同时重新查询工作区与 review，按新状态更新按钮，不自动重发；
  - 403：“当前身份没有撤回权限”；404：“未找到该提交，请刷新后重试”；
  - 其他错误：通用文案“撤回未完成”加错误码（C6）。
- **撤回成功：** 重新读取工作区。指针、当前上传与 Preview 都为空时，离开 Preview 页回到工作台的上传步骤卡，提示“已撤回，可以重新上传”。
- 文案按 FE2 kickoff §4 的原则：只说原因，原始码放悬停提示与 Debug。

### 6.2 刷新恢复与 `active_submit_attempt_id`

- URL 中的 `operation_id`（FE2 kickoff N2）保持不变，仍是操作卡片与轮询的依据。
- 页面加载或刷新时读取工作区：
  - `active_submit_attempt_id` 非空、URL 没有该提交的操作时，经 `GET .../submit-attempts/{id}` 取 `operation_id`，写入 URL，按 FE2c 的续做路径显示操作卡片并继续轮询；
  - URL 中的提交操作与指针所指 attempt 的 `operation_id` 不同时，以服务器（指针）为准，替换 URL 中的值。
- 提交操作到达终态后重新读取工作区：成功时指针转为 `active_submission_id`，失败或 `ABORTED` 时两者都为空，分别按 FE2c 已有的结果与“提交未完成”处理。
- **FE2c 的 `sessionStorage` 提交标记（§11 Q6）：** `gateway-submit-operation`（`SubmitDialog.tsx`、`ComparisonPage.tsx`）只能在同一标签页内找回提交，
  指针可以跨标签页与设备。建议 FE3b 删除该标记，由指针取代（AGENTS：删除被替代的实现）；n3 的失败分支 e2e（§7）随之改为基于指针。
  上传的 `gateway-preview-operation` 标记不受影响。

### 6.3 必测场景

模拟接口 e2e 与真实 backend e2e（R7）都覆盖，本人撤回用“提交人（本人撤回）”身份，无权限用“提交人（仅上传）”身份：

| # | 场景 | 断言 |
| --- | --- | --- |
| W1 | 本人撤回 | `PENDING` 时按钮可用；确认后撤回成功，回到上传步骤卡 |
| W2 | 撤回后重新上传 | 工作区两个指针、`current_upload_revision_id`、`current_preview_result_id` 都为空；重新上传、Preview、提交成功，指针指向新提交 |
| W3 | 无权限 | 仅上传身份提交后，review 查询 403，按钮禁用且原因为“当前身份没有撤回权限” |
| W4 | 已通过 | 审核人通过后，提交人刷新：`active_submission_id` 仍非空，按钮禁用且原因为“该提交已通过审核，不能撤回” |
| W5 | 冲突刷新 | 撤回对话框打开后，审核人先撤回或退回（真实 e2e）或模拟 `REVIEW_VERSION_CONFLICT`（模拟接口）；界面重新读取后按新状态显示，不自动重发 |
| W6 | 提交执行中 | `active_submit_attempt_id` 非空时按钮禁用；刷新后按 §6.2 找回操作卡片（真实 e2e 中提交很快完成时，可只在模拟接口覆盖，handoff 说明） |
| W7 | 回归 | 审核人在审核顶栏撤回，行为与 FE2c 相同 |

模拟数据按 BE-a 设计补充 §2 的生命周期表构造指针，按 FE2 kickoff §7.5 的“后端可达状态”规则核对跨响应关系，场景注明依据。

## 7. FE2 带入项（FE2 kickoff §6.5）

| ID | 子阶段 | 内容与完成标准 |
| --- | --- | --- |
| M7 | FE3a | 提交对话框的摘要不显示原始 ID：History 节点用组态树中的显示名（由前端从 History 推导，例如“当前基线（归档基线 2）”“提交 2”）；Preview 结果显示“本次预览”。拿不到显示名时才显示 ID。原始 ID 放悬停提示与 Debug（C6）。单测覆盖有、无显示名两种情况；重拍提交对话框截图（`submit-*` 中显示摘要的各张） |
| n3 | FE3a | e2e（模拟接口）覆盖续做时 `ABORTED` 与读取失败的提示，以及续做期间“提交”按钮禁用并显示原因。FE3b 若按 §11 Q6 删除 `sessionStorage` 标记，这些用例改为基于指针，覆盖不减 |
| n8 | FE3a | “需要管理员处理”一行：ID、“复制 ID”与正文分开排版，使用同一区域其他提示的提示样式；重拍 `submit-manual-recovery-1280/1920` |
| M1 | FE3a 测量；FE3b 复测，需要时改流式 | 见 §8.4 |

## 8. t1 真实数据旅程（FE3b）

### 8.1 输入（阻塞项）

- 需要组态目录原件（§2.2）：t1 v1、v2 即开发主机的 `small_cut/small_cut-1`、`small_cut-2`。节点上的源包没有 `.pmc`，浏览器上传会在校验阶段拒绝；
  不用源包加占位 `.pmc` 代替：那样不是用户的真实目录，M1 的测量也没有意义。
- **请 owner 授权（§11 Q2）：** 经获准的局域网把上述两个目录传到 05 的 `/home/dev/gateway-real-dumps/source-dirs/t1-v1`、`t1-v2`；
  M1 测量另需 t4 v1 的 `large/large-1`（约 317 MB，528 个文件）到 `source-dirs/t4-v1`。传输后：
  - 目录只读；
  - 记录逐文件 SHA256 清单及其聚合值；
  - 核对 `sql/dbcfg.sql`、`comps/logic/logics.xml` 与同档源包成员的 SHA256 一致（本文 §2.2 已在开发主机核对一次）。
- 授权前 t1 旅程与 M1 测量都不能开始；FE3a 中 M1 测量随之顺延。

### 8.2 节点与步骤

- 节点 05（DC36：t1–t3 在 05），按 §4.2 获取占用；与后端在 05 上的 t1 等运行互斥。
- `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，一个独立 scope，步骤（与后端 `real_dump_journey.py` 的 t1 顺序对应，便于对照）：
  1. 提交人：工作区 → 选择 t1 v1 目录 → MODIFIED_ONLY 上传（基于空的 `INITIAL`） → Preview → 下载并浏览（全部为新增表） → 提交；
  2. 审核人：审核模式下载 History bundle → 通过；
  3. 归档确认人：归档主线 → head 前移到 v1；
  4. 提交人：选择 t1 v2 目录 → MODIFIED_ONLY 上传 → Preview → 下载并浏览差异 → 提交；
  5. 审核人：通过；
  6. 审核人：历史比较三节点（`INITIAL`、归档 v1、v2 提交） → 打开结果浏览。
- FULL 上传、退回、撤回等已由 §4.7 覆盖，t1 不重复。

### 8.3 通过标准

- 每一步在浏览器中完成，没有未捕获错误；每次下载都通过 tar 成员与摘要校验。
- Preview v1 的表数等于 S1 census（`p5-arch-closure-s1-census.json`）中 `rd-t1-a-v1` 的表数；各次浏览中没有比较失败（`FAILED`）的表。
  有降级或诊断时，界面显示对应文案而不是通用文案（FE2 kickoff §5.5），handoff 列出出现过的编码。
- 对照：同一 vnext 树上有后端 t1 运行（BE-d 的 05 t1）结果时，逐表核对 v2 Preview 的表状态与行级记录数一致；取不到时只记录，handoff 说明。
- 各步骤耗时、bundle 体积与下载耗时只报告，不设门槛。05 不是计时参考节点，这些数字不作为性能证据（DC36）。
- 关键页面（工作台、v2 Preview 差异浏览、审核模式、历史比较结果）在 1280 与 1920 下各存参考截图，记录 SHA256；不作验收，FE4 重拍（前端 kickoff §6）。

### 8.4 M1：打包峰值内存

- **测量内容：** 目录字节数与文件数、压缩后包大小、打包耗时，以及打包期间 Chromium 进程的内存峰值。
- **测量方法：**
  - 每次测量启动一个新的浏览器实例，使进程的峰值计数从零开始；
  - 经 CDP `SystemInfo.getProcessInfo` 取渲染进程与浏览器主进程的 PID；
  - 在工具链容器中读取 `/proc/<pid>/status` 的 `VmHWM`（峰值常驻内存）与 `VmRSS`：选择目录前记一次基线，上传请求发出后（打包已完成）再记一次；
  - 渲染进程峰值减基线为主指标，浏览器主进程（Blob 存储在其中）同样记录；`performance.memory`（`--enable-precise-memory-info`）只作参考，
    它不含 `ArrayBuffer` 的外部内存；
  - 打包耗时取“确认上传”到上传请求发出的时间，压缩包大小取请求体长度；
  - 每个目录测 3 次，报告中位数与最大值。
- **FE3a：** 在 05 上用模拟接口测量（开发构建，路由拦截上传请求，不需要 backend 与占用标记），输入为 t1 v1 与 t4 v1 目录。
  测量用独立的 Playwright 配置与提交的脚本，结果写入 handoff。
- **FE3b：** 在 t1 旅程中用生产构建对 t1 v1、v2 再测一次，与 FE3a 对照。
- **判断（§11 Q3）：** 由审核会话与 owner 看数据决定。设计会话建议的默认标准：
  - t4 v1 的渲染进程峰值增量不超过 1 GiB；
  - 按目录大小线性外推到前端上限 1 GB 时不超过 3 GiB。

  任一不满足即在 FE3b 改为流式打包（逐文件读取、边打包边压缩，不在内存中攒整包），FE2 kickoff §7.1 的后端校验继续接受产物，改后重测。

## 9. 证据

| 子阶段 | 节点 | 内容 | 计时 |
| --- | --- | --- | --- |
| FE3a | 04 | `run-tests.sh --e2e --screenshots <目录>`（全量模拟接口，含截图）；上传包后端校验脚本；`run-real-backend-e2e.sh --suite smoke`。各一次，在 clean、已提交的 detached worktree 上 | 否 |
| FE3a | 05 | M1 打包测量（§8.4） | 否（只报告） |
| FE3b | 04 | 同 FE3a 的前两项；`--suite journeys` 一次（含运行时 OpenAPI 比对） | 否 |
| FE3b | 05 | `--suite t1` 一次（含 M1 复测与参考截图） | 否（只报告） |

- 调试与取证分开（DC30）：05 调试只跑 focused 与出问题的那一段；04 只在审核通过后运行一次。
- 04、05 的运行日志、截图与 trace 都在 worktree 外的证据目录，记录 SHA256；handoff 记录工具链与依赖镜像身份、npm 缓存来源、运行节点。
- **需要重拍并交 owner 看图确认的截图：**
  - FE3a：M7 的提交对话框各张；n8 的 `submit-manual-recovery-1280/1920`；
  - FE3b：§6 的各状态，即上传模式顶栏的撤回可用，以及 §6.1 表中的每种禁用状态各一张、
    上传模式撤回对话框、撤回冲突提示、撤回成功后的上传步骤卡；快照刷新后显示有变化的截图。
- 真实 backend 与 t1 的参考截图只作参考；FE4 用真实 backend 与 t1 数据重拍关键页面（前端 kickoff §6，节点见 §12）。

## 10. 实施会话的停止条件

除 AGENTS、前端 kickoff 与 FE2 kickoff §10 已有的规则外：

- 合入后的接口与 §2.3、§6 或 BE-a 设计补充不符，或运行时 OpenAPI 出现前端没有预期的变化（§5.2）；
- 真实 e2e 发现后端缺陷，或后端不接受 §4.6 的输入：保留日志与 trace，交设计会话与后端设计会话处理；不在前端绕过，不改 `vnext/`；
- 需要后端新增字段或接口；
- 依赖镜像、RS 依赖镜像、工具链镜像或 npm 缓存缺失，身份不符，或构建需要访问网络；
- 运行需要修改 `vnext/` 下的 Compose、脚本或配置；
- t1 输入未获授权或核对不符（§8.1）；
- 清理核对失败（§4.2）。

脚本自身的错误按 DC68 重做一次；被测对象运行后的失败不按 DC68 重做。

## 11. owner 决定（待定）

| # | 事项 | 建议 |
| --- | --- | --- |
| Q1 | 阶段安排（§3） | 乙：FE3a 现在开始，FE3b 在 S2a、BE-a、BE-d 合入后开始；tag、范围与退出条件按 §3.2 |
| Q2 | t1 输入（§8.1）：节点上没有组态目录原件 | 授权把 `small_cut-1`、`small_cut-2`（各 19 个文件、约 6.9 MB）与 `large-1`（528 个文件、约 317 MB，只用于 M1）经局域网传到 05 的 `source-dirs/`，只读并记录 SHA256 清单。不建议用源包加占位 `.pmc` 代替 |
| Q3 | M1 的测量与判断（§8.4） | FE3a 用 t1 与 t4 目录测打包内存，FE3b 在 t1 旅程中复测；默认标准按 §8.4，不满足即在 FE3b 改流式。这比 FE2 kickoff Q19（只在 t1 旅程中记录）提前了测量，并增加了 t4 目录：t1 只有约 6.9 MB，测不出问题 |
| Q4 | 真实 e2e 的入口（§4.1） | 单独提交的脚本，不并入 `run-tests.sh` |
| Q5 | 真实 e2e 的被测构建与身份注入（§4.5） | 测生产构建；身份由 Playwright 注入 `window.__gatewaySession`，token 每次随机生成，不进入构建产物 |
| Q6 | FE2c 的 `sessionStorage` 提交标记（§6.2） | 由 `active_submit_attempt_id` 取代并删除；URL 中的 `operation_id` 保留 |
| Q7 | 上传模式顶栏撤回的显示（§6.1） | 始终显示，不可用时禁用并给原因（与 F4 一致）；文案按 §6.1 |

## 12. 开放项

| 项 | 说明 | 何时 |
| --- | --- | --- |
| FE4 真实数据重拍的节点 | 前端 kickoff §6 写“FE4 在 04 上用真实 backend 与 t1 数据重拍”，但 DC36 规定 t1–t3 在 05。建议 FE4 kickoff 时改为：t1 数据的重拍在 05，04 只跑合成输入的真实 backend e2e；如需在 04 使用 t1 数据，由 owner 作例外决定 | FE4 kickoff |
| 首批空基线（FE2 kickoff Q18） | 仍为缺口，不在 FE3。FE3 的输入都从空的 `INITIAL` 开始，界面不禁用第 ① 步 | 后端提供该事实后 |
| P6 计时与整包下载（DC74 草案） | t1 旅程的下载耗时与体积只报告；DC74 确认后，按其结论更新前端 kickoff §9 | DC74 确认后 |

## 13. 实施与审核提示词

以下提示词在各自的前置条件满足、并经 owner 确认后由设计会话发出（或由 owner 转发）。发出时填写方括号中的值。

### 13.1 FE3a 实施（前置：本文经 owner 确认，§11 全部决定已记录）

> 你是 FE3a 前端实施会话。先读 AGENTS、[前端 kickoff](frontend-kickoff.md)（§4、§6、§7）、[FE2 kickoff](fe2-kickoff.md)（§6.5、§7、§10）、本文（main `[确认提交]`）全文，以及 FE2c 复审第 4 轮与证据核对第 1 次。
>
> - **起点与分支：** `fe-vnext`（`fe-fe2c-exit` = `749f219d5f`）。先把 main `[确认提交]` 合入 `fe-vnext`（只合并，不 rebase），在开发主机 worktree `/home/dev/gdds-fe` 开发；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行。
> - **范围（本文 §3.2 FE3a 一行）：**
>   1. §7 的 M7、n3、n8；
>   2. §4 的真实 backend e2e 运行框架与 `--suite smoke`（§3.3、§4.7）；
>   3. §4.6 的上传输入（SQL 移到共用文件，fixture 逐字节不变）；
>   4. §5.4 生成类型一致性检查；
>   5. §8.4 的 M1 打包测量（需要 owner 已按 §11 Q2 传好目录，否则先做其余各项，handoff 说明）。
> - **不做：** 不改 `vnext/`；不刷新 OpenAPI 快照（FE3b）；不做 §6。
> - **节点：**
>   - 调试在 05；05 缺 `gateway-backend-deps:lock-c668cef8e47e`，按本文 §4.3 从开发主机经 DC67 流程传入并核对身份；
>   - 真实 e2e 按 §4.2 获取占用标记与 flock，并完成清理核对；
>   - 某节点占用标记的用途为计时测量时，在该节点上的任何运行都等待。
> - **停止条件：** 本文 §10。脚本自身错误按 DC68 重做一次。
> - **交付：** 05 上完整运行 `run-tests.sh --e2e --screenshots` 与 `--suite smoke` 各一次通过后，提交代码候选与 handoff（`docs/frontend-vnext/fe3a-handoff.md`）。handoff 包括：
>   - 改动清单与完成标准的逐条对应；
>   - 运行框架的使用说明；
>   - 各次运行的节点、日志路径与 SHA256、镜像与缓存身份；
>   - 依赖镜像传输记录；
>   - M1 数据；
>   - 截图清单；
>   - 偏差与未决事项。
>
>   不在 04 上运行，04 取证在审核通过后进行。

### 13.2 FE3a 审核（前置：FE3a handoff 已提交）

> 你是 FE3a 审核会话（不与实施会话为同一会话）。审核 `fe-fe2c-exit..[FE3a handoff 提交]`，其中来自 main 的提交不在前端审核范围内。依据：本文（main `[确认提交]`）§3.2、§3.3、§4、§5.4、§7、§8.4、§10，FE2 kickoff §7，AGENTS“前端测试（FD7）”。
>
> 重点：
> 1. **运行框架：** 符合 §4，包括：
>    - 不修改 `vnext/`，构建设置符合 AGENTS，不覆盖共享 tag；
>    - 占用与 flock 的获取、释放顺序，失败与中断时的清理，清理核对失败时保留标记；
>    - token 不进入构建产物与日志；
>    - 日志字段齐全。
>
>    在 05 上用已提交的一次性 worktree 做探针：
>    - 让占用目录预先存在：脚本应退出且不触碰他人资源；
>    - 运行中途中断：应完成清理，无残留；
>    - 改动快照一处：运行时比对应失败，且不运行浏览器用例。
> 2. **冒烟：** 覆盖 §3.3“FE3a 可以验证”的各项；不为 bundle 下载失败写断言。
> 3. **上传输入：** fixture 逐字节不变（重新生成并比较）；真实 backend 接受全部输入。
> 4. **带入项：** M7、n3、n8 的完成标准。截图对照草图与 FE2 kickoff §7.3 的原则。
> 5. **M1：** 测量方法符合 §8.4（新浏览器实例、`VmHWM` 基线与峰值、3 次）；数据可复核；按 §11 Q3 的标准给出建议。
> 6. 在 05 上独立运行一次 `run-tests.sh --e2e --screenshots` 与 `--suite smoke`。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3a-review.md`，结论为通过、定向修复或停止；需要设计决定的事项标注“交设计会话”。通过后指明 04 取证项（本文 §9 FE3a 行），取证后做证据核对。

### 13.3 FE3b 实施（前置：S2a、BE-a、BE-d 都已合入 main，FE3a 已退出，owner 确认发出）

> 你是 FE3b 前端实施会话。先读 AGENTS、前端 kickoff（§4.3、§4.4、§7.1）、FE2 kickoff §7.5、本文（main `[确认提交]`）全文、FE3a 的 handoff 与审核报告，以及后端 BE-a 设计补充（`f20f08bea9`）、BE-a 合入提交 `[BE-a 合入提交]` 与 BE-d 合入提交 `[BE-d 合入提交]` 的 handoff。
>
> - **起点：** `fe-fe3a-exit`。把 main `[合入 BE-a、BE-d 后的 main 提交]` 合入 `fe-vnext`；之后 `vnext/` 树必须与该 main 提交相同。
> - **范围（本文 §3.2 FE3b 一行）：**
>   1. §5 快照刷新与同步；
>   2. §6 上传模式撤回，含 §6.2 刷新恢复与 §11 Q6；
>   3. `--suite journeys` 的 R1–R11（§4.7），身份按 §4.6 补 `withdraw_own_submission`；
>   4. §8 t1 旅程；
>   5. M1 复测，按 FE3a 的结论决定是否改流式打包。
> - **先核对接口：** 运行时 OpenAPI 与 §2.3、§6 的预期一致；不一致按 §10 停止，交设计会话。
> - **节点：**
>   - 真实 e2e 调试在 05，t1 在 05，均按 §4.2 获取占用；
>   - 依赖镜像使用后端任务传入的 tag，按 §4.3 核对身份，缺失即停止并报告；
>   - 某节点占用标记的用途为计时测量时，在该节点上的任何运行都等待。
> - **停止条件：** 本文 §10。真实 e2e 发现的后端缺陷交设计会话与后端设计会话，不在前端绕过。
> - **交付：** 05 上 `run-tests.sh --e2e --screenshots`、`--suite journeys`、`--suite t1` 各一次通过后，提交代码候选与 handoff（`docs/frontend-vnext/fe3b-handoff.md`）。handoff 包括：
>   - 快照来源（main 提交与 vnext 树）；
>   - §6.3 场景与测试的对应；
>   - R1–R11 的结果；
>   - t1 通过标准的逐条核对（§8.3），以及与后端 t1 的对照或其缺失说明；
>   - M1 数据与结论；
>   - 截图清单与偏差；
>   - 各次运行的节点、日志 SHA256 与镜像、缓存身份。

### 13.4 FE3b 审核（前置：FE3b handoff 已提交）

> 你是 FE3b 审核会话。审核 `fe-fe3a-exit..[FE3b handoff 提交]`：
> - 来自 main 的提交与 `vnext/` 不在前端审核范围；
> - 先核对 `git diff [合入的 main 提交] [候选] -- vnext` 为空。
>
> 依据：本文（main `[确认提交]`）§2.3、§4.7、§5、§6、§8、§10，前端 kickoff §7.1，FE2 kickoff §7.5，BE-a 设计补充 §2–§4。
>
> 重点：
> 1. **快照：** 与运行时逐字节一致；`RETURNED_FOR_REVISION` 映射已删除；201/202 不再使用变通；模拟数据的指针符合 BE-a 生命周期表；错误码单测覆盖新状态码。
> 2. **§6：** 文案与 §6.1 一致。前端没有按 actor 或指针推断可撤回；撤回使用 `review_version`；冲突后不自动重发。删除 `sessionStorage` 标记后，n3 的覆盖不减少。
> 3. **测试与探针：** §6.3 W1–W7 在模拟接口与真实 e2e 中都有对应用例；本人撤回没有用审核人或全权限身份。在 05 上用已提交的一次性 worktree 做探针：
>    - 把撤回的预期版本改为工作区版本：真实 e2e 应失败；
>    - 去掉 403 分支：W3 应失败。
> 4. **旅程：** R1–R11 符合 §4.7。t1 按 §8.3 核对，复核 M1 数据与结论。
> 5. **运行：** 在 05 上独立运行一次 `--suite journeys`。t1 不要求审核会话重跑，只核对日志与参考截图。
>
> 报告写入 `docs/frontend-vnext/reviews/fe3b-review.md`。通过后指明 04 取证项（本文 §9 FE3b 行），取证后做证据核对，并给出 FE3 退出建议。

## 14. 不在 FE3 范围

- BE-b 的分组、列展示、Preview 改前公式与行定位产物（FE4）。
- 首批空基线（FE2 kickoff Q18）。
- Preview 顶栏的上传快捷入口、历史比较结果抽屉布局、1280 下提交对话框滚动：已接受为 FE2 的偏差（FE2 kickoff Q19），FE3 不再处理。
- 正式 SSO、部署形态、外部驱动通道、深色主题。
