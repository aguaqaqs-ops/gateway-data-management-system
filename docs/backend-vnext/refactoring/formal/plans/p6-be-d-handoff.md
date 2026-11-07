# D BE-d 完整 tar 实施交接

2026-11-07；实施 `/root/be_d_impl`（GPT-6.1-Sol / xhigh），独审 `/root/be_d_review`（GPT-6.1-Sol / max）。产品基线 `9ec62e82ad9b70776a03954c30edb94a29e1380a`；实际开始 main `dfc8659744`，初始 status/diff 为空。协调者维护工作单、kickoff、联合准备与总交接，本角色只改本文及下列 D 文件。


**当前本地里程碑：产品候选 `0ba45e5ef83f54bfb2585f963f9518d32086f942`，`vnext` tree `0301aee3a39e3a5dfc37360e9c2062e660eb01ea`。06 受影响定向、五包静态、当前最小 Submit Compose、production OpenAPI、生产 encoder 同 tar 及独立 consumer 已完成；原独审 `6ad7e54fa0` §14–15 核收本地通过。06 本人资源清理后于12:05:51Z释放，非后续预约。联合首轮a999已执行：05 fresh t1通过并释放（§10），04首轮7fail已修，49403最终六包已原exit0；RS旧身份原件缺口保留（§12），Owner已批准方案A，当前同49403执行最小补验（§13）；尚无联合最终 GO；FE3 同字节 OPFS 互通也未解除。** §6及§7前半保留历史失败、暂停与恢复事实；06本地结果见§8；联合当前态以§13为准。旧 aaa 首轮原日志丢失及误跑永不作为当前通过来源。

## 1. 公开 port、准备结果与顺序

`BundleReaderPort.prepare_bundle(artifact_id: str) -> PreparedBundleDownload` 取代旧 `read_bundle -> tuple`，不保留旧格式。准备对象包含 `bundle_digest: str`、`content_length: int`、`filename: str`（`bundle-<digest hex>.tar`）、`etag: str`（含 HTTP 双引号）、`stream: Iterator[bytes]` 和幂等 `close() -> None`。`prepare_bundle` 是同步实际执行的函数：授权/exact scope/readiness/TTL 在 orchestration 先完成，随后取得共享读取借用，读取并验证 metadata，再逐项完整读回所有成员，最后才返回对象；route 创建 `StreamingResponse` 时预检已经结束。

prepare 协调实现为 `application/bundle_download.py`，`artifacts/bundle_download.py` 仅有纯 Prepared DTO/typed error，tar framing 在 `artifacts/tar_stream.py`。manifest 没有 closure 的物理 ref。owning capability 公开 `read_bundle_transport_metadata(manifest_raw)` 从已发布 manifest 的既有 semantic fields / closure entries 按原 JCS 和既有 content-identity 公式求出 expected closure ref，再读取并核对该**原已发布文件**；不把重建字节当作下载文件，不新增持久字段或改业务摘要。manifest / closure 的 canonical bytes、版本、bundle/semantic closure digest、entry size/raw digest 与 ref、pair surface ref 及既有有界 reference metadata 的嵌套 ArtifactRef 闭合在 owner 内校验。generic projection / diagnostics / OTHER 业务 JSON 依既有 assembler 发布校验和最终 raw SHA 逐块读回，不新增16MiB产物限制。下载严格按最终 closure 顺序发每 entry，重复内容/同源不同路径不再去重。

Artifact 最小公开扩展为 `ArtifactStreamingStorePort.get_ref/read_exact/read_session`。Local store 的 `read_exact` 安全打开普通文件、逐块校验 size/SHA，`read_session` 借用 root 目录的共享 `flock`；bounded cleanup 对同一目录取排他非阻塞锁后重查 eligibility，冲突返回 retryable。锁只使用现有 root 目录 FD，无新文件、DB 行、下载状态机或 mmap；信任边界仍为 ADR0012 协作进程。

## 2. 错误映射

| 实际边界 | Preview | History |
| --- | --- | --- |
| 未认证 / 当前权限或 scope 不符 | 原 401/403/隐藏目标 404；读取前拒绝 | 原 401/403/隐藏目标 404；读取前拒绝 |
| Preview 未就绪/过期、History 非 SUCCEEDED 或缺有效 assemble checkpoint | 沿 `read_preview_result` 原分类 | 沿原 `RESOURCE_NOT_FOUND` / `ARTIFACT_UNAVAILABLE` 404 |
| 已授权 metadata 或任一成员不存在、不可读（ENOENT/EACCES/EPERM） | 404 `RESOURCE_NOT_FOUND` | 404 `ARTIFACT_UNAVAILABLE` |
| metadata malformed/非 canonical/版本或交叉 digest 矛盾、ref 不符、大小/SHA 错、缺失引用、非法/重复/保留 path、symlink/非普通文件 | 窄 typed `BundleIntegrityError` → 503 `BUNDLE_INTEGRITY_FAILURE` | 同左 |
| 已解析 PreviewResult 的 expected bundle digest 不等/空值；History checkpoint expected 缺失/不等 | 头前typed503并close prepared | 同左 |
| 其他准备期文件 I/O 故障 | typed integrity/unavailable 边界内脱敏 503 | 同左 |
| 响应头后 I/O 故障 | 传播并中断流，不补 padding/end blocks | 同左 |

`ArtifactUnavailableError` 是存储层窄缺失/不可读类型；不再把所有 `ManifestVerificationError` 转成 404。响应不暴露私有路径或业务行。OpenAPI 200 只声明 `application/x-tar`，明确 Content-Length / ETag / Content-Disposition，新增 typed 503；无旧 JSON/octet-stream 双格式。Preview 原始行若连 `digests.bundle_digest` 键都缺，原 `read_preview_result` mapper 可先发生 KeyError，不在新增绑定检查try内；不扩称所有原始Preview行结构错误统一503，不重开V1 facts分类。

## 3. 生命周期、资源与编码

准备失败立即关闭借用；成功返回由 route 的 response wrapper 在 ASGI 调用 `finally` 关闭，覆盖正常结束、发送异常、客户端断连和取消；iterator 自身也 `finally` 关闭，`close` 幂等，未开始迭代的对象仍可关闭。生成器不持有全包 FD，不依赖普通 BackgroundTask 才能释放。协作 cleanup 在读取期间不删除本 root 产物；完成后可重试。

逐成员 prepare 与 send 均使用 64 KiB chunk；root 目录锁一个 FD、当前 artifact 一个 FD，同时最多两个活动句柄，mmap=0。发送期保留 manifest/closure 原字节各≤16MiB；预检另保留 expected closure≤16MiB，并逐个读取既有有界 reference JSON≤16MiB，join期间的分块与结果临时字节也单独计入metadata预算。parsed结构、路径字符串与entry索引为 O(metadata bytes)，不冒称所有内存仅64KiB。PAX路径逐16Ki code points切片编码，单片≤64KiB，不额外构造整条path/PAX bytes，不新增路径上限。原 `CountingStore` 实际计数字段的≤2活动handles/≤64KiB chunk cap断言已通过；日志未输出精确peak，不虚报实测RSS或精确峰值。

自有确定性 POSIX ustar/PAX encoder：512-byte header，uid/gid/mtime=0，mode=0644，uname/gname 为空，普通文件 type=0；UTF-8 非 ASCII 或超出 ustar name 的路径使用局部 `path` PAX 扩展（type=x，固定非业务 header 名）。size 超11位octal使用标准 PAX decimal `size`（普通头size=0），保留ArtifactRef完整I-JSON范围；仅header/length小向量，不建大文件。PAX length 按整条 UTF-8 bytes 固定点，字面向量 `12 path=中\n`。路径逐16Ki code points编码，每块≤64KiB，不构造整条路径/PAX bytes。总长度与发送共用每 member 的 header/PAX plan，包含 padding 与两个 512-byte 零结束块，不增加 10 KiB record padding。固定小向量独立断言实际长度，Python tar reader 作为互通 consumer。

## 4. 精确文件与唯一测试 owner

产品：`vnext/backend/src/gateway_backend/artifacts/{store.py,bundle_download.py,tar_stream.py}`；`infrastructure/artifact_store/{local_store.py,bounded_store.py}`；`capabilities/bundle_assembly/{transport.py,__init__.py}`（公开4个metadata符号，共享既有identity helper，不改业务输出）；`application/bundle_download.py`；`bootstrap/composition.py`；`http/dependencies.py`；`http/orchestration/{bundle_stream.py,history_compare.py}`；`http/routes/{preview_results.py,history.py}`；`http/bundle_response.py`；`benchmarks/{real_dump_journey.py,bundle_tar.py,bundle_interop_fixture.py}`。

实际增量：`application/preview_jobs.py`、`application/history/compare_jobs.py` 把既有 `bundle_result.referenced_artifacts` 加入原 `required_refs`，使final rewritten/原closure在首次下载前即随现有publication事务受保护，保留全部原恢复refs、owner释放/TTL，不改业务digest/golden；此producer缺口已单独报告并经协调/设计者按既有Contract确认。`benchmarks/bundle_tar.py` 集中完整tar consumer；`tests/support/compose_gate_harness.py` 的既有JSON下载消费同步改用该consumer。`_assembly.py`最终无修改；`__init__.py`正式公开 `BundleTransportMetadata`、`BUNDLE_REFERENCE_METADATA_KINDS`、`read_bundle_transport_metadata`、`validate_bundle_member_metadata`，application只消费capability公开surface，无架构allowlist/兼容转发。

| 不变量 | 唯一测试 owner / 拟改文件 |
| --- | --- |
| tar header/length/PAX UTF-8 固定点、ASCII/中文/非BMP、相邻记录/位数边界/畸形 consumer 向量、每 closure entry 一个普通成员 | `tests/test_bundle_download.py`（新） |
| metadata/ref/path/digest 预检，流中失败/未开始关闭/断连/cleanup 协作、64 KiB/2FD 代表性计数 | 同上；复用轻量真实 Local/Bounded store，不建 Dolt |
| 两公开路由授权先行/状态/缺失/typed503、头与关闭接线 | 参数化 `tests/test_bundle_download_http.py`（新）；旧 `tests/test_preview_read_http.py`、`tests/test_history_http.py` 仅更新 fake port/格式断言 |
| Preview MODIFIED_ONLY/FULL/replacement 与 History 两/三节点真实 job wiring、共享/异schema/空表/closure摘要 | `tests/test_bundle_download_http.py`；复用 `tests/support/http_workspace_harness.py`、既有 preview/history job harness；既有 job/assembly owner不复制矩阵 |
| OpenAPI 唯一媒体及 headers/错误声明 | `tests/test_http_openapi.py` |
| 实际 FULL multipart 输入、双 pair default consumer、tar 全成员/各物理与逻辑摘要、GET完整时间/bytes只报告 | `tests/test_real_dump_journey.py` |
| 当前06容器下载smoke、production OpenAPI/provenance | `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`（0ba实际通过一次） |
| History容器两/三节点完整tar | `tests/test_history_compose_e2e.py`（04最终权威runner待跑；06已有上述真实HTTP/job owner，不重复长旅程） |

Owning 正文只改 `docs/backend-vnext/contracts/comparison-bundle.md`（完整 tar/顺序/头/错误/生命周期/上界），必要真实 port 条款写入该 owning Contract。没有新的业务 golden；原业务 manifest/digest/golden 应原字节保留。共享前端向量由生产 encoder 在06 clean候选生成到 WT 外：同一 tar 包含 ASCII长路径、中文、非BMP，并交原 metadata、各文件/整包 length/SHA、命令/候选/节点；不是新协议 golden。不得改 frontend 或前端文档。

## 5. 实施与验证次序

1. 本清单先提交并直交同一独审预检；依次实现公开 bounded artifact 读取、owning metadata decoder、encoder/prepare/response、两路由与 tests/Contract，固定首产品候选早交独审。
2. 同一后续候选完成 main 真实工具：v1 MODIFIED_ONLY；v2 FULL，INITIAL=v1/MODIFIED=v2；默认业务摘要和 identity 明确取 `initial_to_modified`，另核 `baseline_to_initial`，完整 tar consumer 覆盖两 pair 所有成员；保留 V2 显式归档 reason 环境输入，不 force。

实际功能入口为 `--tier t1 --scope full --v2-input-completeness FULL`，**完整执行命令待最终清单对齐，不执行先前草稿的小fixture N4/M24MiB例子**。host kernel CLI与Compose worker独立：保留已审worker N1、32GiB envelope / 8GiB reserve / 显式M24GiB=25769803776B、单active；host scope沿原S2b E fresh t1实际命令N1/M25769803776B，CLI `--kernel-threads 1 --kernel-memory-budget-bytes 25769803776`；不用t3校准48GiB。pytest/Cargo jobs4只是测试并行度。`--scope full`仍仅表示步骤范围，新增flag才决定v2真实FULL multipart。v1/repeat-v1仍MODIFIED_ONLY；v2 INITIAL与已归档v1同字节，MODIFIED=v2。summary与identity均按请求mode强制确切pair集合（FULL两pair、MOD_ONLY一pair），两个pair均查无降级/失败且baseline_to_initial不变；default summary/identity只取initial_to_modified；所有pair/member均由tar consumer核原metadata、精确顺序、size/raw SHA、引用metadata和records owner逻辑content digest。GET完整读时间/bytes独立只报告，原completion/user-visible在GET前冻结。

前端额外已知接缝：现consumer只读取PAX path且有1MiB PAX body限制；标准size记录、octal边界及I-JSON max仅交header/length小向量，不能冒称大文件互通。主共享tar仍是可完整安装的小制品，后端不新增路径/产物大小上限，FE资源上界由其owner核对；FE修复/同字节证据仍待。
3. 06 BatchMode 连通/现场核空闲后原子本人 marker；LAN bundle 传源码到独立 clean 已提交 WT，legacy 链接、离线缓存/toolchain/dependency-base；`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp`、Cargo/pytest workers4。即使 Rust 无改仍强制重装扩展并核 build input；五 Python 包 ruff/mypy；focused 非serial -n4、serial -n0，空批 exit5 为 N/A。失败原日志/SHA保留，产品失败先停诊断。收敛后一次必要当前小型 Compose 和 OpenAPI/同字节制品。
4. D 独审与06局部证据完成后，同两角色继续已授权联合准备/集中核收：先与协调者固定最终命令/候选，04实际受影响六包权威及其中必要Compose，05一次fresh t1上述两模式完整旅程；不重复同runner Compose，不触冻结基准/CT108。联合退出前 DC33 最终范围仍交 Owner 确认，不自行exit/tag/push，不称 FE3 完成。

当前 container gate：0ba在06离线重建backend/worker并实际通过一次上述最小Submit Compose，production OpenAPI与实际运行镜像身份已保存（§8），非沿用V2。04联合最终权威runner包含必要完整Compose仍待，不重复同runner已覆盖旅程，不由06小旅程代替04门禁。

## 6. 历史候选、已有证据与验证暂停事件（§7已授权恢复）

产品首候选 `36edb20086`；`1c14572725` 清理旧imports/fixture名；`e3b54b8f71` 修F1（generic业务JSON不得误套16MiB metadata上限）；`7f25a1657a` 修实际HTTP受理fixture；`d0a22ba91d` 完整工具/F2保护接线；`aaa0f4a6f3` 测试typing；`8de2a9a060` F3按请求mode强制确切pair集合；`a7954b6b55` 改为首次GET前核manifest/closure/全部final保护；`445a19dfe3` 同步store缺失错误文案。当时独审GO尚未形成；后续本地核收以§8为准。

06新WT `/home/dev/gdds-test-tmp/wt/p6-be-d` 从11:01:37Z取得本人marker开始，使用预填充离线uv/Cargo、独立新venv、Cargo jobs4；source经CT201 LAN bundle传输。36ed新环境强制重装Rust扩展成功，expected=installed `e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`，sync log SHA `cc0eacc8f9615a531877837661a3f6165297f7d867f11295229c7eae10a215b6`，build-input log SHA `1b12990473ed30492e14a01806f4ed8d691b3730e9dd951202f767920945cbb8`。Rust/toolchain同1.97 selector已核，无Rust源码改动。

| 节点/候选 | 实际结果与原log SHA | 适用边界 |
| --- | --- | --- |
| 06 /36ed | ruff2个unused import失败 `2274c2d154019de8642ed3693ec9e8434cd3f51f56a0972ea764fce20ecfa0d2` | 保留失败；随后1c修正 |
| 06 /1c | ruff0；mypy仅新test helper Any return失败 `e11d53006633b920e735fda5b509cab2a6515f765a66d487a76598b42ef62faa` | 随后e3修正 |
| 06 /e3 | ruff/mypy0；focused142pass/7fail/8error `e75aeb3b607d4caa17b87bee7550288863b6ed27cb6f958b919989f108f8ac85` | HTTP新fixture未mkdir/缺acceptance business_ref，不能记整批通过 |
| 06 /7f | 实际HTTP owner21pass `e62743e2029562f7062dc7531e4baf42314383e996bce7a9098e967abbff42d3`；ruff/mypy0；serial21deselected/exit5 `c2519e8d723b19562071a01d891e5fe8c9003e1d12e3e2fe193c777ff7e92706` | marker按主体 `(not serial) or parallel_safe` -n4、serial例外 -n0；空批N/A，脚本`http-fix.sh` |
| 06 /d0 | ruff0；mypy5个新fixture typing失败 `f54653969e3e1aad6b3a6060d6b5fe7f1de9343996871faeedb38d24dadd9e16` | 随后aaa修正 |
| 06 /aaa 首轮 | 工具输出记ruff/mypy0、focused141pass/1fail（CLI fixture漏新flag），旧focused SHA `2345ec835d433ff55a548697c0faeebc67ff8cbb8779b27d35b98c23b14a3cc2` | **三原完整log被后述误跑覆盖，原字节不可复核，不作为通过证据；只保留工具输出/历史SHA事实，不重造** |
| 06 /aaa 误跑 | ruff/mypy0（当前log）；focused150pass/2fail（旧CLI fixture+store旧错误文案）`f882a86a8a0e472b80fa2897e61a1ffc4237a1cee9a3a73ffd8526780bedb9c5` | 不代表目标a795或最新445，完整当前文件保留 |

11:16–11:17Z实施者传输编排失误：用纯SHA而非named `HEAD`建bundle被Git拒绝empty；本地编排未`set -e`，继续传旧bundle；目标checkout失败后仍单独启动旧aaa WT上的focused。该轮已触及旧被测对象，**不能按DC68产品前操作错误单次重做**。同HEAD日志名覆盖aaa首轮ruff/mypy/focused三份原文件。独审明确没有aaa原副本；不拼造恢复、不把后次当首次。

更早checkout的时间只能由相邻原log界定，未记失败秒级UTC，不伪造精确时间：①11:03:35Z 36ed静态失败之后、11:04:31Z 1c复查之前，首次传1c时在linked WT使用primary WT才有的FETCH_HEAD，checkout128；随后改完整1c SHA成功，才启动1c复查。②11:14:43Z d0 mypy失败之后、11:15:21Z aaa复查之前，传aaa typing修订时手填了不存在的literal `8c3f3bd0dc`，checkout128；随后改真实完整aaa SHA成功，才启动aaa首轮复查。两者是不同候选/不同传输步骤，不是同一步连续重做；每次失败当时未启动被测对象，后续成功后的产品执行另记。两次错误输出由工具回包保留，`checkout-operation-error.log` / `checkout-typing-operation-error.log`是事后从工具输出整理的**派生说明**，从未有原命令外置原log，不能称原执行原字节仍在。第三次11:16–11:17误跑与日志覆盖不适用前述产品前例外。

当时协调者接报后明确暂停全部受影响节点focused/static/Compose/04/05，未经Owner回复不恢复。当时仅做证据保全、资源清点/本人释放和可审查guard修正，其他无关产品/工具代码可继续；没有任何D Compose或联合权威/真实旅程通过声明。

保全目录：06 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/incident-preservation-rvpm66sO/`，保存事件时现存log/script/bundle、actual HEAD/status、进程、容器及8000快照，`SHA256SUMS` SHA `78122ba8b893b200c17ad9ae959af5fa7d25cc830f59986043f2b40298ca065b`；LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-d/incident-preservation-rvpm66sO/`。保全时WT为clean `aaa0f4a6f32143448c1b55bb1cc8f509643e1d3c`。11:19:30Z确认无本任务服务/运行容器/8000/Dolt/Cargo/pytest，仅释放本人marker；释放log `node-release-UzrHOQAs.log` SHA `de06e368c6459639f0f04525cdb6a9763edaa30e85eb3e8ff6a21b97422b8ae8`，副本同上。旧WT、卷、镜像及证据未清理。

可审查guard（以下是批准前仅写文件、尚未执行/测试的历史状态；§7–8记录批准后的实际执行）：本地 `/home/dev/gdds-be-d-guarded-transfer.sh`（副本`/home/dev/gdds-reviews/artifacts/p6-be-d/guarded-transfer.sh`），SHA `f83066c0b15a012bf5df673577591910e5b0afd4926553d4f3592ef5edff9d4d`；node-run `/home/dev/gdds-be-d-guarded-node-run.sh`（副本同目录`guarded-node-run.sh`），SHA `4eb10c9fc1a8b3b12d4b5ae4cba4d54528d7462d7a5a8f91549facb0e7c979b2`。两者`set -euo pipefail`，transfer以named HEAD建bundle并verify/核advertised完整SHA及SHA256，任何失败不继续；节点checkout显式完整SHA并核clean/exact HEAD；run每次`mktemp`独立WT外目录，保存精确命令/guard，运行前后核完整HEAD/clean及本人marker；end marker不同或丢失记录`end_owner_marker_matches=false`，保留`command_exit`原值并使`final_exit=2`。无需新evidence状态机；同一独审静态核后由协调者提交具体恢复方案给Owner，当时Owner回复前不执行；该停点已由§7明确授权覆盖。

两guard当前mode664，实际入口均为`bash <file>`；transfer只传source bundle，不安装/执行node-run。Owner恢复后，协调固定clean实际完整SHA（届时含审核/批准文档，核其vnext tree与已审产品相同），赋给`D_EXPECTED_SHA`，再用`bash /home/dev/gdds-be-d-guarded-transfer.sh "$D_EXPECTED_SHA"`传源码。node-run单独经LAN `scp /home/dev/gdds-be-d-guarded-node-run.sh ct107-gw-dms-06:/home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh`，核SHA后以`ssh -o BatchMode=yes ct107-gw-dms-06 "bash /home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh '$D_EXPECTED_SHA' <label> <command-and-properly-quoted-arguments>"`调用，不能`bash -s`令`$0=bash`而使guard自复制错误。具体待恢复命令由协调清单列明，不以这个占位示例启动。释放原log的精确本地副本是 `/home/dev/gdds-reviews/artifacts/p6-be-d/node-release-UzrHOQAs.log`，06原路径是 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/node-release-UzrHOQAs.log`，它在incident-preservation子目录外。

当时拟定的恢复调用形态（历史占位，已由§7–8实际exactSHA运行替代）：

```bash
# D_EXPECTED_SHA由协调填恢复时clean实际完整SHA；先核审查产品vnext tree不变。
bash /home/dev/gdds-be-d-guarded-transfer.sh "$D_EXPECTED_SHA"
scp /home/dev/gdds-be-d-guarded-node-run.sh ct107-gw-dms-06:/home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh
ssh -o BatchMode=yes ct107-gw-dms-06 "bash /home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh '$D_EXPECTED_SHA' backend-ruff vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync ruff check ."
ssh -o BatchMode=yes ct107-gw-dms-06 "bash /home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh '$D_EXPECTED_SHA' backend-focused vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -n 4 -m '(not serial) or parallel_safe' tests/test_bundle_download.py tests/test_bundle_download_http.py tests/test_real_dump_journey.py tests/test_workspace_artifact_store.py"
```

## 7. Owner恢复后的首轮与架构修正

Owner明确回复“按方案恢复验证”，授权提交 `c1d1beefb1260f21810a6809cc9f8ffb4b6bf78d`。该提交main clean、vnext=`e7dfe478e5abb721a4f968dd692380b3cb05f28f`，两guard SHA均未改变。11:35:41Z现场核06空闲后重新原子取得本人marker（非沿用11:19释放），owner副本 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/recovery-lpNIMtZE/node-owner.txt`。实际guard transfer目录 `transfer-UJm9QCM3`，完整named HEAD bundle SHA `7842b52cfd0ed2a106d6f1b43142c6a799a011ef217e0614487ed0d37d203140`，prepare原log记录verify/checkout/clean/完整c1d及exit0。node-run独立LAN安装至`guarded-node-run-v1.sh`，实际SHA=已审4eb10…，不是bash-s执行。

06 `run-prerequisites-c2NGDGTX`：11:36:39–11:36:40Z，legacy正确、local预填充uv/Cargo、无proxy、1.97全selector一致、Rust扩展expected=installed=e6ac…，command/final0，原log SHA `4a0e527b5f4f1c4c906314ceca681f68db7613a722783d85bd15f66412a71ecc`。venv沿此前合法强制构建，Rust未变，未无故重建。

06 `run-backend-focused-yPq3ZLFd`：当前c1d实际 **380pass/2fail**，唯一失败为原架构owner的依赖层约束；原command/final1、end c1d clean/本人marker true，log SHA `7ff99fbc8320be840074f44245bf74b403a71344edbd82f030ca96b9511067f8`。这是guard正确运行后的正常产品失败，已停后续serial/static/Compose处理；不适用或冒称DC68操作重做。F2/F3及下载向量在380实际通过项内，但不记整批通过。

最小修正：`artifacts/bundle_download.py`仅保留纯 `PreparedBundleDownload` 和窄 `BundleIntegrityError`，encoder仍在artifacts；prepare/metadata协调移至新 `application/bundle_download.py`，bootstrap从application导入函数。HTTP只导低层typed error，owning capability transport使用同一低层class，不增allowlist、baseline或兼容转发。相关test/benchmark import同步。06收敛Compose固定最小 `tests/test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey`，其共享consumer实际验证Preview完整tar，并从运行production GET `/openapi.json`保存全量schema及SHA；History两/三节点用原HTTP/job wiring定向证据，最终04 runner仍实际包括已修改的History Compose旅程，不在06重复长旅程。

联合05 fresh t1 host budget经协调从原S2b E fresh t1 `command.json`核实为N1/M25769803776B，后续沿该已过host值；Compose worker独立保持N1/M25769803776B、32GiB envelope/8GiB reserve、单active。§5已按此实际t1来源收敛，不试预算。

后续public surface修正 `ff704555f5` 只正式导出4个既有metadata helper/type/constant并由application公开消费；实际验证提交经无产品差异的他方docs前移到 `b1a43480d426e4e8959fb7cfab5bb2ffeb935227`，vnext=`603fb5d217db9612d243d8ea062e94ca02d12bd0`。原ff传输因main正常前移在本地guard前置拒绝，未建bundle/未触节点/未跑旧WT；协调刷新actual b1a后source_ready，目录`transfer-Ogy6zITV`。b1a架构+download owner139pass、selected serial382deselected/exit5=N/A、五包十项ruff/mypy0与e6ac扩展核0，均为新的唯一run目录，旧丢失/误跑不作当前依据；详细索引在本节最终核收补齐。

F5绑定修正：两个已授权路由prepare后、创建响应前比较 `prepared.bundle_digest` 与当前owning PreviewResult / History checkpoint 的 expected bundle digest，已解析Preview expected不等/空值或History checkpoint expected缺失/不等为typed503并close。一个完整有效但属于另一个结果的bundle也不能200；不增加port参数/兼容跳过/持久字段。`test_bundle_download_http.py`同一共享参数fixture用真实assembler生成第二个有效bundle，再只改own Preview binding /合法History checkpoint的artifact_id（expected保留），经真实public路由断言503/无ETag/借用释放。已有fake reader测试现在显式提供owning digest；真实正向fixture同步自身manifest digest，不把raw SHA当semantic digest。该段记录F5固定时的历史待验状态；后续0ba定向、backend/worker构建、Compose和interop均已完成，见§8；b1a RS依赖准备本身不冒称后端容器通过。

## 8. 当前06本地交付、原证据索引与释放

产品固定 `0ba45e5ef83f54bfb2585f963f9518d32086f942` / vnext `0301aee3a39e3a5dfc37360e9c2062e660eb01ea`；同一原独审报告 `6ad7e54fa0` §14–15 已独立核实际代码、原日志/四项SHA、生产制品、完整镜像身份及释放，F1–F5关闭，本地里程碑通过。本文后续仅docs，不构成新产品变更。所有实际运行在06 clean提交WT `/home/dev/gdds-test-tmp/wt/p6-be-d`，UV/Cargo offline、TMPDIR外置、jobs4；每run完整expected SHA与前后HEAD/clean/本人marker均保存。不是一次全选成功、权威runner通过或package/image carried。

证据根06 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/`；完整LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/`。18-run快照 `evidence-index-9ln5cjtm/index.json` SHA `d784bad64ed01670a143c5c05cf5789ff09df1999bd5639d94b558f2db03c7d2`，逐run列原log/command/guard/expected与SHA核验；该索引早于自身生成、cleanup和release，不循环声称包含后来文件。下表均相对证据根，具体完整argv在各run的 `command.txt`。

| 实际来源 | 结果与run.log SHA256 |
| --- | --- |
| c1d `run-prerequisites-c2NGDGTX` | legacy/1.97全selector/缓存/扩展build-input核0；`4a0e527b5f4f1c4c906314ceca681f68db7613a722783d85bd15f66412a71ecc` |
| b1a `run-architecture-download-hlGAQyFn` | 架构+download139pass/0；`d325886ee7bacc8fbd6bb6a10906377fadcd31716bd3a5b16fc71be0cadb01d8` |
| b1a `run-backend-selected-serial-KNgMhQf7` | 14文件所选serial382deselected/exit5=N/A；`eaf017844bf3c09a1c9f47578ac644d683775b2d118480296a7cd00cf7465a83` |
| b1a `run-static-five-423Ms53b` | 五包十项ruff/mypy0及扩展核0；`95cbb65963119850d2b54073838a08d9ab5e95d213ace8b67cfc92ef78ef4288` |
| b1a `run-dependency-input-nZPH2hbo` | backend依赖输入0，digest `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`；`3fb794d15ccbc390a0491d737babcb8fb3b37c0e1c83a724184fe9b6ce722978` |
| 0ba `run-http-digest-binding-rBoVUD3E` | 三HTTP owner74pass/0；`28daca20f2edd23b85a1fa69e499681efe1321a2098dc01c7c42aa1c73ea0211` |
| 0ba `run-backend-ruff-final-e5Kvyl1I` / `run-backend-mypy-final-wob5kWWW` | 增量backend静态均0；`b1106172e9d9902117080c61b481694f091e8ffd6298ad255e0fabb4e7368b32` / `dde47ec37c282e118fb632b31d82982af32eb5655cff37441e2174d285df437b` |
| 0ba `run-compose-tar-openapi-ZHVSgrfR` | 11:56:53–11:57:26Z，Submit最小Compose1pass/0；`89120149839192c49e4d5827fbaf3802078573eccb3c155acbc49719ffe145a2` |
| 0ba `run-interop-generate-LZPb1TzQ` | 生产assembler/encoder实际生成0；`457ac3a7da59396008394ebdf62171fa7c2aaf818975a4bec5b7adf7dcb7d455` |
| 0ba `run-interop-verify-OeWqqKQW` | wrapper拒绝外置.py，consumer未执行，command/final2；原失败保留 `f9827d7ed88809bee522a19bbcf40a7d41af32ff3da207a9707c31c52921f955` |
| 0ba `run-interop-verify-corrected-6TuXooMk` | root确认DC68首次无副作用前置错误，仅该步骤一次纠正；受控wrapper公开python-c只import已提交consumer+标准库，tar为数据参数，command/final0；`77dc8866fdff679b737740cc129ab3e8fda7c211cbd341b21b31f3626d5f4568` |

正常产品失败c1d380pass/2架构fail、4c8238pass/1公开surface fail完整原run分别为 `run-backend-focused-yPq3ZLFd` / `run-backend-focused-fixed-pQtmiknA`，SHA `7ff99fbc8320be840074f44245bf74b403a71344edbd82f030ca96b9511067f8` / `a5eb185d9ccf5dcd73ae83e308c8e0092bfb39fe3b389787958c074ba8d77e10`，保留且由最小移层/public export修正后定向补验，不改称历史整批通过。§6事故、三份aaa首轮原字节丢失及旧对象误跑不被本节恢复抹除。

### 8.1 当前实际Compose与镜像

精确nodeid为§4的Submit小旅程，实际argv unset `GATEWAY_COMPOSE_GATE_PREBUILT`、设置 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:be-d-b1a43480d4`、`GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee`；受控uv pytest `-n0 -m 'serial and not parallel_safe'`。正常Compose build保留，本机离线构建backend/worker后运行，非prebuilt绕过；RS原b1a离线build输入在0ba未变。无需重复该Compose。

`compose-output-eJGTujH4/production-openapi.json` 是实际production GET，SHA `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`；两route200仅tar、三headers与实际404/typed503声明齐备。`compose-provenance.json` SHA `9e3c0e525bb5677d705d870de38e49da309fa988e2077be8926f2c72ba6cea4b`，实际project `gateway-submit-s8-322478-test_compose_accept_upload_imp0`。

`image-identities-k0fu61o4/image-identities.json` SHA `184b2994f39de63432f3145bd3786c1eb4c8e300010aee455e0e007e85cd9661` 保存五镜像实际docker-save config digest与全部89项RootFS DiffID（13/13/28/19/16），并核inspect全部DiffID。backend/worker config分别 `sha256:2c2e0adb3ef9bac2f8c88a3ef635d91b888b5f6cc6dd5337f0e56d91774ff582` / `sha256:1279f49a9cdd87261f25b8a5dd665331e8c1f08bbd1e41dc2bee5382210a1735`；通过同机running image ID桥接当前build，不虚构其revision标签。RS config `sha256:2ac4ad9fda8863bf3a292870f611e61e68992f0096d9c8c6e6540656806cca72`，revision b1a，build-input `a6876d560050285321fd9f62942d590a03f35d64` / source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。依赖base来源为节点已预填充LAN缓存，不使用代理/公网；完整config/DiffID在同一JSON，不以跨节点inspect ID比较。

### 8.2 Owner可转发的同字节制品

实际生成命令与候选/节点见 `run-interop-generate-LZPb1TzQ/command.txt`。本地目录 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/`，06同名相对目录；`index.json` SHA `199d451123df6a0354e51c92e411aad1770553909d18ff07e6d4fecdd14ea38d` 列每文件和每closure成员length/SHA。

- `bundle.tar` **24576B** / SHA `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`，semantic bundle digest `sha256:2be243c36d03ef8f11fe9108283ff814631d1dda4aafa32d45380006fd5ef050`。
- 原 `manifest.json` 6062B / SHA `320f44e71bdf70f802a83c3362515a7399694a400b88551b9da41be9c8fb4f67`；原 `artifact-closure.json` 5232B / SHA `becf0b703c3dad4bf033341c88c3580ecdc66ae695a728bce5d912cf79f8897a`。共6普通成员，4closure entries：surface2275B，ASCII长路径/中文/非BMP Parquet各741B。
- `pax-records.json` 含 `12 path=中\n`、相邻记录、99/101位数边界及畸形length/newline/UTF8数据向量。三个 `size-*-header-only.bin` 覆盖8589934591/8589934592/I-JSON max；512/1536/1536B，`size-vectors.json` 明确 `complete_tar=false`，不能冒称巨大完整tar已互通。

提交内独立consumer核全部8文件length/SHA及完整tar顺序、原metadata、4closure raw摘要，输出reference metadata1、logical records0；该小制品没有records，不能用其宣称真实records逻辑摘要覆盖。FE须用同一bundle.tar完成解析/hash/OPFS，PAX UTF8字节、标准size及其资源上界由FE owner修正/验证；后端本地通过不等于FE3解除。协调已通过 `57aa092e33` 向Owner交该实际包，无需实施查前端会话。

### 8.3 本人清理与联合待办

`run-cleanup-check-5x362qHI` 12:05:24Z/0，SHA `4b95b3654f2396026e4d3ca25b03c99922b7ee6dc644f94832fea3bb3083827e`：本人project容器/卷/网络、端口8000及Dolt/Cargo/pytest/rustc/clippy为空。`release-O4scz5uE/release.log` 12:05:51Z/0，SHA `91da2118722b0ce0801f9ba9eb01b8e715b1efb584dbfeeedae2918adc92047d`，cmp本人marker后释放、HEAD clean0ba；独审12:07:27Z再次只读核空闲。保留WT、依赖缓存及所有历史证据，不碰他人资源。

本地handoff固定后，同两角色继续联合04六包/必要Compose与05一次fresh t1；exact candidate、各节点独立WT/owner/guard路径、完整CLI/env与逐项archive reasons先交协调和原独审静核，未对齐前不启动。05 host N1/M24GiB独立于worker N1/M24GiB和32/8 envelope；不试预算。最终DC33范围确认、阶段exit/tag/push及FE3互通仍分开，不在本地里程碑自行办理。

## 9. 原固定联合04/05执行清单（已审后按§10执行，当前进度见§11）

本节沿已授权联合收尾，非重复开工/恢复申请。当前产品tree仍0301，最终source expected由协调在本文及独审docs提交后固定**当时clean main完整40位SHA**，先核其vnext=0301；不能把0ba或413旧SHA硬套推进后的main。协调短main提交窗口内，两个source transfer依次完成source_ready即回报解除；此后main的docs推进不改节点固定WT。若发生guard前置HEAD漂移，保留拒绝并协调刷新，不拆开步骤或跑旧WT。

### 9.1 节点、占用与固定guard

| 节点 | 唯一WT | 独立证据根/owner副本 | 执行guard安装路径 |
| --- | --- | --- | --- |
| `ct108-gw-dms-04` / `gw-dms-test-04` | `/home/dev/gdds-test-tmp/wt/p6-be-ad-final-04` | `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-04/node-owner.txt` | 同证据根 `guarded-node-run-v1.sh` |
| `ct108-gw-dms-05` / `gw-dms-test-05` | `/home/dev/gdds-test-tmp/wt/p6-be-ad-final-05` | `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-05/node-owner.txt` | 同证据根 `guarded-node-run-v1.sh` |

固定本地脚本均mode664，用 `bash FILE`；仅静态生成，未在开发机执行/bash-n。它们沿06已审标准shell guard特化节点/路径/hostname，不增加状态机。transfer在exact fetched SHA上新建detached WT/legacy链接；初次执行先要求WT及证据根均不存在，若已存在先辨明归属，不覆盖/清除。后续同本人占用下修订才可复用clean WT。node-run每次 `mktemp run-<label>-XXXXXXXX`，保存原command exit和final exit、完整argv、guard、expected/前后HEAD/clean/owner与四项SHA，前提改变final2。transfer的bash-s无自复制；node-run必须是已安装文件入口，不能bash-s。

| 本地文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-be-ad-04-transfer-v1.sh` | `b4c371a552c26e7470bb97f06177667266ab58bbbb29fb694c203df86ea764b5` |
| `/home/dev/gdds-be-ad-04-node-run-v1.sh` | `b86cb3c1174899106c12d1245032a957656ce398d118c2165506b1d5b91e31ae` |
| `/home/dev/gdds-be-ad-05-transfer-v1.sh` | `3b5bfd131af481f922ac454939baee1beac9349c8ec2eccb30c44c3bdb9bcdea` |
| `/home/dev/gdds-be-ad-05-node-run-v1.sh` | `7e053a42c7f70c3dca7fad714775836bf9851a4d3501bc0b2dcfd5367d58680b` |

实际启动顺序固定：先各自 `ssh -o BatchMode=yes <alias> 'echo OK'`；现场核hostname、有效marker、整机进程/运行容器/8000与磁盘，不依赖协调11:58快照；无冲突再 `mkdir /home/dev/gdds-node-busy.d` 原子取得，owner写角色/本节用途/UTC，复制到新证据根，后续cmp只认该本人字节。标记与清单相符后才传source/安装对应node-run并比本表SHA。04/05可跨节点并行；本任务不在06/07发起重负载，也不碰CT108/冻结基准WT/卷/输入。测试期间不写WT、不提交、不手工retag/rmi镜像。

source入口分别 `bash /home/dev/gdds-be-ad-04-transfer-v1.sh "$AD_EXPECTED_SHA"`、05对应；node-run经LAN scp至本表固定server路径，核SHA后 `ssh ... "bash <guard路径> '<完整AD_EXPECTED_SHA>' <label> <正确引用的argv>"`。实际每个完整命令写其唯一run的command.txt，不以占位值启动。所有节点执行含shell syntax/static检查也只在该节点；失败原日志及SHA保留。

### 9.2 共同真实前提与构建准备

node-run固定 `PATH=/home/dev/.cargo/bin:...`、`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp CARGO_BUILD_JOBS=4 LC_ALL=C.UTF-8`，unset ambient proxy及RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME/PYO3_PYTHON/VIRTUAL_ENV。实际核legacy、1.97 selector全工具、uv本地缓存、Dolt、Docker/Compose、磁盘；不把06缓存当04/05缓存，不假定172.17缓存端点，不改canonical lock identity。缓存/镜像不符或缺失即停补LAN预填充，不开公网/代理替代。

backend已审依赖输入digest为 `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`，所选tag `gateway-backend-deps:lock-d054366c02fa`；RS依赖base `gateway-p2r1-repository:lock-6dc9659f0aee`（label须等当前RS uv.lock SHA）。04另核 `gateway-repository-client-e2e-base:local` 的 `gateway.p2r6.client-uv-lock-sha256` 等当前client lock，及当前本地Python/uv基础镜像。逐节点保存所选base的实际config digest/全部DiffID与原LAN缓存来源记录，先比既有来源；无依赖变更不凭空重造预填充时间。backend/RS base与§8同来源时以完整config+全部DiffID核，不以inspect ID跨节点比较。

每节点先在本地所选dependency-base上用仓库公开 `vnext/scripts/build-repository-service-image.sh` 离线build一次RS，env `GATEWAY_DOCKER_BUILD_NETWORK=none GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:be-ad-final-04-<expected前10位>`（05改对应tag）。保留实际build/identity，不碰原基准tag。随后所有runner/journey用此service tag。client final镜像若revision不符，由既有测试harness用已核本机dependency-base正常build；不手工docker rmi，不关闭harness。

### 9.3 04唯一权威运行

运行全部六包，公共fixtures相对原S2b来源已变，无package carried。以下env通过04对应node-run传给**一次**仓库权威入口；`AD_RS_IMAGE_04`为上节固定的实际tag。workers48是64vCPU正式节点测试并行度，不是产品N。未设置GATEWAY_TEST_BASETEMP，runner自有隔离Hypothesis及cargo-target清理规则不变。

```bash
env -u GATEWAY_COMPOSE_GATE_PREBUILT \
  GATEWAY_TEST_PACKAGES=rust,shared_kernel,repository_contracts,repository_client,backend,repository_service \
  GATEWAY_TEST_WORKERS=48 \
  GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1 \
  GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa \
  GATEWAY_DOCKER_BUILD_NETWORK=none \
  GATEWAY_REPOSITORY_SERVICE_IMAGE="$AD_RS_IMAGE_04" \
  GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee \
  GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE=gateway-repository-client-e2e-base:local \
  vnext/scripts/run-tests.sh
```

runner locked sync五包并强制重装backend扩展，实际核e6ac Rust build-input；输出全部六包起始manifest/总摘要及状态、五锁检查、Rust fmt/clippy/test、pytest主体非serial并行/serial例外单进程和必要完整Compose。同runner已覆盖的Submit/History/Archive等Compose不再额外运行。权威runner非0先停处理，不继续carried/后续验收，不把部分通过拼成整次通过；保存完整原exit及前后身份。04本次不是新增性能测量。

### 9.4 05唯一fresh t1与显式理由

05新WT先受控locked backend `sync --reinstall-package gateway-compute-python`，构建env `GATEWAY_RUST_BUILD_INPUT=$(git rev-parse HEAD:vnext/rust)`，随后仓库 `check-rust-extension-build-input.sh` 核expected=installed；无缓存即停。正式工具命令使用 `run --no-sync` 仍经wrapper只读lock核查。输入根 `/home/dev/gateway-real-dumps`，仅t1 `rd-t1-a-v1` / `rd-t1-a-v2` 实际包，现有datasets/census和tool核size/SHA；不改输入，不运行全8输入的额外validate旅程。

显式reason数据文件本地 `/home/dev/gdds-be-ad-05-archive-reasons-v1.json`，SHA `2868249c224a94c583b648d2db842cd018f4917add2af77a565fd73d39aca698`；经LAN放到05证据根同名 `archive-reasons-v1.json`、比SHA，读作纯JSON数据传一个env参数。清单理由如下，均只对可重建测试库接受流程，不宣称已人工证明真实数据来源/生成原因；保留原detected status/事实/异常和逐项resolution审计。工具只对实际出现的subject逐项引用其issue code对应理由；未支持code/identity异常仍失败，不能force或把UNKNOWN改PASS。

```json
{
  "INITIAL_SOURCE_UNEXPLAINED": "联合fresh t1测试库验证来源异常逐项接受流程：保留初始来源无法解释的原诊断，不推定真实生成原因，不改源事实或判PASS。",
  "BASELINE_TIME_UNAVAILABLE": "联合fresh t1测试库验证时间异常逐项接受流程：保留业务基线时间不可用的原诊断，不补造时间或判PASS。",
  "GENERATION_TIME_MISSING": "联合fresh t1测试库验证时间质量逐项接受流程：保留生成时间缺失的原诊断，不补造时间或判PASS。",
  "GENERATION_TIME_INVALID_VALUES": "联合fresh t1测试库验证时间质量逐项接受流程：保留无效生成时间值的原诊断，不改原值或判PASS。",
  "GENERATION_TIME_LAST_NOT_MAX": "联合fresh t1测试库验证时间质量逐项接受流程：保留最后记录时间非最大值的原诊断，不重排或改原值。",
  "TIME_ABNORMAL_INITIAL": "联合fresh t1测试库验证时间顺序逐项接受流程：保留INITIAL时间异常的原诊断，不推定真实发生顺序或判PASS。",
  "TIME_ABNORMAL_MODIFIED": "联合fresh t1测试库验证时间顺序逐项接受流程：保留MODIFIED时间异常的原诊断，不推定真实发生顺序或判PASS。",
  "APPROVED_SIBLING_EXCLUDED": "联合fresh t1测试库验证候选选择逐项接受流程：按本次选中的提交归档并保留已审核兄弟候选被排除的原异常和审计，不改变候选事实。"
}
```

以下argv通过05对应node-run，`AD_ARCHIVE_REASONS_JSON`是上述已比SHA文件的纯数据内容，`AD_RS_IMAGE_05`是本节点新build tag。host明确N1/M24GiB，独立于Compose原worker N1/M24GiB+32GiB limit/8GiB reserve/单active，不试新预算。

```bash
env -u GATEWAY_COMPOSE_GATE_PREBUILT \
  GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON="$AD_ARCHIVE_REASONS_JSON" \
  GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1 \
  GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa \
  GATEWAY_DOCKER_BUILD_NETWORK=none \
  GATEWAY_REPOSITORY_SERVICE_IMAGE="$AD_RS_IMAGE_05" \
  GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee \
  vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync python -m benchmarks.real_dump_journey \
  --tier t1 --scope full --v2-input-completeness FULL \
  --kernel-threads 1 --kernel-memory-budget-bytes 25769803776
```

不传from-step/keep-stack/project-name/cross-project/DC32/debugprobe：fresh UUID project，tool先正常build当前backend/worker一次，再仅在同次进程内复用已构建镜像，退出由原finally清理本project。真实v1 MO、v2 FULL（INITIAL=已归档v1/MODIFIED=v2）、repeat-v1 MO在同次旅程集中覆盖；FULL必须summary/identity确切两pair。Submit/Review/Archive/Preview/History沿原工具完整步序，tar GET完整读取并核所有closure成员原metadata/顺序/size/物理和records逻辑摘要；单列GET开始到读完时间/实际bytes，仅report-only，READY/operation完成锚不变。STDOUT最终JSON和tool产生的外置compose日志均保留SHA，不以时长作W1/W2证据。

### 9.5 停止、清理与最终绑定

任何实际缓存/身份不符或再编排/保全异常立即停报；产品失败按原Owner授权最小修并同一独审，不用操作例外抹掉产品失败。04权威非0停止后续验收；若05已跨节点启动，保留其实际状态和必要本人finally清理，不用成功05抵消04失败。清理只本任务project/派生卷与进程，核8000/Dolt/Compose空，cmp本人marker后释放，保留WT至最终镜像/包绑定完成。source/每run/原exit/SHA及逐包原始manifest均交同一独审核收；协调整理DC33最终范围确认包，未经所需最终范围/手续不办理exit/tag/push/S3。FE3同tar OPFS证据独立pending。


## 10. 联合首轮a999：05实际通过与04失败待收口

两node相同实际source为 `a999869c7f4714c95ee9a5b82866e52cd265e377` / vnext0301。04/05现场BatchMode、目录初次不存在/整机空闲后分别12:26:16Z、12:26:17Z原子取得本人marker；claim原log分别 `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-04-claim-y7TTADuv/claim.log` SHA `f8b93e7c84e643fd88be0d00019c8d6d929eae7d6c63f90440231afc5b6c08fd`、`/home/dev/gdds-test-tmp/artifacts/p6-be-ad-05-claim-KIM5R8lx/claim.log` SHA `8209ed52fc181a0216da3b32f7e9dc251d912a283d1e4fb95c41f7fce55e7a2b`。

两guard分别独立scp并比SHA=§9固定值；source-ready 04 `transfer-IUOsNXCG` 12:26:25Z，prepare.log SHA `bad842fad3f0ac5c12faf803fc42232a235ffb9ef2ae65a9e29460bd033ea25d`；05 `transfer-cwKZNNWF` 12:26:38Z，SHA `f71eb6f26828efb0ad87265ebede6d4976faa79e6de8712db9fe800a4278cd8f`。两者完整expected/advertised/checkout/clean/prepare0已核后即解除main短窗口；后续main文档不改变节点WT。

两node实际prereq、base身份及仓库helper重算dependency input均0，UV/Cargo offline、legacy、unset basetemp和全selector1.97。04/05 backend/RS base的实际config/全部DiffID逐项等06已审来源，Rust/Python和04 client base另存完整身份；依赖/锁未变，无新增预填或代理。d054源链沿本机已有获准LAN预填与06已审来源：CT201来源提交132fc、archive SHA `3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6` 的原构建/预填时间见node readiness，本文不虚构本轮新预填时间。04 `run-repository-build-AqbozR9J` /05 `run-repository-build-pbMa965Y` 均当前a999本机离线build0，各用§9独立RS tag；源码identity仍a687/13cb。

### 10.1 05 fresh t1的实际范围与结果

原run `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-05/run-fresh-t1-8skuj66m/`，**12:35:37–12:40:42Z，command_exit=final_exit=0，前后a999/clean/owner true**；原run.log SHA `66cdeb8c906434bbdfbdf2b63ee438c4537f1a9aab10bedafe5d3a36189e83c1`。fresh UUID project `s2b-realdata-3917667-5652040c`，当前backend/worker实际build/up、无resume/keep-stack，18步完成，原finally正常down-v。05 fresh环境受控强制sync0及expected=installed e6ac核0，脚本/argv/完整原日志和SHA均保留。

实际输入文件为 `packages/rd-t1-a-v1.tar.gz`（107115B，SHA `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2`）、`packages/rd-t1-a-v2.tar.gz`（107066B，SHA `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`）。v1为MODIFIED_ONLY/identity NOT_APPLICABLE，v2为FULL/identity SAME_PROJECT（INITIAL=v1、MODIFIED=v2），repeat-v1仍MO。FULL的确切两pair由F3生产tool硬断言核，表中summary默认view的pair_count=1只指initial_to_modified，不是FULL退回单pair；其两个records closures另有实际计数。

| 完整tar | actual bytes | closure entries / 普通成员 | records closures / logical records | GET开始→读完秒，仅报告 |
| --- | --- | --- | --- | --- |
| v1 Preview MO | 2834432 | 354 / 356 | 1 / 0 | 0.529 |
| v2 Preview FULL | 2660352 | 118 / 120 | 2 / 12 | 0.214 |
| repeat-v1 Preview MO | 2055680 | 105 / 107 | 1 / 0 | 0.163 |
| History | 2153472 | 114 / 116 | 1 / 12 | 0.183 |

这四个是真实完整tar，与§8的size header-only向量明确区分。已审consumer实际逐entry验证原manifest/closure、普通文件顺序/path/size/raw SHA、bounded ref闭合和records owner逻辑摘要；最终JSON仅保留这些汇总/digest/bytes/time，不宣称每成员原字节/每项response另行外置保存。实际Archive consumer按实际subject/sequence逐项消费§9显式reason数据（SHA286824…），保留生产原诊断/事实与resolution审计语义；未知或identity不自动接受。不宣称已外存全套原diagnostic/resolution响应，正常finally清理测试库不是异常丢失。规则负例及关闭重提仍由04对应owner覆盖，05成功不能抵消04失败。

`final-result.json` 是原log中最终JSON整行的**原字节副本**，SHA `505f9731235430c21c53ff39316bec1f0f4e22b7465275bdea12e4a04823cf1d`；同目录 `final-result-source.json` 记原log SHA、offset53374/length40044，不重序列化或改历史。metadata保存run `run-preserve-journey-result-7sFbOrhR`，log SHA `41f7d3383c1e278320bfd7c5d2977c9c6ac9c68fe2954bc095eff31e77c127bf`。

实际runtime镜像全身份 `base-identities-zdhheiw9/base-identities.json` SHA `798515259fbe1fb0a189297e35c10e8f26e6ff76e3680e46f632d99da433cbb2` 保存三config及全54项DiffID（13/28/13）；backend config `sha256:3d47ed71ec272cabc39d71ef6a845f3a4b2d59c979d5f52b483d9dff6d17b21b`，RS `sha256:adde25e06a61e4c35585355490ecea7569220367945c3b4b245e3e73e8d4d053`，worker `sha256:3730d9d2878cc8ddefea51ed368726aa1a7c8af2448c7d3a6d78c0fb0ce18dbe`。`journey-image-bridge.json` SHA `0da27b38f0550ee575d3705ea34e61eaf09d83fab4709cf5de9acca87365c1b3` 核**原tool报告image IDs与保留镜像的同机桥接+fresh build/up**；源码 `compose_image_ids` 本身取tag的image inspect，并非另做container inspect。其原字段虽名running_report/same_node_running_bridge，准确来源以本句为准，不追加虚构running-container观测。

### 10.2 05索引、副本与释放

完整LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-ad-final-05-copy-vj0oULlJ/` 含 `p6-be-ad-final-05/` 与原claim目录。10个完整run及全部原数据文件索引 `evidence-index-3qrxp8ms/index.json` SHA `5f551201c49fabaca2cc1e6a86e2cf72283b78b3602068357931a8b3fbbdf459`；生成时逐run四SHA核相符，排除自身生成run/之后release。释放补充metadata链接 `release-index.json` SHA `f0bb6b07ec725f5243105ecb0bca750e5edf2a3553303b4c1ad43e1c66749a87`，引用旧index/其生成run/release，不覆盖旧index或原log。

`run-cleanup-check-qDu6CB70` 12:43:52Z/0、log SHA `987eaad6058cf1a2289d26e0ab000f9c6b5d110b5956f03951e96fd502f2414d`，本人project容器/卷/网络、全机运行容器、8000与Dolt/Cargo/pytest/rustc/clippy为空。同一独审核原证据/LAN副本后，**12:46:02Z cmp本人marker释放**，`release-8QB9Ypmg/release.log` SHA `f4a1625250c8f88f17db56e1ab4222fbe5d97f8010254d07aff59b78cc661b54`，release0/end clean a999；12:46:56Z再只读核marker不存在/WT clean。保留最终WT、镜像、缓存/原证据，不等待04修复空占05。

### 10.3 04首轮失败与原owner边界

04唯一六包run `run-authority-six-n3pnBrzg` 12:32:24Z开始；Rust180、shared_kernel243、repository_contracts152、repository_client161已通过，backend parallel **3fail/3383pass**，三项均旧message regex `unknown artifact_id` 与D typed unavailable实际文案不符，原异常类型/缺失拒绝/未发布均命中。`2ae2d825ea775e5ef35c449d924a9edcc6aa8b81` 仅两个原test owner三行expected消息修正，产品/consumer/harness无变化；节点仍a999，不在运行中checkout/retag。原runner自身serial另有失败，当前尚待完整trace/整次exit，**不能预判只有三文案或宣称通过**。后继候选与补验等全部原结果固定后由协调/同审收敛，失败整次任何包均不作carried来源，下一合格权威仍六包。05对后继test-only增量是否未影响，由同审核具体diff后决定，不写后继HEAD fresh实跑。

联合范围保持原owner，无新增矩阵：

| 小节/已审来源 | 04原owner与必要容器 |
| --- | --- |
| A1 / c1ee962755，产品d8 | Review HTTP授权/replay、Review事务/CAS精确释放、Workspace lifecycle/occupancy、Archive concurrency；`test_review_compose_e2e.py` self-only与reviewer、Archive双actor |
| V1 / 5dc01deeb5，产品c229 | Rust `configuration_generated_time.rs`、`test_configuration_facts.py`、`test_preview_job_materialize.py`、`test_submit_transactions.py`、原checkpoint/scoped Review owner；既有Submit/Review容器 |
| V2 / 9ec62e82ad，产品f8 | `test_archive_business_validation.py`/queries/audit/transactions/concurrency/http/schema及History/Review摘要原owner；`test_compose_business_rejection_manual_close_and_fresh_upload_archive` 覆盖异常拒绝→关闭→新上传重提→归档 |
| D / 6ad7e54fa0及cd2d395fbc，本地产品0ba | §4 download/HTTP/real_dump/artifact owner、Submit最小容器与History完整tar原容器 |

静态diff边界：S2b V `a687..a999` 的vnext146文件，D基线 `9ec..a999` 31文件，`0ba..a999` vnext无变化；只是范围盘点，非实际package/image carried比较。各原小节06通过不冒充本轮04/05新证据；最终DC33/阶段手续与FE3依赖仍独立待办。


## 11. 04首轮完整失败、F6修复与同源最终门禁

原a999六包run于**12:59:22Z完整结束，command_exit=final_exit=1，end exact a999/clean/owner true**；run.log SHA `d84088eda0bdb8f9995c27ef5dacb5252524ed1343b3d14542d6f053e949ff23`。backend并行3fail/3383pass、serial4fail/56pass；其余五包passed（Rust180、shared243、contracts152、client161、RS1744+207/1skip），不能以其部分通过作任何package carried来源。`run-failed-authority-cleanup-tk1wnYRI` 12:59:57Z/0，log SHA `a1256931a8ea5a51869b3f07592ed259583c0994b460cfad6cc6e52af618260f` 核运行容器/8000/Dolt/pytest/编译均空，runner Hypothesis/cargo target已清；04本人marker保留给同门禁修复，不释放再空占。原run同目录 `original-starting-manifests/*.json` 为六包原stdout JSON字节范围，`starting-manifests-index.json` SHA `af518bd41c7c56940c60bbd14a8d4be3c94ed0db549e928fda636b3a585fca36` 列各包原字节SHA、offset/length、total_digest与来源原logSHA，不重序列化或改失败事实。

两类修复分开：`2ae2d825ea` 只更新两原test owner三行缺失引用旧regex。**F6实际产品缺陷**为 `application/archive/audit.py` 原next只按kind/issue_code/target_submission_id/target_candidate_digest取首项；合法FULL两侧同GENERATION_TIME_MISSING时，第二个真实subject会与第一个digest比较而409。原helper忠实提交preview subject，不能改成force或放宽digest。`eff1dc531b7f011d870bb100912f079cf500c497` 改为原四字段当前候选集合内按command.subject_digest精确选项，保留缺集合/错digest两原409、后续独立latest sequence/CAS、actor-bound replay、精确subject_payload冻结与scope/auth；无Contract/digest/golden/DDL/port变化。原 `test_archive_audit.py` 一个小型SQLite向量覆盖同四字段/同code不同side的两subject：MODIFIED先接受，各seq1/正确持久payload.side；伪digest拒绝；仅MODIFIED撤销到2、INITIAL保持ACCEPTED1且details不改，Start仍阻塞。不是新矩阵或新状态机。

同一独审静核eff1（报告§19）；协调固定actual clean source **`49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0` / vnext `56720104af34a1eb677336f57bdbc07444a56615`**，04原WT/原marker下 `transfer-6zMscy3m` 13:02:42Z source_ready/prepare0/clean；prepare.log SHA `58a4091b59382f04958eaf7a3f1d7cedef88d518467c0c7004a3747501c3d9a7`，named HEAD bundle SHA `a7601befad4ee00dbb4bf9a5f478a9c28a133dc43856ffcd20f98f1dbf9040be`。guard SHA仍b86cb3…，不硬套eff1或后移main docs；解除source短窗口后节点保持49403。

已审六项门禁诊断实际按顺序执行，所有run前后exact49403/clean/owner true：

| 唯一run | 结果 | run.log SHA256 |
| --- | --- | --- |
| `run-extension-input-Go2XNlez` | e6ac expected=installed，0 | `f7ad658cc4069462105eab9ff8ef1cc7332d3470e70008ad696ae0a55682edda` |
| `run-audit-owner-focused-6Wj1fzDF` | 三原owner非serial n4，66passed/0 | `f4a1ccb21e02c8e7de47096a49eb725f277aa372857ecb04072a0e097660be69` |
| `run-audit-owner-serial-HWIvxAoB` | 同三文件serial n0，66deselected，原exit5=N/A | `fff0e3fbfcc3990313d4c84864e35b88bd483bf46a90292ab4e18ae2e801ba06` |
| `run-backend-ruff-fzwTqR0o` | 0 | `5654feb9015ff19f8f19e3407924f383dbfd152c2587b86bb1db3adf3f58cadc` |
| `run-backend-mypy-eiFSjHGw` | 516 files，0 | `4f8e2bf1356cd5f3796720b654bc56d92c45e372438b4748b86c1a286da482af` |
| `run-resolution-compose-cgJnj4OW` | 13:04:28–13:05:21Z，1passed/52.67s，0 | `b9ea0e253ecbcdd0d671d00e2941a54645db1b7806f37783643e599bd4da2f9e` |

三原文件为 `tests/test_archive_audit.py`、`tests/test_artifact_staging_conformance.py`、`tests/test_operation_checkpoint_contracts.py`，受控uv `run --no-sync pytest -q`，两marker分别 `(not serial) or parallel_safe` / `serial and not parallel_safe`。唯一当前容器复现为 `tests/test_submit_compose_e2e.py::test_compose_submit_removes_deleted_user_and_sibling_tables`，受控uv `-q -s -n0 -m 'serial and not parallel_safe'`，d054 preload1/networknone/prebuiltunset；正常build当前backend/worker，RS复用本次自身a999 tag但核未变a687/13cb source identity，不称新RS revision。该FULL→Archive路径实际接受双side同code后继续删除表Submit，新增双subject分支由此及原audit owner证明，不把它写成自然05覆盖。

05既有a999成功步骤的引用待同一独审正式限定：旧成功resolution请求必有原四字段首项digest等command.digest；新实现仅在同集合内按digest查找，仍选该旧首项，其后sequence/冻结payload/事务同路。其余17步产品/consumer/事实代码没有改动。这是对**原a999实跑**的未影响代码推理，不能改称49403 fresh实跑，也不声称05自然数据覆盖F6新增分支。

六项收敛后按原授权，不等待重复开工，**13:06:41Z同49403启动最终六包 `run-authority-six-final-DTWWhQP4`**。完整env沿§9，RS tag仍本次自身a999源未变，TEST_WORKERS48/Cargo4/offline、basetemp unset与prebuilt unset；同一固定WT/source不因main后续纯docs推进而切换。本段记录启动时尚未结束的状态；后续原exit0及RS身份缺口停点见§12。未作最终GO，不重复同runner Compose；05不重启，04最终清理/释放/绑定按后续Owner选择处理。


## 12. 49403六包原0与RS身份原件缺口：当时停止及恢复方案

**实际功能门禁成功事实**：`run-authority-six-final-DTWWhQP4` 13:06:41–13:33:56Z，command_exit=final_exit=0，end exact49403/clean/owner true，原log SHA `35f15eb8ebf67cc387389b575f862a85d1eae341e11635b518abe07fe4ca8c4d`。六包status全部passed：Rust180、shared_kernel243、repository_contracts152、repository_client161、backend3387+60、RS1744+207，另1 skip。唯一skip为 `test_p2_r1_target_cgroup_smoke::test_target_container_has_real_delegated_cgroup`，源码条件＋本次pytest进程环境定位为 `GATEWAY_P2R1_TARGET_CONTAINER` 未设、reason `runs only inside the delegated target container`；原-q log只打印skip计数，未逐条打印该case/reason，不能伪称来自原log或算passed。不补跑/不改flag。

六包起始manifest原字节保存在该run `original-starting-manifests/`；`starting-manifests-index.json` SHA `d473e1239e32739d398fc18f6b356bacc06e246955b37e44c366cadc1619efe2`，每包原byte offset/length/SHA及total_digest齐。保存metadata run `run-preserve-final-manifests-nqS7jeVA`，log SHA `673f19b4ea03afed2410c92453bfb1247bda42b93ea5fd84ce5b931b82b49a5e`。本次原0是合格整次执行的事实；下面身份缺口不能被隐去或口头宣称最终carried。

当前生产provenance原副本 `final-compose-output-q57wh5vw/compose-provenance.json` SHA `fba8467df935a2205c3e314dbf9228ad91c3aa98254c755d101d1ad35b476c4d`，来自本次Submit真实容器快照，project `gateway-submit-s8-446348-test_compose_accept_upload_imp0`。同目录实际production GET OpenAPI SHA仍 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`。两源文件mtime epoch已与本次awareUTC闭区间核相符，原字节复制相等。`run-preserve-final-compose-UZFqaUIx` 打印字段名 `source_mtime_utc` 实际naive fromtimestamp为节点+08本地21:22:07，真实UTC为13:22:07；这是derived标签精度，原epoch检查/原件/SHA正确。原log不改，`original-sources.json`另记原epoch和带UTC偏移说明。

### 12.1 失败collector与不可取得的原件

`run-final-image-identities-I8627T4H` 13:37:37Z，command_exit=final_exit=1/end49403 clean/owner true，log SHA `f6fe1b6dca1b46822eda78b073278b1f2114056f3e931d302ccf5889e125b3d1`，实际literal script/argv在其command.txt，SHA `fd4ad88058808f8b07d2c5135beb448d695a02a84ad2e10ed089f968f7c708d4`。collector把当前tag inspect ID与早段真实container snapshot ID相比，在Docker save/最终bridge写入之前拒绝；没有重建、retag、测试、原文件覆写。当前backend/worker tag ID分别42437a…/4da6b1…，均等原snapshot且旧ID可inspect；差异仅RS。

RS早段runtime ID `sha256:15e3ffb4944b672a5e2e6d9c858a57d6a1142d2d17e0feb4f2e56d469c97655e` 原revision=a999，实际build-input=a687/source13cb/lock6dc。后段同tag变为 `sha256:1306744645e34d7dce8e016564517d8864a26e9624cd915a1a6e8e9b1b0f157c`，Created13:24:11Z/revision49403，后三源字段同原。RS `compose_build_harness.py` 匹配也要求candidate_sha；不符走既有 `ensure_repository_service_image→_run_build`，与后段RS实际Compose/时点吻合。不能据source13cb倒推旧config，也不能把当前tag当旧runtime。AGENTS运行中重tag例外文字仅client，与现存RS harness及自定义tag被摘要为input的接缝需Owner/独审判断，不是设计豁免。

原 `run-repository-build-AqbozR9J` buildlog留有index15e3、manifest `sha256:c5a4f79c5525b7cbaf9db8502545232b1478782eeb54e52ac92660447a165d57`、config `sha256:9e4764cccb55d9a74da73e21ef640c69527fe1233a6f99686dd48d399cb5c577`，没有旧RS全部28项DiffID原件。获准只读追溯核Docker实际containerd socket `/run/containerd/containerd.sock` /namespace `moby`；三个known blob分别仅查询一次，均not found。未切history namespace/扫描导出无关内容，没有create/import/tag/gc/prune/save/build/重造旧cfg。两剩余blob诊断 `old-rs-content-qshp65vj/read-only-diagnosis.json` SHA `f4ba734bdd94414feb90707fcd22552dd50ac6bbeacdfa445d1c7ddd9dac3cbe` 明确完整index链false，`run-inspect-old-rs-blobs-aMmhuHEc` log SHA `910b4ed114a0892fc5247b9de42a90ac0f13fcdbc1b9c467da51a33aa9497d60`；该run0仅表示两个只读查询按要求完成，两对象query exit均1，不是身份通过。

当前停止后继collector/补验/测试/安装/cleanup-release/checkout；04本人marker及WT49403保留，05已释放不动。旧授权不自动恢复此身份异常之后的执行。协调已把事实/两选项落 `p6-be-a-d-joint-validation-preparation.md` §10并通过一次Owner问题提交；回复未到，不把超时当批准。

### 12.2 Owner方案A的固定静态稿（尚未执行）

同角色原独审已静核完整七步及以下外置文件；它们未在节点安装/执行，未在开发机测试/bash-n，不改产品、权威runner、闭包脚本、规则或旧原件，不新建角色/状态机。

| 外置本地文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-be-ad-image-identity-collector-v2.py` | `1232b535371a689f8c55d6fbb8b6c36697e30b6cb1b03060b8ea4450487ecbf1` |
| `/home/dev/gdds-be-ad-04-rs-input-precheck-v1.sh` | `9b304fe33e9d64b1f6e3422a337e5d210471748001791c0ee7bdf345e2971ce2` |
| `/home/dev/gdds-be-ad-04-compare-four-v1.sh` | `d2bb31f6561142e4c335607776b616594e1cbe39175b8591c206646398c7c7ac` |
| `/home/dev/gdds-be-ad-04-resume-authority-v1.sh` | `07ef6da40042512e232d4e72a5c45529178d3ff8de6e23471fa957c9d8fa8507` |
| `/home/dev/gdds-be-ad-04-copy-new-provenance-v1.py` | `2001054e459746b4a03cd497bca770c707cdf7ffe2157458037c7a8a0f645b27` |

方案A固定49403/同04同WT；批准后先核原本人marker/现场/cleanHEAD及五SHA，LAN安装到原artifact root对应新文件名（collector名 `identity-collector-v2.py`），原bash guard不变。每步都用该guard完整49403、唯一run目录/原exit/前后clean+owner；创建唯一 `resume-a-XXXXXXXX` 数据目录。先预核现RS130674的candidate49403/build-inputa687/source13cb/lock6dc并按**该不可变ID**保存原config/全部DiffID。四包rust/shared/contracts/client在同原profile、逐包原Hypothesis绝对路径且不存在的前提下实际manifest compare DTW原0来源；必须解析status，只有“可沿用”才可引用，“运行”并入待执行包，不预判。

随后实际authority子集最小backend+RS，若上述其它包有真实差异按规则纳入；保持原profile：UV/Cargo offline、TMPDIR、Cargo4、pytest48、preload d054/networknone、现自定义RS tag、client base不变，prebuilt/basetemp unset。wrapper打印原runner_exit，运行前后RS输入ID必须保持130674；任何真失败/身份变化均停。RS candidate已一致避免后段同因重建；不恢复旧tag/换default tag凑等价，不重写起始manifest。

新postcopy只使用**该新guard**实际HEAD49403/原0/起止awareUTC、源mtime epoch落新区间、resolve去重后的新schema和current provenance；唯一原bytes副本/SHA，禁止旧q57/旧时间替换。collector只按该阶段原snapshot内immutable image ID inspect/save，保存原config/allDiffID，新唯一phase文件/awareUTC，不拿终态tag替代旧runtime。新路径/UTC由批准后实际guard产生再原审核，不预造未来值。全部原失败/缺口保留；方案A批准后仍不宣称旧RS原件已补回，只用新的合法验证结果闭合当前绑定。方案B则保留pending交接并按Owner授权清理释放04，不再补验；两者都不自动办理DC33/FE3/exit/tag/push/S3。


## 13. Owner批准方案A后的实际最小补验（进行中）

Owner新turn明确“同意继续最小补验”，协调授权记录 `e5157db91c` / 联合准备§11已提交；§12的“尚未执行/回复未到/停止”均为当时历史状态，不再作为重复申请的理由。节点继续固定 **49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0 / vnext56720104af34a1eb677336f57bdbc07444a56615**，不切换后续main纯docs；05不重跑，旧RS15e3原config缺口未补回，也不改写旧原件。

04 BatchMode/原本人marker cmp、现场资源空闲、exact clean/legacy/offline/toolchain1.97及现RS130674 candidate49403在14:11:01–02Z实际复核0，`run-resume-a-readiness-339eHy8k` log SHA `da6b28808cbf8ad5efb1509ad2d27831b7dd5c29af3cce6e04383d89cf2f1b39`。五个新脚本安装前目标路径不存在，经LAN逐个安装并核§12五SHA全符，`run-resume-a-script-sha-3TI1p51M` 14:11:25Z/0，log SHA `b9b7e8d50972426552d8d114365ac50bbe87f0af8b8626cb0fb32a0c2ba7eaeb`。原bashFILE guard SHA b86cb3…不变；每步仍唯一run/原exit/前后exact clean与owner。

唯一恢复数据目录为 `/home/dev/gdds-test-tmp/artifacts/p6-be-ad-final-04/resume-a-5OBTboKj`。RS预核 `run-rs-input-before-ENkhPtm0` 14:11:38–39Z/0，log SHA `4ee45ca1e049150ba488754f15716afd9bb51a20e2945b2bcdd111bb60929833`。`run-rs-input-config-2NAkmSb8` 14:11:39–45Z/0按已记录不可变ID130674 inspect/save原件，log SHA `6c83d9494ffbcd6adc2c07e8919edcd53552528b3a928365797809c3158390f4`。预采目录 `resume-a-5OBTboKj/image-identities-rs-before-resume-hjh4fkki` 的 `image-identities.json` SHA `9d2b02a2b6672f5ff9d4a10d4406faf609a4d39facddc86edf92726cfa07821f`，原config digest `sha256:13776cfb1d842f66ffb46b6d382ab9bdd57a5e4a85a82251a7bda25622ab9432` 与全部28项DiffID及原inspect/save-manifest/config字节齐；这是当前130674原件，不能冒称旧15e3原件。

`run-four-package-compare-5zuLDhdL` 14:12:32–36Z/0，log SHA `0401fdd84a9cc6e50ec2eea34f3c876200e03eae397b9357c894a391881eece2`。rust/shared_kernel/repository_contracts/repository_client在原04同WT/原完整profile、原逐包Hypothesis绝对路径且不存在的条件下实际compare §12 DTW原0起始manifest，四项status均“可沿用”且changed_components为空；原bytes/current manifests和比较JSON保存在恢复目录 `four-package-closure/`。解析后的 `resume-scope.json` SHA `f2027b0e71b56cb0ea3bfb5126356d0e8fa9c353f118d993692aab35f50b6798` 确定实际需运行 **backend,repository_service**，未预判或人工排除其它差异包；四包直接引用原49403 DTW实际通过来源，不链式引用比较结果。

**14:14:04Z实际启动** `run-authority-resume-mvzi5dNV`，完整路径位于上述04 artifact root。外层完整六包profile保持原环境，已审wrapper根据实际比较结果把runner包集设为backend,repository_service，原log明确打印 `actual_runner_packages=backend,repository_service`。pytest48/Cargo4、UV/Cargo offline、d054 preload1/networknone、原custom RS tag、client base、prebuilt/basetemp unset不变；RS输入现为130674/candidate49403，无手工retag或重建旧镜像。runner按原规则强制重装Rust扩展，e6ac expected输入实际核对。当前backend并行3387passed/0（199.36s），原serial仍运行；**整次尚无退出结果，不宣称当前补验通过**。后续只在整次原0、end exact clean/owner与RS输入不变成立后，按该新guard实际区间复制新production OpenAPI/provenance，再以该阶段snapshot的immutable ID采三runtime原config/全部DiffID，保持新唯一目录与awareUTC。实际结果及清理释放将追加，不复用旧q57/旧时间或05证据冒充当前镜像。
