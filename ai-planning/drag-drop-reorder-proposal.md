# Drag-and-Drop Reorder Proposal

**Date:** 2026-05-20  
**Status:** Implemented — Option C selected and merged to main

---

## Problem

Items in the TodoTree panel cannot be reordered by the user. The only way to change an item's position in the hierarchy is through the indirect Indent/Outdent operations, which only move an item one level at a time and never change its position among siblings. This makes nesting effectively useless: you can create a hierarchy, but you cannot freely reorganise it. Specifically:

- You cannot move an item to a different position among its siblings.
- Moving an item to a different parent requires navigating into the target parent and adding items there, then deleting the original — a destructive, awkward workflow.
- Indent/Outdent only move relative to the immediately adjacent sibling; reaching a distant parent requires repeated operations.

---

## Constraints and context

- The view uses `QTreeView` with a `DoneFilterProxy` (a `QSortFilterProxyModel`) sitting between the view and `TodoItemModel` (a `QAbstractItemModel`).
- Structural mutations (`beginMoveRows`/`endMoveRows`) are already used for indent/outdent and are undo-tracked via FreeCAD transactions.
- FreeCAD's Python environment exposes PySide2 or PySide6 as `PySide`; both support Qt's built-in drag-and-drop machinery.
- Any drag-and-drop implementation must work correctly through the proxy layer, and must integrate with the undo stack.
- The dual-panel design (dock + main view) means both panels share one `TodoItemModel`; a move performed in either panel must be immediately reflected in the other.

---

## Option A — Qt built-in model drag-and-drop (flags + `mimeData`/`dropMimeData`)

### How it works

Qt's `QAbstractItemModel` has built-in drag-and-drop support activated by returning `Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled` from `flags()`, implementing `mimeData()` to serialise the dragged node IDs, and implementing `dropMimeData()` to apply the move.

`QTreeView` then handles all the visual affordances (drag ghost, drop indicator line) automatically when `setDragDropMode(QAbstractItemView.InternalMove)` is set.

Because there is a proxy model, `DoneFilterProxy` must also forward `mimeData` and `dropMimeData` calls to the source model (the default `QSortFilterProxyModel` implementation does this for `mimeData` but not for `dropMimeData` — the latter must be overridden).

### Required changes

1. **`TodoItemModel`**
   - Add `Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled` to `flags()`.
   - Add `supportedDropActions()` returning `Qt.MoveAction`.
   - Implement `mimeData(indexes)` — serialise the node ID (UUID) of each dragged row as JSON in a custom MIME type (`application/x-todotree-node`).
   - Implement `dropMimeData(data, action, row, column, parent)` — decode the node ID, call a new `move_node(node_id, new_parent_id, insert_row)` mutation on `TodoTree`, wrap in a FreeCAD transaction, and call `beginMoveRows`/`endMoveRows`.
   - Add `move_node(node_id, new_parent_id, insert_row)` to `TodoTree` (pure Python, no Qt).

2. **`DoneFilterProxy`**
   - Override `dropMimeData()` to translate the proxy-layer `parent` index back to a source index and forward to the source model, and translate `row` using `mapToSource`.
   - Override `supportedDropActions()` to forward to source model.
   - Override `flags()` to include the drag/drop flags (or just let the base class forward them, which it does by default).

3. **`TreePanel`**
   - Call `self._tree_view.setDragEnabled(True)` and `self._tree_view.setAcceptDrops(True)`.
   - Call `self._tree_view.setDragDropMode(QAbstractItemView.InternalMove)`.
   - Call `self._tree_view.setDropIndicatorShown(True)`.
   - No drag handle is needed — Qt renders the drag ghost from the item text automatically.

### Pros
- Minimal code. Qt handles all visual feedback, hit-testing, and auto-scroll.
- Drag handles are not strictly needed because Qt makes the entire row draggable; users click-and-drag anywhere on the row.
- Works correctly with keyboard-only expand/collapse.

### Cons
- The proxy layer (`DoneFilterProxy`) requires careful `dropMimeData` forwarding; getting the row index translation right when "show done" is off is fiddly.
- Qt's built-in drop indicator does not distinguish "drop before", "drop after", and "drop into (make child)" visually as clearly as a custom delegate would — users may find it ambiguous.
- No explicit drag handle; discovery is poor (users may not know rows are draggable).
- Cross-parent moves (dragging to a different subtree) work, but the visual feedback about where the item will land is sometimes unclear with the default indicator.

### Effort estimate
Medium — approximately 150–200 lines of new code, most of it in `dropMimeData` logic and the `move_node` model mutation.

---

## Option B — Keyboard-only reorder with Up/Down move actions (no drag)

### How it works

Rather than drag-and-drop, add explicit **Move Up** and **Move Down** toolbar buttons (and keyboard shortcuts) that swap the selected item with its adjacent sibling within the same parent. This is analogous to the Up/Down arrow reorder pattern in many list editors (e.g., Xcode build phase lists, preference panes).

A drag handle icon (⠿ or ≡) is added to the left of each item via a custom delegate so users understand items are orderable, even though the actual reordering is done via buttons.

### Required changes

1. **`TodoTree`** — add `move_node_up(node_id)` and `move_node_down(node_id)` mutations that swap the node with its adjacent sibling. These are trivial list index swaps.

2. **`TodoItemModel`** — add `move_up(index)` and `move_down(index)` methods using `beginMoveRows`/`endMoveRows`, wrapped in FreeCAD transactions.

3. **`TreePanel`**
   - Add "↑ Move Up" and "↓ Move Down" toolbar actions.
   - Wire them to the new model methods.
   - Update enabled state in `_update_indent_actions`.
   - Optionally add `Alt+Up` / `Alt+Down` shortcuts.

4. **Custom delegate (optional visual handle)**
   - Subclass `QStyledItemDelegate`, override `paint()` to draw a grip icon (three horizontal lines) in the left margin.
   - Adjust `sizeHint()` to add left padding.

### Pros
- Zero proxy complexity — no MIME types, no drop hit-testing.
- Completely predictable: one press = one position swap.
- Works fully with keyboard navigation.
- Undo/redo integrates trivially.
- A grip icon can be added as a pure visual cue without needing it to be interactive.

### Cons
- Moving an item many positions requires many button presses; moving across parents is impossible directly (requires Indent/Outdent + Move Up/Down).
- Does not satisfy the request for drag-and-drop — the UX is more cumbersome for large reorders.
- Cross-parent reparenting still requires the indirect Indent/Outdent workflow.

### Effort estimate
Low — approximately 80–120 lines of new code. This is the lowest-risk option.

---

## Option C — Custom drag handle with `QTreeView` internal drag-and-drop

### How it works

This is a more polished version of Option A. A custom `QStyledItemDelegate` draws a visible drag handle (e.g., ⠿) in the left margin of every row. Mouse press events on the handle column initiate a drag via `QDrag`. The drop logic is the same as Option A (`mimeData`/`dropMimeData`), but the drag is initiated only from the handle region, preventing accidental drags when clicking to select or edit.

Initiating the drag from a specific region requires overriding `mousePressEvent` / `mouseMoveEvent` on the `QTreeView` (or a viewport event filter) to detect whether the press landed on the handle column and start the drag manually via `QDrag` if so, suppressing the normal Qt auto-drag.

### Required changes

Everything in Option A, plus:

1. **Custom delegate (`DragHandleDelegate`)**
   - Override `paint()` to draw a grip icon in the first ~16px of the row (before the checkbox and text).
   - Override `sizeHint()` to include the handle width.

2. **Viewport event filter or `QTreeView` subclass**
   - On `QEvent.MouseButtonPress`: check if the x coordinate falls within the handle zone. If yes, record the drag start.
   - On `QEvent.MouseMove`: if a drag was started from the handle zone and the mouse has moved past `QApplication.startDragDistance()`, initiate `QDrag` with the node's MIME data manually. Suppress the normal selection drag.
   - If the x coordinate is not in the handle zone, let normal Qt selection/edit handling proceed.

3. **`DoneFilterProxy`** — same forwarding changes as Option A.

4. **`TodoTree` / `TodoItemModel`** — same `move_node` mutation as Option A.

### Pros
- Best discoverability: every item has a visible drag handle so users immediately know items can be reordered.
- Drag is restricted to the handle, so selecting, checkbox-toggling, and inline editing are not accidentally interrupted by drags.
- Cross-parent and cross-level moves in a single gesture.
- Consistent with modern task-manager UX (Notion, Linear, Todoist all use drag handles).

### Cons
- Most complex implementation: custom delegate, event filter for hit-zone detection, MIME encoding, proxy forwarding, and `move_node` mutation — all need to work together.
- The handle zone width must be tuned so it doesn't overlap the Qt checkbox column.
- Requires more testing: drag from handle, drop before/after/into, proxy filter active, undo/redo.

### Effort estimate
High — approximately 300–400 lines across delegate, event filter, model mutation, and proxy forwarding.

---

## Comparison table

| Criterion                     | A — Qt built-in DnD | B — Move Up/Down keys | C — Handle + DnD |
|-------------------------------|---------------------|-----------------------|------------------|
| Discoverability               | Low                 | Medium (toolbar)      | High             |
| Cross-parent moves            | Yes                 | No (Indent/Outdent)   | Yes              |
| Implementation complexity     | Medium              | Low                   | High             |
| Proxy forwarding risk         | Medium              | None                  | Medium           |
| Undo integration              | Straightforward     | Straightforward       | Straightforward  |
| Accidental drag interference  | Possible            | N/A                   | Minimal          |
| Matches the original request  | Partial             | Partial               | Fully            |

---

## Recommendation

**Option C** best matches the stated goal (drag handles on every item, free rearrangement), but **Option A** delivers 80% of the value for roughly half the effort and is a reasonable starting point. A staged approach is also viable: implement Option B first (lowest risk, immediate improvement), then layer Option A or C on top.

If the drag handle is a hard requirement, go directly to Option C and budget accordingly for testing the proxy forwarding and hit-zone logic.

## Decision

**Option C was selected and implemented.** Both options were prototyped on separate branches (`feature/reorder-drag-handle` and `feature/reorder-move-up-down`) for side-by-side testing. Option C was chosen for production; it was merged to `main` on 2026-05-20. Option B remains on its branch for reference but is not shipped.
