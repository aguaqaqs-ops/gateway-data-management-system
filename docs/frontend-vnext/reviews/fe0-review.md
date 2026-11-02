# FE0 审核报告

- **审核对象：** 分支 `fe-vnext`，候选 `6c5dbcb1c41fb34bce0bf7a635d90135e860bd3e`；测试绑定的源码提交
  `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2`（与候选只差 handoff，`frontend/` 树相同）。
- **范围：** `f0ad2461ac..6c5dbcb1c4`（`fe-vnext` 与 `main` 的 merge-base 为 `f0ad2461accf173354cb4fa45a0f132dc4d568e7`）。
- **handoff：** `docs/frontend-vnext/fe0-handoff.md`（候选提交中的版本）。
- **审核日期：** 2026-11-02。
- **结论：定向修复。** 代码范围、FD 遵守、依赖钉版本、OpenAPI 快照与类型均合格；05 默认入口复跑通过。
  有两项阻塞需实施会话修复（B1 lockfile 的 registry 身份、B2 `--e2e` 不可运行），另有一项需设计会话答复后才能
  满足 FE0 退出条件（D1 复合信号公式查看的数据来源）。

## 1. 审核环境与复跑

| 项 | 内容 |
| --- | --- |
| 开发主机只读 worktree | `/home/dev/gdds-fe-review-fe0-6c5dbcb1c4`（detached，`legacy` 符号链接），只读审查，未在开发主机运行测试 |
| 05 worktree | `/home/dev/gdds-fe-review-fe0-6c5dbcb1-05`（detached，clean，`legacy` 符号链接） |
| 源码传输 | 开发主机 `git bundle create ... ^f0ad2461ac fe-vnext`，bundle SHA256 `fd8aca0266631ac0943587c1c2c482dbde07d0b9af65b1a1989a08dea5c47648`（两端一致）；05 主仓库 `git bundle verify` + `git fetch`，`FETCH_HEAD` = 候选；05 `main` 未移动（`0d9ff6d5cd`），未建分支 |
| 节点占用标记 | 每次运行前确认 `/home/dev/gdds-node-busy.d` 不存在 |

05 日志（`/home/dev/gdds-fe-logs/fe0/review/`，节点 `gw-dms-test-05.lan`）：

| 运行 | 起止（UTC） | HEAD（起→止） | exit | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| worktree 准备 `review-setup.log` | 09:37:09–09:37:09 | 候选 | 0 | `fdd0534e77839affe592975f5e4799ca9c246d534266903b6b71e74629c34878` |
| `frontend/scripts/run-tests.sh`（默认） `frontend-tests-20261102T093716Z.log` | 09:37:16–09:37:25 | `6c5dbcb1c4` → 同 | **0** | `f4e307b2292366581756fa7da707b9b975e822bc1dc1e16e4909220727b09829` |
| `frontend/scripts/run-tests.sh --e2e` `frontend-tests-20261102T093733Z.log` | 09:37:33–09:37:42 | `6c5dbcb1c4` → 同 | **1**（`Error: No tests found`） | `67f99d5ae1bd7ae19abd1e65140c7f7c9d9c6b186519d8b9fe5d5c3023348479` |
| OpenAPI 与类型重生成 `openapi-regen.log` | 09:38:16–09:38:25 | 候选 | 0 | `7c118624b19ca4153966520677a1aa3c833be70310f3f8229c2af41b5d88f9fa` |

- 默认流程：`npm ci --offline`（network none）安装 280 个包，typecheck、lint、build 通过；Vitest `No test files found`
  经 `--passWithNoTests` 退出 0。构建产物文件名哈希（`index-DwKvav20.js`、`index-BliSb9Th.css`）与实施者 08:35 运行一致。
- OpenAPI：在 05 用候选树的 `vnext/` 源码只读挂载进 `s1c-vprime-ebd1-backend:latest`（network none），按 handoff 命令重新生成，
  与提交的 `frontend/openapi.json` **逐字节相同**；再在工具链容器中离线安装后运行 `npm run generate:api-types`，生成结果与提交的
  `openapi.d.ts` **逐字节相同**。`7c339bff46..6c5dbcb1c4` 之间 `vnext/` 无改动，快照来源与候选一致。
- 每次运行后 05 worktree 仍 clean。

## 2. handoff 证据核对

- **CT201（`heavy-dev-01`）：** `toolchain-pull/save/transfer.log`、`npm-cache-package/transfer.log`、`npm-install.log`、
  `source-bundle-09730.log`、`fe-vnext-09730.bundle`、旧 `fe-vnext-test.bundle` 与 `frontend-source-transfer.log` 的 SHA256
  均与 handoff 一致；`playwright-v1.64.1-noble.tar` 与 `npm-cacache-fe0.tar.gz` 的 SHA256 与 handoff 及归档 `.sha256` 文件一致。
- **05：** `toolchain-load.log`、`npm-cache-prefill.log`、两次 setup 失败日志、`frontend-bundle-fetch.log`、
  `frontend-test-worktree-add.log`、`npm-ci-offline-20261102T083518Z.log`、`frontend-tests-20261102T083535Z.log` 的 SHA256 均与
  handoff 一致。runner 日志记录了 hostname、起止时间、起止 HEAD（`09730a57ff`）与 exit 0。
- **工具链镜像身份：** 05 `toolchain-target-metadata.txt` 的 config digest `sha256:a0d7b2b4…a1017` 与七个 DiffID 同 CT201 来源；
  我在 05 另用 `docker image inspect .RootFS.Layers` 核对，七个 DiffID 顺序与值一致。未用 inspect ID 做跨节点比较。
- **npm 缓存：** 05 cacache 603 MB，存在且非空。
- **DC68 记录：** 两次 clone 失败均未触及被测对象，日志与 SHA256 保留，后续按设计会话指定的 bundle/fetch 流程从头重做，记录完整。
- 记录偏差（非阻塞，见 N7）：handoff 写的“依赖与锁文件来源提交” `62cd5d5641` 是 rebase 前的旧提交，不在 `fe-vnext` 上。
  我核对过它的 `frontend/package.json` 与 `frontend/package-lock.json` blob 与候选完全相同，因此缓存仍对应当前锁文件。

## 3. 审核要点逐项

### 3.1 范围

`f0ad2461ac..6c5dbcb1c4` 只改动 `frontend/`（19 个文件）、`.gitignore`（新增 6 行 `frontend/` 忽略项）与
`docs/frontend-vnext/fe0-handoff.md`。没有改动 `vnext/`、AGENTS、kickoff、UI 优化方向或 `docs/backend-vnext/`。**通过。**

### 3.2 FD 遵守情况

| FD | 结论 |
| --- | --- |
| FD1 | `frontend/` 无 legacy 引用、无兼容层或 legacy bundle 形状。通过。 |
| FD2 | 当前源码没有任何 `fetch`、`XMLHttpRequest`、`<a href>` 下载或 storage 调用；认证封装属 FE1。FE0 不适用，FE1 审核。 |
| FD3 | 同上，没有取数调用点。FE1 起逐个审查。 |
| FD6 | 尚无分组或列展示代码。FE1 审核。 |
| FD5 | FE2 起审。 |

### 3.3 依赖

- `package.json` 全部依赖精确钉版本（无 `^`/`~`），`package-lock.json`（lockfileVersion 3）已提交，305 个包都有 `integrity` 与 `resolved`。
- `npm ci --offline` 在 05 两次复跑可复现（实施者一次、我一次）。
- 我从开发主机逐个查询 `https://registry.npmjs.org/<包>/<版本>`：305 个包的 `integrity` 与官方一致，tarball 路径一致。
- **问题：** 全部 `resolved` 主机为 `http://192.168.233.184:4873`，见 B1。

### 3.4 测试

FE0 没有业务测试；handoff 如实写明 Vitest 未找到测试文件、当前验证只覆盖工程检查与构建，没有把空跑表述为测试通过。
没有覆盖率探针。`--passWithNoTests` 的后续处理见 N1。

### 3.5 kickoff §7 FE0 退出条件

| 条件 | 状态 |
| --- | --- |
| 工程初始化（React、TS、Vite、glide-data-grid、hyparquet、lucide，分层目录） | 完成 |
| 工具链镜像与 npm 缓存预填充 | 05 完成；04 尚未预填充，阶段退出取证前需要（且须在 B1 修复后进行） |
| 测试入口与节点规则落地 | 入口完成；规则已由治理提交 `f0ad2461ac` 写入 |
| OpenAPI 快照与类型生成 | 完成，05 上可逐字节复现 |
| §3.3 复合信号核对 | 静态核对结论与源码一致（`snapshot_materialization/compose.py:93-94` 物化 `formula_digest`、`formula_ast_json`；`table_rules/registry.py` 仅把 AST 排除在比较列外）。数据来源问题见 D1 |
| legacy 能力清单无“未判定”项 | 名义上无未判定项，但“复合信号表与公式查看”的 KEEP 以设计确认为前提，见 D1 |
| 05 上入口可运行 | 默认流程通过；`--e2e` 不可运行，见 B2 |
| （§6）阶段退出时 04 上完整运行前端测试与 e2e | 未进行；当前候选上 `--e2e` 必然失败，见 B2 |

## 4. Findings

### 阻塞（实施会话定向修复）

**B1. lockfile 的 `resolved` 被开发机 npm 配置改写为局域网 HTTP registry**

- **位置：** `frontend/package-lock.json:37` 起，全部 305 处 `"resolved": "http://192.168.233.184:4873/..."`。
- **原因：** CT201 的用户级 `~/.npmrc` 设置了 `registry=http://192.168.233.184:4873/`，`npm install` 把它写进了锁文件。
- **失败场景：** 锁文件身份绑定到一台局域网主机的明文 HTTP 地址。npm 默认只把 `registry.npmjs.org` 替换为当前配置的 registry，
  不替换其他主机，因此任何不在该网段或换了缓存主机的环境（新节点、CI、日后部署）都只能访问这个固定地址或改写锁文件；
  每个阶段的“依 `package-lock.json` 取得缓存”的来源身份也随之绑定到这台机器。这与 AGENTS 对 Python 的同类规则
  （“保留 lockfile 的 canonical registry identity，不得通过机器级 index 配置改写 lock source”）以及 kickoff §6
  “参照 DC67”相冲突。现在修复只需机械替换；拖到 04 预填充之后再改，会使已传输的缓存来源记录失效。
- **建议修复：** 把 `resolved` 主机改回 `https://registry.npmjs.org`（`integrity` 不变；我已核对 305 个包的 integrity 与 tarball
  路径都与官方一致），或在 CT201 上以官方 registry 为 lock source、局域网 registry 只作取包镜像重新生成锁文件。修复后在 05
  工具链容器中重新执行 `npm ci --offline`，确认现有缓存仍命中；不命中则在 CT201 重新取得缓存并预填充。handoff 记录新的
  锁文件 SHA256、缓存来源与预填充时间。可选：在 `run-tests.sh` 中加一行检查，`resolved` 出现非官方主机即 exit 2。
  npm 的这条规则目前没有写进 testing-conventions 的前端一节，建议治理会话补一句（非阻塞，交 owner）。

**B2. `--e2e` 在当前候选上必然失败，FE0 无法完成 04 阶段退出取证**

- **位置：** `frontend/playwright.config.ts:4`（`testDir: "./e2e"`，目录不存在）；`frontend/scripts/run-tests.sh:70-72`。
- **失败场景：** 05 复跑 `run-tests.sh --e2e` exit 1，`Error: No tests found`（日志 SHA256 `67f99d5a…3348479`）。kickoff §6
  要求阶段退出时在 04 “完整运行一次前端测试与 e2e”，按当前候选这一步必然失败。工具链镜像里的浏览器在 network none 容器中能否
  正常启动也还没有被验证过，而 FE1/FE2 的模拟接口 e2e 和截图验收都依赖它。
- **建议修复：** 增加一个最小的浏览器冒烟用例，按业务行为命名（例如“打开应用显示工作台骨架页”），用 Playwright 启动 dev server，
  断言标题可见。不要用 `--pass-with-no-tests` 让 e2e 空跑通过。在 05 运行 `run-tests.sh --e2e`（不连真实 backend，无需占用标记）并记入
  handoff。若设计会话决定 FE0 退出不跑 e2e，需要在 kickoff 或 handoff 中写明，并由 owner 确认。

### 需设计会话答复（阻塞 FE0 退出，不需要实施会话改代码）

**D1. 复合信号公式查看的数据来源（handoff 设计问题 3）**

- **位置：** `docs/frontend-vnext/fe0-handoff.md:100`、`:115`。
- **情况：** 实施会话把该行判为 KEEP，但同时写明“双侧公式和设备名映射来源需设计确认”。
  `docs/backend-vnext/capabilities/composite-signal-device.md:76-79` 描述的 `composite_signal_points_ref` /
  `composite_signal_formulas_ref` 等 pair artifacts，在当前源码中没有实现（我在 `vnext/` 中检索不到）。另外，按 Comparison Bundle
  Contract（`comparison-bundle.md:229`），Preview bundle 只闭合上传侧全部表和被删除表的基线侧，而 `formula_ast_json` 是比较排除列；
  对于公式改变的行，基线侧 AST 能否从 bundle 取得，取决于 records 是否携带比较排除列，这一点尚未核对。
- **影响：** 如果基线侧公式不可得，legacy 查看器的“双侧公式对照”就无法 KEEP，该行应改为 SIMPLIFY（例如只展示当前侧公式、
  以 `formula_digest` 是否变化标示），或在 BE-b 等后端任务中补数据。FE0 退出条件要求清单无未判定项，因此需要设计会话在 FE0 退出前
  确定：判定为 KEEP（并指明数据来源）还是 SIMPLIFY（写明保留的业务事实）；具体来源可以排到 FE1/FE2 之前定稿。

### 非阻塞

**N1. Vitest `--passWithNoTests`**（`frontend/package.json:11`）
FE0 可以接受。FE1 加入测试后应去掉，否则 `include` 写错或测试文件被移走时，单元测试会静默变成空跑并 exit 0。FE1 审核会核对这一项。

**N2. runner 只按 tag 检查工具链镜像，日志不记录镜像身份和缓存摘要**（`frontend/scripts/run-tests.sh:29`、`:48-50`）
如果节点上的同名 tag 在预填充之后被替换，权威入口照常运行，证据日志也看不出来。建议在日志中记录
`docker image inspect --format '{{json .RootFS.Layers}}'`（即 DiffID 列表，可直接与 handoff 比对），以及 npm 缓存来源归档的 SHA256。
改动很小，可以和 B1、B2 一起做。

**N3. 容器内复制整个 `frontend/` 目录，会带入被 Git 忽略的文件**（`frontend/scripts/run-tests.sh:62`）
clean 检查（`:33`）看不到被忽略的文件。例如 `frontend/.env` 被根 `.gitignore:5` 忽略，但 Vite 会加载它，这样构建结果可能依赖未提交的输入。
新建的取证 worktree 里没有这类文件，因此本次结果不受影响。建议只复制已跟踪文件（例如 `git -C "$REPO_DIR" archive HEAD frontend`），或在检查中拒绝被忽略的文件。

**N4. Playwright `reuseExistingServer: !process.env.CI`**（`frontend/playwright.config.ts:15`）
容器内没有设置 `CI`，所以该值为 true。到 FE3 改用 host 网络连真实 backend 时，如果节点 5173 端口上残留一个其他版本的 dev server，
e2e 会静默复用它，测的不是当前 HEAD。建议固定为 `false`。

**N5. 默认 `--network none` 无法连接真实 backend**（`frontend/scripts/run-tests.sh:9-10`）
FE0 和模拟接口 e2e 用 none 是正确的。到 FE3 时，容器内的 `127.0.0.1:8000` 不是宿主机的 backend，需要 host 网络或显式的 backend 地址。
建议在 README 或 FE3 kickoff 记录中写明用法，避免 FE3 临时调整。

**N6. 入口默认路径写死为 `fe0`**（`frontend/scripts/run-tests.sh:6-7`，`frontend/README.md:18`）
后续阶段要靠环境变量覆盖，容易把 FE1 的日志写进 `fe0` 目录。建议改为与阶段无关的默认值，或要求显式设置。

**N7. handoff 记录**
(a) 锁文件来源提交写的是 rebase 前的 `62cd5d5641`，应改为分支上的 `a2fb4a027a`，并注明两者的 `package.json`/`package-lock.json` blob 相同。
(b) kickoff §6 要求 FE0 评估是否并入 `vnext/scripts/run-tests.sh`；治理提交 `f0ad2461ac` 已确定保持独立，handoff 引用这一结论即可。

## 5. handoff 设计问题的处理

| # | 问题 | 判断 | 去向 |
| --- | --- | --- | --- |
| 1 | 起点 `7c339bff46` 而非 kickoff 记录的 `b7d6e45406` | 不阻塞。`7c339bff46..6c5dbcb1c4` 之间 `vnext/` 无改动，OpenAPI 快照已在候选树上复现 | 无需处理 |
| 2 | `frontend-surface-simplification.md` 仍写“临时旧前端兼容层” | 不阻塞。第 7、72 行确是过期表述，引用的 `frontend-legacy-compatibility-layer.md` 在仓库中不存在；FD1 优先 | 设计会话/治理会话修订文档 |
| 3 | 复合信号公式查看的数据来源 | **阻塞 FE0 退出**，见 D1 | 设计会话 |
| 4 | OpenAPI 快照仍含 `RETURN_FOR_REVISION` | 不阻塞，在 BE-a 落地前属预期。FE1 审核会核对前端不暴露该动作 | BE-a 后刷新快照，FE3 做运行时比对 |
| 5 | 04 退出运行尚未进行 | 依赖 B1、B2 修复后进行 | 实施会话 |

## 6. 复审范围

复审对象为 `6c5dbcb1c4..<修复候选>`，核对内容：

1. B1：锁文件 `resolved` 全部为官方主机，integrity 不变；05 上 `npm ci --offline` 通过；缓存来源记录已更新。
2. B2：e2e 冒烟用例存在且实际执行（日志显示 1 passed）；05 上 `run-tests.sh --e2e` exit 0。
3. 选做的 N 项与 handoff 更新。
4. D1 由设计会话答复，结果写进 handoff 或 kickoff 后，复审核对 §8 该行的最终判定。

04 的阶段退出取证在复审通过后进行。
