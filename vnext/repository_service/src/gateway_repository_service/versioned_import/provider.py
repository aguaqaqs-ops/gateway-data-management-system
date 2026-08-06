"""Candidate A offline CLI adapter for Versioned import ref primitives."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import TableCatalog, UnknownTypePolicy as ArrowUnknownTypePolicy
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, DoltCliError, value
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import (
    IMPORT_MAIN_REF,
    commit_literal,
    parse_log_parent_field,
    validate_commit_id,
    validate_operation_marker,
    validate_private_ref_marker_pair,
    validate_private_ref_name,
    validate_readable_ref_name,
)
from gateway_repository_service.candidate_a.sql import ProviderError
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
    if isinstance(exc, (CandidateAError, ProviderError, DoltCliError, ProcessBoundaryError)):
        return ImportProviderError(str(exc))
    if isinstance(exc, (csv.Error, UnicodeDecodeError)):
        return ImportProviderError(str(exc))
    return ImportProviderError(str(exc))


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
        except DoltCliError as exc:
            raise ImportProviderError(str(exc)) from exc
        if not rows:
            raise ImportProviderError("Dolt did not return ref hash")
        return str(value(rows[0], "commit_id", 0))

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
        except DoltCliError as exc:
            raise ImportProviderError(str(exc)) from exc
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
            ["commit", "--message", marker, f"--author={self._settings.author}"],
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
            for branch_name in self._branch_names():
                rows = self._cli.query_json(
                    "marker_scan",
                    "SELECT commit_hash, message, parents FROM dolt_log;\n",
                    revision=branch_name,
                )
                for row in rows:
                    if str(value(row, "message", 1)) != marker:
                        continue
                    candidate = str(value(row, "commit_hash", 0))
                    parent = parse_log_parent_field(value(row, "parents", 0))
                    if parent is None:
                        return MarkerInspectionAmbiguous()
                    key = (candidate, parent)
                    evidence.setdefault(key, set()).add(branch_name)

            if not evidence:
                return MarkerInspectionZero()
            if len(evidence) != 1:
                return MarkerInspectionAmbiguous()

            (candidate, parent), _ = next(iter(evidence.items()))
            refs = self._refs_for_commit(candidate)
            if not refs:
                return MarkerInspectionAmbiguous()
            return MarkerInspectionUnique(candidate=candidate, parent=parent, refs=refs)
        except (DoltCliError, ProviderError, ValueError, ImportProviderError):
            return MarkerInspectionAmbiguous()

    def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        safe_candidate = validate_commit_id(candidate)
        try:
            rows = self._cli.query_json(
                "candidate_parent",
                "SELECT parents FROM dolt_log AS OF "
                f"{commit_literal(safe_candidate)} WHERE commit_hash = {commit_literal(safe_candidate)};\n",
            )
            if not rows:
                raise ImportProviderError("candidate commit is missing from immutable log")
            parent = parse_log_parent_field(value(rows[0], "parents", 0))
            if parent is None:
                raise ImportProviderError("candidate parent is missing or malformed")
            return self._cli.catalog(parent, safe_candidate)
        except (DoltCliError, ProviderError, ValueError) as exc:
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
                ArrowUnknownTypePolicy(policy),
            )
        except (DoltCliError, ProviderError, ValueError) as exc:
            raise _as_import_provider_error(exc) from exc

        def _emit() -> Iterator[pa.RecordBatch]:
            try:
                for batch in iterator:
                    yield batch
            except (DoltCliError, ProviderError, ValueError, ProcessBoundaryError, csv.Error, UnicodeDecodeError) as exc:
                raise _as_import_provider_error(exc) from exc

        return _emit()

    def publish_main(self, expected_commit: str, candidate: str) -> PublishMainResult:
        safe_expected = validate_commit_id(expected_commit)
        safe_candidate = validate_commit_id(candidate)
        try:
            actual = self.read_ref(IMPORT_MAIN_REF)
        except ImportProviderError:
            return PublishMainAmbiguous()
        if actual != safe_expected:
            return PublishMainMismatch(actual=actual)

        result = self._runner.run(
            "publish_main_force",
            ["branch", "-f", IMPORT_MAIN_REF, safe_candidate],
            cwd=self._repository,
            timeout=self._settings.import_timeout_seconds,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            return PublishMainAmbiguous()

        try:
            readback = self.read_ref(IMPORT_MAIN_REF)
        except ImportProviderError:
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
        if private_ref not in self._branch_names():
            return
        if expected_candidate is not None:
            actual = self.read_ref(private_ref)
            if actual != validate_commit_id(expected_candidate):
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
        result = self._runner.run(
            "current_branch",
            ["branch", "--show-current"],
            cwd=self._repository,
            timeout=self._settings.metadata_timeout_seconds,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            raise ImportProviderError("Dolt did not return current branch")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def _branch_names(self) -> tuple[str, ...]:
        result = self._runner.run(
            "branch_list",
            ["branch", "--list"],
            cwd=self._repository,
            timeout=self._settings.metadata_timeout_seconds,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            raise ImportProviderError("Dolt branch list failed")
        names: list[str] = []
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip().lstrip("*").strip()
            if stripped:
                names.append(stripped)
        return tuple(names)

    def _refs_for_commit(self, candidate: str) -> tuple[str, ...]:
        safe_candidate = validate_commit_id(candidate)
        rows = self._cli.query_json(
            "refs_for_commit",
            f"SELECT name FROM dolt_branches WHERE hash = {commit_literal(safe_candidate)};\n",
        )
        return tuple(str(value(row, "name", 0)) for row in rows)

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
        except DoltCliError as exc:
            raise ImportProviderError(str(exc)) from exc
