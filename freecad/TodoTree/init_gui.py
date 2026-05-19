# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""Workbench definition and GUI initialisation entry point."""

import FreeCAD
import FreeCADGui as Gui

FreeCAD.Console.PrintLog("TodoTree: init_gui.py starting\n")

from .resources import as_icon
from .commands import register_commands

FreeCAD.Console.PrintLog("TodoTree: imports complete\n")


class TodoTreeWorkbench(Gui.Workbench):
    MenuText = "Todo Tree"
    ToolTip = "Hierarchical todo list saved with your FreeCAD document"
    Icon = as_icon("Logo")

    def Initialize(self):
        register_commands()

        toolbar_cmds = [
            "TodoTree_ShowDock",
            "TodoTree_OpenMainView",
            "TodoTree_AddItem",
            "TodoTree_AddChild",
            "TodoTree_DeleteItem",
            "TodoTree_OutdentItem",
            "TodoTree_IndentItem",
            "TodoTree_NavigateInto",
            "TodoTree_ToggleShowDone",
        ]
        self.appendToolbar("Todo Tree", toolbar_cmds)
        self.appendMenu("Todo Tree", toolbar_cmds)
        # Destructive command in its own group at the bottom of the menu.
        self.appendMenu("Todo Tree", ["Separator", "TodoTree_ClearAll"])

    def Activated(self):
        from .dock_widget import show_dock
        show_dock()

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(TodoTreeWorkbench)
FreeCAD.Console.PrintLog("TodoTree: workbench registered successfully\n")

# ── Startup dock bootstrap ─────────────────────────────────────────────────
#
# View → Panels is populated by MainWindow::populateDockWindowMenu() which
# calls findChildren<QDockWidget*>() at menu-open time, so any dock added
# via mw.addDockWidget() appears there automatically — no C++ registration
# needed.  The only requirement is that the dock must be created before the
# user opens that menu.
#
# We hook workbenchActivated, which fires once the first workbench's setup
# sequence has fully completed and the main window is stable — the earliest
# safe moment to call addDockWidget().  The hook disconnects itself after the
# first firing so it runs exactly once per session.

def _bootstrap_dock(wb_name: str) -> None:
    mw = Gui.getMainWindow()
    try:
        mw.workbenchActivated.disconnect(_bootstrap_dock)
    except RuntimeError:
        pass  # already disconnected (PySide2 raises if not connected)
    from .dock_widget import show_dock
    show_dock()

_mw = Gui.getMainWindow()
if _mw is not None:
    _mw.workbenchActivated.connect(_bootstrap_dock)
del _mw
