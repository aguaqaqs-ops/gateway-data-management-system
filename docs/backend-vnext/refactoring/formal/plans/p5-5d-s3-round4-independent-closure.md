# P5-5D-S3 Round-4 Independent Closure Review

日期：2026-09-23。

结论：**复审通过，上一轮两项 P2 关闭；未发现新的阻断 finding。建议进入 S3 stage exit 签署。**
本记录不修改 stage/slice authority，不授权 production deployment；S4 最终候选验收仍须单独执行。

## 候选与范围

- Current HEAD：`918a75a4987c3739c7a70ca8acc680aaeaf436e7`。
- 实现绑定：`d61d37be97821f303e9083abe739618cebd96b46`。
- 审阅增量：`2a5fca344af27b58f8ebbf04c496a5a22d83b41b..918a75a4987c3739c7a70ca8acc680aaeaf436e7`。
- `vnext/**` 无未提交修改；原工作区有三份既有未跟踪文档（closure-verification、rereview-fix-work-order、p5-5e-s0-independent-docs-review），未修改。
- 905 个 tracked `vnext/**` 文件，按 handoff 的 `path\tsha256\n` recipe 复算：
  `c21785c370568befd0c24517c190c003bde7b0ef1efcfc4fb6f97b68c0e24c15`，与 handoff 一致。
- 五个 uv.lock 及 compose.yaml SHA 均与 [handoff](p5-5d-s3-handoff.md) 一致。

## Findings closure

| 原问题 | 独立核验 | 结论 |
| --- | --- | --- |
| P2-1 深层 JSON 返回 500 | 中间件捕获 `RecursionError`。focused 新用例通过；另以 100001-byte、50000 层数组向四个 Archive POST 入口发送请求，全部返回 422 / `REQUEST_VALIDATION_FAILED` | 关闭 |
| P2-2 零 Repository effect 缺 main ref 屏障 | 前置确认 `main_after_a != initial_commit_id`、`main_after_both != main_after_a`；Start 后经 HTTP 重读 main 并断言等于窗口前值，同时保留 commit 集合与 Operation 数量不变断言。fresh-build 双 actor Archive journey 实测通过 | 关闭 |
| 后续自查：root Dolt 读取污染 | commit 集合读取明确使用 `exec -u gateway`；main ref 读取仅使用 HTTP，失败不回退本地 Dolt；容器旅程通过 | 关闭 |

修复限于请求解析异常处理及既有容器测试观测路径，未扩展生产机制。

## 本轮实测

| Gate | 结果 |
| --- | --- |
| E1：handoff 六个 focused 文件 | **137 passed, 1 warning，7.46s**；warning 为既有 Starlette/httpx deprecation |
| E3：五包 ruff + mypy（受控 uv wrapper） | **全部通过**；mypy 文件数 421 / 198 / 26 / 15 / 34 |
| E2：fresh-build conjunction | **6 passed, 0 skipped，346.44s，exit 0** |

E2 六个 nodeid（相对 `vnext/backend/tests/`）：

```text
test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect
test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey
test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart
test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey
test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint
test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service
```

## Build / running provenance

Rebuild required：**yes**（本轮核验修改后的 middleware / container harness）。已完成，无延期的 S3 conjunction nodeid。

Repository 构建脚本首次因原工作区未跟踪文档拒绝 dirty worktree，未产生镜像；随后在同一 HEAD 的
临时 detached clean worktree 执行 `./vnext/scripts/build-repository-service-image.sh`，**exit 0**。
Backend/worker 由原工作区的相同候选源码 fresh build，测试 harness revision 为上述 HEAD。

```bash
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-s3-independent-918a75a \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
GATEWAY_COMPOSE_GATE_PREBUILT=0 \
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest -q \
  -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
```

Archive 运行栈实际采集（2026-09-23，project `gateway-s3-independent-918a75a`）：

| Service | Container ID | Immutable image ID |
| --- | --- | --- |
| repository-service | `a5f026430a4d5e5e4104686a3d5d75e66cdac881c833bed9619457fb710f5f30` | `sha256:6dfc8ad602835ae54d6504bb459bc77eecd697561873f1a20bd3383cf6125a4a` |
| backend | `845b3294cfc4c773e95eaafbb9da0f4f489a92b4a784109655fbc51b8e20f9e9` | `sha256:2391594c8056e340197e185dabaa18253a2d11af6b057b4892002ef3f4f9279a` |
| worker | `2ed431fb1d736026d62a666b9cea986df6ab092a383aa881ef421e51d799636e` | `sha256:dc9b49cea82e2b2c6328e1c9ea004d8043848157321db36e961ec2f06b45fb10` |

Repository image revision 为当前完整 HEAD；其专用 build-context digest 为
`sha256:62a38a0881926ba0afd15fb22db292c15be19318649562033f4b9c3f91d642cf`（与全 vnext digest 的范围不同）。
Archive harness 已验证运行中的 backend/worker image ID 等于构建 image ID。
运行中 backend `/app/backend/src` 的 Python digest 实测为
`b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285`，与 handoff 源码摘要一致。
既有容器 owner 用例覆盖 CMD、readiness、clean-stop 与三进程重启。

本轮不跑 S4 权威全量 runner，不以本次 S3 复审代替 S4 最终 fresh candidate conjunction。
未修改生产源码、测试或依赖锁，未提交或部署；仅新增本独立复审记录。
