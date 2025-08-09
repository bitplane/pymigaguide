from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple, List

# If you want encoding detection, install chardet and uncomment:
# import chardet

from models import (
    GuideDocument,
    GuideMetadata,
    GuideNode,
    NodeAttributes,
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


NODE_START_RE = re.compile(r'^@NODE\s+(\S+)(?:\s+"([^"]*)")?\s*$', re.IGNORECASE)
NODE_END_RE = re.compile(r"^@ENDNODE(?:\s+\S+)?\s*$", re.IGNORECASE)

# Commands that must start at column 0 (global or node-level)
CMD_LINE_RE = re.compile(r"^\s*@([A-Z]+)\b(.*)$", re.IGNORECASE)

# Inline @{ ... } occurrences
INLINE_RE = re.compile(r"@{([^}]*)}")

# Quoted string (for inline commands like @"label")
QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')

# Split file/node as "file/node"
FILE_NODE_SPLIT = re.compile(r"^(.*?)/(.*)$")

ESCAPED_AT_RE = re.compile(r"\\@")  # \@ => literal @
ESCAPED_BS_RE = re.compile(r"\\\\")  # \\ => literal \


def detect_encoding_and_read(path: Path) -> str:
    # Simple strategy: try utf-8, then latin-1; or use chardet if you want.
    data = path.read_bytes()
    # if chardet:
    #     enc = chardet.detect(data).get("encoding") or "utf-8"
    #     try:
    #         return data.decode(enc)
    #     except UnicodeDecodeError:
    #         pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


class AmigaGuideParser:
    """
    Pragmatic AmigaGuide parser:
      - Parses global directives, nodes, and inline @{...} commands.
      - Preserves unknown inline commands as UnknownInline.
      - Does not execute macros; it records global/node macro definitions.
    """

    def parse_file(self, path: str | Path) -> GuideDocument:
        path = Path(path)
        text = detect_encoding_and_read(path)
        return self.parse_text(text)

    def parse_text(self, text: str) -> GuideDocument:
        lines = text.splitlines()
        meta = GuideMetadata()
        nodes: List[GuideNode] = []

        in_node = False
        current: Optional[GuideNode] = None
        pending_content_lines: List[str] = []

        # require @DATABASE on first non-empty line if present
        first_non_empty_seen = False

        for raw in lines:
            line = raw.rstrip("\n")

            if not in_node:
                # Global command or whitespace/comment
                if not line.strip():
                    continue

                # @NODE?
                m_node = NODE_START_RE.match(line)
                if m_node:
                    in_node = True
                    name, title = m_node.group(1), m_node.group(2)
                    current = GuideNode(name=name, attrs=NodeAttributes())
                    if title:
                        current.attrs.title = title
                    pending_content_lines = []
                    continue

                # Global command?
                m_cmd = CMD_LINE_RE.match(line)
                if m_cmd:
                    cmd, arg = m_cmd.group(1).upper(), m_cmd.group(2).strip()
                    self._apply_global_cmd(meta, cmd, arg)
                    if cmd == "DATABASE":
                        first_non_empty_seen = True
                    continue

                # First content before @NODE is not allowed; but tolerate comments/etc.
                if not first_non_empty_seen and line.strip():
                    # allow files missing @DATABASE; we won’t be strict
                    first_non_empty_seen = True
                continue
            else:
                # Inside a node
                if NODE_END_RE.match(line):
                    # flush pending_content_lines into Inline stream
                    if current is not None:
                        current.content.extend(self._parse_node_content("\n".join(pending_content_lines)))
                        nodes.append(current)
                    in_node = False
                    current = None
                    pending_content_lines = []
                    continue

                # Node-scope directive starting at column 0?
                m_cmd = CMD_LINE_RE.match(line)
                if m_cmd and line.startswith("@"):
                    cmd, arg = m_cmd.group(1).upper(), m_cmd.group(2).strip()
                    if current is not None:
                        self._apply_node_cmd(current, cmd, arg)
                    continue

                # Otherwise, normal content line
                pending_content_lines.append(line)

        # If file ended inside a node without @ENDNODE, finalize it
        if in_node and current is not None:
            current.content.extend(self._parse_node_content("\n".join(pending_content_lines)))
            nodes.append(current)

        # Minimal sanity: if no DATABASE, we can set it to None and move on
        return GuideDocument(meta=meta, nodes=nodes)

    # --------- Command handlers --------- #

    def _apply_global_cmd(self, meta: GuideMetadata, cmd: str, arg: str) -> None:
        # Normalize arg: strip surrounding quotes if present
        arg_q = self._unquote(arg)

        if cmd == "DATABASE":
            meta.database = arg_q or None
        elif cmd in ("$VER:", "$VER"):
            meta.version = arg.strip()
        elif cmd in ("(C)", "C", "@(C)"):
            meta.copyright = arg.strip()
        elif cmd == "AUTHOR":
            meta.author = arg_q or None
        elif cmd == "INDEX":
            meta.index_node = self._guide_target_to_node(arg_q)
        elif cmd == "HELP":
            meta.help_node = self._guide_target_to_node(arg_q)
        elif cmd == "FONT":
            name, size = self._parse_font(arg)
            meta.font_name, meta.font_size = name, size
        elif cmd == "WORDWRAP":
            meta.wordwrap = True
        elif cmd == "SMARTWRAP":
            meta.smartwrap = True
        elif cmd == "TAB":
            meta.tab_width = self._parse_int(arg)
        elif cmd == "WIDTH":
            meta.width_hint = self._parse_int(arg)
        elif cmd == "HEIGHT":
            meta.height_hint = self._parse_int(arg)
        elif cmd == "ONOPEN":
            meta.onopen_script = arg_q or None
        elif cmd == "ONCLOSE":
            meta.onclose_script = arg_q or None
        elif cmd == "MACRO":
            name, expansion = self._parse_macro_def(arg)
            if name:
                meta.macros[name] = expansion
        else:
            # preserve unknown globals
            meta.extras.setdefault(cmd, []).append(arg)

    def _apply_node_cmd(self, node: GuideNode, cmd: str, arg: str) -> None:
        attrs = node.attrs
        arg_q = self._unquote(arg)

        if cmd == "TITLE":
            attrs.title = arg_q or None
        elif cmd == "TOC":
            attrs.toc = self._guide_target_to_node(arg_q)
        elif cmd == "NEXT":
            attrs.next = self._guide_target_to_node(arg_q)
        elif cmd == "PREV":
            attrs.prev = self._guide_target_to_node(arg_q)
        elif cmd == "INDEX":
            attrs.index = self._guide_target_to_node(arg_q)
        elif cmd == "HELP":
            attrs.help = self._guide_target_to_node(arg_q)
        elif cmd == "FONT":
            name, size = self._parse_font(arg)
            attrs.font_name, attrs.font_size = name, size
        elif cmd == "PROPORTIONAL":
            attrs.proportional = True
        elif cmd == "WORDWRAP":
            attrs.wordwrap = True
        elif cmd == "SMARTWRAP":
            attrs.smartwrap = True
        elif cmd == "TAB":
            attrs.tab_width = self._parse_int(arg)
        elif cmd == "KEYWORDS":
            attrs.keywords = arg_q or arg or None
        elif cmd == "ONOPEN":
            attrs.onopen_script = arg_q or None
        elif cmd == "ONCLOSE":
            attrs.onclose_script = arg_q or None
        elif cmd == "MACRO":
            name, expansion = self._parse_macro_def(arg)
            if name:
                attrs.macros[name] = expansion
        elif cmd == "EMBED":
            if arg_q:
                attrs.embeds.append(arg_q)
        else:
            attrs.extras.setdefault(cmd, []).append(arg)

    # --------- Inline parsing --------- #

    def _parse_node_content(self, text: str) -> List[Inline]:
        # Replace escaped sequences first (\@ -> @, \\ -> \)
        text = ESCAPED_BS_RE.sub("\\", text)
        text = ESCAPED_AT_RE.sub("@", text)

        out: List[Inline] = []
        pos = 0
        for m in INLINE_RE.finditer(text):
            start, end = m.span()
            if start > pos:
                out.append(Text(text=text[pos:start]))
            raw_cmd = m.group(1).strip()
            out.append(self._parse_inline_command(raw_cmd))
            pos = end
        if pos < len(text):
            out.append(Text(text=text[pos:]))

        return out

    def _parse_inline_command(self, raw: str) -> Inline:
        # Tokenize by whitespace, but preserve quoted segments
        tokens = self._split_tokens_with_quotes(raw)
        if not tokens:
            return UnknownInline(raw=raw, args=[])

        t0 = tokens[0].upper()
        # Style toggles
        if t0 in ("B", "UB"):
            return StyleToggle(style="bold", on=(t0 == "B"))
        if t0 in ("I", "UI"):
            return StyleToggle(style="italic", on=(t0 == "I"))
        if t0 in ("U", "UU"):
            return StyleToggle(style="underline", on=(t0 == "U"))
        if t0 == "CODE":
            # CODE is a toggle that disables wrapping; map to a style flag
            return StyleToggle(style="code", on=True)  # you can track off with PLAIN/BODY below
        if t0 in ("PLAIN", "PLAINTEXT", "BODY"):
            # reset styles; represent as toggles off for bold/italic/underline/code
            # (keep it simple; viewers can interpret as full reset)
            return UnknownInline(raw=raw, args=tokens)  # keep semantic info; rendering can map to reset

        # Colors
        if t0 == "FG" and len(tokens) >= 2:
            return ColorChange(fg=tokens[1])
        if t0 == "BG" and len(tokens) >= 2:
            return ColorChange(bg=tokens[1])
        if t0 == "APEN" and len(tokens) >= 2:
            return ColorChange(fg=f"APEN:{tokens[1]}")
        if t0 == "BPEN" and len(tokens) >= 2:
            return ColorChange(bg=f"BPEN:{tokens[1]}")

        # Alignment + indent
        if t0 in ("JLEFT", "JCENTER", "JRIGHT"):
            return AlignChange(align={"JLEFT": "left", "JCENTER": "center", "JRIGHT": "right"}[t0])

        if t0 == "LINDENT" and len(tokens) >= 2:
            return IndentChange(lindent=self._to_int(tokens[1]))
        if t0 == "PARI" and len(tokens) >= 2:
            return IndentChange(pari=self._to_int(tokens[1]))
        if t0 == "PARD":
            return IndentChange(pard=True)

        # Tabs + breaks
        if t0 == "SETTABS" and len(tokens) >= 2:
            stops = [self._to_int(t) for t in tokens[1:] if self._to_int(t) is not None]
            return TabsChange(set_tabs=stops or None)
        if t0 == "CLEARTABS":
            return TabsChange(clear_tabs=True)
        if t0 == "TAB":
            return TabsChange(tab=True)
        if t0 == "LINE":
            return Break(kind="line", count=1)
        if t0 == "PAR":
            return Break(kind="paragraph", count=2)

        # Links and actions:
        # Pattern:  "<label>" LINK "<target>" [line]
        #           "<label>" ALINK "<target>" [line]   (same as LINK in modern viewers)
        #           "<label>" GUIDE "<target>"          (explicit guide link)
        #           "<label>" SYSTEM "<cmd>"
        #           "<label>" RX "<script.rexx>"   or RXS "<inline-rexx>"
        #           "<label>" BEEP | CLOSE | QUIT
        if raw.startswith('"'):
            # extract first quoted label
            m = QUOTED_RE.match(raw)
            if m:
                label = self._unescape_quotes(m.group(1))
                rest = raw[m.end() :].strip()
                parts = self._split_tokens_with_quotes(rest)
                if parts:
                    op = parts[0].upper()
                    if op in ("LINK", "ALINK", "GUIDE"):
                        target = None
                        line_no = None
                        if len(parts) >= 2 and parts[1].startswith('"'):
                            target = self._strip_quotes(parts[1])
                        elif len(parts) >= 2:
                            target = parts[1]
                        if len(parts) >= 3:
                            # optional line number
                            ln = self._to_int(parts[2])
                            if ln is not None:
                                line_no = ln
                        file_name, node_name = self._split_file_node(target or "")
                        return Link(label=label, target_file=file_name, target_node=node_name, line=line_no)
                    if op in ("SYSTEM", "RX", "RXS"):
                        value = None
                        if len(parts) >= 2:
                            value = self._strip_quotes(" ".join(parts[1:])).strip()
                        return Action(label=label, kind=op, value=value or None)
                    if op in ("BEEP", "CLOSE", "QUIT"):
                        return Action(label=label, kind=op, value=None)
                # If we get here, we couldn’t interpret – stash raw
                return UnknownInline(raw=raw, args=parts)
        # default: unknown
        return UnknownInline(raw=raw, args=tokens)

    # --------- helpers --------- #

    @staticmethod
    def _parse_font(arg: str) -> tuple[Optional[str], Optional[int]]:
        # @FONT <name> <size>
        tokens = arg.split()
        if not tokens:
            return None, None
        if len(tokens) == 1:
            return tokens[0].strip('"'), None
        name = tokens[0].strip('"')
        size = None
        try:
            size = int(tokens[1])
        except ValueError:
            pass
        return name, size

    @staticmethod
    def _parse_int(s: str) -> Optional[int]:
        s = s.strip().split()[0] if s.strip() else ""
        try:
            return int(s)
        except Exception:
            return None

    @staticmethod
    def _parse_macro_def(arg: str) -> tuple[Optional[str], str]:
        # MACRO name expansion...
        parts = arg.split(None, 1)
        if not parts:
            return None, ""
        name = parts[0]
        expansion = parts[1] if len(parts) > 1 else ""
        # Strip a surrounding quoted expansion if present
        if expansion.startswith('"') and expansion.endswith('"') and len(expansion) >= 2:
            expansion = expansion[1:-1]
        return name, expansion

    @staticmethod
    def _split_tokens_with_quotes(s: str) -> List[str]:
        """
        Split a string into tokens, keeping quoted strings intact.
        Keeps the quotes to allow downstream helpers to distinguish.
        """
        out: List[str] = []
        i = 0
        cur = []
        in_q = False
        escape = False
        while i < len(s):
            ch = s[i]
            if in_q:
                cur.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_q = False
                    out.append("".join(cur).strip())
                    cur = []
                i += 1
                continue
            if ch == '"':
                if cur:
                    out.append("".join(cur).strip())
                    cur = []
                in_q = True
                cur.append(ch)
                i += 1
                continue
            if ch.isspace():
                if cur:
                    out.append("".join(cur).strip())
                    cur = []
                i += 1
                continue
            cur.append(ch)
            i += 1
        if cur:
            out.append("".join(cur).strip())
        return [t for t in out if t]

    @staticmethod
    def _strip_quotes(s: str) -> str:
        s = s.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1].replace('\\"', '"')
        return s

    @staticmethod
    def _unescape_quotes(s: str) -> str:
        return s.replace('\\"', '"')

    @staticmethod
    def _unquote(s: str) -> str:
        s = s.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1]
        return s

    @staticmethod
    def _to_int(s: str) -> Optional[int]:
        try:
            return int(s, 10)
        except Exception:
            return None

    @staticmethod
    def _split_file_node(target: str) -> Tuple[Optional[str], Optional[str]]:
        if not target:
            return None, None
        m = FILE_NODE_SPLIT.match(target)
        if m:
            file_name, node_name = m.group(1), m.group(2)
            return (file_name or None), (node_name or None)
        # No slash => node only
        return None, target or None

    @staticmethod
    def _guide_target_to_node(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        # For "file/node", keep full; for "node" return node.
        # At global/node directive level we usually just want the node part or full
        # string as-is for later resolution.
        return s
