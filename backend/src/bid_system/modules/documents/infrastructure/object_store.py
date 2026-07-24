"""Global content-addressed document storage in MinIO."""

import asyncio
from pathlib import Path
from string import hexdigits
from typing import Protocol

from minio.error import S3Error
from urllib3.exceptions import HTTPError

from bid_system.shared.contracts.errors import ExternalServiceError

SHA256_LENGTH = 64
OBJECT_PREFIX = "documents"


class ObjectStoreResource(Protocol):
    async def stat_size(self, object_key: str) -> int | None: ...

    async def put_file(
        self,
        *,
        object_key: str,
        path: Path,
        size_bytes: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> None: ...

    def object_uri(self, object_key: str) -> str: ...


class MinioDocumentBlobStore:
    """Deduplicate immutable bytes in the shared document namespace."""

    def __init__(self, resource: ObjectStoreResource) -> None:
        self._resource = resource

    async def put(
        self,
        *,
        sha256: str,
        path: Path,
        content_type: str,
    ) -> str:
        if not content_type.strip():
            raise ValueError("object content type must not be blank")
        if len(sha256) != SHA256_LENGTH or any(
            character not in hexdigits for character in sha256
        ):
            raise ValueError("object digest must be SHA-256")
        size_bytes = (await asyncio.to_thread(path.stat)).st_size
        object_key = f"{OBJECT_PREFIX}/sha256/{sha256[:2]}/{sha256.lower()}"
        try:
            existing_size = await self._resource.stat_size(object_key)
            if existing_size is not None:
                if existing_size != size_bytes:
                    # WHY: a content-addressed key with a different size indicates external
                    # corruption or manual replacement and must never be silently trusted.
                    raise ExternalServiceError(
                        public_message="对象存储中的文件完整性校验失败"
                    )
                return self._resource.object_uri(object_key)
            await self._resource.put_file(
                object_key=object_key,
                path=path,
                size_bytes=size_bytes,
                content_type=content_type,
                metadata={"sha256": sha256.lower()},
            )
        except ExternalServiceError:
            raise
        except (S3Error, HTTPError, OSError) as error:
            raise ExternalServiceError(public_message="文件存储服务暂时不可用") from error
        return self._resource.object_uri(object_key)
