# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""
Main-window (MDI area) view for the todo tree.

Opens as a sub-window inside FreeCAD's central QMdiArea, similar to how
a Spreadsheet or Text Document opens. Each call to open_main_view() either
re-raises an existing window for the same document or creates a new one.
"""

from PySide.QtWidgets import QMdiSubWindow, QMdiArea
from PySide.QtCore import Qt

import FreeCADGui

from .tree_panel import TreePanel

# doc_name → QMdiSubWindow (weak tracking; window may have been closed)
_open_views: dict = {}


class TodoMainView(QMdiSubWindow):
    def __init__(self, fc_object, item_model, doc_name, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Todo Tree — {doc_name}")
        self._doc_name = doc_name

        # is_primary=False: the dock widget is the primary ViewState writer.
        panel = TreePanel(item_model, fc_object, is_primary=False, parent=self)
        self.setWidget(panel)
        self.resize(420, 600)

    def closeEvent(self, event):
        _open_views.pop(self._doc_name, None)
        super().closeEvent(event)


def open_main_view(fc_object, item_model):
    """Open or raise the main-area todo view for the document."""
    doc_name = fc_object.Document.Name

    # Re-raise if already open.
    existing = _open_views.get(doc_name)
    if existing is not None:
        existing.show()
        existing.raise_()
        mdi = _find_mdi_area()
        if mdi:
            mdi.setActiveSubWindow(existing)
        return

    mdi = _find_mdi_area()
    if mdi is None:
        FreeCAD.Console.PrintWarning("TodoTree: could not find MDI area.\n")
        return

    view = TodoMainView(fc_object, item_model, doc_name, parent=mdi)
    mdi.addSubWindow(view)
    view.show()
    _open_views[doc_name] = view


def _find_mdi_area():
    mw = FreeCADGui.getMainWindow()
    return mw.findChild(QMdiArea)
