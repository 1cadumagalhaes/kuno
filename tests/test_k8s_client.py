from __future__ import annotations

import pytest

from kuno.k8s.client import KubeClient


class FakeApiClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_kube_client_connects(monkeypatch) -> None:
    fake_api_client = FakeApiClient()

    async def fake_new_client_from_config(
        *, config_file: str | None, context: str
    ) -> FakeApiClient:
        assert config_file is None
        assert context == "prod"
        return fake_api_client

    monkeypatch.setattr("kuno.k8s.client.new_client_from_config", fake_new_client_from_config)

    client = KubeClient(context="prod")
    await client.connect()

    assert client.api_client is fake_api_client
    assert client.core_v1 is not None
    assert client.apps_v1 is not None


@pytest.mark.asyncio
async def test_kube_client_closes(monkeypatch) -> None:
    fake_api_client = FakeApiClient()

    async def fake_new_client_from_config(
        *, config_file: str | None, context: str
    ) -> FakeApiClient:
        assert config_file is None
        assert context == "prod"
        return fake_api_client

    monkeypatch.setattr("kuno.k8s.client.new_client_from_config", fake_new_client_from_config)

    client = KubeClient(context="prod")
    await client.connect()
    await client.close()

    assert fake_api_client.closed is True
    assert client.api_client is None
    assert client.core_v1 is None
    assert client.apps_v1 is None


@pytest.mark.asyncio
async def test_kube_client_context_manager(monkeypatch) -> None:
    fake_api_client = FakeApiClient()

    async def fake_new_client_from_config(
        *, config_file: str | None, context: str
    ) -> FakeApiClient:
        assert config_file is None
        assert context == "prod"
        return fake_api_client

    monkeypatch.setattr("kuno.k8s.client.new_client_from_config", fake_new_client_from_config)

    client: KubeClient | None = None
    async with KubeClient(context="prod") as kube_client:
        client = kube_client
        assert kube_client.api_client is fake_api_client

    assert client is not None
    assert fake_api_client.closed is True


@pytest.mark.asyncio
async def test_kube_client_close_is_safe_without_connecting() -> None:
    client = KubeClient(context="prod")

    await client.close()

    assert client.api_client is None
