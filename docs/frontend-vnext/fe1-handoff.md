# FE1 handoff（候选已完成，待独立审核）

## 候选与范围

- 起点：`36047efe5acca90c08acb95796c58c5b4cea33a3`。`fe-vnext` 已从该 main 提交快进；审核范围为 `36047efe5acca90c08acb95796c58c5b4cea33a3..b67da4795fd22afcab1365f4138b131ab4c736d1`。
- FE1 代码候选：`b67da4795fd22afcab1365f4138b131ab4c736d1`。其 `frontend/` tree 为 `3fdda26532349af4db6dbeb9628be87d7f7a748e`。
- 候选由 9 个 FE1 提交组成，所有产品与测试代码改动都在 `frontend/`。本 handoff 在阶段取证完成后作为单独文档提交；最终文档提交 HEAD 由实施会话完成后回报。
- `frontend/package.json` 的 `test:unit` 去掉了 `--passWithNoTests`（N1），并在运行 Vitest 前生成本地 golden tar。依赖版本没有变化，`package-lock.json` 未改。
- `frontend/scripts/run-tests.sh` 记录 `frontend_tree_start` 与 `frontend_tree_end`（R2）。runner 日志中的 `tracked_frontend_archive_sha256` 是各自提交的输入摘要，不跨提交比较。
- 开发主工作区 `/home/dev/gateway-data-management-system` clean，HEAD 为 `36047efe5acca90c08acb95796c58c5b4cea33a3`。`/home/dev/gdds-fe` 在代码候选时 clean，分支 `fe-vnext`。

## 完成情况

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

### 本地 bundle fixture

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
4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3`
5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

npm 缓存沿用 FE0 预填充，归档 SHA256 为 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。缓存实际生成于提交 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4`；该提交的 `package.json` 与 `package-lock.json` blob 和 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 相同。按 R1，两个 runner 均记录 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`，lockfile 有 305 个 resolved 项。05 使用 `/home/dev/gdds-fe-cache/fe0/npm-cache`，04 使用默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cache`；均未重新传输或覆盖缓存。

| 节点 | worktree | 起止时间（UTC） | HEAD（起→止） | frontend tree（起→止） | runner exit | runner 日志与 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| `gw-dms-test-05.lan` | `/home/dev/gdds-fe-fe1-b67da4795f-05` | `2026-11-02 12:56:01–12:56:14` | `b67da4795fd22afcab1365f4138b131ab4c736d1` → 同 | `3fdda26532349af4db6dbeb9628be87d7f7a748e` → 同 | `0` | `/home/dev/gdds-fe-logs/fe1/frontend-tests-20261102T125601Z.log`；`76698b095667c3b8f48169f508b883a03c7a132fd35bfb47baba1f0a7c53a563` |
| `gw-dms-test-04.lan` | `/home/dev/gdds-fe-fe1-exit-04` | `2026-11-02 12:57:42–12:57:58` | `b67da4795fd22afcab1365f4138b131ab4c736d1` → 同 | `3fdda26532349af4db6dbeb9628be87d7f7a748e` → 同 | `0` | `/home/dev/gdds-fe-logs/fe1/frontend-tests-20261102T125742Z.log`；`af5f9eaf829ee50748f913439f79e5cb7bc76d042a132d015c835fcbe0470f46` |

两次运行均为完整 `./frontend/scripts/run-tests.sh --e2e`，`docker_network=none`；typecheck、lint、8 个 Vitest 文件的 32 项测试、build 均通过，Playwright 为 `3 passed`。E2E 包含 OPFS 安装、按本地文件读取 Parquet 和第二次打开命中缓存（未再次请求 fixture）。04 是本阶段唯一一次权威 runner，exit `0`。外层 wrapper SHA256：05 `a2cfde65a12b02dfff3c80618097f1cd50f86a00e10dc2702bab8c3a6167923e`；04 `5769920ca48310d47dd75611ae6719f5c208961954e8f8730541048251b4dad1`。本次 runner 记录的 `tracked_frontend_archive_sha256` 为 `a8dc558a005c6967864cd39f25a439d6df3d681e79554bfb6c83aa72a70fa749`，只作该提交的输入记录，不跨提交比较。

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
