"""Register behavior through the Input Boundary and application-owned ports.

Uses real domain validation/policy and autospecced deferred adapters/Presenter.
Retains existing behavioral cases; Entity/ID creation, result guards and bounded
collision recovery were added test-first. Failure propagation cases also cover
existing wiring without manufactured red. Store uniqueness, zero-effects collision
and immediate-login guarantees need adapter/integration tests.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, create_autospec

from contexts.iam.application.modules.credentials.ports import (
    InvalidHashResult, PasswordHasher, PasswordHashingError,
)
from contexts.iam.application.modules.registration.ports import (
    GeneratedUserIdCollision, IdentityConflict, InvalidGeneratedUserIdResult,
    InvalidIdentityConflictResult, InvalidRegisteredUserResult, RegisteredUser,
    UserIdGenerationError, UserIdGenerator, UserRegistrationError, UserRegistrationStore,
)
from contexts.iam.application.modules.registration.use_cases.register.input_boundary import RegisterInputBoundary
from contexts.iam.application.modules.registration.use_cases.register.interactor import RegisterInteractor
from contexts.iam.application.modules.registration.use_cases.register.output_boundary import RegisterOutputBoundary
from contexts.iam.application.modules.registration.use_cases.register.request import RegisterRequest
from contexts.iam.application.modules.registration.use_cases.register.response import (
    RegistrationFailure, RegistrationSuccess,
)
from contexts.iam.domain.identity.user_account import UserAccount as AccountAccess
from contexts.iam.domain.identity.user_access_status import UserAccessStatus


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.hasher = create_autospec(PasswordHasher, instance=True, spec_set=True)
        self.hasher.hash.return_value = "hashed-value"
        self.identities = create_autospec(UserIdGenerator, instance=True, spec_set=True)
        self.identities.generate.return_value = "id-123"
        self.users = create_autospec(UserRegistrationStore, instance=True, spec_set=True)
        self.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.users.create.return_value = RegisteredUser(
            "id-123", "alice1", "alice@example.com", self.created_at,
        )
        self.output = create_autospec(RegisterOutputBoundary, instance=True, spec_set=True)
        self.interactor: RegisterInputBoundary = RegisterInteractor(
            self.hasher, self.identities, self.users, self.output,
        )
        self.request = RegisterRequest("Alice1", "Alice@Example.COM", "LongPassword123!")

    def assert_creation_write(self, username, email, password_hash, *, user_id="id-123"):
        self.users.create.assert_called_once_with(account=ANY)
        account = self.users.create.call_args.kwargs["account"]
        self.assertIsInstance(account, AccountAccess)
        self.assertEqual(account.username.value, username)
        self.assertEqual(account.email.value, email)
        self.assertEqual(account.password_hash, password_hash)
        self.assertEqual(account.user_id, user_id)
        self.assertIs(account.status, UserAccessStatus.ACTIVE)
        self.assertEqual(account.version, 0)
        self.assertIs(type(account.version), int)
        self.assertEqual(account.credential_generation, 0)
        self.assertIs(type(account.credential_generation), int)
        self.assertIs(account.admin_eligible, False)

    def assert_creation_attempts(self, user_ids):
        self.assertEqual(self.users.create.call_count, len(user_ids))
        for call, expected_id in zip(self.users.create.call_args_list, user_ids):
            self.assertEqual(call.args, ())
            self.assertEqual(set(call.kwargs), {"account"})
            account = call.kwargs["account"]
            self.assertIsInstance(account, AccountAccess)
            self.assertEqual(account.username.value, "alice1")
            self.assertEqual(account.email.value, "alice@example.com")
            self.assertEqual(account.password_hash, "hashed-value")
            self.assertEqual(account.user_id, expected_id)
            self.assertIs(account.status, UserAccessStatus.ACTIVE)
            self.assertEqual(account.version, 0)
            self.assertEqual(account.credential_generation, 0)
            self.assertIs(account.admin_eligible, False)

    def reset_ports(self):
        self.hasher.reset_mock()
        self.identities.reset_mock()
        self.users.reset_mock()
        self.output.reset_mock()

    def assert_rejection_without_hash_or_write(self, request, code):
        returned = self.interactor.execute(request)

        self.assertIsNone(returned)
        self.output.present.assert_called_once_with(RegistrationFailure(code))
        self.hasher.hash.assert_not_called()
        self.identities.generate.assert_not_called()
        self.users.create.assert_not_called()

    def test_complete_entity_is_the_only_creation_write_model(self):
        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.users.create.assert_called_once_with(account=ANY)
        account = self.users.create.call_args.kwargs["account"]
        self.assertIsInstance(account, AccountAccess)
        self.assertEqual(account.user_id, "id-123")
        self.assertEqual(account.username.value, "alice1")
        self.assertEqual(account.email.value, "alice@example.com")
        self.assertEqual(account.password_hash, "hashed-value")
        self.assertNotIn("hashed-value", repr(account))
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "id-123", "alice1", "alice@example.com", self.created_at,
        ))

    def test_allocated_identity_and_non_admin_entity_reach_store(self):
        self.identities.generate.return_value = "allocated-user-71"
        self.users.create.return_value = RegisteredUser(
            "allocated-user-71", "alice1", "alice@example.com", self.created_at,
        )

        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.identities.generate.assert_called_once_with()
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write(
            "alice1", "alice@example.com", "hashed-value", user_id="allocated-user-71",
        )
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "allocated-user-71", "alice1", "alice@example.com", self.created_at,
        ))

    def test_id_collisions_can_recover_on_third_attempt_without_rehashing(self):
        self.identities.generate.side_effect = ["collision-1", "collision-2", "fresh-3"]
        self.users.create.side_effect = [
            GeneratedUserIdCollision("first candidate already exists"),
            GeneratedUserIdCollision("second candidate already exists"),
            RegisteredUser("fresh-3", "alice1", "alice@example.com", self.created_at),
        ]

        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.assertEqual(self.identities.generate.call_count, 3)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1", "collision-2", "fresh-3"])
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "fresh-3", "alice1", "alice@example.com", self.created_at,
        ))

    def test_id_collision_recovery_stops_after_three_attempts_without_outcome(self):
        self.identities.generate.side_effect = [
            "collision-1", "collision-2", "collision-3", "must-not-be-used-4",
        ]
        self.users.create.side_effect = GeneratedUserIdCollision("candidate already exists")

        with self.assertRaises(UserRegistrationError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(type(caught.exception), UserRegistrationError)
        self.assertEqual(self.identities.generate.call_count, 3)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1", "collision-2", "collision-3"])
        self.output.present.assert_not_called()

    def test_generator_failure_propagates_without_a_write_or_retry(self):
        # Existing propagation behavior through the newly injected port.
        for failure in (UserIdGenerationError("generator unavailable"), ValueError("unexpected")):
            with self.subTest(error_type=type(failure).__name__):
                self.reset_ports()
                self.identities.generate.side_effect = failure

                with self.assertRaises(type(failure)) as caught:
                    self.interactor.execute(self.request)

                self.assertIs(caught.exception, failure)
                self.identities.generate.assert_called_once_with()
                self.hasher.hash.assert_called_once_with("LongPassword123!")
                self.users.create.assert_not_called()
                self.output.present.assert_not_called()

    def test_generator_failure_during_recovery_stops_before_another_write(self):
        # Existing recovery wiring; failure is not another collision retry.
        failure = UserIdGenerationError("generator unavailable during recovery")
        self.identities.generate.side_effect = ["collision-1", failure]
        self.users.create.side_effect = GeneratedUserIdCollision("candidate already exists")

        with self.assertRaises(UserIdGenerationError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.assertEqual(self.identities.generate.call_count, 2)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1"])
        self.output.present.assert_not_called()

    def test_uncertain_storage_failure_during_recovery_is_not_retried(self):
        # Existing specific-exception recovery, not catch-all retry.
        failure = UserRegistrationError("commit certainty unknown")
        self.identities.generate.side_effect = ["collision-1", "candidate-2", "must-not-be-used-3"]
        self.users.create.side_effect = [GeneratedUserIdCollision("candidate exists"), failure]

        with self.assertRaises(UserRegistrationError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.assertEqual(self.identities.generate.call_count, 2)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1", "candidate-2"])
        self.output.present.assert_not_called()

    def test_identity_conflict_after_id_collision_ends_recovery_without_another_attempt(self):
        # Existing expected-result handling after recoverable dependency failure.
        for field, code in (("username", "username_taken"), ("email", "email_taken")):
            with self.subTest(field=field):
                self.reset_ports()
                self.identities.generate.side_effect = [
                    "collision-1", "candidate-2", "must-not-be-used-3",
                ]
                self.users.create.side_effect = [
                    GeneratedUserIdCollision("candidate already exists"), IdentityConflict(field),
                ]

                self.assertIsNone(self.interactor.execute(self.request))

                self.assertEqual(self.identities.generate.call_count, 2)
                self.hasher.hash.assert_called_once_with("LongPassword123!")
                self.assert_creation_attempts(["collision-1", "candidate-2"])
                self.output.present.assert_called_once_with(RegistrationFailure(code))

    def test_success_on_second_attempt_stops_recovery_immediately(self):
        # Existing bounded recovery; successful creation is never retried.
        self.identities.generate.side_effect = ["collision-1", "fresh-2", "must-not-be-used-3"]
        self.users.create.side_effect = [
            GeneratedUserIdCollision("candidate already exists"),
            RegisteredUser("fresh-2", "alice1", "alice@example.com", self.created_at),
        ]

        self.assertIsNone(self.interactor.execute(self.request))

        self.assertEqual(self.identities.generate.call_count, 2)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1", "fresh-2"])
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "fresh-2", "alice1", "alice@example.com", self.created_at,
        ))

    def test_malformed_id_during_recovery_stops_before_another_write(self):
        # Existing factory/result guard also applies to a recovered attempt.
        self.identities.generate.side_effect = ["collision-1", None]
        self.users.create.side_effect = GeneratedUserIdCollision("candidate already exists")

        with self.assertRaises(InvalidGeneratedUserIdResult):
            self.interactor.execute(self.request)

        self.assertEqual(self.identities.generate.call_count, 2)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_attempts(["collision-1"])
        self.output.present.assert_not_called()

    def test_malformed_generated_id_is_system_failure_before_storage(self):
        for user_id in ("", " \t\n", None, 42, True, b"id"):
            with self.subTest(result_type=type(user_id).__name__):
                self.reset_ports()
                self.identities.generate.return_value = user_id

                with self.assertRaises(InvalidGeneratedUserIdResult):
                    self.interactor.execute(self.request)

                self.hasher.hash.assert_called_once_with("LongPassword123!")
                self.identities.generate.assert_called_once_with()
                self.users.create.assert_not_called()
                self.output.present.assert_not_called()

    def test_store_success_for_another_identity_is_system_failure_without_retry(self):
        for user_id in ("different-user-99", "", None, True):
            with self.subTest(user_id=user_id):
                self.reset_ports()
                self.users.create.return_value = RegisteredUser(
                    user_id, "alice1", "alice@example.com", self.created_at,
                )

                with self.assertRaises(InvalidRegisteredUserResult):
                    self.interactor.execute(self.request)

                self.identities.generate.assert_called_once_with()
                self.hasher.hash.assert_called_once_with("LongPassword123!")
                self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
                self.output.present.assert_not_called()

    def test_success_must_match_entity_identity_and_have_an_aware_creation_time(self):
        for saved in (
            RegisteredUser("id-123", "other-user", "alice@example.com", self.created_at),
            RegisteredUser("id-123", "alice1", "other@example.com", self.created_at),
            RegisteredUser("id-123", "alice1", "alice@example.com", datetime(2025, 1, 1)),
            RegisteredUser("id-123", "alice1", "alice@example.com", None),
        ):
            with self.subTest(saved=saved):
                self.reset_ports()
                self.users.create.return_value = saved

                with self.assertRaises(InvalidRegisteredUserResult):
                    self.interactor.execute(self.request)

                self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
                self.identities.generate.assert_called_once_with()
                self.output.present.assert_not_called()

    def test_invalid_username_is_presented_before_hash_or_write(self):
        for username in ("ab", "x"):
            with self.subTest(username=username):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(username, self.request.email, self.request.password),
                    "invalid_username",
                )

    def test_username_with_outer_spaces_is_rejected_before_hash_or_write(self):
        for username in (" Alice1", "Alice1 ", " Alice1 "):
            with self.subTest(username=repr(username)):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(username, "alice@example.com", "LongPassword123!"),
                    "invalid_username",
                )

    def test_username_with_underscore_is_rejected_before_hash_or_write(self):
        for username in ("alice_1", "_alice1", "alice1_"):
            with self.subTest(username=username):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(username, "alice@example.com", "LongPassword123!"),
                    "invalid_username",
                )

    def test_username_starting_with_digit_is_rejected_before_hash_or_write(self):
        for username in ("1alice", "12345"):
            with self.subTest(username=username):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(username, "alice@example.com", "LongPassword123!"),
                    "invalid_username",
                )

    def test_invalid_email_is_presented_before_hash_or_write(self):
        for email in ("not-an-email", "alice @example.com", "alice@ example.com", "bad-email"):
            with self.subTest(email=email):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(self.request.username, email, self.request.password),
                    "invalid_email",
                )

    def test_email_with_outer_spaces_is_rejected_before_hash_or_write(self):
        for email in (" alice@example.com", "alice@example.com ", " alice@example.com "):
            with self.subTest(email=repr(email)):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest("alice1", email, "LongPassword123!"),
                    "invalid_email",
                )

    def test_invalid_password_is_presented_before_hash_or_write(self):
        for password in (
            "short", "Long Password123!", " LongPassword123!", "LongPassword123! ",
            "Long\tPassword123!", "Long\nPassword123!", "Long\u00a0Password123!",
        ):
            with self.subTest(password=repr(password)):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest(self.request.username, self.request.email, password),
                    "invalid_password",
                )

    def test_password_matching_username_is_rejected_before_hash_or_write(self):
        for password in ("LongUsername12345", "longusername12345", "LONGUSERNAME12345"):
            with self.subTest(password=password):
                self.reset_ports()
                self.assert_rejection_without_hash_or_write(
                    RegisterRequest("LongUsername12345", "alice@example.com", password),
                    "invalid_password",
                )

    def test_multiple_invalid_fields_present_username_rejection_first(self):
        self.assert_rejection_without_hash_or_write(
            RegisterRequest("x", "bad-email", "short"), "invalid_username",
        )

    def test_distinct_password_is_hashed_unchanged_through_real_policy(self):
        self.users.create.return_value = RegisteredUser(
            "id-123", "longusername12345", "alice@example.com", self.created_at,
        )
        request = RegisterRequest(
            "LongUsername12345", "Alice@Example.COM", "LONGUSERNAME12345!",
        )

        returned = self.interactor.execute(request)

        self.assertIsNone(returned)
        self.hasher.hash.assert_called_once_with("LONGUSERNAME12345!")
        self.assert_creation_write(
            "longusername12345", "alice@example.com", "hashed-value",
        )
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "id-123", "longusername12345", "alice@example.com", self.created_at,
        ))

    def test_empty_hash_raises_without_write_or_present(self):
        self.hasher.hash.return_value = ""

        with self.assertRaises(InvalidHashResult):
            self.interactor.execute(self.request)

        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.identities.generate.assert_not_called()
        self.users.create.assert_not_called()
        self.output.present.assert_not_called()

    def test_non_string_hash_is_system_failure_without_write_or_presentation(self):
        for password_hash in (None, True, 123, b"hash", ["hash"]):
            with self.subTest(result_type=type(password_hash).__name__):
                self.reset_ports()
                self.hasher.hash.return_value = password_hash

                with self.assertRaises(InvalidHashResult):
                    self.interactor.execute(self.request)

                self.hasher.hash.assert_called_once_with("LongPassword123!")
                self.identities.generate.assert_not_called()
                self.users.create.assert_not_called()
                self.output.present.assert_not_called()

    def test_hasher_failure_propagates_without_write_or_presentation(self):
        failure = PasswordHashingError("hash unavailable")
        self.hasher.hash.side_effect = failure

        with self.assertRaises(PasswordHashingError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.identities.generate.assert_not_called()
        self.users.create.assert_not_called()
        self.output.present.assert_not_called()

    def test_store_failure_propagates_without_presentation(self):
        failure = UserRegistrationError("store unavailable")
        self.users.create.side_effect = failure

        with self.assertRaises(UserRegistrationError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_not_called()

    def test_unexpected_dependency_failure_propagates_without_false_outcome(self):
        # ValueError variants plus archived RuntimeError outages are distinct cases.
        for dependency, failure in (
            ("hasher", ValueError("unexpected backend failure")),
            ("store", ValueError("unexpected backend failure")),
            ("hasher", RuntimeError("hash unavailable")),
            ("store", RuntimeError("database unavailable")),
        ):
            with self.subTest(dependency=dependency, error_type=type(failure).__name__):
                self.reset_ports()
                self.hasher.hash.side_effect = None
                self.users.create.side_effect = None
                operation = self.hasher.hash if dependency == "hasher" else self.users.create
                operation.side_effect = failure

                with self.assertRaises(type(failure)) as caught:
                    self.interactor.execute(self.request)

                self.assertIs(caught.exception, failure)
                self.hasher.hash.assert_called_once_with("LongPassword123!")
                if dependency == "hasher":
                    self.identities.generate.assert_not_called()
                    self.users.create.assert_not_called()
                else:
                    self.assert_creation_write(
                        "alice1", "alice@example.com", "hashed-value",
                    )
                self.output.present.assert_not_called()

    def test_username_conflict_is_presented_once(self):
        self.users.create.return_value = IdentityConflict("username")

        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_called_once_with(RegistrationFailure("username_taken"))

    def test_email_conflict_is_presented_once(self):
        self.users.create.return_value = IdentityConflict("email")

        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_called_once_with(RegistrationFailure("email_taken"))

    def test_undeclared_identity_conflict_raises_without_presenting(self):
        # Uses today's declared exception rather than the obsolete archive ValueError.
        self.users.create.return_value = IdentityConflict("other")

        with self.assertRaises(InvalidIdentityConflictResult):
            self.interactor.execute(self.request)

        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_not_called()

    def test_undeclared_store_result_propagates_without_presentation(self):
        self.users.create.return_value = object()

        with self.assertRaises(TypeError):
            self.interactor.execute(self.request)

        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_not_called()

    def test_presentation_failure_does_not_retry_committed_registration(self):
        failure = RuntimeError("presentation unavailable")
        self.output.present.side_effect = failure

        with self.assertRaises(RuntimeError) as caught:
            self.interactor.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "id-123", "alice1", "alice@example.com", self.created_at,
        ))

    def test_identity_creation_state_reaches_store_with_canonical_identity_and_hash(self):
        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.users.create.assert_called_once()
        args, kwargs = self.users.create.call_args
        self.assertEqual(args, ())
        self.assertEqual(set(kwargs), {"account"})
        account = kwargs["account"]
        self.assertIsInstance(account, AccountAccess)
        self.assertEqual(account.username.value, "alice1")
        self.assertEqual(account.email.value, "alice@example.com")
        self.assertEqual(account.password_hash, "hashed-value")
        self.assertEqual(account.user_id, "id-123")
        self.assertIs(account.status, UserAccessStatus.ACTIVE)
        self.assertEqual(account.version, 0)
        self.assertEqual(account.credential_generation, 0)
        self.assertIs(type(account.credential_generation), int)
        self.assertIs(account.admin_eligible, False)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "id-123", "alice1", "alice@example.com", self.created_at,
        ))

    def test_registered_user_is_presented_once_with_canonical_identity_without_password(self):
        returned = self.interactor.execute(self.request)

        self.assertIsNone(returned)
        self.hasher.hash.assert_called_once_with("LongPassword123!")
        self.assert_creation_write("alice1", "alice@example.com", "hashed-value")
        self.output.present.assert_called_once_with(RegistrationSuccess(
            "id-123", "alice1", "alice@example.com", self.created_at,
        ))
        self.assertNotIn("LongPassword123!", repr(self.output.present.call_args))
        self.assertNotIn("LongPassword123!", repr(self.request))


if __name__ == "__main__":
    unittest.main()
