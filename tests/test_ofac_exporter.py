"""Regression tests for deterministic OFAC evidence serialization."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO

import pytest

from black_meridian.data_sources.models import (
    SourceSnapshot,
)
from black_meridian.data_sources.registry import (
    get_source,
)
from black_meridian.ofac.aggregate import (
    OfacEntityEvidence,
)
from black_meridian.ofac.comments import (
    OfacCommentRecord,
)
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
    OfacEvidenceSet,
)
from black_meridian.ofac.exporter import (
    OfacExportError,
    serialize_ofac_csv,
    serialize_ofac_json,
    write_ofac_csv,
    write_ofac_json,
)
from black_meridian.ofac.relations import (
    OfacAddressRecord,
    OfacAliasRecord,
)

_FETCHED_AT = datetime(
    2026,
    8,
    31,
    12,
    0,
    tzinfo=UTC,
)


def _digest(
    source_key: str,
) -> str:
    return sha256(source_key.encode("utf-8")).hexdigest()


def _snapshot(
    source_key: str,
) -> SourceSnapshot:
    source = get_source(source_key)

    return SourceSnapshot(
        source_key=source.key,
        acquisition_method="direct_http",
        requested_url=source.url,
        resolved_url=source.url,
        fetched_at=_FETCHED_AT,
        sha256=_digest(source_key),
        byte_size=1000,
        content_type="text/csv",
        destination=(f"data/raw/external/{source.key}/{source.filename}"),
    )


def _evidence_set() -> OfacEvidenceSet:
    return OfacEvidenceSet(
        snapshots=tuple(_snapshot(source_key) for source_key in OFAC_EVIDENCE_SOURCE_KEYS)
    )


def _primary(
    publisher_record_id: str,
    *,
    source_key: str = "ofac_sdn_csv",
) -> OfacPrimaryRecord:
    return OfacPrimaryRecord.model_validate(
        {
            "source_key": source_key,
            "publisher_record_id": (publisher_record_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("a" * 64),
            "primary_name_raw": (f"PRIMARY {publisher_record_id}"),
            "source_entity_type_raw": ("-0- "),
            "program_text_raw": ("TEST-PROGRAM"),
            "title_raw": "-0- ",
            "call_sign_raw": "-0- ",
            "vessel_type_raw": "-0- ",
            "tonnage_raw": "-0- ",
            "grt_raw": "-0- ",
            "vessel_flag_raw": "-0- ",
            "vessel_owner_raw": "-0- ",
            "remarks_raw": ("Registration Numbe"),
            "acquisition_method": ("direct_http"),
            "acquired_at": (_FETCHED_AT),
            "source_sha256": (_digest(source_key)),
        }
    )


def _address(
    parent_id: str,
) -> OfacAddressRecord:
    source_key = "ofac_sdn_addresses_csv"

    return OfacAddressRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "publisher_relation_id": ("41001"),
            "source_row_number": 1,
            "source_row_fingerprint": ("b" * 64),
            "address_raw": ("123 Publisher Street"),
            "city_state_postal_raw": ("Moscow"),
            "country_raw": ("Russia"),
            "remarks_raw": "-0- ",
            "acquisition_method": ("direct_http"),
            "acquired_at": (_FETCHED_AT),
            "source_sha256": (_digest(source_key)),
        }
    )


def _alias(
    parent_id: str,
) -> OfacAliasRecord:
    source_key = "ofac_sdn_aliases_csv"

    return OfacAliasRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "publisher_relation_id": ("51001"),
            "source_row_number": 1,
            "source_row_fingerprint": ("c" * 64),
            "alias_type_raw": ("a.k.a."),
            "alias_name_raw": ("PUBLISHER ALIAS"),
            "remarks_raw": "-0- ",
            "acquisition_method": ("direct_http"),
            "acquired_at": (_FETCHED_AT),
            "source_sha256": (_digest(source_key)),
        }
    )


def _comment(
    parent_id: str,
) -> OfacCommentRecord:
    source_key = "ofac_sdn_comments_csv"

    return OfacCommentRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("d" * 64),
            "continuation_raw": ("r 1027700342890."),
            "acquisition_method": ("direct_http"),
            "acquired_at": (_FETCHED_AT),
            "source_sha256": (_digest(source_key)),
        }
    )


def _entity(
    publisher_record_id: str,
) -> OfacEntityEvidence:
    return OfacEntityEvidence(
        primary=_primary(publisher_record_id),
        addresses=(_address(publisher_record_id),),
        aliases=(_alias(publisher_record_id),),
        comment=_comment(publisher_record_id),
    )


def test_json_serialization_is_deterministic() -> None:
    evidence_set = _evidence_set()

    first = (
        _entity("200"),
        _entity("100"),
    )

    second = tuple(reversed(first))

    assert serialize_ofac_json(
        evidence_set,
        first,
    ) == serialize_ofac_json(
        evidence_set,
        second,
    )


def test_csv_serialization_is_deterministic() -> None:
    evidence_set = _evidence_set()

    first = (
        _entity("200"),
        _entity("100"),
    )

    second = tuple(reversed(first))

    assert serialize_ofac_csv(
        evidence_set,
        first,
    ) == serialize_ofac_csv(
        evidence_set,
        second,
    )


def test_json_contains_portable_provenance_and_lineage() -> None:
    payload = json.loads(
        serialize_ofac_json(
            _evidence_set(),
            (_entity("17013"),),
        )
    )

    assert payload["schema_version"] == 1

    assert payload["source_count"] == 8

    assert payload["entity_count"] == 1

    assert len(payload["evidence_set_sha256"]) == 64

    assert "destination" not in payload["sources"][0]

    entity = payload["entities"][0]

    assert entity["source_record_key"] == [
        "ofac_sdn_csv",
        "17013",
    ]

    assert entity["reconstructed_remarks_raw"] == ("Registration Number 1027700342890.")

    assert len(entity["addresses"]) == 1

    assert len(entity["aliases"]) == 1

    assert entity["comment"] is not None


def test_csv_emits_one_row_per_primary_evidence_occurrence() -> None:
    content = serialize_ofac_csv(
        _evidence_set(),
        (
            _entity("200"),
            _entity("100"),
        ),
    ).decode("utf-8")

    rows = list(csv.DictReader(StringIO(content)))

    assert len(rows) == 2

    assert [row["publisher_record_id"] for row in rows] == [
        "100",
        "200",
    ]

    assert rows[0]["source_key"] == "ofac_sdn_csv"

    assert rows[0]["has_remarks_spillover"] == "true"

    assert len(rows[0]["evidence_set_sha256"]) == 64


def test_export_rejects_primary_digest_outside_evidence_set() -> None:
    primary = _primary("17013")

    mutated = primary.model_copy(update={"source_sha256": ("f" * 64)})

    entity = OfacEntityEvidence(primary=mutated)

    with pytest.raises(
        OfacExportError,
        match="SHA-256",
    ):
        serialize_ofac_json(
            _evidence_set(),
            (entity,),
        )


def test_export_rejects_relation_digest_outside_evidence_set() -> None:
    primary = _primary("17013")

    address = _address("17013").model_copy(update={"source_sha256": ("f" * 64)})

    entity = OfacEntityEvidence(
        primary=primary,
        addresses=(address,),
    )

    with pytest.raises(
        OfacExportError,
        match="SHA-256",
    ):
        serialize_ofac_csv(
            _evidence_set(),
            (entity,),
        )


def test_export_rejects_duplicate_entity_identity() -> None:
    entity = _entity("17013")

    with pytest.raises(
        OfacExportError,
        match="duplicate entity",
    ):
        serialize_ofac_json(
            _evidence_set(),
            (
                entity,
                entity,
            ),
        )


def test_export_rejects_empty_entity_set() -> None:
    with pytest.raises(
        OfacExportError,
        match="at least one",
    ):
        serialize_ofac_json(
            _evidence_set(),
            (),
        )


def test_atomic_writers_persist_exact_serialized_bytes(
    tmp_path,
) -> None:
    evidence_set = _evidence_set()

    entities = (_entity("17013"),)

    json_path = tmp_path / "ofac_entities.json"

    csv_path = tmp_path / "ofac_entities.csv"

    write_ofac_json(
        evidence_set,
        entities,
        json_path,
    )

    write_ofac_csv(
        evidence_set,
        entities,
        csv_path,
    )

    assert json_path.read_bytes() == serialize_ofac_json(
        evidence_set,
        entities,
    )

    assert csv_path.read_bytes() == serialize_ofac_csv(
        evidence_set,
        entities,
    )

    assert not (tmp_path / ".ofac_entities.json.partial").exists()

    assert not (tmp_path / ".ofac_entities.csv.partial").exists()
