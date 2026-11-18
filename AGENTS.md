# AGENTS

本仓库的 agent 硬约束。完整背景见 [docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。
脚本已经强制执行的步骤不在本文重复，以脚本及其说明为准；本文只列脚本不强制、需要人或 agent 自己遵守的约束。

## 项目前提

这是全新项目：没有已部署的使用方、没有需要保留的历史数据，也没有兼容或迁移要求。

- 改 Contract、checkpoint 载荷、digest 或 HTTP DTO 时，直接改到目标形态，不建设兼容层、
  双读/双写、旧字段别名或数据回填；同步更新 golden 与测试。control DB 以单一基线 schema
  创建（P5 收口设计 DC6）：改 schema 时直接修改基线，schema 与代码不符即拒绝启动，开发者删除本地
  control DB（含 `-wal`、`-shm`）后重建；首次出现需要保留数据的部署时，再引入前向 migration。
- 删除被替代的实现，不保留“以防万一”的旧路径。
- `legacy/` 只作行为与数据格式的参考来源，不是兼容目标；vnext 与真实数据不一致时，以真实
  数据和 owning Contract 为准。
- 这不放宽阶段内的冻结约定：某阶段声明“不改行为”时，golden 与 digest 仍作为该阶段的回归
  基准。

## 新代码的校验与身份（Owner 2026-11-12）

适用于新增和本次改动的代码；存量不为此批量删改，专项改造由 Owner 另定。

- **校验：**有静态类型的字段不再做运行时类型复检，`__post_init__` 只写取值和跨字段的不变量。新增或改字段的文档类型，从字节解码时用 pydantic 严格模式并禁止多余字段，不再手写解码函数。逐行计算用的对象不用 pydantic。
- **身份与版本：**新增 digest、ID、版本常量或状态枚举，要在设计里写明它防的是什么、由谁核对；只计算不核对的不加。

## 流程与角色（P7-D25/D26）

后端自 P7 S1a-C 起按本节执行（P7-D27，见 [S0 决议 §7](docs/backend-vnext/refactoring/formal/plans/p7-s0-owner-decisions.md#7-b-收尾后的流程切换owner-后续确认与安排)）；流程变化不改变产品范围和验收要求。

**前端角色安排（Owner 2026-11-11）：**前端暂不需要固定长程任务的角色分工，无需参考后端角色分配规则。下列角色、上下文、模型家族及按角色分包要求仅适用于后端。

- **默认模型（Owner 2026-11-18）：**持续协调者 `gpt-6.1-terra` / high；每包实施者 `gpt-6.1-terra` / high；独立审核者 `gpt-6.2-sol` / xhigh，复杂判断可 max。后续新建审核角色采用；已启动任务的原 finding 仍由原审复审。
- 后端每阶段一个设计会话和持续协调者；协调者按比例化政策 §4 的实际后果定 A–D 风险、触发门禁、合入并维护阶段日志。每包新实施上下文，内聚的两三个小包可合并。
- A/B 类逐包独审；C/D 类由实施者与门禁完成。阶段末一次全范围独审覆盖全部包；独审须新上下文并使用与实施者不同的模型家族。同一 finding 原审复审。取消专职测试者，门禁由脚本执行，focused 由实施者执行；不自动递归扩队。
- 设计、Contract、正式决议入库。handoff、审核意见、提示词及运行材料放仓库外 `/home/dev/gdds-stage-exchange/<stage>/`；提交加追加式阶段日志交接，退出只入库一页总结。历史过程文档不改写。本文与 testing-conventions 中仍称 handoff 的记录项，由阶段日志或机器结果承接，不再入库。
- **阶段总结写给人看（Owner 2026-11-12）：**一页，写做了什么、与设计的偏差、遗留事项。SHA256、日志路径、run ID 这类机器记录不抄进总结，用引用指向门禁结果目录（阶段交接区的 `gate/`，原件位置记在其中）。模板见流程规格 §4，其“验证”一行按本条只写结论、未测限制和引用。
- 节点选择与原子占用、已授权范围内可逆实现细节、风险定级和已确认环境/命令错误的修复，由协调者按下文默认规则自决。只将产品范围、验收范围、来源冲突、不可逆操作交 Owner 决定；他人资源冲突先针对性协调，不擅自抢占。runner 失败停止本次及依赖验收，不能归作环境错误掩盖产品 finding。
- 审核 worktree 用毕、finding 关闭且无消费者即回收；不删除在途阶段、固定门禁/carried 来源、dirty 或用途不明工作区。批量回收先向 Owner 展示数量及排除项，执行前复核，不 force。

门禁、交接目录、总结模板和实施安排见 [流程规格](docs/backend-vnext/refactoring/formal/plans/p7-gate-and-stage-workflow-design.md)。

### 代码独审与验收核对

- `gpt-6.2-sol` 主要审核代码、架构/Contract、一致性、安全及门禁错误放行风险，并核对必要的关键要求和证据。
- 交付清单、原始日志/证据完整性及截图对照按需交 `gpt-6-luna` 核对，逐项引用提交与原件，区分通过、失败、未知；业务语义、安全、一致性或证据矛盾交独审者或设计负责人判断。
- 确定性的提交/退出码、测试结果、文件完整性、截图尺寸和摘要检查优先纳入既有门禁；视觉与语义正确性仍须核对。门禁由实施者修改，经独审和专用节点验证后采用。
- 核对者不改产品、门禁或验收标准，不自行重跑测试或增加监视任务。交付/阶段验收时集中启用，不逐小包常驻，也不强制前端增加固定角色。
- 协调者分别核收代码独审、必需门禁和适用验收核对结果后按既定权限放行；原始失败和未知不能被摘要覆盖。记录复用现有交接区。

## 跑测试

后端阶段门禁入口，在开发节点触发，经 SSH 在 `ct108-gw-dms-04` 的固定 worktree 执行：

```bash
scripts/run-stage-gate.py <full-sha> [--packages <列表>] [--purpose package|stage|s3-ready|s5|release|production] [--fresh] [--session <名>]
```

脚本调用权威 runner `./vnext/scripts/run-tests.sh`，占用、环境准备、闭包查表与容器等价、身份与日志记录、清理都由它执行，不手工重复，结果不手抄。参数、04 节点配置、结果位置和失败语义见 [`scripts/README.md`](scripts/README.md)；runner 与闭包的行为说明见 [执行入口](docs/backend-vnext/testing-conventions.md#执行入口)。脚本不强制、仍须遵守：

- 权威运行必须在专用节点、clean 已提交 worktree 上进行；期间不写被测树、不改相关镜像（runner 的既定构建例外保留）。同节点整机单飞、离线预填充、保护真实输入及原始证据、失败不冒称通过都是硬约束。
- **工作包与最终门禁档位：**工作包门禁使用 `--purpose package`（跳过 `container` 用例与容器门禁）；若改动命中 [触发式重建](docs/backend-vnext/testing-conventions.md#docker--compose触发式重建) 清单，相关改动收敛后用 `--purpose stage` 跑一次；阶段最终候选必须在最终 HEAD 上有 `--purpose stage` 结果；S5、发布与最终 production gate 选对应 `--purpose`（强制六包 fresh、最终 HEAD 重建），不用 `package` 或普通 `stage` 结果替代。阶段性验证只跑所需 focused/marker 范围，不跑全量。
- 按包沿用和容器结果沿用只以脚本查表结果为准：不手工计算 carried，不把其他节点或其他 worktree 的记录当来源，不手工创建固定门禁 worktree 或删除其归属记录。
- 占用冲突（exit 3）不抢占，稍后重新触发。修正后新开一次运行，不覆盖失败记录；中断后残留的占用标记由协调者核远端进程和结果后处理，不直接删除。
- 脚本不覆盖真实数据旅程和前端，它们使用各自入口。门禁之外的手工运行（focused、真实数据旅程）仍按 [执行入口](docs/backend-vnext/testing-conventions.md#执行入口) 自行满足 `legacy` 链接、`TMPDIR` 和日志记录要求。

### 专用测试节点

所有测试与取证都在专用节点执行。节点上的测试、编译、lint、构建、e2e、取证和有写入的清理按[执行入口](docs/backend-vnext/testing-conventions.md#执行入口)办理。执行时核现场空闲、服务/端口、有效标记，再原子取得本节点占用；自行管理标记的入口由入口获取。只读核对无需占用，不抢占或删除他人标记。五节点按实时空闲、工具链、缓存和输入选择，自动门禁固定在 04。

- 同节点整机单飞，计时独占。按 DC97，仅实际占用、资源干扰、共享文件写入或涉及他人资源时协调。生产预算、清理范围及逐项清理前后空间记录均按上述执行入口。
- 启动长测、等待他人长测或正式测量前，先读执行入口的节点段和[长时间执行与分工](docs/backend-vnext/testing-conventions.md#长时间执行与分工owner-2026-11-09)，遵守唯一执行者、巡视频率、物理拓扑、并发初始值与同组测量条件。
- 直接调用 runner、同步环境、编译 Rust、跑 Compose 前，或依赖、锁、工具链、基础镜像有变化时，先读[测试节点网络与缓存](docs/backend-vnext/testing-conventions.md#测试节点网络与缓存owner-2026-10-28)。测试 CT 禁止直连公网，逐节点核实获准 LAN 和预填缓存，缓存缺失或 LAN 不可达即停，补齐后从头运行。代理例外限 05 调试构建，结果不作证据。跨节点镜像身份、client e2e 重建和来源记录按该节执行，日志、阶段日志和节点配置不得含凭据。

### 构建故障快速修复（Owner 2026-11-10）

- **适用与授权：**命令/路径错误、获准缓存未就绪、可安全修复的本地环境/临时空间问题等，确认未改变程序逻辑、依赖选择、部署语义和测试预期后，执行者直接“定位 → 修正构建条件 → 重跑失败步骤”，无需逐次经评审、申请恢复或换角色。有诊断依据的新方案时可继续排查。重跑失败步骤前须有具体修正或已核实的环境变化，满足条件后的复跑**不设固定次数上限**。
- **何时停：**需要新权限/他人资源、存在来源冲突或无法确认副作用/安全收尾等真实阻塞时，才停止受影响部分并说明所需决定。只停当前失败执行和依赖验收，无依赖的实施可继续。
- **边界：**程序编译/类型错误、运行时行为或产品正确性问题回正常实现/评审流程，不能因发生在 build 就归为环境故障，产品 finding 不归入构建故障。修改仓库构建脚本、Dockerfile、锁/依赖、entrypoint 等源码，由实施者修复并经原审一次针对性代码评审。本授权不含产品源码、资源预算或验收范围的修改权；不得在测试运行中写被测树/重建相关镜像、清理他人资源、跳身份或改预期；已失败的 runner 不续接为合格证据。
- 其他工具/取证错误不适用本节，按 [testing-conventions](docs/backend-vnext/testing-conventions.md#测试节点网络与缓存owner-2026-10-28) 的 DC68 现行规则。动手修复构建故障之前先读 [构建故障快速修复](docs/backend-vnext/testing-conventions.md#构建故障快速修复owner-2026-11-10)：故障条目的记法、评审顺序、从哪一步重做。

### 手工运行与依赖消费

- Rust 改动后跑 backend focused 前须用 `--reinstall-package gateway-compute-python` 强制重装扩展，不能使用旧 `.so`；见 [Rust 扩展规则](docs/backend-vnext/testing-conventions.md#rust-包与-backend-的-rust-扩展dc48)。
- 不盲目并行 serial：手工运行 `serial and not parallel_safe` 组始终 `-n 0`；新增 `parallel_safe` 须逐项隔离审查，backend 当前无此例外。条件与 marker 命令见 [测试批次](docs/backend-vnext/testing-conventions.md#测试批次与-focused-运行)。
- `GATEWAY_TEST_BASETEMP` 的 tmpfs 只用于 pytest 临时目录；持久化、崩溃恢复和快照验收必须用真实文件系统。
- 所有 uv 消费使用 `./vnext/scripts/uv-consume.sh -C vnext/<package> <sync|run|lock-check|pip-install> ...`，Host 依赖准备使用 `./vnext/scripts/prepare-dev-dependencies.sh`（不跑测试）。保持 canonical registry identity，禁止隐式改锁；依赖变更须显式授权并重新同步。Docker build 网络与 uv bootstrap 参数只影响构建，不进入 production runtime、不改变 Compose 服务网络。改 index 模式或构建参数之前先读 [内网构建环境变量](docs/backend-vnext/testing-conventions.md#内网构建环境变量仅记录名与语义不得写入-lockfile-或-production-runtime)。

## 前端测试（FD7）

依据 [前端 kickoff §6](docs/frontend-vnext/frontend-kickoff.md#6-测试与证据fd7)（owner 2026-11-02 确认）。运行前端入口、准备工具链镜像或 npm 缓存、做截图验收之前，
先读 [testing-conventions.md “前端测试”一节](docs/backend-vnext/testing-conventions.md#前端测试fd7)：镜像与缓存的取得流程、日志内容、截图宽度与核对项。

- 前端使用独立入口。按 [FD7 的 npm 缓存规则](docs/backend-vnext/testing-conventions.md#npm-依赖缓存dc67)核对归档摘要，留意前端整顿退出合入后的切换条件。
- **后端改 `frontend/`（owner 2026-11-11）：**后端会话改动 `frontend/` 下任何文件（包括 `frontend/scripts/` 中的真实 backend e2e 入口）之前，先告知前端设计会话改动目的与范围。这类提交属于前端审核范围，由前端设计会话列入当前或下一个前端阶段的审核与调试（起因见 [FE4 kickoff](docs/frontend-vnext/fe4-kickoff.md) 的 FE4a 退出记录）。
- 真实 backend e2e 必填 `--session`，由入口取得、核对和释放占用。其他入口由执行者取得占用，核本机 Dolt/Compose、8000 端口及资源干扰，清理本人运行后释放。镜像或 npm 缓存缺失、身份不符即停止，按 DC67 从 CT201 补齐后从头运行。截图偏差须修正或交 Owner 确认。

## 写测试

`backend` 与 `repository_service` 的五个 marker 已声明，`--strict-markers` 生效，拼错会导致收集失败。

- 遵守 [marker 分层](docs/backend-vnext/testing-conventions.md#marker-分层)的 Dolt 门禁、fixture 自动分类和显式 `integration`、`serial` 标注规则。启动真实 Docker 或 Compose 必须同时标 `container` 和 `serial`。
- **artifact ID（Owner 2026-11-12）：**除 golden 和 ID 格式校验的测试外，backend 测试经 `build_artifact_id`
  （`gateway_backend/artifacts/location.py`）生成 artifact ID，不手写 `a1:` 字面量。已有的字面量在下次改到该文件时
  顺手改，不为此专门返工。
- 改动分类后，按[分类验证](docs/backend-vnext/testing-conventions.md#分类正确性怎么验)在专用节点取得占用、移开 Dolt 并运行 unit 组。

## 测试性能红线

遵守[性能约束](docs/backend-vnext/testing-conventions.md#性能约束)的四条要求：纯解析、校验和类型映射禁用真实建仓 fixture；同构用例共用模块级参数表；按批构造前置状态；新 Dolt HOME 预置关闭 versioncheck 的配置。

## 改依赖

各包依赖一律精确钉版本（`==`），用 `uv add --dev` 添加。

改动 `vnext/repository_service/uv.lock` 后，**必须**同步更新
`vnext/repository_service/Dockerfile` 里的 `ARG UV_LOCK_SHA256`（`sha256sum vnext/repository_service/uv.lock`），否则
`test_dockerfile_uv_lock_sha256_matches_lockfile` 会失败。

## 主线开发与阶段边界

- 直接在 `main` 上提交，不为每个阶段开分支；只有确需并行的工作才开短期分支，并尽快合回。
- 阶段边界用附注 tag（例如 `p5-s1-exit`）标记；审核对象是 `<上一阶段 tag>..<候选提交>` 的提交区间。
- 审核与复审在只读 detached worktree 中进行（`git worktree add --detach`），不在主工作区运行测试；
  测试运行期间任何人都不得在被测 worktree 中写入。
- 调试与取证分开：调试期间只跑必要 focused 测试与受影响的真实数据段；收敛后在最终候选集中完成必要权威包、容器门禁及 Owner 确认的最小真实范围。阶段按实际闭包运行或合格沿用，不默认完整旅程或重复性能采样；项目最终/发布门禁仍运行全部六包。真实范围在 kickoff 写明、阶段退出前由 Owner 确认（DC33、DC98）。
- 未经 owner 授权不推送，不改写已被审核引用的提交。流程细节见
  [流程规格](docs/backend-vnext/refactoring/formal/plans/p7-gate-and-stage-workflow-design.md)。

## Docker / Compose 验证

**工作包做针对性验证，阶段最终候选集中构建验收**（Owner 2026-11-10）。工作包交接、独审轮次或角色更换使用 `--purpose package`（或聚焦测试），不触发完整镜像构建、容器测试或完整真实数据旅程。报告中工作包档位的容器门禁记为 `deferred`，不写通过，也不阻塞无依赖的后续实施；不得用延期关闭已发现的正确性问题。

- 改动容器边界（镜像与依赖构建、entrypoint/Compose/环境变量与 healthcheck 接线、UID/GID/权限/mount/socket/pidfile/broker、依赖容器隔离才能证明的 startup/shutdown、Docker/Compose e2e 与 harness），或要判断某项容器验证该提前做还是延期之前，先读 [触发式重建](docs/backend-vnext/testing-conventions.md#docker--compose触发式重建)：逐项清单、提前做最小容器验证的条件、可延期的情形、依赖基础镜像何时重建。
- 旧镜像结果只能作为回归证据，不得表述为当前 HEAD 已验证；要宣称当前 HEAD 已通过容器门禁，须有绑定到它的门禁结果。
- 阶段退出时最终候选 HEAD 必须有绑定到它的容器门禁结果，重建实跑还是沿用由门禁脚本判定（条件见 [镜像身份等价](docs/backend-vnext/testing-conventions.md#镜像身份等价与结果沿用)）。S5、发布及最终 production gate 必须在最终 HEAD 重建并完整运行六包，不查表跳过。

## 全局比例化保障

按[DC98](docs/backend-vnext/refactoring/formal/plans/p6-s0-owner-decisions.md#dc98-业务正确性优先与s4验证范围收敛owner2026-11-09)，各阶段以新增/受影响业务正确性为主，不默认逐阶段全量测量、合成放大、预热加重复采样或细粒度profiling；性能/容量专项按明确目的、范围和成本另定。合格来源依原规则复用，最终必要门禁、冻结语义、资源硬边界与已发现finding不因裁剪取消。真实数据按改动面提出最小范围，由Owner确认；未运行或未知不写通过，取消项不自动转交后续阶段。

Phase 0–9及后续维护统一遵守
[Proportional Assurance and Risk-Based Verification Policy](docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)。

- 新安全、恢复、一致性、evidence或治理机制必须对应当前威胁、明确业务损失、已确认consumer
  或已发生的可复现故障；否则使用标准平台能力和最小机制。
- 先区分权威/不可逆事实、可恢复durable状态、derived/temporary状态和内部实现细节。
  前两类保持强Contract、事务/CAS/幂等及关键crash验证；后两类优先bounded处理、重试、诊断
  和人工处置，不自动建立同等证明。
- 同机受控模块、worker和同一Service euid默认属于单一信任域。新增独立UID/helper/service、
  自定义IPC/capability、持久evidence状态机、sidecar/quarantine/tombstone或syscall-window
  安全证明前，必须先修订owning Contract/ADR，不能由普通审核Finding直接扩大威胁模型。
- 测试证明Contract语义屏障，不穷举内部步骤。每个不变量只有一个权威测试owner；测试按业务
  行为命名，不按round/finding编号命名；删除production机制时同步删除其mock和证明探针。
- API认证授权、secret、caller输入、path/archive/symlink/root逃逸、非shell执行、资源上限、
  transaction/CAS和跨scope误写等基础边界不能用“比例化”跳过。

## Artifact cleanup 保障边界

权威决策是
[ADR 0012](docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：
V1同机Service进程属于单一信任域。实现和评审聚焦协作并发、崩溃、I/O错误、protected
artifact、server-owned path与root/symlink边界；不要为同euid恶意pathname换名新增broker、
sidecar状态机或安全探针，除非先按reopen conditions修订ADR。

cleanup测试按Contract行为命名，不按`r8_*`、`r19_*`等修复轮次命名；不可逆的Dolt commit/
main CAS、control DB事务和跨root误操作仍保持强验证。完整测试取舍见
[docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## backend 源码门禁

`vnext/backend` 的格式、跨目录私有导入、HTTP 导入 domain policies、函数复杂度遵守[四条门禁](docs/backend-vnext/testing-conventions.md#backend-源码门禁)。审核者须沿路由到应用层用例入口核对实际授权调用。C901 存量豁免按函数登记，只减不增。

## 提交前

五个 Python 包都要过 ruff 与 mypy（`repository_service` 为 `strict = true` 且覆盖
`tests`），不要为了省时间跳过：

纯文档、设计或只读审核且明确未授权产品执行的任务，只做文档差异、链接和源码依据核对，不为文档提交启动这些产品检查；包含代码改动的提交仍遵守下列要求。

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

改动 `vnext/rust` 时还要过 rustfmt 与 clippy。它们会编译 crate，在五节点池内合格空闲节点上按占用规则运行，
`CARGO_TARGET_DIR` 放在 worktree 外：

```bash
cd vnext/rust && cargo fmt --all --check \
  && CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/<任务>-cargo-target \
     cargo clippy --workspace --locked --offline --all-targets -- -D warnings
```
