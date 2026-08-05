"""Fail-closed ISO alpha-3 normalization for parsed FATF publications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from black_meridian.data_sources.contracts import FatfJurisdiction, FatfTier
from black_meridian.fatf.parser import FatfPublication


class FatfNormalizationError(ValueError):
    """Raised when a FATF jurisdiction label cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class _JurisdictionIdentity:
    canonical_name: str
    iso_alpha3: str


@dataclass(frozen=True, slots=True)
class _JurisdictionSpec:
    canonical_name: str
    iso_alpha3: str
    aliases: tuple[str, ...]


_JURISDICTION_SPECS: Final[tuple[_JurisdictionSpec, ...]] = (
    _JurisdictionSpec(
        canonical_name="Democratic People's Republic of Korea",
        iso_alpha3="PRK",
        aliases=(
            "Democratic People's Republic of Korea",
            "Democratic Republic of Korea",
            "DPRK",
        ),
    ),
    _JurisdictionSpec(
        canonical_name="Iran",
        iso_alpha3="IRN",
        aliases=("Iran",),
    ),
    _JurisdictionSpec(
        canonical_name="Myanmar",
        iso_alpha3="MMR",
        aliases=("Myanmar",),
    ),
    _JurisdictionSpec(
        canonical_name="Angola",
        iso_alpha3="AGO",
        aliases=("Angola",),
    ),
    _JurisdictionSpec(
        canonical_name="Bolivia",
        iso_alpha3="BOL",
        aliases=("Bolivia",),
    ),
    _JurisdictionSpec(
        canonical_name="Bosnia and Herzegovina",
        iso_alpha3="BIH",
        aliases=("Bosnia and Herzegovina",),
    ),
    _JurisdictionSpec(
        canonical_name="Bulgaria",
        iso_alpha3="BGR",
        aliases=("Bulgaria",),
    ),
    _JurisdictionSpec(
        canonical_name="Cameroon",
        iso_alpha3="CMR",
        aliases=("Cameroon",),
    ),
    _JurisdictionSpec(
        canonical_name="Côte d'Ivoire",
        iso_alpha3="CIV",
        aliases=("Côte d'Ivoire", "Côte d\N{RIGHT SINGLE QUOTATION MARK}Ivoire"),
    ),
    _JurisdictionSpec(
        canonical_name="Democratic Republic of the Congo",
        iso_alpha3="COD",
        aliases=(
            "Democratic Republic of the Congo",
            "Democratic Republic of Congo",
        ),
    ),
    _JurisdictionSpec(
        canonical_name="Haiti",
        iso_alpha3="HTI",
        aliases=("Haiti",),
    ),
    _JurisdictionSpec(
        canonical_name="Iraq",
        iso_alpha3="IRQ",
        aliases=("Iraq",),
    ),
    _JurisdictionSpec(
        canonical_name="Kenya",
        iso_alpha3="KEN",
        aliases=("Kenya",),
    ),
    _JurisdictionSpec(
        canonical_name="Kuwait",
        iso_alpha3="KWT",
        aliases=("Kuwait",),
    ),
    _JurisdictionSpec(
        canonical_name="Lao PDR",
        iso_alpha3="LAO",
        aliases=(
            "Lao People's Democratic Republic",
            "Lao PDR",
        ),
    ),
    _JurisdictionSpec(
        canonical_name="Lebanon",
        iso_alpha3="LBN",
        aliases=("Lebanon",),
    ),
    _JurisdictionSpec(
        canonical_name="Monaco",
        iso_alpha3="MCO",
        aliases=("Monaco",),
    ),
    _JurisdictionSpec(
        canonical_name="Nepal",
        iso_alpha3="NPL",
        aliases=("Nepal",),
    ),
    _JurisdictionSpec(
        canonical_name="Papua New Guinea",
        iso_alpha3="PNG",
        aliases=("Papua New Guinea",),
    ),
    _JurisdictionSpec(
        canonical_name="South Sudan",
        iso_alpha3="SSD",
        aliases=("South Sudan",),
    ),
    _JurisdictionSpec(
        canonical_name="Syria",
        iso_alpha3="SYR",
        aliases=("Syria",),
    ),
    _JurisdictionSpec(
        canonical_name="Venezuela",
        iso_alpha3="VEN",
        aliases=("Venezuela",),
    ),
    _JurisdictionSpec(
        canonical_name="Vietnam",
        iso_alpha3="VNM",
        aliases=("Vietnam",),
    ),
    _JurisdictionSpec(
        canonical_name="Virgin Islands (UK)",
        iso_alpha3="VGB",
        aliases=("Virgin Islands (UK)", "British Virgin Islands"),
    ),
    _JurisdictionSpec(
        canonical_name="Yemen",
        iso_alpha3="YEM",
        aliases=("Yemen",),
    ),
)


def normalize_fatf_publication(
    publication: FatfPublication,
) -> tuple[FatfJurisdiction, ...]:
    """Normalize one parsed FATF publication without guessing identities."""

    records: list[FatfJurisdiction] = []
    source_labels_by_iso: dict[str, str] = {}

    tier_names = (
        (FatfTier.CALL_FOR_ACTION, publication.call_for_action_jurisdictions),
        (
            FatfTier.INCREASED_MONITORING,
            publication.increased_monitoring_jurisdictions,
        ),
    )

    for tier, jurisdiction_names in tier_names:
        for jurisdiction_name in jurisdiction_names:
            identity = _resolve_jurisdiction(jurisdiction_name)
            previous_label = source_labels_by_iso.get(identity.iso_alpha3)

            if previous_label is not None:
                raise FatfNormalizationError(
                    "FATF publication resolves multiple labels to ISO alpha-3 "
                    f"{identity.iso_alpha3}: {previous_label!r} and "
                    f"{jurisdiction_name!r}."
                )

            source_labels_by_iso[identity.iso_alpha3] = jurisdiction_name
            records.append(
                FatfJurisdiction(
                    jurisdiction_name=identity.canonical_name,
                    iso_alpha3=identity.iso_alpha3,
                    tier=tier,
                )
            )

    return tuple(records)


def _resolve_jurisdiction(jurisdiction_name: str) -> _JurisdictionIdentity:
    normalized_key = _normalization_key(jurisdiction_name)

    if not normalized_key:
        raise FatfNormalizationError("FATF jurisdiction name is empty.")

    identity = _JURISDICTION_ALIAS_INDEX.get(normalized_key)

    if identity is None:
        raise FatfNormalizationError(f"Unknown FATF jurisdiction name: {jurisdiction_name!r}.")

    return identity


def _build_alias_index() -> Mapping[str, _JurisdictionIdentity]:
    aliases: dict[str, _JurisdictionIdentity] = {}
    iso_alpha3_codes: set[str] = set()

    for spec in _JURISDICTION_SPECS:
        if not _is_iso_alpha3(spec.iso_alpha3):
            raise RuntimeError(
                f"Invalid ISO alpha-3 jurisdiction specification: {spec.iso_alpha3!r}."
            )

        if spec.iso_alpha3 in iso_alpha3_codes:
            raise RuntimeError(
                f"Duplicate ISO alpha-3 jurisdiction specification: {spec.iso_alpha3}."
            )

        canonical_key = _normalization_key(spec.canonical_name)

        if not canonical_key:
            raise RuntimeError(f"Empty canonical jurisdiction name for {spec.iso_alpha3}.")

        iso_alpha3_codes.add(spec.iso_alpha3)
        identity = _JurisdictionIdentity(
            canonical_name=spec.canonical_name,
            iso_alpha3=spec.iso_alpha3,
        )
        spec_alias_keys: set[str] = set()

        for alias in spec.aliases:
            alias_key = _normalization_key(alias)

            if not alias_key:
                raise RuntimeError(f"Empty FATF jurisdiction alias for {spec.iso_alpha3}.")

            if alias_key in spec_alias_keys:
                raise RuntimeError(
                    f"Duplicate alias inside FATF specification {spec.iso_alpha3}: {alias!r}."
                )

            previous_identity = aliases.get(alias_key)

            if previous_identity is not None:
                raise RuntimeError(
                    "Duplicate FATF jurisdiction alias "
                    f"{alias!r}: {previous_identity.iso_alpha3} and "
                    f"{spec.iso_alpha3}."
                )

            spec_alias_keys.add(alias_key)
            aliases[alias_key] = identity

        if canonical_key not in spec_alias_keys:
            raise RuntimeError(
                f"Canonical jurisdiction name is not an alias for {spec.iso_alpha3}."
            )

    return MappingProxyType(aliases)


def _normalization_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_iso_alpha3(value: str) -> bool:
    return len(value) == 3 and value.isascii() and value.isalpha() and value.isupper()


_JURISDICTION_ALIAS_INDEX: Final[Mapping[str, _JurisdictionIdentity]] = _build_alias_index()
