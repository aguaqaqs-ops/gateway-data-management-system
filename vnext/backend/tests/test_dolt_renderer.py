"""S4 deterministic repository replay SQL renderer tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.mutation_planning import _repository_replay_renderer as replay_renderer
from gateway_backend.capabilities.mutation_planning._digest import key_bytes_for_ordering
from gateway_backend.capabilities.mutation_planning import (
    MutationFailureCode,
    MutationPlanStatus,
    MutationPolicy,
    plan_storage_mutation,
)
from gateway_backend.capabilities.mutation_planning._repository_replay_renderer import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
    render_change_set_replay,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    MAX_REPLAY_SQL_BYTES,
    CanonicalStorageKey,
    ChangeSetClosure,
    ChangeSetMutation,
    MutationTargetKind,
    PersistedRowImage,
    RendererCapabilityDeclaration,
    RowMutationOperation,
)
from tests.support.mutation_contracts import (
    change_set_closure,
    delete_mutation,
    insert_mutation,
    planning_request,
    renderer_capability,
    keyed_row,
    table_snapshot,
    table_summary,
)
from tests.support.mutation_renderer_fixtures import (
    load_closure,
    load_expected_sql,
)
from tests.support.mutation_contracts import int_cell, row_image, storage_key
from gateway_backend.capabilities.mutation_planning.contracts import TableMutationKind

pytestmark = pytest.mark.unit

R7_RENDERER_GOLDEN_CASES: tuple[tuple[str, str], ...] = (
    ("patch-single-update", "valid/patch-single-update"),
    ("first-load-insert", "valid/first-load-insert"),
    ("rebuild-replace-rows", "valid/rebuild-replace-rows"),
    ("destructive-delete", "valid/destructive-delete"),
    ("multi-table-patch", "valid/multi-table-patch"),
    ("mixed-scalars", "valid/mixed-scalars"),
)


@pytest.mark.parametrize(("case_id", "relative_dir"), R7_RENDERER_GOLDEN_CASES)
def test_renderer_golden_cases(case_id: str, relative_dir: str) -> None:
    closure = load_closure(relative_dir)
    expected = load_expected_sql(relative_dir)
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY", case_id
    assert outcome.sql_bytes == expected
    assert outcome.sql_digest == raw_blob_digest(expected)


def test_renderer_is_deterministic_for_golden_closure() -> None:
    closure = load_closure("valid/patch-single-update")
    first = render_change_set_replay(closure)
    second = render_change_set_replay(closure)
    assert first == second
    assert first.sql_bytes is not None
    assert first.sql_digest == raw_blob_digest(first.sql_bytes)


def test_planner_ready_closure_renders_successfully() -> None:
    result = plan_storage_mutation(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(table_snapshot(rows=(keyed_row(),)),),
            after_tables=(table_snapshot(rows=(keyed_row(status="1"),)),),
        )
    )
    assert result.status is MutationPlanStatus.READY
    assert result.change_set_closure is not None
    outcome = render_change_set_replay(result.change_set_closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert outcome.sql_bytes.endswith(b"\n")


def test_multi_table_sql_statement_order_matches_mutations() -> None:
    closure = load_closure("valid/multi-table-patch")
    outcome = render_change_set_replay(closure)
    assert outcome.sql_bytes is not None
    statements = [line for line in outcome.sql_bytes.decode("utf-8").splitlines() if line]
    assert len(statements) <= len(closure.mutations)
    assert all("`orders`" in statement for statement in statements)
    for statement in statements:
        assert statement.endswith(";")


def test_source_literal_anomaly_fixture_fails_closed() -> None:
    closure = load_closure("capability-failures/source-literal-anomaly")
    outcome = render_change_set_replay(closure)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED
    assert outcome.sql_bytes is None


def test_wrong_renderer_capability_digest_fails_closed() -> None:
    closure = change_set_closure(mutations=(delete_mutation(),))
    wrong_capability = RendererCapabilityDeclaration(
        target_kind=MutationTargetKind.CANONICAL_REPOSITORY_REPLAY,
        capability_version=REPOSITORY_REPLAY_RENDERER_CAPABILITY.capability_version,
        capability_digest=DigestRef("sha256:" + "99" * 32),
        capability_contract_version=REPOSITORY_REPLAY_RENDERER_CAPABILITY.capability_contract_version,
    )
    patched_manifest = replace(
        closure.manifest,
        renderer_capability=wrong_capability,
        target_identity=wrong_capability,
    )
    patched = ChangeSetClosure(manifest=patched_manifest, mutations=closure.mutations)
    outcome = render_change_set_replay(patched)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED


def test_external_reference_renderer_capability_fails_closed() -> None:
    closure = change_set_closure(mutations=(delete_mutation(),))
    external = renderer_capability(target_kind=MutationTargetKind.EXTERNAL_REFERENCE)
    patched_manifest = replace(
        closure.manifest,
        renderer_capability=external,
        target_identity=external,
    )
    patched = ChangeSetClosure(manifest=patched_manifest, mutations=closure.mutations)
    outcome = render_change_set_replay(patched)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED


def test_replay_size_cap_rejects_without_partial_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gateway_backend.capabilities.mutation_planning._repository_replay_renderer.MAX_REPLAY_SQL_BYTES",
        64,
    )
    mutations = tuple(insert_mutation(board=str(i), link_no=str(i + 1)) for i in range(8))
    closure = change_set_closure(
        summaries=(table_summary(operation=TableMutationKind.REBUILD_TABLE),),
        mutations=mutations,
    )
    outcome = render_change_set_replay(closure)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.RESOURCE_EXCEEDED
    assert outcome.sql_bytes is None


def test_replay_size_cap_boundary_accepts_under_limit() -> None:
    # One INSERT line is far below MAX_REPLAY_SQL_BYTES.
    closure = change_set_closure(mutations=(insert_mutation(),))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert len(outcome.sql_bytes) < MAX_REPLAY_SQL_BYTES


def test_update_excludes_key_columns_from_set_clause() -> None:
    closure = load_closure("valid/patch-single-update")
    outcome = render_change_set_replay(closure)
    assert outcome.sql_bytes is not None
    text = outcome.sql_bytes.decode("utf-8")
    assert "SET `status`=CASE WHEN" in text
    assert "SET `board`=" not in text
    assert "SET `link_no`=" not in text


def _update_mutation(
    *,
    table: str,
    key: CanonicalStorageKey,
    image: PersistedRowImage,
    label: str,
) -> ChangeSetMutation:
    return ChangeSetMutation(
        canonical_table=table,
        operation=RowMutationOperation.UPDATE,
        canonical_storage_key=key,
        before_row_digest=raw_blob_digest(label.encode("utf-8")),
        after_image=image,
    )


def _sort_by_key(mutations: tuple[ChangeSetMutation, ...]) -> tuple[ChangeSetMutation, ...]:
    return tuple(sorted(mutations, key=lambda item: key_bytes_for_ordering(item.canonical_storage_key)))


def test_renderer_batches_delete_update_and_insert_at_256_rows() -> None:
    deletes = _sort_by_key(
        tuple(delete_mutation(board="1", link_no=str(index)) for index in range(257))
    )
    updates = _sort_by_key(
        tuple(
            _update_mutation(
                table="orders",
                key=storage_key(board="2", link_no=str(index)),
                image=row_image(board="2", link_no=str(index), status="1"),
                label=f"before-update-{index}",
            )
            for index in range(257)
        )
    )
    inserts = _sort_by_key(
        tuple(insert_mutation(board="3", link_no=str(index)) for index in range(257))
    )
    closure = change_set_closure(mutations=(*deletes, *updates, *inserts))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    statements = outcome.sql_bytes.decode("utf-8").splitlines()
    assert [statement.split(" ", maxsplit=1)[0] for statement in statements] == [
        "DELETE",
        "DELETE",
        "UPDATE",
        "UPDATE",
        "INSERT",
        "INSERT",
    ]
    assert [statement.count("),(") + 1 for statement in statements[:4]] == [256, 1, 256, 1]
    assert [statement.count("), (") + 1 for statement in statements[4:]] == [256, 1]
    assert all(len(statement.encode("utf-8")) <= 4 * 1024 * 1024 for statement in statements)


def test_renderer_batches_composite_keys_and_mixed_mutations() -> None:
    deletes = _sort_by_key(
        (
            delete_mutation(board="1", link_no="2"),
            delete_mutation(board="1", link_no="3"),
        )
    )
    updates = _sort_by_key(
        (
            _update_mutation(
                table="orders",
                key=storage_key(board="2", link_no="4"),
                image=row_image(board="2", link_no="4", status="1"),
                label="before-4",
            ),
            _update_mutation(
                table="orders",
                key=storage_key(board="2", link_no="5"),
                image=row_image(board="2", link_no="5", status="2"),
                label="before-5",
            ),
        )
    )
    inserts = _sort_by_key(
        (insert_mutation(board="3", link_no="6"), insert_mutation(board="3", link_no="7"))
    )
    outcome = render_change_set_replay(
        change_set_closure(mutations=(*deletes, *updates, *inserts))
    )
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    statements = outcome.sql_bytes.decode("utf-8").splitlines()
    assert len(statements) == 3
    assert statements[0].startswith(
        "DELETE FROM `orders` WHERE (`board`,`link_no`) IN ((1, 2),(1, 3));"
    )
    assert statements[1].startswith("UPDATE `orders` SET `status`=CASE WHEN")
    assert "WHEN `board`=2 AND `link_no`=4 THEN 1" in statements[1]
    assert "WHEN `board`=2 AND `link_no`=5 THEN 2" in statements[1]
    assert "WHERE (`board`,`link_no`) IN ((2, 4),(2, 5));" in statements[1]
    assert statements[2].startswith("INSERT INTO `orders` ")
    assert statements[0].startswith("DELETE") and statements[1].startswith("UPDATE")
    assert statements[2].count("), (") == 1


def test_renderer_uses_gid_as_ordered_storage_key_and_updates_no_as_value() -> None:
    mutations: list[ChangeSetMutation] = []
    for index in (1, 2):
        gid = 4_000_000_000 + index
        key = CanonicalStorageKey(
            columns=(("gid", {"kind": "unsigned-integer", "decimal": str(gid)}),)
        )
        image = PersistedRowImage(
            columns=(
                ("gid", {"kind": "unsigned-integer", "decimal": str(gid)}),
                ("no", int_cell(str(index + 20))),
                ("payload", {"kind": "string", "text": f"point-{index}"}),
            )
        )
        mutations.append(
            _update_mutation(
                table="ordered_points",
                key=key,
                image=image,
                label=f"before-ordered-{index}",
            )
        )
    outcome = render_change_set_replay(
        change_set_closure(mutations=_sort_by_key(tuple(mutations)))
    )
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    statement = outcome.sql_bytes.decode("utf-8").strip()
    assert statement.startswith("UPDATE `ordered_points` SET `no`=CASE WHEN `gid`=")
    assert ", `payload`=CASE WHEN `gid`=" in statement
    assert "`gid`=CASE" not in statement
    assert "WHERE `gid` IN (4000000001,4000000002);" in statement


def test_renderer_splits_update_batches_at_the_statement_byte_limit() -> None:
    payload = "x" * 2_100_000
    mutations = tuple(
        _update_mutation(
            table="orders",
            key=storage_key(board="9", link_no=str(index)),
            image=PersistedRowImage(
                columns=(
                    ("board", int_cell("9")),
                    ("link_no", int_cell(str(index))),
                    ("payload", {"kind": "string", "text": payload}),
                )
            ),
            label=f"before-wide-{index}",
        )
        for index in range(2)
    )
    closure = change_set_closure(mutations=_sort_by_key(mutations))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    statements = outcome.sql_bytes.decode("utf-8").splitlines()
    assert len(statements) == 2
    assert all(len(statement.encode("utf-8")) <= 4 * 1024 * 1024 for statement in statements)


def test_renderer_splits_delete_batches_at_the_statement_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(replay_renderer, "_MAX_DELETE_STATEMENT_BYTES", 1_500)
    deletes = tuple(
        ChangeSetMutation(
            canonical_table="wide_keys",
            operation=RowMutationOperation.DELETE,
            canonical_storage_key=CanonicalStorageKey(
                columns=(("id", {"kind": "string", "text": f"key-{index}-" + "x" * 900}),)
            ),
            before_row_digest=raw_blob_digest(f"wide-before-{index}".encode("utf-8")),
        )
        for index in range(2)
    )
    closure = change_set_closure(mutations=_sort_by_key(deletes))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    statements = outcome.sql_bytes.splitlines()
    assert len(statements) == 2
    assert all(len(statement) <= 1_500 for statement in statements)


def _mutation_with_text_value(
    operation: RowMutationOperation,
    *,
    index: int,
    value_size: int,
) -> ChangeSetMutation:
    text = ("é" * (value_size // 2)) + ("x" if value_size % 2 else "")
    if operation is RowMutationOperation.DELETE:
        return ChangeSetMutation(
            canonical_table="wide_keys",
            operation=operation,
            canonical_storage_key=CanonicalStorageKey(
                columns=(("id", {"kind": "string", "text": f"{index}-" + text}),)
            ),
            before_row_digest=raw_blob_digest(f"before-{index}".encode("utf-8")),
        )

    base = (
        insert_mutation(table="wide_values", board=str(index), link_no="1")
        if operation is RowMutationOperation.INSERT
        else _update_mutation(
            table="wide_values",
            key=storage_key(board=str(index), link_no="1"),
            image=row_image(board=str(index), link_no="1"),
            label=f"before-{index}",
        )
    )
    assert base.after_image is not None
    image = PersistedRowImage(
        columns=tuple(
            (name, {"kind": "string", "text": text}) if name == "status" else (name, cell)
            for name, cell in base.after_image.columns
        )
    )
    return replace(base, after_image=image)


def _rendered_statement_sizes(mutations: tuple[ChangeSetMutation, ...]) -> tuple[int, ...]:
    outcome = render_change_set_replay(change_set_closure(mutations=mutations))
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    return tuple(len(statement) for statement in outcome.sql_bytes.splitlines(keepends=True))


def _value_size_for_statement(
    operation: RowMutationOperation,
    *,
    target_size: int,
    row_count: int,
) -> int:
    first = _mutation_with_text_value(operation, index=1, value_size=32)
    low = 0
    high = target_size * 2
    while low <= high:
        candidate_size = (low + high) // 2
        mutations = (first, *(
            _mutation_with_text_value(
                operation,
                index=index,
                value_size=candidate_size,
            )
            for index in range(2, row_count + 1)
        ))
        sizes = _rendered_statement_sizes(tuple(mutations))
        assert len(sizes) == 1
        if sizes[0] == target_size:
            return candidate_size
        if sizes[0] < target_size:
            low = candidate_size + 1
        else:
            high = candidate_size - 1
    raise AssertionError(f"no payload size renders a {target_size}-byte statement")


@pytest.mark.parametrize(
    "operation",
    (
        RowMutationOperation.INSERT,
        RowMutationOperation.UPDATE,
        RowMutationOperation.DELETE,
    ),
)
def test_mutation_statement_byte_limit_includes_complete_utf8_statement(
    monkeypatch: pytest.MonkeyPatch,
    operation: RowMutationOperation,
) -> None:
    byte_limit = 4 * 1024 * 1024
    limit_name = {
        RowMutationOperation.INSERT: "_MAX_INSERT_STATEMENT_BYTES",
        RowMutationOperation.UPDATE: "_MAX_UPDATE_STATEMENT_BYTES",
        RowMutationOperation.DELETE: "_MAX_DELETE_STATEMENT_BYTES",
    }[operation]
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit * 2)

    exact_value_size = _value_size_for_statement(
        operation,
        target_size=byte_limit,
        row_count=2,
    )
    exact_mutations = (
        _mutation_with_text_value(operation, index=1, value_size=32),
        _mutation_with_text_value(operation, index=2, value_size=exact_value_size),
    )
    assert _rendered_statement_sizes((exact_mutations[0],))[0] < byte_limit
    assert _rendered_statement_sizes((exact_mutations[1],))[0] < byte_limit
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit)
    assert _rendered_statement_sizes(exact_mutations) == (byte_limit,)

    over_limit_mutations = (
        exact_mutations[0],
        _mutation_with_text_value(
            operation,
            index=2,
            value_size=exact_value_size + 1,
        ),
    )
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit * 2)
    assert _rendered_statement_sizes(over_limit_mutations) == (byte_limit + 1,)
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit)
    split_sizes = _rendered_statement_sizes(over_limit_mutations)
    assert len(split_sizes) == 2
    assert all(size <= byte_limit for size in split_sizes)

    oversized_value_size = _value_size_for_statement(
        operation,
        target_size=byte_limit + 1,
        row_count=1,
    )
    oversized_mutation = _mutation_with_text_value(
        operation,
        index=3,
        value_size=oversized_value_size,
    )
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit * 2)
    assert _rendered_statement_sizes((oversized_mutation,)) == (byte_limit + 1,)
    monkeypatch.setattr(replay_renderer, limit_name, byte_limit)
    assert _rendered_statement_sizes((oversized_mutation,)) == (byte_limit + 1,)


def test_string_escape_in_sql_literal() -> None:
    image = PersistedRowImage(
        columns=(
            ("board", {"kind": "string", "text": "a'b\\n"}),
            ("link_no", {"kind": "signed-integer", "decimal": "1"}),
            ("status", {"kind": "signed-integer", "decimal": "9"}),
        )
    )
    mutation = ChangeSetMutation(
        canonical_table="orders",
        operation=RowMutationOperation.INSERT,
        canonical_storage_key=CanonicalStorageKey(
            columns=(
                ("board", {"kind": "string", "text": "a'b\\n"}),
                ("link_no", {"kind": "signed-integer", "decimal": "1"}),
            )
        ),
        after_image=image,
    )
    closure = change_set_closure(mutations=(mutation,))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert b"a\\'b\\\\n" in outcome.sql_bytes
