# dir-v1 实施交接与设计对齐记录

当前状态：**处理组接入修订已于 2026-11-12 经 owner 确认为正式设计，详细执行计划已编写；产品实现与阶段 1 验证尚未开始，阶段 2 未开始。**

记录时间：2026-11-12。下文保留基线核对、停止和草案阶段的历史记录；当前正式设计以文末确认及 design/interfaces 为准。本记录不是阶段退出或验收通过记录。

## 基线、分支与范围

- 本轮核对的 `main`：`eb6530b36ef645d920627208fdc3a004a0409d25`，包含 kickoff 要求的 `18d290f20b`。
- 初始主工作区 `/home/dev/gateway-data-management-system` 位于 `fe3b-evidence-04`（`a300b16485`），有既有未提交修改与未跟踪文件；未修改、暂存或清理这些内容。
- `dir-v1` 和独立 worktree `/home/dev/gdds-dir-v1` 已存在，初始 HEAD 为 `996a3389f3fe905c3e7ecb5496a87bd59ae19023`，工作区干净，相对 `main` 没有独有提交。本轮执行 `git merge --ff-only main`，将其快进到上述基线。
- 已阅读 `AGENTS.md`、`design.md`、`interfaces.md` 和 `kickoff-directory-v1.md`，并只读核对 kickoff 指定的网关接点。
- 产品实现提交：无。唯一新增交付是本阻塞报告，提交主题为 `docs(device-directory): report provisioning baseline blockers`。
- 未改动 `frontend/`、`vnext/`，未新增依赖，未推送、合入 `main` 或打退出 tag。

## 阻塞：开通流程缺少当前网关必需的处理组预留

原设计（见 `deb88a1123`）将 CLI 与网关的接点限制为建仓、设备映射文件、会话文件；原 design §6 和 kickoff §4 要求严格执行建仓后停止 backend/worker、写两个文件、重新启动的流程。

但基线源码已经要求处理组与设备预留：

- `vnext/deploy/compose.yaml:28`、`:87` 为 backend 和 worker 分别传入 `groups.json` 与 `device-directory.json`。
- `vnext/backend/src/gateway_backend/bootstrap/composition.py:308` 和 `bootstrap/operation_worker.py:189` 在启动时加载预留目录，并将其传给 `seed_provisioned_mappings`。
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py:62` 对每条 seed 强制调用 `directory.require_reservation(device, group)`。
- `vnext/backend/src/gateway_backend/processing_group_config.py:117` 在找不到本组预留时抛出 `ValueError("device has no reservation in this group")`。
- `vnext/deploy/README.md:388` 已描述当前 `manage-processing-groups.py add-device` 的预留、登记、授权、scope 就绪与入口发布流程。

因此，对尚无预留的新设备，仅按 I4 写映射与会话文件不足以完成启动登记。这是源码核对结论，未在节点启动 Compose 重现；不将其表述为端到端实测结果。

需要先明确目录开通如何接入当前处理组与预留机制，包括目标组的选择、预留的提供方以及公共入口发布职责。现有 I7/I8 没有这些接点，实施者不能自行增加写入网关文件或管理命令的边界，也不能绕过预留检查。

## 差异：会话文件的挂载与宿主路径约定已改变

原设计（`deb88a1123` 中的 `design.md` §6 与 `interfaces.md` I4）声明两个文件均以单文件挂载，I7 又以 `GATEWAY_BACKEND_SESSION_FILE` 指代宿主机路径。

当前 `vnext/deploy/compose.yaml:27` 将容器内会话路径固定为 `/run/gateway/session/session.json`，`:39` 挂载的是宿主 `GATEWAY_BACKEND_SESSION_DIRECTORY` 父目录。`vnext/deploy/README.md:394` 明确每组独立的 session 目录，并说明会话不再使用单文件挂载。

会话仍可由 CLI 在宿主机原子替换，但设计关于挂载的理由、配置路径对应关系及首次端到端验证前提需要同步修订。未自行改动已确认的设计或接口。

## 节点、测试、缓存与截图

- 已按要求通过 `ssh -o BatchMode=yes <别名> 'echo OK'` 只读核对连接：06 为 `ct107-gw-dms-06` / hostname `gw-dms-06`；07 为 `ct109-gw-dms-07` / hostname `gw-dms-07`。
- 现场检查时未发现两节点占用目录，监听端口仅见 SSH；此为当时的只读快照，不构成后续运行授权或空闲保证。未获取占用标记，未在节点执行有写入的操作。
- 因触发停止条件，未创建 `directory/` 产品实现，未运行 ruff、mypy、pytest、前端检查、构建、mock e2e 或截图。没有测试 HEAD、测试 exit code、测试日志或其 SHA256；不得据此宣称通过。
- 未生成锁文件、取得依赖或进行缓存预填充；没有本任务的来源提交、缓存摘要与预填充时间。07 上镜像和 npm 缓存的存在性已只读查看，未核验身份与本任务依赖闭包，不能视为缓存就绪。
- 截图清单为空，未完成草图对照。

## 后续前提

按用户指令及 kickoff §7，发现实际网关行为与设计不符时停止报告；本轮止于此处。需要先确认并修订开通设计与接口，再恢复阶段 1 的实现和专用节点验证。

核对时 `fe-handoff` 已是 `main` 的祖先，但本任务尚未实现或通过审核，仍不满足阶段 2 的全部前置条件。阶段 1 完成后应更新本 handoff，提供实际提交、日志、缓存与十张截图的证据，并等待审核；不以本报告代替这些交付。

## 后续设计对齐草案（2026-11-12）

用户要求在本会话提出原设计的修改建议。本轮已将 `design.md`、`interfaces.md` 与 `kickoff-directory-v1.md` 对齐为一份待确认的修订草案：固定一个预部署处理组；新增复用现有 `add-device`；登记回执及 INITIAL 由网关提供；会话去掉管理工具不接受的 `issuer`，续期在现有宿主锁下仅替换 SQLite 精确归属的授权；前端代理指向公共入口。新增最小待生效凭据供本地中断收尾，未完成续期暂停 handoff。

这是对上文阻塞的建议解决方案，尚非 owner 已确认的替代 Contract，也不表示已运行验证。只做源码与文档一致性核对及 `git diff --check`，未运行测试、改产品代码、增加依赖或进入阶段 2。草案提交主题为 `docs(device-directory): propose processing-group aligned provisioning`。

## 正式设计与执行计划（2026-11-12）

owner 已确认上述处理组接入建议可以作为正式设计。本轮将 design/interfaces/kickoff 更新为正式状态，并补充 [详细执行计划](execution-plan-directory-v1.md)。原开通与挂载差异的设计决定已经解决，后续按已确认的新接点实施，不恢复旧路径。

设计补齐了本地事务、当前/待生效完整凭据、同一次续期的恢复边界、管理锁与第三方会话保留规则。执行计划给出顺序工作内容、风险与测试 owner、06/07 离线组件取证、十张截图清单、阶段 1 handoff 以及 05 阶段 2 的前提与最小真实旅程。具体职责、模型和审核按仓库标准执行。

本轮仅提交本目录文档，做差异、链接及源码接点核对；无产品代码、依赖或网关文件修改，无测试/截图/缓存预填充或真实网关操作，不宣称任何阶段通过，未推送。

## 首次实践验收核对分工（2026-11-12）

owner 已确认新增通用代码独审/验收核对原则，并指定本任务首次实践。通用规则以独立提交 `f229697ad1` 写入本地 main（AGENTS、testing-conventions、流程规格），由目录分支合并同步；未改动其他工作区的未提交文件。目录执行计划 §3.6 与 kickoff 同步了 Astra 代码独审、Luna 清单/原件/截图核对、本系统 runner 确定性检查的边界。

原实施提示词的产品范围和阶段 1 目标继续有效；启动时须使用更新后的分支 HEAD，补充首次实践职责，不能继续把旧 `2bd4e2a806` 当作当前 HEAD。产品、门禁代码及新增核对角色尚未运行，通用规则和本次文档提交不等于实践验收已通过。
