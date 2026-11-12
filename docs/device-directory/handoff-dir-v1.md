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

## 阶段 1 实施进展（2026-11-12，尚未放行）

产品候选 `e5a9feb7dcb402e838fa83c43398aef092963a0a`；基线与分支历史见上文，产品实现提交从 `8f4a557179` 至该候选，后续本 handoff 提交仅记文档。范围为 `directory/` 和本目录文档；未改 `frontend/`、`vnext/`，未推送。`directory/README.md` 记载配置、CLI 和检查入口。新增代码不在网关 build context，本轮未重建网关镜像。

### 组件检查和缓存

- 06 `gw-dms-06`：2026-11-12 18:45:30–18:45:41 UTC，起止 HEAD 均为产品候选，`UV_OFFLINE=1 directory/scripts/run-tests.sh --service`，exit 0；ruff、mypy strict 和 47 项 pytest 通过。原始日志 `/home/dev/gdds-test-tmp/dir-v1-full-e5a9/service.log`（06），副本 `/home/dev/gdds-stage-exchange/dir-v1/evidence/e5a9/service.log`，SHA256 `18ca5bf6ca4dd8b7ea8a99e6017316e463c32597055fed2fdb54c9ef005eadad`。
- 07 `gw-dms-07`：2026-11-12 18:44:29–18:45:03 UTC，起止 HEAD 均为产品候选，`GATEWAY_FE_TEST_WORKERS=2 directory/scripts/run-tests.sh --frontend --screenshots /home/dev/gdds-test-tmp/dir-v1-full-e5a9/screenshots`，exit 0；类型、lint、8 项单元测试、构建、8 项 mock e2e 和十张截图生成通过。原始日志 `/home/dev/gdds-test-tmp/dir-v1-full-e5a9/frontend.log`（07），副本 `/home/dev/gdds-stage-exchange/dir-v1/evidence/e5a9/frontend.log`，SHA256 `d7e8a78602a3671e41153c7fadc85631e27e861b9c0143501d93bc825b7e159f`。
- CT201 实际 hostname `heavy-dev-01`；Python lock SHA256 `e8831eaccba668e94805d683bd8fdcecf9c1e68ecc4e839ff26d32e942f2dca3`，缓存来源提交 `8f4a557179befbeaa10bcf252c276ce89c36195f`，归档 SHA256 `5b6a5182631b5063a2330f9421369acaca9f5338063351b4ddbd5f625eee8651`，06 预填充 `2026-11-12T18:45:25Z`。06 manifest SHA256 `58d76c3aab335fe4d7539084b725b1b33a5d63a1586f84b684e7f9c89f094280`；uv/Python 身份详见原日志。
- npm lock SHA256 `77c82bb106af15487a87bf149a41d16eb3dec5693ae329e39f81bf71f96d71ae`，缓存来源提交 `018d33ec34daa7e9a9aca9d685b54831bf613493`，归档 SHA256 `524744168cb8b139cabc4a215786ccea7aa3586a788eff0f008e1911f4c66f6e`，07 预填充 `2026-11-12T18:40:25Z`；manifest SHA256 `27927845e3a0976972cbebf8ae2c893a159fcd643f8cc012ae0160eb53625a67`。固定 Playwright 镜像 config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，全部七个 DiffID 载于原日志。两节点均通过 LAN 文件传输取预置缓存，测试未连接公网。
- 失败证据：06 `3111a215f5` mypy 名称冲突，日志 `/home/dev/gdds-test-tmp/dir-v1-full-3111/service.log` SHA256 `2b165649cb5903853ed0277317d4fb8cbb2583d7dbd1d6b1f849ce0bd713e94c`；06 `018d33ec34` mypy 测试替身类型错误，日志 `/home/dev/gdds-test-tmp/dir-v1-full-018d/service.log` SHA256 `a1785239361cddf6681cde146cf0b80100d071f80dded744e76fd5f73b53eae3`；06 `3894fea6db` pytest 收集未找到源代码包，日志 `/home/dev/gdds-test-tmp/dir-v1-full-3894/service.log` SHA256 `8ff2b6d01cf85d2479736f63f7346532ce0e5686f56d949c5c4e7fa0aa7d2d83`。分别修复后从入口重跑。
- 07 `3894fea6db` lint 全角空白，日志 `/home/dev/gdds-test-tmp/dir-v1-full-3894/frontend.log` SHA256 `1b96229013a1e1e7ade65f81fd61f77a04fe067274a970fba20eec553af6a3c5`；07 `1b3912ddc7` Vitest 误收集 Playwright，日志 `/home/dev/gdds-test-tmp/dir-v1-full-1b39/frontend.log` SHA256 `57d67567014aa9c2c7f35f782bbcc90e2616dd51355e46962c4013ea72406085`；07 `e58abf1f71` 两项 e2e 定位器歧义，日志 `/home/dev/gdds-test-tmp/dir-v1-full-e58a/frontend.log` SHA256 `efd99ac8ef8ba8fe56c1b70010be25ed92c62f70d95d961437c9a7fbc85e7beb`。分别修复后从入口重跑。
- 06 初次源码准备 Git 所有权检查失败且修正重试仍失败；停止该次操作并释放占用后，owner 授权独立完整 bundle。记录 `/home/dev/gdds-stage-exchange/dir-v1/cache/service/setup-failure-20261112.log` SHA256 `89c8d0e84cebd7c2231cfdbd943e1595c0606a997b2e6fa30a08301b5583913c`；重试记录 `/home/dev/gdds-stage-exchange/dir-v1/cache/service/setup-retry-failure-20261112.log` SHA256 `b1289eb3f010c0345fae630ef6e774c1369fad1eb949ae624292c4f470a8ee81`。两次均未触及测试对象。

### 截图与审核

十张截图原件在 07 `/home/dev/gdds-test-tmp/dir-v1-full-e5a9/screenshots/`，副本在 `/home/dev/gdds-stage-exchange/dir-v1/evidence/e5a9/`。`SHA256SUMS` SHA256 `720ba4df5d670538c44c0bd7adc68c7a035f82ef26d0225b30d0db156ed03a01`，逐张摘要和状态/宽度以该清单及前端原日志为准；摘要和 PNG 尺寸检查通过不代表视觉验收。

实施者初步对照：布局保留顶部搜索、左侧两层地区树、右侧表格、同名标记与未开通状态。相对草图，地区树的独立过滤框、表头的地区内过滤框未实现；本轮样例目录较小，最近访问为空，截图不能证明有内容时的排布。未开通截图的原生 title 提示未显示，不能凭截图核验禁用原因；焦点、文案及全部十图仍须 Luna 逐项核对并交独审/设计负责人处理差异，不能据此记为视觉通过。

- 基础代码静态独审/复审：`/home/dev/gdds-stage-exchange/dir-v1/reviews/foundation-static-20261112.md`，SHA256 `d60c8108985e1d2cd5eef669463756e649deaaa1cb90c12320f7f2f1939bd222`。
- HTTP 静态独审/复审：`/home/dev/gdds-stage-exchange/dir-v1/reviews/http-8f4a-3111.md`，SHA256 `f07cdc517facd9fd467a77bc8b8d80396736bb8dcd7b1dce5427049b80e2eb21`。
- 开通/续期静态独审/复审：`/home/dev/gdds-stage-exchange/dir-v1/reviews/provision-76b7-2aad.md`，SHA256 `af8c300ed28fad98d6adfa200df355f9307927ec8837ae66a4c195885deb78ed`。
- 服务门禁静态独审/复审：`/home/dev/gdds-stage-exchange/dir-v1/reviews/service-runner-static-20261112.md`，SHA256 `a01e87a9520ff3694ef85dcd33598119fa23d2238077646201572f4e2ff447fd`；前端门禁 `/home/dev/gdds-stage-exchange/dir-v1/reviews/frontend-gate-018d.md`，SHA256 `3c537c298b32eebf232a5d95189416274351b0b3efb4025c778ca5ee3525dc1d`。后续 runner 调整须纳入阶段末独审。
- **尚未完成：**最终候选的阶段末全范围 Astra 独审与 findings 复审；Luna 对批准清单、原始日志、缓存/工具链来源和十张截图的独立逐项核对。当前不可宣布阶段 1 审核通过或放行。真实热新增、旧 token 撤销、上传审核和完整真实旅程均未验证；阶段 2 未开始。

### 后续阶段末核对（候选 e5a9，未关闭）

阶段末 Astra 静态独审原件 `/home/dev/gdds-stage-exchange/dir-v1/reviews/final-e5a9-astra.md`，SHA256 `2e6b6a6b209529c63cd5ee0d5ca8cb36b71ceb2872a76367bc3a6e0152791675`。发现三项 P2：静态根可暴露非构建文件；合法长地址状态超过 handoff 1000 字符约束；HTTP 连接无读取超时和并发上限。需实施修正、原审复审和受影响组件重新取证，`e5a9` 不是最终候选。

Luna 核对原件 `/home/dev/gdds-stage-exchange/dir-v1/reviews/acceptance-e5a9-luna.md`，SHA256 `f46d23b6bf53c22f62ae5a54b8d393ce74b2d43a0b88c662d847ddb8db1d901e`。它核对了副本摘要和十张图，原节点文件从其本地上下文不可访问，原件一致性及来源独立核验记为未知；搜索地区列与高亮缺失、两个过滤框缺失、错误提示状态底部行被裁切列为偏差/失败，禁用提示和焦点证据不足。需由实施者处理并重新取证，由适当角色重新核对；不覆盖原核对记录。

### 修正候选 `3255fe69c2`（2026-11-12，尚未放行）

`75ec736e4f` 修正静态构建清单、长查询及 HTTP 资源边界，`4181a3708f` 修正 socket 类型；`52a34abdc5` 补草图布局、可见禁用提示和焦点截图；`ca96f89f7d` 修正跨父地区同名子节点选中；`3255fe69c2` 修正截图测试定位器。当前产品候选 `3255fe69c2558bad184e0883914431450b754c0f`，以下为实际运行，非沿用：

- 06 `gw-dms-06`：19:12:56–19:13:10 UTC，起止 HEAD 均为该候选，服务入口 exit 0，ruff、mypy strict、63 项 pytest 通过。原件 `/home/dev/gdds-test-tmp/dir-v1-full-3255/service.log`（06），交接区副本 `/home/dev/gdds-stage-exchange/dir-v1/evidence/3255/service.log`，SHA256 `c8d27116dabac40c514f0b85783be94b94015408907b31b455398f8bb8bd8943`。该节点重新预填充时间 `2026-11-12T19:12:48Z`，缓存 manifest SHA256 `462abdf0910b4365c167893de6e1fcf46d9d7e297a2f349615270dfcc9f293f9`。
- 07 `gw-dms-07`：19:11:54–19:12:30 UTC，起止 HEAD 均为该候选，前端入口 exit 0；类型、lint、19 项单测、构建、14 项 mock e2e 和十张截图生成通过。原件 `/home/dev/gdds-test-tmp/dir-v1-full-3255/frontend.log`（07），副本 `/home/dev/gdds-stage-exchange/dir-v1/evidence/3255/frontend.log`，SHA256 `a612d05e4be890e2fbe835854e05b494024acebbafe1eec32aa073f5f8574a97`。沿用上文同一 npm 缓存与固定镜像身份，manifest SHA256 `27927845e3a0976972cbebf8ae2c893a159fcd643f8cc012ae0160eb53625a67`。
- 十张截图原件为 07 `/home/dev/gdds-test-tmp/dir-v1-full-3255/screenshots/`，交接区副本 `/home/dev/gdds-stage-exchange/dir-v1/evidence/3255/`；`SHA256SUMS` SHA256 `dd36a8348cdca2ba0e0472327ac6aaf8c531aa3a1902b9bc8f7c1ad9e41c9aa3`。实施者从节点读取原件摘要的记录 `/home/dev/gdds-stage-exchange/dir-v1/evidence/3255/node-original-hashes.log` SHA256 `6081a4885d3c2e38bb47821e0470039e1e40418274436dcf4012a2d22f3b45a7`；Luna 独立视觉核对仍在进行。
- 新失败记录：06 `75ec736e4f` mypy socket 类型错误，日志 `/home/dev/gdds-test-tmp/dir-v1-full-75ec/service.log` SHA256 `fae098728616eecccddae9002f4289a852abcff788bcb1c1a5bc3f622df2be25`；07 `52a34abdc5` 键盘测试失败，日志 `/home/dev/gdds-test-tmp/dir-v1-full-52a3/frontend.log` SHA256 `bc77bace43561ff844f461db187169099aab988dde82987230b1e968368717b5`；07 `3deac086c4` 键盘未选中，日志 `/home/dev/gdds-test-tmp/dir-v1-full-3dea/frontend.log` SHA256 `c3e0ffb27fe856d2372c59abb8d87d461bf9fd7385614a4ad527b3bd92e39f00`；07 `ca96f89f7d` 截图测试 XPath 错误，日志 `/home/dev/gdds-test-tmp/dir-v1-full-ca96/frontend.log` SHA256 `b9855cb9ec6521da01b25b75e471ee905952b635563734bb845de47f4441a227`。修正后重新从入口执行。
- `e5a9` 三项 P2 修订的 Astra 静态复核 `/home/dev/gdds-stage-exchange/dir-v1/reviews/rereview-75ec-astra.md` SHA256 `b78fa092a850581ead9f441ef8480e018cef84161f5a3c4f91d609f7cd37f22a`；前端新 P2 原审 `/home/dev/gdds-stage-exchange/dir-v1/reviews/frontend-52a3-astra.md` SHA256 `8e3d0c6bb3d498277da09fccef6d710fe36f48a28c8deb503f24b4419c77ad57`，修订复核 `/home/dev/gdds-stage-exchange/dir-v1/reviews/rereview-ca96-astra.md` SHA256 `dd53d3b50c2beeece54ceafe14258c08f75d3a66350c9843d438c209b360b977`。两次复核是新的 Astra 上下文：阶段末原审临时会话不可恢复，不能称为原审者复审，须协调者处理此流程差异。
- 搜索草图的拼音命中对应汉字高亮缺少接口位置映射；当前仅直接文字命中高亮，设计偏差已交 owner 决定，未擅自标为通过。真实热新增、撤销、上传审核和完整旅程仍未运行。阶段 1 交审/放行待上述决定、视觉核对和审核流程差异处理；阶段 2 未开始。
