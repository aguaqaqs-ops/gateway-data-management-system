# vNext uv.lock：受控消费入口与 Canonical Identity 执行计划

状态：代码候选已实现；待独立 reviewer 验收与最终 host/container 门禁签署。

日期：2026-09-15

Owner：infra/dev-environment（工程）；独立 reviewer（验收）。

## 1. 基线与决策

Checkout 基线：`c0d607bc49b245dacc49f8c210cd069e12d39b43`。保护对象为
`vnext/{shared_kernel,repository_contracts,repository_client,backend,repository_service}/uv.lock`。
本文是在用户已有 untracked pending 文件上修订，保留路径；不表示已提交。

用户已确认：统一受控 uv 消费入口、隔离 ambient 配置、将合法锁更新分离，并以入口 SHA
不变检查及 CI 作为兜底。原方案默认 git-hook 接管、chmod 只读及“uv 无原生冻结”结论撤回。
仅文档编写获授权；不得凭本文自动实施、升级依赖、配置机器或修改 Git hooks。

与 [D-1 计划](refactoring/formal/plans/p5-5b-s2-d1-projection-freshness-execution-plan.md)
是独立工程轨，不需要等待 S2 final pass 才修复入口；此前“必须 S2 闭环后再实现”的 pending
排期由本次用户方向确认更新。两轨分别复审，最终候选容器重建前必须完成本轨。

## 2. 根因：已知事实与待确认触发点

- 历史事故签名是 canonical PyPI registry 被重写为 LAN mirror；
  [internal-build handoff](internal-build-environment-handoff.md) 已记录机器级 index 和裸 sync 风险。
- `run-tests.sh`/`prepare-dev-dependencies.sh` 已有部分 env 隔离及 `--locked`，但共享 helper
  未覆盖全部 index/config 输入；AGENTS 的 ruff/mypy 与 native wheel build 还有裸 `uv run`。
- `native_kernel_component.sh` 的 `uv run maturin build --locked` 中，后面的 `--locked`
  属于 maturin build，未保护外层 uv。
- Dockerfile 已使用 `uv sync --frozen`，普通 Docker COPY 不回写宿主机。每次“重建后锁变化”的
  实际命令仍需按宿主机前置步骤、bind mount、copy-back 路径定位；不伪称已证明是 Docker RUN。
- 本机 uv 0.12.5 的 help 已验证 `--locked`/`UV_LOCKED`，image uv pin 为 0.11.28。
  TOML 不接受 locked/frozen 字段不等于 uv 没有原生保护。

官方依据：[locking/sync](https://docs.astral.sh/uv/concepts/projects/sync/)、
[UV_LOCKED](https://docs.astral.sh/uv/reference/environment/#uv_locked)、
[配置优先级](https://docs.astral.sh/uv/concepts/configuration-files/)、
[Docker 分层与 frozen](https://docs.astral.sh/uv/guides/integration/docker/)、
[run --no-sync](https://docs.astral.sh/uv/reference/cli/#uv-run--no-sync)。

这是协作构建配置漂移，不是同 euid 恶意篡改威胁；采用标准 flag、薄 wrapper、普通 CI，不新增
持久 evidence、权限管理状态机或自定义镜像源映射协议。

## 3. 消费与更新规则

### 3.1 消费入口

复用 `scripts/lib/gateway-index-env.sh`；新增薄 `scripts/uv-consume.sh` CLI wrapper，
只允许 `run`/`sync`/只读 lock check，不提供任意 lock/add/update passthrough。
普通 run/sync 默认显式 `--locked`；拒绝 caller 注入 index/config 覆盖或冻结保护的反向 override。
`UV_LOCKED=1` 可作 scoped 默认安全网，不替代入口参数、不修改用户全局 shell 配置。

需要区分两项保证：五锁内容不变，以及锁与当前 manifest 一致。`--no-sync` 隐含 frozen，
即便同时写 `--locked`，也不能把该调用当作 metadata 一致性检查。保留 native 已安装 wheel
验证中的 `--no-sync`：直接删除会触发自动 sync，可能将待验证 wheel 替换为项目 path dependency。
该例外必须使用同一 project/config 的独立只读 `uv lock --check --offline`，通过后才执行
`uv run --locked --offline --no-sync ...`；check 不 sync、不安装/替换 wheel，也不更新锁。
Check 不继承会跳过检查的 frozen/no-sync 模式；禁止以 `--check-exists` 代替 freshness check。
例外由共享消费 wrapper 处理，不能靠在 wheel 安装之前曾经 sync 过就免除后续 check。
Ambient `UV_NO_SYNC`/`UV_FROZEN` 等模式覆盖须清理或明确拒绝，不得偷偷进入未经 check 的例外。

- 配置隔离：至少核对 `UV_INDEX`、`UV_DEFAULT_INDEX`、`UV_INDEX_URL`、
  `UV_EXTRA_INDEX_URL`、`UV_FIND_LINKS`、`UV_CONFIG_FILE`、index strategy、
  insecure-host、PIP index/find-links 和 env-file 注入。按当前 uv 支持项维护最小输入表。
- 用户/系统 `uv.toml` 也必须隔离。可用仓库指定配置或验证过的 `--no-config` 策略；
  不能只 unset 两个 env，也不能盲目禁用项目必须的 sources/build 设置。
  用现有五包 path dependency/native build 证明方案兼容；若需仓库 uv.toml，必须在 §4
  记录批准路径。隔离策略需唯一，不散落于各脚本。
- 允许运行时网络代理/可信 CA 和既有 cache 设置；不 dump 全量 env、带 credentials 的 URL 或
  shell xtrace。配置检查仅报告变量名、脱敏命令阶段和锁差异。
- Internal prepare 保留显式选择，但仍受 immutable lock 约束。指定镜像造成锁不匹配即失败，
  不改锁“适配”；缓存/预装依赖优先。Frozen 不承诺重定向锁内的下载 URL。

### 3.2 锁更新工作流

消费 wrapper 不更新锁。合法更新使用独立、显式授权的步骤：确定包/依赖版本或工具格式变更、
固定并记录 lock-generation uv 版本、隔离 ambient 配置、以 canonical PyPI 生成/同步、
审查 manifests/五锁差异、验收来源与依赖闭包、记录更新原因和 candidate。

不预设当前五锁由哪版 uv 生成。先验证现有锁兼容性并记录选定 pin；本 slice 不为统一工具
版本重写锁、升级 image uv 或自动下载新工具。不兼容时先报告，另行授权 dependency/tool slice。
Exact dependency pin 仍遵守 AGENTS。合法 lock-only 格式/重锁变更可以有明确原因，不强制
“锁变更必须伴随 pyproject 改动”的机械门禁。

Repository Service 锁合法变化时，必须同步 Dockerfile `UV_LOCK_SHA256` 并重建相应镜像。
本消费入口修复 slice 本身不允许 manifests/锁变化，也不改变 canonical registry 决策。

### 3.3 错误、SHA 与 CI

受控消费/build 入口在执行前记录五锁 SHA，成功与失败退出都比较；缺锁或漂移必须非零退出。
保留原命令失败状态；若原命令成功但锁漂移，改为失败。保留差异，不自动 checkout/restore，
不覆盖用户已有工作区变化；临时 snapshot 可清理，但不能清理被污染锁。

CI/权威 runner 执行唯一 canonical identity 检查：用 TOML parser 检查 registry 为
`https://pypi.org/simple`，禁止意外 LAN/HTTP registry；区分正常 path/workspace sources，
并拒绝 registry package artifact URL 偷渡未批准 mirror。常规 PyPI artifact host 列入明确
白名单，不把所有 source 误判成 HTTPS registry。不固定五锁 SHA，以允许已授权合法更新。

Git hook 仅可选辅助，本 slice 不实现/激活；不改 `core.hooksPath`、`.git/hooks` 或锁权限。

## 4. 修改范围与实施顺序（获授权后）

允许：

- `AGENTS.md`：消费命令/更新流程指引，不改其他约束。
- `vnext/scripts/lib/gateway-index-env.sh`、新 `vnext/scripts/uv-consume.sh`。
- `vnext/scripts/{run-tests,prepare-dev-dependencies,native_kernel_component,build-repository-service-image}.sh`。
- `vnext/repository_service/tests/test_prepare_dev_dependencies_script.py`、
  `test_build_repository_service_image_script.py`；必要时新 `test_uv_consume_script.py`。
- 新 `vnext/backend/tests/test_canonical_lock_identity.py`（唯一 five-lock identity test owner）。
- `docs/backend-vnext/testing-conventions.md`、本文、内部 build handoff 的相关入口记录。

Dockerfiles/Compose/cache launcher 当前只读审计；若确有未受控入口要改，先列出 exact path、
原因与容器验收范围，批准后再改，不自动扩张 allowed paths。禁止业务代码、依赖 manifests/
五锁、Rust、Repository wire、production runtime ENV 与机器/Git 全局配置变更。

步骤：

1. 清点 repo 内 uv run/sync/lock/add 及 build 前后 host/mount/copy-back；handoff 分类
   controlled consumption、Docker frozen、explicit update、需另行处理。先找触发面再关口。
2. 扩展共享隔离/immutable helpers，实现薄 wrapper；改 authoritative runner、prepare、
   native build 消费路径。Native 命令同时保护 uv 与 maturin 各自的 lock，参数位置正确；
   installed-wheel 检查保留 no-sync，并由独立 lock check 保证 freshness，不替换待验证 wheel。
3. Build wrapper 接入五锁 snapshot/退出检查；Docker frozen 保留，在完整 manifest/source 的
   preflight 做 locked check，不能把 frozen 当作 metadata 最新性检查。
4. 接入唯一 identity test 的权威 gate，更新 AGENTS。无既有 CI 时不引入 CI 平台，仅让现有
   runner 执行该 unit test；沿用已有 job 时记录接入点。
5. 污染演练、五包静态、最终候选重建与 handoff；独立复审绑定 exact code candidate 全 SHA。

## 5. 权威验证与退出

- Identity：`backend/tests/test_canonical_lock_identity.py` owner；参数化正常 registry、
  LAN registry/artifact URL、允许的本地 source、缺锁；使用临时副本，不污染仓库五锁。
- 消费策略/失败退出：复用 `repository_service/tests/test_prepare_dev_dependencies_script.py`
  及新 wrapper test，临时 project/config 与 recording fake uv 验证环境/参数；真实 uv 的最小
  offline probe 验证锁过期会失败且不改锁，不能只靠脚本文本 grep。
- 真实 uv 共享参数表加入 current/stale lock × 普通 run/no-sync。普通 run stale 必须失败；
  原生 run --locked --no-sync 可能在 stale 下成功而锁不变，只作行为对照，不作为受控入口 pass。
  受控 no-sync 必须先 check，stale 时失败且不执行 wheel 验证子命令；current 时执行验证，
  前后五锁不变，安装 wheel 的 direct_url/provenance 不被 check 或隐式 sync 替换。
- Build 不回写：扩展既有 build-script owner，用临时副本/fake builder 验证成功、命令失败、
  漂移后命令成功均正确退出，不自动恢复。其他层不重复该退出矩阵。
- 注入 ambient extra/default index、用户/系统配置、config/env-file override，受控入口屏蔽或
  明确拒绝，且五锁逐字节不变。测试使用 test-owned config；不移动真实用户配置。
- 合法更新流程只在临时 project 演示，明确记录 pin/原因；消费 slice 仓库锁 diff 必须为零。

Focused：backend identity test；repository_service prepare/wrapper/build unit 文件，遵守该包
parallel/serial marker 和已有网络门禁。所有五包 ruff/mypy 通过。不用真实 Dolt fixture
证明 TOML/参数解析；同构场景参数化，不按 finding/round 命名。

本轨修改 build/native 构建入口，并要求证明完整重建锁不变，必须在本轮最终候选执行：

```bash
bash ./vnext/scripts/native_kernel_component.sh wheel-smoke
bash ./vnext/scripts/native_kernel_component.sh wheel-trap-regression
```

Host native 门禁不能由 backend Docker build 替代：Dockerfile 直接执行 .venv/bin/maturin，
不会覆盖该 host 脚本。执行环境为 test-owned 可恢复的开发 checkout/venv、该脚本使用的 host
Python/uv/maturin、仓库 rust-toolchain 指定工具链、C 编译/链接工具，以及完整 uv/Cargo offline
cache；预先通过权威 prepare 入口准备五包环境，不临时升级工具或更改项目锁来绕过缺缓存。
命令以 shell 启动以兼容当前脚本权限，在仓库根目录运行；不得对生产 venv 注入恢复失败。

- wheel-smoke 整体退出 0，实际完成 release wheel 构建、安装、no-sync 检查/业务 smoke、
  direct_url/校验和 provenance 检查及 production install restore，不能只跑
  wheel-smoke-installed 替代该生命周期。保留其既有 no-test-hooks 与恢复检查。
- wheel-trap-regression 顶层退出 0；既有子场景 body success + restore fail 必须退出 99，
  body fail + restore fail 必须保留 42，并满足临时目录清理/CARGO_TARGET_DIR 恢复要求。
  分别记录失败子场景前后五锁 SHA 与原退出码；顶层 0 不能掩盖内部错误优先级被改变。
- 对真实 wheel-smoke 再执行下述既有恢复失败注入，整体预期退出 99（前提 smoke body 已成功）；
  若 body 自身失败，保留 body 非零状态且该 99 门禁不得签 pass。

```bash
NATIVE_KERNEL_FORCE_RESTORE_FAIL=1 bash ./vnext/scripts/native_kernel_component.sh wheel-smoke
```

为上述三个顶层命令分别记录五锁 before/after SHA、整体退出码和生命周期日志；正常成功、
预期恢复失败退出都要求五锁逐字节不变，锁检查不得覆盖既有 restore trap/错误优先级。
恢复失败注入会留下测试 wheel 安装：用 test-owned checkout/venv 隔离执行，结束后取消注入，
通过受控 offline sync 恢复 production install 并验证 no-test-hooks/来源；恢复结果同样记录，
只恢复测试安装环境，不 restore 五锁、不覆盖用户 checkout 的已安装 wheel。
缺 native toolchain/cache 或无法安全隔离安装环境时，host native gate 保持 pending；
fake uv、最小 offline probe、trap 单独成功和镜像构建均不能替代真实 wheel-smoke 证明。

随后完成受影响镜像及权威 Python 验证：

```bash
./vnext/scripts/build-repository-service-image.sh
docker compose -f vnext/deploy/compose.yaml build backend worker
./vnext/scripts/run-tests.sh
```

按现有 cache/remote-builder 文档选择受支持环境；不能无视环境限制强行 uncached build。
相应 Compose 门禁含 backend/worker affected runtime smoke、Repository Service 既有容器门禁；
按 testing-conventions 的延期清单执行，记录精确 nodeids。缺 Docker/cache/remote authority
就保留 gate pending，不能用 fake-builder/unit 或旧镜像宣称 current HEAD 已验证。

退出：上述 unit/污染演练及真实 host native 生命周期/恢复失败门禁 pass、五锁全程未改、
完整构建/测试流程无需 lock restore、current HEAD image/provenance 与对应容器门禁 pass、
exact candidate/handoff 齐备、独立 reviewer pass。
升级 tool/index identity、私有 registry、cache传输或 production 接线需求先另开 scope。

Handoff 至少记录：基线与 code candidate 全 SHA、changed paths、消费入口清单、选定 config
策略/uv pin、五锁 before/after SHA、no-sync 独立 check 与 wheel provenance、host native 成功/
失败/恢复退出码及 SHA、失败退出演练、commands/results、容器 image/source-tree/
nodeids、deferred/reopen。受控入口正常消费后完全不需要“验证后恢复锁”。

当前文档轮：代码候选已接入 `uv-consume.sh`、扩展 `gateway-index-env.sh`、权威脚本接线、
`test_canonical_lock_identity.py` 与 wrapper 单元测试；rebuild required=yes（触及 build/native
入口）。

## 7. 代码候选 handoff（2026-09-15）

### Changed paths

- `vnext/scripts/lib/gateway-index-env.sh`（扩展 env 隔离、`gateway_invoke_uv`、危险参数拒绝）
- `vnext/scripts/uv-consume.sh`（新）
- `vnext/scripts/{run-tests,prepare-dev-dependencies,native_kernel_component,build-repository-service-image}.sh`
- `vnext/backend/tests/test_canonical_lock_identity.py`（新，identity gate owner）
- `vnext/repository_service/tests/{test_uv_consume_script,test_prepare_dev_dependencies_script,test_build_repository_service_image_script}.py`
- `AGENTS.md`、`docs/backend-vnext/testing-conventions.md`、`docs/backend-vnext/internal-build-environment-handoff.md`

### 消费入口清单

| 分类 | 路径 |
| --- | --- |
| controlled consumption | `uv-consume.sh`、`prepare-dev-dependencies.sh`、`run-tests.sh`、`native_kernel_component.sh` |
| Docker frozen | `backend/Dockerfile`、`repository_service/Dockerfile`（未改） |
| explicit update | 不在本 slice；须独立授权 `uv lock` |
| out-of-scope | 文档 handoff 中的裸 `uv run` 示例、cache README 运维命令 |

### Config 策略

- 默认：`gateway_invoke_uv` → unset index/mode env + `uv --no-config`
- internal prepare：`GATEWAY_UV_CONSUME_PRESERVE_INDEX=1`（保留 caller index，仍 `--no-config`）
- no-sync：`uv lock --check --offline` 先于 `uv run --locked --no-sync`

### Focused 验证

| 命令 | 结果 |
| --- | --- |
| `backend/tests/test_canonical_lock_identity.py`（参数化副本） | pass（3/5；工作区污染锁导致 2 项 live-lock 检查 fail，见下） |
| `repository_service` wrapper/prepare/build 单测（34 项，`-n 0`） | pass |
| 五包 `uv-consume.sh run ruff/mypy` | pass |

### Host native 门禁

五锁 before/after SHA 一致（见下表）。`prepare` 后执行。

| 命令 | 退出码 |
| --- | --- |
| `wheel-smoke` | 0 |
| `wheel-trap-regression` | 0 |
| `NATIVE_KERNEL_FORCE_RESTORE_FAIL=1 wheel-smoke` | 99（body 成功后 restore 注入） |

### 五锁 SHA（工作区快照；backend/rs 相对 git HEAD 已污染）

| 包 | sha256 |
| --- | --- |
| shared_kernel | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| repository_contracts | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| repository_client | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| backend | `fe02d6dcaf746d512f88caee499c7281f33982d7f62c80a795e3493527fa0913`（工作区 LAN mirror） |
| repository_service | `7ad042b3893d51c2475888961d663aa94635ce2d6051697fe766fa6820ae5dd0`（工作区 LAN mirror） |

### Container 门禁

| 命令 | 结果 | 备注 |
| --- | --- | --- |
| `build-repository-service-image.sh` | **blocked** | `worktree is dirty`（identity helper 门禁） |
| `docker compose build backend worker` | **pass** | `deploy-backend:latest` / `deploy-worker:latest` 已重建 |
| `./vnext/scripts/run-tests.sh` | **partial** | 受工作区污染锁 + dirty worktree 影响；identity/uv_lock_sha256/compose 相关 nodeid 失败 |

### Deferred / 独立 reviewer

- 工作区 `backend`/`repository_service` 锁污染须在**独立 lock-restore slice**恢复 canonical 后再签 identity gate pass
- `run-tests.sh` 全绿须在 clean worktree + canonical 五锁 环境复跑
- `build-repository-service-image.sh` 须在 clean worktree 复跑并记录 image revision
- 独立 reviewer pass 待新开 context

## 6. 启动提示词与评审

> 阅读本文、AGENTS、testing-conventions 和现有 index helper/build/cache 文档；确认明确
> implementation authorization 后，仅实施允许路径中的受控消费入口、配置隔离、退出 SHA
> 检查及唯一 identity gate。保留用户工作区改动，禁止改五锁/manifests、自动 restore、Git
> hook 接管和默认 chmod；找出裸 uv/native 参数层级缺口，用临时项目做污染/失败演练。
> 保留 native no-sync 并先执行只读 lock check，不以自动 sync 替换待验证 wheel。阶段性
> focused 优先，最终候选执行真实 host wheel-smoke、恢复失败回归/注入及当前 HEAD 容器门禁，
> handoff 全 SHA/五锁 SHA/精确 commands/provenance，缺外部条件则如实 pending，
> 不自行签独立 closure。

本计划文档与完成后的代码候选均建议新开 conversation/context 独立评审；
可以回当前对话讨论 Findings，但不能让同一实施/起草上下文的自查替代 independent pass。
