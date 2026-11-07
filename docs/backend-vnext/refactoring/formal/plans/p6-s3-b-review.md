# Phase 6 S3 B 独立审核

**状态：审核进行中，B 尚无最终候选。** 固定 Rust 检查点 `3577df182d6481a9c6e49554e445c81071924c09` 为原始问题来源，`a4ff75362737ec4a6e15a2cb6f1ace836ea26657` 为第一轮实质修订；`9b34be7356a92228ef07ee0c4f01bf215e2bf653` 与 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 为机械格式检查点，不单独计修订轮。完整 B 仍待 Python 临时差分、随机 batch/N 和 t1–t4 按表差分。此页记录已核静态边界与 06 取证停止，不给 GO，也不把旧镜像结果写成当前通过。

## 1. 固定对象与方法

设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`、kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` §5 已 READY；A 独审 `f28c89eff5ac1e653facb21229c3b5a7d281f971` 最终 GO，A 无剩余 finding。依据 AGENTS、testing conventions、比例化/Rust 政策、S3 设计/kickoff、A handoff 与 Comparison/Ordered Diff/Risk、Shared Canonical Encoding、Canonical Storage、Snapshot Table Access owning Contract，并对照固定 A/旧 Python 生产实现。未重开已关闭的 kickoff 设计。

本人在 `/home/dev/gdds-s3-b-review-3577df18` 和 `/home/dev/gdds-s3-b-review-a4ff7536` 两个新建 detached worktree 只读审核，均固定 HEAD、tracked clean、链接 `legacy/`。a4ff 的 `vnext` tree 为 `de98b3fcedc713e88a0798a1357503e081560a5e`。开发主机和审核 worktree 未运行编译、lint、测试、容器或性能测量。

## 2. 当前静态核点

3577 的 ordered 入口沿用全值 Vec、零 batch 缺 schema、索引/LIS/摘要缺控制检查、scratch charge 留至结果 Drop 且部分 record 在分配后才预约。a4ff 已实际改为三族 locator + Arrow Arc owner、显式 schema 的零/N batch、索引/LIS/gap/digest 控制检查、scratch `shrink_to` 与增长前 record 预约；单侧 compare 任务明确拒绝交 Python 表级 metadata owner。固定 Python 的整表新增/删除不产生逐行 records，不能拿旧 Rust 原型的单侧行为作预期。

下一固定修订仍须核以下具体边界，现不把 a4ff 记为最终失败或通过：

- **预算同一根因：** a4ff 仍逐 batch 累加 `get_buffer_memory_size()` 再按倍数预约；Arrow 59.1.0 `arrow-data/src/data.rs` 明确共享底层 Buffer 的各 slice 均报告完整容量，随机切分同一 backing 可使同数据/同 M 虚假拒绝。`ordered_retained_bytes` 在结果构建后再 `serde_json::to_vec` 和 `shrink_to(retained)`，当 retained 超初始 lease 时事后 `grow`；零行宽 schema 是具体边界。下一预算实质修订为第二轮；若同一 M 不变量仍未解决，停止受影响 B 预算 GO 并报具体阻塞，不用格式检查点重置轮次。
- **流式 JCS 数字：** a4ff `ordered_digest` 直接写 `row.position.to_string()`；固定 Python 与旧 Rust JCS 均拒绝大于 `2^53-1` 的整数，`no=2^53` 在 Int64 中可表示。新流式路径必须保持原失败边界，并对数字写入作最小校验。
- **facts 消费：**正常 ordered 的三族记录在 locators、`facts.records` 为空；退化则 `facts.records` 有 `TABLE_DEGRADED`、locators 为空。C 的完整 table/core payload 必须合并这两支并从未裁剪值重放，不可直接序列化小型 `facts` 或拼 table hash。Blank 私有 `entity_key_kind` 仍属 facts，不进 Parquet。B/C handoff 需把双支消费规则说清并用旧生产退化结果差分。
- **编码依赖的 metadata：**a4ff 会核物理类型，但 Utf8 的 `sql_type=DECIMAL(10,0)` 与 `declared_type.kind=string` 冲突仍可通过并按 decimal 编码。真实 S2b owner 生成一致 metadata；B 只需对自身编码实际依赖的冲突作最小失败检查，不复制整套 IPC 校验矩阵。

已静态对照的正向语义包括 keyless occurrence 0/后续域与 minimal ULEB、SET Utf8 的声明序 sequence frame、ordered 绝对 `no`/LIS 并列/blank gap 锚与排序。它们仍待完整固定向量和差分原件核收。B 新入口不得成为生产 flag/fallback；旧 Vec 原型及临时 Python 差分仅替换期测试使用，E 按清单删除。C 的三族 Arrow builder/JCS writer-reader、D 的风险/去重/生产路由不提前要求 B 实现。

## 3. 06 执行稿的 DC68 停止复核

本人先用 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'` 确认连接，再只读核 `/home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/` 原件。`pre-run-command-errors.log` 现场 SHA256 为 `60e8fc6c95ef2d677cb70babc7a6e64e4545d5c917a358071b99b39dbc21d3b0`，记录第一次可选只读检查因节点无 `rg` 返回 127；第二次改用 `grep` 时 shell 引用错误，把 `WT`/`LOG`/`EXPECTED`/`run_step` 当命令并产生引号 EOF，再返 127。此汇总日志保存了两次错误的 stderr/exit 与作用范围，但没有独立逐字的两次原始 argv，不能据此复原完整命令行。

待执行 `run-rust-focused.sh` 现场和侧车 SHA256 均为 `841e85777ed758fe85e2de4ebf4225985ea81efa44e1b19c7db872515b68ca1b`；脚本本体含固定 HEAD/clean/六锁/离线/toolchain 前后检查、fmt → core clippy → focused tests 首错停。脚本引用的 worktree 路径虽含旧 `9b34` 目录名，现场 HEAD 为 `b91767f5d794701cfebb49b83b64cf5a7130c09a` 且 clean，不能把目录名误判为错误 HEAD。该次证据目录没有 `rust-focused.log` 或测试输出；`marker-release.log` SHA256=`896fdef8270870edcf874ed51171a2c0a4d9906f1123c45c38a37a2d1a6e229d`，记录 06 主机 18:55:38Z 因连续自身命令错误在测试前释放占用。现场占用目录不存在。两次失败均在被测对象运行前，但已重复，按 DC68 停止；本人没有作第三次预检或启动任何测试。此节仅裁定执行停止，不评价 B 代码 GO，也不计作产品预算修复轮。

**最小恢复执行稿建议：**保留两次失败文件与 SHA；Owner 对 DC68 恢复作决定后，测试者重新原子取得 06 占用，核固定 b917 worktree clean/六锁/离线缓存；删去可选 `rg`/`grep` 源码检查与嵌套 shell 引用，按字面执行 `bash /home/dev/gdds-test-tmp/p6-s3-b-test-b91767f5d794/logs/run-rust-focused.sh` 一次。首个被测步骤失败即停，记录 hostname、起止 HEAD/time、各步 exit、最终 exit 与日志 SHA。若候选源码已另修，则先固定新 SHA、使用对应 clean worktree 和新脚本，不把 b917 结果沿用到新树。此建议不授权在 Owner 决定前重试。

## 4. 容器与后续证据

本轮受审固定 HEAD=`a4ff75362737ec4a6e15a2cb6f1ace836ea26657`；`gateway-compute-core/Cargo.toml` 将已锁 `sha2` 从 dev 移至 regular dependency，且 Rust product tree 变化，**触发**当前产品镜像重建判定。workspace 版本仍精确 `=0.11.0`，Cargo.lock 未随 a4ff 变化；06 离线构建命中待测试者实际日志核。B 不接生产路由，当前容器验证延期到 E 最终固定 HEAD 在 04 的集中门禁，不能称 a4ff/b917 已 PASS 或 carried。最近既有已验证 image revision=`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`、source tree=`56720104af34a1eb677336f57bdbc07444a56615`，仅为 BE-a/d 历史基准。

完整 B 候选还须有 06 clean 已提交 worktree 的 fixed/property/旧生产临时差分、随机 batch/允许 N 确定性、预算/取消/截止与 t1–t4 v1/v2 按表差分；八个输入 SHA 须逐包对照 `datasets.json` 与 P5 S4 handoff §8，旧 expected 来自 Contract/A/冻结 Python。B 不跑完整真实旅程、04 runner/carried、Compose 或 CT108 正式性能；这些留后续阶段对应节点。最终独审需核原始日志/脚本/摘要与手册边界后再给 GO 或明确 finding。
