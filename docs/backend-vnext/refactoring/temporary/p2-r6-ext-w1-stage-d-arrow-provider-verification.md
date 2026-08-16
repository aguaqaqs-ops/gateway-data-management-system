# P2-R6-EXT-W1 Stage D — Arrow/Provider/Verification Implementation

状态：`complete`

日期：2026-08-16

本记录完成 ENUM/SET Arrow 批转换、verification/read public wire 映射，以及
`sql-enum-set/v1` 完整 golden。没有运行 S6、没有生成正式 package、没有改历史
S5 evidence，也没有重建 image。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
决策记录：[ADR 0013](../formal/adr/0013-enum-set-v1-import-semantics.md)
Contract：[Repository Service](../formal/contracts/repository-service.md) §10.1
Stage C commit：`8425c41b85bfee3ade8c5b4320ada003e19beabb`

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_d_entry_head_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_c_commit: 8425c41b85bfee3ade8c5b4320ada003e19beabb
freeze_commit_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
package_version: v1
canonicalization_version: v1
published_package_compatibility: none
image_rebuilt: no
full_s6_run: no
formal_package_generated: no
golden_corpus_filled: yes
verification_wire_updated: yes
```

Stage D 从 Stage C commit `8425c41b` 开始。S5 候选 `e7a6e42d` 仍是祖先。

## Implementation

Wire 映射：

- `compile_table_plan` 为 `SqlTypeMalformedError` 附 `table`/`column`
- `_compile_table_plans`：族内畸形 → `IMPORT_REJECTED`（STRINGIFY 同样），不走
  unknown/`VERIFICATION_FAILED_NOT_PUBLISHED` unmappable 分支
- `_reject_unknown_catalog_types`：NONE+REJECT 的畸形 ENUM/SET → `IMPORT_REJECTED`
- `map_read_error`：编译期畸形 ENUM/SET → `422` `REQUEST_VALIDATION_FAILED`，不得
  `UNKNOWN_SQL_TYPE`

Arrow：catalog / STRUCTURAL / FULL_SCAN / read 继续共用 `compile_table_plan`。
`record_batch` 证明 ENUM `utf8`、SET `list<utf8>`、NULL 与空 SET 可区分，且无
`gateway.lossy` / dictionary / `large_string`。

Golden：

- 填满 [`sql-enum-set/v1`](../../../vnext/fixtures/vectors/repository/sql-enum-set/v1/)
  （25 case：9 normalize / 9 values / 7 invalid）
- Repository loader：[`sql_enum_set_cases.py`](../../../vnext/repository_service/tests/support/sql_enum_set_cases.py)
- 测试专用 §3.2 encoder 在 `tests/support/`，生产 `src/` 不 import Shared Kernel
- Python/Rust Shared Kernel 只消费 `values.jsonl` encode 操作；128-case corpus 未改

NONE+STRINGIFY 仍按 §12 不读 catalog。畸形类型由 package admission 与 NONE+REJECT
type catalog 覆盖。

## Verification

```text
cd vnext/repository_service
uv run pytest -m unit
# 1408 passed, 1 skipped

uv run ruff check . && uv run mypy
# ruff all checks passed; mypy Success: no issues found in 191 source files

cd vnext/shared_kernel
uv run pytest tests/test_sql_enum_set_values.py
# 10 passed

cd vnext/rust
cargo test -p gateway-shared-kernel --test sql_enum_set_values --test vector_conformance
# sql_enum_set_values ok; vector_conformance 128-case corpus ok
```

未重建 image：未触碰 Dockerfile、Compose、entrypoint 或 lockfile。

## Not in this stage (Stage E+)

- 独立 implementation review
- 五份 fixture package 与 `canonicalization_manifest_digest`
- production validator / S6 capacity / W2
- Canonical Row Hash 仍拒绝 `list`

```yaml
stage_d_exit: pass
next: Stage E — Implementation review
```
