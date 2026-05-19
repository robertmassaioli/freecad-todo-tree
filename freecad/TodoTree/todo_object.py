# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""FeaturePython proxy and ViewProvider for the TodoTree document object."""

import FreeCAD
from .todo_model import EMPTY_TREE, EMPTY_VIEW_STATE, TodoTree
from .resources import as_icon
import json


OBJECT_TYPE = "App::FeaturePython"
OBJECT_NAME = "TodoTree"


class TodoTreeObject:
    """FeaturePython proxy. Stores todo data in two App::PropertyString fields."""

    def __init__(self, obj):
        # Called only on first creation, not on document restore.
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if "TreeData" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyString", "TreeData", "TodoTree",
                "JSON-serialized todo tree", 4,
            )
            obj.TreeData = json.dumps(EMPTY_TREE)

        if "ViewState" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyString", "ViewState", "TodoTree",
                "JSON-serialized view state (not in undo stack)", 4,
            )
            obj.ViewState = json.dumps(EMPTY_VIEW_STATE)

    def onDocumentRestored(self, obj):
        obj.Proxy = self
        self._add_properties(obj)
        # Invalidate any stale in-memory model so it reloads from the property.
        from .model_registry import invalidate_model
        invalidate_model(obj.Document.Name)

    def onChanged(self, obj, prop):
        if prop == "TreeData":
            from .model_registry import notify_tree_changed
            notify_tree_changed(obj.Document.Name)

    def execute(self, obj):
        pass  # non-geometric object; nothing to recompute

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderTodoTree:
    """ViewProvider for TodoTreeObject. Provides icon and double-click to open main view."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return as_icon("Logo")

    def doubleClicked(self, vobj):
        from .main_view import open_main_view
        from .model_registry import ensure_model
        model = ensure_model(vobj.Object.Document)
        open_main_view(vobj.Object, model)
        return True

    def onChanged(self, vobj, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


def find_todo_object(doc):
    """Return the TodoTree FeaturePython object in doc, or None."""
    for obj in doc.Objects:
        if hasattr(obj, "Proxy") and isinstance(obj.Proxy, TodoTreeObject):
            return obj
    return None


def find_or_create_todo_object(doc):
    """Return the existing TodoTree object, creating one if absent."""
    existing = find_todo_object(doc)
    if existing:
        return existing

    obj = doc.addObject(OBJECT_TYPE, OBJECT_NAME)
    TodoTreeObject(obj)
    if FreeCAD.GuiUp:
        ViewProviderTodoTree(obj.ViewObject)
    doc.recompute()
    return obj
