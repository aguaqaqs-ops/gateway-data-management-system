# 目录阶段 2 窄旅程

本目录只编排已授权的 A/B 功能旅程，不是部署管理器或通用 CI。运行范围、角色及风险依据 [阶段 2 计划](../../docs/device-directory/execution-plan-directory-v1-stage2.md)。A/B CSV 和站号在 `fixtures/` 固定；上传为 FULL：`frontend/e2e-real/fixtures/upload-inputs/sql-baseline.sql` → `sql-initial.sql`，分别配 `frontend/src/test/fixtures/source/upload-inputs/logics-1.xml` → `logics-2.xml`，构造 `full_initial` / `full_modified`，各含顶层 `upload.pmc`、`sql/dbcfg.sql`、`comps/logic/logics.xml`。这与现有真实 e2e 入口 FULL 样例相同；仅 `.pmc` 合成标签区别本轮来源，逐文件摘要入原件。

在 05 的 clean 已提交树运行。先用现有 `vnext/scripts/tests/runtime_config_fixture.py` 准备本人单组空 roots/标准 N1 预算，以既有 render/runtime/build 工具离线构建当前候选镜像。准备只有一个组的 groups 清单、空 seed/session/device-directory，调用 `render-entry` 初始化独立入口、`render-runtime-config.py --build-from-source` 生成覆盖文件。不要复用前端的多 scope harness，它会预先开通设备。所有组内/入口管理均由现有工具拥有。

私有配置按 `config.example.json` 的固定字段写入树外 owned 0600 普通文件；示例路径须在 P2 现场核实后填实。`private_dir` 与证据目录每次必须不存在，禁止复用失败运行目录。配置没有命令、URL、token、shell 或任意环境变量字段。两套 npm 缓存各有 manifest，格式和摘要规则复用 `directory/scripts/frontend-inputs.py verify`，包含 CT201 来源 hostname/完整提交、预填充 UTC、lock、归档和 cache tree SHA256。不得混用两套 lock。

`image_identities` 是 `tag → {config_digest, diff_ids}` 的 JSON，恰含固定 Playwright 工具链、groups 的 entry/backend/worker/repository_service 五个实际镜像。P2 以 `docker save` 和既有 `docker-save-image-identity.py` 从实际节点制品取得，来源/预填充身份另在输入记录中保留；本入口每次重新导出核对，不使用本地 inspect ID 冒充跨节点身份。组 revision 必须等于本次完整 SHA，运行部署检查继续核 OCI revision/实际挂载/预算，不能手工造 label。

```sh
directory/scripts/run-real-journey.sh --head <完整SHA> --session dir-stage2-final \
  --config /home/dev/gdds-test-tmp/dir-stage2-config.json \
  --evidence-dir /home/dev/gdds-test-tmp/dir-stage2-final-evidence
```

入口自行取得整机占用和 Compose flock，外层不重复取得。它核节点/clean/当前候选、固定 Python、离线缓存与镜像、空环境和端口；调用既有 deployment validate/up/check；目录 CLI import/provision；archive 两套前端各自 offline 安装、build。目录 Python 实际提供目录构建，网关 Vite preview 的 `/v1` 只代理公共入口。浏览器单 worker、retries=0、动作 30 秒、业务等待 300 秒、全链 30 分钟；部署和构建另设上限。轮询只等待状态，不重试写动作。公开端口固定目录 8100、preview 4173，冲突停止，不能直连组 backend 替代公共旅程。

浏览器全部由真实目录 handoff 开始，不预注入会话；上传/提交/审核都走 UI。只读 GET 核 actor/scope，续期握手经树外私有标记触发目录 CLI，不向浏览器交内部凭据。旧/新 token 仅在内存及私有 SQLite/session 中；公共 probe 只输出站号、固定标签、状态和布尔值。容器热新增/续期前后核 ID、StartedAt、RestartCount。trace/video/HAR/storageState 和自动失败截图全部关闭，专用 reporter 不输出异常正文。显式十图先核 fragment 清除。

`run.log` 是原始混合输出；`run-events.jsonl` 是固定字段事件；`run-result.json` 保留原始 exit、最终 exit、起止完整 HEAD/clean/UTC/hostname、J0–J7 状态及收尾。`artifacts.json` 只在关闭日志后计算每份原件 SHA256。失败停止依赖验收，unknown 不转通过；停止服务后保留本人私有诊断数据与证据，不删他人卷/镜像。清理失败保留 busy 标记；凭据扫描命中禁止导出，撤销本人 runtime session 并报告。

在同一 05 节点以原件目录运行确定性核对，输出到该运行目录之外：

```sh
python3 -B -I directory/scripts/verify-real-journey.py --run-dir <原件绝对目录> \
  --head <完整SHA> --session <同次名> --output <树外check.json>
```

可选 `--copy-dir` 对可访问副本逐文件核对。无原件、缺字段/文件、unknown、非零、同次身份不符、hash/尺寸或十图清单不符均失败。程序结果只证明确定性条件，视觉/语义由既定角色集中核收。`browser/mock.config.ts` + `mock.spec.ts` 独立补错误初始画面和首末键盘焦点/滚动边界，使用 mock catalog、两宽度六图，不能计入真实 J0–J7。其执行也在专用节点工具链容器；从目录自己的 lock 安装依赖后将 `browser/` 复制到目录 frontend 下运行，`/evidence` 指向独立 mock 输出。

SHA256 用于审核时核原件/副本完整性、锁/缓存和选定镜像来源；不生成新的产品身份/版本。配置和证据 JSON 因用户禁止新依赖而保持 stdlib 严格固定字段校验，这与最新 main 的新增 pydantic 解码要求存在具体冲突，按本轮用户优先约束实施；不改变产品 Contract。
