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


class _OutdentItemCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Outdent"),
            "MenuText": "Outdent Todo Item",
            "ToolTip": "Raise this item one level in the hierarchy",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.outdent_item()

    def IsActive(self):
        return _active_doc() is not None


class _IndentItemCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Indent"),
            "MenuText": "Indent Todo Item",
            "ToolTip": "Lower this item one level under its previous sibling",
        }

    def Activated(self):
        panel = _get_dock_panel()
        if panel:
            panel.indent_item()

    def IsActive(self):
        return _active_doc() is not None


class _ClearAllCommand:
    def GetResources(self):
        return {
            "Pixmap": as_icon("Delete"),
            "MenuText": "Reset Todo List",
            "ToolTip": (
                "Remove all todo items from this document and start fresh. "
                "Also cleans up any duplicate TodoTree objects left by earlier versions."
            ),
        }

    def Activated(self):
        doc = _active_doc()
        if not doc:
            return

        try:
            from PySide.QtWidgets import QMessageBox
            from PySide.QtCore import Qt
        except ImportError:
            from PySide2.QtWidgets import QMessageBox
            from PySide2.QtCore import Qt

        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        answer = QMessageBox.warning(
            mw,
            "Reset Todo List",
            "This will permanently delete all todo items in this document.\n\n"
            "This cannot be undone.\n\nAre you sure?",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Ok:
            return

        # Find every object with our two distinctive properties and remove them all.
        # This handles both the normal case and documents with duplicate objects
        # left by earlier versions of the addon.
        to_remove = [
            obj.Name for obj in doc.Objects
            if "TreeData" in getattr(obj, "PropertiesList", [])
            and "ViewState" in getattr(obj, "PropertiesList", [])
        ]

        if not to_remove:
            return

        doc.openTransaction("Todo: clear todo list")
        for name in to_remove:
            doc.removeObject(name)
        doc.commitTransaction()
        doc.recompute()

        # Purge the stale model so the dock rebuilds cleanly.
        from .model_registry import invalidate_model
        invalidate_model(doc.Name)

        # Tell the dock to refresh; ensure_model will create a new empty object.
        from .dock_widget import get_dock
        dock = get_dock()
        if dock:
            dock.switch_to_document(doc)

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
    FreeCADGui.addCommand("TodoTree_OutdentItem", _OutdentItemCommand())
    FreeCADGui.addCommand("TodoTree_IndentItem", _IndentItemCommand())
    FreeCADGui.addCommand("TodoTree_ClearAll", _ClearAllCommand())
