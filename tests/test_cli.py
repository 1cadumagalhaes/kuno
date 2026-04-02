import pytest

from kuno.cli import StartupConfig, parse_args


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["-c", "prod"], StartupConfig(context="prod")),
        (["--ctx", "prod"], StartupConfig(context="prod")),
        (["--context", "prod"], StartupConfig(context="prod")),
        (["-n", "payments"], StartupConfig(namespace="payments")),
        (["--ns", "payments"], StartupConfig(namespace="payments")),
        (["--namespace", "payments"], StartupConfig(namespace="payments")),
        (
            ["-c", "prod", "--namespace", "payments"],
            StartupConfig(context="prod", namespace="payments"),
        ),
    ],
)
def test_parse_args_supports_aliases(argv: list[str], expected: StartupConfig) -> None:
    assert parse_args(argv) == expected


def test_parse_args_allows_duplicate_same_value() -> None:
    assert parse_args(["-c", "prod", "--context", "prod"]) == StartupConfig(context="prod")


def test_parse_args_rejects_conflicting_context_values() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-c", "prod", "--context", "stage"])


def test_parse_args_rejects_conflicting_namespace_values() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-n", "payments", "--namespace", "billing"])
