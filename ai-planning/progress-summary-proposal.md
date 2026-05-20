# Progress Summary Proposal

**Date:** 2026-05-20  
**Status:** Proposal — pending implementation decision

---

## Problem

There is currently no way to know at a glance how much work remains in the
current view. A user who has navigated into a subtree (e.g. "Engineering →
CAD model") must expand every branch and visually count items to understand
progress. A persistent summary counter would provide this information
instantly.

---

## Shared design decisions

All options share the same underlying computation and reactivity wiring.

### Count scope

The count covers **all descendants of the current view root** recursively —
not just the top-level items, and not the entire document. This is the most
useful scope because it tracks exactly what the user is looking at after
navigating into a subtree.

```python
def _compute_progress(view_root_id, tree):
    node = tree.get_node(view_root_id)  # or tree.root for document root
    done = total = 0
    def walk(n):
        nonlocal done, total
        for child in n.children:
            total += 1
            if child.done:
                done += 1
            walk(child)
    walk(node)
    return done, total
```

### Display format

```
3 / 11 done
```

When **Show Done** is off, append a hidden-item notice so the user
understands the counts include items they cannot currently see:

```
3 / 11 done  ·  3 hidden
```

### Reactivity — signals to connect

The count must update whenever:

| Signal | Reason |
|--------|--------|
| `model.dataChanged` | Done state toggled on any item |
| `model.rowsInserted` | Item added |
| `model.rowsRemoved` | Item deleted |
| `model.modelReset` / `model.treeReset` | Undo / redo |
| Navigation (Go Into, Go Up, breadcrumb click) | View root changed |
| Show Done toggled | Hidden count changes |

All five placement options below use this same signal set. No new model
changes are required — the count reads existing `node.done` flags.

---

## Option A — Status bar label (bottom of panel)

### Layout

```
┌──────────────────────────────────────┐
│ [breadcrumb bar]                      │
│ [toolbar]                             │
│                                       │
│   ☐  Buy milk                         │
│   ☑  Write proposal                   │
│   ☐  Fix bug                          │
│                                       │
├──────────────────────────────────────┤
│  3 / 11 done  ·  3 hidden            │  ← QLabel, small text, aligned right
└──────────────────────────────────────┘
```

A `QLabel` is added below the `QTreeView` in `TreePanel._setup_ui()`. It
uses a slightly smaller font and muted text colour (`QPalette.Disabled /
QPalette.Text`) so it reads as secondary information. When the count is
`0 / 0` (empty view), the label is hidden rather than showing a confusing
fraction.

### Pros
- Does not compete with the toolbar or breadcrumb for vertical space.
- Always visible without scrolling to the top.
- Familiar pattern — status bars at the bottom of panels are a widely
  understood UX convention.

### Cons
- If the dock panel is very short (narrow screen), the status bar may be
  clipped or push the tree view to be smaller than useful.
- The user's eye must travel to the bottom of the panel to check progress.

### Effort: Low (~1 hour)

---

## Option B — Right-aligned count in the toolbar

### Layout

```
┌──────────────────────────────────────┐
│ [breadcrumb bar]                      │
│ + Item  + Child  Delete │ ← →  …  │  3/11  │
│                                       │
│   ☐  Buy milk                         │
│   ☑  Write proposal                   │
└──────────────────────────────────────┘
```

A `QLabel` is added to the existing `QToolBar` using `addWidget` with a
preceding `addSeparator`. The label is right-aligned via a spacer widget
pushed to the left side of the toolbar. Format: compact `3/11` (no word
"done") to fit the tighter space.

```python
spacer = QWidget()
spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
tb.addWidget(spacer)
self._progress_label = QLabel("", self)
tb.addWidget(self._progress_label)
```

### Pros
- Always at the top — immediately visible without looking away from where
  the breadcrumb shows context.
- No extra vertical space consumed.
- Natural position for summary information next to action buttons.

### Cons
- Toolbar is already moderately crowded. On narrow panels the count label
  may be pushed off-screen or cause line-wrapping.
- Compact format (`3/11`) is less explicit than `3 / 11 done`.

### Effort: Low (~1 hour)

---

## Option C — Progress bar below the tree

### Layout

```
┌──────────────────────────────────────┐
│ [breadcrumb bar]                      │
│ [toolbar]                             │
│                                       │
│   ☐  Buy milk                         │
│   ☑  Write proposal                   │
│                                       │
│  ████████░░░░░░░░  3 / 11 done        │  ← QProgressBar
└──────────────────────────────────────┘
```

A `QProgressBar` is added below the tree view. `setMaximum(total)`,
`setValue(done)`, and `setFormat("3 / 11 done")` are set on each update.
The bar is set to a fixed height (14–16 px) so it does not take much space.
When `total == 0`, the bar is hidden.

```python
self._progress_bar = QProgressBar(self)
self._progress_bar.setTextVisible(True)
self._progress_bar.setFixedHeight(16)
layout.addWidget(self._progress_bar)
```

### Pros
- The filled bar gives immediate visual feedback on proportion completed —
  more expressive than a plain number.
- Text inside the bar (`3 / 11 done`) keeps all information in one place.
- At 100% the bar fills solid, giving a clear "done!" signal.

### Cons
- A progress bar implies linear progress toward a goal; a todo tree is
  more fluid (items can be added at any time), which may make the bar feel
  misleading when the total changes.
- Slightly more vertical space than a label.
- `QProgressBar` styling in FreeCAD's custom themes can be inconsistent —
  the bar colour may not theme well in dark mode without additional style work.

### Effort: Low-Medium (~1.5 hours, extra time for theme testing)

---

## Option D — Count integrated into the breadcrumb bar

### Layout

```
┌──────────────────────────────────────┐
│  Root  >  Engineering  >  CAD model   3/11 │
│ [toolbar]                             │
│                                       │
│   ☐  Buy milk                         │
└──────────────────────────────────────┘
```

The `BreadcrumbWidget` is extended to accept and display a progress count
right-aligned within the same bar. The breadcrumb path takes the left
portion; the count floats to the right.

This requires modifying `BreadcrumbWidget` to accept a `set_progress(done,
total)` call, and rendering the count as right-aligned text in the
widget's `paintEvent` (or adding a `QLabel` pushed right with a spacer).

### Pros
- Count and navigation context are co-located — the user sees both the
  path ("where am I?") and the progress ("how far along?") in one line.
- No extra vertical space.

### Cons
- Most implementation complexity — requires changing `BreadcrumbWidget`,
  which is currently just a row of clickable labels.
- The breadcrumb path can be long (deep nesting), which will push the
  count off-screen on narrow panels.
- Combining two pieces of information in one bar reduces clarity of both.

### Effort: Medium (~2–3 hours)

---

## Comparison

| Criterion | A — Status bar | B — Toolbar | C — Progress bar | D — Breadcrumb |
|-----------|---------------|-------------|-----------------|----------------|
| Vertical space used | 1 row | 0 (existing row) | 1 row | 0 (existing row) |
| Visibility | Bottom | Top | Bottom | Top |
| Visual expressiveness | Low (text) | Low (text) | High (bar + text) | Low (text) |
| Narrow panel behaviour | May clip | May overflow | May clip | Likely clips |
| Implementation complexity | Low | Low | Low-Medium | Medium |
| Theme risk | Low | Low | Medium | Low |

---

## Recommendation

**Option A (status bar label)** is the recommended starting point.

- Lowest implementation risk.
- A bottom status bar is a widely understood UX convention — editors,
  file managers, and IDEs all use this pattern for secondary summary
  information.
- The text format `3 / 11 done · 3 hidden` is maximally explicit without
  competing with the toolbar or breadcrumb for space.

If the visual expressiveness of a filled bar is important, **Option C**
is the next best choice. The progress bar adds no implementation
complexity beyond styling concerns.

**Option B** is worth considering if vertical space is tight (e.g. the
panel is used in a narrow docked configuration), since it adds zero height.

**Option D** is not recommended — it overcrowds the breadcrumb bar and
has the most complex implementation for the least benefit.

---

## Files to change (Option A)

| File | Change |
|------|--------|
| `tree_panel.py` | Add `QLabel` to layout; add `_update_progress` method; connect to model signals and navigation calls |
