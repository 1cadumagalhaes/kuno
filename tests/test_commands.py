import pytest

from kuno.commands import ParsedCommand, parse_command


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (":pods", ParsedCommand(name="pods")),
        ("refresh", ParsedCommand(name="refresh")),
        (":details", ParsedCommand(name="details")),
        (":hide-details", ParsedCommand(name="hide-details")),
        (":ns airflow", ParsedCommand(name="ns", argument="airflow")),
        (":ctx prod", ParsedCommand(name="ctx", argument="prod")),
    ],
)
def test_parse_command_supports_current_command_set(raw: str, expected: ParsedCommand) -> None:
    assert parse_command(raw) == expected


@pytest.mark.parametrize("raw", ["", ":", ":unknown", ":ns", ":pods extra"])
def test_parse_command_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_command(raw)
