#!/usr/bin/env python3
"""
fetch_local.py — Read commits straight out of local git clones, with no GitHub
API access and no token required.

This is the offline twin of fetch_commits.py / fetch_all.py: it produces the
*same* JSON schema, so build_change_table.py and render_release_note.py work
downstream without any changes. Use it when:

  - the repos are private and you'd rather not mint a token,
  - you're on a machine that can't reach github.com,
  - or you simply already have the trees checked out (the usual case for
    firmware work — AQ20/modem_proc, cavli_linux_services, cavli_sdk_tools_linux
    are typically sitting on disk already).

The one thing it can't recover is pull-request metadata (title/author/labels
live on GitHub, not in the clone). PR *numbers* are still picked up when they
appear in commit subjects, which is enough for the change tables.

Usage:
  # every repo listed in a repos.yaml that has `local_path:` set
  python3 fetch_local.py --repos-file config/aq20/repos.yaml --out-dir out/

  # or a single repo, ad hoc
  python3 fetch_local.py --repo-path /src/AQ20 --name AQ20_modem_proc \
      --from-ref AQ20_v1.0.0 --to-ref master --out out/AQ20_modem_proc.json

Make sure the clones are up to date first (`git fetch --all --tags`), otherwise
you'll diff against a stale baseline.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import yaml

RS = "\x1e"   # record separator between commits
FS = "\x1f"   # field separator within a commit header
PR_SUBJECT_RE = re.compile(r"\(#(\d+)\)\s*$")
MERGE_PR_RE = re.compile(r"Merge pull request #(\d+) from")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def git(repo_path, *args, check=True):
    proc = subprocess.run(["git", "-C", repo_path, *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        die(f"git {' '.join(args)} failed in {repo_path}:\n{proc.stderr.strip()}")
    return proc.stdout


def ensure_repo(path):
    if not os.path.isdir(path):
        die(f"not a directory: {path}")
    out = subprocess.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                         capture_output=True, text=True)
    if out.returncode != 0 or out.stdout.strip() != "true":
        die(f"not a git repository: {path}")


def ref_exists(repo_path, ref):
    return subprocess.run(["git", "-C", repo_path, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                          capture_output=True).returncode == 0


def resolve_sha(repo_path, ref):
    if not ref or not ref_exists(repo_path, ref):
        return None
    return git(repo_path, "rev-parse", f"{ref}^{{commit}}").strip()


def resolve_date(repo_path, ref):
    """Author date of the commit a ref points at (YYYY-MM-DD).

    The document header dates the From/To baselines, and the From date can't be
    taken from the commits in range — the baseline commit is by definition
    outside that range.
    """
    if not ref or not ref_exists(repo_path, ref):
        return None
    return git(repo_path, "log", "-1", "--format=%as", f"{ref}^{{commit}}").strip() or None


def extract_pr_number(subject, is_merge):
    m = PR_SUBJECT_RE.search(subject)
    if m:
        return int(m.group(1))
    if is_merge:
        m2 = MERGE_PR_RE.search(subject)
        if m2:
            return int(m2.group(1))
    return None


def collect(repo_path, from_ref, to_ref, path=None, since_days=None):
    """Run git log and parse it into the fetch_commits.py record shape."""
    fmt = RS + FS.join(["%H", "%an", "%aI", "%P", "%s", "%b"]) + FS
    args = ["log", f"--pretty=format:{fmt}", "--name-only", "--date-order"]

    if since_days:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
        args += [f"--since={since}", to_ref]
        mode = "since_days"
    elif from_ref:
        args.append(f"{from_ref}..{to_ref}")
        mode = "compare"
    else:
        args.append(to_ref)
        mode = "full_history"

    if path:
        args += ["--", path]

    raw = git(repo_path, *args)
    commits = []
    for chunk in raw.split(RS):
        if not chunk.strip():
            continue
        parts = chunk.split(FS)
        if len(parts) < 6:
            continue
        sha, author, date, parents, subject, body = parts[:6]
        files = [ln.strip() for ln in parts[6].splitlines() if ln.strip()] if len(parts) > 6 else []
        parent_list = parents.split()
        is_merge = len(parent_list) > 1
        commits.append({
            "sha": sha,
            "short_sha": sha[:7],
            "author_name": author,
            "author_login": None,          # not knowable from a clone
            "date": date,
            "is_merge_commit": is_merge,
            "message_subject": subject.strip(),
            "message_body": body.strip(),
            "pr_number": extract_pr_number(subject.strip(), is_merge),
            "html_url": None,
            "files": files,
        })
    return commits, mode


def subsystem_snapshot(repo_path, subsystems, from_ref, to_ref):
    """For each configured subsystem path, record the commit it sits at.

    This is what lets the release note pin EVERY subsystem to a commit ID,
    including the ones that did not change — "no change, and here is the
    commit it's at" is a statement; a blank cell is not.

    Per subsystem we report:
      last_commit        the most recent commit touching that path, ever
      commits_in_range   how many commits in this release touched it
      changed            whether it moved in this release
    """
    out = []
    rng = f"{from_ref}..{to_ref}" if from_ref else to_ref

    def norm(s):
        p = (s.get("path") or s.get("name")) if isinstance(s, dict) else s
        return p.strip("/")

    all_paths = [norm(s) for s in subsystems or []]

    # A subsystem that is actually a nested git repo / submodule is a trap: the
    # parent repo records only a gitlink, so `git log -- <path>` shows the
    # pointer bumps and NONE of the real work inside. Left undetected, an
    # actively developed submodule renders as a confident "No change".
    def nested_repo_url(spath):
        # "." / "" is this repo's own root, not a submodule of itself.
        if spath in ("", "."):
            return None
        dotgit = os.path.join(repo_path, spath, ".git")
        if not os.path.exists(dotgit):
            return None
        url = subprocess.run(["git", "-C", os.path.join(repo_path, spath),
                              "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True).stdout.strip()
        return url or "(no remote)"

    for s in subsystems or []:
        if isinstance(s, dict):
            name = s.get("name") or s.get("path")
            spath = s.get("path") or s.get("name")
        else:
            name = spath = s
        spath_n = spath.strip("/")

        # A catch-all entry (e.g. "apps_proc" alongside "apps_proc/kernel") must
        # not report a child's commit as its own snapshot. Exclude every other
        # configured path nested inside this one, so the row describes exactly
        # what it claims to: the part of the tree nothing more specific covers.
        pathspec = [spath] + [f":(exclude){p}" for p in all_paths
                              if p != spath_n and p.startswith(spath_n + "/")]

        last = git(repo_path, "log", "-1", "--format=%h|%H|%as|%s", "--", *pathspec)
        short = full = date = subject = ""
        if last:
            parts = last.split("|", 3)
            if len(parts) == 4:
                short, full, date, subject = parts
        count = git(repo_path, "rev-list", "--count", rng, "--", *pathspec).strip() or "0"

        # Nothing matched. Two very different causes, and conflating them would
        # be misleading:
        #   - the path is a typo / no longer exists  -> real config error
        #   - it's a catch-all whose every commit belongs to a nested sibling
        #     -> the entry is simply redundant, not wrong
        missing = covered = False
        if not short:
            if len(pathspec) > 1 and git(repo_path, "log", "-1", "--format=%h", "--", spath):
                covered = True     # exists, but fully covered by its children
            else:
                missing = True
                print(f"    warning: subsystem path '{spath}' has no commits in "
                      f"{os.path.basename(repo_path)} — check repos.yaml", file=sys.stderr)
        sub_url = nested_repo_url(spath_n)
        if sub_url:
            print(f"    WARNING: '{spath}' is a nested git repo / submodule "
                  f"({sub_url}).\n"
                  f"             The parent repo only records a pointer to it, so its own\n"
                  f"             commits are INVISIBLE here and it will look unchanged.\n"
                  f"             Add it to repos.yaml as its own repo entry with\n"
                  f"             local_path: <clone>/{spath_n}", file=sys.stderr)

        out.append({
            "name": name,
            "path": spath,
            "part": (s.get("part") if isinstance(s, dict) else None),
            "is_nested_repo": bool(sub_url),
            "nested_repo_url": sub_url,
            "last_commit": short or "n/a",
            "last_commit_full": full,
            "last_commit_date": date,
            "last_commit_subject": subject,
            "commits_in_range": int(count),
            "changed": int(count) > 0,
            "path_missing": missing,
            "covered_by_children": covered,
        })
    return out


def fetch_one(name, repo_path, repo_slug, from_ref, to_ref, path, since_days, out_json,
              subsystems=None):
    ensure_repo(repo_path)

    for ref, label in ((from_ref, "from_ref"), (to_ref, "to_ref")):
        if ref and not ref_exists(repo_path, ref):
            die(f"{name}: {label} '{ref}' not found in {repo_path}.\n"
                f"       Run 'git -C \"{repo_path}\" fetch --all --tags' and check the name "
                f"(git tag -l / git branch -a).")

    commits, mode = collect(repo_path, from_ref, to_ref, path, since_days)
    result = {
        "repo": repo_slug or os.path.basename(os.path.abspath(repo_path)),
        "path": path,
        "from_ref": from_ref,
        "to_ref": to_ref,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "source": "local-git",
        "local_path": os.path.abspath(repo_path),
        "from_sha": resolve_sha(repo_path, from_ref),
        "to_sha": resolve_sha(repo_path, to_ref),
        "from_date": resolve_date(repo_path, from_ref),
        "to_date": resolve_date(repo_path, to_ref),
        "total_commits": len(commits),
        "commits": commits,
        "pull_requests": [],   # not available offline
        "subsystems": subsystem_snapshot(repo_path, subsystems, from_ref, to_ref),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    scope = f" under '{path}'" if path else ""
    print(f"  {name}: {len(commits)} commits{scope} -> {out_json}", file=sys.stderr)
    return result


def list_subsystems(repo_path, ref="HEAD"):
    """Print every top-level directory with the commit that last touched it,
    plus a ready-to-paste `subsystems:` block for repos.yaml.

    Use this instead of guessing directory names. Guessing produces two
    failure modes that both look fine in the rendered document: a path that
    doesn't exist (silently reads as "no change"), and pinning every subsystem
    to the repo HEAD (identical SHAs everywhere, which says nothing).
    """
    ensure_repo(repo_path)
    tree = git(repo_path, "ls-tree", "--name-only", "-d", ref)
    dirs = [d for d in tree.split("\n") if d.strip()]
    if not dirs:
        die(f"no directories found at {ref} in {repo_path}")

    print(f"Top-level directories at {ref} in {os.path.abspath(repo_path)}:\n")
    print(f"  {'directory':<28} {'last commit':<10} {'date':<12} subject")
    rows = []
    for d in dirs:
        last = git(repo_path, "log", "-1", "--format=%h|%as|%s", ref, "--", d)
        short = date = subject = ""
        if last:
            parts = last.split("|", 2)
            if len(parts) == 3:
                short, date, subject = parts
        print(f"  {d:<28} {short or 'n/a':<10} {date:<12} {subject[:52]}")
        rows.append((d, short))

    print("\nPaste into the repo's entry in repos.yaml (trim to the subsystems")
    print("your release note actually reports on):\n")
    print("    subsystems:")
    for d, _ in rows:
        print(f'      - {{name: "{d}", path: "{d}"}}')
    print("\nEach will then be pinned to ITS OWN last-touching commit, not the repo HEAD.")


def resolve_submodule_refs(entries):
    """Derive a submodule's From/To from the parent repo's gitlink.

    For a vendored repo, guessing a baseline from its own tags or branches is
    wrong: it is shared across products and its tags belong to whichever module
    cut them (cavli_linux_services' only tag is `cqm220_v1.0.4` — a cqm220
    release, meaningless for AQ20). The authoritative answer is already
    recorded: the parent pins an exact submodule commit at every ref, so
    `<parent from>:<path>` .. `<parent to>:<path>` IS the range this release
    actually integrates.

    Declare it in repos.yaml with `submodule_of: <parent entry name>`.
    Explicit from_ref/to_ref on the entry still win.
    """
    by_name = {e["name"]: e for e in entries}
    for e in entries:
        parent_name = e.get("submodule_of")
        if not parent_name:
            continue
        parent = by_name.get(parent_name)
        if not parent:
            die(f"{e['name']}: submodule_of '{parent_name}' is not a repo entry "
                f"in this file")
        p_path = os.path.expanduser(os.path.expandvars(parent["local_path"]))
        c_path = os.path.expanduser(os.path.expandvars(e["local_path"]))
        rel = os.path.relpath(c_path, p_path).replace(os.sep, "/")
        if rel.startswith(".."):
            die(f"{e['name']}: local_path is not inside {parent_name}'s local_path")

        for key in ("from_ref", "to_ref"):
            if e.get(key):
                print(f"  {e['name']}: {key} set explicitly, not deriving from "
                      f"{parent_name}", file=sys.stderr)
                continue
            pref = parent.get(key) or parent.get("branch")
            if not pref:
                die(f"{e['name']}: cannot derive {key} — parent {parent_name} has no {key}")
            sha = git(p_path, "rev-parse", f"{pref}:{rel}", check=False).strip()
            if not sha or len(sha) < 40:
                if key == "from_ref":
                    # The submodule did not exist at the baseline: it is new in
                    # this release, so everything in it is a change.
                    print(f"  {e['name']}: not present at {parent_name} {pref} — treating "
                          f"as NEWLY ADDED in this release (full history)", file=sys.stderr)
                    e[key] = None
                    continue
                die(f"{e['name']}: could not read the submodule pointer at "
                    f"{pref}:{rel} in {parent_name}.\n"
                    f"       Is '{rel}' really a submodule of that repo at that ref?")
            e[key] = sha
            print(f"  {e['name']}: {key} = {sha[:12]}  "
                  f"(from {parent_name} {pref}:{rel})", file=sys.stderr)

        if e.get("from_ref") and e["from_ref"] == e["to_ref"]:
            print(f"  note: {e['name']} pointer did not move between "
                  f"{parent.get('from_ref')} and {parent.get('to_ref')} — this release "
                  f"integrates no changes from it", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-file", help="repos.yaml whose entries carry local_path:")
    ap.add_argument("--out-dir", help="Directory for per-repo JSON + snapshot.md")
    # single-repo mode
    ap.add_argument("--repo-path", help="Path to one local clone")
    ap.add_argument("--name", help="Subsystem name for single-repo mode")
    ap.add_argument("--repo", dest="repo_slug", default=None, help="owner/name, for display only")
    ap.add_argument("--path", default=None, help="Restrict to a subfolder")
    ap.add_argument("--from-ref", default=None)
    ap.add_argument("--to-ref", default=None)
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--out", help="Output JSON path (single-repo mode)")
    ap.add_argument("--list-subsystems", metavar="REPO_PATH", default=None,
                    help="List top-level dirs and the commit that last touched each, "
                         "then emit a ready-to-paste subsystems: block. Use this to build "
                         "repos.yaml from the repo instead of guessing paths.")
    args = ap.parse_args()

    if args.list_subsystems:
        list_subsystems(os.path.expanduser(args.list_subsystems),
                        args.to_ref or "HEAD")
        return

    if args.repo_path:
        if not (args.out and args.to_ref):
            die("single-repo mode needs --repo-path, --to-ref and --out")
        fetch_one(args.name or os.path.basename(args.repo_path.rstrip("/\\")),
                  args.repo_path, args.repo_slug, args.from_ref, args.to_ref,
                  args.path, args.since_days, args.out)
        return

    if not (args.repos_file and args.out_dir):
        die("need --repos-file and --out-dir (or single-repo mode: --repo-path/--to-ref/--out)")

    with open(args.repos_file, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    repos = cfg.get("repos", [])
    if not repos:
        die(f"{args.repos_file} has no 'repos:' entries")

    resolve_submodule_refs(repos)

    os.makedirs(args.out_dir, exist_ok=True)
    rows = []
    for entry in repos:
        local_path = entry.get("local_path")
        if not local_path:
            print(f"  skipping {entry.get('name')}: no local_path set", file=sys.stderr)
            continue
        local_path = os.path.expanduser(os.path.expandvars(local_path))
        name = entry["name"]
        res = fetch_one(
            name, local_path, entry.get("repo"),
            entry.get("from_ref"), entry.get("to_ref") or entry.get("branch"),
            entry.get("path"), entry.get("since_days"),
            os.path.join(args.out_dir, f"{name}.json"),
            subsystems=entry.get("subsystems"),
        )
        rows.append((entry, res))

    if not rows:
        die("no repos had local_path set — nothing fetched")

    snap = os.path.join(args.out_dir, "snapshot.md")
    with open(snap, "w", encoding="utf-8") as f:
        f.write("## Repo snapshot\n\n")
        f.write("| Subsystem | Repo | Path | From | From SHA | To | To SHA | Commits |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for entry, r in rows:
            f.write(f"| {entry['name']} | {r['repo']} | {r['path'] or ''} "
                    f"| {r['from_ref'] or '(none)'} | `{(r['from_sha'] or '')[:12]}` "
                    f"| {r['to_ref']} | `{(r['to_sha'] or '')[:12]}` | {r['total_commits']} |\n")

        # Per-subsystem snapshot: every subsystem gets a commit ID, changed or not.
        subs = [(e, s) for e, r in rows for s in r.get("subsystems") or []]
        if subs:
            f.write("\n## Subsystem snapshot\n\n")
            f.write("Every subsystem is pinned to a commit, whether or not it changed "
                    "in this release.\n\n")
            f.write("| Subsystem | Path | Commit | Date | Commits in range | Status |\n")
            f.write("|---|---|---|---|---|---|\n")
            for _e, s in subs:
                status = ("PATH NOT FOUND — check repos.yaml" if s.get("path_missing")
                          else "Changed" if s["changed"] else "No change")
                f.write(f"| {s['name']} | `{s['path']}` | `{s['last_commit']}` "
                        f"| {s['last_commit_date']} | {s['commits_in_range']} | {status} |\n")

            unchanged = [s for _e, s in subs
                         if not s["changed"] and not s.get("path_missing")]
            if unchanged:
                f.write("\n### Ready-made 'no change' rows\n\n")
                f.write("Paste into a Part's `change_table.rows:` in release_note.yaml — "
                        "each unchanged subsystem still carries its commit ID.\n\n")
                f.write("```yaml\n    rows:\n")
                for s in unchanged:
                    f.write(f'      - ["`{s["last_commit"]}`", "{s["name"]}", '
                            f'"No changes on this release"]\n')
                f.write("```\n")
    print(f"\nwrote {snap}", file=sys.stderr)


if __name__ == "__main__":
    main()
