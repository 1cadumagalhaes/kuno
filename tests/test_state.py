from __future__ import annotations

from pathlib import Path

from kuno.state import KunoState, state_path


def test_state_path_respects_xdg_cache_home(monkeypatch, tmp_path) -> None:
    cache = tmp_path / "xdg-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    assert state_path() == cache / "kuno" / "state.json"


def test_state_path_falls_back_to_home_cache(monkeypatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: Path("/home/test"))
    assert state_path() == Path("/home/test") / ".cache" / "kuno" / "state.json"


def test_state_roundtrips_namespace_memory(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = KunoState(path=path)
    assert state.namespace_for("prod") is None

    state.remember_namespace("prod", "payments")
    assert state.namespace_for("prod") == "payments"
    assert path.exists()

    reloaded = KunoState(path=path)
    assert reloaded.namespace_for("prod") == "payments"


def test_state_handles_missing_or_corrupt_file(tmp_path) -> None:
    missing = KunoState(path=tmp_path / "nope.json")
    assert missing.namespaces == {}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{ not valid json")
    state = KunoState(path=corrupt)
    assert state.namespaces == {}
