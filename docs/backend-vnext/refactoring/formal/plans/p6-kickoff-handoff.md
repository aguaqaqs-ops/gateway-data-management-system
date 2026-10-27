# Phase 6 S0 Kickoff 小修 Handoff

状态：**已通过轻量审核并合入 main**（[kickoff 审核](p6-kickoff-review.md)）

日期：2026-10-26（UTC）

实现分支：`p6-s0-kickoff`。代码与相关文档提交：`cd1fe7ffc05cc0f5f50dbbfb81349682ca194a83`（实现、Compose 与文档整理）、`54492807a4d82b8f7ce3cb8ecbb90590fda68dd3`（Popen 测试调用类型修正）、`b46a799d8073ee361bccf903df739db042463017`（兼容 Python 的 SIGTERM returncode 表示）。最终门禁对象为 `b46a799d8073ee361bccf903df739db042463017`。本 handoff 随实现分支单独提交。未推送、未合入。

实施从 main HEAD `a64f9a1b7d3cd85df6efb9a961fbac1453ff3765` 建立隔离 linked worktree，因为开始时主 checkout 有其他未跟踪文件 `vnext/backend/benchmarks/real_dump_keyless_census.py`；没有修改该文件或主 checkout。合入方式由 owner 决定。

## 改动

1. **uv 锁快照清理**：`vnext/scripts/uv-consume.sh` 为 `LOCK_SNAPSHOT` 安装 EXIT trap，覆盖 uv 失败和可捕获信号后的 shell 退出；既有显式清理保持幂等。`test_uv_consume_script.py` 加入失败退出与 SIGTERM 回归用例，信号用例标记为 `serial`。
2. **SQLite sidecar 清理**：backend 的 repository import control-row inline 查询在关闭连接后清理 `repository-import-*.sqlite3-shm`、`-wal` 与主文件。两个调用该查询的测试使用独立 `TMPDIR` 并断言没有 SQLite 临时文件残留。没有改产品持久化语义。
3. **RS defunct Dolt 修复**：`vnext/deploy/compose.yaml` 的 `repository-service` 服务增加 `init: true`，由容器 init 进程回收 Dolt 派生的孤儿进程。
4. **文档整理**：
   - Snapshot Materialization 文档标出 hidden summary 写入/readback 表述已由 ADR 0019 取代，并指出当前 manifest authority 与单遍读取。
   - P5 收口设计补齐 DC28–DC34 索引，澄清 DC26 的精确 import 放行与 Phase 6 无生产消费者延期是两项不同状态。
   - 5B S8 handoff 将 deferred 表保留为 S8 时点历史，并新增 P5 exit 后处置；G11 审核记录补充当前状态；P5 exit review 中 R2-O3 行与 EXIT-F4 已关闭结论对齐。

## Repository Service defunct Dolt

在 `ct108-gw-dms-05`、基线 HEAD `c50ac77885863a959becd360662fb883b96b86c4` 上，用合成的双表 commit 通过公开 Repository Client 重复逐表读取复现。原配置没有容器 init（`HostConfig.Init=null`）；PID 1 是 `runuser -u gateway -- python -m uvicorn ...`。Dolt 派生的孙进程脱离 `DoltRunner` 直接子进程后被重挂到 PID 1，PID 1 不回收它们：额外 60 次逐表读取前后 defunct Dolt 从 **74 增至 134**。这确认了 V7 的推测。

根因局限于 Compose 未配置 init 进程，使用 `init: true` 属于局部修复。候选 HEAD 上同样执行 60 次额外逐表读取：`docker inspect` 显示 `Init=true`，PID 1 为 `/sbin/docker-init -- ... uvicorn ...`，读取前后 Dolt zombie 均为 **0**；Compose teardown 后容器、网络、卷、Dolt、临时 HOME、客户端进程与线程均无残留。

## 验证记录

所有测试均在指定测试节点运行。以下时间为 UTC；每份日志均记录 hostname、起止时间、起止 HEAD 和 exit code。

| 工作 | 节点 / HEAD | 起止时间；exit | 结果 / 日志 |
| --- | --- | --- | --- |
| SQLite sidecar 基线复现 | 05 / `c50ac77885863a959becd360662fb883b96b86c4` | 05:17:09–05:17:11；0 | 两个目标 backend 用例通过，并观察到两组 `-shm`/`-wal` 残留；`/home/dev/gdds-p6-logs/kickoff/sidecar-baseline-c50ac77.log` |
| RS defunct 基线复现 | 05 / `c50ac77885863a959becd360662fb883b96b86c4` | 05:21:50–05:22:18；0 | 60 次额外逐表读取令 zombie 74→134；`/home/dev/gdds-p6-logs/kickoff/rs-defunct-baseline-official2-c50ac77.log` |
| 五包 Ruff/mypy 与 focused 回归 | 05 / `b46a799d8073ee361bccf903df739db042463017` | 05:28:49–05:28:55；0 | 五包 ruff/mypy 全通过（34/15/26/486/200 个 source files）；uv-consume 清理 2 passed；backend SQLite sidecar 2 passed；`/home/dev/gdds-p6-logs/kickoff/focused-b46a799d80.log` |
| RS defunct 修复后复现 | 05 / `b46a799d8073ee361bccf903df739db042463017` | 05:29:29–05:30:06；0 | 合成双表 commit，60 次逐表读取；`Init=true`，zombie 0→0；`/home/dev/gdds-p6-logs/kickoff/rs-defunct-after-init-b46a799d80.log` |
| RS 镜像重建 | 04 / `b46a799d8073ee361bccf903df739db042463017` | 05:30:51–05:31:01；0 | 见下方镜像记录；`/home/dev/gdds-p6-logs/p6-s0-kickoff/repository-service-image-build-b46a799d80.log` |
| 权威 runner 首次预检尝试 | 04 / `b46a799d8073ee361bccf903df739db042463017` | 05:31:08–05:31:54；1 | 在 rust manifest 前因 root PATH 未包含已安装的 `rustc` 而停止，没有运行包测试；详见偏差；`/home/dev/gdds-p6-logs/p6-s0-kickoff/authoritative-runner-b46a799d80.log` |
| **六包权威 runner** | **04 / `b46a799d8073ee361bccf903df739db042463017`** | **05:32:46–06:11:50；0** | **全部包通过**；`/home/dev/gdds-p6-logs/p6-s0-kickoff/authoritative-runner-b46a799d80-rerun1.log` |
| 04 postflight | 04 / `b46a799d8073ee361bccf903df739db042463017` | 06:12:06–06:12:06；0 | clean worktree；无 Dolt、活动容器或 8000 端口占用；Hypothesis 目录与 Cargo target 均不存在；`/home/dev/gdds-p6-logs/p6-s0-kickoff/postflight-b46a799d80.log` |

权威 runner 逐包结果：

| 包 | 结果 |
| --- | --- |
| `rust` | `cargo fmt`、clippy、`cargo test` 均 exit 0 |
| `shared_kernel` | 242 passed |
| `repository_contracts` | 152 passed |
| `repository_client` | 154 passed |
| `backend` parallel / serial | 2917 passed / 39 passed |
| `repository_service` parallel / serial | 1740 passed、1 skipped / 206 passed |

runner 在开始和结束时均为 clean detached worktree、HEAD 不变。package status 全部 `passed`；日志记录的总 exit code 为 0。RS 容器旅程已包含在权威 runner 内。

## 镜像重建

在 04 的干净 detached worktree、当前候选 HEAD 上运行 `./vnext/scripts/build-repository-service-image.sh`。结果：

- tag：`gateway-repository-service:local`
- image ID：`sha256:f5d1d8451b1bb423fe3718a36f8a2d521634409e9a32422394026fdfeb5da494`
- `build-input-revision`：`b46a799d8073ee361bccf903df739db042463017`
- `source-tree-sha256`：`sha256:471723522dc19e5daf38e48a4c9a74ba0d837831dc22245a34dd6011af374e41`
- `uv-lock-sha256`：`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`

## 偏差与未决

- 04 首次 runner 预检失败是 SSH root PATH 配置问题，不是缺少工具链：`1.97.0` 工具已在 `/root/.rustup/toolchains/1.97.0-x86_64-unknown-linux-gnu/bin` 安装。随后仅在 runner 进程环境中将该目录加到 PATH，fmt/clippy/test 与全包 runner 全部通过；未跳过 rust 包或修改节点配置。
- 两次较早的 focused 尝试分别发现了新测试的 mypy `Popen(check=...)` 类型错误，以及 Python 将 SIGTERM 状态表示为 `-15` 而非 `143`。均已修复；终版 focused 结果见上表，失败日志保留：`/home/dev/gdds-p6-logs/kickoff/focused-cd1fe7ffc0.log`、`/home/dev/gdds-p6-logs/kickoff/focused-54492807a4.log`。
- 无未解决的代码或验证事项。未运行真实数据；本任务范围不要求真实数据。

## 节点清理与保留

- 05 的 focused/debug worktree、任务专属 TMPDIR、临时 bundle 和复现脚本已清理；清理日志为 `/home/dev/gdds-p6-logs/kickoff/node05-cleanup-b46a799d80.log`。focused 与复现日志保留。
- 04 的任务 bundle 已移除；runner 清理了五个包专属 Hypothesis storage 与 Cargo target。镜像、日志和 clean detached gate worktree `/home/dev/gdds-p6-s0-gate04` 保留，按 DC51 待轻量审核通过并合入后再清理。
- 测试节点 04 当前 Compose/Dolt/端口残留为零；节点 05 在清理前同样为零。

## 轻量审核请求

请复核上述三个改动面、Dolt 孤儿进程根因与 `init: true` 验证，以及 04 全量门禁 provenance。审核通过后由 owner 决定将 `p6-s0-kickoff` 合入主线；实施方未推送。
