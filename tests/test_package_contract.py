from importlib.metadata import version

import black_meridian


def test_public_version_matches_distribution_metadata() -> None:
    assert black_meridian.__version__ == version("operation-black-meridian")


def test_public_api_exports_version() -> None:
    assert "__version__" in black_meridian.__all__
