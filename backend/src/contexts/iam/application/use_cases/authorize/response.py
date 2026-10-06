"""Semantic outcomes, not HTTP responses or presentation text.

Invalid/expired/revoked credentials and inaccessible accounts all produce
unauthenticated without disclosing why. A currently authenticated non-admin
requesting admin access receives forbidden. Success discloses only actor identity.
"""

from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class AuthorizeSuccess:
    actor_id: str


@dataclass(frozen=True)
class AuthorizeFailure:
    code: Literal["unauthenticated", "forbidden"]


AuthorizeResult = Union[AuthorizeSuccess, AuthorizeFailure]
