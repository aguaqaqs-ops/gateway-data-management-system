# p7-backend-remediation 总结

- **起止提交 / exit tag / 日期：** 起点 `gw08-midterm-exit`（`d7b54533f0467c5e0bbdc3e63404a68915c1c763`）；公开 OpenAPI 定稿 `Sb`（`e5bfd7c46e1e0966051955e47308cb6c33ca8962`）；最终代码候选 `1c9c758cc5c90febcc63af7d1960aeba2b9767b9`；退出提交 `Sx` 即本总结提交 `H`（指向本地附注 tag `p7-backend-remediation-exit`）；日期 `2026-11-17` – `2026-11-18`。

- **完成：**
  - **删除与单基线（第 1 批）：** `J6` 完成 `vnext/backend` 全量 `ruff format`（703 文件）并接入 `run-tests.sh` 最早预检；`C1` 删除 `repository_service` 废弃的 P2-R1 7 个模块及 `SqlServerProvider`、`ServerSupervisor`、`preflight_cgroup`、`repository-probe` 等并同步文档；`C2` 精简 `artifact_cleaner` 清理协议并保留三屏障测试与 pin/边界校验；`C3` 将 `repository_service` `control_db` V2–V16 合并为单一基线并删除无写入列及 `artifact_residual`。
  - **结构整理与公开 schema 定稿（第 2 批）：** 严格串行完成 `J2`（提取 `job_steps.py` 与 `document_string`）、`J1`（独立编解码 `documents.py`）、`J3`（拆包 `preview_jobs/`、`submit_jobs/`、`history/compare_jobs/`，更新全部四类私有引用）、`K1`（用例编排与结果读取下沉至 `application/`，逐路由核齐错误/状态/拒绝顺序）、`G1`（Preview bundle 构造三角色约束）及 `G2`（公开 `/openapi.json` 移出 6 条 `/internal/v1` 路径及 5 个仅内部 schema，保留 35 公开路径与 102 组件并各自冻结）。另完成仓库 `WT` 安全清理，释放约 20.24 GiB。
  - **四门禁与基镜像（第 3 批）：** `J4` 禁止 `src/` 跨包目录私有导入（空基线）、`K2` 将 `statistics` 与 `history` 结果授权迁入 `application/` 并禁止 `http` 导入 `domain.*.policies`（空基线）、`J5` 启用 Ruff `C901 <= 30` 接入 `run-tests.sh` 并按函数登记 14 项存量豁免（只减不增）、`RULE` 产出交接表；重建并向测试节点预填充后端 dependency-base。
  - **试点、审计与验证基线（第 4 批）：**
    - **`L2` 与 `L5` 决定：** 仅 Class 2（`composite_signal` 与 Arrow 防护）保留；Class 1 样板净减 `-30.8%` 未达 `>= 40%` 门槛，已局部撤回为 J1 手写严格解码器，**不开启 `L5`**。
    - **`P1` 与 `P2`：** 审计全部 119 项 digest 名，经 Owner 批准删除 11 个只写不读内部字段（保留全部 23 个公开 OpenAPI DTO digest 字段、`raw_state_digest`、受保护 `comparison_facts_digest` 与 `PreviewResultDigests.input_digest`），同步更新 Contract 与 golden；定稿六类 53 种 digest 归属指南（`digest-map.md`）。
    - **`D24` 与 `C4`：** 增加显式 `N` 传递与 `--scope full` 精确并发守卫（生产默认 `N=1` 不变）；补充 `vnext/deploy/README.md` 与 RS Dolt 升级说明。
  - **跨端与规则交接分离：**
    - **转交前端（`Sb` 与 `Sx` 分列）：** `Sb = e5bfd7c46e1e0966051955e47308cb6c33ca8962`（公开 OpenAPI 相对 `G2` 逐字节完全一致，`Sb` 后无接口或 OpenAPI 变化）；`Sx` 为本总结提交 `H`（绑定门禁且为 `p7-backend-remediation-exit` 所指，供前端在 `04` 跑完整真实 `journeys`）。
    - **转交规则会话：** 四条门禁交接表见交接区 `reference/rule-gates-handoff.md`（规则文档由规则会话更新）。

- **偏差：**
  1. `L2` 试点 Class 1 未达 40% 净减门槛，已按方案撤回并决定不开启 `L5`。
  2. `L2` 首轮 `t1` 运行误带 `--keep-stack` 产生口径偏差；已按 Owner 选择在 `05` 冷栈重跑补证并经原审复审闭环，旧结果保留不改写。
  3. `023f1a9eb0` 首次 `D24-N1` 在 `v2-preview` 因 `real_dump_journey.py` 沿用旧 `S1b` 基线 `26`（未随 GW08 提交 `9465f7a853` 移出 11 张 `BUSINESS_SEQUENCE_KEYS` 表的自增序列重排变更同步更新为 `15`）中止，同时暴露 `d24-capture.py` 失败路径会覆盖原异常；经只读排因与 Owner 批准后更新基线至 `15`（`1c9c758cc5`）、独审与复验采集脚本并在 `1c9c758cc5` 重跑 `D24-N1`/`N2` 通过，原失败现场保留未动。
  4. 按 Owner 2026-11-18 指令将默认独审角色文档更新为 `gpt-6.2-sol`（提交 `1ce8ad1de2`、`61eb1b1144`），本轮 Antigravity 执行沿用 Owner 既批 Gemini 子 Agent 规程并由最终门禁绑定最新 HEAD。

- **验证：**
  - **门禁与构建：** 第 1–3 批及 `023f1a9eb0`（全六包实跑）、`1c9c758cc5`（`--purpose stage` 含容器门禁）的 `04` 阶段门禁均已通过，本总结提交 `H` 随后由阶段门禁自动绑定；结果与原件索引存阶段交接区 `gate/`（`b1-stage-gate/`、`b2-stage-gate/`、`b3-depbase/`、`b3-stage-gate/`、`b4-final-stage-gate/`、`b4-t4-baseline-gate/`、`b4-exit-bind/`）。
  - **独立审核与验收核对：** 重点包（`C2`、`C3`、`J3`、`K1`、`L2` 含冷栈复审、`D24`）、整轮（`gw08-midterm-exit..023f1a9eb0`）及增量（`023f1a9eb0..1c9c758cc5`）独审全部 0 findings 通过；阶段只读验收核对通过，报告均存交接区 `reviews/`。
  - **真实数据与限制：** `L2`（`05` `t1`）与 `D24`（CT108 `t4` `full` `N=1` vs `N=2`）均通过，全部确定性业务计数、`canonical_state_digest`、`history.surface_digest`、`actual_bytes` 及 6 操作 D23 执行摘要一致；**未测/保留限制**：跨冷栈 `bundle_digest` 与 `raw_tar_sha256` 因既有 `client_parquet.py` 写入每栈随机 `repository_id` 仍不相等，`04` 门禁记录 `uv_cache_history` 为 `UNKNOWN`，原始记录与对照报告存交接区 `reference/`。

- **遗留：**
  1. 跨冷栈 `bundle_digest` 字节级一致尚未成立（受每栈随机 `repository_id` 影响），若后续有跨栈可复现 tar 字节需求须另立 `client_parquet.py` 改造项；`04` 历史 `uv_cache_history` 来源待后续离线基线重建时补齐。
  2. `digest-map.md` 中 7 项标为“未知/待决定”的 digest 核对归属留待后续 owning 阶段确认。
  3. 四条门禁交接尚待规则会话接收确认；包含 `Sx` 的前端完整 `journeys` 尚待前端会话在 `04` 执行并回执，不阻塞本阶段退出但前置 S3 实施。
