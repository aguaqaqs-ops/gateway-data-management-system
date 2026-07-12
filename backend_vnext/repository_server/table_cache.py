from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil

from ..core.digests import DigestRef, canonical_json_bytes
from .catalog import RepositoryTableCatalog
from .table_export import RepositoryTableExportArtifact


REPOSITORY_SERVER_TABLE_CACHE_DEFAULT_TTL_DAYS = 180


@dataclass(frozen=True, slots=True)
class RepositoryServerTableCacheKey:
    repository_id: str
    resolved_commit_hash: str
    repository_server_contract_version: str
    dolt_version: str | None = None
    table_name: str | None = None
    table_root_hash: str | None = None
    export_format: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _require_text(self.repository_id, "repository_id"))
        object.__setattr__(
            self,
            "resolved_commit_hash",
            _require_text(self.resolved_commit_hash, "resolved_commit_hash"),
        )
        object.__setattr__(
            self,
            "repository_server_contract_version",
            _require_text(
                self.repository_server_contract_version,
                "repository_server_contract_version",
            ),
        )
        object.__setattr__(self, "dolt_version", _normalize_optional_text(self.dolt_version))
        object.__setattr__(self, "table_name", _normalize_optional_text(self.table_name))
        object.__setattr__(self, "table_root_hash", _normalize_optional_text(self.table_root_hash))
        object.__setattr__(self, "export_format", _normalize_optional_text(self.export_format).upper())

    @classmethod
    def for_catalog(
        cls,
        *,
        repository_id: str,
        resolved_commit_hash: str,
        repository_server_contract_version: str,
        dolt_version: str | None = None,
    ) -> "RepositoryServerTableCacheKey":
        return cls(
            repository_id=repository_id,
            resolved_commit_hash=resolved_commit_hash,
            repository_server_contract_version=repository_server_contract_version,
            dolt_version=dolt_version,
            table_name=None,
            table_root_hash=None,
            export_format=None,
        )

    @classmethod
    def for_export(
        cls,
        *,
        repository_id: str,
        resolved_commit_hash: str,
        repository_server_contract_version: str,
        table_name: str,
        table_root_hash: str | None = None,
        export_format: str,
        dolt_version: str | None = None,
    ) -> "RepositoryServerTableCacheKey":
        return cls(
            repository_id=repository_id,
            resolved_commit_hash=resolved_commit_hash,
            repository_server_contract_version=repository_server_contract_version,
            dolt_version=dolt_version,
            table_name=table_name,
            table_root_hash=table_root_hash,
            export_format=export_format,
        )

    @property
    def cache_digest(self) -> DigestRef:
        return DigestRef.from_payload(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "resolved_commit_hash": self.resolved_commit_hash,
            "repository_server_contract_version": self.repository_server_contract_version,
            "dolt_version": self.dolt_version,
            "table_name": self.table_name,
            "table_root_hash": self.table_root_hash,
            "export_format": self.export_format,
        }


class RepositoryServerTableCache:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def get_catalog(self, key: RepositoryServerTableCacheKey) -> RepositoryTableCatalog | None:
        path = self._catalog_manifest_path(key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("cached catalog payload must be a mapping")
        return RepositoryTableCatalog.from_payload(payload)

    def put_catalog(
        self,
        key: RepositoryServerTableCacheKey,
        catalog: RepositoryTableCatalog,
    ) -> RepositoryTableCatalog:
        self._require_catalog_key(key)
        self._validate_catalog_matches_key(key, catalog)
        path = self._catalog_manifest_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(catalog.to_payload()))
        return catalog

    def get_export_artifact(
        self,
        key: RepositoryServerTableCacheKey,
    ) -> RepositoryTableExportArtifact | None:
        path = self._export_manifest_path(key)
        if not path.is_file():
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, Mapping):
            raise TypeError("cached export manifest must be a mapping")
        artifact_path = self._export_artifact_path(key)
        if not artifact_path.is_file():
            return None
        return RepositoryTableExportArtifact.from_payload(dict(manifest), path=artifact_path)

    def put_export_artifact(
        self,
        key: RepositoryServerTableCacheKey,
        artifact: RepositoryTableExportArtifact,
    ) -> RepositoryTableExportArtifact:
        self._require_export_key(key)
        self._validate_export_matches_key(key, artifact)
        entry_dir = self._export_entry_dir(key)
        entry_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._export_artifact_path(key)
        if artifact.path.resolve() != target_path.resolve():
            shutil.copyfile(artifact.path, target_path)
        else:
            if not target_path.exists():
                target_path.write_bytes(artifact.path.read_bytes())
        manifest_path = self._export_manifest_path(key)
        manifest_path.write_bytes(canonical_json_bytes(artifact.manifest_payload()))
        return RepositoryTableExportArtifact.from_payload(
            artifact.to_payload(),
            path=target_path,
        )

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
            self._root.mkdir(parents=True, exist_ok=True)

    def cleanup_expired(
        self,
        *,
        max_age_days: int = REPOSITORY_SERVER_TABLE_CACHE_DEFAULT_TTL_DAYS,
        now: datetime | None = None,
    ) -> int:
        if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 0:
            raise ValueError("max_age_days must be a non-negative integer")
        reference_time = now or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("now must be timezone-aware when provided")
        export_root = self._root / "export"
        if not export_root.exists():
            return 0
        removed = 0
        for entry_dir in export_root.iterdir():
            if not entry_dir.is_dir():
                continue
            entry_mtime = datetime.fromtimestamp(entry_dir.stat().st_mtime, tz=timezone.utc)
            if reference_time - entry_mtime > timedelta(days=max_age_days):
                shutil.rmtree(entry_dir)
                removed += 1
        return removed

    def _catalog_manifest_path(self, key: RepositoryServerTableCacheKey) -> Path:
        return self._catalog_entry_dir(key) / "catalog.json"

    def _catalog_entry_dir(self, key: RepositoryServerTableCacheKey) -> Path:
        return self._root / "catalog" / key.cache_digest.hex_digest

    def _export_entry_dir(self, key: RepositoryServerTableCacheKey) -> Path:
        return self._root / "export" / key.cache_digest.hex_digest

    def _export_manifest_path(self, key: RepositoryServerTableCacheKey) -> Path:
        return self._export_entry_dir(key) / "manifest.json"

    def _export_artifact_path(self, key: RepositoryServerTableCacheKey) -> Path:
        return self._export_entry_dir(key) / "artifact.bin"

    def _require_catalog_key(self, key: RepositoryServerTableCacheKey) -> None:
        if key.table_name:
            raise ValueError("catalog cache keys must not include table_name")
        if key.export_format:
            raise ValueError("catalog cache keys must not include export_format")

    def _require_export_key(self, key: RepositoryServerTableCacheKey) -> None:
        if not key.table_name:
            raise ValueError("export cache keys must include table_name")
        if not key.export_format:
            raise ValueError("export cache keys must include export_format")

    def _validate_catalog_matches_key(
        self,
        key: RepositoryServerTableCacheKey,
        catalog: RepositoryTableCatalog,
    ) -> None:
        if catalog.repository_id != key.repository_id:
            raise ValueError("catalog repository_id mismatch")
        if catalog.resolved_commit_hash != key.resolved_commit_hash:
            raise ValueError("catalog resolved_commit_hash mismatch")
        if catalog.repository_server_contract_version != key.repository_server_contract_version:
            raise ValueError("catalog repository_server_contract_version mismatch")
        if key.dolt_version and catalog.dolt_version and key.dolt_version != catalog.dolt_version:
            raise ValueError("catalog dolt_version mismatch")

    def _validate_export_matches_key(
        self,
        key: RepositoryServerTableCacheKey,
        artifact: RepositoryTableExportArtifact,
    ) -> None:
        if artifact.repository_id != key.repository_id:
            raise ValueError("export artifact repository_id mismatch")
        if artifact.resolved_commit_hash != key.resolved_commit_hash:
            raise ValueError("export artifact resolved_commit_hash mismatch")
        if artifact.table_name != key.table_name:
            raise ValueError("export artifact table_name mismatch")
        if artifact.export_format != key.export_format:
            raise ValueError("export artifact export_format mismatch")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_text(value: object | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("optional text fields must be strings or None")
    return value.strip()
