"""Deterministic offline parser for trusted OFAC primary CSV snapshots."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO

from pydantic import ValidationError

from black_meridian.data_sources.models import SourceSnapshot
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
    OfacSourceKey,
)

_EXPECTED_FIELD_COUNT = 12
_TERMINAL_SUB = b"\x1a"


class OfacParseError(ValueError):
    """Raised when trusted OFAC primary evidence violates its parser contract."""


def parse_ofac_primary_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> tuple[OfacPrimaryRecord, ...]:
    """Parse one provenance-bound OFAC primary snapshot without network access."""

    source_key = _validate_source_key(snapshot.source_key)

    _reconcile_snapshot(
        content,
        snapshot,
    )

    csv_bytes = _remove_terminal_control(content)

    if _TERMINAL_SUB in csv_bytes:
        raise OfacParseError("OFAC primary CSV structure contains an interior SUB control record.")

    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OfacParseError("OFAC primary source is not valid UTF-8.") from exc

    records: list[OfacPrimaryRecord] = []

    seen_publisher_records: dict[
        str,
        tuple[str, ...],
    ] = {}

    reader = csv.reader(
        StringIO(
            csv_text,
            newline="",
        ),
        strict=True,
    )

    try:
        for source_row_number, row in enumerate(
            reader,
            start=1,
        ):
            row_values = tuple(row)

            if len(row_values) != _EXPECTED_FIELD_COUNT:
                raise OfacParseError(
                    "OFAC primary CSV row "
                    f"{source_row_number} must contain "
                    f"exactly {_EXPECTED_FIELD_COUNT} fields; "
                    f"found {len(row_values)}."
                )

            publisher_record_id = row_values[0]

            previous_row = seen_publisher_records.get(publisher_record_id)

            if previous_row is not None:
                if previous_row == row_values:
                    raise OfacParseError(
                        "OFAC primary CSV contains a "
                        "duplicate publisher identifier "
                        f"'{publisher_record_id}' with "
                        "an exact duplicate record."
                    )

                raise OfacParseError(
                    "OFAC primary CSV contains a "
                    "contradictory duplicate publisher "
                    f"identifier '{publisher_record_id}'."
                )

            seen_publisher_records[publisher_record_id] = row_values

            try:
                record = OfacPrimaryRecord(
                    source_key=source_key,
                    publisher_record_id=row_values[0],
                    source_row_number=source_row_number,
                    source_row_fingerprint=(_fingerprint_row(row_values)),
                    primary_name_raw=row_values[1],
                    source_entity_type_raw=row_values[2],
                    program_text_raw=row_values[3],
                    title_raw=row_values[4],
                    call_sign_raw=row_values[5],
                    vessel_type_raw=row_values[6],
                    tonnage_raw=row_values[7],
                    grt_raw=row_values[8],
                    vessel_flag_raw=row_values[9],
                    vessel_owner_raw=row_values[10],
                    remarks_raw=row_values[11],
                    acquisition_method=(snapshot.acquisition_method),
                    acquired_at=snapshot.fetched_at,
                    source_sha256=snapshot.sha256,
                )
            except ValidationError as exc:
                raise OfacParseError(
                    "OFAC primary record at row "
                    f"{source_row_number} violated "
                    f"the source contract: {exc}"
                ) from exc

            records.append(record)

    except csv.Error as exc:
        raise OfacParseError("OFAC primary CSV structure could not be parsed safely.") from exc

    if not records:
        raise OfacParseError("OFAC primary CSV contains no publisher records.")

    return tuple(records)


def _validate_source_key(
    source_key: str,
) -> OfacSourceKey:
    """Require one of the two approved OFAC primary source identities."""

    if source_key == "ofac_sdn_csv":
        return "ofac_sdn_csv"

    if source_key == "ofac_consolidated_csv":
        return "ofac_consolidated_csv"

    raise OfacParseError(
        "Snapshot source_key must identify an "
        "approved OFAC source: "
        "ofac_sdn_csv or "
        "ofac_consolidated_csv."
    )


def _reconcile_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> None:
    """Reconcile exact source bytes against trusted acquisition provenance."""

    actual_byte_size = len(content)

    if actual_byte_size != snapshot.byte_size:
        raise OfacParseError(
            "OFAC source byte size does not match "
            "the trusted SourceSnapshot: "
            f"artifact={actual_byte_size}, "
            f"snapshot={snapshot.byte_size}."
        )

    actual_sha256 = sha256(content).hexdigest()

    if actual_sha256 != snapshot.sha256:
        raise OfacParseError("OFAC source SHA-256 does not match the trusted SourceSnapshot.")


def _remove_terminal_control(
    content: bytes,
) -> bytes:
    """Require and remove OFAC's terminal ASCII SUB control byte."""

    if not content.endswith(_TERMINAL_SUB):
        raise OfacParseError(
            "OFAC primary CSV is missing the required terminal SUB control record."
        )

    return content[: -len(_TERMINAL_SUB)]


def _fingerprint_row(
    row: tuple[str, ...],
) -> str:
    """Hash the ordered raw publisher fields with unambiguous framing."""

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
