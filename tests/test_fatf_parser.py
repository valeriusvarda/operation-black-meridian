from datetime import date
from pathlib import Path

import pytest

from black_meridian.fatf.parser import (
    FatfParseError,
    parse_fatf_publication,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fatf" / "publication_page.html"

CALL_FOR_ACTION_HEADING = "High-Risk Jurisdictions subject to a Call for Action"
INCREASED_MONITORING_HEADING = "Jurisdictions under Increased Monitoring"


def _jurisdiction_links(names: tuple[str, ...]) -> str:
    return "\n".join(
        f'<a href="/jurisdictions/{index}">{name}</a>' for index, name in enumerate(names)
    )


def _build_html(
    *,
    call_for_action_statement: str = "Statement - 19 June 2026",
    increased_monitoring_statement: str = "Statement - 19 June 2026",
    call_for_action_names: tuple[str, ...] = ("Iran",),
    increased_monitoring_names: tuple[str, ...] = ("Haiti",),
    duplicate_call_for_action_heading: bool = False,
    include_increased_monitoring_section: bool = True,
) -> str:
    duplicate_heading = ""

    if duplicate_call_for_action_heading:
        duplicate_heading = f"<h2>{CALL_FOR_ACTION_HEADING}</h2>"

    increased_monitoring_section = ""

    if include_increased_monitoring_section:
        increased_monitoring_section = f"""
        <h2>{INCREASED_MONITORING_HEADING}</h2>
        <a href="/statement/increased-monitoring">
          {increased_monitoring_statement}
        </a>
        {_jurisdiction_links(increased_monitoring_names)}
        """

    return f"""
    <html>
      <body>
        <h2>{CALL_FOR_ACTION_HEADING}</h2>
        {duplicate_heading}

        <a href="/statement/call-for-action">
          {call_for_action_statement}
        </a>

        {_jurisdiction_links(call_for_action_names)}

        {increased_monitoring_section}
      </body>
    </html>
    """


def test_publication_fixture_parses_expected_structure() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    publication = parse_fatf_publication(html)

    assert publication.publication_date == date(2026, 6, 19)
    assert publication.call_for_action_jurisdictions == (
        "Democratic People's Republic of Korea",
        "Iran",
        "Myanmar",
    )
    assert publication.increased_monitoring_jurisdictions == (
        "Angola",
        "Haiti",
        "Kenya",
    )


@pytest.mark.parametrize("html", ["", " \n\t"])
def test_empty_html_is_rejected(html: str) -> None:
    with pytest.raises(
        FatfParseError,
        match="FATF HTML content is empty",
    ):
        parse_fatf_publication(html)


def test_missing_fatf_tier_is_rejected() -> None:
    html = _build_html(
        include_increased_monitoring_section=False,
    )

    with pytest.raises(
        FatfParseError,
        match=("Expected exactly one structural heading for increased_monitoring; found 0"),
    ):
        parse_fatf_publication(html)


def test_duplicate_structural_heading_is_rejected() -> None:
    html = _build_html(
        duplicate_call_for_action_heading=True,
    )

    with pytest.raises(
        FatfParseError,
        match=("Expected exactly one structural heading for call_for_action; found 2"),
    ):
        parse_fatf_publication(html)


def test_missing_jurisdictions_are_rejected() -> None:
    html = _build_html(
        call_for_action_names=(),
    )

    with pytest.raises(
        FatfParseError,
        match="No jurisdictions were extracted for FATF tier call_for_action",
    ):
        parse_fatf_publication(html)


def test_mismatched_statement_dates_are_rejected() -> None:
    html = _build_html(
        increased_monitoring_statement="Statement - 20 June 2026",
    )

    with pytest.raises(
        FatfParseError,
        match=("FATF tier statement dates do not identify one publication state"),
    ):
        parse_fatf_publication(html)


def test_multiple_dates_in_one_statement_are_rejected() -> None:
    html = _build_html(
        call_for_action_statement=("Statement - 19 June 2026 updated 20 June 2026"),
    )

    with pytest.raises(
        FatfParseError,
        match="A FATF statement link contains multiple dates",
    ):
        parse_fatf_publication(html)


def test_invalid_statement_date_is_rejected() -> None:
    html = _build_html(
        call_for_action_statement="Statement - 31 February 2026",
    )

    with pytest.raises(
        FatfParseError,
        match="Invalid FATF publication date: 31 February 2026",
    ):
        parse_fatf_publication(html)


def test_duplicate_jurisdiction_within_tier_is_rejected() -> None:
    html = _build_html(
        call_for_action_names=("Iran", "Iran"),
    )

    with pytest.raises(
        FatfParseError,
        match="Parsed FATF content violated the publication contract",
    ):
        parse_fatf_publication(html)


def test_jurisdiction_overlap_between_tiers_is_rejected() -> None:
    html = _build_html(
        call_for_action_names=("Iran",),
        increased_monitoring_names=("Iran",),
    )

    with pytest.raises(
        FatfParseError,
        match="Parsed FATF content violated the publication contract",
    ):
        parse_fatf_publication(html)
