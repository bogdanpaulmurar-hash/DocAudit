"""Linia de comandă DocAudit.

    python -m docaudit sample [--out DIR] [--seed N]
    python -m docaudit validate DIR
    python -m docaudit tree [--demo]
    python -m docaudit extract [--profile NUME | --notebook X --section "NB/S" --page ID] [--out DIR] [--demo] [--full]
    python -m docaudit profile save NUME [--notebook ... --section ... --page ... --exclude ...]
    python -m docaudit profile list
    python -m docaudit import-files FOLDER [--out DIR]
    python -m docaudit make-test-notebook FOLDER   (Windows: notebook NOU cu eșantionul)
    python -m docaudit check-sample DIR            (compară o extragere cu eșantionul)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .i18n import t
from .model import SCHEMA_VERSION, read_pages, validate_dataset
from .sample import DEFAULT_SEED, write_sample

DEFAULT_SAMPLE_DIR = Path("tests/fixtures/sample_v1")


def data_dir() -> Path:
    return Path(os.environ.get("DOCAUDIT_DATA", "data"))


def _add_selection_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--notebook", action="append", default=[], help=t("cli.select.notebook"))
    p.add_argument("--section", action="append", default=[], help=t("cli.select.section"))
    p.add_argument("--page", action="append", default=[], help=t("cli.select.page"))
    p.add_argument("--exclude", action="append", default=None, help=t("cli.select.exclude"))


def _selection(args: argparse.Namespace):
    from .extract.selection import DEFAULT_ARCHIVE, Selection, load_profile

    if getattr(args, "profile", None):
        return load_profile(data_dir() / "profiles", args.profile)
    return Selection(notebooks=args.notebook, sections=args.section, pages=args.page,
                     exclude_sections=args.exclude if args.exclude is not None else [DEFAULT_ARCHIVE])


def _source(demo: bool):
    if demo:
        from .extract.demo import DemoOneNote

        return DemoOneNote(), "demo (eșantion fictiv)"
    from .extract.com import ReadOnlyOneNote

    return ReadOnlyOneNote(), "OneNote desktop (COM)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docaudit", description=t("cli.description"))
    parser.add_argument("--version", action="version", version=t("cli.version", version=__version__))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sample = sub.add_parser("sample", help=t("cli.sample.help"))
    p_sample.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_DIR, help=t("cli.sample.out"))
    p_sample.add_argument("--seed", type=int, default=DEFAULT_SEED)

    p_val = sub.add_parser("validate", help=t("cli.validate.help"))
    p_val.add_argument("folder", type=Path)

    p_tree = sub.add_parser("tree", help=t("cli.tree.help"))
    p_tree.add_argument("--demo", action="store_true", help=t("cli.extract.demo"))

    p_ext = sub.add_parser("extract", help=t("cli.extract.help"))
    _add_selection_args(p_ext)
    p_ext.add_argument("--profile", help=t("cli.select.profile"))
    p_ext.add_argument("--out", type=Path, help=t("cli.extract.out"))
    p_ext.add_argument("--demo", action="store_true", help=t("cli.extract.demo"))
    p_ext.add_argument("--full", action="store_true", help=t("cli.extract.full"))

    p_prof = sub.add_parser("profile", help=t("cli.profile.help"))
    prof_sub = p_prof.add_subparsers(dest="action", required=True)
    p_save = prof_sub.add_parser("save")
    p_save.add_argument("name")
    _add_selection_args(p_save)
    prof_sub.add_parser("list")

    p_mk = sub.add_parser("make-test-notebook", help=t("cli.testnb.help"))
    p_mk.add_argument("folder", type=Path, help=t("cli.testnb.folder"))

    p_chk = sub.add_parser("check-sample", help=t("cli.check.help"))
    p_chk.add_argument("folder", type=Path)

    p_imp = sub.add_parser("import-files", help=t("cli.import.help"))
    p_imp.add_argument("folder", type=Path)
    p_imp.add_argument("--out", type=Path, help=t("cli.extract.out"))

    args = parser.parse_args(argv)

    if args.cmd == "sample":
        n = write_sample(args.out, args.seed)
        print(t("cli.sample.done", pages=n, path=args.out))
        return 0

    if args.cmd == "validate":
        errors = validate_dataset(args.folder)
        if errors:
            print(t("cli.validate.errors", count=len(errors)))
            for e in errors:
                print(f"  - {e}")
            return 1
        print(t("cli.validate.ok", pages=len(read_pages(args.folder)), schema=SCHEMA_VERSION))
        return 0

    if args.cmd == "profile":
        from .extract.selection import list_profiles, save_profile

        profiles = data_dir() / "profiles"
        if args.action == "save":
            print(t("cli.profile.saved", path=save_profile(profiles, args.name, _selection(args))))
        else:
            names = list_profiles(profiles)
            print("\n".join(names) if names else t("cli.profile.none"))
        return 0

    if args.cmd == "make-test-notebook":
        from .testnotebook import create_test_notebook

        print(t("cli.testnb.done", pages=create_test_notebook(args.folder), path=args.folder))
        return 0

    if args.cmd == "check-sample":
        from .extract.check import compare_to_sample

        problems = compare_to_sample(args.folder)
        for pr in problems:
            print(f"  - {pr}")
        print(t("cli.check.result", count=len(problems)))
        return 1 if problems else 0

    if args.cmd == "import-files":
        from .extract.files import import_files

        out = args.out or data_dir() / "import"
        report = import_files(args.folder, out)
        for e in report.errors:
            print(t("cli.extract.error", error=e))
        print(t("cli.extract.done", total=report.total, fetched=report.fetched, reused=report.reused,
                skipped=report.skipped, removed=report.removed, path=out))
        return 1 if report.errors else 0

    # tree / extract au nevoie de OneNote (sau de demo)
    from .extract.com import OneNoteError

    try:
        source, label = _source(args.demo)
    except OneNoteError as e:
        print(t("cli.onenote.unavailable", error=e))
        return 2

    if args.cmd == "tree":
        from .extract.onenote_xml import parse_hierarchy

        for nb in parse_hierarchy(source.get_hierarchy_xml()).notebooks:
            print(nb.name)
            for sec in nb.sections:
                print(f"  {'/'.join(sec.path)} — {t('cli.tree.pages', count=len(sec.pages))}")
        return 0

    from .extract.run import extract_to_dataset

    out = args.out or data_dir() / (args.profile or ("demo" if args.demo else "onenote"))
    report = extract_to_dataset(
        source, _selection(args), out, incremental=not args.full, source_label=label,
        progress=lambda n, total, title: print(t("cli.extract.progress", n=n, total=total, title=title)),
    )
    for e in report.errors:
        print(t("cli.extract.error", error=e))
    print(t("cli.extract.done", total=report.total, fetched=report.fetched, reused=report.reused,
            skipped=report.skipped, removed=report.removed, path=out))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
