from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Static

from kuno.models import StartupConfig


class KunoApp(App[None]):
    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.startup_config = startup_config

    def compose(self) -> ComposeResult:
        yield Static(self._summary_text(), id="startup-summary")

    def _summary_text(self) -> str:
        context = self.startup_config.context or "auto"
        namespace = self.startup_config.namespace or "auto"
        return f"kuno\ncontext: {context}\nnamespace: {namespace}"
