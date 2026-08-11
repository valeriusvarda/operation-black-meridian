# cspell:words Côte Ivoire d'Ivoire fsync

import csv
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Never, cast

import pytest
from pydantic import HttpUrl

from black_meridian.data_sources.contracts import (
    FatfJurisdiction,
    FatfSnapshot,
    FatfTier,
)
from black_meridian.fatf.exporter import (
    serialize_fatf_csv,
    serialize_fatf_json,
    write_fatf_csv,
    write_fatf_json,
)

SOURCE_URL_TEXT = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
SOURCE_URL = HttpUrl(SOURCE_URL_TEXT)
CONTENT_SHA256 = "a" * 64

EXPECTED_CSV_TEXT = (
    "jurisdiction_name,iso_alpha3,tier,publication_date,source_name,source_url,"
    "retrieved_at,content_sha256\n"
    "Côte d'Ivoire,CIV,increased_monitoring,2026-06-19,Financial Action Task Force,"
    f"{SOURCE_URL_TEXT},2026-06-19T12:34:56+00:00,{CONTENT_SHA256}\n"
    '"Democratic Republic of the Congo, ""DRC""",COD,increased_monitoring,'
    "2026-06-19,Financial Action Task Force,"
    f"{SOURCE_URL_TEXT},2026-06-19T12:34:56+00:00,{CONTENT_SHA256}\n"
)

EXPECTED_JSON_TEXT = (
    "{\n"
    f'  "content_sha256": "{CONTENT_SHA256}",\n'
    '  "publication_date": "2026-06-19",\n'
    '  "record_count": 2,\n'
    '  "records": [\n'
    "    {\n"
    '      "iso_alpha3": "CIV",\n'
    '      "jurisdiction_name": "Côte d\'Ivoire",\n'
    '      "tier": "increased_monitoring"\n'
    "    },\n"
    "    {\n"
    '      "iso_alpha3": "COD",\n'
    '      "jurisdiction_name": "Democratic Republic of the Congo, \\"DRC\\"",\n'
    '      "tier": "increased_monitoring"\n'
    "    }\n"
    "  ],\n"
    '  "retrieved_at": "2026-06-19T12:34:56Z",\n'
    '  "source_name": "Financial Action Task Force",\n'
    f'  "source_url": "{SOURCE_URL_TEXT}"\n'
    "}\n"
)


class _FailingBinaryWriter:
    """Binary writer that persists a prefix and then raises a controlled failure."""

    def __init__(self, output: BinaryIO) -> None:
        self._output = output

    def __enter__(self) -> "_FailingBinaryWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._output.close()

    def write(self, payload: bytes) -> int:
        prefix_length = max(1, len(payload) // 2)

        self._output.write(payload[:prefix_length])

        self._output.flush()

        raise OSError("simulated partial-file write failure")

    def flush(self) -> None:
        self._output.flush()

    def fileno(self) -> int:
        return self._output.fileno()


def _snapshot() -> FatfSnapshot:
    return FatfSnapshot(
        source_url=SOURCE_URL,
        publication_date=date(
            2026,
            6,
            19,
        ),
        retrieved_at=datetime(
            2026,
            6,
            19,
            12,
            34,
            56,
            tzinfo=UTC,
        ),
        content_sha256=CONTENT_SHA256,
        records=(
            FatfJurisdiction(
                jurisdiction_name="Côte d'Ivoire",
                iso_alpha3="CIV",
                tier=FatfTier.INCREASED_MONITORING,
            ),
            FatfJurisdiction(
                jurisdiction_name=('Democratic Republic of the Congo, "DRC"'),
                iso_alpha3="COD",
                tier=FatfTier.INCREASED_MONITORING,
            ),
        ),
    )


def test_csv_serialization_matches_exact_byte_contract() -> None:
    serialized = serialize_fatf_csv(_snapshot())

    assert serialized == EXPECTED_CSV_TEXT.encode()
    assert b"\r\n" not in serialized

    rows = list(csv.reader(StringIO(serialized.decode("utf-8"))))

    assert rows[0] == [
        "jurisdiction_name",
        "iso_alpha3",
        "tier",
        "publication_date",
        "source_name",
        "source_url",
        "retrieved_at",
        "content_sha256",
    ]

    assert rows[1][0] == "Côte d'Ivoire"

    assert rows[2][0] == 'Democratic Republic of the Congo, "DRC"'


def test_json_serialization_matches_exact_byte_contract() -> None:
    serialized = serialize_fatf_json(_snapshot())

    assert serialized == EXPECTED_JSON_TEXT.encode()

    assert serialized.endswith(b"\n")

    assert "Côte d'Ivoire".encode() in serialized

    assert b"\\u00f4" not in serialized


def test_repeat_serialization_is_byte_identical() -> None:
    snapshot = _snapshot()

    assert serialize_fatf_csv(snapshot) == serialize_fatf_csv(snapshot)

    assert serialize_fatf_json(snapshot) == serialize_fatf_json(snapshot)


def test_csv_writer_creates_nested_parent_and_preserves_serializer_bytes(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "nested" / "fatf_jurisdictions.csv"

    result = write_fatf_csv(
        snapshot,
        destination,
    )

    partial_path = destination.with_name(f".{destination.name}.partial")

    assert result == destination

    assert destination.read_bytes() == serialize_fatf_csv(snapshot)

    assert not partial_path.exists()


def test_json_writer_creates_nested_parent_and_preserves_serializer_bytes(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "nested" / "fatf_snapshot.json"

    result = write_fatf_json(
        snapshot,
        destination,
    )

    partial_path = destination.with_name(f".{destination.name}.partial")

    assert result == destination

    assert destination.read_bytes() == serialize_fatf_json(snapshot)

    assert not partial_path.exists()


def test_repeated_writes_replace_stale_destinations(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()

    csv_destination = tmp_path / "fatf_jurisdictions.csv"

    json_destination = tmp_path / "fatf_snapshot.json"

    csv_destination.write_bytes(b"stale csv evidence")

    json_destination.write_bytes(b"stale json evidence")

    write_fatf_csv(
        snapshot,
        csv_destination,
    )

    write_fatf_json(
        snapshot,
        json_destination,
    )

    assert csv_destination.read_bytes() == serialize_fatf_csv(snapshot)

    assert json_destination.read_bytes() == serialize_fatf_json(snapshot)


def test_existing_partial_file_is_removed_after_success(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "fatf_jurisdictions.csv"

    partial_path = destination.with_name(f".{destination.name}.partial")

    partial_path.write_bytes(b"stale partial evidence")

    write_fatf_csv(
        snapshot,
        destination,
    )

    assert destination.read_bytes() == serialize_fatf_csv(snapshot)

    assert not partial_path.exists()


def test_partial_write_failure_preserves_destination_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "fatf_jurisdictions.csv"

    partial_path = destination.with_name(f".{destination.name}.partial")

    destination.write_bytes(b"existing evidence")

    original_open = Path.open

    def open_with_write_failure(
        path: Path,
        *_: object,
        **__: object,
    ) -> _FailingBinaryWriter:
        assert path == partial_path

        output = cast(
            BinaryIO,
            original_open(
                path,
                "wb",
            ),
        )

        return _FailingBinaryWriter(output)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            Path,
            "open",
            open_with_write_failure,
        )

        with pytest.raises(
            OSError,
            match=("simulated partial-file write failure"),
        ):
            write_fatf_csv(
                snapshot,
                destination,
            )

    assert destination.read_bytes() == b"existing evidence"

    assert not partial_path.exists()


def test_fsync_failure_preserves_destination_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "fatf_snapshot.json"

    partial_path = destination.with_name(f".{destination.name}.partial")

    destination.write_bytes(b"existing evidence")

    def fail_fsync(
        _: int,
    ) -> Never:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(
        "black_meridian.fatf.exporter.os.fsync",
        fail_fsync,
    )

    with pytest.raises(
        OSError,
        match="simulated fsync failure",
    ):
        write_fatf_json(
            snapshot,
            destination,
        )

    assert destination.read_bytes() == b"existing evidence"

    assert not partial_path.exists()


def test_replace_failure_preserves_destination_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()

    destination = tmp_path / "fatf_jurisdictions.csv"

    partial_path = destination.with_name(f".{destination.name}.partial")

    destination.write_bytes(b"existing evidence")

    def fail_replace(
        *_: object,
    ) -> Never:
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(
        "black_meridian.fatf.exporter.os.replace",
        fail_replace,
    )

    with pytest.raises(
        OSError,
        match=("simulated atomic replace failure"),
    ):
        write_fatf_csv(
            snapshot,
            destination,
        )

    assert destination.read_bytes() == b"existing evidence"

    assert not partial_path.exists()
