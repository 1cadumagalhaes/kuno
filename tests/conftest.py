from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_kube_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_list_kube_config_contexts(*, config_file: str | None = None):  # type: ignore[no-untyped-def]
        return (
            [{"name": "prod", "context": {"cluster": "prod-cluster", "namespace": "payments"}}],
            "prod",
        )

    monkeypatch.setattr(
        "kuno.k8s.config.list_kube_config_contexts",
        fake_list_kube_config_contexts,
    )
