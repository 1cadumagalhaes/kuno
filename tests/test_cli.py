import pytest

from kuno.cli import parse_args
from kuno.models import StartupConfig


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
    cfg, debug = parse_args(argv)
    assert cfg == expected
    assert debug is False


def test_parse_args_allows_duplicate_same_value() -> None:
    cfg, debug = parse_args(["-c", "prod", "--context", "prod"])
    assert cfg == StartupConfig(context="prod")
    assert debug is False


def test_parse_args_rejects_conflicting_context_values() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-c", "prod", "--context", "stage"])


def test_parse_args_rejects_conflicting_namespace_values() -> None:
    with pytest.raises(SystemExit):
        parse_args(["-n", "payments", "--namespace", "billing"])
