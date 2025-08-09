import re

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

# Escaped sequences
ESCAPED_AT_RE = re.compile(r"\\@")  # \@ => literal @
ESCAPED_BS_RE = re.compile(r"\\")  # \\ => literal \
