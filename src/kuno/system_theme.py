from __future__ import annotations

import math
import os
import re
import sys
import termios
import time
import tty
from typing import NamedTuple

from textual.theme import Theme

RGB = tuple[int, int, int]


class Palette(NamedTuple):
    background: RGB
    foreground: RGB
    ansi: list[RGB]


_OSC_RE = re.compile(r"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")


def _query_osc(seq: bytes) -> dict[int, RGB] | None:
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        os.write(fd, seq)
        data = b""
        end = time.time() + 1.0
        while time.time() < end:
            chunk = os.read(fd, 1)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\x07") or data.endswith(b"\x1b\\"):
                break
        return _parse_osc_response(data)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _parse_osc_response(data: bytes) -> dict[int, RGB] | None:
    result: dict[int, RGB] = {}
    text = data.decode("utf-8", errors="replace")
    for part in text.split("\x1b]")[1:]:
        part = part.rstrip("\x07\x1b\\ \t\n\r")
        if part.startswith("10;"):
            m = _OSC_RE.search(part)
            if m:
                result[10] = _osc_hex(m.group(1), m.group(2), m.group(3))
        elif part.startswith("11;"):
            m = _OSC_RE.search(part)
            if m:
                result[11] = _osc_hex(m.group(1), m.group(2), m.group(3))
        else:
            m = re.match(r"4;(\d+);rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", part)
            if m:
                result[int(m.group(1))] = _osc_hex(m.group(2), m.group(3), m.group(4))
    return result if result else None


def _osc_hex(r: str, g: str, b: str) -> RGB:
    def _norm(s: str) -> int:
        v = int(s, 16)
        return v if len(s) == 2 else round(v / 65535 * 255)
    return (_norm(r), _norm(g), _norm(b))


def _query_palette() -> Palette | None:
    batch = b"".join(
        [b"\x1b]10;?\x07", b"\x1b]11;?\x07"]
        + [f"\x1b]4;{i};?\x07".encode() for i in range(16)]
    )
    result = _query_osc(batch)
    if not result:
        return None
    bg = result.get(11)
    fg = result.get(10)
    ansi = [result.get(i) for i in range(16)]
    if bg is None or fg is None or any(c is None for c in ansi):
        return None
    return Palette(background=bg, foreground=fg, ansi=[c for c in ansi if c is not None])  # type: ignore[arg-type]


def _luminance(r: int, g: int, b: int) -> float:
    def lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(a: RGB, b: RGB) -> float:
    l1 = _luminance(*a) + 0.05
    l2 = _luminance(*b) + 0.05
    return l1 / l2 if l1 > l2 else l2 / l1


def _lerp_rgb(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def _color_distance(a: RGB, b: RGB) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _snap(palette: list[RGB], c: RGB) -> RGB:
    best, best_d = palette[0], _color_distance(c, palette[0])
    for p in palette[1:]:
        d = _color_distance(c, p)
        if d < best_d:
            best, best_d = p, d
    return best


def _grayscale(bg: RGB, palette: list[RGB], steps: int = 12) -> list[RGB]:
    dark = _luminance(*bg) < 0.5
    endpoint = (255, 255, 255) if dark else (0, 0, 0)
    grays: list[RGB] = []
    for i in range(steps):
        t = i / (steps - 1)
        raw = _lerp_rgb(bg, endpoint, t)
        grays.append(_snap(palette, raw))
    return grays


def _hue_score(r: int, g: int, b: int, target_warm: bool) -> float:
    """Score how well a color matches warm (red/orange/yellow) vs cool (blue/cyan)."""
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    if max_c == min_c:
        return 0  # gray, neutral
    # Rough hue estimation
    if max_c == r:
        hue_deg = 0 + (g - b) / (max_c - min_c) * 60  # red-yellow range
    elif max_c == g:
        hue_deg = 120 + (b - r) / (max_c - min_c) * 60  # green-cyan range
    else:
        hue_deg = 240 + (r - g) / (max_c - min_c) * 60  # blue-magenta range
    # Normalize to 0-360
    hue_deg = hue_deg % 360
    if target_warm:
        # Warm: favor hues 0-60 (red→yellow), punish blues 180-300
        if hue_deg <= 60:
            return 5.0
        if hue_deg >= 300:
            return 3.0  # close to red (magenta)
        if 180 <= hue_deg <= 300:
            return -3.0  # blue ranges
        return 0.0
    else:
        # Cool: favor blues 180-300, punish reds 0-60
        if 180 <= hue_deg <= 300:
            return 5.0
        if hue_deg <= 60 or hue_deg >= 300:
            return -3.0
        return 0.0


def _pick_accent(ansi: list[RGB], bg: RGB, fg: RGB) -> RGB:
    """Pick accent from ANSI 1-15 with hue preference + contrast."""
    bg_is_warm = bg[0] + bg[1] > bg[2] * 1.5

    best_color, best_score = ansi[1], float("-inf")
    for idx in range(1, 16):
        if idx == 8:  # skip bright black
            continue
        c = ansi[idx]
        min_cr = min(_contrast_ratio(c, bg), _contrast_ratio(c, fg))
        hue_bonus = _hue_score(c[0], c[1], c[2], bg_is_warm)
        sat = max(c) - min(c)
        # Combined score: contrast + hue (weighted) + saturation
        score = min_cr * 1.0 + hue_bonus * 1.5 + sat / 255.0 * 1.0
        if score > best_score:
            best_color, best_score = c, score

    return best_color


def _rgb_str(c: RGB) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def build_system_theme() -> Theme:
    palette = _query_palette()
    if palette is None:
        palette = Palette(
            background=(20, 8, 13),
            foreground=(235, 235, 235),
            ansi=[
                (39, 24, 30), (199, 80, 106), (139, 196, 160), (196, 168, 130),
                (122, 142, 196), (168, 123, 181), (123, 181, 168), (209, 198, 203),
                (81, 70, 74), (224, 112, 136), (160, 212, 176), (212, 184, 146),
                (138, 158, 212), (186, 139, 197), (139, 197, 184), (235, 235, 235),
            ],
        )

    bg = palette.background
    fg = palette.foreground
    ansi = palette.ansi
    all_colors = ansi + [bg, fg]
    grays = _grayscale(bg, all_colors)

    acc = _pick_accent(ansi, bg, fg)

    dark = _luminance(*bg) < 0.5

    # Surface/panel: near-terminal-bg, no grey
    surface = _snap(all_colors, (bg[0] + 8, bg[1] + 8, bg[2] + 8))
    panel = _snap(all_colors, (min(bg[0] + 16, 255), min(bg[1] + 16, 255), min(bg[2] + 16, 255)))

    # Text-muted: WCAG >= 3.0 against bg
    muted_target = grays[6] if dark else grays[4]
    if _contrast_ratio(muted_target, bg) < 3.0:
        for i in range(7 if dark else 5, len(grays)):
            if _contrast_ratio(grays[i], bg) >= 3.0:
                muted_target = grays[i]
                break

    # Derive secondary and tertiary accents from palette
    bg_is_warm = bg[0] + bg[1] > bg[2] * 1.5
    if bg_is_warm:
        secondary_idx, tertiary_idx = 5, 3  # magenta, yellow
    else:
        secondary_idx, tertiary_idx = 5, 4  # magenta, blue

    secondary = ansi[secondary_idx]
    tertiary = ansi[tertiary_idx]

    return Theme(
        name="system",
        primary=_rgb_str(acc),
        secondary=_rgb_str(secondary if _contrast_ratio(secondary, bg) >= 2.5 else ansi[7]),
        accent=_rgb_str(acc),
        foreground=_rgb_str(fg),
        background=_rgb_str(bg),
        surface=_rgb_str(surface),
        panel=_rgb_str(panel),
        error=_rgb_str(ansi[1]),
        success=_rgb_str(ansi[2]),
        warning=_rgb_str(ansi[3]),
        dark=dark,
        variables={
            "text": _rgb_str(fg),
            "text-muted": _rgb_str(muted_target),
            "scrollbar": _rgb_str(grays[3]),
            "scrollbar-corner": _rgb_str(bg),
            "scrollbar-hover": _rgb_str(grays[5]),
            "scrollbar-blurred": _rgb_str(grays[2]),
            "border": _rgb_str(acc),
            "border-blurred": _rgb_str(grays[4]),
            "footer-key-foreground": _rgb_str(fg),
            "footer-key-background": _rgb_str(bg),
            "footer-description-foreground": _rgb_str(fg),
            "footer-description-background": _rgb_str(bg),
            "button-color-foreground": _rgb_str(bg),
            "button-color-background": _rgb_str(acc),
            "block-cursor-text-style": "b" if dark else "none",
            "input-cursor-text-style": "reverse",
            "input-selection-background": _rgb_str(acc),
            "breadcrumb": _rgb_str(acc),
            "breadcrumb-active": _rgb_str(secondary),
            "secondary": _rgb_str(secondary),
            "tertiary": _rgb_str(tertiary),
        },
    )