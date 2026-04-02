import pytest

from kuno.k8s.config import DEFAULT_NAMESPACE, UnknownContextError, resolve_startup_targets
from kuno.models import StartupConfig


@pytest.fixture
def kube_contexts() -> list[dict[str, object]]:
    return [
        {
            "name": "dev",
            "context": {
                "cluster": "dev-cluster",
                "namespace": "payments",
            },
        },
        {
            "name": "prod",
            "context": {
                "cluster": "prod-cluster",
            },
        },
    ]


def test_resolve_startup_targets_uses_requested_context(
    kube_contexts: list[dict[str, object]],
) -> None:
    resolved = resolve_startup_targets(
        StartupConfig(context="prod"),
        kube_contexts,
        kube_contexts[0],
    )

    assert resolved == StartupConfig(context="prod", namespace=DEFAULT_NAMESPACE)


def test_resolve_startup_targets_uses_cli_namespace(kube_contexts: list[dict[str, object]]) -> None:
    resolved = resolve_startup_targets(
        StartupConfig(namespace="billing"),
        kube_contexts,
        kube_contexts[0],
    )

    assert resolved == StartupConfig(context="dev", namespace="billing")


def test_resolve_startup_targets_uses_context_namespace(
    kube_contexts: list[dict[str, object]],
) -> None:
    resolved = resolve_startup_targets(
        StartupConfig(),
        kube_contexts,
        kube_contexts[0],
    )

    assert resolved == StartupConfig(context="dev", namespace="payments")


def test_resolve_startup_targets_falls_back_to_default_namespace(
    kube_contexts: list[dict[str, object]],
) -> None:
    resolved = resolve_startup_targets(
        StartupConfig(),
        kube_contexts,
        kube_contexts[1],
    )

    assert resolved == StartupConfig(context="prod", namespace=DEFAULT_NAMESPACE)


def test_resolve_startup_targets_rejects_unknown_context(
    kube_contexts: list[dict[str, object]],
) -> None:
    with pytest.raises(UnknownContextError):
        resolve_startup_targets(
            StartupConfig(context="missing"),
            kube_contexts,
            kube_contexts[0],
        )
