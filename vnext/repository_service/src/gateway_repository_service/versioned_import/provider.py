"""Candidate A offline CLI adapter for Versioned import ref primitives."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import TableCatalog
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, _require_exactly_one_row, value
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import (
    IMPORT_MAIN_REF,
    commit_literal,
    marker_literal,
    parse_marker_parent_field,
    validate_commit_id,
    validate_operation_marker,
    validate_private_ref_marker_pair,
    validate_private_ref_name,
    validate_readable_ref_name,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner, ProcessBoundaryError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.ports import (
    CancellationCallback,
    MarkerInspection,
    MarkerInspectionAmbiguous,
    MarkerInspectionUnique,
    MarkerInspectionZero,
    PublishMainAmbiguous,
    PublishMainMismatch,
    PublishMainPublished,
    PublishMainResult,
)


def _as_import_provider_error(exc: BaseException) -> ImportProviderError:
    if isinstance(exc, ImportProviderError):
        return exc
    if isinstance(
        exc,
        (
            CandidateAError,
            ProcessBoundaryError,
            ValueError,
            TypeError,
            IndexError,
            OSError,
            csv.Error,
            UnicodeDecodeError,
        ),
    ):
        return ImportProviderError(str(exc))
    return ImportProviderError(str(exc))


_IMPORT_PROVIDER_FAULTS = (
    CandidateAError,
    ProcessBoundaryError,
    ValueError,
    TypeError,
    IndexError,
    OSError,
)

_STREAM_PROVIDER_FAULTS = (
    CandidateAError,
    ProcessBoundaryError,
    ValueError,
    TypeError,
    OSError,
    csv.Error,
    UnicodeDecodeError,
)

_PUBLISH_AMBIGUOUS_FAULTS = (*_IMPORT_PROVIDER_FAULTS, ImportProviderError)
_MARKER_AMBIGUOUS_FAULTS = (*_IMPORT_PROVIDER_FAULTS, ImportProviderError)


class CandidateAImportProvider:
    """Production-owned Candidate A adapter for import private refs and main CAS."""

    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        repository: Path,
        runner: DoltRunner,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._repository = repository
        self._runner = runner
        self._cli = CandidateADoltCli(settings, layout, repository, runner)
        self._staging_root = layout.staging_artifacts.resolve()

    def read_ref(self, ref_name: str) -> str:
        safe_ref = validate_readable_ref_name(ref_name)
        try:
            rows = self._cli.query_json(
                "read_ref",
                f"SELECT HASHOF('{safe_ref}') AS commit_id;\n",
            )
            row = _require_exactly_one_row(rows, "read_ref")
            raw = value(row, "commit_id", 0)
            if not isinstance(raw, str) or raw == "":
                raise ImportProviderError("Dolt did not return ref hash")
            return validate_commit_id(raw)
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc

    def create_private_ref(self, private_ref: str, expected_commit: str) -> None:
        validate_private_ref_name(private_ref)
        validate_commit_id(expected_commit)
        if private_ref in self._branch_names():
            existing = self.read_ref(private_ref)
            if existing == expected_commit:
                return
            raise ImportProviderError("private ref exists at wrong commit")
        self._run_cli(
            "create_private_ref",
            ["branch", private_ref, expected_commit],
            self._settings.metadata_timeout_seconds,
        )

    def checkout_private_ref(self, private_ref: str) -> None:
        validate_private_ref_name(private_ref)
        self._run_cli(
            "checkout_private_ref",
            ["checkout", private_ref],
            self._settings.metadata_timeout_seconds,
        )

    def replay_sql(
        self,
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        validate_private_ref_name(private_ref)
        if cancellation is not None and cancellation():
            raise ImportProviderError("import replay cancelled before start")
        safe_path = self._validate_replay_path(replay_path)
        if self._current_branch() != private_ref:
            raise ImportProviderError("replay requires private ref checkout")
        try:
            self._cli.replay(safe_path)
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc
        if self._current_branch() != private_ref:
            raise ImportProviderError("replay left private ref checkout")

    def commit_operation_marker(self, private_ref: str, marker: str) -> str:
        validate_private_ref_name(private_ref)
        validate_operation_marker(marker)
        validate_private_ref_marker_pair(private_ref, marker)
        current = self._current_branch()
        if current != private_ref:
            self.checkout_private_ref(private_ref)
        before = self.read_ref(private_ref)
        self._run_cli(
            "stage_marker",
            ["add", "--all"],
            self._settings.metadata_timeout_seconds,
        )
        self._run_cli(
            "operation_marker_commit",
            [
                "commit",
                "--allow-empty",
                "--message",
                marker,
                f"--author={self._settings.author}",
            ],
            self._settings.import_timeout_seconds,
        )
        after = self.read_ref(private_ref)
        if after == before:
            raise ImportProviderError("marker commit did not advance private ref")
        return after

    def inspect_marker(self, marker: str) -> MarkerInspection:
        validate_operation_marker(marker)
        try:
            evidence: dict[tuple[str, str], set[str]] = {}
            branch_heads = self._branch_heads()
            for branch_name, _ in branch_heads:
                rows = self._cli.query_json(
                    "marker_scan",
                    "SELECT commit_hash, message, parents FROM dolt_log "
                    f"WHERE message = {marker_literal(marker)} LIMIT 2;\n",
                    revision=branch_name,
                )
                for row in rows:
                    raw_message = value(row, "message", 1)
                    if not isinstance(raw_message, str):
                        return MarkerInspectionAmbiguous()
                    if raw_message != marker:
                        return MarkerInspectionAmbiguous()
                    raw_candidate = value(row, "commit_hash", 0)
                    if not isinstance(raw_candidate, str) or not raw_candidate:
                        return MarkerInspectionAmbiguous()
                    if raw_candidate != raw_candidate.strip():
                        return MarkerInspectionAmbiguous()
                    candidate = validate_commit_id(raw_candidate)
                    raw_parents = value(row, "parents", 0)
                    if not isinstance(raw_parents, str) or not raw_parents:
                        return MarkerInspectionAmbiguous()
                    if raw_parents != raw_parents.strip():
                        return MarkerInspectionAmbiguous()
                    parent = parse_marker_parent_field(raw_parents)
                    if parent is None:
                        return MarkerInspectionAmbiguous()
                    key = (candidate, parent)
                    evidence.setdefault(key, set()).add(branch_name)

            if not evidence:
                return MarkerInspectionZero()
            if len(evidence) != 1:
                return MarkerInspectionAmbiguous()

            (candidate, parent), _ = next(iter(evidence.items()))
            refs: list[str] = []
            seen_refs: set[str] = set()
            for branch_name, tip_hash in branch_heads:
                if tip_hash != candidate:
                    continue
                ref = validate_readable_ref_name(branch_name)
                if ref in seen_refs:
                    return MarkerInspectionAmbiguous()
                seen_refs.add(ref)
                refs.append(ref)
            if not refs:
                return MarkerInspectionAmbiguous()
            return MarkerInspectionUnique(candidate=candidate, parent=parent, refs=tuple(sorted(refs)))
        except _MARKER_AMBIGUOUS_FAULTS:
            return MarkerInspectionAmbiguous()

    def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        safe_candidate = validate_commit_id(candidate)
        try:
            rows = self._cli.query_json(
                "candidate_parent",
                "SELECT parents FROM dolt_log AS OF "
                f"{commit_literal(safe_candidate)} WHERE commit_hash = {commit_literal(safe_candidate)};\n",
            )
            parent_row = _require_exactly_one_row(rows, "candidate_parent")
            raw_parents = value(parent_row, "parents", 0)
            if not isinstance(raw_parents, str) or not raw_parents:
                raise ImportProviderError("candidate parent is missing or malformed")
            if raw_parents != raw_parents.strip():
                raise ImportProviderError("candidate parent is missing or malformed")
            parent = parse_marker_parent_field(raw_parents)
            if parent is None:
                raise ImportProviderError("candidate parent is missing or malformed")
            return self._cli.catalog(parent, safe_candidate)
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc

    def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        safe_candidate = validate_commit_id(candidate)
        try:
            rows = self._cli.query_json(
                "candidate_parent",
                "SELECT parents FROM dolt_log AS OF "
                f"{commit_literal(safe_candidate)} WHERE commit_hash = {commit_literal(safe_candidate)};\n",
            )
            parent_row = _require_exactly_one_row(rows, "candidate_parent")
            raw_parents = value(parent_row, "parents", 0)
            if not isinstance(raw_parents, str) or not raw_parents:
                raise ImportProviderError("candidate parent is missing or malformed")
            if raw_parents != raw_parents.strip():
                raise ImportProviderError("candidate parent is missing or malformed")
            parent = parse_marker_parent_field(raw_parents)
            if parent is None:
                raise ImportProviderError("candidate parent is missing or malformed")
            return self._cli.type_catalog(parent, safe_candidate)
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc

    def stream_table(
        self,
        candidate: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        safe_candidate = validate_commit_id(candidate)
        try:
            iterator = self._cli.stream_table(
                safe_candidate,
                table,
                policy,
            )
        except _STREAM_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc

        def _emit() -> Iterator[pa.RecordBatch]:
            try:
                for batch in iterator:
                    yield batch
            except _STREAM_PROVIDER_FAULTS as exc:
                raise _as_import_provider_error(exc) from exc

        return _emit()

    def publish_main(self, expected_commit: str, candidate: str) -> PublishMainResult:
        safe_expected = validate_commit_id(expected_commit)
        safe_candidate = validate_commit_id(candidate)
        try:
            actual = self.read_ref(IMPORT_MAIN_REF)
        except _PUBLISH_AMBIGUOUS_FAULTS:
            return PublishMainAmbiguous()
        if actual != safe_expected:
            return PublishMainMismatch(actual=actual)

        try:
            result = self._run_runner(
                "publish_main_force",
                ["branch", "-f", IMPORT_MAIN_REF, safe_candidate],
                self._settings.import_timeout_seconds,
                capture_stdout=True,
            )
        except _PUBLISH_AMBIGUOUS_FAULTS:
            return PublishMainAmbiguous()
        if result.timed_out or result.exit_code != 0:
            return PublishMainAmbiguous()

        try:
            readback = self.read_ref(IMPORT_MAIN_REF)
        except _PUBLISH_AMBIGUOUS_FAULTS:
            return PublishMainAmbiguous()
        if readback != safe_candidate:
            return PublishMainAmbiguous()
        return PublishMainPublished()

    def delete_private_ref(
        self,
        private_ref: str,
        expected_candidate: str | None = None,
    ) -> None:
        validate_private_ref_name(private_ref)
        safe_expected: str | None = None
        if expected_candidate is not None:
            safe_expected = validate_commit_id(expected_candidate)
        if private_ref not in self._branch_names():
            return
        if safe_expected is not None:
            actual = self.read_ref(private_ref)
            if actual != safe_expected:
                raise ImportProviderError("private ref candidate mismatch")
        self._run_cli(
            "checkout_main_for_delete",
            ["checkout", IMPORT_MAIN_REF],
            self._settings.metadata_timeout_seconds,
        )
        self._run_cli(
            "delete_private_ref",
            ["branch", "-D", private_ref],
            self._settings.metadata_timeout_seconds,
        )

    def _validate_replay_path(self, replay_path: Path) -> Path:
        resolved = replay_path.resolve()
        if not resolved.is_relative_to(self._staging_root):
            raise ImportProviderError("replay path outside server-owned staging")
        if not resolved.is_file():
            raise ImportProviderError("replay path is not a regular file")
        return resolved

    def _current_branch(self) -> str:
        result = self._run_runner(
            "current_branch",
            ["branch", "--show-current"],
            self._settings.metadata_timeout_seconds,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            raise ImportProviderError("Dolt did not return current branch")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def _branch_heads(self) -> tuple[tuple[str, str], ...]:
        rows = self._cli.query_json("branch_heads", "SELECT name, hash FROM dolt_branches;\n")
        heads: list[tuple[str, str]] = []
        for row in rows:
            raw_name = value(row, "name", 0)
            raw_hash = value(row, "hash", 0)
            if not isinstance(raw_name, str) or not raw_name:
                raise ValueError("ref name is invalid")
            if raw_name != raw_name.strip():
                raise ValueError("ref name is invalid")
            if not isinstance(raw_hash, str) or not raw_hash:
                raise ValueError("commit id is invalid")
            if raw_hash != raw_hash.strip():
                raise ValueError("commit id is invalid")
            heads.append((raw_name, validate_commit_id(raw_hash)))
        return tuple(heads)

    def _branch_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._branch_heads())

    def _run_runner(
        self,
        command_kind: str,
        args: list[str],
        timeout: float,
        *,
        capture_stdout: bool = False,
    ) -> CommandResult:
        try:
            return self._runner.run(
                command_kind,
                args,
                cwd=self._repository,
                timeout=timeout,
                capture_stdout=capture_stdout,
            )
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc

    def _refs_for_commit(self, candidate: str) -> tuple[str, ...]:
        safe_candidate = validate_commit_id(candidate)
        rows = self._cli.query_json(
            "refs_for_commit",
            f"SELECT name FROM dolt_branches WHERE hash = {commit_literal(safe_candidate)};\n",
        )
        refs: list[str] = []
        seen: set[str] = set()
        for row in rows:
            raw_name = value(row, "name", 0)
            if not isinstance(raw_name, str) or not raw_name:
                raise ValueError("ref name is invalid")
            if raw_name != raw_name.strip():
                raise ValueError("ref name is invalid")
            ref = validate_readable_ref_name(raw_name)
            if ref in seen:
                raise ValueError("duplicate ref evidence")
            seen.add(ref)
            refs.append(ref)
        return tuple(sorted(refs))

    def _run_cli(
        self,
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
    ) -> CommandResult:
        try:
            return self._cli.run_cli(
                kind,
                args,
                timeout,
                stdin_path=stdin_path,
            )
        except _IMPORT_PROVIDER_FAULTS as exc:
            raise _as_import_provider_error(exc) from exc
