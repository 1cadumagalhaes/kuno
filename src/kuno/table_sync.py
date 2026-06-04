from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from textual.coordinate import Coordinate
from textual.widgets import DataTable


@dataclass(frozen=True, slots=True)
class ColumnDef:
    """A column definition with a value extractor."""

    name: str
    width: int | None
    key: str
    extractor: Callable[[Any], str]


class TableSync:
    """Surgical DataTable updater: diff old vs new data, update only changed cells."""

    def __init__(self, table: DataTable) -> None:
        self.table = table
        self._col_defs: list[ColumnDef] = []
        self._name_extractor: Callable[[Any], str] | None = None

    def setup_columns(
        self,
        name_width: int,
        columns: Sequence[ColumnDef],
        name_extractor: Callable[[Any], str],
    ) -> None:
        self._col_defs = list(columns)
        self._name_extractor = name_extractor
        self.table.clear(columns=True)
        self.table.add_column("Name", width=name_width, key="name")
        for col in self._col_defs:
            self.table.add_column(col.name, width=col.width, key=col.key)

    def sync(
        self,
        items: list[Any],
        key_fn: Callable[[Any], str],
        pending: set[str],
    ) -> str | None:
        """Diff and update table.

        Returns the row key that was removed (if any), so the caller can
        adjust the cursor.
        """
        old_keys = set(self.table.rows.keys())
        new_map: dict[str, Any] = {}
        for item in items:
            k = key_fn(item)
            new_map[k] = item
        new_keys = set(new_map.keys())

        removed_key: str | None = None

        # Remove rows that no longer exist
        for key in old_keys - new_keys:
            try:
                self.table.remove_row(key)
                removed_key = key
            except Exception:
                pass

        # Add new rows
        for key in new_keys - old_keys:
            values = self._full_row_values(new_map[key])
            self.table.add_row(*values, key=key)

        # Update changed cells for existing rows
        for key in new_keys & old_keys:
            try:
                new_values = self._full_row_values(new_map[key])
                row_idx = self.table.get_row_index(key)
            except Exception:
                continue
            for col_idx, val in enumerate(new_values, start=0):
                current = self.table.get_cell_at(Coordinate(row_idx, col_idx))
                if str(current) != val:
                    self.table.update_cell_at(
                        Coordinate(row_idx, col_idx), val
                    )

        # Visual pending state: prepend (deleting) marker on Name cell
        for key in pending & new_keys:
            try:
                row_idx = self.table.get_row_index(key)
                name_val = self.table.get_cell_at(Coordinate(row_idx, 0))
                plain = str(name_val)
                if "(deleting)" not in plain:
                    self.table.update_cell_at(
                        Coordinate(row_idx, 0), f"{plain} (deleting)"
                    )
            except Exception:
                pass

        return removed_key

    def _full_row_values(self, item: Any) -> list[str]:
        """Return ALL display values for a row (including Name column)."""
        values: list[str] = []
        if self._name_extractor is not None:
            values.append(self._name_extractor(item))
        for col in self._col_defs:
            values.append(col.extractor(item))
        return values
