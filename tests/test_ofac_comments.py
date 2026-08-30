"""Adversarial regression tests for OFAC remarks spillover parsing."""

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
from black_meridian.ofac.comments import (
    OfacCommentParseError,
    parse_ofac_comment_snapshot,
)

_FETCHED_AT = datetime(
    2026,
    8,
    30,
    12,
    0,
    tzinfo=UTC,
)

_COMMENT_ROW = (
    "17013",
    ("r 1027700342890 (Russia); Registration Number 123456."),
)


def _encode_comments(
    rows: tuple[
        tuple[str, ...],
        ...,
    ],
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
    source_key: str = ("ofac_sdn_comments_csv"),
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


def test_comment_parser_emits_provenance_bound_record() -> None:
    content = _encode_comments((_COMMENT_ROW,))

    snapshot = _snapshot(content)

    records = parse_ofac_comment_snapshot(
        content,
        snapshot,
    )

    assert len(records) == 1

    record = records[0]

    assert record.parent_publisher_record_id == "17013"

    assert record.continuation_raw == _COMMENT_ROW[1]

    assert record.parent_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert record.source_record_key == (
        "ofac_sdn_comments_csv",
        "17013",
    )

    assert record.source_sha256 == snapshot.sha256

    assert len(record.source_row_fingerprint) == 64


def test_consolidated_comment_maps_to_consolidated_primary() -> None:
    content = _encode_comments((_COMMENT_ROW,))

    record = parse_ofac_comment_snapshot(
        content,
        _snapshot(
            content,
            source_key=("ofac_consolidated_comments_csv"),
        ),
    )[0]

    assert record.parent_record_key == (
        "ofac_consolidated_csv",
        "17013",
    )


def test_comment_parser_preserves_commas_and_midword_continuation() -> None:
    row = (
        "17013",
        ("r 1027700342890, Russia; additional identifier."),
    )

    content = _encode_comments((row,))

    record = parse_ofac_comment_snapshot(
        content,
        _snapshot(content),
    )[0]

    assert record.continuation_raw == row[1]


def test_comment_parser_rejects_wrong_field_count() -> None:
    malformed = (
        "17013",
        "continuation",
        "unexpected",
    )

    content = _encode_comments((malformed,))

    with pytest.raises(
        OfacCommentParseError,
        match="2 fields",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_rejects_duplicate_parent() -> None:
    content = _encode_comments(
        (
            _COMMENT_ROW,
            _COMMENT_ROW,
        )
    )

    with pytest.raises(
        OfacCommentParseError,
        match="duplicate",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_rejects_contradictory_parent() -> None:
    second = (
        "17013",
        "different continuation",
    )

    content = _encode_comments(
        (
            _COMMENT_ROW,
            second,
        )
    )

    with pytest.raises(
        OfacCommentParseError,
        match="contradictory",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_rejects_non_numeric_parent() -> None:
    malformed = (
        "ENTITY-A",
        "continuation",
    )

    content = _encode_comments((malformed,))

    with pytest.raises(
        OfacCommentParseError,
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_rejects_empty_continuation() -> None:
    malformed = (
        "17013",
        "",
    )

    content = _encode_comments((malformed,))

    with pytest.raises(
        OfacCommentParseError,
        match="continuation",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_rejects_snapshot_size_drift() -> None:
    content = _encode_comments((_COMMENT_ROW,))

    with pytest.raises(
        OfacCommentParseError,
        match="byte size",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(
                content,
                byte_size=(len(content) + 1),
            ),
        )


def test_comment_parser_rejects_snapshot_digest_drift() -> None:
    content = _encode_comments((_COMMENT_ROW,))

    with pytest.raises(
        OfacCommentParseError,
        match="SHA-256",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(
                content,
                digest="f" * 64,
            ),
        )


def test_comment_parser_rejects_wrong_source_family() -> None:
    content = _encode_comments((_COMMENT_ROW,))

    source = get_source("ofac_sdn_aliases_csv")

    snapshot = SourceSnapshot(
        source_key=source.key,
        acquisition_method="direct_http",
        requested_url=source.url,
        resolved_url=source.url,
        fetched_at=_FETCHED_AT,
        sha256=sha256(content).hexdigest(),
        byte_size=len(content),
        content_type="text/csv",
        destination=(f"data/raw/external/{source.key}/{source.filename}"),
    )

    with pytest.raises(
        OfacCommentParseError,
        match="comments source",
    ):
        parse_ofac_comment_snapshot(
            content,
            snapshot,
        )


def test_comment_parser_rejects_interior_sub_control() -> None:
    first = _encode_comments(
        (_COMMENT_ROW,),
        terminal_control=False,
    )

    second = _encode_comments(
        (
            (
                "17014",
                "second continuation",
            ),
        )
    )

    content = first + b"\x1a\r\n" + second

    with pytest.raises(
        OfacCommentParseError,
        match="interior SUB",
    ):
        parse_ofac_comment_snapshot(
            content,
            _snapshot(content),
        )


def test_comment_parser_accepts_absent_terminal_sub() -> None:
    content = _encode_comments(
        (_COMMENT_ROW,),
        terminal_control=False,
    )

    records = parse_ofac_comment_snapshot(
        content,
        _snapshot(content),
    )

    assert len(records) == 1


def test_comment_parser_accepts_empty_spillover_relation_set() -> None:
    content = b"\x1a"

    records = parse_ofac_comment_snapshot(
        content,
        _snapshot(content),
    )

    assert records == ()
