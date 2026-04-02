import pytest
from textual.widgets import Static

from kuno.app import KunoApp
from kuno.k8s.config import UnknownContextError
from kuno.models import StartupConfig


@pytest.mark.asyncio
async def test_app_renders_startup_summary(monkeypatch) -> None:
    def fake_load_startup_targets(startup_config: StartupConfig) -> StartupConfig:
        return startup_config

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test():
        summary = app.query_one("#startup-summary", Static)
        assert summary.content == "kuno\ncontext: prod\nnamespace: payments"


@pytest.mark.asyncio
async def test_app_renders_startup_error(monkeypatch) -> None:
    def fake_load_startup_targets(_: StartupConfig) -> StartupConfig:
        raise UnknownContextError("missing")

    monkeypatch.setattr("kuno.app.load_startup_targets", fake_load_startup_targets)

    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test():
        summary = app.query_one("#startup-summary", Static)
        assert summary.content == "kuno\nerror: missing"
