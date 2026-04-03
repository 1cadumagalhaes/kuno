import pytest
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static

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
        return [
            PodSummary(
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=2,
                age="5m",
                containers="api",
                cpu="500m",
                memory="256Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        summary = app.query_one("#startup-summary", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        details_panel = app.query_one("#details-panel", Vertical)
        pod_details = app.query_one("#pod-details", Static)
        assert summary.content == "kuno\ncontext: prod\nnamespace: payments"
        assert pod_table.row_count == 1
        assert details_panel.display is False
        assert (
            pod_details.content
            == "pod\nname: api-1\nready: 1/1\nstatus: Running\nrestarts: 2\nage: 5m\ncontainers: api\ncpu: 500m\nmemory: 256Mi"
        )


@pytest.mark.asyncio
async def test_app_renders_startup_error(monkeypatch) -> None:
    def fake_load_startup_targets(_: StartupConfig) -> StartupConfig:
        raise UnknownContextError("missing")

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test():
        summary = app.query_one("#startup-summary", Static)
        pod_details = app.query_one("#pod-details", Static)
        assert summary.content == "kuno\nerror: missing"
        assert pod_details.content == "pod\n(startup failed)"


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
        pod_table = app.query_one("#pod-table", DataTable)
        pod_details = app.query_one("#pod-details", Static)
        assert pod_table.row_count == 0
        assert pod_details.content == "pod\n(error: boom)"


@pytest.mark.asyncio
async def test_app_updates_details_for_highlighted_pod(monkeypatch) -> None:
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
        return [
            PodSummary(
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=1,
                age="5m",
                containers="api",
                cpu="500m",
                memory="256Mi",
            ),
            PodSummary(
                name="worker-1",
                ready="0/1",
                status="Pending",
                restarts=0,
                age="1m",
                containers="worker,sidecar",
                cpu="250m",
                memory="128Mi",
            ),
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        pod_table = app.query_one("#pod-table", DataTable)
        details_panel = app.query_one("#details-panel", Vertical)
        pod_details = app.query_one("#pod-details", Static)
        await pilot.press("d")
        await pilot.pause()
        assert details_panel.display is True
        pod_table.focus()
        await pilot.press("down")
        await pilot.pause()
        assert (
            pod_details.content
            == "pod\nname: worker-1\nready: 0/1\nstatus: Pending\nrestarts: 0\nage: 1m\ncontainers: worker,sidecar\ncpu: 250m\nmemory: 128Mi"
        )


@pytest.mark.asyncio
async def test_app_toggles_details_panel(monkeypatch) -> None:
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
        return [
            PodSummary(
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api",
                cpu="100m",
                memory="64Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        details_panel = app.query_one("#details-panel", Vertical)
        assert details_panel.display is False
        await pilot.press("d")
        await pilot.pause()
        assert details_panel.display is True
        await pilot.press("d")
        await pilot.pause()
        assert details_panel.display is False


@pytest.mark.asyncio
async def test_app_opens_command_bar(monkeypatch) -> None:
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
        return []

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        command_input = app.query_one("#command-input", Input)
        assert command_input.display is False
        app.action_open_command_bar()
        await pilot.pause()
        assert command_input.display is True
        assert command_input.value == ":"


@pytest.mark.asyncio
async def test_app_executes_namespace_command(monkeypatch) -> None:
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
        return [
            PodSummary(
                name=f"{namespace}-api",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api",
                cpu="100m",
                memory="64Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command(":ns billing")
        await pilot.pause()
        summary = app.query_one("#startup-summary", Static)
        status = app.query_one("#command-status", Static)
        assert summary.content == "kuno\ncontext: prod\nnamespace: billing"
        assert status.content == "Switched namespace to billing"


@pytest.mark.asyncio
async def test_app_executes_invalid_command(monkeypatch) -> None:
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
        return []

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command(":unknown")
        await pilot.pause()
        status = app.query_one("#command-status", Static)
        assert status.content == "Unknown command: unknown"
