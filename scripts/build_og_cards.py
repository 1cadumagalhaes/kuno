"""Render the Open Graph cards for both landing pages from one layout.

Each card is the same composition with translated copy: brand mark and wordmark,
a two-line headline sized to the available column, a two-line tagline, the
install chip, and a real terminal capture on the right.

Run after changing copy, the layout, or the screenshots:

    uv run --with cairosvg --with pillow python scripts/build_og_cards.py

CI runs the same command with --check, which exits non-zero when the committed
PNGs no longer match what the script renders.
"""

from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "site" / "assets"
SCREENSHOT = ASSETS / "screens" / "pods.svg"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

WIDTH, HEIGHT = 1200, 630
INK = "#111827"
MUTED = "#42516a"
LINE = "#b7c2d2"
BLUE = "#2458d3"
PAPER = "#f7f8fb"
TERMINAL = "#10151f"
TERMINAL_BORDER = "#293346"
HEADLINE_X, HEADLINE_BASE, HEADLINE_STEP = 60, 262, 76
HEADLINE_MAX_WIDTH = 552
TAGLINE_X, TAGLINE_TOP, TAGLINE_STEP, TAGLINE_SIZE = 62, 390, 32, 22


@dataclass(frozen=True)
class Card:
    lang: str
    filename: str
    headline: tuple[str, str]
    tagline: tuple[str, str]
    button: str
    alt_lang: str


CARDS = (
    Card(
        lang="pt-BR",
        filename="og-pt.png",
        headline=("Seu cluster.", "Uma tecla."),
        tagline=("Interface de terminal para Kubernetes,", "feita para o teclado."),
        button="Copiar",
        alt_lang="en",
    ),
    Card(
        lang="en",
        filename="og-en.png",
        headline=("Your cluster.", "One keystroke."),
        tagline=("A keyboard-first terminal UI", "for Kubernetes."),
        button="Copy",
        alt_lang="pt",
    ),
)


def _font(path: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_DIR / path), size)


def _fits(
    lines: tuple[str, ...], font_path: str, size: int, max_width: float, tracking: float
) -> bool:
    font = _font(font_path, size)
    widest = max(font.getlength(line) for line in lines) + tracking * (
        max(len(line) for line in lines) - 1
    )
    return widest <= max_width


def _fitted_size(
    lines: tuple[str, ...], font_path: str, start: int, max_width: float, tracking: float
) -> int:
    """Largest size, in even steps down from `start`, whose widest line fits."""
    size = start
    while size > 20 and not _fits(lines, font_path, size, max_width, tracking):
        size -= 2
    return size


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _screenshot_href() -> str:
    """Embed the terminal capture so the SVG carries no machine-specific path."""
    return "data:image/svg+xml;base64," + base64.b64encode(SCREENSHOT.read_bytes()).decode("ascii")


def render_svg(card: Card, screenshot: str) -> str:
    headline_size = _fitted_size(card.headline, "DejaVuSans-Bold.ttf", 70, HEADLINE_MAX_WIDTH, 3.4)
    tagline_size = _fitted_size(card.tagline, "DejaVuSans.ttf", TAGLINE_SIZE, 480, 0)
    headline_lines = "\n".join(
        f'  <text x="{HEADLINE_X}" y="{HEADLINE_BASE + index * HEADLINE_STEP}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{headline_size}" font-weight="bold" letter-spacing="-{3.4 * headline_size / 70:.1f}" fill="{INK}">{_escape(line)}</text>'
        for index, line in enumerate(card.headline)
    )
    tagline_lines = "\n".join(
        f'  <text x="{TAGLINE_X}" y="{TAGLINE_TOP + index * TAGLINE_STEP}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{tagline_size}" fill="{MUTED}">{_escape(line)}</text>'
        for index, line in enumerate(card.tagline)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Kuno social card ({card.lang})">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>

  <g transform="translate(64 52) scale(0.17)">
    <path d="M75 34v172M75 120l98-70M75 120l98 70" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="75" cy="34" r="11" fill="{PAPER}" stroke="{INK}" stroke-width="6"/>
    <circle cx="75" cy="120" r="13" fill="{BLUE}" stroke="{BLUE}" stroke-width="6"/>
    <circle cx="75" cy="206" r="11" fill="{PAPER}" stroke="{INK}" stroke-width="6"/>
    <circle cx="173" cy="50" r="11" fill="{PAPER}" stroke="{INK}" stroke-width="6"/>
    <circle cx="173" cy="190" r="11" fill="{PAPER}" stroke="{INK}" stroke-width="6"/>
  </g>
  <text x="122" y="92" font-family="DejaVu Sans, sans-serif" font-size="28" font-weight="bold" letter-spacing="-1" fill="{INK}">Kuno</text>

{headline_lines}
{tagline_lines}

  <rect x="62" y="462" width="452" height="64" rx="8" fill="#ffffff" stroke="{LINE}"/>
  <text x="86" y="503" font-family="DejaVu Sans Mono, monospace" font-size="22" fill="{INK}">uv tool install kuno</text>
  <rect x="418" y="472" width="82" height="44" rx="4" fill="{BLUE}"/>
  <text x="459" y="501" font-family="DejaVu Sans, sans-serif" font-size="19" font-weight="bold" fill="#ffffff" text-anchor="middle">{_escape(card.button)}</text>

  <clipPath id="shot"><rect x="620" y="188" width="516" height="328" rx="10"/></clipPath>
  <rect x="620" y="188" width="516" height="328" rx="10" fill="{TERMINAL}"/>
  <g clip-path="url(#shot)">
    <svg x="620" y="188" width="516" height="328" viewBox="0 0 1458 928" preserveAspectRatio="xMidYMid meet">
      <image href="{screenshot}" width="1458" height="928"/>
    </svg>
  </g>
  <rect x="620" y="188" width="516" height="328" rx="10" fill="none" stroke="{TERMINAL_BORDER}"/>
</svg>
"""


def render_png(card: Card, screenshot: str) -> bytes:
    import cairosvg

    return cairosvg.svg2png(
        bytestring=render_svg(card, screenshot).encode("utf-8"),
        output_width=WIDTH,
        output_height=HEIGHT,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the committed PNGs instead of writing them"
    )
    arguments = parser.parse_args()

    screenshot = _screenshot_href()
    stale: list[str] = []
    for card in CARDS:
        target = ASSETS / card.filename
        rendered = render_png(card, screenshot)
        if arguments.check:
            if not target.exists() or target.read_bytes() != rendered:
                stale.append(card.filename)
            continue
        target.write_bytes(rendered)
        print(f"wrote {target.relative_to(ROOT)} ({len(rendered) / 1024:.0f} KB)")

    if stale:
        print("social cards are out of date: " + ", ".join(stale))
        print(
            "regenerate with: uv run --with cairosvg --with pillow python scripts/build_og_cards.py"
        )
        return 1
    if arguments.check:
        print(f"social cards up to date ({len(CARDS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
