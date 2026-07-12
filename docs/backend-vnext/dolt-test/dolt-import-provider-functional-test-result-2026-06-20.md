# Dolt 导入 Provider 功能测试报告

## 环境

- OS: Debian GNU/Linux 13 (trixie) on Linux 6.6.114.1-microsoft-standard-WSL2 x86_64
- dolt_path: `/usr/local/bin/dolt`
- dolt_version: `dolt version 2.1.8`
- mysql_client: `/usr/bin/mysql Ver 8.4.9 for Linux on x86_64 (MySQL Community Server - GPL)`
- python: `Python 3.12.12`
- run_root: `/tmp/dolt-import-provider-functional-test-bz9hcajo`
- cleanup: 未清理，保留临时 artifacts 便于排查
- 备注: 已将 `/tmp/dolt-import-provider-functional-test-bz9hcajo/summary.json` 同步修正，当前临时结果与本报告一致

## 预检

- T00 通过: `dolt version`、`dolt --help`、`dolt sql --help`、`dolt table import --help`、`dolt sql-server --help` 都确认了所需 CLI 能力。
- T01 通过: 临时仓库初始化、`status`、`add`、`commit`、`log --oneline` 都可用。

## 摘要

| Provider | 状态 | Commit | Readback | 备注 |
| --- | --- | --- | --- | --- |
| SQL_DUMP_REPLAY | SUPPORTED | `qetqa3aif5jbf2krp9ca27ijgig0o98o` | PASSED | 原始 SQL 回放可稳定导入并提交。 |
| SINGLE_TABLE_CLI_IMPORT | SUPPORTED | `91lljof31n0jcf497saiuslp96qvave9` / `49qtjkg3nj0muora2m51n9a00gfdb566` | PASSED | CSV/TSV 单表导入都成功，且需要显式 schema。 |
| MULTI_TABLE_CLI_IMPORT | SUPPORTED | `kgfr60c56ai8jsq2p8lkkendiitaal4b` | PASSED | 两张表连续导入后一次性提交，结果一致。 |
| LOAD_DATA | SUPPORTED | `i5dqtd7f2md93cebj5tvn2ba0ccuvr3t` | PASSED | 通过 `sql-server` 路由后，`LOAD DATA` 可稳定工作。 |
| PARQUET_IMPORT | SUPPORTED | `u7rehv5s8kdknt8hb4pn7v5csnn322mh` | PASSED | Parquet 导入可用，读回一致。 |
| DOLT_SERVER_BULK_LOAD | SUPPORTED | `gp84h6hqms5jt26qn2s2tr8hcjequgvh` | PASSED | `sql-server + mysql client` 的 bulk load 可用。 |
| SERVER_SESSION_BULK_LOAD | SUPPORTED | `8ctci4lqodhbmufu5gcpcvra745ois3h` | PASSED | 单个 `sql-server` 进程可承接两轮连续导入。 |

## 详细结果

### SQL_DUMP_REPLAY

- 命令:
  - `dolt sql < source.sql`
  - `dolt add .`
  - `dolt commit -m "sql dump replay import"`
  - `dolt sql -r json -q "select * from version_manager order by NO;"`
  - `dolt sql -r json -q "select * from device_cfg order by id;"`
- commit_hash: `qetqa3aif5jbf2krp9ca27ijgig0o98o`
- 读回:
  - `version_manager`: 2 行，主键 `NO`，digest 匹配
  - `device_cfg`: 3 行，主键 `id`，digest 匹配
- 备注: 原始 SQL 回放保留了显式 schema、主键、`NULL`，以及 `gamma,with,comma` 这样的逗号字符串。

### SINGLE_TABLE_CLI_IMPORT

- 命令:
  - `dolt table import -c --schema version_manager_schema.sql version_manager version_manager.csv`
  - `dolt table import -c --schema device_cfg_schema.sql --file-type csv --delim "\t" device_cfg device_cfg.tsv`
- 子测试:
  - `version_manager.csv`
    - commit_hash: `91lljof31n0jcf497saiuslp96qvave9`
    - 格式: CSV
    - 行数: 2
    - 主键: `NO`
    - digest 匹配: `true`
  - `device_cfg.tsv`
    - commit_hash: `49qtjkg3nj0muora2m51n9a00gfdb566`
    - 格式: TSV
    - 行数: 3
    - 主键: `id`
    - digest 匹配: `true`
- 备注: 显式 schema 是 benchmark-safe 路径；另外做过一次不带 schema 的 CSV create-import 探针，会生成 keyless table，因此不适合作为 provider contract。

### MULTI_TABLE_CLI_IMPORT

- 命令:
  - `dolt table import -c --schema version_manager_schema.sql version_manager version_manager.csv`
  - `dolt table import -c --schema device_cfg_schema.sql device_cfg device_cfg.csv`
  - `dolt add .`
  - `dolt commit -m "multi-table cli import"`
- commit_hash: `kgfr60c56ai8jsq2p8lkkendiitaal4b`
- 读回:
  - `version_manager`: 2 行，主键 `NO`，digest 匹配
  - `device_cfg`: 3 行，主键 `id`，digest 匹配
- 备注: 两张表在同一个提交前连续导入，读回与源数据完全一致。

### LOAD_DATA

- 命令:
  - `dolt sql-server --host 127.0.0.1 --port <random> --socket <path>`
  - `dolt sql < load.sql  # 由 sql-server 接管`
  - `dolt add .`
  - `dolt commit -m "load data import"`
- commit_hash: `i5dqtd7f2md93cebj5tvn2ba0ccuvr3t`
- 读回:
  - `version_manager`: 2 行，主键 `NO`，digest 匹配
  - `device_cfg`: 3 行，主键 `id`，digest 匹配
- 备注:
  - 修正后明确使用 LF 行尾，并用 `\\N` 表示 `NULL`
  - `LOAD DATA` 走 `sql-server` 路由后可稳定导入
  - 纯离线 `dolt sql` 并不是这条路径的正确执行方式

### PARQUET_IMPORT

- 命令:
  - `dolt table import -c --schema version_manager_schema.sql version_manager version_manager.parquet`
  - `dolt table import -c --schema device_cfg_schema.sql device_cfg device_cfg.parquet`
  - `dolt add .`
  - `dolt commit -m "parquet import"`
- commit_hash: `u7rehv5s8kdknt8hb4pn7v5csnn322mh`
- 读回:
  - `version_manager`: 2 行，主键 `NO`，digest 匹配
  - `device_cfg`: 3 行，主键 `id`，digest 匹配
- 备注: `backend/.venv` 中的 `polars` 足以生成 Parquet，显式 schema 也能保住主键和字段值。

### DOLT_SERVER_BULK_LOAD

- 命令:
  - `dolt sql-server --host 127.0.0.1 --port <random> --socket <path>`
  - `mysql --protocol=TCP -h 127.0.0.1 -P <port> -u root -e "USE \`t60-server-bulk-load\`; ... LOAD DATA INFILE ..."`
  - `dolt add .`
  - `dolt commit -m "server bulk load import"`
- commit_hash: `gp84h6hqms5jt26qn2s2tr8hcjequgvh`
- 读回:
  - `version_manager`: 2 行，主键 `NO`，digest 匹配
  - `device_cfg`: 3 行，主键 `id`，digest 匹配
- 备注: `sql-server` 生命周期稳定，标准 MySQL 客户端可正确执行非 `LOCAL` 的 `LOAD DATA INFILE`。仓库目录名包含连字符时，数据库名需要按实际名称引用。

### SERVER_SESSION_BULK_LOAD

- 命令:
  - `dolt sql-server --host 127.0.0.1 --port <random> --socket <path>`
  - `mysql --protocol=TCP -h 127.0.0.1 -P <port> -u root -e "... round 1 ..."`
  - `mysql --protocol=TCP -h 127.0.0.1 -P <port> -u root -e "... round 2 ..."`
  - `dolt add .`
  - `dolt commit -m "warm session import"`
- commit_hash: `8ctci4lqodhbmufu5gcpcvra745ois3h`
- 读回:
  - 最终表 `t`: 2 行，主键 `id`
  - 最终数据: `(1, x)`、`(2, y)`
- 备注: 同一个 `sql-server` 进程可连续承接两轮导入，第二轮能干净覆盖第一轮数据。

## 建议

- 第一批 benchmark 候选:
  - `SQL_DUMP_REPLAY`
  - `SINGLE_TABLE_CLI_IMPORT`
  - `MULTI_TABLE_CLI_IMPORT`
  - `LOAD_DATA`
  - `PARQUET_IMPORT`
- 暂缓:
  - `DOLT_SERVER_BULK_LOAD`
  - `SERVER_SESSION_BULK_LOAD`
- 阻塞项:
  - 无
- 补充说明:
  - `LOAD DATA` 建议固定走 `sql-server` 路由，不建议把离线 `dolt sql` 当作正确 contract
  - schema-backed import 是安全 contract，不带 schema 的 CSV create-import 不适合进入 benchmark
