# FE4a fix4 handoff

- 父提交：`59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`（fix3 handoff，`fe-vnext` 与 `fe4a-fix3` 的头）
- 代码候选 X：`d12e3b8f706c99c66d0de2e1763f145f95862c92`（第一次 fix4，调试停止，保留，不改写）
- 代码候选 Y：`26236839f7ce3e0f2c2fedd5cddd62b657ee87ea`（修正候选，本轮调试对象）
- handoff 提交：本文件所在提交，由 `refs/fe4a/fix4` 指向；其父为 Y
- 运行节点：`ct109-gw-dms-07` / `gw-dms-07.lan`（D1），`ct108-gw-dms-05` / `gw-dms-test-05.lan`（D2）
- 范围：`frontend/e2e-real/lib/ui.ts` 与 `frontend/e2e-real/journeys.spec.ts`；`frontend/src/`、`frontend/e2e/`、`t1.spec.ts`、`frontend/scripts/` 未改

## 1. 提交与树

| 提交 | 说明 | `frontend/` 树 | `vnext/` 树 |
| --- | --- | --- | --- |
| `59c5b8cfca` | 父提交（fix3 handoff） | `802bdfb1a42b5319b483f3c4324d2b609a1b57b0` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `d12e3b8f70` | X：helper 三点断言与审核组新断言 | `f6a8a1e2649d86b8335e32d920159872fe8ce0c7` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `26236839f7` | Y：helper 按有无 `aria-describedby` 分两支 | `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 本文件所在提交 | handoff 最终提交，`refs/fe4a/fix4` 指向它 | `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |

本文件无法在正文写入自身提交号；最终提交号见交付回复和 `refs/fe4a/fix4`。H 相对 Y 只加本文件，所以两棵树与 Y 相同。`vnext/` 树三处一致，未动后端。

## 2. diff

`git diff --name-only 59c5b8cfca 26236839f7`：

```
frontend/e2e-real/journeys.spec.ts
frontend/e2e-real/lib/ui.ts
```

`git diff --stat 59c5b8cfca 26236839f7`：

```
frontend/e2e-real/journeys.spec.ts |  5 +++++
frontend/e2e-real/lib/ui.ts        | 32 +++++++++++++++++++++++++++++++-
2 files changed, 36 insertions(+), 1 deletion(-)
```

改动说明：

1. `expectDisabledWithReason(button, reason)` 依次断言三点（kickoff §17.2）：
   - `toBeDisabled()`；
   - `toHaveAccessibleDescription(reason)`，三种结构都成立；
   - 原因可见，按按钮有没有 `aria-describedby` 分两支，命中的那一支必须通过：
     - 有：按 id 取得所指元素，其中文字等于 `reason` 的元素可见（X 的实现，原样保留）；
     - 没有：按钮后面的兄弟元素中有 `span.disabled-reason`，文字等于 `reason` 且可见（`59c5b8cfca` 原 helper 的定位器，另加可见断言）。
   - 两支之间不互相回退。
2. 新增 `expectReviewReasonShownOnce(page, reason)`（X 加入，Y 未动）：`.review-actions .review-actions__reason` 计数为 1、文字等于 `reason` 且可见；`.review-actions .disabled-reason` 计数为 0。对应用 kickoff §15.2 C12 第 3 条。
3. `journeys.spec.ts`（X 加入，Y 未动）：审核操作组的每个禁用状态各调用一次，共四处：`r7-reviewer-withdraw`、`r11-review-conflict`、`j1-archive-mainline`、`j2-manual-close`。原有 5 处 `expectDisabledWithReason` 调用保留；其余 9 处（上传、提交、撤回提交）不改。

`git diff --stat d12e3b8f70 26236839f7`（X..Y，只改 `ui.ts`）：

```
frontend/e2e-real/lib/ui.ts | 31 ++++++++++++++++++-------------
1 file changed, 18 insertions(+), 13 deletions(-)
```

X..Y 说明：把无条件要求 `aria-describedby` 非空的写法改为先分支。有 `aria-describedby` 时走 X 的实现并在末尾直接返回；没有时走兄弟元素分支。`expectReviewReasonShownOnce` 与 `journeys.spec.ts` 在 X..Y 中无改动。

## 3. X 的调试停止记录

X 的运行是调试，不是证据；其中通过的 scope 不代替 Y 的运行（kickoff §17.1）。依据 kickoff §17 处理。

| 项 | 05 | 07 |
| --- | --- | --- |
| worktree | `/home/dev/gdds-fe4a-fix4-d12e3b8f`（detached，HEAD 为 X，起止 clean） | 同左 |
| fetch ref | `refs/fe4a-fix4/d12e3b8f70` | 同左 |
| 日志目录 | `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/` | `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-07/` |

- X D1（07）：`run-tests.sh` 不带 `--e2e`，`GATEWAY_FE_TEST_WORKERS=2`，exit 0；类型检查、lint、单测 214 项、构建通过。
- X D2（05）：`--suite journeys --subphase fe3c` 完整集，20 个 scope 中 17 通过，3 失败，无 flaky；`openapi_compare=match`，`cleanup_status=ok`，起止 HEAD 为 X，起止 clean。§16 的 4 个目标 scope 全部通过。
- 3 个失败 scope（entry log 行 `test_status=failed`）：
  - `r4-submit`（`journeys.spec.ts:566`，失败在 `:590`，`workshopAction(session.page, "上传")`）；
  - `r7-withdraw`（`journeys.spec.ts:733`，失败在 `:746`，同上）；
  - `r7-approved`（`journeys.spec.ts:839`，失败在 `:861`，`workshopAction(session.page, "上传")`，原因 `该提交已通过审核，归档或关闭后才能重新上传`）。
- 失败断言均为 `ui.ts:137` 的 `aria-describedby references at least one element`，期望大于 0，实际为 0；其前面的 `toHaveAccessibleDescription(reason)` 已通过（描述来自 `title`）。失败产物（各含 `error-context.md`、`test-failed-1.png`、`trace.zip`）：
  - `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/artifacts/journeys-r4-submit/`
  - `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/artifacts/journeys-r7-withdraw/`
  - `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/artifacts/journeys-r7-approved/`

## 4. 自查

### 4.1 grep 命令与命中

在 `59c5b8cfca` 上运行：

```
git grep -n -e 'following-sibling' -e 'xpath=' -e 'disabled-reason' -e 'review-actions' -e 'aria-describedby' 59c5b8cfca -- frontend/e2e-real
```

命中：

```
59c5b8cfca:frontend/e2e-real/journeys.spec.ts:232:  await expect(page.locator(".review-actions")).toBeVisible();
59c5b8cfca:frontend/e2e-real/lib/ui.ts:125:  return page.locator(".review-actions").getByRole("button", { name, exact: true });
59c5b8cfca:frontend/e2e-real/lib/ui.ts:134:  await expect(button.locator('xpath=following-sibling::span[contains(@class, "disabled-reason")]')).toHaveText(reason);
59c5b8cfca:frontend/e2e-real/t1.spec.ts:399:      await expect(reviewerPage.locator(".review-actions")).toBeVisible({ timeout: 60_000 });
```

在 Y 上运行：

```
git grep -n -e 'following-sibling' -e 'xpath=' -e 'disabled-reason' -e 'review-actions' -e 'aria-describedby' 26236839f7 -- frontend/e2e-real
```

命中：

```
26236839f7:frontend/e2e-real/journeys.spec.ts:233:  await expect(page.locator(".review-actions")).toBeVisible();
26236839f7:frontend/e2e-real/lib/ui.ts:125:  return page.locator(".review-actions").getByRole("button", { name, exact: true });
26236839f7:frontend/e2e-real/lib/ui.ts:135:  const describedBy = await button.getAttribute("aria-describedby");
26236839f7:frontend/e2e-real/lib/ui.ts:146:        await expect(target, "aria-describedby target shows reason").toBeVisible();
26236839f7:frontend/e2e-real/lib/ui.ts:151:    expect(matched, `aria-describedby points to visible reason "${reason}"`).toBe(true);
26236839f7:frontend/e2e-real/lib/ui.ts:154:  const siblingReason = button.locator('xpath=following-sibling::span[contains(@class, "disabled-reason")]');
26236839f7:frontend/e2e-real/lib/ui.ts:160:  const group = page.locator(".review-actions .review-actions__reason");
26236839f7:frontend/e2e-real/lib/ui.ts:164:  await expect(page.locator(".review-actions .disabled-reason")).toHaveCount(0);
26236839f7:frontend/e2e-real/t1.spec.ts:399:      await expect(reviewerPage.locator(".review-actions")).toBeVisible({ timeout: 60_000 });
```

逐条结论：

- `journeys.spec.ts:233` 与 `t1.spec.ts:399` 的 `.review-actions` 容器可见断言：只检查容器存在，不依赖兄弟、父子关系与 `aria-describedby` 指向；C12 与 fix2 未删该容器，不受影响。
- `ui.ts:125` 的 `reviewAction` 定位器：按角色与名称定位，不依赖原因元素结构；不受影响。
- 其余命中都在 `expectDisabledWithReason` 与 `expectReviewReasonShownOnce` 内部，正是本次 helper 改动的定位器：`aria-describedby` 的读取与两支定位器分别对应 §17.1 表中的三类按钮；`:154` 的兄弟元素分支只在没有 `aria-describedby` 时执行，与有分支不互相回退；`.review-actions__reason` 与 `.review-actions .disabled-reason` 的计数对应 C12 第 3 条的共享原因检查，只在四处审核组调用中使用。

### 4.2 调用处结构表

Y 中 `expectDisabledWithReason` 的全部调用处（`journeys.spec.ts` 行号），逐项按产品代码核对（kickoff §17.1 的表，修订 7 补充）：

| 调用处 | 定位函数 | 产品代码位置 | `aria-describedby` | `title` | 原因元素 | 走 helper 哪一支 |
| --- | --- | --- | --- | --- | --- | --- |
| `:590`、`:746`、`:861` | `workshopAction` | `pages/WorkbenchPage.tsx:528-532` 原生按钮 | 无 | 有（即原因） | 后面的兄弟 `span.disabled-reason`，无 id | 没有分支 |
| `:595`、`:750`、`:866` | `stepUploadAction` | `UploadStepCard.tsx:333` 的 `Button` | 有，指向同一 `button-wrap` 内 `span.disabled-reason` | 无 | 同左，有 id | 有分支 |
| `:815`、`:870`、`:871` | `compareAction` | `pages/ComparisonPage.tsx:713-717` 的 `Button` | 有，指向同一 `button-wrap` 内 `span.disabled-reason` | 无 | 同左，有 id | 有分支 |
| `:959`、`:960`、`:1216`、`:1549`、`:1935` | `reviewAction` | `ReviewActions.tsx:164-171`（组原因为共享） | 有，指向 `.review-actions__reason` | 无 | 组下方一个 `span.review-actions__reason`，各按钮 `aria-describedby` 指向它 | 有分支 |

核对结论：只有上面三种结构，没有第四种；与 kickoff §17.1 一致。`expectReviewReasonShownOnce` 的四处调用（`:961`、`:1217`、`:1550`、`:1936`）都在审核组共享原因的页面上，与最后一行对应。

## 5. Y 的运行

| 项 | D1（07） | D2（05） |
| --- | --- | --- |
| worktree | `/home/dev/gdds-fe4a-fix4-26236839`（detached，HEAD 为 Y，起止 clean） | 同左 |
| fetch ref | `refs/fe4a-fix4/26236839f7` | 同左 |
| 日志目录 | `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/` | `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/` |
| 入口 | `run-tests.sh`，不带 `--e2e` | `run-real-backend-e2e.sh -- --suite journeys --subphase fe3c --session fe4a-impl --log-dir <05 日志目录> --evidence-dir <05 日志目录>/journeys-evidence` |
| 环境 | `GATEWAY_FE_TEST_WORKERS=2`，`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a`，默认缓存 | `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`，`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a` |
| 起止 UTC | wrapper `20261111T031548Z`–`20261111T031630Z`，入口 `2026-11-11T03:16:10Z`–`2026-11-11T03:16:30Z` | wrapper `20261111T031639Z`–`20261111T032433Z`，入口 `2026-11-11T03:16:39Z`–`2026-11-11T03:24:33Z` |
| 起止 HEAD | Y，起止 clean | Y，起止 clean |
| 两棵树 | `frontend/` 树 `d8e9a2e7`，`vnext/` 树 `49c1de43be`（起止一致） | 同左 |
| exit code | wrapper 0，入口 0 | wrapper 0，入口 0 |

### 5.1 D1 日志

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/fe4a-impl-run-tests-20261111T031548Z.log` | `0e66de6a5b2ad506a9c60b1060ee531cde3d59e741bab0d0d91838c9188afdad` |
| `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261111T031610Z.log` | `7d52a48df436beddf11ffd6acbf45f6e858adf93cb42ee81ead93f58da42f94e` |

类型检查（含 `e2e-real/`）、lint、单测 35 文件 214 项、构建通过。X 的 D1 日志（`fe4a-fix4-d12e3b8f-07` 目录下同名 `20261111T024702Z` wrapper 日志与 `frontend-tests-20261111T024725Z.log` 入口日志）同样 exit 0，见 §3。

### 5.2 D2 日志

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/fe4a-impl-run-real-backend-e2e-20261111T031639Z.log` | `913715c09b4f50e78ef0cc468ec444d098ea1313ade2dfa1385cd1519ee4b6c3` |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/entry-journeys-y.log` | `8ddc5e6d924a9c12affe24bbb157aca4c4140fa964131bf705ed1f3845c571dd` |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/results.json` | `72010b4fe505aba96df5cb978d7db680afa1f0df2871a035a183cebc229b38e7` |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/suite-summary.txt` | `add938b42985272ad626783faf8e77dd6556802efa979c70fd7cc5c80e89a2a7` |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/evidence/journey-cases.log` | `4bd721ef3789831ed0cd00ca417f569291c41a4b0bdba3f040c70124b5aee4bd` |

`entry-journeys-y.log` 是入口日志（原名带进程号后缀，内容相同，另见 §9 的命名说明）。20 个 scope 全部通过，无 flaky；`openapi_compare=match`；`cleanup_status=ok`；起止 HEAD 为 Y；起止 clean；结束时占用标记 absent。X 的 D2 日志（`fe4a-fix4-d12e3b8f-05` 目录下 `20261111T024803Z` wrapper 日志、`entry-journeys-x.log`、`results.json`、`suite-summary.txt`、`evidence/journey-cases.log`）记录 17 通过、3 失败，见 §3。

### 5.3 镜像与缓存身份

运行前在节点上用 `docker save` 加 `docker-save-image-identity.py` 现场核对，要求与 kickoff 一致。身份文件（内容为 config digest 与全部 RootFS DiffID）随本 handoff 的来源清单提供，`--evidence-file` 见 §9。镜像 tag 的 `lock-…` 后缀不写入正文，以身份文件路径代替。

- 07：工具链 `image-playwright-v1.64.1-noble.json`，config digest 与 7 个 DiffID 与要求一致；npm 归档与 `a2fb4a027a` 来源一致，`package_lock_resolved_count=305`，归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。
- 05：工具链同上；backend 依赖镜像身份文件 `identity-backend-deps.json`，config digest 与 19 个 DiffID 与证据预检一致；RS 依赖镜像身份文件 `identity-repository-deps.json`，config digest 与 16 个 DiffID 与证据预检一致；npm 缓存为 `fe0` 专用目录与归档，来源提交同上，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。

身份文件路径（05 在 05 日志目录下，07 在 07 日志目录下；`identity-*.json` 为回源安全名副本，内容与 `image-*.json` 相同）：

- `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/identity-backend-deps.json`
- `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/identity-repository-deps.json`
- `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/image-playwright-v1.64.1-noble.json`
- `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/image-playwright-v1.64.1-noble.json`

## 6. 落点

以下均取自 Y 的 D2。case log 指 `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/evidence/journey-cases.log`（行号即文件行号；提交号用 `…` 省略）。entry log 指 `entry-journeys-y.log`（安全名副本，内容与原入口日志相同）。

- J1 第 4 步以后（case log 第 21–29 行）：
  - 第 21 行 `j1-step4 ok baseline_to_initial.changed=0 initial_to_modified.changed=5`；
  - 第 22–23 行 `j1-step7` 异常 3 项后 `ok`；
  - 第 24 行 `j1-step10 ok … head=2`；
  - 第 25–26 行 `j1-step11` 异常 2 项后 `ok … head=3`；
  - 第 27–28 行 `j1-step13` 异常 3 项后 `ok … head=4`；
  - 第 29 行 `j1 ok three-node history compare browsed`。
- J2 第 8 步（case log 第 36–37 行）：第 36 行 `j2-step8` 异常 2 项，第 37 行 `j2-step8 ok … head=3`。
- 每次预检的异常集合（case log `anomalies=[…]` 行，提交号省略后逐项与 FE3 kickoff §4.6 的表对照）：
  - 第 19 行 `j1-step2` 1 项 `GENERATION_TIME_MISSING`（`MODIFIED`），与表 J1 第 2 步一致；
  - 第 22 行 `j1-step7` 3 项（`INITIAL`、`MODIFIED`、`BASELINE_TIME_UNAVAILABLE`），与表第 7 步一致；
  - 第 25 行 `j1-step11` 2 项，与表第 11 步一致；
  - 第 27 行 `j1-step13` 3 项（含 `PROJECT_IDENTITY_EXCEPTION`），与表第 13 步一致；
  - 第 30 行 `j2-step1` 1 项，与表 J2 第 1 步（同 J1 第 2 步）一致；
  - 第 32 行 `j2-step3` 8 项（`APPROVED_SIBLING_EXCLUDED` 2 项、`BASELINE_TIME_UNAVAILABLE` 1 项、`GENERATION_TIME_MISSING` 5 项），与表第 3 步一致；
  - 第 34 行 `j2-step5` 7 项（含 `INITIAL_SOURCE_UNEXPLAINED`），与表第 5 步一致；
  - 第 36 行 `j2-step8` 2 项，与表第 8 步一致。
- `r7-reviewer-withdraw` 中提交人一侧的核对与两侧 `assertClean`：case log 第 12 行 `r7-reviewer-withdraw ok`；指针清除、树状态“已撤回”、重新上传与两侧 `assertClean` 均为用例内断言，通过即成立。证据截图 `r7-reviewer-withdraw-r7-reviewer-withdraw.png` 在 `evidence/` 下。
- `r11-review-conflict` 的证据截图与两侧 `assertClean`：case log 第 17 行 `r11-review-conflict ok … requests=1`；证据截图 `r11-review-conflict-r11-review-conflict.png` 在 `evidence/` 下；两侧 `assertClean` 为用例内断言。
- fix2 的三处应用代码改动各由以下 scope、步骤经过：
  - 归档对话框重读后改用重读结果（C8）：J1 第 3/7/9/10/11 步的接受、撤销、再接受与重新预检（case log 第 20–28 行），J2 第 4 步关闭后自动重新预检与第 5 步（第 33–34 行）；
  - 审核操作错误提示移出按钮行（C12 第 1 条）：`r11-review-conflict` 的版本冲突提示与刷新流程（entry log `test_title=r11-review-conflict` 通过行，`suite-summary.txt` 同）；
  - 处置说明独占一行（C12 第 2 条）：J2 归档时关闭行的顶栏处置（`j2-review-disposition-closed-at-archive` 截图在 `evidence/` 下，用例内 `.review-disposition-line` 断言通过）。
- X 上失败的 `r4-submit`、`r7-withdraw`、`r7-approved` 中工具栏按钮断言之后的步骤：Y 中三者全部通过，case log 第 5 行 `r4-submit ok`、第 8 行 `r7-withdraw ok`、第 10 行 `r7-approved ok`；其后的选择树、展开详情、B1 `stepUploadAction` 同原因断言与 `compareAction` 断言（§4.2 表 `:595`、`:750`、`:866`、`:870`、`:871` 处）均在 Y 中执行通过。

## 7. 耗时

取自日志，只报告：Y D2 入口起止 `2026-11-11T03:16:39Z`–`2026-11-11T03:24:33Z`（含镜像构建与 20 个 scope）；`j1-archive-mainline` 约 75 秒（`2026-11-11T03:21:59.535Z`–`2026-11-11T03:23:14.904Z`）；`j2-manual-close` 约 73 秒（`2026-11-11T03:23:14.912Z`–`2026-11-11T03:24:28.194Z`）。Y D1 入口约 20 秒。

## 8. 其他

- DC68 事件：无。D1、D2 均为第一次运行即通过；运行前核对一次通过，无缓存缺失、无占用冲突、无需联网。
- 偏离：无。修改、传输、运行均按 kickoff §17 执行；未改 §1 范围以外的路径。
- 未决事项：交审核会话做复审第 4 轮（kickoff §16.4、§17.4）：helper 区分力探针（含工具栏原生按钮三情形）、07 模拟接口全量与 `full1` 的 `--stable` 比较、05 调试日志核对、§11.2 第 10 项、本回源。

## 9. 回源结果

在 07 上对本文件运行 `frontend/scripts/check-handoff-hex.py`（`--git-objects --repo` 07 主仓库，`--sha-file` 两份来源清单与两份 npm 归档清单，`--evidence-file` 三份镜像身份文件），需要 exit 0。来源清单为机器生成的 `sha256sum` 绝对路径清单，附 `.sha256` 旁注；05 的清单与证据传到 07 后先用旁注核对一致再使用。

命名说明：入口日志原名带进程号后缀（7 位数字，回源会误判为 git 对象），故以同内容安全名副本（`entry-journeys-x.log`、`entry-journeys-y.log`）供配对，原文件保留；镜像身份文件同样以安全名副本（`identity-*.json`）供配对。

结果：exit 0；`summary: 23 distinct full token(s); git=15 sha256=8 allowed=0 abnormal=0; 0 truncated form(s)`；未命中值无；长度异常值无。短号（`26236839`、`d12e3b8f` 等）按 git 对象核对通过；64 位值全部在来源清单或证据文件中有来源；配对全部通过（含 07 本机文件的现场配对与 05 文件的清单配对）。

回源日志：`/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/hex-handoff.log`，另写 `.sha256` 旁注。

回源日志自身的哈希不写入本文件，只写回源日志路径（kickoff §16.7 二选一中的后者）。

