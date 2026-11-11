# BE-b 实现与产品验证总结

产品 V=`37fe3a87d28ac5fc4f78bf2007260aefc06ecd12`，vnext tree=`2faac9fc1da9a6fd15eddef894f5c6e1652fba95`。**最终 H、04同一固定树的脚本实际 carried/容器绑定、全范围证据核收和附注 `be-b-exit` 待协调者收口；本页不预记退出。** 即使文档/FE4a合入后的vnext tree相同，也不代替实际闭包判定。不push、不部署，不代签FE4b。

本轮落地SQL COMMENT与精确历史presentation绑定、Business Navigation v1、Surface/Bundle v4、最终Parquet五列locator、双侧公式与device别名、稳定pair/view/code。注释不进入canonical/comparison/cache身份，实际仅改注释Submit仍NO_CANONICAL_CHANGE；导航由typed比较/风险/locator完整事实归约，不重算算法。17个backend-owned固定场景、五类golden与真实生成器替代手写导航/诊断；原FE4a八文件保留原字节/SHA，无兼容别名。七项前端交付与完整原件索引见[FE4b交付](be-b-frontend-delivery.md)。

| 产品证据 | 实际结果与原件 |
| --- | --- |
| 04权威阶段门禁 | V，run `20261111T055102Z-cc3ccbdc2fd8`，rust/backend均实际run/pass，backend4178并行+98串行（含容器）；其他四包未请求，不称六包。起止clean同V，05:51:02–06:10:56 UTC，runner/stage exit0、占用释放。result SHA `350cc78acb68f8a7984f7c9e9dd8a627facf4d0ae8ce0fb31762d245ca420905`；runner SHA `9ae59e20219600fe42b0c340e0c3e408e3de73ad20ecc1b0aeb803342dc0fa75`。 |
| 06 fresh最小真实链 | 同V、独立t1/t4栈，05:51:58–06:07:59 UTC，MINIMUM_CHAIN/SHELL_EXIT0；t1 v1 MODIFIED_ONLY、v2 FULL、Submit/Review/Archive、History2/3；t4仅为History必要建点、MODIFIED_ONLY与History2。原result SHA `66e20b1c63843beab8503ab912f5a5973c5a59a3526232a74db33771799a407d`。 |
| 导航/定位与资源 | t1 History2/3实际locator各6行；t4 History2为12 locator/60行，并独立核1908次筛选计数、660个定位cell。两worker无重启/oom；32GiB envelope内cgroup峰值222130176/995536896字节。含setup的t1/t4耗时305.58/641.14秒只报告，不作性能基准或提速结论。 |
| OpenAPI/产物差异 | 当前t1/t4生产原件均79082字节、SHA `ce58f20a209883983d270e6f9d758044a22ce35e15e11eee137d1595f92ac079`，与FE3c/S1a原件raw及规范化完全相同。保留同输入t1v1 literal集合/递归字段机器diff：S1a→BE-b成员354→356、13增11删；manifest11/62、closure34字段不变，Surface独立成员新增30字段路径。fresh路径变化不归一隐藏，完整索引见交付。 |

04原目录 `/home/dev/gdds-gate-results/<V>/20261111T055102Z-cc3ccbdc2fd8/`；06原件交换目录 `/home/dev/gdds-stage-exchange/be-b/b5-real-37fe3a87d2/`（run.log SHA `678aaab91fe8b4f47afa6a2c04c95f19acf66b1b10ae08cb3caf5cc623438421`）。七个服务/依赖镜像真OCI config及全部有序DiffID原件 `image-identities-v2/identities.json` SHA `923de66a5a9ebb3ef1d49768e6aa9467a4699afad3f1474ce9ce24343dedbacf`，逐blob与rootfs核对通过；不以本机inspect ID替代。offline/LAN预填充边界保持；历史uv缓存来源为UNKNOWN，如实保留。04/06本人占用均已释放，原输入、成功/失败、服务日志、tar与持有消费者的worktree保留。

失败V571仍为失败：04六项backend失败未沿用其Rust部分；架构公开API/真实fixture facts修复后原审GO，新V实跑。06旧History3发生SIGBUS并停止，SQLite preflight关闭raw FD释放原锁的问题已以O_PATH修复且原审GO；具体SIGBUS触发时序未证明，旧证据不改写。B0–B4及B5修订的原审结论、完整失败/限制和最后全范围核收由外部阶段日志/正式handoff承载。未扩大t2/t3、t4完整旅程/多轮性能，也未启动前端产品接入或截图。
