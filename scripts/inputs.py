#!/usr/bin/env python3
"""
inputs.py — Parse the human-authored input folder.

The pipeline has two kinds of content, and they belong in different places:

  DERIVED   commit tables, subsystem snapshots, From/To refs and SHAs, the
            appendix range table. Read from the repos, regenerated every run,
            never hand-edited.
  AUTHORED  version numbers, what the release is for, why each change matters,
            test results, known issues. Only a human can write these.

Everything AUTHORED lives in one input folder, in formats that are pleasant to
write and diff — plain Markdown and one small YAML file:

    input/
      versions.yaml      title, subtitle, SDK + modem versions, overview intro
      architecture.md    architecture / structural changes (bullet list)
      part_a.md          Part A subsections (prose)
      part_b.md          Part B subsections (prose)
      test_result.md     Test Result tables
      known_issues.md    Known Issues (bullet list)

Nothing generated is ever written back into this folder, so it is safe to keep
in version control alongside the release.

Subsection format (part_a.md / part_b.md) — headings are auto-numbered 2.1,
2.2, ... for Part A and 3.1, 3.2, ... for Part B, so you never renumber by hand:

    ## AT command interface
    commits: e86e6da, 5638f66

    The `+RFI` command now reports the RFC and QCN version.

    - Bullets work.
    - So does **bold** and `code`.

    ## Next theme
    commits: dcc4e79

    ...

Table format (test_result.md) — a `##` heading followed by a Markdown table:

    ## Functional Test Cases

    | Test Case | Result |
    |---|---|
    | Full image build | PASS |
"""
import os
import re

import yaml

MISSING = object()


class InputError(Exception):
    pass


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    """Drop HTML-comment blocks so templates can carry guidance that never
    reaches the document."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def load_versions(input_dir):
    """versions.yaml — the only YAML the author touches."""
    path = os.path.join(input_dir, "versions.yaml")
    raw = _read(path)
    if raw is None:
        raise InputError(f"missing {path}")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise InputError(f"{path} is not valid YAML:\n{e}")
    if not isinstance(data, dict):
        raise InputError(f"{path} must be a YAML mapping")
    return interpolate(data)


def interpolate(data):
    """Let versions.yaml reference its own scalar fields as {name}.

    So the version number is written once:

        sdk_version: "1.2.5"
        title: "Release Note AQ20 SDK {sdk_version}"

    Only scalar keys defined in this file are substituted, in a single pass
    (no recursion, so a value containing braces can't loop). An unknown
    placeholder is left exactly as written rather than silently blanked —
    a visible `{typo}` in the rendered document is easier to catch than an
    empty title.
    """
    scalars = {k: str(v) for k, v in data.items()
               if isinstance(v, (str, int, float) ) and not isinstance(v, bool)}

    def sub(value):
        if isinstance(value, str):
            for k, v in scalars.items():
                token = "{" + k + "}"
                if token in value:
                    value = value.replace(token, v)
            return value
        if isinstance(value, list):
            return [sub(x) for x in value]
        if isinstance(value, dict):
            return {k: sub(x) for k, x in value.items()}
        return value

    return {k: sub(v) for k, v in data.items()}


def load_bullets(input_dir, filename):
    """A Markdown bullet list -> list of strings. Non-bullet lines are kept as
    their own entries so a stray paragraph is never silently dropped."""
    raw = _read(os.path.join(input_dir, filename))
    if raw is None:
        return []
    out = []
    for line in _strip_comments(raw).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(re.sub(r"^[-*]\s+", "", line))
    return out


# A separator cell: ---, :---, ---:, :---:  (alignment markers optional)
_SEP_CELL_RE = re.compile(r"^:?-{1,}:?$")
# Split on pipes that are not backslash-escaped, so a cell may contain a
# literal "|" written as "\|".
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _md_cells(line):
    """Split one Markdown table row into cells.

    Any number of columns is supported. A literal pipe inside a cell is written
    escaped (`a \| b`) and comes back unescaped, so escaping a pipe never
    silently creates an extra column.
    """
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in _UNESCAPED_PIPE_RE.split(line)]


def _is_separator(cells):
    return bool(cells) and all(_SEP_CELL_RE.match(c) for c in cells)


def _alignments(sep_cells):
    """Read per-column alignment out of the separator row.

    :---  left   ---:  right   :---:  center   ---  unset (renderer default)
    """
    out = []
    for c in sep_cells:
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else
                   "right" if right else
                   "left" if left else "")
    return out


def _parse_md_table(lines, where=""):
    """Markdown table -> {'headers': [...], 'align': [...], 'rows': [[...]]}.

    Works for any number of columns. Ragged rows are the common authoring
    mistake, and the two directions mean different things:

      - too FEW cells: padded with empty strings, so the table still renders
        square. Leaving a trailing column blank is a normal thing to do.
      - too MANY cells: an error. It nearly always means an unescaped `|` inside
        a cell, and silently dropping the overflow would lose text the author
        wrote.
    """
    rows = [l.strip() for l in lines if l.strip().startswith("|")]
    if len(rows) < 2:
        return None

    headers = _md_cells(rows[0])
    ncols = len(headers)

    sep = _md_cells(rows[1])
    if not _is_separator(sep):
        raise InputError(
            f"{where}: the line after the header row must be a Markdown table "
            f"separator, e.g.\n"
            f"    | {' | '.join(headers)} |\n"
            f"    |{'|'.join(['---'] * ncols)}|\n"
            f"  got: {rows[1]}")
    if len(sep) != ncols:
        raise InputError(
            f"{where}: the table has {ncols} header column(s) but its separator "
            f"row has {len(sep)}. They must match.\n"
            f"  header:    {rows[0]}\n"
            f"  separator: {rows[1]}")
    align = _alignments(sep)

    body = []
    for raw in rows[2:]:
        cells = _md_cells(raw)
        if not any(c for c in cells):
            continue
        if len(cells) > ncols:
            raise InputError(
                f"{where}: a row has {len(cells)} cells but the table has {ncols} "
                f"column(s). If a cell contains a literal pipe, escape it as "
                f"\\| .\n"
                f"  row: {raw}")
        cells += [""] * (ncols - len(cells))
        body.append(cells)
    return {"headers": headers, "align": align, "rows": body}


def load_sections(input_dir, filename, number_prefix):
    """Parse `## heading` blocks into release-note subsections.

    Headings are numbered automatically (`number_prefix` of 2 -> 2.1, 2.2 ...)
    so authors never maintain numbering by hand.
    """
    raw = _read(os.path.join(input_dir, filename))
    if raw is None:
        return []
    text = _strip_comments(raw)

    blocks = re.split(r"^##\s+", text, flags=re.M)[1:]
    sections = []
    for i, block in enumerate(blocks, 1):
        lines = block.splitlines()
        heading = lines[0].strip()
        rest = lines[1:]

        commits = []
        body = []
        for line in rest:
            m = re.match(r"^\s*commits?\s*:\s*(.*)$", line, re.I)
            if m and not body:
                commits = [c.strip().strip("`")
                           for c in re.split(r"[,\s]+", m.group(1)) if c.strip()]
                continue
            body.append(line.rstrip())

        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()

        sections.append({
            "heading": f"{number_prefix}.{i} {heading}",
            "commit_refs": commits,
            "body": body,
        })
    return sections


def load_tables(input_dir, filename, number_prefix):
    """Parse `## heading` + Markdown table blocks into table specs."""
    raw = _read(os.path.join(input_dir, filename))
    if raw is None:
        return [], ""
    text = _strip_comments(raw)

    # Anything before the first ## heading is the section intro.
    parts = re.split(r"^##\s+", text, flags=re.M)
    intro = parts[0].strip()
    tables = []
    for i, block in enumerate(parts[1:], 1):
        lines = block.splitlines()
        heading = lines[0].strip()
        table = _parse_md_table(
            lines[1:], where=f"{os.path.join(input_dir, filename)} (section '{heading}')")
        if not table:
            raise InputError(
                f"{os.path.join(input_dir, filename)}: section '{heading}' has no "
                f"Markdown table. Expected a '| col | col |' block under the heading."
            )
        tables.append({"heading": f"{number_prefix}.{i} {heading}", **table})
    return tables, intro


def load_all(input_dir):
    """Read the whole input folder into the release-note fragments."""
    if not os.path.isdir(input_dir):
        raise InputError(
            f"input folder not found: {input_dir}\n"
            f"Create one by copying the template:  cp -r config/aq20/input {input_dir}"
        )
    v = load_versions(input_dir)
    test_tables, test_intro = load_tables(input_dir, "test_result.md", 4)

    return {
        "versions": v,
        "architecture_changes": load_bullets(input_dir, "architecture.md"),
        "part_a_subsections": load_sections(input_dir, "part_a.md", 2),
        "part_b_subsections": load_sections(input_dir, "part_b.md", 3),
        "test_tables": test_tables,
        "test_intro": test_intro or v.get("test_intro", ""),
        "known_issues": load_bullets(input_dir, "known_issues.md"),
    }
