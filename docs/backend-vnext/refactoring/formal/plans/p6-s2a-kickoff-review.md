# Phase 6 S2a kickoff 审核

- 结论：**kickoff 可以确认，有三处调整（第 2 节）**。第 3 节列出 owner 需确认的五项，均附建议。05 编码前基线的四项失败是调试环境准备缺漏，按第 4 节补齐后续跑，不需要 owner 另行决定。
- 日期：2026-10-31。
- 对象：`p6-s2a` 上的 kickoff 提交 `30de9c1cae`，父提交为 merge commit `49d0846d86`；只新增 `p6-s2a-kickoff.md`（145 行），worktree clean。
- 依据：设计 §7、§16；执行计划 S2a、S2b、S6；DC46、DC47、DC50、DC52、DC55 第 4 项、DC62、DC63 第 3 项、DC64、DC66–DC71（含 DC70 补充）。

## 1. 总体评价

- 分支起点正确（DC71 第 2 项）。S1b 冻结语义、诊断码与偏移的边界写得清楚；对“发现新的参照行为不符先交 owner，不借对齐 Python 扩大语义”的约束合适。
- §3 的旧实现删除清单与 DC52、设计 §7 逐项对应，并区分了应保留的独立能力（`comparison/`、`table_access/`、`records.rs`、ArtifactStore 等）。
- 五层语料、测试归属表、镜像与 dependency-base 流程、节点占用约定与 DC64 证据顺序都与现行决议一致。

## 2. 需要调整的三处

1. **AGENTS.md 与 testing-conventions.md 不由 S2a 直接修改。** §3 末行把它们列为 S2a 同步更新的对象。这两份文件由治理会话维护（backend 镜像依赖层任务的先例）。S2a 在 handoff 中写出建议条文，由治理会话同步。执行计划的路径清单同样只在 handoff 中提出，在 exit 时由审核会话按 owner 决定更新。设计文档 §2.2 的事实描述与被删除的 Contract、ADR 链接可以由 S2a 修改。
2. **worker 级共享线程池分两步。** DC47 第 5、7 项要求每个 worker 进程在启动时按固定 N 建一个池，N 与 M 作为部署配置开放；执行计划把“N/M 准入与 pyarrow 线程池”列在 S2b。S2a 中生产路径不调用 Rust，提前接入 worker 启动配置没有使用方。建议：
   - S2a 在 adapter 中实现进程内共享的有界池：一次创建、固定 N、所有调用复用，不在每次调用时新建；N 由调用方传入，测试默认 N=1，一致性测试比较 1 与 N。
   - worker bootstrap 的接线与部署配置 N、M 在 S2b 随生产切换完成。
   - §5 测试归属表中“每 worker 一个共享池”的 owner 相应改为 adapter 层的池复用测试，worker 启动接线的 owner 测试在 S2b 建立。
3. **O2 单独成提交，放在 Rust 工作之前。** O2 不是新语义：DC62 第 2 项 e 已经决定拒绝非有限值，`1e400` 经 `json.loads` 溢出为 inf 是参照实现对既有规则的遗漏，MySQL 同样拒绝这个值。按 DC50“S2a 不同时改语义和换实现”的意图，先在 Python 参照实现中单独修正（复用现有 reject 参数表加用例），再让 Rust 实现对齐；第 ④ 层差分记录真实数据中这类值的出现次数（预期为 0）。

## 3. owner 确认项与建议

| # | 事项 | 建议 |
| --- | --- | --- |
| 1 | O2：JSON 数值解码后非有限（含 `1e400` 溢出）的处理 | 按 kickoff 建议，表级 `SQL_VALUE_ILLEGAL` 拒绝，作为 DC62 第 2 项 e 的一致性修正；实施方式按第 2 节第 3 项 |
| 2 | 旧实现删除范围 | 按 kickoff §3 确认，AGENTS 与 testing-conventions 的修改按第 2 节第 1 项处理 |
| 3 | 差分开关形式 | 接受 test-only 双实现入口，生产 `parse_sql()` 继续走 Python，S2a 不引入部署 flag。设计 §7 与执行计划写的是“feature flag 之后接入（只差分）”，而 S2b 会按 DC46 合并上传侧数据路径并“feature flag 切换生产”。现在为现有 Python 路径加生产 flag，S2b 会重写它。因此把生产 flag 移到 S2b 引入，S6 删除不变。这是对设计 §7 的澄清，需记录 |
| 4 | V6 的表内分块并行（L3）与 DC47 L2 主机制的边界 | 保留 V6 已实现的 INSERT 元组分块，作为 SQL parser 专属的 L3。DC47 第 4 项允许 L3 按实测条件做，V6 已在 1–32 线程与 1 B–1 MiB 分块下证明输出逐字节一致。条件：只用同一个共享池，不嵌套建池；row-budget 偏移、同表多处错误的诊断顺序在不同分块大小下必须相同，纳入第 ③ 层与 Rust 确定性测试；不在其他 kernel 扩大 L3 |
| 5 | adapter 命名 | 复用 distribution 与 crate 名 `gateway-compute-python` 作为新的单一 adapter，删除 `gateway-compute-python-impl`；Python 模块对外接口为全新的 parser 接口，不保留任何旧 API 符号。好处是 runner 的 `--reinstall-package gateway-compute-python`、build-input 检查、闭包与 Dockerfile 的名称不变，改动面最小 |

另外两项按 kickoff 确认即可：真实数据范围只做第 ④ 层逐值差分，t1–t4 的 v1/v2 与 testdata1 均在 05，testdata1 按输入 digest 与 t3 去重（DC50 第 4 项及补充）；审核由原 S1c 审核会话负责，节点按 DC70 及其补充，exit 在基准 exit 之后。

## 4. 05 编码前基线

- 日志 05 `/home/dev/gdds-p6-logs/s2a/baseline-49d0846d86-20261031T221122Z.log`，SHA256 `3bf3b9f4…`（审核者已核对）。backend 离线同步与扩展 build-input 检查通过；pytest 471 passed、4 failed。
- 四项失败（`test_submit_job_effect` 1 项、`test_submit_recovery` 3 项）都报 `repository_service .venv is missing`：这几项会启动真实 Repository Service，而新 worktree 只同步了 backend 环境。不是产品问题。
- 这是调试运行，不是证据，不适用 DC68 的一次重做限制。处置：在同一 clean worktree 用 `UV_OFFLINE=1` 经 `uv-consume.sh` 同步 `repository_service` 环境，重跑这四项，再运行 `rust` 包的三步；通过后开始编码。日志照常记录，失败日志保留。

## 5. 下一步

owner 确认第 3 节后，记为 kickoff 确认决议（拟 DC72），并把第 3 项对设计 §7 的澄清写入设计与执行计划的 S2a、S2b 条目。实施方按第 2 节调整 kickoff，以追加提交的方式修订，然后开始编码。
