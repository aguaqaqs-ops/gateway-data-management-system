# WP2 R7 Repository Consumer

状态：WP2 R7 evidence（Repository Service dev-side vector conformance consumer）

日期：2026-07-21

适用：Phase 1 D3 / WP2 R7 — §6.3 Repository consumer

Authority：`docs/backend-vnext/refactoring/formal/plans/phase-1-implementation-design-and-delivery-plan.md` §6.3、§6.4、§6.5

## 1. 摘要

| 项 | 值 |
| --- | --- |
| Normative root | `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/` |
| `vector_set_id` | `gateway-vnext.shared-kernel.canonical-encoding.v1` |
| `vector_set_content_digest` | `sha256:a01eae14d8741cb9253fadc5dafa464afb70e5b1f85a51dd34e6df6b92f25afe` |
| 总 case 数 | 125（valid 83 + invalid 42） |
| Repository consumer 入口 | `vnext/repository_service/tests/conformance/test_vector_conformance.py` |
| Candidate marker | **未包含**（normative root 无 `CANDIDATE_PENDING_WP2_CONFIRMATION`） |

R7 在 Repository Service 侧新增 dev-only conformance consumer，从与 Python/Rust 相同的 fixed normative root 只读加载 vector set，复用 `gateway-shared-kernel[conformance]` 的 `validate_vector_set` / `dispatch_case`，不复制 fixture、不实现第三套 canonical 算法。

## 2. 依赖变更

### 2.1 `vnext/repository_service/pyproject.toml`

- 新增 `[tool.uv.sources]` path 依赖：`gateway-shared-kernel = { path = "../shared_kernel", editable = true }`
- dev 组新增：`gateway-shared-kernel[conformance]`（拉入 `jsonschema`）
- production `dependencies` **未**引入 shared-kernel
- `editable = true` 确保 `gateway_shared_kernel.testing.paths` 的 vnext root 解析指向 monorepo 源码树（非 `.venv` site-packages）
- `gateway_shared_kernel` 已发布 `py.typed`；Repository mypy **未**对 `gateway_shared_kernel.*` 使用 `ignore_missing_imports`

### 2.2 Lockfile

`vnext/repository_service/uv.lock` 已更新，新增 `gateway-shared-kernel`、`jsonschema` 及其传递依赖。

## 3. Consumer 入口与 root 解析

### 3.1 文件布局

| 文件 | 作用 |
| --- | --- |
| `tests/conformance/paths.py` | Repository-owned normative root 发现 |
| `tests/conformance/test_vector_conformance.py` | 主 conformance consumer 测试 |

### 3.2 Root 解析逻辑

1. 若设置 `GATEWAY_SHARED_KERNEL_VECTOR_ROOT`，通过 `gateway_shared_kernel.testing.paths.resolve_vector_root` 解析（与 Rust gate 行为一致）
2. 否则回退到 repository 计算的固定路径：`vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1`
3. 断言 `(root / "vector-set.json").is_file()`；**不复制** fixture

### 3.3 执行流程

1. `load_validated_vector_set(root)`：单次调用完成 fs-safety、manifest/schema、JSONL hash/count/order、`vector_set_content_digest`，返回已验证的 `(manifest, cases)` 快照
2. 从快照 cases 提取 `closure_ids`
3. Repository 显式遍历 cases，逐个调用 `dispatch_case`；**仅在 dispatch 成功后**将 `case_id` 加入 `executed_ids`
4. 断言 `executed_ids == closure_ids`，并与 manifest `case_count` / 唯一性 / ASCII 全局排序对齐

**快照契约**：`manifest` 与 `cases` 来自同一次 `load_validated_vector_set` 调用；不存在先 validate 后独立 re-read 的路径。`test_load_validated_vector_set_rejects_invalid_content_digest` 回归证明篡改 content digest 后无法加载 cases。

## 4. 验证命令与输出

### 4.1 Repository consumer

```bash
cd vnext/repository_service
export GATEWAY_SHARED_KERNEL_VECTOR_ROOT=../fixtures/vectors/shared-kernel/canonical-encoding/v1
uv run pytest -q tests/conformance/
```

结果：`4 passed`（主 conformance + fixed root 布局 + dispatch 入口绑定 + tampered-bytes 负向）

### 4.2 Python validate（normative root）

```bash
cd vnext/shared_kernel
uv run python -m gateway_shared_kernel.testing validate \
  ../fixtures/vectors/shared-kernel/canonical-encoding/v1
```

结果：`vector set ok`（125 cases，closure + dispatch）

### 4.3 Rust conformance（normative root）

```bash
cd vnext/rust
export GATEWAY_SHARED_KERNEL_VECTOR_ROOT=../fixtures/vectors/shared-kernel/canonical-encoding/v1
cargo test --locked -p gateway-shared-kernel vector_conformance -- --nocapture
```

结果：`rust_vector_conformance_matches_normative_root` 通过；manifest `case_count` sum == collected IDs == 125

### 4.4 Gate correctness

```bash
cd vnext && ./scripts/gate.sh correctness
```

结果：`correctness gate passed`（含 shared_kernel + normative validate + repository_service + Rust）

## 5. 三方 ID 一致性证明

§6.4 要求：

```text
python IDs == rust IDs == repository IDs == manifest closure IDs
```

| Consumer | ID 来源 | Count | 唯一性 | 执行 |
| --- | --- | ---: | --- | --- |
| Python (`validate` CLI) | `validate_vector_set` 全量 dispatch | 125 | closure 校验保证 | zero skip |
| Rust (`vector_conformance.rs`) | `case_ids_from_root` + `validate_vector_set` | 125 | `BTreeSet` 去重断言 | zero skip |
| Repository (`test_vector_conformance.py`) | `executed_ids`（显式 `dispatch_case` 循环）== `closure_ids`（`load_validated_vector_set` 快照） | 125 | `set` 去重 + ASCII 排序断言 | zero skip |
| Manifest closure | `vector-set.json` `files[].case_count` 之和 | 125 | per-file + global uniqueness（closure 校验） | — |

三方均从同一物理 normative root 只读消费；无 fixture 复制、无 xfail/skip、无 operation fallback。

## 6. Gate 变更

`vnext/scripts/gate.sh` correctness 模式在 shared_kernel normative validate **之后**、Rust **之前**新增：

```bash
REPOSITORY_ROOT="${VNEXT_ROOT}/repository_service"
cd "${REPOSITORY_ROOT}"
uv sync --locked --offline --all-groups
uv run --offline --no-sync ruff check src tests
uv run --offline --no-sync mypy
uv run --offline --no-sync pytest -q
```

`GATEWAY_SHARED_KERNEL_VECTOR_ROOT` 在 Python validate 后已 export，Repository 测试复用同一 pin。

## 7. 人工 review checklist（§6.3 + §6.4 + §6.5）

- [ ] Repository dev 依赖仅 `gateway-shared-kernel[conformance]`（path + editable），production 未引入
- [ ] Consumer 从 fixed normative root 直接发现 `vector-set.json`，无 fixture 复制
- [ ] 125 cases 全量执行，无 skip/xfail/operation fallback
- [ ] Valid case 完整 bytes/digest 比较；Invalid case stable error code（由 `dispatch_case` 保证）
- [ ] 无第三套 canonical 算法；test-only 代码未提升为 Repository wire type
- [ ] Normative root 无 `CANDIDATE_PENDING_WP2_CONFIRMATION` marker
- [ ] 无 bless 入口、无 generator 写入 normative root
- [ ] `gate.sh correctness` 含 Repository consumer 且通过

## 8. 不在本步范围

- 修改 normative vectors（除非 authority 冲突）
- Arrow / PyO3 / `gateway-compute-core` 生产接入
- `gateway-repository-service` CLI `main()` 入口修复（bootstrap 遗留）
- `gate.sh bootstrap` 扩展 repository sync
