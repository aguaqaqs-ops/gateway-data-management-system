# AGENTS

本仓库的 agent 硬约束。完整背景见 [docs/backend-vnext/testing-conventions.md](docs/backend-vnext/testing-conventions.md)。

## 跑测试

权威入口：

```bash
./vnext/scripts/run-tests.sh
```

阶段性验证不要跑全量。按范围收敛：

```bash
cd vnext/repository_service
uv run pytest -m unit          # 约 910 项，无外部依赖，约 12 秒
uv run pytest -m integration   # 需要真实 dolt
uv run pytest -m serial -n 0   # 时序敏感组，必须串行
```

`repository_service` 默认并行（`-n auto`）；其余包单进程，不要给它们加 xdist。

## 写测试

三个 marker 已在全部包声明，`--strict-markers` 生效，拼错会导致收集失败。

- **不要**手写 `@pytest.mark.skipif(not dolt_available(), ...)`。dolt 门禁只有一处，
  在 `vnext/repository_service/tests/conftest.py`。
- 通过 `lifecycle_settings()`、`ServiceRuntime.start()`、`DoltRunner()` 等方式依赖
  真实 dolt 的测试，**必须**加 `@pytest.mark.integration`。请求 `import_layout` /
  `import_provider` fixture 的会被 conftest 自动判定，无需重复标注。
- 依赖固定时间预算（`Event.wait(timeout=...)`、`thread.join(timeout=...)`、子进程
  sleep 与 stream timeout 的相对关系）的测试，**必须**加 `@pytest.mark.serial`。
- 改动测试分类后，用「移开 dolt 再跑 `-m unit`」验证，静态扫描不可靠：

```bash
mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
uv run pytest -m unit; mv /usr/local/bin/dolt.parked /usr/local/bin/dolt
```

## 测试性能红线

- **禁止**为纯解析、纯校验、纯类型映射的逻辑引入会执行 `dolt init` 的 fixture。
  「建真实仓库再把 `run_cli` 整个 mock 掉」是明确的反模式。
- 仅 payload 与期望错误消息不同的同构用例，**必须**收敛为模块级共享参数表
  （范例：`MALFORMED_JSON_SHAPES`、`CATALOG_ROW_SHAPE_FAULTS`），不得复制粘贴成多个
  测试函数。
- 构造测试前置状态时，不要在循环里反复 spawn 外部进程，按批构造。
- 任何创建全新 dolt HOME 的代码路径，必须预置 `.dolt/config_global.json` 关闭
  versioncheck（见 `DoltRunner._seed_private_dolt_config`）。否则每次都会联网查版本，
  单次 3~5 秒，且违反 offline provider 边界。

## 改依赖

各包依赖一律精确钉版本（`==`），用 `uv add --dev` 添加。

改动 `vnext/repository_service/uv.lock` 后，**必须**同步更新
`vnext/repository_service/Dockerfile` 里的 `ARG UV_LOCK_SHA256`，否则
`test_dockerfile_uv_lock_sha256_matches_lockfile` 会失败：

```bash
sha256sum vnext/repository_service/uv.lock
```

## 提交前

五个 Python 包都要过 ruff 与 mypy（`repository_service` 为 `strict = true` 且覆盖
`tests`）。mypy 增量缓存命中时五个包合计约 1.5 秒，不是耗时项，不要为了省时间跳过：

```bash
cd vnext/<package> && uv run ruff check . && uv run mypy
```
