# ADR 0005: Shared Canonical Encoding

状态：Accepted

日期：2026-07-19

决策 owner：Shared Kernel

关联阶段：Phase 1、Phase 3

2026-07-31 修订：ADR 0010 保留本 ADR 的 canonical bytes 与
`canonical_encoding_version`，但把 correctness authority 收敛为 Python/Rust
直接消费的静态 corpus 和一个必要业务 golden。Repository 不再消费 normative
vectors；vector-set manifest、closure、runner、evidence 和候选发布流程不再是现行
contract。

## Context

Python与Rust必须对scalar、row identity和digest产生相同bytes。Repository Service
只接收Backend产出的结构package，不实现canonical算法。Legacy的JSON sorting、
运行时lowercase、conversion fallback和temporal处理不是充分的跨语言contract；
只比较最终hash也无法定位编码歧义。

## Decision

发布统一 `canonical_encoding_version` bundle：JSON 使用 RFC 8785 JCS；table scalar 使用 tag + minimal ULEB128 length + canonical payload；CanonicalIdentifier 仅 ASCII upper-to-lower；temporal 区分 civil value、UTC instant 和 MySQL duration；invalid literal 只能成为 owner-declared anomaly 或 hard failure；semantic digest 使用 domain-separated SHA-256；row/collection 使用显式 framing 和集合语义。

Python reference 与 Rust production provider 直接消费同一组 static canonical cases，
逐字节验证。精确 byte contract、tag registry 与现行 corpus 规则位于
[Shared Canonical Encoding Contract](../contracts/shared-canonical-encoding.md)；
[Canonical Encoding Normative Vector Schema](../contracts/canonical-encoding-normative-vector-schema.md)
仅保留历史背景。

## Alternatives

- 继续使用 Python `json.dumps(sort_keys=True)`：拒绝，不是完整跨语言规范。
- 只固定 logical values，不固定 bytes：拒绝，digest/artifact/cache identity 会分叉。
- 每层独立自由版本：拒绝第一版采用，避免未经验证的组合矩阵。
- Conversion 失败后保存普通 string：拒绝，会抹除 schema/anomaly 语义。

## Consequences

Python/Rust 共享稳定 byte authority，代价是严格 fail-closed 和显式版本升级。
Existing digest/cache 不能在 byte contract 改变后静默复用。Scalar frame 仅用于
digest preimage，公开 wire 仍需 owner schema。

## Required Verification

- JCS、scalar、identifier、temporal、row/collection 和 invalid normative vectors。
- Python/Rust byte-for-byte correctness，而非只比 digest。
- Domain separation、raw blob distinction、serial/parallel determinism tests。
- 128 个既有 canonical cases 必须无 skip 通过；byte contract 变更必须另行 ADR。
