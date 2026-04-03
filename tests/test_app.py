import pytest
from textual.containers import Vertical
from textual.widgets import Button, DataTable, Input, Log, Static

from kuno.app import AboutScreen, KunoApp, LogsScreen
from kuno.k8s.config import UnknownContextError
from kuno.models import (
    ContainerSummary,
    ContextSummary,
    DeploymentSummary,
    ExplorerView,
    NamespaceSummary,
    PodSummary,
    PvcSummary,
    SecretSummary,
    ServiceSummary,
    StartupConfig,
    StatefulSetSummary,
)


@pytest.mark.asyncio
async def test_app_starts_in_contexts_view(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr(
        "kuno.app.load_context_summaries",
        lambda: [
            ContextSummary(
                name="prod",
                cluster="prod-cluster",
                user="prod-user",
                namespace="payments",
                current="*",
            )
        ],
    )

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.CONTEXTS
        assert table_title.content == "Contexts"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_selecting_context_opens_namespaces(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr(
        "kuno.app.load_context_summaries",
        lambda: [
            ContextSummary(
                name="prod",
                cluster="prod-cluster",
                user="prod-user",
                namespace="payments",
                current="*",
            )
        ],
    )

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    async def fake_list_namespace_summaries(
        kube_client: FakeKubeClient, *, current_namespace: str | None
    ) -> list[NamespaceSummary]:
        assert current_namespace == "payments"
        return [NamespaceSummary(name="payments", status="Active", age="1h", current="*")]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)
    monkeypatch.setattr("kuno.app.list_namespace_summaries", fake_list_namespace_summaries)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        assert app.current_view is ExplorerView.NAMESPACES
        assert table_title.content == "Namespaces"


@pytest.mark.asyncio
async def test_app_selecting_namespace_opens_pods(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr(
        "kuno.app.load_context_summaries",
        lambda: [
            ContextSummary(
                name="prod",
                cluster="prod-cluster",
                user="prod-user",
                namespace="payments",
                current="*",
            )
        ],
    )

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    async def fake_list_namespace_summaries(
        kube_client: FakeKubeClient, *, current_namespace: str | None
    ) -> list[NamespaceSummary]:
        return [NamespaceSummary(name="payments", status="Active", age="1h", current="*")]

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
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

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)
    monkeypatch.setattr("kuno.app.list_namespace_summaries", fake_list_namespace_summaries)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.PODS
        assert table_title.content == "Pods"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_selecting_pod_opens_containers(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

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
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api,sidecar",
                cpu="350m",
                memory="192Mi",
            )
        ]

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        assert pod_name == "api-1"
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.CONTAINERS
        assert app.container_pod_name == "api-1"
        assert table_title.content == "Containers (api-1)"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_can_go_back_from_containers_to_pods(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

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

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_view is ExplorerView.CONTAINERS
        assert app.query_one("#back-button", Button).display is True
        app.action_go_back()
        await pilot.pause()
        assert app.current_view is ExplorerView.PODS


@pytest.mark.asyncio
async def test_app_can_go_back_from_pods_to_namespaces(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr(
        "kuno.app.load_context_summaries",
        lambda: [
            ContextSummary(
                name="prod",
                cluster="prod-cluster",
                user="prod-user",
                namespace="payments",
                current="*",
            )
        ],
    )

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    async def fake_list_namespace_summaries(
        kube_client: FakeKubeClient, *, current_namespace: str | None
    ) -> list[NamespaceSummary]:
        return [NamespaceSummary(name="payments", status="Active", age="1h", current="*")]

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
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

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)
    monkeypatch.setattr("kuno.app.list_namespace_summaries", fake_list_namespace_summaries)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_view is ExplorerView.PODS
        app.action_go_back()
        await pilot.pause()
        assert app.current_view is ExplorerView.NAMESPACES


@pytest.mark.asyncio
async def test_app_renders_container_details(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

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
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api",
                cpu="250m",
                memory="128Mi",
            )
        ]

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=1,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "container\nname: api\npod: api-1\nready: yes\nstate: Running\nrestarts: 1\nimage: ghcr.io/example/api:1.0.0\ncpu: 250m\nmemory: 128Mi"
        )


@pytest.mark.asyncio
async def test_app_delete_command_opens_confirmation_for_pod(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

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

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("del")
        await pilot.pause()
        confirm_title = app.screen.query_one("#confirm-title", Static)
        assert str(confirm_title.content) == "Delete resource"


@pytest.mark.asyncio
async def test_app_restart_command_opens_confirmation_for_deployment(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_deployments(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[DeploymentSummary]:
        return [
            DeploymentSummary(
                name="api",
                ready="1/1",
                up_to_date=1,
                available=1,
                age="1m",
                containers="api",
                cpu="100m",
                memory="64Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.DEPLOYMENTS

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("restart")
        await pilot.pause()
        confirm_title = app.screen.query_one("#confirm-title", Static)
        assert str(confirm_title.content) == "Restart resource"


@pytest.mark.asyncio
async def test_app_opens_logs_from_selected_pod(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

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

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        assert isinstance(app.screen, LogsScreen)


@pytest.mark.asyncio
async def test_app_opens_logs_from_selected_container(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.CONTAINERS
    app.container_pod_name = "api-1"

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_current_view()
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        assert isinstance(app.screen, LogsScreen)


@pytest.mark.asyncio
async def test_logs_screen_filters_lines(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    async def fake_read_pod_logs(
        kube_client,
        namespace: str,
        pod_name: str,
        *,
        container_name: str | None = None,
        tail_lines: int = 500,
        since_seconds: int | None = None,
        timestamps: bool = False,
    ) -> str:
        assert namespace == "payments"
        assert pod_name == "api-1"
        assert container_name == "api"
        assert tail_lines == 500
        assert since_seconds is None
        assert timestamps is False
        return "info ready\nerror failed\ninfo steady"

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)
    monkeypatch.setattr("kuno.app.read_pod_logs", fake_read_pod_logs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.CONTAINERS
    app.container_pod_name = "api-1"

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_current_view()
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        assert isinstance(app.screen, LogsScreen)
        log_filter = app.screen.query_one("#logs-filter", Input)
        output = app.screen.query_one("#logs-output", Log)
        log_filter.value = "error"
        await pilot.pause()
        assert output.line_count == 1


@pytest.mark.asyncio
async def test_logs_screen_toggles_timestamps_and_wrap(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    calls: list[bool] = []

    async def fake_read_pod_logs(
        kube_client,
        namespace: str,
        pod_name: str,
        *,
        container_name: str | None = None,
        tail_lines: int = 500,
        since_seconds: int | None = None,
        timestamps: bool = False,
    ) -> str:
        calls.append(timestamps)
        return "short line\nvery long line that should wrap when wrapping is enabled in the screen"

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)
    monkeypatch.setattr("kuno.app.read_pod_logs", fake_read_pod_logs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.CONTAINERS
    app.container_pod_name = "api-1"

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_current_view()
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        assert isinstance(app.screen, LogsScreen)
        app.screen.action_toggle_wrap()
        app.screen.action_toggle_timestamps()
        await pilot.pause()
        assert app.screen.wrap_enabled is True
        assert app.screen.timestamps_enabled is True
        title = app.screen.query_one("#logs-title", Static)
        assert "timestamps: on [t]" in str(title.content)


@pytest.mark.asyncio
async def test_logs_screen_cycles_modes(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    async def fake_read_pod_logs(
        kube_client,
        namespace: str,
        pod_name: str,
        *,
        container_name: str | None = None,
        tail_lines: int = 500,
        since_seconds: int | None = None,
        timestamps: bool = False,
    ) -> str:
        return '{"level":"info","message":"ready"}'

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)
    monkeypatch.setattr("kuno.app.read_pod_logs", fake_read_pod_logs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.CONTAINERS
    app.container_pod_name = "api-1"

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_current_view()
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        assert isinstance(app.screen, LogsScreen)
        screen = app.screen
        title = screen.query_one("#logs-title", Static)
        assert "mode: raw [m]" in str(title.content)
        screen.action_cycle_mode()
        await pilot.pause()
        assert "mode: pretty [m]" in str(title.content)
        screen.action_cycle_mode()
        await pilot.pause()
        assert "mode: structured [m]" in str(title.content)


@pytest.mark.asyncio
async def test_logs_screen_refetches_with_since(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    calls: list[int | None] = []

    async def fake_read_pod_logs(
        kube_client,
        namespace: str,
        pod_name: str,
        *,
        container_name: str | None = None,
        tail_lines: int = 500,
        since_seconds: int | None = None,
        timestamps: bool = False,
    ) -> str:
        calls.append(since_seconds)
        return "line-1"

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_pod_containers(
        kube_client: FakeKubeClient, namespace: str, pod_name: str
    ) -> list[ContainerSummary]:
        return [
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=0,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pod_containers", fake_list_pod_containers)
    monkeypatch.setattr("kuno.app.read_pod_logs", fake_read_pod_logs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.CONTAINERS
    app.container_pod_name = "api-1"

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_current_view()
        await pilot.pause()
        app.execute_command("logs")
        await pilot.pause()
        since_input = app.screen.query_one("#logs-since", Input)
        since_input.focus()
        since_input.value = "5m"
        await pilot.press("enter")
        await pilot.pause()
        assert calls[-1] == 300


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
    app.current_view = ExplorerView.PODS

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
    app.current_view = ExplorerView.PODS

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
    app.current_view = ExplorerView.PODS

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
async def test_app_switches_to_statefulsets_view(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [
            StatefulSetSummary(
                name="postgres",
                ready="2/3",
                updated=2,
                current=3,
                age="1h",
                containers="postgres",
                cpu="500m",
                memory="1Gi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("sts")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        details_title = app.query_one("#details-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.STATEFULSETS
        assert table_title.content == "StatefulSets"
        assert details_title.content == "StatefulSet Details"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_renders_statefulset_details(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return [
            StatefulSetSummary(
                name="postgres",
                ready="2/3",
                updated=2,
                current=3,
                age="1h",
                containers="postgres",
                cpu="500m",
                memory="1Gi",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("sts")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "statefulset\nname: postgres\nready: 2/3\nupdated: 2\ncurrent: 3\nage: 1h\ncontainers: postgres\ncpu: 500m\nmemory: 1Gi"
        )


@pytest.mark.asyncio
async def test_app_switches_to_services_view(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [
            ServiceSummary(
                name="api",
                type="ClusterIP",
                cluster_ip="10.0.0.1",
                ports="80/TCP,443/TCP",
                age="1h",
                selector="app=api,tier=backend",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("svc")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        details_title = app.query_one("#details-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.SERVICES
        assert table_title.content == "Services"
        assert details_title.content == "Service Details"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_renders_service_details(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        return [
            ServiceSummary(
                name="api",
                type="ClusterIP",
                cluster_ip="10.0.0.1",
                ports="80/TCP,443/TCP",
                age="1h",
                selector="app=api,tier=backend",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("svc")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "service\nname: api\ntype: ClusterIP\ncluster-ip: 10.0.0.1\nports: 80/TCP,443/TCP\nage: 1h\nselector: app=api,tier=backend"
        )


@pytest.mark.asyncio
async def test_app_switches_to_pvc_view(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        return []

    async def fake_list_pvcs(kube_client: FakeKubeClient, namespace: str) -> list[PvcSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [
            PvcSummary(
                name="data-postgres-0",
                status="Bound",
                volume="pvc-123",
                capacity="10Gi",
                access="ReadWriteOnce",
                storage_class="fast-ssd",
                age="1h",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)
    monkeypatch.setattr("kuno.app.list_pvcs", fake_list_pvcs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("pvc")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        details_title = app.query_one("#details-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.PVC
        assert table_title.content == "PVC"
        assert details_title.content == "PVC Details"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_renders_pvc_details(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        return []

    async def fake_list_pvcs(kube_client: FakeKubeClient, namespace: str) -> list[PvcSummary]:
        return [
            PvcSummary(
                name="data-postgres-0",
                status="Bound",
                volume="pvc-123",
                capacity="10Gi",
                access="ReadWriteOnce",
                storage_class="fast-ssd",
                age="1h",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)
    monkeypatch.setattr("kuno.app.list_pvcs", fake_list_pvcs)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("pvc")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "pvc\nname: data-postgres-0\nstatus: Bound\nvolume: pvc-123\ncapacity: 10Gi\naccess: ReadWriteOnce\nstorage-class: fast-ssd\nage: 1h"
        )


@pytest.mark.asyncio
async def test_app_switches_to_secrets_view(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        return []

    async def fake_list_pvcs(kube_client: FakeKubeClient, namespace: str) -> list[PvcSummary]:
        return []

    async def fake_list_secrets(kube_client: FakeKubeClient, namespace: str) -> list[SecretSummary]:
        assert kube_client.context == "prod"
        assert namespace == "payments"
        return [
            SecretSummary(
                name="app-secrets",
                type="Opaque",
                data_items=2,
                immutable="yes",
                age="1h",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)
    monkeypatch.setattr("kuno.app.list_pvcs", fake_list_pvcs)
    monkeypatch.setattr("kuno.app.list_secrets", fake_list_secrets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("secrets")
        await pilot.pause()
        table_title = app.query_one("#table-title", Static)
        details_title = app.query_one("#details-title", Static)
        pod_table = app.query_one("#pod-table", DataTable)
        assert app.current_view is ExplorerView.SECRETS
        assert table_title.content == "Secrets"
        assert details_title.content == "Secret Details"
        assert pod_table.row_count == 1


@pytest.mark.asyncio
async def test_app_renders_secret_details(monkeypatch) -> None:
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
        return []

    async def fake_list_statefulsets(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[StatefulSetSummary]:
        return []

    async def fake_list_services(
        kube_client: FakeKubeClient, namespace: str
    ) -> list[ServiceSummary]:
        return []

    async def fake_list_pvcs(kube_client: FakeKubeClient, namespace: str) -> list[PvcSummary]:
        return []

    async def fake_list_secrets(kube_client: FakeKubeClient, namespace: str) -> list[SecretSummary]:
        return [
            SecretSummary(
                name="app-secrets",
                type="Opaque",
                data_items=2,
                immutable="yes",
                age="1h",
            )
        ]

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)
    monkeypatch.setattr("kuno.app.list_deployments", fake_list_deployments)
    monkeypatch.setattr("kuno.app.list_statefulsets", fake_list_statefulsets)
    monkeypatch.setattr("kuno.app.list_services", fake_list_services)
    monkeypatch.setattr("kuno.app.list_pvcs", fake_list_pvcs)
    monkeypatch.setattr("kuno.app.list_secrets", fake_list_secrets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.execute_command("secrets")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        pod_details = app.query_one("#pod-details", Static)
        assert (
            pod_details.content
            == "secret\nname: app-secrets\ntype: Opaque\ndata-items: 2\nimmutable: yes\nage: 1h"
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
        assert "Contexts" in titles
        assert "Namespaces" in titles
        assert "Pods" in titles
        assert "Refresh contexts" in titles
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
