from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from kuno.app import KunoApp
from kuno.config import KunoConfig, load_config, merge_startup_config
from kuno.models import StartupConfig
from kuno.system_theme import query_terminal_palette


class StoreUniqueValue(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        if not isinstance(values, str):
            parser.error(f"expected a string value for {self.dest}")

        current = getattr(namespace, self.dest, None)
        if current is not None and current != values:
            parser.error(f"conflicting values provided for {self.dest}: {current!r} and {values!r}")
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kuno")
    parser.add_argument(
        "-c",
        "--ctx",
        "--context",
        dest="context",
        action=StoreUniqueValue,
        help="Kubernetes context to use",
    )
    parser.add_argument(
        "-n",
        "--ns",
        "--namespace",
        dest="namespace",
        action=StoreUniqueValue,
        help="Kubernetes namespace to use",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Write debug output to /tmp/kuno_debug.log",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> tuple[StartupConfig, bool]:
    args = build_parser().parse_args(argv)
    return StartupConfig(context=args.context, namespace=args.namespace), args.debug


def main(argv: Sequence[str] | None = None, config: KunoConfig | None = None) -> int:
    kuno_config = config if config is not None else load_config()
    cli_config, debug = parse_args(argv)
    startup_config = merge_startup_config(kuno_config, cli_config)
    terminal_palette = query_terminal_palette()
    app = KunoApp(startup_config, kuno_config, terminal_palette=terminal_palette)
    if debug:
        app.debug_enabled = True
        _start_debug_log()
        _dblog("kuno started")
        _dblog(f"config_path={kuno_config.path}")
        _dblog(f"startup={startup_config}")
        _dblog(f"theme={kuno_config.theme}")
    app.run()
    return 0


DEBUG_LOG_PATH = Path("/tmp/kuno_debug.log")  # noqa: S108


def _start_debug_log() -> None:
    with DEBUG_LOG_PATH.open("w") as f:
        f.write("=== kuno debug log ===\n")


def _dblog(msg: str) -> None:
    import time

    ts = time.strftime("%H:%M:%S")
    try:
        with DEBUG_LOG_PATH.open("a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: S110
        pass
