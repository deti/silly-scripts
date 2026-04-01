"""Tests for the hello_world CLI command."""

from click.testing import CliRunner

from silly_scripts.cli.hello_world import main


def test_default_greeting() -> None:
    """Test default output contains Hello, World!."""
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_name_option() -> None:
    """Test --name Alice outputs Hello, Alice!."""
    runner = CliRunner()
    result = runner.invoke(main, ["--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output


def test_name_short_option() -> None:
    """Test -n short option works the same as --name."""
    runner = CliRunner()
    result = runner.invoke(main, ["-n", "Bob"])
    assert result.exit_code == 0
    assert "Hello, Bob!" in result.output


def test_help_option() -> None:
    """Test --help shows command documentation."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Hello World" in result.output


def test_empty_name_uses_default() -> None:
    """Test that passing an empty string for --name uses default greeting."""
    runner = CliRunner()
    result = runner.invoke(main, ["--name", ""])
    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_module_has_expected_attributes() -> None:
    """Test that the module has the expected main function."""
    import silly_scripts.cli.hello_world  # noqa: PLC0415

    assert hasattr(silly_scripts.cli.hello_world, "main")
    assert callable(silly_scripts.cli.hello_world.main)
