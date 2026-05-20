# Expansion State and Undo/Redo Proposal

**Date:** 2026-05-20  
**Status:** Proposal — pending implementation decision

---

## What was tried and why it failed

Two previous attempts have been made:

### Attempt 1 — connect `expanded`/`collapsed` signals to `_save_view_state`

Rationale: `ViewState` was only written on navigation events (breadcrumb, Go
Into, Go Up, Show Done). Connecting the QTreeView signals would keep it current.

**Why it failed:** `endResetModel()` (called inside `reload_from_property()` on
every undo) causes Qt to collapse every visible row. This fires the `collapsed`
signal for each row → `_on_expansion_changed` → `_save_view_state` →
`_collect_expanded_ids()` (returns empty, everything is now collapsed) → writes
empty `expanded_ids` to `ViewState`. Then `_on_tree_reset` reads `ViewState`,
gets an empty list, and nothing is re-expanded. My fix actively destroyed the
saved expansion state during every model reset.

### Attempt 2 — read `ViewState` in `_on_tree_reset` (original behaviour)

The original code read `ViewState` in `_on_tree_reset` to restore expansion.

**Why it failed:** `ViewState` is saved OUTSIDE the undo stack (intentionally,
to avoid polluting undo history with view changes). A structural mutation writes
`TreeData` inside a transaction; `ViewState` is written separately without one.
When FreeCAD undoes the transaction it reverts `TreeData` but leaves `ViewState`
at whatever it was last set to. For a single undo this might be close to the
pre-mutation state, but it is not exact, and it breaks completely for multiple
consecutive undos because `ViewState` does not have a stack — it always holds
only the most-recently-saved expansion, not a per-undo snapshot.

---

## Root cause

**Expansion state is not in the undo stack.** `ViewState` is a single flat
property written outside transactions. FreeCAD's undo stack only tracks
`TreeData`. When structural mutations are undone, `TreeData` reverts correctly
but there is no corresponding per-snapshot expansion state to restore. The view
cannot know what was expanded at the time of the original operation.

---

## The correct fix: add `expanded` to `TreeData`

Move expansion state into `TreeData` — the property that IS on the undo stack.
Each node serialises an `expanded` flag. Structural mutations naturally capture
the current expansion state as part of their transaction because they call
`_flush_to_property()` after updating the tree. Undo reverts `TreeData`,
restoring both structure and expansion in one atomic step.

Pure expand/collapse operations (the user clicking the disclosure triangle) are
NOT transactional — they update `expanded` on the node and flush `TreeData`
without opening a FreeCAD transaction, so they do not appear on the undo stack.
This is the correct behaviour: expanding a node should not be undoable.

---

## Detailed implementation plan

### 1. `todo_model.py` — add `expanded` to `TodoNode`

```python
class TodoNode:
    __slots__ = ("id", "text", "done", "expanded", "children", "_parent")

    def __init__(self, node_id, text, done=False, expanded=False):
        ...
        self.expanded = expanded
```

Update `to_dict`:
```python
def _node(n):
    return {
        "id": n.id,
        "text": n.text,
        "done": n.done,
        "expanded": n.expanded,          # new
        "children": [_node(c) for c in n.children],
    }
```

Update `from_dict`:
```python
n = TodoNode(d["id"], d["text"], d.get("done", False), d.get("expanded", False))
```

Add a mutation:
```python
def set_expanded(self, node_id, expanded: bool):
    node = self._id_map.get(node_id)
    if node:
        node.expanded = expanded
```

### 2. `todo_item_model.py` — expose `set_expanded`, flush without transaction

```python
def set_node_expanded(self, index, expanded: bool):
    """Update a node's expanded flag and flush to TreeData (no transaction)."""
    if not index.isValid():
        return
    node = index.internalPointer()
    if node.expanded == expanded:
        return
    self._tree.set_expanded(node.id, expanded)
    self._flush_to_property()
```

`_flush_to_property` already guards re-entry via `is_flushing()`, so calling it
here does not cause a reload loop.

### 3. `tree_panel.py` — wire expansion changes to the model

Replace the current `_on_expansion_changed` handler:

```python
def _on_expansion_changed(self, proxy_index):
    if self._restoring_expansion:
        return
    src_idx = self._proxy.mapToSource(proxy_index)
    expanded = self._tree_view.isExpanded(proxy_index)
    self._model.set_node_expanded(src_idx, expanded)
```

Add a guard flag `self._restoring_expansion = False` in `__init__`.

Replace `_restore_expanded` with `_restore_expanded_from_model`:

```python
def _restore_expanded_from_model(self):
    """Expand all nodes whose model expanded flag is True."""
    self._restoring_expansion = True
    try:
        tree = self._model._tree
        def _walk(node):
            if node is tree.root:
                for child in node.children:
                    _walk(child)
                return
            src_idx = self._model.index_for_node(node.id)
            if src_idx.isValid():
                proxy_idx = self._proxy.mapFromSource(src_idx)
                if node.expanded:
                    self._tree_view.setExpanded(proxy_idx, True)
                for child in node.children:
                    _walk(child)
        _walk(tree.root)
    finally:
        self._restoring_expansion = False
```

Update `_restore_view_state` to call `_restore_expanded_from_model()` instead
of `_restore_expanded(expanded_ids)`.

Update `_on_tree_reset` to call `_restore_expanded_from_model()` instead of
reading `ViewState`.

Remove `_restore_expanded`, `_collect_expanded_ids`, `_walk_expanded`, and
`expanded_ids` from `ViewState` entirely — they are no longer needed.

### 4. `tree_panel.py` — sync expansion before structural mutations

Because the `_on_expansion_changed` handler writes expansion per-node as the
user clicks, the model's `expanded` flags are already current by the time any
structural mutation happens. No explicit sync step is needed — this is the key
advantage of writing per-node immediately rather than batching.

The auto-expand after indent (`self._tree_view.setExpanded(proxy_parent, True)`)
will fire `_on_expansion_changed` → `set_node_expanded`. However, this fires
AFTER `indent_node` has already called `_flush_to_property`. So the auto-expand
will trigger a SECOND flush (without a transaction). This is acceptable but means
there are two writes. To avoid this, call `set_node_expanded` on the new parent
BEFORE calling `self._model.indent_node`:

```python
def _indent_selected(self):
    src_idx = self._current_source_index()
    if self._can_indent(src_idx):
        node_id = self._model.data(src_idx, Qt.UserRole)
        # Mark new parent as expanded before the indent flushes
        prev_sibling = ...  # the node that will become the new parent
        self._model.set_node_expanded(prev_sibling_idx, True)
        self._model.indent_node(src_idx)
        ...
```

Alternatively, simply accept the second flush — it is harmless.

### 5. `tree_panel.py` — clean up `_save_view_state`

Remove `expanded_ids` from the saved/restored ViewState dict. The field can
remain for backward compatibility on read but should not be written.

```python
state = {
    "current_root_id": self._breadcrumb_path[-1],
    "breadcrumb_path": self._breadcrumb_path,
    "show_done": self._act_show_done.isChecked(),
    # expanded_ids removed — now stored in TreeData per-node
}
```

---

## Worked example: undo of indent

```
Before indent:
  TreeData = {root: [A(expanded=True) → [B, C], D]}
  View: A is expanded, showing B and C

User indents D under C:
  _on_expansion_changed fires (nothing changes expansion here)
  indent_node flushes: TreeData = {root: [A(expanded=True) → [B, C → [D]], D removed]}
  After indent, _indent_selected calls setExpanded on C's proxy
  _on_expansion_changed fires → set_node_expanded(C, True) → flush
  TreeData = {root: [A(expanded=True) → [B, C(expanded=True) → [D]]]}

User presses Ctrl+Z:
  FreeCAD reverts TreeData = {root: [A(expanded=True) → [B, C], D]}
  onChanged → reload_from_property → beginResetModel / endResetModel
  (endResetModel collapses view, but _restoring_expansion flag or signal
   block prevents _on_expansion_changed from writing back)
  treeReset → _on_tree_reset → _restore_expanded_from_model
  Walks tree: A.expanded=True → expands A
              B.expanded=False → skip
              C.expanded=False → skip (was reverted by undo!)
              D.expanded=False → skip
  Result: view shows A expanded (B and C visible), D at root level ✓
```

The expansion state at the time of the indent is correctly restored because it
was embedded in `TreeData` at the time of the flush.

---

## What to do about the `expanded`/`collapsed` signal fix from the previous attempt

The connection added in the previous fix:
```python
self._tree_view.expanded.connect(self._on_expansion_changed)
self._tree_view.collapsed.connect(self._on_expansion_changed)
```

**Keep these connections** — they are the right mechanism. The previous
implementation was wrong because `_on_expansion_changed` called `_save_view_state`
(which caused the cascade during model reset). In the new design, it calls
`set_node_expanded` instead, which is guarded by `_restoring_expansion` and
the existing `is_flushing()` guard, breaking the feedback loop.

---

## Trade-offs

| Concern | Impact |
|---------|--------|
| TreeData gets slightly larger | `expanded` is a bool per node; negligible |
| Expand/collapse writes TreeData without a transaction | Two disk writes instead of zero for a bare expand. Fine for a non-geometric data store. |
| Expansion is now per-document, not per-panel | If dock and main view share the model, they share expansion state. This is almost always what users want. |
| Backward compatibility | `from_dict` defaults `expanded=False` for old documents. All nodes start collapsed, which is the natural initial state. |

---

## Files to change

| File | Change |
|------|--------|
| `todo_model.py` | Add `expanded` to `TodoNode`, `to_dict`, `from_dict`, `set_expanded` |
| `todo_item_model.py` | Add `set_node_expanded` |
| `tree_panel.py` | Replace `_restore_expanded` / `_collect_expanded_ids` / `_walk_expanded` with `_restore_expanded_from_model`; update `_on_expansion_changed`; add `_restoring_expansion` flag; clean up `ViewState` |
