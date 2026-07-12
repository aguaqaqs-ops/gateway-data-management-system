from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ....core.digests import DigestRef
from ....core.identifiers import canonical_identifier
from ..models import ORDERED_DIFF_CONTRACT_VERSION
from .models import OrderedPreparedRow, OrderedSummary


@dataclass(frozen=True, slots=True)
class OrderedRowsDigestParts:
    side: str
    stable_key_field: str
    position_field: str
    ordered_policy_digest: DigestRef | None
    ordered_row_content_digest: DigestRef

    def __post_init__(self) -> None:
        if not isinstance(self.side, str) or not self.side.strip():
            raise ValueError("side must be a non-empty string")
        object.__setattr__(self, "stable_key_field", canonical_identifier(self.stable_key_field))
        object.__setattr__(self, "position_field", canonical_identifier(self.position_field))
        if self.ordered_policy_digest is not None:
            object.__setattr__(
                self,
                "ordered_policy_digest",
                DigestRef.parse(str(self.ordered_policy_digest)),
            )
        object.__setattr__(
            self,
            "ordered_row_content_digest",
            DigestRef.parse(str(self.ordered_row_content_digest)),
        )


def build_ordered_rows_digest(
    *,
    table_name: str,
    rows: Sequence[OrderedPreparedRow],
    columns: Sequence[str],
    stable_key_field: str,
    position_field: str,
    ordered_policy_digest: DigestRef | str | None,
    side: str,
) -> DigestRef:
    return build_ordered_rows_digest_from_parts(
        table_name=table_name,
        digest_parts=build_ordered_rows_digest_parts(
            rows=rows,
            columns=columns,
            stable_key_field=stable_key_field,
            position_field=position_field,
            ordered_policy_digest=ordered_policy_digest,
            side=side,
        ),
    )


def build_ordered_rows_digest_parts(
    *,
    rows: Sequence[OrderedPreparedRow],
    columns: Sequence[str],
    stable_key_field: str,
    position_field: str,
    ordered_policy_digest: DigestRef | str | None,
    side: str,
) -> OrderedRowsDigestParts:
    canonical_columns = tuple(canonical_identifier(column) for column in columns if canonical_identifier(column))
    ordered_row_content_digest = DigestRef.from_payload(
        {
            "ordered_digest_contract_version": ORDERED_DIFF_CONTRACT_VERSION,
            "side": side,
            "stable_key_field": canonical_identifier(stable_key_field),
            "position_field": canonical_identifier(position_field),
            "ordered_policy_digest": _optional_digest_payload(ordered_policy_digest),
            "rows": [
                {
                    "row_key": row.row_key,
                    "entity_key_kind": row.entity_key_kind.value,
                    "position": row.position,
                    "blank_signature": [
                        [column, value]
                        for column, value in (row.blank_signature or ())
                    ],
                    "values": {
                        column: row.row.get(column)
                        for column in canonical_columns
                        if column in row.row
                    },
                }
                for row in rows
            ],
        }
    )
    return OrderedRowsDigestParts(
        side=side,
        stable_key_field=stable_key_field,
        position_field=position_field,
        ordered_policy_digest=(
            None
            if ordered_policy_digest is None
            else DigestRef.parse(str(ordered_policy_digest))
        ),
        ordered_row_content_digest=ordered_row_content_digest,
    )


def build_ordered_rows_digest_from_parts(
    *,
    table_name: str,
    digest_parts: OrderedRowsDigestParts,
) -> DigestRef:
    if not isinstance(digest_parts, OrderedRowsDigestParts):
        raise TypeError("digest_parts must be OrderedRowsDigestParts")
    return DigestRef.from_payload(
        {
            "ordered_digest_contract_version": ORDERED_DIFF_CONTRACT_VERSION,
            "table_name": canonical_identifier(table_name),
            "side": digest_parts.side,
            "stable_key_field": digest_parts.stable_key_field,
            "position_field": digest_parts.position_field,
            "ordered_policy_digest": _optional_digest_payload(digest_parts.ordered_policy_digest),
            "ordered_row_content_digest": digest_parts.ordered_row_content_digest.to_payload(),
        }
    )


def build_ordered_summary_digest(summary: OrderedSummary) -> DigestRef:
    if not isinstance(summary, OrderedSummary):
        raise TypeError("summary must be an OrderedSummary")
    return DigestRef.from_payload(summary.to_payload())


def build_ordered_table_digest(
    *,
    table_name: str,
    ordered_policy_digest: DigestRef | str | None,
    before_ordered_digest: DigestRef | str | None,
    current_ordered_digest: DigestRef | str | None,
    ordered_summary: OrderedSummary | None,
    replay_guarantee: str,
    table_processing_mode: str,
    ordered_preprocess_applied: str,
) -> DigestRef:
    payload = {
        "table_name": canonical_identifier(table_name),
        "ordered_policy_digest": _optional_digest_payload(ordered_policy_digest),
        "before_ordered_digest": _optional_digest_payload(before_ordered_digest),
        "current_ordered_digest": _optional_digest_payload(current_ordered_digest),
        "ordered_summary": None if ordered_summary is None else ordered_summary.to_payload(),
        "replay_guarantee": replay_guarantee,
        "table_processing_mode": table_processing_mode,
        "ordered_preprocess_applied": ordered_preprocess_applied,
    }
    return DigestRef.from_payload(payload)


def _optional_digest_payload(value: DigestRef | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value.to_payload()
    return DigestRef.parse(str(value)).to_payload()
