"""Sanitized PostgreSQL health probe."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def probe_database(engine: AsyncEngine) -> None:
    """Verify that PostgreSQL can accept and execute a minimal query."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
