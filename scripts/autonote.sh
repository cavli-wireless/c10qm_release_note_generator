#!/usr/bin/env bash
# autonote.sh — one command, repos in, release note PDF out. No copy-paste.
#
#   fetch_local -> build_parts -> assemble_note -> render_release_note
#
# Usage:
#   ./scripts/autonote.sh <repos.yaml> <input-dir> [out-dir]
#
# Example:
#   ./scripts/autonote.sh config/aq20/repos.yaml config/aq20/input out/
#     -> out/RELEASE_NOTE.pdf   (+ .html, .md, and out/release_note.yaml)
#
# Two folders, cleanly separated:
#
#   <input-dir>   AUTHORED — yours. versions.yaml + five Markdown files:
#                 SDK/modem versions, architecture changes, Part A and Part B
#                 subsections, test results, known issues. Keep it in git.
#                 Nothing generated is ever written here.
#
#   <out-dir>     DERIVED — disposable. Commit tables, snapshots, the assembled
#                 release_note.yaml and the rendered document. Safe to delete
#                 and regenerate at any time; nothing you wrote lives here.
#
# The loop is: edit <input-dir>, re-run, look at the PDF.
#
# If <input-dir> does not exist it is scaffolded from the template and the run
# stops so you can fill it in.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="${PYTHON:-python3}"

REPOS_FILE="${1:-}"
INPUT_DIR="${2:-}"
OUT_DIR="${3:-out}"

if [[ -z "$REPOS_FILE" || ! -f "$REPOS_FILE" ]]; then
  echo "usage: $0 <repos.yaml> <input-dir> [out-dir]" >&2
  [[ -n "$REPOS_FILE" ]] && echo "error: no such file: $REPOS_FILE" >&2
  exit 2
fi
if [[ -z "$INPUT_DIR" ]]; then
  # Prefer the project-level input/ next to scripts/, then one beside the
  # repos.yaml, so the short form of the command just works.
  if [[ -d "$ROOT/input" ]]; then
    INPUT_DIR="$ROOT/input"
  else
    INPUT_DIR="$(dirname "$REPOS_FILE")/input"
  fi
  echo "    (no input dir given, using $INPUT_DIR)"
fi

# Scaffold the authored folder on first use, then stop: rendering a document
# full of REPLACE_ME would look like progress without being any.
if [[ ! -d "$INPUT_DIR" ]]; then
  TEMPLATE_DIR="$ROOT/config/aq20/input"
  if [[ ! -d "$TEMPLATE_DIR" ]]; then
    echo "error: no input folder at $INPUT_DIR and no template at $TEMPLATE_DIR" >&2
    exit 2
  fi
  mkdir -p "$INPUT_DIR"
  cp -r "$TEMPLATE_DIR/." "$INPUT_DIR/"
  cat <<EOF

Created the authored input folder: $INPUT_DIR

  versions.yaml     SDK + modem version, title, overview paragraph
  architecture.md   architecture / structural changes
  part_a.md         Part A subsections (prose)
  part_b.md         Part B subsections (prose)
  test_result.md    Test Result tables
  known_issues.md   Known Issues

Fill these in, then re-run:
  $0 $REPOS_FILE $INPUT_DIR $OUT_DIR
EOF
  exit 0
fi

AREA_RULES="$ROOT/config/area_rules.example.yaml"
[[ -f "$ROOT/config/area_rules.yaml" ]] && AREA_RULES="$ROOT/config/area_rules.yaml"
SIBLING_RULES="$(dirname "$REPOS_FILE")/area_rules.yaml"
[[ -f "$SIBLING_RULES" ]] && AREA_RULES="$SIBLING_RULES"

if ! "$PY" "$HERE/check_deps.py" --stage all >/tmp/rn_deps.$$ 2>&1; then
  cat /tmp/rn_deps.$$; rm -f /tmp/rn_deps.$$
  exit 1
fi
rm -f /tmp/rn_deps.$$

echo "==> 1/4  reading commits from local clones"
"$PY" "$HERE/fetch_local.py" --repos-file "$REPOS_FILE" --out-dir "$OUT_DIR"

echo
echo "==> 2/4  building Part A / Part B tables   (area rules: $AREA_RULES)"
if ! grep -q '^[[:space:]]*subsystems:' "$REPOS_FILE"; then
  echo "error: $REPOS_FILE declares no 'subsystems:' — autonote needs them to build the" >&2
  echo "       Part A/B tables. Generate a list with:" >&2
  echo "         $PY $HERE/fetch_local.py --list-subsystems <clone>" >&2
  exit 2
fi
"$PY" "$HERE/build_parts.py" \
    --repos-file "$REPOS_FILE" \
    --in-dir "$OUT_DIR" \
    --out "$OUT_DIR/part_tables.yaml"

# Build IDs from about.html, if the repo has one and versions.yaml asks for it.
BUILD_IDS_ARG=()
ABOUT_REPO="$("$PY" - "$INPUT_DIR/versions.yaml" <<'PYEOF'
import sys, yaml
try:
    v = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    v = {}
print(v.get("about_html", "") or "")
PYEOF
)"
if [[ -n "$ABOUT_REPO" ]]; then
  echo
  echo "==> 2c/4  reading build IDs from about.html ($ABOUT_REPO)"
  PRIMARY="$("$PY" - "$REPOS_FILE" <<'PYEOF'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
r = (cfg.get("repos") or [{}])[0]
print(f"{r.get('local_path','')}\t{r.get('from_ref','')}\t{r.get('to_ref','')}")
PYEOF
)"
  A_PATH="$(cut -f1 <<<"$PRIMARY")"; A_FROM="$(cut -f2 <<<"$PRIMARY")"; A_TO="$(cut -f3 <<<"$PRIMARY")"
  # "auto" lets parse_about locate about.html itself via `git ls-files`.
  PATH_ARG=()
  [[ "$ABOUT_REPO" != "auto" ]] && PATH_ARG=(--path "$ABOUT_REPO")
  if ! "$PY" "$HERE/parse_about.py" --repo "$A_PATH" "${PATH_ARG[@]}" \
        --from-ref "$A_FROM" --to-ref "$A_TO" --filter \
        --out "$OUT_DIR/build_ids.yaml"; then
    echo "error: could not build Appendix A from about.html. Inspect it with:" >&2
    echo "         $PY $HERE/parse_about.py --repo $A_PATH --ref $A_TO --dump" >&2
    exit 1
  fi
  BUILD_IDS_ARG=(--build-ids "$OUT_DIR/build_ids.yaml")
fi

echo
echo "==> 3/4  assembling release_note.yaml   (authored input: $INPUT_DIR)"
"$PY" "$HERE/assemble_note.py" \
    --in-dir "$OUT_DIR" \
    --parts "$OUT_DIR/part_tables.yaml" \
    --input-dir "$INPUT_DIR" \
    --out "$OUT_DIR/release_note.yaml" \
    "${BUILD_IDS_ARG[@]}"

echo
echo "==> 4/4  rendering document"
"$PY" "$HERE/render_release_note.py" \
    --config "$OUT_DIR/release_note.yaml" \
    --template-dir "$ROOT/templates" \
    --out-md "$OUT_DIR/RELEASE_NOTE.md" \
    --out-html "$OUT_DIR/RELEASE_NOTE.html" \
    --out-pdf "$OUT_DIR/RELEASE_NOTE.pdf"

cat <<EOF

==> done

  $OUT_DIR/RELEASE_NOTE.pdf     <- the deliverable (matches the reference format)
  $OUT_DIR/RELEASE_NOTE.html
  $OUT_DIR/RELEASE_NOTE.md

  $OUT_DIR/release_note.yaml    assembled input + derived data (generated)
  $OUT_DIR/snapshot.md          per-subsystem commit snapshot
  $OUT_DIR/part_tables.md       generated Part A / B tables, readable

To change the document, edit $INPUT_DIR and re-run.
Everything in $OUT_DIR is generated and safe to delete.
EOF
