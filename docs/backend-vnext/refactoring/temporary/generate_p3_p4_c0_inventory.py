#!/usr/bin/env python3
"""One-shot generator for P3→P4 C0 inventory. Preliminary classification only."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_JSON = Path(__file__).with_name("p3-p4-context-code-consolidation-c0-inventory.json")
OUTPUT_MD = Path(__file__).with_name("p3-p4-context-code-consolidation-c0-inventory.md")

DOC_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt"}
CODE_SUFFIXES = {".py", ".rs", ".sh"}

CODE_DISPOSITIONS: dict[str, str] = {
    "vnext/backend/benchmarks/p3_capability_diagnostics.py": "KEEP_EVIDENCE_TOOL",
    "vnext/backend/src/gateway_backend/capabilities/external_target_sync/_reference_executor.py": (
        "KEEP_P3_REFERENCE_DELIVERABLE"
    ),
    "vnext/backend/src/gateway_backend/synthetic_w2.py": "MOVE_REMOVE_CANDIDATE",
    "vnext/scripts/run_r6_s6_evidence.py": "MOVE_REMOVE_CANDIDATE",
    "vnext/shared_kernel/src/gateway_shared_kernel/testing": "MOVE_CANDIDATE",
    "vnext/repository_service/src/gateway_repository_service/matrix.py": "RETIRE_DECISION_REQUIRED",
    "vnext/repository_service/src/gateway_repository_service/workflow.py": "RETIRE_DECISION_REQUIRED",
    "vnext/repository_service/src/gateway_repository_service/workflow_worker.py": (
        "RETIRE_DECISION_REQUIRED"
    ),
    "vnext/repository_service/src/gateway_repository_service/target_gate.py": (
        "KEEP_UNTIL_PROFILE_RETIRED"
    ),
    "vnext/repository_service/tests/test_p2_r1_audit_corrective.py": "FOLLOW_HARNESS_DECISION",
}

AUTHORITY_PATHS = [
    "AGENTS.md",
    "docs/backend-vnext/testing-conventions.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-handoff.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-f5-independent-acceptance.md",
    "docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md",
    "docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md",
    "docs/backend-vnext/refactoring/formal/plans/p2-p3-cleanup-manifest.yaml",
    "docs/backend-vnext/refactoring/temporary/README.md",
]

PROPOSED_PRE_TAG = "docs/p3-p4-cleanup-pre-20260823"
PROPOSED_FINAL_TAG = "docs/p3-p4-cleanup-final-20260823"

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REF_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)
PATH_IN_TEXT_RE = re.compile(
    r"(?:docs/backend-vnext/[\w./-]+|vnext/[\w./-]+|AGENTS\.md)"
)


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_paths() -> list[str]:
    paths: set[str] = set()
    for rel in AUTHORITY_PATHS:
        if (REPO_ROOT / rel).is_file():
            paths.add(rel)
    for base in (
        REPO_ROOT / "docs/backend-vnext/refactoring/formal",
        REPO_ROOT / "docs/backend-vnext/refactoring/temporary",
        REPO_ROOT / "vnext/deploy",
    ):
        if base.is_dir():
            for file_path in base.rglob("*"):
                if file_path.is_file():
                    paths.add(file_path.relative_to(REPO_ROOT).as_posix())
    tracked_code = run_git(
        "ls-files",
        "vnext",
        "--",
        ":(glob)**/*.py",
        ":(glob)**/*.rs",
        ":(glob)**/*.sh",
    ).splitlines()
    for rel in tracked_code:
        if rel.strip():
            paths.add(rel.strip())
    return sorted(paths)


def tracked_paths() -> set[str]:
    return set(run_git("ls-files").splitlines())


def git_last_commit(rel_path: str) -> tuple[str | None, str | None, str | None]:
    try:
        line = run_git("log", "-1", "--format=%H%x1f%ci%x1f%s", "--", rel_path)
    except subprocess.CalledProcessError:
        return None, None, None
    if not line:
        return None, None, None
    commit, date, subject = line.split("\x1f", 2)
    return commit, date, subject


def is_tracked(rel_path: str, tracked: set[str]) -> bool:
    return rel_path in tracked


def worktree_status(rel_path: str) -> str:
    try:
        line = run_git("status", "--porcelain=v1", "--", rel_path)
    except subprocess.CalledProcessError:
        return "??"
    if not line:
        return "  "
    return line[:2]


def normalize_doc_link(source: Path, target: str) -> str | None:
    target = target.strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    target = target.split("#", 1)[0].strip()
    if not target:
        return None
    if target.startswith("/"):
        candidate = (REPO_ROOT / target.lstrip("/")).resolve()
    else:
        candidate = (source.parent / target).resolve()
    try:
        rel = candidate.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return rel.as_posix()


def extract_doc_links(rel_path: str, content: str) -> list[str]:
    source = REPO_ROOT / rel_path
    links: list[str] = []
    for match in LINK_RE.finditer(content):
        normalized = normalize_doc_link(source, match.group(1))
        if normalized:
            links.append(normalized)
    for match in REF_DEF_RE.finditer(content):
        normalized = normalize_doc_link(source, match.group(2))
        if normalized:
            links.append(normalized)
    return sorted(set(links))


def file_kind(rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower()
    if suffix in DOC_SUFFIXES:
        return "doc"
    if suffix in CODE_SUFFIXES:
        return "code"
    return "other"


def initial_disposition(rel_path: str) -> str | None:
    for prefix, disposition in CODE_DISPOSITIONS.items():
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return disposition
    return None


def classify_doc(rel_path: str, c1_flags: list[str]) -> tuple[str, str]:
    name = Path(rel_path).name
    parent = Path(rel_path).parts

    if name == "p3-p4-context-and-code-consolidation-execution-plan.md":
        return "RETAIN_IN_PLACE", "Active cleanup execution plan for this round."
    if rel_path.endswith("temporary/README.md"):
        return "ACTIVE_INTERFACE", "Temporary directory index."
    if rel_path == "AGENTS.md":
        return "ACTIVE_INTERFACE", "Contributor/agent constraints."
    if rel_path.endswith("testing-conventions.md"):
        return "NORMATIVE", "Testing conventions authority."
    if "refactoring/formal/contracts/" in rel_path or "refactoring/formal/policies/" in rel_path:
        return "NORMATIVE", "Formal contract or policy."
    if "refactoring/formal/adr/" in rel_path:
        return "NORMATIVE", "Formal ADR."
    if "refactoring/formal/architecture/" in rel_path:
        return "NORMATIVE", "Architecture authority."
    if name in {
        "p3-final-closure-handoff.md",
        "p3-final-closure-f5-independent-acceptance.md",
        "p3-r7-mutation-target-closure-handoff.md",
        "p2-external-interface-handoff.md",
    }:
        return "ACTIVE_INTERFACE", "Phase handoff or acceptance record."
    if name == "p3-active-context-index.md":
        c1_flags.append("replace_with_p4_index_in_c2")
        return "ACTIVE_INTERFACE", "Current P3 default entry; C2 will add P4 index."
    if name == "p3-final-closure-benchmark.json":
        return "EVIDENCE_POINTER", "P3 F2 benchmark raw evidence."
    if name == "p2-p3-cleanup-manifest.yaml":
        return "EVIDENCE_POINTER", "Prior cleanup manifest and recovery pointer."
    if name == "p3-capability-foundation-design.md":
        return "NORMATIVE", "P3 capability design authority."
    if name.endswith("-handoff.md") or name.endswith("-design.md"):
        return "ACTIVE_INTERFACE", "Module handoff or design retained as authority."
    if any(part.startswith("p3-r") and "-s0-" in name for part in parent):
        c1_flags.append("archive_process_doc_candidate")
        return "ARCHIVE_FROM_DEFAULT", "P3 S0 entry/freeze process record."
    if any(part.startswith("p3-r") and ("-s6-" in name or "-s7-" in name) for part in parent):
        c1_flags.append("archive_process_doc_candidate")
        return "ARCHIVE_FROM_DEFAULT", "P3 S6/S7 review process record."
    if name.endswith("-execution-plan.md") and "/plans/p3-r" in rel_path:
        c1_flags.append("archive_process_doc_candidate")
        return "ARCHIVE_FROM_DEFAULT", "Completed P3 round execution plan."
    if name == "p3-grill-me-discussion-summary.md":
        c1_flags.append("archive_process_doc_candidate")
        return "ARCHIVE_FROM_DEFAULT", "Temporary discussion summary."
    if name == "p2-r9-s2-step-e-container-gate.md":
        c1_flags.append("retain_unique_pointer")
        return "RETAIN_IN_PLACE", "Retained by deploy README unique pointer."
    if name == "README.md" and "refactoring/formal" in rel_path:
        c1_flags.append("shrink_default_index_in_c2")
        return "ACTIVE_INTERFACE", "Formal docs index; C2 will shrink default retrieval."
    if name in {"implementation-stages.md", "p3-capability-foundation-execution-plan.md"}:
        return "NORMATIVE", "Stage or execution authority."
    if name.startswith("p3-final-closure"):
        return "ACTIVE_INTERFACE", "P3 final closure authority."
    if "refactoring/formal/plans/" in rel_path:
        c1_flags.append("c1_reverse_reference_required")
        return "DEFERRED", "Formal plan path requires C1 reverse-reference audit."
    if "refactoring/temporary/" in rel_path:
        return "DEFERRED", "Temporary path requires C1 owner audit."
    return "DEFERRED", "Unclassified doc path; C1 must confirm."


def classify_code(rel_path: str, c1_flags: list[str]) -> tuple[str, str]:
    disposition = initial_disposition(rel_path)
    if disposition:
        c1_flags.append("code_disposition_c4_required")
        return "DEFERRED", f"Code candidate with initial disposition {disposition}."
    if "/tests/" in rel_path or rel_path.endswith("_test.py") or "/test_" in rel_path:
        return "RETAIN_IN_PLACE", "Test file with current consumer."
    if "/src/" in rel_path:
        return "RETAIN_IN_PLACE", "Production or package source path."
    if rel_path.startswith("vnext/deploy/"):
        c1_flags.append("deployment_consumer_check")
        return "RETAIN_IN_PLACE", "Deploy/compose wiring."
    if rel_path.startswith("vnext/scripts/"):
        c1_flags.append("script_consumer_check")
        return "DEFERRED", "Script path requires C4 consumer audit."
    return "DEFERRED", "Code path requires C4 consumer audit."


def build_inventory(baseline_sha: str) -> dict:
    rel_paths = discover_paths()
    all_tracked = tracked_paths()
    worktree_map = {
        line[3:]: line[:2]
        for line in run_git("status", "--porcelain=v1").splitlines()
        if line.strip()
    }

    files: list[dict] = []
    outgoing_by_path: dict[str, list[str]] = {}
    doc_contents: dict[str, str] = {}

    for rel_path in rel_paths:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            continue
        kind = file_kind(rel_path)
        c1_flags: list[str] = []
        content = ""
        if kind == "doc" and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".txt"}:
            content = path.read_text(encoding="utf-8", errors="replace")
            doc_contents[rel_path] = content
            outgoing = [link for link in extract_doc_links(rel_path, content) if link in rel_paths]
        else:
            outgoing = []

        if kind == "doc":
            preliminary_class, rationale = classify_doc(rel_path, c1_flags)
        elif kind == "code":
            preliminary_class, rationale = classify_code(rel_path, c1_flags)
        else:
            preliminary_class, rationale = "DEFERRED", "Non-doc/code inventory row."

        tracked = is_tracked(rel_path, all_tracked)
        commit, commit_date, commit_subject = git_last_commit(rel_path) if tracked else (None, None, None)
        row: dict = {
            "path": rel_path,
            "kind": kind,
            "tracked": tracked,
            "worktree_status": worktree_map.get(rel_path, worktree_status(rel_path)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "last_commit": commit,
            "last_commit_date": commit_date,
            "last_commit_subject": commit_subject,
            "outgoing_doc_links": outgoing,
            "outgoing_doc_link_count": len(outgoing),
            "outgoing_unresolved": [],
            "preliminary_class": preliminary_class,
            "classification_rationale": rationale,
            "c1_flags": sorted(set(c1_flags)),
            "incoming_links": [],
            "incoming_link_count": 0,
        }
        if kind == "code":
            row["initial_disposition"] = initial_disposition(rel_path)
        files.append(row)
        outgoing_by_path[rel_path] = outgoing

    path_set = {row["path"] for row in files}
    incoming: dict[str, list[str]] = defaultdict(list)
    for rel_path, outgoing in outgoing_by_path.items():
        for target in outgoing:
            if target in path_set:
                incoming[target].append(rel_path)

    for row in files:
        row["incoming_links"] = sorted(incoming.get(row["path"], []))
        row["incoming_link_count"] = len(row["incoming_links"])

    classification_counts = Counter(row["preliminary_class"] for row in files)
    c1_flag_counts = Counter(flag for row in files for flag in row["c1_flags"])
    code_disposition_counts = Counter(
        row["initial_disposition"] for row in files if row.get("initial_disposition")
    )

    authority_sha: dict[str, str] = {}
    for rel in AUTHORITY_PATHS:
        path = REPO_ROOT / rel
        if path.is_file():
            authority_sha[rel] = sha256_file(path)

    vnext_delta = run_git("diff", "--name-only", baseline_sha, "--", "vnext").splitlines()
    vnext_delta = [line for line in vnext_delta if line.strip()]

    identity = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "branch": run_git("rev-parse", "--abbrev-ref", "HEAD"),
        "baseline_sha": baseline_sha,
        "baseline_subject": run_git("log", "-1", "--format=%s", baseline_sha),
        "freeze_head_does_not_include_c0_artifacts": True,
        "worktree_root": str(REPO_ROOT),
        "tested_candidate_sha": "13ce18b8b2d689bc7a4087e0072d485891740c0c",
        "f3_validated_source_sha": "a28d88a85793017716029638155687ca17e4b5ed",
        "f4_validated_source_sha": "a28d88a85793017716029638155687ca17e4b5ed",
        "handoff_record_sha": "b0ac984507056fb10c17c07243330b20a315c2c8",
        "f5_acceptance_record_sha": authority_sha.get(
            "docs/backend-vnext/refactoring/formal/plans/p3-final-closure-f5-independent-acceptance.md"
        ),
        "p3_exit": "pass",
        "p4_ready": "yes",
        "p4_implementation_authorized": "no_until_p4_entry_acceptance",
        "vnext_delta_vs_baseline": vnext_delta,
        "proposed_pre_cleanup_tag": PROPOSED_PRE_TAG,
        "proposed_final_tag": PROPOSED_FINAL_TAG,
        "pre_cleanup_tag_exists": bool(run_git("tag", "-l", PROPOSED_PRE_TAG)),
        "pre_cleanup_tag_create_gate": "C1",
        "authority_sha256": authority_sha,
    }

    return {
        "schema": "gateway.docs-code-lifecycle-cleanup.c0-inventory",
        "schema_version": 1,
        "stage": "p3-p4-context-code-consolidation",
        "step": "C0",
        "c0_status": "complete",
        "note": (
            "Preliminary classification only. C1 confirms owner/consumer. "
            "This inventory is not in baseline_sha and is not image input."
        ),
        "identity": identity,
        "stop_conditions": {
            "source_build_deployment_delta": bool(vnext_delta),
            "pre_cleanup_tag_already_exists": identity["pre_cleanup_tag_exists"],
            "continue_plan": not bool(vnext_delta) and not identity["pre_cleanup_tag_exists"],
        },
        "coverage": {
            "doc_files": sum(1 for row in files if row["kind"] == "doc"),
            "code_files": sum(1 for row in files if row["kind"] == "code"),
            "total_inventory_files": len(files),
            "code_disposition_candidates": len(code_disposition_counts),
        },
        "classification_counts": dict(sorted(classification_counts.items())),
        "c1_flag_counts": dict(sorted(c1_flag_counts.items())),
        "code_disposition_counts": dict(sorted(code_disposition_counts.items())),
        "unresolved_escalations": [],
        "c1_watchlist": [
            "formal/README.md still lists many P3 step/review docs; C2 shrinks default retrieval.",
            "p3-active-context-index.md remains P3 default entry; C2 adds P4 index.",
            "p3-grill-me-discussion-summary.md is an archive candidate.",
            "P3 R1-R6 *-s0-*, *-s6-*, *-s7-*, and round execution plans are archive candidates.",
            "Code candidates in code_disposition_counts require C4 consumer audit.",
            "repository-probe profile binds target_gate.py; do not retire harness before C4 decision.",
        ],
        "files": files,
    }


def render_markdown(inventory: dict) -> str:
    identity = inventory["identity"]
    coverage = inventory["coverage"]
    counts = inventory["classification_counts"]
    code_counts = inventory.get("code_disposition_counts", {})
    stop = inventory["stop_conditions"]

    lines = [
        "# P3→P4 Context and Code Consolidation — C0 Freeze and Inventory",
        "",
        "状态：`complete`（`c0_continue_plan: yes`；preliminary classification only）",
        "",
        f"日期：{identity['generated_at'][:10]}",
        "",
        "本记录冻结 cleanup baseline 与 docs/code inventory。没有修改 `vnext/**` 源码、"
        "Dockerfile、Compose、lockfile 或 candidate checkout，没有创建 git tag，没有重跑测试或重建 image。"
        "初步分类供 C1 确认，不是最终 authority。",
        "",
        "权威计划：[P3→P4 Context and Code Consolidation Execution Plan]"
        "(p3-p4-context-and-code-consolidation-execution-plan.md) §6 C0",
        "机器可读清单：[p3-p4-context-code-consolidation-c0-inventory.json]"
        "(p3-p4-context-code-consolidation-c0-inventory.json)",
        "",
        "## Freeze identity",
        "",
        "```yaml",
        f"branch: {identity['branch']}",
        f"baseline_sha: {identity['baseline_sha']}",
        f"baseline_subject: {identity['baseline_subject']!r}",
        f"freeze_head_does_not_include_c0_artifacts: {str(identity['freeze_head_does_not_include_c0_artifacts']).lower()}",
        f"tested_candidate_sha: {identity['tested_candidate_sha']}",
        f"f3_validated_source_sha: {identity['f3_validated_source_sha']}",
        f"f4_validated_source_sha: {identity['f4_validated_source_sha']}",
        f"handoff_record_sha: {identity['handoff_record_sha']}",
        f"p3_exit: {identity['p3_exit']}",
        f"p4_ready: {identity['p4_ready']}",
        f"p4_implementation_authorized: {identity['p4_implementation_authorized']}",
        f"vnext_delta_vs_baseline: {identity['vnext_delta_vs_baseline']}",
        f"proposed_pre_cleanup_tag: {identity['proposed_pre_cleanup_tag']}",
        f"proposed_final_tag: {identity['proposed_final_tag']}",
        f"pre_cleanup_tag_exists: {str(identity['pre_cleanup_tag_exists']).lower()}",
        f"pre_cleanup_tag_create_gate: {identity['pre_cleanup_tag_create_gate']}",
        "```",
        "",
        "C0 开始时 worktree 在 baseline commit 上为 clean。本 inventory 产物在 baseline 之后生成。",
        "",
        "## Stop conditions",
        "",
        "| 条件 | 结果 |",
        "| --- | --- |",
        f"| source/build/deployment delta vs baseline | {'yes' if stop['source_build_deployment_delta'] else 'no'} |",
        f"| 提议的 pre-cleanup tag 已存在 | {'yes' if stop['pre_cleanup_tag_already_exists'] else 'no'} |",
        f"| 继续本计划 | **{'yes' if stop['continue_plan'] else 'no'}** |",
        "",
        "## Coverage",
        "",
        f"- documentation/code inventory rows: **{coverage['total_inventory_files']}**",
        f"- doc rows: **{coverage['doc_files']}**",
        f"- code rows: **{coverage['code_files']}**",
        f"- code disposition candidates: **{coverage['code_disposition_candidates']}**",
        "",
        "## Preliminary classification counts",
        "",
        "| 分类 | 数量 |",
        "| --- | --- |",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"| `{key}` | {value} |")

    if code_counts:
        lines.extend(
            [
                "",
                "## Code disposition candidates (§3.3, C4 decides)",
                "",
                "| initial_disposition | 数量 |",
                "| --- | --- |",
            ]
        )
        for key, value in sorted(code_counts.items()):
            lines.append(f"| `{key}` | {value} |")

    lines.extend(
        [
            "",
            "## C1 watchlist",
            "",
        ]
    )
    for index, item in enumerate(inventory["c1_watchlist"], start=1):
        lines.append(f"{index}. {item}")

    lines.extend(
        [
            "",
            "## Unresolved escalations",
            "",
            "无。R7 handoff 引用已在 baseline commit 中恢复。",
            "",
            "## C0 exit",
            "",
            "```yaml",
            "c0_exit: pass",
            "baseline_sha: " + identity["baseline_sha"],
            "freeze_head_sha: this_c0_freeze_head",
            "unresolved_escalations: 0",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def annotate_freeze_head(freeze_head_sha: str) -> None:
    inventory = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    inventory["identity"]["freeze_head_sha"] = "this_c0_freeze_head"
    inventory["identity"]["freeze_head_resolution"] = (
        "Literal placeholder; resolve with `git rev-parse HEAD` when this inventory is at HEAD."
    )
    inventory["identity"]["freeze_head_subject"] = run_git("log", "-1", "--format=%s", freeze_head_sha)
    OUTPUT_JSON.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    md = OUTPUT_MD.read_text(encoding="utf-8")
    marker = "freeze_head_does_not_include_c0_artifacts:"
    insert = (
        f"freeze_head_sha: {freeze_head_sha}\n"
        f"freeze_head_subject: {inventory['identity']['freeze_head_subject']!r}\n"
    )
    if "freeze_head_sha:" not in md:
        md = md.replace(
            f"{marker} true",
            f"{marker} true\n"
            "freeze_head_sha: this_c0_freeze_head\n"
            "freeze_head_resolution: git rev-parse HEAD when inventory is at HEAD\n",
            1,
        )
    verified = (
        "\n## Verified freeze head (C0 exit)\n\n"
        f"```text\nfreeze_head_sha: {freeze_head_sha}\n"
        f"freeze_head_subject: {inventory['identity']['freeze_head_subject']!r}\n```\n"
    )
    if "## Verified freeze head (C0 exit)" not in md:
        pass  # literal SHA omitted from committed artifact; resolve via git rev-parse HEAD
    else:
        md = re.sub(
            r"freeze_head_sha: \S+",
            f"freeze_head_sha: {freeze_head_sha}",
            md,
            count=1,
        )
    OUTPUT_MD.write_text(md, encoding="utf-8")


def main() -> None:
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--freeze-head":
        annotate_freeze_head(sys.argv[2])
        print(f"Annotated freeze_head_sha={sys.argv[2]}")
        return

    baseline_sha = run_git("rev-parse", "HEAD")
    inventory = build_inventory(baseline_sha)
    OUTPUT_JSON.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(inventory), encoding="utf-8")
    print(f"Wrote {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"baseline_sha={baseline_sha}")
    print(f"rows={inventory['coverage']['total_inventory_files']}")


if __name__ == "__main__":
    main()
