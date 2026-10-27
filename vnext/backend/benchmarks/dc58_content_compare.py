"""Compare saved S1a t1 evidence by logical role without exposing table values.

The report contains paths, counts, durations, and content hashes only.  It is a
one-off evidence tool: it reads saved backend artifacts/control databases and
uses the live Repository Service read API for exported table rows.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc
import pyarrow.parquet as pq


DIGEST_FIELDS = frozenset(
    {
        "artifact_content_digest",
        "before_entry_set_digest",
        "before_ordered_digest",
        "before_snapshot_digest",
        "baseline_canonical_state_digest",
        "bundle_digest",
        "bundle_manifest_digest",
        "business_schema_digest",
        "canonical_business_digest",
        "canonical_schema_digest",
        "canonical_state_digest",
        "canonical_table_set_closure_digest",
        "canonicalization_manifest_digest",
        "closure_manifest_digest",
        "compare_schema_digest",
        "composite_logic_source_digest",
        "comparison_digest",
        "content_digest",
        "current_entry_set_digest",
        "current_ordered_digest",
        "current_snapshot_digest",
        "facts_core_digest",
        "fast_row_digest",
        "identity_assessment_set_digest",
        "initial_canonicalization_manifest_digest",
        "input_canonicalization_manifest_digest",
        "input_digest",
        "manifest_digest",
        "modified_canonical_state_digest",
        "ordering_digest",
        "package_raw_sha256",
        "policy_digest",
        "project_identity_assessment_digest",
        "projection_logical_digest",
        "projection_schema_digest",
        "raw_content_digest",
        "raw_sha256",
        "raw_state_digest",
        "records_content_digest",
        "records_manifest_digest",
        "repository_import_artifact_raw_sha256",
        "request_fingerprint",
        "risk_digest",
        "risk_evaluation_digest",
        "ruleset_digest",
        "sha256",
        "sql_source_digest",
        "snapshot_digest",
        "source_artifact_digest",
        "source_digest",
        "source_schema_digest",
        "storage_projection_ruleset_digest",
        "storage_rule_digest",
        "surface_digest",
    }
)

# A few documents store digest values in a map instead of a *_digest field.
DIGEST_MAP_FIELDS = frozenset({"source_digests"})

# These are the runtime identities present in the S1a DTO/artifact formats.
# Deliberately absent are business_project_id, gateway_device_external_key,
# table_id, annotation_id, and rule_id; those remain ordinary compared data.
RUNTIME_ID_FIELDS = frozenset(
    {
        "acceptance_id",
        "artifact_id",
        "attempt_id",
        "baseline_node_id",
        "business_baseline_node_id",
        "bundle_artifact_id",
        "commit_id",
        "current_preview_result_id",
        "current_upload_revision_id",
        "initial_commit_id",
        "node_id",
        "operation_id",
        "pair_id",
        "preview_result_id",
        "ready_closure_artifact_id",
        "ref_id",
        "repository_commit_id",
        "repository_expected_commit_id",
        "repository_id",
        "request_artifact_id",
        "resolved_commit_hash",
        "snapshot_id",
        "submit_attempt_id",
        "submission_id",
        "surface_id",
        "upload_revision_id",
        "view_id",
        "workspace_id",
    }
)

TIME_FIELDS = frozenset(
    {
        "accepted_at",
        "accepted_at_us",
        "archived_at",
        "archived_at_us",
        "completed_at",
        "completed_at_us",
        "created_at",
        "created_at_us",
        "duration_ms",
        "duration_seconds",
        "elapsed_ms",
        "elapsed_seconds",
        "finished_at",
        "finished_at_us",
        "occurred_at_us",
        "started_at",
        "started_at_us",
        "thread_cpu_seconds",
        "timestamp",
        "updated_at",
        "updated_at_us",
        "wall_seconds",
    }
)

PATH_FIELDS = frozenset({"logical_path"})
_RUN_PATH = re.compile(r"op-[0-9a-f]{12,}(?=[/-])", re.IGNORECASE)
_SUSPICIOUS_DIGEST_KEY = re.compile(r"(?:_digest|_sha256|_hash)$", re.IGNORECASE)
_SUSPICIOUS_TIME_KEY = re.compile(
    r"(?:_at|_at_us|_duration|_elapsed|_wall_seconds|_thread_cpu_seconds)$",
    re.IGNORECASE,
)
_OMIT = object()


APPROVED_GOLDEN_CHANGES: dict[str, str] = {
    "mutation/renderer/capability-failures/source-literal-anomaly/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/destructive-delete/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/first-load-insert/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/mixed-scalars/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/multi-table-patch/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/patch-single-update/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/rebuild-replace-rows/closure.json": "max_patch_change_ratio -> 1% (DC57)",
    "mutation/renderer/valid/destructive-delete/expected.sql": "batched DELETE rendering (DC57)",
    "mutation/renderer/valid/mixed-scalars/expected.sql": "batched DELETE rendering (DC57)",
    "mutation/renderer/valid/multi-table-patch/expected.sql": "batched CASE UPDATE rendering (DC57)",
    "mutation/renderer/valid/patch-single-update/expected.sql": "batched CASE UPDATE rendering (DC57)",
    "mutation/renderer/valid/rebuild-replace-rows/expected.sql": "batched DELETE rendering (DC57)",
    "storage-projection/manifest/valid/s5-durable-roundtrip/document.json": "storage projection 3 / Contract 3.3.0 (§4.1)",
    "storage-projection/ruleset/malformed/s1-duplicate-selector/document.json": "storage projection 3 (§4.1)",
    "storage-projection/ruleset/valid/s1-net-cfg/document.json": "storage projection 3 (§4.1)",
    "storage-projection/ruleset/valid/s2-migrated-matrix/document.json": "storage projection 3 (§4.1)",
}


@dataclass(frozen=True, slots=True)
class Run:
    label: str
    state_path: Path
    artifacts: Path
    control_db: Path
    project: str
    run_root: Path
    golden: Path
    state: dict[str, Any]


def _record_path(paths: set[str], path: str) -> None:
    paths.add(re.sub(r"\[\d+\]", "[*]", path))


def _is_reference_artifact_id(path: str) -> bool:
    parent_path = path.rsplit(".", 1)[0]
    parent_parts = parent_path.split(".")
    parent_name = parent_parts[-1].split("[", 1)[0]
    if parent_name == "artifact_ref" or parent_name.endswith("_ref") or parent_name in {
        "required_refs",
        "refs",
        "row_file_refs",
    }:
        return True
    return len(parent_parts) >= 2 and parent_parts[-2] == "source_artifacts"


def normalize_json(value: Any, *, path: str, masked_paths: set[str]) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = f"{path}.{key}"
            if (
                _SUSPICIOUS_DIGEST_KEY.search(key)
                and key not in DIGEST_FIELDS
                and key not in RUNTIME_ID_FIELDS
            ):
                raise ValueError(f"unlisted digest field path: {item_path}")
            if _SUSPICIOUS_TIME_KEY.search(key) and key not in TIME_FIELDS:
                raise ValueError(f"unlisted time field path: {item_path}")
            if key in DIGEST_FIELDS or key in DIGEST_MAP_FIELDS:
                _record_path(masked_paths, item_path)
                continue
            if key in RUNTIME_ID_FIELDS and (
                key != "artifact_id" or _is_reference_artifact_id(item_path)
            ):
                _record_path(masked_paths, item_path)
                continue
            if key in TIME_FIELDS:
                _record_path(masked_paths, item_path)
                continue
            normalized_item = normalize_json(
                item,
                path=item_path,
                masked_paths=masked_paths,
            )
            if normalized_item is not _OMIT:
                normalized[key] = normalized_item
        for list_key in ("closure_entries", "entries"):
            entries = normalized.get(list_key)
            if isinstance(entries, list) and all(isinstance(item, dict) for item in entries):
                if any("logical_path" in item for item in entries):
                    entries.sort(
                        key=lambda item: (
                            str(item.get("logical_path", "")),
                            str(item.get("kind", "")),
                            str(item.get("table_name") or ""),
                            bool(item.get("shared", False)),
                        )
                    )
        return normalized
    if isinstance(value, list):
        result: list[Any] = []
        for index, item in enumerate(value):
            normalized = normalize_json(
                item,
                path=f"{path}[{index}]",
                masked_paths=masked_paths,
            )
            if normalized is not _OMIT:
                result.append(normalized)
        return result
    if isinstance(value, str) and path.rsplit(".", 1)[-1] in PATH_FIELDS:
        normalized_path = _RUN_PATH.sub("<OPERATION>", value)
        if normalized_path != value:
            _record_path(masked_paths, path)
        return normalized_path
    return value


def changed_paths(left: Any, right: Any, prefix: str = "$", limit: int = 100) -> list[str]:
    out: list[str] = []
    if type(left) is not type(right):
        return [prefix]
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}"
            if key not in left or key not in right:
                out.append(child)
            else:
                out.extend(changed_paths(left[key], right[key], child, limit))
            if len(out) >= limit:
                return out[:limit]
    elif isinstance(left, list):
        if len(left) != len(right):
            out.append(f"{prefix}.length")
        for index, (before, current) in enumerate(zip(left, right)):
            out.extend(changed_paths(before, current, f"{prefix}[{index}]", limit))
            if len(out) >= limit:
                return out[:limit]
    elif left != right:
        out.append(prefix)
    return out[:limit]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def artifact_path(root: Path, artifact_id: str) -> Path:
    hashed = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
    return root / hashed[:2] / hashed[2:4] / hashed


def read_ref_bytes(root: Path, ref: dict[str, Any]) -> bytes:
    artifact_id = ref.get("artifact_id")
    if not isinstance(artifact_id, str):
        raise ValueError("artifact reference has no artifact_id")
    payload_path = artifact_path(root, artifact_id)
    payload = payload_path.read_bytes()
    expected_size = ref.get("size_bytes")
    if type(expected_size) is int and expected_size != len(payload):
        raise ValueError("artifact payload size does not match its reference")
    expected_sha = ref.get("raw_sha256")
    if isinstance(expected_sha, str):
        normalized_sha = expected_sha.removeprefix("sha256:")
        if hashlib.sha256(payload).hexdigest() != normalized_sha:
            raise ValueError("artifact payload hash does not match its reference")
    return payload


def read_ref_json(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(read_ref_bytes(root, ref))
    if not isinstance(value, dict):
        raise ValueError("referenced JSON artifact is not an object")
    return value


def canonical_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, time):
        return {"$time": value.isoformat()}
    if isinstance(value, float):
        return {"$float_hex": value.hex()}
    if isinstance(value, dict):
        return {str(key): canonical_cell(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical_cell(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported cell type: {type(value).__name__}")


def arrow_content_summary(table: pa.Table) -> dict[str, Any]:
    schema = [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in table.schema
    ]
    schema_bytes = canonical_json(schema)
    encoded_rows = [
        canonical_json([canonical_cell(row.get(field.name)) for field in table.schema])
        for row in table.to_pylist()
    ]
    encoded_rows.sort()
    digest = hashlib.sha256()
    digest.update(len(schema_bytes).to_bytes(8, "big"))
    digest.update(schema_bytes)
    for row in encoded_rows:
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
    return {
        "row_count": table.num_rows,
        "column_count": table.num_columns,
        "schema": schema,
        "content_sha256": digest.hexdigest(),
    }


def parquet_content_summary(payloads: list[bytes]) -> dict[str, Any]:
    tables = [pq.read_table(pa.BufferReader(payload)) for payload in payloads]
    if not tables:
        return {"row_count": 0, "column_count": 0, "schema": [], "content_sha256": hashlib.sha256(b"").hexdigest()}
    combined = pa.concat_tables(tables, promote_options="none") if len(tables) > 1 else tables[0]
    return arrow_content_summary(combined)


def snapshot_table_summary(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    document = read_ref_json(root, ref)
    descriptor = document.get("descriptor")
    row_refs = document.get("row_file_refs")
    if not isinstance(descriptor, dict) or not isinstance(row_refs, list):
        raise ValueError("snapshot table artifact is missing its descriptor or row references")
    selected = {key: value for key, value in document.items() if key != "row_file_refs"}
    paths: set[str] = set()
    normalized = normalize_json(selected, path="$snapshot_table", masked_paths=paths)
    payloads = [
        read_ref_bytes(root, cast(dict[str, Any], row_ref))
        for row_ref in row_refs
        if isinstance(row_ref, dict)
    ]
    return {
        "document": normalized,
        "raw_content_digest": descriptor.get("raw_content_digest"),
        "row_content": parquet_content_summary(payloads),
        "mask_paths": sorted(paths),
    }


def _json_from_db(value: Any) -> Any:
    if isinstance(value, bytes):
        return json.loads(value.decode("utf-8"))
    if isinstance(value, str):
        return json.loads(value)
    return value


def _state_operation_roles(state: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for role in ("v1-preview", "v2-preview", "repeat-v1-preview"):
        result = state.get(role, {}).get("preview", {}).get("result", {})
        operation_id = result.get("operation_id") if isinstance(result, dict) else None
        if isinstance(operation_id, str):
            roles[operation_id] = role
    history = state.get("history", {})
    history_id = history.get("operation_id") if isinstance(history, dict) else None
    if isinstance(history_id, str):
        roles[history_id] = "history"
    return roles


def _submit_operation_roles(run: Run) -> dict[str, str]:
    preview_ids: dict[str, str] = {}
    for role in ("v1", "v2"):
        result = run.state.get(f"{role}-preview", {}).get("preview", {}).get("result", {})
        preview_id = result.get("preview_result_id") if isinstance(result, dict) else None
        if isinstance(preview_id, str):
            preview_ids[preview_id] = role
    connection = sqlite3.connect(f"file:{run.control_db}?mode=ro", uri=True)
    try:
        operations = connection.execute(
            "SELECT operation_id, job_payload FROM operation_records "
            "WHERE job_kind = ? ORDER BY created_at_us",
            ("backend-vnext/submit",),
        ).fetchall()
    finally:
        connection.close()
    result: dict[str, str] = {}
    for operation_id, payload in operations:
        document = _json_from_db(payload)
        preview_id = document.get("preview_result_id") if isinstance(document, dict) else None
        role = preview_ids.get(preview_id) if isinstance(preview_id, str) else None
        if role is not None:
            result[str(operation_id)] = role
    return result


def _side_label(
    run: Run,
    operation_role: str,
    raw_label: str,
    document: dict[str, Any],
) -> str:
    if raw_label in {"BASELINE", "INITIAL", "MODIFIED"}:
        return raw_label
    if operation_role == "history":
        for submit_role in ("v1", "v2"):
            submit = run.state.get(f"{submit_role}-submit", {})
            if isinstance(submit, dict) and submit.get("repository_commit_id") == raw_label:
                return f"repository-{submit_role}"
    identity = document.get("repository_identity")
    resolved_commit = identity.get("resolved_commit_hash") if isinstance(identity, dict) else None
    for submit_role in ("v1", "v2"):
        submit = run.state.get(f"{submit_role}-submit", {})
        if isinstance(submit, dict) and submit.get("repository_commit_id") == resolved_commit:
            return f"repository-{submit_role}"
    if operation_role == "history":
        return "history-unmatched-repository-side"
    return raw_label


def snapshot_descriptions(run: Run, masked_paths: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
    operation_roles = _state_operation_roles(run.state)
    connection = sqlite3.connect(f"file:{run.control_db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    result: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        rows = connection.execute(
            "SELECT operation_id, step_name, checkpoint_ref FROM step_records "
            "WHERE step_name = ? ORDER BY created_at_us",
            ("materialize_inputs",),
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        operation_role = operation_roles.get(str(row["operation_id"]))
        if operation_role is None:
            raise ValueError("materialize_inputs operation has no saved journey role")
        checkpoint_ref = _json_from_db(row["checkpoint_ref"])
        checkpoint = read_ref_json(run.artifacts, checkpoint_ref)
        job_state = checkpoint.get("job_state")
        if not isinstance(job_state, dict):
            raise ValueError("materialize_inputs checkpoint has no job state")
        sides_ref = job_state.get("materialized_sides_ref")
        if not isinstance(sides_ref, dict):
            raise ValueError("materialize_inputs checkpoint has no materialized-sides reference")
        sides_doc = read_ref_json(run.artifacts, sides_ref)
        sides = sides_doc.get("sides")
        if not isinstance(sides, dict):
            raise ValueError("materialized-sides artifact has no sides")
        for raw_label, side in sides.items():
            if not isinstance(side, dict):
                continue
            label = _side_label(run, operation_role, str(raw_label), side)
            key = (operation_role, label)
            if key in result:
                raise ValueError(f"duplicate materialized side role: {key}")
            summary = side.get("summary")
            tables = summary.get("tables") if isinstance(summary, dict) else None
            if not isinstance(tables, list):
                raise ValueError("materialized side summary has no table descriptors")
            descriptors: dict[str, Any] = {}
            descriptor_bindings: dict[str, dict[str, Any]] = {}
            for descriptor in tables:
                if not isinstance(descriptor, dict) or not isinstance(descriptor.get("table_name"), str):
                    raise ValueError("materialized side has a malformed table descriptor")
                name = str(descriptor["table_name"])
                normalized = normalize_json(
                    descriptor,
                    path=f"$snapshot[{operation_role}][{label}].tables[{name}]",
                    masked_paths=masked_paths,
                )
                descriptors[name] = normalized
                descriptor_bindings[name] = {
                    "row_count": descriptor.get("row_count"),
                    "raw_content_digest": descriptor.get("raw_content_digest"),
                }
            storage_facts = side.get("storage_facts", [])
            normalized_facts = normalize_json(
                storage_facts,
                path=f"$snapshot[{operation_role}][{label}].storage_facts",
                masked_paths=masked_paths,
            )
            snapshot = normalize_json(
                side.get("snapshot", {}),
                path=f"$snapshot[{operation_role}][{label}].snapshot",
                masked_paths=masked_paths,
            )
            table_entries: dict[str, Any] = {}
            raw_entries = side.get("tables", [])
            if isinstance(raw_entries, list):
                for entry in raw_entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("table_name"), str):
                        continue
                    name = str(entry["table_name"])
                    manifest_ref = entry.get("manifest_ref")
                    if not isinstance(manifest_ref, dict):
                        raise ValueError("canonical table entry has no manifest reference")
                    table_entries[name] = snapshot_table_summary(run.artifacts, manifest_ref)
                    masked_paths.update(
                        f"$snapshot[{operation_role}][{label}].tables[{name}].{path.removeprefix('$snapshot.')}"
                        for path in table_entries[name]["mask_paths"]
                    )
            result[key] = {
                "summary": normalize_json(
                    {key: value for key, value in summary.items() if key != "tables"}
                    if isinstance(summary, dict)
                    else {},
                    path=f"$snapshot[{operation_role}][{label}].summary",
                    masked_paths=masked_paths,
                ),
                "snapshot": snapshot,
                "storage_facts": normalized_facts,
                "descriptors": descriptors,
                "descriptor_bindings": descriptor_bindings,
                "table_artifacts": table_entries,
                "table_count": len(descriptors),
                "rowless_nonempty_descriptors": sorted(
                    name
                    for name, descriptor in descriptors.items()
                    if isinstance(descriptor, dict)
                    and int(descriptor.get("row_count", 0)) > 0
                    and name not in table_entries
                ),
            }
    return result


def compare_snapshot_descriptions(
    base: Run,
    candidate: Run,
    masked_paths: set[str],
) -> dict[str, Any]:
    left = snapshot_descriptions(base, masked_paths)
    right = snapshot_descriptions(candidate, masked_paths)
    canonical = {
        base.label: canonical_submit_tables(base, set()),
        candidate.label: canonical_submit_tables(candidate, set()),
    }
    differences: list[dict[str, Any]] = []
    descriptor_count = 0
    shared_table_payload_count = 0
    rowless_resolution: list[dict[str, Any]] = []
    for role in sorted(set(left) | set(right)):
        if role not in left or role not in right:
            differences.append({"role": list(role), "reason": "missing-side"})
            continue
        lside, rside = left[role], right[role]
        if lside["summary"] != rside["summary"]:
            differences.append(
                {
                    "role": list(role),
                    "reason": "summary",
                    "fields": changed_paths(lside["summary"], rside["summary"]),
                }
            )
        if lside["snapshot"] != rside["snapshot"]:
            differences.append(
                {
                    "role": list(role),
                    "reason": "snapshot-metadata",
                    "fields": changed_paths(lside["snapshot"], rside["snapshot"]),
                }
            )
        if lside["storage_facts"] != rside["storage_facts"]:
            differences.append(
                {
                    "role": list(role),
                    "reason": "storage-facts",
                    "fields": changed_paths(lside["storage_facts"], rside["storage_facts"]),
                }
            )
        if set(lside["descriptors"]) != set(rside["descriptors"]):
            differences.append({"role": list(role), "reason": "descriptor-table-set"})
        for table_name in sorted(set(lside["descriptors"]) & set(rside["descriptors"])):
            descriptor_count += 1
            if lside["descriptors"][table_name] != rside["descriptors"][table_name]:
                differences.append(
                    {
                        "role": list(role),
                        "table_name": table_name,
                        "reason": "descriptor",
                        "fields": changed_paths(
                            lside["descriptors"][table_name],
                            rside["descriptors"][table_name],
                        ),
                    }
                )
        left_payloads = lside["table_artifacts"]
        right_payloads = rside["table_artifacts"]
        for table_name in sorted(set(left_payloads) & set(right_payloads)):
            shared_table_payload_count += 1
            if left_payloads[table_name]["document"] != right_payloads[table_name]["document"]:
                differences.append(
                    {
                        "role": list(role),
                        "table_name": table_name,
                        "reason": "table-artifact-descriptor",
                        "fields": changed_paths(
                            left_payloads[table_name]["document"],
                            right_payloads[table_name]["document"],
                        ),
                    }
                )
            if left_payloads[table_name]["row_content"] != right_payloads[table_name]["row_content"]:
                differences.append(
                    {"role": list(role), "table_name": table_name, "reason": "table-artifact-rows"}
                )
        carrier_role = _canonical_carrier_role(role[0], role[1])
        for run, side in ((base, lside), (candidate, rside)):
            run_canonical = canonical[run.label]
            for table_name, binding in side["descriptor_bindings"].items():
                row_count = binding.get("row_count")
                if type(row_count) is not int or row_count == 0:
                    continue
                if carrier_role is None:
                    differences.append(
                        {
                            "role": list(role),
                            "table_name": table_name,
                            "reason": "nonempty-descriptor-has-no-content-carrier",
                        }
                    )
                    continue
                canonical_role = run_canonical.get(carrier_role)
                canonical_table = (
                    canonical_role.get("tables", {}).get(table_name)
                    if isinstance(canonical_role, dict)
                    else None
                )
                if not isinstance(canonical_table, dict):
                    differences.append(
                        {
                            "role": list(role),
                            "table_name": table_name,
                            "reason": "canonical-content-carrier-missing",
                        }
                    )
                    continue
                if binding.get("raw_content_digest") != canonical_table.get("raw_content_digest"):
                    differences.append(
                        {
                            "role": list(role),
                            "table_name": table_name,
                            "reason": "descriptor-carrier-binding",
                        }
                    )
                snapshot_payload = side["table_artifacts"].get(table_name)
                if snapshot_payload is None:
                    rowless_resolution.append(
                        {
                            "logical_role": list(role),
                            "table_name": table_name,
                            "content_carrier": f"{carrier_role} canonical table artifact and Repository export",
                        }
                    )
                elif snapshot_payload["row_content"] != canonical_table["row_content"]:
                    differences.append(
                        {
                            "role": list(role),
                            "table_name": table_name,
                            "reason": "snapshot-table-content-differs-from-canonical-carrier",
                        }
                    )
    return {
        "base_logical_roles": len(left),
        "candidate_logical_roles": len(right),
        "descriptors_compared": descriptor_count,
        "table_artifact_payloads_compared": shared_table_payload_count,
        "rowless_nonempty_descriptors_resolved": len(rowless_resolution),
        "rowless_content_carriers": rowless_resolution[:300],
        "equal_after_mask": not differences,
        "difference_count": len(differences),
        "differences": differences[:100],
        "missing_row_artifact_policy": "rowless side descriptors are compared directly; canonical table-set artifacts and Repository exports are compared separately by v1/v2 table role",
    }


def _canonical_carrier_role(operation_role: str, side_role: str) -> str | None:
    if operation_role in {"v1-preview", "repeat-v1-preview"}:
        return "v1" if side_role == "MODIFIED" else None
    if operation_role == "v2-preview":
        if side_role == "MODIFIED":
            return "v2"
        return "v1" if side_role == "BASELINE" else None
    if operation_role == "history":
        if side_role == "repository-v1":
            return "v1"
        if side_role == "repository-v2":
            return "v2"
    return None


def canonical_submit_tables(run: Run, masked_paths: set[str]) -> dict[str, dict[str, Any]]:
    submit_roles = _submit_operation_roles(run)
    connection = sqlite3.connect(f"file:{run.control_db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    result: dict[str, dict[str, Any]] = {}
    try:
        rows = connection.execute(
            "SELECT operation_id, checkpoint_ref FROM step_records "
            "WHERE step_name = ? ORDER BY created_at_us",
            ("prepare_import",),
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        role = submit_roles.get(str(row["operation_id"]))
        if role is None:
            raise ValueError("prepare_import operation has no saved v1/v2 role")
        checkpoint_ref = _json_from_db(row["checkpoint_ref"])
        checkpoint = read_ref_json(run.artifacts, checkpoint_ref)
        job_state = checkpoint.get("job_state")
        if not isinstance(job_state, dict):
            raise ValueError("prepare_import checkpoint has no job state")
        closure_id = job_state.get("canonical_table_set_closure_ref")
        if not isinstance(closure_id, str):
            raise ValueError("prepare_import checkpoint has no canonical table-set closure reference")
        closure = read_ref_json(run.artifacts, {"artifact_id": closure_id})
        entries = closure.get("tables")
        if not isinstance(entries, list):
            raise ValueError("canonical table-set closure has no table entries")
        tables: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("table_name"), str):
                raise ValueError("canonical table-set closure has a malformed entry")
            name = str(entry["table_name"])
            ref = entry.get("manifest_ref")
            if not isinstance(ref, dict):
                raise ValueError("canonical table-set entry has no manifest reference")
            tables[name] = snapshot_table_summary(run.artifacts, ref)
            masked_paths.update(
                f"$canonical[{role}][{name}].{path.removeprefix('$snapshot.')}"
                for path in tables[name]["mask_paths"]
            )
        if role in result:
            raise ValueError(f"duplicate canonical table-set role: {role}")
        manifest_ref = job_state.get("canonicalization_manifest_ref")
        if not isinstance(manifest_ref, dict):
            raise ValueError("prepare_import checkpoint has no canonicalization manifest reference")
        manifest = read_ref_json(run.artifacts, manifest_ref)
        manifest_tables = manifest.get("tables")
        if not isinstance(manifest_tables, list):
            raise ValueError("canonicalization manifest has no table list")
        normalized_manifest_tables: dict[str, Any] = {}
        for table in manifest_tables:
            if not isinstance(table, dict) or not isinstance(table.get("name"), str):
                raise ValueError("canonicalization manifest contains a malformed table")
            table_name = str(table["name"])
            normalized_manifest_tables[table_name] = normalize_json(
                table,
                path=f"$canonical_manifest[{role}].tables[{table_name}]",
                masked_paths=masked_paths,
            )
        result[role] = {
            "tables": tables,
            "manifest": {
                "contract_version": manifest.get("contract_version"),
                "storage_projection_version": manifest.get("storage_projection_version"),
                "ruleset_id": manifest.get("ruleset_id"),
                "ruleset_version": manifest.get("ruleset_version"),
                "tables": normalized_manifest_tables,
            },
        }
    return result


def compare_canonical_tables(
    base: Run,
    candidate: Run,
    masked_paths: set[str],
) -> dict[str, Any]:
    left = canonical_submit_tables(base, masked_paths)
    right = canonical_submit_tables(candidate, masked_paths)
    differences: list[dict[str, Any]] = []
    compared = 0
    approved_version_changes: list[dict[str, Any]] = []
    for role in sorted(set(left) | set(right)):
        if role not in left or role not in right:
            differences.append({"role": role, "reason": "missing-submit-role"})
            continue
        if set(left[role]["tables"]) != set(right[role]["tables"]):
            differences.append({"role": role, "reason": "table-set"})
        left_manifest = left[role]["manifest"]
        right_manifest = right[role]["manifest"]
        manifest_diffs: dict[str, Any] = {}
        for field_name in ("contract_version", "storage_projection_version"):
            if left_manifest[field_name] != right_manifest[field_name]:
                manifest_diffs[field_name] = {
                    "baseline": left_manifest[field_name],
                    "candidate": right_manifest[field_name],
                }
        if manifest_diffs:
            approved_version_changes.append({"role": role, "fields": manifest_diffs})
        for field_name in ("ruleset_id", "ruleset_version"):
            if left_manifest[field_name] != right_manifest[field_name]:
                differences.append(
                    {"role": role, "reason": "manifest-policy", "field": field_name}
                )
        if set(left_manifest["tables"]) != set(right_manifest["tables"]):
            differences.append({"role": role, "reason": "manifest-table-set"})
        for table_name in sorted(set(left_manifest["tables"]) & set(right_manifest["tables"])):
            if left_manifest["tables"][table_name] != right_manifest["tables"][table_name]:
                differences.append(
                    {
                        "role": role,
                        "table_name": table_name,
                        "reason": "canonicalization-table-metadata",
                        "fields": changed_paths(
                            left_manifest["tables"][table_name],
                            right_manifest["tables"][table_name],
                        ),
                    }
                )
        for table_name in sorted(set(left[role]["tables"]) & set(right[role]["tables"])):
            compared += 1
            ltable, rtable = left[role]["tables"][table_name], right[role]["tables"][table_name]
            if ltable["document"] != rtable["document"]:
                differences.append(
                    {
                        "role": role,
                        "table_name": table_name,
                        "reason": "descriptor",
                        "fields": changed_paths(ltable["document"], rtable["document"]),
                    }
                )
            if ltable["row_content"] != rtable["row_content"]:
                differences.append(
                    {"role": role, "table_name": table_name, "reason": "rows"}
                )
    return {
        "base_roles": sorted(left),
        "candidate_roles": sorted(right),
        "approved_manifest_version_changes": approved_version_changes,
        "tables_compared": compared,
        "equal_after_mask": not differences,
        "difference_count": len(differences),
        "differences": differences[:100],
    }


def _repository_ip(project: str) -> str:
    container = f"{project}-repository-service-1"
    completed = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    address = completed.stdout.strip()
    if completed.returncode != 0 or not address:
        raise RuntimeError(f"Repository Service container is not running for project {project}")
    return address


def repository_export_tables(run: Run, state_role: str) -> dict[str, Any]:
    submission = run.state.get(f"{state_role}-submit")
    if not isinstance(submission, dict):
        raise ValueError(f"saved state has no {state_role} Submit")
    repository_id = submission.get("repository_id")
    commit_id = submission.get("repository_commit_id")
    if not isinstance(repository_id, str) or not isinstance(commit_id, str):
        raise ValueError(f"saved state has no {state_role} Repository binding")
    token_path = run.run_root / "t1-secrets" / "repository-bearer-token"
    token = token_path.read_text(encoding="utf-8").strip()
    client = httpx.Client(
        base_url=f"http://{_repository_ip(run.project)}:8000",
        headers={"Authorization": f"Bearer {token}"},
        timeout=300.0,
    )
    try:
        encoded_commit = quote(commit_id, safe="")
        catalog_response = client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded_commit}/catalog"
        )
        if catalog_response.status_code != 200:
            raise RuntimeError(
                f"Repository catalog read failed for {state_role}: HTTP {catalog_response.status_code}"
            )
        catalog = catalog_response.json()
        catalog_doc = catalog.get("catalog") if isinstance(catalog, dict) else None
        catalog_tables = catalog_doc.get("tables") if isinstance(catalog_doc, dict) else None
        if not isinstance(catalog_tables, list):
            raise ValueError("Repository Catalog response has no table list")
        tables: dict[str, Any] = {}
        for descriptor in catalog_tables:
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("name"), str):
                raise ValueError("Repository Catalog contains a malformed table descriptor")
            table_name = str(descriptor["name"])
            response = client.get(
                f"/v1/repositories/{repository_id}/versioned/commits/{encoded_commit}/rows",
                params={"table_name": table_name},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Repository row export failed for table {table_name}: HTTP {response.status_code}"
                )
            try:
                arrow_table = pa_ipc.open_stream(response.content).read_all()
            except (pa.ArrowInvalid, ValueError, TypeError) as error:
                raise ValueError(f"Repository Arrow export is invalid for table {table_name}") from error
            expected_rows = descriptor.get("row_count")
            if type(expected_rows) is int and expected_rows != arrow_table.num_rows:
                raise ValueError(f"Repository row count differs from Catalog for {table_name}")
            tables[table_name] = arrow_content_summary(arrow_table)
        return {
            "table_count": len(tables),
            "row_count_total": sum(int(item["row_count"]) for item in tables.values()),
            "tables": tables,
        }
    finally:
        client.close()


def compare_repository_exports(base: Run, candidate: Run) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    differences: list[dict[str, Any]] = []
    for role in ("v1", "v2"):
        left = repository_export_tables(base, role)
        right = repository_export_tables(candidate, role)
        table_differences: list[dict[str, Any]] = []
        for name in sorted(set(left["tables"]) | set(right["tables"])):
            if name not in left["tables"] or name not in right["tables"]:
                table_differences.append({"table_name": name, "reason": "missing-table"})
            elif left["tables"][name] != right["tables"][name]:
                table_differences.append({"table_name": name, "reason": "content-or-schema"})
        equal = not table_differences
        roles[role] = {
            "base_table_count": left["table_count"],
            "candidate_table_count": right["table_count"],
            "base_row_count_total": left["row_count_total"],
            "candidate_row_count_total": right["row_count_total"],
            "tables_equal": equal,
            "difference_count": len(table_differences),
            "differences": table_differences[:100],
        }
        if not equal:
            differences.extend({"role": role, **item} for item in table_differences)
    return {"equal_by_logical_role": not differences, "roles": roles, "differences": differences[:100]}


def role_key(entry: dict[str, Any]) -> tuple[str, str, str, bool]:
    logical_path = str(entry.get("logical_path", ""))
    logical_path = _RUN_PATH.sub("<OPERATION>", logical_path)
    return (
        logical_path,
        str(entry.get("kind", "")),
        str(entry.get("table_name") or ""),
        bool(entry.get("shared", False)),
    )


def bundle_entries(run: Run, selector: tuple[str, ...]) -> list[dict[str, Any]]:
    value: Any = run.state
    for part in selector:
        value = value[part]
    entries = value.get("closure_entries") if isinstance(value, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"bundle selector has no closure entries: {selector}")
    return [item for item in entries if isinstance(item, dict)]


def compare_bundle(
    base: Run,
    candidate: Run,
    selector: tuple[str, ...],
    name: str,
    masked_paths: set[str],
) -> dict[str, Any]:
    indexes: list[dict[tuple[str, str, str, bool], list[tuple[dict[str, Any], bytes]]]] = []
    for run in (base, candidate):
        indexed: dict[tuple[str, str, str, bool], list[tuple[dict[str, Any], bytes]]] = defaultdict(list)
        for entry in bundle_entries(run, selector):
            ref = entry.get("artifact_ref")
            if not isinstance(ref, dict):
                raise ValueError(f"bundle entry has no artifact reference in {name}")
            indexed[role_key(entry)].append((entry, read_ref_bytes(run.artifacts, ref)))
        indexes.append(indexed)
    left, right = indexes
    differences: list[dict[str, Any]] = []
    compared = 0
    unresolved = 0
    role_keys = set(left) | set(right)
    for role in sorted(role_keys):
        if role not in left or role not in right or len(left[role]) != len(right[role]):
            differences.append({"role": list(role[:3]), "reason": "missing-or-multiplicity"})
            continue
        l_items = sorted(left[role], key=lambda item: hashlib.sha256(item[1]).hexdigest())
        r_items = sorted(right[role], key=lambda item: hashlib.sha256(item[1]).hexdigest())
        for (_le, lbytes), (_re, rbytes) in zip(l_items, r_items):
            compared += 1
            try:
                lv, rv = json.loads(lbytes), json.loads(rbytes)
            except (UnicodeDecodeError, json.JSONDecodeError):
                if lbytes != rbytes:
                    differences.append({"role": list(role[:3]), "reason": "binary-content"})
                continue
            lnorm = normalize_json(lv, path=f"$bundle[{name}]", masked_paths=masked_paths)
            rnorm = normalize_json(rv, path=f"$bundle[{name}]", masked_paths=masked_paths)
            if lnorm != rnorm:
                differences.append(
                    {
                        "role": list(role[:3]),
                        "reason": "payload-content",
                        "fields": changed_paths(lnorm, rnorm),
                    }
                )
            for run, value in ((base, lv), (candidate, rv)):
                for ref_id in _nested_artifact_ids(value):
                    if not artifact_path(run.artifacts, ref_id).is_file():
                        unresolved += 1
    return {
        "name": name,
        "base_artifacts": sum(map(len, left.values())),
        "candidate_artifacts": sum(map(len, right.values())),
        "compared_artifacts": compared,
        "unresolved_nested_references": unresolved,
        "equal_after_mask": not differences and unresolved == 0,
        "difference_count": len(differences),
        "differences": differences[:100],
    }


def _nested_artifact_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("artifact_id"), str):
            result.append(str(value["artifact_id"]))
        for item in value.values():
            result.extend(_nested_artifact_ids(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_nested_artifact_ids(item))
    return result


def compare_state(base: Run, candidate: Run, masked_paths: set[str]) -> dict[str, Any]:
    left = {key: value for key, value in base.state.items() if key != "_stack"}
    right = {key: value for key, value in candidate.state.items() if key != "_stack"}
    left_normalized = normalize_json(left, path="$http_dto", masked_paths=masked_paths)
    right_normalized = normalize_json(right, path="$http_dto", masked_paths=masked_paths)
    differences = changed_paths(left_normalized, right_normalized)
    return {"equal_after_mask": not differences, "difference_count": len(differences), "differences": differences}


def compare_golden(base: Run, candidate: Run, masked_paths: set[str]) -> dict[str, Any]:
    left_files = {str(path.relative_to(base.golden)): path for path in base.golden.rglob("*") if path.is_file()}
    right_files = {
        str(path.relative_to(candidate.golden)): path
        for path in candidate.golden.rglob("*")
        if path.is_file()
    }
    changed: list[dict[str, Any]] = []
    equal = 0
    for relative in sorted(set(left_files) | set(right_files)):
        if relative not in left_files or relative not in right_files:
            changed.append({"fixture": relative, "fields": ["$"], "reason": "missing-file"})
            continue
        left_bytes, right_bytes = left_files[relative].read_bytes(), right_files[relative].read_bytes()
        try:
            left_value, right_value = json.loads(left_bytes), json.loads(right_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            if left_bytes == right_bytes:
                equal += 1
            else:
                changed.append({"fixture": relative, "fields": ["$.binary-content"], "reason": "bytes"})
            continue
        lnorm = normalize_json(left_value, path=f"$golden[{relative}]", masked_paths=masked_paths)
        rnorm = normalize_json(right_value, path=f"$golden[{relative}]", masked_paths=masked_paths)
        fields_changed = changed_paths(lnorm, rnorm)
        if not fields_changed:
            equal += 1
        else:
            changed.append({"fixture": relative, "fields": fields_changed})
    unexpected = [item for item in changed if item["fixture"] not in APPROVED_GOLDEN_CHANGES]
    missing_approved = sorted(set(APPROVED_GOLDEN_CHANGES) - {item["fixture"] for item in changed})
    for item in changed:
        item["approved_change"] = APPROVED_GOLDEN_CHANGES.get(item["fixture"])
    return {
        "base_fixture_count": len(left_files),
        "candidate_fixture_count": len(right_files),
        "equal_after_mask_count": equal,
        "approved_difference_count": len(changed) - len(unexpected),
        "approved_changes": changed,
        "unexpected_differences": unexpected,
        "approved_changes_not_present": missing_approved,
        "all_differences_approved": not unexpected and not missing_approved,
    }


def counterexample_checks(masked_paths: set[str]) -> dict[str, Any]:
    business_left = normalize_json(
        {"business_project_id": "project-a"}, path="$counterexample", masked_paths=masked_paths
    )
    business_right = normalize_json(
        {"business_project_id": "project-b"}, path="$counterexample", masked_paths=masked_paths
    )
    hex_left = normalize_json(
        {"value": "a" * 64}, path="$counterexample", masked_paths=masked_paths
    )
    hex_right = normalize_json(
        {"value": "b" * 64}, path="$counterexample", masked_paths=masked_paths
    )
    return {
        "business_project_id_change_detected": business_left != business_right,
        "arbitrary_64_hex_value_change_detected": hex_left != hex_right,
    }


def _load_run(
    label: str,
    state_path: Path,
    artifacts: Path,
    control_db: Path,
    project: str,
    run_root: Path,
    golden: Path,
) -> Run:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError(f"state is not a JSON object: {state_path}")
    return Run(label, state_path, artifacts, control_db, project, run_root, golden, state)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("baseline", "candidate"):
        parser.add_argument(f"--{prefix}-state", type=Path, required=True)
        parser.add_argument(f"--{prefix}-artifacts", type=Path, required=True)
        parser.add_argument(f"--{prefix}-control-db", type=Path, required=True)
        parser.add_argument(f"--{prefix}-project", required=True)
        parser.add_argument(f"--{prefix}-run-root", type=Path, required=True)
        parser.add_argument(f"--{prefix}-golden", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    base = _load_run(
        "baseline",
        arguments.baseline_state,
        arguments.baseline_artifacts,
        arguments.baseline_control_db,
        arguments.baseline_project,
        arguments.baseline_run_root,
        arguments.baseline_golden,
    )
    candidate = _load_run(
        "candidate",
        arguments.candidate_state,
        arguments.candidate_artifacts,
        arguments.candidate_control_db,
        arguments.candidate_project,
        arguments.candidate_run_root,
        arguments.candidate_golden,
    )
    masked_paths: set[str] = set()
    snapshots = compare_snapshot_descriptions(base, candidate, masked_paths)
    canonical_tables = compare_canonical_tables(base, candidate, masked_paths)
    bundles = [
        compare_bundle(base, candidate, ("v1-preview", "manifest"), "v1-preview", masked_paths),
        compare_bundle(base, candidate, ("v2-preview", "manifest"), "v2-preview", masked_paths),
        compare_bundle(base, candidate, ("history", "result", "bundle"), "history", masked_paths),
    ]
    state = compare_state(base, candidate, masked_paths)
    golden = compare_golden(base, candidate, masked_paths)
    exports = compare_repository_exports(base, candidate)
    counterexamples = counterexample_checks(masked_paths)
    report = {
        "baseline_head": base.state.get("_stack", {}).get("head"),
        "candidate_head": candidate.state.get("_stack", {}).get("head"),
        "mask_method": "exact field-name allowlists; no arbitrary suffix-ID masking and no digest-shaped-value masking; logical_path normalizes only embedded operation tokens; content-addressed artifact refs are dereferenced",
        "masked_field_keys": {
            "digest_hash_fields": sorted(DIGEST_FIELDS),
            "digest_map_fields": sorted(DIGEST_MAP_FIELDS),
            "content_addressed_and_runtime_ids": sorted(RUNTIME_ID_FIELDS),
            "time_and_duration_fields": sorted(TIME_FIELDS),
            "path_fields": sorted(PATH_FIELDS),
            "business_project_id_masked": False,
            "table_id_masked": False,
            "annotation_id_masked": False,
            "rule_id_masked": False,
        },
        "masked_field_paths": sorted(masked_paths),
        "counterexamples": counterexamples,
        "http_dto_and_saved_journey": state,
        "snapshot_materialization_descriptions_and_side_artifacts": snapshots,
        "canonical_table_sets_by_submit_role": canonical_tables,
        "bundle_contents": bundles,
        "repository_export_rows_by_submit_role": exports,
        "all_golden_fixtures": golden,
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    passed = (
        counterexamples["business_project_id_change_detected"]
        and counterexamples["arbitrary_64_hex_value_change_detected"]
        and state["equal_after_mask"]
        and snapshots["equal_after_mask"]
        and canonical_tables["equal_after_mask"]
        and all(item["equal_after_mask"] for item in bundles)
        and exports["equal_by_logical_role"]
        and golden["all_differences_approved"]
    )
    print(
        json.dumps(
            {
                "baseline_head": report["baseline_head"],
                "candidate_head": report["candidate_head"],
                "counterexamples_detected": all(counterexamples.values()),
                "http_dto_equal": state["equal_after_mask"],
                "snapshot_descriptions_equal": snapshots["equal_after_mask"],
                "canonical_tables_equal": canonical_tables["equal_after_mask"],
                "bundles_equal": all(item["equal_after_mask"] for item in bundles),
                "repository_exports_equal": exports["equal_by_logical_role"],
                "golden_differences_approved": golden["all_differences_approved"],
                "masked_field_path_count": len(masked_paths),
                "report": str(arguments.report),
                "status": "PASS" if passed else "DIFFERENCE",
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
