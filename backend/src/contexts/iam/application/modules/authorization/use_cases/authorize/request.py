"""Access request; transport objects and caller-supplied roles are excluded."""

from dataclasses import dataclass, field
from enum import Enum


class AccessRequirement(str, Enum):
    """Selected by trusted server-side endpoint configuration, not client input."""

    AUTHENTICATED = "authenticated"
    ADMIN = "admin"


@dataclass(frozen=True)
class AuthorizeRequest:
    token: str = field(repr=False)
