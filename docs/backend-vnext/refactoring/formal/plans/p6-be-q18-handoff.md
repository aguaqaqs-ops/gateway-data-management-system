# BE-Q18：归档候选读取审核版本

状态：2026-11-08 固定实施候选；待独立审核与专用节点验证。本文不代表 S3 容量阻塞解除或 FE3c 前置已验收。

## 范围与决定

FE3c 的关闭请求必须携带 `expected_review_version`，而仅有 `archive_submission` 的归档确认人不能读取 Review GET。归档候选查询本来就在同一个只读 control DB 事务中逐候选读取权威 ReviewProjection，用来校验状态并生成 digest。此次直接从该 projection 的 `optimistic_version` 生成逐候选只读 `review_version`；没有增加 SQL 查询、事务或授权路径。

`GET /v1/archive-candidates` 的 `candidates[]` 每项现在含 `submission_id`、`expected_candidate_digest`、必填 `review_version`（非负 I-JSON 安全整数）。仅当前 scope 的 `archive_submission` 身份可读取，原有界候选和完整性门禁照旧。`ArchiveCandidateRef`、candidate/candidate-set digest、选择与关闭 fingerprint、关闭 CAS、Review GET ACL 和归档语义不变。关闭请求继续使用当前候选 `review_version` 作 CAS；过期返回 `409 REVIEW_VERSION_CONFLICT`。选择请求继续只含原两个引用字段，不能把只读版本原样转入 `selected`。

## 实施与验证所有权

- 产品：`application/archive/snapshot.py` 保存由现有 projection 派生的候选读取行；`queries.py` 只让候选 GET 返回这些行；`http/schemas/archive.py` 将版本映射为响应 DTO。没有改 SQLite schema、Review GET 或写入路径。
- Contract：`contracts/business-lifecycle-and-state.md` 固定字段、scope、CAS 来源与排除项。运行时 OpenAPI 由 DTO 生成；`test_http_openapi.py` 固定字段必填、整数范围与选择请求的两字段边界。本 BE 小项不修改前端快照和生成类型；FE3c 在其既定快照刷新流程中接收固定后端 OpenAPI。
- 轻量 HTTP/查询测试：`test_archive_queries.py` 和 `test_archive_http.py` 覆盖版本、digest 不变、仅归档权限读候选及关闭、Review GET 403、旧版本 409、跨 scope 404、原 key 回放首次结果。这些用现有 SQLite fixture，无真实 Dolt fixture。
- 容器旅程：在已有 `test_archive_compose_e2e.py` 的关闭路径加入同 scope 仅归档权限身份，读取版本、Review GET 403、旧版本 409、关闭 201、原 key 回放 200；关闭 body 去掉写死的 `1`。候选响应新增字段后，测试中的选择引用 helper 仍只传两个合法字段。

## 独审与节点执行提案

独审核对候选读取事务、scope/ACL、版本与 digest 分离、HTTP DTO/OpenAPI、选择引用严格性及容器身份。独审之后由 root 指定的唯一测试执行者在专用节点 clean、已提交 worktree 验证；此实施会话不执行节点测试、编译、lint 或容器门禁。

建议先运行 backend 定向测试及 `ruff`/`mypy`；节点由 root 按本轮最新有效的统一资源池规则指定。按测试约定设置 `UV_OFFLINE=1`、root SSH 的磁盘 `TMPDIR`，使用 `vnext/scripts/uv-consume.sh`。定向目标：

```text
tests/test_archive_queries.py::test_archive_candidates_include_only_approved_current_base_submissions
tests/test_archive_http.py::test_list_archive_candidates_returns_approved_submission
tests/test_archive_http.py::test_archive_only_actor_reads_candidate_version_and_closes_with_cas
tests/test_http_openapi.py::test_openapi_archive_candidate_exposes_required_review_version
```

本轮改了实际 Compose e2e，按容器边界规则需在 root 指定的节点对固定 HEAD 重建并验证容器门禁；目标旅程为 `tests/test_archive_compose_e2e.py::test_compose_business_rejection_manual_close_and_fresh_upload_archive`。执行者按最新有效的 AGENTS 与 testing-conventions 处理节点空闲标志、离线缓存、预置 backend dependency-base、构建网络、日志/镜像身份和收尾。若合入阶段或最终门禁需要更大范围，按对应阶段规则另行决定。本候选未运行上述验证，尚无通过结论。
