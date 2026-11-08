# P6 S4 A 独立代码审核与固定执行稿静审

2026-11-08。**累计结论：A GO**（代码、固定脚本及本节 focused 范围）。原代码结论 `CODE_CLEAR_FOR_FOCUSED`、脚本结论 `SCRIPT_CLEAR_FOR_EXECUTION` 的依据保留在下文；本节 GO 不表示权威全量 runner、容器、真实数据、容量、性能或 S4 退出通过。

## 固定对象与范围

- 直接 base：`94b25a32792821cbc5b3230d98a0aa6f13493c32`；A 候选：`fb9c7fbcd95b411d7598ade2a93bc8a7e6514697`。A 原开工点 `8e144b83455d6975499d036fe045308abc6d763e` 到直接 base 的六个 Q18 并行路径不计作 A 审核通过。
- 审核 worktree：`/home/dev/gdds-s4-a-review-fb9c7fbc`，detached 固定候选；`legacy` 链至主仓库并经 `.git/info/exclude` 忽略。起止 `git status --porcelain` 为空。精确 diff 仅六文件：Storage Mutation Contract、A handoff、Mutation Planning contracts、新向量 JSON、测试支持加载器、新向量测试；`git diff --check` 为空。
- 只读依据：AGENTS、testing-conventions、S4 固定设计 `de0eb3a8b2`/kickoff/独审提示、DC96、Storage Mutation/Canonical Storage/Shared Encoding、Business/Operation Lifecycle、Repository Service、ADR0014、Rust/比例化政策，S1a 产品 `7d0ce6220a` 与 handoff/终审，以及实际旧 SQL/schema/Submit consumer、kernel/context、架构导入规则。没有运行测试、编译、lint、构建、容器或节点取证。

## 代码审核

没有阻塞 finding。

1. `StorageTableSideV1` 区分缺侧和存在但零行的显式 Arrow stream/schema；`StorageTableTaskV1` 要求 after 侧具匹配表名、DDL layout 与行数。before 可为 metadata-only，符合强制 rebuild 不读取无用 parent 的设计。`StorageNetCounts` 的非负整数和 `StorageTableSummary.net_counts=None` 区分未算净差与零差；`StorageTableDecision` 分开记录实际 replay INSERT 数。A 未修改通用 `TableMutationSummary`、ChangeSet 或生产路由。
2. `StorageTableOperation` 是同一 M ledger/cancel/N/deadline/resources 的结构 typing view，没有新增预算或初始化路径。A 无 Mutation Planning→Table Access 导入；Storage Projection 及其 native owner 没有改动，不形成 Projection→Mutation 反向环。`test_architecture.py` 的允许上游仍为 Mutation Planning→Storage Projection，冻结 baseline 未放宽。
3. Contract 按完整 persisted canonical IPC、存储键与 JCS key bytes 决定；ordered `gid` 为键、`no` 为值；keyless 保留重复，mutation row digest 与业务 content/SET sequence 域区分。source-only keyed 零差可 NOOP，未读 parent 的 keyless 不伪报净差；重复键/坏绑定/未建模副作用须在 effect 前拒绝。DDL 完整前缀、DML 表/操作顺序、1000/1%、256/4MiB/200MiB 与旧规则一致。
4. 新向量是人工预期，不从新 Rust 输出反填。独核 `.15g` 的指数 -4/15、15 位舍入、float32 `3dcccccd` 扩展、负零，JCS 非 BMP UTF-16 属性序和十进制字符串 key 序，keyless 重复示例、净 diff、1000/1% 阈值、DDL 前缀。DELETE `t` 单键语句的前缀 30B、尾 3B，255/256 行 542/544B，257 行 `[544,34]`；4MiB 恰限 token 4,194,271B，旧连续 256 行窗口交叉期望 `[254,1,1,1]`，手算与旧 renderer 分窗/flush 顺序一致。示例固定 hash 只证明给定 digest 的排序，不冒充真实 row-hash 向量；B 须引用 Shared Kernel encode_row 的实际来源。
5. 六份既有 renderer `expected.sql` 的 SHA256 与 handoff 全部吻合；另三份 package/manifest fixture 与两份 Repository Client 包 SHA 也吻合。`7d0ce6220a..fb9c7fbc` 的 renderer golden 路径无 diff；A 没有修改旧 SQL expected。Client 包只是协议字节锚点，不能当作 S4 Submit 新包的 expected。

**B/C 实现依赖，非 A 阻塞：** 当前 `KernelExecutionContext` 只有 `kernel_execution_scope` 的 ContextVar 与关闭时资源释放，没有可供 Mutation Planning 在保持 DAG 下直接调用的 active/closed 自检方法。B/C 必须由 Table Access owner 提供最小实例自检或等价单向机制，并在 FFI owner 验证实际 active 实例身份、未关闭、已初始化共享池及 N/M 一致；不可把 Protocol 的结构匹配当运行时授权，也不可在 Mutation Planning 偷加 Table Access import 或放宽架构 baseline。之后核取消/截止/预算错误分类、Arrow 最后 owner 和 chunk 结果 charge。A handoff 已将这些列为 B/C 必达，故本轮不以尚未实现的接口行为制造 A finding。

## 05 固定脚本静审

- 最终脚本 `/home/dev/gdds-test-tmp/p6-s4-a-plan/run-focused-05.sh` SHA256 `69cfbd0e2383345fbbc1e79849fb3f37053c56274b3742760250194fc02082fb`；bundle `a-source.bundle` SHA256 `eeb932cff956ff6e37e93d2022931767244bba587735fa55e976d88b3a9e100f`。`git bundle verify` 为 complete history，唯一 HEAD 是 A 候选。初稿脚本 SHA `328cefc8f248b0963ecb67f22eebf230ca128941c16c903be8ea4b186275ac62` 已另存且未执行，不作本次放行对象。
- 脚本固定 05 hostname/root，执行时重核 marker、Docker、8000 与 `/proc` Dolt/Cargo/pytest 等进程；以 `mkdir` 原子占用，标会话/用途/UTC，marker 内 fetch bundle、另建 clean detached WT、link ignored legacy。拒绝节点 main checkout、Rust tree/工具链不符、离线/锁漂移和脏 WT；日志在 WT 外，记录起止 HEAD、入口与最终 exit、SHA，释放本人 marker。
- Rust 源树未变；脚本仍强制重装 backend native 并查 build input；离线同步五包、五包 ruff/mypy，然后按 `not serial or parallel_safe` 与 `serial and not parallel_safe` 两遍选择五个 focused 文件（含架构测试），串行 `-n 0`。固定五文件无 `serial` marker，conftest 不补标记；最终脚本保留该范围的原始 pytest exit 5 和 `serial_scope=empty`，仅此已知空范围可继续，其他非零立即停止。初稿会把预期空范围误作失败，故替换为上述最终 SHA。未混权威全量 runner、Compose 或真实数据；A 当前没有镜像/deployment/container-only 变更，容器门禁延期到最终候选。最终脚本无其他需改字面项；实际节点空闲、缓存及退出结果须由唯一执行者现场取证。
- LAN staging/调用/抓取外层 `/home/dev/gdds-test-tmp/p6-s4-a-plan/execute-focused-05.sh` SHA256 `3fb02267c9bd70ece5fad47bdf0e848569e74d626e9b7dcaec1859bc9e35e1ca` 静审通过：仅以 BatchMode 核 SSH/hostname/marker、建立本任务 staging、SCP 两固定 SHA 输入并远端核 SHA、调用上述 node 脚本，入口非零仍抓原 focused log/SHA 并保留 outer/entry/capture exit。它不在 marker 外执行 fetch、worktree、环境或测试；这几个动作仍归 node 脚本。若 node 在创建自身日志前即前置失败，outer capture 会非零并保存外层原件；不能声称取得不存在的 node log。

## 证据边界与后续

当前 HEAD `fb9c7fbc`；A 触发镜像重建：**no**（仅内部类型、测试/向量、Contract/handoff）；最后验证的 S4 image revision/source-tree：**none**；当前 HEAD 容器门禁：**deferred**，要求 B/C/D 后在 S4 最终候选重建并按权威入口核收。下列 focused 证据仅证明本节 A 固定范围，不能称为权威全量 runner 或 Compose。若修复 A 候选，则在新固定 diff 上连续复审。

### 第一次外层前置失败（待定位，非 focused 结果）

16:50:04Z 外层原始 `/home/dev/gdds-test-tmp/p6-s4-a-plan/controller-fb9c7fbcd9/outer.log` SHA256 `b6f54016876749c92afc393446cdd446f5dc993ee22ef8805c2aa2f01fa75c0d`：本地脚本/bundle SHA 均 OK、SSH 回显 `OK`，随即 `outer_exit=1`。未到 SCP、node 入口、marker、测试或 focused.log；不能把此失败称作 A 产品/测试失败，也不能宣称执行通过。失败点在 SSH 复合前置回显之后，由唯一执行者只读定位 hostname、marker、staging 具体条件；修订稿固定并复审后方可执行。原失败原件保留，不无修改重试。

唯一执行者的只读 `diagnostic.log` SHA256 `6bc3146b13360977d0f47b42665197d2c788cba6af4732bea0af30104e9c532b` 在稍后观察到 hostname/root 与三项 test 均为 0，staging 不存在；诊断命令自身因 `printf --` 与预期缺失路径的 `stat` 退出 1，故不能证明 16:50 瞬时失败的具体根因。协调者固定外层修订 `/home/dev/gdds-test-tmp/p6-s4-a-plan/execute-focused-05-r1.sh` SHA256 `bcc6412fb04e62dd53233047e0cfcd2428924118c26e1380c148c5903a39f67d`：仅使用独立 controller-r1，并将 SSH 复合前置改为逐项具名状态与明确 staging 成功记录；候选、bundle、node 脚本、测试范围均未变。原审核者已静审此精确修订 **SCRIPT_CLEAR_FOR_EXECUTION**。仍不称原根因已查明；后续若再失败按新日志停止与定位。

### 固定 A focused 原件核收

唯一执行者通过上述 r1 外层于 16:55:03Z–16:56:42Z 运行，node 实际 16:55:05Z–16:56:42Z。原始 outer `/home/dev/gdds-test-tmp/p6-s4-a-plan/controller-fb9c7fbcd9-r1/outer.log` SHA256 `fe72ab6072f409e27f40f357e0d87d474e049fbd9d987ae734a04bfeabb6d12c`，其 sidecar 相同；captured `focused.log` SHA256 `94cc44639710f344d02624d397d07de5f9020076e074f2eaaa8af666ba39ecc8`，与远端日志 sidecar 相同。外层本地与远端均核 node 脚本 SHA `69cfbd0e...`、bundle SHA `eeb932cf...` 为 OK；远端具名 hostname/root/marker/staging 前置通过。outer `ssh_node_entry_exit=0`、`capture_exit=0`、`outer_exit=0`。

node 原日志记录起止 HEAD 均 `fb9c7fbcd95b411d7598ade2a93bc8a7e6514697`，结束 status 空。Rust selector `1.97.0`，rustc/cargo/rustfmt/clippy-driver 同一工具链；backend native 强制重装 exit 0，installed build input 与固定 Rust tree `9d4f84ce0897099402226c77c548c487c4912008` 一致。五 Python 包的 ruff、mypy 均逐项 exit 0。固定五文件 `not serial or parallel_safe` 批次 **151 passed、exit 0**；`serial and not parallel_safe` 批次 **151 deselected、原始 pytest exit 5**，按已审空范围规则记 `serial_scope=empty`，没有把普通非零结果吞掉。六锁前后摘要逐一相同，`lock_drift=0`；node `entry_exit=0`、`final_exit=0`、本人 marker file/dir release 均 0。原审核者依据原日志而非协调者摘要核定本节 **A GO**。

唯一执行者于 16:57:20Z 再只读核 05 现场：marker 不存在，无测试进程、8000 listener 或运行容器；固定 worktree 与日志仍保留。该现场核对与 node 原日志的 release 0 一致，不清理他人资源。

16:50 r0 外层失败和只读诊断仍按上节保留；其失败点未查明，未到被测对象，不将其合入成功 focused 样本，也不以 r1 成功倒改原件。A GO 仅覆盖六文件固定 diff 与本节验证；B/C/D 的 native diff/SQL/Submit、所有权释放、真实镜像/Compose 及 E 的权威与真实旅程仍须各自核收。
