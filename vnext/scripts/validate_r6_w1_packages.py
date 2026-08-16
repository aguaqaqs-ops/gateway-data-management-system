#!/usr/bin/env python3
"""Stage G evidence driver: production validator on five v1 packages.

Calls production ``validate_and_extract_import_package`` and
``verify_import_candidate(FULL_SCAN, REJECT)``. Does not publish main, does
not claim S6 PASS, and does not write readiness digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from uuid import UUID, uuid4

import pyarrow as pa  # type: ignore[import-untyped]

_VNEXT_ROOT = Path(__file__).resolve().parents[1]
for _extra in (
    _VNEXT_ROOT / "backend" / "src",
    _VNEXT_ROOT / "repository_service" / "src",
    _VNEXT_ROOT / "repository_contracts" / "src",
    _VNEXT_ROOT / "shared_kernel" / "src",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from gateway_backend.repository_import_artifact import (  # noqa: E402
    build_repository_import_package,
)

REPOSITORY_IMPORT_MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
from gateway_repository_contracts import (  # noqa: E402
    OperationStatus,
    RepositoryArtifactRef,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_repository_service.arrow_mapping import (  # noqa: E402
    compile_table_plan,
    is_known_sql_type,
)
from gateway_repository_service.control_db import (  # noqa: E402
    CONTROL_DB_USER_VERSION,
    ControlStore,
)
from gateway_repository_service.enum_set_sql import (  # noqa: E402
    EnumSetSqlTypeKind,
    classify_enum_set_sql_type,
)
from gateway_repository_service.layout import DurableLayout  # noqa: E402
from gateway_repository_service.mutation_store import IdempotencyKeyHash  # noqa: E402
from gateway_repository_service.process import DoltRunner  # noqa: E402
from gateway_repository_service.providers import OfflineCliProvider  # noqa: E402
from gateway_repository_service.settings import RepositoryServiceSettings  # noqa: E402
from gateway_repository_service.upload_artifact.visibility import (  # noqa: E402
    artifact_ready_path,
)
from gateway_repository_service.versioned_import import (  # noqa: E402
    ImportOperationStore,
    ImportRequestBinding,
    derive_operation_marker,
    derive_private_ref_name,
    versioned_import_fingerprint_v1,
)
from gateway_repository_service.versioned_import.command import (  # noqa: E402
    ImportOperationExecutor,
)
from gateway_repository_service.versioned_import.models import (  # noqa: E402
    ImportManifest,
    ImportPackageRejected,
)
from gateway_repository_service.versioned_import.package import (  # noqa: E402
    validate_and_extract_import_package,
)
from gateway_repository_service.versioned_import.provider import (  # noqa: E402
    CandidateAImportProvider,
)
from gateway_repository_service.versioned_import.verification import (  # noqa: E402
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
    ImportVerificationError,
    verify_import_candidate,
)

FIXTURE_ORDER = ("small_cut", "small", "medium", "data2", "data1")
EXPECTED_PACKAGES = {
    "small_cut": (
        83838,
        "54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43",
        "sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a",
    ),
    "small": (
        613635,
        "e440af6963d99315ef632fcf34f57741de0791ec9a8942ce284b2900efbf82c3",
        "sha256:5c01406aba92537be95b3ba904e6ff092661c7bce30352f3369bdf3cc6958b49",
    ),
    "medium": (
        2081228,
        "3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e",
        "sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c",
    ),
    "data2": (
        3173874,
        "72a266b25f2712d8f23f3010937693dc4a5a41dd93e2cb237928f711aa0fc813",
        "sha256:c1cad27c519695ba9701cdf4b5572714dfcab295355bd614f42a0d5fad53e340",
    ),
    "data1": (
        5724227,
        "bd607ecbca4890d273188f93d1020fa32e2cc0cbd5f6f9ffdbfcffe49feb9bf2",
        "sha256:29a37b49168a04da8e802471f8eaf6221b64abbdef16eb64cc1ba9fa848dd435",
    ),
}
DEFAULT_FIXTURE_ROOT = Path("/root/test-data")
_EXECUTOR_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")
_EXECUTOR_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
_EXECUTOR_OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c21")


class StageGError(RuntimeError):
    """Stage G production validator failed closed."""


@dataclass(frozen=True)
class FixtureResult:
    alias: str
    package_bytes: int
    package_sha256: str
    canonicalization_manifest_digest: str
    observed_raw_size_bytes: int
    observed_raw_sha256: str
    extract_result: str
    verification_policy: str
    unknown_type_policy: str
    completed_verification_policy: str
    table_count: int
    total_row_count: int
    enum_column_count: int
    set_column_count: int
    unknown_column_count: int
    lossy_column_count: int
    main_unchanged: bool
    candidate: str
    elapsed_seconds: float


@dataclass(frozen=True)
class NegativeProbeResult:
    name: str
    outcome: str
    detail: str


def _git_head() -> str:
    repo = _VNEXT_ROOT.parent
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
    ).strip()


def _strip_sha_prefix(value: str) -> str:
    if value.startswith("sha256:"):
        return value.removeprefix("sha256:")
    return value


def _stage_g_settings(data_root: Path) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=data_root,
        bearer_token="stage-g-validator",
        catalog_parallel_workers=4,
        metadata_timeout_seconds=180.0,
        import_timeout_seconds=4.0 * 60.0 * 60.0,
        full_scan_timeout_seconds=3600,
    )


def _locate_package(alias: str, fixture_root: Path) -> tuple[Path, int, str, str]:
    expected_bytes, expected_sha, expected_digest = EXPECTED_PACKAGES[alias]
    package_path = fixture_root / alias / "package.tar.zst"
    payload = package_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != expected_bytes or digest != expected_sha:
        raise StageGError(
            f"{alias} package identity mismatch: bytes={len(payload)} sha256={digest}"
        )
    return package_path, expected_bytes, expected_sha, expected_digest


def _extract_package(
    *,
    package_path: Path,
    expected_bytes: int,
    expected_sha: str,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> Any:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    return validate_and_extract_import_package(
        artifact_path=package_path,
        expected_size_bytes=expected_bytes,
        expected_raw_sha256=expected_sha,
        staging_dir=staging_dir,
        settings=settings,
    )


def _inspect_compiled_plans(catalog: tuple[Any, ...]) -> tuple[int, int, int, int]:
    enum_count = 0
    set_count = 0
    unknown_count = 0
    lossy_count = 0
    for table in catalog:
        plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
        for column_plan in plan.columns:
            metadata = column_plan.field.metadata or {}
            if metadata.get(b"gateway.lossy") == b"true":
                lossy_count += 1
            kind, parsed = classify_enum_set_sql_type(column_plan.column.sql_type)
            if kind is EnumSetSqlTypeKind.MALFORMED:
                raise StageGError(
                    f"malformed ENUM/SET after FULL_SCAN: {table.name}.{column_plan.column.name}"
                )
            if kind is EnumSetSqlTypeKind.VALID and parsed is not None:
                logical = metadata.get(b"gateway.logical_type")
                sql_type_meta = metadata.get(b"gateway.sql_type")
                if sql_type_meta != parsed.normalized.encode("utf-8"):
                    raise StageGError(
                        f"gateway.sql_type mismatch for {table.name}.{column_plan.column.name}"
                    )
                if parsed.kind == "ENUM":
                    if not pa.types.is_string(column_plan.field.type) or logical != b"enum":
                        raise StageGError(
                            f"ENUM Arrow schema mismatch for {table.name}.{column_plan.column.name}"
                        )
                    enum_count += 1
                else:
                    if (
                        not pa.types.is_list(column_plan.field.type)
                        or not pa.types.is_string(column_plan.field.type.value_type)
                        or logical != b"set"
                    ):
                        raise StageGError(
                            f"SET Arrow schema mismatch for {table.name}.{column_plan.column.name}"
                        )
                    set_count += 1
                continue
            if not is_known_sql_type(column_plan.column.sql_type):
                unknown_count += 1
    return enum_count, set_count, unknown_count, lossy_count


def _upsert_dataset_yaml(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text.replace(
        "production_validator_result: not_run",
        "production_validator_result: pending_review",
        1,
    )
    if updated == text:
        raise StageGError(f"{path} did not contain production_validator_result: not_run")
    path.write_text(updated, encoding="utf-8")


def validate_one(
    alias: str,
    *,
    fixture_root: Path,
    work_root: Path,
    log: TextIO,
    run_row_count_mismatch: bool,
) -> tuple[FixtureResult, NegativeProbeResult | None]:
    started = time.monotonic()
    package_path, expected_bytes, expected_sha, expected_digest = _locate_package(
        alias, fixture_root
    )
    work = work_root / alias
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    data_root = work / "data-root"
    settings = _stage_g_settings(data_root)
    layout = DurableLayout.create_service(data_root)
    repo_path = layout.versioned / "repo"
    repo_path.mkdir()
    home = data_root / "dolt-home"
    tmpdir = data_root / "dolt-tmp"
    runner = DoltRunner(settings, layout.root, home=home, tmpdir=tmpdir)
    offline = OfflineCliProvider(settings, layout, repo_path, runner)
    provider = CandidateAImportProvider(settings, layout, repo_path, runner)
    operation_id = uuid4()
    staging_dir = layout.staging_artifacts / f"import-{operation_id.hex}"
    mismatch: NegativeProbeResult | None = None
    try:
        log.write(f"{alias}: extracting package {expected_bytes} bytes\n")
        log.flush()
        package = _extract_package(
            package_path=package_path,
            expected_bytes=expected_bytes,
            expected_sha=expected_sha,
            staging_dir=staging_dir,
            settings=settings,
        )
        if package.observed_raw_size_bytes != expected_bytes:
            raise StageGError(f"{alias} observed size mismatch")
        if package.observed_raw_sha256 != expected_sha:
            raise StageGError(f"{alias} observed sha256 mismatch")
        if package.manifest.canonicalization_manifest_digest != expected_digest:
            raise StageGError(
                f"{alias} digest mismatch: {package.manifest.canonicalization_manifest_digest}"
            )
        log.write(f"{alias}: initializing Dolt repository\n")
        log.flush()
        offline.initialize_repository()
        main_before = provider.read_ref("main")
        private_ref = derive_private_ref_name(operation_id)
        marker = derive_operation_marker(operation_id)
        provider.create_private_ref(private_ref, main_before)
        provider.checkout_private_ref(private_ref)
        log.write(f"{alias}: replaying extracted replay.sql\n")
        log.flush()
        provider.replay_sql(private_ref, package.replay_sql_path)
        candidate = provider.commit_operation_marker(private_ref, marker)
        log.write(f"{alias}: FULL_SCAN REJECT candidate {candidate}\n")
        log.flush()
        verification = verify_import_candidate(
            provider,
            candidate=candidate,
            manifest=package.manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.REJECT,
            full_scan_timeout_seconds=settings.full_scan_timeout_seconds,
        )
        if verification.completed_verification_policy != VerificationPolicy.FULL_SCAN:
            raise StageGError(f"{alias} completed policy is not FULL_SCAN")
        if verification.unknown_type_policy != UnknownTypePolicy.REJECT:
            raise StageGError(f"{alias} unknown type policy is not REJECT")
        catalog = provider.read_catalog(candidate)
        enum_count, set_count, unknown_count, lossy_count = _inspect_compiled_plans(catalog)
        if unknown_count != 0 or lossy_count != 0:
            raise StageGError(
                f"{alias} ENUM/SET mapping leaked unknown={unknown_count} lossy={lossy_count}"
            )
        main_after = provider.read_ref("main")
        if main_after != main_before:
            raise StageGError(f"{alias} verification mutated main")
        if run_row_count_mismatch:
            mismatch = _probe_row_count_mismatch(
                provider,
                candidate=candidate,
                manifest=package.manifest,
                main_before=main_before,
            )
        total_rows = sum(table.row_count for table in package.manifest.tables)
        elapsed = time.monotonic() - started
        log.write(
            f"{alias}: FULL_SCAN pass tables={len(catalog)} rows={total_rows} "
            f"enum={enum_count} set={set_count} elapsed={elapsed:.1f}s\n"
        )
        log.flush()
        _upsert_dataset_yaml(fixture_root / alias / "dataset.yaml")
        return (
            FixtureResult(
                alias=alias,
                package_bytes=expected_bytes,
                package_sha256=f"sha256:{expected_sha}",
                canonicalization_manifest_digest=expected_digest,
                observed_raw_size_bytes=package.observed_raw_size_bytes,
                observed_raw_sha256=f"sha256:{package.observed_raw_sha256}",
                extract_result="pass",
                verification_policy="FULL_SCAN",
                unknown_type_policy="REJECT",
                completed_verification_policy=verification.completed_verification_policy.value,
                table_count=len(catalog),
                total_row_count=total_rows,
                enum_column_count=enum_count,
                set_column_count=set_count,
                unknown_column_count=unknown_count,
                lossy_column_count=lossy_count,
                main_unchanged=True,
                candidate=candidate,
                elapsed_seconds=elapsed,
            ),
            mismatch,
        )
    finally:
        runner.terminate_active_children()
        shutil.rmtree(work, ignore_errors=True)


def _probe_row_count_mismatch(
    provider: CandidateAImportProvider,
    *,
    candidate: str,
    manifest: ImportManifest,
    main_before: str,
) -> NegativeProbeResult:
    first = manifest.tables[0]
    mutated_first = first.model_copy(update={"row_count": first.row_count + 1})
    mutated = manifest.model_copy(update={"tables": (mutated_first, *manifest.tables[1:])})
    try:
        verify_import_candidate(
            provider,
            candidate=candidate,
            manifest=mutated,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.REJECT,
            full_scan_timeout_seconds=3600,
        )
    except ImportVerificationError as exc:
        if exc.code != VERIFICATION_FAILED_NOT_PUBLISHED_CODE:
            raise StageGError(f"row-count mismatch used unexpected code {exc.code}") from exc
        if provider.read_ref("main") != main_before:
            raise StageGError("row-count mismatch published main")
        return NegativeProbeResult(
            name="verification_row_count_mismatch",
            outcome="rejected",
            detail=exc.detail or VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
        )
    raise StageGError("row-count mismatch was accepted")


def _expect_package_rejected(
    *,
    name: str,
    package_path: Path,
    expected_bytes: int,
    expected_sha: str,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
    match: str,
) -> NegativeProbeResult:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    try:
        validate_and_extract_import_package(
            artifact_path=package_path,
            expected_size_bytes=expected_bytes,
            expected_raw_sha256=expected_sha,
            staging_dir=staging_dir,
            settings=settings,
        )
    except ImportPackageRejected as exc:
        if re.search(match, str(exc), flags=re.IGNORECASE) is None:
            raise StageGError(f"{name} rejected with unexpected message: {exc}") from exc
        if staging_dir.exists() and any(staging_dir.iterdir()):
            raise StageGError(f"{name} left staging residue")
        return NegativeProbeResult(name=name, outcome="rejected", detail=str(exc))
    raise StageGError(f"{name} was accepted")


def run_package_admission_probes(
    *,
    fixture_root: Path,
    work_root: Path,
    log: TextIO,
) -> list[NegativeProbeResult]:
    package_path, expected_bytes, expected_sha, _digest = _locate_package(
        "small_cut", fixture_root
    )
    probe_root = work_root / "negative-admission"
    if probe_root.exists():
        shutil.rmtree(probe_root)
    probe_root.mkdir(parents=True)
    settings = _stage_g_settings(probe_root / "settings-root")
    results: list[NegativeProbeResult] = []

    first_dir = probe_root / "reopen-1"
    second_dir = probe_root / "reopen-2"
    first = _extract_package(
        package_path=package_path,
        expected_bytes=expected_bytes,
        expected_sha=expected_sha,
        staging_dir=first_dir,
        settings=settings,
    )
    second = _extract_package(
        package_path=package_path,
        expected_bytes=expected_bytes,
        expected_sha=expected_sha,
        staging_dir=second_dir,
        settings=settings,
    )
    if first.manifest_path.read_bytes() != second.manifest_path.read_bytes():
        raise StageGError("reopen manifest bytes differ")
    if first.replay_sql_path.read_bytes() != second.replay_sql_path.read_bytes():
        raise StageGError("reopen replay.sql bytes differ")
    results.append(
        NegativeProbeResult(
            name="package_reopen",
            outcome="pass",
            detail="second extract matched first extract bytes",
        )
    )
    log.write("negative: package reopen matched\n")
    log.flush()

    truncated_path = probe_root / "truncated.tar.zst"
    truncated_payload = package_path.read_bytes()[:-32]
    truncated_path.write_bytes(truncated_payload)
    truncated_sha = hashlib.sha256(truncated_payload).hexdigest()
    results.append(
        _expect_package_rejected(
            name="truncated_zstd",
            package_path=truncated_path,
            expected_bytes=len(truncated_payload),
            expected_sha=truncated_sha,
            staging_dir=probe_root / "truncated-staging",
            settings=settings,
            match="malformed|incomplete",
        )
    )
    log.write("negative: truncated zstd rejected\n")
    log.flush()

    results.append(
        _expect_package_rejected(
            name="digest_mismatch",
            package_path=package_path,
            expected_bytes=expected_bytes,
            expected_sha="0" * 64,
            staging_dir=probe_root / "digest-staging",
            settings=settings,
            match="sha256",
        )
    )
    log.write("negative: digest mismatch rejected\n")
    log.flush()

    extracted = _extract_package(
        package_path=package_path,
        expected_bytes=expected_bytes,
        expected_sha=expected_sha,
        staging_dir=probe_root / "metadata-source",
        settings=settings,
    )
    manifest_obj = json.loads(extracted.manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_obj, dict):
        raise StageGError("extracted manifest is not an object")
    manifest_obj["unexpected_field"] = "not-in-contract"
    rebuilt = build_repository_import_package(
        manifest=manifest_obj,
        replay_sql=extracted.replay_sql_path.read_bytes(),
    )
    extra_path = probe_root / "extra-field.tar.zst"
    extra_path.write_bytes(rebuilt.payload)
    results.append(
        _expect_package_rejected(
            name="error_metadata_extra_field",
            package_path=extra_path,
            expected_bytes=rebuilt.size_bytes,
            expected_sha=_strip_sha_prefix(rebuilt.sha256),
            staging_dir=probe_root / "extra-staging",
            settings=settings,
            match="validation|extra",
        )
    )
    log.write("negative: extra manifest field rejected\n")
    log.flush()
    shutil.rmtree(probe_root, ignore_errors=True)
    return results


def run_executor_no_dolt_effect(
    *,
    fixture_root: Path,
    work_root: Path,
    log: TextIO,
) -> NegativeProbeResult:
    package_path, _expected_bytes, _expected_sha, _digest = _locate_package(
        "small_cut", fixture_root
    )
    work = work_root / "executor-no-effect"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    data_root = work / "data-root"
    settings = _stage_g_settings(data_root)
    layout = DurableLayout.create_for_probe(data_root)
    repo_path = layout.published_repository(_EXECUTOR_REPOSITORY_ID.hex)
    repo_path.mkdir(parents=True)
    home = data_root / "dolt-home"
    tmpdir = data_root / "dolt-tmp"
    runner = DoltRunner(settings, layout.root, home=home, tmpdir=tmpdir)
    offline = OfflineCliProvider(settings, layout, repo_path, runner)
    provider = CandidateAImportProvider(settings, layout, repo_path, runner)
    control_store: ControlStore | None = None
    try:
        offline.initialize_repository()
        main_before = provider.read_ref("main")
        truncated_payload = package_path.read_bytes()[:-32]
        ready_path = artifact_ready_path(
            layout, _EXECUTOR_REPOSITORY_ID, _EXECUTOR_ARTIFACT_ID
        )
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_bytes(truncated_payload)
        size_bytes = len(truncated_payload)
        raw_sha256 = hashlib.sha256(truncated_payload).hexdigest()
        control_store = ControlStore.open(
            settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        store = ImportOperationStore(
            control_store.connection,
            transaction_lock=control_store.transaction_lock,
        )
        now = "2026-08-16T00:00:00+00:00"
        with store._lock:
            store.mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes, raw_sha256,
                    created_at, updated_at, cleanup_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?,
                    (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle)
                )
                """,
                (
                    str(_EXECUTOR_ARTIFACT_ID),
                    _EXECUTOR_REPOSITORY_ID.hex,
                    REPOSITORY_IMPORT_MEDIA_TYPE,
                    size_bytes,
                    raw_sha256,
                    now,
                    now,
                ),
            )
            store.mutation_store._connection.commit()
        binding = ImportRequestBinding(
            repository_id=_EXECUTOR_REPOSITORY_ID,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=_EXECUTOR_ARTIFACT_ID,
                media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=main_before,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        key_hash = IdempotencyKeyHash.from_raw_key("stage-g-truncated-executor")
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        claimed = store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=_EXECUTOR_OPERATION_ID,
        )
        store.claim_if_queued(claimed.operation_id)
        context = store.load_execution_context(claimed.operation_id)
        if context is None:
            raise StageGError("executor context missing after claim")
        executor = ImportOperationExecutor(
            settings=settings,
            layout=layout,
            store=store,
        )
        executor.execute(context, provider)
        operation = store.get_operation(_EXECUTOR_REPOSITORY_ID, claimed.operation_id)
        if operation is None or operation.error is None:
            raise StageGError("executor did not persist a failure")
        if operation.status != OperationStatus.FAILED:
            raise StageGError(f"executor status is {operation.status}")
        if operation.error.code != IMPORT_REJECTED_CODE:
            raise StageGError(f"executor error code is {operation.error.code}")
        if provider.read_ref("main") != main_before:
            raise StageGError("executor truncated package mutated main")
        private_ref = derive_private_ref_name(claimed.operation_id)
        if provider.private_ref_exists(private_ref):
            raise StageGError("executor created a private ref after package rejection")
        log.write("negative: executor truncated package had no Dolt ref effect\n")
        log.flush()
        return NegativeProbeResult(
            name="executor_truncated_no_dolt_effect",
            outcome="rejected",
            detail=operation.error.code,
        )
    finally:
        if control_store is not None:
            control_store.close()
        runner.terminate_active_children()
        shutil.rmtree(work, ignore_errors=True)


def _assert_cleanup(work_root: Path) -> None:
    if work_root.exists():
        leftovers = [path for path in work_root.rglob("*") if path.is_file()]
        if leftovers:
            raise StageGError(f"temporary files remain under {work_root}: {leftovers[:8]}")
        shutil.rmtree(work_root, ignore_errors=True)
    if work_root.exists():
        raise StageGError(f"work root {work_root} was not removed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run P2-R6-EXT-W1 Stage G production validator")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/p2-r6-ext-w1-stage-g"))
    parser.add_argument("--only", choices=FIXTURE_ORDER, action="append")
    parser.add_argument("--skip-negative", action="store_true")
    parser.add_argument("--skip-positive", action="store_true")
    args = parser.parse_args(argv)
    aliases = tuple(args.only) if args.only else FIXTURE_ORDER
    work_root = args.work_root.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    fixtures: dict[str, FixtureResult] = {}
    negatives: list[NegativeProbeResult] = []
    try:
        if not args.skip_negative:
            negatives.extend(
                run_package_admission_probes(
                    fixture_root=args.fixture_root,
                    work_root=work_root,
                    log=sys.stderr,
                )
            )
            negatives.append(
                run_executor_no_dolt_effect(
                    fixture_root=args.fixture_root,
                    work_root=work_root,
                    log=sys.stderr,
                )
            )
        if not args.skip_positive:
            for alias in aliases:
                result, mismatch = validate_one(
                    alias,
                    fixture_root=args.fixture_root,
                    work_root=work_root,
                    log=sys.stderr,
                    run_row_count_mismatch=alias == "small_cut",
                )
                fixtures[alias] = result
                if mismatch is not None:
                    negatives.append(mismatch)
    finally:
        _assert_cleanup(work_root)

    payload: dict[str, Any] = {
        "candidate_sha": _git_head(),
        "python_version": sys.version.split()[0],
        "dolt_version": "2.1.11",
        "package_version": 1,
        "canonicalization_version": "v1",
        "production_validator_result": "pending_review",
        "P2-R6-S6_ready": "no",
        "fixtures": {
            alias: {
                "package_bytes": result.package_bytes,
                "package_sha256": result.package_sha256,
                "canonicalization_manifest_digest": result.canonicalization_manifest_digest,
                "observed_raw_size_bytes": result.observed_raw_size_bytes,
                "observed_raw_sha256": result.observed_raw_sha256,
                "extract_result": result.extract_result,
                "verification_policy": result.verification_policy,
                "unknown_type_policy": result.unknown_type_policy,
                "completed_verification_policy": result.completed_verification_policy,
                "table_count": result.table_count,
                "total_row_count": result.total_row_count,
                "enum_column_count": result.enum_column_count,
                "set_column_count": result.set_column_count,
                "unknown_column_count": result.unknown_column_count,
                "lossy_column_count": result.lossy_column_count,
                "main_unchanged": result.main_unchanged,
                "candidate": result.candidate,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
            }
            for alias, result in fixtures.items()
        },
        "negative_probes": [
            {"name": item.name, "outcome": item.outcome, "detail": item.detail}
            for item in negatives
        ],
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"stage-g failed: {exc}", file=sys.stderr)
        raise
