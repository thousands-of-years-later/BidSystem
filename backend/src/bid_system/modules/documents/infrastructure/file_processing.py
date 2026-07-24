"""Bounded local staging, content detection, and canonical PDF metadata."""

import asyncio
import hashlib
import time
import unicodedata
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from bid_system.modules.documents.application.ports import (
    ParsedDocument,
    StagedUpload,
    UploadSource,
)
from bid_system.modules.documents.domain.errors import (
    EncryptedDocumentError,
    FileSizeLimitExceededError,
    InvalidDocumentError,
    UnsupportedDocumentTypeError,
)
from bid_system.modules.documents.domain.models import DocumentFormat

UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
MAX_UPLOAD_FILE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 1_000
MAX_DOCUMENT_NAME_LENGTH = 255
MAX_CONTENT_TYPES_BYTES = 1024 * 1024
PDF_SIGNATURE = b"%PDF-"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
COMPOUND_FILE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
OOXML_CONTENT_TYPES_PATH = "[Content_Types].xml"
DOCX_MARKER_PATH = "word/document.xml"
PPTX_MARKER_PATH = "ppt/presentation.xml"
DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)
PPTX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation.main+xml"
)
PARSER_VERSION = "document-metadata-v1"


class PdfConverter(Protocol):
    """Convert a supported Office source into a local PDF."""

    async def convert(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> Path: ...


class StreamingUploadStager:
    """Copy one upload into an isolated workspace using bounded reads."""

    def __init__(
        self,
        *,
        max_file_bytes: int = MAX_UPLOAD_FILE_BYTES,
        read_chunk_bytes: int = UPLOAD_READ_CHUNK_BYTES,
    ) -> None:
        if max_file_bytes < 1 or read_chunk_bytes < 1:
            raise ValueError("staging limits must be positive")
        if read_chunk_bytes > UPLOAD_READ_CHUNK_BYTES:
            raise ValueError("upload read chunks cannot exceed 1 MiB")
        self._max_file_bytes = max_file_bytes
        self._read_chunk_bytes = read_chunk_bytes

    async def stage(self, source: UploadSource, workspace: Path) -> StagedUpload:
        normalized_name = self._normalize_name(source.filename)
        target = workspace / "source.upload"
        digest = hashlib.sha256()
        total_bytes = 0
        with target.open("wb") as stream:
            while True:
                chunk = await source.read(self._read_chunk_bytes)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > self._max_file_bytes:
                    raise FileSizeLimitExceededError
                digest.update(chunk)
                await asyncio.to_thread(stream.write, chunk)
        if total_bytes == 0:
            raise InvalidDocumentError(public_message="文件不能为空")
        return StagedUpload(
            path=target,
            normalized_name=normalized_name,
            size_bytes=total_bytes,
            sha256=digest.hexdigest(),
        )

    @staticmethod
    def _normalize_name(filename: str) -> str:
        # WHY: uploaded names are display metadata only and must never influence local paths.
        normalized = unicodedata.normalize("NFC", filename).replace("\\", "/")
        basename = PurePosixPath(normalized).name.strip()
        if not basename or len(basename) > MAX_DOCUMENT_NAME_LENGTH:
            raise InvalidDocumentError(public_message="文件名不合法")
        return basename


class ContentFileTypeDetector:
    """Recognize canonical formats from signatures and OOXML package structure."""

    async def detect(self, path: Path) -> DocumentFormat:
        return await asyncio.to_thread(self._detect_sync, path)

    @classmethod
    def _detect_sync(cls, path: Path) -> DocumentFormat:
        with path.open("rb") as stream:
            header = stream.read(len(COMPOUND_FILE_SIGNATURE))
            if header.startswith(PDF_SIGNATURE):
                return DocumentFormat.PDF
            if header == COMPOUND_FILE_SIGNATURE:
                stream.seek(0)
                probe = stream.read(UPLOAD_READ_CHUNK_BYTES)
                if b"EncryptionInfo" in probe and b"EncryptedPackage" in probe:
                    raise EncryptedDocumentError
                raise UnsupportedDocumentTypeError
            if not header.startswith(ZIP_SIGNATURES):
                raise UnsupportedDocumentTypeError
        try:
            with zipfile.ZipFile(path) as archive:
                cls._validate_archive_limits(archive)
                names = set(archive.namelist())
                content_types = cls._read_content_types(archive)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise UnsupportedDocumentTypeError from error
        if OOXML_CONTENT_TYPES_PATH not in names:
            raise UnsupportedDocumentTypeError
        is_docx = DOCX_MARKER_PATH in names
        is_pptx = PPTX_MARKER_PATH in names
        if is_docx == is_pptx:
            raise UnsupportedDocumentTypeError
        if is_docx and (
            f"/{DOCX_MARKER_PATH}",
            DOCX_MAIN_CONTENT_TYPE,
        ) in content_types:
            return DocumentFormat.DOCX
        if is_pptx and (
            f"/{PPTX_MARKER_PATH}",
            PPTX_MAIN_CONTENT_TYPE,
        ) in content_types:
            return DocumentFormat.PPTX
        raise UnsupportedDocumentTypeError

    @staticmethod
    def _validate_archive_limits(archive: zipfile.ZipFile) -> None:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise InvalidDocumentError(public_message="文档压缩包条目过多")
        total_uncompressed = sum(entry.file_size for entry in entries)
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise InvalidDocumentError(public_message="文档解压后体积超过限制")
        for entry in entries:
            normalized_name = entry.filename.replace("\\", "/")
            if (
                normalized_name.startswith("/")
                or ".." in PurePosixPath(normalized_name).parts
            ):
                raise InvalidDocumentError(public_message="文档压缩包路径不安全")
            if entry.file_size == 0:
                continue
            compressed_size = max(entry.compress_size, 1)
            if entry.file_size / compressed_size > MAX_ARCHIVE_COMPRESSION_RATIO:
                raise InvalidDocumentError(public_message="文档压缩比异常")

    @staticmethod
    def _read_content_types(archive: zipfile.ZipFile) -> set[tuple[str, str]]:
        try:
            manifest_info = archive.getinfo(OOXML_CONTENT_TYPES_PATH)
            if manifest_info.file_size > MAX_CONTENT_TYPES_BYTES:
                raise InvalidDocumentError(public_message="文档内容类型清单过大")
            root = ElementTree.fromstring(archive.read(manifest_info))
        except (KeyError, ElementTree.ParseError, RuntimeError) as error:
            raise UnsupportedDocumentTypeError from error
        return {
            (element.attrib.get("PartName", ""), element.attrib.get("ContentType", ""))
            for element in root.iter()
            if element.tag.endswith("Override")
        }


class CanonicalPdfMetadataParser:
    """Produce and inspect the PDF consumed by every downstream parser."""

    def __init__(
        self,
        *,
        converter: PdfConverter,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._converter = converter
        self._monotonic_ns = monotonic_ns

    async def parse(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> ParsedDocument:
        started_ns = self._monotonic_ns()
        normalized_path = source_path
        if file_format is not DocumentFormat.PDF:
            normalized_path = await self._converter.convert(
                source_path,
                file_format,
                workspace,
            )
        page_count, normalized_hash = await asyncio.to_thread(
            self._read_pdf_metadata,
            normalized_path,
        )
        duration_ms = max(0, (self._monotonic_ns() - started_ns) // 1_000_000)
        return ParsedDocument(
            normalized_pdf_path=normalized_path,
            normalized_pdf_hash=normalized_hash,
            page_count=page_count,
            parser_version=PARSER_VERSION,
            parse_duration_ms=duration_ms,
        )

    @staticmethod
    def _read_pdf_metadata(path: Path) -> tuple[int, str]:
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise EncryptedDocumentError
            page_count = len(reader.pages)
        except EncryptedDocumentError:
            raise
        except (OSError, PdfReadError, ValueError) as error:
            raise InvalidDocumentError from error
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(UPLOAD_READ_CHUNK_BYTES):
                digest.update(chunk)
        return page_count, digest.hexdigest()
