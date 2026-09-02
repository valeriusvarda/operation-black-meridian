"""Operator-facing CLI for trusted OFAC evidence generation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.error import URLError

import typer

from black_meridian.data_sources import (
    SourceSnapshot,
    fetch_source,
    get_source,
    write_snapshot_manifest,
)
from black_meridian.ofac.evidence import (
    OFAC_EVIDENCE_SOURCE_KEYS,
)
from black_meridian.ofac.visualization import (
    OfacVisualizationError,
    build_ofac_visualizations,
)
from black_meridian.ofac.workflow import (
    OfacWorkflowError,
    build_ofac_evidence,
)

ofac_app = typer.Typer(
    help=("Acquire approved OFAC source series and build provenance-bound entity evidence."),
    no_args_is_help=True,
)


@ofac_app.command("refresh")
def refresh_ofac_command(
    source_dir: Annotated[
        Path,
        typer.Option(
            "--source-dir",
            help=("Root directory for trusted OFAC source snapshots."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("data/raw/external"),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help=("Directory for generated OFAC JSON and CSV evidence."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("data/reference/ofac"),
    timeout_seconds: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="HTTP timeout in seconds.",
            min=1.0,
            max=300.0,
        ),
    ] = 60.0,
) -> None:
    """Acquire the complete OFAC legacy series and build validated evidence."""

    snapshots: list[SourceSnapshot] = []

    manifest_paths: list[
        tuple[
            str,
            Path,
        ]
    ] = []

    try:
        for source_key in OFAC_EVIDENCE_SOURCE_KEYS:
            source = get_source(source_key)

            destination = source_dir / source.key / source.filename

            snapshot = fetch_source(
                source,
                destination,
                timeout_seconds=(timeout_seconds),
            )

            manifest_path = write_snapshot_manifest(
                snapshot,
                destination,
            )

            snapshots.append(snapshot)

            manifest_paths.append(
                (
                    source.key,
                    manifest_path,
                )
            )

        evidence = build_ofac_evidence(
            tuple(snapshots),
            output_dir,
        )

    except (
        OSError,
        URLError,
        OfacWorkflowError,
    ) as exc:
        typer.echo(
            f"OFAC refresh failed: {exc}",
            err=True,
        )

        raise typer.Exit(code=1) from exc

    typer.echo("OFAC evidence refresh completed.")

    typer.echo(f"Sources: {evidence.source_count}")

    typer.echo(f"Entities: {evidence.entity_count}")

    typer.echo(f"Addresses: {evidence.address_count}")

    typer.echo(f"Aliases: {evidence.alias_count}")

    typer.echo(f"Remarks spillovers: {evidence.remarks_spillover_count}")

    typer.echo(f"Evidence set SHA-256: {evidence.evidence_set.evidence_set_sha256}")

    typer.echo(f"CSV: {evidence.csv_path}")

    typer.echo(f"JSON: {evidence.json_path}")

    for snapshot in evidence.evidence_set.ordered_snapshots:
        typer.echo(
            "Source "
            f"{snapshot.source_key}: "
            f"{snapshot.byte_size} bytes | "
            f"{snapshot.sha256} | "
            f"{snapshot.acquisition_method} | "
            f"{snapshot.fetched_at.isoformat()}"
        )

    for (
        source_key,
        manifest_path,
    ) in manifest_paths:
        typer.echo(f"Manifest {source_key}: {manifest_path}")


@ofac_app.command("visualize")
def visualize_ofac_command(
    evidence_path: Annotated[
        Path,
        typer.Option(
            "--evidence",
            help=("Deterministic OFAC JSON evidence produced by the trusted workflow."),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = Path("data/reference/ofac/ofac_entities.json"),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help=("Directory for generated OFAC visual evidence artifacts."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("reports/generated/ofac"),
) -> None:
    """Render reproducible visual projections of validated OFAC evidence."""

    try:
        result = build_ofac_visualizations(
            evidence_path,
            output_dir,
        )

    except (
        OSError,
        OfacVisualizationError,
    ) as exc:
        typer.echo(
            f"OFAC visualization failed: {exc}",
            err=True,
        )

        raise typer.Exit(code=1) from exc

    typer.echo("OFAC visualization completed.")

    typer.echo(f"Entities: {result.entity_count}")

    typer.echo(f"Evidence JSON SHA-256: {result.evidence_json_sha256}")

    typer.echo(f"Evidence set SHA-256: {result.evidence_set_sha256}")

    typer.echo(f"Provenance graph: {result.provenance_svg_path}")

    typer.echo(f"Subject composition: {result.subject_svg_path}")

    typer.echo(f"Raw program contexts: {result.program_svg_path}")

    typer.echo(f"Visual manifest: {result.manifest_path}")
