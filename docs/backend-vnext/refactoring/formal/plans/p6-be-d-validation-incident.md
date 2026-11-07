# BE-d 06验证编排事件与恢复方案

2026-11-07；协调者维护。**Owner现已明确回复“按方案恢复验证”**，允许按本页已静审guard恢复D及此前授权的联合准备验证；实际新run结果随后记录，D产品尚未GO。先前因已跑旧对象/覆盖原日志按[AGENTS DC68](/home/dev/gateway-data-management-system/AGENTS.md)停止的事实和限制全部保留，恢复不追认旧证据。

## 1. 已确认事实与影响

- 目标为`a7954b6b55`的源码bundle用纯SHA创建，被Git拒为empty；调用缺fail-fast，仍传旧bundle并启动旧候选focused。
- 实际测试WT为06 `/home/dev/gdds-test-tmp/wt/p6-be-d`，起止均`aaa0f4a6f32143448c1b55bb1cc8f509643e1d3c`、clean。11:17:02–11:17:18误跑为150pass/2fail、exit1，现存原log SHA=`f882a86a8a0e472b80fa2897e61a1ffc4237a1cee9a3a73ffd8526780bedb9c5`。它只作旧候选诊断，不是a795或当前候选证据。
- 同HEAD日志命名使aaa首轮ruff/mypy/focused原文件被覆盖。独审明确没有副本；首focused的历史SHA=`2345ec835d433ff55a548697c0faeebc67ff8cbb8779b27d35b98c23b14a3cc2`不能代替原字节，相关首轮来源不可独立复核，不重造或拼接记录冒充恢复。现存误跑ruff/mypy原log仍保全，但不将其冒称首轮文件。
- 两次更早checkout失败属于不同候选传输步骤（FETCH_HEAD、错误literal SHA），均在当次被测对象前、完整SHA纠正后才运行；失败秒级UTC未记，仅有相邻原log的时间界定。`checkout-*-operation-error.log`为工具输出整理的派生说明，从未有原命令外置log；不称原执行原字节仍在。详见固定handoff547a§6。
- 属非权威focused运行；尚未运行D当前Compose、04权威或05 fresh t1，未改冻结基准/他人资源。e3/7f等仍有原字节的历史来源按原报告保留；不因此抹去本次事故或宣称完整D通过。

## 2. 保全与节点收尾

06保全目录：`/home/dev/gdds-test-tmp/artifacts/p6-be-d/incident-preservation-rvpm66sO/`，含现存全部log/script/bundle和actual HEAD/status/进程/容器/8000现场；本地完整副本：[保全索引](/home/dev/gdds-reviews/artifacts/p6-be-d/incident-preservation-rvpm66sO/SHA256SUMS)。该SHA256SUMS自身摘要=`78122ba8b893b200c17ad9ae959af5fa7d25cc830f59986043f2b40298ca065b`，协调已核本地副本，独审另核现存误跑原文/实际SHA。

06于**11:19:30Z**核本人marker后释放：无本任务Dolt/Cargo/pytest/运行容器或8000监听，WT仍aaa/clean，文件和镜像保留。`node-release-UzrHOQAs.log` SHA=`de06e368c6459639f0f04525cdb6a9763edaa30e85eb3e8ff6a21b97422b8ae8`，协调已只读核原log。释放不是后续预约；恢复时重新核现场/原子获取。

## 3. 已固定并静审核收的最小修正

1. 使用标准失败即停（shell `set -euo pipefail`或等效严格subprocess返回码检查），bundle创建失败时不传输、不checkout、不运行。
2. 从指向目标commit的named HEAD/ref创建bundle，创建与接收端verify；使用明确完整SHA，运行入口硬断言actual HEAD=expected、worktree clean，保留legacy/offline/资源前提。
3. 每次运行创建唯一WT外run目录，日志不复用同HEAD文件名；捕获原始exit、host、起止UTC/HEAD和SHA，失败留存。沿标准文件/目录和现有脚本，不建立durable evidence状态机或新平台。
4. 固定handoff **`547a38903456aa6e8799c348c66724d1fd068fb5`**、同角色恢复静审 **`da45bb7b0f`**（[报告§10](p6-be-d-review.md)）：技术方案可接受，供Owner决定，不是恢复授权、脚本运行通过或D GO。两脚本未执行，未bash-n，未运行任何被测对象。

| 固定脚本 | SHA256 |
| --- | --- |
| [source transfer](/home/dev/gdds-be-d-guarded-transfer.sh)，副本`/home/dev/gdds-reviews/artifacts/p6-be-d/guarded-transfer.sh` | `f83066c0b15a012bf5df673577591910e5b0afd4926553d4f3592ef5edff9d4d` |
| [node run](/home/dev/gdds-be-d-guarded-node-run.sh)，同目录副本`guarded-node-run.sh` | `4eb10c9fc1a8b3b12d4b5ae4cba4d54528d7462d7a5a8f91549facb0e7c979b2` |

独审已重算原/副本完整SHA、40保全文件及释放记录，核source-a795.bundle实际advertise旧aaa。node-run末尾再次核本人marker，不匹配时保留原command_exit且final_exit=2；明确mode664以`bash <file>`运行，node-run单独LAN复制到06固定路径并核SHA，不能用`bash -s`破坏`$0`归档。具体入口见handoff§6，不创建新框架。

已静审产品树 **`e7dfe478e5abb721a4f968dd692380b3cb05f28f`**（含18b路径冲突修正、445测试文案、7c未运行interop生成器）；后续只追加审核/决定文档。恢复时协调先固定clean实际完整HEAD并核其vnext tree等于此树，再由named HEAD bundle/接收端/运行前后同一expected SHA硬断言，不能将旧SHA硬套已前移的main。

Owner未回复前不启动任何受影响测试、lint/编译、Compose或04/05后续验证。证据保全/本人资源收尾、独立静审与无关产品修正可继续。

## 4. Owner已批准的恢复边界

推荐：在上述调用修正固定且独审核收后，以新的唯一run对最终正确候选实际运行D受影响focused/所选serial、五包静态/扩展input及必要当前小Compose/encoder制品；缺失aaa来源与误跑结果排除出当前通过依据，事件保留；后续继续既有D/联合最终准备授权。普通产品失败仍按原定向修复，若再出现编排/身份/日志保全异常则立即停交Owner。

**Owner在恢复问题后明确回复“- 按方案恢复验证”**，恢复授权现已生效；不再重复询问本次恢复。协调已核main clean、vnext仍为`e7dfe478e5abb721a4f968dd692380b3cb05f28f`，两guard原文SHA与已审值相同。先提交本授权记录，再固定其clean实际完整HEAD供传输/节点/每run同SHA硬断言；短暂源码传输窗口内不并行提交main，传输完成后可继续独立文档/审查。

恢复先重新现场核空闲/原子获取06占用，以唯一run实际核正确候选所需证据，不复用缺失来源；此后沿原D/联合准备授权推进。本决定只涉及恢复验证，不代表D验收、FE3互通、DC33退出范围确认、tag/push或S3授权。若再有编排/身份/保全异常仍按本页停止规则报告Owner，普通产品失败按既定定向修复。
