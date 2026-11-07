# D BE-d 完整tar：实施工作单

2026-11-07。Owner已授权D，默认在V2独审GO/结束两角色后启动；若前端主要受下载阻塞可说明理由提前，当前没有调整顺序。依据[BE-d已审设计](p6-be-d-design.md)、[最终设计独审](p6-be-a-d-archive-design-review.md)§6、[联合kickoff](p6-be-a-d-kickoff.md)§1.1/§3/§4，不能以本准备文档宣称实现或FE3依赖解除。

## 1. 实际入口与交付

当前实际入口为 `bootstrap/composition.py::LocalArtifactBundleReader`、`http/dependencies.py::BundleReaderPort`，均仍以`tuple[name, iterator]`只传manifest；Preview `http/orchestration/bundle_stream.py`及`http/routes/preview_results.py`，History `http/orchestration/history_compare.py`及`http/routes/history.py`。Artifact公开接口已有 `artifacts/store.py`的`get_ref/open_buffer`、`artifacts/bounded_store.py`的`read_exact/verify_readable/set_protection`，实际adapter在`infrastructure/artifact_store/`，不能为了tar直接散落调用私有store方法、整文件locate或一次保留全包FD/mmap。

本节将这两个公开路由切为一次完整、不压缩POSIX tar（application/x-tar）；metadata为原发布字节，顺序manifest.json、artifact-closure.json、最终closure每entry按顺序一个logical_path普通文件。共享只以assembler最终closure为准；相同source/hash的不同合法entry仍各发一次，禁止下载去重、hardlink/symlink、省表或添加其他业务成员。业务表/records/风险/摘要保值，producer不满足Contract时单独报告，不静默改golden或放宽前端完整性。

开始先提交 `p6-be-d-handoff.md` 的精确port/准备结果字段、错误类型/映射、生命周期/close责任、encoder/长度规则、Contract/OpenAPI/测试/golden改动清单，再产品写入。实施者写产品/测试/owning Contract与handoff，审核者只写`p6-be-d-review.md`；协调者维护启动/总交接。新建每节实施/独审两个角色及模型在启动时记录，不使用前节角色或额外子agent。protect dirty、显式暂存、不推送/改写引用提交，不写frontend/前端文档/AGENTS/testing-conventions或冻结基准资源。

## 2. 必须成立的传输边界

- 精确鉴权/scope/readiness/TTL在artifact读取前；维持Preview缺bundle404 RESOURCE_NOT_FOUND、History不可用404 ARTIFACT_UNAVAILABLE，完整性矛盾/摘要或大小损坏 typed503 BUNDLE_INTEGRITY_FAILURE。实际异常路径在代码前列参数表，同步OpenAPI，不把所有ManifestVerificationError统一伪装成404。
- Reader返回明确准备对象（bundle digest、准确总长度、安全tar文件名、受控stream/close责任）。manifest/closure及全部成员的可读、大小、引用/摘要与普通文件/安全路径预检必须在返回StreamingResponse前实际执行；不能躲到未迭代的generator里。
- 沿现有artifact保护/读取handle协调cleanup；公开port不足时最小扩展其owner接口，不复制私有store状态机或新建持久下载状态机。逐成员预检和发送，单stream工作buffer≤1MiB、同时活动产物handle≤2，metadata沿既有16MiB上限且计入实际内存说明；不能靠整包bytes/全部mmap取得“流式”。在handoff给实际buffer/handle上界与代表性计数证据。
- Content-Length包括512-byte header/padding、全部PAX扩展和结束块，编码与长度共享同规则并有独立固定向量；实际完整响应字节数精确相等。固定mtime/uid/gid/mode等非业务字段，UTF-8路径保持原值。ETag为HTTP双引号包裹bundle digest，200仅声明application/x-tar，移除旧JSON/octet-stream，无双格式兼容。
- 头后I/O失败中断响应，不吞异常或补假成功结尾；正常/失败/取消/断连都释放保护与句柄。预检后仍可能I/O失败，不声称永不失效。不新增Range/压缩/分段下载或按artifact读取接口，无新导航产物。

## 3. UTF-8 PAX与前端手动转发

PAX `<length> <key>=<value>\n`的length为整条UTF-8字节数，含前缀自身并计算到固定点；不是Unicode字符数或UTF-16 code units。必须用生产encoder生成ASCII长路径（dir/×70+rows.parquet）、中文（目录/×60+表.parquet）、非BMP（😀/×60+表.parquet）、相邻两记录及前缀位数边界，另验证错误byte length/缺换行/截断UTF-8。固定单记录字面为`12 path=中\n`。

前端现有parsePaxPath按解码后text.length/slice推进，需要前端owner按字节边界修复；D不写其源码。后端交付生产encoder生成的**同一实际tar**、原manifest/closure、文件/总长度及SHA，复制到可由Owner转发的本地证据目录，附准确生成候选/命令/节点。前端须用同字节制品验证解析、摘要和OPFS安装；不能各造自测fixture或拿ASCII通过代替Unicode互通。后端D GO与FE3依赖解除分别记录，缺前端修复提交/同制品证据时FE3仍待。确需前端判断阻塞当前方案时给Owner明确问题包并等待，其余继续。

## 4. 验证与联合真实工具

纯encoder/长度/closure对应一个小向量owner，两个公开HTTP路由参数化鉴权/状态/缺失/损坏；生产wiring必须含Preview MODIFIED_ONLY/FULL/replacement、History两/三节点、共享/同源不同路径/同内容异schema/长路径/空表，不能只测fake reader。下载完整tar后逐项核closure成员映射、各类逻辑/物理摘要及冻结业务结果，不只解manifest。代表性流中失败、断连和cleanup并发证明释放；不复制内部syscall/线程全排列，不扩大同euid威胁模型。

main `vnext/backend/benchmarks/real_dump_journey.py`改为完整读tar、解析并验证manifest/closure/全部成员，GET起始到完整读完耗时与实际响应字节数单列只报告，不改变READY/Operation完成锚。与V2同步归档新异常consumer；**现工具只MODIFIED_ONLY/FULL入口待补**，D须按联合已授权矩阵补必要FULL功能入口并明确测试，不能把旧JSON字节数当整包。原冻结V_ref工具/输入/卷/镜像不动，不为D跑t4/2×t4性能矩阵。

工具接缝已静态定位：`_assert_preview_summaries`目前要求manifest恰好一个pair，`_assert_identity_pair`等下游也须核实际消费假设。FULL按owning P5-5A§7/Comparison Bundle包含`baseline_to_initial`和`initial_to_modified`两个pair；不能只改上传manifest枚举或忽略另一pair。一次fresh t1可优先用v1 MODIFIED_ONLY、v2 FULL（上传v1作INITIAL、v2作MODIFIED）集中覆盖，具体入口/配对由实施清单固定；默认业务摘要按`initial_to_modified`准确取值，完整tar校验仍覆盖所有pair/closure/共享binding，不把FULL改成三方diff或改已有比较锚。

06日常focused/Contract及收敛候选必要生产wiring/容器重建；五包静态按实际修改。所有编译/测试/lint/取证在专用节点，clean已提交独立WT、LAN bundle/legacy/离线缓存与原子占用/日志host/起止HEAD/UTC/exit/SHA按AGENTS。04联合最终候选受影响包权威及必要Compose，05一次fresh t1合并FULL/MODIFIED_ONLY/Submit/Review/Archive和Preview/History tar；异常用小型真实wiring补齐。未受影响包仅按合格闭包复用；不能用06focused或旧S2b当最终权威来源，不逐轮重复完整runner/旅程/大输入。

正式pytest focused显式按marker分两批：主体`-m '(not serial) or parallel_safe' -n 4`，其余`-m 'serial and not parallel_safe' -n 0`。流中取消/断连/cleanup若有时序依赖则保留serial标记及独立执行，不凭文件名称猜无serial，不改marker绕过；只补实际受影响批次。

## 5. 启动/收口

V2最终独审 **`9ec62e82ad9b70776a03954c30edb94a29e1380a`** GO、F1–F6全关；产品/容器`f8fb796f020ab47725359c176fc0e53bfb68aae6`，handoff`3cd4400f9fe794c3126605ffd8abac7f81830b64`，vnext tree=`3860ed86194e4eafea9cfd408e7e7b5096b24bbb`。两角色均正常结束，明确无后台/写入/节点占用，未销毁历史。06实际10:00:14.111Z取得、10:39:24Z核清释放；这是历史，D执行前重新核现场/原子取得。

D实际clean main起点为 **`9ec62e82ad9b70776a03954c30edb94a29e1380a`**，随后仅允许协调启动文档提交，不回退历史。拟新建实施GPT-6.1-Sol/xhigh、独审GPT-6.1-Sol/max：完整包一致性、公开HTTP、artifact保护/cleanup、流中错误和释放跨层相连，保持一个实施owner；不拆额外实现或证据角色。创建后记录实际ID。先提交`p6-be-d-handoff.md`精确字段/port/生命周期/schema/错误/encoder/唯一验证owner清单并由独审预检，再产品写入。

实际已创建`/root/be_d_impl`（GPT-6.1-Sol/xhigh）与`/root/be_d_review`（GPT-6.1-Sol/max），独立上下文；启动协调提交`dfc8659744`。两角色先read-only盘点/清单预检，未新增第三角色、未复用已结束V2角色；当前没有D产品/证据或占用声明。

**本节角色职责同时包含联合最终验收准备收尾**，见[集中验证工作单](p6-be-a-d-joint-validation-preparation.md)：主线真实工具FULL两pair/完整tar消费、最终候选与闭包/镜像/04-05执行清单、必要集中证据的实施与独立核收均由本节既定两角色承接，不新增第三角色。D局部代码/06验证通过是里程碑；本节约定收尾交接完成后两角色结束，不以里程碑换审清finding。04受影响包权威/必要Compose、05 fresh t1按既有授权与节点规则集中处理，不逐轮全量；最终真实数据范围退出前仍按DC33由Owner确认。不自动办理exit/tag/push，不启动S3、不声称FE3完成。

固定代码候选交只读独审，同一审核者核证据与修复；设计核心冲突带场景/证据/条款/影响/建议交设计者，必要时Owner决定。前端经Owner手动转发；真实判断阻塞时暂停依赖等回复，其他已授权工作继续。额外角色/约定外模型仍先向Owner说明。
