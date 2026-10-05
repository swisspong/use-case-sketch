"""Shared login/admin-login port contracts through their real Input Boundaries.

Covers local eligibility, lookup/verifier/scope/issuer contract breaches,
generation/lifetime forwarding, failures and post-scope single-outcome delivery.
Mocks return facts/technical results, never execute local domain decisions.
Consumer mocks do not prove production
suspension/barrier enforcement. Use-case-specific behavior stays in owning suites.
"""

from contextlib import AbstractContextManager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call, create_autospec

import pytest

from contexts.iam.application.modules.authentication.ports import (
    AdminLoginAccountStore,
    InvalidLoginAccountResult,
    InvalidTokenIssuanceResult,
    IssuedToken,
    LoginAccountStore,
    LoginGrantRejected,
    LoginGrantStore,
    LoginGrantError,
    InvalidLoginGrantResult,
    TokenIssuer,
)
from contexts.iam.application.modules.credentials.ports import (
    InvalidPasswordVerificationResult, PasswordVerifier,
)
from contexts.iam.application.modules.authentication.use_cases.admin_login.errors import InvalidAdminTokenResult
from contexts.iam.application.modules.authentication.use_cases.admin_login.input_boundary import AdminLoginInputBoundary
from contexts.iam.application.modules.authentication.use_cases.admin_login.interactor import AdminLoginInteractor
from contexts.iam.application.modules.authentication.use_cases.admin_login.output_boundary import AdminLoginOutputBoundary
from contexts.iam.application.modules.authentication.use_cases.admin_login.request import AdminLoginRequest
from contexts.iam.application.modules.authentication.use_cases.admin_login.response import AdminLoginFailure, AdminLoginSuccess
from contexts.iam.application.modules.authentication.use_cases.login.errors import InvalidTokenResult
from contexts.iam.application.modules.authentication.use_cases.login.input_boundary import LoginInputBoundary
from contexts.iam.application.modules.authentication.use_cases.login.interactor import LoginInteractor
from contexts.iam.application.modules.authentication.use_cases.login.output_boundary import LoginOutputBoundary
from contexts.iam.application.modules.authentication.use_cases.login.request import LoginRequest
from contexts.iam.application.modules.authentication.use_cases.login.response import LoginFailure, LoginSuccess
from contexts.iam.domain.identity.user_account import (
    UserAccount,
)
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email


@pytest.mark.parametrize("legacy_error", [
    InvalidTokenResult, InvalidAdminTokenResult,
], ids=["login", "admin-login"])
def test_legacy_token_error_imports_alias_shared_authentication_exception(legacy_error):
    assert legacy_error is InvalidTokenIssuanceResult


def account_snapshot(
    *, status=UserAccessStatus.ACTIVE, admin_eligible=True, generation=7,
    user_id="user-42", username="alice",
):
    return UserAccount.from_persisted(
        user_id=user_id, username=Username.from_input(username),
        email=Email.from_input("alice@example.com"), password_hash="stored-hash",
        status=status, admin_eligible=admin_eligible,
        version=9, credential_generation=generation,
    )


@pytest.fixture(params=["login", "admin_login"])
def flow(request):
    if request.param == "login":
        store_type, output_type = LoginAccountStore, LoginOutputBoundary
        interactor_type, request_type = LoginInteractor, LoginRequest
        success_type, failure_type = LoginSuccess, LoginFailure
        lookup_name = "find_by_username"
    else:
        store_type, output_type = AdminLoginAccountStore, AdminLoginOutputBoundary
        interactor_type, request_type = AdminLoginInteractor, AdminLoginRequest
        success_type, failure_type = AdminLoginSuccess, AdminLoginFailure
        lookup_name = "find_admin_by_username"

    accounts = create_autospec(store_type, instance=True, spec_set=True)
    lookup = getattr(accounts, lookup_name)
    lookup.return_value = account_snapshot(admin_eligible=request.param == "admin_login")
    passwords = create_autospec(PasswordVerifier, instance=True, spec_set=True)
    passwords.verify.return_value = True
    passwords.verify_missing.return_value = None
    tokens = create_autospec(TokenIssuer, instance=True, spec_set=True)
    tokens.issue.return_value = IssuedToken("issued-token")
    output = create_autospec(output_type, instance=True, spec_set=True)
    output.present.return_value = None
    grants = create_autospec(LoginGrantStore, instance=True, spec_set=True)
    scope = MagicMock(spec=AbstractContextManager)
    scope.__enter__.return_value = account_snapshot()
    scope.__exit__.return_value = False
    grants.protect.return_value = scope
    boundary: LoginInputBoundary | AdminLoginInputBoundary = interactor_type(
        accounts, passwords, tokens, output, grants=grants,
    )
    return SimpleNamespace(
        name=request.param, boundary=boundary, lookup=lookup,
        passwords=passwords, tokens=tokens, grants=grants, scope=scope,
        output=output, request=request_type("Alice", "submitted-password"),
        success_type=success_type, failure_type=failure_type,
    )


@pytest.mark.parametrize("status,admin_eligible,allowed_flows", [
    (UserAccessStatus.ACTIVE, False, ("login",)),
    (UserAccessStatus.ACTIVE, True, ("login", "admin_login")),
    (UserAccessStatus.SUSPENDED, False, ()),
    (UserAccessStatus.SUSPENDED, True, ()),
])
def test_login_eligibility_is_decided_by_interactor_from_unfiltered_account(
    flow, status, admin_eligible, allowed_flows,
):
    account = account_snapshot(status=status, admin_eligible=admin_eligible)

    flow.lookup.return_value = account

    assert flow.boundary.execute(flow.request) is None

    flow.lookup.assert_called_once_with("alice")
    if flow.name in allowed_flows:
        flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
        flow.passwords.verify_missing.assert_not_called()
        flow.tokens.issue.assert_called_once_with(
            user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
        )
        flow.output.present.assert_called_once_with(flow.success_type("issued-token"))
    else:
        flow.passwords.verify.assert_not_called()
        flow.passwords.verify_missing.assert_called_once_with("submitted-password")
        flow.tokens.issue.assert_not_called()
        flow.output.present.assert_called_once_with(flow.failure_type("invalid_credentials"))


def test_suspended_current_account_rejects_without_issuance(flow):
    flow.scope.__enter__.return_value = account_snapshot(status=UserAccessStatus.SUSPENDED)

    assert flow.boundary.execute(flow.request) is None

    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_called_once_with(flow.failure_type("invalid_credentials"))


@pytest.mark.parametrize("current", [None, "allowed"])
def test_issuance_is_protected_and_outcome_follows_successful_scope_exit(flow, current):
    """Exercise existing scope logic; real domain decisions, no mocked eligibility."""
    protected = False

    def enter():
        nonlocal protected
        protected = True
        return account_snapshot() if current == "allowed" else None

    def exit_scope(*exc):
        nonlocal protected
        assert protected
        flow.output.present.assert_not_called()
        protected = False
        return False

    def issue(*, user_id, credential_generation, ttl):
        assert protected
        assert (user_id, credential_generation, ttl) == (
            "user-42", 7, timedelta(minutes=15),
        )
        return IssuedToken("protected-token")

    def present(outcome):
        assert not protected
        expected = (
            flow.success_type("protected-token") if current == "allowed"
            else flow.failure_type("invalid_credentials")
        )
        assert outcome == expected

    flow.scope.__enter__.side_effect = enter
    flow.scope.__exit__.side_effect = exit_scope
    flow.tokens.issue.side_effect = issue
    flow.output.present.side_effect = present

    assert flow.boundary.execute(flow.request) is None

    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.scope.__enter__.assert_called_once_with()
    flow.scope.__exit__.assert_called_once_with(None, None, None)
    flow.output.present.assert_called_once()
    if current is None:
        flow.tokens.issue.assert_not_called()
    else:
        flow.tokens.issue.assert_called_once_with(
            user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
        )


def test_login_selects_fifteen_minute_token_lifetime_in_application(flow):
    returned = flow.boundary.execute(flow.request)

    assert returned is None
    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(flow.success_type("issued-token"))


@pytest.mark.parametrize("verdict", ["false", None, 0, 1, [], [True]])
def test_non_bool_password_verdict_is_system_failure_without_issuance(flow, verdict):
    flow.passwords.verify.return_value = verdict

    with pytest.raises(InvalidPasswordVerificationResult):
        flow.boundary.execute(flow.request)

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("account", [
    True,
    "legacy-account",
    SimpleNamespace(user_id="user-99", password_hash="hash", credential_generation=7),
    SimpleNamespace(user_id="untrusted-user-99", password_hash="untrusted-hash"),
])
def test_undeclared_account_result_stops_before_verification_or_issuance(flow, account):
    flow.lookup.return_value = account

    with pytest.raises(TypeError):
        flow.boundary.execute(flow.request)

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


def test_lookup_for_another_username_stops_before_verification_or_issuance(flow):
    """Cover the existing exact-resource binding guard with a real Entity."""
    flow.lookup.return_value = account_snapshot(username="bob")

    with pytest.raises(InvalidLoginAccountResult):
        flow.boundary.execute(flow.request)

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("user_id", ["", " \t\n", None, 42])
def test_malformed_account_identity_stops_before_verification_or_issuance(flow, user_id):
    # No invalid Entity is constructed: the factory returns its typed rejection.
    flow.lookup.return_value = account_snapshot(user_id=user_id)

    with pytest.raises(InvalidLoginAccountResult):
        flow.boundary.execute(flow.request)

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("generation", [-1, True, False, "7", 7.0, None])
def test_malformed_account_generation_stops_before_verification_or_issuance(flow, generation):
    flow.lookup.return_value = account_snapshot(generation=generation)

    with pytest.raises(InvalidLoginAccountResult):
        flow.boundary.execute(flow.request)

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("generation", [0, 7])
def test_valid_account_snapshot_is_forwarded_without_normalization(flow, generation):
    """Verify existing forwarding, including zero; no manufactured red cycle."""
    flow.lookup.return_value = account_snapshot(user_id=" user-73 ", generation=generation)
    flow.scope.__enter__.return_value = account_snapshot(user_id=" user-73 ", generation=generation)

    assert flow.boundary.execute(flow.request) is None

    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_called_once_with(
        user_id=" user-73 ", credential_generation=generation, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(flow.success_type("issued-token"))


def test_rejected_login_grant_emits_invalid_credentials_without_retry(flow):
    """Missing current account rejects before technical issuance, not in the issuer."""
    flow.scope.__enter__.return_value = None

    returned = flow.boundary.execute(flow.request)

    assert returned is None
    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.passwords.verify_missing.assert_not_called()
    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_called_once_with(flow.failure_type("invalid_credentials"))


@pytest.mark.parametrize("result", [None, True, "legacy-token", SimpleNamespace(token="token"), LoginGrantRejected()])
def test_undeclared_issuer_result_is_contract_failure_without_outcome(flow, result):
    flow.tokens.issue.return_value = result

    with pytest.raises(InvalidTokenIssuanceResult):
        flow.boundary.execute(flow.request)

    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("token", ["", 123, True, b"token"])
def test_empty_or_non_string_issued_token_is_contract_failure_without_success(flow, token):
    flow.tokens.issue.return_value = IssuedToken(token)

    with pytest.raises(InvalidTokenIssuanceResult):
        flow.boundary.execute(flow.request)

    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_not_called()


def test_old_snapshot_is_not_upgraded_but_fresh_login_can_succeed(flow):
    """Original generation is checked by the Interactor against protected facts."""
    flow.lookup.side_effect = [
        account_snapshot(generation=7),
        account_snapshot(generation=8),
    ]

    flow.scope.__enter__.return_value = account_snapshot(generation=8)
    flow.tokens.issue.return_value = IssuedToken("fresh-token")

    assert flow.boundary.execute(flow.request) is None

    flow.lookup.assert_called_once_with("alice")
    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_called_once_with(flow.failure_type("invalid_credentials"))
    flow.output.reset_mock()

    assert flow.boundary.execute(flow.request) is None

    assert flow.lookup.call_args_list == [call("alice"), call("alice")]
    assert flow.passwords.verify.call_args_list == [
        call("submitted-password", "stored-hash"),
        call("submitted-password", "stored-hash"),
    ]
    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=8, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(flow.success_type("fresh-token"))


@pytest.mark.parametrize("phase", ["creation", "entry"])
def test_scope_failure_before_issuance_propagates_without_outcome(flow, phase):
    """Cover the existing protected-scope failure path, not a manufactured red."""
    failure = LoginGrantError("Protected account scope unavailable")
    if phase == "creation":
        flow.grants.protect.side_effect = failure
    else:
        flow.scope.__enter__.side_effect = failure

    with pytest.raises(LoginGrantError) as caught:
        flow.boundary.execute(flow.request)

    assert caught.value is failure
    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.passwords.verify.assert_called_once_with("submitted-password", "stored-hash")
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("current", [None, "allowed"])
def test_scope_exit_failure_prevents_success_or_rejection_delivery(flow, current):
    """Completed issuance is not retried/rolled back; failed exit emits nothing."""
    flow.scope.__enter__.return_value = account_snapshot() if current == "allowed" else None
    failure = LoginGrantError("Protected scope release failed")
    flow.scope.__exit__.side_effect = failure

    with pytest.raises(LoginGrantError) as caught:
        flow.boundary.execute(flow.request)

    assert caught.value is failure
    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.scope.__exit__.assert_called_once_with(None, None, None)
    flow.output.present.assert_not_called()
    if current is None:
        flow.tokens.issue.assert_not_called()
    else:
        flow.tokens.issue.assert_called_once_with(
            user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
        )


@pytest.mark.parametrize("current", [
    True,
    "legacy-current-account",
    SimpleNamespace(user_id="user-42", credential_generation=7),
    account_snapshot(user_id="another-user-99"),
    account_snapshot(generation=-1),
])
def test_invalid_or_mismatched_protected_facts_prevent_issuance(flow, current):
    """Existing contract guards use real valid Entities or typed factory rejection."""
    flow.scope.__enter__.return_value = current

    with pytest.raises(InvalidLoginGrantResult):
        flow.boundary.execute(flow.request)

    flow.grants.protect.assert_called_once_with(user_id="user-42")
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()
    assert flow.scope.__exit__.call_count == 1


def test_unexpected_lookup_failure_propagates_without_downstream_effects(flow):
    """Existing propagation behavior, shared by both authentication consumers."""
    failure = ValueError("unexpected dependency failure")
    flow.lookup.side_effect = failure

    with pytest.raises(ValueError) as caught:
        flow.boundary.execute(flow.request)

    assert caught.value is failure
    flow.lookup.assert_called_once_with("alice")
    flow.passwords.verify.assert_not_called()
    flow.passwords.verify_missing.assert_not_called()
    flow.tokens.issue.assert_not_called()
    flow.output.present.assert_not_called()


def test_unexpected_issuer_failure_propagates_without_outcome_or_retry(flow):
    """Regression of existing failure propagation; no manufactured red."""
    failure = ValueError("Unexpected issuer failure")
    flow.tokens.issue.side_effect = failure

    with pytest.raises(ValueError) as caught:
        flow.boundary.execute(flow.request)

    assert caught.value is failure
    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_not_called()


def test_presentation_failure_does_not_retry_or_issue_another_token(flow):
    """Regression of existing delivery behavior; issuance cannot be rolled back."""
    failure = RuntimeError("Presentation unavailable")
    flow.output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        flow.boundary.execute(flow.request)

    assert caught.value is failure
    flow.tokens.issue.assert_called_once_with(
        user_id="user-42", credential_generation=7, ttl=timedelta(minutes=15),
    )
    flow.output.present.assert_called_once_with(flow.success_type("issued-token"))
