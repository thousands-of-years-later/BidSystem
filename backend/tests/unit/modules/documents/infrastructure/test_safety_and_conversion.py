"""Encrypted-file, malware, and LibreOffice conversion adapter tests."""

from pathlib import Path

import pytest
from pypdf import PdfWriter

from bid_system.modules.documents.domain.errors import (
    EncryptedDocumentError,
    InvalidDocumentError,
    MalwareDetectedError,
)
from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.modules.documents.infrastructure.conversion import (
    LibreOfficePdfConverter,
    ProcessResult,
)
from bid_system.modules.documents.infrastructure.safety import (
    ClamAvScanner,
    DocumentSafetyScanner,
    PdfEncryptionInspector,
)
from bid_system.shared.contracts.errors import ExternalServiceError


class RecordingMalwareScanner:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def ensure_clean(self, path: Path) -> None:
        del path
        self._calls.append("malware")


class RecordingEncryptionInspector:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def ensure_not_encrypted(
        self,
        path: Path,
        file_format: DocumentFormat,
    ) -> None:
        del path, file_format
        self._calls.append("encryption")


class FakeProcessRunner:
    def __init__(self, workspace: Path, *, exit_code: int = 0) -> None:
        self._workspace = workspace
        self._exit_code = exit_code
        self.args: tuple[str, ...] | None = None
        self.timeout_seconds: float | None = None

    async def run(
        self,
        args: tuple[str, ...],
        *,
        timeout_seconds: float,
    ) -> ProcessResult:
        self.args = args
        self.timeout_seconds = timeout_seconds
        if self._exit_code == 0:
            (self._workspace / "conversion-source.pdf").write_bytes(b"%PDF-output")
        return ProcessResult(exit_code=self._exit_code)


def _write_encrypted_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("password")
    with path.open("wb") as stream:
        writer.write(stream)


@pytest.mark.asyncio
async def test_pdf_encryption_inspector_rejects_password_protected_pdf(tmp_path: Path) -> None:
    source = tmp_path / "encrypted.pdf"
    _write_encrypted_pdf(source)

    with pytest.raises(EncryptedDocumentError):
        await PdfEncryptionInspector().ensure_not_encrypted(source, DocumentFormat.PDF)


@pytest.mark.asyncio
async def test_safety_scanner_checks_encryption_before_malware(tmp_path: Path) -> None:
    calls: list[str] = []
    scanner = DocumentSafetyScanner(
        encryption_inspector=RecordingEncryptionInspector(calls),
        malware_scanner=RecordingMalwareScanner(calls),
    )

    await scanner.ensure_safe(tmp_path / "source", DocumentFormat.DOCX)

    assert calls == ["encryption", "malware"]


def test_clamav_response_accepts_only_explicit_ok() -> None:
    ClamAvScanner.interpret_response(b"stream: OK\x00")


def test_clamav_response_rejects_detected_signature_without_exposing_it() -> None:
    with pytest.raises(MalwareDetectedError) as captured:
        ClamAvScanner.interpret_response(b"stream: Eicar-Test-Signature FOUND\x00")

    assert "Eicar" not in str(captured.value)


@pytest.mark.parametrize(
    "response",
    [
        b"stream: size limit exceeded. ERROR\x00",
        b"unexpected\x00",
    ],
)
def test_clamav_error_or_unknown_response_fails_closed(response: bytes) -> None:
    with pytest.raises(ExternalServiceError):
        ClamAvScanner.interpret_response(response)


@pytest.mark.asyncio
async def test_libreoffice_converter_uses_isolated_profile_and_expected_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.upload"
    source.write_bytes(b"office")
    runner = FakeProcessRunner(tmp_path)
    converter = LibreOfficePdfConverter(
        executable="libreoffice",
        timeout_seconds=45.0,
        runner=runner,
    )

    result = await converter.convert(source, DocumentFormat.DOCX, tmp_path)

    assert result == tmp_path / "conversion-source.pdf"
    assert runner.args is not None
    assert runner.args[0] == "libreoffice"
    assert "--headless" in runner.args
    assert "--convert-to" in runner.args
    assert any(argument.startswith("-env:UserInstallation=") for argument in runner.args)
    assert runner.timeout_seconds == 45.0


@pytest.mark.asyncio
async def test_libreoffice_nonzero_exit_is_invalid_document(tmp_path: Path) -> None:
    source = tmp_path / "source.upload"
    source.write_bytes(b"broken")
    converter = LibreOfficePdfConverter(
        executable="libreoffice",
        timeout_seconds=45.0,
        runner=FakeProcessRunner(tmp_path, exit_code=1),
    )

    with pytest.raises(InvalidDocumentError):
        await converter.convert(source, DocumentFormat.PPTX, tmp_path)
