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
        (":info", ParsedCommand(name="info")),
        (":hide-info", ParsedCommand(name="hide-info")),
        (":theme", ParsedCommand(name="theme")),
        (":theme nord", ParsedCommand(name="theme", argument="nord")),
        (":svc", ParsedCommand(name="svc")),
        (":ns airflow", ParsedCommand(name="ns", argument="airflow")),
        (":ctx prod", ParsedCommand(name="ctx", argument="prod")),
        # Aliases
        (":delete", ParsedCommand(name="del")),
        (":services", ParsedCommand(name="svc")),
        (":statefulsets", ParsedCommand(name="sts")),
        (":deployments", ParsedCommand(name="deploy")),
        (":namespace", ParsedCommand(name="ns")),
        (":namespace airflow", ParsedCommand(name="ns", argument="airflow")),
    ],
)
def test_parse_command_supports_current_command_set(raw: str, expected: ParsedCommand) -> None:
    assert parse_command(raw) == expected


@pytest.mark.parametrize("raw", ["", ":", ":unknown", ":pods extra"])
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
                "back",
                "config",
                "containers",
                "contexts",
                "del",
                "delete",
                "deploy",
                "deployments",
                "events",
                "help",
                "hide-info",
                "info",
                "keys",
                "logs",
                "namespace",
                "namespaces",
                "ns",
                "pods",
                "pvc",
                "refresh",
                "restart",
                "secrets",
                "services",
                "statefulsets",
                "sts",
                "svc",
                "theme",
                "ctx",
            ],
        ),
        ("co", ["config", "containers", "contexts"]),
        ("de", ["del", "delete", "deploy", "deployments"]),
        ("ev", ["events"]),
        ("in", ["info"]),
        ("lo", ["logs"]),
        ("pv", ["pvc"]),
        ("re", ["refresh", "restart"]),
        ("sec", ["secrets"]),
        ("st", ["statefulsets", "sts"]),
        ("sv", ["svc"]),
        ("ns ", ["ns", "ns airflow", "ns billing"]),
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
