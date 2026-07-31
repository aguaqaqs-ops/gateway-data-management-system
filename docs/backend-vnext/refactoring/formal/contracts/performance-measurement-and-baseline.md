# Performance Measurement Guidance

状态：正式设计（Accepted Simplified Baseline）

阶段：Phase 0原则；真实纵切和优化阶段按需执行

Owner：产生性能声明的Capability/Application owner

Semantic version：`3.0.0`

决策依据：
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)

本文件替代原measurement contract v2、formal capture gate、environment identity和
BenchmarkBaselineRecord状态机。

## 1. Purpose

性能测量用于回答当前业务容量或优化问题，不用于提前建设发布证据框架。任何性能
结论必须来自correctness-passed的真实vNext production path。

Legacy可以帮助识别数据规模和人工场景，但不提供vNext numeric baseline、相对
speedup目标或切流门禁。

## 2. Required measurement boundary

正式end-to-end测量使用实际部署拓扑：

```text
Backend/worker
  -> public Repository client/HTTP contract
  -> Repository Service
  -> Dolt and durable storage
```

Component benchmark可以用于诊断算法，但不得冒充端到端用户结果。Benchmark-only
private fast path、直接修改Repository目录或跳过正常validation/commit/ref publication
均不产生正式声明。

## 3. Minimum run record

每次需要保存或引用的测量至少记录：

```text
question or capacity target
dataset ID/revision and relevant scale
software/component versions
deployment topology
CPU/memory limit and storage class when relevant
workload and warm/cold setup
raw samples
summary calculation
correctness result
known limitations
```

记录可以是普通machine-readable result加Markdown说明。不要求content-addressed
evidence、immutable environment profile、git revision签署或独立baseline lifecycle。

不同dataset、algorithm contract、canonical version、provider、concurrency或关键
部署条件的结果不可直接声称为同线regression；报告必须显式说明不可比项。

## 4. Workload and statistics

Workload由当前consumer或容量问题决定，不预建固定profile/workload矩阵。至少覆盖
提出结论所需的representative input和一个相关边界样本。

Runbook应在执行前写明：

- warm-up与measured run数量；
- 记录median、range、percentile或其他统计的理由；
- outlier处理方式；
- cleanup/quiescence要求；
- failure是否重跑。

失败sample不得静默改写成成功。样本数、MAD/p95门槛和history sequence数量不是
跨项目formal常量；没有足够样本时只能限制结论。

## 5. Optimization entry

下列之一存在时才增加并行、cache、provider或低层优化：

- 已接受的业务容量目标；
- validation-passed production measurement显示缺口；
- 明确且可复现的materialization或资源瓶颈。

优化前后必须使用相同业务语义和可比workload。Canonical bytes、业务digest、records
或diagnostics语义改变时，结果属于contract change，不是性能优化。

没有业务容量压力时，简单、串行、确定的实现优先。

## 6. Storage and retention measurement

声称系统存储变化时，至少分开报告：

- durable SourcePackageArtifact；
- canonical Dolt repository；
- Backend/Repository metadata；
- temporary staging high-water；
- cleanup或GC后的状态。

只测Dolt不能声称系统总存储下降。SourcePackage durable retention和外部备份成本
不得隐藏。

## 7. CI and gate boundary

普通CI只运行适合持续执行的correctness、unit、integration和smoke tests。性能测量
默认不是每PR gate；出现明确SLO、容量或regression预算后，由对应owner在runbook或
CI配置中增加局部阈值。

不存在：

- formal first-capture gate；
- `INCOMPLETE/CANDIDATE/ACCEPTED/SUPERSEDED` baseline状态机；
- `environment_profile_id`；
- benchmark result evidence digest；
- generic harness result复用；
- legacy-vs-vNext performance gate。

## 8. Acceptance

- 每个正式性能声明可定位到真实production entrypoint、dataset和raw samples。
- correctness失败的run不进入性能汇总。
- 不可比环境或contract变化被显式说明。
- 优化没有改变canonical或业务结果。
- 未出现真实consumer/容量问题时，不因本文件预建benchmark framework。

## 9. Related authority

- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)
- [Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)
- [Repository Service](repository-service.md)
