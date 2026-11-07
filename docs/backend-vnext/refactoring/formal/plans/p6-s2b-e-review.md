# S2b E 独立审核

状态：**E 未 GO：82c4251b6c的五包静态、04六包整次及fresh t1/t2/t4已通过，82 t3/M16原失败保留；当前源码464289138a补漏预约已过定向/static，隔离a10的64/16/M48 fresh完整t3校准亦独审PASS。main24/8/M16不变，最终生产档与DC33范围待Owner一次决定，最终候选验证/H绑定未办**。本节按 DC86 新建独立审核角色，模型 GPT-6.1-Sol/max。只修改本审核文档，不修改产品或测试；明确小问题直接交实施者修正后复审，真实设计/验收冲突交设计协调者。无新增角色、推送或改写被引用提交。

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
| 冻结、恢复与资源控制 | E 差异不能破坏 exact commit、scope、内容身份、T1/PREPARED、StartArchive Head CAS、强引用/TTL；控制误分类或漏预算可污染 durable 状态或导致真实业务失败 | 复用 A–D 已验证 owning tests，只复核 E 差异；初始DC87 12/4/M8已由Owner最终24/8/显式M16替代，拒启/N1单active不变；DC88仅真实PURE、effect前、fresh lease/drain，保checkpoint/保护/attempt/operator，cancel优先、失租禁写 |
| 最终证据 | 不合格来源、旧 image 或局部旅程不能绑定最终候选 | 06 focused/Contract/五包静态；最终profile触及共同deploy输入，04六包全部实际合格来源；最终H再按同节点同WT闭包/镜像规则绑定。05 t1–t3、CT108 t4既定fresh `real_dump_journey --scope full`，不以capacity、局部或性能延期替代 |

按Owner 2026-11-07简化规则，节点以现场状态和有效原子标志直接取用，无例行跨会话预约/起止请示；仅真实冲突或他人资源协调。最终必需证据仍未完成前不签GO。所有测试节点沿离线缓存、clean committed WT、有效占用与日志规则；本审核默认只读实施者日志、manifest、source，不争抢其占用。

## 删除前预期固定核对

实施者外置脚本 `/tmp/s2b-e-freeze-reference.py` SHA `d97e8c9e36337bacdf506bf7e21f6e2d3912fea1f04589c0980e984cea3e0b60` 已只读核。typed SET/f32、wide 200×100、dropped JSON 三份 SQL 与起点 `test_business_kernel_native.py` 的既有用例一致。脚本仅调用旧 test helper 的 SQL materialize 与旧 canonical projection，采旧 raw/canonical 摘要，不调用新 Rust actual，不保采集器为长期 oracle。

06 `gw-dms-06` 的 `19:04:58–19:05:00Z` 日志起止 clean HEAD 均为 `16e1089a86`，lock-check 与 treechecker（`137d499975f3c104ae9c3268b9e12befb2817ba1`）通过，exit0。日志 `/home/dev/gdds-test-tmp/logs/s2b-e-freeze-reference-16e1089a86.log` SHA `4fe7de2ddf4cea018d86107bb46043436171d70f8889832993f58f0031e699af` 已独立读取并重算吻合。后续发现复制 venv 的 editable 路径仍指 D，故本采集的真实来源为 **D936 旧产品算法＋E16 的 test helper**，不称为 16 全链合格测试或闭包来源。driver SHA `92aef839cdff1b65aa20770c9ab20ce87764ca8b2aedf4c6c4e01beb18e3c9c1` 明确 `cd E/backend; PYTHONPATH=. .venv/bin/python <script>`，helper 来自 E16，产品 `.pth` 指 D936；D WT 独立核 clean。D936/16 的 `vnext` tree 同为 `17bd1c93cb5c3a6b7f8f6271a4088e62d3e3698a`，旧 projection/materialize/digest/parser blobs 已逐项核合。这些事实仅核实旧预期的数据来源，不把整次运行升级为 E 产品证据。

typed raw/canonical 同为 `sha256:f57c8813f99f9226ae5c0970e6619e801cbb013d6d20d7dd32fcba87ee4f7f71`；wide raw/canonical 同为 `sha256:c947ad6fccb65c36c067d38a761ca1049e0122c5f926413ba9f7c09e5dcc603a`；dropped raw `sha256:02fbd36483695eaf632a39a2d83877441b074c7587dd745d579cff4355c8aefd`、canonical `sha256:232a96c506247080963b4d39390ac5bf686238c8fb2edf0febcbdbeb0ae91905`。原日志保留、未反写预期或重做全套 oracle；新路径仍须实际对这些固定值验证。

## 当前容器记录

Current reviewed code HEAD: `464289138a27f03a4dddc3b825e6bd32907fbf9f`，审核detached WT固定clean464。相对82仅内部Python准入/owner测试，06定向覆盖，未新增06 Compose；最终档/H固定后再完成必要04闭包/门禁。此前82的profile触及Compose/环境，已在04本机离线重建并由六包权威入口运行实际Compose，不重复同候选Compose。最后合格04 backend/worker image为 `sha256:a5e0b1df76750aee55cabc9506f0b89427626dab16060794311548617dd8a72f` / `sha256:99ebe2a031d2fb2c81fbf46a266cd8f8f9ac374d55c0f9f8fbce0f649ae25a5c`，RS image为 `sha256:2536840a18c0eb840e88d040988b203d9025270e55337090dca8e848d5b2b08c`、revision82/source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`，provenance SHA `112ddcc6ead0122d356b3bcbd281cc50a1783ad1a519b955c5dd0fecaf23e377`。backend starting closure total为 `23dcc46ad4a910f6d9836c3527b2589dd834b8c9c3c5def8399d300972cb795c`。该结果只绑定实际82，不冒464或旧D/失败/cal的当前容器结论。

82当前容器门禁已通过；最终H的carried仍须按同04/同WT实际闭包与镜像身份规则另办，当前不预填。04 WT保留至stage exit合入。主线读取至36709de375时相对82的vnext无实差异；这仅为差异审计，不代替最终H闭包判定。

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

7c 的 06 定向步骤已实际收敛：source 23:33:59Z/0、另 call 环境 23:34:22–23:34:23Z/0，日志 SHA `4eeda91574be0041f487f37c4fde788134042403e25f0010277b8bafb04089ae` / `3fa7b5bc2f702a06869f22d05de9ead900bd5ee3cf4cf64bc2c061b413a635bc`，native137 与四个 E 实际模块路径吻合。已审 driver `1c805c41ae8629b4ce171956817cae8ae74ad589532165e9ba7176f1060fb942` 在 23:36:11–23:38:44Z 跑 Ruff/mypy500、本地 `test_history_compare_jobs.py` 27 PASS 和上述两个 Compose exact case 2 PASS（141.02s），整步 actual0；日志 SHA `86281ad7703b9f188a37e479868df4bb6a52662407dc339542c2d19652c6c1b7`、provenance SHA `30270af77489af88179e6d08e29a5763bbe58217b6dc3026e7da360d258fc8d4` 已独立读取并重算。包括原失败之后的 zero-write/restart/ordered 断言，未再出现同类失败；06 busy 已释放、WT clean7c，允许按既定范围回到最终 04 backend-only，不作为 04 合格来源。

本次最后成功的容器范围为 **06、7c、这两个 focused Compose**：本机 backend image `sha256:4b4610415a445ad42016faccb2fccb3d2e1c932bf58d4fef5dc3315e8b5656a4`、worker `sha256:3eb3abaed4d67ac27632759908a667eed973218320d302ca7dd3889f0594ad93`、RS `sha256:a8768648faee6971b34c87dda7a425ef0e14a220d7951b086103a5a2d454c9b2`，RS revision7c/source13cb42af/build-inputc52e9fad。全部在 06 本机离线构建；不跨节点比较 inspect ID，不升格为 04 runner、正式 carried、t1–t4 或全 worker 峰值证明。最终这些必需证据仍未齐，E 未 GO。

## 7c 合格 backend 来源与真实数据资源失败

04 同 E gate WT 的 7c source/独立源核/env/独立 env 核均 actual0，原日志 SHA 依次 `3a8140aa2b8ecc521e06c0f87c295e707455f3afcea6e499db61ebe720746496`、`a9d5e512d9e10f55126033935e0d61df42b1cd27199594955b9ee428d8383625`、`fd642f9bceb5f4337f981e99de859b1b8c8db18c60f4d54a5ce53b3dd6e577e9`、`027e3decbcd1e1ee3e510301fc9d5981437dcae6580a8a4026d796289f252cc2` 已独立核。Rust 实际 compare 仍与 d0/5dbb8a… 相等。**backend 合格实际来源 V=7c**：2026-11-06 23:44:03–23:56:36Z，parallel3173 PASS、serial57 PASS，runner0/driver0，起止 clean7c；原 log SHA `1e81ecf2231559035123468ac6a0d27614d9f4f54cc8720d58dc4e484d9c0a75`。从该原 log 提取的起始 manifest SHA `822984029a0c83b61e44c0d82124570c3595a8f53e800a0c9f0cce97cbd1796a`、total `7fb9738df11a230574eee2d9e3a6f9182ad98997194b4cba3bdc7fb0e9f51526`，已独立解析并与原 log 唯一 backend JSON 全对象相等；provenance SHA `d7e2f4b20d603397dee4d1015fd241880139a5e3c400bab014bbb0d9bc503750`。同候选本机 build 及真实 Compose 覆盖计入这次合格来源，无需另跑同候选 Compose。最后 04 backend/worker image 分别为 `sha256:0eb59bd1f0bc18cf9ae9890b498db80c9ee51c69ab46a38b42ecc3ae1a4c2c85` / `sha256:e4438d254c3c98d51fa99adef17b65264707df7e1eb0517d105b29cce5edc939`，RS 本机 image `sha256:ce544459e53d9c318ddabf7274e8d47fbd0b28e7e3ea959cee5f71123dc44de2`、revision7c/source13cb/build-inputc52e。23:56:36Z 释放后才在 23:58:30Z 开新四包占用；四包最终退出另核。

同为 clean7c 的 05 与 CT108 在 2026-11-06 23:58:30Z 各 fresh 运行现 `real_dump_journey --tier t1/t4 --scope full --kernel-threads 1 --kernel-memory-budget-bytes 8589934592 --keep-stack --project-name <E新名>`，无 resume/from-step。远端 driver SHA 实核为已审 d524f828… / 286ef89e…。05 t1 已完整 journey0、normal stop/cleanup0，至 2026-11-07 00:03:36Z；t2/t3 未启动。t4 于 00:01:07Z 首 Preview 业务 `FAILED RESOURCE_LIMIT_EXCEEDED`，journey1，不能归性能延期或完整旅程通过。原命令、旅程日志、各容器前后 logs/inspect/cgroup、result/SHA、原卷与有效 busy 保留；正常停机0，未重跑或扩大 M/envelope。

**Finding：空基线到单侧新增表的比较预算错误地按行展开收费。** 保留 DB 中 `materialize_inputs` step1 SUCCEEDED/cp 保留，`assemble_preview` step2 FAILED，诊断为 `operation memory reservation exceeded`。保留 checkpoint 的 BASELINE/INITIAL 均0表，MODIFIED312表；这次是首个 modified-only Preview，旅程 `scope full` 不等于 `InputCompleteness.FULL`。输入为既定 t4-v1 包 `5597503 B` / SHA `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675`，原输入 census320表/437149行与 canonical task312表是不同层的计数。

真实消费者为 `pair_pipeline → comparison_python_memory_upper → compare_plan`：standard 与 ordered 的 single-side added/deleted 分支均仅生成表级 metadata fact、不消费 rows，但旧准入对这些 task 计全量行/单元格。`dc80-metadata-budget-01.json` SHA `08f7212bee727d2ce0ff26a800065cf299577f74e4bc9455a9b901dd7f0e166b` 已独立核；审核另以原 sides ref 的大小/SHA、当前 registry AST、retained columns/row counts 纯 stdlib 重算一致：312 tasks、278收费/34非记录排除，行项 `13700821888 B` + metadata 基费 `2621440 B` = **至少13703443328 B > M8589934592 B**，尚未加入非负 Arrow logical bytes×64；device_st（54150行×43列）单项6161836800 B。完整 preexisting used 未持久化，不补造 counter；metadata 中 manifest 与 IPC mapping 两项只记部分 retained 值。

同 worker cgroup 在失败返回、正常 stop 前的 lifetime peak 为 **660467712 B**，memory.max/HostConfig.Memory 均12884901888，memory.events 必需 keys 存在且 low/high/max/oom/oom_kill 均0，RestartCount0、OOMKilled false、正常退出0；inspect 资源 Env 明确 N1/M8/reserve4/envelope12。该值含 startup/helpers、不是 RSS，也只覆盖本次失败到首次 Preview 的运行，不能证明完整 t4 的峰值或后续真实读行路径可承载。driver 的 `resource_verdict=PASS` 仅代表配置/证据完整/正常 stop，业务 journey1 仍阻塞 E。

协调者确认这是预算实现偏离真实消费路径的窄修，不变更 DC87：仅 single-side 跳过行模型、保 metadata 基费，双侧与 ordered identity 真实读行预算保持。最小回归归现 comparison owner，普通/ordered×added/deleted 参数化证明小显式 M 下 metadata fact 与零行消费；其余真实读行/资源拒绝 owner 保留。修订后先 06 focused/静态与独立源码复核，不立即盲跑 runner/全旅程；若后续真实读行路径仍超 M，交 Owner 决定，不静默加 M。

后续来源范围：Rust 与三小包待以同 04 WT 的合格 source manifest 实际 compare 确认复用；backend 产品/测试变化必须补。当前四包原始 RS manifest 明确含 `docker:context:vnext` tree `77f8a335362b8c789e72a58761bb0cc38dac35ce`，故预算 src/test 改动将使该真实组件变化，RS 不能仅按功能无关沿用。t1 依 DC64 首受影响步骤为 v1-preview/assemble，旧7c全旅程仅作其准确范围回归；其 owned 卷已按原成功流程清理，run 目录仅 state/secrets，无法从保留卷副本续跑，最终新候选须 fresh t1。t2/t3 未跑、t4 未完成仍须实际 full；先 focused 收敛再排。新最终候选的 t4 可与 04 backend 同 V 跨节点并行；旧7c失败现场完成只读诊断、保留停止容器/卷/镜像/输入/证据并核 idle 后释放旧 owner，新候选另以新 project 原子占用。E 与阶段 exit 仍均未 GO；W1/W2 均未性能 PASS。

## 1de 预算修正与精确补验范围

固定 `ad190ae942…` 及最终 `1de3fa408433b344faac222d28736a82405e566a` 仅改 standard.py 与其 owning test。产品4行在 policy 检查后，对任一侧 descriptor 缺失的 task 跳过行模型；metadata 基费、实际双侧/ordered identity读行公式、全部常数及控制/发布行为不变。新增普通/ordered×added/deleted四项行为参数，用真实1/256行Arrow fixture、显式16MiB构造后留下128KiB余量，证明metadata费用为正、与未读取行量无关、iter_rows/arrow_stream零消费及原ADDED/DELETED事实。新增的重复负向两项已按单owner原则删除；真实双侧/ordered identity低M拒绝继续归现 `test_preview_job_assemble::test_pair_memory_admission_rejects_before_python_row_comparison` 两参数。无新oracle/预期反写/格式/identity/输入或M变更。

06 00:18:52–00:18:55Z（2026-11-07）对 clean1de 实际 Ruff0/mypy500通过、standard/ordered两module及上述既有pipeline拒绝owner共81 PASS，exit0；日志 `artifacts/s2b-e-budget-fix-1de3fa40/budget-focused.log` SHA `850c445ad4a79864ed9a1c0d228a07c0512039acb27523a9ff27009866d29747` 已独立读取并重算。另 call 环境核 SHA `6f99108f38b97556b8ea6bf6ece603f53bd7dde47e54fe62ac344f57ec290c69` actual0，四个实际模块来自本E WT、native137一致；busy已释放。源码及定向复核通过，允许按已确认安排补验；旧7c t4业务失败不改写为通过，新完整t4资源结论仍未知。

7c 的四包权威入口已于2026-11-07 00:11:02Z自然 whole0/driver0并释放，原 log SHA `d1d829ea5bfd398f012ed79bfe70e3f3adb15f18317da717b595107e7f9e2d58` 已独立核（RS parallel1744 PASS/1skip、serial207 PASS）。四个保存的起始manifest均与原log JSON全对象独立核相等、head/package准确；合格原始total为 shared_kernel `26b8a0ba6f67b990433d361aa137dfaeb96d5d0826f6c6e36c2b08d37a98c605`、repository_contracts `eb237e7926624d250119cdb3a755f3e3193432158293108db5085e4ac1af64b5`、repository_client `294456e0d70e11e854243a9947acd8c17b39538475b4a8050215a8747288d213`、RS `67e5a5895d42f018d25eede60eb978e332e0001355f79fa292c6f7a38228b402`。1de实际 `vnext` tree为 `f8e80ac55560e13efbf0768fa9370d50632a2391`，与RS source的77f8…不同，因此后续只补backend→RS两个actual runner；Rust与三小包按同04WT、精确Hypothesis路径不存在、原合格source的实际compare复用。已审三节点固定1de source/env/独立verify、backend/RS-only与三小包compare脚本，均只作候选绑定及必要选择变化；不重跑旧四包，不放宽whole0来源条件。

## 1de 实际补验及真实 Submit 容量阻塞

2026-11-07 更新，审核 WT 固定 clean `1de3fa408433b344faac222d28736a82405e566a`，主线读取时为 `7e800b1e9d1961fe002df003795a740b30b7e6c3`，相对1de的 `vnext` 实差异为空。04 同一 E gate WT 的 Rust compare 仍与原合格 d0 来源 total5dbb…相等；三小包实际逐包 compare（00:26:48–00:26:52Z）均 `changed_components=[]`、上述原 total 相等，日志 SHA `269ea1123546cfb2adc361bab78a27a8276b1d0ad8020e6ecfe752151f44692c`。这三个 carried 直接引用7c实际 whole0来源，不引用旧失败 runner 或另一个 carried。

04 的 **1de backend-only 权威 runner 已合格**：00:27:06–00:39:38Z，主体3177 PASS、serial57 PASS、runner0/driver0、起止1de/clean并释放。`artifacts/s2b-e-gate-1de3fa40/backend-authority-01/authoritative-runner.log` SHA `269cfeb0b9ba5639a04ddf272f3ca73fb52c4af4ca5939fc53514efe33dfb797` 已独立读取；保存 starting manifest SHA `4120a28e79f175f1be684af57fadc9ee516e228dd564dc3bf5b197b9831e16c7` 与原 log 唯一 backend JSON 全对象相等，total `5edbc2561f3424a362c784f33071a2f8b9bf4ccfcf57996b14c1818eaf56e1f6`。本候选本机重建及 Compose 计入该来源，provenance SHA `a86dc5ec2d1d4ea9653054c472932b4e0aa5806851004698ffc77f23d4fa42dc`；backend image `sha256:a0a806f9f2669095ddab07d07bb519e0ab3688958462fbe9f52cb317309822bf`、worker `sha256:a355d755d4aa27e852b5caf072cfdb0f08ec4f1e8102210b72bd25b9245cde07`、RS tag/revision1de及 source-tree13cb42af…/build-inputc52e9fad…。后续 RS-only 暂停，不能将7c RS来源冒充1de合格来源；最终 H 的 closure/image 绑定仍须实际判定。

05 的1de fresh t1 于00:29:00–00:32:28Z完成 full journey0，same-worker、资源/日志完整、正常stop0、owned cleanup0、起止1de/clean，`artifacts/s2b-e-t1-1de3fa4084/result.json` SHA `0a0fc66fee749fea0ddf50fc37b3d4b9db0ed6844e2d15ec1facdd122e440bbd` 已独立核。t2/t3未启动，不能填PASS。CT108相同1de fresh t4 的首次 Preview 已成功，随后v1 Submit于00:30:36Z以 `RESOURCE_LIMIT_EXCEEDED` 失败；`prepare_import` attempt1 FAILED且无checkpoint，后续effect未启动。原driver记录journey1、正常stop/完整证据，worker lifetime cgroup peak `662650880 B`，max12GiB、OOM/kill/restart为零；这不是完整t4容量或租约证明。

本次真实consumer为 `import_publication → frozen projection/typed row images → MutationPlanning/replay`，与已修的single-side metadata比较不同：INITIAL提交的312张changed表确实消费并保留行对象、索引及mutation。现按行预约不能像前一个Finding一样跳过，也不能在对象仍存活时提前release。只读元数据核算 `dc80-submit-budget-metadata-01.json` SHA `fcf5321f929676cf0df2f062c8018dcfd5d7f8a34d8ba9e27bf5d82cba02e92c`：行项下界8335221376 B，package/replay预约2650800128 B，合计至少10986021504 B > M8。closure顺序下界可定位首超额前缀，但确切抛错表未持久化，不声称device_st就是失败表。step只读摘要 SHA `3ee384a569bd4f715f685841dca10c8115fa8667ca4aa68265bcee3140b67b97`。

经协调者批准，固定脚本 `4a28a1e8bcd99634f2524fa3369f9ac5284ed146057c4cd76fedeaac0e4132c5` 仅对保留IPC做readonly mmap/get_batch/select/nbytes统计，无scalar行遍历、运行时/重建/旅程。与实际reader所选列/Arrow Table.nbytes口径相同；锁核、native137、E解释器/pyarrow25前置齐，00:38:01–00:38:02Z actual0。输出 `dc80-submit-arrow-buffer-metadata-01.json` SHA `9cf81e8950e31de789d4c329901dd35af828043165dfa86fe648b19f812036c4`，原log SHA `b25b617bf4290416953850f011e8b6ed11601845d5a836ffd220bb9f06623f59`，已独立读取，并逐项从旧metadata重算全部312项：logical Arrow59223003 B，行预约10230357472 B，加package后 **12881157600 B =11.99651286 GiB**；再加已知mapping62330728 B/metadata17724160 B，得 **12961212488 B =12.07106978 GiB**。这是现显式预约及部分已知retained项，不是完整used/实耗/RSS，后续阶段峰值未知。由此M8不能承载现准入；不自行放大M、改系数或把资源拒绝归为性能延期。

诊断后按协调者预批，仅在HEAD/clean、整机idle、精确owner核齐后于00:44:15Z释放CT108本次busy，`dc80-preserved-postflight-release.log` SHA `b6ddd77cabadfee4140ea46887c693374c285d72df62f6dae57b877521dd2de1` exit0；审核另查busy不存在、7c/1de两代各3个容器均stopped，卷/网络/镜像/输入/证据保留，不做down/rm/prune。04/05同样已释放。

## Owner 授权的一次隔离容量校准

Owner随后明确“先增大预算按测量决定”，协调者批准以1de为基的独立committed Hcal/任务ref/WT：**64GiB worker envelope、16GiB reserve、M48、N1/单active**，其余租约/GC/预算公式不变；不合入最终main，不逐档8→16试探，不为临时档重复六包。CT108实际MemTotal100663296KiB（96GiB）；余32GiB是节点算术余量，并非给其他服务的硬预约。先必要06focused/static、候选与本机镜像身份核齐，再且仅一次CT108 fresh full t4；当前仅批准具体范围，实际Hcal diff/driver与结果另审，未启动校准。

观测优先重用现 `OperationMemoryBudget.high_water_bytes/stage_admissions`：`bind_kernel_execution`实际每次claimed step建context，finally在scope关闭前输出operation/step/attempt及used/highwater/stage，失败也保留且不能掩盖原ack/exception。按operation聚合各step最大值，不将顺序step预约相加。parser/codec `temporary_limit_bytes`是可用准入上限，source-staging也随显式M适应，不能将这些数当实耗或简单以最大值定最终M。标准cgroup `memory.peak`及/proc `VmHWM`为同worker全生命周期累计（含startup、cgroup还含pagecache/helper），按旅程step边界读数只作累计边界，不归属某operation独占峰值；不reset、无后台采样/监控服务。最终profile仍交Owner据完整数据决定，临时大档不证明最终配置或租约已通过。

**当前结论：源码窄修与上述已完成证据范围通过，E最终NO GO。** 未完成项为最终profile决策及其精确候选绑定、RS实际门禁/最终closure、t2/t3与完整t4。A–D累计独立证据仍按其准确范围复用；W1单次诊断不等于正式性能PASS，W1/W2及原线W4未知/OPEN状态不被本次容量诊断覆盖，S2b阶段exit另由协调者按DC86办理。

隔离候选已固定 **`4f808c111b9b8bf8e1673f1bf9b76b1823b7c31b`**，审核detached WT同步至此，main未包含该临时产品差异。独立核相对1de仅4路径：settings三常数、Compose硬限/三个资源值、现bind finally诊断、worker资源owner的max拒绝值及48GiB正向断言。`StepRecord`字段和worker现INFO日志接线有效；观察异常只吞诊断自身错误，不改真实执行结果。N/租约/GC/预算公式/业务expected不变，SOURCE CLEAR仅覆盖此隔离候选；最终main仍待Owner定档。

06实际固定4f，00:49:03Z source0，另call至00:49:24Z环境核0（实际E四模块/directurl、native137、64/16/48常数、同Rust1.97工具链），00:49:29–00:49:32Z Ruff0/mypy500通过，worker_kernel_resources/backend_settings/operation_worker_lifecycle三module `-n0` 共30 PASS、focused0。原log SHA依次 `cfa20878d7010027a73f3fed1a17ab4ce86890e588c8daabcfccbed6046e468a`、`7a76d299981ddb934b6f927c28cb3a71d0a79da7ac56ba67a5c4c2900fa9927c`、`988cfcfb3b06af19d78f42ea785d9e8d6ebd4fd23ddcb198c8ada7d0542781b8`，均已独立读取/重算。00:50:16Z release0 SHA `f69ac7801f6b581a75b6657dca4b2c9a7d6e9b8541e0e98458b9d36383cc8796`，busy另核不存在。该结果仅是临时档必要验证，不作最终六包来源。

CT108专有cal WT的source/env/独立verify三稿 SHA `a62718eac9a099ee628fa5c357842361a69ef0ce043a163cb86ab6d88f735178` / `076a460c9cea92ff4e3d8d58528f6c95918df9fd148d9962bc7df00390c39c0b` / `224528100680505b2bb8b96fa361d90ee659009b4a433a3661337aca88f6d53a` 已审，复用原节点缓存、重建本任务RS、fresh本机build backend/worker，禁止prebuilt。backend依赖base的本节点immutable ID `sha256:d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff` 与此前1de身份核验记录相同/19层，可复用已有config+全部DiffID证明，不重复save大archive。新venv须实际source0后另call核、env0后另call实际路径核，不复制旧venv；旧1de WT/两代失败现场不动。临时资源配置/日志触及容器边界，cal旅程必须本机重建该候选，当前最后合格容器仍仅为上述1de结果。

最终cal driver `/tmp/s2b-e-t4-calibration-driver.py` SHA **`d44a347a81dd19b0bf02773818275a36bc0dccca1774ceeeb0bb7544bda6fab8`** 复审通过：原286独立WT/project/64-16-48接线，保完整日志与scope finally计数，claimed operation/step/attempt与观察集合相等。审核发现最初仅记录VmHWM缺失而仍允许清理，已窄修为有效非负KiB必需条件；缺失/日志或计数不齐即保现场，业务失败仍保真实exit。无后台采样/peakreset；最终lifetime cgroup/RSS事实与step预约分开解释。已授权具体准备/一次fresh校准，实际启动及结果另记，未预填通过。

## 隔离校准的成功前缀与 History 实际失败

CT108 cal source0/独立source0/env0/独立环境0原log SHA分别为 `601949b15aadc9ca6e261a43d66112874d184d3828aced0a204eeaf8f292af16`、`e2d7a65658ae7745c75cbc04b9be45e6e37f2f2b66d8e1ae292c4c6d8d426bfa`、`a55689d30dcd2219d9d7169f7114c6ca7a85df6c1d15e68311d994a096f157bc`、`6c8d7cea94b41c995ef6ba0d38c298c2fd5bc6d65eb171c1f6f238b57d7324f4`，已独立读取/重算；实际新cal解释器/四模块/directurl/native137均吻合，RS本机build revision4f/source13cb42af…。00:52:41Z prepare release0（SHA `d41482275586a53b9b0ed4a379b065a48adf61c8912413e87dfcc3bac29a435d`）后，已审d44新driver另取owner，对clean4f、独立project `s2b-e-cal-t4-4f808c111b` 实际fresh full/N1/M48。未resume、未碰两代旧失败现场或最终main。

本机实际构建的cal worker/backend image分别为 `sha256:790b938e4ccb62433dc84225724b03382e51f01aaf6bd1a5b7e0eab5ac250361` / `sha256:93768892d5b1dddae793239676cd08cd7768a591932af99528081a6e9b54ae38`，RS为 `sha256:bef339546525cdd8480a3251bd15bb6dd3524a63e4bd341455994a3fa388fd85`。这些只绑定失败校准的实际容器，不替代1de的合格容器门禁，也不作为最终profile确认。

00:52:41–01:11:59Z的校准 **journey/driver1**，v1/v2上传、三个Preview（含repeat v1）、两次Submit及相应Repository读回完成；History于01:11:52Z以 `OPERATION.PURE_RECOMPUTE_FAILED` 结束，不能称完整cal或t4通过。原 `journey.log` SHA `8ae6e7e43e26c5fd7f28c5ab92ed22217126e873c02e3a036c667b61bbffbb3f`、`result.json` SHA `4875de8815ba41969efe8d0b4f1d6c8214f3e1990f07293bcb172fd14bde3ea0`，normal stop/同worker/64-16-48与物理资源取证均齐，第三代cal容器/卷/有效busy保留，未重跑。

原worker日志 `08833c79a594-after-stop.log` SHA `550850f090cccc3694370fc72d0a4267d312dc3d1cad5e3d70ecdaa3147e9072` 中真实异常为 `History._materialize_distinct_commits → RepositoryRef._with_artifacts → publish_canonical_tables → C.lookup → controlDB._enable_wal`，`PRAGMA journal_mode=WAL` 抛 `sqlite3.OperationalError: unable to open database file`。它不是已确认的M48拒绝或失租。此时counter已记1019次canonical IPC inspect；源码中旧C reader在新published table替换后仍由context保活，两个commit的mmap handle会累积，构成文件句柄耗尽的具体线索。原worker已停止、原RLIMIT/FD计数缺失；HostConfig.Ulimits为null不能据此断言1024，daemon limit也不能冒作原worker实测。DB目录/文件root755/644，磁盘/inode余量充足，暂无路径/空间证据。后续仅做获准的最小平台/真实C诊断来区分原因，未在此预判修法、提高ulimit/M或扩大机制。

外置collector还有一个独立格式错误：`docker logs --timestamps` 在长counter JSON分片中间插入时间戳，首条在第98435字符解析失败，导致原scope_count0/evidencefalse；业务History失败与此独立。经协调者许可，只离线从上述原log恢复新 `scope-recovered-from-original-log-01.json` SHA `963cdd821b64c4051d5dc505f43d5a1a9e7f587480f9e922060683a094207b76`。审核独立窄去32个Docker分片时间戳，17条claim序列与17条counter逐序相等（16个unique identity，重复await的真实执行保留），与新报告每项identity/highwater/used/stagecount一致；原result SHA及journey1/scope_count0/evidencefalse保持，未重采集/改写/运行worker。此格式恢复关闭collector数据缺失，不关闭History业务失败。

成功前缀的显式预约最大值为v1 Submit prepare `13070921208 B =12.17324399 GiB`；repeat Preview、v2 Preview、v2 Submit分别为6093784234、10997340796、8694034114 B。History失败materialize仅有331156230 B前缀，尚未到比较。全fresh worker累计 `memory.peak=6999605248 B =6.51889038 GiB`、`VmHWM=6682916 KiB =6.37332535 GiB`，必需OOM/kill/max事件均0、RestartCount0、正常worker退出0，未记录lease_lost事件。以上物理值含本次启动和失败History前缀，不归属单operation独占峰值、不称完整租约通过。

`parse_arrow_sql`、native kernel及canonical store把remaining/局部cap传Rust，Python预约highwater没有完整计实Rust内部temporary；stage temporary_limit也不是actual need。相同输入/N1的M8 materialize及1de Preview已成功，仅可复用该范围；最终建议要结合已覆盖路径、物理峰值、合理余量及最终候选必要验证，不能以单个charged_peak声称严格完整上界，不追加Rust allocator跟踪/内部全排列或盲重跑cal。**E仍NO GO；当前先诊断History真实资源生命周期，最终profile与剩余正式验证未决。**

## 文件句柄线索的已证事实及诊断暂停

协调者批准两项最小诊断，均已独立核原脚本/实物。CT108仅使用原cal immutable worker image790b938e…、同64GiB/128GiB memory/swap、空User/null Ulimits的新只读无挂载/network-none容器，输出RLIMIT_NOFILE soft1024/hard524288，01:24:14–01:24:15Z exit0后仅清该probe。原log SHA `f8c7647b3073180aa9a6126f4b2b176440eee75fbd188813244e05685c0ba073`、filtered inspect SHA `1eb0f1fcadab63a33bd7544f3854d8c84971fa0085b1ee14ca6f733597ea6123`，明确为同profile推断，不回填成原worker RLIMIT实测。

06同cal4f/实际E解释器、锁核/native137下，Arrow25两行IPC的标准语义诊断exit0：fd baseline5→mapping6→`source.close()`且buffer仍存活时5，原fd已关闭；同buffer地址/hash不变、IPC仍可读原两值，全部borrower释放后5。输出 SHA `50db37a3506e01d5fb3425e45c0a471097c9e9073a49df48a6ba15712068e596`、原log SHA `e5c88c7ae6acafca95418cad0df0bdf67d32048c6da4502ce0b5dd5ecb10040f` 已独立核。这支持标准source早close有望释放FD并保映射，不单凭此证明本次History根因或批准产品修改。

第三项拟用真实Rust小fixture、CanonicalTableStore、SQLite批register及C.load_table/publication，两组312、独立进程soft1024重现该consumer；尚未完成。首脚本 `e8c2c804017bb4f35280591a15adbcc380578f0188b279c6b02c727c9290ee8d` 在import阶段误从contracts导入compare_schema_digest，未seed/设置limit/进入C。保原01:28:52–01:28:53Z exit1日志 SHA `2987c17279a51bb72521ba0b657b7e076a4ef3e1ba9b5e08298effb3bd288d3a`。按DC68唯一修正稿 `be766600f955eac5a9e80e3eab117520fdabcc6ca53f4df7b0ebda5798939e73` 仅改真实public export和新out02，但01:30:45–01:30:50Z再次准备失败：312 Store/SQLite seed完成后，factory被置于已退出的seed kernel scope外，`operation_codec_budgets`正确拒绝无operation context。原log SHA `f67e1dbbba93550f01f47cbd4c7aa23df5a641b2e113711a7c6b08b48e268e0f` 已独立读取，尚未设置RLIMIT/运行双312 C部分，不能称同故障已复现。审核同样漏核了export和factory/context相对生命周期，已向协调者明确并收回第三项可执行结论。

**按DC68现已停止③，未写/执行第三稿、未改product或提高ulimit、未创建History副本/开服务。** 最小静态更正位置已告协调者，是否恢复由其处理Owner边界；不在此用前两项事实替代第三项或绕过暂停。临时fixture自动清理、原cal4f/clean、原失败日志全部保留。06于01:32:06Z按whole-idle/exact-owner核释放，release SHA `4805176fd9e55678484acc2bab12a9abed8825384cb4333e0af3e884a67515a2` exit0；CT108于01:29:16Z仅释放本cal owner，release SHA `ae9cec35483ce0813f737fcff2a5092d86b7bfea3e5fdfa720231ff8f546deec` exit0。审核另核两节点busy不存在、CT108无运行容器，7c/1de/4f三代各3停止容器/3卷保留，网络/镜像/输入/证据不动。

协调者已认可DC64后续定向路径，仅保持规划：源4f project三卷backend-control/backend-artifacts/repository-service-data及run下t4.state.json（SHA `0b24994ef8334b55a9b94fe9dbb2201c2d2b784d5e34ba30ee0ccb8340753d80`）/t4-secrets四文件，目标独立新project对应三卷/run。原state共18个key，包含_stack及17个成功业务step、无history项，原_stack/head4f字段保持；新project产生新History key，接受层只按key重放，不会复用原FAILED operation。现 `--from-step history --keep-stack` 可跳全部Submit，但内部强制prebuilt且不build/up，故须源全stopped时标准冷拷并核内容/权限一致、候选本机build/up及clone repo/原V1/V2 commit身份后才执行。失败保新copy和日志/资源，原三代不动；局部History与原cal分别列范围，不能拼为完整calPASS。该副本工作仍以③及修复/必要focused收敛为前提，当前未启动。

Owner最新节点协调口径为：空闲节点直接按有效原子标志使用，不再例行跨会话申请/开始/释放通信；真实冲突或他人资源才协调。这不豁免本次DC68重复准备失败。协调者随后仅授权准备可review的第三稿、禁止执行，以便一次向Owner说明具体修法，不提交抽象重试请求。

`/tmp/s2b-e-canonical-fd-reproduction-scoped.py` SHA `4b982cb016eb3ff4903f42e6cdda489cf4e9136751019d26fc7c81523bf8df65` 已只读复核全生命周期，未传节点/未执行。相对be7666仅out03及factory位置：seed scope51–70覆盖Rust fixture/Store put/SQLite批注册；实际consume scope86进入后87–88构建C factory/读取当前预算，97–98 load_table，100–101 publication及lookup；lookup晚绑定port已赋值后才调用，正常/异常退出86后106才检查FD。pool初始化/SQLite初始化不要求kernel context，所有Arrow业务调用在相应scope内。实际4f/clean、E解释器/锁/native137、独立新进程hard-limit条件、out03不存在及原子占用等前检仍须未来执行时满足。**第三稿仅静态CLEAR，等待Owner处理DC68边界，不构成执行许可或FD已复现结论；E仍NO GO。**

## Owner 批准续做后的 FD 因果与窄修闭环

Owner随后明确批准第三稿及明确问题修复后的定向验证（协调者记录08eff0bde1），恢复同E两个角色，无新增角色。06对clean4f实际运行已审4b982cb…第三稿，01:39:18–01:39:46Z exit0，原log SHA `6c6aa8618f7f4832993dafdf70fd4596c8b812d0fb4660ca95ebf7e52bc8bf8d`、输出 SHA `1ea099cf4b3e1e7e8a047061e6023f270e20363c30eddcb810a6490aa542f984` 已独立读取：真实Rust fixture/Store/SQLite/C两组312，FD5→首C317→首publication629→第二C941，lookup395前FD1023，在同一SQLite PRAGMA WAL调用抛 `OperationalError: unable to open database file`；退出operation scope回5。这是单scope同时借用mapping时占满FD的真实复现，不是跨scope永久泄漏；原worker RLIMIT仍只由同profile诊断推断，不回填原实测。此前两次准备失败继续保留，不转记PASS。

产品main固定 **`d6c88cafb38255c66dbb5f8fae091af75e289d62`** 已独立源码CLEAR，相对1de的vnext仅2路径。LocalArtifactStore在同一readonly mapping完成size/raw SHA校验并释放hash memoryview后 `source.close()`；仍yield同一个pa.Buffer、保持强引用及原finally，不复制payload/重新打开文件、不提前释放mapping内存预约。原完整性/取消路径顺序保持。单一canonical store行为owner新增96个真实并存reader，要求artifact FD为0且每个IPC仍读2行；现映射预算、完整性、取消、借用及close owner继续覆盖，无内部步骤矩阵。没有同时修改handoff/http_arrow/ulimit/N/M、FFI或业务expected，main仍12/4/max8。

06实际d6 source0及另call环境0（原log SHA `0931933df64b2dd93a5727861d840c15248bb9c78286cad2d8609420b622dcd2` / `81288f0056bf14afa4b3a505c9c5f18992191cfdcfbe0e9e5ab7a6c8fba7b8c5`，实际E四模块、native137/main12-4-8），01:44:52–01:45:30Z Ruff0/mypy500通过、canonical store/workspace artifact/RepoRef protocol/snapshot business四module57 PASS，整步exit0，日志 SHA `210a2b2cf6729a852af73b29412bee5e14f69fdc3e788bdad9d048ede6996cff` 已独立核。随后同一fixture、同两组312、同1024/524288限制的正向对照（脚本4868b080…只换out/成功判定，factory仍在consume scope），JSON SHA `f84193ea0420c966bc9b0b3eece9f84ac0c4f6792ec38cbbfc4368d9230a8b19`：首C/首publish/第二C/第二publish/退出及lookup采样全为FD5，两commit完成无异常。与原03因果对照闭环，不冒权威runner来源。

隔离cal固定 **`1f9df50a5c01173b82febc3a74b01bae549b1bb0`** 原样cherry同一补丁；审核WT已detach固定此提交。main d6/cal两修复blob逐字节相同（LocalStore `4562452ba735859f8799667a809a0ba1df1d0779`、owning test `28d5bd24710e185582f1025501e036f2e1a029de`），剩余vnext仅原4f四路径64/16/48/logger差异，patch-id与1de..4f同为 `0c8347732432693f7023f66c4820a7df5a8f3ea3`。临时profile未合main。当前06未重建Compose；CT108 History局部将对1f9本机build/up，当前最后合格容器仍为1de，4f失败校准镜像只作相应回归事实，不宣称新候选已通过容器门禁。

已审History专有新WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-history-fd` 的source/env/独立verify三稿，SHA `ba969f70d261848fe3cf1c245067478cb502c0e8f3e2d5012a55983d68079234` / `d7ab5ae735e2cfaf663b71ad87a7bcb025287c9d1a212527fe8ce7bfb5f9f646` / `0059a87963f102bcf3b941e85fe40299a2735ed0cd182dc7d7ddadd364b58d71`；相对已审cal模板仅候选/ref/新WT/out/tag绑定变化，保原4f WT/卷。source0后另call实际HEAD/clean/legacy核，再env0后独立模块/venv/native核，准备与copy可持同任务有效marker连续完成，不为日常节点额外预约。copy/服务/History具体driver另审，尚未创建副本或运行。

源复制口径如实补充：冷态普通SQLite `mode=ro`检查会创建/刷新可重建sidecar，RS本次检查产生空WAL/SHM；不声称源目录从未逐字节变化。两个源WAL实物均0 B，main DB mtime仍cal停止时，backend/RS主DB SHA分别为 `e76b09a20382e9f1a5d66c8d986835cd691c1a9cc3a652182758e92d63371093` / `a3501d58f420fee7c34fbe12ddb626cc9441f46b04bf3537cd4db646c791c2d8`，业务状态backend5成功/旧History1失败、RS2成功保持。协调者已按ADR比例化确认为派生文件事实，无新审批/修复框架；原证据不改写，不删除或回填sidecar。后续源在已停止/WAL0前提用immutable只读，按复制时实际完整卷状态冷拷和比较，含sidecar。

## 1f9 History 冷副本局部验证

History新WT的source0/独立source0/env0/独立环境0原log SHA分别为 `285b708ab2a694de016e31ca7d1fffc2e2fbf10f642a4788a41c38c5439902ba`、`f4ab0dfff40a39f3ab71094f527456fb688b110169093886a686803b26b8be7b`、`be7d1d4f1748b55ddf0d7a1a65414c3e48ec5224593eb5f2c050184115a49d17`、`20f010131dbf138f611b013da26063221602f8cadce0cff377586dc6d551bea4`，已独立读取/重算。固定1f9/clean、实际新WT解释器/四模块/directurl/native137、同节点依赖base及当前RS构建身份吻合。

独立复核的最终一次性driver `/tmp/s2b-e-history-copy-driver.py` SHA **`560ff052cc316732cabaac978464040d5d07e91eb6d562afad6a6cba98163126`** 仅用本E4f停止数据的冷副本，起始metadata即标History_only/原完整cal仍FAILED。已核源卷无special文件、真实SQLite表/字段和terminal状态、固定原state/17成功step、copy前后内容/权限UID/GID aggregate一致；只用cold WAL0下immutable SQLite并显式关闭连接。源三卷实际fingerprint分别为control `5dbe6b45504878f20ecdf26b66e5d40788c2395267cc4c7744f3675c6442f7ca`、artifacts `ef57e8bcc9dfa196debd3989174b363fa1e3af8ea112974ebb6eee5a8e230408`、RS `b18c2102ab0438285bcda74b75ab462fe24025156cb740fd6f8c4d852ae0361a`，均按实际复制时含sidecar的完整卷内容计算，不声称目录历史逐字节未变。

driver直接当前候选本机build和bare Compose up，不调用会teardown/seed的fresh helper；ready后typed catalog核同repo `61b78312-9aef-48ba-8aa1-a024f92c1bfd` 的原V1 `8bge6neeo2mrg8fmem4uj5257ldrhchg` / V2 `cdtvk5eutkiu8k8fkonh858q8d6va9l2` 各312表，再执行现 `--from-step history --keep-stack --project-name s2b-e-history-fd-1f9df50a5c`，新History key、未重复Submit。from-step内部prebuilt只消费外置本次已build镜像。已按审核窄修保存build image IDs并逐container.Image同节点绑定、timeout已有stdout/stderr、History前固定新worker身份；raw timed/untimed日志分存，仅untimed after-stop解析counter，不保留常设时间戳归一化。

**该History局部验证通过**：CT108 02:05:03–02:09:25Z（2026-11-07），fixed1f9/clean、同N1/64-16-48，journey0、正常stop0、日志/资源完整、自有copy cleanup0及busy释放。`artifacts/s2b-e-history-fd-1f9df50a5c/result.json` SHA `9f85607d419adb7a7e954633d30cfd1778e7378613a899a876cf370b8b449a02`、journey log SHA `81bc78ced9bd8979dec25b9b48c32647f0733620bac15c62a96995d2343f39ca` 已独立核。build/up/clone-ready日志 SHA依次 `620df25c4963496ae1b567f96eb08391370c120a50d321ff02f770647c94005f` / `26be027fc06a4d22b3a25f46c4d7ce16c5760d1d62285644493c7a3e37acc7e9` / `87648a2f70d971358b4e517fe913d8e94bc8d652fb0c243a9b3a88afc2122d4e`。当前built image与三container绑定文件 SHA `682f7c18e3d0b8fba4d24488641414f0a584e259bec7580e0e05ece627b3191c` / `3ee9304c682fcd2d3c155b0fbabac2d5d830c4b1a7739a20f3230121e7726c73`，backend/worker/RS image分别为 `sha256:be90d49547dd73f9a294e463e9df58861f60650d04b15fdecfc28a5aa11295f5` / `sha256:0e833a59c72a670e2ba140f2b42b7a8fb4d3f24a261c2c5a98a7b3539707b354` / `sha256:8a3a8b107a2ec99655e407ac0f4e34d9c2f219b2cb42b42c4e63e0bd08b33c2f`，RS revision1f9/source13cb42af…。这些是当前局部镜像事实，不冒最终main权威门禁。

新operation `op-5ad5b9ab937f699652bd2af1` 与旧FAILED不同，untimed原log SHA `37f1bba3f2ff4c9b8c388ba181a6ad39ce1a7ffdd221bbf8e507e2d0f28c9b47` 已独立逐序核3条claim=3条counter，均属此新History；materialize/assemble/publish显式预约highwater分别398673952、**11218037646 B（10.44761GiB）**、3761894 B，未报lease_lost。局部新worker从ready前到终态同Id/StartedAt、Restart0，资源文件 SHA `bba5880eba229592cf159ca5581bf12c7a6af1b6401cf2e8e16de305b5638507`：cgroup lifetime peak263307264 B（0.24522GiB），VmHWM423704KiB（0.40408GiB），mandatory OOM/kill/max均0。RSS包含共享页、cgroup按charge归属，二者不必相等；这两项均是新worker局部生命周期，不与原cal物理峰值相加或拼成完整单worker结果。

审核另查新copy容器/卷均0、busy不存在、节点无运行容器，7c/1de/4f原三代各3停止容器/3卷保留，原state SHA仍0b24994e…，原cal `journey1`/result4875de…不改。FD Finding由窄源码、行为owner、真实C正反对照与此实际History闭环收敛；**E最终仍未GO**，最终profile/候选及六包、t1–t4必要实际验收待收齐。若最终profile改vnext/deploy，按协调者1e9d6a378b确认六包共同闭包变化，最终六包均需实际合格来源；当前临时cal/FD不跑六包，A–D语义证据按影响复用，同候选backend权威Compose不重复。

已给协调者的资源建议为24GiB envelope/8GiB reserve/M16、N1的受限候选：已覆盖成功前缀最大显式预约12.17324GiB，History补验10.44761GiB，M16对此预约峰留3.82676GiB余量；Rusttemporary不被charged完整计实，原cal物理峰值与新History局部也不能拼完整峰值，故此仅为覆盖范围+合理余量的待验选择，最终同worker完整t4及必要验收仍不可免。最终profile由Owner据此决定，不宣称临时64/16/48已获生产确认，也不承诺2×t4/W1/W2或更大输入容量。

## Owner 最终A资源档及必要最终验收

Owner已明确选择最终A：**24GiB envelope / 8GiB reserve / 显式M16，N1/单active**，覆盖此前暂缓配置消息（决议aedeb00679、命令绑定014e7a1c4f）。固定产品候选 **`82c4251b6cf944526c80a5e9bfe707bc57ab5087`** 已独立窄审CLEAR，审核WT同步detach至此：相对d6仅settings三常数、Compose精确字节25769803776/8589934592/17179869184、既有resource owner的M16+1拒绝及显式profile/N1/单active断言。缺M拒启、类型严格、M≤envelope-reserve、固定控制/租约/claim预算及FD修复不变；原小fixture显式M8仍合法，不机械重写。main无临时cal logger/观测框架或ulimit修改。

06对clean82实际source0 SHA `95aa7b2faeb12bf2dab5f178db79e6d3fd3c7dbfb0f385a080c13fa03d962a29`、另call实际E路径/native137/24-8-16环境0 SHA `0f13ca465796fb2ce6a43c47a904034c75fb4aca27cfa3f0c996ba2ee2de82a0`；Ruff0/mypy500通过、worker resources/backend settings/worker lifecycle三module30 PASS、focused0，日志 SHA `c7ed37603c6c2d117ec4350d6bc2ad071042b99909dbf14ad72d4de2b60641c8` 已独立读取。02:17:14Z release0 SHA `a6b17a74059414043ec669259ac2c19c22dc7285bc678b04c9d29faaedc2aedf`。这关闭配置定向验证，不是最终六包或真实数据通过。

按已确认影响执行最终82：04同E gate WT六包全部actual runner（Rustfmt/clippy/test和五Python），05 t1–t3、CT108 fresh完整t4可并行，不复用临时cal充当最终旅程。最终fresh driver `/tmp/s2b-e-final-t4-driver.py` SHA `0ff03b35aca679ac18ba1ecc0f8ba5b94ffb45a6bdc680760b431aa46e1a4d45` 的关键差异已核：新project、M16命令/24-8-16运行配置、同fresh worker cgroup lifetime peak/RSS/事件/正常stop、失败现场保全；无临时scope-counter必需条件。05版仅限制tier参数t1/t2/t3及对应WT/project，04实际选择全部六包、不carry旧Rust。已明确范围的准备/focused/预检按既有模式自行推进，不另立逐脚本GO链；审核重点为实际SourceV整次exit0、最终闭包/容器绑定、fresh t1–t4与资源事实。最终结果尚待，未知不写PASS；原cal三代/源callee数据保留，GC他人文档不触碰，S2b最终exit另办。

## 最终累计条款与既有独审证据映射

累计范围始终为 `53b676a6298d408ccda3a85ee73c7ea223a2311a..82c4251b6cf944526c80a5e9bfe707bc57ab5087`；以下按已交付GO/原测试owner复用，E仅补实际消费者迁移、两项真实故障及最终资源档影响，不重新逐段审核A–D或增加门禁。B引用恢复后的delivery独审，原停止记录不改判。

| 条款/owner | 已有独审/依据 | 82影响及本E收口 |
| --- | --- | --- |
| Arrow值/profile/声明/空列行数、列序与同bytes确定性；Shared Kernel framing/vector与A codec owner | [A独审](p6-s2b-a-review.md)，产品db7767ffbb/审核83b927207a；[mapping §§2–5](p6-s2b-arrow-mapping-design.md)、Canonical Storage §5.1 | A codec/映射及固定vectors未改；E只移交consumer/删除旧实现，独立旧值冻结与fixture construction分开，未由新actual反写business golden。A能表示的类型不等于B业务白名单支持 |
| 唯一Rust批量parse→业务验证/materialize→project/hash→A IPC；过滤前全行/列验证、keyed/keyless/ordered/composite语义 | [B恢复交付独审](p6-s2b-b-delivery-review.md)，产品b820321c1e/审核0dc93c09a9；业务kernel、adapter/diagnostic/golden原owner | E最后应用/工具consumer迁移并删除旧bulk parser/projection/materialize/仅diff/hash probes；六条temporary UNREACHABLE随六模块删除，无fake import/cycle/整层native放行。保真实rules/XML/AST/composite、小metadata、MutationPlanning row-image digest、raw/clientParquet与通用reader；类型/过滤/摘要规范未扩 |
| IPC raw SHA与scope/schema/content绑定、独立handle/borrow/close、same-ref与强引用/TTL | [C独审](p6-s2b-c-review.md)，产品0048040af5/交接7cd2b548c8/审核e9bef6efe8；`test_canonical_table_store`、cache/staging/roundtrip/fault原owner | 仅Store成功校验后早关source FD，保同mapping buffer/内存预约/取消。已由96并存reader owner、真实双312正反对照、修复后实际History补验闭环；无copy/reopen/新reader或broker |
| exact immutable commit恢复、健康canonical content免重写、T1与PREPARED冻结、Archive Head CAS/引用原子性 | C/D独审与Canonical Storage/业务Lifecycle；`test_canonical_commit_access`、`test_submit_import_builder`/prepare/recovery/worker、`test_submit_transactions`/`test_archive_transactions` | 不改变C恢复选择、frozen T1缺失稳定失败/PREPARED复用、正式引用只在StartArchive Head CAS事务移交；E仅替换真实reader/合法fixture。不能把缓存恢复改成重选HEAD/SourcePackage或在Archive内重新物化 |
| W2结构计数：baseline逻辑行需求/实际行读取0、行比较按X派发、规范内容命中不重写 | [设计§16.2](p6-design.md#162-计数断言dc55-第-5-项)、总kickoff§6、C/D已核count owner；`test_unchanged_preview_table_does_not_read_baseline_rows`、`test_unchanged_identity_table_reuses_current_rows_without_baseline_read`、`test_exact_commit_recovery_hits_do_not_rewrite_and_corruption_rebuilds` | 复用结构Contract，不以性能样本替代。普通identity跳双方rows，ordered identity按原owner只读current；raw SHA/必要metadata核验不冒“行读取”，canonical IPC内容免写不等于禁止derived manifest/业务事务写。E删除obsolete probe不删除这些业务断言 |
| operation单active/N、增长前M准入、实际cancel/drain/lease_lost/deadline及safe publication | [D独审](p6-s2b-d-review.md)，产品93678f8439/交接abfe7cb66b/审核78411aa40b；ExecutionControl/LeaseSession及Preview/History/Submit recovery原owner（D既有422项范围） | DC88真实PURE/effect前/fresh lease+drain可RETRY_WAIT，保cp/priorrefs/保护/attempt/operator，cancel优先/失租禁写/EXTERNAL原规则均未改；无deadline仍None。E修单侧未读rows误收费、FD占用，最终只改24/8/显式M16。D旧12/4/M8及675MB materialize局部不是最终whole-worker容量证据 |
| final authority、当前container、真实t1–t4、无fallback/兼容路径 | AGENTS/Testing Conventions、总/E kickoff、ADR0010/0012与比例化policy | 本最终deploy变化令六包actual必需；06不冒04来源，整次失败runner内单包不作来源。最终H按同04/WT实算闭包与image绑定，fresh真实旅程及全worker资源仍待齐；未增加持久evidence状态机/UID或额外角色 |

W2结构条款与W2性能30秒目标分开；W1首次可读观测/单次t4仅为初步诊断，正式2×t4及预热+3次测量未完成不PASS，最迟S6按DC83/DC84归原性能owner；W3自S3，原冻结1f9731dfc3的W4 lease问题继续OPEN，E新运行的未报失租不自动关闭它。InputCompleteness.FULL语义由原D/应用Contract及适用组件证据覆盖，real_dump_journey的`scope full`不冒InputCompleteness.FULL；D局部capacity、4f失败cal前缀及1f9局部History均保持各自准确范围。

五包最终82静态实际齐：backend直接引用c7ed3760…；其余四包02:24:15–02:24:18Z在06 clean82/实际E module/directurl/离线wrapper下Ruff全0、mypy分别34/15/26/200文件通过，`artifacts/s2b-e-final-profile-82c4251b/four-python-static.log` SHA `31ab664f521b74b72e4aac0521119d1917f188b45598adef3e4c83c2c978e8f2` 已独立核，static_and_release_exit0。按AGENTS“提交前”要求补最小四包，不重复backend/pytest，不依赖旧127c static carry，也不说权威runner包含Python静态。

最终t1已独立核PASS：05 fixed82，02:19:44–02:23:14Z fresh full/N1/M16，journey log SHA `3c37fc491d1bb3d1e0d9c9599e70040fc872531917ce177739cfbd3d8d2d97f2`、result SHA `27d573fffae8c6d8b0515523407f9438f6b7ed050465388de8bd3f1a821fd2cf`；cgroup max24GiB/peak273059840 B、VmHWM266804KiB，必需事件0/同worker/正常stop/cleanup与释放均齐。04六包虽部分已过但whole尚未结束，t2–t4及最终H绑定尚待；这里只记已齐事实，不预填剩余PASS。

## 最终82六包实际来源与真实旅程结果

04最终六包整次合格：2026-11-07 **02:19:09–02:45:04Z**，同E gate WT、clean82，Rust fmt/clippy/workspace test全部0；三小包分别243/152/161 PASS，backend parallel3179/serial57 PASS，RS parallel1744 PASS/1 skip、serial207 PASS；六包status均passed、runner0/driver0。原日志 `artifacts/s2b-e-gate-82c4251b/six-package-authority-01/authoritative-runner.log` SHA **`d1dffcd84595d3b7424374d2277fd6276c02a8efa7e38b2c70936021b8621a48`** 已独立核，起始每个manifest均head/worktree_head82、clean=true，末端HEAD82、release02:45:04Z。审核另核无busy/运行容器、gate WT clean及legacy链接正确。

该目录六份 `<package>-source-manifest.json` 均由原log逐字提取；审核独立解析原JSON并逐份同时核对象相等和原始字节加末尾换行相等。最终六包都以此**实际Source V=82**为来源，不引用任何临时/旧失败runner、旧carried：

| package | 原始total_digest | 保存manifest SHA256 |
| --- | --- | --- |
| rust | `352a7fbca8b15ba56b764ac2430b62214c8517751736527fba214d1f7c4a5dca` | `97c2c5e90b5f336aa05b02adf02e470c9cd5645bd39b0bac3e31758d5a163b27` |
| shared_kernel | `9845e1f5d9dc558a5d2aef42e08c7e57c9f54d0f7e5eeb4d9eccde567e835046` | `846e98db90cfe94717d1b6e21e79cbdddbe8ca767152daf8a23b2c03ab5be1b5` |
| repository_contracts | `152bf331a99081d656f57a939eb16721639cbb1d1b4a31624d6151a8262fa72e` | `c4f8032b7e40cf3a5fb74fe133eea8474b91d4ffc1dc0a9ad0c52412f4f3c057` |
| repository_client | `54b277acbdfbb68ea34212d32d9fda4a8fcf79149ed262247cc3b4c9bcd4187e` | `4b550b87df511a3abee477fa82cca13d3366085c85eab7694cc084059bbc6ad3` |
| backend | `23dcc46ad4a910f6d9836c3527b2589dd834b8c9c3c5def8399d300972cb795c` | `10f8bb33cb0d32969730ceaeeb4706b640ea7e8411382c40bde5960324fd5b93` |
| repository_service | `7212abd7ab2ddf7b8697eb502bba7e579736d4eb359fd74e1fb064c9df127a15` | `2a101b4ab5ad6457d7bffd4a07ab63f30c555c2f58ce79017027ae98d8d87b10` |

04 source/另call独立source/env/另call独立env实际均0，原log SHA依次 `ec9037e2a99fa83ff990291beaf191ab014aa471e13f51bdb977e11188c6731a` / `6d513231856ebad93ab0cdd431c6c268ed8efa5c72b8e6b30e78b37735c2d9a5` / `e8614e3f22d17bafc81c8a985cf5255a4bf13d21cbbbdc1bd576e8c26f3e4082` / `0d0f471927964621f9836f64b4a172320ac0a28d8cbea1efb248078695526bd8`。新完整bundle SHA `39cc3944eb410ec0ca14a6636b99f11fd8416a6808f7562ff69f7915208df04c`、本任务namedref、actual previous 1de均记录；实际包路径/venv/native137、Rust1.97同工具链、离线/预置依赖和RS当前标签吻合。容器身份详本记录顶部；最终H沿用/镜像身份判定未办，不因六包过就省略。

05最终t2也已独立核PASS：02:23:24–02:37:05Z，fresh full/N1/M16/clean82、journey0，`artifacts/s2b-e-final-t2-82c4251b6c/journey.log` SHA `74113500b4c9165ca3e7181926aff5e89250c8d3ee32ad1f0c22971d205128ce`、result SHA `6ed3ffffb6dcd8ead1783bd51d6c067bf4eaa2d4e2f90f62697e6714b1085970`。worker a4bc6aa2ecb6 lifetime cgroup peak2563973120 B/max24GiB、VmHWM2411392KiB，必需事件0、同worker/正常stop0/cleanup与释放齐。t3在现场空闲后新原子owner运行，未将t2释放当作预约。

CT108最终fresh完整t4已独立核PASS：**02:19:44–02:40:39Z**，fixed82/clean、显式N1/M16、`--tier t4 --scope full --keep-stack`，无resume/from-step，journey0。project `s2b-e-final-t4-82c4251b6c` 原journey log SHA **`13ac186de8fa7774268a06b4a49f3fb95218b6319787fbfcb598fdf11d642fcc`**、result SHA **`004a026b4f33c2440e5902fb1651326a9471a57df6bd3fd5715f3abb2c4348da`**、command SHA `8a3cf27d66b8dd465d1dba8859e169c53fdeadcc595443b13e9c4397ae40caa8`。完整Preview/Submit/Repository读回/History均成功，worker090f4608269b从首次空catalog观测至终态身份不变、Restart0；profile24/8/M16、normalstop0、全部日志/资源/owned cleanup和busy释放齐，endHEAD82/clean。

此t4完整单worker lifetime cgroup `memory.peak=6991069184 B`、`memory.max=25769803776 B`、`VmHWM=6684612 KiB`，必需OOM/kill/max事件0、未报lease_lost。resources SHA `02a83adc44ce6029df7f2ad850e82c9e75710deef5224deaed88eb8c9f37f793`、worker after-stop log SHA `9a765d034b804c2fbbb79861a4de30e34eff3def99a94905746e6c70d5e6629b` 已核。它补齐旧D局部与分开的cal/History无法给出的完整物理范围，但不等于M的严格总temporary上界、更大输入容量或正式性能PASS；main确无临时cal-counter日志。原cal失败不改判，原三代资源/数据/evidence保留。

W1初诊只使用这次t4本就导出的timing：首次v1 Preview受理响应后至终态fallback58.337秒，repeat v1为62.351秒，`visibility_observed_via=operation_terminal_result`、poll interval2秒。这些是受理响应后至首次可读观测/终态代理，不是精确READY事件时刻；单次t4/N1/M16/24GiB，不冒正式2×t4、预热+3次或W1/W2性能PASS，原时点/责任归属不变。

**最终t3未通过，E保持NO GO。** 05 fresh82于02:38:11–02:46:18Z运行，v1 Preview/Submit、repeat Preview成功，v2 Preview `op-dffc6a0eee79886afcb6b859` 的materialize_inputs attempt1 SUCCEEDED且checkpoint5608d132…保留，assemble_preview attempt1以 `RESOURCE_LIMIT_EXCEEDED: operation memory reservation exceeded` FAILED。只读step摘要 SHA `43f37e9c7138fc7ae24952585ddb5f0754658cb9a20aabd58e1149a28820d23f` 已核；journey SHA `948f27a15f7a6ff87fcf6cfb2c5b02298b005ee1c1fc5d25adf459a82a4f0a4c`、result SHA `78bde259fb8b02853075ddf5c4c1eee658670e35f40728e6ea99b0d6a124b888` 保持journey/driver1。

该worker dfdade767d51的配置/同worker/资源完整/正常stop0均真，lifetime cgroup peak4373372928 B、max24GiB、VmHWM4201560KiB、必需事件0；`resource_verdict=PASS`只指资源证据齐，不能覆盖业务失败。现场容器/卷/busy按DC80保留，未重跑或改M/系数。当前先从保留descriptor/roles/identity筛选重算真实双侧预算需求，尚不认定误收费或选择新资源档，也不把资源拒绝归为性能延期；最终H闭包判定待故障收敛。

### t3准入下界及当前读行分支的漏预约

只读计算已收齐，无新旅程/服务或scalar行展开。原metadata脚本因unmaterialized descriptor没有business_schema_digest字段而失败，01日志 SHA `16d4bb2f87ee33f55a2171c5e6eedeab83429ce4713d9e64ba169bb3478b84ac` 保留；按Owner DC68只读后处理澄清，此字段适配不计一次重试限制，不扩到触产品/证据不符情形。修正摘要身份来源，并按真实table map过滤：BASELINE53个materialized/139个unmaterialized，MODIFIED193个materialized；后者仅summary描述符不会产生task.table，不计行项。

固定脚本d178433d…实际0，`dc80-comparison-row-lower-02.json` SHA `60ab606f271b9a35c73ef5fa6954eb370bf22aa39063b1275b6d4defaa84756c`、原log SHA `437645773a1ca116ac4fbba9c08f3d9eb1688801c427a15a9012bc0615c84a5c` 已独立读取/重算。193 tasks为110 STANDARD/54 ORDERED/25 BROWSE_ONLY/4 SNAPSHOT_ONLY；保守略过87个ordinary identity，28个changed双侧、48个ordered identity current合计104个read-side行项。row项17044254528 B，加base1646592 B为17045901120 B；它单独仍低于M16 133968064 B，不能提前称已超额。

随后仅当前device_st一个既有IPC做Arrow25 mmap/get_batch/select/nbytes，方法与已审4a28相同，不遍历scalar/不运行Rust或业务consumer。02:54:35Z actual0、锁核/native137/E解释器/82clean吻合，脚本065f60ee…；JSON `18be24ff08a342f40539863729945214168778e0390a59f73c7f339d65f21b0d`、log `b850b0acce2b41729c3d1405b3d706b16dafe68e50509e24c7be3713e752f897` 已独立核。device_st current43110行/43列的logical Arrow16646188 B×64=1065356032 B；与上述row/base合计 **18111257152 B（16.86742GiB）>M16，至少超931387968 B**，其余selected Arrow及已存活收费均未计。device_st本身双侧row项9700784640 B。该结论证明当前收费模型的双侧准入至少超M16，不把它叫真实RSS/精确物理需求，也不自动缩系数、跳过真实行或逐档扩大M。

同时独立发现本次实际输入的增长前准入缺口：`standard._compare_non_record_role` 在COLUMNS_ADDED时会双侧`_read_rows`并建Counter来判content_changed，但`comparison_python_memory_upper`对BROWSE_ONLY/SNAPSHOT_ONLY无条件略过。源metadata中iec101_cfg/iec104_cfg/project的共同列scalar_type及nullable逐列相同、无removed，仅新增config_type/tips，分别337/330/13→14行，实际table refs齐；准确落入该读行分支，不是仅凭role猜测。未覆盖费用不能由其他表的宽裕保守系数替代。

协调者已确认这是当前资源正确性窄修，交实施者只补该COLUMNS_ADDED实际读行分支的原行模型预约，保其他metadata-only免行费；不改业务facts/系数/预算档，也不声称这会解决M16拒绝。业务断言继续归现`test_comparison_rule_roles`两role owner，最小低M拒绝须在真实读行前触发。源码/focused闭环尚待；新增宽裕t3剩余路径校准须纳入此修复后另交Owner具体方案，当前未授权或启动。

05所需只读证据齐后于02:55:18Z按idle/82clean/精确owner仅释放busy，release log SHA `2647713da378e4e631b6e47f64e1b52cb44f1f022e0808bce25bf6f69f3af80a` actual0，已独立核。原t3三容器均stopped、三卷/网络/镜像/输入/state及失败证据保留，未down/rm/prune。05实际MemTotal64GiB；若后续选择既有临时64/16/M48档，只能按CT10896GiB及获准用途安排，不能在05假称另留32GiB。现1f9相对82仅profile/log/assert四路径，不含新的漏预约修复，不能直接作为后续修复cal候选。

上述漏预约已由固定main **`464289138a27f03a4dddc3b825e6bd32907fbf9f`** 窄修闭环。相对82仅standard.py/test_comparison_rule_roles.py：nonrecord双方descriptor存在时，复用业务同一_schema_view/schema_evolution，只有COLUMNS_ADDED才对双方真实reader套现行公式；其他metadata/单侧仍skip，ordinary/ordered原early-exit不变。原content_changed业务owner/expected不改；新一个role×columns_added四参数行为owner验证1→256行预约增长、metadata费用不随行量增长、低M在读取双侧前拒绝及零iter_rows/arrow_stream调用，不复制收费常数为expected。

06实际source0/另call环境0日志 SHA `1b888897a385d6fe739a57f68d1febcb8dd406407289a2a728186b74c65581c0` / `b1ff94cbef696dea275cd4999af6f5ee99cb451be73c35dd86197298c9e83525`，clean464/实际E模块和venv/native137、profile仍24/8/M16，已独立核。03:00:22–03:00:24Z Ruff0/mypy500通过、roles/standard/ordered及既有pair admission nodeid共93 PASS，focused0，log SHA **`eeec41b911ba77eea540eae763a8504b2e6623f8c661e6d54ad3f040ae64a004`**。03:01:13Z release0 SHA `cd8534919179c7b272004e144334c4f61f8510e4674ea63426d1e00c2261a57d`，marker另核不存在。此范围独审CLEAR，不作新04来源；它补正确性费用，不会降低t3原模型18111257152 B下界或关闭M16失败。

协调者拟向Owner提出具体一次宽裕隔离t3局部校准：464补丁纳入1f9原64/16/M48/N1 cal基线，CT10896GiB；05闲时原子取得占用后仅对本E三停止卷/state/secrets作标准冷归档，经获准LAN私有传输至新project，核byte/mode/uidgid一致；当前候选本机build/bareup/镜像绑定，原repo和V1 commit核后新key从`v2-preview`走剩余V2 Submit/read及History，不重复V1 Submit、不改原FAIL或source state/head。当前仅为具体方案，**未授权复制或启动新cal**，新cal候选与driver仍须核实际绑定。

审核已核源state路径 `/home/dev/gateway-real-dumps/runs/s2b-e-final-t3-82c4251b6c/t3.state.json`、SHA `443732447e1f4ae12df80b576e44cf51ab17c7a80d8d24aeb0ab80710ad733b2`，14keys为_stack+13成功业务step，已有v2-upload/v2-workspace，无v2-preview。_stack原head82/project保持，repo `9c7cf48f-4d86-44f0-92f4-c12e029ff4cd`、initial commit `4a370s8f7cb72nt7j3dt39oqpd8tc83t`；同run下t3-secrets四文件齐，不输出secret内容。

现CLI机制可用：JourneyStepRunner复用前缀workspace/upload，v2_preview_action按新project生成新key；accept_start_preview按(workspace,key)查重/定operation id，没有FAILED terminal禁止条件，accept本身不增workspace版本；资源失败handler只置operation/step FAILED和释放step保护，不改workspace。因此copy后还须一次核v2workspace OPEN、optimistic_version/current_upload_revision_id/generation与保存upload一致、BaselineHead与成功prefix一致，才可同workspace/upload发新op且newop≠旧FAILED；不人工改state、版本或HEAD来绕前提。此静态方案不替代实际局部结果，也不替代最终profile fresh完整t3/必要门禁。

隔离cal候选已静态固定 **`a10dec894e39013dc02bc7100a27da69ca01040b`**，任务ref `refs/codex/s2b-e/t3-calibration/<fullSHA>`核合。独立逐blob核main464的standard `5bb7b55bda6f4295b246546657ab772523da3389` / role test `7037318c8c0882d7b1a16f309fce8befe713fdcd`与cal相同；464..a10的vnext差异严格四个原cal路径，其kernel_execution/settings/worker资源owner/Compose blob依次为 `043df1d5429c59b63f2aad738c89fef77c011bd7` / `b6e8b2e860054fdc715410e01649c5eae7e1a8cd` / `b4f6a892ba87020dcd0c12c0600e3ee8eada16a2` / `fb2cf4046f8e70ea27c0e8b5d428fa8a50bf1081`，逐一与原1f9相同。1f9..a10仅上述两个漏预约修复路径，无其他产品差异；因此可复用464的93项定向与既有cal profile行为证据，不为同代码再跑相同focused。此为隔离源码等价CLEAR，main仍24/8/M16、审核WT仍clean464；**Owner尚未批准本次校准，未复制或启动**。最终profile与剩余正式验收仍待，E不GO，S2b exit另办。

协调者随后明确：Owner此前“先增大预算，再按测量结果决定，避免多次尝试”的持续授权覆盖原校准遗漏的t3剩余路径，因此撤销前述另等新cal批复的调度等待；**依据既有授权继续，不转记为新的Owner批复**。仅a10同64/16/M48/N1、05冷源→CT108独立copy/from-step v2-preview至History；main最终档不改，原FAIL/state/卷不动，不重复成功V1、不运行临时六包。已核源码/CLI前提不再建立逐版本签GO链；按关键资源/身份/副本边界和事后原始结果独审。真实失败或前提不符停报、不自动提M，最终生产profile仍测后交Owner决定。

## 测后最终范围的最小影响核对

协调者授权只读核已有t4 closed metadata与原counter，评估测后能否沿用82 t1/t2/t4业务结果；不启动最终门禁。审核在CT108现场idle后于03:14:54Z原子取得短readonly owner，固定clean a10/实际锁定venv，未与校准运行重叠；仅读取原4f停止数据与既有82结果。证据目录 `artifacts/s2b-e-review-t4-nonrecord-delta-01/`，原control DB及state最后SHA仍e76b09a2…/0b24994e…，未写源或启动服务。

原4f和82 full t4的V1/V2输入分别同为SHA `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` / `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611`，size5597503/5596595 B，已逐项核。4f与82的standard blob均3c2ffd73…、Rust tree均137d499…；差异仅临时profile/logger与FD早close/对应owner，FD修复保mapping预算。82..464仅新增nonrecord准入分支及其owner，不改任何成功业务输出、reader、规则、digest或事务。

一次脚本 `b29088c67cc6ada98d1d227083b2f383810c6cfc46862bd557ac26b052a54c84` 先核metadata raw SHA/size，精确commit索引312×2完整、所有624绑定均被closed manifest覆盖；只对34个nonrecord表的150个closed variant、48个唯一selected IPC做Arrow25 mmap/get_batch/select/nbytes。它与CanonicalStore真实get_batch/select及Arrow table logical_size口径一致，无scalar遍历、Rust业务kernel或新旅程。每表取所有variant最大单侧现费用，再保守计两侧和全部nonrecord表，即使实际非COLUMNS_ADDED也不略过；实际MODIFIED_ONLY Preview/History均仅一pair，因此新增费用**上界1498264448 B**，不是另造业务oracle或把下界冒上界。

03:19:16–03:19:18Z锁核/native137/实际E解释器前置及该只读计算actual0，`fee-upper.json` SHA **`6cb5fba0be807de08130e9c18491ced3b54572b0c03e80a221d8c356ee2331d9`**，命令log SHA `2eb22b2e1ea2625abd25fc304a4ba3e42e1aac3d3529dd2362708436535b452d`。原cal成功前缀scope预约峰13070921208 B，已修FD的1f9成功History scope峰11218037646 B，取max并加新增上界为 **14569185656 B**，较M16尚余2610683528 B。各claimed step独立建budget，故该最大值可作收费影响上界；不将分开的worker物理峰值相加，不拼成完整calPASS。

该收费合计不包含全部Rust temporary，不能据此称最终M16一定沿用。更保守的资源沿用条件是最终M至少覆盖原已通过M16与新增上界之和：**Mfinal≥18678133632 B（约17.395GiB）**，让未改native调用的remaining cap不低于原82。实际调用链为worker显式M→每step OperationMemoryBudget→增长前reserve；parser/business/canonical仅将remaining或局部min传为max_live/max_codec_peak准入上限，Rust该字段用于边界拒绝，不选hash/schema/输出算法或N。source staging有固定归档上限，bundle/XML收费取实际输入而非按M扩大输出；N1、单active、租约/control保持。这避免用charged峰代替native严格实耗，亦不新增allocator跟踪。03:20:03Z核whole idle/a10clean/精确owner后释放，release SHA `718870f829feb77281c7f1e53785423cec5ea7f913b655e7c74e39c8fa794921` actual0，随后才由cal自取新owner。

给协调者的DC33范围建议是：82 t1/t2/t4完整业务结果可作对应原输入的功能正确性回归，当前最终候选仍需06适用focused/static、04六包actual/current Compose及fresh完整t3验证最终配置。t4新增费用与native headroom有上述具体条件，满足时可省其重复旅程，但旧t4 cgroup/RSS明确只属于24/M16，不冒新profile实测。t1/t2成功资源卷已按原流程清理，现无同等精确新增费用上界，不以tier编号或t4文件更大推定；若Owner按比例化DC33选择功能结果沿用，新profile逐tier资源实测仍须记“未做”；若要求逐tier实际承载，则t1/t2是具体剩余缺口，不默认全t1–t4重跑。最终范围随测后配置一并交Owner确认，目前仅建议，未放行最终运行。

## a10 fresh完整t3宽裕校准

05原线自03:04:56Z有有效占用，已接近/超过t3成功前缀耗时；协调者据持续测量授权将待冷副本方案改为CT108一次fresh完整t3，同64/16/M48/N1，直接使用已齐8输入和a10环境，避免继续等源归档并取得单worker完整峰值。**未实际创建冷归档/复制/恢复副本**，不重复t1/t2/t4或临时runner，原05 t3失败卷/state不动；这不是新生产profile批准或额外新校准轮次。

新driver `/tmp/s2b-e-t3-fresh-calibration-driver.py` SHA **`5f724b12e2c604204b971bdabe4c2b874f2525d1791252fb12d927e59c69b91f`** 关键差异已核：原d44仅tier/newWT/project和已验证untimed after-stop原日志采集/解析，timed日志仍保，真实record_count与unique scope_count分开；64/16/M48、N1、same-worker/CGpeak/RSS/正常stop与失败保现场不变，无from-step或seed/copy新框架。scope对claimed集合完整，不将stage temporary_limit当实耗。

CT108新WT `/home/dev/gdds-test-tmp/wt/p6-s2b-e-t3-calibration` 的source0/另call独立source0/env0/独立env0日志SHA依次 `3318b3dfff8460c516d57f35ae8dbe617a991d1ad038e88c93ca0968e6318a74` / `ca90a2f825d8c43a3d3e8788df87f91a4913ae4d3ee08d8ea5c1317e631256ba` / `7bb84a8c90959c7c47ab2cfd3e80cdd691e192ff80c132f8ef246f6c4b86fc0a` / `3593af436ed156fc298f6d44eee366219c893de4c7e93d350e005ae957f981e0` 已独立核。实际a10clean/新venv及模块/native137、依赖base保持本节点已核身份、当前RS build image `sha256:070c9cc4860d87ce82e531e3a23516d0c111501e216ece3353ffc2250b1ad4d1`，org revision a10、helper build-input revision4f/source-tree13cb42af…（build-input依相关路径最后提交计算，不要求等于candidate）。prepare于03:09:46Z释放0，SHA `324a989a46c4ffc3447367121a42b8d5fb0bac71ee4cd47eaafb5c242f42604a`。

实际03:20:23Z，project `s2b-e-cal-t3-full-a10dec894e` 新原子owner，现CLI fresh `--tier t3 --scope full --kernel-threads 1 --kernel-memory-budget-bytes 51539607552 --keep-stack`。已只读核argv，当前仅v1 Preview成功/v1 Submit运行中，完整终态/物理峰/预算摘要未知；E仍NO GO，不预填新档或完整校准PASS。

### a10完整校准结果及一次最终档建议

**该次fresh完整t3校准独审PASS**：03:20:23–03:42:33Z，clean a10、N1/64-16-M48，journey/driver0，同一worker40fd63d49e97自首次空catalog观测至结束、Restart0，normal stop0、资源/日志/counter齐、自有容器/卷/网络cleanup和busy释放齐。原journey SHA **`c51afa1ff606e923c0149b8ebfb5bd45d784c18297af1c650b87c28763f1470f`**、result SHA **`f2f5fb26cfc110048bc73d0db2f34ba82eae7d22d2083dafd10fb5191a8b8b9f`**、command SHA `4731c4a5c147572527853dfd5f89e6652e04070d5945e4a2785720fe7f55da6e` 已独立核。untimed原worker log SHA **`382d1d2fe02101944fe1c4789fe0b20cc1d1b3bc28b32901e3049738d616ddee`**，独立逐序解析18次claim=18条counter、18unique、全attempt1/N1/M48，未报lease_lost/resource failure/Traceback；保存summary SHA `28e2ae76f6b7f6215571a3965875def2b85c7c1dcbc238ffed42dee90a58e3cf` 与原值相符。

六operation各scope预约峰最大值为V1 Preview3798888734 B、V1 Submit9078047792 B、repeat Preview3798888734 B、V2 Preview21281126550 B、V2 Submit9839426576 B、History **21375346635 B（19.907343GiB）**。不跨step/operation相加。对原18条stage数组重新分组可见最高charged在History assemble的Python比较/Parquet阶段；该scope的Rust inspect先发生于retained≤161175242 B，之后无Rust parser/business/codec调用。真正native调用点最大retained为V2 Submit prepare的canonical-ipc-inspect **8995200416 B**；parser/business/encode最大retained仅355789250 B。计数与stage ceiling分开，temporary_limit不是actual need。

单worker全生命周期cgroup peak **4765663232 B（4.438370GiB）**、VmHWM **4415476KiB（4.210926GiB）**、max64GiB，必需events/OOM/kill均0、正常exit0。resources SHA `931370da36cb6bfc8d85a855214fb71b44cc7159dc269e061f3e29dcfdbb9579`，running/stopped inspect SHA `4bb67a57cee7b7f710e29644924dce8639929c99895728239f72a09496b9744e` / `619059af0f61cf49421c55fc2d373e13fc04e5c0bf4ecb0623e85cf40f3bac50` 已核。当前校准worker/backend image为 `sha256:c7a5f3e8b788be1a0f4f742e403f078d20ee3d0b4d7be3a7c5d09a1c06c71cf3` / `sha256:6ff46741b229b64a7daf7010748b0a6c1ac216cca1b5ed3671aae65ed6946380`，RS为上述070c9cc4…、org revision a10/source13cb42af/build-input4f。本轮是隔离64/M48的实际完整数据，不冒最终main容器或32/40GiB新档物理实测。审核另核新project三类资源均0、node idle，原7c/1de/4f三代各3停止容器/3卷与原4f state SHA0b24994e…保留；05原t3 FAIL不改判。

给协调者的最终选择表如下；表中remaining由校准实际retained投影到候选M，**不是这些候选已经实测的cap，更不是native实际need**。最终新档仍须fresh完整t3及必要门禁实际确认。

| 方案（N1/单active） | M / reserve / envelope | 对完整最高charged的余量 | 真实native调用点的最小remaining投影 | 物理证据界限 |
| --- | --- | --- | --- | --- |
| 主推荐 | 24 / 8 / 32 GiB | 4394457141 B，4.092657GiB | inspect16774603360 B，15.622567GiB；parser/business/encode至少23.6686GiB | 当前只实测cal64/M48的4.43837GiB CG/4.21093GiB RSS，最终32档待验 |
| 备选 | 32 / 8 / 40 GiB | 12984391733 B，12.092657GiB | inspect25364537952 B，23.622567GiB | 多8GiB预算/硬限空间，无额外实测优势，不保证更大输入 |

主推荐不是按charged乘比例。最紧native阶段只作canonical IPC验证/借用，现每call input上限1GiB、descriptor metadata16MiB，N1；parser/business/encode在低retained阶段，比较高峰后是已有增长前准入的Python/Arrow/Parquet。既有t4原log550850f0…按已审963c恢复口径再次仅内存解析（仍17records/去32个原Docker片段、逐项与既有恢复报告相同），最大inspect retained5856116946 B；在相同未改收费下映射至已实际通过的82/M16，其窗口约10.546066GiB。新t3 M24的15.622567GiB窗口更宽，且M24满足上述t4 M16+Δ的保守条件。该对照是保留已通过cap的论证，不把旧stage ceiling当实耗，不追加allocator/probe或逐档试。8GiB reserve仍给解释器、未完全计实native与pagecache/平台余量；最终硬限效果以新档实际fresh t3为准，不保证2×t4或正式W1/W2。

06维护另由协调者实核：96GiB/16CPU/cpuset64–79、Docker/Compose与缓存/镜像保留，03:40:47Z释放，核查log SHA `b871048d3922eb58dd53fc5826f85720464712386bf5f59c71695b0324a1cc99`。仅维护，无产品/测试变化；此前06定向仍按原执行时环境引用，后续任务按已恢复节点用途开展。当前main未改最终profile、未启动最终新门禁；表与DC33范围建议一次交Owner选择，E仍NO GO、S2b exit另办。

## 最终证据接收清单（待Owner定案）

协调者测后提案 `1f02f9e76d` 已读，main相对464无新vnext差异。配置主案32/8/M24、备选40/8/M32；DC33主案本轮06 fresh t1–t3，备选仅t3并显式接受t1/t2新档容量未证。06本轮真实旅程用途与范围同在Owner问题内，尚未定案；此清单仅接收最终证据，不是逐版本前置GO链，不启动验证或重审A–D。

| 接收项 | 最终必须明确的事实 | 已有证据如何使用 |
| --- | --- | --- |
| Owner定案与固定V/H | 精确配置字节、选定DC33范围及本轮真实旅程节点；最终产品fullSHA/clean、显式M/缺失拒启、N1单active、无临时cal logger/默认M；464之后仅预期profile/owner差异 | 464漏预约窄修/93项、FD修复与A–D累计条款按本报告已有范围引用；不重复旧恢复/取消/事务/CAS证明 |
| 06必要定向/静态与实际环境 | 新profile现owner的正向接线/上限拒绝、backend Ruff/mypy；五包静态逐项给实际或准确未影响来源，额外工具未改不重查。实际WT/venv模块/directurl、native tree、离线缓存/镜像/输入身份及有效占用随原始日志记录 | 06维护b871048d…仅硬件核查，不能冒测试；与profile无关的93项可按精确diff复用，不再跑同代码owner；旧五包静态不冒权威runner |
| 04六包实际权威与当前Compose | 同一固定V整次runner0、六包实际passed、Rust fmt/clippy/test齐，起止HEAD/clean/hostname/UTC/退出码；六份starting manifest逐字来自该原log并记录总摘要/SHA；当次当前本机build与Compose provenance/image身份 | 新profile触及共同deploy，不能carry旧82 Rust或三小包。旧82仅作已合格回归来源；同V backend批次内Compose已经满足，不另重复一组 |
| 最终真实旅程与资源 | 若主案获选：06按现场占用fresh完整t1/t2/t3，各自同节点完成；若备选获选：仅fresh完整t3。现CLI明确tier/full/N1/最终M，无resume/from-step；原输入身份、同worker、HostConfig/cgroup max/peak/events与VmHWM原值、正常stop、日志/清理/释放及实际终态齐；最终main无cal计数日志，不要求临时counter | a10/M48只作测后依据，不能代最终档。t1/t2若省略，记82功能结果复用和新档容量未实测，不补PASS；t3原82失败保留，新结果单列。失败按既定DC80保现场诊断，不自动换备选M或盲重跑 |
| t4具体功能沿用 | 最终M≥18678133632 B，464后无其他输出/reader/规则/控制或算法变更，继续N1单active；绑定82完整t4与6cb5fba0…费用上界/remaining分析 | 两提案均满足数值门槛，仍须核最终实差异。沿用13ac186d…/004a026b…完整业务结果；旧24/M16物理峰保持原profile，不冒新档t4实测，不重做完整t4 |
| 最终H与释放/结论 | 最终H与合格Source V在同04/同gate WT实际逐包closure compare，原Hypothesis路径不存在、环境/本机镜像状态匹配；RS helper重算source/build-input身份，backend按同WT闭包绑定；记录最后current image来源、各node实际释放与证据留存 | 不凭docs-only口头carry，不从失败runner摘包，不链式引用carried。WT留至stage exit，原失败/三代数据保持。W1/W2未知及原W4 OPEN不写PASS；E最终GO/范围与DC86 S2b exit分别办理，push/tag归协调者 |

上述清单不新增容器组、allocator探针、输入生成、持久evidence机制或审批步骤；范围由Owner一次选择，后续只审实际差异与最终原证据。当前仍为准备状态，未执行新验证。
