# 设备目录系统接口约定（试运行版）

状态：**正式接口，owner 已确认**。原接口确认于 2026-11-11；处理组接入修订确认于 2026-11-12，与 [design §12](design.md#12-已确认的处理组接入修订owner2026-11-12) 配套。实现与验收仍按 [执行计划](execution-plan-directory-v1.md) 完成。

| 编号 | 接口 | 提供方 → 使用方 |
| --- | --- | --- |
| I1 | 目录导入文件 | 外部导入程序 → 目录命令行 |
| I2 | 唯一键规则 | 目录系统 |
| I3 | 目录服务 HTTP 接口 | 目录服务 → 目录前端 |
| I4 | 会话文件与续期 | 目录命令行 → 目标处理组 |
| I5 | 设备开通与登记回执 | 目录命令行 → 网关宿主管理工具/组内登记接口 |
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
```

| 站号 | 规范化后 | 设备键 | 项目号 |
| --- | --- | --- | --- |
| `SZ-0142` | `SZ-0142` | `dev-fbe8accb4da11574` | `prj-fbe8accb4da11574` |
| ` sz-0142 ` | `SZ-0142` | `dev-fbe8accb4da11574` | `prj-fbe8accb4da11574` |
| `WX-0207` | `WX-0207` | `dev-0a5e7c9870eaba0b` | `prj-0a5e7c9870eaba0b` |

- 键只取决于站号，与名称、地区、导入时间、机器都无关。
- 两个不同站号得到相同的 `h` 时，导入以 `KEY_COLLISION` 拒绝。
- 试运行阶段设备与项目一一对应，所以两个键共用同一个 `h`。
- 初始基线节点 ID 和建仓幂等键由网关登记流程生成，目录不推导它们；保存 I5 返回的固定 INITIAL 回执。

## I3 目录服务 HTTP 接口

没有认证（B2）。JSON 一律 UTF-8。错误响应体统一为 `{"code": "<错误码>", "message": "<中文说明>"}`。

### `GET /api/catalog`

返回完整目录。响应头带 `ETag: "<catalog_version>"`；请求带匹配的 `If-None-Match` 时返回 304。支持 gzip。导入或开通引起 `provisioned` 可见值变化时更新版本；开通不改变 `imported_at`。

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
| 409 | `SESSION_UPDATING` | 会话续期尚未收尾，暂不签发跳转，需运维完成同一次续期 |

### `GET /healthz`

返回 200 `{"status": "ok"}`。

其余路径返回目录前端的静态文件；`/api/` 下的未知路径返回 404 `NOT_FOUND`。

## I4 会话文件与续期

目标宿主路径只从 I7 指定的 groups 清单中所选组的 `session_directory` 派生：`<session_directory>/session.json`。容器固定读取 `/run/gateway/session/session.json`，挂载其父目录；原子替换无需重启。目录不写 seed 映射文件。

文件严格为 `{"sessions": [...]}`，每条只允许以下字段（`expires_at` 在网关协议中可选，目录生成时必填）：

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
    "read_project_history",
    "statistics_read_group"
  ],
  "expires_at": "2027-05-10T08:30:00Z"
}
```

`expires_at` 为签发时间加 `GDDS_DIRECTORY_SESSION_TTL_DAYS`，UTC RFC 3339。token 只存在受控 SQLite、私有 session 文件和跳转响应中，不进入 argv、日志、异常、截图或测试快照。新增传给 I5 的临时 session 文档仅包含本设备一条会话，文件权限 0600，位于网关公共配置目录之外，用毕删除；重跑凭据来自 SQLite。

**新增：**文件由 I5 的现有工具追加。其 schema 拒绝 `issuer`、`documented_permissions` 及其他未知字段，不保留旧设计的扩展字段；发现不合法的既有文件时拒绝操作，不静默删除字段。

**续期：**遵守 design §4.1、§6.2；以 SQLite 保存的 token、actor、scope、permissions、expiry 的完整记录识别本系统条目，其他合法条目的值及顺序保留。不能仅以 `test1` 或 `dir-` 前缀判定归属。持有现有 publication lock → group management lock，并在锁内重读；复用既有宿主 helper 的校验与锁协议，不另建互不协调的锁。严格检查 JSON 重复 key、字段域、到期时间、全部组 token 唯一性和每文件 1 MiB 上限。

先保存待生效凭据，再在同目录写临时文件，复制原文件权限/属主，文件 fsync 后 replace 并 fsync 父目录；确认新 token 的 scope 与旧 token 的 401，再提交 SQLite 的当前凭据。中断重跑使用同一待生效凭据，按 design §4.1 比较本设备完整条目；先完成已有续期并退出，不在恢复后立即再轮换。文件中本设备未知变更或归属冲突时停止，保留诊断，其他合法会话在锁内重读保留。续期不修改路由、不建仓、不调用 `add-device` 代替撤销、不重启服务。待收尾期间 handoff 返回 409 `SESSION_UPDATING`。

## I5 设备开通与登记回执

试运行目标为一个预先部署好的固定组。目录通过可替换的宿主适配器调用现有工具，不复制该工具的发布流程；以参数数组、非 shell 方式执行：

```
python3 <网关仓库>/vnext/scripts/manage-processing-groups.py add-device
  --groups-file <绝对路径> --directory-file <绝对路径>
  --entry-directory <绝对路径> --entry-project <项目名>
  --group <固定组 ID> --device <设备键> --project <项目号>
  --session-document <仅本设备的私有临时文件>
```

工具负责预留、组内登记/建仓、会话追加、入口发布及实际可用性确认。目录不直接请求 Repository Service 建仓，不计算建仓幂等键或 INITIAL ID，不停止已有服务。工具自己获取宿主锁，目录调用时不重复持锁。工具 exit 0 才表示其检查时 available；exit 3 为 busy，exit 2 为前置拒绝，exit 1 为未完成。目录保留原始退出码及脱敏诊断，不自动重放写操作。

工具成功 stdout 只有 `state/group_id/config_digest`，不能从中假设获得仓库信息。目录再使用清单所选组的内部 bearer 文件（不传 secret 值到 argv），请求其固定 loopback backend 端点：

```
GET /internal/v1/devices/registration?device=<设备键 URL 编码>
Authorization: Bearer <所选组内部 token>
```

200 响应：

```json
{
  "environment_id": "<环境>",
  "group_id": "<组>",
  "gateway_device_external_key": "dev-fbe8accb4da11574",
  "business_project_id": "prj-fbe8accb4da11574",
  "repository_id": "<网关登记的仓库 ID>",
  "initial_node_id": "<网关生成的固定 INITIAL ID>",
  "initial_commit_id": "<固定初始提交号>"
}
```

必须核对前四项与本次目标，保存后三项作为回执。随后用本次 session token 经公共入口请求 `GET /v1/device-context`，带 `X-Gateway-Device-Key=hex_lower(SHA256(UTF8(device_key)))`；核对环境、组、设备、项目和仓库一致，才在本地标为已开通。HTTP 请求不跟随重定向、不继承 ambient proxy，不向公共入口发送 internal bearer。

中断后同身份重跑：网关拥有建仓/登记的幂等性，目录拥有待生效 token 与本地回执。部分成功不回滚业务事实，不改组或推测 INITIAL，不把 `enabled=true` 当作成功证据。

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
| `GDDS_DIRECTORY_STATIC_DIR` | `directory/frontend/dist`（相对仓库定位） | 目录前端构建产物目录；显式配置时必须是绝对路径 |

只有命令行使用：

| 环境变量 | 说明 |
| --- | --- |
| `GDDS_DIRECTORY_GATEWAY_ROOT` | 已部署网关源码仓库的绝对路径，用于定位既有宿主管理工具/helper |
| `GDDS_DIRECTORY_GROUPS_FILE` | 网关 groups 清单的绝对路径 |
| `GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE` | 网关设备预留目录 JSON 的绝对路径；与 groups 文件位于同一受控父目录，与业务目录 SQLite 不同 |
| `GDDS_DIRECTORY_GROUP_ID` | 本轮试运行唯一固定目标组 ID；必须存在于清单，已开通设备不能改组 |
| `GDDS_DIRECTORY_ENTRY_DIRECTORY` | 已初始化公共入口配置目录的绝对路径 |
| `GDDS_DIRECTORY_ENTRY_PROJECT` | 已部署公共入口的 Compose 项目名 |
| `GDDS_DIRECTORY_LOG_DIR` | 开通日志目录，放在 worktree 之外 |

组端点、环境、session 路径和管理凭据路径只从已校验的 groups 清单派生，不接受额外 URL/路径覆盖。`serve` 不加载网关管理配置，运行时只读目录 SQLite；`import/status` 也不要求管理凭据，只有 `provision` 校验上述管理必填项。缺项或路径不合法按配置错误退出并报告变量名，不输出 secret 值。

## I8 命令行

| 命令 | 作用 | 退出码 |
| --- | --- | --- |
| `gdds-directory serve` | 启动单进程目录 HTTP/静态服务，只读目录 SQLite | 0 正常退出；1 运行失败；2 配置/用法错误 |
| `gdds-directory import <csv> [--dry-run]` | 校验并导入 I1 文件，输出摘要 | 0 成功；1 校验失败（错误输出到 stderr）；2 配置/用法错误；3 目录管理锁 busy |
| `gdds-directory provision --stations <文件> [--dry-run]` | 在固定目标组开通文件中列出的站号（每行一个） | 0 成功；1 未完成；2 配置/输入拒绝；3 目录或网关管理锁 busy |
| `gdds-directory provision --all [--dry-run]` | 开通全部未开通且未移除的项目，含未完成项 | 同上 |
| `gdds-directory provision --renew-sessions` | 为全部已开通设备重新签发会话（换新 token，延长有效期） | 同上 |
| `gdds-directory status` | 输出项目数、已移除数、已开通数、待开通/待续期数、30 天内到期的会话数；仅本地记录 | 0 |

- `provision --stations` 中，站号不存在或已移除时直接失败，不建任何仓库；`--renew-sessions` 针对全部曾开通设备，包含当前已移除项。
- `provision --dry-run` 只读预检并列出将要开通/恢复的设备和目标组，不调用有副作用的管理命令、不生成新 token、不写文件。
- `provision` 在 `GDDS_DIRECTORY_LOG_DIR` 下写日志：主机名、起止时间、目标环境/组、设备及已完成列表、管理工具原始 exit code、登记回执 ID、可用性探针结果；续期另记 session 文件写入前后 SHA256。日志不写 token、认证头、session 文档、完整 handoff URL 或秘密值。
- `provision` 失败时输出当前设备、本地待生效/已完成状态和可确认的失败步骤；无法确认的网关内部步骤明确写未知。按 design §6 同身份重跑，不声称存在跨 SQLite、授权文件与网关登记的原子事务。
