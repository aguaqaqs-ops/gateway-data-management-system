# Phase 6 S1b handoff

状态：实施与验收完成，交独立会话审核。

## 范围与候选

- 基线：`ae3301d6d8`（`p6-s1a-exit` 为 `1d6a8d03fe`）。实施分支：`p6-s1b-impl`，未推送、未打 tag，未在主 checkout 工作或提交。
- 权威门禁候选 V：`80ce756619290d0ec95515ab73470241ce56a311`。
- 最终实现与真实数据候选 H：`705b17c1a137ede6b4339376527b30a4c58288f7`。V..H 只改 `vnext/backend/benchmarks/real_dump_journey.py` 与 `vnext/backend/tests/test_real_dump_journey.py`，按 P5 执行计划 §8.9 处理；其中 33 张 t3 只增列表不再贡献 schema-only History record，基线由 744 修正为 711。H 的这两处修订已在 H 上重跑 `test_real_dump_journey.py`、相关 synthetic-load 测试、五包 Ruff/mypy 与 t1–t4 旅程。

### 提交清单

下列提交均位于 `ae3301d6d8..705b17c1a137ede6b4339376527b30a4c58288f7`：

| 提交 | 内容 |
| --- | --- |
| `9283a16cbc81` | 实施 Phase 6 S1b 业务语义 Contract |
| `4158ea39d481` | FLOAT 单次舍入与 build snapshot 清理 |
| `24f265e06e28` | 冻结 S1b parser 与 table-rule goldens |
| `57363b1d2692` | 调整 scheduler failure 行为测试 |
| `6f879c63a606` | 修复 additive schema summary 比较 |
| `33653ea7bdb5` | 对齐 S1b fixtures 与 legacy rule 检查 |
| `7d9622be9a56` | 修正 binary32 golden 向量 |
| `bb63babe7fd0` | 修复 S1b diagnostics 与静态检查 |
| `b4cf7391bead` | 修复 backend S1b 类型检查 |
| `e148f478d086` | 删除冗余 cache adapter cast |
| `066dd8281a36` | 保留 JSON census 的 SQL statement 边界 |
| `8351b1e9d21d` | 给 synthetic SET mutation 定型 |
| `f94762933afa` | 标注 synthetic SET mutations |
| `64fffc3307ff` | 计入 SQL INSERT 中每个 JSON tuple |
| `d83a24aa8079` | 修复 worker、bundle 与 cache 边界检查 |
| `78d99e9828ff` | 修复 synthetic input table width 追踪 |
| `b455649d4f8e` | 删除过期 preview 测试 import |
| `0eec65a3bb62` | 更新 Rust canonical vector corpus count |
| `74da64c2ee95` | 调整 browse-only table addition History 断言 |
| `d4c75b004707` | 输出 row-count mismatch 诊断 |
| `f6d979f5a262` | 支持多行 INSERT benchmark 输入 |
| `86f1b3b6628c` | 复用 W4 key index |
| `3a3fd5dad33b` | 修正 key candidate union 类型 |
| `61865d3b90f5` | 复用 W4 fresh-key candidates |
| `80ce75661929` | 修正 expanded W4 输入行数 |
| `23ba083a10e3` | 冻结 S1b real-data baselines |
| `705b17c1a137` | 按 additive-column 规则修正 t3 History baseline |

## Contract 与 golden

- Comparison facts 新增稳定 schema evolution：`NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE`。共有列继续比较；只增列（含 ENUM 标签、SET 成员只增）不降级、不生成 SCHEMA_CHANGE 风险，Submit 仍创建版本。整表新增/删除表现为整表浏览并带表级行数风险。
- Preview 与 History bundle 保留全部表绑定；内容相同的表按内容地址共享。表数据文件为 Parquet。snapshot export cache 以 `row_layout_digest + Parquet writer contract version` 为精确键，并经 artifact protection/TTL 管理；schema 或 writer 版本不同不命中。
- Upload 使用 60 秒 idle timeout 与 `最大包 ÷ 1 Mbps` 总上限；两者返回 `UPLOAD_STREAM_TIMEOUT` / HTTP 408，原因 `IDLE | TOTAL`；413 仅用于大小或资源限制。受理中的同步解压、artifact 写入及 control DB 工作在线程池执行，保留预算、断连释放和完成/取消边界。P5-5A 上传设计的错误码表已同步。
- 参照 SQL parser 为 BIT 负数/超宽/非 ASCII `b'..'` 返回确定诊断；BIT 数字字面量按十进制；支持仅用于二进制列的 `_binary` 字符串与十六进制字面量；保留 `\%`、`\_` 反斜杠；忽略列类型中的注释；JSON 拒绝 NaN、Infinity 与孤立代理，最大嵌套深度 100 且检查不递归。Shared Kernel FLOAT 直接舍入到 binary32；零日期仍拒绝。
- DC56 显式键名单按精确选择器落实：`comm_user_data(data_key)`；`forwardtbl_lst_cs/dz/qt/yc/yk/ym/yt/yx(tbname)`（8 个精确名，`STANDARD_EXACT`）；`mms_rp_cdc_index(idx)`；`out_time_cfg(board, link_no)`。显式键重复或 NULL 时稳定失败，不回退 keyless。新增 17 张 `BROWSE_ONLY`：`iec61850c_cfg`、`jdxx_cfg`、`cnt_manage_cfg`、`dev104_cfg`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、`nbridge_cfg`、`nr103d_cfg`、`nr103ht_cfg`、`sc_cfg`、`scada_cfg`、`sg_manage_cfg`、`sntp_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg`。规则文档从 v3 升至 v4；storage-projection 版本仍为 3。
- Worker 在 executor 正常或异常结束、以及收到停止信号时置位 runtime 持有的 wake event；非 drain 等待该事件，超时取下一 heartbeat 或 drain 截止的剩余时间，不用短间隔轮询。heartbeat、lease、drain 与单 executor 语义不变。build-repository-service-image.sh 的 EXIT trap 覆盖全部退出路径并清理 lock snapshot。
- Contract 文档更新：`comparison.md`、`comparison-surface.md`、`risk.md`、`comparison-bundle.md`、`snapshot.md`、`snapshot-table-access.md`、`shared-canonical-encoding.md` 与相应 capability 文档；P5-5A 错误码表同步。没有修改 p6-design、p6-execution-plan 或 owner decision record。

S1b 更新并冻结的 golden：

- comparison：`vnext/fixtures/golden/comparison/s1b/semantic-results.json`；risk：`.../risk/s1b/structural-risk.json`；surface：`.../surface/s1b/table-presentation.json`；bundle：`.../bundle/s1b/snapshot-table-bindings.json`。
- storage-projection 例外行只更新一次：规则 v4 对应的 ruleset golden 与 `storage-projection/manifest/valid/s5-durable-roundtrip/document.json`。受影响文件为 `ruleset/valid/s1-net-cfg`、`ruleset/valid/s2-migrated-matrix` 与 `ruleset/malformed/s1-duplicate-selector`。
- table-access 的 S1b 合成语义向量：BIT negative/too-wide/non-ASCII、`_binary` 文本列拒绝、JSON depth 100/101、NaN/Infinity/孤立代理、零日期及 parser semantics 接受例。
- shared-kernel canonical FLOAT 向量同步更新；Rust vector corpus count 同步。
- S1a mutation 与导入包 goldens 未改变；真实数据没有进入 Git。所有 golden diff 均对应以上批准项。

## 权威 runner、carried 与镜像

### V 上六包 runner

- 节点 `ct108-gw-dms-04`（hostname `gw-dms-test-04`），V clean worktree，2026-10-28 08:05:22Z–08:26:09Z，runner exit 0。日志：`/home/dev/gdds-p6-logs/s1b/04-runner-80ce756619.log`。
- 环境：umask 022、HOME `/root`、LC_ALL `C.UTF-8`、TMPDIR `/home/dev/gdds-test-tmp`，PATH 以 `/home/dev/.cargo/bin` 开头。Rust fmt/clippy/test 三步通过；六包状态均 passed。backend parallel 3045 passed、serial 40 passed；repository_service parallel 1741 passed/1 skipped、serial 207 passed。runner 退出时 `TMP_SNAPSHOTS_AFTER=` 为空。
- V 起始 package manifest total digest：rust `7a85c5544d4c53794ea0fadd8db803e5f273ffd3d1f2069a34fdc4332cbe9867`；shared_kernel `54e51c2a078d5e47bce39cca8277a0c3541f73036fff871c058332cc5216e928`；repository_contracts `30a2c50c7c3bd2ef296cd1b43b2d0a6896e5373d23612fe0cbb86d7aba02d3f3`；repository_client `162d732710870e114456dce5b9df267c1560a8bab539a6a9c15ea376b2aa4c44`；backend `a14a0567b049dd918cd771f5c6a785b5587e85ad36af77893427793174568a13`；repository_service `1c054008a4b790f15a09bf0f8b960df2c956c59ac7a979bce7eea5e34d83ceca`。

### H 上逐包判定

- V 与 H 的逐包 compare 在 CT04 的同一 `04-wt` worktree 完成；比较日志为 `/home/dev/gdds-p6-logs/s1b/04-carried-manifest-compare-H2-705b17.log`。rust、shared_kernel、repository_contracts、repository_client 为“可沿用”，变化组件为空，来源直接指向 V runner。
- backend 与 repository_service 的 `docker:context:vnext` 摘要在 H 变化；backend 还变化 `package:backend`，与 V 后允许的 benchmark/test 修订相符。因此两包在 H 上另行运行，未把 compare 的“运行”绕成 carried。
- H 上 `GATEWAY_TEST_PACKAGES=backend,repository_service` runner 使用 CT04 同一 clean worktree；节点 hostname `gw-dms-test-04`，2026-10-28 13:42:31Z–14:03:49Z，起止 HEAD 均为 H，exit 0。日志 `/home/dev/gdds-p6-logs/s1b/04-runner-H2-backend-rs-705b17.log`。backend parallel 3045 passed、serial 40 passed；repository_service parallel 1741 passed/1 skipped、serial 207 passed。H 的 post-sync package manifest digest：backend `7f8de198031889f7ec43f42d3a1b0e180d0a8c6bf69d4ad06b839c3cbc70e305`，repository_service `9bebcf74fbaa02fa185fe2d620790d002caa8f6221a6bd59e2ed2323aa031fcb`。退出后复核 HEAD 仍为 H、worktree clean、cache HTTP 200、Hypothesis leftover 0、Cargo target 不存在、TMPDIR lock snapshot 0、active container 0、Dolt process 0；runner 与 postcheck 均 exit 0。postcheck `/home/dev/gdds-p6-logs/s1b/04-H2-runner-postcheck.log`。
- CT04 carried identity：V repository-service image ID `sha256:bd6cb6913f94d62d8dbc8cdc636e21852a30471c43dbeb04d53239a69d6fc312`，build-input revision `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，lock SHA `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`。H 在同一 CT04 worktree 重算得到相同 build-input revision 与 source-tree digest；`gateway-repository-service:local` label 匹配。identity log：`/home/dev/gdds-p6-logs/s1b/04-carried-identity-H2-705b17.log`。V build log：`/home/dev/gdds-p6-logs/s1b/04-image-build-80ce756619.log`。

### 05 门禁前预检与 H focused/static

- V 的 05 预检均通过（不作为门禁证据）：`05-static-preflight-80ce756619.log`、`05-parallel-preflight-80ce756619.log`、`05-history-compose-preflight-80ce756619.log`，均在 CT05/HOST `gw-dms-test-05`，HEAD V，exit 0；V image build 记录 `05-image-build-80ce756619.log`。
- H 的 `test_real_dump_journey.py` 58 passed（2.90s）；五个 Python 包 Ruff 与 mypy 全通过。日志 `/home/dev/gdds-p6-logs/s1b/05-focused-static-H2-705b17c1a1.log`。
- H 的 synthetic load focused 测试 4 passed（0.62s），日志 `/home/dev/gdds-p6-logs/s1b/05-synthetic-load-H2-retry1-705b17c1a1.log`。第一次因远程命令使用错误 cwd，pytest 未启动即 exit 127；改为 worktree 绝对路径后通过，未改代码。

### 网络与缓存

- 开发节点只提供 LAN 静态缓存 `192.168.233.180:18080`，HTTP 200；没有配置公网转发或代理出口。缓存目录 `/home/dev/gdds-p6-logs/s1b/dev-cache` 在 Git 外，缓存清单注明只提供已批准制品。CT04/05/CT108 的运行日志仅记录缓存来源类别与 HTTP health status，不含凭据。
- CT04 选定包 runner 的 uv lock resolution 均命中本机环境/cache；Rust toolchain `1.97.0`、cargo/rustc/rustfmt/clippy-driver 在 `/home/dev/.cargo/bin` 可用，registry source/archive 各 166 项。Rust 权威门禁命令为 offline。H backend extension rebuild 使用 `CARGO_NET_OFFLINE=true`，build-input 校验通过。
- V 镜像构建依赖的 Docker base/service images 均从本机缓存取得。H 后的 candidate Git bundle 从批准的 LAN cache 到 CT04，用于同一 worktree carried 计算；bundle SHA-256 `8cdbaa7c335a5dace3d01d2a338b0cd3bb19a330216634c94faf8403e41862bf`。

## t1–t4 完整旅程

所有旅程在最终 H=`705b17c1a137ede6b4339376527b30a4c58288f7` clean worktree 运行，容器栈已停止、卷保留。

| 档位 | 节点/hostname；起止 UTC；exit；日志 | 结果摘要 |
| --- | --- | --- |
| t1 | 05 / `gw-dms-test-05`；11:33:53–11:37:54；0；`05-t1-final-H2-705b17c1a1.log` | offline composite 4 行 unchanged；v1 Preview 125/125 changed，重复 Preview 0/125；v2 4/125 changed；degraded/failed 0；History 12 records。 |
| t2 | 05 / `gw-dms-test-05`；11:38:57–12:07:48；0；`05-t2-final-H2-705b17c1a1.log` | offline composite 45 行 unchanged；v1 Preview 209/209，重复 0/209；v2 57/220；degraded/failed 0；History 1147 records。 |
| t3 | 05 / `gw-dms-test-05`；12:11:19–13:12:06；0；`05-t3-final-H2-705b17c1a1.log` | offline composite 201 行 unchanged；v1 Preview 192/192，重复 0/192；v2 23/193；degraded/failed 0；History 711 records。 |
| t4 | `ct108-gw-dms` / hostname `gw-dms-test`；11:30:44–12:49:50；0；`ct108-t4-journey-H2-705b17c1a1.log` | offline composite 435 行 unchanged；v1 Preview 312/312，重复 0/312；v2 26/312；degraded/failed 0；History 168 records。 |

对应 stack stop 日志：`05-t1-stack-stop-H2-705b17c1a1.log`、`05-t2-stack-stop-H2-705b17c1a1.log`、`05-t3-stack-stop-H2-705b17c1a1.log`、`ct108-t4-stack-stop-H2-705b17c1a1.log`。

### step 唤醒间隔

从各档只读 control DB `step_records.started_at_us/completed_at_us` 按每个 operation 计算前一步完成至下一步开始间隔；Preview、Submit、History 共 6 个 operation、18 个成功 step、12 个间隔/档。最大间隔：t1 0.039s、t2 0.207s、t3 0.416s、t4 0.696s；均没有超过 1s 的间隔，也没有接近 10s heartbeat 的等待，因此无逐项 >1s 需说明。证据：`05-step-gaps-verify-final-H2-705b17.log`、`ct108-step-gaps-final-H2-705b17.log`。

### 显式键与 BROWSE_ONLY 核对

- t1–t4 每档的 11 张显式键表都按 Contract 列配置，表级投影无失败/降级；重复键/NULL 停止项未触发。只列非空表的行数与比较结果：
  - t1：`comm_user_data` 1 行 unchanged；`forwardtbl_lst_yx` 1 行 unchanged。
  - t2：`comm_user_data` 1 行；`forwardtbl_lst_yc/yk/yt/yx` 各 1 行；均 unchanged。
  - t3：`comm_user_data` 是 1 行整表新增；`forwardtbl_lst_yc/yk/yt/yx` 各 1 行 unchanged。
  - t4：`comm_user_data` 1 行、`mms_rp_cdc_index` 42 行、`forwardtbl_lst_yc` 2 行、`forwardtbl_lst_yk/yt` 各 1 行、`forwardtbl_lst_yx` 2 行；均 unchanged；`forwardtbl_lst_cs/dz/qt/ym` 与 `out_time_cfg` 为空。
- 新增 17 张 BROWSE_ONLY 出现时均无 compare key、无 risk annotation：t1 10 unchanged/7 absent；t2 11/6；t3 12/5；t4 15/2。t4 absent 为 `iec101_cfg`、`iec104gw_cfg`。完整逐档名单和计数日志：CT05 `05-realdata-surface-audit-final-H2-705b17.log`，CT108 `ct108-realdata-surface-audit-final-H2-705b17.log`。
- 整表浏览与风险：t1、t4 无整表新增/删除。t2 有 11 个 `TABLE_ADDED`（共 337 行；`b1_n11_iec104_cfg` 337 行，其余 10 表为 0 行）和 11 个 `TABLE_DELETED`（共 5563 行；非空表为 `b1_n5_iec104_cfg` 337、`b1_n5_iec104_syk_list` 91、`b1_n5_iec104_syx_list` 4609、`b1_n5_iec104_yc_list` 525、`b1_n5_iec104_yt_list` 1 行）。每张表各一条 TABLE_ADDED/TABLE_DELETED 风险 annotation，表级 row count 可见。t3 `comm_user_data` 1 行整表新增，1 条 TABLE_ADDED annotation。没有将整表变化伪装成逐行 records。
- t3 v2 Preview 的 193 张表中，33 张为 `COLUMNS_ADDED`；没有 SCHEMA_CHANGE 风险、degraded 或 failed 表。v1/v2 Submit 都有 repository commit ID，继续生成版本。核对日志：`05-t3-schema-audit-final-H2-705b17.log`。

### parser 真实输入检查

- JSON count-only 扫描覆盖 t1–t4 的 v1/v2 共 8 份 SQL 输入；每份 `json_value_count=0`、最大深度 0、深度分布 `{}`，扫描 exit 0。因此远低于 100 层上限。日志：`05-json-depth-final-H2-705b17.log`、`ct108-json-depth-final-H2-705b17.log`。
- V6 parser report 与 DC62 既有 census 记载 t1–t4 无 DC62 §2 P 语义受影响值；S1b 全量旅程成功解析。没有发现受影响值或触发停止条件。新增接受写法由 synthetic round-trip 与 table-access/shared-kernel goldens 覆盖。

### Export cache 与 upload 行为

- backend 权威测试覆盖同 layout 重复导出读取受保护 Parquet row file；不同 row layout、ENUM/SET label、writer contract version 不误命中；TTL 到期解除保护。权威测试：`test_repeated_parquet_export_uses_the_protected_cached_row_file`、`test_export_cache_is_exact_by_repository_and_row_layout`、`test_row_layout_cache_identity_includes_enum_labels`、`test_export_cache_writer_version_is_part_of_the_exact_key`、`test_export_cache_expiry_releases_cache_protection`。V runner backend passed；H backend 两批均通过。真实旅程重复 v1 Preview 均为 0 changed rows。
- 上传合成测试覆盖低速流在大小推导总预算内成功、IDLE 超时映射 HTTP 408 与原因、TOTAL 超时原因；`UPLOAD_STREAM_TIMEOUT` 与 413 语义由 HTTP golden/Contract 覆盖。对应测试：`test_low_rate_stream_within_size_derived_total_budget_is_accepted`、`test_idle_stream_timeout_maps_to_http_408_with_reason`、`test_total_stream_timeout_has_total_reason`；H backend runner passed。

## S1b synthetic load

生成器与规则位于 `vnext/backend/benchmarks/p6_s1b_synthetic_load.py`、`p6_s1b_measurement_runbook.md`，输出只含表名、计数和耗时；真实数据与合成 SQL 均在 Git 外。

- 2× t4 SQL：153,875,448 bytes，临时路径 `/home/dev/gdds-p6-logs/s1b/ct108-synthetic-load-80ce756619/t4-2x.sql`。
- W4 10%：319 tables；baseline/current rows 436,714/436,869；insert/delete/update 14,674/14,519/14,722；737.931s。
- W4 100% stress：319 tables；同一 row totals；insert/delete/update 145,675/145,520/145,674；726.647s。仅作为压力档报告，不设验收门槛。

## t4 性能对照与限制

t4 H 的 API stage timings：v1 Preview 804.293s、v1 Submit 557.812s、repeat Preview 693.751s、v2 Preview 846.541s、v2 Submit 271.849s、History 744.135s。S1a handoff 对照为 1546.088、579.863、872.580、1007.306、289.942、312.889s；不设性能门槛。

H 的 control DB step 聚合：v1 `materialize_inputs` 734.016s / `assemble_preview` 67.750s / `publish_preview` 0.762s；repeat 616.207 / 74.403 / 0.305s；v2 730.656 / 112.944 / 0.382s；History 595.122 / 146.011 / 0.029s。S1a 的内部 checkpoint-read v1/v2 为 45.110/58.656s，bundle v1/v2 为 51.393/2.442s。

H 现有 worker step 只输出 `materialize_inputs` 与 assemble/publish 聚合，没有独立 checkpoint-read 与 bundle 子段计时；不能把上述 aggregate 当成那两个 S1a 子段的同口径新值。v1 assemble aggregate 明显短于 S1a 的 723.046s worker assembly aggregate；v2 为 112.944s，对照 S1a worker assembly 111.196s，差 1.748s。精确的 checkpoint/bundle 子段差额本阶段无法从现有信号隔离；依 DC62 不增加产品计时插桩，保留为 S2b/owner 可复核的测量限制。

## 偏差、停止条件与清理

- 操作性恢复：第一次读取候选 bundle 时在 Git repo 外运行 `git bundle verify`，因缺少 repository 参数退出 1；改在 CT04 `04-wt` 校验与 fetch 成功。第一次 Cargo 版本探针从 repo 根目录运行，rustup 未读取 `vnext/rust/rust-toolchain.toml`；在 `vnext/rust` 目录复核到预装 1.97.0、rustfmt/clippy 与 crate cache。没有运行失败的测试或代码修改。
- S1b golden 仅在 §4.6/DC56 批准项内变化；t1–t4 显式键、BROWSE_ONLY、schema evolution、HTTP 上传和 parser 项均未发现设计冲突；无 JSON 深度/受影响值停止项；最终 authority/package runner 无失败后停止。
- H 的 package runner 与 postcheck 均 exit 0；S1b 已要求的 runner 与真实数据验收均通过。未触发设计 §17 或执行计划 §7 停止条件。
- 未清理任何 ref、worktree、bundle、Docker image/volume 或真实数据 scratch。交 owner 在独立审核与 exit 合入后清理：实施 worktree `/home/dev/gdds-p6-logs/s1b/impl-wt`；CT04 `/home/dev/gdds-p6-logs/s1b/04-wt` 与 `04-cache`；CT05 `/home/dev/gdds-p6-logs/s1b/05-wt`；CT108 `/home/dev/gdds-p6-logs/s1b/ct108-wt`；候选 bundles 与 `/home/dev/gdds-p6-logs/s1b/` 阶段日志/manifest/cache；本机 cache `/home/dev/gdds-p6-logs/s1b/dev-cache` 及 HTTP service PID/log；CT05 Docker volumes `gateway-s1b-final-t1-705b17_*`、`gateway-s1b-final-t2-705b17_*`、`gateway-s1b-final-t3-705b17_*`；CT108 `gateway-s1b-t4-705b17_*`；t1–t4 真实数据 state/artifact volumes 与 2×t4/W4 scratch。旅程 stack 已停止，volume 均按要求保留。
