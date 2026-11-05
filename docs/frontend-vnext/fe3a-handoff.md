# FE3a handoff

- **分支：** `fe-vnext`，范围 `fe-fe2c-exit (749f219d5f)..<候选>`。
- **起点合并：** 本地 main `8983fe86a6` 已用 `--no-ff` 合入 `fe-vnext`，合并提交 `a3834a977c`；本轮又用 `--no-ff` 合入 main `550ddbcede`（FE3 kickoff Q10–Q12），合并提交 `417408d41d035f52ef1c2155ff9959f4a1eefce3`。两次合并带入的都是 `docs/`；合并后 `git rev-parse HEAD:vnext` 与 `550ddbcede:vnext` 都是 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。相对 `550ddbcede`，`git diff --name-only` 只含 `frontend/` 与本文件。
- **当前代码候选：** `ee064f11cc66632a4832d62df082840f56bad7b8`，`frontend/` 树 `0875c46387bea4b6297983b94ae62a068582d477`。本文件提交只改 `docs/`，不改变 frontend 树。
- **上一候选：** `bd320eaee5`（本文件 §3.3/§6 中标为“修复前”的记录属于它）；两轮之间的差异见 §0。
- **vnext：** 未改动。

## 0. 定向修复（FE3a 复审候选）

复审报告：`docs/frontend-vnext/reviews/fe3a-review.md`（main `a0b9604ddd`）。修复区间 `dd8168b2b8..ee064f11cc66`；`frontend/` 相对 `dd8168b2b8` 为 20 个文件、+963/−190。

| 提交 | 内容 |
| --- | --- |
| `d79f90d87f` | B7 恢复 FE2c 提交续做行为；B8 工作区显示名；B9 警示样式；n3 信号放行用例 |
| `8912edf3f4` | B5 smoke 判据（bundle 失败等待、Preview 结果精确匹配、History 程序断言、`screenshot: "only-on-failure"`）；N1 |
| `fdea754d03` | B1 多 scope 播种、B2 信号与结果文件、B3 残留检查、B4 预览代理 OpenAPI、B6 会话名与日志 |
| `417408d41d` | 合并 main `550ddbcede`（docs-only） |
| `3401f33eea` | B10 派生输入与 5 个输入 scope；M7 共享基线标签与树编号；N3；smoke 9 用例 |
| `6061274309` | M7 编号后的 3 个树选择器 |
| `944097fe54` | bundle 下载失败的普通 `Error` 显示专用文案 |
| `ee064f11cc` | M7 摘要截图；smoke 结果日志容错与逐用例标题 |

### 0.1 B1–B11 逐条对应

| 项 | 处理 | 测试/证据 |
| --- | --- | --- |
| B1 多 scope 播种 | `run-real-backend-e2e.sh` 按 `SCOPE_SLUGS`/`INPUT_SCOPE_SLUGS` 循环播种 7 个 scope（2 个 smoke + 5 个输入），每个 scope 独立 RS `Idempotency-Key`、repository、`business_baseline_node_id`、device key/project 与身份组；全部 seed 与 mapping 在 backend 启动前完成；逐 scope 记录 scope 名、仓库 ID 与 INITIAL 提交 ID。 | 本轮 smoke 日志 `scope=` 7 行（§3.2）；`provisioned_mappings=7`。 |
| B2 中断 | `trap` INT/TERM/HUP 分别记 130/143/129 与非 0 退出码，进入同一 `cleanup`；清理第一步 `docker rm -f` 工具链容器，使 `docker exec` 结束；用例结果以 Playwright JSON reporter 写入日志目录 `results.json`，不以 tee 为准；脚本先起 preview 再跑用例，`reuseExistingServer: true`。 | 探针 `probe-int` rc=130、`probe-term` rc=143，日志均 `signal_received`/`signal_exit_code`/`interrupted_by`/`cleanup_status=ok`（§3.4）。 |
| B3 残留检查 | dolt 改为遍历 `/proc/[0-9]*/comm` 精确匹配进程名；8000 与 dolt 只在 `STACK_STARTED=1` 时纳入清理核对；预检失败只释放本次占用；清理失败只改写 marker 的 `purpose=` 行并追加 `cleanup_failed_at=`；预检增加本脚本前缀的容器、卷与网络。 | 8000 被他人容器占用探针：exit 3、不删他人容器、节点无 marker（§3.4）。 |
| B4 OpenAPI 比对 | 在生产 preview（工具链容器内 `127.0.0.1:4173`）上读取 `/openapi.json`；宿主机 `python3 -I` 按 kickoff §5.1 规范化；不一致时写 `openapi-snapshot.normalized.json`、`openapi-runtime.normalized.json`、`openapi.diff` 并以 exit 2 结束、不跑浏览器用例。 | 本轮 smoke：`openapi_compare=match`，两份规范化文件同为 `a7d9b409…`（§3.2）。 |
| B5 smoke 判据 | 等 `GET …/preview-results/{id}/bundle` 响应与上传卡下载失败提示出现后再断言无 `pageerror`；Preview 结果按 `/\/preview-results\/[^/]+$/` 匹配；程序断言 `GET /v1/history` 只有一个 `INITIAL` 节点且 `head.node_id` 等于该节点 `ref_id`；`playwright.real.config.ts` 增加 `screenshot: "only-on-failure"`。 | 9 个 smoke 用例全部通过（§3.2）。 |
| B6 会话名与日志 | `--session` 改为必填并校验 `^[a-z0-9][a-z0-9-]{1,62}$`、写进日志；项目名前缀与残留子阶段由 `--subphase` 决定；日志补身份名/权限、occupancy marker 内容与获取/释放时间、flock 释放时间、逐用例起止、结尾 HEAD:frontend/HEAD:vnext 树与 worktree clean、依赖镜像 `RootFS.Layers`；等待 worker `code=worker_ready`。 | 本轮 smoke 日志含上述字段；`worker_ready=ok`。 |
| B7 n3 | `ComparisonPage` 恢复 `setSubmitResumeActive(false)`（ABORTED、读取失败、操作失败），提示出现后“提交”恢复可用；n3 e2e 用 `operationHold` 让操作查询停在 RUNNING，断言禁用与“提交结果确认中，请稍候”，放行后断言 ABORTED/读取失败提示与按钮恢复。 | 全量 runner 34 e2e 通过。 |
| B8 M7 工作区 | 摘要“工作区”显示组态树显示名（`gateway_device_external_key`），原始 `workspace_id` 只放悬停；单测期望改为 `gateway-17`，新增“拿不到显示名回退 ID”用例。 | `submit-summary-workspace-1280/1920.png`（§7）。 |
| B9 n8 | `SubmitDialog.tsx` 与 `UploadStepCard.tsx` 的“需要管理员处理”行由 `.form-error` 改为 `.form-warning form-warning--stacked`，保留分行；新增样式只负责纵向排列。 | `submit-manual-recovery-1280/1920.png`（§7）。 |
| B10 上传输入 | 派生 `frontend/e2e-real/fixtures/upload-inputs/{sql-baseline,sql-initial,sql-modified}.sql`（每份只在 `b1_n1_iec104_yc_list` 改两行：加 `gid INT NULL` 首列、INSERT 加 `gid=1`）；删除旧 `real-sql.sql`/`real-logics.xml`；`sql-replacement-current.sql` 与 `logics-1/2/3.xml` 直接读共享目录；单测逐字节校验派生与共享源；smoke 新增 5 个空 INITIAL scope（A、B②、C、D 各一次 MODIFIED_ONLY；B 一次 FULL，①=A）。 | 5 个 scope 全部 Upload 201、Preview SUCCEEDED、`failed_pairs=0`、每 pair `failed_table_count=0`；② pair `changed_table_count>=1`（§3.2、§5）。 |
| B11 handoff | 删除“播种 5 个 scope”（现为 7）；M1 判断按 §8.4 原文（t4 v1 renderer ≤1 GiB；1 GB 线性外推 ≤3 GiB）；补浏览器主进程增量；把“生产构建而非开发构建”列为偏差；§9 第 1 项改为 owner 直接答复（kickoff §11 Q10）。 | 本文件。 |

非阻塞项：

- **N1 采纳：** `packaging-memory.spec.ts` 的 `clear_refs` 写入失败与 FULL 文案等待失败不再吞异常，直接失败。
- **N2 不采纳：** 两处“归档基线”标签规则已由 §7 Q11 统一到 `baseline-labels.ts`，无需再建重复规则检查。
- **N3 采纳：** `generated-types.test.ts` 从 `package.json` 的 `generate:api-types` 读取参数，只替换输出路径，不再复制 CLI 参数。
- **N4 采纳并记录：** 节点运行设 `TMPDIR=/home/dev/gdds-test-tmp`；Compose secret 文件仍为 `0644`（服务用户可读），只写在 worktree 外运行目录。
- **N5 采纳：** 05 上 `gateway-repository-service:fe-2061d9c5a498`、`/tmp/gateway-fe3a-e2e.VN4aBy`、`gdds-fe-fe3a-*` 旧 worktree 在本轮结束时清理。
- **N6 不采纳：** AGENTS/testing-conventions 条文由 owner 决定，本轮只保留 §8 的建议。

### 0.2 本轮 05 运行（最终候选）

| 运行 | 节点/起止（UTC） | HEAD | 结果 | 日志 |
| --- | --- | --- | --- | --- |
| 全量前端 runner | 05 `gw-dms-test-05.lan`，09:48:12–09:49:04 | `ee064f11cc` | exit 0；30 个单测文件 143 项、34 e2e、96 张截图 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T094812Z.log`，SHA256 `a1c97e0fdcb7933f7fbcc1330fd09daac663fc59741829cc54f4fac798015c1c` |
| 真实 smoke | 同上，09:49:31–09:51:14 | `ee064f11cc` | exit 0；9 passed；`cleanup_status=ok` | `/home/dev/gdds-fe-logs/fe3a/real-smoke-ee064f11cc66/real-backend-e2e-smoke-fe3a-impl-ee064f11cc-20261105T094931Z-1340567.log`，SHA256 `3b3f5f73aedffce9d095223125e2f8ef80e4522c93b4a557d3724cbb062d4b71` |
| M1 t1 v1 MODIFIED | 同上，09:56:53–09:57:00 | `ee064f11cc` | 3 次通过 | `/home/dev/gdds-fe-logs/fe3a/m1-ee064f11cc66-t1v1/packaging-measure-ee064f11cc-20261105T095653Z-1365531.log`，SHA256 `23d660bf96c63079901eab5b4edf9eabddd0361bf8b05b2fc81b322d820b24d5` |
| M1 t4 v1 MODIFIED | 同上，09:57:35–09:57:50 | `ee064f11cc` | 3 次通过 | `…-t4v1-mod/packaging-measure-ee064f11cc-20261105T095735Z-1366432.log`，SHA256 `352b6ee1486b67ace07c55877df35309787d4634f0c2129f9fe7250f588706eb` |
| M1 t4 v1 FULL | 同上，09:58:27–09:58:53 | `ee064f11cc` | 3 次通过 | `…-t4v1-full/packaging-measure-ee064f11cc-20261105T095827Z-1367431.log`，SHA256 `d4afdaf7ac4f8979047ad832a1abd2c054ef6caf86b9ce3015d1f697fc194719` |

镜像与缓存（本轮 smoke）：

- 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`；npm 缓存 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- 依赖基础镜像 `gateway-backend-deps:lock-c668cef8e47e`，input/label `c668cef8…`，本机 ID `sha256:a944dca0…`，20 个 DiffID（全部 `RootFS.Layers` 见日志）。
- RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee`；本轮 RS `gateway-repository-service:fe-ee064f11cc66`，本机 ID `sha256:f8a1e88001b19d55448c37409547157ba84c868453ba524a49a48dbb75223de0`。
- backend 本机 ID `sha256:eb4b152ad6c34c85c46ffa4d35fd16cc296a598f3ad8490157c94b9eb8c664dc`；worker `sha256:4eb4a1b11abd1e999ed001c31cafa5c2a561b0314c6ca3a6b4e4f44a2ad2b684`。
- Compose 项目 `gdds-fe-fe3a-ee064f11cc66-20261105t095014z`；网络 ID `ebbeeeaac7014372dbcd900436c926c6e58c72cbb2e1e31037b3091dbc53bcaa`。

### 0.3 自检探针（05，最终候选）

| 探针 | 做法 | 结果 |
| --- | --- | --- |
| SIGINT | 套件开始后约 3 秒向脚本进程组发 SIGINT（Python `start_new_session` 启动，保持默认信号处置） | rc=130；日志 `signal_received=INT`、`signal_exit_code=130`、`cleanup_status=ok`；无本次容器/卷/网络/RS tag/marker。日志 `…/probes-ee064f11cc66/int/log/real-backend-e2e-smoke-probe-int-ee064f11cc-20261105T095331Z-1353468.log`，SHA256 `e315bb262e4359df498cca5f7eacf177f386b622e53bf7086d2f0e54970d1d1c` |
| SIGTERM | 同时间点向脚本进程 PID 发 SIGTERM | rc=143；`signal_received=TERM`、`signal_exit_code=143`、`cleanup_status=ok`；无残留。日志 `…/term/log/real-backend-e2e-smoke-probe-term-ee064f11cc-20261105T095503Z-1359335.log`，SHA256 `faf74ca5e8570022b8faa5ba040f68f6974c63200e7805b122084f7150bf2d3a` |
| 他人占用 8000 | 先起 `fe3a-probe-occupier`（`-p 8000:4173`），不建 busy 目录，再运行脚本 | exit 3，日志 `error=port 8000 is already published` 并列出占用容器；节点无 marker；他人容器保持运行（探针后手动删除）。日志 SHA256 `73466a391dda96a36bf31deab313f9e61a9c435251688ebf714186206d567d7a` |

- DC68 记录：第一次 INT 探针用 bash 的 `setsid ... &` 启动，后台作业继承了被忽略的 SIGINT，脚本收到的是正常退出路径（rc=2，`exit_code=2`，清理仍为 ok），未产生 `signal_received` 行。这是探针自身的启动方式错误，未触及被测对象；保留失败日志 `…/int/log/real-backend-e2e-smoke-probe-int-ee064f11cc-20261105T095149Z-1347413.log`（SHA256 `147f1892f9d5d3b032cb90498a7d9d46094ba1d5681a6c8a0f201e740632fe62`），改用 Python `Popen(..., start_new_session=True)` + `os.killpg` 后重做一次，得到上表的 rc=130。表内 INT 行引用的是重做后的日志。

探针只在 05 的一次性 worktree `/home/dev/gdds-fe-probe-wt`（detached `ee064f11cc`）中运行，未改候选 worktree；探针脚本 `/home/dev/gdds-fe-probe.py` 与 worktree 用后删除。

## 1. 改动清单与完成标准的逐条对应

`frontend/` 相对 `dd8168b2b8` 共 20 个文件、+963/−190（相对上一候选 `bd320eaee5` 的改动见 §0）。

| kickoff 项 | 改动 | 完成标准 | 状态与证据 |
| --- | --- | --- | --- |
| §3.2 / §7 M7 | 新增 `submit-summary.ts`；本轮再加 `baseline-labels.ts`，树与摘要共用“初始基线/归档基线 n（按 created_at、ref_id）”规则；`SubmitDialog.tsx` 工作区显示组态树显示名，原始 ID 放悬停；Preview 显示“本次预览” | 有/无显示名与多归档基线单测；重拍摘要截图 | 完成；§0.1 B8、§7 |
| §3.2 / §7 n3 | `ComparisonPage.tsx` 恢复 ABORTED/读取失败/操作失败后“提交”可用；`workspace-shell.spec.ts` 用 `operationHold` 停在 RUNNING，先断言禁用与原因，再放行断言提示与恢复 | 模拟接口 e2e 覆盖两种失败分支 | 完成；34 e2e 通过 |
| §3.2 / §7 n8 | `SubmitDialog.tsx` 与 `UploadStepCard.tsx` 的“需要管理员处理”行改为 `.form-warning form-warning--stacked`，保留四段分行 | 重拍 `submit-manual-recovery-1280/1920.png` | 完成；§7 |
| §3.2 / §4 运行框架与 §4.7 smoke | 独立 `run-real-backend-e2e.sh`（`--session` 必填、7 scope、信号安全、JSON 结果、预览代理 OpenAPI）、`playwright.real.config.ts`、`e2e-real/smoke.spec.ts`；不并入 `run-tests.sh`；不改 `vnext/` | §3.3/§4.7 判据由程序断言；05 上 smoke 通过 | 完成；9 passed，§3.2 |
| §3.2 / §4.6 上传输入 | 共享目录保留 `sql-*.sql` 与 `logics-1/2/3.xml`；真实 e2e 派生 `upload-inputs/{sql-baseline,sql-initial,sql-modified}.sql`，只对 `b1_n1_iec104_yc_list` 改两行；`sql-replacement-current.sql` 与三个 logics 直接读共享目录；单测校验逐字节 | 派生文件与共享源一致；真实 backend 接受上传并 Preview SUCCEEDED | 完成；5 个输入 scope 全部通过，§5 |
| §3.2 / §5.4 类型一致性 | `generated-types.test.ts` 从 `package.json` 的 `generate:api-types` 读取参数，只替换输出路径 | 重生成逐字节一致 | 完成；全量 runner 通过 |
| §3.2 / §8.4 M1 | `run-packaging-measure.sh`、`playwright.packaging.config.ts`、`packaging-memory.spec.ts`；`UploadStepCard.tsx` 暴露 `data-phase`；N1 失败不再吞 | t1 v1 MODIFIED；t4 v1 MODIFIED 与 FULL；各 3 次并报中位/最大；按 §8.4 判断 | 完成；§6 |
| 调试中发现的必需修复 | `client.ts` 的 sha256 改为 `sha256:<64hex>` DigestRef；`vite.config.ts` 的 `preview.proxy` 加 backend 代理；OperationResponse 读 `status`；compose secret 0644；bundle 下载失败文案；smoke 结果日志容错 | 真实 smoke 通过、清理核对通过 | 完成；§3.3 |

## 2. 运行框架使用说明

### 2.1 前提

- 节点：05（`ct108-gw-dms-05`），在 clean、已提交的 detached worktree 中运行；源码用 `git bundle` 传到节点。
- 05 上需要：`gateway-backend-deps:lock-<input12>`、`gateway-p2r1-repository:lock-<uv.lock12>`、Playwright 工具链镜像、npm 缓存目录与归档。
- 运行前设置（05）：

```bash
export TMPDIR=/home/dev/gdds-test-tmp
export GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache
export GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz
export GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a
```

- 真实 e2e 会起 Compose 栈并占用 8000，必须按 DC70 先 `mkdir /home/dev/gdds-node-busy.d` 获取整机占用并写会话名（`--session`，本轮 `fe3a-impl`）/用途/开始时间，再 `flock -n /tmp/gateway-compose-gate.lock`；完成后先释放 flock，再删除 marker 文件，最后 `rmdir` busy 目录。脚本已实现这些顺序和残留检查。

### 2.2 smoke

```bash
cd <clean worktree>
./frontend/scripts/run-real-backend-e2e.sh \
  --suite smoke --session fe3a-impl \
  --log-dir /home/dev/gdds-fe-logs/fe3a/real-smoke-<HEAD12> \
  --evidence-dir /home/dev/gdds-fe-evidence/fe3a/real-smoke-<HEAD12>
```

- `--session` 必填；`--subphase` 默认 `fe3a`，决定项目名前缀与残留检查前缀。
- 脚本依次：获取占用/flock → 残留检查（8000、`/proc/*/comm` 的 dolt、本前缀容器/卷/网络）→ 校验 npm 缓存与工具链身份 → 校验依赖镜像 input/label → 构建本次 RS 镜像 `gateway-repository-service:fe-<HEAD12>`（`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，不覆盖 `:local`）→ 起 RS、等 ready、循环播种 7 个 scope → 写 provisioned mapping/session/secrets → 起 backend/worker、等 `/readyz` 与 `code=worker_ready` → 用工具链内的生产 preview 读取并比对 OpenAPI → 在 toolchain 容器里 `npm ci --offline && npm run build`、起 preview、跑 `playwright.real.config.ts`（JSON reporter 写日志目录）→ 保存 test-results、Compose 日志 → 清理 → 残留核对 → 释放占用。
- 日志与证据都在 worktree 外；日志记录 hostname、起止时间、HEAD、frontend/vnext tree、占用/flock 内容与起止、npm 缓存 SHA、工具链/依赖/RS/backend/worker 镜像身份（含依赖镜像全部 `RootFS.Layers`）、Compose 项目名、网络 ID、运行时 OpenAPI SHA、逐 scope 仓库/INITIAL、身份名与权限、逐用例起止、清理状态和 exit code。
- 当前只实现 `--suite smoke`；`--suite journeys`、`--suite t1` 与 `--input-root` 会以 exit 2 明确拒绝，留给 FE3b。

### 2.3 M1

```bash
./frontend/scripts/run-packaging-measure.sh \
  --input-root /home/dev/gateway-real-dumps/source-dirs/t4-v1 \
  --mode modified|full --runs 3 \
  --report /home/dev/gdds-fe-evidence/fe3a/m1-<HEAD12>/t4v1-modified.json \
  --log-dir /home/dev/gdds-fe-logs/fe3a/m1-<HEAD12>
```

- 生产构建 + Playwright Chromium；每次运行新建 browser；只走模拟 API（stub `/v1/workspaces`、`/v1/history`），不占节点、不起 backend。
- 选目录后通过 CDP `SystemInfo.getProcessInfo` 枚举进程，对每个 PID 写 `/proc/<pid>/clear_refs=5`，记 `VmHWM`/`VmRSS` 基线；上传请求发出后读 `VmHWM` 峰值，主指标取 renderer 的峰值增量，浏览器主进程增量只报告。
- 包大小取 multipart 中 manifest `artifacts.MODIFIED/INITIAL.size_bytes`；打包耗时取页面 `data-phase` 从 `packaging` 到 `uploading` 的间隔。

## 3. 运行记录

### 3.1 05 全量前端 runner（最终候选）

| 项 | 值 |
| --- | --- |
| 节点 | `gw-dms-test-05.lan` |
| 起止 | 2026-11-05T09:48:12Z – 2026-11-05T09:49:04Z |
| HEAD | `ee064f11cc66632a4832d62df082840f56bad7b8` |
| frontend tree | `0875c46387bea4b6297983b94ae62a068582d477` |
| 命令 | `./frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe3a-fix5/screens` |
| 结果 | exit 0；typecheck、lint、30 个单测文件 143 项、构建、生产构建检查、34 个 e2e 全部通过 |
| 日志 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T094812Z.log` |
| 日志 SHA256 | `a1c97e0fdcb7933f7fbcc1330fd09daac663fc59741829cc54f4fac798015c1c` |
| 截图 | `/home/dev/gdds-fe-evidence/fe3a-fix5/screens`，96 张 |

### 3.2 05 真实 backend smoke（最终候选）

| 项 | 值 |
| --- | --- |
| 节点 | `gw-dms-test-05.lan` |
| 起止 | 2026-11-05T09:49:31Z – 2026-11-05T09:51:14Z |
| HEAD | `ee064f11cc66632a4832d62df082840f56bad7b8` |
| 命令 | `./frontend/scripts/run-real-backend-e2e.sh --suite smoke --session fe3a-impl --log-dir ... --evidence-dir ...` |
| 结果 | exit 0；9 passed；`suite_stats_expected=9 unexpected=0 skipped=0 flaky=0` |
| Compose 项目 | `gdds-fe-fe3a-ee064f11cc66-20261105t095014z` |
| 网络 ID | `ebbeeeaac7014372dbcd900436c926c6e58c72cbb2e1e31037b3091dbc53bcaa` |
| 运行时 OpenAPI | `match`；快照与运行时规范化文件同为 `a7d9b409c5d4f887fb7ef83a067a95a2b317df4aaf92735e88d54adf7c6be337` |
| 日志 | `/home/dev/gdds-fe-logs/fe3a/real-smoke-ee064f11cc66/real-backend-e2e-smoke-fe3a-impl-ee064f11cc-20261105T094931Z-1340567.log` |
| 日志 SHA256 | `3b3f5f73aedffce9d095223125e2f8ef80e4522c93b4a557d3724cbb062d4b71` |
| 证据 | `/home/dev/gdds-fe-evidence/fe3a/real-smoke-ee064f11cc66`（test-results、results.json、input-scope-results.json、compose 日志） |
| 清理 | `cleanup_status=ok`；运行后 05 无本次容器/卷/网络、8000 空闲、无 dolt、无 busy 标记、RS 临时 tag 已删 |

### 3.3 修复前记录（`bd320eaee5`，仅供追溯）

- 05 全量 runner：2026-11-05T08:05:43Z–08:06:36Z，exit 0；29 个单测文件 136 项、34 e2e、94 张；日志 `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T080543Z.log`，SHA256 `50efe761614aaddca28f4c01b5f25f04401648e6d5827cd330f68ebbf8b7a4fb`；截图 `/home/dev/gdds-fe-evidence/fe3a/screenshots-bd320eaee5`。
- 05 真实 smoke：2026-11-05T08:03:49Z–08:05:08Z，4 passed；项目 `gdds-fe-fe3a-bd320eaee591-20261105t080431z`；日志 SHA256 `80d2f0bc3ffbca824b19818297b9a6dff79904ec8355c6320e8833b47b627e94`。
- 早期失败链：`1ed1319b9a` manifest `raw_sha256` 裸 hex → 改 `sha256:<64hex>`；`1e4634297a` 读 `state` 实际为 `status`；`0712368347` 模拟 fixture 的 `b1_n1_iec104_yc_list` 缺 canonical key 导致 `KEY_MISSING`，停止交设计会话；`13be7cd1ab`/`bd320eaee5` 改用合法真实输入后通过；`bf6dd969f9` 全量 runner 2 个 n3 用例失败（当时 `submitResumeActive` 行为相反），`0d722badd3` 修复后 34 passed，失败日志 SHA256 `47fc8fec7baa19bdcf9d510dee004981cc12a31b3d3cac987572da21dfe63d7d`。
- 本轮修复中的失败：`3401f33eea` 全量 runner 因 3 个树选择器仍按 `归档基线` 精确匹配而失败，`6061274309` 修正；`6061274309` smoke 的 UI 用例等待“下载比较结果失败”却显示通用文案，`944097fe54` 修正；`944097fe54` smoke 9 用例通过但脚本因结果 JSON 无 `bundle_id` 抛 `KeyError` 而 exit 1，`ee064f11cc` 改为可选字段并补齐逐用例标题。

## 4. 传输记录

### 4.1 组态目录 → 05

- 开发主机 `/home/dev/gateway-real-dumps/small_cut/small_cut-1` → 05 `/home/dev/gateway-real-dumps/source-dirs/t1-v1`：19 文件，6,853,875 B。
- `small_cut-2` → `t1-v2`：19 文件，6,854,427 B。
- `/home/dev/gateway-real-dumps/large/large-1` → `t4-v1`：528 文件，317,343,632 B。
- 传输时间：2026-11-05T03:15Z–03:16Z；容器中一律只读 bind mount（smoke 的 `/input`、M1 的 `/input`）。
- 逐文件 SHA256 清单留在节点：`/home/dev/gateway-real-dumps/source-dirs/SHA256SUMS-t1-v1.txt`、`-t1-v2.txt`、`-t4-v1.txt`；清单文件的 SHA256：
  - t1-v1 `cdb598cdd30198ee94e56469c0c289be1ad1e1e8524e5da13b9d00249eed0163`
  - t1-v2 `fa2450fac17f5011fee31eb0b163a7355846932c973dedf86bfe10532c32a96a`
  - t4-v1 `b8938dccc3c985b77ff9d533055813e5e38a47a1789ed9915adf9f89f6d39165`
- 2026-11-05T06:49Z 在 05 上逐文件复核：与开发主机原件完全一致（t1-v1/t1-v2 各 19 文件，t4-v1 528 文件）。
- 与源包成员一致性：
  - t1-v1：`sql/dbcfg.sql` `f8da5b9608981f91ba4cef66e593a6e2299386871d53af71ba203802140748f5`、`comps/logic/logics.xml` `03f90da1675345aef17d9c0cadbb81f6271f1c7bfe1ae79d8eb86213b1a68adf`，与 `rd-t1-a-v1` 一致。
  - t1-v2：`sql/dbcfg.sql` `8fdbd3d207b81e933da9a4812b97239737541e574e7be4777dffa4f0c80ec059`、`comps/logic/logics.xml` `7d0fec1905aaa7100f1fc7eaf13347755521e79cbea45b317a14660f821801d9`，与 `rd-t1-a-v2` 一致。
  - t4-v1：与 `rd-t4-d-v1` 包内成员一致。

### 4.2 依赖镜像 → 05

- 来源提交：`3123c3b760`（开发主机 clean worktree；其 vnext 树与当前 main `8983fe86a6` 相同，均为 `2791d3ff3d`）。
- 输入摘要：`c668cef8e47ea2f75934f23a27b153662ac66ed546faf145ff903448bebea290`（当前 HEAD 的 `build-backend-dependency-base.sh --print-input` 与镜像 label 一致）。
- tag：`gateway-backend-deps:lock-c668cef8e47e`。
- 归档：开发主机 `/home/dev/gdds-test-tmp/gateway-backend-deps-lock-c668cef8e47e.tar`，SHA256 `a20f0afe388e59f5f4974f505712292524a38eb6b6287a4ed050606f4f47811e`（05 上同名归档 SHA256 相同）。
- 构建与传输起止：2026-11-05T03:16Z–03:21Z（构建、局域网传输、`docker load`、身份比对）。
- config digest：`a8d9d1ac7140bd2025080649a95146833f7ae8c2fb0e429a8f8e3856a0d9307d`；20 个 RootFS DiffID 与开发主机逐一相同（`RootFS.Layers` 全文见 §0.2 日志）：

```text
sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a
sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104
sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15
sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1
sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a
sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25
sha256:a562ec97b68c41eac099244363e807075a0a46a9d54b1b6019919efe4b765065
sha256:961fb859030f68d47e78ac25b38d885e5be18939a9e513a8373a09ef064e727c
sha256:ef1371df19a442e59ad7f4123b27c742abc0a66ddd1be7a82b13de49392e2be5
sha256:1d50a9cb6a521e6d6c7a0c9bcad5c41513f9293934573e18259cda0edc97160e
sha256:61b6fe15ca54f09a8ca6d45d23475af45a9780fb07b3e2aacd5a1bf044010f69
sha256:855e5f89bb8be8fd9815fe854571345e54ee8f10fceb1f57c2d0295c8edccf9d
sha256:cae988ee0ded0b746b7b12aa6fdfa5a539f4386989aeeb46bc5bd5a07258eada
sha256:d6ffa68abaf5d29d43a390e47db5569e5316be5003c2b0248725ca53ebb29c4c
sha256:45b730a8b2f32c5911a469d2c2595a20afc920411eff37fb6bf85f1edd484c2a
sha256:3c31b499aa8804eabc760e3d80d09e8be96b0b48788268e66c943bc6b2fda6e0
sha256:45f297c6f2a688d2c134f9cba1ebd847c58ac22dd1aebc3f9f174569fc5fb664
sha256:3eb3ddb1a9737656a943b97585f8bea0a4d175bc7c18ba1099e5cff25b638c3b
sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
sha256:0786de6e3e245c59c77a485e08af84aacca7e3614e199891f0b630637357df35
```
- 2026-11-05T06:50Z 复核：05 上镜像存在，label input、config digest 与 20 个 DiffID 与开发主机一致。

## 5. 每个 scope 的上传序列（FE3a smoke 实际执行）

真实 e2e 的 7 个 scope 都由 §0.1 B1 的播种循环建立，均为空 INITIAL，`baseline_head_version=0`。上传目录统一为根占位 `input.pmc` + `sql/dbcfg.sql` + `comps/logic/logics.xml`。

| scope（身份） | 权限 | 序列与相对当时基线的规范变化 |
| --- | --- | --- |
| `上传与预览`（submitter，upload+preview） | `workspace_read`、`read_project_history`、`upload_submit_workspace`、`preview_workspace` | CreateOrGet → 浏览器打包 `MODIFIED_ONLY`（派生 `sql-modified.sql` + `logics-3.xml`）→ 201；Preview → 202，轮询到 `SUCCEEDED`；`GET …/preview-results/{id}` 200 且与工作区 `current_preview_result_id` 一致。相对空 INITIAL 新增整棵组态（9 表变化）；FE3a 不提交、不归档。 |
| `权限拒绝`（noperm，无上传权限） | 仅 `workspace_read`、`read_project_history` | CreateOrGet；上传 → 403 `SCOPE_FORBIDDEN`；页面显示“当前身份没有该操作的权限”。 |
| `权限拒绝`（no-preview，能上传无 Preview 权限） | 上述 + `upload_submit_workspace` | CreateOrGet；上传 `MODIFIED_ONLY` → 201；启动 Preview → 403 `SCOPE_FORBIDDEN`；页面显示同一文案。 |
| `input-a`（A） | upload+preview | `MODIFIED_ONLY`：派生 `sql-baseline.sql` + `logics-1.xml`。相对空 INITIAL 新增整棵组态；`changed_table_count=9`、`failed_table_count=0`。 |
| `input-b-mod`（B②） | upload+preview | `MODIFIED_ONLY`：派生 `sql-initial.sql` + `logics-2.xml`。相对空 INITIAL 新增整棵组态；`changed=9`、`failed=0`。 |
| `input-c`（C） | upload+preview | `MODIFIED_ONLY`：派生 `sql-modified.sql` + `logics-3.xml`。相对空 INITIAL 新增整棵组态；`changed=9`、`failed=0`。 |
| `input-d`（D） | upload+preview | `MODIFIED_ONLY`：共享 `sql-replacement-current.sql` + `logics-3.xml`（项目 b）。相对空 INITIAL 新增 4 表；`changed=4`、`failed=0`；`identity_pairs[].status=NOT_APPLICABLE` 仅记录。 |
| `input-b-full`（B FULL） | upload+preview | `FULL`：① = A 的 `sql-baseline.sql` + `logics-1.xml`，② = B 的 `sql-initial.sql` + `logics-2.xml`。空 INITIAL 上两包都接受；pair 0→1 `changed=9`，pair 1→2 `changed=5`；`identity_pairs.initial_to_modified=SAME_PROJECT`；`failed_pairs=0`。 |

- 审计要点：5 个输入 scope 的 `Upload 201`、`Preview SUCCEEDED`、`GET …/preview-results/{id}` 200、`failed_pairs=0`、每个 pair `summary.failed_table_count=0`、含 ② 的 pair `summary.changed_table_count>=1` 均由 `smoke.spec.ts` 断言；D 的 `identity_pairs[].status` 与 FULL 两个 pair 的 `changed_table_count` 只写入 `/results/input-scope-results.json`，不作判据。
- FULL 与 D 的完整规范语义（归档后身份/项目确认）只有在 FE3b 归档后才能真正证实；FE3a 只证明空 INITIAL 上被接受、可比较且无失败表，**留给 FE3b**。
- 7 个 scope 的仓库与 INITIAL（本轮）：`upload-preview` `3ef27346-…`/`v0m8pol6…`；`permission-denied` `6a6a231c-…`/`qoh6macp…`；`input-a` `f993b812-…`/`v9jk9pi0…`；`input-b-mod` `2ef610b3-…`/`mh1ol2ce…`；`input-c` `fbf6ffac-…`/`t9oq88u8…`；`input-d` `eb0228ef-…`/`lh9bu733…`；`input-b-full` `f71add6a-…`/`ln0s3cq8…`。完整 ID 见 §3.2 日志 `scope=` 行。

## 6. M1 打包测量（§8.4，最终候选）

- 节点：05；提交：`ee064f11cc66632a4832df082840f56bad7b8` 的 frontend 树；方法：生产构建、Playwright Chromium、每次新 browser、`clear_refs=5` + `VmHWM` 增量、主指标 renderer、包大小取 manifest `size_bytes`、打包耗时取 `data-phase` 的 `packaging`→`uploading`。只走模拟 API。
- 报告目录：`/home/dev/gdds-fe-evidence/fe3a/m1-ee064f11cc66/`；日志目录：`/home/dev/gdds-fe-logs/fe3a/m1-ee064f11cc66-*`。

| 场景 | 输入 | 3 次 renderer 峰值增量（MiB） | 中位数 | 最大值 | 3 次浏览器主进程增量（MiB） | 3 次打包耗时（ms） | 包大小 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t1 v1 MODIFIED | 19 文件 / 6,853,875 B | 24.86 / 24.89 / 24.86 | 24.86 MiB（26,071,040 B） | 24.89 MiB（26,103,808 B） | 2.13 / 2.85 / 2.75 | 75 / 74 / 75（中位 75，最大 75） | 461,275 B |
| t4 v1 MODIFIED | 528 文件 / 317,343,632 B | 658.54 / 670.62 / 663.69 | 663.69 MiB（695,926,784 B） | 670.62 MiB（703,197,184 B） | 202.14 / 201.69 / 201.85 | 2253 / 2292 / 2262（中位 2262，最大 2292） | 20,283,589 B |
| t4 v1 FULL | 同上，①+② 两包 | 666.13 / 665.03 / 661.93 | 665.03 MiB（697,331,712 B） | 666.13 MiB（698,482,688 B） | 419.39 / 421.29 / 421.69 | 4483 / 4529 / 4389（中位 4483，最大 4529） | 20,283,589 × 2 = 40,567,178 B |

报告 SHA256：

- `t1v1-modified.json` `5753944ac59b7c5cee084c85d4853c5f6645d8dc51b3889c7ce17d7767b36af8`
- `t4v1-modified.json` `c412f0bc33d63c1b2d9baa4abdab4eac2b8bf2e5a30f53a1f75bd73b07bbcc5a`
- `t4v1-full.json` `48c8399e8798d5fc28218a566e9e83795c80f973224e7c62d40472538caed0cb`

判断（按 §8.4）：

- t4 v1 renderer 峰值增量最大 670.62 MiB，≤ 1 GiB，满足“单次 1 GB 目录不超过 1 GiB”的当前档要求。
- 按目录大小线性外推到 1 GB：`703,197,184 × 1,000,000,000 / 317,343,632 ≈ 2.22 GB ≈ 2.06 GiB`（FULL 外推约 2.05 GiB），≤ 3 GiB。
- 浏览器主进程增量只作报告：t1 约 2–3 MiB，t4 MODIFIED 约 202 MiB，t4 FULL 约 420 MiB；FULL 的 renderer+浏览器主进程合计约 1.08 GiB，但 §8.4 的判据只看 renderer，不据此判失败。
- 结论：FE3a 不需要改流式；M1 测量已完成。FE3b 的旅程上传与 M1 复测仍按 kickoff 执行。

## 7. 截图清单

- 目录：`/home/dev/gdds-fe-evidence/fe3a-fix5/screens`；96 张（48 个场景 × 1280/1920）。
- 聚合 SHA256（`sha256sum *.png | sort -k2 | sha256sum`）：`acd173c279d0609ba7302830caa94d67b4cf144a763d8e04c0652a5351a64b94`。
- M7 摘要（`submit-summary-workspace-1280.png` / `-1920.png`）：
  - 1280 `eadb9b687dad22d898da0591445494bd878196031f9a8bc820c9272a729d9203`
  - 1920 `ad25993d1d1824010b237523b4ffb9553a1039c9885adb410ca6ca53606d63c1`
- M7 身份确认对话框（`submit-identity-confirmation-1280.png` / `-1920.png`）：
  - 1280 `6d242bca5a574c9d9e192d99c2a179e5323c12d9a9218ab40133091b43c257fa`
  - 1920 `f236872307cfe61dfdf1040cbd2c78b65e628890ba04a70c752fec0aba9dedfd`
- n8 `submit-manual-recovery-1280.png` / `-1920.png`：
  - 1280 `feee609932f5d9012b231f911ee26fb957ef68a7bb2a09a2bf40bcbf8764b34a`
  - 1920 `a16681ef4f47068d3ed268efc17367add2f991105e3070877ebb7b31b34e74e6`
- 因 M7 归档基线编号而变化的其他树/摘要场景（同目录，1280/1920 各一份）：`s1-workbench`、`s3-workbench-normal`、`s2-compare-tray`、`archive-mainline`、`archive-audit-conflict`、`archive-blocked`、`archive-permission-denied`、`review-reject-dialog`、`manual-recovery-required`、`history-compare-*`、`submit-aborted`、`submit-result` 等；以聚合 SHA 为准。

## 8. 给 AGENTS 与 testing-conventions 的建议条文（§4.1）

建议在 AGENTS“前端测试（FD7）”下补：

1. **真实 backend e2e 入口：** `frontend/scripts/run-real-backend-e2e.sh` 是独立入口，不并入 `run-tests.sh`；`--session` 必填并写入占用标记与日志；连真实 backend 的运行必须按 DC70 取 `mkdir /home/dev/gdds-node-busy.d` 占用并 `flock -n`，完成后先释放 flock、删 marker，再 `rmdir` busy 目录；释放顺序与残留核对写进脚本而非人工。
2. **输入来源：** 模拟 fixture 的 `frontend/src/test/fixtures/source/upload-inputs/sql-*.sql` 故意包含无 gid 的诊断表，不能直接用于真实 Preview；真实 e2e 使用 `frontend/e2e-real/fixtures/upload-inputs/{sql-baseline,sql-initial,sql-modified}.sql`（只给 `b1_n1_iec104_yc_list` 加 `gid` 两行），`sql-replacement-current.sql` 与 `logics-1/2/3.xml` 直接读共享目录；模拟 fixture 与共享文件保持逐字节不变。
3. **服务用户可读的 secret：** Compose 挂载的 session/token 文件需 `0644`（或对服务用户可读），`0600 root` 会让 repository-service 启动即失败；该类文件仍只写在 worktree 外运行目录。
4. **M1 方法：** 每次测量新建 browser/context；对 CDP 枚举的 PID 写 `/proc/<pid>/clear_refs=5` 后记 `VmHWM` 基线；只报 renderer 峰值增量，浏览器主进程增量单列；包大小解析 multipart manifest 的 `size_bytes`，打包耗时用页面 `data-phase`；不要用整个 multipart body 或 click→request 代替。
5. **节点纪律：** 前端 typecheck/lint/unit/build/e2e 不在开发主机运行；调试统一在 05，04 只在阶段取证时运行。

建议在 testing-conventions 的“前端测试”补：真实 e2e 的日志字段（工具链/依赖/RS/backend/worker 镜像身份、依赖镜像全部 `RootFS.Layers`、npm 缓存 SHA、Compose 项目与网络 ID、运行时 OpenAPI SHA、逐 scope 仓库/INITIAL、身份名与权限、占用与 flock 内容及起止、清理核对）与 M1 的报告字段（逐次 renderer 与浏览器主进程增量、中位/最大、manifest size、打包耗时）。

## 9. 偏差与未决事项

1. **真实 e2e 输入来源（owner 直接答复）：** kickoff §4.6 原意是复用模拟 fixture 的 SQL/logics；实际运行时上传 201 被接受，但 Preview 因 `b1_n1_iec104_yc_list` 缺少 canonical key 返回 `KEY_MISSING`。按 §4.6/§10 停下后，owner 直接答复实施方，决定“真实 e2e 用派生输入、共享源保持逐字节不变”，记录见 `docs/frontend-vnext/fe3-kickoff.md` §11 Q10（main `550ddbcede`）。派生文件为 `frontend/e2e-real/fixtures/upload-inputs/{sql-baseline,sql-initial,sql-modified}.sql`，旧 `real-sql.sql`/`real-logics.xml` 已删除。
2. **套件范围：** FE3a 只实现并验证 `--suite smoke`；`journeys`、`t1` 与 `--input-root` 明确 exit 2，留待 FE3b。真实旅程、t1 旅程、归档/审核/撤回的真实 e2e 未在 FE3a 运行。
3. **FULL 与 D 的规范语义：** 空 INITIAL 上只能证明被接受、可比较、无失败表；FULL 的“① 原始 + ② 归档”与 D 的 `DIFFERENT_PROJECT` 身份确认要在 FE3b 归档后才能完全证实，属已知留项。
4. **04 取证未执行：** 按要求 04 取证在审核通过后进行；本 handoff 只包含 05 的调试证据。审核通过后需在 04 clean detached worktree 上运行 `run-tests.sh --e2e --screenshots` 与 `run-real-backend-e2e.sh --suite smoke`。
5. **M1 的运行环境：** 按 §8.4 用模拟接口（stub）测量，不连真实 backend；测量的是前端打包内存，不受 backend 影响。偏差：用生产构建而非开发构建测量；这是 §4.1 的明确要求，但与“开发构建”口径不同，已在 §6 与本节记录。
6. **M1 指标范围：** 按 owner Q12 只看 renderer；浏览器主进程增量仅报告。`RssAnon/RssFile/RssShmem` 拆分留 FE3b，不在本轮判据内。
7. **n3 的失败分支**由模拟接口 e2e 覆盖（操作查询停在 RUNNING 后放行），未在真实 backend 上重放；当前 backend 还没有对应接口状态。
8. **05 占用等待：** 07:35Z–07:43Z 05 被 owner 的 `p6-four-workers-exit-fix` 占用，早期 smoke 等待其释放；本轮 09:48Z 之后无等待。
9. **RS 临时 tag：** 每次真实 e2e 构建 `gateway-repository-service:fe-<HEAD12>`，清理阶段删除；`gateway-repository-service:local` 与共享依赖镜像未动。
10. **文档提交与证据 HEAD：** 本文件提交后候选 HEAD 会前进一个 docs-only 提交；`ee064f11cc` 上记录的 frontend tree 与候选一致，04 取证以审核后的最终 HEAD 为准。
