# P5 架构收口 S3 STOP handoff（owner 决议后的继续取证）

- 状态：**STOP。S3 代码与 V runner 已完成；真实数据链路未完成，不是 S3 exit 候选。不交 exit 审核、不打 tag、不合并 main、不推送、不开始 S4。**
- 日期：2026-10-17
- 分支 / worktree：p5-s3 / /home/dev/gdds-p5-s3
- range_start：p5-g11b-exit，944982eb910dab9cbfc117a976dea6721cdd6ca2
- kickoff base：be5fd5a9708ebb8a4d3ffb619f58ab75819c3576
- range_start..kickoff base 中仅有审核方合并提交 e8b5322b3c3af8d832080fbbc98255ee52daf80c 和文档提交 be5fd5a9708ebb8a4d3ffb619f58ab75819c3576。
- 实现 HEAD = V：f73deee604a90004ad491c0d8a44e8227240448f；clean V 的权威 runner 通过。
- H：无。真实数据在 t4 v1 Submit 停止；本文的后续文档提交只保存 STOP 证据，不是 H 或退出候选。
- owner 决议位于 main 提交 7c77b5e8c8；本分支未合并 main、不 rebase、不打 tag、不推送。V 后只改本 handoff。

## 1. 停止与恢复

早期 STOP handoff 72bdb6a9ee 因逐表 Preview 公开接口要求超出 S3 验收而停止。当时 PreviewResultResponse 没有逐表状态；bundle 路由只返回 artifact 引用，没有公开 surface 下载接口。已有 Compose helper 是容器内读 LocalArtifactStore，不能代替要求中的主机公开 HTTP 证据。早期 handoff 因此请求 owner 决定新增接口或调整验收；当时没有启动真实数据、最终 runner 或 carried。owner 在 main 的 7c77b5e8c8 作出决议并恢复 S3：

1. 不新增 Backend 公开接口；撤销逐表 Preview 状态对照要求。
2. 真实数据证据改为 Preview 汇总、公开 RS Catalog 汇总、History record_count 和离线 composite 比较。
3. 恢复 test_comparison_canonical_domain.py 的原不变量与测试名。同内容上传与 Repository 基线全表 UNCHANGED、没有记录；夹具经生产业务物化与规范投影创建零行 composite_signal_point，不改生产代码。

S3 代码实现、focused 验证与 V runner 已完成。t1–t3 真实旅程通过；t4 离线 composite 比较、INITIAL 空提交、v1 Preview 通过。随后 t4 v1 Submit 的公开 operation-status 查询返回 HTTP 500 INTERNAL_ERROR，worker 仍在心跳，未留下操作终态证据。按停止规则不继续 t4，不补计数、不重跑真实数据；等待 owner 处理。

## 2. 子步与提交

| S3 子步 | 提交 | 结果 |
| --- | --- | --- |
| DC20：source_table 改 VARCHAR(64) 并校验长度 | f5aa52a39d | 超长沿用 COMPOSITE_LOGIC_FAILED；未改 composite contract。 |
| Preview 业务物化与 XML / EMPTY 来源摘要；DC8 诊断 | 280bb1034d、6afdbc5de6 | 缺失 XML 用稳定 EMPTY；无效 XML 或 composite 不变量失败沿用 P3-R3 diagnostic。 |
| composite 投影、身份与规则事实测试 | 4744b5c5e0 | 未重复实施 S2a 的 registry 规则。 |
| composite canonical golden | 59f204f7f5 | 规范类型、键、列见 §6。 |
| 已有 serial History Compose 扩展 | 9f7af5fd13 至 a61419dc31 | 同一栈完成 XML-only 公式变化、Preview、Submit、Repository、History；不加 parallel_safe、不新增独立栈。 |
| 删除 S3 的 8 个不可达基线项 | d93c76e8f4、48e8f190b5、6a1e002033 | import_rules 预期不可达由 14 降至 6。 |
| 恢复 canonical compare 与生产基线夹具 | 3e01baff21、e988763393 为中间尝试；34baca070c 为最终修正 | 断言恢复为同内容全表 UNCHANGED、零记录；fixture 通过生产路径生成 composite 零行表。 |
| 真实数据 composite 离线比较与计数 | 62cca24b99 | 复用 census 的物化、投影与生产比较能力，只输出计数。 |
| 修正空 composite 的 Catalog exact-set expectation | f73deee604 | 此后最终 V full runner 通过。 |
| 早期 STOP 记录 | 72bdb6a9ee | 历史停止原因与 owner 决议见 §1。 |

range_start..V 其他提交均为 S3 实施和调试收敛提交；V 后没有 benchmark、测试或生产代码提交。

## 3. 路径预算与偏差

预算内生产路径为 application/preview_jobs.py、capabilities/snapshot_materialization/compose.py；S3 所有者测试、既有 History Compose、architecture_baseline.py；真实数据 benchmark 与 tests/test_real_dump 文件。

| 额外路径 | 原因 |
| --- | --- |
| vnext/backend/tests/support/preview_job_harness.py | owner 明确要求 Repository fixture 使用生产业务物化与规范投影。 |
| vnext/backend/tests/test_architecture.py | 删除不可达项后同步 synthetic facade probe；没有 import 规则豁免。 |
| vnext/backend/tests/support/upload_http_packages.py、compose_gate_harness.py | 让现有上传与 Compose harness 携带 logics.xml，复用同一 serial stack。 |
| vnext/backend/tests/test_submit_compose_e2e.py | 更新 Catalog 精确表集合期望以包含业务派生 composite_signal_point。 |
| vnext/backend/benchmarks/real_dump_census.py、real_dump_journey.py，tests/test_real_dump_census.py、test_real_dump_journey.py | 按 owner 恢复后的聚合核对增加只读计数与验证；属于 §8.9 允许路径。 |
| 本 handoff | 记录停止与恢复。 |

未启用 capabilities/composite_signal/contracts.py；snapshot_materialization 是派生表 schema owner，未发现需要改 composite 契约的条件。未改 Repository Service Contract、wire、HTTP DTO、Dockerfile、Compose 文件、依赖或 uv.lock。

## 4. import_rules

命令：cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules

| 时点 | 违例 | 运行时环 | 不可达 |
| --- | ---: | ---: | ---: |
| kickoff base be5fd5a970 | 0 | 0 | 14 |
| V f73deee604 | 0 | 0 | 6 |

删除项为 composite_signal._ast、_bind、_digest、materialize；snapshot_materialization._catalog、compose；table_access._xml_parser、xml。余下 6 项属其他阶段。

## 5. 验收 owner、focused / 静态验证与 V runner

| Owner / 命令 | 结果 |
| --- | --- |
| DC20：test_snapshot_materialization_business.py | 13 passed；键类型、长度校验与 EMPTY 来源。 |
| Preview / DC8：test_preview_job_materialize.py | 9 passed；坏 XML → FAILED 与公开 diagnostic；缺失 XML → EMPTY。 |
| Projection / registry：相关 storage projection 与 table rules unit | 70 passed。 |
| Identity integration：test_canonical_snapshot_identity.py | 1 passed；真实 Repository Service 导入并经 HTTP Arrow 读回 VARCHAR(64) 键列。 |
| canonical compare：test_comparison_canonical_domain.py | 1 passed；两侧同内容，全表 UNCHANGED、零记录。 |
| 五包 Ruff + mypy | shared_kernel、repository_contracts、repository_client、repository_service、backend 全部通过。 |
| 权威 runner V | GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh；V clean，start/end HEAD 相同，exit 0。日志 /home/dev/gdds-p5-closure-s1-gate-logs/s3-v-f73deee6-authoritative.log。 |

静态检查对每个包执行：cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy。mypy 覆盖 shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 476 source files；均无 issue。

G11b 对照：shared_kernel 242、repository_contracts 152、repository_client 154 不变；backend parallel 2,833（基线 2,816，净增 17），backend serial 34 不变；repository_service parallel 1,684 + 1 skipped、serial 205 不变。后端测试增量由 S3 业务/投影/规则/真实数据辅助覆盖构成。runner 包级摘要未提供可靠的参数化按文件分解，本 STOP handoff 不把推算写成实测。62cca24b99 的先前 runner 因 Catalog exact-set 旧期望失败，f73deee604 修正后最终 V full runner exit 0；6a1e002033 的 exit 141 是早期作废运行。

## 6. Golden、digest 与 checkpoint 载荷

- 新 golden：vnext/fixtures/golden/storage-projection/composite-signal/canonical.json。source_table 为 VARCHAR(64)；键为 source_table、point_gid；保留 source_table、point_gid、point_name、formula_digest、formula_ast_json；ignored 为 dev_addr、device_gid、point_payload_json；compare-excluded 为 formula_ast_json、point_name。schema digest sha256:45ab9549945be08b1386620fbc3d2f88f28a6818852dd3dab1628fd34582104c；content digest sha256:369e048b093be7a8ec62de2f1d31648bec77b3b595d660cc1d5ac4d2f1eb73b1；golden SHA-256 1e247286337087123e288a8d7397b896948f7c59933b08ff348426c75e2e8ee1。
- registry 规则由 S2a 396cfa2d28 落地；S3 只通过 test_table_rules_contracts.py 核对。
- snapshot_digest 在 XML 存在时包含 XML 内容摘要，缺失时包含稳定 EMPTY 摘要。规范状态摘要仅覆盖派生表内容；composite_signal_point 规范投影进入存储、比较与风险。
- 公式变化使 formula_digest 改变、该行 MODIFIED；point_name 与 formula_ast_json 为 compare-excluded，不单独改变表状态。Compose serial journey 断言行 MODIFIED 和 History record_count=1。
- checkpoint 未新增字段、envelope 或 materialize-side contract version。已有 composite_logic_source_digest 值包含 XML / EMPTY 来源；materialize_inputs 引用的 snapshot 规范表闭包可包含 composite_signal_point。值及闭包变化是目标形态，DC6 不保留旧兼容路径。
- 真实数据未完成，无法报告最终完整规范摘要、bundle/surface digest；没有从不完整运行推造摘要值。

## 7. V 镜像及 carried

provenance 位于 /home/dev/gdds-p5-closure-s1-gate-logs/s3-v-f73deee6-provenance.json。S3 Compose 旅程触发强制重建，最终 V runner 实际镜像如下。

在 V 上运行 python3 vnext/repository_service/tests/support/build_context_digest.py identity；build-input revision adc5d87fea073545fde6416d123c3d7845e715ff 与 source-tree sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4 均与 provenance RS 镜像两个 label 相等。

| 镜像 | image ID | 记录 |
| --- | --- | --- |
| backend | sha256:764d15b2e02663311613e20fba7775e4324bd4258ae1bfd37a7afcd4e045f3dd | V runner 实际镜像。 |
| worker | sha256:b3190be2134ffbe7a6188c6b094dd3907b06f87eedaf79b5fa3d18846ac83152 | V runner 实际镜像。 |
| repository-service | sha256:c57041fdb85ad759d45e443f35bcbff079d69a522c61e68243d9170e25795fa5 | build-input revision adc5d87fea073545fde6416d123c3d7845e715ff；source-tree sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4；标签与 V identity 一致。 |

carried 未做，因为 STOP、没有有效 H。未在最终 handoff 提交上重算 identity，也未重建 backend/worker。两个禁止触碰的镜像 ID 未变：gateway-repository-client-e2e:local 为 sha256:7883e067020adbdb84f8d7e305218e492f161058b85fa7b74f774acc27811368；gateway-repository-client-e2e-base:local 为 sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764。未删除或重新 tag。

## 8. 真实数据身份与规模

脚本由主机侧 real_dump_journey.py 启动，原始数据只读；使用生产 census、business materialization、规范投影和生产 comparator，通过公开 HTTP 驱动 Preview / Submit / History。下表仅列 dataset ID、package SHA-256、大小与结构统计，不含项目别名、原始路径或行数据。

实际命令为 GATEWAY_REAL_DUMP_ROOT=<host-only configured value> ../scripts/uv-consume.sh -C . run python benchmarks/real_dump_journey.py；变量值仅留在主机日志，不写入 handoff。

| Dataset ID | package SHA-256 | bytes | 源 DDL 表 | census 派生表 | census 行数 | logics.xml |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| rd-t1-a-v1 | 42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2 | 107,115 | 132 | 133 | 6,097 | complete / depth 1 |
| rd-t1-a-v2 | 4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0 | 107,066 | 132 | 133 | 6,095 | complete / depth 1 |
| rd-t2-b-v1 | acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0 | 1,247,459 | 216 | 217 | 97,140 | complete / depth 56 |
| rd-t2-b-v2 | c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98 | 1,197,404 | 216 | 217 | 93,154 | complete / depth 56 |
| rd-t3-c-v1 | c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e | 3,356,815 | 199 | 200 | 268,661 | complete / depth 66 |
| rd-t3-c-v2 | 658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d | 3,370,171 | 200 | 201 | 268,667 | complete / depth 66 |
| rd-t4-d-v1 | 95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675 | 5,597,503 | 319 | 320 | 437,149 | complete / depth 97 |
| rd-t4-d-v2 | 5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611 | 5,596,595 | 319 | 320 | 437,229 | complete / depth 97 |

八份 logics.xml 均 COMPLETE；t1/t2/t3/t4 的 v1/v2 深度依次为 1、1、56、56、66、66、97、97。离线 composite 比较复用 real_dump_census.py 的生产物化、规范投影与比较能力，只输出计数：

| Tier | composite rows v1 → v2 | 状态 | ADDED / REMOVED / MODIFIED | History records |
| --- | ---: | --- | --- | ---: |
| t1 | 4 → 4 | UNCHANGED | 0 / 0 / 0 | 0 |
| t2 | 45 → 45 | UNCHANGED | 0 / 0 / 0 | 0 |
| t3 | 201 → 201 | UNCHANGED | 0 / 0 / 0 | 0 |
| t4 | 435 → 435 | UNCHANGED | 0 / 0 / 0 | 0 |

## 9. 聚合对照、A/B/C 与停止原因

V 上 preflight：2026-10-17 11:47:58Z，nproc=96，loadavg=4.61/6.74/6.53；无 Dolt、无 Compose 栈、8000 端口空闲，docker ps 仅有两个常驻 BuildKit 容器。主机有 next-server 约 3.2% CPU。15:39:19Z 有独立 docker pull，loadavg=5.91/4.90/4.41；15:55:58Z 最近失败前快照为 5.02/5.56/5.25，docker pull 已结束。16:06:53Z 清理后 loadavg=4.07/4.13/4.60、无 Dolt/Compose、8000 空闲。日志在 worktree 外的 s3-realdata preflight、load-monitor 与 postfailure-preflight 文件。CPU quota 未限流，worker cgroup throttling 为 0。

| Tier/version | Preview table_count / changed / degraded / failed | composite rows | Catalog / History | 结果 |
| --- | --- | ---: | --- | --- |
| t1 v1 | 125 / 125 / 0 / 0，S2b + 1 | 4 | Catalog 聚合断言通过 | 通过 |
| t1 repeat v1 | 125 / 0 / 0 / 0 | 4 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t1 v2 | 125 / 4 / 0 / 0 | 4 | Catalog 断言通过；History record_count=12（S2b=12） | 通过 |
| t2 v1 | 209 / 209 / 0 / 0，S2b + 1 | 45 | Catalog 聚合断言通过 | 通过 |
| t2 repeat v1 | 209 / 0 / 0 / 0 | 45 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t2 v2 | 220 / 57 / 0 / 0 | 45 | Catalog 断言通过；History record_count=11,511（S2b=11,511） | 通过 |
| t3 v1 | 192 / 192 / 0 / 0，S2b + 1 | 201 | Catalog 聚合断言通过 | 通过 |
| t3 repeat v1 | 192 / 0 / 0 / 0 | 201 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t3 v2 | 193 / 54 / 0 / 0 | 201 | Catalog 断言通过；History record_count=744（S2b=744） | 通过 |
| t4 v1 | 312 / 312 / 0 / 0；Preview SUCCEEDED | 435 | 没有进入 Submit / Repository Catalog | 部分通过 |
| t4 v1 Submit | 状态查询 HTTP 500 INTERNAL_ERROR | — | worker 仍 heartbeat_succeeded；无终态记录 | STOP |
| t4 repeat / v2 / History | 未运行 | — | Catalog / History 未核对 | 未完成 |

t1–t4 INITIAL 空提交 Catalog 断言均为 0 table / 0 row。t1 的 logics.xml 深度为 1，得到 4 行 composite 表，不是 EMPTY 来源。t1–t3 v1 重传 Preview 全表 UNCHANGED，Submit 返回 NO_CANONICAL_CHANGE，composite 也 UNCHANGED。IEC104 ordered 四项和 DC29 keyless 表约束在完整 t1–t3 journeys 通过；t4 的 repeat / v2 / History 未执行。t1–t3 History record_count 与 S2b 相同；t4 未比较。

### A/B/C 明细

下表按 S2b handoff §8.6 记录每步 wall 与三容器 CPU；括号内为本次减 S2b 的秒数。A 对 operation 表示保护超时内终态，C 表示时间戳和 CPU 采样已写入。t4 v1 Submit 的不完整 elapsed 不与 S2b 成功操作作性能比较。

### t1

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.686 (-0.013) | 0.012 (-0.015) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.692 (-0.010) | 0.017 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 52.963 (-0.026) | 1.493 (-0.002) | 1.316 (+0.007) | 42.128 (+1.143) | A 终态成功；C 已记录 |
| v1-submit | 41.639 (+0.014) | 1.843 (+0.044) | 62.149 (-0.109) | 13.614 (-0.410) | A 终态成功；C 已记录 |
| v1-repository-read | 10.811 (+0.085) | 0.261 (+0.003) | 58.107 (+1.183) | 0.013 (+0.000) | A 不适用；C 已记录 |
| v1-approve | 0.690 (-0.003) | 0.013 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-archive | 0.725 (-0.023) | 0.044 (-0.005) | 0.001 (-0.105) | 0.003 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-workspace | 0.676 (-0.006) | 0.129 (+0.059) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-upload | 0.688 (-0.027) | 0.019 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-preview | 73.075 (-0.011) | 2.099 (+0.036) | 31.518 (+0.423) | 47.603 (+0.513) | A 终态成功；C 已记录 |
| repeat-v1-submit | 0.697 (-0.003) | 0.010 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-workspace | 0.689 (-0.008) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-upload | 0.705 (-0.021) | 0.021 (+0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-preview | 77.104 (-0.009) | 2.233 (+0.013) | 31.627 (+0.182) | 47.679 (+0.048) | A 终态成功；C 已记录 |
| v2-submit | 43.539 (-0.022) | 1.874 (-0.009) | 68.716 (+0.278) | 13.631 (-0.318) | A 终态成功；C 已记录 |
| v2-repository-read | 11.142 (+0.143) | 0.261 (+0.015) | 60.167 (+0.665) | 0.016 (+0.000) | A 不适用；C 已记录 |
| v2-approve | 0.693 (-0.001) | 0.009 (+0.000) | 0.001 (+0.000) | 0.003 (+0.000) | A 不适用；C 已记录 |
| history | 62.963 (-0.008) | 1.748 (+0.017) | 59.917 (+0.209) | 34.371 (-0.595) | A 终态成功；C 已记录 |

### t2

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.683 (-0.017) | 0.071 (+0.030) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.732 (-0.017) | 0.066 (+0.004) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 742.395 (+20.074) | 20.668 (+0.549) | 18.815 (+0.708) | 733.296 (+19.246) | A 终态成功；C 已记录 |
| v1-submit | 237.294 (-1.891) | 7.863 (-0.012) | 116.036 (+0.705) | 202.648 (-1.372) | A 终态成功；C 已记录 |
| v1-repository-read | 27.048 (-0.240) | 0.629 (-0.114) | 117.466 (-0.512) | 0.065 (-0.002) | A 不适用；C 已记录 |
| v1-approve | 0.678 (-0.036) | 0.013 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| v1-archive | 0.703 (-0.023) | 0.042 (+0.001) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| repeat-v1-workspace | 0.654 (-0.052) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-upload | 0.726 (-0.023) | 0.061 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| repeat-v1-preview | 623.827 (+19.939) | 17.705 (+0.711) | 75.356 (+0.182) | 593.528 (+21.892) | A 终态成功；C 已记录 |
| repeat-v1-submit | 0.695 (+0.003) | 0.010 (-0.056) | 0.068 (-0.053) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-workspace | 0.679 (-0.005) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-upload | 0.745 (+0.000) | 0.094 (+0.030) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-preview | 708.216 (+20.173) | 20.037 (+0.837) | 77.443 (+1.157) | 665.864 (+20.497) | A 终态成功；C 已记录 |
| v2-submit | 239.090 (+0.019) | 7.897 (-0.011) | 126.527 (+0.941) | 198.243 (+0.611) | A 终态成功；C 已记录 |
| v2-repository-read | 28.369 (+0.282) | 0.767 (+0.129) | 121.030 (+0.848) | 0.076 (+0.001) | A 不适用；C 已记录 |
| v2-approve | 0.691 (-0.001) | 0.008 (+0.000) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| history | 502.750 (+0.008) | 13.758 (+0.034) | 137.438 (+0.201) | 434.309 (-0.728) | A 终态成功；C 已记录 |

### t3

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.693 (+0.013) | 0.038 (-0.028) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.846 (+0.018) | 0.173 (+0.007) | 0.002 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 1315.151 (+70.303) | 36.980 (+2.131) | 33.233 (+1.827) | 1301.051 (+62.592) | A 终态成功；C 已记录 |
| v1-submit | 484.799 (+5.523) | 15.301 (+0.288) | 121.535 (-0.409) | 443.398 (+4.239) | A 终态成功；C 已记录 |
| v1-repository-read | 24.947 (+0.204) | 0.633 (+0.014) | 102.990 (+1.127) | 0.048 (-0.002) | A 不适用；C 已记录 |
| v1-approve | 0.678 (-0.006) | 0.014 (+0.001) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| v1-archive | 0.716 (-0.001) | 0.044 (+0.002) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| repeat-v1-workspace | 0.669 (-0.018) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-upload | 0.854 (+0.017) | 0.173 (+0.003) | 0.001 (-0.001) | 0.000 (-0.003) | A 不适用；C 已记录 |
| repeat-v1-preview | 1423.743 (+60.275) | 40.527 (+1.732) | 103.271 (+1.170) | 1373.383 (+52.728) | A 终态成功；C 已记录 |
| repeat-v1-submit | 0.659 (-0.037) | 0.011 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-workspace | 0.659 (-0.021) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-upload | 0.844 (+0.000) | 0.181 (+0.004) | 0.001 (-0.001) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-preview | 1588.882 (+60.553) | 45.254 (+2.018) | 108.060 (+2.036) | 1541.536 (+56.531) | A 终态成功；C 已记录 |
| v2-submit | 492.827 (-10.103) | 15.402 (-0.217) | 133.537 (-6.197) | 447.135 (-3.859) | A 终态成功；C 已记录 |
| v2-repository-read | 25.615 (-0.178) | 0.639 (-0.001) | 112.203 (-0.132) | 0.054 (-0.004) | A 不适用；C 已记录 |
| v2-approve | 0.686 (+0.002) | 0.009 (+0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| history | 963.270 (-9.333) | 26.347 (-0.011) | 169.525 (+2.522) | 881.267 (-8.660) | A 终态成功；C 已记录 |

### t4

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.685 (+0.009) | 0.117 (+0.057) | 0.002 (+0.001) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.930 (-0.004) | 0.261 (-0.002) | 0.002 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 2649.893 (+82.452) | 74.207 (+1.657) | 66.947 (+2.141) | 0.945† invalid | A 终态成功；C 记录；worker CPU 失真† |
| v1-submit | 594.828 partial; no comparison | 18.578 | 15.150 | 587.885‡ | A 未证明：HTTP 500；C 记录失败 |

† t4 v1 Preview 在 15:08:24.613Z 开始，公开 operation 于 15:52:33.763Z 为 SUCCEEDED，operation wall 2,649.150s，step wall 2,649.893s。结束前 worker heartbeat 路径抛 StaleWrite，旧 worker 容器于 15:52:29Z 重启；step 结束时 worker cpu.stat 读到新容器，日志 0.945s 不代表本 operation CPU，不作比较。运行期间反复观察 worker 约 99.5–99.7% 单核占用，仅说明该步单核计算，不是精确 CPU 值。backend 74.207s、Repository Service 66.947s，各容器 throttling=0。wall 比 S2b 2,567.441s 多 82.452s（3.2%）；t2 / t3 Preview 分别多约 20s / 60s。新增 Preview 工作随 composite 物化与投影路径出现，记录为 composite 增量；不把它推断为更广泛的结构原因。

‡ t4 v1 Submit 的保护 timeout 为 4,047s；step 于 16:02:28.987Z 在 594.828s 时失败。wall / backend CPU / RS CPU / worker CPU 为 594.828 / 18.578 / 15.150 / 587.885s，throttling=0。公开 GET operation status 返回 HTTP 500 code INTERNAL_ERROR。worker 于 16:02:29.604Z 仍成功 heartbeat，随后脚本按失败路径 teardown。operation 未留下终态记录，故 A 层不通过或无法证明；不是可与完整 S2b Submit 比较的耗时。

该真实旅程起止 HEAD 均为 V，worktree clean，realdata exit code 1；日志 /home/dev/gdds-p5-closure-s1-gate-logs/s3-realdata-v-f73deee6-journey.log。只运行本次一次，没有全流程重跑或手工补接口。缺少 t4 Submit 终态、Catalog、repeat-v1、v2 Preview/Submit、History 与最终 digests。

## 10. 失败、停止条件与后续

- 触发停止：t4 v1 Submit 公开状态请求 HTTP 500 INTERNAL_ERROR；失败时没有操作终态证据。旅程未覆盖 t4 后续，A/B/C 与 §2 全流程验收不完整。
- 已测部分中，八份 XML census 均 COMPLETE，表名长度没有超限；t1–t3 与 t4 v1 Preview 的 Preview degraded/failed 均为 0。未完成部分不能判作全阶段通过。
- 失败附近主机 loadavg 约 5/96，worker 约单核占用、cgroup throttling 为 0；已知证据不支持“整机 CPU 资源不足”作为解释。
- 62cca24b99 的一次 runner 因 Catalog exact-set 旧期望失败，f73deee604 修复后 V runner 通过。6a1e002033 的 runner exit 141 是先前 STOP 阶段的作废运行。dirty-worktree Compose 调试同样不作为证据。
- 没有完成 H、carried、独立 S3 exit 审核；没有 S3 tag 或 main 合并。
- 请 owner 处理公开 operation-status 的 INTERNAL_ERROR，并决定下一步。如果需要修改生产代码，依 §8.9 收敛后创建新 V，再各完整运行一次权威 runner 与真实数据。不得通过放宽统计或兼容特判关闭本 STOP。

## 11. 审阅重点

1. owner 7c77b5e8c8 的三项决议是否落实，尤其 canonical compare 原不变量和生产路径 fixture。
2. DC20、DC8、规则投影、golden、checkpoint 变化与路径预算。
3. V full runner、包计数、RS identity 标签和 client e2e 镜像 ID。
4. t1–t3 聚合与离线 composite 证据；t4 v1 Preview 与 Submit HTTP 500 的失败路径及同期资源证据。
5. t4 没有 Submit terminal、Catalog、repeat、v2、History、H、carried；不得批准 S3 exit。

## 12. 审核提示词（STOP 记录，不是 exit 审核）

任务：独立审阅 P5 架构收口 S3 STOP handoff。你没有参与 S3 实施；按 docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。本记录不是 S3 exit 候选，不得据此打 p5-s3-exit 或进入 S4。

审核对象：没有 H；实现 HEAD 与 V 为 f73deee604a90004ad491c0d8a44e8227240448f；STOP handoff 是本文档提交；区间起点 p5-g11b-exit = 944982eb910dab9cbfc117a976dea6721cdd6ca2。只审该区间和停止证据。
审核 worktree：只读 detached worktree；先创建 legacy 符号链接。不在主工作区运行测试或写入。

权威依据：执行计划 §2 S3、§3 S3、§4、§6、§7、§8.1、§8.2、§8.7、§8.9；设计 §8、§4.4、§4.6、§12、§14；DC4、DC8、DC20、DC22、DC30、DC31；main 上 owner 决议 7c77b5e8c8；Contract logics.xml 条款；S2b handoff §8.5、§8.6、§8.9。

必须核查：
- S3 production / tests / golden / checkpoint 与路径预算，尤其 test_comparison_canonical_domain.py 是否恢复全表 UNCHANGED 且生产 fixture 含零行 composite 表。
- 8 个 unreachable modules 与 import_rules 0/0/14 → 0/0/6。
- V f73deee604 runner clean / exit 0、包计数、provenance RS labels 与保护镜像 ID。
- t1–t3 聚合证据、t4 offline composite 与 v1 Preview；t4 v1 Submit HTTP 500 INTERNAL_ERROR、失败时限、heartbeat 和负载。
- 确认 STOP 结论正确：Submit 未有终态证据，t4 Catalog / repeat / v2 / History、最终 H 与 carried 均缺失；不能批准 S3 exit。
