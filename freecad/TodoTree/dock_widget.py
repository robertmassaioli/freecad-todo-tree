# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Persistent dock widget and document observer.

The dock is created once and persists across workbench switches.
A DocumentObserver keeps it in sync when the active document changes.
"""

from PySide.QtWidgets import QDockWidget, QLabel
from PySide.QtCore import Qt

import FreeCAD
import FreeCADGui

from .tree_panel import TreePanel


def _log(msg):
    FreeCAD.Console.PrintMessage(f"TodoTree [dock] {msg}\n")

_dock_instance = None
_observer = None


class TodoDockWidget(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Todo Tree", parent)
        self.setObjectName("TodoTreeDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._panel = None
        self._placeholder = QLabel("Open a document to use Todo Tree.", self)
        self._placeholder.setAlignment(Qt.AlignCenter)
        self.setWidget(self._placeholder)

    def switch_to_document(self, doc):
        """Replace the panel contents with the todo tree for doc."""
        # Clean up the old panel before replacing it.
        old = self.widget()
        if old and old is not self._placeholder:
            old.setParent(None)  # removes from Qt hierarchy; allows GC + signal cleanup

        if doc is None:
            self.setWidget(self._placeholder)
            self._panel = None
            return

        from .model_registry import ensure_model
        model = ensure_model(doc)
        fc_obj = model._fc_object

        # is_primary=True so this panel writes ViewState on navigation changes.
        panel = TreePanel(model, fc_obj, is_primary=True, parent=self)
        self.setWidget(panel)
        self._panel = panel

    @property
    def panel(self):
        return self._panel


class _DocObserver:
    def __init__(self):
        # Names of documents currently mid-restore. slotActivateDocument
        # fires with an empty objects list while a file is loading; we skip
        # those calls and wait for slotFinishRestoreDocument instead.
        self._restoring: set = set()

    def slotStartRestoreDocument(self, doc):
        _log(f"slotStartRestoreDocument doc={doc.Name!r}")
        self._restoring.add(doc.Name)

    def slotFinishRestoreDocument(self, doc):
        _log(f"slotFinishRestoreDocument doc={doc.Name!r} objects={[o.Name for o in doc.Objects]!r}")
        self._restoring.discard(doc.Name)
        dock = get_dock()
        if dock:
            dock.switch_to_document(doc)

    def slotActivateDocument(self, doc):
        if doc.Name in self._restoring:
            _log(f"slotActivateDocument doc={doc.Name!r} SKIPPED (mid-restore)")
            return
        _log(f"slotActivateDocument doc={doc.Name!r} objects={[o.Name for o in doc.Objects]!r}")
        dock = get_dock()
        if dock:
            dock.switch_to_document(doc)

    def slotCreatedDocument(self, doc):
        _log(f"slotCreatedDocument doc={doc.Name!r}")

    def slotDeletedDocument(self, doc):
        _log(f"slotDeletedDocument doc={doc.Name!r}")
        from .model_registry import invalidate_model
        invalidate_model(doc.Name)
        self._restoring.discard(doc.Name)
        dock = get_dock()
        if dock:
            active = FreeCAD.ActiveDocument
            dock.switch_to_document(active)


def get_dock():
    return _dock_instance


def show_dock():
    """Create or reveal the dock widget, attached to FreeCAD's main window."""
    global _dock_instance, _observer

    mw = FreeCADGui.getMainWindow()

    if _dock_instance is None:
        _dock_instance = TodoDockWidget(mw)
        mw.addDockWidget(Qt.LeftDockWidgetArea, _dock_instance)

        _observer = _DocObserver()
        FreeCAD.addDocumentObserver(_observer)

    _dock_instance.show()

    # Populate for the current active document.
    active = FreeCAD.ActiveDocument
    if active:
        _dock_instance.switch_to_document(active)


def hide_dock():
    if _dock_instance:
        _dock_instance.hide()
