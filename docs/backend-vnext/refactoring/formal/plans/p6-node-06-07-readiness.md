# 06/07 开发测试节点启用核对

日期：2026-11-06 UTC。协调会话：`01a1ac15-9b35-7ea0-9952-c4a31d3d4f6d`。
依据：Owner 本轮节点启用指令、[DC82](p6-s0-owner-decisions.md#dc82-新增后端与前端开发测试节点)及随后关于自主并行的补充。

## 1. 结论与边界

两个节点已具备其指定用途的日常开发测试条件。06 的 Rust/扩展/Contract 与小规模 Compose、07 的前端静态/单元/构建/mock e2e/截图均实际通过。初次启用时 06 为 16 vCPU / 32 GiB、07 为 8 vCPU / 16 GiB；06 已于 2026-11-07 扩容至 96 GiB，见下方实核记录。构建/浏览器并发仍按实际任务控制。

### 2026-11-07：06 内存扩容

Owner 完成 CT107 内存 32→96 GiB 扩容，CPU/cpuset 与磁盘保持不变。03:40:36Z 通过 BatchMode SSH 实核：`MemTotal=103079215104 bytes`（96 GiB）、`nproc=16`、cpuset `64-79`，swap 8 GiB 未使用；guest 根盘 295G、已用 134G、可用 147G。Docker 29.9.1 / Compose v5.6.0 可用，无运行容器或测试/构建进程。uv/Cargo 缓存目录、测试 worktree 根目录及现用 backend/Repository dependency-base tags 保留；此次只核可用性与存在性，不重新声明全部缓存内容已校验或门禁通过。运行前仍按候选核依赖与镜像身份。

节点日志 `/home/dev/gdds-test-tmp/artifacts/s2b-ct107-memory-expansion-20261107/post-expansion-check.log` SHA256 `b871048d3922eb58dd53fc5826f85720464712386bf5f59c71695b0324a1cc99`。精确核对本会话维护 token 后于 03:40:47Z 释放标记，`release.log` SHA256 `043f4ac5e9e5ee1f05d1761e326780fc9af87ac42f2716f95f46feb9c3537247`；没有启动测试、清理缓存或变更被测代码。

Owner 提供的宿主快照：物理 251G；名义分配 240G（VM106 64 + CT108-04 64 + CT107 96 + CT109 16），另有宿主基底；现用 71G、available 180G。此为 Owner 报告，非容器内独立测得；支持当前并行安排，但不代表所有 guest 同时用满上限时仍有 180G 余量。保持既有自主取用与实际干扰时协调规则，不新增常规审批。扩容不改变正式性能/权威门禁节点职责；当前 a10 t3 校准继续在 CT108，未迁移或重启。

Owner 确认 04/06/07 同物理宿主且资源宽裕，不与 CT108 测量节点同宿主。已通过 `read_thread` 核对原设计会话中“不需要过于纠结于资源抢占”“并行开发会话不必为两个新增节点的资源问题与当前总协调会话通信”的原话。06/07 日常自主并行，不建立常规整宿主互斥或向原基准线申请窗口。各节点自己的有效占用、服务/端口与同节点计时独占规则保留，实际干扰时协调。早期保守登记的 04 共享宿主占用已于 03:22:21 释放，04 未运行测试。

这是节点启用核对，不是 S2a/S2b 阶段退出审核。06 的 S2a 候选验证不代替原 04 门禁、05 正式差分，也不使新节点具有跨节点 carried 资格。S2a 仍须核对主线/新增修复影响，由适格独立审核者确认沿用或定向补验，再办理合入与 exit。S2b 仍须收口映射、消费者与覆盖移交、必要容量、N/M 接线及恢复验收；节点就绪不构成全部产品改动的无条件授权。W2/性能条款按 DC81 讨论，未知值不记为通过。原基准线及 W4 租约故障仍独立跟踪。

## 2. 初次启用时的节点与离线环境（2026-11-06）

| 项 | 06 | 07 |
| --- | --- | --- |
| CT / SSH | CT107 / `ct107-gw-dms-06` | CT109 / `ct109-gw-dms-07` |
| hostname | `gw-dms-06.lan` | `gw-dms-07.lan` |
| LAN / MAC | `192.168.233.207` / `42:01:04:10:07:01` | `192.168.233.208` / `42:01:04:10:09:01` |
| nproc / cpuset / guest 内存 | 16 / 64–79 / 32 GiB | 8 / 80–87 / 16 GiB |
| thin 配额 / 验证后 guest df | 300 GiB / 295G，总已用 102G、可用 178G | 200 GiB / 196G，总已用 100G、可用 87G |
| 职责 | Rust、focused/Contract/差分、小规模 Compose | 类型检查、lint、单测、构建、截图、mock e2e |
| 初始并行参数 | `CARGO_BUILD_JOBS=4`；pytest workers 建议 4，serial/focused 本次用 `-n 0` | `GATEWAY_FE_TEST_WORKERS=2` |

这些测试参数与产品 kernel N/M 分开。磁盘已经带入约 92G 克隆内容；没有擅自删除旧 worktree、镜像、卷或日志。guest `df` 不是宿主 thin pool 的物理可用量；本轮未取得宿主 data/metadata 水位，管理员按常规监测，不新增日常开发审批。并发运行结果只说明功能可用，不是正式性能或生产容量证明。

两节点 BatchMode SSH 可用；原主工作区均保持 `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3` clean。工具链为 Rust/Cargo 1.97.0、uv 0.11.28、Dolt 2.1.11、Docker 29.9.1 / Compose v5.6.0；在 `vnext/rust` selector 下核对 rustc/cargo/rustfmt/clippy。宿主不安装 Node，前端使用固定 Playwright 工具链镜像。

克隆环境修正均只作用于新节点：

- root 非交互 SSH 的 PATH 前置 `/home/dev/.cargo/bin`；未设置 `RUSTUP_TOOLCHAIN`、`RUSTUP_HOME`、`CARGO_HOME`，不设置全局默认 Rust toolchain。
- root Dolt 配置关闭 versioncheck/metrics；私有测试 HOME 继续由既有代码配置。
- 空闲 Docker daemon 的克隆 engine ID 重复。备份旧 ID 后重启生成不同 ID：06 `efb41f53-d753-446e-b267-571cb9f21d67`，07 `ba000588-6648-4bb9-8b84-8d899adb9826`；前后完整镜像清单一致。此 ID 是 daemon 身份，不用于跨节点镜像等价比较。

根配置备份在各节点证据目录内保留，不公开其中的私有配置。测试使用本机预填缓存，Python/Cargo 离线，无转发代理；Docker build network 为 `none`，前端工具链容器也为 `none`。两个 CT 无公网默认路由；本轮不通过公网探测来验证隔离。

## 3. 源码与制品来源

所有测试在新建 clean、已提交 detached worktree 进行，`legacy` 链接到节点原参考目录；未在开发主机运行测试。

| 节点 / worktree | 起止提交与用途 |
| --- | --- |
| 06 `/home/dev/gdds-node06-s2a-c3c95282` | `c3c95282bfe90f2d2fd0f2110b7be9bfa134ab38`；现有 S2a 候选的 Rust/Contract/Compose 节点能力核对 |
| 06 `/home/dev/gdds-node06-main-667c6852` | `667c6852d19fde08cb8cd260619ded646611fd74`；当前主线五包 Ruff/mypy |
| 07 `/home/dev/gdds-node07-frontend-667c6852` | `667c6852d19fde08cb8cd260619ded646611fd74`；首次前端检查，e2e exit 1 |
| 07 `/home/dev/gdds-node07-frontend-55d56efb` | `55d56efb6e6803194f3fd9e5d38ac95932a52eee`；显式 2 workers 修正后检查，exit 0 |

CT201 经 LAN 传输 Git bundle；首个 bundle SHA256 为 `3a352b27550774cfd3d186181b892f2504185fffa316527abf02379a58413baf`，worker 修正 bundle 为 `70dc4c8f274f883e8da5ba30eef00361b287b633d6e6776f23c8a9c1a622c022`。主线期间的原基准诊断文档提交保留，未改写。五包静态检查后新增代码只在 `frontend/scripts/run-tests.sh`，不影响 backend 闭包。

本轮复用 CT201 已有归档，不重新下载/构建依赖；传输总窗口 03:10:00–03:10:44（06 制品至 03:10:21，07 制品至 03:10:44）。06 加载/身份核对窗口 03:10:57–03:11:45；07 为 03:10:58–03:11:48。原始目录均在 CT201：

| 制品 | 来源 / SHA256 |
| --- | --- |
| backend dependency-base | `/home/dev/gdds-p6-artifacts/s2a/gateway-backend-deps-lock-d054366c02fa.tar`；`3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6` |
| Playwright 工具链 | `/home/dev/gdds-fe-logs/fe0/playwright-v1.64.1-noble.tar`；`5babfc35ed51468126d75d5996e4f744a4e58f5442a2a3bb0135630379be163c` |
| npm 缓存 | `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`；`0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；来源提交 `62cd5d5641fce9447c1c6422dfd42ff8a28b5ac4` |

backend 归档来源：CT201 clean 提交 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`，2026-10-31 23:03:02–23:04:41 构建，exit 0；完整输入摘要 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`。来源 build 日志 `/home/dev/gdds-p6-logs/s2a/dependency-base-132fc621d5-ct201.log`，SHA256 `1f673c30f48b7f7f77afa3fdc41fbf5bc75f94f2d03da81cbed840173fd88e7b`。逐项输入见提交 `c3c95282bf` 的 `p6-s2a-handoff.md` §6：

| 输入 | SHA256 |
| --- | --- |
| backend pyproject | `4c091e36d4762f11b4085f207528548502ae723e7876d2feeeedcd4cd56f9c7f` |
| backend uv.lock | `d18d89a24a8acae02eb6b3b23c342c1b673ea0e7e87add93d0762edfa18b822d` |
| backend .python-version | `3a55324cbeddc91df012407d051dad08c88624c95a82fbdb856728729fbd14ab` |
| Rust Cargo.lock | `bac3443e4d16c22ed16adaadbaf3d3e7b713d78516e14938cdbca50ebd837d29` |
| Rust selector | `0506c53cddc8435a55513d5f662c302ff6eb4035f012d5d5e5a47e96a7f40420` |
| `rust:1.97.0-bookworm` config digest | `sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1` |

backend/worker 使用 `gateway-backend-deps:lock-d054366c02fa`，保留 Compose 本机构建、预置依赖开关与 `network=none`，未设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。Repository Service 从已在本机的 `gateway-p2r1-repository:lock-6dc9659f0aee` 构建独立新 tag `gateway-node06-rs:c3c95282`；candidate `c3c95282bf`，build-input `3b3d9c97bc`，source-tree `sha256:ee92f50f55fd9a134ddc1684aabc64fff32a32bffba680f5139cb9e692fe4015`。

新传输镜像经 `docker save` 解析，目标 config digest 和全部 RootFS DiffID 与原归档逐项一致，完整列表见本文末尾。不用本机 inspect ID 作跨节点等价。npm 缓存只读挂载，容器内 `npm ci --offline` 实际成功安装 280 包。

## 4. 实际验证与失败处置

以下时间均为 2026-11-06 UTC，日志含 hostname、起止 HEAD、exit code；日志与截图在 worktree 外。

| 节点 / 时间 | 验证与结果 |
| --- | --- |
| 06 03:13:19–03:15:50 | 五包离线准备；强制重装 Rust 扩展，build-input 与 Rust tree `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4` 相同；fmt、workspace clippy 通过；table_access Rust **15 passed**；adapter/SQL limits/storage projection/snapshot materialization **44 passed**；五包 Ruff/mypy 通过；exit 0 |
| 06 03:18:45–03:20:27 | 主线 `667c6852d` 五包离线同步及 Ruff/mypy 通过；exit 0 |
| 06 03:20:34–03:22:07 | RS 离线构建；既有 `test_compose_three_process_submit_stack_smoke_and_backend_restart` **1 passed**（81.70 s），涵盖三服务启动、health/readiness、backend 重启、工作区创建、清理；exit 0 |
| 07 03:13:40–03:14:42 | 首轮 typecheck/lint、**143 单测**、build/production-build check 均通过；mock e2e 默认启动 **34 workers**，32 passed / 2 failed，整次 exit 1，不作成功证据 |
| 07 03:21:14–03:23:00 | 提交 `55d56efb6e`，显式 **2 workers**；typecheck/lint、**143 单测**、build/production-build check、**34 mock e2e** 均通过，exit 0；1280 与 1920 各 **48 张截图** |

首次前端失败分别为大页面截图旅程的 `page.goto` 超时，和 History 连接中断状态未在断言期限内出现。新入口允许 `GATEWAY_FE_TEST_WORKERS` 正整数，记录实际值并显式传 Playwright；未设置时保留原默认。`bash -n` 通过，值 `0` 在启动容器前返回 2。只限制并发，不修改产品行为、测试断言或 timeout；两项失败在 2 workers 下均通过。该结果支持受限并发作为 07 的运行配置，不把一次复验表述为排除了所有潜在时序问题。首次失败日志及其截图另存，未覆盖；失败 container 内未外置的 trace 已随 `--rm` 删除，不声称保有 trace。

另有两类检查命令问题：初次 Rust 预检因 root PATH 缺 Cargo 返回 127，原工具输出保留在本会话（06 chunk `83d68f`、07 `f82e22`），修正 PATH 后预检通过；末态核对误在 selector 外调用 Cargo 返回 1，保存原日志与 SHA 后改到 `vnext/rust`，整步重做通过。均未触及产品运行，不充作测试通过证据。最初 Dolt 版本探测还发出联网查询警告，关闭 versioncheck 后未再发生；无公网下载成功。

06 于 03:23:16、07 于 03:23:42 核对 worktree clean、无活动容器/Dolt、8000 无监听后释放本次标记。构建缓存及证据保留；未清理其他会话或克隆带入的历史产物。所有本轮占用已释放，未触碰 05/CT108 测量资源。

## 5. 后续执行与证据复用

- 06：按单步改动运行 owning Contract/focused、Rust 与 Python 适配器差分；改动 Rust 后先重装扩展、核 build-input。只有触及容器边界的步骤补对应 Compose 检查，不逐轮跑完整 runner 或真实数据全旅程。
- 07：运行前端入口时显式 `GATEWAY_FE_TEST_WORKERS=2`；日常按改动范围选择检查，需截图时输出到 worktree 外。真实 backend e2e 仍在 05，阶段最终候选完整前端入口仍在 04。
- 04：S2a 沿用判断必须在原证据同节点、同 worktree 计算；当前主线/共享修复的受影响包定向补验，由独立审核者确认。S2b 最终候选完成 owning Contract 与必要容器/恢复门禁；最终完整门禁不因新增节点或旧基准通过而豁免。
- CT108：原设计/实施线继续正式测量与故障诊断；开发线不重启、不接管。缺少全量性能值不统一阻塞无关功能开发，但正确性、取消/截止、租约、事务/CAS、冻结产物和资源上限仍须验证。

本次未跑六包权威 runner、完整真实数据旅程、正式测量或重新生成合成输入；没有为节点启用重复 S1a/S1b/S2a 实施。文档更新无需重建后端镜像：本次代码只改 frontend runner；06 容器结果只绑定上述 S2a 提交，不能写成当前 main 产品门禁通过。

## 6. 证据索引

原节点证据根均为 `/home/dev/gdds-test-tmp/p6-nodes-06-07-20261106`，日志/身份副本在 CT201 同路径下 `06/`、`07/`。前端 runner 原日志分别在节点的 `frontend/` 与 `frontend-workers/`；截图在 07 的 `screenshots/`（失败轮）与 `screenshots-workers-2/`（通过轮），截图逐文件 SHA 清单记录绝对路径。以下索引均相对于 CT201 证据根；不含私有配置备份。

| 文件 | SHA256 |
| --- | --- |
| `lan-prefill.log` | `74776203d175c12921b5f5fec7c929ee6251b368976c14f51daf36c8f9dc2566` |
| `preflight-issues.md` | `5ef302836badb1a00f1fe1a290c1e32cac07bd601493d19437ffea92ba30a817` |
| `06/actual-image-identity.json` | `0c1d87ef97a48c5b1067a231407322a39d6d5d4f6912f2beba8cbcfe866249a8` |
| `06/backend-verification.log` | `8b7a1a958bf0f02c6e068c43d1e27d8c996c866daf407975a8d2de7d748c57e8` |
| `06/compose-rs-labels.json` | `c29ec3c36b8b6ca22d23c558c2a595fc9c09d082546bb99b837567164c9b6832` |
| `06/compose-verification.log` | `69b8941465809161a3443d5547438d83db1200f6f6df5daa5216718f09bfe170` |
| `06/main-static-checks.log` | `278b5d0fc3bbd2bb517bc9cbc0f400d010e9cc21f27d0bee9b84b0f5ed986ce6` |
| `06/node-final-state-attempt1.log` | `01c7b2fb7c17ecc2a25c571d38fda9ab85adc89154173e54e13a1859880352bb` |
| `06/node-final-state.log` | `af8d6186a815e6897a168010029284c06963d0e4995e67e3367bb514f53eca11` |
| `06/prepare-node.log` | `7e155c9a151b9c09b0b34721c6938b343a963ce3c83812870365221f248727ee` |
| `06/stage-node.log` | `3081053e49a1510c243a53686ccedb88233842a3c15733e97e2c0286864d48ec` |
| `07/actual-image-identity.json` | `4961e044044f603d9e088b02ab556af4faa4f41b3b4cbae9e4759fa13f87dcfc` |
| `07/frontend-tests-20261106T031340Z.log` | `a78df973c7cb3310a78e5021a90068dc0da2b2d0eb92cf4f68359854c3b928b3` |
| `07/frontend-tests-20261106T032114Z.log` | `80210ac765b108d939cfa71d62e3db8268e68a7d2c5ac393480e7ac3f84a6acd` |
| `07/frontend-verification.log` | `30ae843823400952401b750a11d60e687d12da23275eb3fc9f22c2ed8d8449c2` |
| `07/frontend-workers-verification.log` | `35492799776ada29618df1e54a7289633bbf56adc78dd800d1cbfc57c017ae53` |
| `07/node-final-state.log` | `8344810016f59e6c23bf8d850fe48be7593c09a00288ebbd10ce229e08a626f8` |
| `07/prepare-node.log` | `b5797cb6dcf8b41fbdd3bc8ad5b7ed8748e8425626f301093815ed504fb79d51` |
| `07/screenshots-first-attempt.sha256` | `f787f6334721ad665054009e09d8fb858ffa3bbe71734fefeb59c9fa9107f7a7` |
| `07/screenshots-workers-2.sha256` | `d11c359b77eccfd141c0c86d54a35c81cf5edb6b87e1802260abff8d6ebd0751` |
| `07/stage-node.log` | `32a7debb182ec1c2c0972640cff17278d5d18c9a6c709e67667de3ce64fc2f11` |

## 7. 新传输镜像完整身份

### 06 `gateway-backend-deps:lock-d054366c02fa`

config digest：`sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`。全部 RootFS DiffIDs：

```text
sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a
sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104
sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15
sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1
sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a
sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25
sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588
sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1
sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1
sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f
sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6
sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6
sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce
sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c
sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3
sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4
sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814
sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0
```

### 07 `mcr.microsoft.com/playwright:v1.64.1-noble`

config digest：`sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`。全部 RootFS DiffIDs：

```text
sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278
sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07
sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9
sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d
sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc
sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5
sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb
```
