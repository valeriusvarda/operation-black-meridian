from datetime import UTC, date, datetime
from pathlib import Path
from typing import Never
from urllib.error import URLError

import pytest
from pydantic import AnyHttpUrl, HttpUrl
from typer.testing import CliRunner

from black_meridian.cli import app
from black_meridian.data_sources import (
    AcquisitionMethod,
    DataSource,
    OperatorImportError,
    SourceSnapshot,
)
from black_meridian.data_sources.contracts import (
    FatfJurisdiction,
    FatfSnapshot,
    FatfTier,
)
from black_meridian.fatf.workflow import (
    FATF_CSV_FILENAME,
    FATF_JSON_FILENAME,
    FATF_SOURCE_KEY,
    FatfEvidenceResult,
    FatfWorkflowError,
)

runner = CliRunner()

FATF_SOURCE_URL_TEXT = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"

FATF_SOURCE_URL = AnyHttpUrl(FATF_SOURCE_URL_TEXT)

FATF_HTTP_URL = HttpUrl(FATF_SOURCE_URL_TEXT)

FETCHED_AT = datetime(
    2026,
    6,
    19,
    12,
    34,
    56,
    tzinfo=UTC,
)

CONTENT_SHA256 = "a" * 64


def _source_snapshot(
    destination: Path,
    *,
    acquisition_method: AcquisitionMethod = "direct_http",
) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=FATF_SOURCE_KEY,
        acquisition_method=acquisition_method,
        requested_url=FATF_SOURCE_URL,
        resolved_url=FATF_SOURCE_URL,
        fetched_at=FETCHED_AT,
        sha256=CONTENT_SHA256,
        byte_size=1234,
        content_type="text/html; charset=utf-8",
        destination=str(destination),
    )


def _fatf_snapshot() -> FatfSnapshot:
    return FatfSnapshot(
        source_url=FATF_HTTP_URL,
        publication_date=date(
            2026,
            6,
            19,
        ),
        retrieved_at=FETCHED_AT,
        content_sha256=CONTENT_SHA256,
        records=(
            FatfJurisdiction(
                jurisdiction_name="Iran",
                iso_alpha3="IRN",
                tier=FatfTier.CALL_FOR_ACTION,
            ),
        ),
    )


def _evidence_result(
    source_snapshot: SourceSnapshot,
    output_dir: Path,
) -> FatfEvidenceResult:
    return FatfEvidenceResult(
        source_path=Path(source_snapshot.destination),
        csv_path=(output_dir / FATF_CSV_FILENAME),
        json_path=(output_dir / FATF_JSON_FILENAME),
        snapshot=_fatf_snapshot(),
    )


def test_sources_list_command_exposes_approved_registry() -> None:
    result = runner.invoke(
        app,
        [
            "sources",
            "list",
        ],
    )

    assert result.exit_code == 0, result.output

    assert "ofac_sdn_csv" in result.output
    assert "ofac_consolidated_csv" in result.output
    assert "gleif_lei_records_json" in result.output
    assert FATF_SOURCE_KEY in result.output


def test_sources_fetch_rejects_unknown_source() -> None:
    result = runner.invoke(
        app,
        [
            "sources",
            "fetch",
            "unapproved_source",
        ],
    )

    assert result.exit_code == 2

    assert "Unknown source 'unapproved_source'" in result.output


def test_fatf_command_exposes_acquisition_surfaces() -> None:
    result = runner.invoke(
        app,
        [
            "fatf",
            "--help",
        ],
    )

    assert result.exit_code == 0, result.output

    assert "refresh" in result.output
    assert "import" in result.output


def test_fatf_import_help_exposes_operator_artifact_contract() -> None:
    result = runner.invoke(
        app,
        [
            "fatf",
            "import",
            "--help",
        ],
    )

    assert result.exit_code == 0, result.output

    assert "Operator-provided FATF HTML artifact" in result.output


def test_fatf_refresh_orchestrates_trusted_evidence_pipeline(
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
            SourceSnapshot,
            Path,
        ]
    ] = []

    captured_workflows: list[
        tuple[
            SourceSnapshot,
            Path,
        ]
    ] = []

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

        return _source_snapshot(destination)

    def fake_write_snapshot_manifest(
        snapshot: SourceSnapshot,
        destination: Path,
    ) -> Path:
        captured_manifests.append(
            (
                snapshot,
                destination,
            )
        )

        return destination.with_name(f"{destination.name}.manifest.json")

    def fake_build_fatf_evidence(
        source_snapshot: SourceSnapshot,
        evidence_output_dir: Path,
    ) -> FatfEvidenceResult:
        captured_workflows.append(
            (
                source_snapshot,
                evidence_output_dir,
            )
        )

        return _evidence_result(
            source_snapshot,
            evidence_output_dir,
        )

    monkeypatch.setattr(
        "black_meridian.cli.fetch_source",
        fake_fetch_source,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.write_snapshot_manifest"),
        fake_write_snapshot_manifest,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.build_fatf_evidence"),
        fake_build_fatf_evidence,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
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

    expected_source_path = source_dir / FATF_SOURCE_KEY / "fatf-black-and-grey-lists.html"

    expected_manifest_path = expected_source_path.with_name(
        f"{expected_source_path.name}.manifest.json"
    )

    assert captured_fetches == [
        (
            FATF_SOURCE_KEY,
            expected_source_path,
            17.5,
        )
    ]

    assert len(captured_manifests) == 1

    (
        manifest_snapshot,
        manifest_destination,
    ) = captured_manifests[0]

    assert manifest_snapshot.source_key == FATF_SOURCE_KEY

    assert manifest_snapshot.acquisition_method == "direct_http"

    assert manifest_destination == expected_source_path

    assert len(captured_workflows) == 1

    (
        workflow_snapshot,
        workflow_output_dir,
    ) = captured_workflows[0]

    assert workflow_snapshot.source_key == FATF_SOURCE_KEY

    assert workflow_snapshot.acquisition_method == "direct_http"

    assert workflow_output_dir == output_dir

    assert "FATF evidence refresh completed." in result.output

    assert "Acquisition method: direct_http" in result.output

    assert f"Source: {expected_source_path}" in result.output

    assert f"Manifest: {expected_manifest_path}" in result.output

    assert f"CSV: {output_dir / FATF_CSV_FILENAME}" in result.output

    assert f"JSON: {output_dir / FATF_JSON_FILENAME}" in result.output

    assert "Publication date: 2026-06-19" in result.output

    assert "Jurisdictions: 1" in result.output

    assert f"SHA-256: {CONTENT_SHA256}" in result.output

    assert (f"Retrieved at: {FETCHED_AT.isoformat()}") in result.output


def test_fatf_refresh_reports_source_retrieval_failure(
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

        raise URLError("simulated FATF retrieval failure")

    monkeypatch.setattr(
        "black_meridian.cli.fetch_source",
        fail_fetch_source,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
            "refresh",
        ],
    )

    assert result.exit_code == 1

    assert "FATF refresh failed:" in result.output

    assert "simulated FATF retrieval failure" in result.output

    assert "FATF evidence refresh completed." not in result.output


def test_fatf_refresh_reports_workflow_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "raw"

    source_path = source_dir / FATF_SOURCE_KEY / "fatf-black-and-grey-lists.html"

    def fake_fetch_source(
        source: DataSource,
        destination: Path,
        *,
        timeout_seconds: float = 60.0,
        user_agent: str = "",
    ) -> SourceSnapshot:
        del source
        del timeout_seconds
        del user_agent

        return _source_snapshot(destination)

    def fake_write_snapshot_manifest(
        snapshot: SourceSnapshot,
        destination: Path,
    ) -> Path:
        del snapshot

        return destination.with_name(f"{destination.name}.manifest.json")

    def fail_build_fatf_evidence(
        source_snapshot: SourceSnapshot,
        output_dir: Path,
    ) -> Never:
        del source_snapshot
        del output_dir

        raise FatfWorkflowError("simulated FATF workflow failure")

    monkeypatch.setattr(
        "black_meridian.cli.fetch_source",
        fake_fetch_source,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.write_snapshot_manifest"),
        fake_write_snapshot_manifest,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.build_fatf_evidence"),
        fail_build_fatf_evidence,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
            "refresh",
            "--source-dir",
            str(source_dir),
        ],
    )

    assert result.exit_code == 1

    assert ("FATF refresh failed: simulated FATF workflow failure") in result.output

    assert "FATF evidence refresh completed." not in result.output

    assert str(source_path) not in result.output


def test_fatf_import_orchestrates_operator_evidence_pipeline_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "operator-fatf.html"

    artifact_path.write_text(
        "<html>official FATF artifact</html>",
        encoding="utf-8",
    )

    source_dir = tmp_path / "raw"

    output_dir = tmp_path / "reference"

    captured_imports: list[
        tuple[
            str,
            Path,
            Path,
        ]
    ] = []

    captured_manifests: list[
        tuple[
            SourceSnapshot,
            Path,
        ]
    ] = []

    captured_workflows: list[
        tuple[
            SourceSnapshot,
            Path,
        ]
    ] = []

    def forbid_network_fetch(
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

        raise AssertionError("fatf import must not invoke direct HTTP acquisition")

    def fake_import_operator_source(
        source: DataSource,
        incoming_path: Path,
        destination: Path,
    ) -> SourceSnapshot:
        captured_imports.append(
            (
                source.key,
                incoming_path,
                destination,
            )
        )

        return _source_snapshot(
            destination,
            acquisition_method=("operator_import"),
        )

    def fake_write_snapshot_manifest(
        snapshot: SourceSnapshot,
        destination: Path,
    ) -> Path:
        captured_manifests.append(
            (
                snapshot,
                destination,
            )
        )

        return destination.with_name(f"{destination.name}.manifest.json")

    def fake_build_fatf_evidence(
        source_snapshot: SourceSnapshot,
        evidence_output_dir: Path,
    ) -> FatfEvidenceResult:
        captured_workflows.append(
            (
                source_snapshot,
                evidence_output_dir,
            )
        )

        return _evidence_result(
            source_snapshot,
            evidence_output_dir,
        )

    monkeypatch.setattr(
        "black_meridian.cli.fetch_source",
        forbid_network_fetch,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.import_operator_source"),
        fake_import_operator_source,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.write_snapshot_manifest"),
        fake_write_snapshot_manifest,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.build_fatf_evidence"),
        fake_build_fatf_evidence,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
            "import",
            str(artifact_path),
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output

    expected_destination = source_dir / FATF_SOURCE_KEY / "fatf-black-and-grey-lists.html"

    expected_manifest = expected_destination.with_name(f"{expected_destination.name}.manifest.json")

    assert captured_imports == [
        (
            FATF_SOURCE_KEY,
            artifact_path,
            expected_destination,
        )
    ]

    assert len(captured_manifests) == 1

    (
        manifest_snapshot,
        manifest_destination,
    ) = captured_manifests[0]

    assert manifest_snapshot.acquisition_method == "operator_import"

    assert manifest_destination == expected_destination

    assert len(captured_workflows) == 1

    (
        workflow_snapshot,
        workflow_output_dir,
    ) = captured_workflows[0]

    assert workflow_snapshot.acquisition_method == "operator_import"

    assert workflow_output_dir == output_dir

    assert "FATF operator import completed." in result.output

    assert "Acquisition method: operator_import" in result.output

    assert f"Imported from: {artifact_path}" in result.output

    assert f"Trusted source: {expected_destination}" in result.output

    assert f"Manifest: {expected_manifest}" in result.output

    assert f"CSV: {output_dir / FATF_CSV_FILENAME}" in result.output

    assert f"JSON: {output_dir / FATF_JSON_FILENAME}" in result.output

    assert "Publication date: 2026-06-19" in result.output

    assert "Jurisdictions: 1" in result.output

    assert f"SHA-256: {CONTENT_SHA256}" in result.output

    assert (f"Acquired at: {FETCHED_AT.isoformat()}") in result.output


def test_fatf_import_reports_operator_import_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "operator-fatf.html"

    artifact_path.write_text(
        "<html>official FATF artifact</html>",
        encoding="utf-8",
    )

    def fail_import_operator_source(
        source: DataSource,
        incoming_path: Path,
        destination: Path,
    ) -> Never:
        del source
        del incoming_path
        del destination

        raise OperatorImportError("simulated operator import failure")

    monkeypatch.setattr(
        ("black_meridian.cli.import_operator_source"),
        fail_import_operator_source,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
            "import",
            str(artifact_path),
        ],
    )

    assert result.exit_code == 1

    assert ("FATF import failed: simulated operator import failure") in result.output

    assert "FATF operator import completed." not in result.output


def test_fatf_import_reports_workflow_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "operator-fatf.html"

    artifact_path.write_text(
        "<html>official FATF artifact</html>",
        encoding="utf-8",
    )

    source_dir = tmp_path / "raw"

    def fake_import_operator_source(
        source: DataSource,
        incoming_path: Path,
        destination: Path,
    ) -> SourceSnapshot:
        del source
        del incoming_path

        return _source_snapshot(
            destination,
            acquisition_method=("operator_import"),
        )

    def fake_write_snapshot_manifest(
        snapshot: SourceSnapshot,
        destination: Path,
    ) -> Path:
        del snapshot

        return destination.with_name(f"{destination.name}.manifest.json")

    def fail_build_fatf_evidence(
        source_snapshot: SourceSnapshot,
        output_dir: Path,
    ) -> Never:
        del source_snapshot
        del output_dir

        raise FatfWorkflowError("simulated FATF workflow failure")

    monkeypatch.setattr(
        ("black_meridian.cli.import_operator_source"),
        fake_import_operator_source,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.write_snapshot_manifest"),
        fake_write_snapshot_manifest,
    )

    monkeypatch.setattr(
        ("black_meridian.cli.build_fatf_evidence"),
        fail_build_fatf_evidence,
    )

    result = runner.invoke(
        app,
        [
            "fatf",
            "import",
            str(artifact_path),
            "--source-dir",
            str(source_dir),
        ],
    )

    assert result.exit_code == 1

    assert ("FATF import failed: simulated FATF workflow failure") in result.output

    assert "FATF operator import completed." not in result.output


def test_fatf_import_rejects_missing_operator_artifact() -> None:
    result = runner.invoke(
        app,
        [
            "fatf",
            "import",
            "definitely-missing-fatf-artifact.html",
        ],
    )

    assert result.exit_code == 2

    assert "does not exist" in result.output.lower() or "invalid value" in result.output.lower()
