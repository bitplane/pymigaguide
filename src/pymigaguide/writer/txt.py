from __future__ import annotations

from typing import Dict, List

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


class TxtRenderer:
    def render_document(self, doc: GuideDocument) -> Dict[str, str]:
        """
        Returns a dict: { node_name: text }
        """
        out: Dict[str, str] = {}
        for node in doc.nodes:
            out[node.name] = self.render_node(node)
        return out

    def render_node(self, node: GuideNode) -> str:
        parts: List[str] = []

        title = node.attrs.title or node.name
        parts.append(f"\n\n{title.upper()}\n{'=' * len(title)}\n")

        parts.append(self._render_inline_stream(node.content))
        return "".join(parts)

    def _render_inline_stream(self, items: List[Inline]) -> str:
        out: List[str] = []
        for obj in items:
            if isinstance(obj, Text):
                out.append(obj.text)
            elif isinstance(obj, Link):
                out.append(obj.label)  # Just the label for plain text
            elif isinstance(obj, Action):
                out.append(obj.label)  # Just the label for plain text
            elif isinstance(obj, Break):
                if obj.kind == "line":
                    out.append("\n")
                elif obj.kind == "paragraph":
                    out.append("\n\n")
            elif isinstance(obj, TabsChange) and obj.tab:
                out.append("\t")
            # Ignore other inline types for plain text output
            elif isinstance(obj, (StyleToggle, ColorChange, AlignChange, IndentChange, UnknownInline)):
                pass
        return "".join(out)
