from __future__ import annotations

from dataclasses import dataclass

COMMANDS = (
    "about",
    "back",
    "config",
    "containers",
    "contexts",
    "del",
    "delete",
    "deploy",
    "deployments",
    "events",
    "help",
    "hide-info",
    "info",
    "keys",
    "logs",
    "namespace",
    "namespaces",
    "ns",
    "pods",
    "pvc",
    "refresh",
    "restart",
    "secrets",
    "services",
    "statefulsets",
    "sts",
    "svc",
    "theme",
    "ctx",
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

    # Normalize aliases
    normalized = _normalize_alias(name)

    no_arg_commands = {
        "about",
        "back",
        "config",
        "containers",
        "contexts",
        "del",
        "deploy",
        "events",
        "help",
        "hide-info",
        "info",
        "keys",
        "logs",
        "namespaces",
        "pods",
        "pvc",
        "refresh",
        "restart",
        "secrets",
        "sts",
        "svc",
    }

    if normalized == "ns":
        if argument is None:
            return ParsedCommand(name="ns")
        return ParsedCommand(name="ns", argument=argument)

    if normalized == "ctx":
        if argument is None:
            raise ValueError(f"Command '{name}' requires an argument")
        return ParsedCommand(name="ctx", argument=argument)

    if normalized == "theme":
        return ParsedCommand(name="theme", argument=argument)

    if normalized in no_arg_commands:
        if argument is not None:
            raise ValueError(f"Command '{name}' does not take arguments")
        return ParsedCommand(name=normalized)

    raise ValueError(f"Unknown command: {name}")


def _normalize_alias(name: str) -> str:
    alias_map: dict[str, str] = {
        "delete": "del",
        "services": "svc",
        "statefulsets": "sts",
        "deployments": "deploy",
        "namespace": "ns",
    }
    return alias_map.get(name, name)


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

    candidates = [f"{name} {c}" for c in source if c.startswith(argument)]
    if argument == "" and name in ("ns", "ctx"):
        candidates.insert(0, name)
    return candidates
