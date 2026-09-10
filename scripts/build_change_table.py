#!/usr/bin/env python3
"""
build_change_table.py — Turn the raw per-repo commit JSON from fetch_all.py
into the "Commit | Area | Change" tables used in the release note (see
Section 2 "Android SDK change set" / Section 3 "Chipcode change set" of the
CQS290 reference).

What it automates:
  - Area: the common directory prefix of the files each commit touched
    (e.g. "vendor/camera", "msm-kernel/power"), depth controlled by --depth.
    You can override/relabel any area via config/area_rules.example.yaml
    (regex on filepath -> human label, e.g. "vendor/cavli/.*ota.*" -> "vendor/cavli / OTA").
  - Change: the commit subject line, PR-suffix stripped, capitalized.
  - Grouping by repo/part (A = Android SDK/HLOS, B = Chipcode/firmware),
    matching the reference doc's two-domain split.

What it does NOT automate (by design — this needs engineering judgement,
same as the reference doc's prose):
  - Deciding which commits are release-note-worthy vs. noise (baseline syncs,
    formatting-only commits, revert-of-revert, etc.) — everything is included;
    trim the output before rendering.
  - Writing the explanatory prose under each numbered subsection (2.1, 2.2, ...).
  - Merging multiple related commits into one narrative bullet.

Output: a single YAML file (change_table.yaml) that render_release_note.py
consumes, plus a human-readable Markdown preview (change_table.preview.md)
for quick review/editing before you touch the real config.

Usage:
  python3 build_change_table.py --in-dir out/ --out out/change_table.yaml \
      --area-rules config/area_rules.example.yaml --depth 2
"""
import argparse
import glob
import json
import os
import re

import yaml


def load_area_rules(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        rules = yaml.safe_load(f) or []
    compiled = []
    for r in rules:
        compiled.append((re.compile(r["pattern"]), r["area"]))
    return compiled


def auto_area(files, depth):
    """Best-guess Area label: the shared directory prefix of the touched files.

    The filename itself is always dropped — a commit touching only
    `tools/flash.py` is in area `tools`, not `tools/flash.py`.
    """
    if not files:
        return "(unclassified)"
    prefixes = []
    for fp in files:
        directory = os.path.dirname(fp)
        if not directory:
            prefixes.append("(root)")
            continue
        parts = directory.split("/")
        prefixes.append("/".join(parts[:depth]))
    # majority vote; ties broken by shortest/most common prefix
    counts = {}
    for p in prefixes:
        counts[p] = counts.get(p, 0) + 1
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return best


# "atcop:", "boot(rf):", "fix!:" — a conventional-commit scope prefix, which
# must keep its lowercase form rather than being sentence-cased into "Atcop:".
CONVENTIONAL_PREFIX_RE = re.compile(r"^[a-z0-9_.\-/]+(\([^)]*\))?!?:\s")


def clean_subject(subject):
    subject = re.sub(r"\s*\(#\d+\)\s*$", "", subject).strip()
    if subject and subject[0].islower() and not CONVENTIONAL_PREFIX_RE.match(subject):
        subject = subject[0].upper() + subject[1:]
    return subject


def classify_area(files, rules, depth):
    for fp in files:
        for pattern, label in rules:
            if pattern.search(fp):
                return label
    return auto_area(files, depth)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", required=True, help="Directory of *.json produced by fetch_all.py / fetch_commits.py")
    ap.add_argument("--out", required=True, help="Output change_table.yaml path")
    ap.add_argument("--area-rules", default=None, help="Optional YAML: [{pattern: regex, area: label}, ...]")
    ap.add_argument("--depth", type=int, default=2, help="Path-prefix depth for auto area labels (default 2)")
    args = ap.parse_args()

    rules = load_area_rules(args.area_rules)
    files = sorted(glob.glob(os.path.join(args.in_dir, "*.json")))
    if not files:
        raise SystemExit(f"no *.json files found in {args.in_dir}")

    change_table = {"repos": []}
    for fp in files:
        with open(fp) as f:
            data = json.load(f)
        repo_entry = {
            "name": os.path.splitext(os.path.basename(fp))[0],
            "repo": data["repo"],
            "path": data.get("path"),
            "from_ref": data.get("from_ref"),
            "to_ref": data.get("to_ref"),
            "commits": [],
        }
        for c in data["commits"]:
            if c.get("is_merge_commit") and not c.get("files"):
                continue  # pure merge commits carry no diff of their own
            area = classify_area(c.get("files", []), rules, args.depth)
            repo_entry["commits"].append({
                "commit": c["short_sha"],
                "area": area,
                "change": clean_subject(c["message_subject"]),
                "pr_number": c.get("pr_number"),
                "files_sample": c.get("files", [])[:5],
            })
        change_table["repos"].append(repo_entry)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        yaml.safe_dump(change_table, f, sort_keys=False, width=100)

    preview_path = os.path.splitext(args.out)[0] + ".preview.md"
    with open(preview_path, "w") as f:
        for repo_entry in change_table["repos"]:
            f.write(f"\n### {repo_entry['name']} ({repo_entry['repo']}"
                     f"{'/' + repo_entry['path'] if repo_entry['path'] else ''})\n\n")
            f.write("| Commit | Area | Change |\n|---|---|---|\n")
            for row in repo_entry["commits"]:
                f.write(f"| `{row['commit']}` | {row['area']} | {row['change']} |\n")

    total = sum(len(r["commits"]) for r in change_table["repos"])
    print(f"wrote {args.out} and {preview_path} ({total} commits across {len(change_table['repos'])} repos)")


if __name__ == "__main__":
    main()
