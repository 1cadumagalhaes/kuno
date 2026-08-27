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


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point kuno's cached state at a per-test temp dir so tests don't
    contaminate the real ~/.cache/kuno/state.json (or each other)."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))
