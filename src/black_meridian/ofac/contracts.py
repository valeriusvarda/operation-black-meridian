"""Typed, provenance-bound contracts for OFAC primary records."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from black_meridian.data_sources.models import AcquisitionMethod

OfacSourceKey = Literal[
    "ofac_sdn_csv",
    "ofac_consolidated_csv",
]


class OfacSubjectKind(StrEnum):
    """Deterministic subject classifications derived from OFAC source text."""

    INDIVIDUAL = "individual"
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    UNSPECIFIED = "unspecified"


_SUBJECT_KIND_BY_SOURCE_VALUE: dict[
    str,
    OfacSubjectKind,
] = {
    "individual": OfacSubjectKind.INDIVIDUAL,
    "vessel": OfacSubjectKind.VESSEL,
    "aircraft": OfacSubjectKind.AIRCRAFT,
    "-0-": OfacSubjectKind.UNSPECIFIED,
}


class OfacPrimaryRecord(BaseModel):
    """One immutable OFAC primary-record source-evidence occurrence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    source_key: OfacSourceKey

    publisher_record_id: str = Field(pattern=r"^[0-9]+$")

    source_row_number: int = Field(ge=1)

    source_row_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    primary_name_raw: str

    source_entity_type_raw: str

    program_text_raw: str

    title_raw: str

    call_sign_raw: str

    vessel_type_raw: str

    tonnage_raw: str

    grt_raw: str

    vessel_flag_raw: str

    vessel_owner_raw: str

    remarks_raw: str

    acquisition_method: AcquisitionMethod

    acquired_at: datetime

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("primary_name_raw")
    @classmethod
    def validate_primary_name_raw(
        cls,
        value: str,
    ) -> str:
        """Reject blank publisher names without rewriting source text."""

        if not value.strip():
            raise ValueError("OFAC primary name must not be blank.")

        return value

    @field_validator("source_entity_type_raw")
    @classmethod
    def validate_source_entity_type_raw(
        cls,
        value: str,
    ) -> str:
        """Accept only explicitly observed OFAC primary type values."""

        normalized_value = value.strip()

        if normalized_value not in _SUBJECT_KIND_BY_SOURCE_VALUE:
            raise ValueError(
                "Unsupported OFAC entity type. Expected one of: individual, vessel, aircraft, -0-."
            )

        return value

    @field_validator("program_text_raw")
    @classmethod
    def validate_program_text_raw(
        cls,
        value: str,
    ) -> str:
        """Require publisher program context while preserving raw text."""

        if not value.strip():
            raise ValueError("OFAC program text must not be blank.")

        return value

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone-aware acquisition provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OFAC acquisition timestamp must be timezone-aware.")

        return value

    @property
    def subject_kind(
        self,
    ) -> OfacSubjectKind:
        """Derive a supported semantic subject kind from raw source text."""

        normalized_value = self.source_entity_type_raw.strip()

        return _SUBJECT_KIND_BY_SOURCE_VALUE[normalized_value]

    @property
    def source_record_key(
        self,
    ) -> tuple[
        OfacSourceKey,
        str,
    ]:
        """Return source-scoped publisher-record identity."""

        return (
            self.source_key,
            self.publisher_record_id,
        )
