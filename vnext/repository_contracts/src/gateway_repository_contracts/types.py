"""Small Pydantic scalar constraints shared by Repository DTOs."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import StringConstraints

BoundedOpaqueString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1024),
]
MediaTypeString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
]
RefNameString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
]
TableNameString: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
]
Sha256String: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
