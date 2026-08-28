"""Adversarial regression tests for OFAC address and alias relations."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO

import pytest

from black_meridian.data_sources.models import (
    SourceSnapshot,
)
from black_meridian.data_sources.registry import (
    get_source,
)
from black_meridian.ofac.relations import (
    OfacRelationParseError,
    parse_ofac_address_snapshot,
    parse_ofac_alias_snapshot,
)

_FETCHED_AT = datetime(
    2026,
    8,
    28,
    12,
    0,
    tzinfo=UTC,
)

_ADDRESS_ROW = (
    "17013",
    "41001",
    "123 Publisher Street",
    "Moscow 101000",
    "Russia",
    "-0- ",
)

_SECOND_ADDRESS_ROW = (
    "17013",
    "41002",
    "456 Publisher Street",
    "Moscow 101001",
    "Russia",
    "Secondary published address.",
)

_ALIAS_ROW = (
    "17013",
    "51001",
    "a.k.a.",
    "VTB BANK",
    "-0- ",
)

_SECOND_ALIAS_ROW = (
    "17013",
    "51002",
    "f.k.a.",
    "PUBLISHER BANK NAME",
    "Historical publisher alias.",
)


def _encode_csv(
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
    source_key: str,
    *,
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


def test_address_parser_emits_provenance_bound_record() -> None:
    content = _encode_csv((_ADDRESS_ROW,))

    snapshot = _snapshot(
        content,
        "ofac_sdn_addresses_csv",
    )

    records = parse_ofac_address_snapshot(
        content,
        snapshot,
    )

    assert len(records) == 1

    record = records[0]

    assert record.parent_publisher_record_id == "17013"

    assert record.publisher_relation_id == "41001"

    assert record.address_raw == ("123 Publisher Street")

    assert record.parent_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert record.source_record_key == (
        "ofac_sdn_addresses_csv",
        "41001",
    )

    assert record.source_sha256 == snapshot.sha256

    assert len(record.source_row_fingerprint) == 64


def test_alias_parser_emits_provenance_bound_record() -> None:
    content = _encode_csv((_ALIAS_ROW,))

    snapshot = _snapshot(
        content,
        "ofac_sdn_aliases_csv",
    )

    records = parse_ofac_alias_snapshot(
        content,
        snapshot,
    )

    record = records[0]

    assert record.alias_type_raw == "a.k.a."
    assert record.alias_name_raw == "VTB BANK"

    assert record.parent_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert record.source_record_key == (
        "ofac_sdn_aliases_csv",
        "51001",
    )


@pytest.mark.parametrize(
    (
        "source_key",
        "expected_parent_source",
    ),
    [
        (
            "ofac_consolidated_addresses_csv",
            "ofac_consolidated_csv",
        ),
        (
            "ofac_consolidated_aliases_csv",
            "ofac_consolidated_csv",
        ),
    ],
)
def test_consolidated_relations_map_to_consolidated_primary(
    source_key: str,
    expected_parent_source: str,
) -> None:
    if source_key.endswith("addresses_csv"):
        content = _encode_csv((_ADDRESS_ROW,))

        record = parse_ofac_address_snapshot(
            content,
            _snapshot(
                content,
                source_key,
            ),
        )[0]

    else:
        content = _encode_csv((_ALIAS_ROW,))

        record = parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                source_key,
            ),
        )[0]

    assert record.parent_source_key == expected_parent_source


def test_multiple_addresses_may_share_parent_identifier() -> None:
    content = _encode_csv(
        (
            _ADDRESS_ROW,
            _SECOND_ADDRESS_ROW,
        )
    )

    records = parse_ofac_address_snapshot(
        content,
        _snapshot(
            content,
            "ofac_sdn_addresses_csv",
        ),
    )

    assert len(records) == 2

    assert {record.parent_publisher_record_id for record in records} == {"17013"}

    assert {record.publisher_relation_id for record in records} == {
        "41001",
        "41002",
    }


def test_multiple_aliases_may_share_parent_identifier() -> None:
    content = _encode_csv(
        (
            _ALIAS_ROW,
            _SECOND_ALIAS_ROW,
        )
    )

    records = parse_ofac_alias_snapshot(
        content,
        _snapshot(
            content,
            "ofac_sdn_aliases_csv",
        ),
    )

    assert len(records) == 2

    assert {record.publisher_relation_id for record in records} == {
        "51001",
        "51002",
    }


def test_address_parser_rejects_wrong_field_count() -> None:
    malformed = _ADDRESS_ROW[:-1]

    content = _encode_csv((malformed,))

    with pytest.raises(
        OfacRelationParseError,
        match="6 fields",
    ):
        parse_ofac_address_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_addresses_csv",
            ),
        )


def test_alias_parser_rejects_wrong_field_count() -> None:
    malformed = _ALIAS_ROW[:-1]

    content = _encode_csv((malformed,))

    with pytest.raises(
        OfacRelationParseError,
        match="5 fields",
    ):
        parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_relation_parser_rejects_duplicate_address_identifier() -> None:
    content = _encode_csv(
        (
            _ADDRESS_ROW,
            _ADDRESS_ROW,
        )
    )

    with pytest.raises(
        OfacRelationParseError,
        match="duplicate",
    ):
        parse_ofac_address_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_addresses_csv",
            ),
        )


def test_relation_parser_rejects_contradictory_alias_identifier() -> None:
    contradictory_alias = (
        "17013",
        "51001",
        "a.k.a.",
        "DIFFERENT ALIAS",
        "-0- ",
    )

    content = _encode_csv(
        (
            _ALIAS_ROW,
            contradictory_alias,
        )
    )

    with pytest.raises(
        OfacRelationParseError,
        match="contradictory",
    ):
        parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_alias_parser_rejects_blank_alias_name() -> None:
    malformed = (
        "17013",
        "51001",
        "a.k.a.",
        "   ",
        "-0- ",
    )

    content = _encode_csv((malformed,))

    with pytest.raises(
        OfacRelationParseError,
        match="alias name",
    ):
        parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_relation_parser_rejects_non_numeric_parent_identifier() -> None:
    malformed = (
        "ENTITY-A",
        *_ADDRESS_ROW[1:],
    )

    content = _encode_csv((malformed,))

    with pytest.raises(
        OfacRelationParseError,
    ):
        parse_ofac_address_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_addresses_csv",
            ),
        )


def test_relation_parser_rejects_non_numeric_relation_identifier() -> None:
    malformed = (
        _ALIAS_ROW[0],
        "ALIAS-A",
        *_ALIAS_ROW[2:],
    )

    content = _encode_csv((malformed,))

    with pytest.raises(
        OfacRelationParseError,
    ):
        parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_relation_parser_rejects_snapshot_byte_size_drift() -> None:
    content = _encode_csv((_ADDRESS_ROW,))

    snapshot = _snapshot(
        content,
        "ofac_sdn_addresses_csv",
        byte_size=len(content) + 1,
    )

    with pytest.raises(
        OfacRelationParseError,
        match="byte size",
    ):
        parse_ofac_address_snapshot(
            content,
            snapshot,
        )


def test_relation_parser_rejects_snapshot_sha256_drift() -> None:
    content = _encode_csv((_ALIAS_ROW,))

    snapshot = _snapshot(
        content,
        "ofac_sdn_aliases_csv",
        digest="f" * 64,
    )

    with pytest.raises(
        OfacRelationParseError,
        match="SHA-256",
    ):
        parse_ofac_alias_snapshot(
            content,
            snapshot,
        )


def test_relation_parser_rejects_wrong_source_family() -> None:
    content = _encode_csv((_ADDRESS_ROW,))

    with pytest.raises(
        OfacRelationParseError,
        match="address source",
    ):
        parse_ofac_address_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_relation_parser_rejects_interior_sub_control() -> None:
    first = _encode_csv(
        (_ALIAS_ROW,),
        terminal_control=False,
    )

    second = _encode_csv((_SECOND_ALIAS_ROW,))

    content = first + b"\x1a\r\n" + second

    with pytest.raises(
        OfacRelationParseError,
        match="interior SUB",
    ):
        parse_ofac_alias_snapshot(
            content,
            _snapshot(
                content,
                "ofac_sdn_aliases_csv",
            ),
        )


def test_relation_parser_accepts_source_without_terminal_sub() -> None:
    content = _encode_csv(
        (_ADDRESS_ROW,),
        terminal_control=False,
    )

    records = parse_ofac_address_snapshot(
        content,
        _snapshot(
            content,
            "ofac_sdn_addresses_csv",
        ),
    )

    assert len(records) == 1
