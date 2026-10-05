"""Canonical account usernames shared by registration and authentication."""

from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class InvalidUsernameValue:
    code: Literal["invalid_username"]


@dataclass(frozen=True, init=False)
class Username:
    value: str

    def __init__(self, value: str) -> None:
        raise TypeError("Use Username.from_input")

    @classmethod
    def from_input(cls, raw: str) -> "Username | InvalidUsernameValue":
        if not isinstance(raw, str):
            return InvalidUsernameValue("invalid_username")
        value = raw.lower()
        if re.fullmatch(r"[a-z][a-z0-9]{2,29}", value) is None:
            return InvalidUsernameValue("invalid_username")
        instance = object.__new__(cls)
        object.__setattr__(instance, "value", value)
        return instance
