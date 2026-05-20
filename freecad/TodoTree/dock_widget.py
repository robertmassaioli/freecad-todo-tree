# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Persistent dock widget and document observer.

The dock is created once and persists across workbench switches.
A DocumentObserver keeps it in sync when the active document changes.
"""

from PySide.QtWidgets import QDockWidget, QLabel, QWidget, QVBoxLayout, QPushButton
from PySide.QtCore import Qt

import FreeCAD
import FreeCADGui

from .tree_panel import TreePanel
from .debug import log as _log_raw, Category


def _log(msg):
    _log_raw(Category.DOCUMENT, msg)

_dock_instance = None
_observer = None


def _make_no_doc_placeholder(parent):
    """Placeholder shown when no document is open."""
    w = QLabel("Open a document to use Todo Tree.", parent)
    w.setAlignment(Qt.AlignCenter)
    return w


def _make_no_todos_placeholder(doc, dock, parent):
    """Placeholder shown when a document is open but has no TodoTree yet.

    Contains a single button that creates the TodoTree object and immediately
    starts editing the first item (Option B1 from the design proposal).
    """
    w = QWidget(parent)
    layout = QVBoxLayout(w)
    layout.setAlignment(Qt.AlignCenter)

    label = QLabel("No todo items yet.", w)
    label.setAlignment(Qt.AlignCenter)
    layout.addWidget(label)

    btn = QPushButton("+ Add your first item", w)
    btn.setFixedWidth(180)

    def _on_click():
        _log(f"placeholder button clicked for doc={doc.Name!r}")
        # ensure_model creates the TodoTree object on first call.
        from .model_registry import ensure_model
        model = ensure_model(doc)
        fc_obj = model._fc_object
        panel = TreePanel(model, fc_obj, is_primary=True, parent=dock)
        dock.setWidget(panel)
        dock._panel = panel
        # Immediately add an item and open it for editing.
        panel.add_item()

    btn.clicked.connect(_on_click)
    layout.addWidget(btn, alignment=Qt.AlignHCenter)
    return w


class TodoDockWidget(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Todo Tree", parent)
        self.setObjectName("TodoTreeDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._panel = None
        self._no_doc_placeholder = _make_no_doc_placeholder(self)
        self.setWidget(self._no_doc_placeholder)

    def switch_to_document(self, doc):
        """Replace the panel contents with the todo tree for doc."""
        old = self.widget()
        # Only clean up TreePanel instances — placeholders are cheap and can
        # stay in memory until the dock is destroyed.
        if old and isinstance(old, TreePanel):
            old.setParent(None)

        if doc is None:
            self.setWidget(self._no_doc_placeholder)
            self._panel = None
            return

        # Only look for an existing TodoTree — never create one here.
        # Creation happens on first user action via the placeholder button
        # or any + Item / + Child command.
        from .todo_object import find_todo_object
        fc_obj = find_todo_object(doc)
        _log(f"switch_to_document doc={doc.Name!r} existing_obj={fc_obj.Name if fc_obj else None!r}")

        if fc_obj is None:
            # Document has no TodoTree yet — show the actionable placeholder.
            placeholder = _make_no_todos_placeholder(doc, self, self)
            self.setWidget(placeholder)
            self._panel = None
            return

        from .model_registry import ensure_model
        model = ensure_model(doc)
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
