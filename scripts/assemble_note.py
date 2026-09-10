#!/usr/bin/env python3
"""
assemble_note.py — Combine the authored input folder with the derived repo data
into a complete release_note.yaml. No copy-paste, no hand-editing of generated
content.

Two clearly separated sources:

  AUTHORED (input folder, yours, safe to keep in git)
      versions.yaml    title, subtitle, SDK + modem versions, overview intro
      architecture.md  architecture / structural changes
      part_a.md        Part A subsections
      part_b.md        Part B subsections
      test_result.md   Test Result tables
      known_issues.md  Known Issues

  DERIVED (out/, disposable, regenerated every run)
      Part A / Part B change tables, every subsystem included
      meta From / To / Scope / Repositories, with resolved SHAs
      the Appendix commit-range table

The output file is entirely generated: delete it any time and re-run. Nothing
you wrote lives there, so there is no risk of losing prose to a regeneration.

Usage:
  python3 assemble_note.py --in-dir out/ --parts out/part_tables.yaml \
      --input-dir input/ --out out/release_note.yaml
"""
import argparse
import glob
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import load_all, InputError  # noqa: E402


def load_repo_data(in_dir):
    """Read fetch_local JSON, skipping its derived sibling files."""
    skip = {"part_tables", "change_table"}
    out = []
    for fp in sorted(glob.glob(os.path.join(in_dir, "*.json"))):
        if os.path.splitext(os.path.basename(fp))[0] in skip:
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        if "commits" in data and "repo" in data:
            out.append(data)
    if not out:
        raise SystemExit(f"no fetch_local JSON found in {in_dir} — run fetch_local.py first")
    out.sort(key=lambda d: (len(d.get("commits", [])), d.get("total_commits", 0)), reverse=True)
    return out


def short(sha, n=12):
    return (sha or "")[:n]


def _is_sha(ref):
    return bool(ref) and len(ref) >= 40 and all(c in "0123456789abcdef" for c in ref.lower())


def ref_name(ref):
    """Just the ref, no SHA. A raw SHA (a derived submodule ref) is shortened."""
    if not ref:
        return "(full history)"
    return short(ref) if _is_sha(ref) else ref


def part_intro(v, key, no_changes, default_intro, default_nochange_intro):
    """Pick the Part intro that matches what will actually render.

    When a Part has no changes its change table is removed, so the normal intro
    — which points at "the table below" — would refer to something that is not
    on the page. Authors can override either wording in versions.yaml:

        part_a_intro:             used when the Part has changes
        part_a_intro_no_changes:  used when it does not

    With no override set, the no-change intro falls back to a table-free
    sentence rather than reusing the one that mentions a table.
    """
    if no_changes:
        return (v.get(f"{key}_intro_no_changes")
                or v.get(f"{key}_intro_nochange")
                or default_nochange_intro)
    return v.get(f"{key}_intro") or default_intro


def build_meta(v, repos, parts):
    """Authored version fields, then the From/To baselines with their dates.

    Deliberately NOT here: the repository list, a commit-count "Scope" line, and
    the commit SHAs beside From/To. The header is for versions and dates; the
    per-repo ranges and SHAs live in the appendix, where someone reproducing the
    build will look for them.
    """
    primary = repos[0]
    total = sum(len(d.get("commits", [])) for d in repos)
    n_rows = sum(len((t or {}).get("change_table", {}).get("rows", []))
                 for t in (parts.get("part_a"), parts.get("part_b")))

    meta = []
    for label, key in (("SDK version", "sdk_version"),
                       ("Modem version", "modem_version"),
                       ("Platform", "platform")):
        if v.get(key):
            meta.append({"label": label, "value": str(v[key])})
    for extra in v.get("extra_meta") or []:
        if isinstance(extra, dict) and extra.get("label"):
            meta.append({"label": extra["label"], "value": str(extra.get("value", ""))})

    def dated(ref_key, date_key):
        val = f"`{ref_name(primary.get(ref_key))}`"
        date = primary.get(date_key)
        return val + (f" ({date})" if date else "")

    meta.append({"label": "From", "value": dated("from_ref", "from_date")})
    meta.append({"label": "To", "value": dated("to_ref", "to_date")})
    return meta, total, n_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", required=True, help="Directory of fetch_local.py JSON")
    ap.add_argument("--parts", required=True, help="out/part_tables.yaml from build_parts.py")
    ap.add_argument("--input-dir", required=True, help="Authored input folder")
    ap.add_argument("--out", required=True, help="release_note.yaml to write (fully generated)")
    ap.add_argument("--build-ids", default=None,
                    help="build_ids.yaml from parse_about.py. When present, Appendix A "
                         "becomes the per-subsystem Build ID comparison and the commit "
                         "range moves to Appendix B.")
    args = ap.parse_args()

    repos = load_repo_data(args.in_dir)
    with open(args.parts, encoding="utf-8") as f:
        parts = yaml.safe_load(f) or {}
    try:
        src = load_all(args.input_dir)
    except InputError as e:
        raise SystemExit(f"error: {e}")

    v = src["versions"]
    meta, total, n_rows = build_meta(v, repos, parts)

    # A Part with nothing in it drops its change table entirely (house rule),
    # so its intro must not promise a table that will not be there.
    a_nochange = bool((parts.get("part_a") or {}).get("no_changes", False))
    b_nochange = bool((parts.get("part_b") or {}).get("no_changes", False))

    note = {
        "title": v.get("title") or "REPLACE_ME title (set it in versions.yaml)",
        "subtitle": v.get("subtitle", ""),
        "meta": meta,
        "overview": {
            "intro": v.get("overview") or
                     f"This release covers {total} commits across {n_rows} subsystem rows.",
            "architecture_changes": src["architecture_changes"],
            "domains": v.get("domains") or [
                "**Part A — Linux SDK & Services:** see Section 2.",
                "**Part B — Chipcode (Firmware):** see Section 3.",
            ],
            # Filled in below only when there is an appendix to point at.
            "appendix_note": "",
        },
        "part_a": {
            "heading": v.get("part_a_heading", "2. Part A — Linux SDK & Services"),
            "intro": part_intro(
                v, "part_a", a_nochange,
                "The table lists the subsystems that changed in this release, one row "
                "per commit. Subsystems with no commits in the range are not listed.",
                "Userspace, SDK and build changes for the AQ20 Linux 3.18 line."),
            "change_table": (parts.get("part_a") or {}).get("change_table", {}),
            "no_changes": a_nochange,
            "subsections": src["part_a_subsections"],
        },
        "part_b": {
            "heading": v.get("part_b_heading", "3. Part B — Chipcode (Firmware)"),
            "intro": part_intro(
                v, "part_b", b_nochange,
                "Firmware images that changed in this release, each listed with the "
                "commit that changed it. Images with no commits are not listed.",
                "Firmware images: MPSS, BOOT, RPM, TrustZone, BTFM, CNSS."),
            "change_table": (parts.get("part_b") or {}).get("change_table", {}),
            "no_changes": b_nochange,
            "subsections": src["part_b_subsections"],
        },
        "test_results": {
            "heading": "4. Test Result",
            "intro": src["test_intro"] or
                     "REPLACE_ME — state which hardware these results came from and who ran them.",
            "tables": src["test_tables"] or [{
                "heading": "4.1 Test Cases",
                "headers": ["Test Case", "Result"],
                "rows": [["REPLACE_ME — add tables to input/test_result.md", "REPLACE_ME"]],
            }],
        },
        "known_issues": {
            "heading": "5. Known Issues",
            "points": src["known_issues"] or
                      ["REPLACE_ME — add entries to input/known_issues.md"],
        },
        # No commit-range appendix. The only appendix is the Build ID table,
        # added below when about.html is configured; with no build IDs the
        # document simply ends after Known Issues. Per-repo ranges and SHAs
        # remain available in out/snapshot.md and out/*.json.
    }

    # Build IDs from about.html, when available, become Appendix A — that is
    # what the reference document leads with, and it is the table a customer
    # actually checks. The commit range then becomes Appendix B.
    if args.build_ids:
        bid = None
        if os.path.exists(args.build_ids):
            with open(args.build_ids, encoding="utf-8") as f:
                bid = (yaml.safe_load(f) or {}).get("appendix_build_ids")
        if not (bid and bid.get("rows")):
            # Appendix A is the Build ID table. Quietly swapping in the commit
            # range would put a table under a heading that promises something
            # else, which is worse than stopping.
            raise SystemExit(
                f"error: no build IDs extracted for Appendix A ({args.build_ids}).\n"
                f"       Check what about.html actually contains:\n"
                f"         python3 scripts/parse_about.py --repo <clone> --ref <ref> --dump\n"
                f"       Or clear `about_html:` in versions.yaml to fall back to the\n"
                f"       commit range as Appendix A.")
        note["appendix"] = {
            "heading": "Appendix A — Build ID",
            "intro": v.get("appendix_intro",
                           "Per-subsystem build IDs, read from `about.html` in the AQ20 "
                           "repository at each release ref."),
            "table": bid,
            "footer_notes": ["Extracted from `about.html`; a subsystem marked Unchanged "
                             "carries the identical build ID in both releases."],
        }
        note["overview"]["appendix_note"] = (
            "Per-subsystem build IDs are in **Appendix A**.")
        print(f"  Appendix A: {len(bid['rows'])} build ID(s) from about.html")

    # Keep the author's table labels if they set them.
    for key in ("part_a", "part_b"):
        lbl = v.get(f"{key}_change_label")
        if lbl and note[key].get("change_table"):
            note[key]["change_table"]["label"] = lbl

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# GENERATED by assemble_note.py — do not edit.\n"
                f"# Authored content comes from: {os.path.abspath(args.input_dir)}\n"
                f"# Tables and metadata are derived from the repos in {args.in_dir}.\n"
                f"# This file is disposable; delete it and re-run at any time.\n\n")
        yaml.safe_dump(note, f, sort_keys=False, width=100, allow_unicode=True)

    a = len(note["part_a"]["change_table"].get("rows", []))
    b = len(note["part_b"]["change_table"].get("rows", []))
    print(f"wrote {args.out}")
    print(f"  authored : {args.input_dir}")
    print(f"  Part A: {a} table rows, {len(src['part_a_subsections'])} subsection(s)")
    print(f"  Part B: {b} table rows, {len(src['part_b_subsections'])} subsection(s)")
    print(f"  Test Result: {len(note['test_results']['tables'])} table(s)   "
          f"Known Issues: {len(note['known_issues']['points'])}")

    def count_ph(node):
        if isinstance(node, dict):
            return sum(count_ph(x) for x in node.values())
        if isinstance(node, list):
            return sum(count_ph(x) for x in node)
        return 1 if isinstance(node, str) and "REPLACE_ME" in node else 0

    n = count_ph(note)
    if n:
        print(f"\n  {n} REPLACE_ME placeholder(s) remain — fill them in under "
              f"{args.input_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
