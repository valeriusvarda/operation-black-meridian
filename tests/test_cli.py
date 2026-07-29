from typer.testing import CliRunner

from black_meridian.cli import app

runner = CliRunner()


def test_sources_list_command_exposes_approved_registry() -> None:
    result = runner.invoke(app, ["sources", "list"])

    assert result.exit_code == 0, result.output
    assert "ofac_sdn_csv" in result.output
    assert "ofac_consolidated_csv" in result.output
    assert "gleif_lei_records_json" in result.output
    assert "fatf_monitored_jurisdictions_html" in result.output


def test_sources_fetch_rejects_unknown_source() -> None:
    result = runner.invoke(
        app,
        ["sources", "fetch", "unapproved_source"],
    )

    assert result.exit_code == 2
    assert "Unknown source 'unapproved_source'" in result.output
