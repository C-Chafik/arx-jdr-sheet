#!/usr/bin/env python3
"""Assemble the Roll20 sheet: render Jinja2 templates, concatenate CSS."""
import argparse
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
SRC = ROOT / "src"
BUILD = ROOT / "build"

# Concatenation order matters: later files override earlier ones.
CSS_FILES = ["base.css", "base-page.css"]

# Roll20 only loads HTTPS assets; preview uses the local files instead.
ASSET_BASE = "https://raw.githubusercontent.com/C-Chafik/arx-jdr-sheet/main/assets"
PREVIEW_ASSET_BASE = "../assets"

PREVIEW_WRAPPER = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ARX sheet preview</title>
<link rel="stylesheet" href="preview.css">
</head>
<body>
{content}
</body>
</html>
"""


def render_html() -> str:
    env = Environment(loader=FileSystemLoader(SRC / "templates"), keep_trailing_newline=True)
    return env.get_template("sheet.html.j2").render()


def build_css(asset_base: str) -> str:
    parts = [(SRC / "css" / name).read_text(encoding="utf-8") for name in CSS_FILES]
    return "\n".join(parts).replace("{{ASSET_BASE}}", asset_base)


def build() -> None:
    BUILD.mkdir(exist_ok=True)
    html = render_html()
    (BUILD / "sheet.html").write_text(html, encoding="utf-8")
    (BUILD / "sheet.css").write_text(build_css(ASSET_BASE), encoding="utf-8")
    (BUILD / "preview.css").write_text(build_css(PREVIEW_ASSET_BASE), encoding="utf-8")
    (BUILD / "preview.html").write_text(PREVIEW_WRAPPER.format(content=html), encoding="utf-8")
    print("built: build/sheet.html sheet.css preview.html preview.css")


def watch() -> None:
    last = None
    while True:
        current = {p: p.stat().st_mtime for p in SRC.rglob("*") if p.is_file()}
        if current != last:
            # Keep watching through transient errors (half-saved file, Jinja typo).
            try:
                build()
            except Exception as exc:
                print(f"build failed: {exc}")
            last = current
        time.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    (watch if args.watch else build)()
