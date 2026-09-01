"""End-to-end offline regression tests for the OFAC evidence workflow."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path

import pytest

from black_meridian.data_sources.models import (
    SourceSnapshot,
)
from black_meridian.data_sources.registry import (
    get_source,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
)
from black_meridian.ofac.workflow import (
    OFAC_CSV_FILENAME,
    OFAC_JSON_FILENAME,
    OfacWorkflowError,
    build_ofac_evidence,
)

_FETCHED_AT = datetime(
    2026,
    9,
    1,
    12,
    0,
    tzinfo=UTC,
)


def _encode_csv(
    rows: tuple[
        tuple[str, ...],
        ...,
    ],
) -> bytes:
    stream = StringIO(newline="")

    writer = csv.writer(
        stream,
        lineterminator="\r\n",
    )

    writer.writerows(rows)

    return (stream.getvalue() + "\x1a").encode("utf-8")


def _rows_for_source(
    source_key: str,
    *,
    orphan_address: bool = False,
) -> tuple[
    tuple[str, ...],
    ...,
]:
    if source_key == "ofac_sdn_csv":
        return (
            (
                "100",
                "SDN TEST ENTITY",
                "-0- ",
                "TEST-PROGRAM",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "Registration Numbe",
            ),
        )

    if source_key == "ofac_consolidated_csv":
        return (
            (
                "200",
                "CONSOLIDATED TEST ENTITY",
                "individual",
                "TEST-CONSOLIDATED",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "-0- ",
                "Consolidated remarks.",
            ),
        )

    if source_key == "ofac_sdn_addresses_csv":
        return (
            (
                ("999" if orphan_address else "100"),
                "41001",
                "100 Example Street",
                "Example City",
                "Example Country",
                "-0- ",
            ),
        )

    if source_key == "ofac_consolidated_addresses_csv":
        return (
            (
                "200",
                "42001",
                "200 Example Street",
                "Example City",
                "Example Country",
                "-0- ",
            ),
        )

    if source_key == "ofac_sdn_aliases_csv":
        return (
            (
                "100",
                "51001",
                "a.k.a.",
                "SDN TEST ALIAS",
                "-0- ",
            ),
        )

    if source_key == "ofac_consolidated_aliases_csv":
        return (
            (
                "200",
                "52001",
                "a.k.a.",
                "CONSOLIDATED TEST ALIAS",
                "-0- ",
            ),
        )

    if source_key == "ofac_sdn_comments_csv":
        return (
            (
                "100",
                "r 123456.",
            ),
        )

    if source_key == "ofac_consolidated_comments_csv":
        return (
            (
                "200",
                " Additional remarks.",
            ),
        )

    raise AssertionError(f"Unhandled source key: {source_key}")


def _snapshots(
    root: Path,
    *,
    orphan_address: bool = False,
) -> tuple[
    SourceSnapshot,
    ...,
]:
    snapshots: list[SourceSnapshot] = []

    for source_key in OFAC_EVIDENCE_SOURCE_KEYS:
        source = get_source(source_key)

        destination = root / source.key / source.filename

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        content = _encode_csv(
            _rows_for_source(
                source_key,
                orphan_address=(orphan_address),
            )
        )

        destination.write_bytes(content)

        snapshots.append(
            SourceSnapshot(
                source_key=source.key,
                acquisition_method=("direct_http"),
                requested_url=(source.url),
                resolved_url=(source.url),
                fetched_at=(_FETCHED_AT),
                sha256=sha256(content).hexdigest(),
                byte_size=len(content),
                content_type="text/csv",
                destination=str(destination),
            )
        )

    return tuple(snapshots)


def test_workflow_builds_complete_deterministic_ofac_evidence(
    tmp_path: Path,
) -> None:
    snapshots = _snapshots(tmp_path / "raw")

    output_dir = tmp_path / "reference"

    result = build_ofac_evidence(
        snapshots,
        output_dir,
    )

    assert result.source_count == 8

    assert result.entity_count == 2

    assert result.address_count == 2

    assert result.alias_count == 2

    assert result.remarks_spillover_count == 2

    assert result.csv_path == output_dir / OFAC_CSV_FILENAME

    assert result.json_path == output_dir / OFAC_JSON_FILENAME

    assert result.csv_path.exists()

    assert result.json_path.exists()

    assert len(result.evidence_set.evidence_set_sha256) == 64


def test_workflow_output_is_independent_of_snapshot_input_order(
    tmp_path: Path,
) -> None:
    snapshots = _snapshots(tmp_path / "raw")

    first_dir = tmp_path / "first"

    second_dir = tmp_path / "second"

    first = build_ofac_evidence(
        snapshots,
        first_dir,
    )

    second = build_ofac_evidence(
        tuple(reversed(snapshots)),
        second_dir,
    )

    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()

    assert first.json_path.read_bytes() == second.json_path.read_bytes()


def test_workflow_rejects_incomplete_source_set(
    tmp_path: Path,
) -> None:
    snapshots = _snapshots(tmp_path / "raw")

    with pytest.raises(
        OfacWorkflowError,
        match="missing",
    ):
        build_ofac_evidence(
            snapshots[:-1],
            tmp_path / "reference",
        )


def test_workflow_rejects_source_bytes_mutated_after_snapshot(
    tmp_path: Path,
) -> None:
    snapshots = _snapshots(tmp_path / "raw")

    first_source_path = Path(snapshots[0].destination)

    first_source_path.write_bytes(first_source_path.read_bytes() + b"MUTATED")

    with pytest.raises(
        OfacWorkflowError,
        match="byte size",
    ):
        build_ofac_evidence(
            snapshots,
            tmp_path / "reference",
        )


def test_workflow_rejects_orphan_publisher_relation(
    tmp_path: Path,
) -> None:
    snapshots = _snapshots(
        tmp_path / "raw",
        orphan_address=True,
    )

    with pytest.raises(
        OfacWorkflowError,
        match="missing primary parent",
    ):
        build_ofac_evidence(
            snapshots,
            tmp_path / "reference",
        )
