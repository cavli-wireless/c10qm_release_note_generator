# Cavli Release Note Generator

Generate a Cavli SDK / firmware release note from a list of GitHub
repositories. The pipeline fetches commits and merged PRs between two refs
per repo, builds Commit / Area / Change tables, and renders a document that
follows the `CQS290_RELEASE_NOTE_SDK_2.0.0` reference structure — Overview,
Part A (Android SDK / HLOS), Part B (Chipcode / firmware), Test Results,
Known Issues, and an Appendix A Build-ID comparison.

This repo is packaged as a Claude Code skill (see [SKILL.md](SKILL.md) for
the full, authoritative workflow). This README is the human-facing quick
start.

## What it does, and what it doesn't

Fetching commits/PRs from N repos and laying them out in tables is
mechanical — the scripts here do that. Deciding *which* commits matter,
writing the explanatory prose under each subsystem heading, and judging
whether a change belongs in Part A or Part B still requires reading the
actual diffs. This tool gets you a well-organized first draft fast; it does
not ghost-write the document unsupervised.

## Quick start

```bash
# 1. Install dependencies (see "Dependencies" below)
python3 scripts/check_deps.py

# 2. Point it at a repo list and an authored-content folder
./scripts/autonote.sh config/<product>/repos.yaml config/<product>/input out/
```

That's the one command: repos + your written content in,
`out/RELEASE_NOTE.pdf` out (plus `.html`, `.md`, and `out/release_note.yaml`).
Run it with an input dir that doesn't exist yet and it scaffolds one from the
template, then stops so you can fill it in.

Three worked configs ship in [`config/`](config/): [`aq20`](config/aq20),
[`c10qm_linux_4`](config/c10qm_linux_4), and
[`c10qm_linux_6`](config/c10qm_linux_6) — each a self-contained
`repos.yaml` + `area_rules.yaml` + `note_template.yaml` + `input/` folder.
Copy one as a starting point for a new product.

## Pipeline

```
                    [discover_repos.py]   (optional: scan a workspace
                              |            for git repos -> repos.yaml)
                              v
                      config/<product>/repos.yaml
                              |
        +---------------------+---------------------+
        |                                           |
  [fetch_local.py]                           [fetch_all.py]
  local clones, no token                     GitHub API, needs token
        |                                           |
        +---------------------+---------------------+
                              v
                  out/*.json + out/snapshot.md
                              |
          [build_change_table.py]  +  [build_parts.py]
                              |
     out/change_table.yaml       out/part_tables.yaml
     (flat, by repo)             (Part A / Part B, every subsystem)
                              |
       input/ (authored) --> [assemble_note.py] <-- derived tables
                              |
                  out/release_note.yaml  (fully generated)
                              |
                  [render_release_note.py]
                              |
     out/RELEASE_NOTE .pdf / .html / .md / .docx
```

Two ways to get commits:

- **`fetch_local.py`** (preferred) — reads `git log` from local clones. No
  token, no network, works with private repos. Run `git fetch --all --tags`
  in each clone first.
- **`fetch_all.py` / `fetch_commits.py`** — GitHub REST API. Use when repos
  aren't checked out, or you need PR metadata. Needs `GITHUB_TOKEN` (or
  `GH_TOKEN`) with read access and network access to `api.github.com`.

## Repo layout

| path | holds |
|---|---|
| `SKILL.md` | full pipeline documentation and step-by-step workflow (the source of truth) |
| `scripts/` | the pipeline — fetch, build tables, assemble, render (plain Python + two bash wrappers) |
| `config/<product>/` | per-product `repos.yaml`, `area_rules.yaml`, `note_template.yaml`, and an authored `input/` folder |
| `templates/` | Jinja2 templates (`release_note.html.j2`, `release_note.md.j2`) and optional embedded fonts |
| `examples/` | a rendered example release note (`.md`/`.html`/`.pdf`) showing the target output format |
| `input/`, `out/` (repo root) | untracked scratch folders — see `.gitignore` |

Within a product's `input/` folder — **authored, keep it in git**:

| file | holds |
|---|---|
| `versions.yaml` | title, subtitle, SDK + modem version, platform, overview paragraph, section headings |
| `architecture.md` | architecture / structural changes (bullet list) |
| `part_a.md` | Part A subsections (prose) |
| `part_b.md` | Part B subsections (prose) |
| `test_result.md` | Test Result tables |
| `known_issues.md` | Known Issues (bullet list) |

The `out/` directory produced by a run is **derived and disposable** —
delete and re-run any time.

## Dependencies

```bash
python3 scripts/check_deps.py     # reports what's missing + the exact fix
```

- Python 3 with `PyYAML`, `Jinja2`, `Markdown`, and (for the GitHub API path)
  `requests` — see [`scripts/requirements.txt`](scripts/requirements.txt).
- `git` — for `fetch_local.py`.
- Chrome or Chromium — for PDF output (`render_release_note.py` finds it
  automatically, or set `CHROME_BIN`).
- `pandoc` — optional, only for `.docx` output.

On Ubuntu/Debian/WSL, prefer system packages over `pip install` (PEP 668):

```bash
sudo apt install -y python3-yaml python3-jinja2 python3-markdown
```

## House conventions

A few standing rules enforced by the templates — see SKILL.md for the full
rationale:

1. **The change table lists only what changed.** Subsystems with no commits
   in range are dropped from the table (not shown as an empty/"no change"
   row); every subsystem's state still lives in `out/snapshot.md`. Two row
   types are never dropped because they're errors, not non-events:
   **PATH NOT FOUND** and **NESTED REPO**.
2. **A Part with zero changed subsystems renders one line** — "No changes on
   this release." — with no table, instead of an empty table.
3. **The test section is called "Test Result"**, not "Verification" or "Test
   Results".

## Output formats

`.pdf` matches the reference document (headless-Chrome print pipeline) and
is the deliverable format. `.html` is the same thing unprinted, handy for
review. `.md` is the plain source, good for diffing between releases.
`.docx` goes through pandoc and does not carry the reference styling.

## More detail

See [SKILL.md](SKILL.md) for the complete step-by-step workflow, authoring
formats (numbered headings, table conventions), the environment note about
GitHub network access from sandboxes, and the full script/file reference.
