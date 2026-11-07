# S2b E 独立审核

状态：**E 未 GO：7c 的 t4 预算误收费已在固定 1de3fa4084 窄修并通过 81 项定向验证；新候选最终门禁与真实数据待齐**。本节按 DC86 新建独立审核角色，模型 GPT-6.1-Sol/max。只修改本审核文档，不修改产品或测试；明确小问题直接交实施者修正后复审，真实设计/验收冲突交设计协调者。无新增角色、推送或改写被引用提交。

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

Current reviewed code HEAD: `1de3fa408433b344faac222d28736a82405e566a`。相对7c仅内部 Python 比较准入及其行为测试；06 focused 已覆盖，未增加06全 Compose。阶段退出仍要求当前候选在04本机 build/权威入口以及既定真实节点完成必要范围。最后合格04容器来源为7c backend-only whole0，backend/worker image `sha256:0eb59bd1f0bc18cf9ae9890b498db80c9ee51c69ab46a38b42ecc3ae1a4c2c85` / `sha256:e4438d254c3c98d51fa99adef17b65264707df7e1eb0517d105b29cce5edc939`，RS image `sha256:ce544459e53d9c318ddabf7274e8d47fbd0b28e7e3ea959cee5f71123dc44de2`、revision7c/source13cb42af/build-inputc52e9fad，backend 起始闭包 total7fb9738d…，详下文原始日志/provenance。1de产品变更使backend及RS完整context变化，不能在当前预先声明 carried；D局部与ff失败容器记录只保其原范围。

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
