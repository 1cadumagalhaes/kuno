from contextlib import redirect_stdout
from io import StringIO

from kuno import main


def test_main_prints_placeholder_message() -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        main()

    assert buffer.getvalue() == "Hello from kuno!\n"
