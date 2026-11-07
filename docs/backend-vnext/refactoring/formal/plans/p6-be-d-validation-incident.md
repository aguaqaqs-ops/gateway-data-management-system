# BE-d 06验证编排事件与恢复方案

2026-11-07；协调者维护。当前受影响节点执行暂停，等待可审查guard修正、同一独审核收及Owner恢复决定；D产品尚未GO。依据[AGENTS DC68](/home/dev/gateway-data-management-system/AGENTS.md)和[独审§9](p6-be-d-review.md)：已跑旧被测对象且覆盖原日志，不适用产品执行前操作错误的直接重做例外。

## 1. 已确认事实与影响

- 目标为`a7954b6b55`的源码bundle用纯SHA创建，被Git拒为empty；调用缺fail-fast，仍传旧bundle并启动旧候选focused。
- 实际测试WT为06 `/home/dev/gdds-test-tmp/wt/p6-be-d`，起止均`aaa0f4a6f32143448c1b55bb1cc8f509643e1d3c`、clean。11:17:02–11:17:18误跑为150pass/2fail、exit1，现存原log SHA=`f882a86a8a0e472b80fa2897e61a1ffc4237a1cee9a3a73ffd8526780bedb9c5`。它只作旧候选诊断，不是a795或当前候选证据。
- 同HEAD日志命名使aaa首轮ruff/mypy/focused原文件被覆盖。独审明确没有副本；首focused的历史SHA=`2345ec835d433ff55a548697c0faeebc67ff8cbb8779b27d35b98c23b14a3cc2`不能代替原字节，相关首轮来源不可独立复核，不重造或拼接记录冒充恢复。现存误跑ruff/mypy原log仍保全，但不将其冒称首轮文件。
- 属非权威focused运行；尚未运行D当前Compose、04权威或05 fresh t1，未改冻结基准/他人资源。e3/7f等仍有原字节的历史来源按原报告保留；不因此抹去本次事故或宣称完整D通过。

## 2. 保全与节点收尾

06保全目录：`/home/dev/gdds-test-tmp/artifacts/p6-be-d/incident-preservation-rvpm66sO/`，含现存全部log/script/bundle和actual HEAD/status/进程/容器/8000现场；本地完整副本：[保全索引](/home/dev/gdds-reviews/artifacts/p6-be-d/incident-preservation-rvpm66sO/SHA256SUMS)。该SHA256SUMS自身摘要=`78122ba8b893b200c17ad9ae959af5fa7d25cc830f59986043f2b40298ca065b`，协调已核本地副本，独审另核现存误跑原文/实际SHA。

06于**11:19:30Z**核本人marker后释放：无本任务Dolt/Cargo/pytest/运行容器或8000监听，WT仍aaa/clean，文件和镜像保留。`node-release-UzrHOQAs.log` SHA=`de06e368c6459639f0f04525cdb6a9763edaa30e85eb3e8ff6a21b97422b8ae8`，协调已只读核原log。释放不是后续预约；恢复时重新核现场/原子获取。

## 3. 最小修正（待固定静审核收）

1. 使用标准失败即停（shell `set -euo pipefail`或等效严格subprocess返回码检查），bundle创建失败时不传输、不checkout、不运行。
2. 从指向目标commit的named HEAD/ref创建bundle，创建与接收端verify；使用明确完整SHA，运行入口硬断言actual HEAD=expected、worktree clean，保留legacy/offline/资源前提。
3. 每次运行创建唯一WT外run目录，日志不复用同HEAD文件名；捕获原始exit、host、起止UTC/HEAD和SHA，失败留存。沿标准文件/目录和现有脚本，不建立durable evidence状态机或新平台。
4. 修正脚本、目标候选、传输/运行命令由原独审只读核收后列于此页，交Owner决定恢复；未获回复前不启动任何受影响测试、lint/编译、Compose或04/05后续验证。证据保全/本人资源收尾、独立静审与无关产品修正可继续。

## 4. 待Owner决定的恢复边界

推荐：在上述调用修正固定且独审核收后，以新的唯一run对最终正确候选实际运行D受影响focused/所选serial、五包静态/扩展input及必要当前小Compose/encoder制品；缺失aaa来源与误跑结果排除出当前通过依据，事件保留；后续继续既有D/联合最终准备授权。普通产品失败仍按原定向修复，若再出现编排/身份/日志保全异常则立即停交Owner。

最终脚本/静审提交及具体恢复候选尚待补齐，**当前未请求或收到恢复批准**。本决定只涉及恢复验证，不代表D验收、FE3互通、DC33退出范围确认、tag/push或S3授权。
