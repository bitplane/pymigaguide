from __future__ import annotations

from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel


# --------- Top-level --------- #


class GuideMetadata(BaseModel):
    database: Optional[str] = None  # @DATABASE
    author: Optional[str] = None  # @AUTHOR
    version: Optional[str] = None  # @$VER: ...
    copyright: Optional[str] = None  # @(c) ...
    index_node: Optional[str] = None  # @INDEX  (global)
    help_node: Optional[str] = None  # @HELP   (global)
    font_name: Optional[str] = None  # @FONT name size (global)
    font_size: Optional[int] = None
    wordwrap: Optional[bool] = None  # @WORDWRAP
    smartwrap: Optional[bool] = None  # @SMARTWRAP
    tab_width: Optional[int] = None  # @TAB n
    width_hint: Optional[int] = None  # @WIDTH
    height_hint: Optional[int] = None  # @HEIGHT
    onopen_script: Optional[str] = None  # @ONOPEN (global)
    onclose_script: Optional[str] = None  # @ONCLOSE (global)
    macros: Dict[str, str] = {}  # @MACRO name expansion (global)
    # anything else you want to stash:
    extras: Dict[str, Any] = {}


class GuideDocument(BaseModel):
    meta: GuideMetadata
    nodes: List["GuideNode"]


# --------- Nodes --------- #


class NodeAttributes(BaseModel):
    title: Optional[str] = None  # @TITLE or @NODE "title"
    toc: Optional[str] = None  # @TOC
    next: Optional[str] = None  # @NEXT
    prev: Optional[str] = None  # @PREV
    index: Optional[str] = None  # @INDEX (node-local)
    help: Optional[str] = None  # @HELP  (node-local)
    font_name: Optional[str] = None  # @FONT (node-local)
    font_size: Optional[int] = None
    proportional: Optional[bool] = None  # @PROPORTIONAL
    wordwrap: Optional[bool] = None  # @WORDWRAP
    smartwrap: Optional[bool] = None  # @SMARTWRAP
    tab_width: Optional[int] = None  # @TAB
    onopen_script: Optional[str] = None  # @ONOPEN (node-local)
    onclose_script: Optional[str] = None  # @ONCLOSE (node-local)
    keywords: Optional[str] = None  # @KEYWORDS
    macros: Dict[str, str] = {}  # @MACRO (node-local)
    embeds: List[str] = []  # @EMBED path(s)
    extras: Dict[str, Any] = {}  # stash unknowns


class GuideNode(BaseModel):
    name: str
    attrs: NodeAttributes = NodeAttributes()
    content: List["Inline"] = []  # Flattened inline stream


# --------- Inline content (inside nodes) --------- #


class Text(BaseModel):
    text: str


class Link(BaseModel):
    label: str
    target_file: Optional[str] = None  # "file.guide" or other file (e.g., image)
    target_node: Optional[str] = None  # "NODE" or dummy "main" when linking to non-guide
    line: Optional[int] = None  # optional line number


class Action(BaseModel):
    label: str
    kind: str  # "SYSTEM", "RX", "RXS", "BEEP", "CLOSE", "QUIT"
    value: Optional[str] = None  # command/script, or None for BEEP/CLOSE/QUIT


class StyleToggle(BaseModel):
    style: str  # "bold", "italic", "underline", "code"
    on: bool


class ColorChange(BaseModel):
    fg: Optional[str] = None  # named color, or "APEN:<n>"
    bg: Optional[str] = None  # named color, or "BPEN:<n>"


class AlignChange(BaseModel):
    align: str  # "left", "center", "right"


class IndentChange(BaseModel):
    lindent: Optional[int] = None  # set left indent (spaces)
    pari: Optional[int] = None  # set paragraph initial indent
    pard: bool = False  # reset paragraph settings


class TabsChange(BaseModel):
    set_tabs: Optional[list[int]] = None
    clear_tabs: bool = False
    tab: bool = False  # literal tab insertion


class Break(BaseModel):
    kind: str  # "line" or "paragraph"
    count: int = 1


class UnknownInline(BaseModel):
    raw: str  # raw command text inside @{ ... }
    args: list[str] = []


Inline = Union[
    Text, Link, Action, StyleToggle, ColorChange, AlignChange, IndentChange, TabsChange, Break, UnknownInline
]
