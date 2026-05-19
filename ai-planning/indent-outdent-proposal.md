# Indent / Outdent Proposal

**Date:** 2026-05-19  
**Status:** Proposal — pending implementation decision

---

## Overview

This proposal adds **indent** and **outdent** operations to the TodoTree addon, giving users outliner-style control over the hierarchy level of any todo item. These are the same operations found in OmniOutliner, Workflowy, Notion, and similar tools.

- **Outdent (raise level):** Move a node up one level — it becomes a sibling of its former parent, inserted immediately after it.
- **Indent (lower level):** Move a node down one level — it becomes the last child of its previous sibling.

In both cases the node's entire subtree of children travels with it unchanged.

---

## Concrete Examples

### Outdent

```
Before                         After
──────────────────────         ──────────────────────
Root                           Root
  ├── A                          ├── A
  │   ├── B                      │   └── B
  │   └── C  ← outdent C         └── C        ← moved up, after A
  │         └── D                      └── D  ← travels with C
  └── E                          └── E
```

C leaves A's children list and is inserted in A's parent's children list, at the position immediately after A. D comes along as C's child.

### Indent

```
Before                         After
──────────────────────         ──────────────────────
Root                           Root
  ├── A                          ├── A
  ├── B       ← indent B         │   └── B    ← appended to A's children
  │     └── C                    │         └── C  ← travels with B
  └── D                          └── D
```

B leaves Root's children list and is appended to the children list of A (its previous sibling). C comes along as B's child.

---

## Operation Rules

### Outdent — when it is allowed

| Condition | Allowed? |
|---|---|
| Node is a direct child of the tree root | No — already at top level |
| Node is a direct child of the current **view root** (Go Into mode) | No — would move it outside the visible subtree |
| Node is deeper than the view root (grandchild or deeper) | Yes |

The view-root constraint ensures that while the user is focused on a subtree via "Go Into", they cannot accidentally reorganise items above that boundary. From the user's perspective, the view root acts like a temporary root — outdenting its direct children would mean moving them "off screen" into an ancestor they cannot currently see.

### Indent — when it is allowed

| Condition | Allowed? |
|---|---|
| Node is the first child of its parent (no previous sibling) | No — nothing to indent under |
| Node has a previous sibling | Yes |

There is no view-root restriction on indent, because indenting always moves a node deeper into the tree (never above the view root).

---

## Data Model Changes (`todo_model.py`)

Two new methods on `TodoTree`:

```python
def outdent_node(self, node_id: str) -> bool:
    """
    Move node up one level: insert it after its parent in the grandparent's
    children list. Returns False if the operation is not permitted (node is
    already a direct child of tree root).
    """
    node = self._id_map.get(node_id)
    if node is None:
        return False
    parent = node._parent
    if parent is None or parent is self.root:
        return False  # already at top level

    grandparent = parent._parent
    if grandparent is None:
        grandparent = self.root

    parent.children.remove(node)
    insert_pos = grandparent.children.index(parent) + 1
    grandparent.children.insert(insert_pos, node)
    node._parent = grandparent
    return True


def indent_node(self, node_id: str) -> bool:
    """
    Move node down one level: append it to the children of its previous
    sibling. Returns False if the operation is not permitted (node is the
    first child of its parent).
    """
    node = self._id_map.get(node_id)
    if node is None:
        return False
    parent = node._parent
    if parent is None:
        parent = self.root

    siblings = parent.children
    idx = siblings.index(node)
    if idx == 0:
        return False  # no previous sibling

    new_parent = siblings[idx - 1]
    siblings.remove(node)
    new_parent.children.append(node)
    node._parent = new_parent
    return True
```

Both operations are reversible (outdent undoes indent and vice versa), which means undo/redo via FreeCAD transactions works naturally — the transaction captures the before/after JSON state of `TreeData`.

---

## Qt Model Changes (`todo_item_model.py`)

### Signal strategy

Indent and outdent are cross-parent moves. Qt's `beginMoveRows` / `endMoveRows` is the correct API for this but requires precise row accounting across two different parent indexes simultaneously, which is error-prone. Two approaches are available:

**Option A — `beginMoveRows` / `endMoveRows`**

Correct, efficient, preserves selection and expansion state in the view. More code.

```python
# outdent: row moves from parent to grandparent
self.beginMoveRows(parent_idx, row_in_parent, row_in_parent,
                   grandparent_idx, insert_row_in_grandparent)
self._tree.outdent_node(node_id)
self._flush_to_property()
self.endMoveRows()
```

**Option B — `beginResetModel` / `endResetModel` + `treeReset` signal**

Simpler, at the cost of collapsing all expanded nodes and losing the selection. The panel's `_on_tree_reset` handler already re-applies the breadcrumb root after resets (used for undo/redo), so the view resets cleanly.

```python
doc.openTransaction("Todo: outdent item")
self.beginResetModel()
self._tree.outdent_node(node_id)
self._flush_to_property()
doc.commitTransaction()
self.endResetModel()
self.treeReset.emit()
```

**Recommendation: Option A for indent/outdent.**

These are frequent interactive operations and losing all expansion state on every indent/outdent would feel jarring. The `beginMoveRows` math, while intricate, is deterministic and testable. The key invariant to track:

- **Outdent:** source parent index = parent node's QModelIndex; source row = node's position in parent.children; destination parent = grandparent's QModelIndex; destination row = parent's position in grandparent.children + 1.
- **Indent:** source parent index = current parent's QModelIndex; source row = node's current position; destination parent = previous sibling's QModelIndex; destination row = len(previous_sibling.children) (append at end, before the move).

Two new methods on `TodoItemModel`:

```python
def outdent_node(self, index: QModelIndex) -> bool: ...
def indent_node(self, index: QModelIndex) -> bool: ...
```

Both must also enforce the **view-root constraint** for outdent. The model itself does not know about the panel's current view root, so the constraint check must be performed in `TreePanel` before calling the model method.

---

## View Layer Changes (`tree_panel.py`)

### View-root constraint check

```python
def _can_outdent(self, src_index: QModelIndex) -> bool:
    """Return True if outdenting this node is allowed given the current view root."""
    node = self._model._tree.get_node(self._model.data(src_index, Qt.UserRole))
    if node is None or node._parent is None:
        return False
    parent = node._parent
    view_root_id = self._breadcrumb_path[-1]
    # Disallow if the node's parent IS the view root — outdenting would escape the subtree.
    return parent.id != view_root_id
```

### New toolbar actions

Two new `QAction` entries added to the panel toolbar (between the delete button and the separator before Go Into):

| Action | Label | Shortcut | Tooltip |
|---|---|---|---|
| Outdent | `← Outdent` | Shift+Tab | Raise this item one level in the hierarchy |
| Indent | `→ Indent` | Tab | Lower this item one level (under its previous sibling) |

Keyboard shortcuts only fire when the tree view has focus and an item is selected but not in inline-edit mode. Tab is already intercepted by Qt for focus traversal, so binding it to indent requires installing an event filter or using `QAction` with `Qt.WidgetWithChildrenShortcut` context.

### Action enabling / disabling

The actions should be dynamically enabled/disabled as the selection changes:

```python
self._tree_view.selectionModel().currentChanged.connect(self._update_indent_actions)

def _update_indent_actions(self, current, previous):
    if not current.isValid():
        self._act_outdent.setEnabled(False)
        self._act_indent.setEnabled(False)
        return
    src = self._proxy.mapToSource(current)
    self._act_outdent.setEnabled(self._can_outdent(src))
    node_id = self._model.data(src, Qt.UserRole)
    node = self._model._tree.get_node(node_id)
    parent = node._parent or self._model._tree.root
    idx = parent.children.index(node)
    self._act_indent.setEnabled(idx > 0)
```

---

## FreeCAD Command Changes (`commands.py`)

Two new command classes `_IndentItemCommand` and `_OutdentItemCommand` following the same pattern as `_AddItemCommand`. These delegate to the dock panel's `indent_item()` / `outdent_item()` public methods.

Both commands add new icons to `Resources/Icons/`:
- `Indent.svg` — a right-pointing indentation arrow
- `Outdent.svg` — a left-pointing indentation arrow

They are added to the workbench toolbar and menu in `init_gui.py`.

---

## Undo / Redo Behaviour

Because `TreeData` is a single JSON blob stored in a `App::PropertyString`, any indent or outdent replaces the entire blob inside a transaction. Ctrl+Z restores the previous JSON, which `reload_from_property` / `beginResetModel` picks up exactly as it does for all other undo operations. No special undo handling is needed beyond what already exists.

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| Outdent the only child of a parent | Allowed. Parent ends up with no children (becomes a leaf). |
| Indent a node that has children | Children travel with the node unchanged. |
| Outdent with Go Into active at grandparent level | Allowed — node moves to grandparent's children, still within view. |
| Outdent with Go Into active at parent level | Blocked by `_can_outdent`. Action is disabled. |
| Indent when the previous sibling has `done=True` | Allowed — done state is irrelevant to structural operations. |
| Indent/outdent while "Show Done" is off (proxy filtering active) | The operation targets the source model index (before proxy), so filtered-out items are not affected and the structural change is correct. |
| Outdent the last child of a parent where parent is itself the last child | Allowed. Results in two consecutive leaves under grandparent. |

---

## Files Changed

| File | Change |
|---|---|
| `todo_model.py` | Add `indent_node()` and `outdent_node()` |
| `todo_item_model.py` | Add `indent_node()` and `outdent_node()` with `beginMoveRows` |
| `tree_panel.py` | Add toolbar actions, keyboard shortcuts, `_can_outdent()`, `_update_indent_actions()`, public `indent_item()` / `outdent_item()` |
| `commands.py` | Add `_IndentItemCommand`, `_OutdentItemCommand`, register both |
| `init_gui.py` | Add commands to toolbar and menu |
| `Resources/Icons/Indent.svg` | New icon |
| `Resources/Icons/Outdent.svg` | New icon |

No changes to `todo_object.py`, `dock_widget.py`, `main_view.py`, `filter_proxy.py`, `breadcrumb_widget.py`, or `model_registry.py`.
