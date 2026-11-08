# P6 S2b A 实施与验证交接

日期：2026-11-06 UTC。实现候选：`db7767ffbb5e4eee269b3c0e4778351dd98a092a`。本交接只覆盖 A：纯内存 canonical Arrow mapping/IPC codec。B–E 未纳入本节，也不由本报告授权。

## 实施结果

实现位于 `vnext/rust/gateway-compute-core/src/canonical_ipc.rs`，Python 边界在 `vnext/rust/gateway-compute-python/src/lib.rs`。实现通过 Arrow 59.1 标准 `FileWriter`/`FileReader` 写读 IPC file，复用 Shared Kernel `DeclaredType` 与 JCS 能力；scalar bits 和 SET framing 由既有 owner/fixed vectors 衔接，不声称本 codec 调用通用 framing API。未增加第二个 writer 或通用资源框架。最小 Python 入口消费 Arrow C Stream，返回 IPC bytes；没有 PyO3 decoder 或 Python rows 中转。

输入是业务物化、规范投影且已按 owning 语义排序的 `RecordBatch` 流。调用方传入有界 budgets，编码端按 canonical column name 绑定各批次列并按外层 descriptor 布局恢复读出列序。core 生成 canonical schema/arrays/IPC bytes；reader 绑定同一组 canonical columns，并在交给标准 Arrow reader 前检查有界 footer/block、raw metadata 唯一键和允许的物理 schema。它是内部 mapping/profile reader，不承担外来业务 IPC 的 grammar 验收。

`sql_type` 必须已由 projection owner 规范化；A 不复制 SQL normalizer。decimal、temporal、JSON 等业务文本由 owning materialization/projection 保证规范。A 检查声明与物理类型映射、窄整数范围、有限浮点、nullability、SET/BIT 表示及 profile 元数据。`max_input_bytes` 采用借用输入的保守总和，`max_output_bytes` 限制实际 IPC 文件，`max_codec_peak_bytes` 只界定 codec/adapter 自有活分配；这些局部上限不等于进程 RSS 或系统总内存证明。

adapter 对 `DeclaredType` 的构造通过 core 的 `set_declared_type_from_parts` 完成，避免 Python crate 直接依赖 Shared Kernel 类型，并保持 architecture guard 不变。Arrow mapping 使用既有 `table_access` descriptor 与 Shared Kernel 声明类型；本轮依赖锁未引入新第三方依赖。`Cargo.lock` 最终与本轮基准 blob 一致。

## 独立固定向量

Rust core 测试 `canonical_mapping_preserves_independent_arrow_buffer_vectors_and_outer_layout` 固定检查三行 nullable bool `[true, null, false]`、i64 `[7, null, -1]`、UTF8 `['é', null, '']` 与 BIT(9) `[0001, null, 0100]` 的 IPC body buffers。oracle 直接断言 validity `05`、bool value `01`、i64 little-endian slots `07 00 00 00 00 00 00 00 | 00 00 00 00 00 00 00 00 | ff ff ff ff ff ff ff ff`、UTF8 offsets `0,2,2,2` 和 payload `c3 a9`、BIT slots `0001 | 0000 | 0100`。同一向量同时检查 decode 后外层 descriptor 列序、三批与单批编码相同、descriptor 输入反序、pool 线程数和 display name/ordinal 变化都不改变文件 bytes。

`canonical_ipc_metadata_matches_fixed_jcs_and_schema_version_vector` 使用固定字面量检查 schema 唯一版本键和值 `1`、field 唯一 metadata 键以及四键 JCS：`logical_type`、`sql_type`、`declared_type`、`labels`。Arrow `Field` 保留 canonical 字段名与 nullability；原始 ordinal 不序列化，writer 按 canonical name 形成 profile 列序，decoder 再按外层 descriptor 布局恢复列序。nullability 另由 adapter 的 PyArrow smoke 检查。

`canonical_mapping_covers_declared_arrow_types_and_business_text_layout` 覆盖有符号/无符号整数、Float32/64、DECIMAL、ENUM、SET、JSON、DATE、DATETIME、TIMESTAMP、TIME、Binary 和 BIT 的声明映射及规范文本保值。float 固定位向量由 `canonical_float_layout_preserves_fixed_normalized_bit_vectors` 逐字节检查，取自 Shared Kernel 已有 scalar vectors：Float32 `3f800001`、最小 subnormal `00000001`、normalized negative zero `00000000`；Float64 同样检查宽度、subnormal 与 zero bits。SET decode 文本按既有固定 declaration-order members 检查；Shared Kernel 的 sequence framing 仍由原 owner 测试负责。

其他关键行为包括 N/DDL 列顺序与 chunk 切分确定性、空表和零列非零行保值、all-NULL/普通 Binary、small/large offset 全列 payload 阈值、实际 output 与增长峰值限制、取消和实际 future deadline、未知 mapping version/metadata 矛盾/重复声明/非法 raw Arrow type 拒绝、reader borrowed input byte cap。writer 使用固定 65,536 行 IPC record batches。decoder 的 raw type 检查位于标准 reader 之前，防止畸形 FlatBuffer 触发 panic 或在超预算长度上预分配。

## 候选与依赖基础镜像

最终代码候选是 `db7767ffbb5e4eee269b3c0e4778351dd98a092a`，Rust tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d`。CT06 worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-a-core-a1` clean；legacy 链接就绪，所有编译、测试、静态检查与容器检查均在 CT06 执行。

最终 backend/worker 依赖基础镜像为 `gateway-backend-deps:lock-d054366c02fa`，完整 input SHA256 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`。clean CT201 worktree 的只读 `--print-input` 记录：`/home/dev/gdds-test-tmp/logs/p6-s2b-a-dependency-base-input-db7767.log`，SHA256 `d858f34e811b60cec8f5c2a772a4284b817421e5e08efd368b2fc32e4f980ce3`，其中 `inputs-db7767.json` SHA256 `f7df461e1f4b3f3fd45a9fbfb014942fa3dd0d017cc0a95e2e93ffcf4d7eac44`。该输入由 `vnext/scripts/build-backend-dependency-base.sh --print-input` 在 2026-11-06 09:50:29–09:50:37 UTC 计算，未在 CT201 跑测试。

CT06 对已加载 d054 tag 的 read-only 身份核验记录：`/home/dev/gdds-test-tmp/logs/p6-s2b-a-dependency-base-existing-d054-identity-retry-db7767.log`，SHA256 `c0e93bf597c504b2b99548aa15872ae7a008b8b6d74f1bb2faf3e5d4f793492c`。docker-save archive 中的 config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 与 19 个 RootFS DiffID 均和来源归档相同；完整 DiffID 列表及原始传输记录见[节点 readiness §7](p6-node-06-07-readiness.md#7-新传输镜像完整身份)。本地 tag 未 reload、retag 或 rebuild。原始来源归档为 `/home/dev/gdds-p6-artifacts/s2a/gateway-backend-deps-lock-d054366c02fa.tar`，SHA256 `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`，来源提交 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`。独立身份提取 helper SHA256 为 `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972`。

此前的中间 `gateway-backend-deps:lock-994c32446656`（完整 input SHA256 `994c32446656695d3208c9b0918c196313fe7138617eccac7dae0632971bfd7d`、config digest `sha256:8085d8d981cad1c9b0aaba2ad1d1b75ee4eaddddbd032ad334e488dc3d2affde`、19 DiffID）不属于最终候选。最终 adapter 移除了 Shared Kernel direct dependency，锁回到基准状态，所以 A 最终候选回到 d054；不得把 994c 写为最终所用基础镜像。

## CT06 最终验证

Rust workspace 在 2026-11-06 09:57:51–09:59:57 UTC 执行，日志 `/home/dev/gdds-test-tmp/logs/s2b-a-final-rust-db7767.log`，SHA256 `2dd387cb4f40be5fbb94aabfa85498ec00ebb7b27b8d8884f08c4ffab95ad6dd`。起止 HEAD 均为 db7767，worktree clean，`CARGO_NET_OFFLINE=true`、`CARGO_BUILD_JOBS=4`、target 在 worktree 外。该日志记录 `step_start` 与每步 exit，但没有打印完整 cargo 命令；实际 CT06 调用命令为：

```text
cd /home/dev/gdds-test-tmp/wt/p6-s2b-a-core-a1/vnext/rust
cargo fmt --all --check
cargo clippy --workspace --locked --offline --all-targets -- -D warnings
cargo test --workspace --locked --offline -- --test-threads=1
cargo build --workspace --release --locked --offline
```

完整 Rust 命令来自该 CT06 验证调用记录，不声称是日志文件中的原文。四步均 exit 0；workspace test 日志包含 architecture guard 21/21 与 canonical core 46/46。

五个 Python 包 Ruff/mypy 共 10 项均通过。日志 `/home/dev/gdds-test-tmp/logs/s2b-a-python-static-db7767.log`，SHA256 `57ecd8dd64aa0290a660946af521df2df1c94cd1a61501b641858d034ff74587`；CT06 2026-11-06 10:00:25–10:00:27 UTC，起止 HEAD db7767、worktree clean、`UV_OFFLINE=1`。

强制重装 `gateway-compute-python` 扩展并校验 installed `__build_input__` 与当前 `vnext/rust` tree `5b222191f4689b0eb0a7c2a1123bb299efb13e9d` 一致。日志 `/home/dev/gdds-test-tmp/logs/s2b-a-extension-sync-db7767.log`，SHA256 `63c177e6f22f04d73e478cc069b3d6373e14bf5a10ae439cb8351f1540eb9acb`，CT06 10:03:13–10:03:24 UTC。之后 backend native adapter focused pytest 为 8/8；日志 `/home/dev/gdds-test-tmp/logs/s2b-a-python-adapter-focused-db7767.log`，SHA256 `49d3bb268ec9129cdf37af48644b7cde707d219d7c153391b54af2a10d272284`，CT06 10:03:52–10:03:53 UTC。

当前候选容器证据由 `/home/dev/gdds-test-tmp/run-s2b-a-container-smoke-db7767.sh`（SHA256 `126c4c2daadce7da5629184715aa2be55cddfc70c4fa5bb411c5680b37a9f11f`）及 native 输入 `/home/dev/gdds-test-tmp/s2b-a-native-smoke-db7767.py`（SHA256 `8bb7824df9c338ba2f69824b6f3d97352d6aa14f5c74606532e575c85f246918`）绑定。脚本用唯一 Compose project 和 image refs，`TMPDIR=/home/dev/gdds-test-tmp`、pytest `-n 0`、d054 backend base、RS 已缓存 dependency-base、`GATEWAY_DOCKER_BUILD_NETWORK=none`，未设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。它只运行既有 `test_backend_container_ready_and_stops_cleanly_with_repository_service` 单例，之后 Compose build worker；没有跑完整 runner 或业务旅程。

CT06 容器日志 `/home/dev/gdds-test-tmp/logs/s2b-a-container-smoke-db7767.log`，SHA256 `e73a1acff0f9cb936de50bd6d4e8d5b05fd87929cd5f9751395cb243a1bbf6bf`，时间 10:23:23–10:24:18 UTC，起止 HEAD db7767、worktree clean。health/clean-stop 测试 `1 passed`；运行 backend 镜像 ID `sha256:88665d846710bd26891acbba7fbcb516e57cfaf95edd3314af457e4a48d5b6a0` 与 freshly built backend image ID 相同。worker image ID 为 `sha256:452decd04cbdf87b2a604b6e6802448ae041bc6c243b59dcf812d514b88c7eac`。health test 需要的 Repository Service 以当前 identity 构建为唯一 tag `s2b-a-db7767-repository-service:latest`；其 build-input revision `3b037adf4caf33f65e124a34f56f12f42e529641`、source tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2` 与本候选的 owning image identity 一致。重建原因是既有 RS tag 的 source labels 已过期；当前 RS dependency-base 的 lock label 与现锁一致，build network 为 none。

native container smoke 在 health provenance 确认的 backend image ID 上直接调用 `_encode_canonical_ipc_native`，经 PyArrow reader 检查 `[7, null, -1]`、nullable 和固定四键 metadata。记录的实际值：Arrow 输入 buffers `[1,24]` 共 25 bytes；canonical IPC file 1,314 bytes；定义为 `IPC file bytes - Arrow input buffer bytes` 的 remainder 为 1,289 bytes；IPC SHA256 `974bb1c6317b3820c55e0388e575ee7cd7d671cab814ce7e7e0442addca5a094`。这里的 remainder 是 IPC file 与输入 Arrow buffers 的差值，不外推为内存成本或单一 framing 开销。镜像内 `gateway_compute._native.__build_input__` 实际为空字符串；backend Dockerfile 尚未接线该字段，所以只记录实际值，不宣称容器扩展的 Git build-input 匹配。

Compose provenance JSON 路径 `/home/dev/gdds-test-tmp/artifacts/s2b-a-db7767/compose-provenance.json`，SHA256 `170566393b6e16d962573b0b8aec385676385a0fec0698a25d07c0fd0a261e69`。验证后该唯一 project 容器/volumes 已清理；CT06 busy marker 已释放；没有运行容器。backend/worker/RS 唯一 candidate image refs 为本次证据保留。

## 失败与修复记录

1. 较早候选 `451c315bf2` 的 Rust workspace 检查失败：clippy 发现 11 项可修正 lint，architecture guard 拒绝 adapter 对 Shared Kernel 的 direct edge。保留日志 `/home/dev/gdds-test-tmp/logs/s2b-a-final-rust-451c315.log`，SHA256 `b02b0747da9778f416ef9b7cb4ef1c9c26b417a8d9834652e4b20f0bd54e1e1f`。修复在 core 增加窄 setter、adapter 只传有界 metadata，并改正 lint；architecture guard 未放宽，Cargo.lock 回到基准。最终 db7767 Rust checks 通过。
2. 早期 Python metadata oracle 将 nullability 错放入 field metadata。修正为 mapping spec 固定四键，并单独断言 Arrow field nullability；保留失败日志 `/home/dev/gdds-test-tmp/logs/s2b-a-python-adapter-focused-7d2d87e.log`，SHA256 `efc95e6e39ebbffcc14599d0927ca6b2f67c77bae90ebe58892eb21683bb1c50`。最终 adapter focused test 8/8。
3. CT06 d054 identity 首次尝试的 preflight 发现 worktree 仍 dirty，未调用 Docker。保留 `/home/dev/gdds-test-tmp/logs/p6-s2b-a-dependency-base-existing-d054-identity-06.log`，SHA256 `b0feee0807ad9218e91be65a8c3d75f5ff2e77ef55a56f2e4865e3be5fad49bd`；仅在确认 dirty diff 属于本实现后同步到 db776 clean worktree 并按审核通过的只读 identity checker 重做，成功日志见上节。该记录不覆盖原失败日志。
4. 首次 extension sync 调用在 SSH 嵌套 shell 的命令解析阶段失败，远端命令体未执行。保留 `/home/dev/gdds-test-tmp/logs/s2b-a-extension-sync-shell-parse-fail-db7767.log`，SHA256 `9854efddd98f57b5c3eda0e97ba6425f9e0253fb5ed6f1a9bcaf7f0f3f53be0c`；改用绝对路径命令成功重装并核 build input。最终容器 wrapper 本身在 CT06 `bash -n` 通过。

曾对中间 994c 镜像做身份提取，首次错误是 `tarfile r|` 流不支持脚本随机 seek，日志 `p6-s2b-a-dependency-base-load-451c315.log` SHA256 `efb9452191bb4bc50df7a9c7acc349a80cc610eeacf37f7dd86ba22c87e18830`；第二次错误是假设 manifest 必须为 tar 首成员，日志 `p6-s2b-a-dependency-base-load-identity-retry-451c315.log` SHA256 `df2308bc81efc5607519ebdac76ac035a4c105176f9477a4584b3a1803b701f3`。实施者停止第三次尝试；root 在独立审核确认固定修复与来源身份后，按既有 Owner/DC80 授权恢复单步身份提取。使用已核 helper 后成功，记录 `p6-s2b-a-dependency-base-load-identity-authorized-451c315.log` SHA256 `5721e09a7c637f46ecce66158e2ff627b38c2d1045b99ba9431ae0ec833e4b3f`。最终 d054 tag 另行用同一 helper 验证；不得以中间镜像结果替代最终 d054 provenance。

## A 边界与交接

本节完成唯一纯内存 Arrow mapping/IPC writer/reader 与最小 C Stream encoder 入口。未实施 B 业务 materialization/projection/ordering/hash pipeline；未连接 ArtifactStore、mmap、worker/config 或 C 恢复/T1；没有切生产 parser 或删除仍服务生产的 Python 实现。业务规范化值、全量历史 digest 等消费者仍按 owning slice 负责。

部署 N/M 与 FULL/RSS 校准、后续消费/恢复、阶段整体完整旅程均不属于本 A 验证；本报告不能被引用为它们已经通过。A 本地代码、固定 vector、Rust/Python 验证以及必要容器健康/clean-stop + codec smoke 均绑定到 db7767。
