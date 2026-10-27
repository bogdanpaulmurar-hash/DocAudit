"""Linia de comandă DocAudit (Etapa 2: eșantion și validare).

    python -m docaudit sample [--out DIR] [--seed N]
    python -m docaudit validate DIR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .i18n import t
from .model import SCHEMA_VERSION, read_pages, validate_dataset
from .sample import DEFAULT_SEED, write_sample

DEFAULT_SAMPLE_DIR = Path("tests/fixtures/sample_v1")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docaudit", description=t("cli.description"))
    parser.add_argument("--version", action="version", version=t("cli.version", version=__version__))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sample = sub.add_parser("sample", help=t("cli.sample.help"))
    p_sample.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_DIR, help=t("cli.sample.out"))
    p_sample.add_argument("--seed", type=int, default=DEFAULT_SEED)

    p_val = sub.add_parser("validate", help=t("cli.validate.help"))
    p_val.add_argument("folder", type=Path)

    args = parser.parse_args(argv)

    if args.cmd == "sample":
        n = write_sample(args.out, args.seed)
        print(t("cli.sample.done", pages=n, path=args.out))
        return 0

    errors = validate_dataset(args.folder)
    if errors:
        print(t("cli.validate.errors", count=len(errors)))
        for e in errors:
            print(f"  - {e}")
        return 1
    print(t("cli.validate.ok", pages=len(read_pages(args.folder)), schema=SCHEMA_VERSION))
    return 0


if __name__ == "__main__":
    sys.exit(main())
