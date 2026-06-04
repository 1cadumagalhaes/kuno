from kuno import system_theme


def test_query_single_osc_times_out_without_reading(monkeypatch) -> None:
    writes: list[bytes] = []

    monkeypatch.setattr(system_theme.os, "write", lambda fd, data: writes.append(data))
    monkeypatch.setattr(system_theme.select, "select", lambda r, w, x, timeout: ([], [], []))

    def fail_read(fd: int, size: int) -> bytes:
        raise AssertionError("os.read should not be called when fd is not readable")

    monkeypatch.setattr(system_theme.os, "read", fail_read)

    assert system_theme._query_single_osc(0, b"\x1b]10;?\x07") is None
    assert writes == [b"\x1b]10;?\x07"]


def test_drain_returns_when_fd_is_not_readable(monkeypatch) -> None:
    monkeypatch.setattr(system_theme.select, "select", lambda r, w, x, timeout: ([], [], []))

    def fail_read(fd: int, size: int) -> bytes:
        raise AssertionError("os.read should not be called when fd is not readable")

    monkeypatch.setattr(system_theme.os, "read", fail_read)

    assert system_theme._drain(0) == b""


def test_parse_osc_reply_accepts_st_terminated_rgb_colors() -> None:
    data = b"\x1b]10;rgb:eeee/eeee/eeee\x1b\\\x1b]11;rgb:1111/2222/3333\x1b\\"

    assert system_theme._parse_osc_reply(data) == {
        10: (238, 238, 238),
        11: (17, 34, 51),
    }


def test_parse_osc_reply_accepts_hex_color_specs() -> None:
    data = b"\x1b]10;#eeeeee\x1b\\\x1b]11;#123\x1b\\\x1b]4;0;#112233\x1b\\"

    assert system_theme._parse_osc_reply(data) == {
        0: (17, 34, 51),
        10: (238, 238, 238),
        11: (17, 34, 51),
    }


def test_query_terminal_palette_keeps_dynamic_colors_separate_from_ansi(monkeypatch) -> None:
    monkeypatch.setattr(system_theme.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(system_theme.sys.stdin, "fileno", lambda: 0)
    monkeypatch.setattr(system_theme.termios, "tcgetattr", lambda fd: [])
    monkeypatch.setattr(system_theme.termios, "tcsetattr", lambda fd, when, attrs: None)
    monkeypatch.setattr(system_theme.tty, "setraw", lambda fd: None)
    monkeypatch.setattr(system_theme, "_drain", lambda fd: b"")

    replies = [
        b"\x1b]10;rgb:ebeb/ebeb/ebeb\x1b\\",
        b"\x1b]11;rgb:1414/0808/0d0d\x1b\\",
    ]
    ansi_reply = b"".join(
        f"\x1b]4;{index};rgb:{index:02x}{index:02x}/{index:02x}{index:02x}/{index:02x}{index:02x}\x1b\\".encode()
        for index in range(16)
    )

    def fake_query_single_osc(fd: int, query: bytes, timeout: float = 0.6) -> bytes:
        return replies.pop(0)

    monkeypatch.setattr(system_theme, "_query_single_osc", fake_query_single_osc)
    monkeypatch.setattr(system_theme.os, "write", lambda fd, data: None)

    chunks = [ansi_reply]

    def fake_select(r, w, x, timeout):
        return (r, [], []) if chunks else ([], [], [])

    def fake_read(fd: int, size: int) -> bytes:
        return chunks.pop(0)

    monkeypatch.setattr(system_theme.select, "select", fake_select)
    monkeypatch.setattr(system_theme.os, "read", fake_read)

    palette = system_theme.query_terminal_palette()

    assert palette is not None
    assert palette.foreground == (235, 235, 235)
    assert palette.background == (20, 8, 13)
    assert palette.ansi[10] == (10, 10, 10)
    assert palette.ansi[11] == (11, 11, 11)
