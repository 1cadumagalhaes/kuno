from pathlib import Path

from kuno.config import KunoConfig, load_config, save_config


def test_load_config_defaults_without_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.toml")
    assert config.hidden_namespaces == []
    assert config.hidden_namespaces_by_context == {}


def test_load_config_parses_hidden_namespaces(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                "[namespaces]",
                'hidden = ["gke-*", "kube-*", "istio-*"]',
                "",
                '[namespaces.context_overrides."retize-prod-gke"]',
                'hidden = ["kube-*", "my-temp-ns"]',
            ]
        )
    )

    config = load_config(path)
    assert config.hidden_namespaces == ["gke-*", "kube-*", "istio-*"]
    assert config.hidden_namespaces_by_context == {"retize-prod-gke": ["kube-*", "my-temp-ns"]}


def test_load_config_ignores_malformed_hidden_entries(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                "[namespaces]",
                "hidden = [42, true, '', 'valid-*']",
                '[namespaces.context_overrides."ctx"]',
                'wrong_key = ["a"]',
                '[namespaces.context_overrides."ctx2"]',
                'hidden = "not-a-list"',
            ]
        )
    )

    config = load_config(path)
    assert config.hidden_namespaces == ["valid-*"]
    assert config.hidden_namespaces_by_context == {}


def test_save_config_round_trips_hidden_namespaces(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config = KunoConfig(
        path=path,
        hidden_namespaces=["gke-*", "kube-*"],
        hidden_namespaces_by_context={"prod": ["temp-ns"]},
    )

    save_config(config)
    loaded = load_config(path)

    assert loaded.hidden_namespaces == ["gke-*", "kube-*"]
    assert loaded.hidden_namespaces_by_context == {"prod": ["temp-ns"]}


def test_save_config_round_trips_empty_hidden(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_config(KunoConfig(path=path))
    loaded = load_config(path)

    assert loaded.hidden_namespaces == []
    assert loaded.hidden_namespaces_by_context == {}
    assert "[namespaces]" not in path.read_text()
