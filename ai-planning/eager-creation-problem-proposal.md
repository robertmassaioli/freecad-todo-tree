# TodoTree Object Eager Creation Problem — Proposal

**Date:** 2026-05-19  
**Status:** Proposal — pending implementation decision

---

## Problem Statement

When FreeCAD opens a document that already has a `TodoTree` object, the addon
creates one or two **duplicate** `TodoTree` objects before the restore cycle
completes. The duplicates appear as "unnamed" entries in the Model panel, and
the original saved data ends up in a renamed object (`TodoTree002`) that the
dock ignores in favour of the empty duplicates it created first.

---

## Root Cause (confirmed by diagnostic logging)

### The bootstrap creates the observer too early

`init_gui.py` connects `_bootstrap_dock` to `workbenchActivated`. This fires
during FreeCAD startup — sometimes while a document is mid-restore. At that
moment `show_dock()` runs, which:

1. Creates `TodoDockWidget`
2. Registers `_DocObserver` with `FreeCAD.addDocumentObserver()`
3. Calls `switch_to_document(active)` directly if a document is active

From this point, every `slotActivateDocument` signal FreeCAD fires during the
rest of its document restore cycle hits `switch_to_document` →
`ensure_model` → `find_or_create_todo_object`.

### `slotActivateDocument` fires multiple times with `doc.Objects == []`

FreeCAD fires `slotActivateDocument` several times during document restore —
including at least twice when `doc.Objects` is empty. The confirmed log
sequence is:

```
slotActivateDocument  objects=[]   → find_or_create creates TodoTree #1
slotCreatedDocument                (FreeCAD internally recreates the doc)
slotDeletedDocument
slotActivateDocument  objects=[]   → find_or_create creates TodoTree #2
slotCreatedDocument
slotActivateDocument  objects=['TodoTree']
TodoTreeObject.loads / onDocumentRestored   (original saved object restored)
slotActivateDocument  objects=['TodoTree', 'TodoTree001', ...]
  → find_or_create finally finds the original; returns it
```

The document ends up with three `TodoTree` objects. The original saved data
is in `TodoTree002` (renamed due to name conflicts). The dock connects to the
empty `TodoTree` instead.

### `slotStartRestoreDocument` does not fire

The guard we added in `_DocObserver` — marking a document as "mid-restore"
using `slotStartRestoreDocument` / `slotFinishRestoreDocument` — never
engaged, because those slots **do not fire** for documents opened this way.
They are absent from all log output. They either do not exist in FreeCAD's
Python observer API for this version, or are not emitted for the
recently-opened-files load path.

### The property-name fallback cannot help

The mid-restore fallback added to `find_todo_object` (checking for `TreeData`
and `ViewState` in `obj.PropertiesList`) cannot prevent duplicate creation
when `doc.Objects` is literally `[]` — there are no objects to iterate at all
during the first two activations.

---

## Option A — Remove the bootstrap; dock is created on first workbench visit

**Change:** Delete `_bootstrap_dock` from `init_gui.py`. The dock is created
the first time the user activates the TodoTree workbench, exactly as before
the persistent-panel feature was added. The dock persists across workbench
switches for the remainder of the session (this still works; `DockWindowManager`
does not touch docks outside its registry).

**Behaviour change:**
- The dock does not appear in `View → Panels` until after the user visits the
  TodoTree workbench at least once per FreeCAD session.
- After that first visit the dock is fully persistent as before.

**Pro:** Zero timing issues. The observer is registered only after the document
is fully loaded and stable.

**Con:** Loses the "always available from startup" behaviour that was
specifically implemented to match Report View.

---

## Option B — Keep the bootstrap; never create objects from the observer path; only find

**Change:** Split the responsibility of `switch_to_document`. When called from
the observer (during the restore window), it calls `find_todo_object` (read-only)
instead of `ensure_model` (find-or-create). If an existing `TodoTree` is found,
connect to it normally. If not found, show the placeholder. The `TodoTree`
object is only created on the **first explicit user action** (adding an item,
opening the main view, etc.).

**Implementation sketch:**

```python
# dock_widget.py — switch_to_document
def switch_to_document(self, doc):
    ...
    from .todo_object import find_todo_object
    fc_obj = find_todo_object(doc)

    if fc_obj is None:
        # Document has no TodoTree yet — show placeholder.
        # Object will be created when the user adds their first item.
        self.setWidget(self._placeholder)
        self._panel = None
        return

    # Existing object found — connect to it (or create the model if needed).
    from .model_registry import ensure_model
    model = ensure_model(doc)
    ...
```

```python
# model_registry.py — add a find-only variant
def get_or_create_model_if_object_exists(doc):
    """Return model if a TodoTree object already exists; None otherwise."""
    from .todo_object import find_todo_object
    if doc.Name not in _registry:
        fc_obj = find_todo_object(doc)
        if fc_obj is None:
            return None
        tree = TodoTree.from_json(fc_obj.TreeData)
        _registry[doc.Name] = TodoItemModel(tree, fc_obj)
    return _registry[doc.Name]
```

Commands that require the object (`+ Item`, `+ Child`, etc.) continue to call
`ensure_model` (find-or-create), which creates the object on first use.

**Behaviour change:**
- A brand-new document without a saved `TodoTree` shows the placeholder panel
  until the user adds their first item.
- An existing document with a `TodoTree` connects to it immediately on load
  (the `find_todo_object` property-name fallback handles mid-restore correctly
  once objects start appearing, and the final `slotActivateDocument` with all
  objects present will connect successfully).

**Pro:**
- The persistent-panel feature stays fully intact.
- No object is ever created as a side-effect of the dock appearing.
- Eliminates the race condition at the architectural level.

**Con:**
- New documents show a placeholder panel rather than an immediately usable
  empty tree. This is a minor UX difference that is reasonable — many apps
  show an empty state until you create your first item.

### Option B placeholder design

There are two distinct placeholder states:

**State 1 — No document open** *(existing)*  
The current `QLabel("Open a document to use Todo Tree.")` remains unchanged.

**State 2 — Document open, no TodoTree yet** *(new)*  
Three sub-options:

**B1 — Minimal text + action button (recommended)**
```
┌─────────────────────────────┐
│                             │
│                             │
│     No todo items yet.      │
│                             │
│   [ + Add your first item ] │
│                             │
│                             │
└─────────────────────────────┘
```
A centered label and a single `QPushButton` that triggers the same action as
the `+ Item` toolbar button. Clicking it creates the `TodoTree` object and
immediately opens the new item in inline edit mode. Clean, action-oriented,
zero ambiguity.

**B2 — Icon + description + button**
```
┌─────────────────────────────┐
│                             │
│         [logo icon]         │
│                             │
│  Organise tasks for this    │
│  document as a tree.        │
│                             │
│   [ + Add your first item ] │
│                             │
└─────────────────────────────┘
```
Slightly more onboarding-friendly; useful if users discover the panel
without having explicitly opened it.

**B3 — Text only, pointing to the toolbar**
```
┌─────────────────────────────┐
│                             │
│  No todo items yet.         │
│                             │
│  Use the + Item button in   │
│  the toolbar above to add   │
│  your first task.           │
│                             │
└─────────────────────────────┘
```
No button in the placeholder. Simplest to implement but creates a dead-end
feel — users see text but nothing to interact with.

**Chosen: B1.** A single action button directly in the placeholder converts
"nothing here" to "adding my first item" in one click without requiring the
user to locate the toolbar. This pattern is standard in modern productivity
apps (Notion, Linear, Todoist).

---

## Option C — Guard on `doc.Objects` being non-empty

**Change:** In `slotActivateDocument`, if `doc.Objects` is empty, call
`switch_to_document(None)` (show placeholder) instead of
`switch_to_document(doc)`. Let the next non-empty `slotActivateDocument` do
the real work.

```python
def slotActivateDocument(self, doc):
    if not doc.Objects:
        _log(f"slotActivateDocument doc={doc.Name!r} SKIPPED (objects empty)")
        return
    ...
```

**Pro:** Smallest change — a single early-return guard.

**Con:** Heuristic. Relies on FreeCAD always firing at least one
`slotActivateDocument` with non-empty objects after restore completes. The
logs confirm it does today, but this could break silently on a future FreeCAD
version. It also means a newly-created empty document (which also has zero
objects) will never get `switch_to_document` called from `slotActivateDocument`
— it would have to rely on another signal path to connect.

---

## Option D — Remove the bootstrap and add a `View → Panels` entry manually

**Change:** Remove `_bootstrap_dock`. Add the dock to `View → Panels` by a
different mechanism — for example, injecting `TodoTree_ShowDock` into
`View → Panels` via `appendMenu(["&View", "Panels"], ...)` in
`TodoTreeWorkbench.Initialize()`. The dock still only appears when the user
opens it, but they can do so from `View → Panels` without needing to switch
workbenches.

**Pro:** Clean separation — no timing issues, dock is discoverable from the
standard UI location.  
**Con:** `View → Panels` injection via `appendMenu` may or may not work for
the "Panels" submenu (locale-dependent submenu name). Investigated previously;
works if the submenu name matches.

---

## Comparison

| | Timing safe | Dock in View→Panels on startup | Object only on user action | Complexity |
|---|---|---|---|---|
| **A** — Remove bootstrap | ✓ | ✗ | ✗ | Low |
| **B** — Find-only in observer | ✓ | ✓ | ✓ | Medium |
| **C** — Guard on objects empty | Probably | ✓ | ✗ | Very low |
| **D** — Remove bootstrap + menu injection | ✓ | ✓ (via menu) | ✗ | Low |

---

## Recommendation — Option B

Option B addresses the root cause rather than the symptom. The architectural
insight is that **the `TodoTree` document object should only be created on
deliberate user action**, not as a side-effect of the dock initialising. This
matches standard FreeCAD behaviour — workbench objects (spreadsheets, sketches,
bodies) are never created until the user explicitly requests them.

Option C is tempting for its simplicity but is a heuristic that masks the
underlying issue. Option A sacrifices the persistent-panel feature. Option D
requires verifying that `View → Panels` injection works reliably across locales.

The UX change in Option B is minimal and arguably more correct: an empty
placeholder saying "Add your first item to get started" is a cleaner onboarding
experience than silently creating a hidden object the user didn't ask for.
