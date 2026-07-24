"""Local staging, content detection, and canonical PDF metadata tests."""

import zipfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from bid_system.modules.documents.domain.errors import (
    EncryptedDocumentError,
    FileSizeLimitExceededError,
    UnsupportedDocumentTypeError,
)
from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.modules.documents.infrastructure.file_processing import (
    CanonicalPdfMetadataParser,
    ContentFileTypeDetector,
    StreamingUploadStager,
)


class BytesUploadSource:
    def __init__(self, content: bytes, filename: str) -> None:
        self.filename = filename
        self._content = content
        self._offset = 0
        self.requested_sizes: list[int] = []

    async def read(self, size: int) -> bytes:
        self.requested_sizes.append(size)
        chunk = self._content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class RecordingConverter:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.calls: list[tuple[Path, DocumentFormat, Path]] = []

    async def convert(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> Path:
        self.calls.append((source_path, file_format, workspace))
        return self.output


def _write_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)


def _write_ooxml(path: Path, marker: str) -> None:
    content_type = (
        "application/vnd.openxmlformats-officedocument."
        + (
            "wordprocessingml.document.main+xml"
            if marker.startswith("word/")
            else "presentationml.presentation.main+xml"
        )
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                f'<Override PartName="/{marker}" ContentType="{content_type}"/>'
                "</Types>"
            ),
        )
        archive.writestr(marker, "<root />")


@pytest.mark.asyncio
async def test_stager_never_reads_more_than_configured_chunk_and_hashes_content(
    tmp_path: Path,
) -> None:
    source = BytesUploadSource(b"abcdef", "..\\unsafe/name.pdf")
    stager = StreamingUploadStager(max_file_bytes=10, read_chunk_bytes=2)

    staged = await stager.stage(source, tmp_path)

    assert source.requested_sizes == [2, 2, 2, 2]
    assert staged.path.read_bytes() == b"abcdef"
    assert staged.normalized_name == "name.pdf"
    assert staged.sha256 == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"


@pytest.mark.asyncio
async def test_stager_rejects_bytes_beyond_total_limit(tmp_path: Path) -> None:
    source = BytesUploadSource(b"abcd", "file.pdf")
    stager = StreamingUploadStager(max_file_bytes=3, read_chunk_bytes=2)

    with pytest.raises(FileSizeLimitExceededError):
        await stager.stage(source, tmp_path)


@pytest.mark.asyncio
async def test_type_detector_uses_content_instead_of_extension(tmp_path: Path) -> None:
    source = tmp_path / "actually-not-a-pdf.pdf"
    source.write_bytes(b"plain text")

    with pytest.raises(UnsupportedDocumentTypeError):
        await ContentFileTypeDetector().detect(source)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("word/document.xml", DocumentFormat.DOCX),
        ("ppt/presentation.xml", DocumentFormat.PPTX),
    ],
)
async def test_type_detector_recognizes_ooxml_structure(
    tmp_path: Path,
    marker: str,
    expected: DocumentFormat,
) -> None:
    source = tmp_path / "source.bin"
    _write_ooxml(source, marker)

    assert await ContentFileTypeDetector().detect(source) is expected


@pytest.mark.asyncio
async def test_type_detector_rejects_spoofed_ooxml_marker_without_content_type(
    tmp_path: Path,
) -> None:
    source = tmp_path / "spoofed.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<root />")

    with pytest.raises(UnsupportedDocumentTypeError):
        await ContentFileTypeDetector().detect(source)


@pytest.mark.asyncio
async def test_type_detector_routes_encrypted_office_container_to_encryption_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "encrypted.docx"
    source.write_bytes(
        bytes.fromhex("D0CF11E0A1B11AE1") + b"EncryptionInfo\x00EncryptedPackage"
    )

    with pytest.raises(EncryptedDocumentError):
        await ContentFileTypeDetector().detect(source)


@pytest.mark.asyncio
async def test_pdf_parser_counts_pages_without_conversion(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source, pages=3)
    converter = RecordingConverter(tmp_path / "unused.pdf")
    ticks = iter((1_000_000_000, 1_026_000_000))
    parser = CanonicalPdfMetadataParser(
        converter=converter,
        monotonic_ns=lambda: next(ticks),
    )

    parsed = await parser.parse(source, DocumentFormat.PDF, tmp_path)

    assert parsed.page_count == 3
    assert parsed.normalized_pdf_path == source
    assert parsed.parse_duration_ms == 26
    assert converter.calls == []


@pytest.mark.asyncio
async def test_office_parser_counts_pages_from_persistable_converted_pdf(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(b"source")
    converted = tmp_path / "normalized.pdf"
    _write_pdf(converted, pages=4)
    converter = RecordingConverter(converted)
    ticks = iter((2_000_000_000, 2_030_000_000))
    parser = CanonicalPdfMetadataParser(
        converter=converter,
        monotonic_ns=lambda: next(ticks),
    )

    parsed = await parser.parse(source, DocumentFormat.DOCX, tmp_path)

    assert parsed.page_count == 4
    assert parsed.normalized_pdf_path == converted
    assert parsed.parse_duration_ms == 30
    assert converter.calls == [(source, DocumentFormat.DOCX, tmp_path)]
