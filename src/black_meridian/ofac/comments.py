"""Typed and deterministic parsing of OFAC remarks spillover evidence."""

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
from black_meridian.ofac.contracts import (
    OfacSourceKey,
)

OfacCommentSourceKey = Literal[
    "ofac_sdn_comments_csv",
    "ofac_consolidated_comments_csv",
]

_COMMENT_FIELD_COUNT = 2
_TERMINAL_SUB = b"\x1a"


class OfacCommentParseError(ValueError):
    """Raised when OFAC remarks spillover evidence violates its contract."""


class OfacCommentRecord(BaseModel):
    """One immutable OFAC remarks-continuation source occurrence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    source_key: OfacCommentSourceKey

    parent_publisher_record_id: str = Field(pattern=r"^[0-9]+$")

    source_row_number: int = Field(ge=1)

    source_row_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    continuation_raw: str

    acquisition_method: AcquisitionMethod

    acquired_at: datetime

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("continuation_raw")
    @classmethod
    def validate_continuation_raw(
        cls,
        value: str,
    ) -> str:
        """Reject empty spillover while preserving publisher text exactly."""

        if not value:
            raise ValueError("OFAC remarks continuation must not be empty.")

        return value

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone-aware acquisition provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OFAC comment acquisition timestamp must be timezone-aware.")

        return value

    @property
    def parent_source_key(
        self,
    ) -> OfacSourceKey:
        """Return the primary source associated with this spillover record."""

        if self.source_key == "ofac_sdn_comments_csv":
            return "ofac_sdn_csv"

        return "ofac_consolidated_csv"

    @property
    def parent_record_key(
        self,
    ) -> tuple[
        OfacSourceKey,
        str,
    ]:
        """Return source-scoped primary-record identity."""

        return (
            self.parent_source_key,
            self.parent_publisher_record_id,
        )

    @property
    def source_record_key(
        self,
    ) -> tuple[
        OfacCommentSourceKey,
        str,
    ]:
        """Return source-scoped spillover-record identity."""

        return (
            self.source_key,
            self.parent_publisher_record_id,
        )


def parse_ofac_comment_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> tuple[
    OfacCommentRecord,
    ...,
]:
    """Parse one trusted OFAC remarks spillover CSV snapshot."""

    source_key = _validate_comment_source_key(snapshot.source_key)

    _reconcile_snapshot(
        content,
        snapshot,
    )

    rows = _decode_rows(content)

    records: list[OfacCommentRecord] = []

    seen_parent_rows: dict[
        str,
        tuple[str, ...],
    ] = {}

    for source_row_number, row in enumerate(
        rows,
        start=1,
    ):
        row_values = tuple(row)

        if len(row_values) != _COMMENT_FIELD_COUNT:
            raise OfacCommentParseError(
                "OFAC comments CSV row "
                f"{source_row_number} must contain exactly "
                f"{_COMMENT_FIELD_COUNT} fields; "
                f"found {len(row_values)}."
            )

        _check_one_to_one_parent(
            seen_parent_rows,
            row_values,
        )

        try:
            record = OfacCommentRecord(
                source_key=source_key,
                parent_publisher_record_id=(row_values[0]),
                source_row_number=(source_row_number),
                source_row_fingerprint=(_fingerprint_row(row_values)),
                continuation_raw=(row_values[1]),
                acquisition_method=(snapshot.acquisition_method),
                acquired_at=(snapshot.fetched_at),
                source_sha256=(snapshot.sha256),
            )
        except ValidationError as exc:
            raise OfacCommentParseError(
                "OFAC comments record at row "
                f"{source_row_number} violated "
                f"the source contract: {exc}"
            ) from exc

        records.append(record)

    return tuple(records)


def _decode_rows(
    content: bytes,
) -> list[list[str]]:
    """Decode strict comments CSV with optional terminal SUB handling."""

    csv_bytes = content

    if csv_bytes.endswith(_TERMINAL_SUB):
        csv_bytes = csv_bytes[:-1]

    if _TERMINAL_SUB in csv_bytes:
        raise OfacCommentParseError("OFAC comments CSV contains an interior SUB control record.")

    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OfacCommentParseError("OFAC comments source is not valid UTF-8.") from exc

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
        raise OfacCommentParseError(
            "OFAC comments CSV structure could not be parsed safely."
        ) from exc


def _check_one_to_one_parent(
    seen_parent_rows: dict[
        str,
        tuple[str, ...],
    ],
    row_values: tuple[str, ...],
) -> None:
    """Enforce one spillover row per publisher primary identifier."""

    parent_id = row_values[0]

    previous_row = seen_parent_rows.get(parent_id)

    if previous_row is not None:
        if previous_row == row_values:
            raise OfacCommentParseError(
                "OFAC comments CSV contains "
                "an exact duplicate spillover record "
                f"for parent '{parent_id}'."
            )

        raise OfacCommentParseError(
            f"OFAC comments CSV contains contradictory spillover records for parent '{parent_id}'."
        )

    seen_parent_rows[parent_id] = row_values


def _validate_comment_source_key(
    source_key: str,
) -> OfacCommentSourceKey:
    """Require one approved OFAC comments source."""

    if source_key == "ofac_sdn_comments_csv":
        return "ofac_sdn_comments_csv"

    if source_key == "ofac_consolidated_comments_csv":
        return "ofac_consolidated_comments_csv"

    raise OfacCommentParseError(
        "Snapshot source_key must identify an approved OFAC comments source."
    )


def _reconcile_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> None:
    """Reconcile exact spillover bytes against acquisition provenance."""

    actual_byte_size = len(content)

    if actual_byte_size != snapshot.byte_size:
        raise OfacCommentParseError(
            "OFAC comments source byte size does not match the trusted SourceSnapshot."
        )

    actual_sha256 = sha256(content).hexdigest()

    if actual_sha256 != snapshot.sha256:
        raise OfacCommentParseError(
            "OFAC comments source SHA-256 does not match the trusted SourceSnapshot."
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
