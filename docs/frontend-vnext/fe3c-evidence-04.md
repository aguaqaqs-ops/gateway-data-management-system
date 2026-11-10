# FE3c 证据 handoff：04 三项 + 05 t1（`e22e39ba15`）

本轮只做证据运行和证据 handoff，不改产品代码。fix2 定向核对已通过
（本地 main `docs/frontend-vnext/reviews/fe3c-fix2-check.md`，`5ddd73b962`），
停止核对为 `docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md`（`f9fa8cd8f8`）。
四次运行一次通过，无失败、无重做（DC68 重新计数，见 §8）。

## 0. 被测对象与传输

| 项 | 值 |
| --- | --- |
| 被测提交（fix2 handoff） | `e22e39ba1528c7a0339c9c800d87fb3f3f95190a` |
| 测试修复 | `e8864ce1da2dcd6d6536c421607abb383ec955d9`（父提交 `031dc3d754`） |
| 产品代码 | `cbb14f578cd22f37355db78a62ba9264f71477d3`（未动） |
| `HEAD:frontend` | `46e425f84eb28936563c8751295a8829e33f3ad6` |
| `HEAD:vnext` | `6368c9c40cf08a97eecf2a0c457a6c16ce448080` |
| 传输 bundle SHA256 | `462d6a57567bf66708029b29db9a5677040f499e61ba977a1007d7cf6ebfa90a` |
| bundle 范围 | `031dc3d754..e22e39ba15`（`git bundle create` 正引用取自分支名 `fe-vnext`；`^031dc3d754` 为界，两节点已有该基点 `refs/fe3c-evidence/031dc3d754`） |
| 节点 fetch ref | `refs/fe3c-evidence/e22e39ba15`（两节点 `bundle verify` okay 后 fetch，fetch 后即删除节点与本地 bundle） |
| 04 新 worktree | `/home/dev/gdds-fe3c-evidence-e22e39ba`（detached，`e22e39ba15`，含 `legacy` 符号链接） |
| 05 新 worktree | `/home/dev/gdds-fe3c-evidence-e22e39ba`（同上） |
| 不复用 | `031dc3d754` 那轮的 `/home/dev/gdds-fe3c-evidence-031dc3d7` 及日志/截图/证据目录原样保留 |

04（`ct108-gw-dms-04`）与 05（`ct108-gw-dms-05`）在不同宿主，可并行；06/07 不承接权威运行。
未切换开发主机任何 worktree 的分支，未切换任何节点上他人或共享的 worktree。

## 1. 运行前检查

- **占用标记。** 每次运行前确认 `/home/dev/gdds-node-busy.d` 无他人有效标记；标记用途若为计时测量则等待，
  任何运行都不开始。四次运行起跑时 `busy_marker_at_start` 均为空。
  `run-real-backend-e2e.sh` 自行取得和释放占用标记（`mkdir` + compose gate `flock`），外层 wrapper 不预取。
- **镜像身份。** 用 `docker image save` + `docker-save-image-identity.py` 现场计算 config digest 与全部
  RootFS DiffID，与上一轮 `preflight-identity.txt` 逐项比对，不比较 inspect ID：
  - 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`：config
    `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 DiffID 全部相同（04/05 均为 MATCH）。
  - 04 `gateway-backend-deps:lock-578e079b762e`：config
    `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`，19 个 DiffID 全部相同（MATCH）。
  - 05 另核 `gateway-p2r1-repository:lock-6dc9659f0aee`：config
    `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`，16 个 DiffID 全部相同（MATCH）。
  - 身份无不符，未触发停止。
- **wrapper 参数检查。** 四份外层 wrapper（零参、路径硬编码）在写任何日志之前检查：
  参数个数、worktree/日志/截图（证据）目录为绝对路径、日志目录已存在、截图与证据目录在 worktree 外；
  任一项不满足以非 0 退出并打印原因到终端。本地 `bash -n` 通过；
  误参（`bogus`）在本地与两节点复验均为 exit 2 且无日志文件落地。
- **缓存与输入。** 04 用默认 npm 缓存（`/home/dev/gdds-fe-cache/frontend/npm-cache`，
  归档 `npm-cacache.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`）；
  05 用 `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`、
  `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`
 （同一 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`）；
  两处 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`。
  05 `--input-root /home/dev/gateway-real-dumps/source-dirs` 含 `t1-v1`、`t1-v2` 与两份 `SHA256SUMS`。

## 2. 四次运行记录

四次运行的起止 HEAD、`HEAD:frontend`、`HEAD:vnext` 均为
`e22e39ba1528c7a0339c9c800d87fb3f3f95190a` /
`46e425f84eb28936563c8751295a8829e33f3ad6` /
`6368c9c40cf08a97eecf2a0c457a6c16ce448080`，
起止 `git status --porcelain --untracked-files=all` 均为空（外层日志原文备查）。

### 2.1 04-a：`run-tests.sh --e2e --screenshots`

- 环境：默认 npm 缓存，`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`，`GATEWAY_FE_TEST_WORKERS=2`
  （停止核对 §3 第 2 项）。
- 节点 `gw-dms-test-04`（`ct108-gw-dms-04`），hostname（入口） `gw-dms-test-04.lan`。
- 起止：外层 2026-11-10T02:44:09Z → 2026-11-10T02:46:44Z；
  入口 2026-11-10T02:44:31Z → 2026-11-10T02:46:44Z。
- 结果：`Test Files 34 passed`，`Tests 207 passed`；`Running 86 tests using 2 workers`，`86 passed`；
  `e2e_workers=2`，`exit_code=0`。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/outer-run-tests-20261110T024409Z.log`，
    SHA256 `094c293632b808ebeb282e664833bef9362b30e773c9dd38e837be5867610b5e`。
  - 入口 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/frontend-tests-20261110T024431Z.log`，
    SHA256 `614da0b7939862a94c323388163defcb647ee5db8020214eabba697d60a10a14`。
- 工具链：tag `mcr.microsoft.com/playwright:v1.64.1-noble`，
  config `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 DiffID 见 §3。
- npm：`/home/dev/gdds-fe-cache/frontend/npm-cache`，
  归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，
  SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- RS：本项无 Compose，不适用。`openapi_compare`/`cleanup_status` 不适用。
- 截图：目录 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots`，共 190 个文件
 （`1280`/`1920` 子目录各 45 张，其中 `fe3c-*` 各 20 张；顶层其余套件截图 100 张），
  `shots.sha256`（190 行）SHA256 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`。
  `fe3c-confirm-disabled-*` 五个名称（`loading`、`blocked`、`unchecked`、`unknown`、`unprocessed`）
  在 1280、1920 下齐全。清单见 §4。

### 2.2 04-b：`validate-upload-package.sh`

- 命令：`frontend/scripts/validate-upload-package.sh --output <空目录> --log-dir <目录>`；
  未设 `GATEWAY_BACKEND_DEPS_IMAGE`。
- 节点 `gw-dms-test-04`（`ct108-gw-dms-04`），hostname（入口） `gw-dms-test-04.lan`。
- 起止：外层 2026-11-10T02:52:23Z → 2026-11-10T02:53:51Z；
  入口 2026-11-10T02:52:36Z → 2026-11-10T02:53:51Z。
- 结果：`RESULT packages=4 failures=0`
 （`with-logics`/`without-logics`/`missing-dbcfg`/`long-path` 各按预期；`final_stage=done`），`exit_code=0`。
- 日记解析出的依赖镜像：`dependency_image=gateway-backend-deps:lock-578e079b762e`；
  `validator_image_tag=gateway-backend-validate:fe-e22e39ba15`；
  `dependency_input_preflight_exit_code=0`，`required_inputs_match=true`。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/outer-validate-20261110T025223Z.log`，
    SHA256 `2d32508b870331a1154567e95d871ec506499e36dcf13cc2d1a6f7e38eb710d9`。
  - 入口 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/upload-validator-e22e39ba15-20261110T025236Z-1713770.log`，
    SHA256 `dc5e9f387c37fe8e30d3ab1e067b1439b249237f2d1200b802fbe1e7f3fb9aa3`。
- 输出目录 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/validate-out`（4 个 tarball + `manifest.json`）：
  - `long-path.tar.gz` `8730309ab9586f512fab20b0eb380db1c29cbdf4e5e6b9c76544b21939010b88`
  - `manifest.json` `c0b96832d60498495a69721d723ab1d834490963e433a35b23897c07d4875ee8`
  - `missing-dbcfg.tar.gz` `66ce688f656a618adcc57f556dd31bc86fceaade17336bb3d84764a3585518b1`
  - `with-logics.tar.gz` `6a562b07decf2ce23283ba555b5801eb81df4ec6ce3c0a110672110682ac867d`
  - `without-logics.tar.gz` `1c4ab2bacd7665a1c9fbbc265eaadc0aa4e5af6f5f9d3bbd1ed415dfc4095972`
- 工具链/依赖镜像身份见 §3（validator 镜像身份由入口日志自记：config
  `sha256:c72010f3679af1f302a7fdea6493428b9167b386cf081cb1bf2de9c1a27845c4`，13 层）。
- e2e/RS/`openapi_compare`/`cleanup_status` 不适用。

### 2.3 04-c：`run-real-backend-e2e.sh --suite journeys --subphase fe3c`

- 会话 `fe3c-evidence2-04`，证据目录
  `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/journeys-evidence`。
- 节点 `gw-dms-test-04`（`ct108-gw-dms-04`），hostname（入口） `gw-dms-test-04.lan`。
- 起止：2026-11-10T02:54:17Z → 2026-11-10T03:02:03Z（外层与入口一致）；
  占用 `occupancy_acquired_at=2026-11-10T02:54:17Z`，
  `occupancy_released_at=2026-11-10T03:02:03Z`（`flock` 同时释放，结束时标记已清空）。
- 结果：`Running 20 tests using 1 worker`（`playwright.real.config.ts` 固定 `workers: 1`），
  20 passed；`suite_cases_total=20 suite_cases_passed=20 suite_cases_failed=0`；
  `suite_stats_expected=20 suite_stats_unexpected=0 suite_stats_skipped=0 suite_stats_flaky=0 suite_stats_errors=0`；
  `suite_exit=0`，`exit_code=0`。20 个用例全部 passed：
  `r1-states`、`r2-preview`、`r2-full`、`r3-truncated`、`r4-submit`、`r5-idempotency`、
  `r6-reject-approve`、`r7-withdraw`、`r7-upload-only`、`r7-approved`、`r7-stale`、
  `r7-reviewer-withdraw`、`r9-history`、`r10-noperm`、`r10-no-preview`、`r10-archive`、
  `r11-review-conflict`、`r11-workspace-conflict`、`j1-archive-mainline`、`j2-manual-close`。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/outer-journeys-20261110T025417Z.log`，
    SHA256 `4e5e80d1090436bcfd38dea260e5d0a6becd561c9e02350ab9356000bda94b8b`。
  - 入口 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/real-backend-e2e-journeys-fe3c-evidence2-04-e22e39ba15-20261110T025417Z-1714828.log`，
    SHA256 `de0b92b98167bb5032b30df95e5bdd8ee858859a0de78717bdc13d8af16f4333`。
- 工具链：tag `mcr.microsoft.com/playwright:v1.64.1-noble`，
  config `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 DiffID 见 §3。
- npm：默认缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`，
  归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- RS：`rs_image_tag=gateway-repository-service:fe-e22e39ba1528`（本运行构建），
  `rs_image_config_digest=sha256:abd4e7f7e363c5ed44073e018256c0668805bf56ac6f98715183671e976c7c36`
 （28 层），`rs_image_id=sha256:b4fb452ba6993ca56ab8f1e73170733ec9dd076bbbd801c4e74862dc52e8788e`；
  依赖 base `gateway-backend-deps:lock-578e079b762e`、
  RS 依赖 base `gateway-p2r1-repository:lock-6dc9659f0aee`（本机均有，label 校验通过）。
- `openapi_compare=match`，`cleanup_status=ok`，`worktree_clean_end=true`。
- 证据目录含 `test-results/`（空，`docker cp` 无内容可拷）；
  旅程截图与 `journey-cases.log` 在日志目录的 `evidence/`、`artifacts/`、`results.json`、
  `suite-summary.txt`、`compose-*.log`、`openapi-*.json` 中（见 §9 保留清单）。

### 2.4 05-t1：`run-real-backend-e2e.sh --suite t1 --subphase fe3c`

- 命令含 `--input-root /home/dev/gateway-real-dumps/source-dirs`；会话 `fe3c-evidence2-05`；
  证据目录 `/home/dev/gdds-fe-evidence-05/fe3c-e22e39ba/t1-evidence`。
- 节点 `gw-dms-test-05`（`ct108-gw-dms-05`），hostname（入口） `gw-dms-test-05.lan`。
- 起止：2026-11-10T02:46:55Z → 2026-11-10T02:51:05Z（外层与入口一致）；
  占用由入口脚本取得并释放，结束时标记已清空。
- 结果：`Running 1 test using 1 worker`，`1 passed`；
  `suite_cases_total=1 suite_cases_passed=1 suite_cases_failed=0`；
  `suite_exit=0`，`exit_code=0`。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3c-evidence2-05/outer-t1-20261110T024655Z.log`，
    SHA256 `463a127da189cf2dc52c5b87c1213206d8b509774343ee68778adc954ebb8fa1`。
  - 入口 `/home/dev/gdds-fe-logs/fe3c-evidence2-05/real-backend-e2e-t1-fe3c-evidence2-05-e22e39ba1-20261110T024655Z-3076926.log`，
    SHA256 `f8a6387ec016c14e6ec421a79fbf2416ed89fc0329b1cddd61979258b0a70bdb`。
  - case log `/home/dev/gdds-fe-logs/fe3c-evidence2-05/evidence/journey-cases.log`，
    SHA256 `56399d9ffdd8d295cd57c56220fe6b09e7b35f20447c60190a0a19a18a840a45`。
- 工具链：tag `mcr.microsoft.com/playwright:v1.64.1-noble`，
  config `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 DiffID 见 §3。
- npm：`/home/dev/gdds-fe-cache/fe0/npm-cache`，
  归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，
  SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- RS：`rs_image_tag=gateway-repository-service:fe-e22e39ba1528`（本运行构建），
  `rs_image_config_digest=sha256:b16535b43a43be992b4b2ac67873c4bbc396d10790a3917cf93711725ec9197f`
 （28 层），`rs_image_id=sha256:2400b04f30cf85d900f65669abae0cc59a656f0fe07c09df2f24c1c343944b31`；
  依赖 base `gateway-backend-deps:lock-578e079b762e`、
  RS 依赖 base `gateway-p2r1-repository:lock-6dc9659f0aee`（label 校验通过）。
  与 04-c 同 tag 但 config 不同：两节点各自构建，产物不同属正常，不跨节点比较，以各运行日志自记值为准。
- `openapi_compare=match`，`cleanup_status=ok`。
- 两份清单（各 19 个文件，`sha256sum -c` 通过）：
  - `t1-v1` `SHA256SUMS-t1-v1.txt` SHA256
    `cdb598cdd30198ee94e56469c0c289be1ad1e1e8524e5da13b9d00249eed0163`
  - `t1-v2` `SHA256SUMS-t1-v2.txt` SHA256
    `fa2450fac17f5011fee31eb0b163a7355846932c973dedf86bfe10532c32a96a`
- `baseline_to_initial.table_count=125`，`composite_changed=0`。
- 两次 M1（`journey-cases.log` 原文）：
  - `t1-m1 step=t1-v1-modified renderer_increment_bytes=22339584`（21.30 MiB；
    第 1 步 MODIFIED_ONLY，与 FE3a 的 24.86 MiB 对照，0.86 倍，低于 2 倍）。
  - `t1-m1 step=t1-full renderer_increment_bytes=13828096`（13.19 MiB；第 4 步 FULL 只报告，
    见 §6 Q23 注明）。
- 证据目录 `t1-evidence/test-results/` 为空（同 §2.3 说明）；旅程截图（4 张）与 case log 在日志目录的
  `evidence/` 下，`artifacts/`、`results.json`、`suite-summary.txt`、`compose-*.log`、
  `openapi-*.json` 同目录。

## 3. 镜像身份明细

### 3.1 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`

（04/05 预检与各入口日志一致，7 层）

config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`

- `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
- `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
- `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
- `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
- `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
- `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
- `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`


### 3.2 依赖 base `gateway-backend-deps:lock-578e079b762e`

（04 预检 MATCH；04-b/04-c/05-t1 入口日志自记一致，19 层）

config digest `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`

- `sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a`
- `sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104`
- `sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15`
- `sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1`
- `sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a`
- `sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25`
- `sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588`
- `sha256:67d63b771cd348af352797d3150d4ee7aeca9986f64b7056485b9dca3721e439`
- `sha256:2719d97bf583d5eae11bb1a7a1375cb2a002a5a98c7f5e046cdb3bea3aa2fb2b`
- `sha256:5a9ee4c4d7a73cc1e7255a138f0872221f5c2354b70408210883fa7e944b6cd5`
- `sha256:abac700db849ee4862add67cea9bc027f2e2d5cac936c146025f60fefdb4ebda`
- `sha256:0818d9d3dc213d56f6c764e9cb2ce6ed4d43e9389140461e59e6e936dcd96b8f`
- `sha256:09e1c6b3349d61e1455a91d1535d0c15e22d7a39be95916c420ac1d2c2965b2f`
- `sha256:9703c617bd63873d3dc32a3a6f7b6f4a46db73395a133d55e0474f36cff1f334`
- `sha256:77a8e32e3ec659415a6e088dced874222804ce1097adc3a9f387a17f5ad43967`
- `sha256:a2bb340a942801e7b162d301bf13e3e30020cb3ede57edf1be9bd2c2592d8bd4`
- `sha256:2ede7fbd16d37ae3f56c5f83494788173d2b96e17d7c95ac39c112267037ecff`
- `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
- `sha256:a779f7e472c38ed4ab09448c5b2b14fc97e02996cfc0b87360c9ea159fd4e2a3`


### 3.3 validator 镜像（04-b 构建）

tag `gateway-backend-validate:fe-e22e39ba15`（运行结束已按脚本删除本地 tag），13 层：

config digest `sha256:c72010f3679af1f302a7fdea6493428b9167b386cf081cb1bf2de9c1a27845c4`

- `sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`
- `sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`
- `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`
- `sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`
- `sha256:9f6ae69f818aa79ca31dcc3c3fdaae88bcc9ee83e78753e095d08c74e13a8c01`
- `sha256:519a905ca63f10d3123510f7d30d98c16fe17397ded2c4136c28b330189a14c8`
- `sha256:1dfba3ee1706bc152786e4d31817b826c77f1dd2e522379f12d3f5791b7bbbc4`
- `sha256:fea71dbaa009f0db2361dcc048775920cb2addc1df9d11c0e31c7b6c76dd1689`
- `sha256:1d72baf0ea3a967c14fb26d88f6144b2b1f86738fb79622034378f8f9834561d`
- `sha256:a86556dfa743c370b7a11bbc7bb68738ae7a5fc9b046c9b17c8bb9b7ca2a41a2`
- `sha256:0559b807c81558501b07144322438d4b7990d515ac6cdaad6d4893f4b3feeea1`
- `sha256:7c835fcb7072b3dbe74141f1210f60584c0e4bc5efeac31dc65d46a1165f64bd`
- `sha256:c3b66c61db249d25f2971a93833e2adf1e788c022963ab947f4ab4ff0a044f6c`


### 3.4 RS 镜像（各运行构建，不跨节点比较）

- 04-c：tag `gateway-repository-service:fe-e22e39ba1528`，
  config `sha256:abd4e7f7e363c5ed44073e018256c0668805bf56ac6f98715183671e976c7c36`
  （28 层），image id `sha256:b4fb452ba6993ca56ab8f1e73170733ec9dd076bbbd801c4e74862dc52e8788e`。
- 05-t1：同 tag，
  config `sha256:b16535b43a43be992b4b2ac67873c4bbc396d10790a3917cf93711725ec9197f`
  （28 层），image id `sha256:2400b04f30cf85d900f65669abae0cc59a656f0fe07c09df2f24c1c343944b31`。
- 预置 RS 依赖 base `gateway-p2r1-repository:lock-6dc9659f0aee` 在 05 预检 MATCH
  （config `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`，16 层）。

## 4. 截图清单（`fe3c-*`，按宽度逐行）

截图目录 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots`；
`shots.sha256`（190 行）SHA256
`63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`。
`fe3c-confirm-disabled-*` 五个名称（`loading`、`blocked`、`unchecked`、`unknown`、`unprocessed`）
在 1280、1920 下齐全（各 5 个，共 10 个文件）。

### 4.1 1280（20 个）

| 路径 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-accept-dialog.png` | `a936cf18d6c1d7808132d85b4f517c161ce1539234348b6e5f1362f5622cfd22` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-blocker-no-entry.png` | `cd0ac3da2087e9158645acb30fd62252f5bbfa4139f6e53c083b4d1cce8bf52e` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-close-dialog.png` | `7cdb0715c0cc890a5c4d84ce6380bcbc83385562b69af414323ef2263cbc863d` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-close-result.png` | `e761fd23f19c190d0398126e434ecab4f2390f8cbcce9ce1f04e6fac3ad9f273` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-confirm-disabled-blocked.png` | `a1faa79ef1186d4ccc3a6d43385d09c62e02798a52d276e0476ebb605b925782` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-confirm-disabled-loading.png` | `e12d0da50a1af9c63542c9179996c313c3e9a0f4e4da10916abca17118997676` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-confirm-disabled-unchecked.png` | `0eb84e8dd611b621d079d308f8ed32fce0672ee423bd82ed6589ee0b6c33b47a` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-confirm-disabled-unknown.png` | `0dde3389aeecdda4b5c4192480c1b62554845a4a348b05ef30dbc808878a0c64` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-confirm-disabled-unprocessed.png` | `66f922e3b40dd37d861645776826925a2db44ad1146f9dce26be4c81af9b90bb` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-disabled-unknown-code.png` | `5970c814803b76208844f2e5505c8785b9aa0dbe587f2270c26617181d099a43` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-disabled-unprocessed.png` | `39558e6bb3cc29bdca1cfc9bc8dfbbaf8d961f26d458236a3e83ef33af4a915b` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-last-not-max-card.png` | `346ffa752d700389759f097c5679cb5e59b5bcc1d69fb3ec674342f36a63e558` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-many-first.png` | `169144e7b0439959cf374b0b8db2b483fba1c3ca406f649285c44ab8e00f9111` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-pending-blocked.png` | `67b8ed57e670e5c50862054bb63d0d238d838b4c467f22059ee896299b300c08` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-revoke-dialog.png` | `1811a8d966f7dcf06c77109d81f0e7f4772535dd6caad70e0c16d6d562ca110b` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-source-accepted.png` | `5f913945417280e79b2897604950413e4d453777384f58ddd08ab38cf0c68251` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-start-rejected.png` | `4575a3e96d36d4bf7fcc85d284ec2929b51d38a4e486f95fedff64fd87dbd3d8` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-time-regression-card.png` | `7e58cbed90e825d4157520f8e4c0a97f6c53d42144f423d9318abb565aaa605e` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-twoside-accepted.png` | `a6b02578cd56079b261fb9f685ef6a6a398eb3dddafe9f4dd88814625950e18f` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1280/fe3c-validation-overview.png` | `9f1f431e999894a475367e77d03ad8551b00faffb9858adb81d3f56747de92da` |

### 4.2 1920（20 个）

| 路径 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-accept-dialog.png` | `0c02d12efdfc6e6889e3156ad8114d4d19565dc99082f8b0331a27065c203f9c` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-blocker-no-entry.png` | `dd270cb83e29a9f7ce87971f7aa3ad3c18999499e9a23d28b7abf03a4f1ab601` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-close-dialog.png` | `d7500bf23df74ed2b503ebd7e720d0c46c28f125b93eceb3aaa36ecbd08a7d64` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-close-result.png` | `0c5b1db9e5ed9c3d3d9244fc0a6fd106ac2384596946ca4143cc02ec6d306771` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-confirm-disabled-blocked.png` | `dd270cb83e29a9f7ce87971f7aa3ad3c18999499e9a23d28b7abf03a4f1ab601` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-confirm-disabled-loading.png` | `f57b3d660ad30be7d4dd354b699d720e52918a4a4171d31011bb13fc062e042f` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-confirm-disabled-unchecked.png` | `06ada404fd293cd8fdfa36af61df83f2ee2471bcc5fe9a8fcfa1821d01d411e9` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-confirm-disabled-unknown.png` | `b98fb1a079621285e1693f9c780843eecd4cc90bd360c839ebbd93328a701694` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-confirm-disabled-unprocessed.png` | `ff2ac8576056ba5f0ab702c4446b2388d03bc7c4059eb23bec72662a8a515133` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-disabled-unknown-code.png` | `b98fb1a079621285e1693f9c780843eecd4cc90bd360c839ebbd93328a701694` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-disabled-unprocessed.png` | `9eb3980ccd351b62e284f49f1d5a35b64b9b5ad761d7bd6d47704143b8d3b7ed` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-last-not-max-card.png` | `efd248e6b95465eb237d1b74c4dda2007516994eb1edf5da94e8a41b72944c94` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-many-first.png` | `9250aca853904af8f7aed70ead03fe6112e3da01d5a9b22617455b9e94948c82` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-pending-blocked.png` | `2a946e472087a8d6d46432d969dbd3ed9f90ea50174a6550855e1864282c3d02` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-revoke-dialog.png` | `00e077031a8439560ab5b966093a8ef5bb0505285b17564d2b0665f75ce8204f` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-source-accepted.png` | `1dda5584d4c7809e1cad162a19590a8cb5e4a958b679f9a57cd8122d83ed4b4c` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-start-rejected.png` | `c77e34b5a73f649483e9882a4b3d073729ea1bf527e0c1bfe62b514904f6e89c` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-time-regression-card.png` | `b274b005299204b68eea5674e04afa713817596d7edab584da3ced58f5078883` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-twoside-accepted.png` | `6bcbe2a09a7f692af54a95c84b6d1c090aeee00edf1ecc7fc15bfce5c5ba0823` |
| `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/1920/fe3c-validation-overview.png` | `f74ac3693739b5469cd0c792f84820614a9dc4136862c6aad5445ba0c178230c` |

## 5. 前次运行（`031dc3d754`，已停止，只作参考，不作证据）

- 04 `run-tests`：外层
  `/home/dev/gdds-fe-logs/fe3c-evidence-04/outer-run-tests-20261109T180627Z.log`
  SHA256 `1049fa85aeb54df362719ad391f60244793338ff836895ebad6657c5c26066f3`，
  入口 `frontend-tests-20261109T180649Z.log`
  SHA256 `e5e39c55f36e3d9c7ecf3bacf1dc81e98dde925abaf0d79828d9f73a46427f15`，
  exit 1（B7 `Route is already handled!`，用例路由竞态，见停止核对 §2）。
- 停用：B7 失败发生在被测对象运行之后，按 DC68 停止正确；新被测提交重新计数（同 FE2b Q14 先例）。
- 05 t1：外层 `outer-t1-20261109T180756Z.log`
  SHA256 `378aa3d6a6db40f9156145505231105fdc47d0ce6c588ba3e059e3c27500f6cf`，
  入口 `real-backend-e2e-t1-fe3c-evidence-05-031dc3d75-20261109T180757Z-3036095.log`
  SHA256 `a60fafc31d40d714d831d4e1a5736ab0be09b192b5754ab2f68dd20622d25b7d`，
  case log `evidence/journey-cases.log`
  SHA256 `7a79568123c100af7eb2fef77707edc9942530dcf950d66b3bb421b68cc9440e`，
  exit 0；字段与本 handoff §2.4 同口径（`cdb598cd…0163`、`fa2450fa…a96a` 各 19 文件；
  `table_count=125`；`composite_changed=0`；MODIFIED_ONLY `22581248`、FULL `13078528`），只作参考。
- 第一次 wrapper 未生成日志文件：18:06:06 那次把 `LOG_DIR` 取成了 `$2`（命令第一个词 `env`），
  bash 重定向失败时不执行命令，入口没有运行，也没有留下日志文件；
  04 全盘搜索 `outer-*20261109T1806*` 只找到 18:06:27 那次（见 fix2 handoff §4）。
  本轮 wrapper 已在写日志前检查参数与日志目录（§1）。

## 6. kickoff 措辞（Q22、Q23 之后）

- Q22、Q23 由 owner 于 2026-11-09 按建议确认（`docs/frontend-vnext/fe3-kickoff.md`
  §11 Q22/Q23、§15.6 D1/D2；§5.3、§8.4、§16.9 V9 已改）。
- fix1 handoff §10 第 1 项（D1：V9 措辞）、第 2 项（D2：t1 FULL 是否新浏览器实例）
  已由 main `1be218b6b540bb1e933123f0fcd891305aa3012c`
  （`Merge main into FE3 kickoff D1/D2 (Q22, Q23) for fast-forward`）处理；
  本 handoff 按新措辞引用，不改 fix1（复审 M4 要求）。
- V9 的“改读 Review”由“全过程没有 `GET .../review`”断言区分
 （范围：打开归档主线、关闭、重新预检，含重试与再次打开；按页面请求记录断言）；
  候选值与同一提交 Review GET 的值相同（后端可达），不为区分而构造不同的候选值。
- t1 FULL 只报告：本轮第 4 步 FULL `renderer_increment_bytes=13828096`（13.19 MiB），
  与第 1 步同一浏览器实例，增量偏低，不可与 MODIFIED_ONLY 或 FE3a 比较，不作对照基线、不作以后基线；
  第 1 步 MODIFIED_ONLY `22339584` 字节（21.30 MiB）照常与 FE3a 的 24.86 MiB 对照（0.86 倍，低于 2 倍）。

## 7. 非阻塞项去向（FE4 带入项；M2 交 owner 看图时判断）

- **N2**（首轮审核）：过期通过后只重读 review、没有重读 History；V12 重读后模拟数据仍无处置，
  缺“按 §6.4 显示”断言。
- **N3**（首轮审核）：来源详情摘要前 12 位没有悬停全文；理由超过 3 行没有折叠；
  原始码（`issue_code`、`subject_digest` 等）没有放进悬停提示。
- **N4**（首轮审核）：J1 第 8、10、11、13 步与 J2 第 1、7、8 步的接受用 API 助手完成，
  界面接受只在 J1 第 3 步走过一次真实 backend（fix1 起 J2 第 4 步 BTU 接受已改走界面）。
- **N5**（首轮审核）：`collectionNotice` 在同一对话框会话中不清除。
- **N7**（首轮审核）：阶段退出合入 main 时再处理；不是设计问题。
- **M1**（复审第 1 轮）：`pendingNotice` 在集合变化时替代 §16.4 要求的提示、集合不变时不清，
  与 N5 同属一机制；FE4 把“冲突提示”与“集合变化提示”分成两处显示并每次加载后清除待用提示。
- **M2**（复审第 1 轮）：关闭对话框正文“关闭提交提交 2（不归档）”显示名重复；
  “确认关闭”成功后仍可点击（同 key 再点只回放 200）。交 owner 看图时判断，或列入 FE4。
- **M3**（复审第 1 轮）：详情映射部分分支只由截图与部分 e2e 覆盖，单测可在 FE4 补齐。
- **M4**（复审第 1 轮）：fix1 handoff §10 第 1、2 项旧措辞保留，新措辞见本 handoff §6，不改 fix1。
- **N9**（停止核对）：`workspace-shell.spec.ts` 中 11 处不带参数的 `unrouteAll`，
  其中 `timeoutFirstCompare`、`historyBundleDelayMs`、`slowPreview` 带延迟，
  可能出现与 B7 相同的竞态，竞态未证实；FE4 统一改为 `{ behavior: "wait" }` 或改用闸门。

## 8. DC68、重做与 wrapper 说明

- 本轮重新计数。四次运行 exit 均为 0，无失败，无重做，不回退开发主机、不改用其他节点。
- wrapper 补丁披露：a、t1 完成后、b、c 运行前，给四份 wrapper 的“新文件列举”循环加了
  `[[ -f "$f" ]] || continue`（跳过 `artifacts/`、`evidence/` 等目录）。
  该补丁只改 log 目录内的 harness 文件；已落地的外层日志内容不受影响。
  补丁前 a、t1 的外层日志各含两条终端告警（`sha256sum: ...: Is a directory`，
  对应空 SHA 的 `new_file=` 行），入口日志自身的 `.sha256` 为准，
  本 handoff 所记入口 SHA 均与节点 `.sha256` 文件逐项核对一致。
- 传输 bundle（本地与两节点 `/tmp/fe3c-evidence-e22e39ba.bundle`）fetch 后已删除；
  07 的 `fe3c-fix1.bundle`、`fe3c-fix2-e8864.bundle` 已删，同目录其他 bundle 未动。

## 9. SHA 回源核对

- 方法：脚本 `/tmp/fe3c-src/sha-check.py` 提取文中全部 `[0-9a-f]{7,}` token，
  逐个对照来源：节点现场 `sha256sum`（本次核对时 fresh 取回 15 个文件）、
  取回本地的 8 份入口/外层日志 + case log + `shots.sha256` + 两份
  `preflight-identity.txt` 全文、`docker image inspect`（预检）、git 对象
  （`cat-file -t`/`rev-parse --verify`，40 位与 7–12 位短值）。
  路径与 SHA 逐行配对（截图按“路径 + 宽度”配对到 `shots.sha256` 行；
  `validate-out` 按 basename 配对到节点现场 `sha256sum` 输出）；
  截断值（`cdb598cd…0163`、`fa2450fa…a96a`）要求在来源中唯一回源。
- 结果（`OVERALL: PASS`，以下为终版全文统计，核对脚本最后一次全量运行输出一致）：
  - 十六进制 token 256 处（去重前），纯数字（字节数、PID、时间戳）10 个豁免；
  - 长度不是 7–12、40、64 的非纯数字值：0 个；
  - 候选值 233 处、129 个不同值，129/129 唯一回源
    （git 对象 / 日志与清单全文 / 节点现场重算 / 已删 bundle 三方见证）；
  - 截断值 2 个不同值（§2.4 与 §5 各出现一次，共 4 处），各唯一回源；
    路径+SHA 配对 45 行（截图 40 + `validate-out` 5），0 失败。
  - RS 依赖 tag 后缀 `6dc9659f0aee` 等于 `e22e39ba15:vnext/repository_service/uv.lock`
    的 SHA256 前 12 位（脚本内重算一致）。
  - bundle SHA256 `462d6a57567bf66708029b29db9a5677040f499e61ba977a1007d7cf6ebfa90a`
    的文件已按 §1 删除，无法重算；创建时本地 `sha256sum` 与两节点到货 `sha256sum`
    三处一致，以此见证值记录。
  - 核对中发现并修正 1 处转抄错误（§5 旧 05 入口日志 SHA 中间 `f` 误作 `d`，
    已按停止核对原文程序化替换复核）；另 backend 依赖 tag 后缀校验假设不成立
    （该后缀为多文件输入摘要，非单 lock 前缀），已改为仅校验 RS 后缀，
    backend 身份以 §1 预检 MATCH 为准。

## 10. 保留与交付

- 保留到 FE3 exit 清理：新证据 worktree（两节点 `/home/dev/gdds-fe3c-evidence-e22e39ba`，
  均为 `e22e39ba15`、clean）、04 `fe3c-evidence2-04` 日志目录、
  05 `fe3c-evidence2-05` 日志目录、04 `fe3c-e22e39ba` 截图与 `validate-out` 及 `journeys-evidence`、
  05 `fe3c-e22e39ba` 证据目录；上一轮 `031dc3d754` 的 worktree、日志、截图与证据目录不动。
- 本 handoff 为 `e22e39ba15` 之上单独的 docs-only 提交，只新增本文件，不改其他文件；
  不合入 main、不 rebase、不推送，不改写已被审核引用的提交。
- 交审核会话：
  - 证据 handoff 提交号（本提交）；
  - 四条运行的外层与入口日志 SHA256（§2；case log 见 §2.4）；
  - 截图目录与 `shots.sha256` 清单 SHA256（§4）；
  - 有无重做：无（§8）。

