# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Module-level registry mapping document name → TodoItemModel.

One model instance is shared between the dock widget and any open main views
for the same document. This means edits in either panel are instantly reflected
in the other via Qt's model/view signals.
"""

from .todo_model import TodoTree

# doc_name (str) → TodoItemModel instance
_registry: dict = {}


def get_model(doc):
    """Return the existing model for doc, or None."""
    return _registry.get(doc.Name)


def ensure_model(doc):
    """Return the model for doc, creating it (and the todo object) if needed."""
    if doc.Name not in _registry:
        from .todo_object import find_or_create_todo_object
        from .todo_item_model import TodoItemModel
        fc_obj = find_or_create_todo_object(doc)
        tree = TodoTree.from_json(fc_obj.TreeData)
        model = TodoItemModel(tree, fc_obj)
        _registry[doc.Name] = model
    return _registry[doc.Name]


def invalidate_model(doc_name):
    """Remove the cached model so the next ensure_model call rebuilds it."""
    _registry.pop(doc_name, None)


def notify_tree_changed(doc_name):
    """
    Called by TodoTreeObject.onChanged when TreeData changes (including undo/redo).
    Reload the in-memory model from the property so views reflect the reverted state.
    """
    model = _registry.get(doc_name)
    if model is not None and not model.is_flushing():
        model.reload_from_property()
