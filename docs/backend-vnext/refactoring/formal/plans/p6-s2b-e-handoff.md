# S2b E 实施 handoff（进行中）

状态：**最终验证进行中**；2026-11-07 00:27Z。当前固定产品候选 `1de3fa408433b344faac222d28736a82405e566a`：此前 d0/ff/7c 的消费者迁移已通过源码审核，新增窄修只删除单侧 metadata-only comparison 的虚假行内存收费，N1/M8GiB/worker12GiB/reserve4GiB不变。04 的7c backend及四Python权威整次均通过；7c t1实际成功、t4首Preview资源拒绝，已保留失败现场并定位明确计费错误。旧失败不改记PASS，尚无E GO。

当前 pending：1de 的04 backend→Repository Service权威整次0/最终容器绑定；1de fresh t1–t4完整旅程；最终同WT闭包与独立审核。06定向81项及静态已通过；04 Rust、三小包已在同E WT按实际原来源比较可沿用。三节点00:25:56–57Z已取本次准备占用，source/env/另call独立核全0，04 backend权威已启动。05/CT108准备释放收尾命令语法错的原exit2保留，实际marker移除后已另做只读核0，等待独立复核后fresh自取锁。以下按时间保留历史状态；额外工具mypy待决项早已关闭，CT108窗口已确认，不能把早期暂停段当当前待决。

## 实际消费者与删除

- 已删除六旧 SQL parser 模块与六条精确 temporary unreachable，不加 import/cycle 豁免；native parser 是唯一生产 SQL 路径。
- 删除旧 SQL row materialize fallback、`storage_projection/project.py`、旧 `_ordered.py`、旧 import replay 再投影、RepositoryRef `_read_and_materialize_table`，以及 compose 的旧 row catalog 分派。`_catalog.py` 仅保现 native owner 共用的 `CatalogError` 元数据。
- 删除测试 `_ReferenceCommittedTables` 及旧差分开关/property-only suite；publication/mutation/metadata 的合法小 fixture 通过真实 Rust projection、真实 C committed-table port 和现 Submit typed image consumer 构造，不能称独立 oracle。旧 private hash sink/cell codec 探针随实现删除。后续按 root/reviewer 全局 consumer 检索又删除 `scalar_encoding.encode_repository_row/value/EncodedRepositoryRow` 及 sole old probes，仅保真实 catalog 的 `map_repository_column/_declared_type_for`；SET 声明顺序与 DATETIME/NULL/empty 的真实 C owner 保留，C wire fixture 以逆序 SET 输入验证真实排序。
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

## 早期后续计划（历史，完成情况见后文）

实际consumer残余检查、受影响focused/Contract、五Python包Ruff/mypy和保留工具静态/小入口；最终候选的04权威runner和container、05 t1–t3、CT108 t4仍待完成。本轮新建 E 自有04 gate WT，原 S2a WT不动。三小包不沿用原 `3b037adf4c`：`COMMON_GIT_COMPONENTS` 的 `vnext/scripts` 新增 `run-s2b-capacity-census.sh`，且 `vnext/deploy/compose.yaml` 有 D 资源接线变化，实际共同 Git 输入已不同（不是 fixtures 改动）。因此后续五 Python 包全部实际运行；Rust 已由下节合格本轮来源完成，最终在同 E WT 按真实闭包判沿用。容器需最终候选本机离线build或严格同04同WT等价carried；06证据不作04来源。

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

## 本轮收尾：实际通过与待续边界

产品候选保持 `d0f5602d6f9f352b493bb31fbaf6b0a24dde4c5f`。375 项核心 focused 在 `0d4d4240fe` 实际通过，backend Ruff/default mypy500 通过；额外工具 mypy 失败单独保留，整次不记 PASS。其后受影响 unit 首批在127c为799 passed/4 failed（日志 `logs/s2b-e-consumer-focused-127c501b7c.log` SHA `0c20aefeaba20d7830e32e974e8687558e5e008cf6a4bc4035257e41efa1aa10`，serial未接）。失败为旧 raw Parquet canonical fixture、缺 repository scope 和已退役的 RepoRef Parquet cache 跳读测试；不降低生产 scope/Arrow 检查。

7b3e 的 targeted 为273 passed/3 fixture-scope failures，日志 `logs/s2b-e-consumer-targeted-7b3e40ff97.log` SHA `02224d3fbc55fe58978691a39d3ddb04f5d8634fdd2a8e55d235936a465402b5`。d0 窄修只补 fixture 的显式 repository scope并删 unused imports；原 client Parquet一个共享artifact/四bindings预期保持。d0复验 replacement **7 passed**，此前未接的受影响 serial **3 passed / 831 deselected**，backend Ruff与mypy500均0；`logs/s2b-e-consumer-scope-fixed-d0f5602d6f.log` SHA `ea84c4f1a16f53440dd28453e8ef90ad6e250879d5e11a5c03356270ca96a025`。原失败不改记通过、不为文档重复这批focused。

127c 五 Python 包 Ruff/mypy全部通过，所有 editable paths/direct_url 均为 E WT，native expected/installed tree为 `137d499975f3c104ae9c3268b9e12befb2817ba1`；`logs/s2b-e-static-five-127c501b7c.log` SHA `ad466445efb413ee560d498b047b98c93926a87a78e0692cf57ef9d13a3da0ee`。之后仅backend变化，其d0静态已另通过。314静态首轮在backend遇移交rule test后的10个unused imports，原日志 `logs/s2b-e-static-five-314067ff72.log` SHA `139b831bfb436206b0e1724e797c1babf540a65accb636f3dbdb2ca7d99ce520` 保留。

06 在 **19:48:55Z** clean d0下释放本任务占用，E WT/venvs/target/cache/logs保留，无running Docker/Dolt/8000。释放日志 `logs/s2b-e-06-release-d0f5602d6f.log` SHA `ec3e1fadbff01ab2530428d30836ec475281f50073617444cc7128e9cd1db467`。

### 04 Rust 实际合格来源

新 E WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate` 保留，原 S2a WT/证据不动。唯一 source ref 为 `refs/codex/s2b-e/source/d0f5602d6f9f352b493bb31fbaf6b0a24dde4c5f`；bundle SHA `215d1a49a77bad63b764781178af1d59c6406e75d559a94bd72bcb912027771d`，advertised ref/SHA实际核合。已审 source脚本 SHA `87ce24d81a381173327ceaab98bb4c451f14bcf2a482f641b694acb02b1a2981`，Rust driver SHA `cea9f91316a9ff2462f3004cf76fdc876beb73191f611dd31f6880ed9395c9bf`；均在04 `/home/dev/gdds-test-tmp/` 保留。

04 于19:52:41Z原子取占用，source实际exit0后独立SSH call再次核 HEAD/clean/legacy、Cargo.lock/selector及 rustc/cargo/rustfmt/clippy-driver 同一 `/root/.rustup/toolchains/1.97.0-x86_64-unknown-linux-gnu`；然后另call启动 Rust-only 权威入口。离线、jobs4、固定PATH/TMPDIR，无 Python 包、Compose或真实旅程。

**Rust source V = d0f5602d6f9f352b493bb31fbaf6b0a24dde4c5f**；19:53:12–19:54:00Z，fmt/clippy/test三步0，整次runner0、driver0，target由runner清理，HEAD不变/clean、无残留。19:54:00Z释放本任务04占用。

04路径前缀 `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-d0f5602d/`：

| 证据 | SHA256 |
| --- | --- |
| `source-01/source-prepare.log` | `aa4613deba26e7d221af36f29492908cb5f20b8fa0e7b2e4901793d0010be0ec` |
| `source-01/independent-source-verification.log` | `65b65bacd7892b39f423b2b06db21279057e53676288089f583274ff62870ff5` |
| `rust-01/authoritative-runner.log` | `6253a0e3000ef60456a5359d062ee3a6ef793be21292ecdd47f722ca3286abf9` |
| `rust-01/rust-source-manifest.json`（从原log逐字提取，不重算来源） | `4f091a7f3b369be760575c06a8d152c2ebea12d912057ad9be68a21f010ab950` |

Rust 起始 `total_digest=5dbb8a817e37bad59f5318d63592e405f2bb3dc3886b483bc329a05f77b540ea`，clean_worktree=true，完整manifest留原log；独立审核已核合格。后续只在该同E WT、实际来源环境与闭包规则下 compare；不能把新建WT或06结果充当 carried。

### 真实节点缓存/输入前置及 t4 driver

04/05/CT108均只读见本机uv缓存、Dolt、Python3.14.6/Rust1.97镜像，RS dependency-base `gateway-p2r1-repository:lock-6dc9659f0aee`、client e2e base及其锁labels；04/05已有backend d054。CT108缺d054，已在本节按DC67从获准 CT201归档预填：source commit `132fc621d5711ae39ac8f1dc66f4349b2f6fe428`、input `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，archive SHA `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6`。manifest唯一tag d054，不覆盖任何冻结tag。

CT108短占用19:32:34–19:36:47Z；目标文件实际creation→write-complete为19:32:49.642–19:33:09.205Z（记录真实file stat，未虚构scp精确进程时间）；load19:34:00–19:34:15Z。重save后用既有helper SHA `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972` 核 source config `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 和全部19 DiffIDs逐项MATCH。完整身份文本SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`；归档与完整列表在CT108 `artifacts/s2b-e-dependencies/`。prefill日志 `logs/s2b-e-dependency-prefill-ct108.log` SHA `0a6b22ee02afcdb84fc05691429cc1d9b417c76056cfff7d3caeec6cf4e2981f`；释放日志 SHA `fe64005a9964587b6d83aa333a024e33a0f7ca64a4a16e5447de8a91bb73943c`。无原基准卷/checkpoint/images操作，无代理或公网。

19:57–19:58Z只读前置逐节点核既有 `/home/dev/gateway-real-dumps` 的8个package bytes/SHA与各自datasets.json一致，且五个所需镜像tag均存在，记录实际RootFS/RS/client锁labels。没有运行census、解包再生成输入或实际旅程。各节点 `logs/s2b-e-readonly-input-cache-preflight-d0f5602d.log`：04 SHA `f67953517912a21424fd7cd36fa6094eeb8a370ba982019d170da83771698665`，05 SHA `037724a64071b107109f68d51b71eb3999a0713d66d7599643bb59728088c638`，CT108 SHA `a19e06843f2288da77b01286abedfbc1f288d729250e8bef8cf9d59a30a4b0a6`，实际exit均0。首轮04/05因外置logs目录不存在，shell重定向在Python启动前失败；保原工具stderr转录 `s2b-e-readonly-input-logdir-error.log` SHA `3f2a666f3447084b0f7d5398bca39ab117731ad868c8d8c5b274c711bcad644e`，明确为原工具输出转录；按DC68只创建缺失目录后从该只读步骤开头重做一次通过。

**19:58Z时已审、当时尚未执行 t4 driver：CT201 `/tmp/s2b-e-t4-driver.py`，完整SHA `286ef89e7ce83377165df4c4f1c62e6c408d07bf75da3e0075f0b8abbbb40299`。** 后续只能运行此内容或先审差异；旧稿23339/f430/ba9等均不作为执行版本。它调用同一次 fresh full t4+显式N/M，增加现有 `--keep-stack --project-name s2b-e-t4-<candidate10>`，无from-step/resume。先存stdout完整hostname/起止HEAD/UTC/exit及各owned logs/filteredinspect，直接host cgroup读 memory.max/peak/events并筛4资源Env；peak为cgroup生命周期高水位（含startup/helper），非RSS、非M。OOM/oom_kill key缺失即不完整；核整旅程worker StartedAt/RestartCount及normal stop/ExitCode/OOM/clean HEAD。只有journey0且必需证据全齐才清本E project并释放；否则正常stop后保本E容器/卷/busy，立即交DC80主动诊断，不自动重跑/resume。此driver审核通过不代表旅程已执行。

W1型诊断仅将现有 `record_operation_timing` 所收 timing保存在full JSON的 `operation_timings`，保原DC32，无新增计时点/轮询/HTTP或额外旅程。未来t4单次/N1/M8GiB只称受理响应后→首次可读观测/终态代理（2s轮询与可能fallback），不冒称精确READY、2×t4正式W1、30s目标或性能PASS。

### 19:58Z 暂停时的历史状态（已由22:46Z恢复记录更新）

Owner尚未答复**额外四工具mypy的一次明确修正续做**。第一次显式文件清单在60c5因namespace重复模块名失败；第二次`-m`在0d4d因缺src搜索root报import-untyped/继发Any；两日志/完整命令已交root，严格保失败，未第三次试跑。审核者已只读确认具体待执行命令：`MYPYPATH=src vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync mypy -m benchmarks.real_dump_census -m benchmarks.real_dump_keyless_census -m benchmarks.real_dump_forwardtable_blank -m benchmarks.real_dump_journey`。不扩ignore、不改产品配置/锁、不以default mypy500替代该四工具检查。

按root指令，等待此答复期间**不启动五Python正式runner或完整真实旅程**，避免潜在Python/tool修订后重复。后续尚需：

- 现场重新核各目标节点有效占用/服务/端口并原子取锁；当前04/06/CT108本E占用均已释放，05未取得E占用，无预约冒称。
- 最终候选固定后，在04同E WT同步/强制重装扩展并核本地pathdeps实际绑定；04仅Rust已准备，五包正式venvs/必要工具链闭包、最终manifest、当前RS/client/backend/worker镜像本机离线build与最终容器provenance未执行。
- 05/CT108尚未新建E真实旅程clean WT或其venv/任务RS tag；须分别准备并核离线依赖/镜像身份，不能复制D venv或以旧整镜像prebuilt跳构建。
- 05 t1–t3 fresh full、CT108同一次fresh full t4与资源/观察timing、最终审核及同WT闭包/镜像绑定尚未执行。当前8包原始输入只读hash核验不代替候选工具的`--validate-inputs`/语义前置或真实旅程。

收到Owner答复后用本E实施者/审核者同节续做，不新建角色，不标E GO/S2b exit，不推送。所有未知容量/完整worker峰值/性能值保持unknown。

## 2026-11-06 22:46Z 同节恢复

Owner已明确批准额外工具mypy的具体一次修正续做；未新建角色。06重新BatchMode/整机前检并原子取占用后，在原E WT固定d0、clean、实际E解释器与`gateway_backend.__file__`绑定核合下，于22:46:12–22:46:13Z执行上列`MYPYPATH=src`/四个`-m`命令，**4 source files / exit0**。不改strict/ignore/锁，未出现准备或真实类型错误。

日志06 `/home/dev/gdds-test-tmp/logs/s2b-e-tool-mypy-approved-d0f5602d6f.log` SHA `aea3a32e91ee5e2391bc9d7983b9e9fd31a64a6fbee714d892fa4fa61d3cfe9a`。22:46:58Z释放短占用，释放日志SHA `eb8a8d4213ea5b9d70ca7df674cb4a5bad1321d89bcbbb4bde2b92942aff273b`。上节待决项至此关闭；历史失败与暂停记录保留其当时事实。

恢复时主线a532a3bbf7相对固定产品d0的`vnext/`无差异，后续门禁绑定新冻结完整SHA。继续已授权五Python权威runner与t1–t4；不重跑合格Rust，而在04同E gate WT按实际source manifest compare。所有节点现场重新取占用，脚本/缓存前提经既有审核后执行；原冻结资源保持。当前仍未宣称五Python、最终容器或真实旅程通过。

### 23:09Z：剩余测试消费者修复

04 同 E gate WT 在 d0 离线准备五包环境，实际模块与 editable/direct_url 全绑定 E，native tree `137d499975f3c104ae9c3268b9e12befb2817ba1` 匹配；Rust current manifest 与原来源文件字节摘要同为 `4f091a7f…`，总摘要同 `5dbb8a81…`。`python-prepare-01/prepare.log` SHA `7db3bd86e9c0a37a535dd2f33cef87b131d14c8bf207d3702099d54d2e90556d`，另 call 验证日志 SHA `dfac41a1578ee7756fa66fef1ef576118e11fcfbd2890b8ab86ec1dce01dbd6a`。随后独立 call 开始五 Python 权威 runner。

首轮 backend 主体实际 **20 failed / 3111 passed / 8 collection errors**，serial 因相同两模块收集失败；原 runner 自身继续其余包，于23:13:05Z自然结束 runner1/driver1，起止d0/clean、无残留并释放。完整日志 `python-authority-01/authoritative-runner.log` SHA `6b52584532f2ff237ca99b9275008c16a74d6403d8144e84318ede6aeeec1ad6`；RS主体1744 passed/1 skipped、serial207 passed，也不作该失败整次的合格来源。不另开真实旅程。三小包虽分别243/152/161 passed，失败整次不能作为合格 source V。四类漏迁均在测试侧：

- module-level `PREVIEW_RESULT` 在 autouse kernel context 前构造真实 parser fixture；移到显式依赖现 context 的测试 fixture。idempotency 改 runtime module 访问，避免 `from … import` 留下旧对象。
- UUID Submit 测试仍用默认 `repo-1` 的 canonical artifact；将真实 repository_id 贯穿 seed、canonical bindings、refs/payloads 与 Prepare helper，生产 scope 校验保持。
- removed-tables 仍将 raw Parquet manifest 交 canonical caller；改在真实 seeded UUID 下用现 projection/canonical IPC 构造。
- canonical identity 的直接 RepoRef 调用未供 C port；接真实 committed-table factory 与本测试 control DB，保原身份/行预期。

失败 DB 的只读诊断确认 Prepare 被 `STORAGE_PROJECTION_FAILED / frozen canonical table net_cfg is unavailable or corrupt` 拒绝；04 `python-authority-01/failed-prepare-readonly-diagnostic.log` SHA `87477bd564946ab46315115603aeb91fb0e47e966fc1ee7570d39ebd4b51da3f`。生产拒绝边界、核心 expected 与业务断言均未放宽。

固定修复 `ff970567f875bbc2ae357db950084dc450f8d88d` 仅9个测试/helper，独立源码复审 clear。06 23:06:41Z重新取锁；固定 fullSHA task ref/bundle同步实际0（source log SHA `32be2deaa791ac14a605174a798c4204f9048327c052f04e9726f68cb4132d92`），另 call HEAD/clean/实际4 path deps/native验证0（SHA `a6dbed49a709b173d1babb178ccf1326ed54731bf02aaefc5c07ac21ea357527`）。23:08:11–23:09:01Z：backend Ruff/mypy500、全 backend collect-only **3230 collected**、受影响主体 **184 passed**、serial **16 passed**，整步0。

06目录 `/home/dev/gdds-test-tmp/artifacts/s2b-e-fix-ff970567/`：`fixture-focused.log` SHA `d46faffb6dc231f81c50e3fb30683188751d974ec1b18c9fc30468262fa2a1a5`，`backend-collect-only.log` SHA `80da56e799db9fc7146eae64ba3a7df54a8ea78df72e8677f9eb30386eff8161`。实际命令为受控 wrapper `run --no-sync pytest` 加以下12文件，先 `-m '(not serial) or parallel_safe' -n 4 -q`，再相同文件 `-m 'serial and not parallel_safe' -n 0 -q`：

```text
tests/test_submit_application.py tests/test_submit_idempotency.py
tests/test_submit_transactions.py tests/test_submit_job_prepare.py
tests/test_submit_job_effect.py tests/test_submit_worker.py
tests/test_submit_recovery.py tests/test_submit_prepare_removed_tables.py
tests/test_canonical_snapshot_identity.py tests/test_production_wiring.py
tests/test_submit_http.py tests/test_submit_read_http.py
```

全收集命令为 `vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest --collect-only -q -n 0`。23:09:57Z确认clean/全机无残留后释放06；`release.log` SHA `33613281211d0d1b668eb72d1c5b6904162ce593caad2d405caa1c7c6359da4d`。后续04改为同WT先 backend-only 权威整次0，再其余四包独立整次0；Rust只做同WT来源比较，不重复运行。

### CT108 源码与环境准备（未运行旅程）

原 gate bundle 依赖53b，CT108实际旧 root HEAD `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3` 缺该 prerequisite；source01在 fetch验证前置失败，未建WT、未测试，日志 SHA `7e8971bb24986ae8482f69f616d21dc65ce828fb9f71b26feca050f28a3c1699` 保留且释放其占用。按 DC68 一次明确修正：CT201核实际base为d0祖先，新建本任务 `refs/codex/s2b-e/t4-source/<fulld0>`，bundle仅排除该实际base；新bundle SHA `0f732d7da982902b6a6d56008551d2843640bbda918122e739f43f42c4a2b721`，CT108先只读verify0，source02脚本 SHA `eaf95e9198bdec69484514ef4d7baa4f0aa30fd84560d64444ec9f2df0ec38a9` 经审后执行。

23:02:46Z实际取锁并source02成功，独立 E WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-t4` d0/clean、legacy正确。source log SHA `505400d4ae19260d8cded92ff3bf448237f2fa6c5a4e4ea464c5e7fbc13680d2`；另call HEAD/clean/selector与四Rust工具核0，日志 SHA `d9cba5ce77a071c884f8072436bc2791d2135a6f9ba0534f05b90163d065890a`。未改原root main/冻结refs/卷。

environment01在调用 identity helper 前失败（23:03:25Z，exit2）：脚本错用根临时目录，实际已审 helper/identity 在 `artifacts/s2b-e-dependencies/`。此前自身 `test -f` 被末尾 `df` 的exit0掩盖，明确记为命令检查遗漏；不称缓存缺失或产品失败。原日志 SHA `84bae81a974c77e3d233127e0c9f2e1ed52a9d4f79d3e0070ae78185e8d63688` 保留。按此env步骤 DC68一次修正，先单独核所有外置输入/工具/缓存存在及 helper138e…/identity0577…，新前检日志 SHA `af3c70db55c7f12a04a8f073e01d50f55bb5b7620c2619b0e8fca35aaba870d4`；env02脚本 SHA `73fff0ec107cea721cd3da2413a58a813f6bdeae7f8ed98294ebf0e3051f1210` 仅改两实际路径和新out，经审后重做一次。

environment02 actual0，于23:10:00Z结束：全config/19DiffIDs匹配、offline新 backend venv与四path deps、native treechecker、本机owned RS build、现CLI help及八包 `INPUTS_VALID`。日志 SHA `b1819ca1c5d0fb42390cf89384c7150f87d6f466faa68fa872a88f0ea6814539`。另 call 独立验证actual0，日志 SHA `845f043e45f366cbf9f05bd15a89127ecd7443f5c16fd54a1e5b3f213cec2ce9`；23:12:28Z核owner/HEADclean/整机空闲后释放准备占用，日志 SHA `aeaefcea0afc6c180a3dbf574c1d699c2c0ebf4e55a510b546996dc0f6023354`。这些日志均在 CT108 `artifacts/s2b-e-t4-prepare-d0f5602d/`。

准备仍为d0，不作ff最终门禁。真实t4尚未执行；后续需更新到最终候选并核绑定，保持已审 fresh driver286与失败保卷规则。05原线GC有效占用优先，当前未取得E预约或运行t1–t3。


### 23:40Z：inline comparison 适配器收口

ff970 的04 backend-only 于23:29:03Z自然结束 runner1/driver1，主体3173 passed、serial55 passed/2 failed。完整原日志 `artifacts/s2b-e-gate-ff970567/backend-authority-01/authoritative-runner.log` SHA `a27604d02e9a5c66a9b70442e4f6e78701361adedafc0700f1741d3ccb6dcb1a`；起止ff/clean、无残留并释放，不作backend合格来源。

两失败均在远端 History/ordered operation 已SUCCEEDED、commit/count断言通过之后的测试适配器：`history_compare_oracle` 硬编码repo-1而Compose provider catalog为真实UUID；另inline `_sides_from_materialize_checkpoint` 漏必需repository_id，且新exec进程未显式初始化N/M scope。静态核所有直接/间接caller后一并修第二个ordered-facts inline helper，避免它在首个digest探针之后继续漏同一入口。

固定候选7c023累计仅3测试/helper路径：history请求scope取provider.catalog实际repo，两inline均以repr注入actualrepoid、调用薄bootstrap N1初始化，并以显式M8589934592的new_operation scope包住现artifact load/compare，pair pipeline也传repoid。无src/核心expected/业务断言改变，保zero-write/restart/ordered事实；这些helper明确为production-derived integration consistency，非独立算法golden。独立源码审核clear。

06使用原E WT固定7c023、clean，source实际0后另call实际E四pathdeps/native137核0。23:36:11–23:38:44Z，已审driver SHA `1c805c41ae8629b4ce171956817cae8ae74ad589532165e9ba7176f1060fb942` 实际执行backend Ruff/mypy500、local `tests/test_history_compare_jobs.py -n 4 -q`（27 passed），再本机离线构建owned RS7c，运行两个原Compose exactcases `test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart` 与 `test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey -n 0 -q`（2 passed / 141.02s），整步0。实际argv在原log，不复跑全57serial或全runner。

06 `artifacts/s2b-e-harness-fix-7c023971/fixture-and-compose-focused.log` SHA `86281ad7703b9f188a37e479868df4bb6a52662407dc339542c2d19652c6c1b7`；source log SHA `4eeda91574be0041f487f37c4fde788134042403e25f0010277b8bafb04089ae`，独立env SHA `3fa7b5bc2f702a06869f22d05de9ead900bd5ee3cf4cf64bc2c061b413a635bc`。23:40:06Z核clean/owner/全机无残留后释放，release SHA `1cefe0108f5336a437f20bb1c07b534fdf022f76dd0e30eef5f1e789598a407a`。独立审核已逐项核实；这些不是04权威来源。

随后04同E gate WT固定7c023，source0→另call源0→实际Rustcompare原d0/5db相等→仅ownedRS7c本机build与现五env binding核0→独立verify0后，另call启动backend-only权威入口。source log SHA `3a8140aa2b8ecc521e06c0f87c295e707455f3afcea6e499db61ebe720746496`、源独立核 `a9d5e512d9e10f55126033935e0d61df42b1cd27199594955b9ee428d8383625`；env SHA `fd642f9bceb5f4337f981e99de859b1b8c8db18c60f4d54a5ce53b3dd6e577e9`，独立env SHA `027e3decbcd1e1ee3e510301fc9d5981437dcae6580a8a4026d796289f252cc2`。当前该次runner仍在运行，未提前记PASS；成功后才四包与真实旅程。原合格Rust不重跑。

### 05 首次 E 环境准备

原线GC于23:29:02Z释放05；23:37:45Z E现场只读核无busy/容器/Dolt/8000，actual root previous仍为2c79完整SHA、new E WT未有、缓存/legacy在、磁盘196GiB余。新前检八包bytes/SHA、五基镜RootFS/锁标签、外置helpers SHA均0，`logs/s2b-e-05-input-cache-preflight-7c023971.log` SHA `a7d90c161cf891cd59c1708c0c3275b8b66961cb64319b25b860f12320b4cebe`。既有只读预检脚本SHA与本地同为aefc62c6…，复用既有文件，未覆盖。

新task ref `refs/codex/s2b-e/t1t3-source/<full7c>` 使用完整17MiB、无prerequisite的bundle SHA `71e699bde202541827b4b55f3a38c25d25542735f0b8ff57d5392d08e05ee416`，远端先verify0，不假定05已有d0/ff。23:42:03Z现场原子取锁，source实际0后另call HEAD/clean/legacy/selector四工具0；E WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-t1t3` 固定7c023。source SHA `e1f610908265cc97b7c759d05852edfdc7993bda976966d50301fdfd19c638e5`，独立源 SHA `3429ee30f7e152bd3d5e5fac641b33c35d99784e9a06851a8d7b5a8a4c962690`。

新建offline backend venv（未复制）、真实native137/四pathdeps、同节点backend base的config+全19DiffIDs、RS/client锁labels、ownedRS7c本机offline build、现CLI help/八包INPUTS_VALID均0，23:44:38Z结束；env SHA `61d8945c4d7ac6a3310c7e973326ccfad213b2150c8c0339e266a601350ba331`。另call独立env核0 SHA `0baa6c7173e5dc969634b0c2ef0899c90561a711cb0999d066d722f73ed74e97`；23:47:42Z核owner/HEADclean/全机idle后释放准备busy，release SHA `d22116cdfd99e5f5fc10e46befb0301d304879df996683717ee8f10e6cca1f97`。除preflight log外，各路径均在05 `artifacts/s2b-e-t1t3-prepare-7c023971/` 对应source-01/environment-01下。原线三个保留GC卷/原冻结资源不动。

真实t1–t3仍待backend整次0后按tier顺序fresh。已审外置 `/tmp/s2b-e-t1t3-driver.py` SHA `d524f828ffd32510b57c608f49e7465bda4e9892a72e667714693a016f200d06` 由原t4 driver286仅参数化tier/WT/project/purpose/metadata；同一次fresh full加现keep-stack，失败先取证/正常stop、保本E资源与busy交DC80，不自动下一tier/retry/resume；成功且必需证据/cleanup/release齐才下一tier。未启动真实旅程。


### 2026-11-07 00:27Z：合格来源、首次真实结果与单侧预算修正

04同E gate WT的7c backend-only于2026-11-06 23:56:36Z自然whole runner0/driver0，主体3173 passed、serial57 passed，HEAD clean且释放。`artifacts/s2b-e-gate-7c023971/backend-authority-01/authoritative-runner.log` SHA `1e81ecf2231559035123468ac6a0d27614d9f4f54cc8720d58dc4e484d9c0a75`；从原日志提取的起始backend manifest文件SHA `822984029a0c83b61e44c0d82124570c3595a8f53e800a0c9f0cce97cbd1796a`、total `7fb9738df11a230574eee2d9e3a6f9182ad98997194b4cba3bdc7fb0e9f51526`。Compose provenance SHA `d7e2f4b20d603397dee4d1015fd241880139a5e3c400bab014bbb0d9bc503750`。1de改backend逻辑，因此此结果仅为旧候选回归来源，必须重新实际运行backend。

其余四包独立whole0在7c、同04WT于23:58:30Z启动、00:11:02Z结束并释放。shared_kernel243、contracts152、client161通过；RS主体1744 passed/1 skipped、serial207 passed。`four-python-authority-01/authoritative-runner.log` SHA `d1d829ea5bfd398f012ed79bfe70e3f3adb15f18317da717b595107e7f9e2d58`。下表来源文件均从这次合格原日志的起始JSON提取，审核者逐对象核合，不用post-run计算冒充来源：

| 包 | 原source total | 原manifest文件SHA |
| --- | --- | --- |
| shared_kernel | `26b8a0ba6f67b990433d361aa137dfaeb96d5d0826f6c6e36c2b08d37a98c605` | `d39f3254292f0332859a04e8282a8caeec4273c2c4e7b16eb8309e3964611b2b` |
| repository_contracts | `eb237e7926624d250119cdb3a755f3e3193432158293108db5085e4ac1af64b5` | `94076325123e76a6ffaa43c307077e75d071354a4d3d219621ed5f772acecb0d` |
| repository_client | `294456e0d70e11e854243a9947acd8c17b39538475b4a8050215a8747288d213` | `22fdb2180041fae1751c52cfb7bf08b5d293971af01392de1f50f70cab831073` |
| repository_service | `67e5a5895d42f018d25eede60eb978e332e0001355f79fa292c6f7a38228b402` | `a67b737f8e4909ed9f49866b8e58f41a8b997d6b26bbf13c96ab0c37fb45d585` |

1de同04WT的Rust compare仍等于原d0 total `5dbb8a817e37bad59f5318d63592e405f2bb3dc3886b483bc329a05f77b540ea`；三小包00:26:48–52Z按原HYPOTHESIS路径不存在、实际逐项manifest compare均可沿用（无changed components），`artifacts/s2b-e-gate-1de3fa40/carried-01/closure-compare.log` SHA `269ea1123546cfb2adc361bab78a27a8276b1d0ad8020e6ecfe752151f44692c`。RS的真实`docker:context:vnext`变更，不能沿用，安排backend后独立RS-only。

**7c t1实际PASS**：05 fresh project `s2b-e-t1-7c02397139` 于23:58:30Z启动，00:03:29Z journey0、00:03:36Z driver0/必需资源证据齐/正常停止0/owned cleanup和release完成。`artifacts/s2b-e-t1-7c02397139/journey.log` SHA `f5adef30738d52522c79d4057b865bbbcdc3daf29944a6dc2e4b8a221e6b2f62`；`result.json` SHA `bcec2fce657b0a1671612a78e09295c8747ec82e4054720df80f86f6ccf5da84`。t2/t3未启动；1de需fresh t1，不造已清卷的resume。

**7c t4实际FAIL**：CT108 fresh project `s2b-e-t4-7c02397139` 首v1 Preview（operation `op-c1d2bdb34f8e6eda8b702df5`）在00:01:07.577Z返回`RESOURCE_LIMIT_EXCEEDED / operation memory reservation exceeded`，journey1/driver1。step1 materialize_inputs SUCCEEDED、step2 assemble_preview FAILED。`--scope full`表示完整旅程，实际输入是MODIFIED_ONLY：checkpoint BASELINE/INITIAL均空、MODIFIED312表，不是InputCompleteness.FULL。资源证据本身完整：单一未重启worker/N1/M8589934592/envelope12884901888/reserve4294967296、cgroup memory.max12884901888、memory.peak660467712、OOM事件0、正常stop exit0。660MB只是失败前缀全生命周期cgroup peak，不是RSS/M，也不能证明完整t4的M8容量足够。

CT108 `artifacts/s2b-e-t4-7c02397139/`：journey.log SHA `2a57ee76f3f7d943f78d97f595e424b5a9906df4473f954d16d741dffa9666de`；result.json SHA `032fb2c1b8fb444c91b5c566eb276d617a3526e2795be47156bc6d7f1766a0ab`；worker资源SHA `8ad51eea153c7335ac3a7a06b2e70b5dadf383450a983311feafb3ec3da5e659`。原sha256.json不改。

只读controlDB/checkpoint/metadata诊断不调用Rust、不读取rows、不重跑operation。cpRef SHA `3d3f09d3838939e6aa0a6af193aa75c4c7cf714fa9801edbb1f6ba70ad76945d`/1675B，sidesRef SHA `fda6022369377acc2e61db9292d970466d326f2b8b3610bd47da782bfa469c5e`/513564B，实际modified SQL source SHA `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675`/5597503B。312任务含278record/34browse-snapshot，全部是单侧ADDED。standard与ordered的single-side分支仅输出table metadata，不读取rows；旧upper却收费rowSum13700821888B+metadata base2621440B，**即使不算非负Arrow.nbytes项也至少13703443328B > M8589934592**。device_st单项rowterm6161836800B。已知部分retained27116864+62330728B，完整当时used/high-water未持久化，不能虚构精确used。`dc80-metadata-budget-01.json` SHA `08f7212bee727d2ce0ff26a800065cf299577f74e4bc9455a9b901dd7f0e166b`已由审核者独立metadata重算；control只读log SHA `fde138e04496792096b075863169387d6ac43d712ef65a41f0b7387b80829ddf`。

root授权保现场释放CT108：00:16:05Z固定7c/clean、owner精确/整机idle后仅删除own marker，`dc80-preserved-postflight-release.log` SHA `e21deb1a6df72eb194c3adc64fb3f908381d2112679be0e10fc6886871f859bf`。保留 stopped worker `c8ee877173ec`、backend `1e898e15bf50`、RS `cf732406a535`，三个同project卷backend-artifacts/backend-control/repository-service-data与网络`a65f15c88439`；无down/rm/prune。未来旅程必须新project，不能复用此失败现场。原线冻结资源另保持不动。

**精准修正1de**：standard.comparison_python_memory_upper仅对before/current任一缺失的单侧任务跳过未消费行项，metadata base保留；真实双侧standard/orderedidentity收费、全部系数与N/M/envelope/input不改。权威comparison owner新增普通/ordered×added/deleted四案例，以真实1/256行Arrow、小剩余额度证明positive metadata charge恒定且rows/stream零调用；真实双侧拒绝继续只由既有preview-job owner两参数证明，重复负向探针已删除。源码独立审核clear。

06 fixed1de source0（SHA `55d0e6e6bd3b2c38ac0e4a13204ea6bf58e90535fb29475a8435f44cec45459a`）、另call实际E四模块/native137/clean核0（SHA `6f99108f38b97556b8ea6bf6ece603f53bd7dde47e54fe62ac344f57ec290c69`），00:18:52–55Z backend Ruff/mypy500及定向**81 passed**，`artifacts/s2b-e-budget-fix-1de3fa40/budget-focused.log` SHA `850c445ad4a79864ed9a1c0d228a07c0512039acb27523a9ff27009866d29747`。命令为wrapper `run --no-sync pytest tests/test_comparison_standard.py tests/test_comparison_ordered.py tests/test_preview_job_assemble.py::test_pair_memory_admission_rejects_before_python_row_comparison -n 4 -q`。00:24:09Z核idle/owner/HEAD后释放，release SHA `8e6bd818fc7f5abfb90dd1084233b62fc6a06ace9fa10f2cb1b81f1b3e4b5405`。

H taskref `refs/codex/s2b-e/budget/<full1de>` bundle SHA `711ecbcf21a309eec0b64323288a0391e3cb6cf046c4c1a956fee07c24b2663c`，仅排除各E WT实际previous7c，分别verify0再fetch，不改rootmain/冻结refs。新H门禁安排为04backend→RS、同WT沿用Rust/三小包；CT108 fresh t4与04backend可并行，05 fresh t1–t3逐档0且证据齐后下一档。若真实读行仍超M则停交Owner，不自行加M/改系数。


### 00:29Z：1de门禁与真实旅程已启动

1de三节点分别source0后另call源验证0，再env0后另call环境验证0；actual E path deps、native137、离线base/RS/client锁身份均正确。04 `artifacts/s2b-e-gate-1de3fa40/` source/indsource/env/verify日志SHA依次为 `1bd2c6d00a71ef20e16214b13307e913120ada761b69b3aba1f1332cde47e160`、`cf792573a17e649b3298689eed2403f473d715d42e7521753eaf4930d2d402a6`、`c8fd6b7cea1bb93d313749fc6a4110c41df7cfc93cd47a483a9b875b4dc90223`、`9ebe9262474f1f5af409fcd337f49859903ea321c62b879e06b0d128ac4706c8`。04 backend authority脚本SHA `3e183d53a3ea6330fda409b7976cbd5035ed7bb470d32282469fabb59330c49f`已实际执行；RS-only脚本SHA `eb7b59d8931cc5acecdc778160179ada388ea865263390e45e018d44d0540c25`只在backendwhole0/release后执行。

05 `artifacts/s2b-e-t1t3-prepare-1de3fa40/`四日志SHA为source `f463175d4dd25dabb88d8b8de6008beefa0e7da94ecc0b12f2a9a737851a4207`、源独立核 `864a49143a247d79018210ccf03935edc11f16aa0c886d21881610c364118658`、env `3b506181e93145d01055a0f5876bb3277520c46f12a9c198dba70a28fa09c6cd`、环境独立核 `e58c31d94b072375faf4a935c72f161dc214cfeedff82ba4852af7e252914a04`。CT108对应 `artifacts/s2b-e-t4-prepare-1de3fa40/`四日志SHA为 `3464169d14906aa2e49ecfbdab91258d5ce4dcff9851e1d89b9e4ca87b5adeed`、`0339b3d00226b91c9948fa1522dd03cc1444a4167afd0dc914f3ed6fce434679`、`eb576cc116e48aec93558388b4f41041db78fe39eb041e2915ab82a65bbcf1ce`、`e55bfb1ada7ebea0734e79b158da9d9c29e0f8d5b3a6dbf667605332d118e274`。

05/CT108准备release在00:26:52Z已执行idle/owner检查与移除标记，但追加footer的自身命令`{date`缺空格，使整个外置shell actualexit2。保原release.log（05 SHA `5d24bd99b640ffc2fef9ab782b514240a2c559c5336db50f94513fe6b8c15bea`；CT108 `5725f928f4b23487a8549a6dbd194aa2a5fe401852f547af3f3a1cfa85cc5c44`）不改；实际工具stderr仍保原调用记录。按root DC68一次明确收尾，00:27:07Z先独立只读查marker absent/原log，再00:27:22Z核cleanH/整机idle/无marker；**不重复rm或资源清理、不回填旧exit0**。两个节点各自 `environment-01/release-footer-command-error.txt` 是错误摘要转录，SHA `853153ce94633ffd3e2d061b8c5ccac6d2c943ea9ac39a4983d82a76fb60315e`；新 `independent-post-release-verification.log` actual0，05 SHA `f63200131639811529307b0a0d5ba0e879cc8e3c4175d65b7dcec8c022fd017b`、CT108 `374f47d7c64608137417663e3ee993e212fd5f0c4d3728208b9f4b1631c97eac`。独立审核已核此收尾闭合。

00:29:00Z按已审driver实际SHA匹配后，CT108 fresh project `s2b-e-t4-1de3fa4084`（286ef89…）与05 fresh `s2b-e-t1-1de3fa4084`（d524f828…）各自重新现场原子取锁启动，与04backend并行。无from-step/resume，旧7c t4停止资源保留。结果待实际完整退出，不据中途Preview或step成功宣称整档PASS。
