# S3 独立 kickoff 审核转交提示词

Owner 可将下面正文直接转交独立审核者。固定候选由本轮最终回复的完整提交 SHA 指定；起点 `5dde965a65`。审核者先解析该 SHA，不以移动 main 代替候选。

---

你负责 `/home/dev/gateway-data-management-system` 的 Phase 6 S3 详细设计与 kickoff 独立审核。审核候选为 Owner 随本提示词提供的固定提交；精确范围为 `5dde965a65..<候选SHA>` 中本轮 S3 文档及 owning Contract/总设计的定向修订。先 `git show --stat` 确认路径，额外并行提交单列，不混入本轮结论。

授权为只读核对源码、Contract、提交/tag与现有证据，创建只读 detached 审核worktree，起草并本地提交本人审核报告。不实施、不push/tag、不改产品/冻结基准资源，不创建额外角色，不用设计者的自检代替独立判断。本次不为审核设计自动跑全量测试/真实旅程。报告建议路径 `docs/backend-vnext/refactoring/formal/plans/p6-s3-kickoff-review.md`；先查归属，main按显式路径提交，不暂存他人文件。

必读 AGENTS、testing-conventions、比例化/Rust政策、P6 design/execution/DC，S2b最终exit注释与E review，最新BE-a/d联合退出及FE3b评估末节。主要审核 `p6-s3-design.md`、`p6-s3-kickoff.md`，并追实际 `application/pair_pipeline.py`、Preview/History/Submit、comparison、risk_evaluation、Rust comparison/records与PyO3、S2b Arrow/预算/生命周期。代码起点vnext tree `56720104af34a1eb677336f57bdbc07444a56615`。

重点逐项核实：

1. standard/keyless/ordered共用内核是否覆盖现行语义；原型不能算已交付；负零/NULL/UTF-8/JCS排序、重复次数、LIS并列和两种记录顺序是否准确。
2. 三族Arrow schema/nullability/metadata/detail policy是否精确；流式JCS能否保持字节/content digest；1024行组、raw SHA与冻结golden是否明确，是否藏格式变更。
3. 去除写后全份回读后，真实读取raw/content/schema、I/O失败、closure/READY屏障是否仍成立；是否误增新的恢复机制。
4. 风险是否只取必需Arrow列；现有排序/标注编号/table和pair上限/组合信号是否保持；内存重放与写入是否有界。
5. 去重完整key是否包含规则正文/版本/两侧schema/内容/key/存储/scope；含表名身份是否导致miss；重绑定digest、失败取消及预算行为是否准确。
6. Arrow owner/FFI/GIL与共享池、输入/索引/输出/JCS/writer/风险/FULL驻留是否全部计费；仍为N1/32-8-M24，不以06容量代替生产预算。
7. DC78旧实现/临时差分删除与业务断言移交是否可执行；是否误删Submit独立consumer、永久保留oracle，或以Rust生成expected自证。
8. FE3b稳定接口、S4/S5边界、原基准职责是否保持；W3/W4/FULL/100%压力起测、统计及节点安排是否足够，是否错误沿用S2b t4或把W2行比较收益虚构出来。
9. A–E依赖、focused与最终门禁比例、失败停止、候选与证据绑定是否可实施；是否还有真正改变核心方案的Owner决策。

每个finding写具体源码/Contract证据、场景、影响、严重度、最小修复或选项与推荐；避免因内部实现选择扩建治理。输出明确 `READY_FOR_OWNER` 或 `CHANGES_REQUIRED`，列残余未知与不可推导结论。没有运行的验证不得写PASS，旧阶段技术GO不等于S3启动。经Owner转设计者修订，再审固定增量；最终仍由Owner确认实施范围及启动授权。
