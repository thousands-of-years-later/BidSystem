"""MinIO client lifecycle adapter."""

import asyncio

import urllib3
from minio import Minio

from bid_system.platform.config import MinioSettings


class MinioResource:
    """Own a MinIO client and the explicit urllib3 connection pool it uses."""

    def __init__(self, settings: MinioSettings) -> None:
        self._bucket = settings.bucket
        self._pool = urllib3.PoolManager()
        self.client = Minio(
            settings.endpoint,
            access_key=settings.access_key.get_secret_value(),
            secret_key=settings.secret_key.get_secret_value(),
            secure=settings.secure,
            http_client=self._pool,
        )

    async def probe(self) -> None:
        """Fail startup unless the configured bucket is reachable and exists."""
        exists = await asyncio.to_thread(self.client.bucket_exists, self._bucket)
        if not exists:
            raise RuntimeError(f"Configured MinIO bucket does not exist: {self._bucket}")

    async def close(self) -> None:
        """Clear all connections owned by the explicit HTTP pool."""
        self._pool.clear()


def create_minio_resource(settings: MinioSettings) -> MinioResource:
    """Construct an unconnected MinIO resource."""
    return MinioResource(settings)
