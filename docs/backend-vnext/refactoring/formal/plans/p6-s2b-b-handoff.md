# P6 S2b B 实施与验证交接

日期：2026-11-06 UTC。固定产品：`b820321c1eef78be4430c9a3f5b51d22188f4e0b`；Rust tree：`ab891afe207dc09074de4bdca1cfdf4f65549ee1`。实施、定向验证及本候选容器验证完成；B GO 由独立 [delivery review](p6-s2b-b-delivery-review.md) 判定。本交接不宣布 S2b 整体退出，不承担 C–E 实施。

## 产品与真实调用边界

core 在 `vnext/rust/gateway-compute-core/src/business_kernel.rs` 与 `business_kernel/{cells,operations}.rs` 提供三个窄操作，均接 Arrow batches、明确的小型 plan、调用者的 Rayon pool 与显式局部 budgets/control：

| 操作 | 输入与输出 |
| --- | --- |
| `materialize_sql_table` | READY SQL table、stage、有效比较键；保留所有 Arrow 行，返回实际行数、FINAL raw-content digest、重复有效键 warning。PROVISIONAL digest 为 None。 |
| `filter_catalog` | 可选 device 与固定十类 point 表；先验证所有普通 device 身份与所有 point addr，再输出命中的 Arrow 表和过滤前真实 `source_device_row_count`。不在这里提前判定特殊设备的 0/多命中身份。 |
| `project_canonical_table` | 绑定源行数、已规范化的 retained 声明、key/structural 列、row policy 与 source/canonicalized-input 标志；返回规范 Arrow 表、content digest、ordered real/pseudo counts；blocker 不返回可发布表。 |

单元格使用 Shared Kernel scalar/collection/digest；只把既有 `encode_uleb128` 升为 public 并 re-export，没有复制算法、公开 decode 或改变 Shared Kernel Contract。SET 非 NULL 直接放 sequence frame，行 preimage 仍按 canonical name UTF-8 排序与 ULEB128 拼接，不调用通用 `encode_row`。NULL、空 SET 与 ENUM 空 label 分开。

SQL 重复有效键保留行并 warning，projection 重复键 blocker。普通 keyed 以规则键顺序的 canonical cell-frame tuple 作 unsigned-byte lexicographic 排序；keyless 按 row hash bytes 排序并保留重复/零列行数；ordered 按 no 验证及分配 pseudo，物理按 numeric gid 排序。SQL reserved gid 字符串保持 Python int 的 decimal/underscore/Unicode Nd 语义，Nd 零点表取自固定 Python 3.14/Unicode 16；ordered 仍拒绝非空数字字符串，不复用该宽松检查。

core 校验实际 Arrow name/type/nullability、descriptor ordinal/名称唯一性、逻辑/声明/label 与已有 SQL type mapper 的一致性，以及 retained 的源声明绑定、业务白名单、key/ordered 屏障和实际 source row count。DROP 的 JSON/DECIMAL/BLOB/unknown 等不被扩大为 projection 白名单失败。schema 诊断完整聚合至既有 1024 条并记录 omitted；Python producer 不重复预报同一 missing/type 诊断。plan 的 `schema_diagnostics` 仅供额外 owning metadata，不替代 core 核验。

adapter 在 `gateway-compute-python/src/business.rs` 注册 `_sql_materialize_native`、`_canonical_project_native`、`_catalog_filter_native`。三者最终签名统一为 `(tables, plan, cancel_probe, budgets, deadline_monotonic=None, pool_threads=1)`；每个 table 自带唯一 `arrow_stream`，没有第二个 streams 输入或旧签名兼容层。metadata 在复制前有界；stream 用 A 的安全 C Stream reader，逐批限额，复用既有 pool、watch、GIL detach 和 panic boundary。零 batch reader 用其真实 schema 合成标准零行 batch供 core 校验，真实流消费 cap 不放宽，仅 core 的等效批次数加实际合成数。

Python 实际入口：

- `snapshot_materialization/native.py`：`materialize_arrow_table`、`filter_arrow_catalog`、`catalog_from_arrow_result`。一般表保持 Arrow；只有现有 composite 需要的过滤后 device/point facts 转回 Python。payload 保留 IJSON 整数/大整数文本、float bits、binary hex、SET list 与时间文本。
- `storage_projection/native.py`：`build_projection_plan`、`project_arrow_table`。复用现有 SQL spelling/declared-type/ENUM-SET metadata owner；规则选择/解析仍在 Python。small schema、snapshot、manifest 摘要及 XML/AST/binder 没有移植到 Rust。
- 定向测试和本候选容器 smoke 实际调用 Rust parser C Stream → SQL facts → Python bounded plan → B projection → A IPC，并调用 Arrow catalog → 过滤后 composite facts；不是未消费的 API 骨架。

生产 `table_access.sql.parse_sql` 和 application callers 尚未切换。既有 Python materialize/projection、repository-ref、import-replay/export 算法仍有真实消费者，按 D/E 切换后删除；没有生产 fallback/engine flag，也没有实现 C 的 store/mmap/ref/TTL 或 D 的 worker/config。

## 局部预算与控制

`BusinessKernelBudgets` 显式约束 columns、batches、rows、metadata/input/live/output/diagnostic bytes。SQL/projection 是单表口径；catalog 的 columns/batches/rows/metadata/input 是整次调用汇总，并拒重复/错误 table-name 绑定。borrowed Arrow 按保守 array memory 计 input；返回 shared input 也计 output，SQL 不把这些 shared buffers再次计为新建 live data。projection/catalog 新建数组、adapter metadata/batch references、key/hash/sort/filter 索引、Shared Kernel encoder/聚合复制、Python 输出转换及固定诊断 envelope 纳入自有预约，增长前 checked 检查。

预约是保守上界，包含容量/复制余量及一些未及时释放的预约，可能比实际驻留更早拒绝；不是 allocator tracing、RSS 封顶或生产 M。metadata producer 也用保守复制 envelope。没有生产默认 M、全局 registry 或每线程 allocation 框架。cancel、真实可选 monotonic deadline 在有界自有循环与大段库调用前后检查；probe 异常稳定为 RuntimeError。资源/控制失败不带成功部分输出。C 必须测已实现 kernel/IPC/FULL 生命周期，再由 D 前收口 N/M/envelope/reserve；不能把这里的预约数字当实测。

## 测试 owner 与独立预期

| 主题 | 本次覆盖与 oracle |
| --- | --- |
| SQL facts/SET framing | core 新 7 项中的五组既有 SQL Snapshot golden（minimal、duplicate、keyless、null/types、unknown mixed），PROVISIONAL None；SET 固定 sequence bytes；Shared Kernel 原向量和 ULEB tests。 |
| keyed/keyless/ordered/IPC | canonical frame tuple 的实际 `[2,10,-1]` 顺序、N/DDL/chunk 置换到相同 IPC；重复零列三行/source count、no→pseudo→numeric gid；native 保持既有 Python projection 的 NULL/空/SET key、duplicate、ordered/canonicalized、dropped JSON 与 unsigned/-0/SET digest。 |
| schema/diagnostics | 实际空 C Stream 的 type/nullability 绑定；TEXT 不可伪成 VARCHAR；1050 retained JSON 的完整顺序/1024+26 omitted，与既有 `project_storage` owner 对照。 |
| catalog/composite | 过滤前坏普通 device/point、非空零命中 count、payload 与旧 extractor 一致；原 composite Contract/binder 仍是 identity/XML/AST 优先级 owner。 |
| 控制/资源/FFI | metadata/live/input/diagnostic 拒绝、row cap 立即停止后续流消费、释放 GIL 后的 cancel/真实 future deadline/probe error、真实零列三行 C Stream→B→A IPC。 |
| PARTIAL/FAILED | 真实 parser 状态、failed table 的无 reader/无 digest 与 per-table ready facts，对照既有 Python materialization 分类；没有复制全套 snapshot/manifest/artifact orchestration。 |

一般业务矩阵仍由既有 `test_snapshot_materialization_sql.py`、business/composite 和 storage projection core/integrity/contracts 所有；B native differential 集中在 `test_business_kernel_native.py`。没有在 Rust/Python/容器三层复制完整矩阵。A codec 的未改部分只引用适用已有 owner，不把 A 当 B 通过或正式 carried。

## 合格节点与最终验证

所有测试、编译、lint 与 Docker 验证在 06 `gw-dms-06`，SSH 别名 `ct107-gw-dms-06`。worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-b-impl-9225` 最终 clean 固定 b820；legacy 链接保留。PATH 以 `/home/dev/.cargo/bin` 开头，无 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME 覆写，仓库 selector Rust 1.97；host Cargo jobs 4，UV_OFFLINE=1、CARGO_NET_OFFLINE=true、TMPDIR/target/logs 外置。使用节点本地预填 uv/Cargo/Docker 缓存，无新增依赖或转发代理；源码与必要 identity metadata 经 CT201→06 LAN SSH/SCP。

本角色于 11:54:08 UTC 实际原子 mkdir busy、写 session/purpose/UTC；获取记录 CT201 `/tmp/s2b-b-resume-acquire.log` SHA256 `fa76313434f56b10c537890147fcdd509bd13d71c89245e063b96a1c4d374d9e`。此前旧实施者未持有 busy 的日志继续只作诊断，不能沿用。

| 实际候选/检查 | 时间 UTC / 日志与 SHA256 |
| --- | --- |
| 8c889：强制扩展重装/tree、backend Ruff/mypy、原 owner 与 native 共 180 PASS | 12:45:22–12:45:37；06 `logs/s2b-b-native-focused-8c889.log`；`39bc6ce3faf14c049b44ddec7ed5cba8a3f50bda635f890fb1f28a4f7a5a72cd`。这是 b820 前业务回归，不表述为 b820 跑过 180。 |
| b820：workspace fmt、all-targets clippy、串行 workspace test、release build、实际 architecture CLI、五 Python 包 Ruff/mypy全 PASS | 12:52:25–12:53:26；06 `logs/s2b-b-final-static-b820.log`；`6fb128861bcdbe1e4cb5bfe349122a2db886d1925c61f7cc4d898ca614fc4896`。 |
| b820：强制扩展重装/build-input、受影响 business native + parser adapter 41 PASS | 12:56:29–12:56:41；06 `logs/s2b-b-native-final-b820.log`；`8408b9894670c2e942ee51854d76b47094f2e201a69c4cae5821804b73a6c6d5`。installed/expected tree 均为 ab891afe…；新 nullable/API 边界实际覆盖。 |
| b820：依赖 identity、当前离线 image health/clean-stop、worker build、同 backend image 三 kernel→A smoke PASS | 12:59:54–13:01:10；06 `logs/s2b-b-container-b820.log`；`2b0a6c76326080b0950e83719102e0f101755973acf7295d71cd7944fa026d36`。health `1 passed`；起止 b820/clean/exit0。 |

上述 06 相对日志前缀均为 `/home/dev/gdds-test-tmp/`。最终 Rust 实际命令为：

```text
cargo fmt --all --check
cargo clippy --workspace --locked --offline --all-targets -- -D warnings
cargo test --workspace --locked --offline -- --test-threads=1
cargo build --workspace --release --locked --offline
cargo run --locked --offline -p gateway-architecture-check --bin gateway-architecture-check -- --rust-workspace-root . --vnext-root ..
```

Rust workspace 包含 core 53、Shared Kernel 82 及其向量、adapter panic boundary、architecture 与已有 integration tests；完整 CLI 单独实际执行。五包静态为 shared_kernel、repository_contracts、repository_client、backend、repository_service，均通过受控 uv wrapper。

## 依赖与当前镜像身份

固定 clean CT201 worktree `/tmp/s2b-b-dependency-input-b820` 只运行 `build-backend-dependency-base.sh --print-input`，不是在 CT201 跑测试。12:53:31–12:53:39，CT201 `/tmp/s2b-b-dependency-input-b820.log` SHA256 `92c3c16e8c35fd681502846518d1a8deb8a0444a44654cc4db90702c2d104254`；完整 input JSON SHA `f7df461e1f4b3f3fd45a9fbfb014942fa3dd0d017cc0a95e2e93ffcf4d7eac44`。五个输入与 A 相同，完整 input 为 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`。

因此复用 `gateway-backend-deps:lock-d054366c02fa`，不是仅凭 tag 判断。06 从当前 tag 实际 docker-save，再用既有已审 helper（SHA `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972`）比较 source config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 与全部 19 个 RootFS DiffID，并比较当前 inspect RootFS。B evidence 目录 `/home/dev/gdds-test-tmp/artifacts/s2b-b-b820321c1e/`：`base-identity.txt` SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`，含完整列表；当前节点导出 `base-current.tar` SHA `95f6dc2ccf6ecd9fc352540a8b249bfa978d6bb2f5338fd5b936dfeb68b2076c`。来源仍是 A/readiness 已核 CT201 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428` 的预填 d054 制品；原传输/预填时间与归档身份见 [A handoff](p6-s2b-a-handoff.md) 及 readiness §7，本节没有重传或 retag 基础镜像。

容器外置脚本 `/home/dev/gdds-test-tmp/s2b-b-container-check.sh` SHA `2a7dac5337866aba963f0244a2728264fd6fd7bb5c6e308a39e9bcb2e851381a`；native smoke 同目录 `s2b-b-native-container-smoke.py` SHA `fa2c23f3819e38c91f6cd4efad1563fbd581117c1fb7bba53ee51a36c779b682`。preloaded dependencies=1、Docker build network=none、非 GATEWAY_COMPOSE_GATE_PREBUILT；Compose 本机网络按原门禁运行。唯一项目 `s2b-b-b820321c1e` 的当前镜像：

- backend `s2b-b-b820321c1e-backend:latest`：本机 ID `sha256:484402efd68e0daf00529f261ad9cf5a050b7d1101b58aeb74b1f2d514d97d6a`，与 health 实际运行、native smoke 使用的 ID 相同。
- worker `s2b-b-b820321c1e-worker:latest`：本机 ID `sha256:f31a7d118eff8a1ab263604162d37cc0bb81e832713c86e800342dff64283654`，本候选实际 Compose build。
- Repository Service `s2b-b-b820321c1e-repository-service:latest`：本机 ID `sha256:213a8caaa80a8e0c70c506af03cfe1b339ef1deb9e80f70e8cf2dc8899d08285`；build-input revision `3b037adf4caf33f65e124a34f56f12f42e529641`、source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2` 与该候选 owning identity 一致，revision label 为 b820；其 dependency-base lock `6dc9659f…` 与当前 RS lock 匹配。

本机 image ID 只用于本机运行绑定，不用作跨节点 config identity。Compose provenance 为上述 artifact 目录 `compose-provenance.json`，SHA `07de4641ed90c5002399947e450b83bc8ee18a2ed4bb3121c0f271d59c43c19d`。native smoke 返回 2 行，SET `['','b,a']`、unsigned id `[1,2]`、normalized float `[1.25,0.0]`，catalog 源设备 2/过滤设备 1/过滤测点 1；实际 IPC 2698 bytes、SHA `65796b540e6c7a0bb7effd43d833bd75c156a0438bafb828088a24887597e3b7`，仅为小 fixture，不是 M/RSS/FULL 测量。

镜像内 `__build_input__` 实际仍为空字符串，沿 A 的 Dockerfile 既有限制；没有虚称该字段匹配。容器证明来自固定 clean b820 的实际离线构建与 health/smoke 同 image ID。后续仅文档提交不冒充另一个 HEAD 的 container gate，也没有正式 carried。本节已满足 B 当前候选必要容器验证；最终 S2b 04/真实数据门禁另办。

## 失败、修正与证据边界

历史旧 B 的两次 fmt/CLI 诊断均未取 busy，沿 [历史 review](p6-s2b-b-review.md) 保留，不升级为本角色门禁。本角色取 busy 后的 5621 恢复首轮实际 fmt/完整 CLI/core46/composite29 通过，06 `logs/s2b-b-resume-early-5621.log` SHA `7e8018553e093dbc107ef9225bdec68a90ad7936a9bf45d07aebe76dc5c3948a`；不把它当最终 B 行为验证。

本角色保留的实际失败：

| 失败 | 原日志 SHA256 / 修正 |
| --- | --- |
| 4b546 首轮 fmt：新 ULEB re-export 顺序 | 06 `logs/s2b-b-core-4b546.log`，`24869748e4207dcf1c8469134c25caafce1739ecd262b94745da5b8a0fa5bb2c`；df779 仅格式修正，最终 b820 fmt/clippy 覆盖。 |
| 同步误以共享 main 的 HEAD~1 当 remote previous，随后错误地未在 tool exit 非 0 后阻断验证，旧 0a9 fmt 再失败 | CT201 `/tmp/s2b-b-resume-sync-transfer-format.log`，`a359eff7a51a5fe06c90fadb92886722853fdf2007fb68896f7bb432be2d4e4c`；06 `logs/s2b-b-consumers-compile.log`，`fe2e7bd50bd113945fc756e959ef62a24d8fa8326eb599050f9858b4f0243ec0`。sync 在 fetch/checkout 前拒绝，随后只到旧候选 fmt，未编译/跑业务。立即停止报 root/review，未原样盲试。 |
| d840 新测试前置：NULL PRIMARY KEY 被 parser 先拒绝；dict 不能设置 parser getattr budgets，宽列仍受默认 512 限制 | 06 `logs/s2b-b-native-focused-d840.log`，`3a0dc18ce6c78c0b92434da30570c6127bb072d4ea6353d4544d7b6e81489ab8`；177 pass/3 fail，整次非 PASS。8c889 改真实 comm_user_data nullable source/规则键及 RESOURCE_BUDGETS replace，未改 expected，180 全过。 |
| 8c889 clippy collapsible_if；4006 clippy adapter 参数数目 | 06 `logs/s2b-b-final-static-8c889.log`，`43f6c8c4623ce0e11f05679e98945b722e83d94f9e8824a098635b3197c105da`；`logs/s2b-b-final-static-4006.log`，`247ec51eb85604cc1652646bb1182a44a4b6da365f8be7aafb729db9350cbac9`。均停止在 clippy，之后 workspace/release/五包未跑。改等价 if-let、删重复 streams 输入与内部控制参数归并，不 allow warning；b820 最终门禁全过。 |

同步在 root 明确的一次已审恢复中改为：捕获真实 candidate → 本任务 `refs/codex/s2b-b-transfer/<fullsha>` named bundle → 显式 ref fetch 到 `refs/codex/s2b-b-source`，previous 为实际 06 HEAD；source/sync 和验证分别 tool 调用并检查实际 rc，不再推共享 main 的 parent。修正后的 CT201 `/tmp/s2b-b-resume-sync-authorized-recovery.log` SHA `d729ef6e3b6b0d01fa609e76ecd09f74a8c50f57f64a4cba20de3817a480e91f`，12:39:23–12:39:24，clean 0a9→25fe，实际 tool exit0。旧失败日志/bundle不覆盖。后续沿同一最小参数脚本同步，未改写提交、未建 branch/tag、未推送。

review 发现的诊断前置/重叠预约、catalog 总预算/name 绑定、large offsets、源类型/宽度不可伪装、ordered schema、SET NULL/空键优先级、source gid 字符串、构建循环控制、输出 metadata、空流/probe 分类/display 与 nullable 绑定都由产品修正并在上表最终测试中验证；没有以 Python 预计算诊断或修改 architecture guard 绕过。

## 资源释放与 C–E 移交

本角色于 13:03:51 UTC 确认 clean b820、全机无运行容器/Dolt，核 session 后只删除自己的 owner 文件并 rmdir busy。CT201 `/tmp/s2b-b-release-b820.log` SHA `b320c87de994ef457aff4515cae96683685301dc3dc35dfeda4ed3f00fc0e315`，exit0。B worktree、日志、artifact、任务 refs 与唯一镜像保留供复核；A worktree/镜像及 CT108/04/05/07 冻结资源未被本角色修改。独立审核使用其 detached worktree；实施者不替审核者判证据。

C 承接本次 Arrow 表/小型 facts 与 A codec，按 owning Contract 做 store/mmap/read-handle/refs/恢复；测真实业务 IPC、FULL 双侧同时驻留与临时预约，校准容量，D wiring 前定 M/envelope/reserve。保持外层 DDL/PK/manifest schema 与 IPC 内部 canonical 列序、业务/no 顺序与物理 gid 顺序分离。共享 Python pool 仍是既有固定 process pool，caller 的 pool_threads 必须与首次配置一致；不同 N 测量用明确 caller pool/独立进程，不能把测试 worker 数当 N。

D/E 仍要迁移 production parser、上传 FULL 两侧、Preview baseline、History exact commit、repository-ref READERS_REQUIRED/ARTIFACTS_REQUIRED、import-replay、export，以及 Submit/T1/PREPARED 与恢复/冻结边界；全部真实 consumer 切换后删除替代的 Python 批量算法/只为它保留的 probe，不删除仍有消费者的 metadata/业务 orchestration。最终 04 权威 runner/container、t1–t4 正确性及 W1/W2 的 DC83/DC84 时点保持原安排，未知性能不记 PASS。
