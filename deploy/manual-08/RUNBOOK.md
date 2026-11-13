# 08 人工联调环境运维手册

本目录用于 CT110 的一次性人工联调部署，不是产品数据恢复功能。部署完成并验收前，本文的地址和操作均不代表服务已可用。系统有两套独立业务组、入口、数据根、目录数据库、会话和内部凭据；只读前端构建和同版本镜像可以复用。

## 访问和操作

- 单设备 A：`https://192.168.233.209:8443/manual/`。该页提供进入提交树和仅重置 A 的按钮。
- 多设备 B：`https://192.168.233.209:9443/`。选择设备后交接到 `https://192.168.233.209:10443/` 的网关。
- 凭据仅在 08 的 `/home/dev/gdds-gw-dms-08-v2/credentials/access.txt`（`dev` 所有、0600）；不要复制到日志、截图或公开文档。两套系统的入口账号和密码不同。两个证书是各自的自签证书，需要在浏览器信任；证书公钥指纹由运维从各自 `tls/cert.pem` 核对。
- 每台设备使用现有 `test1` 测试身份，拥有提交、审核和归档所需权限；在页面中操作相应动作即可，无需 DevTools。提交和审核不是不同 actor，多人操作同一设备共享工作区，应先协调。审核通过不会自动归档或推进基线；需要继续推进时按页面规则执行归档。
- B 的地区、站点、设备均明确标注为测试数据。上传需要 HTTPS secure context。管理入口和目录入口使用各自的 HTTP Basic 凭据；设备 API 使用目录签发的既有 bearer。

## 日常控制

所有命令在 08 上执行。状态以 systemd、Compose、服务就绪和页面实际结果为准：

```sh
systemctl status gdds08-reset-manager gdds08-a-stack gdds08-a-directory gdds08-b-stack gdds08-b-directory
python3 /home/dev/gdds-gw-dms-08-v2/source/deploy/manual-08/check_isolation.py
```

正常停止时先停止目录服务，再停止对应栈；启动时先启动栈，再启动目录服务。管理服务独立于 A 栈，重置时不要手动同时启停 A：

```sh
systemctl stop gdds08-a-directory gdds08-a-stack
systemctl start gdds08-a-stack gdds08-a-directory
systemctl stop gdds08-b-directory gdds08-b-stack
systemctl start gdds08-b-stack gdds08-b-directory
```

`gdds08-a-stack` 的启动保护拒绝未完成或失败的重置。所有 Compose 命令必须使用相应栈 unit 中固定的 project、base 和 runtime override；不要手动挂接另一环境的目录、session、secret、卷或网络，不用全局 prune。自启依赖已启用的五个 unit 及 nginx。

## A 重置与失败恢复

页面点击重置并确认一次。管理服务限制同一时间一项任务：关闭 A 入口、停止 A 目录及组，核对没有其他容器引用 A 的资源，然后重建 A 的十个数据根、会话、路由和目录数据库，以正式 `add-device` 流程重新开通唯一设备。完成前检查组部署、设备公共 scope 和只有 INITIAL 的历史；B 不在重置范围。

成功后关闭其他 A 标签页，从 A 入口重新进入，以清除当前标签页的旧 sessionStorage 和 A origin 的 bundle 缓存。其他旧标签页的旧 token 已撤销，不能继续使用。若缓存被其他标签页持有而清理失败，关闭这些标签页并重试进入。已通过审核但尚未归档的提交也会被重置清除。

失败时入口显示失败阶段；先停止使用 A，查看管理 unit 状态及 A 的 `logs/provision/` 中不含凭据的开通诊断，检查 A 的 containers、根目录标记和路由，不操作 B。确认上次执行及其子进程已结束、A 所有根目录仍归属 A 后可通过按钮重试；如果部分删除导致标记缺失而预检拒绝，先由运维核对并修复该 A 根，不能跳过范围校验。不要把中断或失败当成成功，也不要把浏览器重新进入当成服务器重建成功。

## 升级和回退

先记录当前源码完整提交、各镜像 config digest 和全部 RootFS DiffID、配置及实际挂载。按仓库离线制品规则在授权构建节点构建 clean 新候选，经 LAN 传输并核对归档摘要和镜像身份；检查变更是否要求容器门禁。准备完成后分别停目录和栈，按版本配套更新源码、镜像和渲染配置，启动并核对 readiness、scope、隔离与浏览器旅程。不要在两个环境间复用任何可写资源或 bearer。

本项目不提供旧 schema 迁移或数据兼容。升级前如需保留 B 测试数据，应先停写并制作一致的 B 全部数据根、目录数据库及匹配配置的快照，验证快照后再操作；A 可按授权重置。升级后产生新写入时，直接切回旧版本和旧快照会丢失这些写入，必须先确认范围并由操作者决定。未验证的旧镜像或另一节点证据不能宣称为新部署已通过。
