# P2-R1 targeted diagnostics paired analysis

本文件是 A direct DEVNULL paired diagnostic 与 B restart-before-stream diagnostic 的本地派生分析，供审核使用。三个原始 artifact 及各自 runner report 均保持字节级不变；本文件不产生 formal decision。

## Decision boundary

- `formal_status = no-go`
- `selected_provider = null`
- `enter_p2_r2 = false`
- 本诊断只用于定位 failure mechanism 和评估 restart 实验；不放宽 1.5x、不修改 authority、不选择 A/B。

## Common provenance and lifecycle

| 项目 | A paired | B restart |
|---|---|---|
| source/build revision | `50f05cf6e394bfea48d1a7e4cb6c1959a9879396` | same |
| image digest | `sha256:a535fc14dce409fc4bfdce44ad59043f8a576811f5c7a207a7ee3aa1b129e89c` | same |
| methodology | `p2-r1-audit-corrective-v7` | same |
| cache condition | `retained-dependency-cache` | same |
| storage | verified named volume, XFS | verified named volume, XFS |
| cleanup | project container/network/volume absent; cgroup absent | project container/network/volume absent; cgroup absent |
| formal meaning | diagnostic-only, no-go | diagnostic-only, no-go |

### Local artifact integrity

| artifact | size | SHA-256 |
|---|---:|---|
| `a-paired/a-devnull.jsonl` | 486083 bytes | `656ab331467a0c7e4f0902fc453afc0b9de0aa3730237a176d38dd6d1c23e22a` |
| `a-paired/a-devnull.summary.json` | 5160 bytes | `08305285e3ae30ade3d5ef313a7683645b818420b050a93d73c9e729f06b481c` |
| `a-paired/a-devnull.md` | 734 bytes | `3c74995fd99135ba880a5ef07dcbb17f23727bb947ca0c755aae4034d48acb0d` |
| `b-restart/b-restart.jsonl` | 260456 bytes | `8b9ee331e2e88dd45d5edae424c6f91a0a8ee26a3bb207db1e84998a68f18f65` |
| `b-restart/b-restart.summary.json` | 4938 bytes | `a61ba41c62107e2df5c38748e186468212e7b6370acc424d946c1edd8dfa4595` |
| `b-restart/b-restart.md` | 734 bytes | `3c74995fd99135ba880a5ef07dcbb17f23727bb947ca0c755aae4034d48acb0d` |

- A remote run/project: `20260804163016_62478` / `gateway-p2r1-20260804163016_62478`.
- B remote run/project: `20260804201223_1320072` / `gateway-p2r1-20260804201223_1320072`.
- A 的完整 provider/cgroup 原值表见 [A paired review summary](a-paired/a-paired-review-summary.md)。

## Candidate B coverage and restart evidence

- 36 raw records：S10/S40/S100 × row bound 256/1024 × warm-up + 5 measured；唯一 candidate 为 `candidate_b_sql_server`。
- 36/36 `correctness=true`，36/36 `error=null`，`sample_failures=0`；storage mount/provenance 全部通过。
- 每条 record 的 restart identity 均变化；`shutdown_reap_quiesce=true`、`head_preserved=true`、`catalog_preserved=true`。
- restart duration：min/median/max = `0.119300` / `0.192346` / `0.280738` s；before/after server identity 全部不同。
- 36 条记录共享一致的 project-level named-volume `storage_root_identity`；`restart_diagnostic.storage_identity` 随 workflow target 变化。当前 raw 未分别记录 restart 前后的 storage identity，因此不能仅凭该字段机器化证明 before/after target identity 相等。

| restart evidence | result |
|---|---|
| server identity changed | 36/36 true |
| shutdown → reap → quiesce | 36/36 true |
| head preserved | 36/36 true |
| catalog preserved | 36/36 true |
| correctness/cancel | 36/36 correctness true; connection reset recorded on cancellation |
| provider-level RssAnon/RssFile | unavailable in B raw schema; cgroup memory.stat anon/file retained below |

`b-restart.summary.json` 保留了 diagnostic 聚合器的已知字段差异：`records=0`、`scaling_records=36`；raw 实际包含 36 条记录。代码已修正为后续 scaling diagnostic 同时发布总 `records`、`scaling_records` 和 `unique_measurement_keys`，本次已发布 summary 不改写，也不因此重跑 B。

## Restart 对 retained memory 的实际效果

与 80858ca formal 中未重启的 B 对比，restart 大幅清除了 import 后 retained anonymous memory，但没有使 query-before absolute workset 或 query-period anonymous delta 与规模解耦：

| scale | 原 cgroup baseline | restart 后 query baseline | 约降幅 |
|---|---:|---:|---:|
| S10 | 413 MiB | 149 MiB | 64% |
| S40 | 1,280–1,308 MiB | 338–341 MiB | 73–74% |
| S100 | 2,034–2,037 MiB | 753 MiB | 63% |

匿名 baseline 的典型变化约为：S10 `366 → 103 MiB`、S40 `1,080–1,109 → 141–143 MiB`、S100 `1,471–1,473 → 192 MiB`。因此准确结论是：**restart 有效清除了大部分 import-retained anonymous memory，但没有让 query-before absolute workset 和 query-period anonymous delta 与数据规模解耦。** 它对绝对资源预算有真实价值，但不能解除当前 1.5x bounded gate。

## Candidate B post-restart query baseline

以下 baseline 是 restart 完成、catalog/head 校验完成、query/stream 开始前的 baseline；单位：cgroup current/anon/file 为 bytes，provider/workflow RSS 为 KiB。

| bound | scale | cgroup current median/max | anon median/max | file median/max | provider RSS median/max | workflow RSS median/max |
|---:|---|---|---|---|---|---|
| 256 | S10 | 156184576 / 156291072 | 107749376 / 107855872 | 44515328 / 44515328 | 165248 / 167312 | 247592 / 248156 |
| 256 | S40 | 357773312 / 363483136 | 150405120 / 156729344 | 202747904 / 202756096 | 206920 / 215084 | 288500 / 295668 |
| 256 | S100 | 789426176 / 797925376 | 201576448 / 209973248 | 582971392 / 583172096 | 258916 / 264996 | 339176 / 347832 |
| 1024 | S10 | 156426240 / 160628736 | 107786240 / 112041984 | 44515328 / 44515328 | 167316 / 171388 | 247684 / 251188 |
| 1024 | S40 | 354787328 / 355209216 | 148303872 / 148414464 | 202747904 / 202756096 | 206808 / 206936 | 286320 / 287184 |
| 1024 | S100 | 789450752 / 794677248 | 201580544 / 206176256 | 582971392 / 582971392 | 258900 / 262944 | 339120 / 343968 |

观察：restart 后 query baseline 的 cgroup current、anon、provider RSS 仍随 S10→S40→S100 显著增加；因此 restart 没有消除规模相关的 retained anonymous/query baseline footprint。

## Candidate A plateau/peak consistency correction

A raw 中有两个 S10 streaming sample 的 `final_10pct` provider plateau absolute 为 `343148` 和 `324792 KiB`，而同 record 的 provider peak 约为 `175864` 和 `171860 KiB`。根因定位为 sampler 在 stream 已关闭/reap 后仍通过旧的数字 PID 取最终样本；若该 PID 被复用，其他进程会被误归因到 Dolt provider。

代码已修复：`ProcessStream.running_pid` 在 child 已退出/reap 后返回 `None`，A sampler 使用该 guarded PID；同时 `ProcessStream` 与 `DiscardProcess` 的内部 RSS monitor 现在与进程生命周期共享同一把锁，并在任何 wait/reap 前停止并 join。新增了“reaped child 不再被 sampler 采样”和“内部 monitor 在 reap 前停止”的回归测试。现有 A/B raw 不重写、不重跑，因此这两个异常值仍保留在历史 diagnostic evidence 中；在任何绝对预算或 v8 formal rerun 前，必须用修复后的代码重新产生相应 evidence。

## Candidate B plateau raw values

每个 `values (5)` 为 measured-1…measured-5 原值；delta 是 baseline-adjusted plateau，absolute 是同窗口 absolute plateau。provider/workflow 为 KiB，cgroup/Arrow 为 bytes。

### provider process tree

| bound | window | scale | delta values (5) | delta median/max | absolute median/max |
|---:|---|---|---|---|---|
| 256 | first_10pct | S10 | 8380, 4180, 4196, 8284, 6240 | 6240 / 8380 | 171492 / 173628 |
| 256 | first_10pct | S40 | 100, 132, 128, 156, 120 | 128 / 156 | 207040 / 215184 |
| 256 | first_10pct | S100 | 176, 168, 140, 4276, 200 | 176 / 4276 | 259056 / 265172 |
| 256 | middle_10pct | S10 | 8516, 12612, 12656, 10480, 12608 | 12608 / 12656 | 177812 / 179924 |
| 256 | middle_10pct | S40 | 14840, 14868, 18960, 19016, 16916 | 16916 / 19016 | 223808 / 229924 |
| 256 | middle_10pct | S100 | 17124, 39760, 37708, 31596, 35648 | 35648 / 39760 | 294400 / 298532 |
| 256 | final_10pct | S10 | 12692, 12624, 12672, 12576, 12636 | 12636 / 12692 | 177940 / 179940 |
| 256 | final_10pct | S40 | 25276, 27320, 31424, 29376, 27308 | 27320 / 31424 | 236188 / 240360 |
| 256 | final_10pct | S100 | 77324, 68756, 83504, 66912, 87624 | 77324 / 87624 | 342320 / 350508 |
| 1024 | first_10pct | S10 | 4180, 10368, 8292, 8340, 6232 | 8292 / 10368 | 175568 / 177624 |
| 1024 | first_10pct | S40 | 156, 108, 140, 132, 132 | 132 / 156 | 206940 / 207068 |
| 1024 | first_10pct | S100 | 140, 2208, 148, 172, 140 | 148 / 2208 | 259040 / 263084 |
| 1024 | middle_10pct | S10 | 12604, 18892, 14680, 14724, 10576 | 14680 / 18892 | 183992 / 184080 |
| 1024 | middle_10pct | S40 | 16836, 18956, 25076, 16976, 18980 | 18956 / 25076 | 223784 / 227820 |
| 1024 | middle_10pct | S100 | 41780, 25432, 37688, 39792, 31504 | 37688 / 41780 | 296524 / 300680 |
| 1024 | final_10pct | S10 | 12620, 18932, 16744, 14732, 14688 | 14732 / 18932 | 184008 / 186076 |
| 1024 | final_10pct | S40 | 29292, 29356, 33440, 33504, 31428 | 31428 / 33504 | 236232 / 240312 |
| 1024 | final_10pct | S100 | 89624, 66868, 83488, 83552, 77360 | 83488 / 89624 | 340304 / 348524 |

### workflow process tree

| bound | window | scale | delta values (5) | delta median/max | absolute median/max |
|---:|---|---|---|---|---|
| 256 | first_10pct | S10 | 17828, 13916, 13892, 18096, 15964 | 15964 / 18096 | 262852 / 264120 |
| 256 | first_10pct | S40 | 10076, 9920, 10116, 10092, 9916 | 10076 / 10116 | 298416 / 305744 |
| 256 | first_10pct | S100 | 10048, 10024, 9948, 13888, 10084 | 10048 / 13888 | 349124 / 357880 |
| 256 | middle_10pct | S10 | 18120, 22568, 22476, 20412, 22544 | 22476 / 22568 | 270136 / 270724 |
| 256 | middle_10pct | S40 | 24852, 24656, 28972, 28968, 26732 | 26732 / 28972 | 315704 / 320520 |
| 256 | middle_10pct | S100 | 27004, 49620, 47532, 41228, 45560 | 45560 / 49620 | 385056 / 388880 |
| 256 | final_10pct | S10 | 22308, 22580, 22492, 22508, 22572 | 22508 / 22580 | 270156 / 270736 |
| 256 | final_10pct | S40 | 35292, 37108, 41436, 39348, 37144 | 37144 / 41436 | 328156 / 330960 |
| 256 | final_10pct | S100 | 87204, 78620, 93328, 76544, 97540 | 87204 / 97540 | 432504 / 440860 |
| 1024 | first_10pct | S10 | 16656, 22860, 20504, 20800, 18684 | 20504 / 22860 | 268484 / 269852 |
| 1024 | first_10pct | S40 | 15144, 15128, 15336, 15156, 14988 | 15144 / 15336 | 301476 / 302328 |
| 1024 | first_10pct | S100 | 15044, 16060, 15220, 15128, 15312 | 15220 / 16060 | 354164 / 359280 |
| 1024 | middle_10pct | S10 | 26404, 32776, 28544, 28832, 24692 | 28544 / 32776 | 277536 / 279768 |
| 1024 | middle_10pct | S40 | 30832, 32980, 39296, 31008, 32852 | 32852 / 39296 | 318016 / 322332 |
| 1024 | middle_10pct | S100 | 55728, 39308, 51784, 53804, 45700 | 51784 / 55728 | 390740 / 394848 |
| 1024 | final_10pct | S10 | 26420, 32808, 30616, 28840, 28824 | 28840 / 32808 | 277608 / 279800 |
| 1024 | final_10pct | S40 | 43292, 43380, 47664, 47536, 45300 | 45300 / 47664 | 330476 / 333856 |
| 1024 | final_10pct | S100 | 103600, 80760, 97588, 97564, 91564 | 97564 / 103600 | 435532 / 442720 |

### cgroup

| bound | window | scale | delta values (5) | delta median/max | absolute median/max |
|---:|---|---|---|---|---|
| 256 | first_10pct | S10 | 16232448, 11677696, 12333056, 15896576, 13676544 | 13676544 / 16232448 | 169951232 / 170455040 |
| 256 | first_10pct | S40 | 8400896, 7938048, 7454720, 8294400, 8306688 | 8294400 / 8400896 | 366080000 / 371884032 |
| 256 | first_10pct | S100 | 8675328, 8372224, 8716288, 13242368, 8761344 | 8716288 / 13242368 | 798142464 / 806600704 |
| 256 | middle_10pct | S10 | 16789504, 20930560, 20983808, 18108416, 20746240 | 20746240 / 20983808 | 177020928 / 177274880 |
| 256 | middle_10pct | S40 | 23502848, 22978560, 26746880, 28176384, 25067520 | 25067520 / 28176384 | 382898176 / 386985984 |
| 256 | middle_10pct | S100 | 26595328, 49229824, 47165440, 40927232, 45191168 | 45191168 / 49229824 | 834953216 / 839208960 |
| 256 | final_10pct | S10 | 20996096, 20914176, 20500480, 20103168, 20189184 | 20500480 / 20996096 | 176463872 / 177098752 |
| 256 | final_10pct | S40 | 34500608, 35901440, 39866368, 38825984, 36098048 | 36098048 / 39866368 | 395821056 / 397983744 |
| 256 | final_10pct | S100 | 87486464, 79011840, 93859840, 77586432, 97796096 | 87486464 / 97796096 | 883286016 / 891813888 |
| 1024 | first_10pct | S10 | 14704640, 20860928, 18661376, 18735104, 17080320 | 18661376 / 20860928 | 175333376 / 177287168 |
| 1024 | first_10pct | S40 | 13746176, 12996608, 13471744, 14118912, 14090240 | 13746176 / 14118912 | 368050176 / 368955392 |
| 1024 | first_10pct | S100 | 14340096, 15855616, 14008320, 13811712, 13582336 | 14008320 / 15855616 | 803504128 / 808259584 |
| 1024 | middle_10pct | S10 | 25927680, 32579584, 28348416, 28794880, 24764416 | 28348416 / 32579584 | 186556416 / 189005824 |
| 1024 | middle_10pct | S40 | 30973952, 33394688, 38719488, 31707136, 33386496 | 33386496 / 38719488 | 386506752 / 389672960 |
| 1024 | middle_10pct | S100 | 56741888, 39202816, 53047296, 54648832, 45887488 | 53047296 / 56741888 | 842293248 / 846192640 |
| 1024 | final_10pct | S10 | 25522176, 32559104, 29786112, 28540928, 28418048 | 28540928 / 32559104 | 186150912 / 188985344 |
| 1024 | final_10pct | S40 | 44388352, 44257280, 47706112, 48582656, 46186496 | 46186496 / 48582656 | 399310848 / 403369984 |
| 1024 | final_10pct | S100 | 105861120, 82440192, 100237312, 99180544, 93208576 | 99180544 / 105861120 | 887885824 / 895311872 |

### Arrow memory pool

| bound | window | scale | delta values (5) | delta median/max | absolute median/max |
|---:|---|---|---|---|---|
| 256 | first_10pct | S10 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | first_10pct | S40 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | first_10pct | S100 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | middle_10pct | S10 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | middle_10pct | S40 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | middle_10pct | S100 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | final_10pct | S10 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | final_10pct | S40 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 256 | final_10pct | S100 | 124544, 124544, 124544, 124544, 124544 | 124544 / 124544 | 124544 / 124544 |
| 1024 | first_10pct | S10 | 248256, 248256, 248256, 248256, 248256 | 248256 / 248256 | 248256 / 248256 |
| 1024 | first_10pct | S40 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | first_10pct | S100 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | middle_10pct | S10 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | middle_10pct | S40 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | middle_10pct | S100 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | final_10pct | S10 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | final_10pct | S40 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |
| 1024 | final_10pct | S100 | 496512, 496512, 496512, 496512, 496512 | 496512 / 496512 | 496512 / 496512 |

## Candidate B cgroup anon/file delta

provider-level RssAnon/RssFile 未写入 B raw；下面是 workflow cgroup 的 `memory.stat` delta，用于区分匿名内存与 file cache。

| bound | scale | anon delta values (bytes, 5; median/max) | file delta values (bytes, 5; median/max) |
|---:|---|---|---|
| 256 | S10 | 19951616, 19898368, 19906560, 19832832, 19898368; 19898368 / 19951616 | 0, 0, 0, 0, 0; 0 / 0 |
| 256 | S40 | 32874496, 34906112, 39124992, 37072896, 34922496; 34922496 / 39124992 | 0, 0, 0, 0, 0; 0 / 0 |
| 256 | S100 | 86106112, 77369344, 92479488, 75476992, 96587776; 86106112 / 96587776 | 0, 0, 0, 0, 0; 0 / 0 |
| 1024 | S10 | 24166400, 30642176, 28409856, 26329088, 26312704; 26329088 / 30642176 | 0, 0, 0, 0, 0; 0 / 0 |
| 1024 | S40 | 41226240, 41295872, 45498368, 45563904, 43458560; 43458560 / 45563904 | 0, 0, 0, 0, 0; 0 / 0 |
| 1024 | S100 | 103051264, 79757312, 96739328, 96800768, 90484736; 96739328 / 103051264 | 0, 0, 0, 0, 0; 0 / 0 |

## Candidate B scale ratios

每个 `(bound, subject, window)` 取三个 scale 各自五次 measured 的最大值，再计算 max/min；仅作诊断观察。

| bound | window | provider KiB | workflow KiB | cgroup bytes | Arrow bytes |
|---:|---|---:|---:|---:|---:|
| 256 | first_10pct | 53.72 | 1.79 | 1.93 | 1.00 |
| 256 | middle_10pct | 3.14 | 2.20 | 2.35 | 1.00 |
| 256 | final_10pct | 6.90 | 4.32 | 4.66 | 1.00 |
| 1024 | first_10pct | 66.46 | 1.49 | 1.48 | 2.00 |
| 1024 | middle_10pct | 2.21 | 1.70 | 1.74 | 1.00 |
| 1024 | final_10pct | 4.73 | 3.16 | 3.25 | 1.00 |

## Paired findings for review

- **Candidate A：** direct DEVNULL 没有消除 streaming 中观察到的规模增长；Arrow pool 在 streaming 中约固定于 124,544 bytes，DEVNULL 中为 0，而 provider/cgroup 仍随 scale 增长。A 的更可能机制仍是 Dolt CLI/query 侧工作集，而不是 Arrow serialization；详见 A review summary。
- **Candidate B：** restart 确实更换 server identity，并完成 shutdown/reap/quiesce；36/36 保持 head/catalog，且 project-level storage root identity 一致。但 `restart_diagnostic.storage_identity` 随 workflow target 变化，raw 没有 before/after storage identity 配对字段。restart 后的 query-before baseline 已随规模增长，且 middle/final cgroup delta ratio 仍超过 1.5，说明“每次 import 后 restart”没有消除 B 的规模相关内存工作集。
- **B 的匿名内存证据：** cgroup `anon` delta 随 scale 增长，而 `file` delta 在所有 B measured records 为 0；这支持增长主要体现在匿名内存/工作集，而不是新增 file-cache delta。由于没有 provider-level RssAnon/RssFile，不能把 cgroup 结果进一步归因到单一进程。
- **restart 成本与风险：**本次 36 条记录 restart duration 约 0.119–0.281 s，correctness/catalog/head/storage 均通过；但正式采用仍需将 server restart、connection reset、缓存重建和生命周期顺序纳入 authority 与正式 workload 证据，不能由本诊断自动放行。
- **最终边界：** 本报告只补充机制分析，不改变 formal no-go，不选择 Candidate A/B，不进入 P2-R2，不覆盖正式 132-record artifacts。

## Source files

- [A paired raw](a-paired/a-devnull.jsonl)
- [A paired review](a-paired/a-paired-review-summary.md)
- [B restart raw](b-restart/b-restart.jsonl)
- [B restart summary](b-restart/b-restart.summary.json)
- [B restart runner report](b-restart/b-restart.md)
