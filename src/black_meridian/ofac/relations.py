"""Typed and deterministic parsers for OFAC address and alias relations."""

from __future__ import annotations

import csv
from datetime import datetime
from hashlib import sha256
from io import StringIO
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from black_meridian.data_sources.models import (
    AcquisitionMethod,
    SourceSnapshot,
)
from black_meridian.ofac.contracts import OfacSourceKey

OfacAddressSourceKey = Literal[
    "ofac_sdn_addresses_csv",
    "ofac_consolidated_addresses_csv",
]

OfacAliasSourceKey = Literal[
    "ofac_sdn_aliases_csv",
    "ofac_consolidated_aliases_csv",
]

_ADDRESS_FIELD_COUNT = 6
_ALIAS_FIELD_COUNT = 5
_TERMINAL_SUB = b"\x1a"


class OfacRelationParseError(ValueError):
    """Raised when OFAC relational source evidence violates its contract."""


class _OfacRelationBase(BaseModel):
    """Shared immutable provenance for one OFAC relation record."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    parent_publisher_record_id: str = Field(pattern=r"^[0-9]+$")

    publisher_relation_id: str = Field(pattern=r"^[0-9]+$")

    source_row_number: int = Field(ge=1)

    source_row_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    acquisition_method: AcquisitionMethod

    acquired_at: datetime

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone-aware acquisition provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OFAC relation acquisition timestamp must be timezone-aware.")

        return value


class OfacAddressRecord(_OfacRelationBase):
    """One provenance-bound OFAC address relation occurrence."""

    source_key: OfacAddressSourceKey

    address_raw: str

    city_state_postal_raw: str

    country_raw: str

    remarks_raw: str

    @property
    def parent_source_key(
        self,
    ) -> OfacSourceKey:
        """Return the primary source identity this relation belongs to."""

        return _parent_source_key(self.source_key)

    @property
    def parent_record_key(
        self,
    ) -> tuple[OfacSourceKey, str]:
        """Return source-scoped parent primary-record identity."""

        return (
            self.parent_source_key,
            self.parent_publisher_record_id,
        )

    @property
    def source_record_key(
        self,
    ) -> tuple[OfacAddressSourceKey, str]:
        """Return source-scoped address-record identity."""

        return (
            self.source_key,
            self.publisher_relation_id,
        )


class OfacAliasRecord(_OfacRelationBase):
    """One provenance-bound OFAC alternate-identity occurrence."""

    source_key: OfacAliasSourceKey

    alias_type_raw: str

    alias_name_raw: str

    remarks_raw: str

    @field_validator("alias_name_raw")
    @classmethod
    def validate_alias_name_raw(
        cls,
        value: str,
    ) -> str:
        """Reject blank aliases without rewriting publisher text."""

        if not value.strip():
            raise ValueError("OFAC alias name must not be blank.")

        return value

    @property
    def parent_source_key(
        self,
    ) -> OfacSourceKey:
        """Return the primary source identity this relation belongs to."""

        return _parent_source_key(self.source_key)

    @property
    def parent_record_key(
        self,
    ) -> tuple[OfacSourceKey, str]:
        """Return source-scoped parent primary-record identity."""

        return (
            self.parent_source_key,
            self.parent_publisher_record_id,
        )

    @property
    def source_record_key(
        self,
    ) -> tuple[OfacAliasSourceKey, str]:
        """Return source-scoped alias-record identity."""

        return (
            self.source_key,
            self.publisher_relation_id,
        )


def parse_ofac_address_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> tuple[OfacAddressRecord, ...]:
    """Parse one trusted OFAC address CSV snapshot."""

    source_key = _validate_address_source_key(snapshot.source_key)

    _reconcile_snapshot(
        content,
        snapshot,
    )

    rows = _decode_rows(content)

    records: list[OfacAddressRecord] = []

    seen_relation_ids: dict[
        str,
        tuple[str, ...],
    ] = {}

    for source_row_number, row in enumerate(
        rows,
        start=1,
    ):
        row_values = tuple(row)

        if len(row_values) != _ADDRESS_FIELD_COUNT:
            raise OfacRelationParseError(
                "OFAC address CSV row "
                f"{source_row_number} must contain exactly "
                f"{_ADDRESS_FIELD_COUNT} fields; "
                f"found {len(row_values)}."
            )

        _check_duplicate_relation_id(
            seen_relation_ids,
            row_values,
            relation_name="address",
        )

        try:
            record = OfacAddressRecord(
                source_key=source_key,
                parent_publisher_record_id=row_values[0],
                publisher_relation_id=row_values[1],
                source_row_number=source_row_number,
                source_row_fingerprint=_fingerprint_row(row_values),
                address_raw=row_values[2],
                city_state_postal_raw=row_values[3],
                country_raw=row_values[4],
                remarks_raw=row_values[5],
                acquisition_method=(snapshot.acquisition_method),
                acquired_at=snapshot.fetched_at,
                source_sha256=snapshot.sha256,
            )
        except ValidationError as exc:
            raise OfacRelationParseError(
                "OFAC address record at row "
                f"{source_row_number} violated "
                f"the source contract: {exc}"
            ) from exc

        records.append(record)

    if not records:
        raise OfacRelationParseError("OFAC address CSV contains no publisher records.")

    return tuple(records)


def parse_ofac_alias_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> tuple[OfacAliasRecord, ...]:
    """Parse one trusted OFAC alternate-identity CSV snapshot."""

    source_key = _validate_alias_source_key(snapshot.source_key)

    _reconcile_snapshot(
        content,
        snapshot,
    )

    rows = _decode_rows(content)

    records: list[OfacAliasRecord] = []

    seen_relation_ids: dict[
        str,
        tuple[str, ...],
    ] = {}

    for source_row_number, row in enumerate(
        rows,
        start=1,
    ):
        row_values = tuple(row)

        if len(row_values) != _ALIAS_FIELD_COUNT:
            raise OfacRelationParseError(
                "OFAC alias CSV row "
                f"{source_row_number} must contain exactly "
                f"{_ALIAS_FIELD_COUNT} fields; "
                f"found {len(row_values)}."
            )

        _check_duplicate_relation_id(
            seen_relation_ids,
            row_values,
            relation_name="alias",
        )

        try:
            record = OfacAliasRecord(
                source_key=source_key,
                parent_publisher_record_id=row_values[0],
                publisher_relation_id=row_values[1],
                source_row_number=source_row_number,
                source_row_fingerprint=_fingerprint_row(row_values),
                alias_type_raw=row_values[2],
                alias_name_raw=row_values[3],
                remarks_raw=row_values[4],
                acquisition_method=(snapshot.acquisition_method),
                acquired_at=snapshot.fetched_at,
                source_sha256=snapshot.sha256,
            )
        except ValidationError as exc:
            raise OfacRelationParseError(
                f"OFAC alias record at row {source_row_number} violated the source contract: {exc}"
            ) from exc

        records.append(record)

    if not records:
        raise OfacRelationParseError("OFAC alias CSV contains no publisher records.")

    return tuple(records)


def _decode_rows(
    content: bytes,
) -> list[list[str]]:
    """Decode strict CSV while accepting only a terminal SUB control byte."""

    csv_bytes = content

    if csv_bytes.endswith(_TERMINAL_SUB):
        csv_bytes = csv_bytes[:-1]

    if _TERMINAL_SUB in csv_bytes:
        raise OfacRelationParseError("OFAC relation CSV contains an interior SUB control record.")

    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OfacRelationParseError("OFAC relation source is not valid UTF-8.") from exc

    reader = csv.reader(
        StringIO(
            csv_text,
            newline="",
        ),
        strict=True,
    )

    try:
        return list(reader)
    except csv.Error as exc:
        raise OfacRelationParseError(
            "OFAC relation CSV structure could not be parsed safely."
        ) from exc


def _check_duplicate_relation_id(
    seen_relation_ids: dict[
        str,
        tuple[str, ...],
    ],
    row_values: tuple[str, ...],
    *,
    relation_name: str,
) -> None:
    """Reject repeated relation-record identifiers."""

    relation_id = row_values[1]

    previous_row = seen_relation_ids.get(relation_id)

    if previous_row is not None:
        if previous_row == row_values:
            raise OfacRelationParseError(
                f"OFAC {relation_name} CSV contains "
                "an exact duplicate publisher relation "
                f"identifier '{relation_id}'."
            )

        raise OfacRelationParseError(
            f"OFAC {relation_name} CSV contains "
            "a contradictory duplicate publisher "
            f"relation identifier '{relation_id}'."
        )

    seen_relation_ids[relation_id] = row_values


def _validate_address_source_key(
    source_key: str,
) -> OfacAddressSourceKey:
    """Require one approved OFAC address source."""

    if source_key == "ofac_sdn_addresses_csv":
        return "ofac_sdn_addresses_csv"

    if source_key == "ofac_consolidated_addresses_csv":
        return "ofac_consolidated_addresses_csv"

    raise OfacRelationParseError(
        "Snapshot source_key must identify an approved OFAC address source."
    )


def _validate_alias_source_key(
    source_key: str,
) -> OfacAliasSourceKey:
    """Require one approved OFAC alias source."""

    if source_key == "ofac_sdn_aliases_csv":
        return "ofac_sdn_aliases_csv"

    if source_key == "ofac_consolidated_aliases_csv":
        return "ofac_consolidated_aliases_csv"

    raise OfacRelationParseError("Snapshot source_key must identify an approved OFAC alias source.")


def _parent_source_key(
    source_key: (OfacAddressSourceKey | OfacAliasSourceKey),
) -> OfacSourceKey:
    """Map a relation source to its primary publisher source."""

    if source_key in {
        "ofac_sdn_addresses_csv",
        "ofac_sdn_aliases_csv",
    }:
        return "ofac_sdn_csv"

    return "ofac_consolidated_csv"


def _reconcile_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> None:
    """Reconcile exact relation bytes against acquisition provenance."""

    actual_byte_size = len(content)

    if actual_byte_size != snapshot.byte_size:
        raise OfacRelationParseError(
            "OFAC relation source byte size does not match the trusted SourceSnapshot."
        )

    actual_sha256 = sha256(content).hexdigest()

    if actual_sha256 != snapshot.sha256:
        raise OfacRelationParseError(
            "OFAC relation source SHA-256 does not match the trusted SourceSnapshot."
        )


def _fingerprint_row(
    row: tuple[str, ...],
) -> str:
    """Hash ordered raw publisher fields with deterministic framing."""

    digest = sha256()

    for field in row:
        encoded_field = field.encode("utf-8")

        digest.update(
            len(encoded_field).to_bytes(
                8,
                byteorder="big",
                signed=False,
            )
        )

        digest.update(encoded_field)

    return digest.hexdigest()
