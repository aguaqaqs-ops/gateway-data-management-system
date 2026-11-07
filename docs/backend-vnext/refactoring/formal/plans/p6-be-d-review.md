# D BE-d 完整 tar：独立实施审核

2026-11-07。独审角色 `/root/be_d_review`，Owner 指定 GPT-6.1-Sol / max；实施为 `/root/be_d_impl`，协调为 `/root`。范围按 [D 工作单 §5](p6-be-d-work-order.md#5-启动收口) 包含 D 及既定联合最终验收准备收尾，不新建第三角色。

**当前状态：Owner 已授权恢复；F1 已关闭，F2／F3 正常向量已运行，F4 架构依赖修复待补验；旧事故及失败保留，未作 D 或联合产品 GO。** 设计 GO、清单预检、06 定向结果、04/05 联合证据及 FE3 同制品互通分别记录。

## 1. 固定基线与权限

开始前已核 main 的 status/diff/recent log：clean，实际启动 HEAD `dfc8659744dbb9f763f77b74a3d7484cd9b67f18`；随后协调提交 `00f08cdcf2` 仅记录角色/状态，不回退 main。只读 detached 基线为 `/home/dev/gdds-reviews/p6-be-d-base-dfc8659744`，HEAD 固定为 dfc8659744，clean，`legacy` 指向主仓库本地参考目录。产品与后续修复仅在另建的固定 clean detached worktree 审核，不审 main dirty。

既有结论接缝：A1 已结束；V1 最终报告 `5dc01deeb543d4bdc07da02b0e0c6ba1f1472533` 的 §11 取代被暂停的旧 GO，保留最小绑定／scoped SQL→当前授权→完整 facts；V2 最终报告 `9ec62e82ad9b70776a03954c30edb94a29e1380a` 的 F1–F6 全关。D 的既有产品/容器基线为 `f8fb796f020ab47725359c176fc0e53bfb68aae6`，handoff 为 `3cd4400f9fe794c3126605ffd8abac7f81830b64`，`vnext` tree 为 `3860ed86194e4eafea9cfd408e7e7b5096b24bbb`。这些是既有审核引用，不是 D 的新验证结果。

已读 AGENTS、testing-conventions、比例化保障政策、ADR 0012、D 设计／工作单、联合 kickoff／准备工作单／协调交接、设计终审 §6，及 Comparison Bundle、artifact envelope ownership 与实际读取／保护接缝。按 ADR 0012 审协作 cleanup、正常 I/O、protected retention 和 root/symlink 边界；不重开已结束小节，不加入同 euid 对抗、helper/sidecar、持久下载或 evidence 状态机。

本角色只修改／显式暂存本报告，不改产品、tests、前端、实施 handoff、AGENTS、testing-conventions 或冻结基准。全部测试、编译、lint、容器和取证仅在规定的专用节点；本轮准备未执行这些工作，也未占用节点。普通 finding 直交原实施者，同一审核者复审。

## 2. 清单预检与唯一 owner 接缝

实施者须先提交 [D handoff](p6-be-d-handoff.md) 的精确字段、公开 port、错误和生命周期清单；以下是对已审设计的核收项，实际文件／nodeid 由该清单固定后填写，不把它们当作已实现事实。

| 不变量 | 本轮核收范围／权威验证 owner 的划分 |
| --- | --- |
| 当前授权先于 artifact | 两个公开 HTTP owner 参数化认证、permission、exact scope、readiness/TTL；沿用 V1 scoped 读取次序，不复制权限矩阵至编码或 Compose |
| manifest/closure/成员对应 | 生产 reader 先实际预检，准备对象再交 HTTP；原 metadata bytes 在前、最终 closure 按顺序每 entry 恰一个普通文件，同源同 hash 不同路径仍各发一次；reader owner 验拒绝缺失、损坏、重复／冲突／非法路径及非普通文件 |
| HTTP 错误／schema | Preview 缺失 `404 RESOURCE_NOT_FOUND`；History 缺失 `404 ARTIFACT_UNAVAILABLE`；完整性矛盾为 typed `503 BUNDLE_INTEGRITY_FAILURE`；公开 HTTP owner 核实际 status/body，schema owner 核生成的 OpenAPI：200 仅 `application/x-tar`、准确 length、quoted ETag 和安全 tar filename |
| encoder／长度 | 小型纯向量 owner 核 512-byte header/pad、PAX、end blocks 与实际 bytes，固定非业务 metadata；UTF-8 PAX 按整条 byte length 固定点，含 `12 path=中\n`、ASCII／中文／非 BMP／相邻记录／位数边界及畸形向量；不创建 Dolt |
| 生命周期／预算 | owning ArtifactStore 最小公开 port；单 stream 工作 buffer ≤1 MiB、活动 artifact handle ≤2，既有 16 MiB metadata 上界及保留对象计入内存说明；代表性正常、头前失败、流中 I/O、取消／断连和 cleanup 协作 owner 证明 close／保护释放，流中错误不得补假成功 |
| 生产接线 | 生产 wiring owner 覆盖 Preview MODIFIED_ONLY／FULL／replacement、History 两／三节点、shared、同源不同路径、异 schema、长路径及空表；其他层只做必要 smoke，不全靠 fake reader |
| 真实工具 | `real_dump_journey.py` owner 增加真实 FULL 输入入口，适配 `baseline_to_initial` 与 `initial_to_modified` 两 pair consumer，保留 V2 显式逐项 reason；完整读取两类 tar 并核全部 closure 路径／顺序／尺寸及相应逻辑／物理摘要，GET 完整读取时间／bytes 单列，不改 READY 锚 |
| FE3 互通 | 交生产 encoder 同字节 ASCII／中文／非 BMP tar、原 manifest／closure、长度／SHA、生成提交／命令／节点；前端修复提交及同制品解析／摘要／OPFS 证据由其 owner 提供，不把后端 GO 记为 FE3 依赖解除 |

逐项 Contract、公开 port/prepare result、metadata／stream／close 责任、错误映射、golden 与 test-owner 按固定 handoff 及实际产品核收。发现 producer 不满足既有 Contract 时单独报告，不用下载去重、漏 member、链接、宽松 consumer 或重录业务 golden 掩盖。

### 2.1 固定清单 cf2091eadd 预检

固定 handoff 提交为 **`cf2091eadd4bb8e9a2122e4ed1b76ac8e7e83bbb`**，只读 detached WT `/home/dev/gdds-reviews/p6-be-d-list-cf2091eadd` clean／legacy 齐备。已核 `prepare_bundle -> PreparedBundleDownload` 的精确字段、错误矩阵、ASGI／iterator 双重幂等 close、64 KiB artifact chunks／2 FD、ustar/PAX 长度规则、实际产品文件和 owning 正文／golden 范围。

manifest 本身没有 closure 物理 ref；现有 `_digest.py` 的 semantic closure／manifest payload 和 `_assembly.py` 的 content identity 公式足以确定原 closure ref。清单要求只据此定位并核**原发布字节**，不把重新合成的 closure 当作下载文件，不改既有业务身份，方向成立。root 目录 FD 的共享 read-session 与 cleanup 排他非阻塞锁／锁内 eligibility 重查属于 ADR0012 协作生命周期控制；无新 durable 行、sidecar 或安全主体。

**清单预检通过，可按既定范围进入实现；这不是产品 GO。** 两项常规精度已直接交原实施者：PAX body 由整条路径构造时，其临时副本应明确计入 16 MiB metadata 预算或以有界片段编码，不能以发送切片代替工作 buffer 说明；生产 Preview／History wiring 行须补唯一实际测试文件名。二者不需要重开设计或新增路径限制，产品候选再核实际实现与计数。

## 3. 证据核收与联合收尾

06 仅按现场有效标志、clean 已提交 WT／legacy、离线缓存和实际脚本核定向证据；不把 V2 的 10:39:24Z 历史释放当作 D 可用预约。五包静态与 backend 扩展 build-input 均须核实际来源；非 serial 主体 `-n 4` 与 serial `-n 0` 分开，真空批 exit 5 只记 N/A。失败日志／SHA 保留，修复只补受影响范围，不机械重复完整 runner 或大向量。

既定收尾仍包括：固定联合最终候选和版本清单；04 受影响包权威（公共 fixtures 已变，预计六包实际运行）及必要当前 Compose；05 一次 fresh t1 合并 MODIFIED_ONLY／FULL、Submit／Review／Archive 与两类完整 tar；按实际影响核既有异常小型 wiring。日志需 hostname、起止 UTC／HEAD、exit／SHA、实际脚本和命令；镜像核 config digest＋全部 RootFS DiffID 及运行 provenance，跨节点不使用本机 inspect ID 代替 config digest。权威 runner 已覆盖的同提交 Compose 不重复。

D 局部代码／06 通过只作里程碑；联合最终证据另结论。DC33 最终真实范围仍待退出前 Owner 确认，不自动办理 exit、tag、push 或 S3。前端经 Owner 手动转发；确需前端判断的阻塞问题带具体场景／制品交协调，其余工作继续。

## 4. 当前容器决策

```text
Current reviewed HEAD: dfc8659744dbb9f763f77b74a3d7484cd9b67f18（准备基线）
Container rebuild required: no（本轮只读准备及本报告文档）
Last verified image revision: f8fb796f020ab47725359c176fc0e53bfb68aae6（引用 V2 §10）
Last verified RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Last verified backend/worker config: sha256:99188ad41cef18addc3e6760b45b7fd144a0e0f7fc6e51f0de137e7ac0bfc2b1 / sha256:7485e3f252d6cfd6ea4371a7f263913cdce2e392b8535e89369ed14dc312c028
Container gate for D: deferred（尚无产品候选／当前镜像）
Carried from: none（本轮未作 package/image carried）
Deferred gates: D 收敛候选的 06 最小生产 wiring／必要 Compose；联合最终 04 runner/Compose 与 05 fresh t1
Required execution point: 按已审工作单收敛后执行，精确 nodeid/命令由实施清单固定
```

本准备报告不新增测试通过声明，不取代固定产品审核和原始证据核收。

## 5. 首产品子候选 36edb20086 静审

固定候选 **`36edb2008651c9b5a8cd2616b7f249787c5bfe75`**，只读 detached WT `/home/dev/gdds-reviews/p6-be-d-code-36edb20086` clean／legacy 齐备；按 `9ec62e82ad..36edb20086` 核 D 的实际产品、tests、Contract 与 handoff，不审 main 后续 dirty。真实工具 FULL／完整 tar、共享 Compose consumer、进一步固定向量与节点结果仍属后续增量，本子候选不作完整交付。

同步 `prepare_bundle_download` 在返回准备对象前取得 root read session，读回原 manifest、按既有公式定位并重读原 closure，与 expected bytes 比较后逐项消耗全部成员；这段不藏在 lazy generator。下载仅据最终 entries 迭代，没有按 ref/hash 去重。长度由每 member framing 和两结束块求和；标准 PAX path／size 不改变 artifact size 域。原预检的两项精度已实际落实：PAX 路径逐 16 Ki code points 编码，单 allocation ≤64 KiB；生产 wiring owner 固定为 `test_bundle_download_http.py`。

公开两路由的授权调用在 prepare 前，缺失与完整性错误分型，200 仅 tar；History 原 assemble checkpoint 的 404 路径保留。`BundleStreamingResponse` 的 ASGI finally 与 iterator finally 共用幂等资源关闭，未迭代对象可显式关闭；cleanup 同 root 目录排他锁内重查 eligibility，读 session 内返回 retryable，无新 durable 状态。以上为静态代码结论，不是运行证明。

### F1（P2）：generic 业务 JSON 被新增 metadata 上限拒绝

`artifacts/bundle_download.py` L74–84 将 `PROJECTION`／`DIAGNOSTICS`／`OTHER` 的所有 JSON 都送入 `_metadata_bytes`，L63 套用 manifest 的16 MiB上限并整文件物化。既有 `_assembly.py` L560–610 对 generic JSON／supplemental artifacts 校 canonical 和引用后可发布 READY，没有该产物大小限制；Comparison Bundle 明定 supplemental artifact 是任意可附加的 pair artifact。故已有合法大业务 JSON（即使不包含 ref）会因新下载层被503拒绝；工作 buffer 的 metadata 例外也被扩到了业务 payload。

**已直接交原实施者并认领，待固定修复。** 最小处理是只解码既有有界 reference metadata，其余业务 JSON 复用 assembler 发布时已校验的引用与冻结 raw hash，逐块读回 size/SHA；不静默加 cap、不物化大 payload、不新建通用流式 JSON 框架。由原 download owner 用临时降低 metadata 预算的小型合法 payload 向量证明，不要求真实大数据。

其余待核验收集中留在原 owner：最终 closure 的同 ref／不同合法 path 仍发两个成员、metadata/path/ref 损坏共享参数表、实际 task 取消／receive 断连、生产 shared／异 schema／空表／长路径断言。现有 spec2.4 的 send OSError 测试证明发送失败关闭；该 spec 分支不调用 receive，不能把它单独称为 receive 断连或 task 取消通过。另已直交普通静态精度：composition 遗留 unused `Iterator`、旧 Preview fake 的 `.bundle` 文件名；不另建 finding 矩阵。

```text
Current reviewed product HEAD: 36edb2008651c9b5a8cd2616b7f249787c5bfe75
Container rebuild required: yes（当前 HTTP 传输／后续真实 Compose consumer 改动）
Last verified image revision/source-tree: 仍为 §4 的 V2 f8fb796f02 历史来源
Container gate for D HEAD: deferred（无本候选运行证据）
Carried from: none
Deferred: 收敛候选 06 最小当前 Compose/OpenAPI；04 联合 runner/Compose；05 fresh t1；FE3 同制品消费
Required execution point: 产品与工具收敛后按工作单集中验证
```

本轮只读静审与 diff 检查，未在开发机或节点运行测试／编译／lint，没有 D 产品 GO。

## 6. e3b54b8f71 同角色复审与首轮 06 失败核收

固定修复 **`e3b54b8f71b21431ce1001efbcf974439e3eea2a`** 已在 `/home/dev/gdds-reviews/p6-be-d-code-e3b54b8f71` 只读 detached WT 核增量，clean／legacy 齐备。前置 `1c145727252c842f439094033f48372471780581` 只删 obsolete imports 并把 Preview fake filename 改 `.tar`；main 后续真实工具 dirty 未审。

F1 的代码修正成立：`BUNDLE_REFERENCE_METADATA_KINDS` 仅含既有有界 surface、records／risk manifests／closures、risk report；generic projection／diagnostics／OTHER JSON 逐块 size/SHA，不新增大小 cap。原 owner 新增三种业务 JSON 的下调 metadata 预算小向量、最终同 ref 不同 path 两个普通成员、path/ref 矛盾参数表、ASGI2.3 receive disconnect 和 task cancellation。后两项直接 cancel/receive 语义，不靠固定 sleep/timeout，无需新 serial 时序矩阵；PAX 原小向量及资源 finally 维持。

### 6.1 实际日志与执行前提

BatchMode `echo OK` 成功后，本角色只读核 06／`gw-dms-06` 的原始脚本、日志与 SHA；证据根 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/`，WT `/home/dev/gdds-test-tmp/wt/p6-be-d`。11:07:55Z 现场快照：本人 D marker 仍在（声明 started=11:01:37Z），WT HEAD=e3、clean、legacy 正确；本角色没有占用或运行产品。

`check.sh`／`check-resume.sh` 每步校 clean 和本人 owner，记录 hostname、起止 UTC／HEAD、argv／exit，使用 UV／Cargo offline、外置 TMPDIR/target、jobs4、规定 PATH 并 unset proxy／toolchain overrides。toolchain 四工具均解析至 1.97.0 selector；36ed 强制重装扩展成功，expected=installed=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`。当前脚本 focused 为 `-m 'not serial' -n4`，serial 为 `-m serial -n0`；backend 无 parallel_safe，选区与约定相同，已请实施者下一固定脚本使用工作单完整表达式，不为文案变化重复已过 owner。

| 原日志 | 实际结果／UTC | SHA256 |
| --- | --- | --- |
| `sync-backend-36edb20086.log` | 11:02:16–11:03:35，offline 强制同步扩展，exit0 | `cc0eacc8f9615a531877837661a3f6165297f7d867f11295229c7eae10a215b6` |
| `extension-build-input-36edb20086.log` | 11:03:35，expected=installed，exit0 | `1b12990473ed30492e14a01806f4ed8d691b3730e9dd951202f767920945cbb8` |
| `ruff-backend-36edb20086.log` | 11:03:35，两个 obsolete import，exit1，保留 | `2274c2d154019de8642ed3693ec9e8434cd3f51f56a0972ea764fce20ecfa0d2` |
| `mypy-backend-1c14572725.log` | 11:04:31–11:04:41，test helper Any return，exit1，保留 | `e11d53006633b920e735fda5b509cab2a6515f765a66d487a76598b42ef62faa` |
| `ruff-backend-e3b54b8f71.log` | 11:06:21，exit0 | `07ea626dbd224e035c98d1fe3c5fbf713b23ad415896a2cf7e0b52e7f58849b5` |
| `mypy-backend-e3b54b8f71.log` | 11:06:21–11:06:22，515 files，exit0 | `510f0782e249fdfc862ea850d3899cbab85f3bbd59df6122c5f21da9d09ca66c` |
| `focused-e3b54b8f71.log` | 11:06:22–11:06:38，142 passed／7 failed／8 errors，exit1 | `e75aeb3b607d4caa17b87bee7550288863b6ed27cb6f958b919989f108f8ac85` |

F1 及纯 download owner 的新增小向量在142通过部分；整次 focused 失败，不报全选通过、权威 carried 或 D GO。失败后未继续 serial／Compose／联合验收。一次 linked WT 的 FETCH_HEAD checkout 在产品运行前 exit128，日志及单次 exact SHA 纠正已留存（`checkout-operation-error.log` SHA=`b0fdba6a7a042ed2445ab9692e2b4f2a813af120c2d713e8689bae9e7ec9a133`）；该操作重做不替代产品失败停止规则。

### 6.2 HTTP wiring 前置错误待修

已从原失败输出与固定源码独立定位并直接交实施者：Preview8个 setup error 是新 fixture 传入 `tmp_path/http` 却未建立 control DB 父目录；History7个失败的响应为授权前置 `RESOURCE_NOT_FOUND`，`history_compare_job_harness.history_compare_operation_document` 写 `business_refs=[]`，公开授权无法取得已存 acceptance 引用，尚未进入 bundle prepare。它们不是缺失/size/SHA 错误分类的反证。

原实施者应让 fixture 经过真实 HTTP 受理或填同一持久 acceptance 的合法 business ref，并建立 DB 父目录；保持当前权限门禁与404／503期望，不改产品授权、不放宽 producer 校验。仅补受影响 HTTP wiring owner，其他已通过小向量不机械重复。修复的固定候选、成功 HTTP／serial 判定、后续工具／Compose及五包静态仍待，本轮没有整体产品结论。

容器决策：Current reviewed HEAD=e3b54b8f71；D 当前镜像仍 deferred，最后验证来源仍为 §4 的 V2 f8；无本轮新容器或 carried。所需执行点仍为 D 收敛候选06与联合04／05。

### 6.3 固定 7f25a1657a：HTTP 前置修复与增量成功

固定 **`7f25a1657ab620641eeeafd759366e7ab9456444`** 在新只读 WT `/home/dev/gdds-reviews/p6-be-d-code-7f25a1657a` 核 clean／legacy 和唯一测试文件增量。History fixture 改为实际 HTTP POST 受理后执行原三个 job handler，保留 exact acceptance business ref；Preview 建 DB 父目录。没有改产品授权或错误分类。

06 原始增量日志起止均7f25、clean前提脚本沿用同一 wrapper；仅重跑受影响 `test_bundle_download_http.py`，11:09:44–11:09:52 主体 `-m '(not serial) or parallel_safe' -n4` **21 passed、exit0**，SHA=`e62743e2029562f7062dc7531e4baf42314383e996bce7a9098e967abbff42d3`。独立 `-m 'serial and not parallel_safe' -n0` 为21 deselected、**exit5 N/A**，11:09:52–11:09:53，SHA=`c2519e8d723b19562071a01d891e5fe8c9003e1d12e3e2fe193c777ff7e92706`。同HEAD backend ruff／mypy均0，SHA分别`96c19f635041959383f03c829d02052419a4c2e8928b70a08bec4a1e1b366939`／`62ccafce371c1a34a747cb89543aaaeb970b983ecbfa8b5b6bbdecebaf63cd1d`。本角色已读原文并重算SHA，现场WT仍7f25／clean。

**F1 关闭，HTTP 前置错误关闭。** F1 pure owner 在e3通过且7f25未改；7f25新HTTP范围通过，旧142/7/8失败日志保留，不把两轮拼称单次全选157通过或权威 carried。D工具、完整矩阵、五包静态、当前Compose／实际OpenAPI／同制品及联合验收继续待收敛。

## 7. F2（P2）：producer 的 READY protection 未包含最终 bundle 全部 refs

此项由原实施者在完整tar接线时先单独报告协调，本角色在固定7f25独立确认。Preview `preview_jobs.py` L1996／L2271 和 History `compare_jobs.py` L990／L1112 的 `_required_ready_refs` 只集原 surface refs、部分原输入与 manifest；`assemble_bundle` 返回的 `referenced_artifacts` 明确包含全部 rewritten final artifacts 和原 closure，当前调用方却未将其加入既有 READY refs／保护事务。

因此 manifest／operation仍受保护时，下载真正需要的 closure／final bytes 可以落入普通未保护 TTL cleanup；只保护原 surface refs 无法替代 final ref 身份。它是既有 owning 交付／protected retention 缺口，不是新威胁模型或业务digest问题。最小修复为把 `bundle_result.referenced_artifacts` 并入既有 required_refs，保留原 canonical／source 恢复 refs，并沿原事务／lease发布；不新增状态机、版本轴、sidecar或持久下载保护。

原实施者已认领，固定修复及原生产wiring owner 的 final refs／closure保护断言待核；不重录业务golden。当前产品review HEAD为7f25，容器仍deferred，最后镜像来源／集中执行点同§6，未作D GO。

## 8. 完整候选 d0a22ba91d 与 a7954b6b55 静审

固定 **`d0a22ba91dc46f55db9a32728d3257fd3044fe61`**、后续 **`a7954b6b55`**，分别在 `/home/dev/gdds-reviews/p6-be-d-code-d0a22ba91d`、`/home/dev/gdds-reviews/p6-be-d-code-a7954b6b55` 只读 detached WT 核 clean／legacy 和实际增量。中间 typing 修正`aaa0f4a6f3`、精确 FULL pair 修正`8de2a9a060` 均按固定 Git diff 阅读，不审后续 main dirty。

F2 产品修复仅将 `bundle_result.referenced_artifacts` 加入 Preview／History 原 required_refs；source／canonical 恢复refs、lease／checkpoint／保护发布与原释放／TTL不变。d0新增断言原在GET后且漏manifest，已直接要求按首次GET前屏障修改；a795现从原store manifest读取，在HTTP下载前核manifest、closure及全部final refs受保护。**F2代码与向量成立，实际成功补验待恢复后核收。**

`benchmarks/bundle_tar.py` 将GET完整字节写临时文件，再按原metadata／closure逐普通成员核路径、顺序、size／raw SHA，无caller pathname解压。有界reference metadata核闭合；records调用owning public `open_records_closure` 校Parquet schema／count／logical content digest；generic业务JSON沿F1边界逐块核发布raw SHA。共享Compose consumer与History restart下载均切完整tar。

实际CLI `--v2-input-completeness FULL` 给v2发送INITIAL=v1原字节、MODIFIED=v2；v1／repeat-v1保留MODIFIED_ONLY。默认业务摘要取initial_to_modified，baseline_to_initial必须无变化且身份SAME_PROJECT／DETAILED；全部tar members仍全验。Preview user-visible／completion与History terminal锚在GET前冻结，GET开始至完整读取／bytes独立只报告。V2显式逐项reason env consumer保持，无force。handoff中的N4／24MiB为未执行示例，不能当联合命令；最终host offline kernel与Compose worker须按协调清单分别核，不把测试jobs/workers当产品kernel。

### F3（P2）：FULL 请求原可被单 pair 响应冒充

d0的summary／identity helper都接受1或2个pair，实际v2调用未按requested `v2_input_completeness`强制精确集合；FULL producer若错回旧单pair，工具仍通过且报告FULL。已直接交原实施者，**固定8de修复已核**：实际v2两处传requested mode，summary／identity均强制FULL双pair或MODIFIED_ONLY唯一initial_to_modified；原owner新增FULL→旧单pair拒绝小向量。F3代码与向量成立，实际补验待恢复后核收，不扩大identity矩阵。

06 d0首静态原文／SHA已读：11:14:42 ruff0（`4350fa48bc3b09833295abd4573375fcfc43fc5a407c6b80adb8775863244b88`）；11:14:42–11:14:43 mypy两个新test文件5处typing/import错误、exit1（`f54653969e3e1aad6b3a6060d6b5fe7f1de9343996871faeedb38d24dadd9e16`），按脚本停止。aaa0只修这些类型／fixture，产品不放宽；后续首轮原日志保全问题见§9。

容器决策：Current reviewed product/test HEAD=a7954b6b55；共享Compose consumer／History e2e变更触发收敛后当前重建。06当前门禁deferred，最后验证镜像仍§4的V2 f8，无carried。五包静态、当前Compose／OpenAPI／同tar制品及04／05集中证据仍待，不作D GO。

## 9. 06 执行编排错误与验证停止

实施者报告：传a795时本地纯SHA `git bundle create` 被拒为empty，调用缺少fail-fast仍传旧包并在旧aaa0启动focused；同HEAD日志名覆盖了aaa0首轮ruff／mypy／focused。本角色未曾读取或保存aaa0首轮原字节，**原完整日志不可独立复核**；工具输出保留的首focused SHA `2345ec835d433ff55a548697c0faeebc67ff8cbb8779b27d35b98c23b14a3cc2` 不能代替原文件，不重造或拼接日志冒充恢复。

本角色已只读核现存误跑原文与SHA：06／gw-dms-06、起止HEAD均`aaa0f4a6f32143448c1b55bb1cc8f509643e1d3c`，11:17:02–11:17:18 focused **150 passed／2 failed、exit1**，SHA=`f882a86a8a0e472b80fa2897e61a1ffc4237a1cee9a3a73ffd8526780bedb9c5`；同次ruff／mypy0的现存SHA分别`703b88bf0b64df4e7d1546a25837d75fcbb856a1e648b41ff20339edf0fe503b`／`d1db3f7041a1f443761e8b69d66f57e7e9a1a1ab8f633447ba7670cef46dc900`。两失败为CLI旧expected漏新增mode和unknown ref旧消息匹配；均是原expected更新接缝，不放宽产品边界。误跑结果不算a795或当前候选证据，也不以150通过关闭F2／F3。

因已执行旧被测对象，此事不按“产品前、无副作用”的DC68直接重做。协调按Owner停止规则明确暂停全部受影响测试／static／Compose／04-05；只允许证据保全、本人资源清点释放、标准guard修正与独立静审。恢复前须固定fail-fast、named bundle verify／exactSHA和唯一run目录的可审查调用方案，协调交Owner决定，不新建evidence平台。本角色仅继续固定代码和现存证据／guard静审，不运行被测对象。

## 10. 恢复方案静审：可提交 Owner 决定，尚未恢复执行

固定handoff候选 **`547a38903456aa6e8799c348c66724d1fd068fb5`**（前稿`94b9fe92affdc68a704fa9a7b830022474f9e161`），只读 detached WT `/home/dev/gdds-reviews/p6-be-d-guard-547a389034`／`p6-be-d-guard-94b9fe92af` 均clean／legacy齐备。**恢复调用方案的技术静审可接受，可由协调者据此提交Owner决定。此结论不是恢复授权、脚本运行通过或D产品GO。** 本角色没有执行guard、`bash -n`、被测对象、编译、lint或Compose。

| 固定guard／本地副本 | 完整 SHA256 |
| --- | --- |
| `/home/dev/gdds-be-d-guarded-transfer.sh`；`/home/dev/gdds-reviews/artifacts/p6-be-d/guarded-transfer.sh` | `f83066c0b15a012bf5df673577591910e5b0afd4926553d4f3592ef5edff9d4d` |
| `/home/dev/gdds-be-d-guarded-node-run.sh`；`/home/dev/gdds-reviews/artifacts/p6-be-d/guarded-node-run.sh` | `4eb10c9fc1a8b3b12d4b5ae4cba4d54528d7462d7a5a8f91549facb0e7c979b2` |

已逐行读取并独立重算原文件／副本SHA：transfer使用`set -euo pipefail`、named HEAD bundle、verify、advertised完整SHA及bundle SHA256，目标固定06及本任务WT，任一步失败即停止；不自行启动测试。node-run每次创建唯一WT外run目录并保存自身原文／expected SHA／精确argv／日志，开始核clean、exact HEAD、本人marker；末尾再次核三者，保留原`command_exit`，前提变化使`final_exit=2`，不覆盖历史run。首稿仅start核marker的精度已由原实施者补正。原node-run SHA `3889eb…` 只属前稿，不是本次拟采用身份。

两文件mode664，handoff明确`bash <file>`入口。node-run须先LAN复制到06 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh`，校SHA后经SSH以该文件路径调用，不能`bash -s`破坏`$0`归档。实际`D_EXPECTED_SHA`及命令由协调在Owner回复后固定；恢复前重新现场核空闲并原子取得本人marker，历史释放不是预约。guard不代替owning harness的服务清理／任务末尾资源核收与本人marker释放，也不放宽offline／cache、serial或五包规则。

保全目录LAN副本`/home/dev/gdds-reviews/artifacts/p6-be-d/incident-preservation-rvpm66sO/` 的**40个现存文件已逐项重算全部相符**，`SHA256SUMS` SHA=`78122ba8b893b200c17ad9ae959af5fa7d25cc830f59986043f2b40298ca065b`。静态Git读取确认其中`source-a795.bundle`与`source-typing.bundle`均advertise完整aaa0 HEAD且同hash，支持旧包误传事实；这不恢复被覆盖日志。06原释放log与LAN根目录副本`node-release-UzrHOQAs.log` SHA均=`de06e368c6459639f0f04525cdb6a9763edaa30e85eb3e8ff6a21b97422b8ae8`，释放11:19:30Z；11:24:13Z另只读现场核marker不存在、WT clean／aaa0、无运行容器或8000监听。保全11:19:12Z进程快照无Dolt／Cargo／pytest。旧WT、镜像和证据保留。

更早两次checkout错误须按记录边界阅读：它们发生在不同候选／传输步骤，非同一步连续重做；一为linked FETCH_HEAD，一为不存在的literal SHA。没有失败秒级UTC或当时外置原log，现有`checkout-*-operation-error.log`是事后整理的派生说明；第二时间窗终点aaa首轮原字节也已丢失，只能引用工具输出／历史记录，不能称全部原log独立可复核。第三次旧对象误跑／日志覆盖继续按§9停止规则处理，不借此消除原失败或限制。

### 10.1 暂停期间固定产品补件

同时静读`18b239a95fdd63b33c41bf03d2d18ab71612bd98`：在已排序closure paths上拒绝普通文件祖先／后代冲突及保留metadata路径的子路径，使用原download owner两个小向量；不引入新状态或重复矩阵。`445a19dfe3`仅同步缺失ref的旧expected文案。7c新增interop生成器实际调用生产assembler／encoder，完整小tar含ASCII／中文／非BMP小Parquet，另输出明确`complete_tar=false`的size header-only向量和合法／畸形PAX记录；仅静读，尚无运行制品或前端互通证据。

本轮已静审产品/工具树以547a的 **`vnext=e7dfe478e5abb721a4f968dd692380b3cb05f28f`** 为准，不用94b旧树代表新增18b。恢复时实际clean SHA还会含审核／批准文档，须核vnext与本树一致后再按其完整HEAD运行。F2／F3证据关闭、受影响focused／serial、五包静态、扩展input、当前Compose／OpenAPI／同tar制品与04／05仍待；当前容器deferred、最后验证镜像仍V2 f8，无carried。Owner回复前全部受影响节点执行继续暂停。

## 11. Owner 恢复授权与实际守卫运行

Owner明确回复“按方案恢复验证”，授权记录 **`c1d1beefb1260f21810a6809cc9f8ffb4b6bf78d`** 已独立核；vnext=e7、guard f830／4eb均与§10相同。源码短窗口内本角色只读、不提交main；实施者确认source_ready后才解除。06于11:35:41Z现场重新取得本人marker，recovery根`/home/dev/gdds-test-tmp/artifacts/p6-be-d/recovery-lpNIMtZE`，不是沿用历史释放。

已读原transfer `transfer-UJm9QCM3/prepare.log` 并重算SHA：11:35:43–11:35:44Z，完整expected／advertised／source_ready=c1d、clean、verify及prepare_exit0；bundle SHA=`7842b52cfd0ed2a106d6f1b43142c6a799a011ef217e0614487ed0d37d203140`，prepare log SHA=`2cf115e8683960fdce93cd6174fccaccb05a6058d55cfa3205b0d4e9c95e32e2`。实际node-run文件独立LAN安装、SHA仍4eb。原WT／legacy／vnext均现场核对，没有旧WT误跑。

| 06唯一run | 原文核收结果 | run.log SHA256 |
| --- | --- | --- |
| `run-prerequisites-c2NGDGTX` | 11:36:39–40，local预填uv/Cargo、offline／无proxy、四工具同1.97、legacy正确、扩展expected=installed=e6ac；起止c1d、clean／owner true，command/final0 | `4a0e527b5f4f1c4c906314ceca681f68db7613a722783d85bd15f66412a71ecc` |
| `run-backend-focused-yPq3ZLFd` | 11:36:52–11:37:18，14文件主体-n4／约定marker，380 passed／2 failed；起止c1d、clean／owner true，command/final1，失败后停后续 | `7ff99fbc8320be840074f44245bf74b403a71344edbd82f030ca96b9511067f8` |

两run各自guard／expected-head／command／run.log四项SHA均已独立重算相符，实际读取prerequisites脚本与完整focused原文。F2首次GET前保护、F3精确FULL及path／资源／HTTP向量在380通过部分；不称整批通过，也不以此冒称当前D GO。

### F4（P2）：download prepare 违反既定层依赖

恢复后的两个既有architecture测试指出四条依赖违例：artifacts.bundle_download→capability contracts／transport，以及两个HTTP orchestration→capability transport错误类型。初轮静审漏看此层边界，现按原架构owner修正，不增加baseline／allowlist。此为正常产品失败、guard正确停止，无新编排事故或Owner恢复停点。

固定修复 **`1e22d018bc5df9dc48f65b6a1e2ffe9ee4c9bc8d`** 已在只读 `/home/dev/gdds-reviews/p6-be-d-code-1e22d018bc` 核clean／legacy和实际diff：prepare协调全部语句移至application，artifacts仅纯Prepared DTO／窄typed error，capability与HTTP／benchmark／tests统一低层error；旧prepare入口删除，无兼容转发。语义与资源生命周期未改。附加原Submit小Compose实际GET OpenAPI／tar media断言和SHA输出，保留原provenance／finally；完整History容器矩阵留04权威，06不重复长旅程。F4代码修复成立，受影响owner运行结果待核。

实际新传输目标采用main当时完整clean **`4c8c367789c742c0e70ca09af01f0539e00a609f`**，未回退1e；1e..4c8只有独立基准docs，产品tree同为 **`f228ca42309b6370b8181b5d5282283b4a535e32`**。已独立读11:41:35–36Z `transfer-CtpxISe2/prepare.log`，expected／advertised／source_ready与node HEAD均4c8、clean、prepare_exit0，bundle SHA=`a80891031e8a9dda01c430c300822ca464c702c49413d967f87283ac1f1444c8`，log SHA=`50ff3db20681f1d1c89d70a92c76f7b9f838f5934e2ad7340b87691c2adc718d`。后续只补移层触及的architecture／download／HTTP／benchmark及必要静态，不机械重复已通过未影响owner；serial／五包／当前Compose／制品仍待。

当前reviewed产品为1e／f228；当前容器仍deferred、最后镜像为V2 f8，无carried。04／05集中执行清单另与协调对齐，host t1采用原实际已过N1／25769803776B，worker N1／M24GiB及32／8 envelope／reserve独立核，不用测试workers或开发节点容量推导。旧事故、原aaa首轮不可复核与误跑排除限制继续保留。
