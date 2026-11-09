# P6 S3 正式退出独立审查

2026-11-09。本文办理已获 Owner 授权的 S3 本地正式退出审查；不改写已核产品候选、不代替执行 tag 或 merge，不授权 push 或 S5。详细代码与原件逐项审核见 [S3 E 独立报告](p6-s3-e-review.md) §101、§107、§110–111。

## 1. 退出对象与技术结论

- 唯一 S3 产品及证据 H 为 `f9ef26081dfd4710d3709d9f5fbca24543f84de4`，直接父 V 为 `4b0a2eec725bffb0cf2e753df5f3e5d90e26c3fb`。本人在 clean detached worktree 重核 H 仅改 14 份文档，`H:vnext` 与 `V:vnext` 同为 `5610b7137b97196433cc08797d58165b9880e848`，Rust 树同为 `9d4f84ce0897099402226c77c548c487c4912008`，`git diff --check` 为 0。
- 本人 §110 技术 GO 的提交为 `90ca3ebec400ea91da173e2caf89d2682a2654a6`，§111 post-H 文档核收提交为 `03abc1d912d2f1ecee7b9b5eef90eba623dd272c`。H 在 04 原来源 worktree 的实际绑定 outer SHA256 为 `7e3a673cb68f0c91574c0a797fad74dcc4fd788c00bdbda94a2cc03362e43aea`：六包闭包逐包实比全部可沿用，四包直接指最初实跑 V1e669、backend/RS 两包直接指最初实跑 V4b0；RS、backend、worker 本机镜像 ID、config、全部 RootFS DiffID 和 RS build-input/source-tree 实核相符，node/capture/postflight/outer 均 exit 0，04 worktree clean、六锁不漂、执行者原子标记释放。H 此次没有运行新的 runner、build 或 Compose；其合格结果来自已核来源及身份等价。
- 累计 A–E、V4b0 在 04 的权威六包与 Compose、05 的四档完整 fresh、CT108 的 W3 MODIFIED_ONLY 一暖三测和 FULL 暖身加 r1、一次受控部分聚合，满足 Owner 确认的 S3 最小技术退出范围。因此维持 **S3 技术 GO，准许对上述 H 办理本地正式退出 tag**。原 M24 的 2×t4 Submit 失败、W3 FULL 三测统计 `UNKNOWN`、W4 未运行及 Owner 取消的 18 项照原件保留；性能数值目标只报告。本文未重跑测试或把这些未知写为通过。

## 2. Tag 目标和主线关系

[P6 执行计划 §8.1–8.2](p6-execution-plan.md)要求并行短支线以 merge commit 合回，并在审核通过后打附注 tag、合入；没有规定打 tag 前 H 必须已是 `main` 祖先。[P5 执行计划 §8.1](p5-arch-closure-execution-plan.md)的“tag 指报告提交”是 P5 的具体安排；本轮 P6 S4 的 `p6-s4-exit` 已指向实际绑定的 H，并在附注引用独审回执。S3 的最终独审在 H 的实际绑定后才写，不能为纳入自身 SHA 而移动已验证 H。

**`p6-s3-exit` 的本地附注 tag 应直接指向 `f9ef26081dfd4710d3709d9f5fbca24543f84de4`。** 附注应明确 V/H、上述独审提交及本报告提交、04 H 绑定 outer SHA、六包直接来源、Owner 的正式退出授权、旧失败与取消项、仅本地不 push/S5。不能改指当前 `main` 或 S4 H：它们的产品树不是 S3 已核 H。打 tag 不要求先把 H 变成 `main` 祖先，但 tag 不能代替短支线的合回手续。

## 3. 短支线的可审合回方式

本次只读审计的 `main` 快照为 `f8d3cb353dff127ba158ab10a3dda75f904b7802`；`merge-base(H,main)=e76342ef0b58bb0120fc60d8a063d838140ee28d`，H 尚非 `main` 祖先。H 从该共同祖先后只有四个提交：`1e669c053f2486c50a8413c58de11d923d7f3cad`、`acb417df15d7b9fac277c9f5cf9ff97278f1677e`、V4b0 和 H。逐路径归属如下：

| H 支线新增内容 | 已进入主线的对应内容 |
| --- | --- |
| worker 资源测试的类型修正 | `a39339f18dd45777c1b5f40f34512d60c41271b8` 是 `main` 与 S4 exit 的祖先；该测试 H/main blob 相同。 |
| C Arrow 排序预算边界测试 | S4C 适配提交 `1ecb17f6de4c71ddb001a6829d2222cd28bacb34` 是 `main` 与 S4 exit 的祖先；C 测试 H/main blob 相同。 |
| comparison production 三处 native budget 透传、D 测试和 S3 设计说明 | 同一 `1ecb` 提交将三条路径适配 S4C 的 `canonical_comparison_input`；H、`1ecb` 与本次 `main` 快照均保留 `max_sort_bytes=native_budget_bytes`、三处 `native_budget_bytes` 透传及同 operation 的 `native_budget=available-concurrent_scratch`。D 测试只将旧 `_fresh_view_budget` 改为 S4C 的 `fresh_canonical_view_budget` 调用；`1ecb` 的 production、D 测试和设计说明 blob 与本次 `main` 相同。该移植另有 E 报告 §91 静审及 06 focused 原件，与隔离 H 的 Rust9d4 证据分列。 |
| H 的 14 份最终文档 | 逐个 `H:path` blob 与主线祖先 `c32c8c9d123d918604a16edfc2afb0f8b9367c24:path` 相同；后续主线文档可继续更新。 |

上述矩阵支持在**本地 tag H 后**作一次有说明的、只连接历史的双亲 merge：第一父为届时 `main`，第二父精确为 H，合并树必须与第一父的树完全相同。这种 `ours` 策略的前提是执行前再次核实上述四项映射和 `main` 当前树；它只记录已另行纳入或适配的 S3 支线历史，不把旧 S3 实现冲回已退出的 S4 主线。普通内容 merge、无矩阵的盲目 `ours`、以 merge commit 当 S3 被测 H，均不合格。若执行时映射不再成立，应停止并审具体差异，不能强行连接历史。

**审查结论：`S3_EXIT_TAG_GO`，上述条件满足时 `S3_HISTORY_MERGE_GO`。** 完整形式手续以本地附注 tag 和已核双亲 merge 的实际对象及回执为准；在它们完成前，只能称“技术 GO、正式手续待办”。新 merge 本身不是新的 S3 产品候选，不引用 S4 当前树替换 H，也不推导新的容器或真实性能结果。04 原来源 worktree、镜像、输入与全部原始证据继续按交接保护，后续处置另依已授权白名单办理。

## 4. 本地 tag 与历史合回的实际核收

协调者于 2026-11-09 03:28:07 UTC 在本地按 §2–3 办理正式手续。本人只读重算外置 `/home/dev/gdds-test-tmp/p6-s3-formal-exit-20261109/` 的 `receipt.json` SHA256=`aa179ad52e68e4a99d70c49ce7bf2f0d8a44c6126b2b6d109b8ca4b2151c0738`、`raw.log`=`2bef101c6e88fa27d46a457e5c90c9dcbe7315ab4c12ab09472108c553b967e8`、19 路径映射=`932d6d7d72e2f295b1c0cb0095ff95b6ddef0d697a296cf726f6cc7d422323a3`。映射中的 19 个 `H:path` 和合回前 `main:path` blob 逐项与 Git 对象相同，集合恰为共同祖先到 H 的全部变更路径；H 的 14 文档来源保持原§3结论。

`p6-s3-exit` 实际是附注 tag 对象 `cdfe49ccea0ad51d1ea1798e851736644830984e`，其目标精确为 H=`f9ef26081dfd4710d3709d9f5fbca24543f84de4`。附注引用本报告提交前版本 `c1ed5981280e31c5e1e2e6e8ca8d212330105f05`、该版文件SHA256=`e5f5e6597ae86e52357086c368b0cc6c5f1a84633116eb54325364e7bfc6346a`、技术GO `90ca3ebec400ea91da173e2caf89d2682a2654a6`、post-H独审 `03abc1d912d2f1ecee7b9b5eef90eba623dd272c`、H绑定outer SHA及Owner授权；原M24失败、FULL/W4未知、取消18项和“不push/S5”均明列。本人从 `c1ed:path` 独立重算了附注中固定的文件SHA；本节是tag之后的记录，不回写tag或H，也不要求把自身新SHA嵌入tag。

实际合回提交 `87f4ae305c48cd06dfd3033f41c5a8b50ac3ebfc` 的两父严格依次为本报告提交前版本 `c1ed5981280e31c5e1e2e6e8ca8d212330105f05` 和 H，合并树=`43efa62e3418e8c795b113b26c79aaee6d6919a3`，与第一父树完全相同；`vnext`树=`6368c9c40cf08a97eecf2a0c457a6c16ce448080`亦未变。`git diff`第一父至merge为空，H现为main祖先；原raw记录tag、无内容改动的合并及祖先检查均exit0，收尾clean。该合并仅连接已另行适配进入main的历史，**不是**在main的S4树上重新验证S3产品。正式本地退出与短支线合回手续据此核收完成；仍未授权push、发布或S5，04原来源及原始证据继续保护。

## 5. 正式退出后的状态文档归档核收

本人在clean detached worktree只读审核主线 `71fde55965f709cf58456b8073d7ace4e66d1022`：相对父`5e82866b66a303ef5315c48c104e352db9eb469a`仅修改执行计划、S3累计交接、协调、范围补充和性能报告五个文档，`git diff --check`为0，`vnext`树仍是合回第一父的`6368c9c40cf08a97eecf2a0c457a6c16ce448080`。五文档把tag对象`cdfe49ccea0ad51d1ea1798e851736644830984e`、H、19路径合回`87f4ae305c48cd06dfd3033f41c5a8b50ac3ebfc`的双亲及等树、正式报告提交前SHA、外置receipt/raw/mapping SHA转录准确；最新状态明确H才是S3已核产品源、历史段落只记录当时状态。原M24失败、FULL统计UNKNOWN、W4未运行、18取消项、不push/发布/S5及04原件保护均照实保留。

初稿累计交接首段的“Q18／FE／S4／S5与原基准分别核收”会误示S5已经核收；协调者只改该处并提交`15e4845497bcb51887e1e5bd2372e9ef3bfde1b8`，现明确Q18独立核收、FE／S4与原基准各守来源、S5未启动。本人复核该唯一文案差异和五文件累计差异，diff-check为0，tag目标仍是H、H与merge树均未移动。**POST_EXIT_DOC_CLEAR；本地S3正式退出、历史合回及其状态归档均完成独立核收。** 本次没有运行节点、门禁、测量或新增H绑定；仍不宣称push、发布、S5及已取消或未知场景通过。
