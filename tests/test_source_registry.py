"""Regression tests for the approved official-source registry."""

from urllib.parse import urlparse

import pytest

from black_meridian.data_sources import (
    OFFICIAL_SOURCES,
    get_source,
    iter_sources,
)

EXPECTED_SOURCE_KEYS = {
    "fatf_monitored_jurisdictions_html",
    "gleif_lei_records_json",
    "ofac_consolidated_csv",
    "ofac_sdn_csv",
}

TRUSTED_HOSTS = {
    "api.gleif.org",
    "sanctionslistservice.ofac.treas.gov",
    "www.fatf-gafi.org",
}


def test_registry_contains_required_official_sources() -> None:
    assert set(OFFICIAL_SOURCES) == EXPECTED_SOURCE_KEYS


def test_registered_sources_use_trusted_https_hosts() -> None:
    for source in iter_sources():
        parsed_url = urlparse(str(source.url))

        assert parsed_url.scheme == "https"
        assert parsed_url.hostname in TRUSTED_HOSTS
        assert source.filename.endswith(f".{source.format}")


def test_registry_iteration_is_deterministic() -> None:
    observed_keys = [source.key for source in iter_sources()]

    assert observed_keys == sorted(EXPECTED_SOURCE_KEYS)


def test_registry_filenames_are_unique() -> None:
    filenames = [source.filename for source in iter_sources()]

    assert len(filenames) == len(set(filenames))


def test_ofac_consolidated_source_targets_primary_legacy_csv() -> None:
    source = get_source("ofac_consolidated_csv")

    assert str(source.url).endswith("/api/PublicationPreview/exports/CONS_PRIM.CSV")

    assert source.filename == "cons_prim.csv"


def test_ofac_sdn_source_targets_primary_legacy_csv() -> None:
    source = get_source("ofac_sdn_csv")

    assert str(source.url).endswith("/api/PublicationPreview/exports/SDN.CSV")

    assert source.filename == "sdn.csv"


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(
        KeyError,
        match="Unknown source",
    ):
        get_source("unapproved_source")
