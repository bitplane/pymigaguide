from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict

from textual.widgets import Markdown
from textual.containers import Container
from textual.message import Message

from ..model import GuideDocument
from ..writer.markdown import MarkdownRenderer
from .guidetoolbar import GuideToolbar, NavTargets


# --- LinkTarget --------------------------------------------------------------


@dataclass
class LinkTarget:
    file: Optional[str]
    node: Optional[str]
    line: Optional[int]


_LINK_RE = re.compile(
    r"""
    ^
    (?:
        (?P<file>[^#?]+?)     # optional file before anchor
        (?:\#(?P<anchor>[^?]+))?
      |
        \#(?P<anchor2>[^?]+)  # or just an anchor
    )
    (?:\?line=(?P<line>\d+))?
    $
    """,
    re.VERBOSE,
)


def parse_href(href: str) -> LinkTarget:
    m = _LINK_RE.match(href.strip())
    if not m:
        # Fallback: treat as external file
        return LinkTarget(file=href, node=None, line=None)
    file = m.group("file")
    anchor = m.group("anchor") or m.group("anchor2")
    line = int(m.group("line")) if m.group("line") else None
    # anchor corresponds to a node slug; we don't store slugs, so pass raw and
    # let GuideView map slug->node by scanning titles/names
    return LinkTarget(file=file, node=anchor, line=line)


# --- GuideView ---------------------------------------------------------------


class GuideView(Container):
    """
    High-level viewer: holds a Markdown widget, manages navigation/history,
    and resolves links between nodes (and across files later).
    """

    DEFAULT_CSS = """
    GuideView {
        layout: vertical;
    }
    GuideView > Markdown {
        height: 1fr;
    }
    """

    class LinkClicked(Message):
        def __init__(self, target: LinkTarget) -> None:
            self.target = target
            super().__init__()

    def __init__(self, *, id: Optional[str] = None):
        super().__init__(id=id)
        self._doc: Optional[GuideDocument] = None
        self._docs_cache: Dict[Path, GuideDocument] = {}
        self._primary_path: Optional[Path] = None
        self._renderer: Optional[MarkdownRenderer] = None

        # history of (file_path, node_name)
        self._history: list[tuple[Optional[Path], str]] = []
        self._history_index: int = -1

        # reverse anchor lookup cache: slug -> node name
        self._slug_to_node: Dict[str, str] = {}

    def set_renderer(self, renderer: MarkdownRenderer) -> None:
        self._renderer = renderer

    def set_primary_path(self, path: Path) -> None:
        self._primary_path = path

    def set_document(self, doc: GuideDocument) -> None:
        self._doc = doc
        self._docs_cache[self._primary_path or Path("<memory>")] = doc
        self._rebuild_slug_map()

    def compose(self):
        yield GuideToolbar()
        yield Markdown("")

    # --- Navigation API ---

    def goto(self, file: Optional[str], node: Optional[str], line: Optional[int]) -> None:
        """
        Navigate to (file,node). If file is None or .guide is current, use current doc.
        node may be a slug; map to actual node name if possible.
        """
        doc, base_path = self._resolve_document(file)
        if doc is None:
            self.notify(f"Cannot open: {file}", severity="error")
            return

        node_name = self._resolve_node_name(doc, node)
        if node_name is None:
            self.notify(f"Node not found: {node}", severity="warning")
            return

        self._push_history(base_path, node_name)
        self._render_node(doc, node_name)

        # TODO: support precise scroll-to-line after Textual exposes per-line anchors.
        # For now, no-op (you can add a find() and scroll_to once FlowText exists).

    def back(self) -> None:
        if self._history_index > 0:
            self._history_index -= 1
            path, node = self._history[self._history_index]
            doc = self._docs_cache.get(path or Path("<memory>"))
            if doc:
                self._render_node(doc, node)

    def forward(self) -> None:
        if self._history_index + 1 < len(self._history):
            self._history_index += 1
            path, node = self._history[self._history_index]
            doc = self._docs_cache.get(path or Path("<memory>"))
            if doc:
                self._render_node(doc, node)

    # --- Internals ---

    def _render_node(self, doc: GuideDocument, node_name: str) -> None:
        mdw = self.query_one(Markdown)
        if not self._renderer:
            mdw.update(f"# {node_name}\n\n*(no renderer configured)*")
            return
        # Render only this node to markdown
        rendered = self._renderer.render_document(doc)
        text = rendered.get(node_name, f"# {node_name}\n\n*(empty)*")
        mdw.update(text)
        # Update toolbar targets
        tb = self.query_one(GuideToolbar)
        tb.set_targets(self._compute_targets_for(doc, node_name))
        # Rebuild slugs from this document for in-page links
        self._rebuild_slug_map(doc)

    def on_guide_toolbar_nav_requested(self, message: GuideToolbar.NavRequested) -> None:
        """Handle navigation requests from the toolbar."""
        if message.kind == "prev":
            self.back()
        elif message.kind == "next":
            self.forward()
        elif message.target:
            self.goto(file=None, node=message.target, line=None)
        message.stop()

    def _compute_targets_for(self, doc: GuideDocument, node_name: str) -> NavTargets:
        """Compute navigation targets for the toolbar based on the current node."""
        node = None
        for n in doc.nodes:
            if n.name == node_name:
                node = n
                break
        if not node:
            return NavTargets(title="Unknown Node")

        # Find prev/next in document order
        node_names = [n.name for n in doc.nodes]
        try:
            idx = node_names.index(node_name)
            prev_node = node_names[idx - 1] if idx > 0 else None
            next_node = node_names[idx + 1] if idx < len(node_names) - 1 else None
        except ValueError:
            prev_node, next_node = None, None

        # Use node-specific overrides, then global, then computed
        return NavTargets(
            title=node.attrs.title or node.name,
            prev=node.attrs.prev or prev_node,
            next=node.attrs.next or next_node,
            toc=node.attrs.toc or doc.meta.index_node,  # Assuming TOC maps to global index_node
            index=node.attrs.index or doc.meta.index_node,
            help=node.attrs.help or doc.meta.help_node,
        )

    def _resolve_document(self, file: Optional[str]) -> tuple[Optional[GuideDocument], Optional[Path]]:
        """
        file can be:
          - None or "" -> use current (primary) document
          - 'foo.md'   -> corresponding 'foo.guide' next to primary
          - 'foo.guide' or path -> open and cache
          - anything else (image etc.) -> return (None, None) so caller can handle externals
        """
        if file in (None, "", "#"):
            return self._doc, self._primary_path
        # map .md back to .guide to support markdown links
        target = Path(file)
        if target.suffix.lower() == ".md":
            target = target.with_suffix(".guide")

        # If it's a bare filename, resolve relative to primary
        if not target.is_absolute() and self._primary_path:
            target = (self._primary_path.parent / target).resolve()

        if target.suffix.lower() != ".guide":
            # Likely an asset (image, text). Caller should handle externally.
            return None, None

        if target in self._docs_cache:
            return self._docs_cache[target], target

        try:
            from ..parser import AmigaGuideParser  # local import to avoid cycles

            parser = AmigaGuideParser()
            doc = parser.parse_file(target)
        except Exception as e:
            self.notify(f"Failed to load {target.name}: {e}", severity="error")
            return None, None

        self._docs_cache[target] = doc
        return doc, target

    def _resolve_node_name(self, doc: GuideDocument, maybe_slug: Optional[str]) -> Optional[str]:
        # If None, pick MAIN or first
        if not maybe_slug:
            for n in doc.nodes:
                if n.name.upper() == "MAIN":
                    return n.name
            return doc.nodes[0].name if doc.nodes else None

        # Direct name hit?
        for n in doc.nodes:
            if n.name == maybe_slug:
                return n.name

        # Slugify against names and titles
        slug = self._slug(maybe_slug)
        for n in doc.nodes:
            if self._slug(n.name) == slug:
                return n.name
            title = n.attrs.title or ""
            if title and self._slug(title) == slug:
                return n.name

        return None

    def _push_history(self, path: Optional[Path], node_name: str) -> None:
        # Truncate forward history
        if self._history_index + 1 < len(self._history):
            self._history = self._history[: self._history_index + 1]
        self._history.append((path, node_name))
        self._history_index = len(self._history) - 1

    def _rebuild_slug_map(self, doc: Optional[GuideDocument] = None) -> None:
        self._slug_to_node.clear()
        d = doc or self._doc
        if not d:
            return
        for n in d.nodes:
            self._slug_to_node[self._slug(n.name)] = n.name
            if n.attrs.title:
                self._slug_to_node[self._slug(n.attrs.title)] = n.name

    @staticmethod
    def _slug(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return re.sub(r"-+", "-", s).strip("-")

    # --- Markdown link interception ---

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """
        Intercept Markdown links and navigate within guides.
        """
        href = event.href or ""
        target = parse_href(href)

        # Internal node link? (no file)
        if target.file is None and target.node:
            self.goto(file=None, node=target.node, line=target.line)
            event.prevent_default()
            event.stop()
            return

        # Link to another guide (foo.md -> foo.guide) + optional #node
        if target.file and target.file.lower().endswith((".md", ".guide")):
            self.goto(file=target.file, node=target.node, line=target.line)
            event.prevent_default()
            event.stop()
            return

        # Otherwise let Markdown/OS handle it (assets / external URLs)
        # You can plug an AssetView here later.
