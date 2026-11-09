"""Optional durable pure candidate retention, committed only after pair publication."""
from __future__ import annotations

from contextlib import ExitStack
from typing import cast

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.computation_cache import (
    CacheOperationOwner, ComputationCacheEntry, ComputationCacheKey,
    ComputationCacheKind, ComputationCacheLease, ComputationCachePort, encode_cache_manifest,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.risk_evaluation.candidates import (
    MAX_CANDIDATE_BYTES, RISK_CANDIDATES_FORMAT, RiskCandidateEvent, decode_risk_candidates, encode_risk_candidates,
)
from gateway_backend.capabilities.table_access import KernelExecutionContext


def _ref(raw: bytes, media_type: str) -> ArtifactRef:
    digest = raw_blob_digest(raw)
    return ArtifactRef("computation-" + digest.value.removeprefix("sha256:"), media_type, len(raw), digest)


class PersistentRiskCandidates:
    def __init__(self, cache: ComputationCachePort, owner: CacheOperationOwner,
                 repository_id: str, context: KernelExecutionContext) -> None:
        self.cache, self.owner, self.repository_id, self.context = cache, owner, repository_id, context
        self.leases: dict[str, ComputationCacheLease] = {}
        self.decoded: dict[str, ExitStack] = {}
        self.events: dict[str, tuple[object, ...]] = {}
        self.failed: set[str] = set()

    def lookup(self, risk_key: str) -> tuple[object, ...] | None:
        if risk_key in self.failed:
            return None
        if risk_key in self.events:
            return self.events[risk_key]
        context = self.context
        lease = self.cache.lookup_and_pin(
            ComputationCacheKey(self.repository_id, ComputationCacheKind.RISK, DigestRef(risk_key)),
            owner=self.owner, checkpoint=context.checkpoint, reserve=context.memory.reserve,
        )
        if lease is None:
            return None
        charges = ExitStack()
        try:
            if (lease.entry.format != RISK_CANDIDATES_FORMAT or lease.payload != {"complete": True}
                    or len(lease.entry.member_refs) != 1):
                raise ValueError("risk candidate manifest mismatch")
            ref = lease.entry.member_refs[0]
            if ref.size_bytes > MAX_CANDIDATE_BYTES or ref.media_type != "application/json":
                raise ValueError("risk candidate member exceeds its format bound")
            with context.memory.reserve(ref.size_bytes * 2 + 4096), lease.open_buffer(ref) as buffer:
                candidates = decode_risk_candidates(buffer.to_pybytes(), risk_key, context)
            charges.callback(candidates.close)
            charges.callback(lease.close)
            self.leases[risk_key] = lease
            self.decoded[risk_key] = charges
            self.events[risk_key] = candidates.events
            return candidates.events
        except MemoryError:
            charges.close()
            lease.close()
            self.failed.add(risk_key)
            context.checkpoint()
            return None
        except (ValueError, TypeError, KeyError, RecursionError):
            try:
                lease.discard()
            finally:
                charges.close()
                lease.close()
            self.failed.add(risk_key)
            context.checkpoint()
            return None
        except BaseException:
            charges.close()
            lease.close()
            raise

    def commit(self, pending: dict[tuple[str, str], tuple[tuple[object, ...], ExitStack]]) -> None:
        context = self.context
        for lease in self.leases.values():
            lease.mark_used()
        self.close()
        for (_, risk_key), (events, _) in pending.items():
            encoded = None
            try:
                encoded = encode_risk_candidates(cast(tuple[RiskCandidateEvent, ...], events), risk_key, context)
                if encoded is None:
                    continue
                key = ComputationCacheKey(self.repository_id, ComputationCacheKind.RISK, DigestRef(risk_key))
                ref = _ref(encoded.raw, "application/json")
                raw = encode_cache_manifest(key, format=RISK_CANDIDATES_FORMAT,
                    member_refs=(ref,), payload={"complete": True})
                manifest = _ref(raw, "application/json")
                self.cache.store(ComputationCacheEntry(key, RISK_CANDIDATES_FORMAT, manifest, (ref,)),
                    ((manifest, raw), (ref, encoded.raw)), owner=self.owner,
                    checkpoint=context.checkpoint, reserve=context.memory.reserve)
            except (MemoryError, ValueError):
                context.checkpoint()
            finally:
                if encoded is not None:
                    encoded.close()

    def close(self) -> None:
        for charges in self.decoded.values():
            charges.close()
        self.decoded.clear()
        self.leases.clear()
        self.events.clear()
