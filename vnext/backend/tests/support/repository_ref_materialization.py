"""In-memory RepositoryRef provider for S4 unit tests. Not a production adapter."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    fast_row_digest_of,
    fast_row_hash,
    raw_content_digest_of,
    raw_state_digest_of,
    row_content_hash,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DIGEST_CONTRACT_VERSION,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
    DegradedReason,
    HiddenFinalSummary,
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
    SnapshotColumnDescriptor,
    SnapshotMaterializationResult,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import (
    materialize_repository_ref,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_VERSION,
    NeverCancel,
    ParserInvocationContext,
)
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)

REPOSITORY_SERVER_CONTRACT_VERSION = 1
DEFAULT_REPOSITORY_ID = "repo-s4"
DEFAULT_REF = "abc123def456abc123def456abc123de"
DEFAULT_SNAPSHOT_ID = "snap01ab23cd45ef67890123456789abcd"
RepositoryRows = Mapping[str, Sequence[Sequence[object | None]]]


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
        self._closed = False

    def catalog_table(self) -> RepositoryCatalogTable:
        return self._table

    def column_order(self) -> tuple[str, ...]:
        return tuple(column.name for column in self._table.columns)

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
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
        self._closed = True


class FakeRepositoryRefSession:
    def __init__(
        self,
        *,
        catalog: RepositoryTableCatalog,
        hidden: HiddenFinalSummary | None,
        rows: RepositoryRows,
        pinned_commit: str,
        pad_nulls: bool,
        fail_stream: bool,
        close_error: bool,
        hidden_corrupt: bool,
        catalog_error: bool,
        missing_table_on_open: str | None,
    ) -> None:
        self._catalog = catalog
        self._hidden = hidden
        self._rows = rows
        self._pinned_commit = pinned_commit
        self._pad_nulls = pad_nulls
        self._fail_stream = fail_stream
        self._close_error = close_error
        self._hidden_corrupt = hidden_corrupt
        self._catalog_error = catalog_error
        self._missing_table_on_open = missing_table_on_open
        self.catalog_load_count = 0
        self.close_count = 0
        self._memo: RepositoryTableCatalog | None = None
        self.closed = False

    def pinned_commit_hash(self) -> str:
        return self._pinned_commit

    def get_catalog(self) -> RepositoryTableCatalog:
        if self._catalog_error:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                "catalog load failed",
            )
        if self._memo is None:
            self.catalog_load_count += 1
            self._memo = self._catalog
        return self._memo

    def read_hidden_summary(self) -> HiddenFinalSummary | None:
        if self._hidden_corrupt:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT,
                "hidden summary is corrupt",
            )
        return self._hidden

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
                return FakeRepositoryTableReader(
                    table,
                    tuple(tuple(row) for row in self._rows.get(canonical, ())),
                    pad_nulls=self._pad_nulls,
                    fail_stream=self._fail_stream,
                )
        raise RepositoryProviderError(
            MaterializationDiagnosticCode.REPOSITORY_TABLE_NOT_FOUND,
            f"table {table_name!r} is not in the catalog",
            table=table_name,
        )

    def export_table_artifact(self, table_name: str, export_format: str) -> None:
        return None

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
        hidden: HiddenFinalSummary | None,
        rows: RepositoryRows | None = None,
        declared_rows: RepositoryRows | None = None,
        current_commit: str | None = None,
        pad_nulls: bool = True,
        fail_stream: bool = False,
        close_error: bool = False,
        hidden_corrupt: bool = False,
        catalog_error: bool = False,
        missing_table_on_open: str | None = None,
        open_timeout: bool = False,
        open_not_found: bool = False,
        open_failed: bool = False,
        per_read_mutate_raw_digest_table: Sequence[str | None] = (),
        per_read_raw_digest_extra_by_table: Sequence[Mapping[str, bytes]] = (),
        per_read_rows: Sequence[RepositoryRows] = (),
        base_catalog: RepositoryTableCatalog | None = None,
        per_read_catalog_without: Sequence[Sequence[str]] = (),
        per_read_hidden_catalog_without: Sequence[Sequence[str]] = (),
    ) -> None:
        self.catalog = catalog
        self._base_catalog = base_catalog or catalog
        self.hidden = hidden
        self.declared_rows = declared_rows if declared_rows is not None else (rows or {})
        self.rows = rows if rows is not None else self.declared_rows
        self._per_read_mutate_raw_digest_table = tuple(per_read_mutate_raw_digest_table)
        self._per_read_raw_digest_extra_by_table = tuple(per_read_raw_digest_extra_by_table)
        self._per_read_rows = tuple(per_read_rows)
        self._per_read_catalog_without = tuple(tuple(item) for item in per_read_catalog_without)
        self._per_read_hidden_catalog_without = tuple(tuple(item) for item in per_read_hidden_catalog_without)
        self._materialize_read_index = 0
        self.current_commit = current_commit or catalog.resolved_commit_hash
        self.pad_nulls = pad_nulls
        self.fail_stream = fail_stream
        self.close_error = close_error
        self.hidden_corrupt = hidden_corrupt
        self.catalog_error = catalog_error
        self.missing_table_on_open = missing_table_on_open
        self.open_timeout = open_timeout
        self.open_not_found = open_not_found
        self.open_failed = open_failed
        self.open_count = 0
        self.last_session: FakeRepositoryRefSession | None = None

    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> FakeRepositoryRefSession:
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
        read_index = self._materialize_read_index
        base_catalog = self._base_catalog
        if base_catalog.resolved_commit_hash != pinned:
            base_catalog = RepositoryTableCatalog(
                repository_id=base_catalog.repository_id,
                repository_ref=base_catalog.repository_ref,
                resolved_commit_hash=pinned,
                repository_server_contract_version=base_catalog.repository_server_contract_version,
                tables=base_catalog.tables,
                repository_engine_version=base_catalog.repository_engine_version,
                catalog_digest=base_catalog.catalog_digest,
                cache_hit=base_catalog.cache_hit,
            )
        catalog = self.catalog
        if catalog.resolved_commit_hash != pinned:
            catalog = RepositoryTableCatalog(
                repository_id=catalog.repository_id,
                repository_ref=catalog.repository_ref,
                resolved_commit_hash=pinned,
                repository_server_contract_version=catalog.repository_server_contract_version,
                tables=catalog.tables,
                repository_engine_version=catalog.repository_engine_version,
                catalog_digest=catalog.catalog_digest,
                cache_hit=catalog.cache_hit,
            )
        hidden = self.hidden
        session_rows = self.declared_rows
        if (
            self._per_read_rows
            or self._per_read_mutate_raw_digest_table
            or self._per_read_raw_digest_extra_by_table
            or self._per_read_catalog_without
            or self._per_read_hidden_catalog_without
        ):
            if read_index < len(self._per_read_rows):
                session_rows = self._per_read_rows[read_index]
            catalog_drop: tuple[str, ...] = ()
            if read_index < len(self._per_read_catalog_without):
                catalog_drop = self._per_read_catalog_without[read_index]
            if catalog_drop:
                catalog = catalog_without_tables(base_catalog, drop=catalog_drop)
            elif self._per_read_catalog_without or self._per_read_hidden_catalog_without:
                catalog = base_catalog
            hidden_drop: tuple[str, ...] = ()
            if read_index < len(self._per_read_hidden_catalog_without):
                hidden_drop = self._per_read_hidden_catalog_without[read_index]
            if hidden_drop:
                hidden_catalog = catalog_without_tables(base_catalog, drop=hidden_drop)
                hidden = hidden_summary_for(hidden_catalog, self.declared_rows)
            elif self._per_read_catalog_without and read_index < len(self._per_read_catalog_without):
                hidden = hidden_summary_for(base_catalog, self.declared_rows)
            mutate_table = None
            extras: Mapping[str, bytes] = {}
            if read_index < len(self._per_read_mutate_raw_digest_table):
                mutate_table = self._per_read_mutate_raw_digest_table[read_index]
            if read_index < len(self._per_read_raw_digest_extra_by_table):
                extras = self._per_read_raw_digest_extra_by_table[read_index]
            if self._per_read_mutate_raw_digest_table or self._per_read_raw_digest_extra_by_table:
                hidden = hidden_summary_for(
                    catalog,
                    self.declared_rows,
                    mutate_raw_digest_table=mutate_table,
                    raw_digest_extra_by_table=extras,
                )
            self._materialize_read_index += 1
        session = FakeRepositoryRefSession(
            catalog=catalog,
            hidden=hidden,
            rows=session_rows,
            pinned_commit=pinned,
            pad_nulls=self.pad_nulls,
            fail_stream=self.fail_stream,
            close_error=self.close_error,
            hidden_corrupt=self.hidden_corrupt,
            catalog_error=self.catalog_error,
            missing_table_on_open=self.missing_table_on_open,
        )
        self.last_session = session
        return session


def int_id_column(*, nullable: bool = False) -> RepositoryColumn:
    return RepositoryColumn(name="id", ordinal=0, scalar_type="INT", nullable=nullable)


def text_column(name: str, ordinal: int, *, nullable: bool = True) -> RepositoryColumn:
    return RepositoryColumn(
        name=name, ordinal=ordinal, scalar_type="VARCHAR(16)", nullable=nullable
    )


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
        table
        for table in catalog.tables
        if canonicalize_identifier(table.table_name) not in drop_names
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


def hidden_summary_for(
    catalog: RepositoryTableCatalog,
    rows: RepositoryRows,
    *,
    snapshot_id: str = DEFAULT_SNAPSHOT_ID,
    parser_version: int = PARSER_VERSION,
    table_ruleset_version: int = TABLE_RULESET_VERSION,
    digest_contract_version: int = DIGEST_CONTRACT_VERSION,
    scalar_encoding_version: int = SCALAR_ENCODING_VERSION,
    snapshot_materialization_contract_version: int = SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    summary_contract_version: int = SUMMARY_CONTRACT_VERSION,
    stage: MaterializationStage = MaterializationStage.FINAL,
    mutate_snapshot_digest: bool = False,
    mutate_raw_digest_table: str | None = None,
    raw_digest_extra_by_table: Mapping[str, bytes] | None = None,
) -> HiddenFinalSummary:
    descriptors: list[SnapshotTableDescriptor] = []
    for table in catalog.tables:
        canonical = canonicalize_identifier(table.table_name)
        mapped = tuple(map_repository_column(column) for column in table.columns)
        source_columns = tuple(item.source for item in mapped)
        column_names = tuple(item.canonical_name for item in source_columns)
        compare_keys = tuple(canonicalize_identifier(name) for name in table.primary_key_columns)
        schema = compare_schema_digest(canonical, column_names, compare_keys)
        table_rows = rows.get(canonical, ())
        encoded = tuple(
            encode_repository_row(table.columns, tuple(row), table=canonical).cells
            for row in table_rows
        )
        row_hashes = tuple(row_content_hash(source_columns, row) for row in encoded)
        fast_hashes = tuple(fast_row_hash(source_columns, row) for row in encoded)
        raw_digest = raw_content_digest_of(row_hashes)
        if mutate_raw_digest_table == canonical:
            raw_digest = raw_content_digest_of((*row_hashes, b"\x00" * 32))
        extra = (raw_digest_extra_by_table or {}).get(canonical)
        if extra is not None:
            raw_digest = raw_content_digest_of((*row_hashes, extra))
        columns = tuple(
            SnapshotColumnDescriptor(
                name=item.canonical_name,
                display_name=item.display_name,
                nullable=item.nullable,
                scalar_type=item.sql_type,
            )
            for item in source_columns
        )
        degraded = DegradedReason.KEYLESS if not compare_keys else None
        descriptors.append(
            SnapshotTableDescriptor(
                table_name=canonical,
                display_table_name=table.display_table_name or table.table_name,
                columns=columns,
                primary_key_columns=compare_keys,
                compare_key_columns=compare_keys,
                row_count=len(encoded),
                materialization_stage=stage,
                compare_schema_digest=schema,
                table_ruleset_version=table_ruleset_version,
                row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
                scalar_encoding_version=SCALAR_ENCODING_VERSION,
                fast_row_digest=fast_row_digest_of(fast_hashes),
                raw_content_digest=raw_digest if stage is MaterializationStage.FINAL else None,
                degraded_reason=degraded,
            )
        )
    tables = tuple(descriptors)
    snapshot_digest = snapshot_digest_of(
        stage=stage,
        parser_version=parser_version,
        table_ruleset_version=table_ruleset_version,
        tables=tables,
    )
    if mutate_snapshot_digest:
        snapshot_digest = snapshot_digest_of(
            stage=stage,
            parser_version=parser_version + 1,
            table_ruleset_version=table_ruleset_version,
            tables=tables,
        )
    return HiddenFinalSummary(
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state_digest_of(tables),
        materialization_stage=stage,
        parser_version=parser_version,
        table_ruleset_version=table_ruleset_version,
        summary_contract_version=summary_contract_version,
        scalar_encoding_version=scalar_encoding_version,
        snapshot_materialization_contract_version=snapshot_materialization_contract_version,
        digest_contract_version=digest_contract_version,
        tables=tables,
    )


def default_ruleset() -> TableRulesetSnapshot:
    return TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION)


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
    artifact_store: object | None = None,
) -> RepositoryRefMaterializationRequest:
    return RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=DEFAULT_REPOSITORY_ID, ref=DEFAULT_REF),
        provider=provider,
        ruleset=ruleset or default_ruleset(),
        table_ruleset_version=table_ruleset_version,
        materialization_stage=MaterializationStage.FINAL,
        policy=policy,
        context=context or ParserInvocationContext(NeverCancel()),
        timeout_policy=timeout_policy,
        requested_tables=requested_tables,
        parser_version=parser_version,
        artifact_store=artifact_store,
    )


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
    artifact_store: object | None = None,
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
            artifact_store=artifact_store,
        )
    )


def minimal_fixture() -> tuple[FakeRepositoryTableAccessProvider, RepositoryRows]:
    table = catalog_table(
        "items",
        (int_id_column(), text_column("name", 1)),
    )
    rows: RepositoryRows = {"items": ((1, "a"), (2, None))}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    return provider, rows
