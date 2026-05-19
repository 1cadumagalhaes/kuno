from __future__ import annotations

import re
import time
from collections.abc import Iterable
from contextlib import suppress
from typing import ClassVar

from rich.syntax import Syntax
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, RichLog, Select, Static, Switch

from kuno.commands import ParsedCommand, parse_command, suggest_commands
from kuno.config import DEFAULT_CONFIG_PATH, KunoConfig, save_config
from kuno.k8s.actions import delete_resource, restart_resource
from kuno.k8s.client import KubeClient
from kuno.k8s.config import (
    UnknownContextError,
    load_available_context_names,
    load_context_summaries,
    load_startup_targets,
)
from kuno.k8s.resources import (
    get_resource_events,
    get_resource_yaml,
    list_deployments,
    list_namespace_events,
    list_namespace_summaries,
    list_namespaces,
    list_pod_containers,
    list_pods,
    list_pods_for_workload,
    list_pvcs,
    list_secrets,
    list_services,
    list_statefulsets,
    parse_since_duration,
    read_pod_logs,
    read_resource,
    render_container_details,
    render_context_details,
    render_deployment_details,
    render_describe_text,
    render_event_details,
    render_namespace_details,
    render_pod_details,
    render_pvc_details,
    render_secret_details,
    render_service_details,
    render_statefulset_details,
    stream_pod_logs,
    truncate_for_table,
)
from kuno.logs import LogMode, format_log_line, parse_log_line, rich_log_line
from kuno.models import (
    ContainerSummary,
    ContextSummary,
    DeploymentSummary,
    EventSummary,
    ExplorerView,
    NamespaceSummary,
    PodSource,
    PodSummary,
    PvcSummary,
    SecretSummary,
    ServiceSummary,
    StartupConfig,
    StatefulSetSummary,
    WorkloadSource,
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
        ("d", "open_detail", "Detail"),
        ("y", "copy_logs", "Copy"),
        ("f", "toggle_follow", "Follow"),
        ("l", "noop", ""),
        ("j", "next_line", "Next"),
        ("k", "previous_line", "Prev"),
        ("down", "next_line", ""),
        ("up", "previous_line", ""),
        ("g", "jump_top", "Top"),
        ("G", "jump_bottom", "Bottom"),
        ("m", "cycle_mode", "Mode"),
        ("s", "focus_since", "Since"),
        ("slash", "focus_filter", "Filter"),
        ("r", "reload", "Reload"),
        ("t", "toggle_timestamps", "Timestamps"),
        ("ctrl+u", "clear_filter", "Clear Filter"),
        ("w", "toggle_wrap", "Wrap"),
        ("ctrl+h", "previous_container", "Prev Ctnr"),
        ("ctrl+l", "next_container", "Next Ctnr"),
        ("bracketleft", "previous_replica", "Prev Pod"),
        ("bracketright", "next_replica", "Next Pod"),
        ("a", "all_replicas", "All Pods"),
    ]

    def __init__(
        self,
        *,
        context: str,
        namespace: str,
        logs_source: PodSource | WorkloadSource,
        kuno_config: KunoConfig,
    ) -> None:
        super().__init__()
        self.context = context
        self.filter_text = ""
        self.follow_enabled = True
        self.log_lines: list[str] = []
        self.mode = LogMode(kuno_config.log_mode) if kuno_config.log_mode in LogMode._value2member_map_ else LogMode.RAW
        self.namespace = namespace
        self.logs_source = logs_source
        self.pod_name = self._resolve_pod_name()
        self.container_name = self._resolve_container_name()
        self.details_visible = False
        self.rendered_log_spans: list[tuple[int, int, int]] = []
        self.selected_log_index = 0
        self.since_text = ""
        self.stream_workers: list = []
        self.timestamps_enabled = kuno_config.timestamps_enabled
        self.wrap_enabled = kuno_config.wrap_logs
        self.kuno_config = kuno_config

    def _resolve_pod_name(self) -> str:
        if isinstance(self.logs_source, WorkloadSource):
            if self.logs_source.pod_names:
                return f"{self.logs_source.kind}/{self.logs_source.name}"
            return self.logs_source.name
        return self.logs_source.pod_name

    def _resolve_container_name(self) -> str | None:
        if isinstance(self.logs_source, WorkloadSource):
            return None
        return self.logs_source.container_name

    def _is_multi_stream(self) -> bool:
        return isinstance(self.logs_source, WorkloadSource)

    def _current_pod_name(self) -> str | None:
        if not self._is_multi_stream():
            return self.pod_name
        focused = getattr(self, "focused_pod", None)
        if isinstance(self.logs_source, WorkloadSource):
            return focused or (self.logs_source.pod_names[0] if self.logs_source.pod_names else None)
        return None

    def compose(self) -> ComposeResult:
        target = self._display_target()
        yield Static(
            self._title_text(target),
            id="logs-title",
        )
        with Horizontal(id="logs-controls"):
            yield Input(placeholder="since (e.g. 5m, 1h)", id="logs-since")
            yield Input(placeholder="filter logs", id="logs-filter")
        with Horizontal(id="logs-body"):
            yield RichLog(id="logs-output", highlight=False, wrap=self.wrap_enabled)
            with Vertical(id="logs-detail-panel"):
                yield Static("Log Detail", id="logs-detail-title", classes="panel-title")
                yield Static("(no log selected)", id="logs-detail-content")
        yield Static("", id="logs-status")
        yield Footer()

    def on_mount(self) -> None:
        output = self.query_one("#logs-output", RichLog)
        output.focus()
        self.query_one("#logs-detail-panel", Vertical).display = False
        self.load_logs()

    @work(exclusive=True)
    async def load_logs(self) -> None:
        output = self.query_one("#logs-output", RichLog)
        output.clear()
        self.log_lines = []

        if self._is_multi_stream():
            await self._load_all_pod_logs()
        else:
            await self._load_single_pod_logs()

        if self.log_lines:
            self.selected_log_index = len(self.log_lines) - 1
        else:
            self.selected_log_index = 0
        self._render_logs()

    async def _load_single_pod_logs(self) -> None:
        output = self.query_one("#logs-output", RichLog)
        pod_name = self._current_pod_name()
        if pod_name is None:
            return
        try:
            async with KubeClient(context=self.context) as kube_client:
                logs = await read_pod_logs(
                    kube_client,
                    self.namespace,
                    pod_name,
                    container_name=self.container_name,
                    since_seconds=parse_since_duration(self.since_text),
                    timestamps=self.timestamps_enabled,
                )
        except Exception as error:
            output.write(f"error: {error}")
            return
        self.log_lines = logs.splitlines() if logs else []

    async def _load_all_pod_logs(self) -> None:
        output = self.query_one("#logs-output", RichLog)
        if not isinstance(self.logs_source, WorkloadSource):
            return
        merged: list[str] = []
        for pod_name in self.logs_source.pod_names:
            try:
                async with KubeClient(context=self.context) as kube_client:
                    logs = await read_pod_logs(
                        kube_client,
                        self.namespace,
                        pod_name,
                        container_name=None,
                        tail_lines=self.kuno_config.tail_lines,
                        timestamps=self.timestamps_enabled,
                    )
            except Exception as error:
                output.write(f"[{pod_name}] error: {error}")
                continue
            merged.extend(f"[{pod_name}] {line}" for line in logs.splitlines())
        self.log_lines = merged

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "logs-filter":
            self.filter_text = event.value
            self._render_logs()
        elif event.input.id == "logs-since":
            self.since_text = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "logs-since":
            self.load_logs()
            if self.follow_enabled:
                self._start_streaming()
        if event.input.id in ("logs-filter", "logs-since"):
            self.query_one("#logs-output", RichLog).focus()

    def on_click(self, event: events.Click) -> None:
        output = self.query_one("#logs-output", RichLog)
        offset = event.get_content_offset(output)
        if offset is None:
            return
        line_number = int(output.scroll_offset.y) + offset.y
        for index, start, end in self.rendered_log_spans:
            if start <= line_number <= end:
                if self.follow_enabled:
                    self.follow_enabled = False
                    self._stop_streaming()
                    self._update_title()
                self._move_selection(index)
                break

    def action_focus_filter(self) -> None:
        self.query_one("#logs-filter", Input).focus()

    def action_focus_since(self) -> None:
        self.query_one("#logs-since", Input).focus()

    def action_reload(self) -> None:
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def action_toggle_follow(self) -> None:
        self.follow_enabled = not self.follow_enabled
        self._update_title()
        if self.follow_enabled:
            self._start_streaming()
        else:
            self._stop_streaming()

    def action_cycle_mode(self) -> None:
        self.mode = {
            LogMode.RAW: LogMode.STRUCTURED,
            LogMode.STRUCTURED: LogMode.RAW,
        }[self.mode]
        self.kuno_config.log_mode = self.mode.value
        save_config(self.kuno_config)
        self._update_title()
        self._render_logs()

    def action_toggle_timestamps(self) -> None:
        self.timestamps_enabled = not self.timestamps_enabled
        self.kuno_config.timestamps_enabled = self.timestamps_enabled
        save_config(self.kuno_config)
        self._update_title()
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def action_toggle_wrap(self) -> None:
        self.wrap_enabled = not self.wrap_enabled
        self.kuno_config.wrap_logs = self.wrap_enabled
        save_config(self.kuno_config)
        self._update_title()
        self.query_one("#logs-output", RichLog).wrap = self.wrap_enabled
        self._render_logs()

    def action_clear_filter(self) -> None:
        log_filter = self.query_one("#logs-filter", Input)
        log_filter.value = ""
        self.filter_text = ""
        self._render_logs()

    def action_copy_logs(self) -> None:
        self.app.copy_to_clipboard("\n".join(self._display_lines_plain()))
        self.notify("Copied logs")

    def action_next_line(self) -> None:
        if self.follow_enabled:
            self.follow_enabled = False
            self._stop_streaming()
            self._update_title()
            self._render_logs()
            return
        visible = self._visible_log_indices()
        if not visible:
            return
        current = (
            visible.index(self.selected_log_index) if self.selected_log_index in visible else 0
        )
        self.selected_log_index = visible[min(current + 1, len(visible) - 1)]
        self._move_selection(self.selected_log_index)

    def action_previous_line(self) -> None:
        if self.follow_enabled:
            self.follow_enabled = False
            self._stop_streaming()
            self._update_title()
            self._render_logs()
            return
        visible = self._visible_log_indices()
        if not visible:
            return
        current = (
            visible.index(self.selected_log_index) if self.selected_log_index in visible else 0
        )
        self.selected_log_index = visible[max(current - 1, 0)]
        self._move_selection(self.selected_log_index)

    def action_jump_top(self) -> None:
        if self.follow_enabled:
            self.follow_enabled = False
            self._stop_streaming()
            self._update_title()
        visible = self._visible_log_indices()
        if not visible:
            return
        self.selected_log_index = visible[0]
        self._move_selection(self.selected_log_index)

    def action_jump_bottom(self) -> None:
        if self.follow_enabled:
            self.follow_enabled = False
            self._stop_streaming()
            self._update_title()
        visible = self._visible_log_indices()
        if not visible:
            return
        self.selected_log_index = visible[-1]
        self._move_selection(self.selected_log_index)

    def action_open_detail(self) -> None:
        self.details_visible = not self.details_visible
        self.query_one("#logs-detail-panel", Vertical).display = self.details_visible
        if self.details_visible:
            self._update_detail_panel()
        self._update_status()

    def action_previous_container(self) -> None:
        if self._is_multi_stream():
            return
        if not isinstance(self.logs_source, PodSource) or not self.logs_source.all_containers:
            return
        containers = self.logs_source.all_containers
        current = self.container_name
        if current is None and containers:
            idx = 0
        elif current in containers:
            idx = (containers.index(current) - 1) % len(containers)
        else:
            idx = 0
        self.container_name = containers[idx]
        self.pod_name = self.logs_source.pod_name
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def action_next_container(self) -> None:
        if self._is_multi_stream():
            return
        if not isinstance(self.logs_source, PodSource) or not self.logs_source.all_containers:
            return
        containers = self.logs_source.all_containers
        current = self.container_name
        if current is None and containers:
            idx = 0
        elif current in containers:
            idx = (containers.index(current) + 1) % len(containers)
        else:
            idx = 0
        self.container_name = containers[idx]
        self.pod_name = self.logs_source.pod_name
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def action_previous_replica(self) -> None:
        if not self._is_multi_stream() or not isinstance(self.logs_source, WorkloadSource):
            return
        self._cycle_replica(-1)

    def action_next_replica(self) -> None:
        if not self._is_multi_stream() or not isinstance(self.logs_source, WorkloadSource):
            return
        self._cycle_replica(1)

    def action_all_replicas(self) -> None:
        if not self._is_multi_stream() or not isinstance(self.logs_source, WorkloadSource):
            return
        if hasattr(self, "focused_pod"):
            delattr(self, "focused_pod")
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def _cycle_replica(self, direction: int) -> None:
        if not isinstance(self.logs_source, WorkloadSource):
            return
        pod_names = self.logs_source.pod_names
        if not pod_names:
            return
        current = getattr(self, "focused_pod", pod_names[0])
        idx = (pod_names.index(current) + direction) % len(pod_names) if current in pod_names else 0
        self.focused_pod = pod_names[idx]
        self.load_logs()
        if self.follow_enabled:
            self._start_streaming()

    def _move_selection(self, new_index: int) -> None:
        self._render_logs()

    def _render_logs(self) -> None:
        output = self.query_one("#logs-output", RichLog)
        output.clear()
        output.auto_scroll = self.follow_enabled
        self.rendered_log_spans = []
        visible = self._visible_log_indices()
        if visible:
            if self.follow_enabled:
                window = visible
                offset = 0
            else:
                WINDOW = 200
                try:
                    sel_pos = visible.index(self.selected_log_index)
                except ValueError:
                    sel_pos = len(visible) - 1
                half = WINDOW // 2
                win_start = max(0, sel_pos - half)
                win_end = min(len(visible), win_start + WINDOW)
                win_start = max(0, win_end - WINDOW)
                window = visible[win_start:win_end]
                offset = win_start
            for i, index in enumerate(window):
                entry = self._entry_renderables(self.log_lines[index], selected=index == self.selected_log_index)
                start = len(output.lines)
                for item in entry:
                    output.write(item)
                end = len(output.lines) - 1
                self.rendered_log_spans.append((index, start, end))
            if self.follow_enabled or self.selected_log_index == len(self.log_lines) - 1:
                output.scroll_end(animate=False, immediate=True, x_axis=False)
            else:
                for log_index, start_line, _end_line in self.rendered_log_spans:
                    if log_index == self.selected_log_index:
                        self.call_after_refresh(output.scroll_to, y=start_line, animate=False)
                        break
        elif self.log_lines:
            output.write("(no matching log lines)")
        else:
            output.write("(no logs)")
        self._update_detail_panel()

    def _update_status(self) -> None:
        total = len(self.log_lines)
        visible = self._visible_log_indices()
        shown = len(visible)
        if self.filter_text:
            text = f"{shown}/{total} lines  filter: {self.filter_text!r}"
        elif shown < total:
            text = f"showing {shown}/{total} lines"
        else:
            text = f"{total} lines"
        if self.follow_enabled:
            text += "  [following]"
        self.query_one("#logs-status", Static).update(text)

    async def stream_logs_single(self, pod_name: str, container_name: str | None) -> None:
        output = self.query_one("#logs-output", RichLog)
        prefix = f"[{pod_name}] " if self._is_multi_stream() else ""
        try:
            async with KubeClient(context=self.context) as kube_client:
                async for line in stream_pod_logs(
                    kube_client,
                    self.namespace,
                    pod_name,
                    container_name=container_name,
                    since_seconds=parse_since_duration(self.since_text),
                    timestamps=self.timestamps_enabled,
                ):
                    prefixed = f"{prefix}{line}"
                    self.log_lines.append(prefixed)
                    self.selected_log_index = len(self.log_lines) - 1
                    if self.filter_text and self.filter_text not in prefixed:
                        continue
                    rendered = self._entry_renderables(prefixed, selected=True)
                    for item in rendered:
                        output.write(item)
                    output.scroll_end(animate=False, immediate=True, x_axis=False)
                    self._update_status()
        except Exception as error:
            output.write(f"{prefix}error: {error}")

    def _start_streaming(self) -> None:
        self._stop_streaming()
        if self._is_multi_stream() and isinstance(self.logs_source, WorkloadSource):
            pod_names = (
                [self.focused_pod]
                if hasattr(self, "focused_pod") and self.focused_pod
                else self.logs_source.pod_names
            )
            for pod_name in pod_names:
                worker = self.run_worker(
                    self.stream_logs_single(pod_name, None),
                    exclusive=False,
                    group="logs-stream",
                )
                self.stream_workers.append(worker)
        else:
            pod_name = self._current_pod_name()
            if pod_name is None:
                return
            worker = self.run_worker(
                self.stream_logs_single(pod_name, self.container_name),
                exclusive=True,
                group="logs-stream",
            )
            self.stream_workers.append(worker)

    def _stop_streaming(self) -> None:
        for worker in self.stream_workers:
            worker.cancel()
        self.stream_workers = []

    def _display_target(self) -> str:
        if isinstance(self.logs_source, WorkloadSource):
            return f"{self.logs_source.kind}/{self.logs_source.name}"
        if self.container_name:
            return f"{self.logs_source.pod_name}/{self.container_name}"
        return self.logs_source.pod_name

    def _title_text(self, target: str) -> str:
        follow = "on" if self.follow_enabled else "off"
        mode = self.mode.value
        timestamps = "on" if self.timestamps_enabled else "off"
        wrap = "on" if self.wrap_enabled else "off"
        if isinstance(self.logs_source, WorkloadSource):
            focused = getattr(self, "focused_pod", None)
            replica_info = (
                f"pod: {focused}"
                if focused
                else f"all {len(self.logs_source.pod_names)} pods"
            )
            return (
                "Logs\n"
                f"context: {self.context}\n"
                f"namespace: {self.namespace}\n"
                f"target: {target}\n"
                f"mode: {mode} [m]  follow: {follow} [f]  timestamps: {timestamps} [t]  wrap: {wrap} [w]\n"
                f"{replica_info}  since: {self.since_text or 'all'} [s]  filter: /  reload: r  clear filter: ctrl+u  back: esc"
            )
        return (
            "Logs\n"
            f"context: {self.context}\n"
            f"namespace: {self.namespace}\n"
            f"target: {target}\n"
            f"mode: {mode} [m]  follow: {follow} [f]  timestamps: {timestamps} [t]  wrap: {wrap} [w]\n"
            f"since: {self.since_text or 'all'} [s]  filter: /  reload: r  clear filter: ctrl+u  back: esc"
        )

    def _update_title(self) -> None:
        self.query_one("#logs-title", Static).update(self._title_text(self._display_target()))

    def action_close(self) -> None:
        self._stop_streaming()
        self.app.pop_screen()

    def action_noop(self) -> None:
        pass

    def _display_lines_plain(self) -> list[str]:
        lines: list[str] = []
        for raw_line in self.log_lines:
            lines.extend(format_log_line(raw_line, self.mode))
        return lines

    def _update_detail_panel(self) -> None:
        if not self.details_visible:
            return
        title = self.query_one("#logs-detail-title", Static)
        detail = self.query_one("#logs-detail-content", Static)
        visible = self._visible_log_indices()
        if not visible:
            title.update("Log Detail")
            detail.update("(no log selected)")
            return
        index = self.selected_log_index if self.selected_log_index in visible else visible[0]
        raw_line = self.log_lines[index]
        parsed = parse_log_line(raw_line)
        title.update(f"Log Detail ({index + 1}/{len(visible)})")
        timestamp = f"timestamp: {parsed.timestamp}\n\n" if parsed.timestamp else ""
        body = format_log_line(raw_line, LogMode.STRUCTURED)[0]
        detail.update(f"{timestamp}{body}")

    def _visible_log_indices(self) -> list[int]:
        visible: list[int] = []
        for index, raw_line in enumerate(self.log_lines):
            rendered = format_log_line(raw_line, self.mode)
            if self.filter_text and not any(self.filter_text in line for line in rendered):
                continue
            visible.append(index)
        if visible and self.selected_log_index not in visible:
            self.selected_log_index = visible[0]
        return visible

    def _entry_renderables(self, raw_line: str, *, selected: bool) -> list[Text | str]:
        return [rich_log_line(raw_line, self.mode, selected=selected and not self.follow_enabled)]


class ManifestScreen(Screen[None]):
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "close", "Back"),
        ("y", "copy_manifest", "Copy"),
        ("/", "toggle_search", "Search"),
        ("n", "next_match", "Next match"),
        ("N", "prev_match", "Prev match"),
        ("]", "next_key", "Next key"),
        ("[", "prev_key", "Prev key"),
        ("j", "scroll_down", ""),
        ("k", "scroll_up", ""),
        ("h", "scroll_left", ""),
        ("l", "scroll_right", ""),
        ("g", "scroll_top", "Top"),
        ("G", "scroll_bottom", "Bottom"),
        ("down", "scroll_down", ""),
        ("up", "scroll_up", ""),
    ]

    def __init__(
        self, *, yaml_content: str, resource_name: str, yaml_theme: str
    ) -> None:
        super().__init__()
        self.yaml_content = yaml_content
        self.resource_name = resource_name
        self.yaml_theme = yaml_theme
        self._lines: list[str] = yaml_content.splitlines()
        self._match_indices: list[int] = []
        self._match_cursor: int = 0
        self._key_lines: list[int] = [
            i for i, ln in enumerate(self._lines)
            if ln.lstrip().lstrip("- ").split(":")[0].strip()
            and ":" in ln
            and not ln.lstrip().startswith("#")
            and re.match(r"^\s*-?\s*[\w\"'][^:]*:", ln) is not None
        ]
        self._key_cursor: int = 0
        self._search_open: bool = False

    def compose(self) -> ComposeResult:
        yield Static(f"YAML — {self.resource_name}", id="manifest-title")
        with Horizontal(id="manifest-controls"):
            yield Input(placeholder="search  (escape to close)", id="manifest-search")
            yield Static("", id="manifest-match-status")
        with VerticalScroll(id="manifest-panel"):
            yield Static(id="manifest-output")
        yield Footer()

    def on_mount(self) -> None:
        self._render_yaml()
        self.query_one("#manifest-controls").display = False
        self.query_one("#manifest-panel").focus()

    def on_theme_changed(self) -> None:
        self._render_yaml()

    def _syntax_theme(self) -> str:
        t = self.app.get_theme(self.app.theme)
        return "ansi_dark" if (t is None or t.dark) else "ansi_light"

    def _render_yaml(self, highlight_line: int | None = None) -> None:
        output = self.query_one("#manifest-output", Static)
        syntax = Syntax(
            self.yaml_content,
            "yaml",
            theme=self._syntax_theme(),
            line_numbers=True,
            highlight_lines={highlight_line + 1} if highlight_line is not None else set(),
        )
        output.update(syntax)

    def _update_match_status(self) -> None:
        status = self.query_one("#manifest-match-status", Static)
        if not self._match_indices:
            status.update("")
        else:
            status.update(f"{self._match_cursor + 1}/{len(self._match_indices)}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "manifest-search":
            return
        term = event.value.strip().lower()
        if not term:
            self._match_indices = []
            self._match_cursor = 0
            self._render_yaml()
            self._update_match_status()
            return
        self._match_indices = [i for i, ln in enumerate(self._lines) if term in ln.lower()]
        self._match_cursor = 0
        hl = self._match_indices[0] if self._match_indices else None
        self._render_yaml(highlight_line=hl)
        self._update_match_status()
        if hl is not None:
            self._scroll_to_line(hl)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "manifest-search":
            self.query_one("#manifest-panel").focus()

    def on_key(self, event: events.Key) -> None:
        search = self.query_one("#manifest-search", Input)
        if search.has_focus and event.key == "escape":
            event.stop()
            self._close_search()

    def _close_search(self) -> None:
        self._search_open = False
        self.query_one("#manifest-controls").display = False
        self.query_one("#manifest-panel").focus()

    def _scroll_to_line(self, line_index: int) -> None:
        scroll = self.query_one("#manifest-panel", VerticalScroll)
        output = self.query_one("#manifest-output", Static)
        total_lines = len(self._lines)
        if total_lines == 0:
            return
        ratio = line_index / total_lines
        scroll.scroll_to(y=ratio * output.virtual_size.height, animate=False)

    def _panel_focused(self) -> bool:
        return self.query_one("#manifest-panel").has_focus

    def action_toggle_search(self) -> None:
        if self._search_open:
            self._close_search()
        else:
            self._search_open = True
            self.query_one("#manifest-controls").display = True
            self.query_one("#manifest-search", Input).focus()

    def action_next_match(self) -> None:
        if not self._match_indices:
            return
        self._match_cursor = (self._match_cursor + 1) % len(self._match_indices)
        hl = self._match_indices[self._match_cursor]
        self._render_yaml(highlight_line=hl)
        self._update_match_status()
        self._scroll_to_line(hl)

    def action_prev_match(self) -> None:
        if not self._match_indices:
            return
        self._match_cursor = (self._match_cursor - 1) % len(self._match_indices)
        hl = self._match_indices[self._match_cursor]
        self._render_yaml(highlight_line=hl)
        self._update_match_status()
        self._scroll_to_line(hl)

    def action_next_key(self) -> None:
        if not self._key_lines:
            return
        self._key_cursor = (self._key_cursor + 1) % len(self._key_lines)
        line = self._key_lines[self._key_cursor]
        self._render_yaml(highlight_line=line)
        self._scroll_to_line(line)

    def action_prev_key(self) -> None:
        if not self._key_lines:
            return
        self._key_cursor = (self._key_cursor - 1) % len(self._key_lines)
        line = self._key_lines[self._key_cursor]
        self._render_yaml(highlight_line=line)
        self._scroll_to_line(line)

    def action_scroll_down(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_up(animate=False)

    def action_scroll_left(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_left(animate=False)

    def action_scroll_right(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_right(animate=False)

    def action_scroll_top(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        if self._panel_focused():
            self.query_one("#manifest-panel", VerticalScroll).scroll_end(animate=False)

    def action_copy_manifest(self) -> None:
        self.app.copy_to_clipboard(self.yaml_content)
        self.notify("Copied YAML to clipboard")

    def action_close(self) -> None:
        self.app.pop_screen()


class DescribeScreen(Screen[None]):
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "close", "Back"),
        ("y", "copy_describe", "Copy"),
        ("/", "toggle_search", "Search"),
        ("n", "next_match", "Next match"),
        ("N", "prev_match", "Prev match"),
        ("j", "scroll_down", ""),
        ("k", "scroll_up", ""),
        ("g", "scroll_top", "Top"),
        ("G", "scroll_bottom", "Bottom"),
        ("down", "scroll_down", ""),
        ("up", "scroll_up", ""),
    ]

    def __init__(
        self, *, describe_text: str, resource_name: str, events: list[EventSummary] | None = None
    ) -> None:
        super().__init__()
        self.describe_text = describe_text
        self.resource_name = resource_name
        self.events = events or []
        self._lines: list[str] = describe_text.splitlines()
        self._match_indices: list[int] = []
        self._match_cursor: int = 0
        self._search_open: bool = False

    def compose(self) -> ComposeResult:
        yield Static(f"Describe — {self.resource_name}", id="describe-title")
        with Horizontal(id="describe-controls"):
            yield Input(placeholder="search  (escape to close)", id="describe-search")
            yield Static("", id="describe-match-status")
        with Horizontal(id="describe-body"):
            with VerticalScroll(id="describe-panel"):
                yield Static("", id="describe-content")
            if self.events:
                with Vertical(id="describe-events-panel"):
                    yield Static("Events", id="describe-events-title", classes="panel-title")
                    yield Static("", id="describe-events")
        yield Footer()

    def on_mount(self) -> None:
        self._render_content()
        if self.events:
            lines = [
                f"  {ev.age:>10}  {ev.type:>7}  {ev.reason:<20}  {ev.count:>3}  {ev.message}"
                for ev in self.events
            ]
            self.query_one("#describe-events", Static).update(
                "\n".join(lines) if lines else "  (none)"
            )
        self.query_one("#describe-controls").display = False
        self.query_one("#describe-panel").focus()

    def _render_content(self, highlight_line: int | None = None) -> None:
        if highlight_line is None:
            self.query_one("#describe-content", Static).update(self.describe_text)
            return
        text = Text()
        for i, ln in enumerate(self._lines):
            if i == highlight_line:
                text.append(ln + "\n", style="bold reverse")
            else:
                text.append(ln + "\n")
        self.query_one("#describe-content", Static).update(text)

    def _update_match_status(self) -> None:
        status = self.query_one("#describe-match-status", Static)
        if not self._match_indices:
            status.update("")
        else:
            status.update(f"{self._match_cursor + 1}/{len(self._match_indices)}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "describe-search":
            return
        term = event.value.strip().lower()
        if not term:
            self._match_indices = []
            self._match_cursor = 0
            self._render_content()
            self._update_match_status()
            return
        self._match_indices = [i for i, ln in enumerate(self._lines) if term in ln.lower()]
        self._match_cursor = 0
        hl = self._match_indices[0] if self._match_indices else None
        self._render_content(highlight_line=hl)
        self._update_match_status()
        if hl is not None:
            self._scroll_to_line(hl)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "describe-search":
            self.query_one("#describe-panel").focus()

    def on_key(self, event: events.Key) -> None:
        search = self.query_one("#describe-search", Input)
        if search.has_focus and event.key == "escape":
            event.stop()
            self._close_search()

    def _close_search(self) -> None:
        self._search_open = False
        self.query_one("#describe-controls").display = False
        self.query_one("#describe-panel").focus()

    def _scroll_to_line(self, line_index: int) -> None:
        scroll = self.query_one("#describe-panel", VerticalScroll)
        output = self.query_one("#describe-content", Static)
        total_lines = len(self._lines)
        if total_lines == 0:
            return
        ratio = line_index / total_lines
        scroll.scroll_to(y=ratio * output.virtual_size.height, animate=False)

    def _panel_focused(self) -> bool:
        return self.query_one("#describe-panel").has_focus

    def action_toggle_search(self) -> None:
        if self._search_open:
            self._close_search()
        else:
            self._search_open = True
            self.query_one("#describe-controls").display = True
            self.query_one("#describe-search", Input).focus()

    def action_next_match(self) -> None:
        if not self._match_indices:
            return
        self._match_cursor = (self._match_cursor + 1) % len(self._match_indices)
        hl = self._match_indices[self._match_cursor]
        self._render_content(highlight_line=hl)
        self._update_match_status()
        self._scroll_to_line(hl)

    def action_prev_match(self) -> None:
        if not self._match_indices:
            return
        self._match_cursor = (self._match_cursor - 1) % len(self._match_indices)
        hl = self._match_indices[self._match_cursor]
        self._render_content(highlight_line=hl)
        self._update_match_status()
        self._scroll_to_line(hl)

    def action_scroll_down(self) -> None:
        if self._panel_focused():
            self.query_one("#describe-panel", VerticalScroll).scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        if self._panel_focused():
            self.query_one("#describe-panel", VerticalScroll).scroll_up(animate=False)

    def action_scroll_top(self) -> None:
        if self._panel_focused():
            self.query_one("#describe-panel", VerticalScroll).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        if self._panel_focused():
            self.query_one("#describe-panel", VerticalScroll).scroll_end(animate=False)

    def action_copy_describe(self) -> None:
        full = self.describe_text
        if self.events:
            full += "\n\nEvents:\n"
            for ev in self.events:
                full += f"  {ev.age:>10}  {ev.type:>7}  {ev.reason:<20}  {ev.count:>3}  {ev.message}\n"
        self.app.copy_to_clipboard(full)
        self.notify("Copied description to clipboard")

    def action_close(self) -> None:
        self.app.pop_screen()


class EventsScreen(Screen[None]):
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "close", "Back"),
        ("d", "open_event_detail", "Detail"),
        ("/", "toggle_search", "Search"),
        ("j", "next_row", "Next"),
        ("k", "previous_row", "Prev"),
        ("g", "jump_top", "Top"),
        ("G", "jump_bottom", "Bottom"),
        ("down", "next_row", ""),
        ("up", "previous_row", ""),
    ]

    def __init__(self, *, events: list[EventSummary], title: str) -> None:
        super().__init__()
        self.events = events
        self._visible_events: list[EventSummary] = list(events)
        self.screen_title = title
        self._search_open: bool = False

    def compose(self) -> ComposeResult:
        yield Static(self.screen_title, id="events-title")
        with Horizontal(id="events-controls"):
            yield Input(placeholder="search  (escape to close)", id="events-search")
            yield Static("", id="events-match-status")
        with Horizontal(id="events-body"):
            yield DataTable(id="events-table")
            with Vertical(id="events-detail-panel"):
                yield Static("Event Detail", id="events-detail-title", classes="panel-title")
                yield Static("(no event selected)", id="events-detail-content")
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_table()
        self.query_one("#events-controls").display = False
        self.query_one("#events-detail-panel", Vertical).display = False
        self.query_one("#events-table").focus()

    def _rebuild_table(self) -> None:
        table = self.query_one("#events-table", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Type", "Reason", "Age", "Count", "Message")
        for ev in self._visible_events:
            table.add_row(ev.type, ev.reason, ev.age, str(ev.count), ev.message)
        self._update_match_status()

    def _update_match_status(self) -> None:
        status = self.query_one("#events-match-status", Static)
        search = self.query_one("#events-search", Input)
        if not search.value.strip():
            status.update("")
        else:
            status.update(f"{len(self._visible_events)}/{len(self.events)}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "events-search":
            return
        term = event.value.strip().lower()
        if not term:
            self._visible_events = list(self.events)
        else:
            self._visible_events = [
                ev for ev in self.events
                if term in ev.type.lower()
                or term in ev.reason.lower()
                or term in ev.message.lower()
            ]
        self._rebuild_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "events-search":
            self.query_one("#events-table").focus()

    def on_key(self, event: events.Key) -> None:
        search = self.query_one("#events-search", Input)
        if search.has_focus and event.key == "escape":
            event.stop()
            self._close_search()

    def _close_search(self) -> None:
        self._search_open = False
        self.query_one("#events-controls").display = False
        self.query_one("#events-table").focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row >= len(self._visible_events):
            return
        self.query_one("#events-detail-content", Static).update(
            render_event_details(self._visible_events[event.cursor_row])
        )

    def action_toggle_search(self) -> None:
        if self._search_open:
            self._close_search()
        else:
            self._search_open = True
            self.query_one("#events-controls").display = True
            self.query_one("#events-search", Input).focus()

    def action_open_event_detail(self) -> None:
        self.query_one("#events-detail-panel", Vertical).display = not self.query_one(
            "#events-detail-panel", Vertical
        ).display

    def action_next_row(self) -> None:
        table = self.query_one("#events-table", DataTable)
        table.move_cursor(row=min(table.cursor_row + 1, table.row_count - 1), animate=False)

    def action_previous_row(self) -> None:
        table = self.query_one("#events-table", DataTable)
        table.move_cursor(row=max(table.cursor_row - 1, 0), animate=False)

    def action_jump_top(self) -> None:
        self.query_one("#events-table", DataTable).move_cursor(row=0, animate=False)

    def action_jump_bottom(self) -> None:
        table = self.query_one("#events-table", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1, animate=False)

    def action_close(self) -> None:
        self.app.pop_screen()


class KunoApp(App[None]):
    CSS_PATH = "app.tcss"
    MAX_COMMAND_SUGGESTIONS = 4
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("backspace", "go_back", "Back"),
        ("ctrl+d", "describe_selected", "Describe"),
        ("d", "toggle_details", "Details"),
        ("e", "events_selected", "Events"),
        ("l", "open_logs", "Logs"),
        ("colon", "open_command_bar", "Command"),
        ("escape", "close_command_bar", "Close"),
        ("r", "refresh_pods", "Refresh"),
        ("y", "yaml_selected", "YAML"),
    ]

    def __init__(self, startup_config: StartupConfig, kuno_config: KunoConfig | None = None) -> None:
        super().__init__()
        self.kuno_config = kuno_config if kuno_config is not None else KunoConfig(path=DEFAULT_CONFIG_PATH)
        self.available_contexts: list[str] = []
        self.available_namespaces: list[str] = []
        self.command_bar_visible = False
        self.command_suggestions: list[str] = []
        self.command_suggestion_index = 0
        self.container_pod_name: str | None = None
        self.containers: list[ContainerSummary] = []
        self.contexts: list[ContextSummary] = []
        self.current_view = ExplorerView.PODS
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
        self._pending_single_container_check = False
        self.debug_enabled = False

    def _dblog(self, msg: str) -> None:
        if not self.debug_enabled:
            return
        ts = time.strftime("%H:%M:%S")
        try:
            with open("/tmp/kuno_debug.log", "a") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

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
        self._dblog("on_mount start")
        self.theme = self.kuno_config.theme
        back_button = self.query_one("#back-button", Button)
        self._dblog(f"theme set to {self.theme}")
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
        self._dblog(f"available contexts: {self.available_contexts}")
        try:
            self.resolved_startup_config = load_startup_targets(self.startup_config)
            self._dblog(f"resolved_startup={self.resolved_startup_config}")
        except UnknownContextError as error:
            self._dblog(f"UnknownContextError: {error}")
            summary.update(f"kuno\nerror: {error}")
            pod_details.update("pod\n(startup failed)")
            return

        summary.update(self._summary_text())
        self._dblog("calling refresh_current_view")
        self.refresh_current_view()
        self._dblog("on_mount done")

    @work(exclusive=True)
    async def refresh_current_view(self) -> None:
        self._dblog(f"refresh_current_view started, view={self.current_view}")
        try:
            await self._do_refresh_current_view()
        except Exception as error:
            self._dblog(f"refresh_current_view ERROR: {error}")
            self.notify(
                f"Error loading {self.current_view.value}: {error}",
                severity="error",
                timeout=10,
            )

    async def _do_refresh_current_view(self) -> None:
        pod_details = self.query_one("#pod-details", Static)
        if self.resolved_startup_config is None:
            self._dblog("resolved_startup_config is None")
            pod_details.update(f"{self._view_singular()}\n(startup not resolved)")
            return

        context = self.resolved_startup_config.context
        namespace = self.resolved_startup_config.namespace
        if context is None or namespace is None:
            self._dblog(f"context/namespace is None: ctx={context}, ns={namespace}")
            pod_details.update(f"{self._view_singular()}\n(startup not resolved)")
            return

        self._dblog(f"connecting to context={context}, namespace={namespace}")
        try:
            async with KubeClient(context=context) as kube_client:
                self._dblog("kube client connected")
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

        if self._pending_single_container_check and self.current_view is ExplorerView.CONTAINERS:
            self._pending_single_container_check = False
            if len(self.containers) == 1:
                self.navigation_stack.pop()
                self._update_back_button()
                target = self._require_target()
                if target.context and target.namespace:
                    self.push_screen(
                        LogsScreen(
                            context=target.context,
                            namespace=target.namespace,
                            logs_source=PodSource(
                                pod_name=self.container_pod_name or "",
                                container_name=self.containers[0].name,
                            ),
                            kuno_config=self.kuno_config,
                        )
                    )

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
        self._pending_single_container_check = True
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

    def action_describe_selected(self) -> None:
        self._command_describe()

    def action_yaml_selected(self) -> None:
        self._command_yaml()

    def action_events_selected(self) -> None:
        self._command_events()

    def _command_describe(self) -> None:
        selection = self._selected_resource_name()
        if selection is None:
            self.notify("No resource selected", severity="warning")
            return
        target = self._require_target()
        if target.context is None or target.namespace is None:
            return
        self._open_describe_async(selection, target)

    @work(exclusive=True)
    async def _open_describe_async(self, name: str, target: StartupConfig) -> None:
        context = target.context
        namespace = target.namespace
        if context is None or namespace is None:
            return
        kind = self.current_view.value.rstrip("s")
        try:
            async with KubeClient(context=context) as kube_client:
                item = await read_resource(kube_client, namespace, kind, name)
                describe_text = render_describe_text(item)
                events = await get_resource_events(kube_client, namespace, kind, name)
        except Exception as error:
            self.notify(f"Failed to describe {kind}/{name}: {error}", severity="error")
            return
        self.push_screen(
            DescribeScreen(
                describe_text=describe_text,
                resource_name=f"{kind}/{name}",
                events=events,
            )
        )

    def _command_yaml(self) -> None:
        selection = self._selected_resource_name()
        if selection is None:
            self.notify("No resource selected", severity="warning")
            return
        target = self._require_target()
        if target.context is None or target.namespace is None:
            return
        self._open_yaml_async(selection, target)

    @work(exclusive=True)
    async def _open_yaml_async(self, name: str, target: StartupConfig) -> None:
        context = target.context
        namespace = target.namespace
        if context is None or namespace is None:
            return
        kind = self.current_view.value.rstrip("s")
        try:
            async with KubeClient(context=context) as kube_client:
                yaml_content = await get_resource_yaml(kube_client, namespace, kind, name)
        except Exception as error:
            self.notify(f"Failed to get YAML for {kind}/{name}: {error}", severity="error")
            return
        self.push_screen(
            ManifestScreen(
                yaml_content=yaml_content,
                resource_name=f"{kind}/{name}",
                yaml_theme=self.kuno_config.yaml_theme,
            )
        )

    def _command_events(self) -> None:
        selection = self._selected_resource_name()
        if selection is None:
            self._command_namespace_events()
            return
        target = self._require_target()
        if target.context is None or target.namespace is None:
            return
        self._open_events_async(selection, target)

    @work(exclusive=True)
    async def _open_events_async(self, name: str, target: StartupConfig) -> None:
        context = target.context
        namespace = target.namespace
        if context is None or namespace is None:
            return
        kind = self.current_view.value.rstrip("s")
        try:
            async with KubeClient(context=context) as kube_client:
                events = await get_resource_events(kube_client, namespace, kind, name)
        except Exception as error:
            self.notify(f"Failed to get events: {error}", severity="error")
            return
        self.push_screen(
            EventsScreen(
                events=events,
                title=f"Events — {kind}/{name}",
            )
        )

    @work(exclusive=True)
    async def _command_namespace_events(self) -> None:
        target = self._require_target()
        if target.context is None or target.namespace is None:
            return
        context = target.context
        namespace = target.namespace
        try:
            async with KubeClient(context=context) as kube_client:
                events = await list_namespace_events(kube_client, namespace)
        except Exception as error:
            self.notify(f"Failed to get events: {error}", severity="error")
            return
        self.push_screen(
            EventsScreen(
                events=events,
                title=f"Events — {namespace}",
            )
        )

    def _command_logs(self) -> None:
        logs_source = self._selected_logs_source()
        if logs_source is None:
            self.notify("Logs are not available for the current selection", severity="warning")
            return
        startup_target = self._require_target()
        if startup_target.context is None or startup_target.namespace is None:
            self.notify("Startup target is not resolved", severity="error")
            return
        self._open_logs_screen_async(logs_source, startup_target)

    @work(exclusive=True)
    async def _open_logs_screen_async(
        self, logs_source: PodSource | WorkloadSource, startup_target: StartupConfig
    ) -> None:
        context = startup_target.context
        namespace = startup_target.namespace
        if context is None or namespace is None:
            return

        if isinstance(logs_source, WorkloadSource):
            try:
                async with KubeClient(context=context) as kube_client:
                    pod_names = await list_pods_for_workload(
                        kube_client, namespace, logs_source.kind, logs_source.name
                    )
                if not pod_names:
                    self.notify(
                        f"No pods found for {logs_source.kind}/{logs_source.name}",
                        severity="warning",
                    )
                    return
                logs_source.pod_names = pod_names
            except Exception as error:
                self.notify(f"Failed to resolve pods: {error}", severity="error")
                return

        self.push_screen(
            LogsScreen(
                context=context,
                namespace=namespace,
                logs_source=logs_source,
                kuno_config=self.kuno_config,
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
        self.kuno_config.theme = theme_name
        save_config(self.kuno_config)
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
        return self.current_view in {
            ExplorerView.PODS,
            ExplorerView.CONTAINERS,
            ExplorerView.DEPLOYMENTS,
            ExplorerView.STATEFULSETS,
        }

    def _selected_logs_source(self) -> PodSource | WorkloadSource | None:
        pod_table = self.query_one("#pod-table", DataTable)
        cursor_row = pod_table.cursor_row
        if cursor_row is None or cursor_row < 0:
            return None
        if self.current_view is ExplorerView.PODS:
            if cursor_row >= len(self.pods):
                return None
            return PodSource(pod_name=self.pods[cursor_row].name)
        if self.current_view is ExplorerView.CONTAINERS:
            if cursor_row >= len(self.containers):
                return None
            container = self.containers[cursor_row]
            return PodSource(
                pod_name=container.pod,
                container_name=container.name,
            )
        if self.current_view is ExplorerView.DEPLOYMENTS:
            if cursor_row >= len(self.deployments):
                return None
            deployment = self.deployments[cursor_row]
            return WorkloadSource(
                kind="deployment",
                name=deployment.name,
                pod_names=[],
                namespace=self._require_target().namespace or "",
            )
        if self.current_view is ExplorerView.STATEFULSETS:
            if cursor_row >= len(self.statefulsets):
                return None
            sts = self.statefulsets[cursor_row]
            return WorkloadSource(
                kind="statefulset",
                name=sts.name,
                pod_names=[],
                namespace=self._require_target().namespace or "",
            )
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
        if index is None or index < 0 or index >= len(rows):
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
