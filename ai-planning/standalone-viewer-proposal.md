# Standalone Todo Viewer Proposal

**Date:** 2026-05-19  
**Status:** Proposal — pending implementation decision

---

## Is It Possible?

Yes. There are no fundamental blockers. The two challenges — reading todo data without opening the document, and showing a panel that isn't tied to a document — are both solvable with standard FreeCAD and Python APIs.

---

## What "Without the File Open" Means

Two distinct interpretations, each with a different implementation:

**Interpretation A — Cross-document panel (file open in FreeCAD, but not the active document)**  
The user has multiple documents open. They want to see todos from a document they're not currently working in, without switching to it.

**Interpretation B — File not open at all (read directly from the .FCStd on disk)**  
The user wants to browse todo lists from `.FCStd` files on their filesystem without loading them into FreeCAD. The panel reads the ZIP archive directly and displays the tree read-only.

This proposal covers **both**, as they are largely complementary and share most implementation infrastructure.

---

## How `.FCStd` Storage Works

A `.FCStd` file is a ZIP archive. Inside it, the standard XML file (`Document.xml`) contains the serialised properties of all `DocumentObject` instances, including the hidden `TodoTree` object. The `TreeData` property is stored as a plain text string within that XML.

Reading it requires only Python's `zipfile` and `xml.etree.ElementTree` — no FreeCAD runtime is needed:

```python
import zipfile, xml.etree.ElementTree as ET

def read_tree_data(fcstd_path: str) -> str | None:
    with zipfile.ZipFile(fcstd_path) as zf:
        with zf.open("Document.xml") as f:
            tree = ET.parse(f)
    for prop in tree.iter("Property"):
        if prop.attrib.get("name") == "TreeData":
            string_el = prop.find("String")
            if string_el is not None:
                return string_el.attrib.get("value")
    return None
```

This is fast (a small XML parse of a ZIP entry) and works on any `.FCStd` file that has the TodoTree addon data embedded.

---

## Proposed Feature: Standalone Viewer Panel

A new dock panel — **Todo Browser** — that operates independently of the currently active document. It shows a file-picker at the top, lets the user select any `.FCStd` file, and displays its todo tree read-only. The user can navigate the hierarchy, expand/collapse nodes, and toggle show/hide done, but cannot edit.

### Why read-only for the file-not-open case?

Writing back to a `.FCStd` ZIP from outside FreeCAD's document system risks corrupting the file (FreeCAD may have internal checksums or file-version metadata that need updating when properties change). Read-only is safe and sufficient for the use case of reviewing todo lists across multiple projects.

For the cross-document case (Interpretation A), full read-write is possible if the document is open (the data is live in memory via the normal model).

---

## Architecture

### New module: `todo_browser.py`

A new `QDockWidget` subclass, entirely separate from the existing `TodoDockWidget`. It does not use `model_registry` or `TodoItemModel` — it builds a simpler read-only `QTreeWidget` directly from the parsed JSON.

```
freecad/TodoTree/
├── todo_browser.py        # new: standalone viewer dock
├── fcstd_reader.py        # new: .FCStd ZIP parser (no FreeCAD deps)
└── (all existing files unchanged)
```

### `fcstd_reader.py`

Pure Python. No FreeCAD imports. Reads a `.FCStd` file and returns a `TodoTree` (the existing pure-Python class from `todo_model.py`).

```python
import zipfile
import json
import xml.etree.ElementTree as ET
from .todo_model import TodoTree, EMPTY_TREE


class FCStdReadError(Exception):
    pass


def read_todo_tree(fcstd_path: str) -> TodoTree:
    """
    Parse the TreeData property from a .FCStd file and return a TodoTree.
    Raises FCStdReadError if the file has no TodoTree data.
    """
    try:
        with zipfile.ZipFile(fcstd_path) as zf:
            with zf.open("Document.xml") as f:
                root = ET.parse(f).getroot()
    except (zipfile.BadZipFile, KeyError) as e:
        raise FCStdReadError(f"Cannot read {fcstd_path}: {e}") from e

    for prop in root.iter("Property"):
        if prop.attrib.get("name") == "TreeData":
            el = prop.find("String")
            if el is not None:
                value = el.attrib.get("value", "")
                try:
                    return TodoTree.from_json(value)
                except (json.JSONDecodeError, KeyError) as e:
                    raise FCStdReadError(f"Malformed TreeData: {e}") from e

    raise FCStdReadError("No TodoTree data found in this file.")
```

### `todo_browser.py`

A self-contained dock widget. Uses `QFileDialog` for file picking and a `QTreeWidget` for display (simpler than the full MVC stack since this is read-only).

Key UI elements:
- **File selector** — a `QLineEdit` + browse button. Accepts drag-and-drop of `.FCStd` files.
- **Refresh button** — re-reads the file from disk (useful if the file was just saved from another FreeCAD session).
- **Breadcrumb** — reuses `BreadcrumbWidget` for hierarchy navigation.
- **Show/hide done toggle** — same as the editable panel.
- **Read-only `QTreeWidget`** — checkboxes visible but not interactive; items not editable.
- **Status bar** — shows the file path, last-modified time, and item count.

```python
class TodoBrowserDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Todo Browser", parent)
        self.setObjectName("TodoTreeBrowserDock")
        self._current_file = None
        self._tree = None         # TodoTree instance
        self._breadcrumb_path = ["root"]
        self._show_done = True
        self._setup_ui()

    def load_file(self, path: str):
        from .fcstd_reader import read_todo_tree, FCStdReadError
        try:
            self._tree = read_todo_tree(path)
            self._current_file = path
            self._breadcrumb_path = ["root"]
            self._refresh_view()
        except FCStdReadError as e:
            # Show error in status label
            ...

    def load_active_document(self):
        """Load the currently active FreeCAD document's todos (if it has any)."""
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return
        for obj in doc.Objects:
            if hasattr(obj, "Proxy") and hasattr(obj, "TreeData"):
                from .todo_model import TodoTree
                self._tree = TodoTree.from_json(obj.TreeData)
                self._current_file = doc.FileName or f"<{doc.Name}>"
                self._breadcrumb_path = ["root"]
                self._refresh_view()
                return
```

### Interaction with the live document (Interpretation A)

The Todo Browser also has a **"Load Active Document"** button. When clicked, it reads `TreeData` directly from the in-memory `DocumentObject` (no file I/O needed). This lets the user compare todos across open documents by switching which document is active and clicking the button.

This is separate from the editable dock panel — the browser is always read-only. If the user wants to edit, they use the regular Todo Tree dock (which is tied to the active document).

### Live reload option

An optional **auto-refresh** checkbox. When enabled, a `QFileSystemWatcher` monitors the loaded `.FCStd` file for changes. When the file is written (e.g., after another FreeCAD instance saves it), the browser re-reads and refreshes the tree automatically. Useful for teams sharing a project file over a network folder.

```python
self._watcher = QFileSystemWatcher()
self._watcher.fileChanged.connect(self._on_file_changed)

def _on_file_changed(self, path):
    if self._auto_refresh and path == self._current_file:
        self.load_file(path)
```

---

## Registration

The `Todo Browser` panel is registered as a second dock widget, separate from the main `Todo Tree` dock. It appears in the `View → Panels` menu under `Todo Browser` and can be opened from the `Todo Tree` workbench menu.

A new FreeCAD command `TodoTree_OpenBrowser` opens or raises it.

No changes to `TodoDockWidget`, `model_registry`, or any of the existing editing infrastructure.

---

## Files Changed

| File | Change |
|---|---|
| `fcstd_reader.py` | New — pure-Python ZIP parser, no FreeCAD deps |
| `todo_browser.py` | New — read-only viewer dock with file picker and live reload |
| `commands.py` | Add `_OpenBrowserCommand` / `TodoTree_OpenBrowser` |
| `init_gui.py` | Add `TodoTree_OpenBrowser` to menu |

No changes to any existing editing files.

---

## Limitations and Open Questions

1. **ZIP corruption risk for writes:** The read-only constraint for on-disk files is intentional. If write-back is later desired, the safest approach is to open the document in FreeCAD normally (triggering FreeCAD's own save machinery) rather than writing the ZIP directly.

2. **Encrypted/compressed XML:** FreeCAD supports compressed `Document.xml.gz` inside the ZIP for large documents. The reader would need to handle both `Document.xml` and `Document.xml.gz`.

3. **Multiple `TodoTree` objects:** A document could theoretically have more than one `TodoTree` object (e.g., if the addon was reinstalled). The reader should return the first one found, matching the behaviour of `find_todo_object()`.

4. **File picker UX:** Whether to use a `QFileDialog` or a persistent text field with history is a preference question. A persistent path with a recent-files dropdown is more convenient for reviewing multiple projects.

5. **Cross-platform path handling:** The watcher's `fileChanged` signal fires after a file is written, but some editors/platforms write to a temp file then rename, causing the watcher to lose track. A polling fallback (every few seconds) may be needed for robustness.
