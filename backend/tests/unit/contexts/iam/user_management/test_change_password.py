"""Self-service password change through real input/domain and mocked I/O ports.

Unit tests verify approved state reaches commit, not production CAS/barrier effects.
"""

from unittest.mock import ANY, create_autospec

import pytest

from contexts.iam.application.modules.credentials.ports import (
    InvalidHashResult, InvalidPasswordVerificationResult,
    PasswordHasher, PasswordHashingError, PasswordVerificationError, PasswordVerifier,
)
from contexts.iam.application.modules.user_management.password_ports import (
    InvalidPasswordStoreResult, PasswordAccountStore, PasswordAccountUnavailable,
    PasswordChanged, PasswordChangeConflict, PasswordStoreError,
)
from contexts.iam.application.modules.user_management.use_cases.change_password.input_boundary import (
    ChangePasswordInputBoundary,
)
from contexts.iam.application.modules.user_management.use_cases.change_password.interactor import (
    ChangePasswordInteractor,
)
from contexts.iam.application.modules.user_management.use_cases.change_password.output_boundary import (
    ChangePasswordOutputBoundary,
)
from contexts.iam.application.modules.user_management.use_cases.change_password.request import ChangePasswordRequest
from contexts.iam.application.modules.user_management.use_cases.change_password.response import (
    ChangePasswordFailure, ChangePasswordSuccess,
)
from contexts.iam.domain.identity.user_account import UserAccountTransition, UserAccount
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email


def account_snapshot(
    *, user_id="owner-73", status=UserAccessStatus.ACTIVE, admin_eligible=False,
):
    return UserAccount.from_persisted(
        user_id=user_id, username=Username.from_input("LongUsername12345"),
        email=Email.from_input("owner@example.com"), password_hash="old-hash",
        status=status, version=9, credential_generation=17, admin_eligible=admin_eligible,
    )


@pytest.fixture
def flow():
    from types import SimpleNamespace

    account = account_snapshot()
    accounts = create_autospec(PasswordAccountStore, instance=True, spec_set=True)
    accounts.load.return_value = account
    accounts.commit.return_value = PasswordChanged()
    verifier = create_autospec(PasswordVerifier, instance=True, spec_set=True)
    verifier.verify.return_value = True
    hasher = create_autospec(PasswordHasher, instance=True, spec_set=True)
    hasher.hash.return_value = "new-hash"
    output = create_autospec(ChangePasswordOutputBoundary, instance=True, spec_set=True)
    boundary: ChangePasswordInputBoundary = ChangePasswordInteractor(
        accounts, verifier, hasher, output,
    )
    return SimpleNamespace(
        account=account, accounts=accounts, verifier=verifier, hasher=hasher,
        output=output, boundary=boundary,
        request=ChangePasswordRequest("CurrentLongPassword123!", "NextLongPassword123!"),
    )


@pytest.mark.parametrize("admin_eligible", [False, True])
def test_user_and_admin_commit_only_own_entity_password_transition(flow, admin_eligible):
    account = account_snapshot(admin_eligible=admin_eligible)
    flow.accounts.load.return_value = account

    returned = flow.boundary.execute(flow.request, actor_id="owner-73")

    assert returned is None
    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    flow.verifier.verify.assert_called_once_with("CurrentLongPassword123!", "old-hash")
    flow.hasher.hash.assert_called_once_with("NextLongPassword123!")
    flow.accounts.commit.assert_called_once_with(transition=ANY)
    transition = flow.accounts.commit.call_args.kwargs["transition"]
    assert isinstance(transition, UserAccountTransition)
    assert transition.before is account
    after = transition.after
    assert after.user_id == "owner-73"
    assert after.username.value == "longusername12345"
    assert after.email.value == "owner@example.com"
    assert after.password_hash == "new-hash"
    assert after.status is UserAccessStatus.ACTIVE
    assert after.admin_eligible is admin_eligible
    assert after.version == 10
    assert after.credential_generation == 18
    assert account.password_hash == "old-hash"
    assert account.version == 9
    assert account.credential_generation == 17
    flow.output.present.assert_called_once_with(ChangePasswordSuccess())
    for secret in ("CurrentLongPassword123!", "NextLongPassword123!", "old-hash", "new-hash"):
        assert secret not in repr(flow.output.present.call_args)


@pytest.mark.parametrize("snapshot", [object(), account_snapshot(user_id="other-owner-99")])
def test_wrong_owner_or_undeclared_snapshot_stops_before_secrets_or_writes(flow, snapshot):
    flow.accounts.load.return_value = snapshot

    with pytest.raises(InvalidPasswordStoreResult):
        flow.boundary.execute(flow.request, actor_id="owner-73")

    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    flow.verifier.verify.assert_not_called()
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("snapshot", [
    PasswordAccountUnavailable(), account_snapshot(status=UserAccessStatus.SUSPENDED),
])
def test_missing_or_suspended_account_is_unauthenticated_without_secret_work(flow, snapshot):
    flow.accounts.load.return_value = snapshot

    assert flow.boundary.execute(flow.request, actor_id="owner-73") is None

    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    flow.verifier.verify.assert_not_called()
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_called_once_with(ChangePasswordFailure("unauthenticated"))


def test_wrong_current_password_stops_before_candidate_validation_hash_or_commit(flow):
    flow.verifier.verify.return_value = False
    request = ChangePasswordRequest("wrong-current-secret", "short")

    assert flow.boundary.execute(request, actor_id="owner-73") is None

    flow.verifier.verify.assert_called_once_with("wrong-current-secret", "old-hash")
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_called_once_with(ChangePasswordFailure("invalid_current_password"))


@pytest.mark.parametrize("new_password", [
    "short", "Long Password123!", "LONGUSERNAME12345", None,
])
def test_invalid_new_password_uses_real_account_rules_before_hash_or_commit(flow, new_password):
    request = ChangePasswordRequest("CurrentLongPassword123!", new_password)

    assert flow.boundary.execute(request, actor_id="owner-73") is None

    flow.verifier.verify.assert_called_once_with("CurrentLongPassword123!", "old-hash")
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_called_once_with(ChangePasswordFailure("invalid_new_password"))


def test_same_current_and_new_password_has_no_hash_write_or_generation_change(flow):
    request = ChangePasswordRequest("CurrentLongPassword123!", "CurrentLongPassword123!")

    assert flow.boundary.execute(request, actor_id="owner-73") is None

    flow.verifier.verify.assert_called_once_with("CurrentLongPassword123!", "old-hash")
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_called_once_with(ChangePasswordFailure("password_unchanged"))
    assert flow.account.version == 9
    assert flow.account.credential_generation == 17


@pytest.mark.parametrize("password_hash", ["", None, True, 123])
def test_invalid_hasher_result_never_reaches_transition_commit_or_output(flow, password_hash):
    flow.hasher.hash.return_value = password_hash

    with pytest.raises(InvalidHashResult):
        flow.boundary.execute(flow.request, actor_id="owner-73")

    flow.hasher.hash.assert_called_once_with("NextLongPassword123!")
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("result,code", [
    (PasswordAccountUnavailable(), "unauthenticated"),
    (PasswordChangeConflict(), "password_conflict"),
])
def test_commit_rejection_is_terminal_without_retry_or_false_success(flow, result, code):
    flow.accounts.commit.return_value = result

    assert flow.boundary.execute(flow.request, actor_id="owner-73") is None

    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    flow.hasher.hash.assert_called_once_with("NextLongPassword123!")
    flow.accounts.commit.assert_called_once_with(transition=ANY)
    transition = flow.accounts.commit.call_args.kwargs["transition"]
    assert transition.before is flow.account
    assert transition.after.user_id == "owner-73"
    assert transition.after.password_hash == "new-hash"
    assert transition.after.version == 10
    assert transition.after.credential_generation == 18
    flow.output.present.assert_called_once_with(ChangePasswordFailure(code))


def test_undeclared_commit_result_is_system_failure_without_presentation_or_retry(flow):
    flow.accounts.commit.return_value = object()

    with pytest.raises(InvalidPasswordStoreResult):
        flow.boundary.execute(flow.request, actor_id="owner-73")

    flow.accounts.commit.assert_called_once_with(transition=ANY)
    flow.output.present.assert_not_called()


@pytest.mark.parametrize("stage,failure", [
    ("load", PasswordStoreError("lookup unavailable")),
    ("verify", PasswordVerificationError("verification unavailable")),
    ("hash", PasswordHashingError("hashing unavailable")),
    ("commit", PasswordStoreError("commit certainty unknown")),
    ("commit", ValueError("unexpected failure")),
])
def test_existing_dependency_failures_propagate_without_later_effects_or_outcome(flow, stage, failure):
    # Tests already-present propagation; no artificial red/green or domain mocks.
    operations = {
        "load": flow.accounts.load, "verify": flow.verifier.verify,
        "hash": flow.hasher.hash, "commit": flow.accounts.commit,
    }
    operations[stage].side_effect = failure

    with pytest.raises(type(failure)) as caught:
        flow.boundary.execute(flow.request, actor_id="owner-73")

    assert caught.value is failure
    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    if stage == "load":
        flow.verifier.verify.assert_not_called()
    else:
        flow.verifier.verify.assert_called_once_with("CurrentLongPassword123!", "old-hash")
    if stage in ("load", "verify"):
        flow.hasher.hash.assert_not_called()
    else:
        flow.hasher.hash.assert_called_once_with("NextLongPassword123!")
    if stage != "commit":
        flow.accounts.commit.assert_not_called()
    else:
        flow.accounts.commit.assert_called_once_with(transition=ANY)
        transition = flow.accounts.commit.call_args.kwargs["transition"]
        assert transition.before is flow.account
        assert transition.after.user_id == "owner-73"
        assert transition.after.password_hash == "new-hash"
        assert transition.after.version == 10
        assert transition.after.credential_generation == 18
    flow.output.present.assert_not_called()


def test_existing_presentation_failure_does_not_repeat_a_committed_password_change(flow):
    failure = RuntimeError("presentation unavailable")
    flow.output.present.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        flow.boundary.execute(flow.request, actor_id="owner-73")

    assert caught.value is failure
    flow.accounts.load.assert_called_once_with(actor_id="owner-73")
    flow.hasher.hash.assert_called_once_with("NextLongPassword123!")
    flow.accounts.commit.assert_called_once_with(transition=ANY)
    flow.output.present.assert_called_once_with(ChangePasswordSuccess())


@pytest.mark.parametrize("verdict", [None, 0, 1, "true"])
def test_malformed_verification_verdict_is_not_a_business_decision(flow, verdict):
    flow.verifier.verify.return_value = verdict

    with pytest.raises(InvalidPasswordVerificationResult):
        flow.boundary.execute(flow.request, actor_id="owner-73")

    flow.verifier.verify.assert_called_once_with("CurrentLongPassword123!", "old-hash")
    flow.hasher.hash.assert_not_called()
    flow.accounts.commit.assert_not_called()
    flow.output.present.assert_not_called()
