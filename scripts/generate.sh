#!/usr/bin/env bash
# generate.sh — run the whole release-note pipeline from local git clones.
#
#   fetch_local.py  ->  build_change_table.py  ->  render_release_note.py
#
# Usage:
#   ./generate.sh <repos.yaml> <out-dir> [release_note.yaml]
#
# Example:
#   ./generate.sh config/aq20/repos.yaml out/
#       -> out/*.json, out/snapshot.md, out/change_table.yaml,
#          out/change_table.preview.md
#          then STOPS and tells you to curate the change table.
#
#   ./generate.sh config/aq20/repos.yaml out/ config/aq20/release_note.yaml
#       -> also renders out/RELEASE_NOTE.{md,html,pdf}
#
# The two-step split is deliberate: between the change table and the rendered
# document, a human decides which commits matter and writes the prose. Running
# straight through would just dump raw commit subjects into the document.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="${PYTHON:-python3}"

REPOS_FILE="${1:-}"
OUT_DIR="${2:-out}"
NOTE_YAML="${3:-}"

if [[ -z "$REPOS_FILE" ]]; then
  echo "usage: $0 <repos.yaml> <out-dir> [release_note.yaml]" >&2
  exit 2
fi
if [[ ! -f "$REPOS_FILE" ]]; then
  echo "error: no such file: $REPOS_FILE" >&2
  exit 2
fi

# Area rules, most specific first: next to the repos.yaml, then a project-wide
# override, then the shipped example.
AREA_RULES="$ROOT/config/area_rules.example.yaml"
[[ -f "$ROOT/config/area_rules.yaml" ]] && AREA_RULES="$ROOT/config/area_rules.yaml"
SIBLING_RULES="$(dirname "$REPOS_FILE")/area_rules.yaml"
[[ -f "$SIBLING_RULES" ]] && AREA_RULES="$SIBLING_RULES"
echo "    (area rules: $AREA_RULES)"

# Preflight: fail here with a clear fix rather than halfway through the run.
STAGE="table"; [[ -n "$NOTE_YAML" ]] && STAGE="all"
if ! "$PY" "$HERE/check_deps.py" --stage "$STAGE" >/tmp/rn_deps.$$ 2>&1; then
  cat /tmp/rn_deps.$$; rm -f /tmp/rn_deps.$$
  exit 1
fi
rm -f /tmp/rn_deps.$$

echo "==> 1/3  reading commits from local clones"
"$PY" "$HERE/fetch_local.py" --repos-file "$REPOS_FILE" --out-dir "$OUT_DIR"

echo
echo "==> 2/3  building change table"
"$PY" "$HERE/build_change_table.py" \
    --in-dir "$OUT_DIR" \
    --out "$OUT_DIR/change_table.yaml" \
    --area-rules "$AREA_RULES" \
    --depth 2

# Part A / Part B tables, with every configured subsystem present. Only runs
# when repos.yaml declares subsystems: — otherwise there is nothing to group by.
if grep -q '^[[:space:]]*subsystems:' "$REPOS_FILE"; then
  echo
  echo "==> 2b/3  building Part A / Part B tables"
  "$PY" "$HERE/build_parts.py" \
      --repos-file "$REPOS_FILE" \
      --in-dir "$OUT_DIR" \
      --out "$OUT_DIR/part_tables.yaml"
else
  echo
  echo "    (no 'subsystems:' in $REPOS_FILE — skipping Part A/B table generation."
  echo "     Add one with: $PY $HERE/fetch_local.py --list-subsystems <clone>)"
fi

if [[ -z "$NOTE_YAML" ]]; then
  cat <<EOF

==> done (stopping before render)

  Subsystem snapshot : $OUT_DIR/snapshot.md
  Change table       : $OUT_DIR/change_table.yaml
  Readable preview   : $OUT_DIR/change_table.preview.md
  Part A / B tables  : $OUT_DIR/part_tables.yaml  (+ .md to read)

Next: copy the starter release_note.yaml, paste the part_a/part_b blocks from
part_tables.yaml into it, fill in the metadata from snapshot.md, write the
per-subsystem prose, then re-run:

  $0 $REPOS_FILE $OUT_DIR <your-release_note.yaml>
EOF
  exit 0
fi

if [[ ! -f "$NOTE_YAML" ]]; then
  echo "error: no such file: $NOTE_YAML" >&2
  exit 2
fi

echo
echo "==> 3/3  rendering document"
"$PY" "$HERE/render_release_note.py" \
    --config "$NOTE_YAML" \
    --template-dir "$ROOT/templates" \
    --out-md "$OUT_DIR/RELEASE_NOTE.md" \
    --out-html "$OUT_DIR/RELEASE_NOTE.html" \
    --out-pdf "$OUT_DIR/RELEASE_NOTE.pdf"

echo
echo "==> done"
echo "  $OUT_DIR/RELEASE_NOTE.pdf   <- the deliverable (matches the reference format)"
echo "  $OUT_DIR/RELEASE_NOTE.html"
echo "  $OUT_DIR/RELEASE_NOTE.md"
