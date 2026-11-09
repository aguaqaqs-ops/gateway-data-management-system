# P6 S4：业务正确性收敛清单

**核收结果（2026-11-09）：本清单已实际完成，原审S4_EXIT_GO、本地附注`p6-s4-exit`指H1e778。** 见[最终交接](p6-s4-handoff.md)/[独审回执](p6-s4-exit-review.md)。下列为退出前已确认的收敛范围，不是新的待运行队列。

2026-11-09，依据[Owner DC98](p6-s0-owner-decisions.md#dc98-业务正确性优先与s4验证范围收敛owner2026-11-09)。Owner已同意方案；本页更新当前S4范围，不改历史报告/原件，不表示S4已通过。当前产品V仍为6786b28a3506feab3d8eac7d1288c8b22525bb8f。

## 保留与复用

- A–D原审GO及focused、真实t1–t4的850表差分；独立SQL/golden、阈值/分批、FFI/预算/取消/最后owner断言。
- 当前V权威包/Compose：backend与RS实跑，另四包在原04同worktree按闭包直接引用c9e合格来源；精确SHA见[协调§16](p6-s4-coordination.md#16-2026-11-09-权威封口镜像修复与真实旅程调度)。源码若变，按实际影响重判，不口头沿用。
- publisher/readback、T1 PREPARED固定包/key、parent/frozen校验、CAS/幂等/恢复、technical main与业务BaselineHead分界的现役权威测试。
- S1a旧SQL/当前generic Rust facade/private Dolt组件证据按原限定范围引用，不冒生产worker或容量证明。

## 剩余工作

1. 关闭04首个W3 FULL warm的Repository独立核对失败。在保留现场做必要诊断，定位实际schema/行值与固定旧源预期差异，不用新实现反填预期。镜像来源、日志通道和RS停机按真实业务/生命周期影响处置，不恢复旧完整profiling框架。
2. 选冻结**真实t4 v1/v2**作为一组输入，来自标准datasets.json（SHA 78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f），不是2×t4。定向调用生产Submit，仅保合法Preview/首次Submit和增量基线所需审批/Archive，再做一次增量Submit；不History，不为本项完整消费FE records或重复全旅程。
3. 核两次Submit后的technical main、完整目标catalog/schema/行数及代表keyed/ordered/keyless/composite表内容；结合已有权威断言核无变化不额外写Repo、BaselineHead不提前推进。原失败若暴露更广缺口，补最小复现和修复，不重开全矩阵。
4. 保有限配置、实际源码/构建输入/运行镜像来源、原exit/日志及明确收尾。当前N1/48GiB envelope/8GiB reserve/M40不因低RSS降估算、不改全项目默认；M24与未知独立报告。时间顺带记实际值，无逐段profile/统计门槛。
5. 修复后必要focused及按实际闭包要求的最终门禁集中一次；原E连续核finding、当前V/H来源及本清单。满足后按既有授权办理本地S4 exit tag，不推送、不进入S5。

## 取消与限制

- 撤回旧28旅程、04/05的12/16队列及after-FE恢复稿；不跑1预热＋3测量、2×t4/W4放大/100%压力，不重复fresh t1–t4完整Preview→Submit→审核→Archive→History。
- 不为每张表/每段时间、全部INFO事件或双build相同ID增加退出机制；保业务、源码/镜像及资源硬边界的最小充分原件。
- 04 warm失败、05工具失败/占用拒绝及全部原值/日志/保护资源保留。取消项写按DC98取消或未验证，不改PASS、不造median/range。
- 本轮不宣称合成大负载、性能稳定性、吞吐或全部资源档验证；不把这些自动转为S6/P7无条件补测，确有目标再另定最小专项。
