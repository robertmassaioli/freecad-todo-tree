# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""FeaturePython proxy and ViewProvider for the TodoTree document object."""

import FreeCAD
from .todo_model import EMPTY_TREE, EMPTY_VIEW_STATE, TodoTree
from .resources import as_icon
import json


OBJECT_TYPE = "App::FeaturePython"
OBJECT_NAME = "TodoTree"


def _log(msg):
    FreeCAD.Console.PrintMessage(f"TodoTree [obj] {msg}\n")


class TodoTreeObject:
    """FeaturePython proxy. Stores todo data in two App::PropertyString fields."""

    def __init__(self, obj):
        # Called only on first creation, not on document restore.
        _log(f"TodoTreeObject.__init__ called for {obj.Name!r}")
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
        _log(f"TodoTreeObject.onDocumentRestored called for {obj.Name!r}")
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
        _log(f"ViewProviderTodoTree.__init__ called, vobj={vobj!r}")
        vobj.Proxy = self

    def onDocumentRestored(self, vobj):
        _log(f"ViewProviderTodoTree.onDocumentRestored called, proxy type before={type(vobj.Proxy)!r}")
        vobj.Proxy = self
        _log(f"ViewProviderTodoTree.onDocumentRestored: proxy re-attached, type after={type(vobj.Proxy)!r}")

    def getIcon(self):
        _log("ViewProviderTodoTree.getIcon called")
        return as_icon("Logo")

    def doubleClicked(self, vobj):
        _log("ViewProviderTodoTree.doubleClicked called")
        from .main_view import open_main_view
        from .model_registry import ensure_model
        model = ensure_model(vobj.Object.Document)
        open_main_view(vobj.Object, model)
        return True

    def onChanged(self, vobj, prop):
        pass

    def dumps(self):
        _log("ViewProviderTodoTree.dumps called")
        return None

    def loads(self, state):
        _log(f"ViewProviderTodoTree.loads called, state={state!r}")
        return None


def find_todo_object(doc):
    """Return the TodoTree FeaturePython object in doc, or None."""
    for obj in doc.Objects:
        proxy = getattr(obj, "Proxy", None)
        _log(f"find_todo_object: checking {obj.Name!r}, proxy type={type(proxy)!r}, proxy={proxy!r}")
        if isinstance(proxy, TodoTreeObject):
            _log(f"find_todo_object: found {obj.Name!r}")
            return obj
    _log("find_todo_object: not found")
    return None


def find_or_create_todo_object(doc):
    """Return the existing TodoTree object, creating one if absent."""
    _log(f"find_or_create_todo_object called for doc={doc.Name!r}")
    existing = find_todo_object(doc)
    if existing:
        _log(f"find_or_create_todo_object: returning existing {existing.Name!r}")
        vp_proxy = getattr(existing.ViewObject, "Proxy", None)
        _log(f"find_or_create_todo_object: ViewObject.Proxy type={type(vp_proxy)!r}, value={vp_proxy!r}")
        return existing

    _log("find_or_create_todo_object: creating new TodoTree object")
    obj = doc.addObject(OBJECT_TYPE, OBJECT_NAME)
    TodoTreeObject(obj)
    if FreeCAD.GuiUp:
        ViewProviderTodoTree(obj.ViewObject)
    doc.recompute()
    return obj
