"""Encrypted-PDF checks and fail-closed ClamAV streaming."""

import asyncio
import struct
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from bid_system.modules.documents.domain.errors import (
    EncryptedDocumentError,
    InvalidDocumentError,
    MalwareDetectedError,
)
from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.modules.documents.infrastructure.file_processing import (
    UPLOAD_READ_CHUNK_BYTES,
)
from bid_system.shared.contracts.errors import ExternalServiceError

CLAMAV_INSTREAM_COMMAND = b"zINSTREAM\x00"
CLAMAV_PING_COMMAND = b"zPING\x00"
CLAMAV_STREAM_END = struct.pack("!I", 0)
CLAMAV_RESPONSE_TERMINATOR = b"\x00"
CLAMAV_OK_SUFFIX = b": OK"
CLAMAV_FOUND_SUFFIX = b" FOUND"
CLAMAV_ERROR_SUFFIX = b" ERROR"
CLAMAV_PONG_RESPONSE = b"PONG"


class EncryptionInspector(Protocol):
    async def ensure_not_encrypted(
        self,
        path: Path,
        file_format: DocumentFormat,
    ) -> None: ...


class MalwareScanner(Protocol):
    async def ensure_clean(self, path: Path) -> None: ...


class PdfEncryptionInspector:
    """Reject encrypted PDFs before virus scanning and metadata extraction."""

    async def ensure_not_encrypted(
        self,
        path: Path,
        file_format: DocumentFormat,
    ) -> None:
        if file_format is not DocumentFormat.PDF:
            return
        await asyncio.to_thread(self._inspect_pdf, path)

    @staticmethod
    def _inspect_pdf(path: Path) -> None:
        try:
            if PdfReader(path).is_encrypted:
                raise EncryptedDocumentError
        except EncryptedDocumentError:
            raise
        except (OSError, PdfReadError, ValueError) as error:
            raise InvalidDocumentError from error


class DocumentSafetyScanner:
    """Apply deterministic encryption checks before the external malware scan."""

    def __init__(
        self,
        *,
        encryption_inspector: EncryptionInspector,
        malware_scanner: MalwareScanner,
    ) -> None:
        self._encryption_inspector = encryption_inspector
        self._malware_scanner = malware_scanner

    async def ensure_safe(self, path: Path, file_format: DocumentFormat) -> None:
        await self._encryption_inspector.ensure_not_encrypted(path, file_format)
        await self._malware_scanner.ensure_clean(path)


class ClamAvScanner:
    """Stream one local source through clamd's INSTREAM protocol."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout_seconds: float,
        chunk_bytes: int = UPLOAD_READ_CHUNK_BYTES,
    ) -> None:
        if not host.strip() or not 1 <= port <= 65_535 or timeout_seconds <= 0:
            raise ValueError("invalid ClamAV connection settings")
        if not 1 <= chunk_bytes <= UPLOAD_READ_CHUNK_BYTES:
            raise ValueError("ClamAV chunks must be between 1 byte and 1 MiB")
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._chunk_bytes = chunk_bytes

    async def ensure_clean(self, path: Path) -> None:
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                writer.write(CLAMAV_INSTREAM_COMMAND)
                with path.open("rb") as stream:
                    while chunk := await asyncio.to_thread(stream.read, self._chunk_bytes):
                        writer.write(struct.pack("!I", len(chunk)))
                        writer.write(chunk)
                        await writer.drain()
                writer.write(CLAMAV_STREAM_END)
                await writer.drain()
                response = await reader.readuntil(CLAMAV_RESPONSE_TERMINATOR)
        except (
            TimeoutError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as error:
            raise ExternalServiceError(public_message="文件安全扫描服务暂时不可用") from error
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()
        self.interpret_response(response)

    async def probe(self) -> None:
        """Verify clamd responds before accepting upload traffic."""
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                writer.write(CLAMAV_PING_COMMAND)
                await writer.drain()
                response = await reader.readuntil(CLAMAV_RESPONSE_TERMINATOR)
                if response.rstrip(CLAMAV_RESPONSE_TERMINATOR) != CLAMAV_PONG_RESPONSE:
                    raise ExternalServiceError(
                        public_message="文件安全扫描服务暂时不可用"
                    )
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as error:
            raise ExternalServiceError(public_message="文件安全扫描服务暂时不可用") from error
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

    @staticmethod
    def interpret_response(response: bytes) -> None:
        """Map clamd output without propagating a signature or server diagnostic."""
        normalized = response.rstrip(CLAMAV_RESPONSE_TERMINATOR)
        if normalized.endswith(CLAMAV_OK_SUFFIX):
            return
        if normalized.endswith(CLAMAV_FOUND_SUFFIX):
            raise MalwareDetectedError
        if normalized.endswith(CLAMAV_ERROR_SUFFIX):
            raise ExternalServiceError(public_message="文件安全扫描服务暂时不可用")
        raise ExternalServiceError(public_message="文件安全扫描服务返回异常")
