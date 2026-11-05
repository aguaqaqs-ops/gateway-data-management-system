# Phase 6 四路输入生成工具：F1 增量复审

- 结论：**F1 关闭；代码及定向证据通过，无剩余阻塞项。** 可由原基准实施者协调合入及后续需要时使用。当前 CT108 运行不切换；不据本报告直接启动大输入准备或宣布输入 READY。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 原审核：`8983fe86a6b3c18b3c929d7323ece69879db6f6e` 的[代码与证据审核 1](p6-input-four-worker-code-evidence-review-1.md)。增量起点 `6f78b8fc5041416e59b4f32b91828e00819cad9e`；最终代码 `3d6b1ae59b80a173b1b6411744a53f8294a6c1b4`；最终 handoff `a5e8809f08257600c103a396fc8cf8448ba6a533`，分支 `p6-input-four-workers` 的 `p6-baseline-four-worker-handoff.md`。
- 方法：在 `/home/dev/gdds-p6-four-worker-rereview-a5e8809f` clean detached worktree 只读核对；程序比较完整 HEAD、detached/clean、祖先、改动面及 Git 对象。复核 CT201 副本后，经 BatchMode SSH 仅读 05 已结束日志、脚本、锁和保留 worktree，不取占用、不重跑测试或诊断、不访问 CT108。核对程序经 stdin 执行，无落盘临时脚本。

## 1. F1 修正与覆盖

`run_generation_units` 现在收到成功 payload 后，依次执行 `join(timeout=5)`、拒绝仍存活的子进程、拒绝非零 `exitcode`，最后才调用 `accept`。因此成功 payload 后非零/信号退出或不退出均不能进入发布回调；异常进入原 finally，收束所有剩余自有子进程。W4 只有被正常接纳的同档两份结果才可能发布 receipt，已成功兄弟段的保留规则不变。

新增参数化测试运行真实四路 W4，在父进程已接纳其余三单元、10% receipt 已完成后，令 100% 重复单元发出成功 payload，再分别 `os._exit(23)` 或等待不退出。测试断言仅三个正常单元被接纳、失败档无 receipt、无 READY、有效 10% receipt 保留，以及本次子进程全部收束，直接覆盖原 F1 两条路径。

测试用父进程创建的 Event 协调正常单元；最终 `3d6b1ae59b` 将等待失败 fixture 改为有界 sleep，避免在被强制终止的 child 内创建额外 semaphore。既有无 payload 硬退出、成功兄弟段复用、取消、1/2/4 等价与完整验收不发布等用例保留。本轮没有新增算法证明或产品机制。

程序确认 6f78 至最终代码的 `vnext/` 改动只有共享调度器和对应测试。生成算法、封包、pair/receipt、W4 汇合、主准备/验收模块的 Git 对象均未变；代码至最终 handoff 仅文档变化，diff check 通过。最终 `vnext/` tree 为 `f0906b5c9df312214ebdfe2fae0d4e3c449edae2`。

## 2. 原始证据与身份

05 原始日志及 CT201 副本 SHA 均与 handoff 相同；运行记录为 `gw-dms-test-05`、**07:35:49Z–07:36:16Z**、起止完整 HEAD 均为 3d6b、`validation_exit=0`。程序核对 **61 passed in 25.31s**、五次 Ruff 和五次 mypy 成功。

| 证据 | 重算 SHA256 |
| --- | --- |
| `p6-four-workers-fix-3d6b-validation.log` | `e9563b0963b980e9f78d85035021cbc0a6d44cb1a79b42db62579d10f486238a` |
| `p6-four-workers-fix-validate.sh` | `5be2877e8e45393fd13c055b1b7ab83eb6417e90361b4e71df9ce6b351f76e87` |
| `p6-four-workers-fix-postflight.log` | `8261deb0cfb19d2d7dbb489791c7dea621b710d6634184fe9b42f9da4435fe50` |
| LAN bundle | `3051c36e0b34d00477420cae629d3dee53f06f39ac9a7dff877b3400f34255f9` |

wrapper 摘要已记录于运行日志，当前实际脚本与其匹配。脚本核对 clean 和自有占用，设置 offline、外置 TMPDIR、unset proxy/Rust 覆盖，使用受控 `run --no-sync` 依次执行三个工具测试文件和五包静态，失败停止后续步骤。未改锁、安装依赖或使用代理。

before/after/postflight 三份五锁清单 SHA 均为 `16c8ab14e5714fcc4e8470beea91feda7c56405ef42c36d66ef83336e8d3f238`；实际锁与候选 Git 对象逐项比较一致。节点 `/home/dev/gdds-p6-input-four-workers-05` 当前仍为 clean detached 的固定 3d6b。

## 3. 清理与证据边界

postflight 记录 **07:37:09Z** 无本轮 pytest/spawn/tracker 遗留、clean/五锁不变，核对自有 marker 后释放。审核时 05 已由 `fe3a-impl` 于 07:37:45Z 获取，用途为真实 backend e2e smoke；原 `p6-four-workers-exit-fix` 标记已不在。该占用不是本轮遗留，审核只读取本轮已结束的小型材料，未运行新验证、清理进程或改动其他会话标记，也不宣称节点当前空闲。

原 6f78 的有界样本数据与完整复核继续按原提交引用，不改写为 3d6b 实测。此次只修正结果接纳与退出确认顺序，算法/封包/验收未变，符合原审核允许不重跑真实样本或 full4 的范围；新增 focused 已覆盖修正后的正常及失败路径。

## 4. 后续

可协调合入本工具，后续确需重开时按 §5.5 显式选择已核资源预算内的多路值；原停止规则、pair/W4 分阶段、正式计时单飞、完整输入验收均不变。共享调度身份变化会保守失效旧 receipts，不人工豁免；历史 full4 导入仍未纳入本轮。首次必要大输入准备分别核对 pair/W4 预算及运行期资源/截止守卫。

本轮没有产品、依赖、容器或部署边界变化，不触发镜像重建，无新 image revision 门禁声明。仅显式路径提交本报告，不合入工具、不推送、不启用、不修改设计/计划正文。保留节点证据与实施 worktree，审核 worktree 核对 clean/HEAD 不变后清理；按本轮明确沟通授权，仅向指定设计线程回传结论与报告提交。
