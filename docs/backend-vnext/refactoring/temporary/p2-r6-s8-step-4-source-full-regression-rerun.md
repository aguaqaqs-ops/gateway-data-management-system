# P2-R6-S8 Step 4 — Source Full Regression Rerun

状态：`pass`

日期：2026-08-17

本记录是 S8-6 P1 修复后的精确三 ignore 全量回归。原
[p2-r6-s8-step-4-source-full-regression.md](p2-r6-s8-step-4-source-full-regression.md)
保留为修复前证据。权威命令一次通过，无失败、无未分类 skip。

分类修复：[p2-r6-s8-step-2-classification-repair.md](p2-r6-s8-step-2-classification-repair.md)
`3e4bd1fc`

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
classification_repair_sha: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
prior_s8_4_sha: a27fe00453a910d6bdb2d0369b7923125d5d9278
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
production_code_changed: no
test_classification_changed: yes
docker_or_compose_changed: no
repairs_in_this_rerun: none
```

## Authoritative command

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

未附加 `-m`、`-k`、`--ignore-glob`。wall clock `302927 ms`（约 5m03s），
`exit_code=0`。

## Package commands and counts

collected 来自同 ignore 的 `--collect-only`（service 两段）或 passed+skipped。

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q` + 三 ignore | 242 | 242 | 0 | 0 | 0.81s |
| repository_contracts | `uv run pytest -q` + 三 ignore | 152 | 152 | 0 | 0 | 0.20s |
| repository_client | `uv run pytest -q` + 三 ignore | 154 | 154 | 0 | 0 | 1.26s |
| backend | `uv run pytest -q` + 三 ignore | 35 | 35 | 0 | 0 | 0.64s |
| repository_service parallel | `uv run pytest -q -m "not serial"` + 三 ignore | 1639 | 1638 | 1 | 0 | 105.46s |
| repository_service serial | `uv run pytest -q -m serial -n 0` + 三 ignore | 197 | 197 | 0 | 0 | 189.90s |

serial 段 `1639 deselected`。repository_service 三 ignore 后全集仍为 1836。

相对修复前 S8-4（parallel 1636 / serial 200）：3 个 nodeid 离开 serial 进入
parallel。这是去掉模块级 `serial` 的预期结果：

- 两个 in-process `unit` 用例不再被整文件 serial 拖进 serial 段
- `test_check_does_not_mutate_business_files_schema_or_head` 函数级本就无
  `serial`，不再被模块级标记串行化

backend 仍有 1 个 `StarletteDeprecationWarning`，不是失败。

## Skip classification

| nodeid | suite | class |
| --- | --- | --- |
| `tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup` | parallel | expected；`GATEWAY_P2R1_TARGET_CONTAINER != "1"` |

无 Dolt-missing skip。无其他 skip。无失败。

```yaml
repairs: none
first_failure: none
authoritative_exit_code: 0
```

## Docker / Compose decision

```text
Current HEAD: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
Container rebuild required: no
Reason: test marker classification only
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

## Exit

```yaml
source_regression_with_exact_docker_ignores: pass
exact_docker_ignores: 3
unexpected_skip_or_failure: no
S8_exit: no
S9_ready: no
allow_s8_handoff: no
phase_2_complete: no
next: S8-5 hygiene rerun
```
