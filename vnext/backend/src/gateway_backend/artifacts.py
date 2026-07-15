from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    digest: str
    media_type: str
    size_bytes: int


def artifact_ref(payload: bytes, media_type: str) -> ArtifactRef:
    return ArtifactRef(
        digest=f"sha256:{sha256(payload).hexdigest()}",
        media_type=media_type,
        size_bytes=len(payload),
    )
