"""Unit tests for Versioned fixture consumer support."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    RepositoryArtifactRef,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedCatalog,
    VersionedColumn,
    VersionedImportResult,
    VersionedTable,
)
from support.versioned_fixture_consumer import (
    FIXTURE_PACKAGE_FACTS,
    ConsumerSummary,
    ExpectedColumn,
    ExpectedFacts,
    ExpectedTableCatalog,
    ExpectedTableRows,
    _sanitize_error_message,
    assert_arrow_schema_matches,
    assert_catalog_matches,
    assert_import_result_identity,
    assert_rows_match,
    assert_upload_artifact_ref,
    canonical_row_set,
    client_failure_summary,
    decode_arrow_stream,
    expected_arrow_schema,
    load_expected_facts,
    load_fixture_bundle,
    package_digest,
    parse_expected_facts,
    read_package_manifest_digest,
    row_primary_key_tuple,
    validate_fixture_package_bytes,
)

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "versioned_v1"
SUPPORT_ROOT = Path(__file__).resolve().parent / "support"
_ARROW_IPC_STREAM_EOS = b"\xff\xff\xff\xff\x00\x00\x00\x00"

_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
_MANIFEST_DIGEST = "digest"


def _encode_arrow_stream(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with pa_ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    raw: bytes = sink.getvalue().to_pybytes()
    assert raw.endswith(_ARROW_IPC_STREAM_EOS)
    return raw


def _minimal_expected_payload(*, row_count: object = 0) -> dict[str, object]:
    return {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": row_count,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }


def test_parse_expected_facts_rejects_extra_top_level_key() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        parse_expected_facts({"catalog": {"tables": {}}, "rows": {}, "commit_id": "x"})


def test_parse_expected_facts_rejects_invalid_row_count() -> None:
    payload = _minimal_expected_payload(row_count=-1)
    with pytest.raises(ValueError, match="row_count"):
        parse_expected_facts(payload)


@pytest.mark.parametrize("row_count", [True, 1.0, "1"])
def test_parse_expected_facts_rejects_non_integer_row_count(row_count: object) -> None:
    payload = _minimal_expected_payload(row_count=row_count)
    with pytest.raises(ValueError, match="row_count"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_catalog_rows_table_mismatch() -> None:
    payload = {
        "catalog": {
            "tables": {
                "a": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "b": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="same table set"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_empty_primary_key() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": [],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": [],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="primary_key must not be empty"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_column_names() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [
                        {"name": "id", "sql_type": "INT", "nullable": False},
                        {"name": "id", "sql_type": "BIGINT", "nullable": False},
                    ],
                    "primary_key": ["id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate names"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_primary_key_columns() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id", "id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id", "id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate column names"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_record_primary_keys() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": 2,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [
                    {"id": 1},
                    {"id": 1},
                ],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate primary keys"):
        parse_expected_facts(payload)


def test_load_expected_facts_is_deterministic(tmp_path: Path) -> None:
    payload = _minimal_expected_payload()
    path = tmp_path / "expected.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    first = load_expected_facts(path)
    second = load_expected_facts(path)
    assert first == second


def test_fixture_material_exists_and_package_digest_is_stable() -> None:
    for label in ("c1", "c2"):
        bundle = load_fixture_bundle(FIXTURE_ROOT, label)
        assert bundle.package_bytes
        first = package_digest(bundle.package_bytes)
        second = package_digest(bundle.package_bytes)
        assert first == second
        assert first[0] > 0
        assert len(first[1]) == 64


def test_canonical_row_set_is_order_independent() -> None:
    records_a = (
        {"id": 2, "label": "b"},
        {"id": 1, "label": "a"},
    )
    records_b = (
        {"id": 1, "label": "a"},
        {"id": 2, "label": "b"},
    )
    primary_key = ("id",)
    assert canonical_row_set(records_a, primary_key=primary_key) == canonical_row_set(
        records_b,
        primary_key=primary_key,
    )
    assert row_primary_key_tuple(records_a[0], primary_key) == (2,)


def test_assert_rows_match_rejects_duplicate_primary_keys() -> None:
    expected = ExpectedTableRows(
        primary_key=("id",),
        records=(
            {"id": 1, "label": "alpha"},
            {"id": 2, "label": "beta"},
        ),
    )
    actual = [
        {"id": 1, "label": "alpha"},
        {"id": 1, "label": "alpha"},
    ]
    with pytest.raises(AssertionError, match="duplicate primary keys"):
        assert_rows_match(actual, expected, table_name="items")


def test_c1_c2_expected_catalog_differ() -> None:
    c1 = load_fixture_bundle(FIXTURE_ROOT, "c1")
    c2 = load_fixture_bundle(FIXTURE_ROOT, "c2")
    assert set(c1.expected.catalog) == {"fixture_items"}
    assert set(c2.expected.catalog) == {"fixture_items", "fixture_meta"}
    assert c1.expected.catalog["fixture_items"].row_count == 1
    assert c2.expected.catalog["fixture_items"].row_count == 2


def test_assert_import_result_identity_rejects_drift() -> None:
    result = VersionedImportResult(
        commit_id="commit-c1",
        target_ref="main",
        artifact_id=_ARTIFACT_ID,
        canonicalization_manifest_digest="digest",
        expected_commit_id="commit-c0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    with pytest.raises(AssertionError, match="expected_commit_id"):
        assert_import_result_identity(
            result,
            expected_commit_id="commit-wrong",
            artifact_id=_ARTIFACT_ID,
            manifest_digest=_MANIFEST_DIGEST,
        )


@pytest.mark.parametrize(
    ("policy_field", "policy_value"),
    [
        ("completed_verification_policy", VerificationPolicy.FULL_SCAN),
        ("unknown_type_policy", UnknownTypePolicy.STRINGIFY),
    ],
)
def test_assert_import_result_identity_rejects_policy_drift(
    policy_field: str,
    policy_value: VerificationPolicy | UnknownTypePolicy,
) -> None:
    result = VersionedImportResult(
        commit_id="commit-c1",
        target_ref="main",
        artifact_id=_ARTIFACT_ID,
        canonicalization_manifest_digest="digest",
        expected_commit_id="commit-c0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    drifted = result.model_copy(update={policy_field: policy_value})
    with pytest.raises(AssertionError, match=policy_field):
        assert_import_result_identity(
            drifted,
            expected_commit_id="commit-c0",
            artifact_id=_ARTIFACT_ID,
            manifest_digest=_MANIFEST_DIGEST,
        )


def test_decode_arrow_stream_rejects_truncated_body() -> None:
    table = pa.table({"id": [1]})
    sink = pa.BufferOutputStream()
    with pa_ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    truncated = sink.getvalue().to_pybytes()[:16]
    with pytest.raises((pa.ArrowInvalid, OSError, EOFError, ValueError)):
        decode_arrow_stream(truncated)


def test_support_modules_do_not_import_service() -> None:
    banned = "gateway_repository_service"
    offenders: list[str] = []
    for path in sorted(SUPPORT_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == banned:
                        offenders.append(f"{path.name}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.split(".")[0] == banned:
                    offenders.append(f"{path.name}:{node.module}")
    assert offenders == []


MALFORMED_EXPECTED_SHAPES: tuple[tuple[dict[str, object], str], ...] = (
    (
        {
            "catalog": {"tables": {}, "commit_id": "x"},
            "rows": {},
        },
        "catalog has unexpected keys",
    ),
    (
        {
            "catalog": {
                "tables": {
                    "items": {
                        "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                        "primary_key": ["id"],
                        "row_count": 1,
                    }
                }
            },
            "rows": {
                "items": {
                    "primary_key": ["id"],
                    "records": [],
                }
            },
        },
        "row_count and rows.records length must match",
    ),
    (
        {
            "catalog": {
                "tables": {
                    "items": {
                        "columns": [
                            {"name": "id", "sql_type": "INT", "nullable": False},
                            {"name": "label", "sql_type": "VARCHAR(8)", "nullable": False},
                        ],
                        "primary_key": ["id"],
                        "row_count": 1,
                    }
                }
            },
            "rows": {
                "items": {
                    "primary_key": ["id"],
                    "records": [{"id": 1, "label": "a", "extra": True}],
                }
            },
        },
        "keys must match column names exactly",
    ),
    (
        {
            "catalog": {
                "tables": {
                    "items": {
                        "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                        "primary_key": ["missing"],
                        "row_count": 0,
                    }
                }
            },
            "rows": {
                "items": {
                    "primary_key": ["missing"],
                    "records": [],
                }
            },
        },
        "undeclared columns",
    ),
    (
        {
            "catalog": {
                "tables": {
                    "items": {
                        "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                        "primary_key": ["id"],
                        "row_count": 0,
                    }
                }
            },
            "rows": {
                "items": {
                    "primary_key": ["pk"],
                    "records": [],
                }
            },
        },
        "primary_key must match",
    ),
)


@pytest.mark.parametrize(("payload", "match"), MALFORMED_EXPECTED_SHAPES)
def test_parse_expected_facts_rejects_malformed_shapes(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_expected_facts(payload)


def test_load_expected_facts_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "expected.json"
    path.write_text('{"catalog": {"tables": {}}, "catalog": {"tables": {}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_expected_facts(path)


def test_fixture_package_facts_match_committed_bytes() -> None:
    for label, (expected_size, expected_sha) in FIXTURE_PACKAGE_FACTS.items():
        bundle = load_fixture_bundle(FIXTURE_ROOT, label)
        size_bytes, raw_sha256 = package_digest(bundle.package_bytes)
        assert (size_bytes, raw_sha256) == (expected_size, expected_sha)
        manifest = validate_fixture_package_bytes(label, bundle.package_bytes, bundle.expected)
        assert manifest.canonicalization_manifest_digest == read_package_manifest_digest(bundle.package_bytes)


def test_assert_upload_artifact_ref_rejects_drift() -> None:
    ref = RepositoryArtifactRef(
        artifact_id=_ARTIFACT_ID,
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        size_bytes=10,
        raw_sha256="a" * 64,
    )
    with pytest.raises(AssertionError, match="size_bytes"):
        assert_upload_artifact_ref(
            ref,
            size_bytes=11,
            raw_sha256="a" * 64,
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        )


def test_assert_import_result_identity_rejects_manifest_digest_drift() -> None:
    result = VersionedImportResult(
        commit_id="commit-c1",
        target_ref="main",
        artifact_id=_ARTIFACT_ID,
        canonicalization_manifest_digest="wrong",
        expected_commit_id="commit-c0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    with pytest.raises(AssertionError, match="canonicalization_manifest_digest"):
        assert_import_result_identity(
            result,
            expected_commit_id="commit-c0",
            artifact_id=_ARTIFACT_ID,
            manifest_digest=_MANIFEST_DIGEST,
        )


def _catalog_response(
    *,
    commit_id: str,
    tables: tuple[VersionedTable, ...],
) -> GetVersionedCatalogResponse:
    return GetVersionedCatalogResponse(catalog=VersionedCatalog(commit_id=commit_id, tables=tables))


def _items_table(*, row_count: int = 1) -> VersionedTable:
    return VersionedTable(
        name="items",
        columns=(
            VersionedColumn(name="id", sql_type="INT", nullable=False),
        ),
        primary_key=("id",),
        row_count=row_count,
    )


def test_assert_catalog_matches_rejects_wrong_commit_id() -> None:
    expected = ExpectedFacts(
        catalog={
            "items": ExpectedTableCatalog(
                columns=(ExpectedColumn(name="id", sql_type="INT", nullable=False),),
                primary_key=("id",),
                row_count=1,
            )
        },
        rows={"items": ExpectedTableRows(primary_key=("id",), records=({"id": 1},))},
    )
    response = _catalog_response(commit_id="wrong", tables=(_items_table(),))
    with pytest.raises(AssertionError, match="commit_id mismatch"):
        assert_catalog_matches(response, expected, commit_id="expected-commit")


def test_assert_catalog_matches_rejects_duplicate_table_names() -> None:
    expected = ExpectedFacts(
        catalog={
            "items": ExpectedTableCatalog(
                columns=(ExpectedColumn(name="id", sql_type="INT", nullable=False),),
                primary_key=("id",),
                row_count=1,
            )
        },
        rows={"items": ExpectedTableRows(primary_key=("id",), records=({"id": 1},))},
    )
    duplicate_tables = (_items_table(), _items_table())
    response = _catalog_response(commit_id="commit", tables=duplicate_tables)
    with pytest.raises(AssertionError, match="duplicate table names"):
        assert_catalog_matches(response, expected, commit_id="commit")


def test_decode_arrow_stream_rejects_missing_eos() -> None:
    table = pa.table({"id": [1]})
    sink = pa.BufferOutputStream()
    with pa_ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    body_with_native_eos = sink.getvalue().to_pybytes()
    body_without_eos = body_with_native_eos[: -len(_ARROW_IPC_STREAM_EOS)]
    assert not body_without_eos.endswith(_ARROW_IPC_STREAM_EOS)
    with pytest.raises(ValueError, match="missing EOS"):
        decode_arrow_stream(body_without_eos)


def test_assert_arrow_schema_matches_rejects_type_drift() -> None:
    columns = (ExpectedColumn(name="id", sql_type="BIGINT", nullable=False),)
    actual_schema = pa.schema([pa.field("id", pa.int32(), nullable=False)])
    with pytest.raises(AssertionError, match="type mismatch"):
        assert_arrow_schema_matches(actual_schema, columns)


def test_decode_arrow_stream_preserves_order_independent_rows() -> None:
    columns = (
        ExpectedColumn(name="id", sql_type="BIGINT", nullable=False),
        ExpectedColumn(name="label", sql_type="VARCHAR(8)", nullable=False),
    )
    schema = expected_arrow_schema(columns)
    table = pa.Table.from_pydict({"id": [2, 1], "label": ["b", "a"]}, schema=schema)
    decoded = decode_arrow_stream(_encode_arrow_stream(table))
    expected = ExpectedTableRows(
        primary_key=("id",),
        records=(
            {"id": 1, "label": "a"},
            {"id": 2, "label": "b"},
        ),
    )
    assert_arrow_schema_matches(decoded.schema, columns)
    assert_rows_match(list(decoded.rows), expected, table_name="items")


def test_assert_arrow_schema_matches_rejects_schema_level_metadata_drift() -> None:
    columns = (ExpectedColumn(name="id", sql_type="BIGINT", nullable=False),)
    actual_schema = pa.schema(
        [pa.field("id", pa.int64(), nullable=False)],
        metadata={b"gateway.fixture": b"drift"},
    )
    with pytest.raises(AssertionError, match="schema-level metadata mismatch"):
        assert_arrow_schema_matches(actual_schema, columns)


def test_decode_arrow_stream_rejects_trailing_garbage_after_eos() -> None:
    table = pa.table({"id": [1]})
    valid = _encode_arrow_stream(table)
    malformed = valid + b"garbage" + _ARROW_IPC_STREAM_EOS
    with pytest.raises(ValueError, match="unconsumed trailing bytes"):
        decode_arrow_stream(malformed)


def test_decode_arrow_stream_rejects_concatenated_streams() -> None:
    table_a = pa.table({"id": [1]})
    table_b = pa.table({"id": [2]})
    concatenated = _encode_arrow_stream(table_a) + _encode_arrow_stream(table_b)
    with pytest.raises(ValueError, match="unconsumed trailing bytes"):
        decode_arrow_stream(concatenated)


def test_versioned_fixture_consumer_client_protocol_rejects_invalid_calls(tmp_path: Path) -> None:
    from mypy import api

    client_tests = Path(__file__).resolve().parent
    probe_dir = tmp_path / "mypy_probe"
    probe_dir.mkdir()
    (probe_dir / "negative.py").write_text(
        "from support.versioned_fixture_consumer import VersionedFixtureConsumerClient\n"
        "def _probe(client: VersionedFixtureConsumerClient) -> None:\n"
        "    client.no_such_method()\n",
        encoding="utf-8",
    )
    (probe_dir / "mypy.ini").write_text(
        f"[mypy]\npython_version = 3.14\nstrict = True\nmypy_path = {client_tests}\n",
        encoding="utf-8",
    )
    stdout, stderr, exit_status = api.run(
        ["--config-file", str(probe_dir / "mypy.ini"), str(probe_dir / "negative.py")]
    )
    assert exit_status != 0
    assert "no_such_method" in stdout + stderr


def test_consumer_summary_json_contains_only_allowed_keys() -> None:
    summary = ConsumerSummary(
        status="ok",
        repository_id=UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11"),
        c0="commit-c0",
        c1="commit-c1",
        c2="commit-c2",
        main_commit="commit-c2",
    )
    payload = json.loads(summary.to_json())
    assert set(payload) == {"status", "repository_id", "c0", "c1", "c2", "main_commit"}
    assert "\n" not in summary.to_json()


def test_sanitize_error_message_redacts_bearer_token() -> None:
    token = "compose-e2e-bearer-token"
    rendered = _sanitize_error_message(f"unauthorized token={token}", token)
    assert token not in rendered
    assert "<redacted>" in rendered


def test_client_failure_summary_for_401_is_typed_unauthorized() -> None:
    from gateway_repository_client.errors import RepositoryClientError
    from gateway_repository_contracts import SimpleError

    exc = RepositoryClientError(
        status_code=401,
        error=SimpleError(code="UNAUTHENTICATED", message="missing or invalid bearer token"),
    )
    assert str(exc) == "missing or invalid bearer token"
    assert "status_code=401" not in str(exc)
    assert client_failure_summary(exc) == {"http_status": 401, "status": "unauthorized"}
    assert client_failure_summary(RuntimeError("connection refused")) == {"status": "failed"}


def test_emit_client_failure_writes_typed_stdout_and_message_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from gateway_repository_client.errors import RepositoryClientError
    from gateway_repository_contracts import SimpleError

    from support.versioned_fixture_consumer import emit_client_failure

    exc = RepositoryClientError(
        status_code=401,
        error=SimpleError(code="UNAUTHENTICATED", message="missing or invalid bearer token"),
    )
    emit_client_failure(exc, "")
    captured = capsys.readouterr()
    assert captured.err == "missing or invalid bearer token\n"
    assert "status_code=401" not in captured.err
    assert captured.out == '{"http_status":401,"status":"unauthorized"}'
