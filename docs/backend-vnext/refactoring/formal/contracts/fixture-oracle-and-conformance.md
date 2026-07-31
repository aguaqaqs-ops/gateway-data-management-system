# Correctness Golden and Fixture Contract

状态：正式设计（Accepted Simplified Baseline）

阶段：Phase 0–1结论；后续持续使用

Contract ID：`gateway-vnext.correctness-golden-and-fixture`

Owner：测试材料由对应semantic owner拥有；目录约束由Backend vNext Architecture拥有

Semantic version：`2.0.0`

决策依据：
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)

本文件替代原`gateway-vnext.fixture-oracle-and-conformance` v1.1通用scenario、
runner、profile和evidence语义。旧schema与runner只解释Phase 1历史checkpoint，不再
拥有当前测试或CI authority。

## 1. Purpose

Golden只固定跨实现必须保持的业务结果或canonical bytes。测试材料不能自行建立
第二套业务digest、发布身份、运行状态机或可信证据链。

正式测试材料继续位于：

```text
vnext/fixtures/
  vectors/
  golden/
```

具体物理目录可在联合代码清理时调整；路径不是业务identity。普通pytest和Cargo
test直接加载材料并比较结果，不通过generic runner分发。

## 2. Canonical encoding corpus

Phase 0–1保留当前128个canonical encoding case，覆盖：

```text
JCS
typed scalar normalization/encoding
identifier
row/collection framing
semantic/raw digest
valid bytes and stable invalid code
```

每个case必须有稳定`case_id`、operation、input以及expected bytes/digest或
expected error code。Python与Rust分别使用薄、语言习惯化的只读loader和独立
implementation逐case执行。

不再要求：

- `vector-set.json`；
- per-file size/raw hash和semantic closure digest；
- JSON Schema或重复runtime validator；
- candidate generator/bless command；
- Repository第三consumer；
- executed-case evidence bundle。

CI必须断言Python/Rust实际case ID集合与expected corpus一致、无duplicate且zero
skip。现有case的success/error classification或expected bytes改变时必须发布
canonical encoding v2；由v1规则唯一推导的新增case可以加入v1。

## 3. Business golden

Phase 1保留一条canonical row-hash mixed-scalar golden，最小材料为：

```text
request
Arrow input
expected sorted row hashes
expected row_count
expected table_schema_digest
expected raw_content_digest
```

测试直接调用Python reference与Rust production boundary并比较上述业务结果。
不保存scenario manifest、golden envelope、fixture/input digest、contract-binding
closure或`canonical-table-result` wrapper digest。

后续新增golden必须满足：

- 对应Domain/Application/Capability是唯一semantic owner；
- 只保存调用者可观察或持久化后必须兼容的结果；
- provider、host path、PID、随机timestamp、log、stack和build identity不进入expected；
- 业务语义变化通过普通code review记录intentional change和版本影响；
- 普通测试不得自动改写expected文件。

## 4. Test-data integrity and safety

Git本身、code review和普通raw file read提供测试材料版本控制。无需在文件内部重复
保存self-hash。

保留的安全规则：

- fixture不得包含敏感原文、secret或可逆脱敏映射；
- 路径必须是repository-relative，测试不得接受host path作为contract字段；
- 大型或敏感benchmark dataset保存在Git外，并在runbook中记录dataset ID/revision；
- 读取失败、JSON/Arrow解析失败或expected字段缺失直接使测试失败。

不建设approval registry、sanitization evidence bundle、generic verified resolver、
fault legality registry或test-only service。

## 5. Python reference and Rust provider

Python reference只用于小规模golden、property test和诊断。Rust是正式批量production
provider。二者共享semantic contract和golden，不共享implementation source。

Repository Service不计算canonical bytes、不消费canonical corpus。它只消费受信
Backend生成的Repository import package，并按自己的contract做结构检查。

## 6. Ordinary CI

最低持续验证：

```text
Python Shared Kernel: ruff, mypy, pytest
Rust workspace: fmt, clippy, test
Canonical corpus: Python/Rust all cases, exact compare, zero skip
Canonical row hash: reference/native mixed-scalar golden
Backend: artifact round-trip
Native/container: installed wheel and one health/native smoke
```

测试只有普通pass/fail/skip语义；required canonical/golden test不得skip或xfail。
基础设施问题由CI系统直接报告，不映射为`HARNESS_ERROR`、`UNSUPPORTED`或独立
evidence lifecycle。

## 7. Classification and change control

Module public：否，测试数据约定。

Persisted：Git correctness材料。

Wire：无production wire；JSON/JSONL/Arrow只作为test data format。

Breaking changes：

- canonical v1 expected bytes/error classification变化；
- 已确认业务golden结果变化；
- 删除仍覆盖唯一业务边界的golden。

非breaking changes：

- loader、测试框架或目录内部重构；
- 新增由现有规则唯一推导的case；
- 格式化不参与owner semantic equality的说明文件。

## 8. Acceptance

- Python/Rust对保留corpus逐case一致，Repository没有vector依赖。
- mixed-scalar业务golden在reference/native路径结果一致。
- repository中不存在current-authority scenario runner、profile matrix、
  RunEvidence或fixture self-digest。
- 普通CI无需exact commit、closure或identity bundle即可运行。
- Golden变更在普通diff中可直接审查，且不会由测试自动bless。

## 9. Related authority

- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [Canonical Row Hash Compute Boundary](canonical-row-hash-compute-boundary.md)
- [Implementation Stages](../plans/implementation-stages.md)
