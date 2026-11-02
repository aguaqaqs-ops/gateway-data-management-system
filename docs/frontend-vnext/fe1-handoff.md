# FE1 handoff（04 取证完成，待证据核对）

> FE1 独立复审第 2 轮已通过。原候选 `b67da4795fd22afcab1365f4138b131ab4c736d1` 的 04 运行仅作为历史记录；本次对代码候选 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de` 的 04 权威 runner exit code 为 0，现待审核会话核对证据。来源 handoff 提交为 `7732c4140e6c60570c7fe4ea2c806e436e44ac9a`，其 `frontend/` tree 与代码候选相同。本提交只更新 handoff。

## 初始候选与范围（历史记录）

- 起点：`36047efe5acca90c08acb95796c58c5b4cea33a3`。`fe-vnext` 已从该 main 提交快进；审核范围为 `36047efe5acca90c08acb95796c58c5b4cea33a3..b67da4795fd22afcab1365f4138b131ab4c736d1`。
- FE1 代码候选：`b67da4795fd22afcab1365f4138b131ab4c736d1`。其 `frontend/` tree 为 `3fdda26532349af4db6dbeb9628be87d7f7a748e`。
- 候选由 9 个 FE1 提交组成，所有产品与测试代码改动都在 `frontend/`。本 handoff 在阶段取证完成后作为单独文档提交；最终文档提交 HEAD 由实施会话完成后回报。
- `frontend/package.json` 的 `test:unit` 去掉了 `--passWithNoTests`（N1），并在运行 Vitest 前生成本地 golden tar。依赖版本没有变化，`package-lock.json` 未改。
- `frontend/scripts/run-tests.sh` 记录 `frontend_tree_start` 与 `frontend_tree_end`（R2）。runner 日志中的 `tracked_frontend_archive_sha256` 是各自提交的输入摘要，不跨提交比较。
- 开发主工作区 `/home/dev/gateway-data-management-system` clean，HEAD 为 `36047efe5acca90c08acb95796c58c5b4cea33a3`。`/home/dev/gdds-fe` 在代码候选时 clean，分支 `fe-vnext`。

## 完成情况（原 FE1 候选摘要）

> 本节记录 B4 复审发现前的 FE1 完成情况摘要。行风险与行变更定位已在文末“FE1 补充修复：行风险与行变更定位（B4）”按后端产物修正；bundle fixture 的当前来源和摘要也以该节为准。

### A：功能层

- 统一 Bearer 认证 fetch、OpenAPI 快照类型客户端、标准 API 错误；请求携带幂等 key、预期工作区/审核/基线版本。
- 提供 operation 轮询、超时、取消与失败诊断；实现 Preview 上传、dataset replacement、提交、审核、归档、History 比较等模拟接口旅程。
- Review 输入只允许 `APPROVE`、`REJECT`、`WITHDRAW`。快照中遗留的 `RETURNED_FOR_REVISION` 响应在客户端映射为 `REJECTED`，前端不暴露退回操作或独立状态入口；拒绝时要求理由。
- 审核浏览从基线节点到待审提交创建 History 比较并下载 History bundle，不读取 Preview bundle。
- bundle 使用 kickoff §4.4 约定的流式、不压缩 POSIX tar：先 manifest、再 `artifact-closure.json`，之后按 closure 顺序读取 `logical_path` 成员；支持 pax 长路径。校验 ETag、Content-Length、manifest/closure 摘要、成员顺序与各产物 SHA-256；截断或完整性错误会清理本地副本并重新下载一次。
- 下载流按块写入 OPFS，不缓存整包于内存；按 bundle 摘要建本地缓存。表格打开时才从本地读取对应 Parquet；浏览路径不含后端取数接口。已缓存 bundle 的表文件在读取时再次核验摘要，元数据损坏时清除缓存并重新下载。
- 视图模型按 BE-b §4 的 `groups/items/tabs/row_filter/facts` 通用结构推导，未知组名可渲染；整表页签使用 surface/RiskReport，筛选页签使用自身 `facts`，未认领表进入 `OTHER_TABLES`。导航 diagnostics 会保留为可读文本。
- 本地实现筛选、变更定位、行风险、Preview/History 公式展示以及 URL 状态和只读 UI 命令。BE-b 落地前，Preview 公式有变化的测点只显示上传侧公式并标“公式已改”；History 显示前后对照。

### B：设计系统

- 建立颜色、字号、间距、圆角、阴影、字体 token。表格主题运行时从同一 CSS token 读取字体、颜色与尺寸；文本类 ID/hash 使用等宽字体。
- 提供主要、次要、幽灵、危险四档按钮，应用内对话框与焦点捕获/还原，焦点可见样式，表格主题、风险五级色与中性差异样式。
- 组件预览覆盖禁用原因、已选目录、进度阶段、骨架屏、错误恢复和确认对话框；lucide 图标随前端本地打包。
- UI 优化方向 P1、P2 的预览条目已落地。正式工作台与差异浏览页面、截图验收属于 FE2。

### 本地 bundle fixture（历史记录，已被后端 fixture 取代）

> 本节仅记录最初候选曾使用的手写 JSON、PyArrow Parquet 和旧摘要 `sha256:c108ea2c…`。这些文件和路径已删除，不是当前 fixture；当前唯一 fixture 是下文“FE1 补充修复：后端三类行记录”中的后端生成产物，当前摘要为 `sha256:a34e8560…`。导航占位 JSON 仍是唯一手写的业务产物。

由于当前后端 `/bundle` 只返回 manifest，按 owner 2026-11-02 决定，FE1 未依赖该响应。`frontend/scripts/build-golden-bundle-fixture.mjs` 在本地拼装 `manifest.json`、`artifact-closure.json` 与 closure 产物，输出符合 §4.4 的 tar；unit runner 生成文件，不把产物 tar 提交进 Git。Playwright 通过模拟接口返回此 fixture，不连接真实 backend。

fixture 来源：

- 导航、surface、风险 JSON：`frontend/src/test/fixtures/source/business-navigation.json`、`comparison-surface.json`、`risk-report.json`。业务导航占位数据按 BE-b 草案 §4 构造。
- Golden 输入副本：`frontend/src/test/fixtures/source/golden/bundle/snapshot-table-bindings.json`、`golden/surface/table-presentation.json`、`golden/risk/structural-risk.json`，分别来自仓库中的 bundle、surface、risk golden；生成脚本校验其中的固定案例。
- 三份 Parquet fixture 由 PyArrow 25.0.0 生成：`device.before.parquet` SHA256 `9dd60574805efe4d3f6107b5c5677da57776b6115fb276aeb4a8ab714654564c`；`device.current.parquet` SHA256 `bae530bc52f07e7ddc40e981887000cf8c4359ded44fec6590e8d0d56a480a8b`；`device.records.parquet` SHA256 `64ffcb93f978edbc7d70858f07aaa1815f3f4130b5b87e4c50a03170a4d306f4`。
- 本轮生成的 tar 为 41,472 bytes，fixture bundle digest `sha256:c108ea2c24a8d9d8ef5f851693292e2b6715aba1c3b6d205e3d6cd7c7f45be8c`，tar SHA256 `c280e4d1a6d52769f40cc577f8b08de7fe7464544ecf617e035d95d84095a090`。此 tar 是测试时生成的临时输入。

## 05 调试与 04 阶段退出取证

两节点沿用 FE0 预填充的 `mcr.microsoft.com/playwright:v1.64.1-noble`。config digest 为 `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；七个 RootFS DiffID 均与 FE0 handoff 及 runner 记录相同：

1. `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
2. `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
3. `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

npm 缓存沿用 FE0 预填充，归档 SHA256 为 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。缓存实际生成于提交 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4`；该提交的 `package.json` 与 `package-lock.json` blob 和 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 相同。按 R1，两个 runner 均记录 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`，lockfile 有 305 个 resolved 项。05 使用 `/home/dev/gdds-fe-cache/fe0/npm-cache`，04 使用默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cache`；均未重新传输或覆盖缓存。

| 节点 | worktree | 起止时间（UTC） | HEAD（起→止） | frontend tree（起→止） | runner exit | runner 日志与 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| `gw-dms-test-05.lan` | `/home/dev/gdds-fe-fe1-b67da4795f-05` | `2026-11-02 12:56:01–12:56:14` | `b67da4795fd22afcab1365f4138b131ab4c736d1` → 同 | `3fdda26532349af4db6dbeb9628be87d7f7a748e` → 同 | `0` | `/home/dev/gdds-fe-logs/fe1/frontend-tests-20261102T125601Z.log`；`76698b095667c3b8f48169f508b883a03c7a132fd35bfb47baba1f0a7c53a563` |
| `gw-dms-test-04.lan` | `/home/dev/gdds-fe-fe1-exit-04` | `2026-11-02 12:57:42–12:57:58` | `b67da4795fd22afcab1365f4138b131ab4c736d1` → 同 | `3fdda26532349af4db6dbeb9628be87d7f7a748e` → 同 | `0` | `/home/dev/gdds-fe-logs/fe1/frontend-tests-20261102T125742Z.log`；`af5f9eaf829ee50748f913439f79e5cb7bc76d042a132d015c835fcbe0470f46` |

两次运行均为完整 `./frontend/scripts/run-tests.sh --e2e`，`docker_network=none`；typecheck、lint、8 个 Vitest 文件的 32 项测试、build 均通过，Playwright 为 `3 passed`。E2E 包含 OPFS 安装、按本地文件读取 Parquet 和第二次打开命中缓存（未再次请求 fixture）。04 原候选权威 runner exit `0`，但该运行现仅作历史记录，因定向修复失效，待复审后重做。外层 wrapper SHA256：05 `a2cfde65a12b02dfff3c80618097f1cd50f86a00e10dc2702bab8c3a6167923e`；04 `5769920ca48310d47dd75611ae6719f5c208961954e8f8730541048251b4dad1`。本次 runner 记录的 `tracked_frontend_archive_sha256` 为 `a8dc558a005c6967864cd39f25a439d6df3d681e79554bfb6c83aa72a70fa749`，只作该提交的输入记录，不跨提交比较。

### 预检、源码传输与 worktree 日志

- 05 预检：SSH 成功、hostname `gw-dms-test-05.lan`、busy 标记不存在、共享 main 为 `14ea5e8e89d5ffec3104fc1741376534acef5e7e`、镜像与缓存存在且摘要匹配。日志 `/home/dev/gdds-fe-logs/fe1/preflight-05-b67da4795f.log`，SHA256 `cba8af5234dc1e96877cfd760b5251858178453afc742eea1285fbac195c8b70`。
- 04 预检：SSH 成功、hostname `gw-dms-test-04.lan`、busy 标记不存在、共享 main 为 `14ea5e8e89d5ffec3104fc1741376534acef5e7e`、默认 npm cache 与镜像存在且身份匹配。日志 `/home/dev/gdds-fe-logs/fe1/preflight-04-b67da4795f.log`，SHA256 `85fc76dcbda3ff6d739e26f83135cd8f0047717cd67a982c8180bc3ee61788e0`；04 runner 前置检查日志 SHA256 `35be53775517e2b8af822d2c564475f6ffb72baa7a7084e6c11ba09c39027c53`。
- CT201 上创建 bundle 前确认分支 HEAD 为候选、tree 为 `3fdda26532349af4db6dbeb9628be87d7f7a748e`、worktree clean；以 05/04 已有祖先 `14ea5e8e89d5ffec3104fc1741376534acef5e7e` 为 bundle prerequisite。bundle SHA256 `109044709f21418dad58e322bd8261446285b4a2cdd2cfab6d939570338584d1`。创建/verify 日志 `/home/dev/gdds-fe-logs/fe1/source-bundle-create-b67da4795f.log`，SHA256 `ccba3b3e2055c6043d5c603d8726974fb1d1e4705b4e792549e7aca2fcf06ca6`。
- CT201→05 传输前后 SHA 均为上述 bundle SHA；最终传输日志 `/home/dev/gdds-fe-logs/fe1/source-bundle-transfer-05-b67da4795f-retry-1.log`，SHA256 `5aa6539ac674a9ee7b23f17ef3e7e8c459a8cfe7cced945a8140c981b6d5e20d`。
- 05 bundle verify/fetch 后 `FETCH_HEAD` 精确为候选，main 保持 `14ea5e8e89d5ffec3104fc1741376534acef5e7e`。最终日志 `/home/dev/gdds-fe-logs/fe1/bundle-fetch-05-b67da4795f-retry-1.log`，SHA256 `740fc4bb3d90f43fe1c5b1dae67f5f51eaf6992425d0276e679d02e25f7f6d25`。worktree 创建日志 `/home/dev/gdds-fe-logs/fe1/worktree-add-05-b67da4795f.log`，SHA256 `98612a76fd60be5e7c0c48a6ae569685f9e05e2991502f2e8d6962fb0882bf87`。
- CT201→04 传输前后 SHA 同为 bundle SHA；传输日志 `/home/dev/gdds-fe-logs/fe1/source-bundle-transfer-04-b67da4795f.log`，SHA256 `4d4494bd0074457e181069512565605b35b2fda7e6951b263a8b94640c95f0c0`。04 verify/fetch 后 `FETCH_HEAD` 精确为候选，main 保持原值；日志 `/home/dev/gdds-fe-logs/fe1/bundle-fetch-04-b67da4795f.log`，SHA256 `47c47359f1c9d74a5e12c610ee95a3ef600bd796bd86ef6cb276644ba1e9245a`。worktree 创建日志 `/home/dev/gdds-fe-logs/fe1/worktree-add-04-b67da4795f.log`，SHA256 `613f9cd1a5ae74a9173c739b30a03f21db5dac9392b8ac81330b0bc21c7c487d`。
- 两个 worktree 都以 `git worktree add --detach` 建立并链接共享 `legacy/`；运行前后 HEAD 不变且 `git status --porcelain --untracked-files=all` 为空。

### 05 调试失败与修正

以下为收敛期间的 05 调试日志，不是阶段退出证据；最终证据是上表 `b67da4795f` 的 05/04 运行。

| 日志 | SHA256 / exit | 发现与修正 |
| --- | --- | --- |
| `frontend-tests-20261102T123552Z.log` | `98e916e885490cb886a76951c05357f1700fde8e2706f6354d1488f79fb8c328` / `2` | typecheck 错误：未使用 decoder、隐式 any、OPFS 目录类型、Node 类型与 fixture 字段；在 `b0b6173a3a` 修正。 |
| `frontend-tests-20261102T123717Z.log` | `4401ebe41994302635cc2b2188694977123e9b93af8de90e351feb5c63ad6002` / `1` | lint 报无用赋值；在 `749bb729cd` 修正。 |
| `frontend-tests-20261102T123812Z.log` | `399b2032af168d27ecdcfc813a264dc79da1dd4091d846d8cab991148e2221ec` / `1` | jsdom 文件 URL 读取问题与搜索用例匹配过宽；在 `310bfe1fcf` 修正。 |
| `frontend-tests-20261102T124008Z.log` | `69ca587060655dd6d836d0a81853d8abc8853e98b373732ec9280eef40b7e63c` / `1` | jsdom Blob 没有 `.stream()`；在 `b9236ce8c6` 使用 Node web streams fixture helper。 |
| `frontend-tests-20261102T124123Z.log` | `26bf8512d9f7f08e74fc64bc6fe6682deee0b56fd54748689b2d439d91cbadf9` / `2` | Node 与 DOM ReadableStream 类型不一致；在 `cf30a90253` 修正边界类型。 |
| `frontend-tests-20261102T124207Z.log` | `6add4a6803d53ced100b009a3f639ea49bab954e4d2a03f83c5d6a3c3caed739` / `1` | bundle digest 只在左侧去除 `sha256:`；在 `6e09db238f` 统一摘要比较。 |
| `frontend-tests-20261102T124314Z.log` | `7a35f5ba6f734252885fe06f9f644aa937a9263a10ba303c076b290939a91ca8` / `1` | Parquet INT64 读取为 bigint；在 `0571cb948e` 修正断言。 |

### DC68 命令错误与重做

每项均发生在 runner/容器启动之前；失败日志及 SHA 已保留。统一记录 `/home/dev/gdds-fe-logs/fe1/dc68-operations-summary.log`，SHA256 `d5e2bc0ac0fe2654dcc1b66dcc862e507f3f19242a52c2c26c9759beb26984f5`。

1. 首次 bundle create 参数顺序错误，Git 报 `Refusing to create empty bundle`，exit `128`。失败日志 `/home/dev/gdds-fe-logs/fe1/preflight/candidate-bundle-create-attempt-1.failed.log`，SHA256 `6f0f2f70c1a9def90eee5c9c7580b00afd6a50426b21a2865e43cd7de85e129d`。从创建步骤开头改为 `git bundle create <path> ^<base> fe-vnext` 后成功；重做日志 SHA256 `a2846098b7fe82f9cc6d05207102f3f79f2a5f01ce57286f38b467b5b41e33eb`。
2. 先前 CT201→05 的传输完成，但接收端 checksum collector 的 awk quoting 错误，未记录收到端 SHA。保留错误日志 `/home/dev/gdds-fe-logs/fe1/preflight/source-bundle-transfer-dc68.log`（SHA256 `7601dc5cab73bf9f8d7ae42d8e0174e721cd3da5e1f6ecdd1414b35f0d605c07`）和 05 失败日志 `/home/dev/gdds-fe-logs/fe1/source-bundle-transfer-05-attempt-1.failed.log`（SHA256 `a4467ee64b7ca9ef1fb1a7b090b2043e76dfc481beb2df058ae8351403fdaae0`）；重做时从传输开始并以 cut 获取两端 SHA，结果相同，日志 SHA256 `b2cd440bc8704a077e2b75076b74ee0e1edfdd15cdf9913038e97a6c9d28dd8b`。
3. 本轮候选的 CT201→05 传输也遇到 checksum collector awk quoting 错误。失败日志 `/home/dev/gdds-fe-logs/fe1/source-bundle-transfer-05-b67da4795f.log`，SHA256 `2e5a6251010d955a16518d676377ee0ce621e8e8e8e5b0fbe644cf0a5667828e`；外层写了 exit `0`，但接收端 SHA 为空，因此该步骤未通过。按 DC68 从传输步骤开头重做，最终两端 SHA 均为 `109044709f21418dad58e322bd8261446285b4a2cdd2cfab6d939570338584d1`，重做日志 SHA256 `5aa6539ac674a9ee7b23f17ef3e7e8c459a8cfe7cced945a8140c981b6d5e20d`。
4. 首次 05 bundle fetch 后的保护检查错误地将 main 与上一条 reflog 比较，检测到历史值 `17cc76174ba04d3a97eb1a1ca343a86cef7bc805` 后停止；失败日志 SHA256 `9ace974c4b3479aae081fd2ff1520fa879ef5180908d87c4eb9d5a18674b57f2`。fetch 已把预期对象放入共享仓库并设置正确 `FETCH_HEAD`；main 未移动，未建 worktree、未运行容器。保留日志后从 bundle verify/fetch 步骤开头重做，改为比较该步骤实际记录的 main 前后值；候选精确匹配且 main 不变，重做日志 SHA256 `740fc4bb3d90f43fe1c5b1dae67f5f51eaf6992425d0276e679d02e25f7f6d25`。

## 偏差与设计问题

- **已确认的后端缺口：** 当前 `/bundle` 只返回 manifest。依 owner 2026-11-02 决定，BE-d 实现闭合 tar 传输；FE1 按 §4.4 本地 fixture 继续，不等待 BE-d。真实接口对接与 OpenAPI runtime 比较在 FE3。
- **阶段边界：** FE1 提供可复用数据层和 P1/P2 组件预览，没有实现正式页面；真实 backend e2e 和 1280/1920 截图验收分别按 kickoff 留给 FE3、FE2/FE4。
- **FD4 快照：** OpenAPI 快照仍包含 `RETURN_FOR_REVISION` 遗留值。FE1 不暴露其操作或状态入口；BE-a 合入后刷新快照，FE3 做运行时比对。
- **待 BE-b 明确：** BE-b 草案定义 `BusinessNavigation.diagnostics: [Diagnostic]`，但本轮读取的草案没有给 `Diagnostic` 字段结构。FE1 目前保留字符串，或从对象的 `code`/`message` 生成可读文本，其余对象序列化为 JSON。FE2 设计专门 diagnostics 展示前，建议由 BE-b Contract 定义稳定字段和用户文案映射。
- 除上述已排期事项外，没有发现需要 FE1 修改 `vnext/` 或后端行为的问题。

## FE0 worktree 收尾与节点状态

- 按 FE0 收尾要求检查 `/home/dev/gdds-fe-fe0-05`、`/home/dev/gdds-fe-fe0-fix1` 与 `/home/dev/gdds-fe-fe0-exit-04`：三个目录均已不存在，节点共享仓库的 `git worktree list` 也无对应登记。检查日志：05 `/home/dev/gdds-fe-logs/fe1/fe0-cleanup-precheck-05.log` SHA256 `5a34cf3e71d6922092e727604a71f066df0ddf8e7c7bae36e09244b9e53e4a7c`；04 `/home/dev/gdds-fe-logs/fe1/fe0-cleanup-precheck-04.log` SHA256 `3a41b47e489d4cb7ec655f9e2bfa6c89f20aaa6f1429b3bf0afbc5997e814e82`。
- 05 上 8 个已被替代的 FE1 调试 worktree 均 clean，逐一检查 `/proc` 后未发现进程引用，已移除；清理日志 `/home/dev/gdds-fe-logs/fe1/obsolete-fe1-worktree-cleanup-05.log`，SHA256 `e694bac4693f0663f85b98bc6ec035f2f6d8aeca26eb361b8b7fa28c4bddd4b0`。
- 保留最终 05 worktree `/home/dev/gdds-fe-fe1-b67da4795f-05` 与 04 阶段证据 worktree `/home/dev/gdds-fe-fe1-exit-04`，供独立审核核对。05 和 04 的共享 main 均保持 `14ea5e8e89d5ffec3104fc1741376534acef5e7e`；04 运行前后 main 未移动。
- 不推送、不打 tag、不合入 main。等待独立 FE1 审核。

## FE1 定向修复（首个修复候选的失败记录）

### 候选与修复项

- 本轮审核基线为 `c1a76ea345f3b183cc9b04a2e90d3f58257626d7`；修复代码提交为 `be430b9d98e8a31c676bfd8cd0136e893a7950d2`，审核范围 `c1a76ea345..<be430b9d98`，`frontend/` tree 为 `b5956f902ec9e6eec4c7fac17ea204d0a23c93bd`。代码提交只改 `frontend/` 和 `.gitignore` 中的前端生成 fixture 条目；`package.json`、`package-lock.json` 未改。
- **B1：** manifest 类型改为 `closure.entries`；校验器按 `sha256(JCS(manifest.closure))` 校验 closure 摘要，安装、缓存、展示和 Playwright 入口均读取该形状。加入后端产物的跨实现摘要唯一 owner 测试，并覆盖安装、导航、风险、两侧 Parquet 与 records 本地浏览。删除原手写 surface、risk、golden 与 Parquet fixture。POSIX tar 脚本只读取后端产物、校验 closure 顺序/路径/字节摘要并封装，不重写产物字节或摘要。
- **B2/N5：** `listHistory` 跟随 `next_cursor` 收集完整节点；审核比较要求找到唯一提交节点并用其 parent 到提交作为 History 输入，找不到节点或 parent 时明确报错。测试覆盖 History head 已推进且提交带 `NOT_CANDIDATE_BASE_ADVANCED` 的情形，以及缺少节点/parent 的错误路径。
- **B3：** token 更新为草图中实际承担角色的颜色；页面背景采用草图中的 `#F3F5F7`，`#F7F9FB` 用于浅色面板；焦点环同步强调色。字体使用 C7 离线字体栈，不引入字体文件或外链。风险 badge 文案改为“中高风险”“中低风险”。
- 同步完成 **N3**（校验 Preview 的 operation 与 upload revision）、**N7**（忽略 `frontend/src/test/fixtures/generated/`）、**N8**（Dialog 用 `useId` 生成标题/描述 ID）、**N9**（更正本 handoff 中工具链镜像第 4 个 DiffID，今后身份均由命令导出）。
- 建议项 **N1、N2、N4、N6** 未纳入本轮，留 FE2；D1 保持审核报告已有安排。

### 后端 fixture 来源、镜像身份与复现

- 在 CT201 `heavy-dev-01.lan` 使用后端生产代码生成 fixture。来源提交 `c1a76ea345f3b183cc9b04a2e90d3f58257626d7`，`vnext/` tree `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`，`vnext/backend/uv.lock` SHA256 `d18d89a24a8acae02eb6b3b23c342c1b673ea0e7e87add93d0762edfa18b822d`。候选与镜像内该 lock SHA 相同。
- 后端依赖镜像为 `gateway-backend-deps:lock-d054366c02fa`，归档 `/home/dev/gdds-fe-logs/fe1/fix1/backend-dependency-base-ct201.tar`，SHA256 `a9dc6673c1089724859ed1ea7b726af6219aa136dee8b59a5ad961c3d9e32720`。配置摘要 `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`；身份由 `frontend/scripts/docker-save-image-identity.py` 导出并在 CT05 再次比对。该脚本 SHA256 `c205c3c044d388ce7a75f36eb4d02ef209b4487ef4d2f39229d4abc98f179a45`。CT201 与 CT05 的 config digest 和全部 19 个 RootFS DiffID 相同：

  1. `sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a`
  2. `sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104`
  3. `sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15`
  4. `sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1`
  5. `sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a`
  6. `sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25`
  7. `sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588`
  8. `sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1`
  9. `sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1`
  10. `sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f`
  11. `sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6`
  12. `sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6`
  13. `sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce`
  14. `sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c`
  15. `sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3`
  16. `sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4`
  17. `sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814`
  18. `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
  19. `sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0`

- 生成脚本为 `frontend/scripts/generate-backend-bundle-fixture.py`（SHA256 `38e4ddf4f828d38279cb8c5298319ffca72fd85a994edeec37541696f6b0f4ef`）。固定的最小 SQL 输入经后端 `parse_sql`、snapshot materialization、comparison/surface/risk/records pipeline、`surface_artifact_closure` 与 `assemble_bundle` 生成 manifest、closure 和全部 JSON/Parquet 产物。容器 `--network none`；候选 `vnext/` 源码只读挂载；用镜像内 `/build/backend/.venv/bin/python` 执行脚本。可复现步骤为：准备空输出目录，将 `vnext/`、生成脚本和导航输入只读挂入该镜像，然后执行 `generate-backend-bundle-fixture.py --output-root <空目录> --navigation <business-navigation.json>`；同来源提交和镜像连续生成两次，输出逐字节相同。生成输入中的唯一手写产物为 `business-navigation.json`（SHA256 `18a73fe998e935a859bdb66984778fbd81fee1ebbba103d0b64a8231e5ba288c`），按 BE-b §4 构造并由后端 JCS canonicalize；surface、risk、records、bundle 及 Parquet 均来自后端代码。
- 两次最终生成日志：CT201 `/home/dev/gdds-fe-logs/fe1/fix1/backend-fixture-final-1.log` SHA256 `e098cb7f05843bd8c80529e327f6f93b6b1fd93827d967fa46bc5624ff2444fc`；`backend-fixture-final-2.log` SHA256 `5ffe18dc85f686f82c728a92da016aff449225712096a6367d1f0acdc1d015b5`。重现性比较日志 `backend-fixture-reproducibility.log` SHA256 `19c734dc356eea7026365dd71c7c8e702431af449c0e914ff3397bd4d9d885e2`，结果 `byte_identical=true`。
- 后端 fixture 摘要：`bundle_digest=sha256:0faaff406f53ceba674297b3f181d876fa3892713af5e7d39ae5bc3e1bed36b4`；`closure_manifest_digest=sha256:464b00fbdf91fd4df5a28cbdfff1f55ac359e1977ba61bb3f8874e8c1eb64b96`；`bundle_manifest_digest=sha256:0faaff406f53ceba674297b3f181d876fa3892713af5e7d39ae5bc3e1bed36b4`。manifest 与 9 个 closure 产品的 SHA256：

  | 产物 | SHA256 |
  | --- | --- |
  | `manifest.json` | `4d73e102a6a6b8d8eebde2f47af2be230867f46b0f02e213b1281028e88ada3c` |
  | `artifact-closure.json` | `4e8851c7572a8e9e5496be14702a0069d909b3f6ebbf3d2f0e1729988e200d0e` |
  | surface | `68ea395ba5f71f3cf9f212803f2b77cdbddc530d107bd0af5c782dcfad5dd910` |
  | records closure | `7484c6d5d3708de88555f060c8bff5c0d14b1fecc789b5270ecfc746f2023ab9` |
  | records manifest | `6eba34af6646abb6d06045a07a3c436a1724a74360e2c8a154477136576b0109` |
  | records Parquet (`rows.bin`) | `f1a91a369e431a0cca126a85162450cab42b2c7f03948610fb1a2109499232fb` |
  | business navigation projection | `36e72e4e0bbd3f461889fe5266bdfb10e208e416777fa924d8d47a7590a2a97c` |
  | risk annotations | `e9bf61595dedd09edc214a2a38c4724f45a2b1f20157bc9fadb7bf4fa38d7a2f` |
  | risk annotations manifest | `c203b50605cc6c30612d98bfbbbb113985ad5099a1740e91a5468c752bd10942` |
  | before snapshot Parquet | `df8e8db02d169544a0cd0210468f47bfb48a6fa52fd977e914204a8b9107a5cc` |
  | current snapshot Parquet | `30d03c90e74aa2864f2143445104162f6d569b6edd9b1759b28b8914022e37be` |

- 前端 POSIX tar 为 63,488 bytes，SHA256 `bf8ff95ab02870283716f722c2c6fad38a7ee6f9f0a91741ea98d027b4603271`；runner 实际生成的 bundle digest 与后端产物一致。

### CT05 源码、镜像与 runner 证据

| 步骤 | 节点/时间（UTC） | 结果与日志 SHA256 |
| --- | --- | --- |
| CT05 预检（重做） | `gw-dms-test-05.lan`，14:32:16–14:32:18 | SSH OK；busy 标记不存在；共享 main `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`；toolchain、缓存和 backend image 已有。`preflight-05-owner-retry-2.log` SHA256 `23e4c1a08853b3d61e078abcbda9d47ac1b2ec05425de795fcbdb3de35776fb5` |
| bundle 创建（重做） | CT201，14:33:09–14:33:10 | 以 CT05 main 的共同祖先 `36047efe5acca90c08acb95796c58c5b4cea33a3` 创建；bundle SHA256 `bcf022bb6e8bbbec8cc6c6cd0c828f09b5c51ef2f33875b983517730207f2f33`。`source-bundle-create-be430b9d98-retry.log` SHA256 `5f0a5024d5f059f0bdf3d221c6173a3109f5f7e0d99f83448667e0e3e787cb19` |
| bundle LAN 传输 | CT201→CT05，14:33:16–14:33:17 | 两端 bundle SHA256 均为上述值。`source-bundle-transfer-05-be430b9d98.log` SHA256 `62ce1befc22393809f8f20265ba4b82ac5cb4058dab697229e5677c37c3d253c` |
| CT05 bundle verify/fetch | 14:33:27 | `FETCH_HEAD=be430b9d98e8a31c676bfd8cd0136e893a7950d2`；main 前后均为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`。日志 `bundle-fetch-05-be430b9d98.log` SHA256 `ba84be30f1ecd18a5dbb40d106cbddbcfc8ff1563cb05940291b19720d7077f2` |
| detached worktree | CT05，14:33:36 | `/home/dev/gdds-fe-fe1-fix1-05`，HEAD/tree 精确匹配候选，legacy 链接已创建，status clean。日志 `worktree-add-05-be430b9d98.log` SHA256 `f82d8df5dba16a2b10b14da810cf9faa90809e6d12340a81d487aed1b9fa7118` |
| backend image 传输/load | CT201→CT05，14:33:59–14:34:46 | archive SHA256 `a9dc6673c1089724859ed1ea7b726af6219aa136dee8b59a5ad961c3d9e32720`，两端相同；`docker load` exit `0`。传输日志 `backend-image-transfer-05-owner.log` SHA256 `df8dd85767acac6859ff92f629c7acc8eea90e33cbd92c24a685f9a571168ecc`；load 日志 `backend-image-load-05.log` SHA256 `6abd257c7b549923d23428680ef5c1248916dace36bd3079517fac10387babe9` |
| CT05 image identity | 14:34:56–14:35:19 | 使用候选内同一解析脚本对 `docker save` 结果导出；与 CT201 身份 JSON 完全一致，config digest 和全部 19 DiffID 匹配。`backend-image-identity-ct05.log` SHA256 `d46d1602ff63f7c5411c6e6f9f6a7eff42684fcfc3d3efe8423957d0fb5993bc` |
| runner 前检 | CT05，14:36:03 | clean worktree、main 未移动、busy 标记不存在；Playwright 7 DiffID 和 npm archive SHA 匹配；lock resolved 数为 305。`runner-preflight-05-be430b9d98.log` SHA256 `5019205a45d6d63e20db79af4fc1318bc1817696597abd4a2b02829c008539b3` |
| 权威 runner | CT05，14:36:33–14:36:43 | `./frontend/scripts/run-tests.sh --e2e`，HEAD/tree 起止均为候选，`docker_network=none`，exit `1`。typecheck、lint 通过；Vitest 9 文件中 8 个通过、1 个失败，共 37 passed / 1 failed。跨实现测试 `backend-fixture.test.ts` 的 1 项通过。失败为 `parquet-reader.test.ts` 仍断言 records 数量为 3，后端 fixture 实际为 1 条 `ROW_ADDED`。runner 在单测失败后停止，build 和 e2e 未执行。日志 `/home/dev/gdds-fe-logs/fe1/fix1/frontend-tests-20261102T143633Z.log` SHA256 `4a89d3ab6733d5924de3d6457bb190bd7cfe7ae17ba6b35b22b6e023fa9dc676` |

CT05 runner 已启动且 exit 非零；按停止规则未重跑。失败后只读复核确认 worktree 仍 clean、HEAD/tree 未变，main 仍为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`。本轮未在 04 取证，也未修改代码来处理该失败；需要 owner 决定下一步。

### DC68 与 owner 授权重做记录

- **CT201 self-SSH：** `/home/dev/gdds-fe-logs/fe1/fix1/dc68-ct201-self-ssh-failure.log`，SHA256 `6e896d1dd0c537c0474404fd911cf732167aa569211ab86472e7a743c4fefed5`。CT201 是当前主机，SSH 到自身失败；后续改为本机检查，未触碰候选或容器。
- **首次镜像身份解析失败：** `backend-image-identity-ct201.log` SHA256 `5865f1dc1a2b91e619f79838ad5086d8d23478d2c041c23647de45df0f489472`，旧逻辑未找到 config；DC68 重做 `backend-image-identity-ct201-retry.log` SHA256 `eab69421a94b86c94309b5af13f3dd248134e5183502f00768b9279115af6b26`，识别到无扩展名 Config 路径但仍扫描 `.json` 文件，仍失败并停止交 owner。
- **owner 授权的新尝试（不计入 DC68 重做）：** 用已提交的 `frontend/scripts/docker-save-image-identity.py` 从“导出镜像身份”开头重做。CT201 日志 `/home/dev/gdds-fe-logs/fe1/fix1/backend-image-identity-ct201-owner.log` SHA256 `801886e8967f45dcd30ebe5e9609b61879c1b3163a84afcbd89b2f9e8d0c5d72`，14:15:32–14:15:45，exit `0`；自检为单镜像、config 字节 SHA 与 Config 路径摘要一致、DiffID 数等于 Layers 数。随后 CT05 docker load 和身份比对通过。
- **fixture 生成前置失败：** 系统 Python 缺少 `fastapi`，`backend-fixture-generation-run1.log` SHA256 `0e14f4e1b31b153b89ee829ddb0bb432fc47a22ece8248493afd5fcea809cc1b`；改用镜像内 backend venv。第一次 venv 生成发现手写导航 JSON 未按 JCS canonicalize，`backend-fixture-generation-run1-retry.log` SHA256 `b622cc1bbca5c087d81d92feccfc5a49317a4c83d7d840c794c7627194f279b8`；改为后端 `canonicalize_json_value` 后，最终双跑字节一致。此前操作汇总 `dc68-operations-summary.log` SHA256 `d5e2bc0ac0fe2654dcc1b66dcc862e507f3f19242a52c2c26c9759beb26984f5`。
- **本轮 CT05 预检命令错误：** 首次误用不存在的 `/home/dev/gdds-fe`，日志 `preflight-05-owner-retry.log` SHA256 `27cfab1ad1256ec409c666e822f6addb4eb08d4b199f00cd318f5267d0c9221c`；改用实际共享仓库路径 `/home/dev/gateway-data-management-system`，从预检开头重做成功，结果见上表。
- **本轮 bundle 创建命令错误：** 首次误选 `c1a76…` 作为 CT05 main 的前置祖先，创建步骤停止；失败日志 `source-bundle-create-be430b9d98.log` SHA256 `c4961751de1a2053a6b58b692bfe6d90a9ccb9d172ec49ff58027ee20bd14c26`。确认共同祖先为 `36047efe…` 后，从创建步骤开头重做，成功生成并传输/verify/fetch。
- 本节引用的 CT05 远端日志 SHA256 为日志关闭后重算的最终文件摘要；对应 `.sha256` sidecar 已同步修正。任何镜像身份不符均未发生；后续唯一 runner 已开始且非零退出，因此按停止规则未重跑。

## FE1 补充修复：后端三类行记录

### 候选与数据

- 在 `6949ffcb45b6189f57a99de5872f7598e443d2b3` 之后追加代码提交 `b54dd08f37e27db9387aa9c248f7e0f692c57804`，未改写 `be430b9d98`。本轮代码候选 `frontend/` tree 为 `90a37284c3724df1db4ea5dc7bf20cdcd084a125`。最终复审范围从 `c1a76ea345..<本 handoff 提交 HEAD>`。
- `generate-backend-bundle-fixture.py` 的固定 SQL 现在生成：基线设备 1、2、4；当前设备 1 不变、2 的 description 改为“测控装置（升级）”、新增设备 3、删除设备 4。后端产物包含 `ROW_ADDED`、`ROW_DELETED`、`ROW_MODIFIED` 各一条。
- `parquet-reader.test.ts` 两个浏览用例都断言三种 record kind；首个用例还检查修改记录的 before/current description。同步更新基线/当前行数、当前设备 2 文案，以及 surface 的表级风险断言。后端实际结果为 before 3 行、current 3 行、表级风险 `MEDIUM_HIGH`、风险 annotation 数 3；导航 fixture 中新增设备 3 的单项风险仍为 `MEDIUM_LOW`。
- 新 bundle digest 为 `sha256:a34e85601da5bbb2b818f7307273fd6844e81d62ef0ad576e2ee9b285f5f4538`；`closure_manifest_digest=sha256:db3dec9c8329634a2e6a0c7863159619cd5e9cbe0c7f885da56af4cdd40e7b5e`；`bundle_manifest_digest` 与 `bundle_digest` 相同。POSIX tar 为 64,512 bytes，SHA256 `df9f91279dc01cb3c70016910e267ef0de1d04b23537a92e2cfdd8ffd85e4735`。
- fixture 来源、后端代码和依赖镜像身份保持不变：来源提交 `c1a76ea345f3b183cc9b04a2e90d3f58257626d7`，`vnext/` tree `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`，镜像 `gateway-backend-deps:lock-d054366c02fa`。沿用 CT201 与 CT05 已核对的 config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 及 19 个 DiffID；本轮没有重新加载镜像，CT05 上的既有身份证据为 `/home/dev/gdds-fe-logs/fe1/fix1/backend-image-identity-ct05.log`，SHA256 `d46d1602ff63f7c5411c6e6f9f6a7eff42684fcfc3d3efe8423957d0fb5993bc`。
- 在 CT201 用 `--network none`、只读挂载 `vnext/` 的同一后端镜像运行生成器两次。生成日志：`backend-fixture-generation-1.log` SHA256 `6c48d127a921cdcd8bb24755a42e35614110f2984dd510dd8c0cafea340291da`；`backend-fixture-generation-2.log` SHA256 `c71714db67701cd3c7b382914e0dac11f5d6f31cb788c0f35f147ac40e0bc306`；逐字节比较日志 `backend-fixture-reproducibility.log` SHA256 `a39c867ea90ee9fcd807b39966d73580b5e3026c2cf3ad99ce8e977d5db2cae4`，结果 `byte_identical=true`。生成器脚本 SHA256 `f2ac7c839a22feca4dc77497d36e99799539e615ec19c287e998e7c0d58f579b`。
- 新后端产物 SHA256：

  | 产物 | SHA256 |
  | --- | --- |
  | `manifest.json` | `bc22965d44ea8d0ba2e81cb88faf437ad220704429a59cc798ff5511b235dc27` |
  | `artifact-closure.json` | `e8da236d3010e1eeab949b71d872b8c1f0db8f728e3443ab10bc99151203ad17` |
  | surface | `6918d64a8cd24e81ed7b9e3ca6692e0074df0bb7fb464751f222df41ecd90e3d` |
  | records closure | `dd7a394e8cbeac552b966cea75d6de995d3d1f24ade8a4cdf5efa8629b457103` |
  | records manifest | `e20664ffb01a4e6baae0299f61054b2a334306afbec586c5701d90a489e48273` |
  | records Parquet (`rows.bin`) | `e5b21354c259475020a33fe63ca25b8010607086ff2c6c198621c619f4f2ffc0` |
  | business navigation projection | `36e72e4e0bbd3f461889fe5266bdfb10e208e416777fa924d8d47a7590a2a97c` |
  | risk annotations | `6bc85a9204eb02f0836f2d8178de75622255496076a74d3f5d2f4c0d6ad757ef` |
  | risk annotations manifest | `56d9bef475e920b6f22e4636b9dafb4706dbf139a73afec423d37b2373834124` |
  | before snapshot Parquet | `8cc5ec8b54a4ca3117c51138367f8465aac2009336ef3cbb88737627213ea1d5` |
  | current snapshot Parquet | `55b3a45dead4436a47c3ab5ffae9fd4c9a9fa618d502a764a3def8798d678f14` |

### CT05 完整运行

| 步骤 | 节点/时间（UTC） | 结果与日志 SHA256 |
| --- | --- | --- |
| 预检 | `gw-dms-test-05.lan`，15:15:23–15:15:25 | SSH OK、busy 标记不存在；共享 main `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`；缓存、Playwright 和 backend 镜像在。预检日志 `preflight-05-b54dd08f37.log` SHA256 `c9e9455551d71cb77982f741aa40a60d8aa543a24e82395239ba476cc858f7f0` |
| bundle 创建 | CT201，15:15:32–15:15:33 | bundle SHA256 `e64a51a4fe43c96668758ce43a32f80b858d2ccb8e1ffdf81c3f31dbc94136a8`。日志 `source-bundle-create-b54dd08f37.log` SHA256 `15d3246aaa532a6a7adeff0b74164cd9bb339df8ad6ee8d199ac7642005f5c2e` |
| bundle LAN 传输 | CT201→CT05，15:15:43 | 两端 SHA256 相同。日志 `source-bundle-transfer-05-b54dd08f37.log` SHA256 `d2f14059d7d8c0dc7126bb3f1be4e3e2c4480afe226fccb666a2addebf001e72` |
| CT05 verify/fetch | 15:15:52 | `FETCH_HEAD` 精确为 `b54dd08f37e27db9387aa9c248f7e0f692c57804`；main 前后不变。日志 `bundle-fetch-05-b54dd08f37.log` SHA256 `2d2e25be8dcd224d2bf7d67c9c1d178f44f9a0b69d723cda80ed6b10b13cc156` |
| detached worktree | CT05，15:16:01 | `/home/dev/gdds-fe-fe1-fix2-05`，HEAD/tree 精确匹配，legacy 链接已建，status clean。日志 `worktree-add-05-b54dd08f37.log` SHA256 `ca77bbc8dfcc63ba1388a9847c4738b9cc5f833b0b6ba531d82119a7c7857be3` |
| runner 前检 | CT05，15:16:18 | busy 标记不存在；worktree clean；toolchain、npm cache 和 305 个 lock resolved 项符合要求。日志 `runner-preflight-05-b54dd08f37.log` SHA256 `cfaf9f39e5aece47c040684385071c9de447da995817eb9a8b512ade40e4b1cf` |
| 权威 runner | CT05，15:16:22–15:16:35 | 完整 `./frontend/scripts/run-tests.sh --e2e`；HEAD/tree 起止一致，`docker_network=none`，exit `0`。typecheck、lint 通过；Vitest 9 文件、38 项全通过（含跨实现摘要测试与三类 records 测试）；build 成功；Playwright `3 passed`，覆盖 OPFS 安装、Parquet 浏览与缓存命中。runner 日志 `/home/dev/gdds-fe-logs/fe1/fix2/frontend-tests-20261102T151622Z.log` SHA256 `89cd1ffd39985514400aa1971c689c4d7a9ff949383ba83b7d1bb8e007638e4b` |

修复前失败日志保留：`/home/dev/gdds-fe-logs/fe1/fix1/frontend-tests-20261102T143633Z.log`，SHA256 `4a89d3ab6733d5924de3d6457bb190bd7cfe7ae17ba6b35b22b6e023fa9dc676`。修复后完整运行通过；05 worktree 仍 clean，main 仍为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`。本轮尚未重做 04 取证；按流程等待独立复审通过后再进行。

## FE1 补充修复：行风险与行变更定位（B4）

### 候选与修复

- 复审基线为 `918282218eb00d7d1128a3da9e31924c7db6ad3c`。先追加 B4 代码提交 `b55a64db8b8e823efcd070252d079933e90f77ec`（`frontend/` tree `b4b0f8378613743f9fa9dbc987f805f2b5dfdc75`）；其 CT05 首次完整 runner 在 typecheck 失败。随后不改写该提交，再追加行数字段修正提交 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de`（最终 `frontend/` tree `8e553cbf49cced19c686b136f14ec79407c5e14d`）。复审范围为 `918282218e..<本 handoff 提交>`。
- **B4 行标注与 identity：** `RiskAnnotation` 采用后端 annotations 文档的 `annotation_id`、`risk_level`、`reasons`、`diagnostics`、`target` 结构；`RiskReport`、`RiskTableReport`、`SurfaceTable`、`RowDiffRecord` 也改用后端 report、surface 和 records 的字段名及嵌套形状。records 的 binary row identity 和 annotation 的 `sha256:<hex>` 都归一成 `sha256:<hex>`；只有 `target.target_type === "ROW"` 的 annotation 进入行风险 Map。
- **B4 本地读取：** `presentation.ts` 按每个 surface 表的 `risk_refs.annotation_ref` 在 bundle closure 中定位 annotation 文件，并由已安装 bundle 的本地读取接口解析；没有后端请求路径。`readLocalChangeRecords` 返回后端 records 字段形状。
- **B4 record kind：** 行定位只接收 ComparisonRecordKind 与 OrderedRecordKind 的行级成员。`SCHEMA_CHANGE`、`TABLE_DEGRADED`、`ORDERED_TABLE_DEGRADED` 不会进入行定位；前端自造的 `UNCHANGED`、`UNCHANGED_RANGE` record 判断已删除。`filterChangedRows.changeKinds` 明确使用 records 的 row record kind，不使用表级 `ADDED`/`UPDATED`。搜索递归读取后端 `before_values`、`current_values` 的嵌套 scalar 字段。
- **B4 唯一测试 owner：** `model.test.ts` 的“maps backend row records to their local annotations and filters row changes”从本地安装的后端 bundle 读取 records 与 annotations，依序断言 `ROW_ADDED/MEDIUM_LOW`、`ROW_DELETED/MEDIUM_LOW`、`ROW_MODIFIED/MEDIUM_HIGH`；同一用例加入 TABLE annotation 和 `SCHEMA_CHANGE` 记录，验证二者分别不覆盖行风险、不产生行定位。筛选与搜索也使用后端 Parquet 字段形状。
- **typecheck 修正：** 首个 B4 提交的 `rowCount` 仍以字符串索引 surface 行数对象，并包含后端不存在的 `before_row_count`、`current_row_count` 候选名。追加的 `c5ee9a06bc` 将其改为直接读取 `row_count_before`、`row_count_current`。
- **R1：** 删除 `theme.test.ts` 中将测试内颜色常量与自身比较的四条断言。
- **R2：** 原“完成情况”已标为原候选摘要，并指向本节；旧“本地 bundle fixture”明确标为历史记录，注明旧手写 JSON、PyArrow 文件及 `c108ea2c…` 摘要已被后端 fixture 取代。

### 后端 fixture

- fixture 未改、未重生成。仍使用后端来源提交 `c1a76ea345f3b183cc9b04a2e90d3f58257626d7`、依赖镜像 `gateway-backend-deps:lock-d054366c02fa`；当前 `bundle_digest=sha256:a34e85601da5bbb2b818f7307273fd6844e81d62ef0ad576e2ee9b285f5f4538`，tar SHA256 `df9f91279dc01cb3c70016910e267ef0de1d04b23537a92e2cfdd8ffd85e4735`。此前的两次生成和逐字节复现日志见上文“FE1 补充修复：后端三类行记录”。

### CT05 验证

| 运行 | 时间（UTC） | HEAD / `frontend/` tree | 结果与日志 SHA256 |
| --- | --- | --- | --- |
| 首次 B4 候选 | `2026-11-02 15:50:16–15:50:23` | `b55a64db8b8e823efcd070252d079933e90f77ec` / `b4b0f8378613743f9fa9dbc987f805f2b5dfdc75`，起止相同 | runner exit `2`；`npm ci` 后 typecheck 在 `model.ts:273` 报 TS7053（行数对象以 string 索引）。未运行 Vitest、build、e2e。失败日志 `/home/dev/gdds-fe-logs/fe1/fix3/frontend-tests-20261102T155016Z.log`，SHA256 `0c11ece34fae8f98491a09a8e7c1994c077db701af34657be12b9828c4fac062` |
| 修正后的完整 runner | `2026-11-02 15:55:01–15:55:14` | `c5ee9a06bc8f2502f8b5299d2b8cd657441797de` / `8e553cbf49cced19c686b136f14ec79407c5e14d`，起止相同 | `./frontend/scripts/run-tests.sh --e2e` exit `0`；typecheck、lint、build 通过；Vitest 9 文件、38 项通过；Playwright e2e `3 passed`。fixture bundle digest 为上述 `sha256:a34e8560…`。日志 `/home/dev/gdds-fe-logs/fe1/fix3/frontend-tests-20261102T155501Z.log`，SHA256 `f5083ca2e8619345c91c55867a54167b716b90fa51f752fc1048f2a907d47705` |

两次 runner 均在 `gw-dms-test-05.lan` 的 clean、detached worktree 上执行；05 的 `main` 前后均为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`。沿用 Playwright 镜像七个已核对 DiffID、npm cache `/home/dev/gdds-fe-cache/fe0/npm-cache` 和归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；缓存来源提交记录为 `a2fb4a027a6f62218109783674cfc37bd64e14a5`，resolved 数为 305。

源码传输证据：以 `36047efe5acca90c08acb95796c58c5b4cea33a3` 为 bundle 前置，候选 `c5ee9a06bc` bundle SHA256 `de2526516921f98848f94e96877defd964f09cc26a75092c3096b777de4dded7`；创建日志 `source-bundle-create-c5ee9a06bc.log` SHA256 `faba6642627df167b90e5d2e9a4ed1b3cf3c3693d42e37ec4568e788c955a1d4`，LAN 两端校验日志 `source-bundle-transfer-05-c5ee9a06bc.log` SHA256 `b7ad2fb4981d67a06b9f5b87c95cd8d19a4307f972f6b6f140593dc9bcd5cced`，05 verify/fetch 日志 `bundle-fetch-05-c5ee9a06bc.log` SHA256 `f6e94fd36d4a3983368f1a62d294086ea65cf8a89d6d6cc5cbc908b94173bf31`，worktree 日志 `worktree-add-05-c5ee9a06bc.log` SHA256 `ada7b161fb03b2803c3ceab1088ae123ef67a79e1309bb8c316687b10ead86f9`。worktree 为 `/home/dev/gdds-fe-fe1-fix3-retry-05`，运行前后 HEAD/tree 未变且 clean，`legacy` 链接已创建。

### DC68 前置操作错误

以下三次错误均发生在被测 runner 启动前，分别保留失败日志与 SHA256，并从步骤开头修正重做；未发生缓存缺失或镜像身份不符。

1. 05 初次预检使用无效的 Docker `--format "{{.Config.Image}}"` 字段，命令失败；失败日志 `/home/dev/gdds-fe-logs/fe1/fix3/preflight-05-fail-docker-inspect-template.log`，SHA256 `b1d465aada9f2057eb5e7f0591f7fccf9b28334e326076c1db78c62388958574`。改用镜像存在性检查和 runner 使用的 RootFS DiffID 字段，从预检开头重做通过；日志 `preflight-05.log` SHA256 `7885b4aaef0e50dcfae5dcbc0c84bbea909f35dabfd41784d9408429019f7f0a`。
2. 为 b55 候选创建 bundle 时误将 05 的 `main`（`0e0d14f1d1`）当作候选祖先；失败日志 `/home/dev/gdds-fe-logs/fe1/fix3/source-bundle-create-b55a64db8b.log`，SHA256 `dc3fcc05ee2981f81f03f612fd65aef49d188892a2b37f88ab2ce9ceb0b35d7f`。确认实际 merge-base 为 `36047efe5acca90c08acb95796c58c5b4cea33a3` 后从 bundle 创建开头重做，日志 `source-bundle-create-b55a64db8b-retry-1.log` SHA256 `ea3604cbb18afe31cde95fc2acf80c8409155dff8ac3a66ab86276fcc834013d`，bundle SHA256 `f41dba291bd98e750b80cd478fbba0b2a1517c64697fe642544ac06d2f640da7`。
3. 检查 npm cache 时误查默认路径，未找到文件；失败日志 `/home/dev/gdds-fe-logs/fe1/fix3/preflight-05-cache-path-probe-fail.log`，SHA256 `aa42bd02c4c35b875344afdf669f2fb7e225f642a3d66095749b7825cfda2d30`。按既有 runner 日志确认实际 cache 目录及归档路径后，从预检开头重做通过；日志 `preflight-runner-05.log` SHA256 `4f0768617e9601cde2054896df057cdccc0c4b4311247c59bc48651bdd9203a9`。

B4 修复提交阶段未进行 04 取证；复审第 2 轮通过后的阶段退出运行记录见下文。

## FE1 阶段退出取证（04）

### 被测提交与预检

- 独立复审第 2 轮 PASS 报告位于 main `24934e2919992fcde403aea56cdfaf09cbeb875d`。被测代码候选为 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de`，`frontend/` tree 为 `8e553cbf49cced19c686b136f14ec79407c5e14d`。源码从 `fe-vnext` handoff HEAD `7732c4140e6c60570c7fe4ea2c806e436e44ac9a` 传输；该提交只在候选后更新 handoff，`frontend/` tree 未变。04 worktree 检出的是代码候选 `c5ee9a06bc`，没有检出 handoff 提交。
- 04 预检时间 `2026-11-02T16:07:03Z`，节点 `gw-dms-test-04.lan`：`ssh -o BatchMode=yes ... 'echo OK'` 成功；`/home/dev/gdds-node-busy.d` 不存在；共享 main 为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`；宿主机没有 Node.js。原 worktree `/home/dev/gdds-fe-fe1-exit-04`（HEAD `b67da4795f`）仍在，本次未复用。新路径 `/home/dev/gdds-fe-fe1-exit2-04` 当时不存在。预检日志 `/home/dev/gdds-fe-logs/fe1/exit-04/preflight-04.log`，SHA256 `1a45da0836719ec25ae8d15748c7580d86711590848915b11bc2c811929ec6ba`。

### 镜像与缓存身份

- 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble` 已存在。使用代码候选中的 `frontend/scripts/docker-save-image-identity.py` 对 04 上 `docker save` 归档导出身份；解析器 SHA256 `c205c3c044d388ce7a75f36eb4d02ef209b4487ef4d2f39229d4abc98f179a45`，config digest 为 `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`。config 内容摘要与 Config 路径一致、manifest 为单镜像、Layers 和 DiffID 数均为 7；未比较 inspect ID。
- 导出的 RootFS DiffID（顺序与 runner 固定值一致）：

  1. `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  2. `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  3. `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

- 镜像身份日志 `/home/dev/gdds-fe-logs/fe1/exit-04/toolchain-image-identity-04.log`，SHA256 `6eb1b8158980a29afad271367a983d73e975c198c4081a1fe9b63130ef8048df`；导出 JSON `/home/dev/gdds-fe-logs/fe1/exit-04/toolchain-image-identity-04.json`，SHA256 `4961e044044f603d9e088b02ab556af4faa4f41b3b4cbae9e4759fa13f87dcfc`。解析脚本经 CT201→04 传输，两端 SHA256 均为 `c205c3c044d388ce7a75f36eb4d02ef209b4487ef4d2f39229d4abc98f179a45`；传输日志 `/home/dev/gdds-fe-logs/fe1/exit-04/image-identity-script-transfer.log`，SHA256 `5aeeb0acb0bb310f535b607e11359807890584ed928b673ef98fbd6b57414052`。
- npm cache 沿用默认目录 `/home/dev/gdds-fe-cache/frontend/npm-cache`；归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` 的 SHA256 为 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，与预期相同。来源提交按 R1 记录为 `a2fb4a027a6f62218109783674cfc37bd64e14a5`；lockfile 有 305 个 resolved 项。

### 源码传输与 worktree

- CT201 `heavy-dev-01.lan` 于 `2026-11-02T16:08:25Z` 创建 `fe-vnext` bundle，前置为 04 已有的祖先提交 `36047efe5acca90c08acb95796c58c5b4cea33a3`。bundle SHA256 `f09109ce27dc9e10b69fb248d0a223bc69a524730192aef1e05c875b369f176e`；创建/verify 日志 `/home/dev/gdds-fe-logs/fe1/exit-04/source-bundle-create-7732c4140e.log`，SHA256 `313afe94560d81cabc0d2f80e58da3213944e20654150e1e15b9e1aaed2c4f23`。
- CT201→04 局域网传输时间 `16:08:31–16:08:32Z`，两端 bundle SHA256 都是 `f09109ce27dc9e10b69fb248d0a223bc69a524730192aef1e05c875b369f176e`。传输日志（CT201）`/home/dev/gdds-fe-logs/fe1/exit-04/source-bundle-transfer-04-7732c4140e.log`，SHA256 `3189cd7b261d0c7b268d5ecb892f89f3427b0b45760169d1cacbf73663596444`。
- 04 于 `16:08:40Z` 完成 bundle verify/fetch；`FETCH_HEAD=7732c4140e6c60570c7fe4ea2c806e436e44ac9a`，main 前后均为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`，未建分支、未移动 main。日志 `/home/dev/gdds-fe-logs/fe1/exit-04/bundle-fetch-04-7732c4140e.log`，SHA256 `52788c272f6c4b8641acd59f9b447bcaa4c3b5dc3072f1e63b5424b7ce7d5477`。
- 04 于 `16:08:46–16:08:47Z` 新建 detached worktree `/home/dev/gdds-fe-fe1-exit2-04`，HEAD 为代码候选 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de`，`frontend/` tree 为 `8e553cbf49cced19c686b136f14ec79407c5e14d`，legacy 链接指向 `/home/dev/gateway-data-management-system/legacy`，`git status --porcelain --untracked-files=all` 为空。日志 `/home/dev/gdds-fe-logs/fe1/exit-04/worktree-add-04-c5ee9a06bc.log`，SHA256 `c16b663d65d0aaebc8b04fc092588991c85498557b10cc3d13e453e8508ae2ab`。

### 04 权威运行

- 在上述 worktree 只运行一次完整 `./frontend/scripts/run-tests.sh --e2e`，时间 `2026-11-02T16:08:55Z–16:09:10Z`。hostname `gw-dms-test-04.lan`；`head_start` 与 `head_end` 都是代码候选 `c5ee9a06bc8f2502f8b5299d2b8cd657441797de`；`frontend_tree_start` 与 `frontend_tree_end` 都是 `8e553cbf49cced19c686b136f14ec79407c5e14d`；exit code `0`。typecheck、lint、build 均通过；Vitest 9 个文件、38 项通过；e2e `3 passed`。runner 记录 `fixture_bundle_digest=sha256:a34e85601da5bbb2b818f7307273fd6844e81d62ef0ad576e2ee9b285f5f4538`。
- runner 日志 `/home/dev/gdds-fe-logs/fe1/exit-04/frontend-tests-20261102T160855Z.log`，SHA256 `c1df171de4339e5a64b5bd5ad8e9b6e06ef7af63ef932519894bfebd4b481655`。运行后新 worktree 仍 clean，HEAD/tree 未变；04 main 仍为 `0e0d14f1d19779a5ff49c8e3c79f6aba323dd0bf`。本次成功运行取代原候选 `b67da4795f` 的 04 运行，后者仅作为历史记录保留。
- 本轮没有 DC68 重做。测试未在开发主机运行；`/home/dev/gdds-fe` 与开发主工作区均 clean。未推送、未打 tag、未合入 main。本 handoff 提交后，状态为“04 取证完成，待证据核对”。
