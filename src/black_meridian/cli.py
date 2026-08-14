"""Command-line interface for Operation Black Meridian."""

from pathlib import Path
from typing import Annotated
from urllib.error import URLError

import typer

from black_meridian.data_sources import (
    fetch_source,
    get_source,
    iter_sources,
    write_snapshot_manifest,
)
from black_meridian.fatf.workflow import (
    FATF_SOURCE_KEY,
    FatfWorkflowError,
    build_fatf_evidence,
)

app = typer.Typer(
    help="Operation Black Meridian financial intelligence toolkit.",
    no_args_is_help=True,
)

sources_app = typer.Typer(
    help="Inspect and retrieve approved external data sources.",
    no_args_is_help=True,
)

fatf_app = typer.Typer(
    help="Build validated FATF jurisdiction-risk evidence.",
    no_args_is_help=True,
)

app.add_typer(
    sources_app,
    name="sources",
)

app.add_typer(
    fatf_app,
    name="fatf",
)


@sources_app.command("list")
def list_sources_command() -> None:
    """List every approved external source in deterministic order."""

    typer.echo("key\tformat\tpublisher\turl")

    for source in iter_sources():
        typer.echo(f"{source.key}\t{source.format}\t{source.publisher}\t{source.url}")


@sources_app.command("fetch")
def fetch_source_command(
    source_key: Annotated[
        str,
        typer.Argument(
            help=("Registry key of the approved source to retrieve."),
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help=("Root directory for external source snapshots."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("data/raw/external"),
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
    """Download one approved source and persist its provenance manifest."""

    try:
        source = get_source(source_key)
    except KeyError:
        available = ", ".join(source.key for source in iter_sources())

        raise typer.BadParameter(
            (f"Unknown source '{source_key}'. Available: {available}"),
            param_hint="source_key",
        ) from None

    destination = output_dir / source.key / source.filename

    try:
        snapshot = fetch_source(
            source,
            destination,
            timeout_seconds=timeout_seconds,
        )

        manifest_path = write_snapshot_manifest(
            snapshot,
            destination,
        )
    except (
        OSError,
        URLError,
    ) as exc:
        typer.echo(
            f"Source retrieval failed: {exc}",
            err=True,
        )

        raise typer.Exit(code=1) from exc

    typer.echo(f"Downloaded: {destination}")

    typer.echo(f"Manifest: {manifest_path}")

    typer.echo(f"Bytes: {snapshot.byte_size}")

    typer.echo(f"SHA-256: {snapshot.sha256}")

    typer.echo(f"Fetched at: {snapshot.fetched_at.isoformat()}")


@fatf_app.command("refresh")
def refresh_fatf_command(
    source_dir: Annotated[
        Path,
        typer.Option(
            "--source-dir",
            help=("Root directory for the trusted acquired FATF source."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("data/raw/external"),
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help=("Directory for generated FATF CSV and JSON evidence."),
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("data/reference"),
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
    """Retrieve the official FATF source and build validated evidence."""

    source = get_source(FATF_SOURCE_KEY)

    source_path = source_dir / source.key / source.filename

    try:
        source_snapshot = fetch_source(
            source,
            source_path,
            timeout_seconds=timeout_seconds,
        )

        manifest_path = write_snapshot_manifest(
            source_snapshot,
            source_path,
        )

        evidence = build_fatf_evidence(
            source_snapshot,
            output_dir,
        )
    except (
        OSError,
        URLError,
        FatfWorkflowError,
    ) as exc:
        typer.echo(
            f"FATF refresh failed: {exc}",
            err=True,
        )

        raise typer.Exit(code=1) from exc

    typer.echo("FATF evidence refresh completed.")

    typer.echo(f"Source: {evidence.source_path}")

    typer.echo(f"Manifest: {manifest_path}")

    typer.echo(f"CSV: {evidence.csv_path}")

    typer.echo(f"JSON: {evidence.json_path}")

    typer.echo(f"Publication date: {evidence.snapshot.publication_date.isoformat()}")

    typer.echo(f"Jurisdictions: {evidence.snapshot.record_count}")

    typer.echo(f"SHA-256: {evidence.snapshot.content_sha256}")

    typer.echo(f"Retrieved at: {evidence.snapshot.retrieved_at.isoformat()}")


if __name__ == "__main__":
    app()
