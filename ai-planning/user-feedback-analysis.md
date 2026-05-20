# User Feedback Analysis

**Date:** 2026-05-20  
**Source:** External user review of the README

---

## Feedback items

> the checkbox is a bit difficult to read in darktheme (judging from the screenshot)

> the screenshot shows a toy example, it would be easier to understand how it could be used with a "real" example

> it looks like it would be a lot of switches between model tree and todo view. Maybe you could show a summery somewhere, like progress and current selected item: 5 / 11, This looks cool

> some hierarchical checkbox UIs uses [-] when there's a mix of checked and unchecked items under it, doing this would show semiprogress.

> It isn't obvious from the readme if keyboard navigation is available (arrows)

> if space to toggle checkbox would be neat (if it isn't already supported)

---

## Item-by-item assessment

---

### 1. Checkbox visibility in dark theme

**Verdict: Valid bug, worth fixing.**

The screenshot appears to use FreeCAD's default light theme, which makes
it hard to assess dark theme rendering. The problem is real: Qt's default
`QStyleOptionButton` checkbox rendering uses the system palette, and in
dark themes the unchecked checkbox outline can become nearly invisible
against a dark background. This is a known limitation of relying on
`QStyle` defaults.

**Possible fixes:**

**Option A — Custom checkbox drawing in the delegate.**  
Override `paint()` in `_DragHandleDelegate` to draw an explicit checkbox
with hard-coded colours that work in both light and dark themes (e.g. a
white-outlined box on any background). This is the most reliable fix but
requires care not to diverge from the platform's checkbox style in ways
that look out of place.

**Option B — Use SVG icons for done/not-done state.**  
Instead of a native checkbox, return a `Qt.DecorationRole` icon (a
custom SVG tick or empty box) and suppress `Qt.ItemIsUserCheckable` in
`flags()`. The icons can be designed to be legible in both themes.
Clicking the icon area would call `setData` directly.

**Option C — Test against FreeCAD's dark theme and report.**  
Load FreeCAD's dark stylesheet, screenshot the panel, and determine
whether the problem is actually the Qt checkbox or the `ForegroundRole`
gray colour used for done items (which may also become hard to read).
Fixing that is simpler — use a theme-aware colour from the palette rather
than the hard-coded `QColor("gray")`.

Minimum fix: change `QColor("gray")` → `option.palette.mid().color()` in
`data()` for `ForegroundRole` so the done text colour is theme-relative.
Then assess whether the checkbox itself also needs work.

**Effort: Low (Option C) to Medium (Options A/B).**

---

### 2. Screenshot shows a toy example

**Verdict: Valid UX feedback, easy to act on.**

The current screenshot uses placeholder items like "Test 1", "Test 3".
A screenshot showing a realistic design-project todo tree — e.g. a
PartDesign workflow broken down into milestones, tasks, and sub-tasks —
would communicate the addon's value proposition immediately.

**Implementation:** Take a new screenshot of FreeCAD open alongside a
real PartDesign or Assembly document with a plausible todo tree populated
alongside it. No code change required — this is purely a documentation
improvement.

Consider adding a second screenshot showing the dock panel alongside the
3D view, since the README's key selling point is that the dock persists
while working in other workbenches.

**Effort: Trivial (15 minutes of setup + screenshot).**

---

### 3. Progress summary (e.g. "5 / 11" done count)

**Verdict: Excellent idea, moderate implementation effort.**

A persistent count of done vs. total items within the current view root
would let users know at a glance how much work remains without clicking
into individual items. The user specifically suggested showing it in
relation to the current selected item, but a simpler and more useful
variant is a summary for the entire current view.

**Proposed design:**  
Add a small status bar below the tree view (or embed a label in the
existing toolbar) that shows:

```
3 / 8 done  ·  2 hidden
```

- `3 / 8 done` — done items / total items within the current view root,
  counting recursively.
- `2 hidden` — shown only when Show Done is off, to remind the user
  items are filtered out. Omitted when Show Done is on.

The count should update reactively whenever the model changes or the
view root changes.

**Implementation sketch:**

1. Add a `QLabel` to `TreePanel._setup_ui()`, below the tree view.
2. Connect it to `self._model.dataChanged`, `self._model.rowsInserted`,
   `self._model.rowsRemoved`, `self._model.modelReset`, and
   `self._model.treeReset`.
3. Also update it from `_navigate_to`, `_navigate_into_selected`,
   `_navigate_up`, and `_toggle_show_done`.
4. The count is computed by walking `self._model._tree` from the current
   view root node, counting `node.done` recursively.
5. The "hidden" count is `total - proxy.rowCount(recursive)` when
   `show_done` is False.

This is entirely read-only — no new data model changes required.

**Effort: Low-Medium (1–2 hours).**

---

### 4. Indeterminate / mixed-state parent checkbox (`[-]`)

**Verdict: Good idea, meaningful implementation effort.**

Many outliner and task-manager UIs show a parent item's checkbox in an
indeterminate (partially-checked) state when some but not all children
are done. Qt supports this natively via `Qt.PartiallyChecked` (integer
value 1) for `Qt.CheckStateRole`. The flag `Qt.ItemIsTristate` also
exists but is not required — we can return value 1 from `data()` and
let the delegate render it without making the checkbox itself clickable
through the partial state.

This would give useful at-a-glance progress information on collapsed
parents: a fully ticked parent means all children done; `[-]` means
some done; empty means none done.

**Design decisions:**

- **Propagation depth:** Compute the state only from *direct* children,
  or from the entire subtree recursively? Recursive is more meaningful
  (a parent is fully done only when all descendants are done) but
  requires a full tree walk on every change.
- **Clicking a mixed-state checkbox:** Currently clicking a checkbox
  toggles only that node. With tristate enabled, a click on a `[-]`
  parent might be expected to mark all children done. This is optional
  scope — the partial display can be read-only even if clicking still
  toggles only the parent.
- **Filter interaction:** When Show Done is off, a parent whose done
  children are hidden appears to have fewer children. The mixed-state
  computation should be based on the model data, not the filtered view.

**Implementation sketch:**

1. In `TodoItemModel.data()`, for `Qt.CheckStateRole`, replace the
   current two-value return with a three-value computation:
   ```python
   if role == Qt.CheckStateRole:
       if node.done:
           return 2  # Checked
       if self._any_descendant_done(node):
           return 1  # PartiallyChecked
       return 0      # Unchecked
   ```
2. Add `_any_descendant_done(node)` that walks the subtree and returns
   `True` if any descendant has `done=True`.
3. In `flags()`, do NOT add `Qt.ItemIsTristate` — this prevents Qt from
   cycling through the partial state on click, keeping click behaviour
   unchanged (toggle only the clicked node).
4. When a leaf node's done state changes, emit `dataChanged` for all
   its ancestors so their mixed-state indicator updates. This requires
   walking up the parent chain after each toggle.

**Caveat:** Step 4 adds some complexity — the current `setData` only
emits `dataChanged` for the toggled index. It will need to also emit for
each ancestor.

**Effort: Medium (2–4 hours including the ancestor emit chain).**

---

### 5. Arrow key navigation not obvious from README

**Verdict: Documentation gap, trivially fixed.**

Arrow key navigation is provided automatically by Qt's `QTreeView`:

- **↑ / ↓** — move selection up and down through visible items.
- **← / →** — collapse / expand the selected item (or move to
  parent / first child if already collapsed / expanded).

These are not explicitly listed in the README keyboard shortcuts table
because they were not custom-added — they come free from Qt. The user is
right that this should be documented; many users assume tree views are
mouse-only until told otherwise.

**Fix:** Add a row to the README shortcuts table:

| Action | Windows / Linux | macOS |
|--------|----------------|-------|
| Move selection up / down | **↑ / ↓** | **↑ / ↓** |
| Expand / collapse item | **→ / ←** | **→ / ←** |

Also worth mentioning: **→** on an already-expanded item moves selection
to its first child; **←** on a collapsed item moves selection to its
parent. These are standard Qt behaviours.

**Effort: Trivial (one README edit).**

---

### 6. Space to toggle checkbox

**Verdict: Already implemented and documented — just needs more prominence.**

Space to toggle done/not-done is supported. Qt's `QTreeView` fires the
checkbox toggle via `editorEvent` when Space is pressed on an item with
`Qt.ItemIsUserCheckable`. This was documented in `Documentation/Commands/
CompleteItem.md` and added to the README shortcuts table in a recent
commit.

The feedback suggests the user did not see it in the README. Two fixes:
1. Add it to the intro sentence in the README "How to use" section
   alongside "Click the checkbox", e.g.: "…or press **Space** with the
   item selected."
2. The shortcuts table now includes Space — so once this README version
   is published the gap is closed.

**Effort: Trivial (one sentence in the README).**

---

## Priority ranking

| # | Item | Verdict | Effort | Recommendation |
|---|------|---------|--------|----------------|
| 1 | Arrow keys not documented | Documentation gap | Trivial | **Do immediately** |
| 2 | Space not obvious in README | Already fixed in shortcuts table | Trivial | **Add one sentence to How to Use** |
| 3 | Toy screenshot | Documentation improvement | Trivial | **Do next** |
| 4 | Progress summary (N / M done) | Good feature, self-contained | Low-Medium | **Worth implementing** |
| 5 | Checkbox in dark theme | Bug, palette fix is easy | Low–Medium | **Investigate and fix** |
| 6 | Mixed-state parent checkbox | Good feature, more complex | Medium | **Consider after #4** |

---

## Quick wins to do right now

Items 1 and 2 require nothing but two small README edits and can be
done in the same commit. Item 3 (screenshot) requires a bit of staging
but no code. All three improve first impressions significantly.

Items 4, 5, and 6 are real features/fixes that deserve their own
branches, and items 5 and 6 interact (the custom delegate work for dark
theme may overlap with the tristate rendering).
