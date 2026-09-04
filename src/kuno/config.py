from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from kuno.models import StartupConfig

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kuno" / "config.toml"


@dataclass(slots=True)
class KunoConfig:
    path: Path
    theme: str = "system"
    wrap_logs: bool = False
    timestamps_enabled: bool = False
    log_mode: str = "raw"
    tail_lines: int = 500
    default_context: str | None = None
    default_namespace: str | None = None
    hidden_namespaces: list[str] = field(default_factory=list)
    hidden_namespaces_by_context: dict[str, list[str]] = field(default_factory=dict)


def load_config(path: Path | None = None) -> KunoConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return KunoConfig(path=config_path)

    try:
        raw = config_path.read_text()
        data = tomllib.loads(raw)
    except Exception:
        return KunoConfig(path=config_path)

    ui = data.get("ui", {}) if isinstance(data, dict) else {}
    logs = data.get("logs", {}) if isinstance(data, dict) else {}
    defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
    namespaces_section = data.get("namespaces", {}) if isinstance(data, dict) else {}

    return KunoConfig(
        path=config_path,
        theme=_safe_str(ui, "theme", "system"),
        wrap_logs=_safe_bool(logs, "wrap", False),
        timestamps_enabled=_safe_bool(logs, "timestamps", False),
        log_mode=_safe_str(logs, "mode", "raw"),
        tail_lines=_safe_int(logs, "tail_lines", 500),
        default_context=_safe_optional_str(defaults, "context"),
        default_namespace=_safe_optional_str(defaults, "namespace"),
        hidden_namespaces=_safe_str_list(namespaces_section, "hidden"),
        hidden_namespaces_by_context=_safe_context_hidden(namespaces_section),
    )


def save_config(config: KunoConfig) -> None:
    path = config.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_config(config))


def merge_startup_config(config: KunoConfig, cli_config: StartupConfig) -> StartupConfig:
    context = cli_config.context or config.default_context or None
    namespace = cli_config.namespace or config.default_namespace or None
    return StartupConfig(context=context, namespace=namespace)


def _safe_str(data: dict, key: str, default: str) -> str:
    value = data.get(key)
    return str(value) if isinstance(value, str) else default


def _safe_bool(data: dict, key: str, default: bool) -> bool:
    value = data.get(key)
    return bool(value) if isinstance(value, bool) else default


def _safe_int(data: dict, key: str, default: int) -> int:
    value = data.get(key)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else default


def _safe_optional_str(data: dict, key: str) -> str | None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _safe_str_list(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _safe_context_hidden(data: dict) -> dict[str, list[str]]:
    overrides = data.get("context_overrides")
    if not isinstance(overrides, dict):
        return {}
    result: dict[str, list[str]] = {}
    for context, value in overrides.items():
        if not isinstance(context, str) or not context.strip() or not isinstance(value, dict):
            continue
        patterns = _safe_str_list(value, "hidden")
        if patterns:
            result[context] = patterns
    return result


def _format_config(config: KunoConfig) -> str:
    lines: list[str] = [
        "[ui]",
        f'theme = "{config.theme}"',
        "",
        "[logs]",
        f"wrap = {str(config.wrap_logs).lower()}",
        f"timestamps = {str(config.timestamps_enabled).lower()}",
        f'mode = "{config.log_mode}"',
        f"tail_lines = {config.tail_lines}",
        "",
        "[defaults]",
    ]
    if config.default_context:
        lines.append(f'context = "{config.default_context}"')
    if config.default_namespace:
        lines.append(f'namespace = "{config.default_namespace}"')
    lines.append("")

    if config.hidden_namespaces or config.hidden_namespaces_by_context:
        lines.append("[namespaces]")
        if config.hidden_namespaces:
            entries = ", ".join(f'"{p}"' for p in config.hidden_namespaces)
            lines.append(f"hidden = [{entries}]")
        for context, patterns in config.hidden_namespaces_by_context.items():
            entries = ", ".join(f'"{p}"' for p in patterns)
            lines.append(f'[namespaces.context_overrides."{context}"]')
            lines.append(f"hidden = [{entries}]")
        lines.append("")
    return "\n".join(lines)
