"""Typed contracts for trusted external data sources and source snapshots."""

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

SourceFormat = Literal[
    "csv",
    "html",
    "json",
    "xml",
]

AcquisitionMethod = Literal[
    "direct_http",
    "operator_import",
]


class DataSource(BaseModel):
    """Immutable definition of an approved external data source."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    key: str = Field(pattern=r"^[a-z0-9_]+$")

    name: str = Field(min_length=1)

    publisher: str = Field(min_length=1)

    url: AnyHttpUrl

    source_page: AnyHttpUrl

    format: SourceFormat

    filename: str = Field(pattern=r"^[A-Za-z0-9._-]+$")

    description: str = Field(min_length=1)

    refresh_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_filename_extension(self) -> Self:
        """Require the declared filename to match the source format."""

        expected_suffix = f".{self.format}"

        actual_suffix = Path(self.filename).suffix.lower()

        if actual_suffix != expected_suffix:
            raise ValueError(f"Filename '{self.filename}' must end with '{expected_suffix}'.")

        return self


class SourceSnapshot(BaseModel):
    """Immutable provenance record for one acquired source snapshot."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_key: str = Field(pattern=r"^[a-z0-9_]+$")

    acquisition_method: AcquisitionMethod = "direct_http"

    requested_url: AnyHttpUrl

    resolved_url: AnyHttpUrl

    fetched_at: datetime

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    byte_size: int = Field(ge=1)

    content_type: str | None = None

    destination: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timezone_aware_timestamp(
        self,
    ) -> Self:
        """Reject provenance timestamps without explicit timezone information."""

        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("Snapshot timestamps must be timezone-aware.")

        return self
