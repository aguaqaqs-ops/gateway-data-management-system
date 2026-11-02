# FE1 复审报告（第 1 轮）

- **复审对象：** 分支 `fe-vnext`，代码候选 `b54dd08f37e27db9387aa9c248f7e0f692c57804`（`frontend/` 树 `90a37284c3`）；
  handoff 提交 `918282218eb00d7d1128a3da9e31924c7db6ad3c`（只改 handoff，`frontend/` 树相同）。
- **范围：** `c1a76ea345..918282218e`，共四个提交：`be430b9d98`（首个修复）、`6949ffcb45`（handoff）、`b54dd08f37`（补充修复：后端三类行记录）、`918282218e`（handoff）。
- **依据：** [FE1 审核报告](fe1-review.md) §4、§7；kickoff §4.4、§7；BE-b §4.7（`80de06ab5c`、`0e0d14f1d1`）。
- **日期：** 2026-11-02。
- **结论：定向修复。** B1、B2、B3 均已修复，并经独立复现确认；所选 N 项也都已落实。
  但复审中新发现一项阻塞（B4）：视图模型中的行变更类型和行风险标注，用的是前端自造的字段形状，与后端产物不一致。
  这和 B1 是同一类问题，只是出现在 bundle 安装之后的一层。修复范围很小，复审第 2 轮只看这部分 diff，之后在 04 取证。

## 1. 范围

`c1a76ea345..918282218e` 只改动了 `frontend/`（39 个文件）、`.gitignore`（新增一行 `frontend/src/test/fixtures/generated/`，即 N7）和 `docs/frontend-vnext/fe1-handoff.md`。
`vnext/`、AGENTS、kickoff、UI 优化方向、草图和 `docs/backend-vnext/` 均未改动；`vnext/` 树在 `c1a76ea345`、候选和 main `0e0d14f1d1` 上都是 `2791d3ff3d`。
`package.json`、`package-lock.json`、tsconfig 和 `run-tests.sh` 未改动。**通过。**

## 2. 原阻塞项核对

### B1 bundle manifest 形状与后端产出的 fixture：已修复

- **前端按后端形状校验：**
  - `posix-tar.ts` 中的 manifest 类型改为 `closure: { entries }`；
  - `closure_manifest_digest` 改为按 `sha256(JCS(manifest.closure))` 校验；
  - 安装、缓存（`local-bundle.ts`）、展示和 e2e 都改为读取 `closure.entries`。
  - 与后端 `_digest.py` 的 `closure_semantic_payload`、`manifest_semantic_payload` 逐项对照，一致。
- **fixture 由后端代码产出：**
  - `frontend/scripts/generate-backend-bundle-fixture.py` 用后端生产代码生成全部产物：
    `parse_sql` → snapshot materialization → `run_preview_pair_pipeline` → `surface_artifact_closure` → `assemble_bundle`；
  - 手写的 surface、risk、golden 副本和 Parquet fixture 已全部删除；
  - 唯一的手写输入是 `business-navigation.json`，因为 BE-b 还没落地。它由后端 JCS 规范化，作为 projection 挂入 surface，并重算 surface digest；
  - `build-golden-bundle-fixture.mjs` 只负责读取后端产物、校验顺序和摘要，再封装成 tar，不改写字节。
- **独立复现（05）：**
  - 用同一后端依赖镜像，在 network none 下只读挂载候选的 `vnext/` 运行生成器；
  - 输出的 11 个文件与提交的 fixture **逐字节相同**；
  - `bundle_digest` 为 `sha256:a34e8560…4538`，`closure_manifest_digest` 为 `sha256:db3dec9c…7b5e`，与 handoff 一致。
- **跨实现摘要测试：** 唯一 owner 是 `backend-fixture.test.ts`。它用后端 manifest/closure 跑前端校验器，安装 tar，从本地读取两侧 Parquet，并检查三类 records。
- **变异探针：** 在一次性 worktree 中把 closure 摘要改回旧算法 `{ entries: manifest.closure }`，然后运行 runner：
  - exit 1，10 项测试失败，其中包括跨实现测试，报错“closure manifest 摘要不匹配”；
  - 说明测试确实能发现前后端算法不一致，不是自证；
  - 探针 worktree 用后已删除（05 仓库中留下一个无引用的探针提交 `591cda2f4f`，没有 ref，会被 gc）。
- **补充修复：** 后端 fixture 现在包含 `ROW_ADDED`、`ROW_DELETED`、`ROW_MODIFIED` 各一条记录；`parquet-reader.test.ts` 也核对了修改前后的值。
  首个修复候选在 05 上 exit 1，原因是旧测试仍断言 records 数量为 3，而当时后端 fixture 只有 1 条。05 是调试节点，实施会话按规则停止并保留了日志，处理正确。

### B2 审核比较起点：已修复

- `runReviewHistoryJourney` 在 History 中找到唯一的提交节点，用它的 `parent` 作为比较起点；找不到节点或 `parent` 时明确报错（`journeys.ts:162-165`）。
- `listHistory` 跟随 `next_cursor` 取完所有页，遇到空或重复游标时报错（同时处理了 N5）。
- 测试覆盖了这些情形：head 已推进到 `baseline-2`、提交带 `NOT_CANDIDATE_BASE_ADVANCED` 时比较 `baseline-1 → submission-1`；找不到节点；没有 `parent`；两页分页。

### B3 token 与风险文案：已修复

- 强调色 `#1F5FBF`、悬停 `#174A96`、浅底 `#E9F0FB`；文字 `#1B2229`、`#5F6B78`、`#4A5563`；边框 `#DDE2E7`、`#C9D0D8`；字体族与草图相同。
  `frontend/src` 中除 `tokens.css` 外，没有写死的颜色。
- **页面底色：** 实施会话用了 `#F3F5F7`，这是对的。所有草图都是 `body{background:#F3F5F7}`。
  **审核报告勘误：** 原报告 B3 把 `#EEF1F4` 列为页面底色，这是错的。草图中 `#EEF1F4` 有 133 处用作行或区块分隔线，只有 2 处用作背景。
- 风险徽章文案改为“中高风险”“中低风险”。

### N 项

| 项 | 结果 |
| --- | --- |
| N3 | Preview 结果须与本次的 `operation_id`、`upload_revision_id` 一致，否则报错且不下载；有参数化测试 |
| N5 | 已随 B2 处理 |
| N7 | `.gitignore` 已加入生成目录 |
| N8 | `Dialog` 改用 `useId` |
| N9 | handoff 中第 4 个 DiffID 已更正；镜像身份改由 `docker-save-image-identity.py` 导出 |
| N1、N2、N4、N6 | 留到 FE2，见 §5 |

## 3. 新发现

### 阻塞

**B4. 行变更类型和行风险标注与后端产物不一致，行风险在真实数据上永远匹配不到**

- **位置：**
  - `frontend/src/features/view-model/model.ts:261-265`：`RiskAnnotation` 定义为顶层的 `{ row_identity, risk_level }`；
  - `model.ts:77`：`RiskReport.annotations` 也是同样的形状；
  - `model.ts:274-284`：`identityKey` 和 `deriveChangeLocations`；
  - `model.ts:282`、`:297`：用 `"UNCHANGED"`、`"UNCHANGED_RANGE"` 判断“未变化”；
  - 测试 `model.test.ts:67-77` 用的是自造的 `record_kind: "UPDATED"`、`"UNCHANGED"` 和顶层 `row_identity`；
  - `features/bundle/presentation.ts`：没有读取单表风险标注的路径，只读取了可选的 `risk_report_ref`（在后端 fixture 中为 `null`）。
- **后端事实：** 05 探针日志 `records-annotation-identity-probe.log`，读取的是候选中后端产出的 fixture。
  - **records：** `row_identity` 是 `fixed_size_binary[32]`；`record_kind` 取值见 `ComparisonRecordKind`，即 `ROW_ADDED`、`ROW_DELETED`、`ROW_MODIFIED`、`SCHEMA_CHANGE`、`TABLE_DEGRADED`。有序表另有 `OrderedRecordKind`，如 `ORDERED_ROW_MOVED`、`ORDERED_TABLE_DEGRADED` 等。
    后端没有 `UNCHANGED`、`UNCHANGED_RANGE`、`UPDATED` 这几种 record kind。`UPDATED` 是表级的 `SurfaceChangeKind`。
  - **风险标注**（`risk_refs.annotation_ref`，`annotations.bin`）：结构是 `{ annotations: [{ annotation_id, risk_level, reasons, diagnostics, target: { target_type, row_identity: "sha256:<hex>", … } }] }`。
    行标识放在 `target` 下，而且带 `sha256:` 前缀。
- **失败场景：**
  - FE2 接上变更定位和行风险之后，`annotation.row_identity` 永远是 `undefined`，风险 Map 只有一个 `null` 键；records 一侧算出的键是不带前缀的 hex。
    结果是每一处变更的风险都显示为空，“只看有风险的行”筛选出来也是空的，审核人看不到后端已经标出的中高风险行。
  - 表级记录 `SCHEMA_CHANGE`、`TABLE_DEGRADED` 会被算作“第 N 处行变更”。
  - 现有测试用自造的数据，所以都能通过。后端 fixture 里已经有 3 条 records 和对应的 3 条标注（1 条中高、2 条中低），足以暴露这个问题。
- **为什么阻塞：** handoff 声明 FE1 已完成“变更定位、行风险”。kickoff §7 的 FE1 退出条件 A 要求视图模型完成，并且用 golden bundle 覆盖数据流。
  FE2 会直接在这些函数上搭界面，如果形状错误被带进 FE2，返工面会比现在大。
- **建议修复：**
  1. 按后端定义 `RiskAnnotation`（`target.target_type`、`target.row_identity`、`risk_level`）；只有 `target_type === "ROW"` 的标注才进入行风险 Map。
     统一行标识的编码，例如 records 的 32 字节一律转为 `sha256:<hex>` 后再比较。
  2. 在 `presentation.ts` 中加入从本地 bundle 读取单表风险标注的路径：按 surface 表的 `risk_refs.annotation_ref` 在 closure 中定位，只读本地文件。
  3. record kind 按后端两个枚举处理：行级记录进入变更定位，表级记录（`SCHEMA_CHANGE`、`TABLE_DEGRADED`、`ORDERED_TABLE_DEGRADED`）不进入；删除自造的 `UNCHANGED`、`UNCHANGED_RANGE`。
     `filterChangedRows` 的 `changeKinds` 要写明使用哪套取值。
  4. 测试：把 `model.test.ts` 中这个用例改为由后端 fixture 驱动，从本地读 records 和标注，断言三处变更依次是 `ROW_ADDED`/中低、`ROW_DELETED`/中低、`ROW_MODIFIED`/中高。
     这个用例是“行风险与变更定位对齐后端”这一不变量的唯一 owner。
  5. 顺带检查 `model.ts` 中其余直接解析后端产物的接口（`RowDiffRecord` 的 `before_values`/`current_values`、`SurfaceTable`、`RiskReport`），以后端 fixture 的实际字段为准。不需要逐项加测试。

### 非阻塞

**R1. `theme.test.ts` 新加的 4 条断言是自比较**（`theme.test.ts:39-42`）
这几条断言拿测试内部的常量和它自己比，并没有读取 `tokens.css`。建议删除，颜色由 FE2 截图验收把关；如果要保留，就从 `tokens.css` 读取后再断言。

**R2. handoff 中“完成情况”和“本地 bundle fixture”两节已经过时**（`fe1-handoff.md` 的“本地 bundle fixture”一节）
这两节仍然描述已删除的手写 fixture、PyArrow Parquet 和旧摘要 `c108ea2c…`，导航 diagnostics 的说法也早于 BE-b §4.7。
04 取证更新 handoff 时，请把这两节标为历史记录，或改为指向“FE1 补充修复”一节。

**R3. 带入 FE2 的事项：**
- token 中没有草图的行分隔色 `#EEF1F4`，做 FE2 表格时补上；
- `business-navigation.json` 仍然带内联 `diagnostics: []`，FE2 按 BE-b §4.7 改为单独的 `diagnostics_ref` 产物，并去掉过渡用的 `diagnosticText`。

## 4. 复跑与证据

- **源码传输：** 在开发主机执行 `git bundle create … ^0e0d14f1d1 fe-vnext`，bundle SHA256 为 `976685b9fdc610964d2d057de7d9a53b2089978a1b991c98ce27e84d7a655cd0`，两端一致。
  05 verify 并 fetch 后，`FETCH_HEAD` 等于候选；05 的 main 停在 `0e0d14f1d1` 未移动。
- **05 worktree：** `/home/dev/gdds-fe-rereview1-fe1-91828221-05`，detached，clean，已建 `legacy` 符号链接。运行前确认占用标记不存在。
- **环境变量：** 与 FE1 审核相同，缓存使用 `fe0` 路径，来源提交 `a2fb4a027a`。

日志在 05 的 `/home/dev/gdds-fe-logs/fe1/rereview-1/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| worktree 准备 `rereview-setup.log` | 15:28:40 | HEAD `918282218e`、`frontend/` 树 `90a37284c3`、clean（末尾 `exit=2` 是“占用标记不存在”的 `ls` 返回值，符合预期） | `9429bbf221722425045734ef1f60b2681a178f9ae0749c44d4e760c7404e273b` |
| `run-tests.sh --e2e` `frontend-tests-20261102T152913Z.log` | 15:29:13–15:29:26 | **exit 0**；HEAD 和树起止不变；9 个文件 38 项单测通过；build 通过；e2e 3 passed；fixture 摘要和 tar SHA256（`df9f9127…4735`）与 handoff 一致；运行后 clean | `80fb65c895587d381e115e4eaffdcc680561b82388fb136a5a9251e1027172f3` |
| 后端 fixture 重新生成 `backend-fixture-regen-2.log` | 15:30:08–15:30:10 | 生成器 exit 0；`diff -r` 结果为逐字节相同 | `5a2aa138a02c4d46231836251349dbfbcbb7a7ae49d162b4d0e37be9dc881cbe` |
| 摘要算法变异探针 `closure-digest-mutation-probe.log` | 15:30:35–15:30:45 | 探针 exit 1（符合预期），10 项测试失败 | `d11674c8de670054df3e0d380e1a67d2364149f05fc6ec69b23cc7ee5d0a3d28` |
| records 与标注身份探针 `records-annotation-identity-probe.log` | 15:34:11–15:34:12 | 用于 B4 | `d66ff573d15414597b5931a0f6f6f74b2551a22f55fdd2b9538ee78c5edb7623` |

- **我的操作错误：** 第一次重新生成时，我用了 `python -I`，它会忽略 `PYTHONPATH`，结果 import 失败，生成器没有运行，没有任何输出。
  失败日志保留为 `backend-fixture-regen-fail-python-I.log`（SHA256 `d08538ddf136dcdcff4e0fe5c855b9b2fe3215639d4ab79e304387ad1149f46e`）。改用 `-P` 后重做一次，结果见上表。
- **后端依赖镜像身份：**
  - `gateway-backend-deps:lock-d054366c02fa` 在 05 上的 19 个 RootFS DiffID 与 handoff 逐项一致；
  - 05 的 `backend-image-identity-ct05.log` 记录了 `docker save` 导出的 config digest `sha256:b5b54224…b92a`，并与 CT201 的身份 JSON 比对一致；
  - CT201 的 `backend-image-identity-ct201-owner.json` 中，config digest 与 19 个 DiffID 都和 handoff 一致；
  - 没有比较 inspect ID。
- **handoff 日志：** fix1 和 fix2 两节引用的 33 份日志，我在开发主机（即 CT201）和 05 上逐一重算了 SHA256，全部一致。
  `dc68-operations-summary.log` 是 FE1 原轮的同一文件，上次审核已核对。
  `backend-image-identity-ct05.log` 文末记录的 SHA256 是关闭前算的，与最终文件不同；handoff 已说明 sidecar 改用最终摘要，这种处理可以接受。
- **DC68 与 owner 授权：** 镜像身份解析两次失败后，实施会话停止并交给 owner，owner 授权从头重做；预检路径写错、bundle 前置祖先选错，都是在触及被测对象之前的命令错误，各重做一次。处理都符合 DC68。

## 5. 带入 FE2 的事项

N1（按用户意图复用幂等 key）、N2（轮询超时不判为失败，临时错误有上限地重试）、N4（缓存读取时重算摘要）、N6（应用 tsconfig 去掉 Node 类型）按约定留到 FE2。
其中 N1、N2 要在 FE2 接入按钮和进度界面之前完成。FE2 审核时还会一并核对 R3 和 BE-b §4.7 的文案表。

## 6. 复审第 2 轮范围

复审对象为 `918282218e..<修复候选>`，核对内容：

1. **B4：** 标注形状和行标识编码按后端处理；presentation 能从本地读取单表风险标注；record kind 按后端枚举分为行级和表级；由后端 fixture 驱动的变更定位与行风险测试存在，并且实际通过。
2. R1、R2 的处理（可选）。
3. 05 上用 `run-tests.sh --e2e` 复跑。通过后在 04 做一次阶段退出取证，取证提交只改 handoff，由审核会话做证据核对。

本轮不需要改后端 fixture。如果因为 B4 需要改 fixture，就用同一生成脚本和镜像重新生成，并在 handoff 中记录新的摘要。
