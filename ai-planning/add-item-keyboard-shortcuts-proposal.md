# Keyboard Shortcuts for Add Item and Add Child

**Date:** 2026-05-20  
**Status:** Proposal — pending implementation decision

---

## Current shortcut landscape

| Key | Action |
|-----|--------|
| Tab | Indent (move under previous sibling) |
| Shift+Tab | Outdent (raise one level) |
| Enter / Numpad Enter | Go Into (make selected item the view root) |
| Backspace | Go Up (ascend one breadcrumb level) |
| Space | Toggle done state (Qt built-in for checkable items) |
| Alt+Up / Alt+Down | Move item up/down among siblings (Option B branch, not yet merged) |

There are currently **no keyboard shortcuts** for adding a new sibling item
or a new child item. Both actions require a mouse click on the toolbar or
context menu.

---

## Does Qt have built-in defaults for these operations?

No. `QTreeView` (and Qt item views in general) have no default key for
inserting rows. The only built-in key relevant to editing is:

- **F2** — start inline editing of the current item (standard Qt rename key).
  We use double-click for this instead, but F2 would also work with our current
  `setEditTriggers` setting once an item is selected.
- **Space** — toggle a checkable item (already in use for done/not-done).
- **Delete** — no default action in `QTreeView` (some platforms bind it to
  "clear selection" but we don't intercept it).

Qt has no built-in concept of "add sibling" or "add child" — those are always
application-defined.

---

## Constraints

1. **Enter/Return is taken** (Go Into). Any shortcut using bare Return would
   conflict.
2. **Tab is taken** (indent). Ctrl+Tab and Shift+Tab (outdent) are also taken.
3. Shortcuts must be `Qt.WidgetShortcut` scoped to the tree view to avoid
   stealing keys from the rest of FreeCAD while the panel has focus.
4. The shortcut should immediately open the new item's label for inline
   editing (matching the toolbar button behaviour).

---

## Option A — `Insert` and `Ctrl+Insert`

The **Insert** key is the traditional "add row" key in tree views and
spreadsheets across all platforms (Windows Explorer, file managers, many IDEs).

| Key | Action |
|-----|--------|
| Insert | Add sibling item at the same level as the selection |
| Ctrl+Insert | Add child item under the selection |

**Rationale:**
- `Insert` is unambiguous and has decades of tree-editor convention behind it.
- `Ctrl+Insert` extends the pattern logically.
- Neither conflicts with any existing shortcut.
- Works on all platforms (Insert is present on all standard keyboards including
  laptop keyboards via Fn combos).

**Downside:**
- On compact/laptop keyboards, Insert requires a Fn key combination, which is
  slightly awkward for a frequently used action.
- **MacBook Pro has no Insert key at all.** The conventional macOS substitute
  (Fn+Return) is already taken by Go Into. There is no reliable cross-generation
  Mac equivalent that FreeCAD will see as `Key_Insert`. Option A is effectively
  unusable on macOS.

---

## Option B — `Shift+Return` and `Ctrl+Return`

Outliner apps (OmniOutliner, WorkFlowy, Notion) commonly use Return-based
shortcuts for adding items:

| Key | Action |
|-----|--------|
| Shift+Return | Add sibling item at the same level as the selection |
| Ctrl+Return | Add child item under the selection |

**Rationale:**
- Consistent with the outliner mental model: Return-variants mean "create
  something new."
- Ergonomically comfortable — Return is on the home row area.
- `Shift+Return` and `Ctrl+Return` do not conflict with any existing binding.
- Familiar to users coming from Notion, Bear, or OmniOutliner.

**Downside:**
- Bare Return is "Go Into", so users must remember that Return alone has a
  navigation meaning while modified Return has a creation meaning. This could
  be confusing at first.
- `Ctrl+Return` is sometimes a system-level shortcut on some platforms
  (e.g., submit a form). In FreeCAD this is unlikely to matter.

---

## Option C — `Ctrl+N` and `Ctrl+Shift+N`

`Ctrl+N` is the universal "New" shortcut in most applications:

| Key | Action |
|-----|--------|
| Ctrl+N | Add sibling item at the same level as the selection |
| Ctrl+Shift+N | Add child item under the selection |

**Rationale:**
- Immediately legible to any user: Ctrl+N = "New thing."
- Adding Shift for the child variant follows the pattern used in many apps
  (e.g., Ctrl+T for new tab, Ctrl+Shift+T for new tab in background).
- Works on all keyboard layouts.

**Downside:**
- `Ctrl+N` is FreeCAD's global shortcut for **New Document**. Using it as a
  widget-scoped shortcut may conflict — FreeCAD processes global shortcuts
  first, and `WidgetShortcut` context may not reliably intercept it when the
  tree view has focus, depending on the FreeCAD version.
- This option should be tested carefully before shipping. If the conflict
  cannot be resolved, Option A or B is safer.

---

## Recommendation

**Option A** (Insert / Ctrl+Insert) is the safest choice:
- No conflict risk with existing bindings.
- Well-established convention for tree editors.
- The `Insert` key is present on all desktop keyboards.

**Option B** (Shift+Return / Ctrl+Return) is the most ergonomic choice for
users working in an outliner flow, and is worth considering if the Return-key
mental model feels natural for the use case.

**Option C** risks FreeCAD global shortcut conflicts and should only be
considered if A and B are rejected.

---

## Implementation

All three options require the same two lines added to `_setup_ui` in
`tree_panel.py`, after the existing shortcut wiring:

```python
sc_add = QShortcut(QKeySequence(Qt.Key_Insert), self._tree_view)
sc_add.setContext(Qt.WidgetShortcut)
sc_add.activated.connect(self._add_sibling)

sc_add_child = QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Insert), self._tree_view)
sc_add_child.setContext(Qt.WidgetShortcut)
sc_add_child.activated.connect(self._add_child)
```

(Substitute the key constants for whichever option is chosen.)

The shortcuts should also be mentioned in `Documentation/Commands/AddItem.md`
and in the README keyboard shortcuts section.
