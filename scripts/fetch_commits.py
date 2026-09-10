#!/usr/bin/env python3
"""
fetch_commits.py — Pull the commit log (and optionally the merged PRs) for one
GitHub repository between two refs, via the GitHub REST API.

Why the REST API instead of `git clone`:
  - Cavli's repos (AQ20/modem_proc, cavli_linux_services, cavli_sdk_tools_linux, ...)
    are large firmware/BSP trees. Cloning them fresh just to build a release note
    is slow and often blocked by corporate network policy.
  - The API gives us structured author/date/PR metadata for free, and works the
    same whether this runs in a cloud sandbox or on an engineer's laptop, as long
    as a GitHub token with read access to the org's repos is available.

Auth:
  Set one of GITHUB_TOKEN / GH_TOKEN in the environment, or pass --token.
  The token needs at least `repo` (read) scope for private Cavli repos.
  Classic PAT or fine-grained PAT both work; so does `gh auth token` output:
      export GITHUB_TOKEN=$(gh auth token)

Usage:
  python3 fetch_commits.py \
      --repo cavli-wireless/AQ20 \
      --from-ref AQ20_LA4.0 --to-ref master \
      --out out/AQ20.json

  # Scope to a subfolder (e.g. the atcm/ subsystem inside a monorepo-ish service repo)
  python3 fetch_commits.py \
      --repo cavli-wireless/cavli_linux_services --path atcm \
      --from-ref v1.2.0 --to-ref main \
      --out out/cavli_linux_services_atcm.json

  # A whole branch snapshot (no "from" tag exists yet) — last N days instead of a ref range
  python3 fetch_commits.py \
      --repo cavli-wireless/cavli_sdk_tools_linux --branch linux_3.18 \
      --since-days 90 \
      --out out/cavli_sdk_tools_linux.json

Output JSON schema: see README / SKILL.md "fetch_commits.py output" section.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

API_ROOT = "https://api.github.com"
PR_SUBJECT_RE = re.compile(r"\(#(\d+)\)\s*$")
MERGE_PR_RE = re.compile(r"Merge pull request #(\d+) from")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def get_token(cli_token):
    return cli_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def session_for(token):
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cavli-release-note-tools/1.0",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def api_get(session, url, params=None, allow_404=False):
    for attempt in range(3):
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            wait = 5
            if reset:
                wait = max(1, int(reset) - int(time.time()) + 1)
            print(f"  rate limited, waiting {wait}s...", file=sys.stderr)
            time.sleep(min(wait, 60))
            continue
        if resp.status_code == 404 and allow_404:
            return None
        if not resp.ok:
            die(f"GitHub API {resp.status_code} for {url}\n{resp.text[:500]}")
        return resp
    die(f"GitHub API kept rate-limiting for {url}")


def paginate(session, url, params=None):
    params = dict(params or {})
    params.setdefault("per_page", 100)
    items = []
    next_url, next_params = url, params
    while next_url:
        resp = api_get(session, next_url, next_params)
        data = resp.json()
        if isinstance(data, dict):
            # single-object endpoint, not a paginated list
            return data
        items.extend(data)
        next_url = resp.links.get("next", {}).get("url")
        next_params = None  # params are baked into the `next` link already
    return items


def extract_pr_number(subject, is_merge_commit):
    m = PR_SUBJECT_RE.search(subject)
    if m:
        return int(m.group(1))
    if is_merge_commit:
        m2 = MERGE_PR_RE.search(subject)
        if m2:
            return int(m2.group(1))
    return None


def fetch_commit_files(session, owner, repo, sha):
    resp = api_get(session, f"{API_ROOT}/repos/{owner}/{repo}/commits/{sha}")
    data = resp.json()
    return [f["filename"] for f in data.get("files", [])]


def commits_reachable(session, owner, repo, sha_or_branch, path=None, since=None, until=None, max_pages=None):
    """List commits reachable from a ref, optionally scoped to a path / date window."""
    params = {"sha": sha_or_branch}
    if path:
        params["path"] = path
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    url = f"{API_ROOT}/repos/{owner}/{repo}/commits"
    items = []
    page = 1
    while True:
        p = dict(params)
        p["per_page"] = 100
        p["page"] = page
        resp = api_get(session, url, p)
        batch = resp.json()
        if not batch:
            break
        items.extend(batch)
        if max_pages and page >= max_pages:
            break
        if len(batch) < 100:
            break
        page += 1
    return items


def build_commit_record(session, owner, repo, raw, with_files):
    sha = raw["sha"]
    commit = raw["commit"]
    message = commit["message"]
    subject, _, body = message.partition("\n")
    body = body.strip("\n")
    parents = raw.get("parents", [])
    is_merge = len(parents) > 1
    pr_number = extract_pr_number(subject.strip(), is_merge)
    author_login = (raw.get("author") or {}).get("login")
    record = {
        "sha": sha,
        "short_sha": sha[:7],
        "author_name": commit["author"]["name"],
        "author_login": author_login,
        "date": commit["author"]["date"],
        "is_merge_commit": is_merge,
        "message_subject": subject.strip(),
        "message_body": body,
        "pr_number": pr_number,
        "html_url": raw.get("html_url"),
        "files": [],
    }
    if with_files:
        record["files"] = fetch_commit_files(session, owner, repo, sha)
    return record


def fetch_pr(session, owner, repo, number):
    resp = api_get(session, f"{API_ROOT}/repos/{owner}/{repo}/pulls/{number}", allow_404=True)
    if resp is None:
        return None
    d = resp.json()
    return {
        "number": d["number"],
        "title": d["title"],
        "author": d["user"]["login"] if d.get("user") else None,
        "merged_at": d.get("merged_at"),
        "base": d["base"]["ref"],
        "html_url": d["html_url"],
        "labels": [l["name"] for l in d.get("labels", [])],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name, e.g. cavli-wireless/AQ20")
    ap.add_argument("--path", default=None, help="Restrict to commits touching this subfolder (e.g. atcm)")
    ap.add_argument("--from-ref", default=None, help="Base ref/tag/sha (release note 'From' baseline)")
    ap.add_argument("--to-ref", default=None, help="Head ref/tag/sha/branch (release note 'To' baseline)")
    ap.add_argument("--branch", default=None, help="Shorthand: use as --to-ref when --to-ref not given")
    ap.add_argument("--since-days", type=int, default=None,
                     help="Alternative to --from-ref: only commits in the last N days on --to-ref")
    ap.add_argument("--with-files", dest="with_files", action="store_true", default=True,
                     help="Fetch changed-file list per commit (default on; needed for area categorization)")
    ap.add_argument("--no-files", dest="with_files", action="store_false")
    ap.add_argument("--include-prs", action="store_true", default=True,
                     help="Resolve PR numbers found in commit subjects to full PR metadata (default on)")
    ap.add_argument("--no-prs", dest="include_prs", action="store_false")
    ap.add_argument("--token", default=None, help="GitHub token (else $GITHUB_TOKEN / $GH_TOKEN)")
    ap.add_argument("--out", required=True, help="Output JSON path")
    args = ap.parse_args()

    if "/" not in args.repo:
        die("--repo must be OWNER/NAME")
    owner, repo = args.repo.split("/", 1)
    to_ref = args.to_ref or args.branch
    if not to_ref:
        die("--to-ref (or --branch) is required")

    token = get_token(args.token)
    if not token:
        print("warning: no GitHub token found (GITHUB_TOKEN/GH_TOKEN unset). "
              "Unauthenticated requests are capped at 60/hour and cannot see private repos.",
              file=sys.stderr)
    session = session_for(token)

    result = {
        "repo": args.repo,
        "path": args.path,
        "from_ref": args.from_ref,
        "to_ref": to_ref,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "mode": None,
        "commits": [],
        "pull_requests": [],
    }

    if args.from_ref and not args.since_days:
        # Preferred path: exact ref..ref comparison via the compare API.
        result["mode"] = "compare"
        cmp_url = f"{API_ROOT}/repos/{owner}/{repo}/compare/{quote(args.from_ref)}...{quote(to_ref)}"
        resp = api_get(session, cmp_url)
        cmp_data = resp.json()
        result["ahead_by"] = cmp_data.get("ahead_by")
        result["behind_by"] = cmp_data.get("behind_by")
        result["total_commits"] = cmp_data.get("total_commits")
        raw_commits = cmp_data.get("commits", [])
        if args.path:
            # compare API doesn't support path filtering; cross-reference against
            # the path-scoped commit list reachable from to_ref.
            scoped = {c["sha"] for c in commits_reachable(session, owner, repo, to_ref, path=args.path)}
            raw_commits = [c for c in raw_commits if c["sha"] in scoped]
    else:
        # Fallback: date-windowed commit list on a single ref (no baseline tag yet).
        result["mode"] = "since_days"
        since_days = args.since_days or 90
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_commits = commits_reachable(session, owner, repo, to_ref, path=args.path, since=since)

    print(f"  {args.repo}: {len(raw_commits)} commits" + (f" under '{args.path}'" if args.path else ""),
          file=sys.stderr)

    pr_numbers = set()
    for i, raw in enumerate(raw_commits, 1):
        rec = build_commit_record(session, owner, repo, raw, args.with_files)
        result["commits"].append(rec)
        if rec["pr_number"]:
            pr_numbers.add(rec["pr_number"])
        if args.with_files and i % 25 == 0:
            print(f"    ...{i}/{len(raw_commits)} commits fetched", file=sys.stderr)

    if args.include_prs and pr_numbers:
        for n in sorted(pr_numbers):
            pr = fetch_pr(session, owner, repo, n)
            if pr:
                result["pull_requests"].append(pr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  wrote {args.out} ({len(result['commits'])} commits, {len(result['pull_requests'])} PRs)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
