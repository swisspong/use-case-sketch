"""User login behavior through the real Input Boundary and UserAccount.

Shared contract failures/scope timing live in test_login_contracts.py.
Production adapters and suspension/barrier guarantees remain deferred.
"""

from contextlib import AbstractContextManager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, create_autospec

import pytest

from contexts.iam.application.authentication_ports import (
    AccountLookupError, IssuedToken, LoginGrantStore,
    TokenIssuer, TokenIssuanceError,
)
from contexts.iam.application.password_ports import (
    PasswordVerificationError, PasswordVerifier,
)
from contexts.iam.application.use_cases.login.input_boundary import LoginInputBoundary
from contexts.iam.application.use_cases.login.interactor import LoginInteractor
from contexts.iam.application.use_cases.login.output_boundary import LoginOutputBoundary
from contexts.iam.application.use_cases.login.ports import LoginAccountStore
from contexts.iam.application.use_cases.login.request import LoginRequest
from contexts.iam.application.use_cases.login.response import LoginFailure, LoginSuccess
from contexts.iam.domain.identity.user_account import UserAccount
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email


@pytest.fixture
def login_flow():
    account = UserAccount.from_persisted(
        user_id="user-1", username=Username.from_input("alice"),
        email=Email.from_input("alice@example.com"), password_hash="stored-hash",
        status=UserAccessStatus.ACTIVE, admin_eligible=False,
        version=9, credential_generation=7,
    )
    assert isinstance(account, UserAccount)
    accounts = create_autospec(LoginAccountStore, instance=True, spec_set=True)
    accounts.find_by_username.return_value = account
    passwords = create_autospec(PasswordVerifier, instance=True, spec_set=True)
    passwords.verify.return_value = True
    passwords.verify_missing.return_value = None
    tokens = create_autospec(TokenIssuer, instance=True, spec_set=True)
    tokens.issue.return_value = IssuedToken("issued-token")
    output = create_autospec(LoginOutputBoundary, instance=True, spec_set=True)
    grants = create_autospec(LoginGrantStore, instance=True, spec_set=True)
    scope = MagicMock(spec=AbstractContextManager)
    scope.__enter__.return_value = account
    scope.__exit__.return_value = False
    grants.protect.return_value = scope
    boundary: LoginInputBoundary = LoginInteractor(
        accounts, passwords, tokens, output, grants=grants,
    )
    return SimpleNamespace(
        accounts=accounts, passwords=passwords, tokens=tokens, output=output,
        grants=grants, scope=scope, boundary=boundary,
    )


def test_valid_credentials_receive_token_bound_to_lookup_generation(login_flow) -> None:
    flow = login_flow
    returned = flow.boundary.execute(LoginRequest(username="alice", password="correct-password"))

    assert returned is None
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("correct-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_called_once_with(user_id="user-1")
    flow.tokens.issue.assert_called_once_with(
        user_id="user-1", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(LoginSuccess(token="issued-token"))


def test_unknown_username_is_rejected_after_dummy_verification(login_flow) -> None:
    flow = login_flow
    flow.accounts.find_by_username.return_value = None
    returned = flow.boundary.execute(LoginRequest(username="alice", password="submitted-password"))

    assert returned is None
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_called_once_with("submitted-password")
    flow.output.present.assert_called_once_with(LoginFailure(code="invalid_credentials"))
    flow.tokens.issue.assert_not_called()
    flow.grants.protect.assert_not_called()


def test_malformed_username_is_rejected_after_dummy_verification(login_flow) -> None:
    flow = login_flow
    returned = flow.boundary.execute(LoginRequest(username="!bad", password="submitted-password"))

    assert returned is None
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_called_once_with("submitted-password")
    flow.output.present.assert_called_once_with(LoginFailure(code="invalid_credentials"))
    flow.accounts.find_by_username.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.grants.protect.assert_not_called()


def test_wrong_password_is_rejected_without_issuing_token(login_flow) -> None:
    flow = login_flow
    flow.passwords.verify.return_value = False
    returned = flow.boundary.execute(LoginRequest(username="alice", password="wrong-password"))

    assert returned is None
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("wrong-password", "stored-hash")
    flow.output.present.assert_called_once_with(LoginFailure(code="invalid_credentials"))
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.grants.protect.assert_not_called()


def test_mixed_case_username_logs_in_to_registered_account(login_flow) -> None:
    flow = login_flow
    returned = flow.boundary.execute(LoginRequest(username="Alice", password="correct-password"))

    assert returned is None
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("correct-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_called_once_with(user_id="user-1")
    flow.tokens.issue.assert_called_once_with(
        user_id="user-1", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(LoginSuccess(token="issued-token"))


def test_account_lookup_failure_propagates_without_downstream_effects(login_flow) -> None:
    flow = login_flow
    failure = AccountLookupError("account storage unavailable")
    flow.accounts.find_by_username.side_effect = failure

    with pytest.raises(AccountLookupError) as caught:
        flow.boundary.execute(LoginRequest(username="Alice", password="submitted-password"))

    assert caught.value is failure
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


def test_password_verification_failure_propagates_without_issuing_token(login_flow) -> None:
    flow = login_flow
    failure = PasswordVerificationError("verification backend unavailable")
    flow.passwords.verify.side_effect = failure

    with pytest.raises(PasswordVerificationError) as caught:
        flow.boundary.execute(LoginRequest(username="alice", password="submitted-password"))

    assert caught.value is failure
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


def test_dummy_verification_failure_propagates_without_presenting_rejection(login_flow) -> None:
    flow = login_flow
    flow.accounts.find_by_username.return_value = None
    failure = PasswordVerificationError("dummy verification unavailable")
    flow.passwords.verify_missing.side_effect = failure

    with pytest.raises(PasswordVerificationError) as caught:
        flow.boundary.execute(LoginRequest(username="alice", password="submitted-password"))

    assert caught.value is failure
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify_missing.assert_called_once_with("submitted-password")
    flow.passwords.verify.assert_not_called()
    flow.grants.protect.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


def test_token_issuance_failure_propagates_without_presenting_success(login_flow) -> None:
    flow = login_flow
    failure = TokenIssuanceError("issuer unavailable")
    flow.tokens.issue.side_effect = failure

    with pytest.raises(TokenIssuanceError) as caught:
        flow.boundary.execute(LoginRequest(username="alice", password="correct-password"))

    assert caught.value is failure
    flow.accounts.find_by_username.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("correct-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_called_once_with(user_id="user-1")
    flow.tokens.issue.assert_called_once_with(
        user_id="user-1", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_not_called()
