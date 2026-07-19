# Fixture Oracle and Conformance Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 1–8 持续执行

Contract ID：`gateway-vnext.fixture-oracle-and-conformance`

Owner：Conformance Harness；scenario expected content 由对应 semantic owner 拥有

Semantic version：`1.0.0`

Manifest schema version：`1`

## 1. Oracle 权威与不兼容变更

权威顺序为：已接受 formal contract/ADR、人工确认的业务结果、versioned golden fixture、legacy observable behavior。Legacy 仅用于发现旅程、边界 case 和差异，不拥有 vNext 结果，不作为内部结构、目录、状态、provider、cache、Dolt layout 或性能 oracle。

新旧差异必须归类为 `MATCH | OLD_BUG | NEW_BUG | INTENTIONAL_CHANGE | UNRESOLVED`。`UNRESOLVED` 不可自动 bless。正式 intentional change 包括最小持久状态、canonical Dolt、effect-first recovery 和本文语言中立 fixture 体系。

## 2. 根目录与 scenario identity

```text
vnext/fixtures/
  scenarios/
    data/<subject>/<scenario-path>/
    command/<subject>/<scenario-path>/
    recovery/<subject>/<scenario-path>/
  shared/
  vectors/
```

每个 scenario 目录是自包含 closure：

```text
scenario.yaml
input/
expected/
```

Scenario ID 使用稳定 dot notation；物理路径 segment 使用 kebab-case，二者必须可逆一致。ID 至少包含 track、subject 和语义名称，例如 `recovery.submit.timeout-success-journal`；manifest 的 track/subject 必须与路径一致。

不按“最小样本/回归样本”建立目录分类；provenance 表达 handcrafted 或 sanitized regression。Scenario 不继承其他 scenario，不提供模板 DSL、脚本或可执行 hook。共享 immutable asset 只能通过显式 content-digested ref 引用。

## 3. Scenario manifest

每个 `scenario.yaml` 至少声明：

```text
manifest_schema_version
scenario_id
track: data | command | recovery
subject
description
provenance
contract_bindings[]: owner, contract_id, semantic_version
canonical_encoding_version
input_assets[]: logical_name, path/ref, media_type, digest, size
input_digest
fixture_content_digest
expected[]: kind, path, contract binding, digest
required_profiles[]
legacy_classification
```

`input_digest` 只覆盖 schema-declared logical inputs；`fixture_content_digest` 覆盖 manifest closure 与 expected assets，并按 manifest schema 的自引用排除规则计算。Digest 使用 [Shared Canonical Encoding](shared-canonical-encoding.md)。Unknown field、path escape、digest/size mismatch、missing closure 或 track/ID/path mismatch fail closed。

Golden envelope 必须显式声明 owner、contract ID/name/version、payload media/schema、canonical encoding version、comparison mode 和 content digest。Structured semantic golden 经 schema validate 后做 exact canonical compare；artifact golden 比 schema/digest/closure；recovery golden 比 checkpoints 和最终事实。Host path、trace ID、随机 timestamp、log/stack 和非 contract ordering 不进入 golden。

## 4. Provenance 与材料边界

`HANDCRAFTED` 由最小人工输入组成。`SANITIZED_REGRESSION` 必须记录安全来源标识、sanitization policy/version、审批、不可逆脱敏和预期业务边界；任何敏感原文、内部路径或可逆映射不得进入 Git。

Scenario-local closure 上限 1 MiB；单个 shared correctness asset 上限 5 MiB。超限必须裁剪、拆分或通过评审转为外部 dataset。第一版不使用 Git LFS。

外部 benchmark dataset 不进入 Git scenario closure。每个 dataset 必须有 `dataset.yaml`，固定 safe dataset ID/revision、provenance、validation rules、logical composition/change chain、generator version/seed（如适用）和内容 identity。缺失或 identity 不匹配产生 `HARNESS_ERROR`，不能被当作 pass。

## 5. Runner 与 harness registry

Oracle runner core 只负责 schema/closure validation、profile dispatch、stable clock/ID、result aggregation 和 evidence packaging。Subject harness registry 由 subject owner 注册 parser/capability/application/Repository public entrypoint；scenario manifest 不保存语言实现入口。

Execution profiles：

- `reference`：小规模 semantic oracle。
- `integration`：真实组件边界与 artifact。
- `process-crash`：进程终止/restart/takeover。
- `provider-matrix`：同 contract 的 Python/Rust/Repository conformance；不用于比较内部实现结构。

Runner result 只有 `PASSED | ASSERTION_FAILED | HARNESS_ERROR | UNSUPPORTED`。只有 PASSED 才可进入性能 aggregate；自动 retry 不覆盖第一次证据。

## 6. Fault 与 recovery protocol

Recovery scenario 只声明一个 primary typed fault；runner 先验证该 fault 对 subject/profile 合法，再通过 test-only side channel arm。Harness 必须回报 armed/consumed exactly once；未消费或重复消费是 `HARNESS_ERROR`。生产 request/wire schema 不携带 fault 字段。

每个 recovery scenario 至少有 `after_failure` 与 `after_recovery` checkpoint。断言通过 stable public reads 和 Repository journal/evidence 完成；使用 logical clock/deadline 与 stable-read barrier，不使用固定 sleep 猜测完成。恢复使用生产 restart/reconcile/takeover 入口，不由 runner 篡改数据库或目录。

`RunEvidenceBundle` 是 test-only、content-digested evidence，包含 run/profile/scenario identity、environment/component versions、fault receipt、observations/checkpoint results、diagnostics 和 cleanup status。它不是生产 artifact，也不新增业务状态。

## 7. CI lane

Correctness CI 校验 manifest、closure、golden、normative vectors 和 required profile matrix；小规模 reference/integration 必须在普通 CI 可重复运行。Process-crash/provider matrix 可按声明进入专用 lane，但不能永久 optional。

External benchmark lane 使用同一 dataset identity、runner result和 correctness gate，但其数字、repository 和 raw evidence 保存在 Git 外。性能发现的 semantic mismatch 必须回流为最小 correctness scenario；benchmark 不能成为唯一正确性测试。

Golden 更新必须显示 candidate diff、owner approval、intentional-change 分类、contract/version/digest 影响；普通测试运行禁止自动 bless。

## 8. Classification 与版本

Module public：是。Persisted：fixture/golden/evidence manifest。Wire：YAML/JCS JSON/owner artifact formats。

Manifest schema 与 scenario-bound semantic contract 分别版本化。目录变化不能伪装语义兼容；已发布 ID 不因重排目录而复用为另一场景。

## 9. 验收标准

- 所有 scenario ID、path、track、subject、closure 和 digest 可离线验证。
- 每个 expected asset 只有一个 semantic owner 和显式 contract version。
- Python、Rust、Repository 共享同一 vectors/scenarios；不存在实现语言专属的正式 oracle root。
- Recovery tests 不依赖 sleep、内部代码行或数据库 dump。
- Git fixture 无敏感数据、超限资产或 LFS 依赖。
- Legacy 差异均已分类，`UNRESOLVED` 会阻断 bless/cutover。

## 10. 关联文档

- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [Performance Measurement and Baseline](performance-measurement-and-baseline.md)
- [ADR 0006](../adr/0006-language-neutral-fixture-oracle.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
