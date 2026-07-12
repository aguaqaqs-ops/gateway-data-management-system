# Testing Fixtures

本文定义 backend vNext 的 fixture 分层、可提交样本和外部 raw 输入边界。

## 目标

- 让 vNext 测试目录独立于旧项目测试目录。
- 允许少量可审查的小 SQL fixture 进入仓库。
- 明确 raw 业务数据、裁剪回归样本和纯单元样本的落点。

## 目录约定

```text
gateway-data-management-system/backend/tests/backend_vnext/
  README.md
  unit/
  contract/
  integration/
  fixtures/
    README.md
    minimal/
      README.md
      *.sql
    regression/
      README.md
      *.sql
    external/
      README.md
```

## 目录职责

### `fixtures/minimal/`

- 存放最小、手写、单行为样本。
- 适合 unit / contract 测试。
- 每个 fixture 聚焦一个语义点，例如 `NULL`、字符串转义、列顺序、空表、单表多行插入。
- 推荐文件：
  - `source.sql`
  - `expected.json`
  - `expected.md`
  - `fixture.yaml` 可选

### `fixtures/regression/`

- 存放裁剪后的真实问题样本。
- 样本必须脱敏并可复现。
- 每个样本都要带元数据，至少说明：
  - 场景名
  - 验证目标
  - baseline / initial / modified 输入
  - 保留的表和行
  - 被移除的数据
  - 预期输出或断言
  - 脱敏状态
- 推荐文件：
  - `source.sql`
  - `metadata.yaml`
  - `expected.json`
  - `expected.md`

### Ordered diff fixtures

Ordered diff P1 fixture 优先放在 `fixtures/minimal/ordered/`，裁剪自真实 IEC104 的样本放在 `fixtures/regression/ordered/`。

建议最小 fixture：

```text
ordered_iec104_unchanged
ordered_tail_insert
ordered_tail_delete
ordered_middle_insert
ordered_middle_delete
ordered_content_update_name_only
ordered_content_update_other_column
ordered_position_shift_not_move
ordered_move_simple
ordered_pseudo_blank_insert
ordered_pseudo_blank_delete
ordered_duplicate_gid_degraded
ordered_duplicate_position_degraded
ordered_position_gap_degraded
ordered_complex_reorder_degraded
```

每个 ordered fixture 至少断言：

- `semantic_kind` 列表。
- `entity_key_kind`，尤其是 `PSEUDO_BLANK`。
- `table_processing_mode`。
- `replay_guarantee`。
- ordered summary counts。
- risk reason code。
- records manifest/content digest 稳定。

规则：

- IEC104 fixture 默认使用 `gid` / `no` / ignored `no`。
- `gid=0`、NULL 或空值按 pseudo blank 处理。
- `no` 必须正整数、唯一、连续；不满足时 fixture 应断言 degraded。
- shared real rows 相对顺序不变的 position shift 不应断言为 move。
- shared real rows 相对顺序变化才进入 move/reorder 语义。

### `fixtures/external/`

- 存放本地原始业务输入的临时摆放位置。
- 这里的内容默认不进入 git。
- 可放：
  - 原始 `source.sql`
  - `.zip`
  - `.sql.gz`
  - `.tar.gz`
  - 其它调试用输入
- 这个目录只用于本机调试或裁剪回归样本的中转，不是正式测试资产。

## 业务数据与 benchmark 数据

- benchmark 的正式 dataset root 必须放在仓库外。
- 推荐结构仍然是：

```text
business-benchmark-data/
  business_small_cut/
    dbcfg.sql
    dataset.yaml optional
  business_small/
    dbcfg.sql
    dataset.yaml optional
  business_medium/
    dbcfg.sql
    dataset.yaml optional
  business_large/
    dbcfg.sql
    dataset.yaml optional
```

- `dataset.yaml` 只允许保存非敏感描述。
- 如果 benchmark 数据文件名不是 `dbcfg.sql`，则在 `dataset.yaml` 中显式写入 `source_sql_file`。
- 如果要标记少量关键表做更严格的校验，可以在 `dataset.yaml` 中写 `validation_tables`。
- 真实业务 SQL 不进入 git。
- repository import benchmark 的实际运行步骤和 Phase A/B/C 命令见 `repository-import-benchmark-runbook.md`。

## 运行方式

只跑 vNext 测试时，使用明确路径：

```bash
gateway-data-management-system/backend/.venv/bin/python -m pytest -q gateway-data-management-system/backend/tests/backend_vnext
```

不要用 `gateway-data-management-system/backend/tests` 作为 vNext 的验证入口，否则会把老项目测试一起带进来。
