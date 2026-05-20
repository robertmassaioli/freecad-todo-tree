# Indent / Outdent Undo-Redo Proposal

**Date:** 2026-05-20  
**Status:** Proposal — pending implementation decision

---

## Is it implemented?

Yes — partially. Indent and outdent **do** open FreeCAD transactions and flush the
mutated tree to `TreeData` inside that transaction. The intent was always for
undo/redo to work. The bug is in the mechanism that reacts to undo, not in the
mutation itself.

---

## How the mechanism is supposed to work

```
User action (indent/outdent)
  → openTransaction / mutate tree / _flush_to_property() / commitTransaction()
  → TreeData written to FreeCAD property inside a transaction
  → FreeCAD records old TreeData value on undo stack

User presses Ctrl+Z
  → FreeCAD reverts TreeData to old value
  → FreeCAD fires onChanged(obj, "TreeData") on TodoTreeObject proxy
  → notify_tree_changed(doc_name) called
  → model.reload_from_property() called
  → beginResetModel() / rebuild tree from TreeData / endResetModel()
  → treeReset signal → TreePanel re-applies navigation / expansion state
```

This chain works correctly for **the forward operation**. It was also designed to
handle undo. The failure is that **step 3 of the undo path — FreeCAD calling
`onChanged` after reverting the property — is not guaranteed**.

---

## Root cause: `onChanged` is unreliable during undo

FreeCAD's behaviour when undoing a property change on a `FeaturePython` object
varies by version and context:

- In many FreeCAD builds, reverting an `App::PropertyString` via undo **does**
  call `onChanged` on the Python proxy, and the mechanism works.
- In others (particularly when a document recompute is triggered by the undo, or
  when the object is not in the active document's recompute queue), `onChanged`
  is **not** called, and the in-memory `TodoItemModel._tree` stays in the
  post-indent state even though `TreeData` has been reverted on disk.

The user sees: the view still shows the indented/outdented layout after Ctrl+Z,
because the Qt model was never told to reload.

### Why other operations appear to work

Add, delete, rename, and toggle-done use the exact same transaction and
`onChanged` path. If `onChanged` is not fired for indent/outdent it would also
not be fired for those operations. One of two explanations applies:

1. The user has not yet tested undo on add/delete/rename with the specific
   FreeCAD build where `onChanged` is unreliable — all operations may be broken.
2. `onChanged` fires reliably for simple property writes but not when the write
   is interleaved with `beginMoveRows`/`endMoveRows` Qt signals, because FreeCAD
   may process queued notifications differently when Qt's event loop is already
   mid-signal-dispatch.

Either way the fix is the same.

---

## What is NOT broken

- The transaction itself is correct. `TreeData` **is** stored in the undo stack.
  Ctrl+Z reverts the property on disk — the data is correct after undo.
- The `is_flushing()` guard in `notify_tree_changed` is correct. It prevents a
  reload loop when we ourselves write `TreeData`.
- The property flag (`4` = `Prop_Hidden`) is correct. It hides the raw JSON from
  the property editor but does not affect undo tracking. `Prop_Output` (8) would
  remove from the undo stack; we do not use that flag.

---

## Fix options

### Option A — Subscribe to FreeCAD's application-level undo/redo signals (recommended)

FreeCAD exposes `slotUndoDocument` and `slotRedoDocument` on document observers
(the same `_DocObserver` class already used in `dock_widget.py`). These fire
**after** the undo/redo is fully applied, meaning `TreeData` is already at its
reverted value when the slot runs.

**Changes required:**

1. **`dock_widget.py` — `_DocObserver`**: add two new slots:

```python
def slotUndoDocument(self, doc):
    from .model_registry import notify_tree_changed
    notify_tree_changed(doc.Name)

def slotRedoDocument(self, doc):
    from .model_registry import notify_tree_changed
    notify_tree_changed(doc.Name)
```

2. **`model_registry.py` — `notify_tree_changed`**: the existing guard
   `if not model.is_flushing()` is correct and still needed to prevent loops.
   No changes required here.

This is the minimal, lowest-risk fix. It makes undo/redo reliable regardless of
whether FreeCAD calls `onChanged` during undo, because the reload is now also
triggered by the explicit undo/redo signal.

**Risk:** `notify_tree_changed` calls `beginResetModel()`/`endResetModel()`,
which collapses the tree view (loses expanded state and selection). The existing
`_on_tree_reset` handler in `TreePanel` re-applies expanded IDs from `ViewState`,
which mitigates this but does not restore selection.

---

### Option B — Also fix the UX regression: preserve selection after undo/redo

The `beginResetModel()`/`endResetModel()` approach rebuilds the entire view from
scratch. This is correct but blunt: it loses the user's current selection and
scroll position. A user who indents item C then hits Ctrl+Z will see C snap back
to its original level but lose their cursor position.

**Additional changes on top of Option A:**

1. In `reload_from_property`, after `endResetModel()`, attempt to re-select the
   previously-selected node ID (captured before the reset):

```python
def reload_from_property(self, previously_selected_id=None):
    self.beginResetModel()
    self._tree = TodoTree.from_json(self._fc_object.TreeData)
    self.endResetModel()
    self.treeReset.emit(previously_selected_id)
```

2. In `TreePanel._on_tree_reset(node_id=None)`, after re-expanding, also
   re-select by node ID if the node still exists.

3. In `TreePanel`, capture the current selection's node ID before any operation
   that might trigger a subsequent undo, and pass it to `reload_from_property`
   via a `treeReset` signal argument.

This is more invasive but produces a much better undo UX. The selection returns
to the affected item, which is what users expect from undo in a tree editor.

---

### Option C — Replace `beginResetModel` with targeted `beginMoveRows` in reload

Instead of resetting the entire model on undo, compute a diff between the
current in-memory tree and the reverted tree, and emit only the specific
`beginMoveRows`/`endMoveRows` (or insert/remove) signals needed to reconcile.

This would preserve expanded state and selection completely without any special
tracking.

**Complexity:** High. Diffing two ordered trees to produce a minimal edit script
is non-trivial and fragile. This is not recommended unless Options A+B prove
insufficient.

---

## Recommended path

Implement **Option A** first — it fixes the actual bug with minimal code.
Assess whether the UX (selection loss after undo) is acceptable; if not, layer
**Option B** on top. Option C is not worth the complexity.

---

## Files affected by Option A

| File | Change |
|------|--------|
| `dock_widget.py` | Add `slotUndoDocument` and `slotRedoDocument` to `_DocObserver` |

## Files affected by Option B (additional)

| File | Change |
|------|--------|
| `todo_item_model.py` | `reload_from_property` accepts optional `previously_selected_id` |
| `tree_panel.py` | `_on_tree_reset` accepts and re-selects node; `treeReset` signal carries node ID |
