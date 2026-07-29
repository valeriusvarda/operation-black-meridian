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

app = typer.Typer(
    help="Operation Black Meridian financial intelligence toolkit.",
    no_args_is_help=True,
)

sources_app = typer.Typer(
    help="Inspect and retrieve approved external data sources.",
    no_args_is_help=True,
)

app.add_typer(sources_app, name="sources")


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
        typer.Argument(help="Registry key of the approved source to retrieve."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Root directory for external source snapshots.",
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
            f"Unknown source '{source_key}'. Available: {available}",
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
    except (OSError, URLError) as exc:
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


if __name__ == "__main__":
    app()
