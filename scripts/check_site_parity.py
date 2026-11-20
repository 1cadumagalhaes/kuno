"""Compare the Portuguese and English pages for structural drift.

The two pages are hand-maintained translations of the same markup, so a section
added or an id renamed on one side is the failure mode worth catching. Text,
translated attributes and relative asset paths are ignored; tags, ids and the
order of interactive elements are compared.

Usage: uv run python scripts/check_site_parity.py
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {"pt": ROOT / "site" / "index.html", "en": ROOT / "site" / "en" / "index.html"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


class Structure(HTMLParser):
    """Collects a body-only outline of tags, ids and interactive elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.body = False
        self.outline: list[str] = []
        self.ids: list[str] = []
        self.controls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "body":
            self.body = True
            return
        if not self.body:
            return
        node_id = attributes.get("id")
        self.outline.append(f"{tag}#{node_id}" if node_id else tag)
        if node_id:
            self.ids.append(node_id)
        if tag in {"a", "button", "input", "select", "textarea"}:
            self.controls.append(tag)
        if tag in VOID_TAGS:
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self.body = False


def structure_of(path: Path) -> Structure:
    parser = Structure()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def main() -> int:
    structures = {name: structure_of(path) for name, path in PAGES.items()}
    problems: list[str] = []

    pt, en = structures["pt"], structures["en"]
    if pt.outline != en.outline:
        mismatch = next(
            (
                index
                for index, (a, b) in enumerate(zip(pt.outline, en.outline, strict=False))
                if a != b
            ),
            min(len(pt.outline), len(en.outline)),
        )
        problems.append(
            f"markup diverges at element {mismatch}: "
            f"pt={pt.outline[mismatch : mismatch + 3]} en={en.outline[mismatch : mismatch + 3]}"
        )
    if pt.ids != en.ids:
        only_pt = [i for i in pt.ids if i not in en.ids]
        only_en = [i for i in en.ids if i not in pt.ids]
        problems.append(f"ids differ: only-pt={only_pt} only-en={only_en}")

    for name, structure in structures.items():
        duplicates = {i for i in structure.ids if structure.ids.count(i) > 1}
        if duplicates:
            problems.append(f"{name}: duplicate ids {sorted(duplicates)}")

    if problems:
        print("site parity: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"site parity: OK ({len(pt.outline)} elements, {len(pt.ids)} ids, {len(pt.controls)} controls)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
