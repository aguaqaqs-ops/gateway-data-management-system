# FE3a handoff

- **分支：** `fe-vnext`，范围 `fe-fe2c-exit (749f219d5f)..<候选>`。
- **起点合并：** 本地 main `8983fe86a6` 已用 `--no-ff` 合入 `fe-vnext`，合并提交 `a3834a977c`（提交信息 `Merge main 8983fe86a6 into fe-vnext (FE3a start; vnext tree unchanged)`）。合并后 `git rev-parse HEAD:vnext` 与 `git rev-parse 8983fe86a6:vnext` 都是 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`；相对 main `8983fe86a6`，`git diff --name-only` 只含 `frontend/` 与 `docs/frontend-vnext/`（`fe-fe2c-exit..候选` 另含 main 合并带入的 `docs/backend-vnext/` 文档，非本阶段改动）。
- **代码候选：** `bd320eaee5`（本 handoff 提交只新增本文件，frontend 树保持 `22c6cc27aa8431a92215d7fbbb461b1bfab825b7`）。
- **vnext：** 未改动。
- **说明：** 本会话接手时前一个实施者留下的代码有已知缺陷；本 handoff 只描述当前候选的实际状态，早期草稿中的数字与结论已作废。

## 1. 改动清单与完成标准的逐条对应

`frontend/` 下相对 `fe-fe2c-exit` 共 28 个文件、+1816/−145。

| kickoff 项 | 改动 | 完成标准 | 状态与证据 |
| --- | --- | --- | --- |
| §3.2 / §7 M7 | 新增 `frontend/src/features/workbench/submit-summary.ts` 与 `submit-summary.test.ts`；`SubmitDialog.tsx` 用 History 的提交/基线显示名，拿不到显示名才回退原始 ID，原始 ID 放悬停提示；Preview 摘要显示“本次预览” | 有/无显示名的单测；重拍提交对话框截图 | 完成；单测通过；`submit-identity-confirmation-1280/1920.png` |
| §3.2 / §7 n3 | `workspace-shell.spec.ts` 新增“提交续做时 operation 为 ABORTED”“读取提交结果失败”两个模拟接口 e2e，断言提交按钮禁用、原因文案与操作状态区；`ComparisonPage.tsx` 在结果未决时保持 `submitResumeActive`，只有刷新后 marker 已删才恢复 | 模拟接口 e2e 覆盖两种失败分支 | 完成；全量 runner 34 passed |
| §3.2 / §7 n8 | `SubmitDialog.tsx` 与 `UploadStepCard.tsx` 的 `MANUAL_RECOVERY_REQUIRED` 行改为 `role="alert"` 的 `.form-error` 四段排版（提示、`操作 ID：<code>`、复制按钮、后续正文），ID 与正文分开 | 重拍 `submit-manual-recovery-1280/1920.png` | 完成；截图见 §7 |
| §3.2 / §4 运行框架与 §4.7 smoke | 新增独立脚本 `frontend/scripts/run-real-backend-e2e.sh`、`playwright.real.config.ts`、`e2e-real/smoke.spec.ts`；不并入 `run-tests.sh`；不改 `vnext/` | §3.3 判据由程序断言；05 上真实 smoke 一次通过 | 完成；`bd320eaee5` 上 4 passed，日志见 §3 |
| §3.2 / §4.6 上传输入 | 生成器的 SQL/`logics.xml` 移到 `frontend/src/test/fixtures/source/upload-inputs/`；生成器改为读文件；新增真实 e2e 专用 `frontend/e2e-real/fixtures/real-sql.sql`、`real-logics.xml` | 重新生成 fixture 与已提交逐字节一致；真实 backend 接受上传并 Preview 成功 | 完成；全量 runner 的 fixture 摘要用例通过；真实 smoke Upload 201、Preview SUCCEEDED |
| §3.2 / §5.4 类型一致性 | 新增 `frontend/src/features/api/generated-types.test.ts`：用 `npx openapi-typescript openapi.json` 重新生成到临时目录，与已提交 `openapi.d.ts` 逐字节比较 | 重生成逐字节一致 | 完成；全量 runner 通过 |
| §3.2 / §8.4 M1 | 新增 `frontend/scripts/run-packaging-measure.sh`、`playwright.packaging.config.ts`、`e2e-packaging/packaging-memory.spec.ts`；`UploadStepCard.tsx` 暴露 `data-phase` | t1 v1 MODIFIED；t4 v1 MODIFIED 与 FULL；各 3 次并报中位/最大；按 §8.4 判断 | 完成；`bd320eaee5` 上 3 场景各 3 次通过，见 §6 |
| 调试中发现的必需修复 | `client.ts` 的 sha256 改为 `sha256:<64hex>` DigestRef；`vite.config.ts` 给 `preview.proxy` 也加 backend 代理；真实 smoke 读取 OperationResponse 的 `status` 字段；compose secret 文件 `0644`；释放占用时删除 busy 目录；runner 记录 backend/worker image ID | 真实 smoke 通过、清理核对通过 | 完成；失败与修复记录见 §3.3 |

## 2. 运行框架使用说明

### 2.1 前提

- 节点：05（`ct108-gw-dms-05`），在 clean、已提交的 detached worktree 中运行；源码用 `git bundle` 传到节点。
- 05 上需要：`gateway-backend-deps:lock-<input12>`、`gateway-p2r1-repository:lock-<uv.lock12>`、Playwright 工具链镜像、npm 缓存目录与归档。
- 运行前设置（05）：

```bash
export GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache
export GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz
export GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a
```

- 真实 e2e 会起 Compose 栈并占用 8000，必须按 DC70 先 `mkdir /home/dev/gdds-node-busy.d` 获取整机占用并写会话名（`fe3a-impl`）/用途/开始时间，再 `flock -n /tmp/gateway-compose-gate.lock`；完成清理与残留核对后先释放 flock，再删除 marker 文件，最后 `rmdir` busy 目录。脚本已实现这些顺序和残留检查。

### 2.2 smoke

```bash
cd <clean worktree>
./frontend/scripts/run-real-backend-e2e.sh \
  --suite smoke \
  --log-dir /home/dev/gdds-fe-logs/fe3a/real-smoke-<HEAD12> \
  --evidence-dir /home/dev/gdds-fe-evidence/fe3a/real-smoke-<HEAD12>
```

- 脚本依次：获取占用/flock → 残留检查 → 校验 npm 缓存与工具链身份 → 校验依赖镜像 input/label → 构建本次 RS 镜像 `gateway-repository-service:fe-<HEAD12>`（`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，不覆盖 `:local`）→ 起 RS、等 ready、播种 5 个 scope → 写 provisioned mapping/session/secrets → 起 backend/worker、等 `/readyz` → 比对运行时 OpenAPI → 在 toolchain 容器里 `npm ci --offline && npm run build` 并跑 `playwright.real.config.ts` → 保存 test-results、Compose 日志 → 清理 → 残留核对 → 释放占用。
- 日志与证据都在 worktree 外；日志记录 hostname、起止时间、HEAD、frontend/vnext tree、占用/flock、npm 缓存 SHA、工具链/依赖/RS/backend/worker 镜像身份、Compose 项目名、网络 ID、运行时 OpenAPI SHA、播种仓库 ID、每个用例结果、清理状态和 exit code。
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
- 选目录后通过 CDP `SystemInfo.getProcessInfo` 枚举进程，对每个 PID 写 `/proc/<pid>/clear_refs=5`，记 `VmHWM`/`VmRSS` 基线；上传请求发出后读 `VmHWM` 峰值，主指标取 renderer 的峰值增量。
- 包大小取 multipart 中 manifest part 的 `artifacts.INITIAL/MODIFIED.size_bytes`；打包耗时取页面 `data-phase` 从 `packaging` 到 `uploading` 的间隔。

## 3. 运行记录

### 3.1 05 全量前端 runner（模拟接口 + 截图）

| 项 | 值 |
| --- | --- |
| 节点 | `gw-dms-test-05.lan` |
| 起止 | 2026-11-05T08:05:43Z – 2026-11-05T08:06:36Z |
| HEAD | `bd320eaee5912ca9fe81b2a67fdf26a7d01144d9` |
| frontend tree | `22c6cc27aa8431a92215d7fbbb461b1bfab825b7` |
| 命令 | `./frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe3a/screenshots-bd320eaee5` |
| 结果 | exit 0；typecheck、lint、29 个单测文件 136 项、构建、生产构建检查、34 个 e2e 全部通过 |
| 日志 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T080543Z.log` |
| 日志 SHA256 | `50efe761614aaddca28f4c01b5f25f04401648e6d5827cd330f68ebbf8b7a4fb` |
| 截图 | `/home/dev/gdds-fe-evidence/fe3a/screenshots-bd320eaee5`，94 张 |

### 3.2 05 真实 backend smoke（最终）

| 项 | 值 |
| --- | --- |
| 节点 | `gw-dms-test-05.lan` |
| 起止 | 2026-11-05T08:03:49Z – 2026-11-05T08:05:08Z |
| HEAD | `bd320eaee5912ca9fe81b2a67fdf26a7d01144d9` |
| 命令 | `./frontend/scripts/run-real-backend-e2e.sh --suite smoke --log-dir ... --evidence-dir ...` |
| 结果 | exit 0；4 passed（CreateOrGet/INITIAL、上传+Preview SUCCEEDED+指针一致+无未捕获错误、无权限上传 403、无 Preview 权限 403） |
| Compose 项目 | `gdds-fe-fe3a-bd320eaee591-20261105t080431z` |
| 网络 ID | `1f2796303677d19edd808a7ffb3c2c62840ae4b85dbdc4a37f4a8a922999295e` |
| 播种仓库 | `ed616d6a-d25a-4df9-8c44-a86f6229bf24`；INITIAL 提交 `t3n1uq20upn89p3l5o84ahfdvi7p5l9o` |
| 运行时 OpenAPI | 快照 `a7d9b409c5d4f887fb7ef83a067a95a2b317df4aaf92735e88d54adf7c6be337`；运行时 `95051883e46c5322427c48f63cddf533d879a8f8da9bf09ec5760ceb00cb9356`；`match` |
| 日志 | `/home/dev/gdds-fe-logs/fe3a/real-smoke-bd320eaee5/real-backend-e2e-smoke-bd320eaee5-20261105T080349Z-1255447.log` |
| 日志 SHA256 | `80d2f0bc3ffbca824b19818297b9a6dff79904ec8355c6320e8833b47b627e94` |
| 证据 | `/home/dev/gdds-fe-evidence/fe3a/real-smoke-bd320eaee5`（test-results、trace、compose 日志） |
| 清理 | `cleanup_status=ok`；运行后 05 无本次容器/卷/网络、8000 空闲、无 dolt、无 busy 标记、RS 临时 tag 已删 |

镜像与缓存身份：

- 工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 RootFS DiffID：

```text
sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278
sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07
sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9
sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d
sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc
sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5
sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb
```
- npm 缓存：目录 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- 依赖基础镜像：`gateway-backend-deps:lock-c668cef8e47e`，input `c668cef8e47ea2f75934f23a27b153662ac66ed546faf145ff903448bebea290`，label 与 input 一致，本机 ID `sha256:a944dca0b6e6a5f71c59082d2a3e6ddf93b88c1f929fc011a62dd31f1bd6e15e`，20 个 DiffID。
- RS 依赖镜像：`gateway-p2r1-repository:lock-6dc9659f0aee`（uv.lock SHA256 前 12 位）。
- RS 本次镜像：`gateway-repository-service:fe-bd320eaee591`，本机 ID `sha256:834c278a3c13c3c164f5ad62bcc13173a7712fc3eecadbd4e81d91c82b24b748`；labels：`gateway.p2r1.build-input-revision=861ab2467329…`、`gateway.p2r1.source-tree-sha256=sha256:0fb8cd62742e…`、`org.opencontainers.image.revision=bd320eaee5912ca9fe81b2a67fdf26a7d01144d9` 等。
- backend 本机 ID `sha256:95469dd779acbe23d061c04f60d102bb084239f6923cab41e0e25e63d0793ed7`；worker `sha256:7713a6c46039df44c63c49d414fbe22b3d3501cfa87dbd917466569cf04b3f2e`。

### 3.3 smoke 调试记录（失败不重做，记录用于审核）

| 提交 | 结果 | 原因/修正 |
| --- | --- | --- |
| `1ed1319b9a` | 1 passed / 3 failed | manifest `raw_sha256` 是裸 hex，真实 backend 要求 `sha256:<64hex>`；`client.ts` 修正并加单测 |
| `1e4634297a` | 3 passed / 1 failed | OperationResponse 读取 `state`，实际字段是 `status`；`0712368347` 修正 |
| `0712368347` | 3 passed / 1 failed | 合成 fixture SQL 故意让 `b1_n1_iec104_yc_list` 无 gid，真实 Preview 返回 `KEY_MISSING`；停止交设计会话，决定新增真实 e2e 专用合法输入（见 §9） |
| `13be7cd1ab` | 4 passed | 使用 `real-sql.sql`/`real-logics.xml`；通过 |
| `bd320eaee5` | 4 passed | 最终候选；补记 backend/worker image ID |

早期 `bf6dd969f9` 全量 runner 为 32 passed / 2 failed（n3 两个续做用例按钮仍 enabled），根因是 `ComparisonPage` 在 ABORTED/读取失败时把 `submitResumeActive` 置回 false；`0d722badd3` 修复后 34 passed。该次失败日志：`/home/dev/gdds-fe-logs/fe3a/full-bf6dd969f9/frontend-tests-20261105T070429Z.log`，SHA256 `47fc8fec7baa19bdcf9d510dee004981cc12a31b3d3cac987572da21dfe63d7d`。

## 4. 传输记录

### 4.1 组态目录 → 05

- 开发主机 `/home/dev/gateway-real-dumps/small_cut/small_cut-1` → 05 `/home/dev/gateway-real-dumps/source-dirs/t1-v1`：19 文件，6,853,875 B。
- `small_cut-2` → `t1-v2`：19 文件，6,854,427 B。
- `/home/dev/gateway-real-dumps/large/large-1` → `t4-v1`：528 文件，317,343,632 B。
- 传输时间：2026-11-05T03:15Z–03:16Z；创建时间以 05 本地时间 11:16 显示。容器中一律只读 bind mount（smoke 的 `/input`、M1 的 `/input`）。
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
- config digest：`a8d9d1ac7140bd2025080649a95146833f7ae8c2fb0e429a8f8e3856a0d9307d`；20 个 RootFS DiffID 与开发主机逐一相同：

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

| scope（身份） | 权限 | 序列 |
| --- | --- | --- |
| submitter（提交人，upload+preview） | `workspace_read`、`read_project_history`、`upload_submit_workspace`、`preview_workspace` | 1) `POST /v1/workspaces` CreateOrGet → 201；2) 浏览器打包后 `POST .../upload-revisions`，`MODIFIED_ONLY`（`real-sql.sql` + `real-logics.xml`，根一个占位 `.pmc`）→ 201；3) `POST .../preview-operations` → 202；4) 轮询 `GET /v1/operations/{id}` 到 `SUCCEEDED`；5) `GET .../preview-results/{id}` → 200，`preview_result_id` 与工作区 `current_preview_result_id` 一致。FE3a 不提交、不归档。 |
| no-preview（能上传、无 Preview 权限） | 上述前两项 + `upload_submit_workspace` | CreateOrGet；上传 `MODIFIED_ONLY` → 201；`preview-operations` → 403（`SCOPE_FORBIDDEN`）。 |
| noperm（无上传权限） | 仅 `workspace_read`、`read_project_history`（permissions 非空） | CreateOrGet；上传 → 403（`SCOPE_FORBIDDEN`）。 |
| reviewer / archive | 各自审核/归档权限 | 播种身份与工作区；FE3a smoke 不上传。 |

FE3b 旅程将按 kickoff §4.6 在各自 scope 内继续覆盖：首次 `MODIFIED_ONLY`（空 INITIAL）→ 归档后的 `FULL`（① 原始组态 + ② 本次归档组态）→ 再一次内容不同的 `MODIFIED_ONLY` → `REPLACEMENT_CURRENT_SQL` 的 `MODIFIED_ONLY`（`DIFFERENT_PROJECT` 身份确认）。FE3a 脚本目前明确拒绝 `journeys`/`t1`，这些序列留待 FE3b。

## 6. M1 打包测量（§8.4）

- 节点：05；提交：`bd320eaee5`；方法：生产构建、Playwright Chromium、每次新 browser、`clear_refs=5` + `VmHWM` 增量、主指标 renderer、包大小取 manifest `size_bytes`、打包耗时取 `data-phase` 的 `packaging`→`uploading`。只走模拟 API。
- 报告目录：`/home/dev/gdds-fe-evidence/fe3a/m1-bd320eaee5/`；日志目录：`/home/dev/gdds-fe-logs/fe3a/m1-bd320eaee5/`。

| 场景 | 输入 | 3 次 renderer 峰值增量（MiB） | 中位数 | 最大值 | 3 次打包耗时（ms） | 包大小 |
| --- | --- | --- | --- | --- | --- | --- |
| t1 v1 MODIFIED | 19 文件 / 6,853,875 B | 31.09 / 26.10 / 22.51 | 26.10 MiB（27,369,472 B） | 31.09 MiB（32,595,968 B） | 75 / 78 / 76（中位 76，最大 78） | 461,275 B |
| t4 v1 MODIFIED | 528 文件 / 317,343,632 B | 676.31 / 643.37 / 665.79 | 665.79 MiB（698,130,432 B） | 676.31 MiB（709,165,056 B） | 2278 / 2203 / 2311（中位 2278，最大 2311） | 20,283,589 B |
| t4 v1 FULL | 同上，①+② 两包 | 665.28 / 664.76 / 666.33 | 665.28 MiB（697,585,664 B） | 666.33 MiB（698,695,680 B） | 4616 / 4622 / 4622（中位 4622，最大 4622） | 20,283,589 × 2 = 40,567,178 B |

报告 SHA256：

- `t1v1-modified.json` `eee43c9b2fb77094c003c5d4e5c7ad04d9c3579f52abb314fe2bb38b58214bf3`
- `t4v1-modified.json` `2ca1a76bc98ac408fe1420e9544bc407267b92540c44bf852c726863a3f0b70b`
- `t4v1-full.json` `5ae9bc714906b5de0bee4a3bbfdaeb31e094d9b273c54ec86fd0130858efb2d1`

日志 SHA256：

- `packaging-measure-bd320eaee5-20261105T080643Z-1264350.log` `4b3b68b0ae6961aeae3a04202ada165a3956152cba5150cd97bcd49ff2e9fb13`
- `packaging-measure-bd320eaee5-20261105T080719Z-1265261.log` `5b8bdefbb93f551187e559848f398fe2c3a0917e9494ac34e875200059d37781`
- `packaging-measure-bd320eaee5-20261105T080805Z-1266236.log` `8a7d8cdb407a279f1e188d578be9456458cec4c12a3d7ff1efc6dfc9692a2081`

判断（按 §8.4）：

- t4 v1 renderer 峰值增量最大 676.31 MiB，≤ 1 GiB，满足“单次 1 GB 目录不超过 1 GiB”的当前档要求。
- 按目录大小线性外推到 1 GB：`709,165,056 × 1,000,000,000 / 317,343,632 ≈ 2.08 GiB`（FULL 外推约 2.05 GiB），≤ 3 GiB。
- 结论：FE3a 不需要改流式；M1 测量已完成。FE3b 的旅程上传与 M1 复测仍按 kickoff 执行。

## 7. 截图清单

- 目录：`/home/dev/gdds-fe-evidence/fe3a/screenshots-bd320eaee5`；94 张（47 个场景 × 1280/1920）。
- 聚合 SHA256（`sha256sum *.png | sort -k2 | sha256sum`）：`307feb805e981d8e21d7df3f3103d8dd64a954da2f1dcce30489738c0cae9e0f`。
- M7 提交对话框（`submit-identity-confirmation-1280.png` / `-1920.png`）：
  - 1280 `11591ae7d8c9115f038bea9c4b910ae0a8ec0df9aecd4b928be4033712c4a384`
  - 1920 `26bd50c0b34b51c057a2fee3f776e36a79250f2c0891070259bd883a6017969d`
- n8 `submit-manual-recovery-1280.png` / `-1920.png`：
  - 1280 `7610a1ff4bfac09e20a84bcd3ec4242c16145c8bd00fb2d0f2486d6f76428343`
  - 1920 `aaba47fb1c27be008c8f95047f4e8b77b0294b578da334d9286e83f105dd3a5d`
- 同组其他关键截图：`submit-aborted-*`、`submit-result-*`、`manual-recovery-required-*`、`upload-running-modified-only-*`、`upload-permission-denied-*`；完整 47 个场景名可从目录 `ls` 得到。

## 8. 给 AGENTS 与 testing-conventions 的建议条文（§4.1）

建议在 AGENTS“前端测试（FD7）”下补：

1. **真实 backend e2e 入口：** `frontend/scripts/run-real-backend-e2e.sh` 是独立入口，不并入 `run-tests.sh`；连真实 backend 的运行必须按 DC70 取 `mkdir /home/dev/gdds-node-busy.d` 占用并 `flock -n`，完成后先释放 flock、删 marker，再 `rmdir` busy 目录；释放顺序与残留核对写进脚本而非人工。
2. **输入来源：** 模拟 fixture 的 `upload-inputs/sql-*.sql` 故意包含无 gid 的诊断表，不能直接用于真实 Preview；真实 e2e 使用 `frontend/e2e-real/fixtures/{real-sql.sql,real-logics.xml}`，模拟 fixture 保持逐字节不变。新增真实场景时只改真实 e2e 输入，不改模拟 fixture。
3. **服务用户可读的 secret：** Compose 挂载的 session/token 文件需 `0644`（或对服务用户可读），`0600 root` 会让 repository-service 启动即失败；该类文件仍只写在 worktree 外运行目录。
4. **M1 方法：** 每次测量新建 browser/context；对 CDP 枚举的 PID 写 `/proc/<pid>/clear_refs=5` 后记 `VmHWM` 基线；只报 renderer 峰值增量；包大小解析 multipart manifest 的 `size_bytes`，打包耗时用页面 `data-phase`；不要用整个 multipart body 或 click→request 代替。
5. **节点纪律：** 前端 typecheck/lint/unit/build/e2e 不在开发主机运行；调试统一在 05，04 只在阶段取证时运行。

建议在 testing-conventions 的“前端测试”补：真实 e2e 的日志字段（工具链/依赖/RS/backend/worker 镜像身份、npm 缓存 SHA、Compose 项目与网络 ID、运行时 OpenAPI SHA、播种仓库/INITIAL ID、占用与 flock 起止、清理核对）与 M1 的报告字段（逐次 renderer 增量、中位/最大、manifest size、打包耗时、performance.memory 参考值）。

## 9. 偏差与未决事项

1. **真实 e2e 输入来源（已由设计会话确认）：** kickoff §4.6 原意是让真实 e2e 直接复用模拟 fixture 的 SQL/logics；实际运行时上传 201 被接受，但 Preview 因 `b1_n1_iec104_yc_list` 缺少 canonical key 列返回 `KEY_MISSING`（该表无 gid 是模拟诊断场景的刻意设计）。按 §4.6/§10 停下交设计会话后，设计会话选择“新增真实 e2e 专用合法输入”，现有 fixture 未改、逐字节不变。新增文件为 `frontend/e2e-real/fixtures/real-sql.sql`、`real-logics.xml`。
2. **套件范围：** FE3a 只实现并验证 `--suite smoke`；`journeys`、`t1` 与 `--input-root` 明确 exit 2，留待 FE3b。真实旅程、t1 旅程、归档/审核/撤回的真实 e2e 未在 FE3a 运行（§3.3 已列为 BE-a/BE-d 之后）。
3. **04 取证未执行：** 按要求 04 取证在审核通过后进行；本 handoff 只包含 05 的调试证据。审核通过后需在 04 clean detached worktree 上运行 `run-tests.sh --e2e --screenshots`、上传包后端校验与 `--suite smoke`。
4. **M1 的运行环境：** 按 §8.4 用模拟接口（stub）测量，不连真实 backend；测量的是前端打包内存，不受 backend 影响。M1 数据绑定 `bd320eaee5`；本 handoff 提交只新增文档，frontend 树不变（`22c6cc27…`）。
5. **n3 的失败分支**由模拟接口 e2e 覆盖，未在真实 backend 上重放（当前 backend 还没有对应接口状态）。
6. **05 占用等待：** 07:35Z–07:43Z 05 被 owner 的 `p6-four-workers-exit-fix` 占用，真实 smoke 等待其释放后继续；该等待不影响结果。
7. **RS 临时 tag：** 每次真实 e2e 构建 `gateway-repository-service:fe-<HEAD12>`，清理阶段删除；`gateway-repository-service:local` 与共享依赖镜像未动。
8. **文档提交与证据 HEAD：** 本文件提交后候选 HEAD 会前进一个 docs-only 提交；`bd320eaee5` 上记录的 frontend tree 与候选一致，04 取证以审核后的最终 HEAD 为准。
