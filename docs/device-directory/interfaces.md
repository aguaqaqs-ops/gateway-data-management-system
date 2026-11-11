# 设备目录系统接口约定（试运行版）

状态：owner 已确认，2026-11-11。设计背景见 [design.md](design.md)。

| 编号 | 接口 | 提供方 → 使用方 |
| --- | --- | --- |
| I1 | 目录导入文件 | 外部导入程序 → 目录命令行 |
| I2 | 唯一键规则 | 目录系统 |
| I3 | 目录服务 HTTP 接口 | 目录服务 → 目录前端 |
| I4 | 写入网关系统的文件 | 目录命令行 → 网关 backend/worker |
| I5 | 仓库服务建仓 | 网关 repository-service → 目录命令行 |
| I6 | 跳转片段 | 目录服务 → 网关前端 |
| I7 | 配置 | 部署 → 目录服务、命令行 |
| I8 | 命令行 | 运维 → 目录系统 |

## I1 目录导入文件

UTF-8 编码（允许 BOM），RFC 4180 CSV，换行可以是 LF 或 CRLF。第一行是表头，必须恰好为：

```
region1,region2,project_name,station_code,pinyin_initials,pinyin_full
```

| 列 | 必填 | 规则 |
| --- | --- | --- |
| `region1` | 是 | 地区一名称；去掉首尾空白后 1–50 个字符；不含控制字符和 `/` |
| `region2` | 是 | 地区二名称；规则同上 |
| `project_name` | 是 | 项目名；去掉首尾空白后 1–100 个字符；不含控制字符；允许重名 |
| `station_code` | 是 | 站号；按 I2 规范化后 1–64 个字符，不含空白和控制字符；全文件唯一（按规范化后的值比较） |
| `pinyin_initials` | 是 | 拼音首字母。有多种读法时用 `\|` 分隔；每种读法匹配 `^[a-z0-9]+$`，导入时转为小写 |
| `pinyin_full` | 否 | 全拼。多种读法用 `\|` 分隔；每种读法由单个空格分隔的音节组成，每个音节匹配 `^[a-z0-9]+$`。排序用第一种读法 |

示例：

```csv
region1,region2,project_name,station_code,pinyin_initials,pinyin_full
江苏,苏州,城南 110kV 变电站,SZ-0142,cn110kvbdz,cheng nan 110kv bian dian zhan
江苏,苏州,城南 110kV 变电站,SZ-0388,cn110kvbdz,cheng nan 110kv bian dian zhan
浙江,宁波,长宁 220kV 变电站,NB-0018,cn220kvbdz|zn220kvbdz,chang ning 220kv bian dian zhan|zhang ning 220kv bian dian zhan
```

- 文件是完整名单，整份替换上一份（design §5）。任一行出错，整份拒绝。
- 每条错误报告为 `第 <行号> 行 <列名>：<错误码>`。错误码包括 `HEADER_MISMATCH`、`FIELD_EMPTY`、`FIELD_TOO_LONG`、`FIELD_INVALID_CHAR`、`PINYIN_INVALID`、`STATION_DUPLICATE`、`KEY_COLLISION`。
- 至少要有一行数据。

## I2 唯一键规则

```
normalized = NFKC(station_code) 去掉首尾空白后转为大写
h          = SHA-256( "gdds-directory/station/v1" + 0x00 + UTF-8(normalized) ) 十六进制小写的前 16 位
gateway_device_external_key = "dev-" + h
business_project_id         = "prj-" + h
business_baseline_node_id   = "dir-initial-" + h      （I4 映射文件使用）
```

| 站号 | 规范化后 | 设备键 | 项目号 |
| --- | --- | --- | --- |
| `SZ-0142` | `SZ-0142` | `dev-fbe8accb4da11574` | `prj-fbe8accb4da11574` |
| ` sz-0142 ` | `SZ-0142` | `dev-fbe8accb4da11574` | `prj-fbe8accb4da11574` |
| `WX-0207` | `WX-0207` | `dev-0a5e7c9870eaba0b` | `prj-0a5e7c9870eaba0b` |

- 键只取决于站号，与名称、地区、导入时间、机器都无关。
- 两个不同站号得到相同的 `h` 时，导入以 `KEY_COLLISION` 拒绝。
- 试运行阶段设备与项目一一对应，所以两个键共用同一个 `h`。

## I3 目录服务 HTTP 接口

没有认证（B2）。JSON 一律 UTF-8。错误响应体统一为 `{"code": "<错误码>", "message": "<中文说明>"}`。

### `GET /api/catalog`

返回完整目录。响应头带 `ETag: "<catalog_version>"`；请求带匹配的 `If-None-Match` 时返回 304。支持 gzip。

```json
{
  "catalog_version": "c-20261110T083000Z-3f9a1c0e",
  "imported_at": "2026-11-10T08:30:00Z",
  "projects": [
    {
      "device_key": "dev-fbe8accb4da11574",
      "station_code": "SZ-0142",
      "name": "城南 110kV 变电站",
      "region1": "江苏",
      "region2": "苏州",
      "pinyin_initials": ["cn110kvbdz"],
      "pinyin_full": ["cheng nan 110kv bian dian zhan"],
      "provisioned": true
    }
  ]
}
```

- 不含已移除的项目；`pinyin_full` 未提供时为 `[]`。
- `projects` 按默认顺序返回（design §8：先按全拼，没有全拼时按项目名；名称相同再按站号）。
- 地区树、各地区项目数和同名标记都由前端从 `projects` 计算。
- 还没有导入过任何名单时，返回 503 `CATALOG_EMPTY`。

### `POST /api/handoffs`

请求：

```json
{ "device_key": "dev-fbe8accb4da11574", "return_query": "?r1=江苏&r2=苏州&page=1" }
```

`return_query` 可选，是目录页面当前的查询串，必须以 `?` 开头，长度不超过 1000。

成功返回 200，响应头带 `Cache-Control: no-store`：

```json
{ "gateway_url": "http://<主机>:4173/#gdds-handoff=eyJ2IjoxLC..." }
```

| 状态 | 错误码 | 含义 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 请求体不合法 |
| 404 | `DEVICE_NOT_FOUND` | 设备不存在或已移除 |
| 409 | `DEVICE_NOT_PROVISIONED` | 设备未开通 |
| 409 | `SESSION_EXPIRED` | 会话已过期，需要运维执行 `--renew-sessions` |

### `GET /healthz`

返回 200 `{"status": "ok"}`。

其余路径返回目录前端的静态文件；`/api/` 下的未知路径返回 404 `NOT_FOUND`。

## I4 写入网关系统的文件

这两个文件只由 I8 `provision` 写入，并且只在 backend 与 worker 都已停止时写（design §6）。

### 设备映射文件（`GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE` 的宿主机路径）

为每个已开通的设备写入一条：

```json
{
  "gateway_device_external_key": "dev-fbe8accb4da11574",
  "business_project_id": "prj-fbe8accb4da11574",
  "repository_id": "<I5 返回的 repository_id>",
  "business_baseline_node_id": "dir-initial-fbe8accb4da11574",
  "business_baseline_commit_id": "<I5 返回的 initial_commit_id>",
  "baseline_head_version": 0,
  "enabled": true,
  "issuer": "device-directory"
}
```

`baseline_head_version` 固定为 0。网关只在第一次登记时用它建立初始基线，之后重启不会回退已经前进的基线（`vnext/deploy/README.md`）。

### 会话文件（`GATEWAY_BACKEND_SESSION_FILE` 的宿主机路径）

为每个已开通的设备写入一条：

```json
{
  "token": "dir-<32 字节随机数的 base64url，无填充>",
  "actor_id": "test1",
  "gateway_device_external_key": "dev-fbe8accb4da11574",
  "business_project_id": "prj-fbe8accb4da11574",
  "permissions": [
    "workspace_read",
    "upload_submit_workspace",
    "preview_workspace",
    "review_submission",
    "withdraw_own_submission",
    "archive_submission",
    "read_project_history"
  ],
  "expires_at": "2027-05-10T08:30:00Z",
  "issuer": "device-directory"
}
```

`expires_at` 等于签发时间加上 `GDDS_DIRECTORY_SESSION_TTL_DAYS`，UTC，RFC 3339 格式。

### 写入规则（两个文件相同）

- `"issuer": "device-directory"` 的条目归目录管理，每次都按开通记录整体重新生成。其他条目和顶层其他字段（如 `documented_permissions`）原样保留，顺序不变。网关加载这两个文件时只读取自己需要的字段，会忽略 `issuer`。
- 写入前按网关的规则自检：列表非空、token 不重复、一个仓库只对应一个设备/项目组合、必填字段非空。自检不通过就不写。
- 在同一目录下写临时文件，复制原文件的权限和属主，fsync 后改名替换原文件。
- 两个文件都以单文件方式挂载进容器，容器启动时才挂载新文件，所以写完后必须重新启动 backend 与 worker。第一次在 05 节点做端到端时，要实测确认启动后容器内读到的是新内容。

## I5 仓库服务建仓

目录命令行通过 Compose 在 repository-service 容器内发请求（与 `vnext/backend/tests/support/compose_gate_harness.py` 的 `seed_repository_and_mapping` 相同），不需要在宿主机上持有仓库服务的 token：

```
docker compose -p <项目名> --env-file <env 文件> exec -T repository-service python -c <脚本>
```

脚本读取容器内的 `/run/secrets/repository-bearer-token`，然后发送：

```
POST http://127.0.0.1:8000/v1/repositories
Authorization: Bearer <token>
Idempotency-Key: directory-provision-<h>
```

期望返回 201：`{"repository_id": "<UUID>", "default_ref": "...", "initial_commit_id": "..."}`。其他状态视为失败，命令行停止并报告已完成的设备。幂等键长度不超过 255，满足仓库服务的约束。

## I6 跳转片段

```
<GDDS_DIRECTORY_GATEWAY_FRONTEND_URL>#gdds-handoff=<base64url(UTF-8 JSON)，无填充>
```

```json
{
  "v": 1,
  "token": "dir-...",
  "gateway_device_external_key": "dev-fbe8accb4da11574",
  "business_project_id": "prj-fbe8accb4da11574",
  "display": {
    "region1": "江苏",
    "region2": "苏州",
    "project_name": "城南 110kV 变电站",
    "station_code": "SZ-0142"
  },
  "return_url": "http://<主机>:8100/?r1=江苏&r2=苏州&page=1"
}
```

网关前端的处理（design §7.3）：

1. 读取 `gdds-handoff` 并解码。`v` 不是 1、字段缺失或解码失败时，显示“跳转信息无效，请从设备目录重新进入”。
2. 设置 `window.__gatewaySession = { businessProjectId, gatewayDeviceExternalKey, accessToken }`，并在当前标签页保存 `display` 与 `return_url`。
3. 用 `history.replaceState` 去掉地址片段。
4. 把以上内容存入 `sessionStorage` 的 `gdds-gateway-session` 键，刷新后据此恢复（design Q1）。
5. 网关后端返回 401 时，显示“会话无效或已过期，请从设备目录重新进入”，并提供 `return_url` 链接。

`return_url` 由目录服务用 `GDDS_DIRECTORY_PUBLIC_URL` 加上请求中的 `return_query` 拼成，不使用请求方传来的完整地址。

## I7 配置

目录服务与命令行共用：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GDDS_DIRECTORY_DB` | 无，必填 | 目录 SQLite 文件的绝对路径 |
| `GDDS_DIRECTORY_LISTEN` | `0.0.0.0:8100` | 目录服务监听地址 |
| `GDDS_DIRECTORY_PUBLIC_URL` | 无，必填 | 浏览器访问目录的地址，用于拼 `return_url` |
| `GDDS_DIRECTORY_GATEWAY_FRONTEND_URL` | 无，必填 | 浏览器访问网关前端的地址 |
| `GDDS_DIRECTORY_SESSION_TTL_DAYS` | `180` | 会话有效期（天） |

只有命令行使用：

| 环境变量 | 说明 |
| --- | --- |
| `GDDS_DIRECTORY_COMPOSE_FILE` | 网关的 `vnext/deploy/compose.yaml` 路径 |
| `GDDS_DIRECTORY_COMPOSE_PROJECT` | Compose 项目名 |
| `GDDS_DIRECTORY_COMPOSE_ENV_FILE` | 网关 Compose 使用的 env 文件 |
| `GDDS_DIRECTORY_MAPPING_FILE` | 设备映射文件的宿主机路径（与 `GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE` 相同） |
| `GDDS_DIRECTORY_SESSION_FILE` | 会话文件的宿主机路径（与 `GATEWAY_BACKEND_SESSION_FILE` 相同） |
| `GDDS_DIRECTORY_LOG_DIR` | 开通日志目录，放在 worktree 之外 |

## I8 命令行

| 命令 | 作用 | 退出码 |
| --- | --- | --- |
| `gdds-directory import <csv> [--dry-run]` | 校验并导入 I1 文件，输出摘要 | 0 成功；1 校验失败（错误输出到 stderr）；2 用法错误 |
| `gdds-directory provision --stations <文件> [--dry-run]` | 开通文件中列出的站号（每行一个） | 0 成功；1 失败；2 用法错误 |
| `gdds-directory provision --all [--dry-run]` | 开通全部未开通且未移除的项目 | 同上 |
| `gdds-directory provision --renew-sessions` | 为全部已开通设备重新签发会话（换新 token，延长有效期） | 同上 |
| `gdds-directory status` | 输出项目数、已移除数、已开通数、30 天内到期的会话数 | 0 |

- `provision` 中，站号不存在或已移除时直接失败，不建任何仓库。
- `provision --dry-run` 只列出将要新建仓库的设备，不建仓库、不写文件、不重启服务。
- `provision` 在 `GDDS_DIRECTORY_LOG_DIR` 下写日志：主机名、起止时间、设备列表、新建仓库 ID、写入前后两个文件的 SHA256、服务重启结果。日志不写入 token。
- `provision` 失败时，输出停在哪一步：仓库已建到第几个、文件是否已写、服务是否已重新启动；按 design §6 可以直接重跑。
