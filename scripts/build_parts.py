#!/usr/bin/env python3
"""
build_parts.py — Generate the Part A and Part B change tables straight from the
fetched commits, with EVERY configured subsystem present.

This closes the last manual gap in the pipeline. Previously you pasted the
change rows by hand and had to remember to add "no change" rows for untouched
subsystems. Now:

  - a subsystem WITH commits in the range gets one row per commit, showing that
    commit's own SHA and subject;
  - a subsystem WITHOUT commits is left out of the table — the change table
    lists changes, and every such subsystem is still named in the run summary
    and recorded in out/snapshot.md. `--keep-unchanged` puts the rows back,
    each carrying the commit that LAST TOUCHED IT (never the repo HEAD, which
    in a monorepo is one commit shared by every directory and so says nothing);
  - a Part left with no rows at all is marked no_changes, and the templates
    replace its table with a single "No changes on this release." line;
  - a subsystem whose path matches no commit at all is flagged loudly, because
    a typo'd path would otherwise vanish silently as a "no change".

Nothing is silently dropped: commits that fall outside every configured
subsystem are reported and collected into an "Unassigned" row so you notice the
gap in your `subsystems:` list rather than shipping an incomplete table.

Input:  repos.yaml with a `subsystems:` list per repo, each entry tagged
        `part: A` or `part: B`, plus the out/*.json from fetch_local.py.
Output: out/part_tables.yaml   — paste the part_a/part_b blocks into your
                                 release_note.yaml
        out/part_tables.md     — same thing, readable, for review

Usage:
  python3 build_parts.py --repos-file config/aq20/repos.yaml \
      --in-dir out/ --out out/part_tables.yaml
"""
import argparse
import glob
import json
import os
import re
import sys

import yaml

# Exact wording requested by the customer-facing spec. Change it here and
# it changes everywhere: the per-subsystem row and the Part-level statement.
NO_CHANGE = "No changes on this release"
CONVENTIONAL_PREFIX_RE = re.compile(r"^[a-z0-9_.\-/]+(\([^)]*\))?!?:\s")


def clean_subject(subject):
    subject = re.sub(r"\s*\(#\d+\)\s*$", "", subject or "").strip()
    if subject and subject[0].islower() and not CONVENTIONAL_PREFIX_RE.match(subject):
        subject = subject[0].upper() + subject[1:]
    return subject


def load_subsystems(repos_file):
    """Flatten every repo's subsystems into one list, preserving part + repo."""
    with open(repos_file, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    subs = []
    # Local paths of every configured repo, so a submodule that is ALSO tracked
    # as its own entry can be reported as "covered elsewhere" rather than as a
    # config error.
    configured_paths = {os.path.normpath(os.path.expanduser(e["local_path"])): e["name"]
                        for e in cfg.get("repos", []) if e.get("local_path")}
    for entry in cfg.get("repos", []):
        for s in entry.get("subsystems") or []:
            if isinstance(s, str):
                s = {"name": s, "path": s}
            spath = (s.get("path") or s.get("name")).strip("/")
            abs_sub = os.path.normpath(os.path.join(
                os.path.expanduser(entry.get("local_path", "")), spath))
            subs.append({
                "name": s.get("name") or s.get("path"),
                "path": spath,
                "part": str(s.get("part", "")).upper() or "A",
                "repo_entry": entry["name"],
                # If this path is itself a configured repo, its changes are
                # reported by that entry — not missing.
                "tracked_as": configured_paths.get(abs_sub),
            })
    if not subs:
        raise SystemExit(
            f"{repos_file} has no `subsystems:` entries.\n"
            "Add them — run  python3 scripts/fetch_local.py --list-subsystems <clone>\n"
            "to get a ready-to-paste block built from the repo itself."
        )
    return subs


def match_subsystem(filepath, subs):
    """Longest-path-wins, so a file under apps_proc/kernel is attributed to
    'apps_proc/kernel' and not also to a broader 'apps_proc' entry.

    A path of "." or "" means "the whole repo" — used when a repo entry has no
    internal breakdown. It matches anything but at the lowest possible
    precedence, so any concrete path still wins.

    `subs` must already be scoped to the repo the file came from.
    """
    best, best_len = None, -2
    for s in subs:
        p = s["path"]
        if p in ("", "."):
            ok, length = True, -1
        else:
            ok, length = (filepath == p or filepath.startswith(p + "/")), len(p)
        if ok and length > best_len:
            best, best_len = s, length
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-file", required=True)
    ap.add_argument("--in-dir", required=True, help="Directory of fetch_local.py JSON")
    ap.add_argument("--out", required=True, help="Output part_tables.yaml")
    ap.add_argument("--part-a-label", default="Linux SDK / services change set (Cavli commits):")
    ap.add_argument("--part-b-label", default="Chipcode change set (Cavli commits):")
    ap.add_argument("--keep-unchanged", action="store_true",
                    help="Keep a row for every subsystem with no commits in the range, "
                         "carrying its commit ID, its name and \"" + NO_CHANGE + "\". "
                         "OFF by default: the change table lists only what actually "
                         "changed. Unchanged subsystems are still named in the run "
                         "summary and listed in full in out/snapshot.md.")
    ap.add_argument("--omit-unchanged", action="store_true",
                    help=argparse.SUPPRESS)   # accepted for compatibility; now the default
    args = ap.parse_args()

    subs = load_subsystems(args.repos_file)

    # Nested subsystem paths are legal (longest match wins) but worth flagging,
    # since it is usually accidental. Only meaningful within one repo.
    for a in subs:
        for b in subs:
            if (a is not b and a["repo_entry"] == b["repo_entry"]
                    and b["path"] not in ("", ".") and a["path"] != b["path"]
                    and a["path"].startswith(b["path"] + "/")):
                print(f"  note: '{a['path']}' is nested inside '{b['path']}' — "
                      f"commits go to the deeper one", file=sys.stderr)

    files = sorted(glob.glob(os.path.join(args.in_dir, "*.json")))
    if not files:
        raise SystemExit(f"no *.json in {args.in_dir} — run fetch_local.py first")

    # Keyed by (repo entry, path): two repos may both define a subsystem called
    # "." or share a directory name, and their commits must never cross over.
    by_sub = {(s["repo_entry"], s["path"]): [] for s in subs}
    snapshots = {}
    unassigned = []

    for fp in files:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        entry_name = os.path.splitext(os.path.basename(fp))[0]
        repo_subs = [s for s in subs if s["repo_entry"] == entry_name]
        if not repo_subs:
            print(f"  note: {os.path.basename(fp)} has no matching repos.yaml entry "
                  f"named '{entry_name}' — its commits are skipped", file=sys.stderr)
            continue
        for s in data.get("subsystems") or []:
            snapshots[(entry_name, s["path"].strip("/"))] = s
        for c in data.get("commits", []):
            touched = {}
            for path in c.get("files", []):
                m = match_subsystem(path, repo_subs)
                if m:
                    touched[(entry_name, m["path"])] = m
            if touched:
                for key in touched:
                    by_sub[key].append(c)
            elif c.get("files"):
                unassigned.append(c)
            # merge commits with no files of their own are simply skipped

    rows = {"A": [], "B": []}
    missing_paths, covered_skipped, nested_repos = [], [], []
    nochange_names = {"A": [], "B": []}
    changed_by_part = {"A": 0, "B": 0}
    omit_unchanged = not args.keep_unchanged
    changed_n = nochange_n = 0

    for s in subs:
        part = s["part"] if s["part"] in ("A", "B") else "A"
        key = (s["repo_entry"], s["path"])
        commits = by_sub[key]
        snap = snapshots.get(key, {})
        nested = snap.get("is_nested_repo")
        if nested and not s.get("tracked_as"):
            nested_repos.append((s["name"], s["path"], snap.get("nested_repo_url")))

        if commits:
            # For a submodule these are gitlink bumps, not the work itself.
            suffix = ("  [submodule pointer bump — the actual changes are in "
                      "its own repo]") if nested else ""
            changed_n += len(commits)
            changed_by_part[part] += len(commits)
            for c in sorted(commits, key=lambda x: x.get("date", ""), reverse=True):
                rows[part].append([f'`{c["short_sha"]}`', s["name"],
                                   clean_subject(c["message_subject"]) + suffix])
        elif nested and not s.get("tracked_as"):
            # A submodule nobody is tracking separately: its commits are
            # invisible here, which is a config error, not a quiet "no change".
            # Always keep this row.
            rows[part].append([f'`{snap.get("last_commit", "n/a")}`', s["name"],
                               "NESTED REPO — its own commits are not visible from the "
                               "parent repo; add it to repos.yaml as a separate entry"])
        elif snap.get("covered_by_children"):
            # Must be tested BEFORE the missing-path branch: a fully-covered
            # catch-all also reports last_commit "n/a", and calling it a broken
            # path would send someone chasing a config error that isn't there.
            covered_skipped.append(s["name"])
        elif snap.get("path_missing") or snap.get("last_commit") in (None, "", "n/a"):
            # An error: a typo'd path must never look like "nothing changed".
            missing_paths.append(s["path"])
            rows[part].append(["`n/a`", s["name"],
                               "PATH NOT FOUND IN REPO — check subsystems: in repos.yaml"])
        else:
            # Unchanged subsystem (including a submodule whose pointer did not
            # move and which is tracked by its own repo entry). It is DROPPED
            # from the change table: the table is a list of changes, and a row
            # saying "nothing happened here" is not one. It is still counted,
            # named in the run summary below, and recorded in out/snapshot.md,
            # so dropped never means unaccounted for.
            #
            # --keep-unchanged puts the row back, carrying the commit that last
            # touched this subsystem plus NO_CHANGE in the Change column.
            nochange_n += 1
            nochange_names[part].append(s["name"])
            if not omit_unchanged:
                rows[part].append([f'`{snap["last_commit"]}`', s["name"], NO_CHANGE])

    if unassigned:
        # Real commits, just unattributed — they count as changes in Part A.
        changed_by_part["A"] += len(unassigned)
        for c in sorted(unassigned, key=lambda x: x.get("date", ""), reverse=True):
            rows["A"].append([f'`{c["short_sha"]}`', "Unassigned — not under any subsystem",
                              clean_subject(c["message_subject"])])

    # A Part where nothing at all moved is called out above its table too, so
    # the reader gets it in one line instead of scanning every row.
    out = {
        "part_a": {"change_table": {"label": args.part_a_label,
                                    "headers": ["Commit", "Area", "Change"],
                                    "rows": rows["A"]},
                   "no_changes": changed_by_part["A"] == 0},
        "part_b": {"change_table": {"label": args.part_b_label,
                                    "headers": ["Commit", "Image", "Change"],
                                    "rows": rows["B"]},
                   "no_changes": changed_by_part["B"] == 0},
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# Generated by build_parts.py — paste these blocks into release_note.yaml.\n"
                "# Every configured subsystem appears: changed ones with their commits,\n"
                "# unchanged ones with the commit that last touched them.\n"
                "# Curate before shipping: drop noise commits, reword terse subjects.\n\n")
        yaml.safe_dump(out, f, sort_keys=False, width=120, allow_unicode=True)

    md = os.path.splitext(args.out)[0] + ".md"
    with open(md, "w", encoding="utf-8") as f:
        for part, key, hdr in (("A", "part_a", "Area"), ("B", "part_b", "Image")):
            f.write(f"\n## Part {part}\n\n| Commit | {hdr} | Change |\n|---|---|---|\n")
            for r in out[key]["change_table"]["rows"]:
                f.write(f"| {r[0]} | {r[1]} | {r[2]} |\n")

    print(f"wrote {args.out} and {md}")
    print(f"  Part A rows: {len(rows['A'])}   Part B rows: {len(rows['B'])}")
    if omit_unchanged:
        print(f"  {changed_n} commit row(s); {nochange_n} unchanged subsystem(s) "
              f"omitted from the table (--keep-unchanged lists them)")
    else:
        print(f"  {changed_n} commit row(s), {nochange_n} unchanged subsystem(s) "
              f"listed as \"{NO_CHANGE}\"")
    # Name them either way, so "omitted" never means "unaccounted for".
    # Full per-subsystem state is in out/snapshot.md.
    for part in ("A", "B"):
        if nochange_names[part]:
            print(f"    Part {part} unchanged: {', '.join(nochange_names[part])}")
    if nested_repos:
        print(f"\n  WARNING: {len(nested_repos)} subsystem(s) are nested git repos / "
              f"submodules. The parent repo records only a pointer to them, so their\n"
              f"  own commits do NOT appear above:", file=sys.stderr)
        for name, path, url in nested_repos:
            print(f"    - {name}  ({path})  -> {url}", file=sys.stderr)
        print("  Add each as its own entry in repos.yaml, e.g.:\n"
              "    - name: AQ20_cavli\n"
              "      local_path: <clone>/" + nested_repos[0][1] + "\n"
              "      from_ref: <prev release>\n"
              "      to_ref: <this release>\n"
              "      subsystems: [...]", file=sys.stderr)
    if covered_skipped:
        print(f"  skipped {len(covered_skipped)} catch-all entr(y/ies) fully covered by "
              f"more specific subsystems: {', '.join(covered_skipped)}")
    if missing_paths:
        print(f"\n  WARNING: {len(missing_paths)} subsystem path(s) matched nothing in the repo:",
              file=sys.stderr)
        for p in missing_paths:
            print(f"    - {p}", file=sys.stderr)
        print("  They are in the table flagged PATH NOT FOUND. Fix repos.yaml or remove them.",
              file=sys.stderr)
    if unassigned:
        print(f"\n  WARNING: {len(unassigned)} commit(s) touched no configured subsystem "
              f"and were added to Part A as 'Unassigned':", file=sys.stderr)
        for c in unassigned[:10]:
            print(f"    - {c['short_sha']}  {c['message_subject'][:70]}", file=sys.stderr)
        print("  Add the missing paths to subsystems: so they are attributed properly.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
