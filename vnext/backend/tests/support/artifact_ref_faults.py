"""Unsupported delivery identities shared across constructor and READY boundaries."""

UNSUPPORTED_DELIVERY_ARTIFACT_IDS = (
    "cache-local", "cache:local", "repository-internal", "flow-state", "preview-token",
    "/tmp/cache/object", "a1:unknown:" + "a" * 64, "a1:export:" + "A" * 64,
)
