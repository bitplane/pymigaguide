from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Iterable

from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive

from rich.console import RenderableType, Group
from rich.text import Text
from rich.align import Align

from ..model import (
    Inline,
    Text as TextNode,
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


# ---------- Options / Palette ----------


@dataclass
class FlowOptions:
    word_wrap: bool = True  # AmigaGuide WORDWRAP (soft wrap at width)
    smart_wrap: bool = False  # SMARTWRAP (single \n treated as space)
    default_tab: int = 8  # @TAB n default
    underline_html: bool = True  # honor underline (as underline style)
    show_unknown_inline: bool = False  # render unknowns visibly (debug)


# Amiga-ish named colors -> Rich color names
DEFAULT_PALETTE: Dict[str, str] = {
    "text": "default",
    "background": "default",
    "back": "default",
    "highlight": "cyan",
    "shine": "white",
    "shadow": "grey50",
    "fill": "grey23",
    "filltext": "white",
}


# ---------- Message types ----------


@dataclass
class FlowLinkTarget:
    file: Optional[str]
    node: Optional[str]
    line: Optional[int]


class LinkActivated(Message):
    """Posted by FlowText when a link is clicked."""

    def __init__(self, target: FlowLinkTarget) -> None:
        self.target = target
        super().__init__()


# ---------- Widget ----------


class FlowText(Widget):
    """
    Render AmigaGuide Inline items faithfully enough for TUI:
      - Styles: bold/italic/underline
      - Colors: FG/BG by name; APEN/BPEN best-effort
      - Breaks: LINE, PAR
      - Tabs: @{TAB} with default/custom tab stops
      - Links: clickable labels (emit LinkActivated)
      - Actions: rendered as plain labels (no execution)

    Notes:
      - Alignment (JLEFT/JCENTER/JRIGHT) is applied per paragraph.
      - CODE mode as a strict "no wrap" inline is not supported per-run in Rich;
        we treat it as a style toggle (monospace effect is up to your theme) and
        TODO: we can segment paragraphs to no-wrap blocks later.

      - SMARTWRAP: single newlines turn into spaces unless an explicit @{LINE}
        or paragraph boundary is encountered.
    """

    # Reactive state
    items: reactive[List[Inline] | None] = reactive(None)
    options: reactive[FlowOptions] = reactive(FlowOptions())
    palette: reactive[Dict[str, str]] = reactive(DEFAULT_PALETTE.copy())

    # private: map click IDs to targets
    _link_targets: Dict[str, FlowLinkTarget]

    def __init__(self, *, id: Optional[str] = None, name: Optional[str] = None) -> None:
        super().__init__(id=id, name=name)
        self._link_targets = {}

    # ---- Public API ----

    def set_items(self, items: List[Inline]) -> None:
        self.items = items[:] if items else []

    def set_options(self, opts: FlowOptions) -> None:
        self.options = opts

    def set_palette(self, palette: Dict[str, str]) -> None:
        self.palette = palette

    # ---- Event bridge: click on links ----

    def on_click(self, event) -> None:
        # Rich turns "link <href>" into a click with event.style.meta.get("link")
        # Textual forwards those as clicks with .style and .meta.
        # We'll store "flow:<id>" and look it up.
        meta = getattr(event, "style", None)
        href = None
        if meta and getattr(meta, "meta", None):
            href = meta.meta.get("link")
        if href and href.startswith("flow:"):
            key = href.split(":", 1)[1]
            target = self._link_targets.get(key)
            if target:
                self.post_message(LinkActivated(target))
                event.stop()
                return

    # ---- Render ----

    def render(self) -> RenderableType:
        if not self.items:
            return Text("")

        # Reset click target map each render
        self._link_targets.clear()

        # Build paragraphs with a small state machine
        paragraphs: List[Tuple[str, Text]] = list(self._build_paragraphs(self.items))

        # Wrap each paragraph in alignment
        rendered_blocks: List[RenderableType] = []
        for align, text in paragraphs:
            if align == "center":
                rendered_blocks.append(Align.center(text))
            elif align == "right":
                rendered_blocks.append(Align.right(text))
            else:
                rendered_blocks.append(text)

        return Group(*rendered_blocks)

    # ---- Paragraph builder ----

    def _build_paragraphs(self, items: List[Inline]) -> Iterable[Tuple[str, Text]]:
        # paragraph state
        align = "left"
        lindent = 0
        pari = 0
        tab_stops: Optional[List[int]] = None
        tab_default = max(1, int(self.options.default_tab))

        # inline style state
        bold = False
        italic = False
        underline = False
        code = False  # reserved for future no-wrap
        fg = None
        bg = None

        # SMARTWRAP behavior: collapse single newlines to spaces across TextNodes
        smart = bool(self.options.smart_wrap)
        word_wrap = bool(self.options.word_wrap)

        # builder
        t = Text(no_wrap=not word_wrap, end="")
        col = 0  # current column for tabs
        first_in_para = True

        def flush_para() -> Tuple[str, Text]:
            nonlocal t, col, first_in_para
            # Close any open inline markers? (Rich handles styles per span.)
            out = (align, t)
            # reset for next paragraph
            t = Text(no_wrap=not word_wrap, end="")
            col = 0
            first_in_para = True
            return out

        def apply_style() -> Dict:
            style_parts = []
            if bold:
                style_parts.append("bold")
            if italic:
                style_parts.append("italic")
            if underline and self.options.underline_html:
                style_parts.append("underline")
            # colors
            if fg:
                style_parts.append(self._map_color(fg, "fg"))
            if bg:
                style_parts.append(f"on {self._map_color(bg, 'bg')}")
            return {"style": " ".join(style_parts) if style_parts else None}

        def add_text(s: str) -> None:
            nonlocal col, first_in_para
            if not s:
                return
            # Measure column advance (assumes monospace)
            col += len(s.replace("\n", ""))  # newlines handled elsewhere
            t.append(s, **apply_style())
            first_in_para = False

        def add_spaces(n: int) -> None:
            add_text(" " * max(0, n))

        def next_tab_stop(c: int) -> int:
            if tab_stops:
                for stop in tab_stops:
                    if stop > c:
                        return stop
                # if beyond last, keep adding default tab width
                last = tab_stops[-1] if tab_stops else 0
                if c < last:
                    return last
                # fall through to default spacing
            # default: ceil((c+1)/tab)*tab
            width = tab_default
            return ((c // width) + 1) * width

        # iterate items
        i = 0
        L = len(items)
        while i < L:
            obj = items[i]

            # Breaks
            if isinstance(obj, Break):
                if obj.kind == "line":
                    add_text("\n")
                    col = 0
                else:  # paragraph
                    # flush current paragraph
                    yield flush_para()
                i += 1
                continue

            # Tabs
            if isinstance(obj, TabsChange):
                if obj.set_tabs is not None:
                    # explicit tab stops
                    tab_stops = [n for n in obj.set_tabs if isinstance(n, int) and n > 0]
                elif obj.clear_tabs:
                    tab_stops = None
                elif obj.tab:
                    nxt = next_tab_stop(col)
                    add_spaces(nxt - col)
                i += 1
                continue

            # Paragraph indentation & alignment
            if isinstance(obj, IndentChange):
                if obj.pard:
                    pari = 0
                    lindent = 0
                if obj.lindent is not None:
                    lindent = max(0, int(obj.lindent))
                if obj.pari is not None:
                    pari = max(0, int(obj.pari))
                i += 1
                continue

            if isinstance(obj, AlignChange):
                align = obj.align if obj.align in ("left", "center", "right") else "left"
                i += 1
                continue

            # Colors
            if isinstance(obj, ColorChange):
                if obj.fg:
                    fg = obj.fg
                if obj.bg:
                    bg = obj.bg
                i += 1
                continue

            # Styles
            if isinstance(obj, StyleToggle):
                if obj.style == "bold":
                    bold = obj.on
                elif obj.style == "italic":
                    italic = obj.on
                elif obj.style == "underline":
                    underline = obj.on
                elif obj.style == "code":
                    # TODO: toggle no-wrap per run; for now just mark italic off and keep as-is
                    code = obj.on
                i += 1
                continue

            # Reset styles (UnknownInline with PLAIN/BODY)
            if isinstance(obj, UnknownInline) and obj.args:
                head = obj.args[0].upper()
                if head in ("PLAIN", "PLAINTEXT", "BODY"):
                    bold = italic = underline = False
                    fg = bg = None
                    # keep alignment/indent and tabs; they are paragraph attributes
                    i += 1
                    continue

            # Links
            if isinstance(obj, Link):
                label = obj.label or ""
                href_key = self._register_link(obj)
                add_text("")
                # Insert initial indents if first content in paragraph
                if first_in_para and (lindent or pari):
                    add_spaces(lindent + pari)
                # stylize as clickable
                style = apply_style()
                base = style.get("style") or ""
                link_style = (base + " " if base else "") + f"link flow:{href_key}"
                t.append(label, style=link_style)
                col += len(label)
                first_in_para = False
                i += 1
                continue

            # Actions (render label as plain text for now)
            if isinstance(obj, Action):
                # TODO: turn into a clickable action span behind a policy gate
                label = obj.label or ""
                if first_in_para and (lindent or pari):
                    add_spaces(lindent + pari)
                add_text(label)
                i += 1
                continue

            # Plain text
            if isinstance(obj, TextNode):
                s = obj.text or ""
                if smart:
                    # collapse single newlines to spaces, keep double as paragraph
                    # we don't split paragraphs here; use Break(PAR) for that.
                    s = s.replace("\r\n", "\n")
                    s = s.replace("\n", " ")
                if first_in_para and (lindent or pari):
                    add_spaces(lindent + pari)
                add_text(s)
                i += 1
                continue

            # Unknown inline
            if isinstance(obj, UnknownInline):
                if self.options.show_unknown_inline:
                    add_text(f"[[@{{{obj.raw}}}]]")
                i += 1
                continue

            # Fallback
            i += 1

        # flush final paragraph
        yield flush_para()

    # ---- helpers ----

    def _register_link(self, link: Link) -> str:
        key = f"{len(self._link_targets)}"
        self._link_targets[key] = FlowLinkTarget(
            file=link.target_file,
            node=link.target_node,
            line=link.line,
        )
        return key

    def _map_color(self, spec: str, kind: str) -> str:
        """
        Map AmigaGuide color names or APEN/BPEN specs to Rich colors.
        spec examples: 'text', 'highlight', 'APEN:2'
        """
        s = (spec or "").strip().lower()
        # APEN/BPEN:<n>
        if s.startswith("apen:") or s.startswith("bpen:"):
            # crude mapping of indices to a small palette; project can provide a better one
            try:
                idx = int(s.split(":", 1)[1])
            except Exception:
                idx = 0
            # simple 0-7 mapping
            table = [
                "default",
                "bright_white",
                "bright_cyan",
                "bright_magenta",
                "bright_green",
                "bright_yellow",
                "bright_blue",
                "bright_red",
            ]
            return table[idx % len(table)]
        # named
        return self.palette.get(s, s or "default")
