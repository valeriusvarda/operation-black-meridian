"""Deterministic parser for acquired FATF public-list HTML snapshots."""

from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from typing import Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from black_meridian.data_sources.contracts import FatfTier

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_COUNTRY_DETAIL_PATH_PREFIX = "/en/countries/detail/"

_CALL_FOR_ACTION_HEADING = "high-risk jurisdictions subject to a call for action"
_INCREASED_MONITORING_HEADING = "jurisdictions under increased monitoring"

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_DATE_PATTERN = re.compile(
    r"\b(?P<day>[0-3]?\d)\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<year>\d{4})\b",
    flags=re.IGNORECASE,
)


class FatfParseError(ValueError):
    """Raised when an acquired FATF page violates the expected structure."""


class FatfPublication(BaseModel):
    """Unnormalized jurisdiction names extracted from one FATF publication."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    publication_date: date
    call_for_action_jurisdictions: tuple[str, ...] = Field(min_length=1)
    increased_monitoring_jurisdictions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_jurisdiction_sets(self) -> Self:
        """Require canonical, unique, and mutually exclusive jurisdiction names."""

        jurisdiction_sets = (
            self.call_for_action_jurisdictions,
            self.increased_monitoring_jurisdictions,
        )

        for jurisdictions in jurisdiction_sets:
            canonical_names = tuple(" ".join(name.split()) for name in jurisdictions)

            if jurisdictions != canonical_names:
                raise ValueError("Jurisdiction names must use canonical whitespace.")

            casefolded_names = tuple(name.casefold() for name in jurisdictions)

            if len(casefolded_names) != len(set(casefolded_names)):
                raise ValueError("Jurisdiction names must be unique within each FATF tier.")

        call_for_action_names = {name.casefold() for name in self.call_for_action_jurisdictions}
        increased_monitoring_names = {
            name.casefold() for name in self.increased_monitoring_jurisdictions
        }

        if call_for_action_names & increased_monitoring_names:
            raise ValueError("A jurisdiction cannot appear in both FATF tiers.")

        return self


class _FatfLandingPageParser(HTMLParser):
    """Collect FATF statement dates and jurisdiction names from structural sections."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

        self._current_tier: FatfTier | None = None
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._capturing_anchor = False
        self._anchor_parts: list[str] = []
        self._anchor_href: str | None = None

        self._heading_counts: dict[FatfTier, int] = {tier: 0 for tier in FatfTier}
        self._statement_dates: dict[FatfTier, list[date]] = {tier: [] for tier in FatfTier}
        self._jurisdiction_names: dict[FatfTier, list[str]] = {tier: [] for tier in FatfTier}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Begin structural heading or section-anchor capture."""

        normalized_tag = tag.casefold()

        if normalized_tag in _HEADING_TAGS:
            self._current_tier = None
            self._heading_tag = normalized_tag
            self._heading_parts = []
            return

        if normalized_tag == "a" and self._current_tier is not None:
            self._capturing_anchor = True
            self._anchor_parts = []
            self._anchor_href = next(
                (value for name, value in attrs if name.casefold() == "href"),
                None,
            )

    def handle_endtag(self, tag: str) -> None:
        """Finalize structural heading or anchor capture."""

        normalized_tag = tag.casefold()

        if normalized_tag == "a" and self._capturing_anchor:
            anchor_text = _normalize_text(self._anchor_parts)
            anchor_href = self._anchor_href

            self._capturing_anchor = False
            self._anchor_parts = []
            self._anchor_href = None

            if anchor_text:
                self._record_anchor(anchor_text, anchor_href)

        if normalized_tag == self._heading_tag:
            heading_text = _normalize_text(self._heading_parts)
            self._heading_tag = None
            self._heading_parts = []
            self._record_heading(heading_text)

    def handle_data(self, data: str) -> None:
        """Collect textual content for the active heading and anchor."""

        if self._heading_tag is not None:
            self._heading_parts.append(data)

        if self._capturing_anchor:
            self._anchor_parts.append(data)

    def build_publication(self) -> FatfPublication:
        """Validate collected structure and build the parsed publication contract."""

        for tier in FatfTier:
            heading_count = self._heading_counts[tier]

            if heading_count != 1:
                raise FatfParseError(
                    f"Expected exactly one structural heading for {tier.value}; "
                    f"found {heading_count}."
                )

            statement_dates = self._statement_dates[tier]

            if len(statement_dates) != 1:
                raise FatfParseError(
                    f"Expected exactly one dated statement link for {tier.value}; "
                    f"found {len(statement_dates)}."
                )

            if not self._jurisdiction_names[tier]:
                raise FatfParseError(f"No jurisdictions were extracted for FATF tier {tier.value}.")

        call_for_action_date = self._statement_dates[FatfTier.CALL_FOR_ACTION][0]
        increased_monitoring_date = self._statement_dates[FatfTier.INCREASED_MONITORING][0]

        if call_for_action_date != increased_monitoring_date:
            raise FatfParseError("FATF tier statement dates do not identify one publication state.")

        try:
            return FatfPublication(
                publication_date=call_for_action_date,
                call_for_action_jurisdictions=tuple(
                    self._jurisdiction_names[FatfTier.CALL_FOR_ACTION]
                ),
                increased_monitoring_jurisdictions=tuple(
                    self._jurisdiction_names[FatfTier.INCREASED_MONITORING]
                ),
            )
        except ValidationError as exc:
            raise FatfParseError("Parsed FATF content violated the publication contract.") from exc

    def _record_heading(self, text: str) -> None:
        normalized_heading = text.casefold()

        if _CALL_FOR_ACTION_HEADING in normalized_heading:
            tier = FatfTier.CALL_FOR_ACTION
        elif _INCREASED_MONITORING_HEADING in normalized_heading:
            tier = FatfTier.INCREASED_MONITORING
        else:
            self._current_tier = None
            return

        self._current_tier = tier
        self._heading_counts[tier] += 1

    def _record_anchor(
        self,
        text: str,
        href: str | None,
    ) -> None:
        if self._current_tier is None:
            return

        statement_date = _extract_date(text)

        if statement_date is not None:
            self._statement_dates[self._current_tier].append(statement_date)
            return

        if not self._statement_dates[self._current_tier]:
            return

        if not _is_jurisdiction_href(href):
            return

        self._jurisdiction_names[self._current_tier].append(text)


def parse_fatf_publication(html: str) -> FatfPublication:
    """Parse one acquired FATF landing-page snapshot without network access."""

    if not html.strip():
        raise FatfParseError("FATF HTML content is empty.")

    parser = _FatfLandingPageParser()

    try:
        parser.feed(html)
        parser.close()
    except FatfParseError:
        raise
    except Exception as exc:
        raise FatfParseError("FATF HTML parsing failed.") from exc

    return parser.build_publication()


def _normalize_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


def _is_jurisdiction_href(href: str | None) -> bool:
    if href is None:
        return False

    normalized_path = urlparse(href).path.casefold()

    if not normalized_path.startswith(_COUNTRY_DETAIL_PATH_PREFIX):
        return False

    detail_slug = normalized_path.removeprefix(_COUNTRY_DETAIL_PATH_PREFIX)

    return detail_slug.endswith(".html") and detail_slug != ".html" and "/" not in detail_slug


def _extract_date(text: str) -> date | None:
    matches = list(_DATE_PATTERN.finditer(text))

    if not matches:
        return None

    if len(matches) != 1:
        raise FatfParseError("A FATF statement link contains multiple dates.")

    match = matches[0]
    month_name = match.group("month").casefold()

    try:
        return date(
            year=int(match.group("year")),
            month=_MONTHS[month_name],
            day=int(match.group("day")),
        )
    except ValueError as exc:
        raise FatfParseError(f"Invalid FATF publication date: {match.group(0)}.") from exc
