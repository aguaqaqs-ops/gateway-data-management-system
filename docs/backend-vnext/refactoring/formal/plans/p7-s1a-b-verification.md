# P7-S1a B 固定验证稿

日期：2026-11-10。状态：候选待原审，尚未执行；本稿不签 SCRIPT_GO/B_GO。

起点 `00ca325c2ed6d705abfa39e9528ef148e6029cfc`。唯一测试角色只在原审核准精确候选 B_SHA、本稿与脚本 SHA256 后执行 [p7-s1a-b-verify.sh](p7-s1a-b-verify.sh)。固定节点 `ct107-gw-dms-06`，主机名 `gw-dms-06`；不改节点、参数、worker 数、预期或现场修脚本。失败先停本次及依赖验收、保原 exit/日志/SHA，交实施者/原审；依本轮用户 AGENTS/DC68和提示词处理，不沿用 main 的 DC91/三轮恢复权限，不无修改重试。

开始前 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`，只读核本节点有效占用、Dolt/Compose 与共享端口；忙则等待，不能碰他人标记。源码经获准 LAN Git/文件传输到本任务新 clean detached worktree，准备仓库忽略的 `legacy` 参考链接。不在主工作区执行，不覆盖 A 成功/失败原件。脚本自身原子取得 `/home/dev/gdds-node-busy.d`，外层不要重复取标记。记录本节点实际 uv/Cargo 缓存类别、LAN 缓存端点标识/来源提交/摘要/预填时间（已知项）及是否使用预填缓存；未知如实写明，不打印含凭据 URL。缓存缺失停止，不经公网或代理补装。

固定命令：

```bash
bash "$CLEAN_WORKTREE/docs/backend-vnext/refactoring/formal/plans/p7-s1a-b-verify.sh" \
  "$B_SHA" "$CLEAN_WORKTREE" "$NEW_LOG_DIR" "$SESSION"
```

四参数精确值由协调者交接；B_SHA为40位小写hex，SESSION为1–64位`[a-z0-9][a-z0-9_-]*`。NEW_LOG_DIR为 worktree 外、父目录已存在的全新路径。调用时保 SSH 原 numeric exit，不能用 tee 成功掩盖脚本失败。

脚本完整固定内容：

1. 起止 hostname/UTC/HEAD/clean；HEAD等于B_SHA且起点为祖先；脚本与本稿SHA。拒绝dirty/错误节点；核锁文件与Rust源码未变。
2. 离线 `UV_OFFLINE=1 CARGO_NET_OFFLINE=true`，`TMPDIR=/home/dev/gdds-test-tmp`、Cargo jobs4/外置target，root PATH以`/home/dev/.cargo/bin`起，不接受RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME覆盖。通过受控uv同步五包，backend强制重装扩展并绑定HEAD的Rust tree，检查安装扩展build-input；该编译仅在06执行。
3. 五Python包分别 `ruff check .` 与 `mypy`。脚本遇首次非0停止，不跳过未改包，不在节点auto-fix。
4. backend按脚本固定文件列表运行focused unit：非serial `-n 4`，serial `-n 0`。覆盖共享配置、四位置codec/拒绝、nominal UUID、canonical完整key、Snapshot wrapper内容身份、producer/cache、checkpoint/job/SQLite/domain、facts/archive绑定golden、bundle/surface与上传接线。RS仅运行同一共享配置格式向量，`-m unit -n 0`，不创建Dolt库。不是权威全包runner，不作carried来源。
5. 成功与失败均收尾核起止HEAD/clean、原numeric exit；只删除本人且owner内容匹配的标记文件，再rmdir忙目录，不递归清理/释放他人资源。保源码、环境、成功/失败原件。tee结束后另存VERIFIER_EXIT、LOGGER_EXIT和最终日志SHA256。资源释放或logger失败也非0；不能被验证主体成功覆盖。

6. 本轮改到实际Compose harness的manifest观测器，必须在当前候选离线重建backend/worker，并运行代表性既有`test_compose_history_compare_journey_zero_write_restart`（`-n 0`）。观测器按严格ref/位置及owning manifest decoder识别全部规范化manifest；前置非空、前后相等与重启断言保持，不再按不可见的旧kind前缀返回空集合。ordered旅程只改同helper名称并补非空保护；同一观测器由上述history向量覆盖，不将两套长旅程相乘。本步骤实际仍是B现有单root部署，不能称多root/缺挂载/cgroup通过。

容器前提由唯一测试角色只读预检实际06本机dependency-base，向原审固定具体tag、config digest和全部RootFS DiffID，记录来源/预填时间；脚本要求`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<固定本机tag>`、`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=<固定本机RS tag>`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，且不得设置`GATEWAY_COMPOSE_GATE_PREBUILT`。两个base必须已在本机；RS builder保留既有预置依赖逻辑，缺base停止，不走公网/转发或臆测cache。`GATEWAY_COMPOSE_GATE_PROJECT_NAME`、session和provenance路径由脚本固定至本任务。harness在本机正常build，不手工retag/rmi。日志内inspect ID仅作本机身份，跨节点仍比config digest与全部DiffID。既有harness负责其Compose生命周期/finally收尾，脚本保留provenance及SHA；唯一测试角色收尾再核无本人栈/进程残留后核收资源释放。

本稿不运行Rust算法测试（Rust源码未变）、真实输入、全量runner、carried或性能测量。依赖/lock/Dockerfile/entrypoint/Compose YAML未变。Current HEAD container gate未执行；旧P6结果不表述为B当前HEAD通过。typed格式通过不等于实际source/mount/marker/symlink/cgroup/ready检查通过；四位置ID通过不等于多root存储发布或跨盘借用通过。C–F实际新布局和G仍须自己的当前候选边界验证。

回执须给B_SHA、节点、起止UTC/HEAD、每步及整稿原exit、日志路径/SHA、实际运行范围/未运行步骤、缓存来源类别/限制、资源释放状态；原审据真实证据决定B核收。未执行、失败、UNKNOWN和后续包责任不填PASS。
