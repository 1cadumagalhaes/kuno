from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Static

from kuno.k8s.config import UnknownContextError, load_startup_targets
from kuno.models import StartupConfig


class KunoApp(App[None]):
    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.startup_config = startup_config
        self.resolved_startup_config: StartupConfig | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), id="startup-summary")

    def on_mount(self) -> None:
        summary = self.query_one("#startup-summary", Static)
        try:
            self.resolved_startup_config = load_startup_targets(self.startup_config)
        except UnknownContextError as error:
            summary.update(f"kuno\nerror: {error}")
            return

        summary.update(self._summary_text())

    def _summary_text(self) -> str:
        startup_config = self.resolved_startup_config or self.startup_config
        context = startup_config.context or "auto"
        namespace = startup_config.namespace or "auto"
        return f"kuno\ncontext: {context}\nnamespace: {namespace}"
