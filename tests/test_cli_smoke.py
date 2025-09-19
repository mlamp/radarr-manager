from typer.testing import CliRunner

from radarr_manager import __version__
from radarr_manager.cli.__main__ import app


runner = CliRunner()


def test_version_command_outputs_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
