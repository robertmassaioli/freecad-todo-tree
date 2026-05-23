# Ten Improvements Proposal

**Date:** 2026-05-22  
**Status:** In progress — items 1, 7, and 8 completed on `feature/unit-tests`

This document proposes ten concrete improvements across functional,
usability, documentation, and engineering dimensions. Items already covered
by an existing focused proposal are cross-referenced rather than duplicated.

---

## 1. F2 keyboard shortcut to rename the selected item ✓ Done

**Area:** Usability  
**Effort:** Trivial (< 30 minutes)  
**Priority:** High  
**Completed:** 2026-05-22 on `feature/unit-tests`

### Problem

Renaming an item requires a double-click. Keyboard-centric users who have
just added or navigated to an item must reach for the mouse to trigger inline
edit mode. Every other tree editor (Windows Explorer, VS Code, Xcode) binds
**F2** to "rename the selected item".

### Solution

Add a `Qt.WidgetShortcut` for `Qt.Key_F2` on `self._tree_view` in
`TreePanel._setup_ui()`:

```python
sc_rename = QShortcut(QKeySequence(Qt.Key_F2), self._tree_view)
sc_rename.setContext(Qt.WidgetShortcut)
sc_rename.activated.connect(self._rename_selected)
```

```python
def _rename_selected(self):
    src_idx = self._current_source_index()
    if src_idx.isValid():
        self._start_edit(src_idx)
```

`_start_edit` already exists and opens the inline editor. This is a one-
method, two-line wiring change.

Update **README.md** keyboard shortcuts table and **Documentation/Commands/
AddItem.md** (which covers editing).

---

## 2. Live text search / quick-filter

**Area:** Functional  
**Effort:** Medium (3–5 hours)  
**Priority:** High for large trees

### Problem

There is no way to find a specific item by name. In a tree with 50+ items
spread across multiple levels, the user must manually expand and scan every
branch. As projects grow, this becomes a real friction point.

### Solution

Add a search bar — a `QLineEdit` — between the toolbar and the tree view.
It is hidden by default and revealed by `Ctrl+F` (WidgetShortcut). While
text is present in the search box, a second `QSortFilterProxyModel` is
stacked on top of the existing `DoneFilterProxy`, applying
`filterRegularExpression` (or `filterFixedString`) to match item text.

**Proxy chain:**

```
TodoItemModel
    └── DoneFilterProxy (existing — hides done items)
            └── TextSearchProxy (new — hides non-matching items)
                    └── QTreeView
```

When the text box is empty, the `TextSearchProxy` is a no-op (all rows pass
through). `TextSearchProxy` must override `filterAcceptsRow` to also accept
any row that has a **visible descendant** that matches, so the tree path to
a matching item remains navigable.

Pressing **Escape** clears the search box and hides it. Results update as
the user types (real-time filtering).

**Changes required:**
- `filter_proxy.py` — add `TextSearchProxy(QSortFilterProxyModel)`
- `tree_panel.py` — add `QLineEdit`, `Ctrl+F` shortcut, wire proxy chain

---

## 3. Export to Markdown (and plain text)

**Area:** Functional  
**Effort:** Medium (2–4 hours)  
**Priority:** Medium

### Problem

Todo lists created in the addon are trapped in the FreeCAD document. There
is no way to share them in a meeting, paste them into a PR description, send
them in an email, or archive them outside of FreeCAD. An export command would
open the addon to many new workflows.

### Solution

Add a **"Export Todo List…"** command (`TodoTree_Export`) that opens a
`QFileDialog` (Save As) and writes the current tree to a file. Support two
formats selectable via file extension:

**Markdown (`.md`)**

```markdown
# Design Review — Mounting Bracket v2

- [x] Sketch base profile
- [x] Extrude body (12 mm)
- [ ] Add mounting holes
    - [x] Top face holes
    - [ ] Side face holes
- [ ] Fillet exposed edges
```

**Plain text (`.txt`)** — indented with spaces, checkmark characters:

```
☑ Sketch base profile
☑ Extrude body (12 mm)
☐ Add mounting holes
    ☑ Top face holes
    ☐ Side face holes
☐ Fillet exposed edges
```

The export respects the current view root (exports from the breadcrumb
position, not necessarily the whole tree). The "Show Done" toggle is
respected — if done items are hidden, they are omitted from the export.

**Implementation:** A recursive tree walk in a new `export.py` module.
The export command is triggered from the menu. No FreeCAD transaction
is needed (export is read-only).

---

## 4. JSON schema versioning for forward/backward compatibility

**Area:** Robustness  
**Effort:** Low-Medium (2–3 hours for the infrastructure, plus work per schema change)  
**Priority:** Medium (critical before any schema changes)

### Problem

The `TreeData` JSON has no version field. If a future addon update changes
the schema (e.g. adds a new field, renames a key, changes the structure of
nodes), documents saved by the old version will silently fail or produce
wrong results when opened by the new version. There is no migration path,
no error message, and no way to detect the mismatch.

The current schema:
```json
{
  "id": "root",
  "text": "__root__",
  "done": false,
  "expanded": false,
  "children": [...]
}
```

### Solution

Add a top-level `"schema_version"` key to the JSON structure:

```json
{
  "schema_version": 1,
  "id": "root",
  "text": "__root__",
  "done": false,
  "expanded": false,
  "children": [...]
}
```

In `TodoTree.from_dict`, read `data.get("schema_version", 0)` and apply
migration functions for each version step:

```python
_MIGRATIONS = {
    # 0 → 1: add "expanded" field (already done implicitly via d.get())
    # 1 → 2: hypothetical future change
}

def _migrate(data, from_version, to_version):
    for v in range(from_version, to_version):
        migration = _MIGRATIONS.get(v)
        if migration:
            data = migration(data)
    return data
```

If `schema_version` is newer than the addon supports, show a warning in
the dock rather than silently corrupting the tree:

```
⚠ This document was saved by a newer version of TodoTree (schema v3).
  Some data may not display correctly. Update the addon to fix this.
```

**Changes required:**
- `todo_model.py` — add version key to `to_dict`, add migration runner to
  `from_dict`, define `CURRENT_SCHEMA_VERSION = 1`
- `dock_widget.py` — handle `SchemaVersionError` from the model, show
  warning placeholder

---

## 5. Copy / duplicate a subtree

**Area:** Functional  
**Effort:** Medium (2–4 hours)  
**Priority:** Medium

### Problem

There is no way to duplicate an item (and its entire subtree of children).
This is a common need when a task has a recurring structure — e.g. the same
"Design → Simulate → Document → Sign off" sub-tree appears under every
major component in a design project. Currently the user must manually re-
create the structure every time.

### Solution

Add **"Duplicate"** to the context menu and a `TodoTree_Duplicate` command.
It inserts a deep copy of the selected item and all its descendants,
placed immediately after the selected item as a sibling. All UUIDs in the
copy are regenerated (via `uuid.uuid4()`) to ensure uniqueness. The
operation is undo-tracked.

The deep copy is done in `TodoTree`:

```python
def duplicate_node(self, node_id):
    """Insert a deep copy of node_id after itself in its parent."""
    import copy as _copy
    node = self._id_map.get(node_id)
    if node is None or node is self.root:
        return None
    
    def _deep_copy(n, parent):
        new_id = str(uuid.uuid4())
        new_node = TodoNode(new_id, n.text, n.done, n.expanded)
        new_node._parent = parent
        self._id_map[new_id] = new_node
        new_node.children = [_deep_copy(c, new_node) for c in n.children]
        return new_node
    
    copy = _deep_copy(node, node._parent)
    idx = node._parent.children.index(node)
    node._parent.children.insert(idx + 1, copy)
    return copy
```

The `TodoItemModel` wraps this in `beginInsertRows` / `endInsertRows` and a
FreeCAD transaction.

---

## 6. Expand all / Collapse all actions

**Area:** Usability  
**Effort:** Low (1–2 hours)  
**Priority:** Low-Medium

### Problem

When a user navigates into a subtree or opens a document, they often want
to either see the entire tree expanded (to assess the full scope of work) or
fully collapsed (to get a high-level overview). Currently this requires
clicking every disclosure triangle individually.

### Solution

Add two toolbar actions and context menu entries:

- **Expand all** (`↓↓` or tree-expand icon) — recursively expands every
  item under the current view root.
- **Collapse all** (`↑↑` or tree-collapse icon) — collapses every item
  under the current view root to show only top-level children.

Implementation in `TreePanel`:

```python
def _expand_all(self):
    self._tree_view.expandAll()

def _collapse_all(self):
    self._tree_view.collapseAll()
```

`QTreeView.expandAll()` and `collapseAll()` are built-in Qt methods. The
expansion signals will fire for each item, updating `node.expanded` in the
model via the existing `_on_expansion_changed` handler, which means the
state persists correctly to `TreeData`.

Note: `expandAll()` on a very large tree (hundreds of items) may cause a
brief UI pause. For the typical todo list size this is not a concern.

---

## 7. Unit test suite ✓ Done

**Area:** Engineering quality  
**Effort:** High (initial setup + ongoing commitment)  
**Priority:** High (long-term maintainability)  
**Completed:** 2026-05-22 on `feature/unit-tests`

### Problem

The addon has no automated test suite. Complex interactions — undo/redo,
drag-and-drop row index arithmetic, filter proxy index translation, schema
migration — are verified only by manual testing. Every change to these areas
risks silent regressions. The `beginMoveRows` coordinate bug fixed recently
is exactly the kind of issue a test would have caught immediately.

### Solution

Add a `tests/` directory with a Python unittest or pytest suite. Because
`todo_model.py` has no FreeCAD or Qt dependencies, its full mutation and
serialisation surface can be tested without launching FreeCAD:

```
tests/
├── test_todo_model.py       — TodoNode, TodoTree: add, remove, indent,
│                             outdent, move, set_text, set_done, set_expanded,
│                             to_dict/from_dict, schema versioning
├── test_todo_item_model.py  — TodoItemModel with a mock FreeCAD object:
│                             flags, data, setData, beginMoveRows args
└── test_filter_proxy.py     — DoneFilterProxy: filter acceptance, dropMimeData
                               index translation
```

**Priority test cases (from known bugs):**

1. `test_move_node_same_parent_downward` — verify `beginMoveRows` args
   (the `insert_row - 1` fix is still easy to break)
2. `test_move_node_end_of_list` — verify no "Invalid index" Qt error
3. `test_indent_outdent_roundtrip` — indent then outdent returns to original
4. `test_schema_migration_v0_to_v1` — old documents load correctly
5. `test_duplicate_node` — deep copy has unique UUIDs, subtree is intact

**Continuous integration:** Add a `tox.ini` or `pyproject.toml` so tests
run on every push without FreeCAD installed. This is achievable because
the data layer has no FreeCAD imports.

---

## 8. Contributing and architecture documentation ✓ Done

**Area:** Documentation  
**Effort:** Low-Medium (2–4 hours)  
**Priority:** Medium  
**Completed:** 2026-05-22 on `feature/unit-tests`

### Problem

A developer who wants to extend the addon — add a new command, change the
data schema, add a new panel type — has no map to the codebase. They must
read several hundred lines of code to understand the relationship between the
data model, Qt model, proxy, panels, and FreeCAD integration. There is no
`CONTRIBUTING.md`, no architecture overview, and no explanation of the
transaction/undo contract.

### Solution

Add two documents:

**`CONTRIBUTING.md`** (repo root):
- How to set up a development environment (symlink install)
- How to run the test suite
- Coding conventions (SPDX headers, no comments unless non-obvious, etc.)
- PR workflow expectations

**`Documentation/Architecture.md`**:
- Full explanation of the data flow diagram already in README.md
- When to open a FreeCAD transaction (always for TreeData mutations)
- The `_flushing` guard and why it exists
- The two-property design (TreeData vs ViewState) and their different undo semantics
- How to add a new command (step-by-step: add class to `commands.py`,
  register in `init_gui.py`, add to toolbar/menu list)
- How to add a new field to `TodoNode` (update `__slots__`, `to_dict`,
  `from_dict`, increment schema version)
- The dual-panel architecture and why mutations go through the model not the panel

---

## 9. Intelligent breadcrumb truncation for narrow panels ✓ Done

**Area:** Usability  
**Effort:** Low-Medium (2–3 hours)  
**Priority:** Low  
**Completed:** 2026-05-22 on `feature/breadcrumb-truncation`, merged to `main`

### Problem

When the user navigates deep into a tree (e.g. `Root > Engineering > CAD
model > PartDesign body > Sketch`), the breadcrumb bar shows the full path.
On a narrow dock panel this overflows, clipping the right-most (most
contextually important) crumbs and making the bar useless.

### Problem illustration:

```
Root  >  Engineering  >  CAD model  >  PartDesign body  >  Sk  [clipped]
```

### Solution

Override `BreadcrumbWidget` to truncate the path intelligently when it does
not fit:
1. Always show the **first crumb** (Root or document name).
2. Always show the **last crumb** (current view root — the most important).
3. Replace middle crumbs that do not fit with a `…` ellipsis button that
   expands a dropdown showing the hidden ancestors:

```
Root  >  …  >  PartDesign body  >  Sketch
               └── Engineering
               └── CAD model
```

**Implementation:**

`BreadcrumbWidget` needs to override `resizeEvent` or use a `QHBoxLayout`
with `setSizeConstraint`. On each layout pass, measure the total width of
all crumbs and iteratively hide middle ones from the inside out, inserting
an ellipsis button that shows a popup menu of hidden crumbs when clicked.

This is purely a UI change — the full `_breadcrumb_path` list is still
stored in `TreePanel` and used for navigation; only the display is truncated.

---

## 10. Per-item notes / description field ✗ Won't do

**Area:** Functional  
**Effort:** Medium-High (4–6 hours)  
**Priority:** Low-Medium  
**Decision:** Overcomplicates the addon. Rejected 2026-05-23.

### Problem

Todo items currently have two fields: a text label and a done flag. There
is no way to attach additional context — acceptance criteria, links to
relevant FreeCAD objects, references to supplier part numbers, or notes on
why an item is blocked. Users work around this by creating child items
labelled "Note: …", which pollutes the hierarchy.

### Solution

Add an optional **notes** field to `TodoNode` (a free-text string, empty by
default). The notes are displayed and edited in an expandable area below the
item when the item is selected, similar to how many task managers show a
description pane.

**Data model changes** (`todo_model.py`):
```python
class TodoNode:
    __slots__ = ("id", "text", "done", "expanded", "notes", "children", "_parent")
```
Serialised as `"notes": ""` in the JSON (empty string, not stored if blank to keep
documents compact — use `if n.notes` in `to_dict`).

**UI:**
A `QTextEdit` (or `QPlainTextEdit`) below the tree view, shown only when
an item is selected. It displays the selected item's notes and saves on
focus-lost or `Ctrl+S`. The panel can be toggled with a toolbar button.

```
┌──────────────────────────────────┐
│ [breadcrumb]                      │
│ [toolbar]                         │
│ ☐  Add mounting holes             │
│   ☑  Top face holes               │ ← selected
│   ☐  Side face holes              │
├──────────────────────────────────┤
│ Notes for: "Top face holes"       │  ← QTextEdit, collapsible
│ M5 × 12mm socket head cap bolts  │
│ See supplier quote Q-2024-118.    │
└──────────────────────────────────┘
```

Notes edits are undo-tracked (FreeCAD transaction: `"Todo: edit notes"`).
Schema version must be bumped (see Improvement 4).

---

## Summary table

| # | Improvement | Area | Effort | Priority | Status |
|---|-------------|------|--------|----------|--------|
| 1 | F2 shortcut to rename | Usability | Trivial | High | ✓ Done |
| 2 | Live text search / quick-filter | Functional | Medium | High | Open |
| 3 | Export to Markdown / plain text | Functional | Medium | Medium | Open |
| 4 | JSON schema versioning | Robustness | Low-Medium | Medium | Open |
| 5 | Copy / duplicate subtree | Functional | Medium | Medium | Open |
| 6 | Expand all / Collapse all | Usability | Low | Low-Medium | Open |
| 7 | Unit test suite | Engineering | High | High | ✓ Done |
| 8 | Contributing & architecture docs | Documentation | Low-Medium | Medium | ✓ Done |
| 9 | Breadcrumb truncation | Usability | Low-Medium | Low | ✓ Done |
| 10 | Per-item notes field | Functional | Medium-High | Low-Medium | ✗ Won't do |

---

## Related existing proposals

Several other improvements are already captured in focused proposals:

| Topic | File |
|-------|------|
| Progress summary (X / Y done) | `progress-summary-proposal.md` |
| Duplicate object detection & recovery | `duplicate-todo-objects-proposal.md` |
| Eager creation bug | `eager-creation-problem-proposal.md` |
| Mixed-state parent checkboxes | `user-feedback-analysis.md` §4 |
| Dark theme checkbox colour | `user-feedback-analysis.md` §1 |
