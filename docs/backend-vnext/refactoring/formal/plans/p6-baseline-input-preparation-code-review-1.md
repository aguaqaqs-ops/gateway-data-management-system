# Phase 6 基准输入准备工具：代码定向审核 1

- 结论：**需定向修正 F1、F2；实施证据待交付，本轮不作证据放行。** 分段生成、完整验收及 W4 机械拆分的主体方向符合 DC79；当前双进程异常退出收束和复用来源目录隔离尚有缺口。当前 CT108 测量继续原版本，不受本报告影响。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 起点：`d458d05835a3d297583624a28eb4fb2dffe9bec7`；初始候选 `a421bfefdebce5ee51c3c4fb3c5f9a553dd8b0ec`，随后核对 `335aeb6cb2fee77fa84d93b525bd2ea209c6741d`；本报告最终代码对象 **`e08cabdb234e0ba77331660fc2d096dad97bd12e`**。
- 设计依据：[工具 kickoff](p6-baseline-input-preparation-kickoff.md)，固定设计提交 `dbbaa1282e18b8a236843b5c7e9f713ab8936716`，含 `779cd9f9fd` 的历史来源/物理拆分边界与 `733bfe98d6` 的预检/继承 census 澄清；DC66 第 5 项、DC73、DC79、AGENTS。
- 方法：分别在 `/home/dev/gdds-p6-input-tool-review-a421bfef`、`/home/dev/gdds-p6-input-tool-review-335aeb6c`、`/home/dev/gdds-p6-input-tool-review-e08cabdb` clean detached worktree 只读审核；程序比较完整 HEAD、detached、clean、祖先关系、改动面与 AST。不访问 05 或 CT108，不获取占用、不运行测试或工具，不读取运行中输出；无落盘临时脚本。

## 1. 需修正项

### F1 — P1：任务子进程直接退出时，Pool 可能永久等待，不能完成失败收束

位置：`vnext/backend/benchmarks/p6_baseline_inputs.py:253–262`；对应测试 `tests/test_p6_input_preparation.py:300–328`。

`_generate_w4_stages(workers=2)` 用 `dict(pool.imap_unordered(...))` 等待两项返回，只在迭代抛出异常后 terminate/join。普通 Python 异常会被 Pool 回传，这条路径可以进入清理；但任务已被取走后，子进程若因信号、`os._exit` 或进程级故障直接退出，就没有该任务的返回值。Pool 会补充 worker，却不会补回已丢失的结果，父进程仍等待两项结果，不能进入当前异常处理。

静态依据除候选代码外，还核对了本机缓存的相同 Python selector 版本 `cpython-3.14.6` 标准库 `multiprocessing/pool.py`：worker 只捕获 `Exception` 并写结果；`_join_exited_workers`/`_repopulate_pool_static` 负责回收和补充 worker；`IMapIterator.next(timeout=None)` 等待结果，没有将上述退出转换为当前任务失败。本轮未在开发机或节点运行故障注入，结论属于源码路径审核，不冒称已复现的运行日志。

实际后果是两路大输入生成中一条进程退出后，任务可能长期占住节点且无法按 §5.1 报告失败和收束。外层 `except BaseException` 不能捕获另一个进程未传回的异常。现有测试用输出目录引发 `OSError`，覆盖的是正常异常回传；它不覆盖任务进程消失。

修正要求：使用能观察任务进程退出的标准生命周期机制；异常退出应结束父任务、停止并回收本次其余子进程、保持失败状态且不发布 READY。保留已经完整写入且可核验的分段即可，不新增通用恢复状态机或任意生成时长阈值。05 定向验证应包含一次任务进程直接退出，并证明父调用在测试预算内结束、无本次存活子进程，以及本次已完成分段仍能按原规则复用。现有普通异常及 1/2 路字节一致测试保留。

### F2 — P2：新输出根允许位于复用来源根内，违反来源不变约束

位置：`vnext/backend/benchmarks/p6_baseline_inputs.py:507–528`，后续写入位于 `_generate_pair:278–291`。

`prepare_inputs` 只检查 reuse root 存在、输出不在 worktree 且尚不存在，没有检查输出与复用来源的包含关系。例如已有 `/evidence/source`，调用 `--reuse-root /evidence/source --output-root /evidence/source/retry` 时，新的 `retry` 可以通过检查；随后立即在原来源根内创建目录、复制源 SQL 并写入预检文件。即使后续验收失败，来源根也已被改变。经 symlink 解析后落入来源根的别名同样应拒绝。

这不要求防范同 euid 恶意换名；它是正常命令参数可触发的目录范围错误，与 kickoff §4 的“复制至新根消费，不修改来源”和 §5 的来源不变验证直接相关。现有 `test_valid_generation_receipt_reuses_bytes_without_calling_builder` 使用两个平级目录，只证明该正常用法未修改来源，不能约束公开准备入口。

修正要求：在任何 mkdir、复制或预检前，按规范化路径拒绝输出落入复用来源根；通过公开准备入口验证直接嵌套及 symlink 别名两种情况，确认拒绝前后来源不变。无需扩展为新的安全协议。

## 2. 已核对的主体行为

| 范围 | 代码结论 |
| --- | --- |
| W4 拆分 | 程序比较确认 `p6_w4_synthetic._make_w4` 与起点算法 AST 完全相同；共享 synthetic 模块的函数/类仅 `_make_w4` 改为保留入口的转调。335 增量移除未用 import，并在预检失败消息中增加诊断代码和表名，未加入真实行值。 |
| 指纹依赖 | pair 包含共享生成/分段模块、backend/shared 源码树、相关锁与 Python selector、v1/v2 原包与 SQL 摘要及后缀；W4 增加独立算法/构建模块、基底 SQL、模板包及 rate。共享解析/规则变会失效，W4 独有模块变化不直接使 pair 失效；非生成校验器与普通文档不强制使生成物失效。 |
| receipt 与来源 | 固定三段，生成后分别独立重复 SQL/封包并比 SHA，成功后原子写 receipt。复用校验 stage/schema、fingerprint、deterministic、文件集合、实际大小/SHA 和路径边界；复制后再比目标摘要。validate 缺少匹配来源即拒绝；generate/all 缺失或不匹配时重新生成，不能将历史无 receipt 根追认为已复用。来源文件摘要不符直接失败。 |
| 分段与 READY | preflight 返回 PREFLIGHT_COMPLETE，generate 返回 GENERATED_NOT_VALIDATED；均不写最终 input-summary。validate/all 每次重新运行全部完整验收，未复用旧验收结论；因此校验器修正只要生成身份不变即可复用生成物，并执行新验收。 |
| 原验收保留 | 已接受 2× identity 在 W4 启动前核对；原四个输入的完整 Preview/business/canonical、三种 census 合并、dataset 集合/COMPLETE/ordered 检查及输入计数汇总保留。v1/v2 未变化副本检查移入 pair 构建。最终 summary 仅在全部检查成功后写入，记录 manifest/census 实际摘要；重复生成证据来自成功段，不是复制同一文件后比较。 |
| 预检范围 | 扫描全 SQL 语句，按表保留最多 60 行及原 DDL；执行 2×、W4 两档和生产 SQL materializer/canonical primitives。覆盖记录区分主键/比较键、无键、nullable、空表、有序和特殊点，列明未触发插入的表及 XML/composite 排除项。已有空表字符串键、重复主键和 keyless 回归保留。它不验证全量值域或 XML 关联，也不能称为全量业务验收。 |
| 并行范围 | 只并行两个 W4 段，默认 1、限定 1/2；pair、预检、Preview/census 不进池；W4 SQL、包、重复结果和 receipt 文件名各自独立。普通任务异常走 terminate/join，异常退出缺口见 F1。 |

生成与校验相关的原 `_assert_accepted_2x_package_identity`、`_validate_generated_preview_materialization`、`_validate_census_materialization_complete`、`_summarize_input` 等函数 AST 未变；改动限七个 benchmark/测试文件，产品源码、golden、依赖未改。最终候选的 `vnext/` tree 为 `86e3f041a70e3f6fcf05d765585fb18403646ae8`。

335 至 e08 的增量已纳入：独立 preflight 不再要求不使用的 accepted summary/census；generate 仍要求 accepted summary，validate/all 在写根前要求 census；预检结果增加实际 SQL 摘要、大小与实现身份；receipt 局部变量改名及两个文件 EOF 整理。上述增量不改变 F1/F2 所在路径。

## 3. 非阻塞整理及证据缺口

- 最终候选 `git diff --check d458d05835..e08cabdb23` 通过；335 中发现的两处 EOF 空行已清理，不再列为待修项。
- 预检当前直接处理 SQL bytes，没有封包/staging 冒烟；不能把它描述为 kickoff §3 所写的全部“生成、封包”已覆盖。**交设计会话：**结合现有独立封包回归，明确 SQL primitives 预检的这一边界；不要求把 XML/business 搬回低成本预检。若仍要求预检覆盖封包，则由实施补足该小路径。最终候选已补 source/tool 身份，handoff 仍须绑定实际原包和工具提交。
- 新测试覆盖分段复用及完整验收失败，但当前候选未见公开 `prepare_inputs` 的完整成功发布用例。建议用有界 fixture 贯通 generate→新根 validate，验证保留原业务/census 检查后才发布 summary；不以此为由重复大输入或产品 runner。F1 测试另须验证本次成功分段，不能只证明失败前另一个来源根仍可复用。
- 05 focused、五包静态、最多 600 秒的真实来源预检及最终 handoff 尚未正式交付。本轮没有重算任何节点日志 SHA，也没有接受转述的测试数字。转述的 `/usr/bin/time` 缺失 exit 127 及 Bash time 修正尚待日志核对，本报告不作停止复核结论。真实来源预检不替代完整生成验收；首次采用双进程的资源预算仍按 kickoff 核对，不能以单进程峰值或 fixture 耗时承诺加速。

## 4. 修正、镜像与后续

F1/F2 是 DC79 范围内的实现修正，不需要扩充产品、输入定义或验收授权。修正后交固定候选与独立 handoff，05 focused 及五包 Ruff/mypy 记录起止 HEAD、exit、节点和日志 SHA；审核再核对增量与证据。审核不修改产品或设计正文，不直接向其他会话发送消息。

本轮只审核 host benchmark 工具，不触发冻结产品镜像重建；没有本次工具的 image revision/source-tree、门禁或 carried 结论。现有 CT108 任务不切换，新工具待定向复审后协调下一次实际需要时使用，不为演示再生成大输入。

本报告仅按显式路径提交；不推送、不打 tag、不办理 exit。三个审核 worktree 在确认 clean、HEAD 不变后清理。
