#!/usr/bin/env python3
from __future__ import annotations

import argparse
from .writer.json import dump_json
from .writer.markdown import MarkdownRenderer
from .writer.html import HtmlRenderer
from .writer.txt import TxtRenderer
import sys
from pathlib import Path

try:
    import chardet  # type: ignore
except Exception:
    print("ERROR: chardet is required. Install with: pip install chardet", file=sys.stderr)
    raise

# Local imports (same folder)
from .parser import AmigaGuideParser


def detect_and_decode(data: bytes) -> tuple[str, str]:
    """
    Detect encoding with chardet and decode to a Python str (UTF-8 internally).
    Returns (text, detected_encoding).
    """
    guess = chardet.detect(data) or {}
    enc = guess.get("encoding") or "utf-8"
    # Some detectors return weird labels; normalize/try a couple fallbacks.
    tried = []
    for candidate in (enc, "utf-8", "latin-1"):
        try:
            text = data.decode(candidate, errors="strict")
            return text, candidate
        except UnicodeDecodeError:
            tried.append(candidate)
            continue
    # Last resort: decode with replacement to avoid crashing
    text = data.decode(enc, errors="replace")
    return text, f"{enc} (with replacements)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AmigaGuide CLI: detect encoding, convert to UTF-8, parse, and optionally dump JSON."
    )
    p.add_argument("file", type=Path, help="Path to .guide file")
    p.add_argument(
        "--dump",
        action="store_true",
        help="Dump the parsed model (use --format to choose output format).",
    )
    p.add_argument(
        "--format",
        choices=["json", "markdown", "html", "txt"],
        default="json",
        help="Output format for --dump (default: json).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential stderr messages (like encoding info).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 2
    if not args.file.is_file():
        print(f"ERROR: not a regular file: {args.file}", file=sys.stderr)
        return 2

    # Read as binary
    data = args.file.read_bytes()

    # Detect + decode
    text, detected = detect_and_decode(data)
    if not args.quiet:
        print(f"[info] detected encoding: {detected}", file=sys.stderr)

    # Parse
    parser = AmigaGuideParser()
    doc = parser.parse_text(text)

    # Dump if requested
    if args.dump:
        if args.format == "json":
            print(dump_json(doc))
        elif args.format == "markdown":
            renderer = MarkdownRenderer()
            rendered_nodes = renderer.render_document(doc)
            for node_name, content in rendered_nodes.items():
                print(f"--- NODE: {node_name} ---\n{content}")
        elif args.format == "html":
            renderer = HtmlRenderer()
            rendered_nodes = renderer.render_document(doc)
            # For HTML, we might want to output a full HTML page or just the body content
            # For simplicity, let's just concatenate all node HTML for now
            print("<!DOCTYPE html>\n<html>\n<head><title>Guide Document</title></head><body>")
            for node_name, content in rendered_nodes.items():
                print(f'<div id="{node_name}">\n{content}\n</div>')
            print("</body>\n</html>")
        elif args.format == "txt":
            renderer = TxtRenderer()
            rendered_nodes = renderer.render_document(doc)
            for node_name, content in rendered_nodes.items():
                print(f"--- NODE: {node_name} ---\n{content}")
        else:
            print(f"ERROR: unsupported format: {args.format}", file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
