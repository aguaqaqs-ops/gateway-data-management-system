# D BE-d 完整 tar：独立实施审核

2026-11-07。独审角色 `/root/be_d_review`，Owner 指定 GPT-6.1-Sol / max；实施为 `/root/be_d_impl`，协调为 `/root`。范围按 [D 工作单 §5](p6-be-d-work-order.md#5-启动收口) 包含 D 及既定联合最终验收准备收尾，不新建第三角色。

**当前状态：F1–F4 已闭环，F5 envelope／下载digest绑定待固定修复；五包静态通过，当前Compose／制品及联合证据仍待。旧事故及失败保留，未作 D 或联合产品 GO。** 设计 GO、清单预检、06 定向结果、04/05 联合证据及 FE3 同制品互通分别记录。

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

## 12. F4 公开 surface 修复及 06 增量核收

4c8的 `run-backend-focused-fixed-pQtmiknA` 原文与四项SHA已核：11:42:11–23，238 passed／1 failed，唯一剩余违例是application直接导入capability内部transport；起止4c8、clean／owner true、command/final1，run.log SHA=`a5eb185d9ccf5dcd73ae83e308c8e0092bfb39fe3b389787958c074ba8d77e10`。按正常产品失败停后续，未掩盖或扩baseline。

固定 **`ff704555f58cdd315daf2807492fab83be320a84`** 在新只读WT `/home/dev/gdds-reviews/p6-be-d-code-ff704555f5` 核clean／legacy、实际import规则和两文件diff：owning package root显式export既有四个metadata helper/type/constant，application只从该公开surface导入；无业务／格式／baseline变化。第三方基准docs先将main推进到 **`b1a43480d426e4e8959fb7cfab5bb2ffeb935227`**，guard正常在本地前置拒绝，未建bundle／SSH／运行被测对象；协调只读核同树后刷新实际expected，没有回退或绕过。后一次source_ready原文已核：11:45:32–33，`transfer-Ogy6zITV`完整b1a／clean／prepare_exit0，bundle SHA=`d39de36998f0e0a29d07fea0d31d6a1711399c223ee1e143039c6b057a5641cf`，prepare log SHA=`565a56767f509884c0b813562ab977e0f852285b6bad6286dc22cb773cc47db0`。实际被测vnext与ff704同为 **`603fb5d217db9612d243d8ea062e94ca02d12bd0`**。

| 06唯一run／b1a | 实际结果 | run.log SHA256 |
| --- | --- | --- |
| `run-architecture-download-hlGAQyFn` | 11:45:54–57，architecture＋download owner主体139 passed，command/final0 | `d325886ee7bacc8fbd6bb6a10906377fadcd31716bd3a5b16fc71be0cadb01d8` |
| `run-backend-selected-serial-KNgMhQf7` | 11:46:25–26，原14文件选择serial-n0，382 deselected，**command/final5，空批N/A** | `eaf017844bf3c09a1c9f47578ac644d683775b2d118480296a7cd00cf7465a83` |
| `run-static-five-423Ms53b` | 11:47:12–29，四包locked offline sync、五包ruff/mypy十项全0、扩展expected=installed=e6ac再核0，command/final0 | `95cbb65963119850d2b54073838a08d9ab5e95d213ace8b67cfc92ef78ef4288` |

已独立读全部原文、实际静态脚本并重算各run的guard／expected-head／command／log SHA，均相符；起止b1a、clean／owner true。静态脚本`static-five-v1.sh` SHA=`5db529da9748d05a5727893bf82bb8e5334fa996efb3798775336847616cfd7e`，fail-fast、受控uv消费，无掩码；mypy分别34／15／26／516／200 source files。Rust未改，继续引用36ed合法强制构建并明确核build-input，不为本轮重跑Rust全集。

**F2／F3／F4关闭。** F2首次GET前全部final refs保护与F3严格FULL向量在c1d／4c8的实际通过owner中，随后仅移层／公开import改变且139补验通过；原380/2、238/1及全部旧失败保留。仅按实际变更组合引用focused来源，不拼称一次全选通过或权威package/image carried。CountingStore的≤2活动句柄／≤64KiB chunk代表性计数字段断言已在download owner通过；不把静态上界冒称额外RSS测量。当前无新容器／制品结果，D整体仍待。

## 13. F5（P2）：envelope 的 digest 未与准备结果绑定

最终接缝静核确认：Preview orchestration只取已授权result的artifact ID后返回prepare，未比 `prepared.bundle_digest` 与 `result.digests.bundle_digest`；History亦未比prepare digest与assemble checkpoint已有`bundle_digest`。若已授权own对象的artifact ID错误指向另一份完整有效bundle，现有tar内部预检会全过并返回200／另一份字节；ArtifactRef本身没有scope，包内部闭合不能替代owning envelope绑定。

已直接交原实施者并认领：保留原授权次序，prepare后／响应头前对owning expected digest，矛盾复用typed503并close prepared，避免泄漏借用；不新增port、状态机、权限矩阵或业务digest。原HTTP owner共用一条有效但不匹配bundle引用向量即可。当前Compose／interop尚未dispatch，先修固定最终候选再一次构建，不浪费旧候选容器运行。F5待固定代码与实际补验；Current reviewed tree=603f，容器deferred，最后镜像仍V2 f8，无D GO。

## 14. F5 关闭与当前 06 本地里程碑

固定产品 **`0ba45e5ef83f54bfb2585f963f9518d32086f942`** 在 `/home/dev/gdds-reviews/p6-be-d-code-0ba45e5ef8` 只读 detached WT 复审，clean／legacy正确，**vnext=`0301aee3a39e3a5dfc37360e9c2062e660eb01ea`**。编写本节前main为clean `0a7c34be7c7c37bdd915eb21251336012706e101`，后移只有独立文档；未拿main代替固定产品审核。

F5修复保持授权先行：Preview在已解析Result的prepare之后强比owning digest；History从原assemble checkpoint取artifact ID和非空expected digest，prepare后同样比较。矛盾在创建响应前关闭prepared并抛原typed503，缺expected不能跳过。这里的Preview分类仅指**已解析Result的digest不等／空值**，不宣称原始DB binding缺少结构键也新增503映射；该旧mapper边界未扩展。原共享HTTP向量确实生成第二个完整有效bundle，再只改本对象artifact指向、保留原expected digest；两端均503／无ETag，清理借用可再取得。正向fake／真实fixture显式同步semantic digest，未拿raw SHA代替。

已独立核本次 `transfer-4IYV7WNF/prepare.log`：11:54:37–38Z，expected／advertised／source_ready完整0ba、clean／prepare_exit0；bundle SHA=`6356e7d690aba586299e4983ee8638f2df206ef58039fb1077db1bcb23830f45`，log SHA=`17cd9a4cc674323b0625cb5fd65b3fa566ccaa39241e8b5901b45b40d2585f0a`。下表位于06 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/`，LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/`；各run完整原文、精确argv、expected-head、guard及四项SHA均核相符，起止0ba、clean／owner true。

| 唯一run | 实际结果／UTC | run.log SHA256 |
| --- | --- | --- |
| `run-http-digest-binding-rBoVUD3E` | 11:55:00–14，三个HTTP owner **74 passed，command/final0** | `28daca20f2edd23b85a1fa69e499681efe1321a2098dc01c7c42aa1c73ea0211` |
| `run-backend-ruff-final-e5Kvyl1I` | 11:55:51，ruff0 | `b1106172e9d9902117080c61b481694f091e8ffd6298ad255e0fabb4e7368b32` |
| `run-backend-mypy-final-wob5kWWW` | 11:55:51–52，516files，mypy0 | `dde47ec37c282e118fb632b31d82982af32eb5655cff37441e2174d285df437b` |
| `run-compose-tar-openapi-ZHVSgrfR` | 11:56:53–11:57:26，现有Submit小Compose **1 passed／32.22s，command/final0** | `89120149839192c49e4d5827fbaf3802078573eccb3c155acbc49719ffe145a2` |
| `run-interop-generate-LZPb1TzQ` | 11:58:36–37，提交内generator实际调用生产assembler／encoder，0 | `457ac3a7da59396008394ebdf62171fa7c2aaf818975a4bec5b7adf7dcb7d455` |
| `run-image-identities-fJ57ziyb` | 11:59:21–57，五镜像config／全部DiffID及同机running桥接，0 | `08618883a19f08afe40db2c9bb84a2ae092f9b8c990894231d29ca88158a2dfc` |
| `run-interop-verify-OeWqqKQW` | 12:01:07，wrapper在consumer执行前拒绝外置.py，**command/final2，保留** | `f9827d7ed88809bee522a19bbcf40a7d41af32ff3da207a9707c31c52921f955` |
| `run-interop-verify-corrected-6TuXooMk` | 12:04:05–06，单次公开python-c纠正，完整tar consumer **command/final0** | `77dc8866fdff679b737740cc129ab3e8fda7c211cbd341b21b31f3626d5f4568` |

最后两run按DC68准确区分：首调用被既有受控wrapper的project target前置检查拒绝，consumer未执行、无副作用；原log／SHA保留后由协调确认仅该步骤单次纠正。纠正后的literal argv仍经 `uv-consume.sh ... run --no-sync python -c`，仅import本提交 `benchmarks.bundle_tar.verify_bundle_tar` 与标准库，两个显式参数为实际tar路径及完整0ba；没有exec外置.py、关闭wrapper或直接python绕锁。不是自动审批拒绝，也不适用来消除§9已运行旧对象的事故。

**F5关闭；F1–F5无未闭合产品finding，D固定代码与06局部验证里程碑通过。** 依据是§11–12实际通过的未受影响owner、两次最小移层补验和本轮三HTTP owner／backend静态／当前小Compose；不拼称一次全选通过、权威runner通过或package carried。原380/2、238/1和所有旧失败、aaa原字节不可复核及旧误跑排除均保留。实施handoff当前态另待固定文档核收；这不构成联合最终GO或角色结束。

## 15. 当前镜像、实际 OpenAPI、同 tar 制品与释放核收

### 15.1 构建与镜像身份

实际最小Compose nodeid为 `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`，明确unset `GATEWAY_COMPOSE_GATE_PREBUILT`，预置dependency-base、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、build network=none；原harness实际build backend／worker后启动，未重复同一次Compose。RS先在b1a本机离线build，原脚本 `repository-build-v1.sh` SHA=`4fd1609b0940e1377e9d310b2609201befb49bad718e97bb28e63e69f38c3778`，原build run.log SHA=`f398f85a20e46bd1ff0a8086771367c5afa1a6b06f4ee11932053dd4aa0cf963`。0ba未改RS build输入，harness按当前source identity确认，无须为了revision标签重建相同RS源码。

五镜像原始身份JSON为 `image-identities-k0fu61o4/image-identities.json`，SHA=`184b2994f39de63432f3145bd3786c1eb4c8e300010aee455e0e007e85cd9661`，LAN同名副本已重算。已读实际 `image-identities-v1.py`（SHA=`ee85f0a00aa47dab5b01f3d5a164251566d52411de9067e9da8a335157916815`）：从docker save的**实际config bytes**求digest，将config全部diff_ids与本机inspect RootFS逐项比较；报告保留全部89项，不用本机inspect ID充当跨节点config digest。

| 镜像 | config digest | 全部DiffID项数 |
| --- | --- | --- |
| 当前project backend | `sha256:2c2e0adb3ef9bac2f8c88a3ef635d91b888b5f6cc6dd5337f0e56d91774ff582` | 13 |
| 当前project worker | `sha256:1279f49a9cdd87261f25b8a5dd665331e8c1f08bbd1e41dc2bee5382210a1735` | 13 |
| `gateway-repository-service:be-d-b1a43480d4` | `sha256:2ac4ad9fda8863bf3a292870f611e61e68992f0096d9c8c6e6540656806cca72` | 28 |
| `gateway-backend-deps:lock-d054366c02fa` | `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` | 19 |
| `gateway-p2r1-repository:lock-6dc9659f0aee` | `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |

`compose-output-eJGTujH4/compose-provenance.json` SHA=`9e3c0e525bb5677d705d870de38e49da309fa988e2077be8926f2c72ba6cea4b`，记录实际三个running容器；本角色逐项核本机image IDs与上述fresh build对应，RS亦一致。backend／worker本来没有revision/source-tree label，准确绑定为guard的clean0ba、当前build context与running同机ID桥接，不能虚构0ba标签。RS实际revision是b1a，build-input-revision=`a6876d560050285321fd9f62942d590a03f35d64`，source-tree=`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。

### 15.2 实际 schema 与共享字节

实际production GET `/openapi.json` 副本 `compose-output-eJGTujH4/production-openapi.json`，SHA=`977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`。已独立读完整schema：两个200仅 `application/x-tar`、Content-Length／ETag／Content-Disposition齐备；Preview缺失404 RESOURCE_NOT_FOUND，History包含404 ARTIFACT_UNAVAILABLE，二者503均含BUNDLE_INTEGRITY_FAILURE。HTTP实际typed分类由原74通过owner核，schema不是其替代。

生产encoder共享制品在 `recovery-lpNIMtZE/interop-0ba45e5ef8/`，LAN副本在上述recovery-copy相同子目录。`index.json` SHA=`199d451123df6a0354e51c92e411aad1770553909d18ff07e6d4fecdd14ea38d`；**bundle.tar为24,576bytes，SHA=`b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`**，semantic digest=`sha256:2be243c36d03ef8f11fe9108283ff814631d1dda4aafa32d45380006fd5ef050`。本角色在06只读逐文件重算八个index数据文件的length／SHA，并读取完整tar原字节：原manifest6062B、原closure5232B在前且与单列原文件完全一致，随后surface2275B及ASCII／中文／非BMP三个长path的Parquet各741B，共6普通成员／4closure entries；路径、顺序、size／raw SHA相符，固定tar metadata与两个零结束块正确。

独立已提交consumer的成功输出还核1个reference metadata，**records closure／logical record count均为0**；此小共享制品不冒充真实records逻辑摘要向量，主旅程及其owner另核records。PAX原字节包含 `12 path=中\n`、相邻record、99／101位数边界和畸形UTF-8／length／newline向量；octal边界／I-JSON max三个size文件仅512／1536／1536B header，均明确 `complete_tar=false`，未造大文件或声称其可完整安装。

协调已以 `57aa092e33` 将同tar／index／实际OpenAPI包提供Owner手动转前端。**FE3/PAX同一tar解析／hash／OPFS安装证据仍pending**，没有FE固定提交及同制品成功证据，不报前端依赖解除或FE互通完成。

### 15.3 释放与当前结论范围

原cleanup脚本已读，`run-cleanup-check-5x362qHI` 12:05:24Z／0，run.log SHA=`4b95b3654f2396026e4d3ca25b03c99922b7ee6dc644f94832fea3bb3083827e`；本人project容器／卷／网络、8000、Dolt／Cargo／pytest／rustc／clippy均为空。`release-O4scz5uE/release.log` SHA=`91da2118722b0ce0801f9ba9eb01b8e715b1efb584dbfeeedae2918adc92047d`，12:05:51Z先cmp本人marker再释放，起止0ba／clean，command/final0。12:07:27Z本角色另只读现场核marker不存在、WT clean0ba、本项目容器／卷／网络和8000均空；未触碰其他角色资源或删除缓存／历史证据。LAN副本20个run的全部四项SHA已重算，18-run索引是cleanup前快照，SHA=`d784bad64ed01670a143c5c05cf5789ff09df1999bd5639d94b558f2db03c7d2`，不称权威runner或包含之后release。

```text
Current reviewed product HEAD: 0ba45e5ef83f54bfb2585f963f9518d32086f942
Current reviewed vnext tree: 0301aee3a39e3a5dfc37360e9c2062e660eb01ea
Rebuild triggered: yes；D HTTP/container consumer与最终交付行为变更
Last verified backend/worker: clean 0ba context于06当前实际build/run；无原生revision/source标签
Last verified RS revision/source-tree: b1a43480d4 / sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
06 local container gate: passed，Submit最小Compose一次；非权威runner carried
Carried from: none（未作package或最终image carried判定）
Deferred: 固定handoff当前态核收；协调对齐04六包权威及其Compose、05 fresh t1；FE3同tar OPFS
Required execution point: 原两角色既定联合准备/核收；DC33最终范围仍由Owner确认后才谈退出
```

本角色本轮只静审固定WT、读取节点原证据／制品与现场metadata，未执行测试／编译／lint／容器或重跑consumer。D本地里程碑成立后继续同角色联合收尾，当前没有联合最终GO、DC33 exit、tag／push或S3声明。

## 16. 固定 41386e12e6 本地 handoff 核收

固定 **`41386e12e6e06843e9db85ec34bc8ad950a9a156`** 已在新只读 detached WT `/home/dev/gdds-reviews/p6-be-d-handoff-41386e12e6` 核clean／legacy、实际两文件增量与handoff全文；0ba..41386的vnext diff为空，tree仍 **`0301aee3a39e3a5dfc37360e9c2062e660eb01ea`**。

**本地handoff核收通过。** Contract已准确限定F5：已解析Preview Result的不等／空expected，以及History checkpoint缺失／不等expected在头前typed503／close；原始Preview binding结构缺键沿原mapper分类，没有扩大V1语义。handoff顶部及§8以实际0ba／06结果为当前态，application prepare／公开capability surface、64KiB工作chunk与各16MiB metadata／join开销计账、唯一test owner及06 Submit／04待跑History边界均与固定产品相符；§5已使用原实际t1 host N1／25769803776B，独立列worker32／8 envelope和N1／M24GiB。

逐项对照本角色§11–15原始核收，handoff引用的guard、实际focused成功与失败来源、serial exit5=N/A、五包静态及增量backend静态、当前Compose／OpenAPI、五镜像config及全部DiffID、同24576B tar／八文件index／header-only向量、12:05:24清理和12:05:51本人释放均一致。历史暂停与恢复有明确标签，aaa首轮三原log不可复核及旧误跑排除仍保留；没有把18-run快照、records count0或FE pending扩大成新证明。

当前reviewed handoff HEAD=41386，产品与最后06验证仍绑定0ba／0301；本次仅Contract措辞和实施文档，无新的image/deployment/runtime/container-harness变更，因此不触发额外构建或重复06 Compose。最后验证image revision/source-tree按§15.1记录，未新增package/image carried判定。**本地handoff待办关闭；原两角色继续04六包权威及其必要Compose、05一次fresh t1的固定候选／完整env／CLI／逐项reasons／各节点路径与guard静核及实际证据收口。** 这些联合运行尚未执行，DC33最终范围与阶段退出、FE3同tar OPFS仍pending；本次核收不结束D角色或宣称联合最终GO。

## 17. ec586 联合04／05执行清单与guard静核

固定 **`ec586cbc2d173931aeed942e37ca44037f5ec0ae`** 已在 `/home/dev/gdds-reviews/p6-be-ad-plan-ec586cbc2d` 新只读 detached WT 核clean／legacy、handoff §9与实际消费源码，vnext仍0301。**静核通过，无剩余实际阻塞；可在协调固定当时clean main完整SHA、逐节点现场前提满足后按清单集中执行。** 本角色未执行节点命令、guard、bash-n或被测对象；本节不是运行通过、最终GO或新的恢复申请。

四份实际脚本已全文读取、独立重算SHA并与06已审版逐行diff：仅节点／hostname／WT／artifact／cargo target特化，以及首次detached WT／legacy创建。named HEAD bundle verify／advertised exact SHA、fail-fast、独立node-run安装文件入口、每run唯一目录、精确argv、原command exit／final exit、起止HEAD／clean／本人owner与四项SHA保持；不增加evidence状态机。均mode664，实际须显式bash FILE；初次WT／证据根不存在与现场空闲后原子mkdir本人marker由§9兑现，既有他人目录／占用不能覆盖，后续仅本人cmp下复用clean WT。

| 固定本地脚本 | SHA256 |
| --- | --- |
| `/home/dev/gdds-be-ad-04-transfer-v1.sh` | `b4c371a552c26e7470bb97f06177667266ab58bbbb29fb694c203df86ea764b5` |
| `/home/dev/gdds-be-ad-04-node-run-v1.sh` | `b86cb3c1174899106c12d1245032a957656ce398d118c2165506b1d5b91e31ae` |
| `/home/dev/gdds-be-ad-05-transfer-v1.sh` | `3b5bfd131af481f922ac454939baee1beac9349c8ec2eccb30c44c3bdb9bcdea` |
| `/home/dev/gdds-be-ad-05-node-run-v1.sh` | `7e053a42c7f70c3dca7fad714775836bf9851a4d3501bc0b2dcfd5367d58680b` |

04使用本节点新 `/home/dev/gdds-test-tmp/wt/p6-be-ad-final-04` 与对应artifacts，**六包权威入口一次**、正式64vCPU节点workers48、Cargo jobs4；原runner两批marker、隔离Hypothesis／cargo清理、locked同步／强制扩展重装和e6ac input核验均由原入口执行，未指定GATEWAY_TEST_BASETEMP（实际前提再核unset）。prebuilt unset、dependency-base preload=1、build network=none，RS与client base的env名和消费源码吻合；逐节点比config／全部DiffID并保留当前镜像provenance。公共fixtures变化不作package carried；同runner已做Compose不重复。最终权威镜像／包绑定留本WT完成，未拿06小旅程当04门禁。

05使用本节点新 `/home/dev/gdds-test-tmp/wt/p6-be-ad-final-05`，先locked offline强制同步扩展并核input，正式工具仍受控 `run --no-sync python -m benchmarks.real_dump_journey`。实际CLI为 `--tier t1 --scope full --v2-input-completeness FULL --kernel-threads 1 --kernel-memory-budget-bytes 25769803776`，输入根 `/home/dev/gateway-real-dumps`；仅选t1两包并由原工具核原size／SHA，不做额外全输入旅程。fresh UUID／不from-step／keep-stack／cross-project／DC32／debug，当前backend／worker先正常build一次，仅同进程复用，原finally清本project。host N1／M24GiB与worker N1／M24GiB、32／8 envelope及单active分开；GET完整读时间／bytes单列只报告，原READY／operation计时锚不改。

已独立读取纯数据 `/home/dev/gdds-be-ad-05-archive-reasons-v1.json`，**1445bytes，SHA=`2868249c224a94c583b648d2db842cd018f4917add2af77a565fd73d39aca698`**，八项与§9逐字一致：INITIAL_SOURCE_UNEXPLAINED、BASELINE_TIME_UNAVAILABLE、GENERATION_TIME_MISSING／INVALID_VALUES／LAST_NOT_MAX、TIME_ABNORMAL_INITIAL／MODIFIED、APPROVED_SIBLING_EXCLUDED。明确仅对可重建测试库逐项接受，保留原UNKNOWN／诊断／事实与resolution审计。原consumer按actual subject digest或issue code查显式reason；未知code、unsupported subject和identity异常继续失败，无force。实际LAN文件SHA及完整JSON作为单一env argv仍待原run核收。

联合运行尚未启动。接下来协调固定actual clean SHA及短source窗口；本角色在该窗口不提交main，source_ready后继续核原日志／manifest／image身份与完整fresh t1结果。04权威非0或身份／缓存／编排保全异常按既定停止规则处理，不以05成功抵消；任务结束只释放本人资源。产品tree未变，本次无新重建理由，最后06镜像／source记录仍§15；04／05当前镜像门禁与联合最终结论deferred到上述实际运行，FE3同tar OPFS及DC33退出手续仍pending。

## 18. a999 联合首轮前提、05实际成功与04待收口失败

### 18.1 两节点实际source及缓存

协调固定实际source **`a999869c7f4714c95ee9a5b82866e52cd265e377`**／vnext0301；本角色在双source短窗口不提交main，两个source_ready后才解除。初次新WT／证据根不存在、无他人marker／运行容器／8000／Dolt等进程，原子mkdir本人marker后传source；原claim日志及ps／disk／owner已逐字核收。claim完整命令由实施者事后逐字转录原工具输入供静核，没有当时另存command文件，不冒称该转录是原命令日志。

| 节点 | 原claim／UTC／log SHA256 | 原transfer／prepare SHA256；bundle SHA256 |
| --- | --- | --- |
| 04／gw-dms-test-04 | `p6-be-ad-04-claim-y7TTADuv/claim.log`，12:26:16Z，`f8b93e7c84e643fd88be0d00019c8d6d929eae7d6c63f90440231afc5b6c08fd` | `transfer-IUOsNXCG`，12:26:24–25Z，`bad842fad3f0ac5c12faf803fc42232a235ffb9ef2ae65a9e29460bd033ea25d`；`f140814f72d7f7695e949e2819317074a5b28ac62c6858c1885aa1269f13045d` |
| 05／gw-dms-test-05 | `p6-be-ad-05-claim-KIM5R8lx/claim.log`，12:26:17Z，`8209ed52fc181a0216da3b32f7e9dc251d912a283d1e4fb95c41f7fce55e7a2b` | `transfer-cwKZNNWF`，12:26:37–38Z，`f71eb6f26828efb0ad87265ebede6d4976faa79e6de8712db9fe800a4278cd8f`；`4adbfaf24cc4c9ec219e4f5fb42adb4bf8ea5376fb0d130958f76392d51cbf46` |

两份不同bundle各自通过verify／advertised exact a999／SHA／clean／prepare_exit0，不要求跨节点bundle archive字节相同。owner副本SHA04=`4680c89153f428b761984de79d3be261f13402803f7ecd30c5a31b782d62b379`、05=`9fe440a74123d50700b327e89ce3fd6cafc73d9ed90d2473009db32c976b87bd`，与现场本人marker相同；独立安装node-run SHA仍§17对应值。

各run均在对应 `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-04|05/` 下，原命令／guard／expected／log四项SHA均已核。04 `run-prerequisites-Q1qbm78j`（SHA=`4f104383e4ef2bcb98174f1077ed831ae89a2025d38d408f37857ca6f63f3128`）、05 `run-prerequisites-9gbq9dXi`（`2eb633dffc51de892fbb750165d68c64562c1e162e0b5a7a0b30acc57a2fb467`）均12:28:09起、command/final0：UV/Cargo offline、BASETemp unset、local uv缓存、legacy、四工具同1.97、Dolt及Docker/Compose均实际到位。metadata脚本SHA=`31269239b278424574101fe2060f88eec1c3353729a8c3b547816b7f87b4c8b2`从实际docker-save config bytes求digest并核全部DiffID；04 `base-identities-e2nfolpk/base-identities.json` SHA=`dee4c57577d2527aa18a56e43f87a4b8d5ac8bf440df381d6e45705d3c46b86e`，05 `base-identities-y_o5a51u/base-identities.json` SHA=`b5343a80611bc0635e026c0a5ee78041ed01f16c7a3affff9043605a33015ccf`。两节点backend／RS base config及全部DiffID独立比§15已审06原来源完全相同；本地Rust／Python config及DiffID也跨04／05相同，04 client-base另保存config／9DiffID且label匹配lock，不将没有06 reference的三类写成source_match=true。

两节点实际 `--print-input`仍完整d054，RS各自当前tag正常offline build0（04 log SHA=`58e74acc3be3c67bbb38a5250a4b6fb417ebb704094c36168197da0891032d6f`；05=`9634b847c87f62fe535a9aadb071c77869281a55cb70bfcd9bc9d1dfa157dbf2`），revision实际a999、source仍a687／13cb。05强制扩展sync `run-backend-sync-3U0NQiGH` 12:32:31–12:33:49Z，log SHA=`0ad22dedda643d6e8e4698838545153a91efce311586470929fb0835b03fa6a9`；`run-extension-build-input-913obiwP` 12:35:22Z，SHA=`d3d9e128c4342a3d7644c84abcd33d4854018c7c6bf840761279673360c1bdb7`，均0、expected=installed=e6ac。测试／编译只在节点，本角色读取Bash `%q`原文，不执行或eval精确argv；一次只读检查尾部用shlex解析ANSI-C引号报错，没有运行被测对象或写文件，原日志核收不受其影响。

### 18.2 05唯一fresh t1实际通过，仅绑定a999

`run-fresh-t1-8skuj66m` **12:35:37–12:40:42Z，command/final0，起止a999／clean／本人owner true**，原log SHA=`66cdeb8c906434bbdfbdf2b63ee438c4537f1a9aab10bedafe5d3a36189e83c1`。完整literal argv及单一JSON env参数已独立读核，与§17一致；LAN reason文件SHA仍286824…。原输入实际为 **`rd-t1-a-v1`／107115B／SHA=`42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`**，以及 **`rd-t1-a-v2`／107066B／SHA=`4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`**，不是另一t1-b数据集。

`final-result.json` SHA=`505f9731235430c21c53ff39316bec1f0f4e22b7465275bdea12e4a04823cf1d`是原run.log在byte offset53374、length40044的**原始JSON行字节**，本角色独立比切片完全一致；不是重序列化或补造结果。保全metadata实际原run `run-preserve-journey-result-7sFbOrhR` SHA=`41f7d3383c1e278320bfd7c5d2977c9c6ac9c68fe2954bc095eff31e77c127bf`。原18步从v1 workspace／upload／preview／submit／repository-read／approve／archive，经repeat-v1四步，再到v2同六步和History，均成功。v1 MO身份N/A；v2实际FULL，INITIAL=v1／MODIFIED=v2，身份SAME_PROJECT；repeat-v1 MO为unchanged／NO_CANONICAL_CHANGE。FULL双pair由requested-mode的F3硬断言在default摘要前实际核过；输出 `preview.pair_count=1` 表示默认 `initial_to_modified` view的摘要，不能据此写成FULL单pair或声称JSON另存了完整manifest。

| 实际完整tar GET | bytes | closure／普通成员 | records closure／逻辑records | GET至完整读取秒（只报告） |
| --- | ---: | ---: | ---: | ---: |
| v1 Preview／MODIFIED_ONLY | 2834432 | 354／356 | 1／0 | 0.529 |
| v2 Preview／FULL | 2660352 | 118／120 | 2／12 | 0.214 |
| repeat-v1 Preview／MODIFIED_ONLY | 2055680 | 105／107 | 1／0 | 0.163 |
| History | 2153472 | 114／116 | 1／12 | 0.183 |

对应semantic bundle digests依次为`sha256:5374345d0c32bf50a0c82c281cd226b1ed2184df198b26cfa23d62624a34c441`、`sha256:3fce1e91a655e612916ec10e7fdc7b34256ba3c66907e0b49a8cdcc8486b3bae`、`sha256:325d83b86a0438158911982e2118d80868afc9718395a160ee9c00a47d622c7e`、`sha256:0215af75516a8804bacba23cc9c5804bb8dd229402688cd383959676930e398e`。它们不是整tar的外存raw SHA。已提交consumer实际逐项核原metadata、全部closure路径／顺序／尺寸／物理SHA、引用闭合与适用records逻辑digest；现有留存是聚合counts／digest／bytes／time、原JSON／log及reason数据，不宣称外置保存了每成员原字节或所有diagnostic／resolution HTTP响应。持久diagnostic／接受仍保留原detected事实由V2 owning规则与本轮实际流程验证，不新增工具字段或evidence框架。GET计时单列report-only；原READY／operation完成锚未改，本轮 `operation_timings={}`，不冒称W1/W2性能证据。

### 18.3 05镜像与释放

`run-journey-image-identities-YSHUiWZd` command/final0，log SHA=`bd1a3f360c86fa926d61e8162cc3030cd4a53e9f476f73e524fbd0de17d50634`；`journey-image-bridge.json` SHA=`0da27b38f0550ee575d3705ea34e61eaf09d83fab4709cf5de9acca87365c1b3`，`base-identities-zdhheiw9/base-identities.json` SHA=`798515259fbe1fb0a189297e35c10e8f26e6ff76e3680e46f632d99da433cbb2`，全部54项DiffID（13／28／13）及actual config bytes来源脚本已核。backend config=`sha256:3d47ed71ec272cabc39d71ef6a845f3a4b2d59c979d5f52b483d9dff6d17b21b`；RS=`sha256:adde25e06a61e4c35585355490ecea7569220367945c3b4b245e3e73e8d4d053`；worker=`sha256:3730d9d2878cc8ddefea51ed368726aa1a7c8af2448c7d3a6d78c0fb0ce18dbe`。同机桥接确实逐项比较原tool的 `compose_image_ids` 与保留tag inspect IDs；原JSON字段名含running，但实际来源是构建tag的image inspect，并未另存container inspect，报告按该来源限定，不虚构额外采样。fresh build／UUID project／原up流程、原tool IDs与config共同绑定a999，跨节点仍只比config和全部DiffID。

05原finally清理后 `run-cleanup-check-qDu6CB70` 12:43:52Z／0，log SHA=`987eaad6058cf1a2289d26e0ab000f9c6b5d110b5956f03951e96fd502f2414d`；`release-8QB9Ypmg/release.log` 12:46:02Z／0，SHA=`f4a1625250c8f88f17db56e1ab4222fbe5d97f8010254d07aff59b78cc661b54`，cmp本人marker后释放、保留WT clean a999。12:47:58Z本角色另只读现场确认marker不存在、本project容器／卷／网络和8000空。完整LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/` 的11run四项SHA全符；旧10-run index SHA=`5f551201c49fabaca2cc1e6a86e2cf72283b78b3602068357931a8b3fbbdf459`与释放后metadata SHA=`f0bb6b07ec725f5243105ecb0bca750e5edf2a3553303b4c1ad43e1c66749a87`分开，不改旧index或原log。

### 18.4 04失败与固定test-only修订，未给联合GO

04唯一原authority `run-authority-six-n3pnBrzg` 从12:32:24Z在a999执行，实际argv已核六包／workers48／全部既定env。backend parallel原 **3 failed／3383 passed**，本角色独立读完整三trace：checkpoint缺closure、reopen缺sidecar、sidecar replace失败后不可locate三例均已得到原 `CheckpointDecodeError`／`ManifestVerificationError`，只因expected `unknown artifact_id` 与D统一的实际 `artifact ref is not available` 不匹配。没有放宽拒绝或原子发布。

固定 **`2ae2d825ea775e5ef35c449d924a9edcc6aa8b81`** 在 `/home/dev/gdds-reviews/p6-be-ad-fix-2ae2d825ea` 新只读WT核clean／legacy：仅两个原owner三行match同步，异常类型／fail-closed／未发布断言不变；产品src／consumer／harness／Rust／deploy／scripts／fixtures相对a999 diff为空，vnext仅tests变为`220ba52851eebf2886a109c32d6dd7f8c1ff80a2`。**该已知修订静核通过，实际补验待；不提前定最终候选。** 原runner serial已见失败标记，完整serial trace及总exit尚待，不写被测WT／不重tag／不启动后续验收。

失败整次不得作为任一package carried来源，下一合格权威仍须六包（原S2b公共fixtures闭包不同），不把部分通过拼整次。05成功只绑定实际a999；是否可为后续仅tests变化的候选按步骤引用未影响证据，须等最终diff及对应owner结论，当前不称2ae或新HEAD实跑fresh，也未作image/package carried判定。A1/V1/V2／D联合覆盖与当前04镜像门禁仍待合格原运行收口，FE3同tar OPFS、DC33最终范围与退出手续继续pending；05成功不抵消04失败，本角色继续同一职责。
