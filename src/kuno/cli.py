from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StartupConfig:
    context: str | None = None
    namespace: str | None = None


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
    return parser


def parse_args(argv: Sequence[str] | None = None) -> StartupConfig:
    args = build_parser().parse_args(argv)
    return StartupConfig(context=args.context, namespace=args.namespace)


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    print("Hello from kuno!")
    return 0
