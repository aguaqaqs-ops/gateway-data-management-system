# Phase 6 S3 C 实施交接

状态：C 代码候选待 06 focused 验证与同角色独审；本文不自行宣称 C GO。固定设计为 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，B 独审已 GO。C 的实际代码候选、06 日志、镜像身份和复审结论在验证后补入。

## C 实现与 D 接口

正式新入口在 `gateway-compute-python/src/comparison_records.rs`，Python 薄门面在 `backend/.../comparison/native.py`。`_begin_comparison_operation_native` 从现有 operation 的 `OperationMemoryBudget` 取得真实 native portion token，复用已有 N1 pool、取消 watch、单调截止。`_compare_records_native` 接有 schema 的 Arrow C Stream、有效小 policy JSON、唯一 input backing charge 和其对应的 `max_input_bytes`；先在 GIL 释放下逐批读并核单侧 4096 batch/1000 万行与两侧累计可见 Arrow bytes，然后调用 B 的 `StandardComputation` / `OrderedKernelResult`。零 batch 的空表仍带 schema，不与缺侧混同；单侧新增/删除表的 metadata 路由仍归 D。

`build_standard_records`、`build_ordered_records`、`build_blank_records` 只从 B 保留的 Arrow batches 与 facts locator 逐行取值。FULL 行确定产物排序，按请求 detail 裁剪后做重复检查，三族 exact Arrow schema、nullable Scalar/list/struct、metadata 与 1024 行分组由 builder 生成。每条 `serde_json::Value` 只作单行 scratch，不把完整 Python records/dict/JSON 传进 Rust；blank 的私有 `entity_key_kind` 只供 facts replay，不进 BLANK Parquet。builder 同一趟逐行 JCS 计算各族 content digest。输出 `handle.family_summary(family)` 与 `handle.record_batches(family)`；后者经安全 Arrow C Stream 返回实际 PyArrow RecordBatchReader。

`handle.table_fact_digest` 与 `_facts_core_digest_native` 从 B 的 facts-order locator 重放完整 table payload。core 按 JCS key 顺序先写 summary 再逐个写完整 table，不能拼 table hash。事实 frame 是 canonical cell frame hex，records Scalar 是结构化 Arrow 字段，风险必要列由 D 决定，三者不能互换。Python 传入的 `_table_digest_payload` skeleton 必须保留表 metadata 而把三族 `records` 设为空数组；B 的 `facts_metadata` 仅用于小 metadata，不能替代完整 facts。`comparison_digest` 仍为 D 的小 envelope 逻辑。

`publish_records_family_arrow(table_name, family, handle, store, ...)` 从同一个已 seal 的 handle 取得 count/content digest 与 Arrow batches，按旧 writer 参数 `zstd`、`use_dictionary=False`、1024 行 row group 写 Parquet；只回读小 manifest/ref，不整份 locate/decode/JCS 回读新写的 records。Parquet raw SHA 仍由实际文件 bytes 得出，和逻辑 JCS/content digest 分层。失败、取消、put/flush/close 和原子发布继续按现有 artifact store/closure 外层边界处理。当前生产 `publish_records_closure(tuple)` 仍是旧路线，D 接线时只把 Preview/History/risk 的正式调用改到上述新 handle；E 再删旧 tuple writer、临时 B probe 和两份 B 测试桥，无运行时开关或 fallback。

## 同一 M 与最后 owner

Python operation 先独占 reserve 一个明确 native portion，输入唯一 backing 的 charge 另由 caller 持有；两者与 writer/risk 的 Python reservation 都从同一个 M24 GiB 账本取得。Rust `KernelContext` 只在 native portion 内发 B lease、C sort/JCS/Arrow output lease。FULL sort 的单行 Value 在从 Arrow 读取前预留；JSON 长度用无分配计数器确定，再为编码/JCS 增长。排序 entry/index、detail 去重 hash 与 output builder 在增长前预约；builder 每完成 1024 行把暂额缩到实际 buffers 与 header 费用。facts metadata 按 raw、结构 token 累计预留，row JCS 有独立三份 scratch；FFI 入参字符串复制前也预约。

`OperationUse` 覆盖所有可分配 native 方法，GIL 释放期间仍计 active。所有 table/core 摘要完成后，`operation.seal()` 仅在 active=0 时可执行，阻止旧 phase 的 reserve/grow，并把 Python native token 缩到 `initial−KernelContext.remaining`；随后 writer/risk 可从同一 M 取得额度。已导出的 Arrow Buffer 用 `Bytes::from_owner`、`Buffer::from(Bytes)` 与递归安全 `ArrayData` 重绑，绑定 C output lease 和 input owner/charge；handle 或 reader 关闭后，最后一个 batch/table buffer 释放才退 token。每一族/表释放后可显式 `reconcile_retained()` 再单调缩 Python token。seal 后仅导出已生成 Arrow/小 summary；新的 table/core JCS 必须在新 native phase 预约。D 必须在 seal 前取出并在同一 operation 计费需长期保存的 Python 小 metadata，按事实摘要→seal→writer/risk→最后 consumer 的顺序释放 owner。

## 真实读侧

`open_records_closure`、诊断 `read_records_artifact` 与 `restore_records_closure` 的验证实际走 Python Parquet→逐 row-group Arrow→`_validate_records_batches_native`。在 ctx 内先按 records ref size 预约 raw 与小 footer，再按 Parquet metadata 的 1024 行组、禁止 dictionary 的写入格式及未压缩大小×16+offset/validity/JCS 额度，在解码前预约；无字典的 plain 值即使 UTF8 控制字节需最多六倍 JSON escape，两份编码/JCS 与 Value/Arrow/offset 仍在十六倍内。Rust validator 逐批核 exact schema/nullable/metadata/count/content，单行 Value/JCS 在构造前同十六倍检查上界，取消/截止在批和行边界检查。raw ref size/SHA 与 content digest 分开校。ctx 外的真实 open/restore 只需 raw+单组 Arrow/JCS 的 M24 上界；诊断 reader 还为已返回批次和下一组预留累计额度，显式 `close()`，不作生产下载时的新增全份解码。`bundle_tar` 使用同一 open 边界。生产读侧不经 B 临时 JSON probe。

新 writer 的 RAM spool 阈值不超过 `max_records_artifact_bytes`；同 operation 在写前预约 `2×max_artifact + 2×最大输出 batch.nbytes + 1 MiB`，分别覆盖 spool/raw 双份与单组 Parquet 页编码/压缩暂额，超额在写前拒绝。它仍按每 1024 行独立 `write_table`，不会合并成一份 Python rows/table；直写实际 raw golden 逐字节对照旧 writer。

## 验证与容器判定

独立 expected 固定自 A/owning Contract、4d5 旧 Python 来源及现有 Parquet goldens；不从新 Rust 输出回填。C focused 应核三族 exact schema/nullable/metadata、0/1/1023/1024/1025 与随机 batch、宽度和 offset、FULL 排序/重复、完整 table/core JCS、content 与 raw SHA 两层、真实 open/read/restore 内容/损坏/I/O/提前 close、GIL/取消/截止、同 M phase seal 与最后 exported batch/table 释放。新增 `test_comparison_s3_c_arrow.py` 包含 STANDARD/ORDERED/BLANK 新 builder 对旧 Python rows/content/raw、facts/core、1024 边界、独立大 metadata JCS、producer 禁 records locate spy、native 输入/输出预算拒绝退账、已取消/截止/GIL watch 进度及 raw 正确但 content/schema 错误、读 I/O 故障；core 私有单测核 FULL 排序与 detail 投影后重复。既有 records tests 保 null/binary/float/date/decimal 行断言。C 的 SQL→canonical Arrow 输入 helper 已置于 `tests/support/comparison_s3_c_inputs.py`，不依赖 E 要删除的 B probe/test bridge；当前动态 expected 仍取冻结 4d5 旧 Python 路线，E 删除旧实现前必须把这些向量的旧输出冻结成独立 fixture/golden并将 C tests 改用它们，不能把新 Rust 输出反填。

唯一 06 tester 在 clean 已提交 detached worktree 用离线缓存按 `AGENTS.md` 跑 Rust fmt/clippy/workspace tests、强制重装 Rust 扩展及 build-input 树校验、backend focused 和五包 ruff/mypy；若新测试工具不在默认 mypy 集合则单独明确运行。不得在开发主机跑测试、编译或 lint。C 修改真实 PyO3 read consumer、Rust 依赖锁及 backend/worker 镜像输入，已触发当前候选 HEAD 的 container-only 边界：需在 06 当前离线 dependency-base 上做小规模 Compose native smoke 并记录实际 image revision/source-tree；E 的 04 六包/正式最终容器门禁另办，不将 B 的延期判断机械沿用。`Cargo.lock` 的直接 `arrow-data 59.1.0` 依赖 checkpoint 为 `573d58248f`，须按 CT201 clean 构建 dependency-base、LAN 转运并记录完整输入摘要、config digest、全部 DiffID、归档 SHA 与时间，不能把开发机或旧镜像当当前候选证据。

06 的 `0194d145bf` core 早期检查点未得到编译结果：LAN bundle 准备按 DC68 纠正后再次 exit 128（尚未触及被测对象），tester 按规则停止并释放 marker；恢复决定由协调者办理。该检查点非 C 验收候选。下次测试只能在固定的新完整候选与获准恢复的传输步骤上进行，原失败日志及 SHA 由 tester/协调记录。
