"""In-memory RepositoryRef provider for Snapshot Materialization tests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence, Callable
from dataclasses import replace
from contextlib import contextmanager
from typing import Any
import datetime
import pyarrow as pa

from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryCatalogTable,
    RepositoryColumn,
    RepositoryProviderError,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryRefTimeoutPolicy,
    RepositoryTableCatalog,
    SnapshotMaterializationResult,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import materialize_repository_ref
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    OrderedPolicy,
    StorageRuleView,
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
    compute_ruleset_digest,
    table_ruleset_document,
)

REPOSITORY_SERVER_CONTRACT_VERSION = 1
DEFAULT_REPOSITORY_ID = "repo-s4"
DEFAULT_REF = "abc123def456abc123def456abc123de"
RepositoryRows = Mapping[str, Sequence[Sequence[object | None]]]


def _identity_fixture_value(value: Any) -> Any:
    return value


def _datetime_fixture_value(value: Any) -> Any:
    return datetime.datetime.fromisoformat(str(value))


def _set_fixture_value(value: Any) -> Any:
    return list(value) if isinstance(value, (list, tuple)) else str(value).split(",") if value else []


class FakeRepositoryTableReader:
    def __init__(
        self,
        table: RepositoryCatalogTable,
        rows: tuple[tuple[object | None, ...], ...],
        *,
        pad_nulls: bool,
        fail_stream: bool,
    ) -> None:
        self._table = table
        self._rows = rows
        self._pad_nulls = pad_nulls
        self._fail_stream = fail_stream
        self.closed = False
        self.stream_count = 0

    def catalog_table(self) -> RepositoryCatalogTable:
        return self._table

    def column_order(self) -> tuple[str, ...]:
        return tuple(column.name for column in self._table.columns)

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        self.stream_count += 1
        if self._fail_stream:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
                "table read failed",
                table=self._table.table_name,
            )
        width = len(self._table.columns)
        for row in self._rows:
            if self._pad_nulls and len(row) < width:
                row = row + (None,) * (width - len(row))
            yield row

    def close(self) -> None:
        self.closed = True


class FakeRepositoryRefSession:
    def __init__(
        self,
        *,
        catalog: RepositoryTableCatalog,
        rows: RepositoryRows,
        pinned_commit: str,
        pad_nulls: bool,
        fail_stream: bool,
        close_error: bool,
        catalog_error: bool,
        catalog_error_message: str | None,
        missing_table_on_open: str | None,
    ) -> None:
        self._catalog = catalog
        self._rows = rows
        self._pinned_commit = pinned_commit
        self._pad_nulls = pad_nulls
        self._fail_stream = fail_stream
        self._close_error = close_error
        self._catalog_error = catalog_error
        self._catalog_error_message = catalog_error_message
        self._missing_table_on_open = missing_table_on_open
        self.catalog_load_count = 0
        self.table_readers: list[FakeRepositoryTableReader] = []
        self.close_count = 0
        self._memo: RepositoryTableCatalog | None = None
        self.closed = False

    def pinned_commit_hash(self) -> str:
        return self._pinned_commit

    def get_catalog(self) -> RepositoryTableCatalog:
        if self._catalog_error or self._catalog_error_message is not None:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                self._catalog_error_message or "catalog load failed",
            )
        if self._memo is None:
            self.catalog_load_count += 1
            self._memo = self._catalog
        return self._memo

    def open_table_reader(self, table_name: str) -> FakeRepositoryTableReader:
        if self._missing_table_on_open == table_name:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_TABLE_NOT_FOUND,
                f"table {table_name!r} is not in the catalog",
                table=table_name,
            )
        canonical = canonicalize_identifier(table_name)
        for table in self._catalog.tables:
            if canonicalize_identifier(table.table_name) == canonical:
                reader = FakeRepositoryTableReader(
                    table,
                    tuple(tuple(row) for row in self._rows.get(canonical, ())),
                    pad_nulls=self._pad_nulls,
                    fail_stream=self._fail_stream,
                )
                self.table_readers.append(reader)
                return reader
        raise RepositoryProviderError(
            MaterializationDiagnosticCode.REPOSITORY_TABLE_NOT_FOUND,
            f"table {table_name!r} is not in the catalog",
            table=table_name,
        )

    @contextmanager
    def open_arrow_table_reader(
        self, table_name: str, *, max_input_bytes: int, max_rows: int, max_columns: int, max_batches: int,
    ) -> Iterator[pa.RecordBatchReader]:
        # A fixture wire renderer; production has only the HTTP Arrow adapter.
        from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import map_repository_column
        reader = self.open_table_reader(table_name)
        try:
            table = reader.catalog_table()
            fields = []
            columns: list[list[Any]] = []
            conversions = []
            for column in table.columns:
                mapped = map_repository_column(column).source
                kind = None if mapped.declared_type is None else mapped.declared_type.kind.value
                convert: Callable[[Any], Any] = _identity_fixture_value
                physical: pa.DataType = pa.string()
                if kind in ("signed-integer", "unsigned-integer"):
                    bits = mapped.declared_type.bits  # type: ignore[union-attr]
                    physical = getattr(pa, ("uint" if kind == "unsigned-integer" else "int") + str(32 if bits == 24 else bits))()
                    convert = int
                elif kind in ("float32", "float64"):
                    physical = pa.float32() if kind == "float32" else pa.float64()
                    convert = float
                elif kind == "datetime":
                    physical = pa.timestamp("us")
                    convert = _datetime_fixture_value
                elif mapped.logical_type.value == "set":
                    physical = pa.list_(pa.field("item", pa.string(), nullable=False))
                    convert = _set_fixture_value
                fields.append(pa.field(column.name, physical, nullable=mapped.nullable))
                columns.append([])
                conversions.append(convert)
            count = 0
            for row in reader.stream_rows():
                if len(row) != len(columns):
                    raise ValueError("repository fixture row width mismatch")
                count += 1
                for index, value in enumerate(row):
                    columns[index].append(None if value is None else conversions[index](value))
            arrays = [pa.array(values, type=field.type) for values, field in zip(columns, fields, strict=True)]
            table_arrow = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
            if count > max_rows or len(columns) > max_columns or table_arrow.nbytes > max_input_bytes or max_batches < 1:
                raise MemoryError("fixture Arrow exceeds requested bounds")
            with table_arrow.to_reader() as stream:
                yield stream
        finally:
            reader.close()

    def export_table_artifact(self, table_name: str, export_format: str) -> None:
        del table_name, export_format

    def close(self) -> None:
        self.close_count += 1
        self.closed = True
        if self._close_error:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_SESSION_CLOSE_FAILED,
                "session close failed",
            )


class FakeRepositoryTableAccessProvider:
    def __init__(
        self,
        *,
        catalog: RepositoryTableCatalog,
        rows: RepositoryRows | None = None,
        declared_rows: RepositoryRows | None = None,
        current_commit: str | None = None,
        pad_nulls: bool = True,
        fail_stream: bool = False,
        close_error: bool = False,
        catalog_error: bool = False,
        catalog_error_message: str | None = None,
        missing_table_on_open: str | None = None,
        open_timeout: bool = False,
        open_not_found: bool = False,
        open_failed: bool = False,
        per_read_rows: Sequence[RepositoryRows] = (),
        base_catalog: RepositoryTableCatalog | None = None,
        per_read_catalog_without: Sequence[Sequence[str]] = (),
    ) -> None:
        self.catalog = catalog
        self._base_catalog = base_catalog or catalog
        self.declared_rows = declared_rows if declared_rows is not None else (rows or {})
        self.rows = rows if rows is not None else self.declared_rows
        self._per_read_rows = tuple(per_read_rows)
        self._per_read_catalog_without = tuple(tuple(item) for item in per_read_catalog_without)
        self._materialize_read_index = 0
        self.current_commit = current_commit or catalog.resolved_commit_hash
        self.pad_nulls = pad_nulls
        self.fail_stream = fail_stream
        self.close_error = close_error
        self.catalog_error = catalog_error
        self.catalog_error_message = catalog_error_message
        self.missing_table_on_open = missing_table_on_open
        self.open_timeout = open_timeout
        self.open_not_found = open_not_found
        self.open_failed = open_failed
        self.open_count = 0
        self.last_session: FakeRepositoryRefSession | None = None
        self.sessions: list[FakeRepositoryRefSession] = []

    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> FakeRepositoryRefSession:
        del timeout_policy
        self.open_count += 1
        if self.open_timeout:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_TIMEOUT,
                "open_ref timed out",
                retryable=True,
            )
        if self.open_not_found:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_REF_NOT_FOUND,
                f"repository ref {repository_ref.ref!r} was not found",
            )
        if self.open_failed:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
                "open_ref failed",
            )
        pinned = self.current_commit
        catalog = self.catalog
        read_index = self._materialize_read_index
        if catalog.resolved_commit_hash != pinned:
            catalog = _catalog_at_commit(catalog, pinned)
        rows = self.declared_rows
        if read_index < len(self._per_read_rows):
            rows = self._per_read_rows[read_index]
        if self._per_read_catalog_without:
            drop = self._per_read_catalog_without[read_index] if read_index < len(self._per_read_catalog_without) else ()
            catalog = catalog_without_tables(self._base_catalog, drop=tuple(drop))
            if catalog.resolved_commit_hash != pinned:
                catalog = _catalog_at_commit(catalog, pinned)
        if self._per_read_rows or self._per_read_catalog_without:
            self._materialize_read_index += 1
        session = FakeRepositoryRefSession(
            catalog=catalog,
            rows=rows,
            pinned_commit=pinned,
            pad_nulls=self.pad_nulls,
            fail_stream=self.fail_stream,
            close_error=self.close_error,
            catalog_error=self.catalog_error,
            catalog_error_message=self.catalog_error_message,
            missing_table_on_open=self.missing_table_on_open,
        )
        self.last_session = session
        self.sessions.append(session)
        return session


def int_id_column(*, nullable: bool = False) -> RepositoryColumn:
    return RepositoryColumn(name="id", ordinal=0, scalar_type="INT", nullable=nullable)


def text_column(name: str, ordinal: int, *, nullable: bool = True) -> RepositoryColumn:
    return RepositoryColumn(name=name, ordinal=ordinal, scalar_type="VARCHAR(16)", nullable=nullable)


def catalog_table(
    name: str,
    columns: tuple[RepositoryColumn, ...],
    *,
    primary_key: tuple[str, ...] = ("id",),
    table_root_hash: str | None = None,
    row_count: int | None = None,
) -> RepositoryCatalogTable:
    return RepositoryCatalogTable(
        table_name=name,
        columns=columns,
        primary_key_columns=primary_key,
        table_root_hash=table_root_hash,
        row_count=row_count,
    )


def make_catalog(
    tables: tuple[RepositoryCatalogTable, ...],
    *,
    repository_id: str = DEFAULT_REPOSITORY_ID,
    ref: str = DEFAULT_REF,
    commit: str = DEFAULT_REF,
    cache_hit: bool = False,
    engine_version: str | None = None,
) -> RepositoryTableCatalog:
    return RepositoryTableCatalog(
        repository_id=repository_id,
        repository_ref=ref,
        resolved_commit_hash=commit,
        repository_server_contract_version=REPOSITORY_SERVER_CONTRACT_VERSION,
        tables=tables,
        repository_engine_version=engine_version,
        cache_hit=cache_hit,
    )


def catalog_without_tables(
    catalog: RepositoryTableCatalog,
    *,
    drop: tuple[str, ...],
) -> RepositoryTableCatalog:
    drop_names = {canonicalize_identifier(name) for name in drop}
    remaining = tuple(
        table for table in catalog.tables if canonicalize_identifier(table.table_name) not in drop_names
    )
    return RepositoryTableCatalog(
        repository_id=catalog.repository_id,
        repository_ref=catalog.repository_ref,
        resolved_commit_hash=catalog.resolved_commit_hash,
        repository_server_contract_version=catalog.repository_server_contract_version,
        tables=remaining,
        repository_engine_version=catalog.repository_engine_version,
        catalog_digest=catalog.catalog_digest,
        cache_hit=catalog.cache_hit,
    )


def canonical_binding_for_catalog(
    catalog: RepositoryTableCatalog,
    *,
    ruleset: TableRulesetSnapshot | None = None,
    is_initial: bool = False,
) -> CanonicalBinding:
    active = _complete_ruleset(ruleset or default_ruleset())
    if active.ruleset_digest is None:
        raise AssertionError("completed test ruleset has no digest")
    views: list[StorageRuleView] = []
    if not is_initial:
        for table in catalog.tables:
            if active.rules:
                record = resolve_table_rule(
                    active,
                    table.table_name,
                    primary_key_columns=table.primary_key_columns,
                ).record
                key_columns = (
                    record.compare_key_columns
                    if record.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
                    else tuple(canonicalize_identifier(name) for name in table.primary_key_columns)
                    if record.canonical_key_policy in (CanonicalKeyPolicy.DDL_PRIMARY_KEY, CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS)
                    else ()
                )
                dropped_names = {item.name for item in record.dropped_columns}
                views.append(
                    StorageRuleView(
                        canonical_table=table.table_name,
                        canonical_key_policy=record.canonical_key_policy,
                        ordered_policy=record.ordered_policy,
                        dropped_columns=record.dropped_columns,
                        structural_columns=record.structural_columns,
                        retained_columns=tuple(
                            canonicalize_identifier(column.name)
                            for column in table.columns
                            if canonicalize_identifier(column.name) not in dropped_names
                        ),
                        canonical_key_columns=key_columns,
                    )
                )
            else:
                key_policy = (
                    CanonicalKeyPolicy.DDL_PRIMARY_KEY
                    if table.primary_key_columns
                    else CanonicalKeyPolicy.EXPLICIT_KEYLESS
                )
                views.append(
                    StorageRuleView(
                        canonical_table=table.table_name,
                        canonical_key_policy=key_policy,
                        ordered_policy=OrderedPolicy.NONE,
                        retained_columns=tuple(
                            canonicalize_identifier(column.name) for column in table.columns
                        ),
                        canonical_key_columns=tuple(canonicalize_identifier(name) for name in table.primary_key_columns),
                    )
                )
    return CanonicalBinding(
        storage_projection_version=active.storage_projection_version,
        ruleset_id=active.ruleset_id,
        ruleset_version=active.ruleset_version,
        ruleset_digest=active.ruleset_digest,
        tables=tuple(sorted(views, key=lambda item: item.canonical_table.encode("utf-8"))),
        is_initial=is_initial,
    )


def default_ruleset() -> TableRulesetSnapshot:
    return _complete_ruleset(TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION))


def make_request(
    provider: FakeRepositoryTableAccessProvider,
    *,
    policy: MaterializationPolicy = MaterializationPolicy.DESCRIPTOR_ONLY,
    requested_tables: tuple[str, ...] | None = None,
    timeout_policy: RepositoryRefTimeoutPolicy | None = None,
    context: ParserInvocationContext | None = None,
    parser_version: int | None = None,
    table_ruleset_version: int = TABLE_RULESET_VERSION,
    ruleset: TableRulesetSnapshot | None = None,
    canonical_binding: CanonicalBinding | None = None,
    artifact_store: object | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
) -> RepositoryRefMaterializationRequest:
    active_ruleset = _complete_ruleset(ruleset or default_ruleset())
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=provider.catalog.repository_id, ref=provider.current_commit),
        provider=provider,
        ruleset=active_ruleset,
        canonical_binding=canonical_binding or canonical_binding_for_catalog(
            provider.catalog,
            ruleset=active_ruleset,
        ),
        table_ruleset_version=table_ruleset_version,
        materialization_stage=MaterializationStage.FINAL,
        policy=policy,
        context=context or ParserInvocationContext(NeverCancel()),
        timeout_policy=timeout_policy,
        requested_tables=requested_tables,
        parser_version=parser_version,
        artifact_store=artifact_store,
        export_cache=export_cache,
    )

    return _bind_fixture_tables(request, provider)


def materialize_ref(
    provider: FakeRepositoryTableAccessProvider,
    *,
    policy: MaterializationPolicy = MaterializationPolicy.DESCRIPTOR_ONLY,
    requested_tables: tuple[str, ...] | None = None,
    timeout_policy: RepositoryRefTimeoutPolicy | None = None,
    context: ParserInvocationContext | None = None,
    parser_version: int | None = None,
    table_ruleset_version: int = TABLE_RULESET_VERSION,
    ruleset: TableRulesetSnapshot | None = None,
    canonical_binding: CanonicalBinding | None = None,
    artifact_store: object | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
) -> SnapshotMaterializationResult:
    return materialize_repository_ref(
        make_request(
            provider,
            policy=policy,
            requested_tables=requested_tables,
            timeout_policy=timeout_policy,
            context=context,
            parser_version=parser_version,
            table_ruleset_version=table_ruleset_version,
            ruleset=ruleset,
            canonical_binding=canonical_binding,
            artifact_store=artifact_store,
            export_cache=export_cache,
        )
    )


def minimal_fixture() -> tuple[FakeRepositoryTableAccessProvider, RepositoryRows]:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows: RepositoryRows = {"items": ((1, "a"), (2, None))}
    catalog = make_catalog((table,))
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows)
    return provider, rows


def _catalog_at_commit(catalog: RepositoryTableCatalog, commit_id: str) -> RepositoryTableCatalog:
    return RepositoryTableCatalog(
        repository_id=catalog.repository_id,
        repository_ref=catalog.repository_ref,
        resolved_commit_hash=commit_id,
        repository_server_contract_version=catalog.repository_server_contract_version,
        tables=catalog.tables,
        repository_engine_version=catalog.repository_engine_version,
        catalog_digest=catalog.catalog_digest,
        cache_hit=catalog.cache_hit,
    )


def _complete_ruleset(ruleset: TableRulesetSnapshot) -> TableRulesetSnapshot:
    if ruleset.ruleset_digest is not None:
        return ruleset
    return replace(
        ruleset,
        ruleset_digest=compute_ruleset_digest(table_ruleset_document(ruleset)),
    )


class _FixtureCanonicalIndex:
    """Ephemeral index for the real C port used by metadata/selection fixtures."""
    def __init__(self) -> None:
        self.refs: dict[Any, Any] = {}

    def lookup(self, key: Any) -> Any:
        return self.refs.get(key)

    def register(self, key: Any, ref: Any) -> None:
        self.refs[key] = ref

    def bind_commit(self, *, repository_id: str, commit_id: str, refs: Any) -> None:
        pass


def _bind_fixture_tables(request: RepositoryRefMaterializationRequest, provider: FakeRepositoryTableAccessProvider) -> RepositoryRefMaterializationRequest:
    from types import SimpleNamespace
    from gateway_backend.application.canonical_metadata.table_access import build_committed_table_access
    from gateway_backend.artifacts import InMemoryArtifactStore
    from gateway_backend.capabilities.snapshot_materialization import (
        canonical_columns, canonical_repository_stream, compare_schema_digest,
        operation_business_budgets, current_kernel_context,
    )
    from gateway_backend.capabilities.snapshot_materialization.contracts import (
        CanonicalTableIdentity, SnapshotColumnDescriptor, SnapshotTableDescriptor,
        ROW_MATERIALIZATION_PROFILE, SCALAR_ENCODING_VERSION,
    )
    from gateway_backend.capabilities.storage_projection import compute_schema_digest
    from gateway_backend.capabilities.storage_projection.native import project_arrow_table
    from gateway_shared_kernel import DigestRef
    if not request.canonical_binding.tables:
        return request
    index = _FixtureCanonicalIndex()
    @contextmanager
    def uow() -> Iterator[Any]:
        yield SimpleNamespace(canonical_tables=index)
    port = build_committed_table_access(store=InMemoryArtifactStore(), unit_of_work_factory=uow,
        repository_provider_factory=lambda repository_id, commit_id: provider,
        repository_id=request.repository_ref.repository_id)
    if request.canonical_binding.table_identities:
        return replace(request, committed_tables=port)
    # Construct legitimate fixed-scope metadata using the same Rust/C producer
    # as production. These fixture values are not correctness expectations.
    session = FakeRepositoryRefSession(catalog=provider.catalog, rows=provider.declared_rows,
        pinned_commit=provider.current_commit, pad_nulls=True, fail_stream=False,
        close_error=False, catalog_error=False, catalog_error_message=None, missing_table_on_open=None)
    active = current_kernel_context()
    assert active is not None
    identities = []
    for view in request.canonical_binding.tables:
        catalog_table = next(t for t in provider.catalog.tables if canonicalize_identifier(t.table_name) == view.canonical_table)
        columns = tuple(SnapshotColumnDescriptor(canonicalize_identifier(c.name), c.display_name or c.name,
            True if c.nullable is None else c.nullable, c.scalar_type or c.raw_type or "UNKNOWN") for c in catalog_table.columns)
        keys = tuple(canonicalize_identifier(k) for k in catalog_table.primary_key_columns)
        count = len(provider.declared_rows.get(view.canonical_table, ()))
        schema = compare_schema_digest(view.canonical_table, tuple(c.name for c in columns), keys)
        descriptor = SnapshotTableDescriptor(view.canonical_table, catalog_table.display_table_name or catalog_table.table_name,
            columns, keys, keys, count, request.materialization_stage, schema, request.table_ruleset_version,
            ROW_MATERIALIZATION_PROFILE, SCALAR_ENCODING_VERSION, raw_content_digest=DigestRef("sha256:" + "00" * 32))
        budgets = operation_business_budgets()
        with session.open_arrow_table_reader(catalog_table.table_name, max_rows=budgets["max_rows"],
                max_columns=budgets["max_columns"], max_input_bytes=budgets["max_input_bytes"], max_batches=budgets["max_batches"]) as wire:
            with canonical_repository_stream(wire, descriptor, budgets=budgets) as converted:
                resolved = replace(view, canonical_key_columns=keys) if view.canonical_key_policy.value in ("DDL_PRIMARY_KEY", "DDL_PRIMARY_KEY_OR_KEYLESS") else view
                result = project_arrow_table({"canonical_name": view.canonical_table,
                    "display_name": descriptor.display_table_name, "columns": canonical_columns(descriptor),
                    "primary_key": list(keys), "reader_ready": True, "arrow_stream": converted}, descriptor,
                    resolved, canonicalized_input=True, cancel_probe=active.cancel_probe, budgets=budgets,
                    deadline_monotonic=active.deadline_monotonic, pool_threads=active.threads)
        assert result["output"] is not None, result["diagnostics"]
        result["output"]["tables"][0]["arrow_stream"].close()
        identities.append(CanonicalTableIdentity(view.canonical_table, count, schema,
            compute_schema_digest(columns=[{"name": c.name, "nullable": c.nullable, "sql_type": c.scalar_type} for c in columns],
                primary_key=keys), DigestRef(result["output"]["raw_content_digest"])))
    return replace(request, canonical_binding=replace(request.canonical_binding, table_identities=tuple(identities)), committed_tables=port)
