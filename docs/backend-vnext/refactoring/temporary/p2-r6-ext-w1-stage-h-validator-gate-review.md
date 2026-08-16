# P2-R6-EXT-W1 Stage H — Independent Validator Gate Review

状态：`pass`

日期：2026-08-16

本记录是 Stage G production validator evidence 之后的独立只读 validator gate
review。审核只回答执行计划 Stage H 的五个问题，不审实现风格，不修改生产代码，
不重跑 FULL_SCAN / S6 / container，不重建 image。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
Stage F 记录：[P2-R6-EXT-W1 Stage F Five-fixture Packages](p2-r6-ext-w1-stage-f-five-fixture-packages.md)
Stage G 记录：[P2-R6-EXT-W1 Stage G Production Validator](p2-r6-ext-w1-stage-g-production-validator.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
stage_g_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
stage_g_entry_head_sha: b11922135b30c70af668218fd558d0c77138a3c2
stage_f_commit_sha: b11922135b30c70af668218fd558d0c77138a3c2
stage_e_reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
stage_g_is_head: yes
reviewed_worktree: clean
production_code_changed_by_review: no
full_s6_run: no
package_version: v1
canonicalization_version: v1
image_rebuilt: no
container_rebuild_required: no
review_scope: five-fixture production validator evidence, negative probes, identity
```

HEAD 为 Stage G 收口 `7f068a24`。Stage G 记录中的 `Current HEAD: b1192213` 是该
阶段入口 SHA，不是收口身份。S5 候选 `e7a6e42d` 仍是祖先。Worktree 干净，无未提交
生产代码。五份本地 `package.tar.zst` 仍在 `/root/test-data/<alias>/`，size/SHA 与
Stage F 字面量、`EXPECTED_PACKAGES`、`dataset.yaml` 和
`canonicalization-manifest.json` 的 `manifest_digest` 逐字节一致。

## Required questions

1. 五份 validator 结果是否全部 PASS？
   **是。** 每份均完成 production `validate_and_extract_import_package()` 与
   `verify_import_candidate(FULL_SCAN, REJECT)`。extract=`pass`，
   `completed_verification_policy=FULL_SCAN`，`unknown_type_policy=REJECT`，
   `main_unchanged=yes`。未走 HTTP worker，未 publish `main`。

   | alias | tables | rows | enum | set | unknown | lossy | extract | FULL_SCAN |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
   | small_cut | 132 | 6091 | 273 | 1 | 0 | 0 | pass | FULL_SCAN |
   | small | 216 | 97095 | 404 | 1 | 0 | 0 | pass | FULL_SCAN |
   | medium | 199 | 268460 | 327 | 1 | 0 | 0 | pass | FULL_SCAN |
   | data2 | 319 | 436714 | 544 | 1 | 0 | 0 | pass | FULL_SCAN |
   | data1 | 260 | 638088 | 401 | 1 | 0 | 0 | pass | FULL_SCAN |

2. manifest/catalog exact match、Arrow schema、row count、raw SHA/size 是否闭合？
   **是。** 生产 `verify_import_candidate(FULL_SCAN)` 比较 name / `sql_type` /
   nullable / PK / catalog `row_count`，再 compile Arrow 并扫描全表值；scanned
   row count 必须等于 manifest。Stage G 脚本另核对 observed raw size/SHA 与
   Stage F binding、`canonicalization_manifest_digest` 与 Stage F 字面量。本审核
   独立复算五份 package SHA 与 manifest digest，全部匹配。

   `dataset.yaml` 的 `reported_total` 来自 `information_schema.TABLE_ROWS` 估计
   （如 small_cut 6088），与 catalog/FULL_SCAN 实际行数（6091）不同。权威是
   manifest/catalog/FULL_SCAN，不是 information_schema。这不是 mismatch。

3. ENUM/SET 是否没有 unknown/unmappable 或隐式 stringify？
   **是，没有。** 五份 unknown=0、lossy=0。合法 ENUM 为 `utf8` +
   `gateway.logical_type=enum`；合法 SET 为 `list<utf8>` +
   `gateway.logical_type=set`。畸形类型在 STRINGIFY 下仍由既有 unit owner 证明为
   `IMPORT_REJECTED`。medium ENUM 列为 327（readiness 预检 328）；权威是 Stage F/G
   catalog 扫描，且 unknown=0，不构成 blocker。

4. validator failure/no-effect、reopen、截断、digest 错误和 metadata 错误证据是否
   充分？
   **是。** 以 small_cut 正式 package 为底，不改五份正向 SQL：

   | name | outcome |
   | --- | --- |
   | package_reopen | pass；连续 extract 两次，`manifest.json` / `replay.sql` 逐字节相同 |
   | truncated_zstd | rejected；`import package is malformed` |
   | digest_mismatch | rejected；`artifact raw sha256 does not match binding` |
   | error_metadata_extra_field | rejected；`manifest.json failed closed validation` |
   | executor_truncated_no_dolt_effect | rejected；`IMPORT_REJECTED`；`main` 不变，无 private ref |
   | verification_row_count_mismatch | rejected；`row count mismatch for adv_app_list`；`main` 不变 |

   既有 unit owner 111 passed（`test_import_package` /
   `test_import_verification` / `test_p2_r1_primitives`）。

5. candidate SHA、package SHA、配置快照和运行时版本是否一致？旧 image 结果不得
   替代当前 HEAD。
   **一致；旧 image 未替代当前 HEAD。** 审核绑定 Stage G 收口
   `7f068a24`。python `3.14.6`，dolt `2.1.11`。容量快照沿用 Stage A /
   `RepositoryServiceSettings` 默认值；最大 package 5724227 bytes（data1），低于
   256 MiB upload 与 200 MiB replay hard cap。image 未重建；S5 image `e7a6e42d`
   只作为历史 container evidence，container gate 延期 Stage J。本 gate 的证明是
   当前 HEAD 的 production Python 路径，不是旧镜像。

## Published v1 digests

本审核通过后正式发布到本轮 evidence。算法标识保持
`gateway-vnext:canonicalization-manifest:v1`。selected W1 仍是 medium。

| alias | package_bytes | package_sha256 | canonicalization_manifest_digest |
| --- | ---: | --- | --- |
| small_cut | 83838 | `sha256:54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43` | `sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a` |
| small | 613635 | `sha256:e440af6963d99315ef632fcf34f57741de0791ec9a8942ce284b2900efbf82c3` | `sha256:5c01406aba92537be95b3ba904e6ff092661c7bce30352f3369bdf3cc6958b49` |
| medium | 2081228 | `sha256:3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` | `sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c` |
| data2 | 3173874 | `sha256:72a266b25f2712d8f23f3010937693dc4a5a41dd93e2cb237928f711aa0fc813` | `sha256:c1cad27c519695ba9701cdf4b5572714dfcab295355bd614f42a0d5fad53e340` |
| data1 | 5724227 | `sha256:bd607ecbca4890d273188f93d1020fa32e2cc0cbd5f6f9ffdbfcffe49feb9bf2` | `sha256:29a37b49168a04da8e802471f8eaf6221b64abbdef16eb64cc1ba9fa848dd435` |

## Findings

No findings.

## Non-findings

以下已闭合，不构成 blocker：

- `dataset.yaml` `reported_total` 是 information_schema 估计，FULL_SCAN 使用实际
  catalog/scan 行数。
- medium ENUM 327 对 readiness 预检 328：权威是当前 catalog 扫描；unknown=0。
- Stage G 记录的 `Current HEAD` 是入口 `b1192213`；收口 commit 是 `7f068a24`。
- 未走 HTTP worker、未 publish main：符合 Stage G 生产 API 路径，不是本 gate 缺口。
- 旧 S5 image 未重建：本 gate 不宣称当前 HEAD 的 container 证明。
- 2746-byte 外部 descriptor 文件本机不可检索；facts 在 readiness 与本地
  `dataset.yaml`。Stage K 按脱敏摘要重发，本阶段不伪造该文件。
- 五份 live `package.tar.zst` 仍在批准位置，SHA 与已发布 digest 一致。

## Residual risks（不阻断 Stage I）

- 本 gate 不是 S6 capacity PASS。容量、W2、concurrency matrix 属于 Stage I。
- `R6-EXT-W1` 保持 `no`，直到 S6/W2 evidence 完成。
- 最终 candidate 仍须按 testing conventions 在 Stage J 重建 image 并跑 container
  gates。
- operational-closure 中 `R6-EXT-W1: not_provided_to_s0` 留给 Stage I/K 按取得
  方式改写，本审核不扩大到那份计划。

## Verdict

```yaml
review_status: pass
stage_h_exit: pass
blocker_count: 0
required_fix_count: 0
five_packages_validated: yes
full_scan_reject: pass
enum_set_unknown_or_lossy: no
negative_probes: pass
gate_published: yes
production_validator_result: pass
P2-R6-S6_ready: yes
R6-EXT-W1: no
s6_capacity: not_run
production_code_changed_by_review: no
image_rebuilt: no
container_rebuild_required: no
next: Stage I — S6 capacity and W2 handoff
```

独立审核通过。正式发布五份 v1 `canonicalization_manifest_digest`，并将
`P2-R6-S6_ready` 改为 `yes`。这仍不代表 S6 capacity PASS。新会话须从本收口
commit 复核 SHA 与 worktree，不得假定本会话状态。未授权不得开始 S6 capacity、
W2、concurrency matrix 或把旧 image 写成当前 HEAD 已验证。
