# S2b D 交付：真实 worker 接线、operation 预算和规范 IPC 消费者

产品候选：`93678f8439ec1393d496182f16ae5049b220242f`。本节实施与定向验证见下文；独立决定以 [D 审核](p6-s2b-d-review.md) 为准。本交付不签 S2b exit/S3 ready，不代替 E 的 04 权威 runner（按包闭包判定实际运行/合格来源沿用，Rust 必须覆盖）、最终容器与既定真实数据全旅程。没有推送、tag、改写已引用提交或进入 E。

前置为 C 产品 `0048040af59214bf1113c820396ac4b306befe31`、交付 `7cd2b548c8`、独立 GO `e9bef6efe8`；D 启动文档 `63925fe47c`。相关 owning 决议为 DC87（12/4/显式 8 GiB、N1/单 active）、DC88（正常 drain 纯重算让出），及本节 [任务](p6-s2b-d-kickoff.md)。原 W4 失租仍 OPEN；本节未触碰 CT108 冻结资源，未合入原基准局部诊断 `1f9731dfc3`，也不将旧 Python 峰值或 C 组件测量作为 D worker 容量证明。

## 1. 实际入口和格式

- `OperationWorkerSettings` 要求显式 M，拒绝缺失/非法/超过 envelope-reserve 的值；8 GiB 是部署显式值及本档上限，不是代码 fallback。生产 `run()` 在 operation 派发前一次 `_init_kernel_native(N)`，并一次设置 PyArrow CPU/IO N；未初始化的 native adapter 稳定拒绝，不假 parse、不按表建池。精确 native import guard 保留 parser 与 bootstrap initializer 两条 owner，不放开整层。
- Preview FULL 上传侧走 Rust parser → B materialization/filter/projection → A IPC → C store；baseline 与 History 走注入的 committed-tables port，绑定 caller 已知 repository、exact commit、完整 canonical identity 与 schema。实际 selected/导出表缺 port 或 identity 拒绝；没有 Python rows/source fallback。
- 公共 artifact wrapper 直接改为目标 schema，必带 `repository_id`（raw 为 null）：raw 是 `parquet/zstd`，internal canonical 是 `arrow-ipc/none`。canonical checkpoint/Submit frozen caller 额外要求 canonical 格式及 expected repository，不能借通用 raw reader 放过旧规范 Parquet。物理摘要绑定实际格式/scope；业务摘要、逻辑 scalar profile、storage projection version=3 不变。
- Submit parent readers 复用 C port；T1 frozen 输入严格使用 IPC closure，不重新选择来源。已核实该处原就没有重复整表业务 hash；保留 MutationPlanning 拥有的 typed row-image 摘要，实际 mutation/replay/tag/render 仍沿原 owner。PREPARED 复用冻结包。已提交派生副本缺损按 exact commit 恢复；StartArchive 才移动 Head，Submit finalize 未接管 Head。
- 客户端 surface/replacement/full bundle 统一复用现 export/cache owner，真实列式写 Parquet。保 source schema/DDL/SET 空与 null/float bits/时间与 ordered metadata；按 no 的有界 ordered export 不拿内部 gid/key/hash 排序替代协议语义。内部 IPC 从未直接标成 `.parquet`。

## 2. M 生命周期与控制

同一 `KernelExecutionContext` 持有 operation memory 和资源 ExitStack。共享 Arrow root backing 与同 mapping views 去重；独立 reopen 是不同 mapping，不按 artifact_id 假去重。SQL source 在实际 caller 持有期内预约，已借用 source 不在 parser 再计 owned。descriptor、filtered SQL facts/无 XML composite、返回 staging metadata 与真实存活对象保持一致。

增长前准入包括 parser phase A/jobs/实际列宽 ordinals/所有 chunk builders/merge/Arrow 交接；B/A 局部临时 cap 取 operation remaining；C mmap、SHA/inspect、IPC/Vec→PyBytes/存储 staging；FULL 双侧重叠、XML/AST/composite；wire/复合列式转换在 native 计算 cap 前先预约。parser 新整体预算拒绝是既有码 `RESOURCE_LIMIT_EXCEEDED`、`max_live_bytes`、offset 0；旧 quota 定位/成功语义不改。

剩余 Python owner 也接同 M：comparison 按真正需读表（含 ordered identity hit 的 current rows）给 values/frames/index/Counter/ordered/facts/records/JCS/Arrow/Parquet spool 保守包络，跨 FULL 多 pair 持有至 operation end；Submit changed/parent mutation images 与索引单独预约，16/200 MiB 既有 package ceilings 给 render/USTAR/zstd/verify 临时包络，readback bytes 另计；READY verify 逐 ref 短期预约，JSON/manifest 解码在读取前准入。bundle 在 application owner 按完整闭包 binary 复制和 JSON rewrite/metadata 预约，覆盖 planned/generated/verify/readback 与返回 refs；没有给 bundle 增加 Table Access 反向依赖。

两项标准读取边界已修：LocalArtifactStore 先 opened-FD size 检查再 bounded read；pinned CPython 3.14 的 TarInfo 扩展点在 PAX/GNU/sparse metadata 读取前准入，保持标准格式解析/首 header/global PAX member copies 与普通 metadata 的实际总额。不重写 tar parser，不新增部署旋钮或同 euid 窗口协议。

实际控制合并 caller 与 operation：停止条件 OR、finite deadline 取最早、local quota 取最小；无 deadline 保持 None，不用 lease 续期或 benchmark timeout 充 operation deadline。native monitor 显式捕获实际 probe，不依赖 ContextVar 线程继承。EOF、native 异常返回、完成及发布前复核；cleanup 只释放资源，不在已 ack 后重新抛 stop。ArrowMemoryError 的多继承不被 C cache corruption catch 吞掉。comparison/records/bundle/parent reader 的 broad catch 穿透 stop/deadline/Memory。

LeaseSession 仍是唯一正式 durable mutation owner。DC88 仅对 registry 真实 PURE_RECOMPUTE 启用：真实 drain、fresh 有效 lease、effect 前保留 checkpoint/prior refs/保护，RUNNING→RETRY_WAIT 立即可 claim、清 worker/token/lease；独立 marker 保 attempt_count 不增不重置，operator session 保留。cancel 优先，失租禁写，EXTERNAL 不启用。可报告 MemoryError/预约拒绝先复核实际 control，再沿原 Preview/History/prepare 失败事务清保护；prepare 同时 ABORT Attempt/清占用。进程终止/OOM kill 仍原 Runtime 恢复，不作 catch 承诺。

## 3. 节点、源码与依赖

实际运行仅 `ct107-gw-dms-06` / `gw-dms-06`，CT201 仅编辑/Git/制品。06 session=`p6-s2b-d-impl`，busy 起始 `2026-11-06T14:47:31Z`，owner 文件 SHA `e31c5ffa8f4090024e3e73b333c1eb803a8732d22c6a4021df69084d63bef28a`。开始 BatchMode SSH、占用/进程检查及原子 mkdir 的日志：`/home/dev/gdds-test-tmp/logs/s2b-d-node-prepare.log`，SHA `af803027f30e1e10b495fecdc8c20131d4d02f2e114b192f9753234fd4119c3d`。起始实际 remote HEAD `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3`，clean，legacy 链接齐全。

测试 detached WT `/home/dev/gdds-test-tmp/wt/p6-s2b-d-impl`，日志/TMPDIR `/home/dev/gdds-test-tmp`，Cargo target `/home/dev/gdds-test-tmp/s2b-d-cargo-target`。经 owner 批准从已释放 C target 复制到 D 独立 target，只作缓存；未删改 C 缓存/WT/镜像/证据。PATH 以 `/home/dev/.cargo/bin` 开头，不设 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME；Rust selector 1.97.0，Cargo jobs4，时序/数据库 focused `-n 0`。`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，使用 06 已预填本地缓存，无公网/代理，无依赖锁变化/新传输。

源码传输：CT201 `/tmp/s2b-d-publish-source.sh` SHA `07bce72f3f513f7666cb05bf896913a8b2350c56c3ec4f95ed2e39e35a35b879`；remote `/home/dev/gdds-test-tmp/s2b-d-sync-source.sh` SHA `73ad4f7e9689a72fc59d952f8b97785aca6de6a9c379a357670f068cd3e23b51`。每小步固定 full SHA → `refs/codex/s2b-d-transfer/<fullSHA>` → named bundle，核 advertised ref/checksum/fetch；previous 总是实际 remote HEAD，同步 actual exit0 后另一次 tool 确认 expected HEAD/clean 才测试。没有共享 main HEAD~1、测试中写 WT 或改镜像 tag。最终同步 `/tmp/s2b-d-sync-final-static.log` SHA `d54179870edd7881ed294b8a42996642079010054646a273ae642ccee1b8490d`，previous BBC→936；独立 HEAD/clean 另查已完成。所有 `/tmp/s2b-d-sync-*.log` 保留，并复制至06 `artifacts/s2b-d-sync-logs/`。ff399 同步实际 previous=`77a4b57811b0f9d01aa1783d5f4a10a2dcef4a25`，`/tmp/s2b-d-sync-parserfix.log` SHA `548879b318f2e79ee6edf37bb5adb0c2d5f00f086e9d5fd1ddffcc13692085d3`，15:08:09Z同步exit0后独立HEAD/clean核过才跑parser链。

## 4. 合格的小步证据

下列均为 06 外置日志，前缀 `/home/dev/gdds-test-tmp/logs/`。每次记录 hostname/UTC/起止 HEAD/clean/实际 exit；只按该 fixed SHA 的实际范围使用，不合并成“最终整包 runner 已过”。

| 固定候选 / 实际范围 | 结果 | 日志及 SHA256 |
| --- | --- | --- |
| `865d814cab88b2c4979d8dc6924e55153c3aacab` initializer/settings/guard | Rust 全链、强制扩展/tree、171 PASS / exit0 | `s2b-d-step1-865d814cab.log` `8a95f84013322b2e683da4daaf2b0b513e825eb1694ceaa444c729931a3dfba7` |
| `ff399ac0057e9aa28266b16fae12494101e67aca` parser whole-live | Rust 全链、强制扩展/tree、171 PASS / exit0 | `s2b-d-parser-ff399ac005.log` `39adaa77014cb2e6dbefb7efaf88735f3913217882c9bc4cb4e9262f70b0d72d` |
| `2d385ffcc79156c41fd6283f5236a5226fab41cb` context/source/metadata/caller control | 208 PASS / exit0 | `s2b-d-context-focused-2d385ffcc7.log` `cf7ebb67d97afe7e0a3da785734f43df259fe135169eb6ccf3c0633128e0bf64` |
| `23bd4b596284760db9f762587fd62ef738166249` C IPC/lifetime/EOF/error classification | 220 PASS / exit0 | `s2b-d-ipc-focused-23bd4b5962.log` `8eb08e97ffbc16796808d1ed4bdcc069fd5f05d842eb1725cb305cb89d945115` |
| `f45bcd7b6ab868654777271ebc2182f46a950f97` archive metadata/result lifetime | 256 PASS / exit0 | `s2b-d-archive-f45bcd7b6a.log` `e7ba62872530a57deac1700941979bb198b3a1bc0e32063cb7a4ed58c4b8883e` |
| `2347126bb05fa762fba80bd788fd4b0f727abc42` uploaded native vertical/checkpoint scope | 121 PASS / exit0 | `s2b-d-preview-2347126bb0.log` `b6b3a1f349e42c5e289cf605454f9a2968f073fc35e245c46361553852cc1651` |
| `9315d0966191c02186da3c600737aa25bfe586cc` committed port/control/cleanup + protocol/digest | 58 PASS / exit0 | `s2b-d-committed-9315d09661.log` `3f162081acfb6a0831a41df7acc38ad6ae98a365736f921d54d104ec7176d850` |
| `5325076e629ab1162cf9240cf508052dd43acd83` filtered facts fixture；`9b4964fdb52f1ef4a00430deb6e9ddd21175769c` formula | 532 owner35 PASS；9b formula 在84f实际native35也通过（84f整次失败） | `s2b-d-catalog-5325076e62.log` `29d3049cce23f9c879bee6bfbdc0d25b36ba6812a42576b3dc69c498404c73c4` |
| `beca6c334abf8786ab506e3d71b1a78f05d95bd4` History/source identity；`e9585003d96b3d8bbd6e0801f48ab764fdc49dce` client metadata lowM | 27 / 14 PASS，各 exit0 | `s2b-d-export-beca6c334a.log` `9caad12eed123e9344b4dfa931b0ed52bf0584337f975eaee6db045a401be4d0`；`s2b-d-export-e9585003d9.log` `a1aec35214e57ab13dcd3a81e1dcd6e97167cfa8544e09f677e2e3ba6f713d0e` |
| `17ceec610e32c21223fc80753d30f7e6b399d042` actual Submit IPC fixtures/builders | 26 PASS / exit0（a6已过prepare7/C9/arch90，a6整次失败） | `s2b-d-submit-17ceec610e.log` `101e391669707ee08deb10c2d4409de6d83a0c826af60614455f3a955845a19e` |
| `7f61ceedf4a93842422338b58c876124a8af093c` DC88 lease/state/R5/真实 fileDB Runtime drain/reclaim | 422 PASS / exit0 | `s2b-d-control-fixed-7f61ceedf4.log` `bfad4f180647e3f11e5da71e1dee50443828381bde797da3b81a470c9a3cc7cb` |
| `985e5e0ae83358be8118da901ed18bea7ebb75a9` pair/records control + T1 actual IPC missing/no-source/ABORT | 182 PASS / exit0 | `s2b-d-pair-control-985e5e0ae8.log` `b74d5ebb48aee81de9070be4d1d2e8fe48a7db66797b7b19a154a02aac0ad54b` |
| `b05c390a2a6547a1b2b21600116048508b32a484` Python M/READY/replay/实际低M清占用 | 243 PASS / exit0 | `s2b-d-python-memory-b05c390a2a.log` `07cd2ed8a1cccaced2ca3643d707e61c57b3631e9eced3433370644aab357ae4` |
| `bbcdd8c82cb6bb6c35ee411fb4c5ce1483fdf79b` ordered identity current rows + bundle staging/control | 155 PASS / exit0 | `s2b-d-bundle-memory-bbcdd8c82c.log` `b151e1fca9504c8677ca1bad8e98440a9a0badc13e8219f91f6044f14650a439` |
| `93678f8439ec1393d496182f16ae5049b220242f` 五 Python 包 Ruff/mypy，C ArrowMemoryError 参数 | 18:40:53–18:41:11，五包静态 +10 PASS / exit0 | `s2b-d-final-static-93678f8439.log` `0498abcb38bb5b66977fb7fe80e40aef5bf9628158c4a9fc4a0947106483b3db` |

Rust 最终 tree `137d499975f3c104ae9c3268b9e12befb2817ba1` 的最后完整链在 `ff1c98d1c694db11230d74bc3b7ac2caa285b2cb` 日志中：fmt → all-target clippy `-D warnings` → workspace tests `--test-threads=1` → release build → architecture CLI → 强制重装及 installed/expected tree 一致均通过；该整次随后 Ruff 缺 Callable 失败，**不把整次当 PASS**。修复后的 `23bd` static/220 PASS 与相同 treechecker 收口。后续产品至936无 Rust 变化。FF1 log `fe5360db1ee94c6069648a06441362e71454c4dc47ad1a61d1286bf66c8e7212` 保留；不是声称 final SHA 跑过完整 runner。

## 5. 真实 worker materialize 局部校准

固定 BBC，06 `18:39:04–18:39:46Z`，实际 registered `preview.materialize_inputs` handler、KernelRegistry、WorkerRuntime、LeaseSession/SQLite、LocalArtifactStore，N1/M=8,589,934,592，无 operation deadline。既有输入：

| 输入 | package bytes | SHA256 |
| --- | --- | --- |
| `rd-t4-d-v1` | 5,597,503 | `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` |
| `rd-t4-d-v2` | 5,596,595 | `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611` |

输入路径为 `/home/dev/gateway-real-dumps/packages/<dataset>.tar.gz`。仅 INITIAL 空 catalog 是已批准 fixture；上传 SQL/XML、staging、parser/filter/B/A/IPC/store 和 FULL 双侧实际驻留均走产品。准备包 bytes 在 put 后删除，不跨 worker 保留。测量 wrapper 只读 handler 本次 context、在真实 handler 返回后 stop，不替换计算或伪 control。实际 materialize Step SUCCEEDED/attempt1/非空 checkpoint；assemble_preview PENDING/attempt0；operation RUNNING；无 executor_failed/lease_lost/drain_timed_out。

| 指标 | bytes / 口径 |
| --- | --- |
| 进程 VmHWM 与 ru_maxrss | `675241984`（约0.629 GiB）；本次 fresh host real-runtime 进程峰值 |
| runtime 结束后 VmRSS | `526581760`；与峰值分开 |
| charged/reserved high-water | `3976940733`（约3.704 GiB）；含 retained backing 与 staging/SQL-derived 等保守 envelope，并非纯 retained 或完整 native allocator 峰值 |
| stage admission | `2233` 条，逐项 retained-before/local temporary cap 在 report 中；不与 RSS 相加冒充实测 |

完整 report `/home/dev/gdds-test-tmp/s2b-d-capacity/worker-t4-bbcdd8c82c/report.json` SHA `0fa7b17b6710b803fc27838ed8fbea864b6937a0817687046de164fd1044d626`；日志 `logs/s2b-d-worker-capacity-fixed-bbcdd8c82c.log` SHA `103c084d8f2eb68d820f101f6eeaa3375073f98939c192a426ed61d6a56beb5a`，exit0。脚本 `/home/dev/gdds-test-tmp/s2b-d-worker-capacity.py` SHA `8003ab50bcac06b3b6edc4da6c27722f7c11dd4ef3c34909825218b69f8f8783`；driver fixed SHA `14e0dc9aac95b5fb5bec54e9687f0a5da640361b8f7aaec96b85ce99549ac845`。受控 lock-check/treechecker 后使用同锁定 venv 的 CPython3.14.6，实际解释器 `/root/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3.14` SHA `255e900f44ce87c630e83b637a79435f9ae7778dd72f6e2a2f18a486e501d016`；未同步/安装依赖。

此结果只证明以上 materialize 阶段校准；没有执行 assemble/Submit 全旅程，不把手动一次 init 冒作生产 entrypoint 证据，不把 host HWM≤12 GiB 冒作容器硬限制。pair/Submit/bundle 的 M 拒增长及清理另由 §4 现 owner 验证，最终全旅程留 E。

## 6. 当前候选离线容器

实际候选936，重建理由：本轮 settings/startup/Compose/生产 reader/control 接线及 Docker build-only `ARG CARGO_BUILD_JOBS=4`。ARG 仅 builder 阶段，不入 runtime、不改产品 N/M；依赖输入/五锁/base不变。06 本机 preloaded dependencies=1、build network=none、保留 Compose build，未设 COMPOSE_GATE_PREBUILT。只用 session-owned project `s2b-d-93678f8439`。

复用 A/readiness/C 已核 CT201 来源制品 `gateway-backend-deps:lock-d054366c02fa`（本节无新预填/传输），完整输入 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`。容器 driver 对当前 WT 五输入逐项 hash 后重算 digest，再实际 docker-save 核 config `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 及全部19 DiffID。完整列表 `artifacts/s2b-d-93678f8439/base-identity.txt` SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`；保存 tar SHA `95f6dc2ccf6ecd9fc352540a8b249bfa978d6bb2f5338fd5b936dfeb68b2076c`。来源传输时间/全身份沿 [C handoff §6](p6-s2b-c-handoff.md#6-当前镜像与依赖身份)，不虚构 D 新传输。

Repository dependency-base lock `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` 与当前锁核合。当前 RS source identity：candidate936，build_input_revision=`c52e9fad62e14b016ed814d0799e08e6d97e82b3`，source_tree=`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。

容器脚本 `/home/dev/gdds-test-tmp/s2b-d-container-check.sh` SHA `1e56e8aace2636b994048d620545a762e5c02f597411181b32c0db879144f355`；worker probe SHA `d65e7f4e540a8461b885be6cbb888e0c1bb6f792b21bff2a1580122df39a1fdd`。实际取证分两次 focused 来源，均绑定936同镜像，不回填首轮失败：

| 实际来源 | 结果与证据 |
| --- | --- |
| `18:43:47–18:45:59Z` 当前本机离线 build + backend HTTP gate | gate自身1 PASS/命令exit0（100.07s），provenance SHA `1303fdc2e46d03218a7c24098709bc70d12a25dc780247f60d5361ad5a33a0f4`；后worker错误fixture早退使外置整组exit1，原log `logs/s2b-d-container-93678f8439.log` SHA `daa9d38d0d0e96f5f06b86bf776992fa1bbfcc22066e4325754e2076ace55227`，不称整组PASS |
| `18:51:28–18:51:41Z` root授权 worker-only 合法fixture诊断/验收 | 同已建worker image、无build/重tag/HTTP重跑，ready→正常drain→exit0；driver实际exit0/HEADclean，`logs/s2b-d-worker-container-diagnostic-fixed-93678f8439.log` SHA `f8744950738a3e75c93f59aea644d11452cfb4678ebc6f53c8bbd32178e6e1cb` |

worker本机imageID前后均 `sha256:cfa0d7cd053c5aaac6d0779ef743a5e8afa973450f97a69f1ba80bc6ca31a073`；backend gate/已建image均 `sha256:b1cfc1b955b6c44d4e3a92321f23dbd0e7f2edb4acd8679e9bb1d64fd0060f02`。actual HostConfig.Memory 与容器内 `/sys/fs/cgroup/memory.max` **均为12884901888**；同容器settings N1/M8589934592/envelope12884901888/reserve4294967296，PID1是 `python -m gateway_backend.bootstrap.operation_worker`。固定诊断driver SHA `c3ba7fa8fea5f30580c68f57b8a29b9d7d989af598b3cc0350686cbef2d6d8e5`。

以下相对路径前缀 `artifacts/s2b-d-93678f8439/worker-diagnostic-fixed/`：`worker-config-memory.json` SHA `edcbda45d1cb34c95a37648d186f5957a6ddd4007a618d1d3bb16f375a63b036`，`worker-running-inspect.json` SHA `f5aadace30891d369a05d9bf4220c8510f59b2ba8c010ad38211398115ef357c`，`worker-stopped-inspect.json` SHA `8932d0985c7641cef7e208542e5f26ff506f9748ce55b08c0bc0f3582054f3c8`，`worker-stopped.log` SHA `f9f04712bbc87ab9b6ff7234911f04d329ada3feb252bdd680aaab28777f8531`。

从实际 saved image configs 读取的身份（不拿跨节点inspectID当config）：

| 镜像tag前缀 `s2b-d-93678f8439-` | config digest | 完整DiffID数量 |
| --- | --- | --- |
| `backend:latest` | `sha256:577a055c6797a35b2475ddc70cf5d64bc2ac289af0d9956efd46cccafada77e8` | 13 |
| `worker:latest` | `sha256:05ad1486646ba59079eb928540f52d72a18cc48e47e8fc0d7cb477fdc318983c` | 13 |
| `repository-service:latest` | `sha256:0ef5b6c494ee677712ad78dc9a2083cbeb3ac7947fb3ada7c855f5eb0da18187` | 28 |

全部逐项DiffID在 `candidate-image-identities.json` SHA `7bd6657c38eb6ebfbe8ce0645cd2bc6679421cff952ec3f32bcb17686b73683f`；`candidate-images.tar` SHA `3f50a790025abbf55f99c9cfe145d1b98bb65bf583456fb26d93b85cdf9f9359`。保留全部镜像及归档；仅清本节project的运行容器/卷/network。这是本候选必要容器边界的focused组合证据，不是合格权威runner来源或最终stage镜像carried判定。

## 7. 失败保留与归因

完整失败/通过日志索引（含 full HEAD、实际 exit、SHA）为 `/home/dev/gdds-test-tmp/artifacts/s2b-d-evidence-index.json`，当前45份日志，SHA `ee905af20896045e49aaae3ac45bf8ea4f43c035a1ece9878f04271d722e911e`。最终49份日志索引 `artifacts/s2b-d-evidence-index-final.json` SHA `a0b742a16886029da6746d819300f813e65e49a40caa59ff8418a456f3caa44f` 包含容器/CLI失败和closeout，不覆盖初始索引。未删除失败、不把部分通过写成整次 PASS。

- parser `77a4b57811b0f9d01aa1783d5f4a10a2dcef4a25` Rust test pool helper构造错误，exit101，`logs/s2b-d-parser-77a4b57811.log` SHA `c52d70dbcf338ca5365a0fd9def90c0e2ee3efef26f415a627a9770fb15d9883`；ff399 修复后整链通过。
- 其余首步/import/type/Callable/generator/cast 等 static 失败按原日志保留；context 205/1 架构不可达由 approved 六项精确 temporary baseline 收口；687d 256/1 修真实 checkpoint expectedrepo。旧 source session 次数、canonical no/gid 和 wire count fixture更新按目标 Contract，保原 move/pseudo/稳定拒绝断言。
- `9ea243160331ac04fa051abfe227487ff4b8001a` 57/2 失败包含审核将 RS/A 表示能力误扩成 B 支持的范围错误；root/审核明确撤回，在9315新提交删除无 consumer 的 BOOL/DATE/TIME/TIMESTAMP/DECIMAL/BINARY/BIT 转换和向量，保真实 scope/arrays/cleanup修正。未改 B 白名单或改写9ea。
- 7a9 filteredfacts低M例的 fixture description 实际过滤为空，532修身份；84f 191/12、a3 139/1、a6 114/18 分别是冻结 ordered/source schema/count/Arrow nullable fixture目标事实未齐，由现 owner窄复验收口，均不作整次通过来源。
- DC88 b5 外置 pytest路径误写 `tests/architecture`，0 collected/exit4，SHA `32f62edd276fc56a268a3cbf386ef8ea6bd0a9919a4c7cfe3ab30e345244c7ca`，按DC68修命令从开头一次重做；实际418/3另一个日志 SHA `c2690433a03d7af7d424037bfc9855652a00d42e1c860d500b06775c2e0a5270`，两例重复ref fixture/一例漏实际signal唤醒已7f61修复。
- a8 180/2：真实T1缺IPC揭露 READY verify 的 typed error未接 ABORT，985e修真实owner；另一项private capability import改public surface，没有新baseline。
- capacity首命令 uv wrapper拒工程外脚本，未运行对象/未创建输出，exit2日志SHA `0d731eb77faf0f925c8a8316c77475c9e3535217efece99d04526c1bc07f2292`；root/review批准DC68一次改为 lock-check/treecheck 后同 venv直接运行已审外置脚本，fixed exit0独立记录，非runner闭包。

- 当前容器首轮实际worker已启动后早退：driver给 `{"mappings":[]}`，生产 `sqlite_mapping.py:72–73` 明确拒空（review独立核此fixture遗漏）；首轮finally未保存worker stderr/inspect便清容器，取证缺口如实保留，不假称恢复原stderr。后续只用HTTPgate已有合法mapping、同image做worker-only，产品校验不放宽。
- worker-only首个CLI命令 `--no-build` 在本机Compose5.6不支持，尚未create/start，独立日志 `logs/s2b-d-worker-container-diagnostic-93678f8439.log` SHA `cb0877b2870d19eb0ec6e7d149de23380feea1f337153abbbb604da1c0038cd4` /exit1；root/review核本机help后按DC68只改一次：不传`--build`、保`--pull never`、前后同imageID，fixed新日志exit0。这个未触对象CLI错误与原真实worker失败严格分开。

## 8. E 边界与释放

E 按既定授权删除最后旧 Python bulk algorithms/临时差分。D 为保固定参考仅保六个精确 UNREACHABLE：`table_access.sql/_sql_reader/_sql_scan/_sql_statements/_sql_types/_sql_values`；无生产 consumer、无 fake import、无 IMPORT/cycle baseline。E 同删测试侧 `_ReferenceCommittedTables` 与其既有 row-reference/identity生成依赖，转独立固定预期或真实 C port；`tests/support/snapshot_materialization.py::snapshot_table_as_arrow` 仅小 fixture 转换不是生产算法。C 原暂不可达五模块已真实接线并删 baseline。raw/client Parquet 仍有实际协议/消费者，不随 E 一并删除。

`real_dump_journey` → `real_dump_census` 的工具 consumer 按 `2991530d13` 移交 E，切换 fixed vectors/真实 Rust 路径后删除旧批量解析/差分依赖；不改原基准冻结分支。

最终 04 权威 runner（逐包闭包决定实际运行或从合格实际来源沿用，Rust 必须覆盖）、镜像 carried 判定、t1–t4 既定完整旅程及正式性能工作留 E/原 owner；此处均为06日常 focused和局部容量/容器证据。节点清理只停删 D owned运行容器/卷，保留本节/A/B/C WT、镜像、缓存和全部日志/归档；06 `18:52:58Z` closeout实际exit0：当前936/clean、五locks/Cargo/selector与C无diff，Rust tree与解释器身份重核；无D容器/卷/network、无运行Docker或Dolt；owner SHA仍等于本session起始值后只删本session owner文件/目录，busy已释放。`logs/s2b-d-closeout-93678f8439.log` SHA `7cdafad65fc639fe8c72b6e6add5d529899527398fd1ecc89accafb08080982d`，driver SHA `03867b3da71aaec2ca4858a4d52c716b4c6c01149dcdc4a342f44386b536a410`。磁盘295G/used130G/available151G只是guest状态，不冒宿主thin pool承诺。
