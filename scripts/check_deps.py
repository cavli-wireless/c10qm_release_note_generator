#!/usr/bin/env python3
"""
check_deps.py — Report which Python packages and external tools the pipeline
needs, which are missing, and the exact command to fix it on this machine.

Run standalone, or let generate.sh call it as a preflight:
    python3 scripts/check_deps.py
    python3 scripts/check_deps.py --stage fetch     # only what fetching needs

Exit code 0 = everything required is present, 1 = something required is missing.

Why this exists: on Ubuntu 23.04+ / Debian 12+ (including WSL), PEP 668 makes
`pip install` fail with "externally-managed-environment", which is confusing the
first time you hit it. This prints the three ways out, in the order most people
should try them.
"""
import argparse
import importlib
import os
import shutil
import sys

# module name -> (pip name, apt name, which stages need it)
PY_DEPS = {
    "yaml":     ("PyYAML",   "python3-yaml",     {"fetch", "table", "render"}),
    "jinja2":   ("Jinja2",   "python3-jinja2",   {"render"}),
    "markdown": ("Markdown", "python3-markdown", {"render"}),
    "requests": ("requests", "python3-requests", {"api"}),
}

# external binaries: name -> (what it's for, required?)
BIN_DEPS = {
    "git":    ("reading commits from local clones", {"fetch"}),
    "pandoc": ("optional .docx output only",        set()),
}

CHROME_NAMES = ["chromium", "chromium-browser", "google-chrome",
                "google-chrome-stable", "chrome"]

WSL_BROWSERS = [
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]


def _is_wsl():
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "fetch", "table", "render", "api"],
                    help="Only check what this stage needs (default: all)")
    args = ap.parse_args()

    want = ({"fetch", "table", "render"} if args.stage == "all"
            else {args.stage})

    missing_py, missing_bin, notes = [], [], []

    print("Python packages:")
    for mod, (pip_name, apt_name, stages) in PY_DEPS.items():
        needed = bool(stages & want)
        try:
            importlib.import_module(mod)
            print(f"  [ok]      {mod}")
        except ImportError:
            if needed:
                print(f"  [MISSING] {mod}  ({pip_name}) — required")
                missing_py.append((pip_name, apt_name))
            else:
                print(f"  [ - ]     {mod}  ({pip_name}) — not needed for this stage")

    print("\nExternal tools:")
    for binary, (purpose, stages) in BIN_DEPS.items():
        found = shutil.which(binary)
        needed = bool(stages & want)
        if found:
            print(f"  [ok]      {binary}  ({purpose})")
        elif needed:
            print(f"  [MISSING] {binary}  ({purpose}) — required")
            missing_bin.append(binary)
        else:
            print(f"  [ - ]     {binary}  ({purpose})")

    # Use the renderer's own resolver so the preflight can never disagree with
    # what actually happens at render time (it also knows about Playwright's
    # bundled Chromium and, on WSL, the Windows browser).
    chrome = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from render_release_note import find_chrome
        found = find_chrome()
        if found:
            suffix = ""
            if found.lower().endswith(".exe"):
                suffix = "  (Windows browser via WSL — used automatically)"
            elif os.environ.get("CHROME_BIN") == found:
                suffix = "  (from $CHROME_BIN)"
            chrome = found + suffix
    except Exception:
        chrome = next((c for c in CHROME_NAMES if shutil.which(c)), None)

    if chrome:
        print(f"  [ok]      {chrome}  (PDF output)")
    else:
        print("  [ - ]     chrome/chromium  (PDF output)")
        if _is_wsl():
            notes.append(
                "No browser found, so --out-pdf will be skipped.\n"
                "    You are on WSL. Installing a Linux browser is usually NOT worth it here\n"
                "    (chromium is a snap on Ubuntu 24.04 and snapd does not run in WSL by\n"
                "    default). Point at the Windows browser instead — no install needed:\n"
                "      export CHROME_BIN='/mnt/c/Program Files/Google/Chrome/Application/chrome.exe'\n"
                "    Edge is the same engine and ships with Windows:\n"
                "      export CHROME_BIN='/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'\n"
                "    Add that line to ~/.bashrc to make it stick."
            )
        else:
            notes.append(
                "No Chrome/Chromium found, so --out-pdf will be skipped.\n"
                "    Install one (e.g. sudo apt install -y chromium), set CHROME_BIN to a\n"
                "    browser binary, or open the generated .html and print to PDF from your\n"
                "    browser (margins: Default, Background graphics: ON)."
            )

    if missing_py:
        pip_names = " ".join(n for n, _ in missing_py)
        apt_names = " ".join(a for _, a in missing_py)
        print(f"\nMissing Python packages: {pip_names}")
        print("\nOn Ubuntu/Debian/WSL, `pip install` may refuse with")
        print("'externally-managed-environment' (PEP 668). Pick one:")
        print(f"\n  1. System packages (recommended, no pip involved):")
        print(f"       sudo apt install -y {apt_names}")
        print(f"\n  2. A virtualenv (no sudo needed):")
        print(f"       python3 -m venv .venv")
        print(f"       .venv/bin/pip install {pip_names}")
        print(f"       # then run the pipeline with:  PYTHON=.venv/bin/python ./scripts/generate.sh ...")
        print(f"       # (if venv is unavailable:  sudo apt install -y python3-venv)")
        print(f"\n  3. Override the protection (quickest, slightly messier):")
        print(f"       pip3 install --break-system-packages {pip_names}")

    if missing_bin:
        print(f"\nMissing tools: {' '.join(missing_bin)}")
        print(f"  sudo apt install -y {' '.join(missing_bin)}")

    for n in notes:
        print(f"\nNote: {n}")

    if missing_py or missing_bin:
        print("\n=> not ready")
        return 1
    print("\n=> all required dependencies present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
