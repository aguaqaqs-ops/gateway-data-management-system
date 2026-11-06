# S2b E 实施 handoff（进行中）

状态：IMPLEMENTING；2026-11-06。当前产品删除候选 `172807821ad9e1afcd1ae8979036f1b893146d0b`，尚无 E GO、04 权威 runner、最终容器或 t1–t4 结果。D 的 06 focused 及局部容量仍仅是 D 已确认来源；性能未知项不记 PASS。

## 实际消费者与删除

- 已删除六旧 SQL parser 模块与六条精确 temporary unreachable，不加 import/cycle 豁免；native parser 是唯一生产 SQL 路径。
- 删除旧 SQL row materialize fallback、`storage_projection/project.py`、旧 `_ordered.py`、旧 import replay 再投影、RepositoryRef `_read_and_materialize_table`，以及 compose 的旧 row catalog 分派。`_catalog.py` 仅保现 native owner 共用的 `CatalogError` 元数据。
- 删除测试 `_ReferenceCommittedTables` 及旧差分开关/property-only suite；publication/mutation/metadata 的合法小 fixture 通过真实 Rust projection、真实 C committed-table port 和现 Submit typed image consumer 构造，不能称独立 oracle。旧 private hash sink/cell codec 探针随实现删除。
- 保留 Python orchestration/rules/XML/AST/composite、small metadata/digest、MutationPlanning row-image 与通用 row reader。`row_content_hash/raw_content_digest_of` 仍有 composite 业务结果和 raw Parquet 验证真实消费者，按 root 确认保留；内部 canonical IPC 与 raw/client Parquet 不混用。
- `real_dump_journey → real_dump_census.compare_composite_packages` 已接唯一新 parser/projection/canonical IPC；六项 counts 只证明跨层一致性，非独立算法 golden。保留的 census/keyless/forwardtable CLI 显式要求 N/M，不重生成输入或重跑普查。
- 按 DC79 的 main 消费者裁决，退役旧 `p3_capability_diagnostics`、`p6_v6_parser_diff`、`p6_s1b_synthetic_load`、`s5_dc32_capability_measurement`、`s5_v5b_segment_measurement`、`p6_s1a_mutation_replay_measurement` 与仅服务它们的测试。冻结 refs、输入、卷、JSON/report 与证据全不动；后续历史测量在获准冻结源码运行。
- `bootstrap.compute_kernel.initialize_compute_kernel(N)` 仅归并既有 native 与 PyArrow pools 初始化，worker/真实 CLI 显式调用。私有 FFI 白名单 owner 从 operation_worker 精确替换为 compute_kernel，无扩白名单或 import-time 初始化。

## 独立预期移交

既有 parser、SQL materialization、projection publication 与 Shared Kernel 的 fixed golden 保留，不从 Rust actual 改 expected。删除前用只读脚本采集旧 typed SET/F32、wide200×100、droppedJSON 的三个 raw/canonical digest：脚本 `/home/dev/gdds-test-tmp/s2b-e-freeze-reference.py` SHA256 `d97e8c9e36337bacdf506bf7e21f6e2d3912fea1f04589c0980e984cea3e0b60`，审核者已读。

实际来源是 **D `93678f8439` product editable sources + E `16e1089a86` 的 test helper（PYTHONPATH）**；当时 E copied venv 的 editable 指 D，二提交相关 product blobs 相同。此范围按 root 确认的用途用于旧 oracle 值移交，独立审核者已核相关日志与 source blobs，不声称 E 产品已经执行。06 19:04:58–19:05:00Z，lock-check/native treechecker 匹配，exit0；日志 `/home/dev/gdds-test-tmp/logs/s2b-e-freeze-reference-16e1089a86.log` SHA256 `4fe7de2ddf4cea018d86107bb46043436171d70f8889832993f58f0031e699af`。采集器不入永久 oracle。

- typed raw/canonical：`sha256:f57c8813f99f9226ae5c0970e6619e801cbb013d6d20d7dd32fcba87ee4f7f71`
- wide raw/canonical：`sha256:c947ad6fccb65c36c067d38a761ca1049e0122c5f926413ba9f7c09e5dcc603a`
- dropped canonical：`sha256:232a96c506247080963b4d39390ac5bf686238c8fb2edf0febcbdbeb0ae91905`

## 06 环境与验证记录

节点 `ct107-gw-dms-06` / hostname `gw-dms-06`，E WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-impl`、target `/home/dev/gdds-test-tmp/s2b-e-cargo-target`；D WT/target/镜像/证据不动。SSH BatchMode通过；前检无 busy/运行 Docker/Dolt/8000。原子 busy mkdir 实际 birth 为 **19:03:48.689387117Z**，初始 owner 文本粗写19:05Z有偏差，以后续日志中的 UTC stat 和实际前检工具记录为准，不倒推更早占用。legacy 链接齐，TMPDIR 磁盘目录、UV_OFFLINE/CARGO_NET_OFFLINE、jobs4，无测试 CT 公网或代理。

发现并修正一次环境准备缺陷：初始 copied D venv 的 editable 和 shebang 未重绑定，d5 的203 passed仅诊断，不能作 E 产品证据；efe5 focused 在 collection 阶段因新 compute_kernel 不可见而失败，未运行被测对象。按 DC68 保失败日志，整体移动 E 自有 copied venv 至 `/home/dev/gdds-test-tmp/s2b-e-venv-copied-invalid` 留证，从固定1728 clean WT离线新建 E venv并重新构建 path deps/native。无重试全 runner、无改 D 环境。

| 固定候选/步骤 | 结果 | 外置日志及 SHA256 |
| --- | --- | --- |
| d5dcc43b reference focused | 203 passed，ruff8 unused失败；因实际product仍D仅诊断 | `logs/s2b-e-reference-focused-d5dcc43b73.log` / `f81f3004ce75b29e62f671a4f44d43ec8ee4b9539d341c8f8f8f3b36b6c0797a` |
| 2e77436c static | ruff-diff1、mypy18 errors，随后修正 | `logs/s2b-e-static-2e77436c49.log` / `5049ef4e2b83619da5c60a2a391933bfbf69fbd50c914f84afab8b3f00d32e5c` |
| efe5f3bc focused准备 | ruff2 unused、mypy500 PASS、pytest collection2；editable缺陷 | `logs/s2b-e-cutover-focused-efe5f3bc54.log` / `0fe017348993738a60bde7d032f0c0c02816ae228666349b0aa6a84aa9f492a6` |
| 17280782 一次setup修正，19:18:51–19:19:06Z | exit0；重新建E venv及所有path deps，native tree137d499匹配 | `logs/s2b-e-setup-fixed-172807821a.log` / `5b5536037282a28748e37681bcdb8a2312f2352dc4fd7c4fce335b8dc619306b` |
| 17280782 环境binding，19:19:24–19:19:25Z | exit0；backend/shared_kernel/contracts/client actual `__file__`、direct_url与sys.path全部E | `logs/s2b-e-environment-binding-172807821a.log` / `ff6d81dd383cee649739f57a8b0e5764e501391cf8514a2364b6c19e7016f425` |

所有相对日志路径均在06 `/home/dev/gdds-test-tmp/` 下。新环境1728实际focused为357 passed/34 failed，原日志SHA `ace74286b299711a1fcecbf1726e77852d9846f19d93719c57f84c09f717d181`；60c5定向修正后373 passed/2 failed，日志SHA `f3345fb773e750d6d7d7fb8dc69c110adeeaab4e641571b65490688c264860d1`。两项剩余是pure rules拒绝被旧ProjectionRequest测试helper包裹，改直接断言真实resolver；原失败不回填。首次显式mypy file清单遇namespace重复模块名，后续以`-m benchmarks.<module>`统一限定名；不修改产品配置。

## 最终候选前仍需完成

实际consumer残余检查、受影响focused/Contract、五Python包Ruff/mypy和保留工具静态/小入口；最终候选的04权威runner和container、05 t1–t3、CT108 t4仍待完成。04三小包只可用原WT中 `3b037adf4c` 实际runner manifest逐包compare，Rust必跑，backend/RS闭包已变化必须运行。容器需最终候选本机离线build或严格同04同WT等价carried；06证据不作04来源。

真实旅程命令使用 `real_dump_journey.py --tier <t1|t2|t3|t4> --scope full --kernel-threads 1 --kernel-memory-budget-bytes 8589934592`，沿既有root输入核SHA，host composite scope与worker12/4/8 GiB分别验证。05/CT108窗口由root协调；CT108未确认，不擅自换节点/触原冻结材料。W4 lease_lost仍由原线OPEN；W1/W2最迟S6，W3从S3，未知不记PASS。

## 测试 owner 移交

| 退役旧入口/探针 | 保留的真实语义 owner |
| --- | --- |
| Python双parser/跨语言property、private类型映射 | 既有parser fixed golden/type/identifier/limit向量与native adapter |
| ProjectionRequest version/source-binding/provisional、Python reader内部错误/width探针 | 无真实caller的旧入口退役；实际schema/width/C Stream生命周期由native/A/C、冻结binding由Preview/Submit owner |
| Python projection单次hash sink/ENUM/SET cell codec | B固定typed digest与Shared Kernel sequence向量、真实native NULL/empty/SET业务测试 |
| 旧ordered Python算法/mock one-reader-pass census矩阵 | B真实ordered/key/zero/diagnostic owner；census真实Rust小fixture；G8伪gid固定值 |
| 旧ProjectionRequest cancel/deadline包装 | native GIL释放control、真实operation worker/C stop/deadline/lease/EOF与publish owner |
| 旧RepoRef reference identities与再投影fixtures | 真实C port、合法compute_schema_digest identity、outer-session close warning owner；不扩C关闭协议 |

CT108原线已允许E最终条件齐后独立fresh full t4；仍需现场前检与原子占用，不是预留，不触原冻结资源。05若原线调试占用，以当时有效marker协调。
