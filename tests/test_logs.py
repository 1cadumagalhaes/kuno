from kuno.logs import LogMode, StructuredLogHighlighter, format_log_line, parse_log_line


def test_parse_log_line_reads_common_json_fields() -> None:
    parsed = parse_log_line(
        '{"timestamp":"2026-04-03T12:00:00Z","level":"info","message":"ready","logger":"api","user_id":123}'
    )

    assert parsed.timestamp == "2026-04-03T12:00:00Z"
    assert parsed.level == "info"
    assert parsed.message == "ready"
    assert parsed.category == "api"
    assert parsed.fields == {"user_id": 123}


def test_format_log_line_structured_formats_json() -> None:
    lines = format_log_line(
        '{"timestamp":"2026-04-03T12:00:00Z","level":"warn","message":"boom","component":"worker","user_id":123}',
        LogMode.STRUCTURED,
    )

    assert lines == ["2026-04-03T12:00:00Z WARN worker boom user_id=123"]


def test_format_log_line_structured_keeps_plain_text() -> None:
    assert format_log_line("plain line", LogMode.STRUCTURED) == ["plain line"]


def test_structured_log_highlighter_keeps_text_shape() -> None:
    from rich.text import Text

    text = Text("2026-04-03T12:00:00Z INFO api ready user_id=123")
    StructuredLogHighlighter().highlight(text)
    assert text.plain == "2026-04-03T12:00:00Z INFO api ready user_id=123"
