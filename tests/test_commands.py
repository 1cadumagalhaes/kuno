import pytest

from kuno.commands import ParsedCommand, parse_command, suggest_commands


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (":about", ParsedCommand(name="about")),
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ["about", "pods", "refresh", "details", "hide-details", "ns", "ctx", "help"]),
        ("re", ["refresh"]),
        ("ns ", ["ns airflow", "ns billing"]),
        ("ns bi", ["ns billing"]),
        ("ctx p", ["ctx prod"]),
    ],
)
def test_suggest_commands_returns_contextual_matches(raw: str, expected: list[str]) -> None:
    assert (
        suggest_commands(raw, contexts=["dev", "prod"], namespaces=["airflow", "billing"])
        == expected
    )
