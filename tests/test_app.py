import pytest
from textual.widgets import Static

from kuno.app import KunoApp
from kuno.k8s.config import UnknownContextError
from kuno.models import PodSummary, StartupConfig


@pytest.mark.asyncio
async def test_app_renders_startup_summary(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [PodSummary(name="api-1", phase="Running")]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        summary = app.query_one("#startup-summary", Static)
        pod_list = app.query_one("#pod-list", Static)
        assert summary.content == "kuno\ncontext: prod\nnamespace: payments"
        assert pod_list.content == "pods\napi-1 [Running]"


@pytest.mark.asyncio
async def test_app_renders_startup_error(monkeypatch) -> None:
    def fake_load_startup_targets(_: StartupConfig) -> StartupConfig:
        raise UnknownContextError("missing")

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test():
        summary = app.query_one("#startup-summary", Static)
        pod_list = app.query_one("#pod-list", Static)
        assert summary.content == "kuno\nerror: missing"
        assert pod_list.content == "pods\n(startup failed)"


@pytest.mark.asyncio
async def test_app_renders_pod_loading_error(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        raise RuntimeError("boom")

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        pod_list = app.query_one("#pod-list", Static)
        assert pod_list.content == "pods\n(error: boom)"
