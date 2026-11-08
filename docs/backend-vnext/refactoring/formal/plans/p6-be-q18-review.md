# BE-Q18 独立审核：归档候选读取审核版本

状态：2026-11-08，固定产品候选 `a1ca3bad93a25cb47384a81fbc985075b1299c39` 的静态初审 **CLEAR，证据待核**。此结论不是测试通过、容器门禁通过或 BE-Q18 交付 GO；S3 原产品 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e2` 仍为 `BLOCKED_CAPACITY`，与本接口补缺分别判定。

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

**当前没有产品阻塞 finding。** `ArchiveCandidateRead` 与原引用分列增加少量内存，但候选已有 200 上限；符合本轮只读 DTO 目标。静态结论以候选提交为准，后续产品修订需增量复审。

## 3. 尚缺证据与验收要求

1. 依 DC91 在统一五节点池选择当次空闲且工具链、缓存、输入合格的节点，于 clean、已提交固定 worktree 按本节点占用、离线缓存、`UV_OFFLINE=1`、磁盘 `TMPDIR` 和 `uv-consume.sh` 规则运行 backend 定向测试：`test_archive_queries.py::test_archive_candidates_include_only_approved_current_base_submissions`、`test_archive_http.py::test_list_archive_candidates_returns_approved_submission`、`test_archive_http.py::test_archive_only_actor_reads_candidate_version_and_closes_with_cas`、`test_http_openapi.py::test_openapi_archive_candidate_exposes_required_review_version`。池内选点不需旧用途例外；若失败，保留原始 exit/log/SHA，停止后续验收并按现行规则处理。
2. 提交前五个 Python 包均需 `ruff check .` 与 `mypy` 通过；本次未改 Rust 源，不触发独立 rustfmt/clippy 门禁。backend focused 的已安装扩展仍须按 DC48 与当前 Rust tree 核对，执行稿选择强制重装。节点执行者应核对候选 HEAD、clean、五锁未漂、日志起止 HEAD/时间/hostname/入口 exit 与 SHA256。
3. 本增量修改了实际 `test_archive_compose_e2e.py`，触发 AGENTS 的容器门禁重建条款。须在许可节点以当前固定 HEAD、本机 Compose build、已预置且身份核对的 backend dependency-base、`GATEWAY_DOCKER_BUILD_NETWORK=none`，实际重建并运行 `test_compose_business_rejection_manual_close_and_fresh_upload_archive`，核对 backend/worker 运行镜像与构建结果、OpenAPI、日志、provenance 和清理。不能把旧提交的容器结果表述为本 HEAD 已验证。
4. 若后续以此候选参加阶段退出、S3 ready 或最终门禁，另按相应阶段闭包、六包和镜像身份规则判定；本次定向验证本身不代替那些门禁。FE3c 在固定后端 OpenAPI 与独审/节点结果交付后再刷新类型、mock 与 §16.6，并按其既定真实 backend e2e 验收。

待同一审核者独立核对固定执行稿、节点原始证据及失败处置后，更新本报告结论；当前不得标记 BE-Q18 GO。

## 4. 固定 focused 执行稿静审

2026-11-08 收到实施者工作树外的 `run-focused-06.sh`，原件 SHA256=`0f93d34358f7dadb38da22452ab1dd25bcb2d160f283a7e5969fb80fb91976cd`；配套 `execution-proposal.md` SHA256=`7b3fe4132249edf8747ecc690e9a9153be420f995a6a235ddf3776278c980c62`。本人只读重算摘要并审精确脚本，未执行、未转发、未取得节点占用。

**脚本静审 CLEAR，可作为 06 focused 执行稿；不是执行许可之外的 PASS 证据。** 它固定 `a1ca3bad93` 和 Rust tree `9d4f84ce`，检查本节点空闲后原子获取 marker，创建 clean detached worktree/`legacy` 链接，校验四项 Rust 工具链及离线环境，强制重装扩展并核安装的 build input；五包 Ruff/mypy 后以 backend 两遍 marker 规则运行六个 archive 查询、HTTP、OpenAPI、事务、审计、并发测试文件。所有测试缓存、Cargo target 和日志都在 worktree 外；失败即停，记录步骤 exit、起止 HEAD、lock SHA、guarded marker 释放与日志 SHA。六文件均标 unit，两个显式 serial 用例进入 `-n 0` 一遍。范围比上述四个最小定向用例广，但仍为受影响 archive focused 范围，并未偷跑全量 runner。

执行者须先按提案进行 SSH BatchMode、获准 LAN 源码/缓存与脚本 SHA 核对；本脚本不负责传输和连接检查。06 是本稿选择的一个 DC91 合格节点，不是旧固定用途要求。若改脚本、节点或候选，先固定新字节并按实际变化复审。容器提案只描述后续最终 HEAD 的构建与单项 Compose 旅程，目前没有固定容器执行脚本，也没有镜像/缓存/测试原件可核收。
