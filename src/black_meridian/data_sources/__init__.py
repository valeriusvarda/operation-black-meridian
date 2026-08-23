"""Public interface for trusted external data acquisition."""

from black_meridian.data_sources.fetcher import (
    DEFAULT_USER_AGENT,
    fetch_source,
    write_snapshot_manifest,
)
from black_meridian.data_sources.importer import (
    OperatorImportError,
    import_operator_source,
)
from black_meridian.data_sources.models import (
    AcquisitionMethod,
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
    "AcquisitionMethod",
    "DataSource",
    "OperatorImportError",
    "SourceFormat",
    "SourceSnapshot",
    "fetch_source",
    "get_source",
    "import_operator_source",
    "iter_sources",
    "write_snapshot_manifest",
]
