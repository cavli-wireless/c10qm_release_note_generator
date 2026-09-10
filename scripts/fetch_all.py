#!/usr/bin/env python3
"""
fetch_all.py — Run fetch_commits.py across every repo listed in a repos.yaml
file, and write a subsystem snapshot table (repo, path, from/to ref, resolved
SHA, commit count) alongside the per-repo commit JSON.

This is the entry point for "generate a release note from a list of
repositories" — point it at a repos.yaml like config/repos.example.yaml and
it produces everything the later steps (build_change_table.py,
render_release_note.py) need.

Usage:
  python3 fetch_all.py --repos-file config/repos.example.yaml --out-dir out/
"""
import argparse
import os
import subprocess
import sys

import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_commits import API_ROOT, session_for, get_token, api_get, die  # noqa: E402


def resolve_ref_sha(session, owner, repo, ref):
    if not ref:
        return None
    resp = api_get(session, f"{API_ROOT}/repos/{owner}/{repo}/commits/{ref}", allow_404=True)
    if resp is None:
        return None
    return resp.json()["sha"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-file", required=True, help="YAML file listing repos (see config/repos.example.yaml)")
    ap.add_argument("--out-dir", required=True, help="Directory to write per-repo JSON + snapshot.md into")
    ap.add_argument("--token", default=None)
    ap.add_argument("--no-files", action="store_true", help="Skip per-commit file fetch (faster, but breaks area auto-categorization)")
    ap.add_argument("--no-prs", action="store_true", help="Skip PR metadata resolution")
    args = ap.parse_args()

    with open(args.repos_file) as f:
        cfg = yaml.safe_load(f)

    repos = cfg.get("repos", [])
    if not repos:
        die("repos.yaml has no 'repos:' entries")

    os.makedirs(args.out_dir, exist_ok=True)
    token = get_token(args.token)
    session = session_for(token)

    snapshot_rows = []
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_commits.py")

    for entry in repos:
        name = entry["name"]
        repo = entry["repo"]
        owner, short = repo.split("/", 1)
        path = entry.get("path")
        from_ref = entry.get("from_ref")
        to_ref = entry.get("to_ref") or entry.get("branch")
        since_days = entry.get("since_days")

        out_json = os.path.join(args.out_dir, f"{name}.json")
        cmd = [sys.executable, script, "--repo", repo, "--to-ref", to_ref, "--out", out_json]
        if path:
            cmd += ["--path", path]
        if from_ref:
            cmd += ["--from-ref", from_ref]
        if since_days:
            cmd += ["--since-days", str(since_days)]
        if args.no_files:
            cmd += ["--no-files"]
        if args.no_prs:
            cmd += ["--no-prs"]
        if token:
            cmd += ["--token", token]

        print(f"== {name} ({repo}) ==", file=sys.stderr)
        subprocess.run(cmd, check=True)

        from_sha = resolve_ref_sha(session, owner, short, from_ref) if from_ref else None
        to_sha = resolve_ref_sha(session, owner, short, to_ref)
        import json
        with open(out_json) as f:
            data = json.load(f)
        snapshot_rows.append({
            "name": name,
            "repo": repo,
            "path": path or "",
            "from_ref": from_ref or "(none)",
            "from_sha": (from_sha or "")[:12],
            "to_ref": to_ref,
            "to_sha": (to_sha or "")[:12],
            "commit_count": len(data["commits"]),
            "pr_count": len(data["pull_requests"]),
            "part": entry.get("part", ""),
        })

    snap_path = os.path.join(args.out_dir, "snapshot.md")
    with open(snap_path, "w") as f:
        f.write("| Subsystem | Repo | Path | From | From SHA | To | To SHA | Commits | PRs |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in snapshot_rows:
            f.write(f"| {r['name']} | {r['repo']} | {r['path']} | {r['from_ref']} | `{r['from_sha']}` "
                    f"| {r['to_ref']} | `{r['to_sha']}` | {r['commit_count']} | {r['pr_count']} |\n")
    print(f"\nwrote {snap_path}", file=sys.stderr)
    print(f"per-repo commit JSON in {args.out_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
