from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from kuno.k8s.client import KubeClient
from kuno.k8s.config import UnknownContextError, load_startup_targets
from kuno.k8s.resources import list_pods, render_pod_details
from kuno.models import PodSummary, StartupConfig


class KunoApp(App[None]):
    CSS_PATH = "app.tcss"

    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.startup_config = startup_config
        self.pods: list[PodSummary] = []
        self.resolved_startup_config: StartupConfig | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), id="startup-summary")
        with Horizontal(id="explorer"):
            with Vertical(id="pod-panel"):
                yield Static("Pods", classes="panel-title")
                yield DataTable(id="pod-table")
            with Vertical(id="details-panel"):
                yield Static("Details", classes="panel-title")
                yield Static("pod\n(loading)", id="pod-details")

    def on_mount(self) -> None:
        summary = self.query_one("#startup-summary", Static)
        pod_table = self.query_one("#pod-table", DataTable)
        pod_details = self.query_one("#pod-details", Static)
        pod_table.cursor_type = "row"
        pod_table.zebra_stripes = True
        pod_table.add_columns("Name", "Phase")
        try:
            self.resolved_startup_config = load_startup_targets(self.startup_config)
        except UnknownContextError as error:
            summary.update(f"kuno\nerror: {error}")
            pod_details.update("pod\n(startup failed)")
            return

        summary.update(self._summary_text())
        self.load_pods()

    @work(exclusive=True)
    async def load_pods(self) -> None:
        pod_details = self.query_one("#pod-details", Static)
        if self.resolved_startup_config is None:
            pod_details.update("pod\n(startup not resolved)")
            return

        context = self.resolved_startup_config.context
        namespace = self.resolved_startup_config.namespace
        if context is None or namespace is None:
            pod_details.update("pod\n(startup not resolved)")
            return

        try:
            async with KubeClient(context=context) as kube_client:
                pods = await list_pods(kube_client, namespace)
        except Exception as error:
            self.pods = []
            await self._render_pod_table()
            pod_details.update(f"pod\n(error: {error})")
            return

        self.pods = pods
        await self._render_pod_table()
        if self.pods:
            self._update_pod_details(0)
        else:
            pod_details.update("pod\n(no pods found)")

    async def _render_pod_table(self) -> None:
        pod_table = self.query_one("#pod-table", DataTable)
        pod_table.clear()
        for pod in self.pods:
            pod_table.add_row(pod.name, pod.phase, key=pod.name)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "pod-table":
            return

        self._update_pod_details(event.cursor_row)

    def _update_pod_details(self, index: int | None) -> None:
        pod_details = self.query_one("#pod-details", Static)
        if index is None or index >= len(self.pods):
            pod_details.update("pod\n(no pod selected)")
            return

        pod_details.update(render_pod_details(self.pods[index]))

    def _summary_text(self) -> str:
        startup_config = self.resolved_startup_config or self.startup_config
        context = startup_config.context or "auto"
        namespace = startup_config.namespace or "auto"
        return f"kuno\ncontext: {context}\nnamespace: {namespace}"
