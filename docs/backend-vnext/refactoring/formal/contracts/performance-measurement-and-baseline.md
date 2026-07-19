# Performance Measurement and Baseline Contract

状态：正式设计（Accepted）

阶段：Phase 0 contract；Phase 2–5 首次 capture；Phase 6–8 持续使用

Contract ID：`gateway-vnext.performance-measurement-and-baseline`

Owner：Performance Measurement owner；环境 profile 由 Deployment/Repository owners 共同维护

Semantic version：`1.0.0`

Measurement contract version：`1`

## 1. 目的与非目标

Phase 0 交付 measurement contract、workload/dataset identity、result schema 和 first-capture gate。首份 numeric baseline 等真正可运行、correctness-passed 的 containerized vNext production path 建成后捕获。Legacy 可以帮助识别业务规模，但不提供 numeric baseline、性能目标、相对 speedup 或切流门禁。

只评价 vNext 自身：后续优化与同一可比 series 的 accepted vNext baseline 比较。不建立 legacy-vs-vNext performance benchmark。

## 2. 权威环境与阶段

正式 end-to-end baseline profile：Backend/worker container 通过 public client/wire contract 调用 Repository Service container；Repository Service 独占 Dolt binary/process、registry/journal/repository/staging lifecycle。第一版不另拆 Dolt container。业务容器不安装 Dolt、不挂载 Repository volume。

Image/base image/Dolt digest、CPU/memory quota、volume/filesystem、host CPU/disk class、kernel/runtime 形成 immutable `environment_profile_id`。同一 machine 一次只运行一个正式 suite。Host-local/pytest/CLI 结果仅是 component diagnostic，不可混入 deployment baseline series。

Exclusive phases：

```text
storage_projection
repository_prepare
dolt_apply
commit
post_commit_readback
verification_persist
```

观察层级为 component、effect（Repository request accepted 至 VERIFIED）和 journey（AcceptSubmit T1 至 Finalize T3）。Total 独立计量，不由 component durations 相加；duration 使用 monotonic clock，跨进程 spans 分开记录。

## 3. Profiles 与 workloads

四种 profile 不得拼接或相加：

| Profile | 生产入口与重建边界 |
| --- | --- |
| `projection-build` | public storage projection；固定 SnapshotTableArtifact，每次 fresh manifest/import artifact |
| `repository-effect` | public Repository client；固定 prebuilt import artifact，每次 fresh repository + full readback |
| `canonical-write-e2e` | production Submit job；每次 projection/import/commit/readback |
| `history-sequence` | production import/readback/CAS/cleanup；固定 immutable revision chain |

Workload 独立报告，不做 composite score：`initial-load`、`canonical-no-change`、`sparse-business-change`、`row-churn`、`compatible-schema-change`、`normal-history-30`、`retention-stress-100`、`ordered-position-shift`、`storage-projection-upgrade`。

Accepted baseline 至少覆盖 typical dataset 的 initial/sparse/row-churn/schema/history-30，及 upper-bound representative dataset 的 initial/change/readback。No-change、history-100、ordered shift 和 projection upgrade 单列诊断。

## 4. History retention 与 GC

每代按生产机制 canonicalize、submit、full readback VERIFIED、mainline CAS/archive equivalent、清除 transient operation/staging refs、quiescence、计量。保留 mainline 可达正式历史和业务 retention 引用；不得每代重建 repository 或过度删除历史。

记录每 commit 增量、累计大小和 working high-water。30/100 sequence 完成并 quiescent 后执行固定 GC checkpoint，GC 不进入单次 Submit latency；报告 pre/post size、reclaimed bytes、duration 和 retained closure。

## 5. Metrics 与 result eligibility

必需指标：exclusive phase/effect/journey duration；rows/s、canonical bytes/s、tables/s、readback rows/bytes/s；GC 单独计时。每个 run 记录 Backend/worker 与 Repository Service/Dolt cgroup memory；`pipeline_memory_peak` 是同步 monotonic timeline 上各容器 usage 之和的最大值，不能相加各自异时 peak。CPU、I/O 和 fallback sampler 方法同样记录。

Storage 分为 SourcePackageArtifact store、Canonical Dolt repository（apparent/allocated/pre/post GC）、Repository metadata/journal/manifest、temporary staging high-water/cleanup。只测 Dolt 不能声称系统总 storage 降低。

单代 profile：1 warm-up + 至少 5 measured runs；报告 raw samples、median、MAD、min/max。少于 20 samples 不报告 p95；需要 p95 时至少 20。History profile 至少 3 条完整 fresh-repository sequence。不静默删除 outlier；失败样本与首次证据保留。

Result 复用 `PASSED | ASSERTION_FAILED | HARNESS_ERROR | UNSUPPORTED`。只有正式路径、full readback、required metrics 和 cleanup 均完成的 PASSED 可进入 aggregate。

## 6. Baseline series 与 record

`measurement_contract_version` 固定阶段、指标、denominator、eligibility、aggregation、cold/warm、GC 和 result schema。语义变化升级 version。Dataset/change chain、storage projection/ruleset/canonical encoding/readback、Dolt/Repository image/provider 或 environment profile 变化必须新建 series，不能判为同线 regression。

`BenchmarkBaselineRecord` 状态独立于 execution result：

```text
INCOMPLETE -> CANDIDATE -> ACCEPTED -> SUPERSEDED
```

Record 是 immutable machine-readable JSON authority，至少含 baseline/supersedes identity、measurement contract digest、git revision、safe dataset ID/revision、environment/image/component digests、validation、全部 samples/aggregates、external evidence digest/ref 和 limitations。Markdown 是生成报告，不是第二 authority。Git 内 record 不含 private digest/path/raw row/sensitive log。

## 7. First accepted baseline capture gate

首次 ACCEPTED 必须同时满足：

1. Storage projection、RepositoryImportArtifact、SnapshotManifest 和 measurement contract 已版本化。
2. Normative vectors、scenario、Repository conformance 和 full readback tests 通过。
3. Repository Service container 具备 public contract、health、persistent volume、restart recovery 和固定 image/Dolt identity。
4. External dataset identity/validation 通过。
5. 四 profile 只走 production public entrypoint，无 benchmark-only fast path。
6. Required 单代各至少 5 个有效 samples，history 至少 3 条完整 sequence。
7. 进入 aggregate 的结果全部 PASSED，环境/evidence/cleanup 完整。
8. Storage Projection、Repository 与 environment profile owners 共同接受。

Gate 前不能声称 accepted numeric baseline。首条正确路径本身可含初始 Rust production provider；但任何后续 Rust coverage、并行、cache、incremental readback 或 provider 性能优化及收益声明必须等待 accepted baseline。

## 8. Run validity

Runner 只观察 production typed spans/counters，不调用 private step、绕过 journal/readback、直接改服务端目录、伪造 VERIFIED 或改变 batch/order/digest。Preflight 验证 machine isolation、single writer、quota/filesystem、disk headroom、health/quiescence 和无未声明 maintenance。Restart/OOM、异常 throttling、disk exhaustion 或 required metric gap 使 run 为 HARNESS_ERROR。

## 9. Classification 与验收标准

Module public：是。Persisted：baseline record；raw evidence 外部 content-digested。Wire：JCS JSON + metrics/evidence refs。

- Measurement schema 可验证且所有单位/denominator 明确。
- Profile/workload 不混算，不产生 composite score。
- Multi-generation retention 与 GC 可重复。
- Environment drift 会新建 series或使 run invalid。
- 所有 performance aggregate 可追溯到 PASSED evidence。
- Formal 计划和 CI 不含 legacy performance gate。

## 10. 关联文档

- [Fixture Oracle and Conformance](fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [ADR 0007](../adr/0007-vnext-performance-baseline-authority.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
