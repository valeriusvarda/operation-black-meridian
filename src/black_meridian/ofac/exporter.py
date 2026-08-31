"""Deterministic serialization of provenance-bound OFAC entity evidence."""

from __future__ import annotations

import csv
import json
import os
from io import StringIO
from pathlib import Path
from typing import Any, Final

from black_meridian.ofac.aggregate import (
    OfacEntityEvidence,
)
from black_meridian.ofac.evidence import (
    OfacEvidenceSet,
)

_CSV_COLUMNS: Final[tuple[str, ...]] = (
    "source_key",
    "publisher_record_id",
    "primary_name_raw",
    "source_entity_type_raw",
    "subject_kind",
    "program_text_raw",
    "title_raw",
    "remarks_raw",
    "reconstructed_remarks_raw",
    "address_count",
    "alias_count",
    "has_remarks_spillover",
    "primary_source_sha256",
    "primary_source_row_fingerprint",
    "evidence_set_sha256",
    "addresses_json",
    "aliases_json",
    "comment_json",
)

_PRIMARY_SOURCE_ORDER: Final[dict[str, int]] = {
    "ofac_sdn_csv": 0,
    "ofac_consolidated_csv": 1,
}

_SCHEMA_VERSION: Final[int] = 1


class OfacExportError(ValueError):
    """Raised when OFAC evidence cannot be exported safely."""


def serialize_ofac_json(
    evidence_set: OfacEvidenceSet,
    entities: tuple[
        OfacEntityEvidence,
        ...,
    ],
) -> bytes:
    """Serialize validated OFAC evidence as deterministic UTF-8 JSON."""

    ordered_entities = _validate_and_order_entities(
        evidence_set,
        entities,
    )

    payload: dict[
        str,
        Any,
    ] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_set_sha256": (evidence_set.evidence_set_sha256),
        "source_count": (evidence_set.source_count),
        "entity_count": len(ordered_entities),
        "sources": [
            _portable_source_payload(snapshot) for snapshot in evidence_set.ordered_snapshots
        ],
        "entities": [_entity_payload(entity) for entity in ordered_entities],
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    return f"{serialized}\n".encode("utf-8")


def serialize_ofac_csv(
    evidence_set: OfacEvidenceSet,
    entities: tuple[
        OfacEntityEvidence,
        ...,
    ],
) -> bytes:
    """Serialize one deterministic CSV row per OFAC primary evidence occurrence."""

    ordered_entities = _validate_and_order_entities(
        evidence_set,
        entities,
    )

    output = StringIO(newline="")

    writer = csv.writer(
        output,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )

    writer.writerow(_CSV_COLUMNS)

    evidence_set_sha256 = evidence_set.evidence_set_sha256

    for entity in ordered_entities:
        primary = entity.primary

        writer.writerow(
            (
                primary.source_key,
                primary.publisher_record_id,
                primary.primary_name_raw,
                primary.source_entity_type_raw,
                primary.subject_kind.value,
                primary.program_text_raw,
                primary.title_raw,
                primary.remarks_raw,
                entity.reconstructed_remarks_raw,
                entity.address_count,
                entity.alias_count,
                str(entity.has_remarks_spillover).lower(),
                primary.source_sha256,
                primary.source_row_fingerprint,
                evidence_set_sha256,
                _compact_json([address.model_dump(mode="json") for address in entity.addresses]),
                _compact_json([alias.model_dump(mode="json") for alias in entity.aliases]),
                _compact_json(
                    (entity.comment.model_dump(mode="json") if entity.comment is not None else None)
                ),
            )
        )

    return output.getvalue().encode("utf-8")


def write_ofac_json(
    evidence_set: OfacEvidenceSet,
    entities: tuple[
        OfacEntityEvidence,
        ...,
    ],
    destination: Path,
) -> Path:
    """Write deterministic OFAC JSON evidence atomically."""

    return _write_bytes_atomically(
        destination,
        serialize_ofac_json(
            evidence_set,
            entities,
        ),
    )


def write_ofac_csv(
    evidence_set: OfacEvidenceSet,
    entities: tuple[
        OfacEntityEvidence,
        ...,
    ],
    destination: Path,
) -> Path:
    """Write deterministic OFAC CSV evidence atomically."""

    return _write_bytes_atomically(
        destination,
        serialize_ofac_csv(
            evidence_set,
            entities,
        ),
    )


def _validate_and_order_entities(
    evidence_set: OfacEvidenceSet,
    entities: tuple[
        OfacEntityEvidence,
        ...,
    ],
) -> tuple[
    OfacEntityEvidence,
    ...,
]:
    """Reconcile entity provenance against the complete source evidence set."""

    if not entities:
        raise OfacExportError("OFAC export requires at least one entity evidence occurrence.")

    snapshots_by_key = {snapshot.source_key: snapshot for snapshot in evidence_set.snapshots}

    seen_entity_keys: set[tuple[str, str]] = set()

    for entity in entities:
        entity_key = entity.source_record_key

        if entity_key in seen_entity_keys:
            raise OfacExportError(
                f"OFAC export contains duplicate entity source-record identity: {entity_key!r}."
            )

        seen_entity_keys.add(entity_key)

        _require_matching_source_digest(
            snapshots_by_key,
            source_key=(entity.primary.source_key),
            source_sha256=(entity.primary.source_sha256),
        )

        for address in entity.addresses:
            _require_matching_source_digest(
                snapshots_by_key,
                source_key=(address.source_key),
                source_sha256=(address.source_sha256),
            )

        for alias in entity.aliases:
            _require_matching_source_digest(
                snapshots_by_key,
                source_key=(alias.source_key),
                source_sha256=(alias.source_sha256),
            )

        if entity.comment is not None:
            _require_matching_source_digest(
                snapshots_by_key,
                source_key=(entity.comment.source_key),
                source_sha256=(entity.comment.source_sha256),
            )

    return tuple(
        sorted(
            entities,
            key=lambda entity: (
                _PRIMARY_SOURCE_ORDER[entity.primary.source_key],
                int(entity.primary.publisher_record_id),
            ),
        )
    )


def _require_matching_source_digest(
    snapshots_by_key: dict[
        str,
        Any,
    ],
    *,
    source_key: str,
    source_sha256: str,
) -> None:
    """Require entity evidence to reference bytes in the supplied evidence set."""

    snapshot = snapshots_by_key.get(source_key)

    if snapshot is None:
        raise OfacExportError(
            "OFAC entity evidence references "
            "a source absent from the evidence set: "
            f"{source_key!r}."
        )

    if snapshot.sha256 != source_sha256:
        raise OfacExportError(
            "OFAC entity evidence source SHA-256 "
            "does not match the supplied evidence set "
            f"for {source_key!r}."
        )


def _portable_source_payload(
    snapshot: Any,
) -> dict[
    str,
    Any,
]:
    """Return portable provenance without embedding local filesystem paths."""

    return {
        "source_key": (snapshot.source_key),
        "acquisition_method": (snapshot.acquisition_method),
        "requested_url": str(snapshot.requested_url),
        "fetched_at": (snapshot.fetched_at.isoformat()),
        "sha256": snapshot.sha256,
        "byte_size": (snapshot.byte_size),
        "content_type": (snapshot.content_type),
    }


def _entity_payload(
    entity: OfacEntityEvidence,
) -> dict[
    str,
    Any,
]:
    """Return complete source-scoped entity evidence for JSON output."""

    return {
        "source_record_key": [
            entity.primary.source_key,
            entity.primary.publisher_record_id,
        ],
        "primary": {
            **entity.primary.model_dump(mode="json"),
            "subject_kind": (entity.primary.subject_kind.value),
        },
        "addresses": [address.model_dump(mode="json") for address in entity.addresses],
        "aliases": [alias.model_dump(mode="json") for alias in entity.aliases],
        "comment": (entity.comment.model_dump(mode="json") if entity.comment is not None else None),
        "reconstructed_remarks_raw": (entity.reconstructed_remarks_raw),
    }


def _compact_json(
    value: Any,
) -> str:
    """Serialize embedded CSV structures deterministically."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


def _write_bytes_atomically(
    destination: Path,
    payload: bytes,
) -> Path:
    """Persist evidence through sibling partial-file replacement."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = destination.with_name(f".{destination.name}.partial")

    try:
        with partial_path.open("wb") as output:
            output.write(payload)

            output.flush()

            os.fsync(output.fileno())

        os.replace(
            partial_path,
            destination,
        )

    except Exception:
        partial_path.unlink(missing_ok=True)

        raise

    return destination
