# Phase 6 S3 C 实施交接

状态：C 产品候选 `854d3888a9de49a666f209145756befec1dd2532` 的 06 focused、五包静态和当前镜像小门禁已过，最终独审结论待独立 review 文档；本文不自行宣称 C GO。固定设计为 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，B 独审已 GO。

## C 实现与 D 接口

正式新入口在 `gateway-compute-python/src/comparison_records.rs`，Python 薄门面在 `backend/.../comparison/native.py`。`_begin_comparison_operation_native` 从现有 operation 的 `OperationMemoryBudget` 取得真实 native portion token，复用已有 N1 pool、取消 watch、单调截止。`_compare_records_native` 接有 schema 的 Arrow C Stream、有效小 policy JSON、唯一 input backing charge 和其对应的 `max_input_bytes`；先在 GIL 释放下逐批读并核单侧 4096 batch/1000 万行与两侧累计可见 Arrow bytes，然后调用 B 的 `StandardComputation` / `OrderedKernelResult`。零 batch 的空表仍带 schema，不与缺侧混同；单侧新增/删除表的 metadata 路由仍归 D。

`build_standard_records`、`build_ordered_records`、`build_blank_records` 只从 B 保留的 Arrow batches 与 facts locator 逐行取值。FULL 行确定产物排序，按请求 detail 裁剪后做重复检查，三族 exact Arrow schema、nullable Scalar/list/struct、metadata 与 1024 行分组由 builder 生成。所有 List child 名为冻结 Python `pa.list_` 的 `item`，element nullable 不变。每条 `serde_json::Value` 只作单行 scratch，不把完整 Python records/dict/JSON 传进 Rust；blank 的私有 `entity_key_kind` 只供 facts replay，不进 BLANK Parquet。builder 同一趟逐行 JCS 计算各族 content digest。Utf8/Binary 值累计字节 offset 与 List 累计 child offset 均在 Arrow append 前按 `i32::MAX` checked 拒绝，递归覆盖嵌套字段；每个 1024 行 batch 独立重置 offset，不设整表 2 GiB 上限。输出 `handle.family_summary(family)` 与 `handle.record_batches(family)`；后者经安全 Arrow C Stream 返回实际 PyArrow RecordBatchReader。

`handle.table_fact_digest` 与 `_facts_core_digest_native` 从 B 的 facts-order locator 重放完整 table payload。core 按 JCS key 顺序先写 summary 再逐个写完整 table，不能拼 table hash。事实 frame 是 canonical cell frame hex，records Scalar 是结构化 Arrow 字段，风险必要列由 D 决定，三者不能互换。Python 传入的 `_table_digest_payload` skeleton 必须保留表 metadata 而把三族 `records` 设为空数组；B 的 `facts_metadata` 仅用于小 metadata，不能替代完整 facts。`comparison_digest` 仍为 D 的小 envelope 逻辑。

`publish_records_family_arrow(table_name, family, handle, store, ...)` 从同一个已 seal 的 handle 取得 count/content digest 与 Arrow batches，按旧 writer 参数 `zstd`、`use_dictionary=False`、1024 行 row group 写 Parquet；只回读小 manifest/ref，不整份 locate/decode/JCS 回读新写的 records。Parquet raw SHA 仍由实际文件 bytes 得出，和逻辑 JCS/content digest 分层。失败、取消、put/flush/close 和原子发布继续按现有 artifact store/closure 外层边界处理。当前生产 `publish_records_closure(tuple)` 仍是旧路线，D 接线时只把 Preview/History/risk 的正式调用改到上述新 handle；E 再删旧 tuple writer、临时 B probe 和两份 B 测试桥，无运行时开关或 fallback。

## 同一 M 与最后 owner

Python operation 先独占 reserve 一个明确 native portion，输入唯一 backing 的 charge 另由 caller 持有；两者与 writer/risk 的 Python reservation 都从同一个 M24 GiB 账本取得。Rust `KernelContext` 只在 native portion 内发 B lease、C sort/JCS/Arrow output lease。FULL sort 的单行 Value 在从 Arrow 读取前预留；JSON 长度用无分配计数器确定，再为编码/JCS 增长。排序 entry/index、detail 去重 hash 与 output builder 在增长前预约；builder 每完成 1024 行把暂额缩到实际 buffers 与 header 费用。facts metadata 按 raw、结构 token 累计预留，row JCS 有独立三份 scratch；FFI 入参字符串复制前也预约。

`OperationUse` 覆盖所有可分配 native 方法，GIL 释放期间仍计 active。所有 table/core 摘要完成后，`operation.seal()` 仅在 active=0 时可执行，阻止旧 phase 的 reserve/grow，并把 Python native token 缩到 `initial−KernelContext.remaining`；随后 writer/risk 可从同一 M 取得额度。已导出的 Arrow Buffer 用 `Bytes::from_owner`、`Buffer::from(Bytes)` 与递归安全 `ArrayData` 重绑，绑定 C output lease 和 input owner/charge；handle 或 reader 关闭后，最后一个 batch/table buffer 释放才退 token。物理 retained 在包装前以递归 `ArrayData.get_array_memory_size()` 计原 Buffer capacity、null/children/header；不能用逻辑 slice 长度或包装后 external Buffer 的 capacity=0。最宽 STANDARD 固定 48 个 builder 节点，每组初始 1024-slot/1024-byte 容量预留 512 KiB，组边界同时保已完成 physical retained 与下一组 workspace；每组和最终均核 physical≤output policy/已预充 lease，结束 drop builder 后才缩到真正 retained。每一族/表释放后可显式 `reconcile_retained()` 再单调缩 Python token。seal 后仅导出已生成 Arrow/小 summary；新的 table/core JCS 必须在新 native phase 预约。D 必须在 seal 前取出并在同一 operation 计费需长期保存的 Python 小 metadata，按事实摘要→seal→writer/risk→最后 consumer 的顺序释放 owner。

## 真实读侧

`open_records_closure`、诊断 `read_records_artifact` 与 `restore_records_closure` 的验证实际走 Python Parquet→逐 row-group Arrow→`_validate_records_batches_native`。在 ctx 内先按 records ref size 预约 raw 与小 footer，再按 Parquet metadata 的 1024 行组、禁止 dictionary 的写入格式及每个叶列的 `num_values`，在解码前预约。单组上界为 `16×total_byte_size + 512×Σleaf.num_values + 2048×num_rows + 1 MiB`；`num_values` 包括 nullable List 元素的 definition/repetition slots，不能只按压缩字节或顶层行数估。固定 schema 叶路径最多四层 List/Struct/Scalar，逐叶 512 B 覆盖 Arrow child/offset/validity 和 serde/JCS 节点；无字典 plain 可变值的 JSON escape、同时编码和 Arrow/JCS 两份暂额由字节 16 倍及总预约 2 倍覆盖。Rust validator 逐批核 exact schema/nullable/metadata/count/content，单行 Value/JCS 在构造前同十六倍检查上界，取消/截止在批和行边界检查。raw ref size/SHA 与 content digest 分开校。ctx 外的真实 open/restore 只需 raw+单组 Arrow/JCS 的 M24 上界；诊断 reader 还为已返回批次和下一组预留累计额度，显式 `close()`，不作生产下载时的新增全份解码。`bundle_tar` 使用同一 open 边界。生产读侧不经 B 临时 JSON probe。C 移除无生产 caller 的旧 Rust raw-copy `read_records_parquet_v1`；它的 STANDARD/ORDERED/BLANK 三份固定 Parquet、各自独立 family/version/count/content 预期及空 raw 拒绝已迁到实际 Python Parquet→PyO3 validator 测试，golden bytes 与 digest 未改。其已无代码用途的 `parquet`/`base64` direct Cargo 声明暂留当前锁定依赖输入，E 统一清理并按锁变化重建 dependency-base。

06 固定 `ab610e82` 的只读诊断（`diagnostic-run.log` SHA256 `71961e18b44a1ea5bdf798456c8ba24f393f274301ecbf2002cddc955a9fd2f9`）证明：三份冻结 Parquet 经 PyArrow 读出时每个 List child 均为物理名 `element`，公共 `_schema_for` 的对应名为 `item`；PyArrow `Schema.equals(check_metadata=False)` 对该嵌套名差异返回真，但 Rust exact validator 正确拒绝直接送入的批。三族用公共 schema 写入与旧 Python writer 均逐字还原原 raw golden；使用读回 schema 写入仅改变 footer 内 `ARROW:schema`。实际读侧因此先递归严格核每个 Field 名、类型、nullable、metadata 及唯一允许的 List child 物理名 `element`，每批用 `RecordBatch.from_arrays(batch.columns, schema=canonical)` 安全重绑 Arrow header 后再交 Rust；无 Python 整行转换，解码 buffer 不复制。诊断证明该重绑路径三族 content digest 与冻结 expected 一致。诊断 reader 返回公共 `item` schema，关闭 stream 后已返回批仍可读；新增 header 由原单组准入的 1 MiB 底额及诊断累计保留费覆盖。不建设第二份生产 schema 或宽松字段别名。

新 writer 的 RAM spool 阈值不超过 `max_records_artifact_bytes`；同 operation 在写前预约 `2×max_artifact + 2×最大输出 batch.nbytes + 1 MiB`，分别覆盖 spool/raw 双份与单组 Parquet 页编码/压缩暂额，超额在写前拒绝。它仍按每 1024 行独立 `write_table`，不会合并成一份 Python rows/table；直写实际 raw golden 逐字节对照旧 writer。

## 验证与容器判定

独立 expected 固定自 A/owning Contract、4d5 旧 Python 来源及现有 Parquet goldens；不从新 Rust 输出回填。C focused 应核三族 exact schema/nullable/metadata、0/1/1023/1024/1025 与随机 batch、宽度和 offset、FULL 排序/重复、完整 table/core JCS、content 与 raw SHA 两层、真实 open/read/restore 内容/损坏/I/O/提前 close、GIL/取消/截止、同 M phase seal 与最后 exported batch/table 释放。新增 `test_comparison_s3_c_arrow.py` 包含 STANDARD/ORDERED/BLANK 新 builder 对旧 Python rows/content/raw、facts/core、1024 边界、独立大 metadata JCS、producer 禁 records locate spy、native 输入/输出预算拒绝退账、已取消/截止/GIL watch 进度及 raw 正确但 content/schema 错误、读 I/O 故障；core 私有单测核 FULL 排序与 detail 投影后重复。既有 records tests 保 null/binary/float/date/decimal 行断言。C 的 SQL→canonical Arrow 输入 helper 已置于 `tests/support/comparison_s3_c_inputs.py`，不依赖 E 要删除的 B probe/test bridge；当前动态 expected 仍取冻结 4d5 旧 Python 路线，E 删除旧实现前必须把这些向量的旧输出冻结成独立 fixture/golden并将 C tests 改用它们，不能把新 Rust 输出反填。

serial GIL 向量用惰性 Arrow stream 首批实际拉取事件唤醒后台 Python 线程，由该线程推进并触发取消；同时断 stream 的首批确已进入 native 读取，避免仅在比较入口前第二次 cancel poll 的伪证。

唯一 06 tester 在 clean 已提交 detached worktree 用离线缓存按 `AGENTS.md` 跑 Rust fmt/clippy/workspace tests、强制重装 Rust 扩展及 build-input 树校验、backend focused 和五包 ruff/mypy；若新测试工具不在默认 mypy 集合则单独明确运行。不得在开发主机跑测试、编译或 lint。C 修改真实 PyO3 read consumer、Rust 依赖锁及 backend/worker 镜像输入，已触发当前候选 HEAD 的 container-only 边界：需在 06 当前离线 dependency-base 上做小规模 Compose native smoke 并记录实际 image revision/source-tree；E 的 04 六包/正式最终容器门禁另办，不将 B 的延期判断机械沿用。`Cargo.lock` 的直接 `arrow-data 59.1.0` 依赖 checkpoint 为 `573d58248f`，须按 CT201 clean 构建 dependency-base、LAN 转运并记录完整输入摘要、config digest、全部 DiffID、归档 SHA 与时间，不能把开发机或旧镜像当当前候选证据。

06 的 `0194d145bf` core 早期检查点未得到编译结果：LAN bundle 准备按 DC68 纠正后再次 exit 128（尚未触及被测对象），tester 按规则停止并释放 marker。Owner 后续按独审通过的恢复稿放行，tester 对 clean、已提交的新候选重新执行；该 0194 错误仍保留原日志与 SHA，不作为 C 产品测试或验收证据。

### 已核 06 focused 与独立 expected

产品候选 V 为 `854d3888a9de49a666f209145756befec1dd2532`，`vnext/rust` tree 为 `0866ac1223177d66cf13dc8b7389875c7bcb39b7`。同一 Rust tree 在 06 的固定 `ab610e82672d83b04bfabe88f2a8a34e0ea5cbbd` clean worktree 上实际执行 `cargo fmt --all --check`、workspace locked/offline clippy、workspace locked/offline test，三步 exit 0；原日志 `06:/home/dev/gdds-test-tmp/p6-s3-c-ab610e82/logs/run-focused.log` SHA256 `1ba0d0f7da4a8d8e8127b6fa50d39fa7272daccd18e705fbe52524c0ba2f9f07`，`02:10:53–02:11:27Z`。该次整稿随后 backend focused 失败，`FINAL_EXIT=1`；只作为同树 Rust focused 原件，不能称权威 runner carried 或 ab 整稿通过。

06 的 V clean detached worktree 在 `02:48:19–02:49:07Z` 强制重装 `gateway-compute-python` 并核扩展 `__build_input__=0866ac...`，backend C focused **67 passed**（三冻结读/三 raw、实际 open/read/restore、typed SQL NULL/binary/float/date/decimal、owner 释放及取消/GIL 等），architecture import shapes **50 passed**，`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 五包的 ruff/mypy 均 exit 0。起止 HEAD 精确 V、worktree clean、六锁无漂移、`FINAL_EXIT=0`；原日志 `06:/home/dev/gdds-test-tmp/p6-s3-c-854d3888/logs/run-focused.log` SHA256 `12f07b3f5aa294cabb66d02e95c7de64c05e0882049369e2906aa994771e45d4`。这是阶段 focused，不是 04 权威全量 runner。

三份 pre-C 冻结 Python Parquet b64 的独立期待不取新 Rust 输出；旧 Rust direct reader 的专用测试已由实际 PyArrow→PyO3 validator 对同一 raw、family/version/FULL/count/content 断言接替，空 raw 拒绝另保留。新 builder 三族 raw 逐字对旧 Python writer，亦对照以下固定来源；逻辑 JCS/content digest 与 raw SHA 分开判定。

| Family | Version / count | 冻结 content digest | 冻结 raw SHA256 |
| --- | --- | --- | --- |
| STANDARD | `standard-records/v1` / 1 | `sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4` | `6f36fec125a0fe48fd021b4cdba4486b280a4e3e596fe44a8f57ebb0ac7fa309` |
| ORDERED | `ordered-records/v1` / 1 | `sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b` | `15b51249f09fd147c77a9cac2ee13cb2bff819a0767aedd0b90564bed07ce331` |
| BLANK | `blank-records/v1` / 2 | `sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a` | `39bfb0fb8a026e71c5328c237e89c89baeaa128a88109186a7e052328afc1279` |

失败闭合链保留原件，不靠改 golden 或放宽断言：`0194` source bundle DC68 两次 setup error 后按 Owner 已审恢复稿重做；`9f` fmt、`bca/bd/bf` clippy、`20f` PyO3 编译、`4a` 被替代旧 direct reader 的物理 `element` 测试，分别在后续固定树上修正，最终同树 ab Rust 三步全过。ab 的 backend 首败包含遗漏 `typing.cast`、`DigestRef.parse` 虚构 API 与三 raw footer 差异；`46b` 只修 cast 未运行，随后 `1f` 经真实三 b64 读桥/公共 schema 写入证明 raw 逐字。`1f` 8 个首败依实际边界修：diagnostic standalone 与 autouse operation 区分，已导出 batch 最后 owner 退账，BLANK facts 序与旧 artifact sort 序区分，ref raw identity 在 closure/manifest/records 解析前拒绝并报具体部位；`7c` 06 focused 67/67 与 architecture 50/50 已过，但 backend mypy 26 条类型错误使整稿 `FINAL_EXIT=1`（原日志 SHA256 `11e6c88430f12134fa36f310996476b760e7f7f2fe0da7ae52ef14a6deb43ef9`），由 V 局部精确类型修闭合，V 五包静态全过。早期失败完整来源索引为开发节点 `/home/dev/gdds-test-tmp/p6-s3-c-evidence-index.md`，它只索引原件，不签 GO。

CT201 的 clean 依赖 checkpoint `573d58248f0dc90e27f1be79ac9f2802211ed738` 在 `heavy-dev-01` 于 `01:22:02–01:24:09Z` 按完整输入 SHA256 `ca0ba0a24a5e96a435e14a6da80b26cc390d315722f0432be3affe9de3339085` 构建/保存 `gateway-backend-deps:lock-ca0ba0a24a5e`；归档 SHA256 `fb30d4666cf5466c66ca464c9db7103457cec92f4eb9003980f6c1a2e3dfc136`，config digest `sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c`。06 经获准 LAN 于 `01:36:35–01:36:55Z` 传输、`01:37:14–01:37:29Z` load，核 config 与以下全部 19 个 RootFS DiffID 相同，未走公网/代理；构建原日志 SHA256 `7e1b02db9b823bd4be8c55a4888c2e40b99e83a9320a2919e17c7f18762094d3`，预填原日志 SHA256 `c84aaade82bb2d52618d579e9afa634586c7dae2e1924b4b3c0160ffff083d11`。当前 V 的五项 dependency-base 输入与该 checkpoint 相同，最终 06 Compose 仍须按实际 `--print-input` 和本机镜像身份复核。

```text
sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a
sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104
sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15
sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1
sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a
sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25
sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588
sha256:234dfe258b3d948dab2e1a1c001437fd46b4e71da8f7c1314981acb098d2d547
sha256:b92b3277af9693a1e9447d275f2028586485b1add134b67565904e6feb30ea2b
sha256:09700be33d693283b898b565c45fdd1b1565689aff5af92a430c1fd166db69bf
sha256:4e4ce5587cdaf796f63c5af9693ce2f339a7dc0163e0bd8c529ac363ed450afc
sha256:7beae3f6038867aa129aca2d5bb3ff21de1b1505ca2f5d8cdaf3b407ce064c9e
sha256:9e9bd7e3f80137b97b7df080e637dea5f65ec76b2c30bf5c85a5ff1f1c8c9fe6
sha256:ed736377f94046644118088d441142544466807cd758d68b0a5b6a2d593ed57a
sha256:1ddd6ddb7206aadbc02d443873544a553fa6ea41bbe46311c282fc1621fd0f77
sha256:527bb8413693212ca83d05ea064f54b71c9b64577f3324fd5bbe2adc56548d57
sha256:93bccfc22a8b43705d1a1250974b5845871ae65d1911d68cd0d9d8de46a8a3e3
sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
sha256:3b57bc4f973ed872d72fcea5366bac94c997c415b29d06c28f8e9a631b7a8429
```

### 当前镜像小门禁与 D/E 待办

唯一 06 tester 在固定 V clean worktree、当前本机预置 dependency-base 上以 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-ca0ba0a24a5e`、`GATEWAY_DOCKER_BUILD_NETWORK=none` 保留 Compose build，实际重建 `gateway-s3-c-854d3888-backend:latest` 与 `gateway-s3-c-854d3888-worker:latest`；没有设置 prebuilt 模式。实际 backend 镜像内用 N1 pool 写一份固定 STANDARD Arrow batch 为 Parquet，再由 `_validate_parquet_bytes` 经 PyArrow row group→真实 PyO3 Rust validator 核 family/version/FULL/count/content，输出 `S3_C_NATIVE_PARQUET_SMOKE_OK sha256:fe356998e284fbbe24af3eb5ebd396fbc6d7f7cddd19a753c87c16187efceeac`。06 日志起止 `2026-11-08T02:52:14–02:54:13Z`、HEAD 精确 V、`vnext` tree `f2b1ca467434730482dbf0a85ba163b59eb2fb59`、Rust tree `0866ac...`，六锁无漂移、worktree clean、`SMOKE_EXIT=0`、`FINAL_EXIT=0`、本人 marker 已释放。原件在开发节点 `/home/dev/gdds-test-tmp/p6-s3-c-compose-854d3888/compose-native.log`，SHA256 `97df5395210b420430519268a84c5daf0b74ab902d1f361bb3ed0ba6cbac9f3d`；当前镜像 archive SHA256 `1a5a447da032b35380ae332e74b591f31b5496ba09c1fced53b46f3f5c0a5d58`，06 `image-identities.json` SHA256 `045ac22b1b2084c262f6cb78b6ea2fde761c370e9576e3aa26c4601b5b064696`。该结果只证明本节当前镜像的小型 native read 边界，不是 04 权威全量 runner 或完整 Compose 服务旅程。

| 06 当前镜像 | config digest | RootFS DiffID |
| --- | --- | --- |
| `gateway-s3-c-854d3888-backend:latest` | `sha256:15d83b25314b89a9625f39835970eae8ee24d22ada58ccc947a7d4deaab026ef` | 下列相同 13 层 |
| `gateway-s3-c-854d3888-worker:latest` | `sha256:1ef7719fcbc443abffe52993709d9daefdc42afc8827b5b87e87a226798765a3` | 下列相同 13 层 |

```text
sha256:66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe
sha256:97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067
sha256:3fda3219c8f4a902e577efcdb924b514318c606d47db4a53640511b27925da18
sha256:594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5
sha256:e5d5d6d9e0a5f93b01200d90860522a50d4c4d6d34710c117212d0071e43c150
sha256:225cd91c26ef9dc0468d190ae99d4b37f57f4c3e6f50259f8c0f1830f8e3d7f8
sha256:754f547225d914d029db66988a9ab28ec04c54c388c265e95a168cf0b8e03092
sha256:a73b7714f07f506ab15477b3b06817c04650473022989479e71a06482663d0c3
sha256:143d43bcc5ef0975b0eb506059f6b597799ed8a904f68ab8583ba41bfbd1c5ee
sha256:a9880cd756421768ccad0ef9c0c0570c671766c28776cb358f0cf1c5512eca1b
sha256:f23cf9dcc532b8683deec160ceb90b6ec6e8af58b016008f5071f04dd98022a2
sha256:7f0d7e5a910dd095513158a1b8bc57ac7a3791a35d5931c5ecfd7a5b530c6e7c
sha256:64164ec99acd1b7952cfea3b787c6e7d9c18aba73f0f90d1f3da58affd79ba44
```

D 的唯一生产接线仍须把 Preview/History/risk 从旧 tuple 发布路线改到 C 的 native handle/Arrow 与本节 read validator，并在同一 operation M 账本上按 facts/core→seal→writer/risk 顺序用新 API；C 本节没有开启生产开关或隐式 fallback。D/E 特别要处理 BROWSE_ONLY/SNAPSHOT_ONLY 的 `COLUMNS_ADDED` 旧 `_read_rows+Counter` 热点，使用 B 的 keyless `emit=false` counts→bool 接口并保旧 role 测试。E 负责删除 B JSON locator probe、两份临时 Python 工具与剩余旧 tuple 路线，在最终候选按 04 六包权威 runner、完整容器门禁、DC33 真实数据范围及 W3/W4 测量/测量来源完成阶段退出；本节 focused 与小 smoke 不替代这些证据。

### 06 当前镜像最小 native smoke

以下在 06 已取得节点占用、clean 已提交候选 worktree 的仓库根目录运行；由 tester 把完整 stdout/stderr、起止 UTC/HEAD、exit code 与 SHA256 写到 worktree 外。dependency-base 先按 CT201→LAN 流程在 06 `docker load`，并核 config digest 与全部 RootFS DiffID。脚本只在 worktree 外建立无凭据 Compose 配置，构建当前 HEAD 的 backend/worker，再在实际 backend 镜像内运行真实 records 读侧 `_validate_parquet_bytes`（Python Parquet→Arrow→PyO3 Rust validator）。`open_records_closure` / `restore_records_closure` 的外层 store/ref 路由另由上面的 focused 测试覆盖；这里不声称完整 Compose 旅程。

```bash
set -euo pipefail
mkdir -p /home/dev/gdds-test-tmp
smoke_dir="$(mktemp -d /home/dev/gdds-test-tmp/p6-s3-c-compose.XXXXXX)"
trap 'rm -rf -- "$smoke_dir"' EXIT
printf 's3-c-smoke\n' > "$smoke_dir/secret"
printf '{"mappings":[]}\n' > "$smoke_dir/mapping.json"
export GATEWAY_P2R2_BEARER_TOKEN_FILE="$smoke_dir/secret"
export GATEWAY_BACKEND_SESSION_FILE="$smoke_dir/secret"
export GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE="$smoke_dir/secret"
export GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE="$smoke_dir/mapping.json"
base_tag="$(./vnext/scripts/build-backend-dependency-base.sh --print-input \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["image"])')"
export GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE="$base_tag"
export GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1
export GATEWAY_DOCKER_BUILD_NETWORK=none
unset GATEWAY_COMPOSE_GATE_PREBUILT
smoke_project="gateway-s3-c-$(git rev-parse --short=8 HEAD)"
docker compose -f vnext/deploy/compose.yaml -p "$smoke_project" build backend worker
docker run --rm -i --entrypoint python "${smoke_project}-backend" - <<'PY'
from contextlib import closing

import pyarrow as pa
import pyarrow.parquet as pq
from gateway_compute._native import _init_kernel_native
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationPolicy,
    _schema_for,
    _validate_parquet_bytes,
)
from gateway_backend.capabilities.comparison.contracts import (
    RecordsArtifactFamily,
    RecordsArtifactManifest,
    RecordsDetailPolicy,
)
from gateway_backend.capabilities.comparison.native import validate_records_batches

_init_kernel_native(1)
family = RecordsArtifactFamily.STANDARD
detail = RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES
schema = _schema_for(family, detail_policy=detail)
batch = pa.RecordBatch.from_pylist([{
    "table_name": "t",
    "record_kind": "ROW_MODIFIED",
    "row_identity": bytes(32),
    "changed_columns": [],
    "before_values": [],
    "current_values": [],
    "field_changes": [],
    "diagnostics": [],
}], schema=schema)
with closing(pa.RecordBatchReader.from_batches(schema, [batch])) as reader:
    found_family, version, found_detail, count, digest_text = validate_records_batches(
        reader, max_records=2, max_batch_bytes=1024 * 1024
    )
assert (found_family, version, found_detail, count) == (
    "STANDARD", "standard-records/v1", "FULL_BEFORE_AFTER_VALUES", 1
)
digest = DigestRef(digest_text)
sink = pa.BufferOutputStream()
pq.write_table(
    pa.Table.from_batches([batch], schema=schema), sink,
    compression="zstd", use_dictionary=False, row_group_size=1,
)
raw = sink.getvalue().to_pybytes()
manifest = RecordsArtifactManifest(
    table_name="t", family=family, record_format="PARQUET",
    schema_version=version, row_diff_detail_policy=detail,
    record_count=1, content_digest=digest,
)
assert _validate_parquet_bytes(raw, manifest, RecordsPublicationPolicy()) == (1, digest)
print("S3_C_NATIVE_PARQUET_SMOKE_OK", digest_text)
PY
```
