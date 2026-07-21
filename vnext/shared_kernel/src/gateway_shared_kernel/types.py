"""Production value types for Shared Canonical Encoding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Mapping


class DeclaredTypeKind(StrEnum):
    NULL = "null"
    BOOLEAN = "boolean"
    SIGNED_INTEGER = "signed-integer"
    UNSIGNED_INTEGER = "unsigned-integer"
    DECIMAL = "decimal"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    STRING = "string"
    BINARY = "binary"
    BIT = "bit"
    DATE = "date"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"
    TIME_DURATION = "time-duration"
    SOURCE_LITERAL_ANOMALY = "source-literal-anomaly"


_INTEGER_BITS = frozenset({8, 16, 24, 32, 64})


@dataclass(frozen=True, slots=True)
class DeclaredType:
    kind: DeclaredTypeKind
    bits: int | None = None
    precision: int | None = None
    scale: int | None = None
    bit_width: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not DeclaredTypeKind:
            raise ValueError("kind must be DeclaredTypeKind")
        if self.bits is not None and type(self.bits) is not int:
            raise ValueError("bits must be int when present")
        if self.precision is not None and type(self.precision) is not int:
            raise ValueError("precision must be int when present")
        if self.scale is not None and type(self.scale) is not int:
            raise ValueError("scale must be int when present")
        if self.bit_width is not None and type(self.bit_width) is not int:
            raise ValueError("bit_width must be int when present")
        kind = self.kind
        if kind in {DeclaredTypeKind.SIGNED_INTEGER, DeclaredTypeKind.UNSIGNED_INTEGER}:
            if self.bits not in _INTEGER_BITS:
                raise ValueError("integer declared type requires bits in {8,16,24,32,64}")
            if self.precision is not None or self.scale is not None or self.bit_width is not None:
                raise ValueError("integer declared type rejects extra fields")
            return
        if kind is DeclaredTypeKind.DECIMAL:
            if self.precision is None or self.scale is None:
                raise ValueError("decimal declared type requires precision and scale")
            if not (1 <= self.precision <= 65 and 0 <= self.scale <= 30):
                raise ValueError("decimal precision/scale out of owner range")
            if self.scale > self.precision:
                raise ValueError("decimal scale must be <= precision")
            if self.bits is not None or self.bit_width is not None:
                raise ValueError("decimal declared type rejects extra fields")
            return
        if kind is DeclaredTypeKind.BIT:
            if self.bit_width is None or not (1 <= self.bit_width <= 64):
                raise ValueError("bit declared type requires bit_width in 1..=64")
            if self.bits is not None or self.precision is not None or self.scale is not None:
                raise ValueError("bit declared type rejects extra fields")
            return
        if self.bits is not None or self.precision is not None or self.scale is not None:
            raise ValueError(f"{kind.value} declared type rejects extra fields")
        if self.bit_width is not None:
            raise ValueError(f"{kind.value} declared type rejects extra fields")


@dataclass(frozen=True, slots=True)
class Utf8LogicalLiteral:
    text: str
    kind: Literal["utf8-logical-literal"] = "utf8-logical-literal"


@dataclass(frozen=True, slots=True)
class RawLogicalLiteral:
    raw_bytes: bytes
    kind: Literal["raw-logical-literal"] = "raw-logical-literal"


LogicalLiteral = Utf8LogicalLiteral | RawLogicalLiteral


@dataclass(frozen=True, slots=True)
class NullScalar:
    kind: Literal["null"] = "null"


@dataclass(frozen=True, slots=True)
class BooleanScalar:
    value: bool
    kind: Literal["boolean"] = "boolean"


@dataclass(frozen=True, slots=True)
class SignedIntegerScalar:
    decimal: str
    kind: Literal["signed-integer"] = "signed-integer"


@dataclass(frozen=True, slots=True)
class UnsignedIntegerScalar:
    decimal: str
    kind: Literal["unsigned-integer"] = "unsigned-integer"


@dataclass(frozen=True, slots=True)
class DecimalScalar:
    decimal: str
    kind: Literal["decimal"] = "decimal"


@dataclass(frozen=True, slots=True)
class Float32Scalar:
    bits_hex: str
    kind: Literal["float32"] = "float32"


@dataclass(frozen=True, slots=True)
class Float64Scalar:
    bits_hex: str
    kind: Literal["float64"] = "float64"


@dataclass(frozen=True, slots=True)
class StringScalar:
    text: str
    kind: Literal["string"] = "string"


@dataclass(frozen=True, slots=True)
class BinaryScalar:
    raw_bytes: bytes
    kind: Literal["binary"] = "binary"


@dataclass(frozen=True, slots=True)
class BitScalar:
    raw_bytes: bytes
    kind: Literal["bit"] = "bit"


@dataclass(frozen=True, slots=True)
class DateScalar:
    text: str
    kind: Literal["date"] = "date"


@dataclass(frozen=True, slots=True)
class DateTimeScalar:
    text: str
    kind: Literal["datetime"] = "datetime"


@dataclass(frozen=True, slots=True)
class TimestampScalar:
    text: str
    kind: Literal["timestamp"] = "timestamp"


@dataclass(frozen=True, slots=True)
class TimeDurationScalar:
    text: str
    kind: Literal["time-duration"] = "time-duration"


@dataclass(frozen=True, slots=True)
class AnomalyScalar:
    envelope: Mapping[str, Any]
    kind: Literal["source-literal-anomaly"] = "source-literal-anomaly"


TypedScalar = (
    NullScalar
    | BooleanScalar
    | SignedIntegerScalar
    | UnsignedIntegerScalar
    | DecimalScalar
    | Float32Scalar
    | Float64Scalar
    | StringScalar
    | BinaryScalar
    | BitScalar
    | DateScalar
    | DateTimeScalar
    | TimestampScalar
    | TimeDurationScalar
    | AnomalyScalar
)


@dataclass(frozen=True, slots=True)
class EncodedScalar:
    payload: bytes
    scalar_frame: bytes


@dataclass(frozen=True, slots=True)
class NormalizedScalar:
    typed_value: TypedScalar
    payload: bytes
    scalar_frame: bytes


class DigestKind(StrEnum):
    """Closed formal registry of semantic digest kinds."""

    ROW = "row"
    RAW_CONTENT = "raw-content"
    COLLECTION_ITEM = "collection-item"
    VECTOR_SET = "vector-set"
    TABLE_SCHEMA = "table-schema"
    SCENARIO_INPUT = "scenario-input"
    SCENARIO_FIXTURE = "scenario-fixture"


FORMAL_DIGEST_KINDS: frozenset[DigestKind] = frozenset(DigestKind)

_DIGEST_REF_PREFIX = "sha256:"
_SHA256_HEX_LEN = 64
_RAW_DIGEST_LEN = 32


@dataclass(frozen=True, slots=True)
class DigestRef:
    """Wire digest reference: ``sha256:`` + 64 lowercase hex chars."""

    value: str

    def __post_init__(self) -> None:
        if not (
            self.value.startswith(_DIGEST_REF_PREFIX)
            and len(self.value) == len(_DIGEST_REF_PREFIX) + _SHA256_HEX_LEN
            and all(ch in "0123456789abcdef" for ch in self.value[len(_DIGEST_REF_PREFIX) :])
        ):
            raise ValueError("DigestRef must be sha256: + 64 lowercase hex characters")

    @classmethod
    def from_raw_digest(cls, raw_digest: bytes) -> DigestRef:
        if len(raw_digest) != _RAW_DIGEST_LEN:
            raise ValueError("raw digest must be exactly 32 bytes")
        return cls(f"{_DIGEST_REF_PREFIX}{raw_digest.hex()}")

    @property
    def raw_digest(self) -> bytes:
        return bytes.fromhex(self.value[len(_DIGEST_REF_PREFIX) :])


@dataclass(frozen=True, slots=True)
class SemanticDigest:
    """Domain-separated semantic digest result."""

    kind: DigestKind
    raw_digest: bytes
    digest_ref: DigestRef

    def __post_init__(self) -> None:
        if len(self.raw_digest) != _RAW_DIGEST_LEN:
            raise ValueError("raw digest must be exactly 32 bytes")
        if self.digest_ref.raw_digest != self.raw_digest:
            raise ValueError("digest_ref must match raw_digest")

    @classmethod
    def from_raw(cls, kind: DigestKind, raw_digest: bytes) -> SemanticDigest:
        return cls(
            kind=kind,
            raw_digest=raw_digest,
            digest_ref=DigestRef.from_raw_digest(raw_digest),
        )


@dataclass(frozen=True, slots=True)
class RowField:
    """One row field prior to canonical identifier ordering and framing."""

    name: str
    declared_type: DeclaredType
    typed_value: TypedScalar


@dataclass(frozen=True, slots=True)
class EncodedRow:
    """Canonical row frame plus row semantic digest."""

    row_frame: bytes
    raw_hash: bytes
    digest_ref: DigestRef

    def __post_init__(self) -> None:
        if len(self.raw_hash) != _RAW_DIGEST_LEN:
            raise ValueError("row raw_hash must be exactly 32 bytes")
        if self.digest_ref.raw_digest != self.raw_hash:
            raise ValueError("digest_ref must match raw_hash")


class CollectionSemantics(StrEnum):
    SEQUENCE = "sequence"
    MULTISET = "multiset"
    SET = "set"
    KEYED_COLLECTION = "keyed-collection"


FORMAL_COLLECTION_SEMANTICS: frozenset[CollectionSemantics] = frozenset(CollectionSemantics)


@dataclass(frozen=True, slots=True)
class EncodedCollection:
    """Canonical collection frame only.

    Collection-level digests are computed separately via ``semantic_digest``
    with an owner-registered ``DigestKind``; Shared Kernel has no generic
    collection-frame digest kind.
    """

    collection_frame: bytes
