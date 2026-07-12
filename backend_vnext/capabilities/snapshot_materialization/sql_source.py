from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
import gzip
from typing import Final

from ...artifacts import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from .source_package import (
    SQL_DUMP_REQUIRED_PATH,
    SourceDocumentRef,
    SourcePackage,
    SourcePackageStagingResult,
    get_source_package,
    load_source_document_bytes,
    resolve_required_sql_document,
    resolve_source_document_content_path,
    stage_source_package,
)
from .versions import SQL_DUMP_SOURCE_CONTRACT_VERSION


DEFAULT_SQL_ENCODING: Final = "utf-8"
DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES: Final = 1024 * 1024


def _coerce_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _diagnostics_payload(
    diagnostics: tuple[DiagnosticRecord, ...],
) -> tuple[DiagnosticRecord, ...]:
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class SqlDumpSource:
    source_document_ref: SourceDocumentRef
    sql_source_digest: DigestRef | str
    parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION
    encoding: str = DEFAULT_SQL_ENCODING
    source_size_bytes: int = 0
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    source_path: Path | None = field(default=None, repr=False)
    source_bytes: bytes | None = field(default=None, repr=False)
    source_text: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_document_ref, SourceDocumentRef):
            raise TypeError("source_document_ref must be a SourceDocumentRef")
        object.__setattr__(self, "sql_source_digest", _coerce_digest(self.sql_source_digest))
        if not isinstance(self.parser_input_contract_version, str) or not self.parser_input_contract_version:
            raise ValueError("parser_input_contract_version must be a non-empty string")
        if not isinstance(self.encoding, str) or not self.encoding:
            raise ValueError("encoding must be a non-empty string")
        if (
            not isinstance(self.source_size_bytes, int)
            or isinstance(self.source_size_bytes, bool)
            or self.source_size_bytes < 0
        ):
            raise ValueError("source_size_bytes must be a non-negative integer")
        source_path = self.source_path
        if source_path is not None and not isinstance(source_path, Path):
            raise TypeError("source_path must be a Path or None")
        source_bytes = None if self.source_bytes is None else bytes(self.source_bytes)
        source_text = self.source_text
        if source_path is None and source_bytes is None and source_text is None:
            raise ValueError("source_path, source_bytes or source_text must be provided")
        if source_bytes is None and source_text is not None:
            source_bytes = source_text.encode(self.encoding)
        if source_text is None and source_bytes is not None:
            source_text = source_bytes.decode(self.encoding)
        object.__setattr__(self, "source_bytes", source_bytes)
        object.__setattr__(self, "source_text", source_text)
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.source_size_bytes == 0 and source_bytes is not None:
            object.__setattr__(self, "source_size_bytes", len(source_bytes))
        if self.source_size_bytes == 0 and source_path is not None:
            object.__setattr__(self, "source_size_bytes", source_path.stat().st_size)
        if source_text is not None:
            actual_digest = DigestRef.from_bytes(source_text.encode("utf-8"))
            if self.sql_source_digest != actual_digest:
                raise ValueError("sql_source_digest does not match source_text")

    @classmethod
    def from_text(
        cls,
        source_document_ref: SourceDocumentRef,
        source_text: str,
        *,
        parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION,
        encoding: str = DEFAULT_SQL_ENCODING,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
    ) -> "SqlDumpSource":
        source_bytes = source_text.encode(encoding)
        return cls(
            source_document_ref=source_document_ref,
            sql_source_digest=DigestRef.from_bytes(source_text.encode("utf-8")),
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding,
            source_size_bytes=len(source_bytes),
            diagnostics=diagnostics,
            source_path=None,
            source_bytes=source_bytes,
            source_text=source_text,
        )

    @classmethod
    def from_bytes(
        cls,
        source_document_ref: SourceDocumentRef,
        source_bytes: bytes,
        *,
        parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION,
        encoding: str = DEFAULT_SQL_ENCODING,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
    ) -> "SqlDumpSource":
        source_text = source_bytes.decode(encoding)
        return cls(
            source_document_ref=source_document_ref,
            sql_source_digest=DigestRef.from_bytes(source_text.encode("utf-8")),
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding,
            source_size_bytes=len(source_bytes),
            diagnostics=diagnostics,
            source_path=None,
            source_bytes=source_bytes,
            source_text=source_text,
        )

    @classmethod
    def from_file(
        cls,
        source_document_ref: SourceDocumentRef,
        source_path: Path,
        *,
        sql_source_digest: DigestRef | str,
        parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION,
        encoding: str = DEFAULT_SQL_ENCODING,
        source_size_bytes: int = 0,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
    ) -> "SqlDumpSource":
        return cls(
            source_document_ref=source_document_ref,
            sql_source_digest=sql_source_digest,
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding,
            source_size_bytes=source_size_bytes,
            diagnostics=diagnostics,
            source_path=source_path,
            source_bytes=None,
            source_text=None,
        )

    @property
    def file_backed(self) -> bool:
        return self.source_path is not None and self.source_text is None

    def iter_text_chunks(
        self,
        *,
        chunk_size_bytes: int = DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES,
    ):
        if self.source_text is not None:
            yield self.source_text
            return
        if self.source_bytes is not None:
            yield self.source_bytes.decode(self.encoding)
            return
        if self.source_path is None:
            raise ValueError("SQL source has no readable content")
        with self.source_path.open("r", encoding=self.encoding) as handle:
            while True:
                chunk = handle.read(chunk_size_bytes)
                if not chunk:
                    break
                yield chunk


def resolve_sql_dump_source(
    source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | ArtifactRef | Path | str | bytes | bytearray | memoryview,
    *,
    parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION,
    encoding_policy: str = DEFAULT_SQL_ENCODING,
) -> SqlDumpSource:
    if isinstance(source, SqlDumpSource):
        return source
    if isinstance(source, SourceDocumentRef):
        encoding = source.encoding_hint or encoding_policy
        try:
            source_path = resolve_source_document_content_path(source)
        except (KeyError, ValueError):
            source_bytes = load_source_document_bytes(source)
            return SqlDumpSource.from_bytes(
                source,
                source_bytes,
                parser_input_contract_version=parser_input_contract_version,
                encoding=encoding,
            )
        return SqlDumpSource.from_file(
            source,
            source_path,
            sql_source_digest=source.document_content_digest,
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding,
            source_size_bytes=source.size_bytes,
        )
    if isinstance(source, SourcePackageStagingResult):
        if source.required_sql_document_ref is not None:
            return resolve_sql_dump_source(
                source.required_sql_document_ref,
                parser_input_contract_version=parser_input_contract_version,
                encoding_policy=encoding_policy,
            )
        return resolve_sql_dump_source(
            resolve_required_sql_document(source),
            parser_input_contract_version=parser_input_contract_version,
            encoding_policy=encoding_policy,
        )
    if isinstance(source, SourcePackage):
        return resolve_sql_dump_source(
            resolve_required_sql_document(source),
            parser_input_contract_version=parser_input_contract_version,
            encoding_policy=encoding_policy,
        )
    if isinstance(source, ArtifactRef):
        return resolve_sql_dump_source(
            resolve_required_sql_document(source),
            parser_input_contract_version=parser_input_contract_version,
            encoding_policy=encoding_policy,
        )
    if isinstance(source, Path):
        if source.is_dir() or _looks_like_package_container(source):
            staged = stage_source_package(source)
            return resolve_sql_dump_source(
                staged,
                parser_input_contract_version=parser_input_contract_version,
                encoding_policy=encoding_policy,
            )
        if source.suffix.lower() == ".gz":
            source_bytes = gzip.decompress(source.read_bytes())
            synthetic_ref = _synthetic_source_document_ref(
                source_bytes,
                encoding=encoding_policy,
            )
            return SqlDumpSource.from_bytes(
                synthetic_ref,
                source_bytes,
                parser_input_contract_version=parser_input_contract_version,
                encoding=encoding_policy,
            )
        source_text = source.read_text(encoding=encoding_policy)
        synthetic_ref = _synthetic_source_document_ref(
            source_text.encode("utf-8"),
            encoding=encoding_policy,
        )
        return SqlDumpSource.from_text(
            synthetic_ref,
            source_text,
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding_policy,
        )
    if isinstance(source, (bytes, bytearray, memoryview)):
        raw_bytes = bytes(source)
        if raw_bytes.startswith(b"\x1f\x8b"):
            raw_bytes = gzip.decompress(raw_bytes)
        source_text = raw_bytes.decode(encoding_policy)
        synthetic_ref = _synthetic_source_document_ref(
            source_text.encode("utf-8"),
            encoding=encoding_policy,
        )
        return SqlDumpSource.from_text(
            synthetic_ref,
            source_text,
            parser_input_contract_version=parser_input_contract_version,
            encoding=encoding_policy,
        )
    if isinstance(source, str):
        if any(marker in source for marker in ("\n", "\r", ";")):
            return resolve_sql_dump_source(
                source.encode(encoding_policy),
                parser_input_contract_version=parser_input_contract_version,
                encoding_policy=encoding_policy,
            )
        path = Path(source)
        try:
            if path.exists():
                return resolve_sql_dump_source(
                    path,
                    parser_input_contract_version=parser_input_contract_version,
                    encoding_policy=encoding_policy,
                )
        except OSError:
            return resolve_sql_dump_source(
                source.encode(encoding_policy),
                parser_input_contract_version=parser_input_contract_version,
                encoding_policy=encoding_policy,
            )
        return resolve_sql_dump_source(
            source.encode(encoding_policy),
            parser_input_contract_version=parser_input_contract_version,
            encoding_policy=encoding_policy,
        )
    raise TypeError(f"unsupported SQL dump source: {type(source)!r}")


def _synthetic_source_document_ref(source_bytes: bytes, *, encoding: str) -> SourceDocumentRef:
    sql_text = source_bytes.decode(encoding)
    sql_source_digest = DigestRef.from_bytes(sql_text.encode("utf-8"))
    synthetic_package_id = f"compat:{sql_source_digest.hex_digest}"
    entry_manifest_digest = DigestRef.from_payload(
        {
            "schema_version": SQL_DUMP_SOURCE_CONTRACT_VERSION,
            "source_package_id": synthetic_package_id,
            "normalized_path": SQL_DUMP_REQUIRED_PATH,
            "document_content_digest": sql_source_digest.to_payload(),
            "size_bytes": len(sql_text.encode("utf-8")),
        }
    )
    return SourceDocumentRef(
        source_package_id=synthetic_package_id,
        normalized_path=SQL_DUMP_REQUIRED_PATH,
        document_kind="SQL_DUMP",
        document_content_digest=sql_source_digest,
        size_bytes=len(sql_text.encode("utf-8")),
        encoding_hint=encoding,
        entry_manifest_digest=entry_manifest_digest,
    )


def _looks_like_package_container(path: Path) -> bool:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    return path.suffix.lower() == ".zip" or suffixes[-2:] == [".tar", ".gz"] or path.suffix.lower() == ".tgz"


__all__ = [
    "DEFAULT_SQL_ENCODING",
    "SqlDumpSource",
    "resolve_sql_dump_source",
]
