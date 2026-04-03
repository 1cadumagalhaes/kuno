from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Input, Static

from kuno.commands import ParsedCommand, parse_command
from kuno.k8s.client import KubeClient
from kuno.k8s.config import UnknownContextError, load_startup_targets
from kuno.k8s.resources import list_pods, render_pod_details, truncate_for_table
from kuno.models import PodSummary, StartupConfig


class KunoApp(App[None]):
    CSS_PATH = "app.tcss"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("d", "toggle_details", "Details"),
        ("colon", "open_command_bar", "Command"),
        ("escape", "close_command_bar", "Close"),
    ]

    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.command_bar_visible = False
        self.details_visible = False
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
        yield Input(placeholder=": command", id="command-input")
        yield Footer()

    def on_mount(self) -> None:
        command_input = self.query_one("#command-input", Input)
        details_panel = self.query_one("#details-panel", Vertical)
        summary = self.query_one("#startup-summary", Static)
        pod_table = self.query_one("#pod-table", DataTable)
        pod_details = self.query_one("#pod-details", Static)
        command_input.display = self.command_bar_visible
        details_panel.display = self.details_visible
        pod_table.focus()
        pod_table.cursor_type = "row"
        pod_table.zebra_stripes = True
        pod_table.add_column("Name", width=56)
        pod_table.add_columns("Ready", "Status", "Restarts", "Age", "CPU", "Memory", "Containers")
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
            pod_table.add_row(
                truncate_for_table(pod.name),
                pod.ready,
                pod.status,
                str(pod.restarts),
                pod.age,
                pod.cpu,
                pod.memory,
                pod.containers,
                key=pod.name,
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "pod-table":
            return

        self._update_pod_details(event.cursor_row)

    def action_toggle_details(self) -> None:
        self.details_visible = not self.details_visible
        details_panel = self.query_one("#details-panel", Vertical)
        details_panel.display = self.details_visible
        if self.details_visible:
            self._update_pod_details(self.query_one("#pod-table", DataTable).cursor_row)
        else:
            pass

    def action_open_command_bar(self) -> None:
        command_input = self.query_one("#command-input", Input)
        self.command_bar_visible = True
        command_input.display = True
        command_input.value = ":"
        command_input.focus()

    def action_close_command_bar(self) -> None:
        if not self.command_bar_visible:
            return
        command_input = self.query_one("#command-input", Input)
        self.command_bar_visible = False
        command_input.display = False
        command_input.value = ""
        self.query_one("#pod-table", DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        self.execute_command(event.value)
        self.action_close_command_bar()

    def get_system_commands(self, screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("Refresh pods", "Reload the current pods table", self._command_refresh)
        yield SystemCommand(
            "Show details", "Open the details side panel", self._command_show_details
        )
        yield SystemCommand(
            "Hide details", "Close the details side panel", self._command_hide_details
        )
        yield SystemCommand("Pods view", "Focus the pods table", self._command_pods)

    def execute_command(self, raw: str) -> None:
        try:
            command = parse_command(raw)
            self._run_command(command)
        except (UnknownContextError, ValueError) as error:
            self.notify(str(error), severity="error")

    def _run_command(self, command: ParsedCommand) -> None:
        match command.name:
            case "pods":
                self._command_pods()
            case "refresh":
                self._command_refresh()
            case "details":
                self._command_show_details()
            case "hide-details":
                self._command_hide_details()
            case "ns":
                if command.argument is None:
                    raise ValueError("Command 'ns' requires an argument")
                self._command_namespace(command.argument)
            case "ctx":
                if command.argument is None:
                    raise ValueError("Command 'ctx' requires an argument")
                self._command_context(command.argument)
            case "help":
                self.notify("Commands: pods, refresh, details, hide-details, ns <ns>, ctx <ctx>")
            case _:
                self.notify(f"Unknown command: {command.name}", severity="error")

    def _command_pods(self) -> None:
        self.query_one("#pod-table", DataTable).focus()

    def _command_refresh(self) -> None:
        self.load_pods()
        self.notify("Refreshing pods")

    def _command_show_details(self) -> None:
        if not self.details_visible:
            self.action_toggle_details()
        else:
            self.notify("Details panel already open")

    def _command_hide_details(self) -> None:
        if self.details_visible:
            self.action_toggle_details()
        else:
            self.notify("Details panel already closed")

    def _command_namespace(self, namespace: str) -> None:
        current = self._require_target()
        self.resolved_startup_config = StartupConfig(context=current.context, namespace=namespace)
        self.query_one("#startup-summary", Static).update(self._summary_text())
        self.load_pods()
        self.notify(f"Switched namespace to {namespace}")

    def _command_context(self, context: str) -> None:
        current = self._require_target()
        self.resolved_startup_config = load_startup_targets(
            StartupConfig(context=context, namespace=current.namespace)
        )
        self.query_one("#startup-summary", Static).update(self._summary_text())
        self.load_pods()
        self.notify(f"Switched context to {self.resolved_startup_config.context}")

    def _require_target(self) -> StartupConfig:
        if self.resolved_startup_config is None:
            raise ValueError("Startup target is not resolved")
        return self.resolved_startup_config

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
