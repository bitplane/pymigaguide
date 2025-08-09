from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static


@dataclass
class NavTargets:
    title: str
    prev: Optional[str] = None
    next: Optional[str] = None
    toc: Optional[str] = None
    index: Optional[str] = None
    help: Optional[str] = None


class GuideToolbar(Horizontal):
    """Top navigation bar for AmigaGuide docs."""

    DEFAULT_CSS = """
    GuideToolbar {
        height: 3;
        dock: top;
        padding: 0 1;
        background: $boost;
    }
    GuideToolbar > .title {
        content-align: left middle;
        width: 1fr;
    }
    GuideToolbar Button {
        margin: 0 1;
    }
    """

    class NavRequested(Message):
        """Emitted when a toolbar button requests navigation."""

        def __init__(self, kind: str, target: Optional[str]) -> None:
            self.kind = kind  # "prev"|"next"|"toc"|"index"|"help"
            self.target = target
            super().__init__()

    # current targets (node names or None)
    targets: reactive[NavTargets | None] = reactive(None)

    def compose(self):
        yield Button("◀ Prev", id="prev", variant="default")
        yield Button("▶ Next", id="next", variant="default")
        yield Button("Contents", id="toc", variant="primary")
        yield Button("Index", id="index", variant="primary")
        yield Button("Help", id="help", variant="primary")
        yield Static("", classes="title", id="title")

    def set_targets(self, nt: NavTargets) -> None:
        self.targets = nt

    def watch_targets(self, nt: NavTargets | None) -> None:
        prev_b = self.query_one("#prev", Button)
        next_b = self.query_one("#next", Button)
        toc_b = self.query_one("#toc", Button)
        idx_b = self.query_one("#index", Button)
        help_b = self.query_one("#help", Button)
        title = self.query_one("#title", Static)

        if nt is None:
            for b in (prev_b, next_b, toc_b, idx_b, help_b):
                b.disabled = True
            title.update("")
            return

        title.update(nt.title or "")
        prev_b.disabled = nt.prev is None
        next_b.disabled = nt.next is None
        toc_b.disabled = nt.toc is None
        idx_b.disabled = nt.index is None
        help_b.disabled = nt.help is None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self.targets:
            return
        bid = event.button.id or ""
        if bid == "prev":
            self.post_message(self.NavRequested("prev", self.targets.prev))
        elif bid == "next":
            self.post_message(self.NavRequested("next", self.targets.next))
        elif bid == "toc":
            self.post_message(self.NavRequested("toc", self.targets.toc))
        elif bid == "index":
            self.post_message(self.NavRequested("index", self.targets.index))
        elif bid == "help":
            self.post_message(self.NavRequested("help", self.targets.help))
