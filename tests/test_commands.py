import pytest

from kuno.commands import ParsedCommand, parse_command, suggest_commands


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (":about", ParsedCommand(name="about")),
        (":deploy", ParsedCommand(name="deploy")),
        (":keys", ParsedCommand(name="keys")),
        (":pods", ParsedCommand(name="pods")),
        ("refresh", ParsedCommand(name="refresh")),
        (":details", ParsedCommand(name="details")),
        (":hide-details", ParsedCommand(name="hide-details")),
        (":theme", ParsedCommand(name="theme")),
        (":theme nord", ParsedCommand(name="theme", argument="nord")),
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
        (
            "",
            [
                "about",
                "deploy",
                "keys",
                "pods",
                "refresh",
                "details",
                "hide-details",
                "theme",
                "ns",
                "ctx",
                "help",
            ],
        ),
        ("de", ["deploy", "details"]),
        ("re", ["refresh"]),
        ("ns ", ["ns airflow", "ns billing"]),
        ("ns bi", ["ns billing"]),
        ("ctx p", ["ctx prod"]),
        ("theme n", ["theme nord"]),
    ],
)
def test_suggest_commands_returns_contextual_matches(raw: str, expected: list[str]) -> None:
    assert (
        suggest_commands(
            raw,
            contexts=["dev", "prod"],
            namespaces=["airflow", "billing"],
            themes=["gruvbox", "nord"],
        )
        == expected
    )
