from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import ClassVar

from textual import events, work
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Static

from kuno.commands import ParsedCommand, parse_command, suggest_commands
from kuno.k8s.client import KubeClient
from kuno.k8s.config import UnknownContextError, load_available_context_names, load_startup_targets
from kuno.k8s.resources import list_namespaces, list_pods, render_pod_details, truncate_for_table
from kuno.models import PodSummary, StartupConfig


class AboutScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "close", "Close")]

    def compose(self) -> ComposeResult:
        yield Static(
            "kuno\n\nA Kubernetes TUI focused on fast operational workflows and better logs.\n\n"
            "Current slice:\n- pod explorer\n- command palette\n- vim-style : commands\n\n"
            "Press Escape to close.",
            id="about-panel",
        )

    def action_close(self) -> None:
        self.dismiss(None)


class KunoApp(App[None]):
    CSS_PATH = "app.tcss"
    MAX_COMMAND_SUGGESTIONS = 4
    theme = "nord"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("d", "toggle_details", "Details"),
        ("colon", "open_command_bar", "Command"),
        ("escape", "close_command_bar", "Close"),
        ("r", "refresh_pods", "Refresh"),
    ]

    def __init__(self, startup_config: StartupConfig) -> None:
        super().__init__()
        self.available_contexts: list[str] = []
        self.available_namespaces: list[str] = []
        self.command_bar_visible = False
        self.command_suggestions: list[str] = []
        self.command_suggestion_index = 0
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
        with Vertical(id="command-area"):
            with Horizontal(id="command-bar"):
                yield Static(":", id="command-prefix")
                yield Input(placeholder="command", id="command-input")
            yield Static("", id="command-suggestions")
        yield Footer()

    def on_mount(self) -> None:
        command_area = self.query_one("#command-area", Vertical)
        details_panel = self.query_one("#details-panel", Vertical)
        summary = self.query_one("#startup-summary", Static)
        pod_table = self.query_one("#pod-table", DataTable)
        pod_details = self.query_one("#pod-details", Static)
        command_area.display = self.command_bar_visible
        details_panel.display = self.details_visible
        pod_table.focus()
        pod_table.cursor_type = "row"
        pod_table.zebra_stripes = True
        pod_table.add_column("Name", width=56)
        pod_table.add_columns("Ready", "Status", "Restarts", "Age", "CPU", "Memory", "Containers")
        self.available_contexts = load_available_context_names()
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
                with suppress(Exception):
                    self.available_namespaces = await list_namespaces(kube_client)
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
        command_area = self.query_one("#command-area", Vertical)
        command_input = self.query_one("#command-input", Input)
        self.command_bar_visible = True
        command_area.display = True
        command_input.value = ""
        self._update_command_suggestions("")
        command_input.focus()

    def action_close_command_bar(self) -> None:
        if not self.command_bar_visible:
            return
        command_area = self.query_one("#command-area", Vertical)
        command_input = self.query_one("#command-input", Input)
        self.command_bar_visible = False
        command_area.display = False
        command_input.value = ""
        self.command_suggestions = []
        self.command_suggestion_index = 0
        self._render_command_suggestions()
        self.query_one("#pod-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-input":
            return
        self._update_command_suggestions(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        raw = event.value
        if self.command_suggestions:
            selected = self.command_suggestions[self.command_suggestion_index]
            if raw.strip() != selected:
                raw = selected
        self.execute_command(raw)
        self.action_close_command_bar()

    def on_key(self, event: events.Key) -> None:
        if not self.command_bar_visible:
            return
        command_input = self.query_one("#command-input", Input)
        if self.focused is not command_input:
            return

        if event.key == "tab":
            self._accept_command_suggestion()
            event.stop()
        elif event.key == "down":
            self._move_command_suggestion(1)
            event.stop()
        elif event.key == "up":
            self._move_command_suggestion(-1)
            event.stop()

    def get_system_commands(self, screen) -> Iterable[SystemCommand]:
        yield SystemCommand(
            "Kuno / Help / About", "Show information about kuno", self._command_about
        )
        if screen.query("HelpPanel"):
            yield SystemCommand(
                "Kuno / Help / Keys",
                "Hide the keys and widget help panel",
                self.action_hide_help_panel,
            )
        else:
            yield SystemCommand(
                "Kuno / Help / Keys",
                "Show help for the focused widget and a summary of available keys",
                self.action_show_help_panel,
            )
        yield SystemCommand(
            "Kuno / Config / Theme",
            "Open the theme selector",
            self.action_change_theme,
        )
        for theme_name in sorted(self.available_themes):
            yield SystemCommand(
                f"Kuno / Config / Theme / {theme_name}",
                f"Switch to the {theme_name} theme",
                lambda theme_name=theme_name: self._command_theme(theme_name),
                discover=False,
            )
        for context_name in self.available_contexts:
            yield SystemCommand(
                f"Kuno / Config / Context / {context_name}",
                f"Switch to the {context_name} context",
                lambda context_name=context_name: self._command_context(context_name),
                discover=False,
            )
        for namespace in self.available_namespaces:
            yield SystemCommand(
                f"Kuno / Config / Namespace / {namespace}",
                f"Switch to the {namespace} namespace",
                lambda namespace=namespace: self._command_namespace(namespace),
                discover=False,
            )
        yield SystemCommand(
            "Kuno / View / Pods",
            "Focus the pods table",
            self._command_pods,
        )
        yield SystemCommand(
            "Kuno / View / Pods / Refresh",
            "Reload the current pods table",
            self._command_refresh,
        )
        if self.details_visible:
            yield SystemCommand(
                "Kuno / View / Pods / Details / Hide",
                "Close the details side panel",
                self._command_hide_details,
            )
        else:
            yield SystemCommand(
                "Kuno / View / Pods / Details / Show",
                "Open the details side panel",
                self._command_show_details,
            )
        yield SystemCommand("App / Quit", "Quit the application", self.action_quit)

    def execute_command(self, raw: str) -> None:
        try:
            command = parse_command(raw)
            self._run_command(command)
        except (UnknownContextError, ValueError) as error:
            self.notify(str(error), severity="error")

    def _run_command(self, command: ParsedCommand) -> None:
        match command.name:
            case "about":
                self._command_about()
            case "keys":
                self._command_keys()
            case "pods":
                self._command_pods()
            case "refresh":
                self._command_refresh()
            case "details":
                self._command_show_details()
            case "hide-details":
                self._command_hide_details()
            case "theme":
                self._command_theme(command.argument)
            case "ns":
                if command.argument is None:
                    raise ValueError("Command 'ns' requires an argument")
                self._command_namespace(command.argument)
            case "ctx":
                if command.argument is None:
                    raise ValueError("Command 'ctx' requires an argument")
                self._command_context(command.argument)
            case "help":
                self.notify(
                    "Commands: about, keys, pods, refresh, details, hide-details, theme [name], ns <ns>, ctx <ctx>"
                )
            case _:
                self.notify(f"Unknown command: {command.name}", severity="error")

    def _command_about(self) -> None:
        self.push_screen(AboutScreen())

    def _command_pods(self) -> None:
        self.query_one("#pod-table", DataTable).focus()

    def _command_keys(self) -> None:
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

    def _command_refresh(self) -> None:
        self.load_pods()
        self.notify("Refreshing pods")

    def action_refresh_pods(self) -> None:
        self._command_refresh()

    def _command_theme(self, theme_name: str | None) -> None:
        if theme_name is None:
            self.action_change_theme()
            return
        self.theme = theme_name
        self.notify(f"Switched theme to {self.theme}")

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

    def _update_command_suggestions(self, raw: str) -> None:
        self.command_suggestions = suggest_commands(
            raw,
            contexts=self.available_contexts,
            namespaces=self.available_namespaces,
            themes=sorted(self.available_themes),
        )
        self.command_suggestion_index = 0
        self._render_command_suggestions()

    def _render_command_suggestions(self) -> None:
        suggestions = self.query_one("#command-suggestions", Static)
        suggestions.display = bool(self.command_suggestions)
        if not self.command_suggestions:
            suggestions.update("")
            return

        start = max(0, self.command_suggestion_index - self.MAX_COMMAND_SUGGESTIONS + 1)
        end = min(len(self.command_suggestions), start + self.MAX_COMMAND_SUGGESTIONS)
        start = max(0, end - self.MAX_COMMAND_SUGGESTIONS)
        lines = []
        for index in range(start, end):
            suggestion = self.command_suggestions[index]
            prefix = ">" if index == self.command_suggestion_index else " "
            lines.append(f"{prefix} {suggestion}")
        suggestions.update("\n".join(lines))

    def _accept_command_suggestion(self) -> None:
        if not self.command_suggestions:
            return
        command_input = self.query_one("#command-input", Input)
        command_input.value = self.command_suggestions[self.command_suggestion_index]
        command_input.cursor_position = len(command_input.value)
        self._update_command_suggestions(command_input.value)

    def _move_command_suggestion(self, direction: int) -> None:
        if not self.command_suggestions:
            return
        self.command_suggestion_index = (self.command_suggestion_index + direction) % len(
            self.command_suggestions
        )
        self._render_command_suggestions()

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
