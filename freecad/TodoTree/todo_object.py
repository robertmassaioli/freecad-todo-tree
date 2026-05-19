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
        _log(f"TodoTreeObject.__init__ name={obj.Name!r}")
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
        _log(f"TodoTreeObject.onDocumentRestored name={obj.Name!r}")
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
        _log(f"TodoTreeObject.loads state={state!r}")
        return None


class ViewProviderTodoTree:
    """ViewProvider for TodoTreeObject. Provides icon and double-click to open main view."""

    def __init__(self, vobj):
        _log(f"ViewProviderTodoTree.__init__ vobj={vobj!r}")
        vobj.Proxy = self

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
        return None

    def loads(self, state):
        _log(f"ViewProviderTodoTree.loads state={state!r}")
        return None


def find_todo_object(doc):
    """Return the TodoTree FeaturePython object in doc, or None.

    Checks the proxy type first (fast path for a fully-initialised object).
    Falls back to a property-name check to catch objects that are mid-restore:
    FreeCAD loads properties from XML before calling onDocumentRestored, so
    'TreeData' and 'ViewState' are already present even while the proxy is
    still being reconstructed. Without this fallback, callers that run before
    onDocumentRestored (e.g. the startup dock bootstrap) would miss the
    existing object and create unwanted duplicates.
    """
    for obj in doc.Objects:
        proxy = getattr(obj, "Proxy", None)
        props = getattr(obj, "PropertiesList", [])
        has_tree_data = "TreeData" in props
        has_view_state = "ViewState" in props
        _log(
            f"find_todo_object: checking {obj.Name!r} "
            f"proxy={type(proxy).__name__!r} "
            f"TreeData={has_tree_data} ViewState={has_view_state}"
        )
        if isinstance(proxy, TodoTreeObject):
            _log(f"find_todo_object: found via proxy {obj.Name!r}")
            return obj
        # Mid-restore fallback: proxy not yet a TodoTreeObject but our
        # distinctive properties are already present in PropertiesList.
        if has_tree_data and has_view_state:
            _log(f"find_todo_object: found via properties {obj.Name!r}")
            return obj
    _log("find_todo_object: not found in doc")
    return None


def find_or_create_todo_object(doc):
    """Return the existing TodoTree object, creating one if absent."""
    import traceback
    _log(f"find_or_create_todo_object doc={doc.Name!r} objects={[o.Name for o in doc.Objects]!r}")
    _log(f"find_or_create_todo_object called from:\n{''.join(traceback.format_stack(limit=5))}")
    existing = find_todo_object(doc)
    if existing:
        vp_type = type(getattr(existing.ViewObject, "Proxy", None)).__name__
        _log(f"find_or_create_todo_object: returning existing {existing.Name!r} vp_proxy={vp_type!r}")
        return existing

    _log("find_or_create_todo_object: CREATING new object")
    obj = doc.addObject(OBJECT_TYPE, OBJECT_NAME)
    TodoTreeObject(obj)
    if FreeCAD.GuiUp:
        ViewProviderTodoTree(obj.ViewObject)
    doc.recompute()
    return obj
