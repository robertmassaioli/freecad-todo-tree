# Navigation Keyboard Shortcuts Proposal

**Date:** 2026-05-19  
**Status:** Proposal — pending implementation decision

---

## Current State

No keyboard shortcuts exist for **Go Into** or **Go Up**.

The existing shortcuts are:

| Shortcut | Scope | Action |
|---|---|---|
| Tab | Widget (tree view) | Indent selected item |
| Shift+Tab | Widget (tree view) | Outdent selected item |
| Double-click | Widget | Inline-edit item label |

Tab and Shift+Tab were implemented as `QShortcut` with `Qt.WidgetShortcut` scope — they fire only when the tree view has keyboard focus and are **not** visible in Tools → Customize → Keyboard.

---

## How FreeCAD Keyboard Shortcuts Work

### The two mechanisms

**`QShortcut` (widget-scoped)**
Fires only when a specific widget has focus. Bypasses FreeCAD's command system entirely. Does not appear in Tools → Customize → Keyboard. Cannot be remapped by users.
*Used for Tab/Shift+Tab because indent/outdent are pure panel-internal operations with no global meaning.*

**`"Accel"` in `GetResources()`**
Registered with FreeCAD's `ShortcutManager` via `FreeCADGui.addCommand()`. Appears in **Tools → Customize → Keyboard** in the "Default" column. Users can remap it. The Python command's `Activated()` is called regardless of which widget has focus.

```python
def GetResources(self):
    return {
        "MenuText": "Navigate Into",
        "Accel": "Enter",          # default shortcut
        "ToolTip": "...",
    }
```

From `src/Gui/Command.cpp`:
```cpp
void Command::initAction() {
    setShortcut(ShortcutManager::instance()->getShortcut(getName(), getAccel()));
}
```

The dialog (`DlgKeyboardImp.cpp`) lists all commands from the CommandManager — including Python commands registered with `addCommand()` — showing their current shortcut and default `Accel`.

### Conflict landscape

| Key(s) | Owner | Notes |
|---|---|---|
| Tab | Ours (widget-scoped) | Indent |
| Shift+Tab / Backtab | Ours (widget-scoped) | Outdent |
| Arrow keys (bare) | Qt / QTreeView built-in | Up/Down = row selection, Left/Right = collapse/expand |
| Alt+Up/Down/Left/Right | BIM workbench (global) | Nudge operations — **conflict risk** |
| Ctrl+Z / Ctrl+Y | FreeCAD core | Undo / Redo |
| Delete | FreeCAD core | Standard delete |
| F2 | FreeCAD core | Rename in model tree |
| Enter | **Available** | QTreeView activates row but we use DoubleClicked edit trigger only |
| Backspace | **Available** | No QTreeView built-in, no core claim |

---

## Recommended Shortcuts

### Widget-scoped shortcuts (primary UX — fires when dock is focused)

These match the conventions of every mainstream file browser and outliner
(macOS Finder, Windows Explorer, Workflowy, OmniOutliner):

| Shortcut | Action | Convention |
|---|---|---|
| **Enter** | Go Into — make selected item the view root | File browser: open folder |
| **Backspace** | Go Up — ascend one level in the breadcrumb | Browser: back button |

**Why Enter is safe:** We set `setEditTriggers(QAbstractItemView.DoubleClicked)`, so the `Enter` key does not trigger inline editing in our tree view. The key is available.

**Why Backspace is safe:** `QTreeView` has no built-in binding for Backspace. It is not claimed by any core FreeCAD shortcut.

These should be implemented as `QShortcut` with `Qt.WidgetShortcut` scope on the tree view — identical to the Tab/Shift+Tab approach. They only fire when the tree view has keyboard focus, so there is zero global conflict risk.

### FreeCAD command Accel (for discoverability in Tools → Customize → Keyboard)

The commands `TodoTree_NavigateInto` and `TodoTree_NavigateUp` already exist but have no `Accel`. Adding an `Accel` makes them discoverable and remappable:

| Command | Recommended Accel | Rationale |
|---|---|---|
| `TodoTree_NavigateInto` | *(none — see below)* | |
| `TodoTree_NavigateUp` | *(none — see below)* | |

**Why no global default Accel?**

`Enter` and `Backspace` are safe as *widget-scoped* shortcuts because they only fire when the tree view has focus. As *global* `Accel` shortcuts they would fire whenever any command input is active — including when the user is typing text or using other panels — which would be jarring.

The better approach: register the commands **without a default `Accel`** (omit the key entirely). This makes them appear in Tools → Customize → Keyboard as customisable commands with no default. Users who want a global shortcut can assign one themselves. The widget-scoped Enter/Backspace shortcuts provide the day-to-day UX without any global conflict risk.

---

## Implementation Plan

### 1. Widget-scoped shortcuts in `tree_panel.py`

Add two `QShortcut` instances alongside the existing Tab/Shift+Tab ones:

```python
sc_into = QShortcut(QKeySequence(Qt.Key_Return), self._tree_view)
sc_into.setContext(Qt.WidgetShortcut)
sc_into.activated.connect(self._navigate_into_selected)

# Qt.Key_Return = Enter; also bind Qt.Key_Enter (numpad Enter)
sc_into_kp = QShortcut(QKeySequence(Qt.Key_Enter), self._tree_view)
sc_into_kp.setContext(Qt.WidgetShortcut)
sc_into_kp.activated.connect(self._navigate_into_selected)

sc_up = QShortcut(QKeySequence(Qt.Key_Backspace), self._tree_view)
sc_up.setContext(Qt.WidgetShortcut)
sc_up.activated.connect(self._navigate_up)
```

Note: Qt distinguishes `Key_Return` (main Enter key) from `Key_Enter` (numpad Enter). Binding both gives consistent behaviour.

### 2. No Accel changes to `commands.py`

`TodoTree_NavigateInto` and `TodoTree_NavigateUp` already exist as FreeCAD commands and already appear in the command manager. They appear in Tools → Customize → Keyboard without a default shortcut, which is correct — the user can assign any global shortcut they want.

---

## Summary

| Shortcut | Mechanism | Action | Fires when |
|---|---|---|---|
| Enter (main + numpad) | QShortcut, WidgetShortcut | Go Into | Tree view has focus, item selected |
| Backspace | QShortcut, WidgetShortcut | Go Up | Tree view has focus |
| Tab | QShortcut, WidgetShortcut | Indent | Tree view has focus, item selected |
| Shift+Tab | QShortcut, WidgetShortcut | Outdent | Tree view has focus, item selected |
| *(user-assigned)* | FreeCAD Accel | Navigate Into | Global |
| *(user-assigned)* | FreeCAD Accel | Navigate Up | Global |

All four widget-scoped shortcuts are safe: no global conflicts, no QTreeView built-in conflicts, no BIM or core FreeCAD conflicts.
