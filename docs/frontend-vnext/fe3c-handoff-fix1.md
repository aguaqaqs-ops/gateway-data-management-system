# FE3c handoff fix1（第 1 轮定向修复）

本文件是 `docs/frontend-vnext/fe3c-handoff.md`（提交 `1df3dc05e23e147b30afe822414b9cf3aa089313`）的补丁说明，原 handoff 不改。审核报告为 `docs/frontend-vnext/reviews/fe3c-review.md`（本地 main `ccd7b80fa2`，未推送）。

- 起点 handoff：`1df3dc05e2`
- 原代码候选：`09351e42ad`（frontend tree `6158d776`）
- 本轮修复候选：`cbb14f578cd22f37355db78a62ba9264f71477d3`
- 修复候选 frontend tree：`f626a8f0b3ab4ebd2a3e1d7a3eb15e1803c48908`
- 修复候选 vnext tree：`6368c9c40cf08a97eecf2a0c457a6c16ce448080`（与 `09351e42ad` 相同，本轮未改 `vnext/`）
- 未合入 main、未 rebase、未推送。

提交序列（`1df3dc05e2..cbb14f57`）：

| 提交 | 内容 |
| --- | --- |
| `f34f98df10` | B1–B7 主体：view-model 抽取、dialog 文案/流程、e2e 与真实旅程断言、t1 清单核对、N1 |
| `76603a77c7` | 对齐 V1/V2/V4/V8/V9 的模拟实现与恒等键断言 |
| `9aadd8622e` | J2 接受 BTU 后重新展开“基线时间”组 |
| `396a983624` | 断言 dialog 发出的撤销 action 为 `REVOKE` |
| `4905ebe916` | 卡片截图先滚动再截 |
| `741ad4bfba` | 总览截图前把对话框正文滚回顶部 |
| `cbb14f578c` | 归档确认人会话从建立起统计 `GET .../review` |

## 1. B1：J2 第 4 步（真实 backend 关闭中断与重试）

用例位置：`frontend/e2e-real/journeys.spec.ts`，`j2-manual-close` 第 4 步（约 :1760）与第 5 步（约 :1833）。

改动：

1. 关闭前先在界面展开“基线时间”，接受 `BASELINE_TIME_UNAVAILABLE`（理由“j2 接受基线时间缺失”），断言该卡显示“已接受”；不再跳过该项直接关闭。
2. 关闭 C 时用 `page.route("**/v1/submissions/*/closure")` 拦截：每次请求先 `route.fetch()` 真正送到 backend，读取响应状态与响应体；第一次把响应交给浏览器前 `route.abort("failed")` 模拟浏览器中断，第二次用同一 key 重发，`route.fulfill` 把 backend 的 200 回放给浏览器。
3. 断言：
   - 两次请求的 `Idempotency-Key` 相同，body 逐字节相同；
   - 状态码序列 `[201, 200]`，即首次创建、重试回放；
   - body 的 `expected_review_version` 等于同次候选读取的 `review_version`，理由等于输入；
   - 响应体 `closed_by` 等于归档确认人的 `actor_id`；结果区 `[aria-label="关闭结果"]` 显示“关闭人/关闭时间/理由”，关闭时间按响应体 UTC 格式化；
   - 归档确认人会话从 `openSession` 起监听并断言 `GET /v1/submissions/{id}/review` 次数为 0；
   - 关闭结果区改用 `aria-label="关闭结果"` 定位，不再用会被静态影响说明文字命中的 `getByText("已关闭")`。
4. 第 5 步重新读取候选并预检（`digestBAfterClose`），断言仍为 7 项、全部 `UNRESOLVED`、`candidate_set_digest` 与第 3 步不同，且原先接受的 BTU `subject_digest` 不再出现。

实测（05 r4，`cbb14f57`）：

```text
j2-step4 ok closed=sub-194d281a-7a7b-44a0-90a5-e70f819b6314 review_version=1 key=3725b3ed-2edf-46bc-b51b-9b77f634b666 statuses=201,200
```

即两次请求 key 相同（`3725b3ed-2edf-46bc-b51b-9b77f634b666`），首次 201、重试 200；`closed_by` 为归档确认人 actor。

## 2. B2：§4.6 两组集合逐次实测校正

用例位置：`frontend/e2e-real/journeys.spec.ts`。

- `businessIssueSet`（约 :1297）从 `business_validation.issues` 去掉 `APPROVED_SIBLING_EXCLUDED` 与 `PROJECT_IDENTITY_EXCEPTION`，格式为 `subject_kind|issue_code|side|受影响提交(排序,join)`。
- `expectAnomalySets`（约 :1304）同时比较 `anomalies` 与上述 business 集，两个集合都写入 case log；不一致即抛“stop for design review”，不放宽。
- 覆盖范围：J1 第 2/7/11/13 步，J2 第 1/3/5/8 步。
- J1 第 7 步新增 B 的来源断言：`detected_status === "EXPLAINED"` 且 `matching_sources` 含 `BASELINE`。

修复后逐次集合（05 r4 `evidence/journey-cases.log`，`cbb14f57`；`anomalies` / `business_issues`）：

J1 第 2 步（两者相同）：

```text
["CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-5943453e-a37e-4ad0-9697-4bf03271645b"]
```

J1 第 7 步（两者相同）：

```text
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-3cc42906-daf8-448b-8fad-482bd67d1a0c",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-3cc42906-daf8-448b-8fad-482bd67d1a0c",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-3cc42906-daf8-448b-8fad-482bd67d1a0c"]
```

J1 第 7 步来源诊断：B `EXPLAINED`，`matching_sources` 含 `BASELINE`。

J1 第 11 步（两者相同）：

```text
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-9cda0bd0-ba3d-47e0-ba35-d18dd314839c",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-9cda0bd0-ba3d-47e0-ba35-d18dd314839c"]
```

J1 第 13 步：

```text
anomalies:
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-443bca92-1b98-4506-a863-17aef0a81c1d",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-443bca92-1b98-4506-a863-17aef0a81c1d",
 "PROJECT_IDENTITY_EXCEPTION|PROJECT_IDENTITY_EXCEPTION|-|sub-443bca92-1b98-4506-a863-17aef0a81c1d"]
business_issues:
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-443bca92-1b98-4506-a863-17aef0a81c1d",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-443bca92-1b98-4506-a863-17aef0a81c1d"]
```

J2 第 1 步（两者相同）：

```text
["CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-d721ae10-1798-4329-bc9c-965e040d2a62"]
```

J2 第 3 步：

```text
anomalies:
["APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|sub-194d281a-7a7b-44a0-90a5-e70f819b6314",
 "APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-0bd528e1-0594-4248-b7db-420dad596a05,sub-194d281a-7a7b-44a0-90a5-e70f819b6314,sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-194d281a-7a7b-44a0-90a5-e70f819b6314",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-332c6070-c1aa-485b-b7dc-d84b92c96942"]
business_issues:
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-0bd528e1-0594-4248-b7db-420dad596a05,sub-194d281a-7a7b-44a0-90a5-e70f819b6314,sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-194d281a-7a7b-44a0-90a5-e70f819b6314",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-332c6070-c1aa-485b-b7dc-d84b92c96942"]
```

J2 第 5 步：

```text
anomalies:
["APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_SOURCE|INITIAL_SOURCE_UNEXPLAINED|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-0bd528e1-0594-4248-b7db-420dad596a05,sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-332c6070-c1aa-485b-b7dc-d84b92c96942"]
business_issues:
["CONFIGURATION_SOURCE|INITIAL_SOURCE_UNEXPLAINED|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-0bd528e1-0594-4248-b7db-420dad596a05,sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|sub-332c6070-c1aa-485b-b7dc-d84b92c96942",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-0bd528e1-0594-4248-b7db-420dad596a05",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-332c6070-c1aa-485b-b7dc-d84b92c96942"]
```

J2 第 8 步（两者相同）：

```text
["CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|sub-ed1863bf-d52a-4abb-b578-a52000d9f19d",
 "CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|sub-ed1863bf-d52a-4abb-b578-a52000d9f19d"]
```

## 3. B3：文案与错误显示

实现位置：`frontend/src/features/view-model/archive-dialog.ts`（新文件），`frontend/src/features/workbench/ArchiveMainlineDialog.tsx` 只负责渲染。

| 审核意见 | 修复 |
| --- | --- |
| 阻断项只显示原始码（`ArchiveMainlineDialog.tsx:574`） | `blockerCopy` 按 §16.5：`ACTIVE_SUBMIT_ATTEMPT` → “已有提交正在处理，完成后才能归档”；`ARCHIVE_INTEGRITY_FAILURE` → “归档数据完整性校验未通过，不能继续，请联系管理员”；其他 → “当前不能归档”。原始码只在“错误代码：<code title=…>”区。V7 断言中文文案。 |
| 禁用原因顺序（`:439-448`） | `startDisabledReason` 顺序改为：预检中 → 预检失败 → 阻断 → 未知编码 → 未处理/已撤销 → 未勾选 → 归档中。文字“还有 {n} 项异常未处理”。 |
| BTU 问题文字（`:36`） | “当前基线没有可用的生成时间，本轮无法比较时间先后”。 |
| BTU 详情不带计数 | `NO_VALUE` → “saved_time 全部为空（{empty_count} 行）”；`NO_VALID_VALUE` → “saved_time 没有可识别的时间（{invalid_count} 个无法识别）”；基线为空时“基线没有生成时间记录”；随后“比较结果：无法比较”。 |
| 关闭 404 显示服务器 message | `closeError` 对 404/`RESOURCE_NOT_FOUND` 显示“未找到该提交，请重新预检”。 |
| 关闭/接受/撤销 413、429、503 及其他码显示服务器 message | `closeError`/`resolutionError` 对这些码显示“关闭未完成”/“操作未完成”+错误码，不取服务器 message。 |
| retryClose 的 `ARCHIVE_CLOSED` 文案 | 统一显示“该提交已归档或关闭”。 |
| V7 只断言原始码 | V7 改为断言两条中文文案，并把原始码限定在 `.archive-blockers code` 内。 |

## 4. B4：候选读取与预检“一次加载”

`ArchiveMainlineDialog.tsx` 的 `load()`（约 :99-140）现在：

1. 读取候选、构造 selected、预检；
2. 若两次 `candidate_set_digest` 不同，标记阶段为 candidates，重新读取候选列表、找到目标并用**新候选**重建 selected，再预检一次；
3. 仍不同才设置“归档候选集合已变化，请重新预检。”，不再拿旧 selected 反复预检。

新增模拟用例：`frontend/e2e/archive-validation.spec.ts` “B4 候选读取与预检不一致时重读候选与预检一次”（约 :682）。断言候选请求 2 次、预检 2 次、第二次预检 body 的 `selected.expected_candidate_digest` 为 `sha256:v-candidate-v-s1-refreshed`，且无加载错误。

## 5. B5：用例区分力与单测

### 5.1 view-model 与单测

- 新增 `frontend/src/features/view-model/archive-dialog.ts`：问题文字与详情、`SIDE_COPY`、`RELATION_COPY`、状态标签与色调、`anomalyAction`、`formatReasonLimitError`（UTF-8 字节）、`startDisabledReason`、阻断文案、三类错误文案、`formatServerTimeUtc`。
- 新增 `frontend/src/features/view-model/archive-dialog.test.ts`（16 项）：文案映射、BTU 计数详情、ACCEPTED 中性色 / 其他警示色、action 映射、1365×“多”+“x”=4096 可用与 4097 禁用、禁用原因顺序、阻断与错误文案。
- `frontend/src/features/api/journeys.test.ts` 的引用测试改名为“covers every accepted anomaly and skips unresolved items”，数据含非 ACCEPTED 项，断言只生成 ACCEPTED 的引用。

### 5.2 模拟用例

`frontend/e2e/archive-validation.spec.ts`：

| 审核意见 | 修复与断言 |
| --- | --- |
| V3 只查文字 | 断言处理标签含 `status-tag--neutral` 且不含 `success`（`:363`）。 |
| V4 无 REVOKED、禁用断言平凡 | 新 fixtures `vPreviewAcceptedSourceRevoked`；撤销后断言“已撤销接受，需要重新处理”“已撤销，原因：需要重新核对来源”；先勾选“确认把…”再断言禁用，并断言“还有 2 项异常未处理”（`:378`）。 |
| V9 无“无 GET review”、无 200 回放、无 404/422、无重开取新版本、无 4096/4097 多字节 | 拆成五个用例（`:509`、`:547`、`:575`、`:596`、`:613`）：① 首次中断、同 key 重试、`[200]`、结果区显示首次关闭人（`reviewer`，与当前 `archive-confirmer` 不同）、全程 `reviewGets=0`；② `REVIEW_VERSION_CONFLICT` 后重新打开，取新候选 `review_version=22` 再关闭；③ 404/422 文案与码；④ 403 与 413 文案；⑤ `"多".repeat(1365)+"x"`=4096 可用、“已输入 4096 字节”，再加一个 `x` 为 4097 禁用并显示字节上限。 |
| V2 无各自撤销、无 ② 接受请求、无卡内定位 | 五次预检覆盖未处理→①已接受→两侧已接受→①撤销→两侧撤销；两卡各自接受/撤销；“已接受”限定在 ①/② 卡内；resolution body 断言四条（含两条 `REVOKE`）。 |
| V1 无 §16.3 详情文字 | 增加 BTU 完整文字、基线无生成时间记录、`GENERATION_TIME_INVALID_VALUES` 计数。 |
| V8 未触发 409、未断言树选中 | 第二次预检 `vPreviewPendingStartable` + `startConflict=ARCHIVE_PENDING_REVIEW`，勾选后点“确认归档”触发 409，断言“出现了新的待审核提交，请重新预检”与码；点“提交 2”后断言 `table[aria-label="History 组态树"] tr.is-selected` 含该名字；无 `/v1/archives` 成功请求。 |
| V13 无 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` | 追加用例（`:670`），断言“候选提交超过归档上限，需要管理员处理”+码。 |
| §16.8 可达性单测 | `archive-validation-data.test.ts` 增加：ACCEPTED 三字段非空；REVOKED 的 `accepted_by`/`accepted_at` 为 null、理由非空、`latest_sequence≥2`；MODIFIED_ONLY 只有 ② 侧；`≤8N+1`。 |

## 6. B6：t1 输入清单与 case log

`frontend/scripts/run-real-backend-e2e.sh` 的 t1 分支（约 :946-966）：

- 启动 Compose 前，对 `t1-v1`/`t1-v2` 断言 `$INPUT_ROOT/SHA256SUMS-<dir>.txt` 存在且 SHA256 等于期望值，不符合以 exit 2 停止；
- 在各版本目录内执行 `sha256sum -c -- "$manifest"`，逐文件核对；
- 日志记录清单文件的实际 SHA256 与核对文件数。

实测（05 t1，`cbb14f57`）：

```text
t1_manifest=t1-v1 path=/home/dev/gateway-real-dumps/source-dirs/SHA256SUMS-t1-v1.txt sha256=cdb598cdd30198ee94e56469c0c289be1ad1e1e8524e5da13b9d00249eed0163
t1_manifest_verified=t1-v1 files=19
t1_manifest=t1-v2 path=/home/dev/gateway-real-dumps/source-dirs/SHA256SUMS-t1-v2.txt sha256=fa2450fac17f5011fee31eb0b163a7355846932c973dedf86bfe10532c32a96a
t1_manifest_verified=t1-v2 files=19
```

与 FE3a handoff §4.1 一致。

`frontend/e2e-real/t1.spec.ts`：

- `:350` 记录 `baseline_to_initial.table_count`；实测 `125`；
- `:357` 起 `compositeChanged` 取不到 `composite_signal_point` 时直接失败（`expect(...).not.toBeNull()`），不再按 0；实测 `composite_changed=0`，`initial_to_modified.changed_count` 按 `v2Changed + composite` 断言。

## 7. B7：截图

模拟用例（07 r9，`cbb14f57`，宽度 1280/1920 各一张；`fe3c-time-regression-card` 同屏含 ①/② 两张时间倒退卡）：

| 名称 | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- |
| `fe3c-time-regression-card` | `7e58cbed90e825d4157520f8e4c0a97f6c53d42144f423d9318abb565aaa605e` | `b274b005299204b68eea5674e04afa713817596d7edab584da3ced58f5078883` |
| `fe3c-last-not-max-card` | `346ffa752d700389759f097c5679cb5e59b5bcc1d69fb3ec674342f36a63e558` | `efd248e6b95465eb237d1b74c4dda2007516994eb1edf5da94e8a41b72944c94` |
| `fe3c-confirm-disabled-loading` | `e12d0da50a1af9c63542c9179996c313c3e9a0f4e4da10916abca17118997676` | `f57b3d660ad30be7d4dd354b699d720e52918a4a4171d31011bb13fc062e042f` |
| `fe3c-confirm-disabled-blocked` | `a1faa79ef1186d4ccc3a6d43385d09c62e02798a52d276e0476ebb605b925782` | `dd270cb83e29a9f7ce87971f7aa3ad3c18999499e9a23d28b7abf03a4f1ab601` |
| `fe3c-confirm-disabled-unprocessed` | `66f922e3b40dd37d861645776826925a2db44ad1146f9dce26be4c81af9b90bb` | `ff2ac8576056ba5f0ab702c4446b2388d03bc7c4059eb23bec72662a8a515133` |
| `fe3c-confirm-disabled-unknown` | `0dde3389aeecdda4b5c4192480c1b62554845a4a348b05ef30dbc808878a0c64` | `b98fb1a079621285e1693f9c780843eecd4cc90bd360c839ebbd93328a701694` |
| `fe3c-confirm-disabled-unchecked` | `0eb84e8dd611b621d079d308f8ed32fce0672ee423bd82ed6589ee0b6c33b47a` | `06ada404fd293cd8fdfa36af61df83f2ee2471bcc5fe9a8fcfa1821d01d411e9` |
| `fe3c-close-result` | `e761fd23f19c190d0398126e434ecab4f2390f8cbcce9ce1f04e6fac3ad9f273` | `0c5b1db9e5ed9c3d3d9244fc0a6fd106ac2384596946ca4143cc02ec6d306771` |

真实 backend 审核顶栏参考（05 r4，1920）：

| 名称 | 宽度 | SHA256 |
| --- | ---: | --- |
| `j1-review-disposition-archived` | 1920 | `90c2916113fcfbaa53c782421a59be4f9eae1086b30b642201054c23648d9d34` |
| `j2-review-disposition-closed` | 1920 | `6477ad534c10a8bee06ac43e3d46219c30c29e8b1a73f97a5f22b762262b7d8d` |
| `j2-review-disposition-closed-at-archive` | 1920 | `e0b03015e2eae2052e438a852e3b8ab939219c10cd5f6e739ebba327e7e9eb6e` |

真实 backend 截图沿用 J1/J2 会话的 1920 视口，没有另拍 1280；这一点列入未处理事项。

## 8. B8：原 handoff 更正

1. **§4.3、§5.1 的 200 回放说法**：修复前 J2 第 4 步的 `route.abort` 没有先把请求送到 backend，也没有真实的 200 回放；原文“同 key 重放 201→200”是计划而非实测。修复后 J2 第 4 步与 V9 都实际执行“转发首次请求→中断→同 key 重试”，实测 `201,200`，结果区显示首次关闭人。
2. **§6.4 UploadStepCard.tsx**：`git diff --name-only fe-fe3b-exit..09351e42ad -- frontend/src/features/workbench/UploadStepCard.tsx` 为空，该文件在本轮范围内没有改动；原文“diff 只是开始按钮的占用原因禁用/提示”不正确。
3. **§10 第 7 项 `test.pmc` 0 字节**：`t1-v1/test.pmc`、`t1-v2/test.pmc` 在原件中本来就是 0 字节占位，不是本轮输入的偏差，也不表示打包/校验缺失。
4. **t1 截图位置**：`saveEvidence` 的 `evidenceDir()` 在容器内默认 `GATEWAY_FE_RESULTS_DIR/evidence`，runner 把 `$LOG_DIR` 挂为 `/results`，所以截图实际写在 `$LOG_DIR/evidence/`；`--evidence-dir` 只接收 `test-results` 的拷贝，不是截图的直接目标。原 handoff 的 t1 截图路径因此写成 `05:<log-dir>/evidence/`。
5. **§2 路径计数**：`09351e42ad` 相对 `fd9e383d76` 是 6 个 `docs/frontend-vnext/` + 54 个 `frontend/`，共 60 个文件；handoff 提交 `1df3dc05e2` 自身再加 1 个 docs 路径，因此 handoff HEAD 为 7 docs + 54 frontend。`vnext` tree 仍为 `6368c9c4`。

## 9. 运行记录

工具链镜像：`mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 RootFS DiffID：

```text
sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278
sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07
sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9
sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d
sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc
sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5
sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb
```


npm 缓存：07/05 均使用来源提交 `a2fb4a027a`；05 缓存目录 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。依赖镜像 `gateway-backend-deps:lock-578e079b762e`，本机 image ID `sha256:2d13e70aa3101dba0bd4f07695ce4886c844b930787b56fafad0bda2c9a0dfbd`。RS 依赖基础镜像 `gateway-p2r1-repository:lock-6dc9659f0aee`；RS 镜像 `rs_image_id` `sha256:2ca6ac784eb08dda3d586359c476b64685a98acdbc5e9e8f68711d32f603bdfc`。backend image `sha256:d9646379aab36bf47ee91b7dd7835526fa78b8dd9e22a80a3b2e74e48232712b`，worker image `sha256:2b7323b27e51c425c87835b17eaf437506cc82075f26b9c884fc6022d37f8ff9`；OpenAPI 比对 `match`。

最终证据运行：

| 用途 | 节点 | hostname | 起（UTC） | 止（UTC） | HEAD 起/止 | exit | 日志 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| 07 模拟 e2e + 截图 | `ct109-gw-dms-07` | `gw-dms-07.lan` | 2026-11-09T16:31:54Z | 2026-11-09T16:34:28Z | `cbb14f57` / `cbb14f57` | 0 | `07:/home/dev/gdds-fe-logs/fe3c-fix1-07-r9/run-tests-e2e.log` | `5f40d1491adf04aeaffee3b3a8d923cda909e34e660911c18767ebeee8c0e0a9` |
| 05 真实 journeys | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T16:13:36Z | 2026-11-09T16:21:15Z | `cbb14f57` / `cbb14f57` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-fix1-05-r4/real-backend-e2e-journeys-fe3c-impl-cbb14f578-20261109T161336Z-2674752.log` | `7fc115d5c8363bab01474f77c0be6ee7de9da8e993c2ef4e1b7f72907027bca8` |
| 05 t1 | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T16:23:54Z | 2026-11-09T16:28:01Z | `cbb14f57` / `cbb14f57` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-fix1-05-r4-t1/real-backend-e2e-t1-fe3c-t1-cbb14f578-20261109T162354Z-2745363.log` | `d69e050f279efaa6b12af7d697bb379cb20bd14959091fdb6c38a2f0971977bd` |
| 05 上传校验器（N1） | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T16:29:39Z | 2026-11-09T16:30:56Z | `cbb14f57` / `cbb14f57` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-fix1-05-r4-validate/upload-validator-cbb14f578c-20261109T162953Z-2785179.log` | `f15d5895c829a8d4d0e02eeff68a0a88fb3757ea388872b5549b3881de266b9f` |

补充日志：05 journeys case log `.../fe3c-fix1-05-r4/evidence/journey-cases.log`，SHA256 `3d3aa0cb0d2a1eb013ba855e846a31ca11e8baacca12ad98bacb3e03bc3ff868`；05 t1 case log `.../fe3c-fix1-05-r4-t1/evidence/journey-cases.log`，SHA256 `4d63b1187827cb49cb5d5764c3a9bb16596913fd631c8582e4751f21e58b441e`。

调试运行（非证据；均未改动 worktree）：

| 运行 | HEAD | exit | 日志 SHA256 |
| --- | --- | ---: | --- |
| 07 r1 | `f34f98df10` | 1 | `b08f6a86f2f55eea2230dd2597cd2848ad43b79ecfe1405d340360bf05231a5a` |
| 07 r2 | `76603a77c7` | 1 | `548c0b3b8a5293d19fdead5710deb3878bc9702ded369c130aa8bc9fda553a2d` |
| 07 r3 | `9aadd8622e` | 1 | `99141c1b4f53613b0b361c950bcfcee86b04f15b07ba2c9d56d84c05684cba81` |
| 07 r4 | `396a983624` | 0 | `7cda300d0bbb0fac666e7feafb93a3646736067e9aeb469ac41d7bda7368dafd` |
| 07 r5 | `4905ebe916` | 0 | `d8f8b9eb4fda046aca01f2802504d2a45595ec70e1eaeea7bf0b70a70b4bb892` |
| 05 r1 | `f34f98df10` | 1 | `3a3cf95e16d1508bf9ffa6a852fda8ec3ce72f2e4cfa6665a3193794bb0d4185` |
| 05 r2 | `9aadd8622e` | 0 | `3ba09a10e454ebcf32bb9b64420c5313ae2edbccd4f0eb4e0f23932fcab87cc2` |
| 05 r3 | `396a983624` | 0 | `d1d16d7da4b2c7eeea9d56f52d5cee4844940e16e12a3687dfacee64b1dde52c` |

另有 07 r6（HEAD 在运行中从 `741ad4bfba` 变为 `cbb14f57`）、07 r7（与 r8 重叠）、07 r8（与 r7 重叠）不列为证据；其日志保留在 `07:/home/dev/gdds-fe-logs/`，不计入本轮结论。

## 10. 仍未处理的事项

1. **D1**：设计会话尚未修正 §16.9 V9 关于 Review 版本的措辞；模拟数据仍保持 §5.3（候选与 Review GET 的 `review_version` 相同），V9 的区分力由“没有 `GET .../review`”断言提供。
2. **D2**：t1 FULL 是否用新浏览器实例由设计会话决定；本轮 t1 的 FULL M1 仍在同一浏览器实例内测得（`renderer_increment_bytes=1961984`），不能与 MODIFIED_ONLY 的 `20631552` 比较，只作 report-only。
3. **04 权威门禁**未运行；07/05 均为调试运行，阶段退出仍需在 04 的 clean、已提交 worktree 上用权威入口完整运行。
4. **main 未合入**：候选只基于 `fd9e383d76`；本地 main 已前进，未重新合并/重算 OpenAPI。
5. **N2/N3/N5** 未处理：过期通过后未重读 History；12 位摘要悬停全文、理由 3 行折叠、原始码悬停未全部实现；`collectionNotice` 同会话不清除。**N4** 只把 J2 第 4 步的 BTU 接受改走界面，J1 的多处接受仍用 API 助手。
6. **N6** 已在第 2 项说明：t1 FULL M1 数值偏低，不能与 MODIFIED_ONLY 比较。
7. 真实 backend 的 D1–D3 参考截图只拍了 1920，未拍 1280。

## 11. SHA 回源核对

交付前用脚本对本文每个十六进制值逐项核对（2026-11-09，在开发机与 05/07 节点上）：

- 64 位 SHA256：本文 48 个，全部命中来源；0 个未通过。来源为 05/07 的日志、证据文件名、`sha256sum` 重算结果、`docker image inspect` 的 config digest 与 RootFS DiffID、npm 缓存归档和镜像 ID。
- 路径 + SHA 配对：8 行模拟截图（16 个 SHA，含 1280/1920 两种宽度）逐行命中文件名与宽度；3 张真实 backend 截图命中 attachments 中的实际文件；4 条运行日志按表内路径逐一重算命中；journeys/t1 两个 case log 也按路径重算命中。
- 40 位 Git 对象：4 个，`git cat-file -t` 分别为 commit/commit/tree/tree；`cbb14f57:frontend` 重算为 `f626a8f0…`、`cbb14f57:vnext` 重算为 `6368c9c4…`，与本文一致。
- 7–12 位截断值：共 45 个。17 个是 Git 提交/树的真实前缀，`git rev-parse --verify <prefix>^{commit|tree}` 全部唯一解析；2 个是日志中真实出现的前缀/后缀（`578e079b762e` 见 `dependency_image=gateway-backend-deps:lock-578e079b762e`，`6dc9659f0aee` 见 `rs_dependency_base_image=gateway-p2r1-repository:lock-6dc9659f0aee`）；20 个是 `sub-…`/`key=…` UUID 的分段；6 个是十进制字节数或时间戳（`1961984`、`20631552`、`20261109`、`2674752`、`2745363`、`2785179`），不是十六进制哈希。
- 长度异常：扫描未发现 13–39、41–63 或 65 位以上的十六进制串；提交前自查发现 DiffID 第 3 行被写成 62 位（漏了前缀 `c8`），已改为 64 位，本文即修正后的版本。

核对脚本与节点原始 `sha256sum` 输出保留在 `/tmp/fe3c-handoff-audit.txt`（开发机），未写入仓库；未通过项为 0。
