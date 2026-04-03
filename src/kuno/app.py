from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from textwrap import wrap as text_wrap
from typing import ClassVar

from textual import events, work
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, Log, Static

from kuno.commands import ParsedCommand, parse_command, suggest_commands
from kuno.k8s.actions import delete_resource, restart_resource
from kuno.k8s.client import KubeClient
from kuno.k8s.config import (
    UnknownContextError,
    load_available_context_names,
    load_context_summaries,
    load_startup_targets,
)
from kuno.k8s.resources import (
    list_deployments,
    list_namespace_summaries,
    list_namespaces,
    list_pod_containers,
    list_pods,
    list_pvcs,
    list_secrets,
    list_services,
    list_statefulsets,
    parse_since_duration,
    read_pod_logs,
    render_container_details,
    render_context_details,
    render_deployment_details,
    render_namespace_details,
    render_pod_details,
    render_pvc_details,
    render_secret_details,
    render_service_details,
    render_statefulset_details,
    truncate_for_table,
)
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


class ConfirmActionScreen(ModalScreen[bool]):
    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.dialog_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self.dialog_title, id="confirm-title")
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-actions"):
                yield Button("Confirm", id="confirm-yes", variant="error")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class LogsScreen(Screen[None]):
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "close", "Back"),
        ("f", "toggle_follow", "Follow"),
        ("s", "focus_since", "Since"),
        ("slash", "focus_filter", "Filter"),
        ("r", "reload", "Reload"),
        ("t", "toggle_timestamps", "Timestamps"),
        ("ctrl+l", "clear_filter", "Clear Filter"),
        ("w", "toggle_wrap", "Wrap"),
    ]

    def __init__(
        self,
        *,
        context: str,
        namespace: str,
        pod_name: str,
        container_name: str | None,
    ) -> None:
        super().__init__()
        self.context = context
        self.filter_text = ""
        self.follow_enabled = False
        self.log_lines: list[str] = []
        self.namespace = namespace
        self.pod_name = pod_name
        self.container_name = container_name
        self.since_text = ""
        self.timestamps_enabled = False
        self.wrap_enabled = False

    def compose(self) -> ComposeResult:
        target = (
            self.pod_name
            if self.container_name is None
            else f"{self.pod_name}/{self.container_name}"
        )
        yield Static(
            self._title_text(target),
            id="logs-title",
        )
        with Horizontal(id="logs-controls"):
            yield Input(placeholder="since (e.g. 5m, 1h)", id="logs-since")
            yield Input(placeholder="filter logs", id="logs-filter")
        yield Log(id="logs-output", highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#logs-output", Log).focus()
        self.set_interval(2, self._poll_logs)
        self.load_logs()

    @work(exclusive=True)
    async def load_logs(self) -> None:
        output = self.query_one("#logs-output", Log)
        output.clear()
        try:
            async with KubeClient(context=self.context) as kube_client:
                logs = await read_pod_logs(
                    kube_client,
                    self.namespace,
                    self.pod_name,
                    container_name=self.container_name,
                    since_seconds=parse_since_duration(self.since_text),
                    timestamps=self.timestamps_enabled,
                )
        except Exception as error:
            output.write_line(f"error: {error}")
            return

        self.log_lines = logs.splitlines() if logs else []
        self._render_logs()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "logs-filter":
            self.filter_text = event.value
            self._render_logs()
        elif event.input.id == "logs-since":
            self.since_text = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "logs-since":
            self.load_logs()

    def action_focus_filter(self) -> None:
        self.query_one("#logs-filter", Input).focus()

    def action_focus_since(self) -> None:
        self.query_one("#logs-since", Input).focus()

    def action_reload(self) -> None:
        self.load_logs()

    def action_toggle_follow(self) -> None:
        self.follow_enabled = not self.follow_enabled
        self._update_title()

    def action_toggle_timestamps(self) -> None:
        self.timestamps_enabled = not self.timestamps_enabled
        self._update_title()
        self.load_logs()

    def action_toggle_wrap(self) -> None:
        self.wrap_enabled = not self.wrap_enabled
        self._update_title()
        self._render_logs()

    def action_clear_filter(self) -> None:
        log_filter = self.query_one("#logs-filter", Input)
        log_filter.value = ""
        self.filter_text = ""
        self._render_logs()

    def _render_logs(self) -> None:
        output = self.query_one("#logs-output", Log)
        output.clear()
        output.auto_scroll = self.follow_enabled
        if self.filter_text:
            lines = [line for line in self.log_lines if self.filter_text in line]
        else:
            lines = self.log_lines
        if self.wrap_enabled:
            lines = self._wrap_lines(lines)
        if lines:
            output.write_lines(lines)
        elif self.log_lines:
            output.write_line("(no matching log lines)")
        else:
            output.write_line("(no logs)")

    def _poll_logs(self) -> None:
        if self.follow_enabled:
            self.load_logs()

    def _wrap_lines(self, lines: list[str]) -> list[str]:
        output = self.query_one("#logs-output", Log)
        width = max(output.size.width - 2, 20)
        wrapped: list[str] = []
        for line in lines:
            pieces = text_wrap(line, width=width, replace_whitespace=False, drop_whitespace=False)
            wrapped.extend(pieces or [""])
        return wrapped

    def _title_text(self, target: str) -> str:
        follow = "on" if self.follow_enabled else "off"
        timestamps = "on" if self.timestamps_enabled else "off"
        wrap = "on" if self.wrap_enabled else "off"
        return (
            "Logs\n"
            f"context: {self.context}\n"
            f"namespace: {self.namespace}\n"
            f"target: {target}\n"
            f"follow: {follow} [f]  timestamps: {timestamps} [t]  wrap: {wrap} [w]\n"
            f"since: {self.since_text or 'all'} [s]  filter: /  reload: r  clear filter: ctrl+l  back: esc"
        )

    def _update_title(self) -> None:
        target = (
            self.pod_name
            if self.container_name is None
            else f"{self.pod_name}/{self.container_name}"
        )
        self.query_one("#logs-title", Static).update(self._title_text(target))

    def action_close(self) -> None:
        self.app.pop_screen()


class KunoApp(App[None]):
    CSS_PATH = "app.tcss"
    MAX_COMMAND_SUGGESTIONS = 4
    theme = "nord"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("backspace", "go_back", "Back"),
        ("d", "toggle_details", "Details"),
        ("l", "open_logs", "Logs"),
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
        self.container_pod_name: str | None = None
        self.containers: list[ContainerSummary] = []
        self.contexts: list[ContextSummary] = []
        self.current_view = ExplorerView.CONTEXTS
        self.details_visible = False
        self.navigation_stack: list[tuple[ExplorerView, str | None]] = []
        self.namespaces: list[NamespaceSummary] = []
        self.startup_config = startup_config
        self.deployments: list[DeploymentSummary] = []
        self.pods: list[PodSummary] = []
        self.pvcs: list[PvcSummary] = []
        self.secrets: list[SecretSummary] = []
        self.services: list[ServiceSummary] = []
        self.statefulsets: list[StatefulSetSummary] = []
        self.resolved_startup_config: StartupConfig | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="summary-bar"):
            yield Static(self._summary_text(), id="startup-summary")
            yield Button("Back", id="back-button")
        with Horizontal(id="explorer"):
            with Vertical(id="pod-panel"):
                yield Static(self._panel_title(), id="table-title", classes="panel-title")
                yield DataTable(id="pod-table")
            with Vertical(id="details-panel"):
                yield Static(self._details_title(), id="details-title", classes="panel-title")
                yield Static(f"{self._view_singular()}\n(loading)", id="pod-details")
        with Vertical(id="command-area"):
            with Horizontal(id="command-bar"):
                yield Static(":", id="command-prefix")
                yield Input(placeholder="command", id="command-input")
            yield Static("", id="command-suggestions")
        yield Footer()

    def on_mount(self) -> None:
        back_button = self.query_one("#back-button", Button)
        command_area = self.query_one("#command-area", Vertical)
        details_panel = self.query_one("#details-panel", Vertical)
        summary = self.query_one("#startup-summary", Static)
        pod_table = self.query_one("#pod-table", DataTable)
        pod_details = self.query_one("#pod-details", Static)
        command_area.display = self.command_bar_visible
        back_button.display = False
        details_panel.display = self.details_visible
        pod_table.focus()
        pod_table.cursor_type = "row"
        pod_table.zebra_stripes = True
        self._configure_table_columns()
        self.available_contexts = load_available_context_names()
        try:
            self.resolved_startup_config = load_startup_targets(self.startup_config)
        except UnknownContextError as error:
            summary.update(f"kuno\nerror: {error}")
            pod_details.update("pod\n(startup failed)")
            return

        summary.update(self._summary_text())
        self.refresh_current_view()

    @work(exclusive=True)
    async def refresh_current_view(self) -> None:
        pod_details = self.query_one("#pod-details", Static)
        if self.resolved_startup_config is None:
            pod_details.update(f"{self._view_singular()}\n(startup not resolved)")
            return

        context = self.resolved_startup_config.context
        namespace = self.resolved_startup_config.namespace
        if context is None or namespace is None:
            pod_details.update(f"{self._view_singular()}\n(startup not resolved)")
            return

        try:
            async with KubeClient(context=context) as kube_client:
                if self.current_view is ExplorerView.PODS:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.pods = await list_pods(kube_client, namespace)
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.CONTAINERS:
                    self.contexts = []
                    self.namespaces = []
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                    if self.container_pod_name is None:
                        self.containers = []
                    else:
                        self.containers = await list_pod_containers(
                            kube_client, namespace, self.container_pod_name
                        )
                elif self.current_view is ExplorerView.CONTEXTS:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = load_context_summaries()
                    self.namespaces = []
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.DEPLOYMENTS:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.deployments = await list_deployments(kube_client, namespace)
                    self.pods = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.NAMESPACES:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = await list_namespace_summaries(
                        kube_client, current_namespace=namespace
                    )
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.PVC:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.pvcs = await list_pvcs(kube_client, namespace)
                    self.pods = []
                    self.deployments = []
                    self.secrets = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.SECRETS:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.secrets = await list_secrets(kube_client, namespace)
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.services = []
                    self.statefulsets = []
                elif self.current_view is ExplorerView.SERVICES:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.services = await list_services(kube_client, namespace)
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.statefulsets = []
                else:
                    self.container_pod_name = None
                    self.containers = []
                    self.contexts = []
                    self.namespaces = []
                    self.statefulsets = await list_statefulsets(kube_client, namespace)
                    self.pods = []
                    self.deployments = []
                    self.pvcs = []
                    self.secrets = []
                    self.services = []
                with suppress(Exception):
                    self.available_namespaces = await list_namespaces(kube_client)
        except Exception as error:
            self.container_pod_name = None
            self.containers = []
            self.contexts = []
            self.namespaces = []
            self.pods = []
            self.deployments = []
            self.pvcs = []
            self.secrets = []
            self.services = []
            self.statefulsets = []
            await self._render_pod_table()
            pod_details.update(f"{self._view_singular()}\n(error: {error})")
            return

        await self._render_pod_table()
        if self._current_rows():
            self._update_pod_details(0)
        else:
            pod_details.update(f"{self._view_singular()}\n(no {self.current_view.value} found)")

    async def _render_pod_table(self) -> None:
        pod_table = self.query_one("#pod-table", DataTable)
        self.query_one("#table-title", Static).update(self._panel_title())
        self.query_one("#details-title", Static).update(self._details_title())
        self._configure_table_columns()
        pod_table.clear()
        if self.current_view is ExplorerView.PODS:
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
        elif self.current_view is ExplorerView.CONTAINERS:
            for container in self.containers:
                pod_table.add_row(
                    truncate_for_table(container.name),
                    container.ready,
                    container.state,
                    str(container.restarts),
                    truncate_for_table(container.image, max_length=40),
                    container.cpu,
                    container.memory,
                    key=f"{container.pod}:{container.name}",
                )
        elif self.current_view is ExplorerView.CONTEXTS:
            for context in self.contexts:
                pod_table.add_row(
                    truncate_for_table(context.name),
                    context.cluster,
                    context.user,
                    context.namespace,
                    context.current,
                    key=context.name,
                )
        elif self.current_view is ExplorerView.DEPLOYMENTS:
            for deployment in self.deployments:
                pod_table.add_row(
                    truncate_for_table(deployment.name),
                    deployment.ready,
                    str(deployment.up_to_date),
                    str(deployment.available),
                    deployment.age,
                    deployment.cpu,
                    deployment.memory,
                    deployment.containers,
                    key=deployment.name,
                )
        elif self.current_view is ExplorerView.SERVICES:
            for service in self.services:
                pod_table.add_row(
                    truncate_for_table(service.name),
                    service.type,
                    service.cluster_ip,
                    service.ports,
                    service.age,
                    service.selector,
                    key=service.name,
                )
        elif self.current_view is ExplorerView.PVC:
            for pvc in self.pvcs:
                pod_table.add_row(
                    truncate_for_table(pvc.name),
                    pvc.status,
                    pvc.volume,
                    pvc.capacity,
                    pvc.access,
                    pvc.storage_class,
                    pvc.age,
                    key=pvc.name,
                )
        elif self.current_view is ExplorerView.NAMESPACES:
            for namespace in self.namespaces:
                pod_table.add_row(
                    truncate_for_table(namespace.name),
                    namespace.status,
                    namespace.age,
                    namespace.current,
                    key=namespace.name,
                )
        elif self.current_view is ExplorerView.SECRETS:
            for secret in self.secrets:
                pod_table.add_row(
                    truncate_for_table(secret.name),
                    secret.type,
                    str(secret.data_items),
                    secret.immutable,
                    secret.age,
                    key=secret.name,
                )
        else:
            for statefulset in self.statefulsets:
                pod_table.add_row(
                    truncate_for_table(statefulset.name),
                    statefulset.ready,
                    str(statefulset.updated),
                    str(statefulset.current),
                    statefulset.age,
                    statefulset.cpu,
                    statefulset.memory,
                    statefulset.containers,
                    key=statefulset.name,
                )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "pod-table":
            return

        self._update_pod_details(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "pod-table":
            return

        if self.current_view is ExplorerView.CONTEXTS:
            self._open_selected_context(event.cursor_row)
        elif self.current_view is ExplorerView.NAMESPACES:
            self._open_selected_namespace(event.cursor_row)
        elif self.current_view is ExplorerView.PODS:
            self._open_selected_pod(event.cursor_row)

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
        yield SystemCommand("About", "Show information about kuno", self._command_about)
        if self.navigation_stack:
            yield SystemCommand("Back", "Return to the previous explorer view", self.action_go_back)
        if screen.query("HelpPanel"):
            yield SystemCommand(
                "Keys",
                "Hide the keys and widget help panel",
                self.action_hide_help_panel,
            )
        else:
            yield SystemCommand(
                "Keys",
                "Show help for the focused widget and a summary of available keys",
                self.action_show_help_panel,
            )
        yield SystemCommand(
            "Theme",
            "Open the theme selector",
            self.action_change_theme,
        )
        for theme_name in sorted(self.available_themes):
            yield SystemCommand(
                f"Use theme {theme_name}",
                f"Switch to the {theme_name} theme",
                lambda theme_name=theme_name: self._command_theme(theme_name),
                discover=False,
            )
        for context_name in self.available_contexts:
            yield SystemCommand(
                f"Use context {context_name}",
                f"Switch to the {context_name} context",
                lambda context_name=context_name: self._command_context(context_name),
                discover=False,
            )
        for namespace in self.available_namespaces:
            yield SystemCommand(
                f"Use namespace {namespace}",
                f"Switch to the {namespace} namespace",
                lambda namespace=namespace: self._command_namespace(namespace),
                discover=False,
            )
        yield SystemCommand(
            "Pods",
            "Focus the pods table",
            self._command_pods,
        )
        yield SystemCommand(
            "Containers",
            "Show containers for the selected pod",
            self._command_containers,
        )
        if self._can_open_logs_selected():
            yield SystemCommand(
                "Logs",
                f"Open logs for the selected {self._view_singular()}",
                self._command_logs,
            )
        if self._can_delete_selected():
            yield SystemCommand(
                "Delete selected",
                f"Delete the selected {self._view_singular()}",
                self._command_delete,
            )
        yield SystemCommand(
            "Contexts",
            "Show kube contexts in the main table",
            self._command_contexts,
        )
        yield SystemCommand(
            "Deployments",
            "Show deployments in the main table",
            self._command_deployments,
        )
        yield SystemCommand(
            "Namespaces",
            "Show namespaces in the main table",
            self._command_namespaces,
        )
        yield SystemCommand(
            "PVC",
            "Show persistent volume claims in the main table",
            self._command_pvc,
        )
        yield SystemCommand(
            "Secrets",
            "Show secrets in the main table",
            self._command_secrets,
        )
        yield SystemCommand(
            "Services",
            "Show services in the main table",
            self._command_services,
        )
        yield SystemCommand(
            "StatefulSets",
            "Show statefulsets in the main table",
            self._command_statefulsets,
        )
        yield SystemCommand(
            f"Refresh {self.current_view.value}",
            f"Reload the current {self.current_view.value} table",
            self._command_refresh,
        )
        if self._can_restart_selected():
            yield SystemCommand(
                "Restart selected",
                f"Restart the selected {self._view_singular()}",
                self._command_restart,
            )
        if self.details_visible:
            yield SystemCommand(
                "Hide details",
                "Close the details side panel",
                self._command_hide_details,
            )
        else:
            yield SystemCommand(
                "Show details",
                "Open the details side panel",
                self._command_show_details,
            )
        yield SystemCommand("Quit", "Quit the application", self.action_quit)

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
            case "back":
                self.action_go_back()
            case "containers":
                self._command_containers()
            case "contexts":
                self._command_contexts()
            case "del":
                self._command_delete()
            case "keys":
                self._command_keys()
            case "logs":
                self._command_logs()
            case "deploy":
                self._command_deployments()
            case "namespaces":
                self._command_namespaces()
            case "pods":
                self._command_pods()
            case "pvc":
                self._command_pvc()
            case "refresh":
                self._command_refresh()
            case "restart":
                self._command_restart()
            case "secrets":
                self._command_secrets()
            case "svc":
                self._command_services()
            case "sts":
                self._command_statefulsets()
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
                    "Commands: about, back, contexts, namespaces, pods, containers, deploy, sts, svc, pvc, secrets, logs, refresh, details, hide-details, del, restart, theme [name], ns <ns>, ctx <ctx>"
                )
            case _:
                self.notify(f"Unknown command: {command.name}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-button":
            self.action_go_back()

    def _command_about(self) -> None:
        self.push_screen(AboutScreen())

    def action_go_back(self) -> None:
        if not self.navigation_stack:
            self.notify("Already at the top level", severity="warning")
            return
        self.current_view, self.container_pod_name = self.navigation_stack.pop()
        self.refresh_current_view()
        self._update_back_button()

    def _command_pods(self) -> None:
        if self.current_view is not ExplorerView.PODS:
            self._push_navigation_state()
            self.current_view = ExplorerView.PODS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _open_selected_pod(self, index: int) -> None:
        if index < 0 or index >= len(self.pods):
            return
        self._push_navigation_state()
        self.container_pod_name = self.pods[index].name
        self.current_view = ExplorerView.CONTAINERS
        self.refresh_current_view()

    def _command_containers(self) -> None:
        if self.current_view is ExplorerView.PODS:
            pod_table = self.query_one("#pod-table", DataTable)
            cursor_row = pod_table.cursor_row
            if cursor_row is None or cursor_row < 0 or cursor_row >= len(self.pods):
                self.notify("No pod selected", severity="warning")
                return
            self.container_pod_name = self.pods[cursor_row].name
        if self.container_pod_name is None:
            self.notify("No pod selected", severity="warning")
            return
        if self.current_view is not ExplorerView.CONTAINERS:
            self._push_navigation_state()
            self.current_view = ExplorerView.CONTAINERS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _open_selected_context(self, index: int) -> None:
        if index < 0 or index >= len(self.contexts):
            return
        context = self.contexts[index]
        self._push_navigation_state()
        self._command_context(context.name)
        self.current_view = ExplorerView.NAMESPACES
        self.refresh_current_view()

    def _open_selected_namespace(self, index: int) -> None:
        if index < 0 or index >= len(self.namespaces):
            return
        namespace = self.namespaces[index]
        self._push_navigation_state()
        self._command_namespace(namespace.name)
        self.current_view = ExplorerView.PODS
        self.refresh_current_view()

    def _command_contexts(self) -> None:
        if self.current_view is not ExplorerView.CONTEXTS:
            self._push_navigation_state()
            self.current_view = ExplorerView.CONTEXTS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_deployments(self) -> None:
        if self.current_view is not ExplorerView.DEPLOYMENTS:
            self._push_navigation_state()
            self.current_view = ExplorerView.DEPLOYMENTS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_namespaces(self) -> None:
        if self.current_view is not ExplorerView.NAMESPACES:
            self._push_navigation_state()
            self.current_view = ExplorerView.NAMESPACES
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_pvc(self) -> None:
        if self.current_view is not ExplorerView.PVC:
            self._push_navigation_state()
            self.current_view = ExplorerView.PVC
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_secrets(self) -> None:
        if self.current_view is not ExplorerView.SECRETS:
            self._push_navigation_state()
            self.current_view = ExplorerView.SECRETS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_services(self) -> None:
        if self.current_view is not ExplorerView.SERVICES:
            self._push_navigation_state()
            self.current_view = ExplorerView.SERVICES
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_statefulsets(self) -> None:
        if self.current_view is not ExplorerView.STATEFULSETS:
            self._push_navigation_state()
            self.current_view = ExplorerView.STATEFULSETS
            self.refresh_current_view()
        self.query_one("#pod-table", DataTable).focus()

    def _command_keys(self) -> None:
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

    def action_open_logs(self) -> None:
        self._command_logs()

    def _command_logs(self) -> None:
        target = self._selected_logs_target()
        if target is None:
            self.notify("Logs are not available for the current selection", severity="warning")
            return
        startup_target = self._require_target()
        if startup_target.context is None or startup_target.namespace is None:
            self.notify("Startup target is not resolved", severity="error")
            return
        pod_name, container_name = target
        self.push_screen(
            LogsScreen(
                context=startup_target.context,
                namespace=startup_target.namespace,
                pod_name=pod_name,
                container_name=container_name,
            )
        )

    def _command_delete(self) -> None:
        selection = self._selected_resource_name()
        target = self._require_target()
        if selection is None:
            self.notify("No resource selected", severity="warning")
            return
        if not self._can_delete_selected():
            self.notify(
                f"Delete is not supported for {self.current_view.value}", severity="warning"
            )
            return

        resource_view = self.current_view
        namespace_label = target.namespace or "default"
        self.push_screen(
            ConfirmActionScreen(
                "Delete resource",
                f"Delete {resource_view.value.rstrip('s')}/{selection} in namespace {namespace_label}?",
            ),
            callback=lambda confirmed: self._handle_delete_confirmation(
                confirmed, resource_view, selection, target.namespace
            ),
        )

    def _handle_delete_confirmation(
        self,
        confirmed: bool | None,
        view: ExplorerView,
        name: str,
        namespace: str | None,
    ) -> None:
        if not confirmed:
            return
        if namespace is None:
            self.notify("Namespace is not resolved", severity="error")
            return
        self.delete_selected_resource(view=view, name=name, namespace=namespace)

    @work(exclusive=True)
    async def delete_selected_resource(
        self, *, view: ExplorerView, name: str, namespace: str
    ) -> None:
        target = self._require_target()
        if target.context is None:
            self.notify("Context is not resolved", severity="error")
            return
        try:
            async with KubeClient(context=target.context) as kube_client:
                await delete_resource(kube_client, view=view, name=name, namespace=namespace)
        except Exception as error:
            self.notify(str(error), severity="error")
            return

        self.notify(f"Deleted {view.value.rstrip('s')}/{name}")
        self.refresh_current_view()

    def _command_restart(self) -> None:
        selection = self._selected_resource_name()
        target = self._require_target()
        if selection is None:
            self.notify("No resource selected", severity="warning")
            return
        if not self._can_restart_selected():
            self.notify(
                f"Restart is not supported for {self.current_view.value}", severity="warning"
            )
            return

        resource_view = self.current_view
        namespace_label = target.namespace or "default"
        self.push_screen(
            ConfirmActionScreen(
                "Restart resource",
                f"Restart {resource_view.value.rstrip('s')}/{selection} in namespace {namespace_label}?",
            ),
            callback=lambda confirmed: self._handle_restart_confirmation(
                confirmed, resource_view, selection, target.namespace
            ),
        )

    def _handle_restart_confirmation(
        self,
        confirmed: bool | None,
        view: ExplorerView,
        name: str,
        namespace: str | None,
    ) -> None:
        if not confirmed:
            return
        if namespace is None:
            self.notify("Namespace is not resolved", severity="error")
            return
        self.restart_selected_resource(view=view, name=name, namespace=namespace)

    @work(exclusive=True)
    async def restart_selected_resource(
        self, *, view: ExplorerView, name: str, namespace: str
    ) -> None:
        target = self._require_target()
        if target.context is None:
            self.notify("Context is not resolved", severity="error")
            return
        try:
            async with KubeClient(context=target.context) as kube_client:
                await restart_resource(kube_client, view=view, name=name, namespace=namespace)
        except Exception as error:
            self.notify(str(error), severity="error")
            return

        self.notify(f"Restarted {view.value.rstrip('s')}/{name}")
        self.refresh_current_view()

    def _command_refresh(self) -> None:
        self.refresh_current_view()
        self.notify(f"Refreshing {self.current_view.value}")

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
        self.refresh_current_view()
        self.notify(f"Switched namespace to {namespace}")

    def _command_context(self, context: str) -> None:
        current = self._require_target()
        self.resolved_startup_config = load_startup_targets(
            StartupConfig(context=context, namespace=current.namespace)
        )
        self.query_one("#startup-summary", Static).update(self._summary_text())
        self.refresh_current_view()
        self.notify(f"Switched context to {self.resolved_startup_config.context}")

    def _require_target(self) -> StartupConfig:
        if self.resolved_startup_config is None:
            raise ValueError("Startup target is not resolved")
        return self.resolved_startup_config

    def _selected_resource_name(self) -> str | None:
        pod_table = self.query_one("#pod-table", DataTable)
        cursor_row = pod_table.cursor_row
        rows = self._current_rows()
        if cursor_row is None or cursor_row < 0 or cursor_row >= len(rows):
            return None

        row = rows[cursor_row]
        return getattr(row, "name", None) if isinstance(getattr(row, "name", None), str) else None

    def _can_delete_selected(self) -> bool:
        return self.current_view in {
            ExplorerView.PODS,
            ExplorerView.DEPLOYMENTS,
            ExplorerView.STATEFULSETS,
            ExplorerView.SERVICES,
            ExplorerView.PVC,
            ExplorerView.SECRETS,
        }

    def _can_restart_selected(self) -> bool:
        return self.current_view in {ExplorerView.DEPLOYMENTS, ExplorerView.STATEFULSETS}

    def _can_open_logs_selected(self) -> bool:
        return self.current_view in {ExplorerView.PODS, ExplorerView.CONTAINERS}

    def _selected_logs_target(self) -> tuple[str, str | None] | None:
        pod_table = self.query_one("#pod-table", DataTable)
        cursor_row = pod_table.cursor_row
        if cursor_row is None or cursor_row < 0:
            return None
        if self.current_view is ExplorerView.PODS:
            if cursor_row >= len(self.pods):
                return None
            return (self.pods[cursor_row].name, None)
        if self.current_view is ExplorerView.CONTAINERS:
            if cursor_row >= len(self.containers):
                return None
            container = self.containers[cursor_row]
            return (container.pod, container.name)
        return None

    def _push_navigation_state(self) -> None:
        state = (self.current_view, self.container_pod_name)
        if not self.navigation_stack or self.navigation_stack[-1] != state:
            self.navigation_stack.append(state)
        self._update_back_button()

    def _update_back_button(self) -> None:
        self.query_one("#back-button", Button).display = bool(self.navigation_stack)

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
        rows = self._current_rows()
        if index is None or index >= len(rows):
            pod_details.update(f"{self._view_singular()}\n(no {self._view_singular()} selected)")
            return
        if self.current_view is ExplorerView.PODS:
            pod_details.update(render_pod_details(self.pods[index]))
        elif self.current_view is ExplorerView.CONTAINERS:
            pod_details.update(render_container_details(self.containers[index]))
        elif self.current_view is ExplorerView.CONTEXTS:
            pod_details.update(render_context_details(self.contexts[index]))
        elif self.current_view is ExplorerView.DEPLOYMENTS:
            pod_details.update(render_deployment_details(self.deployments[index]))
        elif self.current_view is ExplorerView.NAMESPACES:
            pod_details.update(render_namespace_details(self.namespaces[index]))
        elif self.current_view is ExplorerView.PVC:
            pod_details.update(render_pvc_details(self.pvcs[index]))
        elif self.current_view is ExplorerView.SECRETS:
            pod_details.update(render_secret_details(self.secrets[index]))
        elif self.current_view is ExplorerView.SERVICES:
            pod_details.update(render_service_details(self.services[index]))
        else:
            pod_details.update(render_statefulset_details(self.statefulsets[index]))

    def _configure_table_columns(self) -> None:
        pod_table = self.query_one("#pod-table", DataTable)
        pod_table.clear(columns=True)
        pod_table.add_column("Name", width=56)
        if self.current_view is ExplorerView.PODS:
            pod_table.add_columns(
                "Ready", "Status", "Restarts", "Age", "CPU", "Memory", "Containers"
            )
        elif self.current_view is ExplorerView.CONTAINERS:
            pod_table.add_columns("Ready", "State", "Restarts", "Image", "CPU", "Memory")
        elif self.current_view is ExplorerView.CONTEXTS:
            pod_table.add_columns("Cluster", "User", "Namespace", "Current")
        elif self.current_view is ExplorerView.DEPLOYMENTS:
            pod_table.add_columns(
                "Ready", "Up-to-date", "Available", "Age", "CPU", "Memory", "Containers"
            )
        elif self.current_view is ExplorerView.NAMESPACES:
            pod_table.add_columns("Status", "Age", "Current")
        elif self.current_view is ExplorerView.PVC:
            pod_table.add_columns("Status", "Volume", "Capacity", "Access", "StorageClass", "Age")
        elif self.current_view is ExplorerView.SECRETS:
            pod_table.add_columns("Type", "Data", "Immutable", "Age")
        elif self.current_view is ExplorerView.SERVICES:
            pod_table.add_columns("Type", "Cluster IP", "Ports", "Age", "Selector")
        else:
            pod_table.add_columns(
                "Ready", "Updated", "Current", "Age", "CPU", "Memory", "Containers"
            )

    def _current_rows(
        self,
    ) -> (
        list[ContainerSummary]
        | list[ContextSummary]
        | list[PodSummary]
        | list[DeploymentSummary]
        | list[NamespaceSummary]
        | list[PvcSummary]
        | list[SecretSummary]
        | list[ServiceSummary]
        | list[StatefulSetSummary]
    ):
        if self.current_view is ExplorerView.CONTAINERS:
            return self.containers
        if self.current_view is ExplorerView.CONTEXTS:
            return self.contexts
        if self.current_view is ExplorerView.PODS:
            return self.pods
        if self.current_view is ExplorerView.NAMESPACES:
            return self.namespaces
        if self.current_view is ExplorerView.DEPLOYMENTS:
            return self.deployments
        if self.current_view is ExplorerView.PVC:
            return self.pvcs
        if self.current_view is ExplorerView.SECRETS:
            return self.secrets
        if self.current_view is ExplorerView.SERVICES:
            return self.services
        return self.statefulsets

    def _panel_title(self) -> str:
        if self.current_view is ExplorerView.CONTAINERS:
            pod_name = self.container_pod_name or "-"
            return f"Containers ({pod_name})"
        if self.current_view is ExplorerView.CONTEXTS:
            return "Contexts"
        if self.current_view is ExplorerView.PODS:
            return "Pods"
        if self.current_view is ExplorerView.NAMESPACES:
            return "Namespaces"
        if self.current_view is ExplorerView.DEPLOYMENTS:
            return "Deployments"
        if self.current_view is ExplorerView.PVC:
            return "PVC"
        if self.current_view is ExplorerView.SECRETS:
            return "Secrets"
        if self.current_view is ExplorerView.SERVICES:
            return "Services"
        return "StatefulSets"

    def _details_title(self) -> str:
        if self.current_view is ExplorerView.CONTAINERS:
            return "Container Details"
        if self.current_view is ExplorerView.CONTEXTS:
            return "Context Details"
        if self.current_view is ExplorerView.PODS:
            return "Pod Details"
        if self.current_view is ExplorerView.NAMESPACES:
            return "Namespace Details"
        if self.current_view is ExplorerView.DEPLOYMENTS:
            return "Deployment Details"
        if self.current_view is ExplorerView.PVC:
            return "PVC Details"
        if self.current_view is ExplorerView.SECRETS:
            return "Secret Details"
        if self.current_view is ExplorerView.SERVICES:
            return "Service Details"
        return "StatefulSet Details"

    def _view_singular(self) -> str:
        if self.current_view is ExplorerView.CONTAINERS:
            return "container"
        if self.current_view is ExplorerView.CONTEXTS:
            return "context"
        if self.current_view is ExplorerView.PODS:
            return "pod"
        if self.current_view is ExplorerView.NAMESPACES:
            return "namespace"
        if self.current_view is ExplorerView.DEPLOYMENTS:
            return "deployment"
        if self.current_view is ExplorerView.PVC:
            return "pvc"
        if self.current_view is ExplorerView.SECRETS:
            return "secret"
        if self.current_view is ExplorerView.SERVICES:
            return "service"
        return "statefulset"

    def _summary_text(self) -> str:
        startup_config = self.resolved_startup_config or self.startup_config
        context = startup_config.context or "auto"
        namespace = startup_config.namespace or "auto"
        return f"kuno\ncontext: {context}\nnamespace: {namespace}"
