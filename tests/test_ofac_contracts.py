"""Regression tests for typed OFAC primary-record contracts."""

# cspell:words SDGT

from datetime import UTC, datetime
from typing import Any

import pytest
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
    OfacSubjectKind,
)
from pydantic import ValidationError

_ACQUIRED_AT = datetime(
    2026,
    8,
    27,
    12,
    0,
    tzinfo=UTC,
)

_SOURCE_SHA256 = "a" * 64
_ROW_FINGERPRINT = "b" * 64


def _record_payload(
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_key": "ofac_sdn_csv",
        "publisher_record_id": "17013",
        "source_row_number": 1,
        "source_row_fingerprint": _ROW_FINGERPRINT,
        "primary_name_raw": ("VTB BANK PUBLIC JOINT STOCK COMPANY"),
        "source_entity_type_raw": "-0- ",
        "program_text_raw": ("UKRAINE-EO13662] [RUSSIA-EO14024"),
        "title_raw": "-0- ",
        "call_sign_raw": "-0- ",
        "vessel_type_raw": "-0- ",
        "tonnage_raw": "-0- ",
        "grt_raw": "-0- ",
        "vessel_flag_raw": "-0- ",
        "vessel_owner_raw": "-0- ",
        "remarks_raw": "-0- ",
        "acquisition_method": "direct_http",
        "acquired_at": _ACQUIRED_AT,
        "source_sha256": _SOURCE_SHA256,
    }

    payload.update(overrides)

    return payload


@pytest.mark.parametrize(
    ("raw_value", "expected_kind"),
    [
        (
            "individual",
            OfacSubjectKind.INDIVIDUAL,
        ),
        (
            "vessel",
            OfacSubjectKind.VESSEL,
        ),
        (
            "aircraft",
            OfacSubjectKind.AIRCRAFT,
        ),
        (
            "-0- ",
            OfacSubjectKind.UNSPECIFIED,
        ),
    ],
)
def test_ofac_primary_record_derives_supported_subject_kind(
    raw_value: str,
    expected_kind: OfacSubjectKind,
) -> None:
    record = OfacPrimaryRecord.model_validate(
        _record_payload(
            source_entity_type_raw=raw_value,
        )
    )

    assert record.subject_kind is expected_kind


def test_ofac_primary_record_preserves_raw_publisher_text() -> None:
    record = OfacPrimaryRecord.model_validate(
        _record_payload(
            primary_name_raw="TEST PUBLISHER NAME  ",
            source_entity_type_raw="-0- ",
            program_text_raw="SDGT] [NS-PLC",
            remarks_raw="Publisher remarks exactly as supplied.  ",
        )
    )

    assert record.primary_name_raw == "TEST PUBLISHER NAME  "
    assert record.source_entity_type_raw == "-0- "
    assert record.program_text_raw == "SDGT] [NS-PLC"
    assert record.remarks_raw == ("Publisher remarks exactly as supplied.  ")

    assert record.subject_kind is OfacSubjectKind.UNSPECIFIED


def test_ofac_primary_record_uses_source_scoped_record_identity() -> None:
    record = OfacPrimaryRecord.model_validate(
        _record_payload(
            source_key="ofac_consolidated_csv",
            publisher_record_id="9647",
        )
    )

    assert record.source_record_key == (
        "ofac_consolidated_csv",
        "9647",
    )


def test_ofac_primary_record_accepts_operator_import_provenance() -> None:
    record = OfacPrimaryRecord.model_validate(
        _record_payload(
            acquisition_method="operator_import",
        )
    )

    assert record.acquisition_method == "operator_import"


def test_ofac_primary_record_rejects_unknown_source_key() -> None:
    with pytest.raises(
        ValidationError,
        match="ofac_sdn_csv",
    ):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                source_key="unapproved_ofac_source",
            )
        )


@pytest.mark.parametrize(
    "publisher_record_id",
    [
        "",
        "ABC",
        "17013A",
        "-1",
        "17 013",
    ],
)
def test_ofac_primary_record_rejects_non_numeric_publisher_id(
    publisher_record_id: str,
) -> None:
    with pytest.raises(ValidationError):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                publisher_record_id=publisher_record_id,
            )
        )


@pytest.mark.parametrize(
    "source_row_number",
    [
        0,
        -1,
    ],
)
def test_ofac_primary_record_rejects_invalid_row_number(
    source_row_number: int,
) -> None:
    with pytest.raises(ValidationError):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                source_row_number=source_row_number,
            )
        )


@pytest.mark.parametrize(
    "primary_name_raw",
    [
        "",
        " ",
        "\t",
        "\n",
    ],
)
def test_ofac_primary_record_rejects_blank_primary_name(
    primary_name_raw: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="primary name",
    ):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                primary_name_raw=primary_name_raw,
            )
        )


@pytest.mark.parametrize(
    "source_entity_type_raw",
    [
        "",
        "entity",
        "organization",
        "person",
        "Individual",
    ],
)
def test_ofac_primary_record_rejects_unsupported_entity_type(
    source_entity_type_raw: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="OFAC entity type",
    ):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                source_entity_type_raw=source_entity_type_raw,
            )
        )


@pytest.mark.parametrize(
    "program_text_raw",
    [
        "",
        " ",
        "\t",
    ],
)
def test_ofac_primary_record_rejects_blank_program_text(
    program_text_raw: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="program",
    ):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                program_text_raw=program_text_raw,
            )
        )


@pytest.mark.parametrize(
    "source_row_fingerprint",
    [
        "",
        "b" * 63,
        "b" * 65,
        "B" * 64,
        "g" * 64,
    ],
)
def test_ofac_primary_record_rejects_invalid_row_fingerprint(
    source_row_fingerprint: str,
) -> None:
    with pytest.raises(ValidationError):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                source_row_fingerprint=source_row_fingerprint,
            )
        )


@pytest.mark.parametrize(
    "source_sha256",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "z" * 64,
    ],
)
def test_ofac_primary_record_rejects_invalid_source_sha256(
    source_sha256: str,
) -> None:
    with pytest.raises(ValidationError):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                source_sha256=source_sha256,
            )
        )


def test_ofac_primary_record_rejects_naive_acquisition_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        OfacPrimaryRecord.model_validate(
            _record_payload(
                acquired_at=datetime(
                    2026,
                    8,
                    27,
                    12,
                    0,
                ),
            )
        )


def test_ofac_primary_record_forbids_extra_fields() -> None:
    payload = _record_payload()

    payload["analyst_guess"] = "same entity"

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        OfacPrimaryRecord.model_validate(payload)


def test_ofac_primary_record_is_immutable() -> None:
    record = OfacPrimaryRecord.model_validate(_record_payload())

    with pytest.raises(
        ValidationError,
        match="frozen",
    ):
        record.primary_name_raw = "MUTATED NAME"
