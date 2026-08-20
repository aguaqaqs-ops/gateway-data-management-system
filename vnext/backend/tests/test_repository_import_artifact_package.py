"""Repository import package shape, safety, and size gates."""

from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Callable

import compression.zstd
import pytest
from gateway_backend.capabilities.storage_projection import (
    PACKAGE_VERSION,
    PackageError,
    ProjectionDiagnosticCode,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    ProjectionInvocationContext,
    RepositoryImportArtifactInput,
    build_repository_import_package,
    project_storage,
    repository_import_input_from_bytes,
    repository_import_manifest_bytes,
    validate_repository_import_package,
)
from gateway_backend.capabilities.storage_projection.package import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    pack_repository_import_entries,
    unpack_repository_import_entries,
)
from gateway_backend.capabilities.storage_projection import package as package_mod
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.repository_import_artifact import build_repository_import_package as build_identity_package
from tests.support.storage_projection import as_row, int_cell, int_column, table_input, varchar_cell, varchar_column

pytestmark = pytest.mark.unit

_NET_CFG_COLUMNS = (
    varchar_column("board"),
    int_column("link_no"),
    int_column("no", nullable=True),
)
_NET_CFG_ROWS = (
    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
    as_row(varchar_cell("eth1"), int_cell(2), int_cell(20)),
)


def _complete_import_input() -> RepositoryImportArtifactInput:
    reader, binding = table_input(
        "net_cfg",
        columns=_NET_CFG_COLUMNS,
        primary_key_columns=("board", "link_no"),
        rows=_NET_CFG_ROWS,
    )
    result = project_storage(
        ProjectionRequest(
            ruleset=migrated_table_ruleset_snapshot(),
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=(
                ProjectionTableInput(
                    canonical_table="net_cfg",
                    reader=reader,
                    source_binding=binding,
                ),
            ),
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
    )
    assert result.status is ProjectionStatus.COMPLETE
    assert result.import_input is not None
    return result.import_input


def _pack_raw(
    entries: tuple[tuple[str, bytes], ...],
    *,
    member_type: bytes | None = None,
    linkname: str | None = None,
    apply_type_to: str | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name=name)
            if apply_type_to == name and member_type is not None:
                info.type = member_type
                if linkname is not None:
                    info.linkname = linkname
                info.size = 0 if member_type != tarfile.REGTYPE else len(payload)
                if member_type == tarfile.REGTYPE:
                    archive.addfile(info, io.BytesIO(payload))
                else:
                    archive.addfile(info)
                continue
            info.type = tarfile.REGTYPE
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(payload))
    return compression.zstd.compress(buffer.getvalue())


def test_structural_package_round_trip_preserves_key_and_drops() -> None:
    import_input = _complete_import_input()
    payload = repository_import_manifest_bytes(import_input)
    parsed = repository_import_input_from_bytes(payload)
    assert parsed == import_input
    table = parsed.tables[0]
    assert table.primary_key == ("board", "link_no")
    assert tuple(column.name for column in table.columns) == ("board", "link_no")
    assert "no" not in {column.name for column in table.columns}
    document = json.loads(payload.decode("utf-8"))
    assert list(document) == [
        "package_version",
        "canonicalization_manifest_digest",
        "tables",
    ]
    assert document["package_version"] == PACKAGE_VERSION
    assert "no" not in {column["name"] for column in document["tables"][0]["schema"]["columns"]}


def test_package_writer_is_reproducible_and_ustar_only() -> None:
    import_input = _complete_import_input()
    first = build_repository_import_package(import_input=import_input, replay_sql=b"")
    second = build_repository_import_package(import_input=import_input, replay_sql=b"")
    assert first.payload == second.payload
    assert first.sha256 == second.sha256
    assert first.size_bytes == len(first.payload)
    identity = build_identity_package(
        manifest=json.loads(repository_import_manifest_bytes(import_input).decode("utf-8")),
        replay_sql=b"",
    )
    assert identity.payload == first.payload
    tar_bytes = compression.zstd.decompress(first.payload)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [MANIFEST_ENTRY_NAME, REPLAY_SQL_ENTRY_NAME]
        for member in members:
            assert member.mtime == 0
            assert member.uid == 0
            assert member.gid == 0
            assert member.uname == ""
            assert member.gname == ""
            assert member.pax_headers == {}
            assert member.isfile()


def test_empty_replay_is_admitted() -> None:
    import_input = _complete_import_input()
    packed = build_repository_import_package(import_input=import_input, replay_sql=b"")
    parsed = validate_repository_import_package(packed.payload)
    assert parsed == import_input
    _manifest, replay = unpack_repository_import_entries(packed.payload)
    assert replay == b""


PACKAGE_SHAPE_FAULTS: tuple[tuple[str, Callable[[], bytes]], ...] = (
    (
        "extra-entry",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
                ("other.txt", b"x"),
            )
        ),
    ),
    (
        "missing-replay",
        lambda: _pack_raw(((MANIFEST_ENTRY_NAME, b"{}"),)),
    ),
    (
        "wrong-order",
        lambda: _pack_raw(
            (
                (REPLAY_SQL_ENTRY_NAME, b""),
                (MANIFEST_ENTRY_NAME, b"{}"),
            )
        ),
    ),
    (
        "absolute-path",
        lambda: _pack_raw(
            (
                ("/" + MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            )
        ),
    ),
    (
        "parent-segment",
        lambda: _pack_raw(
            (
                ("../" + MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            )
        ),
    ),
    (
        "symlink",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            ),
            member_type=tarfile.SYMTYPE,
            linkname=REPLAY_SQL_ENTRY_NAME,
            apply_type_to=MANIFEST_ENTRY_NAME,
        ),
    ),
    (
        "hardlink",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            ),
            member_type=tarfile.LNKTYPE,
            linkname=REPLAY_SQL_ENTRY_NAME,
            apply_type_to=MANIFEST_ENTRY_NAME,
        ),
    ),
    (
        "device",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            ),
            member_type=tarfile.CHRTYPE,
            apply_type_to=MANIFEST_ENTRY_NAME,
        ),
    ),
    (
        "fifo",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            ),
            member_type=tarfile.FIFOTYPE,
            apply_type_to=MANIFEST_ENTRY_NAME,
        ),
    ),
    (
        "directory",
        lambda: _pack_raw(
            (
                (MANIFEST_ENTRY_NAME, b"{}"),
                (REPLAY_SQL_ENTRY_NAME, b""),
            ),
            member_type=tarfile.DIRTYPE,
            apply_type_to=MANIFEST_ENTRY_NAME,
        ),
    ),
)


@pytest.mark.parametrize("label,factory", PACKAGE_SHAPE_FAULTS, ids=[item[0] for item in PACKAGE_SHAPE_FAULTS])
def test_malformed_package_shape_is_rejected(label: str, factory: Callable[[], bytes]) -> None:
    del label
    with pytest.raises(PackageError) as exc:
        validate_repository_import_package(factory())
    assert exc.value.code is ProjectionDiagnosticCode.BINDING_INVALID


PACKAGE_JSON_FAULTS: tuple[tuple[str, bytes], ...] = (
    ("unknown-field", b'{"package_version":1,"canonicalization_manifest_digest":"sha256:' + b"aa" * 32 + b'","tables":[],"extra":true}'),
    ("package-version", b'{"package_version":2,"canonicalization_manifest_digest":"sha256:' + b"aa" * 32 + b'","tables":[]}'),
    ("not-utf8", b'{"package_version":1,\xff}'),
    ("utf8-bom", b'\xef\xbb\xbf{"package_version":1,"canonicalization_manifest_digest":"sha256:' + b"aa" * 32 + b'","tables":[]}'),
    ("duplicate-member", b'{"package_version":1,"package_version":1,"canonicalization_manifest_digest":"sha256:' + b"aa" * 32 + b'","tables":[]}'),
)


@pytest.mark.parametrize("label,payload", PACKAGE_JSON_FAULTS, ids=[item[0] for item in PACKAGE_JSON_FAULTS])
def test_malformed_package_manifest_json_is_rejected(label: str, payload: bytes) -> None:
    del label
    packed_payload = _pack_raw(((MANIFEST_ENTRY_NAME, payload), (REPLAY_SQL_ENTRY_NAME, b"")))
    with pytest.raises(PackageError) as exc:
        validate_repository_import_package(packed_payload)
    assert exc.value.code is ProjectionDiagnosticCode.BINDING_INVALID


def test_packer_rejects_non_utf8_manifest() -> None:
    with pytest.raises(PackageError) as exc:
        pack_repository_import_entries(b"{\xff}", b"")
    assert exc.value.code is ProjectionDiagnosticCode.BINDING_INVALID


def test_size_gates_reject_oversized_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(package_mod, "MAX_MANIFEST_JSON_BYTES", 4)
    with pytest.raises(PackageError) as exc:
        pack_repository_import_entries(b"hello", b"")
    assert exc.value.code is ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED
    monkeypatch.setattr(package_mod, "MAX_MANIFEST_JSON_BYTES", 16 * 1024 * 1024)
    monkeypatch.setattr(package_mod, "MAX_REPLAY_SQL_BYTES", 4)
    with pytest.raises(PackageError) as replay_exc:
        pack_repository_import_entries(b"{}", b"hello")
    assert replay_exc.value.code is ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED
