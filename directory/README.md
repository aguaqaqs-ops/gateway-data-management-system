# 设备目录 v1

目录由独立的 Python 标准库服务、宿主 CLI 和静态前端组成。正式契约见 [接口](../docs/device-directory/interfaces.md)与[设计](../docs/device-directory/design.md)。本阶段不替代网关的处理组部署与公共入口管理。

## 配置和启动

设置 `GDDS_DIRECTORY_DB` 为受控私有目录中的 SQLite 绝对路径；其父目录须由当前用户拥有且不允许其他用户访问。数据库、sidecar 和私有临时文件不能位于静态目录或网关公共配置目录。schema 不匹配时拒绝使用。目录首次导入时创建；新项目不提供旧 schema 迁移。

设置 `GDDS_DIRECTORY_PUBLIC_URL` 为浏览器访问目录的 HTTP(S) 地址，`GDDS_DIRECTORY_GATEWAY_FRONTEND_URL` 为浏览器访问网关前端的 HTTP(S) 地址。`GDDS_DIRECTORY_LISTEN` 默认 `0.0.0.0:8100`；`GDDS_DIRECTORY_STATIC_DIR` 可指定构建产物的绝对路径，默认 `directory/frontend/dist`。确保 PATH 中的 `python3` 是 Python 3.14.6，并在前端构建产物就绪后启动：

```sh
export PATH="$PWD/directory/bin:$PATH"
gdds-directory serve
```

不使用 launcher 时，`PYTHONPATH="$PWD/directory/service" python3 -m gdds_directory serve` 等价。服务只读本地 SQLite，不加载网关管理凭据；尚无导入名单时 catalog 返回 `CATALOG_EMPTY`。

静态目录必须是本项目 Vite 构建的完整输出，包含 `index.html`、`.vite/manifest.json` 及清单引用的文件；旧构建需重新生成。启动时校验清单，仅公开 HTML 和清单列出的 chunk、CSS、资产，不公开清单本身或混入的源码、配置、备份。新资产应通过 Vite import 纳入构建清单，不手工复制到 dist；替换构建后重启目录服务加载新清单。

HTTP 最多同时处理 32 个连接，超额连接直接关闭；读写空闲超时 5 秒，每连接总期限 30 秒（包括慢速逐字节请求与响应发送）。关闭服务会中断活动连接并等待处理线程与期限计时器退出。慢速客户端可能需要重试。

跳转时仅还原查询串的非 ASCII UTF-8 编码，保留查询分隔符与转义语义，使长地区名、搜索、范围和页码能在 I3 的 1000 字符以内完整返回。还原后仍超限则保留当前页面状态、提示缩短搜索内容，不截断返回位置或发送不合约请求。

## 导入和状态

CSV 必须符合 I1 的表头、编码、站号与拼音规则，且是完整名单；任一行出错整份拒绝。

```sh
gdds-directory import /absolute/path/catalog.csv --dry-run
gdds-directory import /absolute/path/catalog.csv
gdds-directory status
```

移除和恢复由下一份完整名单表达；站号决定稳定设备键与项目号。恢复已移除站号沿用原开通记录。

## 开通和续期

先按网关既有流程部署并配置固定环境、处理组及公共入口。设置 `GDDS_DIRECTORY_GATEWAY_ROOT`、`GDDS_DIRECTORY_GROUPS_FILE`、`GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE`、`GDDS_DIRECTORY_GROUP_ID`、`GDDS_DIRECTORY_ENTRY_DIRECTORY`、`GDDS_DIRECTORY_ENTRY_PROJECT`、`GDDS_DIRECTORY_LOG_DIR`；路径使用绝对路径，日志目录在工作树之外。`GDDS_DIRECTORY_SESSION_TTL_DAYS` 默认 180。组端点、会话路径及管理凭据路径由清单确定。

```sh
gdds-directory provision --stations /absolute/path/stations.txt --dry-run
gdds-directory provision --stations /absolute/path/stations.txt
gdds-directory provision --all --dry-run
gdds-directory provision --all
gdds-directory provision --renew-sessions
```

站号文件每行一个站号。新增设备复用网关 `add-device`，目录不直接建仓、不写 seed 映射或自行重启网关。退出码 0 表示成功，1 表示未完成，2 表示配置或输入拒绝，3 表示管理锁忙。busy 时稍后重试；未完成时保留数据库和网关现状，用相同目标及原命令重跑，完成已保存的待生效凭据；不要清空目录、更换设备键或绕过冲突。待续期未完成时 handoff 暂停。凭据不得放入日志、命令参数或截图。

## 检查

唯一组件入口为 `directory/scripts/run-tests.sh`：06 上以 `UV_OFFLINE=1` 运行 `--service`；07 上以 `GATEWAY_FE_TEST_WORKERS=2` 运行 `--frontend --screenshots <工作树外绝对目录>`。两者要求 clean 已提交 worktree、`GDDS_DIRECTORY_TEST_HEAD`、节点专用缓存及来源 manifest；运行前按执行计划核验节点、占用与工具链，日志和截图存工作树外。具体前置与证据要求见 [执行计划](../docs/device-directory/execution-plan-directory-v1.md)。

真实阶段 2 使用独立的 `directory/scripts/run-real-journey.sh`，配置、固定输入、凭据与证据规则见 [窄旅程说明](journey/README.md)。它不替代组件入口或网关门禁，必须在 05 的 clean 候选和本人独立单组环境运行。
