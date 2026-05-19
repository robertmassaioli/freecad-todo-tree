# Persistent Panel Proposal (Report-View Style)

**Date:** 2026-05-19  
**Status:** Proposal — pending implementation decision

---

## What Already Exists

The current `TodoDockWidget` is already a persistent dock. Once created, it:

- Stays visible when the user switches to any other workbench (PartDesign, Sketcher, etc.)
- Automatically shows the todo tree for whichever document becomes active
- Shows a placeholder ("Open a document to use Todo Tree") when no document is open
- Is managed entirely outside FreeCAD's per-workbench layout system, so workbench switches never hide it

**The only gap:** the dock is created the first time the user activates the TodoTree workbench. If the user never switches to that workbench in a given FreeCAD session, the dock never appears. This is unlike Report View, which is available from the moment FreeCAD starts.

---

## Desired Behaviour

The Todo Tree panel should be available immediately at FreeCAD startup:

- Visible in **View → Panels → Todo Tree** (the same menu as Report View, Model, etc.)
- Openable without ever switching to the TodoTree workbench
- Persistently visible across all workbench switches, just as it is today once created

---

## Why This Is Non-Trivial

FreeCAD's **View → Panels** menu is populated by `DockWindowManager::registerDockWindow()` — a C++ singleton not exposed to Python. Standard Python addons cannot add entries to that menu.

What Python addons *can* do:

1. Call `mw.addDockWidget(area, dock)` at any time after the main window exists.
2. Attach to Qt signals on the main window (`workbenchActivated`) or FreeCAD events to know when the GUI is ready.
3. Register `WorkbenchManipulator` instances that run on every workbench switch.

The challenge is **timing**: `InitGui.py` runs at FreeCAD startup, but at that point the main window may not yet be fully initialised and `getMainWindow()` may return `None` or a partially-built window.

---

## Proposed Solution: Deferred Startup via `workbenchActivated` Signal

Hook the main window's `workbenchActivated(name: str)` Qt signal. This fires once for every workbench switch, including the very first one at FreeCAD startup (when the default workbench, typically `NoneWorkbench` or the user's saved workbench, is activated). We use this as the trigger to create the dock the first time, then immediately disconnect — so the hook runs exactly once.

```python
# In init_gui.py, at module level (runs when the addon loads):

def _create_dock_on_first_workbench(wb_name: str):
    """Called once after the first workbench activates at startup."""
    from .dock_widget import show_dock
    mw = FreeCADGui.getMainWindow()
    mw.workbenchActivated.disconnect(_create_dock_on_first_workbench)
    show_dock()

mw = FreeCADGui.getMainWindow()
if mw is not None:
    mw.workbenchActivated.connect(_create_dock_on_first_workbench)
```

This has a well-defined invariant: the dock is created no later than the first workbench switch, which happens within milliseconds of FreeCAD's GUI becoming ready. From the user's perspective the dock is simply "always there".

### Why not `QTimer.singleShot(0, show_dock)`?

A zero-delay timer fires after the current event loop iteration completes, which sounds right but is unreliable at startup because the main window's layout isn't stable yet. The `workbenchActivated` signal fires at exactly the right moment — after Qt has finished building the workbench UI.

### Why not a `WorkbenchManipulator`?

`WorkbenchManipulator` is a FreeCAD C++/Python bridge that runs on every workbench switch. We could call `show_dock()` from it, but `show_dock()` is idempotent (does nothing if the dock already exists), so calling it on every workbench switch is harmless but wasteful. The one-time signal connection is cleaner.

---

## View → Panels Integration

Since `DockWindowManager::registerDockWindow()` is not accessible from Python, we cannot add an entry to the native **View → Panels** menu. Two workarounds:

**Option A — Todo Tree menu item (simplest):**  
Add "Show Todo Panel" to the top-level **Todo Tree** menu (already exists via `appendMenu`). Users open the panel from here if they accidentally close it. This is exactly what many other Python addons do.

**Option B — View menu injection:**  
`appendMenu(["View", "Panels"], ["TodoTree_ShowDock"])` adds the command to `View → Panels` via FreeCAD's Python menu API. This places it alongside Report View, Python Console etc. in the exact right location.  
Risk: The `"Panels"` submenu name is locale-dependent (translated in non-English FreeCAD). A fallback to Option A is needed if the submenu can't be found.

**Recommendation: Option B, with Option A as fallback.** Try to inject into `View → Panels`; if the submenu is absent (translated or restructured), fall back to the Todo Tree menu.

```python
# In TodoTreeWorkbench.Initialize():
try:
    self.appendMenu(["&View", "Panels"], ["TodoTree_ShowDock"])
except Exception:
    self.appendMenu("Todo Tree", ["TodoTree_ShowDock"])
```

---

## Files Changed

| File | Change |
|---|---|
| `init_gui.py` | Connect `workbenchActivated` signal at module load to create dock on first startup |
| `init_gui.py` | Attempt to inject `TodoTree_ShowDock` into `View → Panels` menu |
| `dock_widget.py` | No change needed — `show_dock()` is already idempotent |

No changes to any other file. The dock widget, observer, and tree panel are already implemented correctly — this proposal is purely about *when* the dock is first created.

---

## What Changes From the User's Perspective

| Before | After |
|---|---|
| Must switch to Todo Tree workbench at least once per session | Panel appears immediately at FreeCAD startup |
| Panel listed only in Todo Tree workbench menu | Panel listed in View → Panels (or Todo Tree menu as fallback) |
| Panel state restored from QMainWindow saved state on restart | Same — no change |
| Dock tracks active document automatically | Same — no change |

---

## Open Questions

1. **Default visibility:** Should the dock start hidden (user opens it from the menu) or start visible? Starting visible is consistent with Report View behaviour but may annoy users who never use the addon. Starting hidden (dock exists but `hide()` is called) is safer — the user still gets it in View → Panels without it cluttering their layout on first launch.

2. **Locale robustness of `View → Panels`:** The submenu name needs testing on non-English FreeCAD. The `appendMenu` API uses the untranslated name (the key), so `"Panels"` should work regardless of locale if FreeCAD uses internal menu IDs — but this needs verification.
