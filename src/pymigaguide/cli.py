#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import chardet  # type: ignore
except Exception:
    print("ERROR: chardet is required. Install with: pip install chardet", file=sys.stderr)
    raise

# Local imports (same folder)
from parser import AmigaGuideParser
from models import GuideDocument  # for typing / duck-typing of Pydantic object


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


def dump_json(doc: GuideDocument) -> str:
    """
    Pydantic v2 uses model_dump_json; v1 uses .json().
    Support both without caring which is installed.
    """
    # Try v2
    try:
        return doc.model_dump_json(indent=2)
    except AttributeError:
        pass
    # Fall back to v1
    try:
        return doc.json(indent=2)
    except AttributeError:
        # absolute last resort: use dict + json.dumps
        try:
            data = doc.model_dump()
        except AttributeError:
            data = doc.dict()
        return json.dumps(data, indent=2, ensure_ascii=False)


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
        choices=["json"],
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
        else:
            print(f"ERROR: unsupported format: {args.format}", file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
