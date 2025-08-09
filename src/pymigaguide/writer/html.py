from __future__ import annotations

from typing import Dict, List
import html as html_escape

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


class HtmlRenderer:
    def render_document(self, doc: GuideDocument) -> Dict[str, str]:
        """
        Returns a dict: { node_name: html }
        """
        out: Dict[str, str] = {}
        for node in doc.nodes:
            out[node.name] = self.render_node(node)
        return out

    def render_node(self, node: GuideNode) -> str:
        parts: List[str] = []

        title = node.attrs.title or node.name
        parts.append(f"<h1>{html_escape.escape(title)}</h1>")

        parts.append(self._render_inline_stream(node.content))
        return "\n".join(parts)

    def _render_inline_stream(self, items: List[Inline]) -> str:
        out: List[str] = []
        # Simple style tracking
        bold = False
        italic = False
        underline = False

        for obj in items:
            if isinstance(obj, Text):
                out.append(html_escape.escape(obj.text))
            elif isinstance(obj, Link):
                label = html_escape.escape(obj.label)
                # For simplicity, just use the target node as href for now
                # More complex link resolution would be needed for cross-file links
                href = f"#{obj.target_node}" if obj.target_node else "#"
                out.append(f'<a href="{href}">{label}</a>')
            elif isinstance(obj, StyleToggle):
                if obj.style == "bold":
                    if obj.on and not bold:
                        out.append("<strong>")
                        bold = True
                    elif not obj.on and bold:
                        out.append("</strong>")
                        bold = False
                elif obj.style == "italic":
                    if obj.on and not italic:
                        out.append("<em>")
                        italic = True
                    elif not obj.on and italic:
                        out.append("</em>")
                        italic = False
                elif obj.style == "underline":
                    if obj.on and not underline:
                        out.append("<u>")
                        underline = True
                    elif not obj.on and underline:
                        out.append("</u>")
                        underline = False
                # Ignoring 'code' style for basic HTML for now
            elif isinstance(obj, Break):
                if obj.kind == "line":
                    out.append("<br>")
                elif obj.kind == "paragraph":
                    out.append("<p>")
            elif isinstance(obj, Action):
                # Actions are not rendered in basic HTML output
                out.append(html_escape.escape(obj.label))
            elif isinstance(obj, (ColorChange, AlignChange, IndentChange, TabsChange)):
                # These are visual formatting, ignored for basic HTML
                pass
            elif isinstance(obj, UnknownInline):
                # Optionally render as a comment or just ignore
                pass

        # Close any open tags at the end
        if bold:
            out.append("</strong>")
        if italic:
            out.append("</em>")
        if underline:
            out.append("</u>")

        return "".join(out)
