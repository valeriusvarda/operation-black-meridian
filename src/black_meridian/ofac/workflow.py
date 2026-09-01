"""End-to-end OFAC evidence orchestration over trusted source snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from black_meridian.data_sources.models import (
    SourceSnapshot,
)
from black_meridian.ofac.aggregate import (
    OfacAggregationError,
    OfacEntityEvidence,
    build_ofac_entity_evidence,
)
from black_meridian.ofac.comments import (
    OfacCommentParseError,
    OfacCommentRecord,
    parse_ofac_comment_snapshot,
)
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
)
from black_meridian.ofac.evidence import (
    OfacEvidenceSet,
)
from black_meridian.ofac.exporter import (
    OfacExportError,
    write_ofac_csv,
    write_ofac_json,
)
from black_meridian.ofac.parser import (
    OfacParseError,
    parse_ofac_primary_snapshot,
)
from black_meridian.ofac.relations import (
    OfacAddressRecord,
    OfacAliasRecord,
    OfacRelationParseError,
    parse_ofac_address_snapshot,
    parse_ofac_alias_snapshot,
)

OFAC_CSV_FILENAME: Final = "ofac_entities.csv"

OFAC_JSON_FILENAME: Final = "ofac_entities.json"


class OfacWorkflowError(RuntimeError):
    """Raised when trusted OFAC evidence cannot be produced safely."""


@dataclass(
    frozen=True,
    slots=True,
)
class OfacEvidenceResult:
    """Validated artifacts and evidence produced by one OFAC workflow run."""

    source_paths: tuple[
        Path,
        ...,
    ]

    csv_path: Path

    json_path: Path

    evidence_set: OfacEvidenceSet

    entities: tuple[
        OfacEntityEvidence,
        ...,
    ]

    @property
    def source_count(
        self,
    ) -> int:
        """Return trusted source count."""

        return self.evidence_set.source_count

    @property
    def entity_count(
        self,
    ) -> int:
        """Return primary evidence occurrence count."""

        return len(self.entities)

    @property
    def address_count(
        self,
    ) -> int:
        """Return total publisher-linked address count."""

        return sum(entity.address_count for entity in self.entities)

    @property
    def alias_count(
        self,
    ) -> int:
        """Return total publisher-linked alias count."""

        return sum(entity.alias_count for entity in self.entities)

    @property
    def remarks_spillover_count(
        self,
    ) -> int:
        """Return number of entities with publisher remarks spillover."""

        return sum(entity.has_remarks_spillover for entity in self.entities)


def build_ofac_evidence(
    source_snapshots: tuple[
        SourceSnapshot,
        ...,
    ],
    output_dir: Path,
) -> OfacEvidenceResult:
    """Build canonical OFAC evidence from one complete trusted source set."""

    try:
        evidence_set = OfacEvidenceSet(snapshots=source_snapshots)

        primary_records: list[OfacPrimaryRecord] = []

        address_records: list[OfacAddressRecord] = []

        alias_records: list[OfacAliasRecord] = []

        comment_records: list[OfacCommentRecord] = []

        source_paths: list[Path] = []

        for snapshot in evidence_set.ordered_snapshots:
            source_path = Path(snapshot.destination)

            source_bytes = _read_source_bytes(source_path)

            source_paths.append(source_path)

            if snapshot.source_key in {
                "ofac_sdn_csv",
                "ofac_consolidated_csv",
            }:
                primary_records.extend(
                    parse_ofac_primary_snapshot(
                        source_bytes,
                        snapshot,
                    )
                )

                continue

            if snapshot.source_key in {
                "ofac_sdn_addresses_csv",
                "ofac_consolidated_addresses_csv",
            }:
                address_records.extend(
                    parse_ofac_address_snapshot(
                        source_bytes,
                        snapshot,
                    )
                )

                continue

            if snapshot.source_key in {
                "ofac_sdn_aliases_csv",
                "ofac_consolidated_aliases_csv",
            }:
                alias_records.extend(
                    parse_ofac_alias_snapshot(
                        source_bytes,
                        snapshot,
                    )
                )

                continue

            if snapshot.source_key in {
                "ofac_sdn_comments_csv",
                "ofac_consolidated_comments_csv",
            }:
                comment_records.extend(
                    parse_ofac_comment_snapshot(
                        source_bytes,
                        snapshot,
                    )
                )

                continue

            raise OfacWorkflowError(
                "Complete OFAC evidence set contained "
                "an unsupported source identity: "
                f"{snapshot.source_key!r}."
            )

        entities = build_ofac_entity_evidence(
            tuple(primary_records),
            tuple(address_records),
            tuple(alias_records),
            tuple(comment_records),
        )

        csv_path = output_dir / OFAC_CSV_FILENAME

        json_path = output_dir / OFAC_JSON_FILENAME

        write_ofac_csv(
            evidence_set,
            entities,
            csv_path,
        )

        write_ofac_json(
            evidence_set,
            entities,
            json_path,
        )

    except (
        OSError,
        ValidationError,
        OfacParseError,
        OfacRelationParseError,
        OfacCommentParseError,
        OfacAggregationError,
        OfacExportError,
    ) as exc:
        raise OfacWorkflowError(
            f"Trusted OFAC source evidence could not be built safely: {exc}"
        ) from exc

    return OfacEvidenceResult(
        source_paths=tuple(source_paths),
        csv_path=csv_path,
        json_path=json_path,
        evidence_set=evidence_set,
        entities=entities,
    )


def _read_source_bytes(
    source_path: Path,
) -> bytes:
    """Read the exact trusted artifact represented by one SourceSnapshot."""

    try:
        return source_path.read_bytes()

    except OSError as exc:
        raise OfacWorkflowError(
            f"Trusted OFAC source artifact could not be read: {source_path}."
        ) from exc
