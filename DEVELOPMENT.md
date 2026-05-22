# TodoTree — Development Guide

This document covers everything you need to contribute to the TodoTree addon:
environment setup, running the test suite, understanding the architecture,
and adding new features.

---

## Contents

1. [Prerequisites](#prerequisites)
2. [Setting up the development environment](#setting-up-the-development-environment)
3. [Running the tests](#running-the-tests)
4. [Project structure](#project-structure)
5. [Architecture](#architecture)
6. [Common extension patterns](#common-extension-patterns)
7. [Coding conventions](#coding-conventions)
8. [Pull request workflow](#pull-request-workflow)

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| FreeCAD | 1.0.2 or later | Required to run the addon in practice |
| Python | 3.8 or later | Bundled with FreeCAD; also needed for the test suite |
| PySide6 | any recent | For running the Qt-dependent tests outside FreeCAD; install via `pip` |
| pytest | any recent | Test runner; install via `pip` |

FreeCAD ships its own Python interpreter and PySide build. The test suite is
designed to also run against a standalone PySide6 installation so that CI can
execute without FreeCAD being present.

---

## Setting up the development environment

### Symlink install

The recommended approach is to clone the repository somewhere on your machine
and symlink it into FreeCAD's `Mod` directory. FreeCAD follows symlinks at
startup, so every change you make to the source tree is picked up the next
time FreeCAD starts — no copying or reinstalling needed.

**macOS:**

```bash
git clone https://github.com/robertmassaioli/freecad-todo-tree \
  ~/projects/freecad-todo-tree

ln -s ~/projects/freecad-todo-tree \
  ~/Library/Application\ Support/FreeCAD/Mod/TodoTree
```

**Linux:**

```bash
git clone https://github.com/robertmassaioli/freecad-todo-tree \
  ~/projects/freecad-todo-tree

ln -s ~/projects/freecad-todo-tree \
  ~/.local/share/FreeCAD/Mod/TodoTree
```

**Windows:**

```
git clone https://github.com/robertmassaioli/freecad-todo-tree ^
  %USERPROFILE%\projects\freecad-todo-tree

mklink /D %APPDATA%\FreeCAD\Mod\TodoTree ^
       %USERPROFILE%\projects\freecad-todo-tree
```

After creating the symlink, restart FreeCAD once. Subsequent `git pull`
runs are enough to update; no restart is needed for Python file changes
unless the file is one that FreeCAD caches on first load (`init_gui.py`,
`__init__.py`).

### Reloading changes without restarting FreeCAD

For modules that are imported on demand (most of the codebase), you can force
a reload from the FreeCAD Python console:

```python
import importlib, freecad.TodoTree.tree_panel as m
importlib.reload(m)
```

For changes to `init_gui.py` (workbench registration) or `commands.py`
(command classes), a full FreeCAD restart is the safest option.

---

## Running the tests

The test suite uses **pytest** and covers the three testable layers of the
addon:

| File | Layer | FreeCAD/Qt needed? |
|------|-------|--------------------|
| `tests/test_todo_model.py` | Pure-Python data model | No |
| `tests/test_todo_item_model.py` | Qt item model | PySide6 only |
| `tests/test_filter_proxy.py` | Qt filter proxy | PySide6 only |

### Install the test dependencies

```bash
pip install pytest PySide6
```

If you are on a system that blocks pip from modifying system packages (PEP 668),
use a virtual environment or add `--break-system-packages`:

```bash
pip install --break-system-packages pytest PySide6
```

### Run all tests

From the repository root:

```bash
python3 -m pytest
```

Or, if `pytest` is on your PATH:

```bash
pytest
```

Expected output:

```
========================== 73 passed in 0.12s ==========================
```

### Run a single file

```bash
pytest tests/test_todo_model.py
```

### Run a single test

```bash
pytest tests/test_todo_item_model.py::test_drop_same_parent_downward_uses_correct_bm_dest
```

### Run with verbose output

```bash
pytest -v
```

### How the tests work outside FreeCAD

`tests/conftest.py` does two things before any addon module is imported:

1. Maps `PySide6` onto the `PySide` namespace that the addon uses, so
   `from PySide.QtCore import …` resolves correctly in a non-FreeCAD Python.
2. Installs a `MagicMock` for `FreeCAD` and `FreeCADGui`, so the addon's
   conditional `FreeCAD.Console.PrintMessage(…)` calls inside `debug.py` do
   not crash.

The tests that exercise `TodoItemModel` and `DoneFilterProxy` use a minimal
mock FreeCAD object (a `MagicMock` with a `TreeData` string attribute and a
`Document` that accepts `openTransaction` / `commitTransaction` calls).
A session-scoped `QApplication` fixture keeps Qt happy for the duration of the
run.

---

## Project structure

```
freecad-todo-tree/
├── package.xml                    Addon Manager metadata
├── LICENSE
├── README.md
├── DEVELOPMENT.md                 This file
├── pyproject.toml                 pytest configuration
├── tests/
│   ├── conftest.py                PySide6 shim + FreeCAD mock + helpers
│   ├── test_todo_model.py         Pure-Python tree tests
│   ├── test_todo_item_model.py    Qt model tests
│   └── test_filter_proxy.py      Filter proxy tests
└── freecad/TodoTree/
    ├── __init__.py
    ├── init_gui.py                Workbench class + command registration
    ├── resources.py               Icon path helper (importlib.resources)
    ├── todo_model.py              TodoNode, TodoTree, JSON serialisation
    ├── todo_object.py             FeaturePython proxy + ViewProvider
    ├── model_registry.py          Per-document model cache; undo-reload bridge
    ├── todo_item_model.py         QAbstractItemModel wrapping TodoTree
    ├── filter_proxy.py            QSortFilterProxyModel for done-item filtering
    ├── breadcrumb_widget.py       Clickable breadcrumb bar
    ├── tree_panel.py              Composite panel: breadcrumb + toolbar + tree view
    ├── dock_widget.py             Persistent QDockWidget + DocumentObserver
    ├── main_view.py               QMdiSubWindow in FreeCAD's central MDI area
    ├── commands.py                FreeCAD GUI command classes
    └── Resources/Icons/
```

---

## Architecture

### Layers

The codebase has three distinct layers. Keeping them separate matters for
testability and for understanding which changes need a FreeCAD transaction.

```
┌──────────────────────────────────────────────┐
│  todo_model.py                               │  ← Pure Python; no Qt, no FreeCAD
│  TodoNode, TodoTree, JSON serialisation      │
└──────────────────────────────────────────────┘
                  ↑ wraps
┌──────────────────────────────────────────────┐
│  todo_item_model.py                          │  ← Qt model; reads/writes FreeCAD property
│  TodoItemModel (QAbstractItemModel)          │
└──────────────────────────────────────────────┘
                  ↑ filters
┌──────────────────────────────────────────────┐
│  filter_proxy.py                             │  ← Qt proxy; pure view logic
│  DoneFilterProxy (QSortFilterProxyModel)     │
└──────────────────────────────────────────────┘
                  ↑ displayed by
┌──────────────────────────────────────────────┐
│  tree_panel.py, dock_widget.py, main_view.py │  ← Qt widgets; FreeCAD integration
└──────────────────────────────────────────────┘
```

### Data flow

Every document has exactly one `TodoItemModel` instance, shared between the
dock panel and the main-window view. The full pipeline for a mutation is:

```
User action (click, keypress)
  → TreePanel calls TodoItemModel.add_child / remove_node / setData / …
    → openTransaction
    → beginInsertRows / beginRemoveRows / dataChanged (notify views before)
    → TodoTree mutated in memory
    → TodoTree.to_json() → fc_object.TreeData (flush to FreeCAD property)
    → commitTransaction
    → endInsertRows / endRemoveRows / dataChanged (notify views after)
```

For undo/redo, FreeCAD reverts `TreeData` and calls `onChanged` on the proxy
object. `model_registry.py` bridges this into `TodoItemModel.reload_from_property()`,
which wraps the in-memory rebuild in `beginResetModel / endResetModel` and
emits `treeReset` so each panel can re-validate its breadcrumb path.

### The two-property design

The FreeCAD object carries two properties with different undo semantics:

| Property | What it stores | Written in a transaction? |
|----------|---------------|--------------------------|
| `TreeData` | The entire tree as JSON | Yes — appears in undo history |
| `ViewState` | Breadcrumb path, expanded nodes, show-done toggle | No — persisted but never undone |

Never write `ViewState` inside a `openTransaction` block. Navigation is view
state, not data; rolling it back on undo would be disorienting.

### The `_flushing` guard

`TodoItemModel` sets `self._flushing = True` while it writes to `TreeData`.
The `todo_object.py` `onChanged` hook fires on every property write — including
writes the model itself makes. Without the guard, each flush would trigger a
reload loop. Any code that listens to `onChanged` must check `model.is_flushing()`
and return early if it is set.

---

## Common extension patterns

### Adding a new command

1. **Add the command class** in `commands.py`:

   ```python
   class TodoTree_MyCommand:
       def GetResources(self):
           return {
               "Pixmap": get_icon_path("Logo.svg"),
               "MenuText": "My Action",
               "ToolTip": "What it does",
           }

       def IsActive(self):
           return _active_panel() is not None

       def Activated(self):
           panel = _active_panel()
           if panel:
               panel.my_action()
   ```

2. **Add the panel method** in `TreePanel` (`tree_panel.py`):

   ```python
   def my_action(self):
       self._do_something()
   ```

3. **Register the command** in `init_gui.py` (add to the `_COMMANDS` list and
   to the toolbar/menu lists).

4. **Add a documentation file** in `Documentation/Commands/`.

### Adding a new field to TodoNode

1. Add the slot in `TodoNode.__slots__` (`todo_model.py`):

   ```python
   __slots__ = ("id", "text", "done", "expanded", "my_field", "children", "_parent")
   ```

2. Set a default in `TodoNode.__init__`:

   ```python
   self.my_field = default_value
   ```

3. Serialise it in `TodoTree.to_dict`:

   ```python
   "my_field": n.my_field,
   ```

4. Deserialise it in the `_node` helper inside `TodoTree.from_dict`:

   ```python
   n = TodoNode(d["id"], d["text"], d.get("done", False),
                d.get("expanded", False), d.get("my_field", default_value))
   ```

   Use `.get()` with a default so that documents saved before the field
   existed still load correctly.

5. If `my_field` affects what the user sees or does, expose it through
   `TodoItemModel` via a new role or by extending `data()` / `setData()`.

6. Add tests in `tests/test_todo_model.py` covering the new field's
   serialisation round-trip, including a test that omitting the key from the
   JSON still produces the correct default.

### Adding a new mutation to TodoItemModel

Any mutation that changes `TreeData` must follow this pattern:

```python
def my_mutation(self, index):
    if not index.isValid():
        return
    node = index.internalPointer()

    doc = self._fc_object.Document
    doc.openTransaction("Todo: my operation")
    self.beginXxxRows(…)          # or dataChanged — notify Qt before
    self._tree.mutate(node.id)    # mutate the in-memory tree
    self._flush_to_property()     # write TreeData (guarded by _flushing)
    doc.commitTransaction()
    self.endXxxRows(…)            # or dataChanged — notify Qt after
```

Never call `self._flush_to_property()` outside a transaction for data
mutations. Never wrap navigation or view-state writes in a transaction.

---

## Coding conventions

- **SPDX headers** on every new source file:

  ```python
  # SPDX-License-Identifier: LGPL-2.1-or-later
  # SPDX-FileNotice: Part of the TodoTree addon.
  ```

- **No comments by default.** Only add one when the *why* is non-obvious: a
  hidden constraint, a workaround for a specific Qt or FreeCAD behaviour, or
  an invariant that would surprise a reader. The `_flushing` guard, the
  `beginMoveRows` coordinate arithmetic for same-parent downward moves, and
  the plain-integer return from `CheckStateRole` are examples of things that
  warrant a comment. A function that adds a child item does not.

- **No docstrings on obvious methods.** A one-line description is fine for
  non-obvious module-level context (see `todo_model.py`'s module docstring).
  Multi-paragraph docstrings on individual methods add noise without value.

- **Qt enum values as integers where Qt6 requires it.** FreeCAD may ship
  PySide2 or PySide6 depending on the version. When returning role data
  that Qt's C++ delegate reads back with `toInt()`, return plain `int` values
  (0, 1, 2) rather than enum members — see the `CheckStateRole` comment in
  `todo_item_model.py` for the reason.

---

## Pull request workflow

1. Fork the repository and create a feature branch from `main`.
2. Write tests for any new behaviour before or alongside the implementation.
3. Run `pytest` and confirm all 73 existing tests still pass.
4. Keep commits focused — one logical change per commit.
5. Open a pull request against `main`. The description should explain *why*
   the change is needed, not just what it does.
