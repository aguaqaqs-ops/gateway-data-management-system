# P7-S1a B 固定验证稿

日期：2026-11-10。状态：本轮新候选待原审、未执行；下文保留旧候选失败/备料历史，本稿不签SCRIPT_GO/B_GO。2bacea之后本轮RS新依赖按[独立准备稿](p7-s1a-b-rs-dependency-preparation.md)执行，新base原件审核后才能固定正文EXEC_GO。

起点 `00ca325c2ed6d705abfa39e9528ef148e6029cfc`。唯一测试角色只在原审核准精确候选 B_SHA、本稿与脚本 SHA256 后执行 [p7-s1a-b-verify.sh](p7-s1a-b-verify.sh)。固定节点 `ct107-gw-dms-06`，主机名 `gw-dms-06`；不改节点、参数、worker 数、预期或现场修脚本。失败先停本次及依赖验收、保原 exit/日志/SHA，交实施者/原审；依本轮用户 AGENTS/DC68和提示词处理，不沿用 main 的 DC91/三轮恢复权限，不无修改重试。

准备阶段先在06固定候选clean树对脚本做`bash -n`，记录hostname/UTC/HEAD、原numeric exit、stdout/stderr和SHA；只由唯一测试者执行，语法失败停止，不直接执行正文。开始前 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`，只读核本节点有效占用、Dolt/Compose 与共享端口；忙则等待，不能碰他人标记。源码经获准 LAN Git/文件传输到本任务新 clean detached worktree，准备仓库忽略的 `legacy` 参考链接。不在主工作区执行，不覆盖 A 成功/失败原件。脚本自身原子取得 `/home/dev/gdds-node-busy.d`，外层不要重复取标记。记录本节点实际 uv/Cargo 缓存类别、LAN 缓存端点标识/来源提交/摘要/预填时间（已知项）及是否使用预填缓存；未知如实写明，不打印含凭据 URL。缓存缺失停止，不经公网或代理补装。

固定命令：

```bash
bash "$CLEAN_WORKTREE/docs/backend-vnext/refactoring/formal/plans/p7-s1a-b-verify.sh" \
  "$B_SHA" "$CLEAN_WORKTREE" "$NEW_LOG_DIR" "$SESSION" "$RS_IDENTITY_SHA256"
```

五参数精确值由协调者交接；B_SHA为40位小写hex，SESSION为1–64位`[a-z0-9][a-z0-9_-]*`。NEW_LOG_DIR为 worktree 外、父目录已存在的全新路径。RS_IDENTITY_SHA256为成功新base原件经原审核收后的64位SHA，现在UNKNOWN，不能占位执行。调用时保 SSH 原 numeric exit，不能用 tee 成功掩盖脚本失败。

脚本完整固定内容：

1. 起止 hostname/UTC/HEAD/clean；HEAD等于B_SHA且起点为祖先；脚本与本稿SHA。拒绝dirty/错误节点；核除RS锁外的四锁及Rust源码未变；RS锁仅新增精确rfc的证明在依赖准备原件中。
2. 离线 `UV_OFFLINE=1 CARGO_NET_OFFLINE=true`，`TMPDIR=/home/dev/gdds-test-tmp`、Cargo jobs4/外置target，root PATH以`/home/dev/.cargo/bin`起，不接受RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME覆盖。通过受控uv同步五包，backend强制重装扩展并绑定HEAD的Rust tree，检查安装扩展build-input；该编译仅在06执行。
3. 五Python包分别 `ruff check .` 与 `mypy`。脚本遇首次非0停止，不跳过未改包，不在节点auto-fix。
4. backend按脚本固定文件列表运行focused unit：非serial `-n 4`，serial `-n 0`。覆盖共享配置、四位置codec/拒绝、nominal UUID、canonical完整key、Snapshot wrapper内容身份、producer/cache、checkpoint/job/SQLite/domain、facts/archive绑定golden（包括`test_archive_queries.py::test_archive_digest_v2_preimages_match_the_frozen_consumer_vectors`）、bundle/surface与上传接线。real_dump_journey.py在此仅为旅程工具自身的mock/SQLite unit，不读真实输入、不启动完整旅程。RS运行同一共享配置格式向量及既有`test_repository_sources_do_not_import_non_repository_packages` owner selector，`-n 0`，不创建Dolt库。不是权威全包runner，不作carried来源。
5. 成功与失败均收尾核起止HEAD/clean、原numeric exit；只删除本人且owner内容匹配的标记文件，再rmdir忙目录，不递归清理/释放他人资源。保源码、环境、成功/失败原件。tee结束后另存VERIFIER_EXIT、LOGGER_EXIT和最终日志SHA256。资源释放或logger失败也非0；不能被验证主体成功覆盖。

6. 本轮改到实际Compose harness的manifest观测器，必须在当前候选离线重建backend/worker，并运行代表性既有`test_compose_history_compare_journey_zero_write_restart`（`-n 0`）。观测器按严格ref/位置及owning manifest decoder识别全部规范化manifest；前置非空、前后相等与重启断言保持，不再按不可见的旧kind前缀返回空集合。ordered旅程只改同helper名称并补非空保护；同一观测器由上述history向量覆盖，不将两套长旅程相乘。本步骤实际仍是B现有单root部署，不能称多root/缺挂载/cgroup通过。

容器前提由唯一测试角色只读预检实际06本机dependency-base，向原审固定具体tag、config digest和全部RootFS DiffID，记录来源/预填时间；脚本要求`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-578e079b762e`、`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-b47d6de3cbce`、`GATEWAY_DOCKER_BUILD_NETWORK=none`，且不得设置`GATEWAY_COMPOSE_GATE_PREBUILT`。四项由脚本显式设置。两个base必须已在本机；在任何环境同步/产品检查前，`build-backend-dependency-base.sh --print-input`（只读输入、拒绝缺失本机Rust base）按候选全部输入及源base config digest/DiffID重算backend tag/input摘要，与固定tag和本机`gateway.backend.dependency-input-sha256` label逐项匹配；RS按候选lock SHA匹配固定tag及本机`gateway.p2r1.uv-lock-sha256` label。不一致即早停，不重试、重tag或fall back。RS builder保留既有预置依赖逻辑。脚本要求没有DOCKER_HOST/DOCKER_CONTEXT覆盖，先只读核Docker context endpoint为本机Unix socket，再记录daemon ID/name/version；不接远程daemon。脚本拒绝06 forward proxy，不输出proxy值；cache/proxy如需记录只保摘要。缺base停止，不走公网/转发或臆测cache。`GATEWAY_COMPOSE_GATE_PROJECT_NAME`、session和provenance路径由脚本固定至本任务。harness在本机正常build，不手工retag/rmi。来源原件、候选完整输入、本机当前config原字节与全部有序DiffID三者分别核验，不能只看inspect ID/层数或抄旧label。正式稿在sync前核backend下表原件SHA和新RS实际原件SHA（第五参），旧RS表仅是备料来源，比较source.input.tag_inputs与当前官方计算结果相同；分别docker-save当前选中的backend/RS dependency-base到本任务日志目录，使用[原样保留的image verifier](p7-s1a-b-verify-saved-image.py)从manifest唯一Config原bytes算SHA并逐项比全DiffID。backend用dependency模式并核label；RS精确选新base聚合JSON中ref为b47d6de3cbce的唯一dependency-base条目，核其lock label后生成仅含config_digest/diff_ids的expected文档，用同verifier的base模式做通用identity比较（此处是RS base，不是Rust base或最终RS镜像）。两当前归档及expected文档保SHA；保留原件，不docker-load、不重tag/覆盖已有base。任何原件/输入/config/DiffID不等立即停，不进入sync/测试。当前config比对仍未执行，不把原审只读inspect比层数记作此步通过。既有harness负责其Compose生命周期/finally收尾，脚本保留provenance及SHA；唯一测试角色收尾再核无本人栈/进程残留后核收资源释放。

本稿不运行Rust算法测试（Rust源码未变）、真实输入、全量runner、carried或性能测量。本轮RS production依赖、lock及Docker ARG已变，触发新RS预置依赖base准备与当前HEAD容器构建；entrypoint/Compose YAML未变。Current HEAD container gate未执行；旧P6结果不表述为B当前HEAD通过。typed格式通过不等于实际source/mount/marker/symlink/cgroup/ready检查通过；四位置ID通过不等于多root存储发布或跨盘借用通过。C–F实际新布局和G仍须自己的当前候选边界验证。

回执须给B_SHA、节点、起止UTC/HEAD、每步及整稿原exit、日志路径/SHA、实际运行范围/未运行步骤、缓存来源类别/限制、资源释放状态；原审据真实证据决定B核收。未执行、失败、UNKNOWN和后续包责任不填PASS。


## F6 固定预填来源补充（旧bba9历史；backend578仍适用）

849cf6f799稿误用了旧Cargo.lock时期的d054，未执行。测试者的首次内联578推导没有独立原件，不作正式证据。原审随后核到以下P6 S3-E原始来源；本次只沿用已预填依赖来源，仍由当前候选官方计算+当前config bytes核准后消费，不将P6产品结果carried为B。

| 来源 | SHA256/身份 |
| --- | --- |
| CT201 `/home/dev/gdds-test-tmp/p6-s3-e-dependency-base-53746c7236a7/archives/input.json`；06副本`/home/dev/gdds-test-tmp/p6-s3-e-06-cache-prefill-578e079b/archives/input.json` | `270ed39e56b2eec16f0a5a1c0e4a57ef5680e8a0f3b8fba8dfdf236140b8d560` |
| 同两archives目录`image-identity.json` | `d5ebabf6cf39b98917adca5ebad6f66138e2a9fa00e63eb8e6526956ccdff7c3`；source commit `53746c7236a79c96bd41587165e80683da283400`；input `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`；config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`；全19有序DiffID在原件 |
| CT201上述source archives `backend-dependency-base.tar` | `1b595f069197d75a9226978a530fdb06db93e7df29dbf1f4458e00ec3f6cc648` |
| CT201 `/home/dev/gdds-test-tmp/p6-s3-e-06-cache-prefill-578e079b/logs/prefill-06.log` | `762c4b3f828ddee4c618e006f716c4b241cce3d186e18c7d7adb9a39a41c4d97`；LAN预填2026-11-08T09:32:05Z–09:34:32Z，原exit0；当前不重放该预填 |
| 06 `/home/dev/gdds-test-tmp/artifacts/p6-v1-f5/image-identities-c229582a9e.json` | `cafb565752514e0328764c0c5d750634005f7f38e7a61c9bb97b0e5d1a8195cd`；只取ref=`gateway-p2r1-repository:lock-6dc9659f0aee`的一条，config `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`、全16有序DiffID及lock label在原件。最终RS的28 DiffID条目不作为dependency-base |
| 原样复制的verifier | 来源CT201 `/home/dev/gdds-test-tmp/p6-s3-e-06-cache-prefill-578e079b/verify-saved-image.py`，本候选相邻`p7-s1a-b-verify-saved-image.py`；二者SHA均`bbf4a6ac956ec57cc88bdb496f334306bdfe9e92024a538526cc6b2136ca7d50` |

原审只读核来源和候选五个输入SHA/现有label与DiffID，未导出当前config或执行正文；本稿补齐正式导出/比对步骤。无需新依赖构建或覆盖缓存；如现场不符，停交协调者，不自行修理资源或把未知写作通过。除了被明确固定的tag/开关，不打印ambient proxy/cache值或凭据；只有摘要/类别进入回执。


## 首次正式执行失败与范围内修订

06于候选`bba9d6ae9a1e36509f2d51934ec565b2dbc990fd`执行固定稿，原日志`/home/dev/gdds-test-tmp/p7-s1a-b-bba9d6ae/logs-r1/verification.log`，SHA256=`7c1e27022cfee459eb9cb1563b944da3ed507fd8e095841e926a587a83a7a6a2`，原exit1且本人资源已释放。完整依赖身份、五包offline sync及shared_kernel/repository_contracts/repository_client的ruff/mypy已执行通过；backend ruff在`comparison/artifacts.py:367`因F841未使用`control`退出。backend mypy、后续包静态、focused、Compose未执行，不能记PASS。

原因：B删除caller自定义ID prefix后，`restore_records_closure`的context仅剩原来给ID helper供prefix的残余赋值。只读核当前唯一调用者为既有`test_comparison_s3_c_arrow.py::test_real_open_read_restore_use_native_arrow_validator`，未传context；其余两个`control`变量仍用于Arrow publication/预算路径，保留原checkpoint回调。修订删除restore的无效context入口和赋值，保其验证、copy预算、写入/重开及内容/规则摘要；不新增取消语义，不改预期掩盖结果。

固定选择器增加上述既有restore owner单例，文件存在性校验对静态nodeid先取`::`前的文件；其余选择、参数/预算/离线身份早停和五包检查不变。新候选由原审重新核SCRIPT_GO后在06 clean已提交worktree从完整稿开头执行，保旧失败原件，不无修改重试。开发机未跑测试/lint/编译/语法检查。本次修订仍不签产品/容器通过。


## d97 backend mypy 失败与测试类型修订

06候选`d97fd42b71cd34471d2a816dd90ad4da47e3da0d`日志`/home/dev/gdds-test-tmp/p7-s1a-b-d97fd42b/logs-r1/verification.log`，SHA256=`f3a06469911edf8982f32aba261305d18ac8ced465deba8daf5e033956d84f33`，原exit1、本人marker已释放。backend ruff已通过；backend mypy在`test_submit_domain.py:324`/`test_workspace_domain.py:289`报告共19条类型错误（原审按原日志复核为SubmitAttempt12条、PreviewResult7条；先前任务转述11/8不作为原件事实），后续pytest、RS静态/配置unit、Compose未运行。

原因是新增负向向量用`dataclasses.replace(record, **dict[str, str])`动态选择字段，mypy无法证明未知key只落在字符串ref字段，将其视作可能传给record全部其他字段。修订为模块级共享参数表，mutator明确标`Callable[[SubmitAttempt], SubmitAttempt]`或`Callable[[PreviewResult], PreviewResult]`，每个lambda直接填写固定ref keyword；故障仍是同一legacy artifact字符串、同一fixture与同一ValueError/a1断言，四个Attempt/两个Preview向量不减。未添加cast/type-ignore/skip或放宽产品校验；产品代码未改变。

正文选择器、参数、资源与身份机制无需修改。原审核新候选/本稿SHA后，在全新独立task/source/log路径按完整正文从开头执行；外置准备包另固定bundle、wrapper与SHA，不复用d97已失败的目录或wrapper。旧日志、源码和退出事实保留，未运行或未知不记PASS；实施者未在开发机运行测试/静态/编译/语法检查。


## 2bacea RS包边界首败及新依赖前提

06原日志`/home/dev/gdds-test-tmp/p7-s1a-b-2bacea83/logs-r1/verification.log` SHA256 `627608c5b62a318c36ce6242f426704625cc71232271e25479d090b6c8ab3cf0`，原exit1、资源已释放。shared/contracts/client/backend ruff/mypy均0、RS ruff0；RS mypy在deployment_config.py非法import shared kernel两条错误停止，pytest/Compose未到达。旧原件/候选/脚本保持，不无修改重试。

本轮RS adapter只依赖精确rfc8785+stdlib；BE仍用shared kernel。共同冻结JCS preimage与SHA覆盖Unicode、整数边界、2.0/1e-7/-0.0，拒绝lone surrogate/noncharacter与safe integer之外值。五包静态后新增既有RS distribution owner selector直接证明包边界，不改测试约束或忽略诊断。

RS锁变为`b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f`，Docker ARG同步，backend578五输入未变。上面F6来源/6dc/无新构建陈述仅为bba9时期历史；当前正文明确选择新`gateway-p2r1-repository:lock-b47d6de3cbce`，来源路径`/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3/archives/image-identity.json`；其实际SHA由已审外置wrapper第五参固定。旧6dc只用作独立备料输入，新镜像身份不能用旧6dc或任意环境值替代。

新base须先按独立准备稿clean CT201构建/精确身份、06LAN/load/re-save/full锁环境与host uv offline缓存准备，完整原件回审后正文才能EXEC_GO。当前只有可审计划，实际新config/全DiffID/archive/identity SHA及时间均UNKNOWN，没有新镜像/测试通过。保全部失败及准备命令事实；语法/AST/静态/编译/pytest只由唯一测试者在规定节点执行。


## 3b1a原审R13静态修订（未执行）

3b1a未获执行许可，原审报告`/home/dev/gdds-p7-s1a-reviews/b/3b1a707c-rs-repair-r13.md` SHA `13287e26c9be38c85bfc3c8f248f2fda443189fe6f5a4ab8fafea6344be49f98`指出RS递归JSON类型证明与备料trap资源/退出聚合问题。本轮将实际递归域校验标为明确JSON TypeGuard，未知非JSON类型拒绝，不cast/Any/ignore；两备料脚本每次run取得独立CID文件及本次invocation label，只在CID+精确归属证明后清理，前置碰撞不碰既存容器。成功ls空才确认absent，查询/inspect/归属/rm或确认失败均非0，06保busy至确定清完。end hostname/UTC/HEAD/clean每步原exit聚合，INT/TERM分别130/143进入收尾，保主体原exit与独立tee退出。活跃配置前提直接选新b47。未执行3b1a或新候选，不伪造语法/镜像/产品通过。
