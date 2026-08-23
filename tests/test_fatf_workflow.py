from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl

from black_meridian.data_sources import SourceSnapshot
from black_meridian.fatf import (
    serialize_fatf_csv,
    serialize_fatf_json,
)
from black_meridian.fatf.workflow import (
    FATF_CSV_FILENAME,
    FATF_JSON_FILENAME,
    FATF_SOURCE_KEY,
    FatfWorkflowError,
    build_fatf_evidence,
)

SOURCE_URL_TEXT = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
SOURCE_URL = AnyHttpUrl(SOURCE_URL_TEXT)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fatf" / "publication_page.html"

FETCHED_AT = datetime(
    2026,
    6,
    19,
    12,
    34,
    56,
    tzinfo=UTC,
)


def _snapshot_for_source(
    source_path: Path,
    source_bytes: bytes,
    *,
    source_key: str = FATF_SOURCE_KEY,
    byte_size: int | None = None,
    content_sha256: str | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=source_key,
        requested_url=SOURCE_URL,
        resolved_url=SOURCE_URL,
        fetched_at=FETCHED_AT,
        sha256=(sha256(source_bytes).hexdigest() if content_sha256 is None else content_sha256),
        byte_size=(len(source_bytes) if byte_size is None else byte_size),
        content_type="text/html; charset=utf-8",
        destination=str(source_path),
    )


def _write_trusted_source(
    tmp_path: Path,
    source_bytes: bytes,
    *,
    source_key: str = FATF_SOURCE_KEY,
    byte_size: int | None = None,
    content_sha256: str | None = None,
) -> SourceSnapshot:
    source_path = tmp_path / "raw" / "fatf-black-and-grey-lists.html"

    source_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_path.write_bytes(source_bytes)

    return _snapshot_for_source(
        source_path,
        source_bytes,
        source_key=source_key,
        byte_size=byte_size,
        content_sha256=content_sha256,
    )


def test_workflow_builds_validated_fatf_evidence(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes()

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
    )

    output_dir = tmp_path / "reference"

    result = build_fatf_evidence(
        source_snapshot,
        output_dir,
    )

    expected_csv_path = output_dir / FATF_CSV_FILENAME

    expected_json_path = output_dir / FATF_JSON_FILENAME

    assert result.source_path == Path(source_snapshot.destination)

    assert result.csv_path == expected_csv_path
    assert result.json_path == expected_json_path

    assert expected_csv_path.exists()
    assert expected_json_path.exists()

    assert expected_csv_path.read_bytes() == serialize_fatf_csv(result.snapshot)

    assert expected_json_path.read_bytes() == serialize_fatf_json(result.snapshot)

    assert result.snapshot.publication_date == date(2026, 6, 19)

    assert result.snapshot.retrieved_at == FETCHED_AT

    assert result.snapshot.content_sha256 == source_snapshot.sha256

    assert str(result.snapshot.source_url) == SOURCE_URL_TEXT

    assert result.snapshot.record_count == 6

    assert tuple(record.iso_alpha3 for record in result.snapshot.records) == (
        "PRK",
        "IRN",
        "MMR",
        "AGO",
        "HTI",
        "KEN",
    )

    assert not (output_dir / f".{FATF_CSV_FILENAME}.partial").exists()

    assert not (output_dir / f".{FATF_JSON_FILENAME}.partial").exists()


def test_workflow_rejects_unexpected_source_identity(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes()

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
        source_key="ofac_sdn_csv",
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match="unexpected source key",
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_source_byte_size_drift(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes()

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
        byte_size=len(source_bytes) + 1,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match=("byte size no longer matches its provenance snapshot"),
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_source_sha256_drift(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes()

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
        content_sha256="0" * 64,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match=("SHA-256 no longer matches its provenance snapshot"),
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_missing_source_artifact(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes()

    missing_source_path = tmp_path / "missing" / "fatf-black-and-grey-lists.html"

    source_snapshot = _snapshot_for_source(
        missing_source_path,
        source_bytes,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match=("source artifact could not be read"),
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_non_utf8_source(
    tmp_path: Path,
) -> None:
    source_bytes = b"\xff\xfe\xfa\xfb"

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match="not valid UTF-8 HTML",
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_invalid_fatf_structure(
    tmp_path: Path,
) -> None:
    source_bytes = (
        b"<!doctype html>"
        b"<html>"
        b"<body>"
        b"<h1>Not a FATF monitored-jurisdiction publication</h1>"
        b"</body>"
        b"</html>"
    )

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match=("could not be converted into validated jurisdiction intelligence"),
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()


def test_workflow_rejects_unknown_jurisdiction_identity(
    tmp_path: Path,
) -> None:
    source_bytes = FIXTURE_PATH.read_bytes().replace(
        b"Angola",
        b"Atlantis",
    )

    source_snapshot = _write_trusted_source(
        tmp_path,
        source_bytes,
    )

    output_dir = tmp_path / "reference"

    with pytest.raises(
        FatfWorkflowError,
        match=("could not be converted into validated jurisdiction intelligence"),
    ):
        build_fatf_evidence(
            source_snapshot,
            output_dir,
        )

    assert not output_dir.exists()
