# Phase 6 四路输入生成工具：代码与证据审核 1

- 结论：**需定向修正 F1，当前候选暂不放行合入/启用。** 所交 focused、五包静态、有界诊断及清理证据复核通过，但成功路径证据不能消除 F1 的进程失败判定缺口。不要求重跑全量产品 runner 或 full4 大生成。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 起点：`3b03b7ee3ccaea9e2b664afc5611539ff9d1e143`；代码：`6f78b8fc5041416e59b4f32b91828e00819cad9e`；最终 handoff：`02bff0adfbf45e7e8c3ed3c41fc7e3861e171ff8`，分支 `p6-input-four-workers` 上的 `p6-baseline-four-worker-handoff.md`。依据设计 `7ab0e44abf`、范围审核 `ea04df3cb8`、AGENTS 与 DC66/DC68/DC73/DC79。
- 方法：在 `/home/dev/gdds-p6-four-worker-review-02bff0ad` clean detached worktree 只读审核；程序比较身份、祖先、差异、Git 对象和相关 AST。CT201 先核证据副本，再以 BatchMode SSH 确认 05 可达且占用已释放，仅重算原始文件与读取进程状态；不取占用、不写被测 worktree、不运行测试或诊断、不访问 CT108。核对脚本经 stdin 执行，真实数据仅输出计数与摘要。

## 1. F1 — P2：返回结果先于正常退出确认，可能把异常 worker 发布为成功

位置：`vnext/backend/benchmarks/p6_input_generation.py:74`；关联 `p6_w4_input_stage.py:62` 的 `accept`。

调度器收到 `(True, result)` 后立即执行 `accept(index, result)`，之后才 `join(timeout=5)`；它只检查 `is_alive()`，没有检查 `process.exitcode == 0`。有两条明确路径：

1. worker 发出成功结果后非零退出或被信号终止，`join` 返回、`is_alive()` 为假，父进程将其当作成功删除。pair/W4 可继续发布 receipt，完整调用也可能成功结束，硬退出没有成为失败。
2. worker 发出结果但 5 秒内未退出，父进程最终会报错并收束；但 `accept` 已执行。W4 若这是该档第二份结果，回调已经发布该档 receipt，留下的成功记录来自随后被判失败并终止的 worker。

这是 §5.5 已要求的失败/硬退出收束与成功记录发布顺序问题，不是新增恶意进程模型。实际影响是失败步骤可能被当作完整来源复用，或直接漏报失败。本次为源码控制流结论，未在节点做额外故障注入，不宣称现有诊断发生过该错误。

**修正要求：**成功 payload 先暂存；在调用 `accept` 前确认该子进程已经正常退出且 exit code 为 0。退出超时、非零或信号退出均走现有失败收束，不接受该单元，不发布依赖它的 receipt。其他已完整核验成功的独立段仍可保留，无需新增状态机或删除有效兄弟段。

现有 `test_direct_child_exit_ends_parent_and_preserves_completed_sibling` 注入的是**未发回结果**就 `os._exit`，覆盖不到上述路径。补一个参数化的有界用例，覆盖成功 payload 后非零退出与不退出，验证失败单元未被接纳、对应 W4 receipt 不存在、其余进程收束且整体无 READY；保留既有成功兄弟段复用验证。采用标准进程/事件同步，不复制算法矩阵。

## 2. 其余代码核对

| 范围 | 结论 |
| --- | --- |
| 改动边界 | 起点至代码候选仅四个 benchmark 模块及一个测试文件；代码至最终 handoff 只改 handoff 文档。生成算法、共享 helper、预检、census、backend/shared 产品源码、相关锁未变。候选 `vnext/` tree 为 `5659e9db86216b6db9c5c3a58ef079ec1af3cdc9`。 |
| 调度 | 公开 CLI/API 支持 1/2/4，默认 1；1 路在父进程顺序调用，2/4 路使用 spawn、每单元一个进程和独立 Pipe/sentinel，最多四任务及所选活跃数，无替补丢失任务的 worker 或嵌套池。pair 完成、关系及 accepted identity 检查通过后才进入 W4。 |
| 独立生成 | pair/W4 各首次与重复都真实调用原算法及正式模板封包，路径各自独立；父进程比较包含完整生成报告、SQL SHA 和包 SHA 的返回值。pair 保留原未变化副本核验；W4 每档两份匹配后保留完整逐表报告。F1 是接纳前还需确认退出的缺口。 |
| 复用 | `reuse_stage` 保留原来源安全路径、大小/SHA、fingerprint、完整文件集合及确定性标志校验，复制至新根后再核摘要。pair 或 W4 某档命中时不调度该段。仅复用完整阶段，来源/输出目录隔离规则未变。 |
| 身份 | 新共享调度模块纳入 `generation_identity`；共享改动保守失效 pair/W4，W4 专属模块只进入 W4 身份。workers 不进入 fingerprint，三种调度应产生相同字节/报告；没有旧 receipt 人工豁免或历史导入。 |
| 验收与取消 | accepted 2× identity、full Preview、census 完整性、输入汇总、根清单及 JSON 发布函数 AST 与起点相同。CLI SIGTERM 转成取消并在 finally 恢复 handler；Ctrl-C/SIGTERM 测试覆盖活跃兄弟进程收束，当前测试通过。未新增完整验收并行或正式计时并跑。 |

## 3. Focused、静态与运行身份

原始 validation 日志与 CT201 副本重算 SHA 均为 `41d68cfe066d10765ddaf43c6f20a6c302811158d128e8465af489de74c6f6b9`。日志记录 `gw-dms-test-05`、06:20:08Z–06:21:22Z、起止完整 HEAD 均为 6f78，`validation_exit=0`；**59 passed in 19.78s**，五次 Ruff 和五次 mypy 成功。程序逐项确认上述记录，不接受单独转述的 PASS。

读取实际 validation wrapper，确认受控 locked uv 同步/消费、backend 扩展重装、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、外置 TMPDIR、proxy 与 Rust 覆盖 unset，失败会停止后续步骤。wrapper 本轮重算 SHA 为 `abb02dc373703f76177da1b3e30abb10351e7f6348ce7acdf29c6534fef78e3d`；它是当前读取的脚本摘要，不追称日志已记录该摘要。

LAN bundle 实际 SHA 为 `2c6584114d015fb2137c62f74c9fe8af35a43483a22115ebfe6d9cf354f23823`，与 handoff 一致。节点保留 worktree 当前仍 clean、HEAD 为 6f78、legacy 链接存在。focused 前后、诊断前后和 postflight 五份锁清单均为 `16c8ab14e5714fcc4e8470beea91feda7c56405ef42c36d66ef83336e8d3f238`；各项实际锁与候选 Git 对象一致。

## 4. 有界诊断复核

实际脚本 SHA `a872e680028c1c6edc5b9b53a14c9220f16796327580279e38ed9c20d0257979`、wrapper SHA `52fe4d9c8c3c44c92251a044fc6f82a2f118957a2fdd0265c407c95799134eec` 与 handoff 相符。代码按 2、4 各一次执行，分别串行 pair 四单元及 W4 四单元，无重试；使用同一冻结 SQL 样本及 SQL-only 模板，运行本候选父调度/汇合入口。wrapper 有固定 HEAD/clean/占用 owner 检查、offline lock-check、外层 900 秒预算；内部 880 秒、聚合 RSS 8 GiB、MemAvailable 8 GiB、磁盘 10 GiB 边界与 handoff 相同。

重算原输出清单 **52 个文件**全部匹配；再核 summary/result、实际 artifact 摘要、每份 receipt 的文件集合/大小/摘要、两模式完整 reports、同档首次/重复 SQL/包相等。四种输出包均核对其中唯一 SQL 与生成 SQL 的摘要一致。两档 W4 每种模式均保存 638 张表的完整计数字段，逐表 before + inserted − deleted = after，汇总与报告相等；未打印表值。来源 retained SQL 与私有副本实际字节均匹配 provenance，未变化。

| 模式 | pair / W4 秒 | 总秒 | RSS 样本数 | 父进程加后代采样峰值 bytes | 最小可用内存 / 磁盘 bytes |
| --- | --- | ---: | ---: | ---: | --- |
| 2 | 92.320 / 91.825 | 184.174328 | 920 | 701,804,544 | 67,068,959,744 / 228,715,126,784 |
| 4 | 63.145 / 46.559 | 109.732385 | 549 | 1,148,538,880 | 66,705,418,240 / 228,687,613,952 |

RSS 峰值约 669.293/1,095.332 MiB。逐样本独立求和、最大/最小值均与 summary 匹配，已有采样未触及阈值；不能证明采样间无短峰值。CPU 字段核对了脚本统计边界和层级，不宣称另做独立 CPU 测量。两种模式各一次，只能说明本样本本次观测，不外推稳定加速比、全尺寸 pair 峰值或 CT108 总耗时。

| 证据 | 重新计算 SHA256 |
| --- | --- |
| 诊断主日志 | `0a6a26e6b71147167cc291e65411ef57e67112e85453d3d1dc4102de780c5775` |
| summary | `030b39533210b17dad880d989add8ac3805523e79f2fc5f87340fbc8bd088995` |
| provenance | `e15285e2a492a8f595fa4716e50033dac071f33926a82b89939dd619369995ed` |
| 输出清单 | `355114a0218af929a1e6b140b2baac69b1119dc00f23327f8f8f6327f5738c88` |
| postflight | `91cfb4c7e83eb67f38e41257bca855db2f0371da1749661b8ecbbb10ae6c9c14` |
| 2 路 RSS samples | `ad063d9cb58817fbca8f7d938570b60c680f04a79d63db0af6996e2e5655752b` |
| 4 路 RSS samples | `d8c0b4d04a752a5f04ad8d79fa452363b0af01edfa7e5ef96790dd7aa51d6e81` |

主日志为 06:24:36Z–06:29:32Z，起止完整 HEAD 与 6f78 程序比较相等，exit 0。postflight 记录 06:30:22Z 自有占用释放；从原 RSS 样本汇总的 20 个 PID 目前均不存在，05 busy marker 不存在。此次成功运行及清理证据成立，不受 F1 尚未覆盖的失败路径推翻。

## 5. 修正与后续

F1 属 §5.5 和 DC66 第 5 项范围内修正，不需要扩大设计或产品授权。修改后在 05 clean 已提交候选完成定向失败用例、既有工具 focused 与五包静态，提交固定代码和 handoff 供复审。原有 6f78 样本保持绑定 6f78；不要求为了 F1 重做真实样本诊断或 full4，大生成算法和封包未变的判断由增量复审确认。

本轮没有正式输入验收或新 READY，没有容器/部署/依赖变化，不触发镜像重建，也不声明新的 image revision 门禁通过。当前 CT108 任务和停止规则不变；不得把成功样本取证当作跳过 F1 的理由。

仅显式路径提交本报告；不改产品、工具、设计或计划正文，不合入候选、不推送、不打 tag。节点证据和实施 worktree 保留，审核 worktree 核对 clean/HEAD 不变后清理。
