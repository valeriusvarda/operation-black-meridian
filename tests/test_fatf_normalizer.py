from datetime import date

import pytest

from black_meridian.data_sources.contracts import FatfTier
from black_meridian.fatf.normalizer import (
    FatfNormalizationError,
    normalize_fatf_publication,
)
from black_meridian.fatf.parser import FatfPublication

PUBLICATION_DATE = date(2026, 6, 19)

CALL_FOR_ACTION_NAMES = (
    "Democratic People's Republic of Korea",
    "Iran",
    "Myanmar",
)

INCREASED_MONITORING_NAMES = (
    "Angola",
    "Bolivia",
    "Bosnia and Herzegovina",
    "Bulgaria",
    "Cameroon",
    "Côte d'Ivoire",
    "Democratic Republic of Congo",
    "Haiti",
    "Iraq",
    "Kenya",
    "Kuwait",
    "Lao People's Democratic Republic",
    "Lebanon",
    "Monaco",
    "Nepal",
    "Papua New Guinea",
    "South Sudan",
    "Syria",
    "Venezuela",
    "Vietnam",
    "Virgin Islands (UK)",
    "Yemen",
)

EXPECTED_RECORDS = (
    ("Democratic People's Republic of Korea", "PRK", FatfTier.CALL_FOR_ACTION),
    ("Iran", "IRN", FatfTier.CALL_FOR_ACTION),
    ("Myanmar", "MMR", FatfTier.CALL_FOR_ACTION),
    ("Angola", "AGO", FatfTier.INCREASED_MONITORING),
    ("Bolivia", "BOL", FatfTier.INCREASED_MONITORING),
    ("Bosnia and Herzegovina", "BIH", FatfTier.INCREASED_MONITORING),
    ("Bulgaria", "BGR", FatfTier.INCREASED_MONITORING),
    ("Cameroon", "CMR", FatfTier.INCREASED_MONITORING),
    ("Côte d'Ivoire", "CIV", FatfTier.INCREASED_MONITORING),
    ("Democratic Republic of the Congo", "COD", FatfTier.INCREASED_MONITORING),
    ("Haiti", "HTI", FatfTier.INCREASED_MONITORING),
    ("Iraq", "IRQ", FatfTier.INCREASED_MONITORING),
    ("Kenya", "KEN", FatfTier.INCREASED_MONITORING),
    ("Kuwait", "KWT", FatfTier.INCREASED_MONITORING),
    ("Lao PDR", "LAO", FatfTier.INCREASED_MONITORING),
    ("Lebanon", "LBN", FatfTier.INCREASED_MONITORING),
    ("Monaco", "MCO", FatfTier.INCREASED_MONITORING),
    ("Nepal", "NPL", FatfTier.INCREASED_MONITORING),
    ("Papua New Guinea", "PNG", FatfTier.INCREASED_MONITORING),
    ("South Sudan", "SSD", FatfTier.INCREASED_MONITORING),
    ("Syria", "SYR", FatfTier.INCREASED_MONITORING),
    ("Venezuela", "VEN", FatfTier.INCREASED_MONITORING),
    ("Vietnam", "VNM", FatfTier.INCREASED_MONITORING),
    ("Virgin Islands (UK)", "VGB", FatfTier.INCREASED_MONITORING),
    ("Yemen", "YEM", FatfTier.INCREASED_MONITORING),
)


def _publication(
    *,
    call_for_action: tuple[str, ...] = CALL_FOR_ACTION_NAMES,
    increased_monitoring: tuple[str, ...] = INCREASED_MONITORING_NAMES,
) -> FatfPublication:
    return FatfPublication(
        publication_date=PUBLICATION_DATE,
        call_for_action_jurisdictions=call_for_action,
        increased_monitoring_jurisdictions=increased_monitoring,
    )


def test_current_fatf_labels_normalize_to_expected_records() -> None:
    records = normalize_fatf_publication(_publication())

    actual_records = tuple(
        (record.jurisdiction_name, record.iso_alpha3, record.tier) for record in records
    )

    assert actual_records == EXPECTED_RECORDS


@pytest.mark.parametrize(
    ("source_label", "canonical_name", "iso_alpha3"),
    [
        (
            "Democratic Republic of Korea",
            "Democratic People's Republic of Korea",
            "PRK",
        ),
        ("DPRK", "Democratic People's Republic of Korea", "PRK"),
        (
            "Côte d\N{RIGHT SINGLE QUOTATION MARK}Ivoire",
            "Côte d'Ivoire",
            "CIV",
        ),
        (
            "Democratic Republic of the Congo",
            "Democratic Republic of the Congo",
            "COD",
        ),
        ("Lao PDR", "Lao PDR", "LAO"),
        ("British Virgin Islands", "Virgin Islands (UK)", "VGB"),
    ],
)
def test_explicit_aliases_resolve_to_canonical_identity(
    source_label: str,
    canonical_name: str,
    iso_alpha3: str,
) -> None:
    records = normalize_fatf_publication(
        _publication(
            call_for_action=(source_label,),
            increased_monitoring=("Haiti",),
        )
    )

    assert records[0].jurisdiction_name == canonical_name
    assert records[0].iso_alpha3 == iso_alpha3
    assert records[0].tier is FatfTier.CALL_FOR_ACTION


def test_matching_is_case_insensitive_without_fuzzy_inference() -> None:
    records = normalize_fatf_publication(
        _publication(
            call_for_action=("dprk",),
            increased_monitoring=("HAITI",),
        )
    )

    assert tuple(record.iso_alpha3 for record in records) == ("PRK", "HTI")


@pytest.mark.parametrize("unknown_name", ["Atlantis", "Viet Nam", "Korea"])
def test_unknown_jurisdiction_names_are_rejected(unknown_name: str) -> None:
    publication = _publication(
        call_for_action=(unknown_name,),
        increased_monitoring=("Haiti",),
    )

    with pytest.raises(
        FatfNormalizationError,
        match="Unknown FATF jurisdiction name",
    ):
        normalize_fatf_publication(publication)


def test_empty_jurisdiction_name_is_rejected() -> None:
    publication = _publication(
        call_for_action=("",),
        increased_monitoring=("Haiti",),
    )

    with pytest.raises(
        FatfNormalizationError,
        match="FATF jurisdiction name is empty",
    ):
        normalize_fatf_publication(publication)


def test_aliases_resolving_to_one_identity_are_rejected() -> None:
    publication = _publication(
        call_for_action=("Democratic People's Republic of Korea",),
        increased_monitoring=("DPRK",),
    )

    with pytest.raises(
        FatfNormalizationError,
        match="resolves multiple labels to ISO alpha-3 PRK",
    ):
        normalize_fatf_publication(publication)
