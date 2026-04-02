from contextlib import redirect_stdout
from io import StringIO

from kuno import main


def test_main_prints_placeholder_message() -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        result = main([])

    assert result == 0
    assert buffer.getvalue() == "Hello from kuno!\n"
