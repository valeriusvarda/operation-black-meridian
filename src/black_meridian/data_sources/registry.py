"""Registry of approved official external data sources."""

from collections.abc import Mapping
from types import MappingProxyType

from black_meridian.data_sources.models import DataSource


_SOURCE_MAP: dict[str, DataSource] = {
    "fatf_monitored_jurisdictions_html": DataSource(
        key="fatf_monitored_jurisdictions_html",
        name="FATF High-Risk and Monitored Jurisdictions",
        publisher="Financial Action Task Force",
        url=(
            "https://www.fatf-gafi.org/en/countries/"
            "black-and-grey-lists.html"
        ),
        source_page=(
            "https://www.fatf-gafi.org/en/publications/"
            "High-risk-and-other-monitored-jurisdictions/"
            "More-on-high-risk-and-non-cooperative-jurisdictions.html"
        ),
        format="html",
        filename="fatf-black-and-grey-lists.html",
        description=(
            "Official FATF publication covering high-risk jurisdictions "
            "and jurisdictions under increased monitoring."
        ),
        refresh_policy=(
            "Refresh after every FATF plenary publication and preserve "
            "the retrieval manifest used by each analytical run."
        ),
    ),
    "gleif_lei_records_json": DataSource(
        key="gleif_lei_records_json",
        name="GLEIF LEI Records API",
        publisher="Global Legal Entity Identifier Foundation",
        url="https://api.gleif.org/api/v1/lei-records",
        source_page="https://www.gleif.org/en/lei-data/gleif-api",
        format="json",
        filename="lei-records.json",
        description=(
            "Official JSON:API endpoint for real legal-entity reference "
            "and Legal Entity Identifier records."
        ),
        refresh_policy=(
            "Retrieve on demand for entity-resolution workflows and retain "
            "a snapshot manifest for every material analytical result."
        ),
    ),
    "ofac_consolidated_csv": DataSource(
        key="ofac_consolidated_csv",
        name="OFAC Consolidated Non-SDN List",
        publisher="U.S. Department of the Treasury — OFAC",
        url=(
            "https://sanctionslistservice.ofac.treas.gov/"
            "api/PublicationPreview/exports/CONSOLIDATED.CSV"
        ),
        source_page="https://ofac.treasury.gov/sanctions-list-service",
        format="csv",
        filename="consolidated.csv",
        description=(
            "Official consolidated data file covering OFAC sanctions lists "
            "outside the primary SDN publication."
        ),
        refresh_policy=(
            "Refresh before sanctions-screening analysis and preserve "
            "the exact digest used by each run."
        ),
    ),
    "ofac_sdn_csv": DataSource(
        key="ofac_sdn_csv",
        name="OFAC Specially Designated Nationals List",
        publisher="U.S. Department of the Treasury — OFAC",
        url=(
            "https://sanctionslistservice.ofac.treas.gov/"
            "api/PublicationPreview/exports/SDN.CSV"
        ),
        source_page="https://ofac.treasury.gov/sanctions-list-service",
        format="csv",
        filename="sdn.csv",
        description=(
            "Official Specially Designated Nationals and Blocked Persons "
            "data file published by OFAC."
        ),
        refresh_policy=(
            "Refresh before sanctions-screening analysis and preserve "
            "the exact digest used by each run."
        ),
    ),
}


OFFICIAL_SOURCES: Mapping[str, DataSource] = MappingProxyType(_SOURCE_MAP)


def get_source(source_key: str) -> DataSource:
    """Return one approved source or raise a descriptive KeyError."""

    try:
        return OFFICIAL_SOURCES[source_key]
    except KeyError as exc:
        available = ", ".join(sorted(OFFICIAL_SOURCES))
        raise KeyError(
            f"Unknown source '{source_key}'. Available sources: {available}"
        ) from exc


def iter_sources() -> tuple[DataSource, ...]:
    """Return all approved sources in deterministic key order."""

    return tuple(
        OFFICIAL_SOURCES[source_key]
        for source_key in sorted(OFFICIAL_SOURCES)
    )
