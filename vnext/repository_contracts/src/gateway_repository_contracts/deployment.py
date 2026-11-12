"""Authenticated deployment identity; distinct from readiness."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

DeploymentIdentityString = Annotated[str,
    StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]


class DeploymentIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    environment_id: DeploymentIdentityString
    group_id: DeploymentIdentityString
    storage_digest: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
