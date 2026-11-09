# BE-Q18：归档候选读取审核版本 — 最终交接

2026-11-08；固定产品 **`94b25a32792821cbc5b3230d98a0aa6f13493c32`** 经原审核者核收 **BE-Q18 GO**。
独立报告提交 **`27eab454b7f645ca4d0f347b218de8eaec31eb37`**，见 [Q18 review §13](p6-be-q18-review.md#13-94b25a-四例容器原始证据与结论)。
本结论仅覆盖本接口补缺及四条受影响容器旅程，不代表 S3 容量、六包权威 runner、真实 t1–t4、性能、S4 或前端阶段退出。

## 1. 问题、结果与冻结边界

FE3c 关闭请求必须携带 `expected_review_version`，仅有归档权限的确认人不能读取 Review GET，旧候选响应又没有该值。
现在 `GET /v1/archive-candidates` 的 `candidates[]` 每项提供必填 `review_version`（严格非负 I-JSON 安全整数，0–2^53−1），取自同一只读 control DB 事务中原本就读取的 ReviewProjection.optimistic_version；没有增加 SQL 查询、事务或审核读取权限。
归档确认人从该值填写关闭 CAS；Review GET 原 ACL 保留，stale 版本仍 409，关闭成功 201、同 key 合法回放 200。

只读版本不进入 `ArchiveCandidateRef`、candidate/candidate-set digest、归档选择或关闭 fingerprint。写请求的 `selected` 仍严格只有 `submission_id` 与 `expected_candidate_digest`，不能把整个候选读 DTO 转发进去。
本项修复了实际真实数据旅程及 ordered/Submit/History Compose helper 的四处整候选转发，并以含 `review_version` 的独立 mock 断言每个预检、确认、异常处置、归档请求只传两字段；保留业务理由及 subject 引用断言。

Owning Contract 仅在 `formal/contracts/business-lifecycle-and-state.md` 固定新增读字段与来源。
未改 SQLite schema、锁文件、Rust、比较/风险/记录语义、golden、candidate digest 或恢复边界；未增加兼容层或 fallback。
生成时间预期继续遵守现有上传侧检查，与 baseline 是否为空分开；Q18 不改变它。

## 2. 提交与文件归属

| 固定提交 | 实际职责 |
| --- | --- |
| 起点 `18e76dbbf0` | Q18 之前的当前 main；不是回退目标 |
| `a1ca3bad93a25cb47384a81fbc985075b1299c39` | 首次接口实现、Contract、测试、交接；尚缺实际消费者完整投影 |
| `94b25a32792821cbc5b3230d98a0aa6f13493c32` | 四处实际消费者投影修复与业务测试；最终产品候选 |
| `27eab454b7f645ca4d0f347b218de8eaec31eb37` | 同一独审者的初审/修复复审/全部实际证据核收及 GO |

Q18 仅改以下路径，不把提交区间内并行治理/S4 文档或产品归为 Q18：

- `vnext/backend/src/gateway_backend/application/archive/{snapshot,queries}.py`：现有权威 projection 生成独立只读候选行。
- `vnext/backend/src/gateway_backend/http/schemas/archive.py`：required `review_version` 响应映射。
- `vnext/backend/tests/support/archive_fixtures.py`；`test_archive_queries.py`、`test_archive_http.py`、`test_http_openapi.py`、`test_archive_compose_e2e.py`：读版本、ACL/scope、stale CAS、成功/回放与 OpenAPI。
- `vnext/backend/benchmarks/real_dump_journey.py`、`tests/test_real_dump_journey.py`：strict selected 两字段与真实旅程消费者断言。
- `vnext/backend/tests/{test_ordered_compare_compose,test_submit_compose_e2e,test_history_compose_e2e}.py`：同根投影修复。
- 上述 owning Contract、本交接和独审报告。

## 3. 实际验证与直接来源

全部在 `ct107-gw-dms-06` / `gw-dms-06`，clean、已提交、linked worktree，磁盘 TMPDIR、offline uv/Cargo、pytest workers4；与产品 N1 分开。
没有在开发主机测试、编译或 lint。来源 WT 为 `/home/dev/gdds-test-tmp/be-q18-a1ca3bad93-06/wt/subject`：首轮在 a1，后续在无测试运行且取得本人标记后检出 94b。

| 实际来源/范围 | UTC、原始结果 | 原始日志与 SHA256 |
| --- | --- | --- |
| a1 archive focused；强制 native 重装/输入核对、五包 Ruff/mypy | 16:27:31–16:32:18；179 nonserial＋2 serial passed，entry/final/outer0 | 06 `/home/dev/gdds-test-tmp/be-q18-a1ca3bad93-06/logs/focused.log`；`390dcb75e3805517adfa8f7f284ed5de05a22f52a49b23e4a06733d4e9c0e366` |
| 94b consumer 增量；native 输入核对、五包 Ruff/mypy | 16:53:21–16:53:48；74 nonserial＋3 serial passed，entry/final/outer/capture0 | 06 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-06/node.log`；`56808f65b9d75b1ec73b8aa5def20e767a78f6124e436daae0a8289b863945a5` |
| 94b 四条当前产品容器旅程 | 16:57:42–17:02:53；每条1 passed，24/24步骤exit0，entry/final/outer/capture0 | 06 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-container-06/logs/container.log`；`f6a1b6c1b305bdcf127b73a251aaee9559a422d9bd8baf8a2d68b4c37981538b` |

a1 的 181 个 archive focused 是未变接口核心的直接来源，不冒称在 94b 重跑。94b 增量和四容器证明消费者修复；此选择由原审核者核收，非协调者自行沿用完整包结果。
增量 outer 原件 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-plan/outer.log` SHA=`89e8ef07a8442c3efd8e3ab15bfa451c3a0dad1dad62151481b11c8b878f5215`；
容器 outer `/home/dev/gdds-test-tmp/be-q18-94b25a3279-container-plan/outer.log` SHA=`674ac39773fed46748fd13ca5e3c5b120bbd262f342cbd7488ce39b78642d51e`。
原审逐项重算节点原件/副本、六锁前后及起止 HEAD；无锁漂移、无测试期间写入、无 dirty 结果。

四个 exact nodeid（均 `integration`＋`serial`、`-n 0`）依次实际运行：

```text
tests/test_archive_compose_e2e.py::test_compose_business_rejection_manual_close_and_fresh_upload_archive
tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey
tests/test_submit_compose_e2e.py::test_compose_submit_removes_deleted_user_and_sibling_tables
tests/test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart
```

## 4. 容器、镜像与资源收尾

Q18 修改实际 Compose e2e，故在最终产品 94b 本机离线构建并执行上述适用门禁。
预置 backend base 为 `gateway-backend-deps:lock-578e079b762e`，完整 input `578e079b762e170dacf10974ddaf81462fef99c2db355a53af9a49610dac3ff5`，config `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`、全部19 DiffID及 label 均实核；来源为原 S3 已核收预填充链。RS base `gateway-p2r1-repository:lock-6dc9659f0aee` 核当前 lock label并记录 config/全部 DiffID，观察候选不冒充 base 构建来源。
设置预置依赖、build network none，保留 Compose 本机构建，不设 prebuilt，不用转发代理或公网。

每例有独立 project/provenance，三运行容器的本机 image ID 与当次保存 tag 一一相等，runtime config digest/全部 DiffID 齐全（backend/worker各13、RS28）。跨节点不以本机 ID 判等。
RS 专用 tag `gateway-repository-service:be-q18-94b25a3279`，revision=94b，build-input=`c6a2792901ad9e1c90c401b455258685c4f4e2e0`、source-tree=`sha256:e450ceba3b21e940ac0d9d6a5bd521e662c6bc2d92c655e8b71c4a9a3fd12646`；实际绑定见独审 §13 的四例逐行矩阵。

10份实际 JSON 原件的本地字节副本位于 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-container-plan/captured/logs/`。
其逐文件清单 `/home/dev/gdds-test-tmp/be-q18-94b25a3279-container-plan/captured-json.sha256`，SHA=`8d822d319df52d9618a9af098eba7e877d6f2847eb9585da32c8dc7afab00fe2`。
四份 runtime tar、原 JSON、原日志和同来源 WT 保留在06；每例本人容器/卷/网络均清零，最终 marker文件/目录释放0，原审独核 Docker/8000/marker为空。未清他人资源或冻结基准。

本交接不是新的全量 runner 来源或最新 main 的容器 carried 判定。后续 S3 最终候选如改变 vnext/部署/实际测试，按闭包和强制重建规则验证；不把 Q18 的单项门禁代替整阶段义务。

## 5. Findings、限制及前端交接

实际消费者整候选转发的产品 finding 已在94b经代码、focused和四容器实证关闭，无剩余 Q18 阻塞 finding。
RS base 来源字段及传输父目录等执行稿问题均在运行前由同一独审者指出并修订，旧 SHA未执行；原稿/复审记录留在 review，不补造失败测试或更改预期。

附加的 live `/openapi.json` 单次读取在本次 archive 容器健康/监听快照后遭 curl7、HTTP000，未生成响应文件，未重试或重启。
观察原件 `production-openapi-observation.txt` SHA=`be9044d5a81ca486866fd920b1c3080ae7813233017589840caff72757ad8925`。
因此**没有交付新的 production OpenAPI 原始快照**；这项缺失不伪称通过。原审根据 OpenAPI 必填字段 focused、未变 DTO 及真实 API 旅程核收 Q18；前端在其自有真实栈按既定流程刷新快照、生成类型和 mock。

可转发前端：

> Q18 后端已在固定94b修复并经独审 GO。归档候选逐项返回 `review_version`，关闭请求的 `expected_review_version` 从该值取得；不猜常量、不增加 review 权限。Review GET 仍遵守原 ACL，过期版本409。`selected` 必须只传 `submission_id` 和 `expected_candidate_digest`，不要转发整个读 DTO。请按此刷新 OpenAPI/生成类型/mock，再完成 FE3c 关闭旅程验收；后端 GO 不等于 FE3c 已退出。生成时间修正仍按每个实际上传侧检查，空 baseline 不免除缺失异常，现有预期表和首次真实核对安排保留。

前端文件/快照未由本项修改；S3剩余容量/真实性能、S4和前端验收各自继续。未推送、未打 tag、未办理发布或正式 S3 退出手续。
