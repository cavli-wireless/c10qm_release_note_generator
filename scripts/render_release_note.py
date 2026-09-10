#!/usr/bin/env python3
"""
render_release_note.py — Render release_note.yaml into the final release note
document, in whichever formats you ask for:

  --out-md    plain Markdown        (templates/release_note.md.j2)
  --out-html  styled HTML           (templates/release_note.html.j2)
  --out-pdf   PDF via headless Chrome printing that HTML
  --out-docx  Word via pandoc

The HTML/PDF path reproduces the visual format of the reference document
CQS290_RELEASE_NOTE_SDK_2.0.0.pdf — whose own PDF metadata shows it was made
the same way (Creator: HeadlessChrome, Producer: Skia/PDF, source file
"render.html"). Colors, fonts and page geometry in the HTML template were
sampled directly from that reference, so `--out-pdf` output matches it.

This is the last step of the pipeline:
  fetch_all.py -> build_change_table.py -> (you curate) -> render_release_note.py

The YAML schema is documented in config/release_note.example.yaml, a fully
worked example reproducing the reference doc's structure (Overview, Part A
Android SDK/HLOS, Part B Chipcode/firmware, Test Results, Known Issues,
Appendix A Build ID comparison).

Usage:
  # the usual: styled PDF + the Markdown source it came from
  python3 render_release_note.py --config release_note.yaml \
      --out-md out/RELEASE_NOTE.md --out-html out/RELEASE_NOTE.html \
      --out-pdf out/RELEASE_NOTE.pdf

  # everything, including Word
  python3 render_release_note.py --config release_note.yaml --out-all out/RELEASE_NOTE
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import yaml
from jinja2 import Environment, FileSystemLoader, ChainableUndefined

try:
    import markdown as md_lib
except ImportError:
    md_lib = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE_DIR = os.path.join(os.path.dirname(HERE), "templates")

# Chrome/Chromium binaries we try, in order, for --out-pdf.
CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN"),
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# Under WSL there is usually no Linux browser, but the Windows one is reachable
# through /mnt/c via interop. Edge is included because it ships on every
# Windows install and is the same Chromium engine, so the output is identical.
WSL_CANDIDATES = [
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]


def is_wsl():
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def is_windows_exe(path):
    return bool(path) and path.lower().endswith(".exe")


def to_win_path(path):
    """Translate a WSL path to a Windows one so a Windows browser can open it.

    Windows Chrome cannot resolve /home/... or /tmp/...; it needs D:\\... or a
    \\\\wsl.localhost\\... UNC path. `wslpath -w` does exactly that translation.
    """
    try:
        out = subprocess.run(["wslpath", "-w", os.path.abspath(path)],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.path.abspath(path)


# --------------------------------------------------------------------------
# Jinja filters
# --------------------------------------------------------------------------

NO_CHANGE_TEXT = "No changes on this release"


def ensure_rows(t, default_headers=None):
    """Guarantee a change table renders, even with nothing in it.

    House rules:
      - The change table is always present in every Part. A missing table is
        ambiguous (did nothing change, or did nobody check?); an explicit row
        is a statement.
      - A "no change" row still carries the commit ID and the area/image, so
        the document always pins every subsystem to a commit. That is the
        subsystem snapshot: "this image did not change, and here is the commit
        it sits at."

    Supply those values in the YAML alongside the empty table:

        change_table:
          headers: ["Commit", "Image", "Change"]
          rows: []
          no_change:
            commit: "`06f07bc`"                 # commit the subsystem sits at
            area:   "modem_proc, boot_images"   # or per-column: ["a", "b"]
            text:   "No changes on this release" # optional override

    You can also just write the no-change rows out by hand in `rows:` — this
    only fires when there are none.
    """
    t = dict(t) if t else {}
    headers = t.get("headers") or default_headers or ["Commit", "Area", "Change"]
    # `align` is per-column, so it must never outlive a header list it no
    # longer matches; _squared() re-pads it, this just drops a stale one.
    if t.get("align") and len(t["align"]) != len(headers):
        t.pop("align")
    rows = [r for r in (t.get("rows") or []) if any(str(c).strip() for c in r)]
    if not rows:
        nc = t.get("no_change") or {}
        if isinstance(nc, str):            # shorthand: no_change: "<commit>"
            nc = {"commit": nc}
        commit = str(nc.get("commit", "")).strip() or "—"
        text = str(nc.get("text", "") or NO_CHANGE_TEXT)
        n_mid = max(0, len(headers) - 2)   # columns between Commit and Change
        area = nc.get("area", "")
        if isinstance(area, (list, tuple)):
            mid = [str(a) for a in area][:n_mid]
            mid += ["—"] * (n_mid - len(mid))
        else:
            area = str(area).strip() or "—"
            mid = [area] * n_mid
        rows = [[commit] + mid + [text]]
    t["headers"], t["rows"] = headers, rows
    return t


# Separator cell for each alignment, used by md_table.
_MD_SEP = {"left": ":---", "right": "---:", "center": ":---:", "": "---"}


def _squared(t):
    """Headers, per-column alignment and rows, all normalised to one width.

    Any column count is supported. Rows shorter than the header are padded and
    rows longer are truncated, so a ragged table — from a hand-edited YAML or a
    generated one — can never emit a row with the wrong number of cells, which
    both Markdown and HTML render as a visibly broken table.
    """
    headers = [str(h) for h in (t.get("headers") or [])]
    rows = [[str(c) for c in (r or [])] for r in (t.get("rows") or [])]
    ncols = max([len(headers)] + [len(r) for r in rows] or [0])
    headers += [""] * (ncols - len(headers))
    rows = [r + [""] * (ncols - len(r)) if len(r) < ncols else r[:ncols] for r in rows]
    align = [str(a) for a in (t.get("align") or [])]
    align += [""] * (ncols - len(align))
    return headers, align[:ncols], rows


def md_table(t):
    """Render a table spec as a GitHub-flavored Markdown table, any width.

    Built as a filter rather than a Jinja for-loop on purpose: looping in the
    template kept gluing the header separator row onto the first data row.

    Per-column alignment from the input file's separator row is preserved, so a
    right-aligned numeric column stays right-aligned in the Markdown output too.
    A literal pipe inside a cell is re-escaped, so it cannot split the cell.
    """
    if not t:
        return ""
    headers, align, rows = _squared(t)
    if not headers:
        return ""

    def cell(v):
        return str(v).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(h) for h in headers) + " |",
             "|" + "|".join(_MD_SEP.get(a, "---") for a in align) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(cell(c) for c in row) + " |")
    return "\n".join(lines)


def _require_markdown():
    if md_lib is None:
        raise SystemExit(
            "The 'markdown' package is required for HTML/PDF output.\n"
            "Install it with:  pip install markdown\n"
            "(or render Markdown only, with --out-md)"
        )


def md_block(text):
    """Markdown -> HTML, block level (paragraphs, lists, tables, blockquotes)."""
    _require_markdown()
    if text is None:
        return ""
    return md_lib.markdown(str(text), extensions=["tables", "sane_lists"])


def md_inline(text):
    """Markdown -> HTML with the wrapping <p> stripped, for table cells etc."""
    html = md_block(text).strip()
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return html


def html_table(t):
    """Render {'headers': [...], 'rows': [[...]]} as an HTML <table>.

    Cell contents run through inline markdown, so `code`, **bold** and links
    inside table cells render properly.
    """
    if not t:
        return ""
    headers, align, rows = _squared(t)
    if not headers:
        return ""

    def attr(i):
        a = align[i] if i < len(align) else ""
        return f' class="ta-{a}"' if a else ""

    out = ["<table>", "<thead>", "<tr>"]
    out += [f"<th{attr(i)}>{md_inline(h)}</th>" for i, h in enumerate(headers)]
    out += ["</tr>", "</thead>", "<tbody>"]
    for row in rows:
        out.append("<tr>")
        out += [f"<td{attr(i)}>{md_inline(c)}</td>" for i, c in enumerate(row)]
        out.append("</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


FONT_MIME = {".woff2": "font/woff2", ".woff": "font/woff",
             ".ttf": "font/ttf", ".otf": "font/otf"}
# Filename hints -> (weight, style). Files are matched case-insensitively.
FONT_VARIANTS = [
    ("bolditalic", 700, "italic"), ("boldoblique", 700, "italic"),
    ("italic", 400, "italic"), ("oblique", 400, "italic"),
    ("bold", 700, "normal"), ("medium", 500, "normal"),
    ("regular", 400, "normal"),
]


def build_font_face_css(template_dir, family="Roboto"):
    """Base64-embed any font files found in <template_dir>/fonts/ as @font-face
    rules, so the rendered HTML/PDF looks identical on every machine.

    The reference document was typeset in Roboto. If Roboto isn't installed
    where you render, drop Roboto-Regular/-Bold/-Italic (.woff2 or .ttf) into
    templates/fonts/ and they get inlined here automatically. With no fonts
    present this returns "" and the CSS font stack falls back gracefully.
    """
    import base64
    font_dir = os.path.join(template_dir, "fonts")
    if not os.path.isdir(font_dir):
        return ""
    rules = []
    for path in sorted(glob.glob(os.path.join(font_dir, "*"))):
        ext = os.path.splitext(path)[1].lower()
        if ext not in FONT_MIME:
            continue
        stem = os.path.basename(path).lower()
        weight, style = 400, "normal"
        for hint, w, s in FONT_VARIANTS:
            if hint in stem.replace("-", "").replace("_", ""):
                weight, style = w, s
                break
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:{style};"
            f"font-weight:{weight};font-display:swap;"
            f"src:url(data:{FONT_MIME[ext]};base64,{b64}) format('{ext.lstrip('.')}');}}"
        )
    if rules:
        print(f"  embedded {len(rules)} font file(s) from {font_dir}")
    return "\n".join(rules)


def make_env(template_dir):
    env = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["md_table"] = md_table
    env.filters["html_table"] = html_table
    env.filters["md"] = md_block
    env.filters["mdi"] = md_inline
    env.filters["ensure_rows"] = ensure_rows
    return env


# --------------------------------------------------------------------------
# Output writers
# --------------------------------------------------------------------------

def write(path, content):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"wrote {path}")


def find_chrome():
    for cand in CHROME_CANDIDATES:
        if not cand:
            continue
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
        found = shutil.which(cand)
        if found:
            return found
    # Playwright-managed Chromium (versioned dirs, e.g. chromium-1194/)
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "/opt/pw-browsers",
             os.path.expanduser("~/.cache/ms-playwright")]
    for root in roots:
        for pattern in ("chromium*/chrome-linux/chrome",
                        "chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                        "chromium*/chrome-win/chrome.exe"):
            for hit in sorted(glob.glob(os.path.join(root, pattern)), reverse=True):
                if os.access(hit, os.X_OK):
                    return hit
    # Last resort on WSL: the Windows browser via interop.
    if is_wsl():
        for cand in WSL_CANDIDATES:
            if os.path.isfile(cand):
                return cand
    return None


def html_to_pdf(html_path, pdf_path):
    """Print an HTML file to PDF with headless Chrome — same pipeline the
    reference document was produced with."""
    chrome = find_chrome()
    if not chrome:
        extra = ""
        if is_wsl():
            extra = ("\n         You are on WSL, which usually has no Linux browser. Point at\n"
                     "         the Windows one instead (no install needed):\n"
                     "           export CHROME_BIN='/mnt/c/Program Files/Google/Chrome/Application/chrome.exe'\n"
                     "         Microsoft Edge works identically (same engine):\n"
                     "           export CHROME_BIN='/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'")
        print("warning: no Chrome/Chromium binary found; skipping PDF."
              + extra +
              "\n         Or open the .html and print to PDF from your browser "
              "(Ctrl+P -> Save as PDF, margins: Default, Background graphics: ON).",
              file=sys.stderr)
        return False

    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    win = is_windows_exe(chrome)

    # A Windows browser cannot read WSL paths, so translate both the input URL
    # and the output path. The profile dir goes next to the PDF for the same
    # reason — a /tmp path would be unreachable from the Windows side.
    profile_ctx = None
    if win:
        profile_dir = os.path.join(os.path.dirname(os.path.abspath(pdf_path)),
                                   ".chrome-profile")
        os.makedirs(profile_dir, exist_ok=True)
        arg_profile = to_win_path(profile_dir)
        arg_pdf = to_win_path(pdf_path)
        arg_url = "file:///" + to_win_path(html_path).replace("\\", "/")
    else:
        profile_ctx = tempfile.TemporaryDirectory()
        arg_profile = profile_ctx.name
        arg_pdf = os.path.abspath(pdf_path)
        arg_url = "file://" + os.path.abspath(html_path)

    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={arg_profile}",
        "--no-pdf-header-footer",
        f"--print-to-pdf={arg_pdf}",
        arg_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if profile_ctx:
        profile_ctx.cleanup()
    elif win:
        shutil.rmtree(os.path.join(os.path.dirname(os.path.abspath(pdf_path)),
                                   ".chrome-profile"), ignore_errors=True)

    if not os.path.exists(pdf_path):
        via = " (Windows browser via WSL interop)" if win else ""
        print(f"error: {os.path.basename(chrome)} did not produce a PDF{via}.\n"
              f"{(proc.stderr or proc.stdout)[-800:]}", file=sys.stderr)
        return False
    print(f"wrote {pdf_path}" + ("  (via Windows browser)" if win else ""))
    return True


def md_to_docx(md_path, docx_path, reference_docx=None):
    pandoc = shutil.which("pandoc")
    if not pandoc:
        print("warning: pandoc not found on PATH; skipping DOCX. Use the .html/.pdf "
              "output, or hand the Markdown to the 'docx' skill.", file=sys.stderr)
        return False
    os.makedirs(os.path.dirname(os.path.abspath(docx_path)), exist_ok=True)
    cmd = [pandoc, md_path, "-o", docx_path]
    if reference_docx:
        cmd.append(f"--reference-doc={reference_docx}")
    subprocess.run(cmd, check=True)
    print(f"wrote {docx_path}")
    return True


# --------------------------------------------------------------------------

def lint_config(cfg):
    """Warn about the mistakes that look fine in the rendered PDF.

    These are all things a reader cannot detect but that make the document
    wrong, so they get called out at render time rather than at review time.
    """
    warns = []

    # Unresolved placeholders.
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and "REPLACE_ME" in node:
            warns.append(f"unresolved REPLACE_ME at {path}")
    walk(cfg)

    # Identical commit IDs down a change table's Commit column. In a monorepo
    # this is the signature of pinning every subsystem to the repo HEAD instead
    # of to the commit that last touched each one.
    for part_key in ("part_a", "part_b"):
        part = cfg.get(part_key) or {}
        if part.get("no_changes"):
            # This Part's change table is not rendered at all, so warning about
            # its contents would send someone hunting for a table that isn't in
            # the document.
            continue
        t = part.get("change_table") or {}
        rows = [r for r in (t.get("rows") or []) if r]
        commits = [str(r[0]).strip() for r in rows if len(r) > 1]
        real = [c for c in commits if c and c not in ("—", "-", "n/a", "`REPLACE_ME`")]
        if len(real) > 1 and len(set(real)) == 1:
            warns.append(
                f"{part_key}.change_table: every row has the same commit id ({real[0]}). "
                "Check these were not pinned to the repo HEAD — in a monorepo that is one "
                "commit shared by every directory, so it says nothing. Each subsystem should "
                "carry the commit that last touched IT (build_parts.py does this). "
                "If they genuinely all trace to the same commit, this is fine."
            )

    if warns:
        print("render warnings:", file=sys.stderr)
        for w in warns[:20]:
            print(f"  - {w}", file=sys.stderr)
        if len(warns) > 20:
            print(f"  ... and {len(warns) - 20} more", file=sys.stderr)
        print("  (document still rendered; fix before issuing it)\n", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True,
                    help="release_note.yaml (see config/release_note.example.yaml)")
    ap.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR,
                    help="Directory holding release_note.md.j2 / release_note.html.j2")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-html", default=None)
    ap.add_argument("--out-pdf", default=None)
    ap.add_argument("--out-docx", default=None)
    ap.add_argument("--out-all", default=None, metavar="PREFIX",
                    help="Shorthand: write PREFIX.md, PREFIX.html, PREFIX.pdf and PREFIX.docx")
    ap.add_argument("--reference-docx", default=None,
                    help="pandoc --reference-doc for corporate DOCX styling")
    args = ap.parse_args()

    if args.out_all:
        args.out_md = args.out_md or args.out_all + ".md"
        args.out_html = args.out_html or args.out_all + ".html"
        args.out_pdf = args.out_pdf or args.out_all + ".pdf"
        args.out_docx = args.out_docx or args.out_all + ".docx"

    if not any([args.out_md, args.out_html, args.out_pdf, args.out_docx]):
        # Default to the format that matches the reference document.
        base = os.path.splitext(args.config)[0]
        args.out_html = base + ".html"
        args.out_pdf = base + ".pdf"

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # `appendix` is optional: it exists only when build IDs were extracted from
    # about.html. With none, the document ends after Known Issues.
    required = ("title", "meta", "overview", "part_a", "part_b",
                "test_results", "known_issues")
    missing = [k for k in required if k not in cfg]
    if missing:
        raise SystemExit(f"config missing required top-level key(s): {', '.join(missing)}")

    lint_config(cfg)

    env = make_env(args.template_dir)

    # Markdown (also the source for DOCX)
    md_text = None
    if args.out_md or args.out_docx:
        md_text = env.get_template("release_note.md.j2").render(**cfg)
        if args.out_md:
            write(args.out_md, md_text)

    # HTML (also the source for PDF)
    html_path = args.out_html
    tmp_html = None
    if args.out_html or args.out_pdf:
        ctx = dict(cfg)
        ctx.setdefault("font_face_css", build_font_face_css(args.template_dir))
        html_text = env.get_template("release_note.html.j2").render(**ctx)
        if args.out_html:
            write(args.out_html, html_text)
        else:
            tmp_html = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                                   encoding="utf-8")
            tmp_html.write(html_text)
            tmp_html.close()
            html_path = tmp_html.name

    if args.out_pdf:
        html_to_pdf(html_path, args.out_pdf)
    if tmp_html:
        os.unlink(tmp_html.name)

    if args.out_docx:
        if args.out_md:
            md_to_docx(args.out_md, args.out_docx, args.reference_docx)
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                             encoding="utf-8") as tf:
                tf.write(md_text)
                tmp_md = tf.name
            md_to_docx(tmp_md, args.out_docx, args.reference_docx)
            os.unlink(tmp_md)


if __name__ == "__main__":
    main()
