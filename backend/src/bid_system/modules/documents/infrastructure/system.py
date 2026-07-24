"""Replaceable system clock, identifiers, and temporary workspace."""

import asyncio
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

WORKSPACE_PREFIX = "bid-document-"


class LocalWorkspaceFactory:
    """Own and always clean one isolated directory per upload."""

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Path]:
        workspace = tempfile.TemporaryDirectory(prefix=WORKSPACE_PREFIX)
        try:
            yield Path(workspace.name)
        finally:
            await asyncio.to_thread(workspace.cleanup)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidGenerator:
    def new_id(self) -> UUID:
        return uuid4()
