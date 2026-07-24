"""MinIO client lifecycle adapter."""

import asyncio
from pathlib import Path

import urllib3
from minio import Minio
from minio.error import S3Error

from bid_system.platform.config import MinioSettings

MISSING_OBJECT_ERROR_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NotFound"})


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

    async def stat_size(self, object_key: str) -> int | None:
        """Return an object's byte length or None when it does not exist."""
        try:
            result = await asyncio.to_thread(
                self.client.stat_object,
                self._bucket,
                object_key,
            )
        except S3Error as error:
            if error.code in MISSING_OBJECT_ERROR_CODES:
                return None
            raise
        return result.size

    async def put_file(
        self,
        *,
        object_key: str,
        path: Path,
        size_bytes: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        """Upload one sized local file without loading it into memory."""

        def upload() -> None:
            resolved_metadata: dict[str, str | list[str] | tuple[str]] = dict(metadata)
            with path.open("rb") as stream:
                self.client.put_object(
                    self._bucket,
                    object_key,
                    stream,
                    size_bytes,
                    content_type=content_type,
                    metadata=resolved_metadata,
                )

        await asyncio.to_thread(upload)

    def object_uri(self, object_key: str) -> str:
        """Return a stable private URI rather than an expiring presigned URL."""
        return f"minio://{self._bucket}/{object_key}"

    async def close(self) -> None:
        """Clear all connections owned by the explicit HTTP pool."""
        self._pool.clear()


def create_minio_resource(settings: MinioSettings) -> MinioResource:
    """Construct an unconnected MinIO resource."""
    return MinioResource(settings)
