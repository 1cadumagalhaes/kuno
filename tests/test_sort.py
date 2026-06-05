"""Tests for DataTable sorting in KunoApp."""

import pytest
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from kuno.app import KunoApp
from kuno.models import ExplorerView, PodSummary, StartupConfig


def _cell_text(value: object) -> str:
    plain = getattr(value, "plain", None)
    return plain if isinstance(plain, str) else str(value)


@pytest.mark.asyncio
async def test_sort_by_age() -> None:
    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS
    app.pods = [
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
        PodSummary(
            name="cache-1",
            ready="1/1",
            status="Running",
            restarts=2,
            age="1d",
            containers="redis",
            cpu="100m",
            memory="64Mi",
        ),
    ]

    # Sort by age ascending (youngest first)
    app._sort_column = "age"
    app._sort_reverse = False
    app._apply_sort()

    names = [p.name for p in app.pods]
    assert names == ["worker-1", "api-1", "cache-1"]


@pytest.mark.asyncio
async def test_sort_by_name() -> None:
    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS
    app.pods = [
        PodSummary(
            name="zebra",
            ready="1/1",
            status="Running",
            restarts=0,
            age="1m",
            containers="api",
            cpu="100m",
            memory="64Mi",
        ),
        PodSummary(
            name="alpha",
            ready="0/1",
            status="Pending",
            restarts=0,
            age="1m",
            containers="api",
            cpu="100m",
            memory="64Mi",
        ),
        PodSummary(
            name="beta",
            ready="1/1",
            status="Running",
            restarts=0,
            age="1m",
            containers="api",
            cpu="100m",
            memory="64Mi",
        ),
    ]

    app._sort_column = "name"
    app._sort_reverse = False
    app._apply_sort()

    names = [p.name for p in app.pods]
    assert names == ["alpha", "beta", "zebra"]


@pytest.mark.asyncio
async def test_sort_cycle() -> None:
    app = KunoApp(StartupConfig(context="prod", namespace="payments"))
    app.current_view = ExplorerView.PODS

    # Start with no sort
    assert app._sort_column is None

    # First cycle: name asc
    app.action_cycle_sort()
    assert app._sort_column == "name"
    assert app._sort_reverse is False

    # Second cycle: status asc
    app.action_cycle_sort()
    assert app._sort_column == "status"
    assert app._sort_reverse is False

    # Third cycle: age asc
    app.action_cycle_sort()
    assert app._sort_column == "age"
    assert app._sort_reverse is False

    # Fourth cycle: age desc (reverse)
    app.action_cycle_sort()
    assert app._sort_column == "age"
    assert app._sort_reverse is True

    # Fifth cycle: back to default (no sort)
    app.action_cycle_sort()
    assert app._sort_column is None
    assert app._sort_reverse is False


@pytest.mark.asyncio
async def test_cycle_sort_rerenders_table_and_title(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["prod"])

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
        return [
            PodSummary(
                name="zebra",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api",
                cpu="100m",
                memory="64Mi",
            ),
            PodSummary(
                name="alpha",
                ready="1/1",
                status="Running",
                restarts=0,
                age="1m",
                containers="api",
                cpu="100m",
                memory="64Mi",
            ),
        ]

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#pod-table", DataTable)
        panel = app.query_one("#pod-panel", Vertical)
        assert _cell_text(table.get_cell_at(Coordinate(0, 0))) == "zebra"

        app.action_cycle_sort()
        await pilot.pause()
        await pilot.pause()

        assert _cell_text(table.get_cell_at(Coordinate(0, 0))) == "alpha"
        assert panel.border_title == "Pods | sort: name asc"


@pytest.mark.asyncio
async def test_ctrl_o_binding_cycles_sort(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)
    monkeypatch.setattr("kuno.app.load_available_context_names", lambda: ["prod"])

    class FakeKubeClient:
        def __init__(self, context: str) -> None:
            self.context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_list_namespaces(kube_client: FakeKubeClient) -> list[str]:
        return ["payments"]

    async def fake_list_pods(kube_client: FakeKubeClient, namespace: str) -> list[PodSummary]:
        return []

    monkeypatch.setattr("kuno.app.KubeClient", FakeKubeClient)
    monkeypatch.setattr("kuno.app.list_namespaces", fake_list_namespaces)
    monkeypatch.setattr("kuno.app.list_pods", fake_list_pods)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test() as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()

        assert app._sort_column == "name"
