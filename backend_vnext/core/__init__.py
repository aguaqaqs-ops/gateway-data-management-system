"""Core primitives for backend_vnext."""

from .digests import DigestRef, canonical_json_bytes, stable_sha256
from .diagnostics import DiagnosticRecord, Diagnostics, Error, ErrorRecord
from .results import BenchmarkRunResult, Result, ResultRecord
from .identifiers import canonical_identifier
from .row_digests import stable_rows_digest, stable_snapshot_rows_digest
from .scalar_encoding import (
    normalize_json_rows,
    normalize_json_scalar_value,
    normalize_parquet_rows,
    normalize_parquet_scalar_value,
    normalize_snapshot_rows,
    normalize_snapshot_scalar_value,
    parquet_scalar_value_normalizer,
    scalar_type_family,
)
from .validation import ensure_bundle_relative_path, require_non_empty
from .versions import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    BENCHMARK_RESULT_SCHEMA_VERSION,
    CORE_CONTRACT_VERSION,
    DIGEST_ALGORITHM,
    LOCAL_ARTIFACT_STORE_SCHEMA_VERSION,
)

__all__ = [
    "ARTIFACT_MANIFEST_SCHEMA_VERSION",
    "BENCHMARK_RESULT_SCHEMA_VERSION",
    "BenchmarkRunResult",
    "CORE_CONTRACT_VERSION",
    "DIGEST_ALGORITHM",
    "DigestRef",
    "DiagnosticRecord",
    "Diagnostics",
    "Error",
    "ErrorRecord",
    "ensure_bundle_relative_path",
    "LOCAL_ARTIFACT_STORE_SCHEMA_VERSION",
    "Result",
    "ResultRecord",
    "canonical_identifier",
    "require_non_empty",
    "canonical_json_bytes",
    "normalize_json_rows",
    "normalize_json_scalar_value",
    "normalize_parquet_rows",
    "normalize_parquet_scalar_value",
    "normalize_snapshot_rows",
    "normalize_snapshot_scalar_value",
    "parquet_scalar_value_normalizer",
    "scalar_type_family",
    "stable_rows_digest",
    "stable_snapshot_rows_digest",
    "stable_sha256",
]
