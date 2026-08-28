"""Deterministic contracts for complete OFAC source evidence sets."""

from collections import Counter
from hashlib import sha256
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from black_meridian.data_sources.models import SourceSnapshot

OFAC_SDN_SOURCE_KEYS: tuple[str, ...] = (
    "ofac_sdn_csv",
    "ofac_sdn_addresses_csv",
    "ofac_sdn_aliases_csv",
    "ofac_sdn_comments_csv",
)

OFAC_CONSOLIDATED_SOURCE_KEYS: tuple[str, ...] = (
    "ofac_consolidated_csv",
    "ofac_consolidated_addresses_csv",
    "ofac_consolidated_aliases_csv",
    "ofac_consolidated_comments_csv",
)

OFAC_EVIDENCE_SOURCE_KEYS: tuple[str, ...] = (
    *OFAC_SDN_SOURCE_KEYS,
    *OFAC_CONSOLIDATED_SOURCE_KEYS,
)

_EXPECTED_SOURCE_KEYS = frozenset(OFAC_EVIDENCE_SOURCE_KEYS)

_FINGERPRINT_DOMAIN = "operation-black-meridian/ofac-evidence-set/v1"


def _frame_text(value: str) -> bytes:
    """Encode text with deterministic length framing."""

    encoded = value.encode("utf-8")

    return (
        len(encoded).to_bytes(
            8,
            byteorder="big",
            signed=False,
        )
        + encoded
    )


class OfacEvidenceSet(BaseModel):
    """Immutable collection of the complete approved OFAC legacy CSV evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    snapshots: tuple[SourceSnapshot, ...]

    @model_validator(mode="after")
    def validate_complete_source_boundary(self) -> Self:
        """Require exactly one snapshot for every approved OFAC evidence source."""

        source_keys = tuple(snapshot.source_key for snapshot in self.snapshots)

        source_key_counts = Counter(source_keys)

        duplicate_source_keys = sorted(
            source_key for source_key, count in source_key_counts.items() if count > 1
        )

        if duplicate_source_keys:
            duplicate_text = ", ".join(duplicate_source_keys)

            raise ValueError(
                f"OFAC evidence set contains duplicate source_key values: {duplicate_text}."
            )

        actual_source_keys = frozenset(source_keys)

        missing_source_keys = sorted(_EXPECTED_SOURCE_KEYS - actual_source_keys)

        unexpected_source_keys = sorted(actual_source_keys - _EXPECTED_SOURCE_KEYS)

        if missing_source_keys or unexpected_source_keys:
            problems: list[str] = []

            if missing_source_keys:
                problems.append("missing: " + ", ".join(missing_source_keys))

            if unexpected_source_keys:
                problems.append("unexpected: " + ", ".join(unexpected_source_keys))

            raise ValueError(
                "OFAC evidence set must contain exactly "
                "one snapshot for each approved source; " + "; ".join(problems) + "."
            )

        destinations = tuple(snapshot.destination for snapshot in self.snapshots)

        if len(destinations) != len(set(destinations)):
            raise ValueError("OFAC evidence snapshots must use distinct destination identities.")

        return self

    @property
    def ordered_snapshots(
        self,
    ) -> tuple[SourceSnapshot, ...]:
        """Return snapshots in the canonical evidence-set order."""

        snapshots_by_source_key = {snapshot.source_key: snapshot for snapshot in self.snapshots}

        return tuple(
            snapshots_by_source_key[source_key] for source_key in OFAC_EVIDENCE_SOURCE_KEYS
        )

    @property
    def source_count(self) -> int:
        """Return the number of source snapshots in the evidence set."""

        return len(self.snapshots)

    @property
    def evidence_set_sha256(self) -> str:
        """Fingerprint the exact canonical source-key/content combination."""

        digest = sha256()

        digest.update(_frame_text(_FINGERPRINT_DOMAIN))

        for snapshot in self.ordered_snapshots:
            digest.update(_frame_text(snapshot.source_key))

            digest.update(_frame_text(snapshot.sha256))

            digest.update(_frame_text(str(snapshot.byte_size)))

        return digest.hexdigest()
