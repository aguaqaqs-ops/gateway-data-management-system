# S3 B：DC68 执行停止与恢复工作单

2026-11-07；状态：**执行已停止，待 Owner 决定恢复**。本单不授权第三次执行，不是 B 产品 GO。A 已独立 GO；B 代码静态修订和临时差分准备可继续，依赖新运行的验证及 C–E 放行不可预记完成。

## 1. 具体场景与影响

固定 Rust 检查点 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 已经 LAN 同步到 06 的 clean detached WT：

`/home/dev/gdds-test-tmp/p6-s3-b-test-9b34be7356a9/wt/subject`

目录名中的 9b34 是本节先前运行的路径，当前 HEAD 实际为 b917；这不是身份冲突。待执行的三步为 `cargo fmt --all --check`、`cargo clippy -p gateway-compute-core --locked --offline --all-targets -- -D warnings`、`cargo test -p gateway-compute-core --locked --offline comparison::standard::tests`（8 个 case）。它们均**尚未启动**；没有 backend sync、真实数据或容器运行。

测试者在脚本已保存之后追加可选源码检查：第一次调用节点没有的 `rg`，exit127；一次修正尝试又因 shell 引用错误将 `WT/LOG/EXPECTED/run_step` 解释为命令并出现未闭合双引号，仍 exit127。依据 [AGENTS DC68](../../../../../AGENTS.md)：“重做再次失败……均停止交 owner”。本次已经停止，不能由协调者换人、换模型或第三次试命令绕过。

两次错误均在测试前；它们不证明产品失败或成功。当前 B Rust 最近一次实际结果仍是 **9b34 fmt0、clippy101、cargo test 未运行**，不能用已修源代码推定通过。B 的预算第二轮修订另行追踪，不将本次执行错误混为产品预算修复轮。

## 2. 保留证据

06 目录：`/home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/`。

| 原件 | SHA256 / 状态 |
| --- | --- |
| `run-rust-focused.sh` | `841e85777ed758fe85e2de4ebf4225985ea81efa44e1b19c7db872515b68ca1b`；已保存，未执行；包含完整三步 argv、起止 HEAD/UTC、原 exit 与六锁检查 |
| `pre-run-command-errors.log` | `60e8fc6c95ef2d677cb70babc7a6e64e4545d5c917a358071b99b39dbc21d3b0`；两失败的事后综合摘要，**不是完整原始 argv/输出日志**；原工具会话保留，不能冒称现场逐命令原件 |
| `marker-release.log` | `896fdef8270870edcf874ed51171a2c0a4d9906f1123c45c38a37a2d1a6e229d`；2026-11-07 **18:55:38Z** 释放本人标记 |

b917 source bundle SHA256=`e941a202e7bec91e2294899ee6bd3699d1bcba9ebab0c11d63c8d5574aec9372`。原审已在 06 只读核脚本/侧车/错误摘要/release 的 SHA、WT clean/HEAD=b917、marker absent，以及没有 `rust-focused.log` 或测试输出。没有自动重试。

9b34 实际编译失败原件继续保留在 `.../p6-s3-b-test-9b34be7356a9/logs/rust-focused.log`，SHA256=`c0eecef9412e267f98cef536d91025af4c5209db77ace24f790de27349fc8d6f`。完整停止复核由原 [B 独审报告](p6-s3-b-review.md)维护。

## 3. 推荐的最小恢复稿（未执行）

Owner 如明确允许恢复，本轮不再添加 `rg/grep` 源码检查或嵌套 shell 引用生成；不改产品、不放宽断言、不改 expected、不重造环境框架。

1. 唯一执行者按 AGENTS 现场核 06 空闲、原子取得本人标记，确认原 WT clean/HEAD=b917、六锁/工具链及离线前提，原失败与 WT 保留。
2. 以普通只读 SHA 检查确认已保存脚本仍为上表 `841e…ca1b`，然后直接启动现有脚本；外层获取原 SSH/script exit，不用额外命令包裹或修改测试选择。

   ```bash
   ssh -o BatchMode=yes ct107-gw-dms-06 'bash /home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/run-rust-focused.sh'
   ```

3. 首个实际失败即停止后续、保留原日志和 SHA，不能自动重试。正常结束或失败收尾后释放本人标记。该次仍仅是 B 检查点反馈；B 完整候选、差分、真实数据逐表和后续门禁按原授权另行固定，不冒称 b917 是最终 B。

## 4. 需要 Owner 决定

- **推荐：**确认停止复核和上述最小恢复稿后，允许恢复 06 的这次检查点及既有授权范围内后续验证；本次例外不取消未来失败停止规则。
- 或保持测试暂停，只推进不依赖测试的静态代码/文档，待另行决定。

这里请求决定的唯一原因是已触发 AGENTS 的明确停止条件，不是重新申请 B 开工、依赖或日常节点窗口。预算第二轮、JCS/记录接口及最终 DC33 范围仍按各自规则处理，均未记通过。
