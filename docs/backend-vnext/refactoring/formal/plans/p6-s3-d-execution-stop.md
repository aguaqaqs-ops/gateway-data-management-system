# Phase 6 S3 D 取证停止与最小恢复稿

2026-11-08；状态：**D 执行通道暂停，待同一独审核本稿后交 Owner 决定。静态实施和审核继续，尚无 D GO。** C 已由 `ce217c0ad77783a4a3c0eba3f0033bce356aaa3c` §19 独审核收。本次不是 C 恢复决定的追加豁免。

## 1. 固定对象与产品结果

首次执行对象为 D 检查点 `f000e5b075408455a35e8ae3dededc28036c73c6`。同一测试者 `/root/s3_d_test` 在 06 的本任务 clean detached WT 执行已审 Rust fmt → clippy 稿。实际于 **03:36:30Z** `cargo fmt --all --check` exit1，`comparison_records.rs` 有十处格式差异；**clippy 未启动**，没有 Rust test、backend focused 或容器运行。起止 HEAD=f000/clean，六锁无漂移。此次产品格式反馈须由实施者修订新候选，不能记通过或重跑旧候选掩盖。

该轮记录位于节点及 CT201 的 `/home/dev/gdds-test-tmp/p6-s3-d-f000e5b075/`；日志在 `logs/`，脚本在 `scripts/`。实际 run 原件及其本地副本 `logs/remote-run-focused.log` 的 SHA256 均为 `6bd909e6ceeca3b168a078b0544c4a3e276be380de6c5895543ecc5a7a7a483c`。source bundle SHA256=`987b71b0c9ca23dd7d55a7fb364cb6e62c54bb06341c705d5f71a82bb055f4d3`。

后续产品集中修订已固定为 `5c47795062937a8db0315640a95ab763d2c2c8ab`，由原审核者在 detached WT 静态复审。它尚无编译、测试或容器结果。main 中其后的个人 WIP 和并行文档不自动纳入固定对象。

## 2. 两次取证错误与停止依据

06 postflight 自身 SSH exit0，本人占用标记于 **03:36:56Z** 已释放；未留本任务进程、容器或 8000 服务。以下错误均发生在日志抓取/比较阶段，不能改写为产品算法失败，也不能覆盖其外层 exit1。

| 步骤与原件 | 原始结果与限制 | SHA256 |
| --- | --- | --- |
| `scripts/postflight-release.sh` | 本地外层 exit1；把 `PREP_LOG_SHA256=<hash>` 整串与纯本地 hash 比较，假报不等。远端收尾本身 exit0。 | 脚本 `e9a9b88c856113d334df7e058419bee259fe89008c5a37b3e2c3aca2e26f5117` |
| `logs/postflight-release.log` | 首次外层失败完整记录。 | `62ee3e96122640a974d304534de5e97ecca1e845dc46477107f0453f3c586164` |
| `logs/postflight-release-ssh.stdout.log` | 已成功远端 postflight 的原始输出。 | `0a39b386fb5978eee2d637e6cff76bc7411bdc1b0d31474211435aa5f49d6f91` |
| `logs/remote-prepare-node.log` | 已复制的 node 准备日志；其纯 hash 与远端记录相同，不改变首次外层失败。 | `50479890f5832bfe2ee3838402de6d038f5d3395c20f6d0563f209370a6c407c` |
| 03:38:20Z 的一次修正抓取 | inline `exec_command`，SCP exit0；又把 `RUN_LOG_SHA256=<hash>` 与纯 hash 比较，外层再次 exit1。组合 stdout 没有独立落盘，**没有该组合日志 SHA**；不能事后誊录为实时完整原件。 | 不适用 |
| `logs/capture-run-log.stdout.log` | 第二次 SCP 本身的空 stdout 文件；不是上述组合 stdout 或整个失败记录。 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

第二次工具原返回明确含 `SCP_EXIT=0`、`REMOTE_SHA=RUN_LOG_SHA256=6bd909…a483c`、`LOCAL_SHA=6bd909…a483c`，且工具数值 exit1。两次同根因为人类标签输出的自定义提取保留了前缀。原审核者曾再做纯本地对比后表示 CLEAR，现已撤回其作为恢复依据的结论：该动作只能佐证文件内容相同，**不能把两次外层失败关闭为成功或恢复通道**。不再追加 f000 补验。

[AGENTS.md DC68](../../../../../AGENTS.md) 原文：“**重做再次失败、被测对象已运行后的失败、缓存缺失或身份不符均停止交 owner**”。本次同类取证错误修正一次又失败，因此暂停后续测试、编译、native 重装、容器、缓存/镜像准备及取证补验；不以换角色、换节点或 C 的旧许可绕过。原失败、未知记录和现有文件均保留。静态代码、文档与固定对象审核可以继续。

## 3. 最小恢复执行稿（尚未执行）

建议仅恢复本次受影响的 D 执行通道，由同一测试者和同一审核者继续。无需第三次 f000 SHA 比较，也不重跑旧 f000 fmt。已有证据按 §1–2 的真实失败和限制交接。

后续新候选的日志传输采用标准 `sha256sum` 文件清单，移除 `FIELD=hash`/AWK 人类输出解析：

1. 同一原审核者先核固定新候选和全部字面执行稿，明确 HEAD、源/节点新 WT、日志目录及适用 focused 范围。若候选继续修订，先重新固定和快核这些绑定，再执行；此条件不授予跳过审核或重复旧失败的权利。
2. 节点仍按 BatchMode、现场占用/服务核查及原子本人标记获取规则。源 clean detached WT 使用字面 `HEAD` 完整 bundle；新的被测 WT 保持 clean，legacy 链接、工具链、离线缓存、扩展 input、jobs4/pytest4 及 M/N 保持现有规则。原 f000 与 C/原基准的 WT、镜像、卷和日志不改动。
3. 每个运行仍记录 hostname、起止 UTC/HEAD、每步 argv/cwd/原始 exit、完整 stdout/stderr、锁与资源收尾；首失败停止后续被测步骤。一次外部总日志可承载这些信息，不增加逐命令独立日志要求。
4. 在节点的运行日志**全部关闭后**，于该任务 `logs/` 执行标准清单生成，例如 `sha256sum -- ./*.log > artifacts.sha256`。预先拒绝覆盖清单，要求预期 run 日志存在；清单不摘要自身。生成命令及原始 exit 在外层收据记录，不能把失败吞成 0。
5. 经 LAN 复制这些已关闭日志与 `artifacts.sha256` 至任务自有的**新本地捕获目录**，在该目录以 `sha256sum --check artifacts.sha256` 一次核对。保留该命令的原 stdout/stderr/exit；不提取带标签 hash。捕获回执位于清单目录外，避免自引用。失败仍停止，不自动重试。
6. 独审核真实分项结果和证据；保留原始失败，不更新 golden、放宽断言或用逻辑相等掩盖 raw 差异。收尾仅释放本人标记。后续 DC68、缓存/身份、runner 非0及其他停止条件全部继续有效。

上述是已发生日志抓取故障的最小 shell 修订，不引入产品持久 evidence 机制。具体捕获模板与新候选脚本由同一测试者仅写入、不执行，原审核者静态核收后才可用于本恢复稿；Owner 决定前仍不运行。标准清单不追补或改写 f000 原始记录。

字面捕获模板已仅写入 CT201 `/home/dev/gdds-test-tmp/p6-s3-d-capture-template/capture-artifacts.sh`，静态文件 SHA256=`1c8dd8c56518499dd98f2506333451d122f85f6bf525a757864534e0a6e2aa23`。调用参数为 node alias、专用远端 logs 目录、全新本地捕获目录、逐项日志 basename；总收据写在 `${LOCAL_CAPTURE_DIR}.capture.log`，目录和收据均预先拒覆盖，避免 SCP 覆盖活动收据。脚本没有执行，没有触节点或追加 f000 比对；该 SHA 仅固定新稿身份。实际新候选完整字面执行稿仍按第1项先由原审核者绑定后再执行。

## 4. 影响、选项与待决定事项

受影响的是 D 动态验证及其后续依赖验收；D 代码静态修订/独审继续，E 的静态删除清单和交接准备不需要冒充 D 已 GO。S3 当前仍无最终产品 V/H、集中 runner/镜像结果、真实数据/DC33 或 W3/W4 达标结论。

推荐 Owner 在同一独审核收本稿后，允许按 §3 恢复；另一个选项是保持执行暂停，只继续静态工作。需要的决定仅为这次执行通道恢复，**不改变冻结语义、Contract/golden、N1/M24GiB、节点用途、DC33、正式退出/tag/push 边界**。独审结论由原审核者维护 [D review](p6-s3-d-review.md)，协调者和实施者不代签。
