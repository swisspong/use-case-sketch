"""Shared Identity Entity/Policy contracts; real domain behavior, no domain mocks."""

import unittest
from dataclasses import FrozenInstanceError

from contexts.iam.domain.identity.user_account import (
    UserAccount as AccountAccess, AccountAccessRejection,
    UserAccountTransition as AccountAccessTransition,
    InvalidUserAccount as InvalidAccountAccess, InvalidAccountAccessChange, InvalidPasswordChange,
    PasswordChangeRejection, LoginEligibility, CredentialEligibility, InvalidAccountDecisionFacts,
)
from contexts.iam.domain.identity.policies import (
    IdentityStatusPolicy, IdentityStatusRejection, InvalidIdentityStatusFacts,
)
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import (
    Email, InvalidRegistrationValue, Password,
)


def identity_values():
    return dict(
        username=Username.from_input("Alice71"),
        email=Email.from_input("alice@example.com"), password_hash="private-hash",
    )


class UserAccountCreationTests(unittest.TestCase):
    def test_creation_cannot_bypass_account_password_username_rule(self) -> None:
        result = AccountAccess.create(
            user_id="new-user-71", admin_eligible=False,
            username=Username.from_input("LongUsername12345"),
            email=Email.from_input("alice@example.com"), password_hash="private-hash",
            password=Password.from_input("LONGUSERNAME12345"),
        )

        self.assertEqual(result, InvalidRegistrationValue("invalid_password"))

    def test_creation_owns_canonical_identity_and_hides_password_hash(self) -> None:
        account = AccountAccess.create(
            user_id="new-user-71", admin_eligible=False,
            username=Username.from_input("Alice71"),
            email=Email.from_input("Alice@Example.COM"), password_hash="private-hash",
            password=Password.from_input("LongPassword123!"),
        )

        self.assertIsInstance(account, AccountAccess)
        self.assertEqual(account.username.value, "alice71")
        self.assertEqual(account.email.value, "alice@example.com")
        self.assertEqual(account.password_hash, "private-hash")
        self.assertNotIn("private-hash", repr(account))

    def test_account_creation_preserves_allocated_identity_and_starts_at_revision_zero(self) -> None:
        account = AccountAccess.create(
            user_id="new-user-71", admin_eligible=False, **identity_values(),
            password=Password.from_input("LongPassword123!"),
        )

        self.assertIsInstance(account, AccountAccess)
        self.assertEqual(account.user_id, "new-user-71")
        self.assertIs(account.status, UserAccessStatus.ACTIVE)
        self.assertEqual(account.version, 0)
        self.assertIs(type(account.version), int)
        self.assertEqual(account.credential_generation, 0)
        self.assertIs(type(account.credential_generation), int)
        self.assertIs(account.admin_eligible, False)

    def test_creation_validates_identity_and_eligibility_through_the_shared_factory_guards(self) -> None:
        # Existing factory guards apply on creation as well as rehydration.
        for field, value in (
            ("user_id", ""), ("user_id", " \t"), ("user_id", 42), ("user_id", None),
            ("admin_eligible", 1), ("admin_eligible", None), ("admin_eligible", "true"),
            ("password", "LongPassword123!"), ("password", None),
        ):
            with self.subTest(field=field, value=value):
                args = dict(
                    user_id="new-user-71", admin_eligible=False, **identity_values(),
                    password=Password.from_input("LongPassword123!"),
                )
                args[field] = value

                self.assertEqual(AccountAccess.create(**args), InvalidAccountAccess(field))

    def test_new_accounts_start_active_with_generation_zero(self) -> None:
        access = AccountAccess.create(
            user_id="new-user-71", admin_eligible=False, **identity_values(),
            password=Password.from_input("LongPassword123!"),
        )

        self.assertIs(access.status, UserAccessStatus.ACTIVE)
        self.assertEqual(access.credential_generation, 0)
        self.assertIs(type(access.credential_generation), int)

    def test_creation_state_rejects_overridden_defaults(self) -> None:
        # Creation defaults remain non-overridable through the Entity factory.
        for overrides in (
            {"status": UserAccessStatus.SUSPENDED},
            {"version": 9},
            {"version": True},
            {"credential_generation": 17},
            {"credential_generation": True},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(TypeError):
                AccountAccess.create(
                    user_id="new-user-71", admin_eligible=False,
                    **identity_values(), **overrides, password=Password.from_input("LongPassword123!"),
                )

    def test_creation_state_cannot_be_mutated_after_creation(self) -> None:
        # Immutable Entity; persisted state uses a separate loading path.
        access = AccountAccess.create(
            user_id="new-user-71", admin_eligible=False, **identity_values(),
            password=Password.from_input("LongPassword123!"),
        )

        for name, value in (
            ("status", UserAccessStatus.SUSPENDED),
            ("credential_generation", 17),
        ):
            with self.subTest(field=name), self.assertRaises(FrozenInstanceError):
                setattr(access, name, value)


class IdentityStatusPolicyTests(unittest.TestCase):
    def snapshot(self, **overrides) -> AccountAccess:
        values = dict(
            user_id="user-42", status=UserAccessStatus.ACTIVE, version=9,
            credential_generation=17, admin_eligible=False, **identity_values(),
        )
        values.update(overrides)
        target = AccountAccess.from_persisted(**values)
        self.assertIsInstance(target, AccountAccess)
        return target

    def decisions(self, *, target, status, expected_version):
        # Shared transition obligations at both public seams; domain stays real.
        return (
            ("entity", target.change_status(
                status=status, expected_version=expected_version,
            ), AccountAccessRejection),
            ("authorized_policy", IdentityStatusPolicy.decide(
                actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=target,
                status=status, expected_version=expected_version,
            ), IdentityStatusRejection),
        )

    def test_password_rotation_advances_revision_and_generation_for_user_and_admin(self) -> None:
        for admin_eligible in (False, True):
            with self.subTest(admin_eligible=admin_eligible):
                target = self.snapshot(admin_eligible=admin_eligible)
                decision = target.change_password(
                    password=Password.from_input("NewLongPassword123!"),
                    password_hash="new-private-hash", expected_version=9,
                )

                self.assertIsInstance(decision, AccountAccessTransition)
                self.assertIs(decision.before, target)
                self.assertEqual(decision.after.user_id, "user-42")
                self.assertEqual(decision.after.username.value, "alice71")
                self.assertEqual(decision.after.email.value, "alice@example.com")
                self.assertEqual(decision.after.password_hash, "new-private-hash")
                self.assertIs(decision.after.status, UserAccessStatus.ACTIVE)
                self.assertIs(decision.after.admin_eligible, admin_eligible)
                self.assertEqual(decision.after.version, 10)
                self.assertEqual(decision.after.credential_generation, 18)
                self.assertEqual(target.password_hash, "private-hash")
                self.assertEqual(target.version, 9)
                self.assertEqual(target.credential_generation, 17)
                self.assertNotIn("new-private-hash", repr(decision))

    def test_suspended_accounts_cannot_rotate_password_in_any_channel(self) -> None:
        for admin_eligible in (False, True):
            with self.subTest(admin_eligible=admin_eligible):
                target = self.snapshot(
                    status=UserAccessStatus.SUSPENDED, admin_eligible=admin_eligible,
                )
                result = target.change_password(
                    password=Password.from_input("NewLongPassword123!"),
                    password_hash="new-private-hash", expected_version=9,
                )

                self.assertIs(result, PasswordChangeRejection.INACTIVE)
                self.assertEqual(target.password_hash, "private-hash")
                self.assertEqual(target.version, 9)
                self.assertEqual(target.credential_generation, 17)

    def test_password_rotation_rejects_stale_revision_without_changes(self) -> None:
        target = self.snapshot()
        result = target.change_password(
            password=Password.from_input("NewLongPassword123!"),
            password_hash="new-private-hash", expected_version=8,
        )

        self.assertIs(result, PasswordChangeRejection.VERSION_CONFLICT)
        self.assertEqual(target.password_hash, "private-hash")
        self.assertEqual(target.version, 9)
        self.assertEqual(target.credential_generation, 17)

    def test_password_rotation_cannot_construct_invalid_next_state(self) -> None:
        target = self.snapshot()
        for field, value in (
            ("password", "NewLongPassword123!"), ("password", None),
            ("password_hash", ""), ("password_hash", None), ("password_hash", True),
            ("expected_version", True), ("expected_version", -1),
            ("expected_version", "9"), ("expected_version", 9.0),
        ):
            with self.subTest(field=field, value=value):
                args = dict(
                    password=Password.from_input("NewLongPassword123!"),
                    password_hash="new-private-hash", expected_version=9,
                )
                args[field] = value

                self.assertEqual(target.change_password(**args), InvalidPasswordChange(field))
                self.assertEqual(target.password_hash, "private-hash")
                self.assertEqual(target.version, 9)
                self.assertEqual(target.credential_generation, 17)

    def test_account_password_validation_shares_value_and_username_rules(self) -> None:
        username = Username.from_input("LongUsername12345")
        for raw in ("short", "Long Password123!", "LONGUSERNAME12345", None):
            with self.subTest(raw=raw):
                self.assertEqual(
                    AccountAccess.validate_password(username=username, raw=raw),
                    InvalidRegistrationValue("invalid_password"),
                )
        password = AccountAccess.validate_password(
            username=username, raw="LONGUSERNAME12345!",
        )
        self.assertIsInstance(password, Password)
        self.assertEqual(password.value, "LONGUSERNAME12345!")

    def test_rotation_cannot_bypass_account_password_username_rule(self) -> None:
        target = self.snapshot(username=Username.from_input("LongUsername12345"))
        result = target.change_password(
            password=Password.from_input("LONGUSERNAME12345"),
            password_hash="new-private-hash", expected_version=9,
        )

        self.assertEqual(result, InvalidRegistrationValue("invalid_password"))
        self.assertEqual(target.password_hash, "private-hash")
        self.assertEqual(target.version, 9)
        self.assertEqual(target.credential_generation, 17)

    def test_password_and_status_changes_share_one_revision_and_generation_owner(self) -> None:
        # Tests the combined model's existing behavior, not an artificial red.
        target = self.snapshot()
        rotation = target.change_password(
            password=Password.from_input("NewLongPassword123!"),
            password_hash="new-private-hash", expected_version=9,
        )
        self.assertIsInstance(rotation, AccountAccessTransition)
        self.assertIs(rotation.after.credential_eligibility(generation=17), CredentialEligibility.DENIED)
        self.assertIs(rotation.after.credential_eligibility(generation=18), CredentialEligibility.ALLOWED)
        stale = IdentityStatusPolicy.decide(
            actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=rotation.after,
            status=UserAccessStatus.SUSPENDED, expected_version=9,
        )
        self.assertIs(stale, IdentityStatusRejection.VERSION_CONFLICT)
        suspension = IdentityStatusPolicy.decide(
            actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=rotation.after,
            status=UserAccessStatus.SUSPENDED, expected_version=10,
        )
        self.assertIsInstance(suspension, AccountAccessTransition)
        self.assertEqual(suspension.after.version, 11)
        self.assertEqual(suspension.after.credential_generation, 19)
        self.assertEqual(suspension.after.password_hash, "new-private-hash")
        self.assertIs(suspension.after.credential_eligibility(generation=19), CredentialEligibility.DENIED)
        restoration = IdentityStatusPolicy.decide(
            actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=suspension.after,
            status=UserAccessStatus.ACTIVE, expected_version=11,
        )
        self.assertIsInstance(restoration, AccountAccessTransition)
        self.assertEqual(restoration.after.version, 12)
        self.assertEqual(restoration.after.credential_generation, 19)
        self.assertEqual(restoration.after.user_id, "user-42")
        self.assertEqual(restoration.after.username.value, "alice71")
        self.assertEqual(restoration.after.email.value, "alice@example.com")
        self.assertEqual(restoration.after.password_hash, "new-private-hash")
        self.assertTrue(restoration.after.permits_password_change())
        self.assertIs(restoration.after.credential_eligibility(generation=17), CredentialEligibility.DENIED)
        self.assertIs(restoration.after.credential_eligibility(generation=18), CredentialEligibility.DENIED)
        self.assertIs(restoration.after.credential_eligibility(generation=19), CredentialEligibility.ALLOWED)

    def test_login_eligibility_is_owned_by_the_account_not_the_adapter(self) -> None:
        for status, admin_eligible, admin_required, expected in (
            (UserAccessStatus.ACTIVE, False, False, LoginEligibility.ALLOWED),
            (UserAccessStatus.ACTIVE, False, True, LoginEligibility.DENIED),
            (UserAccessStatus.ACTIVE, True, False, LoginEligibility.ALLOWED),
            (UserAccessStatus.ACTIVE, True, True, LoginEligibility.ALLOWED),
            (UserAccessStatus.SUSPENDED, False, False, LoginEligibility.DENIED),
            (UserAccessStatus.SUSPENDED, False, True, LoginEligibility.DENIED),
            (UserAccessStatus.SUSPENDED, True, False, LoginEligibility.DENIED),
            (UserAccessStatus.SUSPENDED, True, True, LoginEligibility.DENIED),
        ):
            with self.subTest(status=status, admin=admin_eligible, requirement=admin_required):
                account = self.snapshot(status=status, admin_eligible=admin_eligible)
                self.assertIs(account.login_eligibility(admin_required=admin_required), expected)

    def test_malformed_trusted_login_requirement_never_becomes_an_account_decision(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            account = self.snapshot(status=status, admin_eligible=True)
            for requirement in (None, 0, 1, "false"):
                with self.subTest(status=status, requirement=requirement):
                    with self.assertRaises(InvalidAccountDecisionFacts):
                        account.login_eligibility(admin_required=requirement)

    def test_credential_eligibility_requires_active_account_and_exact_valid_generation(self) -> None:
        for status, recorded_generation, supplied_generation, expected in (
            (UserAccessStatus.ACTIVE, 17, 17, CredentialEligibility.ALLOWED),
            (UserAccessStatus.ACTIVE, 0, 0, CredentialEligibility.ALLOWED),
            (UserAccessStatus.SUSPENDED, 17, 17, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, 16, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, 18, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, "17", CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, 17.0, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, None, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 17, -1, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 0, False, CredentialEligibility.DENIED),
            (UserAccessStatus.ACTIVE, 1, True, CredentialEligibility.DENIED),
        ):
            with self.subTest(status=status, recorded=recorded_generation, supplied=supplied_generation):
                account = self.snapshot(status=status, credential_generation=recorded_generation)
                self.assertIs(
                    account.credential_eligibility(generation=supplied_generation), expected,
                )

    def test_rehydration_preserves_suspended_state_revision_and_generation(self) -> None:
        target = self.snapshot(status=UserAccessStatus.SUSPENDED)

        self.assertEqual(target.user_id, "user-42")
        self.assertEqual(target.username.value, "alice71")
        self.assertEqual(target.email.value, "alice@example.com")
        self.assertEqual(target.password_hash, "private-hash")
        self.assertIs(target.status, UserAccessStatus.SUSPENDED)
        self.assertEqual(target.version, 9)
        self.assertEqual(target.credential_generation, 17)
        self.assertIs(target.admin_eligible, False)

    def test_invalid_recorded_facts_return_typed_rejection_not_an_invalid_snapshot(self) -> None:
        for field, value in (
            ("user_id", ""), ("user_id", " \t"), ("user_id", 42),
            ("status", "active"), ("status", None),
            ("version", -1), ("version", True), ("version", 9.0),
            ("credential_generation", -1), ("credential_generation", True),
            ("credential_generation", "17"),
            ("admin_eligible", 1), ("admin_eligible", None),
            # Existing merged-factory guards, also checked during rehydration.
            ("username", "alice71"), ("username", None),
            ("email", "alice@example.com"), ("email", None),
            ("password_hash", ""), ("password_hash", None), ("password_hash", True),
        ):
            with self.subTest(field=field, value=value):
                values = dict(
                    user_id="user-42", status=UserAccessStatus.ACTIVE, version=9,
                    credential_generation=17, admin_eligible=False, **identity_values(),
                )
                values[field] = value

                result = AccountAccess.from_persisted(**values)

                self.assertEqual(result, InvalidAccountAccess(field))

    def test_non_admin_is_denied_before_any_target_decision(self) -> None:
        for target in (None, self.snapshot(admin_eligible=True), self.snapshot()):
            with self.subTest(target=target):
                result = IdentityStatusPolicy.decide(
                    actor=self.snapshot(user_id="ordinary-user-9", admin_eligible=False), target=target,
                    status=UserAccessStatus.SUSPENDED, expected_version=0,
                )

                self.assertIs(result, IdentityStatusRejection.ADMIN_REQUIRED)

    def test_admin_receives_missing_target_decision(self) -> None:
        result = IdentityStatusPolicy.decide(
            actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=None,
            status=UserAccessStatus.SUSPENDED, expected_version=9,
        )

        self.assertIs(result, IdentityStatusRejection.USER_NOT_FOUND)

    def test_admin_targets_are_protected_before_revision_and_already_set_checks(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            for expected_version in (0, 9):
                with self.subTest(status=status, expected_version=expected_version):
                    target = self.snapshot(admin_eligible=True, status=status)

                    for owner, result, rejections in self.decisions(
                        target=target, status=status, expected_version=expected_version,
                    ):
                        with self.subTest(owner=owner):
                            self.assertIs(result, rejections.ADMIN_TARGET_FORBIDDEN)
                            self.assertEqual(target.version, 9)
                            self.assertEqual(target.credential_generation, 17)

    def test_stale_revision_wins_over_already_matching_status(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            with self.subTest(status=status):
                target = self.snapshot(status=status)

                for owner, result, rejections in self.decisions(
                    target=target, status=status, expected_version=8,
                ):
                    with self.subTest(owner=owner):
                        self.assertIs(result, rejections.VERSION_CONFLICT)
                        self.assertEqual(target.version, 9)
                        self.assertEqual(target.credential_generation, 17)

    def test_already_matching_status_has_no_revision_or_generation_effect(self) -> None:
        for status in (UserAccessStatus.ACTIVE, UserAccessStatus.SUSPENDED):
            with self.subTest(status=status):
                target = self.snapshot(status=status)

                for owner, result, rejections in self.decisions(
                    target=target, status=status, expected_version=9,
                ):
                    with self.subTest(owner=owner):
                        self.assertIs(result, rejections.ALREADY_SET)
                        self.assertEqual(target.version, 9)
                        self.assertEqual(target.credential_generation, 17)

    def test_suspension_advances_revision_and_credential_generation_without_mutating_snapshot(self) -> None:
        target = self.snapshot()

        for owner, result, _ in self.decisions(
            target=target, status=UserAccessStatus.SUSPENDED, expected_version=9,
        ):
            with self.subTest(owner=owner):
                self.assertIsInstance(result, AccountAccessTransition)
                self.assertIs(result.before, target)
                self.assertEqual(result.after.user_id, "user-42")
                self.assertIs(result.after.status, UserAccessStatus.SUSPENDED)
                self.assertEqual(result.after.version, 10)
                self.assertIs(type(result.after.version), int)
                self.assertEqual(result.after.credential_generation, 18)
                self.assertIs(type(result.after.credential_generation), int)
                self.assertIs(result.after.admin_eligible, False)
                self.assertIs(target.status, UserAccessStatus.ACTIVE)
                self.assertEqual(target.version, 9)
                self.assertEqual(target.credential_generation, 17)

    def test_restoration_advances_revision_but_preserves_generation(self) -> None:
        target = self.snapshot(
            status=UserAccessStatus.SUSPENDED, version=10, credential_generation=18,
        )

        for owner, result, _ in self.decisions(
            target=target, status=UserAccessStatus.ACTIVE, expected_version=10,
        ):
            with self.subTest(owner=owner):
                self.assertIsInstance(result, AccountAccessTransition)
                self.assertIs(result.before, target)
                self.assertEqual(result.after.user_id, "user-42")
                self.assertIs(result.after.status, UserAccessStatus.ACTIVE)
                self.assertEqual(result.after.version, 11)
                self.assertEqual(result.after.credential_generation, 18)
                self.assertIs(target.status, UserAccessStatus.SUSPENDED)
                self.assertEqual(target.version, 10)
                self.assertEqual(target.credential_generation, 18)

    def test_entity_rejects_malformed_change_input_without_an_invalid_transition(self) -> None:
        # Existing guards, now observed directly at the Entity seam.
        target = self.snapshot()
        for field, value in (
            ("status", "suspended"), ("status", None),
            ("expected_version", True), ("expected_version", -1),
            ("expected_version", "9"), ("expected_version", 9.0),
        ):
            with self.subTest(field=field, value=value):
                args = dict(status=UserAccessStatus.SUSPENDED, expected_version=9)
                args[field] = value

                result = target.change_status(**args)

                self.assertEqual(result, InvalidAccountAccessChange(field))
                self.assertEqual(target.version, 9)
                self.assertEqual(target.credential_generation, 17)

    def test_malformed_trusted_policy_facts_are_system_failures_not_access_decisions(self) -> None:
        for field, value in (
            ("actor", 1), ("actor", "true"),
            ("actor", True), ("actor", InvalidAccountAccess("status")),
            ("status", "suspended"),
            ("status", None), ("expected_version", True),
            ("expected_version", -1), ("expected_version", "9"),
            ("target", object()),
        ):
            with self.subTest(field=field, value=value):
                facts = dict(
                    actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=self.snapshot(),
                    status=UserAccessStatus.SUSPENDED, expected_version=9,
                )
                facts[field] = value

                with self.assertRaises(InvalidIdentityStatusFacts):
                    IdentityStatusPolicy.decide(**facts)

    def test_snapshots_and_transitions_require_their_validated_factories(self) -> None:
        # Existing constructor guards; no manufactured red-green cycle.
        with self.assertRaises(TypeError):
            AccountAccess()
        with self.assertRaises(TypeError):
            AccountAccessTransition()

    def test_approved_transition_and_its_snapshots_are_immutable(self) -> None:
        # Existing immutable domain types, tested through public construction paths.
        target = self.snapshot()
        transition = IdentityStatusPolicy.decide(
            actor=self.snapshot(user_id="admin-7", admin_eligible=True), target=target,
            status=UserAccessStatus.SUSPENDED, expected_version=9,
        )
        self.assertIsInstance(transition, AccountAccessTransition)

        for instance, field, value in (
            (target, "admin_eligible", True),
            (target, "version", 0),
            (transition.after, "credential_generation", 0),
            (transition, "after", target),
        ):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(instance, field, value)


if __name__ == "__main__":
    unittest.main()
