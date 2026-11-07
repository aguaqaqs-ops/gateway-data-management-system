# BE-a / 归档核验 / BE-d 联合正式退出工作单

2026-11-07，协调者维护。**Owner 已明确要求“请办理正式退出”**；本次授权涵盖必要的最终绑定、原独审核收、退出记录与本地附注 tag，不包含推送、S3 实施、前端验收或接管原基准。

## 1. 实际起点与角色

- 起点：clean main `c837d281928911867d493994d79fccea07e902d4`；本工作单首次提交作为退出绑定候选 H0，以提交后的完整 SHA 固定、同步和核对，不追逐并行 main。
- 产品/直接权威来源：`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`，`vnext` tree `56720104af34a1eb677336f57bdbc07444a56615`。起点与该产品树相同，但此事实不替代真实闭包比较。
- 联合技术 GO：`ccdd1eb39d8b1c8e80fdbc4157f096595ba6ac5f`，见[原独审 §25](p6-be-d-review.md#25-正式后端联合技术go绑定49403及既定范围)；最终实施 handoff `233e6f788b9b9568664f0e427b45d08bf8d22dec`。
- Owner 已确认的 DC33 范围见[联合记录 §13](p6-be-a-d-joint-validation-preparation.md#13-owner最终dc33范围确认与交接)：05 a999 一次 fresh t1/18步/四完整 tar 的有限步骤引用，加04当前真实接线及原 owner 异常覆盖；不新增 t2/t3/t4 或正式性能测量。
- 继续使用原 D 实施者 `/root/be_d_impl`（GPT-6.1-Sol/xhigh）和原独审者 `/root/be_d_review`（GPT-6.1-Sol/max）；恢复本节收尾职责，不创建新角色、不更换审核者。协调者只维护工作单/状态/交接并办理通过后的本地 tag。
- 实施者负责节点方案、实际绑定及 D handoff；独审者负责独立方案核对、证据复核及 `p6-be-a-d-exit-review.md`，可更新执行计划的退出状态行。根协调文档与审核报告分属各自角色，不交叉提交。

## 2. 最小绑定方案与停止条件

1. 原04节点 BatchMode/现场状态及有效占用核对后，原子取得本人标记；只操作本任务原 gate WT `/home/dev/gdds-test-tmp/wt/p6-be-ad-final-04`。保留来源日志、manifest、镜像及历史失败，不清理他人资源，不占CT108。
2. 固定 H0 后，经具名 ref、完整 SHA 与归档摘要校验的 LAN bundle 同步；在原 WT clean 检出 H0。原技术 GO 后的增量须逐路径核对，不能只看 HEAD 或 `vnext` 摘要。
3. 使用原权威运行的离线环境、工具链、逐包 Hypothesis 路径及 Docker build profile，在同一原 WT 为六包实际生成当前 manifest。四基础包直接对 `run-authority-six-final-DTWWhQP4` 原0来源；backend/RS直接对 `run-authority-resume-mvzi5dNV` 原0来源。解析 compare 的实际 status/changed_components，不能仅按 CLI exit0判沿用，也不链式引用旧 carried 结果。
4. 核对三个 runtime 的不可变 image 身份及原 config/全部 DiffID、RS source/build-input 标签和参与闭包的 custom RS tag 输入，按 AGENTS 镜像身份等价绑定。不得为了本次纯文档候选重建或 retag 镜像；只有规则要求的实际差异才进入相应补验，先交原独审确认影响与执行范围。
5. 日志写原 WT 外的新唯一目录，记录节点、UTC、起止完整 HEAD/clean、原 exit、命令与 SHA。脚本先由原独审静核，执行/等待/资源操作串行；全部测试及 manifest 取证仅在04执行，开发主机只读核对/文档/提交。
6. 任意缓存缺失、身份/来源矛盾或被测运行非0，按仓库停止规则处理；不自行修改闭包政策、忽略自定义 tag、换 WT 凑等价或用重复测量掩盖失败。有效他人占用时只等待/协调，不抢占。

## 3. 审核与退出动作

- 六包比较及容器绑定成立后，原独审核收实际证据、既定 DC33、代码/Contract/golden范围和无剩余 finding，提交独立退出报告。不得把本轮 manifest 绑定写成 H0 又实际重跑了六包或05 fresh t1。
- 最终报告及必要状态同步只能是闭包外的文档增量；原审核对增量路径与闭包建模，必要时在同原 WT 追加最终报告提交的实际绑定。保持可审查的 V/H/报告提交关系，不因报告自身的纯文档提交无限追逐 HEAD。
- 通过后按 Owner 本次明确退出授权，在记录通过结论的审核报告提交上创建本地附注 tag **`p6-be-a-d-exit`**，注释列明产品 V、绑定 H、原技术 GO、直接运行来源、DC33与独立遗留边界；不移动旧 tag，不推送。
- 验证 tag 类型/目标/在 main 上、产品树及工作区状态，落盘交接；只清理本人运行资源并释放本人占用，来源 WT/镜像/证据继续保留。两角色收尾后正常停止，保留历史，不声称销毁。
- FE3b 的同 tar 解析/摘要/OPFS、前端 kickoff 定稿及其阶段验收仍独立；W1/W2和原基准测量仍独立，不把未知值记 PASS。S3 设计细化不等于 S3 实施授权。

## 4. 当前进度

Owner授权已记录；原两角色已恢复收尾。实施者15:51:09Z只读核04可连接、无marker/运行容器/8000，原WT exact49403 clean、legacy正确；这是该时点观察，不是占用或未来空闲证明。实际 claim、H0同步、manifest比较、镜像绑定、最终独审及tag尚待执行。
