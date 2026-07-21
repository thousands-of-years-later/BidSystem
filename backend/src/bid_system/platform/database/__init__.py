"""PostgreSQL platform adapter."""

from bid_system.platform.database.engine import DatabaseResource, create_database_resource
from bid_system.platform.database.models import OrmBase
from bid_system.platform.database.transaction import AsyncTransactionManager

__all__ = (
    "AsyncTransactionManager",
    "DatabaseResource",
    "OrmBase",
    "create_database_resource",
)
