"""Password-processing capabilities shared by IAM application modules.

Registration, authentication and user management use these same hashing and
verification contracts; credentials is a module, not a new bounded context.
UserAccount/value objects own business rules. These ports obtain cryptographic
facts and do not select password rules, account defaults or state transitions.
Production adapters and algorithm/barrier integration tests remain deferred.
"""

from typing import Protocol


class PasswordHashingError(RuntimeError):
    """Hashing could not complete due to a backend failure, not invalid input."""


class InvalidHashResult(RuntimeError):
    """The hasher returned a value that cannot be used as a password hash."""


class PasswordVerificationError(RuntimeError):
    """Password verification could not complete (system failure, not mismatch)."""


class InvalidPasswordVerificationResult(RuntimeError):
    """Verifier returned a non-bool result; never treat it as a login decision."""


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        """Return a nonempty one-way password hash (prefer Argon2id), never plaintext.

        Hash the exact application-validated candidate, without normalization.
        Recognized backend failure -> hasher adapter -> PasswordHashingError ->
        Interactor propagates -> outer handler [deferred], without further writes,
        issuance, presentation or retry. Prior completed steps are not rolled back.
        Unexpected errors propagate. Empty/non-string result -> Interactor ->
        InvalidHashResult -> outer handler before using it for persistence.
        Registration hashes before ID generation/storage; self-service password
        change hashes after account lookup/current-password verification, but
        before transition commit. Callers own that orchestration, not the adapter.
        Never expose the password/hash or raw failure messages.
        """
        ...


class PasswordVerifier(Protocol):
    def verify(self, password: str, password_hash: str) -> bool:
        """Check the exact submitted secret against the stored hash; never expose it.

        Return exactly True for a match or False for a mismatch, never raise for
        that expected decision. Non-bool result -> Interactor ->
        InvalidPasswordVerificationResult -> outer handler without further hashing,
        writes, token issuance or presentation. Never coerce truthy/falsy results.
        Recognized backend/hash-processing failure (including corrupt stored hash)
        -> verifier adapter -> PasswordVerificationError -> Interactor propagates
        -> outer handler [deferred] without further effects, outcome or retry.
        Unexpected errors propagate. Password-value rules apply to new candidates,
        not retroactively to a submitted existing login/current password here.
        """
        ...

    def verify_missing(self, password: str) -> None:
        """Verify against an adapter-held dummy hash when no account matches.

        Use a valid dummy hash with comparable algorithm/cost to real accounts to
        reduce username-enumeration timing leaks; this does not promise constant time.
        Ignore the dummy comparison result; no account exists to authenticate.
        The verifier adapter translates known backend/hash-processing failures
        (including an invalid dummy hash) to PasswordVerificationError.
        The Interactor does not retry or present an outcome on failure; this
        exception and unexpected errors propagate to the outer error handler.
        """
        ...
