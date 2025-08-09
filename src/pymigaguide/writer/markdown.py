from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..model import (
    GuideDocument,
    GuideNode,
    Inline,
    Text,
    Link,
    Action,
    StyleToggle,
    ColorChange,
    AlignChange,
    IndentChange,
    TabsChange,
    Break,
    UnknownInline,
)


# --------- helpers ---------

_slug_non_alnum = re.compile(r"[^a-z0-9]+")
_collapse_dashes = re.compile(r"-+")


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = _slug_non_alnum.sub("-", s)
    s = _collapse_dashes.sub("-", s)
    return s.strip("-")


def md_escape(text: str) -> str:
    # Escape special Markdown characters minimally
    # (we'll still allow backticks inside code spans, handled separately)
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("#", "\\#")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace(">", "\\>")
        .replace("|", "\\|")
    )


def fence_backticks(s: str) -> str:
    """
    Wrap s in a backtick fence that doesn't conflict with backticks inside s.
    Uses inline-style by default (not code blocks).
    """
    backtick_runs = re.findall(r"`+", s)
    if not backtick_runs:
        return f"`{s}`"
    longest = max(backtick_runs, key=len)
    fence = "`" * (len(longest) + 1)
    # If the string starts/ends with space, add a space inside fence to be safe
    prefix = " " if s and s[0].isspace() else ""
    suffix = " " if s and s[-1].isspace() else ""
    return f"{fence}{prefix}{s}{suffix}{fence}"


# --------- renderer ---------


@dataclass
class MarkdownOptions:
    heading_level: int = 1  # # heading per node
    file_suffix: str = ".md"  # links to other guides
    tab_spaces: int = 4  # how many spaces for @{TAB}
    paragraph_blank_lines: int = 1  # blank lines for PAR
    line_break: str = "\n"  # soft line break (we just use newline)
    underline_html: bool = True  # use <u> for underline
    include_node_title: bool = True  # emit H1/H2... title at top of node


class MarkdownRenderer:
    def __init__(self, options: Optional[MarkdownOptions] = None) -> None:
        self.opt = options or MarkdownOptions()

    # --- Public API ---

    def render_document(self, doc: GuideDocument) -> Dict[str, str]:
        """
        Returns a dict: { node_name: markdown }
        """
        out: Dict[str, str] = {}
        for node in doc.nodes:
            out[node.name] = self.render_node(node)
        return out

    def render_node(self, node: GuideNode) -> str:
        parts: List[str] = []

        if self.opt.include_node_title:
            title = node.attrs.title or node.name
            level = max(1, min(6, self.opt.heading_level))
            parts.append(f'{"#" * level} {md_escape(title)}')

        parts.append(self._render_inline_stream(node.content).rstrip())
        return "\n".join(parts).rstrip() + "\n"

    # --- Internals ---

    def _render_inline_stream(self, items: List[Inline]) -> str:
        out: List[str] = []
        # style state
        bold = False
        italic = False
        underline = False
        code = False
        code_buf: List[str] = []

        def flush_code():
            nonlocal code_buf
            if code_buf:
                segment = "".join(code_buf)
                out.append(fence_backticks(segment))
                code_buf = []

        for obj in items:
            # Breaks first (since they’re structural)
            if isinstance(obj, Break):
                if code:
                    # code stays inline; we still respect breaks as real newlines
                    code_buf.append("\n" if obj.kind == "line" else "\n\n")
                else:
                    out.append("\n" if obj.kind == "line" else "\n\n")
                continue

            # Tabs
            if isinstance(obj, TabsChange) and obj.tab:
                if code:
                    code_buf.append(" " * self.opt.tab_spaces)
                else:
                    out.append(" " * self.opt.tab_spaces)
                continue

            # Style resets signaled via UnknownInline for PLAIN/PLAINTEXT/BODY
            if isinstance(obj, UnknownInline) and obj.args:
                kw = obj.args[0].upper()
                if kw in ("PLAIN", "PLAINTEXT", "BODY"):
                    # close open styles in sensible order
                    if code:
                        flush_code()
                        code = False
                    if underline and self.opt.underline_html:
                        out.append("</u>")
                        underline = False
                    if italic:
                        out.append("*")
                        italic = False
                    if bold:
                        out.append("**")
                        bold = False
                    continue

            # Style toggles
            if isinstance(obj, StyleToggle):
                if obj.style == "bold":
                    if code:
                        code_buf.append("**" if not bold else "**")
                    else:
                        out.append("**" if not bold else "**")
                    bold = obj.on if obj.on else False if bold else False
                    continue
                if obj.style == "italic":
                    if code:
                        code_buf.append("*" if not italic else "*")
                    else:
                        out.append("*" if not italic else "*")
                    italic = obj.on if obj.on else False if italic else False
                    continue
                if obj.style == "underline":
                    if self.opt.underline_html:
                        if obj.on and not underline:
                            out.append("<u>")
                            underline = True
                        elif not obj.on and underline:
                            out.append("</u>")
                            underline = False
                    # If not using HTML, ignore underline
                    continue
                if obj.style == "code":
                    if code:
                        # closing CODE
                        flush_code()
                        code = False
                    else:
                        # opening CODE
                        code = True
                    continue

            # Ignored visual controls in Markdown phase
            if isinstance(obj, (ColorChange, AlignChange, IndentChange)):
                # could emit HTML spans in the future; ignore for now
                continue

            # Links
            if isinstance(obj, Link):
                label = md_escape(obj.label)
                href = self._mk_href(obj)
                link_md = f"[{label}]({href})"
                if code:
                    code_buf.append(link_md)
                else:
                    out.append(link_md)
                continue

            # Actions (SYSTEM/RX/RXS/BEEP/CLOSE/QUIT): render as plain label
            if isinstance(obj, Action):
                label = md_escape(obj.label)
                if code:
                    code_buf.append(label)
                else:
                    out.append(label)
                continue

            # Plain text
            if isinstance(obj, Text):
                text = obj.text
                if not code:
                    out.append(md_escape(text))
                else:
                    code_buf.append(text)
                continue

            # Unknowns: drop silently (or show raw)
            if isinstance(obj, UnknownInline):
                # If you want to preserve, uncomment:
                # out.append(f"<!-- @{obj.raw} -->")
                continue

        # Close any open styles at end of stream
        if code:
            flush_code()
            code = False
        if underline and self.opt.underline_html:
            out.append("</u>")
        if italic:
            out.append("*")
        if bold:
            out.append("**")

        return "".join(out)

    def _mk_href(self, link: Link) -> str:
        """
        Build a Markdown link target:
        - node-only:               "#<node-slug>"
        - file+node:               "<file><suffix>#<node-slug>"
        - file-only (non-guide):   "<file>" (pass-through)
        - +line: append ?line=N
        """
        node = link.target_node or ""
        file = link.target_file or ""
        line = link.line

        # heuristic: if file has an extension and it's not .guide, treat as asset
        if file and not file.lower().endswith(".guide"):
            base = file
            if node and node.lower() != "main":
                base = f"{base}#{slugify(node)}"
            if line:
                sep = "&" if "#" in base and "?" in base else "?"
                base = f"{base}{sep}line={line}"
            return base

        if file:
            base = re.sub(r"\.guide$", "", file, flags=re.IGNORECASE) + self.opt.file_suffix
            anchor = f"#{slugify(node or 'main')}" if node else ""
            if line:
                return f"{base}{anchor}?line={line}"
            return f"{base}{anchor}"

        # node only
        anchor = f"#{slugify(node or 'main')}"
        if line:
            return f"{anchor}?line={line}"
        return anchor
