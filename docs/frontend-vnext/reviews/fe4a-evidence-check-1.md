# FE4a 证据核对第 1 轮（停止核对）

**结论：证据未通过，停止，交设计会话。** 实施会话的停止判断正确。04-c 的 4 个失败 scope 不是后端缺陷，也不是取证错误：候选的真实旅程 helper 没有随 C12 第 3 条更新。真实 backend 上的页面行为符合 C12。修复需要一个新候选（只改 `frontend/e2e-real/`），由设计会话决定新候选的调试与证据范围（§6）。另外三项（04-a、04-b、05-t1）在被测提交上都通过。

- **审核会话：** `fe4a-rereview3`（同一会话）。
- **核对时间：** 2026-11-11 02:00–02:22 UTC。
- **方式：** 开发主机只读核对 git 对象；04、05 上只读核对日志与产物，没有运行测试，也没有取占用标记。核对时两节点均无占用标记。

## 1. 被测对象

| 项 | 值 |
| --- | --- |
| 被测提交 | `59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`（开发主机 `fe-vnext` 已快进至此，没有新提交） |
| `frontend/` 树 | `802bdfb1a42b5319b483f3c4324d2b609a1b57b0` |
| `vnext/` 树 | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 两节点 worktree | `/home/dev/gdds-fe4a-evidence-59c5b8cf`，HEAD 为被测提交，`git status --porcelain` 为空 |
| 证据 handoff | 未写（实施会话按停止规则不写），回源未跑 |

## 2. 通过的三项

| # | 节点 | 结果（取自日志原文） | 日志 | SHA256（节点现场计算，与 `.sha256` 旁注一致） |
| --- | --- | --- | --- | --- |
| 04-a | 04 `gw-dms-test-04.lan` | 起止 `frontend/` 树 `802bdfb1`、clean；单测 35 文件 214 项通过；`Running 96 tests using 2 workers`，96 passed；`exit_code=0` | `/home/dev/gdds-fe-logs/fe4a-evidence-04/fe4a-evidence-04-run-tests-20261111T013929Z.log` | `e0b4828f7ddc6f582c50694bb28cc82779067110f1e113600c4403ea9bbe49ca` |
| 04-b | 04 | `dependency_image=gateway-backend-deps:lock-578e079b762e`；config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`、19 个 DiffID，与预检一致；`RESULT packages=4 failures=0`；`entry_exit=0`；起止 clean | `/home/dev/gdds-fe-logs/fe4a-evidence-04/fe4a-evidence-04-validate-upload-package-20261111T014800Z.log` | `df6bf5d5af5720842f80de35b752295f2eeb19c43f51cf0a1579f48d9492ce95` |
| 05-t1 | 05 `gw-dms-test-05` | 1/1 通过；`openapi_compare=match`；`suite_exit=0`；`cleanup_status=ok`；`busy_end=absent`；起止 clean | `/home/dev/gdds-fe-logs/fe4a-evidence-05/fe4a-evidence-05-run-real-backend-e2e-20261111T014213Z.log` | `2653f29e2eb0bd33f8b5f21432ac41c016cb58a5e3d6eb4c5fe6e468c6c42e83` |
| 05-t1 入口 | 05 | 同上 | `/home/dev/gdds-fe-logs/fe4a-evidence-05/real-backend-e2e-t1-fe4a-evidence-05-59c5b8cfc-20261111T014213Z-3562717.log` | `4faf52988ec98bba595f1fcbe0ab3478c9496df16447acd5f509dd486398d7d5` |

- **04-a 截图：**
  - `/home/dev/gdds-fe-evidence-04/fe4a-59c5b8cf/shots` 下有 198 个 PNG；
  - `shots.sha256` 的 SHA256 为 `5fe0e95413aba58d0a7223986608e2404353020ec53529ccafcce2084419a0a9`，`sha256 -c` 全部通过。
- **05-t1 参考截图：**
  - 14 张 `fe4-t1-*` 齐全（7 个名字 × 1280、1920）；
  - 位于 `/home/dev/gdds-fe-logs/fe4a-evidence-05/evidence/` 与 Playwright 附件目录，不在 `--evidence-dir`（该目录只有 `test-results`）。这是入口的既有行为，记录，不判为问题。
- **04-b 的 wrapper 日志：** 有一行 `wrapper_field_missing exit_code reason=entry did not log exit_code`。入口记录的是 `entry_exit=0`，不影响结论，记录备查。
- **未核对：** 05-t1 的 §8.3 逐条核对与 M1 增量（20.38 MiB）。这两项留到证据 handoff 时一并核对。

## 3. 04-c 失败

### 3.1 事实

- **运行与日志：**
  - 外层日志 `/home/dev/gdds-fe-logs/fe4a-evidence-04/fe4a-evidence-04-run-real-backend-e2e-20261111T015023Z.log`，SHA256 `ebcc1be7c9fd3c7e955eb52dffd656d7bcb281f8f7fa7b072949929bc1b91909`；
  - 入口日志 `real-backend-e2e-journeys-fe4a-evidence-04-59c5b8cf-20261111T015023Z-3097538.log`，SHA256 `6ba65c8fc46493b4ca18a4e91f560bd073f88d96cf149490f6ac6453572901e8`；
  - `openapi_compare=match`，`suite_exit=1`，`cleanup_status=ok`，`busy_end=absent`，起止 clean。
- **结果：** `suite-summary.txt` 记录 20 个 scope 中 16 个通过，失败 4 个，没有 flaky：

  | scope | 失败位置 | 断言 | 期望原因 |
  | --- | --- | --- | --- |
  | `r7-reviewer-withdraw` | `journeys.spec.ts:958` | `expectDisabledWithReason(reviewAction(…, "撤回"), …)` | 该提交已撤回 |
  | `r11-review-conflict` | `journeys.spec.ts:1214` | `expectDisabledWithReason(reviewAction(…, "审核通过"), …)` | 该提交已撤回 |
  | `j1-archive-mainline` | `journeys.spec.ts:1546` | `expectDisabledWithReason(reviewAction(…, "审核通过"), …)` | 该提交已归档 |
  | `j2-manual-close` | `journeys.spec.ts:1931` | `expectDisabledWithReason(reviewAction(…, "审核通过"), …)` | 该提交已关闭（未归档） |

- **失败形态：** 四处相同，都是 `e2e-real/lib/ui.ts:134` 的定位器 `xpath=following-sibling::span[contains(@class, "disabled-reason")]` 找不到元素（`element(s) not found`）。
- **页面状态：** 四个 `error-context.md` 的页面快照都显示三个按钮 `[disabled]`，按钮组下方只有一行与期望完全相同的原因文字。真实 backend 上的行为符合 kickoff §15.2 C12 第 3 条。
- **`journeys.spec.ts` 中的其他调用：** `expectDisabledWithReason` 另有 9 处，对象是上传、提交、撤回提交等非审核按钮，所在 scope 都通过。

### 3.2 根因

- **C12 第 3 条的实现：** fix2 `d9fc3b3d56`（2026-11-10 14:49 UTC）实现了第 3 条。
  - 审核操作组的原因相同时，各按钮 `disabledReason={undefined}`；
  - 原因渲染一次，放在 `.review-actions__buttons` 之后的 `span.review-actions__reason`；
  - 各按钮的 `aria-describedby` 指向它。
- **未同步的 helper：** 该提交没有改 `frontend/e2e-real/`。`expectDisabledWithReason` 仍要求原因是按钮的下一个兄弟元素 `span.disabled-reason`，审核操作组中这个元素已不存在。
- **为什么只有这 4 个 scope 失败：** 只有审核操作组的断言依赖这个结构，`compareAction` 与 `workshopAction` 的调用都通过。
- **最后一次真实旅程调试运行：** 05 上的 J1/J2，提交 `501fd7469c`，早于 fix2，所以当时通过。
- **其他 class 定位器：** 我把 `e2e-real/` 中所有按 class 定位的 26 个选择器，与 `fe-fe3c-exit` 及被测提交的 `frontend/src` 逐一对照，没有被删除的 class。

### 3.3 归类

- **DC68：** 失败发生在被测对象已经运行之后，不在 DC68 的“修正后重做一次”范围内。实施会话没有重做，处理正确。
- **不是后端缺陷：** OpenAPI 一致，后端返回的状态与页面渲染都正确。
- **候选内部的测试缺陷：** 产品代码按 C12 实现，真实旅程 helper 没有同步。修复只能改候选的 `frontend/e2e-real/`，因此需要新候选。按 kickoff §8，这交设计会话决定。

## 4. 遗漏

- **设计依据与转达：**
  - kickoff §15.4 写明“C12 只改模拟接口可覆盖的顶栏，不改 `journeys.spec.ts` 与 `t1.spec.ts`，不增加真实旅程或 t1 调试运行”。
  - 复审第 1 轮（`e903158bdb`）的 F11 照此转达。
  - 复审第 2、3 轮在 diff 范围表中把“`e2e-real/` 无改动”当作正面事实记录。
- **都没有检查的一点：** 第 3 条改变了按钮与原因的 DOM 关系，而 `e2e-real/lib/ui.ts` 正依赖这个关系。
- **审核报告的说法不准确：** 审核报告 §1 说“真实旅程按角色和文字定位”，对这个 helper 不成立。
- **本会话的责任：** 本会话负责复审第 2、3 轮。正确的做法是在 C12 改动后，用 `grep -rn "disabled-reason" frontend/e2e-real` 核对一次。今后审核涉及 DOM 结构的修改时，同时检查 `e2e-real/` 中的定位器，并把这一项写进 FE4b 审核清单。

## 5. 证据运行没有覆盖的部分

失败的断言让各 scope 提前结束。在被测提交上，下列内容没有在真实 backend 上执行过：

| scope | 未执行的部分 |
| --- | --- |
| `j1-archive-mainline` | 第 4 步起的全部步骤（`journeys.spec.ts:1550–1720`），包括其后各次预检的异常集合核对 |
| `j2-manual-close` | 第 8 步（C 在基线 2 上重新上传、接受、归档为基线 3）及其异常集合核对 |
| `r7-reviewer-withdraw` | 提交人一侧的核对：指针清除、树状态“已撤回”、可以重新上传；两侧 `assertClean` |
| `r11-review-conflict` | 证据截图与两侧 `assertClean` |

fix2 改动的应用代码自 `501fd7469c` 起也没有在真实 backend 上运行过：

- `ArchiveMainlineDialog.tsx`：重读计划后改用重读结果（C8）；
- `ReviewActions.tsx`：错误提示移到 `.compare-header__notice`；
- `ComparisonPage.tsx`：处置说明独占一行。

J1、J2 的后续步骤会经过归档对话框的重读路径。

## 6. 建议（交设计会话决定）

1. **修复（fix4，只改测试代码）：**
   - 把 `e2e-real/lib/ui.ts` 的 `expectDisabledWithReason` 改为断言 `toBeDisabled()` 与 `toHaveAccessibleDescription(reason)`；
   - 这对两种结构都成立：`Button` 自带原因时 `aria-describedby` 指向 `span.disabled-reason`（`design-system/components.tsx:15-24`），共享原因时指向 `.review-actions__reason`；
   - 审核操作组的调用处另加一条断言：组内原因只显示一次（`.review-actions__reason` 计数为 1，且没有 `.review-actions .disabled-reason`），对应 C12 第 3 条；
   - 不改 `frontend/src/`、`t1.spec.ts` 与入口。
2. **调试（需要 owner 或设计会话授权）：**
   - kickoff §7.2 与 §8 只允许 J1、J2 的真实旅程调试；
   - 建议授权在 05 上用一次完整集或这 4 个 scope 调试，原因有两个：失败的 4 个 scope 中有 2 个不属于 J1/J2；§5 列出的未执行部分需要先在调试中跑通，再进证据；
   - 不授权时，在 05 上只跑 J1/J2，r7、r11 留到证据运行中验证，风险是证据再次失败。
3. **审核：** 定向复审 fix4。内容包括：helper 改动的区分力探针（把 C12 第 3 条回退为各按钮各自显示原因时，“只显示一次”的断言失败，原因断言仍通过；删掉共享原因时原因断言失败）、07 上模拟接口全量一次（fix4 不改模拟接口用例，截图应与本轮 04-a 相同），以及核对 05 调试日志。
4. **证据：** 新候选的 `frontend/` 树会变。kickoff §7.2 写明前端没有沿用机制，因此建议在新候选上把四项各重跑一次，合计约 30 分钟，不为 04-b、05-t1 开沿用例外。05-t1 在新候选上再跑一次属于证据，不是第二次 t1 调试，但 kickoff 没有明说，请设计会话一并写明。第 ③ 次稳定性比较在新证据之后做。
5. **证据 handoff 中的哈希：**
   - 实施会话这次回复中，7 个 SHA256 有 2 个抄错：04-a 日志少了两个字符；05-t1 外层日志只有 58 个字符，且有多处错误。第 2 节表中是节点现场计算的值；
   - 新证据的 handoff 应按复审第 3 轮 N20 的要求，用机器生成的清单与回源脚本核对，不手抄哈希。

## 7. 保留

本轮全部产物原样保留，直到 FE4a 退出：

- 两节点的 `/home/dev/gdds-fe4a-evidence-59c5b8cf` worktree 与 `refs/fe4a-evidence/59c5b8cfca`；
- `/home/dev/gdds-fe-logs/fe4a-evidence-0{4,5}/`（含 4 个失败 scope 的 trace 与截图）；
- `/home/dev/gdds-fe-evidence-0{4,5}/fe4a-59c5b8cf/`；
- 开发主机 `fe-vnext` 的快进。

本核对没有删改任何会话的产物，没有推送，也没有改 `fe-vnext`。
