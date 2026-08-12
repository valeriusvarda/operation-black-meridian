"""End-to-end FATF evidence orchestration over trusted source snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final

from pydantic import HttpUrl

from black_meridian.data_sources import SourceSnapshot
from black_meridian.data_sources.contracts import FatfSnapshot
from black_meridian.fatf.exporter import (
    write_fatf_csv,
    write_fatf_json,
)
from black_meridian.fatf.normalizer import (
    FatfNormalizationError,
    normalize_fatf_publication,
)
from black_meridian.fatf.parser import (
    FatfParseError,
    parse_fatf_publication,
)

FATF_SOURCE_KEY: Final = "fatf_monitored_jurisdictions_html"

FATF_CSV_FILENAME: Final = "fatf_jurisdictions.csv"
FATF_JSON_FILENAME: Final = "fatf_snapshot.json"


class FatfWorkflowError(RuntimeError):
    """Raised when trusted FATF evidence cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class FatfEvidenceResult:
    """Paths and validated snapshot produced by one FATF evidence run."""

    source_path: Path
    csv_path: Path
    json_path: Path
    snapshot: FatfSnapshot


def build_fatf_evidence(
    source_snapshot: SourceSnapshot,
    output_dir: Path,
) -> FatfEvidenceResult:
    """Build validated FATF evidence from one trusted acquired source snapshot."""

    _require_fatf_source(source_snapshot)

    source_path = Path(source_snapshot.destination)

    source_bytes = _read_source_bytes(source_path)

    _verify_source_integrity(
        source_snapshot,
        source_bytes,
    )

    html = _decode_source_html(source_bytes)

    try:
        publication = parse_fatf_publication(html)

        records = normalize_fatf_publication(publication)
    except (
        FatfParseError,
        FatfNormalizationError,
    ) as exc:
        raise FatfWorkflowError(
            "Acquired FATF content could not be converted into validated jurisdiction intelligence."
        ) from exc

    evidence_snapshot = FatfSnapshot(
        source_url=HttpUrl(str(source_snapshot.resolved_url)),
        publication_date=publication.publication_date,
        retrieved_at=source_snapshot.fetched_at,
        content_sha256=source_snapshot.sha256,
        records=records,
    )

    csv_path = output_dir / FATF_CSV_FILENAME

    json_path = output_dir / FATF_JSON_FILENAME

    try:
        write_fatf_csv(
            evidence_snapshot,
            csv_path,
        )

        write_fatf_json(
            evidence_snapshot,
            json_path,
        )
    except OSError as exc:
        raise FatfWorkflowError("Validated FATF evidence could not be persisted.") from exc

    return FatfEvidenceResult(
        source_path=source_path,
        csv_path=csv_path,
        json_path=json_path,
        snapshot=evidence_snapshot,
    )


def _require_fatf_source(
    source_snapshot: SourceSnapshot,
) -> None:
    """Reject snapshots that did not originate from the approved FATF source."""

    if source_snapshot.source_key != FATF_SOURCE_KEY:
        raise FatfWorkflowError(
            "FATF evidence workflow received an unexpected "
            f"source key: {source_snapshot.source_key!r}."
        )


def _read_source_bytes(
    source_path: Path,
) -> bytes:
    """Read the exact acquired source artifact used for FATF analysis."""

    try:
        return source_path.read_bytes()
    except OSError as exc:
        raise FatfWorkflowError(
            f"Acquired FATF source artifact could not be read: {source_path}."
        ) from exc


def _verify_source_integrity(
    source_snapshot: SourceSnapshot,
    source_bytes: bytes,
) -> None:
    """Reconcile the current source artifact with acquisition provenance."""

    actual_byte_size = len(source_bytes)

    if actual_byte_size != source_snapshot.byte_size:
        raise FatfWorkflowError(
            "Acquired FATF source byte size no longer matches its provenance snapshot."
        )

    actual_sha256 = sha256(source_bytes).hexdigest()

    if actual_sha256 != source_snapshot.sha256:
        raise FatfWorkflowError(
            "Acquired FATF source SHA-256 no longer matches its provenance snapshot."
        )


def _decode_source_html(
    source_bytes: bytes,
) -> str:
    """Decode the acquired FATF HTML artifact as strict UTF-8."""

    try:
        return source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FatfWorkflowError("Acquired FATF source is not valid UTF-8 HTML.") from exc
