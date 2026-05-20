from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.style import Style
from rich.text import Lines, Text
from textual.geometry import Size
from textual.reactive import var
from textual.scroll_view import ScrollView
from textual.selection import Selection
from textual.strip import Strip

from kuno.logs import LogMode, rich_log_line

if TYPE_CHECKING:
    pass


class LogView(ScrollView, can_focus=True):
    ALLOW_SELECT = True

    DEFAULT_CSS = """
    LogView {
        background: transparent;
        color: $text;
        overflow: auto;
        &:focus {
            background-tint: $foreground 5%;
        }
    }
    """

    auto_scroll: var[bool] = var(True)

    def __init__(
        self,
        *,
        mode: LogMode = LogMode.RAW,
        max_lines: int = 50_000,
        wrap: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.mode = mode
        self.max_lines = max_lines
        self.wrap = wrap
        self._lines: list[str] = []
        self._cumulative: list[int] = []
        self._cache: dict[int, Lines] = {}
        self._width = 0
        self._max_cell_width = 0
        self.selected_index: int = -1
        self.follow_mode: bool = True

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def clear(self) -> None:
        self._lines.clear()
        self._cumulative.clear()
        self._cache.clear()
        self._max_cell_width = 0
        self.virtual_size = Size(0, 0)
        self.selected_index = -1

    def _content_width(self) -> int:
        if self.wrap:
            return 0
        return max(self._max_cell_width, 1)

    def _update_virtual_size(self) -> None:
        height = self._cumulative[-1] if self._cumulative else 0
        self.virtual_size = Size(self._content_width(), height)

    def append(self, line: str) -> None:
        self._lines.append(line)
        idx = len(self._lines) - 1
        wrapped = self._wrap_line(line)
        count = len(wrapped)
        self._cache[idx] = wrapped
        prev = self._cumulative[-1] if self._cumulative else 0
        self._cumulative.append(prev + count)
        cell_w = cell_len(line.expandtabs())
        if cell_w > self._max_cell_width:
            self._max_cell_width = cell_w
        self._update_virtual_size()
        if self.auto_scroll:
            self.scroll_end(animate=False, immediate=True, x_axis=False)

    def append_many(self, lines: list[str]) -> None:
        if not lines:
            return
        start = len(self._lines)
        self._lines.extend(lines)
        prev = self._cumulative[-1] if self._cumulative else 0
        for i, line in enumerate(lines):
            idx = start + i
            wrapped = self._wrap_line(line)
            count = len(wrapped)
            self._cache[idx] = wrapped
            prev += count
            self._cumulative.append(prev)
            cell_w = cell_len(line.expandtabs())
            if cell_w > self._max_cell_width:
                self._max_cell_width = cell_w
        self._update_virtual_size()
        if self.auto_scroll:
            self.scroll_end(animate=False, immediate=True, x_axis=False)

    def _prune_max_lines(self) -> None:
        if self.max_lines is None:
            return
        remove = len(self._lines) - self.max_lines
        if remove <= 0:
            return
        del self._lines[:remove]
        removed_count = self._cumulative[remove - 1] if remove > 0 else 0
        self._cumulative = [c - removed_count for c in self._cumulative[remove:]]
        self._cache.clear()
        self._max_cell_width = 0
        for line in self._lines:
            cell_w = cell_len(line.expandtabs())
            if cell_w > self._max_cell_width:
                self._max_cell_width = cell_w
        self._update_virtual_size()

    def _wrap_line(self, line: str) -> Lines:
        styled = rich_log_line(line, self.mode, selected=False)
        if not self.wrap or self._width <= 0:
            return Lines([styled])
        wrap_width = max(self.size.width - 1, 1)
        return styled.wrap(self.app.console, wrap_width)

    def _y_to_line(self, y: int) -> tuple[int, int]:
        if not self._cumulative:
            return 0, 0
        idx = bisect.bisect_right(self._cumulative, y)
        if idx == 0:
            return 0, y
        prev = self._cumulative[idx - 1]
        return idx, y - prev

    def _get_wrapped(self, line_idx: int) -> Lines:
        if line_idx in self._cache:
            return self._cache[line_idx]
        if line_idx >= len(self._lines):
            return Lines([Text("")])
        line = self._lines[line_idx]
        selected = line_idx == self.selected_index and not self.follow_mode
        styled = rich_log_line(line, self.mode, selected=selected)
        if not self.wrap or self._width <= 0:
            wrapped = Lines([styled])
        else:
            wrap_width = max(self.size.width - 1, 1)
            wrapped = styled.wrap(self.app.console, wrap_width)
        self._cache[line_idx] = wrapped
        return wrapped

    def set_selection(self, index: int) -> None:
        old = self.selected_index
        self.selected_index = index
        self.follow_mode = False
        if old >= 0:
            self._cache.pop(old, None)
        if index >= 0:
            self._cache.pop(index, None)
        self.refresh()
        if index >= 0 and index < len(self._cumulative):
            y = self._cumulative[index - 1] if index > 0 else 0
            self.scroll_to(y=y, animate=False)

    def _rebuild_cumulative(self) -> None:
        self._cache.clear()
        self._cumulative.clear()
        self._max_cell_width = 0
        prev = 0
        for line in self._lines:
            wrapped = self._wrap_line(line)
            prev += len(wrapped)
            self._cumulative.append(prev)
            cell_w = cell_len(line.expandtabs())
            if cell_w > self._max_cell_width:
                self._max_cell_width = cell_w
        self._update_virtual_size()

    def _on_resize(self) -> None:
        new_width = self.size.width
        if new_width != self._width and new_width > 0:
            self._width = new_width
            self._rebuild_cumulative()
            self.refresh()

    def on_mount(self) -> None:
        self.focus()

    def on_resize(self) -> None:
        self._on_resize()

    @property
    def allow_select(self) -> bool:
        return True

    def _visual_to_text_pos(self, visual_row: int, col: int) -> tuple[int, int] | None:
        """Map a visual (row, col) to (text_line_index, char_offset_in_line)."""
        scroll_y = self.scroll_offset.y
        actual_y = visual_row + scroll_y
        line_idx, seg_idx = self._y_to_line(actual_y)
        if line_idx >= len(self._lines):
            return None
        wrapped = self._get_wrapped(line_idx)
        if seg_idx >= len(wrapped):
            return None
        # Calculate character offset within the original line
        char_offset = 0
        for s in range(seg_idx):
            char_offset += len(wrapped[s].plain)
        # Clamp col to segment length
        seg_len = len(wrapped[seg_idx].plain)
        char_offset += min(col, seg_len)
        return line_idx, char_offset

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        if not self._lines:
            return None
        if selection.start is None or selection.end is None:
            return None
        start_row, start_col = selection.start.transpose
        end_row, end_col = selection.end.transpose
        if start_row > end_row or (start_row == end_row and start_col > end_col):
            start_row, end_row = end_row, start_row
            start_col, end_col = end_col, start_col
        start_pos = self._visual_to_text_pos(start_row, start_col)
        end_pos = self._visual_to_text_pos(end_row, end_col)
        if start_pos is None or end_pos is None:
            return None
        start_line, start_offset = start_pos
        end_line, end_offset = end_pos
        if start_line > end_line or (start_line == end_line and start_offset > end_offset):
            start_line, end_line = end_line, start_line
            start_offset, end_offset = end_offset, start_offset
        parts: list[str] = []
        for i in range(start_line, end_line + 1):
            line = self._lines[i]
            if i == start_line and i == end_line:
                parts.append(line[start_offset:end_offset])
            elif i == start_line:
                parts.append(line[start_offset:])
            elif i == end_line:
                parts.append(line[:end_offset])
            else:
                parts.append(line)
        return "\n".join(parts), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._cache.clear()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        actual_y = scroll_y + y
        line_idx, seg_idx = self._y_to_line(actual_y)

        if line_idx >= len(self._lines):
            return Strip.blank(self.size.width, Style())

        wrapped = self._get_wrapped(line_idx)
        if seg_idx >= len(wrapped):
            return Strip.blank(self.size.width, Style())

        segment = wrapped[seg_idx]
        selection = self.text_selection
        if selection is not None:
            select_span = selection.get_span(y)
            if select_span is not None:
                start, end = select_span
                if end == -1:
                    end = len(segment)
                selection_style = self.screen.get_component_rich_style("screen--selection")
                segment = segment.copy()
                segment.stylize(selection_style, start, end)

        strip = Strip(segment.render(self.app.console), cell_len(segment.plain))
        return strip.crop_extend(scroll_x, scroll_x + self.size.width, Style())
