"""Deterministic document-ingestion failures."""

from bid_system.shared.contracts.errors import DomainError, ErrorCode


class FileSizeLimitExceededError(DomainError):
    """The source bytes exceed the configured upload boundary."""

    code = ErrorCode.FILE_TOO_LARGE
    default_public_message = "文件大小超过限制"


class InvalidDocumentUploadRequestError(DomainError):
    """The multipart envelope does not contain exactly the supported fields."""

    code = ErrorCode.VALIDATION_ERROR
    default_public_message = "上传请求必须且只能包含一个文件"


class PageLimitExceededError(DomainError):
    """The canonical PDF contains more pages than the supported boundary."""

    code = ErrorCode.PAGE_LIMIT_EXCEEDED
    default_public_message = "文件页数超过限制"


class DuplicateDocumentContentError(DomainError):
    """The logical document already contains the uploaded source bytes."""

    code = ErrorCode.DUPLICATE_DOCUMENT_CONTENT
    default_public_message = "上传内容与已有文档版本相同"


class UnsupportedDocumentTypeError(DomainError):
    """The source bytes are not one of the supported document formats."""

    code = ErrorCode.UNSUPPORTED_DOCUMENT_TYPE
    default_public_message = "文件类型不受支持"


class EncryptedDocumentError(DomainError):
    """The source requires a password or contains encrypted content."""

    code = ErrorCode.ENCRYPTED_DOCUMENT
    default_public_message = "不支持加密文件"


class MalwareDetectedError(DomainError):
    """The configured malware scanner reported a known threat."""

    code = ErrorCode.MALWARE_DETECTED
    default_public_message = "文件未通过安全扫描"


class InvalidDocumentError(DomainError):
    """The bytes claim a supported format but cannot be parsed safely."""

    code = ErrorCode.INVALID_DOCUMENT
    default_public_message = "文件已损坏或格式不合法"
