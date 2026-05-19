# FreeCAD Todo Tree Addon — Design Plan

**Date:** 2026-05-18  
**Status:** Pre-implementation planning

---

## Context & Requirements

A standalone FreeCAD addon (installable via Addon Manager) that adds a hierarchical, tree-structured todo list to FreeCAD. Key requirements:

- **Tree hierarchy:** Unlimited depth. Any node can have children.
- **Dual view:** A persistent dock widget companion panel AND a full main-window view (opened as an MDI area tab, like Spreadsheet or Text Document).
- **Navigation:** Expand/collapse nodes; click any node to make it the "root" of the current view; breadcrumb trail back up the hierarchy.
- **Inline editing:** Double-click a node to edit its label in-place.
- **Completion:** Each item has a done/not-done checkbox. Done items get strikethrough + greyed text. A toggle button hides/shows completed items.
- **Persistence:** Both the todo tree data and the view state are stored per-document inside the `.FCStd` file. On re-open, the user is returned to exactly where they left off: same breadcrumb root, same expanded/collapsed nodes, same show/hide done toggle.
- **Undo/redo:** All mutations (add, delete, rename, move, check/uncheck) integrate with FreeCAD's document undo stack via `openTransaction` / `commitTransaction`.
- **v1 scope:** Plain text only — no links to model objects, no priority, no due dates.
- **Distribution:** Standalone addon repo (pure Python, no C++ build step).

---

## Questions Asked & Answered

| Question | Answer |
|---|---|
| Panel location | Persistent dock widget + main-window MDI view (both) |
| Todo scope | Per-document only |
| Metadata per item | Text label + done checkbox only |
| Done items display | Strikethrough + grey, plus toggle to hide/show |
| Tree depth | Unlimited |
| Distribution | Standalone addon (Addon Manager) |
| Undo/redo | Full FreeCAD document undo stack integration |
| Object linking | No — plain text only for v1 |
| Editing UX | Inline editing (double-click in tree) |

---

## Common Architecture Across All Options

Regardless of which option is chosen, the following design decisions apply:

### Data Model (In-memory)

The tree is represented as a recursive Python dict structure:

```python
node = {
    "id": "uuid4-string",   # stable identity for undo references
    "text": "Todo item",
    "done": False,
    "children": [...]        # list of child nodes, same structure
}
document_root = {
    "id": "root",
    "text": "__root__",
    "done": False,
    "children": [...]
}
```

This is serialized to/from JSON for persistence. JSON is human-readable if someone inspects the `.FCStd` zip, and Python's `json` module is zero-dependency.

### View State Persistence

View state is saved to the document alongside tree data so the user is returned to exactly where they left off on re-open. The persisted view state is a small JSON blob:

```python
view_state = {
    "current_root_id": "uuid-of-current-root-node",  # "root" when at the top level
    "breadcrumb_path": ["root", "uuid1", "uuid2"],    # node IDs from root down to current_root_id
    "expanded_ids": ["uuid1", "uuid3", "uuid5"],      # IDs of currently expanded nodes
    "show_done": True                                  # show/hide completed items toggle
}
```

**View state is NOT part of the undo/redo stack.** Navigating to a subtree, expanding a node, or toggling the done filter are navigation actions — undoing them would be surprising and wrong. The way to achieve this in FreeCAD is to mutate the view-state property **outside of any `openTransaction` / `commitTransaction` block**. Properties changed outside a transaction are saved to the file normally but are invisible to the undo system.

**Stale ID handling on load:** If `current_root_id` or any ID in `breadcrumb_path` or `expanded_ids` no longer exists in the tree (e.g., that node was deleted and the deletion was not undone before saving), those IDs are silently ignored. The view falls back gracefully: if `current_root_id` is missing, the view resets to the document root; stale entries in `expanded_ids` are simply skipped; the breadcrumb is truncated at the last still-valid ancestor.

**Capturing expand/collapse state before save:** A `beforeSaveDocument` slot in the DocumentObserver (or a FreeCAD `onSaveDocument` hook in the FeaturePython ViewProvider) walks the visible tree and collects the set of currently expanded node IDs, writing them to the view-state property just before the file is written.

### Breadcrumb Navigation

`breadcrumb_path` from the view state drives the breadcrumb bar on load. The view re-roots at `current_root_id`. The breadcrumb bar renders as clickable labels: `Root > Engineering > CAD tasks`. Clicking any crumb re-roots the view there and updates both `current_root_id` and `breadcrumb_path` in the view-state property (outside a transaction).

### Done-item Filtering

`show_done` from the view state initialises the filter toggle on load (default `True` for new documents). Toggling it updates the view-state property (outside a transaction) so the preference persists across sessions.

### Undo/Redo Integration

Every mutation wraps the property change in a FreeCAD transaction:

```python
doc.openTransaction("Todo: add item")
# mutate the property that stores the JSON
doc.commitTransaction()
```

Because FreeCAD's undo system tracks property changes, any `App::PropertyString` mutation inside a transaction is automatically undoable via Ctrl+Z. No custom undo stack needed.

### Addon File Layout

```
freecad-todo-tree/
├── Init.py                  # non-GUI module init
├── InitGui.py               # workbench class + GUI registration
├── package.xml              # Addon Manager metadata
├── LICENSE
├── README.md
├── freecad_todo_tree/
│   ├── __init__.py
│   ├── commands.py          # toolbar/menu command classes
│   ├── todo_model.py        # in-memory tree data model + JSON serialization
│   ├── todo_object.py       # FeaturePython proxy (options A & B) or observer (option C)
│   ├── dock_widget.py       # persistent dock panel
│   ├── main_view.py         # MDI main-area view
│   ├── tree_widget.py       # shared QTree* widget implementation
│   └── breadcrumb.py        # breadcrumb bar widget
└── resources/
    └── icons/
        └── TodoTree.svg
```

---

## Option 1 — Lean FeaturePython + QTreeWidget

**Philosophy:** Do the simplest thing that works correctly. `QTreeWidget` handles tree rendering natively with no custom model class required. A single hidden `FeaturePython` object owns the data. Easy to understand, easy to maintain.

### Storage

A `FeaturePython` object named `"TodoTree"` is created automatically when the addon is first used in a document. It carries two properties — one for tree data (undo-tracked), one for view state (not undo-tracked):

```python
EMPTY_TREE = {"id": "root", "text": "__root__", "done": False, "children": []}
EMPTY_VIEW_STATE = {
    "current_root_id": "root",
    "breadcrumb_path": ["root"],
    "expanded_ids": [],
    "show_done": True,
}

class TodoTreeObject:
    def __init__(self, obj):
        obj.addProperty(
            "App::PropertyString", "TreeData", "TodoTree",
            "JSON-serialized todo tree", 4  # flag 4 = hidden from UI
        ).TreeData = json.dumps(EMPTY_TREE)
        obj.addProperty(
            "App::PropertyString", "ViewState", "TodoTree",
            "JSON-serialized view state (not in undo stack)", 4
        ).ViewState = json.dumps(EMPTY_VIEW_STATE)
        obj.Proxy = self

    def execute(self, fp):
        pass  # no geometry, nothing to recompute

    def dumps(self):
        return None  # all state is in the properties, not the proxy

    def loads(self, state):
        return None
```

`TreeData` mutations are always wrapped in `openTransaction` / `commitTransaction`. `ViewState` mutations are written **directly** (no transaction), so they save with the file but never appear in the undo history.

The object is marked hidden via `obj.setEditorMode("TreeData", 2)` and `obj.ViewObject.Visibility = False`. It will not appear in the model tree's visible hierarchy (it exists in the document but the ViewProvider suppresses it).

### GUI: Dock Widget

```python
class TodoDockWidget(QtWidgets.QDockWidget):
    # QTreeWidget inside; each QTreeWidgetItem stores node_id in Qt.UserRole
    # Signals: itemChanged (checkbox), itemDoubleClicked (inline edit),
    #          customContextMenuRequested (add/delete/navigate)
```

`QTreeWidget` natively supports:
- Checkboxes via `item.setCheckState(0, Qt.Checked)`
- Inline editing via `item.setFlags(item.flags() | Qt.ItemIsEditable)` + `itemChanged` signal
- Expand/collapse built-in
- Drag-and-drop for reordering via `setDragDropMode(QAbstractItemView.InternalMove)`

The dock widget is registered with FreeCAD's main window on workbench activation:

```python
mw = FreeCADGui.getMainWindow()
mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.dock)
```

### GUI: Main-Window View

A `QMdiSubWindow` wrapping the same tree widget content, opened via a toolbar command or by double-clicking the `TodoTree` object in the model tree (via `ViewProvider.doubleClicked()`):

```python
class ViewProviderTodoTree:
    def doubleClicked(self, vobj):
        mw = FreeCADGui.getMainWindow()
        view = TodoMainView(vobj.Object, mw)
        mw.centralWidget().addSubWindow(view)
        view.show()
        return True
```

The dock and main view share the same underlying data (re-read from the property on each render). Mutations from either panel write back to the property inside a transaction and then refresh the other panel.

### Complexity & Inline Editing Caveat

`QTreeWidget.itemChanged` fires for both checkbox changes and text edits. Care must be taken to distinguish these (track an `_editing` flag) to avoid double-triggering transactions.

### Trade-offs

| Pros | Cons |
|---|---|
| Least code to write | QTreeWidget's `itemChanged` ambiguity requires careful signal management |
| No custom model class | Rebuilds entire widget on every data change (full `clear()` + repopulate) |
| Well-understood Qt API | Harder to share a live-updating model between dock and main view |
| Minimal FreeCAD API surface | QMdiSubWindow is not a true FreeCAD `MDIView` — lacks file-type tab behavior |

### When to choose this option

Best for a fast v1 that just works. The todo tree is unlikely to have thousands of items, so the full-repopulate approach is fine in practice. Recommended if implementation speed is the priority.

---

## Option 2 — MVC Architecture: QTreeView + Custom QAbstractItemModel

**Philosophy:** Separate the data model from the view properly. A custom `QAbstractItemModel` wraps the in-memory Python tree and is shared by both the dock widget and the main view. Both widgets observe the same model instance — a change in one is instantly reflected in the other without any "refresh other panel" logic.

### Storage

Identical to Option 1: a hidden `FeaturePython` object with both `App::PropertyString TreeData` and `App::PropertyString ViewState`. The difference is purely in the GUI layer.

The custom `QAbstractItemModel` reads `ViewState` on initialisation and writes it back (outside any transaction) whenever the breadcrumb root changes, a node is expanded/collapsed, or the show-done toggle is flipped. Because the model is shared between the dock and the main view, view-state writes from either panel are automatically consistent.

### Custom Item Model

```python
class TodoItemModel(QtCore.QAbstractItemModel):
    """
    Wraps the in-memory dict tree. Emits dataChanged / layoutChanged
    when the tree is mutated. Both dock and main view share one instance.
    """

    def index(self, row, column, parent):
        # Return QModelIndex pointing to the node dict
        ...

    def parent(self, index):
        # Walk up to parent node
        ...

    def rowCount(self, parent):
        node = self._node_from_index(parent)
        if self._show_done:
            return len(node["children"])
        return sum(1 for c in node["children"] if not c["done"])

    def columnCount(self, parent):
        return 1

    def data(self, index, role):
        node = self._node_from_index(index)
        if role == Qt.DisplayRole:
            return node["text"]
        if role == Qt.CheckStateRole:
            return Qt.Checked if node["done"] else Qt.Unchecked
        if role == Qt.ForegroundRole and node["done"]:
            return QtGui.QColor("grey")
        if role == Qt.FontRole and node["done"]:
            f = QtGui.QFont()
            f.setStrikeOut(True)
            return f
        return None

    def setData(self, index, value, role):
        node = self._node_from_index(index)
        if role == Qt.EditRole:
            self._mutate(lambda: node.update({"text": value}), "rename item")
        elif role == Qt.CheckStateRole:
            self._mutate(lambda: node.update({"done": value == Qt.Checked}), "toggle item")
        return True

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsUserCheckable

    def _mutate(self, fn, transaction_label):
        doc = FreeCAD.ActiveDocument
        doc.openTransaction(f"Todo: {transaction_label}")
        fn()
        self._flush_to_property()  # write JSON back to the FeaturePython property
        doc.commitTransaction()
        self.dataChanged.emit(...)
```

`QTreeView` is configured with a `QStyledItemDelegate` for inline editing, and the same model instance is passed to both the dock widget's `QTreeView` and the main view's `QTreeView`.

### Filtering

A `QSortFilterProxyModel` wraps `TodoItemModel` and filters out done items when `show_done=False`. The proxy is toggled by the toolbar button. This is cleaner than manual show/hide in Option 1.

### Breadcrumb as a Proxy Root

Setting the view's root to a subtree uses `QTreeView.setRootIndex(model.index_for_node(node_id))`. The breadcrumb bar holds the path of `QModelIndex` values and clicking a crumb calls `setRootIndex` on that index.

### Main-Window View

Same approach as Option 1 (QMdiSubWindow), but both dock and main view share the model instance — no refresh-other-panel code needed.

### Trade-offs

| Pros | Cons |
|---|---|
| Shared model: changes in dock instantly appear in main view | More code: custom `QAbstractItemModel` is non-trivial |
| Qt's filter proxy handles done-item hiding cleanly | `QModelIndex` + internal pointer management is subtle |
| Scales to large trees (virtual rendering) | Overkill if the tree rarely exceeds ~200 nodes |
| Clean separation: model knows nothing about widgets | |

### When to choose this option

Best when correctness and scalability matter more than implementation speed. The MVC split also makes unit testing the data model possible independently of Qt widgets. Recommended if the addon is intended to grow (more metadata, import/export, etc.).

---

## Option 3 — Document-Level Property + DocumentObserver Pattern

**Philosophy:** Instead of creating a `FeaturePython` object in the document's object list, attach the todo data directly as a property on `App.Document` itself. This means the todo tree is completely invisible in the model tree — users will never accidentally select or delete it. A `DocumentObserver` handles all multi-document scenarios.

### Storage

```python
def ensure_todo_properties(doc):
    """Add todo properties to the document if not already present."""
    if not hasattr(doc, "TodoTreeData"):
        doc.addProperty(
            "App::PropertyString", "TodoTreeData", "TodoTree",
            "Serialized todo tree", 4
        )
        doc.TodoTreeData = json.dumps(EMPTY_TREE)
    if not hasattr(doc, "TodoViewState"):
        doc.addProperty(
            "App::PropertyString", "TodoViewState", "TodoTree",
            "Serialized view state (not in undo stack)", 4
        )
        doc.TodoViewState = json.dumps(EMPTY_VIEW_STATE)
```

Both properties are saved automatically as part of the document's XML when the `.FCStd` is written. `TodoTreeData` mutations use `openTransaction` / `commitTransaction`; `TodoViewState` mutations are written directly (no transaction) so they persist without entering the undo stack. No `FeaturePython` object, no ViewProvider, no entry in the model tree.

### DocumentObserver

```python
class TodoDocumentObserver(FreeCAD.Base.BaseClass):
    """
    Watches for document events and keeps the GUI in sync.
    """

    def slotActivateDocument(self, doc):
        ensure_todo_property(doc)
        gui.refresh_from_document(doc)

    def slotCreatedDocument(self, doc):
        ensure_todo_property(doc)

    def slotDeletedDocument(self, doc):
        gui.clear_if_showing(doc)

observer = TodoDocumentObserver()
FreeCAD.addDocumentObserver(observer)
```

The observer is registered once when the workbench is initialized and removed when it is deactivated.

### Undo/Redo

Since the property lives on the document object (not a FeaturePython proxy), mutations must still be wrapped in transactions:

```python
def set_tree(doc, tree_dict):
    doc.openTransaction("Todo: modify tree")
    doc.TodoTreeData = json.dumps(tree_dict)
    doc.commitTransaction()
```

FreeCAD tracks `App::PropertyString` changes on `App.Document` in its undo stack the same way it does on `DocumentObject` children. This has been verified in the FreeCAD source (`Test/Document.py` tests this explicitly).

### GUI

Use Option 1's `QTreeWidget` approach (simpler) or Option 2's `QAbstractItemModel` (scalable) — the GUI layer is independent of the storage choice. Option 3 is purely about storage architecture.

### Handling Document Switching

When the user switches active documents, `slotActivateDocument` fires. The GUI reads `doc.TodoTreeData` from the newly active document and re-populates the tree. This is the key advantage: no FeaturePython object means there is no ViewProvider to manage and no risk of the user deleting the storage object.

### Trade-offs

| Pros | Cons |
|---|---|
| Zero model-tree pollution — completely invisible to users | `addProperty` on `App.Document` is less commonly used; edge cases are less tested |
| No risk of user accidentally deleting the todo storage object | No ViewProvider → no `doubleClicked()` hook for opening the main view (must use toolbar command only) |
| Clean multi-document handling via observer | Observer pattern adds statefulness that must be carefully managed |
| No FeaturePython boilerplate | Property on document object has less documentation/examples |

### When to choose this option

Best when you want the cleanest possible user-facing experience (no mystery objects in the model tree). The reduced ViewProvider flexibility is the main cost — the main-window view must be opened via a toolbar command rather than double-clicking a model tree entry. Recommended if "invisible infrastructure" is a design priority.

---

## Comparison Summary

| Criterion | Option 1: QTreeWidget | Option 2: QTreeView + Model | Option 3: Doc Property + Observer |
|---|---|---|---|
| **Implementation effort** | Low | Medium | Medium |
| **Qt complexity** | Low (QTreeWidget) | High (custom model) | Low–Medium |
| **Model tree impact** | Hidden FeaturePython object | Hidden FeaturePython object | No impact at all |
| **Live sync dock↔main view** | Manual refresh | Automatic (shared model) | Manual refresh |
| **Filtering done items** | Manual show/hide | QSortFilterProxyModel | Manual show/hide |
| **View state persisted** | Yes (ViewState property, no undo) | Yes (ViewState property, no undo) | Yes (TodoViewState property, no undo) |
| **Undo/redo correctness** | Solid (property on FeaturePython) | Solid | Solid (property on document) |
| **Double-click to open main view** | Yes (ViewProvider hook) | Yes (ViewProvider hook) | No (toolbar only) |
| **Scale to 1000+ items** | Acceptable | Excellent | Depends on chosen GUI |
| **Recommended for v1** | ✓ Fast path | ✓ Long-term investment | If "no model tree objects" is critical |

---

## Recommended Path

**Option 1 for v1, with an upgrade path to Option 2.**

Option 1 gets a working addon into users' hands fastest. The `QTreeWidget` approach is well-understood, the FreeCAD integration is straightforward, and the todo tree will rarely be large enough to hit performance limits.

The architecture should be written to keep `todo_model.py` (in-memory tree + JSON) and `todo_object.py` (FeaturePython persistence) cleanly separated from the widget code. This makes upgrading the GUI layer from `QTreeWidget` to `QTreeView + QAbstractItemModel` (Option 2) a widget-layer change only — the storage and data model layers need not change.

Option 3 is worth revisiting if user feedback consistently mentions confusion about the `TodoTree` object appearing in their model tree (even though it is hidden, it can appear under certain view filters).

---

## Open Implementation Questions

1. **MDI view type:** `QMdiSubWindow` is not a true FreeCAD `MDIView` — it won't appear in the Window menu. To get full Spreadsheet-style integration (tab in the central area, appears in Window menu), a C++ `MDIView` subclass is required. For a pure-Python addon, `QMdiSubWindow` is the best available option.
2. **Drag-and-drop reordering:** `QTreeWidget`'s `InternalMove` drag-drop mode does not map back to the JSON model cleanly. Will need to intercept `dropEvent` and update the underlying tree manually, then flush to the property.
3. **Icon:** A simple SVG icon needs to be created for the addon and the toolbar command.
4. **Addon Manager metadata:** `package.xml` must follow the FreeCAD Addon Manager spec (version, author, FreeCAD min/max version, tags).
5. **Multi-document UX:** When multiple documents are open, the dock widget should show which document's todos are displayed (a label or title update).
6. **Expand/collapse capture timing:** The set of expanded node IDs must be written to `ViewState` either eagerly (on every expand/collapse event) or lazily (just before save via a `beforeSave` hook). The eager approach is simpler but causes frequent property writes outside transactions; the lazy approach batches them into one write at save time and is preferred.
