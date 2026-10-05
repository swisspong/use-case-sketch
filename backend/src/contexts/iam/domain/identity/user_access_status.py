"""Account access state belongs to identity, not authentication credentials."""

from dataclasses import dataclass
from enum import Enum
from typing import Union


@dataclass(frozen=True)
class InvalidUserAccessStatus:
    """Expected input rejection; no invalid access-state object is constructed."""


class UserAccessStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"

    @classmethod
    def parse(cls, raw: object) -> Union["UserAccessStatus", InvalidUserAccessStatus]:
        """Accept exact values only; return a typed rejection, never normalize."""
        if isinstance(raw, str):
            if raw == cls.ACTIVE.value:
                return cls.ACTIVE
            if raw == cls.SUSPENDED.value:
                return cls.SUSPENDED
        return InvalidUserAccessStatus()
