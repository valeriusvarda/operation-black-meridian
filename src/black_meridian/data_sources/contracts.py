from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
)


class FatfTier(StrEnum):
    """Official FATF public-list classifications."""

    CALL_FOR_ACTION = "call_for_action"
    INCREASED_MONITORING = "increased_monitoring"


class FatfJurisdiction(BaseModel):
    """One normalized jurisdiction classification."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    jurisdiction_name: str = Field(min_length=2)
    iso_alpha3: str = Field(pattern=r"^[A-Z]{3}$")
    tier: FatfTier


class FatfSnapshot(BaseModel):
    """Provenance-rich snapshot of one FATF publication state."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    source_name: Literal["Financial Action Task Force"] = "Financial Action Task Force"

    source_url: HttpUrl
    publication_date: date
    retrieved_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[FatfJurisdiction, ...] = Field(min_length=1)

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an explicit timezone for snapshot provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")

        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def record_count(self) -> int:
        """Return the number of normalized jurisdiction records."""

        return len(self.records)
