# Phase 6 full4 诊断产物转待验收输入：只读评估

- 结论：**可以设计一次显式导入，将已核 full4 产物复制为待验收输入，沿用可绑定的独立复生成证据；目前不能直接接入现有 CLI，也不能判 INPUTS_READY。** 模板兼容、逐表生成信息及完整验收仍是实际缺口。本报告不授权启用、停止或替换当前 CT108 任务。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。设计建议均交设计会话，由 owner 转交，不直接通信。
- 对象：诊断报告 `eb72d0eb7cfbc4df13621ab33e3f2dd70b301d51`，已有结果复核 `30194dd7c15d1f5662f9d47976b863e6731df9a5`；工具代码 `249c09d0824c5d9716f02f7deb1bb8c154ea4c98`，对照原算法 `20cf0ec87e7e0c068aaa61c33ad49014cae36f52`。设计口径采用 `211eb59921c8e29a4328e7c479a6e1f1bf4faeba` 的输入准备 kickoff §4/§5.4。
- 方法：在 `/home/dev/gdds-p6-full4-import-assess-249c09d0` clean detached worktree 只读核对源码；程序比较 HEAD、detached、clean、AST 与 Git 对象。仅读 CT201 现有证据副本，重算 summary/result/provenance 和 accepted summary 摘要；不访问任何节点，不执行生成器、物化器、测试或封包，不读取运行中输出。真实数据只输出计数与摘要，核对程序经 stdin 执行。

## 1. 已具备的复用基础

249 的 `p6_w4_synthetic._make_w4` 与 20cf 原函数 AST 相同；共享 synthetic 模块所有函数/类中仅原 `_make_w4` 变为转调。backend/shared 产品源码树、两包 uv.lock 和 backend Python selector 的 Git 对象相同。因此机械拆分本身不要求重生成；不能把该结论推广到今后修改的算法、共享 helper、规则或输入。

已有[结果复核](p6-w4-full-input-diagnostic-result-review.md)独立核对了四单元真实运行、各档首次/重复 SQL 与完整包字节相同、源不变、完整包非 SQL 成员保留、日志身份及退出清理。可以引用该独立生成事实，不应为了建立新目录再次生成同一批字节，也不能把复制文件当成一次新的独立生成。

本轮重新计算 CT201 副本摘要，与结果复核匹配：summary `423f8937ae1378701d6e571931a0ad506e028e3c8199bdd3d3cc355443588d08`，result `afeebf2d4f6eb19afe564ed1d8b53fda02df68690b82a4781b0bbb9121232ae0`，provenance `8e8ec1c579b29181d2332b9ac7a847e23062427886d8dfe3d096740a0d1fa0de`；accepted summary 为 `c31c18f6d17147b3edbfb0e0655c5edd8db99245318acd05f433e2b12e1b3227`。本轮没有重新读取节点大制品，导入时仍须核对实际来源和复制后字节。

## 2. 最小补核对与阻塞项

| 项目 | 最小要求与目前缺口 |
| --- | --- |
| 来源与参数 | 固定 accepted summary、原始 v1/v2 包、2×v1/v2 实际 SQL/包、W4 rate 0.1/1.0、生成实现及相关依赖。full4 仅使用 2×v1，不能代替 v2 的来源核对。v1/v2 未变化副本检查及 accepted 2× identity 必须保留；历史证明的输入/实现绑定不足时补相应检查。 |
| 模板兼容 | 正式 `build_w4` 经 `_generate_pair` 使用原始 v1 包；诊断使用 accepted 2×v1 包。前者包 SHA 为 `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675`，后者为 `74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c`。包摘要不同不等于不兼容，但现有诊断只证明相对后者保留成员。须比较成员顺序、名称、类型、非 SQL 内容/metadata，以及 SQL 成员被替换大小/内容之外的有效 metadata，特别是 PAX。连同相同 repacker 的处理证明两模板产生同一目标包；不能只比较 XML 摘要或忽略 metadata。 |
| 独立重复 | 绑定已有首次/重复的四个单元、实际 SQL/包摘要、代码及源身份。模板兼容成立时沿用现有证据即可；若需改包，保留原 SQL 独立生成证明，对两个已有独立 SQL 产物分别用正式模板重新封包并比较，新记录明确是重新封包，不称重新生成 SQL。此为未来定向操作建议，本轮未执行。 |
| 逐表生成信息 | full4 单元 JSON 只有表数和前后总行数，没有 `_make_w4` 返回的逐表 inserted/deleted/updated、位移及 unavailable 明细。249 的完整 summary 要消费这些信息。须由设计明确补取方法：从冻结输入/输出及算法核对逐表变更与位移，区分事后验证计数与历史生成记录。仅做 census 得到 after 行数，或按总差额推导插删改，都不足；尤其 keyless 与 ordered 表不能凭总量拆分。不能复制旧失败 W4 的报告。若无法等价恢复某项证明，只补做该项所必需的计算，不默认重跑全部生成，也不能将缺项填零或标通过。 |
| 完整验收 | 四个输入的 full Preview/business/canonical projection、三种根的 census、全部 dataset COMPLETE、manifest/census dataset 集合相等、ordered census 完整性、逐表计数及 expected-input manifest 均须完成。绑定 datasets.json、继承 baseline census、验证器和实际包的身份；未变化的继承数据仍按原规则核对。full4 没有执行这些验收，生成成功不能替代。 |

冻结的 2×v1 SQL SHA 为 `a4b45a455d386845a49eca4b53e6fd3d18aacf51f4630606b41eedf6f3429b7e`。accepted summary 还记录 v2 包 SHA `121dc3b0e0418a76e2563111970dd136cf00d0942c83f37b8cc19597995b6d20`、SQL SHA `0aabe9205b33fe562e6485515a56e5354eb05776cbac5004b30145aeb4086c7b`；本轮读取的是接受记录，没有新核对 v2 实际文件，不将记录存在等同于字节核对通过。

full4 的原始输入 873,428 行，与 accepted v1 的 873,863 canonical 行是不同层级计数；不能为了使其相等而调整冻结口径。

## 3. 显式导入的最小方案——交设计会话

现有 249 `--phase validate` 要求匹配的 pair、w4-10pct、w4-100pct 三段 receipt。历史 accepted root 与 full4 根没有这些 receipt；`all/generate` 遇缺失或不匹配会重新生成。故当前不能通过 `--reuse-root`、手填 JSON 或复制目录解决。

建议在工具内增加一个范围明确的显式导入入口，复用现有完整验收函数，不增加通用恢复状态机或顺带改变 1/2 路 CLI：

1. 显式指定冻结 accepted 2× 来源、full4 产物与独立重复证据、正式模板及相关实现身份。完成前述核对后复制到全新根；规范化路径拒绝与任一来源重合或落入来源根，保持历史 accepted 根、full4 根、当前运行根及失败记录不变。复制前后均核对大小/SHA。
2. 写入**当下的导入来源记录**，分别引用历史生成事实、现时模板兼容/计数检查与后续验收。不能声称过去运行过新 CLI、补写历史 generation receipt、伪造起止时间或把当前代码 SHA 当作历史生成代码 SHA。记录只需表达有限的来源和检查结果。
3. 导入结束仍是待验收。原完整验收全部成功后才发布最终 summary/expected-input manifest；失败保留证据、不发布 READY，不自动回退到旧 W4。适用的 DC66/DC68 与停止规则不变。
4. 定向验证覆盖公开导入入口的成功贯通、来源/模板/重复证明不符、缺逐表信息、来源目录嵌套及 symlink 别名、验收失败不发布，以及原根不变；05 focused 与五包静态后交固定代码和 handoff 审核。无需为这个工具入口重测已完成产品场景或重建冻结产品镜像。

这需要设计明确扩充“诊断产物只能作诊断”及历史无 receipt 不自动转换的现有使用范围；它是一次明确的新导入，不是追溯改变诊断授权。本报告只提供建议，不构成实施或切换授权。

## 4. 对当前任务的影响

复用有望省去重复 W4 生成与已有独立确定性验证，但不会免除完整验收；尚不能估计能比当前剩余任务快多少。当前 CT108 到哪一步、哪些检查已完成，由持锁实施会话提供；本轮没有读运行中目录，也不建议仅凭“full4 约 48 分钟”立即停止当前任务。

先明确上述模板与计数补证的成本，再比较当前剩余工作，决定是否值得采用。已完成场景、H3 接受的 2× 输入、旧 W4 作废状态和冻结产品口径均不因本评估自动改变。

本轮仅评估文档与静态身份，不触发镜像重建，无新增产品/image revision 验收结论。仅显式路径提交报告，不改设计或产品、不推送、不打 tag；审核 worktree 核对 clean/HEAD 不变后清理。
