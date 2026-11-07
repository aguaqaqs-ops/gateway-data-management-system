# Phase 6 S3 B 实施交接

状态：最终 B 候选已完成 06 focused 验证，待同角色独审核收；本页不自行宣称 B GO。设计固定 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，A 已按 `p6-s3-a-review.md` 最终 GO 放行。

最终 B 代码候选为 `fbb7fca65d81ff61ecf0022e85da0bdf0f71ae9a`。它包含预算第二轮 `ac21ad4069ab`、临时差分和诊断至 `2e9758885a`、共享 context 的并发多任务性质 `39bfa7552e`、真实逐表 CLI 当前物化接口与 kernel scope `4efa4b3ec5`、测试 fixture/原型回归/内部排序断言修正至 `2b629e4562`，以及 CLI 非记录 role 分流 `503cfbd4da`。2b 在 06 的 Rust 全 workspace、native build input、Python 六例与八包 SHA 已通过；真实逐表首败 `t1/forwardtable_yx1` 属 CLI 将 `SNAPSHOT_ONLY` 错送 B probe。503 的四档逐表差分已通过，但 CLI 独立 mypy 首败 20 个测试工具类型错误；fbb 只修 B 临时工具类型、去除旧 benchmark 辅助导入，Rust tree 不变。fbb 的受影响差分和静态复验已在 06 全通过，证据列下。

## 边界与实现

B 负责共用比较计算：standard/keyless 与 ordered 的 canonical Arrow 共有列投影、Shared Kernel scalar/SET framing、行身份、facts 顺序、artifact 顺序、调用方共享池/取消/单调截止/预算。C 负责三族 records Arrow builders、流式 JCS 和真实读取校验，D 负责风险规则与去重接线，E 删除替换期旧 Python 行比较、旧 Vec 原型和临时差分入口。B 不切 Python 生产路由、不加部署选择开关或运行时回退，不修改 Submit mutation。

B 写入区间从 A 后父提交 `ecb96af0092999e54c5499f126ee1436e38ce7fd` 到代码候选 `fbb7fca65d81ff61ecf0022e85da0bdf0f71ae9a`；区间内并行文档提交不算 B 代码。`git diff --name-only ecb96..fbb -- vnext` 恰有 11 路径：

```text
vnext/backend/benchmarks/s3_b_real_table_diff.py
vnext/backend/tests/test_comparison_s3_b_differential.py
vnext/rust/gateway-compute-core/Cargo.toml
vnext/rust/gateway-compute-core/src/comparison/kernel.rs
vnext/rust/gateway-compute-core/src/comparison/mod.rs
vnext/rust/gateway-compute-core/src/comparison/ordered.rs
vnext/rust/gateway-compute-core/src/comparison/ordered/tests.rs
vnext/rust/gateway-compute-core/src/comparison/probe.rs
vnext/rust/gateway-compute-core/src/comparison/standard.rs
vnext/rust/gateway-compute-python/src/lib.rs
vnext/rust/gateway-compute-python/src/s3_compare_probe.rs
```

`Cargo.toml` 把锁定的 `sha2 =0.11.0` 提升为生产依赖以流式算摘要，Cargo.lock 不变；core 的 kernel/standard/ordered 与测试为正式 B API，C/D 用其 locator、预算和排序视图。`probe.rs`、PyO3 probe/注册以及两份 backend 差分工具只属替换期测试，E 在正式接线验证后删除，不能将 JSON probe 接入生产。

早期 Rust 检查点 `3577df182d6481a9c6e49554e445c81071924c09` 仅供当时的 06 scratch 格式与编译反馈，不是最终候选。该提交的 `comparison/kernel.rs` 定义 operation-local 共享预算/取消/截止；`standard.rs` 的 `StandardComputation` 持有 cloned Arrow RecordBatch 的 Arc backing owner、行定位、双排序索引与计数；`ordered.rs` 初步扩展 canonical metadata/SET 和多 batch 入口。当时 ordered Vec 结果、零 batch schema 与增长前预算尚待收口，已在后续提交修正。

静态第二轮候选 `ac21ad4069abb08f162d9418a6426a63d7508974`：仅修改 core 的 `comparison/kernel.rs`、`mod.rs`、`ordered.rs`、`standard.rs`。新 ordered 主入口返回 Arrow owner + 三族 locator 和分别排序的索引，`facts_metadata` 明示只含状态、计数、digest 和小 metadata；正常与 TABLE_DEGRADED 的标准记录均在 locator 视图，C 必须用未裁剪 Arrow 值重放完整 table/core facts payload。旧完整 Vec 仅替换期单批原型入口，E 删除。缺侧整表仍归 Python metadata 分支，两个有 schema 的零 batch 侧是存在的空表。unchanged ordered 只读当前 0/N batch，返回相同的两侧 ordered/occupancy digest，不跑 before/LIS/records。

本候选已静态写入：S2b canonical metadata/physical/SQL declared type 最小一致性校验与 Utf8 SET 声明序 sequence frame；keyless occurrence 首次直接 row digest、重复用独立 domain preimage；ordered 流式 digest 对位置/计数守 I-JSON 2^53−1 边界；COLUMNS_ADDED 且有共享 compare-excluded 列时以完整共有列逐行 digest multiset 识别隐藏变化。core `sha2` 从已锁定 0.11.0 dev 依赖提升为 regular，用于流式 digest；Cargo.lock 与新 crate 集合不变。该静态候选未运行 fmt、clippy 或测试，不能作为 B GO。

`782d07f054` 已将旧原型独有的 512 列、200 万 ordered 行准入上限提高至 S2b 生产 canonical Arrow 的 2048 列、1000 万行预算上限；M 的实际可用额度仍先于行分配约束计算。

### 预算与 owner 约定

调用方先从 operation M=24 GiB 中按唯一 backing owner 计费已 pinned 的 canonical Arrow 输入（含 mmap 驻留风险），把剩余值交给 `KernelContext`。B 的 lease 只计编码帧、临时索引、排序与结果定位/metadata；`RecordBatch::clone` 只复制 Arc 引用，不重复计 backing。**当前 B API 仅定义这个计费约定，没有持有 Python 的输入 charge token，因此尚不能声称端到端保持了 input charge。** C adapter/D 调用层须组合持有输入 owner/charge 与 B result，直到最后一个 records/facts/risk 消费者结束，D/E 在真实调用测试核；若需要最小 Rust owner token，再按该具体接口补，不建全局 allocator registry。B 计算完成应释放编码/索引 scratch charge，仅保留实际结果；C 的 output builders、重排/JCS/writer 与 D 风险消费按自身分项增长前另行预约。N1/32 GiB envelope/8 GiB reserve/M24 GiB 不变，节点 Cargo jobs4/pytest workers4 与产品 N 分开。

ac21 的 local scratch 以 `ArrayData::get_slice_memory_size()` 按本 batch 可见字节估算，避免共享 backing 的随机切片重复乘整块 capacity；这不是 input backing 的唯一 owner charge。small metadata 校验先预约、校验后退账；主 lease 预含结果 metadata 上界及编码/索引/排序结构；locator push 在 String/Vec 构造前增长预约；结算 `shrink_to` 只退 scratch，绝不事后增长。新增共享 slice 同 budget、零 batch 宽 metadata 紧预算拒绝/释放向量。原审须对这组根因复核；若第二轮仍不守相同预算不变量，按 Owner 两轮停止要求暂停，不自行叠补第三轮。

### 语义核点

- Python planner 继续先处理单侧、role、健康 early exit 与 schema/key 退化，再调用 Rust 行核。非控制类语义异常按现表降级；取消、截止、资源错误直接向 operation 传播。
- `BROWSE_ONLY`/`SNAPSHOT_ONLY` 的双侧 `COLUMNS_ADDED` 是 D/E 的特殊接线：固定 Python `standard._compare_non_record_role` 对 `schema.selected`（两侧所有共有列，**包括** compare-excluded 列）逐行计算 row digest Counter，`content_changed` 是两侧 Counter 不等，仍无逐行 records。D 应在该分支调用 B 的 `StandardMode::Keyless`，传 `selected_columns=all shared`、`compare_excluded_columns=[]`、`columns_added=true`、`emit_add_delete=false`，以 `suppressed_added_count != 0 || suppressed_deleted_count != 0` 还原布尔值并丢弃计数；保持 caller 输入 owner/charge、M/取消/截止。其余 non-record role 情况沿旧 descriptor 元数据公式，不做行扫描。B 的真实数据 CLI 将这些任务列为 Python-owned `metadata_only` 子集 `python_owned_non_record_role`，其中 `COLUMNS_ADDED` **可能读行**；该计数不能作为零行读取证据。D 用固定 `test_comparison_rule_roles.py` 的双 role 向量核 status、records、content_changed；E 删除旧 `_read_rows`/Counter 热点。原审确认 B 无需为这一后续接线另加固定向量。
- keyless multiset 对重复行保留次数；occurrence 0 用原 row digest，大于 0 用 `keyless-row-occurrence:v1\0`、digest ASCII、minimal ULEB128 后再做 row-domain SHA。A 的第三份固定 expected 为 `sha256:a30dfdfae0f29e7d4a7da411578d351fac59a100052dc8fd2135f6940f4ba2bb`。
- facts 摘要使用完整未裁剪 payload 与 facts 顺序；records content 使用 artifact 顺序及 detail 裁剪。Blank 私有 `entity_key_kind` 保留于 facts 源视图，不进 Parquet 物理 schema。facts_core 必须重放 table payload bytes，不能拼 table hash。
- unchanged ordered 只读当前侧、两侧摘要相同，不运行 LIS、不生成 records。空表与任意 batch 划分仍必须有确定性。ordered 主路径保留 GID/no 绝对位置、LIS 并列、blank gaps 与伪 GID 规则。
- `ordered.rs` 的旧 `gdms.scalar_type`/单 batch 原型是替换期冻结差分材料，不是新生产兼容层；E 随其旧专用消费者删除。新路径要求 S2b `gdds.canonical_type` 与 canonical mapping version；SET 为 Utf8 中按声明序的逗号分隔成员，再用 Shared Kernel Sequence framing，NULL 为 null scalar frame、空 SET 为零长度 sequence。canonical metadata 存在而畸形/类型冲突时直接失败，不回退旧字段。

## 验证与证据

检查点的唯一 06 测试者先在 scratch 副本执行 `cargo fmt --all` 并回传四个 Rust 文件的机械格式补丁；实施者在 main 应用后提交新固定 SHA，再由同一测试者在 06 clean 已提交独立 worktree 跑 fmt --check、focused clippy/core tests。首个失败停报，按同角色修复并原审复审。Rust 变更后 backend focused 必须 `--reinstall-package gateway-compute-python` 并从当前 Git `HEAD:vnext/rust` tree id 校验 native build input。所有测试、编译、lint、真实数据和容器仅在专用节点；本地仅静态阅读与编辑。

`9b34be7356a92228ef07ee0c4f01bf215e2bf653` 的 06 Rust 检查点：fmt --check exit 0；clippy exit 101（unused ListArray、不可变 batch iterator），按首失败规则未运行测试。原日志 `/home/dev/gdds-test-tmp/p6-s3-b-test-9b34be7356a9/logs/rust-focused.log` SHA256 `c0eecef9412e267f98cef536d91025af4c5209db77ace24f790de27349fc8d6f`；两点已在后续源码修复，原失败保留。格式后 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 测试准备中测试者的额外只读命令两次 exit 127，未启动 fmt/clippy/test；依 DC68 已停并由协调者交 Owner，不能将 b917 记为运行过。

替换期差分实现为 `comparison/probe.rs` 小策略 JSON/locator frame 视图、`gateway-compute-python/src/s3_compare_probe.rs` Arrow C Stream 薄桥、`backend/tests/test_comparison_s3_b_differential.py` 和 `backend/benchmarks/s3_b_real_table_diff.py`。它固定 4d5 Python `standard.py`、`ordered.py`、`row_encoding.py` 源 SHA，路由变更时失败而不是两边误用新核；比较 keyed/keyless/ordered 的 counts、record kind/identity、locator 解引用完整 frame、ordered/occupancy digest、blank 私有键和新增列隐藏内容。逐表工具先对 datasets.json 与 P5 S4 既定身份核八包 size/SHA，然后按 tier 只做表级差分；不启动完整旅程，标准 early exit/缺侧 metadata 计为上层任务而不伪称 Rust 已扫描。E 删除四处临时材料及 `comparison/mod.rs` 的 probe 导出、`gateway-compute-python/src/lib.rs` 注册。该薄桥不增加 member dependency、不更新 Cargo.lock；probe JSON 输出仅为替换期测试视图，不作 production bridge 或 M 端到端计费证据。它已按下文 fbb 原件编译并验证。

后续差分覆盖还比较完整 ordered/blank summary 与 blank interval 六字段；unchanged ordered 给新核空 before stream；canonical 伪 GID 非法输入由固定 Python 独立产生 `CANONICAL_GID_INVALID` 退化事实。真实 t1–t4 任一旧事实预退化即列 tier/table/诊断失败，不能静默跳过。独立 CLI 全进程只初始化一次 N1，四个 tier 各在单独 M24 operation scope 内完成 v1/v2 当前 preview API 物化与比较；`repository_id` 固定、`export_cache=None`，未改旧 benchmark 或生产启动边。

原审在 ac21 第二轮静态复核时认为已针对性关闭预算根因，但当时未有完整运行证明。另指出两项 ordered 诊断差异：`CanonicalPseudoGid` 的非法非空非零 gid 应报 `CANONICAL_GID_INVALID` 而非 source 诊断；合法 S2b Utf8 字段充当 gid/no 时，非空文本即报 `ORDERED_INTEGER_INVALID`，不能把 `"1"` 解析为数字。后续增量已按冻结 Python `_parse_stable`/`_integer` 修正并加诊断向量；旧原型入口保留替换期 numeric-text 宽容供差分，E 删除。Owner 已放行 DC68 恢复；同一 06 测试者实际重跑 b917 已审脚本，fmt exit 0、clippy 因 `standard.rs` 两处 `usize` 错误解引用 exit 101，focused test 未运行。原日志 SHA256=`5ba79e1bf4c38850f9f35ba1f1ae77b30364e863987eb2a1fefafc167a20cf74`，该编译错误已在 `a665a3c063` 修正；不重跑旧候选。

其后原失败均按首失败保留、由同角色修复并独审：`4efa4b3` clippy 编译 E0596（日志 SHA256 `ee3a15b125830433289684a5ee46334f6ac20286d18a4c07c195b10860791b38`）；`4f1bd419` clippy 19 条 lint（`a42bdce9329c5d69aa532ba5c768d347bfc87a42fbc5a21b1784c04829251a29`）；`b63409b3` workspace test 57 过/15 败，根因为合成 BIGINT metadata bits 与 S2b 不符及旧 ordered prototype 预算退化边界（`a8263f71cc1130610bb8dc79caf68ed176f105493be4632bef07f8535c705c78`）；`04afdbb3` workspace test 71 过/1 败，根因为断言读 locator 储存序而非冻结 facts 顺序（`b03f83593d3f5e58402532b185fddfc563578dabf20247be51c926e689944552`）。这些日志在各自 `/home/dev/gdds-test-tmp/p6-s3-b-<SHA8>/logs/run-final.log`，均未把失败对象记作 PASS；2b/503 的后续首败另列下文。

06 执行顺序：clean 固定候选、外置 target、offline/jobs4；a665 与 39b 的 scratch `cargo fmt --all` 机械补丁均已回传应用并重固定 SHA。随后依次 `cargo fmt --all --check`、`cargo clippy --workspace --locked --offline --all-targets -- -D warnings`、`cargo test --workspace --locked --offline`，首失败即停。core 的 standard 测试有固定向量与性质用例；新 standard 用同一 caller pool/context 并行12个 keyed/keyless/全重排 ordered 任务，比 N1/N4 的有序签名与释放余额，资源向量还核已过期截止。Rust 更动后使用当时提交 `git rev-parse HEAD:vnext/rust` 作为 `GATEWAY_RUST_BUILD_INPUT`，在 backend 受控离线 uv 同步时 `--reinstall-package gateway-compute-python`，通过 build-input check 后仅跑 `tests/test_comparison_s3_b_differential.py`（6个参数化用例）。八包实际 SHA 全核后，单独运行 `python -m benchmarks.s3_b_real_table_diff --root <06实际输入根>`；只做逐表差分。任何 Rust/API/差分失败均保留原日志并停报，不改旧 Python expected 或 golden 消差。

`2b629e4562166de706da984995fc2ebc14fb1252` 的实际 06 focused 运行在 `gw-dms-06`，UTC `2026-11-07T23:27:50Z`–`23:29:23Z`，起止 HEAD 相同、worktree clean、六锁无漂移。Rust tree `cef7eaf099937a66ce33c160154936a5c086f0be`；workspace fmt、clippy、test 均 exit 0，backend 离线强制重装扩展与当前 Rust tree build input 校验 exit 0，固定 Python 六例 `6 passed in 1.65s`，八个真实包 size/SHA/manifest identity 全匹配。真实逐表在 `t1/forwardtable_yx1` 首败，五包静态检查未启动；原日志 `/home/dev/gdds-test-tmp/p6-s3-b-2b629e45/logs/run-final.log` SHA256 `28103b95e234a63dcc24eb1f36fcc641ac2aeb14de119f6def0d413413986f57`。独审按固定 migrated 规则与 resolver rank 核出该表 comparison role 为 `SNAPSHOT_ONLY`，旧 CLI 把它送到 standard probe 导致计数假差异。`503cfbd4da` 只修该 CLI 分流，Rust tree 不变；2b 原失败仍保留。

`503cfbd4da72b232dc175c3692c040adf499878c` 的 06 逐表运行在 `gw-dms-06`，UTC `2026-11-07T23:36:04Z`–`23:39:59Z`，起止 HEAD 相同、worktree clean、六锁无漂移；build input 与八包真实 SHA 再核 exit 0。四档 `planned_tables` 为 125/220/193/312，`row_kernel_checked` 为 9/72/76/145，`metadata_only` 为 24/50/30/34，`python_owned_non_record_role` 为 24/28/29/34，`standard_early_exit` 为 92/98/87/133，`predegraded` 全 0；逐表 CLI exit 0。行核计数含 ordered unchanged 的单侧摘要路径，不等同双侧行比较次数；本工具未量测 task-kind 细分、真实读取量或速度收益，D 后续必须按正式接线补证。CLI 专属 mypy exit 1（20 errors：旧 p6_v1 benchmark 11、新 CLI 8、B 差分 test 1），按首失败停止，五包静态未启动。原日志 `/home/dev/gdds-test-tmp/p6-s3-b-503cfbd4/logs/run-real-static.log` SHA256 `2100c1ea15380859af33a06698a78be0276527a74619b47a67652a9bb3bddcd1`。fbb 删除旧 benchmark 导入、给两处 task 精确类型、显式收窄 descriptor 与 isolated Arrow reader；旧 frozen expected/Rust 树均未改。

`fbb7fca65d81ff61ecf0022e85da0bdf0f71ae9a` 的最终受影响验证在同节点 clean、已提交 detached worktree，UTC `2026-11-07T23:45:00Z`–`23:49:11Z`，起止 HEAD 均为 fbb，六锁无漂移。Rust tree 仍为 `cef7eaf099937a66ce33c160154936a5c086f0be`，原 2b workspace fmt/clippy/test 及强制扩展重装原件绑定该 tree；fbb 再核已安装 build input 与此 tree 相等。固定 Python 差分六例 `6 passed in 0.65s`；八包实际 size/SHA 与 datasets.json 固定身份全匹配，`datasets.json` SHA256 为 `78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f`；四档真实按表差分重验 exit 0，`row_kernel_checked`、metadata/non-record/early-exit/predegraded JSON 与 503 一致，真实步骤 UTC `23:45:01Z`–`23:48:49Z`。CLI 自身 `mypy -m benchmarks.s3_b_real_table_diff` exit 0；`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 的 ruff 与 mypy 各 exit 0，整体 `FINAL_EXIT=0`。原日志 `/home/dev/gdds-test-tmp/p6-s3-b-fbb7fca6/logs/run-real-static.log` SHA256 `26826be79042550ee2e98f66f8e99b156b2696a27ad053b9e0f01992dd985b1e`，脚本 SHA256 `0c13f470981de362dc912db40315f9c4f7e7ac78db874b2ba18be5f11f99ce4e`；06 使用本节点预置离线 uv/Cargo/toolchain 与 worktree 外 target，无新依赖缓存转运，未改任何锁或输入包。06 占用标记在 UTC `23:50:26Z` 释放，原工作树、缓存和日志保留。此节未跑完整旅程、权威 runner、Compose 或性能测量。

本节代码改动未碰 owning Contract、golden、HTTP DTO、六锁、Dockerfile、Compose 或前端。B 未切生产路由；现有 backend/worker 镜像未作为当前 fbb 结果，Rust 生产依赖/源码变化的镜像重建与 S3 ready 容器门禁留 E 在当前最终 HEAD 执行。C 必须按上文 owner/lease/locator 接口构建 Arrow records、流式完整 facts/JCS；D 接入风险/去重及 non-record `COLUMNS_ADDED` 行 multiset 布尔值并核真实输入 charge；E 删除旧 Python 行比较、旧 Rust Vec 原型、`comparison/probe.rs`/PyO3 `_s3_compare_probe`、两份 B 临时差分工具及本节所述旧 Counter 热点。B 没有为正式生产接线或容器结果作出通过声明。

本节覆盖 C1/C2/C3/C4/O1 相关独立固定向量、随机 batch/允许 N 的确定性与预算/取消/截止、standard/keyless/ordered 替换期 Python 差分，以及 t1–t4 v1/v2 按表差分。expected 源为 A、owning Contract、已冻结 Python/golden，不从新 Rust 输出生成。独审尚须核收本页原件后才可给 B GO；C/D/E 的正式生产接线与 S3 ready 门禁仍为后续责任。
