"""Regression tests for trusted source provenance models."""

from datetime import UTC, datetime

import pytest
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from black_meridian.data_sources.models import SourceSnapshot

_HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)

_SOURCE_URL = _HTTP_URL_ADAPTER.validate_python("https://official.example.test/source.csv")

_FETCHED_AT = datetime(
    2026,
    8,
    25,
    12,
    0,
    tzinfo=UTC,
)

_SHA256 = "a" * 64


def test_source_snapshot_rejects_zero_byte_evidence() -> None:
    """A trusted source snapshot must represent non-empty evidence."""

    with pytest.raises(
        ValidationError,
        match="greater than or equal to 1",
    ):
        SourceSnapshot(
            source_key="test_official_csv",
            acquisition_method="direct_http",
            requested_url=_SOURCE_URL,
            resolved_url=_SOURCE_URL,
            fetched_at=_FETCHED_AT,
            sha256=_SHA256,
            byte_size=0,
            content_type="text/csv",
            destination="data/raw/external/test/source.csv",
        )


def test_source_snapshot_accepts_non_empty_evidence() -> None:
    """A non-empty acquisition remains valid provenance evidence."""

    snapshot = SourceSnapshot(
        source_key="test_official_csv",
        acquisition_method="direct_http",
        requested_url=_SOURCE_URL,
        resolved_url=_SOURCE_URL,
        fetched_at=_FETCHED_AT,
        sha256=_SHA256,
        byte_size=1,
        content_type="text/csv",
        destination="data/raw/external/test/source.csv",
    )

    assert snapshot.byte_size == 1
    assert snapshot.acquisition_method == "direct_http"
