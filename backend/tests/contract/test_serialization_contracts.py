"""Cross-contract serialization policy tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum

import pytest
from pydantic import ValidationError

from bid_system.shared.contracts.api import (
    ApiContractModel,
    MoneyAmount,
    UtcDateTime,
)


class ReviewStatus(StrEnum):
    APPROVED = "approved"


class SerializationPayload(ApiContractModel):
    occurred_at: UtcDateTime
    status: ReviewStatus
    amount: MoneyAmount


def test_time_enum_and_money_use_stable_json_representations() -> None:
    payload = SerializationPayload(
        occurred_at=datetime(
            2026,
            7,
            21,
            16,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        status=ReviewStatus.APPROVED,
        amount=Decimal("1234.50"),
    )

    assert payload.model_dump(mode="json") == {
        "occurred_at": "2026-07-21T08:30:00Z",
        "status": "approved",
        "amount": "1234.50",
    }


def test_naive_datetime_is_rejected_at_contract_boundary() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SerializationPayload(
            occurred_at=datetime(2026, 7, 21, 8, 30),
            status=ReviewStatus.APPROVED,
            amount=Decimal("1.00"),
        )
