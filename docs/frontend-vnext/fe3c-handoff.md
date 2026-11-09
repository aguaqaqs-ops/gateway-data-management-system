# FE3c 实现 handoff

> 状态：调试运行完成，等待设计会话/owner 确认与 04 权威门禁；**未推送**。
> 候选代码 HEAD：`09351e42adf91a17d48c57c47ac24444e39f051a`（分支 `fe-vnext`）
> 本文档提交为同一分支上的 docs-only 子提交；提交后候选 HEAD 会前进一个提交，代码树不变。
> 运行日期：2026-11-09（UTC）；所有时间均为 UTC。

## 1. 结论

- FE3c 的归档业务核验 UI、关闭流程、J1/J2 真实 backend 旅程与 t1 真实数据旅程已实现，并在专用测试节点上各通过一次调试运行。
- 最终 journeys `20/20`、t1 `1/1`、mock e2e `80/80`、`validate-upload-package.sh` `4/4`，四条命令 exit 0；worktree 起止均 clean。
- §4.6 的逐次预检异常集合与实测一致；未发现需要设计会话修正的集合差异。
- t1 §8.3 两个 `pair_id` 的比较对通过；M1 为 report-only：v1 28.95 MiB，为 FE3a 基准 24.86 MiB 的 1.164×，低于 2× 升级线。
- 本文所有 SHA 均从命令输出复制，提交前由脚本逐项回源核对（§11）。
- 未在 04 运行权威门禁，未推送。

## 2. 合并、路径核对

| 项 | 值 |
| --- | --- |
| 合并提交 | `03880f1e757269e039282d017704297bbc3a9107` |
| 第一父（合并前 fe-vnext） | `ed5d2c24e97199db8c9ca840e474a1fdf3633373` |
| 第二父（被合入的 main） | `fd9e383d76642037e4b3246c847222ea9483e033` |
| 被合入 main 的 `vnext` tree | `6368c9c40cf08a97eecf2a0c457a6c16ce448080` |
| 候选 HEAD 的 `vnext` tree | `6368c9c40cf08a97eecf2a0c457a6c16ce448080` |
| 路径核对 | `git rev-parse HEAD:vnext` 与 `git rev-parse fd9e383d76:vnext` 相等；`git diff --name-only fd9e383d76 HEAD` 仅 6 个 `docs/frontend-vnext/` 与 54 个 `frontend/` 路径，0 个白名单外路径 |
| 候选代码 diff 规模（不含本文档提交） | 60 files changed, 13534 insertions(+), 682 deletions(-) |

路径核对命令与结果（原始输出摘要）：

```text
$ git rev-parse 03880f1e757269e039282d017704297bbc3a9107:vnext
6368c9c40cf08a97eecf2a0c457a6c16ce448080
$ git rev-parse fd9e383d76642037e4b3246c847222ea9483e033:vnext
6368c9c40cf08a97eecf2a0c457a6c16ce448080
$ git rev-parse 09351e42adf91a17d48c57c47ac24444e39f051a:vnext
6368c9c40cf08a97eecf2a0c457a6c16ce448080
$ git diff --name-only fd9e383d76642037e4b3246c847222ea9483e033 09351e42adf91a17d48c57c47ac24444e39f051a | cut -d/ -f1 | sort | uniq -c
      6 docs/frontend-vnext
     54 frontend
```

> 注意：本仓库本地 `main` 在 FE3c 实现后已前进到 `2d8b29d332ceb467ba77bb4826fb0925653ebb4e`（`vnext` tree `fb92c4757f4f9d9174ce6ab8c17187fdabafacdf`），候选只合入了 `fd9e383d76`。路径核对是对“已合入的 main”通过，不是对最新 main 通过。阶段退出前若要求最新 main，需要重新合并并重算 OpenAPI 原件；见 §10。

## 3. OpenAPI 原件重算与快照差异

FE3b 的 OpenAPI 快照以 `fe-fe3b-exit`（`8da25ee3f593c55593b4e58b122f17cd6e38e8ac`）为基线。FE3c 的 vnext tree 为 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`，对应运行时 OpenAPI 原件 `/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`。

| 对象 | 字节 | SHA256 |
| --- | ---: | --- |
| 原件 raw | 79,082 | `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079` |
| 原件按仓库规范化（`json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`） | 146,666 | `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a` |
| 提交的 `frontend/openapi.json` | 146,666 | `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a` |
| 运行时 `/openapi.json` 规范化 | 146,666 | `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a` |

- 提交快照 raw 字节本身已是规范化形式，因此 raw 与 normalized 的 SHA 相同。
- `frontend/openapi.json` 与原件规范化结果的 diff 为空。
- 运行时 `openapi_compare=match`（t1 runner 每次重算并比较）。
- 相对 FE3b 快照的唯一差异是 `ArchiveCandidateResponse` 新增 `review_version`，并把它追加到 `required`：

```json
"review_version": {
  "maximum": 9007199254740991.0,
  "minimum": 0.0,
  "title": "Review Version",
  "type": "integer"
}
```

```json
"required": [
  "submission_id",
  "expected_candidate_digest",
  "review_version"
]
```

- 无其他 schema/path/operation 差异。

## 4. §4.6 预期异常表与实测

### 4.1 集合记号

| 缩写 | 完整 code |
| --- | --- |
| `GTM` | `GENERATION_TIME_MISSING` |
| `BTU` | `BASELINE_TIME_UNAVAILABLE` |
| `ASE` | `APPROVED_SIBLING_EXCLUDED` |
| `PIE` | `PROJECT_IDENTITY_EXCEPTION` |
| `ISU` | `INITIAL_SOURCE_UNEXPLAINED` |

表中 `GTM/MODIFIED/A` 表示 code/affected side/提交 A；方括号表示同一异常携带的 affected 提交集合。集合按“逐次预检”列出，顺序不作为断言；实测来自最终 journeys 运行的 `journey-cases.log`（05，`/home/dev/gdds-fe-logs/fe3c-05/evidence/journey-cases.log`）。

### 4.2 逐次预检

| 预检 | §4.6 / 步骤预期 | 实测集合 | 差异 |
| --- | --- | --- | --- |
| J1 step 2（A，MODIFIED_ONLY） | 1 项：`GTM/MODIFIED/A` | 1 项：`GTM/MODIFIED/A` | 无 |
| J1 step 7（B，FULL；C 关闭后重预检） | 3 项：`GTM/INITIAL/B`、`GTM/MODIFIED/B`、`BTU/[B]` | 3 项：`GTM/INITIAL/B`、`GTM/MODIFIED/B`、`BTU/[B]` | 无 |
| J1 step 11（C，MODIFIED_ONLY） | 2 项：`GTM/MODIFIED/C`、`BTU/[C]` | 2 项：`GTM/MODIFIED/C`、`BTU/[C]` | 无 |
| J1 step 13（D，MODIFIED_ONLY，身份不同） | 3 项：`GTM/MODIFIED/D`、`BTU/[D]`、`PIE/D` | 3 项：`GTM/MODIFIED/D`、`BTU/[D]`、`PIE/D` | 无 |
| J2 step 1（A，MODIFIED_ONLY） | 1 项：`GTM/MODIFIED/A` | 1 项：`GTM/MODIFIED/A` | 无 |
| J2 step 3（B 归档，候选 B/C/E） | 8 项：`GTM/INITIAL/B`、`GTM/MODIFIED/B`、`GTM/MODIFIED/C`、`GTM/INITIAL/E`、`GTM/MODIFIED/E`、`BTU/[B,C,E]`、`ASE/C`、`ASE/E` | 同 8 项 | 无 |
| J2 step 5（关闭 C 后自动重预检） | 7 项：`ISU/INITIAL/[E]`、`GTM/INITIAL/B`、`GTM/MODIFIED/B`、`GTM/INITIAL/E`、`GTM/MODIFIED/E`、`BTU/[B,E]`、`ASE/E` | 同 7 项 | 无 |
| J2 step 8（C 重新提交并归档） | 2 项：`GTM/MODIFIED/C`、`BTU/[C]` | 2 项：`GTM/MODIFIED/C`、`BTU/[C]` | 无 |

J1 step 2、J2 step 1、J2 step 8 的 §4.6 预期从“每个上传侧都有 `GENERATION_TIME_MISSING`、归档基线无有效时间时全部候选有 `BASELINE_TIME_UNAVAILABLE`”推导；实测与推导一致。

### 4.3 非异常断言

| 断言 | 实测 |
| --- | --- |
| J1 step 4（B FULL 预览） | `baseline_to_initial.changed=0`；`initial_to_modified.changed=5` |
| J1 step 10 | 归档 B，head=2 |
| J1 step 11 / 13 / 14 | 归档 C head=3；归档 D head=4；三节点历史可浏览 |
| J2 step 4 | 关闭 C，`review_version=1`；同 key 重放 201→200，UI 显示首次关闭人/时间/理由 |
| J2 step 5 | 7 项全部 `UNRESOLVED`（关闭后 candidate_set_digest 变化，全部失效） |
| J2 step 6 | s2 刷新后空指针、上传可用；C 树节点为“已关闭未归档”；审核详情含关闭人/时间/理由 |
| J2 step 7 | 归档 B head=2；E 以“归档时选中了其他提交”关闭；s3 工作区释放 |
| J2 step 8 | 重新上传 C、预览、提交、审核、归档 head=3 |

### 4.4 来源诊断与设计会话处理

- J1 step 2 断言来源诊断 `NOT_APPLICABLE`；J2 step 3 断言 3 个候选来源均为 `EXPLAINED`（B 命中基线、C 复用基线、E ① 命中 C 的 ②）。
- **J1 step 7 的来源 `EXPLAINED` 没有在测试中断言**，只断言了 3 个异常项。由于 J1 step 2 已覆盖 `NOT_APPLICABLE`、J2 step 3 已覆盖 `EXPLAINED`，本轮不把它当作阻塞项，但作为断言缺口记录（§10）。
- 时间质量/顺序类异常（`TIME_ABNORMAL_*`、`GENERATION_TIME_LAST_NOT_MAX`）在合成输入上不可达：合成 `version_manager` 没有 `saved_time`，`GENERATION_TIME_MISSING` 先触发 `NOT_COMPARABLE`；因此 §4.6 的“无 TIME_ABNORMAL*”是构造性结论，实测也从未出现。只由 mock 覆盖（§5.2）。
- 设计会话处理：本轮未发现需要修正 §4.6 的集合差异；请设计会话确认 J1 step 7 来源断言的缺口和截图缺口即可。

## 5. V1–V14、J1、J2 与用例对应

### 5.1 V1–V14（mock e2e）

文件：`frontend/e2e/archive-validation.spec.ts`；V11/V12 在 `frontend/e2e/workspace-shell.spec.ts`。

| 用例 | 测试位置 | 覆盖点 |
| --- | --- | --- |
| V1 | `archive-validation.spec.ts:222`、`:240` | 九类业务核验卡片与详情；未知 code 无接受入口、确认归档禁用 |
| V2 | `:251` | 两侧独立项分别接受/撤销 |
| V3 | `:286` | 接受后原始诊断不变、无成功色 |
| V4 | `:298` | 撤销后回未处理、确认归档禁用 |
| V5 | `:312`、`:327` | 审计冲突提示并重新预检不重发；候选集合变化提示 |
| V6 | `:341` | 399 条引用全部进入开始归档请求 |
| V7 | `:365` | 阻断项只有文字与重新预检，无接受 |
| V8 | `:382` | 待审核阻塞列出全部并可定位 |
| V9 | `:403`、`:425` | 关闭携带同次候选 review_version，200 回放显示首次关闭人；理由 4096/4097 字节边界与 409 |
| V10 | `:458` | 关闭后自动重预检、全部回未处理 |
| V11 | `workspace-shell.spec.ts:1549` | 审核过期 409，顶栏过期态；截图 `fe3c-review-expired` |
| V12 | `workspace-shell.spec.ts:1566` | `ARCHIVE_CLOSED`；截图 `fe3c-review-closed` |
| V13 | `archive-validation.spec.ts:476` | 开始归档被拒后无状态改写、可重试 |
| V14 | `:491` | 所有归档请求的 `selected` 恰好两个键（实现/评审新增，§16.9 未列） |

### 5.2 J1（`frontend/e2e-real/journeys.spec.ts:1437`）

| 步骤 | 用例内断言位置 | 结果 |
| --- | --- | --- |
| J1 1–3：A 上传/审核/预检/接受/撤销/再接受/归档 | 测试主体；step4 断言 `:1517` | 1 项 `GTM/MODIFIED/A`；归档 head=1；树显示归档基线 1/A archived |
| J1 4：B FULL 预览 | `:1517` | `baseline_to_initial.changed=0`；`initial_to_modified.changed≥1`（实测 5） |
| J1 5：B/C 提交与审核 | 测试主体 | B APPROVED，C PENDING |
| J1 6：B 归档阻断 | `:1529` | `ARCHIVE_PENDING_REVIEW`，列出 C 名称 |
| J1 7：拒绝 C、重传草案、重预检 | `:1552` | 3 项，见 §4.2；来源 B 未断言 |
| J1 8：只接受 INITIAL 侧 | 测试主体 | MODIFIED 仍未处理，确认按钮禁用 |
| J1 9：第二上下文撤销 MODIFIED 后开始归档 | 测试主体 | 409 `ARCHIVE_ANOMALY_UNRESOLVED`；UI 提示重新预检，不自动重发 |
| J1 10：再接受 + 归档 | `:1591` | head=2 |
| J1 11：C 重传/提交/审核/预检/归档 | `:1605` | 2 项，见 §4.2；head=3 |
| J1 12：D 预览身份不同 | 测试主体 | `DIFFERENT_PROJECT`；提交对话框要求确认 |
| J1 13：D 归档 | `:1638` | 3 项含 `PIE/D`；归档成功 |
| J1 14：三节点历史比较与浏览 | `:1664` | INITIAL、archive1、archive2 可比较/浏览 |

### 5.3 J2（`frontend/e2e-real/journeys.spec.ts:1679`）

| 步骤 | 用例内断言位置 | 结果 |
| --- | --- | --- |
| J2 1：A 归档 | 测试主体 | 1 项；head=1 |
| J2 2：B FULL、C MODIFIED、E FULL 提交并审核 | 测试主体 | 3 个已审核候选 |
| J2 3：B 预检 | `:1739` | 8 项，见 §4.2；3 个来源均 `EXPLAINED` |
| J2 4：接受 BTU、关闭 C、浏览器中断后重试 | `:1777` | `review_version=1`；201→200 回放；UI 首次关闭人/时间/理由 |
| J2 5：自动重预检 | `:1792` | 7 项；全部 `UNRESOLVED`；candidate_set_digest 变化 |
| J2 6：s2 刷新与工作区释放 | `:1807` | 空指针、上传可用；C 已关闭未归档；审核详情含关闭信息 |
| J2 7：接受全部、归档 B、关闭 E | `:1823` | head=2；E 关闭理由“归档时选中了其他提交”；s3 工作区释放 |
| J2 8：C 重传/预览/提交/审核/预检/归档 | `:1849` | 2 项，见 §4.2；head=3 |

### 5.4 `selected` 的构造位置与“只取两个字段”的方式

| 位置 | 作用 | 方式 |
| --- | --- | --- |
| `frontend/src/features/api/journeys.ts:372-386` | 生产 helper `buildArchiveSelectedRef` | 参数类型和返回对象都只含 `submission_id`、`expected_candidate_digest`；函数内逐字段构造，不 spread 整个候选对象 |
| `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:230` | 初次预览 | 调 helper |
| `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:312` | 异常接受/撤销后的请求追加 | 调 helper；只追加异常 resolution，不改 selected 的键 |
| `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:428` | 开始归档 | 调 helper |
| `frontend/src/features/api/journeys.test.ts:170-173` | 单元测试 | `Object.keys(selected)` 恰好两个 |
| `frontend/src/features/dev/mock-data.ts:781-792` | 模拟接口校验 | allow-list 只允许两个键，其他键拒绝 |
| `frontend/e2e-real/lib/api.ts:322-326` | 真实 e2e API 类型 | 参数类型只含两个字段 |
| `frontend/e2e-real/journeys.spec.ts:1395` | J1 字面量 | 只写两个键 |
| `frontend/e2e-real/t1.spec.ts:275` | t1 字面量 | 只写两个键 |
| `frontend/e2e/archive-validation.spec.ts:359-360`、`:511-513` | V14 wire 断言 | 对每个归档请求断言 `Object.keys(selected)` 恰好两个 |

结论：生产路径没有把整个 candidate 对象传入 `selected`；即使调用方持有更多字段，helper 的返回对象也只有两个键。

### 5.5 只由模拟接口覆盖的项与原因

| 项 | 原因 |
| --- | --- |
| V6 399 条引用 | 真实 backend 构造 200 个 FULL 候选不现实，且会显著拖长真实数据旅程 |
| V11 审核过期 409 | 需要服务端审核过期/时钟条件，调试节点上无法稳定构造 |
| V12 `ARCHIVE_CLOSED` | 需要归档后关闭/删除竞态，真实旅程难以稳定复现 |
| V7 完整性失败/有活动归档尝试 | 需要故障注入或并发窗口 |
| V1 未知 code | 需要后端返回前端尚不认识的 code，只能在模拟接口构造 |
| 时间质量/顺序异常（`TIME_ABNORMAL_*`、`GENERATION_TIME_LAST_NOT_MAX`） | 合成输入没有 `saved_time`，`GENERATION_TIME_MISSING` 先使比较 `NOT_COMPARABLE`；见 §4.4 |
| 关闭理由 4096/4097 字节边界 | 用模拟接口精确构造；真实数据旅程不携带边界理由 |
| `selected` 恰好两个键 | V14 对所有归档请求断言；真实旅程的 helper 单元测试和字面量也覆盖 |

真实 backend 覆盖 J1/J2 全部业务异常流程、关闭、身份异常和三节点历史；t1 覆盖真实数据上传/预览/归档/三节点历史。

## 6. t1 真实数据旅程

### 6.1 环境与步骤

- 节点：`ct108-gw-dms-05`（hostname `gw-dms-test-05.lan`）。
- worktree：`/home/dev/gdds-test-tmp/wt/fe3c-05-2246e6f2a1`，HEAD `09351e42adf91a17d48c57c47ac24444e39f051a`，clean。
- 输入根：`/home/dev/gateway-real-dumps/source-dirs`；`t1-v1`、`t1-v2` 各 11 个顶层条目，挂载 `:ro`。`t1-v1/test.pmc` 为 0 字节占位；runner 校验“一个顶层 `.pmc` + `sql/dbcfg.sql` + `comps/logic/logics.xml`”并记录 `sha256sum`。
- 命令：`frontend/scripts/run-real-backend-e2e.sh --suite t1 --session fe3c-impl --input-root /home/dev/gateway-real-dumps/source-dirs --log-dir /home/dev/gdds-fe-logs/fe3c-05 --evidence-dir /home/dev/gdds-fe-evidence-05/fe3c-t1-r2 --subphase fe3c`。
- 六个步骤：① submitter 上传 `t1-v1` MODIFIED_ONLY，预览/下载/提交；② reviewer History 审核通过；③ archiver 主线预检（业务核验）→ 归档，head→1；④ submitter FULL 上传 ①`t1-v1` ②`t1-v2`，预览/下载两对/提交；⑤ reviewer 审核通过；⑥ reviewer 三节点历史比较。

结果：`t1-step3 anomalies=[]`（无业务核验编码），归档 `sub-a2f1a83d-a7a2-4487-b3eb-5a86add75e88` head=1；`t1-step4 composite_changed=0`；六步全部通过。

### 6.2 §8.3 逐条核对

常量来源：`vnext/backend/benchmarks/real_dump_journey.py` 的 `S2B_DATASET_BASELINE`（`rd-t1-a-v1`/`rd-t1-a-v2` 的 `preview_table_count=124`）与 `S1B_V2_PREVIEW_CHANGED_COUNTS`（`rd-t1-a-v2=4`），用 `python3 -I` + `ast.literal_eval` 读取。

| 比较对（`pair_id`） | 步骤 | 字段 | 预期 | 实测 | 结果 |
| --- | --- | --- | --- | --- | --- |
| `initial_to_modified`（v1 预览） | 1 | table_count | 124+1=125 | 125 | 通过 |
| `initial_to_modified`（v1 预览） | 1 | changed | 125 | 125 | 通过 |
| `initial_to_modified`（v1 预览） | 1 | degraded / failed | 0 / 0 | 0 / 0 | 通过 |
| `baseline_to_initial` | 4 | changed | 0 | 0 | 通过 |
| `baseline_to_initial` | 4 | degraded / failed | 0 / 0 | 0 / 0 | 通过 |
| `baseline_to_initial` | 4 | table_count | 未在测试中断言 | 未记录 | 缺口，见 §10 |
| `initial_to_modified`（FULL） | 4 | table_count | 124+1=125 | 125 | 通过 |
| `initial_to_modified`（FULL） | 4 | changed | 4 + composite_changed(0)=4 | 4 | 通过 |
| `initial_to_modified`（FULL） | 4 | degraded / failed | 0 / 0 | 0 / 0 | 通过 |

`baseline_to_initial.table_count` 只作为推断：FULL 的 ① 就是归档后的 v1，两侧都应是 125；当前测试和 case log 没有记录该字段，不能写成“实测 125”。

### 6.3 第 3 步业务核验编码与后端 t1 对照

- 实测第 3 步 `anomalies=[]`，即没有出现 `GENERATION_TIME_MISSING`、`BASELINE_TIME_UNAVAILABLE`、`PROJECT_IDENTITY_EXCEPTION` 等编码。
- `vnext/backend/benchmarks/real_dump_journey.py` 没有为 t1 定义“预期异常集合”；它按通用逻辑接受带理由的异常（`_apply_archive_anomalies`/`require_one_of` 风格），因此前端 `[]` 不与后端 t1 的某个固定期望冲突。
- §8 的预期是空 INITIAL 上不应有业务核验阻断；实测为空集合，符合。若出现时间质量/顺序编码，按 §8 应接受并列出细节；本轮未出现。

### 6.4 M1 数据与结论

| 测量 | renderer increment | RssAnon max | RssFile max | RssShmem max |
| --- | ---: | ---: | ---: | ---: |
| t1-v1 MODIFIED_ONLY | 30,351,360 B（28.95 MiB） | 53,506,048 B | 110,223,360 B | 30,248,960 B |
| t1 FULL（①+②） | 7,270,400 B（6.93 MiB） | 90,439,680 B | 115,568,640 B | 48,386,048 B |

- FE3a 参考：t1 v1 19 文件/6,853,875 B，renderer 24.86/24.89/24.86 MiB，median 24.86 MiB（26,071,040 B），max 26,103,808 B；浏览器主进程 2.13/2.85/2.75 MiB；包 461,275 B。
- 本次/参考 = 28.95/24.86 = 1.164×，低于 §8.4 的 2× 升级线（49.72 MiB），不升级。
- 方法差异：FE3a 是模拟接口 3 次运行的中位数；本次是单次真实数据旅程内生产构建的 renderer 增量。两者不是同分布，结论仅作 report-only。
- FULL 没有 FE3a 参考，report-only；RssAnon/RssFile/RssShmem 按要求记录。
- FE3c 没有改打包/压缩代码（`UploadStepCard.tsx` 的 diff 只是开始按钮的占用原因禁用/提示），按 §8.4 不重跑 t4 M1；t4 仍是唯一阈值。

### 6.5 t1 截图

t1 截图在 `05:/home/dev/gdds-fe-logs/fe3c-05/evidence/`，文件名与 SHA：

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| `t1-real-data-journey-with-M1-re-measurement-t1-v1-diff.png` | 134,470 | `d1cbb640826a7cf9eb9d0606e6e6581786b9cea29bc1ba66c412164484d1d9ab` |
| `t1-real-data-journey-with-M1-re-measurement-t1-archive-v1.png` | 116,040 | `339ac643f9d0ad6b7a6139e1b319ee41e393af6f319573594a1b2955e8e6577c` |
| `t1-real-data-journey-with-M1-re-measurement-t1-v2-diff.png` | 149,385 | `bfa4b8ca56651909d53bb2055d25e09e57fa718a766fdf30bce3f1f789464606` |
| `t1-real-data-journey-with-M1-re-measurement-t1-history-three-nodes.png` | 121,300 | `d976d8ea98668cf8b98fbe3ac276e81addf132cd01153f8e57deaa155ce36880` |

早期失败运行的 `artifacts/.../attachments/` 同名文件不是本轮证据，不引用。

## 7. Mock e2e 与前端门禁

`frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-shots/fe3c-mock-20261109-final` 在 07 通过：

- typecheck、lint、unit（33 files/188 tests）、build、production build check、mock e2e（80 tests）全部通过，exit 0。
- 覆盖 V1–V14、V11/V12、上传/归档/关闭/权限/过期等 FE3c mock 场景；截图清单见 §8。
- 该运行是调试运行；阶段退出的 04 权威运行仍需按 kickoff §9 执行。

## 8. 截图清单（kickoff §9 FE3c）

### 8.1 07 mock 截图

目录：`/home/dev/gdds-fe-shots/fe3c-mock-20261109-final`。所有文件均为 1280×800 与 1920×1080；嵌套 FE3c 文件在 `1280/`、`1920/` 下，顶层 FE3c 文件为 `<name>-<width>.png`。

| 名称 | 1280 SHA256 | 1920 SHA256 |
| --- | --- | --- |
| `fe3c-validation-overview` | `aeba8db410b448837966ff4e07f3f1c67cfae13b97476e91ce6090e29d85653a` | `2b1020104baa6d9b6b3aa050d3d4ddc72f3bcbf3899709dfa2088e5d702e4ee4` |
| `fe3c-accept-dialog` | `a936cf18d6c1d7808132d85b4f517c161ce1539234348b6e5f1362f5622cfd22` | `0c02d12efdfc6e6889e3156ad8114d4d19565dc99082f8b0331a27065c203f9c` |
| `fe3c-twoside` | `f50fc5e9d4fa7d96553a5f99fdcbc4deb9410b2de2fe00f28fed617e190955a5` | `6d3671b61f2337e3e1e88e7e4c0f0b3f2a145df6bdb85090f1b585cb393e851e` |
| `fe3c-source-accepted` | `16a329f0a12a37bcee46c36b9f842e96665634369c12c0c086ae725ce0c83b96` | `04881b6e8addd9c6e0834e89c124ba2c1189c08b49c0c2cf5bcddae14bae4412` |
| `fe3c-revoke-dialog` | `1811a8d966f7dcf06c77109d81f0e7f4772535dd6caad70e0c16d6d562ca110b` | `00e077031a8439560ab5b966093a8ef5bb0505285b17564d2b0665f75ce8204f` |
| `fe3c-many-first` | `169144e7b0439959cf374b0b8db2b483fba1c3ca406f649285c44ab8e00f9111` | `bc8f864244ae36bdb4540045e44f8015d22ac388e143be160e2403579a81f6b3` |
| `fe3c-blocker-no-entry` | `9f180d7df37882bb2635f64d83028c452d8ac2614906aab937e5ac130235b0d6` | `13dd3b60945b80b3b9147d6a6aa1723e244945f32a871d6c3798d8340857aacc` |
| `fe3c-pending-blocked` | `082c8ac9e5f4adc5afd48aa9fe6f50a3026aa2e06b2cf3ddafcc4139bcb13258` | `06fcfcfec74013f9a2503c5d4e4977e7f443be7d3d653481ecab1fcb06e659fb` |
| `fe3c-close-dialog` | `7cdb0715c0cc890a5c4d84ce6380bcbc83385562b69af414323ef2263cbc863d` | `d7500bf23df74ed2b503ebd7e720d0c46c28f125b93eceb3aaa36ecbd08a7d64` |
| `fe3c-close-result` | `e761fd23f19c190d0398126e434ecab4f2390f8cbcce9ce1f04e6fac3ad9f273` | `0c5b1db9e5ed9c3d3d9244fc0a6fd106ac2384596946ca4143cc02ec6d306771` |
| `fe3c-start-rejected` | `4575a3e96d36d4bf7fcc85d284ec2929b51d38a4e486f95fedff64fd87dbd3d8` | `c77e34b5a73f649483e9882a4b3d073729ea1bf527e0c1bfe62b514904f6e89c` |
| `archive-blocked` | `6d4c69b4a166cefa821fbdfa3f17b69bb976ad34fe546e91f35160951825e4a1` | `3c6b13934fe0928e034423edab6b502ded64704eed34d41bbcd5eec32ae080f5` |
| `archive-audit-conflict` | `073ffc9360ea246f155c2a320b54784edee8ad00f2458a19691e13db3e8938d4` | `17cd6f185cb8792ed5cb2483c4b117573379891efb2a8e5fd7a0abd5d571ba48` |
| `archive-permission-denied` | `dd15aa1034900150621da7e85bce37ff448830c2d4516bf71af2eda3fb7010ad` | `d3fd5f4619efc38574412ddd83fce5db6add9006fa00ff4bee79c70ccdf7cf66` |
| `upload-running-modified-only` | `4e64cdce91c04fd85a21867e575168c07007c36720b8ba66136f3f973972724a` | `02d100263dec119255ab45110e8d12c5df53f56ccd83d01d35ef077f9c6023e0` |
| `submit-manual-recovery` | `2a30664dff6abb26e7caf71e4e872585987b1864faeaf4f9674b621a55d2e5b8` | `b8c6c787f5ca4e94e7ec08e35172f9bea1b072ab7c4614371dbd37e511a73974` |
| `submit-result` | `6534301b37c9a1a648965241d0328a2831eeb7b20ed5c7f77b30003d31e3282d` | `ebcfbc866a4fc2ebed5c21694a7a1fe4c35a2401e550f1a22bf01189833be1f5` |
| `submit-aborted` | `5d3f4625e08c3e59641f331e92c92221e89d5a03e865221d00a244b37f4685aa` | `17c351347dfa9e97e4d85a3e59a19b20990b59c61bbbac5463ea41bc4b4e03e6` |
| `review-version-conflict` | `5047580dc17761ba7760605651aabea4e8c04aa819524d6163ab441c41c63717` | `783fcc924f95b6d838b71bcd3168f93422220c58ae6f87789ecf90b0c7a5bf73` |
| `fe3c-review-expired` | `b85e61ce7ca49ae975bfe2e4d775a6ce753f842d452910c8ce78d878955b3e33` | `a39b7ef39fe4709098d2974373d05d03d6cd0041bada89c39b35f5aa0e7e18fa` |
| `fe3c-review-closed` | `1ca107cbe20e655917f5a6b60aacf115452f5ca999a22796fd3e66df567f016a` | `4327a580ef134d62ac86fc9ce6bc5717e37bcbbd9b05b43fbf7ffc06e5a5a06c` |


### 8.2 §9 覆盖对照

| §9 要求 | 对应截图 | 状态 |
| --- | --- | --- |
| 业务核验总览 | `fe3c-validation-overview` | 有 |
| 两侧独立卡片 | `fe3c-twoside` | 有 |
| 来源未解释项接受后的卡片 | `fe3c-source-accepted` | 有 |
| 时间质量/顺序卡片 | 无专门截图；V1 九类卡片测试覆盖，但截图只拍到来源组 | 缺口 |
| `GENERATION_TIME_LAST_NOT_MAX` 卡片 | 无专门截图 | 缺口 |
| 399 条分组首屏 | `fe3c-many-first` | 有 |
| 接受对话框（空理由禁用） | `fe3c-accept-dialog` | 有 |
| 撤销对话框 | `fe3c-revoke-dialog` | 有 |
| 关闭对话框 | `fe3c-close-dialog` | 有 |
| 关闭结果/200 回放首次关闭人 | `fe3c-close-result` | 有 |
| 待审核阻塞 | `fe3c-pending-blocked` | 有 |
| 完整性阻断无接受入口 | `fe3c-blocker-no-entry` | 有 |
| 确认归档禁用原因矩阵 | `fe3c-start-rejected`、`archive-blocked`、`archive-audit-conflict`、`archive-permission-denied`、`upload-running-modified-only` | 部分；不是完整矩阵 |
| 开始归档被拒 | `fe3c-start-rejected` | 有 |
| 审核顶栏过期 409 | `fe3c-review-expired` | 有 |
| `ARCHIVE_CLOSED` | `fe3c-review-closed` | 有 |
| 真实数据 D1–D3 树/顶栏参考 | 无 | 缺口；t1 只有 4 张旅程证据图 |

结论：截图覆盖了主流程和多数阻断态，但 §9 的时间质量/顺序卡片、完整禁用原因矩阵、D1–D3 参考没有专门截图。是否必须补齐，交 owner/设计会话确认；本轮作为偏差记录。

## 9. 运行记录与身份

### 9.1 运行表

| 运行 | 节点 | hostname | 起（UTC） | 止（UTC） | 起 HEAD | 止 HEAD | exit | 日志 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| 07 mock + screenshots | `ct109-gw-dms-07` | `gw-dms-07.lan` | 2026-11-09T13:57:17Z | 2026-11-09T13:59:25Z | `09351e42adf91a17d48c57c47ac24444e39f051a` | `09351e42adf91a17d48c57c47ac24444e39f051a` | 0 | `07:/home/dev/gdds-fe-logs/fe3c-07/frontend-tests-09351e42ad-20261109T135655Z.log` | `67eb6b5504594bd306208d18e9358b122a98700c3c971b14f7b83176d16176c8` |
| 05 t1 | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T13:54:43Z | 2026-11-09T13:58:50Z | `09351e42adf91a17d48c57c47ac24444e39f051a` | `09351e42adf91a17d48c57c47ac24444e39f051a` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-05/real-backend-e2e-t1-fe3c-impl-09351e42a-20261109T135443Z-2143667.log` | `526c74817fcedd4520b70ab9862a4362eba3130e07bd9de8d46b4cfd4fd0ccc6` |
| 05 journeys | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T13:59:50Z | 2026-11-09T14:07:19Z | `09351e42adf91a17d48c57c47ac24444e39f051a` | `09351e42adf91a17d48c57c47ac24444e39f051a` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-05/real-backend-e2e-journeys-fe3c-impl-09351e42a-20261109T135950Z-2183780.log` | `282092858826b8b422f08acf99a2d5b47669f60fbe564b7fd15adc6f485d5ba2` |
| 05 validate-upload-package | `ct108-gw-dms-05` | `gw-dms-test-05.lan` | 2026-11-09T14:07:39Z | 2026-11-09T14:08:52Z | `09351e42adf91a17d48c57c47ac24444e39f051a` | `09351e42adf91a17d48c57c47ac24444e39f051a` | 0 | `05:/home/dev/gdds-fe-logs/fe3c-05/validate/upload-validator-09351e42ad-20261109T140739Z-2254074.log` | `df67a3201ef73d66236b04615e3fda948398df791afc14fd68ce0ddb2a3690c2` |

- 07 的 wrapper 日志另有一份详细日志 `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261109T135717Z.log`，SHA256 `5384de6ff901b44c4802eb452a708df59c70d85036fc978635d60836ca404731`。
- 四个运行的 `frontend_tree` 均为 `6158d776080e82a7fa9696a1a18675e1208dd799`；`vnext_tree` 均为 `6368c9c40cf08a97eecf2a0c457a6c16ce448080`。
- 05 t1 与 07 mock 在不同节点上时间重叠（13:57–13:58），符合节点独立规则；05 的 t1、journeys、validator 串行。
- 工作树起止均 clean；日志均在 worktree 外。

### 9.2 工具链、npm 缓存、依赖与 RS 身份

- 07 运行：`GATEWAY_FE_TEST_WORKERS=2`，工具链容器网络 `none`；npm 缓存目录 `/home/dev/gdds-fe-cache/frontend/npm-cache`，源归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，归档 SHA `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，源提交 `a2fb4a027a`。
- 05 运行：`TMPDIR=/home/dev/gdds-test-tmp`；npm 缓存目录 `/home/dev/gdds-fe-cache/fe0/npm-cache`，源归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，归档 SHA 同上，源提交 `a2fb4a027a`。
- 05/07 工具链镜像同一身份：`mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 RootFS DiffID。
- 05 Docker `29.9.1`，Compose `5.6.0`。

### 工具链镜像（05 与 07 同一身份）

| 项 | 值 |
| --- | --- |
| 镜像 | `mcr.microsoft.com/playwright:v1.64.1-noble` |
| config digest | `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017` |
| RootFS DiffID 数 | 7 |

RootFS DiffID：

- `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  - `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  - `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  - `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  - `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  - `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  - `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

### backend 依赖基础镜像

| 项 | 值 |
| --- | --- |
| tag | `gateway-backend-deps:lock-578e079b762e` |
| 输入摘要 | `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5` |
| 本机 image ID（仅供参考） | `sha256:2d13e70aa3101dba0bd4f07695ce4886c844b930787b56fafad0bda2c9a0dfbd` |
| config digest | `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` |
| RootFS DiffID 数 | 19 |

RootFS DiffID：

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

### Repository Service 依赖基础镜像与 RS 镜像

| 项 | 值 |
| --- | --- |
| RS 依赖基础镜像 | `gateway-p2r1-repository:lock-6dc9659f0aee` |
| RS 依赖 uv.lock SHA256 label | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| RS 镜像 tag | `gateway-repository-service:fe-09351e42adf9` |
| RS 本机 image ID（05 t1 运行，仅供参考） | `sha256:89be4357a72bb45dbd695f1fc66fa46cb54664fa412b59da572219fe652d370d` |
| RS config digest | `sha256:9b8c208dcfd40cde0b6c18f70e6523e1e4eec22cb02c523c3b5a917638014a9f` |
| RS RootFS DiffID 数 | 28 |

RS RootFS DiffID：

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
  - `sha256:a726ea0b5e280abbd87ceb5f5d0eb2343413e3644e4d469775ce98342629eed9`
  - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
  - `sha256:5a81223444c9e36b68f991c274f1698d543abf6be384419223bbc46212a48730`
  - `sha256:b08d290ade3ddd43d592117771e55de526d49ccb202fa01c276275acf5490dff`
  - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
  - `sha256:b962b4683835d1ac0956f933c709823ecef22d2456f0a513d1bf00a7ff2ea86f`
  - `sha256:1ae1813fd5cf7d30af43908ba94ba4837a0742f10e9deab76ad6d1bda01c3443`
  - `sha256:0bcab9eaddfb29c61cfb4371b6eae7a03f95b19f976e48008a0f28aa12f5e97e`
  - `sha256:cd6bfbcf8489e27577f3aaac14ca25d4c4eddb780fabac085bd8c17c84f16d0c`
  - `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`

### 校验器镜像（validate-upload-package.sh 临时构建，运行后删除）

| 项 | 值 |
| --- | --- |
| tag | `gateway-backend-validate:fe-09351e42ad` |
| config digest | `sha256:dfbf180703939ba3f5336e892011ad9ae1ad1f6f1ccf60a251ee79a5bfa01acb` |
| RootFS DiffID 数 | 13 |

RootFS DiffID：

- `sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`
  - `sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`
  - `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18`
  - `sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`
  - `sha256:c13de7943e38051b7d0696374ce006eea481e57f938605adca62d00dce64d8b4`
  - `sha256:3c532e5e25e5be49a1e9a9891a12ee65361cda80931d4d9b041dc16e9301b77a`
  - `sha256:387a9f613c555ae7a735f7fbce669004f0a2f1a37127a6f12ca450e485d1511e`
  - `sha256:7df247c7aa1f61ca60eb1d5e740ca81b52f3fc75cf38410220792d3549636994`
  - `sha256:3d6770e1c19bffc4b71a2a3acc99d35a8010565fec30a43016960e0c6fc278b8`
  - `sha256:afe611dca541c4becf50fd339e78d7ad0f36815e3a0aaa0a1b8ae3075184990b`
  - `sha256:9d95d0711cc7aa5d61642fafc3aa9e2925f031327c9da5413684def5845fa4df`
  - `sha256:5929366fe9372510f8bbc7f08c955ea853ce1e362d010553cc4e80519dce910f`
  - `sha256:60d03fd7b3c70a45a95562c9238fbc35c872924469032d20b8651721d838f26a`


### 9.3 每次运行的 RS/backend/worker 镜像

| 运行 | RS image ID（本机） | backend image ID | worker image ID |
| --- | --- | --- | --- |
| 05 t1 | `sha256:89be4357a72bb45dbd695f1fc66fa46cb54664fa412b59da572219fe652d370d` | `sha256:10ac81fdea4f43163f5598fa2b94294f2e62c87031fbffa2ef920cab575b872b` | `sha256:060db97b45726ac16cf716f76f548525c70b665695911f3bacf62813ebee342d` |
| 05 journeys | `sha256:4e21e5ef4c6f9a2d4f275eec7ec77ef4ff0987edf10721724d7cb1fa390da56d` | `sha256:c5f3ba6fb2fa49acb51a4156f0768f0e5017bfef5d061d1a75685f98734b6a04` | `sha256:0f53129e7b49492f8a99f8316795895519a7b39f8b344ac6a2b05a07e32bf263` |

- 两次运行的 RS config digest 均为 `sha256:9b8c208dcfd40cde0b6c18f70e6523e1e4eec22cb02c523c3b5a917638014a9f`，28 个 RootFS DiffID 相同（§9.2）。
- image ID 是各节点 containerd 本机生成的 manifest digest，按仓库规则不用于跨节点/跨构建等价比较；identity 以 config digest + 全部 RootFS DiffID 为准。

### 9.4 校验器输出

`RESULT packages=4 failures=0`：

| 包 | SHA256 | 结果 |
| --- | --- | --- |
| `with-logics.tar.gz` | `6a562b07decf2ce23283ba555b5801eb81df4ec6ce3c0a110672110682ac867d` | 3 members，OK |
| `without-logics.tar.gz` | `1c4ab2bacd7665a1c9fbbc265eaadc0aa4e5af6f5f9d3bbd1ed415dfc4095972` | 2 members，OK |
| `missing-dbcfg.tar.gz` | `66ce688f656a618adcc57f556dd31bc86fceaade17336bb3d84764a3585518b1` | 拒绝 `UPLOAD_CLOSURE_INVALID`，OK |
| `long-path.tar.gz` | `8730309ab9586f512fab20b0eb380db1c29cbdf4e5e6b9c76544b21939010b88` | 3 members，OK |

校验器需要 `GATEWAY_BACKEND_DEPS_IMAGE=gateway-backend-deps:lock-578e079b762e`；脚本默认的 `lock-d054366c02fa` 与当前 tree 的 `--print-input` 不一致（见 §10）。校验器临时镜像运行后删除。

## 10. 偏差与未决事项

1. **未跑 04 权威门禁**：本轮是 05/07 调试运行；阶段退出仍需在 04 的 clean、已提交 worktree 上用权威入口完整运行，并把结果绑定到最终 HEAD。
2. **main 已前进**：候选只合入 `fd9e383d76`；本地 `main` 已是 `2d8b29d332`（vnext `fb92c475`）。若阶段退出要求最新 main，需要重新合并、重算 OpenAPI 原件并重跑受影响检查；否则路径核对只能对 `fd9e383d76` 成立。
3. **截图缺口**：§9 的时间质量/顺序卡片、完整禁用原因矩阵、D1–D3 真实数据参考没有专门截图；需要 owner/设计会话确认是否补齐。
4. **J1 step 7 来源断言缺口**：测试只断言 3 个异常项，没有断言 B 的来源 `EXPLAINED`；J2 step 3 已覆盖 `EXPLAINED`，J1 step 2 已覆盖 `NOT_APPLICABLE`。
5. **`baseline_to_initial.table_count` 未断言/未记录**：当前只能推断为 125，不能写成实测；需要在 t1 测试或 case log 中补记才能关闭。
6. **校验器默认依赖 tag 过期**：`validate-upload-package.sh` 默认 `lock-d054366c02fa`，当前 tree 需要 `lock-578e079b762e`；本轮用环境变量覆盖。建议设计会话决定更新默认或把“按 `--print-input` 自动取 tag”写进脚本。
7. **t1 的 `test.pmc` 是 0 字节占位**：`t1-v1/test.pmc` 为 0 字节；runner 只要求存在一个顶层 `.pmc`，后端 t1 接受该占位。若 §8.1 的本意是必须使用真实 pmc 内容，则本轮输入不满足该条件，记录为偏差；本轮按 t1 runner 的既有输入约定执行。
8. **时间质量/顺序异常仅 mock 覆盖**：合成输入没有 `saved_time`，真实旅程无法产生 `TIME_ABNORMAL_*`/`LAST_NOT_MAX`；这是构造限制，不是实现遗漏。
9. **FULL M1 无参考**：FE3a 只有 v1 参考；FULL 6.93 MiB 只报告，不比较。
10. **未推送**：按要求不 push；`fe-vnext` 分支和 `09351e42ad` 仍只在本地/节点。

**待 owner/设计会话确认**：§4.6 集合结论；截图缺口是否补齐；J1 step 7 来源断言和 t1 `baseline_to_initial.table_count` 是否要在退出前补；是否重新合并最新 main；04 权威门禁的窗口与范围。

## 11. SHA 回源核对

本文所有 64 位十六进制 SHA 均由命令输出复制，覆盖提交/tree、OpenAPI、日志、镜像 identity、截图和校验器输出。提交前运行：

```bash
python3 /home/dev/gdds-test-tmp/fe3c-verify-handoff.py docs/frontend-vnext/fe3c-handoff.md
```

脚本对每个 SHA 做“来源存在 + 值等于来源”的检查，而不是只查长度：

- 文件类 SHA：重新计算本地副本（日志、截图、OpenAPI、校验器输出、t1 截图）的 SHA256；
- Git 对象：`git rev-parse`/`git cat-file` 校验提交与 tree；
- 日志内值：确认该值出现在对应日志的原始行中；
- 表格中的“日志/截图 + SHA”组合：按路径逐对比较，防止把 A 的 SHA 贴到 B 上。

结果：`PASS 198 / FAIL 0`。脚本同时覆盖 64 位 SHA256 与 40 位 Git 对象 ID；对文件类值重算 SHA256，对日志/镜像值确认出现在对应日志原文，对日志路径+SHA、截图+宽度+SHA、校验器输出+包名+SHA 逐对比较。
