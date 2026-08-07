# 测试套件耗时调查

调查时间：2026-08-07。目标是回答"测试是否写得过多、分阶段任务动辄数十分钟是否必须"。

结论：测试数量正常，问题在运行方式。当前 46 分钟的全量耗时中约 85% 是 dolt 的外部版本检查网络等待，与测试逻辑无关。

**状态：P1–P4 已于 2026-08-07 全部实施。`repository_service` 全量从 46m47s 降到 63s（44 倍），整仓五个 Python 包合计 1m07s。**沉淀出的规范见
[Testing Conventions](../testing-conventions.md) 与仓库根 `AGENTS.md`；实施结果记录在文末。

## 基线

按包实测（单进程，`uv run pytest -q`）：

| 包 | 测试数 | 耗时 |
| --- | ---: | ---: |
| `shared_kernel` | 232 | 1.0s |
| `repository_contracts` | 64 | 0.2s |
| `repository_client` | 15 | 0.5s |
| `backend` | 18 | 0.8s |
| `repository_service` | 701 | 2806.97s（46m47s） |

合计 1030 个测试。其中 329 个总共 2.5 秒，剩余 701 个占据全部 46 分钟。

测试代码 16,997 行，`src/` 源码 20,546 行，比例 0.83:1。这个比例属于正常偏保守，**测试总量本身不构成问题**，不建议以"删测试"为优化手段。

## 关键观察：耗时不是计算，是空等

`repository_service` 全量运行的资源画像：

- wall：2806.97s
- user：4m05.7s
- sys：2m46.5s

CPU 合计约 411s，占 wall 的 14.6%；**约 2396 秒是进程空等**。机器有 16 核，全程单进程，无 `pytest-xdist`。

`--durations=30` 显示耗时高度量化在 5 秒的整数倍附近（16s / 21s / 26s / 32s / 37s / 42s / 46s），提示存在固定时长的等待而非可变计算量。

## 根因：dolt 版本检查网络往返

### 定位过程

逐层剖析 `test_import_provider.py` 的 `import_provider` fixture：

```text
import:                 0.418s
settings:               0.001s
layout:                 0.000s
runner (DoltRunner()):  13.366s   <-- 瓶颈
cli ctor:               0.000s
initialize_repository:  0.076s
```

真正的 `dolt init` 只需 0.076s，`DoltRunner` 的构造函数却要 5~13s。该构造函数只做一件外部动作，即执行一次 `dolt version`：

```1026:1031:vnext/repository_service/src/gateway_repository_service/process.py
    def __init__(self, settings: RepositoryServiceSettings, server_root: Path) -> None:
        self.settings = settings
        self.server_root = server_root.resolve()
        self.home = self.server_root / "provider" / "runner-home"
        self.home.mkdir(parents=True, exist_ok=True)
        self._validate_version()
```

`process.py` 第 1134 行把子进程的 `HOME` 指向 `self.home`，即 `server_root/provider/runner-home`。而 `server_root` 源自 `tmp_path`，**每个测试都得到一个全新的空 HOME**。

dolt 在全新 HOME 下首次执行任何命令时，会向外部查询最新发布版本并打印过期告警。这个网络往返在本环境需要 3~5 秒（并发压力下观测到 13 秒）。

### 验证

原生 `dolt version` 三组对照：

| 条件 | 耗时 | 输出 |
| --- | ---: | --- |
| 全新空 HOME | 3.29s | `Warning: you are on an old version of Dolt. The newest version is 2.2.3.` |
| 同一 HOME 第二次（已缓存） | 0.056s | 同上 |
| 全新 HOME + 预置 `versioncheck.disabled` | 0.052s | 无告警 |
| 全新 HOME + 无网络命名空间（`unshare -n`） | 0.057s | `Warning: unable to query latest released Dolt version` |

断网即恢复到 0.057s，确认是出站网络调用而非本地初始化开销。

在项目实际代码路径上直接对照 `DoltRunner()` 构造（交替执行，排除缓存干扰）：

```text
seed=False  DoltRunner(): 5.054s
seed=True   DoltRunner(): 0.036s
seed=False  DoltRunner(): 5.055s
seed=True   DoltRunner(): 0.038s
```

`seed=True` 表示在 runner-home 下预置 `.dolt/config_global.json` 内容 `{"versioncheck.disabled": "true"}`。差距 140 倍。

### 量级吻合

空闲时间 2396s ÷ 单次 5.05s ≈ 474 次 `DoltRunner` 构造。701 个测试中大量测试构造 1 个 runner，重启恢复类测试（`test_synchronous_mutation_recovery.py`，单测 26~47s）会构造多个，量级完全吻合。即**约 80–85% 的全量耗时可归因于此单一原因**。

### 这同时是一个生产问题

`OfflineCliProvider` 的命名与 `DoltRunner` 的 "a private environment" 注释都表明该路径应当是离线的，但每个新建的 runner-home 都会发出出站请求。影响不限于测试：

- 离线 / 气隙部署下服务启动会白等 3~5 秒后才拿到降级结果。
- 一个声明为 offline 的组件产生了未预期的出站网络连接。

因此该修复独立于测试提速，本身就应该做。

## 优化方向

按投入产出排序。前两项不改动任何测试语义。

### P1：关闭 dolt 版本检查

在 `DoltRunner.__init__` 创建 `self.home` 之后写入 dolt 全局配置（`.dolt/config_global.json` 置 `versioncheck.disabled`），使私有 HOME 从一开始就不触发外部查询。

- 改动量：一处，行级。
- 预期收益：`repository_service` 全量 46m47s → 约 8 分钟。
- 附带收益：消除 offline 路径的出站网络调用与服务启动延迟。

### P2：引入 pytest-xdist

机器 16 核，当前全程单进程。测试普遍使用 `tmp_path` 做目录隔离（`test_p2_r1_audit_corrective.py` 98 处、`test_auth_lifecycle.py` 114 处等），结构上已具备并行安全前提。

- 预期收益：与 P1 叠加后约 8 分钟 → 1~2 分钟。
- 需要注意：`_candidate_on_private_ref` 使用固定的 `OPERATION_ID` 常量派生 private ref 名，若后续改为共享仓库需先改成按测试唯一。当前每测试独立仓库，不受影响。

### P3：修正测试分层

`test_import_provider.py` 单文件 252 个测试，占 `repository_service` 的 36%。其中 56 个测试的形态是"用真实 dolt 建仓并建私有分支，然后把 `run_cli` 整个 mock 掉"，实际验证目标是纯 JSON 解析：

```2199:2220:vnext/repository_service/tests/test_import_provider.py
@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_count_rejects_extra_cell(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_extra_cell (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
```

`read_catalog` 仅通过 `self._cli.query_json` / `self._cli.catalog` 与外部交互，行宽与 schema 校验位于 `_require_exactly_one_row` / `value` 等纯函数中，不需要真实仓库状态。

实测这类测试的 setup/call 比例：setup 5.1~13.6s，call 仅 0.8~0.95s。建议对解析函数直接做参数化单测，`test_catalog_count_rejects_extra_cell`、`test_catalog_count_rejects_extra_field_real_dolt_shape`、`test_catalog_json_rejects_extra_or_missing_cells`、`test_scalar_metadata_rejects_positional_multi_cell_row` 这类结构同构、仅 payload 与期望消息不同的用例应合并为一个参数化用例。

### P4：为分阶段任务提供选择性运行入口

当前 `repository_service/pyproject.toml` 的 `[tool.pytest.ini_options]` 只配置了 `testpaths` 与 `pythonpath`，没有任何 marker 定义，因此分阶段验证只能跑全量。

建议区分 `unit` 与 `integration`（后者即依赖真实 dolt 的用例，已有 `dolt_available()` skipif 可作为划分依据），使阶段性验证只跑受影响的包与单测层，全量留给提交前与 CI。

## 回答原始问题

- 数十分钟的测试**不是必须的**。当前耗时主要不来自测试覆盖面，而来自一个可以行级修复的外部网络等待。
- 测试写得**不算多**（0.83:1），不建议削减覆盖面。
- P1 + P2 预计把全量从 46 分钟压到 1~2 分钟，且不改动任何测试语义；P3、P4 属于结构性改善，可渐进推进。

## 实施结果（2026-08-07）

### 逐步实测

| 阶段 | `repository_service` 全量 | 相对基线 |
| --- | ---: | ---: |
| 整改前 | 46m47s | 1.0x |
| P1 关闭 dolt 版本检查 | 4m14s | 11x |
| P2 叠加 xdist `-n auto` | 2m03s | 23x |
| 长历史 fixture 改批量提交 | 63s | 44x |

整仓五个 Python 包合计 1031 项测试，`./vnext/scripts/run-tests.sh` 全程约 1m07s。
日常迭代的 `-m unit` 子集 443 项，约 7 秒，且在 dolt 完全不可用时也全绿。

### 与原计划的差异

三处超出原计划范围的改动：

1. **serial 组比预估多两项。** 计划识别出 4 组时序敏感测试；并行实测暴露出第 5 项
   `test_concurrent_streams_with_over_128k_field`（两个线程流式读取 140KB，隔离运行
   2.88s，并行下涨到 20.9s 并间歇失败），一并归入 serial。最终 serial 组 6 项，
   连跑 3 次稳定在 4.2~4.7s。

2. **marker 误分类比预估多得多。** 计划预计 3 个测试隐式依赖 dolt。改为在 conftest
   中按 fixture 依赖自动判定后消除了 6 个，再用"移开 dolt 跑 `-m unit`"实测，又发现
   13 个（含既有的 `test_runner_validates_exact_dolt_version`，属整改前就存在的漏网）。
   静态扫描无法发现这些，只有实跑能验证。该判据已写入规范。

3. **长历史 fixture 改为批量提交。** `test_marker_scan_unique_with_long_history` 循环
   spawn 1000 次 `dolt commit`，并行后成为整个套件的关键路径（单测 105s，占并行墙钟
   九成）。改为单次 `replay_sql` 执行 1000 条 `CALL DOLT_COMMIT`，65s → 1.65s。已加
   `SELECT COUNT(*) FROM dolt_log` 深度断言守住测试前提，实测深度 1001，与原实现等价；
   反向验证（阈值抬到 100000）确认断言生效。

### 附带修复

- 加 `pytest-xdist` 改变了 `uv.lock`，同步更新了 `Dockerfile` 的 `ARG UV_LOCK_SHA256`，
  否则 `test_dockerfile_uv_lock_sha256_matches_lockfile` 失败。该联动已写入 `AGENTS.md`。
- 159 处重复的 `@pytest.mark.skipif(not dolt_available(), ...)` 收敛为 `@pytest.mark.integration`，
  门禁集中到 `tests/conftest.py` 一处。
- P3 把 4 个同构 JSON 行形校验用例合并为一个参数化用例，其中
  `test_catalog_count_rejects_extra_cell` 的 payload 与同文件另一用例逐字节相同，属纯冗余。

## 复现方式

```bash
# 基线
cd vnext/repository_service && time uv run pytest -q --durations=30

# 版本检查开销对照
mkdir -p /tmp/h_off/.dolt
echo '{"versioncheck.disabled":"true"}' > /tmp/h_off/.dolt/config_global.json
mkdir -p /tmp/h_on
time env HOME=/tmp/h_off dolt version   # ~0.05s
time env HOME=/tmp/h_on  dolt version   # ~3-5s
unshare -n -- env HOME=/tmp/h_net dolt version   # ~0.06s，输出无法查询版本
```
