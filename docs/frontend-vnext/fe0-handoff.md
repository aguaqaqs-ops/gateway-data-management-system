# FE0 handoff（04 阶段退出取证完成，待证据复核）

## 完成状态

- 已从当前 `main` 创建 `/home/dev/gdds-fe` worktree 和 `fe-vnext` 分支，代码起点为 `7c339bff460254e19f36e81cb75028ca3a2702b1`；已建立 `legacy` 符号链接。治理规则提交 `f0ad2461accf173354cb4fa45a0f132dc4d568e7` 已成为分支祖先，规则文件在本分支没有额外改动。
- 前端代码提交：`a2fb4a027a6f62218109783674cfc37bd64e14a5`（`feat(frontend): scaffold vnext frontend`）；handoff 独立提交。
- 在 `frontend/` 初始化 React、TypeScript、Vite、glide-data-grid、hyparquet、lucide 工程；依赖在 `package.json` 中精确钉版本，已生成并提交 `package-lock.json`。功能、设计系统、页面分别落在 `src/features/`、`src/design-system/`、`src/pages/`。
- `frontend/scripts/run-tests.sh` 提供类型检查、lint、单元测试、构建入口和 `--e2e` 接口；已在 05 默认流程运行通过。
- 已提交 OpenAPI 快照 `frontend/openapi.json` 和生成类型 `frontend/src/features/api/generated/openapi.d.ts`。
- FE0 工程、缓存预填充、05 调试验证和 04 阶段退出取证均已完成。代码候选仍为 `e22f510a82a143ccee76a1b3b3b6c854aa755129`；04 证据待审核会话核对。

## 测试状态与等待项

owner 已将 FD7 规则提交为 `f0ad2461accf173354cb4fa45a0f132dc4d568e7`，包含 AGENTS.md 与 `docs/backend-vnext/testing-conventions.md` 两处规则，本分支已 rebase 到该提交之上。此前的两次 clone 错误按 DC68 保留；设计会话随后指定从 05 共享仓库 fetch 的新方式，重新从准备步骤开始后成功。

FE0 初始候选的运行结果与本次定向修复结果分别记录在下方相应日志小节。本次定向修复已在代码提交 `d62eb3603747d3dceed2269c3cfc74be100b73e3` 上完成 standalone `npm ci --offline`、默认入口和 `--e2e`。

工具链镜像与 npm 缓存已预填充至 05 和 04。05 调试运行与 04 阶段退出运行均已完成；04 的日志与摘要见“04 阶段退出取证”。

## 工具链与缓存来源

开发节点为 `heavy-dev-01.lan`（CT201），预填充目标为 `gw-dms-test-05.lan`。日志和归档均在 worktree 外的 `/home/dev/gdds-fe-logs/fe0/`；工具链镜像按 config digest 和全部 RootFS DiffID 核对，未使用 `docker inspect` ID 比较。

### Playwright 工具链镜像

- 来源：CT201 拉取官方镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`，随后 `docker save` 并经局域网传到 05，再 `docker load`。Playwright npm 包也钉为 `1.64.1`。
- OCI manifest digest：`sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f`。
- config digest：`sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`。
- RootFS DiffID（顺序与镜像一致）：

  1. `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  2. `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  3. `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

- `docker save` 归档 SHA256：`5babfc35ed51468126d75d5996e4f744a4e58f5442a2a3bb0135630379be163c`。05 加载后导出镜像元数据，config digest 与七个 DiffID 均匹配。
- 时间（UTC）：CT201 拉取 `08:07:29–08:10:26`；保存 `08:11:02–08:11:17`；传输 `08:11:34–08:11:59`；05 加载与身份核对 `08:12:07–08:12:51`，均为 `2026-11-02`。
- 相关日志及 SHA256：

  | 文件 | SHA256 |
  | --- | --- |
  | `toolchain-pull.log` | `58897e5e314704f3f7378d6694a109762053cd858a9f05dc435bdab2db49724d` |
  | `toolchain-save.log` | `1ce64d57e0fd1ed06b61f2ef9df8819a4c0b7a02059d6c2d1321e1d290e3a9c3` |
  | `toolchain-transfer.log` | `248f0d539a948b2d7435ffb4be0ac946d56f7c27b81920b339a4b43042ca85af` |
  | 05 `toolchain-load.log` | `dc141096afcb11f82caf3a8ae48316eae6ea8e01f3039dd85e1cc24a5cecb514` |

### npm 缓存

- 原始缓存生成时依赖/锁文件提交为 rebase 前的 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4`，registry host 为 `192.168.233.184:4873`（未记录凭据）。N7 核对确认它与分支提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 的 `package.json`、`package-lock.json` blob 相同。B1 只改 lockfile 的 resolved source；本次被验证的新锁文件来源提交为 `d62eb3603747d3dceed2269c3cfc74be100b73e3`。
- CT201 的 npm cacache 为 603 MB；归档 `npm-cacache-fe0.tar.gz` 为 100 MB，SHA256：`0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。
- 归档与传输日志记录时间为 `2026-11-02 08:14:24–08:14:41 UTC`；05 解包并校验 `08:14:49–08:14:51 UTC`。05 解包后的 cacache 同为 603 MB，归档 SHA 校验通过。随后 05 工具链容器中 `npm ci --offline` 成功，详情见“05 测试日志”。
- 日志 SHA256：`npm-cache-package.log` `22b6abd65da891c0be51bd722db0ab3aa65d3d96585fada89be20b334d343f0b`；`npm-cache-transfer.log` `185404dc867f081cd8abeca27a6d7abf1c995d40545aef00bd919d99c44110ea`；05 `npm-cache-prefill.log` `d845b4249d1283f8d310cdce97b6af30b4b3ff63677e927ca0751392617410b4`。

### 开发机依赖安装

CT201 使用 Node `v24.20.0`、npm `11.19.0` 执行 `npm install --cache /home/dev/gdds-fe-cache/fe0/npm-cache --no-audit --no-fund`，时间 `08:04:51–08:05:53 UTC`，起始仓库 HEAD 为 `7c339bff460254e19f36e81cb75028ca3a2702b1`，exit code `0`，日志 SHA256 `7a42e7d8dff24e50d20c0d0bba6ebf1cb3885b3de5104cb87fe1b243d2dd2d06`。安装 280 个包；npm 输出两个已弃用 Babel transitive package 警告。该步骤只安装依赖、生成 lockfile 和填充缓存，没有运行测试、类型检查、lint 或构建。

## OpenAPI 快照与类型

- 源码来自 FE0 worktree 起点 main 提交 `7c339bff460254e19f36e81cb75028ca3a2702b1` 的 `vnext/backend/src`、`shared_kernel/src`、`repository_client/src`、`repository_contracts/src`；仅只读挂载到已有后端依赖镜像 `s1c-vprime-ebd1-backend:latest`，容器网络为 `none`。容器内运行 `create_app(workspace_http=object()).openapi()` 生成 schema，没有发起 HTTP 请求或运行测试。
- 生成命令主体：

  ```bash
  docker run --rm --network none \
    -v "$PWD/vnext/backend/src:/source/backend:ro" \
    -v "$PWD/vnext/shared_kernel/src:/source/shared-kernel:ro" \
    -v "$PWD/vnext/repository_client/src:/source/repository-client:ro" \
    -v "$PWD/vnext/repository_contracts/src:/source/repository-contracts:ro" \
    -e PYTHONPATH=/source/backend:/source/shared-kernel:/source/repository-client:/source/repository-contracts \
    --entrypoint python3 s1c-vprime-ebd1-backend:latest -c \
    'import json; from gateway_backend.app import create_app; app=create_app(workspace_http=object()); print(json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True))' \
    > frontend/openapi.json
  cd frontend && npm run generate:api-types
  ```

- 类型生成器为锁定版本 `openapi-typescript@7.13.0`。快照反映上述来源提交，不代表 BE-a 后的 schema。当前快照仍含 `RETURN_FOR_REVISION`；按 FD4，前端操作语义采用 `REJECT` 表示“退回”，不展示旧动作。BE-a 落地后需重新生成并在 FE3 做运行时 OpenAPI 一致性比对。

## §3.3 复合信号核对

**结论：当前 backend 的 snapshot Parquet 表路径会携带 `composite_signal_point`，其数据 schema 包含 `formula_ast_json`；静态核对支持“bundle 闭包包含该表及字段”。** `snapshot_materialization/compose.py` 组装该字段；`table_rules/registry.py` 将 AST 排除在比较列之外，但没有从物化表删除它。Comparison Bundle Contract 要求 Preview 闭合上传侧全部表，History 在提供 snapshot table set 时闭合可浏览 snapshot；相应组装/roundtrip 测试源码也断言该表存在。以上是源码与契约核对，不是本会话运行测试所得。

公式内容的语义比较应依据 `formula_digest`；`formula_ast_json` 是展示/绑定数据。当前后端没有独立的 `composite_signal_points` / `composite_signal_formulas` pair artifacts 与设备名映射投影；设计会话已在 main `bb6a09252a` 定下呈现范围：History 与 Preview 都提供改前、改后对照，BE-b 在表有变化时为 Preview 补齐 `composite_signal_point` 与 `device` 的基线侧整表；补齐前，Preview 中公式有变化的测点只显示上传侧公式并标“公式已改”。该结论与数据来源、名称映射见 kickoff §8 和 BE-b 设计草案 §4.4。

## §8 legacy 能力判定

| legacy 能力 | 判定 | 保留或处理的业务事实 |
| --- | --- | --- |
| 正式工作台组态树与节点详情 | KEEP | 工作区、历史节点、head 与节点身份/状态由 workspace/history API 组合呈现。 |
| 上传：目录选择、浏览器端打包、校验 | KEEP | 按 Source Package Contract 保留必需 `/sql/dbcfg.sql`、可选 `/comps/logic/logics.xml`、包校验结果及错误。 |
| Preview 进度与任务锁定 | KEEP | 保留 operation 状态、进度轮询和任务锁定/可操作状态。 |
| 表列表、表级状态、行级差异 | KEEP | 依据 surface、records 引用和闭包 Parquet 浏览，不重建 legacy bundle 形状。 |
| 整表新增/删除浏览与表级风险 | KEEP | 新增/删除表通过 `TABLE_BROWSE` 与相应 snapshot ref 浏览，风险来自 RiskReport/annotation。 |
| ordered 表差异 | SIMPLIFY | 展示 provider 实际输出的 ordered records/位置事实；未支持或真实降级时展示 `DEGRADED_NOTICE`、diagnostics 与 review-required 风险，不从普通 key diff 猜 move/interval 语义。 |
| 风险浏览与提示 | KEEP | 保留 RiskReport、annotation 原因及可用定位；不从 records 自行推断风险。 |
| 业务分组、节点、页签 | SIMPLIFY | FD6 占位为单一组、表为节点、无装置页签；保留全部表名、状态、统计、风险和数据访问，不推断尚未提供的业务分组。 |
| 列展示 | SIMPLIFY | 暂用原始列名和内容计算宽度；保留原始 schema/值，不虚构缺失的显示名、顺序、隐藏、固定或键列配置。 |
| 复合信号表与公式查看 | KEEP | History 与 Preview 都提供改前、改后对照。BE-b 在表有变化时，为 Preview 补齐 `composite_signal_point` 与 `device` 的基线侧整表；补齐前，Preview 中公式有变化的测点只显示上传侧公式并标“公式已改”。依据 owner 2026-11-02 确认的 main `bb6a09252a`（kickoff §8 与 BE-b 设计草案 §4.4）。 |
| 数据集替换双侧浏览与确认 | KEEP | 两侧 snapshot 独立浏览，保留 `identity_pairs` 与显式 `identity_confirmations`，不拼成普通 diff。 |
| 提交 | KEEP | 保留 submit attempt、幂等 key、预期版本和身份确认事实。 |
| 审核通过、退回、撤回 | SIMPLIFY | 保留审核人、决定、原因、时间和结果状态；“退回”映射 `REJECT`，移除 `START_REVIEW` 与 `RETURN_FOR_REVISION`。 |
| 归档主线（预检、异常处理、确认） | KEEP | 保留预检候选、影响、异常处理和确认事实，使用应用内确认。 |
| 历史比较（2/3 节点、比较对切换） | KEEP | 保留 2/3 节点与 pair 切换，按 bundle 的 pairs 与 snapshot refs 浏览。 |
| diagnostics 与 KEYLESS_FALLBACK 提示 | KEEP | 保留 diagnostics、fallback 原因和 review 提示；用可读说明呈现 backend 事实。 |
| 上传性能基准 Playwright 工具 | REMOVE | 不迁移 legacy 上传基准工具；P6 使用后端测量工具。 |

没有遗留“未判定”项。ordered 表只在 provider 输出事实时按事实浏览；合同未支持的语义不由前端补造。

## 与 kickoff 的偏差和设计问题

1. kickoff §3 标注核对时的 main 为 `b7d6e45406`，本实施会话按用户要求从创建 worktree 时的当前 `main` 起步，实际起点是 `7c339bff460254e19f36e81cb75028ca3a2702b1`。OpenAPI 来源和 worktree 基线均使用实际起点，未修改 `vnext/`。
2. `docs/backend-vnext/frontend-surface-simplification.md` 开头提及临时 legacy compatibility layer，与 AGENTS、FD1 和 kickoff 的“新建前端、legacy 只作参考、不建设兼容层”方向冲突。FE0 没有实现或引入兼容层。请设计/owner 确认该文档表述是否为过期内容。
3. 公式查看器数据来源已由 owner 于 2026-11-02 在设计会话通过 main `bb6a09252a` 确认：History 与 Preview 都提供改前、改后对照；BE-b 在表有变化时，为 Preview 补齐 `composite_signal_point` 与 `device` 的基线侧整表；补齐前，Preview 中公式有变化的测点只显示上传侧公式并标“公式已改”。详见 kickoff §8 与 BE-b 设计草案 §4.4。
4. OpenAPI 快照来自 BE-a 前的 backend，仍含 `RETURN_FOR_REVISION`；FE0 记录此来源，前端遵从 FD4，不把旧动作作为产品操作。BE-a 后刷新快照属于后续同步工作。
5. FE0 在 05 的默认权威入口及独立离线安装验证通过；04 阶段退出取证已按 kickoff §6 完成，见本 handoff 的“04 阶段退出取证”。

当前没有需要修改 `vnext/` 或后端行为的实施项；第 2 项文档表述冲突交 owner 处理，D1 公式数据来源已按上述设计结论记录，不在 FE0 自行改写 FD 或后端事实。

## FD7 恢复、DC68 记录与 05 测试日志

- 规则提交：`f0ad2461accf173354cb4fa45a0f132dc4d568e7`。FE 分支已 rebase 到该提交之上；本次实际测试候选 HEAD 为 `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2`。测试后只更新了本 handoff。
- 05 预检：`ssh -o BatchMode=yes ct108-gw-dms-05 'echo OK'` 成功，节点为 `gw-dms-test-05.lan`。工具链 tag 存在；已加载归档元数据中的 config digest 和七个 DiffID 与 CT201 来源相同，当前 daemon 的 RootFS layer 列表也相同。`docker inspect` 本机 ID 不作为跨节点身份。npm cacache 存在且为 603 MB；节点占用标记不存在。
- 先前按错误方式尝试克隆的旧候选 bundle `fe-vnext-test.bundle` 对应 `c87741db0de3b416eba658509ae8b6d800b13291`，本轮没有使用。它的 CT201 传输日志 SHA256 为 `09b6b69c54760fc8b2c9f8ef5dd96af3c149c605d5f7a1bf6e402c3ae41ffbd3`，旧 bundle SHA256 为 `6dde3db829a15afe4672b453f991ef59763b762e2e58669370f5b7073bca97c2`。
- 第一次 worktree setup 于 `2026-11-02 08:25:08Z` 在 05 失败，exit code `128`。root 执行 `git clone --shared --no-checkout /home/dev/gateway-data-management-system /home/dev/gdds-fe-test` 时，Git 因源仓库由 `dev` 拥有而报 `detected dubious ownership`。失败日志 `/home/dev/gdds-fe-logs/fe0/frontend-test-worktree-setup.log` SHA256：`e088cbe18e6bf91a488ff695198d785fcd350d3ad39853508ef09b6e0254d087`。
- 确认目标目录不存在、节点 main worktree 干净且未改全局 `safe.directory` 后，按 DC68 从准备步骤开头重做一次，于 `08:25:38Z` 将 clone 命令改为传入 `-c safe.directory=/home/dev/gateway-data-management-system/.git`。本地 clone 子进程仍报相同 ownership 错误，exit code `128`；重做日志 `/home/dev/gdds-fe-logs/fe0/frontend-test-worktree-setup-redo.log` SHA256：`7874a1c5bb2f2e3c2c5bde91a0e920a7ad533cfa4c102c4b54aa4d066ba8dfff`。重做后目标目录仍不存在，未改全局配置或 main worktree。
- 以上两次失败均未创建目标 worktree、未改全局 Git 配置或 main worktree，也没有触及被测对象；日志按 DC68 保留。设计会话确认原因是克隆方式不匹配 05 现有安全目录设置，并指定新的 bundle/fetch/worktree 流程。这次按指定流程从步骤 1 重新开始，不作为第三次 DC68 重做。
- 新 bundle：CT201 以 `b7d6e4540677d38117adde2885682ad5a4f4ce09..fe-vnext` 创建，候选为 `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2`；`fe-vnext-09730.bundle` SHA256 为 `d36a38782b4af00a99de16bfe6371435d6f0e01b495e1d82c900cf0ff4edafaa`。创建/传输日志 `source-bundle-09730.log` SHA256：`8a1940f4619d5b191e0df8c61a174b9cf1af6baf594bb8cb0c73abe80a173d7f`，时间 `08:34:10Z`，exit `0`。
- 05 在 `/home/dev/gateway-data-management-system` 对新 bundle 执行 `git bundle verify` 和 `git fetch <bundle> fe-vnext`；`FETCH_HEAD` 精确为 `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2`，main 仍为 `b7d6e4540677d38117adde2885682ad5a4f4ce09`，未移动 main、未创建分支。日志 `frontend-bundle-fetch.log` SHA256：`20254225c5ed8bec01c75f70fe1a76077fdf71dd26179c15a5b00b9987e030d7`，时间 `08:34:21Z`，exit `0`。
- 05 创建 `/home/dev/gdds-fe-fe0-05` detached worktree 并链接 `legacy`。worktree HEAD 与候选一致，状态 clean；日志 `frontend-test-worktree-add.log` SHA256：`b060ce493a5ae4ada2a615786aa766074a461b9ba634f56020691429972ad0fb`，时间 `08:34:47Z`，exit `0`。

### 05 测试日志

| 运行 | 节点 | 起止时间（UTC） | 起止 HEAD | exit code | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| 容器临时副本 `npm ci --offline`（network none） | `gw-dms-test-05.lan` | `08:35:18–08:35:24` | `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2` → 同一 HEAD | `0` | `5dd123972c3b10834ddbd74728771f2829a0bfd5ae8a5e3eab3a4753a8ee37e3` |
| `frontend/scripts/run-tests.sh`（`run_e2e=0`） | `gw-dms-test-05.lan` | `08:35:35–08:35:44` | `09730a57ffa99a07cc53c3b05c6dca0f1314b8e2` → 同一 HEAD | `0` | `22ced6a030176ab2f5f6a3466c4f6fb78b17f6c616bece939d7886cd1137a77b` |

日志分别为 `/home/dev/gdds-fe-logs/fe0/npm-ci-offline-20261102T083518Z.log` 与 `/home/dev/gdds-fe-logs/fe0/frontend-tests-20261102T083535Z.log`。权威入口内也再次完成一次离线安装。Vitest 显示 `No test files found`，由配置的 `--passWithNoTests` 正常 exit `0`；因此当前验证覆盖工程检查和构建，不包含业务单元测试断言。测试后确认 detached worktree 仍 clean、HEAD 未变；05 main 仍在原 HEAD。

## FE0 定向修复

### 提交与范围

- 代码修复提交：`d62eb3603747d3dceed2269c3cfc74be100b73e3`，复审范围为 `6c5dbcb1c41fb34bce0bf7a635d90135e860bd3e..` 后续 handoff 提交。05 三次成功运行均绑定到代码修复提交 `d62eb3603747d3dceed2269c3cfc74be100b73e3`；测试后只修改本 handoff，并单独提交。
- 改动仅在 `frontend/`；未修改 `package.json`、`.gitignore`、`vnext/`、AGENTS、kickoff、UI 优化方向或复审报告。

### B1：lockfile registry 身份（`d62eb3603747d3dceed2269c3cfc74be100b73e3`）

- 将 305 处 `resolved` 主机改为 `https://registry.npmjs.org/`，保留原 tarball 路径。lockfile SHA256：`811fa3dfbf22233738906335b35ec3e2abf0846f510a157cb69ff18db71f0f7c`。
- 与修复前锁文件逐项静态比较：305 个 integrity 值全部不变、305 个 tarball 路径全部不变、package 条目集合不变；`frontend/package.json` 未改。修复前锁文件快照 SHA256：`64e87a373bbded64d1d1cc63da179556895e2fe9fba6f8a6e51f1bd9a83b760b`。
- `run-tests.sh` 运行前检查 lockfile 的每个 `resolved` 必须使用官方 HTTPS 源；缺失或出现其他 source 时以 exit `2` 拒绝。README 说明 CT201 局域网 registry 只用于取包，lock source 保持官方。
- 使用既有 CT201 缓存，未重新预填充。缓存原始生成提交为 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4`；其 `package.json` 与 `package-lock.json` blob 和分支 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 相同。新锁文件提交为 `d62eb3603747d3dceed2269c3cfc74be100b73e3`，05 离线安装证明旧缓存可用于新官方 lock source。归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，CT201→05 原预填充时间 `2026-11-02 08:14:24–08:14:51 UTC`；本次未重新传输缓存。

### B2：Playwright 冒烟（`d62eb3603747d3dceed2269c3cfc74be100b73e3`）

- 新增 `frontend/e2e/workspace-shell.spec.ts`，用例名“打开应用显示工作台骨架页”，启动 Vite dev server 并断言一级标题“网关数据工作台”可见；不连接 backend。
- Playwright `reuseExistingServer` 固定为 `false`。未使用 `--pass-with-no-tests` 或其他空跑选项；`--e2e` 日志确认 `1 passed`。

### N2–N6 与 N7

| 项 | 修复 | 对应提交 |
| --- | --- | --- |
| N2 | runner 日志记录并校验工具链镜像 RootFS DiffID 列表；记录 npm 缓存来源归档 SHA256。 | `d62eb3603747d3dceed2269c3cfc74be100b73e3` |
| N3 | 容器仅接收 `git archive HEAD frontend` 生成的 tracked source tar，忽略工作区被 Git 忽略的文件。 | `d62eb3603747d3dceed2269c3cfc74be100b73e3` |
| N4 | Playwright 不复用已有 dev server。 | `d62eb3603747d3dceed2269c3cfc74be100b73e3` |
| N5 | README 说明默认 `none` 仅适用于模拟接口；FE3 真实 backend e2e 需 host network 或可达的显式地址，并配置对应环境变量。 | `d62eb3603747d3dceed2269c3cfc74be100b73e3` |
| N6 | 日志、npm cache、cache archive 的默认路径均与阶段无关；可通过环境变量覆盖。 | `d62eb3603747d3dceed2269c3cfc74be100b73e3` |
| N7 | B1 后当前 lockfile 来源提交记录为 `d62eb3603747d3dceed2269c3cfc74be100b73e3`。B1 前分支提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 与旧 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4` 的 `package.json`、`package-lock.json` blob 相同。依 FD7 治理提交 `f0ad2461ac`，前端测试入口保持独立，不并入 `vnext` runner。 | 本 handoff 单独提交 |

N1 按要求保留到 FE1 再处理。D1 已由 owner 于 2026-11-02 在设计会话通过 main `bb6a09252a`（kickoff §8 与 BE-b 设计草案 §4.4）定为 KEEP：BE-b 在表有变化时，为 Preview 补齐 `composite_signal_point` 与 `device` 的基线侧整表；补齐前，Preview 中公式有变化的测点只显示上传侧公式并标“公式已改”。04 阶段退出取证已完成，见下节。

### 05 源码传输与 worktree

- CT201 以 05 已有祖先 `b7d6e4540677d38117adde2885682ad5a4f4ce09` 创建新 bundle `fe-vnext-d62eb36037.bundle`，候选 `d62eb3603747d3dceed2269c3cfc74be100b73e3`；SHA256：`a7310943b3dd58091a7ab4f7c26c2f3c2792f7dbfaa486e504b029f4fd99450e`。使用了新 bundle，未使用旧 `fe-vnext-test.bundle`。
- CT201 创建/传输日志 `/home/dev/gdds-fe-logs/fe0/fix1/source-bundle-d62eb.log`，SHA256 `659677191c92d65eca51c28956da725cf34c19dadb22edf752206d1f8fdd9dba`，时间 `09:50:32Z`，exit `0`。
- 05 在共享主仓库 verify/fetch 后，`FETCH_HEAD` 精确等于候选 `d62eb3603747d3dceed2269c3cfc74be100b73e3`；未移动 main、未创建分支。05 main 保持 `0d9ff6d5cd8d59509955c7ccf6ac9dddffa0b93c`。fetch 日志 `/home/dev/gdds-fe-logs/fe0/fix1/bundle-fetch.log`，SHA256 `78aef8c8e9f3dff80fe84a0acc3ce2190da0327d5b706d59dc659a4eeb8a2b6d`，时间 `09:50:40Z`，exit `0`。
- detached worktree `/home/dev/gdds-fe-fe0-fix1` 链接 `legacy`；HEAD 精确等于候选且 clean。worktree 日志 `/home/dev/gdds-fe-logs/fe0/fix1/worktree-add.log`，SHA256 `5096be15b810361d28de6edc03f8968bd65d6b5f0714beb6b596ef59e04e25b0`，时间 `09:50:50Z`，exit `0`。

### 05 三次运行日志

每份日志均记录 `gw-dms-test-05.lan`、UTC 起止时间、起止 HEAD、exit code；runner 日志另记录 DiffID、缓存归档 SHA 和 source archive SHA。三次均在 `network=none` 下运行，起止 HEAD 均为 `d62eb3603747d3dceed2269c3cfc74be100b73e3`。

| 运行 | 日志路径 | 起止时间（UTC） | exit code | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 工具链容器 standalone `npm ci --offline` | `/home/dev/gdds-fe-logs/fe0/fix1/npm-ci-offline-retry-20261102T095156Z.log` | `09:51:56–09:52:02` | `0` | `28a5d7fafde27b111b908c2287657d83b721921128afd11044231626f8e59b1b` |
| `frontend/scripts/run-tests.sh` 默认流程 | `/home/dev/gdds-fe-logs/fe0/fix1/frontend-tests-20261102T095215Z.log` | `09:52:15–09:52:25` | `0` | `6fa00b245f23364ac2e73c77bccdc26638d107869c5c8f136c18672854b96ee7` |
| `frontend/scripts/run-tests.sh --e2e` | `/home/dev/gdds-fe-logs/fe0/fix1/frontend-tests-20261102T095233Z.log` | `09:52:33–09:52:44` | `0` | `26ccf12bea16563928214ac219d91f7cc17906ff1462130d6bd92cebc90c753f` |

standalone 与 runner 内的离线安装均安装 280 个包。默认流程的 typecheck、lint、build 通过；Vitest 仍显示没有单元测试文件，并按保留的 N1 配置正常退出。E2E 运行实际执行冒烟用例并报告 `1 passed`。运行后确认测试 worktree clean 且 HEAD 未变。

### DC68 本轮操作参数错误

首次 standalone 命令的日志 `/home/dev/gdds-fe-logs/fe0/fix1/npm-ci-offline-20261102T095125Z.log` SHA256 为 `5cefa7d4da25556ab4483aff4b565199c2788080c16ffc137481b717c0fb5ba9`，起止时间 `09:51:25Z`、exit `2`。原因是预检脚本中的候选变量少录末位，导致 HEAD 对比失败；容器未启动、npm 未运行，也未改变 worktree。按 DC68 保留失败日志，从该步骤开头重做一次，候选改由 05 的 `FETCH_HEAD` 读取，standalone 安装成功。缓存 SHA 和镜像 DiffID 在失败预检中均匹配，没有缓存 miss 或镜像身份不符。

## 04 阶段退出取证

- **取证对象：** `ct108-gw-dms-04` 上的 detached worktree `/home/dev/gdds-fe-fe0-exit-04`，HEAD 为 `e22f510a82a143ccee76a1b3b3b6c854aa755129`，`frontend/` tree 为 `47e901a8485de1655142df89544f24f1a7e3402a`。取证期间 HEAD 与 worktree 状态未变化。
- **预检：** CT201 为 `heavy-dev-01.lan`，fe-vnext 在 `e22f510a82a143ccee76a1b3b3b6c854aa755129`，主工作区 HEAD 为 `26d3c6542be24a31b04748e7c6ea8f3ca3220a04`；日志 `/home/dev/gdds-fe-logs/fe0/exit-04/ct201-preflight.log`，SHA256 `6626bb0570510defa6e68ad9e958a8793e5da485388f65d6ce2d01afb7b38a7d`。04 为 `gw-dms-test-04.lan`，10:26:06Z 检查时 `/home/dev/gdds-node-busy.d` 不存在，主仓库 HEAD 为 `bb6a09252aabf2f4409eec4049e7e204a914e637`，目标镜像 tag 与默认 npm cache 目录均不存在；日志 `/home/dev/gdds-fe-logs/fe0/exit-04/04-preflight.log`，SHA256 `876aa3c18fa0560f9d2b526cbbce0159c5bfc24ce010cdc91e45d16344a64f5a`。
- **工具链镜像：** 04 原先没有 `mcr.microsoft.com/playwright:v1.64.1-noble`，因此从 CT201 新传归档。CT201 归档与 04 收件归档均为 SHA256 `5babfc35ed51468126d75d5996e4f744a4e58f5442a2a3bb0135630379be163c`；传输时间 `10:26:52–10:27:20Z`，04 加载时间 `10:28:01–10:28:19Z`。加载后按 05 使用的归档元数据方法导出并核对，config digest 为 `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，与 handoff 一致；没有比较 `docker inspect` ID。

  RootFS DiffID 顺序与全部七项均匹配：

  1. `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  2. `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  3. `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  4. `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  5. `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  6. `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  7. `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`

  传输日志 `/home/dev/gdds-fe-logs/fe0/exit-04/toolchain-transfer-04.log` SHA256 `93d314362eefeac2d88c60d31fcd2ce9aa9068df759a30b3922e2d377ac94ef8`；04 加载和身份核对日志 `/home/dev/gdds-fe-logs/fe0/exit-04/toolchain-load-verify.log` SHA256 `2e61565f17e36cf926dab717a3688d5cae1d062c069ded8b2b7a5a6a8e796e77`。
- **npm 缓存：** CT201 归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz` 的 SHA256 为 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；04 传输时间 `10:29:01–10:29:02Z`，解包到默认目录 `/home/dev/gdds-fe-cache/frontend/npm-cache` 的时间 `10:29:20–10:29:22Z`，大小 `603M`。缓存最初生成于 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4`；其 `package.json` 和 `package-lock.json` blob 与 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 相同，因此按 R1 在 runner 中填写 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`。传输日志 `/home/dev/gdds-fe-logs/fe0/exit-04/npm-cache-transfer-04.log` SHA256 `db2a8b1bacb0a3fa07ffe15b4d2f03c679dfb887b9e05cce8560dc5aaba33a7b`；解包及校验日志 `/home/dev/gdds-fe-logs/fe0/exit-04/npm-cache-prefill.log` SHA256 `d16855abe31d46e55ffb5d3eb23f4d02b646d9cff87ef9351a40985b524ca08d`。
- **源码 bundle 与 worktree：** CT201 创建 bundle 前再次确认 fe-vnext 为目标 HEAD、frontend tree 为 `47e901a8485de1655142df89544f24f1a7e3402a`；以 04 已有祖先 `f0ad2461accf173354cb4fa45a0f132dc4d568e7` 为基点创建 bundle，SHA256 `9d4375f8d9450a565bae97c1eef144a0e05dc1d81eccc163cd77a416ae25171c`。CT201 创建/校验日志 `/home/dev/gdds-fe-logs/fe0/exit-04/source-bundle-ct201.log` SHA256 `8d4afef61b3b2175526c2cf81453efc0a8bfa8cedca5ea34c78e2cd280719359`，时间 `10:29:35Z`；传输时间 `10:29:41Z`，传输日志 `/home/dev/gdds-fe-logs/fe0/exit-04/source-bundle-transfer-04.log` SHA256 `156f625bf36fdd966cd74e888b08ba7b5ac2451346f83986ca7c41192a19003b`。04 `git bundle verify`、fetch 后 `FETCH_HEAD` 精确等于目标 HEAD；日志 `/home/dev/gdds-fe-logs/fe0/exit-04/bundle-fetch.log` SHA256 `0ec47e0146a7c26ebac73f3e2194acd71d4f1afd68b09c24e1b1a4b1c7cd57e9`，时间 `10:30:56Z`。worktree 已建立 `legacy` 符号链接，HEAD 精确、clean；日志 `/home/dev/gdds-fe-logs/fe0/exit-04/worktree-add.log` SHA256 `2b6de37a18fb81cacdbd70022fba3929c2cf464174fe379022297ce4a370758a`，时间 `10:31:16Z`。
- **04 main 状态：** 本会话没有更新 04 的 `main`。预检后、bundle fetch 前，`main` 已由外部 `git pull --ff-only` 从 `bb6a09252aabf2f4409eec4049e7e204a914e637` 推进到 `17cc76174ba04d3a97eb1a1ca343a86cef7bc805`（reflog 时间 `10:28:10Z`）。fetch 和 runner 的前后检查均保持 `17cc76174ba04d3a97eb1a1ca343a86cef7bc805`；变更记录 `/home/dev/gdds-fe-logs/fe0/exit-04/main-movement-investigation.log` SHA256 `bcd454785e222b57c1128ecdf6c724869ec41f285ab678336e6c21b022c509c0`。

### 04 权威运行

| 节点 | 运行（UTC） | HEAD（起→止） | exit code | 日志路径与 SHA256 | 结果 |
| --- | --- | --- | --- | --- | --- |
| `gw-dms-test-04.lan` | `2026-11-02 10:32:34–10:32:45` | `e22f510a82a143ccee76a1b3b3b6c854aa755129` → 同 | `0` | `/home/dev/gdds-fe-logs/fe0/exit-04/frontend-tests-20261102T103234Z.log`；`31c8e57c458570e00b2ea6ad6004f958a599985b1da9cabc818a78b8b2f9083b` | typecheck、lint、build 通过；Vitest 未发现单测文件并按配置 exit `0`；E2E `1 passed` |

runner 使用默认 npm cache 路径和 `docker_network=none`。日志记录 `package_lock_resolved_count=305`、缓存归档 SHA256 `0d861824…0089f4`、缓存来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5` 与七个 DiffID。运行前检查日志 `/home/dev/gdds-fe-logs/fe0/exit-04/runner-precheck.log` SHA256 `107646f70a374843e97164dc3d759f4ff9d5f82843d78d0e296bd8d65a78aa55`；运行包装日志 `/home/dev/gdds-fe-logs/fe0/exit-04/runner-invocation.meta.log` SHA256 `096b95f31a1e3548cc3ff6c2755ff40c67b9502ece2d15c10b104ec30a878a06`。运行后 worktree 仍 clean，HEAD 与 frontend tree 均未变化。

### 04 DC68 操作错误记录

- bundle fetch 的首次保护检查在 `10:29:51Z` 发现 `main` 已从预检 HEAD 前进，因此在 `bundle verify` 和 fetch 前停止，观察到 exit `21`，没有副作用。失败日志 `/home/dev/gdds-fe-logs/fe0/exit-04/bundle-fetch-attempt-1.failed.log` SHA256 `57ec36755ed2f1e81e0c2be98d5bd924b3903eeb1e7b4a82bb9cd221153cd15c`；保护检查记录和 main reflog 分别见 `bundle-fetch-attempt-1-preservation.log`（SHA256 `dc38b4c0c26cf09e5c5791f8efd4c16b85cbd29373541f87a21a05208ba3fa71`）与 `main-movement-investigation.log`。当时的日志包装在函数内使用 `exit`，未写入结束标记；保留原日志后改用函数返回码并补齐 footer，从 bundle verify 开始重做，`bundle-fetch.log` exit `0`、`FETCH_HEAD` 精确匹配。
- 运行后一次只读证据查询误用 04 未安装的 `rg`，两个子命令返回 `127`，SSH 包装命令因后续读取成功而总体返回 `0`；没有改动取证对象或日志。错误记录 `/home/dev/gdds-fe-logs/fe0/exit-04/postrun-evidence-query-attempt-1.failed.log` SHA256 `0d4bf2920ce80724d0b566573b9d2de4b9b83c2cceaee867e57e4c07d9a3eab7`；修正为 `grep` 后的证据核对日志 `/home/dev/gdds-fe-logs/fe0/exit-04/postrun-evidence-check.log` SHA256 `12a9ecc4afdbd62e45ac847ceb24dce185535a2b84b96f69b34d542be6c3d2ee`。权威 runner 只运行了一次。
