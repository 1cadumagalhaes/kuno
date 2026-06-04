"""Tests for TableSync."""

import pytest
from textual.app import App
from textual.widgets import DataTable

from kuno.table_sync import ColumnDef, TableSync


class SyncApp(App[None]):
    def compose(self):
        yield DataTable(id="t")


@pytest.mark.asyncio
async def test_sync_adds_and_removes():
    app = SyncApp()
    async with app.run_test():
        table = app.query_one("#t", DataTable)
        sync = TableSync(table)
        sync.setup_columns(
            name_width=20,
            columns=[
                ColumnDef("Ready", 6, "ready", lambda p: p["ready"]),
                ColumnDef("Status", 10, "status", lambda p: p["status"]),
            ],
            name_extractor=lambda p: p["name"],
        )

        items = [
            {"name": "pod-a", "ready": "1/1", "status": "Running"},
            {"name": "pod-b", "ready": "0/1", "status": "Pending"},
        ]
        removed = sync.sync(items, key_fn=lambda p: p["name"], pending=set())
        assert removed is None
        assert table.row_count == 2

        # Update pod-b status, remove pod-a
        items = [{"name": "pod-b", "ready": "1/1", "status": "Running"}]
        removed = sync.sync(items, key_fn=lambda p: p["name"], pending=set())
        assert removed == "pod-a"
        assert table.row_count == 1
        # Cell should be updated
        row = table.get_row_at(0)
        assert "Running" in str(row)


@pytest.mark.asyncio
async def test_sync_preserves_cursor():
    app = SyncApp()
    async with app.run_test():
        table = app.query_one("#t", DataTable)
        sync = TableSync(table)
        sync.setup_columns(
            name_width=20,
            columns=[ColumnDef("Ready", 6, "ready", lambda p: p["ready"])],
            name_extractor=lambda p: p["name"],
        )

        items = [
            {"name": "pod-a", "ready": "1/1"},
            {"name": "pod-b", "ready": "1/1"},
        ]
        sync.sync(items, key_fn=lambda p: p["name"], pending=set())
        table.move_cursor(row=1)

        # Update without clearing — cursor should stay
        items = [
            {"name": "pod-a", "ready": "1/1"},
            {"name": "pod-b", "ready": "0/1"},
        ]
        sync.sync(items, key_fn=lambda p: p["name"], pending=set())
        assert table.cursor_row == 1
