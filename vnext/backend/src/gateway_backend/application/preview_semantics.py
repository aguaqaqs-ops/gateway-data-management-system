"""Current server-owned semantic identity for new Preview work and Submit acceptance."""

from gateway_backend.capabilities.business_navigation.contracts import CONTRACT_VERSION
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_MODEL_VERSION,
    V1_RISK_RULE_SPECS,
    RiskRulesetSnapshot,
)


def current_preview_capabilities() -> dict[str, str]:
    snapshot = RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS)
    assert snapshot.risk_ruleset_digest is not None
    return {
        "risk_model": RISK_MODEL_VERSION,
        "risk_ruleset_digest": snapshot.risk_ruleset_digest.value,
        "business_navigation": CONTRACT_VERSION,
    }
