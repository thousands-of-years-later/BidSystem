"""Stable pagination contracts for collection queries."""

from typing import Self

from pydantic import NonNegativeInt, PositiveInt, model_validator

from bid_system.shared.contracts.api import ApiContractModel, SuccessResponse


class PaginationMeta(ApiContractModel):
    """One-based page metadata with a deterministic total page count."""

    page: PositiveInt
    page_size: PositiveInt
    total: NonNegativeInt
    total_pages: NonNegativeInt = 0

    @model_validator(mode="after")
    def calculate_total_pages(self) -> Self:
        expected = 0 if self.total == 0 else (self.total + self.page_size - 1) // self.page_size
        if self.total_pages not in (0, expected):
            raise ValueError("total_pages does not match total and page_size")
        object.__setattr__(self, "total_pages", expected)
        return self


class PageData[PageItemT](ApiContractModel):
    """Typed page items and their pagination metadata."""

    items: list[PageItemT]
    pagination: PaginationMeta


class PaginatedResponse[PageItemT](SuccessResponse[PageData[PageItemT]]):
    """Stable success envelope for paginated queries."""
