# ADR 0005: Shared Canonical Encoding

状态：Accepted

日期：2026-07-19

决策 owner：Shared Kernel

关联阶段：Phase 1、Phase 3

## Context

Python、Rust 和 Repository Service 必须对 scalar、manifest、row identity 和 digest 产生相同 bytes。Legacy 的 JSON sorting、运行时 lowercase、conversion fallback 和 temporal 处理不是充分的跨语言 contract；只比较最终 hash 也无法定位编码歧义。

## Decision

发布统一 `canonical_encoding_version` bundle：JSON 使用 RFC 8785 JCS；table scalar 使用 tag + minimal ULEB128 length + canonical payload；CanonicalIdentifier 仅 ASCII upper-to-lower；temporal 区分 civil value、UTC instant 和 MySQL duration；invalid literal 只能成为 owner-declared anomaly 或 hard failure；semantic digest 使用 domain-separated SHA-256；row/collection 使用显式 framing 和集合语义。

Python、Rust、Repository 直接消费同一组 static normative vectors并逐字节验证。精确 byte contract与tag registry位于 [Shared Canonical Encoding Contract](../contracts/shared-canonical-encoding.md)；vector manifest/case/closure/error schema位于 [Canonical Encoding Normative Vector Schema](../contracts/canonical-encoding-normative-vector-schema.md)。

## Alternatives

- 继续使用 Python `json.dumps(sort_keys=True)`：拒绝，不是完整跨语言规范。
- 只固定 logical values，不固定 bytes：拒绝，digest/artifact/cache identity 会分叉。
- 每层独立自由版本：拒绝第一版采用，避免未经验证的组合矩阵。
- Conversion 失败后保存普通 string：拒绝，会抹除 schema/anomaly 语义。

## Consequences

所有实现共享稳定 byte authority，代价是严格 fail-closed、版本升级和 vector review 流程。Existing digest/cache 不能在 byte contract 改变后静默复用。Scalar frame 仅用于 digest preimage，公开 wire 仍需 owner schema。

## Required Verification

- JCS、scalar、identifier、temporal、row/collection 和 invalid normative vectors。
- Python/Rust/Repository byte-for-byte conformance，而非只比 digest。
- Domain separation、raw blob distinction、serial/parallel determinism tests。
- v1 vector candidate 必须经人工与两个独立实现审核。
