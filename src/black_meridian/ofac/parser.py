"""Deterministic offline parser for trusted OFAC primary CSV snapshots."""

from black_meridian.data_sources.models import SourceSnapshot
from black_meridian.ofac.contracts import OfacPrimaryRecord


class OfacParseError(ValueError):
    """Raised when trusted OFAC primary evidence violates its parser contract."""


def parse_ofac_primary_snapshot(
    content: bytes,
    snapshot: SourceSnapshot,
) -> tuple[OfacPrimaryRecord, ...]:
    """Parse one provenance-bound OFAC primary snapshot without network access."""

    del content
    del snapshot

    raise NotImplementedError(
        "OFAC primary parser behavior is not implemented yet."
    )
