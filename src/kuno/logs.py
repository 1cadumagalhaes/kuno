from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LogMode(StrEnum):
    RAW = "raw"
    PRETTY = "pretty"
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
    if mode is LogMode.PRETTY:
        if parsed.data is None:
            return [parsed.raw]
        return json.dumps(parsed.data, indent=2, sort_keys=True).splitlines()
    return [_structured_line(parsed)]


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
