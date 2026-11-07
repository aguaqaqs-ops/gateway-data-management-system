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

自有确定性 POSIX ustar/PAX encoder：512-byte header，uid/gid/mtime=0，mode=0644，uname/gname 为空，普通文件 type=0；UTF-8 非 ASCII 或超出 ustar name/prefix 的路径使用一个局部 `path` PAX 扩展（type=x，固定非业务 header 名）。PAX length 按整条 UTF-8 bytes 固定点，字面向量 `12 path=中\n`。总长度与发送共用每 member 的 header/PAX plan，包含 padding 与两个 512-byte 零结束块，不增加 10 KiB record padding。固定小向量独立断言实际长度，Python tar reader 作为互通 consumer。

## 4. 精确文件与唯一测试 owner

产品：`vnext/backend/src/gateway_backend/artifacts/{store.py,bundle_download.py,tar_stream.py}`；`infrastructure/artifact_store/{local_store.py,bounded_store.py}`；`capabilities/bundle_assembly/{transport.py,_assembly.py,__init__.py}`（共享现有 identity helper，不改输出）；`bootstrap/composition.py`；`http/dependencies.py`；`http/orchestration/{bundle_stream.py,history_compare.py}`；`http/routes/{preview_results.py,history.py}`；`http/bundle_response.py`；`benchmarks/real_dump_journey.py`。

| 不变量 | 唯一测试 owner / 拟改文件 |
| --- | --- |
| tar header/length/PAX UTF-8 固定点、ASCII/中文/非BMP、相邻记录/位数边界/畸形 consumer 向量、每 closure entry 一个普通成员 | `tests/test_bundle_download.py`（新） |
| metadata/ref/path/digest 预检，流中失败/未开始关闭/断连/cleanup 协作、64 KiB/2FD 代表性计数 | 同上；复用轻量真实 Local/Bounded store，不建 Dolt |
| 两公开路由授权先行/状态/缺失/typed503、头与关闭接线 | 参数化 `tests/test_bundle_download_http.py`（新）；旧 `tests/test_preview_read_http.py`、`tests/test_history_http.py` 仅更新 fake port/格式断言 |
| Preview MODIFIED_ONLY/FULL/replacement 与 History 两/三节点真实 job wiring、共享/异schema/空表/closure摘要 | 新 owner 复用 `tests/support/http_workspace_harness.py`、既有 preview/history job harness；既有 job/assembly owner不复制矩阵 |
| OpenAPI 唯一媒体及 headers/错误声明 | `tests/test_http_openapi.py` |
| 实际 FULL multipart 输入、双 pair default consumer、tar 全成员/各物理与逻辑摘要、GET完整时间/bytes只报告 | `tests/test_real_dump_journey.py` |
| 当前容器实际下载 smoke 与 provenance | `tests/test_history_compose_e2e.py`（既有旅程加完整 tar 断言；候选收敛后一次） |

Owning 正文只改 `docs/backend-vnext/contracts/comparison-bundle.md`（完整 tar/顺序/头/错误/生命周期/上界），必要真实 port 条款写入该 owning Contract。没有新的业务 golden；原业务 manifest/digest/golden 应原字节保留。共享前端向量由生产 encoder 在06 clean候选生成到 WT 外：同一 tar 包含 ASCII长路径、中文、非BMP，并交原 metadata、各文件/整包 length/SHA、命令/候选/节点；不是新协议 golden。不得改 frontend 或前端文档。

## 5. 实施与验证次序

1. 本清单先提交并直交同一独审预检；依次实现公开 bounded artifact 读取、owning metadata decoder、encoder/prepare/response、两路由与 tests/Contract，固定首产品候选早交独审。
2. 同一后续候选完成 main 真实工具：v1 MODIFIED_ONLY；v2 FULL，INITIAL=v1/MODIFIED=v2；默认业务摘要和 identity 明确取 `initial_to_modified`，另核 `baseline_to_initial`，完整 tar consumer 覆盖两 pair 所有成员；保留 V2 显式归档 reason 环境输入，不 force。
3. 06 BatchMode 连通/现场核空闲后原子本人 marker；LAN bundle 传源码到独立 clean 已提交 WT，legacy 链接、离线缓存/toolchain/dependency-base；`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp`、Cargo/pytest workers4。即使 Rust 无改仍强制重装扩展并核 build input；五 Python 包 ruff/mypy；focused 非serial -n4、serial -n0，空批 exit5 为 N/A。失败原日志/SHA保留，产品失败先停诊断。收敛后一次必要当前小型 Compose 和 OpenAPI/同字节制品。
4. D 独审与06局部证据完成后，同两角色继续已授权联合准备/集中核收：先与协调者固定最终命令/候选，04实际受影响六包权威及其中必要Compose，05一次fresh t1上述两模式完整旅程；不重复同runner Compose，不触冻结基准/CT108。联合退出前 DC33 最终范围仍交 Owner 确认，不自行exit/tag/push，不称 FE3 完成。

当前 container gate：D 未有产品改动；最后实际产品/镜像 revision `f8fb796f020ab47725359c176fc0e53bfb68aae6`，vnext tree `3860ed86194e4eafea9cfd408e7e7b5096b24bbb`。D 完整候选因 HTTP container harness 与最终传输行为变更须重建/运行；暂记 deferred 到06候选收敛及04联合最终候选，不能沿用旧V2结果宣称当前D通过。
