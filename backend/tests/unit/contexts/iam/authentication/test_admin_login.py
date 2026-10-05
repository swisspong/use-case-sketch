"""Admin lookup/credential behavior through the real Input Boundary.

Shared contract failures/delivery are in test_login_contracts.py. These application
tests do not prove production admin eligibility or adapter guarantees.
"""

import unittest
from contextlib import AbstractContextManager
from datetime import timedelta
from unittest.mock import MagicMock, create_autospec

from contexts.iam.application.modules.authentication.ports import (
    AccountLookupError,
    AdminLoginAccountStore,
    IssuedToken,
    LoginGrantStore,
    TokenIssuanceError,
    TokenIssuer,
)
from contexts.iam.application.modules.credentials.ports import (
    PasswordVerificationError, PasswordVerifier,
)
from contexts.iam.application.modules.authentication.use_cases.admin_login.input_boundary import (
    AdminLoginInputBoundary,
)
from contexts.iam.application.modules.authentication.use_cases.admin_login.interactor import (
    AdminLoginInteractor,
)
from contexts.iam.application.modules.authentication.use_cases.admin_login.output_boundary import (
    AdminLoginOutputBoundary,
)
from contexts.iam.application.modules.authentication.use_cases.admin_login.request import AdminLoginRequest
from contexts.iam.application.modules.authentication.use_cases.admin_login.response import (
    AdminLoginFailure,
    AdminLoginSuccess,
)


from contexts.iam.domain.identity.user_account import UserAccount
from contexts.iam.domain.identity.user_access_status import UserAccessStatus
from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.value_objects import Email


class AdminLoginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.accounts = create_autospec(AdminLoginAccountStore, instance=True, spec_set=True)
        self.passwords = create_autospec(PasswordVerifier, instance=True, spec_set=True)
        self.tokens = create_autospec(TokenIssuer, instance=True, spec_set=True)
        self.output = create_autospec(AdminLoginOutputBoundary, instance=True, spec_set=True)
        self.accounts.find_admin_by_username.return_value = UserAccount.from_persisted(
            user_id="user-42", username=Username.from_input("rootops"),
            email=Email.from_input("rootops@example.com"), password_hash="stored-admin-hash",
            status=UserAccessStatus.ACTIVE, admin_eligible=True,
            version=42, credential_generation=41,
        )
        self.passwords.verify.return_value = True
        self.passwords.verify_missing.return_value = None
        self.tokens.issue.return_value = IssuedToken("opaque-admin-token")
        self.output.present.return_value = None
        self.grants = create_autospec(LoginGrantStore, instance=True, spec_set=True)
        self.scope = MagicMock(spec=AbstractContextManager)
        self.scope.__enter__.return_value = self.accounts.find_admin_by_username.return_value
        self.scope.__exit__.return_value = False
        self.grants.protect.return_value = self.scope
        self.input: AdminLoginInputBoundary = AdminLoginInteractor(
            self.accounts, self.passwords, self.tokens, self.output, grants=self.grants,
        )
        self.request = AdminLoginRequest(
            username="RootOps", password="Private Admin Password!"
        )

    def test_valid_admin_credentials_emit_one_token_for_trusted_identity(self) -> None:
        returned = self.input.execute(self.request)

        self.assertIsNone(returned)
        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify.assert_called_once_with(
            "Private Admin Password!", "stored-admin-hash"
        )
        self.tokens.issue.assert_called_once_with(
            user_id="user-42", credential_generation=41, ttl=timedelta(minutes=15),
        )
        self.output.present.assert_called_once_with(
            AdminLoginSuccess(token="opaque-admin-token")
        )
        self.passwords.verify_missing.assert_not_called()

    def test_revoked_admin_role_with_same_generation_rejects_after_protected_exit(self) -> None:
        protected = False
        exited = False

        class ScopeBoundAccount(UserAccount):
            def administrative_eligibility(account):
                self.assertTrue(protected, "Admin decision escaped the protected scope")
                return super().administrative_eligibility()

        current = ScopeBoundAccount.from_persisted(
            user_id="user-42", username=Username.from_input("rootops"),
            email=Email.from_input("rootops@example.com"), password_hash="stored-admin-hash",
            status=UserAccessStatus.ACTIVE, admin_eligible=False,
            version=43, credential_generation=41,
        )
        self.assertIsInstance(current, UserAccount)

        def enter():
            nonlocal protected
            protected = True
            return current

        def exit_scope(*args):
            nonlocal protected, exited
            self.output.present.assert_not_called()
            protected = False
            exited = True
            return False

        def present(outcome):
            self.assertTrue(exited)
            self.assertFalse(protected)

        self.scope.__enter__.side_effect = enter
        self.scope.__exit__.side_effect = exit_scope
        self.output.present.side_effect = present

        self.assertIsNone(self.input.execute(self.request))

        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify.assert_called_once_with(
            "Private Admin Password!", "stored-admin-hash",
        )
        self.grants.protect.assert_called_once_with(user_id="user-42")
        self.tokens.issue.assert_not_called()
        self.output.present.assert_called_once_with(AdminLoginFailure("invalid_credentials"))

    def test_missing_or_non_admin_lookup_rejects_without_issuing_a_token(self) -> None:
        self.accounts.find_admin_by_username.return_value = None

        self.assertIsNone(self.input.execute(self.request))

        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify_missing.assert_called_once_with("Private Admin Password!")
        self.passwords.verify.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_called_once_with(
            AdminLoginFailure(code="invalid_credentials")
        )

    def test_wrong_admin_password_rejects_without_issuing_a_token(self) -> None:
        self.passwords.verify.return_value = False
        request = AdminLoginRequest(username="RootOps", password="Wrong password")

        self.assertIsNone(self.input.execute(request))

        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify.assert_called_once_with("Wrong password", "stored-admin-hash")
        self.passwords.verify_missing.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_called_once_with(
            AdminLoginFailure(code="invalid_credentials")
        )

    def test_invalid_username_rejects_with_dummy_verification_without_lookup(self) -> None:
        request = AdminLoginRequest(username="invalid user!", password="Submitted secret")

        self.assertIsNone(self.input.execute(request))

        self.accounts.find_admin_by_username.assert_not_called()
        self.passwords.verify_missing.assert_called_once_with("Submitted secret")
        self.passwords.verify.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_called_once_with(
            AdminLoginFailure(code="invalid_credentials")
        )

    def test_account_lookup_outage_propagates_without_downstream_effects(self) -> None:
        failure = AccountLookupError("storage unavailable")
        self.accounts.find_admin_by_username.side_effect = failure

        with self.assertRaises(AccountLookupError) as caught:
            self.input.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify.assert_not_called()
        self.passwords.verify_missing.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_not_called()

    def test_real_password_verifier_failure_propagates_without_token_or_outcome(self) -> None:
        failure = PasswordVerificationError("verification unavailable")
        self.passwords.verify.side_effect = failure

        with self.assertRaises(PasswordVerificationError) as caught:
            self.input.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.passwords.verify.assert_called_once_with(
            "Private Admin Password!", "stored-admin-hash"
        )
        self.passwords.verify_missing.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_not_called()

    def test_dummy_verifier_failure_for_missing_admin_does_not_become_rejection(self) -> None:
        self.accounts.find_admin_by_username.return_value = None
        failure = PasswordVerificationError("dummy verification unavailable")
        self.passwords.verify_missing.side_effect = failure

        with self.assertRaises(PasswordVerificationError) as caught:
            self.input.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.accounts.find_admin_by_username.assert_called_once_with("rootops")
        self.passwords.verify_missing.assert_called_once_with("Private Admin Password!")
        self.passwords.verify.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_not_called()

    def test_dummy_verifier_failure_for_invalid_username_does_not_become_rejection(self) -> None:
        failure = PasswordVerificationError("dummy verification unavailable")
        self.passwords.verify_missing.side_effect = failure
        request = AdminLoginRequest(username="invalid user!", password="Submitted secret")

        with self.assertRaises(PasswordVerificationError) as caught:
            self.input.execute(request)

        self.assertIs(caught.exception, failure)
        self.accounts.find_admin_by_username.assert_not_called()
        self.passwords.verify_missing.assert_called_once_with("Submitted secret")
        self.passwords.verify.assert_not_called()
        self.tokens.issue.assert_not_called()
        self.output.present.assert_not_called()

    def test_token_issuance_failure_propagates_without_presenting_or_retrying(self) -> None:
        failure = TokenIssuanceError("issuer unavailable")
        self.tokens.issue.side_effect = failure

        with self.assertRaises(TokenIssuanceError) as caught:
            self.input.execute(self.request)

        self.assertIs(caught.exception, failure)
        self.passwords.verify.assert_called_once_with(
            "Private Admin Password!", "stored-admin-hash"
        )
        self.tokens.issue.assert_called_once_with(
            user_id="user-42", credential_generation=41, ttl=timedelta(minutes=15),
        )
        self.output.present.assert_not_called()


if __name__ == "__main__":
    unittest.main()
