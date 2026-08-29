"""Adversarial regression tests for publisher-grounded OFAC aggregation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from black_meridian.ofac.aggregate import (
    OfacAggregationError,
    OfacEntityEvidence,
    build_ofac_entity_evidence,
)
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
)
from black_meridian.ofac.relations import (
    OfacAddressRecord,
    OfacAliasRecord,
)

_ACQUIRED_AT = datetime(
    2026,
    8,
    29,
    12,
    0,
    tzinfo=UTC,
)

_PRIMARY_SHA = "a" * 64
_ADDRESS_SHA = "b" * 64
_ALIAS_SHA = "c" * 64


def _primary(
    publisher_record_id: str,
    *,
    source_key: str = "ofac_sdn_csv",
    row_number: int = 1,
) -> OfacPrimaryRecord:
    return OfacPrimaryRecord.model_validate(
        {
            "source_key": source_key,
            "publisher_record_id": (publisher_record_id),
            "source_row_number": (row_number),
            "source_row_fingerprint": ("d" * 64),
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
            "remarks_raw": "-0- ",
            "acquisition_method": ("direct_http"),
            "acquired_at": (_ACQUIRED_AT),
            "source_sha256": (_PRIMARY_SHA),
        }
    )


def _address(
    parent_id: str,
    relation_id: str,
    *,
    source_key: str = ("ofac_sdn_addresses_csv"),
) -> OfacAddressRecord:
    return OfacAddressRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "publisher_relation_id": (relation_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("e" * 64),
            "address_raw": (f"ADDRESS {relation_id}"),
            "city_state_postal_raw": ("CITY"),
            "country_raw": ("COUNTRY"),
            "remarks_raw": "-0- ",
            "acquisition_method": ("direct_http"),
            "acquired_at": (_ACQUIRED_AT),
            "source_sha256": (_ADDRESS_SHA),
        }
    )


def _alias(
    parent_id: str,
    relation_id: str,
    *,
    source_key: str = ("ofac_sdn_aliases_csv"),
) -> OfacAliasRecord:
    return OfacAliasRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "publisher_relation_id": (relation_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("f" * 64),
            "alias_type_raw": "a.k.a.",
            "alias_name_raw": (f"ALIAS {relation_id}"),
            "remarks_raw": "-0- ",
            "acquisition_method": ("direct_http"),
            "acquired_at": (_ACQUIRED_AT),
            "source_sha256": (_ALIAS_SHA),
        }
    )


def test_builder_attaches_publisher_relations_to_primary() -> None:
    primary = _primary("17013")

    addresses = (
        _address(
            "17013",
            "41002",
        ),
        _address(
            "17013",
            "41001",
        ),
    )

    aliases = (
        _alias(
            "17013",
            "51002",
        ),
        _alias(
            "17013",
            "51001",
        ),
    )

    evidence = build_ofac_entity_evidence(
        (primary,),
        addresses,
        aliases,
    )

    assert len(evidence) == 1

    aggregate = evidence[0]

    assert aggregate.primary is primary

    assert aggregate.source_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert aggregate.address_count == 2
    assert aggregate.alias_count == 2

    assert [address.publisher_relation_id for address in aggregate.addresses] == [
        "41001",
        "41002",
    ]

    assert [alias.publisher_relation_id for alias in aggregate.aliases] == [
        "51001",
        "51002",
    ]


def test_builder_preserves_primary_without_relations() -> None:
    primary = _primary("17013")

    evidence = build_ofac_entity_evidence((primary,))

    assert len(evidence) == 1

    assert evidence[0].addresses == ()

    assert evidence[0].aliases == ()


def test_builder_rejects_orphan_address_relation() -> None:
    primary = _primary("17013")

    orphan = _address(
        "99999",
        "41001",
    )

    with pytest.raises(
        OfacAggregationError,
        match="missing primary parent",
    ):
        build_ofac_entity_evidence(
            (primary,),
            (orphan,),
        )


def test_builder_rejects_orphan_alias_relation() -> None:
    primary = _primary("17013")

    orphan = _alias(
        "99999",
        "51001",
    )

    with pytest.raises(
        OfacAggregationError,
        match="missing primary parent",
    ):
        build_ofac_entity_evidence(
            (primary,),
            alias_records=(orphan,),
        )


def test_same_bare_publisher_id_across_sources_remains_distinct() -> None:
    sdn_primary = _primary(
        "17013",
        source_key="ofac_sdn_csv",
    )

    consolidated_primary = _primary(
        "17013",
        source_key=("ofac_consolidated_csv"),
        row_number=2,
    )

    sdn_address = _address(
        "17013",
        "41001",
    )

    consolidated_address = _address(
        "17013",
        "42001",
        source_key=("ofac_consolidated_addresses_csv"),
    )

    evidence = build_ofac_entity_evidence(
        (
            consolidated_primary,
            sdn_primary,
        ),
        (
            consolidated_address,
            sdn_address,
        ),
    )

    assert len(evidence) == 2

    assert [item.source_record_key for item in evidence] == [
        (
            "ofac_sdn_csv",
            "17013",
        ),
        (
            "ofac_consolidated_csv",
            "17013",
        ),
    ]

    assert evidence[0].addresses[0].source_key == "ofac_sdn_addresses_csv"

    assert evidence[1].addresses[0].source_key == "ofac_consolidated_addresses_csv"


def test_builder_rejects_duplicate_primary_identity() -> None:
    first = _primary(
        "17013",
        row_number=1,
    )

    second = _primary(
        "17013",
        row_number=2,
    )

    with pytest.raises(
        OfacAggregationError,
        match="duplicate primary",
    ):
        build_ofac_entity_evidence(
            (
                first,
                second,
            )
        )


def test_builder_rejects_duplicate_address_identity() -> None:
    primary = _primary("17013")

    address = _address(
        "17013",
        "41001",
    )

    with pytest.raises(
        OfacAggregationError,
        match="duplicate address",
    ):
        build_ofac_entity_evidence(
            (primary,),
            (
                address,
                address,
            ),
        )


def test_builder_rejects_duplicate_alias_identity() -> None:
    primary = _primary("17013")

    alias = _alias(
        "17013",
        "51001",
    )

    with pytest.raises(
        OfacAggregationError,
        match="duplicate alias",
    ):
        build_ofac_entity_evidence(
            (primary,),
            alias_records=(
                alias,
                alias,
            ),
        )


def test_builder_is_deterministic_for_primary_input_order() -> None:
    first = _primary(
        "200",
        row_number=2,
    )

    second = _primary(
        "100",
        row_number=1,
    )

    evidence = build_ofac_entity_evidence(
        (
            first,
            second,
        )
    )

    assert [item.primary.publisher_record_id for item in evidence] == [
        "100",
        "200",
    ]


def test_entity_evidence_rejects_wrong_attached_parent() -> None:
    primary = _primary("17013")

    wrong_address = _address(
        "99999",
        "41001",
    )

    with pytest.raises(
        ValidationError,
        match="does not point",
    ):
        OfacEntityEvidence(
            primary=primary,
            addresses=(wrong_address,),
        )


def test_entity_evidence_forbids_extra_fields() -> None:
    primary = _primary("17013")

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        OfacEntityEvidence.model_validate(
            {
                "primary": primary,
                "addresses": (),
                "aliases": (),
                "analyst_guess": ("same real-world entity"),
            }
        )
