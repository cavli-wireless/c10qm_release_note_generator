#!/usr/bin/env python3
"""
suggest_baseline.py — Work out a sensible From/To range for a repo that has no
release tags.

Tags are the easy case: `from_ref` is last release's tag. Plenty of firmware
repos don't tag at all, and then you need another way to answer "what changed
in this release?". This inspects a clone and reports the evidence you'd
otherwise dig out by hand:

  - branches (local and remote), with each one's merge-base against HEAD and
    how many commits separate them -> the usual source of a baseline
  - any tags, if some exist after all
  - commit volume per month -> shows where release boundaries probably fall
  - commits whose message looks like a version bump or release marker
  - top-level directories by commit count -> tells you which subsystems are
    active, which feeds the Part A / Part B split and area_rules.yaml

It only reads; it changes nothing. Run it, look at the output, then set
from_ref/to_ref in repos.yaml yourself.

Usage:
  python3 suggest_baseline.py ~/workspace/aq20_linux_318
  python3 suggest_baseline.py ~/workspace/aq20_linux_318 --months 18 --top-dirs 25
"""
import argparse
import os
import re
import subprocess
import sys
from collections import Counter

VERSION_HINT = re.compile(
    r"(v?\d+\.\d+(\.\d+)*)|(\brelease\b)|(\bbump\b)|(\btag\b)|(\bRC\d+\b)|(\bversion\b)",
    re.I,
)


def git(path, *args):
    p = subprocess.run(["git", "-C", path, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.rstrip("\n") if p.returncode == 0 else ""


def head(path, n=8):
    return "=" * n


def section(title):
    print(f"\n{title}\n{'-' * len(title)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", help="Path to the git clone")
    ap.add_argument("--months", type=int, default=12, help="How many months of history to chart")
    ap.add_argument("--top-dirs", type=int, default=15, help="How many top-level dirs to list")
    ap.add_argument("--depth", type=int, default=2, help="Directory depth for the activity list")
    args = ap.parse_args()

    repo = os.path.expanduser(args.repo)
    if git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        sys.exit(f"error: not a git repository: {repo}")

    cur = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    total = git(repo, "rev-list", "--count", "HEAD")
    first_date = git(repo, "log", "--reverse", "--format=%as", "--max-parents=0") .split("\n")[0]
    last_date = git(repo, "log", "-1", "--format=%as")

    print(f"Repository : {os.path.abspath(repo)}")
    print(f"Remote     : {git(repo, 'config', '--get', 'remote.origin.url') or '(none)'}")
    print(f"HEAD       : {cur} @ {git(repo, 'rev-parse', '--short', 'HEAD')}")
    print(f"History    : {total} commits, {first_date or '?'} -> {last_date}")

    # ---- tags -------------------------------------------------------------
    tags = [t for t in git(repo, "tag", "--sort=-creatordate").split("\n") if t]
    section("Tags")
    if tags:
        for t in tags[:20]:
            d = git(repo, "log", "-1", "--format=%as", t)
            ahead = git(repo, "rev-list", "--count", f"{t}..HEAD")
            print(f"  {t:<32} {d}   {ahead} commits behind HEAD")
        print("\n  -> Use the newest tag that marks the PREVIOUS release as from_ref.")
    else:
        print("  (none)")
        print("  -> No tags, so the baseline has to come from a branch, a date")
        print("     window, or a specific commit. See the sections below.")

    # ---- branches ---------------------------------------------------------
    section("Branches (merge-base vs HEAD)")
    refs = git(repo, "for-each-ref", "--format=%(refname:short)|%(committerdate:short)",
               "refs/heads", "refs/remotes")
    rows = []
    for line in refs.split("\n"):
        if not line or "|" not in line:
            continue
        name, date = line.split("|", 1)
        if name.endswith("/HEAD"):
            continue
        if name == cur:
            continue
        base = git(repo, "merge-base", "HEAD", name)
        if not base:
            continue
        ahead = git(repo, "rev-list", "--count", f"{name}..HEAD")   # on HEAD, not on name
        behind = git(repo, "rev-list", "--count", f"HEAD..{name}")   # on name, not on HEAD
        rows.append((name, date, ahead, behind, base[:9]))

    if rows:
        print(f"  {'branch':<40} {'last commit':<12} {'HEAD ahead':>10} {'behind':>7}  merge-base")
        for name, date, ahead, behind, base in sorted(rows, key=lambda r: -int(r[2] or 0)):
            print(f"  {name:<40} {date:<12} {ahead:>10} {behind:>7}  {base}")
        print("\n  -> 'HEAD ahead' is how many commits this release would contain if you")
        print("     used that branch as from_ref.")
        print("  -> Watch for STALE mainline branches. A branch called 'master' that")
        print("     stopped moving a year ago is not the baseline just because it is")
        print("     called master — check the 'last commit' column, not the name.")
    else:
        print("  (no other branches)")

    # ---- commit volume per month -----------------------------------------
    section(f"Commit volume (last {args.months} months)")
    dates = [d for d in git(repo, "log", "--format=%as").split("\n") if d]
    months = Counter(d[:7] for d in dates)
    recent = sorted(months.items(), reverse=True)[:args.months]
    if recent:
        peak = max(c for _, c in recent)
        for m, c in recent:
            bar = "#" * max(1, round(c / peak * 40))
            print(f"  {m}  {c:>4}  {bar}")
        print("\n  -> Gaps or sudden bursts often mark release boundaries.")

    # ---- release-looking commits -----------------------------------------
    section("Commits that look like version/release markers")
    log = git(repo, "log", "--format=%h|%as|%s")
    hits = []
    for line in log.split("\n"):
        parts = line.split("|", 2)
        if len(parts) == 3 and VERSION_HINT.search(parts[2]):
            hits.append(parts)
    if hits:
        print(f"  {'commit':<11} {'date':<12} {'commits to HEAD':>15}  subject")
        for h, d, s in hits[:25]:
            ahead = git(repo, "rev-list", "--count", f"{h}..HEAD")
            print(f"  {h:<11} {d:<12} {ahead:>15}  {s[:76]}")
        print(f"\n  ({len(hits)} matched in total)")
        print("  -> If one of these is the last release, use its hash as from_ref;")
        print("     'commits to HEAD' is how big the release note would then be.")
    else:
        print("  (none found)")

    # ---- directory activity ----------------------------------------------
    section(f"Most active directories (depth {args.depth})")
    files = git(repo, "log", "--name-only", "--format=").split("\n")
    dirs = Counter()
    for f in files:
        f = f.strip()
        if not f:
            continue
        d = os.path.dirname(f)
        dirs["/".join(d.split("/")[:args.depth]) if d else "(root)"] += 1
    for d, c in dirs.most_common(args.top_dirs):
        print(f"  {c:>6}  {d}")
    print("\n  -> These become the Area column. Map them to readable labels in")
    print("     config/area_rules.yaml, and use them to decide what belongs in")
    print("     Part A vs Part B of the release note.")

    section("Suggested next step")
    if tags:
        print(f"  from_ref: {tags[0]}      # newest tag")
    else:
        # Pick the mainline branch by RECENCY, not by how far ahead HEAD is.
        # A long-abandoned 'master' shows a huge ahead-count precisely because
        # it is dead, which makes ahead-count exactly the wrong signal.
        mainline = [r for r in rows if re.search(r"(^|/)(master|main|release|develop)$", r[0])]
        if mainline:
            by_date = sorted(mainline, key=lambda r: r[1], reverse=True)
            best = by_date[0]
            print(f"  from_ref: {best[0]}      # most recent mainline "
                  f"({best[1]}), HEAD is {best[2]} ahead")
            stale = [r for r in by_date[1:] if r[1] < best[1]]
            if stale:
                names = ", ".join(f"{r[0]} ({r[1]}, {r[2]} ahead)" for r in stale[:4])
                print(f"  # ignoring staler mainline branches: {names}")
            if hits:
                print(f"  #")
                print(f"  # But a release-marker commit is usually the better baseline than a")
                print(f"  # branch head. Most recent one found:")
                h, d, s = hits[0]
                ahead = git(repo, "rev-list", "--count", f"{h}..HEAD")
                print(f"  #   {h}  {d}  {s[:70]}   ({ahead} commits to HEAD)")
        else:
            print("  from_ref: <pick a commit hash from the sections above>")
            print("  # or drop from_ref entirely and set  since_days: 90")
    print(f"  to_ref:   {cur}")


if __name__ == "__main__":
    main()
