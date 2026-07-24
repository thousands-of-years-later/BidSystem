"""Stable task-message contracts shared by producers and worker entrypoints."""

from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

DOCUMENT_PARSE_TASK_TYPE: Final[Literal["documents.parse"]] = "documents.parse"
DOCUMENT_PARSE_SCHEMA_VERSION: Final[Literal[3]] = 3


class DocumentParseTaskInput(BaseModel):
    """Minimal identity-only input for the future product-document workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: Literal["documents.parse"] = DOCUMENT_PARSE_TASK_TYPE
    schema_version: Literal[3] = DOCUMENT_PARSE_SCHEMA_VERSION
    document_version_id: UUID
