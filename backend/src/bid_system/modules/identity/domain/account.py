"""Local account identity facts without password cryptography implementation."""

from dataclasses import dataclass, replace
from enum import StrEnum


class AccountStatus(StrEnum):
    """Authentication availability of a local account."""

    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True)
class LocalAccount:
    """Locally authenticated account with an opaque encoded password hash."""

    user_id: str
    login_identifier: str
    password_hash: str
    status: AccountStatus
    password_version: int

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.user_id, self.login_identifier, self.password_hash)
        ):
            raise ValueError("Local account identifiers and password hash must not be blank")
        if self.password_version < 1:
            raise ValueError("Password version must be positive")

    @classmethod
    def register(
        cls,
        *,
        user_id: str,
        login_identifier: str,
        password_hash: str,
    ) -> "LocalAccount":
        normalized_identifier = login_identifier.strip().casefold()
        return cls(
            user_id=user_id,
            login_identifier=normalized_identifier,
            password_hash=password_hash,
            status=AccountStatus.ACTIVE,
            password_version=1,
        )

    @property
    def can_authenticate(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    def disable(self) -> "LocalAccount":
        return replace(self, status=AccountStatus.DISABLED)

    def replace_password(self, *, password_hash: str) -> "LocalAccount":
        return replace(
            self,
            password_hash=password_hash,
            password_version=self.password_version + 1,
        )
