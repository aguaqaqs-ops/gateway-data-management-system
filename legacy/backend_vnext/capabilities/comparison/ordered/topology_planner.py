from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .models import OrderedEntityKeyKind, OrderedPreparedRow


ORDERED_PREPROCESS_NONE = "NONE"
DEGRADE_AMBIGUOUS_MOVE_PLAN = "ORDERED_AMBIGUOUS_MOVE_PLAN"

PLANNER_MODE_PURE_LOCAL = "PURE_LOCAL"
PLANNER_MODE_SHIFT_ONLY = "SHIFT_ONLY"
PLANNER_MODE_LOCAL_TOPOLOGY_CHANGED = "LOCAL_TOPOLOGY_CHANGED"
PLANNER_MODE_LARGE_TOPOLOGY_CHANGED = "LARGE_TOPOLOGY_CHANGED"
PLANNER_MODE_INPUT_INVALID = "INPUT_INVALID"


@dataclass(frozen=True, slots=True)
class _Prescan:
    shared_real_keys: tuple[str, ...]
    inserted_real_keys: tuple[str, ...]
    deleted_real_keys: tuple[str, ...]
    content_changed_keys: tuple[str, ...]
    position_changed_keys: tuple[str, ...]
    old_real_order: tuple[str, ...]
    new_real_order: tuple[str, ...]
    old_common_order: tuple[str, ...]
    new_common_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TopologyCore:
    prefix_keys: tuple[str, ...]
    old_order: tuple[str, ...]
    new_order: tuple[str, ...]
    suffix_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BackboneCandidate:
    backbone_keys: tuple[str, ...]
    backbone_length: int
    blank_interval_churn: int
    real_row_topology_distance: int
    new_topology_sequence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PlannerDecision:
    planner_mode: str
    planner_budget: dict[str, Any]
    planner_diagnostics: dict[str, Any]
    topology_core: _TopologyCore
    backbone_keys: tuple[str, ...]
    moved_keys: tuple[str, ...]
    degrade_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _OrderedTopologyPlanner:
    max_backbone_candidates: int = 2048
    small_core_threshold: int = 512
    large_core_threshold: int = 5000
    planner_step_budget: int = 1_000_000
    planner_time_budget_ms: int = 1000

    def plan(
        self,
        *,
        prescan: _Prescan,
        prepared_before: list[OrderedPreparedRow] | None = None,
        prepared_after: list[OrderedPreparedRow] | None = None,
    ) -> _PlannerDecision:
        planner_budget = self._planner_budget()
        planner_mode = self._initial_planner_mode(prescan)
        topology_core = _TopologyCore(
            prefix_keys=(),
            old_order=(),
            new_order=(),
            suffix_keys=(),
        )
        planner_diagnostics: dict[str, Any] = {
            "planner_used": False,
            "overflow_reason": None,
            "core_size": 0,
            "candidate_count": 0,
            "step_count": 0,
            "elapsed_ms": 0.0,
        }
        chosen_backbone_keys = prescan.old_common_order
        moved_keys: tuple[str, ...] = ()
        degrade_reason: str | None = None

        if planner_mode == PLANNER_MODE_LOCAL_TOPOLOGY_CHANGED:
            topology_core = self._shrink_topology_core(
                old_common_order=prescan.old_common_order,
                new_common_order=prescan.new_common_order,
            )
            planner_diagnostics["planner_used"] = True
            planner_diagnostics["core_size"] = len(topology_core.old_order)
            move_candidate = self._unique_move_candidate(
                old_common_order=prescan.old_common_order,
                new_common_order=prescan.new_common_order,
            )
            if move_candidate is None:
                backbone_decision = self._plan_backbone(
                    topology_core=topology_core,
                    prescan=prescan,
                    prepared_before=prepared_before,
                    prepared_after=prepared_after,
                )
                if backbone_decision is None:
                    planner_diagnostics["overflow_reason"] = DEGRADE_AMBIGUOUS_MOVE_PLAN
                    degrade_reason = DEGRADE_AMBIGUOUS_MOVE_PLAN
                else:
                    chosen_backbone_keys, moved_keys, p2_diagnostics = backbone_decision
                    planner_diagnostics.update(p2_diagnostics)
                    planner_diagnostics["overflow_reason"] = None
            else:
                planner_diagnostics["candidate_count"] = 1
                chosen_backbone_keys = tuple(
                    row_key for row_key in prescan.old_common_order if row_key != move_candidate
                )
                moved_keys = (move_candidate,)

        return _PlannerDecision(
            planner_mode=planner_mode,
            planner_budget=planner_budget,
            planner_diagnostics=planner_diagnostics,
            topology_core=topology_core,
            backbone_keys=chosen_backbone_keys,
            moved_keys=moved_keys,
            degrade_reason=degrade_reason,
        )

    def _plan_backbone(
        self,
        *,
        topology_core: _TopologyCore,
        prescan: _Prescan,
        prepared_before: list[OrderedPreparedRow] | None,
        prepared_after: list[OrderedPreparedRow] | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]] | None:
        if prepared_before is None or prepared_after is None:
            return None
        core_size = max(len(topology_core.old_order), len(topology_core.new_order))
        if core_size > self.large_core_threshold:
            return None
        old_rank = {row_key: index + 1 for index, row_key in enumerate(prescan.old_common_order)}
        new_rank = {row_key: index + 1 for index, row_key in enumerate(prescan.new_common_order)}
        candidates, overflow, stats = self._p2_build_backbone_candidates(
            topology_core=topology_core,
            old_common_order=prescan.old_common_order,
            prepared_before=prepared_before,
            prepared_after=prepared_after,
            old_rank=old_rank,
            new_rank=new_rank,
        )
        if overflow:
            return None
        chosen = self._p2_choose_backbone(candidates)
        if chosen is None:
            stats["overflow_reason"] = DEGRADE_AMBIGUOUS_MOVE_PLAN
            return None
        backbone_set = set(chosen.backbone_keys)
        moved_keys = tuple(row_key for row_key in prescan.old_common_order if row_key not in backbone_set)
        if not moved_keys:
            stats["overflow_reason"] = DEGRADE_AMBIGUOUS_MOVE_PLAN
            return None
        stats["chosen_backbone_length"] = chosen.backbone_length
        stats["chosen_blank_interval_churn"] = chosen.blank_interval_churn
        stats["chosen_real_row_topology_distance"] = chosen.real_row_topology_distance
        return chosen.backbone_keys, moved_keys, stats

    @staticmethod
    def _initial_planner_mode(prescan: _Prescan) -> str:
        if not prescan.position_changed_keys:
            return PLANNER_MODE_PURE_LOCAL
        if prescan.old_common_order == prescan.new_common_order:
            return PLANNER_MODE_SHIFT_ONLY
        return PLANNER_MODE_LOCAL_TOPOLOGY_CHANGED

    @staticmethod
    def _unique_move_candidate(
        *,
        old_common_order: tuple[str, ...],
        new_common_order: tuple[str, ...],
    ) -> str | None:
        if len(old_common_order) != len(new_common_order):
            return None

        first_mismatch: int | None = None
        for index, (old_key, new_key) in enumerate(zip(old_common_order, new_common_order, strict=True)):
            if old_key != new_key:
                first_mismatch = index
                break
        if first_mismatch is None:
            return None

        candidates: list[str] = []
        seen: set[str] = set()
        for candidate in (
            old_common_order[first_mismatch],
            new_common_order[first_mismatch],
        ):
            if candidate in seen:
                continue
            seen.add(candidate)
            if not _orders_equal_without_candidate(
                old_common_order=old_common_order,
                new_common_order=new_common_order,
                candidate=candidate,
            ):
                continue
            candidates.append(candidate)
            if len(candidates) > 1:
                return None
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _shrink_topology_core(
        *,
        old_common_order: tuple[str, ...],
        new_common_order: tuple[str, ...],
    ) -> _TopologyCore:
        prefix_len = 0
        order_len = min(len(old_common_order), len(new_common_order))
        while prefix_len < order_len and old_common_order[prefix_len] == new_common_order[prefix_len]:
            prefix_len += 1

        suffix_len = 0
        while (
            suffix_len < order_len - prefix_len
            and old_common_order[len(old_common_order) - 1 - suffix_len]
            == new_common_order[len(new_common_order) - 1 - suffix_len]
        ):
            suffix_len += 1

        old_core_end = len(old_common_order) - suffix_len if suffix_len else len(old_common_order)
        new_core_end = len(new_common_order) - suffix_len if suffix_len else len(new_common_order)
        return _TopologyCore(
            prefix_keys=old_common_order[:prefix_len],
            old_order=old_common_order[prefix_len:old_core_end],
            new_order=new_common_order[prefix_len:new_core_end],
            suffix_keys=old_common_order[old_core_end:],
        )

    def _planner_budget(self) -> dict[str, Any]:
        return {
            "max_backbone_candidates": self.max_backbone_candidates,
            "small_core_threshold": self.small_core_threshold,
            "large_core_threshold": self.large_core_threshold,
            "planner_step_budget": self.planner_step_budget,
            "planner_time_budget_ms": self.planner_time_budget_ms,
        }

    # P2 planner seam: block-move / global topology planning stays isolated here.

    def _p2_build_backbone_candidates(
        self,
        *,
        topology_core: _TopologyCore,
        old_common_order: tuple[str, ...],
        prepared_before: list[OrderedPreparedRow],
        prepared_after: list[OrderedPreparedRow],
        old_rank: dict[str, int],
        new_rank: dict[str, int],
    ) -> tuple[list[_BackboneCandidate], bool, dict[str, Any]]:
        started_at = time.monotonic()
        stats: dict[str, Any] = {
            "planner_used": True,
            "overflow_reason": None,
            "core_size": len(topology_core.old_order),
            "candidate_count": 0,
            "step_count": 0,
            "elapsed_ms": 0.0,
        }
        core_new_rank = {row_key: index + 1 for index, row_key in enumerate(topology_core.new_order)}
        permutation = [core_new_rank[row_key] for row_key in topology_core.old_order]
        lis_index_sequences, overflow = self._p2_bounded_lis_index_sequences(
            values=permutation,
            started_at=started_at,
            stats=stats,
        )
        if overflow:
            stats["elapsed_ms"] = self._elapsed_ms(started_at)
            return [], True, stats
        seen_backbones: set[tuple[str, ...]] = set()
        candidates: list[_BackboneCandidate] = []
        for index_sequence in lis_index_sequences:
            core_backbone_keys = tuple(topology_core.old_order[index] for index in index_sequence)
            backbone_keys = topology_core.prefix_keys + core_backbone_keys + topology_core.suffix_keys
            if backbone_keys in seen_backbones:
                continue
            seen_backbones.add(backbone_keys)
            stats["step_count"] += len(prepared_before) + len(prepared_after)
            if self._p2_planner_budget_exceeded(started_at=started_at, stats=stats):
                stats["elapsed_ms"] = self._elapsed_ms(started_at)
                return candidates, True, stats
            backbone_set = set(backbone_keys)
            distance = sum(
                abs(old_rank[row_key] - new_rank[row_key])
                for row_key in old_common_order
                if row_key not in backbone_set
            )
            candidates.append(
                _BackboneCandidate(
                    backbone_keys=backbone_keys,
                    backbone_length=len(backbone_keys),
                    blank_interval_churn=self._p2_blank_interval_churn(
                        backbone_keys=backbone_keys,
                        prepared_before=prepared_before,
                        prepared_after=prepared_after,
                    ),
                    real_row_topology_distance=distance,
                    new_topology_sequence=tuple(sorted(backbone_keys, key=new_rank.get)),
                )
            )
            stats["candidate_count"] = len(candidates)
        if not candidates:
            stats["overflow_reason"] = "no_backbone_candidates"
            stats["elapsed_ms"] = self._elapsed_ms(started_at)
            return [], True, stats
        stats["elapsed_ms"] = self._elapsed_ms(started_at)
        return candidates, False, stats

    @staticmethod
    def _p2_choose_backbone(candidates: list[_BackboneCandidate]) -> _BackboneCandidate | None:
        if not candidates:
            return None
        sorted_candidates = sorted(
            candidates,
            key=lambda candidate: (
                -candidate.backbone_length,
                candidate.blank_interval_churn,
                candidate.real_row_topology_distance,
                candidate.new_topology_sequence,
            ),
        )
        best = sorted_candidates[0]
        tied = [
            candidate
            for candidate in sorted_candidates
            if (
                candidate.backbone_length,
                candidate.blank_interval_churn,
                candidate.real_row_topology_distance,
            )
            == (
                best.backbone_length,
                best.blank_interval_churn,
                best.real_row_topology_distance,
            )
        ]
        if len(tied) != 1:
            return None
        return best

    def _p2_blank_interval_churn(
        self,
        *,
        backbone_keys: tuple[str, ...],
        prepared_before: list[OrderedPreparedRow],
        prepared_after: list[OrderedPreparedRow],
    ) -> int:
        before_counts_by_interval = self._blank_signature_counts_by_interval(
            rows=prepared_before,
            backbone_keys=set(backbone_keys),
        )
        after_counts_by_interval = self._blank_signature_counts_by_interval(
            rows=prepared_after,
            backbone_keys=set(backbone_keys),
        )
        churn = 0
        for interval_index in set(before_counts_by_interval) | set(after_counts_by_interval):
            before_counts = before_counts_by_interval.get(interval_index, {})
            after_counts = after_counts_by_interval.get(interval_index, {})
            for signature in set(before_counts) | set(after_counts):
                churn += abs(before_counts.get(signature, 0) - after_counts.get(signature, 0))
        return churn

    def _p2_bounded_lis_index_sequences(
        self,
        *,
        values: list[int],
        started_at: float,
        stats: dict[str, Any],
    ) -> tuple[list[tuple[int, ...]], bool]:
        if not values:
            return [()], False
        lengths = [1] * len(values)
        predecessors: list[list[int]] = [[] for _ in values]
        for current in range(len(values)):
            for prev in range(current):
                stats["step_count"] += 1
                if self._p2_planner_budget_exceeded(started_at=started_at, stats=stats):
                    return [], True
                if values[prev] >= values[current]:
                    continue
                candidate_length = lengths[prev] + 1
                if candidate_length > lengths[current]:
                    lengths[current] = candidate_length
                    predecessors[current] = [prev]
                elif candidate_length == lengths[current]:
                    predecessors[current].append(prev)
        max_length = max(lengths)
        endings = [index for index, length in enumerate(lengths) if length == max_length]
        sequences: list[tuple[int, ...]] = []
        seen_sequences: set[tuple[int, ...]] = set()
        stack = [(ending, ()) for ending in reversed(endings)]
        while stack:
            stats["step_count"] += 1
            if self._p2_planner_budget_exceeded(started_at=started_at, stats=stats):
                return [], True
            current_index, suffix = stack.pop()
            current_suffix = (current_index, *suffix)
            previous_indexes = predecessors[current_index]
            if previous_indexes:
                for previous_index in reversed(previous_indexes):
                    stack.append((previous_index, current_suffix))
                continue
            if current_suffix in seen_sequences:
                continue
            seen_sequences.add(current_suffix)
            sequences.append(current_suffix)
            stats["candidate_count"] = len(sequences)
            if len(sequences) > self.max_backbone_candidates:
                stats["overflow_reason"] = "max_backbone_candidates_exceeded"
                return [], True
        if not sequences:
            stats["overflow_reason"] = "no_lis_sequences"
            return [], True
        return sorted(sequences), False

    def _p2_planner_budget_exceeded(self, *, started_at: float, stats: dict[str, Any]) -> bool:
        if self.planner_step_budget >= 0 and stats["step_count"] > self.planner_step_budget:
            stats["overflow_reason"] = "planner_step_budget_exceeded"
            return True
        if self.planner_time_budget_ms >= 0 and self._elapsed_ms(started_at) > self.planner_time_budget_ms:
            stats["overflow_reason"] = "planner_time_budget_exceeded"
            return True
        return False

    @staticmethod
    def _collect_blank_rows_by_interval(
        *,
        rows: list[OrderedPreparedRow],
        backbone_keys: set[str],
        interval_count: int,
    ) -> dict[int, list[OrderedPreparedRow]]:
        buckets: dict[int, list[OrderedPreparedRow]] = {}
        interval_index = 0
        for row in rows:
            if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE and row.row_key in backbone_keys:
                interval_index += 1
                continue
            if row.entity_key_kind == OrderedEntityKeyKind.PSEUDO_BLANK:
                if interval_index >= interval_count:
                    interval_index = interval_count - 1
                buckets.setdefault(interval_index, []).append(row)
        return buckets

    @staticmethod
    def _blank_signature_counts_by_interval(
        *,
        rows: list[OrderedPreparedRow],
        backbone_keys: set[str],
    ) -> dict[int, dict[tuple[tuple[str, Any], ...], int]]:
        buckets: dict[int, dict[tuple[tuple[str, Any], ...], int]] = {}
        interval_index = 0
        for row in rows:
            if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE and row.row_key in backbone_keys:
                interval_index += 1
                continue
            if row.entity_key_kind != OrderedEntityKeyKind.PSEUDO_BLANK:
                continue
            signature = row.blank_signature or ()
            counts = buckets.setdefault(interval_index, {})
            counts[signature] = counts.get(signature, 0) + 1
        return buckets

    @staticmethod
    def _rows_by_signature(rows: list[OrderedPreparedRow]) -> dict[tuple[tuple[str, Any], ...], list[OrderedPreparedRow]]:
        grouped: dict[tuple[tuple[str, Any], ...], list[OrderedPreparedRow]] = {}
        for row in rows:
            grouped.setdefault(row.blank_signature or (), []).append(row)
        return grouped

    @staticmethod
    def _interval_label(backbone_keys: tuple[str, ...], interval_index: int) -> str:
        if not backbone_keys:
            return "whole"
        if interval_index <= 0:
            return f"head->{backbone_keys[0]}"
        if interval_index >= len(backbone_keys):
            return f"{backbone_keys[-1]}->tail"
        return f"{backbone_keys[interval_index - 1]}->{backbone_keys[interval_index]}"

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((time.monotonic() - started_at) * 1000, 3)


def _orders_equal_without_candidate(
    *,
    old_common_order: tuple[str, ...],
    new_common_order: tuple[str, ...],
    candidate: str,
) -> bool:
    old_index = 0
    new_index = 0
    old_len = len(old_common_order)
    new_len = len(new_common_order)
    while True:
        while old_index < old_len and old_common_order[old_index] == candidate:
            old_index += 1
        while new_index < new_len and new_common_order[new_index] == candidate:
            new_index += 1
        if old_index >= old_len or new_index >= new_len:
            return old_index >= old_len and new_index >= new_len
        if old_common_order[old_index] != new_common_order[new_index]:
            return False
        old_index += 1
        new_index += 1
