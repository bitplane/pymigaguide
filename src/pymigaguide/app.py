from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

# Local package imports
from .parser import AmigaGuideParser
from .model import GuideDocument
from .markdown import MarkdownRenderer  # your renderer -> Markdown text
from .widgets.guideview import GuideView


class GuideApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("b", "back", "Back"),
        ("f", "forward", "Forward"),
    ]

    def __init__(self, guide_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._guide_path = Path(guide_path) if guide_path else None
        self._doc: Optional[GuideDocument] = None
        self._renderer = MarkdownRenderer()

    def compose(self) -> ComposeResult:
        yield Header()
        yield GuideView(id="body")
        yield Footer()

    def on_mount(self) -> None:
        # Allow passing file via CLI
        if self._guide_path is None and len(sys.argv) > 1:
            self._guide_path = Path(sys.argv[1])

        if not self._guide_path or not self._guide_path.exists():
            self.bell()
            self.notify("Pass a .guide file path.", severity="warning")
            return

        parser = AmigaGuideParser()
        self._doc = parser.parse_file(self._guide_path)

        view = self.query_one(GuideView)
        view.set_renderer(self._renderer)
        view.set_primary_path(self._guide_path)
        view.set_document(self._doc)

        # Go to first node (MAIN if present; else first)
        start_node = self._pick_start_node(self._doc)
        view.goto(file=None, node=start_node, line=None)

    def _pick_start_node(self, doc: GuideDocument) -> str:
        names = [n.name for n in doc.nodes]
        if "MAIN" in (n.upper() for n in names):
            # find original case
            for n in names:
                if n.upper() == "MAIN":
                    return n
        return names[0]

    # History actions
    def action_back(self) -> None:
        self.query_one(GuideView).back()

    def action_forward(self) -> None:
        self.query_one(GuideView).forward()


def main():
    guide_path = None
    if len(sys.argv) > 1:
        guide_path = sys.argv[1]
    app = GuideApp(guide_path=guide_path)
    app.run()


if __name__ == "__main__":
    main()
