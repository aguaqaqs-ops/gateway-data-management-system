# Phase 6 S5 D 交接

固定产品 `cb2ad300845f73f12ae5367d247829623b728f18`，D 基线
`bf1f15393e1c1bfba8e906a9b2cc071affb1e7e2`；vnext tree
`8a28a9ab172d967eb526132084ec2b43b34b7c04`，Rust tree保持
`c0213e18a9645c5cfbd39f310f532273a03a10cb`。**D CODE_GO / EVIDENCE_GO，可进入E**。原审核收原文SHA256=
`70c06d1ccf7a38e083e3e386800bdfe3434fb9e5f761f9c3b3fc09b568a16405`；
逐字归档整体SHA256=`51183ad55e63c4cd8a55f3343165f57ce53f3eb35cab79471cd72f3f4c8e149a`。

## 产品与边界

- T3 在原 MatchingFinalizeFacts 后从 attempt.preview_result_id 取得真实 Preview producer，
  核 workspace/repository/完整 configuration facts；已 FINALIZED replay 不续期。Preview
  临时记录缺失时跳过可选触达，T1 已冻结的 Attempt 事实继续负责原业务屏障；存在但矛盾即
  FinalizeBindingMismatch，不能当 cache miss。未将缺失解释为 GC 删除，也不猜 producer。
- bounded touch 复用 B 的现存 manifest/expiry/uses 规则，仍只 SQL。在原 write transaction
  内用窄 SAVEPOINT，只容忍已 typed 的 InvalidComputationCachePayload；回滚/释放和外层
  事务均须有效。未知 SQLite/IntegrityError、事务/CAS 错误继续传播。没有新文件/Repository
  访问、重算、BaselineHead 推进、跨服务事务或恢复 journal。
- 通用 client RequestControl 传到 catalog、Arrow open/read/chunk/backoff，当前 cancel/deadline
  及原请求 timeout 取最小约束；仍单请求最多3次原502/503/transport尝试，已暴露字节不拼接
  重试。pending open 即使吞取消后返回，也由 abandon 关闭 response/client。原 poll 在截止
  时已经完成的 terminal observation 保持原行为；显式 catalog/stream 在自身返回边界检查。
- backend HTTPArrow 与实际 Submit parent catalog 都显式转发当前 context，控制异常恢复原
  KernelStopped/Timeout；不被 OSError 包成可重试 provider 故障。未增加外层重试、pool 或 M。
- DC94 原 T1/prepare checkpoint/固定包/key 边界保持；新增缺持久包小向量明确不重建publisher。
  已替换 repr identity 与 History 全表预读在 A/C 删除；实际仍有 consumer 的 generic facade、
  map-only library seams、artifact validator/独立 golden 保留，不为删除数量制造改动。

owning Artifacts、Canonical Storage、Operation Lifecycle、Repository Service Contract 同步。
无依赖/锁、HTTP DTO、SQL golden、Rust、部署或容器 harness 改动；N1/单 active、32GiB worker、
8GiB reserve、显式 M24 不变。D 独立容器重建未触发，最终门禁集中 E。

## 独审与实际验证

D 新建 d_implement / d_review / d_test，协调者持续；Sol high实施、Sol xhigh独审、Luna max
唯一执行，没有继承 C 对话或 Astra 临时权限。同原审 R1–R3 连续关闭：原 poll deadline
completion、真实 Submit parent catalog 漏转发、client tuple Optional 类型，以及两个新
fixture 非法前置；后两项只修合法外部 workspace 与 fresh CAS，不改业务 expected。
逐字原审和证据审核见 [D 归档](p6-s5-d-review.md)。

06 / gw-dms-06.lan 本地起2026-11-09 **10:34:03Z**，remote session
**10:34:06Z–10:36:18Z**，runtime **10:34:07Z–10:36:17Z**。19步 command/tee 全0：
强制 native 重装、四包其余环境同步、build-input、五包 ruff/mypy、client **74 passed**、
backend parallel **256 passed / 2 warnings / 27.20s**、serial **4 passed / 256 deselected /
9.61s**。入口/remote/local/outer tee/copy均0；起止 HEAD 同 cb2、clean、cleanup0、本人标记释放。
RS 环境使用本人新WT正常 .venv，成功清理，原失败环境/日志均保留。

实际范围含 T3 真实 SQLite 事务/TTL/错误与回滚、真实 subprocess RS、原 Submit hard restart
与 missing-package 屏障、client cancel/deadline/资源释放和 backend 实际参数接线。
Rust tree未变，D未重复 fmt/clippy/test；A focused Rust来源不冒 E 权威来源。

成功执行稿 `/home/dev/gdds-s5-logs/execution/d-focused-revised.sh` SHA256=
`5a16b2bc44a57f0f76dc4197a425605302383f6a51c0f47f3f7e9212736387e2`。
成功原件根：
`/home/dev/gdds-s5-logs/execution/d-focused/20261109T103403Z-cb2ad300845f73f12ae5367d247829623b728f18/`。

| 原件 | SHA256 |
| --- | --- |
| session.log | `264979dd0e73eba148096edc889ce717db76dfaedeaddd0126193be0fb7bcb19` |
| steps.tsv | `b1cfff7ba17c36829c6285987c87ff8ac160a777f794695d8f7b9cfb48b8fe6c` |
| client focused | `9921d43b13663261822d35c45b8f8153f81b33fe9ee384374960f204d1dd3437` |
| backend parallel | `b4d0df3647aef2e8fb8184268444b422eb43b3dd6c7f7f85c202c78e567be07d` |
| backend serial | `42d843a7cd3688487cf5fdc6ec7e5cdbdefd990ed183ec947925359f1d874ad2` |
| LAN source bundle | `0e03cfa620169dce09f9ef7aa978452093c957220e4dfe009657cd9742f517d7` |
| local SHA256SUMS | `b13f879fe9a93193810f8df5d843dcf9c24d213b6fd0c8984b4eb2977916acc8` |

本机既有 LAN 预填 uv/Cargo，offline=1/true，无公网/代理。uv0.11.28，Rust四工具selector
1.97.0、Python3.14.6，Cargo/pytest workers4；Dolt SHA256=
`615e47b782f4ad5c664e5a8dab5bb09532be4336d249abb414c4a2a826cda3e8`。
日志的实际命令、每步完整 HEAD/UTC、缓存类别和释放状态均可核。

## 两次失败与修复

失败同06、固定 clean候选，首非零停止；原稿SHA256=
`331ebe525102bdd3d7cb98ea0306827be1d2dde5dacb284102aea18b6ea7925d`，保留未改。

| 原候选 / session UTC | 原始结果 / 未跑项 | 关键日志SHA256 |
| --- | --- | --- |
| `8d7a1580f3`，10:16:35Z–10:17:46Z 产品步骤 | 前11步0；client mypy1/tee0，两Optional tuple类型错；后续静态/focused未跑 | `660a3251a34c25785792ec3f088600b8289c1ffbc4e7f62b875c9f6a3c62d47a` |
| `5610ae7025`，10:20:53Z–10:22:46Z session | 前17步0，client74；backend251过5败/exit1；serial未跑 | `cbca3b0623a75f560353d11e3d8041932b56a831ae7ef9c05558ad3187610aae` |

原件根分别为同执行目录下
`20261109T101631Z-8d7a1580f3321608382a06e16334c733d1a0f4a8/` 与
`20261109T102051Z-5610ae7025ac5c6269233a3d04613480292c99c8/`。
首次修订5610只用真实 opened tuple固定类型，不 cast/ignore。第二次两项新fixture在到达T3前
被FK/旧CAS拒绝，cb2修前置；另三个现有集成在启动前找不到RS正常项目 .venv。原执行稿RS
sync成功但环境放外部，与既有harness固定路径不符；修稿仅恢复RS标准目录并收尾本人目录。
该profile故障按DC68第1修复轮闭合，不将整次混合失败称为工具问题，不修改原numeric exit。

## E 输入与未测

D 原审证据已核收，固定本交接后 D 三角色退出活动分工；E 新建实施、独审、唯一测试/等待，
协调者持续，不跨节复用。E 以最终产品、A–D handoff/原审及必要原件接手，另核 E 源码和退出。

没有 qualified runner、Compose、carried 或真实 t1 结论。历史最后验证镜像仅 S4 V=
`6786b28a3506feab3d8eac7d1288c8b22525bb8f`，原身份SHA=
`1d349eba449e9fa5b8fc3293a9277eb850c6f7b3b28edf1ba72e4a4a8af94411`，D未重算。
E 必须按最终实际闭包完成全部六包和适用 Compose，保持来源WT/环境/镜像以绑定文档H；
标准 t1 v1/v2仅冷History、新key的新operation复查、实际records与完整tar，必要合法前置依
kickoff §5补建。不能把 A–D focused 当合格来源，不能据S4 M40推M24成功。无push、无提前tag。
