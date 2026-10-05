"""IAM account values; factories reject ordinary invalid input as domain results.

Identity owns Email/Password with the same meanings across UserAccount,
registration and password changes. InvalidRegistrationValue retains its established
name/result contract; it is an Identity-owned value rejection, not a use-case outcome.
"""

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from email_validator import EmailNotValidError, validate_email


ValidationCode = Literal["invalid_email", "invalid_password"]
_Code = TypeVar("_Code", bound=ValidationCode)


@dataclass(frozen=True)
class InvalidRegistrationValue(Generic[_Code]):
    code: _Code


_Value = TypeVar("_Value")


def _validated(cls: type[_Value], value: str) -> _Value:
    """Internal constructor; call only after the public factory validates the value."""
    instance = object.__new__(cls)
    object.__setattr__(instance, "value", value)
    return instance


@dataclass(frozen=True, init=False)
class Email:
    value: str

    def __init__(self, value: str) -> None:
        raise TypeError("Use Email.from_input")

    @classmethod
    def from_input(cls, raw: str) -> "Email | InvalidRegistrationValue[Literal['invalid_email']]":
        if not isinstance(raw, str):
            return InvalidRegistrationValue("invalid_email")
        if raw != raw.strip():
            return InvalidRegistrationValue("invalid_email")
        try:
            # DNS deliverability and ownership verification are separate concerns.
            checked = validate_email(raw, check_deliverability=False)
        except EmailNotValidError:
            return InvalidRegistrationValue("invalid_email")
        # Identity comparisons ignore case for the entire address.
        return _validated(cls, checked.normalized.lower())


@dataclass(frozen=True, init=False)
class Password:
    value: str = field(repr=False)

    def __init__(self, value: str) -> None:
        raise TypeError("Use Password.from_input")

    @classmethod
    def from_input(cls, raw: str) -> "Password | InvalidRegistrationValue[Literal['invalid_password']]":
        # Do not strip, normalize, log or return the secret.
        if not isinstance(raw, str) or not 15 <= len(raw) <= 128:
            return InvalidRegistrationValue("invalid_password")
        if any(character.isspace() for character in raw):
            return InvalidRegistrationValue("invalid_password")
        return _validated(cls, raw)
