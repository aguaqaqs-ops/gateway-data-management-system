"""Durable CanonicalizationManifest publication and atomic artifact replacement."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    PACKAGE_VERSION,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    STORAGE_PROJECTION_VERSION,
    CanonicalPublicationResult,
    NeverCancel,
    PackageError,
    ProjectionDiagnosticCode,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTableInput,
    PublicationError,
    RepositoryImportColumn,
    canonicalization_manifest_from_bytes,
    durable_manifest_bytes,
    open_canonicalization_manifest,
    open_repository_import_package,
    project_storage,
    publish_canonicalization,
    publish_canonicalization_manifest,
    repository_import_manifest_bytes,
)
from gateway_backend.capabilities.storage_projection import package as package_mod
from gateway_backend.capabilities.storage_projection._digest import (
    compute_manifest_digest,
    manifest_document,
)
from gateway_backend.capabilities.table_rules.contracts import DroppedColumn, legacy_ignored_column_reason
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from tests.support.storage_projection import (
    as_row,
    dummy_digest,
    int_cell,
    int_column,
    table_input,
    varchar_cell,
    varchar_column,
)
from tests.support.table_rules import net_cfg_record

pytestmark = pytest.mark.unit

_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "storage-projection"
)
_NET_CFG_COLUMNS = (
    varchar_column("board"),
    int_column("link_no"),
    int_column("no", nullable=True),
)
_NET_CFG_ROWS = (
    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
    as_row(varchar_cell("eth1"), int_cell(2), int_cell(20)),
)


class FlagCancel:
    def __init__(self, flag: bool = False) -> None:
        self.flag = flag

    def is_set(self) -> bool:
        return self.flag


class FailSecondPut:
    def __init__(self) -> None:
        self.inner = InMemoryArtifactStore()
        self.puts = 0

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        self.puts += 1
        if self.puts >= 2:
            raise OSError("write failed")
        return self.inner.put(raw_bytes, ref)

    def locate(self, ref: ArtifactRef) -> bytes:
        return self.inner.locate(ref)


class CollisionStore(InMemoryArtifactStore):
    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        occupied = ArtifactRef(
            artifact_id=ref.artifact_id,
            media_type=ref.media_type,
            size_bytes=1,
            raw_sha256=dummy_digest(),
        )
        self._artifacts[ref.artifact_id] = (occupied, b"x")
        return super().put(raw_bytes, ref)


class CancelAfterSecondLocate:
    def __init__(self, cancel: FlagCancel) -> None:
        self.inner = InMemoryArtifactStore()
        self.cancel = cancel
        self.locates = 0

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        return self.inner.put(raw_bytes, ref)

    def locate(self, ref: ArtifactRef) -> bytes:
        payload = self.inner.locate(ref)
        self.locates += 1
        if self.locates == 2:
            self.cancel.flag = True
        return payload


def _project() -> ProjectionResult:
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
    assert result.manifest is not None
    assert result.import_input is not None
    return result


def test_durable_manifest_jcs_round_trip_and_preimage_omits_digest() -> None:
    result = _project()
    assert result.manifest is not None
    payload = durable_manifest_bytes(result.manifest)
    opened = canonicalization_manifest_from_bytes(payload)
    assert opened == result.manifest
    document = json.loads(payload.decode("utf-8"))
    assert "manifest_digest" in document
    preimage = dict(document)
    del preimage["manifest_digest"]
    assert canonicalize_json_value(preimage) == canonicalize_json_value(manifest_document(result.manifest))
    assert compute_manifest_digest(result.manifest) == result.manifest.manifest_digest
    golden = json.loads(
        (_GOLDEN / "manifest" / "valid" / "s5-durable-roundtrip" / "document.json").read_text(
            encoding="utf-8"
        )
    )
    assert canonicalize_json_value(golden) == payload


def test_previous_manifest_version_decodes_but_cannot_be_written() -> None:
    result = _project()
    assert result.manifest is not None
    historical = replace(result.manifest, contract_version="3.0.0", manifest_digest=None)
    historical = replace(historical, manifest_digest=compute_manifest_digest(historical))
    assert historical.manifest_digest is not None
    document = dict(manifest_document(historical))
    document["manifest_digest"] = historical.manifest_digest.value
    payload = canonicalize_json_value(document)

    assert canonicalization_manifest_from_bytes(payload) == historical
    with pytest.raises(PackageError, match="current contract_version"):
        durable_manifest_bytes(historical)


def test_durable_manifest_size_gate_applies_to_write_and_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _project()
    assert result.manifest is not None
    payload = durable_manifest_bytes(result.manifest)
    monkeypatch.setattr(package_mod, "MAX_MANIFEST_JSON_BYTES", 4)
    with pytest.raises(PackageError) as write_exc:
        durable_manifest_bytes(result.manifest)
    assert write_exc.value.code is ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED
    with pytest.raises(PackageError) as read_exc:
        canonicalization_manifest_from_bytes(payload)
    assert read_exc.value.code is ProjectionDiagnosticCode.RESOURCE_LIMIT_EXCEEDED


def test_canonical_key_retained_and_dropped_survive_manifest_to_package() -> None:
    result = _project()
    assert result.manifest is not None
    assert result.import_input is not None
    assert result.manifest.manifest_digest is not None
    dropped = result.manifest.tables[0].dropped_columns
    assert dropped == (
        DroppedColumn(name="no", reason=legacy_ignored_column_reason(net_cfg_record().selector)),
    )
    assert result.manifest.tables[0].retained_columns == ("board", "link_no")
    assert result.manifest.tables[0].canonical_key_columns == ("board", "link_no")
    assert result.import_input.tables[0].primary_key == ("board", "link_no")
    package_json = json.loads(repository_import_manifest_bytes(result.import_input).decode("utf-8"))
    golden = json.loads(
        (_GOLDEN / "package" / "valid" / "s5-structural-shape" / "manifest.json").read_text(encoding="utf-8")
    )
    package_json["canonicalization_manifest_digest"] = result.manifest.manifest_digest.value
    golden["canonicalization_manifest_digest"] = result.manifest.manifest_digest.value
    assert package_json["tables"][0]["schema"]["primary_key"] == ["board", "link_no"]
    assert [column["name"] for column in package_json["tables"][0]["schema"]["columns"]] == [
        "board",
        "link_no",
    ]
    assert golden["tables"] == package_json["tables"]
    assert golden["package_version"] == PACKAGE_VERSION


def test_publish_and_open_round_trip_opaque_refs() -> None:
    result = _project()
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.COMPLETE
    assert published.publication is not None
    publication = published.publication
    assert publication.package_ref.media_type == REPOSITORY_IMPORT_MEDIA_TYPE
    assert publication.manifest_ref.media_type == CANONICALIZATION_MANIFEST_MEDIA_TYPE
    assert set(publication.manifest_ref.__dataclass_fields__) == {
        "artifact_id",
        "media_type",
        "size_bytes",
        "raw_sha256",
    }
    opened_manifest = open_canonicalization_manifest(store, publication.manifest_ref)
    opened_package = open_repository_import_package(store, publication.package_ref)
    assert opened_manifest == result.manifest
    assert opened_package == result.import_input
    assert publication.manifest_digest == result.manifest.manifest_digest


def test_manifest_publisher_does_not_require_an_import_package() -> None:
    result = _project()
    assert result.manifest is not None
    store = InMemoryArtifactStore()

    ref = publish_canonicalization_manifest(result.manifest, store)

    assert ref.media_type == CANONICALIZATION_MANIFEST_MEDIA_TYPE
    assert len(store._artifacts) == 1
    assert open_canonicalization_manifest(store, ref) == result.manifest


def test_failed_projection_does_not_publish() -> None:
    store = InMemoryArtifactStore()
    result = ProjectionResult(status=ProjectionStatus.FAILED, tables=(), diagnostics=())
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.BINDING_INVALID
    assert store._artifacts == {}


def test_stale_manifest_digest_fails_before_store_write() -> None:
    result = _project()
    assert result.manifest is not None
    stale = replace(
        result.manifest,
        tables=(replace(result.manifest.tables[0], content_digest=dummy_digest()),),
    )
    mutated = replace(result, manifest=stale)
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        mutated,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.DIGEST_MISMATCH
    assert store._artifacts == {}


def test_import_row_count_mismatch_fails_closed() -> None:
    result = _project()
    assert result.import_input is not None
    mutated_input = replace(
        result.import_input,
        tables=(replace(result.import_input.tables[0], row_count=99),),
    )
    mutated = replace(result, import_input=mutated_input)
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        mutated,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.ROW_INTEGRITY
    assert store._artifacts == {}


def test_dropped_column_in_import_schema_fails_closed() -> None:
    result = _project()
    assert result.import_input is not None
    table = result.import_input.tables[0]
    mutated_table = replace(
        table,
        columns=(
            *table.columns,
            RepositoryImportColumn(name="no", sql_type="INT", nullable=True),
        ),
    )
    mutated = replace(result, import_input=replace(result.import_input, tables=(mutated_table,)))
    published = publish_canonicalization(
        mutated,
        store=InMemoryArtifactStore(),
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.BINDING_INVALID


def test_second_put_failure_returns_no_publication() -> None:
    result = _project()
    store = FailSecondPut()
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.PUBLICATION_FAILED
    assert store.puts == 2
    assert len(store.inner._artifacts) == 1


def test_atomic_replace_conflict_is_publication_failure() -> None:
    result = _project()
    published = publish_canonicalization(
        result,
        store=CollisionStore(),
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.PUBLICATION_FAILED


def test_cancel_and_deadline_fail_closed() -> None:
    result = _project()
    cancelled = publish_canonicalization(
        result,
        store=InMemoryArtifactStore(),
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=FlagCancel(True)),
    )
    assert cancelled.status is ProjectionStatus.FAILED
    assert cancelled.publication is None
    assert cancelled.diagnostics[0].code is ProjectionDiagnosticCode.PROJECTION_CANCELLED
    timed_out = publish_canonicalization(
        result,
        store=InMemoryArtifactStore(),
        replay_sql=b"",
        context=ProjectionInvocationContext(
            cancel_requested=NeverCancel(),
            deadline_monotonic=time.monotonic() - 1.0,
        ),
    )
    assert timed_out.status is ProjectionStatus.FAILED
    assert timed_out.publication is None
    assert timed_out.diagnostics[0].code is ProjectionDiagnosticCode.PROJECTION_TIMEOUT


def test_cancellation_after_final_store_read_does_not_return_complete() -> None:
    result = _project()
    cancel = FlagCancel()
    store = CancelAfterSecondLocate(cancel)
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=cancel),
    )
    assert store.locates == 2
    assert published.status is ProjectionStatus.FAILED
    assert published.publication is None
    assert published.diagnostics[0].code is ProjectionDiagnosticCode.PROJECTION_CANCELLED


def test_missing_and_corrupt_refs_fail_closed() -> None:
    result = _project()
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.publication is not None
    missing = published.publication.manifest_ref
    del store._artifacts[missing.artifact_id]
    with pytest.raises(PublicationError) as missing_exc:
        open_canonicalization_manifest(store, missing)
    assert missing_exc.value.code is ProjectionDiagnosticCode.PUBLICATION_FAILED
    other = put_with_built_ref(
        store,
        b"{}",
        artifact_id="r4-corrupt-aaaaaaaa",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    )
    with pytest.raises(PublicationError) as corrupt_exc:
        open_canonicalization_manifest(store, other)
    assert corrupt_exc.value.code in {
        ProjectionDiagnosticCode.BINDING_INVALID,
        ProjectionDiagnosticCode.DIGEST_MISMATCH,
        ProjectionDiagnosticCode.PUBLICATION_FAILED,
    }


def test_cache_miss_rebuild_from_source_binding_is_stable() -> None:
    first_reader, binding = table_input(
        "net_cfg",
        columns=_NET_CFG_COLUMNS,
        primary_key_columns=("board", "link_no"),
        rows=_NET_CFG_ROWS,
    )
    second_reader = first_reader.reopen()
    first = project_storage(
        ProjectionRequest(
            ruleset=migrated_table_ruleset_snapshot(),
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=(
                ProjectionTableInput(
                    canonical_table="net_cfg",
                    reader=first_reader,
                    source_binding=binding,
                ),
            ),
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
    )
    second = project_storage(
        ProjectionRequest(
            ruleset=migrated_table_ruleset_snapshot(),
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=(
                ProjectionTableInput(
                    canonical_table="net_cfg",
                    reader=second_reader,
                    source_binding=binding,
                ),
            ),
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.manifest.manifest_digest == second.manifest.manifest_digest
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        first,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.publication is not None
    del store._artifacts[published.publication.manifest_ref.artifact_id]
    with pytest.raises(PublicationError):
        open_canonicalization_manifest(store, published.publication.manifest_ref)
    rebuilt = publish_canonicalization(
        second,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert rebuilt.status is ProjectionStatus.COMPLETE
    assert rebuilt.publication is not None
    assert rebuilt.publication.manifest_digest == first.manifest.manifest_digest


def test_complete_publication_requires_both_refs() -> None:
    with pytest.raises(ValueError, match="COMPLETE publication requires CanonicalPublication"):
        CanonicalPublicationResult(status=ProjectionStatus.COMPLETE)
    result = _project()
    store = InMemoryArtifactStore()
    published = publish_canonicalization(
        result,
        store=store,
        replay_sql=b"",
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    assert published.publication is not None
    with pytest.raises(ValueError, match="FAILED publication must not include"):
        CanonicalPublicationResult(
            status=ProjectionStatus.FAILED,
            publication=published.publication,
        )
