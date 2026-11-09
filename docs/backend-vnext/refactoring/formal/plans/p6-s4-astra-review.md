# S4 第二次独立设计审核（Astra）

日期：2026-11-08。结论：**DESIGN_CLEAR_FOR_OWNER**。

- 固定 base：`572359d3a7719591eb21ce81d6f0b07cb18b237c`。
- 固定 candidate：`de0eb3a8b2f9881737a183f0a4663dad9a75d67f`。
- 审核 worktree：`/home/dev/gdds-s4-astra-review-de0eb3`，本人创建的 detached worktree；`legacy` 链接主仓库且经 `git check-ignore` 确认忽略。起止 tracked/untracked status 为空。
- 角色：Owner 明确授权的一次 GPT-6-Astra high 独立审核；未参与设计，未递归创建 agent。报告在 worktree 外交协调者，未提交、推送或改产品。
- 本轮仅设计审查；没有测试、编译、lint、构建、容器、SSH 或测试节点执行。没有重算历史节点原始证据，以下历史结论仅用于核对设计依赖和待验收边界，不能当作本候选的新产品证据。

## 1. 审核结论

未发现需要在实施前修订的阻塞设计缺口。当前候选足以按 kickoff A–E 分节实施：语义及独立预期先固定，storage diff 与策略分离，SQL 编码及通用 facade 明确迁移，最后接入 Submit 并删除旧路径，再集中取完整业务、资源与性能证据。

这个结论不保证未来实现正确、M24 容量通过或性能达标，也不代表产品实施授权、S4 exit、S3 解阻或 S5 放行。S3 原 W3 失败仍是 BLOCKED_CAPACITY；Q18 的静态 CLEAR 仍不替代节点/容器核收及 FE 前置交接。

## 2. 独立核查结果

| 检查项 | 设计与当前源码事实 | 结论 |
| --- | --- | --- |
| 存储 diff 的输入和策略 | design §3.1–3.3 按完整 persisted 列与 canonical storage key；ordered 使用 gid/no 原语义，不消费 records/LIS/共有列。`import_publication.py:517–585` 的 manifest 初筛/patch-comparable 与 `_planner.py:156–361` 的最终策略已交叉核对。source-only keyed 零差 NOOP、keyless 未读 before 的 rebuild 被明确区分；version 变化先于 NOOP；非 INITIAL 缺/坏 parent 拒绝。 | DC94 与实际产品路径一致；没有把 FE key 不同变成 rebuild 条件。 |
| 计数的真实消费者 | 当前 Submit 只从旧 plan summary 取得 rebuild 表名（`import_publication.py:279–286`）；keyless parent 被 `_patch_comparable` 排除，旧 Submit 空 rows 不是完整净差。design 明确新 Submit `net_counts=None` 与通用完整 ChangeSet 计数不同。 | 无需为无消费者的旧 Submit 计数额外读取 parent；通用 keyless multiset 净差保留。 |
| SQL 排序与冻结字节 | `_changeset.py`、`_digest.py`、`_repository_replay_renderer.py:147–422`、projection `import_replay.py:17–75` 支持 design §4 的 DDL 全前置、表/操作顺序、CASE 全非键列、JCS key 排序和 keyless mutation row hash 排序。INSERT 贪心批次与 UPDATE/DELETE 原 256 窗口内按字节分批的区别确实存在。 | 设计没有把旧窗口改成统一贪心算法；完整语句 4 MiB、超大单行例外、DDL+DML 200 MiB 等号边界均已覆盖。 |
| 标量编码 | 当前 literal 的 `.15g`、float32 解码后格式化、负零、转义、BIT/binary、SET 文本与业务 sequence frame 的区别，均可在 renderer、`_mutation_cell_from_frozen_artifact`、`_digest.py` 和 Shared Encoding 中对应。 | Rust 同名逻辑不能直接借用默认 Display 或业务 content digest，设计已明确；尚需独立向量证明。 |
| 内存与 FFI | 当前 Python rows 预约挂 operation lifetime；`ArtifactReadHandle` 在 mmap 前预约、持有 streams 与关闭 owner；`OperationMemoryBudget` 按真实 backing 去重；Rust comparison kernel 已有 lease、可取消排序和 schema-explicit side，但错误类型仍依赖 ordered。design §3.3、§5 给出最小抽取、错误保持、同 operation M 子额度、逐表释放、Vec capacity/复制/最后 consumer 计费和保留 2528 MiB package envelope。 | 改善机制合理，未把 mmap/低 RSS 当免费，也未新增第二 M、无界队列、spool 或恢复系统。 |
| 通用 facade 与真实调用方 | 仓库检索的两个 facade 生产/测试调用与 design §3.4/§6 迁移清单吻合。现 `tests/conftest.py::operation_kernel_context` 只 yield None，候选明确改为 yield context；caller 显式初始化共享池、提供有效 scope/context，结果 charge 保留到最后使用。DDL FFI 留在 projection owner，避免 Projection→Mutation 反向依赖。 | 不存在依赖隐藏 ContextVar 或无预算旧签名的设计空缺；精确接口与 import guard 可在 A/C 落实。 |
| 恢复、CAS、保护 | `submit_jobs.py:501–568` 实际按 prepare step checkpoint 有无走 reuse/publish；`import_builder.py:214–230` 的 reuse 校验原包，不调用 renderer。`submit_jobs.py:1569–1663` 仍解析冻结 closure、exact parent metadata/catalog，`repository_ref.py:174–255` 按 pinned commit 校验 catalog 与所选 parent。design §7 与 Business/Operation Lifecycle、Canonical Storage、Repository Service 保持一致。 | T1 PREPARED 不等于已构包；checkpoint 后不重建/换 key，unknown outcome、STRUCTURAL 全 catalog、技术 main/业务 BaselineHead 分离完整。 |
| 验收与归因 | kickoff §2/§4/§5/§6/§7 分别给阶段依赖、唯一测试 owner、实际扩展/离线/闭包/镜像、DC33 真旅程和退出交接。S1a 的 7d0ce622 冻结及终审 §7、S3 E §61–64/容量报告、Q18 报告与 DC91–94 已交叉核对。 | fresh t1–t4、冻结 2×t4、1 warm+3、100% 压力单列、S1a 阈值真实回放及原 M24 same-worker 守卫形成闭环；未冒用 S3 失败或旧来源作新成功。 |

## 3. 实施期必须证明的事项（不是新增设计 finding）

1. A/C 独立 expected 必须覆盖 `.15g` 舍入与指数转换、JCS 非 BMP 属性序/键列序、keyless mutation hash，以及 byte flush 和第 256 行交叉。不得由新 Rust 生成预期。现冻结 SQL/包 golden 保持。
2. C 的显式 context 不能只有签名：未初始化池、无有效 scope、关闭后调用要拒绝；caller closure、转换 Arrow/scratch 和返回 bytes 的 charge 期限必须实际成立。`KernelExecutionContext` 当前没有显式 closed 字段，落实关闭后拒绝属于已列接口语义的实现工作，不是目前已有能力。
3. D 的逐表测试要证明 native Arrow 先退、reader/mmap 再关，before/after/batch_reader 与导出 stream 的最后 owner 都释放；不能仅把旧预约函数删除。parent cache miss 的精确 commit 回填仍需 count/content 验证。
4. 2528 MiB package envelope 覆盖新增 DML 汇集、DDL、拼接、USTAR/zstd 与 readback 的同时驻留，仍需真实账本及代码分配上界核对。若实测无法成立，按 design §9 停受影响工作；不能以本次设计 CLEAR 推定容量 PASS。
5. E 固定执行稿需落实具体输入 SHA、模式/冷暖、节点镜像与包闭包，保留失败并逐栏报告 SQL/功能、M24 容量、时间、压力及未知。S4/joint 改善不能倒签原 774 的纯 S3 结论。

以上均已在 design/kickoff 中有 owner、阶段和验收位置。没有因未来实现尚未提供运行结果而要求额外机制，也没有为潜在 SDK/未来不可信同机 actor 扩大本轮范围。

## 4. 读取范围与容器记录

读取候选全部九个差异文档，以及 AGENTS、testing-conventions 的扩展/闭包/镜像规则、Rust 和比例化政策、P6 总设计相关节与执行计划引用、DC45/55/57/78/91–94、S1a handoff/终审相关节、S3 累计 handoff/E 容量/E 终审 §61–64、Q18 最新报告。Owning 文档覆盖 Storage Mutation、Canonical Storage、Shared Encoding、ADR0014，以及 Business/Operation Lifecycle 和 Repository Service 的相关状态/验证边界。

源码主要覆盖 Submit import adapter，mutation planner/digest/ChangeSet/import wrappers/SQL renderer，projection schema facade，snapshot repository materialization/canonical mmap reader，Python kernel budget/context，comparison native bridge 与 Rust kernel/cell 基础，Submit prepare/reuse build input，以及两个 facade 的调用点/现有 fixture；固定 expected 路径已核存在。没有将未读取的历史原始节点日志写成本人新核收。

本轮 `container rebuild=no`：base..candidate 仅九份设计/Contract/计划文档，没有产品、锁、部署或测试 harness 改动；不是阶段退出或 production gate。当前 candidate 产品验证未运行，未进行 carried 身份判定。最后引用的 S3 产品来源为 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`，H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2`，其镜像/闭包资格限原 E 报告范围；不能表述为未来 S4 产品已通过。S4 实施后按 kickoff E 在固定候选重建并运行适用 Compose，再按实际同源闭包处理文档 H。
