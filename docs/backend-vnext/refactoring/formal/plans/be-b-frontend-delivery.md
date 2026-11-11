# BE-b → FE4b 交付

状态：B4 实施交付草稿。后端输入、真实生成器、五类 golden 与正式 Contract 已提供；最终生产 OpenAPI 原件、V/H/exit tag、当前镜像身份、集中门禁/真实数据及全范围独审由 B5 绑定后才可宣称 BE-b 退出。本文不启动 FE4b，不修改 frontend 产品或代签前端验收。

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

生成器显式固定 secrets.token_hex 的单进程序号→SHAKE256、各 materialization/publication owner 的时钟、repository、flow pair/view、单 kernel thread 与预算，全部记入 index。scratch 随临时上下文关闭；生产 fresh journey 不使用这些替身。comment-only 场景实际调用 accept_submit_transaction，原 no-op guard 返回 NO_CANONICAL_CHANGE，记录只读事务数、零写事务和零 Repository main 调用；fixture 的只读 control/baseline ports 在 index 明示。

前端 wrapper 只用 subprocess 调入口并整体替换 `backend/`；复制输入时逐文件核 manifest SHA。删除手写导航/诊断、fallbackNavigation 和旧无导航 fixture；不编辑生成产物。浏览器不重算 surface_digest，继续核 bundle/closure 摘要、ref raw SHA/size、同侧 Parquet metadata/BigInt 与形状。

场景覆盖普通两 pair、History 三节点、replacement、gid/地址变化且未改 cfg/点、UPDATE_ONLY suppressed 增删、重复/孤儿、整数 UTF8/安全边界、整数 registry 与文本数字 cfg 不混等、逐侧 IDENTITY_EXCLUDED、空 sg_cfg/点 schema、before-only 列、缺快照 context、keyless 第三次副本、改前公式/未变 device 别名、仅注释 Preview/实际 no-op Submit。EXACT 未记录行场景与 suppressed fallback 分开断言。

真实 business materialization 的 composite catalog 要求 device/测点地址为整数，且非空 device 具有唯一特殊身份；因此不伪造文本装置/文本测点可达的上传组合。文本数字反例使用允许的 device_cfg.gid TEXT，对整数 registry 必须 UNSUPPORTED_TYPE 整表降级。keyless identity frame 未包含筛选身份时必须唯一整表入口并按受影响侧报 IDENTITY_EXCLUDED；keyed 物理缺列走 COUNT_UNKNOWN/受限 fallback，不把缺列当比较排除。默认共享表规则不允许 keyless，keyless frame 分支以 owning capability 参数化测试验证；生成输出的 keyless_demo 证明真实 occurrence/locator。排除身份场景显式通过正式规则 decoder 注入对 device_st.dev_addr 的 compare exclusion，index 记录该非默认策略，不改变产品 registry。

## 4. 版本与镜像身份

最终合入 main H、H:vnext、BE-b exit tag、门禁 V/H 绑定、镜像 revision/source-tree 与 backend/worker/RS 真 OCI config digest/全部有序 RootFS DiffID：**B5 待补**。当前生成 provenance 见输出 index，不能替代最终 exit 身份。

BE-b 未改五锁、toolchain selector 或依赖基线输入，不为本轮新增 dependency-base；仍按节点实际预置依赖模式本机构建，network=none。Rust/产品逻辑已变，B5 必须重建产品镜像并跑对应容器门禁。S1a 镜像仅为历史来源，不称 BE-b 已通过。

## 5. 生产 OpenAPI 原件

**B5 待补当前候选生产 Compose `/openapi.json` 的 response.content 原件、SHA256、节点/起止 UTC/HEAD/镜像及取件日志。** FE3 §5.1 规范化固定为 `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`。静态 app.openapi 结果不替代生产原件；最终 current-vs-FE3c 与 current-vs-S1a 规范化结果均须有机器 diff。

## 6. 稳定编码全集

[稳定编码替换表](../../../contracts/presentation-diagnostic-codes.md) 与输入目录 `diagnostic-codes.json` 同源交付：包括导航十二码及 params、Surface/Risk/records codes，以及 DUPLICATE_EFFECTIVE_KEY 参数尾缀、Python 异常类名与风险英文短句的替换。比较 production 的 generic ValueError/OSError/ArrowException/TableAccessError 路径也向公开 records 发 COMPARISON_INTERNAL_ERROR；typed StandardComparisonError 的既有大写码保留。前端移除旧前缀/短句匹配并完整映射文案。

## 7. 相对 FE3c 的差异（S1a 与 BE-b 分列）

比较起点：FE3c main `fd9e383d76642037e4b3246c847222ea9483e033`，vnext tree `6368c9c40c`。S1a 最终 H=`42780a12303c8040526bf5dc8f9c6f0acb12dbb1`，tag=p7-s1a-exit。FE3c→P6 exit 期间已有内部缓存/计算重构，FE4 kickoff §6.2 记录其 API/业务产物无变化；不将它们算为 BE-b 新业务。

| 面 | S1a | BE-b |
| --- | --- | --- |
| 规范化 OpenAPI | 原退出独审八 tar/原件复核确认不变，规范化 SHA `4c2ddca7d64ec77029528f5a6f03f73b17185784091530c7086fa67d484d620a` | HTTP DTO/route 源码未改；当前生产原件与正式机器 diff 待 B5，不能提前写通过 |
| tar logical_path literal 集合 | 固定身份下四组集合 354/105/111/114 均与 P6 相同；原件保留 | 新 BUSINESS_NAVIGATION 与有诊断时导航 DIAGNOSTICS、标准 ROW_LOCATOR、device/composite before；History 稳定 pair 名取代 operation-pN。完整实际集合逐场景由生成 index 记录，变化类别不能替代具体文件集合 |
| manifest 字段集合 | 原 manifest 递归字段 62、closure 34，不变 | core manifest 顶层字段集合不加字段，bundle selector v3→v4、kind 新增 ROW_LOCATOR；嵌套 surface 增加列/内容 binding/locator 字段，完整字段与类型以新 Contract/golden 为准 |
| ArtifactRef/摘要 | 四字段 shape 保留；ID 改 `a1:<location>:<64hex>`，混合 root；ref JSON raw 变化经原 integrity 传递至 surface/bundle digest；不删除 raw preimage | 沿用 a1 codec/raw 校验；Surface v4 表/locator 物理 raw 排除改由内容 binding；导航 digest/展示列/pair ID 等产生新语义值。bundle 继续绑定所有实际 raw bytes |
| surface | selector v3/fields 保留；opaque ref 与 nested raw integrity 值变化 | v4；columns 两侧并集、present_in/pinned/display_order；replacement 本侧 display_name；table_content_bindings、row_locator_ref；恰一个导航；稳定 pair/view 与 codes |
| fixture | 固定身份只是 S1a 比较取证，不是 fresh 生产 IDs | 新 backend-owned 固定输入/真实 generator/五类 golden；不再手写导航/诊断，不再生成 no-navigation；前端整体替换并核原件 SHA |

S1a 来源：其 [总结](p7-s1a-summary.md) 与外部原退出独审 `/home/dev/gdds-stage-exchange/p7-s1a/reviews/42780a12303c8040526bf5dc8f9c6f0acb12dbb1-exit-go.md` §可见集合复核；本阶段不得改写历史原件。BE-b 的最终 machine delta（相同输入下 logical_path/递归字段集合与 OpenAPI）由 B5 追加原件索引；本文列出预期消费面及已经真实生成的集合，不把不同输入的字面差异算作业务变化。
