# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""FreeCAD GUI commands for the Todo Tree workbench."""

import FreeCAD
import FreeCADGui

from .resources import as_icon


def _active_doc():
    return FreeCAD.ActiveDocument


def _get_dock_panel():
    from .dock_widget import get_dock
    dock = get_dock()
    return dock.panel if dock else None


class _ShowDockCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Logo"),
            "MenuText": "Show Todo Panel",
            "ToolTip": "Show or raise the Todo Tree dock panel",
        }

    def Activated(self):
        from .dock_widget import show_dock
        show_dock()

    def IsActive(self):
        return True


class _OpenMainViewCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Logo"),
            "MenuText": "Open Todo Tree View",
            "ToolTip": "Open the todo tree in the main window area",
        }

    def Activated(self):
        doc = _active_doc()
        if not doc:
            return
        from .model_registry import ensure_model
        from .main_view import open_main_view
        model = ensure_model(doc)
        open_main_view(model._fc_object, model)

    def IsActive(self):
        return _active_doc() is not None


class _AddItemCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("AddItem"),
            "MenuText": "Add Todo Item",
            "ToolTip": "Add a new item at the same level as the selection",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.add_item()

    def IsActive(self):
        return _active_doc() is not None


class _AddChildCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("AddChild"),
            "MenuText": "Add Child Item",
            "ToolTip": "Add a child item under the selection",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.add_child_item()

    def IsActive(self):
        return _active_doc() is not None


class _DeleteItemCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Delete"),
            "MenuText": "Delete Todo Item",
            "ToolTip": "Delete the selected item and all its children",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.delete_item()

    def IsActive(self):
        return _active_doc() is not None


class _NavigateIntoCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Logo"),
            "MenuText": "Navigate Into",
            "ToolTip": "Make the selected item the root of the view",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.navigate_into()

    def IsActive(self):
        return _active_doc() is not None


class _ToggleShowDoneCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Logo"),
            "MenuText": "Toggle Show Done",
            "ToolTip": "Show or hide completed todo items",
            "Checkable": True,
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.toggle_show_done()

    def IsActive(self):
        return _active_doc() is not None


def register_commands():
    FreeCADGui.addCommand("TodoTree_ShowDock", _ShowDockCommand())
    FreeCADGui.addCommand("TodoTree_OpenMainView", _OpenMainViewCommand())
    FreeCADGui.addCommand("TodoTree_AddItem", _AddItemCommand())
    FreeCADGui.addCommand("TodoTree_AddChild", _AddChildCommand())
    FreeCADGui.addCommand("TodoTree_DeleteItem", _DeleteItemCommand())
    FreeCADGui.addCommand("TodoTree_NavigateInto", _NavigateIntoCommand())
    FreeCADGui.addCommand("TodoTree_ToggleShowDone", _ToggleShowDoneCommand())
