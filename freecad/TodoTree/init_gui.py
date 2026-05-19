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

    def Activated(self):
        from .dock_widget import show_dock
        show_dock()

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(TodoTreeWorkbench)
FreeCAD.Console.PrintLog("TodoTree: workbench registered successfully\n")
