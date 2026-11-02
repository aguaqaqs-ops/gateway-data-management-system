# FE1 证据核对（第 1 轮）

- **核对对象：** FE1 在 04 上的阶段退出取证。
  - 被测代码候选：`c5ee9a06bc8f2502f8b5299d2b8cd657441797de`，`frontend/` 树 `8e553cbf49`；
  - handoff 提交：`a42139222fa8dcac8fb4ba2910cc76f51c447ad8`，父提交为 `7732c4140e`（复审第 2 轮的终点）。
- **依据：** kickoff §6、§7；[FE1 复审第 2 轮](fe1-rereview-2.md) §6。
- **日期：** 2026-11-02。
- **结论：PASS。** 04 的权威运行有效，可以作为 FE1 阶段退出证据。FE1 可以交 owner 确认退出。

## 1. 范围

`7732c4140e..a42139222f` 只改动了 `docs/frontend-vnext/fe1-handoff.md`。`frontend/` 树仍是 `8e553cbf49`，与复审第 2 轮通过的代码一致。04 运行检出的是代码候选 `c5ee9a06bc`，不是 handoff 提交。

## 2. 04 权威运行

运行日志为 04 上的 `/home/dev/gdds-fe-logs/fe1/exit-04/frontend-tests-20261102T160855Z.log`，SHA256
`c1df171de4339e5a64b5bd5ad8e9b6e06ef7af63ef932519894bfebd4b481655`，与 handoff 一致，sidecar 校验通过。我在 04 上逐项读取了日志内容：

| 项 | 日志内容 |
| --- | --- |
| 节点 | 起止的 hostname 都是 `gw-dms-test-04.lan` |
| 时间 | `16:08:55Z`–`16:09:10Z` |
| HEAD 和树 | 起止都是 `c5ee9a06bc`；`frontend/` 树起止都是 `8e553cbf49` |
| 工具链 | 7 个 RootFS DiffID 与固定值一致，runner 检查通过 |
| 缓存 | 默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 SHA256 `0d861824…089f4`，来源提交 `a2fb4a027a` |
| lock source | `package_lock_resolved_count=305` |
| 网络 | `docker_network=none` |
| 步骤 | 离线安装 280 个包；typecheck、lint、build 通过；9 个测试文件 38 项通过；e2e 3 passed |
| fixture | `bundle_digest` 为 `sha256:a34e8560…4538`，`closure_manifest_digest` 为 `sha256:db3dec9c…7b5e`，tar SHA256 `df9f9127…4735`；与后端产物以及 05 上的各次运行相同 |
| 结果 | `exit_code=0` |

- 权威 runner 只运行了一次，没有 DC68 重做。
- 运行后的状态：
  - worktree `/home/dev/gdds-fe-fe1-exit2-04` 是 detached HEAD `c5ee9a06bc`，clean，`legacy` 符号链接指向主仓库；
  - 占用标记不存在；
  - 04 的 main 是 `0e0d14f1d1`。reflog 显示 main 最后一次移动是在 `14:09:14Z`，早于这次运行，运行期间没有移动。
- 原候选 `b67da4795f` 的 04 运行和 worktree `/home/dev/gdds-fe-fe1-exit-04` 保留为历史记录，没有被复用。

## 3. 制品与环境身份

- **工具链镜像：**
  - 04 上 `docker image inspect .RootFS.Layers` 列出的 7 个 DiffID，与 handoff、runner 固定值逐项一致；
  - `toolchain-image-identity-04.json` 由 `docker save` 导出，其中 config digest 是 `sha256:a0d7b2b4…a1017`，DiffID 列表也一致；
  - 解析脚本在 04 上的副本，SHA256（`c205c3c0…9a45`）与候选中的 `frontend/scripts/docker-save-image-identity.py` 相同；
  - 没有比较 inspect ID。
- **npm 缓存：** 04 上的归档 SHA256 为 `0d861824…089f4`，与 FE0 预填充相同。
- **源码：**
  - CT201 与 04 上的 bundle SHA256 都是 `f09109ce…176e`；
  - 它和我复审第 2 轮生成的 bundle 也相同：两者的前置提交都是 `36047efe5a`（我写的 `^0e0d14f1d1` 不是 `fe-vnext` 的祖先，git 实际取的边界也是 `36047efe5a`），引用都是 `fe-vnext` → `7732c4140e`。

## 4. 日志 SHA256

handoff 列出的日志 SHA256 全部一致：

- **04 侧：**
  - `preflight-04.log`（`1a45da08…6ba`）
  - `toolchain-image-identity-04.log`（`6eb1b815…8df`）
  - `toolchain-image-identity-04.json`（`4961e044…dfc`）
  - `bundle-fetch-04-7732c4140e.log`（`52788c27…477`）
  - `worktree-add-04-c5ee9a06bc.log`（`c16b663d…2ab`）
  - runner 日志（见 §2）
- **CT201 侧：**
  - `source-bundle-create-7732c4140e.log`（`313afe94…f23`）
  - `source-bundle-transfer-04-7732c4140e.log`（`3189cd7b…444`）
  - `image-identity-script-transfer.log`（`5aeeb0ac…052`）

## 5. FE1 退出条件（kickoff §7）

| 条件 | 状态 |
| --- | --- |
| A：认证封装、API 客户端、轮询与幂等、bundle 本地化与解析、视图模型、命令层 | 已完成。B1、B2、B4 已修复；N1、N2、N4、N6 按约定留到 FE2 |
| A 用 golden bundle 与模拟接口覆盖全部旅程的数据流 | 满足。fixture 由后端生产代码产出，可逐字节复现；跨实现摘要测试和行风险测试都已经变异探针验证 |
| B：token、组件、表格主题、对话框，覆盖 UI 优化方向 P1、P2 | 满足。B3 已修复 |
| 04 阶段退出取证 | 满足（本报告） |

## 6. 建议

1. **退出：** owner 确认 FE1 退出后，由设计会话把附注 tag `fe-fe1-exit` 打在 `a42139222f` 上（handoff 提交，代码候选在它的祖先链上，`frontend/` 树与被测代码相同），然后合入 `main`。
2. **带入 FE2 的事项：**
   - N1（按用户意图复用幂等 key）、N2（轮询超时与临时错误）要在接入按钮和进度界面之前完成；N4、N6 也在 FE2 处理；
   - R4：本地搜索要跳过二进制行标识，也不要匹配值结构中的 `kind` 字段；
   - token 补上行分隔色 `#EEF1F4`；
   - 导航 diagnostics 按 BE-b §4.7 改为单独的 `diagnostics_ref` 产物，去掉 `diagnosticText`，并按文案表做用户可见的文案；
   - FE2 起按 kickoff §6 截图验收；FD5 侧栏从 FE2 起审。
3. **合入后可以清理：**
   - 审核会话：开发主机上的 `/home/dev/gdds-fe-rereview1-fe1-91828221`、`/home/dev/gdds-fe-rereview2-fe1-7732c414`；05 上的 `/home/dev/gdds-fe-rereview1-fe1-91828221-05`、`/home/dev/gdds-fe-rereview2-fe1-7732c414-05`；
   - 实施会话：05 上已被取代的 FE1 调试 worktree（`gdds-fe-fe1-*-05`）；04 上的 `/home/dev/gdds-fe-fe1-exit-04` 和 `/home/dev/gdds-fe-fe1-exit2-04`。

   证据目录 `/home/dev/gdds-fe-logs/fe1/`，以及各节点的工具链镜像、npm 缓存和后端依赖镜像 `gateway-backend-deps:lock-d054366c02fa`，都保留供 FE2 使用。
