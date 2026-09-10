---
name: cavli-release-note
description: Generate a Cavli SDK/firmware release note from a list of GitHub repositories (e.g. AQ20/modem_proc, cavli_linux_services, cavli_sdk_tools_linux). Fetches commits and merged PRs between two refs per repo via the GitHub API, builds Commit/Area/Change tables, and renders a document that follows the CQS290_RELEASE_NOTE_SDK_2.0.0 reference structure (Overview, Part A Android SDK/HLOS, Part B Chipcode/firmware, Test Results, Known Issues, Appendix Build-ID comparison). Use when asked to create, draft, or update a release note, changelog, or "what changed between versions" summary for a Cavli / cavli-wireless product.
---

# Cavli Release Note Generator

## What this skill automates, and what it doesn't

Fetching commits/PRs from N repositories and laying them out in tables is
mechanical — the scripts here do that. Deciding *which* commits matter,
writing the explanatory prose under each subsystem heading, and judging
whether a change belongs in Part A (Android SDK/HLOS) or Part B (Chipcode/
firmware) requires reading the actual diffs and exercising engineering
judgment — the reference document (`CQS290_RELEASE_NOTE_SDK_2.0.0.pdf` in
this project's folder) is a good example of that judgment already applied.
This skill's job is to remove the tedious data-gathering step and get you to
a well-organized first draft fast, not to fully ghost-write the document
unsupervised. When you (Claude) run this pipeline, plan on reading the
fetched commit messages/diffs yourself and curating the change tables and
subsystem write-ups before rendering — don't just pass raw commit subjects
through untouched.

## Pipeline overview

```
                    [discover_repos.py]   (optional: scan a workspace
                              |            for git repos -> repos.yaml)
                              v
                      config/repos.yaml
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
     (flat, by repo)             (Part A / Part B, every subsystem;
                              |   unchanged = blank Change cell)
                              |
       input/ (authored) --> [assemble_note.py] <-- derived tables
                              |
                  out/release_note.yaml  (fully generated)
                              |
                  [render_release_note.py]
                              |
     out/RELEASE_NOTE .pdf / .html / .md / .docx
```

## The one command

```
./scripts/autonote.sh config/aq20/repos.yaml config/aq20/input out/
```

repos + your written content in, `out/RELEASE_NOTE.pdf` out. No copy-paste and
no round-trip through anyone.

### Two folders, cleanly separated

**`<input-dir>` — AUTHORED. Yours. Keep it in git.** Nothing generated is ever
written here.

| file | holds |
|---|---|
| `versions.yaml` | title, subtitle, SDK + modem version, platform, overview paragraph, section headings |
| `architecture.md` | architecture / structural changes (bullet list) |
| `part_a.md` | Part A subsections (prose) |
| `part_b.md` | Part B subsections (prose) |
| `test_result.md` | Test Result tables |
| `known_issues.md` | Known Issues (bullet list) |

**`<out-dir>` — DERIVED. Disposable.** Commit tables, subsystem snapshots, the
assembled `release_note.yaml`, and the rendered document. Delete it and re-run
whenever you like; nothing you wrote lives there.

The loop is: edit the input folder, re-run, look at the PDF.

Run it with an input dir that does not exist and it is scaffolded from the
template, then the run stops so you can fill it in — rendering a document full
of `REPLACE_ME` would look like progress without being any.

### Authoring formats

Subsections (`part_a.md`, `part_b.md`) are `##` blocks. **Headings are numbered
automatically** — 2.1, 2.2 for Part A, 3.1, 3.2 for Part B — so you never
renumber by hand when inserting a section:

```markdown
## AT command interface — +CCOPS and MBN upload
commits: e86e6da, 5638f66

Two additions to the vendor AT command set:

- **`+CCOPS`** operator-selection response corrected.
```

The optional `commits:` line renders as code pills beside the heading, matching
the reference document. `test_result.md` uses the same `##` blocks, each
followed by a Markdown table, numbered 4.1, 4.2, ... Text before the first
heading becomes the section intro. `<!-- HTML comments -->` are stripped, so
templates can carry guidance that never reaches the document.

### Tables in the input files

**Any number of columns.** Two is not a special case — write as many as the
result needs and every output format follows:

```markdown
| # | Test Case | Env | Duration | Result |
|---:|---|:---:|---:|:---:|
| 1 | Full image build | EVK | 42 min | PASS |
| 2 | AT `+CCOPS` | EVK | 3 s | PASS |
```

- **Alignment carries through.** The markers in the separator row — `:---`
  left, `---:` right, `:---:` centered — reach the Markdown, the HTML and the
  PDF, so a numeric column stays right-aligned and a PASS/FAIL column stays
  centered.
- **A short row is padded**, so leaving trailing columns blank is fine.
- **A row with MORE cells than the header is an error**, naming the file, the
  section and the offending line. It nearly always means an unescaped pipe, and
  silently dropping the overflow would lose text somebody wrote.
- **A literal pipe is escaped** as `\|` (`grep a \| b`) and survives into the
  output unsplit.
- **The separator row is required** and must have one cell per column; a
  missing or mismatched one is reported with the corrected table printed back.
- Cells take inline markdown: `` `code` ``, **bold**, links.

Wide tables wrap rather than running past the page margin, and their header row
repeats across page breaks.

### What is filled in for you

The Part A/B change tables (every subsystem — see House conventions),
the From/To baselines with their dates, and **Appendix A — Build ID**: the
per-subsystem build ID comparison parsed from `about.html` at both release refs.

There is no commit-range appendix. With no `about_html` configured the document
simply ends after Known Issues; per-repo ranges and SHAs stay in
`out/snapshot.md` and `out/*.json` for anyone reproducing the build.

Any `REPLACE_ME` left in the input folder is counted at the end of the run, so
an unfinished note cannot ship unnoticed.

`scripts/generate.sh <repos.yaml> <out-dir> [release_note.yaml]` is the older,
more manual path: it stops after the change table so you can assemble the
document yourself. Use `autonote.sh` unless you specifically want that pause.

## Two ways to get the commits

**From local clones — `fetch_local.py`. Prefer this.** Reads `git log`
directly, so it needs no token, no network, and works with private repos. Most
firmware work already has the trees checked out. The one thing it can't
recover is PR titles/authors (those live on GitHub); PR *numbers* still get
picked up from commit subjects, which is enough for the change tables.

```
python3 scripts/discover_repos.py ~/workspace/aq20_linux_318 \
    --out config/aq20/repos.yaml --product AQ20     # find the repos
python3 scripts/fetch_local.py --repos-file config/aq20/repos.yaml --out-dir out/
```

Run `git fetch --all --tags` in each clone first, or you'll diff against a
stale baseline. `fetch_local.py` fails loudly if a `from_ref`/`to_ref` doesn't
exist rather than silently producing an empty or wrong range.

**From the GitHub API — `fetch_all.py` / `fetch_commits.py`.** Use when the
repos aren't checked out, or you want PR metadata. Needs `GITHUB_TOKEN` (or
`GH_TOKEN`) with read access to the org, and network access to
`api.github.com`. Note that a Claude cloud sandbox generally has **neither** —
its egress is allowlisted, so this path usually has to run on a developer
machine or CI runner.

## House conventions (do not deviate)

These are standing rules from the team. They are enforced in the templates, so
they hold automatically — but keep them in mind when authoring a
`release_note.yaml` by hand:

1. **The change table lists only what changed.** A subsystem with no commits in
   the release range is **dropped from the table**, not shown with an empty
   cell and not shown with a "no change" row. The table is a list of changes; a
   row saying nothing happened is not one.

   Dropped never means unaccounted for. `build_parts.py` counts every unchanged
   subsystem and names it in the run summary, and the full per-subsystem state
   — every configured path with the commit it currently sits at — stays in
   `out/snapshot.md` and `out/part_tables.md`. Those are working files; they do
   not go in the customer document.

   `--keep-unchanged` restores the old behaviour, giving each unchanged
   subsystem a row with its last-touching commit and the text
   **"No changes on this release"** in the Change column. That wording lives in
   one place, `NO_CHANGE` in `build_parts.py` (mirrored as `NO_CHANGE_TEXT` in
   `render_release_note.py`). `--omit-unchanged` is still accepted and is now a
   no-op, since it describes the default.

   Two kinds of row are **never** dropped, because they are errors rather than
   quiet non-events: a subsystem path matching nothing renders as
   **PATH NOT FOUND**, and an untracked nested repo renders as **NESTED REPO**.
   Both would otherwise vanish silently, looking exactly like "nothing
   changed" — which is the failure this rule could easily have introduced.

2. **A Part where nothing moved says so in one line, with no table.** When no
   subsystem in Part A (or Part B) has a single commit in the range,
   `build_parts.py` sets `no_changes: true`, `assemble_note.py` carries the flag
   through, and the templates emit

       **No changes on this release.**

   With unchanged subsystems already dropped by rule 1, such a Part has no rows
   left, so no table renders and the line stands alone.

   The statement and the table are two **independent** conditions in the
   templates, deliberately not an `if/else`:

   - the statement renders when `part.no_changes`;
   - the table renders when `part.change_table.rows` is non-empty.

   Normally exactly one appears. But a no-change Part can still hold rows — the
   PATH NOT FOUND and NESTED REPO rows above, and every row under
   `--keep-unchanged` — and an `if/else` would hide precisely the rows that most
   need to be seen. Keep them independent.

   Two things must stay in step with the flag, and both already are:

   - `part_intro()` in `assemble_note.py` swaps in a table-free intro, since the
     normal one points at "the table below". Override per Part in
     `versions.yaml` with `part_a_intro_no_changes` / `part_b_intro_no_changes`.
   - the identical-commit lint in `render_release_note.py` skips a Part with
     `no_changes`, so nobody hunts for a table that is not in the document.

3. **The test section is called "Test Result"**, not "Verification", not
   "Test Results".

## Matching the reference document's format

The reference `CQS290_RELEASE_NOTE_SDK_2.0.0.pdf` was produced by **printing an
HTML page from headless Chrome** — its own PDF metadata says so (Creator:
HeadlessChrome, Producer: Skia/PDF, source file `render.html`). This skill
reproduces that exact pipeline, so `--out-pdf` output matches the reference
rather than approximating it. The styling in `templates/release_note.html.j2`
was measured out of the reference PDF, not guessed:

| | value |
|---|---|
| Headings / rules | teal `#0f766e` |
| Subtitle | `#334155` |
| Body text | `#24292f` |
| Table header fill | `#f1f6f5`, borders `#cfd8d6` |
| Note callout | `#f6f9f8` with 3px teal left border |
| Inline code | `#eef4f3` pill, DejaVu Sans Mono |
| Type scale | h1 20pt · subtitle 15pt · h2 14pt · h3 12pt · body 10.5pt · tables 9pt · code 9.6/9.2pt |
| Rhythm | body line pitch 12pt, paragraph gap +6pt, list pitch 14.25pt |
| Page | A4, 45px margins |

The type scale came from the reference PDF's own `/Tf` operators, so those
sizes are exact rather than eyeballed.

**Fonts.** The reference is set in **Roboto**. Chrome only uses Roboto if it's
installed on the rendering machine — on Windows it usually isn't, so the CSS
falls back to Segoe UI / Arial. Colors, sizes and layout still match; only line
breaks shift slightly, because the fallback faces are marginally wider. For
byte-identical typography, drop `Roboto-Regular/-Bold/-Italic` (`.woff2` or
`.ttf`) into `templates/fonts/` — `render_release_note.py` base64-embeds
whatever it finds there into the HTML automatically. See
`templates/fonts/README.md`.

**Which output format to hand over.** `.pdf` is the one that matches the
reference — use it as the deliverable. `.html` is the same thing unprinted
(handy for review and for re-printing from a browser). `.md` is the plain
source, good for diffing between releases or pasting into a wiki. `.docx` goes
through pandoc and does *not* carry the reference styling; only produce it if
someone specifically needs to edit in Word, and pass `--reference-docx` with a
branded Word template to get closer.

Scripts live in `scripts/`, are plain Python (`requirements.txt` lists the 3
dependencies: `requests`, `PyYAML`, `Jinja2`), and are meant to be run from a
shell that has real network access to `api.github.com` and, for private
Cavli repos, a GitHub token with read access to the `cavli-wireless` org.

**Important environment note:** a Claude cloud sandbox (Cowork/Claude Code
remote session) typically does NOT have open network access to arbitrary
GitHub repos — its outbound traffic to `api.github.com`/`github.com` is
gated by a per-session allowlist, so `fetch_commits.py`/`fetch_all.py` will
likely fail there even with a valid token. Run the fetch stage from an
environment with real GitHub access instead: the user's own machine (a
local terminal, or `device_bash` if that tool has network access enabled
for this session — check first), a CI runner, or any shell where
`curl https://api.github.com` and `git` already work against GitHub. The
render stage (`render_release_note.py`) has no network dependency and can
run anywhere, including inside a cloud sandbox, once you have the JSON/YAML
data.

## Step-by-step workflow

1. **Collect the repo list and version boundary from the user.** For each
   repo you need: `owner/repo`, the ref that marks the *previous* release
   (tag/branch/SHA — this is "From"), and the ref for *this* release ("To":
   often a branch head like `master`/`main`, or a new tag once cut).
   Optionally a `path` to scope to a subfolder (e.g. `atcm` inside a
   monorepo-ish service repo — see the second entry in
   `config/repos.example.yaml`, modeled on the AQ20 example the user gave:
   `AQ20/modem_proc`, `cavli_linux_services/atcm`, and
   `cavli_sdk_tools_linux@linux_3.18`). If a repo has no previous-release tag
   yet, use `since_days` instead of `from_ref` (rolling window). Write this
   into a `repos.yaml` modeled on `config/repos.example.yaml`.

2. **Make sure GitHub auth is available** wherever you'll run the fetch
   step: `export GITHUB_TOKEN=$(gh auth token)` or a PAT with `repo` read
   scope for the `cavli-wireless` org. Without it, private repos 404/403 and
   public API calls are capped at 60 requests/hour.

3. **Fetch.** From that shell:
   ```
   python3 scripts/fetch_all.py --repos-file repos.yaml --out-dir out/
   ```
   This writes `out/<repo-name>.json` (commits with files-changed, plus any
   PR referenced in a commit subject) and `out/snapshot.md` — the
   "commit ID / snapshot per subsystem" table the project instructions ask
   for (repo, path, from/to ref, resolved SHA, commit count).

4. **Build the raw change table.**
   ```
   python3 scripts/build_change_table.py --in-dir out/ --out out/change_table.yaml \
       --area-rules config/area_rules.example.yaml --depth 2
   ```
   `area_rules.example.yaml` maps file-path regexes to human-readable Area
   labels (e.g. `vendor/camera` -> "vendor / camera"); anything unmatched
   falls back to an auto path-prefix guess. Copy and extend this file per
   product — the rules are repo/tree-layout specific. Review
   `out/change_table.preview.md`: drop noise commits (pure baseline syncs
   you don't want called out twice, formatting-only changes, reverts), fix
   any auto-guessed Area you don't like, and rewrite `change` text to be
   reader-facing rather than a raw commit subject where needed.

5. **Assemble `release_note.yaml`.** Copy
   `config/release_note.example.yaml` (a fully worked example reproducing
   the CQS290 reference doc's structure/field names) and fill it in using:
   - `out/snapshot.md` and the curated `out/change_table.yaml` for the
     `meta`, `part_a.change_table` / `part_b.change_table` sections.
   - Your own reading of the commits/diffs (and PR descriptions in
     `out/*.json` -> `pull_requests[]`) to write the `overview`, each
     `part_a.subsections[]` / `part_b.subsections[]` narrative (mirrors
     reference §2.1-2.8 and §3.1-3.5), and `known_issues`.
   - Test results and the Appendix A build-ID comparison table come from
     wherever the team tracks them (test reports, build server) — ask the
     user if they're not supplied; don't fabricate PASS/FAIL results or
     build IDs.
   Full field-by-field schema is documented via comments in
   `config/release_note.example.yaml`; the Jinja2 template that consumes it
   is `templates/release_note.md.j2`.

6. **Render.**
   ```
   python3 scripts/render_release_note.py --config release_note.yaml \
       --out-all out/RELEASE_NOTE
   ```
   That writes `.md`, `.html`, `.pdf` and `.docx` in one go. To produce only
   the format that matches the reference:
   ```
   python3 scripts/render_release_note.py --config release_note.yaml \
       --out-pdf out/RELEASE_NOTE.pdf --out-html out/RELEASE_NOTE.html
   ```
   PDF output needs Chrome/Chromium on the machine. The script finds it
   automatically (PATH, the usual Windows/macOS install locations, and
   Playwright's bundled Chromium); otherwise set `CHROME_BIN=/path/to/chrome`,
   or just open the generated `.html` and print to PDF from the browser
   (margins: Default, **Background graphics: ON** — otherwise the table
   shading and note callouts come out white).

7. **Review against the reference format** before delivering: title +
   metadata block, §1 Overview (intro, architecture changes, Part A/B
   split, appendix pointer), §2 Part A with peripherals + change-set tables
   and numbered subsections, §3 Part B likewise, §4 Test Results, §5 Known
   Issues, Appendix A Build-ID table. Send the final file to the user with
   SendUserFile (and write it back into their connected project folder, per
   the sharing-files convention).

## File reference

- `scripts/generate.sh` — one-command runner for the local-clone path
  (fetch -> change table -> render), stopping for curation in between.
- `scripts/discover_repos.py` — scan a workspace root for git repos and emit a
  starter `repos.yaml`, reporting each repo's remote, branch, tags and commit
  count so you can pick a baseline.
- `scripts/fetch_local.py` — commits from local clones via `git log`. Same
  output schema as the API path; no token or network needed. Handles path
  scoping, `from..to` ranges, `since_days` windows, and full history.
- `scripts/fetch_commits.py` — single-repo commit fetch (GitHub REST
  `compare` API for exact ref ranges; falls back to a date-windowed
  `commits` list when no baseline ref exists yet). Resolves PR numbers
  referenced in commit subjects (`(#123)` squash-merge pattern, or
  `Merge pull request #123 from ...`) to full PR metadata.
- `scripts/fetch_all.py` — runs `fetch_commits.py` over every repo in a
  `repos.yaml`, plus writes the cross-repo `snapshot.md` table.
- `scripts/build_change_table.py` — turns raw commit JSON into
  Commit/Area/Change rows; Area is auto-derived from the common directory
  prefix of changed files, overridable via `area_rules.yaml`.
- `scripts/autonote.sh` — **the one command**: repos in, PDF out, no copy-paste.
- `scripts/assemble_note.py` — combines the authored input folder with the
  derived tables/metadata into release_note.yaml (fully generated).
- `scripts/inputs.py` — parses the authored input folder (Markdown + one YAML).
- `config/aq20/input/` — the input folder template, scaffolded on first run.
- `scripts/build_parts.py` — generates the finished **Part A / Part B** change
  tables, with every configured subsystem present (changed ones by commit,
  untouched ones as "No change" pinned to their last-touching commit). Flags
  bad subsystem paths and commits that fall outside every subsystem.
- `scripts/render_release_note.py` — Jinja2 render of `release_note.yaml` into
  Markdown / HTML / PDF / DOCX. Handles Chrome discovery for PDF printing and
  auto-embeds any fonts in `templates/fonts/`.
- `templates/release_note.html.j2` — **the format-matching template**: styling
  measured from the reference PDF, printed to PDF by headless Chrome.
- `templates/release_note.md.j2` — the same document as plain Markdown.
- `templates/fonts/` — drop Roboto here for typographically exact output.
- `config/repos.example.yaml` — worked example using the AQ20 repo list
  (AQ20/modem_proc, cavli_linux_services/atcm, cavli_sdk_tools_linux).
- `config/aq20/release_note.starter.yaml` — AQ20-shaped scaffold to fill in
  (Part A = Linux SDK/services, Part B = chipcode), as opposed to the CQS290
  example which is Android-shaped.
- `config/area_rules.example.yaml` — worked example Area-label rules drawn
  from the CQS290 reference doc's own category names.
- `config/release_note.example.yaml` — the CQS290 reference doc's content
  reproduced in the YAML schema `render_release_note.py` expects; use it as
  the field-by-field template for a new release note.

## Common pitfalls (already fixed in these scripts, worth knowing about)

- GitHub's `compare` API doesn't support a `path` filter — `fetch_commits.py`
  cross-references against the path-scoped `commits` list on the head ref to
  emulate it.
- Squash-merged PRs don't produce a two-parent merge commit, so PR number
  extraction has to also match the `(#123)` suffix GitHub appends to the
  commit subject, not just `Merge pull request #N`.
- Jinja's dict attribute lookup silently resolves `foo.items` to Python's
  `dict.items` method instead of a config key literally named `items` —
  that's why the known-issues list field is named `points`, not `items`, in
  the YAML schema. Keep that naming if you extend the schema.
- Markdown table rendering is done by the `md_table` Python filter (not a
  Jinja for-loop) specifically to avoid whitespace-trimming bugs between the
  header separator row and the first data row.
