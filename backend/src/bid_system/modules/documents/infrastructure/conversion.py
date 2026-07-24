"""Isolated LibreOffice headless conversion with an explicit timeout."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bid_system.modules.documents.domain.errors import InvalidDocumentError
from bid_system.modules.documents.domain.models import DocumentFormat
from bid_system.shared.contracts.errors import ExternalServiceError

DOCX_EXTENSION = ".docx"
PPTX_EXTENSION = ".pptx"
PDF_EXTENSION = ".pdf"
CONVERSION_BASENAME = "conversion-source"
LIBREOFFICE_PROFILE_DIRECTORY = "libreoffice-profile"
PDF_EXPORT_FILTERS: dict[DocumentFormat, str] = {
    DocumentFormat.DOCX: "pdf:writer_pdf_Export",
    DocumentFormat.PPTX: "pdf:impress_pdf_Export",
}


@dataclass(frozen=True)
class ProcessResult:
    """Non-sensitive external-process outcome."""

    exit_code: int


class ProcessRunner(Protocol):
    async def run(
        self,
        args: tuple[str, ...],
        *,
        timeout_seconds: float,
    ) -> ProcessResult: ...


class AsyncProcessRunner:
    """Run one non-shell subprocess while bounding execution time."""

    async def run(
        self,
        args: tuple[str, ...],
        *,
        timeout_seconds: float,
    ) -> ProcessResult:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            async with asyncio.timeout(timeout_seconds):
                await process.communicate()
        except FileNotFoundError as error:
            raise ExternalServiceError(public_message="文档转换服务不可用") from error
        except TimeoutError as error:
            if process is not None:
                process.kill()
                await process.wait()
            raise ExternalServiceError(public_message="文档转换超时") from error
        exit_code = process.returncode
        if exit_code is None:
            raise RuntimeError("subprocess completed without an exit code")
        return ProcessResult(exit_code=exit_code)


class LibreOfficePdfConverter:
    """Convert DOCX/PPTX into the durable canonical PDF representation."""

    def __init__(
        self,
        *,
        executable: str,
        timeout_seconds: float,
        runner: ProcessRunner | None = None,
    ) -> None:
        if not executable.strip() or timeout_seconds <= 0:
            raise ValueError("invalid LibreOffice settings")
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._runner = runner or AsyncProcessRunner()

    async def convert(
        self,
        source_path: Path,
        file_format: DocumentFormat,
        workspace: Path,
    ) -> Path:
        if file_format not in PDF_EXPORT_FILTERS:
            raise ValueError("LibreOffice conversion requires DOCX or PPTX")
        source_extension = (
            DOCX_EXTENSION if file_format is DocumentFormat.DOCX else PPTX_EXTENSION
        )
        conversion_source = workspace / f"{CONVERSION_BASENAME}{source_extension}"
        await asyncio.to_thread(shutil.copyfile, source_path, conversion_source)
        profile = workspace / LIBREOFFICE_PROFILE_DIRECTORY
        profile.mkdir()
        args = (
            self._executable,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            PDF_EXPORT_FILTERS[file_format],
            "--outdir",
            str(workspace),
            str(conversion_source),
        )
        result = await self._runner.run(args, timeout_seconds=self._timeout_seconds)
        output = workspace / f"{CONVERSION_BASENAME}{PDF_EXTENSION}"
        if result.exit_code != 0 or not output.is_file() or output.stat().st_size == 0:
            raise InvalidDocumentError(public_message="文档无法转换为PDF")
        return output
