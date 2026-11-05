# FE3a 证据核对（第 1 次）

- **对象：** 开发主机分支 `fe-vnext` 的证据 handoff 提交 `0e7caf66f4558e3337d5688e263970f2945a64a2`。
  - 相对复审第 2 轮通过的 `58c6c9e29f`，只改 `docs/frontend-vnext/fe3a-handoff.md`；
  - `frontend/` 树仍为 `8a9f11c84f`，代码候选为 `09715b2205`，`vnext/` 树为 `2791d3ff3d`。
- **依据：** [FE3 kickoff](../fe3-kickoff.md) §3.2 的 FE3a 退出条件，[复审第 2 轮](fe3a-rereview-2.md) §4。
- **日期：** 2026-11-05。
- **结论：通过。** 04 上三项权威运行都已通过：
  - 模拟接口全量 runner（含截图）；
  - 上传包的后端校验，本次补跑，见 §2；
  - 真实 backend 冒烟。

  M1 已经测完，owner 已看图，并授权 FE3a 退出。

## 1. 实施方的 04 运行

- **运行位置：** 节点 `gw-dms-test-04.lan`，worktree `/home/dev/gdds-fe-fe3a-evidence`。核对时这个 worktree 处于 detached `58c6c9e29f`，并且是 clean。

| 运行 | 起止（UTC） | 核对 | 日志 / SHA256 |
| --- | --- | --- | --- |
| runner `--e2e --screenshots` | 11:48:45–11:49:37 | 日志记录了 hostname，起止 HEAD 都是 `58c6c9e29f`，起止 `frontend/` 树都是 `8a9f11c84f`，exit 0 | `/home/dev/gdds-fe-logs/frontend-fe3a-evidence/frontend-tests-20261105T114845Z.log`，`3383d9a2…4dfa4b72b`，与 handoff 一致 |
| 真实 smoke `--session fe3a-evidence` | 11:49:50–11:52:04 | 详见下文 | `/home/dev/gdds-fe-logs/fe3a-04/smoke/real-backend-e2e-smoke-fe3a-evidence-58c6c9e2-20261105T114950Z-1558148.log`，`98768dfd…7c14355`，与 handoff 一致 |

smoke 日志中核对了以下各项：
- 占用标记：会话名、用途、开始时间、worktree 与 HEAD；
- 依赖镜像：label 为 `c668cef8…`；
- `provisioned_mappings=7`、`worker_ready=ok`、`openapi_compare=match`；
- Playwright：`playwright_process_exit=0`，`expected=9 unexpected=0 skipped=0 flaky=0 errors=0`；
- 结尾：`worktree_clean_end=true`、`cleanup_status=ok`，exit 0。

**截图：** 96 张，目录 `/home/dev/gdds-fe-evidence/fe3a-04/screens`。
- 聚合 SHA256 `15e316d3…fc0fb1e065e9`，算法为 `cd <目录> && sha256sum *.png | sort -k2 | sha256sum`；
- owner 已看图确认，以后可能微调符号与字体，不需要大改。

**5 个输入 scope 的结果：** 与 05 一致，比较对计数相同，5 个 `bundle_digest` 也逐个相同：
- A、B②、C：0→1，changed 9；
- D：0→1，changed 4；
- B FULL：0→1 changed 9，1→2 changed 5；
- 所有 scope 的 `failed_pairs` 与 `failed_table_count` 都为 0。

**运行后：** 04 没有占用目录，没有本前缀的容器、卷、网络，也没有 RS 临时 tag。

## 2. 补跑：上传包的后端校验

- **为什么补跑：** kickoff §3.2 把它列为 FE3a 在 04 上的退出条件。实施方的证据中没有这一项；我在复审第 2 轮 §4 写下一步时也漏写了。
- **为什么由审核会话补跑：**
  - 它只需要一次运行，不起 Compose 栈；
  - FE3a 改动了 `client.ts` 中 manifest 的 `raw_sha256` 格式，这一项应当在退出前确认。
- **运行方式：** 在同一个 clean worktree（`58c6c9e29f`）上运行。
  - 运行前手工获取占用 `/home/dev/gdds-node-busy.d`，标记写明会话名 `fe3a-evidence-check`、owner `fe3a-review`、用途 `fe3a-04-upload-package-validation` 与开始时间；
  - 12:07 获取，12:08:27 删除标记并 `rmdir`。

| 项 | 值 |
| --- | --- |
| 命令 | `frontend/scripts/validate-upload-package.sh --output /home/dev/gdds-test-tmp/fe3a-04-upload-validation --log-dir /home/dev/gdds-fe-logs/fe3a-04/upload-validation` |
| 结果 | exit 0；`with-logics` 被接受（3 个成员），`without-logics` 被接受（2 个成员），`long-path` 被接受（3 个成员），`missing-dbcfg` 被拒收（`UPLOAD_CLOSURE_INVALID`）；`RESULT packages=4 failures=0` |
| 依赖镜像核对 | `required_inputs_match=true`；`record_only_mismatches=backend/pyproject.toml,rust/Cargo.lock`，与 FE2 kickoff §7.1（Q14）的已知情形相同 |
| 工具链 | config digest `sha256:a0d7b2b4…a1017` |
| 日志 | `/home/dev/gdds-fe-logs/fe3a-04/upload-validation/upload-validator-58c6c9e29f-20261105T120740Z-1568674.log`，SHA256 `395d0f3b3d3f5abe2112027e85a5f7a1194b304d21fa45dd3648294bcfc1a963` |

运行后 worktree 仍是 clean。

## 3. handoff 勘误

以下几处不改 handoff，在退出记录中更正：

- **§9 第 5 项：** “实施方确认接受该偏差”应为 owner 接受。owner 于 2026-11-05 看图并授权 FE3a 退出，同时接受“M1 用生产构建测量”这一偏差。
- **§9 第 4 项：** “04 取证未执行”已过时，04 取证见 §0.5 与本报告。
- **§0.5 标题：** 标题写“复审通过前”，实际上 04 取证是在复审第 2 轮通过之后进行的。
- **漏项：** handoff 没有记录上传包的后端校验，见本报告 §2。

## 4. 退出

- FE3a 满足 kickoff §3.2 的全部退出条件：
  - 审核：审核结论为定向修复，复审第 1 轮为定向修复，第 2 轮通过；
  - 04 三项运行都已通过；
  - M1 已测完，按 Q12 满足；
  - owner 已看图并授权退出。
- tag 与合并：
  - 附注 tag `fe-fe3a-exit` 指向证据 handoff 提交 `0e7caf66f4`，审核范围 `fe-fe2c-exit..0e7caf66f4`；
  - 以 `--no-ff` 合入 main。
