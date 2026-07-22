"""Identity persistence ownership and schema contract."""

from bid_system.modules.identity.infrastructure.models import IDENTITY_SCHEMA
from bid_system.platform.database.models import OrmBase


def test_identity_schema_owns_normalized_rbac_and_refresh_tables() -> None:
    expected = {
        "identity_account",
        "tenant_membership",
        "permission",
        "role",
        "role_permission",
        "membership_role",
        "refresh_session",
    }

    actual = {
        table.name for table in OrmBase.metadata.tables.values() if table.schema == IDENTITY_SCHEMA
    }

    assert expected.issubset(actual)


def test_refresh_session_persists_digest_but_never_raw_token() -> None:
    table = OrmBase.metadata.tables[f"{IDENTITY_SCHEMA}.refresh_session"]

    assert "token_digest" in table.c
    assert "refresh_token" not in table.c
    assert table.c.token_digest.unique is True

