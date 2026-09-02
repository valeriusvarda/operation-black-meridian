"""Deterministic visual projections of exported OFAC evidence."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any, Final, Literal, Self

import matplotlib
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

matplotlib.use("Agg")

from matplotlib import pyplot as plt  # noqa: E402

from black_meridian.data_sources.models import (
    AcquisitionMethod,
)
from black_meridian.ofac.comments import (
    OfacCommentRecord,
)
from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
    OfacSourceKey,
    OfacSubjectKind,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
    fingerprint_ofac_source_set,
)
from black_meridian.ofac.relations import (
    OfacAddressRecord,
    OfacAliasRecord,
)

OFAC_PROVENANCE_SVG_FILENAME: Final = "ofac_provenance_graph.svg"

OFAC_SUBJECT_SVG_FILENAME: Final = "ofac_subject_composition.svg"

OFAC_PROGRAM_SVG_FILENAME: Final = "ofac_raw_program_contexts.svg"

OFAC_VISUAL_MANIFEST_FILENAME: Final = "ofac_visual_manifest.json"

_VISUAL_SCHEMA_VERSION: Final = 1

_EVIDENCE_SCHEMA_VERSION: Final = 1

_SVG_HASH_SALT: Final = "operation-black-meridian/ofac-visual/v1"

_SUBJECT_ORDER: Final[
    tuple[
        OfacSubjectKind,
        ...,
    ]
] = (
    OfacSubjectKind.INDIVIDUAL,
    OfacSubjectKind.VESSEL,
    OfacSubjectKind.AIRCRAFT,
    OfacSubjectKind.UNSPECIFIED,
)


class OfacVisualizationError(RuntimeError):
    """Raised when OFAC evidence cannot be visualized safely."""


class OfacPortableSourceEvidence(BaseModel):
    """Portable source provenance serialized by the OFAC exporter."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_key: str

    acquisition_method: AcquisitionMethod

    requested_url: AnyHttpUrl

    fetched_at: datetime

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    byte_size: int = Field(ge=1)

    content_type: str | None = None

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone-aware portable provenance."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OFAC visualization source timestamp must be timezone-aware.")

        return value


class OfacVisualizationPrimary(BaseModel):
    """Validate the flat primary representation emitted by the exporter."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    record: OfacPrimaryRecord

    subject_kind: OfacSubjectKind

    @model_validator(mode="before")
    @classmethod
    def unpack_exported_primary(
        cls,
        value: Any,
    ) -> Any:
        """Convert exporter-flat primary JSON into typed internal form."""

        if not isinstance(
            value,
            dict,
        ):
            return value

        payload = dict(value)

        subject_kind = payload.pop(
            "subject_kind",
            None,
        )

        return {
            "record": payload,
            "subject_kind": subject_kind,
        }

    @model_validator(mode="after")
    def validate_subject_kind(
        self,
    ) -> Self:
        """Require exported semantic kind to match raw source type."""

        if self.subject_kind is not self.record.subject_kind:
            raise ValueError(
                "OFAC visualization primary subject_kind does not match source_entity_type_raw."
            )

        return self


class OfacVisualizationEntity(BaseModel):
    """One exported source-scoped OFAC entity evidence occurrence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_record_key: tuple[
        OfacSourceKey,
        str,
    ]

    primary: OfacVisualizationPrimary

    addresses: tuple[
        OfacAddressRecord,
        ...,
    ]

    aliases: tuple[
        OfacAliasRecord,
        ...,
    ]

    comment: OfacCommentRecord | None

    reconstructed_remarks_raw: str

    @model_validator(mode="after")
    def validate_entity_lineage(
        self,
    ) -> Self:
        """Require every relation to point to the exported primary."""

        primary = self.primary.record

        if self.source_record_key != primary.source_record_key:
            raise ValueError(
                "OFAC visualization source_record_key does not match the primary record."
            )

        for address in self.addresses:
            if address.parent_record_key != primary.source_record_key:
                raise ValueError("OFAC visualization address does not point to its primary.")

        for alias in self.aliases:
            if alias.parent_record_key != primary.source_record_key:
                raise ValueError("OFAC visualization alias does not point to its primary.")

        if self.comment is not None and self.comment.parent_record_key != primary.source_record_key:
            raise ValueError("OFAC visualization comment does not point to its primary.")

        expected_remarks = primary.remarks_raw + (
            self.comment.continuation_raw if self.comment is not None else ""
        )

        if self.reconstructed_remarks_raw != expected_remarks:
            raise ValueError(
                "OFAC visualization reconstructed remarks do not match publisher evidence lineage."
            )

        return self


class OfacVisualizationEvidence(BaseModel):
    """Validated portable evidence consumed by the visualization layer."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal[1]

    evidence_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    source_count: int = Field(ge=1)

    entity_count: int = Field(ge=1)

    sources: tuple[
        OfacPortableSourceEvidence,
        ...,
    ]

    entities: tuple[
        OfacVisualizationEntity,
        ...,
    ]

    @model_validator(mode="after")
    def validate_portable_evidence(
        self,
    ) -> Self:
        """Reconcile counts, evidence-set identity, and source digests."""

        if self.schema_version != _EVIDENCE_SCHEMA_VERSION:
            raise ValueError("Unsupported OFAC evidence schema version.")

        if self.source_count != len(self.sources):
            raise ValueError("OFAC visualization source_count does not match serialized sources.")

        if self.entity_count != len(self.entities):
            raise ValueError("OFAC visualization entity_count does not match serialized entities.")

        source_keys = tuple(source.source_key for source in self.sources)

        if frozenset(source_keys) != frozenset(OFAC_EVIDENCE_SOURCE_KEYS):
            raise ValueError(
                "OFAC visualization input does not contain the complete approved source boundary."
            )

        recomputed_fingerprint = fingerprint_ofac_source_set(
            (
                (
                    source.source_key,
                    source.sha256,
                    source.byte_size,
                )
                for source in self.sources
            )
        )

        if recomputed_fingerprint != self.evidence_set_sha256:
            raise ValueError(
                "OFAC visualization evidence-set SHA-256 "
                "does not reconcile with portable source provenance."
            )

        source_sha256_by_key = {source.source_key: source.sha256 for source in self.sources}

        seen_entity_keys: set[
            tuple[
                OfacSourceKey,
                str,
            ]
        ] = set()

        for entity in self.entities:
            if entity.source_record_key in seen_entity_keys:
                raise ValueError(
                    "OFAC visualization input contains duplicate entity source-record identity."
                )

            seen_entity_keys.add(entity.source_record_key)

            primary = entity.primary.record

            _require_source_sha256(
                source_sha256_by_key,
                primary.source_key,
                primary.source_sha256,
            )

            for address in entity.addresses:
                _require_source_sha256(
                    source_sha256_by_key,
                    address.source_key,
                    address.source_sha256,
                )

            for alias in entity.aliases:
                _require_source_sha256(
                    source_sha256_by_key,
                    alias.source_key,
                    alias.source_sha256,
                )

            if entity.comment is not None:
                _require_source_sha256(
                    source_sha256_by_key,
                    entity.comment.source_key,
                    entity.comment.source_sha256,
                )

        return self


@dataclass(
    frozen=True,
    slots=True,
)
class OfacVisualizationMetrics:
    """Deterministic aggregate metrics derived from validated evidence."""

    entity_count: int

    address_count: int

    alias_count: int

    remarks_spillover_count: int

    sdn_entity_count: int

    consolidated_entity_count: int

    subject_counts: tuple[
        tuple[
            str,
            int,
        ],
        ...,
    ]

    raw_program_context_counts: tuple[
        tuple[
            str,
            int,
        ],
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class OfacVisualizationResult:
    """Generated visual artifacts bound to one evidence JSON snapshot."""

    evidence_path: Path

    evidence_json_sha256: str

    evidence_set_sha256: str

    entity_count: int

    provenance_svg_path: Path

    subject_svg_path: Path

    program_svg_path: Path

    manifest_path: Path


def build_ofac_visualizations(
    evidence_path: Path,
    output_dir: Path,
) -> OfacVisualizationResult:
    """Validate exported OFAC evidence and render deterministic SVG artifacts."""

    evidence_bytes = _read_evidence_bytes(evidence_path)

    evidence_json_sha256 = sha256(evidence_bytes).hexdigest()

    evidence = _parse_evidence(evidence_bytes)

    metrics = _derive_metrics(evidence)

    provenance_payload = _render_provenance_svg(
        evidence,
        metrics,
    )

    subject_payload = _render_subject_svg(
        evidence,
        metrics,
    )

    program_payload = _render_program_svg(
        evidence,
        metrics,
    )

    provenance_path = output_dir / OFAC_PROVENANCE_SVG_FILENAME

    subject_path = output_dir / OFAC_SUBJECT_SVG_FILENAME

    program_path = output_dir / OFAC_PROGRAM_SVG_FILENAME

    manifest_path = output_dir / OFAC_VISUAL_MANIFEST_FILENAME

    _write_bytes_atomically(
        provenance_path,
        provenance_payload,
    )

    _write_bytes_atomically(
        subject_path,
        subject_payload,
    )

    _write_bytes_atomically(
        program_path,
        program_payload,
    )

    output_entries = (
        (
            provenance_path.name,
            provenance_payload,
        ),
        (
            subject_path.name,
            subject_payload,
        ),
        (
            program_path.name,
            program_payload,
        ),
    )

    manifest_payload = _serialize_manifest(
        evidence_path=evidence_path,
        evidence_json_sha256=(evidence_json_sha256),
        evidence=evidence,
        metrics=metrics,
        output_entries=(output_entries),
    )

    _write_bytes_atomically(
        manifest_path,
        manifest_payload,
    )

    return OfacVisualizationResult(
        evidence_path=evidence_path,
        evidence_json_sha256=(evidence_json_sha256),
        evidence_set_sha256=(evidence.evidence_set_sha256),
        entity_count=(evidence.entity_count),
        provenance_svg_path=(provenance_path),
        subject_svg_path=(subject_path),
        program_svg_path=(program_path),
        manifest_path=(manifest_path),
    )


def _require_source_sha256(
    expected_by_key: dict[
        str,
        str,
    ],
    source_key: str,
    source_sha256: str,
) -> None:
    """Require record provenance to reconcile with portable sources."""

    expected = expected_by_key.get(source_key)

    if expected is None:
        raise ValueError(f"OFAC visualization record references unknown source {source_key!r}.")

    if expected != source_sha256:
        raise ValueError(
            "OFAC visualization record SHA-256 "
            "does not reconcile with portable source "
            f"{source_key!r}."
        )


def _read_evidence_bytes(
    evidence_path: Path,
) -> bytes:
    """Read exact exported evidence bytes."""

    try:
        return evidence_path.read_bytes()

    except OSError as exc:
        raise OfacVisualizationError(
            f"OFAC visualization evidence could not be read: {evidence_path}."
        ) from exc


def _parse_evidence(
    evidence_bytes: bytes,
) -> OfacVisualizationEvidence:
    """Decode and validate portable exported evidence."""

    try:
        payload = json.loads(evidence_bytes.decode("utf-8"))

        return OfacVisualizationEvidence.model_validate(payload)

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise OfacVisualizationError(
            f"OFAC visualization input failed evidence validation: {exc}"
        ) from exc


def _derive_metrics(
    evidence: OfacVisualizationEvidence,
) -> OfacVisualizationMetrics:
    """Derive source-grounded aggregate counts without entity inference."""

    subject_counter: Counter[str] = Counter()

    program_counter: Counter[str] = Counter()

    sdn_entity_count = 0

    consolidated_entity_count = 0

    address_count = 0

    alias_count = 0

    remarks_spillover_count = 0

    for entity in evidence.entities:
        primary = entity.primary.record

        subject_counter[entity.primary.subject_kind.value] += 1

        program_counter[primary.program_text_raw] += 1

        if primary.source_key == "ofac_sdn_csv":
            sdn_entity_count += 1
        else:
            consolidated_entity_count += 1

        address_count += len(entity.addresses)

        alias_count += len(entity.aliases)

        remarks_spillover_count += int(entity.comment is not None)

    subject_counts = tuple(
        (
            subject_kind.value,
            subject_counter[subject_kind.value],
        )
        for subject_kind in _SUBJECT_ORDER
    )

    raw_program_context_counts = tuple(
        sorted(
            program_counter.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )
    )

    return OfacVisualizationMetrics(
        entity_count=(evidence.entity_count),
        address_count=(address_count),
        alias_count=(alias_count),
        remarks_spillover_count=(remarks_spillover_count),
        sdn_entity_count=(sdn_entity_count),
        consolidated_entity_count=(consolidated_entity_count),
        subject_counts=(subject_counts),
        raw_program_context_counts=(raw_program_context_counts),
    )


def _render_provenance_svg(
    evidence: OfacVisualizationEvidence,
    metrics: OfacVisualizationMetrics,
) -> bytes:
    """Render fixed-layout evidence provenance topology."""

    figure, axis = plt.subplots(
        figsize=(
            14,
            7,
        )
    )

    axis.set_xlim(
        0,
        1,
    )

    axis.set_ylim(
        0,
        1,
    )

    axis.axis("off")

    nodes = (
        (
            0.10,
            0.68,
            (
                "OFAC SDN SERIES\n"
                "4 approved artifacts\n"
                f"{metrics.sdn_entity_count:,} primary records"
            ),
        ),
        (
            0.10,
            0.32,
            (
                "OFAC CONSOLIDATED SERIES\n"
                "4 approved artifacts\n"
                f"{metrics.consolidated_entity_count:,} primary records"
            ),
        ),
        (
            0.39,
            0.50,
            (
                "OFAC EVIDENCE SET\n"
                f"{evidence.evidence_set_sha256[:16]}…\n"
                f"{evidence.source_count} source snapshots"
            ),
        ),
        (
            0.66,
            0.50,
            (
                "ENTITY EVIDENCE\n"
                f"{metrics.entity_count:,} primary\n"
                f"{metrics.address_count:,} addresses\n"
                f"{metrics.alias_count:,} aliases\n"
                f"{metrics.remarks_spillover_count:,} spillovers"
            ),
        ),
        (
            0.90,
            0.66,
            "DETERMINISTIC JSON",
        ),
        (
            0.90,
            0.34,
            "DETERMINISTIC CSV",
        ),
    )

    for (
        x_position,
        y_position,
        label,
    ) in nodes:
        axis.text(
            x_position,
            y_position,
            label,
            ha="center",
            va="center",
            transform=(axis.transAxes),
            bbox={
                "boxstyle": ("round,pad=0.55"),
            },
        )

    arrows = (
        (
            (
                0.18,
                0.66,
            ),
            (
                0.31,
                0.53,
            ),
        ),
        (
            (
                0.18,
                0.34,
            ),
            (
                0.31,
                0.47,
            ),
        ),
        (
            (
                0.47,
                0.50,
            ),
            (
                0.57,
                0.50,
            ),
        ),
        (
            (
                0.75,
                0.52,
            ),
            (
                0.83,
                0.63,
            ),
        ),
        (
            (
                0.75,
                0.48,
            ),
            (
                0.83,
                0.37,
            ),
        ),
    )

    for (
        start,
        end,
    ) in arrows:
        axis.annotate(
            "",
            xy=end,
            xytext=start,
            xycoords="axes fraction",
            textcoords="axes fraction",
            arrowprops={
                "arrowstyle": "->",
            },
        )

    axis.set_title("Operation Black Meridian — OFAC Evidence Provenance")

    return _figure_to_svg_bytes(figure)


def _render_subject_svg(
    evidence: OfacVisualizationEvidence,
    metrics: OfacVisualizationMetrics,
) -> bytes:
    """Render deterministic subject-kind composition."""

    labels = [
        label
        for (
            label,
            _,
        ) in metrics.subject_counts
    ]

    counts = [
        count
        for (
            _,
            count,
        ) in metrics.subject_counts
    ]

    figure, axis = plt.subplots(
        figsize=(
            10,
            6,
        )
    )

    bars = axis.bar(
        labels,
        counts,
    )

    axis.set_title(f"OFAC Subject Composition\nEvidence set {evidence.evidence_set_sha256[:16]}…")

    axis.set_ylabel("Source-scoped primary records")

    for bar, count in zip(
        bars,
        counts,
        strict=True,
    ):
        axis.text(
            (bar.get_x() + bar.get_width() / 2),
            bar.get_height(),
            f"{count:,}",
            ha="center",
            va="bottom",
        )

    figure.tight_layout()

    return _figure_to_svg_bytes(figure)


def _render_program_svg(
    evidence: OfacVisualizationEvidence,
    metrics: OfacVisualizationMetrics,
) -> bytes:
    """Render frequency of exact raw publisher program-context fields."""

    top_contexts = metrics.raw_program_context_counts[:12]

    labels = [
        _display_program_context(context)
        for (
            context,
            _,
        ) in reversed(top_contexts)
    ]

    counts = [
        count
        for (
            _,
            count,
        ) in reversed(top_contexts)
    ]

    figure, axis = plt.subplots(
        figsize=(
            12,
            7,
        )
    )

    axis.barh(
        labels,
        counts,
    )

    axis.set_title(
        "Top Raw OFAC Program Contexts\n"
        "Exact publisher field frequencies — no program normalization\n"
        f"Evidence set {evidence.evidence_set_sha256[:16]}…"
    )

    axis.set_xlabel("Source-scoped primary records")

    figure.tight_layout()

    return _figure_to_svg_bytes(figure)


def _display_program_context(
    value: str,
) -> str:
    """Create a display-only label without changing evidence data."""

    display = value.replace(
        "\n",
        "\\n",
    )

    if len(display) <= 56:
        return display

    return display[:53] + "..."


def _figure_to_svg_bytes(
    figure: Any,
) -> bytes:
    """Render stable SVG metadata under the locked visualization stack."""

    buffer = StringIO()

    with matplotlib.rc_context(
        {
            "svg.hashsalt": (_SVG_HASH_SALT),
            "svg.fonttype": "none",
        }
    ):
        figure.savefig(
            buffer,
            format="svg",
            metadata={
                "Date": None,
            },
        )

    plt.close(figure)

    return buffer.getvalue().encode("utf-8")


def _serialize_manifest(
    *,
    evidence_path: Path,
    evidence_json_sha256: str,
    evidence: OfacVisualizationEvidence,
    metrics: OfacVisualizationMetrics,
    output_entries: tuple[
        tuple[
            str,
            bytes,
        ],
        ...,
    ],
) -> bytes:
    """Serialize deterministic visual provenance manifest."""

    payload = {
        "schema_version": (_VISUAL_SCHEMA_VERSION),
        "source_evidence_filename": (evidence_path.name),
        "evidence_json_sha256": (evidence_json_sha256),
        "evidence_set_sha256": (evidence.evidence_set_sha256),
        "source_count": (evidence.source_count),
        "entity_count": (evidence.entity_count),
        "metrics": {
            "address_count": (metrics.address_count),
            "alias_count": (metrics.alias_count),
            "remarks_spillover_count": (metrics.remarks_spillover_count),
            "sdn_entity_count": (metrics.sdn_entity_count),
            "consolidated_entity_count": (metrics.consolidated_entity_count),
            "subject_counts": dict(metrics.subject_counts),
            "raw_program_context_counts": [
                {
                    "program_text_raw": context,
                    "count": count,
                }
                for (
                    context,
                    count,
                ) in metrics.raw_program_context_counts
            ],
        },
        "outputs": [
            {
                "filename": filename,
                "sha256": sha256(payload_bytes).hexdigest(),
                "byte_size": len(payload_bytes),
            }
            for (
                filename,
                payload_bytes,
            ) in output_entries
        ],
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    return (f"{serialized}\n").encode("utf-8")


def _write_bytes_atomically(
    destination: Path,
    payload: bytes,
) -> Path:
    """Write a generated visualization artifact atomically."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = destination.with_name(f".{destination.name}.partial")

    try:
        with partial_path.open("wb") as output:
            output.write(payload)

            output.flush()

            os.fsync(output.fileno())

        os.replace(
            partial_path,
            destination,
        )

    except Exception:
        partial_path.unlink(missing_ok=True)

        raise

    return destination
