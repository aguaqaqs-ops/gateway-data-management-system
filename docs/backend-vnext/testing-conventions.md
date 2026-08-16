# Testing Conventions

状态：2026-08-07 建立；2026-08-09 增补P2后半段container gate合并规则；
2026-08-13 冻结Docker/Compose触发式重建、评审记录、全局风险验证与artifact cleanup规则

本文规定 vNext Python 包的测试分层、执行入口与性能约束。Fixture 材料语义由
[Testing Fixtures](testing-fixtures.md) 拥有，本文不重复。

## 执行入口

权威入口是 `vnext/scripts/run-tests.sh`，它按正确顺序跑完全部 Python 包：

```bash
./vnext/scripts/run-tests.sh
```

`repository_service` 分两遍执行：主体并行，`serial` 组单独串行，避免 CPU 争用导致
时序敏感测试 flaky。其余包体量小，worker 启动开销会超过并行收益，因此单进程执行。

日常迭代用 marker 缩小范围：

```bash
cd vnext/repository_service
uv run pytest -m unit          # 约 910 项，无外部依赖，约 12 秒
uv run pytest -m integration   # 需要真实 dolt
uv run pytest -m serial -n 0   # 时序敏感组，必须串行
```

裸跑 `uv run pytest` 会执行全部测试并自动并行；结果正确，但 `serial` 组会与其他测试
争用 CPU，判定 flaky 时以脚本为准。

### P2后半段的功能门禁与最终container门禁

P2专用执行规则见
[P2 Versioned Repository Execution Checklist §1.1](refactoring/formal/plans/p2-versioned-repository-execution-checklist.md)。
从P2-R4 post-audit后续修复到R5，在未触碰build/deployment boundary时，允许把镜像构建、
跨主机传输和实际Compose测试合并到R6最终候选一次执行。期间整仓功能门禁仍使用权威脚本，
只精确排除实际启动Docker的测试文件：

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

当前延期inventory为

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
```

`tests/test_compose_lifecycle_negative_probes.py` 是 expected-failure cleanup 的独立
probe（missing readiness / wrong token / wrong network / non-empty restore），不是第五个
S7 PASS nodeid，同样按精确 path ignore，不用宽泛 marker。
静态Dockerfile/Compose测试、build script/harness单测和真实Dolt integration仍属于功能门禁，
不得一并跳过。以后新增实际Docker测试时，round handoff必须登记精确path/nodeid并同步更新
调用参数；不新增宽泛`container` marker来隐式改变现有三类marker语义。

此命令不是新的全局权威入口，也不能用于Phase 2最终退出。R6必须对最终source tree运行无
`--ignore`的`./vnext/scripts/run-tests.sh`，完成production image build/provenance、镜像传输、
全部延期Compose nodeid和资源清理后，才可宣布P2完成。任何Dockerfile、production依赖闭包、
Compose/container wiring或container harness变更都会提前终止延期，并要求在所属round执行
相应容器门禁。

### Docker / Compose触发式重建

镜像构建验证的是某个精确source tree的image/deployment/container runtime行为，不是所有
代码修改的默认单元测试入口。阶段迭代不要求每轮、每个提交都重建；同一轮内即使有多个触发
改动，也允许先完成相关修改，再对该轮最终HEAD构建一次。是否重建按以下边界判定。

必须重建当前HEAD并运行受影响容器门禁：

- Dockerfile、依赖锁或production依赖闭包、基础镜像、OS package、build/save/load脚本发生变化；
- entrypoint、Compose、环境变量接线、healthcheck/readiness接线发生变化；
- UID/GID、ownership/mode、volume/mount、socket、pidfile、broker/helper协议或生命周期发生变化；
- startup/shutdown、signal、子进程监督或filesystem行为的正确性依赖容器用户、PID namespace、
  mount namespace或双UID隔离；
- 修改实际Docker/Compose e2e、container harness，或评审结论要声称当前HEAD已经通过容器门禁；
- 阶段退出、S3 ready、发布或最终production gate。最终候选HEAD必须重新构建并核对provenance，
  不能用祖先提交的镜像替代。

通常可以延期到必要节点：

- 可由focused/unit/integration完整覆盖的纯Python内部算法、SQL、projection或状态机修改；
- 不改变production artifact的测试、注释和普通文档修改；
- 只读审核，以及没有修改image/deployment/container-only runtime boundary的修复轮。

“可以延期”不等于旧镜像仍代表当前HEAD。只要image label中的revision/source-tree与当前HEAD
不一致，旧Compose结果就只能作为祖先提交的回归证据；报告必须把当前HEAD的container gate
标为`deferred`或`stale`，不得写成“当前HEAD PASSED”。若后续任一改动触发上面的强制条件，
应在相关改动收敛后重建，不必为中间提交重复构建。

### 每轮评审记录

实现汇报和独立评审都必须记录Docker/Compose决策，即使决定不构建。最少包含：

```text
Current HEAD: <sha>
Container rebuild required: yes | no
Reason: <命中的触发项，或未触碰container boundary的依据>
Last verified image revision: <sha | none>
Last verified source-tree/image id: <digest | none>
Container gate for current HEAD: passed | deferred | stale | not-applicable
Deferred gates/nodeids: <精确命令、path或nodeid>
Required execution point: <本轮结束 | 阶段最终候选 | S3 ready前 | 发布前>
```

若`Container rebuild required: yes`，评审不得用旧镜像结果关闭相关finding；若为`no`，评审应
检查理由是否确实不依赖容器边界。无论中间轮次如何决定，阶段最终候选都必须让image revision、
source-tree provenance与最终HEAD一致，并执行权威Compose/production gate。

## Marker 分层

三个 marker 在全部包的 `[tool.pytest.ini_options]` 中声明，并由 `--strict-markers`
强制：拼错的 marker 会让收集直接失败。

| Marker | 含义 |
| --- | --- |
| `unit` | 无重量级外部依赖，可全并发运行 |
| `integration` | 需要真实 dolt、子进程或落盘状态 |
| `serial` | 时序敏感，不得与其他测试争用 CPU |

`repository_service` 的 `tests/conftest.py` 统一处理分类与门禁：

- 请求 `import_layout` / `import_provider` fixture 的测试**自动**判定为 `integration`，
  无论是否写了装饰器。这两个 fixture 会真实执行 `dolt init`。
- 未被判定为 `integration` 的测试自动补 `unit`。
- 标了 `integration` 而 dolt 不可用时统一 skip；**不要**在测试里手写
  `@pytest.mark.skipif(not dolt_available(), ...)`，门禁只有一处。
- 标了 `serial` 的测试自动获得 `xdist_group("serial")`。

### 新增测试时

- 测试通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式
  间接依赖真实 dolt 的，**必须**显式加 `@pytest.mark.integration`。fixture 自动判定
  只覆盖 `import_layout` / `import_provider` 两个入口，覆盖不到函数体内的直接构造。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、
  子进程 sleep 与 stream timeout 的相对关系）的测试，必须加 `@pytest.mark.serial`。

### 分类正确性怎么验

把 dolt 移开再跑 `-m unit`，任何错分类都会直接失败：

```bash
mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit; mv /usr/local/bin/dolt.parked /usr/local/bin/dolt
```

这是唯一可靠的判据，静态扫描做不到。建立本规范时用它发现了 13 个漏标的测试。

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

## Artifact cleanup 比例化验证（S2）

权威边界见
[ADR 0012](refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)：
V1把同euid本地进程视为可信部署组件，不对抗恶意pathname换名。测试必须证明功能自身在
协作并发、崩溃和普通I/O错误下健壮，不得把directory-broker、inode-CAS unlink、双UID、
SCM_RIGHTS、pidfd或sidecar收敛重新设为S2/S3硬门。

保留的核心验证按业务后果组织：

- eligibility纯逻辑：SUCCEEDED、ordinary FAILED TTL、orphan TTL与protected引用；
- 正常成功删除、eligible `ENOENT`幂等、I/O失败重试且不改变commit/result；
- PENDING/QUEUED/RUNNING/manual-recovery保留，admission pin与cleaner协作竞态；
- server-owned root、caller path拒绝、symlink/regular-file/scope与跨repository边界；
- 业务成功持久化前、成功后cleanup前、cleanup失败后重试三个crash/restart语义屏障；
- bounded candidate pagination、shutdown无遗留线程，以及一条legacy sidecar/DB fixture路径。

以下不再是权威验证：

- `r8_*`、`r9_*`至`r22_*`按历史修复轮次命名的quarantine/detach/unlink-verify/stage、
  generation、receipt、residual proof或broker syscall-window矩阵；
- 同euid恶意ancestor/pathname替换、broker partial frame、capability/peer角色、fd/pidfd与双UID
  隔离证明。生产机制删除时对应测试一并删除，不保留mock实现考古。

不可逆或大故障域不变量不能因本次简化而降级：Dolt commit/main CAS、control DB transaction、
跨repository/root误操作和protected artifact误删仍需强验证。但测试语义屏障，不穷举每两个
系统调用之间的调度窗口。同一Contract不变量只保留一处权威断言，同构shape用共享参数表；
保留的测试不得继续使用round编号命名。

## 历史基线

| 阶段 | `repository_service` 全量耗时 |
| --- | ---: |
| 整改前 | 46m47s |
| 关闭 dolt 版本检查后 | 4m14s |
| 叠加 xdist 并行后 | 2m03s |
| 长历史 fixture 改批量提交后 | 63s |

整仓五个 Python 包合计 1031 项测试，`run-tests.sh` 全程约 1m07s。

详见 [Test Suite Runtime Investigation](notes/test-suite-runtime-investigation.md)。
