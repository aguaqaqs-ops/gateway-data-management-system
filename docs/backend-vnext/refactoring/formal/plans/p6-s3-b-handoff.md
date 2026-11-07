# Phase 6 S3 B 实施交接

状态：实施中；本页的检查点不是 B GO。设计固定 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，A 已按 `p6-s3-a-review.md` 最终 GO 放行。

## 边界与实现

B 负责共用比较计算：standard/keyless 与 ordered 的 canonical Arrow 共有列投影、Shared Kernel scalar/SET framing、行身份、facts 顺序、artifact 顺序、调用方共享池/取消/单调截止/预算。C 负责三族 records Arrow builders、流式 JCS 和真实读取校验，D 负责风险规则与去重接线，E 删除替换期旧 Python 行比较、旧 Vec 原型和临时差分入口。B 不切 Python 生产路由、不加部署选择开关或运行时回退，不修改 Submit mutation。

Rust 检查点 `3577df182d6481a9c6e49554e445c81071924c09` 仅供 06 scratch 格式与编译反馈，不能表述为 B 最终候选。该提交的 `comparison/kernel.rs` 定义 operation-local 共享预算/取消/截止；`standard.rs` 的 `StandardComputation` 持有 cloned Arrow RecordBatch 的 Arc backing owner、行定位、双排序索引与计数；`ordered.rs` 初步扩展 canonical metadata/SET 和多 batch 入口。现有 ordered Vec 结果、零 batch schema 与增长前预算尚待收口，故本检查点不作 B 验收。

静态第二轮候选 `ac21ad4069abb08f162d9418a6426a63d7508974`：仅修改 core 的 `comparison/kernel.rs`、`mod.rs`、`ordered.rs`、`standard.rs`。新 ordered 主入口返回 Arrow owner + 三族 locator 和分别排序的索引，`facts_metadata` 明示只含状态、计数、digest 和小 metadata；正常与 TABLE_DEGRADED 的标准记录均在 locator 视图，C 必须用未裁剪 Arrow 值重放完整 table/core facts payload。旧完整 Vec 仅替换期单批原型入口，E 删除。缺侧整表仍归 Python metadata 分支，两个有 schema 的零 batch 侧是存在的空表。unchanged ordered 只读当前 0/N batch，返回相同的两侧 ordered/occupancy digest，不跑 before/LIS/records。

本候选已静态写入：S2b canonical metadata/physical/SQL declared type 最小一致性校验与 Utf8 SET 声明序 sequence frame；keyless occurrence 首次直接 row digest、重复用独立 domain preimage；ordered 流式 digest 对位置/计数守 I-JSON 2^53−1 边界；COLUMNS_ADDED 且有共享 compare-excluded 列时以完整共有列逐行 digest multiset 识别隐藏变化。core `sha2` 从已锁定 0.11.0 dev 依赖提升为 regular，用于流式 digest；Cargo.lock 与新 crate 集合不变。该静态候选未运行 fmt、clippy 或测试，不能作为 B GO。

### 预算与 owner 约定

调用方先从 operation M=24 GiB 中按唯一 backing owner 计费已 pinned 的 canonical Arrow 输入（含 mmap 驻留风险），把剩余值交给 `KernelContext`。B 的 lease 只计编码帧、临时索引、排序与结果定位/metadata；`RecordBatch::clone` 只复制 Arc 引用，不重复计 backing。**当前 B API 仅定义这个计费约定，没有持有 Python 的输入 charge token，因此尚不能声称端到端保持了 input charge。** C adapter/D 调用层须组合持有输入 owner/charge 与 B result，直到最后一个 records/facts/risk 消费者结束，D/E 在真实调用测试核；若需要最小 Rust owner token，再按该具体接口补，不建全局 allocator registry。B 计算完成应释放编码/索引 scratch charge，仅保留实际结果；C 的 output builders、重排/JCS/writer 与 D 风险消费按自身分项增长前另行预约。N1/32 GiB envelope/8 GiB reserve/M24 GiB 不变，节点 Cargo jobs4/pytest workers4 与产品 N 分开。

ac21 的 local scratch 以 `ArrayData::get_slice_memory_size()` 按本 batch 可见字节估算，避免共享 backing 的随机切片重复乘整块 capacity；这不是 input backing 的唯一 owner charge。small metadata 校验先预约、校验后退账；主 lease 预含结果 metadata 上界及编码/索引/排序结构；locator push 在 String/Vec 构造前增长预约；结算 `shrink_to` 只退 scratch，绝不事后增长。新增共享 slice 同 budget、零 batch 宽 metadata 紧预算拒绝/释放向量。原审须对这组根因复核；若第二轮仍不守相同预算不变量，按 Owner 两轮停止要求暂停，不自行叠补第三轮。

### 语义核点

- Python planner 继续先处理单侧、role、健康 early exit 与 schema/key 退化，再调用 Rust 行核。非控制类语义异常按现表降级；取消、截止、资源错误直接向 operation 传播。
- keyless multiset 对重复行保留次数；occurrence 0 用原 row digest，大于 0 用 `keyless-row-occurrence:v1\0`、digest ASCII、minimal ULEB128 后再做 row-domain SHA。A 的第三份固定 expected 为 `sha256:a30dfdfae0f29e7d4a7da411578d351fac59a100052dc8fd2135f6940f4ba2bb`。
- facts 摘要使用完整未裁剪 payload 与 facts 顺序；records content 使用 artifact 顺序及 detail 裁剪。Blank 私有 `entity_key_kind` 保留于 facts 源视图，不进 Parquet 物理 schema。facts_core 必须重放 table payload bytes，不能拼 table hash。
- unchanged ordered 只读当前侧、两侧摘要相同，不运行 LIS、不生成 records。空表与任意 batch 划分仍必须有确定性。ordered 主路径保留 GID/no 绝对位置、LIS 并列、blank gaps 与伪 GID 规则。
- `ordered.rs` 的旧 `gdms.scalar_type`/单 batch 原型是替换期冻结差分材料，不是新生产兼容层；E 随其旧专用消费者删除。新路径要求 S2b `gdds.canonical_type` 与 canonical mapping version；SET 为 Utf8 中按声明序的逗号分隔成员，再用 Shared Kernel Sequence framing，NULL 为 null scalar frame、空 SET 为零长度 sequence。canonical metadata 存在而畸形/类型冲突时直接失败，不回退旧字段。

## 验证与证据

检查点的唯一 06 测试者先在 scratch 副本执行 `cargo fmt --all` 并回传四个 Rust 文件的机械格式补丁；实施者在 main 应用后提交新固定 SHA，再由同一测试者在 06 clean 已提交独立 worktree 跑 fmt --check、focused clippy/core tests。首个失败停报，按同角色修复并原审复审。Rust 变更后 backend focused 必须 `--reinstall-package gateway-compute-python` 并从当前 Git `HEAD:vnext/rust` tree id 校验 native build input。所有测试、编译、lint、真实数据和容器仅在专用节点；本地仅静态阅读与编辑。

`9b34be7356a92228ef07ee0c4f01bf215e2bf653` 的 06 Rust 检查点：fmt --check exit 0；clippy exit 101（unused ListArray、不可变 batch iterator），按首失败规则未运行测试。原日志 `/home/dev/gdds-test-tmp/p6-s3-b-test-9b34be7356a9/logs/rust-focused.log` SHA256 `c0eecef9412e267f98cef536d91025af4c5209db77ace24f790de27349fc8d6f`；两点已在后续源码修复，原失败保留。格式后 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 测试准备中测试者的额外只读命令两次 exit 127，未启动 fmt/clippy/test；依 DC68 已停并由协调者交 Owner，不能将 b917 记为运行过。

临时差分草稿（尚未编译/运行）为 `comparison/probe.rs` 小策略 JSON/locator frame 视图、`gateway-compute-python/src/s3_compare_probe.rs` Arrow C Stream 薄桥、`backend/tests/test_comparison_s3_b_differential.py` 和 `backend/benchmarks/s3_b_real_table_diff.py`。固定 4d5 Python `standard.py`、`ordered.py`、`row_encoding.py` 源 SHA，路由变更时失败而不是两边误用新核；比较 keyed/keyless/ordered 的 counts、record kind/identity、locator 解引用完整 frame、ordered/occupancy digest、blank 私有键和新增列隐藏内容。逐表工具先对 datasets.json 与 P5 S4 既定身份核八包 size/SHA，然后按 tier 只做表级差分；不启动完整旅程，标准 early exit/缺侧 metadata 计为上层任务而不伪称 Rust 已扫描。E 删除四处临时材料及 `comparison/mod.rs` 的 probe 导出、`gateway-compute-python/src/lib.rs` 注册。该薄桥不增加 member dependency、不更新 Cargo.lock；probe JSON 输出仅为替换期测试视图，不作 production bridge 或 M 端到端计费证据。

原审在 ac21 第二轮静态复核认为已针对性关闭预算根因，但未有任何运行证明，不能据此 GO。另指出 `CanonicalPseudoGid` 的非法非空非零 gid 应报 `CANONICAL_GID_INVALID`，而非 source 诊断；后续语义增量按冻结 Python `_parse_stable` 修正并加同诊断向量。06 测试仍因前述 DC68 操作错误停，待 Owner 决定后才可继续；新的测试者不得自行代跑。

待 06 恢复后的最小 focused 顺序：clean 固定候选、外置 target、offline/jobs4；先 scratch `cargo fmt --all` 回传纯格式补丁并重固定 SHA；然后 `cargo fmt --all --check`、`cargo clippy --workspace --locked --offline --all-targets -- -D warnings`、`cargo test -p gateway-compute-core --locked --offline comparison::standard::tests`（当前14个）、`cargo test -p gateway-compute-core --locked --offline comparison::ordered::tests`，首失败即停。Rust 更动后使用当前提交 `git rev-parse HEAD:vnext/rust` 作为 `GATEWAY_RUST_BUILD_INPUT`，在 backend 受控离线 uv 同步时 `--reinstall-package gateway-compute-python`，通过 build-input check 后仅跑 `tests/test_comparison_s3_b_differential.py`（5个参数化用例）。八包实际 SHA 全核后，单独运行 `python -m benchmarks.s3_b_real_table_diff --root <06实际输入根>`；只做逐表差分。任何 Rust/API/差分失败均保留原日志并停报，不改旧 Python expected 或 golden 消差。

最终 B 验证还须有 C1/C2/C3/C4/O1 独立固定向量、随机 batch/允许 N 的确定性与预算/取消/截止、standard/keyless/ordered 替换期 Python 差分，以及 t1–t4 v1/v2 按表差分。expected 源为 A、owning Contract、已冻结 Python/golden，不从新 Rust 输出生成。真实数据差分前逐 tar 校验 SHA256；本节不跑完整旅程、04 权威 runner、Compose 或正式性能测量。完成后补本页固定候选、06 hostname/起止 HEAD/time/exit/SHA、源码传输和缓存来源、六锁及独审核收。
