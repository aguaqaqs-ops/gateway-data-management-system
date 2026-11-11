# FE4a 证据 handoff（H，`16f4306306`）

本轮按 FE4 kickoff 修订 7 §16.5–§16.7 在 H 上重跑四项证据，不在 `59c5b8cfca` 的三项结果上沿用。四项全部通过；未修改 `frontend/` 与 `vnext/`，未运行调试运行与 t4，未做计时或重复采样。

- 依据：kickoff §16.5（四项）、§16.6（新路径与保留）、§16.7（哈希来源与写法）、§7.4–§7.5（运行与记录格式）；复审第 4 轮 §7；证据核对第 1 轮 §5。
- 本文件是 H 之后唯一的改动，父提交为 H。

## 1. 提交与树

| 项 | 提交 | `frontend/` 树 | `vnext/` 树 |
| --- | --- | --- | --- |
| 证据提交 H | `16f4306306` | `d8e9a2e7` | `49c1de43` |
| 本文件所在提交 | 本文件所在提交，父提交为 H | `d8e9a2e7` | `49c1de43` |

- 开发主机 `/home/dev/gdds-fe` 的 `fe-vnext` 由 `59c5b8cfca` 以 `git merge --ff-only 16f4306306` 快进到 H；未 rebase，未改写已被引用的提交。
- 两节点各自用 detached worktree `/home/dev/gdds-fe4a-evidence-16f43063` 检出 H；起止 HEAD 均为 H，起止均 clean，运行期间未写 worktree。
- 未复用 `59c5b8cfca` 证据、调试或复审用过的 worktree；未切换任何共享 worktree 的分支。

## 2. 传输、worktree 与新路径

- bundle：`/home/dev/gdds-bundles/fe4a-evidence-16f4306306.bundle`，范围 `59c5b8cfca..fe-vnext`，10,742 字节，SHA256 `44edc28318a465b042eb18e47c37c6dda049db6c60a198fb21e21f14c4846587`。
- 04、05 各自 `git bundle verify` 通过；以 `git fetch <bundle> refs/heads/fe-vnext:refs/fe4a-evidence/16f4306306` 写入 ref，ref 指向 H。两节点 bundle 与开发主机的 SHA256 相同。
- 日志目录（运行前新建）：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04`、`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05`。
- 证据目录（运行前不存在，worktree 外）：`/home/dev/gdds-fe-evidence-04/fe4a-16f43063`、`/home/dev/gdds-fe-evidence-05/fe4a-16f43063`。
- `59c5b8cfca` 的 worktree、ref、日志与截图，以及 X、Y 的调试产物、各轮审核会话产物均未删改。

## 3. 运行前核对

### 3.1 占用

每次运行前在该节点确认 `/home/dev/gdds-node-busy.d` 不存在，且没有他人的有效占用标记（无计时测量标记）。

- 04-a、04-b：由 `run-evidence-wrapper.sh` 取标记，入口不再重复取；运行结束后标记释放，运行后抽查 `/home/dev/gdds-node-busy.d` 不存在。
- 04-c、05-t1：入口 `run-real-backend-e2e.sh` 自行取标记，wrapper 只要求标记不存在；日志记 `busy_end=absent`。

### 3.2 镜像身份

每次运行前用 H 的 `frontend/scripts/docker-save-image-identity.py` 对 `docker save` 归档导出身份，按 config digest 与全部 DiffID 核对（不比较 `docker inspect` ID）。

| 镜像 | config digest | DiffID 数 |
| --- | --- | --- |
| 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble` | `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017` | 7 |
| backend 依赖镜像 | `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` | 19 |
| RS 依赖镜像 | `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |

各次运行前的身份文件（路径即本次导出的身份文件，作为回源 `--evidence-file`）：

- 04-a：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/precheck-04a/identity-toolchain.json`。
- 04-b：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/precheck-04b/identity-backend-deps.json`；工具链身份由入口日志 `entry-upload-validator.log` 现场记录，与 04-a 的导出值相同。
- 04-c：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/precheck-04c/identity-toolchain.json`、`identity-backend-deps.json`、`identity-repository-deps.json`。
- 05-t1：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/precheck-05t1/identity-toolchain.json`、`identity-backend-deps.json`、`identity-repository-deps.json`。

### 3.3 `--print-input`

两节点都在主检出 `16ffe72829` 上（与 H 同 `vnext/` 树）运行 `./vnext/scripts/build-backend-dependency-base.sh --print-input`，exit 0：

- `image` 为 backend 依赖 tag，`input_sha256=578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`。
- 输出 JSON 已写入各日志目录，路径 `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/print-input-before-run.json`，SHA256 `1c6d3ed500f28ea2baa39a70143bfb74e3abbfdda9e74f17e2643abd2ef4efde`（05 同值同哈希）。
- 04-b 未设 `GATEWAY_BACKEND_DEPS_IMAGE`，由校验器从 `--print-input` 取 tag。

### 3.4 npm 缓存

| 节点 | 缓存目录 | 归档 | 归档 SHA256 |
| --- | --- | --- | --- |
| 04 | `/home/dev/gdds-fe-cache/frontend/npm-cache` | `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` | `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4` |
| 05 | `/home/dev/gdds-fe-cache/fe0/npm-cache` | `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz` | `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4` |

两节点均设 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`；05 另设 `GATEWAY_FRONTEND_NPM_CACHE` 与 `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE` 指向表中路径。

### 3.5 t1 输入（05）

| 静态清单 | SHA256 | 行数 |
| --- | --- | --- |
| `/home/dev/gateway-real-dumps/source-dirs/SHA256SUMS-t1-v1.txt` | `cdb598cdd30198ee94e56469c0c289be1ad1e1e8524e5da13b9d00249eed0163` | 19 |
| `/home/dev/gateway-real-dumps/source-dirs/SHA256SUMS-t1-v2.txt` | `fa2450fac17f5011fee31eb0b163a7355846932c973dedf86bfe10532c32a96a` | 19 |

在 `t1-v1/`、`t1-v2/` 下分别 `sha256sum -c`，均 19/19 OK；入口另记 `t1_manifest_verified`（见 §7.1）。

### 3.6 打包流程

`git diff --stat fe-fe3c-exit 16f4306306 -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx` 为空，不触发 t4。

## 4. 运行记录

| 运行 | 节点 | hostname | wrapper 起止（UTC） | 入口起止（UTC） | 起止 HEAD | 起止 clean | exit code |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 04-a | 04 | gw-dms-test-04.lan | 2026-11-11T04:39:41Z–04:42:23Z | 2026-11-11T04:40:03Z–04:42:23Z | `16f4306306` | clean / clean | 0 |
| 04-b | 04 | gw-dms-test-04.lan | 2026-11-11T04:43:22Z–04:44:39Z | 2026-11-11T04:43:35Z–04:44:38Z | `16f4306306` | clean / clean | 0 |
| 04-c | 04 | gw-dms-test-04.lan | 2026-11-11T04:45:48Z–04:53:36Z | 2026-11-11T04:45:48Z–04:53:36Z | `16f4306306` | clean / clean | 0 |
| 05-t1 | 05 | gw-dms-test-05.lan | 2026-11-11T04:40:48Z–04:45:01Z | 2026-11-11T04:40:49Z–04:45:01Z | `16f4306306` | clean / clean | 0 |

wrapper 与入口日志（入口原日志名带进程号，表中为同目录、逐字节相同的安全名副本；原件保留）：

| 运行 | wrapper 日志 | SHA256 | 入口日志 | SHA256 |
| --- | --- | --- | --- | --- |
| 04-a | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-tests-20261111T043941Z.log` | `088da58cc4fd0834c20d2e4f3b8acfe4a12ae85028a78ff8ad1d9e4c95a1f2f5` | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261111T044003Z.log` | `33fdee3515a3eb4a3958d8afbf5188846c1a2e11b1b8f70696ca85070ab5d1de` |
| 04-b | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-validate-upload-package-20261111T044322Z.log` | `b1d4932eab7697969cf0e54811492c200f3ac254a9b3f6bc9f120a7d081094f1` | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/entry-upload-validator.log` | `a7dda95ef19204a9adb52190de282517a0dca6999c489a251de15a62cb21ab37` |
| 04-c | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-real-backend-e2e-20261111T044548Z.log` | `94da0b0f3b9430aed5cc86b10639a650be5f05ffb28ec08b2ff907edc2339ce2` | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/entry-journeys.log` | `70ef17c069e1d4f9655ad950053a2d11feafd44b49541ce9de243bfc285338b1` |
| 05-t1 | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/fe4a-evidence-05-run-real-backend-e2e-20261111T044048Z.log` | `3a450ca0b666f3549f0b0d729201d98d89653c655d0f789c35bd79b4d42d954e` | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/entry-t1.log` | `3f1a22d78913203f861b634e639bdd4235043a4aa2db9632c5a63a05a27b9d81` |

- 04-a 的入口日志由 `run-tests.sh` 写到默认日志目录 `/home/dev/gdds-fe-logs/frontend/`，表中即原件，未做副本。
- 04-b、04-c、05-t1 的入口原件名带 7 位进程号后缀（原件保留在对应日志目录）；三份安全名副本与原件逐字节相同（`cmp` 通过）。

每次运行构建的 RS 镜像（本机构建，tag 与 config digest 见下；依赖镜像身份见 §3.2）：

| 运行 | RS tag | config digest | 层数 |
| --- | --- | --- | --- |
| 04-c | `gateway-repository-service:fe-16f4306306d0` | `sha256:1b2f8028d635abe7ccab35603d24d7f23e90ee7169cf6d7731e8ffc54eb9f947` | 28 |
| 05-t1 | `gateway-repository-service:fe-16f4306306d0` | `sha256:276d612b9ef9d88e13cdec29ae2a0c04baeeebc141c94bd2cbf6aafd14b0258e` | 28 |

- 两节点各自构建，config digest 不同属预期；config digest、DiffID 与层数均取自入口日志现场记录。
- 04-b 的 `validator_image_tag` 为 `gateway-backend-validate:fe-16f4306306`，`dependency_image_config_digest` 与 §3.2 的 backend 依赖一致。

## 5. 04-a

- `run-tests.sh --e2e`：单元测试 `Test Files 35 passed (35)`、`Tests 214 passed (214)`；Playwright `96 passed (2.0m)`；wrapper 与入口均 exit 0。
- 截图 198 张：`shots/` 顶层 100 张（`*-1280.png`、`*-1920.png`），`shots/1280/` 49 张，`shots/1920/` 49 张。
- 截图目录：`/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots`；清单与旁注：

| 清单 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots/shot-files.txt` | `3db69cef9dc15ac8adeece2d52ce061f108ac4b754db384ebbaa4a77f233aa35` |
| `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots/shot-files.txt.sha256` | `a181e4134f93efd4febdfaeefb73ba296a3aa9896b300a8d054fe15b3f5f7c47` |

- 环境：`GATEWAY_FE_TEST_WORKERS=2`；工具链镜像与 npm 缓存见 §3.2、§3.4（config digest 在入口日志中现场记录）。
- 截图留在 04，由审核会话与复审第 4 轮在 07 上的 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1` 按 `frontend/` 树号比较；本轮不做第 ③ 次稳定性比较。

## 6. 04-b

- `validate-upload-package.sh --output <全新空目录> --log-dir <本次日志目录>`；未设 `GATEWAY_BACKEND_DEPS_IMAGE`。
- `dependency_image` 为 §3.3 的 backend 依赖 tag；其 `lock-` 后缀等于 `dependency_input_sha256` 前 12 位，正文不写 tag 后缀，身份见 §3.2。
- `dependency_image_config_digest=sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`，19 个 DiffID。
- `RESULT packages=4 failures=0`：`with-logics OK members=3`、`without-logics OK members=2`、`missing-dbcfg OK rejected=UPLOAD_CLOSURE_INVALID`、`long-path OK members=3`。
- 4 个包：`/home/dev/gdds-fe-evidence-04/fe4a-16f43063/upload-package/with-logics.tar.gz`、`without-logics.tar.gz`、`missing-dbcfg.tar.gz`、`long-path.tar.gz`。
- exit 0；起止 clean。

## 7. 04-c

- 完整集 `--suite journeys --subphase fe3c`；`suite_cases_total=20 suite_cases_passed=20 suite_cases_failed=0`，无 flaky；`journey_scopes=20`、`journey_identities=65`。
- `openapi_compare=match`；`cleanup_status=ok`；`playwright_process_exit=0`；wrapper 与入口均 exit 0；`busy_end=absent`。

### 7.1 20 个用例

| scope | 结果 |
| --- | --- |
| `r1-states` | passed |
| `r2-preview` | passed |
| `r2-full` | passed |
| `r3-truncated` | passed |
| `r4-submit` | passed |
| `r5-idempotency` | passed |
| `r6-reject-approve` | passed |
| `r7-withdraw` | passed |
| `r7-upload-only` | passed |
| `r7-approved` | passed |
| `r7-stale` | passed |
| `r7-reviewer-withdraw` | passed |
| `r9-history` | passed |
| `r10-noperm` | passed |
| `r10-no-preview` | passed |
| `r10-archive` | passed |
| `r11-review-conflict` | passed |
| `r11-workspace-conflict` | passed |
| `j1-archive-mainline` | passed |
| `j2-manual-close` | passed |

### 7.2 J1、J2 预检异常集合（按 FE3 kickoff §4.6 核对）

| scope / 步骤 | case log 行 | 项数 | 异常集合 |
| --- | --- | --- | --- |
| J1 第 2 步 | 19 | 1 | `GENERATION_TIME_MISSING`（MODIFIED） |
| J1 第 7 步 | 22 | 3 | `BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`（INITIAL）、`GENERATION_TIME_MISSING`（MODIFIED） |
| J1 第 11 步 | 25 | 2 | `BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`（MODIFIED） |
| J1 第 13 步 | 27 | 3 | `BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`（MODIFIED）、`PROJECT_IDENTITY_EXCEPTION` |
| J2 第 1 步 | 30 | 1 | `GENERATION_TIME_MISSING`（MODIFIED） |
| J2 第 3 步 | 32 | 8 | `APPROVED_SIBLING_EXCLUDED`×2、`BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`×5（INITIAL×2、MODIFIED×3） |
| J2 第 5 步 | 34 | 7 | `APPROVED_SIBLING_EXCLUDED`、`INITIAL_SOURCE_UNEXPLAINED`（INITIAL）、`BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`×4（INITIAL×2、MODIFIED×2） |
| J2 第 8 步 | 36 | 2 | `BASELINE_TIME_UNAVAILABLE`（BASELINE）、`GENERATION_TIME_MISSING`（MODIFIED） |

逐项与 FE3 kickoff §4.6 的预期集合一致（B ①、B ②、C ②、E ①、E ② 的分布相同）：J1 第 2、7、11、13 步与 J2 第 1、3、5、8 步均相符。`business_issues` 只保留业务相关项：J1 第 13 步去掉 `PROJECT_IDENTITY_EXCEPTION`（2 项），J2 第 3、5 步去掉 `APPROVED_SIBLING_EXCLUDED`。

### 7.3 证据核对第 1 轮 §5 未执行部分的落点

- J1 第 4 步以后：`j1-archive-mainline`，case log 第 21 行（step4）至第 29 行（`j1 ok`）；第 21、22、24、25、27 行分别覆盖第 4、7、10、11、13 步。
- J2 第 8 步：`j2-manual-close`，case log 第 36–37 行（预检与 `j2 ok`）。
- r7 提交人一侧与两侧 `assertClean`：`r7-reviewer-withdraw`，case log 第 12 行；截图 `r7-reviewer-withdraw-r7-reviewer-withdraw.png`。
- r11 证据截图与两侧 `assertClean`：`r11-review-conflict`，case log 第 17 行；截图 `r11-review-conflict-r11-review-conflict.png`。

### 7.4 fix2 的 C12 第 1 条

错误提示移出按钮行（过期通过、`ARCHIVE_CLOSED` 在对话框关闭后出现）在 journeys 的 20 个 scope 中都无法构造：真实旅程未覆盖，由模拟接口 V12 覆盖（复审第 4 轮 N24）。

### 7.5 耗时

- J1：`04:51:01.806`–`04:52:14.534`，72.7 s。
- J2：`04:52:14.546`–`04:53:29.893`，75.3 s。

只报告，不作验收判定。

### 7.6 日志与截图

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/evidence/journey-cases.log` | `21bc936b4f12ac65dde0ba409d8937d30de05a00fc591394912eca8cc2a635ad` |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/evidence/journeys-shots.txt` | `0a861583ed8c22290e12b288b0b5a159ff7fc0c33a09a4a1c956eb49aba7fcdc` |

- case log 37 行；`suite-summary.txt` 与 `results.json` 均在本次日志目录。
- 截图目录：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/evidence`，24 张 PNG；`journeys-evidence`（`/home/dev/gdds-fe-evidence-04/fe4a-16f43063/journeys-evidence`）下只有空的 `test-results`。

## 8. 05-t1

- `--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`；`suite_cases_total=1 suite_cases_passed=1 suite_cases_failed=0`；`1 passed (2.9m)`。
- `openapi_compare=match`；`suite_exit=0`；`cleanup_status=ok`；`busy_end=absent`；均 exit 0；起止 clean。
- 证据目录 `/home/dev/gdds-fe-evidence-05/fe4a-16f43063/t1-evidence` 下只有 `test-results`；参考截图落在日志目录的 `evidence/`。

### 8.1 输入核对

- 入口记 `t1_input_dir=t1-v1 files=19 bytes=6,853,875`、`t1-v2 files=19 bytes=6,854,427`。
- `t1_manifest=...SHA256SUMS-t1-v1.txt`、`t1_manifest_verified=t1-v1 files=19`；两份静态清单见 §3.5。
- `t1_expected_from=vnext/backend/benchmarks/real_dump_journey.py`；预期值从同树代码读取，未手写常量。

### 8.2 FE3 kickoff §8.3 逐条

1. 输入核对：19 行 × 2 的清单在节点上 `sha256sum -c` 通过，入口复核 `t1_manifest_verified` 通过。
2. t1-v1 Preview：`table_count=changed=124+1=125`，`degraded=0`、`failed=0`（`S1B_V2_PREVIEW_CHANGED_COUNTS` 与同树代码一致；测试通过）。
3. t1-v2 Preview：`table_count=125`、`changed=4`（v2 changed 4 + 无额外变更）。
4. v2 FULL：恰好 `baseline_to_initial` 与 `initial_to_modified` 两对，无第三对（v2 FULL 断言通过）。
5. `baseline_to_initial`：`changed=0`、`degraded=0`、`failed=0`；case log 记 `table_count=125`。
6. `initial_to_modified`：`table_count=125`、`changed=4`（v2 changed 4 + composite 0）、`degraded=0`、`failed=0`。
7. 诊断码为空（`anomalies=[]`）；无未捕获页面错误；每次下载经 `parseBundleTar` 成员与摘要校验。

### 8.3 第 1 步 MODIFIED_ONLY 的 renderer 增量

- 本次 t1-v1 MODIFIED：`19,300,352` 字节（18.41 MiB），为 FE3a 的 24.86 MiB 的 0.74 倍，未超过 2 倍（2 倍为 49.72 MiB）。
- t1 FULL：`241664` 字节，只报告；与 MODIFIED 增量不可比（同一浏览器实例、增量口径不同）。
- FE3c 上一轮值为 22,339,584（21.30 MiB）与 21,364,736（20.38 MiB），一并只作对照。

### 8.4 14 张参考截图

`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/evidence/` 下 7 个名字 × 1280、1920：

| 文件名 | SHA256 |
| --- | --- |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-workbench-1280.png` | `ee691da89f524c7b60b99feaaf9a9842ad009e44bb1985e480f0fe07f367458b` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v1-1280.png` | `7997c1b54aa4d026f0f6ad874f54c22860ff2fbcc74d033eb92bb943bdc6179b` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v2-baseline_to_initial-1280.png` | `e5ea1fbcd7bab23df4bf194aa4f4df2864a01569725f27070d7eb871a993a084` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v2-initial_to_modified-1280.png` | `ab0b6ada1f60408d34c3c05343b0922826c1812d93d69f8b7abf2376945db542` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-review-1280.png` | `8d8afbd606de1e804bee69f5666a510cde978365e89d54e97270c19b8b4f18d7` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-history-3node-1280.png` | `03ba15bc552edb2edea9c6d14596b8f444cc0d45bf41e64f86c0a6ff4febf3b6` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-archive-1280.png` | `55e420d5be3bb46a64c756f45938279804a8815e9bc642274e5f008767b2a740` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-workbench-1920.png` | `a5c4ab5544782aedf29cb6870678852e73b56dd078073a1459a1cdba83c50c96` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v1-1920.png` | `9a36b53024f58c17f4dc1b1018652f931baae38438a79a4f3f19af344a6d10ac` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v2-baseline_to_initial-1920.png` | `f37d62bc7e6a85553d6a928e74c5de99fc7e073a4045aa7d2886367b0b0b1bdd` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-preview-v2-initial_to_modified-1920.png` | `c02c34824e200f8d92176fc0500b4e3470764f3879215a87f226aa4c791ac024` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-review-1920.png` | `adfbbb8827351775419ffe1f4adb33e08e7edeba3b3918edda47ca247e23c1ed` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-history-3node-1920.png` | `ca5599ece0e194a8c91a33c3e1ff619291c8bb1ac3cb51b4cd4bc36f92701ea5` |
| `t1-real-data-journey-with-M1-re-measurement-fe4-t1-archive-1920.png` | `403057704b53114e35dd0cb6930d8638e8a31c6d96f3ec659c1d7c8207a5baa3` |

同目录另有 4 张不属 7 个名字的截图（`t1-archive-v1`、`t1-history-three-nodes`、`t1-v1-diff`、`t1-v2-diff`），保留，不在 14 张参考截图清单内。

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/evidence/journey-cases.log` | `7a82bfa1a81ac650bcde8cd194488628441350325ae3d7439983449a3095a7c8` |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/evidence/t1-reference-shots.txt` | `d45d1ceece47a78988f4619060c1fa8ac8aecf46c2d4463ddb8ab912a9c9000b` |

- case log 9 行：第 1–2 行输入、第 3 行 `anomalies=[]`、第 4 行归档（head=1）、第 5 行 `composite_changed=0`、第 6 行 `baseline_to_initial.table_count=125`、第 7 行 MODIFIED 增量、第 8 行 `t1 ok`、第 9 行 FULL 增量。

## 9. 其他

- 打包流程筛查：为空（见 §3.6），不触发 t4。
- DC68 事件：无。四项证据均一次运行通过；未发生需要保留首败日志后重做的工具、脚本或参数错误。
- 偏离：
  - 04-b 的 wrapper 结果段记 `wrapper_field_missing exit_code`（入口日志末行有 `exit_code=0`，wrapper 自身 exit 0）；属记录层解析差异，未改动被测对象，不改变判据。
  - 04-a、04-b 的 wrapper 在释放前把标记内容记入 `busy_end`（不是 `absent`）；运行后抽查 `/home/dev/gdds-node-busy.d` 不存在，标记已释放。
  - 04-a 的入口日志写在 `/home/dev/gdds-fe-logs/frontend/`（`run-tests.sh` 的默认目录），其余运行日志在本次日志目录；已加入 04 来源清单。
- 未决：无。第 ③ 次稳定性比较与 owner 确认留给审核会话/设计会话；本轮不推送、不合入 main、不打 tag。

## 10. 回源

提交前用 H 的 `frontend/scripts/check-handoff-hex.py` 核对本文件（回源日志自身哈希不写入本文件，只写路径）：

```text
python3 -I frontend/scripts/check-handoff-hex.py --handoff docs/frontend-vnext/fe4a-evidence.md --git-objects --repo /home/dev/gdds-fe --sha-file /home/dev/gdds-fe4a-handoff/04/handoff-sources-04.txt --sha-file /home/dev/gdds-fe4a-handoff/05/handoff-sources-05.txt --evidence-file /home/dev/gdds-fe4a-handoff/05/evidence/t1-reference-shots.txt --evidence-file /home/dev/gdds-fe4a-handoff/04/entry-journeys.log --evidence-file /home/dev/gdds-fe4a-handoff/05/entry-t1.log --evidence-file /home/dev/gdds-fe4a-handoff/04/print-input-before-run.json --evidence-file /home/dev/gdds-fe4a-handoff/04/ids/identity-toolchain.json --evidence-file /home/dev/gdds-fe4a-handoff/04/ids/identity-backend-deps.json --evidence-file /home/dev/gdds-fe4a-handoff/04/ids/04c-identity-repository-deps.json --evidence-file /home/dev/gdds-fe4a-handoff/05/ids/identity-repository-deps.json
```

结果：

- 回源日志：`/home/dev/gdds-fe4a-handoff/check-handoff.log`。

- exit 0；`summary: 47 distinct full token(s); git=8 sha256=39 allowed=0 abnormal=0; 0 truncated form(s)`。
- 未命中值：0；长度异常值：0；未使用 `--allow`；32 对路径与 SHA256 全部一致（回源日志逐对列出命中来源）。
- 截断形：0（本文件未使用截断形）。
