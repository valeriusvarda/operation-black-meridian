import csv
from datetime import UTC, date, datetime
from io import StringIO

from black_meridian.data_sources.contracts import (
    FatfJurisdiction,
    FatfSnapshot,
    FatfTier,
)
from black_meridian.fatf.exporter import (
    serialize_fatf_csv,
    serialize_fatf_json,
)

SOURCE_URL = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
CONTENT_SHA256 = "a" * 64

EXPECTED_CSV_TEXT = (
    "jurisdiction_name,iso_alpha3,tier,publication_date,source_name,source_url,"
    "retrieved_at,content_sha256\n"
    "Côte d'Ivoire,CIV,increased_monitoring,2026-06-19,Financial Action Task Force,"
    f"{SOURCE_URL},2026-06-19T12:34:56+00:00,{CONTENT_SHA256}\n"
    '"Democratic Republic of the Congo, ""DRC""",COD,increased_monitoring,'
    "2026-06-19,Financial Action Task Force,"
    f"{SOURCE_URL},2026-06-19T12:34:56+00:00,{CONTENT_SHA256}\n"
)

EXPECTED_JSON_TEXT = (
    "{\n"
    f'  "content_sha256": "{CONTENT_SHA256}",\n'
    '  "publication_date": "2026-06-19",\n'
    '  "record_count": 2,\n'
    '  "records": [\n'
    "    {\n"
    '      "iso_alpha3": "CIV",\n'
    '      "jurisdiction_name": "Côte d\'Ivoire",\n'
    '      "tier": "increased_monitoring"\n'
    "    },\n"
    "    {\n"
    '      "iso_alpha3": "COD",\n'
    '      "jurisdiction_name": "Democratic Republic of the Congo, \\"DRC\\"",\n'
    '      "tier": "increased_monitoring"\n'
    "    }\n"
    "  ],\n"
    '  "retrieved_at": "2026-06-19T12:34:56Z",\n'
    '  "source_name": "Financial Action Task Force",\n'
    f'  "source_url": "{SOURCE_URL}"\n'
    "}\n"
)


def _snapshot() -> FatfSnapshot:
    return FatfSnapshot(
        source_url=SOURCE_URL,
        publication_date=date(2026, 6, 19),
        retrieved_at=datetime(
            2026,
            6,
            19,
            12,
            34,
            56,
            tzinfo=UTC,
        ),
        content_sha256=CONTENT_SHA256,
        records=(
            FatfJurisdiction(
                jurisdiction_name="Côte d'Ivoire",
                iso_alpha3="CIV",
                tier=FatfTier.INCREASED_MONITORING,
            ),
            FatfJurisdiction(
                jurisdiction_name='Democratic Republic of the Congo, "DRC"',
                iso_alpha3="COD",
                tier=FatfTier.INCREASED_MONITORING,
            ),
        ),
    )


def test_csv_serialization_matches_exact_byte_contract() -> None:
    serialized = serialize_fatf_csv(_snapshot())

    assert serialized == EXPECTED_CSV_TEXT.encode()
    assert b"\r\n" not in serialized

    rows = list(
        csv.reader(
            StringIO(
                serialized.decode("utf-8"),
            )
        )
    )

    assert rows[0] == [
        "jurisdiction_name",
        "iso_alpha3",
        "tier",
        "publication_date",
        "source_name",
        "source_url",
        "retrieved_at",
        "content_sha256",
    ]
    assert rows[1][0] == "Côte d'Ivoire"
    assert rows[2][0] == 'Democratic Republic of the Congo, "DRC"'


def test_json_serialization_matches_exact_byte_contract() -> None:
    serialized = serialize_fatf_json(_snapshot())

    assert serialized == EXPECTED_JSON_TEXT.encode()
    assert serialized.endswith(b"\n")
    assert "Côte d'Ivoire".encode() in serialized
    assert b"\\u00f4" not in serialized


def test_repeat_serialization_is_byte_identical() -> None:
    snapshot = _snapshot()

    assert serialize_fatf_csv(snapshot) == serialize_fatf_csv(snapshot)
    assert serialize_fatf_json(snapshot) == serialize_fatf_json(snapshot)
