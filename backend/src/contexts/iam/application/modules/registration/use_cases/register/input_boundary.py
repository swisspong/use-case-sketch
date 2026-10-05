from typing import Protocol

from .request import RegisterRequest


class RegisterInputBoundary(Protocol):
    def execute(self, request: RegisterRequest) -> None:
        """Create a committed ACTIVE account eligible for immediate separate login.

        After validation/hash, request a candidate ID through UserIdGenerator and
        create UserAccount before persistence. Its creation factory supplies
        ACTIVE/version 0/generation 0 across creation channels; registration chooses
        non-admin eligibility. Rehydration must preserve recorded state instead.
        Registration creates no token/session and needs no activation or approval.
        Recover only GeneratedUserIdCollision with guaranteed zero effects: request
        another ID, create another Entity and persist, at most 3 attempts including
        the first, hashing only once. Username/email rejection or success ends the
        branch. Exhaustion raises UserRegistrationError; other dependency/contract
        failures propagate without retry or a normal outcome to the deferred outer
        handler. An uncertain commit is never a recoverable collision.
        Send one final semantic result through RegisterOutputBoundary; return no
        second result. The store enforces atomic initialization and uniqueness;
        concrete enforcement and zero-effects guarantees remain deferred.
        """
        ...
