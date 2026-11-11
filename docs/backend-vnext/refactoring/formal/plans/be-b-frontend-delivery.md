# BE-b → FE4b 交付

状态：B5 产品证据已落到固定 V；最终 H、04 同一固定 worktree 的脚本实际 carried/容器绑定及退出 tag 仍待协调者核收。本文交付正式 Contract、五类 golden、入口/输入/输出、V/镜像身份、生产 OpenAPI、稳定码和差异原件；不以 vnext tree 相同代替 H 绑定，不提前宣称 BE-b 已退出。本文不启动 FE4b，不修改 frontend 产品或代签前端验收。

## 1. 正式 Contract

| 交付 | 当前 owner |
| --- | --- |
| 导航 v1、十二诊断、typed 谓词与完整性 | [Business Navigation](../../../contracts/business-navigation.md) |
| Surface v4、列并集/展示序、双侧内容 binding、固定 pair/view ID、semantic digest | [Comparison Surface](../../../contracts/comparison-surface.md) |
| Bundle v4、ROW_LOCATOR、shared closure、完整 tar/保护与 raw 校验 | [Comparison Bundle](../../../contracts/comparison-bundle.md) |
| 五列定位、最终文件顺序、keyless occurrence 与缺快照 context | [Row Location](../../../contracts/row-location.md) |
| 注释及二十条列重排 | [Table Presentation](../../../contracts/table-presentation.md) |
| 双侧公式与 device 别名 | [Composite Signal](../../../capabilities/composite-signal-device.md) |

旧五份 business projection、width/hidden/align、points/formulas 独立产物和 Surface v3 旧字段说明已经替换。只接受当前 selector，不提供旧 wire alias/兼容 decoder。每个成功 surface 恰一个 `business_navigation`/BUSINESS_NAVIGATION，risk_summary_ref=null；缺失/重复拒绝。B9、preview-no-navigation、fallbackNavigation 由 FE4b 退役。

## 2. 五类 golden 与生成输出

版本目录 `vnext/fixtures/golden/presentation/be-b/v1/` 下为 navigation、navigation-diagnostics、row-location、surface、bundle 五类。全部由实际 parser→business materialization→canonical projection/publication→Preview/History pair pipeline→bundle assembly 生成，没有手写导航、诊断或定位。row-location 包含真实五列 Parquet 的 base64/schema/解码行；surface 包含精确 semantic preimage、digest 以及真实 Parquet 重排/重编码后 digest 相等的向量。物理变体仅证明 Surface 的语义排除项；原输出 bundle/closure 保留原字节。

完整前端 fixture 位于生成输出的 `backend/`，包括 `fe2a/{preview-full,preview-modified-only,preview-replacement,history-three-nodes}`、`fe2b/preview-workbench-normal`、`pairs/initial_to_modified_fixture_for_backend_digest_cross_implementation`、根 manifest/closure 及它们引用的全部成员。根 bundle 从同次生成的跨语言 pair 原样复制，不混用旧 metadata。新增场景全部在 `index.json` 声明；缺 required 目录即失败。

## 3. 固定输入、命令与消费者动作

后端持有 `vnext/fixtures/presentation-inputs/manifest.json` 与全部输入。八个 FE4a 原文件来自完整提交 `59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`，路径与逐文件 SHA 固定。原 baseline/initial/modified 的 yc_list 缺 required gid，真实 canonical projection 均返回 KEY_MISSING；原件不改。另增 `sql-{baseline,initial,modified}-canonical.sql`，只为该表补 gid 声明和值，并清楚标明 derived_from、变更与授权。原输入失败在每次 index 的 rejected_frozen_sources 实际记录，不静默修补生产输入或放宽规则。

在专用离线节点的 clean 已提交 worktree、本人原子占用下执行：

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
CANDIDATE_SHA=$(git rev-parse HEAD)
UV_OFFLINE=1 CARGO_NET_OFFLINE=true ./vnext/scripts/uv-consume.sh -C vnext/backend sync
UV_OFFLINE=1 CARGO_NET_OFFLINE=true vnext/backend/.venv/bin/python \
  "$REPO_ROOT/vnext/scripts/generate-presentation-fixtures.py" \
  --input-root "$REPO_ROOT/vnext/fixtures/presentation-inputs" \
  --output-root "/home/dev/gdds-test-tmp/be-b-fixtures-$CANDIDATE_SHA"
```

Rust 变化先按 AGENTS 强制重装扩展并核 build input。wrapper 的 run 不允许跨项目脚本，故同步后显式用同一已锁定环境 Python 调用。后端镜像可只读挂载 scripts 和 inputs，以该镜像 Python 调用同一入口；入口的 Git clean/commit provenance 检查需同时可见原 checkout 与 Git metadata，不在镜像内改造生产 identity。

生成器显式固定 secrets.token_hex 的单进程序号→SHAKE256、各 materialization/publication owner 的时钟、repository、flow pair/view、单 kernel thread 与预算，全部记入 index。BundleInput 严格跟随真实 flow producer：Preview 的 baseline/initial/modified 角色与英文标题；History 的固定 fixture node ref_id 角色与 node-i 标题；两者 snapshot_digest=null、display_metadata={}，不把组件计算中的 snapshot identity 填入 flow 未发布字段。scratch 随临时上下文关闭；生产 fresh journey 不使用这些替身。comment-only 场景实际调用 accept_submit_transaction，原 no-op guard 返回 NO_CANONICAL_CHANGE，记录只读事务数、零写事务和零 Repository main 调用；fixture 的只读 control/baseline ports 在 index 明示。

前端 wrapper 只用 subprocess 调入口并整体替换 `backend/`；复制输入时逐文件核 manifest SHA。删除手写导航/诊断、fallbackNavigation 和旧无导航 fixture；不编辑生成产物。浏览器不重算 surface_digest，继续核 bundle/closure 摘要、ref raw SHA/size、同侧 Parquet metadata/BigInt 与形状。

场景覆盖普通两 pair、History 三节点、replacement、gid/地址变化且未改 cfg/点、UPDATE_ONLY suppressed 增删、重复/孤儿、整数 UTF8/安全边界、整数 registry 与文本数字 cfg 不混等、逐侧 IDENTITY_EXCLUDED、空 sg_cfg/点 schema、before-only 列、缺快照 context、keyless 第三次副本、改前公式/未变 device 别名、仅注释 Preview/实际 no-op Submit。EXACT 未记录行场景与 suppressed fallback 分开断言。

真实 business materialization 的 composite catalog 要求 device/测点地址为整数，且非空 device 具有唯一特殊身份；因此不伪造文本装置/文本测点可达的上传组合。文本数字反例使用允许的 device_cfg.gid TEXT，对整数 registry 必须 UNSUPPORTED_TYPE 整表降级。keyless identity frame 未包含筛选身份时必须唯一整表入口并按受影响侧报 IDENTITY_EXCLUDED；keyed 物理缺列走 COUNT_UNKNOWN/受限 fallback，不把缺列当比较排除。默认共享表规则不允许 keyless，keyless frame 分支以 owning capability 参数化测试验证；生成输出的 keyless_demo 证明真实 occurrence/locator。排除身份场景显式通过正式规则 decoder 注入对 device_st.dev_addr 的 compare exclusion，index 记录该非默认策略，不改变产品 registry。

## 4. 版本、门禁与镜像身份

产品验证 V=`37fe3a87d28ac5fc4f78bf2007260aefc06ecd12`，`V:vnext=2faac9fc1da9a6fd15eddef894f5c6e1652fba95`。最终 main H、H 的实际门禁/容器绑定与附注 `be-b-exit` **待最终核收**；本页不预填 tag。main 随后合入 FE4a/AGENTS 文档的事实不等于 carried 已通过，即使 vnext tree 相同，仍由04原固定 worktree 的门禁脚本实际判定。

04 权威 stage run `20261111T055102Z-cc3ccbdc2fd8`（gw-dms-test-04，固定 `/home/dev/gdds-stage-gate`）起止 clean 同 V，UTC 05:51:02–06:10:56，stage/runner exit0、占用已释放。rust 与 backend 都实际 run/pass；backend 并行4178、串行98通过，含本轮容器旅程。其余四包 not_run（未请求），不称六包全量或 carried。原目录 `/home/dev/gdds-gate-results/<V>/<run>/`：result.json SHA256 `350cc78acb68f8a7984f7c9e9dd8a627facf4d0ae8ce0fb31762d245ca420905`；runner.log `9ae59e20219600fe42b0c340e0c3e408e3de73ad20ecc1b0aeb803342dc0fa75`；compose-provenance.json `e65c3b7b517d510f21e5d28841659e3b768833fd2ea840d44226cbbd0a517a01`。交换副本在 `/home/dev/gdds-stage-exchange/be-b/b5-gate-37fe3a87d2/`。

06 fresh 真实链使用同 V。下表为该次实际服务/依赖镜像的**真 OCI config digest**与完整有序 RootFS DiffID 的原件索引，不将04/06本机 inspect image ID 混为 config digest，也不假定跨节点镜像相等：

| 06 实际 tag | OCI config digest | DiffID 数 |
| --- | --- | --- |
| be-b-b5-t1-37fe3a87d2-backend:latest | sha256:9cf43af712bdc027836bcb0a41c1356e7c5087a3c00cad9135cd8f03166af9b4 | 13 |
| be-b-b5-t1-37fe3a87d2-worker:latest | sha256:6508b162440286c8c6d688767bd4249506cb75d7415d2ebc1b9ef4da0e9e8175 | 13 |
| be-b-b5-t4-37fe3a87d2-backend:latest | sha256:533779dbad2e61ea686cbc60bb7753a1a0e5cfe7da87718bd0c921986525b4a5 | 13 |
| be-b-b5-t4-37fe3a87d2-worker:latest | sha256:03e524be8b47475ae27d289204ca1dd29b637fecbb7ff42436b3cbc3703aafc4 | 13 |
| gateway-repository-service:be-b-b5-37fe3a87d2 | sha256:45b27bc72e1423e372bc2d113b791aebd1ebc406ac2d8767edd1afa23a841197 | 31 |
| gateway-backend-deps:lock-578e079b762e | sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939 | 19 |
| gateway-p2r1-repository:lock-b47d6de3cbce | sha256:567e7bf95a9a226efb7e557260d494b63c1f3c865de53eb6860c181703db9c13 | 19 |

完整七镜像身份及每一条有序 DiffID：`/home/dev/gdds-stage-exchange/be-b/b5-real-37fe3a87d2/image-identities-v2/identities.json`，SHA256 `923de66a5a9ebb3ef1d49768e6aa9467a4699afad3f1474ce9ce24343dedbacf`；同目录保留从 Docker-save 原样抽取的 config blobs。逐一重算 config bytes SHA、核 rootfs.diff_ids 与索引完全一致，结果 `b5-frontend-image-audit.json` SHA `d971e82efdb42bdddc399a385ae3062b436bbb0e2680cf6fd081c4d1e6bb3509`。该索引是完整身份，表中数量不代替全部 DiffID。

BE-b 未改五锁、toolchain selector 或依赖基线输入，未为本轮新建 dependency-base；本机离线重建并使用预置依赖。04 result 明示 RS 缓存来源 CT201/f3d12825e9、2026-11-10T11:49:59Z 的批准 LAN 预填充；历史 uv 缓存来源提交/时间为 UNKNOWN，保留此限制。S1a 镜像只作历史来源；BE-b 当前产品/容器结果来自上面的 V 实跑。

## 5. 生产 OpenAPI 原件与双 baseline diff

原响应保存在 `/home/dev/gdds-stage-exchange/be-b/b5-real-37fe3a87d2/{t1,t4}/production-openapi.json`，均为06同 V 的生产 Compose HTTP 响应原字节；各79082字节、SHA256 `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`。来源 run.log（gw-dms-06，clean V，UTC05:51:58–06:07:59，MINIMUM_CHAIN/SHELL_EXIT0）SHA `678aaab91fe8b4f47afa6a2c04c95f19acf66b1b10ae08cb3caf5cc623438421`。镜像身份见§4；没有用静态 app.openapi 替代原件。

按 FE3 §5.1 的 `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"` 规范化，FE3c 生产原件、S1a real-r4 原件、当前 t1/t4 原件**原字节和规范化结果均相同**；规范化146666字节，SHA256 `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a`。baseline 原件分别为 `/home/dev/gdds-reviews/artifacts/p6-openapi-6368c9c40c/production-openapi.json`、`/home/dev/gdds-stage-exchange/p7-s1a/g/evidence/real-r4/runtime-openapi.json`。

机器索引 `/home/dev/gdds-stage-exchange/be-b/b5-frontend-openapi-audit.json` SHA256 `6bfd316bf044b108aecc8257bd63ace62fc1366d2e62fee71a0d498cff0fc991`，逐一记录原件/规范化 SHA与字节数。其同目录 `b5-openapi-{fe3c-to-current_t1,s1a-to-current_t1,fe3c-to-s1a,current_t1-to-current_t4}.diff` 均为0字节、SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；规范化文件原样保留。

## 6. 稳定编码全集

[稳定编码替换表](../../../contracts/presentation-diagnostic-codes.md) 与输入目录 `diagnostic-codes.json` 同源交付：包括导航十二码及 params、Surface/Risk/records 分列 codes，以及 Surface 中 DUPLICATE_EFFECTIVE_KEY 参数尾缀、generic Python 异常类名与风险英文短句的替换。comparison facts/records 的 `DUPLICATE_EFFECTIVE_KEY:<table>` 保持原形式，只有 Surface summary 去尾缀；KEYLESS_FALLBACK、ORDERED_DIFF_UNSUPPORTED、ORDERED_PROVENANCE_MISSING/INVALID 和其余 typed emitter 错误空间均列明。比较 production 的 generic ValueError/OSError/ArrowException/TableAccessError 路径也向公开 records 发 COMPARISON_INTERNAL_ERROR；typed StandardComparisonError 的既有大写码保留。前端移除旧前缀/短句匹配并完整映射文案。

## 7. 相对 FE3c 的差异（S1a 与 BE-b 分列）

比较起点：FE3c main `fd9e383d76642037e4b3246c847222ea9483e033`，vnext tree `6368c9c40c`。S1a 最终 H=`42780a12303c8040526bf5dc8f9c6f0acb12dbb1`，tag=p7-s1a-exit。FE3c→P6 exit 期间已有内部缓存/计算重构，FE4 kickoff §6.2 记录其 API/业务产物无变化；不将它们算为 BE-b 新业务。

| 面 | S1a | BE-b |
| --- | --- | --- |
| 规范化 OpenAPI | 与FE3c原件逐字节一致，规范化 SHA见§5 | 与FE3c及S1a双baseline机器diff均空；当前生产原件/索引见§5 |
| tar logical_path literal 集合 | 原退出固定身份四组354/105/111/114相同；本次保留fresh原件的同输入v1复核354→354，但11增11删，不归一隐藏 | 同输入v1实测354→356，13增11删；精确列表见下列machine索引。该样本新增导航/诊断2成员，其余shared路径差异原样保留。完整t1/t4另含真实locator；History稳定pair名取代operation-pN |
| manifest 字段集合 | 同输入实测顶层11/递归62、closure递归34，均无增删 | 同输入实测仍11/62/34；bundle selector v3→v4、kind增加ROW_LOCATOR。另附Surface文件字段118→148（新增30递归路径），它是独立成员，不能误记为manifest新增字段 |
| ArtifactRef/摘要 | 四字段 shape 保留；ID 改 `a1:<location>:<64hex>`，混合 root；ref JSON raw 变化经原 integrity 传递至 surface/bundle digest；不删除 raw preimage | 沿用 a1 codec/raw 校验；Surface v4 表/locator 物理 raw 排除改由内容 binding；导航/展示列产生新 Surface 语义值，pair/view 命名改变 bundle metadata；comparison 业务摘要不因诊断编码字节替换而改变，records 物理诊断字节及其 raw integrity 引用改变。bundle 继续绑定所有实际 raw bytes |
| surface | selector v3/fields 保留；opaque ref 与 nested raw integrity 值变化 | v4；columns 两侧并集、present_in/pinned/display_order；replacement 本侧 display_name；table_content_bindings、row_locator_ref；恰一个导航；稳定 pair/view 与 codes |
| fixture | 固定身份只是 S1a 比较取证，不是 fresh 生产 IDs | 新 backend-owned 固定输入/真实 generator/五类 golden；不再手写导航/诊断，不再生成 no-navigation；前端整体替换并核原件 SHA |

同输入机器索引 `/home/dev/gdds-stage-exchange/be-b/b5-frontend-delta/index.json`，SHA256 `94a78f6459f9aa455c4b9f1a747705c52a407633bc4ac5fbc2016fc3656248ae`。其 `p6-inventory.json`、`s1a-inventory.json`、`be_b-inventory.json` 保留原 tar/state 路径及 SHA、完整 literal closure/ordinary tar 成员集合、顶层与递归字段路径；`p6-to-s1a.json`、`s1a-to-be_b.json`、`p6-to-be_b.json` 逐项列新增/删除，不去 UUID/hash/path。`*-table-bindings.json` 另将实际重命名路径按原table binding对应并核raw integrity，不假定物理字节相等。

三方均为实际 t1 v1、MODIFIED_ONLY、INITIAL空baseline，包SHA `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`、107115字节；旧state里的source ref与当前输入清单逐项相符。只比较该同输入同scope样本；当前v2 FULL不与历史v2 MODIFIED_ONLY混比。P6/S1a fresh原件各自源提交 `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809` / `8cb31da588db17994b18cccc22e4dc3b7b9f1110`，当前为V。**literal tar baseline 使用保留P6原件，不冒称新运行了FE3c树6368c9c40c**；`fe3c-to-p6-source-audit.json` 记录该区间bundle_assembly、surface_assembly及bundle_download源码均无差异，结合FE4 kickoff §6.2/S1a退出记录衔接。FE3c OpenAPI则是直接原件双baseline比较。

当前 t1/t4 的每一次真实 bundle 路径/字段原件在 `b5-real-37fe3a87d2/summary.json` 的 bundle_transfer；完整 tar 在各tier/bundles/，其 SHA逐个记录。t1覆盖MODIFIED_ONLY、FULL两pair、History2/3；t4为必要建点后的MODIFIED_ONLY及History2，未运行t4全旅程/三节点/性能矩阵。导航计数与locators同时由实际最终文件核对，不由consumer重算surface digest。

S1a 历史[总结](p7-s1a-summary.md)与原退出独审 `/home/dev/gdds-stage-exchange/p7-s1a/reviews/42780a12303c8040526bf5dc8f9c6f0acb12dbb1-exit-go.md`保留原限定。B5真实链结果/摘要分别为 `b5-real-37fe3a87d2/result.json` SHA `66e20b1c63843beab8503ab912f5a5973c5a59a3526232a74db33771799a407d`、summary.json SHA `00f35654340f67f74a52ec5e1ec1b32e951ac0dffc6c16f6dde056a3982a3126`；完整正式handoff与最终全范围核收/H绑定由协调者追加。失败V571的runner六失败、06 SQLite锁/SIGBUS停止原件继续保留，不以最终成功覆盖；SIGBUS具体触发时序未证明，不把已确认的SQLite原锁释放问题扩大成完整因果证明。
