"""Tests for bounded Repository import package validation and extraction."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from collections.abc import Callable
from pathlib import Path

import compression.zstd
import pytest

from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.models import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    ImportPackageRejected,
    ValidatedImportPackage,
)
from gateway_repository_service.versioned_import.package import (
    validate_and_extract_import_package,
)


def tiny_manifest_dict() -> dict[str, object]:
    return {
        "package_version": 1,
        "canonicalization_manifest_digest": "d",
        "tables": [
            {
                "name": "t",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }


def build_valid_manifest_dict() -> dict[str, object]:
    return {
        "package_version": 1,
        "canonicalization_manifest_digest": "manifest-digest-1",
        "tables": [
            {
                "name": "records",
                "schema": {
                    "columns": [
                        {"name": "id", "sql_type": "BIGINT", "nullable": False},
                    ],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }


def _tar_header(name: str, size: int, *, typeflag: bytes = b"0") -> bytes:
    header = bytearray(512)
    name_bytes = name.encode("utf-8")[:100]
    header[0 : len(name_bytes)] = name_bytes
    size_field = f"{size:o}".encode("ascii")
    header[124 : 124 + len(size_field)] = size_field
    header[156:157] = typeflag
    header[148:156] = b"        "
    checksum = sum(header)
    checksum_field = f"{checksum:o}\0".encode("ascii")
    header[148 : 148 + len(checksum_field)] = checksum_field
    return bytes(header)


def _tar_record(name: str, payload: bytes, *, typeflag: bytes = b"0") -> bytes:
    padding = (512 - (len(payload) % 512)) % 512
    return _tar_header(name, len(payload), typeflag=typeflag) + payload + (b"\x00" * padding)


def build_tar_bytes(
    entries: list[tuple[str, bytes]],
    *,
    tar_format: int = tarfile.USTAR_FORMAT,
    mutate: Callable[[tarfile.TarInfo, str, bytes], None] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tar_format) as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.type = tarfile.REGTYPE
            info.mode = 0o644
            if mutate is not None:
                mutate(info, name, payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


_TAR_EOF_BLOCKS = b"\x00" * 1024


def build_raw_tar_bytes(entries: list[tuple[str, bytes, bytes]], *, include_eof: bool = True) -> bytes:
    payload = b"".join(_tar_record(name, data, typeflag=typeflag) for name, data, typeflag in entries)
    if include_eof:
        payload += _TAR_EOF_BLOCKS
    return payload


def compress_zstd(payload: bytes) -> bytes:
    return compression.zstd.compress(payload)


def compress_zstd_with_checksum(payload: bytes) -> bytes:
    return compression.zstd.compress(
        payload,
        options={compression.zstd.CompressionParameter.checksum_flag: 1},
    )


def build_package_bytes(
    *,
    manifest: dict[str, object] | None = None,
    replay_sql: bytes = b"SELECT 1;\n",
    entries: list[tuple[str, bytes]] | None = None,
    tar_bytes: bytes | None = None,
    tar_format: int = tarfile.USTAR_FORMAT,
    mutate: Callable[[tarfile.TarInfo, str, bytes], None] | None = None,
    trailing: bytes = b"",
) -> bytes:
    if tar_bytes is not None:
        return compress_zstd(tar_bytes) + trailing
    manifest_payload = json.dumps(manifest or build_valid_manifest_dict(), separators=(",", ":")).encode(
        "utf-8"
    )
    if entries is None:
        entries = [
            (MANIFEST_ENTRY_NAME, manifest_payload),
            (REPLAY_SQL_ENTRY_NAME, replay_sql),
        ]
    built_tar = build_tar_bytes(entries, tar_format=tar_format, mutate=mutate)
    return compress_zstd(built_tar) + trailing


def write_artifact(path: Path, payload: bytes) -> tuple[int, str]:
    path.write_bytes(payload)
    return len(payload), hashlib.sha256(payload).hexdigest()


@pytest.fixture
def settings(tmp_path: Path) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        data_root=tmp_path / "root",
        profile="test",
        bearer_token="token",
    )


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    return tmp_path / "staging"


def validate_package(
    artifact_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    payload: bytes | None = None,
) -> ValidatedImportPackage:
    if payload is None:
        payload = artifact_path.read_bytes()
    size_bytes, raw_sha256 = write_artifact(artifact_path, payload)
    return validate_and_extract_import_package(
        artifact_path=artifact_path,
        expected_size_bytes=size_bytes,
        expected_raw_sha256=raw_sha256,
        staging_dir=staging_dir,
        settings=settings,
    )


def test_valid_package_happy_path(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    replay_sql = b"CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
    payload = build_package_bytes(replay_sql=replay_sql)
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(artifact_path, staging_dir, settings, payload)

    assert result.manifest.package_version == 1
    assert result.manifest.canonicalization_manifest_digest == "manifest-digest-1"
    assert result.manifest.tables[0].name == "records"
    assert result.manifest_path.read_bytes() == json.dumps(
        build_valid_manifest_dict(), separators=(",", ":")
    ).encode("utf-8")
    assert result.replay_sql_path.read_bytes() == replay_sql
    assert staging_dir.exists()


@pytest.mark.parametrize(
    ("entries", "match"),
    [
        ([(REPLAY_SQL_ENTRY_NAME, b"x"), (MANIFEST_ENTRY_NAME, b"{}")], "invalid"),
        ([(MANIFEST_ENTRY_NAME, b"{}")], "not allowed|malformed|EOF"),
        (
            [
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b"x"),
                ("extra.txt", b"x"),
            ],
            "EOF|trailing",
        ),
        ([("replay.sql", b"x"), (MANIFEST_ENTRY_NAME, b"{}")], "invalid"),
    ],
)
def test_rejects_wrong_entry_layout(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    entries: list[tuple[str, bytes]],
    match: str,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    payload = build_package_bytes(entries=entries, manifest=tiny_manifest_dict())
    with pytest.raises(ImportPackageRejected, match=match):
        validate_package(artifact_path, staging_dir, settings, payload)
    assert not staging_dir.exists() or not any(staging_dir.iterdir())


@pytest.mark.parametrize(
    "entry_name",
    ["../manifest.json", "/manifest.json", "./manifest.json"],
)
def test_rejects_traversal_or_invalid_entry_names(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    entry_name: str,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    entries = [(entry_name, manifest_payload), (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n")]
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="invalid"):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(entries=entries))


@pytest.mark.parametrize(
    "typeflag",
    [
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.DIRTYPE,
        tarfile.FIFOTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.GNUTYPE_SPARSE,
    ],
)
def test_rejects_non_regular_tar_entries(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    typeflag: bytes,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    tar_bytes = build_raw_tar_bytes(
        [
            (MANIFEST_ENTRY_NAME, manifest_payload, typeflag),
            (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n", tarfile.REGTYPE),
        ]
    )
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(tar_bytes=tar_bytes))


def test_rejects_pax_headers(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    def mutate(info: tarfile.TarInfo, name: str, payload: bytes) -> None:
        if name == MANIFEST_ENTRY_NAME:
            info.pax_headers = {"comment": "evil"}

    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="extended|not allowed"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(
                manifest=tiny_manifest_dict(),
                tar_format=tarfile.PAX_FORMAT,
                mutate=mutate,
            ),
        )


def test_rejects_gnu_longname(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    long_name = "a" * 200
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    entries = [(long_name, manifest_payload), (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n")]
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(entries=entries, tar_format=tarfile.GNU_FORMAT),
        )


def test_rejects_trailing_compressed_garbage(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="trailing"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(trailing=b"GARBAGE"),
        )


def test_rejects_declared_size_mismatch(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    tar_bytes = build_raw_tar_bytes(
        [
            (MANIFEST_ENTRY_NAME, manifest_payload, tarfile.REGTYPE),
            (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n", tarfile.REGTYPE),
        ]
    )
    header = bytearray(_tar_header(MANIFEST_ENTRY_NAME, len(manifest_payload) + 1))
    tar_bytes = bytes(header) + tar_bytes[512:]
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="JSON|malformed|padding|payload"):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(tar_bytes=tar_bytes))


@pytest.mark.parametrize(
    ("manifest", "match"),
    [
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "tables": [
                    {
                        "name": "b",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["id"],
                        },
                        "row_count": 0,
                    },
                    {
                        "name": "a",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["id"],
                        },
                        "row_count": 0,
                    },
                ],
            },
            "validation",
        ),
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "tables": [
                    {
                        "name": "records",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["missing"],
                        },
                        "row_count": 0,
                    }
                ],
            },
            "validation",
        ),
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "extra": True,
                "tables": [
                    {
                        "name": "records",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["id"],
                        },
                        "row_count": 0,
                    }
                ],
            },
            "validation",
        ),
    ],
)
def test_rejects_invalid_manifest_contract(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    manifest: dict[str, object],
    match: str,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match=match):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(manifest=manifest))


def test_rejects_invalid_utf8_manifest(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="UTF-8"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(
                entries=[
                    (MANIFEST_ENTRY_NAME, b"\xff\xfe"),
                    (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n"),
                ]
            ),
        )


def test_rejects_duplicate_json_keys(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    duplicate_manifest = (
        b'{"package_version":1,"package_version":1,"canonicalization_manifest_digest":"d",'
        b'"tables":[{"name":"t","schema":{"columns":[{"name":"id","sql_type":"INT","nullable":false}],'
        b'"primary_key":["id"]},"row_count":0}]}'
    )
    with pytest.raises(ImportPackageRejected, match="duplicate"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(
                entries=[
                    (MANIFEST_ENTRY_NAME, duplicate_manifest),
                    (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n"),
                ]
            ),
        )


def test_rejects_bool_row_count(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest = tiny_manifest_dict()
    tables = manifest["tables"]
    assert isinstance(tables, list)
    table = tables[0]
    assert isinstance(table, dict)
    table["row_count"] = True
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="validation"):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(manifest=manifest))


def test_rejects_raw_size_mismatch(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    payload = build_package_bytes()
    artifact_path = tmp_path / "artifact.tar.zst"
    size_bytes, raw_sha256 = write_artifact(artifact_path, payload)
    with pytest.raises(ImportPackageRejected, match="raw size"):
        validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=size_bytes + 1,
            expected_raw_sha256=raw_sha256,
            staging_dir=staging_dir,
            settings=settings,
        )
    assert artifact_path.exists()
    assert not staging_dir.exists() or not any(staging_dir.iterdir())


@pytest.mark.parametrize(
    "size_delta",
    [-1, 1],
    ids=["expected_larger_than_actual", "expected_smaller_than_actual"],
)
def test_rejects_size_binding_before_extraction(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    size_delta: int,
) -> None:
    payload = build_package_bytes()
    artifact_path = tmp_path / "artifact.tar.zst"
    size_bytes, raw_sha256 = write_artifact(artifact_path, payload)
    with pytest.raises(ImportPackageRejected, match="raw size"):
        validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=size_bytes + size_delta,
            expected_raw_sha256=raw_sha256,
            staging_dir=staging_dir,
            settings=settings,
        )
    assert artifact_path.exists()
    assert not (staging_dir / "manifest.json").exists()
    assert not (staging_dir / "replay.sql").exists()


def test_rejects_streaming_size_growth_during_read(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service.versioned_import import package as package_module

    payload = build_package_bytes()
    artifact_path = tmp_path / "artifact.tar.zst"
    size_bytes, raw_sha256 = write_artifact(artifact_path, payload)
    original_read = package_module._CompressedArtifactSource._read_compressed_chunk

    def growing_read(self: package_module._CompressedArtifactSource) -> bytes:
        chunk = original_read(self)
        if chunk:
            self._compressed_bytes += 1
            self._enforce_compressed_byte_limits()
        return chunk

    monkeypatch.setattr(
        package_module._CompressedArtifactSource,
        "_read_compressed_chunk",
        growing_read,
    )

    with pytest.raises(ImportPackageRejected, match="raw size"):
        validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=size_bytes,
            expected_raw_sha256=raw_sha256,
            staging_dir=staging_dir,
            settings=settings,
        )
    assert artifact_path.exists()
    assert not (staging_dir / "manifest.json").exists()


def test_rejects_raw_sha_mismatch(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    payload = build_package_bytes()
    artifact_path = tmp_path / "artifact.tar.zst"
    size_bytes, raw_sha256 = write_artifact(artifact_path, payload)
    with pytest.raises(ImportPackageRejected, match="sha256"):
        validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=size_bytes,
            expected_raw_sha256="0" * 64 if raw_sha256 != "0" * 64 else "1" * 64,
            staging_dir=staging_dir,
            settings=settings,
        )


def test_failure_cleans_staging_and_preserves_artifact(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    payload = build_package_bytes(trailing=b"EXTRA")
    artifact_path = tmp_path / "artifact.tar.zst"
    write_artifact(artifact_path, payload)
    with pytest.raises(ImportPackageRejected):
        validate_package(artifact_path, staging_dir, settings)
    assert artifact_path.exists()
    assert not staging_dir.exists() or not any(staging_dir.iterdir())


def test_compressed_upload_boundary(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    payload = build_package_bytes(manifest=tiny_manifest_dict())
    exact_limit = len(payload)
    artifact_path = tmp_path / "artifact.tar.zst"
    validate_package(
        artifact_path,
        staging_dir / "exact",
        settings.model_copy(update={"max_upload_bytes": exact_limit}),
        payload,
    )
    with pytest.raises(ImportPackageRejected, match="compressed"):
        validate_package(
            artifact_path,
            staging_dir / "over",
            settings.model_copy(update={"max_upload_bytes": exact_limit - 1}),
            payload,
        )


def sized_manifest_payload(size: int) -> bytes:
    manifest = tiny_manifest_dict()
    digest = "d"
    payload = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    while len(payload) < size:
        digest += "d"
        manifest["canonicalization_manifest_digest"] = digest
        payload = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    if len(payload) > size:
        raise ValueError("unable to build manifest payload of exact size")
    return payload


@pytest.mark.parametrize(
    ("limit_attr", "build_payload"),
    [
        (
            "max_manifest_json_bytes",
            lambda limit: (sized_manifest_payload(limit), b"a"),
        ),
        (
            "max_replay_sql_bytes",
            lambda limit: (
                json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8"),
                b"x" * limit,
            ),
        ),
    ],
)
def test_entry_expanded_boundary(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    limit_attr: str,
    build_payload: Callable[[int], tuple[bytes, bytes]],
) -> None:
    limit = 256
    local_settings = settings.model_copy(update={limit_attr: limit})
    manifest_payload, replay_payload = build_payload(limit)
    artifact_path = tmp_path / "artifact.tar.zst"
    validate_package(
        artifact_path,
        staging_dir / "exact",
        local_settings,
        build_package_bytes(
            entries=[
                (MANIFEST_ENTRY_NAME, manifest_payload),
                (REPLAY_SQL_ENTRY_NAME, replay_payload),
            ]
        ),
    )
    under_manifest, under_replay = build_payload(limit - 1)
    validate_package(
        artifact_path,
        staging_dir / "under",
        local_settings,
        build_package_bytes(
            entries=[
                (MANIFEST_ENTRY_NAME, under_manifest),
                (REPLAY_SQL_ENTRY_NAME, under_replay),
            ]
        ),
    )
    over_manifest, over_replay = build_payload(limit + 1)
    with pytest.raises(ImportPackageRejected):
        validate_package(
            artifact_path,
            staging_dir / "over",
            local_settings,
            build_package_bytes(
                entries=[
                    (MANIFEST_ENTRY_NAME, over_manifest),
                    (REPLAY_SQL_ENTRY_NAME, over_replay),
                ]
            ),
        )


def test_total_payload_boundary(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    limit = len(manifest_payload) + 32
    local_settings = settings.model_copy(update={"max_total_expanded_entry_bytes": limit})
    replay_size = limit - len(manifest_payload)
    artifact_path = tmp_path / "artifact.tar.zst"
    validate_package(
        artifact_path,
        staging_dir / "exact",
        local_settings,
        build_package_bytes(
            manifest=tiny_manifest_dict(),
            replay_sql=b"x" * replay_size,
        ),
    )
    with pytest.raises(ImportPackageRejected, match="total expanded"):
        validate_package(
            artifact_path,
            staging_dir / "over",
            local_settings,
            build_package_bytes(
                manifest=tiny_manifest_dict(),
                replay_sql=b"x" * (replay_size + 1),
            ),
        )


def test_decoder_stream_boundary_minus_one_equal_plus_one(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    payload = build_package_bytes(manifest=tiny_manifest_dict())
    decompressed_size = len(compression.zstd.decompress(payload))
    artifact_path = tmp_path / "artifact.tar.zst"

    with pytest.raises(ImportPackageRejected, match="decompressed tar stream"):
        validate_package(
            artifact_path,
            staging_dir / "under",
            settings.model_copy(update={"max_decompressed_tar_stream_bytes": decompressed_size - 1}),
            payload,
        )
    validate_package(
        artifact_path,
        staging_dir / "exact",
        settings.model_copy(update={"max_decompressed_tar_stream_bytes": decompressed_size}),
        payload,
    )
    validate_package(
        artifact_path,
        staging_dir / "over",
        settings.model_copy(update={"max_decompressed_tar_stream_bytes": decompressed_size + 1}),
        payload,
    )


def test_decoder_stream_counts_tar_headers(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    tar_bytes = build_raw_tar_bytes(
        [
            (MANIFEST_ENTRY_NAME, manifest_payload, tarfile.REGTYPE),
            (REPLAY_SQL_ENTRY_NAME, b"a", tarfile.REGTYPE),
        ]
    )
    limit = len(tar_bytes) - 1
    local_settings = settings.model_copy(update={"max_decompressed_tar_stream_bytes": limit})
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="decompressed tar stream"):
        validate_package(artifact_path, staging_dir, local_settings, compress_zstd(tar_bytes))


def test_rejects_invalid_utf8_tar_header(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest_payload = json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    header = bytearray(_tar_header(MANIFEST_ENTRY_NAME, len(manifest_payload)))
    header[0:4] = b"\xff\xfe\xfd\xfc"
    tar_bytes = bytes(header) + manifest_payload + b"\x00" * ((512 - (len(manifest_payload) % 512)) % 512)
    tar_bytes += build_raw_tar_bytes(
        [(REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n", tarfile.REGTYPE)],
        include_eof=False,
    )
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="tar header is invalid"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_accepts_checksum_enabled_frame_at_exact_decoder_boundary_with_chunked_read(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tar_bytes = valid_tar_bytes()
    compressed = compress_zstd_with_checksum(tar_bytes)
    monkeypatch.setattr(
        "gateway_repository_service.versioned_import.package._COMPRESSED_READ_CHUNK_BYTES",
        len(compressed) - 4,
    )
    local_settings = settings.model_copy(
        update={"max_decompressed_tar_stream_bytes": len(tar_bytes)}
    )
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(artifact_path, staging_dir, local_settings, compressed)
    assert result.manifest.package_version == 1


def test_accepts_full_zero_padding_block_after_tar_eof(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    tar_bytes = valid_tar_bytes() + (b"\x00" * 512)
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))
    assert result.manifest.package_version == 1


@pytest.mark.parametrize("extra_zero_bytes", [1, 511, 513])
def test_rejects_partial_or_extra_zero_tail_after_eof(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    extra_zero_bytes: int,
) -> None:
    tar_bytes = valid_tar_bytes() + (b"\x00" * extra_zero_bytes)
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="trailing"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_chunked_copy_streams_large_replay_without_full_read(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gateway_repository_service.versioned_import.package.COPY_CHUNK_BYTES",
        17,
    )
    replay_sql = b"X" * 10_000
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(
        artifact_path,
        staging_dir,
        settings,
        build_package_bytes(manifest=tiny_manifest_dict(), replay_sql=replay_sql),
    )
    assert result.replay_sql_path.read_bytes() == replay_sql


def empty_manifest_dict() -> dict[str, object]:
    return {
        "package_version": 1,
        "canonicalization_manifest_digest": "d",
        "tables": [],
    }


def valid_tar_bytes(
    *,
    manifest: dict[str, object] | None = None,
    replay_sql: bytes = b"SELECT 1;\n",
) -> bytes:
    manifest_payload = json.dumps(manifest or tiny_manifest_dict(), separators=(",", ":")).encode("utf-8")
    return build_raw_tar_bytes(
        [
            (MANIFEST_ENTRY_NAME, manifest_payload, tarfile.REGTYPE),
            (REPLAY_SQL_ENTRY_NAME, replay_sql, tarfile.REGTYPE),
        ]
    )


def test_accepts_empty_tables_manifest(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(
        artifact_path,
        staging_dir,
        settings,
        build_package_bytes(manifest=empty_manifest_dict()),
    )
    assert result.manifest.tables == ()


def test_rejects_table_name_with_leading_whitespace(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest = tiny_manifest_dict()
    manifest["tables"] = [
        {
            "name": " leading",
            "schema": {
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
            },
            "row_count": 0,
        }
    ]
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="failed closed validation"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(manifest=manifest),
        )


def test_rejects_table_name_with_trailing_whitespace(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest = tiny_manifest_dict()
    manifest["tables"] = [
        {
            "name": "trailing ",
            "schema": {
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
            },
            "row_count": 0,
        }
    ]
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="failed closed validation"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            build_package_bytes(manifest=manifest),
        )


def test_accepts_column_name_with_trailing_whitespace(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": "d",
        "tables": [
            {
                "name": "t",
                "schema": {
                    "columns": [{"name": "trailing ", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["trailing "],
                },
                "row_count": 0,
            }
        ],
    }
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(
        artifact_path,
        staging_dir,
        settings,
        build_package_bytes(manifest=manifest),
    )
    assert result.manifest.tables[0].table_schema.columns[0].name == "trailing "


def test_rejects_decompressed_trailing_garbage_in_same_zstd_frame(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="trailing"):
        validate_package(
            artifact_path,
            staging_dir,
            settings,
            compress_zstd(valid_tar_bytes() + b"GARBAGE"),
        )


@pytest.mark.parametrize("eof_blocks", [0, 1])
def test_rejects_insufficient_eof_zero_blocks(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    eof_blocks: int,
) -> None:
    tar_bytes = valid_tar_bytes()[: -1024] + (b"\x00" * (512 * eof_blocks))
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="EOF|malformed|trailing"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_rejects_extra_entry_after_eof_blocks(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    extra = _tar_record("extra.txt", b"x")
    tar_bytes = valid_tar_bytes() + extra
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="trailing|EOF|not allowed"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_rejects_nonzero_data_after_eof_blocks(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    tar_bytes = valid_tar_bytes() + b"TRAILER"
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="trailing"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_rejects_empty_global_pax_header(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    tar_bytes = build_raw_tar_bytes(
        [
            ("././@PaxHeader", b"", tarfile.XGLTYPE),
            (
                MANIFEST_ENTRY_NAME,
                json.dumps(tiny_manifest_dict(), separators=(",", ":")).encode("utf-8"),
                tarfile.REGTYPE,
            ),
            (REPLAY_SQL_ENTRY_NAME, b"SELECT 1;\n", tarfile.REGTYPE),
        ]
    )
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="not allowed"):
        validate_package(artifact_path, staging_dir, settings, compress_zstd(tar_bytes))


def test_rejects_truncated_zstd_frame(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    payload = compress_zstd(valid_tar_bytes())[:32]
    with pytest.raises(ImportPackageRejected, match="incomplete|malformed|trailing"):
        validate_package(artifact_path, staging_dir, settings, payload)


def test_rejects_decompression_bomb_before_high_allocation(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    replay_sql = b"A" * (32 * 1024 * 1024)
    compressed = compress_zstd(valid_tar_bytes(replay_sql=replay_sql))
    local_settings = settings.model_copy(update={"max_decompressed_tar_stream_bytes": 1024 * 1024})
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match="decompressed tar stream"):
        validate_package(artifact_path, staging_dir, local_settings, compressed)


@pytest.mark.parametrize(
    ("manifest", "match"),
    [
        ({"package_version": True, "canonicalization_manifest_digest": "d", "tables": []}, "validation"),
        ({"package_version": 1.0, "canonicalization_manifest_digest": "d", "tables": []}, "validation"),
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "tables": [
                    {
                        "name": "t",
                        "table_schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["id"],
                        },
                        "row_count": 0,
                    }
                ],
            },
            "validation",
        ),
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "tables": [
                    {
                        "name": "t",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": 1}],
                            "primary_key": ["id"],
                        },
                        "row_count": 0,
                    }
                ],
            },
            "validation",
        ),
        (
            {
                "package_version": 1,
                "canonicalization_manifest_digest": "d",
                "tables": [
                    {
                        "name": "t",
                        "schema": {
                            "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                            "primary_key": ["id"],
                        },
                        "row_count": "1",
                    }
                ],
            },
            "validation",
        ),
    ],
)
def test_rejects_non_strict_manifest_scalars(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    manifest: dict[str, object],
    match: str,
) -> None:
    artifact_path = tmp_path / "artifact.tar.zst"
    with pytest.raises(ImportPackageRejected, match=match):
        validate_package(artifact_path, staging_dir, settings, build_package_bytes(manifest=manifest))


def test_manifest_accepts_point_srid_normalized_sql_type(
    tmp_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> None:
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": "manifest-digest-spatial",
        "tables": [
            {
                "name": "spatial_pt",
                "schema": {
                    "columns": [
                        {"name": "geom", "sql_type": "POINT SRID 4326", "nullable": False},
                        {"name": "id", "sql_type": "BIGINT", "nullable": False},
                    ],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }
    replay_sql = (
        b"CREATE TABLE spatial_pt (geom POINT SRID 4326 NOT NULL, "
        b"id BIGINT NOT NULL PRIMARY KEY);\n"
    )
    payload = build_package_bytes(manifest=manifest, replay_sql=replay_sql)
    artifact_path = tmp_path / "artifact.tar.zst"
    result = validate_package(artifact_path, staging_dir, settings, payload)
    assert result.manifest.tables[0].table_schema.columns[0].sql_type == "POINT SRID 4326"
