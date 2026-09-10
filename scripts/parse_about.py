#!/usr/bin/env python3
"""
parse_about.py — Extract per-subsystem Build IDs from the AQ20 `about.html`,
and diff them between two refs to build Appendix A.

Why read it from git rather than from the working tree: `about.html` is
committed, so the build IDs at the previous release and at this one are both
recoverable (`git show <ref>:<path>`). That turns Appendix A into a real
Previous/This comparison — the same shape as the CQS290 reference — instead of
a snapshot of whatever happens to be checked out right now.

Extraction is deliberately tolerant, because "about page" markup varies:

  1. <table> rows            -> first cell = subsystem, last = build ID
  2. <dt>/<dd> pairs
  3. "Label: VALUE" lines in any text node
  4. JS/JSON assignments     var mpss = "MPSS.JO..."  /  "mpss": "MPSS.JO..."

Everything found is reported. Use --dump to see exactly what was extracted
before wiring it into a document, and --filter to keep only rows whose value
looks like a build ID.

Usage:
  # what does it find?
  python3 parse_about.py --repo ~/workspace/aq20_linux_318 \
      --path about.html --ref origin/main --dump

  # Appendix A comparison rows
  python3 parse_about.py --repo ~/workspace/aq20_linux_318 --path about.html \
      --from-ref 7604bfe62 --to-ref origin/main --out out/build_ids.yaml

  # or a plain file, no git involved
  python3 parse_about.py --file /path/to/about.html --dump

No third-party dependency: uses html.parser from the standard library, so this
adds nothing to install.
"""
import argparse
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

import yaml

# A value that looks like a firmware build ID: dotted component names with
# digits, e.g. MPSS.JO.4.0.2-00170-9607_GENNS_PACK-1, or a plain semver.
BUILD_ID_RE = re.compile(
    r"(?:[A-Z][A-Z0-9_]*\.){1,}[A-Za-z0-9._\-]*\d[A-Za-z0-9._\-]*"   # QC style
    r"|\bv?\d+\.\d+\.\d+[A-Za-z0-9._\-]*\b"                           # semver
)
LABEL_VALUE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ._/&+()-]{1,40}?)\s*[:=]\s*(\S.*?)\s*$")
JS_ASSIGN_RE = re.compile(
    r"""(?:var\s+|let\s+|const\s+|["'])([A-Za-z_][A-Za-z0-9_ .-]{0,40})["']?\s*[:=]\s*["']([^"']{2,120})["']"""
)


class AboutParser(HTMLParser):
    """Collect table rows, definition lists, script bodies and loose text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._row, self._cell = [], None, None
        self._row_is_header = False
        self.dts, self.dds, self._dt, self._dd = [], [], None, None
        self.texts, self.scripts = [], []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
            self._row_is_header = False
        elif tag in ("td", "th"):
            self._cell = []
            if tag == "th":
                self._row_is_header = True
        elif tag == "dt":
            self._dt = []
        elif tag == "dd":
            self._dd = []
        elif tag == "script":
            self._in_script = True
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "tr" and self._row is not None:
            # A <th> row is the table's own header ("Component | Version"),
            # not a subsystem. Including it would show up as a bogus image
            # named "Component" that appears and disappears between releases.
            if self._row and not self._row_is_header:
                self.rows.append(self._row)
            self._row = None
            self._row_is_header = False
        elif tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "dt" and self._dt is not None:
            self.dts.append(" ".join("".join(self._dt).split()))
            self._dt = None
        elif tag == "dd" and self._dd is not None:
            self.dds.append(" ".join("".join(self._dd).split()))
            self._dd = None
        elif tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts.append(data)
            return
        for sink in (self._cell, self._dt, self._dd):
            if sink is not None:
                sink.append(data)
                return
        text = data.strip()
        if text:
            self.texts.append(text)


def extract(html):
    """Return [(label, value, how)] with duplicates removed, order preserved."""
    p = AboutParser()
    p.feed(html)
    found, seen = [], set()

    def add(label, value, how):
        label = " ".join(str(label).split()).strip(" :=")
        value = " ".join(str(value).split()).strip()
        if not label or not value or len(value) > 200:
            return
        if label.lower() == value.lower():
            return
        key = label.lower()
        if key in seen:
            return
        seen.add(key)
        found.append((label, value, how))

    for row in p.rows:                       # 1. table rows
        cells = [c for c in row if c]
        if len(cells) >= 2:
            add(cells[0], cells[-1], "table")

    for dt, dd in zip(p.dts, p.dds):         # 2. definition lists
        add(dt, dd, "dl")

    for text in p.texts:                     # 3. "Label: VALUE"
        for line in text.splitlines():
            m = LABEL_VALUE_RE.match(line)
            if m:
                add(m.group(1), m.group(2), "text")

    for script in p.scripts:                 # 4. JS / JSON assignments
        for m in JS_ASSIGN_RE.finditer(script):
            add(m.group(1), m.group(2), "script")

    return found


def looks_like_build_id(value):
    return bool(BUILD_ID_RE.search(value))


def git_show(repo, ref, path):
    proc = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return None
    return proc.stdout


def find_about(repo, path=None):
    """Locate about.html in the working tree if no explicit path is given."""
    if path:
        return path
    proc = subprocess.run(["git", "-C", repo, "ls-files", "*about.html"],
                          capture_output=True, text=True)
    hits = [l for l in proc.stdout.splitlines() if l.strip()]
    if not hits:
        return None
    hits.sort(key=len)
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="Path to the clone containing about.html")
    ap.add_argument("--path", help="Repo-relative path to about.html (auto-located if omitted)")
    ap.add_argument("--file", help="Parse a plain file instead of reading from git")
    ap.add_argument("--ref", help="Single ref to read (implies a snapshot, not a comparison)")
    ap.add_argument("--from-ref", help="Previous release ref")
    ap.add_argument("--to-ref", help="This release ref")
    ap.add_argument("--dump", action="store_true", help="Print everything extracted and exit")
    ap.add_argument("--filter", action="store_true",
                    help="Keep only rows whose value looks like a build ID")
    ap.add_argument("--out", help="Write Appendix rows as YAML here")
    args = ap.parse_args()

    def load(ref):
        if args.file:
            with open(args.file, encoding="utf-8", errors="replace") as f:
                return f.read()
        if not args.repo:
            sys.exit("error: need --file, or --repo with a ref")
        path = find_about(args.repo, args.path)
        if not path:
            sys.exit(f"error: no about.html found in {args.repo}.\n"
                     f"       Locate it with:  git -C {args.repo} ls-files '*about*'\n"
                     f"       then pass it with --path")
        html = git_show(args.repo, ref, path)
        if html is None:
            sys.exit(f"error: '{path}' does not exist at ref '{ref}' in {args.repo}")
        return html

    if args.dump:
        ref = args.ref or args.to_ref or "HEAD"
        pairs = extract(load(ref))
        if not pairs:
            sys.exit("error: nothing extracted — the markup is a shape this parser does not\n"
                     "       know. Send the file (or an excerpt) so the parser can be tuned.")
        print(f"{len(pairs)} field(s) extracted"
              + ("" if args.file else f" from {find_about(args.repo, args.path)} at {ref}") + ":\n")
        print(f"  {'source':<8} {'looks like':<11} {'label':<34} value")
        for label, value, how in pairs:
            flag = "build id" if looks_like_build_id(value) else "-"
            print(f"  {how:<8} {flag:<11} {label[:33]:<34} {value[:60]}")
        print("\nUse --filter to keep only the build-id rows.")
        return

    # --- comparison mode -------------------------------------------------
    if not (args.from_ref and args.to_ref):
        sys.exit("error: need --from-ref and --to-ref (or --dump to inspect)")

    prev_pairs = extract(load(args.from_ref))
    curr_pairs = extract(load(args.to_ref))
    if args.filter:
        # Filter BOTH sides, or a row dropped from the new file reappears as a
        # spurious "Removed in this release".
        prev_pairs = [(l, v, h) for l, v, h in prev_pairs if looks_like_build_id(v)]
        curr_pairs = [(l, v, h) for l, v, h in curr_pairs if looks_like_build_id(v)]
    prev = dict((l, v) for l, v, _ in prev_pairs)

    rows, changed = [], 0
    for label, value, _ in curr_pairs:
        before = prev.get(label)
        if before is None:
            note, changed = "New in this release", changed + 1
            before = "–"
        elif before != value:
            note, changed = "Updated", changed + 1
        else:
            note = "Unchanged"
        rows.append([label, f"`{before}`", f"`{value}`", note])

    for label, value in prev.items():                 # dropped subsystems
        if not any(r[0] == label for r in rows):
            rows.append([label, f"`{value}`", "–", "Removed in this release"])
            changed += 1

    out = {"appendix_build_ids": {
        "headers": ["Software Image", "Previous Build ID", "This Build ID", "Note"],
        "rows": rows}}

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(f"# Generated by parse_about.py from {find_about(args.repo, args.path)}\n"
                    f"# {args.from_ref} -> {args.to_ref}\n\n")
            yaml.safe_dump(out, f, sort_keys=False, width=120, allow_unicode=True)
        print(f"wrote {args.out}")
    else:
        print(yaml.safe_dump(out, sort_keys=False, width=120, allow_unicode=True))

    print(f"  {len(rows)} subsystem(s), {changed} changed", file=sys.stderr)
    if not rows:
        print("  WARNING: no build IDs extracted — run with --dump to see what the file "
              "actually contains.", file=sys.stderr)


if __name__ == "__main__":
    main()
