"""Controlled operator-assisted acquisition for approved external sources."""

import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from black_meridian.data_sources.models import (
    DataSource,
    SourceFormat,
    SourceSnapshot,
)

_CHUNK_SIZE = 1024 * 1024

_CONTENT_TYPES: dict[SourceFormat, str] = {
    "csv": "text/csv",
    "html": "text/html",
    "json": "application/json",
    "xml": "application/xml",
}


class OperatorImportError(RuntimeError):
    """Raised when an operator-provided source cannot be imported safely."""


def import_operator_source(
    source: DataSource,
    source_path: Path,
    destination: Path,
) -> SourceSnapshot:
    """Import an operator-provided official-source artifact with provenance."""

    if destination.name != source.filename:
        raise OperatorImportError(
            "Operator-import destination filename must match the "
            f"approved source filename: {source.filename!r}."
        )

    source_resolved = _resolve_source_file(source_path)

    partial_path = destination.with_name(f".{destination.name}.partial")

    _validate_destination_paths(
        source_resolved,
        destination,
        partial_path,
    )

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise OperatorImportError(
            "Operator-import destination directory could not be prepared."
        ) from exc

    digest = sha256()
    byte_size = 0

    try:
        with source_resolved.open("rb") as input_stream, partial_path.open("wb") as output_stream:
            while True:
                chunk = input_stream.read(_CHUNK_SIZE)

                if not chunk:
                    break

                output_stream.write(chunk)

                digest.update(chunk)

                byte_size += len(chunk)

            if byte_size == 0:
                raise OperatorImportError("Operator-provided source artifact is empty.")

            output_stream.flush()

            os.fsync(output_stream.fileno())

        os.replace(
            partial_path,
            destination,
        )

    except OperatorImportError:
        partial_path.unlink(missing_ok=True)

        raise

    except OSError as exc:
        partial_path.unlink(missing_ok=True)

        raise OperatorImportError(
            "Operator-provided source artifact could not be imported safely."
        ) from exc

    return SourceSnapshot(
        source_key=source.key,
        acquisition_method="operator_import",
        requested_url=source.url,
        resolved_url=source.url,
        fetched_at=datetime.now(UTC),
        sha256=digest.hexdigest(),
        byte_size=byte_size,
        content_type=_CONTENT_TYPES[source.format],
        destination=str(destination),
    )


def _resolve_source_file(
    source_path: Path,
) -> Path:
    """Resolve and validate the operator-provided source artifact."""

    try:
        source_resolved = source_path.resolve(strict=True)
    except OSError as exc:
        raise OperatorImportError(
            "Operator-provided source artifact does not exist or cannot be resolved."
        ) from exc

    if not source_resolved.is_file():
        raise OperatorImportError("Operator-provided source artifact must be a regular file.")

    return source_resolved


def _validate_destination_paths(
    source_resolved: Path,
    destination: Path,
    partial_path: Path,
) -> None:
    """Reject unsafe source, destination, and temporary-path relationships."""

    if destination.is_symlink():
        raise OperatorImportError("Operator-import destination must not be a symbolic link.")

    if partial_path.is_symlink():
        raise OperatorImportError("Operator-import temporary path must not be a symbolic link.")

    try:
        destination_resolved = destination.resolve(strict=False)

        partial_resolved = partial_path.resolve(strict=False)
    except OSError as exc:
        raise OperatorImportError(
            "Operator-import destination paths could not be resolved safely."
        ) from exc

    if source_resolved == destination_resolved:
        raise OperatorImportError(
            "Operator-provided source and trusted destination must be different files."
        )

    if source_resolved == partial_resolved:
        raise OperatorImportError(
            "Operator-provided source must not collide with the temporary import path."
        )

    if destination.exists() and not destination.is_file():
        raise OperatorImportError(
            "Operator-import destination must be a regular file when it already exists."
        )

    if partial_path.exists() and not partial_path.is_file():
        raise OperatorImportError(
            "Operator-import temporary path must be a regular file when it already exists."
        )
