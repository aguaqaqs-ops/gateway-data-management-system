# FE4 kickoff 修订 8：FE4b 设计审核

**结论：定向修订。** BE-b 退出身份、OpenAPI 不变、依赖镜像和稳定编码的回源成立；F1–F13 的主要接入范围完整。暂不建议按当前文字发出实施提示词：无记录行复用的前端判定尚未与后端保证对齐，另有测试输入传递、定位判据、截图覆盖和带入项修法的缺口。下列 R8-1–R8-6 修订后定向复核；R8-7 同轮清理。

- 审核对象：`4d143e09725462a957ae28cf5780cfb969f824c8`，父提交 `3e5f24583dee3d3c44705e4ef34557890557568b`。区间只改 `docs/frontend-vnext/fe4-kickoff.md`。
- 对象文件 SHA256：`6bf21d88047e68c1306682a863331bd59a51e005483f4a8ab95864c54b2e1521`。
- 日期：2026-11-11，UTC。只读审核区 `/home/dev/gdds-fe4-kickoff-rev8-review`，detached 于上述对象；报告另在 `/home/dev/gdds-fe4-kickoff-rev8-review-report`、分支 `fe4-kickoff-rev8-review` 提交。
- 方法：文档、源码和已交付 JSON/tar 原件的静态核对；04/05 只读检查。没有运行测试、fixture 生成器、编译、Compose 或产品服务，没有修改产品、共享工作区、节点文件、镜像或占用标记。
- 本轮不触发镜像重建：纯设计审核。后端最后正式绑定是 `be-b-exit` 的 H `3e5f24583d`、`vnext` 树 `2faac9fc1d`；依据 tag 消息和阶段日志，04 的 H backend/container 实跑通过，rust 直接沿用 V `37fe3a87d2`。本轮镜像只核依赖身份，不冒称验证 FE4b 产品。

## 1. Findings

### R8-1 — P1：无记录行复用不能按尚未成立的等价式实施

**位置：** kickoff §18.2 第 2 项、§3.1 B4、§5.3 F5、§8 Contract 停止条件。

**问题：** ①–⑤不是已确认的后端复用判据，也不能据此推出“当且仅当页签为 EXACT”。将后端确认列为“不阻塞”，同时要求实现者遇到该歧义停止，会把设计已知的问题推迟到实施。

**依据：**

- `business_navigation/contracts.py::NavigationEvidence.fallback_reason()` 还检查 `risk_attribution_complete`；它不足时是 `RISK_ATTRIBUTION_UNAVAILABLE`。`NavigationTable.may_reuse_unrecorded_identity` 要求 `local_fallback_reason is None`，而①–⑤没有风险归属完整性条件。正式 Business Navigation 也允许记录完整而局部事实因风险归属不足进入 TABLE_FALLBACK。不能新增“①–⑤成立但 fallback 就拒包”的前端不变量。
- `application/business_presentation.py` 只把 `ComparisonTableStatus.SCHEMA_ONLY_CHANGED` 当作 `schema_only`；`surface_assembly/_assembly.py::_display()` 却把 SCHEMA_CHANGED 和 SCHEMA_ONLY_CHANGED 都显示为 `table_processing_mode=SCHEMA_ONLY`。①直接拒绝所有 SCHEMA_CHANGED，比 owning 条件“非 schema-only”更宽。已有 `schema-keyless` 的 `device_st` 就是 surface SCHEMA_CHANGED/SCHEMA_ONLY、导航 EXACT；该场景有双侧快照，不直接触发缺 before 复用，但足以否定将此等价式推广为一般解码不变量。缺 before 时到底从哪个公开事实区分两种状态，需要写定。
- ⑤“locator 存在时全部绑定成功”还应明确非零已发布 STANDARD 行记录的 locator 不能缺失；只有真实零记录/零计数的合法路径可以接受 null。不能把条件式检查当成完整性证明。

**最小修正：** **交 owner 转后端，作为 F5 设计收口前置。** 请后端确认当前公开 surface/compare/records manifest/locator 对复用条件的准确映射，说明风险归属 fallback 与 schema 变化的处理，再把 B4、F5、§18.2 写成同一判定。②依赖后端已把规则排除和不兼容身份改为整表入口的理由成立，可保留；但它不能补齐其他条件。不要要求前端重算身份，也不预设必须增加新字段。答复前可以继续不依赖该规则的工作，不能宣称 FE4b 设计已全部写定。

### R8-2 — P2：新单测读取的后端清单没有进入前端 runner 容器

**位置：** §5.3“上传输入”、F8、§18.4 的清单全等单测。

**问题：** 设计要求单测直接读取 `vnext/fixtures/presentation-inputs/manifest.json` 和 `diagnostic-codes.json`，但 `frontend/scripts/run-tests.sh` 只归档 `HEAD frontend`，容器解包至 `/tmp/frontend`；没有挂载或复制 `vnext/`。在完整节点 checkout 中存在文件，不等于 Vitest 容器能够读取。照当前方案写测试，权威入口会因缺文件失败。

**依据：** `run-tests.sh:101` 的 `git archive --format=tar HEAD frontend`，以及后面的 `SOURCE_ARCHIVE` 只读挂载和容器解包命令；F11 的 wrapper 只承诺搬运 `<output>/backend/`，这也不包含上述两个输入清单。

**最小修正：** 在设计中选定一条输入通路。例如 runner 从同一 HEAD 另归档这两个清单并只读交给容器，记录来源/摘要；或由受控生成/复制步骤在前端保存原字节副本，并在节点预检核其与同 HEAD 后端清单一致。明确单测实际路径，并纳入 runner/fixture wrapper 改动范围。无需把整个 `vnext/` 复制进前端测试环境。

### R8-3 — P2：定位程序判据漏了“该记录在该侧逻辑存在”

**位置：** §5.3 程序判据 4，及 B4/F5 的“有快照侧按 index 读行”。

**问题：** “每条行级记录在有快照侧的 index 处命中恰好一行”会要求 ROW_ADDED 在 before、ROW_DELETED 在 current 也有 index。表快照存在并不表示新增/删除记录在该侧有行。按此编写独立 helper 会拒绝正常 bundle。

**依据：** Row Location“身份与最终位置”“缺快照侧上下文”要求每个**逻辑存在侧**匹配，逻辑不存在侧的 index/context 都为 null。`row-location/preview-modified-only.json` 的 `device` 有新增、删除 locator；surface 的 before/current 表 ref 都存在，但对应不存在侧 index 正确为 null。t1 v2 的定位表也有 added/deleted，各 3 条。

**最小修正：** 按 record kind 明确矩阵：ADDED 只核 current，DELETED 只核 before，MODIFIED 核两侧；逻辑存在且有快照才要求合法 index，逻辑不存在要求 index/context 均 null；逻辑存在且缺快照、并发布筛选 tabs 时才要求 context。定位的一一对应只针对已发布 STANDARD 三种普通行记录，ordered/blank/schema 沿原语义。把非零记录缺 locator 的拒绝条件与 R8-1 一并写清。

### R8-4 — P2：所选 t1 页面不能替代退役截图的页签溢出覆盖

**位置：** §7.3 `tab-overflow` 退役理由、`fe4-t1-device-tabs` / `fe4-t1-forward-channel`，§18.2 第 7 项、§18.3 第 3 项。

**问题：** 设计因生成场景单项最多 3 页签而允许退役 `tab-overflow`，再称由这两张 t1 截图覆盖。然而它们固定在 v2 FULL 的 `initial_to_modified`；该产物转发通道只有 1 页签，装置最多 3 页签，与被认为不足的模拟场景相同。前者会按设计合法跳过，后者没有证明会溢出。

**依据：** 只读解析保留的 t1 tar `063b8cab8a954213932037bbfcaafcf8.tar`：两个 FULL pair 都是上述 1/3；v1 tar `18dbbdf638294503890da50d5613efd8.tar` 的转发通道/装置最大值是 10/12。读取的是已交付原件，没有重跑真实数据。

**最小修正：** 把这两个截图的选取改为 v1，或明确在已运行的 pair 中选取真正溢出的项，并断言溢出控件可用、滚动后能到达末页签。若具体宽度仍不溢出，不能写成已覆盖；组件测试保留该行为，缺口如实记录。无需增加旅程步骤或真实运行次数；同步截图时机、条件和文件数量说明。

### R8-5 — P2：N27 的修法没有处理实际丢字段原因

**位置：** §18.5 N27、§11.3 的 wrapper 审核要求。

**问题：** 设计要求只取 `^exit_code=` 整行以免误取 `main_exit_code`，但现有 wrapper 的 `report_field()` 已经这样做。04-b 丢字段的根因是上传校验入口只把退出字段追加到自身 `$LOG_FILE`，没有输出到 wrapper 捕获的 stdout/stderr。改正则仍会得到 `wrapper_field_missing exit_code`。

**依据：** `run-evidence-wrapper.sh:249` 已使用 `^${key}=`；`validate-upload-package.sh::finish()` 的退出字段块用 `>> "$LOG_FILE"`，最后只向 stdout 打印 `log_file` 与摘要。wrapper 只扫描 entry-output 段。

**最小修正：** 写定上传校验入口结束字段也输出至 wrapper，或 wrapper 在核对入口日志来源后从该文件读取。保留进程退出码 `ENTRY_EXIT` 为执行结果；不能因字段缺失改成成功。`busy_end` 的时机修正可照原建议。验收分别覆盖上传校验和真实 backend 入口，证明得到最终 `exit_code`，不会误取 `main_exit_code`。

### R8-6 — P2：FE4b 的角色与交付约定仍沿用已结束的 FE4a 例外

**位置：** 头部会话分工、§11.3 的发提示词/报告/handoff 安排，§6.4 的推进分工。

**问题：** 设计仍引用已不存在的 AGENTS“角色与子 agent”，直接称“框架与 FE4a 相同”，要求后续 handoff/审核报告入库，没有明确持续协调者、风险定级及独审不同模型家族。

**依据：** 审核对象自身的 `AGENTS.md`“流程与角色（P7-D25/D26）”明确前端从 FE4a 后下一步生效；P7-D26/D27 保留的是 FE4a 既有安排。流程规格又明确前端继续使用现有前端脚本，不需为切换流程引入后端按包门禁。不能把“前端入口未换”理解成“角色和材料位置都不换”。

**最小修正：** 仅改 FE4b 的未来安排：明确持续协调者、按实际风险划分的工作包与独审/最终全范围审核责任、不同模型家族要求；handoff/审核/运行材料放阶段交换目录，正式设计与退出总结入库。保留历史 FE4a 记录不改。如确需延用旧安排，应列成明确的 owner 例外，而非默认继承。本轮报告按用户明确指定的位置提交，不据此替未来 FE4b 批准例外。

### R8-7 — P3：清除当前执行条款中互相冲突的旧句

**位置与最小修正：**

- §7.2 的“t1 调试只有一次，需要第二次由 owner 决定”限定为 **FE4a**；FE4b 的两次建议继续以 Q23 为准。
- §11.3 首段“刷新 OpenAPI”改成“不刷新”；§5.2 FE4b 行同样同步。§6.3 已证明不需要刷新。
- §11.3 handoff 的“§18.3 列出的只由单测覆盖的编码”改指 §18.2 第 7 项。
- §3.3、§7.3、§8、§11.3 尚在生效语境中写“第 2 步写定”的句子改为具体落点；历史修订记录可以保留。

## 2. Q22–Q25 的意见

| 问题 | 审核建议 | 理由与边界 |
| --- | --- | --- |
| Q22 | **建议改为有条件的甲：先明确 `fe-handoff` 的可验证基线，再决定是否把其退出设为 FE4b 送审前置。** | 两者顶栏重叠、在最终候选前集成并统一看图的理由成立；三种合入情形和树/路径检查本身可执行。但 `fe-handoff` 从最新 main 开始，要求现有 e2e-real 不改且通过；现在 main 已含 BE-b，而原前端仍按 `{column,value}` 消费导航，尚未实现本轮 F1–F13。不能仅凭其范围小就假定可以独立先退出，也不能把既有测试偶然通过当成新 Contract 已适配。请 owner/两任务协调者先写定它的后端基线、真实回归范围与遇到 BE-b 不兼容时的归属。若需先交付 FE4b 的适配，可先并行完成会话模块，在最终候选前集成后取证；不要形成相互等待，也不在退出合并后留下未经验证的树。 |
| Q23 | **同意建议，修正 R8-2/R8-3/R8-4/R8-7 后执行。** | bundle 解析影响全部下载旅程，完整 journeys 调试有依据；最多两次且第二次有触发条件，审核不再独立跑真实数据，符合 DC30/DC33/DC98。四项最终证据含上传包校验和 20 scope 完整集，没有遗漏。不需要 t2–t4；打包改变的 t4 例外保持。DC68 工具错误与产品 finding 分开，不能把“还有第二次配额”当作不保留失败的自动重试许可。 |
| Q24 | **同意纳入/推迟的分界，修正 N27 的做法。** | 原带入清单完整，N14/N17 原件在复审第 2 轮，修订 8 的归属正确；统一工作台原生按钮是可选项，可不并入本轮。N24 不应写成已经能由 r11 覆盖：现有 r11 是 REVIEW_VERSION_CONFLICT，刷新清除错误后再关对话框，不是过期 APPROVE/ARCHIVE_CLOSED 的关闭后顶栏提示。按设计已有的“到不了则记录未测”处理即可，不为这一项另加完整真实旅程。 |
| Q25 | **同意建议。** | 推送退出 tag 会传送其祖先对象，包括 S1a、BE-b；不移动远端 main。这一影响已说清。最终推送仍以 owner 的决定为准，本轮不推送。 |

`fe-handoff` 的会话优先级、无 display 的测试注入、布局重叠和“合入后目录任务才进阶段 2”均与其 kickoff/I6 相符；本地未发现对应分支。截图归因采用其自身证据作基线合理，但需在正式提示词中指明该证据的提交、目录和 SHA；最终稳定性比较仍比较同一 FE4b 树，不能拿两个阶段不同的树作稳定性判据。

## 3. 其余核对结论

### Contract、输入与诊断

- F1–F13 引用的正式 Contract 节均存在，主要归属正确。FE-BEB-01–11、13 的关闭落点成立；12 的后端文字已补齐，但**前端消费判定**仍有 R8-1。B4 摘要方向正确，具体实施规则不能早于该项关闭。
- 五类 golden 各 17 个文件；输入清单列 17 个必需目录和 2 个根文件。输入文件 SHA 全部相符；8 个原件与所列 `59c5b8cfca` Git blob 逐字节相同。canonical 派生输入与 e2e-real 派生输入分别管理合理。
- 诊断码机器差集：现有 surface 文案键 49 个，正式集合 48 个；新增/恢复 6 个、删除 7 个，逐项等于 §18.4。导航由 10 增到 12，旧 10 码 params 键集合未变；Contract 十二码及 params 与 JSON 全等。`BLANK_PROVENANCE_INVALID` 作为 native retained 错误空间恢复合理，不推翻旧 Q21 对当时主动产生点的结论。
- 新文案没有原始异常或路径；surface 新键沿用旧文案符合此次替换范围。导航两条新提示还承担 fallback/整表行为说明，不能把这些提示误当 surface 的降级原因。未知码保留通用文案/Debug；不需要为文案补整份后端场景。
- 生成器可以在 05 的后端环境执行；本轮只确认环境目录和 Rust 1.97.0 工具链存在，**没有验证离线同步成功或缓存完整**。实施前按已写定的强制重装扩展、build-input 和离线规则预检即可。两次生成及审核独立生成可保留；比较 `backend/` 时不要把外层含 `generator_commit` 的 `index.json` 当作跨提交必然相同的产物。

### 截图与覆盖边界

- 新增模拟接口截图表有 19 个常规名字，合入 `fe-handoff` 后 20 个，即 38/40 个文件；t1 是 7 个原名字加 4 个必选和 2 个条件名字，即 22–26 个文件。数量表达一致，R8-4 修改时同步。
- `duplicates-orphans` 的三页签项实际是 `device:composite`；普通 `device:addr:49` 为两页签。实施时应明确选中前者，不能随便选“第一个普通装置”。重复地址/gid、孤儿提示确实存在。
- `table-addition` 有 `table_scope`，但目标 `device_st` 为零行；这张图可证明表级标记，不能独自证明“不涂到各行”。后者用 F7 同列的 `identity-changes` 非空场景/组件断言覆盖即可，不需另造真实数据。
- `schema-keyless` 有 before-only 列；`preview-modified-only/keyless_demo` 有两条两侧 index 都为 null 的删除定位；`formula-unchanged-device/device` 的 before/current ref 完全相同，composite 有修改；相应截图来源成立。
- F5 的正向复用验证应具体落在 `duplicates-orphans` 缺 before 的共享表；`identity-unrecorded-exact` 的未变共享表已有 before 别名，适合验证 gid/地址变化的归属，单用它不能证明缺快照复用分支执行过。

### BE-d 向量、入口与停止条件

- **同意 §18.3 第 1 项的总体处理，不要求后端仅为 selector 更新重新交付 BE-d tar。** `tar_stream.py` 在所列区间无变化；保留生产 PAX/size 向量，v3 完整包改反例；真实下载的 v4 验证生产 encoder→浏览器，生成 fixture 的 v4 覆盖安装逐成员完整性。必须同步 `interop-fixture.test.ts` 的旧完整安装用例；三种 e2e 模式的截断/损坏反例要基于有效 v4 包，证明是在对应边界失败，不能都提前失败于 v3 selector。原逐文件 size/SHA、失败后无已安装目录等断言保留。没有丢弃这些结论，就属于设计会话可作的实现安排。
- 两个后端 `frontend/` 提交确为 `7b16061b2e`、`b79fd4c72f`，在 FE4b 全范围审核中审并由第一次 journeys 调试验证合理，不另加一次真实运行。成功清理路径之外，静态审核须核主失败/清理失败的退出码、本人资源归属和凭据删除；不需扩建故障矩阵。依赖 helper 的通知规则可作为协调约定，不阻塞产品。
- §8 已覆盖 fixture 输出/确定性、合入树、后端异常、身份/缓存、OpenAPI、新入口清理、超次数、截图找不到对象和豁免删除。缺口主要是 R8-1 已知歧义不能仍标“不阻塞”。停止失败执行及依赖验收即可，不自动停止无依赖工作。
- BE-b 交付/总结的旧状态行属于退出前记录。tag 和阶段日志有最终 H 核收事实；可以另请后端同步文字，不要求本轮重开后端验收。

## 4. 回源与节点记录

### 十六进制与文件

对 `git diff --unified=0 3e5f24583d 4d143e0972` 的新增文字用 `python3 -I frontend/scripts/check-handoff-hex.py` 核对：**41 个不同完整值，Git 对象 28、SHA256 10、非 Git 镜像 tag 后缀 3；未命中 0，长度异常 0，截断形式 0，exit 0。** 三个后缀 `578e079b762e`、`6dc9659f0aee`、`b47d6de3cbce` 显式按镜像 tag 处理，不伪称 Git 对象；前两当前/历史来源分别回查 BE-b/FE4a 交付。工具结果之外，另外核对了以下绑定关系，避免“对象存在”代替“引用正确”：

- `4d143e0972` 的父提交、`be-b-exit` tag 对象及目标、S1a tag 目标、V/H 的 vnext 树、main frontend 树；FE4a 目标是 H 的祖先，可快进，均与设计一致。
- 开发主机重算 BE-b delta `index.json`、OpenAPI audit、镜像完整索引、输入清单及设计文件 SHA，均与设计相同。
- t1、t4、FE3c 三份生产 OpenAPI 原件均 79082 字节、原 SHA 相同；按既定 JSON 规范化均 146666 字节，并与提交的前端快照逐字节相同。
- golden 五类计数、输入目录/根文件数、8 个来源 blob、诊断码与 params 均独立读取核对；截图原件清单在 04 重算，198 张 PNG。

本轮原始核对材料保存在 `/home/dev/gdds-stage-exchange/fe4-kickoff-rev8-review/`：`added.md`、`hex-check.log`、`source-sha256.txt`、`node04-files.log`、两个镜像流式核对日志、`static-audit.json`。脚本的路径配对有已知 N20 限制，本轮文件配对另由明确路径的重算补核，未只依赖“SHA 在某份文字中出现”。

### 节点

| 节点/hostname | UTC | 方法 | 结果 |
| --- | --- | --- | --- |
| 04 / `gw-dms-test-04` | 08:03:26 | `ssh -o BatchMode=yes`；核占用目录 | 连接 OK，无占用标记 |
| 04 / `gw-dms-test-04` | 08:04:00–08:04:15 | `docker save gateway-backend-deps:lock-578e079b762e` 流式交标准库读取 manifest/config，不落节点磁盘 | config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`；全部 **19 个有序 DiffID** 与 BE-b 完整索引相同；exit 0 |
| 04 / `gw-dms-test-04` | 08:04:15–08:04:20 | 同法读取 `gateway-p2r1-repository:lock-b47d6de3cbce`，调用前再次核无占用 | config `sha256:567e7bf95a9a226efb7e557260d494b63c1f3c865de53eb6860c181703db9c13`；全部 **19 个有序 DiffID** 相同；exit 0 |
| 05 / `gw-dms-test-05` | 08:05:24 | BatchMode SSH、只读目录/文件存在检查 | 无占用；uv 缓存、Cargo registry、Rust 1.97.0 工具链、backend `.venv/bin/python` 和 t1 输入目录存在；未运行 sync/生成器 |
| 04 / `gw-dms-test-04` | 08:07:04 | 无占用时重算 npm 缓存归档、截图清单 SHA；计数 PNG | npm `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；截图清单 `3db69cef9dc15ac8adeece2d52ce061f108ac4b754db384ebbaa4a77f233aa35`；198 张，均与设计一致 |

镜像比较未使用 `docker inspect` ID，没有 build/tag/load。05 的存在检查不代替正式预检；07 未独立登录，本报告不将设计会话的三节点核对冒称为本轮实测。

修订后交回本审核会话做定向复核，再由设计会话请 owner 确认 Q22–Q25；本轮不合入 main、不推送，也不写 FE4b 正式实施/审核提示词。
