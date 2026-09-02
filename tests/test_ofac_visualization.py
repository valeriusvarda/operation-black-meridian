"""Regression tests for deterministic OFAC evidence visualization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from typer.testing import CliRunner

from black_meridian.cli import app
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
    fingerprint_ofac_source_set,
)
from black_meridian.ofac.visualization import (
    OFAC_PROGRAM_SVG_FILENAME,
    OFAC_PROVENANCE_SVG_FILENAME,
    OFAC_SUBJECT_SVG_FILENAME,
    OFAC_VISUAL_MANIFEST_FILENAME,
    OfacVisualizationError,
    build_ofac_visualizations,
)

runner = CliRunner()

_ACQUIRED_AT = datetime(
    2026,
    9,
    2,
    12,
    0,
    tzinfo=UTC,
)


def _source_sha256(
    source_key: str,
) -> str:
    return sha256(source_key.encode("utf-8")).hexdigest()


def _portable_sources() -> list[dict[str, object]]:
    return [
        {
            "source_key": source_key,
            "acquisition_method": ("direct_http"),
            "requested_url": (f"https://example.com/{source_key}"),
            "fetched_at": (_ACQUIRED_AT.isoformat()),
            "sha256": (_source_sha256(source_key)),
            "byte_size": (1000 + index),
            "content_type": ("text/csv"),
        }
        for (
            index,
            source_key,
        ) in enumerate(OFAC_EVIDENCE_SOURCE_KEYS)
    ]


def _primary_payload(
    *,
    source_key: str,
    publisher_record_id: str,
    source_entity_type_raw: str,
    subject_kind: str,
    program_text_raw: str,
) -> dict[
    str,
    object,
]:
    return {
        "source_key": source_key,
        "publisher_record_id": (publisher_record_id),
        "source_row_number": 1,
        "source_row_fingerprint": (sha256(publisher_record_id.encode("utf-8")).hexdigest()),
        "primary_name_raw": (f"ENTITY {publisher_record_id}"),
        "source_entity_type_raw": (source_entity_type_raw),
        "program_text_raw": (program_text_raw),
        "title_raw": "-0- ",
        "call_sign_raw": "-0- ",
        "vessel_type_raw": "-0- ",
        "tonnage_raw": "-0- ",
        "grt_raw": "-0- ",
        "vessel_flag_raw": "-0- ",
        "vessel_owner_raw": "-0- ",
        "remarks_raw": "-0- ",
        "acquisition_method": ("direct_http"),
        "acquired_at": (_ACQUIRED_AT.isoformat()),
        "source_sha256": (_source_sha256(source_key)),
        "subject_kind": (subject_kind),
    }


def _entity_payload(
    *,
    source_key: str,
    publisher_record_id: str,
    source_entity_type_raw: str,
    subject_kind: str,
    program_text_raw: str,
) -> dict[
    str,
    object,
]:
    return {
        "source_record_key": [
            source_key,
            publisher_record_id,
        ],
        "primary": _primary_payload(
            source_key=source_key,
            publisher_record_id=(publisher_record_id),
            source_entity_type_raw=(source_entity_type_raw),
            subject_kind=(subject_kind),
            program_text_raw=(program_text_raw),
        ),
        "addresses": [],
        "aliases": [],
        "comment": None,
        "reconstructed_remarks_raw": ("-0- "),
    }


def _evidence_payload() -> dict[
    str,
    object,
]:
    sources = _portable_sources()

    evidence_set_sha256 = fingerprint_ofac_source_set(
        (
            (
                str(source["source_key"]),
                str(source["sha256"]),
                int(source["byte_size"]),
            )
            for source in sources
        )
    )

    entities = [
        _entity_payload(
            source_key="ofac_sdn_csv",
            publisher_record_id="100",
            source_entity_type_raw=("individual"),
            subject_kind="individual",
            program_text_raw="PROGRAM-A",
        ),
        _entity_payload(
            source_key="ofac_sdn_csv",
            publisher_record_id="101",
            source_entity_type_raw=("vessel"),
            subject_kind="vessel",
            program_text_raw="PROGRAM-A",
        ),
        _entity_payload(
            source_key="ofac_sdn_csv",
            publisher_record_id="102",
            source_entity_type_raw=("aircraft"),
            subject_kind="aircraft",
            program_text_raw="PROGRAM-B",
        ),
        _entity_payload(
            source_key=("ofac_consolidated_csv"),
            publisher_record_id="200",
            source_entity_type_raw="-0- ",
            subject_kind="unspecified",
            program_text_raw=("PROGRAM-C [PROGRAM-D]"),
        ),
    ]

    return {
        "schema_version": 1,
        "evidence_set_sha256": (evidence_set_sha256),
        "source_count": 8,
        "entity_count": len(entities),
        "sources": sources,
        "entities": entities,
    }


def _write_evidence(
    path: Path,
    *,
    mutate_hash: bool = False,
) -> None:
    payload = _evidence_payload()

    if mutate_hash:
        payload["evidence_set_sha256"] = "f" * 64

    path.write_text(
        (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        encoding="utf-8",
    )


def test_visualization_outputs_are_deterministic(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "ofac_entities.json"

    _write_evidence(evidence_path)

    first_dir = tmp_path / "first"

    second_dir = tmp_path / "second"

    first = build_ofac_visualizations(
        evidence_path,
        first_dir,
    )

    second = build_ofac_visualizations(
        evidence_path,
        second_dir,
    )

    assert first.provenance_svg_path.read_bytes() == second.provenance_svg_path.read_bytes()

    assert first.subject_svg_path.read_bytes() == second.subject_svg_path.read_bytes()

    assert first.program_svg_path.read_bytes() == second.program_svg_path.read_bytes()

    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()


def test_visual_manifest_binds_outputs_to_exact_evidence(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "ofac_entities.json"

    _write_evidence(evidence_path)

    result = build_ofac_visualizations(
        evidence_path,
        tmp_path / "visuals",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["evidence_json_sha256"] == sha256(evidence_path.read_bytes()).hexdigest()

    assert manifest["evidence_set_sha256"] == result.evidence_set_sha256

    assert manifest["metrics"]["subject_counts"] == {
        "aircraft": 1,
        "individual": 1,
        "unspecified": 1,
        "vessel": 1,
    }

    raw_program_counts = {
        item["program_text_raw"]: item["count"]
        for item in manifest["metrics"]["raw_program_context_counts"]
    }

    assert raw_program_counts["PROGRAM-A"] == 2

    assert raw_program_counts["PROGRAM-C [PROGRAM-D]"] == 1

    outputs = {item["filename"]: item for item in manifest["outputs"]}

    for filename in (
        OFAC_PROVENANCE_SVG_FILENAME,
        OFAC_SUBJECT_SVG_FILENAME,
        OFAC_PROGRAM_SVG_FILENAME,
    ):
        artifact = result.manifest_path.parent / filename

        assert outputs[filename]["sha256"] == sha256(artifact.read_bytes()).hexdigest()


def test_visualization_rejects_tampered_evidence_set_hash(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "ofac_entities.json"

    _write_evidence(
        evidence_path,
        mutate_hash=True,
    )

    with pytest.raises(
        OfacVisualizationError,
        match="SHA-256",
    ):
        build_ofac_visualizations(
            evidence_path,
            tmp_path / "visuals",
        )


def test_ofac_visualize_cli_generates_bound_artifacts(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "ofac_entities.json"

    output_dir = tmp_path / "visuals"

    _write_evidence(evidence_path)

    result = runner.invoke(
        app,
        [
            "ofac",
            "visualize",
            "--evidence",
            str(evidence_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output

    assert "OFAC visualization completed." in result.output

    assert "Entities: 4" in result.output

    assert "Evidence JSON SHA-256:" in result.output

    assert "Evidence set SHA-256:" in result.output

    assert (output_dir / OFAC_PROVENANCE_SVG_FILENAME).exists()

    assert (output_dir / OFAC_SUBJECT_SVG_FILENAME).exists()

    assert (output_dir / OFAC_PROGRAM_SVG_FILENAME).exists()

    assert (output_dir / OFAC_VISUAL_MANIFEST_FILENAME).exists()
