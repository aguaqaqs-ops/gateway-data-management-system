#!/usr/bin/env python3
"""Generate P3→P4 C1 classification, manifest draft, and summary."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
C0_JSON = Path(__file__).with_name("p3-p4-context-code-consolidation-c0-inventory.json")
OUTPUT_JSON = Path(__file__).with_name("p3-p4-context-code-consolidation-c1-classification.json")
OUTPUT_MD = Path(__file__).with_name("p3-p4-context-code-consolidation-c1-classification.md")
OUTPUT_MANIFEST = (
    REPO_ROOT / "docs/backend-vnext/refactoring/formal/plans/p3-p4-cleanup-manifest.yaml"
)

BASELINE_SHA = "31409c8e0c37d8c12a323269ddeefebdb9927955"
PRE_TAG = "docs/p3-p4-cleanup-pre-20260823"
FINAL_TAG = "docs/p3-p4-cleanup-final-20260823"

DOC_ROOTS = [
    "docs/backend-vnext/refactoring/formal",
    "docs/backend-vnext/refactoring/temporary",
    "AGENTS.md",
    "docs/backend-vnext/testing-conventions.md",
]

ARCHIVE_EXPLICIT = {
    "docs/backend-vnext/refactoring/formal/plans/p3-r1-capability-foundation-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r1-s0-asset-inventory.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r1-s4-focused-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r1-s6-independent-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r2-table-access-parser-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r3-s6-focused-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r3-s7-independent-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r4-s6-focused-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r4-s7-independent-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r5-comparison-discussion-summary.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r5-comparison-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r5-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r6-risk-surface-bundle-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r6-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r6-s6-independent-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r7-mutation-target-closure-execution-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r7-s0-entry-and-budget-freeze.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-r7-s6-independent-review.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-execution-plan.md",
    "docs/backend-vnext/refactoring/temporary/p3-grill-me-discussion-summary.md",
}

MUST_RETAIN_SOURCE_POINTER = {
    "docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md": [
        "vnext/repository_service/tests/test_p2_r1_audit_corrective.py",
        "docs/backend-vnext/refactoring/formal/contracts/repository-service.md",
    ],
    "docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md": [
        "vnext/repository_service/README.md",
    ],
    "docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md": [
        "vnext/deploy/p2r1-cache/README.md",
    ],
}

C6_PROCESS_DOCS = {
    "docs/backend-vnext/refactoring/temporary/p3-p4-context-and-code-consolidation-execution-plan.md",
    "docs/backend-vnext/refactoring/temporary/p3-p4-context-code-consolidation-c0-inventory.json",
    "docs/backend-vnext/refactoring/temporary/p3-p4-context-code-consolidation-c0-inventory.md",
    "docs/backend-vnext/refactoring/temporary/generate_p3_p4_c0_inventory.py",
    "docs/backend-vnext/refactoring/temporary/p3-p4-context-code-consolidation-c1-classification.json",
    "docs/backend-vnext/refactoring/temporary/p3-p4-context-code-consolidation-c1-classification.md",
    "docs/backend-vnext/refactoring/temporary/generate_p3_p4_c1_classification.py",
}

P4_DEFAULT_READS = [
    {
        "path": "docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md",
        "status": "c2_create",
        "role": "P4 default entry",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-handoff.md",
        "status": "active",
        "role": "P3 exit and P4 entry boundary",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-f5-independent-acceptance.md",
        "status": "active",
        "role": "P3 F5 independent acceptance",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/plans/implementation-stages.md",
        "status": "active",
        "role": "Phase map; P4 section",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md",
        "status": "active",
        "role": "Operation lifecycle owner",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md",
        "status": "active",
        "role": "External effect owner",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md",
        "status": "active",
        "role": "Business lifecycle owner",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/contracts/repository-service.md",
        "status": "active",
        "role": "Repository service owner",
    },
    {
        "path": "docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md",
        "status": "active",
        "role": "P3 capability design authority",
    },
    {
        "path": (
            "docs/backend-vnext/refactoring/formal/policies/"
            "proportional-assurance-and-risk-based-verification-policy.md"
        ),
        "status": "active",
        "role": "Proportional assurance policy",
    },
    {"path": "AGENTS.md", "status": "optional", "role": "Contributor constraints"},
    {
        "path": "docs/backend-vnext/testing-conventions.md",
        "status": "optional",
        "role": "Testing conventions",
    },
]

CODE_BUNDLES: list[dict[str, Any]] = [
    {
        "id": "KEEP_EVIDENCE_TOOL",
        "paths": ["vnext/backend/benchmarks/p3_capability_diagnostics.py"],
        "initial_disposition": "KEEP_EVIDENCE_TOOL",
        "consumers": [
            "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-handoff.md",
            "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-benchmark.json",
            "docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md",
        ],
        "c4_default": "KEEP",
    },
    {
        "id": "KEEP_P3_REFERENCE",
        "paths": [
            "vnext/backend/src/gateway_backend/capabilities/external_target_sync/_reference_executor.py",
        ],
        "initial_disposition": "KEEP_P3_REFERENCE_DELIVERABLE",
        "consumers": [
            "vnext/backend/tests/test_external_target_executor.py",
            "vnext/backend/tests/support/external_target_executor.py",
            "vnext/backend/tests/test_external_target_contracts.py",
            "vnext/backend/src/gateway_backend/capabilities/external_target_sync/__init__.py",
        ],
        "c4_default": "KEEP",
    },
    {
        "id": "MOVE_REMOVE_CANDIDATE",
        "paths": [
            "vnext/backend/src/gateway_backend/synthetic_w2.py",
            "vnext/scripts/run_r6_s6_evidence.py",
        ],
        "initial_disposition": "MOVE_REMOVE_CANDIDATE",
        "consumers": [
            "vnext/backend/tests/test_synthetic_w2.py",
            "vnext/backend/tests/test_architecture.py",
        ],
        "c4_default": "DEFER",
    },
    {
        "id": "MOVE_CANDIDATE",
        "paths": [
            "vnext/shared_kernel/src/gateway_shared_kernel/testing/__init__.py",
            "vnext/shared_kernel/src/gateway_shared_kernel/testing/codec.py",
            "vnext/shared_kernel/src/gateway_shared_kernel/testing/dispatch.py",
            "vnext/shared_kernel/src/gateway_shared_kernel/testing/validate_frame.py",
        ],
        "initial_disposition": "MOVE_CANDIDATE",
        "consumers": [
            "vnext/shared_kernel/tests/test_canonical_cases.py",
            "vnext/shared_kernel/tests/test_validate_scalar_frame.py",
            "vnext/shared_kernel/tests/test_sql_enum_set_values.py",
            "vnext/backend/tests/test_architecture.py",
        ],
        "c4_default": "DEFER",
    },
    {
        "id": "RETIRE_DECISION_REQUIRED",
        "paths": [
            "vnext/repository_service/src/gateway_repository_service/matrix.py",
            "vnext/repository_service/src/gateway_repository_service/workflow.py",
            "vnext/repository_service/src/gateway_repository_service/workflow_worker.py",
        ],
        "initial_disposition": "RETIRE_DECISION_REQUIRED",
        "consumers": [
            "vnext/repository_service/tests/test_p2_r1_audit_corrective.py",
            "vnext/repository_service/src/gateway_repository_service/workflow.py",
        ],
        "c4_default": "DEFER",
    },
    {
        "id": "KEEP_UNTIL_PROFILE_RETIRED",
        "paths": [
            "vnext/repository_service/src/gateway_repository_service/target_gate.py",
        ],
        "initial_disposition": "KEEP_UNTIL_PROFILE_RETIRED",
        "consumers": [
            "vnext/deploy/compose.yaml",
            "vnext/repository_service/tests/test_p2_r2_compose_integration.py",
            "vnext/repository_service/tests/test_p2_r1_audit_corrective.py",
        ],
        "c4_default": "KEEP",
    },
    {
        "id": "FOLLOW_HARNESS_DECISION",
        "paths": [
            "vnext/repository_service/tests/test_p2_r1_audit_corrective.py",
        ],
        "initial_disposition": "FOLLOW_HARNESS_DECISION",
        "consumers": [
            "vnext/scripts/run-tests.sh",
            "docs/backend-vnext/testing-conventions.md",
        ],
        "c4_default": "DEFER",
    },
]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REF_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)
BACKTICK_PATH_RE = re.compile(
    r"`((?:docs/backend-vnext/[\w./-]+|vnext/[\w./-]+|AGENTS\.md)[^`]*)`"
)


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_doc_paths() -> list[str]:
    paths: set[str] = set()
    for root in DOC_ROOTS:
        full = REPO_ROOT / root
        if full.is_file():
            paths.add(root)
        elif full.is_dir():
            for file_path in full.rglob("*"):
                if file_path.is_file():
                    paths.add(file_path.relative_to(REPO_ROOT).as_posix())
    # C1 outputs (may not exist yet during first run)
    for rel in (
        OUTPUT_JSON.relative_to(REPO_ROOT).as_posix(),
        OUTPUT_MD.relative_to(REPO_ROOT).as_posix(),
        Path(__file__).relative_to(REPO_ROOT).as_posix(),
        OUTPUT_MANIFEST.relative_to(REPO_ROOT).as_posix(),
    ):
        if (REPO_ROOT / rel).is_file() or rel.endswith((".json", ".md", ".py", ".yaml")):
            paths.add(rel)
    return sorted(paths)


def file_meta(rel_path: str, c0_index: dict[str, dict]) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    if rel_path in c0_index:
        row = c0_index[rel_path]
        return {"bytes": row["bytes"], "sha256": row["sha256"]}
    if path.is_file():
        return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return {"bytes": 0, "sha256": ""}


def consumer_kind(source: str) -> str:
    if source in MUST_RETAIN_SOURCE_POINTER:
        return "must_retain_source_pointer"
    if "/contracts/" in source or "/policies/" in source or "/adr/" in source:
        return "active_normative"
    if "/architecture/" in source:
        return "active_normative"
    if source.endswith("-handoff.md") or source.endswith("-design.md"):
        return "evidence_pointer"
    if "final-closure" in source and source.endswith(".md"):
        return "evidence_pointer"
    if "active-context-index" in source or source.endswith("formal/README.md"):
        return "process_only"
    if "-s0-" in source or "-s6-" in source or "-s7-" in source or "-execution-plan" in source:
        return "process_only"
    if source.startswith("vnext/"):
        return "vnext_consumer"
    if source in {"AGENTS.md", "docs/backend-vnext/testing-conventions.md"}:
        return "active_normative"
    if "implementation-stages" in source or "capability-foundation" in source:
        return "active_normative"
    return "other"


def build_reverse_refs(doc_paths: list[str]) -> dict[str, list[dict[str, str]]]:
    inbound: dict[str, list[dict[str, str]]] = defaultdict(list)
    doc_set = set(doc_paths)
    scan_roots = [
        REPO_ROOT / "docs",
        REPO_ROOT / "vnext",
        REPO_ROOT / "AGENTS.md",
    ]

    def add_ref(target: str, source: str) -> None:
        if target not in doc_set:
            return
        entry = {"source": source, "kind": consumer_kind(source)}
        if entry not in inbound[target]:
            inbound[target].append(entry)

    for source in doc_paths:
        path = REPO_ROOT / source
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in LINK_RE.finditer(text):
            add_ref(normalize_ref(source, match.group(1)), source)
        for match in REF_DEF_RE.finditer(text):
            add_ref(normalize_ref(source, match.group(2)), source)
        for match in BACKTICK_PATH_RE.finditer(text):
            add_ref(match.group(1).split("#", 1)[0], source)

    # vnext string consumers for must-retain docs
    for rel, consumers in MUST_RETAIN_SOURCE_POINTER.items():
        for consumer in consumers:
            add_ref(rel, consumer)

    # basename fallback scan for high-value targets
    for target in doc_paths:
        basename = Path(target).name
        if basename in {"README.md", "implementation-stages.md"}:
            continue
        try:
            hits = subprocess.check_output(
                ["rg", "-l", re.escape(basename), "docs", "vnext", "AGENTS.md"],
                cwd=REPO_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).splitlines()
        except subprocess.CalledProcessError:
            hits = []
        for hit in hits:
            if hit == target:
                continue
            add_ref(target, hit)

    for target in inbound:
        inbound[target].sort(key=lambda item: item["source"])
    return inbound


def normalize_ref(source: str, raw: str) -> str:
    raw = raw.strip().split("#", 1)[0].strip()
    if not raw or raw.startswith(("http://", "https://", "mailto:", "#")):
        return ""
    source_path = REPO_ROOT / source
    if raw.startswith("/"):
        candidate = (REPO_ROOT / raw.lstrip("/")).resolve()
    else:
        candidate = (source_path.parent / raw).resolve()
    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return ""


def classify_doc(rel_path: str, inbound: list[dict[str, str]]) -> dict[str, Any]:
    name = Path(rel_path).name
    meta = {"path": rel_path}

    if rel_path in ARCHIVE_EXPLICIT:
        active_norm = [c for c in inbound if c["kind"] == "active_normative"]
        return {
            **meta,
            "confirmed_class": "ARCHIVE_FROM_DEFAULT",
            "owner": "Backend vNext Architecture",
            "role": "completed_process_record",
            "c3_action": "archive",
            "c2_action": "link_rewrite" if active_norm else "none",
            "recovery_tag": PRE_TAG,
            "blocks_archive": False,
            "c1_rationale": (
                "Completed P3 step/review/execution process record; semantics owned by "
                "module handoffs, design, contracts, or final closure handoff."
            ),
        }

    if rel_path in MUST_RETAIN_SOURCE_POINTER:
        return {
            **meta,
            "confirmed_class": "RETAIN_IN_PLACE",
            "owner": "Backend vNext Architecture",
            "role": "must_retain_source_pointer",
            "c3_action": "retain",
            "c2_action": "none",
            "blocks_c4_delete": True,
            "consumers": MUST_RETAIN_SOURCE_POINTER[rel_path],
            "c1_rationale": "Unique vnext or contract consumer blocks archive.",
        }

    if rel_path in C6_PROCESS_DOCS or name.startswith("generate_p3_p4"):
        return {
            **meta,
            "confirmed_class": "RETAIN_IN_PLACE",
            "owner": "Cleanup implementer",
            "role": "cleanup_process_record",
            "c3_action": "retain_until_c6",
            "c2_action": "none",
            "c1_rationale": "Cleanup process artifact; removed in C6.",
        }

    if rel_path == "docs/backend-vnext/refactoring/formal/plans/p3-p4-cleanup-manifest.yaml":
        return {
            **meta,
            "confirmed_class": "ACTIVE_INTERFACE",
            "owner": "Backend vNext Architecture",
            "role": "cleanup_manifest_draft",
            "c3_action": "retain",
            "c2_action": "update_through_cleanup",
            "c1_rationale": "Formal cleanup manifest draft for this round.",
        }

    if rel_path.startswith("docs/backend-vnext/refactoring/formal/contracts/"):
        return normative_entry(rel_path, "contract")
    if rel_path.startswith("docs/backend-vnext/refactoring/formal/policies/"):
        return normative_entry(rel_path, "policy")
    if rel_path.startswith("docs/backend-vnext/refactoring/formal/adr/"):
        return normative_entry(rel_path, "adr")
    if rel_path.startswith("docs/backend-vnext/refactoring/formal/architecture/"):
        return normative_entry(rel_path, "architecture")

    if rel_path in {
        "docs/backend-vnext/refactoring/formal/plans/p2-p3-cleanup-manifest.yaml",
        "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-benchmark.json",
    }:
        return {
            **meta,
            "confirmed_class": "EVIDENCE_POINTER",
            "owner": "Backend vNext Architecture",
            "role": "prior_cleanup_or_benchmark_evidence",
            "c3_action": "retain",
            "c2_action": "source_pointer_only",
            "c1_rationale": "Recovery pointer or raw benchmark evidence.",
        }

    if rel_path in {
        "AGENTS.md",
        "docs/backend-vnext/testing-conventions.md",
        "docs/backend-vnext/refactoring/formal/README.md",
        "docs/backend-vnext/refactoring/temporary/README.md",
        "docs/backend-vnext/refactoring/formal/plans/p2-external-interface-handoff.md",
        "docs/backend-vnext/refactoring/formal/plans/implementation-stages.md",
        "docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md",
        "docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md",
        "docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md",
        "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-handoff.md",
        "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-f5-independent-acceptance.md",
        "docs/backend-vnext/refactoring/formal/plans/dx-cross-phase-interface-reconciliation.md",
    }:
        c2 = "shrink_default_index" if rel_path.endswith("formal/README.md") else "none"
        if rel_path.endswith("p3-active-context-index.md"):
            c2 = "replace_with_p4_index_in_c2_archive_in_c3"
        return {
            **meta,
            "confirmed_class": "ACTIVE_INTERFACE",
            "owner": "Backend vNext Architecture",
            "role": "default_entry_or_stage_authority",
            "c3_action": "retain" if "active-context" not in rel_path else "retain_until_c3",
            "c2_action": c2,
            "c1_rationale": "Active retrieval entry or stage authority.",
        }

    if name.endswith("-handoff.md"):
        return {
            **meta,
            "confirmed_class": "ACTIVE_INTERFACE",
            "owner": "Module gate owner",
            "role": "module_handoff",
            "c3_action": "retain",
            "c2_action": "rewrite_links_to_manifest_pointer_for_archived_process_docs",
            "c1_rationale": "P3 module handoff retained as authority.",
        }

    if name.endswith("-design.md") and "/plans/p3-r" in rel_path:
        return {
            **meta,
            "confirmed_class": "ACTIVE_INTERFACE",
            "owner": "Module design owner",
            "role": "module_design",
            "c3_action": "retain",
            "c2_action": "none",
            "c1_rationale": "P3 module design retained as authority.",
        }

  # p2 plans not in must-retain (none left)

    raise ValueError(f"Unclassified doc path: {rel_path}")


def normative_entry(rel_path: str, role: str) -> dict[str, Any]:
    c2_action = "none"
    if rel_path.endswith("0013-enum-set-v1-import-semantics.md"):
        c2_action = "link_rewrite_to_contract_or_handoff"
    return {
        "path": rel_path,
        "confirmed_class": "NORMATIVE",
        "owner": "Contract/ADR owner",
        "role": role,
        "c3_action": "retain",
        "c2_action": c2_action,
        "c1_rationale": f"Formal {role} authority.",
    }


def manifest_bucket(confirmed_class: str, entry: dict[str, Any]) -> str:
    mapping = {
        "ACTIVE_INTERFACE": "active",
        "NORMATIVE": "normative",
        "EVIDENCE_POINTER": "evidence_pointer",
        "RETAIN_IN_PLACE": "retain_in_place",
        "ARCHIVE_FROM_DEFAULT": "archive_from_default",
    }
    return mapping[confirmed_class]


def yaml_quote(value: str) -> str:
    if not value:
        return '""'
    if any(ch in value for ch in ':"{}\n#'):
        return json.dumps(value, ensure_ascii=False)
    return value


def dump_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit(key: str, value: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            for child_key, child_value in value.items():
                emit(child_key, child_value, indent + 1)
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{pad}  -")
                    first = True
                    for child_key, child_value in item.items():
                        if first:
                            lines.append(
                                f"{pad}    {child_key}: {format_scalar(child_value)}"
                            )
                            first = False
                        else:
                            emit(child_key, child_value, indent + 2)
                else:
                    lines.append(f"{pad}  - {format_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {format_scalar(value)}")

    def format_scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, (int, float)):
            return str(value)
        return yaml_quote(str(value))

    for key, value in data.items():
        emit(key, value, 0)
    return "\n".join(lines) + "\n"


def render_markdown(payload: dict[str, Any]) -> str:
    counts = payload["classification_counts"]
    identity = payload["identity"]
    lines = [
        "# P3→P4 Context and Code Consolidation — C1 Classification",
        "",
        "状态：`complete`（`c1_continue_plan: yes`；`unresolved_escalations: 0`）",
        "",
        f"日期：{identity['generated_at'][:10]}",
        "",
        "本记录确认每个文档 path 的 owner、consumer、保留义务与 C2/C3/C4 动作。"
        "没有修改 `vnext/**`、没有删除文件、没有创建 pre-tag（提交后创建）。",
        "",
        "权威计划：[P3→P4 Context and Code Consolidation Execution Plan]"
        "(p3-p4-context-and-code-consolidation-execution-plan.md) §7 C1",
        "上游 C0：[p3-p4-context-code-consolidation-c0-inventory.md]"
        "(p3-p4-context-code-consolidation-c0-inventory.md)",
        "机器可读表：[p3-p4-context-code-consolidation-c1-classification.json]"
        "(p3-p4-context-code-consolidation-c1-classification.json)",
        "Manifest draft：[p3-p4-cleanup-manifest.yaml](../formal/plans/p3-p4-cleanup-manifest.yaml)",
        "",
        "## Continue / stop",
        "",
        "```yaml",
        "c1_status: complete",
        "c1_continue_plan: yes",
        "unresolved_escalations: 0",
        f"baseline_sha: {identity['baseline_sha']}",
        f"pre_cleanup_tag: {PRE_TAG}",
        "```",
        "",
        "## Confirmed counts",
        "",
        "| Manifest bucket | 数量 |",
        "| --- | ---: |",
    ]
    for key in (
        "active",
        "normative",
        "evidence_pointer",
        "retain_in_place",
        "archive_from_default",
        "deferred",
    ):
        lines.append(f"| `{key}` | {counts.get(key, 0)} |")

    lines.extend(["", "## P4 default reads", ""])
    for item in payload["p4_default_reads"]:
        status = item["status"]
        lines.append(f"- `{item['path']}` ({status}) — {item['role']}")

    lines.extend(["", "## Must retain source pointer", ""])
    for path, consumers in MUST_RETAIN_SOURCE_POINTER.items():
        lines.append(f"- `{path}` ← {', '.join(f'`{c}`' for c in consumers)}")

    lines.extend(["", "## Code bundles (C4 decides)", ""])
    for bundle in payload["code_bundles"]:
        lines.append(
            f"- `{bundle['id']}`: {len(bundle['paths'])} path(s); "
            f"default `{bundle['c4_default']}`"
        )

    lines.extend(["", "## Findings", ""])
    for finding in payload["findings"]:
        lines.append(f"### `{finding['id']}`")
        lines.append("")
        lines.append(f"- path: `{finding['path']}`")
        lines.append(f"- fact: {finding['fact']}")
        lines.append(f"- action: {finding['action']}")
        lines.append("")

    lines.extend(
        [
            "## C1 exit",
            "",
            "```yaml",
            "c1_exit: pass",
            "unresolved_escalations: 0",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_payload() -> dict[str, Any]:
    c0 = json.loads(C0_JSON.read_text(encoding="utf-8"))
    c0_index = {row["path"]: row for row in c0["files"] if row["kind"] == "doc"}
    doc_paths = discover_doc_paths()
    inbound = build_reverse_refs(doc_paths)

    files: list[dict[str, Any]] = []
    manifest_paths: dict[str, list[dict[str, Any]]] = {
        "active": [],
        "normative": [],
        "evidence_pointer": [],
        "retain_in_place": [],
        "archive_from_default": [],
        "move_test_support": [],
        "remove_dead": [],
        "deferred": [],
    }

    for rel_path in doc_paths:
        if not (REPO_ROOT / rel_path).is_file() and rel_path not in C6_PROCESS_DOCS:
            continue
        classification = classify_doc(rel_path, inbound.get(rel_path, []))
        meta = file_meta(rel_path, c0_index)
        row = {
            **classification,
            "bytes": meta["bytes"],
            "sha256": meta["sha256"],
            "inbound_refs": inbound.get(rel_path, []),
            "inbound_ref_count": len(inbound.get(rel_path, [])),
        }
        files.append(row)
        bucket = manifest_bucket(row["confirmed_class"], row)
        manifest_entry = {
            "path": rel_path,
            "class": row["confirmed_class"],
            "role": row["role"],
            "sha256": meta["sha256"],
            "bytes": meta["bytes"],
        }
        if bucket == "archive_from_default":
            manifest_entry["recovery_tag"] = PRE_TAG
        if row.get("blocks_c4_delete"):
            manifest_entry["blocks_c4_delete"] = True
        manifest_paths[bucket].append(manifest_entry)

    for bundle in CODE_BUNDLES:
        manifest_paths["deferred"].append(
            {
                "bundle_id": bundle["id"],
                "class": "DEFERRED",
                "initial_disposition": bundle["initial_disposition"],
                "paths": bundle["paths"],
                "c4_default": bundle["c4_default"],
            }
        )

    counts = {key: len(value) for key, value in manifest_paths.items()}

    findings = [
        {
            "id": "adr-0013-process-links",
            "path": "docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md",
            "fact": "ADR links to P3-R2 S0 and execution plan as table_access pointers.",
            "action": "C2 rewrite links to owning contracts/handoff; not an archive blocker.",
        },
        {
            "id": "p3-active-context-process-matrix",
            "path": "docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md",
            "fact": "Default P3 index still lists many process docs slated for archive.",
            "action": "C2 create P4 index; C3 archive process docs and retire P3 index.",
        },
        {
            "id": "formal-readme-process-list",
            "path": "docs/backend-vnext/refactoring/formal/README.md",
            "fact": "Formal README still lists R5/R6/R7 S0 and execution plans.",
            "action": "C2 shrink default index to active handoffs/contracts only.",
        },
        {
            "id": "final-closure-plan-links",
            "path": "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-execution-plan.md",
            "fact": "Active handoff/F5/design still link to final closure execution plan.",
            "action": "C2 rewrite to handoff/F5/manifest recovery pointer before C3 archive.",
        },
        {
            "id": "repository-probe-harness",
            "path": "vnext/repository_service/src/gateway_repository_service/target_gate.py",
            "fact": "Compose repository-probe profile still invokes target_gate.",
            "action": "C4 must decide harness retirement as one bundle with profile/README/tests.",
        },
    ]

    return {
        "schema": "gateway.docs-code-lifecycle-cleanup.c1-classification",
        "schema_version": 1,
        "stage": "p3-p4-context-code-consolidation",
        "step": "C1",
        "c1_status": "complete",
        "c1_continue_plan": True,
        "note": (
            "Confirmed classification for C2/C3/C4. No deletions. Pre-tag created after commit."
        ),
        "identity": {
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "baseline_sha": BASELINE_SHA,
            "c1_head_sha": "this_c1_head",
            "branch": run_git("rev-parse", "--abbrev-ref", "HEAD"),
            "tested_candidate_sha": "13ce18b8b2d689bc7a4087e0072d485891740c0c",
            "p3_exit": "pass",
            "p4_ready": "yes",
        },
        "classification_counts": counts,
        "unresolved_escalations": [],
        "p4_default_reads": P4_DEFAULT_READS,
        "code_bundles": CODE_BUNDLES,
        "findings": findings,
        "must_retain_paths": list(MUST_RETAIN_SOURCE_POINTER.keys()),
        "archive_path_count": len(manifest_paths["archive_from_default"]),
        "files": files,
        "manifest_paths": manifest_paths,
    }


def build_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "gateway.docs-code-lifecycle-cleanup.manifest",
        "schema_version": 1,
        "stage": "p3-p4-context-code-consolidation",
        "step": "C1",
        "c1_status": "complete",
        "generated_at": payload["identity"]["generated_at"],
        "public_semantics_changed": False,
        "archive_medium": "git_annotated_tag_and_history",
        "retain_owner": "Backend vNext Architecture",
        "identity": {
            "baseline_sha": BASELINE_SHA,
            "c1_head_sha": "this_c1_head",
            "tested_candidate_sha": payload["identity"]["tested_candidate_sha"],
            "p3_exit": "pass",
            "p4_ready": "yes",
        },
        "tags": {
            "proposed_pre_cleanup_tag": PRE_TAG,
            "pre_cleanup_tag": PRE_TAG,
            "pre_cleanup_commit": "this_c1_head",
            "pre_cleanup_tag_object": "this_pre_cleanup_tag",
            "proposed_final_tag": FINAL_TAG,
        },
        "artifacts": {
            "c0_inventory": (
                "docs/backend-vnext/refactoring/temporary/"
                "p3-p4-context-code-consolidation-c0-inventory.md"
            ),
            "c1_classification": (
                "docs/backend-vnext/refactoring/temporary/"
                "p3-p4-context-code-consolidation-c1-classification.md"
            ),
            "manifest": "docs/backend-vnext/refactoring/formal/plans/p3-p4-cleanup-manifest.yaml",
            "execution_plan": (
                "docs/backend-vnext/refactoring/temporary/"
                "p3-p4-context-and-code-consolidation-execution-plan.md"
            ),
        },
        "p4_default_reads": payload["p4_default_reads"],
        "code_bundles": payload["code_bundles"],
        "counts": payload["classification_counts"],
        "unresolved_escalations": 0,
        "paths": payload["manifest_paths"],
    }


def annotate_tag_in_manifest(tag_object: str, tag_commit: str) -> None:
    text = OUTPUT_MANIFEST.read_text(encoding="utf-8")
    text = re.sub(
        r"pre_cleanup_tag_object: \S+",
        f"pre_cleanup_tag_object: {tag_object}",
        text,
        count=1,
    )
    # commit stays this_c1_head placeholder; verified in C1 MD
    OUTPUT_MANIFEST.write_text(text, encoding="utf-8")
    payload = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["identity"]["pre_cleanup_tag_object"] = tag_object
    payload["identity"]["pre_cleanup_commit"] = tag_commit
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md = OUTPUT_MD.read_text(encoding="utf-8")
    verified = (
        "\n## Verified pre-cleanup tag (C1 exit)\n\n"
        f"```text\npre_cleanup_tag: {PRE_TAG}\n"
        f"pre_cleanup_commit: {tag_commit}\n"
        f"pre_cleanup_tag_object: {tag_object}\n```\n"
    )
    if "## Verified pre-cleanup tag (C1 exit)" not in md:
        md = md.replace("## C1 exit", verified + "\n## C1 exit", 1)
    OUTPUT_MD.write_text(md, encoding="utf-8")


def main() -> None:
    import sys

    if len(sys.argv) == 4 and sys.argv[1] == "--annotate-tag":
        annotate_tag_in_manifest(sys.argv[2], sys.argv[3])
        print(f"Annotated tag object {sys.argv[2]}")
        return

    payload = build_payload()
    manifest = build_manifest(payload)

    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(payload), encoding="utf-8")
    OUTPUT_MANIFEST.write_text(dump_yaml(manifest), encoding="utf-8")

    print(f"Wrote {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"Wrote {OUTPUT_MANIFEST.relative_to(REPO_ROOT)}")
    print("counts", payload["classification_counts"])
    print("archive", payload["archive_path_count"])
    print("files", len(payload["files"]))


if __name__ == "__main__":
    main()
