from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Static

from kuno.k8s.client import KubeClient
from kuno.k8s.config import UnknownContextError, load_startup_targets
from kuno.k8s.resources import list_pods, render_pod_summaries
from kuno.models import StartupConfig


class KunoApp(App[None]):
    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.startup_config = startup_config
        self.resolved_startup_config: StartupConfig | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), id="startup-summary")
        yield Static("pods\n(loading)", id="pod-list")

    def on_mount(self) -> None:
        summary = self.query_one("#startup-summary", Static)
        pod_list = self.query_one("#pod-list", Static)
        try:
            self.resolved_startup_config = load_startup_targets(self.startup_config)
        except UnknownContextError as error:
            summary.update(f"kuno\nerror: {error}")
            pod_list.update("pods\n(startup failed)")
            return

        summary.update(self._summary_text())
        self.load_pods()

    @work(exclusive=True)
    async def load_pods(self) -> None:
        pod_list = self.query_one("#pod-list", Static)
        if self.resolved_startup_config is None:
            pod_list.update("pods\n(startup not resolved)")
            return

        context = self.resolved_startup_config.context
        namespace = self.resolved_startup_config.namespace
        if context is None or namespace is None:
            pod_list.update("pods\n(startup not resolved)")
            return

        try:
            async with KubeClient(context=context) as kube_client:
                pods = await list_pods(kube_client, namespace)
        except Exception as error:
            pod_list.update(f"pods\n(error: {error})")
            return

        pod_list.update(render_pod_summaries(pods))

    def _summary_text(self) -> str:
        startup_config = self.resolved_startup_config or self.startup_config
        context = startup_config.context or "auto"
        namespace = startup_config.namespace or "auto"
        return f"kuno\ncontext: {context}\nnamespace: {namespace}"
