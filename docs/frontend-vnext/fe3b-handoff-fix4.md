# FE3b handoff fix4：工作台页续做提示“重试”补用例（N5）

- **复审范围：** `88237dbc3b..` 本提交（fix4 handoff）。
- **代码候选：** `dac69890a8b5691ab641f39bad25d743a64367c9`，`frontend/` 树
  `54b5a333c6fb5d7ef297bbdec6ecd4e9689e9907`，`vnext/` 树
  `56720104af34a1eb677336f57bdbc07444a56615`（与 `88237dbc3b` 一致，未动）。
- **结论：** 复审第 3 轮 N5 已补。只改 `frontend/e2e/workspace-shell.spec.ts`
 （+105/−6），产品代码零改动；新用例在同一提交上连续 2 次完整运行通过，
  G1w 下两支新用例失败、G1c 下三支预览 W9 用例失败而新用例不受影响。

## 1. 新用例说明

两支都只跑工作台页（`/?page=workspace&operationId=submit-op-1&operationKind=operation`，
指针 `active_submit_attempt_id: "attempt-1"`），复用 n3/W9① 的 fixture 写法
（`operationHold`、`clearWorkspacePointer`、`submitAttemptState`），标题按业务行为
命名，不带 N5 与轮次编号：

| 用例 | 对应 | 断言 |
| --- | --- | --- |
| 工作台续做提示重试时按已知 attempt 重读并保留原提示 | n3/W9①、W9③b | hold 住操作时把后端切成双指针为空、attempt 为 ABORTED（`IMPORT_REJECTED`）再放行；`.workspace-notice[role="alert"]` 内显示“提交未完成，请检查上传与 Preview 后重试”+ `IMPORT_REJECTED` + “原始代码”；选目录后卡片“上传并生成预览”与工具栏“上传”可用；记 attempt 读取数，点提示框内“重试”（限定在 notice 内，工作台另有比较托盘/历史抽屉/操作面板的“重试”），`expect.poll` 等 attempt 读取数增加，再断言提示文字、原始代码仍在、“上传”仍可用 |
| 工作台续做提示重试时读不到提交结果仍保留刷新提示 | W9④ 前半 | 双指针为空且 attempt 读不到时提示“无法读取提交结果，请刷新后重试”且无 `IMPORT_REJECTED`；选目录后两处“上传”可用；重试后 `expect.poll` 等 attempt 读取数增加，提示保留、无原始代码、上传仍可用 |

三处与预览页不同的写法（都是工作台页的页面特性，不是产品缺陷）：

- 先 `await held` 再放行：挂载读会沿 attempt 链读被 hold 的操作，工作台在操作
  放行前停在加载骨架上，`组态树` 标题断言必须放在 `releaseOperation()` 之后
  （首轮失败即因此，已按 DC68 修订，见 §3）。
- 提示框定位限定在 `.workspace-notice[role="alert"]` 内，避免命中比较托盘与
  历史抽屉的 `alert`；点击的“重试”限定在该 notice 内。
- “上传可用”的可观测形态：门控放行后工具栏与卡片仍以前置目录为禁用原因，
  故用例先选有效目录（复用 `setDirectoryInput` + `VALID_DIRECTORY`），再断言
  两处可用。这证明的是占用门控已放行，不是目录校验。

## 2. 探针表

一次性提交，只放在 05 节点上，结束后已删除 worktree 与 ref（diff 留在日志目录）：

| 探针 | 提交 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| G1w：工作台页提示“重试”改回 `load()`（`onClick={() => { void retryResumeNotice; void load(); }}`） | `836d6399517a98fb5c50c9f69cf05dcde34f8d80` | 两支新用例失败 | **符合**：仅两支新用例失败（均卡在 attempt 读取数 `poll`，无重读），单测 175 项、其余 61 项 e2e 通过 | `aa649b0b1f05e93af92d3a21385187825e999ba0496d8b819891c77060da0b44` |
| G1c：预览页提示“重试”改回 `refreshUploadMode()` | `17855424511ff184759c3cc3f8000fb9b8dda46b` | n3/W9①、W9③b、W9④ 失败，新用例不受影响 | **符合**：仅 n3/W9①（attempt `poll`）、W9③b（`IMPORT_REJECTED` 缺失）、W9④（attempt 计数）失败，两支新用例通过；单测 175 项、其余 60 项 e2e 通过 | `f35fcc1d3bb210717fce0afb13ca6a2345199b7e896a30859974b584ae08cf0b` |

## 3. 运行记录

- **节点与占用：** 05（`gw-dms-test-05`，独立宿主；运行前五节点均无占用标记，
  为避开 04/06/07 同宿主的 S4 计时干扰选 05）。`mkdir` 原子取得标记
  `/home/dev/gdds-node-busy.d/fe3b-fix4-n5`（02:53:43Z 起），收尾时释放，
  无残留容器，期间无他人标记。
- **源码传入：** `git bundle`（基线 `88237dbc3b` 在 05 已存在，经 `git bundle verify`
  通过），落盘 SHA256 与源一致：
  `7a4ee83992dff321ebc765baf6c42dce07d4e5538b10f57a3f9c0b915008e416`
  （首包 `926af9f98` 为
  `87d3f56d8ca44f3d03e4c11ecca95dcdbac6d839fde36b29cf9931ff08df5ede`）。
  05 上 `refs/tmp/fe3b-fix4-dac69890` 取包，detached worktree
  `/home/dev/gdds-fe3b-fix4-dac69890`（`legacy` 软链已建），运行前后 clean，
  起止 HEAD 均为 `dac69890a8`。
- **运行参数：** `frontend/scripts/run-tests.sh --e2e`，`GATEWAY_FE_TEST_WORKERS=2`，
  `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`，
  `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`。
  工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest
  `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，
  npm 缓存归档 SHA256
  `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。
- **运行结果（同一提交 `dac69890a8` 上连续 2 次 exit 0，无抖动）：**

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| run1（`926af9f98`，修订前） | 02:54:10–02:56:27 | exit 1：仅两支新用例失败（工作台挂载读被 hold 操作挡住，标题断言 5s 超时；见下 DC68） | `028087c27bded15c6e578c1f5a1112b076e5f0cf8c6b093fabd6f6d8c01080dc` |
| run2（`dac69890a8`） | 02:57:36–02:59:48 | exit 0：单测 32 文件 175 项，e2e 63 项（含两支新用例） | `0b3210b3b42f6fc12205fd74d5bf40ffb231955730f4639bb6bf6b479e3fd288` |
| run3（`dac69890a8`） | 02:59:55–03:02:07 | exit 0：同 run2 | `78938374ec5e42ed3b93dbf20979a4203719c60a906157cada20b33d492ca269` |

内层 `frontend-tests` 日志（`/home/dev/gdds-fe-logs/frontend/`）：
run1 `e16336b4c42ae073171e9039dad1532b438ea96d9577cd524f7ebbf7219c1c38`、
run2 `60f3f90a6ed91aaa341765af4c19ecc4add79b33b52ca384f2abf646ca51e9b0`、
run3 `450d20547ebb41f753a139e787ca5746e9299f8983194619543ed8cffda69870`、
G1w `3ddd496bb37f39a5968ee58411d73db6099376b4ce9e81f073c6f66d798e33bc`、
G1c `e4decd99a9f2f3c609a2dceac616bf8ee5f023862d2e2a138007bc7217e05842`。

- **DC68 首轮修订：** run1 失败后停止（保留原始日志）、修订（`held` 前置、
  标题断言加 15s 超时，仅 e2e 用例改动）再重验；run2/run3 为修订稿在同一提交
  上的两次完整通过，不是无修改重试。

## 4. 不重跑项的理由（本轮只改 mock e2e 用例）

- 真实后端 journeys：不触及产品代码、fixture 与 API 契约，mock 旅程的通过已
  覆盖改动面；04 取证会按 kickoff §9 另行运行。
- `validate-upload-package.sh`：改动面无打包输入（fixtures、脚本、依赖锁均未动）。
- 截图：改动面无 UI 文案、布局与样式；FE3b 截图证据沿用 rereview-3 的 146 张。

## 5. 遗留与后续

- 本提交只新增本文件，不改 fix1–fix3 与代码。
- 05 上保留（FE3b 退出后清理）：detached worktree
  `/home/dev/gdds-fe3b-fix4-dac69890`、`refs/tmp/fe3b-fix4-dac69890`、传输 bundle
  与 `/home/dev/gdds-fe-logs/fe3b-fix4-n5/` 下全部日志/diff；探针 worktree 与
  `refs/tmp/fe3b-fix4-probe-*` 已删。
- 之后的 04 取证在代码候选 `dac69890a8`（`frontend/` 树 `54b5a333c…`）上运行。
