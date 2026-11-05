# Phase 6 重建对照基准：H3 provenance 定向审核 1

- 结论：**需修订，1 项阻塞；当前候选不可继续缓存准备或正式 H3。** 来源选择与两阶段流程方向成立，但目标比较器错误地要求服务启动前后的三卷逐字节相等，会误拒绝正常运行。修正后定向复审，不重建基准、不改产品、不放宽 DC68。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 候选：`p6-baseline@95b1d4b1c4122747a08fffd31d8fbea7688a83b9`；范围：`25e95c35f0e19380f3f53079f1a3b418b472fc36..95b1d4b1c4122747a08fffd31d8fbea7688a83b9` 的工具、对应测试、runbook 与 handoff，共 6 个文件。
- 依据：DC66 第 5 项、DC68、DC73、执行计划 §7–8；实施方报告已获认可的“原 H2 cold checkpoint → 独立 prime → 成功最终状态复制 → H3”边界。本报告审核工具与恢复流程，不接受尚未产生的测量结果。
- 方法：`/home/dev/gdds-p6-h3-review-95b1d4b1` clean detached worktree 只读审核，程序确认完整 HEAD、detached 与 clean。05/ct108 只读取指定日志、JSON 与 HEAD/status；未取节点占用，未启动测试、产品、Compose、sampler 或 journey，未写节点。

## 1. 阻塞项

### F1：把启动后的 checkpoint 与启动前复制卷强制判等

位置：候选 `vnext/backend/benchmarks/p6_baseline_h3_provenance.py:1241` 的 `checkpoint_report[volume_digests] == expected_target_volume_digests` 判定；相关测试 `vnext/backend/tests/test_p6_baseline_h3_provenance.py:264`。

`expected_target_volume_digests` 来自 prime 成功停栈后的最终卷。`run_journey()` 先复制这三卷并立即核对复制摘要，随后 `_run_journey_impl()` 执行 Compose up、等待 readiness；`_run_tier()` 检查 healthy cache 后，才在 `runner.run("history", ...)` 前暂停服务、保存 H3 checkpoint。因此，复制摘要与 checkpoint 摘要代表两个不同时间点。

这里不是仅有潜在的后台写入：Repository Service 的 `runtime.py:181` 启动路径调用 `is_durable_root_writable(layout.service_state)`；`capacity.py:54` 在卷内 service_state 目录创建并删除 `.write-probe-*`，正常情况下即改变该目录的 mtime。`real_dump_journey.py:6893` 的 `_volume_tree_digest()` 摘要全部子目录及文件的 mtime、权限、大小与内容。故即使比较 commit、缓存对象与 TTL 完全正确，启动后的 checkpoint 也不应等于启动前的复制卷。当前比较发生在正式 H3 完成后的 `compare-target`，会把有效运行误判为 `H3 pre-History checkpoint differs from the copied cache-source volumes`，再次触发停止。

现有成功 fixture 在 final-state 分支专门将 checkpoint 的静态 `volume.data` 内容设成源最终卷内容，并固定 mtime；它没有模拟真实启动的目录变化，因而 164/164 通过不能证明此判定可用于正式运行。本结论来自调用顺序和明确文件系统写入的静态核对，未运行真实 H3 来复现。

处置（DC66 第 5 项工具修正）：保留源最终卷→目标刚复制完成卷的精确摘要核对；H3 pre-History checkpoint 则核对自身三卷快照与记录摘要、步骤边界及恢复来源，同时继续核对相同比较 commit/rules、healthy cache、原 TTL、输入与镜像身份。不要把跨服务启动的两份全卷摘要要求相等，也不要通过排除真实文件或统一删除 mtime 来掩盖复制错误。

验收：补一个启动后存在正常目录/运行时状态变化、但来源复制与 checkpoint 自身均正确的正例；保留复制错误和 checkpoint 实物被修改的负例。定向测试覆盖实际生产调用顺序；不以扩大真实 t4 测量替代工具验证。05 focused 与五包静态检查通过后交复审。若认为必须调整已认可的恢复语义或验收边界，标记 **交设计会话**，由 owner 转交；本审核不直接修改设计。

## 2. 已核对成立的部分

| 项目 | 核对结果 |
| --- | --- |
| 来源与目标隔离 | 来源读取其 `run.json` 记录的原 manifest 路径及 SHA，再执行严格 `compare_state_to_manifest`；目标 manifest 独立解析并按角色、包 SHA/bytes、census、dataset manifest、accepted-input 摘要比较，没有拿 H3 manifest 覆盖来源绑定或忽略额外上传。 |
| H2 选择 | 限定已成功的 `p6bwh2twonode20261102a`、完整两节点步骤与 3 个上传角色，拒绝 v3。原 run/state/log 的实际字节 SHA 与 source-check 报告一致；原 manifest 与 H3 manifest 实际字节相同。来源 HEAD `0739d8cba0057e2edfa0ee991d46e1c7282ef31e` 到候选的文件差异经程序确认仅在工具、测试和文档。 |
| cold → prime | 原 History checkpoint 的状态、三卷摘要和日志清空顺序受到核对。prime 要求空缓存，不删除条目或修改 TTL；准备后必须非空、无过期记录、无缺失对象。原 H2 卷和证据保留，不把超过 24h 的旧缓存直接用于 H3。 |
| final-state 恢复 | 显式选项限于 healthy t4 两节点 History；成功来源保留三卷，复制前后均校验，复制 state 仅去掉 history。新 project 生成新的 History idempotency key；不重用旧请求结果。 |
| 两段关系 | parent run/state/log SHA、源/目标卷映射、输入、产品与 backend/worker config digest、全部 DiffID、v1/v2 commit 与 comparison/risk/surface 摘要有程序关系核验；F1 是额外施加的错误跨时间点相等要求。 |
| TTL 与计时 | 准备运行检查空缓存和生成结果，目标 History 前检查完整健康缓存；比较器另用 prime 前置检查时间给出保守 24h 上限。准备、复制、checkpoint 与 Compose 启停不计入正式 History operation timing。未改计时器或已完成场景的计时路径。 |
| runbook | sampler/module 工作目录与字面绝对 `.venv/bin/python` 路径一致；同一 H3 manifest 双绑定，保留 V′ identity checker、离线、清除代理、offline composite、stop-on-manual-recovery、独占与清理要求。17 个 Bash fenced blocks 的 `bash -n` 全通过；未执行内容。 |

## 3. 证据复核与限制

以下 SHA256 均从节点读取实际文件字节后重新计算并程序比较：

| 节点 / 文件 | SHA256 / 结果 |
| --- | --- |
| 05 `/home/dev/gdds-p6-logs/baseline/h3-revision/95b1d4b1c4-ct05/validation.log` | `fb6b3963629f0c4ff737cf7d6045a21fd0903dd80e9a8ff022ace2adaee1cc97`；hostname `gw-dms-test-05`，12:18:03Z–12:18:07Z，起止完整 HEAD 均为候选，164 passed，五包 ruff/mypy 全通过，overall exit 0，结束 status 空。 |
| ct108 `/home/dev/gdds-p6-logs/baseline/scenarios/h3-source-check-verified.json` | `d309f95b2d741af6f1b77f85e1ab8443105602c4b0a8cd6783b68fc3af354a43`；RESULT=MATCH，purpose=cache-preparation，3 个角色、3 个 checkpoint 卷。 |
| ct108 同目录 `h3-source-check-verified.log` | `679e712db8697666751c3d3c602ae0e593249c55ccd8c6d6aee5b75679bf626a`；RESULT=MATCH。 |

另核对 source run SHA `d59325ab74772626d0aa7e441628621277d1a7fde282221f6c2dbcca73750131`、state SHA `f5e928507f021123f578e83a0847f6fcbe14cc3b82b5835f5e17cd7d1b3a8802`、source log SHA 与报告一致；原/目标 manifest SHA 均为 `3142b35994971efb925de1ed073835cc866387ecdd9762a8065753181511b6b6`。只输出身份、计数及摘要。未再次遍历大体积真实 checkpoint 卷；该项本轮核对已提交校验实现及已保存 source-check 结果，不声称独立重跑了全部 source 校验。

ct108 指定 worktree `/home/dev/gdds-p6-baseline-measure-h3-ct108` 当前 HEAD 程序比较等于候选，status 空。现有静态/单元证据与 source MATCH 不代替尚未执行的 prime、H3 和 compare-target。`git diff --check` 通过。

候选 handoff 最后仍写“candidate commit、CT05 验证、CT108 source check 待填写”；复审前须补入准确提交、上述实际路径/摘要、失败调试与修正记录，保留停止历史。属于 DC66 第 5 项既有记录要求，不新增测量场景。

## 4. 镜像、停止与后续

本轮只改基准工具及测试/文档，不触发产品镜像重建；冻结产品仍为 S1c V′，来源 backend config digest 为 `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1`，记录有全部 15 个 DiffID。实际 prime/H3 启动前仍按 runbook 对 V′ 做完整程序比较。本报告不把工具 HEAD 当作新的产品 image revision，也不作当前候选容器门禁或 carried 声明；基准最终 04 runner/终审仍待完成。

维持缓存准备和 H3 暂停。F1 修正并经定向复审通过后，按已获授权的原范围推进，不扩大场景、不自动重跑已完成 H2；新失败继续遵守 DC66/DC68 与输入/身份/缓存停止规则。剩余超过 48 小时停止交 owner。S2a exit 仍等基准 exit（DC70）。本次不推送、不办理 tag/合入/阶段 exit。

## 5. handoff 更新补核：9bf9b02701

实施方随后将审核终点更新为 `9bf9b02701252ad9ba0b8c31440e14c01070703b`。在 clean detached worktree `/home/dev/gdds-p6-h3-review-9bf9b027` 程序核对：相对代码候选 `95b1d4b1c4122747a08fffd31d8fbea7688a83b9` 仅修改 baseline handoff，`vnext` Git tree 完全相同；`git diff --check` 通过。因此本报告覆盖的累计区间更新为 `25e95c35f0e19380f3f53079f1a3b418b472fc36..9bf9b02701252ad9ba0b8c31440e14c01070703b`，代码审核不重复。

handoff 已补齐代码候选、验证路径/SHA、来源原 manifest 与目标关系、失败调试说明及剩余 `14–30 小时` 估计，关闭 §3 的“验证结果待填写”记录项。新增 05 preflight、postflight 与 ct108 source-check-execution 三份日志实际 SHA 程序比较均符合 handoff；最后一份记录 hostname `gw-dms-test`、2026-11-04T12:19:52Z–12:19:55Z、候选 start HEAD、exit 0，与已核对的 source MATCH 对应。未重新运行任何测试或测量。

**结论仍为需修订，F1 未关闭。** handoff 将 `95b1d4b1c4` 描述为修正 fixture、不改拒绝规则，恰好意味着 §1 的错误跨启动卷判等仍在。记录补齐、164 项测试与 source MATCH 均不能解除该代码阻塞。继续暂停缓存准备与 H3，待 F1 修正后的新候选复审；本补核不评价尚未产生的运行结果。
