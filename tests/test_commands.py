import pytest

from kuno.commands import ParsedCommand, parse_command, suggest_commands


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (":about", ParsedCommand(name="about")),
        (":containers", ParsedCommand(name="containers")),
        (":deploy", ParsedCommand(name="deploy")),
        (":keys", ParsedCommand(name="keys")),
        (":logs", ParsedCommand(name="logs")),
        (":pods", ParsedCommand(name="pods")),
        (":pvc", ParsedCommand(name="pvc")),
        ("refresh", ParsedCommand(name="refresh")),
        (":secrets", ParsedCommand(name="secrets")),
        (":sts", ParsedCommand(name="sts")),
        (":details", ParsedCommand(name="details")),
        (":hide-details", ParsedCommand(name="hide-details")),
        (":theme", ParsedCommand(name="theme")),
        (":theme nord", ParsedCommand(name="theme", argument="nord")),
        (":svc", ParsedCommand(name="svc")),
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
                "containers",
                "contexts",
                "del",
                "deploy",
                "keys",
                "logs",
                "namespaces",
                "pods",
                "pvc",
                "refresh",
                "secrets",
                "svc",
                "sts",
                "details",
                "hide-details",
                "restart",
                "theme",
                "ns",
                "ctx",
                "help",
            ],
        ),
        ("co", ["containers", "contexts"]),
        ("de", ["del", "deploy", "details"]),
        ("lo", ["logs"]),
        ("pv", ["pvc"]),
        ("re", ["refresh", "restart"]),
        ("sec", ["secrets"]),
        ("st", ["sts"]),
        ("sv", ["svc"]),
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
