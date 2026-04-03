import pytest
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static

from kuno.app import AboutScreen, KunoApp
from kuno.k8s.config import UnknownContextError
from kuno.models import DeploymentSummary, ExplorerView, PodSummary, StartupConfig


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
        command_area = app.query_one("#command-area", Vertical)
        command_input = app.query_one("#command-input", Input)
        suggestions = app.query_one("#command-suggestions", Static)
        assert command_area.display is False
        app.action_open_command_bar()
        await pilot.pause()
        assert command_area.display is True
        assert command_input.value == ""
        assert suggestions.display is True


@pytest.mark.asyncio
async def test_app_closes_command_bar(monkeypatch) -> None:
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
        command_area = app.query_one("#command-area", Vertical)
        command_input = app.query_one("#command-input", Input)
        app.action_open_command_bar()
        await pilot.pause()
        app.action_close_command_bar()
        await pilot.pause()
        assert command_area.display is False
        assert command_input.value == ""


@pytest.mark.asyncio
async def test_app_updates_command_suggestions(monkeypatch) -> None:
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
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["dev", "prod"])
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["airflow", "billing"]

    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_command_bar()
        await pilot.pause()
        command_input = app.query_one("#command-input", Input)
        suggestions = app.query_one("#command-suggestions", Static)
        command_input.value = "ns "
        await pilot.pause()
        suggestion_text = str(suggestions.content)
        assert "ns airflow" in suggestion_text
        assert "ns billing" in suggestion_text


@pytest.mark.asyncio
async def test_app_accepts_command_suggestion(monkeypatch) -> None:
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
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["dev", "prod"])
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["airflow", "billing"]

    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_command_bar()
        await pilot.pause()
        command_input = app.query_one("#command-input", Input)
        command_input.value = "re"
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        assert command_input.value == "refresh"


@pytest.mark.asyncio
async def test_app_submits_selected_command_suggestion_with_enter(monkeypatch) -> None:
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

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["airflow", "billing"]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["dev", "prod"])
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_command_bar()
        await pilot.pause()
        command_input = app.query_one("#command-input", Input)
        command_input.value = "re"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.command_bar_visible is False


@pytest.mark.asyncio
async def test_app_opens_about_screen_from_command(monkeypatch) -> None:
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
        app.execute_command("about")
        await pilot.pause()
        assert isinstance(app.screen, AboutScreen)
        about_panel = app.screen.query_one("#about-panel", Static)
        assert "kuno" in str(about_panel.content)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AboutScreen)


@pytest.mark.asyncio
async def test_app_executes_theme_command(monkeypatch) -> None:
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
        app.execute_command("theme nord")
        await pilot.pause()
        assert app.theme == "nord"


@pytest.mark.asyncio
async def test_app_switches_to_deployments_view(monkeypatch) -> None:
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

    async def fake_list_deployments(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[DeploymentSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [
            DeploymentSummary(
                name="api",
                ready="2/3",
                up_to_date=3,
                available=2,
                age="1h",
                containers="api,sidecar",
                cpu="750m",
                memory="384Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("deploy")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        details_title = app.query_one("#details-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.DEPLOYMENTS
        assert table_title.content == "Deployments"
        assert details_title.content == "Deployment Details"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_renders_deployment_details(monkeypatch) -> None:
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

    async def fake_list_deployments(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[DeploymentSummary]:
        return [
            DeploymentSummary(
                name="api",
                ready="2/3",
                up_to_date=3,
                available=2,
                age="1h",
                containers="api,sidecar",
                cpu="750m",
                memory="384Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("deploy")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "deployment\nname: api\nready: 2/3\nup-to-date: 3\navailable: 2\nage: 1h\ncontainers: api,sidecar\ncpu: 750m\nmemory: 384Mi"
        )


@pytest.mark.asyncio
async def test_app_exposes_clean_system_commands(monkeypatch) -> None:
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

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["airflow", "billing"]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["dev", "prod"])
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        titles = [command.title for command in app.get_system_commands(app.screen)]
        assert "About" in titles
        assert "Keys" in titles
        assert "Theme" in titles
        assert "Use context dev" in titles
        assert "Use namespace airflow" in titles
        assert "Pods" in titles
        assert "Refresh pods" in titles
        assert "Quit" in titles
        assert all("Maximize" not in title for title in titles)


@pytest.mark.asyncio
async def test_app_scrolls_command_suggestions(monkeypatch) -> None:
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

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["airflow", "billing", "default", "kube-system", "payments"]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["dev", "prod"])
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_command_bar()
        await pilot.pause()
        command_input = app.query_one("#command-input", Input)
        suggestions = app.query_one("#command-suggestions", Static)
        command_input.value = "ns "
        await pilot.pause()
        await pilot.press("down", "down", "down", "down")
        await pilot.pause()
        suggestion_text = str(suggestions.content)
        assert "ns payments" in suggestion_text
        assert "> ns payments" in suggestion_text


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
        assert summary.content == "kuno\ncontext: prod\nnamespace: billing"
