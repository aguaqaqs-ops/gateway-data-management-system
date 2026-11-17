# 后端阶段门禁提速方案（定稿，已落地）

日期：2026-11-16。依据：`main` 上的门禁脚本、runner 与闭包脚本，以及 `ct108-gw-dms-04` `/home/dev/gdds-gate-results` 2026-11-10 至 2026-11-16 的 55 次运行记录。过程材料（含 A 期审核意见与实测记录）保留于仓库外 `/home/dev/gdds-stage-exchange/gate-cost-reduction/`。

## 1. 目标与结论

目标：小改动不再付出一次约 25 分钟的 backend 整包运行；阶段最终候选、S5、发布和 production 门禁的验证内容不变。

分三期，均已完成确认、实施与专用节点验收（`main` 提交 `a22c7ad523..35fa9d3f35` 及 `04` 节点配置）：

| 期 | 内容 | 是否改变验证内容 | 前提 / 结论 |
|---|---|---|---|
| A | 修复沿用失效、失败早停、放宽重复的容器区间扫描、记录单项耗时 | 否 | Owner 同意 O1、O3；已在 `cf7bea421c` 落地并通过 `04` 验收 |
| B | 增加 `--purpose package` 工作包档位（跳过 `@pytest.mark.container`） | 是，改变工作包证据要求 | D1 实测容器占 17.45m（>8m 线），Owner 同意 O2；已在 `35fa9d3f35` 落地并通过 `04` 验收 |
| C | 调整并行 worker 数 | 否 | D2 在 `05` 实测 `8` / `16` 各 3 次全过；已将 `04` `GATEWAY_TEST_WORKERS` 调为 `16` |

## 2. 依据

**运行记录。** 55 次运行中 41 次通过、14 次失败。请求 backend 且通过的 38 次里，backend 全部是实跑，没有一次沿用。

**backend 为什么从不沿用。** 闭包组件 `non-git:package-uv-environment` 对整个 `vnext/backend/.venv` 求摘要。`maturin 1.14.1` 默认在 wheel 的 `dist-info/sboms/gateway-compute-python.cyclonedx.json` 里写入随机 `serialNumber` 和构建时间，`RECORD` 又记录了这个文件的哈希，所以每次 `--reinstall-package gateway-compute-python` 之后摘要都变。

**重复运行的规模。** 38 次里有 16 次的 `vnext/` 树与此前已通过的提交完全相同（约 6.1 小时）。其中 12 次满足现有全部沿用前提（约 4.6 小时）；另 4 次是合并提交，被 `container_equivalent` 的区间扫描挡住（约 1.5 小时）。

**一次 backend 运行的构成（约 25 分钟）。**

| 环节 | 耗时 |
|---|---|
| 准备阶段同步环境并冷编译 Rust 扩展 | 约 1 分钟 |
| runner 清空 cargo target 后再次冷编译 | 约 1 分钟 |
| 并行批 5286 项，4 个 worker | 5.3 分钟 |
| serial 批 132 项，含全部容器测试 | 17.7 分钟 |

**失败运行。** 13 次 runner 失败中，10 次在 backend 并行批就已失败，runner 仍跑完 serial 批（每次约 14–18 分钟，合计约 3 小时）。这 10 次里只有 1 次在 serial 批另有失败。

## 3. A 期：不改变验证内容的修正

四个提交落地于 `main`（`a22c7ad523`、`8c2d1e6dfb`、`13a72022aa`、`cf7bea421c`）：

### A1 关闭扩展 wheel 的 SBOM

`vnext/rust/gateway-compute-python/pyproject.toml` 增加 `[tool.maturin.sbom]`（`rust = false`、`auditwheel = false`）并注明原因。`Dockerfile.dependency-base` 只复制各 crate 的 `Cargo.toml`，因此依赖基础镜像不需重建。

### A2 便宜的批次先跑，失败就不进 serial 批

`vnext/scripts/run-tests.sh` 调整执行顺序：`rust` → 三个小包 → `backend (parallel)` → `repository_service (parallel)` → 若任一前序步失败则跳过两个 serial 批（`PACKAGE_STATUS` 初值改为 `not_run`），否则执行 `backend (serial)` → `repository_service (serial)`。同步更新 `vnext/repository_service/tests/test_run_tests_script.py` 与 `docs/backend-vnext/testing-conventions.md`。

### A3 容器沿用改为比较 `vnext` 树，不再扫描区间

`scripts/run-stage-gate.py` 的 `container_equivalent` 去掉 `git log --full-history -m … -- vnext` 区间扫描，改为核对来源提交与目标提交的祖先关系、双方 `vnext` 树 ID 相等（`V:vnext == HEAD:vnext`）、RS 镜像 label 及入口镜像身份（闭包 manifest 已覆盖 `vnext` 树、非 Git context 与文件权限，经独审确认不存在树相同而区间扫描额外挡住的容器输入）。同步更新 `scripts/tests/test_stage_gate.py`、`scripts/README.md`、`docs/backend-vnext/testing-conventions.md` 与 `docs/backend-vnext/refactoring/formal/plans/p7-gate-and-stage-workflow-design.md`。

### A4 记录单项耗时

`vnext/scripts/run-tests.sh` 的 `run_locked_pytest` 增加 `--durations=0 --durations-min=1.0`，完整列出 1 秒以上的 setup/call/teardown 阶段供 D1 统计与后续性能排查使用。

## 4. 判断点 D1 实测结果与 B 期启动结论

在 A 期验收第 2 步（`cf7bea421c`，运行 `20261116T152108Z-fc7b86db7d0e`）测得：

- **`backend (serial)`（132 passed，总耗时 `1125.11s` = `18.75` 分钟）：** 11 个容器测试文件 ≥1s 阶段合计 **17.45 分钟（1047.25s）**，其余非容器 serial 测试 ≥1s 阶段合计 **0.68 分钟（40.63s）**（前十项分布于 `5.45s`–`1.91s`）。
- **`repository_service (serial)`（231 passed，总耗时 `634.58s` = `10.58` 分钟）：** 4 个容器测试文件 ≥1s 阶段合计 **2.89 分钟（173.44s）**，其余非容器 serial 测试 ≥1s 阶段合计 **6.92 分钟（415.12s）**（最长项 `test_http_disconnect_reports_command_result_cancelled` 113.17s，其余前十 `15.80s`–`14.69s`）。

容器测试占 `backend (serial)` 绝大部分（17.45 分钟 > 8 分钟参考线），Owner 确认 **O2**，按计划实施 B 期。

## 5. B 期：工作包档位

两个提交落地于 `main`（`c34b21c485`、`35fa9d3f35`）：

- **标记。**
  - `backend` 通过 `vnext/backend/tests/conftest.py` 的 `pytest_configure` 注册 `container` marker（注：`vnext/backend/pyproject.toml` 是预装基础镜像 `gateway-backend-deps:lock-*` 的哈希输入，不修改该文件可避免触发五节点镜像重建），标注全部 11 个容器测试文件。
  - `repository_service` 在 `vnext/repository_service/pyproject.toml` 声明 `container` marker，标注 4 个容器测试文件及 `test_storage_root_boundaries.py` 中 2 个真实容器用例。
- **runner。** `vnext/scripts/run-tests.sh` 删除 `BACKEND_COMPOSE_TEST_FILES` 与 `REPOSITORY_SERVICE_COMPOSE_TEST_FILES` 两份手工清单，统一使用 `container` marker；设置 `GATEWAY_TEST_SCOPE=package` 时，并行批与 serial 批在原 marker 表达式后均排除 `and not container`；启用 `GATEWAY_TEST_BASETEMP` 且非 `package` scope 时，serial 按 `(serial and not parallel_safe) and not container` 与 `(serial and not parallel_safe) and container` 拆批。
- **门禁。** `scripts/run-stage-gate.py` 增加 `--purpose package`：设置 `GATEWAY_TEST_SCOPE=package`，结果记录 `"scope": "package"` 与 `container_gate.status="not_run"`；跳过容器缓存预置前提、RS 镜像构建、Compose provenance 校验与 `container_equivalent`。因 `test_input_closure.py` 对 `backend` / `repository_service` 纳入 `GATEWAY_TEST_SCOPE`，两种档位互不沿用，而四个快包仍共享合格来源。
- **规则文档。** 同步更新 `AGENTS.md`（“跑测试”、“写测试”、“Docker / Compose 验证”）、`scripts/README.md` 与 `docs/backend-vnext/testing-conventions.md`。

## 6. C 期：并行 worker 数（判断点 D2）

在独立空闲节点 `ct108-gw-dms-05`（32 vCPU，clean detached worktree @ `cf7bea421c`）对 `backend` 并行批（`-m "(not serial) or parallel_safe"`）分别用 `8` 和 `16` 各测 3 次，全部 `5311 passed, exit=0`：

| `GATEWAY_TEST_WORKERS` | 第 1 次 | 第 2 次 | 第 3 次 | 均值 | 对比 `workers=4`（321s） |
|---|---|---|---|---|---|
| 8 | 296.26s | 289.21s | 285.52s | 290.33s | 快 ~31s |
| 16 | 256.34s | 255.82s | 256.61s | 256.26s | 快 ~65s |

按规则取 3 次全部通过的最大值，已将 `ct108-gw-dms-04` `/home/dev/gdds-stage-gate-config.json` 中 `GATEWAY_TEST_WORKERS` 更新为 `"16"`（不进入闭包，不使现有来源失效）。

## 7. 不做的事项

| 事项 | 不做的原因 | 重新考虑的条件 |
|---|---|---|
| 收窄闭包（例如 benchmarks、tests 不触发容器包；repository_service 不含整个 `vnext` 树） | A、B 落地后，这类改动在工作包档位已不跑容器；阶段末多跑一次 `repository_service` 约 10.6 分钟，每阶段一次 | 阶段末重跑成为明显成本 |
| 一次运行只编译一次扩展 | 每次只省约 1 分钟，却要动 DC48 的强制重装规则 | 扩展编译时间明显变长 |
| 把 ruff、mypy 并入门禁 | 扩大门禁范围，mypy 耗时未测 | 出现因漏跑静态检查而失败的门禁 |
| 新增带占用和记录的 focused 入口 | B 期的工作包档位已覆盖这个需求 | — |

## 8. Owner 决定与验收留痕

- **O1（Owner 已确认）：** 同意 A1 移除产品 wheel 中的 SBOM；经 `review-a-phase.md` 核实无漏挡输入后同意 A3 放宽容器沿用至 `V:vnext == HEAD:vnext`；免除额外 `gpt-6.1-sol` 独审，原审核一次即可。
- **O2（Owner 已确认）：** 依据 D1 实测结果同意工作包改用不含容器测试的 `--purpose package` 档位；阶段最终候选仍需 `--purpose stage`，S5/发布/production 保持不变。
- **O3（Owner 已确认）：** `gw08-dual-env` 已合入 `main`，统一直接合入 `main` 并回收短期 worktree。
- **验收证据位置（`ct108-gw-dms-04` `/home/dev/gdds-gate-results/`）：**
  - A 期 `cf7bea421c`：六包全跑 `20261116T152108Z-fc7b86db7d0e`（pass，无 `sboms` 目录，prepared/runner manifest 一致）、同提交 `carried` 复跑 `20261116T160459Z-6a2f6647c2ec`（6 包 `carried`）、文档提交 `carried` 验证 `20261116T160926Z-29026917cf63`（6 包 `carried`）。
  - B 期 `35fa9d3f35`：`--purpose package --packages backend` `20261116T231616Z-2017ff7bd968`（pass，8m40s，`backend (serial)` 73s）、`--purpose stage --packages backend` `20261116T232548Z-dd9eb1bb592f`（pass，未沿用，132 serial 全过）、文档提交 `--purpose package` `20261116T235243Z-829cbc91efba`（pass，`backend carried`）。
