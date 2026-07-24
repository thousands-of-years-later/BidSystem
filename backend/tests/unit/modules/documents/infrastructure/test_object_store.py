"""Content-addressed MinIO document storage behavior."""

from pathlib import Path

import pytest

from bid_system.modules.documents.infrastructure.object_store import (
    MinioDocumentBlobStore,
)
from bid_system.shared.contracts.errors import ExternalServiceError


class FakeObjectStoreResource:
    def __init__(self, existing_size: int | None = None) -> None:
        self.existing_size = existing_size
        self.stat_keys: list[str] = []
        self.puts: list[tuple[str, Path, int, str, dict[str, str]]] = []

    async def stat_size(self, object_key: str) -> int | None:
        self.stat_keys.append(object_key)
        return self.existing_size

    async def put_file(
        self,
        *,
        object_key: str,
        path: Path,
        size_bytes: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        self.puts.append((object_key, path, size_bytes, content_type, metadata))

    def object_uri(self, object_key: str) -> str:
        return f"minio://bucket/{object_key}"


@pytest.mark.asyncio
async def test_blob_store_uses_global_content_address(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    resource = FakeObjectStoreResource()
    store = MinioDocumentBlobStore(resource)

    uri = await store.put(
        sha256="a" * 64,
        path=source,
        content_type="application/pdf",
    )

    assert uri == f"minio://bucket/documents/sha256/aa/{'a' * 64}"
    assert resource.puts[0][2:] == (
        len(b"content"),
        "application/pdf",
        {"sha256": "a" * 64},
    )


@pytest.mark.asyncio
async def test_blob_store_reuses_existing_object_without_upload(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    resource = FakeObjectStoreResource(existing_size=len(b"content"))

    await MinioDocumentBlobStore(resource).put(
        sha256="a" * 64,
        path=source,
        content_type="application/pdf",
    )

    assert resource.puts == []


@pytest.mark.asyncio
async def test_existing_object_with_wrong_size_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    resource = FakeObjectStoreResource(existing_size=1)

    with pytest.raises(ExternalServiceError):
        await MinioDocumentBlobStore(resource).put(
            sha256="a" * 64,
            path=source,
            content_type="application/pdf",
        )

    assert resource.puts == []
