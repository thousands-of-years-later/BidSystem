"""Pure DocumentIR element entities produced by document parsing."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from string import hexdigits
from uuid import UUID

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
MIN_PAGE_DIMENSION = 1
MIN_TABLE_DIMENSION = 1
SHA256_HEX_LENGTH = 64

_COMPARISON_PATTERN = re.compile(r">=|<=|≠|≥|≤|>|<|=")


class DocumentElementType(StrEnum):
    """Stable discriminator for parsed DocumentIR elements."""

    TEXT = "text"
    PICTURE = "picture"
    TABLE = "table"


class ComparisonOperator(StrEnum):
    """Normalized comparison operators preserved from parsed content."""

    GT = "GT"
    LT = "LT"
    GE = "GE"
    LE = "LE"
    EQ = "EQ"
    NE = "NE"


class ConfidenceStatus(StrEnum):
    """Availability of confidence evidence for a parsed element."""

    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ConfidenceBasis(StrEnum):
    """Rule used to derive an element's aggregate confidence."""

    PROVIDED = "provided"
    LAYOUT_ONLY = "layout_only"
    MIN_LAYOUT_RECOGNITION = "min_layout_recognition"
    MIN_AVAILABLE = "min_available"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    """Human-review lifecycle for a parsed element."""

    NOT_REVIEWED = "NOT_REVIEWED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


class TableMergeStatus(StrEnum):
    """Cross-page merge decision for one physical table segment."""

    NOT_REQUIRED = "NOT_REQUIRED"
    UNRESOLVED = "UNRESOLVED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"


_SYMBOL_OPERATORS: dict[str, ComparisonOperator] = {
    ">": ComparisonOperator.GT,
    "<": ComparisonOperator.LT,
    ">=": ComparisonOperator.GE,
    "≥": ComparisonOperator.GE,
    "<=": ComparisonOperator.LE,
    "≤": ComparisonOperator.LE,
    "=": ComparisonOperator.EQ,
    "≠": ComparisonOperator.NE,
}


def _validate_confidence(value: float, *, field_name: str) -> None:
    if not MIN_CONFIDENCE <= value <= MAX_CONFIDENCE:
        raise ValueError(f"{field_name} must be between 0 and 1")


def _is_sha256(value: str) -> bool:
    return len(value) == SHA256_HEX_LENGTH and all(
        character in hexdigits for character in value
    )


@dataclass(frozen=True)
class BoundingBox:
    """Pixel coordinates in the original parsed page."""

    x1: int
    y1: int
    x2: int
    y2: int

    def __post_init__(self) -> None:
        if self.x1 < 0 or self.y1 < 0:
            raise ValueError("bounding-box origin must not be negative")
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("bounding box must have positive width and height")


@dataclass(frozen=True)
class NormalizedBoundingBox:
    """Page-relative coordinates in the inclusive range from zero to one."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        for field_name, value in (
            ("x1", self.x1),
            ("y1", self.y1),
            ("x2", self.x2),
            ("y2", self.y2),
        ):
            _validate_confidence(value, field_name=field_name)
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("normalized bounding box must have positive dimensions")


@dataclass(frozen=True)
class PagePosition:
    """Page identity, reading order, and evidence coordinates."""

    page_index: int
    page_width: int
    page_height: int
    bbox: BoundingBox
    reading_order: int | None
    raw_block_id: int

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("page index must not be negative")
        if (
            self.page_width < MIN_PAGE_DIMENSION
            or self.page_height < MIN_PAGE_DIMENSION
        ):
            raise ValueError("page dimensions must be positive")
        if self.bbox.x2 > self.page_width or self.bbox.y2 > self.page_height:
            raise ValueError("bounding box must remain inside the page")
        if self.reading_order is not None and self.reading_order < 0:
            raise ValueError("reading order must not be negative")
        if self.raw_block_id < 0:
            raise ValueError("raw block id must not be negative")

    @property
    def page_number(self) -> int:
        """Return the one-based page number used by reviewers."""
        return self.page_index + 1

    @property
    def normalized_bbox(self) -> NormalizedBoundingBox:
        """Derive stable page-relative coordinates without duplicated state."""
        return NormalizedBoundingBox(
            x1=self.bbox.x1 / self.page_width,
            y1=self.bbox.y1 / self.page_height,
            x2=self.bbox.x2 / self.page_width,
            y2=self.bbox.y2 / self.page_height,
        )


@dataclass(frozen=True)
class RecognitionConfidence:
    """Summary of OCR scores contributing to one parsed element."""

    minimum: float
    average: float
    maximum: float

    def __post_init__(self) -> None:
        _validate_confidence(self.minimum, field_name="minimum recognition confidence")
        _validate_confidence(self.average, field_name="average recognition confidence")
        _validate_confidence(self.maximum, field_name="maximum recognition confidence")
        if not self.minimum <= self.average <= self.maximum:
            raise ValueError(
                "recognition confidence must satisfy minimum <= average <= maximum"
            )


@dataclass(frozen=True)
class ElementConfidence:
    """Confidence evidence without conflating layout, OCR, and structure scores."""

    status: ConfidenceStatus
    basis: ConfidenceBasis
    overall: float | None = None
    layout: float | None = None
    recognition: RecognitionConfidence | None = None
    structure: float | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("overall confidence", self.overall),
            ("layout confidence", self.layout),
            ("structure confidence", self.structure),
        ):
            if value is not None:
                _validate_confidence(value, field_name=field_name)

        available_scores = (
            self.overall,
            self.layout,
            self.recognition,
            self.structure,
        )
        has_score = any(score is not None for score in available_scores)
        if self.status is ConfidenceStatus.UNKNOWN and has_score:
            raise ValueError("unknown confidence must not contain scores")
        if self.status is not ConfidenceStatus.UNKNOWN and not has_score:
            raise ValueError("known or partial confidence must contain a score")
        if self.status is ConfidenceStatus.UNKNOWN and self.basis is not ConfidenceBasis.UNKNOWN:
            raise ValueError("unknown confidence must use the unknown basis")
        if self.status is not ConfidenceStatus.UNKNOWN and self.basis is ConfidenceBasis.UNKNOWN:
            raise ValueError("available confidence must declare its aggregation basis")


@dataclass(frozen=True)
class ComparisonMatch:
    """One comparison symbol and its exact source location."""

    raw: str
    operator: ComparisonOperator
    start: int
    end: int
    source_field: str
    source_id: UUID | None = None

    def __post_init__(self) -> None:
        expected_operator = _SYMBOL_OPERATORS.get(self.raw)
        if expected_operator is None:
            raise ValueError("unsupported comparison symbol")
        if self.operator is not expected_operator:
            raise ValueError("comparison symbol does not match normalized operator")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("comparison offsets must define a positive source span")
        if self.end - self.start != len(self.raw):
            raise ValueError("comparison offsets must match the raw symbol length")
        if not self.source_field.strip():
            raise ValueError("comparison source field must not be blank")


@dataclass(frozen=True)
class ComparisonInfo:
    """All comparison symbols found in one element or sub-element."""

    symbols: tuple[ComparisonMatch, ...]

    @property
    def contains_symbol(self) -> bool:
        """Return whether the element contains a supported comparison symbol."""
        return bool(self.symbols)

    @classmethod
    def from_text(
        cls,
        *,
        text: str,
        source_field: str,
        source_id: UUID | None = None,
    ) -> "ComparisonInfo":
        """Extract supported symbols from one exact text source."""
        return cls(
            symbols=extract_comparison_symbols(
                text=text,
                source_field=source_field,
                source_id=source_id,
            )
        )

    @classmethod
    def combine(cls, items: tuple["ComparisonInfo", ...]) -> "ComparisonInfo":
        """Combine matches while preserving source-specific offsets."""
        return cls(symbols=tuple(symbol for item in items for symbol in item.symbols))


def extract_comparison_symbols(
    *,
    text: str,
    source_field: str,
    source_id: UUID | None = None,
) -> tuple[ComparisonMatch, ...]:
    """Extract comparison symbols in source order, matching compound forms first."""
    if not source_field.strip():
        raise ValueError("comparison source field must not be blank")
    return tuple(
        ComparisonMatch(
            raw=match.group(0),
            operator=_SYMBOL_OPERATORS[match.group(0)],
            start=match.start(),
            end=match.end(),
            source_field=source_field,
            source_id=source_id,
        )
        for match in _COMPARISON_PATTERN.finditer(text)
    )


@dataclass(frozen=True)
class ParserProvenance:
    """Parser and source-result identity required for evidence traceability."""

    parser_name: str
    parser_version: str
    parsed_at: datetime
    raw_result_uri: str | None
    model_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.parser_name.strip() or not self.parser_version.strip():
            raise ValueError("parser name and version must not be blank")
        if self.parsed_at.tzinfo is None or self.parsed_at.utcoffset() is None:
            raise ValueError("parsed time must be timezone-aware")
        if self.raw_result_uri is not None and not self.raw_result_uri.strip():
            raise ValueError("raw result URI must be absent or non-blank")
        if any(not model_name.strip() for model_name in self.model_names):
            raise ValueError("parser model names must not be blank")


@dataclass(frozen=True)
class ReviewMetadata:
    """Human-review routing state attached to parser evidence."""

    required: bool
    status: ReviewStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("review reasons must not be blank")
        if self.required and not self.reasons:
            raise ValueError("required review must contain at least one reason")
        if not self.required and self.status is ReviewStatus.PENDING:
            raise ValueError("non-required review cannot be pending")


@dataclass(frozen=True, kw_only=True)
class DocumentElement(ABC):
    """Common identity and evidence metadata for a parsed DocumentIR element."""

    id: UUID
    document_version_id: UUID
    raw_type: str
    position: PagePosition
    confidence: ElementConfidence
    review: ReviewMetadata
    provenance: ParserProvenance

    def __post_init__(self) -> None:
        if not self.raw_type.strip():
            raise ValueError("raw parser type must not be blank")

    @property
    @abstractmethod
    def type(self) -> DocumentElementType:
        """Return the stable parsed-element discriminator."""

    @property
    @abstractmethod
    def comparison(self) -> ComparisonInfo:
        """Return all comparison symbols contained by the element."""


@dataclass(frozen=True, kw_only=True)
class TextElement(DocumentElement):
    """One ordered text-bearing block from a parsed page."""

    text: str
    markdown: str | None = None
    language: str | None = None
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.text.strip():
            raise ValueError("text element content must not be blank")
        if self.markdown is not None and not self.markdown.strip():
            raise ValueError("text markdown must be absent or non-blank")
        if self.language is not None and not self.language.strip():
            raise ValueError("text language must be absent or non-blank")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading path items must not be blank")

    @property
    def type(self) -> DocumentElementType:
        """Return the text discriminator."""
        return DocumentElementType.TEXT

    @property
    def comparison(self) -> ComparisonInfo:
        """Extract comparison symbols from the original text."""
        return ComparisonInfo.from_text(text=self.text, source_field="text")


@dataclass(frozen=True, kw_only=True)
class PictureElement(DocumentElement):
    """One extracted picture stored outside the structured database payload."""

    object_uri: str
    relative_path: str
    mime_type: str
    width: int
    height: int
    sha256: str | None = None
    caption: str | None = None
    ocr_text: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.object_uri.strip() or not self.relative_path.strip():
            raise ValueError("picture object URI and relative path must not be blank")
        if not self.mime_type.strip():
            raise ValueError("picture MIME type must not be blank")
        if self.width < MIN_PAGE_DIMENSION or self.height < MIN_PAGE_DIMENSION:
            raise ValueError("picture dimensions must be positive")
        if self.sha256 is not None and not _is_sha256(self.sha256):
            raise ValueError("picture hash must be a SHA-256 hex digest")
        if self.caption is not None and not self.caption.strip():
            raise ValueError("picture caption must be absent or non-blank")
        if self.ocr_text is not None and not self.ocr_text.strip():
            raise ValueError("picture OCR text must be absent or non-blank")

    @property
    def type(self) -> DocumentElementType:
        """Return the picture discriminator."""
        return DocumentElementType.PICTURE

    @property
    def comparison(self) -> ComparisonInfo:
        """Extract comparison symbols from the caption and optional picture OCR."""
        sources: list[ComparisonInfo] = []
        if self.caption is not None:
            sources.append(
                ComparisonInfo.from_text(
                    text=self.caption,
                    source_field="caption",
                )
            )
        if self.ocr_text is not None:
            sources.append(
                ComparisonInfo.from_text(
                    text=self.ocr_text,
                    source_field="ocr_text",
                )
            )
        return ComparisonInfo.combine(tuple(sources))


@dataclass(frozen=True)
class TableCell:
    """One table cell with source coordinates and OCR confidence."""

    id: UUID
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    bbox: BoundingBox
    text: str
    confidence: float | None

    def __post_init__(self) -> None:
        if self.row_start < 0 or self.column_start < 0:
            raise ValueError("table-cell start coordinates must not be negative")
        if self.row_end < self.row_start or self.column_end < self.column_start:
            raise ValueError("table-cell end coordinates must not precede start coordinates")
        if self.confidence is not None:
            _validate_confidence(
                self.confidence,
                field_name="table-cell recognition confidence",
            )

    @property
    def row_span(self) -> int:
        """Return the number of rows covered by the cell."""
        return self.row_end - self.row_start + 1

    @property
    def column_span(self) -> int:
        """Return the number of columns covered by the cell."""
        return self.column_end - self.column_start + 1

    @property
    def comparison(self) -> ComparisonInfo:
        """Extract comparison symbols from this cell."""
        return ComparisonInfo.from_text(
            text=self.text,
            source_field="cell.text",
            source_id=self.id,
        )


@dataclass(frozen=True)
class TableContinuation:
    """Cross-page relationship between physical table segments."""

    logical_table_id: UUID | None
    segment_index: int
    is_cross_page: bool
    is_continuation: bool
    previous_element_id: UUID | None
    next_element_id: UUID | None
    merge_status: TableMergeStatus

    def __post_init__(self) -> None:
        if self.segment_index < 0:
            raise ValueError("table segment index must not be negative")
        if self.is_cross_page and self.logical_table_id is None:
            raise ValueError("cross-page table segment must identify its logical table")
        if not self.is_cross_page and self.merge_status is not TableMergeStatus.NOT_REQUIRED:
            raise ValueError("single-page table must not have a cross-page merge status")
        if self.is_continuation and self.previous_element_id is None:
            raise ValueError("continuation table segment must identify the previous segment")


@dataclass(frozen=True, kw_only=True)
class TableElement(DocumentElement):
    """One physical page segment of a parsed table."""

    html: str
    row_count: int
    column_count: int
    cells: tuple[TableCell, ...]
    continuation: TableContinuation
    title: str | None = None
    markdown: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.html.strip() and not self.cells:
            raise ValueError("table element must contain HTML or cells")
        if (
            self.row_count < MIN_TABLE_DIMENSION
            or self.column_count < MIN_TABLE_DIMENSION
        ):
            raise ValueError("table dimensions must be positive")
        if self.title is not None and not self.title.strip():
            raise ValueError("table title must be absent or non-blank")
        if self.markdown is not None and not self.markdown.strip():
            raise ValueError("table markdown must be absent or non-blank")

        cell_ids: set[UUID] = set()
        for cell in self.cells:
            if cell.id in cell_ids:
                raise ValueError("table cell ids must be unique")
            if cell.row_end >= self.row_count or cell.column_end >= self.column_count:
                raise ValueError("table cell coordinates exceed table dimensions")
            cell_ids.add(cell.id)

    @property
    def type(self) -> DocumentElementType:
        """Return the table discriminator."""
        return DocumentElementType.TABLE

    @property
    def comparison(self) -> ComparisonInfo:
        """Aggregate title and cell comparison symbols with evidence identity."""
        sources = tuple(cell.comparison for cell in self.cells)
        if self.title is not None:
            sources = (
                ComparisonInfo.from_text(
                    text=self.title,
                    source_field="title",
                ),
                *sources,
            )
        return ComparisonInfo.combine(sources)
