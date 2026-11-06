# S2b E 独立审核

状态：**审核进行中；不是 E GO 或 S2b exit**。本节按 DC86 新建独立审核角色，模型 GPT-6.1-Sol/max。只修改本审核文档，不修改产品或测试；明确小问题直接交实施者修正后复审，真实设计/验收冲突交设计协调者。无新增角色、推送或改写被引用提交。

## 范围与固定基线

审核起点为 clean main `16e1089a8659f87b0c6585543174c6722f876d86`。CT201 审核 detached worktree `/home/dev/gdds-test-tmp/s2b-e-review` 固定该 SHA，已建 `legacy` 链接；只读源码与证据，不在开发机运行测试、编译或 lint。每组仅在实施者给出固定已提交候选后更新审核 worktree。

最终累计审核范围为 `p6-s2a-exit`（`53b676a6298d408ccda3a85ee73c7ea223a2311a`）至最终候选。复用 A–D 各独立交付及其准确证据范围，E 审实际差异和最终证据：A 产品 `db7767ffbb` / 审核 `83b927207a`；B 产品 `b820321c1e` / 审核 `0dc93c09a9`；C 产品 `0048040af5` / handoff `7cd2b548c8` / 审核 `e9bef6efe8`；D 产品 `93678f8439ec1393d496182f16ae5049b220242f` / handoff `abfe7cb66b` / 审核 `78411aa40b`。D 至本起点的 `vnext/` 无差异，不把 D 的 06 focused 组合、局部 materialize 校准或失败 runner 内单项通过升级为 04 权威来源。

已读 AGENTS、Testing Conventions、比例化保障政策、ADR0012、DC70/72/76–88、执行计划、S2b 总 kickoff、E kickoff、mapping 与 D handoff/review。核心边界遵循当前 owning Contract；A 表示能力不扩大 B 业务白名单，同 euid 仍为既定单一信任域。

## 一次性审核矩阵

| 维度 | 核对范围与实际后果 | 最小验证与 owner |
| --- | --- | --- |
| 真实消费者与唯一批量路径 | 上传 FULL 两侧、Preview baseline、History exact commit、RepositoryRef 两 policy、pair/identity/ordered、export/replay、Submit T1/PREPARED，以及 `real_dump_journey → real_dump_census` 和仍继续使用的工具入口；残留旧 caller 会在删除后失效或形成双路径 | 按实际 import/call graph，固定组做原应用/capability owner focused；删除六个旧 parser 模块及六条 temporary UNREACHABLE，清旧 bulk materialize/projection/hash、仅服务旧算法的 helper/mock/probe；不新增假 import 或 baseline |
| 独立语义预期 | mapping bytes、业务摘要、诊断、结构过滤、keyed/keyless/ordered 预期不能随新 actual 自证 | 保既有 Contract/golden/已验证旧值和 Shared Kernel vectors；删除旧 oracle 前把必要动态预期固定。metadata/选表/恢复策略的合法 fixture 可用真实 Rust/C 构造，但不称为 hash 独立证明，也不为每个 fixture 再建 oracle |
| 保留职责 | 误删仍用 Python IO/规则/编排或外部格式会破坏真实业务消费者 | 保 XML/AST/composite、rules、small metadata/digest、MutationPlanning row-image 摘要、raw/client Parquet、SourcePackage、通用 row reader/DTO；每项按真实 caller 判断，不整文件盲删 |
| 冻结、恢复与资源控制 | E 差异不能破坏 exact commit、scope、内容身份、T1/PREPARED、StartArchive Head CAS、强引用/TTL；控制误分类或漏预算可污染 durable 状态或导致真实业务失败 | 复用 A–D 已验证 owning tests，只复核 E 差异；DC87 保 12 GiB/4 GiB reserve/显式 M8 GiB、N1/单 active；DC88 仅真实 PURE、effect 前、fresh lease/drain，保 checkpoint/保护/attempt/operator，cancel 优先、失租禁写 |
| 最终证据 | 不合格来源、旧 image 或局部旅程不能绑定最终候选 | 06 focused/Contract/五包静态及适用 Rust；04 最终权威 Rust 必覆盖，其他按同节点同 WT 的合格实际 V/逐包闭包判 run/carried；最终 image 当前重建或严格同 04 同 WT 等价。05 t1–t3、CT108 t4 既定 `real_dump_journey --scope full`，不以 capacity 或性能延期替代 |

必要节点窗口由设计协调者负责。当前 CT108 未确认不阻碍源码/06 工作；最终必需证据仍未完成前不签 GO。所有测试节点沿离线缓存、clean committed WT、有效原子占用与日志规则；本审核默认只读实施者日志、manifest、source，不争抢其占用。

## 删除前预期固定核对

实施者外置脚本 `/tmp/s2b-e-freeze-reference.py` SHA `d97e8c9e36337bacdf506bf7e21f6e2d3912fea1f04589c0980e984cea3e0b60` 已只读核。typed SET/f32、wide 200×100、dropped JSON 三份 SQL 与起点 `test_business_kernel_native.py` 的既有用例一致。脚本仅调用旧 test helper 的 SQL materialize 与旧 canonical projection，采旧 raw/canonical 摘要，不调用新 Rust actual，不保采集器为长期 oracle。

06 `gw-dms-06` 的 `19:04:58–19:05:00Z` 实际起止 clean HEAD 均为 `16e1089a86`，lock-check 与 treechecker（`137d499975f3c104ae9c3268b9e12befb2817ba1`）通过，exit0。日志 `/home/dev/gdds-test-tmp/logs/s2b-e-freeze-reference-16e1089a86.log` SHA `4fe7de2ddf4cea018d86107bb46043436171d70f8889832993f58f0031e699af` 已独立读取并重算吻合。typed raw/canonical 同为 `sha256:f57c8813f99f9226ae5c0970e6619e801cbb013d6d20d7dd32fcba87ee4f7f71`；wide raw/canonical 同为 `sha256:c947ad6fccb65c36c067d38a761ca1049e0122c5f926413ba9f7c09e5dcc603a`；dropped raw `sha256:02fbd36483695eaf632a39a2d83877441b074c7587dd745d579cff4355c8aefd`、canonical `sha256:232a96c506247080963b4d39390ac5bf686238c8fb2edf0febcbdbeb0ae91905`。这只固定既有旧语义；新路径仍须实际对这些固定值验证。

## 当前容器记录

Current reviewed HEAD: `16e1089a8659f87b0c6585543174c6722f876d86`（E 代码前基线）。本报告仅文档，不触发本轮重建。最后实际必要容器边界为 D 的产品 `93678f8439`，06 同候选离线 build 的 backend HTTP 1 PASS 加同 image 后续 worker-only ready/12 GiB cgroup/正常 stop0；原容器整组 FAIL 与 CLI 前置失败保留。RS source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`、build-input revision `c52e9fad62e14b016ed814d0799e08e6d97e82b3`，详 D handoff/review。

本基线不宣称正式 carried 或 E 当前容器门禁通过。阶段最终候选必在 04 绑定合格权威/container 证据，04 WT 保留至 stage exit 合入；E 产品差异收敛后再精确记录是否触发重建及来源。

## 未决与结论

尚无已确认 E 产品 Finding。旧消费者删除与独立预期移交、E focused、最终 04 及 t1–t4 证据均待固定候选交付；不将待完成事项写成通过。W1/W2 按 DC84/DC83 后续复核，W3 自 S3，原 W4 lease 故障仍 OPEN；未知性能不记 PASS，不接管原基准冻结资源。
