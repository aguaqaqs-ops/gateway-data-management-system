# P6 S4 最终退出独立原审回执

- 原审核收对象：最终产品 `V=6786b28a3506feab3d8eac7d1288c8b22525bb8f`；交接与退出候选 `H=1e778aae0522db75ea1f507ecfa83a6d7b714d65`。
- 结论：**S4_EXIT_GO**。A–D各节原审已GO；E在V的实现、Owner DC98固定范围内真实业务与有界资源已GO；H在来源04同一worktree的六包闭包、RS构建身份及当前镜像绑定已实际通过。可按Owner已授予的权限在H创建本地附注 `p6-s4-exit` tag。此结论不授权push、S5或S3退出。
- 审核边界：本文是H固定后实际原件的独立回执。H未重跑runner；按仓库规则逐包直接指向最初实跑V，镜像按同04来源身份沿用。旧失败原件及未运行范围仍保留原状态。

## 来源与门禁

A V`fb9c7fbcd95b411d7598ade2a93bc8a7e6514697`、B V`788ed36e7742a067bf01c16ad2e6aaed2fed91fb`、C V`48053253f9a3c46b0d227167a4d0ca1f8ad94bf3`、D V`41d1944208fe99911df0a15641ab651505d1274c`的原审GO及原件见各自已归档报告。E正式Rust tree `e2a901417b19259ece669637a41545e774261445`。04 c9e (`c9e9b3e74ab2e2895f9e0f6aac78740e7f48f008`) 在clean、已提交同worktree全六包runner exit0，原runner SHA `a32acbdb407b3059222ad786dfec4c98b7a581195d549f4ea741a790fcf4baae`；其后V6786在同04同worktree实际backend+repository_service两包runner exit0，原runner SHA `7e4a066156890ab8cbca03b4e6fbfed6bad17682e1fde4eceaae322c592128e5`。另四包直接沿c9e，未声称在V重跑Rust。V04正常Compose本机build与三镜像原身份记录SHA `1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`已独核。

H在clean detached审核worktree `/home/dev/gdds-reviews/p6-s4-e-final-h-1e778aae`窄审，`H^..H`只改协调、handoff及原E报告三文档；`V..H`全部仅AGENTS/docs，无vnext产品、测试、依赖、Docker/Compose或harness变动，diff check清洁。归档的原E报告与worktree外原创快照逐字同SHA `978fb940253e55665aefefd4774963b330999e59d7d33bbfad16d94c7c02f7f9`。

H首次04绑定r0在实际checkout H后因独立外层未继承原authority SSH Cargo PATH前缀而以node/outer exit1、`status=HELD`停止，六包compare尚未运行；原result `35f86963f0c7a1fdc5cb75aa07591c4e31a724483cedda8142c343861f96d549`、manifest `0bcc208e116109dec4e188524b47d3f1e9609f5024b6f42116eea6924a343701`保留。受控恢复于04 03:06:26–27Z把原来源worktree从H恢复V、六锁不变、clean，并仅释放本人marker；outer SHA `a82ff1498ecab6fc6176a458e8fcdbd6d63211afa1bfd62278bd7df5988eb56b`、receipt `9fed9ff6bedde6f132ecfb911502582858380dfd7dd326410cb59a155f1cd572`，我逐实体核对。r1远端入口精确沿用原V authority的Cargo PATH前缀与四项unset，原六包/身份守卫未删；DC68首轮工具修订，不把r0写成门禁PASS。

H r1固定外层SHA `927fe129b592130cec290801296a053652e766e7bcdd27dabe91ca7eb8739244`、node `b84adc137a418d80ce13de556e9db4bb6ad79867c33483bd9b073929d0285030`、bundle `f0a13412059bc01046c5137874bc31ac82a74d40b8ea9742cb36690b2c2e80f9`，bundle verify exit0、唯一HEAD精确H。04一次实际执行03:07:49–03:07:59Z：stage与bind两段各自原子本人marker并释放，node/outer/capture exit0，控制端 `S4_FINAL_H_ALL_SIX_CARRY_RECEIPT=1`、最终来源worktree H clean。控制端原outer `a42395b7769cd79ab6ee1acb0a3994bac6f7b4f188acb15c05dbf335c7240d95`，captured result `9387cdffedb67b176fbf1037006a3e309321e92872a040ed9e09566629a540da`，14实体manifest `d4800968be0566e0d56018529ee37eeba75dd1238e42cb1cb56d44a5bdb8215c`；我重新计算全部14实体，零失配。result为 `status=ALL_CARRY`、`closure_pre_release_pass=true`、`marker_released=true`。

六包`current-*.json`均H、clean，`compare-*.json`与result逐字段相同，六个 `source_total_digest == current_total_digest`、`changed_components=[]`、状态均“可沿用”。rust/shared_kernel/repository_contracts/repository_client分别直接指c9e最初合格原manifest；backend/repository_service直接指V6786最初合格原manifest；原六source manifest SHA与上述两个runner原件固定。RS在H重算build-input `e76342ef0b58bb0120fc60d8a063d838140ee28d`、source-tree `sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`，与原V镜像标签逐字段相同，candidate_sha为H。04现存RS/backend/worker三tag的本机image ID、所有28/13/13 DiffID与labels分别精确等于原V保存身份；没有重tag、重build、sync或runner。05标准t4用的镜像另经stage2跨节点config digest与全部DiffID对04权威原身份核收，未跨节点比较inspect ID。

## 真实业务、资源和限制

Owner现行DC98仅需冻结官方真实t4 v1/v2一次生产首次与增量流程。05独立执行r1一次（02:44:21–02:50:31Z）outer/node/capture均0：v1 Preview→Submit使技术main精确前移、真实Repository exact-commit独立读→审批/Archive建合法BaselineHead；v2同项目MODIFIED_ONLY Preview→Submit再次前移并确读。两版完整312表Catalog schema与逐表count摘要、五代表表内容对原B+Contract独立预期相等；`app_cfg`各24行SET从旧B内部UTF8按正式Repository wire `list<utf8>`独立映射，完整typed row multiset相等，wire digest两版均 `sha256:2c9c580537840e71b6d35f4704a9ade016adbc8521894e1483621d28da696a93`。对应原件outer SHA `142a2b50d9b5079c0ae83f382935b05d5e98d347ed04690247085aaa6c0b3cc2`、business result `3cf9db7a9e8dc7a76a7f871497dbaebacc339628c27e986a6a430e4d4a5d89cb`、13实体manifest `ead2315ba21ea79362aec105488db5ec557bc4bc9f84b470bfd6adfcfd47f317`均已由原E逐实体实核。首次312表TABLE_ADDED REBUILD、增量27候选=12PATCH+13阈值REBUILD+2缺before REBUILD，SQL字节50,566,368/2,125,772，旧B SQL/golden不反填。v1/v2 Submit调用至HTTP核main的保守单次观察104.105179/77.447006秒，仅记录DC97参考目标事实，不是稳定性能统计。

05同一真实旅程固定N1、M40GiB、worker envelope48GiB、reserve8GiB，32 CPU/64GiB guest、worker cgroup memory.max 51,539,607,552 B、peak 926,642,176 B；三服务OOM/重启均0，技术main及Repository数据均核，TERM后backend/worker exit0、RS exit143且其stderr明确application shutdown complete，全部停止并释放本人标记。低RSS不据以缩预算或默改默认。S1a的旧/现SQL逐字节与私有Dolt表结果仅是generic planner/Rust facade组件证据，不冒生产worker容量。

旧04 W3 FULL warm外层Repository checker FAIL、05早期工具FAIL、H r0工具FAIL及其原件保持原值；旧W3差异经独立旧B24行与真实Repository逐字段复核仅SET内部字符串/正式wire list口径，不倒写原FAIL为PASS。原M24基线/S3容量失败仍原样保留；本次M40成功不等于M24成功。DC98撤回的28/16/12样本、History、合成压力和1暖3测均为取消/未验证，不推导吞吐或稳定性能，也不自动转S6/P7。S4退出不等于S3退出。

**最终签署：S4_EXIT_GO，允许root仅对H作本地附注tag；不push，不开始S5。**
