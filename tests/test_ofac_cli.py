"""Operator CLI regression tests for OFAC evidence refresh."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Never
from urllib.error import URLError

import pytest
from typer.testing import CliRunner

from black_meridian.cli import app
from black_meridian.data_sources.models import (
    DataSource,
    SourceSnapshot,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
    OfacEvidenceSet,
)
from black_meridian.ofac.workflow import (
    OFAC_CSV_FILENAME,
    OFAC_JSON_FILENAME,
    OfacEvidenceResult,
)

runner = CliRunner()

_FETCHED_AT = datetime(
    2026,
    9,
    1,
    12,
    0,
    tzinfo=UTC,
)


def _snapshot(
    source: DataSource,
    destination: Path,
) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=source.key,
        acquisition_method="direct_http",
        requested_url=source.url,
        resolved_url=source.url,
        fetched_at=_FETCHED_AT,
        sha256=sha256(source.key.encode("utf-8")).hexdigest(),
        byte_size=1234,
        content_type="text/csv",
        destination=str(destination),
    )


def test_ofac_command_exposes_refresh_surface() -> None:
    result = runner.invoke(
        app,
        [
            "ofac",
            "--help",
        ],
    )

    assert result.exit_code == 0, result.output

    assert "refresh" in result.output


def test_ofac_refresh_orchestrates_complete_trusted_source_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "raw"

    output_dir = tmp_path / "reference"

    captured_fetches: list[
        tuple[
            str,
            Path,
            float,
        ]
    ] = []

    captured_manifests: list[
        tuple[
            str,
            Path,
        ]
    ] = []

    captured_workflows: list[
        tuple[
            tuple[
                SourceSnapshot,
                ...,
            ],
            Path,
        ]
    ] = []

    snapshots: list[SourceSnapshot] = []

    def fake_fetch_source(
        source: DataSource,
        destination: Path,
        *,
        timeout_seconds: float = 60.0,
        user_agent: str = "",
    ) -> SourceSnapshot:
        del user_agent

        captured_fetches.append(
            (
                source.key,
                destination,
                timeout_seconds,
            )
        )

        snapshot = _snapshot(
            source,
            destination,
        )

        snapshots.append(snapshot)

        return snapshot

    def fake_write_snapshot_manifest(
        snapshot: SourceSnapshot,
        destination: Path,
    ) -> Path:
        captured_manifests.append(
            (
                snapshot.source_key,
                destination,
            )
        )

        return destination.with_name(f"{destination.name}.manifest.json")

    def fake_build_ofac_evidence(
        source_snapshots: tuple[
            SourceSnapshot,
            ...,
        ],
        evidence_output_dir: Path,
    ) -> OfacEvidenceResult:
        captured_workflows.append(
            (
                source_snapshots,
                evidence_output_dir,
            )
        )

        evidence_set = OfacEvidenceSet(snapshots=source_snapshots)

        return OfacEvidenceResult(
            source_paths=tuple(Path(snapshot.destination) for snapshot in source_snapshots),
            csv_path=(evidence_output_dir / OFAC_CSV_FILENAME),
            json_path=(evidence_output_dir / OFAC_JSON_FILENAME),
            evidence_set=evidence_set,
            entities=(),
        )

    monkeypatch.setattr(
        "black_meridian.ofac.cli.fetch_source",
        fake_fetch_source,
    )

    monkeypatch.setattr(
        "black_meridian.ofac.cli.write_snapshot_manifest",
        fake_write_snapshot_manifest,
    )

    monkeypatch.setattr(
        "black_meridian.ofac.cli.build_ofac_evidence",
        fake_build_ofac_evidence,
    )

    result = runner.invoke(
        app,
        [
            "ofac",
            "refresh",
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
            "--timeout",
            "17.5",
        ],
    )

    assert result.exit_code == 0, result.output

    assert [item[0] for item in captured_fetches] == list(OFAC_EVIDENCE_SOURCE_KEYS)

    assert all(
        timeout == 17.5
        for (
            _,
            _,
            timeout,
        ) in captured_fetches
    )

    assert len(captured_manifests) == 8

    assert len(captured_workflows) == 1

    workflow_snapshots, workflow_output_dir = captured_workflows[0]

    assert len(workflow_snapshots) == 8

    assert workflow_output_dir == output_dir

    assert "OFAC evidence refresh completed." in result.output

    assert "Sources: 8" in result.output

    assert "Entities: 0" in result.output

    assert "Evidence set SHA-256:" in result.output

    assert f"CSV: {output_dir / OFAC_CSV_FILENAME}" in result.output

    assert f"JSON: {output_dir / OFAC_JSON_FILENAME}" in result.output

    for source_key in OFAC_EVIDENCE_SOURCE_KEYS:
        assert f"Source {source_key}:" in result.output

        assert f"Manifest {source_key}:" in result.output


def test_ofac_refresh_reports_acquisition_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_fetch_source(
        source: DataSource,
        destination: Path,
        *,
        timeout_seconds: float = 60.0,
        user_agent: str = "",
    ) -> Never:
        del source
        del destination
        del timeout_seconds
        del user_agent

        raise URLError("simulated OFAC retrieval failure")

    monkeypatch.setattr(
        "black_meridian.ofac.cli.fetch_source",
        fail_fetch_source,
    )

    result = runner.invoke(
        app,
        [
            "ofac",
            "refresh",
        ],
    )

    assert result.exit_code == 1

    assert "OFAC refresh failed:" in result.output

    assert "simulated OFAC retrieval failure" in result.output

    assert "OFAC evidence refresh completed." not in result.output
