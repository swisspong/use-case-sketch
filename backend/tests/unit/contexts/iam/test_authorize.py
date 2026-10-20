from contextlib import AbstractContextManager
from unittest.mock import create_autospec

import pytest

from contexts.iam.application.use_cases.authorize.ports import (
    AccessAccountStore,
    AccessValidationError,
    AccessValidator,
    UnauthenticatedAccess,
    ValidatedAccess,
    VerifiedCredential,
)
from contexts.iam.application.use_cases.authorize.errors import (
    InvalidAccessRequirement,
    InvalidAccessValidationResult,
)
from contexts.iam.application.use_cases.authorize.input_boundary import (
    AuthorizeInputBoundary,
)
from contexts.iam.application.use_cases.authorize.interactor import (
    AuthorizeInteractor,
)
from contexts.iam.application.use_cases.authorize.output_boundary import (
    AuthorizeOutputBoundary,
)
from contexts.iam.application.use_cases.authorize.request import (
    AccessRequirement,
    AuthorizeRequest,
)
from contexts.iam.application.use_cases.authorize.response import (
    AuthorizeFailure,
    AuthorizeSuccess,
)
from contexts.iam.domain.identity.user_account import (
    InvalidUserAccount, UserAccount, UserAccountTransition,
)
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email, Password


@pytest.fixture
def access():
    return create_autospec(AccessValidator, instance=True, spec_set=True)


@pytest.fixture
def output():
    return create_autospec(AuthorizeOutputBoundary, instance=True, spec_set=True)


def account_facts(*, user_id="user-42", admin_eligible=False, account_type=UserAccount):
    account = account_type.from_persisted(
        user_id=user_id, username=Username.from_input("alice"),
        email=Email.from_input("alice@example.com"), password_hash="stored-hash",
        status=UserAccessStatus.ACTIVE, version=9,
        credential_generation=7, admin_eligible=admin_eligible,
    )
    assert isinstance(account, UserAccount)
    return account


@pytest.fixture
def account_scope():
    scope = create_autospec(AbstractContextManager, instance=True, spec_set=True)
    scope.__enter__.return_value = account_facts()
    scope.__exit__.return_value = False
    return scope


@pytest.fixture
def accounts(account_scope):
    store = create_autospec(AccessAccountStore, instance=True, spec_set=True)
    store.protect.return_value = account_scope
    return store


@pytest.fixture
def boundary(access, output, accounts) -> AuthorizeInputBoundary:
    return AuthorizeInteractor(access, output, accounts=accounts)


@pytest.mark.parametrize("generation", [7, 8])
def test_verified_credential_cannot_access_suspended_account(
    boundary, access, accounts, account_scope, output, generation,
):
    credential = VerifiedCredential("user-42", generation)
    access.validate.return_value = credential
    suspension = account_facts().change_status(
        status=UserAccessStatus.SUSPENDED, expected_version=9,
    )
    assert isinstance(suspension, UserAccountTransition)
    account_scope.__enter__.return_value = suspension.after

    boundary.execute(
        AuthorizeRequest(token="signed-original-generation7"),
        requirement=AccessRequirement.AUTHENTICATED,
    )

    access.validate.assert_called_once_with("signed-original-generation7")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", generation), token="signed-original-generation7",
    )
    output.present.assert_called_once_with(AuthorizeFailure("unauthenticated"))


@pytest.mark.parametrize("requirement,generation,missing,expected", [
    (AccessRequirement.AUTHENTICATED, 7, False, AuthorizeSuccess("user-42")),
    (AccessRequirement.ADMIN, 7, False, AuthorizeFailure("forbidden")),
    (AccessRequirement.ADMIN, 6, False, AuthorizeFailure("unauthenticated")),
    (AccessRequirement.ADMIN, 7, True, AuthorizeFailure("unauthenticated")),
])
def test_protected_facts_are_decided_inside_scope_and_presented_after_exit(
    boundary, access, account_scope, output, requirement, generation, missing, expected,
):
    protected = False
    exited = False

    class ScopeBoundAccount(UserAccount):
        # Enforce the port's fact lifetime, but execute the REAL domain decision.
        def credential_eligibility(self, *, generation):
            assert protected, "Account decision escaped the protected scope"
            return super().credential_eligibility(generation=generation)

        def administrative_eligibility(self):
            assert protected, "Admin decision escaped the protected scope"
            return super().administrative_eligibility()

    account = account_facts(account_type=ScopeBoundAccount)

    def enter():
        nonlocal protected
        protected = True
        return None if missing else account

    def exit_scope(*args):
        nonlocal protected, exited
        output.present.assert_not_called()
        protected = False
        exited = True
        return False

    def present(outcome):
        assert exited and not protected

    account_scope.__enter__.side_effect = enter
    account_scope.__exit__.side_effect = exit_scope
    output.present.side_effect = present
    access.validate.return_value = VerifiedCredential("user-42", generation)

    boundary.execute(AuthorizeRequest("scope-bound-credential"), requirement=requirement)

    output.present.assert_called_once_with(expected)


@pytest.mark.parametrize("stage,generation,error_type", [
    ("open", 7, AccessValidationError),
    ("enter", 7, AccessValidationError),
    ("exit", 7, AccessValidationError),
    ("exit", 6, AccessValidationError),
    ("enter", 7, ValueError),
])
def test_account_scope_failures_propagate_without_outcome_or_retry(
    boundary, access, accounts, account_scope, output, stage, generation, error_type,
):
    access.validate.return_value = VerifiedCredential("user-42", generation)
    failure = error_type("Protected access unavailable")
    failing_operation = {
        "open": accounts.protect,
        "enter": account_scope.__enter__,
        "exit": account_scope.__exit__,
    }[stage]
    failing_operation.side_effect = failure

    with pytest.raises(error_type) as caught:
        boundary.execute(
            AuthorizeRequest("credential-during-protection-failure"),
            requirement=AccessRequirement.AUTHENTICATED,
        )

    assert caught.value is failure
    access.validate.assert_called_once_with("credential-during-protection-failure")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", generation),
        token="credential-during-protection-failure",
    )
    if stage == "open":
        account_scope.__enter__.assert_not_called()
    else:
        account_scope.__enter__.assert_called_once_with()
    output.present.assert_not_called()


@pytest.mark.parametrize("result", [
    True, {"user_id": "user-42", "admin_eligible": True},
    InvalidUserAccount("status"),
    account_facts(user_id="other-admin-99", admin_eligible=True),
])
def test_invalid_or_wrong_subject_account_facts_are_system_failures(
    boundary, access, accounts, account_scope, output, result,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)
    account_scope.__enter__.return_value = result

    with pytest.raises(InvalidAccessValidationResult):
        boundary.execute(
            AuthorizeRequest("credential-for-user42-not-other-admin"),
            requirement=AccessRequirement.ADMIN,
        )

    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7),
        token="credential-for-user42-not-other-admin",
    )
    account_scope.__exit__.assert_called_once()
    output.present.assert_not_called()


@pytest.mark.parametrize("generation", [None, -1, 6, 8])
def test_missing_or_noncurrent_generation_is_not_upgraded_to_current_account(
    boundary, access, accounts, output, generation,
):
    access.validate.return_value = VerifiedCredential("user-42", generation)

    boundary.execute(
        AuthorizeRequest(token="credential-with-original-generation"),
        requirement=AccessRequirement.AUTHENTICATED,
    )

    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", generation),
        token="credential-with-original-generation",
    )
    output.present.assert_called_once_with(AuthorizeFailure("unauthenticated"))


@pytest.mark.parametrize("credential", [
    VerifiedCredential("", 7), VerifiedCredential("   ", 7),
    VerifiedCredential(None, 7), VerifiedCredential("user-42", "7"),
    VerifiedCredential("user-42", True), VerifiedCredential("user-42", 7.0),
])
def test_malformed_verification_facts_fail_before_account_lookup(
    boundary, access, accounts, output, credential,
):
    access.validate.return_value = credential

    with pytest.raises(InvalidAccessValidationResult):
        boundary.execute(
            AuthorizeRequest(token="malformed-trusted-verification-result"),
            requirement=AccessRequirement.ADMIN,
        )

    accounts.protect.assert_not_called()
    output.present.assert_not_called()


def test_verified_credential_with_no_current_account_is_unauthenticated(
    boundary, access, accounts, account_scope, output,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)
    account_scope.__enter__.return_value = None

    boundary.execute(
        AuthorizeRequest(token="signed-credential-with-missing-subject"),
        requirement=AccessRequirement.ADMIN,
    )

    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7),
        token="signed-credential-with-missing-subject",
    )
    output.present.assert_called_once_with(AuthorizeFailure("unauthenticated"))


@pytest.mark.parametrize("state,allowed", [
    ("current", True), ("rotated", False), ("suspended", False), ("restored", False),
])
def test_existing_access_consumer_uses_real_entity_generation_decisions(
    boundary, access, accounts, account_scope, output, state, allowed,
):
    # Verified token subject/generation are test facts, not real cryptographic checks.
    before = UserAccount.from_persisted(
        user_id="user-42", username=Username.from_input("alice"),
        email=Email.from_input("alice@example.com"), password_hash="stored-hash",
        status=UserAccessStatus.ACTIVE, version=9,
        credential_generation=7, admin_eligible=False,
    )
    rotation = before.change_password(
        password=Password.from_input("NextLongPassword123!"),
        password_hash="rotated-hash", expected_version=9,
    )
    suspension = before.change_status(status=UserAccessStatus.SUSPENDED, expected_version=9)
    assert isinstance(rotation, UserAccountTransition)
    assert isinstance(suspension, UserAccountTransition)
    restoration = suspension.after.change_status(status=UserAccessStatus.ACTIVE, expected_version=10)
    assert isinstance(restoration, UserAccountTransition)
    account = {
        "current": before, "rotated": rotation.after,
        "suspended": suspension.after, "restored": restoration.after,
    }[state]

    access.validate.return_value = VerifiedCredential("user-42", 7)
    account_scope.__enter__.return_value = account

    assert boundary.execute(
        AuthorizeRequest(token="trusted-original-generation7"),
        requirement=AccessRequirement.AUTHENTICATED,
    ) is None

    access.validate.assert_called_once_with("trusted-original-generation7")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7), token="trusted-original-generation7",
    )
    if allowed:
        output.present.assert_called_once_with(AuthorizeSuccess("user-42"))
    else:
        output.present.assert_called_once_with(AuthorizeFailure("unauthenticated"))


def test_user_with_valid_access_can_enter_authenticated_endpoint(
    boundary, access, accounts, output,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)

    returned = boundary.execute(
        AuthorizeRequest(token="user-session-credential"),
        requirement=AccessRequirement.AUTHENTICATED,
    )

    assert returned is None
    access.validate.assert_called_once_with("user-session-credential")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7), token="user-session-credential",
    )
    output.present.assert_called_once_with(AuthorizeSuccess(actor_id="user-42"))


def test_authenticated_user_cannot_enter_admin_endpoint(
    boundary, access, accounts, output,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)

    boundary.execute(
        AuthorizeRequest(token="nonadmin-session-credential"),
        requirement=AccessRequirement.ADMIN,
    )

    access.validate.assert_called_once_with("nonadmin-session-credential")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7), token="nonadmin-session-credential",
    )
    output.present.assert_called_once_with(AuthorizeFailure(code="forbidden"))


@pytest.mark.parametrize("requirement", list(AccessRequirement))
def test_current_admin_can_enter_both_access_levels(
    boundary, access, accounts, account_scope, output, requirement,
):
    access.validate.return_value = VerifiedCredential("admin-73", 7)
    account_scope.__enter__.return_value = account_facts(
        user_id="admin-73", admin_eligible=True,
    )

    boundary.execute(
        AuthorizeRequest(token="admin-session-credential"), requirement=requirement,
    )

    access.validate.assert_called_once_with("admin-session-credential")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("admin-73", 7), token="admin-session-credential",
    )
    output.present.assert_called_once_with(AuthorizeSuccess(actor_id="admin-73"))


@pytest.mark.parametrize("requirement", list(AccessRequirement))
def test_rejected_credential_or_account_cannot_enter_either_level(
    boundary, access, accounts, output, requirement,
):
    access.validate.return_value = UnauthenticatedAccess()

    boundary.execute(
        AuthorizeRequest(token="unusable-session-credential"), requirement=requirement,
    )

    access.validate.assert_called_once_with("unusable-session-credential")
    accounts.protect.assert_not_called()
    output.present.assert_called_once_with(AuthorizeFailure(code="unauthenticated"))


@pytest.mark.parametrize("requirement", [None, "admin", "authenticated", "unknown"])
def test_invalid_server_requirement_fails_without_validating_or_presenting(
    boundary, access, accounts, output, requirement,
):
    access.validate.return_value = VerifiedCredential("admin-73", 7)

    with pytest.raises(InvalidAccessRequirement):
        boundary.execute(AuthorizeRequest(token="valid-credential"), requirement=requirement)

    access.validate.assert_not_called()
    accounts.protect.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("result", [None, True, {"actor_id": "admin-73"}])
def test_undeclared_validator_result_is_system_failure_not_access_decision(
    boundary, access, accounts, output, result,
):
    access.validate.return_value = result

    with pytest.raises(InvalidAccessValidationResult):
        boundary.execute(
            AuthorizeRequest(token="credential-to-validate"),
            requirement=AccessRequirement.AUTHENTICATED,
        )

    access.validate.assert_called_once_with("credential-to-validate")
    accounts.protect.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize(
    "result",
    [
        ValidatedAccess("", False),
        ValidatedAccess("   ", False),
        ValidatedAccess(None, False),
        ValidatedAccess("user-42", "true"),
        ValidatedAccess("user-42", 1),
        ValidatedAccess("user-42", None),
        ValidatedAccess("user-42", False),
        ValidatedAccess("admin-73", True),
    ],
)
def test_malformed_trusted_access_data_cannot_grant_or_deny_admin_access(
    boundary, access, accounts, output, result,
):
    access.validate.return_value = result

    with pytest.raises(InvalidAccessValidationResult):
        boundary.execute(
            AuthorizeRequest(token="credential-with-invalid-provider-result"),
            requirement=AccessRequirement.ADMIN,
        )

    access.validate.assert_called_once_with("credential-with-invalid-provider-result")
    accounts.protect.assert_not_called()
    output.present.assert_not_called()


@pytest.mark.parametrize("token", ["", " \t\n", None, 123])
def test_missing_or_non_string_token_is_rejected_without_dependency_call(
    boundary, access, accounts, output, token,
):
    access.validate.return_value = VerifiedCredential("admin-73", 7)

    boundary.execute(AuthorizeRequest(token=token), requirement=AccessRequirement.ADMIN)

    access.validate.assert_not_called()
    accounts.protect.assert_not_called()
    output.present.assert_called_once_with(AuthorizeFailure(code="unauthenticated"))


def test_validator_outage_propagates_without_outcome_or_retry(
    boundary, access, accounts, output,
):
    failure = AccessValidationError("Access validation unavailable")
    access.validate.side_effect = failure

    with pytest.raises(AccessValidationError) as caught:
        boundary.execute(
            AuthorizeRequest(token="credential-during-outage"),
            requirement=AccessRequirement.ADMIN,
        )

    assert caught.value is failure
    access.validate.assert_called_once_with("credential-during-outage")
    accounts.protect.assert_not_called()
    output.present.assert_not_called()


def test_unexpected_validator_error_is_not_converted_to_denial(
    boundary, access, accounts, output,
):
    failure = ValueError("Unexpected adapter failure")
    access.validate.side_effect = failure

    with pytest.raises(ValueError) as caught:
        boundary.execute(
            AuthorizeRequest(token="credential-during-unexpected-failure"),
            requirement=AccessRequirement.AUTHENTICATED,
        )

    assert caught.value is failure
    access.validate.assert_called_once_with("credential-during-unexpected-failure")
    accounts.protect.assert_not_called()
    output.present.assert_not_called()


def test_presentation_failure_propagates_without_revalidation_or_second_outcome(
    boundary, access, accounts, output,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)
    failure = RuntimeError("Presentation unavailable")
    output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        boundary.execute(
            AuthorizeRequest(token="credential-before-presentation-failure"),
            requirement=AccessRequirement.AUTHENTICATED,
        )

    assert caught.value is failure
    access.validate.assert_called_once_with("credential-before-presentation-failure")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7), token="credential-before-presentation-failure",
    )
    output.present.assert_called_once_with(AuthorizeSuccess(actor_id="user-42"))


def test_verified_token_is_forwarded_unchanged_to_protected_account_scope(
    boundary, access, accounts, output,
):
    access.validate.return_value = VerifiedCredential("user-42", 7)

    boundary.execute(
        AuthorizeRequest(" opaque-credential-preserved-exactly "),
        requirement=AccessRequirement.AUTHENTICATED,
    )

    access.validate.assert_called_once_with(" opaque-credential-preserved-exactly ")
    accounts.protect.assert_called_once_with(
        credential=VerifiedCredential("user-42", 7),
        token=" opaque-credential-preserved-exactly ",
    )
    output.present.assert_called_once_with(AuthorizeSuccess("user-42"))


def test_credential_is_passed_unchanged_not_normalized_into_valid_access(
    boundary, access, accounts, output,
):
    def validate(token):
        if token == "exact-valid-credential":
            return VerifiedCredential("admin-73", 7)
        return UnauthenticatedAccess()

    access.validate.side_effect = validate

    boundary.execute(
        AuthorizeRequest(token=" exact-valid-credential "),
        requirement=AccessRequirement.ADMIN,
    )

    access.validate.assert_called_once_with(" exact-valid-credential ")
    accounts.protect.assert_not_called()
    output.present.assert_called_once_with(AuthorizeFailure(code="unauthenticated"))
