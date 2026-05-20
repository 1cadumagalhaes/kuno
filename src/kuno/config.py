from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from kuno.models import StartupConfig

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kuno" / "config.toml"


@dataclass(slots=True)
class KunoConfig:
    path: Path
    theme: str = "textual-ansi"
    yaml_theme: str = "monokai"
    wrap_logs: bool = False
    timestamps_enabled: bool = False
    log_mode: str = "raw"
    tail_lines: int = 500
    default_context: str | None = None
    default_namespace: str | None = None


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

    return KunoConfig(
        path=config_path,
        theme=_safe_str(ui, "theme", "nord"),
        yaml_theme=_safe_str(ui, "yaml_theme", "monokai"),
        wrap_logs=_safe_bool(logs, "wrap", False),
        timestamps_enabled=_safe_bool(logs, "timestamps", False),
        log_mode=_safe_str(logs, "mode", "raw"),
        tail_lines=_safe_int(logs, "tail_lines", 500),
        default_context=_safe_optional_str(defaults, "context"),
        default_namespace=_safe_optional_str(defaults, "namespace"),
    )


def save_config(config: KunoConfig) -> None:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    content = _format_config(config)
    with NamedTemporaryFile(
        mode="w",
        dir=config.path.parent,
        prefix=".kuno_config_",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.rename(config.path)


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


def _format_config(config: KunoConfig) -> str:
    return (
        "[ui]\n"
        f"theme = \"{config.theme}\"\n"
        f"yaml_theme = \"{config.yaml_theme}\"\n"
        "\n"
        "[logs]\n"
        f"wrap = {str(config.wrap_logs).lower()}\n"
        f"timestamps = {str(config.timestamps_enabled).lower()}\n"
        f"mode = \"{config.log_mode}\"\n"
        f"tail_lines = {config.tail_lines}\n"
        "\n"
        "[defaults]\n"
        f"# context = \"{config.default_context or ''}\"\n"
        f"# namespace = \"{config.default_namespace or ''}\"\n"
    )
