# Testing Conventions

状态：现行执行要求；决议依据见各节链接。

本文规定 vNext 各包（五个 Python 包与 `rust` 包）的测试分层、执行入口与性能约束；前端（`frontend/`）的运行位置、
工具链与证据见“前端测试（FD7）”一节。Fixture 材料语义由
[Testing Fixtures](testing-fixtures.md) 拥有，本文不重复。

## 新流程生效与自动门禁（P7-D25/D26）

后端按 P7-D27 在 S1a-B 原流程收尾后暂停，门禁工具独审及验证通过后从 C 采用新流程；前端仍从 FE4a 后下一步切换。A/B 的既有记录和 FE4a 安排保留，S1a 产品范围、验收范围与 exit 条件不变。设计/Contract/决议入库，过程日志、handoff、提示词和审核意见移至 `/home/dev/gdds-stage-exchange/<stage>/`；阶段退出只入库一页总结。下文旧 handoff 字段在新阶段由阶段日志或机器结果承接，不再要求重复入库文档。

每阶段一个设计者、一个持续协调者；每包新实施上下文（内聚两三个小包可合并），取消专职测试者。协调者按比例化政策 §4 定风险：A/B 逐包独审，C/D 实施者加门禁；阶段末全部包做一次全范围独审。独审使用新上下文及不同模型家族。独立代码审核、真实旅程、clean 已提交权威运行与架构门禁保留。

范围内节点调度/占用、可逆实现细节、风险定级及已确认环境/命令错误的修复按默认规则自决；产品/验收范围变化、来源冲突和不可逆操作交 Owner。构建快速修复规则保持，产品失败仍停止该次 runner 及依赖验收，修正后新运行不覆盖原失败。

拟建 `scripts/run-stage-gate.py`，输入 SHA 与可选包列表，04 固定 worktree 自动占用、准备闭包、运行权威 runner、写仓库外 JSON、释放占用；按同来源闭包查表替代手工 carried。详细算法、失败语义、最初来源、镜像等价、目录与模板见 [门禁与交接规格](refactoring/formal/plans/p7-gate-and-stage-workflow-design.md)。**目前仅有规格，启用前仍执行下文操作步骤**；步骤保留为现行运行依据及脚本实施规范，不能提前删除。S1a-A/B、FE4a 不切换入口；C–F 不因自动化改跑全量，G 仍集中验收。

五节点资源池保持现行规则；Owner 已确认规格 §6 的处理：自动门禁固定 04，其他工作继续池调度，不恢复旧节点职责。新自动门禁不迁移固定 worktree 来获取命中。前端继续独立 runner/e2e，不以 backend 包命中推断 FE 通过。

## 执行入口

Host 依赖准备与权威测试分为两阶段，不得混用机器级 index：

```bash
./vnext/scripts/prepare-dev-dependencies.sh
./vnext/scripts/run-tests.sh
```

所有测试、容器门禁与取证都在专用测试节点上执行（DC34、DC36），不回退开发主机。五节点均为 **32 vCPU / 64 GiB**，组成统一资源池（DC91）：`ct108-gw-dms-04`、`ct108-gw-dms-05`、`ct108-gw-dms`、`ct107-gw-dms-06`、`ct109-gw-dms-07` 均可承接前后端调试、权威 runner、容器、真实数据或正式性能测量。选择执行时空闲且本次工具链、离线缓存、输入合格的节点，池内换节点无需另请用途授权；配置相同不证明缓存齐全或旧证据可搬迁。

所有测试、编译、lint、构建、mock/真实 e2e、取证和有写入的清理均原子 `mkdir /home/dev/gdds-node-busy.d` 获取本节点占用，记录会话、用途和开始 UTC；失败不抢占，完成本次运行与资源收尾后仅释放本人标记。已有自行取得标记的入口不在外层重复取得。只读现场核对无需标记。不以旧空闲快照作为预约。

已知物理拓扑仍为 04/06/07 共享宿主、04/05/CT108 分属不同宿主；配置调整不证明物理隔离变化。不同节点不自动互斥，实际干扰时协调；同节点整机单飞，计时独占。正式统计组的预热和全部测量留在同一节点、配置及存储条件，硬件或节点变化另组记录，不能与旧条件混成同一性能对照。pytest workers/Cargo jobs 初始各 4，前端 `GATEWAY_FE_TEST_WORKERS=2`；产品 kernel N/M 独立设置，仍为 N1、32 GiB worker/8 GiB reserve/M24 GiB。64 GiB guest 不构成增大生产预算授权。其他资源档须有适用授权、固定参数与独审，保留系统及其他服务余量，结果按配置分别报告。宿主 thin pool 水位仍由管理员监测，guest 可用磁盘不能证明宿主余量。

清理仅限已授权且确认无执行者、无待用消费者、无需保留的本人或明确废弃派生文件；逐项记录路径、理由和空间变化。保护已引用成功/失败证据、当前carried worktree/环境/镜像、冻结基准、真实输入与未决故障状态，不按年龄批删、不全局prune、不接管他人资源。

开始前用 `ssh -o BatchMode=yes <别名> 'echo OK'` 检查连接。运行前提在每台
节点上分别满足，同一节点整机单飞，不同节点按上述物理宿主边界并行。carried 与来源 V 必须在同一节点、同一 worktree；
闭包 manifest 不记录节点身份（克隆节点首次重建镜像前 image ID 也相同），因此 runner、carried 与真实数据日志
开头记录 `hostname` 与起止时间，handoff 写明运行节点，评审逐项核对。SSH 会话以 root 登录时，
设置磁盘上的 `TMPDIR=/home/dev/gdds-test-tmp`，避免复用其他用户拥有的
`/tmp/pytest-of-root`；不需要 pytest tmpfs 时保持 `GATEWAY_TEST_BASETEMP` 未设置，以保留默认批次与 Compose 路径。

### 长时间执行与分工（Owner 2026-11-09）

按DC91/DC97，五节点是统一空闲资源池，没有前端、后端、门禁、真实数据或性能的固定功能分工；任一空闲节点均可选用，选后满足本次工具链、离线缓存与输入前提，池内换点无需另请用途许可。执行时核现场并原子取本人标记，无需常规跨会话预约、批准或逐次通报；仅真实占用／资源干扰、同路径写入或涉及他人资源时协调。同节点单飞、04/06/07共享宿主、同统计组同节点／配置、carried同来源节点／worktree规则保持。

长测由唯一测试执行者负责执行与监视。启动及必要预检完成后，优先等待既有进程的异常／退出事件；常规巡视按预计时长降低频率，可以间隔小时级时间，不要求分钟级轮询或定期逐项进度转述。出现失败、需要协调的异常或执行完成时，测试者主动汇报并唤醒协调者；协调者等待事件，不重复巡视同一执行。实施者和独审者在固定候选、修复或原件核收时介入，无需同步轮询。按需只读监视角色仍与唯一执行责任人合并或错峰，不启动第二份测试、不自行重试／终止、不代签通过。

减少外部巡视不改变产品已有健康检查、租约心跳、固定执行稿的有限超时、失败留证或最终收尾；不为此新增后台observer、持久监控状态或修改正在运行的采样稿。失败保原始exit／日志和现场，完成时交付节点、起止HEAD／UTC、日志SHA、资源与占用释放事实，依原规则独审核收。Owner主动询问状态时可按需只读检查。

### 验证范围与测量成本（Owner 2026-11-09，DC98）

各阶段先列新增/受影响业务断言及唯一测试owner，复用合格固定向量、回归、真实数据与门禁来源；不默认重复完整旅程、全量合成负载、1预热加3测量或逐段耗时剖析。真实代表样本优先；合成小向量仍可验证SQL字节、阈值、预算/取消等明确边界，大规模合成旅程不替代真实使用。确有性能/容量问题时，限定目的、输入、次数和成本再安排专项，不把取消项自动转入后续阶段。

缩减不取消基础正确性/安全门禁及未关闭finding。按实际影响与原闭包规则跑必要focused/权威包，修订收敛后集中完成必要门禁，避免每次微调重复全套。保当前源码/镜像、原exit与失败日志、真实表结果、CAS、恢复、有限资源和生命周期的最小充分证据；诊断日志是否齐全、两次正常build本机ID是否相同或细粒度性能是否收全，不自动成为新业务Contract。具体新范围以Owner确认清单为准，未确认项不自签PASS。见[DC98](refactoring/formal/plans/p6-s0-owner-decisions.md#dc98-业务正确性优先与s4验证范围收敛owner2026-11-09)。

### 测试节点网络与缓存（owner 2026-10-28）

CT201 是联网开发节点，不用于运行测试。专用测试 CT 禁止直接访问公网，但可经局域网访问 CT201 或指定的公共缓存 CT 提供的获准缓存。该访问只用于依赖、镜像和构建制品，不开通任意公网出口。测试代码通过获准的局域网 Git/文件传输方式同步到各自的 clean、已提交 worktree；测试、Compose 与真实数据旅程仍在指定测试 CT 上执行。

缓存按节点分别准备，不能假设一个节点的 cache、image 或 build layer 已存在于其他节点：

- **Python：**测试节点的权威 runner 与环境同步设置 `UV_OFFLINE=1`，使用已填充的 uv 缓存/环境。`prepare-dev-dependencies.sh` 的 `GATEWAY_DEV_OFFLINE=1` 只约束准备步骤，不代替 runner 的 `UV_OFFLINE=1`。保留 lockfile 中的 canonical registry identity，不得通过机器级 index 配置改写 lock source。
- **Rust：**测试节点的权威 runner 设置 `CARGO_NET_OFFLINE=true`；对应 rustup toolchain 与 crates 必须预先齐全。root SSH 环境的 `PATH` 以 `/home/dev/.cargo/bin` 开头，不设置 `RUSTUP_TOOLCHAIN`、`RUSTUP_HOME` 或 `CARGO_HOME`；在 `vnext/rust` 下用仓库 selector 检查 `rustc` 版本，并确认 `cargo`、`rustfmt` 与 `clippy-driver` 使用同一工具链。不可依赖测试节点联网安装工具链。
- **DC67 预填充与代理：**依赖、锁文件或基础镜像变化时，先在 CT201 取得制品，经获准的局域网预填充到实际使用的节点；handoff 记录来源节点/提交、制品摘要与预填充时间。任何池内节点的权威 runner、carried、正式测量与真实数据取证均不经转发代理；缓存缺失即停止，完成预填充后从头运行。仅 05 调试构建可临时使用受限转发代理：只放行所需主机、不传凭据、用完即停；handoff 记录放行主机范围、起止时间与用途，调试结果不作证据。
- **Docker/Compose：** 基础镜像须已在节点本地或可从批准的 LAN registry/cache 获取。Dockerfile 下载的 uv、Python、Dolt 与 Python 包须命中现有构建层、预置依赖镜像或 LAN 制品缓存。Repository Service 可使用已校验的依赖基础镜像；使用 `build-repository-service-image.sh` 的 `GATEWAY_P2R1_CACHE_URL` 时，须设置为该节点实际可达的获准缓存地址（owner 2026-11-08 确认保留两种方式）；默认 `172.17.0.1:18080` 是本机 Docker bridge gateway 的假设，不是通用 CT 地址。
- **backend/worker dependency-base：** `vnext/backend/pyproject.toml`、`vnext/backend/uv.lock`、`vnext/backend/.python-version`、`vnext/rust/Cargo.lock`、`vnext/rust/rust-toolchain.toml` 或 Rust 基础镜像变化时，在 CT201 的 clean worktree 执行 `vnext/scripts/build-backend-dependency-base.sh --save <归档>`，构建 `gateway-backend-deps:lock-<12>`。通过获准 LAN 传到实际使用的测试节点后执行 `docker load`。handoff 记录来源提交、完整输入摘要、tag、config digest、全部 RootFS DiffID、归档 SHA256、构建/传输起止时间与缓存来源类别/端点标识，不记录凭据；inspect ID 仅作参考。
  - backend/worker 特有的 build 设置为 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`、`GATEWAY_DOCKER_BUILD_NETWORK=none`。保留 Compose build，由节点在无构建网络时本机实际构建 backend/worker；不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- **跨节点镜像身份：**传输镜像用 config digest 与全部 RootFS DiffID 逐项比较，不比较 `docker inspect` ID；containerd store 的 inspect ID 是本机生成的 manifest digest。同节点闭包 manifest 与按包 carried 判定使用本机 image ID；这不改变下文容器门禁镜像等价规则。
- **Repository Service 与 client e2e：**继续使用各自的预置依赖模式。若 client e2e 镜像的 revision label 与当前 HEAD 不同，门禁会在本机重建，这是正常行为；不要手工执行 `docker rmi`。
- **本地运行依赖：** Dolt、Compose 本地网络、真实数据文件、Docker daemon 和测试端口仍须在各测试节点就绪；断公网不应影响节点 loopback、容器间网络或获准 LAN 缓存连接。

启动 runner 或容器门禁前，确认本次闭包涉及的缓存端点可达，且依赖、基础镜像和必需构建层可从本机或获准 LAN 缓存取得。若发生 cache miss 且缓存不可达，停止验收并补齐缓存/恢复端点，不得回退到 CT201 执行测试。handoff 记录 cache 来源类别/端点标识与使用方式；runner 和 carried 证据仍按原规则记录 hostname、起止 HEAD、exit code，凭据不得写入日志。proxy/cache URL 的 manifest 指纹只作闭包判定，不应反推出或打印凭据。

**DC68 现行规则（Owner 2026-11-10 补充）：确认属于非程序逻辑的构建/环境故障，适用下文快速修复流程，不受旧版一次或最多三轮限制。**其余自身命令、脚本、参数、执行范围或 DC66 第 5 项工具缺陷，继续适用 2026-11-08 的最多三轮“定位→固定修订→适用独审→受影响步骤复验”；不因被测对象已经运行而立即交 Owner。仅对这类其余工具故障，首次失败不计轮次、第三轮仍未解决后交 Owner，不以更换候选/目录/节点/角色重计。既有只读后处理/预检和代码传输准备不计次数澄清继续适用。

- 每次首失败仍先停止该次执行及后续验收，保留原始 numeric exit、日志和 SHA256，确认资源/状态可安全收尾后再修复。若只留工具stdout而没有独立原文件，明确来源限制，不补造实时原日志。后续成功不改写旧失败、缺失或未知。
- 修复授权不允许无修改自动重试。是否独审按实际修订内容及下文分流；clean 固定候选、节点占用/离线和输入身份规则继续有效。只重跑受影响范围，不重复合格且未受影响结果；正式 runner 自身不增加自动重试逻辑。
- 不确定故障原因、无法确认副作用/资源收尾、需改冻结语义/Contract/golden/输入或超出现有授权时，仍停止受影响部分交Owner。真实产品failure按阶段已有修复授权和同根停止规则处理，不伪装成工具错误，也不靠DC68放宽断言。
- 缓存缺失、镜像/HEAD/输入身份不符、结果不一致时不得继续该次验收。明确由错误工具/命令选择引起的，可按本条修正后重新核验；可按DC67既有授权准备正确缓存，但不绕过预置来源/离线规则或接受错误身份。真实来源/正确性冲突未解决时交Owner。
- runner 已开始测试后 exit 非 0 仍先停止后续 carried/验收并处理失败；确认归类后按适用流程恢复，不能直接继续原失败链。原始失败与修正、复跑结果写入普通故障条目，handoff 引用即可，不增建持久计数/evidence 机制。

### 构建故障快速修复（Owner 2026-11-10）

本规则为全局实施原则，立即适用于当前因镜像构建错误停止的 S1a，及 P7 后续、P7 之后的阶段和维护。它覆盖确认未改变程序逻辑、依赖选择、部署语义及测试预期的命令/路径、获准缓存预填充、本地环境或临时空间故障。不能仅因错误发生在 Docker build 中就认定是基础设施问题；程序编译/类型错误、运行期权限/挂载/资源语义和产品正确性问题仍走正常流程。

| 实际修复内容 | 执行流程与评审要求 |
| --- | --- |
| 命令/路径纠正、按 DC67 准备正确缓存、已授权的环境恢复或本人废弃临时文件清理 | 唯一执行者直接定位、修正、核前提、重跑失败步骤；不逐次交实现者/独审，不要求执行稿双重评审或 Owner 恢复许可 |
| 修改仓库构建脚本、Dockerfile、依赖/锁、entrypoint 等源码 | 实施者修复 → 原审对修订做一次针对性代码评审 → 执行者重建/必要验证；后续命令/环境修正不再次评审，有新代码差异才审其差异 |
| 程序逻辑、部署行为、测试断言或结果正确性问题 | 正常实现/独审/测试流程及 owning Contract；不使用环境故障名义放宽验收 |

确认属于非程序逻辑、未改变依赖选择/部署语义/预期的构建条件或工具修复（上表前两类），修正复跑**无固定次数上限**；源码修订仍按第二类做针对性评审。每次要有具体修正、诊断支持的新排查方案或已核实的环境变化，不无变化盲重试。失败持续时继续收集有用诊断并调整方案，不因达到两三次机械停工。真正需要新权限/他人资源、无法确认副作用/安全收尾、来源/身份冲突无法消解或需要改变已接受边界时，才停受影响部分并交 Owner 所需决定；可以继续无依赖工作。原因未明时先做只读诊断，不自行把未知错误当已确认的环境故障。

每个故障只维护一个普通条目：首次保存失败步骤、候选/节点、原始 exit/日志/SHA；后续简短追加根因、修正、复跑结果与日志索引，最终 handoff 只引用一次。不逐次重写报告、建立新签署或重复记录相同上下文。原始失败和未知不改写为成功，阶段最终证据核收仍完成。

本补充明确授权测试/构建执行者在上述第一类范围修正命令、恢复环境并复跑，取代 S1a 旧稿中对此类故障“一律不得改执行参数/自行重试”的限制；产品/预算/预期/验收范围仍不可自行修改。仓库源码修订后先提交，再同步 clean 固定候选；不在运行中的被测树写入。节点占用、获准 LAN/离线、预填缓存、镜像 config/RootFS 身份、清理范围及证据规则不变，不开放测试 CT 公网或随意 prune。

重跑从失败构建步骤开头开始，不重跑未受影响的前置步骤。若失败发生在权威 runner 内，原次仍为失败；恢复条件后按阶段范围和闭包规则重新运行所需权威入口，不能把拼接日志当整次 exit 0，不自动开展完整业务旅程。A–F 的完整容器验收仍可按阶段集中原则移交 G，不必先解决无依赖的完整构建才推进其他工作。

linked worktree 里先建 `legacy` 符号链接（`ln -s /home/dev/gateway-data-management-system/legacy <worktree>/legacy`；该目录不在提交里，backend 的
`test_table_rules_resolver.py` 依赖该链接），再执行上面的两步。

`prepare-dev-dependencies.sh` 只同步五包 venv，不跑 pytest。`run-tests.sh` 先跑 `rust` 包，再按正确顺序跑
完全部 Python 包：

```bash
./vnext/scripts/run-tests.sh
```

阶段允许通过 `GATEWAY_TEST_PACKAGES` 指定部分包，例如
`GATEWAY_TEST_PACKAGES=backend,repository_service ./vnext/scripts/run-tests.sh`。合法值按固定顺序是
`rust`、`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service`；
未知或重复名称以 exit 2 拒绝，实际执行顺序仍按权威 runner 固定顺序。未设置变量时运行全部六个包，
原有包顺序、backend 与 `repository_service` 的两遍拆分、`GATEWAY_TEST_BASETEMP` 下的 Compose 文件
处理和五锁检查不变。项目最终门禁与发布门禁不允许缩小范围，必须运行全部六包（含 `rust`）；其他阶段按范围与闭包规则选择。

### `rust` 包与 backend 的 Rust 扩展（DC48）

`rust` 包最先运行，失败最快暴露。它在 `vnext/rust` 下依次执行以下三步；三步都执行，每步记录
`elapsed_seconds` 与 `status`，任一失败则 `rust status=failed`，其余包照常运行：

```bash
cargo fmt --all --check
cargo clippy --workspace --locked --offline --all-targets -- -D warnings
cargo test --workspace --locked --offline
```

- **Workspace**：`cargo test` 覆盖全部crate。扩展的Python/Arrow行为
  由 backend pytest 测已安装扩展，不在 Rust 用例中嵌入解释器；clippy 与 fmt 覆盖全部 crate。
- **离线**：cargo 以 `--locked --offline` 运行，crate 缓存在 `CARGO_HOME`（固定环境下为 `/root/.cargo`）。
- **`CARGO_TARGET_DIR`**：固定为 worktree 外的 `<TMPDIR>/gateway-runner-cargo-target`（`TMPDIR` 未设置或为空时为
  `/tmp`）。它是构建缓存，不是测试输入，不进闭包。选中 `rust` 或 backend 时，runner 在使用前删除残留、退出时
  （包括失败与可捕获的中断）删除，因此每次门禁都从空目录完整构建；runner 不再向 worktree 的 `vnext/rust/target` 写入。
- **`PYO3_PYTHON`**：`cargo test` 中没有 crate 嵌入 Python，runner 不设置 `PYO3_PYTHON`。
  clippy 仍会运行 PyO3 的构建脚本，它按 `PYO3_PYTHON`、`VIRTUAL_ENV`、`CONDA_PREFIX`、PATH 上的 `python3` 的顺序选择
  解释器；闭包记录 `PYO3_PYTHON` 的值与所选解释器的 `-VV`。今后若有 crate 需要嵌入解释器，通过 `PYO3_PYTHON`
  显式指定，不依赖系统 `python3`。
- runner 的额外命令行参数只传给 pytest，不传给 cargo。

backend 以 maturin 路径依赖安装 Rust 扩展（`gateway-compute-python = { path = "../rust/gateway-compute-python" }`）。
只改Rust源码也必须重建路径依赖，不能使用旧扩展。

- **强制重装（DC48）**：runner 同步 backend 时始终使用
  `uv-consume.sh -C . sync --reinstall-package gateway-compute-python`，`CARGO_TARGET_DIR` 同上。
- **构建输入一致性检查**：runner 以 `GATEWAY_RUST_BUILD_INPUT=<HEAD:vnext/rust 的 Git tree id>` 构建扩展，扩展在编译时用
  `option_env!` 嵌入该值，暴露为 `gateway_compute._native.__build_input__`（未设置时为空串，镜像构建即如此）。
  同步后 `vnext/scripts/check-rust-extension-build-input.sh` 读取已安装扩展的值并与当前提交比较，不一致、为空或无法导入时
  backend 失败，runner 在 manifest 之前以 exit 1 停止。该变量只传给 backend 的同步命令，不导出到 manifest 与 pytest 的环境。
  cargo 跟踪 `option_env!` 读取的变量，值变化时重新编译所在 crate。此机制对任何以 maturin 路径依赖装入 backend 的扩展都成立，
  扩展的 `#[pymodule]` 中同样导出 `__build_input__`。
- 开发者在 Rust 改动后跑 backend focused 测试时，同样先用 `--reinstall-package gateway-compute-python` 同步。

### Hypothesis 隔离与按包闭包沿用

权威 runner 为每个选中的 Python 包无条件设置 `HYPOTHESIS_STORAGE_DIRECTORY` 为
`<TMPDIR>/gateway-runner-hypothesis/<包名>`；路径不含随机部分。`TMPDIR` 未设置或为空时固定使用 `/tmp`，
有效 TMPDIR 必须是 worktree 外已存在的绝对路径。runner 在 manifest 前打印各包的有效 storage directory 并删除选中包的残留目录，并在退出时（包括失败与
可捕获的中断）清理这些包专属目录；不会删除 worktree 的 `.hypothesis` 或 TMPDIR 下的其他内容。同一包的
所有 pytest 调用共用一个目录，包括 backend 与 `repository_service` 的并行、串行两遍。worktree 内的
`.hypothesis` 只用于开发者直接运行 focused 测试，不是权威 runner 的输入。

权威 runner 不跨运行保留 Hypothesis 失败样例，这是隔离目录带来的代价。失败时依据 Hypothesis 输出的反例分析；
runner exit 非 0 时先停止并处理失败，不继续做 carried 或后续验收。

runner 先经受控 wrapper 同步待运行包的 locked uv 环境，再为每个待运行包写出一份 JSON 闭包 manifest，可单独运行
`python3 -I vnext/scripts/test_input_closure.py manifest --package <包名>` 查看；dirty worktree 会被拒绝。
Python 包还摘要该包实际使用的 uv 环境目录内容；由锁定源码与对应 Python
解释器派生的 `__pycache__`、`.pyc`、`.pyo` 不计入 uv 环境摘要。
Git 组成部分使用当前提交对应路径的 tree/blob object id，`legacy/` 使用排序后的相对路径与文件内容摘要，
环境部分记录每包 Python `-VV`、Dolt、uv、rustc 版本；每包还对有效 Hypothesis storage directory
（`HYPOTHESIS_STORAGE_DIRECTORY` 或包目录下 `.hypothesis`）及包内 `.pytest_cache` 的路径、内容和权限做摘要，涵盖可能参与输入生成或被测试工具读取的缓存。backend 与 `repository_service` 还记录 Docker/
Compose 工具与 daemon 身份、有效 build 环境变量指纹、基础/服务/dependency-base 镜像 tag 和本机 image ID；backend 另记录所选 dependency-base 名称与 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES` 开关；
backend 的 prebuilt Compose 选项启用时，manifest 还摘要本机镜像清单。proxy/cache URL 等可能含凭据的值只记录 SHA-256，
不将原值写入 manifest。每包闭包包括自身与传递路径依赖、fixtures、全部五个 lockfile、
runner/wrapper 脚本、workspace 配置、deployment 输入和共享 rust-toolchain selector。backend 的 Rust
闭包包含 workspace crate、`Cargo.lock` 与 `rust-toolchain.toml`（生成的 `target/` 排除）；backend 和
`repository_service` 还包括 Compose 镜像使用的完整 `vnext/` build context、相关 Compose 与 Dockerfile。
repository_service 的 context 因而包含 `repository_client` 及 e2e/dependency-base Dockerfile。manifest 记录
本机 base image ID、repository-service 与 dependency-base ID、client e2e 与 client dependency-base ID，以及
会影响 build 的环境设置指纹。backend 所选 dependency-base 名称、本机 image ID 或预置开关任一变化，都要求 backend 重新运行。`compare --source <来源-manifest.json> --current <当前-manifest.json>`
逐项比较并输出“运行”或“可沿用”及变化的组成部分。

`rust` 包的闭包（schema version 9 起）：`package:rust` 为 `vnext/rust` 的 Git tree（未跟踪的 `target/` 不在其中），
`rust:cargo-lock` 单列 `Cargo.lock`；共享组件与 Python 包相同（fixtures、`vnext/scripts`、workspace 配置、
rust-toolchain selector、deployment、五个 lockfile）；`non-git:cargo-config` 按路径与内容摘要 cargo 会读取的
`.cargo/config.toml`/`.cargo/config`（`vnext/rust` 及其祖先目录、`CARGO_HOME`，不存在的文件不记录）；
`environment:rust-toolchain` 记录 `rustc -vV`、`cargo`、`rustfmt`、`clippy-driver` 版本（在 `vnext/rust` 下按
`rust-toolchain.toml` 选择）、`PYO3_PYTHON` 与 PyO3 构建脚本所选解释器的 `-VV`，以及 `CARGO_*`、`RUST*`、
`PYO3_*`、`HOME`、`PATH`、`VIRTUAL_ENV`、`CONDA_PREFIX`、`LANG`、`LC_ALL`、`TZ` 的 SHA-256 指纹（`CARGO_TARGET_DIR`
除外）。`rust` 包没有 uv 环境、Hypothesis storage、pytest cache，也不读 `legacy/`，这些组件不出现在它的 manifest
中；crate 内容由 `Cargo.lock` 的 checksum 固定。`compare` 对 `rust` 包的“可沿用 / 运行”判定与其他包相同。
对 backend 与 `repository_service` 的 `vnext/` Docker context，tracked 内容由 Git tree 覆盖；Git 只记录
tracked 文件的 executable bit，普通权限模式由闭包单独摘要 `vnext/` 下 tracked 路径、祖先目录和 context
根的本机 `0o7777` 模式。通过 `vnext/.dockerignore` 后仍进入 context 的非 Git 文件和目录按相对路径、类型、权限和内容摘要。
当前摘要器遇到 Dockerfile 专属 ignore 文件或未建模的 ignore 语法时失败关闭，加入此类规则前须扩展并测试闭包实现。

来源 V 必须满足：该包在该次权威 runner 中实际运行并通过；worktree clean；日志记录起止 HEAD；整次
runner exit 0。只运行部分包的权威 runner 也可作为来源。当前 V 上闭包有变化的包都必须实际运行并通过。
carried 计算必须为每个包设置与来源 V runner 相同的 `HYPOTHESIS_STORAGE_DIRECTORY`
（`<TMPDIR>/gateway-runner-hypothesis/<包名>`；TMPDIR 未设置或为空时为 `/tmp`）；该目录须不存在，若有残留会使
`hypothesis-storage` 组件变化并要求运行。worktree 内 `.hypothesis` 仅用于开发者 focused 测试。
handoff 逐包记录总摘要、运行或沿用、来源 V 与来源日志。链式沿用必须直接引用最初实际运行该包的 V，
不得把一次沿用结果当作新来源。manifest 比较只证明闭包相等；它不替代来源 runner 的 clean、包通过、
整体 exit 0 与 HEAD 日志要求。

按包沿用与镜像身份等价分别判定：包沿用决定当前 V 上哪些包需要运行，镜像身份等价决定 V..H 的容器结果能否
carried。backend manifest 覆盖其 Compose 旅程使用的所有镜像构建上下文、Dockerfile、Rust workspace、
Docker build 设置与实际选择的本机 image ID（启用 prebuilt 时包括本机镜像清单），因此 backend 沿用时，
同一次权威 runner 的 backend Compose 旅程一并沿用；V..H
仍须独立满足下文的镜像身份等价。项目最终门禁与发布门禁始终运行全部六包；其他阶段按范围与闭包规则选择。

### 内网构建环境变量（仅记录名与语义；不得写入 lockfile 或 production runtime）

Host 准备使用 `GATEWAY_DEV_DEPENDENCY_MODE=internal` 时须显式提供 `UV_INDEX_URL` 或 `UV_DEFAULT_INDEX`；默认 `pypi` 在同步时剥离机器级 index，保持 lock 的 canonical PyPI identity。`GATEWAY_DEV_OFFLINE=1` 使用 `uv sync --locked --offline`，不代替 runner 的 `UV_OFFLINE=1`。
`run-tests.sh`、`prepare-dev-dependencies.sh` 与 `build-repository-service-image.sh` 均接入 `uv-consume.sh`。普通 `run`/`sync` 默认 `--locked`，隔离 ambient index/config；`--no-sync` 先只读 `uv lock --check --offline` 再 `uv run --locked --no-sync`，不得以自动 sync 替换待验证 wheel。消费前后比较五锁 SHA，漂移即非零退出、不自动 restore；测试不得隐式改锁，依赖变更须显式授权并重新同步环境。

Docker build 的 `GATEWAY_DOCKER_BUILD_NETWORK` 由 `deploy/compose.yaml` 与 `build-repository-service-image.sh` 读取，默认分别为 bridge 与 `host`。`GATEWAY_BACKEND_UV_BOOTSTRAP_*` / `GATEWAY_REPOSITORY_UV_BOOTSTRAP_*` 仅为 build-time 参数，不进入 production runtime ENV。Compose 测试客户端镜像在 Linux nested LXC 中默认用 Docker `host` build 网络，可设 `GATEWAY_DOCKER_BUILD_NETWORK=default`；不改变 production Compose 服务网络边界。

| 变量 | 阶段 | 说明 |
| --- | --- | --- |
| `GATEWAY_DEV_DEPENDENCY_MODE` | host 准备 | `internal` 需显式 index；`pypi`（默认）剥离机器 index |
| `GATEWAY_DEV_OFFLINE` | host 准备 | `1` → `uv sync --locked --offline` |
| `UV_INDEX_URL` / `UV_DEFAULT_INDEX` | host 准备（internal） | 内网 PyPI mirror；不得进入 `run-tests.sh` |
| `UV_INSECURE_HOST` | host 准备 / Docker build | HTTP mirror trusted-host |
| `GATEWAY_DOCKER_BUILD_NETWORK` | Docker build | 仅 build 网络；不改变 Compose 服务 runtime |
| `GATEWAY_BACKEND_UV_BOOTSTRAP_*` | backend/worker build | build-time pip 装 uv；不进 runtime ENV |
| `GATEWAY_REPOSITORY_UV_BOOTSTRAP_*` | repository-service build | 同上 |
| `GATEWAY_P2R1_CACHE_URL` | repository-service build | retained artifact cache 根 URL |

权威 runner 与提交前静态检查须通过上述受控消费入口：

```bash
./vnext/scripts/run-tests.sh
./vnext/scripts/uv-consume.sh -C vnext/<package> run pytest ...
./vnext/scripts/uv-consume.sh -C vnext/<package> run ruff check .
```

五锁 canonical registry identity 的权威 owner 为
`backend/tests/test_canonical_lock_identity.py`。

### 测试批次与 focused 运行

权威 runner 将 backend 与 `repository_service` 分成并行主体和 serial 两遍：
`-m "(not serial) or parallel_safe" -n "$TEST_WORKERS"` 后接
`-m "serial and not parallel_safe" -n 0`。其余三个包单进程运行。`rust` 包最先运行，由 cargo 自行并行，不受 `GATEWAY_TEST_WORKERS` 影响。
两遍拆分避免 timing-sensitive 测试争用 CPU；`parallel_safe` 只包括下文经逐项隔离审查的例外，backend 当前没有此例外。其余三个 Python 包的 worker 启动开销超过并行收益，因此保持单进程。

非串行worker默认`auto`；初始建议`GATEWAY_TEST_WORKERS=4`，按本次资源调整。阶段性验证不要跑全量；日常迭代用 marker 缩小范围：

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -m unit
cd ../repository_service
../scripts/uv-consume.sh -C . run pytest -m unit          # 不依赖外部服务
../scripts/uv-consume.sh -C . run pytest -m integration   # 需要真实 dolt
../scripts/uv-consume.sh -C . run pytest -m 'serial and not parallel_safe' -n 0   # 未确认可隔离的时序敏感组
../scripts/uv-consume.sh -C . run pytest -m parallel_safe -n 4  # 已逐项审查、可进入并行批次的 serial 来源测试
```

`parallel_safe` 不是“运行较快”的别名，而是严格的隔离审查结论：测试不得依赖真实线程
或进程、sleep/wait/固定时序、网络、Dolt、Docker、socket 或共享持久化状态。测试仍可保留
`serial` 标记以记录其来源；权威入口会将 `parallel_safe` 纳入并行批次，并只对
`serial and not parallel_safe` 使用 `-n 0`。当前仅审查通过以下 4 项：

- `test_diagnostics.py::test_streaming_cleanup_error_survives_failing_log_event`
- `test_row_stream_admission.py::test_ninth_row_stream_rejected_before_response_start`
- `test_runtime_admission_ownership.py::test_shutdown_closes_admission_then_stops_cleaner_before_db_and_lock`
- `test_upload_concurrency_admission.py::test_closed_pool_denies_new_upload`

专用测试节点可通过 `GATEWAY_TEST_BASETEMP=/mnt/gateway-test-tmpfs/pytest` 将 pytest 临时工作区
放入有容量上限的 tmpfs（变量必须为绝对路径）；这不会替换 Docker named volume，也不能替代真实文件系统上的
持久化、崩溃恢复、快照和容量语义验收。权威脚本在启用该变量时，会让三个实际 Compose
e2e 文件回到真实磁盘临时目录，以避开 unprivileged LXC 下 Docker secret bind mount 的
remount 限制；其余测试仍使用 tmpfs。

不带 marker 直接运行 pytest 会执行全部测试并自动并行；结果正确，但 `serial` 组会与其他
测试争用 CPU，判定 flaky 时以脚本为准。

权威脚本的运行前提（已提交的 clean worktree、运行期间不写 worktree、整机单飞、日志记录
HEAD 与 exit code）见 [AGENTS.md](../../AGENTS.md)“跑测试”一节；不满足时结果不能作为门禁
证据。

### Compose 门禁串行与端口

backend Compose旅程共用host `127.0.0.1:8000`，同节点必须串行。现harness在启动入口对`/tmp/gateway-compose-gate.lock`加flock并检查端口，cleanup释放锁；项目名保留会话隔离。外层仍先取得节点占用，不把flock等待当作节点预约。`GATEWAY_COMPOSE_GATE_SESSION`或既有project-name覆盖用于本任务唯一命名，不复用他人栈。

### Docker / Compose触发式重建

镜像构建验证的是某个精确source tree的image/deployment/container runtime行为，不是所有
代码修改的默认单元测试入口。Owner 于 2026-11-10 明确，从当前 S1a 起及后续实施统一采用
**工作包针对性验证、阶段最终候选集中构建验收**。S1a A–F 属于小节，G 才是阶段集中验收点；
后续阶段的工作包交接、角色更换与复审也不自动成为完整构建/全量 runner/完整真实旅程的触发点。

小节执行受影响静态/类型、focused/unit/Contract、必要真实 filesystem/Dolt 与最小数据链验证。
容器边界改动可合并到阶段最终候选；若 mount、权限、entrypoint、cgroup、signal 等行为只能在容器内证明，
且其结果影响后续接线，在相关改动收敛后提前做最小必要容器验证，关联小节可合并，不重复完整业务矩阵。
仅因完整容器证据集中到最终候选，不阻塞无依赖的后续实施；延期项标为 `deferred`，记录具体验证与执行点，
不得把未测写成通过或借延期关闭已发现的正确性 finding。

依赖基础镜像只在其定义的依赖、锁、工具链等输入变化时重建/传输；产品源码变化使用已有基础镜像及缓存，
仍按现行规则在测试节点实际构建产品镜像。正常通过时以一次集中完整验收为目标；失败修复后按影响重建复验，
不把“一次”当作禁止复验的次数上限。构建/缓存故障停止受影响执行和依赖验收，按现行停止/DC68 规则处理，
允许继续无依赖的逻辑开发，不绕过离线、镜像身份或失败处理前提。

以下边界在相应容器验证点必须重建当前候选 HEAD 并运行受影响容器门禁：

- Dockerfile、依赖锁或production依赖闭包、基础镜像、OS package、build/save/load脚本发生变化；
- entrypoint、Compose、环境变量接线、healthcheck/readiness接线发生变化；
- UID/GID、ownership/mode、volume/mount、socket、pidfile、broker/helper协议或生命周期发生变化；
- startup/shutdown、signal、子进程监督或filesystem行为的正确性依赖容器用户、PID namespace、
  mount namespace或双UID隔离；
- 修改实际Docker/Compose e2e、container harness，或评审结论要声称当前HEAD已经通过容器门禁；
- 阶段退出、发布或最终production gate。发布与最终production gate必须在最终候选
  HEAD重新构建并核对provenance，不能用祖先提交的镜像替代；阶段退出可按下文
  “镜像身份等价与结果沿用”沿用已验证提交的结果。

通常可以延期到必要节点：

- 可由focused/unit/integration完整覆盖的纯Python内部算法、SQL、projection或状态机修改；
- 不改变production artifact的测试、注释和普通文档修改；
- 只读审核，以及没有修改image/deployment/container-only runtime boundary的修复轮。

“可以延期”不等于旧镜像仍代表当前HEAD。除非满足下文的镜像身份等价，旧Compose结果只能
作为祖先提交的回归证据；报告必须把当前HEAD的container gate标为`deferred`或`stale`，
不得写成“当前HEAD PASSED”。若后续任一改动触发上面的强制条件，应在相关改动收敛后重建，
不必为中间提交重复构建。

### 镜像身份等价与结果沿用

适用范围：阶段退出；发布与最终production gate不适用。目的是让门禁之后只改
handoff、评审报告或普通文档的提交不必重跑Compose，而不是放宽容器门禁本身。

已验证提交`V`与最终HEAD同时满足以下条件时，`V`的容器门禁结果视为最终HEAD的结果，
记为`carried`：

1. **门禁运行合格**：`V`是已提交的clean worktree；全量或容器门禁由权威入口执行；日志记录
   开始与结束时的`git rev-parse HEAD`和明确的exit code；运行期间未写worktree，也未提交或
   重建其他镜像。若client e2e镜像revision label与HEAD不符，允许门禁在本机正常重建该镜像并更新本机tag；实施者不得手工`docker rmi`。在dirty worktree或临时index tree上的运行不能作为`V`。
2. **diff不触及容器边界**：`git diff --name-only V HEAD`中没有上文“必须重建”前五项所列的
   内容，也没有Docker/Compose e2e测试、container harness或其support模块。
3. **镜像身份相等**，逐个镜像核对：
   - 带`gateway.p2r1.build-input-revision`与`gateway.p2r1.source-tree-sha256` label的镜像
     （repository-service）：在最终HEAD用`build_context_digest.py identity`重算，两项都等于`V`
     门禁所用镜像的label。`org.opencontainers.image.revision`随提交变化，不参与比较。
   - 没有source identity label的镜像（backend、worker）：以backend包的闭包manifest判定。在运行
     `V`门禁的同一worktree中检出最终HEAD，用`python3 -I vnext/scripts/test_input_closure.py manifest
     --package backend`计算，与`V`那次runner起始时记录的backend manifest用`compare`逐项比较，必须
     为“可沿用”。完整输入成分见 [Hypothesis 隔离与按包闭包沿用](#hypothesis-隔离与按包闭包沿用)。
     专用测试节点使用containerd image store，重建可能生成不同本机image ID；镜像等价按此处的同来源manifest判定。
     manifest 包含 worktree 本机权限、非 Git context 内容与测试缓存等本地状态，Git 不会规范化这些状态；
     换 worktree 可能得到不同摘要，因此要求同一worktree；不得用另一个
     worktree 的结果判定“等价”或“不等价”。同一 worktree 也意味着同一节点（owner 决议 DC36）。
     因此阶段的门禁 worktree 保留到该阶段 exit 合入之后再清理（owner 决议 DC51）。

任一条件不满足，就在最终HEAD重建镜像并重跑受影响的容器门禁。S1a-A/B、FE4a 的等价判定仍由实现方记录、独立评审复核；新流程由门禁脚本记录判定，独审按风险和阶段全范围核收，失败不得以 `carried` 关闭 finding。

按包沿用与 V..H 镜像等价的关系、backend Compose 随包沿用及合格来源条件，统一见
[Hypothesis 隔离与按包闭包沿用](#hypothesis-隔离与按包闭包沿用)；阶段退出绑定最终 HEAD 仍须满足本节全部条件。

避免重复执行：权威runner的backend批次已包含backend Compose旅程。同一提交上runner已运行
并通过的Compose旅程不再单独重跑，provenance从该次运行的
`vnext/backend/tests/support/.last_compose_gate_provenance.json`复制到worktree外的日志目录。
只有需要单独复现失败或runner未覆盖的nodeid时，才单独运行Compose旅程。

### 新阶段门禁引用模板

脚本启用后阶段日志、审核和一页总结只引用结果，不抄逐包摘要或重写 carried 文档：

```text
Candidate: <full SHA>
Gate result: <node:/absolute/path/result.json>; run_id=<id>; sha256=<digest>
Coverage: <请求包/前端入口/真实旅程，未覆盖项明确写出>
Deferred: <尚未到验证点的容器项及明确阶段；无则 none>
```

JSON 必须含起止 HEAD/UTC、hostname、exit、日志/SHA、各包摘要/实跑或沿用/最初来源，以及镜像重建理由和 revision/source-tree。包查表不能替代容器等价条件；不符即重建实跑。S5/发布/最终 production gate 强制 fresh 六包和最终 HEAD 重建。真实数据范围仍按 DC33，引用原始旅程结果，不按包查表代替。

### S1a-A/B、FE4a 及脚本启用前的记录细节

实现汇报和独立评审都必须记录Docker/Compose决策，即使决定不构建。最少包含：

```text
Current HEAD: <sha>
Container rebuild required: yes | no
Reason: <命中的触发项，或未触碰container boundary的依据>
Last verified image revision: <sha | none>
Last verified source-tree/image id: <digest | none>
Container gate for current HEAD: passed | carried | deferred | stale | not-applicable
Carried from: <V sha、门禁日志、逐镜像身份比较结果 | none>
Deferred gates/nodeids: <精确命令、path或nodeid>
Required execution point: <必要容器接线验证点 | 阶段最终候选 | 发布前>
```

`Container rebuild required: yes` 表示在所记录的验证点需重建，不表示每个工作包现在都要完整构建。
按上述原则延期时可继续无依赖实施，评审不得用旧镜像结果关闭相关 finding；若为 `no`，评审应
检查理由是否确实不依赖容器边界。无论中间轮次如何决定，阶段最终候选都必须让容器门禁结果
绑定到最终HEAD：要么在最终HEAD执行权威Compose/production gate，要么在阶段退出
节点满足上文镜像身份等价并记为`carried`。

## 前端测试（FD7）

来源：[前端 kickoff §6](../frontend-vnext/frontend-kickoff.md#6-测试与证据fd7)（owner 2026-11-02 确认，FD7）。
本节只规定前端测试的运行位置、工具链与证据；前端测试分层见 kickoff §4.2。

### 位置与入口

前端工程位于仓库根目录 `frontend/`，不在 `vnext/` 下。backend 与 `repository_service` 的闭包和镜像身份以整个
`vnext/` 为 Docker context，前端不进入后端测试闭包，前端提交不影响后端按包沿用与 carried 判定。前端权威入口为
`frontend/scripts/run-tests.sh`，与 `vnext/scripts/run-tests.sh` 相互独立。

### 节点

与后端共用上述五节点池，不在开发主机运行；静态检查、mock/真实 backend e2e 和阶段退出证据可选任一合格空闲节点。阶段证据仍在 clean、已提交 worktree 用权威入口完整运行，记录实际节点。

### 工具链镜像

测试节点宿主机不安装 Node.js。前端测试在固定版本的工具链镜像中运行，镜像包含 Node.js、浏览器与所需系统库：

1. 在 CT201 取得镜像，经 `docker save`/`docker load` 通过获准的局域网传到实际使用的池内节点。
2. 跨节点身份比较 config digest 与全部 RootFS DiffID（同 DC67），不比较 `docker inspect` ID。身份不符即停止。
3. 镜像版本变化时按同一流程重新取得与传输。

### npm 依赖缓存（DC67）

在 CT201 依 `package-lock.json` 取得 npm 缓存，经获准的局域网预填充到实际使用的节点；运行时把缓存挂载进工具链
容器，在容器中执行 `npm ci --offline`。缓存缺失即停止，补齐预填充后从头运行。DC67 关于转发代理的限制同样适用：
任何节点上的证据运行均不经转发代理。

### 节点协调（DC70 补充）

- 所有前端运行均按本节执行入口取得原子占用；核本机进程、Compose 与端口，计时占用期间等待释放。
- `frontend/scripts/run-real-backend-e2e.sh` 自行取得/释放 DC70 标记，外层不要重复获取；其他入口由执行者获取，完成本人运行、清理容器和进程后释放。
- 跨节点按实际资源干扰协调，不建立常规整宿主互斥或报批；不得删除他人标记。

### 日志与 handoff

与后端相同：日志写到 worktree 外，开头记录 `hostname`、起止时间、起止 `git rev-parse HEAD` 与入口自身的 exit
code（经 `tee` 时用 `set -o pipefail` 或 `${PIPESTATUS[0]}`），并记录日志 SHA256。handoff 另记：

- 每次运行所在节点；
- 工具链镜像 tag、config digest 与全部 RootFS DiffID；
- npm 缓存来源：来源节点/提交、缓存摘要与预填充时间；不记录凭据。

### 截图验收

FE2 起，在 1280 与 1920 两种宽度下对 [UI 优化方向](../frontend-vnext/ui-optimization-direction.md) §7 草图清单中的每个页面与状态截图（模拟接口，固定示例数据）。截图与运行日志
存于 worktree 外的证据目录并记录 SHA256。审核会话逐张对照 `docs/frontend-vnext/sketches` 核对布局、层级、
语义色、按钮层级、禁用原因与焦点样式，不做像素级比对（示例数据不同）。与草图不符处要么修正，要么作为偏差列入
handoff 交 owner 确认。

### 真实 backend e2e

依据 [FE3a handoff §8](../frontend-vnext/fe3a-handoff.md#8-给-agents-与-testing-conventions-的建议条文41)，运行框架与场景见 [FE3 kickoff §4](../frontend-vnext/fe3-kickoff.md#4-真实-backend-e2e-的运行框架)，M1 范围和判断见 [§8.4](../frontend-vnext/fe3-kickoff.md#84-m1打包峰值内存)。

独立入口 `frontend/scripts/run-real-backend-e2e.sh` 不并入 `run-tests.sh`，使用独立 Playwright 配置与目录；`--session` 必填并写入占用标记和日志。脚本自行获取、核对和释放占用；调用前不要手工获取，即使同会话已有标记也以 exit 3 退出。
输入来源遵循 [FE3 kickoff §4.6（Q10）](../frontend-vnext/fe3-kickoff.md#46-测试身份与初始数据)。

**占用与清理顺序：**

1. 脚本以 `mkdir /home/dev/gdds-node-busy.d` 原子取得占用，写入会话名、用途、UTC 开始时间、hostname、worktree 与 HEAD；目录存在即退出，不抢占。再用 `flock -n` 取得 `/tmp/gateway-compose-gate.lock`，失败退出。
2. 核对没有发布 8000 的容器、`/proc` 中的 Dolt 进程，以及本脚本命名前缀的 Compose 项目、卷、网络和工具链容器残留；不满足即退出，不清理他人资源。
3. 退出（含失败与可捕获中断）先停止并删除本次工具链容器、保存 Compose logs，再按 kickoff §4.8 `down -v --remove-orphans --rmi local`，按项目 label 清理本次残留卷/网络，删除本次 RS tag 和 secret 目录。不删除共享镜像、后端遗留镜像或他人资源。
4. 核对本次容器、卷、网络与进程已无残留，8000 空闲且无 Dolt；成功后先释放 flock，再删本会话 marker 文件，最后 `rmdir` busy 目录。核对失败保留占用，标为 `cleanup-failed`，非零退出交 owner；顺序与核对由脚本执行。

**Compose secret：**session/token 文件只写在 worktree 外运行目录，权限 `0644`（或保证服务用户可读）；`0600 root` 会使服务无法读取。

**M1 方法与报告：**每次测量新建 browser/context，经浏览器级 CDP 枚举 PID（不可用时按 kickoff §8.4 的 `/proc` 方法识别），记录各进程；确认上传前向 `/proc/<pid>/clear_refs` 写 `5`，以重置后的 `VmHWM` 为基线，同时记录 `VmRSS`，请求发出后读取 `VmHWM`，峰值增量为后测 `VmHWM` 减重置后 `VmHWM`。判定只看 renderer，浏览器主进程增量单列报告；`performance.memory` 仅作参考。包大小取 multipart manifest 的 `size_bytes`，不用整个 multipart body；打包耗时取页面 `data-phase` 对应 packaging 阶段，不用 click→request。逐次报告 renderer/主进程增量、manifest size、打包耗时，多次测量报告中位数与最大值；场景、次数、FE3c 单次与三次测量的差异说明、附加采样和阈值均按 kickoff §8.4，不在此另设标准。

**日志字段：**日志与证据放 worktree 外，结束写日志 SHA256 旁注；沿用 FD7 的缓存来源与预填充记录，并记：

- 开头/结尾 hostname、UTC 时间、HEAD、`HEAD:frontend`/`HEAD:vnext` 树、clean 状态，结尾入口 exit code；
- 占用 marker 内容及获取/释放时间、flock 路径及获取/释放时间、前后残留核对结果；
- 工具链身份沿用 FD7；依赖、RS、backend/worker 的每次运行身份按 [FE3 kickoff §4.3](../frontend-vnext/fe3-kickoff.md#43-镜像)：依赖镜像 tag、dependency-input label、本机 image ID 与全部 `RootFS.Layers`；RS tag、本机 ID 与 build-input/source-tree/revision labels；backend/worker 本机 ID；Docker/Compose 版本。跨节点传输时才比较 config digest 与全部 DiffID 并记入 handoff，不要求每次运行 save 依赖镜像；
- npm 缓存归档 SHA256 与来源提交；
- Compose 项目名、网络 ID、工具链容器名；运行时 OpenAPI SHA256 与比对结果；
- 逐 scope 仓库 ID、`INITIAL` 提交 ID、身份名和权限，不含 token；
- 用例名称、起止时间与结果；每次 bundle 的 `Content-Length`、实收字节、`ETag`；
- 清理核对结果；t1 另记输入文件数、字节数、逐文件 SHA256 聚合值、M1 指标与各步骤耗时（只报告）。

Playwright trace、Compose 日志和 t1 参考截图只留节点，不入仓库或 handoff 正文；handoff 只记路径与 SHA256（trace 可能含临时 token 和输入数据，截图可能含真实值）。

## Marker 分层

`unit`、`integration` 与 `serial` 在全部包的 `[tool.pytest.ini_options]` 中声明，
并由 `--strict-markers` 强制：拼错的 marker 会让收集直接失败。`repository_service` 与
backend 还声明 `parallel_safe`，记录经逐项隔离审查、可进入并行主体的 serial 来源例外。

| Marker | 含义 |
| --- | --- |
| `unit` | 无重量级外部依赖，可全并发运行 |
| `integration` | 需要真实 dolt、子进程或落盘状态 |
| `serial` | 时序敏感，不得与其他测试争用 CPU |
| `parallel_safe` | serial 来源中已逐项确认隔离、允许进入并行主体的例外 |

`repository_service` 的 `tests/conftest.py` 统一处理分类与门禁：

- 请求 `import_layout` / `import_provider` fixture 的测试**自动**判定为 `integration`，
  无论是否写了装饰器。这两个 fixture 会真实执行 `dolt init`。
- 未被判定为 `integration` 的测试自动补 `unit`。
- 标了 `integration` 而 dolt 不可用时统一 skip；**不要**在测试里手写
  `@pytest.mark.skipif(not dolt_available(), ...)`，门禁只有一处。
- 标了 `serial` 的测试自动获得 `xdist_group("serial")`。

backend 的 `tests/conftest.py` 保留默认 `unit` 分类：未标 `integration` 的测试（包括保留
`serial` 的 unit 测试）自动获得 `unit`；serial 测试自动获得
`xdist_group("serial")`，除非它们显式标了 `parallel_safe`。所有通过
`requires_dolt` 或其他方式依赖真实 Dolt 的 backend 测试显式标 `integration`。

### 新增测试时

- 测试通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式
  间接依赖真实 dolt 的，**必须**显式加 `@pytest.mark.integration`。fixture 自动判定
  只覆盖 `import_layout` / `import_provider` 两个入口，覆盖不到函数体内的直接构造。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、
  子进程 sleep 与 stream timeout 的相对关系）的测试，必须加 `@pytest.mark.serial`。

### 分类正确性怎么验

仅在专用测试节点按占用规则把 dolt 移开再跑 `-m unit`，任何错分类都会直接失败：

```bash
mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit; mv /usr/local/bin/dolt.parked /usr/local/bin/dolt
```

这是唯一可靠的判据，静态扫描做不到。

## 性能约束

### 不得让纯逻辑测试付真实建仓代价

验证纯解析、纯校验、纯类型映射的测试，不得引入会执行 `dolt init` 的 fixture。
典型反例是「用 `import_provider` 建真实仓库，再把 `run_cli` 整个 mock 掉」——真实
仓库状态在断言路径上根本没被用到，却让每个测试多付数百毫秒。

`read_catalog` 一类方法只经 `self._cli.query_json` / `self._cli.catalog` 与外部交互，
行宽与 schema 校验都在纯函数里，直接对纯函数断言即可。

### 同构用例必须收敛为共享参数表

payload 与期望错误消息之外完全相同的用例，不得复制粘贴成多个测试函数，要收敛为
`tuple[tuple[bytes, str], ...]` 形式的模块级共享表。现有范例见
`tests/test_import_provider.py` 的 `MALFORMED_JSON_SHAPES`、`MARKER_FAULT_JSON_SHAPES`、
`CATALOG_ROW_SHAPE_FAULTS`。

复制粘贴的直接后果已经出现过：`test_catalog_count_rejects_extra_cell` 的 payload 与
同文件另一个已参数化用例逐字节相同，是纯冗余。

### 子进程要按批构造，不要按次 spawn

构造测试前置状态时，避免在循环里反复 spawn 外部进程。进程启动开销会主导测试耗时，
在并行执行下还会成为整个套件的关键路径。

### 私有 HOME 必须离线

`DoltRunner` 给子进程设置私有 `HOME`，并在其中预置 `.dolt/config_global.json` 关闭
dolt 的版本检查与 metrics 上报。该写入发生在 `DoltRunner` 构造期，属于 provider
process boundary 的生产语义，不仅服务于测试提速。全新 HOME 下 `dolt version` 会联网
查询最新发布版本，单次 3~5 秒。任何新增的、会创建全新 dolt HOME 的代码路径都必须
沿用这一预置，否则既拖慢测试，也违反 offline provider 边界。

## 全局风险分级与测试预算

权威规则见
[Proportional Assurance and Risk-Based Verification Policy](refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)。
该规则适用于Repository Service之外的Phase 3 capability、Phase 4 Operation Runtime、Phase 5
业务纵切以及后续优化、cutover和production hardening。

新增或修改功能时，先标出测试对象：

| 对象 | 测试重点 |
| --- | --- |
| 权威/不可逆事实与外部安全边界 | Contract、negative、transaction/CAS/idempotency、关键crash/restart和scope隔离 |
| 可恢复durable workflow | claim/terminal、retry/takeover、一个代表性矛盾与人工修复分支 |
| derived/temporary/rebuildable对象 | 正常/边界输入、失败不污染权威事实、bounded重试/诊断 |
| 私有helper/adapter/纯转换 | 最小输入输出、类型和owner contract；不复制production状态机 |

测试设计约束：

- 证明业务语义屏障，不默认在每两个syscall、transaction statement或线程事件间注入；
- 每个不变量只有一个权威owner；其他层只保留必要integration smoke；
- 参数矩阵的每个维度必须会改变行为或错误边界，否则合并；
- 测试按Contract行为命名，不用`rNN_*`、finding编号或实现技巧命名；
- production机制删除时同步删除mock、fixture、probe和historical proof；
- 单文件/单功能测试明显主导所在包，或新增用例主要证明私有interleaving时，暂停追加并复核
  风险等级、owner和重复性。没有机械LOC比例，通过拆文件不能规避复核。

新增独立UID/helper/service、自定义IPC/capability、持久evidence状态机、sidecar/quarantine、
tombstone或同机恶意actor调度证明，不是普通测试扩展；必须先有owning Contract/ADR接受的威胁、
损失和验收场景。安全探针可以交给实现者执行，但探针不能自行扩大当前威胁模型。

## Artifact cleanup 比例化验证

权威边界见
[ADR 0012](refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：
V1把同euid本地进程视为可信部署组件，不对抗恶意pathname换名。测试必须证明功能自身在
协作并发、崩溃和普通I/O错误下健壮，不得把directory-broker、inode-CAS unlink、双UID、
SCM_RIGHTS、pidfd或sidecar设为验收硬门。

保留的核心验证按业务后果组织：

- eligibility纯逻辑：SUCCEEDED、ordinary FAILED TTL、orphan TTL与protected引用；
- 正常成功删除、eligible `ENOENT`幂等、I/O失败重试且不改变commit/result；
- PENDING/QUEUED/RUNNING/manual-recovery保留，admission pin与cleaner协作竞态；
- server-owned root、caller path拒绝、symlink/regular-file/scope与跨repository边界；
- 业务成功持久化前、成功后cleanup前、cleanup失败后重试三个crash/restart语义屏障；
- bounded candidate pagination、shutdown无遗留线程，既有受保护与失败重试路径。

不可逆或大故障域不变量不能因本次简化而降级：Dolt commit/main CAS、control DB transaction、
跨repository/root误操作和protected artifact误删仍需强验证。但测试语义屏障，不穷举每两个
系统调用之间的调度窗口。同一Contract不变量只保留一处权威断言，同构shape用共享参数表；
保留的测试不得继续使用round编号命名。
