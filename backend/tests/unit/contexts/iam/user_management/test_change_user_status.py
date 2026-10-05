"""Status orchestration through real Input Boundary/domain and mocked atomic I/O.

Mocks supply authoritative facts and acknowledge commit; they never call policy.
Tests verify exact transitions, security-significant identities, no commit after
rejection, single post-scope outcome and failure propagation without retries.
Production locking, rollback, persistence and access-barrier guarantees are deferred.
"""

from contextlib import AbstractContextManager
import unittest
from unittest.mock import ANY, create_autospec

from contexts.iam.application.modules.user_management.ports import (
    InvalidUserStatusChangeResult, StatusChangeFacts, StatusChangeTransaction,
    StatusChangeUoW, UserStatusManagementError,
)
from contexts.iam.application.modules.user_management.use_cases.change_user_status.input_boundary import (
    ChangeUserStatusInputBoundary,
)
from contexts.iam.application.modules.user_management.use_cases.change_user_status.interactor import (
    ChangeUserStatusInteractor,
)
from contexts.iam.application.modules.user_management.use_cases.change_user_status.output_boundary import (
    ChangeUserStatusOutputBoundary,
)
from contexts.iam.application.modules.user_management.use_cases.change_user_status.request import (
    ChangeUserStatusRequest,
)
from contexts.iam.application.modules.user_management.use_cases.change_user_status.response import (
    ChangeUserStatusFailure, ChangeUserStatusSuccess,
)
from contexts.iam.domain.identity.user_account import InvalidUserAccount, UserAccount, UserAccountTransition
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email


class ChangeUserStatusTests(unittest.TestCase):
    def snapshot(self, *, account_type=UserAccount, **overrides) -> UserAccount:
        values = dict(
            user_id="user-42", status=UserAccessStatus.ACTIVE, version=9,
            credential_generation=17, admin_eligible=False,
            username=Username.from_input("alice42"),
            email=Email.from_input("alice@example.com"), password_hash="stored-hash",
        )
        values.update(overrides)
        account = account_type.from_persisted(**values)
        self.assertIsInstance(account, UserAccount)
        return account

    def setUp(self) -> None:
        self.uow = create_autospec(StatusChangeUoW, instance=True, spec_set=True)
        self.tx = create_autospec(StatusChangeTransaction, instance=True, spec_set=True)
        self.scope = create_autospec(AbstractContextManager, instance=True, spec_set=True)
        self.scope.__enter__.return_value = self.tx
        self.scope.__exit__.return_value = False
        self.uow.begin.return_value = self.scope
        self.account = self.snapshot()
        self.actor = self.snapshot(user_id="admin-7", admin_eligible=True)
        self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, self.account)
        self.tx.commit.return_value = None
        self.output = create_autospec(ChangeUserStatusOutputBoundary, instance=True, spec_set=True)
        self.use_case: ChangeUserStatusInputBoundary = ChangeUserStatusInteractor(
            self.uow, self.output,
        )

    def test_suspension_commits_real_entity_transition_before_presenting(self) -> None:
        def read_facts():
            self.scope.__enter__.assert_called_once_with()
            self.scope.__exit__.assert_not_called()
            return StatusChangeFacts("admin-7", self.actor, self.account)

        def commit_transition(*, transition):
            self.scope.__enter__.assert_called_once_with()
            self.scope.__exit__.assert_not_called()
            self.output.present.assert_not_called()
            return None

        def observe_outcome(outcome):
            self.scope.__exit__.assert_called_once_with(None, None, None)
            self.tx.commit.assert_called_once_with(transition=ANY)

        self.tx.facts.side_effect = read_facts
        self.tx.commit.side_effect = commit_transition
        self.output.present.side_effect = observe_outcome

        returned = self.use_case.execute(
            ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
            actor_id="admin-7",
        )

        self.assertIsNone(returned)
        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
        self.tx.commit.assert_called_once_with(transition=ANY)
        transition = self.tx.commit.call_args.kwargs["transition"]
        self.assertIsInstance(transition, UserAccountTransition)
        self.assertIs(transition.before, self.account)
        self.assertEqual(transition.after.user_id, "user-42")
        self.assertEqual(transition.after.username.value, "alice42")
        self.assertEqual(transition.after.email.value, "alice@example.com")
        self.assertEqual(transition.after.password_hash, "stored-hash")
        self.assertIs(transition.after.admin_eligible, False)
        self.assertIs(transition.after.status, UserAccessStatus.SUSPENDED)
        self.assertEqual(transition.after.version, 10)
        self.assertIs(type(transition.after.version), int)
        self.assertEqual(transition.after.credential_generation, 18)
        self.assertIs(type(transition.after.credential_generation), int)
        self.assertIs(self.account.status, UserAccessStatus.ACTIVE)
        self.assertEqual(self.account.version, 9)
        self.assertEqual(self.account.credential_generation, 17)
        self.output.present.assert_called_once_with(
            ChangeUserStatusSuccess("user-42", UserAccessStatus.SUSPENDED, version=10),
        )

    def test_restoration_preserves_generation_and_credentials_in_exact_committed_transition(self) -> None:
        account = self.snapshot(
            status=UserAccessStatus.SUSPENDED, version=10, credential_generation=18,
        )
        self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, account)

        returned = self.use_case.execute(
            ChangeUserStatusRequest("user-42", "active", expected_version=10),
            actor_id="admin-7",
        )

        self.assertIsNone(returned)
        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
        self.tx.commit.assert_called_once_with(transition=ANY)
        transition = self.tx.commit.call_args.kwargs["transition"]
        self.assertIsInstance(transition, UserAccountTransition)
        self.assertIs(transition.before, account)
        self.assertEqual(transition.after.user_id, "user-42")
        self.assertEqual(transition.after.username.value, "alice42")
        self.assertEqual(transition.after.email.value, "alice@example.com")
        self.assertEqual(transition.after.password_hash, "stored-hash")
        self.assertIs(transition.after.admin_eligible, False)
        self.assertIs(transition.after.status, UserAccessStatus.ACTIVE)
        self.assertEqual(transition.after.version, 11)
        self.assertEqual(transition.after.credential_generation, 18)
        self.assertIs(account.status, UserAccessStatus.SUSPENDED)
        self.assertEqual(account.version, 10)
        self.assertEqual(account.credential_generation, 18)
        self.output.present.assert_called_once_with(
            ChangeUserStatusSuccess("user-42", UserAccessStatus.ACTIVE, version=11),
        )

    def test_exact_status_strings_and_enum_values_reach_committed_domain_state(self) -> None:
        for raw, status, before in (
            ("active", UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED),
            ("suspended", UserAccessStatus.SUSPENDED, UserAccessStatus.ACTIVE),
            (UserAccessStatus.ACTIVE, UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED),
            (UserAccessStatus.SUSPENDED, UserAccessStatus.SUSPENDED, UserAccessStatus.ACTIVE),
        ):
            with self.subTest(raw=raw):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.output.reset_mock()
                account = self.snapshot(status=before)
                self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, account)

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", raw, expected_version=9),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                self.tx.commit.assert_called_once_with(transition=ANY)
                transition = self.tx.commit.call_args.kwargs["transition"]
                self.assertIs(transition.before, account)
                self.assertIs(transition.after.status, status)
                self.assertEqual(transition.after.version, 10)
                self.output.present.assert_called_once_with(
                    ChangeUserStatusSuccess("user-42", status, version=10),
                )

    def test_suspended_admin_is_forbidden_inside_scope_without_commit(self) -> None:
        class ScopeBoundActor(UserAccount):
            def administrative_eligibility(actor):
                self.scope.__enter__.assert_called_once_with()
                self.scope.__exit__.assert_not_called()
                return super().administrative_eligibility()

        actor = self.snapshot(
            account_type=ScopeBoundActor, user_id="admin-7", admin_eligible=True,
            status=UserAccessStatus.SUSPENDED,
        )
        self.tx.facts.return_value = StatusChangeFacts("admin-7", actor, self.account)

        def exit_scope(*args):
            self.output.present.assert_not_called()
            self.tx.commit.assert_not_called()
            return False

        self.scope.__exit__.side_effect = exit_scope

        self.assertIsNone(self.use_case.execute(
            ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
            actor_id="admin-7",
        ))

        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
        self.tx.commit.assert_not_called()
        self.scope.__exit__.assert_called_once_with(None, None, None)
        self.output.present.assert_called_once_with(ChangeUserStatusFailure("forbidden"))
        self.assertIs(self.account.status, UserAccessStatus.ACTIVE)
        self.assertEqual(self.account.version, 9)

    def test_non_admin_is_forbidden_before_any_target_decision_without_commit(self) -> None:
        for target in (None, self.snapshot(admin_eligible=True), self.snapshot()):
            with self.subTest(target=target):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.output.reset_mock()
                actor = self.snapshot(user_id="ordinary-user-9", admin_eligible=False)
                self.tx.facts.return_value = StatusChangeFacts("ordinary-user-9", actor, target)

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", "suspended", expected_version=0),
                    actor_id="ordinary-user-9",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_called_once_with(
                    actor_id="ordinary-user-9", user_id="user-42",
                )
                self.tx.commit.assert_not_called()
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("forbidden"))

    def test_missing_actor_is_forbidden_before_any_target_decision_without_commit(self) -> None:
        # Coverage of the now-implemented absent-actor branch, not a manufactured red.
        for target in (None, self.snapshot(admin_eligible=True), self.account):
            with self.subTest(target=target):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.scope.reset_mock()
                self.output.reset_mock()
                self.tx.facts.return_value = StatusChangeFacts("admin-7", None, target)

                self.assertIsNone(self.use_case.execute(
                    ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                    actor_id="admin-7",
                ))

                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                self.tx.commit.assert_not_called()
                self.scope.__exit__.assert_called_once_with(None, None, None)
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("forbidden"))

    def test_missing_target_is_not_found_without_commit(self) -> None:
        self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, None)

        returned = self.use_case.execute(
            ChangeUserStatusRequest("missing-user-81", "suspended", expected_version=9),
            actor_id="admin-7",
        )

        self.assertIsNone(returned)
        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="missing-user-81")
        self.tx.commit.assert_not_called()
        self.output.present.assert_called_once_with(ChangeUserStatusFailure("user_not_found"))

    def test_self_and_other_admin_targets_are_protected_before_version_and_already_set(self) -> None:
        for user_id, before_status, status, expected_version in (
            ("admin-7", UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED, 9),
            ("admin-7", UserAccessStatus.SUSPENDED, UserAccessStatus.ACTIVE, 9),
            ("other-admin-23", UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED, 9),
            ("other-admin-23", UserAccessStatus.SUSPENDED, UserAccessStatus.ACTIVE, 9),
            ("admin-7", UserAccessStatus.ACTIVE, UserAccessStatus.ACTIVE, 0),
            ("other-admin-23", UserAccessStatus.SUSPENDED, UserAccessStatus.SUSPENDED, 9),
        ):
            with self.subTest(user_id=user_id, status=status, expected_version=expected_version):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.output.reset_mock()
                account = self.snapshot(user_id=user_id, status=before_status, admin_eligible=True)
                actor = account if user_id == "admin-7" else self.actor
                self.tx.facts.return_value = StatusChangeFacts("admin-7", actor, account)

                returned = self.use_case.execute(
                    ChangeUserStatusRequest(user_id, status, expected_version),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id=user_id)
                self.tx.commit.assert_not_called()
                # A suspended self-actor is denied before target protection;
                # active actors still cannot change any admin target.
                expected_code = (
                    "forbidden" if user_id == "admin-7" and before_status is UserAccessStatus.SUSPENDED
                    else "admin_target_forbidden"
                )
                self.output.present.assert_called_once_with(
                    ChangeUserStatusFailure(expected_code),
                )
                self.assertEqual(account.version, 9)
                self.assertEqual(account.credential_generation, 17)

    def test_stale_revision_is_conflict_even_when_requested_status_already_matches(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            with self.subTest(status=status):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.output.reset_mock()
                account = self.snapshot(status=status)
                self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, account)

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", status, expected_version=8),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                self.tx.commit.assert_not_called()
                self.assertEqual(account.version, 9)
                self.assertEqual(account.credential_generation, 17)
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("status_conflict"))

    def test_matching_status_has_no_commit_revision_or_generation_effect(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            with self.subTest(status=status):
                self.tx.reset_mock()
                self.output.reset_mock()
                account = self.snapshot(status=status)
                self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, account)

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", status, expected_version=9),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.tx.commit.assert_not_called()
                self.assertEqual(account.version, 9)
                self.assertEqual(account.credential_generation, 17)
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("status_already_set"))

    def test_rejection_is_presented_only_after_successful_scope_exit(self) -> None:
        self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, None)

        def exit_scope(*args):
            self.output.present.assert_not_called()
            self.tx.commit.assert_not_called()
            return False

        self.scope.__exit__.side_effect = exit_scope

        self.assertIsNone(self.use_case.execute(
            ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
            actor_id="admin-7",
        ))

        self.output.present.assert_called_once_with(ChangeUserStatusFailure("user_not_found"))

    def test_malformed_or_wrong_identity_facts_stop_before_commit_and_presentation(self) -> None:
        for facts in (
            object(),
            StatusChangeFacts("other-actor-99", self.actor, self.account),
            StatusChangeFacts("admin-7", self.actor, self.snapshot(user_id="different-user-99")),
            StatusChangeFacts("admin-7", self.actor, object()),
            StatusChangeFacts("admin-7", self.snapshot(user_id="other-admin-99", admin_eligible=True), self.account),
        ):
            with self.subTest(facts=facts):
                self.uow.reset_mock()
                self.tx.reset_mock()
                self.output.reset_mock()
                self.tx.facts.return_value = facts

                with self.assertRaises(InvalidUserStatusChangeResult):
                    self.use_case.execute(
                        ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                        actor_id="admin-7",
                    )

                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                self.tx.commit.assert_not_called()
                self.output.present.assert_not_called()

    def test_malformed_authoritative_actor_is_a_system_failure_not_a_denial(self) -> None:
        # None now means a missing actor; malformed/leaked Entity results remain errors.
        for actor in (1, "true", True, InvalidUserAccount("status")):
            with self.subTest(actor=actor):
                self.tx.reset_mock()
                self.output.reset_mock()
                self.tx.facts.return_value = StatusChangeFacts("admin-7", actor, self.account)

                with self.assertRaises(InvalidUserStatusChangeResult):
                    self.use_case.execute(
                        ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                        actor_id="admin-7",
                    )

                self.tx.commit.assert_not_called()
                self.output.present.assert_not_called()

    def test_non_none_commit_acknowledgement_is_not_presented_as_success(self) -> None:
        # There is no independently writable success user/status/version result.
        for acknowledgement in (True, False, "committed", 9, 11, "10", object()):
            with self.subTest(acknowledgement=acknowledgement):
                self.tx.reset_mock()
                self.output.reset_mock()
                self.tx.commit.return_value = acknowledgement

                with self.assertRaises(InvalidUserStatusChangeResult):
                    self.use_case.execute(
                        ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                        actor_id="admin-7",
                    )

                self.tx.commit.assert_called_once_with(transition=ANY)
                self.output.present.assert_not_called()

    def test_invalid_user_id_is_rejected_before_opening_scope(self) -> None:
        for user_id in ("", " \t\n", None, 42):
            with self.subTest(user_id=user_id):
                self.output.reset_mock()

                returned = self.use_case.execute(
                    ChangeUserStatusRequest(user_id, "suspended", expected_version=9),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_not_called()
                self.tx.commit.assert_not_called()
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("invalid_user_id"))

    def test_invalid_status_is_rejected_without_normalization_or_opening_scope(self) -> None:
        for status in ("", "ACTIVE", " suspended ", "disabled", None, 1, True, ["active"]):
            with self.subTest(status=status):
                self.output.reset_mock()

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", status, expected_version=9),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_not_called()
                self.tx.commit.assert_not_called()
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("invalid_status"))

    def test_invalid_version_is_rejected_without_coercion_or_opening_scope(self) -> None:
        for version in (-1, "9", 9.0, True, False, None):
            with self.subTest(version=version):
                self.output.reset_mock()

                returned = self.use_case.execute(
                    ChangeUserStatusRequest("user-42", "suspended", expected_version=version),
                    actor_id="admin-7",
                )

                self.assertIsNone(returned)
                self.uow.begin.assert_not_called()
                self.tx.commit.assert_not_called()
                self.output.present.assert_called_once_with(ChangeUserStatusFailure("invalid_version"))

    def test_multiple_invalid_fields_observe_user_id_status_version_priority(self) -> None:
        # Tests already-present validation order, including the earlier coverage gap.
        for request, code in (
            (ChangeUserStatusRequest("", "ACTIVE", -1), "invalid_user_id"),
            (ChangeUserStatusRequest("user-42", "ACTIVE", -1), "invalid_status"),
        ):
            with self.subTest(request=request):
                self.output.reset_mock()

                self.assertIsNone(self.use_case.execute(request, actor_id="admin-7"))

                self.uow.begin.assert_not_called()
                self.tx.commit.assert_not_called()
                self.output.present.assert_called_once_with(ChangeUserStatusFailure(code))

    def test_nonblank_identity_is_preserved_and_zero_revision_is_valid(self) -> None:
        account = self.snapshot(user_id=" user-42 ", version=0)
        self.tx.facts.return_value = StatusChangeFacts("admin-7", self.actor, account)

        returned = self.use_case.execute(
            ChangeUserStatusRequest(" user-42 ", "suspended", expected_version=0),
            actor_id="admin-7",
        )

        self.assertIsNone(returned)
        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id=" user-42 ")
        self.tx.commit.assert_called_once_with(transition=ANY)
        transition = self.tx.commit.call_args.kwargs["transition"]
        self.assertIs(transition.before, account)
        self.assertEqual(transition.after.user_id, " user-42 ")
        self.assertEqual(transition.after.version, 1)
        self.assertIs(type(transition.after.version), int)
        self.output.present.assert_called_once_with(
            ChangeUserStatusSuccess(" user-42 ", UserAccessStatus.SUSPENDED, version=1),
        )

    def test_known_scope_failures_propagate_without_later_effects_outcome_or_retry(self) -> None:
        # Existing propagation behavior at each distinct transaction obligation.
        operations = {
            "begin": self.uow.begin, "enter": self.scope.__enter__,
            "facts": self.tx.facts, "commit": self.tx.commit, "exit": self.scope.__exit__,
        }
        for stage in operations:
            with self.subTest(stage=stage):
                self.uow.reset_mock(side_effect=True)
                self.scope.reset_mock(side_effect=True)
                self.tx.reset_mock(side_effect=True)
                self.output.reset_mock()
                failure = UserStatusManagementError("dependency unavailable")
                operations[stage].side_effect = failure

                with self.assertRaises(UserStatusManagementError) as caught:
                    self.use_case.execute(
                        ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                        actor_id="admin-7",
                    )

                self.assertIs(caught.exception, failure)
                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                if stage == "begin":
                    self.scope.__enter__.assert_not_called()
                else:
                    self.scope.__enter__.assert_called_once_with()
                if stage in ("begin", "enter"):
                    self.tx.facts.assert_not_called()
                    self.scope.__exit__.assert_not_called()
                else:
                    self.tx.facts.assert_called_once_with()
                    self.scope.__exit__.assert_called_once()
                if stage in ("begin", "enter", "facts"):
                    self.tx.commit.assert_not_called()
                else:
                    self.tx.commit.assert_called_once_with(transition=ANY)
                    transition = self.tx.commit.call_args.kwargs["transition"]
                    self.assertIs(transition.before, self.account)
                    self.assertEqual(transition.after.user_id, "user-42")
                    self.assertIs(transition.after.status, UserAccessStatus.SUSPENDED)
                    self.assertEqual(transition.after.version, 10)
                    self.assertEqual(transition.after.credential_generation, 18)
                if stage in ("facts", "commit"):
                    args = self.scope.__exit__.call_args.args
                    self.assertIs(args[0], UserStatusManagementError)
                    self.assertIs(args[1], failure)
                self.output.present.assert_not_called()

    def test_unexpected_dependency_failures_are_not_business_denials_or_retried(self) -> None:
        for stage in ("begin", "commit"):
            with self.subTest(stage=stage):
                self.uow.reset_mock(side_effect=True)
                self.tx.reset_mock(side_effect=True)
                self.output.reset_mock()
                failure = ValueError("unexpected dependency failure")
                operation = self.uow.begin if stage == "begin" else self.tx.commit
                operation.side_effect = failure

                with self.assertRaises(ValueError) as caught:
                    self.use_case.execute(
                        ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                        actor_id="admin-7",
                    )

                self.assertIs(caught.exception, failure)
                self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
                if stage == "begin":
                    self.tx.facts.assert_not_called()
                    self.tx.commit.assert_not_called()
                else:
                    self.tx.commit.assert_called_once_with(transition=ANY)
                self.output.present.assert_not_called()

    def test_presenter_failure_does_not_repeat_commit_or_reenter_scope(self) -> None:
        failure = RuntimeError("presentation unavailable")
        self.output.present.side_effect = failure

        with self.assertRaises(RuntimeError) as caught:
            self.use_case.execute(
                ChangeUserStatusRequest("user-42", "suspended", expected_version=9),
                actor_id="admin-7",
            )

        self.assertIs(caught.exception, failure)
        self.uow.begin.assert_called_once_with(actor_id="admin-7", user_id="user-42")
        self.tx.commit.assert_called_once_with(transition=ANY)
        self.scope.__exit__.assert_called_once_with(None, None, None)
        self.output.present.assert_called_once_with(
            ChangeUserStatusSuccess("user-42", UserAccessStatus.SUSPENDED, version=10),
        )


if __name__ == "__main__":
    unittest.main()
