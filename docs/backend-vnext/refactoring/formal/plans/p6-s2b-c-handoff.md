# S2b C 交付：规范 IPC store、引用与恢复

状态：产品固定 `0048040af59214bf1113c820396ac4b306befe31`，实施与本节验证完成，交本节独立审核者签 GO。Owner 已选容量 A（12 GiB envelope、4 GiB reserve、显式 M=8 GiB/上限 8 GiB、N=1/单 active）；D 仍须完成接线与实际资源验收，本交付不声明 worker capacity PASS。没有推送、tag 或改写引用提交。

前置 B 产品 `b820321c1eef78be4430c9a3f5b51d22188f4e0b`、B handoff `ac59ffeb79`、独立审核 `0dc93c09a9`；A 产品 `db7767ffbb`。本节不重做 A/B。边界与容量分别见 [C 任务](p6-s2b-c-kickoff.md)、[容量报告](p6-s2b-c-capacity-calibration.md)、[独立审核](p6-s2b-c-review.md)。

## 1. 产品与实际消费者

- `artifacts/canonical_table_store.py`：scope 内五项内容身份（projection version、含 table name 的 business schema digest、row count、table digest、mapping version），返回标准最小 `ArtifactRef`。不以 raw SHA 代替业务摘要；外层保留 DDL/export 列序。
- `snapshot_materialization/canonical_store.py`：`CanonicalTableStore.put/open` 与 context-managed `ArtifactReadHandle`。写入只调用 A 唯一 Rust codec；没有 Python writer、引擎开关或生产 fallback。reader 按绑定列名恢复外层顺序，同 ref 独立 open，close 幂等、closed read 稳定失败，borrowed C Stream 先于 reader/source/mapping 释放。
- `LocalArtifactStore.open_buffer`：真实只读 fd/mmap，在同一 mapping 上分块校 size/raw SHA；保留 root 内解析边界并拒绝 symlink/非普通文件。内存 store 用 Arrow BufferReader 遵循同一 handle。原通用 `locate(ref)->bytes` 保留给 raw Snapshot/manifest、bundle、Repository import/export 等真实消费者。
- A core 的 `inspect_v1` 复用同一 raw footer/block/schema/metadata/profile preflight；adapter 仅用 safe Arrow C Stream 的单元素 LargeBinary 借用已有 buffer，不复制整份 IPC，不接 path/IO/unsafe。随后标准 PyArrow reader 仍用原 mapping。该 inspect 不替代 A decoder 的完整映射值检查，也不是外来 IPC 业务导入 validator。
- `SQLiteCanonicalTableCache` 复用既有 protection/UoW，直接修改唯一 baseline schema，增加 derived cache/commit 索引及 expiry/FK 标准索引。lookup 在 writable transaction 中先 touch 保护再检查文件；过期条目不命中；有强引用的 head/Attempt 不按 TTL 失效。generic artifact 保留规则不因 canonical cache 改变。
- `SQLiteArtifactProtectionStore` 的现有 set/clear owner 接口仅对已登记 canonical ref 衔接强引用与最后释放 TTL。T1 的现有顺序仍为先 set Attempt、再 clear Preview；终态 finalize/abort 沿同一 clear owner 触达 TTL。
- `SQLiteBaselineRepository.save_initial_node_and_head/save_archived_node_and_cas_head` 实际调用 head 引用移交。**Archive Head CAS、归档结果与引用同事务**；没有文件读取、物化或 Repository import。Submit finalize 不推进业务 Head。exact-commit backfill 登记时比较当下业务 head，只为当前 head 增长期 owner，历史 commit 保留 TTL。
- `CanonicalCommittedTableAccess.open_committed` 与真实 `HttpArrowRepositoryRefSession.open_arrow_table_reader`：健康缓存命中不重写；miss/corruption 只读指定 immutable commit，检查返回 catalog 的 commit/scope/schema/count，经 B `canonicalized_input=True` 重核业务 digest，再 A/store 回填。写前短事务保护/绑定结束后才写文件，不将长 IO 放进 SQLite。网络/I/O 沿旧 adapter 的脱敏 retryable 分类；资源错误保留资源拒绝。
- 实际 Repository wire 以标准 Arrow 列 kernel 桥接现有 canonical 白名单：窄整数拓宽、SET list→文本、civil DATETIME(us, no timezone)→规范文本。SET visible member 不可 NULL，NULL/空列表分开；DATETIME 不作时区转换。声明/成员顺序/业务值/摘要仍归 B/Shared Kernel，不扩 DATE/TIMESTAMP/DECIMAL 等没有本节 canonical consumer 的矩阵。

local writer 复用已有 temp/fsync/rename，C 新路径不做写后整文件读回；实际 reader 的核验保留。普通 I/O、协作并发、root/symlink 与 crash 继续按 ADR 0012，不新增 broker/helper/持久 evidence 状态机或同 euid 敌手换名证明。

## 2. C 与 D 的真实分界

C 交付了真实 B/A/store 闭环、SQLite/UoW/Archive/终态释放 hook，以及生产 HTTP adapter 的受约束 exact-commit 恢复能力；HTTP 取证测试使用真实 client/session 路径与符合 Repository wire 的 int16、list<utf8>、timestamp(us) fixtures，通过 MockTransport 提供响应，不冒称 live Repository/operation 端到端。

生产 Preview `_materialize_uploaded_side`、History、Submit closure/import-replay/export 的完整 IPC 路由仍在 D；现行生产 Python/Parquet 路径仍有真实 consumer，不在 C 盲删，也不是 C 新建兼容双读。C 新 committed reader 与 frozen reader 分开：冻结 ref 只 `store.open`，没有调用 committed source 的分支。

四种恢复边界保持：T1 前上传丢失要求重新 Preview；T1 后、PREPARED 前冻结缺损稳定失败，不换 parent/source/ruleset、不前移 main；PREPARED 复用冻结 import package/raw SHA；已提交派生副本只从 exact commit 校验回填。C focused 沿既有 Submit prepare/recovery owner 验证现有屏障；新的 production operation IPC 路由和 actual cancel/drain/lease/deadline 由 D 接线复核。

Python architecture guard 依据正式 Rust policy v4 §4（`f690e22aef`）只允许三个精确模块/五个已批准 native 函数，不给全部 capability 开放 compute，不增 IMPORT/cycle baseline。暂不可达仅列已批五项：application `canonical_metadata.table_access`，capability `snapshot_materialization.canonical_store/native/repository_arrow` 与 `storage_projection.native`；每项实际 D consumer/删除点见 C 任务。D 真实接线后删这些 entries，不能留到 S2b exit，也不靠假 import 使其可达。

## 3. 不变量与证据 owner

| 不变量 | 唯一主要 owner/证据 |
| --- | --- |
| IPC profile/绑定/raw SHA、独立 reopen/close、真实 B 借用、外层列序、symlink/预算拒绝 | `test_canonical_table_store.py`；A 原 profile/值向量保持原 owner |
| atomic staging/普通 I/O 失败与清理 | 原 `test_artifact_staging_conformance.py` / `test_workspace_artifact_store.py`，没有复制 syscall 矩阵 |
| 共享 strong、最后释放 TTL、过期 lookup、readonly 诊断 | `test_canonical_table_cache.py` |
| 真 T1 转移、finalize/abort 释放、不移动业务 Head | 原 `test_submit_transactions.py` 相应测试增加 canonical refs 断言 |
| Archive CAS/结果/正式引用晚期失败回滚、合法 replay 不重复修改 | 原 `test_archive_transactions.py` 同一 owner 扩断言，故意没有实际文件也可归档 |
| initial/current head 与历史 exact commit 的 owner | `test_canonical_table_cache.py` 与 SQLite 实际 participant |
| exact commit HTTP/wire/B/A/store、健康 hit 免写、corruption 回填、错 digest/commit、network/budget 失败无 temp/ref | `test_canonical_commit_access.py` |
| T1/PREPARED/真实 Dolt recovery | 原 `test_submit_job_prepare.py`、`test_submit_import_builder.py`、`test_submit_recovery.py`、`test_submit_worker.py` |
| 资源拒绝/业务摘要与宽表临时量不累计 | B 原 `test_business_kernel_native.py`；单项 200×100/16 MiB 回归，不重建三层矩阵 |

## 4. 节点、源码与工具链

全部测试/编译/lint/容器/容量执行在 06 `gw-dms-06`，worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-c-impl`，保留 legacy 链接至 `/home/dev/gateway-data-management-system/legacy`。CT201 只编辑/Git/制品准备，未跑产品测试。

本角色先 BatchMode `echo OK`，只读核无占用/运行容器/Dolt后，于 **13:15:33Z** 原子 mkdir `/home/dev/gdds-node-busy.d` 并写 `session=p6-s2b-c-impl`。原获取保存在会话工具输出，未伪造一份该时刻的外置日志；review 曾独立读取原 owner。closeout 将原 owner 原样归档为 `artifacts/s2b-c-0048040af5/node-owner.txt`，SHA `77d22f97170f51f37128f9fbb8767176dc9b0b820cb59029f5f2fb02e81b09ea`。

PATH 以 `/home/dev/.cargo/bin` 开头，不覆盖 RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME；仓库 selector Rust 1.97.0。rustc `1.97.0 (2d8144b78)`、cargo `1.97.0 (c980f4866)`、rustfmt `1.9.0-stable`、clippy `0.1.97` 均解析到 `/root/.rustup/toolchains/1.97.0-x86_64-unknown-linux-gnu/bin/`。初次版本只读检查在会话工具输出，closeout 外置日志再次记录实际 selector/path/version，不能把收尾时刻标成初次时刻。

`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、Cargo jobs 4；focused 的 timing-sensitive/SQLite/Dolt 组 `-n 0`，产品 pool N=1 的校准与 pytest worker 数分开。TMPDIR=/home/dev/gdds-test-tmp，target/log/artifacts 外置；不改 `/tmp/pytest-of-root`、不设置 GATEWAY_TEST_BASETEMP。所有消费走受控 uv wrapper；Rust 改动后强制重装 gateway-compute-python，并检查 installed build input。

源码传输使用本任务经审核的显式脚本：CT201 `/tmp/s2b-c-publish-source.sh` SHA `5e564c3253babe663ef434e82e1a10c489c986a7ca7d1790abc0417c2498a49f`，remote `/home/dev/gdds-test-tmp/s2b-c-sync-source.sh` SHA `20fc50f9db0ead64c28ab4e622bd3c8b1f6606fb81a9b4bdfa05a7d79d793418`。固定 full SHA → `refs/codex/s2b-c-transfer/<fullsha>` → named bundle/advertised ref/SHA/fetch 校验；previous 总是实际 remote HEAD。同步 actual exit0/clean 在独立 tool call 核对后才测试，没有借共享 main 的 HEAD~1，没有要求其他 main 会话暂停。

使用节点本地预填 uv/Cargo/Docker 缓存，无公网/代理、无新锁文件/依赖或预填传输。五个 uv locks、Cargo.lock、selector 与 B 完全一致，closeout 记录逐项 SHA 和 Git diff exit0；依赖 base 的完整输入与身份另见 §6。

## 5. 实际验证（不合并冒称同一 HEAD 全过）

下列相对日志前缀均为 06 `/home/dev/gdds-test-tmp/`。所有结果以外部 SHA 为准，记录 hostname/起止 UTC/HEAD、clean、exit。

| 实际候选 / 范围 | UTC / 结果 | 日志 SHA256 |
| --- | --- | --- |
| `61931ee914` store 首个小步 | 13:28:21–24；backend Ruff/mypy、tree checker、6 PASS | `logs/s2b-c-reader-6193.log` `21a9534ce06a55bb5734bd0faf693d41c9ba8541b2a915ceefc42c7fcc2ece5d` |
| `3e4cb7e156` 引用/原 owner | 13:32:06–23；backend static、store/cache/Archive/protection/Submit 92 PASS | `logs/s2b-c-refs-3e4c.log` `1e4381dab87bc5f0bbd41d3e167028794e2bf142d1103566a6e25a851882f398` |
| `309c511e40` 真实 HTTP/wire/恢复 | 13:44:25–27；backend static、12 PASS | `logs/s2b-c-recovery-309c.log` `4ecda1ea67026a55b8a3b3342fcf478d6dba73fe794923ba2fa5a61133b887d5` |
| `3ae27b98ff` keyed 预约最小修正 | 13:56:27–46；fmt/clippy、强制重装/tree、backend+tool static、50 PASS | `logs/s2b-c-key-3ae2.log` `305e4c53746dc20935324da187fcc141e78c7a8f8009f80420e5f3c37f4dc3d4` |
| `cff2f20b62` 完整 Rust policy 与五包静态 | 14:12:26–14:13:43；fmt/all-target clippy、workspace tests、release build、architecture CLI、强制扩展/tree、五包 Ruff/mypy、两 tools static，全部 exit0 | `logs/s2b-c-final-static-cff2f20b62.log` `9df26b9d60636f6796e07e401df9f7f3915699efaec237e2e939b6d1f7601181` |
| `cff2f20b62` 最终影响面 focused | 14:14:24–59；325 PASS、schema 期望漏列 2 FAIL，**整次 exit1，不是合格整包来源** | `logs/s2b-c-final-focused-cff2f20b62.log` `04bea68a9e00ea295fa0aad615d8145d5acd47ebda1c42297161c3b7c88ca340` |
| `0048040af5` schema 目标清单+HTTP 网络错误分类修复 | 14:20:20–24；五包 Ruff/mypy、tree checker、受影响 schema/HTTP owner 17 PASS | `logs/s2b-c-final-targeted-0048040af5.log` `c3c740d7313d60fe4c09230f1ae0ba039a9022df3b016888a5bf9d6ec63927eb` |
| `0048040af5` 当前离线容器 | 14:23:33–14:24:54；health 1 PASS、worker build、同 health image 的 B/A/store/mmap/TTL smoke PASS | `logs/s2b-c-container-0048040af5.log` `fd50960429337f6c72aebf79bd476cdb8b6a35b3cf1522a0320be82d454b997f` |

cff 的 focused 范围为新 store/cache/HTTP、B/native parser、实际 Python architecture、Archive/并发、schema/provisioned scope、原 staging/FS/Parquet/cache faults，以及 Submit transaction/prepare/import/recovery/worker（含真实 Dolt）共 327 项。其两个失败仅是 EXPECTED_TABLES/INDEXES 未列已批准新增两表两索引；`5c4c2cb003` 四行补齐目标期望。`0048040af5` 再窄修网络错误分类并用同一 budget/network 参数表验证无 temp/ref。按比例化规则定向复验 owner，不重跑已过 325 或任何容量输入。

004 与 cff 的 Rust tree 同为 `d7bbe223f17a155b01ec8b948a7c4fbe51628d05`；host extension checker 实际 installed/expected 相同。Rust 完整命令为 fmt → all-target clippy → workspace test `--test-threads=1` → release build → 独立 architecture CLI，不只 cargo test。没有在 06 跑权威 full runner，不作包 closure carried 或 S2b phase exit 结论。

容量的完整输入/计数/来源/失败/实测与推导见容量报告，不重复搬成第二套数字。

## 6. 当前镜像与依赖身份

本轮新 codec/mmap/HTTP/storage 真实消费者在最终 product HEAD 上重建本机 backend/worker 并跑必要容器验证；不是以旧 image 或跨节点结果冒充当前候选。

CT201 clean worktree `/tmp/s2b-c-dependency-input-cff2` 只运行 dependency-base `--print-input`，14:13:02–11，exit0；完整输入 SHA `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad` 与 B 相同，input JSON SHA `f7df461e1f4b3f3fd45a9fbfb014942fa3dd0d017cc0a95e2e93ffcf4d7eac44`，日志 `/tmp/s2b-c-dependency-input-cff2.log` SHA `281a424d390b60f390e30b189179196a45e04fe589ce8fd0c3620fc778bf7526`。cff→004 未改任何依赖输入。

复用 06 已预填 `gateway-backend-deps:lock-d054366c02fa`，来源仍为 A/readiness 核过的 CT201 `132fc621d5711ae39ac8f1dc66f4349b2f6fe428` 制品；原预填时间/传输摘要见 A handoff/readiness，不虚构本节新传输。C 从当前 tag 实际 docker save，核 source config `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` 和全部 19 DiffID。`artifacts/s2b-c-0048040af5/base-identity.txt` 含完整列表，SHA `3c5764473f68c1fb2d362226816bddfbce133897a0227c0738d1c65d5df22793`；本次保存归档 `base-current.tar` SHA `95f6dc2ccf6ecd9fc352540a8b249bfa978d6bb2f5338fd5b936dfeb68b2076c`。核验 helper SHA `138eade578d3f9e06e3b3cc1b7f62a16cc04c64f64095eafa62c6b598738a972`，不比较跨节点 inspect ID。

Compose 使用 preloaded dependencies=1、d054 base、build network=none，未启用 GATEWAY_COMPOSE_GATE_PREBUILT；本机服务网络保持正常。Repository dependency-base lock `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` 与当前锁匹配。

本次唯一 project `s2b-c-0048040af5` 的本机 image：

- backend `s2b-c-0048040af5-backend:latest`，ID `sha256:043b88bec8b74205d3f3a5b3b4fc4790fca680567752363d741f7cde8a1d586a`；health provenance 与 smoke 用同一 ID。
- worker `s2b-c-0048040af5-worker:latest`，ID `sha256:58d2649cd7c379aac3ab36f02c0d2f5978ae90186caa9d6bc5f9790a5709006d`，当前 HEAD 实际离线 build。
- Repository Service `s2b-c-0048040af5-repository-service:latest`，ID `sha256:f4b4197ef64e2c8e9c219be3f1ce5d778d16cfa105194be82e6d102b47aabfa7`，revision label 为 004；owning build-input `3b037adf4caf33f65e124a34f56f12f42e529641` / source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2` 与当前身份一致。

provenance `artifacts/s2b-c-0048040af5/compose-provenance.json` SHA `9d5a09a700de04fbb9657d24347310eba078ad8c8da859f278a8f2de4e59e672`。外置 container script SHA `9930a60361dbea1b1ae3680b7c3394e9887b6581b6e319bef5346835d7c9cf26`、smoke SHA `53b979cdc597b54eea1b5f95ac373760b08a13ca44bb3af6d723844d00fdfe4c`。smoke 两行，IPC 2,098 B，raw SHA `9c7a29e26b74c54bc2eea8fcdb1ba3e4da01411e289a99a28abbb99e675d88ba`；只证明实际 container 中的 coarse B/A/store/借用/TTL 小闭环，不是生产容量。

Dockerfile 未为镜像编译注入 host GATEWAY_RUST_BUILD_INPUT，不能宣称镜像 extension 用该非空字段完成 host tree checker；容器证据来自 fixed clean source 的实际构建、image ID 与执行绑定，保留 A/B 已知限制。

## 7. 失败与修正记录

失败原日志不覆盖；没有通过修改 golden/输入/预期业务行为或放宽验收消除失败。

| 失败 | 保留外部 SHA256 / 处理 |
| --- | --- |
| 1059 mypy：projection version 既有类型为 str、测试 Optional 未 assert | `logs/s2b-c-component-1059.log` `2d36fc060fc6c4c0cc7af8cb24307acfffd9bd2ebf0adb00471371839436f82d`；保持 owning str，补类型断言，pytest 尚未跑。该首次脚本 EXIT 曾将 self-sha 写进日志，早报 `3f89…` 是写该行前摘要；此处使用完成后外部 SHA，原文件未改。 |
| 3adc mypy：PyArrow compute 无 typed marker、测试访问未公开 tempfile module attribute | `logs/s2b-c-recovery-3adc.log` `170ec6be8e3e281c86490215a78d7eeb22dc1bdf84dacd8d495e7687368193e4`；沿既有 import-untyped 边界，测试直接 patch stdlib tempfile，不改规则。 |
| 9f55 HTTP fixture 错用 raw commit path 断言 | `logs/s2b-c-recovery-9f55.log` `a00889b195bca5ab272e47efb47766f4fb61e4bd6140beabe2b35c7d82029e5f`；改用 owning Contract base64url decoder，预期 exact commit 未放宽。 |
| 545a 实际 RS SET child-nonnullable list 不匹配 PyArrow25 binary_join 签名 | `logs/s2b-c-recovery-545a.log` `0c06e934e5e8e294c64c94ee574dc7426ccd957d0d7db98c26a552672af95614`；先拒 null member，再 safe cast 标准 list wrapper，仅物理适配；真实 wire fixture 未改，309c通过。 |
| capacity tool 单独 mypy 命令、t4 4 GiB keyed 临时量误累计 | 见容量报告；原失败/部分文件保留，经 root/独立审核最小 keys-only 修正、同输入同预算一次复验通过。 |
| b721 Python architecture 3 FAIL | `logs/s2b-c-architecture-hooks-b721.log` `2a1612d79916b91c07f3690d576e4cafa5136db575e05ba6385319bc72621927`；真实 core tests fixture IO 改编译期 bytes；正式 policy 精确 native caller 与五项 D 切片边界由 root 批准后纳 guard，无 IMPORT/cycle 豁免。cff actual gate通过。 |
| 41d8 compiletime fixture 遗漏后段 assert 的 case 标签，clippy E0425 | `logs/s2b-c-final-static-41d8d4c0a4.log` `e62ffd03a21f4241f6d47b9b14af4d7bc20ee34fc1028aad346f76097eaaa1d2`；cff保留(case,sql,expected)，输入/断言未改，完整 Rust policy 通过。 |
| cff schema target 清单未列新两表/两索引 | §5 原 focused 日志；5c4仅补四行目标期望，004定向17 PASS。 |

## 8. 释放与 D 交接

本角色 **14:30:50Z** closeout 核自身 owner、clean 004、无运行容器/Dolt、无本 project 残留 container/volume 后，仅删除自己的 owner 文件并 rmdir busy。closeout 日志 `logs/s2b-c-closeout-0048040af5.log` SHA `00f62e93669cadb87dea729b42accd567408eea444e97ecaeef3a150cdbc7f1b`，exit0；这是实际收尾日志，不倒填初次获取时间。

保留 C clean worktree、所有日志/失败产物/容量 JSON、images、task refs/bundles，以及 focused Cargo target `/home/dev/gdds-test-tmp/s2b-c-cargo-target` 构建缓存；未删除已填充依赖。A/B worktree/image/证据及 CT108/04/05/07 资源未被本角色修改。

D 待办：落实 Owner 已选容量 A 的显式配置；实际 startup N/M/control 与所有 operation caller 迁移；complete canonical closure/reader/repository-ref/import-replay/export 接线；删五项临时 unreachable；真实 worker EOF/publish、cancel/drain/lease/deadline、FULL/borrowed/shared reservation 与拒绝边界。M 缺失应 fail startup，8 GiB 是显式部署初始值而非隐式默认。C 已释放节点，不以配置选择冒称容量 PASS。

最终 S2b 的 E 单路径清理、04 权威 runner/container、t1–t4 正确性、W1/W2 时点与 CT108 基准仍按原计划；本节不进入 D/E、不做推送或最终 phase exit。
