# Phase 6 READY 闭包容量产品代码与 05 证据审核

- **结论：代码通过，05 focused/静态证据通过，无阻塞项。可将该窄修正纳入实际恢复候选，推进新镜像和 04 backend/容器门禁；不是基准恢复放行。**
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 冻结起点：`9f288ad50475030ddb496ad00b3b79f4abdc0082`。
- 代码：`c18f83ddf8b4e4d54b8ebce37070fe0fbee546fc`；handoff：`357fc648b414b92999618b3e54618057f1379285`。
- 依据：DC80、[kickoff](p6-ready-closure-capacity-kickoff.md)、[容量定值补审](p6-ready-closure-capacity-kickoff-review.md#4-容量定值补审2026-11-05)。本次不审核尚未提交的 benchmark 恢复接线。
- 方法：在 `/home/dev/gdds-p6-capacity-code-357fc648` detached worktree 只读审核，程序比较完整 HEAD、detached、clean、父提交、文件范围和源码字节；05 经 BatchMode SSH 只读核对原始证据、wrapper 和当前候选 worktree，不取占用标记、不执行测试，不访问 CT108 测量卷。

## 1. 产品与测试

代码父提交与冻结起点相等；相对起点仅修改 `application/checkpoints.py` 和 `tests/test_operation_checkpoint_contracts.py`，handoff 提交只新增独立交接文档，`vnext/` tree 与代码候选一致。

程序比较确认产品文件恰好等于原文件将 `_MAX_READY_CLOSURE_OUTPUT_REFS = 4_096` 替换为 `32_768` 的结果，无其他字节变化。build、直接构造和 canonical decode 继续共用同一上限。排序、去重/重复拒绝、exact refs、size/raw digest、JCS、closed shape、版本、CAS/set-once、prior-output 与 inline payload 均保持原实现。没有修改输出集合、持久格式、锁或镜像边界。

测试覆盖符合定值审核要求：

- 旧范围样例使用独立固定 wire literal，断言规范字节、摘要和读回字节；审核者静态提取 literal 重算 SHA，匹配 `7fa7de2bba9d11b98082ffee1e3d67ed41ab4c7a595de5498a8d06a9f3b74a99`，期望不由被测序列化器生成。
- 4,096、4,097、32,768 三个集合验证完整 refs、document 和 canonical bytes round-trip；32,769 同时覆盖 build、直接构造、canonical decode 的拒绝。
- 原唯一性、损坏/缺失、版本、闭包一次设置及 CAS 测试保留；新增边界用例受模块级 unit marker 覆盖，不依赖真实 Dolt 或大业务输入。无需新增重复业务矩阵。

没有需要交设计会话修订的实质项。此单行变化支持“旧上限内格式/算法不变”的判断；旧步骤沿用仍须绑定其实际成功路径和来源身份，不以代码通过替代恢复证据。

## 2. 05 证据复核

原节点 `ct108-gw-dms-05`，hostname `gw-dms-test-05`，worktree `/home/dev/gdds-p6-ready-closure-capacity-05`。日志时间 `15:11:36Z–15:12:19Z`，起止 HEAD 均为完整 c18f；审核时程序确认该 worktree 仍为 c18f 且 clean。

在原节点及 CT201 只读副本分别重算日志与锁清单 SHA256，均匹配 handoff；读取原 wrapper，确认 locked 受控 uv 消费、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、代理变量清除、worktree 外 TMPDIR、backend Rust 扩展重装与 build-input 设置。wrapper 遇失败保留非零结果，五锁前后比较，不掩盖 pytest/静态失败。

| 证据（05 `/home/dev/gdds-test-tmp/` 下） | SHA256 / 结果 |
| --- | --- |
| p6-ready-closure-c18f-validation.log | `0eb087993e9cebbe0f4ca3d001fddab99f5acfb797af76e723004fe62b4ff9fc`；30 passed in 9.56s；五次 Ruff、五次 mypy 成功；validation_exit=0 |
| p6-ready-closure-validate.sh | `8e138e387be3d7b68abd541d89622d37cfe0973d5527c54262ed5e18a004dee2`；与运行日志中记录相同 |
| p6-ready-closure-locks-before/after/postflight.txt | 三份均为 `16c8ab14e5714fcc4e8470beea91feda7c56405ef42c36d66ef83336e8d3f238` |
| p6-ready-closure-postflight.log | `ff53277d4136be6b8560b83dafd0a14c9672bf4e145e343b35e81e072cb38511`；15:14:18Z 记录 clean、无 pytest/spawn 遗留、五锁一致及自有标记释放 |

CT201 副本目录为 `/home/dev/gdds-p6-logs/ready-closure-capacity-20261105/`。本轮未重复执行测试；已有定向证据足以审核本次常量和测试变化。候选 diff whitespace 检查通过。

## 3. 镜像与后续

本轮没有 H 镜像 revision/source-tree 或容器结果可判定。虽然改动不涉及 Dockerfile/锁/entrypoint，恢复产品代码已变化，后续必须构建并核验实际 H 的新镜像；原 V′ 只标识来源，不能冒充 H 或写成同镜像 MATCH。

原实施者可按获准流程将窄修正纳入最终恢复候选，按旧产品 DC67 整镜像流程准备并传输，在 04 执行实际候选 backend 权威包及容器门禁。benchmark 的精确 V→H 双身份例外另做代码审核；门禁、目标 config digest/全部 DiffID、输入及快照和逐步骤来源齐备后再审核恢复资格。此报告不授权跳过任一后续门槛，也不要求重复 owner 确认。

本次只提交审核文档，未合入产品、未运行镜像构建/门禁/旅程、未推送。05 候选 worktree 和证据保留供后续流程使用，审核自己的 detached worktree 用后清理。
