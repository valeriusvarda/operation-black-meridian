"""Public interface for trusted external data acquisition."""

from black_meridian.data_sources.fetcher import (
    DEFAULT_USER_AGENT,
    fetch_source,
    write_snapshot_manifest,
)
from black_meridian.data_sources.models import (
    DataSource,
    SourceFormat,
    SourceSnapshot,
)
from black_meridian.data_sources.registry import (
    OFFICIAL_SOURCES,
    get_source,
    iter_sources,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "OFFICIAL_SOURCES",
    "DataSource",
    "SourceFormat",
    "SourceSnapshot",
    "fetch_source",
    "get_source",
    "iter_sources",
    "write_snapshot_manifest",
]
