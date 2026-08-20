from hashlib import sha256
from pathlib import Path
from typing import Never

import pytest

from black_meridian.data_sources.importer import (
    OperatorImportError,
    import_operator_source,
)
from black_meridian.data_sources.registry import get_source

FATF_SOURCE_KEY = "fatf_monitored_jurisdictions_html"


def test_operator_import_preserves_exact_bytes_and_provenance(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "operator-download.html"

    payload = b"<!doctype html><html><body>official FATF evidence fixture</body></html>"

    incoming.write_bytes(payload)

    destination = tmp_path / "trusted" / source.filename

    snapshot = import_operator_source(
        source,
        incoming,
        destination,
    )

    assert destination.read_bytes() == payload
    assert incoming.read_bytes() == payload

    assert snapshot.source_key == source.key
    assert snapshot.acquisition_method == "operator_import"

    assert snapshot.requested_url == source.url
    assert snapshot.resolved_url == source.url

    assert snapshot.sha256 == sha256(payload).hexdigest()

    assert snapshot.byte_size == len(payload)

    assert snapshot.content_type == "text/html"

    assert snapshot.destination == str(destination)

    assert snapshot.fetched_at.tzinfo is not None

    assert snapshot.fetched_at.utcoffset() is not None

    partial_path = destination.with_name(f".{destination.name}.partial")

    assert not partial_path.exists()


def test_operator_import_atomically_replaces_existing_destination(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"new official source bytes")

    destination = tmp_path / source.filename

    destination.write_bytes(b"old trusted bytes")

    snapshot = import_operator_source(
        source,
        incoming,
        destination,
    )

    assert destination.read_bytes() == b"new official source bytes"

    assert snapshot.sha256 == sha256(b"new official source bytes").hexdigest()


def test_operator_import_rejects_noncanonical_destination_filename(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"official source bytes")

    destination = tmp_path / "unexpected-name.html"

    with pytest.raises(
        OperatorImportError,
        match=("destination filename must match the approved source filename"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()


def test_operator_import_rejects_missing_source(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "missing.html"

    destination = tmp_path / source.filename

    with pytest.raises(
        OperatorImportError,
        match=("does not exist or cannot be resolved"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()


def test_operator_import_rejects_directory_source(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "source-directory"

    incoming.mkdir()

    destination = tmp_path / source.filename

    with pytest.raises(
        OperatorImportError,
        match="must be a regular file",
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()


def test_operator_import_rejects_empty_source_and_cleans_partial(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "empty.html"
    incoming.touch()

    destination = tmp_path / source.filename

    partial_path = destination.with_name(f".{destination.name}.partial")

    with pytest.raises(
        OperatorImportError,
        match="source artifact is empty",
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()
    assert not partial_path.exists()


def test_operator_import_rejects_source_destination_identity(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    source_and_destination = tmp_path / source.filename

    source_and_destination.write_bytes(b"official source bytes")

    with pytest.raises(
        OperatorImportError,
        match=("source and trusted destination must be different files"),
    ):
        import_operator_source(
            source,
            source_and_destination,
            source_and_destination,
        )

    assert source_and_destination.read_bytes() == b"official source bytes"


def test_operator_import_rejects_symbolic_link_destination(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"official source bytes")

    link_target = tmp_path / "link-target.html"

    link_target.write_bytes(b"existing trusted bytes")

    destination = tmp_path / source.filename

    try:
        destination.symlink_to(link_target)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this test environment.")

    with pytest.raises(
        OperatorImportError,
        match=("destination must not be a symbolic link"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert link_target.read_bytes() == b"existing trusted bytes"


def test_operator_import_rejects_symbolic_link_partial_path(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"official source bytes")

    destination = tmp_path / source.filename

    partial_path = destination.with_name(f".{destination.name}.partial")

    partial_target = tmp_path / "partial-target.html"

    partial_target.write_bytes(b"must remain unchanged")

    try:
        partial_path.symlink_to(partial_target)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this test environment.")

    with pytest.raises(
        OperatorImportError,
        match=("temporary path must not be a symbolic link"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()

    assert partial_target.read_bytes() == b"must remain unchanged"


def test_operator_import_rejects_directory_at_partial_path(
    tmp_path: Path,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"official source bytes")

    destination = tmp_path / source.filename

    partial_path = destination.with_name(f".{destination.name}.partial")

    partial_path.mkdir()

    with pytest.raises(
        OperatorImportError,
        match=("temporary path must be a regular file when it already exists"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert not destination.exists()
    assert partial_path.is_dir()


def test_operator_import_failed_atomic_replace_preserves_old_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = get_source(FATF_SOURCE_KEY)

    incoming = tmp_path / "incoming.html"
    incoming.write_bytes(b"new official source bytes")

    destination = tmp_path / source.filename

    destination.write_bytes(b"previous trusted source bytes")

    partial_path = destination.with_name(f".{destination.name}.partial")

    def fail_replace(
        source_path: Path,
        destination_path: Path,
    ) -> Never:
        del source_path
        del destination_path

        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(
        "black_meridian.data_sources.importer.os.replace",
        fail_replace,
    )

    with pytest.raises(
        OperatorImportError,
        match=("could not be imported safely"),
    ):
        import_operator_source(
            source,
            incoming,
            destination,
        )

    assert destination.read_bytes() == b"previous trusted source bytes"

    assert not partial_path.exists()
