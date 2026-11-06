# S2b E 独立审核

状态：**源码审核清楚（固定 7c02397139）；最终证据待齐，不是 E GO 或 S2b exit**。本节按 DC86 新建独立审核角色，模型 GPT-6.1-Sol/max。只修改本审核文档，不修改产品或测试；明确小问题直接交实施者修正后复审，真实设计/验收冲突交设计协调者。无新增角色、推送或改写被引用提交。

## 范围与固定基线

审核起点为 clean main `16e1089a8659f87b0c6585543174c6722f876d86`。CT201 审核 detached worktree `/home/dev/gdds-test-tmp/s2b-e-review` 固定该 SHA，已建 `legacy` 链接；只读源码与证据，不在开发机运行测试、编译或 lint。每组仅在实施者给出固定已提交候选后更新审核 worktree。

最终累计审核范围为 `p6-s2a-exit`（`53b676a6298d408ccda3a85ee73c7ea223a2311a`）至最终候选。复用 A–D 各独立交付及其准确证据范围，E 审实际差异和最终证据：A 产品 `db7767ffbb` / 审核 `83b927207a`；B 产品 `b820321c1e` / 审核 `0dc93c09a9`；C 产品 `0048040af5` / handoff `7cd2b548c8` / 审核 `e9bef6efe8`；D 产品 `93678f8439ec1393d496182f16ae5049b220242f` / handoff `abfe7cb66b` / 审核 `78411aa40b`。D 至本起点的 `vnext/` 无差异，不把 D 的 06 focused 组合、局部 materialize 校准或失败 runner 内单项通过升级为 04 权威来源。

已读 AGENTS、Testing Conventions、比例化保障政策、ADR0012、DC70/72/76–88、执行计划、S2b 总 kickoff、E kickoff、mapping 与 D handoff/review。核心边界遵循当前 owning Contract；A 表示能力不扩大 B 业务白名单，同 euid 仍为既定单一信任域。

## 一次性审核矩阵

| 维度 | 核对范围与实际后果 | 最小验证与 owner |
| --- | --- | --- |
| 真实消费者与唯一批量路径 | 上传 FULL 两侧、Preview baseline、History exact commit、RepositoryRef 两 policy、pair/identity/ordered、export/replay、Submit T1/PREPARED，以及 `real_dump_journey → real_dump_census` 和仍继续使用的工具入口；残留旧 caller 会在删除后失效或形成双路径 | 按实际 import/call graph，固定组做原应用/capability owner focused；删除六个旧 parser 模块及六条 temporary UNREACHABLE，清旧 bulk materialize/projection/hash、仅服务旧算法的 helper/mock/probe；不新增假 import 或 baseline |
| 独立语义预期 | mapping bytes、业务摘要、诊断、结构过滤、keyed/keyless/ordered 预期不能随新 actual 自证 | 保既有 Contract/golden/已验证旧值和 Shared Kernel vectors；删除旧 oracle 前把必要动态预期固定。metadata/选表/恢复策略的合法 fixture 可用真实 Rust/C 构造，但不称为 hash 独立证明，也不为每个 fixture 再建 oracle |
| 保留职责 | 误删仍用 Python IO/规则/编排或外部格式会破坏真实业务消费者 | 保 XML/AST/composite、rules、small metadata/digest、MutationPlanning row-image 摘要、raw/client Parquet、SourcePackage、通用 row reader/DTO；每项按真实 caller 判断，不整文件盲删 |
| 冻结、恢复与资源控制 | E 差异不能破坏 exact commit、scope、内容身份、T1/PREPARED、StartArchive Head CAS、强引用/TTL；控制误分类或漏预算可污染 durable 状态或导致真实业务失败 | 复用 A–D 已验证 owning tests，只复核 E 差异；DC87 保 12 GiB/4 GiB reserve/显式 M8 GiB、N1/单 active；DC88 仅真实 PURE、effect 前、fresh lease/drain，保 checkpoint/保护/attempt/operator，cancel 优先、失租禁写 |
| 最终证据 | 不合格来源、旧 image 或局部旅程不能绑定最终候选 | 06 focused/Contract/五包静态及适用 Rust；04 最终权威 Rust 必覆盖，其他按同节点同 WT 的合格实际 V/逐包闭包判 run/carried；最终 image 当前重建或严格同 04 同 WT 等价。05 t1–t3、CT108 t4 既定 `real_dump_journey --scope full`，不以 capacity 或性能延期替代 |

必要节点窗口由设计协调者负责。CT108/05 已有可用条件但不作预约，执行前按现场有效占用取锁；最终必需证据仍未完成前不签 GO。所有测试节点沿离线缓存、clean committed WT、有效原子占用与日志规则；本审核默认只读实施者日志、manifest、source，不争抢其占用。

## 删除前预期固定核对

实施者外置脚本 `/tmp/s2b-e-freeze-reference.py` SHA `d97e8c9e36337bacdf506bf7e21f6e2d3912fea1f04589c0980e984cea3e0b60` 已只读核。typed SET/f32、wide 200×100、dropped JSON 三份 SQL 与起点 `test_business_kernel_native.py` 的既有用例一致。脚本仅调用旧 test helper 的 SQL materialize 与旧 canonical projection，采旧 raw/canonical 摘要，不调用新 Rust actual，不保采集器为长期 oracle。

06 `gw-dms-06` 的 `19:04:58–19:05:00Z` 日志起止 clean HEAD 均为 `16e1089a86`，lock-check 与 treechecker（`137d499975f3c104ae9c3268b9e12befb2817ba1`）通过，exit0。日志 `/home/dev/gdds-test-tmp/logs/s2b-e-freeze-reference-16e1089a86.log` SHA `4fe7de2ddf4cea018d86107bb46043436171d70f8889832993f58f0031e699af` 已独立读取并重算吻合。后续发现复制 venv 的 editable 路径仍指 D，故本采集的真实来源为 **D936 旧产品算法＋E16 的 test helper**，不称为 16 全链合格测试或闭包来源。driver SHA `92aef839cdff1b65aa20770c9ab20ce87764ca8b2aedf4c6c4e01beb18e3c9c1` 明确 `cd E/backend; PYTHONPATH=. .venv/bin/python <script>`，helper 来自 E16，产品 `.pth` 指 D936；D WT 独立核 clean。D936/16 的 `vnext` tree 同为 `17bd1c93cb5c3a6b7f8f6271a4088e62d3e3698a`，旧 projection/materialize/digest/parser blobs 已逐项核合。这些事实仅核实旧预期的数据来源，不把整次运行升级为 E 产品证据。

typed raw/canonical 同为 `sha256:f57c8813f99f9226ae5c0970e6619e801cbb013d6d20d7dd32fcba87ee4f7f71`；wide raw/canonical 同为 `sha256:c947ad6fccb65c36c067d38a761ca1049e0122c5f926413ba9f7c09e5dcc603a`；dropped raw `sha256:02fbd36483695eaf632a39a2d83877441b074c7587dd745d579cff4355c8aefd`、canonical `sha256:232a96c506247080963b4d39390ac5bf686238c8fb2edf0febcbdbeb0ae91905`。原日志保留、未反写预期或重做全套 oracle；新路径仍须实际对这些固定值验证。

## 当前容器记录

Current reviewed code HEAD: `7c023971397a8fba2c9e2aa86e9e7cbb9f088fe1`（相对 d0 仅测试 fixture/harness 迁移）。审核文档提交自身不触发重建；7c 改实际 Compose harness，按既定范围先 06 两个受影响 Compose 定向本机 build，最终 04 候选仍本机 build 及 runner 内 Compose，不为每步重复全 Compose。E 的 startup owner 接线与阶段退出边界不变。D 的 06 局部验证只作其原范围回归来源；当前 ff 的 04 实际 Compose 镜像已构建/运行，backend `sha256:d426a30b774abf2f1e56836130c0d6fb04fa44aa27b8dc395de02bb472d0c74c`、worker `sha256:e6bfc8bd5548ac844381db83d3b075b329dad0b6cef978d22d4da73721e7e5d2`，RS 本机 image `sha256:77dcda8e4a45afad911f797f0a7780734f0f285cdc0f80f60617338210d41aa0`、revision ff、source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`、build-input `c52e9fad62e14b016ed814d0799e08e6d97e82b3`。ff 整次 runner 失败，以上仅记录真实镜像与失败范围，不作最终 HEAD 合格容器来源。

本基线不宣称正式 carried 或 E 当前容器门禁通过。阶段最终候选必在 04 绑定合格权威/container 证据，04 WT 保留至 stage exit 合入；E 产品差异收敛后再精确记录是否触发重建及来源。

## 固定组审核记录

`d5dcc43b73cc7a4102a22a357a051094f762ec0d` 仅改测试/helper：移除 parser 双实现选择与纯 differential property suite；SQL golden 继续按原 Rust owner 的 code/table/byte offset 比较，原固定输入与预期文件未改；production Arrow reader 的 single-consumer/reopen/close 及 INSERT 列重排仍保留。旧 Python 私有 reader invalidation/EOF 探针随替代实现移除，对应 C/D 真实生命周期/control owner 仍为权威。typed/wide/dropped 摘要准确固定到上述旧值，未用新 actual 反写。本组无已确认语义 Finding；后组仍需移交 catalog 旧 extractor 的动态对照，并清其无真实 caller 的旧分支。

06 日志 `/home/dev/gdds-test-tmp/logs/s2b-e-reference-focused-d5dcc43b73.log` SHA `f81f3004ce75b29e62f671a4f44d43ec8ee4b9539d341c8f8f8f3b36b6c0797a` 已独立读取并重算（初稿转记少两位 `f8`，现按实物 64 hex 纠正）。`19:07:20–19:07:22Z` 起止 d5dcc，pytest 输出 203 PASS、exit0；同日志 Ruff 因 8 项 unused imports exit1，明确记 `ruff_exit=1 pytest_exit=0`。后续核旧 `.pth` 和 pytest shebang 仍指 D，**本 203 只保作诊断，不作为 E 候选通过证据**；当前新路径由正确环境的后续 focused 覆盖。busy owner 粗记 `19:05Z` 与实际采集起时差两秒；06 目录 birth time 独立实读为 `19:03:48.689387117Z`，早于 freeze。实施者保留原工具输出并在 handoff 说明/更正粗记，不重写原日志来消除此记录差异。

`2e77436c49` 已独立核 six parser 与精确 baseline、旧 SQL row fallback、`project.py/_ordered.py`、Repository row materialize/hash、旧 catalog extractor 和 replay-only 转换全部移除；保实际 `_digest` composite/raw Parquet 职责。新 fixture adapter 仅小型 metadata 和合法 rows→Arrow 构造，projection/hash 用真实 Rust，typed replay image 用现 Submit consumer；不作独立算法 oracle。bootstrap private init 精确 owner 从 operation_worker 替换至 compute_kernel，M/control 仍归 caller，无自动初始化或默认 M。仍有效 census/journey 改唯一新路径并要求显式 N/M；退役工具依赖闭包按 DC79 后续使用边界核，冻结资源未动。全 vnext caller 搜索仅余 runbook/源码注释历史文字，无旧实际 import/call；fixture golden 自 S2a 起未改。源码删除边界无已确认产品 Finding，fixture/API owner 移交仍需收敛。

## 环境修正及真实路径首轮失败

`efe5f3bc5408bd8e644a9958a344186b247d3ae5` 的 collection 失败为复制 E venv 仍绑定 D：四个 path dependency `.pth`、backend `direct_url.json` 与 pytest shebang 均独立读取确认。日志 `logs/s2b-e-cutover-focused-efe5f3bc54.log` SHA `0fe017348993738a60bde7d032f0c0c02816ae228666349b0aa6a84aa9f492a6`，pytest collection2/ruff1/mypy0，不作产品行为结果。按 DC68 只修一次 E 自有环境；旧 venv 移到 `/home/dev/gdds-test-tmp/s2b-e-venv-copied-invalid` 保留，不改 D WT/venv。

固定 `172807821ad9e1afcd1ae8979036f1b893146d0b` 的受控 offline sync 实际重建 E backend/compute 与三个 path packages、重装扩展并核 tree137d499，`19:18:51–19:19:06Z` exit0。setup driver SHA `b4e7ce5150b25fae9f177cc85f1143a75e1e4dd09199eb1265f08959895bbad9`，日志 `logs/s2b-e-setup-fixed-172807821a.log` SHA `5b5536037282a28748e37681bcdb8a2312f2352dc4fd7c4fce335b8dc619306b` 已核。后续 binding 日志 `logs/s2b-e-environment-binding-172807821a.log` SHA `ff6d81dd383cee649739f57a8b0e5764e501391cf8514a2364b6c19e7016f425` 明示 actual interpreter/sys.path/__file__/direct_urls 全来自 E；本审核又只读重核四 `.pth`/direct_urls 和 pytest shebang 均为 E 路径。

修正后 `19:19:52–19:19:59Z` 新 E 真实路径首次 focused 为 357 PASS / 34 FAIL、Ruff1/mypy1/pytest1。日志 `logs/s2b-e-cutover-focused-fixed-172807821a.log` SHA `ace74286b299711a1fcecbf1726e77852d9846f19d93719c57f84c09f717d181` 已独立读取并重算；这不是重复 setup 错，不称整组 PASS。共因为旧 API request/private probe 仍指向已删除入口、合法 C fixture 的 identity/PK nullable/wire shape 不齐、census 旧 SimpleNamespace fixture，以及少量静态错误，交实施者按真实 owner 定向修正。核心 fixed digest/catalog facts 未出现分歧。

close-failure 测试的 fake provider 将原 outer-session 关闭 fault 再注入了 C 内会话；真实 `HttpArrowRepositoryRefSession.close()` 仅置 closed，没有该内关闭 I/O fault 来源。本审核与实施者约定只将 fault 限 outer session、保原 warning/COMPLETE 断言，不扩 C 产品关闭协议或吞控制异常。rowless 测试旧将 business schema digest 填 canonical schema 字段，应修合法 fixture 并保持真实 C schema 校验；复合 PK nullable 应与合法 canonical catalog 一致。若修后仍有真实 consumer/hash/control 分歧，按产品 Finding 处理，不归入 fixture。

## 未决与结论

`60c5` 首次修正后的真实 focused 为 373 PASS / 2 FAIL，余下两项旧 projection API probe 直接抛 resolver 拒绝；日志 `logs/s2b-e-cutover-focused-60c5f05df1.log` SHA `f3345fb773e750d6d7d7fb8dc69c110adeeaab4e641571b65490688c264860d1` 保留。unclassified 已有 `test_table_rules_resolver::test_empty_rules_snapshot_is_unclassified`；RAW_PRIMARY_KEY 与 ignored column 冲突的唯一语义断言在 `314067ff72` 精简移到真实 resolver owner，直接检查拒绝，不复制旧 validator。

`0d4d4240fe03aab1b66b308ffa457799a623c939` 的 375 PASS、Ruff0/default mypy500通过，与额外工具 mypy 的命令准备失败分开记录；原日志 SHA `9956381afb8f29b09c6eea7d0b4a3966189049f0b8fc78a6dcbe1b5ece7e98c8`，不称整组 PASS。额外工具检查先用源码路径产生重复 module，后 `-m` 缺源码搜索 root 产生 import-untyped/继发 Any；实施者停止该步骤，未自行第三次尝试。本审核只读核建议的 `MYPYPATH=src ... uv-consume.sh -C vnext/backend run --no-sync mypy -m benchmarks.<四入口>`：wrapper cwd 为 backend，源 root 与模块身份明确，保 strict/既有 overrides、不增 ignore；协调者按 DC68 交 Owner 确认一次修正续做。该单项尚未通过。

本审核另发现 `scalar_encoding.encode_repository_row/value/EncodedRepositoryRow` 已仅由两份旧测试调用，协调者独立检索确认后在 f97/127c 窄删其旧转换及 sole probes；保 `map_repository_column/_declared_type_for` 的真实 catalog 元数据职责及 C/RS 往返 owner，未删除通用 RS/client row reader/DTO。`127c501b7c592e9a3dce33625af770be802ef40e` 五 Python 包 Ruff/mypy、实际 editable 路径与扩展 tree137 检查均通过，`19:31:43–19:31:52Z` exit0；日志 `logs/s2b-e-static-five-127c501b7c.log` SHA `ad466445efb413ee560d498b047b98c93926a87a78e0692cf57ef9d13a3da0ee` 已逐项独立读取并重算。

127c 后续 broad focused 为 799 PASS / 4 FAIL，serial 未接；日志 `logs/s2b-e-consumer-focused-127c501b7c.log` SHA `0c20aefeaba20d7830e32e974e8687558e5e008cf6a4bc4035257e41efa1aa10` 保留。失败为旧 raw Parquet fixture 被当 canonical、缺 repository scope、已退役的 RepositoryRef-Parquet cache 跳读 probe。7b 定向为 273 PASS / 3 fixture scope FAIL，日志 SHA `02224d3fbc55fe58978691a39d3ddb04f5d8634fdd2a8e55d235936a465402b5`，serial 未接。d0 仅修合法 fixture/显式 scope 并移除旧 cache probe，未让生产接受旧格式。

独立源码核 `row_layout_digest_of` 不含 table name，client Parquet/cache 的 layout+repository 身份与 canonical IPC 含 table name 的 business-schema 身份是不同用途；因此原 1 client artifact/4 bindings 预期保持，未按 actual 改成两个 artifact。d0 日志 `logs/s2b-e-consumer-scope-fixed-d0f5602d6f.log` SHA `ea84c4f1a16f53440dd28453e8ef90ad6e250879d5e11a5c03356270ca96a025` 已核：Ruff0/mypy500通过、replacement 7 PASS、之前未执行的 serial 3 PASS，exit0。以上按实际 SHA/范围使用，不拼成“d0 全包 runner 已过”。

**源码审核清楚，允许按固定候选开始最终取证。** d0 的 W1 型诊断输出仅将本就收集的 timing 拷入 `operation_timings`，不新增计时、轮询或 HTTP，原 dc32 不变。t4 单次诊断只称受理响应后至首次可读观测/终态代理，明示 2 秒轮询与 observation/fallback 来源，不称精确 READY 或正式 W1 PASS。正式 2×t4/W1 与 W2 按原时点收口，W3 自 S3；原 W4 lease 故障仍 OPEN。

## 04 首个合格权威来源与准备边界

04 新 E gate WT 为 `/home/dev/gdds-test-tmp/wt/p6-s2b-e-gate`，保留 S2a gate WT。三小包既有 S2a 来源到 d0 的 `COMMON_GIT_COMPONENTS` 已必异：闭包拥有整个 `vnext/scripts` 和 `vnext/deploy`，区间新增 `run-s2b-capacity-census.sh`、Compose 增加资源接线；`vnext/fixtures` 未改。因此后续五 Python 包均须实际运行，不将“方便全跑”作理由，也不为注定变化的共同 Git 组件占旧 WT 算 carry。

04 source prepare driver SHA `87ce24d81a381173327ceaab98bb4c451f14bcf2a482f641b694acb02b1a2981` 与 Rust-only driver SHA `cea9f91316a9ff2462f3004cf76fdc876beb73191f611dd31f6880ed9395c9bf` 已执行前独立读审：full SHA 唯一 bundle ref/摘要、拒覆盖 evidence directory、source 成功后另一次实际验证、再另 call 权威 runner、所有退出 footer、只匹配本 owner 且残留为空才释放。bundle SHA `215d1a49a77bad63b764781178af1d59c6406e75d559a94bd72bcb912027771d`。

实际节点 `gw-dms-test-04`，source `19:52:41–19:52:42Z` exit0，独立 HEAD/clean/legacy/四工具同 1.97.0 工具链与锁核对 `19:53:00Z` exit0。证据目录 `/home/dev/gdds-test-tmp/artifacts/s2b-e-gate-d0f5602d/`：`source-01/source-prepare.log` SHA `aa4613deba26e7d221af36f29492908cb5f20b8fa0e7b2e4901793d0010be0ec`；`source-01/independent-source-verification.log` SHA `65b65bacd7892b39f423b2b06db21279057e53676288089f583274ff62870ff5`，均已独立读取并重算。

**合格 Rust 实际来源 V 为 d0**：`GATEWAY_TEST_PACKAGES=rust ./vnext/scripts/run-tests.sh` 在 `19:53:12–19:54:00Z` 实际执行，起止 d0/clean，fmt0、all-target clippy0、workspace test0，整次 runner0、driver0；离线、jobs4、TMPDIR/target 外置，runner 退出清 cargo target。原始 `rust-01/authoritative-runner.log` SHA `6253a0e3000ef60456a5359d062ee3a6ef793be21292ecdd47f722ca3286abf9` 与其中 starting manifest 的 total `5dbb8a817e37bad59f5318d63592e405f2bb3dc3886b483bc329a05f77b540ea` 已独立核。source/final owner 内容 cmp 相等，`19:54:00Z` 释放；另只读核无 busy、运行容器、Dolt/Cargo，E gate WT 仍 d0/clean 并保留。后续最终 HEAD 的 Rust carry 仍须同此 04/WT/环境实际 compare，不在当前预先判 carry。

## 待续的最终证据

最终尚待：04 五 Python 权威 runner/最终镜像绑定、05 t1–t3 与 CT108 t4 fresh full，以及全 worker 资源事实；额外工具 mypy 已按下文获准续做并通过。CT108/05 条件窗口已协调，不再笼统以无窗口豁免 W1 型诊断。协调者已选现有 `--tier t4 --scope full --keep-stack --project-name <E新名>` 的外置取证，禁止 from-step/resume，不碰原线冻结资源。

CT201 `/tmp/s2b-e-t4-driver.py` 当前实物 SHA `286ef89e7ce83377165df4c4f1c62e6c408d07bf75da3e0075f0b8abbbb40299` 已独立执行前审，**仅准备、未运行 t4**。脚本持本 E node busy，先存全部 owned logs/filtered inspect，标准 PID/cgroup 一次读取 memory.max/peak/events；必需 oom/oom_kill 缺 key 不当 0，停止前核 12 GiB/N1/M8/reserve4、StartedAt/RestartCount、同 worker 与现 HEAD/clean，正常 SIGTERM 停止后再次留 logs/inspect。只有真实 journey0、资源/日志/正常 stop/身份前置齐才删本项目容器/卷/网络并释放。真实业务/租约或资源/evidence 失败则先正常 stop、保本 E 容器/卷/busy 交 DC80 主动诊断，不自动重跑、不覆盖原日志；异常停机不强杀。无监控服务、采样器或新持久状态机。

memory.peak 将如实为该 fresh cgroup 全生命周期（含 startup/pagecache/helper）事实，不外推 D 的 materialize `675241984 B` 到全 worker，不以 cgroup peak 冒充进程 RSS 或 M 硬上限。当前无未关闭源码 Finding，**E 最终证据 GO 尚未给出**。

Owner 随后明确批准工具 mypy 具体修正续做，已恢复同 E 两角色，未新建角色。主线 `a532a3bbf755198645b758f34b29f08cd89aab32` clean，d0 至该提交的 `vnext` 实差异为空；t4 driver 实物 SHA 仍为上述 286ef89e，未改变或运行。06 在重新取得本任务占用后，对 clean d0 运行已审 `MYPYPATH=src` 加四个 `-m benchmarks.*` 的原受控命令；`22:46:12–22:46:13Z` 实际 E 解释器/backend module 路径正确、4 个工具 mypy通过、exit0。日志 `/home/dev/gdds-test-tmp/logs/s2b-e-tool-mypy-approved-d0f5602d6f.log` SHA `aea3a32e91ee5e2391bc9d7983b9e9fd31a64a6fbee714d892fa4fa61d3cfe9a` 已独立读取并重算；另只读核 E `.pth`/mypy shebang、d0/clean 与占用已释放。该暂停项关闭，无产品/依赖/config/ignore 修改，允许继续当前具体最终 driver 的审核与既定取证，不重做旧 focused/oracle/Rust。旧节点空闲仅为历史现场，执行前仍查有效占用、输入和缓存。

## 续做后的实际准备及首轮门禁问题

04 在原 E gate WT、clean d0 上实际计算 Rust 闭包并与原合格来源比较，`changed_components=[]`、total 仍为 `5dbb8a817e37bad59f5318d63592e405f2bb3dc3886b483bc329a05f77b540ea`，不是凭路径或未改 Rust 文件推定沿用。五包环境新建/离线同步、native 强制重装及 tree137d499、逐包实际模块/direct URL 均为 E WT。dependency-base 的 config/全部 19 DiffID 与锁标签吻合；04 本机构建本任务 RS，revision 为 d0、source-tree 仍为 `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。`python-prepare-01/prepare.log`（22:55:01–22:57:00Z，exit0）SHA `7db3bd86e9c0a37a535dd2f33cef87b131d14c8bf207d3702099d54d2e90556d`；另 call 独立环境验证至 22:57:24Z、exit0，日志 SHA `dfac41a1578ee7756fa66fef1ef576118e11fcfbd2890b8ab86ec1dce01dbd6a`，均已独立读取并重算。之后才另 call 五 Python 权威入口，运行时未改 WT/镜像。

该次权威运行的 backend 主体实际为 20 FAIL / 3111 PASS / 8 collection ERROR，serial 另 2 collection ERROR；不是前置命令错误。已独立核原 trace 与只读失败 DB：模块级 `PREVIEW_RESULT` 在 autouse kernel scope 前调用真实 Rust；Submit UUID scope 使用默认 `repo-1` canonical fixture，Prepare 正确报 `STORAGE_PROJECTION_FAILED`；removed-tables helper 仍把 raw Parquet manifest 当 canonical IPC；live canonical identity 未传新必需 `committed_tables`。最小修正交现测试 owner：运行期构造合法 fixture、传真实 repository scope、真实 canonical IPC 与 C factory，保 fingerprint/idempotency、removal、await/effect/recovery、live roundtrip 业务断言，不放宽产品校验或加 fallback。运行仍由原入口自然收束，不提前重跑；整次非零时任何包内通过均不能作合格来源，真实旅程暂不启动。

CT108 `source-01` 在 fetch/建 WT/测试前因旧 bundle prerequisite `53b676a6…` 不存在失败。原日志 SHA `7e8971bb24986ae8482f69f616d21dc65ce828fb9f71b26feca050f28a3c1699` 保留；未修改原根 main，busy 已释放。协调者按 DC68 批准一次明确修正：以 actual remote previous `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3` 核祖先，新建任务 ref `refs/codex/s2b-e/t4-source/<d0完整SHA>` 与 bundle（SHA `0f732d7da982902b6a6d56008551d2843640bbda918122e739f43f42c4a2b721`）。source02 driver SHA `eaf95e9198bdec69484514ef4d7baa4f0aa30fd84560d64444ec9f2df0ec38a9` 已审；独立 remote list-heads/三 prerequisite/bundle verify 实际 exit0 后执行，23:02:46Z source02 实际 exit0。`source-02/source-prepare.log` SHA `505400d4ae19260d8cded92ff3bf448237f2fa6c5a4e4ea464c5e7fbc13680d2` 已读并核；后续仍按另 call 验证与 env 准备，不将 source 成功称为 t4 通过，也不启动真实旅程。

固定 `ff970567f875bbc2ae357db950084dc450f8d88d` 的 9 个 tests/support 差异已在审核 detached WT 独立审清：显式运行期 fixture 依赖现 operation kernel scope，idempotency 改 runtime module 访问避免 by-value 陈旧对象；canonical refs/payload/preview 贯穿真实 repository_id；removed-tables 在 seeded UUID 下构造真实 canonical IPC；live identity 接现真实 C factory 与独立 control DB。无产品源码、expected 或业务断言修改。06 独立 source/环境核分别 SHA `32be2deaa791ac14a605174a798c4204f9048327c052f04e9726f68cb4132d92` / `a6dbed49a709b173d1babb178ccf1326ed54731bf02aaefc5c07ac21ea357527`，实际四模块路径均为 E WT、native tree137d499。23:08:11–23:09:01Z Ruff/mypy500、全 backend collect-only 3230、12 个受影响模块 parallel184/serial16 均通过、driver0；focused SHA `d46faffb6dc231f81c50e3fb30683188751d974ec1b18c9fc30468262fa2a1a5`、collect SHA `80da56e799db9fc7146eae64ba3a7df54a8ea78df72e8677f9eb30386eff8161` 已独立读取并重算。范围为 application/idempotency/transactions/prepare/effect/worker/recovery/removal/live identity/wiring/Submit HTTP/read HTTP，未拼成全包 runner 通过；06 busy 已独立核释放。下一正式验证按协调者确认拆分为同 04 E WT 的 backend-only 成功整次，然后其余四 Python 包成功整次；Rust 与 backend 最后闭包均须按实际同 WT compare，不能引用 d0 失败整组的局部通过。

CT108 source02 后另 call 独立源码核实际0，日志 SHA `d9cba5ce77a071c884f8072436bc2791d2135a6f9ba0534f05b90163d065890a`。其后 env01 在 sync/build/test 前因外置 helper 路径错报 prepare_exit2，原日志 SHA `84bae81a974c77e3d233127e0c9f2e1ed52a9d4f79d3e0070ae78185e8d63688` 保留，不冒称缺缓存或产品错误。协调者按 DC68 只批准该 env 步骤一次修正：env02 driver SHA `73fff0ec107cea721cd3da2413a58a813f6bdeae7f8ed98294ebf0e3051f1210` 仅改新日志目录及既有 artifact helper/identity 的实际路径；独立 set-e 只读核所有外置工具/输入存在、helper SHA `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972` / identity SHA `057793b471b5b6061d01f45cd96566c7f2c389308211a3ffa2b1b6a66fab99ba` 后执行。env02 至 23:10:00Z actual0，日志 SHA `b1819ca1c5d0fb42390cf89384c7150f87d6f466faa68fa872a88f0ea6814539` 已核，含 native/tree/实际 binding、本机离线 RS build 及现 CLI help/8 输入 `INPUTS_VALID`；只证明 d0 的准备。独立环境验证 driver `60e14b787174bf9f17bf3649edc17caf53bcd0d7571440659fd8479bbb501d9e` 已审，仅核本 t4 WT 的 backend 四实际模块、tree/selector/image/idle/clean，不运行测试。待其实际0后按同 owner 释放准备占用；最终候选更新与真实 fresh full 仍待执行。

## 两次完整失败的结论与下一最小验证

d0 五 Python 原入口已于 23:13:05Z 自然收束，起时 22:57:30Z，runner1/driver1；完整日志 SHA `6b52584532f2ff237ca99b9275008c16a74d6403d8144e84318ede6aeeec1ad6` 已独立核。最终仅 backend failed，三小包 243/152/161 通过，RS parallel1744 PASS/1 skip、serial207 PASS/1745 deselected（586.98s）均为0，无额外 RS 故障；这些包内通过不能从失败整次取作 formal source。原 owner-final 与原准备 owner cmp 相合、23:13:05Z 释放后才新取 ff 占用。

04 同一 E WT 的 ff source/另 call 源验证/环境/另 call 环境验证分别 actual0，日志 SHA `d5706408f9c63fea6eea313a3d01652438721dbc01453ea70aac196d74543ed3`、`bfd88dc1127a99d4371a16172cb6a5919944e481449f03438b2f4350d12ef961`、`78cd6bfc434abb3ed2511a294f60a474d31acb7f63bac86146790e2af95a1486`、`b05fd41777ce294a46a4f4dc7314f8a3c94bd50e1b7cff2673505802149f8e02` 已核。Rust 实际 compare 与原 d0 合格来源总摘要 `5dbb8a…` 相等、changed_components 为空，明确可沿用。随后 backend-only 原入口实际为 parallel3173 PASS、serial55 PASS/2 FAIL，至 23:29:03Z runner1/driver1；原完整日志 SHA `a27604d02e9a5c66a9b70442e4f6e78701361adedafc0700f1741d3ccb6dcb1a` 已独立读取并重算，事后另 set-e 只读核 idle/clean/owner cmp/release，WT 保留。不是 backend 合格来源。

两项串行失败为 `test_compose_history_compare_journey_zero_write_restart` 和 `test_ordered_history_compare_compose_journey`。远端 Preview/Submit/Review/Archive/History 已执行到对应成功断言；两项 History operation 的 `SUCCEEDED`、精确 commits 与非零 count 均已断言。失败分别在测试侧 local materialization 硬编码 `repo-1` 而其 fake catalog 为真实 UUID，被 C scope 校验拒绝；以及 inline checkpoint helper 漏新必需 `repository_id`。本次是此前 collection 失败未执行到的测试 adapter，未见远端租约、资源或摘要分歧，不能据此宣称整个真实旅程成功。静态追查又发现 ordered facts inline helper 处于先失败断言之后，同样需 scope/init；已一次移交全部直接/间接 caller。

7c 固定小修只改 3 个 test/helper 路径：catalog 实际 repository scope、两个 inline helper 显式实际 repo/N1 薄 bootstrap 初始化/M8589934592 execution scope、pair 调用 scope，ordered 两处 caller 均透传。独立核现函数签名与全部 caller，未改 src、expected、zero-write/restart/ordered 事实断言；这些 helper 明确是 production-derived integration consistency，不冒称独立算法 golden，原核心固定向量未动。协调者按 DC80 允许先 06 backend 静态、本地 History owner 和上述两个 Compose exact case 定向验证；若修后再次同类失败，暂停交协调者，不盲跑 runner。通过后再按固定候选执行 04 backend-only，成功后其余四包；目前四包与 t1–t4 均未实际启动，E 最终 GO 未给出。

ff 失败容器 provenance 原文件 SHA `88d5f8ead36087308bc4b4bc96d84c1203c228e32b2491f2cc854e2a8b53b8be` 保留，不替换为后续成功结果。CT108 d0 独立环境验证 actual0，SHA `845f043e45f366cbf9f05bd15a89127ecd7443f5c16fd54a1e5b3f213cec2ce9`；随后 ff 刷新 source/独立 source/env/独立 env 也均0，原日志 SHA 依次 `682aa921941e499da54950fbbc9deed4fe54471068fd0e88d089a5efd3df7019`、`f823a7e90fbdc077439caa03dd67e30e84cb25a08e702ed98265ee949f96b450`、`a7163a389d0f3c7d93c3da6892466f0190c56cc3b7b0e127c18e5aac50bda79d`、`c0d554a26eb3fb0164ebc2d9e18c1383a32461642f98018fa5286ecf9e49e5b5`，均已独立核。后续另 set-e 只读现场核 CT108 无 busy/运行容器/Dolt/Cargo/8000，t4 WT 仍 clean ff，原输入、冻结资源及本次证据保留；这些只证明准备与释放，不证明真实 t4 已跑。
