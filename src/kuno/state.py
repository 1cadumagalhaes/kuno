from __future__ import annotations

import json
import os
from pathlib import Path


def state_path() -> Path:
    """Return the path to kuno's cached state file (XDG cache dir)."""
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "kuno" / "state.json"


class KunoState:
    """Per-context UI memory, cached to disk under ~/.cache/kuno."""

    def __init__(self, *, path: Path | None = None) -> None:
        self.path = path or state_path()
        self.namespaces: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = self.path.read_text()
            data = json.loads(raw)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        namespaces = data.get("namespaces")
        if isinstance(namespaces, dict):
            self.namespaces = {
                str(context): str(namespace)
                for context, namespace in namespaces.items()
                if isinstance(context, str) and isinstance(namespace, str)
            }

    def remember_namespace(self, context: str, namespace: str) -> None:
        self.namespaces[context] = namespace
        self.save()

    def namespace_for(self, context: str) -> str | None:
        return self.namespaces.get(context)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps({"namespaces": self.namespaces}, indent=2)
            self.path.write_text(data)
        except Exception:  # noqa: S110
            pass
