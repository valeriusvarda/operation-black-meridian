"""Regression tests for trusted direct-HTTP source acquisition."""

from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, TypeAdapter

from black_meridian.data_sources.fetcher import fetch_source
from black_meridian.data_sources.models import DataSource

_HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)

_RESOLVED_URL = "https://official.example.test/published/source.csv"


def _http_url(value: str) -> AnyHttpUrl:
    """Return one validated HTTP URL for test contracts."""

    return _HTTP_URL_ADAPTER.validate_python(value)


def _source() -> DataSource:
    """Return one approved-style CSV source definition."""

    return DataSource(
        key="test_official_csv",
        name="Test Official CSV",
        publisher="Test Publisher",
        url=_http_url("https://official.example.test/source.csv"),
        source_page=_http_url("https://official.example.test/"),
        format="csv",
        filename="source.csv",
        description=("Deterministic source used to validate acquisition invariants."),
        refresh_policy=("Retrieve only inside isolated acquisition regression tests."),
    )


class _FakeResponse:
    """Minimal deterministic response object for downloader tests."""

    def __init__(
        self,
        payload: bytes,
        *,
        content_type: str | None = "text/csv",
        resolved_url: str = _RESOLVED_URL,
    ) -> None:
        self._payload = payload
        self._consumed = False
        self._resolved_url = resolved_url

        self.headers: dict[str, str] = {}

        if content_type is not None:
            self.headers["Content-Type"] = content_type

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        del exc_type
        del exc_value
        del traceback

    def geturl(self) -> str:
        return self._resolved_url

    def read(
        self,
        size: int = -1,
    ) -> bytes:
        del size

        if self._consumed:
            return b""

        self._consumed = True

        return self._payload


def test_fetch_source_rejects_empty_response_and_preserves_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "source.csv"

    existing_payload = b"previously-trusted-source\n"

    destination.write_bytes(existing_payload)

    partial_path = destination.with_name(f".{destination.name}.partial")

    response = _FakeResponse(b"")

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> _FakeResponse:
        del request
        del timeout

        return response

    monkeypatch.setattr(
        "black_meridian.data_sources.fetcher.urlopen",
        fake_urlopen,
    )

    observed_error: OSError | None = None

    try:
        fetch_source(
            _source(),
            destination,
        )
    except OSError as exc:
        observed_error = exc

    assert destination.read_bytes() == existing_payload
    assert not partial_path.exists()

    assert observed_error is not None
    assert "empty" in str(observed_error).lower()


def test_fetch_source_rejects_empty_response_without_publishing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "source.csv"

    partial_path = destination.with_name(f".{destination.name}.partial")

    response = _FakeResponse(b"")

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> _FakeResponse:
        del request
        del timeout

        return response

    monkeypatch.setattr(
        "black_meridian.data_sources.fetcher.urlopen",
        fake_urlopen,
    )

    observed_error: OSError | None = None

    try:
        fetch_source(
            _source(),
            destination,
        )
    except OSError as exc:
        observed_error = exc

    assert not destination.exists()
    assert not partial_path.exists()

    assert observed_error is not None
    assert "empty" in str(observed_error).lower()


def test_fetch_source_publishes_non_empty_response_with_matching_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "source.csv"

    payload = b'1001,"Example Entity","Entity","TEST"\n'

    response = _FakeResponse(payload)

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> _FakeResponse:
        del request
        del timeout

        return response

    monkeypatch.setattr(
        "black_meridian.data_sources.fetcher.urlopen",
        fake_urlopen,
    )

    snapshot = fetch_source(
        _source(),
        destination,
    )

    assert destination.read_bytes() == payload

    assert snapshot.source_key == "test_official_csv"
    assert snapshot.acquisition_method == "direct_http"

    assert str(snapshot.requested_url) == ("https://official.example.test/source.csv")

    assert str(snapshot.resolved_url) == _RESOLVED_URL

    assert snapshot.byte_size == len(payload)

    assert snapshot.sha256 == sha256(payload).hexdigest()

    assert snapshot.content_type == "text/csv"

    assert snapshot.destination == str(destination)
