# FE3b 04 取证 handoff（对象 `dac69890a8`）

- 取证节点：`ct108-gw-dms-04`（`gw-dms-test-04.lan`）。
- 依据：FE3 kickoff（main `885f5c4b64`）§9 FE3b 行；DC30（各一次）；DC68（失败处理）。
- 结论先行：三项运行 exit 均为 0，无产品失败，无工具/取证错误（DC68 未触发）。
  截图 146 张 PNG（25 组 `fe3b-*` × 2 宽度 + 其余回归截图 × 2 宽度），清单见 §4。

## 0. 对象与范围

- 代码候选：`dac69890a8b5691ab641f39bad25d743a64367c9`
 （`test(frontend): wait for held operation before asserting workbench load`）。
- 树：
  - `frontend/`：`54b5a333c6fb5d7ef297bbdec6ecd4e9689e9907`（前缀 `54b5a333c6`）。
  - `vnext/`：`56720104af34a1eb677336f57bdbc07444a56615`（前缀 `56720104af`）。
- 复审基线：复审第 3 轮通过（main `ae3117eb89`）；N5 定向复核通过
  （main `f8d3cb353d`，见 `docs/frontend-vnext/reviews/fe3b-rereview-3-n5.md`，
  证据即本对象）。
- 本 handoff 提交在 `a3b72d4461` 之上（其子提交），不改 fix1–fix4 的文件，
  不合入 main，不推送，不改写已有提交。
- 三项运行都在本对象的 clean、已提交 detached worktree 上进行；运行期间未写
  worktree、未提交、未重建或重新 tag 镜像（第 2、3 项入口脚本按设计构建并在
  结束时删除一次性 `validator`/`RS` 镜像，见各节记录）。

## 1. 节点与传输

- 开始前：`ssh -o BatchMode=yes ct108-gw-dms-04 'echo OK'` 连通；
  04 上 `/home/dev/gdds-node-busy.d/` 不存在（无他人有效标记）；
  `ct107-gw-dms-06`、`ct109-gw-dms-07` 同样无标记（04/06/07 同宿主，当时无计时测量）。
- 04 仓库状态：`/home/dev/gateway-data-management-system` 停在 `2c79d0947f`
 （`[main]`）；已有 `748de5034d` 与 `0e7caf66f4`；未切换任何在用 worktree。
- 传输（`git bundle create … <ref> ^748de5034d`，具名引用 `fe-vnext` 打包，
  裸 SHA 不能建 bundle ref 故用分支名；内容覆盖 `748de5034d..a3b72d4461`，
  含对象提交）：
  - 本地包：`/tmp/fe3b-dac69890.bundle`（183 KiB），内含
    `refs/heads/fe-vnext = a3b72d4461437f6c3d64c6ae3689156a42feb769`，
    需 `748de5034dcb324b5d0fb3740e7a2680da61faf1` 与
    `0e7caf66f4558e3337d5688e263970f2945a64a2`（04 上两者皆有）。
  - bundle SHA256：`6eb95d0422c4a624ecdff232bc8f6a334374b902809c3cf39db58aafec00e432`
   （本地与 04 落盘后两次 `sha256sum` 一致；两地 bundle 现已删除，现已无法复核）。
  - 04 上 `git bundle verify` 通过（exit 0），再
    `git fetch <bundle> fe-vnext:refs/heads/fe3b-evidence-04-dac69890`（exit 0）。
  - 取证 worktree：`git worktree add --detach
    /home/dev/gdds-test-tmp/wt/fe3b-evidence-04-dac69890
    dac69890a8b5691ab641f39bad25d743a64367c9`；`git rev-parse HEAD` 与
    `git status --porcelain` 全程干净（起止均已记录，见 §3）。
  - `ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`
   （`legacy/` 不入 Git）。
  - 04 上核对 `git rev-parse dac69890:frontend / :vnext` 与目标树一致（见 §0）。

## 2. 前提核对（运行前，后两次复核：取证前手动一次、各入口脚本内一次）

- 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`：
  - config digest：`sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`
   （与 `run-tests.sh` 钉选值一致；入口脚本 `docker save` + `docker-save-image-identity.py`
    核对通过，第 1 项与第 3 项日志均有记录）。
  - 全部 RootFS DiffID（7 个，入口脚本逐项比对通过）：
    - `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
    - `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
    - `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
    - `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
    - `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
    - `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
    - `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`
- npm 缓存（04 默认路径，未照搬 05 路径）：
  - 目录 `/home/dev/gdds-fe-cache/frontend/npm-cache` 非空；
    归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`；
  - 归档 SHA256：`0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`
   （与预期一致）；`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`；
    `package-lock.json` resolved 条目 305（第 1 项日志）。
- 依赖镜像（04 上均已存在；缺失即停，本次齐备）：
  - `gateway-backend-deps:lock-d054366c02fa`
    - image ID：`sha256:d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff`
    - config digest：`sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`
    - label `gateway.backend.dependency-input-sha256` =
      `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`
     （与 `--print-input` 一致，第 3 项日志复核 `dependency_input_label` 相等）。
    - 全部 DiffID（19 个；`docker inspect .RootFS.Layers` 与 save 身份一致）：
    - `sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a`
    - `sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104`
    - `sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15`
    - `sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1`
    - `sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a`
    - `sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25`
    - `sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588`
    - `sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1`
    - `sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1`
    - `sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f`
    - `sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6`
    - `sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6`
    - `sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce`
    - `sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c`
    - `sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3`
    - `sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4`
    - `sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0`
  - `gateway-p2r1-repository:lock-6dc9659f0aee`
    - image ID：`sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f`
    - config digest：`sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`
    - label `gateway.p2r1.uv-lock-sha256` =
      `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`
     （与 worktree 内 `vnext/repository_service/uv.lock` 的 SHA 一致，第 3 项日志复核 passed）。
    - 全部 DiffID（16 个）：
    - `sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`
    - `sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`
    - `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`
    - `sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`
    - `sha256:e71a8e608dae14fd4714075be2b4a9414f95cb1320e4f50ac93e8cd04f891182`
    - `sha256:bf9c530779848667dbbd8e30a4f7e461f11bda2c42ebcf25c0b6622e0f36b16b`
    - `sha256:c78079bcff29b229330e0f4f33c055e603d8bda53a1c7244cd776ed333c95fd8`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:3f84221a5ef0c33689c4d15fb53f86dc618c996e67e196d3196ecec7db4bd38e`
    - `sha256:89cb20c39b038b95f15bef87d6533c84e566d9f0fbf073a12287837757376963`
    - `sha256:8983264c3d9c3b6664ff105d488b3f4c5a9526ef3912e25238df939e04523f5a`
    - `sha256:e8d3d2975f360e4ffd7d9d31034595baff845b722c5d10bc52dd7d5834d402d5`
    - `sha256:649ba2e1cef7b5ac098594475f8a9fa901492e72404e9d67c0b446fb411689c3`
    - `sha256:58a6251b35cf2736c01ca83684a7b89d4fc55067344233cf80c629dab3886579`
    - `sha256:3553360462a84b2e4611c386abfde29582bf355197d9ba017a873eec054ea330`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`

## 3. 三项运行记录

占用：第 1、2 项共用一个本人标记（`mkdir /home/dev/gdds-node-busy.d` 原子取得，
`session=fe3b-evidence-04`，`purpose=fe3b-evidence-items1-2-non-timing`，
`started_at=2026-11-09T03:30:54Z`），两项连续运行后释放；第 3 项由入口脚本自行
取得/释放 DC70 占用（外层未取，否则脚本以 exit 3 退出），`occupancy_acquired_at`
与 `flock_acquired_at` 均为 `2026-11-09T03:36:36Z`，`occupancy_released_at` 与
`flock_released_at` 均为 `2026-11-09T03:41:57Z`，运行后标记目录已消失。
每项外层均记录 hostname（起止一致 `gw-dms-test-04.lan`）、起止 UTC、起止 HEAD
（均为对象提交）、起止 `git status --porcelain`（均为空）、入口 exit
（`${PIPESTATUS[0]}`）；外层日志与入口日志的 SHA 见各节。

### 3.1 `frontend/scripts/run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`）

- 命令（worktree 内，`TMPDIR=/home/dev/gdds-test-tmp`，
  `GATEWAY_FE_LOG_DIR=/home/dev/gdds-fe-logs/fe3b/evidence-04`，
  `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`）：
  `frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-shots/fe3b-04-dac69890`
 （截图目录为新建空目录；`docker_network=none`）。
- 时间：外层 `started_at=2026-11-09T03:31:32Z`，入口 `started_at=2026-11-09T03:31:53Z`，
  起止 `ended_at=2026-11-09T03:33:55Z`（约 2 分）。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3b/evidence-04/outer-run-tests-20261109T033132Z.log`
    SHA256：`f4288333003f7f1b98a257fb643713f1dd1332e03248932b3302e916dc434af2`
  - 入口 `/home/dev/gdds-fe-logs/fe3b/evidence-04/frontend-tests-20261109T033153Z.log`
    SHA256：`577e044b64ed47b814169b3e70b37436a5cdcde85fc1a923aa2d4867a092ac70`
   （附 `.sha256` 同名文件；入口按惯例另写，该文件随日志保留）。
- 结论：`exit_code=0`。单测 32 文件 175 项通过；`npm run build` 与
  `check:production-build` 通过；Playwright e2e 63 项全部通过（`63 passed`）。
  跟踪前端归档 `tracked_frontend_archive_sha256` =
  `dc9650f17fdf4e4e035aa0d88bafe9c6154af850a84135089e54a641f4ec5292`。
- 截图：`/home/dev/gdds-fe-shots/fe3b-04-dac69890`，146 个 PNG（§4），清单
  `shots.sha256`（仅 PNG，不含自身）SHA256：
  `13c705e3b782aa2ff50c993fafa605d3d540c2b1a590a72a782648b41692f222`。

### 3.2 `frontend/scripts/validate-upload-package.sh --output … --log-dir …`

- 命令：`frontend/scripts/validate-upload-package.sh --output
  /home/dev/gdds-fe-evidence-04/validate-output --log-dir
  /home/dev/gdds-fe-evidence-04/validate-logs`（输出目录事先为空；日志在 worktree 外）。
- 时间：起止 `started_at=2026-11-09T03:34:45Z`，`ended_at=2026-11-09T03:36:01Z`。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3b/evidence-04/outer-validate-20261109T033445Z.log`
    SHA256：`b12af46782262161a6740c9b2921b9ab9cd6f544aa0cef98f5ef2ebd2ab5fcb4`
  - 入口 `/home/dev/gdds-fe-evidence-04/validate-logs/upload-validator-dac69890a8-20261109T033445Z-1562748.log`
    SHA256：`40836269bb63e6ca2710c3116f31c9321a5972407ff6af17add30803d5dcb25d`
   （附 `.sha256` 文件，其 SHA256 为
    `577198b9b37cd985b79f31b5fd35daa256d3a274563df3754413e1d32d44eeb9`）。
- 校验镜像 tag：`gateway-backend-validate:fe-dac69890a8`
 （`fe-` + HEAD 前 10 位；构建前确认该 tag 不存在，构建网段 `none`，
  结束时由入口 `trap` 执行 `docker rmi` 删除，事后核对已无此镜像）。
  - config digest：`sha256:2e93c6121e05f50d5e82dc0c49c76a37b5f0d37c9a5780bc1caaf072650180ae`
  - 全部 DiffID（13 个）：
    - `sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`
    - `sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`
    - `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`
    - `sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`
    - `sha256:9f6ae69f818aa79ca31dcc3c3fdaae88bcc9ee83e78753e095d08c74e13a8c01`
    - `sha256:519a905ca63f10d3123510f7d30d98c16fe17397ded2c4136c28b330189a14c8`
    - `sha256:da1182fd848112d13f92087ed5f2f6e9265c97fbb1fd9d418ec889b69f3f00af`
    - `sha256:23397010a3eff21d9010627e96b089982d1ef2d7e4f3f757ac8a086685c96827`
    - `sha256:0a3375faa2b5046477269c6120da6978516e7ba7fa16584f1b7e9fd8fbe4d67f`
    - `sha256:c2d72a11859db0cfd5de8d0aa34dffef5c1cb813cdb1845801f7d7dcfd367b54`
    - `sha256:a741990d05e2015c13f5c7b3b47b4e1544ab2cb689d0e6dcc3eee5cb4dd1dd71`
    - `sha256:4fa994f680ce2239e93de5500c545167cbe0cac22b50c6cadd5c8aa59083d3ba`
    - `sha256:afcb635971c59025f07cfd3a8b119c968e1951d92818d94d6d37da1693aee734`
  - 同日志另记录 `toolchain_image_*` 与 `dependency_image_*`，与 §2 一致。
- 依赖输入预检：`required_inputs_match=true`，`record_only_mismatches=none`
 （`backend/uv.lock`、`backend/.python-version` 等 5 项输入 SHA 见入口日志
  `input_sha256` 行与 `image_input … candidate=` 行）。
- 校验结论：`RESULT packages=4 failures=0`；`exit_code=0`。包 SHA：
  - `with-logics.tar.gz`：`6a562b07decf2ce23283ba555b5801eb81df4ec6ce3c0a110672110682ac867d`
  - `without-logics.tar.gz`：`1c4ab2bacd7665a1c9fbbc265eaadc0aa4e5af6f5f9d3bbd1ed415dfc4095972`
  - `missing-dbcfg.tar.gz`：`66ce688f656a618adcc57f556dd31bc86fceaade17336bb3d84764a3585518b1`
   （预期拒绝 `UPLOAD_CLOSURE_INVALID`）
  - `long-path.tar.gz`：`8730309ab9586f512fab20b0eb380db1c29cbdf4e5e6b9c76544b21939010b88`

### 3.3 `frontend/scripts/run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-evidence-04 …`

- 命令：`frontend/scripts/run-real-backend-e2e.sh --suite journeys --subphase fe3b
  --session fe3b-evidence-04 --log-dir /home/dev/gdds-fe-evidence-04/real-logs
  --evidence-dir /home/dev/gdds-fe-evidence-04/real-evidence`
 （外层未取占用，由脚本自行取得/释放；`TMPDIR=/home/dev/gdds-test-tmp`，
  `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`，默认 04 缓存路径）。
- 时间：起止 `started_at=2026-11-09T03:36:36Z`，`ended_at=2026-11-09T03:41:57Z`
 （约 5 分；18 个旅程 03:38:08Z–03:41:50Z）。
- 日志：
  - 外层 `/home/dev/gdds-fe-logs/fe3b/evidence-04/outer-real-journeys-20261109T033636Z.log`
    SHA256：`2416082c20ecaddb618270efad30006f140d76bcef71f14df9041a580138277c`
  - 入口 `/home/dev/gdds-fe-evidence-04/real-logs/real-backend-e2e-journeys-fe3b-evidence-04-dac69890a8-20261109T033636Z-1563806.log`
    SHA256：`9037ff78409d5d81cbc6937a982be1acb6e7e47c7a138603abe1ed17696728e6`
   （附 `.sha256` 文件，其 SHA256 为
    `93ee8926bd3a705dff08c1a3cf4c69f74968765f4356203f077506b1e3a4ec4d`）。
  - Compose 日志 `real-logs/compose-gdds-fe-fe3b-dac69890a8b5-20261109t033723z.log`
    SHA256：`b0ed41cbf480172c64f13dd664bb87e59a8de4c3e7bfbcf72b19b6221e04d4aa`。
  - `results.json` SHA256：
    `13dab768fd67fa9cfa37a17fdd6c53277364ffb9f87db3cf16488db0968e5466`；
    `suite-summary.txt` SHA256：
    `c1898be81ba76ecfa219aab82866b58480be99bf5e656cef46b1b25e555654c3`。
- RS 镜像 tag：`gateway-repository-service:fe-dac69890a8b5`
 （`fe-` + HEAD 前 12 位；由脚本构建，结束时 `trap` 删除，事后核对已无此镜像；
  残留容器无，`docker ps -a --filter name=gdds-fe-fe3b-` 为空）。
  - image ID：`sha256:f00e1e4b8343d7e969bfccf56c532c16223e8dc48bd2a40fe51bc9f1fd646e27`
  - config digest：`sha256:1181f4b5e18e5dbb4c1174ad6a4f7ad8f76b254ee4449c85ce8dfded1d3fe837`
  - 全部 DiffID（28 个）：
    - `sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`
    - `sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`
    - `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`
    - `sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`
    - `sha256:e71a8e608dae14fd4714075be2b4a9414f95cb1320e4f50ac93e8cd04f891182`
    - `sha256:bf9c530779848667dbbd8e30a4f7e461f11bda2c42ebcf25c0b6622e0f36b16b`
    - `sha256:c78079bcff29b229330e0f4f33c055e603d8bda53a1c7244cd776ed333c95fd8`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:3f84221a5ef0c33689c4d15fb53f86dc618c996e67e196d3196ecec7db4bd38e`
    - `sha256:89cb20c39b038b95f15bef87d6533c84e566d9f0fbf073a12287837757376963`
    - `sha256:8983264c3d9c3b6664ff105d488b3f4c5a9526ef3912e25238df939e04523f5a`
    - `sha256:e8d3d2975f360e4ffd7d9d31034595baff845b722c5d10bc52dd7d5834d402d5`
    - `sha256:649ba2e1cef7b5ac098594475f8a9fa901492e72404e9d67c0b446fb411689c3`
    - `sha256:58a6251b35cf2736c01ca83684a7b89d4fc55067344233cf80c629dab3886579`
    - `sha256:3553360462a84b2e4611c386abfde29582bf355197d9ba017a873eec054ea330`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:f34f7061ac5c5042958668454301ecdda0b9ab7b10a560dc03fbb0bd36136a34`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:99c55dca8e11c29de72d56f73f3df80bdbc211bfd0d9f53b8e2dcdb1c6ad156c`
    - `sha256:70dbe6dd6355c509c86e36a0e80d9ee2ba0e58316b20d3240a84225f6cf246c2`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
    - `sha256:0286cd555ad9581c3b283e27d97df04a3d81ea7c1baf4ca774760a45021a7634`
    - `sha256:db143562ee333c6599dac8d66dcfb397aac356f0c86534df406c2a223be79389`
    - `sha256:a59b30564addd40e62fb761077993461447a51d1afbe684457805e9cadb54f90`
    - `sha256:34b56056b3d9e0627985e6139decf79e09dd6d0383649f56f54b8eb832698608`
    - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
  - 同日志另记录 `toolchain_identity`（与 §2 一致）、`dependency_image_id`、
    `dependency_rootfs_layers`（与 §2 的 19 个 DiffID 一致）、
    `rs_dependency_base_image` 与 `rs_dependency_label`（与 §2 一致）。
- `openapi_compare=match`。运行时 `openapi-runtime.json` SHA256
  `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`
 （与 kickoff §4 的生产 OpenAPI 原件一致）；归一化快照与运行时均为
  `e26d9e14b4ee7e699220fafc8b6b8e3420a6d7335fa2171ea685beebc440574a`。
- Playwright：`playwright_process_exit=0`，`18 passed`（3.7m），
  `suite_cases_total=18 suite_cases_passed=18 suite_cases_failed=0`，
  `suite_stats_expected=18 suite_stats_unexpected=0 suite_stats_skipped=0
  suite_stats_flaky=0 suite_stats_errors=0`，`suite_exit=0`；
  18 个旅程（r1-states、r2-preview、r2-full、r3-truncated、r4-submit、
  r5-idempotency、r6-reject-approve、r7-withdraw、r7-upload-only、r7-approved、
  r7-stale、r7-reviewer-withdraw、r9-history、r10-noperm、r10-no-preview、
  r10-archive、r11-review-conflict、r11-workspace-conflict）全部 passed。
- 日志无 token：入口日志中随机 token 值零命中
 （`grep -ciE 'fe3b-(submitter|reviewer|archiver|noperm|nopreview|rs)-[0-9a-f]{16,}'`
  为 0，无 `token=` 行；脚本注释“永不记录 token”，符合）。
- `cleanup_status=ok`；`cleanup_port_8000_busy`、`cleanup_dolt_processes` 均无异常
  （日志 `cleanup_status=ok`，事后端口与 dolt 均空）。

## 4. 截图清单（交 owner 看图）

- 目录 `/home/dev/gdds-fe-shots/fe3b-04-dac69890`：146 个 PNG，
  25 组 `fe3b-*`（`1280/` 与 `1920/` 各 25 张）+ 48 组回归截图 × 2 宽度。
- 清单 `shots.sha256`（`find -name '*.png'` 生成，不含自身）SHA256：
  `13c705e3b782aa2ff50c993fafa605d3d540c2b1a590a72a782648b41692f222`。
- 每组两种宽度文件名仅前缀目录不同（`1280/<名>` 与 `1920/<名>`），下表列文件名
  （省略目录前缀）：

| kickoff 要求 | 文件名（× 2 宽度） |
| --- | --- |
| §6.1 撤回可用 | `fe3b-withdraw-enabled.png` |
| §6.1 禁用：无待审提交 | `fe3b-withdraw-none.png` |
| §6.1 禁用：无权限 | `fe3b-withdraw-forbidden.png` |
| §6.1 禁用：无法确认提交状态（含工作区读取失败） | `fe3b-withdraw-unknown.png` |
| §6.1 其他禁用：W4 已通过 | `fe3b-w4-approved-upload.png`、`fe3b-w4-approved-withdraw.png` |
| §6.1 其他禁用：W6/W8/W10 | `fe3b-w6-attempt-running.png`、`fe3b-w6-withdraw-busy.png`、`fe3b-w6-recovery.png`、`fe3b-w6-resumed-card.png`、`fe3b-w6-preview-resumed-card.png`、`fe3b-w8-upload-disabled.png`、`fe3b-w10-stale-preview.png`、`fe3b-w10-stale-workspace.png` |
| 撤回对话框 | `fe3b-withdraw-dialog.png` |
| 撤回冲突提示 | `fe3b-w5-conflict.png` |
| 撤回成功后的上传步骤卡 | `fe3b-upload-restored.png` |
| W8 工作台上传禁用 | `fe3b-w8-upload-disabled.png` |
| §6.4 D1 | `fe3b-d1-archived.png`、`fe3b-d1-review-topbar.png` |
| §6.4 D2 | `fe3b-d2-closed-at-archive.png`、`fe3b-d2-review-topbar.png` |
| §6.4 D3 | `fe3b-d3-manual-close.png`、`fe3b-d3-review-topbar.png` |
| §6.4 D4 | `fe3b-d4-priority.png` |
| §6.4 D5 | `fe3b-d5-flag.png` |
| 快照刷新与退回用词统一后有变化的页面 | `fe3b-w10-stale-preview.png`、`fe3b-w10-stale-workspace.png`（陈旧快照刷新）、`fe3b-w4-approved-upload.png`、`fe3b-w4-approved-withdraw.png`、`fe3b-d1-archived.png`、`fe3b-d1-review-topbar.png`、`fe3b-d2-closed-at-archive.png`、`fe3b-d2-review-topbar.png`、`fe3b-d3-manual-close.png`、`fe3b-d3-review-topbar.png`（“退回/已退回”用词，FD4） |
| N3：按钮间距 | `fe3b-withdraw-unknown.png`（沿用，交 owner 看图确认） |
| N4：长关闭理由不折叠 | `fe3b-d3-manual-close.png`、`fe3b-d3-review-topbar.png`（D3 截图可见，交 owner 看图确认） |
| N4：被占用时节点仍标“可提交” | `fe3b-w8-upload-disabled.png`（工作区节点状态位，交 owner 看图确认） |

## 5. 保留与清理

保留到 FE3b 退出（04 上，均在 worktree 外）：

- 取证 worktree `/home/dev/gdds-test-tmp/wt/fe3b-evidence-04-dac69890`
 （detached `dac69890a8`，`legacy` 软链；04 证据分支
  `refs/heads/fe3b-evidence-04-dac69890` 一并保留以支撑该 worktree）。
- 外层与入口日志目录 `/home/dev/gdds-fe-logs/fe3b/evidence-04/`
 （含本节外层包装脚本 `run-item{1,2,3}.sh`）。
- 第 2 项输出与日志 `/home/dev/gdds-fe-evidence-04/validate-output/`、
  `/home/dev/gdds-fe-evidence-04/validate-logs/`。
- 第 3 项日志与证据 `/home/dev/gdds-fe-evidence-04/real-logs/`（含 `results.json`、
  `suite-summary.txt`、归一化 OpenAPI 与 `artifacts/`、`evidence/test-results/`）、
  `/home/dev/gdds-fe-evidence-04/real-evidence/`。
- 截图目录 `/home/dev/gdds-fe-shots/fe3b-04-dac69890/`（含 `shots.sha256`）。

已删除的传输中间文件（SHA 见 §1）：

- 本地 `/tmp/fe3b-dac69890.bundle`（已删）。
- 04 上 `/home/dev/gdds-test-tmp/fe3b-dac69890.bundle`（已删；删除前两地一致，现已无法复核）。
- 本地 `/tmp/run-item{1,2,3}.sh`  staged 包装脚本草稿（已删；04 上日志目录内的
  同名副本保留为证据）。

## 6. SHA 核对（脚本）

本文件所有值均从命令输出复制，不手抄。核对脚本 `verify-fe3b-evidence.py`
（位于开发主机 scratch 目录 `/tmp/fe3b-evidence-verify/`，不提交进仓库）
枚举本文全部长度 ≥ 7 的小写十六进制串（前后不能紧邻其他十六进制字符，
大小写均计入边界），按以下规则判定：

- 64 位：必须逐字出现在来源集合中；唯一允许的例外是 bundle SHA
  （删除前两地一致，现已无法复核，见 §1），在脚本中按值显式列出；
- 40 位：必须是仓库中存在的对象（`git cat-file -e` 通过）；
- 7–12 位：含字母的是缩写，必须是某个已核对完整值或仓库对象的前缀，
  或是“前缀…后缀”写法中能对上的两端；纯数字的是日志文件名中的日期/PID，
  必须出现在来源集合中；
- 其他长度一律报错。

来源集合（开发主机 `/tmp/fe3b-evidence-verify/sources/`，均从 04 只读收集，
命令输出直接落盘，未经手抄；`source-index.txt` 为各文件 SHA256 索引，
其全文即下表内容，其自身哈希不另列；04 上 real-evidence 目录内无文件）：

| scratch 文件 | 内容来源（04 只读） | SHA256 |
| --- | --- | --- |
| `frontend-tests-20261109T033153Z.log` | 第 1 项入口日志（`/home/dev/gdds-fe-logs/fe3b/evidence-04/` 复制） | `577e044b64ed47b814169b3e70b37436a5cdcde85fc1a923aa2d4867a092ac70` |
| `outer-run-tests-20261109T033132Z.log` | 第 1 项外层日志（同目录复制） | `f4288333003f7f1b98a257fb643713f1dd1332e03248932b3302e916dc434af2` |
| `outer-validate-20261109T033445Z.log` | 第 2 项外层日志（同目录复制） | `b12af46782262161a6740c9b2921b9ab9cd6f544aa0cef98f5ef2ebd2ab5fcb4` |
| `upload-validator-dac69890a8-20261109T033445Z-1562748.log` | 第 2 项入口日志（`/home/dev/gdds-fe-evidence-04/validate-logs/` 复制） | `40836269bb63e6ca2710c3116f31c9321a5972407ff6af17add30803d5dcb25d` |
| `outer-real-journeys-20261109T033636Z.log` | 第 3 项外层日志（`/home/dev/gdds-fe-logs/fe3b/evidence-04/` 复制） | `2416082c20ecaddb618270efad30006f140d76bcef71f14df9041a580138277c` |
| `real-backend-e2e-journeys-fe3b-evidence-04-dac69890a8-20261109T033636Z-1563806.log` | 第 3 项入口日志（`/home/dev/gdds-fe-evidence-04/real-logs/` 复制） | `9037ff78409d5d81cbc6937a982be1acb6e7e47c7a138603abe1ed17696728e6` |
| `logdir.sha256` | 日志目录 `sha256sum` 输出 | `71084b0179cc29c40347a83a468b6251c6a929630220d94801de920b9c907754` |
| `validate-output.sha256` | 第 2 项输出目录 `sha256sum` 输出 | `aab7445dee6889daf1a54fde9ee20e65db515e23a131acf207a708b566623534` |
| `validate-logs.sha256` | 日志目录 `sha256sum` 输出 | `a4591ba3952614ee855120ade55a2b1e9507803a7a38fce8938560e991d36bdc` |
| `real-logs.sha256` | 日志与证据目录递归 `sha256sum` 输出（34 个文件） | `999ea1ea94100ef83c6ca5577a3dbd80ed2c47427c088ebf2ecf5e899cc82079` |
| `real-evidence.sha256` | 证据目录递归 `sha256sum` 输出（空目录） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `shots-npm.sha256` | 截图清单与 npm 归档的 `sha256sum` 输出 | `f8c999eb3d389fdc91de7a837b8ee54df60916a5908338cc5f0209e7b53406ae` |
| `shots.sha256` | 截图清单（`/home/dev/gdds-fe-shots/fe3b-04-dac69890/` 复制） | `13c705e3b782aa2ff50c993fafa605d3d540c2b1a590a72a782648b41692f222` |
| `inspect-backend-deps.json` | `docker image inspect gateway-backend-deps:lock-d054366c02fa` 输出 | `079670e698dc0f1f4ae89206bcc47f0d1c614f89ddd382fcdbf005a489b06b00` |
| `inspect-p2r1.json` | `docker image inspect gateway-p2r1-repository:lock-6dc9659f0aee` 输出 | `a1e3c86000abb37fdbe6c5df47fc6f2152465d4628513954408dad62635837dc` |
| `p2r1-manifest.json` | `docker save` 经 `tar -xO manifest.json` 提取的输出（同镜像） | `bc6d28ae9e6ccb09c9d2255ef561d158ce45c04548572dfd509044571284c993` |

脚本全文：

```python
#!/usr/bin/env python3
"""Check every hex string in fe3b-evidence-04.md against 04 sources.

Usage:
  python3 verify-fe3b-evidence.py <md-file> <sources-dir>

Rules:
  64 hex: must occur verbatim in the source set, except BUNDLE_SHA below.
  40 hex: must be an object in the repo (git cat-file -e).
  7-12 hex with a letter: git object prefix, or prefix of a checked
      64/40 value, or one end of a "left...right" pair matching a value.
  7-12 digits only: log filename date/PID, must occur in the source set.
  Any other length: fail.
Exit status is 0 only when nothing fails.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

BUNDLE_SHA = "6eb95d0422c4a624ecdff232bc8f6a334374b902809c3cf39db58aafec00e432"
# The bundle held the transfer bytes only. Both sides removed it after the
# two matching checks noted in section 1, so it cannot be redone now.

FIND = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7,}(?![0-9a-fA-F])")
PAIR = re.compile(r"([0-9a-f]{1,})…([0-9a-f]{1,})")


def git_exists(repo, value):
    done = subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", value],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return done.returncode == 0


def main():
    md_path = Path(sys.argv[1])
    src_dir = Path(sys.argv[2])
    top = subprocess.run(
        ["git", "-C", str(md_path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True)
    repo = top.stdout.strip()
    index_path = src_dir / "source-index.txt"
    wanted = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            head, name = line.split(None, 1)
            wanted[name] = head
    bad_index = []
    parts = []
    for name, head in wanted.items():
        data = (src_dir / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != head:
            bad_index.append(name)
        parts.append(data)
    parts.append(index_path.read_bytes())
    pool = b"\n".join(parts).decode("utf-8", errors="replace")
    text = md_path.read_text(encoding="utf-8")
    pairs = PAIR.findall(text)
    hits = []
    for num, line in enumerate(text.splitlines(), 1):
        for item in FIND.finditer(line):
            hits.append((num, item.group(0)))
    counts = {"hex64": 0, "hex40": 0, "short_git": 0, "short_prefix": 0,
              "short_pair": 0, "decimal": 0, "bundle": 0}
    full = set()
    bad = []
    round1 = []
    # First round: 64 and 40 only, so later shorts can use the full set.
    for num, val in hits:
        size = len(val)
        if size == 64:
            counts["hex64"] += 1
            if val == BUNDLE_SHA:
                counts["bundle"] += 1
            elif val in pool:
                full.add(val)
            else:
                bad.append((num, val, "hex64 not in sources"))
        elif size == 40:
            counts["hex40"] += 1
            if git_exists(repo, val):
                full.add(val)
            else:
                bad.append((num, val, "hex40 not a git object"))
        else:
            round1.append((num, val))
    for num, val in round1:
        size = len(val)
        if 7 <= size <= 12:
            if val.isdigit():
                counts["decimal"] += 1
                if val not in pool:
                    bad.append((num, val, "digits not in sources"))
            elif git_exists(repo, val):
                counts["short_git"] += 1
            elif any(item.startswith(val) for item in full):
                counts["short_prefix"] += 1
            elif any(item.startswith(a) and item.endswith(b)
                     and (val == a or val == b)
                     for item in full for a, b in pairs):
                counts["short_pair"] += 1
            else:
                bad.append((num, val, "short not a prefix"))
        else:
            bad.append((num, val, "bad length %d" % size))
    print("md: %s" % md_path)
    print("sources: %s (%d files)" % (src_dir, len(wanted)))
    print("index_mismatch: %d" % len(bad_index))
    for name in bad_index:
        print("  MISMATCH %s" % name)
    print("total_hex_runs: %d" % len(hits))
    print("hex64: %d" % counts["hex64"])
    print("hex40: %d" % counts["hex40"])
    print("short_git: %d" % counts["short_git"])
    print("short_prefix: %d" % counts["short_prefix"])
    print("short_pair: %d" % counts["short_pair"])
    print("decimal: %d" % counts["decimal"])
    print("bundle_excepted: %d" % counts["bundle"])
    print("ellipsis_pairs: %d" % len(pairs))
    print("failures: %d" % len(bad))
    for num, val, why in bad:
        print("  FAIL line %d %s %s" % (num, val, why))
    return 1 if (bad or bad_index) else 0


if __name__ == "__main__":
    sys.exit(main())
```

本次核对输出（提交前在 clean worktree 执行）：

```
md: /home/dev/gdds-fe/docs/frontend-vnext/fe3b-evidence-04.md
sources: sources (16 files)
index_mismatch: 0
total_hex_runs: 197
hex64: 132
hex40: 7
short_git: 37
short_prefix: 4
short_pair: 0
decimal: 17
bundle_excepted: 2
ellipsis_pairs: 0
failures: 0
```

勘误说明：本提交修正第 99、151、194、215、219 行的 5 个 SHA（依据
`fe3b-evidence-check-1` E1，以 04 实测为准），§1 与 §5 补 bundle 已删注记，
重写 §6；运行结果本身无变化；除 E1 外未发现其他不一致。
