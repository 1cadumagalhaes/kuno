from kuno.cli import main
from kuno.models import StartupConfig


def test_main_runs_app_with_startup_config(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(self) -> None:
        captured["startup_config"] = self.startup_config

    monkeypatch.setattr("kuno.app.KunoApp.run", fake_run)

    result = main(["--context", "prod", "--namespace", "payments"])

    assert result == 0
    assert captured["startup_config"] == StartupConfig(context="prod", namespace="payments")
