# Phase 6 S2a 证据复核 2

- 结论：**证据通过；S2a exit 仍等基准 exit 后办理（DC70）。** 测试删除合理，04 六包权威 runner exit 0，05 第 ④ 层 t1–t4 与 testdata1 逐值差分为 0。发现一处非阻塞的预检记录勘误，见 §3。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 对象：候选 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`；handoff `c3c95282bf` §11。主线接手 HEAD `dc6d1fbb2a`。
- 依据：AGENTS、DC64、DC66、DC68、DC70、DC73；执行计划 §7–8；证据复核 1。
- 方法：复用 clean detached worktree `/home/dev/gdds-p6-s2a-evidence-review2-c3c95282`，legacy 链接有效。04、05 仅只读取日志，不取占用、不运行测试、不写被测 worktree；未访问 ct108。本轮没有新增产品、测试或构建改动。

## 1. 删除与覆盖

`3b3d9c97bc` 仅删除 `repository_service/tests/test_uv_consume_script.py` 中 17 行旧组件调用测试。所依赖的 `gateway-compute-python/tests/test_v1.py` 与调用方 `native_kernel_component.sh` 已删除；通用外部 pytest 路径仍由相邻的 `test_uv_consume_allows_pytest_external_test_path` 覆盖，它断言调用成功、不误判项目外路径、完成 lock-check 与 run 两次调用。没有产品、Contract、golden、依赖或其他测试变动；符合证据复核 1 §3。

05 同候选定向验证：该文件 18 passed；RS unit 1,553 passed / 1 skipped；RS Ruff 通过，mypy 200 source files 通过。日志 SHA256 均程序核对与 handoff 一致。本轮不重跑这些检查；既有五包静态检查见复审 1，本次改动包的检查已补齐。

## 2. 正式证据

| 项 | 核对结果 |
| --- | --- |
| 04 runner | `gw-dms-test-04`，2026-11-01 02:45:07–03:06:41Z；起止 HEAD 均为候选；六包 manifest 均 `clean_worktree=true`；runner exit 0 |
| 逐包闭包 | 解析六份 JSON，重算 total_digest，逐包与 handoff §11 程序比较，6/6 一致；全部是本候选实际运行，不沿用上轮失败 runner |
| 结果 | Rust fmt/clippy/test 通过（152 tests）；shared_kernel 243；repository_contracts 152；repository_client 161；backend 3,235 + 52；RS 1,742 + 207，1 skipped |
| 离线与代理 | manifest 指纹验证 `CARGO_NET_OFFLINE=true`、`UV_OFFLINE=1`；Docker 输入中的大小写 HTTP(S) proxy 均未设置，主日志亦记录 proxy unset。使用已预填充依赖，未使用 PREBUILT |
| 镜像 | 候选上 04 backend/worker、RS、client e2e build 均 exit 0；依赖镜像本机 ID 与前次校验记录一致；RS candidate/build-input 均为候选，source-tree 为 `sha256:ee92f50f55fd9a134ddc1684aabc64fff32a32bffba680f5139cb9e692fe4015`；client revision 为候选 |
| 05 第 ④ 层 | `gw-dms-test-05`，02:10:48–02:28:50Z；起止 HEAD 均为候选，结束 clean；10 个覆盖输入、8 个唯一 digest；每份 4 个 Rust 配置（threads 1/8 × chunk 1048576/65536），全部 COMPLETE、parser exit 0、确定性一致 |
| 差分计数 | 8 份输入的 bytes、SHA256、表/行/值计数逐项与 handoff 程序比较一致；共 33,895,148 个值，逐值与诊断差异均 0 |
| testdata1 | 两份来源/目标 SHA 与 t3 v1/v2 一致；wrapper 按实际提取文件摘要去重，保留两个覆盖别名；没有因别名重复漏掉不同输入 |
| 清理 | runner 日志与清理记录显示 Cargo target、五个 Hypothesis storage 已清理，worktree clean，Dolt/Compose/8000 空闲，marker 已释放；这是当次运行后的状态，不代表节点当前可用 |

审核只读取摘要日志与 wrapper，不输出 SQL 或业务值。wrapper 对实际提取 SQL 计算 SHA 后传给差分工具；差分错误会停止，不把失败项记作 PASS。

日志根均为 `/home/dev/gdds-p6-logs/s2a/`。主证据 SHA256：

| 节点 / 文件 | SHA256 |
| --- | --- |
| 04 `authoritative-runner-04-3b3d9c97bc.log` | `e39675de73554a9908d2c9b1b8c3485f8278cef80c04bd40a9452dffba986ce5` |
| 05 `layer4-formal-diff-3b3d9c97bc-05.log` | `da4be0d15e903016b1c74f0d093641f6b36de69d3f6d1a7f958e1259dad339bc` |
| 05 `run-layer4-3b3d9c97bc.py` | `a9be5e67226a33d8c4a30c3d20e6e339b7e2a816ea10c216621e3ab30528e2c8` |

同时重算 §11 引用的定向测试、静态检查、Rust build、backend sync、04 三次 build、身份与环境预检、源码传输、失败预检和清理日志，所列 SHA 全部一致。程序输出及原始摘要日志副本保存在 CT201 `.../s2a/evidence-check-2-review/`：`hash-audit.json`、六份 `*-manifest.json`、`comparison-summary.json`。hash-audit 中 `handoff_match=false` 的六项是额外读取但 §11 未列 SHA 的辅助日志，不是已列 SHA 不符。

## 3. 停止规则与勘误

1. 上一轮 `30d67140d4` runner exit 1 后停止，先交证据复核 1，再追加测试删除与新候选六包完整运行；没有把失败 runner 作为沿用来源，处置正确。
2. 05 第一次 RS unit 因子进程缺少 Cargo PATH 失败（日志 `ff7c25d9…`），maturin bootstrap 尝试公网访问，被网络隔离拒绝。它是测试修订后的 focused 调试，未作为正式证据；修正环境后 unit 通过，再开始正式差分。此事不能称作 DC68 的“尚未运行测试”重做；不据此放宽任何正式 runner 停止规则。正式差分与 04 runner 无该失败。
3. 输入路径/heredoc、SSH 引号与缺少 rg 的错误发生在只读预检，记录保留，按 DC68 只读预检澄清处理。
4. **非阻塞勘误**：handoff §11 称 04 `offline-env-preflight-04-3b3d9c97bc.log` 已确认四个 Rust 工具版本，原日志实际在四个版本查询处均报“未选择工具链”，随后同步成功并以 exit 0 结束。不能把该退出码解释为版本检查通过。权威 runner 的 Rust manifest 在 selector 下实际记录 rustc/cargo 1.97.0、rustfmt 1.9.0-stable、clippy 0.1.97，Rust 三项检查全部通过，扩展 build input 亦匹配候选 Rust tree。因此正式证据足以支撑结论，不重跑；实施方在下次 handoff 更新时更正该句，后续预检须在 `vnext/rust` 查询并传播查询失败。

## 4. 后续边界

本轮审核文档不触发镜像重建。本结论绑定候选 `3b3d9c97bc` 的实际容器门禁，未宣称 main 或未来 exit HEAD 已验证。04 来源 worktree `/home/dev/gdds-p6-s2a-runner-3b3d9c97bc-04` 保留到 exit 合入后；exit 时在同节点同 worktree 判定 carried，不能用本审核 worktree 代替。

S2a tag 与合入须等基准 exit（DC70）；届时核对后续变更、按包闭包与镜像身份等价，并办理执行计划阶段状态行及 DC72 路径清单。路径清单正文修订交设计会话。本轮不打 tag、不合入、不推送，不修改设计或 DC。
