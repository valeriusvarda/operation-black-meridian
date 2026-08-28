"""Adversarial regression tests for the OFAC primary CSV parser."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO

import pytest

from black_meridian.data_sources.models import SourceSnapshot
from black_meridian.data_sources.registry import get_source
from black_meridian.ofac.contracts import OfacSubjectKind
from black_meridian.ofac.parser import (
    OfacParseError,
    parse_ofac_primary_snapshot,
)

_FETCHED_AT = datetime(
    2026,
    8,
    28,
    12,
    0,
    tzinfo=UTC,
)

_SDN_ROW = (
    "17013",
    "VTB BANK PUBLIC JOINT STOCK COMPANY",
    "-0- ",
    "UKRAINE-EO13662] [RUSSIA-EO14024",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
)

_CONSOLIDATED_ROW = (
    "9640",
    "ABU TEIR, Mohammed",
    "individual",
    "NS-PLC",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "-0- ",
    "DOB 1951; POB Umm Tuba.",
)


def _encode_primary_csv(
    rows: tuple[tuple[str, ...], ...],
    *,
    terminal_control: bool = True,
) -> bytes:
    stream = StringIO(newline="")

    writer = csv.writer(
        stream,
        lineterminator="\r\n",
    )

    writer.writerows(rows)

    payload = stream.getvalue()

    if terminal_control:
        payload += "\x1a"

    return payload.encode("utf-8")


def _snapshot(
    content: bytes,
    *,
    source_key: str = "ofac_sdn_csv",
    byte_size: int | None = None,
    digest: str | None = None,
) -> SourceSnapshot:
    source = get_source(source_key)

    return SourceSnapshot(
        source_key=source.key,
        acquisition_method="direct_http",
        requested_url=source.url,
        resolved_url=source.url,
        fetched_at=_FETCHED_AT,
        sha256=(digest if digest is not None else sha256(content).hexdigest()),
        byte_size=(byte_size if byte_size is not None else len(content)),
        content_type="text/csv",
        destination=(f"data/raw/external/{source.key}/{source.filename}"),
    )


def test_parser_emits_provenance_bound_sdn_record() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    snapshot = _snapshot(content)

    records = parse_ofac_primary_snapshot(
        content,
        snapshot,
    )

    assert len(records) == 1

    record = records[0]

    assert record.source_key == "ofac_sdn_csv"
    assert record.publisher_record_id == "17013"

    assert record.source_row_number == 1

    assert record.primary_name_raw == ("VTB BANK PUBLIC JOINT STOCK COMPANY")

    assert record.source_entity_type_raw == "-0- "

    assert record.program_text_raw == ("UKRAINE-EO13662] [RUSSIA-EO14024")

    assert record.subject_kind is OfacSubjectKind.UNSPECIFIED

    assert record.source_sha256 == snapshot.sha256
    assert record.acquired_at == snapshot.fetched_at
    assert record.acquisition_method == "direct_http"

    assert record.source_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert len(record.source_row_fingerprint) == 64


def test_parser_accepts_consolidated_primary_source() -> None:
    content = _encode_primary_csv((_CONSOLIDATED_ROW,))

    snapshot = _snapshot(
        content,
        source_key="ofac_consolidated_csv",
    )

    records = parse_ofac_primary_snapshot(
        content,
        snapshot,
    )

    assert len(records) == 1

    record = records[0]

    assert record.source_key == "ofac_consolidated_csv"
    assert record.publisher_record_id == "9640"

    assert record.subject_kind is OfacSubjectKind.INDIVIDUAL

    assert record.remarks_raw == ("DOB 1951; POB Umm Tuba.")


def test_parser_does_not_emit_terminal_sub_control_record() -> None:
    content = _encode_primary_csv(
        (
            _SDN_ROW,
            _CONSOLIDATED_ROW,
        )
    )

    records = parse_ofac_primary_snapshot(
        content,
        _snapshot(content),
    )

    assert len(records) == 2

    assert [record.source_row_number for record in records] == [
        1,
        2,
    ]


def test_parser_requires_terminal_sub_control_record() -> None:
    content = _encode_primary_csv(
        (_SDN_ROW,),
        terminal_control=False,
    )

    with pytest.raises(
        OfacParseError,
        match="terminal",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_interior_sub_control_record() -> None:
    content = (
        _encode_primary_csv(
            (_SDN_ROW,),
            terminal_control=False,
        )
        + b"\x1a\r\n"
        + _encode_primary_csv((_CONSOLIDATED_ROW,))
    )

    with pytest.raises(
        OfacParseError,
        match="structure",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_non_twelve_field_record() -> None:
    malformed_row = _SDN_ROW[:-1]

    content = _encode_primary_csv((malformed_row,))

    with pytest.raises(
        OfacParseError,
        match="12",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_snapshot_byte_size_drift() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    snapshot = _snapshot(
        content,
        byte_size=len(content) + 1,
    )

    with pytest.raises(
        OfacParseError,
        match="byte size",
    ):
        parse_ofac_primary_snapshot(
            content,
            snapshot,
        )


def test_parser_rejects_snapshot_sha256_drift() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    snapshot = _snapshot(
        content,
        digest="0" * 64,
    )

    with pytest.raises(
        OfacParseError,
        match="SHA-256",
    ):
        parse_ofac_primary_snapshot(
            content,
            snapshot,
        )


def test_parser_rejects_non_ofac_source_snapshot() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    snapshot = _snapshot(
        content,
        source_key="fatf_monitored_jurisdictions_html",
    )

    with pytest.raises(
        OfacParseError,
        match="approved OFAC source",
    ):
        parse_ofac_primary_snapshot(
            content,
            snapshot,
        )


def test_parser_rejects_non_utf8_source_bytes() -> None:
    content = b"\xff\xfe\x1a"

    with pytest.raises(
        OfacParseError,
        match="UTF-8",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_unsupported_publisher_entity_type() -> None:
    unsupported_row = (
        _SDN_ROW[0],
        _SDN_ROW[1],
        "organization",
        *_SDN_ROW[3:],
    )

    content = _encode_primary_csv((unsupported_row,))

    with pytest.raises(
        OfacParseError,
        match="entity type",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_exact_duplicate_publisher_identifier() -> None:
    content = _encode_primary_csv(
        (
            _SDN_ROW,
            _SDN_ROW,
        )
    )

    with pytest.raises(
        OfacParseError,
        match="duplicate publisher",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_parser_rejects_contradictory_duplicate_publisher_identifier() -> None:
    contradictory_row = (
        _SDN_ROW[0],
        "DIFFERENT PUBLISHER NAME",
        *_SDN_ROW[2:],
    )

    content = _encode_primary_csv(
        (
            _SDN_ROW,
            contradictory_row,
        )
    )

    with pytest.raises(
        OfacParseError,
        match="contradictory",
    ):
        parse_ofac_primary_snapshot(
            content,
            _snapshot(content),
        )


def test_row_fingerprint_is_deterministic() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    snapshot = _snapshot(content)

    first = parse_ofac_primary_snapshot(
        content,
        snapshot,
    )[0]

    second = parse_ofac_primary_snapshot(
        content,
        snapshot,
    )[0]

    assert first.source_row_fingerprint == second.source_row_fingerprint


def test_identical_publisher_row_has_same_fingerprint_across_sources() -> None:
    content = _encode_primary_csv((_SDN_ROW,))

    sdn_record = parse_ofac_primary_snapshot(
        content,
        _snapshot(
            content,
            source_key="ofac_sdn_csv",
        ),
    )[0]

    consolidated_record = parse_ofac_primary_snapshot(
        content,
        _snapshot(
            content,
            source_key="ofac_consolidated_csv",
        ),
    )[0]

    assert sdn_record.source_row_fingerprint == consolidated_record.source_row_fingerprint

    assert sdn_record.source_record_key != consolidated_record.source_record_key


def test_different_publisher_rows_have_different_fingerprints() -> None:
    content = _encode_primary_csv(
        (
            _SDN_ROW,
            _CONSOLIDATED_ROW,
        )
    )

    records = parse_ofac_primary_snapshot(
        content,
        _snapshot(content),
    )

    assert records[0].source_row_fingerprint != records[1].source_row_fingerprint
