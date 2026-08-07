# Testing Conventions

状态：2026-08-07 建立，随 [Test Suite Runtime Investigation](notes/test-suite-runtime-investigation.md) 的整改落地

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
uv run pytest -m unit          # 约 443 项，无外部依赖，约 7 秒
uv run pytest -m integration   # 需要真实 dolt
uv run pytest -m serial -n 0   # 时序敏感组，必须串行
```

裸跑 `uv run pytest` 会执行全部测试并自动并行；结果正确，但 `serial` 组会与其他测试
争用 CPU，判定 flaky 时以脚本为准。

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

## 历史基线

| 阶段 | `repository_service` 全量耗时 |
| --- | ---: |
| 整改前 | 46m47s |
| 关闭 dolt 版本检查后 | 4m14s |
| 叠加 xdist 并行后 | 2m03s |
| 长历史 fixture 改批量提交后 | 63s |

整仓五个 Python 包合计 1031 项测试，`run-tests.sh` 全程约 1m07s。

详见 [Test Suite Runtime Investigation](notes/test-suite-runtime-investigation.md)。
