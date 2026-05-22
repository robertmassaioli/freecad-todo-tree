# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Categorical debug logging for the TodoTree addon.

Add categories to ENABLED to turn on specific logging. Leave the set
empty (the default) for silent operation.

Usage:
    from .debug import log, Category

    log(Category.DRAG_DROP, "some message")

Enabling examples:
    ENABLED = {Category.DRAG_DROP}
    ENABLED = {Category.DOCUMENT, Category.OBJECT}
    ENABLED = set(Category)   # everything
"""

import enum


class Category(enum.Enum):
    DRAG_DROP  = "drag_drop"   # drag-and-drop reorder gestures and drops
    DOCUMENT   = "document"    # document open / close / switch lifecycle
    OBJECT     = "object"      # FreeCAD TodoTree object and ViewProvider lifecycle
    BREADCRUMB = "breadcrumb"  # breadcrumb bar layout and truncation decisions


# Add Category members here to enable their logging output.
ENABLED: set = set()


def log(category: Category, msg: str) -> None:
    if category not in ENABLED:
        return
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(f"TodoTree [{category.value}] {msg}\n")
    except Exception:
        print(f"TodoTree [{category.value}] {msg}")
