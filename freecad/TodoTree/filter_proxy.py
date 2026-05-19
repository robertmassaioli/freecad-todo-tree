# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TodoTree addon.

"""QSortFilterProxyModel that hides done nodes (and their entire subtrees)."""

from PySide.QtCore import Qt, QSortFilterProxyModel
from .debug import log


class DoneFilterProxy(QSortFilterProxyModel):
    """
    When show_done is False, any row whose node has done=True is hidden,
    which also hides all descendants (Qt's default tree-filter behaviour).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._show_done = True

    def set_show_done(self, show):
        if show == self._show_done:
            return
        self._show_done = show
        self.invalidateFilter()

    def show_done(self):
        return self._show_done

    def setData(self, index, value, role=Qt.EditRole):
        log(f"proxy.setData: role={role!r} value={value!r}")
        return super().setData(index, value, role)

    def filterAcceptsRow(self, source_row, source_parent):
        if self._show_done:
            return True
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        node_id = source_model.data(idx, Qt.UserRole)
        if node_id:
            node = source_model._tree.get_node(node_id)
            if node and node.done:
                return False
        return True
