"""Neutral, bounded Risk candidate values; current control stays in the evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from hashlib import sha256
from typing import TypeAlias

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.risk_evaluation._facts import ExtractedRiskFacts
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_CONTRACT_VERSION,
    RiskEvaluationInput,
    RiskExecutionPolicy,
    RiskOperationPort,
    RiskReservationPort,
    RiskRuleId,
    RiskTarget,
    RiskTargetType,
    risk_ruleset_document,
)


RISK_CANDIDATES_FORMAT = "risk-table-candidates/v1"
# These are optional retention bounds, never limits on accepted Risk results.
MAX_CANDIDATE_BYTES = 16 * 1024**2
_KEY_RESERVATION_BYTES = 16 * 1024**2


@dataclass(frozen=True, slots=True)
class RiskCandidateInputV1:
    """Complete comparison task plus the pure facts/rules read by the evaluator.

    The comparison task identifies the complete neutral records, including their
    detail policy. Closure refs and the successful validation of a prior closure
    are outer bindings; CHECK_RECORDS_CLOSURE always checks the current request.
    Time, remaining caps and annotation numbering are current execution control.
    """

    comparison_task_digest: str
    facts_jcs: bytes
    ruleset_jcs: bytes
    options_jcs: bytes
    artifact_policy_jcs: bytes
    policy_version: str

    def task_digest(self) -> str:
        document = {
            "artifact_policy": json.loads(self.artifact_policy_jcs),
            "comparison_task_digest": self.comparison_task_digest,
            "facts": json.loads(self.facts_jcs),
            "format": RISK_CANDIDATES_FORMAT,
            "options": json.loads(self.options_jcs),
            "policy_version": self.policy_version,
            "risk_contract_version": RISK_CONTRACT_VERSION,
            "ruleset": json.loads(self.ruleset_jcs),
        }
        raw = canonicalize_json_value(document)
        return "sha256:" + sha256(b"risk-table-candidates/v1\0" + raw).hexdigest()


@dataclass(frozen=True, slots=True)
class RiskEmitEvent:
    rule_id: RiskRuleId
    target: RiskTarget
    evidence: tuple[tuple[str, str | int | bool | None], ...] = ()

    def neutral(self) -> RiskEmitEvent:
        return replace(self, target=replace(self.target, table_name=None))

    def bind_target(self, table_name: str) -> RiskTarget:
        return replace(self.target, table_name=table_name)


@dataclass(frozen=True, slots=True)
class RiskCheckRecordsClosure:
    """Recheck the current closure at exactly this point in the rule sequence."""


RiskCandidateEvent: TypeAlias = RiskEmitEvent | RiskCheckRecordsClosure
CHECK_RECORDS_CLOSURE = RiskCheckRecordsClosure()


def _input_upper(value: object) -> int:
    """Conservative metadata admission without first building a JSON graph."""
    if isinstance(value, str):
        return 256 + len(value) * 256
    if isinstance(value, bytes):
        return 256 + len(value) * 32
    if isinstance(value, (tuple, list)):
        total = 256
        for item in value:
            total += _input_upper(item)
            if total > _KEY_RESERVATION_BYTES:
                break
        return total
    if is_dataclass(value) and not isinstance(value, type):
        total = 1024
        for descriptor in fields(value):
            total += _input_upper(getattr(value, descriptor.name))
            if total > _KEY_RESERVATION_BYTES:
                break
        return total
    return 256


def optional_candidate_input(
    item: ExtractedRiskFacts,
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    comparison_task_digest: str,
    operation: RiskOperationPort | None,
) -> tuple[RiskCandidateInputV1 | None, RiskReservationPort | None]:
    """Admit a canonical key, or leave the unchanged lazy evaluator uncached."""
    if operation is None or item.composite_signal:
        return None, None
    upper = 64 * 1024 + sum(_input_upper(value) for value in (
        comparison_task_digest, item.comparison_facts,
        item.table_fact.diagnostics,
        evaluation_input.comparison_facts.diagnostics,
        evaluation_input.risk_ruleset, evaluation_input.risk_options,
        evaluation_input.artifact_policy,
    ))
    if upper > _KEY_RESERVATION_BYTES:
        return None, None
    try:
        charge = operation.memory.reserve(_KEY_RESERVATION_BYTES)
    except MemoryError:
        return None, None
    try:
        facts = item.comparison_facts.to_document()
        # These fields bind publication/authority rather than pure rule input.
        for name in ("comparison_digest", "table_name", "records_ref"):
            del facts[name]
        facts.update({
            "comparison_failed": item.comparison_failed,
            "content_changed": item.table_fact.content_changed,
            "ordered_unsupported": item.ordered_unsupported,
            "pair_diagnostics": list(evaluation_input.comparison_facts.diagnostics),
            "row_count_before": item.table_fact.row_count_before,
            "row_count_current": item.table_fact.row_count_current,
            "suppressed_added_count": item.table_fact.suppressed_added_count,
            "suppressed_deleted_count": item.table_fact.suppressed_deleted_count,
            "table_diagnostics": list(item.table_fact.diagnostics),
            "uncovered_targets": list(item.uncovered_targets),
        })
        candidate = RiskCandidateInputV1(
            comparison_task_digest=comparison_task_digest,
            facts_jcs=canonicalize_json_value(facts),
            ruleset_jcs=canonicalize_json_value(risk_ruleset_document(evaluation_input.risk_ruleset)),
            options_jcs=canonicalize_json_value(evaluation_input.risk_options.to_document()),
            artifact_policy_jcs=canonicalize_json_value(evaluation_input.artifact_policy.to_document()),
            policy_version=policy.policy_version,
        )
        actual = 2048 + sum(len(value) * 16 for value in (
            candidate.facts_jcs, candidate.ruleset_jcs, candidate.options_jcs,
            candidate.artifact_policy_jcs,
        ))
        if actual > _KEY_RESERVATION_BYTES:
            charge.close()
            return None, None
        charge.shrink_to(actual)
        return candidate, charge
    except (ValueError, OverflowError):
        charge.close()
        return None, None
    except BaseException:
        charge.close()
        raise


@dataclass(slots=True)
class EncodedRiskCandidates:
    raw: bytes
    charge: RiskReservationPort

    def close(self) -> None:
        self.raw = b""
        self.charge.close()


@dataclass(slots=True)
class DecodedRiskCandidates:
    events: tuple[RiskCandidateEvent, ...]
    charge: RiskReservationPort

    def close(self) -> None:
        self.events = ()
        self.charge.close()


def _event_document(event: RiskCandidateEvent, ordinal: int) -> dict[str, object]:
    if isinstance(event, RiskCheckRecordsClosure):
        return {"kind": "CHECK_RECORDS_CLOSURE", "ordinal": ordinal}
    if not isinstance(event, RiskEmitEvent):
        raise ValueError("invalid risk candidate event")
    target = event.target.to_document()
    del target["table_name"]
    return {
        "evidence": [[name, value] for name, value in event.evidence],
        "kind": "EMIT",
        "ordinal": ordinal,
        "rule_id": event.rule_id.value,
        "target": target,
    }


def encode_risk_candidates(
    events: tuple[RiskCandidateEvent, ...], task_digest: str,
    operation: RiskOperationPort,
) -> EncodedRiskCandidates | None:
    """Encode only a naturally completed sequence; failure to retain is a miss.

    Iterate events rather than constructing another whole list of dictionaries.
    Both temporary encoding and retained bytes are admitted before allocation.
    """
    upper = 4096 + len(task_digest) * 32
    for event in events:
        upper += _input_upper(event)
        if upper > MAX_CANDIDATE_BYTES:
            return None
    try:
        charge = operation.memory.reserve(upper * 4)
    except MemoryError:
        return None
    try:
        raw = bytearray(b'{"complete":true,"events":[')
        for index, event in enumerate(events):
            if index % 1024 == 0:
                operation.checkpoint()
            if index:
                raw.extend(b",")
            raw.extend(canonicalize_json_value(_event_document(event, index)))
        raw.extend(b'],"format":')
        raw.extend(canonicalize_json_value(RISK_CANDIDATES_FORMAT))
        raw.extend(b',"task_digest":')
        raw.extend(canonicalize_json_value(task_digest))
        raw.extend(b"}")
        if len(raw) > MAX_CANDIDATE_BYTES:
            charge.close()
            return None
        result = EncodedRiskCandidates(bytes(raw), charge)
        charge.shrink_to(len(raw) * 2 + 1024)
        return result
    except BaseException:
        charge.close()
        raise


_TARGET_KEYS = frozenset({
    "target_type", "row_identity", "before_row_identity", "current_row_identity",
    "changed_columns", "position", "position_range", "coverage",
})


def _target_from_document(value: object) -> RiskTarget:
    if not isinstance(value, dict) or set(value) != _TARGET_KEYS:
        raise ValueError("invalid neutral risk target")
    columns = value["changed_columns"]
    position_range = value["position_range"]
    if not isinstance(columns, list):
        raise ValueError("invalid neutral changed columns")
    if position_range is not None and (
        not isinstance(position_range, list) or len(position_range) != 2
    ):
        raise ValueError("invalid neutral position range")
    def digest(name: str) -> DigestRef | None:
        item = value[name]
        if item is None:
            return None
        if type(item) is not str:
            raise ValueError("invalid neutral risk identity")
        return DigestRef(item)
    return RiskTarget(
        target_type=RiskTargetType(value["target_type"]),
        row_identity=digest("row_identity"),
        before_row_identity=digest("before_row_identity"),
        current_row_identity=digest("current_row_identity"),
        changed_columns=tuple(columns),
        position=value["position"],
        position_range=None if position_range is None else (position_range[0], position_range[1]),
        coverage=value["coverage"],
    )


def decode_risk_candidates(
    raw: bytes, task_digest: str, operation: RiskOperationPort,
) -> DecodedRiskCandidates:
    if len(raw) > MAX_CANDIDATE_BYTES:
        raise ValueError("risk candidate payload exceeds retention bound")
    charge = operation.memory.reserve(8192 + len(raw) * 64)
    try:
        document = json.loads(raw)
        if (not isinstance(document, dict)
                or set(document) != {"complete", "events", "format", "task_digest"}
                or document["complete"] is not True
                or document["format"] != RISK_CANDIDATES_FORMAT
                or document["task_digest"] != task_digest
                or not isinstance(document["events"], list)
                or canonicalize_json_value(document) != raw):
            raise ValueError("invalid risk candidate envelope")
        events: list[RiskCandidateEvent] = []
        for index, value in enumerate(document["events"]):
            if index % 1024 == 0:
                operation.checkpoint()
            if (not isinstance(value, dict) or type(value.get("ordinal")) is not int
                    or value["ordinal"] != index):
                raise ValueError("invalid risk candidate ordinal")
            if value.get("kind") == "CHECK_RECORDS_CLOSURE":
                if set(value) != {"kind", "ordinal"}:
                    raise ValueError("invalid risk closure event")
                events.append(CHECK_RECORDS_CLOSURE)
                continue
            if (value.get("kind") != "EMIT"
                    or set(value) != {"kind", "ordinal", "rule_id", "target", "evidence"}
                    or not isinstance(value["evidence"], list)):
                raise ValueError("invalid risk emit event")
            evidence: list[tuple[str, str | int | bool | None]] = []
            for pair in value["evidence"]:
                if (not isinstance(pair, list) or len(pair) != 2
                        or type(pair[0]) is not str or not pair[0]
                        or (pair[1] is not None and type(pair[1]) not in {str, int, bool})):
                    raise ValueError("invalid risk candidate evidence")
                evidence.append((pair[0], pair[1]))
            events.append(RiskEmitEvent(
                RiskRuleId(value["rule_id"]), _target_from_document(value["target"]),
                tuple(evidence),
            ))
        return DecodedRiskCandidates(tuple(events), charge)
    except BaseException:
        charge.close()
        raise
