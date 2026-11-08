# BE-Q18 独立审核：归档候选读取审核版本

状态：2026-11-08，修复产品候选 `94b25a32792821cbc5b3230d98a0aa6f13493c32` 的适用 focused 与四例容器原件已独核，**BE-Q18 GO**；仅限归档候选读取版本、严格选择引用及四个受影响旅程。旧 `a1ca3bad93` focused 原件保留、容器未启动；S3 容量、完整 runner 与真实数据另行判断。

## 1. 审核对象与边界

- 增量：`18e76dbbf0..a1ca3bad93a25cb47384a81fbc985075b1299c39`，共十个文件；前提交 `18e76dbbf0` 为独立前端文档提交。审核在 `/home/dev/gdds-reviews/p6-be-q18-a1ca3bad` 的 detached、clean worktree 进行，HEAD 固定为 `a1ca3bad93`，`legacy` 已链接；没有在开发主机执行测试、编译或 lint。
- 依据：`AGENTS.md`、`testing-conventions.md`、比例化保障政策、`business-lifecycle-and-state.md`、S3 coordination §16、FE3c 的 Q18 前置。当前任务只提供归档确认人关闭已批准 submission 所需的 CAS 版本，不扩审核读取权限、不改变 S3 计算/容量结论。
- 只读后处理：`git diff --check 18e76dbbf0..a1ca3bad` 为 0；不是运行时验证。

## 2. 静态结论

| 不变量 | 核查结果 |
| --- | --- |
| 当前 scope 与授权 | `get_archive_candidates` 先校验 `archive_submission`，再在只读 UoW 中解析当前 provisioned scope。候选事实和 ReviewProjection 在该事务中读取；外 scope 候选不进入响应。Review GET 仍要求 `review_submission` 或本人撤回权限。 |
| 版本来源与查询量 | `snapshot.py` 原有逐候选 `review.get_projection()` 的 `optimistic_version` 填入独立 `ArchiveCandidateRead`。增量没有改 control DB SQL、schema、事务边界或查询次数。 |
| digest、选择与关闭 | 原 `ArchiveCandidateRef` 仍单独生成并参与 candidate-set digest、Preview/Start/审计选择；新增 `review_version` 仅进入候选读取 DTO。`ArchiveSelectedRefRequest` 保持额外字段拒绝，关闭写入/CAS/fingerprint 未改。 |
| HTTP/OpenAPI | `ArchiveCandidateResponse.review_version` 为必填 `NonNegativeIJsonInt`（严格整数，0 到 2^53−1）；响应映射取新只读行。Contract 规定当前 scope、字段来源和排除项。 |
| 测试范围 | 新 HTTP 用例覆盖 archive-only 读取、Review GET 403、外 scope 空候选及关闭 404、stale 409、成功 201 与同 key 回放 200。Compose 旅程覆盖 archive-only 真实服务路径；选择 helper 显式只转两字段。OpenAPI 用例锁定必填和选择边界。 |

**这是初审当时结论；后续消费方 finding 见 §9，修复与最终结论见 §10–13。** `ArchiveCandidateRead` 与原引用分列增加少量内存，但候选已有 200 上限；符合本轮只读 DTO 目标。

## 3. 初审时尚缺的证据与验收要求

1. 依 DC91 在统一五节点池选择当次空闲且工具链、缓存、输入合格的节点，于 clean、已提交固定 worktree 按本节点占用、离线缓存、`UV_OFFLINE=1`、磁盘 `TMPDIR` 和 `uv-consume.sh` 规则运行 backend 定向测试：`test_archive_queries.py::test_archive_candidates_include_only_approved_current_base_submissions`、`test_archive_http.py::test_list_archive_candidates_returns_approved_submission`、`test_archive_http.py::test_archive_only_actor_reads_candidate_version_and_closes_with_cas`、`test_http_openapi.py::test_openapi_archive_candidate_exposes_required_review_version`。池内选点不需旧用途例外；若失败，保留原始 exit/log/SHA，停止后续验收并按现行规则处理。
2. 提交前五个 Python 包均需 `ruff check .` 与 `mypy` 通过；本次未改 Rust 源，不触发独立 rustfmt/clippy 门禁。backend focused 的已安装扩展仍须按 DC48 与当前 Rust tree 核对，执行稿选择强制重装。节点执行者应核对候选 HEAD、clean、五锁未漂、日志起止 HEAD/时间/hostname/入口 exit 与 SHA256。
3. 本增量修改了实际 `test_archive_compose_e2e.py`，触发 AGENTS 的容器门禁重建条款。须在许可节点以当前固定 HEAD、本机 Compose build、已预置且身份核对的 backend dependency-base、`GATEWAY_DOCKER_BUILD_NETWORK=none`，实际重建并运行 `test_compose_business_rejection_manual_close_and_fresh_upload_archive`，核对 backend/worker 运行镜像与构建结果、OpenAPI、日志、provenance 和清理。不能把旧提交的容器结果表述为本 HEAD 已验证。
4. 若后续以此候选参加阶段退出、S3 ready 或最终门禁，另按相应阶段闭包、六包和镜像身份规则判定；本次定向验证本身不代替那些门禁。FE3c 在固定后端 OpenAPI 与独审/节点结果交付后再刷新类型、mock 与 §16.6，并按其既定真实 backend e2e 验收。

待同一审核者独立核对固定执行稿、节点原始证据及失败处置后，更新本报告结论；当前不得标记 BE-Q18 GO。

## 4. 固定 focused 执行稿静审

2026-11-08 收到实施者工作树外的 `run-focused-06.sh`，原件 SHA256=`0f93d34358f7dadb38da22452ab1dd25bcb2d160f283a7e5969fb80fb91976cd`；配套 `execution-proposal.md` SHA256=`7b3fe4132249edf8747ecc690e9a9153be420f995a6a235ddf3776278c980c62`。本人只读重算摘要并审精确脚本，未执行、未转发、未取得节点占用。

**脚本静审 CLEAR，可作为 06 focused 执行稿；不是执行许可之外的 PASS 证据。** 它固定 `a1ca3bad93` 和 Rust tree `9d4f84ce`，检查本节点空闲后原子获取 marker，创建 clean detached worktree/`legacy` 链接，校验四项 Rust 工具链及离线环境，强制重装扩展并核安装的 build input；五包 Ruff/mypy 后以 backend 两遍 marker 规则运行六个 archive 查询、HTTP、OpenAPI、事务、审计、并发测试文件。所有测试缓存、Cargo target 和日志都在 worktree 外；失败即停，记录步骤 exit、起止 HEAD、lock SHA、guarded marker 释放与日志 SHA。六文件均标 unit，两个显式 serial 用例进入 `-n 0` 一遍。范围比上述四个最小定向用例广，但仍为受影响 archive focused 范围，并未偷跑全量 runner。

执行者须先按提案进行 SSH BatchMode、获准 LAN 源码/缓存与脚本 SHA 核对；本脚本不负责传输和连接检查。06 是本稿选择的一个 DC91 合格节点，不是旧固定用途要求。若改脚本、节点或候选，先固定新字节并按实际变化复审。容器提案只描述后续最终 HEAD 的构建与单项 Compose 旅程，目前没有固定容器执行脚本，也没有镜像/缓存/测试原件可核收。

## 5. 待到稿的容器执行稿核审清单

本节成稿时 main=`de0eb3a8b2`，`a1ca3bad93..de0eb3a8b2` 只有 S4 设计/Contract 文档新增，backend、Rust 和部署路径无变动；Q18 产品审查对象仍为 `a1ca3bad93`。后续 S4 提交不混入这个固定产品候选。这不预判最终容器候选或 S3 退出闭包。收到 Sol 固定脚本时，同一审核者逐字核对并记录脚本 SHA256、绑定 HEAD、节点与以下项目，然后才能给脚本静审结论：

1. **节点与输入**：DC91 池内节点在执行前以 BatchMode SSH 可达；候选提交已在该节点；clean detached worktree、`legacy` 链接、起止 HEAD/状态固定；测试期间不写 worktree。获取前整机残留、Docker 栈、端口 8000 与有效标记核查，原子 `mkdir` 标记，失败/中断的本人容器、卷、端口及标记收尾有可核日志。
2. **离线依赖与镜像**：本节点核对当前 lock 对应预置 backend dependency-base 的来源提交、输入摘要、config digest、全部 RootFS DiffID、归档 SHA 与预填充时间；缓存端点本次可达，缺失即停。`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、磁盘 `TMPDIR`，不用转发代理或公网；root Rust selector/扩展 build input 按 DC48 核验。Compose 保留用例既定的本机 build，设置 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、正确 lock tag 和 `GATEWAY_DOCKER_BUILD_NETWORK=none`，不设 `GATEWAY_COMPOSE_GATE_PREBUILT`；除用例既定构建外，执行期间不另行重建或 retag。
3. **明确测试与证明**：只在固定 HEAD 上运行 `tests/test_archive_compose_e2e.py::test_compose_business_rejection_manual_close_and_fresh_upload_archive`，该用例标 integration/serial，须 `-n 0`。确认真实 backend/worker 镜像由本次 Compose build 生成且运行镜像身份匹配，生产 OpenAPI 导出来自本次容器；旅程证明 archive-only 候选取版本、Review GET 403、stale 409、关闭 201、同 key 回放 200，后续新上传/归档路径及原 main/commit 不变断言也执行完成。
4. **原件与停止**：脚本/传输物 SHA、节点 hostname、起止 UTC、起止 HEAD、每步 argv/exit、入口 numeric exit、镜像身份、Compose provenance、测试日志及 SHA256 均写在 worktree 外；用 `tee` 时保留入口自身 exit。任一身份、缓存、测试或清理失败先停并保留原件，不用后续成功覆盖原失败；按 DC68 的实际根因与修复轮次处理。审核只接受原件核收，不以提案或旧提交结果代替当前门禁。

最终 HEAD 如在 Q18 测试后继续变化，按 AGENTS 的镜像身份等价/按包闭包在来源同节点同 worktree 单独判定；若变化涉及实际 Compose 测试或其他强制重建项，则最终 HEAD 重新构建并运行相应门禁。发布/最终 production gate 始终在最终 HEAD 完整运行。

## 6. 固定容器稿静审

收到 Sol 准备的工作树外 `run-container-06.sh`，本人只读重算 SHA256=`12d6faad61edd2c5920d803fe3261463a4cd483f5b32087ca3b33810d383ca78` 并逐字核对。四项 helper/输入 SHA256 分别为：`backend-base-identity.json`=`d5ebabf6cf39b98917adca5ebad6f66138e2a9fa00e63eb8e6526956ccdff7c3`、`verify-saved-image.py`=`bbf4a6ac956ec57cc88bdb496f334306bdfe9e92024a538526cc6b2136ca7d50`、`saved-runtime-images.py`=`8cf502321df784415a53a46e84091da6e5afb4edee14bdd14d0f85a1f4b559d9`、`bind-compose-provenance.py`=`826a4398255b6f2f4cb70acc50866bc1990700de09c9426a36dcf962f8775623`。原 S3 记录的 dependency-base 完整身份与本次 JSON 对应；未在开发主机运行脚本或 helper。

原稿其余执行边界静审通过，但随后发现 `rs-base-record` 错把当前候选 `a1` 传入已有 RS dependency-base 记录的 `source_commit` 字段；该镜像实际来源早于 `a1`，会使交接误认构建来源。此为**证据语义 finding**，已在容器稿执行前交 root；原 SHA `12d6faad…` **撤回，不得执行**。脚本固定 `a1ca3bad93`/Rust tree、06 同一 focused worktree 与独立 RUN_ROOT/marker；离线、root selector/native build input、六锁、backend dependency-base config digest/全 DiffID/输入 label、RS base lock label 均有断言。用例正常路径在本机重建 RS 及 backend/worker，未启用 prebuilt；单一 `integration`+`serial` Compose 用例使用 `-n 0`。成功后保存三运行镜像的 config digest/全 DiffID与本机 ID，并把当次 Compose provenance 的三个容器 ID 绑定到所存镜像，同时核 RS build-input/source-tree/revision；检查本项目容器、卷、网络清零，再 guarded 释放 marker。脚本按失败即停保留外部日志与摘要，不重跑全量或复用旧镜像结论。

脚本的 `grep final_exit=0` 是 focused 放行的附加守卫，不代替本人核对 focused 原日志及 SHA、实际步骤 exit、clean/locks/收尾。唯一执行者在启动容器前还须核本节点缓存来源/端点、预置镜像身份、脚本与 helper 传输 SHA、Docker build 所需本机层可用；任何不符即停。`a1ca3bad93` 的容器成功仅证明该固定产品候选，后续 H 的 carried 仍按同节点同 worktree 的独立闭包与镜像等价规则核收。

## 7. 容器稿证据语义修复复审

root 已废弃上述原稿，改定 `run-container-06.sh` SHA256=`16406c318af907068326ca4131a6a03e3eee01a2c323b464a439709ab7b1efc4`，新增 `record-base-observation.py` SHA256=`2e46dc1934dc95a99af8150efe1b5f1ade97d6462b5511a2fba558187ad2262a`；本人只读重算均匹配。新 helper 读取当次 `docker save` 的 RS base config 和全 DiffID，核其 `gateway.p2r1.uv-lock-sha256` 等于当前 lock；输出字段改为 `observed_at_candidate=a1`、现有节点 preload 类别及镜像自身若存在的 declared revision，不再将 `a1` 称为预置镜像的构建源。运行时新构建的三镜像继续由原 helper 以 `source_commit=a1` 记录并与容器 provenance 绑定，含义正确。

**修订稿静审 CLEAR，证据语义 finding 关闭。** 旧容器 SHA 作历史原稿保留，不作可执行版本；只允许传输并运行 `16406c…` 与上述五项配套资产固定 SHA。仍须先独核 focused 原始成功、节点缓存与镜像/工具输入，再由唯一执行者启动；此处未宣称容器已运行或通过。

## 8. 06 focused 原始证据核收

唯一执行者在 `gw-dms-06` 以原稿 `run-focused-06.sh` SHA256=`0f93d34358f7dadb38da22452ab1dd25bcb2d160f283a7e5969fb80fb91976cd` 于 **16:27:31–16:32:18 UTC** 运行。本人重算本地同字节副本和经 BatchMode SSH 现场重算节点原日志 `/home/dev/gdds-test-tmp/be-q18-a1ca3bad93-06/logs/focused.log`，SHA256 均为 `390dcb75e3805517adfa8f7f284ed5de05a22f52a49b23e4a06733d4e9c0e366`，节点 `.sha256` 同值；外层入口日志 SHA256=`c158d98d2f88d6fe54fe0b4067b3f6692b963284309a853f658bbd3c3f54b413`，独立 postflight 日志 SHA256=`731661ad130e90e348c26b9abe6c0a98b27555379e51ae9e0974a5ceb9843cd1`。

- 起止 HEAD 均为 `a1ca3bad93a25cb47384a81fbc985075b1299c39`，detached worktree clean；节点报告 32 CPU / 64 GiB，Rust selector `1.97.0`，四工具同一 toolchain。扩展强装后 build input expected=installed=`9d4f84ce0897099402226c77c548c487c4912008`。
- 本人逐项核 18 个 start/end 步骤成对且 exit 0：backend offline sync/native checker、其余四包 offline sync、五包 Ruff/mypy 十项、archive 六文件非串行与串行两遍。非串行 **179 passed / 4 StarletteDeprecationWarning**；串行 **2 passed、179 deselected / 1 同类 warning**。两遍均无 failed/error，满足本轮 focused 范围；warning 非 Q18 失败。
- 六个锁 SHA 行前后逐字相同，`lock_drift=0`；脚本 entry/final exit 均 0，SSH outer numeric exit 0。标记文件/目录释放各 exit 0；独立 postflight 和本人 SSH 复核 marker absent、Docker running 0、8000 listener 0、目标进程 0，当前 worktree HEAD/clean 仍正确。

**focused 与提交前静态范围 PASS。** 本人当时据此放行已静审的容器稿，随后因 §9 的消费方 finding 在容器启动前撤回放行；此核收不把六文件 focused 说成全量 backend、官方 runner、正式 Compose 或 S3 容量通过。

## 9. 消费方漏项：Q18 产品 finding

root 提示真实消费者后，本人回查固定 `a1ca3bad93`：`vnext/backend/benchmarks/real_dump_journey.py::_archive` 直接把 `GET /v1/archive-candidates` 的整个候选 dict 作为 `selected` 发送给 Preview、Confirmation、AnomalyResolution 和 Start。Q18 响应新增 required `review_version`，而 `ArchiveSelectedRefRequest` 明确 `extra="forbid"`；因此真实 t1–t4 首个 Preview 会因多余字段返回 422，既定 fresh 旅程不能在此候选通过。现有 `test_real_dump_journey.py` mock 仍只有旧双字段，未覆盖新 read DTO；§8 archive focused 未选择此文件，不能掩盖漏项。

同一误用还存在于 `test_ordered_compare_compose.py::_archive_submission`、`test_submit_compose_e2e.py::_archive_single_submission` 及 `test_history_compose_e2e.py::_candidate_for_submission`，这些容器旅程都把完整读取候选原样送入严格 selected 请求。`test_archive_compose_e2e.py` 已显式只取双字段，故单项 Q18 容器即使通过也不能证明其他旅程安全。本人全仓搜索未在其他后端消费者发现同样 raw dict 转发；前端 FE3c 的生成类型/mock 仍是后续独立交付。

**修复范围**：四处消费者显式投影 `submission_id` 与 `expected_candidate_digest`，必要时校验读取项的形状；真实旅程 mock 候选提供 `review_version`，测试断所有发出的 `selected` 仅有这两个字段。保留候选读取版本、选择 DTO 的 `extra="forbid"`、digest 与 CAS。修复须另固定产品候选并复审，至少跑受影响 `test_real_dump_journey.py` focused、五包静态与适用 Compose 门禁；实际容器稿和最终 H 身份按新候选重新绑定。唯一执行者获报后已在旧 `a1` 容器前暂停，旧 focused 原件保留为来源回归，不作新候选 PASS 或 Q18 GO。

### 修复候选的比例化取证安排

先在新固定候选上跑真实旅程消费测试 `test_real_dump_journey.py::test_archive_consumer_requires_explicit_business_reason_and_references_each_latest_subject` 的两参数、五包 Ruff/mypy，并用本机当前 HEAD 重建跑 archive-only Q18 单项 Compose。此范围足以先判断新增读 DTO、严格 selected 双字段及真实旅程 mock 的主语义，但尚不足签完整 Q18 GO。

另三处被修订的是实际 Compose e2e；AGENTS 要求其对应容器旅程在当前 HEAD 验证。若紧接着的 S3 必要 backend 权威 runner 在同一固定产品候选上覆盖 `test_ordered_compare_compose.py`、`test_submit_compose_e2e.py`、`test_history_compose_e2e.py` 且整次 exit 0，本人可从该原件核收，不重复单独跑三例；在此之前三例记为未测，不称 carried/PASS。若 S3 runner 推迟、HEAD 改变或 FE3c 交付必须先于它完成，就在当前已重建镜像与合格节点上定向跑这三例，不为标题另启完整 runner。真实 t1–t4 与容量仍按 S3 自身义务判断。

## 10. 同根修复候选静态复审

新固定提交 `94b25a32792821cbc5b3230d98a0aa6f13493c32`（父 `8e144b8345`）已在 `/home/dev/gdds-reviews/p6-be-q18-94b25a3279` clean detached worktree 独审并链接 `legacy`。`8e144b..94b25a` 仅改 Q18 handoff、真实旅程消费/测试及三处 Compose helper，共六文件；`git diff --check` 为 0。其间其他 S4 治理与工作不混入本增量审查；`a1ca3bad93..94b25a` 的 Q18 产品代码本体与 Rust/部署路径未改，只有上述五个 backend benchmark/test 文件变化。

四处消费者均将读取候选显式投影为 `submission_id` 与 `expected_candidate_digest`，未把只读 `review_version` 带入 strict selected。真实旅程另校验目标 ID 为 1–255 UTF-8 字节和 digest 形状；`re` 已导入，未修改后端 DTO/digest/CAS。参数化 mock 候选现含 `review_version=1`，每次 Preview、确认、异常处置和 Start 的 POST body 都断 selected 恰为原双字段；原理由和 subject 引用断言仍在。三处 Compose 测试 nodeid 均已标 `integration`、`serial`。静态未见新 finding，§9 的代码原因在此修订稿**静态关闭**；实际关闭仍待新候选 focused 和容器原件。

`94b25a` 是新产品候选，旧 `a1` 的 181 个 focused PASS 不冒充其运行结果。修订后的执行稿须重新固定 HEAD/脚本 SHA；优先五包 Ruff/mypy 和真实旅程两参数 focused，再按上节门禁计划验证容器。当前 main 后续 S4 WIP 不改变此固定审核对象，不从 dirty main 运行测试。

## 11. `94b25a` 新候选执行稿静审

实施者在工作树外固定 06 增量稿：完整 Git bundle SHA256=`b669afc9019da17df1c2c5c50e4c4df129c102b31c82af427d236cccae2b05a3`，本人 `git bundle verify` 确认完整历史且唯一 HEAD=`94b25a3279`；源 detached worktree clean。节点脚本 `node-incremental-06.sh` SHA256=`cb7b1d32cbc99b3980abaaf4d25efac823a9694922fe756c3ba9da6c195d7e5e` 固定旧 `a1`→新 `94b`，检查同一 Rust tree、六锁未改、clean/legacy/节点标记、root toolchain、离线/native build input；五包 Ruff/mypy 后仅跑 `test_real_dump_journey.py` 非串行/串行两遍，不重复旧 archive focused。该范围符合新差异。

初版外层 `prepare-run.sh` SHA256=`223f775027c18bf59828f08ecde0bf9431bb45ab42a8e07dd41a60a52201717d` 在 06 不存在父目录时使用普通 `mkdir node-input`，本人只读 SSH 确认父目录缺失，因此执行前指出确定性工具错误；旧稿未执行、撤回，不计一次 DC68 运行后修复。实施者仅改受控创建为 `mkdir -p`，保留目标路径与 RUN_ROOT 不存在断言。修订外层 SHA256=`febaf5e66ba7c6e8164c468b9b2e2cf1f0f44130a4db44113fda1501c206ea66`，manifest SHA256=`8654f7672d80dcd3a32cafbdbbcff9f5a6b7606d58dc06de301dcd69cd684f73`，节点脚本/bundle 不变；本人重算并静审 **CLEAR**。外层以 BatchMode SSH/LAN 传固定 bundle/节点稿，核 SHA、记录入口 numeric exit、回收节点日志及副本 SHA；运行尚待原件。

新四例容器稿主体 SHA256=`983122b02d9ee4b3bb05eaad9af119026fb7c162d732bb4c5b4f800a22a5fb10` 已静审：固定 `94b`，四个确切 `integration`+`serial` nodeid 按 archive→ordered→submit→history 每例独立 Compose project、本机构建、provenance 与三镜像身份绑定，失败即停；五项 asset SHA 与 §6–7 一致。初版新 focused guard 的日志路径待实施者固定，故该 SHA 未放行。修订脚本只把 guard 指向实际 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-06/node.log`，最终 SHA256=`24c2e4502acb4ea3e5ebf3a1ac8f8a482e25c6a535a17e4c5e70a9de3ddeefdc`，本人重算且静审 **CLEAR**。它仍须等新 focused 日志独核、节点缓存与镜像/磁盘空间前提合格才可执行；旧 `9831…` 和 `a1` 容器稿均停用。

容器外层 `prepare-run.sh` SHA256=`a967af868125c01bc0cff8fa89b85716d570a12af6d84b1349403d502809be6a`、`assets.sha256` SHA256=`01ab1aecdc79c6b832163fe177a68c080b0e6a1c4b30adb79da6498d922d1468` 已由本人逐字核审；manifest 列出的最终 node `24c2…` 与五项资产实读 SHA 均匹配。外层在 clean `94b` 源 WT 验证后 BatchMode SSH，核节点标记/RUN_ROOT 不存在，以固定目录受控 `mkdir -p`、逐项传输并在节点核 SHA；记录 node 入口原 numeric exit，即使失败也尝试捕获外部日志，校验 `container.log` sidecar，原 node exit 优先返回。**外层静审 CLEAR**；其文本没有增加自动重试或替代 focused 原件独核。

## 12. `94b25a` 增量 focused 原始证据核收

唯一执行者在 `gw-dms-06` 以修订外层 `febaf5e6…` 和固定节点脚本 `cb7b1d32…` 于 **16:53:21–16:53:48 UTC** 执行。本人重算外层日志 SHA256=`89e8ef07a8442c3efd8e3ab15bfa451c3a0dad1dad62151481b11c8b878f5215`、captured node 日志 SHA256=`56808f65b9d75b1ec73b8aa5def20e767a78f6124e436daae0a8289b863945a5`；经 BatchMode SSH 直接重算节点原 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-06/node.log` 与其 `.sha256` 同为后一值。外层显示受控 bundle/脚本传输与远端核 SHA，node entry/capture/outer exit 均 0。

节点日志 13 个 start/end 步骤成对且 exit 0：native checker expected=installed `9d4f84ce0897099402226c77c548c487c4912008`；五包 Ruff/mypy 十项全 0；完整 `test_real_dump_journey.py` 非串行 **74 passed**、串行 **3 passed / 74 deselected**。六锁前后六行逐字一致，`lock_drift=0`；起点旧 `a1ca3bad93`、检出目标与末 HEAD=`94b25a32792821cbc5b3230d98a0aa6f13493c32`，末状态 clean；entry/final exit 0，标记释放文件/目录均 0，本人 SSH 现场核标记已不存在。**新候选增量 focused PASS**，本人已直接通知唯一执行者可在缓存、镜像、磁盘与资产传输前提合格后运行四例容器。容器结果不由本节预记。

## 13. `94b25a` 四例容器原始证据与结论

唯一执行者于 `gw-dms-06` 用最终 node `24c2e450…`、outer `a967af86…`、manifest `01ab1aec…` 于 **16:57:42–17:02:53 UTC** 跑固定 `94b25a32792821cbc5b3230d98a0aa6f13493c32`。本人本地重算外层日志 SHA256=`674ac39773fed46748fd13ca5e3c5b120bbd262f342cbd7488ce39b78642d51e`、captured `container.log` SHA256=`f6a1b6c1b305bdcf127b73a251aaee9559a422d9bd8baf8a2d68b4c37981538b`，经 BatchMode SSH 直接重算 06 原日志与其 sidecar 为同值。node entry/capture/outer、node entry/final exit 均 0；24 个 start/end 步骤成对且 exit 0，含 backend dependency-base 原 config/全 19 DiffID/输入 label 的 `IDENTITY_MATCH`、RS base lock label 检查、四组镜像导出/身份生成及四次 `COMPOSE_RUNNING_IMAGES_BOUND_TO_SAVED_TAGS=1`。

| Compose 旅程（均 `integration`+`serial`、`-n 0`） | 实际 pytest | 运行镜像 identity JSON SHA256 | 本次容器 provenance SHA256 | 节点 runtime tar SHA256 |
| --- | --- | --- | --- | --- |
| archive-only 关闭/重新上传 | 1 passed | `b93a7c92225e11cf774377df03fe1d2e46d7307688362ea014a4868b16445333` | `c51a9d200317d148bd89224230b0ac585de5ca738acedfcb24086ecf61498491` | `2c9280be6e24d0aaf89adc8e311ffac300549df7d79f28c1fb3e633aa9765c79` |
| ordered compare 归档 | 1 passed | `5cae06c05a457cf478ea7522cdcdf5f03335534c4f378b026bca1d14d980e19e` | `397ce300988ec882bf8e83d91bce0169e447b6a79005fb1943d03c3ef44ce5f3` | `2de0e49ae5e037ffb30931fc60e5deb3a9d08fbcc860c8887cf000e36bf0081e` |
| submit 删除表归档 | 1 passed | `f8a6fb4f010b2a953c1f8c7bea2f663bcb0cc23f7d72d326b968147d1e7f4252` | `aa9e30799d813e409a813101e855ab13efc294d4c6b16427172985d7527967f4` | `34266641f34e2405bf716a4683051a8a5fedd3a3d3826d2d010383f3a644eff4` |
| History compare 归档/重启 | 1 passed | `d4497e72116f74dfd4ee083528e84c3f07b7e680b7f7ba3690d4873329eabb6f` | `500932353871b201f7d2e2fa46cbf59d80bd2ffccbe1b1ac414c7a696315457f` | `32c2f968505a9d50cd083b14041d4a11b0048e8f2bcfd89e304220e6212ffd1d` |

本人逐个读取四组 JSON，并对照 06 原件与 captured 副本 SHA：每组 backend、worker、RS 三个运行容器的本机 image ID 等于本次保存 tag 的本机 ID，config digest 和全部 RootFS DiffID 已记录（backend/worker 各 13 条、RS 28 条）；跨节点不以本机 ID 作身份比较。RS 在四例均使用专用 `94b` tag，revision=`94b25a3279…`、build-input=`c6a2792901ad9e1c90c401b455258685c4f4e2e0`、source-tree=`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646` 与本次 repository build identity 一致；该 identity JSON SHA256=`d1fad414e347659c460db19fbe81e53924dca06346cf28d626bc76a3179f5dee`。RS 预置 base 仅记录观察候选/lock label/config/全 DiffID，不伪称构建来源，观察 JSON SHA256=`fe244b7b7093644cdacd5b44695f2bfdb202bed1eb559a7ffe08b85dd1e492a6`。四份 runtime tar 本人经 06 原路径重算 SHA，均与表中一致。

六锁前后逐字一致、`lock_drift=0`；起止 HEAD=`94b25a3279…`、worktree clean、每例自身项目容器/卷/网络清零，最终标记文件/目录释放 exit 0。本人现场复核 06 marker absent、Docker running 0、host 8000 无 listener。同一来源 worktree 与四份 runtime tar 留在 06，供后续 H/阶段绑定核验；不擅自清理。§9 消费者 finding 因 `94b` 的静态复审、真实旅程 focused 与四例当前 HEAD 容器实际通过而**关闭**，固定候选 **BE-Q18 GO**。

FE 附加的生产 OpenAPI 单次只读抓取在 archive 容器健康/8000 监听观察后遇 curl exit 7、HTTP 000，未生成响应文件，也未重试/重启；原观察记录 SHA256=`be9044d5a81ca486866fd920b1c3080ae7813233017589840caff72757ad8925`。此缺失不写成 OpenAPI 快照已交付；旧 `a1` 的 OpenAPI 必填字段 focused 与未变的 `94b` DTO、真实容器 API 旅程足以支持本次接口结论，FE3c 自行按固定后端刷新快照与生成类型。Q18 GO 不解除 S3 `BLOCKED_CAPACITY`、不代表六包权威 runner/真实 t1–t4/正式性能或 S4 代码已验证。

## 14. 最终交接文档独立核收

本人只读审核 root 的单路径交接提交 `8cf472a4dd`（`p6-be-q18-handoff.md`），与固定产品 `94b25a32792821cbc5b3230d98a0aa6f13493c32`、本报告 §8/§12/§13 的原始日志及四例镜像/容器证据逐项对照。交接明确区分 a1 未变接口核心的 181 个 focused、94b 增量的 74＋3 个 focused、94b 四例容器各 1 passed；没有把本项 GO 扩大成 S3 容量、全量 runner、真实数据、S4 或前端退出。附加 production OpenAPI 抓取缺失与前端自行刷新也如实保留。

本人重算外置 `captured-json.sha256` SHA256=`8d822d319df52d9618a9af098eba7e877d6f2847eb9585da32c8dc7afab00fe2`，逐项 `sha256sum -c` 核对四组 runtime identity、四组 provenance、repository build identity、RS base observation 共十份同字节副本均通过；交接中的路径与摘要匹配。该提交仅改交接文档，`git diff --check` 通过。**交接文档核收 CLEAR，无新增 Q18 finding；§13 的固定 94b BE-Q18 GO 结论不变。** 此次仅审核文档，没有重跑测试、重建镜像或判定后续 main 的 carried。
