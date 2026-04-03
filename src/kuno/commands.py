from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedCommand:
    name: str
    argument: str | None = None


def parse_command(raw: str) -> ParsedCommand:
    text = raw.strip()
    if not text:
        raise ValueError("Empty command")
    if text.startswith(":"):
        text = text[1:].strip()
    if not text:
        raise ValueError("Empty command")

    parts = text.split(maxsplit=1)
    name = parts[0].lower()
    argument = parts[1].strip() if len(parts) == 2 else None

    if name in {"pods", "refresh", "details", "hide-details", "help"}:
        if argument is not None:
            raise ValueError(f"Command '{name}' does not take arguments")
        return ParsedCommand(name=name)

    if name in {"ns", "ctx"}:
        if argument is None:
            raise ValueError(f"Command '{name}' requires an argument")
        return ParsedCommand(name=name, argument=argument)

    raise ValueError(f"Unknown command: {name}")
