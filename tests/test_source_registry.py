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
    "ofac_consolidated_addresses_csv",
    "ofac_consolidated_aliases_csv",
    "ofac_consolidated_comments_csv",
    "ofac_consolidated_csv",
    "ofac_sdn_addresses_csv",
    "ofac_sdn_aliases_csv",
    "ofac_sdn_comments_csv",
    "ofac_sdn_csv",
}

TRUSTED_HOSTS = {
    "api.gleif.org",
    "sanctionslistservice.ofac.treas.gov",
    "www.fatf-gafi.org",
}

EXPECTED_OFAC_EXPORTS = {
    "ofac_consolidated_addresses_csv": (
        "CONS_ADD.CSV",
        "cons_add.csv",
    ),
    "ofac_consolidated_aliases_csv": (
        "CONS_ALT.CSV",
        "cons_alt.csv",
    ),
    "ofac_consolidated_comments_csv": (
        "CONS_COMMENTS.CSV",
        "cons_comments.csv",
    ),
    "ofac_consolidated_csv": (
        "CONS_PRIM.CSV",
        "cons_prim.csv",
    ),
    "ofac_sdn_addresses_csv": (
        "ADD.CSV",
        "sdn_add.csv",
    ),
    "ofac_sdn_aliases_csv": (
        "ALT.CSV",
        "sdn_alt.csv",
    ),
    "ofac_sdn_comments_csv": (
        "SDN_COMMENTS.CSV",
        "sdn_comments.csv",
    ),
    "ofac_sdn_csv": (
        "SDN.CSV",
        "sdn.csv",
    ),
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


@pytest.mark.parametrize(
    ("source_key", "remote_filename", "local_filename"),
    [
        (
            source_key,
            remote_filename,
            local_filename,
        )
        for source_key, (
            remote_filename,
            local_filename,
        ) in sorted(EXPECTED_OFAC_EXPORTS.items())
    ],
)
def test_ofac_sources_target_documented_legacy_csv_series(
    source_key: str,
    remote_filename: str,
    local_filename: str,
) -> None:
    source = get_source(source_key)

    assert str(source.url).endswith(f"/api/PublicationPreview/exports/{remote_filename}")

    assert source.filename == local_filename


def test_ofac_series_has_four_sdn_sources() -> None:
    source_keys = {
        source_key for source_key in OFFICIAL_SOURCES if source_key.startswith("ofac_sdn")
    }

    assert source_keys == {
        "ofac_sdn_addresses_csv",
        "ofac_sdn_aliases_csv",
        "ofac_sdn_comments_csv",
        "ofac_sdn_csv",
    }


def test_ofac_series_has_four_consolidated_sources() -> None:
    source_keys = {
        source_key for source_key in OFFICIAL_SOURCES if source_key.startswith("ofac_consolidated")
    }

    assert source_keys == {
        "ofac_consolidated_addresses_csv",
        "ofac_consolidated_aliases_csv",
        "ofac_consolidated_comments_csv",
        "ofac_consolidated_csv",
    }


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(
        KeyError,
        match="Unknown source",
    ):
        get_source("unapproved_source")
