"""Two-entry Repository import package encode, decode, and safety checks."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
from typing import Any

import compression.zstd
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.storage_projection._digest import (
    compute_manifest_digest,
    manifest_document,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    MAX_MANIFEST_JSON_BYTES,
    MAX_REPLAY_SQL_BYTES,
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    ProjectionDiagnosticCode,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
    WrittenImportPackage,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    canonicalize_rule_identifier,
)

MANIFEST_ENTRY_NAME = "manifest.json"
REPLAY_SQL_ENTRY_NAME = "replay.sql"
_FILE_MODE = 0o644
_TAR_HEADER_SLACK = 64 * 1024
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_DURABLE_KEYS = (
    "contract_version",
    "manifest_digest",
    "ruleset_digest",
    "ruleset_id",
    "ruleset_version",
    "source_artifact_digest",
    "storage_projection_version",
    "tables",
)
_DURABLE_TABLE_KEYS = (
    "canonical_key_columns",
    "canonical_key_policy",
    "canonical_row_count",
    "canonical_schema_digest",
    "content_digest",
    "dropped_columns",
    "gid_pseudo_count",
    "gid_real_count",
    "name",
    "ordered_policy",
    "ordering_digest",
    "retained_columns",
    "source_row_count",
    "source_schema_digest",
    "structural_columns",
)
_DROPPED_KEYS = ("name", "reason")
_PACKAGE_KEYS = ("canonicalization_manifest_digest", "package_version", "tables")
_PACKAGE_TABLE_KEYS = ("name", "row_count", "schema")
_SCHEMA_KEYS = ("columns", "primary_key")
_COLUMN_KEYS = ("name", "nullable", "sql_type")
_IJSON_MAX = (2**53) - 1


class PackageError(ValueError):
    def __init__(self, code: ProjectionDiagnosticCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def durable_manifest_bytes(manifest: CanonicalizationManifest) -> bytes:
    if type(manifest) is not CanonicalizationManifest:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest must be CanonicalizationManifest",
        )
    if manifest.contract_version != CANONICALIZATION_MANIFEST_CONTRACT:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "new manifest writes require the current contract_version",
        )
    if manifest.storage_projection_version != STORAGE_PROJECTION_VERSION:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "new manifest writes require the current storage_projection_version",
        )
    if manifest.manifest_digest is None:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "durable manifest requires manifest_digest",
        )
    document = dict(manifest_document(manifest))
    document["manifest_digest"] = manifest.manifest_digest.value
    payload = canonicalize_json_value(document)
    if len(payload) > MAX_MANIFEST_JSON_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "manifest.json exceeds max_manifest_json_bytes",
        )
    return payload


def canonicalization_manifest_from_bytes(payload: bytes) -> CanonicalizationManifest:
    if type(payload) is not bytes:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "durable manifest must be bytes",
        )
    if len(payload) > MAX_MANIFEST_JSON_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "manifest.json exceeds max_manifest_json_bytes",
        )
    document = _loads_object(payload, "durable manifest")
    mapping = _exact_object(document, _DURABLE_KEYS, "durable manifest")
    tables_raw = _array(mapping["tables"], "tables")
    tables = tuple(_durable_table(item, index) for index, item in enumerate(tables_raw))
    try:
        manifest = CanonicalizationManifest(
            contract_version=_text(mapping["contract_version"], "contract_version"),
            storage_projection_version=_text(
                mapping["storage_projection_version"],
                "storage_projection_version",
            ),
            ruleset_id=_text(mapping["ruleset_id"], "ruleset_id"),
            ruleset_version=_text(mapping["ruleset_version"], "ruleset_version"),
            ruleset_digest=_digest(mapping["ruleset_digest"], "ruleset_digest"),
            source_artifact_digest=_digest(
                mapping["source_artifact_digest"],
                "source_artifact_digest",
            ),
            tables=tables,
            manifest_digest=_digest(mapping["manifest_digest"], "manifest_digest"),
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc
    recomputed = compute_manifest_digest(manifest)
    if recomputed != manifest.manifest_digest:
        raise PackageError(
            ProjectionDiagnosticCode.DIGEST_MISMATCH,
            "durable manifest digest mismatch",
        )
    return manifest


def repository_import_manifest_bytes(import_input: RepositoryImportArtifactInput) -> bytes:
    if type(import_input) is not RepositoryImportArtifactInput:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "import_input must be RepositoryImportArtifactInput",
        )
    tables = sorted(import_input.tables, key=lambda table: table.name.encode("utf-8"))
    document: dict[str, object] = {
        "package_version": import_input.package_version,
        "canonicalization_manifest_digest": import_input.canonicalization_manifest_digest.value,
        "tables": [
            {
                "name": table.name,
                "schema": {
                    "columns": [
                        {
                            "name": column.name,
                            "sql_type": column.sql_type,
                            "nullable": column.nullable,
                        }
                        for column in table.columns
                    ],
                    "primary_key": list(table.primary_key),
                },
                "row_count": table.row_count,
            }
            for table in tables
        ],
    }
    payload = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_MANIFEST_JSON_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "manifest.json exceeds max_manifest_json_bytes",
        )
    return payload


def repository_import_input_from_bytes(payload: bytes) -> RepositoryImportArtifactInput:
    document = _loads_object(payload, "package manifest")
    mapping = _exact_object(document, _PACKAGE_KEYS, "package manifest")
    tables_raw = _array(mapping["tables"], "tables")
    tables = tuple(_package_table(item, index) for index, item in enumerate(tables_raw))
    try:
        return RepositoryImportArtifactInput(
            package_version=_int(mapping["package_version"], "package_version"),
            canonicalization_manifest_digest=_digest(
                mapping["canonicalization_manifest_digest"],
                "canonicalization_manifest_digest",
            ),
            tables=tables,
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def build_repository_import_package(
    *,
    import_input: RepositoryImportArtifactInput,
    replay_sql: bytes,
) -> WrittenImportPackage:
    manifest_bytes = repository_import_manifest_bytes(import_input)
    return pack_repository_import_entries(manifest_bytes, replay_sql)


def validate_repository_import_package(payload: bytes) -> RepositoryImportArtifactInput:
    manifest_bytes, _replay_sql = unpack_repository_import_entries(payload)
    return repository_import_input_from_bytes(manifest_bytes)


def pack_repository_import_entries(manifest_bytes: bytes, replay_sql: bytes) -> WrittenImportPackage:
    if type(manifest_bytes) is not bytes:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest.json must be bytes",
        )
    if type(replay_sql) is not bytes:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "replay.sql must be bytes",
        )
    if len(manifest_bytes) > MAX_MANIFEST_JSON_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "manifest.json exceeds max_manifest_json_bytes",
        )
    if len(replay_sql) > MAX_REPLAY_SQL_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "replay.sql exceeds max_replay_sql_bytes",
        )
    _decode_utf8(manifest_bytes, "manifest.json")
    tar_bytes = _build_ustar(
        (
            (MANIFEST_ENTRY_NAME, manifest_bytes),
            (REPLAY_SQL_ENTRY_NAME, replay_sql),
        )
    )
    payload = compression.zstd.compress(tar_bytes)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return WrittenImportPackage(payload=payload, size_bytes=len(payload), sha256=digest)


def unpack_repository_import_entries(payload: bytes) -> tuple[bytes, bytes]:
    if type(payload) is not bytes:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "package payload must be bytes",
        )
    tar_bytes = _decompress_zstd(payload)
    try:
        archive = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:")
    except tarfile.TarError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "import package tar is malformed",
        ) from exc
    with archive:
        members = archive.getmembers()
        if len(members) != 2:
            raise PackageError(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "import package must contain exactly two regular files",
            )
        first = _read_regular_member(archive, members[0], MANIFEST_ENTRY_NAME)
        second = _read_regular_member(archive, members[1], REPLAY_SQL_ENTRY_NAME)
    if len(first) > MAX_MANIFEST_JSON_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "manifest.json exceeds max_manifest_json_bytes",
        )
    if len(second) > MAX_REPLAY_SQL_BYTES:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "replay.sql exceeds max_replay_sql_bytes",
        )
    _decode_utf8(first, "manifest.json")
    return first, second


def _build_ustar(entries: tuple[tuple[str, bytes], ...]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in entries:
            if name not in {MANIFEST_ENTRY_NAME, REPLAY_SQL_ENTRY_NAME}:
                raise PackageError(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    f"unexpected tar entry {name!r}",
                )
            info = tarfile.TarInfo(name=name)
            info.type = tarfile.REGTYPE
            info.size = len(payload)
            info.mode = _FILE_MODE
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _decompress_zstd(payload: bytes) -> bytes:
    limit = MAX_MANIFEST_JSON_BYTES + MAX_REPLAY_SQL_BYTES + _TAR_HEADER_SLACK
    decompressor = compression.zstd.ZstdDecompressor()
    try:
        output = decompressor.decompress(payload, max_length=limit)
    except (compression.zstd.ZstdError, EOFError) as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "zstd payload is malformed",
        ) from exc
    if not decompressor.eof:
        raise PackageError(
            ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "expanded package exceeds budget",
        )
    return output


def _read_regular_member(archive: tarfile.TarFile, member: tarfile.TarInfo, expected: str) -> bytes:
    if member.issym() or member.islnk():
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "symlink and hardlink members are refused",
        )
    if member.isdev() or member.isfifo() or member.isdir():
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "non-regular archive members are refused",
        )
    if not member.isreg():
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "non-regular archive members are refused",
        )
    if member.pax_headers:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "extended archive metadata is refused",
        )
    unsafe = _unsafe_member_name(member.name)
    if unsafe is not None:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, unsafe)
    if member.name != expected:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"archive member {member.name!r} must be {expected!r}",
        )
    extracted = archive.extractfile(member)
    if extracted is None:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "regular archive member has no payload",
        )
    content = extracted.read()
    if member.size != len(content):
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "archive member size does not match payload",
        )
    return content


def _unsafe_member_name(name: str) -> str | None:
    if type(name) is not str or name == "":
        return "archive member name must be a non-empty string"
    if "\x00" in name or "\\" in name:
        return "archive member name must not contain NUL or backslash"
    lowered = name.casefold()
    if name.startswith("/") or name.startswith("//") or lowered.startswith("file:"):
        return "archive member name must not be an absolute path"
    if _WINDOWS_DRIVE.match(name) is not None:
        return "archive member name must not be an absolute path"
    parts = name.split("/")
    if any(part == "" or part in {".", ".."} for part in parts):
        return "archive member name must not contain empty, . or .. segments"
    return None


def _durable_table(value: object, index: int) -> CanonicalizationManifestTable:
    mapping = _exact_object(value, _DURABLE_TABLE_KEYS, f"tables[{index}]")
    dropped_raw = _array(mapping["dropped_columns"], f"tables[{index}].dropped_columns")
    dropped = tuple(_dropped_column(item, index, drop_index) for drop_index, item in enumerate(dropped_raw))
    try:
        return CanonicalizationManifestTable(
            name=_text(mapping["name"], "name"),
            source_row_count=_int(mapping["source_row_count"], "source_row_count"),
            canonical_row_count=_int(mapping["canonical_row_count"], "canonical_row_count"),
            canonical_key_policy=_key_policy(mapping["canonical_key_policy"]),
            ordered_policy=_ordered_policy(mapping["ordered_policy"]),
            retained_columns=_name_tuple(mapping["retained_columns"], "retained_columns"),
            structural_columns=_name_tuple(mapping["structural_columns"], "structural_columns"),
            dropped_columns=dropped,
            canonical_key_columns=_name_tuple(mapping["canonical_key_columns"], "canonical_key_columns"),
            source_schema_digest=_optional_digest(
                mapping["source_schema_digest"],
                "source_schema_digest",
            ),
            canonical_schema_digest=_optional_digest(
                mapping["canonical_schema_digest"],
                "canonical_schema_digest",
            ),
            content_digest=_optional_digest(mapping["content_digest"], "content_digest"),
            ordering_digest=_optional_digest(mapping["ordering_digest"], "ordering_digest"),
            gid_real_count=_optional_int(mapping["gid_real_count"], "gid_real_count"),
            gid_pseudo_count=_optional_int(mapping["gid_pseudo_count"], "gid_pseudo_count"),
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def _dropped_column(value: object, table_index: int, drop_index: int) -> DroppedColumn:
    mapping = _exact_object(
        value,
        _DROPPED_KEYS,
        f"tables[{table_index}].dropped_columns[{drop_index}]",
    )
    try:
        return DroppedColumn(
            name=_text(mapping["name"], "name"),
            reason=_text(mapping["reason"], "reason"),
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def _package_table(value: object, index: int) -> RepositoryImportTable:
    mapping = _exact_object(value, _PACKAGE_TABLE_KEYS, f"tables[{index}]")
    schema = _exact_object(mapping["schema"], _SCHEMA_KEYS, f"tables[{index}].schema")
    columns_raw = _array(schema["columns"], f"tables[{index}].schema.columns")
    columns = tuple(
        _package_column(item, index, column_index) for column_index, item in enumerate(columns_raw)
    )
    try:
        return RepositoryImportTable(
            name=_text(mapping["name"], "name"),
            columns=columns,
            primary_key=_name_tuple(schema["primary_key"], "primary_key"),
            row_count=_int(mapping["row_count"], "row_count"),
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def _package_column(value: object, table_index: int, column_index: int) -> RepositoryImportColumn:
    mapping = _exact_object(
        value,
        _COLUMN_KEYS,
        f"tables[{table_index}].schema.columns[{column_index}]",
    )
    try:
        return RepositoryImportColumn(
            name=_text(mapping["name"], "name"),
            sql_type=_text(mapping["sql_type"], "sql_type"),
            nullable=_bool(mapping["nullable"], "nullable"),
        )
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def _loads_object(payload: bytes, label: str) -> dict[str, object]:
    text = _decode_utf8(payload, label)
    try:
        loaded: Any = json.loads(text, object_pairs_hook=_unique_object_pairs)
    except json.JSONDecodeError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} is not UTF-8 JSON",
        ) from exc
    if type(loaded) is not dict:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} must be an object")
    return loaded


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise PackageError(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "JSON object members must be unique",
            )
        seen.add(key)
        mapping[key] = value
    return mapping


def _exact_object(value: object, allowed: tuple[str, ...], label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} must be an object")
    keys = set(value)
    allowed_keys = set(allowed)
    extra = keys - allowed_keys
    if extra:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} has unknown field")
    missing = allowed_keys - keys
    if missing:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} is missing a required field",
        )
    return value


def _array(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or value == "":
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} must be a non-empty string",
        )
    return value


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} must be a boolean")
    return value


def _int(value: object, label: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0 or value > _IJSON_MAX:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} must be a non-negative I-JSON integer",
        )
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _int(value, label)


def _digest(value: object, label: str) -> DigestRef:
    if type(value) is not str:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, f"{label} must be a digest string")
    try:
        return DigestRef(value)
    except ValueError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} is not a valid digest",
        ) from exc


def _optional_digest(value: object, label: str) -> DigestRef | None:
    if value is None:
        return None
    return _digest(value, label)


def _name_tuple(value: object, label: str) -> tuple[str, ...]:
    names = _array(value, label)
    try:
        return tuple(canonicalize_rule_identifier(_text(item, label)) for item in names)
    except ValueError as exc:
        raise PackageError(ProjectionDiagnosticCode.BINDING_INVALID, str(exc)) from exc


def _key_policy(value: object) -> CanonicalKeyPolicy:
    text = _text(value, "canonical_key_policy")
    try:
        return CanonicalKeyPolicy(text)
    except ValueError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "canonical_key_policy is not supported",
        ) from exc


def _ordered_policy(value: object) -> OrderedPolicy:
    text = _text(value, "ordered_policy")
    try:
        return OrderedPolicy(text)
    except ValueError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "ordered_policy is not supported",
        ) from exc


def _decode_utf8(payload: bytes, label: str) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} must not include a UTF-8 BOM",
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"{label} must be UTF-8",
        ) from exc
