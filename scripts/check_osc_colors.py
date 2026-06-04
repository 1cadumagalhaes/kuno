from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

from kuno.system_theme import _drain, _parse_osc_reply, _query_single_osc, query_terminal_palette


def query_raw(fd: int, label: str, query: bytes, timeout: float = 0.5) -> bytes:
    os.write(fd, query)
    data = b""
    end = time.time() + timeout
    while time.time() < end:
        remaining = end - time.time()
        if remaining <= 0:
            break
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            break
        chunk = os.read(fd, 1024)
        if not chunk:
            break
        data += chunk
        if data.endswith(b"\x07") or data.endswith(b"\x1b\\"):
            break

    return data


def print_reply(label: str, data: bytes | None) -> None:
    printable = data.decode("utf-8", errors="replace") if data else "NO_REPLY"
    print(f"{label}: {printable!r}")


def check_raw_replies() -> bytes:
    if not sys.stdin.isatty():
        print("stdin is not a TTY; run this from the terminal that launches Kuno")
        return b""

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        fg = query_raw(fd, "OSC 10 foreground", b"\x1b]10;?\x1b\\")
        bg = query_raw(fd, "OSC 11 background", b"\x1b]11;?\x1b\\")
        ansi0 = query_raw(fd, "OSC 4 palette[0]", b"\x1b]4;0;?\x1b\\")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    print_reply("OSC 10 foreground", fg)
    print_reply("OSC 11 background", bg)
    print_reply("OSC 4 palette[0]", ansi0)
    return b"".join([fg, bg, ansi0])


def check_kuno_sequence() -> bytes:
    if not sys.stdin.isatty():
        return b""

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        fg = _query_single_osc(fd, b"\x1b]10;?\x1b\\", 0.6)
        drained_after_fg = _drain(fd)
        bg = _query_single_osc(fd, b"\x1b]11;?\x1b\\", 0.6)
        drained_after_bg = _drain(fd)
        ansi0 = _query_single_osc(fd, b"\x1b]4;0;?\x1b\\", 0.6)
        drained_after_ansi0 = _drain(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print_reply("Kuno sequence OSC 10", fg)
    print_reply("Kuno sequence drain after OSC 10", drained_after_fg)
    print_reply("Kuno sequence OSC 11", bg)
    print_reply("Kuno sequence drain after OSC 11", drained_after_bg)
    print_reply("Kuno sequence OSC 4 palette[0]", ansi0)
    print_reply("Kuno sequence drain after OSC 4", drained_after_ansi0)
    return b"".join(data for data in [fg, bg, ansi0] if data)


def check_full_palette_sequence() -> tuple[bytes, bytes]:
    if not sys.stdin.isatty():
        return b"", b""

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        fg = _query_single_osc(fd, b"\x1b]10;?\x1b\\", 0.6)
        drain_fg = _drain(fd)
        bg = _query_single_osc(fd, b"\x1b]11;?\x1b\\", 0.6)
        drain_bg = _drain(fd)

        batch = b"".join(f"\x1b]4;{i};?\x1b\\".encode() for i in range(16))
        os.write(fd, batch)
        ansi = b""
        end = time.time() + 1.2
        while time.time() < end:
            remaining = end - time.time()
            if remaining <= 0:
                break
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                break
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            ansi += chunk
        drain_ansi = _drain(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print_reply("Full sequence OSC 10", fg)
    print_reply("Full sequence drain after OSC 10", drain_fg)
    print_reply("Full sequence OSC 11", bg)
    print_reply("Full sequence drain after OSC 11", drain_bg)
    print_reply("Full sequence OSC 4 batch", ansi)
    print_reply("Full sequence drain after OSC 4 batch", drain_ansi)
    return b"".join(data for data in [fg, bg] if data), ansi


def main() -> int:
    dynamic_raw, ansi_raw = check_full_palette_sequence()
    if dynamic_raw or ansi_raw:
        print(f"parsed full sequence dynamic replies: {_parse_osc_reply(dynamic_raw)}")
        print(f"parsed full sequence ANSI replies: {_parse_osc_reply(ansi_raw)}")

    raw = check_raw_replies()
    if raw:
        parsed = _parse_osc_reply(raw)
        print(f"parsed replies: {parsed}")

    kuno_raw = check_kuno_sequence()
    if kuno_raw:
        print(f"parsed Kuno sequence replies: {_parse_osc_reply(kuno_raw)}")

    palette = query_terminal_palette()
    if palette is None:
        print("NO OSC color reply or incomplete reply")
        return 1

    print("OSC color reply OK")
    print(f"background: {palette.background}")
    print(f"foreground: {palette.foreground}")
    print(f"ansi colors: {len(palette.ansi)}")
    for index, color in enumerate(palette.ansi):
        print(f"ansi[{index}]: {color}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
