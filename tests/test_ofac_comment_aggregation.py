"""Regression tests for OFAC remarks spillover aggregation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from black_meridian.ofac.aggregate import (
    OfacAggregationError,
    OfacEntityEvidence,
    build_ofac_entity_evidence,
)
from black_meridian.ofac.comments import (
    OfacCommentRecord,
)
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
)

_ACQUIRED_AT = datetime(
    2026,
    8,
    30,
    12,
    0,
    tzinfo=UTC,
)


def _primary(
    publisher_record_id: str = "17013",
    *,
    source_key: str = "ofac_sdn_csv",
) -> OfacPrimaryRecord:
    return OfacPrimaryRecord.model_validate(
        {
            "source_key": source_key,
            "publisher_record_id": (publisher_record_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("a" * 64),
            "primary_name_raw": ("TEST PRIMARY"),
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
            "acquired_at": (_ACQUIRED_AT),
            "source_sha256": ("b" * 64),
        }
    )


def _comment(
    parent_id: str = "17013",
    *,
    source_key: str = ("ofac_sdn_comments_csv"),
    continuation: str = ("r 1027700342890 (Russia)."),
) -> OfacCommentRecord:
    return OfacCommentRecord.model_validate(
        {
            "source_key": source_key,
            "parent_publisher_record_id": (parent_id),
            "source_row_number": 1,
            "source_row_fingerprint": ("c" * 64),
            "continuation_raw": (continuation),
            "acquisition_method": ("direct_http"),
            "acquired_at": (_ACQUIRED_AT),
            "source_sha256": ("d" * 64),
        }
    )


def test_builder_attaches_one_to_one_comments_spillover() -> None:
    primary = _primary()

    comment = _comment()

    evidence = build_ofac_entity_evidence(
        (primary,),
        comment_records=(comment,),
    )

    aggregate = evidence[0]

    assert aggregate.comment is comment

    assert aggregate.has_remarks_spillover is True

    assert aggregate.reconstructed_remarks_raw == ("Registration Number 1027700342890 (Russia).")


def test_primary_without_spillover_preserves_original_remarks() -> None:
    primary = _primary()

    aggregate = build_ofac_entity_evidence((primary,))[0]

    assert aggregate.has_remarks_spillover is False

    assert aggregate.reconstructed_remarks_raw == primary.remarks_raw


def test_builder_rejects_orphan_comments_spillover() -> None:
    primary = _primary()

    orphan = _comment(parent_id="99999")

    with pytest.raises(
        OfacAggregationError,
        match="missing primary parent",
    ):
        build_ofac_entity_evidence(
            (primary,),
            comment_records=(orphan,),
        )


def test_same_bare_id_across_source_families_remains_distinct() -> None:
    sdn_primary = _primary(source_key="ofac_sdn_csv")

    consolidated_primary = _primary(source_key=("ofac_consolidated_csv"))

    sdn_comment = _comment(
        source_key=("ofac_sdn_comments_csv"),
        continuation=("r SDN continuation."),
    )

    consolidated_comment = _comment(
        source_key=("ofac_consolidated_comments_csv"),
        continuation=("r Consolidated continuation."),
    )

    evidence = build_ofac_entity_evidence(
        (
            consolidated_primary,
            sdn_primary,
        ),
        comment_records=(
            consolidated_comment,
            sdn_comment,
        ),
    )

    assert evidence[0].source_record_key == (
        "ofac_sdn_csv",
        "17013",
    )

    assert evidence[0].comment is sdn_comment

    assert evidence[1].source_record_key == (
        "ofac_consolidated_csv",
        "17013",
    )

    assert evidence[1].comment is consolidated_comment


def test_builder_rejects_duplicate_comment_identity() -> None:
    primary = _primary()

    comment = _comment()

    with pytest.raises(
        OfacAggregationError,
        match="duplicate comments",
    ):
        build_ofac_entity_evidence(
            (primary,),
            comment_records=(
                comment,
                comment,
            ),
        )


def test_entity_evidence_rejects_wrong_comment_parent() -> None:
    primary = _primary()

    wrong_comment = _comment(parent_id="99999")

    with pytest.raises(
        ValidationError,
        match="does not point",
    ):
        OfacEntityEvidence(
            primary=primary,
            comment=wrong_comment,
        )
