from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from rich.highlighter import Highlighter
from rich.text import Text


class LogMode(StrEnum):
    RAW = "raw"
    STRUCTURED = "structured"


@dataclass(slots=True)
class ParsedLogLine:
    raw: str
    data: dict[str, Any] | None
    timestamp: str | None
    level: str | None
    message: str | None
    category: str | None
    fields: dict[str, Any]


def parse_log_line(line: str) -> ParsedLogLine:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return ParsedLogLine(
            raw=line,
            data=None,
            timestamp=None,
            level=None,
            message=line,
            category=None,
            fields={},
        )

    if not isinstance(data, dict):
        return ParsedLogLine(
            raw=line,
            data=None,
            timestamp=None,
            level=None,
            message=line,
            category=None,
            fields={},
        )

    timestamp = _extract_first_string(data, "timestamp", "time", "ts", "@timestamp")
    level = _extract_first_string(data, "level", "severity", "lvl")
    message = _extract_first_string(data, "message", "msg")
    category = _extract_first_string(data, "category", "logger", "component", "module")
    used_keys = {
        key
        for key in (
            "timestamp",
            "time",
            "ts",
            "@timestamp",
            "level",
            "severity",
            "lvl",
            "message",
            "msg",
            "category",
            "logger",
            "component",
            "module",
        )
        if key in data
    }
    fields = {key: value for key, value in data.items() if key not in used_keys}
    return ParsedLogLine(
        raw=line,
        data=data,
        timestamp=timestamp,
        level=level,
        message=message,
        category=category,
        fields=fields,
    )


def format_log_line(line: str, mode: LogMode) -> list[str]:
    parsed = parse_log_line(line)
    if mode is LogMode.RAW:
        return [parsed.raw]
    return [_structured_line(parsed)]


def rich_log_line(line: str, mode: LogMode, *, selected: bool = False) -> Text:
    parsed = parse_log_line(line)
    if mode is LogMode.RAW or parsed.data is None:
        text = Text(parsed.raw)
    else:
        text = _structured_text(parsed)
    if selected:
        text.stylize("reverse")
    return text


def _structured_line(parsed: ParsedLogLine) -> str:
    if parsed.data is None:
        return parsed.raw

    parts: list[str] = []
    if parsed.timestamp:
        parts.append(parsed.timestamp)
    if parsed.level:
        parts.append(parsed.level.upper())
    if parsed.category:
        parts.append(parsed.category)
    if parsed.message:
        parts.append(parsed.message)
    field_parts = [f"{key}={_stringify(value)}" for key, value in parsed.fields.items()]
    parts.extend(field_parts)
    return " ".join(part for part in parts if part)


def _structured_text(parsed: ParsedLogLine) -> Text:
    text = Text()
    if parsed.timestamp:
        text.append(_short_timestamp(parsed.timestamp), style="dim")
        text.append(" ")
    if parsed.level:
        level_str = parsed.level.upper()
        text.append(level_str, style=_level_style_name(level_str))
        text.append(" ")
    if parsed.category:
        text.append(parsed.category, style="dim cyan")
        text.append(" ")
    if parsed.message:
        text.append(parsed.message)
    for key, value in parsed.fields.items():
        text.append(" ")
        text.append(key, style="magenta")
        text.append("=")
        text.append(_stringify(value))
    return text


def _short_timestamp(ts: str) -> str:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(UTC)
            return dt.strftime("%m-%d %H:%M:%S")
        except ValueError:
            continue
    return ts[:19] if len(ts) > 19 else ts


class StructuredLogHighlighter(Highlighter):
    TIMESTAMP_RE = re.compile(r"^\S+Z?\s")
    LEVEL_RE = re.compile(r"\b(INFO|WARN|WARNING|ERROR|DEBUG|CRITICAL|FATAL)\b")
    KEY_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_.-]*)=")

    def highlight(self, text: Text) -> None:
        if match := self.TIMESTAMP_RE.match(text.plain):
            text.stylize("dim", 0, match.end())
        for match in self.LEVEL_RE.finditer(text.plain):
            level = match.group(1)
            text.stylize(_level_style_name(level), match.start(), match.end())
        for match in self.KEY_RE.finditer(text.plain):
            text.stylize("magenta", match.start(1), match.end(1))


def _level_style_name(level: str) -> str:
    value = level.lower()
    if value in {"error", "fatal", "critical"}:
        return "bold red"
    if value in {"warn", "warning"}:
        return "bold yellow"
    if value == "debug":
        return "blue"
    return "green"


def _extract_first_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)
