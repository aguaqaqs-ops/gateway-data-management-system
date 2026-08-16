# P2-R6-EXT-W1 Stage C — Parser/Model Implementation

状态：`complete`

日期：2026-08-16

本记录完成 ENUM/SET bounded parser、manifest model 与无 Dolt 的参数化 unit
tests。没有运行 S6、没有生成正式 package、没有填 golden 完整 case，也没有改
verification/read public wire 映射或历史 S5 evidence。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
决策记录：[ADR 0013](../formal/adr/0013-enum-set-v1-import-semantics.md)
Contract：[Repository Service](../formal/contracts/repository-service.md) §10.1
Stage B 冻结包 commit：`d03e8e94ff8ab10658050559a52beb350fdd8dd3`

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_c_entry_head_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
freeze_commit_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
freeze_committed: yes
stage_a_commit: 2fe7b1fed1fd9c1702335071d4f28aa8be01e626
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
package_version: v1
canonicalization_version: v1
published_package_compatibility: none
image_rebuilt: no
full_s6_run: no
formal_package_generated: no
golden_corpus_filled: no
verification_wire_updated: no
```

Stage C 从 Stage B freeze commit `d03e8e94` 开始。S5 候选 `e7a6e42d` 仍是祖先。
开始前已将 Stage B 文档冻结包单独提交；本 stage 才改生产 parser/model。

## Implementation

新增 [`enum_set_sql.py`](../../../vnext/repository_service/src/gateway_repository_service/enum_set_sql.py)：

- 族判定：只剥 `CHARACTER SET`/`COLLATE`，折叠 label 外空白，第一个整词为
  `ENUM`/`SET` 时要么唯一 normalized spelling，要么 `SQL_TYPE_MALFORMED`
- 严格 grammar：仅单引号 + `''` 转义；残留 token、越界、声明重复、SET 空 label
  与逗号 label 不得落入 unknown/STRINGIFY
- `parse_enum_value` / `parse_set_value`：NULL 独立；禁止 ordinal 与 `str(value)`；
  SET 按声明顺序重排

接入：

- `normalize_sql_type`、`_known_arrow_type`、`convert_value` /
  `_make_column_converter`
- `validate_manifest_sql_type`：ENUM/SET 要求已规范化 spelling，上限 64 KiB，
  不走 ASCII unknown 门

合法 ENUM Arrow 为 `utf8` + `gateway.logical_type=enum`；SET 为 `list<utf8>`
（item 不可空）+ `gateway.logical_type=set`。STRINGIFY 不得降级已知 ENUM/SET。

W0 unknown 探针从 `ENUM('a','b')` 改为仍为 unknown 的 `YEAR`。

## Verification

```text
cd vnext/repository_service
uv run pytest -m unit tests/test_p2_r1_primitives.py tests/test_arrow_mapping_plan.py tests/test_import_package.py tests/test_enum_set_sql_type.py
# 235 passed

uv run pytest -m unit
# 1376 passed, 1 skipped

uv run ruff check . && uv run mypy
# ruff all checks passed; mypy Success: no issues found in 188 source files
```

未重建 image：未触碰 Dockerfile、Compose、entrypoint 或 lockfile。

## Not in this stage (Stage D+)

- golden loader 与 `sql-enum-set/v1` 完整 case
- `verification.py` / `versioned_read/wire.py` 把 `SQL_TYPE_MALFORMED` 映到
  `IMPORT_REJECTED` / `REQUEST_VALIDATION_FAILED`
- producer digest、`sequence_frame` 跨语言 golden、五份 fixture package
- Canonical Row Hash 仍拒绝 `list`

```yaml
stage_c_exit: pass
next: Stage D — Arrow/provider/verification implementation
```
