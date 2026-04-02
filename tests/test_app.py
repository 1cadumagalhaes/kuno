import pytest
from textual.widgets import Static

from kuno.app import KunoApp
from kuno.models import StartupConfig


@pytest.mark.asyncio
async def test_app_renders_startup_summary() -> None:
    app = KunoApp(StartupConfig(context="prod", namespace="payments"))

    async with app.run_test():
        summary = app.query_one("#startup-summary", Static)
        assert summary.content == "kuno\ncontext: prod\nnamespace: payments"
