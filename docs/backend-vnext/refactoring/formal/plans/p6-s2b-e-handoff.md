# S2b E 实施 handoff（进行中）

状态：**最终32GiB envelope / 8GiB reserve / 显式M24GiB的必要实际验收全部通过，待唯一最终H绑定与独立结论**；2026-11-07 05:27Z。固定产品V `a6876d560050285321fd9f62942d590a03f35d64`，N1/单active，保留FD生命周期与non-record新增列真实行比较准入修复，main无临时校准日志。06必要定向30PASS、五包Ruff/mypy全部0，04六包权威runner整次PASS；06新real WT离线环境/实际绑定已核，fresh t1/t2/t3完整PASS且资源/停机/清理/释放齐。

当前 pending：**全部报告收齐后的一次同04同WT最终H闭包/镜像绑定、独立E GO及S2b exit**。Owner明确采用06 fresh三档功能/容量，06结果不作正式性能依据；t4按独立审核具体保守bound（最终M≥18678133632B、464后无其他业务/reader/规则/控制/算法变更）及Owner DC33决议沿用82完整PASS，不冒称新32GiB档t4物理峰值已实测。旧82 t3FAIL、4f calFAIL与既有失败证据全部保留，a10临时64/16/M48完整t3校准PASS仅供定档依据。后文各时刻“待Owner/未执行”均为当时历史状态，以本段和最新追加记录为准。

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


### 00:37Z：1de真实Submit容量前提失败，停止后续档位

CT108新项目 `s2b-e-t4-1de3fa4084` 首Preview已在00:30:30.430Z成功（operation wall58.34s），证明前次metadata-only错收费修正覆盖实际路径；随后Submit `op-c0146af9fb33f230e59afd8c` 的 `prepare_import` attempt1于00:30:34.690Z FAILED，首个effect前无checkpoint、无repository operation，diagnostic `RESOURCE_LIMIT_EXCEEDED / operation memory reservation exceeded`。journey00:30:36.861Z exit1，driver00:30:43.580Z exit1，正常stop保本E容器/卷/network/busy。

本次资源证据齐全/独立resource verdict PASS只表示边界取证通过，不是功能通过：单未重启worker `6db383022a82`、N1/M8589934592/envelope12884901888/reserve4294967296；memory.max12884901888，memory.peak662650880，OOM与oom_kill0，normalstop exit0，结束1de/clean。peak仍只是失败前缀cgroup生命周期值，不能据此宣称M8足够或实际完整worker峰值。证据前缀 `artifacts/s2b-e-t4-1de3fa4084/`：journey.log SHA `293d682d6d4efbc38a981cbb4b3c14e3d02b2e32ebb1b861c0e1a9d28437ac56`，result.json SHA `5e904cd7dc6d47a9d574a2b313d8b166b0ac3b8e0a7a6c5d8bdde58f616751fe`，worker资源SHA `2d69976f583ea171d5137f8dc4dcf061a61e41d4cae83bc1b47b50d7bce96383`。

只读DB与JSON metadata核：Submit step仅prepare_import失败，无后续effect。canonical table closure312表、初始parent故全changed；冻结canonicalization manifest SHA `0dc2f6f1c7c5f1ed33c08f248dd655fc2eb9ccb0c2d22d5c3fbed7cdc681ef9d`/216641B，table-set closure SHA `09eb1e9f140aef15f20399800f51a10c29d363088791fff5fde1d267eeee9b30`/73481B，READY closure SHA `3f7f7e3c9068c8ff8b2dc9512e644b45b427bfa4a0a198e29061b671a7690f7a`/493619B。`import_publication._reserve_submit_python_rows` 后的typed images/indexes/adaptive lists确实真实消费；不能按Preview单侧规则跳过。312表已知row-term下界8335221376B，加package-replay固定2650800128B为 **10986021504B > M8**，尚未计非负Arrow.nbytes×32。device_st单项3666670336B；按冻结顺序累计下界到该表已10682437056B，但确切触发的table/当前used未持久化，不能把数学下界当现场确切拒绝点。已知canonical mapping62330728B、reader metadata17724160B；其他retained/临时重开峰值未完整观测。

只读metadata `dc80-submit-budget-metadata-01.json` SHA `fcf5321f929676cf0df2f062c8018dcfd5d7f8a34d8ba9e27bf5d82cba02e92c`；step/diagnostic/ref摘要 `dc80-submit-step-readonly-01.json` SHA `3ee384a569bd4f715f685841dca10c8115fa8667ca4aa68265bcee3140b67b97`。首只读摘要命令在JSON序列化BLOB时报TypeError，读取mode=ro，无DB或输出写入；原工具stderr转录 `dc80-control-readonly-01-command-error.txt` SHA `c601819ccf1fbafcfdbe56209a833a584e6b4bd672db6402154191bec8f68eb2`。按DC68一次明确修正为BLOB仅大小/SHA后的 `dc80-control-readonly-02.json` actual0，SHA `628166f612af5359b1d6b8abf362681cfacdedc7a9f0fb0163103763c0ce3fc3`。无Rust/runtime/行迭代或operation重跑。现存IPC的Arrow buffer只读统计待独立核，不为求完整上限建立新框架。

05同H fresh t1自然收束：00:32:21.126Z journey0、00:32:28.432Z driver0、resources完整/同worker/normalstop0/ownedcleanup/release/HEADclean全真。`artifacts/s2b-e-t1-1de3fa4084/journey.log` SHA `5aa942a20ed275d5e49d42070d4d57a69d21344bff79852865201513b766a938`，result.json SHA `0a0fc66fee749fea0ddf50fc37b3d4b9db0ed6844e2d15ec1facdd122e440bbd`。按t4真实失败约定不接t2/t3。

root已知且暂停后续真实运行/RS。24GiB envelope/8GiB reserve/M16仅可能的受限校准候选，尚无Owner执行决议，不承诺它解决完整旅程；不自行调整系数/M/输入。若Owner选该方案，settings固定值与上限、Compose mem_limit/四Env、显式CLI M、外置driver资源判定及对应断言/owning决议均需同步。Compose属于所有包COMMON Git输入，因此新候选最终六包均需实际run与本机当前HEAD容器门禁，不借旧source。性能W1/W2/W3及完整t4仍未知/未通过。


00:38:01–02Z，经独立源码/call审核后执行一次有界现IPC buffer统计：外置脚本 `/home/dev/gdds-test-tmp/s2b-e-submit-arrow-metadata.py` SHA `4a28a1e8bcd99634f2524fa3369f9ac5284ed146057c4cd76fedeaac0e4132c5`，固定1de/clean/精确owner、受控wrapper lock-check与native137检查后，用本E现锁定解释器/Arrow25读取。仅 mmap→IPC get_batch→按真实descriptor列select→nbytes，等于production选列后的logical_size_bytes；无标量行迭代、runtime、Rust、重建或旅程重跑。312表logicalArrow合计59223003B，×32=1895136096B；row reservations合计10230357472B，加package2650800128B为12881157600B=11.99651286GiB；再计已知mapping62330728B及reader metadata17724160B，已知约12.07106978GiB。相对M16的剩余为4218656696B=3.92893022GiB，**不是4.22GiB**；JSON/其他retained、临时重开及后续阶段峰值仍未知，不能承诺完整旅程通过。结果 `dc80-submit-arrow-buffer-metadata-01.json` SHA `9cf81e8950e31de789d4c329901dd35af828043165dfa86fe648b19f812036c4`；外置日志同名`.log` SHA `b25b617bf4290416953850f011e8b6ed11601845d5a836ffd220bb9f06623f59`，实际exit0。root已预批在证据独立核齐后保两代E stopped全部资源/镜像/输入，仅精确owner与全机idle/Hclean成立时释放本次busy；截至此记录尚未执行该释放。


### 00:51Z：独立临时容量校准准备（不是最终profile）

04固定1de backend-only已于00:39:38Z自然whole runner0/driver0，主体3177 passed、serial57 passed，结束Hclean/idle并释放。`artifacts/s2b-e-gate-1de3fa40/backend-authority-01/authoritative-runner.log` SHA `269cfeb0b9ba5639a04ddf272f3ca73fb52c4af4ca5939fc53514efe33dfb797`；原日志起始JSON逐字提取的backend-source-manifest.json SHA `4120a28e79f175f1be684af57fadc9ee516e228dd564dc3bf5b197b9831e16c7`、total `5edbc2561f3424a362c784f33071a2f8b9bf4ccfcf57996b14c1818eaf56e1f6`；Compose provenance SHA `a86dc5ec2d1d4ea9653054c472932b4e0aa5806851004698ffc77f23d4fa42dc`。RS按root在容量决策前暂停，不把此backend结果作为t4容量通过。

CT108本次Submit失败/统计证据已由审核者核齐，00:44:14–15Z按root预批核全机idle、1de clean、精确ownmarker并列出两代各3 stopped containers/各3卷/网络，**仅移除本次busy**。`artifacts/s2b-e-t4-1de3fa4084/dc80-preserved-postflight-release.log` SHA `b6ddd77cabadfee4140ea46887c693374c285d72df62f6dae57b877521dd2de1`，exit0。新保留容器worker `6db383022a82`、backend `6855e0a60851`、RS `e32524a1878a`，网络 `a8cc272cffcb s2b-e-t4-1de3fa4084_default`，三个项目卷仍为backend-artifacts/backend-control/repository-service-data；旧7c同样保留。无down/rm/prune，原冻结资源不动。

Owner改为先一次宽裕完整校准，暂停24/8/16提案。root批准临时Hcal `4f808c111b9b8bf8e1673f1bf9b76b1823b7c31b`，local独立detached WT `/home/dev/gdds-p6-e-calibration-wt`，task ref `refs/codex/s2b-e/calibration/<full4f>`、bundle SHA `727702ce51a11614551f649bf2432a5363541bf8c31268ba49ff6304cdd29cf8`（实际已具备1de为prerequisite）。仅4路径：settings固定64GiB envelope/16GiB reserve/M上限48GiB、Compose worker硬限68719476736及M51539607552/reserve17179869184/N1；必要profile断言；既有bind_kernel_execution在scope关闭前finally记录operation/step/attempt、used/high_water/stage_admissions。诊断自身异常不替换真实ack/exception，无新observer/采样/控制机制，租约/GC/系数保持。此临时日志不进最终main。

high_water是每claimed execution/step的真实charged预约峰值；按operation仅取各step最大值，不把它们相加当共存。stage temporary_limit（例如parser/codec available）是准入上限，不能据max该字段定最终M。cgroup memory.peak与host VmHWM均为fresh worker生命周期累计（前者含pagecache/helpers，后者为主进程RSS KiB），不伪称每operation独立峰值。现已知Submit12.07GiB支持宽裕校准，但v2/后续路径上界未知，不能保证M48完整通过；64GiB硬限在实读96GiB CT108上留32GiB给其他服务/OS，仅是headroom而非他们的硬预约。

06复用本E自有implWT固定cal4f、actualpathdeps/native137/clean核合后，于00:49:29–32Z backend Ruff0/mypy5000与worker_resources/backend_settings/worker_lifecycle三module `-n0 -q` **30 passed**。`artifacts/s2b-e-calibration-4f808c11/calibration-focused.log` SHA `988cfcfb3b06af19d78f42ea785d9e8d6ebd4fd23ddcb198c8ada7d0542781b8`；source SHA `cfa20878d7010027a73f3fed1a17ab4ce86890e588c8daabcfccbed6046e468a`、另callenv SHA `7a76d299981ddb934b6f927c28cb3a71d0a79da7ac56ba67a5c4c2900fa9927c`。00:50:16Z核idle/own/calclean释放0，release SHA `f69ac7801f6b581a75b6657dca4b2c9a7d6e9b8541e0e98458b9d36383cc8796`。这不是04正式runner/carried来源。

CT108于00:50:32Z现场自取cal准备锁，新专有WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-calibration`（旧t4WT保1de），source0 SHA `601949b15aadc9ca6e261a43d66112874d184d3828aced0a204eeaf8f292af16`；另call HEAD/clean/legacy/四Rust工具0 SHA `e2d7a65658ae7745c75cbc04b9be45e6e37f2f2b66d8e1ae292c4c6d8d426bfa`。新offline backend venv/native与currentRS本机build准备中，无复制环境。base同节点immutable ID d363b45…与先前完整config/19DiffIDs证明相等，审核认可复用，不重复save大归档。

临时driver `/tmp/s2b-e-t4-calibration-driver.py` SHA `d44a347a81dd19b0bf02773818275a36bc0dccca1774ceeeb0bb7544bda6fab8`已审，保原286失败保留/正常stop规则，使用新WT、新project `s2b-e-cal-t4-<cal10>`、显式N1/M48/硬64/reserve16。取现保存worker日志静态对应claim→finally scope identities；必需counter/stage或VmHWM/cgroup缺失不清现场。只一次fresh full，无from-step/resume；任何真实正确性/租约/资源故障或缺必需观测均保现场停报，不自动增档/重试。临时不跑全六包，最终profile定后才做最终必要门禁。


00:52:15Z CT108 cal新环境准备actual0（source `601949b1…`/独立源 `e2d7a656…`不重复）：`artifacts/s2b-e-calibration-prepare-4f808c11/environment-01/prepare.log` SHA `a55689d30dcd2219d9d7169f7114c6ca7a85df6c1d15e68311d994a096f157bc`，新backend venv的四pathdeps全部本calWT、native137匹配、五base在位、当前cal RS本机offline build、八包INPUTS_VALID。另call独立env0 SHA `6c8d7cea94b41c995ef6ba0d38c298c2fd5bc6d65eb171c1f6f238b57d7324f4`，00:52:41Z核own/idle/calclean释放准备占用0，release SHA `d41482275586a53b9b0ed4a379b065a48adf61c8912413e87dfcc3bac29a435d`。

随后原已审d44a driver实际SHA匹配，00:52:41.337Z新project `s2b-e-cal-t4-4f808c111b`现场重新原子取锁并启动一次fresh full t4，硬64/M48/reserve16/N1，证据目录 `artifacts/s2b-e-cal-t4-4f808c111b/`。首Preview已成功、进入v1 Submit；审核者只读现worker日志确认3个Preview scope的finally记录齐：materialize_inputs highwater3803370110B（stage1259）、assemble_preview291755426B（stage314）、publish_preview53136194B（stage0），M均48，长stage行JSON完整。此仅证明观测接线和已完成前缀，不是完整校准PASS/最终M选择；当前保持自然运行，不改timeout/信号/输入。


### 01:32Z：校准History失败与FD诊断停止边界

临时4f校准已完成v1/v2路径及验证，但History `op-a872c285b33728563c769bbd` 的materialize_inputs失败。01:11:52.751Z journey1，reason `t4 History compare did not succeed, diagnostic=OPERATION.PURE_RECOMPUTE_FAILED`；01:11:59.524Z driver1，正常stop且保第三代cal containers/volumes/network/busy。原worker trace为真实C materialize→RepoRef._with_artifacts→publish_canonical_tables→C.lookup→ControlDbUnitOfWork连接的 `PRAGMA journal_mode=WAL` 抛 `sqlite3.OperationalError: unable to open database file`。不是已确认的M/lease问题，不改expected、不重跑，不把scope异常当资源不足继续增M。

cal证据前缀 `artifacts/s2b-e-cal-t4-4f808c111b/`：journey.log SHA `8ae6e7e43e26c5fd7f28c5ab92ed22217126e873c02e3a036c667b61bbffbb3f`，result.json SHA `4875de8815ba41969efe8d0b4f1d6c8214f3e1990f07293bcb172fd14bde3ea0`，worker `08833c79a594-after-stop.log` SHA `550850f090cccc3694370fc72d0a4267d312dc3d1cad5e3d70ecdaa3147e9072`。同worker/64硬限/48M/16reserve、normalstop0、cgroup/RSS字段齐：memory.peak6999605248B/max68719476736B，OOM事件0；VmHWM6682916KiB，均为失败前缀worker生命周期累计，不是每operation独立峰值或完整t4峰值。

另有临时collector纯解析缺陷：`docker logs --timestamps`在长JSON分片中插入ISO timestamp，原driver scope_count0/evidencefalse，原journey1/driver1与result **不改写**。经root/reviewer允许，仅对原已保存worker日志的counter JSON窄去32处Docker时间戳，离线恢复17实际counter记录、16唯一scope（await同attempt重复记录保留），覆盖17claim事件/16唯一scope。新 `scope-recovered-from-original-log-01.json` SHA `963cdd821b64c4051d5dc505f43d5a1a9e7f587480f9e922060683a094207b76`；格式诊断 `scope-collector-format-diagnostic-01.json` SHA `a5c3424312c8b0b6dc7344a454366c4f0b3024025dc8b26f0897f2ffa61aa46a`。无运行或观测重采集。

| 实际operation（按执行顺序） | 状态 | 各step charged highwater最大值/B |
| --- | --- | --- |
| Preview op-cf16baba… | SUCCEEDED | 3803370110 |
| Submit op-d3bf7372… | SUCCEEDED | 13070921208 |
| Preview op-79ce1f07… | SUCCEEDED | 6093784234 |
| Preview op-cab82510… | SUCCEEDED | 10997340796 |
| Submit op-7f839dc3… | SUCCEEDED | 8694034114 |
| History op-a872c285… | FAILED materialize_inputs | 331156230 |

上述最大值取每operation各step之最大，不相加；stage temporary_limit不是实耗。已执行前缀最大charged13070921208B，History后续比较/发布未覆盖，不能由此保证M16完整旅程。History失败scope有1019条canonical-ipc-inspect，接近1024只作FD压力线索。Control DB文件/父目录仍在、root644/755、空间/inode充足；UoW已有显式close，未证明SQLite连接泄漏或跨scope泄漏。

原worker已停，标准残留OCI spec路径不存在、containerd moby container列表为空，HostConfig.Ulimits=null；**原worker RLIMIT未知**，daemon limits不作为原测证据。经root/review准许，同原immutableimage `sha256:790b938e4ccb62433dc84225724b03382e51f01aaf6bd1a5b7e0eab5ac250361`、相同Memory64/Swap128/defaultUlimits/User空的新短命只读无网络/无挂载probe，在01:24:14–15Z输出RLIMIT_NOFILE `[1024,524288]`，仅同profile推断。`nofile-profile-probe-01/probe.log` SHA `f8c7647b3073180aa9a6126f4b2b176440eee75fbd188813244e05685c0ba073`，filteredinspect SHA `1eb0f1fcadab63a33bd7544f3854d8c84971fa0085b1ee14ca6f733597ea6123`；保存logs/inspect后仅移除此probe。

06 Arrow25两行小IPC平台诊断实际0：FD baseline5→map6→`source.close()`且buffer仍借用时回5、原FD已关闭；删除source后相同buffer地址/hash、Arrow读取已知值仍成立，所有借用释放后仍5。未复制payload替代mapping。`artifacts/s2b-e-arrow-fd-probe-01.json` SHA `50db37a3506e01d5fb3425e45c0a471097c9e9073a49df48a6ba15712068e596`，该目录 `probe.log` SHA `e5c88c7ae6acafca95418cad0df0bdf67d32048c6da4502ce0b5dd5ecb10040f`；准备环境日志SHA `6d33cd93df811d1d4cb1837c4f0ccb97459bc2a89b8c41bf6366da689f492e0f`。此支持标准Arrow提前关闭源FD而保映射的候选修法，但尚不是整个C故障复现/修复证明。

③真实LocalStore/C/SQLite两组312小表诊断**尚未完成**，不得称已证实FD根因。首脚本 e8c2c804…误从contracts import compare_schema_digest，在任何fixture/object前ImportError；原log `canonical-reproduction.log` SHA `2987c17279a51bb72521ba0b657b7e076a4ef3e1ba9b5e08298effb3bd288d3a`。按DC68一次明确修正的 be766600…只改public export和新out，01:30:45–50Z实际成功seed312 Store/SQLite fixture后，C factory位于seed scope外，被正确拒绝 `business Arrow work requires an operation kernel context`；尚未设RLIMIT或执行C双312。`canonical-reproduction-fixed.log` SHA `f67e1dbbba93550f01f47cbd4c7aa23df5a641b2e113711a7c6b08b48e268e0f`。实施与审核都漏核此调用上下文，现已按DC68停止，不第三稿/不产品改/不建History副本。临时fixture已自动清理，日志保留，交root处理恢复边界。

CT108 01:29:15–16Z核cal4f clean、wholeidle、精确ownmarker并列三代各3 stopped/各3卷/网络，**仅释放cal busy**，`dc80-preserved-postflight-release.log` SHA `ae9cec35483ce0813f737fcff2a5092d86b7bfea3e5fdfa720231ff8f546deec`。第三代worker08833c79a594/backend4e67cc926187/RS31eea9da0064，网络0802e1720545，三卷均保留；旧7c/1de同样保留。06 01:32:06Z核4f clean/idle/精确owner释放0，`artifacts/s2b-e-arrow-fd-probe-01/release.log` SHA `4805176fd9e55678484acc2bab12a9abed8825384cb4333e0af3e884a67515a2`。无活动E占用，原冻结资源均不动。

root已给后续有条件方向：仅在③证实/最小store候选修复focused与源码clear后，允许把本E cal冷停三卷/secrets/state复制到新项目，现CLI `--from-step history`对副本做DC64局部补验；不得直接恢复原项目、重Submit或新建恢复框架。该局部结果不称完整cal；当前尚未创建副本或实施产品修复。main最终12/4/8保持，独立4f的64/16/48与临时日志不合main。


### 02:01Z：Owner批准第三稿后真实复现与最小FD修复

Owner明确批准已审第三稿继续。06于01:39:08Z现场原子取占用，固定cal4f/clean、实际E解释器/native137/锁核0（`artifacts/s2b-e-canonical-fd-third-01/independent-environment.log` SHA `a813cca8fa8340f6d0211a044e58a6394148ec15747796f3b42dee8960843f73`）。01:39:18–46Z真实C/LocalStore/SQLite两组312小表、子进程soft1024/hard524288的第三稿实际完成诊断0：FD5→第一C组317→第一publication629→第二C组941→第二publication lookup395前1023，然后出现与History相同C.lookup→SQLite WAL `unable to open database file`。退出operation scope后FD回5，支持scope内映射源FD持有超过该profile上限，不是跨scopeSQLite连接泄漏。原worker RLIMIT仍未知；1024/524288依据同image/profile probe，边界不改。

原故障复现JSON `artifacts/s2b-e-canonical-fd-reproduction-03.json` SHA `1ea099cf4b3e1e7e8a047061e6023f270e20363c30eddcb810a6490aa542f984`；外置日志 `artifacts/s2b-e-canonical-fd-third-01/reproduction.log` SHA `6c6aa8618f7f4832993dafdf70fd4596c8b812d0fb4660ca95ebf7e52bc8bf8d`。原前两次准备失败不改、不用诊断0冒充产品PASS。

main产品修复d6仅2路径：LocalArtifactStore.open_buffer在同一readonly mapping的SHA校验成功后 `source.close()`，随后仍yield原强引用buffer，原finally、取消/完整性路径和预算释放owner不变；无copy/reopen/ulimit/reader-handoff修改。单一owner测试在96真实canonical readers仍借用且全部IPC可读时，证明无artifact源FD留开。main resource profile12/4/8不变。

06固定d6，source实际0（SHA `0931933df64b2dd93a5727861d840c15248bb9c78286cad2d8609420b622dcd2`）后另call四actual modules/directurls/native137/main12/4/8核0（SHA `81288f0056bf14afa4b3a505c9c5f18992191cfdcfbe0e9e5ab7a6c8fba7b8c5`）。01:44:52–01:45:30Z Ruff0/mypy5000、`tests/test_canonical_table_store.py tests/test_workspace_artifact_store.py tests/test_repository_ref_materialization_protocol.py tests/test_snapshot_materialization_business.py -n0 -q` **57 passed**；再完全相同fixture/两312/1024限制正向对照，C_loaded/publication两组及全部lookup/退出scope FD均5，两个commit完成、无异常。`artifacts/s2b-e-fd-fix-d6c88caf/fd-focused.log` SHA `210a2b2cf6729a852af73b29412bee5e14f69fdc3e788bdad9d048ede6996cff`；正向JSON `artifacts/s2b-e-canonical-fd-fixed-success-01.json` SHA `f84193ea0420c966bc9b0b3eece9f84ac0c4f6792ec38cbbfc4368d9230a8b19`。独立源码/结果审核clear。01:47:28Z核clean/idle/精确owner后释放06，release SHA `0642cc82fc5bc3221b541af718da4ef148f404c6c4dea78e3e56c422987c27ed`。

将d6两路径原样cherry到独立cal4f得到 `1f9df50a5c01173b82febc3a74b01bae549b1bb0`；两产品blob与main d6相同，剩余cal资源/临时日志补丁与4f相同，独立核清。不因等价再跑57项或临时六包。

CT108新专有WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-history-fd` 固定1f9，原4f WT/资源不动。task ref `refs/codex/s2b-e/calibration-fd/<full1f9>`，bundle SHA `dc337c763ee7e9520e7aaf89c733671c75bce232325f70ade944e34c1816cf34`，实际prerequisite4f在位。01:52:58Z source0 SHA `285b708ab2a694de016e31ca7d1fffc2e2fbf10f642a4788a41c38c5439902ba`，另call源/legacy/四工具0 SHA `f4ab0dfff40a39f3ab71094f527456fb688b110169093886a686803b26b8be7b`；新offline venv/实际四pathdeps/native137/current ownedRS/八包INPUTS_VALID准备0（01:53:34Z，SHA `be7d1d4f1748b55ddf0d7a1a65414c3e48ec5224593eb5f2c050184115a49d17`），01:59:04Z另call独立env0 SHA `20f010131dbf138f611b013da26063221602f8cadce0cff377586dc6d551bea4`。日志位于 `artifacts/s2b-e-history-fd-prepare-1f9df50a/`。当前持此有效prepare owner等待具体driver审，尚未copy/up。

后续仅DC64 History冷拷副本；源state SHA `0b24994ef8334b55a9b94fe9dbb2201c2d2b784d5e34ba30ee0ccb8340753d80`（18keys含_stack=17成功业务step），源repository61b78312-9aef-48ba-8aa1-a024f92c1bfd，v1/v2 commits8bge6neeo2mrg8fmem4uj5257ldrhchg/cdtvk5eutkiu8k8fkonh858q8d6va9l2。源backend/RS WAL实读0B，普通mode=ro会生成derived SHM/空WAL的事实如实保留，不删除或回填旧hash；后续先核stopped/WAL0再immutable只读，整卷包含现sidecar复制并按复制时bytes/mode/uidgid核。现CLI不负责resume build/up；外置仅当前candidate build和bareup，禁止start_three_container_stack的teardown/seed。新project新History key，原source/state不改。时序日志保原timed，另存无timestamps原worker log供counter解析；新worker ready后固定身份，局部峰值与原失败校准各scope最大值分列，不拼成一条完整worker峰值。


### 02:09Z：修复后History独立冷拷局部验证通过

已审driver `/tmp/s2b-e-history-copy-driver.py` SHA `560ff052cc316732cabaac978464040d5d07e91eb6d562afad6a6cba98163126`，远端同内容。沿既有prepare owner执行，02:05:03.678Z开始；新project `s2b-e-history-fd-1f9df50a5c`，新WT固定1f9且全程clean。仅从全stopped原cal三卷和state/secrets冷拷，按复制时实际bytes/mode/uidgid/fingerprint核相同；源state仍 `0b24994e…`、源两Submit/commit/scope身份和旧History失败均保留。没有重Submit、seed或修改原三代卷。当前候选本机offline build后保存三镜像IDs/RS revision/source labels，并逐container核对应Image相同；bare up后核两个真实commit的312表typed catalog、ready固定worker身份后才调用现CLI `--from-step history`。复制前17成功业务step仅复用。

History新operation `op-5ad5b9ab937f699652bd2af1`（与旧失败op不同）02:07:26.894Z开始，02:09:17.249Z SUCCEEDED，operation_wall110.355s；公共History record_count168、bundle/surface digest及composite unchanged等既有正确性断言通过。journey0；driver02:09:25.327Z exit0，resource_evidence_complete/calibration_scope_evidence_complete/worker_status_ok均true，无必需缺项。worker `aef38a6d79ba` StartedAt02:05:24.234Z，整个局部验证同Id/StartedAt且RestartCount0；正常stop退出0、无OOM。随后仅清副本containers/三卷/network并释放本owner，原三代各3 stopped containers/各3卷及网络保留。独立审核已核结果与现场。

仅解析一份保存的无timestamps原worker log，3个claim与3个counter逐身份齐（各attempt1）；保timed原log另存，未使用旧脆弱长JSON时间戳解析，未重采样：

| 本次History step | charged highwater/B | scope关闭前used/B | stage数 |
| --- | ---: | ---: | ---: |
| materialize_inputs | 398673952 | 398673952 | 1248 |
| assemble_comparison | 11218037646 | 11217201256 | 626 |
| publish_result | 3761894 | 2925504 | 0 |

本次History最大charged为11218037646B；与原cal已成功前缀的最大charged13070921208B分别保留，不相加成共存或完整worker峰值。原cal失败前缀worker cgroup peak6999605248B、VmHWM6682916KiB；新副本worker局部生命周期cgroup peak263307264B、VmHWM423704KiB，memory.max68719476736B，memory.events所有项0。两个worker分别启动、卷cache/映射与生命周期不同；cgroup charge和RSS为不同指标，不能拼接为一次修复后fresh全旅程峰值，也不由此宣告最终M16/profile通过。stage temporary_limit依然是准入可用上限而非实际消耗。

证据节点CT108，目录 `/home/dev/gdds-test-tmp/artifacts/s2b-e-history-fd-1f9df50a5c/`：

| 证据 | SHA256 |
| --- | --- |
| `journey.log` | `81bc78ced9bd8979dec25b9b48c32647f0733620bac15c62a96995d2343f39ca` |
| `result.json` | `9f85607d419adb7a7e954633d30cfd1778e7378613a899a876cf370b8b449a02` |
| `aef38a6d79ba-resources.json` | `bba5880eba229592cf159ca5581bf12c7a6af1b6401cf2e8e16de305b5638507` |
| `aef38a6d79ba-after-stop-untimed.log` | `37f1bba3f2ff4c9b8c388ba181a6ad39ce1a7ffdd221bbf8e507e2d0f28c9b47` |
| `aef38a6d79ba-after-stop.log` | `3c36c2dcabc5ef7849c1ac960aa963f1205dfc76343231233f7bc220d78a3969` |
| `built-images.json` | `682f7c18e3d0b8fba4d24488641414f0a584e259bec7580e0e05ece627b3191c` |
| `container-image-bindings.json` | `3ee9304c682fcd2d3c155b0fbabac2d5d830c4b1a7739a20f3230121e7726c73` |
| `clone-ready-and-exact-commits.log` | `87648a2f70d971358b4e517fe913d8e94bc8d652fb0c243a9b3a88afc2122d4e` |

此结果是DC64 History_only_on_cold_copy，通过最小FD修复后补齐原故障路径的正确性与预约记录；原cal journey1/driver1与scope原collector evidencefalse不改。当前各E节点无占用；04 gate WT和全部原证据保留。等待Owner最终profile决定后再冻结实际最终候选/闭包与相应门禁，不在此次局部PASS后自动接全门禁或完整旅程。


### 02:19Z：最终A资源档与实际最终验收启动

Owner明确选择24GiB envelope/8GiB reserve/显式M16GiB，N1/单active；main `82c4251b6cf944526c80a5e9bfe707bc57ab5087` 仅改settings三常数、Compose硬限与三资源Env、worker资源owner的超上限负例/最终profile正向断言。资源值精确为25769803776/8589934592/17179869184B；缺M仍拒启，既有控制/租约/GC/固定参数不变，不合临时logger。仍用较小显式M的小fixture合法，不为改profile重写其他业务expected或A–D向量。

06固定82，source实际0 SHA `95aa7b2faeb12bf2dab5f178db79e6d3fd3c7dbfb0f385a080c13fa03d962a29`，另call实际四module/directurls/native137/profile24-8-16/工具核0 SHA `0f13ca465796fb2ce6a43c47a904034c75fb4aca27cfa3f0c996ba2ee2de82a0`。02:16:47–50Z backend Ruff0/mypy5000、worker_kernel_resources/backend_settings/operation_worker_lifecycle三module `-n0 -q` **30 passed**，log `artifacts/s2b-e-final-profile-82c4251b/profile-focused.log` SHA `c7ed37603c6c2d117ec4350d6bc2ad071042b99909dbf14ad72d4de2b60641c8`；02:17:14Z exactowner/clean/wholeidle释放0 SHA `a6b17a74059414043ec669259ac2c19c22dc7285bc678b04c9d29faaedc2aedf`。

最终task ref `refs/codex/s2b-e/final-profile/<full82>`；完整history/no-prerequisites bundle SHA `39cc3944eb410ec0ca14a6636b99f11fd8416a6808f7562ff69f7915208df04c`。04/05/CT108均记录实际root previous2c79与各E WT previous1de，再bundle verify0/fetch本ref/检出固定82；source实际0后另call核HEAD/clean/legacy/四Rust工具，再env实际0后独立实际pathdeps/native/HEAD/镜像身份核。各节点existing venv均原地自有，无复制；base/19DiffIDs与锁身份不变、RS候选镜像在各节点本机offline build。05/CT108现CLI --validate-inputs逐包核八输入，INPUTS_VALID；无重生成/普查。全部准备日志完整保留。

| 节点/证据前缀（均在 `/home/dev/gdds-test-tmp/artifacts/`） | source / 独立源 / env / 独立env SHA256 |
| --- | --- |
| 04 `s2b-e-gate-82c4251b/` | `ec9037e2a99fa83ff990291beaf191ab014aa471e13f51bdb977e11188c6731a` / `6d513231856ebad93ab0cdd431c6c268ed8efa5c72b8e6b30e78b37735c2d9a5` / `e8614e3f22d17bafc81c8a985cf5255a4bf13d21cbbbdc1bd576e8c26f3e4082` / `0d0f471927964621f9836f64b4a172320ac0a28d8cbea1efb248078695526bd8` |
| 05 `s2b-e-t1t3-prepare-82c4251b/` | `9ce2a15519c79a98f48e60a9b38ad86452fdf601b9b78b4b87474d92529ab4a4` / `f5b40a3cb371c717aff8c693c8e4c70488e4af26e914e76ab007a3481ac07cbc` / `5d415c4de707ff09b6a1cdc757286c3d85c2d469a6a10787bf76310ebfef8930` / `c11eb8b8a304424a5b35e414b44fe9e0ec8176674f854040a0003890062d6f9c` |
| CT108 `s2b-e-t4-prepare-82c4251b/` | `6a1bcc88c66312faae708f0832f31a136c820581e308f75f56e107588468a031` / `8e3407e13ef6ca43d024d8fca5782e776d7e9726ed48cbf01c246aa1d07388ba` / `462e6662714a722e05b9d72d0bcbbe4a406a87495aa70295eefe1bd2d9473893` / `bf354f01980cf6887c05b537ee6925775167d866524d7b67cfcf419c3f67dedb` |

04同E gateWT于02:19:09Z启动六包实际权威runner，显式selection rust/shared_kernel/repository_contracts/repository_client/backend/repository_service，jobs4/pytest4、serial-n0。由于Compose属于所有包COMMON Git输入，旧来源不能沿用；本次六包实际run，backend批次已覆盖Compose不另跑。实际driver `/tmp/s2b-e-six-authority-final-04.sh` SHA `20251be2960e77f3f93cbb5d95171609f091cafdd9c23541c4b467a614c3bc60`，日志 `six-package-authority-01/authoritative-runner.log`，当前运行中，尚未合格来源。

05/CT108于02:19:31Z独立准备释放0，SHA各为 `3a8cf2fa76110e5418af39e8eeab25aaa5679b4c6de2a3f03936ddbb86d07dc5` / `8fbb09c235c8827e278f21f01a8bee50d049996e522c31c6464ba0944ede8392`，随后fresh driver重新现场原子取锁。CT108 `/tmp/s2b-e-final-t4-driver.py` SHA `0ff03b35aca679ac18ba1ecc0f8ba5b94ffb45a6bdc680760b431aa46e1a4d45`；05 `/tmp/s2b-e-final-05-tier-driver.py` SHA `6053196a10fcfc69571d9df56ff2e0ad22c499f4a3b277cf6fcb5b8745992d24`。仅复用既有driver改最终24/8/16、新project与显式M16；去掉临时calcounter解析要求，保必需CG/RSS/同worker/正常stop/HEADclean与失败保现场。新project分别 `s2b-e-final-t4-82c4251b6c` 与 `s2b-e-final-t1-82c4251b6c`；fresh full无resume/from-step。05每档必须实际0+证据齐+cleanup/release才接下一档，真实失败停后续。所有原失败与冻结资源不动。


### 03:02Z：82完整门禁/三档PASS、t3真实容量拒绝与漏预约窄修

04最终82六包权威入口02:19:09–02:45:04Z，整次runner0/driver0，起止HEAD82/clean、原Hypothesis路径清理及cargo target清理完成，wholeidle/精确owner释放；E gateWT/环境/镜像保留至S2b退出。Rust fmt/clippy/test三步通过；shared243、contracts152、client161；backend3179主体+57serial；RS1744主体/1skip+207serial。没有以失败整次中的包作来源，也不为同次backend Compose再跑一轮。

来源V均为 `82c4251b6cf944526c80a5e9bfe707bc57ab5087`，同04 E gateWT；原日志 `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-82c4251b/six-package-authority-01/authoritative-runner.log` SHA `d1dffcd84595d3b7424374d2277fd6276c02a8efa7e38b2c70936021b8621a48`。Compose provenance `backend-compose-gate-provenance.json` SHA `112ddcc6ead0122d356b3bcbd281cc50a1783ad1a519b955c5dd0fecaf23e377`。六份 `<package>-source-manifest.json` 均在整次0之后从该原log起始JSON逐字提取（不是post-run重算），独立审核raw_equal=true：

| 包（本次均实际run） | 原起始total_digest | source文件SHA256 |
| --- | --- | --- |
| rust | `352a7fbca8b15ba56b764ac2430b62214c8517751736527fba214d1f7c4a5dca` | `97c2c5e90b5f336aa05b02adf02e470c9cd5645bd39b0bac3e31758d5a163b27` |
| shared_kernel | `9845e1f5d9dc558a5d2aef42e08c7e57c9f54d0f7e5eeb4d9eccde567e835046` | `846e98db90cfe94717d1b6e21e79cbdddbe8ca767152daf8a23b2c03ab5be1b5` |
| repository_contracts | `152bf331a99081d656f57a939eb16721639cbb1d1b4a31624d6151a8262fa72e` | `c4f8032b7e40cf3a5fb74fe133eea8474b91d4ffc1dc0a9ad0c52412f4f3c057` |
| repository_client | `54b277acbdfbb68ea34212d32d9fda4a8fcf79149ed262247cc3b4c9bcd4187e` | `4b550b87df511a3abee477fa82cca13d3366085c85eab7694cc084059bbc6ad3` |
| backend | `23dcc46ad4a910f6d9836c3527b2589dd834b8c9c3c5def8399d300972cb795c` | `10f8bb33cb0d32969730ceaeeb4706b640ea7e8411382c40bde5960324fd5b93` |
| repository_service | `7212abd7ab2ddf7b8697eb502bba7e579736d4eb359fd74e1fb064c9df127a15` | `2a101b4ab5ad6457d7bffd4a07ab63f30c555c2f58ce79017027ae98d8d87b10` |

按AGENTS提交前五包static要求，06另于02:24:15–18Z固定82/clean/actual E pathdeps，对shared_kernel/contracts/client/RS实际Ruff0+mypy34/15/26/200全部0；backend82/c7ed已实际通过，不重复。`artifacts/s2b-e-final-profile-82c4251b/four-python-static.log` SHA `31ab664f521b74b72e4aac0521119d1917f188b45598adef3e4c83c2c978e8f2`，本次核idle/ownmarker释放0。

82各档真实旅程均fresh full、显式N1/M16、currentHEAD本机offline build、无resume；05逐档资源/cleanup/release全齐后再下一档，原线实际冲突以有效marker为准。证据前缀均为所在节点 `/home/dev/gdds-test-tmp/artifacts/s2b-e-final-<tier>-82c4251b6c/`：

| 档/节点 | 实际终态 | journey.log SHA256 | result.json SHA256 |
| --- | --- | --- | --- |
| t1/05 | 02:23:14.623Z driver0/旅程0，资源/同worker/stop/cleanup/release全齐 | `3c37fc491d1bb3d1e0d9c9599e70040fc872531917ce177739cfbd3d8d2d97f2` | `27d573fffae8c6d8b0515523407f9438f6b7ed050465388de8bd3f1a821fd2cf` |
| t2/05 | 02:37:05.579Z driver0/旅程0，资源/同worker/stop/cleanup/release全齐 | `74113500b4c9165ca3e7181926aff5e89250c8d3ee32ad1f0c22971d205128ce` | `6ed3ffffb6dcd8ead1783bd51d6c067bf4eaa2d4e2f90f62697e6714b1085970` |
| t3/05 | 02:46:18.233Z driver1/旅程1，v2-preview assemble资源拒绝，保现场 | `948f27a15f7a6ff87fcf6cfb2c5b02298b005ee1c1fc5d25adf459a82a4f0a4c` | `78bde259fb8b02853075ddf5c4c1eee658670e35f40728e6ea99b0d6a124b888` |
| t4/CT108 | 02:40:39.561Z driver0/旅程0，完整同worker资源/stop/cleanup/release全齐 | `13ac186de8fa7774268a06b4a49f3fb95218b6319787fbfcb598fdf11d642fcc` | `004a026b4f33c2440e5902fb1651326a9471a57df6bd3fd5715f3abb2c4348da` |

完整t4 worker090f4608269b全旅程StartedAt/RestartCount核齐，memory.max25769803776B、cgroup生命周期peak6991069184B、VmHWM6684612KiB、events全0，normalstop0，无missing；它们不是M预约高水位或每operation独占峰值。原after-stop log SHA `9a765d034b804c2fbbb79861a4de30e34eff3def99a94905746e6c70d5e6629b`，lease_lost/RESOURCE_LIMIT_EXCEEDED/Traceback命中均0。单次t4/N1/M16既有JSON诊断：受理响应后首Preview到终态观测58.337s（completion58.359s、2s轮询/operation_terminal_result fallback），repeat62.351s、v2Preview94.545s；v1/v2Submit535.712/183.264s，History118.370s。此不是精确READY、正式W1/2×t4或30s达标证据；W1/W2正式任务仍按Owner计划，不将功能PASS当性能PASS。

**t3真实失败**：op-dffc6a0eee79886afcb6b859，materialize_inputs成功，assemble_preview attempt1正常ack `RESOURCE_LIMIT_EXCEEDED / operation memory reservation exceeded`；无Traceback/失租/容器OOM。保存的v2-modified-only双侧cp由192 baseline/193 modified构成，baseline实际53 materialized+139 summary-only、modified193 materialized；不能给无reader的summary-only侧加费。失败前缀CGpeak4373372928B、VmHWM4201560KiB、events全0。resource_verdict=PASS仅表示资源事实完整/配置/正常停机，业务journey1不能改称PASS。

只读证据：`dc80-step-diagnostic-01.json` SHA `43f37e9c7138fc7ae24952585ddb5f0754658cb9a20aabd58e1149a28820d23f`。初次pure metadata脚本误从unmaterialized descriptor取business_schema_digest，KeyError，失败log SHA `16d4bb2f87ee33f55a2171c5e6eedeab83429ce4713d9e64ba169bb3478b84ac`；已保存证据的纯只读解析/计算按DC68澄清不受一次重做上限，不代表业务失败获豁免。修后用已确认summary身份条件与actual materialized side过滤，193tasks的row+base严格lower17045901120B，距M仅133968064B；普通identity条件不确定者保守跳过，只减少lower。报告 `dc80-comparison-row-lower-02.json` SHA `60ab606f271b9a35c73ef5fa6954eb370bf22aa39063b1275b6d4defaa84756c`，log SHA `437645773a1ca116ac4fbba9c08f3d9eb1688801c427a15a9012bc0615c84a5c`，实际0。

仅补当前真实selected device_st的一个既有IPC，沿旧已审mmap/get_batch/select/nbytes方法，不标量迭代/运行消费者；43110行43列logical16646188B，×64=1065356032B，加row+base后lower18111257152B **已超过M17179869184B，差931387968B**，其他Arrow/live预约仍省略，不能叫完整upper或RSS。`dc80-comparison-one-ipc-lower-01.json` SHA `18be24ff08a342f40539863729945214168778e0390a59f73c7f339d65f21b0d`，log SHA `b850b0acce2b41729c3d1405b3d706b16dafe68e50509e24c7be3713e752f897`，实际0。审核者独立复核该lower与真实双侧/ordered行消费，未自动缩系数或加M。

05在02:55:18Z核全机idle、82clean、精确ownmarker，**仅释放本E标记**以让实际冲突方继续；`dc80-preserved-postflight-release.log` SHA `2647713da378e4e631b6e47f64e1b52cb44f1f022e0808bce25bf6f69f3af80a`。本E项目s2b-e-final-t3-82c4251b6c的workerdfdade767d51/backendf0fcd56da1a8/RS35da190af1d6均stopped，三卷backend-artifacts/backend-control/repository-service-data与网络c37d84d81b02、镜像/输入/state/secrets/全部证据保留，无down/rm/prune。其worker原log SHA `a727732be13c65af648eb20ec9200cfc9400891172c6790e570382a3cd21238f`、resource JSON SHA `0dc5580e8bcfd3a62bab76fee5e9ecfea6161ad8d700db34b7bc9dd478511ff5`。

**同owner漏预约修正464**：审核还确认BROWSE_ONLY/SNAPSHOT_ONLY的COLUMNS_ADDED分支真实读取两侧共享列并构造Counter，但旧upper恒skip这两role。root按DC80批准最小修正，standard.py仅在双descriptor且同existing_schema helper确定COLUMNS_ADDED时落入既有双侧公式；其余metadata-only/单侧照旧skip，普通/ordered identity收费不变，不改系数/业务结果/golden/M。现role内容变化真实owner保留，新增role×schemaadded的4参数资源行为用1/256行真实fixture证明增长前低M拒绝、metadata费用不随行数增长、rows/stream未在拒绝前调用。

06固定464，source0 SHA `1b888897a385d6fe739a57f68d1febcb8dd406407289a2a728186b74c65581c0`、另call actual E四pathdeps/native137/profile24-8-16/tool核0 SHA `b1ff94cbef696dea275cd4999af6f5ee99cb451be73c35dd86197298c9e83525`。03:00:22–24Z Ruff0/mypy5000，rule_roles/standard/ordered三module+原pair_memory_admission节点 **93 passed**，`artifacts/s2b-e-non-record-budget-46428913/non-record-focused.log` SHA `eeec41b911ba77eea540eae763a8504b2e6623f8c661e6d54ad3f040ae64a004`；03:01:13Z ownidle/464clean释放0，release SHA `cd8534919179c7b272004e144334c4f61f8510e4674ea63426d1e00c2261a57d`。源码/结果独立核清；该修正补漏计项，更不能把t3 M16失败改记PASS。

隔离cal准备候选 `a10dec894e39013dc02bc7100a27da69ca01040b`，专有localWT clean，ref `refs/codex/s2b-e/t3-calibration/<fullSHA>`。464两路径原样cherry到1f9，standard blob `5bb7b55bda6f4295b246546657ab772523da3389`、role-test `7037318c8c0882d7b1a16f309fce8befe713fdcd` 与main精确相同；其余vnext严格只4个原cal路径，且逐blob=1f9（kernel_execution临时finally日志/settings/resourceowner断言/Compose），仍64/16/M48/N1，无新observer或系数变化。root指定CT108作为临时容量诊断节点；Owner待决是扩展剩余t3校准与重新定档，而非再次申请节点。

计划只在05现场空闲取本任务占用时，把自有stopped三卷+实际state/secrets标准冷归档并按bytes/mode/uidgid核，经获准LAN传CT108；新project/current cal镜像本机offline build+bare up，禁止teardown/seed。源state SHA `443732447e1f4ae12df80b576e44cf51ab17c7a80d8d24aeb0ab80710ad733b2`，14keys含_stack+13成功业务step，v2workspace/upload已存，v2-preview无成功state。source与clone在启动前各一次immutable核workspace OPEN、optimistic_version匹配saved upload、current_upload_revision_id/generation/BaselineHead与prefix一致；不修源state/版本，newkey/newop不能复用旧FAILED。现CLI `--tier t3 --scope full --from-step v2-preview --keep-stack --project-name s2b-e-cal-t3-rest-a10dec894e --kernel-threads 1 --kernel-memory-budget-bytes 51539607552` 仅补v2Preview→v2Submit/read/approve→History，不重V1Submit。只取各scope charged/stage与新copyworker局部生命周期CG/RSS；原t3仍FAIL，局部不冒完整fresh PASS。**截至此记录未复制05/未启动新cal，未做最终Hcompare或额外完整runner。**


### 03:14Z：按既有授权接续t3剩余校准准备

root重核Owner此前“先增大预算再按测量结果定配置”的持续授权，本次仅补原宽裕校准遗漏的t3剩余路径，复用64/16/M48/N1；**不是Owner新批复，也不再次申请临时节点**。按新固定a10继续可审准备/执行，main仍464的24/8/M16，不提前定最终档，不跑新六包或重V1。

CT108于03:06:58Z闲时原子取prepare owner，新WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-t3-calibration` 固定a10，ref `refs/codex/s2b-e/t3-calibration/<fulla10>`、bundle SHA `2441e2dbc859f165146c0f7e17bbd6c9ce98f7e29aab46d23122d77f540b008c`，actual prerequisite1f9在位、verify0。source0 SHA `3318b3dfff8460c516d57f35ae8dbe617a991d1ad038e88c93ca0968e6318a74`；另call HEAD/clean/legacy/四Rust工具0 SHA `ca90a2f825d8c43a3d3e8788df87f91a4913ae4d3ee08d8ea5c1317e631256ba`；03:07:45Z offline新venv/actual四pathdeps/native137/currentRS本机build/INPUTS_VALID环境0 SHA `7bb84a8c90959c7c47ab2cfd3e80cdd691e192ff80c132f8ef246f6c4b86fc0a`；03:08:47Z另call独立env0 SHA `3593af436ed156fc298f6d44eee366219c893de4c7e93d350e005ae957f981e0`。全部在 `artifacts/s2b-e-t3-calibration-prepare-a10dec89/`。

03:09:46Z准备后核ownidle/a10clean释放CT108，release SHA `324a989a46c4ffc3447367121a42b8d5fb0bac71ee4cd47eaafb5c242f42604a`，保WT/venv/镜像/证据，不占节点等05。05在03:04:56Z由原线有效GC marker取得，故截至本记录未归档/复制/开cal副本；已向root报实际冲突，不抢占/预留。05 source saved v2-workspace是旧version7，v2-upload是version8/generation3；复制前按实际DB与upload8/currentID核，不误用旧workspace7。一次性归档与局部driver已从既有已审560模板最小适配并交独立审核，原源/13prefix/新key与权限/镜像/计数/失败保全边界不扩为产品框架。


### 03:20Z：避免等待05，改为一次fresh完整t3宽裕校准

05原线GC持续有效占用。root与独立审核核实后采用更小执行接线：CT108现输入/源码/env已齐，直接一次fresh完整t3，代价是多执行约8分钟成功前缀，但避免等待/跨节点冷恢复并取得同一worker完整峰值。停止冷归档/copy路线，相关draft仅在CT201 `/tmp`，未执行归档/未传源数据/未开副本；原05三卷/state/secrets完全保留。该改变仍沿Owner既有先宽裕测后定档授权，不是新Owner批复，不重其他档或runner，不改最终main档。

独立审核者在03:20:03Z释放其CT108短只读占用（release SHA `718870f829feb77281c7f1e53785423cec5ea7f913b655e7c74e39c8fa794921`），确认wholeidle/a10clean。最小fresh driver `/tmp/s2b-e-t3-fresh-calibration-driver.py` SHA `5f724b12e2c604204b971bdabe4c2b874f2525d1791252fb12d927e59c69b91f` 相对已审d44只改tier/newWT/newproject、采用已验证untimed原worker log解析，并分记实际counter记录数与unique scope数；原timed log保留，64硬限/16reserve/M48/N1、同worker/CG/RSS/正常stop/失败现场保全不变，无from-step/恢复逻辑。已独立核无实质边界阻碍。

CT108于 **03:20:23.298329Z** 现场重新原子取得本cal owner，project `s2b-e-cal-t3-full-a10dec894e`，journey原log header03:20:23.457631Z/HEADa10；证据 `/home/dev/gdds-test-tmp/artifacts/s2b-e-cal-t3-full-a10dec894e/`。完整fresh当前自然运行，尚无结果，不改timeout/M/输入。临时scope日志用于真实charged预约高水位（不取stage ceiling），新worker CG/RSS为该完整校准生命周期；仍不冒最终生产档或正式性能PASS。main保464/24-8-M16，原82 t3FAIL及旧4f校准FAIL不改。


### 03:43Z：a10 fresh完整t3宽裕校准通过

同一次CT108 fresh full t3于03:42:33.292Z自然收束，journey0/driver0；起止a10clean不变，18实际counter记录/18unique scope逐claim覆盖且全attempt1，calibration_scope_evidence_complete/resource_evidence_complete/worker_status_ok全true，无missing。worker40fd63d49e97全生命周期同StartedAt/Restart0，正常stop退出0、OOM事件0；只清本project containers/三卷/network并释放owner，原05失败卷及CT108三代旧失败资源不动。完整校准是临时64/16/M48档的功能/资源事实，不替代最终生产档门禁。

每scope原始high_water/used-before-close/全部stage_admissions保存在原无timestamps worker log。只从该原log作一次只读JSON汇总，18条记录和18unique均保留，无Docker时间戳修复或重采样。逐scope完整表见 `scope-summary-from-original-untimed-log-01.json`；各operation取其scope最大值，不相加：

| 实际operation（按执行顺序） | 最大scope | charged highwater/B |
| --- | --- | ---: |
| V1 Preview op-2970a27327e3af148f017319 | materialize_inputs | 3798888734 |
| V1 Submit op-d20a4c38587ee7dc4b806b93 | prepare_import | 9078047792 |
| repeat V1 Preview op-3a9ed8fdeee6b41bc357554b | materialize_inputs | 3798888734 |
| V2 Preview op-e486d548daf53988760c4623 | assemble_preview | 21281126550 |
| V2 Submit op-b45d3bda80812ad88ab2933b | prepare_import | 9839426576 |
| History op-3d5632fe698b1eeaf66d1ccc | assemble_comparison | 21375346635 |

全程最大真实charged预约为 **21375346635B = 19.9073428614GiB**，在History assemble_comparison（387 stages）；不是max stage temporary_limit。完整同worker cgroup memory.max68719476736B、memory.peak4765663232B=4.43836975GiB，VmHWM4415476KiB=4.21092606GiB、memory.events全0。两个指标各自为完整生命周期累计，CG包含startup/helpers/pagecache，RSS为主进程；不把charged当RSS，也不拼到旧cal/独立History worker上。原无timestampslog的lease_lost/RESOURCE_LIMIT_EXCEEDED/Traceback均0。

证据CT108目录 `/home/dev/gdds-test-tmp/artifacts/s2b-e-cal-t3-full-a10dec894e/`：

| 原证据/汇总 | SHA256 |
| --- | --- |
| `journey.log` | `c51afa1ff606e923c0149b8ebfb5bd45d784c18297af1c650b87c28763f1470f` |
| `result.json` | `f2f5fb26cfc110048bc73d0db2f34ba82eae7d22d2083dafd10fb5191a8b8b9f` |
| `40fd63d49e97-after-stop-untimed.log` | `382d1d2fe02101944fe1c4789fe0b20cc1d1b3bc28b32901e3049738d616ddee` |
| `scope-summary-from-original-untimed-log-01.json`（仅原log解析） | `28e2ae76f6b7f6215571a3965875def2b85c7c1dcbc238ffed42dee90a58e3cf` |

若Owner选M24，相对本次最大charged余4394457141B=4.0926571386GiB，约高于实测20.5585%；这只是定档所需数字，不先承诺该生产档所有新门禁/未来输入通过。main仍464/24-8-M16、已知t3原FAIL不改，未把a10临时profile/logger合main，未启动新正式runner/最终Hcompare。06扩容已由root在03:40:36Z核96GiB/16CPU并03:40:47Z释放维护标记，后续可按原用途现场取用；没有迁移/重启本次CT108校准。


### 04:44Z：最终32/8/M24候选与必要验收已启动

Owner确定32GiB envelope / 8GiB reserve / 显式M24GiB（25769803776B）、N1/单active，生产候选 `a6876d560050285321fd9f62942d590a03f35d64` 严格只调整settings、Compose、既有worker资源owner断言三路径；拒绝缺M与M24+1、固定单active及控制预算保持。464漏预约与d6 mmap FD修复保留；不引入cal logger/系数变更。独立源码审核CLEAR。

06现有impl WT在04:37:28–04:40:20Z固定a687完成source/独立实际绑定/必要定向及五包静态：native build input137d499975f3c104ae9c3268b9e12befb2817ba1、实际四pathdeps均本E WT，profile32/8/24；资源/settings/lifecycle三module30PASS，backend Ruff/mypy500及其余四包Ruff/default mypy均0。随后核clean/wholeidle/精确ownmarker释放，保WT/环境/target/日志。证据目录06 `/home/dev/gdds-test-tmp/artifacts/s2b-e-final-m24-a6876d56/`：

| 步骤 | SHA256 |
| --- | --- |
| source-01/source-prepare.log | `9c728fffb4915f09777a0270a4f67c4c88414b0a1546559e98c4cf6d6d62a6bf` |
| independent-environment.log | `ca24de4b6de06df54ae81ea535a0bb644533e857fd56f700a1a3f2efae83cb2f` |
| profile-focused-and-five-static.log | `8af309bc680872fb21d0e6981fde0109881b744199f65d2661265ec90e075d97` |
| release.log | `2725673aba5d80e5b08c3ac3fd52d95b05d3e4c4757c4b524db360cb3a1388d9` |

最终源码用full-history bundle SHA `15737087c6958fd561d0ad37efc555c54267fe6ccc8867753723130eee9bc133`、唯一ref `refs/codex/s2b-e/final-m24/<fulla687>` 分别同步04/06，记录实际remote previous HEAD，不改root main/冻结refs。04保原gate WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate`，06为独立新WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-final-real` 建新venv，禁止复制其他WT环境。两节点source与另call独立HEADclean/legacy/四Rust工具核于04:40:31Z实际0。

04环境04:44:12Z实际0（prepare SHA `15403c0938f913fd4d6a1f3c0ffd3a067fca7d35fc10fbc08d23ca5bd2fe5d24`），独立五包实际依赖binding/native/镜像核04:44:31Z实际0（SHA `fc885006681bb83f09028c7298631dd266cd77d52374daba93cd9c915bc4e641`）。04六包权威于**04:44:47Z**实际启动，日志 `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-m24-a6876d56/six-package-authority-01/authoritative-runner.log`，全部6包实际run而非carry，jobs4/pytest4、serial-n0、offline/native重装/本机Compose build。进行中，不提前认来源V或PASS。

06 final fresh driver `/tmp/s2b-e-m24-06-tier-driver.py` SHA `223988b801e882ee2622541d9fe4ff37c1021634f55b2ebe4337f178bcdab93d`，参数 `<fulla687> t1|t2|t3`，各新project `s2b-e-m24-<tier>-a6876d5600`。沿已有fresh full/keep-stack边界，显式N1/M24、实际32硬限/8reserve、同worker与CG/RSS/正常stop事实；main无cal logger，driver不要求临时counter。各档实际成功且证据/cleanup/release全齐才下一档；失败保本E停止容器/卷/网络/证据与busy，不自动重跑。

06独立新real环境04:45:35Z实际0（prepare SHA `63c8336ab6e31d46a3db80ee8f5769bf3f6b8f26561b66e035f08212d1a8013d`），另call实际四模块/directurls/新venv/native137/32-8-24/四Rust工具核04:45:45Z实际0（SHA `9cd321447daa9759ae5f506452fe5d2efc8dcf64a52829be6d35943f38d13329`），04:45:55Z精确ownmarker/wholeidle/a687clean释放prepare（SHA `ee1e353216541e7c6941545d135c09fe4cf189c3da68604989cb8a74ee60fb5d`）。同节点配置/19DiffID既有证明由未变immutable本机backend-base ID复核，RS/client锁label与实际本机build/source13cb/a687核齐；无LAN补缺/公网或代理。随后06新project `s2b-e-m24-t1-a6876d5600` fresh full t1已实际开始，证据 `/home/dev/gdds-test-tmp/artifacts/s2b-e-m24-t1-a6876d5600/`；此时尚无结果。


### 04:50Z：06最终t1完整通过，t2接续

06 final t1 fresh full于04:46:00.698–04:49:55.583Z实际journey0/driver0，起止a687clean，project `s2b-e-m24-t1-a6876d5600`。worker8de3335b6ef0同StartedAt/Restart0、N1/M24/32GiB硬限/8reserve，memory.peak283107328B、VmHWM264192KiB、必需events全0、normalstop0；所有logs完整/资源证据/同worker事实通过，只清本project containers/三卷/network并释放owner。原输入/保留失败资源不动。原journey SHA `f2dbf26ba4b4270e8d344daa5e63ba1335b1f9e47e19c920714b8bff51f5acd2`，result SHA `598691b35f600c3dacde90630767ada25a91662a92932faa872930e61baa7088`，证据06 `/home/dev/gdds-test-tmp/artifacts/s2b-e-m24-t1-a6876d5600/`。独立审核已逐项复算SHA及command/inspect/resources成立。

06 backend dependency-base既有完整本节点身份证据：D `/home/dev/gdds-test-tmp/artifacts/s2b-d-93678f8439/base-identity.txt` SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`，含config b5b542…与全部19DiffIDs、IDENTITY_MATCH；同组base-current.tar SHA `95f6dc2ccf6ecd9fc352540a8b249bfa978d6bb2f5338fd5b936dfeb68b2076c`保留。关联D原log `/home/dev/gdds-test-tmp/logs/s2b-d-container-93678f8439.log` SHA `daa9d38d0d0e96f5f06b86bf776992fa1bbfcc22066e4325754e2076ace55227`明确当时本机immutableID d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff，当前同节点复核ID相等。D整组后来fixture失败不改变先前独立镜像身份核事实，也不改称整组PASS；无跨节点inspectID等价或新save。

同节点现场重新原子取用，t2新project `s2b-e-m24-t2-a6876d5600` 已接续fresh完整旅程。04 backend并行主体3183PASS，串行仍自然执行；目前不提前认六包整次来源。


### 05:04Z：06最终t2完整通过，fresh t3接续

06 final t2于04:50:11.425–05:04:10.365Z实际journey0/driver0，固定a687clean，project `s2b-e-m24-t2-a6876d5600`。worker234e2ce1f33b完整同身份/Restart0、32/8/M24/N1；cgroup max34359738368B/peak2566234112B、VmHWM2415676KiB、必需events全0，normalstop0、全部logs与资源事实齐、ownedcleanup与busy释放齐。journey SHA `88666462a8e53b7c4de13df3d7130e1bd9b8d9e06d3c4d0ac3d3b7349c80ca59`，result SHA `51a4b6f85a8a7f75e24330017466283da5657d26c3973a087c36a0921e1c9852`，均在06 `/home/dev/gdds-test-tmp/artifacts/s2b-e-m24-t2-a6876d5600/`。t2成功/清理不当作t3预约；重新核现场并原子取用后，同finaldriver独立project `s2b-e-m24-t3-a6876d5600` 已fresh启动，无resume/from-step，等待自然终态。04此时backend3183+57通过，RS串行运行中，整次尚未认合格来源。


### 05:11Z：最终04六包权威与当次Compose整次通过

04 hostname gw-dms-test-04，在保留gate WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate` 固定clean a687于04:44:47–05:11:23Z运行权威入口；Rust fmt/all-target clippy/workspace tests均0，shared_kernel243、contracts152、client161、backend3183并行+57串行、RS1744并行+1skip与207串行通过。整次runner0/driver0，全部五包Hypothesis路径及外置Cargotarget由runner自身清理，核HEADclean/无running容器/Dolt/cargo/8000及精确ownmarker后释放。WT、五venv、本机镜像/缓存/证据保留到S2b exit；无单独重复Compose。

合格实际来源V均直接引用a687本次实际运行，而非旧82或链式carry。证据04 `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-m24-a6876d56/six-package-authority-01/`：原log SHA `9faaf9d80a2b3f249616e58880156155b177fb6d763d4b83acd0b4b375b85985`，当次 backend-compose-gate-provenance.json SHA `ac28f04e1b2d36aca3b4a5243f477cb577db4ae7ba807042818bbfbfd57b513f`。只在whole0后用纯原log解析逐字提取六starting JSON到 `original-starting-manifests/`，非post-run重算；head/worktree_head/package/clean字段逐项断言：

| 包（均实际run） | 原starting total_digest | starting JSON SHA256 |
| --- | --- | --- |
| rust | `ec9549bb1980f6894c75a37b6ddcd094f183993078e54ed124e16c8176c59b79` | `429960a9aad2a12e81c9d8936d3eddb5727516949de3b57f463ce09697950d3c` |
| shared_kernel | `b2aa9cb246423a2dc982a8851d375d187c9c83a4adcd57e47a370eae10955612` | `7ac6a85b629007f47ae360824d64d6ae98e4512c5095854a3b32f4a7be702a7e` |
| repository_contracts | `72f77cf22ee074184887adab578d7e353c623fa250f112635edac7b264704650` | `0dd24001e0bb7855618b5f6dc94b9310ca0fb3dd18c9aa9b3bf8b5138f924724` |
| repository_client | `36c310182dbea4686acfff425876a394b888b50cdebef07c414c5942c2bed378` | `2eba3a5248a65cdc07c021121b78e8d74003d4595016329c36e9d1fc99f68879` |
| backend | `8d0b73df9f15d899265a4d57f24cac4dd87d24b5ca9f00c3b01992b1feff8645` | `fd42a472b44437c49939f926aa8c256fbcdb611a21e038ca457fe79a07c6c568` |
| repository_service | `80203cb5ac294234e4192bc2c6842cbde5d853cec012d6884f54fa15bb0a5960` | `095405d818abe31a7034c0648aa9589eca45fc2fa83eee247633afcbbf5f25b9` |

当次provenance最后实际ordered-bisect本机容器镜像为backend `sha256:34130ae839ba946d07bee991f2a7e44b01f1f1f33b9416aba6b13c8c14644e3e`、worker `sha256:692cc893fdbbc4e5c5b336679334b3561c6e0ed1a0b36cf20e42e3d661334298`、RS `sha256:cbc547e4b01d8aba6d5fd00e6df896975df4c1deb4f962f4fcf8105d3bb81e15`；RS label build-input-revision=a687、source-tree13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2。本机ID只作同节点状态记录，不作跨节点等价。最终H仍待所有报告收齐后固定，再在此同WT按正式路径六包closure compare/RS身份绑定一次；现不提前carry最终H。


### 05:27Z：最终06 fresh t3完整通过，实际验收收齐

06 hostname gw-dms-06、独立new real WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-final-real` 固定a687，于05:04:56.516–05:27:08.830Z完成本轮fresh full t3，journey0/driver0。首次Preview/Submit、重复Preview及no-rewrite读回、v2Preview/Submit/读回/approve与History全部成功。v2Preview于05:15:08Z成功，v2Submit05:23:46Z成功，History05:27:01Z成功；原82/M16在v2Preview的容量失败保持FAIL，不据新PASS改写旧证据。

同一个workerbc4356c1ec0d从首次业务观测至末端身份/StartedAt保持、Restart0，N1/单active、显式M25769803776B、envelope/cgroup memory.max34359738368B、reserve8589934592B。完整生命周期memory.peak **4761649152B**，主进程VmHWM **4419688KiB**，必需memory.events含oom/oom_kill全0；normalstop退出0/OOMKilledfalse。全部logs/CG/RSS/同worker/HEADclean事实齐，无missing；资源verdict PASS与业务journey0同时成立。本轮main没有临时scope logger，最终M支持来自真实完整成功路径，不伪造最终charged高水位。CG包含startup/helpers/pagecache，RSS为主进程生命周期，不是每operation峰值，也不与旧校准/局部History相加。

证据06 `/home/dev/gdds-test-tmp/artifacts/s2b-e-m24-t3-a6876d5600/`：

| 原证据 | SHA256 |
| --- | --- |
| journey.log | `0b7059ad2ca0bacdda2cab76beec002d0e56d2cc5512780d451c20bf9ac4fa31` |
| result.json | `32a028d51f9fc7c4d3ad073c395b643ee18939f767201e3110d416cc9925b78d` |
| bc4356c1ec0d-resources.json | `eb7ef0bf551ebaaf9b0b49aaf09278d80ce9507f5571154d41b35822fc4889d5` |

原worker after-stop log中lease_lost/RESOURCE_LIMIT_EXCEEDED/Traceback命中均0。成功后只清本project containers/三卷/network并释放精确owner，另call实际busy不存在/无running容器0；WT、新venv、native target/本机镜像/全部证据保留，不动原05失败资源、CT108三代失败资源、原线冻结材料。06三个tier均在该同节点各自fresh完成，按Owner本轮96GiB节点用途授权，不作为正式性能测量。

**t4沿用的精确边界**：Owner已确认本轮t4不重复完整旅程；直接引用82/CT108完整fresh成功log `13ac186de8fa7774268a06b4a49f3fb95218b6319787fbfcb598fdf11d642fcc` / result `004a026b4f33c2440e5902fb1651326a9471a57df6bd3fd5715f3abb2c4348da`。审核者对同输入closed metadata的新增nonrecord费用保守上界1498264448B，报告CT108 `artifacts/s2b-e-review-t4-nonrecord-delta-01/fee-upper.json` SHA `6cb5fba0be807de08130e9c18491ced3b54572b0c03e80a221d8c356ee2331d9`；最保守条件Mfinal≥旧已过M16+新增上界=18678133632B，以保持未改native调用remaining cap不低于原82。本次M25769803776满足，464后仅profile/既有断言变化，N1/单active/reader/规则/业务输出/控制/算法均不变；FD与新增准入不改输出。旧t4 CG/RSS仅属于24/8/M16实际profile，不记成32/8/M24的t4实测。此为明确DC33范围沿用，不以文件更大/tier编号猜测容量。

本节必要实际证据现已齐：06最终profile30focused+五包静态、04六包实际整次/当次Compose、06三个fresh完整真实tier；t4按上述确切来源/条件沿用。产品V=a687，最终H仍由协调者在报告/审核资料收齐后固定。唯一比较稿 `/tmp/s2b-e-final-H-closure-04.sh` SHA `6f4c91831f28196a5dc97363dda854f2f3fed332a835c43182b3f708602cba62` 已只读独审，参数H留待固定；复用同04原gateWT、qualified a687原6starting JSON、本轮RS tag/实际venv/native/逐包Hyp不存在路径，RS helper重算identity对label与原provenance。**截至此记录未同步H/未执行最终比较、未签E GO、未tag/push或办理S2b exit。**

性能待补保持既有归属：W1/W2正式输入/2×t4预热与多次/30秒目标不从功能旅程PASS推导，W1本轮仅保旧单次t4受理响应后至观测的初诊，W2性能最迟S6；W3自S3，原冻结基准W4 lease_lost仍OPEN。最终生产gate/发布与本次阶段证据区分，不能冒已完成。
