"""Public value factories/constructors; recovered from archived specifications.

These verify existing invariants with real domain values, not mocked policy.
Username/Email/Password are Identity-owned IAM account values. Existing cases
remain in this owning suite; only value-object imports changed during relocation.
"""

import pytest

from contexts.iam.domain.identity.username import InvalidUsernameValue, Username
from contexts.iam.domain.identity.value_objects import (
    Email, InvalidRegistrationValue, Password,
)


@pytest.mark.parametrize("factory,raw,rejection", [
    (Username.from_input, "x", InvalidUsernameValue("invalid_username")),
    (Email.from_input, "bad-email", InvalidRegistrationValue("invalid_email")),
    (Password.from_input, "short", InvalidRegistrationValue("invalid_password")),
], ids=["username", "email", "password"])
def test_invalid_input_returns_typed_rejection(factory, raw, rejection):
    assert factory(raw) == rejection


@pytest.mark.parametrize("length,accepted", [
    (2, False), (3, True), (30, True), (31, False),
], ids=["below-minimum", "minimum", "maximum", "above-maximum"])
def test_username_length_boundaries(length, accepted):
    raw = "a" * length

    result = Username.from_input(raw)

    if accepted:
        assert isinstance(result, Username)
        assert result.value == raw
    else:
        assert result == InvalidUsernameValue("invalid_username")


@pytest.mark.parametrize("length,accepted", [
    (14, False), (15, True), (128, True), (129, False),
], ids=["below-minimum", "minimum", "maximum", "above-maximum"])
def test_password_length_boundaries(length, accepted):
    raw = "a" * length

    result = Password.from_input(raw)

    if accepted:
        assert isinstance(result, Password)
        assert result.value == raw
    else:
        assert result == InvalidRegistrationValue("invalid_password")


@pytest.mark.parametrize("password", [
    "Long Password123!", " LongPassword123!", "LongPassword123! ",
    "Long\tPassword123!", "Long\nPassword123!", "Long\u00a0Password123!",
], ids=["space", "leading-space", "trailing-space", "tab", "newline", "nbsp"])
def test_password_whitespace_returns_typed_rejection(password):
    assert Password.from_input(password) == InvalidRegistrationValue("invalid_password")


@pytest.mark.parametrize("constructor,raw", [
    (Username, "Alice"),
    (Email, " ALICE@example.com "),
    (Password, "short"),
], ids=["username", "email", "password"])
def test_direct_construction_cannot_bypass_validating_factories(constructor, raw):
    with pytest.raises(TypeError):
        constructor(raw)


def test_valid_password_is_not_exposed_in_representation():
    password = Password.from_input("LongPassword123!")

    assert isinstance(password, Password)
    assert "LongPassword123!" not in repr(password)
