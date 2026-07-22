"""Framework-neutral construction of application ports and adapters."""

from bid_system.modules.identity.application.ports import (
    IdentityAuthenticationRepository,
    IdentityReader,
    PasswordVerifier,
)
from bid_system.modules.identity.infrastructure.passwords import Argon2PasswordVerifier
from bid_system.modules.identity.infrastructure.repository import SqlAlchemyIdentityReader
from bid_system.platform.config import AuthSettings
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.security.authentication import PasswordHasher


def build_identity_reader(transaction: AsyncTransactionManager) -> IdentityReader:
    """Wire the identity query port to the caller's request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_identity_authentication_repository(
    transaction: AsyncTransactionManager,
) -> IdentityAuthenticationRepository:
    """Wire all local-authentication persistence ports to one request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_password_verifier(settings: AuthSettings) -> PasswordVerifier:
    """Wire identity password verification to the configured Argon2id adapter."""
    return Argon2PasswordVerifier(
        PasswordHasher(
            memory_cost_kib=settings.argon2_memory_cost_kib,
            time_cost=settings.argon2_time_cost,
            parallelism=settings.argon2_parallelism,
        )
    )
