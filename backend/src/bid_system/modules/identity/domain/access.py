"""Stable identity roles, restricted capabilities, and registration credentials."""

import re
from dataclasses import dataclass
from enum import StrEnum

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_PASSWORD_BYTES = 1_024
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
DEFAULT_TENANT_ID = "default"
MANAGER_ROLE_ID = "default-manager"
EMPLOYEE_ROLE_ID = "default-employee"


class IdentityRole(StrEnum):
    """Closed set of tenant roles exposed by the account-management contract."""

    MANAGER = "manager"
    EMPLOYEE = "employee"


class PermissionCode(StrEnum):
    """Capabilities that require more than an authenticated active membership."""

    ACCOUNTS_CREATE = "accounts.create"
    CONTENT_UPLOAD = "content.upload"
    CONTENT_MODIFY = "content.modify"


def permissions_for_role(role: IdentityRole) -> frozenset[PermissionCode]:
    """Return the explicit mutation grants for one stable role."""
    if role is IdentityRole.MANAGER:
        return frozenset(PermissionCode)
    return frozenset()


@dataclass(frozen=True)
class RegistrationCredentials:
    """Validated local username and an unmodified transient password."""

    username: str
    password: str

    @classmethod
    def create(cls, *, username: str, password: str) -> "RegistrationCredentials":
        normalized_username = username.strip().casefold()
        if not MIN_USERNAME_LENGTH <= len(normalized_username) <= MAX_USERNAME_LENGTH:
            raise ValueError("Username length is outside the supported boundary")
        if USERNAME_PATTERN.fullmatch(normalized_username) is None:
            raise ValueError("Username contains unsupported characters")
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise ValueError("Password length is outside the supported boundary")
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("Password byte length is outside the supported boundary")
        if not any(character.isalpha() for character in password):
            raise ValueError("Password must contain a letter")
        if not any(character.isdigit() for character in password):
            raise ValueError("Password must contain a digit")
        if password.casefold() == normalized_username:
            raise ValueError("Password must differ from username")
        return cls(username=normalized_username, password=password)
