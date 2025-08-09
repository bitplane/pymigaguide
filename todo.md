# Integrating `pymigaguide` (parser, Markdown, and Textual viewer)

This is a step‑by‑step plan to stitch together what we’ve built: the parser, Markdown renderer, CLI, and the Textual viewer with toolbar/navigation. Follow it in order; you’ll have a working app and a JSON‑dumping CLI at the end.

---

## 0) What you have right now

```
docs
└── guide.md
LICENSE.md
Makefile
mkdocs.yml
pyproject.toml
README.md
scripts/
src/
└── pymigaguide/
    ├── app.py
    ├── cli.py
    ├── __init__.py
    ├── markdown.py
    ├── model.py
    ├── parser.py
    └── widgets/
        ├── guidetoolbar.py
        ├── guideview.py
        └── __init__.py
tests/
```

> Note: earlier snippets referenced `models.py` and `widgets/toolbar.py`. Your package uses `model.py` and `widgets/guidetoolbar.py`. The steps below reconcile those names.

---

## 1) Sanity: dependencies

Ensure these are in `pyproject.toml` (they’re already installed per your note, but double‑check versions if anything misbehaves):

* `pydantic` (v2 preferred; code is tolerant of v1)
* `textual`
* `chardet`
* Dev: `pytest`, `ruff` (optional)

---

## 2) Reconcile imports (model vs. models; toolbar filename)

Do a quick pass and update imports to match **your** filenames:

* In **`src/pymigaguide/parser.py`** and **`src/pymigaguide/markdown.py`**:

  * Replace `from models import ...` → `from .model import ...`
* In **`src/pymigaguide/app.py`** and **`src/pymigaguide/widgets/guideview.py`**:

  * Replace `from widgets.toolbar import GuideToolbar` → `from .guidetoolbar import GuideToolbar`
  * Replace relative imports appropriately (use package‑relative imports everywhere).

Tip: a quick grep to confirm no stale paths remain:

```bash
grep -R "from models" -n src/pymigaguide || true
grep -R "widgets\.toolbar" -n src/pymigaguide || true
```

---

## 3) `model.py`: ensure schema matches the parser/renderer

Your `model.py` should match the Pydantic schema we agreed (GuideDocument/GuideMetadata/GuideNode/etc.). If you started from the earlier draft, you’re good. If not, sync it to the latest version you want to use.

**Contract the rest of the code expects:**

* `GuideDocument(meta: GuideMetadata, nodes: list[GuideNode])`
* `GuideNode(name: str, attrs: NodeAttributes, content: list[Inline])`
* `Inline` is a `Union[...]` that includes: `Text`, `Link`, `Action`, `StyleToggle`, `ColorChange`, `AlignChange`, `IndentChange`, `TabsChange`, `Break`, `UnknownInline`.

---

## 4) `parser.py`: keep the API stable

Parser entry points used by CLI/Textual:

* `AmigaGuideParser.parse_file(path: str|Path) -> GuideDocument`
* `AmigaGuideParser.parse_text(text: str) -> GuideDocument`

Internally it may attempt UTF‑8 then Latin‑1; the CLI will do detection with `chardet` and call `parse_text` with a proper Unicode `str`.

**If your parser currently imports `model` using absolute imports**, switch to relative: `from .model import ...`.

Optional (but nice): ensure unknown commands go into `extras` and unknown inline to `UnknownInline` so we don’t lose information.

---

## 5) `markdown.py`: renderer contract

* Expose `MarkdownRenderer` with:

  * `render_document(doc: GuideDocument) -> dict[str,str]` (map of node name → Markdown)
  * `render_node(node: GuideNode) -> str`
* The link targets should be of the form:

  * `#<node-slug>` for intra‑doc
  * `<otherfile>.md#<node-slug>` for cross‑doc
  * Optional `?line=N` query is fine (no‑op in current viewer; useful later).

**Imports**: `from .model import ...` (not `models`).

---

## 6) `widgets/guidetoolbar.py`: drop in toolbar implementation

Ensure this file contains the `GuideToolbar` we discussed (Prev, Next, Contents, Index, Help, and a live title) and the `NavTargets` dataclass.

**Public surface:**

* `GuideToolbar.set_targets(NavTargets)` sets/updates the buttons and title.
* Emits `GuideToolbar.NavRequested(kind: str, target: Optional[str])` when a button is clicked.

If you used the earlier snippet, you’re done here.

---

## 7) `widgets/guideview.py`: wire toolbar + Markdown viewer

`GuideView` should:

* Compose a `GuideToolbar` and a `Markdown` widget.
* Hold state: current document, current node, history stack.
* Provide `goto(file: Optional[str], node: Optional[str], line: Optional[int])`.
* Intercept Markdown link clicks and translate them back to `(file,node,line)`.
* Compute toolbar targets (`@PREV/@NEXT/@TOC/@INDEX/@HELP`, with sane fallbacks).

**Key integration points to verify:**

* `compose()` yields `GuideToolbar()` then `Markdown("")`.
* On navigation/render (`_render_node`), call `tb.set_targets(self._compute_targets_for(doc, node_name))`.
* Implement `on_guide_toolbar_nav_requested()` to call `self.goto(file=None, node=msg.target, line=None)`.
* Link interception: handle `on_markdown_link_clicked()` and parse `href` (support `#node`, `file.md#node`, `?line=N`).

Imports must be package‑relative:

```python
from .guidetoolbar import GuideToolbar, NavTargets
from ..markdown import MarkdownRenderer
from ..model import GuideDocument
```

---

## 8) `app.py`: boot the viewer

`GuideApp` should:

* Instantiate `GuideView` in `compose()`.
* On mount: pick the guide path (CLI arg `sys.argv[1]` is fine for now), parse it with `AmigaGuideParser`, pass `GuideDocument` into `GuideView`, then `goto()` the start node (`MAIN` if present, else the first node).
* Bindings for `back`/`forward` are handy.

Imports should be package‑relative (example):

```python
from .parser import AmigaGuideParser
from .markdown import MarkdownRenderer
from .widgets.guideview import GuideView
```

Smoke‑test launch (after editable install):

```bash
python -m pymigaguide.app path/to/file.guide
```

---

## 9) `cli.py`: encoding detect → JSON dump

CLI contract:

```
python -m pymigaguide.cli path/to/file.guide --dump --format=json
```

* Reads file as **binary**, uses **chardet** to detect encoding, decodes to Unicode.
* Calls `AmigaGuideParser.parse_text()`.
* Dumps JSON via Pydantic (`model_dump_json(indent=2)` or fallback).

Ensure imports are `from .parser import AmigaGuideParser` etc.

Optional: add entry points later (see Next Steps).

---

## 10) Minimal sample to test

Create `sample.guide` somewhere convenient:

```text
@DATABASE Sample
@NODE MAIN "Welcome"
@{b}AmigaGuide demo@{ub}

See @{"Other node" LINK "Other"}.
@ENDNODE

@NODE Other "Second Page"
This is the @{i}other@{ui} node. @{"Back to main" LINK "MAIN"}
@ENDNODE
```

Run:

```bash
python -m pymigaguide.cli sample.guide --dump --format=json | head
python -m pymigaguide.app sample.guide
```

You should see the viewer with a title, toolbar, and clickable links.

---

## 11) Packaging quality‑of‑life (optional now)

* Add console scripts in `pyproject.toml`:

```toml
[project.scripts]
pymigaguide = "pymigaguide.cli:main"
pymigaguide-view = "pymigaguide.app:main"
```

* Editable install while developing:

```bash
pip install -e .
```

---

## 12) Next steps (file references you’ll likely add next)

**Rendering fidelity & UX**

* `src/pymigaguide/widgets/flowtext.py` — faithful inline renderer (clickable spans, tabs, alignment, indent, color, code‑mode, smart/word wrap). Replace Markdown viewer when ready.
* `src/pymigaguide/widgets/actionpolicy.py` — pluggable gate/confirm for `SYSTEM/RX/RXS` and behavior for `BEEP/CLOSE/QUIT`.
* `src/pymigaguide/widgets/assetview.py` — open non‑guide links (images via `Image`, text via `TextLog`, fallback to OS).
* `src/pymigaguide/palette.py` — mapping for Amiga color names → theme tokens (and APEN/BPEN best‑effort mapping).
* `src/pymigaguide/linkresolver.py` — cache and resolve `(file,node)` to loaded docs; centralises cross‑file navigation.

**Conversion & tooling**

* `src/pymigaguide/mdcli.py` — write one `.md` file per node (consume `MarkdownRenderer.render_document`).
* `src/pymigaguide/macros.py` — optional macro expander (`@MACRO` + `@{name $1 ...}` two‑pass expansion).
* `src/pymigaguide/tests/` — parser unit tests (nodes, links, styles, escapes), plus round‑trip markdown smoke tests.

**Docs & distribution**

* Add an example gallery to `docs/` (screenshots + sample `.guide`).
* Wire `mkdocs.yml` to include the format reference and usage examples.
* Entry points (see §11) and a `README.md` quickstart.

**Performance**

* Bench large guides; if needed, replace regex hot paths in parser (simple hand‑rolled scanner) and cache inline tokenization per node.

---

## 13) Done checklist

* [ ] Imports reconciled (model vs models; guidetoolbar path).
* [ ] Parser parses sample.
* [ ] Markdown renderer emits links that viewer understands.
* [ ] GuideView toolbar buttons navigate.
* [ ] CLI JSON dump works.
* [ ] Textual app opens `sample.guide` and navigates.

When these are all ✅, you’ve got a working vertical slice. Then we can swap in `FlowText` for full fidelity without touching the app shell or toolbar.
