"""Integrity-aware downloader for approved external data sources."""

import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

from black_meridian.data_sources.models import (
    DataSource,
    SourceFormat,
    SourceSnapshot,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; OperationBlackMeridian/0.1; "
    "+https://github.com/valeriusvarda/operation-black-meridian)"
)

_CHUNK_SIZE = 1024 * 1024

_ACCEPT_HEADERS: dict[SourceFormat, str] = {
    "csv": "text/csv, application/octet-stream;q=0.9, */*;q=0.1",
    "html": "text/html, application/xhtml+xml;q=0.9, */*;q=0.1",
    "json": "application/vnd.api+json, application/json;q=0.9, */*;q=0.1",
    "xml": "application/xml, text/xml;q=0.9, */*;q=0.1",
}


def fetch_source(
    source: DataSource,
    destination: Path,
    *,
    timeout_seconds: float = 60.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> SourceSnapshot:
    """Download an approved source and return immutable provenance metadata."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = destination.with_name(f".{destination.name}.partial")

    digest = sha256()
    byte_size = 0
    resolved_url = str(source.url)
    content_type: str | None = None

    request = Request(
        str(source.url),
        headers={
            "Accept": _ACCEPT_HEADERS[source.format],
            "User-Agent": user_agent,
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            resolved_url = response.geturl()

            content_type = response.headers.get("Content-Type")

            with partial_path.open("wb") as output:
                while True:
                    chunk = response.read(_CHUNK_SIZE)

                    if not chunk:
                        break

                    output.write(chunk)

                    digest.update(chunk)

                    byte_size += len(chunk)

                output.flush()

                os.fsync(output.fileno())

        os.replace(
            partial_path,
            destination,
        )

    except Exception:
        partial_path.unlink(missing_ok=True)

        raise

    return SourceSnapshot(
        source_key=source.key,
        acquisition_method="direct_http",
        requested_url=source.url,
        resolved_url=resolved_url,
        fetched_at=datetime.now(UTC),
        sha256=digest.hexdigest(),
        byte_size=byte_size,
        content_type=content_type,
        destination=str(destination),
    )


def write_snapshot_manifest(
    snapshot: SourceSnapshot,
    destination: Path,
) -> Path:
    """Persist snapshot provenance beside the downloaded source atomically."""

    manifest_path = destination.with_name(f"{destination.name}.manifest.json")

    temporary_path = manifest_path.with_name(f".{manifest_path.name}.partial")

    payload = snapshot.model_dump_json(indent=2) + "\n"

    try:
        temporary_path.write_text(
            payload,
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            manifest_path,
        )

    except Exception:
        temporary_path.unlink(missing_ok=True)

        raise

    return manifest_path
