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
    python -m docaudit group DIR [--threshold 0.6] [--semantic] [--scan]
    python -m docaudit group-eval DIR [--expected FILE]
    python -m docaudit group-merge DIR PAGINA_A PAGINA_B
    python -m docaudit group-detach DIR PAGINA
    python -m docaudit compare DIR                 (după „group”; scrie findings.json)
    python -m docaudit compare-eval DIR [--expected FILE]
    python -m docaudit                             (fără comandă: iconiță în tray + interfața în browser)
    python -m docaudit ui [--port N] [--no-browser]
    python -m docaudit report DIR [--format html|csv|md] [--out FILE]
    python -m docaudit apply DIR [--yes]          (previzualizare; --yes scrie în OneNote, dacă e permis)
    python -m docaudit restore DIR NUMĂR
    python -m docaudit make-icon FOLDER
    python -m docaudit download-model              (o singură dată, singura comandă cu internet)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .i18n import t
from .model import SCHEMA_VERSION, read_pages, validate_dataset
from .paths import data_dir, resolve_folder
from .sample import DEFAULT_SEED, write_sample

DEFAULT_SAMPLE_DIR = Path("tests/fixtures/sample_v1")


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


def _tree_link(hierarchy, link: str) -> int:
    from .extract.links import LinkError, match_link, parse_link

    try:
        info = parse_link(link)
    except LinkError:
        print(t("ui.error.link"))
        return 2
    m = match_link(hierarchy, info)
    if m is None:
        print(t("cli.tree.link.missing"))
        if info.open_url:
            print(f"  {info.open_url}")
        return 1
    print(t("cli.tree.link.found", notebook=m.notebook, section=m.section or "-"))
    return 0


def _source(demo: bool):
    if demo:
        from .extract.demo import DemoOneNote

        return DemoOneNote(), "demo (eșantion fictiv)"
    from .extract.com import ReadOnlyOneNote

    return ReadOnlyOneNote(), "OneNote desktop (COM)"


def _utf8_output() -> None:
    """Pe Windows, ieșirea redirecționată (de ex. `>nul` în Install.bat) folosește cp1252 și nu poate scrie
    diacritice românești (ă, ț, ș). Trecem pe UTF-8, iar un caracter imposibil devine „?”, nu o eroare."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # fluxul nu poate fi reconfigurat
                pass


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is None:  # pythonw: fără consolă
        import io
        import os

        sys.stdout = sys.stderr = io.TextIOWrapper(open(os.devnull, "wb"), encoding="utf-8")  # noqa: SIM115
    _utf8_output()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        from .tray import run_app

        return run_app()
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
    p_tree.add_argument("--link", help=t("cli.tree.link"))

    p_diag = sub.add_parser("diagnose", help=t("cli.diagnose.help"))
    p_diag.add_argument("--demo", action="store_true", help=t("cli.extract.demo"))

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

    p_grp = sub.add_parser("group", help=t("cli.group.help"))
    p_grp.add_argument("folder", type=Path)
    p_grp.add_argument("--threshold", type=float, default=None, help=t("cli.group.threshold"))
    p_grp.add_argument("--semantic", action="store_true", help=t("cli.group.semantic"))
    p_grp.add_argument("--scan", action="store_true", help=t("cli.group.scan"))

    p_gev = sub.add_parser("group-eval", help=t("cli.groupeval.help"))
    p_gev.add_argument("folder", type=Path)
    p_gev.add_argument("--expected", type=Path, default=None)

    p_gm = sub.add_parser("group-merge", help=t("cli.groupmerge.help"))
    p_gm.add_argument("folder", type=Path)
    p_gm.add_argument("page_a")
    p_gm.add_argument("page_b")

    p_gd = sub.add_parser("group-detach", help=t("cli.groupdetach.help"))
    p_gd.add_argument("folder", type=Path)
    p_gd.add_argument("page")

    p_cmp = sub.add_parser("compare", help=t("cli.compare.help"))
    p_cmp.add_argument("folder", type=Path)

    p_cev = sub.add_parser("compare-eval", help=t("cli.compareeval.help"))
    p_cev.add_argument("folder", type=Path)
    p_cev.add_argument("--expected", type=Path, default=None)

    p_ui = sub.add_parser("ui", help=t("cli.ui.help"))
    p_ui.add_argument("--port", type=int, default=None, help=t("cli.ui.port"))
    p_ui.add_argument("--no-browser", action="store_true", help=t("cli.ui.nobrowser"))

    p_rep = sub.add_parser("report", help=t("cli.report.help"))
    p_rep.add_argument("folder", type=Path)
    p_rep.add_argument("--format", choices=["html", "csv", "md"], default="html")
    p_rep.add_argument("--out", type=Path, default=None)

    p_app = sub.add_parser("apply", help=t("cli.apply.help"))
    p_app.add_argument("folder", type=Path)
    p_app.add_argument("--yes", action="store_true", help=t("cli.apply.yes"))

    p_res = sub.add_parser("restore", help=t("cli.restore.help"))
    p_res.add_argument("folder", type=Path)
    p_res.add_argument("number", type=int)

    p_icon = sub.add_parser("make-icon", help=t("cli.icon.help"))
    p_icon.add_argument("folder", type=Path)

    sub.add_parser("download-model", help=t("cli.model.help"))

    p_imp = sub.add_parser("import-files", help=t("cli.import.help"))
    p_imp.add_argument("folder", type=Path)
    p_imp.add_argument("--out", type=Path, help=t("cli.extract.out"))

    args = parser.parse_args(argv)

    if args.cmd == "sample":
        n = write_sample(args.out, args.seed)
        print(t("cli.sample.done", pages=n, path=args.out))
        return 0

    if args.cmd == "validate":
        args.folder = resolve_folder(args.folder)
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

        problems = compare_to_sample(resolve_folder(args.folder))
        for pr in problems:
            print(f"  - {pr}")
        print(t("cli.check.result", count=len(problems)))
        return 1 if problems else 0

    if args.cmd in ("group", "group-eval", "group-merge", "group-detach"):
        return _group_commands(args)

    if args.cmd in ("compare", "compare-eval"):
        return _compare_commands(args)

    if args.cmd in ("ui", "report", "apply", "restore", "make-icon"):
        return _app_commands(args)

    if args.cmd == "download-model":
        from .group.semantic import SemanticUnavailable, download_model

        try:
            print(t("cli.model.done", model=download_model()))
        except SemanticUnavailable:
            print(t("cli.model.missing"))
            return 2
        return 0

    if args.cmd == "import-files":
        from .extract.files import import_files

        out = resolve_folder(args.out) if args.out else data_dir() / "import"
        report = import_files(args.folder, out)
        for e in report.errors:
            print(t("cli.extract.error", error=e))
        print(t("cli.extract.done", total=report.total, fetched=report.fetched, reused=report.reused,
                skipped=report.skipped, removed=report.removed, path=out))
        return 1 if report.errors else 0

    if args.cmd == "diagnose":
        from .extract.diagnose import diagnose

        if args.demo:
            from .extract.demo import DemoOneNote

            checks = diagnose(DemoOneNote, windows_checks=False)
        else:
            checks = diagnose()
        for c in checks:
            mark = {True: "OK ", False: "NU ", None: " - "}[c.ok]
            print(f"[{mark}] {t('diag.' + c.key)}" + (f": {c.detail}" if c.detail else ""))
            if c.ok is False:
                print("       → " + t(f"diag.{c.key}.fix"))
        return 0 if all(c.ok for c in checks) else 1

    # tree / extract au nevoie de OneNote (sau de demo)
    from .extract.com import OneNoteError

    try:
        source, label = _source(args.demo)
    except OneNoteError as e:
        print(t("cli.onenote.unavailable", error=e))
        return 2

    if args.cmd == "tree":
        from .extract.onenote_xml import parse_hierarchy

        try:
            hierarchy = parse_hierarchy(source.get_hierarchy_xml())
        except OneNoteError as e:
            print(t("cli.onenote.unavailable", error=e))
            return 2
        if args.link:
            return _tree_link(hierarchy, args.link)
        if not hierarchy.notebooks:
            print(t("cli.tree.empty"))
            return 1
        for nb in hierarchy.notebooks:
            print(f"{nb.name}  [{nb.location}]" if nb.location else nb.name)
            for sec in nb.sections:
                print(f"  {'/'.join(sec.path)} — {t('cli.tree.pages', count=len(sec.pages))}")
        return 0

    from .extract.run import extract_to_dataset

    out = resolve_folder(args.out) if args.out else data_dir() / (args.profile or ("demo" if args.demo else "onenote"))
    try:
        report = extract_to_dataset(
            source, _selection(args), out, incremental=not args.full, source_label=label,
            progress=lambda n, total, title: print(t("cli.extract.progress", n=n, total=total, title=title)),
        )
    except OneNoteError as e:
        print(t("cli.onenote.unavailable", error=e))
        return 2
    for e in report.errors:
        print(t("cli.extract.error", error=e))
    print(t("cli.extract.done", total=report.total, fetched=report.fetched, reused=report.reused,
            skipped=report.skipped, removed=report.removed, path=out))
    return 1 if report.errors else 0


def _group_commands(args: argparse.Namespace) -> int:
    import json

    from .group.overrides import GroupOverrides
    from .group.run import DEFAULT_THRESHOLD, load_groups, run_grouping, scan_thresholds
    from .group.semantic import SemanticUnavailable

    folder = resolve_folder(args.folder)
    if args.cmd == "group":
        try:
            if args.scan:
                for th, n_groups, n_pages in scan_thresholds(
                        folder, [round(0.3 + 0.05 * i, 2) for i in range(14)], use_semantic=args.semantic):
                    print(t("cli.group.scanrow", threshold=th, groups=n_groups, pages=n_pages))
                return 0
            threshold = args.threshold if args.threshold is not None else DEFAULT_THRESHOLD
            result = run_grouping(folder, threshold, use_semantic=args.semantic)
        except SemanticUnavailable as e:
            print(t("cli.group.nosemantic", error=e))
            return 2
        for g in result.groups:
            print(t("cli.group.row", label=g.label, count=len(g.pages), score=g.avg_score))
        print(t("cli.group.done", groups=len(result.groups), alone=len(result.ungrouped), threshold=threshold))
        return 0

    if args.cmd == "group-eval":
        from .group.evaluate import evaluate

        expected = json.loads((args.expected or folder / "expected.json").read_text("utf-8"))
        data = load_groups(folder)
        score = evaluate([g["pages"] for g in data["groups"]], expected, with_translations=data["semantic"])
        print(t("cli.groupeval.result", precision=score.precision, recall=score.recall, f1=score.f1))
        return 0

    ov = GroupOverrides.load(folder)
    if args.cmd == "group-merge":
        ov.merge(args.page_a, args.page_b)
    else:
        group = next((g for g in load_groups(folder)["groups"] if args.page in g["pages"]), None)
        if group is None:
            print(t("cli.groupdetach.notfound", page=args.page))
            return 1
        ov.detach(args.page, group["pages"])
    ov.save(folder)
    print(t("cli.groupoverride.saved"))
    return 0


def _compare_commands(args: argparse.Namespace) -> int:
    import json

    from .compare.run import load_findings, run_compare

    folder = resolve_folder(args.folder)
    if args.cmd == "compare-eval":
        from .compare.evaluate import evaluate_compare

        expected = json.loads((args.expected or folder / "expected.json").read_text("utf-8"))
        s = evaluate_compare(load_findings(folder), expected)
        print(t("cli.compareeval.result", found=s.conflicts_found, planted=s.conflicts_planted,
                false_rate=s.false_alarm_rate, steps_found=s.step_diffs_found, steps_planted=s.step_diffs_planted,
                stale_found=s.stale_found, stale_planted=s.stale_planted, stale_extra=s.stale_extra,
                dup_found=s.duplicates_found, dup_planted=s.duplicates_planted))
        for m in s.missed:
            print(f"  - {m}")
        return 0

    try:
        result = run_compare(folder)
    except FileNotFoundError:
        print(t("cli.compare.nogroups", path=folder))
        return 1
    titles = {p.id: p.title for p in read_pages(folder)}
    labels = {g["id"]: g["label"] for g in json.loads((folder / "groups.json").read_text("utf-8"))["groups"]}

    def names(ids: list[str]) -> str:
        return ", ".join(f"{titles.get(i, i)} [{i}]" for i in ids)

    for g in result.groups:
        if not g.findings:
            continue
        ref = names([g.reference]) if g.reference else "—"
        print(t("cli.compare.group", label=labels.get(g.group, g.group), count=len(g.findings), reference=ref))
        for f in g.findings:
            print(_finding_line(f, names))
    for f in result.shared_images:
        print(t("cli.compare.shared_image", pages=names(f.pages)))
    found = result.findings()
    kinds = [f.kind for f in found]
    print(t("cli.compare.done", groups=len(result.groups), conflicts=kinds.count("value_conflict"),
            steps=sum(kinds.count(k) for k in ("missing_step", "extra_step", "reordered")),
            duplicates=kinds.count("duplicate"), stale=kinds.count("stale")))
    return 0


def _finding_line(f, names) -> str:
    d = f.details
    if f.kind == "value_conflict":
        values = " · ".join(f"{v or '—'} [{p}]" for p, v in d["values"].items())
        return t("cli.compare.value_conflict", values=values)
    if f.kind in ("missing_step", "extra_step"):
        return t(f"cli.compare.{f.kind}", pages=names(f.pages), text=d["text"])
    if f.kind == "reordered":
        return t("cli.compare.reordered", page=names([d["page"]]), text=" / ".join(d["texts"]))
    if f.kind == "duplicate":
        return t("cli.compare.duplicate", similarity=d["similarity"], pages=names(f.pages))
    reasons = []
    for r in d["reasons"]:
        if r["reason"] == "marker":
            reasons.append(t("cli.compare.reason.marker", value=", ".join(r["markers"])))
        elif r["reason"] == "old":
            reasons.append(t("cli.compare.reason.old", days=r["days_older"]))
        else:
            reasons.append(t(f"cli.compare.reason.{r['reason']}", value=r["value"], other=r.get("other", "")))
    return t("cli.compare.stale", page=names(f.pages), reasons="; ".join(reasons))


def _app_commands(args: argparse.Namespace) -> int:
    from .settings import load_settings

    settings = load_settings()
    if args.cmd == "make-icon":
        from .icon import write_icons

        print(t("cli.icon.done", path=write_icons(args.folder)))
        return 0
    if args.cmd == "ui":  # pragma: no cover - pornire interactivă
        import webbrowser

        from .ui.server import make_server

        server = make_server(args.port or settings.port)
        print(t("cli.ui.started", url=server.url))
        if not args.no_browser:
            webbrowser.open(server.url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    folder = resolve_folder(args.folder)
    if args.cmd == "report":
        from .report import build_state, render

        out = args.out or folder / f"raport.{args.format}"
        out.write_text(render(build_state(folder), args.format), encoding="utf-8", newline="\n")
        print(t("cli.report.done", path=out))
        return 0

    from .apply.run import WriteDisabled, apply, plan, restore, writer_for
    from .extract.com import OneNoteError

    try:
        writer = writer_for(folder)
        if args.cmd == "restore":
            print(t("cli.restore.done", section=restore(folder, writer, settings, args.number)["section"]))
            return 0
        items = plan(folder, writer, settings)
        if not items:
            print(t("cli.apply.none"))
            return 0
        for it in items:
            extra = t(f"ui.apply.reason.{it.reason}") if it.reason else ""
            print(t("cli.apply.row", status=t("ui.apply.ready") if it.status == "ready" else "—", id=it.decision_id,
                    action=t(f"ui.action.{it.action}"), title=it.title, where=f"{it.notebook} › {it.section}",
                    extra=extra))
        if not args.yes:
            print(t("cli.apply.preview"))
            return 0
        r = apply(folder, writer, settings, [it.decision_id for it in items if it.status == "ready"])
        for e in r.errors:
            print(f"  ⚠ {e['title']}: {e['error']}")
        print(t("cli.apply.result", done=len(r.done), skipped=len(r.skipped), errors=len(r.errors)))
        return 1 if r.errors else 0
    except (WriteDisabled, OneNoteError, ValueError) as e:
        print(e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
