"""Framework-neutral construction of application ports and adapters."""

from bid_system.modules.documents.application.upload import UploadDocumentHandler
from bid_system.modules.documents.infrastructure.conversion import LibreOfficePdfConverter
from bid_system.modules.documents.infrastructure.file_processing import (
    CanonicalPdfMetadataParser,
    ContentFileTypeDetector,
    StreamingUploadStager,
)
from bid_system.modules.documents.infrastructure.object_store import (
    MinioDocumentBlobStore,
)
from bid_system.modules.documents.infrastructure.repository import (
    TransactionalDocumentRepository,
)
from bid_system.modules.documents.infrastructure.safety import (
    ClamAvScanner,
    DocumentSafetyScanner,
    PdfEncryptionInspector,
)
from bid_system.modules.documents.infrastructure.system import (
    LocalWorkspaceFactory,
    SystemClock,
    UuidGenerator,
)
from bid_system.modules.identity.application.ports import (
    IdentityAuthenticationRepository,
    IdentityReader,
    PasswordEncoder,
    PasswordVerifier,
)
from bid_system.modules.identity.infrastructure.passwords import (
    Argon2PasswordEncoder,
    Argon2PasswordVerifier,
)
from bid_system.modules.identity.infrastructure.repository import SqlAlchemyIdentityReader
from bid_system.platform.config import AuthSettings, DocumentProcessingSettings
from bid_system.platform.database.engine import DatabaseResource
from bid_system.platform.database.transaction import AsyncTransactionManager
from bid_system.platform.object_store.client import MinioResource
from bid_system.platform.security.authentication import PasswordHasher


def build_identity_reader(transaction: AsyncTransactionManager) -> IdentityReader:
    """Wire the identity query port to the caller's request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_identity_authentication_repository(
    transaction: AsyncTransactionManager,
) -> IdentityAuthenticationRepository:
    """Wire all local-authentication persistence ports to one request transaction."""
    return SqlAlchemyIdentityReader(transaction.session)


def build_password_verifier(settings: AuthSettings) -> PasswordVerifier:
    """Wire identity password verification to the configured Argon2id adapter."""
    return Argon2PasswordVerifier(_password_hasher(settings))


def build_password_encoder(settings: AuthSettings) -> PasswordEncoder:
    """Wire account registration to the configured Argon2id encoder."""
    return Argon2PasswordEncoder(_password_hasher(settings))


def build_document_upload_handler(
    *,
    database: DatabaseResource,
    minio: MinioResource,
    settings: DocumentProcessingSettings,
) -> UploadDocumentHandler:
    """Wire document ingestion without opening a database transaction early."""
    converter = LibreOfficePdfConverter(
        executable=settings.libreoffice_executable,
        timeout_seconds=settings.conversion_timeout_seconds,
    )
    return UploadDocumentHandler(
        workspace_factory=LocalWorkspaceFactory(),
        stager=StreamingUploadStager(),
        type_detector=ContentFileTypeDetector(),
        safety_scanner=DocumentSafetyScanner(
            encryption_inspector=PdfEncryptionInspector(),
            malware_scanner=ClamAvScanner(
                host=settings.clamav_host,
                port=settings.clamav_port,
                timeout_seconds=settings.clamav_timeout_seconds,
            ),
        ),
        metadata_parser=CanonicalPdfMetadataParser(converter=converter),
        blob_store=MinioDocumentBlobStore(minio),
        repository=TransactionalDocumentRepository(database),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def _password_hasher(settings: AuthSettings) -> PasswordHasher:
    return PasswordHasher(
        memory_cost_kib=settings.argon2_memory_cost_kib,
        time_cost=settings.argon2_time_cost,
        parallelism=settings.argon2_parallelism,
    )
