"""Regression tests for deterministic OFAC evidence-set contracts."""

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from black_meridian.data_sources.models import (
    AcquisitionMethod,
    SourceSnapshot,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
    OfacEvidenceSet,
)

_HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)

_FETCHED_AT = datetime(
    2026,
    8,
    28,
    12,
    0,
    tzinfo=UTC,
)


def _snapshot(
    source_key: str,
    *,
    sha256_value: str | None = None,
    byte_size: int = 1024,
    acquisition_method: AcquisitionMethod = "direct_http",
    destination: str | None = None,
) -> SourceSnapshot:
    source_url = _HTTP_URL_ADAPTER.validate_python(
        f"https://sanctionslistservice.ofac.treas.gov/evidence/{source_key}.csv"
    )

    resolved_sha256 = (
        sha256_value if sha256_value is not None else sha256(source_key.encode("utf-8")).hexdigest()
    )

    resolved_destination = (
        destination if destination is not None else f"data/raw/ofac/{source_key}.csv"
    )

    return SourceSnapshot(
        source_key=source_key,
        acquisition_method=acquisition_method,
        requested_url=source_url,
        resolved_url=source_url,
        fetched_at=_FETCHED_AT,
        sha256=resolved_sha256,
        byte_size=byte_size,
        content_type="text/csv",
        destination=resolved_destination,
    )


def _complete_snapshots() -> tuple[SourceSnapshot, ...]:
    return tuple(_snapshot(source_key) for source_key in OFAC_EVIDENCE_SOURCE_KEYS)


def test_ofac_evidence_set_accepts_complete_source_boundary() -> None:
    evidence_set = OfacEvidenceSet(snapshots=_complete_snapshots())

    assert evidence_set.source_count == 8

    assert (
        tuple(snapshot.source_key for snapshot in evidence_set.ordered_snapshots)
        == OFAC_EVIDENCE_SOURCE_KEYS
    )

    assert len(evidence_set.evidence_set_sha256) == 64


def test_evidence_set_fingerprint_is_input_order_independent() -> None:
    snapshots = _complete_snapshots()

    forward = OfacEvidenceSet(snapshots=snapshots)

    reverse = OfacEvidenceSet(snapshots=tuple(reversed(snapshots)))

    assert forward.evidence_set_sha256 == reverse.evidence_set_sha256


def test_evidence_set_fingerprint_changes_when_source_digest_changes() -> None:
    baseline = OfacEvidenceSet(snapshots=_complete_snapshots())

    changed_snapshots = tuple(
        _snapshot(
            source_key,
            sha256_value=("f" * 64 if source_key == "ofac_sdn_csv" else None),
        )
        for source_key in OFAC_EVIDENCE_SOURCE_KEYS
    )

    changed = OfacEvidenceSet(snapshots=changed_snapshots)

    assert baseline.evidence_set_sha256 != changed.evidence_set_sha256


def test_evidence_set_fingerprint_changes_when_source_size_changes() -> None:
    baseline = OfacEvidenceSet(snapshots=_complete_snapshots())

    changed_snapshots = tuple(
        _snapshot(
            source_key,
            byte_size=(2048 if source_key == "ofac_sdn_csv" else 1024),
        )
        for source_key in OFAC_EVIDENCE_SOURCE_KEYS
    )

    changed = OfacEvidenceSet(snapshots=changed_snapshots)

    assert baseline.evidence_set_sha256 != changed.evidence_set_sha256


def test_ofac_evidence_set_rejects_missing_source() -> None:
    snapshots = _complete_snapshots()

    with pytest.raises(
        ValidationError,
        match="missing",
    ):
        OfacEvidenceSet(snapshots=snapshots[:-1])


def test_ofac_evidence_set_rejects_duplicate_source_key() -> None:
    snapshots = _complete_snapshots()

    duplicate_snapshots = snapshots[:-1] + (snapshots[0],)

    with pytest.raises(
        ValidationError,
        match="duplicate source_key",
    ):
        OfacEvidenceSet(snapshots=duplicate_snapshots)


def test_ofac_evidence_set_rejects_unapproved_source() -> None:
    snapshots = _complete_snapshots()

    unexpected = _snapshot("ofac_unapproved_csv")

    mutated_snapshots = snapshots[:-1] + (unexpected,)

    with pytest.raises(
        ValidationError,
        match="unexpected",
    ):
        OfacEvidenceSet(snapshots=mutated_snapshots)


def test_ofac_evidence_set_rejects_duplicate_destination() -> None:
    snapshots = list(_complete_snapshots())

    snapshots[-1] = _snapshot(
        snapshots[-1].source_key,
        destination=snapshots[0].destination,
    )

    with pytest.raises(
        ValidationError,
        match="distinct destination",
    ):
        OfacEvidenceSet(snapshots=tuple(snapshots))


def test_ofac_evidence_set_preserves_snapshot_acquisition_provenance() -> None:
    snapshots = tuple(
        _snapshot(
            source_key,
            acquisition_method=(
                "operator_import" if source_key == "ofac_sdn_comments_csv" else "direct_http"
            ),
        )
        for source_key in OFAC_EVIDENCE_SOURCE_KEYS
    )

    evidence_set = OfacEvidenceSet(snapshots=snapshots)

    snapshot_by_key = {snapshot.source_key: snapshot for snapshot in evidence_set.snapshots}

    assert snapshot_by_key["ofac_sdn_comments_csv"].acquisition_method == "operator_import"


def test_ofac_evidence_set_forbids_extra_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        OfacEvidenceSet.model_validate(
            {
                "snapshots": _complete_snapshots(),
                "analyst_conclusion": "high risk",
            }
        )


def test_ofac_evidence_set_is_immutable() -> None:
    evidence_set = OfacEvidenceSet(snapshots=_complete_snapshots())

    with pytest.raises(
        ValidationError,
        match="frozen",
    ):
        evidence_set.snapshots = ()
