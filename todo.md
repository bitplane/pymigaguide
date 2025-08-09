# FlowText Integration Plan

## Purpose

Replace the current Markdown-based rendering in `GuideView` with a `FlowText` widget that renders AmigaGuide Inline sequences faithfully.

---

## Integration Instructions

1. **Add `flowtext.py`**

   * Create `src/pymigaguide/widgets/flowtext.py`.
   * Paste the provided `FlowText` implementation.

2. **Modify `guideview.py`**

   * Replace the Markdown widget in `compose()` with:

     ```python
     from .flowtext import FlowText, LinkActivated
     yield GuideToolbar()
     yield FlowText()
     ```
   * In the node rendering method (`_render_node` or equivalent):

     ```python
     ft = self.query_one(FlowText)
     node = next(n for n in doc.nodes if n.name == node_name)
     ft.set_items(node.content)
     # Optionally:
     # ft.set_options(FlowOptions(word_wrap=..., smart_wrap=...))
     ```
   * Add a message handler for link clicks:

     ```python
     def on_link_activated(self, msg: LinkActivated) -> None:
         self.goto(file=msg.target.file, node=msg.target.node, line=msg.target.line)
         msg.stop()
     ```

3. **Keep Markdown path as fallback**

   * Keep the old Markdown widget code behind a flag or toggle for testing.

4. **Palette Configuration**

   * Optionally set a palette via `ft.set_palette(custom_palette)` if you want Amiga-accurate colours.

5. **Test**

   * Run a guide file with varied inline commands, including `@{B}`, `@{U}`, `@{FG text}`, `@{TAB}`, `@{LINK}`.
   * Verify:

     * Bold/italic/underline works
     * Tabs align text as expected
     * Colours render according to palette mapping
     * Links are clickable and trigger navigation

---

## TODO List

* **CODE toggle support**

  * Make `@{CODE}` blocks no-wrap by splitting paragraphs into `Text(no_wrap=True)` runs.

* **Per-paragraph alignment refinements**

  * Compute available width from `self.size.width` for more precise centering with tabs.

* **Action commands**

  * (`SYSTEM`, `RX`, `RXS`, `BEEP`, `CLOSE`, `QUIT`) → clickable with `ActionActivated` messages and a policy handler.

* **SMARTWRAP fidelity**

  * Honour explicit `@{LINE}` / `@{PAR}` vs raw `\n` more faithfully.

* **Palette improvements**

  * Wire in an actual Amiga palette or theme mapping; support user overrides via config.

* **Testing matrix**

  * Create test `.guide` files exercising all inline features and edge cases.

---

## Next Steps

* Implement the TODOs above iteratively.
* Add unit tests for `FlowText` rendering with representative `Inline` sequences.
* Benchmark rendering performance vs Markdown renderer.
* Once stable, remove Markdown path if no longer needed.
