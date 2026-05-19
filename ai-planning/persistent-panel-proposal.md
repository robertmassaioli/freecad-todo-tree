# Persistent Panel Proposal (Report-View Style)

**Date:** 2026-05-19  
**Status:** Revised after deep FreeCAD source analysis

---

## What Already Works

Our `TodoDockWidget` is already a persistent dock. Once created it:

- Stays visible when switching to any workbench (confirmed by source: `DockWindowManager::setup()` only manages docks it registered; ours bypasses that system entirely)
- Automatically shows the active document's todos via `_DocObserver`
- **Already appears in `View → Panels`** — the menu is populated dynamically by `MainWindow::populateDockWindowMenu()` which calls `findChildren<QDockWidget*>()` on the main window at menu-open time. Any dock added with `mw.addDockWidget()` is included automatically, no C++ registration required.

The only gap: the dock is created the first time the user activates the TodoTree workbench. If they never do, it doesn't exist yet.

---

## What the Source Says

### `View → Panels` menu — `MainWindow.cpp` lines 1593–1615

```cpp
void MainWindow::onDockWindowMenuAboutToShow() {
    auto menu = static_cast<QMenu*>(sender());
    menu->clear();
    populateDockWindowMenu(menu);
}

void MainWindow::populateDockWindowMenu(QMenu* menu) {
    QList<QDockWidget*> dock = this->findChildren<QDockWidget*>();
    for (auto& it : dock) {
        menu->addAction(it->toggleViewAction());
    }
}
```

**Every `QDockWidget` child of the main window is listed.** No registration step needed.

### `WorkbenchManipulator::modifyDockWindows()` — dead end

The Python binding calls `tryModifyDockWindows(dict, dockWindow)` whose body is:

```cpp
void WorkbenchManipulatorPython::tryModifyDockWindows(
    [[maybe_unused]] const Py::Dict& dict,
    [[maybe_unused]] DockWindowItems* dockWindow)
{}
```

Empty. Marked `[[maybe_unused]]`. Never implemented. Not a viable path.

### `DockWindowItems` — no Python binding

`DockWindowItems::addDockWidget(name, pos, option)` is C++ only. There is no Python binding anywhere in the source tree.

### BIM module uses exactly our approach

`BimViews.py` lines 160–175:

```python
mw = FreeCADGui.getMainWindow()
mw.addDockWidget(self.getDockArea(area), vm)
```

Direct `mw.addDockWidget()`. Same mechanism we use. BIM panels appear in `View → Panels` automatically.

### Startup timing — `Workbench.cpp` lines 463–466

```cpp
DockWindowItems* dw = setupDockWindows();
WorkbenchManipulator::changeDockWindows(dw);  // Python modifyDockWindows (empty)
DockWindowManager::instance()->setup(dw);     // applies panel visibility
delete dw;
```

This runs every time a workbench is activated, including at startup. The `workbenchActivated` Qt signal on `MainWindow` fires after this sequence completes. At that point `getMainWindow()` is fully initialised and `addDockWidget()` is safe to call.

---

## The Fix: Two Lines in `init_gui.py`

The entire gap is solved by creating the dock during addon load, deferred to the first `workbenchActivated` signal — which fires within milliseconds of startup as FreeCAD activates the user's saved workbench.

```python
# init_gui.py — add after Gui.addWorkbench(TodoTreeWorkbench)

def _bootstrap_dock(wb_name: str) -> None:
    """Create the Todo Tree dock on the first workbench activation at startup."""
    mw = Gui.getMainWindow()
    mw.workbenchActivated.disconnect(_bootstrap_dock)
    from .dock_widget import show_dock
    show_dock()

mw = Gui.getMainWindow()
if mw is not None:
    mw.workbenchActivated.connect(_bootstrap_dock)
```

### Why `workbenchActivated` and not `QTimer.singleShot(0, ...)`?

A zero-delay timer fires after the current event loop turn. At addon-load time during FreeCAD startup, the main window layout is mid-construction — the dock areas may not be finalised. `workbenchActivated` fires at an exact, well-defined point: after the workbench's setup sequence has completed and the main window is stable. This is the same moment FreeCAD itself calls `DockWindowManager::setup()`.

### Why not call `show_dock()` directly at module level?

`init_gui.py` runs during FreeCAD's Python module scan, before the main window fully exists. `getMainWindow()` may return `None` at this point. The deferred approach is safe even if `getMainWindow()` returns `None` (the connection is simply not made; the dock will be created when the user first activates the TodoTree workbench as today).

---

## Resulting Behaviour

| Situation | Before | After |
|---|---|---|
| User launches FreeCAD, never switches to TodoTree workbench | Dock not created | Dock created automatically on first workbench activation |
| User opens `View → Panels` | "Todo Tree" absent until workbench visited | "Todo Tree" present from first session |
| User closes the dock (clicks X) | Must re-open from TodoTree workbench | Can re-open from `View → Panels` |
| Dock tracks active document | Yes (once created) | Yes (same behaviour) |
| Dock persists across workbench switches | Yes (once created) | Yes (same behaviour) |

---

## Files Changed

| File | Change |
|---|---|
| `init_gui.py` | Add ~8 lines: connect `workbenchActivated` to `_bootstrap_dock` after workbench registration |

No other files need to change. `show_dock()` in `dock_widget.py` is already idempotent — calling it more than once is safe.

---

## Open Questions

1. **Default visibility:** Should the dock start visible or hidden? Starting visible mirrors Report View behaviour. Starting hidden (dock exists but is closed) is less intrusive for users who never use the addon. Recommended: start visible — the user explicitly installed the addon.

2. **One-time connect safety:** The `disconnect` inside `_bootstrap_dock` must not throw if the signal was already disconnected. In PySide6 this is safe; in PySide2 a `RuntimeError` is raised if the signal is not connected. A `try/except RuntimeError: pass` guard may be needed for PySide2 compatibility.
