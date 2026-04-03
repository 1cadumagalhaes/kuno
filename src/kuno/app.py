from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import ListItem, ListView, Static

from kuno.k8s.client import KubeClient
from kuno.k8s.config import UnknownContextError, load_startup_targets
from kuno.k8s.resources import list_pods, render_pod_details, render_pod_row
from kuno.models import PodSummary, StartupConfig


class KunoApp(App[None]):
    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.startup_config = startup_config
        self.pods: list[PodSummary] = []
        self.resolved_startup_config: StartupConfig | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), id="startup-summary")
        with Horizontal():
            yield ListView(id="pod-list", initial_index=None)
            yield Static("pod\n(loading)", id="pod-details")

    def on_mount(self) -> None:
        summary = self.query_one("#startup-summary", Static)
        pod_details = self.query_one("#pod-details", Static)
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
            await self._render_pod_list()
            pod_details.update(f"pod\n(error: {error})")
            return

        self.pods = pods
        await self._render_pod_list()
        if self.pods:
            self._update_pod_details(0)
        else:
            pod_details.update("pod\n(no pods found)")

    async def _render_pod_list(self) -> None:
        pod_list = self.query_one("#pod-list", ListView)
        await pod_list.clear()
        await pod_list.extend(ListItem(Static(render_pod_row(pod))) for pod in self.pods)
        pod_list.index = 0 if self.pods else None

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "pod-list":
            return

        self._update_pod_details(event.list_view.index)

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
