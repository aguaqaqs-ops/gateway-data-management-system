# FE2a 证据核对（第 1 轮）

- **核对对象：** FE2a 在 04 上的阶段退出取证。
  - 被测代码候选：`a80a2e93af663cda6f4f972a0840df5142df4cea`，`frontend/` 树 `f1c238248a`；
  - handoff 提交：`e301cc0f88427b390bbeef009e2b2f7058bddc0a`，父提交为 `c1b8fc818a`（复审第 2 轮的终点）。
- **依据：** FE2 kickoff §7.3、§7.4；[FE2a 复审第 2 轮](fe2a-rereview-2.md) §3.3、§5。
- **日期：** 2026-11-03。
- **结论：PASS。** 04 的权威运行有效，可以作为 FE2a 阶段退出证据。还需要 owner 看图确认无草图页面（§5），然后才能退出。

## 1. 范围

`c1b8fc818a..e301cc0f88` 只改动了 `docs/frontend-vnext/fe2a-handoff.md`，`frontend/` 树仍是 `f1c238248a`，与复审第 2 轮通过的代码一致。04 运行检出的是代码候选 `a80a2e93af`，不是 handoff 提交。

## 2. 04 权威运行

运行日志为 04 上的 `/home/dev/gdds-fe-logs/fe2a/exit-04/frontend-tests-20261103T092014Z.log`，SHA256 `1fd6443994825992aace3e729eee424ab03cd557cab1e0fa6d8c87fc009ab105`，与 handoff 一致，sidecar 校验通过。我在 04 上逐项读取了日志内容：

| 项 | 日志内容 |
| --- | --- |
| 节点 | 起止的 hostname 都是 `gw-dms-test-04.lan` |
| 时间 | `09:20:14Z`–`09:20:39Z` |
| HEAD 和树 | 起止都是 `a80a2e93af`；`frontend/` 树起止都是 `f1c238248a` |
| 工具链 | config digest `sha256:a0d7b2b4…a1017`，7 个 RootFS DiffID 与固定值一致；04 上 `docker image inspect` 的 DiffID 列表也一致 |
| 缓存 | 默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cache`；来源归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，SHA256 `0d861824…089f4`（我在 04 上重算一致），来源提交 `a2fb4a027a`。没有使用节点上重新打包的副本 |
| lock source | `package_lock_resolved_count=305` |
| 网络 | `docker_network=none` |
| 步骤 | 离线安装 280 个包；typecheck、lint、build 通过；生产包检查通过；17 个测试文件 72 项通过；e2e 4 passed |
| 截图 | `screenshot_dir=/home/dev/gdds-fe-evidence/fe2a/a80a2e93af-04` |
| 结果 | `exit_code=0` |

- **外层日志：** `runner-wrapper-04.log`（`16f3846c…8dbe`）、`preflight-04.log`（`ad26c685…73cf5`）重算一致。
- **重做：** 权威 runner 只运行了一次，没有 DC68 重做。
- **运行后的状态：**
  - worktree `/home/dev/gdds-fe-fe2a-a80a2e93af-04` 是 detached HEAD `a80a2e93af`，clean，`legacy` 链接指向主仓库；
  - 占用标记不存在；
  - 04 的 main 是 `c18b9b0993`。reflog 显示 main 最后一次移动在 `06:50:39Z`，早于这次运行。
- **源码传输：** 这次用的是 `fe-vnext` 的完整历史 bundle（`f6222aa9…625f`），开发主机和 04 上的副本 SHA256 一致；`FETCH_HEAD` 为 `c1b8fc818a`。

## 3. 截图

- 04 证据目录中有 30 张截图，SHA256 与 handoff §10 的表格逐项一致。
- 与我在 05 上为复审第 2 轮拍的截图比较：29 张逐字节相同；`bundle-error-1280.png` 不同，我对照了图像，内容相同，只是像素级渲染差异。
- 草图对照的结论与复审第 2 轮 §2 和复审第 1 轮 §4 相同，没有新的偏差。

## 4. 缓存来源勘误

handoff §8、§9 已按复审第 2 轮 §3.3 更正：05 上的 `91ccf614…` 注明为节点本地重新打包的副本，内容与 FE0 归档相同；权威来源为 CT201 的 FE0 预填充（来源提交 `a2fb4a027a`，归档 `0d861824…089f4`）。**通过。**

## 5. FE2a 退出条件（FE2 kickoff §2、§7）

| 条件 | 状态 |
| --- | --- |
| FE2a 范围（§5.1–§5.6）：两行顶栏、侧栏 A、页签、S4 表格呈现、变更定位与分布条、仅看差异、表级状态、ordered 与 blank、数据集替换、公式查看、诊断、Debug、加载与错误页、URL 状态 | 已完成（审核 B1–B9，复审 N1、N2） |
| FE1 带入项 R4、N4、N6、行分隔色、D1、视图按比较对区分 | 已完成，相关项都经变异探针或类型探针验证 |
| fixture 由后端生产代码产出，可逐字节复现（§7.1） | 满足；213 个文件，我在 05 上独立复现 |
| 截图验收（§7.3）：S3、S4 逐张对照 | 满足。已知差异：模式操作区为空（§5.1）；`grid-main` 只含 v1 产出的风险等级（§7.1）；Preview 没有改前公式（§5.4） |
| 无草图页面交 owner 看图确认（§7.3、Q5） | **待 owner 确认。** 截图见下 |
| 04 阶段退出取证（§7.4） | 满足（本报告） |

**请 owner 查看的截图**（04 上的 `/home/dev/gdds-fe-evidence/fe2a/a80a2e93af-04/`，每项有 1280 和 1920 两张）：

- `formula-preview`、`formula-history`：公式抽屉。待定事项 R7：一元运算符目前显示为分组，规则要求直接作为前缀；请决定在 FE2a 内修，还是留到 FE2b。
- `dataset-replacement-browse`：数据集替换的双侧浏览（确认操作属于 FE2b）。
- `loading-skeleton`、`bundle-error`：加载骨架和错误页。
- `navigation-fallback`：没有导航产物时的单组回退。

## 6. 建议

1. **退出：** owner 确认上述截图（以及 R7 的处理方式）后，由设计会话把附注 tag `fe-fe2a-exit` 打在 `e301cc0f88` 上（handoff 提交；代码候选在它的祖先链上，`frontend/` 树与被测代码相同），然后合入 `main`。如果 owner 要求在 FE2a 内修 R7，则需要新候选、一次针对性复审和一次新的 04 运行。
2. **带入 FE2b：**
   - R2：token 来源、URL 中的 bundle 地址脚手架、生产构建检查的禁止模式；
   - R5：连接状态目前固定为“已连接”；
   - R7（如果没有在 FE2a 内处理）；
   - FE1 留下的 N1、N2，要在接入按钮和进度界面之前完成。
3. **合入后可以清理：**
   - 审核会话：开发主机上的 `/home/dev/gdds-fe-review-fe2a-57e77505`、`/home/dev/gdds-fe-rereview1-fe2a-c1abe10c`；05 上的 `/home/dev/gdds-fe-review-fe2a-57e77505-05`、`/home/dev/gdds-fe-rereview1-fe2a-c1abe10c-05`、`/home/dev/gdds-fe-rereview2-fe2a-c1b8fc81-05`；
   - 实施会话：已被取代的 05 worktree（`gdds-fe-fe2a-*-05`）；04 上的 `/home/dev/gdds-fe-fe2a-764d952757-04`、`/home/dev/gdds-fe-fe2a-a80a2e93af-04`；04 上的传输 bundle `/home/dev/gdds-test-tmp/src-fe-vnext-c1b8fc81.bundle`；05 上重新打包的缓存副本 `fe2a/npm-cache-prefilled-a2fb4a02-05.tar.gz`。

   证据目录 `/home/dev/gdds-fe-logs/fe2a/`、`/home/dev/gdds-fe-evidence/fe2a/`，以及各节点的工具链镜像、npm 缓存和后端依赖镜像 `gateway-backend-deps:lock-d054366c02fa`，都保留供 FE2b 使用。
