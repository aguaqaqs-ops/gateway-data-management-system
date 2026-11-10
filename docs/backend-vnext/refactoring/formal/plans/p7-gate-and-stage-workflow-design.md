# P7 门禁自动化与阶段交接规格

2026-11-10；P7-D25/D26 的设计交付。脚本尚未实现，本文件不宣称门禁已通过。
流程从后端 S1b、前端 FE4a 后下一步生效；S1a/FE4a 的授权、角色、执行方案保留。
不触及 D3，不改 P6 结果，不建设 CI 服务或新的 evidence 状态机。

## 1. 门禁入口与实施顺序

拟建仓库根 `scripts/run-stage-gate.py <commit-sha> [--packages <列表>]`，放在 `vnext/` 外，避免仅修改编排就改变 Docker context。另提供 `--fresh`：跳过查表，最终 S5、发布和最终 production gate 必须使用，完整六包且最终 HEAD 重建镜像。参数只接受可解析到本地 commit 的完整 SHA；包列表按 runner 固定顺序及合法性处理，默认六包，拒绝未知/重复包。

由一个独立流程工具实施任务负责，可现在与 S1a 并行准备，S1b 启动前完成：

1. 先实现执行、占用和结果记录，调用原 runner，不修改 runner 行为。
2. 再加入闭包准备、查表及容器等价判定；首次无记录正常实跑。
3. 在专用节点 clean 已提交源码上验证：占用冲突不抢占、错误 SHA/包拒绝、runner 失败不重试、信号退出、日志/JSON 完整、文档提交命中、包闭包变化重跑、镜像变化重跑、fresh 强制六包。故障控制用入口的窄 subprocess 测试替身，不触发真实破坏；至少一次真实权威 runner 成功及同树文档提交查表闭环。验证不能在开发机执行，也不在本次文档任务执行。
4. 协调者按实际故障后果定级（假阳性可放行错误产品，需重点审核查表/失败逻辑），安排独立代码审核及一次结果核对后启用。结果记阶段交接区，不另造入库 handoff。

真实数据旅程在第二步扩展中接入同一记录格式，当前仍用已有旅程入口；不按包摘要自动沿用真实数据、不更改 DC33 已确认范围。前端仍调用自己的权威入口与真实 backend e2e 入口，首版后端查表不涵盖前端。取消测试者后由实施者执行前端现有脚本，协调者引用机器日志；后续适配可复用结果格式。

## 2. 执行算法与失败语义

- 目标 `ct108-gw-dms-04`，固定 detached worktree `/home/dev/gdds-stage-gate`；经获准 LAN Git/文件取得已提交源码，不网络 fetch 公网。启动先 BatchMode SSH；固定树若 dirty、用途冲突或不存在且父目录不受本任务管理则失败，不 reset/clean 他人内容。
- `mkdir /home/dev/gdds-node-busy.d` 原子取标记，记录本次 run ID、会话、用途、UTC；冲突即 exit 3，由协调者稍后重新触发，不抢占、不自动清陈旧标记、不无限等待。取得后复核 Dolt/Compose/端口与本机现场，冲突安全退出。
- 检出 SHA，保证 `legacy` 指向 `/home/dev/gateway-data-management-system/legacy`；已有错误类型/目标拒绝覆盖。运行期间不写被测树、不重建/retag 相关镜像（runner 内已规定的构建例外保留）。记录起止 HEAD，必须等于输入 SHA，确认 clean。
- 环境采用现行 testing-conventions：`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`，root PATH 首项 `/home/dev/.cargo/bin`，无 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME，按 selector 核四个 Rust 工具。预填充 dependency-base、Compose 本机构建、build network none、五锁保护、LAN 缓存及代理禁令全部保留；缺缓存停止，补齐后新运行，不伪装命中。
- **闭包前置准备必须等价于 runner**：用 `uv-consume.sh` 同步所有选中 Python 包（backend 强制 reinstall 扩展及校验 build input）；采用 runner 相同逐包 Hypothesis 路径并清理，清理规则内的 Cargo 临时目录。不得清理 worktree `.hypothesis`、包 `.pytest_cache` 或其他文件以制造命中。环境同步可能编译，仍在占用内、专用节点执行。
- 逐包调用 `python3 -I vnext/scripts/test_input_closure.py manifest --package ...`；同节点、同固定 worktree、相同路径和权限/环境/缓存/镜像等组成的摘要才能查表。固定路径只是必要条件，文档提交也可能因环境变化不命中；不承诺所有文档提交无条件沿用。
- 没有可用通过记录的包合并成一次 `GATEWAY_TEST_PACKAGES=... ./vnext/scripts/run-tests.sh`。保存 runner 自身 exit（不能用 tee 的 exit）、原始日志及 runner 起始 manifest；前置摘要与 runner manifest 不同则以实际 runner 输入为准，不把旧摘要写成通过。整次 runner 非零，本次失败，不把部分包成功录入可沿用表，不继续 carried 或依赖验收，不自动重试。
- `try/finally`/信号清理本次进程与资源后才释放自己的标记。无法确认子进程/服务已收尾时保留标记和失败记录交协调者，不释放供下一执行误入；SIGKILL/断电残留人工核进程后处理。失败结果仍保留日志与 SHA，环境/命令修复按现行快速修复规则另开 run，不能覆盖失败。

## 3. 结果与查表

04 本机结果根 `/home/dev/gdds-gate-results/<full-sha>/<run-id>/`；每次一个 `result.json`，同目录 raw log、逐包 manifest，JSON 临时文件写完后原子 rename。run ID 使用 UTC 加随机后缀；失败不覆盖历史成功记录。不另建数据库，查现有 JSON 即可。

必填：`schema_version`、`run_id`、`commit_sha`、`node_hostname`、`worktree`、`started_at`、`ended_at`、`start_head`、`end_head`、`exit_code`、`status`、`requested_packages`、`fresh`、编排脚本版本、日志路径/SHA256、各包闭包总摘要/manifest 引用、`mode=run|carried|not_run`、最初实际运行的来源记录/提交/日志，以及 `container_gate` 的状态、触发重建理由和 image revision/source-tree。缓存来源与镜像身份附在结果中或引用相邻机器记录；敏感 URL 只留摘要。失败前尚不可得字段用 null 并写原因，不填成功值。

查表只接受原始实跑包通过且整次 runner exit 0、clean、起止 HEAD 一致的完整记录；核原日志/manifest 存在且 SHA 匹配。沿用记录直接指最初实跑来源，不递归沿用链。同节点/同 worktree 外的旧记录不导入自动命中库。成功判定覆盖所有请求包；未请求包不得记为通过。脚本版本记录用于解释执行差异；修改查表或失败语义后，需审核确认是否仍可使用旧记录，不能用产品闭包不变掩盖工具缺陷。

按包查表替代人工摘要抄录和 carried 文档；容器等价由脚本同时检查：来源至目标未触及现行 Docker/部署/runtime/e2e/harness 边界，RS 重算 build-input/source-tree 与 label 一致，backend/worker 按同来源 worktree backend manifest 一致。任一不满足则相关包必须重建并实跑；后来的“改回去”也不能跳过既有区间规则。仅阶段退出/S3 ready 可沿用，发布/最终 production gate 及 S5 强制 fresh。阶段总结里的门禁引用即可，不再人工重写整份 carried 证明。

## 4. 阶段交接区与一页总结

开发协调节点统一 `/home/dev/gdds-stage-exchange/<stage>/`，stage 如 `p7-s1b`、`fe4b`；不在 Git checkout 下，不假定各节点共享磁盘。协调者将远端结果按原字节复制并保留来源 hostname/路径；保留原始记录，复制不使跨节点沿用合法。

- `log.md`：追加每个角色的一小段，UTC、角色、提交 SHA、做了什么、未测/未决问题、下一步；同一协调者串行合并追加，避免覆盖。
- `reviews/<sha>.md`：审核意见及追加复审结论，标明审核范围、风险和模型家族。
- `gate/<sha>.json`：本阶段采用的结果引用（node、path、run ID、SHA256）；多次运行保留原结果，失败引用留在日志。
- `reference/<sha>/t4/`：已有真实 t4 旅程的逐尝试摘要、输入身份、配置和旅程结果引用；用于同输入参考，非数值退出门槛。
- `prompts/`：如确需角色提示词，放这里；设计、Contract、正式决议仍入库，旧过程文档不迁移或删除。

退出时协调者在 `docs/backend-vnext/refactoring/formal/plans/<stage>-summary.md` 合入一页（建议不超过约 800 汉字，链接不复制原始记录）：

```text
# <阶段> 总结
起止提交 / exit tag / 日期：
完成：用户可观察的行为与 Contract 改动。
偏差：相对已批准设计的变化及已确认决定；无则写无。
验证：门禁结果 URI、run ID、SHA256；真实旅程及独审引用；未测限制。
遗留：问题、影响、负责阶段；无则写无。
```

不得把总结提交冒称已经实测；由自动查表将结果绑定到总结后的 HEAD，需重跑则照常运行。

## 5. worktree 回收安排

本次仅盘点，不删除。2026-11-10 本机共有 402 个注册 worktree，其中 352 个 HEAD 为盘点时 main 的祖先；按 clean 与排除规则筛出 250 个候选、152 个排除项。候选仍需执行前核实无活动消费者，不能仅凭名称删。清单在 `/home/dev/gdds-stage-exchange/process-rollout/worktree-{candidate,excluded}-20261110.md`，机器清单另存 JSON，包含盘点时 main、HEAD、clean 与原因。本机清单不覆盖测试节点，也不把复盘时 352 当作当前可删数。

候选须 HEAD 是 main 祖先、含未跟踪文件检查为 clean、用途明确且无消费者；在途 S1a/FE4a、门禁及 carried 来源、分支工作区、有改动、锁定/失联及用途不明者排除。执行前先给 Owner 看数量和排除项，核现场进程/标记及来源使用；仅用 `git worktree remove <path>`，不用 force、reset、clean 或按年龄批删。移除失败保留并记原因。远端盘点/移除另在各节点依现行占用规则完成，不顺带清卷/镜像/证据。今后审核区用毕、finding 关闭且无消费者即回收；固定门禁 worktree 长期保留。

## 6. 来源冲突与待 Owner 决定

D1 输入仍按旧分工指定 04 门禁、05/06 调试；最新 AGENTS 的 DC91/DC97 已是五节点资源池。**建议**仅新自动门禁固定 04（同树沿用需要），focused/真实旅程继续现行池规则，05 t1 为优先安排；不恢复旧节点职责。本规格不废止池规则，若 Owner 要恢复旧分工需明确决定。04 忙则自动门禁退出等待，不自动移到另一节点复用记录。

P7-D23 的“只记已算出的数、不新增采集机制”与输入同时要求补解析/物化/bundle/RS/finalize 计时、其他缓存计数存在字面张力。**建议**允许在现有阶段边界增加单调时钟计时和现有缓存分支的普通整数计数，禁止扫描、profiler、新采集服务；S1b 详细设计据 Owner 确认后实施。缺失目前记 null，不伪造零或以一次抽样猜全量。
