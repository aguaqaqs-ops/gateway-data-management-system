# Canonical Encoding Vector Schema — Historical

状态：Superseded by
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md) and
[Correctness Golden and Fixture Contract](fixture-oracle-and-conformance.md)

原Contract ID：`gateway-vnext.canonical-encoding-vector-schema`

原版本：`1.0.0`

## Historical scope

本文路径曾拥有Phase 1 `vector-set.json`、JSONL case schema、closure digest、
candidate generation和Repository第三consumer规则。该方案已经完成Phase 1历史
checkpoint，但不再是当前设计或CI authority。

当前规则：

- Shared Canonical Encoding Contract继续唯一拥有canonical bytes、tag、framing和
  digest算法；
- 保留的128个case是普通只读golden corpus；
- 每个case只需稳定`case_id`、operation、input和expected bytes/digest/error code；
- Python与Rust使用薄loader直接消费同一corpus并zero skip；
- 不再维护vector manifest、self-digest、JSON Schema、candidate generator或
  Repository consumer。

实现和测试不得从本历史文件恢复旧closure、schema或publication流程。精确当前
验收见：

- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [Correctness Golden and Fixture](fixture-oracle-and-conformance.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
