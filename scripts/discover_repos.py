#!/usr/bin/env python3
"""
discover_repos.py — Walk a workspace directory, find every git repo inside it,
and print a ready-to-edit repos.yaml.

Firmware workspaces (a `repo`-tool checkout, or just a folder where several
clones sit side by side) usually hold many git repos at once. Rather than
hand-writing the repo list, point this at the workspace root and it reports,
per repo: its remote URL, current branch, the most recent tags, and how many
commits sit on the branch — everything you need to choose a From/To baseline.

Usage:
  # look around
  python3 discover_repos.py /home/thodo/workspace/aq20_linux_318

  # write a starter repos.yaml
  python3 discover_repos.py /home/thodo/workspace/aq20_linux_318 \
      --out config/aq20/repos.yaml --product AQ20

  # only the repos you care about
  python3 discover_repos.py ~/workspace/aq20_linux_318 \
      --filter modem_proc --filter cavli_linux_services --filter sdk_tools

Depth defaults to 3 levels, which covers both flat layouts and one level of
grouping. Bump --depth for a deep `repo`-tool manifest checkout.
"""
import argparse
import os
import subprocess
import sys

import yaml


def git(path, *args):
    p = subprocess.run(["git", "-C", path, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip() if p.returncode == 0 else ""


def find_repos(root, max_depth):
    """Yield directories that are git work trees, without descending into them."""
    root = os.path.abspath(root)
    found = []

    def walk(d, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except (PermissionError, FileNotFoundError):
            return
        if any(e.name == ".git" for e in entries):
            found.append(d)
            return                      # don't recurse into a repo's own subdirs
        for e in entries:
            if e.is_dir(follow_symlinks=False) and not e.name.startswith("."):
                walk(e.path, depth + 1)

    walk(root, 0)
    return found


def describe(path):
    remote = git(path, "config", "--get", "remote.origin.url")
    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(path, "rev-parse", "--short", "HEAD")
    count = git(path, "rev-list", "--count", "HEAD")
    tags = [t for t in git(path, "tag", "--sort=-creatordate").splitlines() if t][:8]
    last_date = git(path, "log", "-1", "--pretty=%as")
    slug = ""
    if remote:
        s = remote.rstrip("/")
        if s.endswith(".git"):
            s = s[:-4]
        parts = s.replace(":", "/").split("/")
        if len(parts) >= 2:
            slug = "/".join(parts[-2:])
    return {
        "path": path, "remote": remote, "slug": slug, "branch": branch,
        "head": head, "count": count, "tags": tags, "last_date": last_date,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="Workspace directory to scan")
    ap.add_argument("--depth", type=int, default=3, help="How deep to search (default 3)")
    ap.add_argument("--filter", action="append", default=[],
                    help="Only include repos whose path contains this substring (repeatable)")
    ap.add_argument("--out", default=None, help="Write a starter repos.yaml here")
    ap.add_argument("--product", default="PRODUCT", help="Product name for the yaml header")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        sys.exit(f"error: not a directory: {args.root}")

    repos = find_repos(args.root, args.depth)
    if args.filter:
        repos = [r for r in repos if any(f.lower() in r.lower() for f in args.filter)]
    if not repos:
        sys.exit(f"error: no git repositories found under {args.root} "
                 f"(depth {args.depth}) — try --depth 5")

    infos = [describe(r) for r in repos]

    print(f"Found {len(infos)} git repo(s) under {os.path.abspath(args.root)}:\n")
    for i in infos:
        rel = os.path.relpath(i["path"], args.root)
        if rel == ".":
            rel = f"{os.path.basename(os.path.abspath(args.root))}  (the root itself is the repo)"
        print(f"  {rel}")
        print(f"      remote : {i['remote'] or '(none)'}")
        print(f"      branch : {i['branch']}  @ {i['head']}   "
              f"({i['count']} commits, last {i['last_date']})")
        print(f"      tags   : {', '.join(i['tags']) if i['tags'] else '(no tags)'}")
        print()

    if args.out:
        entries = []
        for i in infos:
            name = os.path.basename(i["path"].rstrip("/"))
            entry = {
                "name": name,
                "repo": i["slug"] or name,
                "local_path": i["path"],
                "to_ref": i["branch"] if i["branch"] != "HEAD" else i["head"],
                "from_ref": i["tags"][0] if i["tags"] else "REPLACE_ME_previous_release_tag",
                "part": "A",
            }
            entries.append(entry)
        doc = {"product": args.product, "release_version": "REPLACE_ME", "repos": entries}
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(f"# Generated by discover_repos.py from {os.path.abspath(args.root)}\n"
                    "#\n"
                    "# Check each entry before running the fetch:\n"
                    "#   from_ref  - the PREVIOUS release baseline. discover_repos guessed the\n"
                    "#               newest tag; that is often right, but verify it.\n"
                    "#   to_ref    - this release. Usually the branch head shown above.\n"
                    "#   part      - A = Android SDK / HLOS side, B = chipcode / firmware.\n"
                    "#               Used only to help you sort changes into Section 2 vs 3.\n"
                    "#   path      - add this to scope a repo to one subfolder (e.g. atcm).\n"
                    "#   Delete any repo you don't want in the release note.\n\n")
            yaml.safe_dump(doc, f, sort_keys=False, width=100, allow_unicode=True)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
