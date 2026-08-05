"""Deterministic serialization for validated FATF evidence snapshots."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Final

from black_meridian.data_sources.contracts import FatfSnapshot

_CSV_COLUMNS: Final[tuple[str, ...]] = (
    "jurisdiction_name",
    "iso_alpha3",
    "tier",
    "publication_date",
    "source_name",
    "source_url",
    "retrieved_at",
    "content_sha256",
)


def serialize_fatf_csv(snapshot: FatfSnapshot) -> bytes:
    """Serialize one validated FATF snapshot as deterministic UTF-8 CSV bytes."""

    output = StringIO(newline="")
    writer = csv.writer(
        output,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(_CSV_COLUMNS)

    publication_date = snapshot.publication_date.isoformat()
    retrieved_at = snapshot.retrieved_at.isoformat()
    source_url = str(snapshot.source_url)

    for record in snapshot.records:
        writer.writerow(
            (
                record.jurisdiction_name,
                record.iso_alpha3,
                record.tier.value,
                publication_date,
                snapshot.source_name,
                source_url,
                retrieved_at,
                snapshot.content_sha256,
            )
        )

    return output.getvalue().encode("utf-8")


def serialize_fatf_json(snapshot: FatfSnapshot) -> bytes:
    """Serialize one validated FATF snapshot as deterministic UTF-8 JSON bytes."""

    payload = snapshot.model_dump(mode="json")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    return f"{serialized}\n".encode()
