from __future__ import annotations

from dataclasses import dataclass

COMMANDS = (
    "about",
    "containers",
    "contexts",
    "deploy",
    "keys",
    "namespaces",
    "pods",
    "pvc",
    "refresh",
    "secrets",
    "svc",
    "sts",
    "details",
    "hide-details",
    "theme",
    "ns",
    "ctx",
    "help",
)


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

    if name in {
        "about",
        "containers",
        "contexts",
        "deploy",
        "keys",
        "namespaces",
        "pods",
        "pvc",
        "refresh",
        "secrets",
        "sts",
        "svc",
        "details",
        "hide-details",
        "help",
    }:
        if argument is not None:
            raise ValueError(f"Command '{name}' does not take arguments")
        return ParsedCommand(name=name)

    if name == "theme":
        return ParsedCommand(name=name, argument=argument)

    if name in {"ns", "ctx"}:
        if argument is None:
            raise ValueError(f"Command '{name}' requires an argument")
        return ParsedCommand(name=name, argument=argument)

    raise ValueError(f"Unknown command: {name}")


def suggest_commands(
    raw: str,
    *,
    contexts: list[str],
    namespaces: list[str],
    themes: list[str],
) -> list[str]:
    text = raw
    if text.startswith(":"):
        text = text[1:]

    if not text.strip():
        return list(COMMANDS)

    if text.endswith(" "):
        parts = text.strip().split(maxsplit=1)
        if len(parts) != 1:
            return []
        return _argument_suggestions(
            parts[0].lower(), "", contexts=contexts, namespaces=namespaces, themes=themes
        )

    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        command = parts[0].lower()
        argument_suggestions = _argument_suggestions(
            command,
            "",
            contexts=contexts,
            namespaces=namespaces,
            themes=themes,
        )
        if argument_suggestions:
            return argument_suggestions
        return [candidate for candidate in COMMANDS if candidate.startswith(command)]

    name = parts[0].lower()
    argument = parts[1]
    return _argument_suggestions(
        name, argument, contexts=contexts, namespaces=namespaces, themes=themes
    )


def _argument_suggestions(
    name: str,
    argument: str,
    *,
    contexts: list[str],
    namespaces: list[str],
    themes: list[str],
) -> list[str]:
    source: list[str]
    if name == "ctx":
        source = contexts
    elif name == "ns":
        source = namespaces
    elif name == "theme":
        source = themes
    else:
        return []

    return [f"{name} {candidate}" for candidate in source if candidate.startswith(argument)]
