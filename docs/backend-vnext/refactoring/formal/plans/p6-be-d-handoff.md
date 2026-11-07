# D BE-d 完整 tar 实施交接

2026-11-07；实施 `/root/be_d_impl`（GPT-6.1-Sol / xhigh），独审 `/root/be_d_review`（GPT-6.1-Sol / max）。产品基线 `9ec62e82ad9b70776a03954c30edb94a29e1380a`；实际开始 main `dfc8659744`，初始 status/diff 为空。本文先固定实现接缝供预检，尚无 D 产品或测试 GO。协调者维护工作单、kickoff、联合准备与总交接，本角色只改本文及下列 D 文件。

## 1. 公开 port、准备结果与顺序

`BundleReaderPort.prepare_bundle(artifact_id: str) -> PreparedBundleDownload` 取代旧 `read_bundle -> tuple`，不保留旧格式。准备对象包含 `bundle_digest: str`、`content_length: int`、`filename: str`（`bundle-<digest hex>.tar`）、`etag: str`（含 HTTP 双引号）、`stream: Iterator[bytes]` 和幂等 `close() -> None`。`prepare_bundle` 是同步实际执行的函数：授权/exact scope/readiness/TTL 在 orchestration 先完成，随后取得共享读取借用，读取并验证 metadata，再逐项完整读回所有成员，最后才返回对象；route 创建 `StreamingResponse` 时预检已经结束。

目前 manifest 没有 closure 的物理 ref。owning bundle helper 从已发布 manifest 的既有 semantic fields / closure entries 按原 JCS 和既有 content-identity 公式求出 expected closure ref，再读取并核对该**原已发布文件**；不把重建字节当作下载文件，不新增持久字段或改业务摘要。manifest / closure 的 canonical bytes、版本、bundle/semantic closure digest、entry size/raw digest 与 ref、pair surface ref 及所有嵌套 ArtifactRef 的闭合在 owner 内校验。下载严格按最终 closure 顺序发每 entry，重复内容/同源不同路径不再去重。

Artifact 最小公开扩展为 `ArtifactStreamingStorePort.get_ref/read_exact/read_session`。Local store 的 `read_exact` 安全打开普通文件、逐块校验 size/SHA，`read_session` 借用 root 目录的共享 `flock`；bounded cleanup 对同一目录取排他非阻塞锁后重查 eligibility，冲突返回 retryable。锁只使用现有 root 目录 FD，无新文件、DB 行、下载状态机或 mmap；信任边界仍为 ADR0012 协作进程。

## 2. 错误映射

| 实际边界 | Preview | History |
| --- | --- | --- |
| 未认证 / 当前权限或 scope 不符 | 原 401/403/隐藏目标 404；读取前拒绝 | 原 401/403/隐藏目标 404；读取前拒绝 |
| Preview 未就绪/过期、History 非 SUCCEEDED 或缺有效 assemble checkpoint | 沿 `read_preview_result` 原分类 | 沿原 `RESOURCE_NOT_FOUND` / `ARTIFACT_UNAVAILABLE` 404 |
| 已授权 metadata 或任一成员不存在、不可读（ENOENT/EACCES/EPERM） | 404 `RESOURCE_NOT_FOUND` | 404 `ARTIFACT_UNAVAILABLE` |
| metadata malformed/非 canonical/版本或交叉 digest 矛盾、ref 不符、大小/SHA 错、缺失引用、非法/重复/保留 path、symlink/非普通文件 | 窄 typed `BundleIntegrityError` → 503 `BUNDLE_INTEGRITY_FAILURE` | 同左 |
| 其他准备期文件 I/O 故障 | typed integrity/unavailable 边界内脱敏 503 | 同左 |
| 响应头后 I/O 故障 | 传播并中断流，不补 padding/end blocks | 同左 |

`ArtifactUnavailableError` 是存储层窄缺失/不可读类型；不再把所有 `ManifestVerificationError` 转成 404。响应不暴露私有路径或业务行。OpenAPI 200 只声明 `application/x-tar`，明确 Content-Length / ETag / Content-Disposition，新增 typed 503；无旧 JSON/octet-stream 双格式。

## 3. 生命周期、资源与编码

准备失败立即关闭借用；成功返回由 route 的 response wrapper 在 ASGI 调用 `finally` 关闭，覆盖正常结束、发送异常、客户端断连和取消；iterator 自身也 `finally` 关闭，`close` 幂等，未开始迭代的对象仍可关闭。生成器不持有全包 FD，不依赖普通 BackgroundTask 才能释放。协作 cleanup 在读取期间不删除本 root 产物；完成后可重试。

逐成员 prepare 与 send 均使用 64 KiB chunk；root 目录锁一个 FD、当前 artifact 一个 FD，同时最多两个活动句柄，mmap=0。metadata 原 manifest ≤16 MiB、closure ≤16 MiB，保留其原字节用于发送；其解析结构和 entry 索引为 O(metadata bytes) 有界内存，单文件工作 chunk 64 KiB，不能将整包 materialize。PAX body 只为一条路径构造，路径由受限 metadata 上界约束；发送按 ≤1 MiB 切片，handoff 后补实际代表性 chunk/FD 计数。

自有确定性 POSIX ustar/PAX encoder：512-byte header，uid/gid/mtime=0，mode=0644，uname/gname 为空，普通文件 type=0；UTF-8 非 ASCII 或超出 ustar name 的路径使用局部 `path` PAX 扩展（type=x，固定非业务 header 名）。size 超11位octal使用标准 PAX decimal `size`（普通头size=0），保留ArtifactRef完整I-JSON范围；仅header/length小向量，不建大文件。PAX length 按整条 UTF-8 bytes 固定点，字面向量 `12 path=中\n`。路径逐16Ki code points编码，每块≤64KiB，不构造整条路径/PAX bytes。总长度与发送共用每 member 的 header/PAX plan，包含 padding 与两个 512-byte 零结束块，不增加 10 KiB record padding。固定小向量独立断言实际长度，Python tar reader 作为互通 consumer。

## 4. 精确文件与唯一测试 owner

产品：`vnext/backend/src/gateway_backend/artifacts/{store.py,bundle_download.py,tar_stream.py}`；`infrastructure/artifact_store/{local_store.py,bounded_store.py}`；`capabilities/bundle_assembly/{transport.py,_assembly.py,__init__.py}`（共享现有 identity helper，不改输出）；`bootstrap/composition.py`；`http/dependencies.py`；`http/orchestration/{bundle_stream.py,history_compare.py}`；`http/routes/{preview_results.py,history.py}`；`http/bundle_response.py`；`benchmarks/real_dump_journey.py`。

实际增量：`application/preview_jobs.py`、`application/history/compare_jobs.py` 把既有 `bundle_result.referenced_artifacts` 加入原 `required_refs`，使final rewritten/原closure在首次下载前即随现有publication事务受保护，保留全部原恢复refs、owner释放/TTL，不改业务digest/golden；此producer缺口已单独报告并经协调/设计者按既有Contract确认。`benchmarks/bundle_tar.py` 集中完整tar consumer；`tests/support/compose_gate_harness.py` 的既有JSON下载消费同步改用该consumer。`_assembly.py`/`__init__.py`最终无须修改，transport helper在相同owning package内直接共享既有identity/parser。

| 不变量 | 唯一测试 owner / 拟改文件 |
| --- | --- |
| tar header/length/PAX UTF-8 固定点、ASCII/中文/非BMP、相邻记录/位数边界/畸形 consumer 向量、每 closure entry 一个普通成员 | `tests/test_bundle_download.py`（新） |
| metadata/ref/path/digest 预检，流中失败/未开始关闭/断连/cleanup 协作、64 KiB/2FD 代表性计数 | 同上；复用轻量真实 Local/Bounded store，不建 Dolt |
| 两公开路由授权先行/状态/缺失/typed503、头与关闭接线 | 参数化 `tests/test_bundle_download_http.py`（新）；旧 `tests/test_preview_read_http.py`、`tests/test_history_http.py` 仅更新 fake port/格式断言 |
| Preview MODIFIED_ONLY/FULL/replacement 与 History 两/三节点真实 job wiring、共享/异schema/空表/closure摘要 | `tests/test_bundle_download_http.py`；复用 `tests/support/http_workspace_harness.py`、既有 preview/history job harness；既有 job/assembly owner不复制矩阵 |
| OpenAPI 唯一媒体及 headers/错误声明 | `tests/test_http_openapi.py` |
| 实际 FULL multipart 输入、双 pair default consumer、tar 全成员/各物理与逻辑摘要、GET完整时间/bytes只报告 | `tests/test_real_dump_journey.py` |
| 当前容器实际下载 smoke 与 provenance | `tests/test_history_compose_e2e.py`（既有旅程加完整 tar 断言；候选收敛后一次） |

Owning 正文只改 `docs/backend-vnext/contracts/comparison-bundle.md`（完整 tar/顺序/头/错误/生命周期/上界），必要真实 port 条款写入该 owning Contract。没有新的业务 golden；原业务 manifest/digest/golden 应原字节保留。共享前端向量由生产 encoder 在06 clean候选生成到 WT 外：同一 tar 包含 ASCII长路径、中文、非BMP，并交原 metadata、各文件/整包 length/SHA、命令/候选/节点；不是新协议 golden。不得改 frontend 或前端文档。

## 5. 实施与验证次序

1. 本清单先提交并直交同一独审预检；依次实现公开 bounded artifact 读取、owning metadata decoder、encoder/prepare/response、两路由与 tests/Contract，固定首产品候选早交独审。
2. 同一后续候选完成 main 真实工具：v1 MODIFIED_ONLY；v2 FULL，INITIAL=v1/MODIFIED=v2；默认业务摘要和 identity 明确取 `initial_to_modified`，另核 `baseline_to_initial`，完整 tar consumer 覆盖两 pair 所有成员；保留 V2 显式归档 reason 环境输入，不 force。

实际功能入口为 `--tier t1 --scope full --v2-input-completeness FULL`，**完整执行命令待最终清单对齐，不执行先前草稿的小fixture N4/M24MiB例子**。host kernel CLI与Compose worker独立：保留已审worker N1、32GiB envelope / 8GiB reserve / 显式M24GiB=25769803776B、单active；host scope亦N1，独立budget参考原旅程51539607552B，在联合清单核实后填写。pytest/Cargo jobs4只是测试并行度。`--scope full`仍仅表示步骤范围，新增flag才决定v2真实FULL multipart。v1/repeat-v1仍MODIFIED_ONLY；v2 INITIAL与已归档v1同字节，MODIFIED=v2。summary与identity均按请求mode强制确切pair集合（FULL两pair、MOD_ONLY一pair），两个pair均查无降级/失败且baseline_to_initial不变；default summary/identity只取initial_to_modified；所有pair/member均由tar consumer核原metadata、精确顺序、size/raw SHA、引用metadata和records owner逻辑content digest。GET完整读时间/bytes独立只报告，原completion/user-visible在GET前冻结。

前端额外已知接缝：现consumer只读取PAX path且有1MiB PAX body限制；标准size记录、octal边界及I-JSON max仅交header/length小向量，不能冒称大文件互通。主共享tar仍是可完整安装的小制品，后端不新增路径/产物大小上限，FE资源上界由其owner核对；FE修复/同字节证据仍待。
3. 06 BatchMode 连通/现场核空闲后原子本人 marker；LAN bundle 传源码到独立 clean 已提交 WT，legacy 链接、离线缓存/toolchain/dependency-base；`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp`、Cargo/pytest workers4。即使 Rust 无改仍强制重装扩展并核 build input；五 Python 包 ruff/mypy；focused 非serial -n4、serial -n0，空批 exit5 为 N/A。失败原日志/SHA保留，产品失败先停诊断。收敛后一次必要当前小型 Compose 和 OpenAPI/同字节制品。
4. D 独审与06局部证据完成后，同两角色继续已授权联合准备/集中核收：先与协调者固定最终命令/候选，04实际受影响六包权威及其中必要Compose，05一次fresh t1上述两模式完整旅程；不重复同runner Compose，不触冻结基准/CT108。联合退出前 DC33 最终范围仍交 Owner 确认，不自行exit/tag/push，不称 FE3 完成。

当前 container gate：D产品已固定至本节提交链，尚未执行D镜像/Compose。最后实际产品/镜像 revision `f8fb796f020ab47725359c176fc0e53bfb68aae6`，vnext tree `3860ed86194e4eafea9cfd408e7e7b5096b24bbb`。D 完整候选因 HTTP container harness 与最终传输行为变更须重建/运行；暂记 deferred 到恢复授权后的06候选收敛及04联合最终候选，不能沿用旧V2结果宣称当前D通过。

## 6. 实际候选、已有证据与验证暂停事件

产品首候选 `36edb20086`；`1c14572725` 清理旧imports/fixture名；`e3b54b8f71` 修F1（generic业务JSON不得误套16MiB metadata上限）；`7f25a1657a` 修实际HTTP受理fixture；`d0a22ba91d` 完整工具/F2保护接线；`aaa0f4a6f3` 测试typing；`8de2a9a060` F3按请求mode强制确切pair集合；`a7954b6b55` 改为首次GET前核manifest/closure/全部final保护；`445a19dfe3` 同步store缺失错误文案。独审GO尚未形成；当前产品待最终复核。

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

协调者接报后明确暂停全部受影响节点focused/static/Compose/04/05，未经Owner回复不恢复。现仅做证据保全、资源清点/本人释放和可审查guard修正，其他无关产品/工具代码可继续；没有任何D Compose或联合权威/真实旅程通过声明。

保全目录：06 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/incident-preservation-rvpm66sO/`，保存事件时现存log/script/bundle、actual HEAD/status、进程、容器及8000快照，`SHA256SUMS` SHA `78122ba8b893b200c17ad9ae959af5fa7d25cc830f59986043f2b40298ca065b`；LAN副本 `/home/dev/gdds-reviews/artifacts/p6-be-d/incident-preservation-rvpm66sO/`。保全时WT为clean `aaa0f4a6f32143448c1b55bb1cc8f509643e1d3c`。11:19:30Z确认无本任务服务/运行容器/8000/Dolt/Cargo/pytest，仅释放本人marker；释放log `node-release-UzrHOQAs.log` SHA `de06e368c6459639f0f04525cdb6a9763edaa30e85eb3e8ff6a21b97422b8ae8`，副本同上。旧WT、卷、镜像及证据未清理。

可审查guard（仅写文件，尚未执行/测试）：本地 `/home/dev/gdds-be-d-guarded-transfer.sh`（副本`/home/dev/gdds-reviews/artifacts/p6-be-d/guarded-transfer.sh`），SHA `f83066c0b15a012bf5df673577591910e5b0afd4926553d4f3592ef5edff9d4d`；node-run `/home/dev/gdds-be-d-guarded-node-run.sh`（副本同目录`guarded-node-run.sh`），SHA `4eb10c9fc1a8b3b12d4b5ae4cba4d54528d7462d7a5a8f91549facb0e7c979b2`。两者`set -euo pipefail`，transfer以named HEAD建bundle并verify/核advertised完整SHA及SHA256，任何失败不继续；节点checkout显式完整SHA并核clean/exact HEAD；run每次`mktemp`独立WT外目录，保存精确命令/guard，运行前后核完整HEAD/clean及本人marker；end marker不同或丢失记录`end_owner_marker_matches=false`，保留`command_exit`原值并使`final_exit=2`。无需新evidence状态机；同一独审静态核后由协调者提交具体恢复方案给Owner，Owner回复前不执行。

两guard当前mode664，实际入口均为`bash <file>`；transfer只传source bundle，不安装/执行node-run。Owner恢复后，协调固定clean实际完整SHA（届时含审核/批准文档，核其vnext tree与已审产品相同），赋给`D_EXPECTED_SHA`，再用`bash /home/dev/gdds-be-d-guarded-transfer.sh "$D_EXPECTED_SHA"`传源码。node-run单独经LAN `scp /home/dev/gdds-be-d-guarded-node-run.sh ct107-gw-dms-06:/home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh`，核SHA后以`ssh -o BatchMode=yes ct107-gw-dms-06 "bash /home/dev/gdds-test-tmp/artifacts/p6-be-d/guarded-node-run-v1.sh '$D_EXPECTED_SHA' <label> <command-and-properly-quoted-arguments>"`调用，不能`bash -s`令`$0=bash`而使guard自复制错误。具体待恢复命令由协调清单列明，不以这个占位示例启动。释放原log的精确本地副本是 `/home/dev/gdds-reviews/artifacts/p6-be-d/node-release-UzrHOQAs.log`，06原路径是 `/home/dev/gdds-test-tmp/artifacts/p6-be-d/node-release-UzrHOQAs.log`，它在incident-preservation子目录外。

Owner恢复后的固定调用形态（目前禁止执行）：

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

联合05 fresh t1 host budget经协调从原S2b E fresh t1 `command.json`核实为N1/M25769803776B，后续沿该已过host值；Compose worker独立保持N1/M25769803776B、32GiB envelope/8GiB reserve、单active。此前§5的host48GiB参考现以此实际t1来源修正，不试预算。
